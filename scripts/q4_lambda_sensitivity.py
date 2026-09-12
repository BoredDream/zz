"""第四问终端储能价值 λ 的全年敏感性扫描。

背景与动机
----------
第四问按**附件4 实际电价**结算（`q4_solver.PMAT`，全年区间 0.0076—1.7936 元/kWh），
但两个变体的终端储能水价 `λ` **都取自附件1**：

* 变体 4-3（`src/q4_solver.py:316,326`，`lam = LAM`）：`LAM = 0.478 = p_谷/η`，
  其中 `p_谷 = 0.4302` 是附件1 的谷价；
* 变体 4-2（`src/q4_q2_solver.py:90`）：`terminal = η × min(附件1 自然日电价)`
  = 0.9 × 0.3713 = **0.33417**，注释写明「与Q2完全相同的终端水价，保证 Q2 vs 4-2
  只改变价格过程」。

也就是说，两个变体都在用**附件1 的价格水平**给附件4 的储能量定价，
而附件4 的价格区间比附件1（0.3713—1.3952）宽得多。λ 是外生常数、不由最优性导出，
所以必须回答「换一个 λ，第四问的答案变多少」。

做法
----
**不修改 `src/`**，只替换模块命名空间里的名字：

* 4-3：`q4_solver.LAM` 是 `solve_day4` 在运行时读取的模块全局量，直接赋值即可；
* 4-2：`terminal` 是 `backtest` 内的局部变量，无法直接改；但 `backtest` 以模块全局
  名字调用 `solve_saa(...)`，故替换 `q4_q2_solver.solve_saa` 为「忽略传入的 terminal、
  改用扫描值」的包装函数即可。注意**不能**改用 `cfg.eta_discharge`，因为它同时是
  SOC 递推里的效率（`src/q4_q2_solver.py:68`）。

每个变体按它自己的基准 λ₀ 取 0/0.5/0.75/1/1.5/2/3 倍共 7 点。

用法
----
    python scripts/q4_lambda_sensitivity.py run <2|3> <λ>   # 跑一个点
    python scripts/q4_lambda_sensitivity.py assemble        # 汇总

基准点（1×）应与已交付的 `summary_q4-<v>_K30.json` 逐位相同，`assemble` 会检查。
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

import q4_solver as M3  # noqa: E402
import q4_q2_solver as M2  # noqa: E402

OUT = ROOT / "outputs" / "q4"
SCAN = OUT / "lambda_scan"
SCAN.mkdir(parents=True, exist_ok=True)
DELIVERY_START = "2025-02-01"
K_DEFAULT = 30
TOL_BASELINE = 1e-6

# 各变体自己的基准 λ（见模块 docstring 的推导）。
BASE_LAM = {"2": 0.9 * 0.3713, "3": 0.478}
STAGE_TAG = {"2": "0", "3": "0,1,2,3"}


# 未打补丁的原始名字，用于在同一个进程内跑多个 λ 时还原（避免包装函数层层套娃）。
_ORIG_SOLVE_SAA = M2.solve_saa
_ORIG_LAM3 = M3.LAM


def patch(variant: str, lam: float) -> None:
    """把该变体的终端水价换成 lam，其余一字不动。"""
    if variant == "3":
        M3.LAM = float(lam)
        return
    orig = _ORIG_SOLVE_SAA

    def solve_saa(scenarios, price145, committed_grid, initial_soc, terminal_value, cfg):
        return orig(scenarios, price145, committed_grid, initial_soc, float(lam), cfg)

    M2.solve_saa = solve_saa


def run_one(variant: str, lam: float, K: int = K_DEFAULT) -> dict:
    # 每个进程只跑一个点，但同一进程内多次调用时先还原再打补丁。
    M2.solve_saa = _ORIG_SOLVE_SAA
    M3.LAM = _ORIG_LAM3
    patch(variant, lam)
    assert M3.LAM == (float(lam) if variant == "3" else _ORIG_LAM3)

    t0 = time.perf_counter()
    if variant == "2":
        rec, data = M2.backtest(ROOT / "problem" / "data")
    else:
        stages = tuple(int(x) for x in STAGE_TAG["3"].split(","))
        rec, _ = M3.backtest4(0, M3.ND, K=K, stages=stages, S0=6000.0, verbose=False)
    elapsed = time.perf_counter() - t0

    days = sorted(rec)
    start = M3.DSTR.index(DELIVERY_START)
    keys = ("total_cost_yuan", "plan_cost_yuan", "adjust_cost_yuan", "emergency_cost_yuan",
            "emergency_kwh", "charge_kwh", "discharge_kwh", "curtail_kwh",
            "adjust_up_kwh", "adjust_down_kwh")
    totals = {k: 0.0 for k in keys}
    soc_end_daily, soc_min_hits, soc_max_hits = [], 0, 0
    for i in range(start, len(days)):
        d = days[i]
        r = rec[d]
        n = r["natural"]
        if variant == "2":
            pnat = data["price4_natural"][d]
            s_plan = pnat * r["natural_x"]
            s_adjust = np.zeros(M3.T)
            s_emg = 5.0 * pnat * n["z"]
        else:
            s_plan, s_adjust, s_emg = M3.natural_settle_parts4(
                d, r["natural_x"], r["natural_q"], n["z"])
        total = float(s_plan.sum() + s_adjust.sum() + s_emg.sum())
        for k, v in (("total_cost_yuan", total), ("plan_cost_yuan", s_plan.sum()),
                     ("adjust_cost_yuan", s_adjust.sum()), ("emergency_cost_yuan", s_emg.sum()),
                     ("emergency_kwh", n["z"].sum()), ("charge_kwh", n["c"].sum()),
                     ("discharge_kwh", n["g"].sum()), ("curtail_kwh", n["w"].sum()),
                     ("adjust_up_kwh", float(np.maximum(r["natural_q"] - r["natural_x"], 0).sum())),
                     ("adjust_down_kwh", float(np.maximum(r["natural_x"] - r["natural_q"], 0).sum()))):
            totals[k] += float(v)
        soc_end_daily.append(float(r["S24"]))
        S = np.r_[r["S0"], n["S"]]
        soc_min_hits += int((S <= M3.SMIN + 1e-6).sum())
        soc_max_hits += int((S >= M3.SMAX - 1e-6).sum())

    soc_start_delivery = float(rec[days[start]]["S0"])
    return {
        "variant": variant,
        "lam": float(lam),
        "lam_over_baseline": float(lam / BASE_LAM[variant]),
        "baseline_lam": BASE_LAM[variant],
        "lam_source": "附件1 谷价/η（4-3）" if variant == "3"
                      else "η × min(附件1 自然日电价)（4-2，继承 Q2）",
        "price_process_range_yuan_per_kwh": [float(M3.PMAT.min()), float(M3.PMAT.max())],
        "attachment1_price_range_yuan_per_kwh": [0.3713, 1.3952],
        "K": K, "stages": STAGE_TAG[variant],
        "delivery_start": DELIVERY_START, "delivery_end": M3.DSTR[days[-1]],
        "delivery_days": len(days) - start,
        "elapsed_seconds": elapsed,
        "totals": totals,
        "soc_start_delivery_kwh": soc_start_delivery,
        "soc_end_delivery_kwh": soc_end_daily[-1],
        "soc_net_change_kwh": soc_end_daily[-1] - soc_start_delivery,
        "soc_end_mean_daily_kwh": float(np.mean(soc_end_daily)),
        "soc_band_hits_delivery": {"at_min": soc_min_hits, "at_max": soc_max_hits},
    }


def tag_of(lam: float) -> str:
    # 用 %.10g 而非 %g（后者只有 6 位有效数字，会把 0.2506275 截成 0.250628）。
    return "lam" + ("%.10g" % lam).replace("-", "m").replace(".", "p")


def cmd_run(variant: str, lam: float, K: int = K_DEFAULT) -> int:
    res = run_one(variant, lam, K=K)
    p = SCAN / ("q4-%s_%s_K%d.json" % (variant, tag_of(lam), K))
    p.write_text(json.dumps(res, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"variant": variant, "lam": res["lam"],
                      "total_cost_yuan": round(res["totals"]["total_cost_yuan"], 4),
                      "elapsed_seconds": round(res["elapsed_seconds"], 1)},
                     ensure_ascii=False, indent=2))
    print("-> %s" % p)
    return 0


def cmd_assemble(K: int = K_DEFAULT) -> int:
    out = {"meta": {"purpose": "第四问终端储能价值 λ 的全年敏感性扫描",
                    "model": {"2": "src/q4_q2_solver.py", "3": "src/q4_solver.py"},
                    "settlement_price": "附件4 实际电价",
                    "K": K, "S0": 6000.0, "baseline_lam": BASE_LAM},
           "variants": {}}
    bad = False
    for variant in ("2", "3"):
        files = sorted(SCAN.glob("q4-%s_lam*_K%d.json" % (variant, K)))
        if not files:
            continue
        pts = sorted((json.loads(f.read_text(encoding="utf-8")) for f in files),
                     key=lambda r: r["lam"])
        base = next((r for r in pts if abs(r["lam"] - BASE_LAM[variant]) < 1e-12), None)

        chk = {"baseline_lam": BASE_LAM[variant], "rerun_matches_delivered": None,
               "delivered_total_cost_yuan": None, "rerun_total_cost_yuan": None,
               "abs_gap_yuan": None}
        ref = OUT / ("summary_q4-%s_K%d.json" % (variant, K))
        if base is not None and ref.exists():
            delivered = float(json.loads(ref.read_text(encoding="utf-8"))["totals"]["total_cost_yuan"])
            gap = abs(base["totals"]["total_cost_yuan"] - delivered)
            chk.update({"delivered_total_cost_yuan": delivered,
                        "rerun_total_cost_yuan": base["totals"]["total_cost_yuan"],
                        "abs_gap_yuan": gap,
                        "rerun_matches_delivered": bool(gap < TOL_BASELINE)})
            bad = bad or not chk["rerun_matches_delivered"]

        costs = [r["totals"]["total_cost_yuan"] for r in pts]
        bref = (base or pts[0])["totals"]["total_cost_yuan"]
        lo = min(pts, key=lambda r: r["totals"]["total_cost_yuan"])
        hi = max(pts, key=lambda r: r["totals"]["total_cost_yuan"])
        out["variants"][variant] = {
            "baseline_reproduction_check": chk,
            "scan": [{"lam": r["lam"], "lam_over_baseline": r["lam_over_baseline"],
                      "total_cost_yuan": r["totals"]["total_cost_yuan"],
                      "delta_vs_baseline_yuan": r["totals"]["total_cost_yuan"] - bref,
                      "delta_pct": (r["totals"]["total_cost_yuan"] / bref - 1.0) * 100.0,
                      "emergency_kwh": r["totals"]["emergency_kwh"],
                      "emergency_cost_yuan": r["totals"]["emergency_cost_yuan"],
                      "charge_kwh": r["totals"]["charge_kwh"],
                      "discharge_kwh": r["totals"]["discharge_kwh"],
                      "curtail_kwh": r["totals"]["curtail_kwh"],
                      "soc_start_delivery_kwh": r["soc_start_delivery_kwh"],
                      "soc_end_delivery_kwh": r["soc_end_delivery_kwh"],
                      "soc_end_mean_daily_kwh": r["soc_end_mean_daily_kwh"],
                      "soc_band_hits_delivery": r["soc_band_hits_delivery"]} for r in pts],
            "range": {
                "min_cost": {"lam": lo["lam"], "total_cost_yuan": lo["totals"]["total_cost_yuan"]},
                "max_cost": {"lam": hi["lam"], "total_cost_yuan": hi["totals"]["total_cost_yuan"]},
                "spread_yuan": hi["totals"]["total_cost_yuan"] - lo["totals"]["total_cost_yuan"],
                "spread_pct_of_baseline": (hi["totals"]["total_cost_yuan"]
                                           - lo["totals"]["total_cost_yuan"]) / bref * 100.0,
                "costs_monotone_in_lam": bool(all(np.diff(costs) >= -1e-6)
                                              or all(np.diff(costs) <= 1e-6)),
            },
            "points": len(pts), "point_files": [f.name for f in files],
        }
    if not out["variants"]:
        print("没有找到任何单点结果，先跑 run。")
        return 1
    p = OUT / ("lambda_sensitivity_q4_K%d.json" % K)
    p.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    for variant, v in out["variants"].items():
        print("4-%s: %s" % (variant, json.dumps(v["range"], ensure_ascii=False)))
        print("      baseline check: %s" % json.dumps(v["baseline_reproduction_check"],
                                                      ensure_ascii=False))
    print("-> %s" % p)
    return 1 if bad else 0


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "assemble"
    if cmd == "run":
        if len(sys.argv) < 4:
            print(__doc__)
            sys.exit(2)
        sys.exit(cmd_run(sys.argv[2], float(sys.argv[3]),
                         K=int(sys.argv[4]) if len(sys.argv) > 4 else K_DEFAULT))
    elif cmd == "assemble":
        sys.exit(cmd_assemble(K=int(sys.argv[2]) if len(sys.argv) > 2 else K_DEFAULT))
    else:
        print(__doc__)
        sys.exit(2)
