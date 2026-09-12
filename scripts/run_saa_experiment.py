"""Run comparable Q3/Q4 SAA experiments and retain daily evidence."""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
OUT = ROOT / "outputs" / "paper_analysis" / "saa"
DELIVERY_START = "2025-02-01"


def summarize(module, records, *, q4: bool) -> tuple[list[dict], dict]:
    start = module.DSTR.index(DELIVERY_START)
    daily = []
    for d in sorted(records):
        if d < start:
            continue
        r, n = records[d], records[d]["natural"]
        if q4:
            plan, adjust, emergency_cost = module.natural_settle_parts4(
                d, r["natural_x"], r["natural_q"], n["z"])
        else:
            plan, adjust, emergency_cost = module.natural_settle_parts(
                r["natural_x"], r["natural_q"], n["z"])
        row = {
            "date": module.DSTR[d],
            "total_cost_yuan": float(plan.sum() + adjust.sum() + emergency_cost.sum()),
            "plan_cost_yuan": float(plan.sum()),
            "adjust_cost_yuan": float(adjust.sum()),
            "emergency_cost_yuan": float(emergency_cost.sum()),
            "planned_purchase_kwh": float(r["natural_q"].sum()),
            "emergency_kwh": float(n["z"].sum()),
            "charge_kwh": float(n["c"].sum()),
            "discharge_kwh": float(n["g"].sum()),
            "curtail_kwh": float(n["w"].sum()),
            "soc_start_kwh": float(r["S0"]),
            "soc_end_kwh": float(r["S24"]),
        }
        daily.append(row)
    keys = [k for k in daily[0] if k not in ("date", "soc_start_kwh", "soc_end_kwh")]
    totals = {k: float(sum(row[k] for row in daily)) for k in keys}
    soc = np.asarray([row["soc_end_kwh"] for row in daily])
    totals.update(soc_end_mean_kwh=float(soc.mean()), soc_end_min_kwh=float(soc.min()),
                  soc_end_max_kwh=float(soc.max()), delivery_days=len(daily))
    return daily, totals


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("model", choices=("q3", "q4"))
    parser.add_argument("K", type=int)
    parser.add_argument("stages", help="comma-separated stages, e.g. 0 or 0,1,2,3")
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()
    stages = tuple(int(x) for x in args.stages.split(","))
    tag = "".join(str(x) for x in stages)
    OUT.mkdir(parents=True, exist_ok=True)
    path = OUT / f"{args.model}_K{args.K}_stages{tag}.json"
    if path.exists() and not args.force:
        print(f"exists: {path}")
        return

    t0 = time.perf_counter()
    if args.model == "q3":
        import q3_multistage as module
        records, _ = module.backtest(0, module.ND, K=args.K, stages=stages,
                                     S0=6000.0, verbose=True)
        daily, totals = summarize(module, records, q4=False)
    else:
        import q4_solver as module
        records, _ = module.backtest4(0, module.ND, K=args.K, stages=stages,
                                      S0=6000.0, verbose=True)
        daily, totals = summarize(module, records, q4=True)
    payload = {
        "meta": {"model": args.model, "K_max": args.K, "stages": list(stages),
                 "efficiency": {"eta_charge": 0.9, "eta_discharge": 0.9,
                                "roundtrip": 0.81},
                 "delivery_period": ["2025-02-01", "2025-12-31"],
                 "elapsed_seconds": time.perf_counter() - t0},
        "totals": totals,
        "daily": daily,
    }
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"path": str(path), "elapsed_seconds": payload["meta"]["elapsed_seconds"],
                      "total_cost_yuan": totals["total_cost_yuan"]}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
