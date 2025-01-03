#%%
import torch
import numpy as np
import pandas as pd
from torch_geometric import seed_everything
import final_model, training_utils
import pickle
import final_model, training_utils, prediction_utils
from sklearn.metrics import roc_auc_score, accuracy_score, average_precision_score, precision_score, recall_score
seed_everything(0)
#%%
data_folder = "../../data/processed/graph_data_nohubs/merged_types/split_dataset/"
models_folder = "../../models/final_model/"
feature_folder = "../../data/processed/feature_data/"
device = torch.device('cuda' if torch.cuda.is_available() else 'cpu')
#%%
seeds = [4,5,6,7,8]
node_df = pd.read_csv(data_folder+f"seed_{seeds[-1]}/tensor_df.csv",index_col=0).set_index("node_index",drop=True)
#load data
data = []
for seed in seeds:
    datasets, node_map = training_utils.load_data(data_folder+f"seed_{seed}/",load_test=True)
    data.append(datasets)

with open(f"{models_folder}training_parameters.pickle", 'rb') as handle:
    params = pickle.load(handle)

#initialize features in test data
test_data = []
for dataset in data:
    test_set = dataset[2]
    test_data.append(training_utils.initialize_features(test_set,params["feature_type"],params["feature_dim"],feature_folder))

#load models
models = []
for seed in seeds:
    weights_path = models_folder+f"seeds/final_model_{seed}.pth"
    weights = torch.load(weights_path)
    model = final_model.Model(test_data[-1].metadata(),[("gene_protein","gda","disease")])
    model.load_state_dict(weights)
    models.append(model)
#%%
def full_eval(data,node_df):
    encodings_dict = training_utils.get_encodings(model,data)
    predictor = prediction_utils.Predictor(node_df,encodings_dict)

    preds = predictor.predict_supervision_edges(data,("gene_protein","gda","disease"))
    y_true = preds.label.values
    y_score = preds.score.values
    y_pred_labels = preds.score.values.round()

    auc = roc_auc_score(y_true,y_score)
    acc = accuracy_score(y_true,y_pred_labels)
    ap = average_precision_score(y_true,y_score)
    precision = precision_score(y_true,y_pred_labels)
    recall = recall_score(y_true,y_pred_labels)

    return {"auc":auc, "acc":acc, "ap":ap, "precision":precision, "recall":recall}

all_results = []
for seed in test_data:
    eval_results = full_eval(seed,node_df)
    all_results.append(eval_results)
#%%
all_results_df = pd.DataFrame(all_results)
all_results_df.loc['mean'] = all_results_df.mean()
all_results_df.loc["std"] = all_results_df.std()
#%%
all_results_df.to_csv(f"{models_folder}test_eval.csv")
