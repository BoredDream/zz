"""问题4-2：直接继承问题2，仅把固定电价替换为因果预测的波动电价。

负荷/光伏预测、145段时域、SOC连续和实时执行全部调用 q2_solver 的实现。
附件1仅用于2025-01-01无历史时的显式冷启动先验；交付期决策已有完整1月历史。
"""
from __future__ import annotations

from pathlib import Path
import numpy as np
import pandas as pd
from scipy.optimize import linprog
from scipy.sparse import coo_matrix

import q2_solver as B


def load_inputs(data_dir: Path, cfg: B.Config):
    data = B.load_inputs(data_dir, cfg)
    p4 = pd.read_excel(data_dir / "附件4.xlsx", header=0).iloc[:, 1:].to_numpy(float)
    p1 = data["price_template"]
    natural = np.full_like(p4, np.nan)
    natural[:, 1:] = p4[:, :143]
    natural[1:, 0] = p4[:-1, 143]
    natural[0, 0] = p1[-1]  # 显式冷启动；不进入交付期价格评价
    data.update(price4_template=p4, price4_natural=natural, q4_cold_price_source="附件1仅用于2025-01-01 00:00冷启动")
    return data


def price_forecast_145(data, day: int, window: int = 20):
    """仅使用计划日前历史价格，返回自然日午夜至次日00:10的145段预测。"""
    p4, p1 = data["price4_template"], data["price_template"]
    if day == 0:
        template = p1.copy()
        midnight = float(p1[-1])
    else:
        hist = p4[max(0, day-window):day]
        shape = hist.mean(0) / max(float(hist.mean()), 1e-9)
        level = 0.5*float(p4[day-1].mean()) + 0.5*float(hist.mean())
        template = np.maximum(shape*level, 1e-3)
        midnight = float(p4[day-1, 142])  # 上一已完成23:50--24:00区间
    return np.r_[midnight, template]


def solve_saa(scenarios, price145, committed_grid, initial_soc, terminal_value, cfg):
    """q2_solver.solve_saa的变价版本；唯一变化是使用145段预测价格。"""
    K, H = scenarios.shape
    if H != 145 or len(price145) != 145:
        raise ValueError("Q4-2要求145段净负荷情景和价格预测")
    nplan, block = 144, 5*H+1
    nv = nplan + K*block
    obj = np.zeros(nv); obj[:nplan] = price145[1:]
    for k in range(K):
        base=nplan+k*block
        obj[base:base+2*H] = cfg.throughput_penalty/K
        obj[base+2*H:base+3*H] = cfg.emergency_price_multiple*price145/K
        obj[base+5*H] = -terminal_value/K
    rows=[]; cols=[]; vals=[]; rhs=[]; row=0
    for k in range(K):
        base=nplan+k*block; c0=base; d0=base+H; e0=base+2*H; u0=base+3*H; s0=base+4*H
        for h in range(H):
            if h:
                rows.append(row); cols.append(h-1); vals.append(1.0); rhs.append(float(scenarios[k,h]))
            else: rhs.append(float(scenarios[k,h]-committed_grid))
            for cc,vv in ((c0+h,-1.0),(d0+h,1.0),(e0+h,1.0),(u0+h,-1.0)):
                rows.append(row); cols.append(cc); vals.append(vv)
            row+=1
        for h in range(H):
            for cc,vv in ((s0+h+1,1.0),(s0+h,-1.0),(c0+h,-cfg.eta_charge),(d0+h,1.0/cfg.eta_discharge)):
                rows.append(row); cols.append(cc); vals.append(vv)
            rhs.append(0.0); row+=1
        rows.append(row); cols.append(s0); vals.append(1.0); rhs.append(initial_soc); row+=1
    mat=coo_matrix((vals,(rows,cols)),shape=(row,nv)).tocsr()
    bounds=[(0.0,None)]*nplan
    for _ in range(K):
        bounds += [(0.0,cfg.interval_limit_kwh)]*(2*H)+[(0.0,None)]*(2*H)+[(cfg.soc_min_kwh,cfg.soc_max_kwh)]*(H+1)
    result=linprog(obj,A_eq=mat,b_eq=np.asarray(rhs),bounds=bounds,method="highs")
    if not result.success: raise RuntimeError(f"Q4-2随机线性规划失败：{result.message}")
    cs=[]; ds=[]
    for k in range(K):
        base=nplan+k*block; cs.append(result.x[base:base+H]); ds.append(result.x[base+H:base+2*H])
    return {"grid":result.x[:nplan],"reference_charge":np.mean(cs,axis=0),"reference_discharge":np.mean(ds,axis=0)}


def backtest(data_dir: Path, cfg=None, d0: int = 0, d1: int | None = None):
    cfg = cfg or B.Config(); data=load_inputs(data_dir,cfg)
    net=data["net_actual"].copy(); net[0,0]=data["cold_start_net"][0]
    soc=cfg.initial_soc_kwh; committed=max(float(data["cold_start_net"][0]),0.0)
    records={}
    # 与Q2完全相同的终端水价，保证Q2 vs 4-2只改变价格过程。
    terminal=cfg.eta_discharge*float(np.min(data["price_natural"]))
    if d1 is None: d1=len(data["dates"])
    if d0 != 0: raise ValueError("Q4-2跨日SOC回测必须从2025-01-01开始")
    for day in range(d0,d1):
        weight=B.choose_weight(data["net_actual"],data["cold_start_net"],day,cfg)
        scenarios,center,window=B.scenario_set(data["net_actual"],data["cold_start_net"],day,weight,cfg)
        ph=price_forecast_145(data,day)
        sol=solve_saa(scenarios,ph,committed,soc,terminal,cfg)
        published=sol["grid"]; natural_grid=np.r_[committed,published[:143]]
        run=B.causal_dispatch(net[day],natural_grid,sol["reference_charge"][:144],sol["reference_discharge"][:144],soc,cfg)
        records[day]=dict(x=published,q=published.copy(),natural_x=natural_grid,natural_q=natural_grid.copy(),
                          natural=dict(c=run["charge"],g=run["discharge"],z=run["emergency"],w=run["surplus"],S=run["soc"]),
                          S0=soc,S24=float(run["soc"][-1]),price_forecast_145=ph,weight=weight,window=window)
        soc=float(run["soc"][-1]); committed=float(published[-1])
    return records,data
