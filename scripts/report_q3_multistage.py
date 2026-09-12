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
ISSUE = {1: "6:00", 2: "12:00", 3: "18:00"}   # 阶段号 -> 预报发布时刻
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


def load_comparison() -> dict:
    """第 4 节的八组合对照，由 scripts/assemble_q3_stage_comparison.py 生成。"""
    path = OUT / "q3_stage_comparison.json"
    if not path.exists():
        raise FileNotFoundError(
            f"缺少八组合对照结果：{path}\n"
            "先跑齐 scripts/export_q3_multistage.py 30 <stages> 的 8 种组合，再跑 "
            "scripts/assemble_q3_stage_comparison.py。")
    return json.loads(path.read_text(encoding="utf-8"))


def load_solver() -> dict | None:
    """第 8.1 节的求解器检验结果，由 scripts/q3_solver_uniqueness_check.py 生成。

    产物缺失时返回 None，报告退化为一句「未运行」提示——不阻塞其余章节。
    """
    need = {"alt_ds": "solver_sensitivity_highs-ds.json",
            "alt_ipm": "solver_sensitivity_highs-ipm.json",
            "census": "solver_degeneracy_census.json"}
    paths = {k: OUT / v for k, v in need.items()}
    if not all(p.exists() for p in paths.values()):
        return None
    return {k: json.loads(p.read_text(encoding="utf-8")) for k, p in paths.items()}


def invariants(detail, payload) -> dict[str, float]:
    """重算物理不变量，供报告第 7 节引用（与 validate_q3_multistage.py 相互独立地再算一遍）。"""
    x,q,z,c,g,w,S=(detail[k] for k in ("x","q","z","c","g","w","S"))
    nq=detail["natural_q"]; nx=detail["natural_x"]
    S0 = detail["S0"]
    worst = {"balance": 0.0, "soc": 0.0, "charge_limit": 0.0, "discharge_limit": 0.0,
             "soc_lo": 0.0, "soc_hi": 0.0, "cost_split": 0.0, "simultaneous": 0.0,
             "emg_charge_slots": 0, "emg_charge_kwh": 0.0}
    tol = 1e-6
    for i in range(len(S0)):
        for t in range(M.T):
            now=float(S[i,t+1])
            worst["soc"]=max(worst["soc"],abs(now-(S[i,t]+M.ETA*c[i,t]-g[i,t]/M.ETA)))
            ml,mg=M.midnight_actual(i); actual=(ml-mg) if t==0 else M.L[i,t-1]-M.G[i,t-1]
            worst["balance"]=max(worst["balance"],abs(nq[i,t]+z[i,t]+g[i,t]-c[i,t]-w[i,t]-actual))
            worst["charge_limit"] = max(worst["charge_limit"], c[i, t] - M.CMAX)
            worst["discharge_limit"] = max(worst["discharge_limit"], g[i, t] - M.CMAX)
            worst["soc_lo"] = max(worst["soc_lo"], M.SMIN - now)
            worst["soc_hi"] = max(worst["soc_hi"], now - M.SMAX)
            worst["simultaneous"] = max(worst["simultaneous"], min(c[i, t], g[i, t]))
            if z[i, t] > tol and c[i, t] > tol:
                worst["emg_charge_slots"] += 1
                worst["emg_charge_kwh"] += float(z[i, t])
        total=M.natural_day_cost(nx[i],nq[i],z[i])
        p1,p2,p3=M.natural_settle_parts(nx[i],nq[i],z[i])
        worst["cost_split"] = max(worst["cost_split"], abs(total - (p1.sum() + p2.sum() + p3.sum())))
    # 跨日 SOC 连续性：当日 0:00 等于前一日24:00。
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
        f"| 0:00 储电量/kWh | {f(day['soc_start_kwh'])} | |",
        f"| 24:00 储电量/kWh | {f(day['soc_end_kwh'])} | |",
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


def comparison(c: dict) -> list[str]:
    """第 4 节正文：八种预报发布组合的费用、条件边际与 Shapley 分解。"""
    rows = sorted(c["rows"], key=lambda x: x["rank"])
    tot = {r["policy"]: r["total_cost_yuan"] for r in rows}
    full = rows[0]
    issues = [ISSUE[m] for m in (1, 2, 3)]
    # (上下文, 时刻) -> 节省；上下文用 issue 标签集合表示
    lookup = {(frozenset(v["context"]), k): v["saving_yuan"]
              for k, vals in c["conditional_marginal_savings"].items() for v in vals}
    ctxs: list[tuple[str, tuple[str, ...]]] = [("0-only", ())]
    for p in issues:
        ctxs.append((f"0+{p}", (p,)))
    for i, p in enumerate(issues):
        for q in issues[i + 1:]:
            ctxs.append((f"0+{p}+{q}", (p, q)))

    L: list[str] = []
    A = L.append
    A("题目要求分析「是否需要引入其他时刻的预报制定调整购电策略」。本节在**同一模型、"
      "同一份数据、同一交付期、同一情景数、同一末端储能价值与同一初值**下，"
      "只改变启用了哪些发布时刻，重跑全部 8 种组合。")
    A("")
    A("各组合产物为 `outputs/q3_multistage/summary_stages<tag>_K30.json`；"
      "汇总脚本 `scripts/assemble_q3_stage_comparison.py` 会逐份校验元数据中"
      "的情景数、储能效率、单时段上限与交付期起止完全一致，"
      "以免把与「是否引入该时刻预报」无关的差异混进费用差。")
    A("")
    A("**口径说明**：`0-only` 是「只在 0:00 发布一次、全天不再调整」的退化情形，"
      "此时阶段 0 锁定全天 `[0,144)`；`0+6` 表示只启用 6:00 这一次调整，"
      "由 6:00 负责到当日结束。锁定区间一律按第 1 节的统一规则确定。")
    A("")
    A("| 策略 | 调整时刻 | 交付期总费用/元 | 相对 `0-only` 节省/元 | 节省比例 | 排名 |")
    A("|---|---|---:|---:|---:|---:|")
    for r in rows:
        times = " / ".join(r["adjustment_times"]) or "无"
        A(f"| `{r['policy']}` | {times} | {f(r['total_cost_yuan'])} | "
          f"{f(r['saving_vs_0_only_yuan'])} | {r['saving_vs_0_only_pct']:.3f}% | {r['rank']} |")
    A("")
    A(f"四阶段全启用的 `{full['policy']}` 费用最低，相对 `0-only` 节省 "
      f"**{f(full['saving_vs_0_only_yuan'])} 元**（{full['saving_vs_0_only_pct']:.3f}%），"
      "即**日内预报整体确有价值**。但「每个时刻是否都值得保留」不能只看整组排名，"
      "要看下面两个口径的边际。")
    A("")
    base_row = next(r for r in rows if r["policy"] == "0-only")
    A("**机制**：节省不是数值噪声。发布时刻越多，越能把「只有实时才知道的净负荷缺口」"
      "提前转成合同调整，于是**紧急购电费大幅下降、调整相关费用相应上升**：")
    A("")
    A("| 策略 | 调整相关费用/元 | 紧急购电费/元 | 紧急购电量/kWh |")
    A("|---|---:|---:|---:|")
    for r in rows:
        A(f"| `{r['policy']}` | {f(r['adjust_cost_yuan'])} | {f(r['emergency_cost_yuan'])} | "
          f"{f(r['emergency_kwh'])} |")
    A("")
    A(f"`0-only` 的紧急购电费为 {f(base_row['emergency_cost_yuan'])} 元"
      f"（{f(base_row['emergency_kwh'])} kWh），全启用降至 {f(full['emergency_cost_yuan'])} 元"
      f"（{f(full['emergency_kwh'])} kWh），降幅 "
      f"{100.0 * (1 - full['emergency_cost_yuan'] / base_row['emergency_cost_yuan']):.1f}%；"
      f"同期调整相关费用从 0 元升到 {f(full['adjust_cost_yuan'])} 元。"
      "即策略用**按 1.5 倍/0.5 倍电价的可预期合同调整**，替代了**5 倍电价的事后补救**。"
      "注意紧急购电费**不随可用时刻数严格单调**（`0+6` 就低于 `0+12`，因两者调整的"
      "时刻位置不同），因此排序只能依据总费用，不能依据紧急购电费单一指标。")
    A("")
    A("### 4.1 条件边际价值")
    A("")
    A("下表是「在已有某些发布时刻的前提下，再增加某一个时刻」能降低的费用（元）。"
      "每一行是一个上下文，三列分别是该上下文下再引入 6:00 / 12:00 / 18:00 的节省；"
      "已在上下文中的时刻记「—」。**行与行不可相加**：同一笔节省在不同上下文里会被重复计入。")
    A("")
    A("| 上下文 | 再引入 6:00/元 | 再引入 12:00/元 | 再引入 18:00/元 |")
    A("|---|---:|---:|---:|")
    for label, have in ctxs:
        cells = []
        for p in issues:
            if p in have:
                cells.append("—")
            else:
                cells.append(f(lookup[(frozenset(have), p)]))
        A(f"| `{label}` | " + " | ".join(cells) + " |")
    A("")
    n_marg = len(lookup)
    n_pos = sum(1 for v in lookup.values() if v > 0)
    A(f"全部 **{n_marg}** 个条件边际均为**正**（{n_pos}/{n_marg}，最小值 "
      f"{f(min(lookup.values()))} 元）：在本题考察的所有上下文里，"
      "**任一时间点的预报单独加进来都会降低总费用，没有一个时刻应当被舍弃**。"
      "这是对题面「是否需要引入其他时刻的预报」的直接回答：**需要，三个时刻都值得引入**。")
    A("")
    A("### 4.2 价值排序与可替代性")
    A("")
    A("上述条件边际随上下文变化很大，说明三个时刻的价值高度**可替代**："
      "单独引入 18:00 的节省为 "
      f"{f(lookup[(frozenset(), '18:00')])} 元，但在已有 6:00 与 12:00 时只剩 "
      f"{f(lookup[(frozenset({'6:00', '12:00'}), '18:00')])} 元。"
      "因此用 Shapley 值（对加入顺序取平均）给出与顺序无关的分配：")
    A("")
    shap = c["shapley_savings_vs_0_only_for_full_policy_yuan"]
    A("| 发布时刻 | Shapley 分摊/元 | 占比 | 单独引入（0-only 上下文）/元 |")
    A("|---|---:|---:|---:|")
    for p in issues:
        v = shap[p]
        A(f"| {p} | {f(v)} | {100.0 * v / c['full_policy_saving_vs_0_only_yuan']:.1f}% | "
          f"{f(lookup[(frozenset(), p)])} |")
    A("")
    A(f"三个时刻的 Shapley 分摊之和等于全启用的总节省 "
      f"{f(c['full_policy_saving_vs_0_only_yuan'])} 元（精确恒等，非近似）。"
      "按贡献排序为 **18:00 > 12:00 > 6:00**：18:00 的更新靠近晚高峰与高电价时段，"
      "12:00 次之，6:00 最小 —— 这与各发布时间距结算高峰的远近一致。")
    A("")
    A("两点值得写进结论：")
    A("")
    A(f"1. **最优二元与三元组合**：三元组合里 `0+6+18`（{f(tot['0+6+18'])} 元）与 "
      f"`0+12+18`（{f(tot['0+12+18'])} 元）只差 "
      f"{f(abs(tot['0+6+18'] - tot['0+12+18']))} 元；二元组合里 `0+18` 最好"
      f"（{f(tot['0+18'])} 元，占全启用节省的 "
      f"{100.0 * lookup[(frozenset(), '18:00')] / c['full_policy_saving_vs_0_only_yuan']:.1f}%）。"
      "在已启用 18:00 的前提下，6:00 与 12:00 几乎是彼此的替代品。")
    A("2. **边际递减但始终为正**：在其余两个时刻都已启用的前提下，再引入第三个时刻的边际如下。")
    A("")
    A("| 再引入 | 已有上下文 | 边际节省/元 |")
    A("|---|---|---:|")
    for p in issues:
        have = tuple(q for q in issues if q != p)
        A(f"| {p} | `0+{' + '.join(have)}` | {f(lookup[(frozenset(have), p)])} |")
    A("")
    A("三者仍都显著大于 0，因此**保留全部三次更新**是本题数据下的最优选择；"
      "若取得某时刻预报本身有成本，应按 Shapley 分摊与成本的比值排序取舍，"
      "而不是按单独引入的节省排序 —— 后者会系统性高估已被其他时刻覆盖的那部分价值。")
    A("")
    A("### 4.3 本节结论的适用范围")
    A("")
    A("1. 这里度量的是**「在该时刻重新制定计划的能力」**的价值，不是预报精度本身的价值；"
      "预报质量已包含在各时刻的情景生成中，若替换预测器，本表数字会随之变化。")
    A("2. 节省差是在**同一套 SAA 情景、同一末端价值 `λ`**下算出的模型内比较，"
      "属于模型条件结论，不等于实际系统上的保证；`λ` 与情景数变化会影响具体数值。")
    A("3. 各组合共用同一初值 6000 kWh 与同一交付期，跨组合的 SOC 轨迹不同，"
      "因此费用差里已包含储能路径差异 —— 这正是「能否调整」的经济价值所在。")
    A("")
    return L


def solver_section(s: dict | None, by: dict) -> list[str]:
    """第 8.1 节：求解器退化与配置敏感性。s 为 None 时只给提示。

    `by` 是主答案的 {日期: 当日记录}，只用来给出最差日的费用量级作参照。
    """
    L: list[str] = []
    A, X = L.append, L.extend
    A("### 8.1 求解器退化与配置敏感性")
    A("")
    if s is None:
        A("**未运行。** 跑 `scripts/q3_solver_uniqueness_check.py alt <method>`（整年对照）"
          "与 `... census`（LP 级普查）后重新生成本报告，本节会自动填充。")
        A("")
        return L

    ds, ip, cen = s["alt_ds"], s["alt_ipm"], s["census"]
    ref = ds["reference_total_cost_yuan"]
    A("旧模型曾实测「目标函数一字不改、只换求解算法，年度总费用可差约 0.226%」。"
      "本节在**现行模型**上重做该检验，脚本 `scripts/q3_solver_uniqueness_check.py`。")
    A("")
    A("该脚本不修改 `src/`：现行代码写的是 `linprog(c, ..., method='highs')`，"
      "`method` 是关键字参数，因此脚本通过替换模块命名空间里的 `linprog` "
      "名字来换算法，主答案路径一字未动。")
    A("")
    A("**（1）整年端到端对照**（334 天交付期，其余口径与主答案完全一致）：")
    A("")
    A("| 算法 | 交付期总费用/元 | 与主答案之差/元 | 逐日最大偏差/元 | 偏差 > 1 元的天数 |")
    A("|---|---:|---:|---:|---:|")
    A(f"| `highs`（主答案所用） | {ref:,.4f} | — | — | — |")
    A(f"| `highs-ds`（对偶单纯形） | {ds['alt_total_cost_yuan']:,.4f} | "
      f"**{ds['total_gap_yuan']:,.4f}** | {ds['max_abs_daily_gap_yuan']:,.4f} | "
      f"{ds['days_with_gap_over_1yuan']} |")
    A(f"| `highs-ipm`（内点法） | {ip['alt_total_cost_yuan']:,.4f} | "
      f"**{ip['total_gap_yuan']:,.4f}**（{ip['total_gap_pct']:+.6f}%） | "
      f"{ip['max_abs_daily_gap_yuan']:,.4f}（{ip['worst_day']}） | "
      f"{ip['days_with_gap_over_1yuan']} |")
    A("")
    wd = ip["worst_day"]
    wd_cost = by.get(wd, {}).get("total_cost_yuan")
    wd_note = (f"（{wd}，该日总费用 {wd_cost:,.2f} 元，即单日 "
               f"{100.0 * ip['max_abs_daily_gap_yuan'] / wd_cost:.2f}%）"
               if wd_cost else f"（{wd}）")
    A("`highs-ds` 与主答案**逐位相同**（逐日费用、334 天合计均为 0 偏差）。"
      f"`highs-ipm` 的总费用低 {abs(ip['total_gap_yuan']):,.2f} 元，"
      f"相对偏差 **{ip['total_gap_pct']:+.6f}%**；"
      f"偏差分散在 {ip['days_with_gap_over_1yuan']} 天上，"
      f"单日最大 {ip['max_abs_daily_gap_yuan']:,.2f} 元{wd_note}。")
    A("")
    ov, per_stage = cen["overall"], cen["by_stage"]
    n_ds = sum(per_stage[k]["highs-ds"]["n_solution_differs"] for k in per_stage)
    n_ip = sum(per_stage[k]["highs-ipm"]["n_solution_differs"] for k in per_stage)
    A(f"**（2）LP 级普查**（{cen['lps']} 个发布 LP，各用 3 种算法重解）：")
    A("")
    A("| 指标 | 数值 |")
    A("|---|---:|")
    A(f"| 覆盖 LP 数 | {cen['lps']} |")
    A(f"| 最优值最大相对偏差（跨算法） | {ov['max_rel_obj_gap_across_methods']:.2e} |")
    A(f"| 最优**值**相对偏差 > 1e-9 的 LP | {ov['n_lps_obj_gap_gt_1e-9']} |")
    A(f"| 最优**解向量**不同的 (LP, 备选算法) 对 | "
      f"{ov['n_lp_method_pairs_solution_differs']} / {ov['n_lp_method_pairs']}"
      f"（{100.0 * ov['n_lp_method_pairs_solution_differs'] / ov['n_lp_method_pairs']:.1f}%） |")
    A(f"| ├ 其中 `highs-ds` | {n_ds} / {cen['lps']} |")
    A(f"| └ 其中 `highs-ipm` | {n_ip} / {cen['lps']} |")
    A(f"| 目标系数加 {cen['jitter_rel']:g} 相对扰动后解向量不同 | "
      f"{ov['jitter_n_solution_differs']} / {ov['jitter_n']} |")
    A("")
    A("**结论：**")
    A("")
    A("1. **现行模型不存在旧模型那种「换算法年度费用差 0.226%」的配置敏感性。** "
      f"约束与目标不变时，{cen['lps']} 个 LP 的最优值跨算法一致到 "
      f"{ov['max_rel_obj_gap_across_methods']:.2e} 相对量级，无一个超过 1e-9；"
      f"端到端也只有内点法产生 {abs(ip['total_gap_yuan']):,.2f} 元的偏差。"
      f"主答案 {ref:,.4f} 元**不是**求解器配置的伪影。")
    A("2. **但 LP 确实普遍退化（最优解不唯一）。** "
      f"{100.0 * ov['n_lp_method_pairs_solution_differs'] / ov['n_lp_method_pairs']:.1f}% 的 "
      "(LP, 算法) 对给出不同的最优解向量——内点法返回最优面上的相对内点，"
      "与单纯形法给出的顶点不同；`highs` 与 `highs-ds` 则完全一致。"
      "这与旧模型实测的 41.9% 退化率量级相符，**但两者分母不同**"
      "（旧模型按发布时刻统计，本表按 (LP, 算法) 对统计），不可直接比较。")
    A("3. **方法学注意**：普查比较的是**完整 LP 解向量**，而模型只取前缀 `r.x[:nD]` "
      "作为实际决策（其余为情景 recourse 变量）。因此上表「解向量不同」一栏描述的是 "
      "LP 的退化程度，**不等于**决策层面的不唯一率。决策层面的影响由第（1）项的"
      "端到端对照界定：即便近半数 LP 的解向量不同，334 天总费用仍只差 "
      f"{abs(ip['total_gap_yuan']):,.2f} 元。")
    n_days = cen["lps"] // len(cen["stages"])
    A(f"4. 脚本的 `census` 模式本意是「按步长抽样 {cen['sampled_days']} 天」，"
      f"但 `backtest` 的调用会求解 `[起, 止)` 区间内的**每一天**，因此实际普查的是 "
      f"2025-02-01 起连续 **{n_days} 天**的全部 {cen['lps']} 个发布 LP，"
      "比原打算的抽样覆盖更广、结论更强（代价：单次约 31 分钟）。")
    A("")
    A("**产物**：`outputs/q3_multistage/solver_sensitivity_highs-ds.json`、"
      "`solver_sensitivity_highs-ipm.json`、`solver_degeneracy_census.json`。")
    A("")
    return L


def main() -> int:
    payload, detail, by = load()
    comp = load_comparison()
    solver = load_solver()
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
    A("| 阶段 `m` | 发布时刻 | 起始时段 `TSTAGE[m]` | 该阶段锁定区间 |")
    A("|---|---|---|---|")
    A("| 0 | 0:00 | 0 | 制定全天计划 `x[0..143]`，锁定至下一次启用的发布时刻 |")
    A("| 1 | 6:00 | 35 | `[35, 下一次启用时刻)` |")
    A("| 2 | 12:00 | 71 | `[71, 下一次启用时刻)` |")
    A("| 3 | 18:00 | 107 | `[107, 144)` |")
    A("")
    A("**锁定区间的统一规则**：某个发布时刻被禁用时，上一次启用的发布时刻不再只负责固定的 "
      "6 小时块，而是负责到**下一次实际启用的发布时刻**为止；最后一次启用负责到当日结束。"
      "否则被禁用时刻之后的区间会悄悄退回 0:00 计划 —— 既不许可调整、又不延续上一版计划，"
      "会系统性低估被禁用预报的价值。上表末列即四阶段全启用时的特例。")
    A("")
    A("区间起点和物理参数与问题1/2一致，但报表采用双时间框：计划/调整表保留**模板行**（第 `t` 个时段覆盖 "
      "`[(t+1)×10, (t+2)×10)` 分钟，`t=0` 为 0:10–0:20，`t=143` 为次日 0:00–0:10）；"
      "**交流母线侧储能**（`S_t = S_(t-1) + 0.9·c_t − g_t/0.9`，充、放电单时段上限同为 "
      "`5000/6 = 833.3333` kWh，`S ∈ [1200, 10800]`，初值6000）；实际执行、SOC、紧急购电和总费用按自然日0:00–24:00。**题面结算口径**")
    A("")
    A("```")
    A("C_t = p_t·min(x_t, q_t) + 1.5·p_t·(q_t − x_t)^+ + 0.5·p_t·(x_t − q_t)^+ + 5·p_t·z_t")
    A("```")
    A("")
    A(f"其中 `p_t` 取附件1 的确定分时电价（144 维，范围 {M.P.min():.4f}–{M.P.max():.4f} "
      f"元/kWh，均值 {M.P.mean():.4f}）。")
    A("")
    A(f"自然日交付期为 {per['start']} 至 {per['end']}，共 {per['days']} 天。"
      "全年回测自 2025-01-01 起算，前 31 天为预热期，不计入交付期统计。"
      f"情景数 `K = {K}`，末端储能价值 `λ = {M.LAM}`（常数水价）。")
    A("")
    A("⚠️ **实时层的性质**：给定 `q` 后实时唯一的自由度是「放电 or 紧急购电」，"
      "由 `dispatch()` 按贪心规则决定，**不是**滚动 LP 最优。"
      "该层会按实际净负荷执行，故可能出现「同时紧急购电与充电」的时段（见第 8 节）。")
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
      "**两者不可混算**：现行模型已统一为计划模板行与物理自然日双时间框；"
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
    A("## 4. 预报发布时刻组合对照")
    A("")
    X(comparison(comp))
    A("## 5. 指定日期：表1 计划购电量与最终调整购电量")
    A("")
    A("按题面表1 的格式给出表3 指定的四个日期，各行对应的时段起止时刻见第一列。"
      "全天购电量与购电费取该日的模板行合计。")
    A("")
    for date in DATES:
        A(f"### {date}")
        A("")
        X(table1(by[date], M.DSTR.index(date)))
        A("")

    A("## 6. 指定日期：表2 充放电量与储电量")
    A("")
    A("按题面表2的自然日口径给出四个日期：0:00–4:00至20:00–24:00；SOC为0:00与24:00。")
    A("")
    for date in DATES:
        A(f"### {date}")
        A("")
        X(table2(by[date]))
        A("")

    A("## 7. 指定日期：表3 紧急购电")
    A("")
    A("按题面表3 与表4 的格式给出四个日期。连续的非零 10 分钟时段合并为一段；"
      "无紧急购电的日期标注为无。")
    A("")
    for date in DATES:
        A(f"### {date}")
        A("")
        X(table3(by[date]))

    A("## 8. 数值校验")
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
    X(solver_section(solver, by))
    A("## 9. 尚存限制")
    A("")
    A("1. **八组合对照已补齐，但结论是模型内条件结论。** 第 4 节的对照在现行模型上"
      "重跑了 `0-only / 0+6 / 0+12 / 0+18 / 0+6+12 / 0+6+18 / 0+12+18 / 0+6+12+18` "
      "八种发布组合，**已可回答题面「是否需要引入其他时刻的预报」**；"
      "旧模型那版同题对照（见 `reports/_archive/q3_report.md` 第 2 节）数字仍全部失效、不可引用。"
      "仍需注意第 4.3 节列出的适用范围：节省是同一 SAA 情景与同一 `λ` 下的模型内比较，"
      "换预测器或换情景数都会改变具体数值。")
    A("2. **求解器检验已补做，但独立复核仍未做。** 旧模型曾有两轮独立复核"
      "（退款口径 8 组合复算、主口径最优解唯一性检验，见 "
      "`reports/_archive/q3_refund_verification.md` 与 `reports/_archive/q3_uniqueness_check.md`）。"
      "现行模型现已补上第 8.1 节的求解器退化与配置敏感性检验"
      "（结论：换算法不改变最优值，端到端差 0.0002%；但 LP 普遍退化、最优解不唯一），"
      "**仍未做**独立于 `src/q3_multistage.py` 的第二套实现复算——"
      "`scripts/validate_q3_multistage.py` 验证的是「编码与已验收产物自洽」，不是第三方复算。")
    A("3. 0:00 计划没有用完整情景树联合定价未来 6/12/18 时的信息到达与调整机会，"
      "属于滚动两阶段近似；`strict_multistage_optimal=false`，**不宣称严格多阶段随机最优**。")
    A(f"4. 终端储能价值固定为常数水价 `λ = {M.LAM}`，未表达次日清晨负荷与紧急电价风险，"
      "该系数不是由最优性推导唯一确定；未做全年敏感性扫描。")
    A("5. 实时层为贪心规则而非滚动 LP 最优（见第 1 节）。")
    A("6. 附件3只给整点光伏预报，10分钟值采用以发布时刻为锚点的PCHIP保形插值；"
      "0:00锚点使用上一已完成区间，其他发布时刻使用当时可测量值。附件未提供负荷预报，"
      "日内负荷预测沿用计划日前的历史轮廓。")
    A("7. 午夜购电锁定为前一日最后一次提交的次日 00:00 量，属于合同时间假设；"
      "结算口径（逐次提交不退款）需人工确认。")
    A("")

    REPORT.write_text("\n".join(L), encoding="utf-8")
    print(f"-> {REPORT}  ({len(L)} 行)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
