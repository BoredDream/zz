"""Assemble SAA scenario-count convergence evidence and paper figure."""
from __future__ import annotations

import csv
import json
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np

ROOT=Path(__file__).resolve().parent.parent
SAA=ROOT/"outputs/paper_analysis/saa"
OUT=ROOT/"outputs/paper_analysis/k_convergence"
REPORT=ROOT/"reports/saa_k_convergence.md"
FIG=ROOT/"figures/paper"
KS=(10,20,30,50,80)
TAGS=("0","01","02","03","012","013","023","0123")


def load_q3(K:int,tag:str)->dict:
    p=SAA/f"q3_K{K}_stages{tag}.json"
    if p.exists(): return json.loads(p.read_text(encoding="utf-8"))
    if K==30:
        return json.loads((ROOT/f"outputs/q3_multistage/summary_stages{tag}_K30.json").read_text(encoding="utf-8"))
    raise FileNotFoundError(p)


def metric(raw:dict,key:str)->float:
    z=raw["totals"]
    aliases={"emergency_kwh":"emergency_total_kwh"}
    if key in z: return float(z[key])
    if aliases.get(key) in z: return float(z[aliases[key]])
    daily=raw.get("daily",[])
    daily_keys={"planned_purchase_kwh":"plan_total_kwh"}
    dk=daily_keys.get(key,key)
    if daily and dk in daily[0]: return float(sum(x[dk] for x in daily))
    return float("nan")


def soc_stats(raw:dict)->tuple[float,float,float]:
    z=raw["totals"]
    if "soc_end_mean_kwh" in z:
        return float(z["soc_end_mean_kwh"]),float(z["soc_end_min_kwh"]),float(z["soc_end_max_kwh"])
    s=np.asarray([x["soc_end_kwh"] for x in raw["daily"]],dtype=float)
    return float(s.mean()),float(s.min()),float(s.max())


def main()->None:
    rows=[]
    for K in KS:
        for tag in TAGS:
            r=load_q3(K,tag)
            sm,sn,sx=soc_stats(r)
            rows.append({"model":"Q3","K":K,"stages":tag,"total_cost_yuan":metric(r,"total_cost_yuan"),
                         "emergency_kwh":metric(r,"emergency_kwh"),"curtail_kwh":metric(r,"curtail_kwh"),
                         "planned_purchase_kwh":metric(r,"planned_purchase_kwh"),
                         "charge_kwh":metric(r,"charge_kwh"),"discharge_kwh":metric(r,"discharge_kwh"),
                         "soc_end_mean_kwh":sm,"soc_end_min_kwh":sn,"soc_end_max_kwh":sx,
                         "solve_seconds":float(r.get("meta",{}).get("elapsed_seconds",np.nan))})
        for tag in ("0","0123"):
            r=json.loads((SAA/f"q4_K{K}_stages{tag}.json").read_text(encoding="utf-8"))
            sm,sn,sx=soc_stats(r)
            rows.append({"model":"Q4","K":K,"stages":tag,"total_cost_yuan":metric(r,"total_cost_yuan"),
                         "emergency_kwh":metric(r,"emergency_kwh"),"curtail_kwh":metric(r,"curtail_kwh"),
                         "planned_purchase_kwh":metric(r,"planned_purchase_kwh"),
                         "charge_kwh":metric(r,"charge_kwh"),"discharge_kwh":metric(r,"discharge_kwh"),
                         "soc_end_mean_kwh":sm,"soc_end_min_kwh":sn,"soc_end_max_kwh":sx,
                         "solve_seconds":float(r["meta"]["elapsed_seconds"])})
    OUT.mkdir(parents=True,exist_ok=True); FIG.mkdir(parents=True,exist_ok=True)
    (OUT/"k_convergence.json").write_text(json.dumps(rows,ensure_ascii=False,indent=2),encoding="utf-8")
    with (OUT/"k_convergence.csv").open("w",newline="",encoding="utf-8-sig") as f:
        w=csv.DictWriter(f,fieldnames=rows[0].keys());w.writeheader();w.writerows(rows)
    best={str(K):min((r for r in rows if r["model"]=="Q3" and r["K"]==K),key=lambda x:x["total_cost_yuan"])["stages"] for K in KS}
    q3_ref=next(r for r in rows if r["model"]=="Q3" and r["K"]==80 and r["stages"]=="0123")["total_cost_yuan"]
    q4_ref=next(r for r in rows if r["model"]=="Q4" and r["K"]==80 and r["stages"]=="0123")["total_cost_yuan"]
    lines=["# SAA情景数收敛分析", "", "主口径为两端效率各90%（往返81%）。K是最多采用的历史残差路径数；年初有效场景数受可用历史限制。", "",
           "|K|Q3最优发布组合|Q3-0123费用(元)|相对K80|Q4-仅0费用(元)|Q4-0123费用(元)|相对K80|Q4滚动节省|", "|---:|---|---:|---:|---:|---:|---:|---:|"]
    for K in KS:
        q3=next(r for r in rows if r["model"]=="Q3" and r["K"]==K and r["stages"]=="0123")
        a=next(r for r in rows if r["model"]=="Q4" and r["K"]==K and r["stages"]=="0")
        b=next(r for r in rows if r["model"]=="Q4" and r["K"]==K and r["stages"]=="0123")
        lines.append(f"|{K}|{best[str(K)]}|{q3['total_cost_yuan']:.2f}|{(q3['total_cost_yuan']/q3_ref-1):+.3%}|{a['total_cost_yuan']:.2f}|{b['total_cost_yuan']:.2f}|{(b['total_cost_yuan']/q4_ref-1):+.3%}|{(a['total_cost_yuan']-b['total_cost_yuan'])/a['total_cost_yuan']:.3%}|")
    lines += ["", "判据：费用相对K=80的偏差、最优发布组合是否一致，以及Q4滚动调整节省是否保持同号。详细紧急购电、弃光量和耗时见CSV。"]
    REPORT.write_text("\n".join(lines)+"\n",encoding="utf-8")
    fig,ax=plt.subplots(1,2,figsize=(10,4.1),layout="constrained")
    for model,tag,label in [("Q3","0123","Q3 0+6+12+18"),("Q4","0","Q4 only 0:00"),("Q4","0123","Q4 rolling")]:
        z=[r for r in rows if r["model"]==model and r["stages"]==tag]
        ax[0].plot([r["K"] for r in z],[r["total_cost_yuan"]/1e6 for r in z],marker="o",label=label)
        ax[1].plot([r["K"] for r in z],[r["emergency_kwh"]/1e3 for r in z],marker="o",label=label)
    ax[0].set(xlabel="Maximum scenario count K",ylabel="Annual cost (million yuan)")
    ax[1].set(xlabel="Maximum scenario count K",ylabel="Emergency purchase (MWh)")
    for a in ax:a.grid(alpha=.25);a.legend(fontsize=8)
    fig.savefig(FIG/"fig_k_convergence.png",dpi=300);fig.savefig(FIG/"fig_k_convergence.pdf")
    print(json.dumps({"best_q3":best,"rows":len(rows)},ensure_ascii=False,indent=2))


if __name__=="__main__":main()
