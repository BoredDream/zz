"""
2026 高教社杯 C 题 —— 问题 3：含日内预报更新的多阶段随机购电策略
=================================================================
时间轴约定：第 i 个时段(i=0..143) 覆盖 [(i+1)*10min, (i+2)*10min)，
即 i=0 -> 0:10-0:20, i=143 -> 0:00+1 - 0:10+1，与 result 模板列标签一致。

四个决策阶段（预报发布时刻）：
    m=0  0:00   t_m=0    制定全天计划 x[0..143]
    m=1  6:00   t_m=35   调整 [35,71)
    m=2 12:00   t_m=71   调整 [71,107)
    m=3 18:00   t_m=107  调整 [107,144)
（6:00 对应的时段起点 (35+1)*10=360min=6:00，故 t_1=35，其余同理。）

费用（单时段）：
    C_t = 0.5*p_t*x_t + 0.5*p_t*q_t + p_t*(q_t-x_t)^+ + 5*p_t*z_t
    其中 x=0:00 计划量，q=最终生效合约量，z=紧急购电量。
    （由 p*min(x,q)+1.5p*(q-x)^+ +0.5p*(x-q)^+ 化简而来，关于 q 分段线性凸。）

储能口径（与问题 1/2 的固定口径一致，见 README「固定口径」第 6 条）：
    充电量 c 与放电量 g 均定义在交流母线侧，SOC 递推为
        S_j = S_{j-1} + eta*c_j - g_j/eta
    充、放电的单时段上限同为 CMAX=5000*DT kWh（母线侧），
    故放电一个 CMAX 会消耗 CMAX/eta 的储电量。
"""
from pathlib import Path

import numpy as np, pandas as pd, scipy.sparse as sp
from scipy.optimize import linprog
from scipy.interpolate import PchipInterpolator

# ----------------------------------------------------------------------
# 0. 参数与数据
# ----------------------------------------------------------------------
import os
UP = os.environ.get('Q3_DATA', str(Path(__file__).resolve().parent.parent / 'problem' / 'data')) + os.sep
T, DT = 144, 1/6.0                     # 时段数、时段长(h)
ETA = 0.9                              # 充/放电效率(各 0.9)
SMIN, SMAX = 1200.0, 10800.0
CMAX = 5000 * DT                       # 单时段最大充/放电量 kWh（交流母线侧，与问题1/2同）
LAM = 0.478                            # 末端储能水价 元/kWh = p_谷/eta
ALPHA = 5.0                            # LP 中紧急电价倍数(真实为 5，可调高以增保守度)
TSTAGE = [0, 35, 71, 107, 144]         # 各阶段起始时段（含哨兵 144）
H0 = [0, 6, 12, 18]                    # 各阶段发布时刻(小时)
WCOMB = [0.4, 0.6, 0.9, 0.4]           # 附件3预报与衰减均值的组合权重(已标定)

_dl = pd.read_excel(UP+'附件2.xlsx', sheet_name='小区负载', header=0)
DATES = pd.to_datetime(_dl.iloc[:, 0])
LKW = _dl.iloc[:, 1:].to_numpy(float)                                   # kW
GKW = pd.read_excel(UP+'附件2.xlsx', sheet_name='光伏发电实际功率',
                    header=0).iloc[:, 1:].to_numpy(float)               # kW
_a1 = pd.read_excel(UP+'附件1.xlsx', header=0); _a1.columns = ['t','p','L','G']
P = _a1.p.values                                                        # 元/kWh
L = LKW * DT                                                            # kWh/时段
G = GKW * DT
ND = len(L)

_f = pd.read_excel(UP+'附件3.xlsx', header=0); _f.iloc[:, 0] = _f.iloc[:, 0].ffill()
_fd = pd.to_datetime(_f.iloc[:, 0]); _iss = _f.iloc[:, 1].astype(str)
_FV = _f.iloc[:, 2:].to_numpy(float)
FCAST = {}                       # (日期字符串, 发布小时) -> 未来 1..24 小时整点预报(kW)
for i in _f.index:
    FCAST[(_fd[i].strftime('%Y-%m-%d'), int(_iss[i].split(':')[0]))] = _FV[i]
DSTR = [d.strftime('%Y-%m-%d') for d in DATES]
SLOT_MIN = np.array([(i+1)*10 for i in range(T)])     # 每个时段的采样时刻(分钟)

# ----------------------------------------------------------------------
# 1. 预测子模型
# ----------------------------------------------------------------------
def pv_from_forecast(d, m):
    """把附件3的整点预报插值成 10 分钟序列(kW)。
    关键细节：
      * 以发布时刻 h0 的实测出力作为锚点，避免插值在 h0 附近悬空；
      * 用 PCHIP 保形插值，线性插值会在日出/日落段出现折角与负值；
      * 只对 t>=t_m 的时段有效，之前的时段用实测值。"""
    h0 = H0[m]
    fv = FCAST.get((DSTR[d], h0))
    if fv is None:
        return None
    t0 = h0 * 60
    if h0 == 0:
        # 0:00 只能使用刚结束的 23:50--24:00 区间；原始末列对应
        # 0:00--0:10，发布时尚未实现，禁止拿它作锚点。
        anchor = GKW[d-1, T-2] if d > 0 else _a1.G.values[-2]
    else:
        anchor = GKW[d, (h0*60)//10 - 1]
    ts = np.concatenate([[t0], t0 + 60*np.arange(1, 25)])
    vs = np.concatenate([[anchor], fv])
    pch = PchipInterpolator(ts, vs)
    out = np.zeros(T)
    msk = SLOT_MIN >= t0
    out[msk] = np.maximum(pch(np.clip(SLOT_MIN[msk], t0, ts[-1])), 0.0)
    return out

def pv_decay(d, lam=0.8, n=10):
    """近 n 日指数衰减加权平均(kW)，作为与附件3独立的第二个预测源。"""
    idx = [d-1-j for j in range(n) if d-1-j >= 0]
    if not idx:
        return _a1.G.values.copy()
    w = np.array([lam**j for j in range(len(idx))]); w /= w.sum()
    return (GKW[idx] * w[:, None]).sum(0)

def pv_hat(d, m):
    """组合预测：w*附件3 + (1-w)*衰减均值。
    标定结果(白天 RMSE，kW)： 0:00 543->355, 6:00 ->284, 12:00 ->188。
    两个预测源的误差几乎不相关(corr≈0.06)，所以组合能显著降误差。"""
    fc = pv_from_forecast(d, m)
    dc = pv_decay(d)
    if fc is None:
        return dc * DT
    w = WCOMB[m]
    return np.maximum(w*fc + (1-w)*dc, 0.0) * DT

def load_hat(d, m):
    """负载预测：近 3 个同星期日均值 × 近 7 日水平偏差修正；
    日内更新：用已实现时段的实际/预测比对剩余时段整体缩放(阻尼后限幅)。"""
    idx = [d-7*k for k in range(1, 4) if d-7*k >= 0]
    base = L[idx].mean(0) if idx else _a1.L.values*DT
    r = []
    for j in range(1, 8):
        dd = d - j
        ii = [dd-7*k for k in range(1, 4) if dd-7*k >= 0]
        if len(ii) == 3:
            r.append(L[dd].sum() / L[ii].mean(0).sum())
    base = base * (np.mean(r) if r else 1.0)
    tm = TSTAGE[m]
    if tm > 0:                                   # 日内偏差修正
        ratio = L[d, :tm].sum() / max(base[:tm].sum(), 1e-6)
        base = base * np.clip(ratio, 0.85, 1.15)
    return base

# ----------------------------------------------------------------------
# 2. 阶段 LP（多阶段随机规划的滚动实现）
# ----------------------------------------------------------------------
def stage_lp(m, x_ref, S_cur, scenL, scenG, alpha=ALPHA, lam=LAM):
    """求解第 m 阶段的两阶段随机 LP。

    决策结构（非预期性）：
      * 本阶段"锁定"的合约量 —— m=0 时为全天计划 x[0..143]，m>=1 时为 a[t_m..t_next)
      * 之后仍可调整的时段作为 recourse 变量 q^k（逐场景），体现"未来还能再调"的期权价值
      * 储能 c,g、紧急购电 z、弃电 w、SOC S 均为逐场景 recourse

    返回：m=0 时返回全天计划 x；m>=1 时返回 [t_m,t_next) 的调整量。
    """
    tm, tn = TSTAGE[m], TSTAGE[m+1]
    K = len(scenL)
    nT = T - tm                              # 剩余时段数
    stage0 = (m == 0)
    dec = list(range(0, T)) if stage0 else list(range(tm, tn))   # 本阶段决策时段
    R = list(range(tn, T))                   # 仍可 recourse 的时段
    nD, nR = len(dec), len(R)
    dpos = {t: i for i, t in enumerate(dec)}

    # ---- 变量布局 ----
    # [0, nD)                : 决策量 D_t
    # 若 m>=1: [nD, nD+nD)   : committed 段的 U_t = (a_t - x_ref_t)^+
    nU0 = 0 if stage0 else nD
    base = nD + nU0
    per = nR + nR + 5*nT                     # 每场景: Q(nR) U(nR) c g z w S
    nv = base + K*per
    def o(k):  # 第 k 个场景的起始下标
        return base + k*per

    c = np.zeros(nv)
    for t in dec:
        c[dpos[t]] += (P[t] if (stage0 and t < tn) else 0.5*P[t])
    if not stage0:
        for i, t in enumerate(dec):
            c[nD+i] += P[t]                  # committed 段的超计划罚项
    rows, cols, vals, beq = [], [], [], []
    iru, icu, ivu, bub = [], [], [], []      # 不等式(U 约束)
    nr = nq = 0
    for k in range(K):
        ok = o(k); oQ, oU, oc, og, oz, ow, oS = ok, ok+nR, ok+2*nR, ok+2*nR+nT, \
             ok+2*nR+2*nT, ok+2*nR+3*nT, ok+2*nR+4*nT
        for j, t in enumerate(R):
            c[oQ+j] += 0.5*P[t]/K
            c[oU+j] += P[t]/K
        for j in range(nT):
            c[oz+j] += alpha*P[tm+j]/K
        c[oS+nT-1] -= lam/K
        # 等式 1：功率平衡（四项均为交流母线侧电量）  Qeff + z + g - c - w = L-G
        for j in range(nT):
            t = tm + j
            if t in dpos and (not stage0 or t < tn):
                rows.append(nr); cols.append(dpos[t]); vals.append(1.0)
            elif stage0 and t >= tn:
                rows.append(nr); cols.append(oQ + (t-tn)); vals.append(1.0)
            elif t >= tn:
                rows.append(nr); cols.append(oQ + (t-tn)); vals.append(1.0)
            else:
                rows.append(nr); cols.append(dpos[t]); vals.append(1.0)
            for cc, vv in ((oz+j, 1.0), (og+j, 1.0), (oc+j, -1.0), (ow+j, -1.0)):
                rows.append(nr); cols.append(cc); vals.append(vv)
            beq.append(scenL[k][t] - scenG[k][t]); nr += 1
        # 等式 2：SOC 转移  S_j = S_{j-1} + eta*c_j - g_j/eta
        for j in range(nT):
            for cc, vv in ((oS+j, 1.0), (oc+j, -ETA), (og+j, 1.0/ETA)):
                rows.append(nr); cols.append(cc); vals.append(vv)
            if j > 0:
                rows.append(nr); cols.append(oS+j-1); vals.append(-1.0); beq.append(0.0)
            else:
                beq.append(S_cur)
            nr += 1
        # 不等式：U^k_t >= Q^k_t - x_t
        for j, t in enumerate(R):
            iru.append(nq); icu.append(oQ+j); ivu.append(1.0)
            iru.append(nq); icu.append(oU+j); ivu.append(-1.0)
            if stage0:                        # x_t 是变量
                iru.append(nq); icu.append(dpos[t]); ivu.append(-1.0); bub.append(0.0)
            else:
                bub.append(float(x_ref[t]))
            nq += 1
    if not stage0:                            # committed 段： U_t >= a_t - x_ref_t
        for i, t in enumerate(dec):
            iru.append(nq); icu.append(i); ivu.append(1.0)
            iru.append(nq); icu.append(nD+i); ivu.append(-1.0)
            bub.append(float(x_ref[t])); nq += 1

    Aeq = sp.csr_matrix((vals, (rows, cols)), shape=(nr, nv))
    Aub = sp.csr_matrix((ivu, (iru, icu)), shape=(nq, nv)) if nq else None
    lb = np.zeros(nv); ub = np.full(nv, np.inf)
    for k in range(K):
        ok = o(k); oc = ok+2*nR; og = oc+nT; oS = ok+2*nR+4*nT
        ub[oc:oc+nT] = CMAX; ub[og:og+nT] = CMAX
        lb[oS:oS+nT] = SMIN; ub[oS:oS+nT] = SMAX
    r = linprog(c, A_ub=Aub, b_ub=np.array(bub) if nq else None,
                A_eq=Aeq, b_eq=np.array(beq),
                bounds=np.column_stack([lb, ub]), method='highs')
    if r.x is None:
        raise RuntimeError('LP infeasible at stage %d' % m)
    return r.x[:nD]


def stage0_lp_145(committed_q, S_cur, scenL, scenG, alpha=ALPHA, lam=LAM):
    """0:00 的 145 段随机 LP。

    h=0 是前一日已锁定的 00:00--00:10 合约量；h=1..144 对应今天
    新发布的模板行 t=0..143。首段参与物理/SOC递推但不是当天的新决策。
    """
    K, H, tn = len(scenL), T + 1, TSTAGE[1]
    if any(len(v) != H for v in (*scenL, *scenG)):
        raise ValueError("阶段0情景必须为145段")
    R = list(range(tn, T))
    nD, nR = T, len(R)
    per = 2 * nR + 5 * H
    nv = nD + K * per

    def o(k):
        return nD + k * per

    obj = np.zeros(nv)
    obj[:tn] = P[:tn]
    obj[tn:nD] = 0.5 * P[tn:]
    rows, cols, vals, beq = [], [], [], []
    iru, icu, ivu, bub = [], [], [], []
    nr = nq = 0
    for k in range(K):
        ok = o(k)
        oQ, oU = ok, ok + nR
        oc, og = ok + 2*nR, ok + 2*nR + H
        oz, ow, oS = ok + 2*nR + 2*H, ok + 2*nR + 3*H, ok + 2*nR + 4*H
        for j, t in enumerate(R):
            obj[oQ+j] += 0.5 * P[t] / K
            obj[oU+j] += P[t] / K
        p145 = np.r_[P[-1], P]
        obj[oz:oz+H] += alpha * p145 / K
        obj[oS+H-1] -= lam / K

        for h in range(H):
            if h == 0:
                rhs = scenL[k][h] - scenG[k][h] - committed_q
            else:
                t = h - 1
                if t < tn:
                    rows.append(nr); cols.append(t); vals.append(1.0)
                else:
                    rows.append(nr); cols.append(oQ + t-tn); vals.append(1.0)
                rhs = scenL[k][h] - scenG[k][h]
            for cc, vv in ((oz+h, 1.0), (og+h, 1.0), (oc+h, -1.0), (ow+h, -1.0)):
                rows.append(nr); cols.append(cc); vals.append(vv)
            beq.append(float(rhs)); nr += 1

        for h in range(H):
            for cc, vv in ((oS+h, 1.0), (oc+h, -ETA), (og+h, 1.0/ETA)):
                rows.append(nr); cols.append(cc); vals.append(vv)
            if h:
                rows.append(nr); cols.append(oS+h-1); vals.append(-1.0)
                beq.append(0.0)
            else:
                beq.append(float(S_cur))
            nr += 1

        for j, t in enumerate(R):
            iru += [nq, nq, nq]
            icu += [oQ+j, oU+j, t]
            ivu += [1.0, -1.0, -1.0]
            bub.append(0.0); nq += 1

    Aeq = sp.csr_matrix((vals, (rows, cols)), shape=(nr, nv))
    Aub = sp.csr_matrix((ivu, (iru, icu)), shape=(nq, nv))
    lb, ub = np.zeros(nv), np.full(nv, np.inf)
    for k in range(K):
        ok = o(k); oc = ok+2*nR; og = oc+H; oS = ok+2*nR+4*H
        ub[oc:oc+H] = CMAX; ub[og:og+H] = CMAX
        lb[oS:oS+H] = SMIN; ub[oS:oS+H] = SMAX
    result = linprog(obj, A_ub=Aub, b_ub=np.asarray(bub), A_eq=Aeq,
                     b_eq=np.asarray(beq), bounds=np.column_stack([lb, ub]), method='highs')
    if result.x is None:
        raise RuntimeError('LP infeasible at stage 0 (145 intervals)')
    return result.x[:T]

# ----------------------------------------------------------------------
# 3. 实时层：给定已锁定的合约量，10 分钟粒度调度储能，不足则紧急购电
# ----------------------------------------------------------------------
def dispatch(t0, t1, q, S, Lr, Gr, out):
    """贪心调度。给定 q 后实时唯一的自由度是"放电 or 紧急购电"，
    由于紧急电价恒为 5*p_t，且计划已按分位数留足裕量，贪心接近最优
    （实测：改用"按计划SOC设预留下限"反而更差，因为下限建立在偏乐观的光伏预报上）。

    c 与 g 均为交流母线侧电量：放电 g 需消耗 g/eta 的储电量，充电 c 只能存入 eta*c。"""
    for t in range(t0, t1):
        net = Lr[t] - Gr[t] - q[t]
        if net > 0:
            g = max(min(net, CMAX, (S-SMIN)*ETA), 0.0)
            out['g'][t] = g; S -= g/ETA; out['z'][t] = net - g
        else:
            s = -net
            cc = max(min(s, CMAX, (SMAX-S)/ETA), 0.0)
            out['c'][t] = cc; S += ETA*cc; out['w'][t] = s - cc
        out['S'][t] = S
    return S


def dispatch_locked_interval(q, S, load, pv):
    """执行午夜已锁定的一段，不读取该段实现值来反推0:00计划。"""
    net = float(load - pv - q)
    c = g = z = w = 0.0
    if net > 0:
        g = max(min(net, CMAX, (S-SMIN)*ETA), 0.0)
        S -= g/ETA; z = net-g
    else:
        surplus = -net
        c = max(min(surplus, CMAX, (SMAX-S)/ETA), 0.0)
        S += ETA*c; w = surplus-c
    return S, dict(c=c, g=g, z=z, w=w)

# ----------------------------------------------------------------------
# 4. 单日主流程
# ----------------------------------------------------------------------
def scenarios(d, m, K=30):
    """场景生成：对同一阶段 m，取过去 K 天的整条 144 维预测残差路径叠加到当日预测上。
    整条路径重采样而非逐点独立抽样，才能保住误差的时序相关性。"""
    Lh, Gh = load_hat(d, m), pv_hat(d, m)
    sl, sg = [], []
    first_lag = 2 if m == 0 else 1
    for j in range(first_lag, first_lag+K):
        dd = d - j
        if dd < 10:
            continue
        sl.append(np.maximum(Lh + (L[dd] - load_hat(dd, m)), 0))
        sg.append(np.maximum(Gh + (G[dd] - pv_hat(dd, m)), 0))
    if not sl:
        sl, sg = [Lh], [Gh]
    return sl, sg


def midnight_center(d):
    """0:00 对 00:00--00:10 的因果预测：使用上一已完成区间持久性。"""
    if d > 0:
        return float(L[d-1, T-2]), float(G[d-1, T-2])
    return float(_a1.L.values[-2] * DT), float(_a1.G.values[-2] * DT)


def midnight_actual(d):
    """自然日首段实际值；附件2缺失的1月1日午夜仅作冷启动。"""
    if d > 0:
        return float(L[d-1, T-1]), float(G[d-1, T-1])
    return float(_a1.L.values[-1] * DT), float(_a1.G.values[-1] * DT)


def scenarios0_145(d, K=30):
    """阶段0使用145段，并且最晚只使用 d-2 的完整历史轮廓。"""
    Lh, Gh = load_hat(d, 0), pv_hat(d, 0)
    ml, mg = midnight_center(d)
    center_l, center_g = np.r_[ml, Lh], np.r_[mg, Gh]
    sl, sg = [], []
    for j in range(2, K+2):
        dd = d-j
        if dd < 10:
            continue
        aml, amg = midnight_actual(dd)
        hml, hmg = midnight_center(dd)
        hist_l = np.r_[aml, L[dd]]
        hist_g = np.r_[amg, G[dd]]
        hist_hat_l = np.r_[hml, load_hat(dd, 0)]
        hist_hat_g = np.r_[hmg, pv_hat(dd, 0)]
        sl.append(np.maximum(center_l + hist_l-hist_hat_l, 0.0))
        sg.append(np.maximum(center_g + hist_g-hist_hat_g, 0.0))
    return (sl, sg) if sl else ([center_l], [center_g])

def solve_day(d, S0, committed_q, K=30, stages=(0, 1, 2, 3), cache=None):
    """stages 指定启用哪些调整时刻，(0,) 即退化为问题 2 的"只在 0:00 决策"。"""
    out = {k: np.zeros(T) for k in ('z', 'c', 'g', 'w', 'S')}
    sl, sg = scenarios0_145(d, K)
    x = stage0_lp_145(committed_q, S0, sl, sg) # 0:00 计划，含已锁定午夜段
    q = x.copy()                               # 最终合约量
    ml, mg = midnight_actual(d)
    S, midnight = dispatch_locked_interval(committed_q, S0, ml, mg)
    S_after_midnight = S
    for m in range(4):
        tm, tn = TSTAGE[m], TSTAGE[m+1]
        if m >= 1 and m in stages:
            sl, sg = scenarios(d, m, K)
            q[tm:tn] = stage_lp(m, x, S, sl, sg)
        # t=143 是次日00:00--00:10，必须留给次日0:00决策之后执行。
        S = dispatch(tm, min(tn, T-1), q, S, L[d], G[d], out)
    natural = {k: np.r_[midnight[k], out[k][:T-1]] for k in ('c','g','z','w')}
    natural['S'] = np.r_[S0, S_after_midnight, out['S'][:T-1]]
    return x, q, out, natural, S

def day_cost(x, q, out):
    """0.5p*x + 0.5p*q + p*(q-x)^+ + 5p*z"""
    plan = (0.5*P*x).sum()
    adj  = (0.5*P*q).sum() + (P*np.maximum(q-x, 0)).sum()
    emg  = (5*P*out['z']).sum()
    return plan+adj+emg, plan+adj, emg


def natural_price():
    return np.r_[P[-1], P[:T-1]]


def natural_settle_parts(x, q, z):
    """自然日00:00--24:00费用；x/q已跨行拼接。"""
    p = natural_price()
    up, dn = np.maximum(q-x, 0.0), np.maximum(x-q, 0.0)
    return p*np.minimum(x, q), 1.5*p*up + 0.5*p*dn, 5.0*p*z


def natural_day_cost(x, q, z):
    parts = natural_settle_parts(x, q, z)
    return float(sum(v.sum() for v in parts))

def settle_parts(x, q, z):
    """按题面口径把单日费用拆成填写工作簿用的三项（三者之和恒等于 day_cost 的总费用）：
        计划购电费用   = Σ p*min(x,q)
        调整相关费用   = Σ [1.5p*(q-x)^+ + 0.5p*(x-q)^+]
        紧急购电费用   = Σ 5p*z
    """
    up, dn = np.maximum(q-x, 0.0), np.maximum(x-q, 0.0)
    return (P*np.minimum(x, q), 1.5*P*up + 0.5*P*dn, 5.0*P*z)

# ----------------------------------------------------------------------
# 4b. 模板行口径的时刻标签（第 t 个时段覆盖 [(t+1)*10, (t+2)*10) 分钟）
# ----------------------------------------------------------------------
def clock_min(minutes):
    """自当日 0:00 起的分钟数 -> 标签；超过 1440 用模板自身的 '+1' 写法（如 '0:10+1'）。
    小时不补零，与模板列标签 '0:10-0:20' / '0:00-0:10+1' 的排版一致。"""
    if minutes <= 1440:
        return '24:00' if minutes == 1440 else '%d:%02d' % (minutes//60, minutes % 60)
    minutes -= 1440
    return '%d:%02d+1' % (minutes//60, minutes % 60)

def interval_label(t):
    return '%s-%s' % (clock_min((t+1)*10), clock_min((t+2)*10))

def emergency_segments(z, tol=1e-6):
    """连续非零的紧急购电时段合并成一段，返回 [{'time_range','energy_kwh'}, ...]。"""
    segs, start = [], None
    for t, v in enumerate(np.r_[z, 0.0]):
        if v > tol and start is None:
            start = t
        elif v <= tol and start is not None:
            segs.append({'time_range': '%s-%s' % (clock_min((start+1)*10), clock_min((t+1)*10)),
                         'energy_kwh': float(z[start:t].sum())})
            start = None
    return segs


def natural_emergency_segments(z, tol=1e-6):
    """自然日数组的紧急购电时段标签。"""
    segs, start = [], None
    for t, v in enumerate(np.r_[z, 0.0]):
        if v > tol and start is None:
            start = t
        elif v <= tol and start is not None:
            segs.append({'time_range': '%s-%s' % (clock_min(start*10), clock_min(t*10)),
                         'energy_kwh': float(z[start:t].sum())})
            start = None
    return segs

# ----------------------------------------------------------------------
# 5. 全年回测
# ----------------------------------------------------------------------
def backtest(d0=0, d1=ND, K=30, stages=(0, 1, 2, 3), S0=6000.0, verbose=True):
    S, rec = S0, {}
    cold = max(float((_a1.L.values[-1]-_a1.G.values[-1])*DT), 0.0)
    committed_x = committed_q = cold
    for d in range(d0, d1):
        Sstart = S
        x, q, out, natural, S = solve_day(d, S, committed_q, K, stages)
        natural_x = np.r_[committed_x, x[:T-1]]
        natural_q = np.r_[committed_q, q[:T-1]]
        rec[d] = dict(x=x, q=q, S0=Sstart, S24=S,
                      natural_x=natural_x, natural_q=natural_q,
                      natural=natural, **out)
        committed_x, committed_q = float(x[-1]), float(q[-1])
        if verbose and d % 20 == 0:
            print(d, DSTR[d], 'S=%.0f' % S, flush=True)
    return rec, S

if __name__ == '__main__':
    import sys, time
    a, b = (int(sys.argv[1]), int(sys.argv[2])) if len(sys.argv) > 2 else (55, 60)
    t0 = time.time()
    rec, _ = backtest(a, b, verbose=False)
    tot = adj = emg = 0
    for d, r in rec.items():
        c1, c2, c3 = day_cost(r['x'], r['q'], r)
        tot += c1; adj += c2; emg += c3
        print('%s 总%.0f 购电%.0f 紧急%.0f 调整量%.0f kWh 紧急%.1f kWh'
              % (DSTR[d], c1, c2, c3, np.abs(r['q']-r['x']).sum(), r['z'].sum()))
    print('合计 %.0f (购电 %.0f + 紧急 %.0f)  %.0fs' % (tot, adj, emg, time.time()-t0))
