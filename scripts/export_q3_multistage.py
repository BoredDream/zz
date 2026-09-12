"""运行 src/q3_multistage.py 的全年回测并落盘，供生成 result3.xlsx 与报告使用。

不修改模型代码，只调用其 backtest()/settle_parts()。
时间口径：模板行（第 t 个时段覆盖 [(t+1)*10, (t+2)*10) 分钟），与附件5 模板列标签一致。
储能口径：充/放电量均为交流母线侧（README 固定口径 6）。

用法： python scripts/export_q3_multistage.py [K] [stages]     默认 30 与 0,1,2,3
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

import q3_multistage as M  # noqa: E402

OUT = ROOT / "outputs" / "q3_multistage"
OUT.mkdir(parents=True, exist_ok=True)
DELIVERY_START = "2025-02-01"


def storage_blocks(charge: np.ndarray, discharge: np.ndarray) -> list[dict[str, float | str]]:
    """模板行口径的六个 4 小时段：t=24k..24k+23 覆盖 [(24k+1)*10, (24k+25)*10) 分钟。"""
    return [{"time_range": "%s-%s" % (M.clock_min((24 * k + 1) * 10), M.clock_min((24 * k + 25) * 10)),
             "charge_kwh": float(charge[24 * k:24 * k + 24].sum()),
             "discharge_kwh": float(discharge[24 * k:24 * k + 24].sum())} for k in range(6)]


if __name__ == "__main__":
    K = int(sys.argv[1]) if len(sys.argv) > 1 else 30
    stages = tuple(int(x) for x in sys.argv[2].split(",")) if len(sys.argv) > 2 else (0, 1, 2, 3)
    tag = "".join(str(s) for s in stages)
    t0 = time.perf_counter()
    rec, _ = M.backtest(0, M.ND, K=K, stages=stages, S0=6000.0, verbose=True)
    elapsed = time.perf_counter() - t0

    days = sorted(rec)
    keys = ("x", "q", "z", "c", "g", "w", "S")
    payload = {k: np.stack([rec[d][k] for d in days]) for k in keys}
    payload["S0"] = np.array([rec[d]["S0"] for d in days])
    payload["dates"] = np.array([M.DSTR[d] for d in days])
    np.savez_compressed(OUT / f"detail_stages{tag}_K{K}.npz", **payload)

    start = M.DSTR.index(DELIVERY_START)
    out_days, totals = [], {k: 0.0 for k in
                            ("total_cost_yuan", "plan_cost_yuan", "adjust_cost_yuan", "emergency_cost_yuan",
                             "emergency_kwh", "charge_kwh", "discharge_kwh", "curtail_kwh",
                             "adjust_up_kwh", "adjust_down_kwh")}
    for i in range(start, len(days)):
        d = days[i]
        r = rec[d]
        s_plan, s_adjust, s_emg = M.settle_parts(r["x"], r["q"], r["z"])
        total = M.day_cost(r["x"], r["q"], r)[0]
        residual = abs(float(total - (s_plan.sum() + s_adjust.sum() + s_emg.sum())))
        assert residual < 1e-6, f"{M.DSTR[d]} 费用拆分与总费用不一致：{residual:.3e}"
        up = float(np.maximum(r["q"] - r["x"], 0).sum())
        dn = float(np.maximum(r["x"] - r["q"], 0).sum())
        out_days.append({
            "date": M.DSTR[d],
            "plan_kwh": [float(v) for v in r["x"]],
            "plan_total_kwh": float(r["x"].sum()),
            "plan_cost_yuan": float(s_plan.sum()),
            "adjusted_kwh": [float(v) for v in r["q"]],
            "adjusted_total_kwh": float(r["q"].sum()),
            "adjusted_cost_yuan": float(s_adjust.sum()),
            "storage_blocks": storage_blocks(r["c"], r["g"]),
            "soc_start_kwh": float(r["S0"]),
            "soc_end_kwh": float(r["S"][-1]),
            "emergency_segments": M.emergency_segments(r["z"]),
            "emergency_total_kwh": float(r["z"].sum()),
            "emergency_cost_yuan": float(s_emg.sum()),
            "total_cost_yuan": float(total),
            "adjust_up_kwh": up, "adjust_down_kwh": dn,
            "curtail_kwh": float(r["w"].sum()),
        })
        for k, v in (("total_cost_yuan", total), ("plan_cost_yuan", s_plan.sum()),
                     ("adjust_cost_yuan", s_adjust.sum()), ("emergency_cost_yuan", s_emg.sum()),
                     ("emergency_kwh", r["z"].sum()), ("charge_kwh", r["c"].sum()),
                     ("discharge_kwh", r["g"].sum()), ("curtail_kwh", r["w"].sum()),
                     ("adjust_up_kwh", up), ("adjust_down_kwh", dn)):
            totals[k] += float(v)

    meta = {"model": "multistage_rolling_SAA_scenario_branched_recourse",
            "storage_convention": "bus_side_charge_and_discharge",
            "soc_recursion": "S[t] = S[t-1] + eta*c[t] - g[t]/eta",
            "time_frame": "template_row", "scenarios_K": K, "stages": list(stages), "tag": tag,
            "elapsed_seconds": elapsed, "eta": M.ETA, "interval_limit_kwh": M.CMAX,
            "delivery_period": {"start": DELIVERY_START, "end": M.DSTR[days[-1]], "days": len(out_days)},
            "totals": totals}
    (OUT / f"payload_stages{tag}_K{K}.json").write_text(
        json.dumps({"meta": meta, "days": out_days}, ensure_ascii=False), encoding="utf-8")
    (OUT / f"summary_stages{tag}_K{K}.json").write_text(
        json.dumps({"meta": meta, "totals": totals,
                    "daily": [{k: v for k, v in day.items()
                               if k not in ("plan_kwh", "adjusted_kwh", "storage_blocks", "emergency_segments")}
                              for day in out_days]}, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"elapsed_seconds": round(elapsed, 1), **{k: round(v, 2) for k, v in totals.items()}},
                     ensure_ascii=False, indent=2))
    print(f"-> {OUT}")
