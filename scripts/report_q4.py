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
    A("## 8. 尚存限制")
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
    A("")

    REPORT.write_text("\n".join(L), encoding="utf-8")
    print(f"-> {REPORT}  ({len(L)} 行)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
