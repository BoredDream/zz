# 第三问数学推导（修正版）

## 1. 发布时刻与情景

发布时刻集合为 \(\mathcal R=\{0,6,12,18\}\)。在时刻 \(r\)，历史残差情景为

\[
N_{r,h}^{\omega}=\widehat N_{r,h}+\varepsilon_{r,h}^{\omega},
\qquad \pi_\omega=|\Omega_r|^{-1}.
\]

## 2. 非预见性修正

对同一发布时刻产生的所有情景，购电量 \(A_h\)、充电量 \(C_h\)、放电量 \(D_h\)及SOC \(S_h\)均不带情景上标；只有紧急购电 \(E_h^\omega\)和弃电 \(U_h^\omega\)是情景补救变量。因此当前动作不能随未来情景分叉。

对每个 \(h,\omega\)：

\[
A_h+D_h+E_h^\omega-C_h-U_h^\omega=N_h^\omega,
\]

\[
S_{h+1}-S_h-\eta_cC_h+D_h/\eta_d=0,
\]

\[
1200\le S_h\le10800,\quad 0\le C_h,D_h\le833.3333.
\]

## 3. 0:00计划模型

令午夜锁定购电量为 \(g^-\)，其余144个时段计划为 \(G_h\)。目标为

\[
\min\sum_{h=1}^{144}p_hG_h+
\frac1{|\Omega|}\sum_{\omega,h}5p_hE_h^\omega
-vS_H+\epsilon\sum_h(C_h+D_h),
\]

其中 \(v=0.9\min_hp_h\)。该模型没有完整表示未来6/12/18时信息到达的期权价值，故属于滚动近似。

## 4. 主结算口径：逐次提交、不退款

第 \(k\) 次调整前的有效合同为 \(A_h^{k-1}\)，调整后为 \(A_h^k\)：

\[
A_h^k-Q_{h,k}^++Q_{h,k}^-=A_h^{k-1},
\quad Q_{h,k}^+,Q_{h,k}^-\ge0.
\]

已支付的初始计划费和历史调整费是沉没成本。当前调整子问题目标为

\[
\min\sum_h\left(1.5p_hQ_{h,k}^++0.5p_hQ_{h,k}^-\right)
+\frac1{|\Omega|}\sum_{\omega,h}5p_hE_h^\omega-vS_H
+\epsilon\sum_h(C_h+D_h).
\]

自然日非紧急结算费用为

\[
C_d^{grid}=\sum_tp_tG_{d,t}+
\sum_{k\in\{6,12,18\}}\sum_t
\left(1.5p_tQ_{d,t,k}^++0.5p_tQ_{d,t,k}^-\right).
\]

## 5. 退款/最终净额敏感性

若允许取消计划并退还原价，且只按最终合同与原计划净额结算，则

\[
C_d^{grid,alt}=\sum_tp_t\left[A_{d,t}^{final}
+0.5|A_{d,t}^{final}-G_{d,t}|\right].
\]

此口径单独重新优化，并对主策略固定电量再结算一次。两者都只用于敏感性分析，不能在合同规则未明确前替代主口径。

## 6. 实际执行与总费用

每次求解后仅执行下一36个时段的共同 \(C_h,D_h\)。实际净负荷到达后

\[
\Delta_h=N_h^{act}-(A_h+D_h-C_h),
\quad E_h=(\Delta_h)^+,\quad U_h=(-\Delta_h)^+.
\]

总费用为

\[
C^{total}=\sum_d C_d^{grid}+\sum_{d,t}5p_tE_{d,t}.
\]
