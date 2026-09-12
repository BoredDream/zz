# -*- coding: utf-8 -*-
"""生成第二问论文图所需的全部绘图数据（纯数据整备，不画图）。

自包含版本：路径全部相对本文件解析，可直接在仓库内运行。
  · 读取仓库 problem/data/附件1.xlsx 与 outputs/q2/ 的已提交结果
  · 写出 _figdata/ 下的 CSV
  · 不重跑求解器、不修改仓库任何已有文件
"""
import csv, json, sys, collections
from pathlib import Path
import numpy as np
import openpyxl

HERE = Path(__file__).resolve().parent          # handoff/q2/scripts
Q2DIR = HERE.parent                             # handoff/q2
REPO = HERE.parents[2]                          # 仓库根（zz/）
OUT = Q2DIR / "_figdata"
OUTPUTS = REPO / "outputs" / "q2"
ATT = REPO / "problem" / "data"
DT = 1.0 / 6.0


def rows_of(name):
    with (OUTPUTS / name).open(encoding="utf-8-sig", newline="") as h:
        return list(csv.DictReader(h))


def main() -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:                            # noqa: BLE001
        pass
    OUT.mkdir(parents=True, exist_ok=True)

    iv = rows_of("interval_detail.csv")
    dm = rows_of("daily_metrics.csv")
    payload = json.loads((OUTPUTS / "solver_payload.json").read_text(encoding="utf-8"))
    summary = json.loads((OUTPUTS / "summary.json").read_text(encoding="utf-8"))

    # ---------- 1) 附件1 日内轮廓 ----------
    ws = openpyxl.load_workbook(ATT / "附件1.xlsx", read_only=True, data_only=True).active
    a1 = list(ws.iter_rows(values_only=True))[1:]

    def label(v) -> str:
        """把附件1 的时间标签统一规范为 'HH:MM'（末行为 '24:00'）。

        ⚠ 重要：附件1.xlsx 的时间列是【混合类型】——
          前 132 行为 datetime.time，后 12 行（22:10 ~ 0:00+1）为纯字符串。
        早先的实现写成 `"24:00" if not hasattr(v, "hour") else ...`，
        使所有字符串行都被误判为 24:00，导致最后 12 行标签全部相同；
        绘图时 slot_of() 对它返回同一个 x，折线在 x=24 处往返，形成一根
        假的垂直下降线，并让末端曲线形态完全失真。
        这里按「显式类型判断 + 字符串解析」双路径规范化，不再依赖属性探测。
        """
        if hasattr(v, "hour"):                      # datetime.time
            return f"{v.hour:02d}:{v.minute:02d}"
        s = str(v).strip()
        if s in ("0:00+1", "00:00+1"):              # 题面：表示次日 0:00 即当天 24:00
            return "24:00"
        parts = s.split(":")
        if len(parts) >= 2:
            try:
                return f"{int(parts[0]):02d}:{int(parts[1]):02d}"
            except ValueError:
                pass
        raise ValueError(f"无法解析附件1 的时间标签：{v!r}")

    with (OUT / "annex1_net_load.csv").open("w", newline="", encoding="utf-8-sig") as h:
        w = csv.writer(h)
        w.writerow(["time_label", "price_yuan_per_kwh", "load_kw", "pv_kw",
                    "net_kw", "net_kwh"])
        for t in a1:
            L, V = float(t[2]), float(t[3])
            w.writerow([label(t[0]), float(t[1]), L, V,
                        round(L - V, 6), round((L - V) * DT, 6)])
    labels = [label(t[0]) for t in a1]
    assert len(set(labels)) == 144, f"时间标签仍有重复：{len(set(labels))} 个唯一值 / 144 行"
    assert labels[0] == "00:10" and labels[-1] == "24:00", f"首末标签异常：{labels[0]} / {labels[-1]}"
    print(f"annex1_net_load.csv            : {len(a1)} 行（144 个唯一时间标签，已校验）")

    # ---------- 2) 月度汇总 ----------
    mm = collections.defaultdict(lambda: [0.0] * 4)
    for r in dm:
        k = r["date"][:7]
        mm[k][0] += float(r["natural_plan_kwh"]);  mm[k][1] += float(r["natural_plan_cost_yuan"])
        mm[k][2] += float(r["emergency_kwh"]);     mm[k][3] += float(r["emergency_cost_yuan"])
    with (OUT / "monthly_summary.csv").open("w", newline="", encoding="utf-8-sig") as h:
        w = csv.writer(h)
        w.writerow(["month", "plan_kwh", "plan_cost_yuan", "emergency_kwh",
                    "emergency_cost_yuan", "total_cost_yuan", "emergency_share_pct"])
        for k in sorted(mm):
            p, pc, e, ec = mm[k]
            w.writerow([k, round(p, 4), round(pc, 4), round(e, 4), round(ec, 4),
                        round(pc + ec, 4), round(100 * e / (p + e), 6)])
    print(f"monthly_summary.csv            : {len(mm)} 行")

    # ---------- 3) 终端价值敏感性 ----------
    n = 0
    v0 = summary["parameters"]["terminal_value_yuan_per_internal_kwh"]
    with (OUT / "sensitivity_terminal.csv").open("w", newline="", encoding="utf-8-sig") as h:
        w = csv.writer(h)
        w.writerow(["date", "terminal_value_factor", "terminal_value_yuan_per_kwh",
                    "natural_day_cost_yuan", "soc_end_kwh"])
        for d in payload["days"]:
            for x in d["sensitivity"]:
                w.writerow([d["date"], x["terminal_value_factor"],
                            round(v0 * x["terminal_value_factor"], 6),
                            round(x["natural_day_cost_yuan"], 4),
                            round(x["soc_end_kwh"], 4)])
                n += 1
    print(f"sensitivity_terminal.csv       : {n} 行")

    # ---------- 4) 三策略对照 ----------
    T = summary["totals_natural_day"]
    B = summary["baseline_no_storage"]
    F = summary["local_counterfactual_fixed_storage"]
    with (OUT / "baseline_compare.csv").open("w", newline="", encoding="utf-8-sig") as h:
        w = csv.writer(h)
        w.writerow(["strategy", "total_cost_yuan", "planned_cost_yuan",
                    "emergency_cost_yuan", "note"])
        w.writerow(["主策略：情景优化+因果补救", round(T["total_cost_yuan"], 4),
                    round(T["planned_purchase_cost_yuan"], 4),
                    round(T["emergency_purchase_cost_yuan"], 4), "交付结果"])
        w.writerow(["固定参考储能（局部反事实）", round(F["total_cost_yuan"], 4),
                    round(F["planned_purchase_cost_yuan"], 4),
                    round(F["emergency_purchase_cost_yuan"], 4),
                    "每日SOC起点复制主策略，非独立全年策略"])
        w.writerow(["无储能基线", round(B["total_cost_yuan"], 4),
                    round(B["planned_purchase_cost_yuan"], 4),
                    round(B["emergency_purchase_cost_yuan"], 4), "同情景集逐时段最优"])
    print("baseline_compare.csv           : 3 行")

    # ---------- 5) SOC 边界触及 ----------
    tol = 1.0
    with (OUT / "soc_bound_check.csv").open("w", newline="", encoding="utf-8-sig") as h:
        w = csv.writer(h)
        w.writerow(["date", "time_start", "soc_start_kwh", "soc_end_kwh",
                    "touch_lower", "touch_upper"])
        for r in iv:
            s0, s1 = float(r["soc_start_kwh"]), float(r["soc_end_kwh"])
            w.writerow([r["date"], r["time_start"], round(s0, 4), round(s1, 4),
                        int(s0 <= 1200 + tol or s1 <= 1200 + tol),
                        int(s0 >= 10800 - tol or s1 >= 10800 - tol)])
    print(f"soc_bound_check.csv            : {len(iv)} 行")

    # ---------- 6) SOC / 充放电 直方图 ----------
    soc = np.array([float(r["soc_start_kwh"]) for r in iv])
    chg = np.array([float(r["charge_kwh"]) for r in iv])
    dis = np.array([float(r["discharge_kwh"]) for r in iv])
    with (OUT / "soc_charge_hist.csv").open("w", newline="", encoding="utf-8-sig") as h:
        w = csv.writer(h); w.writerow(["series", "bin_left", "bin_right", "count"])
        for name, arr in [("soc", soc), ("charge", chg), ("discharge", dis)]:
            edges = (np.linspace(1200, 10800, 41) if name == "soc"
                     else np.linspace(0, 5000 * DT, 41))
            cnt, _ = np.histogram(arr, bins=edges)
            for i in range(len(cnt)):
                w.writerow([name, round(edges[i], 4), round(edges[i + 1], 4), int(cnt[i])])
    print("soc_charge_hist.csv            : 120 行")

    # ---------- 7) 预测误差按小时 ----------
    err_h = collections.defaultdict(list)
    for r in iv:
        hr = 24 if r["time_start"] == "24:00" else int(r["time_start"][:2])
        err_h[hr].append(float(r["actual_net_kwh"]) - float(r["forecast_net_kwh"]))
    with (OUT / "forecast_error_by_hour.csv").open("w", newline="", encoding="utf-8-sig") as h:
        w = csv.writer(h)
        w.writerow(["hour", "n", "mean_kwh", "std_kwh", "q05", "q25", "q50", "q75", "q95", "mae_kwh"])
        for k in range(24):
            v = np.array(err_h[k])
            w.writerow([k, len(v), round(v.mean(), 4), round(v.std(), 4),
                        *[round(float(np.percentile(v, q)), 4) for q in (5, 25, 50, 75, 95)],
                        round(float(np.abs(v).mean()), 4)])
    print("forecast_error_by_hour.csv     : 24 行")

    # ---------- 8) 紧急购电散点与电价档 ----------
    em = [r for r in iv if float(r["emergency_kwh"]) > 1e-7]

    def band_of(p):
        return ("谷(<0.5)" if p < 0.5 else "平(0.5-0.9)" if p < 0.9
                else "峰(0.9-1.25)" if p < 1.25 else "尖(≥1.25)")

    with (OUT / "emergency_scatter.csv").open("w", newline="", encoding="utf-8-sig") as h:
        w = csv.writer(h)
        w.writerow(["date", "time_start", "hour", "price_yuan_per_kwh",
                    "emergency_kwh", "price_band"])
        for r in em:
            hr = 24 if r["time_start"] == "24:00" else int(r["time_start"][:2])
            p = float(r["price_yuan_per_kwh"])
            w.writerow([r["date"], r["time_start"], hr, p,
                        round(float(r["emergency_kwh"]), 4), band_of(p)])
    band = collections.defaultdict(lambda: [0.0, 0])
    for r in em:
        k = band_of(float(r["price_yuan_per_kwh"]))
        band[k][0] += float(r["emergency_kwh"]); band[k][1] += 1
    tot = sum(v[0] for v in band.values())
    with (OUT / "emergency_by_price_band.csv").open("w", newline="", encoding="utf-8-sig") as h:
        w = csv.writer(h); w.writerow(["price_band", "emergency_kwh", "share_pct", "intervals"])
        for k in ["谷(<0.5)", "平(0.5-0.9)", "峰(0.9-1.25)", "尖(≥1.25)"]:
            e, c = band.get(k, [0.0, 0])
            w.writerow([k, round(e, 4), round(100 * e / tot, 4), c])
    print(f"emergency_scatter.csv          : {len(em)} 行")
    print("emergency_by_price_band.csv    : 4 行")

    print(f"\n全部绘图数据已写入 {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
