# Tasks · UI 浅色升级 & Tab 完整度补齐

实施顺序与依赖：每项任务的"依赖"都只指向已完成的上游任务，可按顺序独立执行；每项都有验收条款，完成后立刻验证再推进。

唯一编辑文件：`src/templates/index.html`
对应规格：`requirements.md` + `design.md`

---

## 1. CSS 硬编码色彩清理

- [ ] 1.1 扫描并替换旧深色 palette 遗留
  - 在 `<style>` 段内 grep 检查 `#0f1117 / #1a1d27 / #22263a / #2d3348 / #e2e8f0 / #8892a4 / #1677ff / #f59e0b`，全部替换为对应浅色变量
  - 扫描 `rgba(0,0,0,.7) / rgba(0,0,0,.85)`，替换为 `rgba(26,31,44,.45)` + `backdrop-filter:blur(4px)` 或 `rgba(26,31,44,.82)` + `blur(6px)`
  - 扫描 `color:#f87171`，替换为 `var(--red)`
  - _Requirements: R1.2, R1.7_
  - _Design: §2.2_

- [ ] 1.2 半透明白色背景替换
  - 将 `rgba(255,255,255,.1) / .18) / .05)` 替换为 `var(--bg3)` 或 `var(--bg4)`
  - 特别覆盖：`.btn-icon` hover 态、Settings 里的被动背景
  - _Requirements: R1.3_
  - _Design: §2.2_

- [ ] 1.3 主图 / A+ 标签换色
  - `.img-type` 主图：`background:rgba(22,119,255,.85)` → `background:var(--teal); color:#fff`
  - `.img-type.aplus,.img-type.a+` → `background:var(--accent2); color:#fff`
  - _Requirements: R2.3_
  - _Design: §2.2_

- [ ] 1.4 表格与复制按钮悬停色
  - `.data-table tr:hover td` 背景从 `rgba(22,119,255,.05)` → `var(--bg4)`
  - `.copy-btn:hover` / `.result-card .actions a:hover` 从旧蓝色系换成 `var(--accent2)` + `rgba(201,166,107,.12)`
  - _Requirements: R1.5_
  - _Design: §2.2_

- [ ] 1.5 表单焦点 ring 统一
  - 给 `input:focus` / `textarea:focus` / `select:focus` 追加统一规则：
    `border-color:var(--accent2); box-shadow:0 0 0 3px rgba(201,166,107,.15); outline:none`
  - 放在 `<style>` 底部或 form-row 样式块附近
  - _Requirements: R1.8_
  - _Design: §2.3_

- [ ] 1.6 CTA 按钮 / 滚动条收尾
  - `.btn-start:disabled` 使用 `background:var(--bg3); color:var(--muted); cursor:not-allowed`
  - `.btn-primary:hover` 已是 `background:#000`，确认生效
  - 滚动条 hover 态 `*::-webkit-scrollbar-thumb:hover{background:var(--accent2)}` 验证覆盖 sidebar / content / main-tabs-bar 三处
  - _Requirements: R1.6, R1.9_
  - _Design: §2.1_

---

## 2. 产品素材生成 tab · 仅视觉

- [ ] 2.1 素材 tab 视觉审视
  - 浏览器打开 `/`，切到「产品素材生成」tab
  - 检查上传拖拽区、参考图卡、提示词卡、结果卡、copy-btn、send-chatgpt-btn 是否有残留深色
  - 如有 inline style 深色，逐项替换为变量
  - _Requirements: R2.1, R2.2, R2.4, R2.5_
  - _Design: §10 不改业务逻辑_

---

## 3. Rufus 调研 tab · 浅色化 + 回归

- [ ] 3.1 Chrome 检测状态文字色
  - `#rufusChromeStatus` 三种状态文字色改为：`var(--green) / var(--warning) / var(--red)`
  - 确保三种态在浅色底上对比度足够
  - _Requirements: R5.2_
  - _Design: §5.1_

- [ ] 3.2 priority 标签 + 报告卡进度条
  - `#rufusQuestionsArea` 里 priority 小 label 用 4.4 定义的 priority 色
  - `#rufusReportArea` 动态生成的维度进度条：excellent=green / adequate=金 / weak=红
  - _Requirements: R5.4_
  - _Design: §5.1, §3.3_

- [ ] 3.3 Rufus 端到端回归
  - 跑 `python rufus_regression.py`，确认 5 phase 全绿
  - 浏览器里走一遍 Step 1（生成问题）→ Step 3（粘贴 mock 答案）→ 看报告卡
  - _Requirements: R5.5_
  - _Design: §5.2_

---

## 4. SQP 品牌分析 tab · 浅色化 + 回归

- [ ] 4.1 `sqpRenderResult()` 的 4 个数字块换色
  - 分析周数 → `var(--accent)`（墨色）
  - 高转化词 → `var(--green)`
  - WoW 新入列 → `var(--warning)`（由旧金色改为警告橙，R6.3）
  - WoW 跌出列 → `var(--red)`
  - _Requirements: R6.3_
  - _Design: §6.1_

- [ ] 4.2 品牌总量 / 历史 session 列表分隔线
  - 品牌总量 4 格背景统一 `var(--bg3)`
  - `#sqpSessionsList` 的分隔线 → `border-bottom:1px solid var(--border-light)`
  - 下载按钮统一 `.header-chip` 样式
  - _Requirements: R6.4, R6.5_
  - _Design: §6.1_

- [ ] 4.3 SQP 端到端手动验证
  - 浏览器上传 2 个 mock CSV（已有 `SQP_Test_Week_*` 合成数据脚本）
  - 看概览 4 个数字 + 下载 1 个 CSV + 1 个 PNG
  - _Requirements: R6.6_
  - _Design: §6.2_

---

## 5. Settings / Init Guide / Activation Modal 收尾

- [ ] 5.1 Settings Modal 扫尾
  - `.settings-field input` 在 focus 态应用 R1.8 金色 ring（由 §1.5 的全局规则自动覆盖，这里仅确认）
  - 「Step X：...」标题色 `var(--accent2)` 保持
  - 「必选」红字使用 `var(--red)`
  - _Requirements: R7.1, R7.3_
  - _Design: §7.1_

- [ ] 5.2 Activation Modal / Preview Modal 扫尾
  - Activation Modal 输入框底色确认为 `var(--bg3)`，提交按钮 `var(--accent2)` 金色
  - Preview Modal 遮罩确认 `rgba(26,31,44,.82)` + `blur(6px)`
  - Init Guide 里 5 个「注册 XXX」按钮保持 `var(--accent)` 墨色，免费试用按钮 `var(--green)`
  - _Requirements: R7.4, R7.5, R7.6_
  - _Design: §7.2, §7.3_

---

## 6. 新增：GEO 6 维度卡片（R3）

- [ ] 6.1 定义 DIM_LABELS 常量
  - 在 JS 里合适位置（`// ── Expert Tab Switch ──` 附近）添加
    `const GEO_DIM_LABELS = { scenario_coverage:'场景覆盖', ... }`
  - _Requirements: R3.3_
  - _Design: §3.3_

- [ ] 6.2 实现 `renderGeoAuditCard(ga)` 函数
  - 完整按 §3.4 伪代码实现
  - 入参空 / total_score null 时返回空串（隐藏条件，R3.6）
  - 总分等级色按 §3.3 四档映射
  - 进度条 level 色按 excellent/adequate/weak 三档
  - 建议区渲染前 3 条（不足 3 条也显示），带 🔴🟡🟢 图标 + priority + area + action + evidence
  - _Requirements: R3.1-R3.5_
  - _Design: §3.2, §3.3, §3.4_

- [ ] 6.3 挂接到 `renderTitle()`
  - 在现有 `标题 COSMO 评分` 卡之后、`标题结构检测` 卡之前插入
    `html += renderGeoAuditCard(ts.geo_audit);`
  - 确认不破坏原有渲染顺序（R3.7）
  - _Requirements: R3.1, R3.7_
  - _Design: §3.2_

- [ ] 6.4 验收：提交一个 ASIN，看「标题优化」子 tab
  - 打开 `http://127.0.0.1:5173/`，提交 `B0F7QJC249`
  - 切到「Rufus & COSMO 专家建议」→「标题优化」
  - 看到新卡片，包含：总分 + 等级 + 6 条进度条（各带 level 图标）+ 建议区
  - 后端 `/api/expert-suggestions/<job>` 返回里的 `geo_audit.total_score=78` / `overall_grade=B` 与前端显示一致
  - _Requirements: R3_（全部 AC）
  - _Design: §3, §11 验收_

---

## 7. 新增：Rufus Probe Strategy 卡片（R4）

- [ ] 7.1 实现 `renderProbeStrategyCard(probe, asin)` 函数
  - 顶部：framework 一行说明
  - priority 三色标签（primary=红系 / secondary=警告 / tertiary=teal）+ reason
  - weakness_scores 5 条进度条，score 低→红，中→金，高→绿
  - 默认折叠 questions，点击 `[▼ 展开 10 个探针问题]` 切换展示
  - 展开后按类型分组显示问题 + purpose
  - 底部按钮：`[📋 复制到 Rufus 调研 tab]`
  - 入参空 / 无 probing_strategy 时返回空串（R4.6）
  - _Requirements: R4.1-R4.7_
  - _Design: §4.2, §4.3, §4.4_

- [ ] 7.2 实现折叠展开交互
  - 用一个 `#probeQuestionsBlock` DIV 包住问题列表，默认 `display:none`
  - 按钮 onclick 切换 `display`，同时切换按钮文本 `[▼ 展开]` ↔ `[▲ 收起]`
  - _Requirements: R4.5, 开放问题 2_
  - _Design: §4.3 默认折叠_

- [ ] 7.3 实现复制到 Rufus 调研 tab 的交互
  - 点击"复制"按钮：
    - 先 `confirm('将 10 个问题复制到 Rufus 调研 tab（会覆盖当前 tab 的问题）？')`
    - 确认后：`switchMainTab('rufus')` → 把 probe.questions 扁平成 `[{q, purpose, type}]` 写入 `window.rufusQuestions` → 调用 `rufusRenderPasteForm()` → `rufusAsinInput` 填充当前 ASIN
    - 若 `probing_strategy.questions` 为空则按钮 disabled
  - _Requirements: R4.8, 开放问题 3_
  - _Design: §4.3 复制按钮行为_

- [ ] 7.4 挂接到 `renderQa()`
  - 在现有 `🤖 Rufus 智能 Q&A` 标题卡**之前**注入
    `html = renderProbeStrategyCard(qs.probing_strategy, currentAsin) + html;`
  - 确认不破坏原有 Q&A 对展示（R4.7）
  - _Requirements: R4.1, R4.7_
  - _Design: §4.2_

- [ ] 7.5 验收：看「Q&A 建议」子 tab
  - 浏览器打开，跑完一个 ASIN
  - 切到「Q&A 建议」子 tab，最上方看到 Probe Strategy 卡片
  - 看到：framework 一行、priority 三标签、5 条弱点进度条
  - 点击"展开" → 出现按类型分组的 10 个问题
  - 点击"复制到 Rufus 调研 tab" → 跳 Rufus 调研 tab，Step 3 表单已预填问题
  - _Requirements: R4_（全部 AC）
  - _Design: §4, §11 验收_

---

## 8. 终局验证

- [ ] 8.1 静态 grep 扫净度
  - `grep_search` 对 `#0f1117|#1a1d27|#22263a|#2d3348|#e2e8f0|#8892a4|#1677ff|#f59e0b` 全部零命中
  - `grep_search` 对 `rgba\(0,\s*0,\s*0,\s*\.(7|85)` 全部零命中（除图片叠层小 btn 蒙层保留 `.5` 是合理的）
  - _Requirements: 成功标准 · 代码_
  - _Design: §11 代码 grep_

- [ ] 8.2 视觉巡查
  - 逐个切换 4 个业务 tab，逐个打开 3 个 Modal
  - hover 态、focus 态、disabled 态视觉一致
  - 无残留深色块 / 蓝色按钮 / 橙色 CTA（旧 palette 的特征色）
  - _Requirements: 成功标准 · 视觉_
  - _Design: §11 视觉_

- [ ] 8.3 功能巡查
  - 跑 `rufus_regression.py` 5 phase 全绿
  - 浏览器完整跑一个 ASIN（提交→ 5 个子 tab 能展开 → 其中「标题优化」有 GEO 新卡、「Q&A 建议」有 Probe 新卡）
  - 浏览器完整跑一次 SQP 上传→看报告→下载
  - 浏览器完整跑一次 Probe 卡"复制"按钮跳转
  - _Requirements: 成功标准 · 功能_
  - _Design: §11 功能_

---

## 依赖关系

```
1 (CSS 清理) ─┬─> 2 (素材 tab)
              ├─> 3 (Rufus 调研 tab) ─┐
              ├─> 4 (SQP tab)        ├─> 8 (终局验证)
              ├─> 5 (Modals)         │
              ├─> 6 (GEO 卡片) ──────┤
              └─> 7 (Probe 卡片) ────┘
```

建议顺序：1 → 2 → 3 → 4 → 5 → 6 → 7 → 8，按章节号线性推进。

---

## 交付判定

**完成判定** = 8.1 / 8.2 / 8.3 三项全部通过。

若 8.3 某项功能在浅色化后被破坏，应优先修复该项再走 8.1、8.2；不得为了视觉牺牲功能。
