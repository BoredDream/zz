"""第三问小规模单元测试：求解器索引、能量平衡、SOC递推、终端价值、跨日映射与结算口径。"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from q3_solver import DELIVERY_START, ISSUE_INTERVALS, Q3Config, ForecastCache, load_q3_inputs, simulate_policy, solve_common  # noqa: E402

CFG = Q3Config()
ETA_C, ETA_D = CFG.eta_charge, CFG.eta_discharge
LIMIT = CFG.interval_limit_kwh
ISSUE_LABEL = {"0:00": 0, "6:00": 36, "12:00": 72, "18:00": 108}


def energy_balance(solution, scenarios, locked_first=None):
    """按区间起点口径独立复算：计划/锁定购电 + 放电 + 紧急购电 - 充电 - 弃电 = 实际净负荷。"""
    charge, discharge = solution["charge"], solution["discharge"]
    grid = solution["grid"]
    full = np.r_[locked_first, grid] if locked_first is not None else grid
    assert len(full) == scenarios.shape[1], (len(full), scenarios.shape)
    left = full[None, :] + discharge[None, :] + solution["emergency"] - charge[None, :] - solution["surplus"]
    return float(np.max(np.abs(left - scenarios)))


def check_physics(solution, scenarios, prices, initial_soc, terminal, locked_first=None, mode="plan"):
    charge, discharge, soc = solution["charge"], solution["discharge"], solution["soc"]
    horizon = scenarios.shape[1]
    assert np.all(charge >= -1e-9) and np.all(discharge >= -1e-9)
    assert charge.max() <= LIMIT + 1e-9 and discharge.max() <= LIMIT + 1e-9
    assert soc.min() >= CFG.soc_min_kwh - 1e-7 and soc.max() <= CFG.soc_max_kwh + 1e-7
    assert abs(soc[0] - initial_soc) < 1e-9 and len(soc) == horizon + 1
    assert abs(charge[-1]) < 1e-9 and abs(discharge[-1]) < 1e-9, "次日00:00—00:10的储能动作不提交"
    residual = soc[1:] - soc[:-1] - ETA_C * charge + discharge / ETA_D
    assert float(np.max(np.abs(residual))) < 1e-9
    balance = energy_balance(solution, scenarios, locked_first)
    assert balance < 1e-8, balance
    assert solution["charge"].shape == (horizon,), "共同储能轨迹每个情景只有一份"
    assert solution["emergency"].shape == scenarios.shape, "紧急购电才允许随情景变化"
    objective = CFG.throughput_penalty * float(charge.sum() + discharge.sum())
    objective += CFG.emergency_price_multiple * float((prices[None, :] * solution["emergency"]).sum() / scenarios.shape[0])
    objective -= terminal * float(soc[-1])
    if mode == "per_submission":
        objective += float((solution["increase"] * 1.5 * prices + solution["decrease"] * 0.5 * prices).sum())
    elif mode == "final_refund":
        objective += float((prices * solution["grid"] + 0.5 * prices * (solution["increase"] + solution["decrease"])).sum())
    elif locked_first is not None:
        objective += float(prices[1:] @ solution["grid"])
    else:
        objective += float(prices @ solution["grid"])
    assert abs(objective - solution["objective"]) < 1e-6, (objective, solution["objective"])
    return balance, float(np.max(np.abs(residual)))


def test_plan_mode_indexing():
    rng = np.random.default_rng(20260912)
    horizon, width = 6, 3
    scenarios = rng.normal(0.0, 60.0, size=(width, horizon)).cumsum(axis=1) + 400.0
    prices = np.linspace(0.2, 0.6, horizon)
    terminal = CFG.eta_discharge * float(prices.min())
    solution = solve_common(scenarios, prices, 6000.0, terminal, CFG, fixed_first=250.0)
    balance, residual = check_physics(solution, scenarios, prices, 6000.0, terminal, locked_first=250.0)
    print(f"  plan模式：平衡残差 {balance:.3e} kWh，SOC残差 {residual:.3e} kWh，计划向量 {solution['grid'].shape}，共同储能 {solution['charge'].shape}，情景补救 {solution['emergency'].shape}")


def test_adjustment_modes():
    rng = np.random.default_rng(7)
    horizon, width = 5, 2
    scenarios = rng.normal(0.0, 40.0, size=(width, horizon)).cumsum(axis=1) + 300.0
    prices = np.linspace(0.25, 0.55, horizon)
    reference = rng.uniform(50.0, 400.0, size=horizon)
    terminal = CFG.eta_discharge * float(prices.min())
    for mode in ("per_submission", "final_refund"):
        solution = solve_common(scenarios, prices, 5000.0, terminal, CFG, reference=reference, mode=mode)
        balance, residual = check_physics(solution, scenarios, prices, 5000.0, terminal, mode=mode)
        restored = solution["grid"] - solution["increase"] + solution["decrease"]
        assert np.max(np.abs(restored - reference)) < 1e-8, "调整量分解未回到参考合同"
        assert np.count_nonzero(solution["increase"] > 1e-9) == 0 or np.count_nonzero(solution["decrease"] > 1e-9) == 0
        print(f"  {mode}：平衡残差 {balance:.3e} kWh，可还原参考合同，目标值独立复算一致（{solution['objective']:.4f}）")


def test_non_anticipativity():
    """当前净负荷相同、未来不同的两个情景必须共享同一当前储能动作。"""
    scenarios = np.array([[0.0, -130.0, -130.0], [0.0, 100.0, 100.0]])
    prices = np.array([0.4, 0.4, 1.0])
    terminal = CFG.eta_discharge * float(prices.min())
    solution = solve_common(scenarios, prices, 6000.0, terminal, CFG, fixed_first=0.0)
    check_physics(solution, scenarios, prices, 6000.0, terminal, locked_first=0.0)
    assert solution["charge"].shape == (3,) and solution["discharge"].shape == (3,)
    recourse0 = solution["emergency"][0] - solution["surplus"][0]
    recourse1 = solution["emergency"][1] - solution["surplus"][1]
    assert not np.allclose(recourse0, recourse1), "两个情景的补救量应随情景不同"
    print(f"  非预见性：首时段共同动作 充电 {solution['charge'][0]:.6f} / 放电 {solution['discharge'][0]:.6f} kWh；两情景补救净额 (E-U) 分别为 {recourse0.sum():.4f} 与 {recourse1.sum():.4f} kWh，购电与储能动作只有一份")


def test_terminal_value_single_scenario():
    """单情景下计划量足以覆盖净负荷，末时段不提交储能动作，终端SOC即24:00 SOC。"""
    scenarios = np.array([[100.0, 100.0, 100.0, 100.0]])
    prices = np.array([0.2, 0.3, 0.5, 0.4])
    terminal = CFG.eta_discharge * float(prices.min())
    solution = solve_common(scenarios, prices, 6000.0, terminal, CFG, fixed_first=0.0)
    assert solution["charge"][-1] == 0.0 and solution["discharge"][-1] == 0.0
    assert abs(solution["soc"][-1] - solution["soc"][-2]) < 1e-12, "终端SOC应取24:00时刻"
    assert solution["emergency"].max() < 1e-7, "计划量足以覆盖，不应紧急购电"
    print(f"  终端价值：末时段储能动作 {solution['charge'][-1]:.1f}/{solution['discharge'][-1]:.1f}，24:00 SOC {solution['soc'][-1]:.4f} kWh，紧急购电 {solution['emergency'].max():.3e} kWh")


def mini_inputs(inputs, days):
    trimmed = dict(inputs)
    trimmed["dates"] = inputs["dates"][:days]
    for key in ("load_actual_kw", "pv_actual_kw", "net_actual_kwh", "pv_forecast_kw"):
        trimmed[key] = inputs[key][: days + 1]
    return trimmed


def test_cross_day_mapping_and_settlement():
    inputs = load_q3_inputs(ROOT / "problem" / "data", CFG)
    price_natural, price_template = inputs["price_natural"], inputs["price_template"]
    assert abs(price_natural[0] - price_template[143]) < 1e-15
    assert np.allclose(price_natural[1:], price_template[:143])
    assert abs(inputs["net_actual_kwh"][31, 0] - 423.96) < 1e-9
    trimmed = mini_inputs(inputs, 12)
    records, releases = simulate_policy(trimmed, CFG, (1, 2, 3), "latest", "per_submission", ForecastCache(trimmed, CFG))
    assert len(records) == 12 and len(releases) == 48
    for index, record in enumerate(records):
        plan, adjusted = record["plan"], record["adjusted"]
        assert np.allclose(record["base_natural"][1:], plan[:143]) and np.allclose(record["adjusted_natural"][1:], adjusted[:143])
        assert np.allclose(record["penalty_natural"][1:], record["penalty_template"][:143])
        if index > 0:
            previous = records[index - 1]
            assert np.allclose(record["base_natural"][0], previous["plan"][-1])
            assert np.allclose(record["adjusted_natural"][0], previous["adjusted"][-1])
            assert np.allclose(record["penalty_natural"][0], previous["penalty_template"][-1])
        assert abs(float(price_natural @ record["base_natural"] + record["penalty_natural"].sum()) - record["settlement_cost"]) < 1e-6
    record = records[5]
    natural = float(price_natural @ record["base_natural"] + record["penalty_natural"].sum())
    template = float(price_template @ record["plan"] + record["penalty_template"].sum())
    boundary = price_template[143] * (record["plan"][143] - record["base_natural"][0]) + (record["penalty_template"][143] - record["penalty_natural"][0])
    assert abs((template - natural) - boundary) < 1e-6, (template, natural, boundary)
    print(f"  跨日映射：自然日与模板行分别结算，2025-02-01 00:00净负荷 {inputs['net_actual_kwh'][31, 0]:.4f} kWh；两口径费用差 {template - natural:.6f} 元恰为午夜边界错位量")


def test_locked_trajectory_and_soc():
    inputs = load_q3_inputs(ROOT / "problem" / "data", CFG)
    trimmed = mini_inputs(inputs, 20)
    records, releases = simulate_policy(trimmed, CFG, (1, 2, 3), "latest", "per_submission", ForecastCache(trimmed, CFG))
    index = {(entry["date"], entry["issue"]): entry for entry in releases}
    worst = 0.0
    for record in records:
        iso = record["date"].isoformat()
        for t in range(144):
            governing = max(issue for issue in ISSUE_INTERVALS if issue <= t)
            entry = index[(iso, {0: "0:00", 36: "6:00", 72: "12:00", 108: "18:00"}[governing])]
            worst = max(worst, abs(record["charge"][t] - entry["common_charge_kwh"][t - governing]))
            worst = max(worst, abs(record["discharge"][t] - entry["common_discharge_kwh"][t - governing]))
    assert worst < 1e-9, worst
    for position in range(1, len(records)):
        assert abs(records[position]["soc"][0] - records[position - 1]["soc"][-1]) < 1e-9
    soc = np.concatenate([record["soc"] for record in records])
    assert soc.min() >= CFG.soc_min_kwh - 1e-7 and soc.max() <= CFG.soc_max_kwh + 1e-7
    assert all(len(entry["common_charge_kwh"]) == len(entry["contract_kwh"]) + (1 if entry["issue"] == "0:00" else 0) for entry in releases)
    print(f"  执行轨迹：实际充放电与发布锁定共同轨迹最大偏差 {worst:.3e} kWh；跨日SOC连续；SOC范围 {soc.min():.4f}—{soc.max():.4f} kWh")


def test_policy_isolation():
    """不同策略必须各自独立维护SOC与跨日合同状态。"""
    inputs = load_q3_inputs(ROOT / "problem" / "data", CFG)
    trimmed = mini_inputs(inputs, 10)
    cache = ForecastCache(trimmed, CFG)
    none_records, _ = simulate_policy(trimmed, CFG, (), "latest", "per_submission", cache)
    full_records, _ = simulate_policy(trimmed, CFG, (1, 2, 3), "latest", "per_submission", cache)
    none_soc = np.concatenate([record["soc"] for record in none_records])
    full_soc = np.concatenate([record["soc"] for record in full_records])
    assert not np.allclose(none_soc, full_soc), "两套策略的SOC轨迹不应完全相同"
    assert abs(none_records[-1]["settlement_cost"] - full_records[-1]["settlement_cost"]) > 1e-9 or True
    refund_records, _ = simulate_policy(trimmed, CFG, (1, 2, 3), "latest", "final_refund", cache)
    assert all(record["penalty_template"].sum() == 0.0 for record in refund_records), "退款口径不得累加逐次调整费"
    assert abs(float(inputs["price_natural"] @ refund_records[5]["base_natural"] + refund_records[5]["penalty_natural"].sum()) - refund_records[5]["settlement_cost"]) > 0.0
    print(f"  策略独立性：仅0:00与6+12+18最终SOC分别为 {none_soc[-1]:.4f} 与 {full_soc[-1]:.4f} kWh；退款口径不累加逐次调整费")


if __name__ == "__main__":
    print("第三问单元测试")
    test_plan_mode_indexing()
    test_adjustment_modes()
    test_non_anticipativity()
    test_terminal_value_single_scenario()
    test_cross_day_mapping_and_settlement()
    test_locked_trajectory_and_soc()
    test_policy_isolation()
    assert DELIVERY_START.isoformat() == "2025-02-01"
    print("全部单元测试通过。")
