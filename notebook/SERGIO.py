import numpy as np
import pandas as pd 
import scanpy as sc 
# import matplotlib.pyplot as plt
# import seaborn as sns
# from scipy import stats
# from PIL import Image
# import io
import os
from sklearn.metrics import roc_curve, roc_auc_score, precision_recall_curve, average_precision_score
# from time import time 

# import matplotlib as mpl
# mpl.rcParams['interactive'] == False
# mpl.rcParams['lines.linewidth'] = 2
# mpl.rcParams['lines.linestyle'] = '--'
# mpl.rcParams['axes.titlesize'] = 24
# mpl.rcParams['axes.labelsize'] = 16
# mpl.rcParams['lines.markersize'] = 2
# mpl.rcParams['xtick.labelsize'] = 16
# mpl.rcParams['ytick.labelsize'] = 16
# mpl.rcParams['figure.dpi'] = 80
# mpl.rcParams['legend.fontsize'] = 12
# markers = [".",",","o","v","^","<",">"]
# linestyles = ['-', '--', '-.', ':', 'dashed', 'dashdot', 'dotted']

import GenKI as gk
from GenKI.preprocesing import build_adata
from GenKI.train import VGAE_trainer
from GenKI import utils
from scTenifold import scTenifoldKnk


def main(args):
    file = args.data
    # target_gene = args.KO

    exp = pd.read_csv(f"SERGIO/De-noised_{file}/simulated_noNoise_0.csv", index_col=0)
    gt_grn_df = pd.read_csv(f"SERGIO/De-noised_{file}/gt_GRN.csv", header=None)
    inds = list(zip(gt_grn_df[0], gt_grn_df[1]))
    gt_grn = np.zeros((len(exp), len(exp))).astype(int)
    for ind in inds:
        gt_grn[ind] = 1

    genes = np.arange(len(exp)).astype(str)
    genes = np.char.add(["g"]*len(genes), genes)
    idx = np.unique(gt_grn_df[0].to_numpy())
    KO_genes = genes[idx] # gene list to be KO
    print(KO_genes)

    ada = sc.AnnData(exp.values.T)
    ada.var_names = genes
    ada_WT = build_adata(ada, scale_data = True, uppercase=False)

    for target_gene in KO_genes:
        data_wrapper = gk.DataLoader(ada_WT, 
                        target_gene = [target_gene], 
                        target_cell = None, 
        #                 obs_label = None,
                        GRN_file_dir = 'GRNs',
                        rebuild_GRN = False,
                        pcNet_name = f'pcNet_{file}_0_man', # build network
                        cutoff = 85,
                        verbose = False,
                            )
        ko_idx = data_wrapper([target_gene])[0]		
        labels = np.zeros(len(exp)).astype(int)
        labels_inds = gt_grn_df.loc[gt_grn_df[0]==ko_idx, 1].to_numpy().astype(int)
        labels[labels_inds] = 1	
        data = data_wrapper.load_data()		
        data_KO = data_wrapper.load_kodata()

        hyperparams = {"epochs": 75, 
                    "lr": 7e-4, 
                    "beta": 1e-4, 
                    "seed": 8096} 
        log_dir=None 

        sensei = VGAE_trainer(data, 
                            epochs=hyperparams["epochs"], 
                            lr=hyperparams["lr"], 
                            log_dir=log_dir, 
                            beta=hyperparams["beta"],
                            seed=hyperparams["seed"],
                            )
        sensei.train()
        z_mu, z_std = sensei.get_latent_vars(data)
        z_mu_KO, z_std_KO = sensei.get_latent_vars(data_KO)
        dis = gk.utils.get_distance(z_mu_KO, z_std_KO, z_mu, z_std, by = 'KL')
        res = utils.get_generank(data, dis, rank=False)
        scores = res["dis"].to_numpy()
        fpr, tpr, thres = roc_curve(labels, scores)
        roc_auc = roc_auc_score(labels, scores)
        print("AUROC:", roc_auc)
        precision, recall, _ = precision_recall_curve(labels, scores)
        ap = average_precision_score(labels, scores)
        print("AP:", ap)

        exp.index = genes
        # sct = scTenifoldKnk(data=exp,
        #            ko_method="default",
        #            ko_genes=[target_gene],  # the gene you wants to knock out
        #            qc_kws={"min_lib_size": 1, "min_percent": 0.001},
        #            )
        # result = sct.build()

        knk = scTenifoldKnk(data=exp,
                        qc_kws={"min_lib_size": 1, "min_percent": 0.001},
                        )
        knk.run_step("qc")
        knk.run_step("nc", n_cpus=1)
        knk.run_step("td")
        knk.run_step("ko", ko_genes=[target_gene], ko_method="default")
        knk.run_step("ma")
        knk.run_step("dr", sorted_by="adjusted p-value")
        result = knk.d_regulation

        knk_score = dict(zip(result["Gene"], result["FC"]))
        res["temp"] = res.index
        res["Knk"] = res["temp"].map(knk_score)
        del res["temp"]
        scores_knk = res["Knk"].to_numpy()
        fpr_knk, tpr_knk, thres_knk = roc_curve(labels, scores_knk)
        roc_auc_knk = roc_auc_score(labels, scores_knk)
        print(roc_auc_knk)
        precision_knk, recall_knk, _ = precision_recall_curve(labels, scores_knk)
        ap_knk = average_precision_score(labels, scores_knk)
        print(ap_knk)

        try:
            f = open(os.path.join("result", f'{args.out}.txt'), 'r')
        except IOError:
            f = open(os.path.join("result", f'{args.out}.txt'), 'w')
            f.writelines("file,KO_gene,ROC,ROC_Knk,AP,AP_Knk\n")
        finally:  
            f = open(os.path.join("result", f'{args.out}.txt'), 'a')
            f.writelines(f"{file}, {target_gene}, {roc_auc:.4f}, {roc_auc_knk:.4f}, {ap:.4f}, {ap_knk:.4f}\n")
            f.close()


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('--data', type = str, default = '100G_9T_300cPerT_4_DS1')
    # parser.add_argument('-K', '--KO', type = str, default = 'g1')
    parser.add_argument('-O', '--out', default = 'SERGIO')
    
    args = parser.parse_args()
    main(args)
