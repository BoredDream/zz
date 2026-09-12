# 微网与外部电网电力调控策略

本目录保存赛题原始材料，以及独立完成的第二问、第三问模型、推导、代码、结果和报告。

## 目录

- `problem/`：题面、附件和官方结果模板。
- `docs/q2_model.md`：第二问模型定义、信息边界和求解流程。
- `docs/q2_derivation.md`：分位数反例、直接情景模型与因果补救推导。
- `src/q2_solver.py`：预测、优化、逐日回测和审计输出。
- `scripts/build_result2.mjs`：使用官方模板生成 `result2.xlsx`。
- `scripts/run_q2.ps1`：Windows一键运行脚本。
- `scripts/validate_q2.py`：时标、48,096条记录、物理约束与工作簿对账。
- `docs/q3_model.md`、`docs/q3_derivation.md`：第三问多时点预测、调整结算与随机优化模型。
- `src/q3_solver.py`：第三问因果滚动SAA、共同储能轨迹、8种预报组合及结算敏感性回测。
- `scripts/run_q3.ps1`、`scripts/validate_q3.py`：第三问一键生成和独立验收。
- `reports/q2_report.md`：由真实附件数据生成的第二问报告。
- `outputs/q2/`：完整工作簿、逐日指标和逐时段审计数据。

## 固定口径

1. 时间标签采用用户确认的“区间起点”口径。
2. 每个自然日按 `0:00, 0:10, ..., 23:50` 建模。
3. 附件原始列 `0:10, ..., 0:00+1` 映射到绝对时刻，不做同一行循环移位。
4. 模板每行是当天0:00发布、覆盖00:10至次日00:00的同一版计划；自然日00:00购电来自上一日计划末列。
5. 每天0:00制定计划时，只使用已完整出现的历史轮廓；当日实际数据仅在对应时段到达后用于因果储能补救和结算。
6. 充电量和放电量均定义在交流母线侧，SOC递推为
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

独立复核：

```powershell
.\.venv\Scripts\python.exe .\scripts\validate_q2.py
```

## 输出定义

- `result2.xlsx`：按官方模板结构填写完整计划购电量、充放电量和紧急购电量。
- `interval_detail.csv`：2025.2.1—12.31全部10分钟时段的预测、计划、实际、储能和紧急购电记录。
- `daily_metrics.csv`：逐日计划购电费、紧急购电费、SOC和预测误差。
- `summary.json`：2025.2.1—12.31交付期汇总、四个指定日期结果及数值校验。
- `solver_payload.json`：供模板写入程序使用的完整结果。

第二问主模型直接保留历史残差情景及期望紧急购电费用，不再声称80%分位数替代与含储能随机优化等价。

## 第三问运行

```powershell
.\scripts\run_q3.ps1
```

第三问输出位于 `outputs/q3/`，包括官方模板工作簿 `result3.xlsx`、主策略48,096条自然日区间记录、8种预报组合逐日比较、冻结0:00预报基线、逐次发布日志、结算敏感性、汇总结果和预览图。报告为 `reports/q3_report.md`。主结算口径保留初始计划费并逐次计收调整费；退款/最终净额口径仅作敏感性，二者均需结合合同条款人工确认。该模型是可执行的滚动策略，不宣称严格多阶段随机最优。
