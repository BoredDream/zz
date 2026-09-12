# 第二问：给论文手的交付包

本目录是**第二问的全部可交付材料**，自包含：数据 → 绘图脚本 → 成图（SVG/PDF/PNG）→ 论文素材 → 图注。
本分支为 `paper-handoff-materials`，基于 `master` 的 `37957da`。

> **引用契约**：论文里凡出现第二问的数字或结论，口径以
> **`reports/q2_paper_handoff.md`** 为准（对标仓库已有的 `reports/q3_paper_handoff.md`）。
> 本目录只提供素材与图件，不重复定义口径。

---

## 1. 先读哪个

| 顺序 | 文件 | 给谁 | 内容 |
|---|---|---|---|
| ① | `reports/q2_paper_handoff.md` | 论文手 | **口径契约**：能写什么、不能写什么、每个数字的来源 |
| ② | `handoff/q2/第二问_论文素材包.md` | 论文手 | §A–§J 全套素材（公式、符号表、假设、数据预处理、结果表、检验、评价、摘要素材）+ 附录 §K 代码索引 |
| ③ | `handoff/q2/figures/README_图表说明.md` | 论文手 + 编程手 | 9 张图各自"是干嘛的" + 可直抄图注 + 视觉规范 + 改图指引 |
| ④ | `handoff/q2/图集_第二问_论文版.pdf` | 论文手 | 9 张图合并，一次审阅/打印 |
| ⑤ | `handoff/q2/第二问_题目表格_表1表2表3.csv` | 论文手 | 表1/表2/表3 可复制版（每行带口径列） |

---

## 2. 目录结构

```
handoff/q2/
├── README.md                            ← 本文件
├── 第二问_论文素材包.md                   ← §A–§J + 附录 §K
├── 第二问_题目表格_表1表2表3.csv
├── 第二问_核心指标汇总.csv
├── 第二问_图表数据需求清单.csv
├── 图集_第二问_论文版.pdf                 ← 9 张图合并
├── figures/
│   ├── README_图表说明.md
│   ├── figs_q2_paper.py                  ← 绘图脚本（一次产出 9 张）
│   ├── make_album.py
│   └── fig1…fig5 共 9 张 × {svg, pdf, png} = 27 个图片文件
├── scripts/
│   ├── gen_plot_data.py                  ← 生成 _figdata/ 全部绘图数据
│   └── gen_scenarios.py                  ← 重算净负荷情景集（图1 数据源）
└── _figdata/                             ← 11 个绘图数据文件（CSV/JSON，均带表头）
```

---

## 3. 怎么跑

在**仓库根目录**执行（脚本路径全部相对自身解析，任意位置调用均可）：

```powershell
# 重出全部 9 张论文级图（同时覆盖 svg / pdf / png）
python handoff/q2/figures/figs_q2_paper.py

# 重出图集 PDF（输出到 handoff/q2/）
python handoff/q2/figures/make_album.py

# 仅当需要重新生成绘图数据时（不重跑求解器）
python handoff/q2/scripts/gen_plot_data.py
python handoff/q2/scripts/gen_scenarios.py
```

**依赖**：`numpy`、`matplotlib`、`openpyxl`（`gen_scenarios.py` 另需 `scipy`）。
**字体**：脚本优先使用 `Microsoft YaHei`；本机实测它是唯一同时支持中文与 U+2212 减号的 CJK 字体，
`SimHei`/`SimSun`/`KaiTi`/`FangSong`/`DengXian` 等会把负号渲染成空白方框。
换机器出图请改用开源的 `Noto Sans CJK SC`，并保持 `axes.unicode_minus = False`。

---

## 4. 数据来源与一致性

- 绘图数据由 `scripts/gen_*.py` 从 **`problem/data/` 的原始附件**与 **`outputs/q2/` 的已提交结果**整理而来，
  **不重跑求解器、不修改仓库任何已有文件**。
- 本轮已逐项验证：素材包与 9 张图引用的**全部数值**与 `outputs/q2/` 一致
  （57 项对照，0 项超差；含 `interval_detail.csv`、`daily_metrics.csv`、`summary.json`、`solver_payload.json`）。
- 图1 的情景包络由 `gen_scenarios.py` 用 `src/q2_solver.py` 的**确定性函数**重算，
  中心预测与已落盘的 `forecast_net_kwh` **最大绝对差 0.000e+00**。

**一条必须注意的口径差异**：`interval_detail.csv` 的 `committed_plan_kwh` 是**自然日 00:00–24:00**口径，
`payload.template_grid_kwh` 是**模板行**口径（当日 0:00 发布的 144 项，起点 00:10）。
两者错开一格，合计相差约 1,200 kWh/天。图2a 横轴为自然日时刻，用的是自然日口径；
表1/表2/表3 与 `result2.xlsx` 用模板行口径。**引用"全天"时务必注明是哪一种。**

---

## 5. 本分支不含什么

| 项 | 说明 |
|---|---|
| 第一问 | 尚无模型与结果。**图6（第一问 vs 第二问对比）因此未生成**，未用第二问数字冒充。 |
| 第三问图表 | 按需搁置。第三问自身的口径契约见 `reports/q3_paper_handoff.md`。 |
| 工作区探针脚本 | 数据核对用的 `_q2_*.py` 探针未随库分发（属过程工具，非交付物）。 |
| 论文正文 | 本分支只提供**素材与图件**，不提供成稿。 |