# 第二问 图片代码（本分支即「图片代码」分支）

> 本目录是**第二问全部图片的代码**，每张图一个文件。
> 分支名用 ASCII 的 `q2-figure-code`，对应你所说的「图片代码」分支。
> 论文素材与成绩单见另一分支 `paper-handoff-materials` 的 `handoff/q2/`。

---

## 1. 目录结构

```
handoff/q2/code/
├── README.md                  ← 本文件（代码索引与运行说明）
├── run_all_figures.py         ← 一键生成全部 9 张图
├── make_album.py              ← 把 9 张图合并成《图集_第二问_论文版.pdf》
├── gen_plot_data.py           ← 生成 _figdata/ 全部绘图数据（读附件1 + outputs/q2）
├── gen_scenarios.py           ← 重算净负荷情景集（图1 情景包络的数据源）
└── q2_figures/                ← 图件包：每张图一个模块
    ├── __init__.py            ← 包说明 + FIGURE_INDEX（图号 ↔ 模块 ↔ 输出文件名）
    ├── _common.py             ← ★ 公共件：路径、配色、全局样式、共用工具（唯一权威定义）
    ├── fig1.py                ← 图1   净负荷预测与情景包络（2×2）
    ├── fig1b.py               ← 图1b  典型日负荷/光伏/净负荷与分时电价
    ├── fig2a.py               ← 图2a  单日计划购电对分时电价的响应（单主题图）
    ├── fig2b.py               ← 图2b  月度购电量构成与紧急购电占比
    ├── fig3a.py               ← 图3a  四个指定日期的储电量轨迹（单面板四日对比）
    ├── fig3b.py               ← 图3b  储电量分布与充放电量分布
    ├── fig4a.py               ← 图4a  预测误差日内分布与逐月 MAE
    ├── fig4b.py               ← 图4b  紧急购电量的电价档与时段分布
    └── fig5.py                ← 图5   费用构成与终端储电价值敏感性
```

**代码规模**：由 826 行单文件拆为 13 个 Python 文件 ——
`q2_figures/` 包内 11 个（`_common.py` 170 行最长，各图模块 110–156 行）
加顶层 2 个（`run_all_figures.py` 66 行、`make_album.py` 82 行）。
每张图的模块含完整的设计意图、口径护栏与数据来源说明。

---

## 2. 图号 ↔ 模块 ↔ 输出文件

| 图号 | 模块 | 输出文件名（figures/ 下，各 3 种格式） | 这张图回答什么 |
|---|---|---|---|
| 图1 | `q2_figures/fig1.py` | `fig1_netload_forecast` | 预测与真实观测在四个指定日期的吻合度、不确定性范围 |
| 图1b | `q2_figures/fig1b.py` | `fig1b_typical_day` | 典型日负荷/光伏/净负荷与电价的日内变化 |
| 图2a | `q2_figures/fig2a.py` | `fig2a_single_day_dispatch` | 模型是否实现"低价多购、高价少购" |
| 图2b | `q2_figures/fig2b.py` | `fig2b_monthly_stack` | 月度购电量构成、紧急购电是否可控 |
| 图3a | `q2_figures/fig3a.py` | `fig3a_soc_trajectory` | 储电量是否始终在 1200–10800 kWh 内 |
| 图3b | `q2_figures/fig3b.py` | `fig3b_soc_hist` | 储能是否长期贴边界、是否打满功率上限 |
| 图4a | `q2_figures/fig4a.py` | `fig4a_forecast_error` | 预测误差有无系统性偏置、哪个月最差 |
| 图4b | `q2_figures/fig4b.py` | `fig4b_emergency_cost_band` | 紧急购电落在什么电价档与什么时刻 |
| 图5 | `q2_figures/fig5.py` | `fig5_strategy_compare` | 储能与日内补救各值多少钱、结果稳不稳 |

---

## 3. 怎么跑

在**任意目录**均可执行（脚本按自身位置解析路径）：

```powershell
cd handoff/q2/code

python run_all_figures.py            # 生成全部 9 张（每张 3 种格式）
python run_all_figures.py 2a 5       # 只生成图2a 与图5
python q2_figures/fig2a.py           # 单独运行某一张（调试用，不依赖包导入）

python make_album.py                 # 合并成《图集_第二问_论文版.pdf》
```

**依赖**：`numpy`、`matplotlib`（`gen_plot_data.py` 另需 `openpyxl`；
`gen_scenarios.py` 另需 `scipy` 与仓库 `src/q2_solver.py`）。

**绘图数据已固化**在 `handoff/q2/_figdata/`（11 个 CSV/JSON），
因此出图**不需要重跑求解器**。仅在需要重新生成数据时才运行：

```powershell
python gen_plot_data.py     # 读 problem/data/附件1.xlsx 与 outputs/q2/ 的已提交结果
python gen_scenarios.py     # 用 src/q2_solver.py 的确定性函数重算情景集
```

---

## 4. 视觉规范（在 `q2_figures/_common.py` 统一定义）

| 项目 | 规范 |
|---|---|
| 背景 / 风格 | 纯白、简洁二维，**无渐变 / 发光 / 3D / 阴影** |
| 边框 | 去掉顶部与右侧；左/下 0.7 pt、色 `#B4BBC2` |
| 网格 | 仅水平，`#DFE3E7`、lw 0.5、alpha 0.30（弱化） |
| 主色 | 深蓝灰 `#4C6E91`（计划量、模型预测等主数据）；深版 `#3A5470` 用于中位数线 |
| 强调色 | 去饱和赤陶 `#A9705A`（紧急购电、最大偏差、最差月份、核心结论）—— 全篇唯一暖色 |
| 实测值 | 灰 `#5B6470` |
| 对照 / 次要 | 灰 `#9AA4AE`、浅灰 `#C9D0D6` |
| 储电量 | 低饱和绿 `#7E9B84`（**仅图3a、图3b 使用**） |
| 多重区分 | 颜色 + 线型 + marker：实线/● = 主数据；虚线/■ = 对照或实测；点划线/▲ = 次要 |
| 双轴 | **不使用 twinx**（图2a 为上下分栏单主题，图3a 为单面板四日对比） |
| 字号 | 刻度 8.5、轴标题 9.5、图例 8.5；文字统一深灰 `#333333` |
| 版面 | A4 双栏 7.1 × (3.2–4.7) 英寸 |
| 输出 | SVG（矢量、文字可编辑）+ PDF（矢量）+ PNG（**600 dpi**） |

改配色只需改 `_common.py` 的 `C_*` 常量，9 张图同时生效。

---

## 5. 字体注意事项（会影响出图质量）

本机实测：**只有 `Microsoft YaHei` 同时支持中文与 U+2212 减号**。
`SimHei`、`SimSun`、`KaiTi`、`FangSong`、`DengXian`、`Microsoft JhengHei`
**均缺 U+2212 字形** —— 若用它们出图，纵轴负值会渲染成**空白方框**。

`_common.py` 已做双保险：① 字体优先级把 `Microsoft YaHei` 排首位；
② 设置 `axes.unicode_minus = False`，用 ASCII 连字符替代 U+2212。
换机器出图时若无 Microsoft YaHei，请改用开源的 `Noto Sans CJK SC`。

---

## 6. 代码内的口径护栏（改图时请勿违反）

每张图的模块 docstring 里都写了该图的**核心任务**与**不可越界的口径**，摘要如下：

- **图1**：色带是「历史残差情景包络」，**不是置信区间、不是预测区间**（n=7 时算不出 95% 分位）；
  图注覆盖率必须用分位带口径，与图内一致。
- **图1b**：光伏"日落衰减"是真实数据（19:20 归零），不是缺失；
  时间标签修复的来龙去脉写在模块 docstring 里，并内置了时间轴自检防回归。
- **图2a**：只回答电价响应，**不再承担预测精度展示**（该任务归图1）；
  用的是 `interval_detail.csv` 的**自然日口径**，不是 result2.xlsx 的模板行口径。
- **图3a**：图注"全部时段位于运行区间内"由代码实测校验（`meta["in_band"]`）。
- **图4b**：66% 落在尖峰价档是"预测误差落在高价时段"的结果，
  **不得写成策略偏好高价购电**；紧急购电电量占 1.27% 但费用占约 11.22%。
- **图5**：「固定参考储能」是**局部反事实**，每日 SOC 起点复制主策略，
  **不是独立连续全年策略**，不得与主策略并列为两种完整策略。

---

## 7. 拆分正确性验证

拆分（826 行单文件 → 12 个文件）后已做逐图验证：

| 验证项 | 结果 |
|---|---|
| 新实现的 PNG 与拆分前**逐像素**比对 | ✅ **9/9 张像素完全一致** |
| 新 meta 中沿用旧键的数值 | ✅ 全部一致（个别键重命名以更清晰，如 `mae` → `mae_kwh_per_interval`） |
| 新 meta 中新增的派生值 | ✅ 逐项验算通过（如 `saving_pct_of_baseline = 22.714077% = 4,248,402.3834 / 18,703,830.0174`） |
| 9 张图重出 | ✅ 9/9 成功 |
| 单张图独立运行 | ✅ 已验证（`python q2_figures/fig2a.py`） |

**结论：拆分为独立文件只改变代码组织，未改动任何数据、数值或渲染结果。**
