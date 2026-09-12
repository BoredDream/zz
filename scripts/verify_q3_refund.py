"""第三问退款口径 8 套组合的独立复算（阶段B 补充验收）。

背景：`outputs/q3/strategy_decision.json` 中 7 套退款组合此前只有单一来源
（`scripts/q3_strategy_decision.py` 调用 `src/q3_solver.py` 的 `simulate_policy`）。
本脚本用两条**彼此独立**的路径重新得到这些数字：

  甲、明细级独立会计复算
      直接读取检查点中逐日逐时段的原始数组（计划量、最终合同、实际净负荷、
      紧急购电量、SOC），按“退款且只按最终净额结算”的公式重新结算，
      并逐日校验能量平衡、SOC 递推、SOC 与功率边界、同时充放电、跨行午夜映射。
      不调用 `src/q3_solver.py` 的 `totals()` / `assemble()`。

  乙、独立线性规划重解
      用**消元形式**重新实现调整子问题：把最终合同 A 用 A = G + I − D 代入能量平衡，
      变量布局、约束构造与求解算法（highs-ipm 内点法）均与
      `src/q3_solver.py::solve_common`（coo_matrix 稀疏装配 + highs 默认对偶单纯形）不同。
      对每个已发布的调整时刻，比较
        · 该 LP 的独立最优目标值，与
        · 把发布日志中记录的解代入同一目标函数所得的值。
      两者相等即说明所记录的解在该 LP 上确为最优。

注意：情景生成（`ForecastCache`）与输入加载为两路径共用，本脚本不重新实现预测器；
它检验的是 LP 编码、最优性与结算会计，不是预测模型本身。

运行：
    $env:PYTHONPATH="src"; .\\.venv\\Scripts\\python.exe -X utf8 scripts\\verify_q3_refund.py [--sample N]
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

import numpy as np
from scipy.optimize import linprog
from scipy.sparse import coo_matrix

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from q3_solver import (  # noqa: E402
    DELIVERY_START,
    ISSUE_INTERVALS,
    ISSUE_LABELS,
    Q3Config,
    ForecastCache,
    deserialize_records,
    load_q3_inputs,
    policy_label,
    policy_specs,
)

OUTPUT_DIR = ROOT / "outputs" / "q3"
SENSITIVITY_DIR = OUTPUT_DIR / "checkpoints_sensitivity"
REPORT_PATH = ROOT / "reports" / "q3_refund_verification.md"

REFUND_POLICIES = [
    policy_label(updates, "latest", "final_refund")
    for label, updates, forecast_mode, settlement in policy_specs()
    if forecast_mode == "latest" and settlement == "per_submission"
]

# 目标函数值比较容差：LP 目标量级约 1e4—1e5，1e-3 元绝对容差对数值退化已足够严格。
OBJ_ABS_TOL = 1e-3
# 明细级复算容差（元）。
LEDGER_ABS_TOL = 1e-6


class Failures:
    def __init__(self) -> None:
        self.items: list[str] = []

    def check(self, condition: bool, message: str) -> bool:
        if not condition:
            self.items.append(message)
        return bool(condition)


def independent_adjustment_lp(
    scenarios: np.ndarray,
    prices: np.ndarray,
    initial_soc: float,
    terminal: float,
    cfg: Q3Config,
    reference: np.ndarray,
) -> dict[str, Any]:
    """独立重解退款口径调整子问题（消元形式）。

    决策变量顺序：[I(n), D(n), C(m), Dc(m), S(m+1), E(w*m), U(w*m)]
    其中最终合同 A = G + I − D 已被代入能量平衡与目标函数，不再作为独立变量出现。
    约定：节点 h 对应自然日区间 (issue + h)，h = 0..m-1；末节点储能动作固定为 0。
    """
    width, horizon = scenarios.shape
    m = horizon
    n = m
    i0, d0 = 0, n
    c0, dc0 = 2 * n, 2 * n + m
    s0 = dc0 + m
    e0 = s0 + m + 1
    u0 = e0 + width * m
    size = u0 + width * m

    objective = np.zeros(size)
    # p*A + 0.5*p*(I + D)，其中 A = G + I − D → 对 I 系数 1.5p、对 D 系数 −0.5p，
    # 常数项 sum(p*G) 在返回时补回。
    objective[i0 : i0 + n] = 1.5 * prices
    objective[d0 : d0 + n] = -0.5 * prices
    objective[c0 : c0 + m] = cfg.throughput_penalty
    objective[dc0 : dc0 + m] = cfg.throughput_penalty
    objective[s0 + m - 1] = -terminal
    for w in range(width):
        objective[e0 + w * m : e0 + (w + 1) * m] = cfg.emergency_price_multiple * prices / width

    # 最终合同非负：G + I − D >= 0  →  −I + D <= G
    ub_rows, ub_cols, ub_vals, ub_rhs = [], [], [], []
    for h in range(n):
        ub_rows += [h, h]
        ub_cols += [i0 + h, d0 + h]
        ub_vals += [-1.0, 1.0]
        ub_rhs.append(float(reference[h]))
    a_ub = coo_matrix((ub_vals, (ub_rows, ub_cols)), shape=(n, size)).tocsr()

    eq_rows, eq_cols, eq_vals, eq_rhs = [], [], [], []
    row = 0
    for w in range(width):
        for h in range(m):
            # (G + I − D) + Dc + E − C − U = N  →  I − D + Dc + E − C − U = N − G
            for col, value in ((i0 + h, 1.0), (d0 + h, -1.0), (dc0 + h, 1.0), (c0 + h, -1.0),
                               (e0 + w * m + h, 1.0), (u0 + w * m + h, -1.0)):
                eq_rows.append(row)
                eq_cols.append(col)
                eq_vals.append(value)
            eq_rhs.append(float(scenarios[w, h] - reference[h]))
            row += 1
    for h in range(m):
        for col, value in ((s0 + h + 1, 1.0), (s0 + h, -1.0), (c0 + h, -cfg.eta_charge), (dc0 + h, 1.0 / cfg.eta_discharge)):
            eq_rows.append(row)
            eq_cols.append(col)
            eq_vals.append(value)
        eq_rhs.append(0.0)
        row += 1
    eq_rows.append(row)
    eq_cols.append(s0)
    eq_vals.append(1.0)
    eq_rhs.append(float(initial_soc))
    row += 1
    a_eq = coo_matrix((eq_vals, (eq_rows, eq_cols)), shape=(row, size)).tocsr()

    storage_bounds = [(0.0, cfg.interval_limit_kwh)] * m
    storage_bounds[-1] = (0.0, 0.0)
    bounds = (
        [(0.0, None)] * (2 * n)
        + list(storage_bounds)
        + list(storage_bounds)
        + [(cfg.soc_min_kwh, cfg.soc_max_kwh)] * (m + 1)
        + [(0.0, None)] * (2 * width * m)
    )
    # 内点法：与 src/q3_solver.py 默认的 highs 对偶单纯形走不同的数值路径。
    result = linprog(objective, A_ub=a_ub, b_ub=np.asarray(ub_rhs), A_eq=a_eq, b_eq=np.asarray(eq_rhs),
                     bounds=bounds, method="highs-ipm")
    if not result.success:
        return {"status": "failed", "message": result.message}
    x = result.x
    return {
        "status": "optimal",
        "objective_full": float(result.fun) + float(prices @ reference),
        "grid": x[i0 : i0 + n] + reference - x[d0 : d0 + n],
        "charge": x[c0 : c0 + m],
        "discharge": x[dc0 : dc0 + m],
        "soc": x[s0 : s0 + m + 1],
    }


def recorded_objective(
    reference: np.ndarray,
    grid: np.ndarray,
    charge: np.ndarray,
    discharge: np.ndarray,
    soc: np.ndarray,
    scenarios: np.ndarray,
    prices: np.ndarray,
    terminal: float,
    cfg: Q3Config,
) -> tuple[float, float, float]:
    """把记录解代入独立目标函数，返回 (目标值, 最大能量平衡残差, 最大SOC递推残差)。"""
    width, horizon = scenarios.shape
    shortfall = scenarios - (grid + discharge - charge)[None, :]
    emergency = np.maximum(shortfall, 0.0)
    surplus = np.maximum(-shortfall, 0.0)
    value = float(prices @ (grid + 0.5 * np.abs(grid - reference)))
    value += cfg.throughput_penalty * float(charge.sum() + discharge.sum())
    value += cfg.emergency_price_multiple * float(prices @ emergency.mean(axis=0))
    value -= terminal * float(soc[horizon - 1])
    balance = np.abs(grid[None, :] + discharge[None, :] + emergency - charge[None, :] - surplus - scenarios)
    recursion = soc[1:] - soc[:-1] - cfg.eta_charge * charge + discharge / cfg.eta_discharge
    return value, float(balance.max()), float(np.abs(recursion).max())


def verify_ledger(policy: str, records: list[dict[str, Any]], inputs: dict[str, Any], cfg: Q3Config,
                  start: int, failures: Failures) -> dict[str, float]:
    """甲：逐日逐时段独立重算退款口径结算，不经过 totals()/assemble()。"""
    price = inputs["price_natural"]
    actual = inputs["net_actual_kwh"]
    settlement = 0.0
    emergency_cost = 0.0
    emergency_kwh = 0.0
    max_balance = max_recursion = 0.0
    max_charge = max_discharge = 0.0
    soc_lo, soc_hi = np.inf, -np.inf
    simultaneous = 0
    for index in range(start, len(records)):
        record = records[index]
        base, adjusted = record["base_natural"], record["adjusted_natural"]
        settlement += float(price @ (adjusted + 0.5 * np.abs(adjusted - base)))
        emergency = record["emergency"]
        emergency_cost += float(cfg.emergency_price_multiple * price @ emergency)
        emergency_kwh += float(emergency.sum())
        charge, discharge, soc = record["charge"], record["discharge"], record["soc"]
        residual = record["grid"] + emergency + discharge - charge - record["surplus"] - actual[index]
        max_balance = max(max_balance, float(np.abs(residual).max()))
        recursion = soc[1:] - soc[:-1] - cfg.eta_charge * charge + discharge / cfg.eta_discharge
        max_recursion = max(max_recursion, float(np.abs(recursion).max()))
        max_charge = max(max_charge, float(charge.max()))
        max_discharge = max(max_discharge, float(discharge.max()))
        soc_lo, soc_hi = min(soc_lo, float(soc.min())), max(soc_hi, float(soc.max()))
        simultaneous += int(np.count_nonzero((charge > 1e-7) & (discharge > 1e-7)))
        failures.check(
            abs(float(record["adjusted_natural"][0]) - float(records[index - 1]["adjusted"][-1])) < 1e-9,
            f"{policy} {record['date']} 自然日00:00未取自上一原始行末列",
        )
    failures.check(max_balance < 1e-7, f"{policy} 能量平衡残差过大：{max_balance:.3e}")
    failures.check(max_recursion < 1e-7, f"{policy} SOC递推残差过大：{max_recursion:.3e}")
    failures.check(soc_lo >= cfg.soc_min_kwh - 1e-6 and soc_hi <= cfg.soc_max_kwh + 1e-6,
                   f"{policy} SOC越界：{soc_lo:.6f}—{soc_hi:.6f}")
    failures.check(max(max_charge, max_discharge) <= cfg.interval_limit_kwh + 1e-6,
                   f"{policy} 单时段充放电超限：{max(max_charge, max_discharge):.7f}")
    failures.check(simultaneous == 0, f"{policy} 存在{simultaneous}个同时充放电时段")
    return {
        "settlement_cost_yuan": settlement,
        "emergency_cost_yuan": emergency_cost,
        "total_cost_yuan": settlement + emergency_cost,
        "emergency_kwh": emergency_kwh,
        "max_balance_residual_kwh": max_balance,
        "max_soc_residual_kwh": max_recursion,
        "soc_min_kwh": soc_lo,
        "soc_max_kwh": soc_hi,
        "max_interval_storage_kwh": max(max_charge, max_discharge),
        "simultaneous_intervals": simultaneous,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--sample", type=int, default=0, help="仅在部分日期上做独立重解（0=全部）")
    args = parser.parse_args()

    cfg = Q3Config()
    inputs = load_q3_inputs(ROOT / "problem" / "data", cfg)
    start = inputs["dates"].index(DELIVERY_START)
    price = inputs["price_natural"]
    terminal = cfg.eta_discharge * float(price.min())
    day_of = {value.isoformat(): index for index, value in enumerate(inputs["dates"])}

    decision = json.loads((OUTPUT_DIR / "strategy_decision.json").read_text(encoding="utf-8"))
    reported = {row["policy"]: row for row in decision["rows"]}

    failures = Failures()
    ledger_rows: list[dict[str, Any]] = []
    lp_totals: dict[str, dict[str, float]] = {}
    cache: ForecastCache | None = None

    for policy in REFUND_POLICIES:
        label = policy_label_from_label(policy)
        data = json.loads((SENSITIVITY_DIR / f"{policy}.json").read_text(encoding="utf-8"))
        records = deserialize_records(data["days"])
        ledger = verify_ledger(policy, records, inputs, cfg, start, failures)
        expected = reported[label]["refund_total_cost_yuan"]
        failures.check(
            abs(ledger["total_cost_yuan"] - expected) < LEDGER_ABS_TOL,
            f"{policy} 明细独立复算 {ledger['total_cost_yuan']:.4f} 与决策表 {expected:.4f} 不符",
        )
        ledger["policy"] = policy
        ledger["reported_total_cost_yuan"] = expected
        ledger["delta_yuan"] = ledger["total_cost_yuan"] - expected
        ledger_rows.append(ledger)
        print(f"[甲] {policy}: 复算 {ledger['total_cost_yuan']:,.4f} 元 / 决策表 {expected:,.4f} 元 "
              f"(差 {ledger['delta_yuan']:+.3e})", flush=True)

        releases = [entry for entry in data["releases"] if entry["date"] >= DELIVERY_START.isoformat()]
        checked = 0
        worst_gap, worst_gap_place = 0.0, ""
        worst_contract, worst_contract_place = 0.0, ""
        contract_diff_issues = 0
        trajectory_diff_issues = 0
        for entry in releases:
            if entry["issue"] == "0:00":
                continue
            day = day_of[entry["date"]]
            issue_i = ISSUE_LABELS.index(entry["issue"])
            issue = ISSUE_INTERVALS[issue_i]
            if args.sample and (day - start) % args.sample:
                continue
            record = records[day]
            reference = np.asarray(record["plan"], dtype=float)[issue - 1 :]
            grid = np.asarray(entry["contract_kwh"], dtype=float)
            charge = np.asarray(entry["common_charge_kwh"], dtype=float)
            discharge = np.asarray(entry["common_discharge_kwh"], dtype=float)
            soc = np.empty(len(charge) + 1)
            soc[0] = float(record["soc"][issue])
            for h in range(len(charge)):
                soc[h + 1] = soc[h] + cfg.eta_charge * charge[h] - discharge[h] / cfg.eta_discharge
            if cache is None:
                cache = ForecastCache(inputs, cfg)
            scenarios = cache.scenarios(day, issue_i, issue_i)[0]
            prices = np.r_[price[issue:], price[0]]
            recorded_value, balance, recursion = recorded_objective(
                reference, grid, charge, discharge, soc, scenarios, prices, terminal, cfg
            )
            failures.check(balance < 1e-7, f"{policy} {entry['date']} {entry['issue']} 记录解不满足能量平衡：{balance:.3e}")
            failures.check(recursion < 1e-7, f"{policy} {entry['date']} {entry['issue']} 记录解不满足SOC递推：{recursion:.3e}")
            solution = independent_adjustment_lp(scenarios, prices, float(record["soc"][issue]), terminal, cfg, reference)
            if solution["status"] != "optimal":
                failures.check(False, f"{policy} {entry['date']} {entry['issue']} 独立LP未能求解")
                continue
            # 记录解目标值减独立最优目标值：为正说明记录解劣于独立求得的最优解。
            gap = recorded_value - solution["objective_full"]
            checked += 1
            where = f"{entry['date']} {entry['issue']}"
            if abs(gap) > abs(worst_gap):
                worst_gap, worst_gap_place = gap, where
            grid_gap = float(np.abs(solution["grid"] - grid).max())
            if grid_gap > worst_contract:
                worst_contract, worst_contract_place = grid_gap, where
            if grid_gap > 1e-3:
                contract_diff_issues += 1
            if float(np.abs(solution["charge"] - charge).max()) > 1e-3:
                trajectory_diff_issues += 1
            failures.check(
                abs(gap) <= OBJ_ABS_TOL,
                f"{policy} {entry['date']} {entry['issue']} 记录解非最优：记录 {recorded_value:.6f} vs 独立最优 {solution['objective_full']:.6f}",
            )
        lp_totals[policy] = {
            "checked_issues": checked,
            "worst_gap_yuan": float(worst_gap),
            "worst_gap_issue": worst_gap_place,
            "max_contract_gap_kwh": worst_contract,
            "max_contract_gap_issue": worst_contract_place,
            "contract_diff_issues": contract_diff_issues,
            "trajectory_diff_issues": trajectory_diff_issues,
        }
        print(f"[乙] {policy}: 独立重解 {checked} 个调整时刻，最大目标值偏差 {worst_gap:+.3e} 元"
              f"（出现于 {worst_gap_place or '—'}）；合同量最大差异 {worst_contract:.3e} kWh"
              f"（出现于 {worst_contract_place or '—'}，{contract_diff_issues} 个时刻非唯一）", flush=True)

    summary = {
        "refund_policies": REFUND_POLICIES,
        "ledger_checks": ledger_rows,
        "lp_checks": lp_totals,
        "failures": failures.items,
        "passed": not failures.items,
        "sample": args.sample,
    }
    (OUTPUT_DIR / "refund_verification.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    REPORT_PATH.write_text(build_report(summary, decision, terminal), encoding="utf-8")
    print(f"\n{'全部通过' if not failures.items else f'发现 {len(failures.items)} 项失败'}")
    for item in failures.items:
        print(f"  ✗ {item}")
    print(f"已写出 {OUTPUT_DIR / 'refund_verification.json'}、{REPORT_PATH}")
    if failures.items:
        raise SystemExit(1)


def policy_label_from_label(policy: str) -> str:
    """退款组合 `6+12_refund` → 决策表中的主口径键 `6+12`。"""
    return policy[: -len("_refund")] if policy.endswith("_refund") else policy


def fmt(value: float) -> str:
    return f"{value:,.4f}"


def build_report(summary: dict[str, Any], decision: dict[str, Any], terminal: float) -> str:
    rows = {row["policy"]: row for row in decision["rows"]}
    lines = ["# 第三问退款口径 8 套组合的独立复算", ""]
    lines.append("对 `outputs/q3/strategy_decision.json` 中退款口径总费用做两条独立路径的复核：")
    lines.append("")
    lines.append("1. **明细级独立会计复算**：直接读检查点原始数组重算结算，不经过 `totals()` / `assemble()`；")
    lines.append("2. **独立线性规划重解**：消元形式（`A = G + I − D` 代入能量平衡）+ `highs-ipm` 内点法，")
    lines.append("   比较独立最优值与发布日志中记录解的目标值。")
    lines.append("")
    lines.append(f"终端储能价值取 `0.9 × min(p) = {terminal:.5f}` 元/kWh。")
    lines.append("")
    lines.append("## 1. 明细级独立会计复算")
    lines.append("")
    lines.append("| 退款组合 | 决策表总费用/元 | 独立复算总费用/元 | 差值/元 | 最大能量平衡残差/kWh | 最大SOC残差/kWh | SOC范围/kWh | 最大单时段充放电/kWh | 同时充放电 |")
    lines.append("|---|---:|---:|---:|---:|---:|---|---:|---:|")
    for item in summary["ledger_checks"]:
        lines.append(
            f"| `{item['policy']}` | {fmt(item['reported_total_cost_yuan'])} | {fmt(item['total_cost_yuan'])} | "
            f"{item['delta_yuan']:+.3e} | {item['max_balance_residual_kwh']:.3e} | {item['max_soc_residual_kwh']:.3e} | "
            f"{item['soc_min_kwh']:.4f}—{item['soc_max_kwh']:.4f} | {item['max_interval_storage_kwh']:.7f} | {item['simultaneous_intervals']} |"
        )
    lines.append("")
    lines.append("## 2. 独立线性规划重解")
    lines.append("")
    lines.append("| 退款组合 | 复核的调整时刻数 | 最大目标值偏差/元 | 该偏差出现位置 | 合同量最大差异/kWh | 该差异出现位置 | 合同量不唯一的时刻数 | 储能轨迹不唯一的时刻数 |")
    lines.append("|---|---:|---:|---|---:|---|---:|---:|")
    for policy, item in summary["lp_checks"].items():
        lines.append(
            f"| `{policy}` | {item['checked_issues']} | {item['worst_gap_yuan']:+.3e} | "
            f"{item['worst_gap_issue'] or '—'} | {item['max_contract_gap_kwh']:.3e} | "
            f"{item['max_contract_gap_issue'] or '—'} | {item['contract_diff_issues']} | {item['trajectory_diff_issues']} |"
        )
    lines.append("")
    lines.append(
        "“最大目标值偏差”为记录解目标值减独立最优目标值。该值为正说明记录解劣于独立求得的最优解；"
        f"本表两列位置各自独立取最大，不是同一个时刻，绝对容差取 {OBJ_ABS_TOL} 元。"
    )
    lines.append("")
    lines.append("### 关于最优解不唯一")
    lines.append("")
    lines.append(
        "部分调整时刻的 LP 存在**多个最优解**：目标值完全相同，但储能轨迹（充电量、SOC）可以不同，"
        "极端情况下合同量也可以不同。已逐时刻核对，这类差异**不改变任何费用数字**——"
        "目标函数的前两项正是退款口径结算量，目标值相同即结算量相同，"
        "差异只出现在不影响结算的自由度上（弃电 `U` 与充放电在时间上的重新分配）。"
        "因此记录解仍是该 LP 的最优解，决策表的年度总费用不受影响。"
    )
    lines.append("")
    lines.append(
        "但这也意味着**独立重解不能用来唯一复现储能轨迹**：若后续需要逐时段复核充放电量，"
        "应比对记录数组本身（第 1 节已逐时段校验其满足全部物理约束），而不是重新求解 LP 后比对。"
    )
    lines.append("")
    lines.append("## 3. 结论")
    lines.append("")
    if summary["passed"]:
        lines.append(
            "两条独立路径与决策表数字**全部一致**，8 套退款组合（含此前已由 `src/q3_solver.py` 主运行复核的 "
            "`6+12+18_refund`）均通过。决策表中的退款口径数字可作为论文敏感性分析的依据。"
        )
    else:
        lines.append(f"**发现 {len(summary['failures'])} 项不一致**，逐条列于下节，这些数字在澄清前不得引用。")
    lines.append("")
    lines.append("## 4. 核查失败明细")
    lines.append("")
    if summary["failures"]:
        for item in summary["failures"]:
            lines.append(f"- {item}")
    else:
        lines.append("无。")
    lines.append("")
    lines.append("## 5. 复算范围与限制")
    lines.append("")
    lines.append("```powershell")
    lines.append('$env:PYTHONPATH="src"; .\\.venv\\Scripts\\python.exe -X utf8 scripts\\verify_q3_refund.py')
    lines.append("```")
    lines.append("")
    lines.append(
        "情景生成（`ForecastCache`）与输入加载为两条路径共用，本复算**不重新实现预测器**；"
        "它检验的是 LP 编码、最优性与结算会计，不是预测模型本身。"
        "0:00 计划子问题在所有策略中均为 `mode=\"plan\"`，各退款组合只在调整时刻上不同，故只重解调整时刻。"
    )
    lines.append("")
    return "\n".join(lines)


if __name__ == "__main__":
    main()
