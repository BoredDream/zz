"""汇总现行Q3八种预报发布组合，计算边际价值与Shapley贡献。"""
from __future__ import annotations

import csv
import itertools
import json
import math
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "outputs" / "q3_multistage"
K = 30
SPECS = [
    ("0-only", (0,)),
    ("0+6", (0, 1)), ("0+12", (0, 2)), ("0+18", (0, 3)),
    ("0+6+12", (0, 1, 2)), ("0+6+18", (0, 1, 3)),
    ("0+12+18", (0, 2, 3)), ("0+6+12+18", (0, 1, 2, 3)),
]
ISSUE = {1: "6:00", 2: "12:00", 3: "18:00"}
M_ETA = 0.9
M_CMAX = 5000 * (1 / 6.0)   # 与 src/q3_multistage.py 的常量写法保持一致


def tag(stages: tuple[int, ...]) -> str:
    return "".join(map(str, stages))


def main() -> int:
    rows, by_set = [], {}
    ref_period = None
    for label, stages in SPECS:
        path = OUT / f"summary_stages{tag(stages)}_K{K}.json"
        if not path.exists():
            raise FileNotFoundError(f"缺少组合结果：{path}")
        obj = json.loads(path.read_text(encoding="utf-8"))
        if tuple(obj["meta"]["stages"]) != stages or obj["meta"]["delivery_period"]["days"] != 334:
            raise ValueError(f"组合元数据不一致：{path}")
        # 对照组必须同口径：情景数、储能效率与单时段上限、交付期起止都要逐一相同，
        # 否则费用差里会混进非「是否引入该时刻预报」的因素。
        meta = obj["meta"]
        # 注意：元数据里的 interval_limit_kwh 是 5000*(1/6) 而非 5000/6，
        # 两者在 float 末位不同，必须按相对容差比较，不能直接 !=。
        if (meta["scenarios_K"] != K or not math.isclose(meta["eta"], M_ETA)
                or not math.isclose(meta["interval_limit_kwh"], M_CMAX, rel_tol=1e-12)):
            raise ValueError(f"组合物理口径不一致：{path}")
        period = (meta["delivery_period"]["start"], meta["delivery_period"]["end"])
        if ref_period is None:
            ref_period = period
        elif period != ref_period:
            raise ValueError(f"交付期不一致：{path} -> {period} != {ref_period}")
        total = float(obj["totals"]["total_cost_yuan"])
        item = {"policy": label, "stages": list(stages), "adjustment_times": [ISSUE[s] for s in stages if s],
                **{k: float(v) for k, v in obj["totals"].items()}}
        rows.append(item)
        by_set[frozenset(stages[1:])] = total

    baseline = by_set[frozenset()]
    for row in rows:
        row["saving_vs_0_only_yuan"] = baseline - row["total_cost_yuan"]
        row["saving_vs_0_only_pct"] = 100.0 * row["saving_vs_0_only_yuan"] / baseline
    for rank, row in enumerate(sorted(rows, key=lambda x: x["total_cost_yuan"]), 1):
        row["rank"] = rank

    marginal = {}
    players = (1, 2, 3)
    for p in players:
        vals = []
        for n in range(3):
            for subset in itertools.combinations([q for q in players if q != p], n):
                s = frozenset(subset)
                vals.append({"context": [ISSUE[q] for q in subset],
                             "saving_yuan": by_set[s] - by_set[s | {p}]})
        marginal[ISSUE[p]] = vals

    shapley = {}
    for p in players:
        value = 0.0
        others = [q for q in players if q != p]
        for n in range(3):
            weight = math.factorial(n) * math.factorial(2-n) / math.factorial(3)
            for subset in itertools.combinations(others, n):
                s = frozenset(subset)
                value += weight * (by_set[s] - by_set[s | {p}])
        shapley[ISSUE[p]] = value

    # 自检 1：费用三项拆分必须恒等于总费用（否则后续所有差值都不可信）。
    for row in rows:
        split = row["plan_cost_yuan"] + row["adjust_cost_yuan"] + row["emergency_cost_yuan"]
        if abs(split - row["total_cost_yuan"]) > 1e-6:
            raise ValueError(f"{row['policy']} 费用拆分与总费用不一致：{split} vs {row['total_cost_yuan']}")
    # 自检 2：八种组合的集合必须齐备（缺一个会让某些条件边际根本算不出来）。
    expect = {frozenset(s) for n in range(4) for s in itertools.combinations((1, 2, 3), n)}
    if set(by_set) != expect:
        raise ValueError(f"组合集合不齐：缺 {sorted(map(sorted, expect - set(by_set)))}")
    # 自检 3：Shapley 分摊之和恒等于全启用相对 0-only 的总节省（效率公理，必须是精确恒等）。
    full_saving = by_set[frozenset()] - by_set[frozenset(players)]
    if abs(sum(shapley.values()) - full_saving) > 1e-6:
        raise ValueError(f"Shapley 效率公理不成立：{sum(shapley.values())} != {full_saving}")

    best = min(rows, key=lambda x: x["total_cost_yuan"])
    result = {
        "model": "q3_multistage_current_145_interval_natural_day",
        "K": K, "delivery_days": 334, "baseline": "0-only",
        "best_policy": best["policy"], "rows": rows,
        "conditional_marginal_savings": marginal,
        "shapley_savings_vs_0_only_for_full_policy_yuan": shapley,
        "full_policy_saving_vs_0_only_yuan": baseline - by_set[frozenset(players)],
    }
    (OUT / "q3_stage_comparison.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    fields = ["policy", "rank", "total_cost_yuan", "saving_vs_0_only_yuan", "saving_vs_0_only_pct",
              "plan_cost_yuan", "adjust_cost_yuan", "emergency_cost_yuan", "emergency_kwh",
              "adjust_up_kwh", "adjust_down_kwh"]
    with (OUT / "q3_stage_comparison.csv").open("w", newline="", encoding="utf-8-sig") as fh:
        writer = csv.DictWriter(fh, fieldnames=fields)
        writer.writeheader()
        writer.writerows({k: row[k] for k in fields} for row in rows)
    print(json.dumps({"best_policy": best["policy"], "best_total": best["total_cost_yuan"],
                      "full_saving": result["full_policy_saving_vs_0_only_yuan"],
                      "shapley": shapley}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
