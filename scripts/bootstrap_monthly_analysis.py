"""Paired moving-block bootstrap and monthly stratification for policy costs."""
from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "outputs" / "paper_analysis" / "bootstrap"
REPORT = ROOT / "reports" / "bootstrap_monthly.md"


def read_daily(path: Path) -> dict[str, float]:
    rows = json.loads(path.read_text(encoding="utf-8"))["daily"]
    return {r["date"]: float(r["total_cost_yuan"]) for r in rows}


def compare(name: str, baseline: Path, enhanced: Path, seed: int) -> dict:
    a, b = read_daily(baseline), read_daily(enhanced)
    dates = sorted(set(a) & set(b))
    delta = np.asarray([a[d]-b[d] for d in dates])
    n, block, B = len(delta), 7, 10000
    rng = np.random.default_rng(seed)
    starts = rng.integers(0, n, size=(B, int(np.ceil(n/block))))
    offsets = np.arange(block)
    idx = (starts[:, :, None] + offsets) % n
    boot = delta[idx.reshape(B, -1)[:, :n]].sum(1)
    by_month = defaultdict(list)
    for d, x in zip(dates, delta): by_month[d[:7]].append(float(x))
    months = [{"month": m, "saving_yuan": float(sum(x)), "positive_days": int(sum(v>0 for v in x)),
               "days": len(x), "worst_day_yuan": float(min(x)), "best_day_yuan": float(max(x))}
              for m,x in sorted(by_month.items())]
    return {"name": name, "definition": "baseline daily cost minus enhanced daily cost",
            "days": n, "annual_saving_yuan": float(delta.sum()),
            "saving_pct_of_baseline": float(delta.sum()/sum(a[d] for d in dates)*100),
            "ci95_yuan": [float(x) for x in np.quantile(boot, [.025,.975])],
            "bootstrap_positive_probability": float(np.mean(boot>0)),
            "positive_days": int(np.sum(delta>0)), "loss_days": int(np.sum(delta<0)),
            "worst_day_yuan": float(delta.min()), "best_day_yuan": float(delta.max()),
            "block_days": block, "replicates": B, "months": months}


def main() -> None:
    q3 = ROOT/"outputs/q3_multistage"
    saa = ROOT/"outputs/paper_analysis/saa"
    specs = [
      ("Q3: stages0 vs stages0123", q3/"summary_stages0_K30.json", q3/"summary_stages0123_K30.json"),
      ("Q3: stages023 vs stages013", q3/"summary_stages023_K30.json", q3/"summary_stages013_K30.json"),
      ("Q4 common predictor: stages0 vs stages0123", saa/"q4_K30_stages0.json", saa/"q4_K30_stages0123.json")]
    missing=[str(p) for _,a,b in specs for p in (a,b) if not p.exists()]
    if missing: raise FileNotFoundError("missing controlled results: "+", ".join(missing))
    result={"method":"paired circular moving-block bootstrap", "comparisons":
            [compare(name,a,b,20250912+i) for i,(name,a,b) in enumerate(specs)]}
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT/"paired_bootstrap.json").write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding="utf-8")
    lines=["# 逐日费用差Bootstrap与月度分层", "", "定义：节省 = 基准策略费用 − 增强策略费用。采用7日循环移动块、10,000次配对Bootstrap。", "",
           "|对照|年度节省(元)|相对节省|95% CI(元)|Bootstrap节省为正|正收益日/总日|最差单日(元)|", "|---|---:|---:|---:|---:|---:|---:|"]
    for z in result["comparisons"]:
        lo,hi=z["ci95_yuan"]
        lines.append(f"|{z['name']}|{z['annual_saving_yuan']:.2f}|{z['saving_pct_of_baseline']:.3f}%|[{lo:.2f}, {hi:.2f}]|{z['bootstrap_positive_probability']:.1%}|{z['positive_days']}/{z['days']}|{z['worst_day_yuan']:.2f}|")
    for z in result["comparisons"]:
        lines += ["", f"## {z['name']}：月度", "", "|月份|节省(元)|正收益日/天数|最差单日(元)|", "|---|---:|---:|---:|"]
        for m in z["months"]:
            lines.append(f"|{m['month']}|{m['saving_yuan']:.2f}|{m['positive_days']}/{m['days']}|{m['worst_day_yuan']:.2f}|")
    lines += ["", "解释边界：置信区间针对本年度逐日费用差的时间块重采样，不代表跨年度结构不确定性。"]
    REPORT.write_text("\n".join(lines)+"\n",encoding="utf-8")
    print(json.dumps(result,ensure_ascii=False,indent=2))


if __name__ == "__main__": main()
