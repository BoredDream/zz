"""Unified Q1--Q4 efficiency-scenario runner.

Each worker changes only the shared (eta_charge, eta_discharge) convention and
writes compact comparison metrics without overwriting any delivered workbook.
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from dataclasses import asdict, replace
from datetime import date
from pathlib import Path
from typing import Any

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from efficiency import EFFICIENCY_SCENARIOS, EfficiencyParameters  # noqa: E402

OUT = ROOT / "outputs" / "efficiency_sensitivity"
DATA = ROOT / "problem" / "data"
DELIVERY_START = date(2025, 2, 1)


def activity(values: np.ndarray, tol: float = 1e-7) -> int:
    return int(np.count_nonzero(np.asarray(values) > tol))


def base_payload(question: str, scenario: str, eff: EfficiencyParameters, elapsed: float) -> dict[str, Any]:
    return {
        "question": question,
        "scenario": scenario,
        "efficiency": {**asdict(eff), "roundtrip_efficiency": eff.roundtrip_efficiency},
        "elapsed_seconds": elapsed,
        "capacity": {"optimized": False, "installed_capacity_kwh": 12000.0},
    }


def run_q1(scenario: str, eff: EfficiencyParameters) -> dict[str, Any]:
    import q1_solver as M

    t0 = time.perf_counter()
    cfg = replace(M.Config(), eta_charge=eff.eta_charge, eta_discharge=eff.eta_discharge)
    inputs = M.load_inputs(DATA, cfg)
    sol = M.solve_day(inputs, cfg, cfg.initial_soc_kwh, cyclic=True)
    out = base_payload("q1", scenario, eff, time.perf_counter() - t0)
    out["metrics"] = {
        "total_purchase_cost_yuan": float(sol["purchase_cost_yuan"]),
        "total_purchase_kwh": float(sol["grid"].sum()),
        "planned_purchase_kwh": float(sol["grid"].sum()),
        "charge_kwh": float(sol["charge"].sum()),
        "discharge_kwh": float(sol["discharge"].sum()),
        "curtail_kwh": float(sol["curtail"].sum()),
        "emergency_purchase_kwh": 0.0,
        "adjustment_cost_yuan": 0.0,
    }
    out["strategy"] = {
        "charge_intervals": activity(sol["charge"]),
        "discharge_intervals": activity(sol["discharge"]),
        "curtail_intervals": activity(sol["curtail"]),
    }
    return out


def run_q2(scenario: str, eff: EfficiencyParameters) -> dict[str, Any]:
    import q2_solver as M

    t0 = time.perf_counter()
    cfg = replace(M.Config(), eta_charge=eff.eta_charge, eta_discharge=eff.eta_discharge)
    inputs = M.load_inputs(DATA, cfg)
    records = M.simulate(inputs, cfg)
    summary, _, _ = M.assemble(records, inputs, cfg)
    delivered = [r for r in records if r["date"] >= DELIVERY_START]
    totals = summary["totals_natural_day"]
    charge = np.concatenate([r["charge"] for r in delivered])
    discharge = np.concatenate([r["discharge"] for r in delivered])
    emergency = np.concatenate([r["emergency"] for r in delivered])
    surplus = np.concatenate([r["surplus"] for r in delivered])
    out = base_payload("q2", scenario, eff, time.perf_counter() - t0)
    out["metrics"] = {
        "total_purchase_cost_yuan": float(totals["total_cost_yuan"]),
        "planned_purchase_cost_yuan": float(totals["planned_purchase_cost_yuan"]),
        "total_purchase_kwh": float(totals["planned_purchase_kwh"] + totals["emergency_purchase_kwh"]),
        "planned_purchase_kwh": float(totals["planned_purchase_kwh"]),
        "charge_kwh": float(charge.sum()),
        "discharge_kwh": float(discharge.sum()),
        "curtail_kwh": float(surplus.sum()),
        "emergency_purchase_kwh": float(emergency.sum()),
        "adjustment_cost_yuan": 0.0,
    }
    out["strategy"] = {
        "charge_intervals": activity(charge), "discharge_intervals": activity(discharge),
        "curtail_intervals": activity(surplus), "emergency_intervals": activity(emergency),
    }
    return out


def multistage_metrics(M: Any, rec: dict[int, dict[str, Any]], start: int, q4: bool = False) -> tuple[dict[str, float], dict[str, int]]:
    totals = {k: 0.0 for k in ("total_purchase_cost_yuan", "planned_purchase_cost_yuan",
                               "adjustment_cost_yuan", "emergency_cost_yuan", "planned_purchase_kwh",
                               "emergency_purchase_kwh", "charge_kwh", "discharge_kwh", "curtail_kwh")}
    arrays = {k: [] for k in ("c", "g", "z", "w")}
    adjusted = []
    for d in sorted(rec):
        if d < start:
            continue
        r, n = rec[d], rec[d]["natural"]
        if q4:
            plan, adjust, emergency_cost = M.natural_settle_parts4(d, r["natural_x"], r["natural_q"], n["z"])
        else:
            plan, adjust, emergency_cost = M.natural_settle_parts(r["natural_x"], r["natural_q"], n["z"])
        totals["planned_purchase_cost_yuan"] += float(plan.sum())
        totals["adjustment_cost_yuan"] += float(adjust.sum())
        totals["emergency_cost_yuan"] += float(emergency_cost.sum())
        totals["planned_purchase_kwh"] += float(r["natural_q"].sum())
        totals["emergency_purchase_kwh"] += float(n["z"].sum())
        totals["charge_kwh"] += float(n["c"].sum())
        totals["discharge_kwh"] += float(n["g"].sum())
        totals["curtail_kwh"] += float(n["w"].sum())
        for key in arrays:
            arrays[key].append(n[key])
        adjusted.append(np.abs(r["natural_q"] - r["natural_x"]))
    totals["total_purchase_cost_yuan"] = (totals["planned_purchase_cost_yuan"] +
                                            totals["adjustment_cost_yuan"] + totals["emergency_cost_yuan"])
    totals["total_purchase_kwh"] = totals["planned_purchase_kwh"] + totals["emergency_purchase_kwh"]
    strategy = {
        "charge_intervals": activity(np.concatenate(arrays["c"])),
        "discharge_intervals": activity(np.concatenate(arrays["g"])),
        "curtail_intervals": activity(np.concatenate(arrays["w"])),
        "emergency_intervals": activity(np.concatenate(arrays["z"])),
        "adjusted_intervals": activity(np.concatenate(adjusted)),
    }
    return totals, strategy


def run_q3(scenario: str, eff: EfficiencyParameters, K: int, stages: tuple[int, ...]) -> dict[str, Any]:
    import q3_multistage as M

    M.set_efficiency(eff)
    t0 = time.perf_counter()
    rec, _ = M.backtest(0, M.ND, K=K, stages=stages, S0=6000.0, verbose=True)
    metrics, strategy = multistage_metrics(M, rec, M.DSTR.index("2025-02-01"))
    out = base_payload("q3", scenario, eff, time.perf_counter() - t0)
    out.update(metrics=metrics, strategy=strategy, solver={"scenarios_K": K, "stages": list(stages)})
    return out


def run_q4_2(scenario: str, eff: EfficiencyParameters) -> dict[str, Any]:
    import q2_solver as B
    import q4_q2_solver as M2
    import q4_solver as M

    cfg = replace(B.Config(), eta_charge=eff.eta_charge, eta_discharge=eff.eta_discharge)
    t0 = time.perf_counter()
    rec, data = M2.backtest(DATA, cfg=cfg)
    start = M.DSTR.index("2025-02-01")
    totals = {k: 0.0 for k in ("total_purchase_cost_yuan", "planned_purchase_cost_yuan",
                               "adjustment_cost_yuan", "emergency_cost_yuan", "planned_purchase_kwh",
                               "emergency_purchase_kwh", "charge_kwh", "discharge_kwh", "curtail_kwh")}
    arrays = {k: [] for k in ("c", "g", "z", "w")}
    for d in sorted(rec):
        if d < start:
            continue
        r, n, p = rec[d], rec[d]["natural"], data["price4_natural"][d]
        totals["planned_purchase_cost_yuan"] += float(p @ r["natural_x"])
        totals["emergency_cost_yuan"] += float(5.0 * p @ n["z"])
        totals["planned_purchase_kwh"] += float(r["natural_x"].sum())
        totals["emergency_purchase_kwh"] += float(n["z"].sum())
        totals["charge_kwh"] += float(n["c"].sum())
        totals["discharge_kwh"] += float(n["g"].sum())
        totals["curtail_kwh"] += float(n["w"].sum())
        for key in arrays:
            arrays[key].append(n[key])
    totals["total_purchase_cost_yuan"] = totals["planned_purchase_cost_yuan"] + totals["emergency_cost_yuan"]
    totals["total_purchase_kwh"] = totals["planned_purchase_kwh"] + totals["emergency_purchase_kwh"]
    strategy = {"charge_intervals": activity(np.concatenate(arrays["c"])),
                "discharge_intervals": activity(np.concatenate(arrays["g"])),
                "curtail_intervals": activity(np.concatenate(arrays["w"])),
                "emergency_intervals": activity(np.concatenate(arrays["z"])), "adjusted_intervals": 0}
    out = base_payload("q4-2", scenario, eff, time.perf_counter() - t0)
    out.update(metrics=totals, strategy=strategy)
    return out


def run_q4_3(scenario: str, eff: EfficiencyParameters, K: int) -> dict[str, Any]:
    import q4_solver as M

    M.set_efficiency(eff)
    t0 = time.perf_counter()
    rec, _ = M.backtest4(0, M.ND, K=K, stages=(0, 1, 2, 3), S0=6000.0, verbose=True)
    metrics, strategy = multistage_metrics(M, rec, M.DSTR.index("2025-02-01"), q4=True)
    out = base_payload("q4-3", scenario, eff, time.perf_counter() - t0)
    out.update(metrics=metrics, strategy=strategy, solver={"scenarios_K": K, "stages": [0, 1, 2, 3]})
    return out


RUNNERS = {"q1": run_q1, "q2": run_q2, "q4-2": run_q4_2}


def parse_efficiency(value: str) -> tuple[str, EfficiencyParameters]:
    if value in EFFICIENCY_SCENARIOS:
        return value, EFFICIENCY_SCENARIOS[value]
    rte = float(value)
    return f"rte_{rte:.6f}", EfficiencyParameters.symmetric_roundtrip(rte)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("question", choices=("q1", "q2", "q3", "q4-2", "q4-3"))
    parser.add_argument("scenario", help="roundtrip90, oneway90, or a symmetric round-trip efficiency")
    parser.add_argument("--K", type=int, default=30)
    parser.add_argument("--stages", default="0,1,2,3", help="Q3 enabled release stages")
    args = parser.parse_args()
    scenario, eff = parse_efficiency(args.scenario)
    stages = tuple(int(x) for x in args.stages.split(","))
    if args.question == "q3":
        result = run_q3(scenario, eff, args.K, stages)
    elif args.question == "q4-3":
        result = run_q4_3(scenario, eff, args.K)
    else:
        result = RUNNERS[args.question](scenario, eff)
    OUT.mkdir(parents=True, exist_ok=True)
    suffix = f"_stages{''.join(map(str, stages))}" if args.question == "q3" else ""
    path = OUT / f"{args.question}_{scenario}{suffix}.json"
    path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, indent=2))
    print(f"-> {path}")


if __name__ == "__main__":
    main()
