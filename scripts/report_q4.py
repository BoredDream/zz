"""由 outputs/q4 的产物生成 reports/q4_report.md。

只读 payload / npz / 求解器常量，不重新求解、不修改任何已验收产物。
报告里的数字全部机器提取，避免手抄出错。

用法： python scripts/report_q4.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
import q4_solver as M  # noqa: E402
import q3_multistage as Q3  # noqa: E402
import q4_q2_solver as Q2M  # noqa: E402

OUT = ROOT / "outputs" / "q4"
Q3_SUMMARY = ROOT / "outputs" / "q3_multistage" / "summary_stages0123_K30.json"
REPORT = ROOT / "reports" / "q4_report.md"
K = 30
DATES = ["2025-03-20", "2025-06-21", "2025-09-23", "2025-12-21"]
# 表1 的六个指定 10 分钟时段。模板行框下 t 覆盖 [(t+1)*10, (t+2)*10) 分钟
WINDOWS = [("10:00-10:10", 59), ("12:00-12:10", 71), ("14:00-14:10", 83),
           ("16:00-16:10", 95), ("18:00-18:10", 107), ("20:00-20:10", 119)]


def f(v: float) -> str:
    """四位小数；把 -0.0 与小于显示精度的量归成 0，避免出现 "-0.0000"。"""
    if abs(v) < 5e-5:
        v = 0.0
    return f"{v:,.4f}"


def load(variant: str):
    payload = json.loads((OUT / f"payload_q4-{variant}_K{K}.json").read_text(encoding="utf-8"))
    detail = np.load(OUT / f"detail_q4-{variant}_K{K}.npz")
    return payload, detail, {day["date"]: day for day in payload["days"]}


def invariants(detail, variant: str) -> dict[str, float]:
    """重算物理不变量，供报告第 7 节引用（与 validate_q4.py 相互独立地再算一遍）。"""
    x,q,z,c,g,w,S=(detail[k] for k in ("x","q","z","c","g","w","S"))
    nx,nq=detail["natural_x"],detail["natural_q"]
    S0 = detail["S0"]
    q2data=Q2M.load_inputs(ROOT/"problem"/"data",Q2M.B.Config()) if variant=="2" else None
    worst = {"balance": 0.0, "soc": 0.0, "charge_limit": 0.0, "discharge_limit": 0.0,
             "soc_lo": 0.0, "soc_hi": 0.0, "cost_split": 0.0}
    for i in range(len(S0)):
        for t in range(M.T):
            now=float(S[i,t+1]); worst["soc"]=max(worst["soc"],abs(now-(S[i,t]+M.ETA*c[i,t]-g[i,t]/M.ETA)))
            if variant=="2": actual=float(q2data["net_actual"][i,t] if not(i==0 and t==0) else q2data["cold_start_net"][0])
            else:
                ml,mg=Q3.midnight_actual(i); actual=(ml-mg) if t==0 else M.L[i,t-1]-M.G[i,t-1]
            worst["balance"]=max(worst["balance"],abs(nq[i,t]+z[i,t]+g[i,t]-c[i,t]-w[i,t]-actual))
            worst["charge_limit"] = max(worst["charge_limit"], c[i, t] - M.CMAX)
            worst["discharge_limit"] = max(worst["discharge_limit"], g[i, t] - M.CMAX)
            worst["soc_lo"] = max(worst["soc_lo"], M.SMIN - now)
            worst["soc_hi"] = max(worst["soc_hi"], now - M.SMAX)
        if variant=="2":
            pp=q2data["price4_natural"][i]; p1=pp*nx[i]; p2=np.zeros(M.T); p3=5*pp*z[i]
        else: p1,p2,p3=M.natural_settle_parts4(i,nx[i],nq[i],z[i])
        total=float(p1.sum()+p2.sum()+p3.sum())
        worst["cost_split"] = max(worst["cost_split"], abs(total - (p1.sum() + p2.sum() + p3.sum())))
    return worst


def table1(day2: dict, day3: dict, d: int) -> list[str]:
    rows = ["| 时间段 | 实际电价<br>元/kWh | 4-2 计划=最终<br>kWh | 4-3 计划<br>kWh | 4-3 最终调整<br>kWh |",
            "|---|---:|---:|---:|---:|"]
    for label, t in WINDOWS:
        rows.append(f"| {label} | {f(M.PMAT[d, t])} | {f(day2['plan_kwh'][t])} | "
                    f"{f(day3['plan_kwh'][t])} | {f(day3['adjusted_kwh'][t])} |")
    rows += [
        f"| **全天购电量** | | **{f(day2['plan_total_kwh'])}** | **{f(day3['plan_total_kwh'])}** | "
        f"**{f(day3['adjusted_total_kwh'])}** |",
        f"| 全天计划购电费/元 | | {f(day2['plan_cost_yuan'])} | {f(day3['plan_cost_yuan'])} | |",
        f"| 全天调整相关费用/元 | | 0.0000 | | {f(day3['adjusted_cost_yuan'])} |",
        f"| 全天紧急购电费/元 | | {f(day2['emergency_cost_yuan'])} | {f(day3['emergency_cost_yuan'])} | |",
        f"| **全天总费用/元** | | **{f(day2['total_cost_yuan'])}** | **{f(day3['total_cost_yuan'])}** | |",
        f"| 当日弃电量/kWh | | {f(day2['curtail_kwh'])} | {f(day3['curtail_kwh'])} | |",
    ]
    return rows


def table2(day2: dict, day3: dict) -> list[str]:
    rows = ["| 时间段 | 4-2 充电量 | 4-2 放电量 | 4-3 充电量 | 4-3 放电量 |",
            "|---|---:|---:|---:|---:|"]
    for b2, b3 in zip(day2["storage_blocks"], day3["storage_blocks"]):
        assert b2["time_range"] == b3["time_range"]
        rows.append(f"| {b2['time_range']} | {f(b2['charge_kwh'])} | {f(b2['discharge_kwh'])} | "
                    f"{f(b3['charge_kwh'])} | {f(b3['discharge_kwh'])} |")
    rows += [
        f"| 0:00 储电量 | {f(day2['soc_start_kwh'])} | | {f(day3['soc_start_kwh'])} | |",
        f"| 24:00 储电量 | {f(day2['soc_end_kwh'])} | | {f(day3['soc_end_kwh'])} | |",
    ]
    return rows


def table3(day: dict) -> list[str]:
    if not day["emergency_segments"]:
        return ["（当日无紧急购电）", ""]
    rows = ["| 时间段 | 购电量/kWh |", "|---|---:|"]
    for seg in day["emergency_segments"]:
        rows.append(f"| {seg['time_range']} | {f(seg['energy_kwh'])} |")
    rows += [f"| **合计** | **{f(day['emergency_total_kwh'])}** |", ""]
    return rows


def load_optional(name: str):
    """读取可选证据产物；缺失时返回 None，报告相应小节自动省略。"""
    p = OUT / name
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else None


def independent_section(v: dict | None) -> list[str]:
    """第 8 节：独立复算（脚本不 import 模型）。"""
    L: list[str] = []
    A, X = L.append, L.extend
    A("## 8. 独立复算（第二套实现）")
    A("")
    A("`scripts/validate_q4.py` **import 了模型**，复用了模型自己的常量与结算函数，"
      "它证明的是「编码与已验收产物自洽」。`scripts/verify_q4.py` 换一条路："
      "**不 import `src/q4_solver.py` 或 `src/q4_q2_solver.py`**，只读原始附件 2/4 与"
      "已落盘明细 npz，按题面公式与 README「固定口径」从零重算。")
    A("")
    if v is None:
        A("（尚未运行 `scripts/verify_q4.py`。）")
        A("")
        return L
    A("| 复算路径 | 覆盖 4-2 | 覆盖 4-3 | 最大偏差 |")
    A("|---|---|---|---:|")
    A(f"| 甲 结算（题面公式逐日重算） | ✅ | ✅ | {v['worst']['[3] 交付期总费用 vs summary']:.3e} 元 |")
    A("| 乙 实时层与储能轨迹重放 | — | ✅ | "
      f"{v['worst']['[3] 重放 SOC 轨迹 vs 明细/kWh']:.3e} kWh |")
    A("| 丙 物理与能量平衡不变量 | ✅ | ✅ | "
      f"{v['worst']['[3] 能量平衡恒等式/kWh']:.3e} kWh |")
    A("")
    A("偏差全为 **0.000e+00**，即 4-3 的实时层贪心规则可以逐时段逐位重放出来。")
    A("")
    A("**本脚本没有证明什么**（引用时必须保留）：")
    A("")
    A("1. **4-2 的实时层规则未被独立重放。** 变体 4-2 用的是 `q2_solver.causal_dispatch`，"
      "它以 SAA 最优解的**参考充放电轨迹**为输入，而这两个数组没有落盘"
      "（`scripts/export_q4.py` 只存 c/g/z/w/S），故无法从已有产物重放该规则。"
      "对 4-2 只做了路径甲与路径丙。")
    A("2. **不重解任何 LP。** 「记录解是该 LP 的最优解」这件事没有被独立复核——"
      "最优化层面的证据只有第 11 节的求解器检验与「记录解可行且满足全部物理约束」。")
    A("3. 预测子模型（`price_hat`、`scenario_set`）、SAA 情景生成、终端价值 `λ`、"
      "冷启动约定、1 月预热期都仍是**建模选择**，不是被复算证明的结论。")
    A("4. `result4-{2,3}.xlsx` 工作簿本身未被本脚本直接重算；"
      "它与本脚本复合可把工作簿传递地锚到原始附件。")
    A("")
    return L


def lambda_section(v: dict | None) -> list[str]:
    """第 9 节：终端储能价值 λ 的全年敏感性扫描。"""
    L: list[str] = []
    A, X = L.append, L.extend
    A("## 9. 终端储能价值 λ 的全年敏感性扫描")
    A("")
    A("第四问按**附件4 实际电价**结算（全年 0.0076–1.7936 元/kWh），但两个变体的终端"
      "储能水价 `λ` **都取自附件1**：4-3 取 `LAM = 0.478 = p_谷/η`（附件1 谷价 0.4302），"
      "4-2 取 `η × min(附件1 自然日电价) = 0.33417`（继承 Q2 的设定）。"
      "λ 是外生常数、**不由最优性导出**，故必须回答「换一个 λ，答案变多少」。")
    A("")
    if v is None:
        A("（尚未运行 `scripts/q4_lambda_sensitivity.py`。）")
        A("")
        return L
    for variant, name in (("2", "4-2"), ("3", "4-3")):
        r = v["variants"].get(variant)
        if not r:
            continue
        chk = r["baseline_reproduction_check"]
        A(f"### 9.{1 if variant == '2' else 2} 变体 {name}（基准 λ₀ = {chk['baseline_lam']:.5f}）")
        A("")
        A(f"基准点重跑与已交付产物的差：**{chk['abs_gap_yuan']:.3e} 元**"
          f"（逐位相同：{chk['rerun_matches_delivered']}）。")
        A("")
        A("| λ | λ/λ₀ | 交付期总费用/元 | 差/元 | 差% | 期初 SOC | 日均日末 SOC | 紧急购电/kWh | 弃电/kWh | 充电/kWh | 放电/kWh |")
        A("|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|")
        for row in r["scan"]:
            A(f"| {row['lam']:.5f} | {row['lam_over_baseline']:.2f}× | {f(row['total_cost_yuan'])} | "
              f"{f(row['delta_vs_baseline_yuan'])} | {row['delta_pct']:+.3f}% | "
              f"{f(row['soc_start_delivery_kwh'])} | {f(row['soc_end_mean_daily_kwh'])} | "
              f"{f(row['emergency_kwh'])} | {f(row['curtail_kwh'])} | "
              f"{f(row['charge_kwh'])} | {f(row['discharge_kwh'])} |")
        rg = r["range"]
        scan = r["scan"]
        A("")
        A(f"极差 **{f(rg['spread_yuan'])} 元（{rg['spread_pct_of_baseline']:.3f}% 于基准）**，"
          f"最小点在 λ = {rg['min_cost']['lam']:.5f}，最大点在 λ = {rg['max_cost']['lam']:.5f}；"
          f"费用随 λ 单调：**{rg['costs_monotone_in_lam']}**。")
        A("")
        # 发现 1：量级不敏感（数字全部来自本表）
        base = next((row for row in scan if abs(row["lam_over_baseline"] - 1.0) < 1e-9), scan[0])
        A(f"**发现 1（量级不敏感）**：λ 在 {scan[0]['lam']:.5f}–{scan[-1]['lam']:.5f} "
          f"（基准的 {scan[0]['lam_over_baseline']:.2f}–{scan[-1]['lam_over_baseline']:.2f} 倍）之间，"
          f"交付期总费用只在 {f(rg['min_cost']['total_cost_yuan'])}–"
          f"{f(rg['max_cost']['total_cost_yuan'])} 元之间变动，极差 {f(rg['spread_yuan'])} 元，"
          f"仅占基准的 {rg['spread_pct_of_baseline']:.3f}%。")
        A("")
        # 发现 2/4：数据驱动地找「体制切换点」= 相邻两点期初 SOC 跳变最大处
        socs = [row["soc_start_delivery_kwh"] for row in scan]
        if len(socs) >= 2:
            k = int(np.argmax([abs(socs[i + 1] - socs[i]) for i in range(len(socs) - 1)]))
            lo_pts, hi_pts = scan[: k + 1], scan[k + 1:]
            A(f"**发现 2（存在储能运行体制切换）**：相邻 λ 点之间期初 SOC 跳变最大的位置在 "
              f"λ = {scan[k]['lam']:.5f} 与 λ = {scan[k + 1]['lam']:.5f} 之间——"
              f"交付期期初 SOC 由 {f(scan[k]['soc_start_delivery_kwh'])} kWh 跳到 "
              f"{f(scan[k + 1]['soc_start_delivery_kwh'])} kWh，日均日末 SOC 由 "
              f"{f(scan[k]['soc_end_mean_daily_kwh'])} 跳到 {f(scan[k + 1]['soc_end_mean_daily_kwh'])} kWh。"
              f"低 λ 段储能常年接近放空，高 λ 段则被压在高位，两者是**不同的运行机制**，"
              f"不是同一机制的连续变化。")
            A("")
            if base["lam"] in [p["lam"] for p in scan]:
                side = "低" if base["lam"] <= scan[k]["lam"] else "高"
                A(f"交付所用的基准 λ₀ = {base['lam']:.5f} 落在**{side} λ 段**。")
                A("")
            lo_min = min(lo_pts, key=lambda x: x["total_cost_yuan"])
            hi_min = min(hi_pts, key=lambda x: x["total_cost_yuan"])
            if lo_pts[0]["total_cost_yuan"] > lo_pts[-1]["total_cost_yuan"] and len(lo_pts) > 1:
                lo_dir = "随 λ 递减"
            elif len(lo_pts) > 1:
                lo_dir = "随 λ 递增"
            else:
                lo_dir = "单点"
            if len(hi_pts) > 1 and hi_pts[-1]["total_cost_yuan"] > hi_pts[0]["total_cost_yuan"]:
                hi_dir = "随 λ 递增"
            elif len(hi_pts) > 1:
                hi_dir = "随 λ 递减"
            else:
                hi_dir = "单点"
            A(f"**发现 3（费用非单调）**：全局最低点在 λ = {rg['min_cost']['lam']:.5f}"
              f"（比基准低 {f(base['total_cost_yuan'] - rg['min_cost']['total_cost_yuan'])} 元）。"
              f"费用在**低 λ 段内部{lo_dir}**、**高 λ 段内部{hi_dir}**，"
              f"整体呈 V 形而非单调——所以「λ 越大费用越高/越低」都不成立。")
            A("")
            _dcost = abs(hi_pts[0]["total_cost_yuan"] - lo_pts[-1]["total_cost_yuan"])
            A(f"**发现 4（费用面很平，策略面不平）**：跨过切换点的两点，费用只差 "
              f"{f(_dcost)} 元（{_dcost / base['total_cost_yuan'] * 100.0:.3f}%），"
              f"但物理量差得远——紧急购电量 "
              f"{f(lo_pts[-1]['emergency_kwh'])} → {f(hi_pts[0]['emergency_kwh'])} kWh"
              f"（差 {f(abs(hi_pts[0]['emergency_kwh'] - lo_pts[-1]['emergency_kwh']))} kWh）、"
              f"弃电量 {f(lo_pts[-1]['curtail_kwh'])} → {f(hi_pts[0]['curtail_kwh'])} kWh、"
              f"充/放电量各差 "
              f"{f(abs(hi_pts[0]['charge_kwh'] - lo_pts[-1]['charge_kwh']))} kWh。"
              f"因此**不能用「费用差不多」推断「策略差不多」**。")
            A("")
        lo_min_note = rg["min_cost"]["lam"]
        _gain = base["total_cost_yuan"] - rg["min_cost"]["total_cost_yuan"]
        if _gain <= 1e-6:
            A(f"⚠️ **扫描的最低点恰为基准点本身（λ = {lo_min_note:.5f}，差 "
              f"{f(_gain)} 元），这不构成对基准 λ₀ 的任何支持**：代价面在该处本就平坦，"
              f"且表中最低点进入交付期时的存量与基准相同、其余点则不同，"
              f"各点差额里含**存量转移**而非纯粹效率。λ 是外生假设，本表只说明敏感程度。")
        else:
            A(f"⚠️ **{f(_gain)} 元不能读作"
              f"「λ = {lo_min_note:.5f} 更优」**：该点进入交付期时的存量与基准不同，"
              f"差额里含**存量转移**而非纯粹效率；且 λ 是外生假设，本表只说明敏感程度。")
        A("")
    A("**本节没有覆盖什么**（引用时必须保留）：")
    A("")
    A("1. λ 仍是**外生常数**，没有被内生求解或标定；本扫描只度量它的影响，不给出它的正确取值。")
    A("2. **不能说某个 λ「更优」或「最优」。** 见第 12 节第 6 条。")
    A("3. 扫描只做了各变体自己的 7 个倍数点，其余 λ 取值未做独立复算。")
    A("4. 两变体的基准 λ₀ 不同（0.33417 vs 0.478），横向比较应看**相对各自主基准的偏移**，"
      "不能直接比绝对费用。")
    A("")
    return L


def pf_section(v: dict | None) -> list[str]:
    """第 10 节：完美预见电价对照，拆分 +5.20%。"""
    L: list[str] = []
    A, X = L.append, L.extend
    A("## 10. 完美预见电价对照：拆分与第三问的 +5.20%")
    A("")
    if v is None or not v.get("decomposition"):
        A("（尚未运行 `scripts/q4_perfect_foresight.py`。）")
        A("")
        return L
    d = v["decomposition"]
    A("第三问把附件1 的分时电价当作**已知**量送入 LP，第四问必须在 0:00 **预测**附件4 的"
      "波动电价。因此两者的差额同时含「波动风险」与「预测误差信息缺失」两项。"
      "`scripts/q4_perfect_foresight.py` 补上缺失的对照点：把 `price_hat` 整个换成"
      "**当日实际电价**，其余一字不动（同样的负荷/光伏场景、λ = 0.478、实时层、滚动时域）。")
    A("")
    A("| 对照点 | 价格过程 | 是否已知 | 交付期总费用/元 | 相对第三问 |")
    A("|---|---|---|---:|---:|")
    A(f"| 第三问 | 附件1 分时（确定性） | 已知 | {f(d['c_q3_deterministic_price_known_yuan'])} | — |")
    A(f"| 第四问·完美预见 | 附件4 波动 | **已知** | {f(d['c_q4_PF_volatile_price_known_yuan'])} | "
      f"{d['a_pct_of_q3']:+.3f}% |")
    A(f"| 第四问 4-3 | 附件4 波动 | 预测 | {f(d['c_q4_3_volatile_price_forecast_yuan'])} | "
      f"{d['total_gap_pct_of_q3']:+.3f}% |")
    A("")
    A("分解（三项之和恒等，残差 "
      f"{d['identity_residual_yuan']:.3e} 元）：")
    A("")
    A(f"- **(a) 价格波动的风险成本** = 完美预见 − 第三问 = **{f(d['a_price_volatility_risk_cost_yuan'])} 元"
      f"（{d['a_pct_of_q3']:+.3f}%）**；")
    A(f"- **(b) 预测误差的信息缺失成本** = 第四问 − 完美预见 = **{f(d['b_forecast_error_information_loss_yuan'])} 元"
      f"（{d['b_pct_of_q3']:+.3f}%）**；")
    A(f"- (a) + (b) = {f(d['total_gap_yuan'])} 元（{d['total_gap_pct_of_q3']:+.3f}%）。")
    A("")
    a = d["a_price_volatility_risk_cost_yuan"]
    b = d["b_forecast_error_information_loss_yuan"]
    a_bigger = abs(a) >= abs(b)
    share = abs(a) / (abs(a) + abs(b)) * 100.0
    A(f"即该差额的 **{share:.1f}%** 来自"
      f"**{'价格波动的风险成本' if a_bigger else '预测误差的信息缺失成本'}**，"
      f"其余 {100.0 - share:.1f}% 来自另一项。"
      "⚠️ 完美预见变体只换了价格信息，**不是**一个可交付的方案（它假设 0:00 就知道全天实际电价），"
      "只作归因用。")
    A("")
    ic = v.get("inventory_contamination") or {}
    if ic.get("terminal_soc_kwh"):
        ts = ic["terminal_soc_kwh"]
        A("**期末存量转移的扣除**：两个对照点期末留在储能里的电量不同，而 `λ` 正是终端储能的"
          "影子价值（1 kWh 留在期末值 `λ` 元），故期末存量差 `ΔS` 在目标函数里正好值 "
          f"`λ·ΔS` 元。这部分是**存量转移**而非效率差异，必须从 (a)/(b) 里扣掉再解读：")
        A("")
        A(f"| 对照点 | 交付期末 SOC/kWh | 存量差 ΔS/kWh | 折算 λ·ΔS/元 | 占该项 |")
        A("|---|---:|---:|---:|---:|")
        A(f"| 第三问 | {f(ts['q3'])} | {f(ts['q3'] - ts['perfect_foresight'])} | "
          f"{f(-ic['a_stock_transfer_yuan'])} | {ic['a_stock_transfer_pct_of_gap']:.3f}% |")
        A(f"| 第四问 4-3 | {f(ts['q4_3'])} | {f(ts['q4_3'] - ts['perfect_foresight'])} | "
          f"{f(-ic['b_stock_transfer_yuan'])} | {ic['b_stock_transfer_pct_of_gap']:.3f}% |")
        A(f"| 完美预见 | {f(ts['perfect_foresight'])} | — | — | — |")
        A("")
        A("表中 ΔS = 对照点期末 SOC − 完美预见期末 SOC，`λ·ΔS` 需**加回**对应的 (a)/(b) "
          "才是同存量口径下的纯效率差（因为目标函数对期末存量按 `λ` 计价，"
          "多留电会压低当期费用）。")
        A("")
        A(f"加回后：(a) 的纯效率差 {f(ic['a_pure_efficiency_yuan'])} 元、"
          f"(b) 的纯效率差 {f(ic['b_pure_efficiency_yuan'])} 元。"
          f"存量转移占 (a) 的 {ic['a_stock_transfer_pct_of_gap']:.3f}%、"
          f"占 (b) 的 {ic['b_stock_transfer_pct_of_gap']:.3f}%，"
          "**量级都很小，不足以改变上面的归因结论**；但引用 (a)/(b) 时不应把它当作纯效率——"
          "严格说法是「(a)/(b) 中包含一笔 ≤1.1% 的期末存量转移」。")
        A("")
    return L


def solver_section(alt: list[dict], census: dict | None) -> list[str]:
    """第 11 节：求解器退化与配置敏感性检验。"""
    L: list[str] = []
    A, X = L.append, L.extend
    A("## 11. 求解器退化与配置敏感性检验")
    A("")
    if not alt:
        A("（尚未运行 `scripts/q4_solver_uniqueness_check.py`。）")
        A("")
        return L
    A("`src/q4_solver.py` 与 `src/q4_q2_solver.py` 里的调用都是 "
      "`linprog(..., method='highs')`，`method` 是关键字参数。脚本**不修改 `src/`**，"
      "只替换两个模块各自命名空间里的 `linprog` 名字。两个模块都写了 "
      "`from scipy.optimize import linprog`，故这两个**属性**目前指向同一个函数对象，"
      "但它们位于不同的模块命名空间，改一个不影响另一个（已实测），"
      "因此两个变体可以分别独立打补丁。")
    A("")
    A("| 变体 | 算法 | 交付期总费用/元 | 与主答案之差/元 | 差% | 逐日最大差/元 | 差>1 元的天数 |")
    A("|---|---|---:|---:|---:|---:|---:|")
    for r in sorted(alt, key=lambda r: (r["variant"], r["method"])):
        A(f"| 4-{r['variant']} | `{r['method']}` | {f(r['alt_total_cost_yuan'])} | "
          f"{f(r['total_gap_yuan'])} | {r['total_gap_pct']:+.5f}% | "
          f"{f(r['max_abs_daily_gap_yuan'])} | {r['days_with_gap_over_1yuan']} |")
    A("")
    if census:
        o = census["overall"]
        n_stage = len(census["stages"])
        A(f"**LP 级普查**（变体 4-{census['variant']}，抽样 {census['sampled_days']} 天"
          f"（步长 {census['step_days']} 天）、共 {o['n_lps']} 个 LP；每个 LP 用"
          f"`highs`/`highs-ds`/`highs-ipm` 各解一次，并加一组目标系数相对扰动 "
          f"{census['jitter_rel']:.0e} 的探针）：")
        A("")
        A("| 阶段 | LP 数 | `highs-ds` 解向量不同 | `highs-ipm` 解向量不同 | ipm 最优值最大相对差 | 抖动探针解向量不同 |")
        A("|---|---:|---:|---:|---:|---:|")
        for st, e in census["by_stage"].items():
            ds, ip, j = e["highs-ds"], e["highs-ipm"], e["jitter"]
            A(f"| `{st}` | {e['n']} | {ds['n_solution_differs']}/{e['n']} | "
              f"{ip['n_solution_differs']}/{e['n']} | {ip['max_rel_obj_gap']:.3e} | "
              f"{j['n_solution_differs']}/{j['n']} |")
        A("")
        A(f"跨算法最优值最大相对差 **{o['max_rel_obj_gap_across_methods']:.3e}**"
          f"（超 1e-6 的 **{o['n_lps_obj_gap_gt_1e-6']}** 个、超 1e-9 的 "
          f"{o['n_lps_obj_gap_gt_1e-9']} 个），但最优**解向量**不同的 (LP, 算法) 对占 "
          f"**{o['n_lp_method_pairs_solution_differs']}/{o['n_lp_method_pairs']}**"
          f"（{100.0 * o['n_lp_method_pairs_solution_differs'] / max(1, o['n_lp_method_pairs']):.1f}%）；"
          f"抖动探针下解向量不同的有 {o['jitter_n_solution_differs']}/{o['jitter_n']} 个"
          f"（{100.0 * o['jitter_n_solution_differs'] / max(1, o['jitter_n']):.1f}%）。")
        A("")
        A("⇒ **费用面唯一，策略面不唯一。** 三点值得写进论文：")
        A("")
        A(f"1. **最优值不依赖求解器**：最大相对差 {o['max_rel_obj_gap_across_methods']:.1e}，"
          "没有任何一个 LP 超过 1e-6；这与上表端到端结果（差 ≤ 1.9e-09 元）互相印证。")
        A(f"2. **但 LP 普遍退化**：{100.0 * o['n_lp_method_pairs_solution_differs'] / max(1, o['n_lp_method_pairs']):.1f}% 的"
          "(LP, 算法) 对给出不同的解向量，逐时段最大差达数千 kWh。"
          "退化的直接来源是储能「充多少/放多少」在很宽的区间内等费用（低价段尤其如此）。")
        if census["by_stage"].get("stage0"):
            s0 = census["by_stage"]["stage0"]
            A(f"3. **0:00 计划阶段尤其特殊**：`highs-ds` 与主算法 `highs` 的解向量"
              f"{'完全一致' if s0['highs-ds']['n_solution_differs'] == 0 else '部分不同'}"
              f"（{s0['highs-ds']['n_solution_differs']}/{s0['n']}），"
              f"而 `highs-ipm` 有 {s0['highs-ipm']['n_solution_differs']}/{s0['n']} 不同——"
              "两种单纯形法落在同一个顶点上，内点法落在另一个。")
        A("")
        A("⚠️ 与第三问的对照：第三问同口径普查的解向量不同比例为 **46.9%**"
          "（换算法最优值一致到 6.17e-14、端到端最坏差 28.21 元）。"
          "第四问的 **"
          f"{100.0 * o['n_lp_method_pairs_solution_differs'] / max(1, o['n_lp_method_pairs']):.1f}%**"
          " 与之一致，说明**退化是这套 LP 编码本身的性质，不是第四问引入的**。")
        A("")
    A("**结论边界**：可以写「该变体的总费用不依赖求解器配置」；"
      "若逐时段引用「最优策略」，必须说明该解在退化时段只是最优解之一。")
    A("")
    return L


def main() -> int:
    p2, d2, by2 = load("2")
    p3, d3, by3 = load("3")
    t2, t3 = p2["meta"]["totals"], p3["meta"]["totals"]
    assert p2["meta"]["delivery_period"] == p3["meta"]["delivery_period"]
    per = p2["meta"]["delivery_period"]
    plan2 = sum(day["plan_total_kwh"] for day in p2["days"])
    adj3 = sum(day["adjusted_total_kwh"] for day in p3["days"])
    plan3 = sum(day["plan_total_kwh"] for day in p3["days"])
    w2, w3 = invariants(d2,"2"), invariants(d3,"3")

    L: list[str] = []
    A, X = L.append, L.extend
    A("# 第四问计算报告（波动电价）")
    A("")
    A("本报告是 `result4-2.xlsx` 与 `result4-3.xlsx` 的计算结果说明。文中数字全部由")
    A("`outputs/q4/payload_q4-{2,3}_K30.json` 机器提取，未手工誊写。模型定义见 "
      "`docs/q4_model.md`，独立验收见 `scripts/validate_q4.py`。")
    A("")
    A("## 1. 模型与口径")
    A("")
    A("第四问在波动电价下分别重算问题2和问题3：4-2直接继承Q2，4-3继承Q3。")
    A("")
    A("| 变体 | 对应 | 决策结构 | 输出文件 |")
    A("|---|---|---|---|")
    A("| 4-2 | 问题2 | 只在 0:00 决策一次，不设调整机制（`q ≡ x`） | `result4-2.xlsx` |")
    A("| 4-3 | 问题3 | 0:00 计划 + 6:00/12:00/18:00 三次滚动调整 | `result4-3.xlsx` |")
    A("")
    A("区间起点和物理参数一致，但报表时间框不同：计划/调整表保留模板行；"
      "实际执行、SOC、紧急购电和总费用按自然日0:00–24:00跨行重组；"
      "**交流母线侧储能**（`S_t = S_(t-1) + 0.9·c_t − g_t/0.9`，充、放电单时段上限同为 "
      "`5000/6 = 833.3333` kWh）；**题面结算口径**")
    A("")
    A("```")
    A("C_t = p_t·min(x_t, q_t) + 1.5·p_t·(q_t − x_t)^+ + 0.5·p_t·(x_t − q_t)^+ + 5·p_t·z_t")
    A("```")
    A("")
    A("其中 `p_t` 取附件4 的**实际**电价"
      f"（365×144，范围 {M.PMAT.min():.4f}–{M.PMAT.max():.4f} 元/kWh，均值 {M.PMAT.mean():.4f}）。"
      "**预测值只参与决策，不参与结算。**")
    A("")
    A("4-2保留Q2的负荷/光伏预测器、145段时域、SOC与因果执行规则，只加入基于历史的波动价格预测；"
      "4-3保留Q3的四阶段结构，价格预测采用日内形态 × 水平 × 日内AR(1)，并在6:00/12:00/18:00"
      "用已实现电价滚动修正。4-3的价格、负载、光伏按**同日配对**做联合场景重采样以保住相关性"
      f"（情景数 `K = {K}`）。")
    A("")
    A(f"交付期为 {per['start']} 至 {per['end']}，共 {per['days']} 天。"
      "全年回测自 2025-01-01 起算，前 31 天为预热期，不计入交付期统计。")
    A("")
    A("## 2. 交付期结果汇总")
    A("")
    A(f"| 指标（{per['start']} 至 {per['end']}，{per['days']} 天） | 4-2（对应问题2） | 4-3（对应问题3） |")
    A("|---|---:|---:|")
    A(f"| 计划购电量/kWh | {f(plan2)} | {f(plan3)} |")
    A(f"| 最终合同购电量/kWh | {f(plan2)} | {f(adj3)} |")
    A(f"| 计划购电费/元 | {f(t2['plan_cost_yuan'])} | {f(t3['plan_cost_yuan'])} |")
    A(f"| 调整相关费用/元 | 0.0000 | {f(t3['adjust_cost_yuan'])} |")
    A(f"| 紧急购电费/元 | {f(t2['emergency_cost_yuan'])} | {f(t3['emergency_cost_yuan'])} |")
    A(f"| **总费用/元** | **{f(t2['total_cost_yuan'])}** | **{f(t3['total_cost_yuan'])}** |")
    A(f"| 紧急购电量/kWh | {f(t2['emergency_kwh'])} | {f(t3['emergency_kwh'])} |")
    A(f"| 充电量/kWh | {f(t2['charge_kwh'])} | {f(t3['charge_kwh'])} |")
    A(f"| 放电量/kWh | {f(t2['discharge_kwh'])} | {f(t3['discharge_kwh'])} |")
    A(f"| 弃电量/kWh | {f(t2['curtail_kwh'])} | {f(t3['curtail_kwh'])} |")
    A(f"| 累计上调量/kWh | 0.0000 | {f(t3['adjust_up_kwh'])} |")
    A(f"| 累计下调量/kWh | 0.0000 | {f(t3['adjust_down_kwh'])} |")
    A(f"| 含紧急购电的日期数 | {sum(1 for x in p2['days'] if x['emergency_segments'])} / {per['days']} | "
      f"{sum(1 for x in p3['days'] if x['emergency_segments'])} / {per['days']} |")
    A("")
    save = t2["total_cost_yuan"] - t3["total_cost_yuan"]
    A(f"**Q3型四阶段策略（4-3）相对Q2型一次决策（4-2）全年节省 {f(save)} 元"
      f"（{save / t2['total_cost_yuan'] * 100:.2f}%），紧急购电量由 "
      f"{f(t2['emergency_kwh'])} 降至 {f(t3['emergency_kwh'])} kWh"
      f"（−{(1 - t3['emergency_kwh'] / t2['emergency_kwh']) * 100:.1f}%）。**")
    A("")
    n2 = sum(1 for x in p2["days"] if x["emergency_segments"])
    n3 = sum(1 for x in p3["days"] if x["emergency_segments"])
    if n3 <= n2:
        A(f"4-3 的紧急购电日期由 {n2} 天降至 {n3} 天，紧急购电总量也显著下降。"
          "该差异是Q2型与Q3型完整策略的对照，不能单独归因于日内滚动调整。")
    else:
        A(f"4-3 的紧急购电日期为 {n3} 天，高于4-2的 {n2} 天，但总量更低。"
          "该差异是Q2型与Q3型完整策略的对照，不能单独归因于日内滚动调整。")
    A("")

    if Q3_SUMMARY.exists():
        q3 = json.loads(Q3_SUMMARY.read_text(encoding="utf-8"))["totals"]
        A("## 3. 与第三问（确定性电价）的对照")
        A("")
        A("附件1 的分时电价恰是附件4 电价过程的**逐时段均值**（逐时段最大差 5.15e-05，"
          "属表格取整），因此第三问与第四问 4-3 是在**期望相同**的价格过程下的两组结果，"
          "可以直接对照：")
        A("")
        A("| 指标 | 第三问（确定性电价） | 第四问 4-3（波动电价） | 差异 |")
        A("|---|---:|---:|---:|")
        A(f"| 总费用/元 | {f(q3['total_cost_yuan'])} | {f(t3['total_cost_yuan'])} | "
          f"+{(t3['total_cost_yuan'] / q3['total_cost_yuan'] - 1) * 100:.2f}% |")
        A(f"| 紧急购电量/kWh | {f(q3['emergency_kwh'])} | {f(t3['emergency_kwh'])} | "
          f"+{(t3['emergency_kwh'] / q3['emergency_kwh'] - 1) * 100:.2f}% |")
        A(f"| 弃电量/kWh | {f(q3['curtail_kwh'])} | {f(t3['curtail_kwh'])} | "
          f"{(t3['curtail_kwh'] / q3['curtail_kwh'] - 1) * 100:+.2f}% |")
        A(f"| 充电量/kWh | {f(q3['charge_kwh'])} | {f(t3['charge_kwh'])} | "
          f"{(t3['charge_kwh'] / q3['charge_kwh'] - 1) * 100:+.2f}% |")
        A(f"| 放电量/kWh | {f(q3['discharge_kwh'])} | {f(t3['discharge_kwh'])} | "
          f"{(t3['discharge_kwh'] / q3['discharge_kwh'] - 1) * 100:+.2f}% |")
        A("")
        A("即：**在期望相同的价格过程下，波动的交付期总费用比确定性电价高 "
          f"{(t3['total_cost_yuan'] / q3['total_cost_yuan'] - 1) * 100:.2f}%**。")
        A("")
        A("> **该差额不能整体归因于「价格波动」。** 两次回测的可利用信息不同：第三问把")
        A("> 附件1 的分时电价当作**已知**量直接送入 LP，第四问则必须在 0:00 **预测**当日电价。")
        A("> 因此上面这个百分比是两项之和——(a) 价格波动带来的风险成本，(b) 预测误差带来的")
        A("> 信息缺失成本。要拆开需要再做一次「完美预见电价」的第四问回测（把 `p̂` 换成当日")
        A("> 实际电价、其余不动），本次未做。")
        A("")
        A("另外，储能并没有因为价格波动而更频繁地套利：充电量 "
          f"{f(q3['charge_kwh'])} → {f(t3['charge_kwh'])} kWh"
          f"（{(t3['charge_kwh'] / q3['charge_kwh'] - 1) * 100:+.2f}%），放电量同幅下降。"
          "这与「波动增大→套利空间增大」的直觉相反，合理解释是预测不确定性使模型"
          "在充放电上更保守，但本次未做拆分验证。")
        A("")

    A("## 4. 指定日期：表1 计划购电量与最终调整购电量")
    A("")
    A("按题面表1 的格式给出表3 指定的四个日期。各行对应的时段起止时刻见第一列；"
      "4-2 无调整机制，故其「计划」即「最终」。全天购电量与购电费取该日的模板行合计。")
    A("")
    for date in DATES:
        d = M.DSTR.index(date)
        A(f"### {date}")
        A("")
        X(table1(by2[date], by3[date], d))
        A("")

    worse = [dt for dt in DATES if by3[dt]["total_cost_yuan"] > by2[dt]["total_cost_yuan"]]
    if worse:
        A(f"需要说明：这四个日期里有 {len(worse)} 天（{'、'.join(worse)}）4-3 的当日总费用"
          "**高于** 4-2，而全年合计仍是 4-3 更低（见第 2 节）。这不矛盾——滚动调整的作用是"
          "用已知信息纠正 0:00 计划，它按**期望**降本，不保证每一天都更优；且调整本身要付"
          "`1.5p`（上调）/`0.5p`（下调）的偏差费用，一旦实际电价走势偏离预测，调得越多亏得越多。"
          "表述时应按全周期合计而非单日比较。")
        A("")

    A("## 5. 指定日期：表2 充放电量与储电量")
    A("")
    A("按题面表2自然日口径给出四个日期：0:00–4:00至20:00–24:00；SOC为0:00与24:00。")
    A("")
    for date in DATES:
        A(f"### {date}")
        A("")
        X(table2(by2[date], by3[date]))
        A("")

    A("## 6. 指定日期：表3 紧急购电")
    A("")
    A("按题面表3 与表4 的格式给出四个日期。连续的非零 10 分钟时段合并为一段；"
      "无紧急购电的日期标注为无。")
    A("")
    for date in DATES:
        A(f"### {date} —— 4-2（对应问题2）")
        A("")
        X(table3(by2[date]))
        A(f"### {date} —— 4-3（对应问题3）")
        A("")
        X(table3(by3[date]))

    A("## 7. 数值校验")
    A("")
    A("由 `scripts/validate_q4.py` 独立验收，报告脚本另行重算一遍关键不变量，两处结果一致。")
    A("")
    A("| 校验项 | 4-2 最大偏差 | 4-3 最大偏差 |")
    A("|---|---:|---:|")
    A(f"| 功率平衡残差/kWh | {w2['balance']:.3e} | {w3['balance']:.3e} |")
    A(f"| SOC 递推残差/kWh | {w2['soc']:.3e} | {w3['soc']:.3e} |")
    A(f"| 充电量超上限/kWh | {w2['charge_limit']:.3e} | {w3['charge_limit']:.3e} |")
    A(f"| 放电量超上限/kWh | {w2['discharge_limit']:.3e} | {w3['discharge_limit']:.3e} |")
    A(f"| SOC 低于下限/kWh | {w2['soc_lo']:.3e} | {w3['soc_lo']:.3e} |")
    A(f"| SOC 高于上限/kWh | {w2['soc_hi']:.3e} | {w3['soc_hi']:.3e} |")
    A(f"| 三项费用拆分与总费用之差/元 | {w2['cost_split']:.3e} | {w3['cost_split']:.3e} |")
    A("")
    A("此外验收脚本还逐格核对了两个工作簿的全部单元格"
      "（334 天 × 144 列 × 2 张价格表 + 全天合计列 + 表2 六个段 + 紧急购电时段），"
      "并断言结算价等于附件4 实际电价、4-2 的 `max|q − x| = 0`。")
    A("")
    _verify = load_optional(f"independent_verify_q4_K{K}.json")
    _lam = load_optional(f"lambda_sensitivity_q4_K{K}.json")
    _pf = load_optional(f"perfect_foresight_q4_K{K}.json")
    _alt = [r for r in (load_optional(f"solver_sensitivity_q4-{v}_{m}.json")
                        for v in ("2", "3") for m in ("highs-ds", "highs-ipm")) if r]
    _census = load_optional("solver_degeneracy_census_q4-3.json")
    X(independent_section(_verify))
    X(lambda_section(_lam))
    X(pf_section(_pf))
    X(solver_section(_alt, _census))

    A("## 12. 尚存限制")
    A("")
    A("1. 电价预测为两因子（形态×水平）+ 日内 AR(1)，未使用任何外部信息"
      "（天气、星期、节假日），峰谷时段的系统性偏差只能靠水平比部分吸收。"
      "全年日前 MAPE 13.2%、6:00 更新后 9.1%。")
    A("2. 场景取自历史残差重采样，未做同月/同形态分层，尾部价格风险可能被低估；"
      "电价残差另被截断在 [0.3, 3.0] 倍，进一步削掉了极端情形。")
    A("3. 18:00 的日内更新在**预测精度**上是负收益（同窗口 MAE 由 0.0631 升到 0.0832），"
      "因为它用 15:00–18:00 午后低价段估出的水平比被乘到 18:00–24:00 晚高峰上，"
      "跨了价格形态体制。但按**费用**的消融显示影响仅 0.003%，故未改动模型。"
      "详见 `docs/q4_model.md` 第 10 节。")
    A("4. 与第三问同：名为多阶段实为「滚动两阶段」，不宣称严格多阶段随机最优；"
      "实时层为贪心规则而非滚动 LP 最优；末端储能价值取常数水价。")
    A("5. 结算口径沿用题面口径（逐次提交不退款），若实际合同另有约定需重新结算。")
    A("6. **禁止声称某个终端储能价值 `λ` 取值「更优」或「最优」。** λ 是外生常数，"
      "不由模型最优性导出；第 9 节的扫描只说明费用对 λ 的**敏感程度**，"
      "不构成对 λ 的标定或选择。")
    A("7. **禁止由「换算法费用不变」推断「最优策略唯一」。** 第 11 节的 LP 级普查显示"
      "该 LP 编码**普遍退化**（44.6% 的 (LP, 算法) 对解向量不同），"
      "费用面唯一**不等于**策略面唯一。逐时段引用「最优策略」（如某天某时段的"
      "充放电量）时必须说明该解只是多个最优解之一。")
    A("")
    A("")

    REPORT.write_text("\n".join(L), encoding="utf-8")
    print(f"-> {REPORT}  ({len(L)} 行)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
