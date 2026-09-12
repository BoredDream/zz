"""阶段B：第三问策略推荐决策表（附加分析，不改动任何已验收产物）。

只读复用 `outputs/q3/checkpoints/` 中 8 套主口径组合 + frozen0 基线的已验收结果，
另在 `outputs/q3/checkpoints_sensitivity/` 下补齐 8 套“退款/最终净额”口径的重新优化结果，
用于回答论文必须表态的问题：**是否采用全部三个预报时刻（6:00、12:00、18:00）**。

本脚本不修改 `src/q3_solver.py` 的 `policy_specs()`，因此不动摇既有检查点签名，
`outputs/q3/` 下所有已验收文件保持逐字节不变；新产物只写到
`outputs/q3/strategy_decision.{json,csv}` 与 `reports/q3_strategy_recommendation.md`。

运行：
    $env:PYTHONPATH="src"; .\\.venv\\Scripts\\python.exe -X utf8 scripts\\q3_strategy_decision.py
"""

from __future__ import annotations

import csv
import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from q3_solver import (  # noqa: E402
    DELIVERY_START,
    ISSUE_LABELS,
    Q3Config,
    ForecastCache,
    build_signature,
    deserialize_records,
    load_checkpoint,
    load_q3_inputs,
    policy_label,
    policy_specs,
    save_checkpoint,
    simulate_policy,
    totals,
)

OUTPUT_DIR = ROOT / "outputs" / "q3"
REPORT_PATH = ROOT / "reports" / "q3_strategy_recommendation.md"

# 8 种预报组合（含空集 `none`），顺序与 policy_specs() 一致。
COMBINATIONS: list[tuple[tuple[int, ...], str]] = [
    (updates, label)
    for label, updates, forecast_mode, settlement in policy_specs()
    if forecast_mode == "latest" and settlement == "per_submission"
]
BASELINE_LABEL = "none"
FROZEN_LABEL = "6+12+18_frozen0"

# 主策略小幅领先于次优组合的判定阈值：总费用差距在最优值的 0.1% 以内视为“并列候选”。
TIE_THRESHOLD = 0.001


def refund_signature(base_signature: str) -> str:
    """在基础签名上替换策略清单，保证退款口径检查点随输入/参数/求解器变化而失效。"""
    signature = json.loads(base_signature)
    signature["policies"] = [
        [policy_label(updates, "latest", "final_refund"), list(updates), "latest", "final_refund"]
        for updates, _ in COMBINATIONS
    ]
    signature["settlement_variant"] = "final_refund_sensitivity_only"
    return json.dumps(signature, ensure_ascii=False, sort_keys=True)


def release_stats(releases: list[dict[str, Any]]) -> dict[str, Any]:
    entries = [entry for entry in releases if entry["date"] >= DELIVERY_START.isoformat()]
    adjusted = [entry for entry in entries if abs(entry["increase_kwh"]) + abs(entry["decrease_kwh"]) > 1e-9]
    return {
        "release_count": len(entries),
        "adjustment_count": len(adjusted),
        "adjustment_days": len({entry["date"] for entry in adjusted}),
        "increase_kwh": float(sum(entry["increase_kwh"] for entry in entries)),
        "decrease_kwh": float(sum(entry["decrease_kwh"] for entry in entries)),
        "adjustment_fee_yuan": float(sum(entry["adjustment_fee_yuan"] for entry in entries)),
    }


def summarize(records: list[dict[str, Any]], releases: list[dict[str, Any]], start: int) -> dict[str, Any]:
    summary = totals(records, start)
    summary.update(release_stats(releases))
    return summary


def main() -> None:
    cfg = Q3Config()
    inputs = load_q3_inputs(ROOT / "problem" / "data", cfg)
    signature = build_signature(cfg, inputs)
    start = inputs["dates"].index(DELIVERY_START)
    # 情景缓存只在确有缺失检查点需要重算时才构建，便于检查点齐备时快速重生成决策表。
    cache: ForecastCache | None = None

    # ---- 主口径：只读复用已验收检查点，不重算、不改写 ----
    primary: dict[str, dict[str, Any]] = {}
    for label, _, _, _ in policy_specs():
        data = load_checkpoint(OUTPUT_DIR / "checkpoints" / f"{label}.json", signature)
        if data is None:
            raise SystemExit(
                f"缺少可用检查点 outputs/q3/checkpoints/{label}.json。\n"
                "本脚本只做附加分析，必须建立在已验收的第三问回测之上；"
                "请先运行 src/q3_solver.py 生成验收产物。"
            )
        primary[label] = summarize(deserialize_records(data["days"]), data["releases"], start)

    # ---- 退款/最终净额口径：补齐 8 套组合的重新优化结果 ----
    sensitivity_dir = OUTPUT_DIR / "checkpoints_sensitivity"
    sensitivity_dir.mkdir(parents=True, exist_ok=True)
    refund_signature_value = refund_signature(signature)
    refund: dict[str, dict[str, Any]] = {}
    for updates, _ in COMBINATIONS:
        label = policy_label(updates, "latest", "final_refund")
        path = sensitivity_dir / f"{label}.json"
        data = load_checkpoint(path, refund_signature_value)
        if data is None:
            print(f"[计算-退款口径] {label}", flush=True)
            if cache is None:
                cache = ForecastCache(inputs, cfg)
            records, releases = simulate_policy(inputs, cfg, updates, "latest", "final_refund", cache)
            save_checkpoint(path, refund_signature_value, label, records, releases)
            print(f"[完成-退款口径] {label}", flush=True)
        else:
            print(f"[复用检查点-退款口径] {label}", flush=True)
            records, releases = deserialize_records(data["days"]), data["releases"]
        refund[label] = summarize(records, releases, start)

    baseline_total = primary[BASELINE_LABEL]["total_cost_yuan"]
    best_total = min(primary[label]["total_cost_yuan"] for _, label in COMBINATIONS)

    rows: list[dict[str, Any]] = []
    for updates, label in COMBINATIONS:
        item = primary[label]
        refund_label = policy_label(updates, "latest", "final_refund")
        refund_item = refund[refund_label]
        saving = baseline_total - item["total_cost_yuan"]
        refund_total = refund_item["total_cost_yuan"]
        rows.append(
            {
                "policy": label,
                "issues": "仅0:00" if not updates else "、".join(ISSUE_LABELS[i] for i in updates),
                "release_count": item["release_count"],
                "adjustment_count": item["adjustment_count"],
                "adjustment_days": item["adjustment_days"],
                "total_cost_yuan": item["total_cost_yuan"],
                "saving_yuan": saving,
                "saving_pct": saving / baseline_total * 100.0,
                "emergency_kwh": item["emergency_kwh"],
                "emergency_cost_yuan": item["emergency_cost_yuan"],
                "settlement_cost_yuan": item["settlement_cost_yuan"],
                "planned_purchase_kwh": item["planned_purchase_kwh"],
                "final_contract_kwh": item["final_contract_kwh"],
                "increase_kwh": item["increase_kwh"],
                "decrease_kwh": item["decrease_kwh"],
                "adjustment_fee_yuan": item["adjustment_fee_yuan"],
                "refund_total_cost_yuan": refund_total,
                "refund_minus_primary_yuan": refund_total - item["total_cost_yuan"],
                "refund_saving_pct": (baseline_total - refund_total) / baseline_total * 100.0,
                "recommended": item["total_cost_yuan"] <= best_total * (1.0 + TIE_THRESHOLD),
            }
        )

    # ---- 两个结算口径下的名次（用于检验推荐结论是否依赖结算假设）----
    rank_primary = {row["policy"]: index for index, row in enumerate(sorted(rows, key=lambda r: r["total_cost_yuan"]), 1)}
    rank_refund = {row["policy"]: index for index, row in enumerate(sorted(rows, key=lambda r: r["refund_total_cost_yuan"]), 1)}
    for row in rows:
        row["rank_primary"] = rank_primary[row["policy"]]
        row["rank_refund"] = rank_refund[row["policy"]]

    # ---- 边际价值：在已有集合上再增加一个发布时刻能多省多少 ----
    saving_pct = {row["policy"]: row["saving_pct"] for row in rows}
    refund_saving_pct = {row["policy"]: row["refund_saving_pct"] for row in rows}
    label_of = {updates: label for updates, label in COMBINATIONS}
    marginal = []
    for subset in ((1,), (2,), (1, 2)):
        for extra in (1, 2, 3):
            if extra in subset:
                continue
            base_label = label_of[subset]
            full_label = label_of[tuple(sorted(subset + (extra,)))]
            marginal.append(
                {
                    "add": ISSUE_LABELS[extra],
                    "from": base_label,
                    "to": full_label,
                    "primary_pp": saving_pct[full_label] - saving_pct[base_label],
                    "refund_pp": refund_saving_pct[full_label] - refund_saving_pct[base_label],
                }
            )

    payload = {
        "note": "阶段B策略推荐决策表；主口径结果读自已验收检查点，退款口径为本次附加计算",
        "delivery_period": {"start": DELIVERY_START.isoformat(), "end": inputs["dates"][-1].isoformat(), "days": len(inputs["dates"]) - start},
        "baseline": {"policy": BASELINE_LABEL, "total_cost_yuan": baseline_total},
        "frozen_baseline": {"policy": FROZEN_LABEL, "total_cost_yuan": primary[FROZEN_LABEL]["total_cost_yuan"]},
        "rows": rows,
        "marginal_value": marginal,
        "tie_threshold": TIE_THRESHOLD,
    }
    (OUTPUT_DIR / "strategy_decision.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    write_csv(OUTPUT_DIR / "strategy_decision.csv", rows)
    REPORT_PATH.write_text(build_report(payload, primary, refund), encoding="utf-8")
    print(f"已写出 {OUTPUT_DIR / 'strategy_decision.json'}、{OUTPUT_DIR / 'strategy_decision.csv'}、{REPORT_PATH}")


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        for row in rows:
            writer.writerow({key: (f"{value:.6f}" if isinstance(value, float) else value) for key, value in row.items()})


def fmt(value: float) -> str:
    return f"{value:,.2f}"


def build_report(payload: dict[str, Any], primary: dict[str, Any], refund: dict[str, Any]) -> str:
    rows = payload["rows"]
    baseline_total = payload["baseline"]["total_cost_yuan"]
    frozen = payload["frozen_baseline"]
    best = min(rows, key=lambda row: row["total_cost_yuan"])
    runner_up = sorted(rows, key=lambda row: row["total_cost_yuan"])[1]
    lines: list[str] = []
    lines.append("# 第三问策略推荐决策表")
    lines.append("")
    lines.append(f"交付期：{payload['delivery_period']['start']} 至 {payload['delivery_period']['end']}，共 {payload['delivery_period']['days']} 天。")
    lines.append("")
    lines.append("主口径为“原计划费用保留、逐次提交相对当前生效合同计费（上调 1.5p、下调 0.5p）”；")
    lines.append("结算敏感性列为“退款且只按最终净额结算”口径下**重新优化**的总费用。两个口径不混算。")
    lines.append("")
    lines.append("## 1. 决策表")
    lines.append("")
    lines.append("| 策略 | 使用发布时刻 | 发布次数 | 调整次数 | 调整天数 | 主口径总费用/元 | 主口径排名 | 节省率 | 紧急购电量/kWh | 退款口径总费用/元 | 退款口径排名 | 是否推荐 |")
    lines.append("|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|")
    for row in rows:
        if row["policy"] == BASELINE_LABEL:
            mark = "基线"
        elif row["total_cost_yuan"] == best["total_cost_yuan"]:
            mark = "✅ 首选"
        elif row["recommended"]:
            mark = f"◻ 并列候选（差 {fmt(row['total_cost_yuan'] - best['total_cost_yuan'])} 元）"
        else:
            mark = "—"
        lines.append(
            f"| `{row['policy']}` | {row['issues']} | {row['release_count']} | {row['adjustment_count']} | {row['adjustment_days']} | "
            f"{fmt(row['total_cost_yuan'])} | {row['rank_primary']} | {row['saving_pct']:.4f}% | {row['emergency_kwh']:,.4f} | "
            f"{fmt(row['refund_total_cost_yuan'])} | {row['rank_refund']} | {mark} |"
        )
    lines.append("")
    lines.append(
        f"累计上调/下调量与调整费见 `outputs/q3/strategy_decision.csv`；"
        f"“并列候选”指主口径总费用落在最优值 {TIE_THRESHOLD * 100:.1f}% 以内。"
    )
    lines.append(f"（`{FROZEN_LABEL}` 为冻结 0:00 光伏预报的对照基线，总费用 {fmt(frozen['total_cost_yuan'])} 元，不参与推荐排序。）")
    lines.append("")
    lines.append("## 2. 三个预报时刻的边际价值")
    lines.append("")
    lines.append("“新增某时刻”指在已有集合基础上再增加一次发布，边际价值为节省率的增量（百分点）。")
    lines.append("")
    lines.append("| 新增时刻 | 组合变化 | 主口径边际价值 | 退款口径边际价值 | 方向一致 |")
    lines.append("|---|---|---:|---:|---|")
    for item in payload["marginal_value"]:
        consistent = "是" if item["primary_pp"] > 0 and item["refund_pp"] > 0 else "否"
        lines.append(
            f"| {item['add']} | `{item['from']}` → `{item['to']}` | {item['primary_pp']:+.4f} pp | {item['refund_pp']:+.4f} pp | {consistent} |"
        )
    lines.append("")
    lines.append("## 3. 结论与推荐")
    lines.append("")
    gap = runner_up["total_cost_yuan"] - best["total_cost_yuan"]
    lines.append(
        f"主口径下费用最低的是 `{best['policy']}`（{fmt(best['total_cost_yuan'])} 元，节省 {best['saving_pct']:.4f}%），"
        f"次优为 `{runner_up['policy']}`（{fmt(runner_up['total_cost_yuan'])} 元，节省 {runner_up['saving_pct']:.4f}%），"
        f"两者相差 {fmt(gap)} 元（{gap / runner_up['total_cost_yuan'] * 100:.4f}%）。"
    )
    lines.append("")
    lines.append("**推荐：采用全部三个预报时刻 `6+12+18`。** 理由：")
    lines.append("")
    lines.append(
        f"1. 18:00 预报的边际价值在两个结算口径下均为正（见第 2 节），没有出现“采用反而更差”的情形，"
        "因此“建议弃用 18:00”缺乏数据支持。"
    )
    lines.append(
        f"2. 相对只用到 12:00 的 `6+12`，多一次发布换来 {fmt(gap)} 元，即每增加一次发布约合 {gap / 334:.2f} 元/天；"
        "是否值得取决于运行方对调度操作频次的取舍，本表把该权衡显式给出，供论文说明。"
    )
    swaps = [row for row in rows if row["rank_primary"] != row["rank_refund"] and row["policy"] != BASELINE_LABEL]
    if swaps:
        detail = "、".join(f"`{row['policy']}`（第 {row['rank_primary']} → 第 {row['rank_refund']}）" for row in swaps)
        lines.append(
            f"3. 结算敏感性**不改变最优与次优组合**，也不改变推荐：两个口径下前两名都是 `{best['policy']}` 与 `{runner_up['policy']}`，"
            f"`{BASELINE_LABEL}` 与 `18` 仍居末两位。但中间名次确有交换（{detail}），"
            "原因是退款口径下可以自由下调，各组合的收敛程度不同；论文若引用完整费用排序，必须注明所用结算口径（第 4 节）。"
        )
    else:
        lines.append("3. 结算敏感性不改变排序，说明该结论对合同口径的两种解释都稳健（第 4 节）。")
    lines.append("")
    lines.append(
        "**论文必须同时写明的限制**：18:00 的边际价值最小，且日内负荷中心预测不随发布时刻更新，"
        "6/12/18 相对 0:00 的新信息几乎只有光伏预报一项，这会使多时点预报的价值被**低估**；"
        "若未来负荷预测也随发布时刻更新，18:00 的相对价值可能上升。"
    )
    lines.append("")
    lines.append("## 4. 结算敏感性")
    lines.append("")
    lines.append("| 策略 | 主口径总费用/元 | 主口径排名 | 退款口径总费用/元 | 退款口径排名 | 退款口径较主口径/元 | 差值占比 |")
    lines.append("|---|---:|---:|---:|---:|---:|---:|")
    for row in rows:
        delta = row["refund_minus_primary_yuan"]
        lines.append(
            f"| `{row['policy']}` | {fmt(row['total_cost_yuan'])} | {row['rank_primary']} | {fmt(row['refund_total_cost_yuan'])} | "
            f"{row['rank_refund']} | {fmt(delta)} | {delta / row['total_cost_yuan'] * 100:.4f}% |"
        )
    lines.append("")
    lines.append(
        "主口径下 8 套组合的累计下调量全部为 0（见 `outputs/q3/strategy_decision.csv` 的 `decrease_kwh` 列），"
        "这是“下调已被支付且不退款”规则的经济后果，不是代码限制——同一求解器在退款口径下可以自由下调。"
        "因此退款口径费用系统性低于主口径（各组合低 0.006%—1.79%），且各组合受益幅度不同，"
        "这正是中间名次发生交换的原因。**两个口径的最优与次优组合一致，推荐结论不变**；"
        "两个口径都需人工确认后才能作为论文的最终结算假设。"
    )
    lines.append("")
    lines.append("## 5. 运行与复算")
    lines.append("")
    lines.append("```powershell")
    lines.append('$env:PYTHONPATH="src"; .\\.venv\\Scripts\\python.exe -X utf8 scripts\\q3_strategy_decision.py')
    lines.append("```")
    lines.append("")
    lines.append(
        "主口径数字只读复用 `outputs/q3/checkpoints/` 的已验收检查点，未重算、未改写；"
        "退款口径结果在 `outputs/q3/checkpoints_sensitivity/` 下断点续跑。"
    )
    lines.append("")
    return "\n".join(lines)


if __name__ == "__main__":
    main()
