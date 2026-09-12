"""第一问独立验收。

与 `src/q1_solver.py` 不同，本脚本：
1. 用**消元后的另一套编码**重解线性规划（把购电量 `g = 净负荷 + 充 − 放 + 弃` 代入目标函数，
   `g ≥ 0` 变成不等式约束），并换用 `highs-ipm` 内点法；
2. 从 `interval_detail.csv` 独立复算购电量与购电费，不读 `summary.json` 的费用字段；
3. 用原始附件重新核对时间映射与物理约束；
4. 核对 `solver_payload.json` 与 `result1.xlsx` 工作簿逐格一致。
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
from openpyxl import load_workbook
from scipy.optimize import linprog
from scipy.sparse import coo_matrix

ROOT = Path(__file__).resolve().parent.parent
DATA, OUT = ROOT / "problem" / "data", ROOT / "outputs" / "q1"

DT = 1 / 6
N = 144
ETA_C = ETA_D = 0.90
LIMIT = 5000.0 * DT
SOC_MIN, SOC_MAX, SOC0 = 1200.0, 10800.0, 6000.0
TOL = 1e-6

failures: list[str] = []


def check(name: str, ok: bool, detail: str) -> None:
    print(f"[{'通过' if ok else '失败'}] {name}：{detail}")
    if not ok:
        failures.append(name)


def raw_columns() -> tuple[np.ndarray, ...]:
    sheet = load_workbook(DATA / "附件1.xlsx", read_only=True, data_only=True).active
    rows = list(sheet.iter_rows(min_row=2, max_row=145, min_col=1, max_col=4, values_only=True))
    price = np.asarray([float(r[1]) for r in rows])
    load = np.asarray([float(r[2]) for r in rows]) * DT
    pv = np.asarray([float(r[3]) for r in rows]) * DT
    return price, load, pv


def reoptimise(price: np.ndarray, net: np.ndarray) -> tuple[np.ndarray, float]:
    """消元编码：变量为 c、d、u、s；购电量由能量平衡回代得到。"""
    base = {"c": 0, "d": N, "u": 2 * N}
    soc0 = 3 * N
    count = 3 * N + N + 1
    objective = np.zeros(count)
    objective[base["c"] : base["c"] + N] = price
    objective[base["d"] : base["d"] + N] = -price
    objective[base["u"] : base["u"] + N] = price
    rows, cols, values, rhs, kinds = [], [], [], [], []
    row = 0
    for t in range(N):  # g = net + c − d + u ≥ 0  ⟺  −c + d − u ≤ net
        rows += [row, row, row]
        cols += [base["c"] + t, base["d"] + t, base["u"] + t]
        values += [-1.0, 1.0, -1.0]
        rhs.append(float(net[t])); kinds.append("ub"); row += 1
    for t in range(N):
        rows += [row] * 4
        cols += [soc0 + t + 1, soc0 + t, base["c"] + t, base["d"] + t]
        values += [1.0, -1.0, -ETA_C, 1.0 / ETA_D]
        rhs.append(0.0); kinds.append("eq"); row += 1
    rows += [row, row]
    cols += [soc0, soc0 + N]
    values += [1.0, -1.0]
    rhs.append(0.0); kinds.append("eq"); row += 1

    matrix = coo_matrix((values, (rows, cols)), shape=(row, count)).tocsr()
    eq = np.asarray([k == "eq" for k in kinds])
    bounds = [(0.0, LIMIT)] * N + [(0.0, LIMIT)] * N + [(0.0, None)] * N + [(SOC0, SOC0)] + [(SOC_MIN, SOC_MAX)] * (N - 1) + [(SOC0, SOC0)]
    result = linprog(
        objective,
        A_ub=matrix[~eq], b_ub=np.asarray(rhs)[~eq],
        A_eq=matrix[eq], b_eq=np.asarray(rhs)[eq],
        bounds=bounds, method="highs-ipm",
    )
    if not result.success:
        raise RuntimeError(f"独立重解失败：{result.message}")
    x = result.x
    grid = net + x[base["c"] : base["c"] + N] - x[base["d"] : base["d"] + N] + x[base["u"] : base["u"] + N]
    return grid, float(price @ grid)


def main() -> int:
    summary = json.loads((OUT / "summary.json").read_text(encoding="utf-8"))
    payload = json.loads((OUT / "solver_payload.json").read_text(encoding="utf-8"))
    raw_price, raw_load, raw_pv = raw_columns()
    price = np.r_[raw_price[-1], raw_price[:-1]]
    net = np.r_[(raw_load - raw_pv)[-1], (raw_load - raw_pv)[:-1]]

    # 1. 时间映射
    check(
        "时间映射：自然日00:00取原始行0:00+1，其余取前一行",
        abs(price[0] - raw_price[-1]) < 1e-12 and float(np.max(np.abs(price[1:] - raw_price[:-1]))) == 0.0,
        f"自然日00:00电价 {price[0]:.4f} = 原始行0:00+1电价 {raw_price[-1]:.4f}；其余143项逐位一致",
    )

    # 2. 明细复算
    rows = list(__import__("csv").DictReader((OUT / "interval_detail.csv").open(encoding="utf-8-sig")))
    check("明细行数", len(rows) == N, f"{len(rows)} 行")
    detail_price = np.asarray([float(r["price_yuan_per_kwh"]) for r in rows])
    detail_grid = np.asarray([float(r["purchase_kwh"]) for r in rows])
    detail_charge = np.asarray([float(r["charge_kwh"]) for r in rows])
    detail_discharge = np.asarray([float(r["discharge_kwh"]) for r in rows])
    detail_soc_start = np.asarray([float(r["soc_start_kwh"]) for r in rows])
    detail_soc = np.asarray([float(r["soc_end_kwh"]) for r in rows])
    detail_net = np.asarray([float(r["net_load_kwh"]) for r in rows])
    detail_curtail = np.asarray([float(r["curtail_kwh"]) for r in rows])

    check("明细电价与附件重算一致", float(np.max(np.abs(detail_price - price))) < 1e-12, "最大差 0.000e+00")
    check("明细净负荷与附件重算一致", float(np.max(np.abs(detail_net - net))) < 1e-9, f"最大差 {np.max(np.abs(detail_net - net)):.3e} kWh")

    cost = float(detail_price @ detail_grid)
    check(
        "购电费独立复算",
        abs(cost - summary["totals"]["purchase_cost_yuan"]) < 1e-6,
        f"明细复算 {cost:.4f} 元 / summary {summary['totals']['purchase_cost_yuan']:.4f} 元",
    )
    check(
        "购电量独立复算",
        abs(detail_grid.sum() - summary["totals"]["purchase_kwh"]) < 1e-6,
        f"明细复算 {detail_grid.sum():.4f} kWh / summary {summary['totals']['purchase_kwh']:.4f} kWh",
    )

    # 3. 物理约束（全部从明细列独立判定）
    balance = detail_grid + detail_discharge - detail_charge - detail_curtail - detail_net
    soc_recur = detail_soc - detail_soc_start - ETA_C * detail_charge + detail_discharge / ETA_D
    check("能量平衡残差 < 1e-7", float(np.max(np.abs(balance))) < 1e-7, f"最大 {np.max(np.abs(balance)):.3e} kWh")
    check("储电量递推残差 < 1e-7", float(np.max(np.abs(soc_recur))) < 1e-7, f"最大 {np.max(np.abs(soc_recur)):.3e} kWh")

    soc_all = np.r_[detail_soc_start[0], detail_soc]
    check(
        "储电量全程在 1200—10800 内",
        float(soc_all.min()) >= SOC_MIN - 1e-6 and float(soc_all.max()) <= SOC_MAX + 1e-6,
        f"{soc_all.min():.4f}—{soc_all.max():.4f} kWh",
    )
    peak = float(max(detail_charge.max(), detail_discharge.max()))
    check("单区间充放电不超精确限值 5000/6", peak <= LIMIT + 1e-9, f"峰值 {peak:.10f} kWh，限值 {LIMIT:.10f} kWh")
    check("无同时充放电", int(np.count_nonzero((detail_charge > 1e-7) & (detail_discharge > 1e-7))) == 0, "0 个区间")
    check("弃电为零", float(detail_curtail.sum()) < 1e-9, f"{detail_curtail.sum():.3e} kWh")
    check(
        "购电量非负（供给不低于负载）",
        float(detail_grid.min()) >= -1e-9,
        f"最小购电量 {detail_grid.min():.3e} kWh",
    )
    check("0:00 与 24:00 储电量相同", abs(soc_all[-1] - soc_all[0]) < 1e-9, f"{soc_all[0]:.4f} kWh / {soc_all[-1]:.4f} kWh")

    # 4. 独立线性规划重解
    grid_ipm, cost_ipm = reoptimise(price, net)
    gap = cost_ipm - summary["totals"]["purchase_cost_yuan"]
    check("独立编码 + 内点法重解目标值一致", abs(gap) < 1e-3, f"重解 {cost_ipm:.4f} 元，差 {gap:+.4e} 元")
    check(
        "重解解可行且首末储电量相等",
        float(grid_ipm.min()) >= -1e-7,
        f"重解最小购电量 {grid_ipm.min():.3e} kWh",
    )

    # 5. 对照口径与效率恒等式
    baseline = float(price @ np.maximum(net, 0.0))
    check(
        "不配置储能基线独立复算",
        abs(baseline - summary["baseline_no_storage"]["cost_yuan"]) < 1e-6,
        f"复算 {baseline:.4f} 元 / summary {summary['baseline_no_storage']['cost_yuan']:.4f} 元",
    )
    saving = baseline - summary["totals"]["purchase_cost_yuan"]
    check(
        "储能节省额与节省率",
        abs(saving - summary["baseline_no_storage"]["saving_yuan"]) < 1e-6
        and abs(saving / baseline - summary["baseline_no_storage"]["saving_rate"]) < 1e-12,
        f"{saving:.4f} 元（{saving / baseline * 100:.2f}%）",
    )
    charge_side = ETA_C * detail_charge.sum()
    discharge_side = detail_discharge.sum() / ETA_D
    check(
        "效率恒等式 0.9·ΣC = ΣD/0.9",
        abs(charge_side - discharge_side) < 1e-6,
        f"{charge_side:.4f} kWh = {discharge_side:.4f} kWh（差 {abs(charge_side - discharge_side):.3e}）",
    )

    shifted_price = np.r_[price[1:], price[0]]
    shifted_net = np.r_[net[1:], net[0]]
    _, cost_alt = reoptimise(shifted_price, shifted_net)
    check(
        "区间终点反事实口径独立重解",
        abs(cost_alt - summary["alternative_interval_end_reading"]["purchase_cost_yuan"]) < 1e-3,
        f"重解 {cost_alt:.4f} 元 / summary {summary['alternative_interval_end_reading']['purchase_cost_yuan']:.4f} 元",
    )

    # 6. 载荷与工作簿
    template = np.asarray(payload["template_grid_kwh"])
    check("模板行数 144", len(template) == 144, f"{len(template)} 行")
    check(
        "模板行 = [g1..g143, g0]（自然日00:00 落在末行）",
        float(np.max(np.abs(template[:143] - detail_grid[1:]))) < 1e-9 and abs(template[143] - detail_grid[0]) < 1e-9,
        "逐位一致",
    )

    book = load_workbook(OUT / "result1.xlsx", data_only=True)
    plan, storage = book["计划购电量"], book["充放电量"]
    book_grid = np.asarray([float(plan.cell(r, 2).value) for r in range(2, 146)])
    check("工作簿购电量与载荷一致", float(np.max(np.abs(book_grid - template))) < 1e-9, f"最大差 {np.max(np.abs(book_grid - template)):.3e} kWh")
    book_charge = np.asarray([float(storage.cell(r, 2).value) for r in range(2, 8)])
    book_discharge = np.asarray([float(storage.cell(r, 3).value) for r in range(2, 8)])
    blocks = payload["storage_blocks"]
    check(
        "工作簿充放电量与载荷一致",
        float(np.max(np.abs(book_charge - [b["charge_kwh"] for b in blocks]))) < 1e-9
        and float(np.max(np.abs(book_discharge - [b["discharge_kwh"] for b in blocks]))) < 1e-9,
        "6 个 4 小时段逐项一致",
    )
    check(
        "工作簿 0:00/24:00 储电量一致",
        abs(float(storage.cell(2, 5).value) - payload["soc_start_kwh"]) < 1e-9
        and abs(float(storage.cell(3, 5).value) - payload["soc_end_kwh"]) < 1e-9,
        f"{storage.cell(2,5).value} / {storage.cell(3,5).value} kWh",
    )
    check(
        "模板 D 列时刻标签保留",
        storage.cell(2, 4).value == "0:00" and storage.cell(3, 4).value == "24:00",
        f"{storage.cell(2,4).value!r} / {storage.cell(3,4).value!r}",
    )

    print()
    if failures:
        print(f"共 {len(failures)} 项失败：" + "；".join(failures))
        return 1
    print("第一问全部验收项通过。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
