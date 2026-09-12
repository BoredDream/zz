"""标定 HiGHS 求解耗时，据此定情景数 Ω 与实时层方案。"""
from __future__ import annotations

import time

import numpy as np
from scipy.optimize import linprog
from scipy.sparse import coo_matrix

ETA = 0.90
LIMIT = 5000.0 / 6.0
SOC_MIN, SOC_MAX = 1200.0, 10800.0
P = np.full(144, 0.5)
P[72:108] = 1.0
P_EXT = np.r_[P, P[0]]
NODE = 145


def build_two_stage(width: int, seed: int = 0):
    """阶段0两阶段SAA：x(144) 第一阶段；每情景 q/α/β/c/g/z/u/S 第二阶段。"""
    rng = np.random.default_rng(seed)
    scen = np.r_[600.0 + 400 * np.sin(np.arange(144) / 24), 600.0][None, :] + rng.normal(0, 120, size=(width, NODE))
    nx, node = 144, NODE
    off_q, off_ab, off_cg, off_z, off_u, off_s = 0, node, node + 2 * (node - 1), node + 2 * (node - 1) + 2 * node, 0, 0
    off_z = off_cg + 2 * node
    off_u = off_z + node
    off_s = off_u + node
    per = off_s + node + 1
    size = nx + width * per
    obj = np.zeros(size)
    rows, cols, vals, rhs = [], [], [], []
    row = 0
    for w in range(width):
        b = nx + w * per
        qb, ab, cb, gb, zb, ub, sb = b + off_q, b + off_ab, b + off_cg, b + off_cg + node, b + off_z, b + off_u, b + off_s
        for h in range(1, node):
            rows += [row] * 4
            cols += [qb + h, h - 1, ab + h - 1, ab + (node - 1) + h - 1]
            vals += [1.0, -1.0, -1.0, 1.0]
            rhs.append(0.0); row += 1
        for h in range(node):
            rows += [row] * 4
            cols += [qb + h, gb + h, cb + h, ub + h]
            vals += [1.0, 1.0, -1.0, -1.0]
            rhs.append(float(scen[w, h])); row += 1
        rows += [row] * 2
        cols += [qb + node - 1, gb + node - 1]
        vals += [1.0, 1.0]
        rhs.append(float(scen[w, node - 1])); row += 1
        for h in range(node):
            rows += [row] * 4
            cols += [sb + h + 1, sb + h, cb + h, gb + h]
            vals += [1.0, -1.0, -ETA, 1 / ETA]
            rhs.append(0.0); row += 1
        obj[qb + 1: qb + node] = P_EXT[1:] / width
        obj[ab: ab + 2 * (node - 1)] = 0.5 * np.r_[P_EXT[1:], P_EXT[1:]] / width
        obj[zb: zb + node] = 5 * P_EXT / width
        obj[sb + node - 1] = -0.45 / width
    mat = coo_matrix((vals, (rows, cols)), shape=(row, size)).tocsr()
    bounds = [(0.0, None)] * nx
    for _ in range(width):
        bounds += [(0.0, None)] * node + [(0.0, None)] * (2 * (node - 1))
        bounds += [(0.0, LIMIT)] * node + [(0.0, LIMIT)] * node
        bounds += [(0.0, None)] * node + [(0.0, None)] * node
        bounds += [(SOC_MIN, SOC_MAX)] * (node + 1)
    return mat, np.asarray(rhs), obj, bounds


def build_rolling(horizon: int, width: int = 1):
    """滚动LP：合约已锁定，仅储能+紧急购电为决策；1情景时即实时层。"""
    rng = np.random.default_rng(0)
    node = horizon + 1
    scen = rng.uniform(500, 1200, size=(width, node))
    per = 5 * node + 1
    size = width * per
    obj = np.zeros(size)
    rows, cols, vals, rhs = [], [], [], []
    row = 0
    for w in range(width):
        b = w * per
        cb, gb, zb, ub, sb = b, b + node, b + 2 * node, b + 3 * node, b + 4 * node
        for h in range(node):
            rows += [row] * 4
            cols += [gb + h, cb + h, zb + h, ub + h]
            vals += [1.0, -1.0, 1.0, -1.0]
            rhs.append(float(scen[w, h])); row += 1
        for h in range(node):
            rows += [row] * 4
            cols += [sb + h + 1, sb + h, cb + h, gb + h]
            vals += [1.0, -1.0, -ETA, 1 / ETA]
            rhs.append(0.0); row += 1
        obj[zb: zb + node] = 5 * P_EXT[:node] / width
        obj[sb + node - 1] = -0.45 / width
    mat = coo_matrix((vals, (rows, cols)), shape=(row, size)).tocsr()
    bounds = []
    for _ in range(width):
        bounds += [(0.0, LIMIT)] * node + [(0.0, LIMIT)] * node
        bounds += [(0.0, None)] * node + [(0.0, None)] * node
        bounds += [(SOC_MIN, SOC_MAX)] * (node + 1)
    return mat, np.asarray(rhs), obj, bounds


print("=== 阶段0 两阶段SAA（144列计划 + Ω情景）===")
for width in (10, 30, 50):
    t0 = time.perf_counter()
    mat, rhs, obj, bounds = build_two_stage(width)
    t_build = time.perf_counter() - t0
    t0 = time.perf_counter()
    res = linprog(obj, A_eq=mat, b_eq=rhs, bounds=bounds, method="highs")
    t_solve = time.perf_counter() - t0
    print(f"  Ω={width:3d}  变量{mat.shape[1]:7d} 约束{mat.shape[0]:6d}  建模{t_build:5.2f}s  求解{t_solve:6.2f}s  status={res.status}")
    if res.status == 0:
        print(f"          全年334天×1次 ≈ {334 * t_solve / 60:.1f} min")

print()
print("=== 实时层滚动LP（1情景）===")
for horizon in (36, 72, 144):
    mat, rhs, obj, bounds = build_rolling(horizon)
    reps = 20
    t0 = time.perf_counter()
    for _ in range(reps):
        linprog(obj, A_eq=mat, b_eq=rhs, bounds=bounds, method="highs")
    t = (time.perf_counter() - t0) / reps
    print(f"  horizon={horizon:3d}  变量{mat.shape[1]:5d} 约束{mat.shape[0]:5d}  求解{t * 1000:6.2f}ms → 全年{334 * 144 * t / 60:6.1f} min/策略")

print()
print("=== 实时层滚动LP（多情景，用于核对是否值得用SAA做实时）===")
for width in (10, 20):
    mat, rhs, obj, bounds = build_rolling(144, width)
    reps = 5
    t0 = time.perf_counter()
    for _ in range(reps):
        linprog(obj, A_eq=mat, b_eq=rhs, bounds=bounds, method="highs")
    t = (time.perf_counter() - t0) / reps
    print(f"  Ω={width:3d} horizon=144  变量{mat.shape[1]:6d}  求解{t * 1000:7.2f}ms → 全年{334 * 144 * t / 60:7.1f} min/策略")
