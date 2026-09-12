"""第三问：求解器退化与配置敏感性检验。

背景
----
`reports/project_task_reference.md`「最终状态定义」第 3 条要求「每个结果均能由明细
独立复算」，但现行第三问模型只有 `scripts/validate_q3_multistage.py`，它验证的是
「编码与已验收产物自洽」，**不是**独立复算，也没有最优解唯一性检验。旧模型曾实测：
目标函数一字不改、只换求解算法，年度总费用可差约 0.226%，且约 41.9% 的发布时刻
存在退化（多个最优解）。本脚本在**现行模型**上重做这两件事。

不修改被检验的代码
------------------
`src/q3_multistage.py` 里的调用是 `linprog(c, ..., method='highs')`——`method` 是
关键字参数。因此本脚本通过替换模块命名空间里的 `linprog` 名字来换算法，
`src/` 一字不改，主答案路径不受影响。

两个模式
--------
alt <method>
    整年回测改用 <method>（highs-ds 对偶单纯形 / highs-ipm 内点法），
    与已验收的 `summary_stages0123_K30.json` 比较 **334 天交付期总费用**与**逐日费用**。
    这直接回答「13,162,682.89 元是否依赖求解器配置」。

census
    抽样若干天，在**同一个 LP** 上用多种算法重解，比较最优值与最优解：
      * 最优值一致、最优解不同  => LP 退化（存在多个最优解，决策不唯一）；
      * 最优值本身不同          => 求解器配置敏感（更严重）。
    另加一组「目标系数微扰动」探针，作为退化的独立旁证。

用法
----
    python scripts/q3_solver_uniqueness_check.py alt highs-ds
    python scripts/q3_solver_uniqueness_check.py alt highs-ipm
    python scripts/q3_solver_uniqueness_check.py census [步长]
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
K = 30
STAGES = (0, 1, 2, 3)
DELIVERY_START = "2025-02-01"
PRIMARY = "highs"                     # 主答案所用的算法
ALT_METHODS = ("highs-ds", "highs-ipm")
JITTER = 1e-7                         # 目标系数相对扰动幅度

_real_linprog = M.linprog             # 保存真身，供 shim 调用


def _solve(c, kw: dict, method: str):
    """用指定算法解同一个 LP；丢掉模型传入的 method（本脚本要覆盖它）。"""
    kw = dict(kw)
    kw.pop("method", None)
    return _real_linprog(c, method=method, **kw)


def delivery_totals(rec: dict) -> tuple[dict, dict]:
    """按 scripts/export_q3_multistage.py 的同一口径算 334 天交付期合计与逐日费用。"""
    days = sorted(rec)
    start = M.DSTR.index(DELIVERY_START)
    totals = {k: 0.0 for k in ("total_cost_yuan", "plan_cost_yuan", "adjust_cost_yuan",
                               "emergency_cost_yuan", "emergency_kwh", "charge_kwh",
                               "discharge_kwh", "curtail_kwh", "adjust_up_kwh", "adjust_down_kwh")}
    daily: dict[str, float] = {}
    for d in days[start:]:
        r = rec[d]
        n = r["natural"]
        s_plan, s_adjust, s_emg = M.natural_settle_parts(r["natural_x"], r["natural_q"], n["z"])
        total = float(s_plan.sum() + s_adjust.sum() + s_emg.sum())
        daily[M.DSTR[d]] = total
        up = float(np.maximum(r["natural_q"] - r["natural_x"], 0).sum())
        dn = float(np.maximum(r["natural_x"] - r["natural_q"], 0).sum())
        for k, v in (("total_cost_yuan", total), ("plan_cost_yuan", s_plan.sum()),
                     ("adjust_cost_yuan", s_adjust.sum()), ("emergency_cost_yuan", s_emg.sum()),
                     ("emergency_kwh", n["z"].sum()), ("charge_kwh", n["c"].sum()),
                     ("discharge_kwh", n["g"].sum()), ("curtail_kwh", n["w"].sum()),
                     ("adjust_up_kwh", up), ("adjust_down_kwh", dn)):
            totals[k] += float(v)
    return totals, daily


def mode_alt(method: str) -> int:
    """整年回测改用 method，与已验收产物比较。"""
    stored = json.loads((OUT / f"summary_stages0123_K{K}.json").read_text(encoding="utf-8"))
    ref_totals = stored["totals"]
    ref_daily = {d["date"]: d["total_cost_yuan"] for d in
                 json.loads((OUT / f"payload_stages0123_K{K}.json").read_text(encoding="utf-8"))["days"]}

    M.linprog = lambda c, **kw: _solve(c, kw, method)      # noqa: E731
    t0 = time.perf_counter()
    try:
        rec, _ = M.backtest(0, M.ND, K=K, stages=STAGES, S0=6000.0, verbose=False)
    finally:
        M.linprog = _real_linprog
    elapsed = time.perf_counter() - t0

    totals, daily = delivery_totals(rec)
    ref_total = float(ref_totals["total_cost_yuan"])
    got_total = totals["total_cost_yuan"]
    day_gap = {d: daily[d] - ref_daily[d] for d in daily if d in ref_daily}
    worst_day = max(day_gap, key=lambda d: abs(day_gap[d]))
    result = {
        "mode": "alt", "method": method, "K": K, "stages": list(STAGES),
        "elapsed_seconds": elapsed,
        "reference_total_cost_yuan": ref_total,
        "alt_total_cost_yuan": got_total,
        "total_gap_yuan": got_total - ref_total,
        "total_gap_pct": 100.0 * (got_total - ref_total) / ref_total,
        "max_abs_daily_gap_yuan": abs(day_gap[worst_day]),
        "worst_day": worst_day,
        "days_with_gap_over_1yuan": sum(1 for v in day_gap.values() if abs(v) > 1.0),
        "delivery_days": len(daily),
        "alt_totals": totals,
    }
    (OUT / f"solver_sensitivity_{method}.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({k: v for k, v in result.items() if k != "alt_totals"},
                     ensure_ascii=False, indent=2))
    return 0


def mode_census(step: int = 8) -> int:
    """抽样若干天，在同一 LP 上多算法重解，统计退化与配置敏感性。"""
    records: list[dict] = []
    rng = np.random.default_rng(20260912)

    def shim(c, **kw):
        c = np.asarray(c, dtype=float)
        prim = _solve(c, kw, PRIMARY)
        rec = {"fun_primary": float(prim.fun), "status_primary": int(prim.status),
               "nvar": int(c.size), "alts": {}, "jitter": None}
        for a in ALT_METHODS:
            ra = _solve(c, kw, a)
            rec["alts"][a] = {
                "status": int(ra.status),
                "fun": float(ra.fun) if ra.x is not None else None,
                "sol_maxdiff": float(np.abs(ra.x - prim.x).max()) if ra.x is not None else None,
            }
        cj = c * (1.0 + JITTER * rng.standard_normal(c.size))
        rj = _solve(cj, kw, PRIMARY)
        if rj.x is not None:
            rec["jitter"] = {"fun": float(rj.fun),
                             "sol_maxdiff": float(np.abs(rj.x - prim.x).max())}
        records.append(rec)
        return prim

    days = list(range(M.DSTR.index(DELIVERY_START), M.ND, step))
    M.linprog = shim                                       # noqa: E731
    t0 = time.perf_counter()
    try:
        M.backtest(days[0], days[-1] + 1, K=K, stages=STAGES, S0=6000.0, verbose=False)
    finally:
        M.linprog = _real_linprog
    elapsed = time.perf_counter() - t0

    def rel_gap(a: float, b: float) -> float:
        return abs(a - b) / max(1.0, abs(b))

    stages = [f"stage{i}" for i in range(4)]
    summary = {"mode": "census", "K": K, "stages": list(STAGES), "step_days": step,
               "sampled_days": len(days), "lps": len(records), "elapsed_seconds": elapsed,
               "jitter_rel": JITTER, "by_stage": {}, "overall": {}}
    for si, sname in enumerate(stages):
        sel = records[si::4]
        if not sel:
            continue
        entry = {"n": len(sel)}
        for a in ALT_METHODS:
            ok = [r for r in sel if r["alts"][a]["fun"] is not None]
            gaps = [rel_gap(r["alts"][a]["fun"], r["fun_primary"]) for r in ok]
            diffs = [r["alts"][a]["sol_maxdiff"] for r in ok]
            entry[a] = {
                "solvable": len(ok), "failed": len(sel) - len(ok),
                "max_rel_obj_gap": max(gaps) if gaps else None,
                "n_obj_gap_gt_1e-9": sum(1 for g in gaps if g > 1e-9),
                "n_obj_gap_gt_1e-6": sum(1 for g in gaps if g > 1e-6),
                "n_solution_differs": sum(1 for d in diffs if d > 1e-6),
                "max_sol_diff": max(diffs) if diffs else None,
            }
        jf = [r for r in sel if r["jitter"] is not None]
        jgaps = [rel_gap(r["jitter"]["fun"], r["fun_primary"]) for r in jf]
        jdiffs = [r["jitter"]["sol_maxdiff"] for r in jf]
        entry["jitter"] = {
            "n": len(jf),
            "max_rel_obj_gap": max(jgaps) if jgaps else None,
            "n_solution_differs": sum(1 for d in jdiffs if d > 1e-6),
            "max_sol_diff": max(jdiffs) if jdiffs else None,
        }
        summary["by_stage"][sname] = entry

    all_gaps, all_diffs, all_jg, all_jd = [], [], [], []
    for r in records:
        for a in ALT_METHODS:
            v = r["alts"][a]
            if v["fun"] is not None:
                all_gaps.append(rel_gap(v["fun"], r["fun_primary"]))
                all_diffs.append(v["sol_maxdiff"])
        if r["jitter"] is not None:
            all_jg.append(rel_gap(r["jitter"]["fun"], r["fun_primary"]))
            all_jd.append(r["jitter"]["sol_maxdiff"])
    summary["overall"] = {
        "n_lps": len(records),
        "max_rel_obj_gap_across_methods": max(all_gaps) if all_gaps else None,
        "n_lps_obj_gap_gt_1e-9": sum(1 for g in all_gaps if g > 1e-9),
        "n_lps_obj_gap_gt_1e-6": sum(1 for g in all_gaps if g > 1e-6),
        "n_lp_method_pairs_solution_differs": sum(1 for d in all_diffs if d > 1e-6),
        "n_lp_method_pairs": len(all_diffs),
        "jitter_max_rel_obj_gap": max(all_jg) if all_jg else None,
        "jitter_n_solution_differs": sum(1 for d in all_jd if d > 1e-6),
        "jitter_n": len(all_jd),
    }
    (OUT / "solver_degeneracy_census.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    if len(sys.argv) < 2 or sys.argv[1] not in ("alt", "census"):
        print(__doc__)
        raise SystemExit(2)
    if sys.argv[1] == "alt":
        raise SystemExit(mode_alt(sys.argv[2] if len(sys.argv) > 2 else "highs-ds"))
    raise SystemExit(mode_census(int(sys.argv[2]) if len(sys.argv) > 2 else 8))
