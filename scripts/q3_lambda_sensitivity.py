"""第三问终端储能价值 λ 的全年敏感性扫描。

背景
----
`src/q3_multistage.py` 里 `LAM = 0.478 = p_谷/η`（谷价 0.4302 元/kWh ÷ η=0.9），
作为**每个阶段 LP 视界末端**的储能水价（`stage_lp` 与 `stage0_lp_145` 目标函数里
最后一时段的 `-lam/K`）。因为阶段每天滚动，它实际是**逐日**的末端水价：
每天都会用它给「当天结束时剩下的电」定价，故它会影响全部 334 天，而不只是年末。

λ 是外生常数、不是由最优性推导出来的，所以必须做敏感性扫描。

做法
----
**不修改 `src/`**：只替换模块命名空间里的 `stage_lp` / `stage0_lp_145` 两个名字
（与 `q3_solver_uniqueness_check.py` 替换 `linprog` 同一手法），把 `lam` 默认值
换成扫描值，其余参数（`alpha`、`commit_end`）原样透传。

用法
----
    python scripts/q3_lambda_sensitivity.py run 0.478      # 跑一个 λ，写一份 JSON
    python scripts/q3_lambda_sensitivity.py assemble       # 汇总 -> lambda_sensitivity.json

`run` 每次只跑一个 λ，便于多进程并行；`assemble` 只读已落盘的单点结果。
参照点：λ = 0.478 的那一次应当**逐位复现** `summary_stages0123_K30.json`，
否则说明补丁机制本身改变了模型，扫描结果不可用（脚本会检查并报错）。
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
SCAN = OUT / "lambda_scan"
SCAN.mkdir(parents=True, exist_ok=True)
DELIVERY_START = "2025-02-01"
BASELINE_LAM = 0.478          # = M.LAM，主答案所用值
TOL_BASELINE = 1e-6           # 与已交付 summary 的逐位一致性容差(元)


def tag_of(lam: float) -> str:
    return "lam" + ("%g" % lam).replace("-", "m").replace(".", "p")


def patch_lambda(lam: float) -> None:
    """把两个 LP 入口的 lam 默认值换成 lam，其余原样透传。"""
    orig_stage = M.stage_lp
    orig_stage0 = M.stage0_lp_145

    def stage_lp(m, x_ref, S_cur, scenL, scenG, alpha=M.ALPHA, lam=lam, commit_end=None):
        return orig_stage(m, x_ref, S_cur, scenL, scenG, alpha, lam, commit_end)

    def stage0_lp_145(committed_q, S_cur, scenL, scenG, alpha=M.ALPHA, lam=lam, commit_end=None):
        return orig_stage0(committed_q, S_cur, scenL, scenG, alpha, lam, commit_end)

    M.stage_lp = stage_lp
    M.stage0_lp_145 = stage0_lp_145


def run_one(lam: float, K: int = 30, stages: tuple[int, ...] = (0, 1, 2, 3)) -> dict:
    patch_lambda(lam)
    t0 = time.perf_counter()
    rec, _ = M.backtest(0, M.ND, K=K, stages=stages, S0=6000.0, verbose=False)
    elapsed = time.perf_counter() - t0

    days = sorted(rec)
    start = M.DSTR.index(DELIVERY_START)
    keys = ("total_cost_yuan", "plan_cost_yuan", "adjust_cost_yuan", "emergency_cost_yuan",
            "emergency_kwh", "charge_kwh", "discharge_kwh", "curtail_kwh",
            "adjust_up_kwh", "adjust_down_kwh")
    totals = {k: 0.0 for k in keys}
    soc_end_daily, daily_cost, soc_min_hits, soc_max_hits = [], [], 0, 0
    for i in range(start, len(days)):
        r = rec[days[i]]
        n = r["natural"]
        s_plan, s_adjust, s_emg = M.natural_settle_parts(r["natural_x"], r["natural_q"], n["z"])
        total = float(s_plan.sum() + s_adjust.sum() + s_emg.sum())
        for k, v in (("total_cost_yuan", total), ("plan_cost_yuan", s_plan.sum()),
                     ("adjust_cost_yuan", s_adjust.sum()), ("emergency_cost_yuan", s_emg.sum()),
                     ("emergency_kwh", n["z"].sum()), ("charge_kwh", n["c"].sum()),
                     ("discharge_kwh", n["g"].sum()), ("curtail_kwh", n["w"].sum()),
                     ("adjust_up_kwh", float(np.maximum(r["natural_q"] - r["natural_x"], 0).sum())),
                     ("adjust_down_kwh", float(np.maximum(r["natural_x"] - r["natural_q"], 0).sum()))):
            totals[k] += float(v)
        soc_end_daily.append(float(r["S24"]))
        daily_cost.append(total)
        S = np.r_[r["S0"], r["natural"]["S"]]
        soc_min_hits += int((S <= M.SMIN + 1e-6).sum())
        soc_max_hits += int((S >= M.SMAX - 1e-6).sum())

    delivery_days = len(days) - start
    # 交付期期初 SOC = 交付期第一天开始时的储电量（= 前一日 24:00）。
    # 现金费用只结算购电与紧急购电，不结算储能存量，故跨 λ 比较费用时必须
    # 同时看期末存量：`cost_net_of_storage_change` 把交付期内储能净变化按 λ 计价扣回，
    # 才是「服务这 334 天负荷的真实代价」。λ=0 时该项等于现金费用。
    soc_start_delivery = float(rec[days[start]]["S0"])
    soc_snap = soc_end_daily[-1] - soc_start_delivery
    return {
        "lam": float(lam),
        "lam_over_baseline": float(lam / BASELINE_LAM),
        "p_valley_yuan_per_kwh": 0.4302,
        "p_valley_over_eta": float(0.4302 / M.ETA),
        "price_min_yuan_per_kwh": float(M.P.min()),
        "price_mean_yuan_per_kwh": float(M.P.mean()),
        "price_max_yuan_per_kwh": float(M.P.max()),
        "K": K, "stages": list(stages),
        "delivery_start": DELIVERY_START, "delivery_end": M.DSTR[days[-1]],
        "delivery_days": delivery_days,
        "elapsed_seconds": elapsed,
        "totals": totals,
        "soc_start_delivery_kwh": soc_start_delivery,
        "soc_end_delivery_kwh": soc_end_daily[-1],
        "soc_net_change_kwh": soc_snap,
        "soc_net_change_value_yuan": float(lam * soc_snap),
        "cost_net_of_storage_change_yuan": float(totals["total_cost_yuan"] - lam * soc_snap),
        "soc_end_mean_daily_kwh": float(np.mean(soc_end_daily)),
        "soc_end_min_daily_kwh": float(np.min(soc_end_daily)),
        "soc_end_max_daily_kwh": float(np.max(soc_end_daily)),
        "soc_band_hits_delivery": {"at_min": soc_min_hits, "at_max": soc_max_hits},
        "daily": [{"date": M.DSTR[days[i]], "total_cost_yuan": daily_cost[i - start],
                   "soc_end_kwh": soc_end_daily[i - start]}
                  for i in range(start, len(days))],
    }


def cmd_run(lam: float, K: int = 30) -> int:
    res = run_one(lam, K=K)
    p = SCAN / (tag_of(lam) + "_K%d.json" % K)
    p.write_text(json.dumps(res, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"lam": res["lam"], "total_cost_yuan": round(res["totals"]["total_cost_yuan"], 4),
                      "elapsed_seconds": round(res["elapsed_seconds"], 1)},
                     ensure_ascii=False, indent=2))
    print("-> %s" % p)
    return 0


def cmd_assemble(K: int = 30) -> int:
    files = sorted(SCAN.glob("lam*_K%d.json" % K))
    if not files:
        print("没有找到任何单点结果，先跑 run。")
        return 1
    pts = [json.loads(f.read_text(encoding="utf-8")) for f in files]
    pts.sort(key=lambda r: r["lam"])

    base = next((r for r in pts if abs(r["lam"] - BASELINE_LAM) < 1e-12), None)
    check = {"baseline_lam": BASELINE_LAM, "rerun_matches_delivered": None,
             "delivered_total_cost_yuan": None, "rerun_total_cost_yuan": None, "abs_gap_yuan": None}
    ref = OUT / "summary_stages0123_K30.json"
    if base is not None and ref.exists():
        delivered = float(json.loads(ref.read_text(encoding="utf-8"))["totals"]["total_cost_yuan"])
        gap = abs(base["totals"]["total_cost_yuan"] - delivered)
        check.update({"delivered_total_cost_yuan": delivered,
                      "rerun_total_cost_yuan": base["totals"]["total_cost_yuan"],
                      "abs_gap_yuan": gap,
                      "rerun_matches_delivered": bool(gap < TOL_BASELINE)})

    costs = [r["totals"]["total_cost_yuan"] for r in pts]
    nets = [r["cost_net_of_storage_change_yuan"] for r in pts]
    lo, hi = min(pts, key=lambda r: r["totals"]["total_cost_yuan"]), \
        max(pts, key=lambda r: r["totals"]["total_cost_yuan"])
    nlo, nhi = min(pts, key=lambda r: r["cost_net_of_storage_change_yuan"]), \
        max(pts, key=lambda r: r["cost_net_of_storage_change_yuan"])
    summary = {
        "meta": {
            "purpose": "第三问终端储能价值 lambda 的全年敏感性扫描",
            "model": "src/q3_multistage.py",
            "method": "替换模块命名空间里 stage_lp/stage0_lp_145 的 lam 默认值；src/ 未改动",
            "K": K, "stages": [0, 1, 2, 3], "S0": 6000.0,
            "delivery_period": pts[0]["delivery_start"] + " 至 " + pts[0]["delivery_end"],
            "delivery_days": pts[0]["delivery_days"],
            "baseline_lam": BASELINE_LAM,
            "reference_values": {
                "p_valley_over_eta": pts[0]["p_valley_over_eta"],
                "price_min": pts[0]["price_min_yuan_per_kwh"],
                "price_mean": pts[0]["price_mean_yuan_per_kwh"],
                "price_max": pts[0]["price_max_yuan_per_kwh"],
            },
            "points": len(pts),
            "point_files": [f.name for f in files],
        },
        "baseline_reproduction_check": check,
        "scan": [
            {"lam": r["lam"], "lam_over_baseline": r["lam_over_baseline"],
             "total_cost_yuan": r["totals"]["total_cost_yuan"],
             "delta_vs_baseline_yuan": r["totals"]["total_cost_yuan"] - base["totals"]["total_cost_yuan"]
             if base is not None else None,
             "delta_pct": (r["totals"]["total_cost_yuan"] / base["totals"]["total_cost_yuan"] - 1.0) * 100.0
             if base is not None else None,
             "emergency_kwh": r["totals"]["emergency_kwh"],
             "emergency_cost_yuan": r["totals"]["emergency_cost_yuan"],
             "charge_kwh": r["totals"]["charge_kwh"],
             "discharge_kwh": r["totals"]["discharge_kwh"],
             "curtail_kwh": r["totals"]["curtail_kwh"],
             "soc_start_delivery_kwh": r["soc_start_delivery_kwh"],
             "soc_end_delivery_kwh": r["soc_end_delivery_kwh"],
             "soc_net_change_kwh": r["soc_net_change_kwh"],
             "cost_net_of_storage_change_yuan": r["cost_net_of_storage_change_yuan"],
             "delta_net_vs_baseline_yuan": r["cost_net_of_storage_change_yuan"]
             - base["cost_net_of_storage_change_yuan"] if base is not None else None,
             "soc_end_mean_daily_kwh": r["soc_end_mean_daily_kwh"],
             "soc_band_hits_delivery": r["soc_band_hits_delivery"]}
            for r in pts],
        "range": {
            "min_cost": {"lam": lo["lam"], "total_cost_yuan": lo["totals"]["total_cost_yuan"]},
            "max_cost": {"lam": hi["lam"], "total_cost_yuan": hi["totals"]["total_cost_yuan"]},
            "spread_yuan": hi["totals"]["total_cost_yuan"] - lo["totals"]["total_cost_yuan"],
            "spread_pct_of_baseline": (hi["totals"]["total_cost_yuan"] - lo["totals"]["total_cost_yuan"])
            / base["totals"]["total_cost_yuan"] * 100.0 if base is not None else None,
            "costs_monotone_in_lam": bool(all(np.diff(costs) >= -1e-6) or all(np.diff(costs) <= 1e-6)),
            "min_net_cost": {"lam": nlo["lam"], "cost_net_of_storage_change_yuan":
                             nlo["cost_net_of_storage_change_yuan"]},
            "max_net_cost": {"lam": nhi["lam"], "cost_net_of_storage_change_yuan":
                             nhi["cost_net_of_storage_change_yuan"]},
            "net_spread_yuan": nhi["cost_net_of_storage_change_yuan"]
            - nlo["cost_net_of_storage_change_yuan"],
            "net_spread_pct_of_baseline": ((nhi["cost_net_of_storage_change_yuan"]
                                            - nlo["cost_net_of_storage_change_yuan"])
                                           / base["cost_net_of_storage_change_yuan"] * 100.0)
            if base is not None else None,
            "nets_monotone_in_lam": bool(all(np.diff(nets) >= -1e-6) or all(np.diff(nets) <= 1e-6)),
        },
    }
    p = OUT / ("lambda_sensitivity_K%d.json" % K)
    p.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(summary["range"], ensure_ascii=False, indent=2))
    print("baseline_reproduction_check: %s" % json.dumps(check, ensure_ascii=False))
    print("-> %s" % p)
    return 0 if (check["rerun_matches_delivered"] is not False) else 1


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "assemble"
    if cmd == "run":
        if len(sys.argv) < 3:
            print(__doc__)
            sys.exit(2)
        sys.exit(cmd_run(float(sys.argv[2]), K=int(sys.argv[3]) if len(sys.argv) > 3 else 30))
    elif cmd == "assemble":
        sys.exit(cmd_assemble(K=int(sys.argv[2]) if len(sys.argv) > 2 else 30))
    else:
        print(__doc__)
        sys.exit(2)
