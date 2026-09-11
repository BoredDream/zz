# 微网与外部电网电力调控策略

本目录保存赛题原始材料和独立完成的第二问模型、推导、代码、结果及报告。

## 目录

- `problem/`：题面、附件和官方结果模板。
- `docs/q2_model.md`：第二问模型定义、信息边界和求解流程。
- `docs/q2_derivation.md`：80%分位数及滚动优化的数学推导。
- `src/q2_solver.py`：预测、优化、逐日回测和审计输出。
- `scripts/build_result2.mjs`：使用官方模板生成 `result2.xlsx`。
- `scripts/run_q2.ps1`：Windows一键运行脚本。
- `reports/q2_report.md`：由真实附件数据生成的第二问报告。
- `outputs/q2/`：完整工作簿、逐日指标和逐时段审计数据。

## 固定口径

1. 时间标签采用用户确认的“区间起点”口径。
2. 每个自然日按 `0:00, 0:10, ..., 23:50` 建模。
3. 附件原始列 `0:10, ..., 0:00+1` 映射到绝对时刻，不做同一行循环移位。
4. 每天0:00制定计划时，只使用此前已经出现的数据；当日真实数据仅用于紧急购电结算和回测。
5. 充电量和放电量均定义在交流母线侧，SOC递推为
   `S[t+1] = S[t] + 0.9*C[t] - D[t]/0.9`。

## 运行

在 PowerShell 中执行：

```powershell
.\scripts\run_q2.ps1 -Install
```

首次运行使用 `-Install` 创建 `.venv` 并安装依赖；以后可省略该参数。

单独运行求解器：

```powershell
.\.venv\Scripts\python.exe .\src\q2_solver.py --data-dir .\problem\data --output-dir .\outputs\q2 --report .\reports\q2_report.md
```

随后生成工作簿：

```powershell
node .\scripts\build_result2.mjs
```

## 输出定义

- `result2.xlsx`：按官方模板结构填写完整计划购电量、充放电量和紧急购电量。
- `interval_detail.csv`：2025.2.1—12.31全部10分钟时段的预测、计划、实际、储能和紧急购电记录。
- `daily_metrics.csv`：逐日计划购电费、紧急购电费、SOC和预测误差。
- `summary.json`：全年汇总、四个指定日期结果及数值校验。
- `solver_payload.json`：供模板写入程序使用的完整结果。

当前目录原先不含 `.git`，因此文件已写入工作目录，但没有创建提交或执行远程推送。

