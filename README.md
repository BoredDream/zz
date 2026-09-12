# 微网与外部电网电力调控策略

本目录保存赛题原始材料，以及独立完成的第二问、第三问模型、推导、代码、结果和报告。

## 目录

- `problem/`：题面、附件和官方结果模板。
- `src/q1_solver.py`：第一问单日确定性线性规划（周期条件 `S_0 = S_144`、弃电变量、起点自由敏感性与区间终点反事实口径）。
- `scripts/build_result1.mjs`、`scripts/validate_q1.py`：第一问工作簿生成与独立验收（另一套消元编码 + 内点法重解）。
- `reports/q1_report.md`：第一问计算报告（含与独立对照标准的逐项复核）。
- `outputs/q1/`：第一问工作簿、结果与逐时段明细。
- `docs/q2_model.md`：第二问模型定义、信息边界和求解流程。
- `docs/q2_derivation.md`：分位数反例、直接情景模型与因果补救推导。
- `src/q2_solver.py`：预测、优化、逐日回测和审计输出。
- `scripts/build_result2.mjs`：使用官方模板生成 `result2.xlsx`。
- `scripts/run_q2.ps1`：Windows一键运行脚本。
- `scripts/validate_q2.py`：时标、48,096条记录、物理约束与工作簿对账。
- `docs/q3_multistage_model.md`：**第三问正式模型**的定义——模板行时间网格、母线侧储能口径、题面费用函数、四阶段非预期性结构、阶段LP、预测与场景生成、实时层、报表口径。
- `src/q3_multistage.py`：第三问正式模型的多阶段随机规划求解器（滚动两阶段SAA + 贪心实时层）。
- `scripts/export_q3_multistage.py`：第三问全年回测与产物落盘（payload / npz / summary）。
- `scripts/build_result3_multistage.mjs`：用官方附件5模板生成第三问 `result3.xlsx`。
- `scripts/validate_q3_multistage.py`：第三问独立验收（物理约束、费用口径恒等、工作簿逐格对账）。
- `outputs/q3_multistage/`：第三问正式工作簿与结果。
- `docs/q3_model.md`、`docs/q3_derivation.md`：第三问**旧模型**（共同储能轨迹）的模型与推导，保留作对照。
- `src/q3_solver.py`：第三问旧模型（因果滚动SAA/MPC、共同储能轨迹、8种预报组合、冻结预报基线及结算敏感性回测，含按策略检查点与断点续跑），结果保留在 `outputs/q3/`。
- `scripts/run_q3.ps1`、`scripts/validate_q3.py`：第三问旧模型的一键生成和独立验收。
- `scripts/test_q3_units.py`：第三问小规模单元测试（求解器索引、能量平衡、SOC递推、终端价值、跨日映射、结算口径、执行轨迹锁定）。
- `reports/q2_report.md`：由真实附件数据生成的第二问报告。
- `outputs/q2/`：完整工作簿、逐日指标和逐时段审计数据。

## 固定口径

1. 时间标签采用用户确认的“区间起点”口径。
2. 每个自然日按 `0:00, 0:10, ..., 23:50` 建模。
3. 附件原始列 `0:10, ..., 0:00+1` 映射到绝对时刻，不做同一行循环移位。
4. 模板每行是当天0:00发布、覆盖00:10至次日00:00的同一版计划；自然日00:00购电来自上一日计划末列。
5. 每天0:00制定计划时，只使用已完整出现的历史轮廓；当日实际数据仅在对应时段到达后用于因果储能补救和结算。
6. 充电量和放电量均定义在交流母线侧，SOC递推为
   `S[t+1] = S[t] + 0.9*C[t] - D[t]/0.9`。问题1、2、3 均适用。
7. 第三问结算采用题面口径 `C = p*min(x,q) + 1.5p*(q-x)^+ + 0.5p*(x-q)^+ + 5p*z`：
   只对实际取用的电量付基价，下调部分另收50%违约金。"计划费沉没、逐笔计收调整费"
   是另一种口径，仅作对照，不与本口径混算。

## 运行

第一问（单日确定性优化）单独运行：

```powershell
$env:PYTHONPATH="src"; .\.venv\Scripts\python.exe -X utf8 src\q1_solver.py --data-dir problem/data --output-dir outputs/q1 --report reports/q1_report.md
node scripts/build_result1.mjs
$env:PYTHONPATH="src"; .\.venv\Scripts\python.exe -X utf8 scripts\validate_q1.py
```

第二问在 PowerShell 中执行：

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

## 第三问运行（正式模型）

```powershell
$env:PYTHONPATH="src"
.\.venv\Scripts\python.exe -X utf8 scripts\export_q3_multistage.py 30 0,1,2,3   # 全年回测，约 374 s
node scripts\build_result3_multistage.mjs 0123 30                              # 生成 result3.xlsx
.\.venv\Scripts\python.exe -X utf8 scripts\validate_q3_multistage.py 0123 30   # 独立验收
```

模型定义见 `docs/q3_multistage_model.md`，输出位于 `outputs/q3_multistage/`。
时间口径为模板行（`t=0` 覆盖 0:10–0:20，`t=143` 覆盖次日 0:00–0:10），
表 2 的六个段即 `t=0..23, 24..47, …, 120..143`。

## 第三问运行（旧模型，保留对照）

```powershell
.\scripts\run_q3.ps1
```

第三问旧模型输出位于 `outputs/q3/`：官方模板工作簿 `result3.xlsx`、主策略48,096条自然日区间记录、10套策略逐日比较、冻结0:00预报基线、主策略逐次发布日志 `release_log.json`（全部策略另存于 `release_logs/`）、结算敏感性、汇总结果、检查点 `checkpoints/` 和预览图。报告为 `reports/q3_report.md`。

- 共同储能轨迹：同一发布时刻的全部情景共享购电、充电、放电和SOC，只有紧急购电与弃电随情景变化，消除情景提前预知未来。
- 执行端严格按发布时锁定的共同充放电轨迹，不再用贪心规则覆盖优化结果；因此允许出现“紧急购电同时充电”，报告中按审计结果统计并解释。
- 自然日按00:00—24:00结算，模板行按00:10—次日00:00单独结算，模板末列“次日00:00”的调整费结转到下一自然日，两者不能跨表相加。
- 主结算口径保留初始计划费并逐次计收调整费（上调1.5p、下调0.5p）；退款/最终净额口径仅作敏感性，二者均需结合合同条款人工确认。
- 该模型是可执行的滚动策略，`strict_multistage_optimal=false`，不宣称严格多阶段随机最优。

中断后重新执行同一条命令即可续跑：每套策略完成后立即写入 `outputs/q3/checkpoints/<策略>.json`，只有输入SHA256、模型版本与参数签名完全一致时才复用检查点。
