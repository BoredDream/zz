"""Independent structural and arithmetic checks for the paper-analysis package."""
from __future__ import annotations

import json
from pathlib import Path

ROOT=Path(__file__).resolve().parent.parent


def load(p:str): return json.loads((ROOT/p).read_text(encoding="utf-8"))


def main()->None:
    ctl=load("outputs/paper_analysis/q4_controlled/comparison.json")
    a,b=ctl["baseline"],ctl["rolling"]
    assert a["delivery_days"]==b["delivery_days"]==334
    assert abs((a["total_cost_yuan"]-b["total_cost_yuan"])-ctl["difference_baseline_minus_rolling"]["total_cost_yuan"])<1e-6
    assert abs(100*(a["total_cost_yuan"]-b["total_cost_yuan"])/a["total_cost_yuan"]-ctl["cost_saving_pct"])<1e-10
    boot=load("outputs/paper_analysis/bootstrap/paired_bootstrap.json")
    for z in boot["comparisons"]:
        assert z["days"]==334 and z["ci95_yuan"][0]<=z["annual_saving_yuan"]<=z["ci95_yuan"][1]
        assert sum(m["days"] for m in z["months"])==334
    cal=load("outputs/paper_analysis/calibration/q4_calibration.json")
    for variable in ("net_load","price"):
        for m in range(4):
            z=cal[variable][str(m)]
            assert z["n_vectors"]==334
            assert all(0<=x<=1 for x in z["central_interval_coverage"].values())
            assert all(0<=x<=1 for x in z["quantile_calibration"].values())
    print("paper analysis validation passed")


if __name__=="__main__":main()
