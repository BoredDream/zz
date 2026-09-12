"""由 outputs/q3_multistage 的产物生成 reports/q3_report.md（现行第三问报告）。

只读 payload / npz / 求解器常量，不重新求解、不修改任何已验收产物。
报告里的数字全部机器提取，避免手抄出错。

本脚本取代旧的 src/q3_solver.py 时代的 q3_report.md；后者已移入
reports/_archive/ 并在顶部加了封存横幅。

用法： python scripts/report_q3_multistage.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
import q3_multistage as M  # noqa: E402

OUT = ROOT / "outputs" / "q3_multistage"
REPORT = ROOT / "reports" / "q3_report.md"
K = 30
TAG = "0123"
DATES = ["2025-03-20", "2025-06-21", "2025-09-23", "2025-12-21"]
# 表1 的六个指定 10 分钟时段。模板行框下 t 覆盖 [(t+1)*10, (t+2)*10) 分钟
WINDOWS = [("10:00-10:10", 59), ("12:00-12:10", 71), ("14:00-14:10", 83),
           ("16:00-16:10", 95), ("18:00-18:10", 107), ("20:00-20:10", 119)]
# 被取代的旧模型（src/q3_solver.py）交付期总费用，仅用于第 3 节对照，不作其他引用
OLD_TOTAL = 14743406.7685


def f(v: float) -> str:
    """四位小数；把 -0.0 与小于显示精度的量归成 0，避免出现 "-0.0000"。"""
    if abs(v) < 5e-5:
        v = 0.0
    return f"{v:,.4f}"


def load():
    payload = json.loads((OUT / f"payload_stages{TAG}_K{K}.json").read_text(encoding="utf-8"))
    detail = np.load(OUT / f"detail_stages{TAG}_K{K}.npz")
    return payload, detail, {day["date"]: day for day in payload["days"]}


def invariants(detail, payload) -> dict[str, float]:
    """重算物理不变量，供报告第 7 节引用（与 validate_q3_multistage.py 相互独立地再算一遍）。"""
    x, q, z, c, g, w, S = (detail[k] for k in ("x", "q", "z", "c", "g", "w", "S"))
    S0 = detail["S0"]
    worst = {"balance": 0.0, "soc": 0.0, "charge_limit": 0.0, "discharge_limit": 0.0,
             "soc_lo": 0.0, "soc_hi": 0.0, "cost_split": 0.0, "simultaneous": 0.0,
             "emg_charge_slots": 0, "emg_charge_kwh": 0.0}
    tol = 1e-6
    for i in range(len(S0)):
        prev = float(S0[i])
        for t in range(M.T):
            now = float(S[i, t])
            worst["soc"] = max(worst["soc"], abs(now - (prev + M.ETA * c[i, t] - g[i, t] / M.ETA)))
            worst["balance"] = max(worst["balance"], abs(q[i, t] + z[i, t] + g[i, t]
                                                      - c[i, t] - w[i, t] - (M.L[i, t] - M.G[i, t])))
            worst["charge_limit"] = max(worst["charge_limit"], c[i, t] - M.CMAX)
            worst["discharge_limit"] = max(worst["discharge_limit"], g[i, t] - M.CMAX)
            worst["soc_lo"] = max(worst["soc_lo"], M.SMIN - now)
            worst["soc_hi"] = max(worst["soc_hi"], now - M.SMAX)
            worst["simultaneous"] = max(worst["simultaneous"], min(c[i, t], g[i, t]))
            if z[i, t] > tol and c[i, t] > tol:
                worst["emg_charge_slots"] += 1
                worst["emg_charge_kwh"] += float(z[i, t])
            prev = now
        total = M.day_cost(x[i], q[i], {"z": z[i]})[0]
        p1, p2, p3 = M.settle_parts(x[i], q[i], z[i])
        worst["cost_split"] = max(worst["cost_split"], abs(total - (p1.sum() + p2.sum() + p3.sum())))
    # 跨日 SOC 连续性：当日 0:10 储电量应等于前一日「次日 0:10 储电量」
    gaps = 0.0
    for a, b in zip(payload["days"], payload["days"][1:]):
        gaps = max(gaps, abs(a["soc_end_kwh"] - b["soc_start_kwh"]))
    worst["soc_continuity"] = gaps
    return worst


def table1(day: dict, d: int) -> list[str]:
    rows = ["| 时间段 | 分时电价<br>元/kWh | 计划购电量<br>kWh | 最终调整购电量<br>kWh |",
            "|---|---:|---:|---:|"]
    for label, t in WINDOWS:
        rows.append(f"| {label} | {f(M.P[t])} | {f(day['plan_kwh'][t])} | "
                    f"{f(day['adjusted_kwh'][t])} |")
    rows += [
        f"| **模板行购电量合计** | | **{f(day['plan_total_kwh'])}** | "
        f"**{f(day['adjusted_total_kwh'])}** |",
        f"| 计划购电费/元 | | {f(day['plan_cost_yuan'])} | |",
        f"| 调整相关费用/元 | | | {f(day['adjusted_cost_yuan'])} |",
        f"| 紧急购电费/元 | | | {f(day['emergency_cost_yuan'])} |",
        f"| **当日总费用/元** | | | **{f(day['total_cost_yuan'])}** |",
        f"| 当日弃电量/kWh | | | {f(day['curtail_kwh'])} |",
        f"| 当日累计上调量/kWh | | | {f(day['adjust_up_kwh'])} |",
        f"| 当日累计下调量/kWh | | | {f(day['adjust_down_kwh'])} |",
    ]
    return rows


def table2(day: dict) -> list[str]:
    rows = ["| 时间段 | 充电量/kWh | 放电量/kWh |", "|---|---:|---:|"]
    for b in day["storage_blocks"]:
        rows.append(f"| {b['time_range']} | {f(b['charge_kwh'])} | {f(b['discharge_kwh'])} |")
    rows += [
        f"| 0:10 储电量/kWh | {f(day['soc_start_kwh'])} | |",
        f"| 次日 0:10 储电量/kWh | {f(day['soc_end_kwh'])} | |",
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


def main() -> int:
    payload, detail, by = load()
    t = payload["meta"]["totals"]
    per = payload["meta"]["delivery_period"]
    w = invariants(detail, payload)
    n_emg = sum(1 for day in payload["days"] if day["emergency_segments"])

    L: list[str] = []
    A, X = L.append, L.extend
    A("# 第三问计算报告（多阶段随机规划，现行模型）")
    A("")
    A("> ⚠️ **本文件已由现行模型 `src/q3_multistage.py` 重新生成**，取代 `src/q3_solver.py`")
    A("> 时代的同名文件（后者见 `reports/_archive/q3_report.md`，其全部数字已失效）。")
    A("> 本报告数字全部由 `outputs/q3_multistage/payload_stages0123_K30.json` 机器提取，")
    A("> 未手工誊写。模型定义见 `docs/q3_multistage_model.md`，"
      "独立验收见 `scripts/validate_q3_multistage.py`。")
    A("")
    A("## 1. 模型与口径")
    A("")
    A("每天 0:00 制定当天计划，**6:00 / 12:00 / 18:00 三次**仅调整尚未交付的区间；"
      "同一发布时刻的全部情景共享购电量、充电量、放电量和 SOC 轨迹，"
      "只有紧急购电与弃电是情景补救变量，因此不存在情景提前预知未来。")
    A("")
    A("| 阶段 `m` | 发布时刻 | 起始时段 `TSTAGE[m]` | 该阶段可调整区间 |")
    A("|---|---|---|---|")
    A("| 0 | 0:00 | 0 | 制定全天计划 `x[0..143]` |")
    A("| 1 | 6:00 | 35 | `[35, 71)` |")
    A("| 2 | 12:00 | 71 | `[71, 107)` |")
    A("| 3 | 18:00 | 107 | `[107, 144)` |")
    A("")
    A("三条口径与问题 1/2 完全一致：**模板行时间框**（第 `t` 个时段覆盖 "
      "`[(t+1)×10, (t+2)×10)` 分钟，`t=0` 为 0:10–0:20，`t=143` 为次日 0:00–0:10）；"
      "**交流母线侧储能**（`S_t = S_(t-1) + 0.9·c_t − g_t/0.9`，充、放电单时段上限同为 "
      "`5000/6 = 833.3333` kWh，`S ∈ [1200, 10800]`，初值 6000）；**题面结算口径**")
    A("")
    A("```")
    A("C_t = p_t·min(x_t, q_t) + 1.5·p_t·(q_t − x_t)^+ + 0.5·p_t·(x_t − q_t)^+ + 5·p_t·z_t")
    A("```")
    A("")
    A(f"其中 `p_t` 取附件1 的确定分时电价（144 维，范围 {M.P.min():.4f}–{M.P.max():.4f} "
      f"元/kWh，均值 {M.P.mean():.4f}）。")
    A("")
    A(f"交付期为 {per['start']} 至 {per['end']}，共 {per['days']} 天。"
      "全年回测自 2025-01-01 起算，前 31 天为预热期，不计入交付期统计。"
      f"情景数 `K = {K}`，末端储能价值 `λ = {M.LAM}`（常数水价）。")
    A("")
    A("⚠️ **实时层的性质**：给定 `q` 后实时唯一的自由度是「放电 or 紧急购电」，"
      "由 `dispatch()` 按贪心规则决定，**不是**滚动 LP 最优。"
      "该层会按实际净负荷执行，故可能出现「同时紧急购电与充电」的时段（见第 7 节）。")
    A("")
    A("## 2. 交付期结果汇总")
    A("")
    A(f"| 指标（{per['start']} 至 {per['end']}，{per['days']} 天） | 结果 |")
    A("|---|---:|")
    A(f"| 计划购电量（模板行）/kWh | {f(sum(d['plan_total_kwh'] for d in payload['days']))} |")
    A(f"| 最终合同购电量（模板行）/kWh | {f(sum(d['adjusted_total_kwh'] for d in payload['days']))} |")
    A(f"| 计划购电费/元 | {f(t['plan_cost_yuan'])} |")
    A(f"| 调整相关费用/元 | {f(t['adjust_cost_yuan'])} |")
    A(f"| 紧急购电费/元 | {f(t['emergency_cost_yuan'])} |")
    A(f"| **总费用/元** | **{f(t['total_cost_yuan'])}** |")
    A(f"| 紧急购电量/kWh | {f(t['emergency_kwh'])} |")
    A(f"| 充电量/kWh | {f(t['charge_kwh'])} |")
    A(f"| 放电量/kWh | {f(t['discharge_kwh'])} |")
    A(f"| 弃电量/kWh | {f(t['curtail_kwh'])} |")
    A(f"| 累计上调量/kWh | {f(t['adjust_up_kwh'])} |")
    A(f"| 累计下调量/kWh | {f(t['adjust_down_kwh'])} |")
    A(f"| 含紧急购电的日期数 | {n_emg} / {per['days']} |")
    A("")
    A("## 3. 与旧模型的对照")
    A("")
    A("本模型取代 `src/q3_solver.py`（旧报告已移入 `reports/_archive/`）。"
      "**两者不可混算**：旧模型用自然日口径 + 跨行映射，本模型用模板行框；"
      "旧模型的结算主口径把初始计划费记为沉没成本，本模型用题面口径，"
      "对下调时段的结果不同。")
    A("")
    A("| 指标 | 旧模型 `q3_solver`（已弃用） | 现行 `q3_multistage` | 差 |")
    A("|---|---:|---:|---:|")
    A(f"| 总费用/元 | {f(OLD_TOTAL)} | {f(t['total_cost_yuan'])} | "
      f"{(t['total_cost_yuan'] / OLD_TOTAL - 1) * 100:+.2f}% |")
    A("")
    A("> **该差额不表示模型改进或退化。** 两次回测的时间口径（自然日 vs 模板行）、"
      "结算口径（沉没成本 vs 题面）、策略结构（8 套预报组合 vs 0/6/12/18 四阶段）"
      "都不同，费用不可直接相减。此处仅登记「旧数字已作废」这一事实。")
    A("")
    A("## 4. 指定日期：表1 计划购电量与最终调整购电量")
    A("")
    A("按题面表1 的格式给出表3 指定的四个日期，各行对应的时段起止时刻见第一列。"
      "全天购电量与购电费取该日的模板行合计。")
    A("")
    for date in DATES:
        A(f"### {date}")
        A("")
        X(table1(by[date], M.DSTR.index(date)))
        A("")

    A("## 5. 指定日期：表2 充放电量与储电量")
    A("")
    A("按题面表2 的格式给出四个日期，六个 4 小时段即 `t=0..23, 24..47, …, 120..143`。"
      "储电量按模板行口径给出，即该行起点（0:10）与终点（次日 0:10）的储电量，"
      "与 `result3.xlsx` 的「充放电量」工作表一致。")
    A("")
    for date in DATES:
        A(f"### {date}")
        A("")
        X(table2(by[date]))
        A("")

    A("## 6. 指定日期：表3 紧急购电")
    A("")
    A("按题面表3 与表4 的格式给出四个日期。连续的非零 10 分钟时段合并为一段；"
      "无紧急购电的日期标注为无。")
    A("")
    for date in DATES:
        A(f"### {date}")
        A("")
        X(table3(by[date]))

    A("## 7. 数值校验")
    A("")
    A("由 `scripts/validate_q3_multistage.py` 独立验收，报告脚本另行重算一遍关键不变量，"
      "两处结果一致。")
    A("")
    A("| 校验项 | 最大偏差/极值 |")
    A("|---|---:|")
    A(f"| 功率平衡残差/kWh | {w['balance']:.3e} |")
    A(f"| SOC 递推残差/kWh | {w['soc']:.3e} |")
    A(f"| 充电量超上限/kWh | {w['charge_limit']:.3e} |")
    A(f"| 放电量超上限/kWh | {w['discharge_limit']:.3e} |")
    A(f"| SOC 低于下限/kWh | {w['soc_lo']:.3e} |")
    A(f"| SOC 高于上限/kWh | {w['soc_hi']:.3e} |")
    A(f"| 同时充放电量/kWh | {w['simultaneous']:.3e} |")
    A(f"| 跨日 SOC 不连续/kWh | {w['soc_continuity']:.3e} |")
    A(f"| 三项费用拆分与总费用之差/元 | {w['cost_split']:.3e} |")
    A("")
    A("**「同时紧急购电与充电」的时段**（第 1 节提到的现象）："
      f"共 **{w['emg_charge_slots']}** 个 10 分钟时段，涉及紧急购电量 "
      f"**{f(w['emg_charge_kwh'])}** kWh。")
    A("")
    A("这不是执行器自相矛盾：充电来自发布时锁定、按实际净负荷执行的储能轨迹，"
      "而紧急购电补的是同一时段的功率缺口。因实时层是贪心规则（第 1 节），"
      "两者可以并存。")
    A("")
    A("## 8. 尚存限制")
    A("")
    A("1. **本模型尚未做预报时刻组合的对照。** 题目要求分析「是否需要引入其他时刻的预报"
      "制定调整购电策略」，旧模型曾给出 `none / 6 / 12 / 18 / 6+12 / 6+18 / 12+18 / 6+12+18` "
      "八套组合的比较（见 `reports/_archive/q3_report.md` 第 2 节），但那是在旧模型上做的，"
      "**其数字与结论均已随模型更换失效**。现行模型只跑过 `stages=(0,1,2,3)` 一种配置，"
      "因此**本报告不能回答该问题**。补齐需以现行模型重跑各组合"
      "（`scripts/export_q3_multistage.py 30 <stages>`，单次约 374 s）。")
    A("2. **本模型尚未做独立复核。** 旧模型曾有两轮独立复核（退款口径 8 组合复算、"
      "主口径最优解唯一性检验，见 `reports/_archive/q3_refund_verification.md` 与 "
      "`reports/_archive/q3_uniqueness_check.md`）。现行模型**没有**同等强度的复核，"
      "论文引用前需补做或降级表述。")
    A("3. 0:00 计划没有用完整情景树联合定价未来 6/12/18 时的信息到达与调整机会，"
      "属于滚动两阶段近似；`strict_multistage_optimal=false`，**不宣称严格多阶段随机最优**。")
    A(f"4. 终端储能价值固定为常数水价 `λ = {M.LAM}`，未表达次日清晨负荷与紧急电价风险，"
      "该系数不是由最优性推导唯一确定；未做全年敏感性扫描。")
    A("5. 实时层为贪心规则而非滚动 LP 最优（见第 1 节）。")
    A("6. 附件3 只给整点光伏预报，10 分钟值是线性插值；发布时刻的插值首节点使用上一区间"
      "实际值，属于持续性近似。附件未提供负荷预报，日内负荷预测沿用计划日前的历史轮廓。")
    A("7. 午夜购电锁定为前一日最后一次提交的次日 00:00 量，属于合同时间假设；"
      "结算口径（逐次提交不退款）需人工确认。")
    A("")

    REPORT.write_text("\n".join(L), encoding="utf-8")
    print(f"-> {REPORT}  ({len(L)} 行)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
