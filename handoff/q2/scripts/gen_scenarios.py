# -*- coding: utf-8 -*-
"""重算四个指定日期的净负荷情景集（图1 情景包络的数据源）。

自包含版本：路径全部相对本文件解析，可直接在仓库内运行。
  · 读取仓库 problem/data/ 下的附件1、附件2（经 src/q2_solver.py 的确定性函数）
  · 写出 _figdata/netload_scenarios_4days.csv 与 _figdata/netload_scenarios_meta.json
  · 不使用任何随机数
  · 不修改仓库任何已有文件
"""
import sys, csv, json, datetime
from pathlib import Path
import numpy as np

HERE = Path(__file__).resolve().parent          # handoff/q2/scripts
Q2DIR = HERE.parent                             # handoff/q2
REPO = HERE.parents[2]                          # 仓库根（zz/）
OUT = Q2DIR / "_figdata"
sys.path.insert(0, str(REPO / "src"))

import q2_solver as S                            # noqa: E402

CFG = S.Config()
TARGETS = ["2025-03-20", "2025-06-21", "2025-09-23", "2025-12-21"]


def main() -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:                            # noqa: BLE001
        pass

    OUT.mkdir(parents=True, exist_ok=True)
    inputs = S.load_inputs((REPO / "problem" / "data").resolve(), CFG)
    net, cold, dates = inputs["net_actual"], inputs["cold_start_net"], inputs["dates"]

    # interval_detail.csv 用于交叉校验中心预测（读仓库已提交的结果，不重跑求解器）
    detail = REPO / "outputs" / "q2" / "interval_detail.csv"
    rec = {}
    if detail.exists():
        with detail.open(encoding="utf-8-sig", newline="") as h:
            for r in csv.DictReader(h):
                if r["date"] in TARGETS:
                    rec.setdefault(r["date"], {})[r["time_start"]] = (
                        float(r["forecast_net_kwh"]), float(r["actual_net_kwh"]))

    rows, sel = [], []
    for t in TARGETS:
        day = dates.index(datetime.date(*map(int, t.split("-"))))
        w = S.choose_weight(net, cold, day, CFG)
        scen, center, window = S.scenario_set(net, cold, day, w, CFG)

        err = float("nan")
        act = np.full(144, np.nan)
        if t in rec and len(rec[t]) == 144:
            keys = sorted(rec[t], key=lambda s: (24 if s == "24:00" else int(s[:2]),
                                                 0 if s == "24:00" else int(s[3:5])))
            got = np.array([rec[t][k][0] for k in keys])
            act = np.array([rec[t][k][1] for k in keys])
            err = float(np.abs(center[:144] - got).max())
        sel.append({"date": t, "weight": w, "window": window,
                    "n_scenarios": int(scen.shape[0]),
                    "center_check_max_abs_err_kwh": err})
        print(f"  {t}: day={day:3d} w={w} window={window} 情景数={scen.shape[0]} "
              f"中心预测复现误差={err:.3e} kWh")
        for i in range(scen.shape[0]):
            for h in range(144):
                rows.append([t, h, i, round(float(scen[i, h]), 6),
                             round(float(center[h]), 6), round(float(act[h]), 6)])

    with (OUT / "netload_scenarios_4days.csv").open("w", newline="", encoding="utf-8-sig") as h:
        wr = csv.writer(h)
        wr.writerow(["date", "interval_index", "scenario_id",
                     "scenario_net_kwh", "center_forecast_kwh", "actual_net_kwh"])
        wr.writerows(rows)
    (OUT / "netload_scenarios_meta.json").write_text(
        json.dumps(sel, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n已写出 {OUT/'netload_scenarios_4days.csv'}（{len(rows)} 行）")
    print(f"已写出 {OUT/'netload_scenarios_meta.json'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
