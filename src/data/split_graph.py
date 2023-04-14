#%%
import torch
from torch_geometric.data import HeteroData
import torch_geometric.transforms as T
import pandas as pd
import random

random.seed(0)
torch.manual_seed(0)
#%%
def load_node_csv(path, index_col,type_col, **kwargs):
    """Returns node dataframe and a dict of mappings for each node type. 
    Each mapping maps from original df index to "heterodata index" { node_type : { dataframe_index : heterodata_index}}"""
    df = pd.read_csv(path, **kwargs,index_col=index_col)
    node_types = df[type_col].unique()
    mappings_dict = dict()
    for node_type in node_types:
        mapping = {index: i for i, index in enumerate(df[df[type_col] == node_type].index.unique())}
        mappings_dict[node_type] = mapping

    return df,mappings_dict

def load_edge_csv(path, src_index_col, dst_index_col, mappings, edge_type_col,src_type_col,dst_type_col, **kwargs):
    """Returns edge dataframe and a dict of edge indexes. Nodes are indexed according to the "heterodata index", using the node mappings from load_node_csv. Edge indexes are tensors of shape [2, num_edges]. Dict is indexed by triplets of shape (src_type, edge_type, dst_type)."""
    df = pd.read_csv(path, **kwargs)
    df["edge_triple"] = list(zip(df[src_type_col],df[edge_type_col], df[dst_type_col]))
    edge_triplets = df["edge_triple"].unique()

    edge_index_dict = dict()
    for edge_triplet in edge_triplets:

        sub_df = df[df.edge_triple == edge_triplet]
        src_type,edge_type,dst_type = edge_triplet

        src_mapping = mappings[src_type]
        dst_mapping = mappings[dst_type]

        src = [src_mapping[index] for index in sub_df[src_index_col]]
        dst = [dst_mapping[index] for index in sub_df[dst_index_col]]
        edge_index = torch.tensor([src, dst])
        edge_index_dict[edge_triplet] = edge_index

    return df, edge_index_dict

def create_heterodata(node_map, edge_index):
    """Initializes HeteroData object from torch_geometric and creates corresponding nodes and edges, without any features"""
    data = HeteroData()
    for node_type,vals in node_map.items():
        # Initialize all node types without features
        data[node_type].num_nodes = len(vals)
    
    for edge_triplet, index in edge_index.items():
        src_type, edge_type, dst_type = edge_triplet
        data[src_type, edge_type, dst_type].edge_index = index
    
    return data

def get_reverse_types(edge_types):
    newlist = []
    for edge in edge_types:
        rev = tuple(reversed(edge))
        if rev != edge:
            if edge not in newlist:
                newlist.append(rev)
        else:
            newlist.append(rev)

    reversed_newlist = [tuple(reversed(edge)) for edge in newlist]

    return newlist, reversed_newlist
#%%
data_folder = "../../data/processed/graph_data_nohubs/"
node_data, node_map = load_node_csv(data_folder+"nohub_graph_nodes.csv","node_index","node_type")
edge_data, edge_index = load_edge_csv(data_folder+"nohub_graph_edge_data.csv","x_index","y_index",node_map,"edge_type","x_type","y_type")

data = create_heterodata(node_map,edge_index)
#%%
edge_types, rev_edge_types = get_reverse_types(data.edge_types)
p_val = 0.1
p_test = 0.1
p_train = round(1 - p_val - p_test,1)

split_transform = T.RandomLinkSplit(num_val=p_val, num_test=p_test, is_undirected=True, add_negative_train_samples=True, disjoint_train_ratio=0.2,edge_types=edge_types,rev_edge_types=rev_edge_types)
transform_dataset = T.Compose([split_transform, T.ToSparseTensor(remove_edge_index=False)])

train_data, val_data, test_data = transform_dataset(data)
#%%
# Test if splits are correct
def test_equal_num_edges(dataset):
    num_gda_r = dataset[("disease", "gda", "gene_protein")]["edge_index"].shape[1]
    num_gda_l = dataset[("gene_protein", "gda", "disease")]["edge_index"].shape[1]
    print(f"num gda edges in both directions is equal: {num_gda_r == num_gda_l}")

def test_is_correct_p(dataset,p,total_num,prev_edges):
    #num_supervision divided by 2 because the same number of edges is generated as negative samples.
    #These are directed (i.e, a single link in one direction)
    num_supervision = dataset[("gene_protein", "gda", "disease")]["edge_label"].shape[0]/2

    #num_msg divided by 2 because these links are undirected (i.e, two links per edge, one in each direction)
    num_msg = dataset[("gene_protein", "gda", "disease")]["edge_index"].shape[1]

    num = round(num_supervision + num_msg)
    expected_num = round(p*total_num + prev_edges)
    print(f"Is expected % of edges: {num == expected_num}")
    print(f"Expected {expected_num}, is {num}")

total_num_gda = data[("disease", "gda", "gene_protein")]["edge_index"].shape[1]

datasets = [train_data,val_data,test_data]
percentage = [p_train,p_val,p_test]
names = ["train","validation","test"]

prev_edges = 0
for name,dataset,p in zip(names,datasets,percentage):
    print(name +":")
    test_equal_num_edges(dataset)
    test_is_correct_p(dataset,p,total_num_gda,prev_edges)
    print("\n")

    prev_edges = round(dataset[("gene_protein", "gda", "disease")]["edge_label"].shape[0]/2 + dataset[("gene_protein", "gda", "disease")]["edge_index"].shape[1])

#%%
# Save splits to cpu
split_folder = data_folder+"split_dataset/"
torch.save(data,split_folder+"full_dataset"+".pt")

for dataset,name in zip(datasets,names):
    path = split_folder+name+".pt"
    torch.save(dataset,path)
#%%