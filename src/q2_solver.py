from __future__ import annotations

import argparse
import csv
import hashlib
import json
from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path
from typing import Any

import numpy as np
from openpyxl import load_workbook
from scipy.optimize import linprog
from scipy.sparse import coo_matrix, csr_matrix


@dataclass(frozen=True)
class Config:
    dt_hours: float = 1 / 6
    intervals_per_day: int = 144
    horizon_days: int = 2
    eta_charge: float = 0.90
    eta_discharge: float = 0.90
    power_limit_kw: float = 5000.0
    soc_min_kwh: float = 1200.0
    soc_max_kwh: float = 10800.0
    initial_soc_kwh: float = 6000.0
    emergency_price_multiple: float = 5.0
    residual_window_days: int = 28
    planning_quantile: float = 0.80

    @property
    def interval_limit_kwh(self) -> float:
        return self.power_limit_kw * self.dt_hours

    @property
    def horizon_intervals(self) -> int:
        return self.intervals_per_day * self.horizon_days


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def load_inputs(data_dir: Path, cfg: Config) -> dict[str, Any]:
    price_path = data_dir / "附件1.xlsx"
    actual_path = data_dir / "附件2.xlsx"

    price_sheet = load_workbook(price_path, read_only=True, data_only=True).active
    price_rows = list(
        price_sheet.iter_rows(min_row=2, max_row=145, min_col=1, max_col=4, values_only=True)
    )
    if len(price_rows) != cfg.intervals_per_day:
        raise ValueError(f"附件1应有144个数据时段，实际为{len(price_rows)}")

    raw_price = np.array([float(row[1]) for row in price_rows], dtype=float)
    raw_q1_net = np.array(
        [(float(row[2]) - float(row[3])) * cfg.dt_hours for row in price_rows],
        dtype=float,
    )

    actual_wb = load_workbook(actual_path, read_only=True, data_only=True)
    load_sheet = actual_wb["小区负载"]
    pv_sheet = actual_wb["光伏发电实际功率"]
    load_rows = list(
        load_sheet.iter_rows(min_row=2, max_row=366, min_col=1, max_col=145, values_only=True)
    )
    pv_rows = list(
        pv_sheet.iter_rows(min_row=2, max_row=366, min_col=1, max_col=145, values_only=True)
    )
    if len(load_rows) != 365 or len(pv_rows) != 365:
        raise ValueError("附件2应分别包含365天负荷和光伏数据")

    dates = [row[0].date() for row in load_rows]
    if dates[0] != date(2025, 1, 1) or dates[-1] != date(2025, 12, 31):
        raise ValueError("附件2日期范围不是2025-01-01至2025-12-31")

    load_raw = np.array(
        [[float(value) * cfg.dt_hours for value in row[1:]] for row in load_rows],
        dtype=float,
    )
    pv_raw = np.array(
        [[float(value) * cfg.dt_hours for value in row[1:]] for row in pv_rows],
        dtype=float,
    )

    # 原始列为0:10,...,23:50,0:00+1。区间起点口径下，自然日数组
    # 必须按0:00,0:10,...,23:50排列，因此将上一原始行末端的0:00
    # 置于自然日首位。题目给定每日固定价格，价格同样按此顺序重排。
    natural_order = np.r_[cfg.intervals_per_day - 1, np.arange(cfg.intervals_per_day - 1)]
    return {
        "dates": dates,
        "price_natural": raw_price[natural_order],
        "price_template": raw_price,
        "net_actual": (load_raw - pv_raw)[:, natural_order],
        "cold_start_net": raw_q1_net[natural_order],
        "input_hashes": {
            "附件1.xlsx": file_sha256(price_path),
            "附件2.xlsx": file_sha256(actual_path),
        },
    }


def point_forecast(
    net_actual: np.ndarray,
    cold_start_net: np.ndarray,
    target_index: int,
    cutoff_index: int,
) -> np.ndarray:
    """Forecast a target day using only rows with index < cutoff_index."""
    if cutoff_index <= 0:
        return cold_start_net.copy()

    origin = date(2025, 1, 1)
    target_weekday = (origin + timedelta(days=target_index)).weekday()
    past = np.arange(cutoff_index)
    same_weekday = [
        int(i)
        for i in past
        if (origin + timedelta(days=int(i))).weekday() == target_weekday
    ][-4:]
    recent = past[-7:]

    components: list[np.ndarray] = []
    weights: list[float] = []
    if same_weekday:
        components.append(np.median(net_actual[same_weekday], axis=0))
        weights.append(0.70)
    if len(recent):
        components.append(np.median(net_actual[recent], axis=0))
        weights.append(0.30 if same_weekday else 1.0)

    normalized = np.asarray(weights, dtype=float)
    normalized /= normalized.sum()
    return sum(weight * component for weight, component in zip(normalized, components))


def build_balance_matrix(cfg: Config) -> csr_matrix:
    horizon = cfg.horizon_intervals
    soc_offset = 4 * horizon
    rows: list[int] = []
    cols: list[int] = []
    values: list[float] = []

    for t in range(horizon):
        # G + D - C - W = planned net load.
        for column, value in (
            (t, 1.0),
            (horizon + t, -1.0),
            (2 * horizon + t, 1.0),
            (3 * horizon + t, -1.0),
        ):
            rows.append(t)
            cols.append(column)
            values.append(value)

        # S[t+1] - S[t] - eta_c*C + D/eta_d = 0.
        row = horizon + t
        for column, value in (
            (soc_offset + t + 1, 1.0),
            (soc_offset + t, -1.0),
            (horizon + t, -cfg.eta_charge),
            (2 * horizon + t, 1.0 / cfg.eta_discharge),
        ):
            rows.append(row)
            cols.append(column)
            values.append(value)

    rows.extend([2 * horizon, 2 * horizon + 1])
    cols.extend([soc_offset, soc_offset + horizon])
    values.extend([1.0, 1.0])
    return coo_matrix(
        (values, (rows, cols)),
        shape=(2 * horizon + 2, 5 * horizon + 1),
    ).tocsr()


def solve_horizon(
    planned_net: np.ndarray,
    price_natural: np.ndarray,
    initial_soc: float,
    matrix: csr_matrix,
    cfg: Config,
) -> dict[str, np.ndarray]:
    horizon = cfg.horizon_intervals
    objective = np.zeros(5 * horizon + 1, dtype=float)
    objective[:horizon] = np.tile(price_natural, cfg.horizon_days)
    objective[horizon : 3 * horizon] = 1e-9
    rhs = np.r_[planned_net, np.zeros(horizon), initial_soc, initial_soc]

    bounds = (
        [(0.0, None)] * horizon
        + [(0.0, cfg.interval_limit_kwh)] * (2 * horizon)
        + [(0.0, None)] * horizon
        + [(cfg.soc_min_kwh, cfg.soc_max_kwh)] * (horizon + 1)
    )
    result = linprog(
        objective,
        A_eq=matrix,
        b_eq=rhs,
        bounds=bounds,
        method="highs",
    )
    if not result.success:
        raise RuntimeError(f"线性规划失败：{result.message}")

    x = result.x
    return {
        "grid": x[:horizon],
        "charge": x[horizon : 2 * horizon],
        "discharge": x[2 * horizon : 3 * horizon],
        "planned_surplus": x[3 * horizon : 4 * horizon],
        "soc": x[4 * horizon :],
    }


def clock(index: int) -> str:
    if index == 144:
        return "24:00"
    minutes = index * 10
    return f"{minutes // 60:02d}:{minutes % 60:02d}"


def emergency_segments(values: np.ndarray, tolerance: float = 1e-7) -> list[dict[str, Any]]:
    segments: list[dict[str, Any]] = []
    start: int | None = None
    extended = np.r_[values, 0.0]
    for index, value in enumerate(extended):
        if value > tolerance and start is None:
            start = index
        elif value <= tolerance and start is not None:
            segments.append(
                {
                    "time_range": f"{clock(start)}-{clock(index)}",
                    "energy_kwh": float(values[start:index].sum()),
                }
            )
            start = None
    return segments


def make_planned_net(
    day_index: int,
    net_actual: np.ndarray,
    cold_start_net: np.ndarray,
    residuals: np.ndarray,
    cfg: Config,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    center_today = point_forecast(net_actual, cold_start_net, day_index, day_index)
    center_tomorrow = point_forecast(net_actual, cold_start_net, day_index + 1, day_index)
    available = residuals[max(0, day_index - cfg.residual_window_days) : day_index]
    if len(available):
        margin = np.quantile(available, cfg.planning_quantile, axis=0)
    else:
        margin = np.zeros(cfg.intervals_per_day)
    return (
        np.r_[center_today + margin, center_tomorrow + margin],
        center_today,
        margin,
    )


def simulate(inputs: dict[str, Any], cfg: Config) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    dates: list[date] = inputs["dates"]
    price = inputs["price_natural"]
    net_actual = inputs["net_actual"]
    cold_start_net = inputs["cold_start_net"]
    matrix = build_balance_matrix(cfg)

    residuals = np.array(
        [
            net_actual[index]
            - point_forecast(net_actual, cold_start_net, index, index)
            for index in range(len(dates))
        ]
    )

    records: list[dict[str, Any]] = []
    soc_now = cfg.initial_soc_kwh
    for day_index, current_date in enumerate(dates):
        planned_net, center_forecast, margin = make_planned_net(
            day_index, net_actual, cold_start_net, residuals, cfg
        )
        solution = solve_horizon(planned_net, price, soc_now, matrix, cfg)
        count = cfg.intervals_per_day
        grid = solution["grid"][:count]
        charge = solution["charge"][:count]
        discharge = solution["discharge"][:count]
        soc = solution["soc"][: count + 1]
        planned_supply = grid + discharge - charge
        emergency = np.maximum(net_actual[day_index] - planned_supply, 0.0)
        actual_surplus = np.maximum(planned_supply - net_actual[day_index], 0.0)

        records.append(
            {
                "date": current_date,
                "grid": grid,
                "charge": charge,
                "discharge": discharge,
                "soc": soc,
                "emergency": emergency,
                "actual_surplus": actual_surplus,
                "forecast": center_forecast,
                "planned_net": center_forecast + margin,
                "plan_cost": float(price @ grid),
                "emergency_cost": float(cfg.emergency_price_multiple * price @ emergency),
            }
        )
        soc_now = float(soc[-1])
        if (day_index + 1) % 50 == 0:
            print(f"已完成 {day_index + 1}/{len(dates)} 天")

    # 为绝对时间映射补算2026-01-01的0:00计划值，不读取2026年实际数据。
    next_planned_net, _, _ = make_planned_net(
        len(dates), net_actual, cold_start_net, residuals, cfg
    )
    next_solution = solve_horizon(next_planned_net, price, soc_now, matrix, cfg)
    extra = {
        "date": date(2026, 1, 1),
        "grid_zero": float(next_solution["grid"][0]),
    }
    return records, extra


def rounded_list(values: np.ndarray) -> list[float]:
    return [float(value) for value in values]


def assemble_outputs(
    records: list[dict[str, Any]],
    extra: dict[str, Any],
    inputs: dict[str, Any],
    cfg: Config,
) -> tuple[dict[str, Any], dict[str, Any], list[dict[str, Any]]]:
    start_date = date(2025, 2, 1)
    start_index = next(i for i, record in enumerate(records) if record["date"] == start_date)
    delivered = records[start_index:]
    price_natural = inputs["price_natural"]
    price_template = inputs["price_template"]

    max_balance_residual = 0.0
    max_soc_residual = 0.0
    max_interval_storage = 0.0
    simultaneous_intervals = 0
    interval_rows: list[dict[str, Any]] = []
    daily_rows: list[dict[str, Any]] = []
    payload_days: list[dict[str, Any]] = []

    for delivered_index, record in enumerate(delivered):
        original_index = start_index + delivered_index
        actual_net = inputs["net_actual"][original_index]
        balance = (
            record["grid"]
            + record["emergency"]
            + record["discharge"]
            - record["charge"]
            - record["actual_surplus"]
            - actual_net
        )
        soc_residual = (
            record["soc"][1:]
            - record["soc"][:-1]
            - cfg.eta_charge * record["charge"]
            + record["discharge"] / cfg.eta_discharge
        )
        max_balance_residual = max(max_balance_residual, float(np.max(np.abs(balance))))
        max_soc_residual = max(max_soc_residual, float(np.max(np.abs(soc_residual))))
        max_interval_storage = max(
            max_interval_storage,
            float(np.max(record["charge"])),
            float(np.max(record["discharge"])),
        )
        simultaneous_intervals += int(
            np.count_nonzero((record["charge"] > 1e-7) & (record["discharge"] > 1e-7))
        )

        next_grid_zero = (
            float(records[original_index + 1]["grid"][0])
            if original_index + 1 < len(records)
            else float(extra["grid_zero"])
        )
        template_grid = np.r_[record["grid"][1:], next_grid_zero]
        block_rows = []
        for block_start in range(0, 24, 4):
            section = slice(block_start * 6, (block_start + 4) * 6)
            block_rows.append(
                {
                    "time_range": f"{block_start}:00-{block_start + 4}:00",
                    "charge_kwh": float(record["charge"][section].sum()),
                    "discharge_kwh": float(record["discharge"][section].sum()),
                }
            )

        segments = emergency_segments(record["emergency"])
        payload_days.append(
            {
                "date": record["date"].isoformat(),
                "template_grid_kwh": rounded_list(template_grid),
                "template_grid_total_kwh": float(template_grid.sum()),
                "template_grid_cost_yuan": float(price_template @ template_grid),
                "natural_grid_total_kwh": float(record["grid"].sum()),
                "natural_grid_cost_yuan": float(record["plan_cost"]),
                "soc_start_kwh": float(record["soc"][0]),
                "soc_end_kwh": float(record["soc"][-1]),
                "storage_blocks": block_rows,
                "emergency_segments": segments,
                "emergency_total_kwh": float(record["emergency"].sum()),
                "emergency_cost_yuan": float(record["emergency_cost"]),
            }
        )

        daily_rows.append(
            {
                "date": record["date"].isoformat(),
                "planned_purchase_kwh": float(record["grid"].sum()),
                "planned_purchase_cost_yuan": float(record["plan_cost"]),
                "emergency_purchase_kwh": float(record["emergency"].sum()),
                "emergency_purchase_cost_yuan": float(record["emergency_cost"]),
                "total_cost_yuan": float(record["plan_cost"] + record["emergency_cost"]),
                "surplus_kwh": float(record["actual_surplus"].sum()),
                "soc_start_kwh": float(record["soc"][0]),
                "soc_end_kwh": float(record["soc"][-1]),
                "forecast_mae_kwh": float(np.mean(np.abs(actual_net - record["forecast"]))),
                "coverage_rate": float(np.mean(actual_net <= record["planned_net"] + 1e-9)),
            }
        )

        for t in range(cfg.intervals_per_day):
            interval_rows.append(
                {
                    "date": record["date"].isoformat(),
                    "time_start": clock(t),
                    "price_yuan_per_kwh": float(price_natural[t]),
                    "forecast_net_kwh": float(record["forecast"][t]),
                    "planned_net_quantile_kwh": float(record["planned_net"][t]),
                    "actual_net_kwh": float(actual_net[t]),
                    "planned_purchase_kwh": float(record["grid"][t]),
                    "charge_kwh": float(record["charge"][t]),
                    "discharge_kwh": float(record["discharge"][t]),
                    "soc_start_kwh": float(record["soc"][t]),
                    "soc_end_kwh": float(record["soc"][t + 1]),
                    "emergency_purchase_kwh": float(record["emergency"][t]),
                    "surplus_kwh": float(record["actual_surplus"][t]),
                    "planned_cost_yuan": float(price_natural[t] * record["grid"][t]),
                    "emergency_cost_yuan": float(
                        cfg.emergency_price_multiple * price_natural[t] * record["emergency"][t]
                    ),
                }
            )

    all_actual = np.concatenate(
        [inputs["net_actual"][start_index + i] for i in range(len(delivered))]
    )
    all_forecast = np.concatenate([record["forecast"] for record in delivered])
    all_planned_net = np.concatenate([record["planned_net"] for record in delivered])
    all_emergency = np.concatenate([record["emergency"] for record in delivered])
    all_surplus = np.concatenate([record["actual_surplus"] for record in delivered])
    all_soc = np.concatenate([record["soc"] for record in delivered])

    summary = {
        "model": "rolling_48h_empirical_quantile_lp",
        "time_convention": "interval_start_absolute_time",
        "forecast_information_rule": "only dates strictly before the planning date",
        "period": {"start": "2025-02-01", "end": "2025-12-31", "days": len(delivered)},
        "parameters": {
            "planning_quantile": cfg.planning_quantile,
            "residual_window_days": cfg.residual_window_days,
            "horizon_days": cfg.horizon_days,
            "emergency_price_multiple": cfg.emergency_price_multiple,
            "eta_charge": cfg.eta_charge,
            "eta_discharge": cfg.eta_discharge,
            "soc_min_kwh": cfg.soc_min_kwh,
            "soc_max_kwh": cfg.soc_max_kwh,
            "interval_storage_limit_kwh": cfg.interval_limit_kwh,
        },
        "totals": {
            "planned_purchase_kwh": float(sum(record["grid"].sum() for record in delivered)),
            "emergency_purchase_kwh": float(all_emergency.sum()),
            "surplus_kwh": float(all_surplus.sum()),
            "planned_purchase_cost_yuan": float(sum(record["plan_cost"] for record in delivered)),
            "emergency_purchase_cost_yuan": float(
                sum(record["emergency_cost"] for record in delivered)
            ),
            "total_cost_yuan": float(
                sum(record["plan_cost"] + record["emergency_cost"] for record in delivered)
            ),
            "emergency_intervals": int(np.count_nonzero(all_emergency > 1e-7)),
        },
        "forecast_metrics": {
            "mae_kwh_per_interval": float(np.mean(np.abs(all_actual - all_forecast))),
            "rmse_kwh_per_interval": float(np.sqrt(np.mean((all_actual - all_forecast) ** 2))),
            "realized_quantile_coverage": float(np.mean(all_actual <= all_planned_net + 1e-9)),
        },
        "checks": {
            "max_energy_balance_residual_kwh": max_balance_residual,
            "max_soc_residual_kwh": max_soc_residual,
            "soc_min_observed_kwh": float(all_soc.min()),
            "soc_max_observed_kwh": float(all_soc.max()),
            "max_interval_storage_energy_kwh": max_interval_storage,
            "simultaneous_charge_discharge_intervals": simultaneous_intervals,
            "cross_day_soc_continuity": all(
                abs(delivered[i]["soc"][-1] - delivered[i + 1]["soc"][0]) <= 1e-8
                for i in range(len(delivered) - 1)
            ),
        },
        "input_hashes_sha256": inputs["input_hashes"],
    }
    target_dates = {"2025-03-20", "2025-06-21", "2025-09-23", "2025-12-21"}
    summary["target_dates"] = {
        day["date"]: day for day in payload_days if day["date"] in target_dates
    }
    payload = {
        "metadata": {
            "time_convention": summary["time_convention"],
            "generated_from": ["附件1.xlsx", "附件2.xlsx"],
            "input_hashes_sha256": inputs["input_hashes"],
        },
        "days": payload_days,
    }
    return summary, payload, {"interval": interval_rows, "daily": daily_rows}


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    if not rows:
        raise ValueError(f"没有可写入的数据：{path}")
    with path.open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)


def fmt(value: float, digits: int = 4) -> str:
    return f"{value:,.{digits}f}"


def build_report(summary: dict[str, Any]) -> str:
    totals = summary["totals"]
    metrics = summary["forecast_metrics"]
    checks = summary["checks"]
    lines = [
        "# 第二问计算报告",
        "",
        "## 1. 结论",
        "",
        "本报告使用附件1固定电价和附件2真实负荷、光伏数据进行逐日滚动回测。每天0:00的计划仅使用此前历史数据；当日真实值仅用于紧急购电结算。",
        "",
        "| 指标 | 结果 |",
        "|---|---:|",
        f"| 计划购电量 | {fmt(totals['planned_purchase_kwh'])} kWh |",
        f"| 紧急购电量 | {fmt(totals['emergency_purchase_kwh'])} kWh |",
        f"| 计划购电费 | {fmt(totals['planned_purchase_cost_yuan'])} 元 |",
        f"| 紧急购电费 | {fmt(totals['emergency_purchase_cost_yuan'])} 元 |",
        f"| 总购电费 | {fmt(totals['total_cost_yuan'])} 元 |",
        f"| 紧急购电10分钟时段数 | {totals['emergency_intervals']:,} |",
        "",
        "## 2. 模型口径",
        "",
        "- 时间标签采用区间起点口径，按绝对时刻跨行映射。",
        "- 净负荷中心预测由最近4个同星期日中位数和最近7日中位数组合得到。",
        "- 最近28天滚动预测残差用于计算经验80%分位数。",
        "- 采用48小时滚动线性规划，每天只执行前24小时。",
        "- 充放电效率均为90%，SOC范围为1200—10800 kWh。",
        "",
        "## 3. 预测检验",
        "",
        "| 指标 | 结果 |",
        "|---|---:|",
        f"| 中心预测MAE | {fmt(metrics['mae_kwh_per_interval'])} kWh/10分钟 |",
        f"| 中心预测RMSE | {fmt(metrics['rmse_kwh_per_interval'])} kWh/10分钟 |",
        f"| 经验80%分位数实际覆盖率 | {metrics['realized_quantile_coverage']:.2%} |",
        "",
        "实际覆盖率低于理论80%，说明残差存在季节性漂移。可在后续敏感性分析中比较月份分组残差和动态分位数校准。",
        "",
        "## 4. 指定日期结果",
        "",
        "| 日期 | 全天计划购电量/kWh | 计划购电费/元 | 紧急购电量/kWh | 紧急购电费/元 | 0:00 SOC/kWh | 24:00 SOC/kWh |",
        "|---|---:|---:|---:|---:|---:|---:|",
    ]
    for day in summary["target_dates"].values():
        lines.append(
            f"| {day['date']} | {fmt(day['natural_grid_total_kwh'])} | "
            f"{fmt(day['natural_grid_cost_yuan'])} | {fmt(day['emergency_total_kwh'])} | "
            f"{fmt(day['emergency_cost_yuan'])} | {fmt(day['soc_start_kwh'])} | "
            f"{fmt(day['soc_end_kwh'])} |"
        )

    lines += [
        "",
        "### 紧急购电区间",
        "",
    ]
    for day in summary["target_dates"].values():
        lines.append(f"#### {day['date']}")
        lines.append("")
        if not day["emergency_segments"]:
            lines.append("无紧急购电。")
        else:
            lines.append("| 时间段 | 紧急购电量/kWh |")
            lines.append("|---|---:|")
            for segment in day["emergency_segments"]:
                lines.append(
                    f"| {segment['time_range']} | {fmt(segment['energy_kwh'])} |"
                )
        lines.append("")

    lines += [
        "## 5. 数值校验",
        "",
        "| 校验项 | 结果 |",
        "|---|---:|",
        f"| 最大电量平衡残差 | {checks['max_energy_balance_residual_kwh']:.3e} kWh |",
        f"| 最大SOC递推残差 | {checks['max_soc_residual_kwh']:.3e} kWh |",
        f"| 最低SOC | {fmt(checks['soc_min_observed_kwh'])} kWh |",
        f"| 最高SOC | {fmt(checks['soc_max_observed_kwh'])} kWh |",
        f"| 最大单时段充放电量 | {fmt(checks['max_interval_storage_energy_kwh'])} kWh |",
        f"| 同时充放电时段 | {checks['simultaneous_charge_discharge_intervals']} |",
        f"| 跨日SOC连续 | {'是' if checks['cross_day_soc_continuity'] else '否'} |",
        "",
        "## 6. 限制",
        "",
        "题目没有指定0:00负荷和光伏预测方法，因此本结果是一套可复现的建模答案，而不是唯一数值答案。结果工作簿中的计划购电表按官方模板时标填写；报告费用按自然日0:00—24:00统计。",
        "",
    ]
    return "\n".join(lines)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="求解微网赛题第二问")
    parser.add_argument("--data-dir", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    cfg = Config()
    args.output_dir.mkdir(parents=True, exist_ok=True)
    args.report.parent.mkdir(parents=True, exist_ok=True)

    inputs = load_inputs(args.data_dir.resolve(), cfg)
    records, extra = simulate(inputs, cfg)
    summary, payload, tables = assemble_outputs(records, extra, inputs, cfg)

    (args.output_dir / "summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    (args.output_dir / "solver_payload.json").write_text(
        json.dumps(payload, ensure_ascii=False), encoding="utf-8"
    )
    write_csv(args.output_dir / "daily_metrics.csv", tables["daily"])
    write_csv(args.output_dir / "interval_detail.csv", tables["interval"])
    args.report.write_text(build_report(summary), encoding="utf-8")

    print(json.dumps(summary["totals"], ensure_ascii=False, indent=2))
    print(f"报告：{args.report.resolve()}")
    print(f"审计结果：{args.output_dir.resolve()}")


if __name__ == "__main__":
    main()

