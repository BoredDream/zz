"""Strict same-predictor Q4 comparison and paper-ready cost-breakdown figure."""
from __future__ import annotations

import json
from pathlib import Path

import matplotlib.pyplot as plt

ROOT=Path(__file__).resolve().parent.parent
SAA=ROOT/"outputs/paper_analysis/saa"
OUT=ROOT/"outputs/paper_analysis/q4_controlled"
REPORT=ROOT/"reports/q4_controlled_comparison.md"
FIG=ROOT/"figures/paper"


def main()->None:
    a=json.loads((SAA/"q4_K30_stages0.json").read_text(encoding="utf-8"))
    b=json.loads((SAA/"q4_K30_stages0123.json").read_text(encoding="utf-8"))
    ta,tb=a["totals"],b["totals"]
    keys=("total_cost_yuan","planned_purchase_kwh","emergency_kwh","charge_kwh","discharge_kwh","curtail_kwh")
    result={"design":{"predictor":"q4_solver shared load, PV and price predictor","K":30,
                      "baseline_stages":[0],"rolling_stages":[0,1,2,3],
                      "controlled_variables":["data","predictor","scenario generator","K","efficiency","settlement","initial SOC"]},
            "baseline":ta,"rolling":tb,
            "difference_baseline_minus_rolling":{k:ta[k]-tb[k] for k in keys},
            "cost_saving_pct":(ta["total_cost_yuan"]-tb["total_cost_yuan"])/ta["total_cost_yuan"]*100}
    OUT.mkdir(parents=True,exist_ok=True);FIG.mkdir(parents=True,exist_ok=True)
    (OUT/"comparison.json").write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding="utf-8")
    labels={"total_cost_yuan":"总购电费(元)","planned_purchase_kwh":"计划购电量(kWh)","emergency_kwh":"紧急购电量(kWh)","charge_kwh":"充电量(kWh)","discharge_kwh":"放电量(kWh)","curtail_kwh":"弃光量(kWh)"}
    lines=["# Q4共同预测器严格控制变量对照", "", "两组均使用 `q4_solver` 的同一负荷、光伏与价格预测器、同一残差路径场景、K=30、往返效率81%及相同结算规则；唯一处理差异是是否允许6:00、12:00、18:00滚动调整。", "",
           "|指标|仅0:00决策|0+6+12+18滚动|基准−滚动|", "|---|---:|---:|---:|"]
    for k in keys: lines.append(f"|{labels[k]}|{ta[k]:.2f}|{tb[k]:.2f}|{ta[k]-tb[k]:.2f}|")
    lines += ["",f"严格对照下，滚动调整节省 **{result['cost_saving_pct']:.3f}%**。该差异可以解释为同一预测体系下信息更新与调整权的联合价值。", "",
              "注意：它不能分解为纯信息价值与纯调整权价值；若需分别识别，仍须增加‘更新预测但禁止调整’或‘不更新预测但允许调整’的额外组。"]
    REPORT.write_text("\n".join(lines)+"\n",encoding="utf-8")
    parts=("plan_cost_yuan","adjust_cost_yuan","emergency_cost_yuan")
    names=("Planned purchase","Adjustment","Emergency")
    fig,ax=plt.subplots(figsize=(6.6,4.5),layout="constrained")
    bottoms=[0.,0.]
    for k,name in zip(parts,names):
        vals=[ta[k]/1e6,tb[k]/1e6]
        ax.bar([0,1],vals,bottom=bottoms,label=name)
        bottoms=[bottoms[i]+vals[i] for i in range(2)]
    ax.set_xticks([0,1],["Only 0:00","0:00+6:00+12:00+18:00"])
    ax.set_ylabel("Annual cost (million yuan)");ax.legend();ax.grid(axis="y",alpha=.25)
    ax.set_title(f"Same-predictor Q4 comparison: {result['cost_saving_pct']:.2f}% saving")
    fig.savefig(FIG/"fig_q4_controlled.png",dpi=300);fig.savefig(FIG/"fig_q4_controlled.pdf")
    print(json.dumps(result,ensure_ascii=False,indent=2))


if __name__=="__main__":main()
