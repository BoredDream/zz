"""
2026 高教社杯 C 题 —— 问题 4：波动电价下的购电策略
==================================================
在问题 2/3 的基础上，电价 p_{d,t} 由确定的分时电价变成附件 4 的随机过程。

与问题 3 的三点本质差别
  1) 0:00 时当天电价未知，必须先建电价预测模型；6/12/18 点可用已实现电价滚动修正；
  2) 违约价/紧急价都定义为"交易时刻电价"的倍数，所以相对价格结构不变，
     费用化简式 C_t = 0.5 p x + 0.5 p q + p (q-x)^+ + 5 p z 原样成立；
  3) 目标里出现 E[p·q]。由于同一阶段的 here-and-now 决策不带场景下标，
     其系数取 E[p]；而 recourse 变量 q^k、z^k 与价格同场景配对，用 p^k。
     ⇒ 报童条件从概率分位数变成"价格加权分位数"
        E[p·1{D>q}]/E[p] ∈ [0.1, 0.3] 时不调整。

口径（与问题 1/2/3 一致，见 README「固定口径」）：
  * 时间采用模板行框，第 t 个时段覆盖 [(t+1)*10, (t+2)*10) 分钟；
  * 充/放电量均定义在交流母线侧，S_j = S_{j-1} + eta*c_j - g_j/eta，
    两者单时段上限同为 CMAX = 5000*DT kWh（母线侧）；
  * 结算按题面口径 C = p*min(x,q) + 1.5p*(q-x)^+ + 0.5p*(x-q)^+ + 5p*z，
    其中 p 为【实际】电价。

运行（用 scripts/export_q4.py，见 docs/q4_model.md）。
"""
from pathlib import Path

import numpy as np, pandas as pd, scipy.sparse as sp
from scipy.optimize import linprog

from q3_multistage import (UP, T, DT, ETA, SMIN, SMAX, CMAX, TSTAGE, ND,
                           DATES, DSTR, L, G, load_hat, pv_hat, dispatch,
                           clock_min, emergency_segments)

# ----------------------------------------------------------------------
# 0. 电价数据
# ----------------------------------------------------------------------
PMAT = pd.read_excel(UP+'附件4.xlsx', header=0).iloc[:, 1:].to_numpy(float)   # 365x144 元/kWh
PHI = 0.85          # 日内电价残差的 AR(1) 衰减系数（10 分钟步长，已标定）
WIN = 20            # 电价形态滚动窗口(天)
ALPHA = 5.0         # LP 中紧急电价倍数
_PHAT_CACHE = {}

# ----------------------------------------------------------------------
# 1. 电价预测子模型
# ----------------------------------------------------------------------
def price_hat(d, m):
    """两因子电价预测： p̂ = 形态_t × 水平_d × 日内AR(1)修正。

      * 形态：近 WIN 天逐时段均值归一化（附件4 的日内形态很稳定，
              谷 22:00-05:00≈0.42、峰 19:00≈1.35、午间凹陷 11:00≈0.50）
      * 水平：0.5×前一日均价 + 0.5×窗口均价（日均价滞后1天相关 0.506）
      * 日内更新(m>=1)：用 [0,t_m) 已实现电价算水平比与瞬时偏离，
              偏离按 AR(1) 以 PHI^k 衰减（10分钟滞后自相关 0.96，
              但用于多步外推时 0.85 的实测误差最小）

    标定结果（2025 年，留出预热 30 天）。各阶段剩余窗口不同，MAPE 不可横比，
    故同时给出"同一窗口下含更新 vs 不更新"的 MAE：

        阶段  发布   MAPE     MAE      同窗口不更新 MAE   前一日持续
         0    0:00  13.16%   0.0799   0.0799（同）        0.0846
         1    6:00   9.09%   0.0556   0.0916  (-39%)     0.0950
         2   12:00  11.61%   0.0837   0.0865  ( -3%)     0.0892
         3   18:00  13.44%   0.0832   0.0631  (+32%)     0.0651

    m=3 的更新在精度上是负收益：它用 15:00-18:00（午后低价段）估出的水平比被乘到
    18:00-24:00（晚高峰）上，跨了价格形态的"体制"。但按费用的消融
    （docs/_ablate_q4_m3.py，60 天）显示影响仅 0.003%，故不为此改动模型，
    详见 docs/q4_model.md 第 10 节。
    """
    key = (d, m)
    if key in _PHAT_CACHE:
        return _PHAT_CACHE[key]
    lo = max(d-WIN, 0)
    if d == 0:
        base = PMAT[0].copy()
    else:
        win = PMAT[lo:d]
        shape = win.mean(0) / win.mean()
        level = 0.5*PMAT[d-1].mean() + 0.5*win.mean()
        base = shape * level
    tm = TSTAGE[m]
    if tm > 0:
        r = PMAT[d, :tm] / np.maximum(base[:tm], 1e-6)
        lvl = float(np.clip(r[-18:].mean(), 0.6, 1.6))       # 近 3 小时水平比
        dev = float(np.clip(r[-1]/lvl, 0.5, 2.0))            # 瞬时偏离
        k = np.arange(1, T-tm+1)
        base = base.copy()
        base[tm:] = base[tm:] * lvl * (1 + (dev-1)*PHI**k)
    out = np.maximum(base, 1e-3)
    _PHAT_CACHE[key] = out
    return out

def water_value(phat):
    """末端储能水价：用当日预测的最低 12 个时段均价折算的重置成本 p_谷/η。"""
    return float(np.sort(phat)[:12].mean() / ETA)

# ----------------------------------------------------------------------
# 2. 联合场景生成（价格 / 负载 / 光伏必须同日配对抽样以保留相关性）
# ----------------------------------------------------------------------
def scenarios4(d, m, K=30):
    Lh, Gh, Ph = load_hat(d, m), pv_hat(d, m), price_hat(d, m)
    sl, sg, spz = [], [], []
    for j in range(1, K+1):
        dd = d - j
        if dd < 10:
            continue
        sl.append(np.maximum(Lh + (L[dd] - load_hat(dd, m)), 0))
        sg.append(np.maximum(Gh + (G[dd] - pv_hat(dd, m)), 0))
        # 价格用乘性残差，避免出现负价
        ratio = PMAT[dd] / np.maximum(price_hat(dd, m), 1e-6)
        spz.append(np.maximum(Ph * np.clip(ratio, 0.3, 3.0), 1e-3))
    if not sl:
        sl, sg, spz = [Lh], [Gh], [Ph]
    return sl, sg, spz

# ----------------------------------------------------------------------
# 3. 阶段 LP（价格随机版）
# ----------------------------------------------------------------------
def stage_lp4(m, x_ref, S_cur, scenL, scenG, scenP, pdet,
              adjust=True, alpha=ALPHA, lam=0.478):
    """第 m 阶段两阶段随机 LP。

    adjust=False 时（问题 4-2）不设 recourse 购电变量，即 q≡x，
    费用退化为 p·x + 5p·z，与问题 2 完全一致。

    变量布局
        [0,nD)                本阶段锁定的合约量 D_t
        [nD,nD+nU0)           m>=1 时 committed 段的 U_t=(a_t-x_ref_t)^+
        每场景 k：Q(nR) U(nR) c(nT) g(nT) z(nT) w(nT) S(nT)
    """
    tm = TSTAGE[m]
    tn = TSTAGE[m+1] if adjust else T          # 不可调整时后续无 recourse
    K = len(scenL)
    nT = T - tm
    stage0 = (m == 0)
    dec = list(range(0, T)) if stage0 else list(range(tm, tn))
    R = list(range(tn, T))
    nD, nR = len(dec), len(R)
    dpos = {t: i for i, t in enumerate(dec)}
    nU0 = 0 if stage0 else nD
    base = nD + nU0
    per = 2*nR + 5*nT
    nv = base + K*per
    o = lambda k: base + k*per

    c = np.zeros(nv)
    # here-and-now 决策不带场景下标，其价格系数取期望电价 pdet
    if stage0:
        # t<tn 的计划即最终合约(不可再调) -> 系数 p；t>=tn 的计划只承担一半 -> 0.5p
        for t in dec:
            c[dpos[t]] = pdet[t] if t < tn else 0.5*pdet[t]
    else:
        for i, t in enumerate(dec):
            c[i] = 0.5*pdet[t]
            c[nD+i] = pdet[t]                  # committed 段的超计划罚项

    rows, cols, vals, beq = [], [], [], []
    iru, icu, ivu, bub = [], [], [], []
    nr = nq = 0
    for k in range(K):
        pk = scenP[k]
        ok = o(k)
        oQ, oU = ok, ok+nR
        oc = ok+2*nR; og = oc+nT; oz = og+nT; ow = oz+nT; oS = ow+nT
        for j, t in enumerate(R):
            c[oQ+j] += 0.5*pk[t]/K
            c[oU+j] += pk[t]/K
        for j in range(nT):
            c[oz+j] += alpha*pk[tm+j]/K
        c[oS+nT-1] -= lam/K
        for j in range(nT):                    # 功率平衡（四项均交流母线侧）
            t = tm + j
            col = dpos[t] if t < tn else oQ + (t-tn)
            rows.append(nr); cols.append(col); vals.append(1.0)
            for cc, vv in ((oz+j, 1.0), (og+j, 1.0), (oc+j, -1.0), (ow+j, -1.0)):
                rows.append(nr); cols.append(cc); vals.append(vv)
            beq.append(scenL[k][t] - scenG[k][t]); nr += 1
        for j in range(nT):                    # SOC 转移 S_j = S_{j-1} + eta*c_j - g_j/eta
            for cc, vv in ((oS+j, 1.0), (oc+j, -ETA), (og+j, 1.0/ETA)):
                rows.append(nr); cols.append(cc); vals.append(vv)
            if j > 0:
                rows.append(nr); cols.append(oS+j-1); vals.append(-1.0); beq.append(0.0)
            else:
                beq.append(S_cur)
            nr += 1
        for j, t in enumerate(R):              # U^k >= Q^k - x_t
            iru.append(nq); icu.append(oQ+j); ivu.append(1.0)
            iru.append(nq); icu.append(oU+j); ivu.append(-1.0)
            if stage0:
                iru.append(nq); icu.append(dpos[t]); ivu.append(-1.0); bub.append(0.0)
            else:
                bub.append(float(x_ref[t]))
            nq += 1
    if not stage0:
        for i, t in enumerate(dec):
            iru.append(nq); icu.append(i); ivu.append(1.0)
            iru.append(nq); icu.append(nD+i); ivu.append(-1.0)
            bub.append(float(x_ref[t])); nq += 1

    Aeq = sp.csr_matrix((vals, (rows, cols)), shape=(nr, nv))
    Aub = sp.csr_matrix((ivu, (iru, icu)), shape=(nq, nv)) if nq else None
    lb = np.zeros(nv); ub = np.full(nv, np.inf)
    for k in range(K):
        ok = o(k); oc = ok+2*nR; og = oc+nT; oS = og+3*nT
        ub[oc:oc+nT] = CMAX; ub[og:og+nT] = CMAX
        lb[oS:oS+nT] = SMIN; ub[oS:oS+nT] = SMAX
    r = linprog(c, A_ub=Aub, b_ub=np.array(bub) if nq else None,
                A_eq=Aeq, b_eq=np.array(beq),
                bounds=np.column_stack([lb, ub]), method='highs')
    if r.x is None:
        raise RuntimeError('LP infeasible: stage %d' % m)
    return r.x[:nD]

# ----------------------------------------------------------------------
# 4. 单日主流程与结算
# ----------------------------------------------------------------------
def solve_day4(d, S0, K=30, stages=(0, 1, 2, 3)):
    adjust = len(stages) > 1
    out = {k: np.zeros(T) for k in ('z', 'c', 'g', 'w', 'S')}
    sl, sg, spz = scenarios4(d, 0, K)
    ph = price_hat(d, 0); lam = water_value(ph)
    x = stage_lp4(0, None, S0, sl, sg, spz, ph, adjust=adjust, lam=lam)
    q = x.copy(); S = S0
    for m in range(4):
        tm, tn = TSTAGE[m], TSTAGE[m+1]
        if m >= 1 and m in stages:
            sl, sg, spz = scenarios4(d, m, K)
            ph = price_hat(d, m); lam = water_value(ph)
            q[tm:tn] = stage_lp4(m, x, S, sl, sg, spz, ph, adjust=True, lam=lam)
        S = dispatch(tm, tn, q, S, L[d], G[d], out)
    return x, q, out, S

def day_cost4(d, x, q, out):
    """按【实际】电价结算： 0.5p x + 0.5p q + p(q-x)^+ + 5p z"""
    p = PMAT[d]
    plan = (0.5*p*x).sum()
    adj = (0.5*p*q).sum() + (p*np.maximum(q-x, 0)).sum()
    emg = (5*p*out['z']).sum()
    return plan+adj+emg, plan+adj, emg

def settle_parts4(d, x, q, z):
    """按题面口径把单日费用拆成填写工作簿用的三项（三者之和恒等于 day_cost4 的总费用）：
        计划购电费用   = Σ p*min(x,q)
        调整相关费用   = Σ [1.5p*(q-x)^+ + 0.5p*(x-q)^+]
        紧急购电费用   = Σ 5p*z
    其中 p 为当日【实际】电价 PMAT[d]。"""
    p = PMAT[d]
    up, dn = np.maximum(q-x, 0.0), np.maximum(x-q, 0.0)
    return (p*np.minimum(x, q), 1.5*p*up + 0.5*p*dn, 5.0*p*z)

def storage_blocks(charge, discharge):
    """模板行口径的六个 4 小时段：t=24k..24k+23 覆盖 [(24k+1)*10, (24k+25)*10) 分钟。"""
    return [{"time_range": "%s-%s" % (clock_min((24*k+1)*10), clock_min((24*k+25)*10)),
             "charge_kwh": float(charge[24*k:24*k+24].sum()),
             "discharge_kwh": float(discharge[24*k:24*k+24].sum())} for k in range(6)]

def backtest4(d0=0, d1=ND, K=30, stages=(0, 1, 2, 3), S0=6000.0, verbose=False):
    S, rec = S0, {}
    for d in range(d0, d1):
        Ss = S
        x, q, out, S = solve_day4(d, S, K, stages)
        rec[d] = dict(x=x, q=q, S0=Ss, S24=out['S'][142], **out)
        if verbose and d % 20 == 0:
            print(d, DSTR[d], 'S=%.0f' % S, flush=True)
    return rec, S
