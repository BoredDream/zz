"""运行 src/q4_solver.py 的全年回测并落盘，供生成 result4-2.xlsx / result4-3.xlsx 与报告使用。

不修改模型代码，只调用其 backtest4()/settle_parts4()。
时间口径：模板行（第 t 个时段覆盖 [(t+1)*10, (t+2)*10) 分钟）。
储能口径：充/放电量均为交流母线侧。结算口径：按当日【实际】电价。

用法： python scripts/export_q4.py <2|3> [K] [stages]     默认 30 与 0,1,2,3
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

import q4_solver as M  # noqa: E402
import q4_q2_solver as Q2M  # noqa: E402

OUT = ROOT / "outputs" / "q4"
OUT.mkdir(parents=True, exist_ok=True)
DELIVERY_START = "2025-02-01"


if __name__ == "__main__":
    which = sys.argv[1] if len(sys.argv) > 1 else "3"
    K = int(sys.argv[2]) if len(sys.argv) > 2 else 30
    default_stages = "0" if which == "2" else "0,1,2,3"
    stages = tuple(int(x) for x in (sys.argv[3] if len(sys.argv) > 3 else default_stages).split(","))

    t0 = time.perf_counter()
    if which == "2":
        rec, q2data = Q2M.backtest(ROOT / "problem" / "data")
    else:
        rec, _ = M.backtest4(0, M.ND, K=K, stages=stages, S0=6000.0, verbose=True)
    elapsed = time.perf_counter() - t0

    days = sorted(rec)
    payload = {k: np.stack([rec[d][k] for d in days]) for k in ("x", "q")}
    for k in ("c","g","z","w","S"):
        payload[k] = np.stack([rec[d]["natural"][k] for d in days])
    payload["natural_x"] = np.stack([rec[d]["natural_x"] for d in days])
    payload["natural_q"] = np.stack([rec[d]["natural_q"] for d in days])
    payload["S0"] = np.array([rec[d]["S0"] for d in days])
    payload["dates"] = np.array([M.DSTR[d] for d in days])
    payload["price"] = M.PMAT[days]
    np.savez_compressed(OUT / f"detail_q4-{which}_K{K}.npz", **payload)

    start = M.DSTR.index(DELIVERY_START)
    out_days, totals = [], {k: 0.0 for k in
                            ("total_cost_yuan", "plan_cost_yuan", "adjust_cost_yuan", "emergency_cost_yuan",
                             "emergency_kwh", "charge_kwh", "discharge_kwh", "curtail_kwh",
                             "adjust_up_kwh", "adjust_down_kwh")}
    for i in range(start, len(days)):
        d = days[i]
        r = rec[d]
        n=r["natural"]
        if which == "2":
            pnat=q2data["price4_natural"][d]
            s_plan=pnat*r["natural_x"]; s_adjust=np.zeros(M.T); s_emg=5.0*pnat*n["z"]
            template_plan=M.PMAT[d]*r["x"]; template_adjust=np.zeros(M.T)
        else:
            s_plan,s_adjust,s_emg=M.natural_settle_parts4(d,r["natural_x"],r["natural_q"],n["z"])
            template_plan,template_adjust,_=M.settle_parts4(d,r["x"],r["q"],np.zeros(M.T))
        total=float(s_plan.sum()+s_adjust.sum()+s_emg.sum())
        residual = abs(float(total - (s_plan.sum() + s_adjust.sum() + s_emg.sum())))
        assert residual < 1e-6, f"{M.DSTR[d]} 费用拆分与总费用不一致：{residual:.3e}"
        up = float(np.maximum(r["natural_q"] - r["natural_x"], 0).sum())
        dn = float(np.maximum(r["natural_x"] - r["natural_q"], 0).sum())
        out_days.append({
            "date": M.DSTR[d],
            "plan_kwh": [float(v) for v in r["x"]],
            "plan_total_kwh": float(r["x"].sum()),
            "plan_cost_yuan": float(template_plan.sum()),
            "adjusted_kwh": [float(v) for v in r["q"]],
            "adjusted_total_kwh": float(r["q"].sum()),
            "adjusted_cost_yuan": float(template_adjust.sum()),
            "storage_blocks": M.storage_blocks(n["c"], n["g"]),
            "soc_start_kwh": float(r["S0"]),
            "soc_end_kwh": float(r["S24"]),
            "emergency_segments": M.natural_emergency_segments(n["z"]),
            "emergency_total_kwh": float(n["z"].sum()),
            "emergency_cost_yuan": float(s_emg.sum()),
            "total_cost_yuan": float(total),
            "natural_day_plan_cost_yuan": float(s_plan.sum()),
            "natural_day_adjust_cost_yuan": float(s_adjust.sum()),
            "adjust_up_kwh": up, "adjust_down_kwh": dn,
            "curtail_kwh": float(n["w"].sum()),
        })
        for k, v in (("total_cost_yuan", total), ("plan_cost_yuan", s_plan.sum()),
                     ("adjust_cost_yuan", s_adjust.sum()), ("emergency_cost_yuan", s_emg.sum()),
                     ("emergency_kwh", n["z"].sum()), ("charge_kwh", n["c"].sum()),
                     ("discharge_kwh", n["g"].sum()), ("curtail_kwh", n["w"].sum()),
                     ("adjust_up_kwh", up), ("adjust_down_kwh", dn)):
            totals[k] += float(v)

    meta = {"model": "q4_fluctuating_price_two_stage_saa", "variant": which,
            "storage_convention": "bus_side_charge_and_discharge",
            "soc_recursion": "S[t] = S[t-1] + eta_charge*c[t] - g[t]/eta_discharge",
            "plan_adjust_time_frame": "template_row_00:10_to_next_00:10",
            "physical_reporting_time_frame": "natural_day_00:00_to_24:00",
            "settlement_price": "actual_price_附件4",
            "scenarios_K": K, "stages": list(stages), "elapsed_seconds": elapsed,
            "eta": M.ETA_CHARGE, "eta_charge": M.ETA_CHARGE,
            "eta_discharge": M.ETA_DISCHARGE,
            "roundtrip_efficiency": M.ETA_CHARGE * M.ETA_DISCHARGE,
            "interval_limit_kwh": M.CMAX,
            "delivery_period": {"start": DELIVERY_START+"T00:00", "end": "2026-01-01T00:00", "days": len(out_days)},
            "variant2_base_model": "q2_solver" if which == "2" else None,
            "cold_start": q2data["q4_cold_price_source"] if which == "2" else
                          "首段已锁定购电量为0；附件2缺失的1月1日午夜负荷/光伏和无附件4历史时的价格先验显式取附件1；1月仅作预热",
            "totals": totals}
    (OUT / f"payload_q4-{which}_K{K}.json").write_text(
        json.dumps({"meta": meta, "days": out_days}, ensure_ascii=False), encoding="utf-8")
    (OUT / f"summary_q4-{which}_K{K}.json").write_text(
        json.dumps({"meta": meta, "totals": totals,
                    "daily": [{k: v for k, v in day.items()
                               if k not in ("plan_kwh", "adjusted_kwh", "storage_blocks", "emergency_segments")}
                              for day in out_days]}, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"variant": which, "elapsed_seconds": round(elapsed, 1),
                      **{k: round(v, 2) for k, v in totals.items()}}, ensure_ascii=False, indent=2))
    print(f"-> {OUT}")
