# Requirements · UI 浅色升级 & Tab 完整度补齐

## 背景

前序迭代已完成 4 块底层 Skill（SQP 品牌分析、GEO 6 维度审计、Rufus Probe 问题生成、Rufus 调研双模式），并在 UI 加了 `Rufus 调研` 和 `SQP 品牌分析` 两个新 tab。

这一版主要解决两个遗留问题：

1. **UI 改了一半**：从深色科技风切换到浅色高级感（象牙白 / 墨 / 金 / 深青）时，部分硬编码颜色没清干净，且新 tab（Rufus 调研 / SQP）里用到的小组件（textarea / 卡片分隔条 / 下载按钮）还没与浅色变量完全对齐。
2. **Tab 完整度**：`Rufus & COSMO 专家建议` tab 新增了 `geo_audit`（GEO 6 维度评分）和 `qa_suggestions.probing_strategy`（Rufus Probe 分配策略）两个后端字段，前端目前**没有渲染**这些新数据 —— 用户看不到新能力。

> **说明**：AI Agent / LLM Provider / 悬浮助手相关需求已搁置（后端代码 `src/agent/` 暂时保留，但前端不接线）。这部分独立做一个新 spec。

## 愿景（一句话）

**把四个业务 tab（产品素材 / Rufus & COSMO / Rufus 调研 / SQP 品牌分析）都打磨到浅色高级感的一致视觉，并把 GEO 6 维度和 Rufus Probe 策略两个后端已有但前端未渲染的能力显式展示出来。**

## 术语

- **GEO 6 维度**：`expert_suggestions.py:_build_geo_audit()` 产出，含 scenario_coverage / audience_match / decision_drivers / positioning / user_language / ai_readable_structure 六维度 100 分制评分 + recommendations。
- **Rufus Probe Strategy**：`expert_suggestions.py:_build_rufus_probe_strategy()` 产出，按 listing 最弱三类自动按 3/3/2/2 分配 10 题。
- **结果卡 / 报告卡**：tab 内部展示后端数据的视觉块，主要用 `.expert-card` / `.expert-panel` 样式。

## 目标（In Scope）

- **UI 浅色化**：所有业务 tab 完全对齐浅色 CSS 变量，**无任何深色残留**。
- **产品素材生成 tab**：仅跟随全局 CSS 变量自动浅色化，**不改功能、不改布局**。
- **Rufus & COSMO 专家建议 tab**：
  - 皮肤对齐
  - **新增 GEO 6 维度评分可视化**（雷达 / 进度条 / 建议列表）
  - **新增 Rufus Probe Strategy 可视化**（弱点识别 + 10 题探针问题预览）
- **Rufus 调研 tab**：皮肤对齐 + 做一次完整端到端回归（确保之前写的手动 / 自动两种模式在新皮肤下仍可用）。
- **SQP 品牌分析 tab**：皮肤对齐 + 确保上传 / 下载 / 历史 session 列表可用。
- **Settings / Init Guide / Activation 等 Modal**：皮肤对齐（已有一部分，差什么补什么）。

## 非目标（Out of Scope）

- 不接入 AI Agent / LLM Provider / 悬浮助手（暂停，独立 spec）
- 不改任何业务逻辑（Skill 层 / Flask 路由 / Python 模块）
- 不做新功能 / 新 tab / 新工具
- 不做移动端响应式（维持现状）
- 不做主题切换（只做浅色一种）
- 产品素材 tab 不额外加新组件

---

## 需求列表

### R1 · 全局浅色 UI 升级

**User Story**：作为用户，我希望整套界面是高级感的浅色（象牙白 / 墨 / 金 / 深青），不残留任何深色痕迹。

#### Acceptance Criteria (EARS)

1. CSS 根变量**应**沿用已定义的以下值：`--bg:#f8f5f0` / `--bg2:#fff` / `--bg3:#f1ece2` / `--bg4:#faf6ef` / `--text:#1a1f2c` / `--text-light:#41485b` / `--muted:#8a8070` / `--border:#e5ddd0` / `--border-light:#efe9dd` / `--accent:#1a1f2c` / `--accent2:#c9a66b` / `--teal:#0f766e` / `--green:#15803d` / `--red:#b91c1c` / `--warning:#c2704b`。
2. 整套界面**不得**残留任何原深色 palette（`#0f1117` / `#1a1d27` / `#22263a` / `#2d3348` / `#e2e8f0` / `#8892a4` / `#1677ff` / `#f59e0b` 等）。
3. 所有**使用写死 `rgba(255,255,255,.N)` 作为浅色的旧代码**应改为使用 `var(--bg3)` / `var(--bg4)` / `var(--bg2)`。
4. 所有**写死 `color:#fff` 但背景变成浅色后对比度不足的地方**应改成 `var(--text)` 或 `var(--text-light)`。
5. 高亮 / 强调元素（badge / hover 边框 / 高亮文字 / 焦点态）**应**统一使用金色 `--accent2`。
6. CTA 主按钮（`.btn-start` / `.btn-primary`）**应**用墨色 `--accent`，hover 加深到 `#000`；disabled 使用 `--bg3` + `--muted`。
7. Modal 遮罩**应**用 `rgba(26,31,44,.45)` + `backdrop-filter: blur(4px)`，**不得**用纯黑 `rgba(0,0,0,.7)`。
8. 表单 input focus 态**应**有柔和 ring：`border-color: var(--accent2)` + `box-shadow: 0 0 0 3px rgba(201,166,107,.15)`。
9. 滚动条 hover 状态**应**变成金色 `var(--accent2)`。

### R2 · 产品素材生成 tab · 样式跟随

**User Story**：作为用户，我希望产品素材 tab 里所有元素视觉上和新浅色风格一致，但功能和布局完全不变。

#### Acceptance Criteria (EARS)

1. `.image-workspace` / `.ref-image-card` / `.prompt-card` / `.result-card` **应**继承新浅色变量，**不得**出现深色背景。
2. 上传拖拽区 `#uploadZone` **应**在 hover / dragover 时显示金色 `--accent2` 边框 + `--bg4` 底色。
3. 图片卡片的"MAIN / APLUS"标签 **应**保持原来的识别度（蓝=主图、金=A+），但底色可以从 `rgba(22,119,255,.85)` 调到更克制的配色（主图：`--teal`，A+：`--accent2`）。
4. 该 tab 的**业务逻辑（上传 / 拖拽 / 点击设为原型 / 调生成 / 下载）不得**有任何变化。
5. tab 内所有 copy-btn / send-chatgpt-btn / result-card actions **应**统一为浅色按钮样式。

### R3 · Rufus & COSMO 专家建议 tab · 新增 GEO 6 维度可视化

**User Story**：作为用户，我希望在"标题优化"子 tab 里直接看到 GEO 6 维度的评分（后端已产出但前端没显示），因为这比原有的 5 项结构 checks 信息量更大。

#### Acceptance Criteria (EARS)

1. `renderTitle()` JS 函数**应**在现有 COSMO 评分卡之后、结构检测卡之前，**新增一张「GEO 6 维度审计」卡片**。
2. 此卡片**应**显示 `geo_audit.total_score` / 100 的总分，配合 `geo_audit.overall_grade` 等级标签（A/B/C/D）。
3. 此卡片**应**以进度条形式列出 6 个维度（每条：维度名 / 得分 / 满分 / level 图标 ✓ ~ ✗）。
4. 每个维度进度条下方**应**显示 `gap` 前 2-3 条（缺失要点）或 `note`（说明）。
5. 此卡片底部**应**显示 `geo_audit.recommendations` 前 3 条（按 priority 排序 high/medium/low），每条带🔴🟡🟢图标 + area + action + why。
6. 若 `geo_audit` 字段缺失或为空对象，该卡片**应**完全隐藏（不显示占位符）。
7. 此可视化**不得**影响原有 COSMO 分析卡、结构检测卡、关键词缺口卡的展示顺序和内容。

### R4 · Rufus & COSMO 专家建议 tab · 新增 Rufus Probe Strategy 可视化

**User Story**：作为用户，我希望在"Q&A 建议"子 tab 里看到"Rufus 探针策略"（后端已有 probing_strategy 字段但前端没显示），了解 listing 哪些维度最弱、建议问 Rufus 哪些探针问题。

#### Acceptance Criteria (EARS)

1. `renderQa()` JS 函数**应**在原有 Q&A 列表**上方**新增一张「Rufus 探针策略」卡片。
2. 此卡片**应**显示 `probing_strategy.framework` 说明（一行小字：自适应分配最多 10 题）。
3. 此卡片**应**显示 priority 三级：primary / secondary / tertiary（每级一个色彩标签 + 维度中文名 + 理由）。
4. 此卡片**应**以进度条形式显示 5 类维度（场景与人群 / 决策因素 / 对比与替代 / 用户反馈 / 买家自然语言）的 weakness_scores（0-10 分，分数越低越弱）。
5. 此卡片**应**折叠展示 `questions` 字段 —— 点击标题展开后显示各类型的问题列表（每题带 purpose）。
6. 若 `probing_strategy` 字段缺失，该卡片**应**完全隐藏。
7. 此可视化**不得**影响原有 Q&A 对列表。
8. 此卡片上**应**有一个"复制全部探针问题到 Rufus 调研 tab"按钮（点击跳到 Rufus 调研 tab 并自动填问题，前提是 Rufus 调研 tab 已加载过 ASIN）。

### R5 · Rufus 调研 tab · 浅色化 + 端到端回归

**User Story**：作为用户，我希望 Rufus 调研 tab 在新皮肤下仍能正常工作（生成问题 / 自动检测 Chrome / 手动粘贴 / 生成报告）。

#### Acceptance Criteria (EARS)

1. `#mainTabRufus` 内所有 `.expert-card` / input / textarea / button **应**继承浅色变量。
2. "Chrome 检测"状态文字**应**使用 `--green` / `--warning` / `--red` 三色，而非旧 accent 蓝。
3. Step 3 手动粘贴表单里的 textarea **应**使用 `--bg3` 底色 + `--border` 边框，focus 态金色 ring。
4. 报告卡（`#rufusReportArea`）**应**用浅色卡片样式，维度进度条颜色对齐（高分绿 / 中分金 / 低分红）。
5. 从"生成探针问题" → "粘贴答案" → "生成报告"的端到端流程 **应**在浅色化后仍可跑通（通过现有测试脚本 `rufus_regression.py` 验证）。
6. 报告预览链接（"在新窗口打开 Markdown"）**应**用主 CTA 样式。

### R6 · SQP 品牌分析 tab · 浅色化 + 端到端回归

**User Story**：作为用户，我希望 SQP tab 在新皮肤下仍可上传 CSV / 下载报告 / 查看历史 session。

#### Acceptance Criteria (EARS)

1. `#mainTabSqp` 内所有卡片 **应**继承浅色变量。
2. `#sqpDropZone` hover / dragover **应**使用金色边框。
3. "概览卡"的 4 个数字块（分析周数 / 高转化词 / WoW 新入列 / WoW 跌出列）**应**用浅色底 + 对应语义色文字（`--accent` / `--green` / `--warning` / `--red`）。
4. 历史 session 列表 **应**使用 `--border-light` 分隔线，而非深色。
5. 下载按钮 **应**统一用 `.header-chip` 样式。
6. 从"上传 CSV" → "生成报告" → "下载文件"的端到端流程 **应**在浅色化后仍可跑通。

### R7 · Settings / Init Guide / Activation Modal · 浅色化

**User Story**：作为用户，我希望从 header 打开的 3 个 Modal 都是浅色高级感，不会割裂。

#### Acceptance Criteria (EARS)

1. `.settings-box` **应**使用 `--bg2` 白底 + `--border` 米色边框 + `--shadow` 柔和阴影。
2. `.settings-head` / `.settings-footer` 分隔线**应**用 `--border`。
3. `.settings-field input` **应**使用浅色 `--bg3`（或 `#fff`）+ `--border` 边框。
4. Init Guide 里的 5 步指引按钮（注册 APIMart / SIF / ...）**应**保留金色 CTA 或墨色 CTA，但不能出现蓝色。
5. Activation Modal 的输入框 + 提交按钮 **应**用浅色。
6. 所有 Modal 遮罩 **应**使用 R1.7 定义的 `rgba(26,31,44,.45)` + `blur(4px)`。

---

## 边界情况与错误处理

- **用户浏览器禁用了 `backdrop-filter`**：Modal 遮罩仍使用 `rgba(26,31,44,.45)` 保底，失去毛玻璃效果但不影响可用性。
- **后端返回 `geo_audit` / `probing_strategy` 为 `null` 或缺失**：对应卡片完全隐藏，**不得**报错或显示空框。
- **`geo_audit.recommendations` 为空数组**：只显示评分部分，建议区不展示。
- **`probing_strategy.questions` 某个类型数组为空**：折叠展开时该类型不显示（不空占位）。
- **SQP 上传了只有 1 周的 CSV**：后端会跳过 WoW 相关输出，前端 **应**在结果区给一条提示"至少 2 周才能出 WoW 分析"。
- **Rufus 调研时 Chrome 端口未开**：Step 2 区域保持禁用状态，Help 指引显示；不影响 Step 3 手动模式可用。

---

## 成功标准

### 视觉标准（肉眼验证）
- 在浏览器里逐一切换 4 个 tab（素材 / Rufus & COSMO / Rufus 调研 / SQP），**无任何深色块**、**无蓝色按钮**、高亮统一金色、CTA 统一墨色。
- 打开 Settings / Init Guide / Activation 三个 Modal，风格统一。
- 滚动、hover、focus、disabled 几种交互态视觉一致。

### 功能标准（脚本回归）
- 现有 `rufus_regression.py` 能一次通过 5 个 phase。
- SQP 端到端手动测试（前端上传 CSV → 看到 4 个概览数字 → 能下载 6 个 CSV + PNG + MD）。
- 老的 ASIN 端到端（`/api/submit` → 看 Rufus & COSMO 5 子 tab）都正常，且"标题优化"里能看到新加的 GEO 6 维度卡片、"Q&A 建议"里能看到新加的 Probe Strategy 卡片。

### 代码标准（grep 验证）
- `grep_search` 搜 `index.html` **不得**命中：`#0f1117`, `#1a1d27`, `#22263a`, `#2d3348`, `#e2e8f0`, `#8892a4`, `#1677ff`, `#f59e0b`, `rgba(0,0,0,.7)`, `rgba(0,0,0,.85)`。
- 新增的 GEO 6 维度卡 + Probe Strategy 卡的渲染函数在`renderTitle()` 和 `renderQa()` 里完整实现。

---

## 开放问题（需要用户确认）

1. **GEO 6 维度的可视化形态**：雷达图（半径等于得分）还是 6 条水平进度条？
   - 雷达图更直观但实现复杂（要引 Chart.js 或 SVG）
   - 进度条简单纯 CSS 能做
   - **建议**：进度条（和现有风格一致，零依赖）
2. **Rufus Probe Strategy 的问题展示**：默认折叠还是默认展开？
   - 折叠：Q&A 子 tab 保持紧凑
   - 展开：用户一眼就看到 10 题
   - **建议**：默认折叠 + 一键展开
3. **"复制探针问题到 Rufus 调研 tab"按钮**（R4.8）：如果 Rufus 调研 tab 里已经填了别的 ASIN 的问题，要不要弹确认？
   - 弹确认更安全，不会误覆盖
   - 不弹更流畅
   - **建议**：弹确认

你直接回复 "默认都通过" 或对哪条有特别意见，我就进入 Design 阶段。
