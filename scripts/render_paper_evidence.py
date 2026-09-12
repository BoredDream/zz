"""Render compact scientific figures from audited paper-analysis JSON files."""
from __future__ import annotations

import json
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np

ROOT=Path(__file__).resolve().parent.parent
FIG=ROOT/"figures/paper"


def calibration()->None:
    z=json.loads((ROOT/"outputs/paper_analysis/calibration/q4_calibration.json").read_text(encoding="utf-8"))
    fig,ax=plt.subplots(1,2,figsize=(9.5,4),layout="constrained")
    stages=np.arange(4); nominal=np.array([.5,.8,.9])
    for i,c in enumerate(("0.5","0.8","0.9")):
        ax[0].plot(stages,[z["net_load"][str(m)]["central_interval_coverage"][c] for m in stages],marker="o",label=f"Nominal {float(c):.0%}")
        ax[0].axhline(float(c),color=f"C{i}",ls="--",alpha=.35)
    ax[0].set(xlabel="Forecast update stage",ylabel="Empirical marginal coverage",xticks=stages,ylim=(.35,.95))
    crps=[z["net_load"][str(m)]["mean_crps"] for m in stages]
    ax[1].plot(stages,crps,marker="o",color="C3")
    ax[1].set(xlabel="Forecast update stage",ylabel="Net-load CRPS (kWh)",xticks=stages)
    ax[0].legend(fontsize=8)
    for a in ax:a.grid(alpha=.25)
    fig.savefig(FIG/"fig_scenario_calibration.png",dpi=300);fig.savefig(FIG/"fig_scenario_calibration.pdf")


def monthly()->None:
    z=json.loads((ROOT/"outputs/paper_analysis/bootstrap/paired_bootstrap.json").read_text(encoding="utf-8"))
    fig,axes=plt.subplots(len(z["comparisons"]),1,figsize=(9,7.5),layout="constrained")
    for ax,c in zip(axes,z["comparisons"]):
        m=c["months"]; x=np.arange(len(m)); vals=np.array([r["saving_yuan"] for r in m])/1000
        ax.bar(x,vals,color=np.where(vals>=0,"#2878B5","#C82423"));ax.axhline(0,color="black",lw=.7)
        ax.set_xticks(x,[r["month"][5:] for r in m]);ax.set_ylabel("Saving (k yuan)");ax.set_title(c["name"],fontsize=10);ax.grid(axis="y",alpha=.2)
    axes[-1].set_xlabel("Month in 2025")
    fig.savefig(FIG/"fig_bootstrap_monthly.png",dpi=300);fig.savefig(FIG/"fig_bootstrap_monthly.pdf")


def main()->None:
    FIG.mkdir(parents=True,exist_ok=True);calibration();monthly();print(FIG)


if __name__=="__main__":main()
