# Design · UI 浅色升级 & Tab 完整度补齐

## 1. 架构总览

本 spec 是**纯前端 / CSS 改造**，不动任何后端代码。改动全部落在一个文件里：

```
src/templates/index.html
```

整体分两层：

```
┌──────────────────────────────────────────────────┐
│  样式层（CSS）                                    │
│  :root 变量统一浅色 palette → 全站元素自动跟随    │
│  硬编码色残留 → 清除或替换为变量                   │
└──────────────────────────────────────────────────┘
                       ↓
┌──────────────────────────────────────────────────┐
│  渲染层（JS）                                     │
│  renderTitle()  → 扩展：读 ctx.geo_audit 加一张卡  │
│  renderQa()     → 扩展：读 probing_strategy 加一张卡│
│  其它 render 函数 → 不改                           │
└──────────────────────────────────────────────────┘
```

两层都不碰 Python 后端 —— `expert_suggestions.py` 已经在 return 里带了 `geo_audit` 和 `probing_strategy`，等前端读取。

---

## 2. CSS 变量体系

### 2.1 根变量（已在 R1 确认）

```css
:root {
  /* 背景 */
  --bg:         #f8f5f0;  /* 页面底色 · 象牙奶白 */
  --bg2:        #ffffff;  /* 卡片 / Header / Sidebar */
  --bg3:        #f1ece2;  /* 次层 · 输入框底 / 被动 */
  --bg4:        #faf6ef;  /* hover / stripe */

  /* 文字 */
  --text:       #1a1f2c;  /* 主字 · 墨 */
  --text-light: #41485b;  /* 次字 */
  --muted:      #8a8070;  /* 辅文 · 暖灰 */

  /* 边框 */
  --border:       #e5ddd0;  /* 主边框 */
  --border-light: #efe9dd;  /* 浅边框 */

  /* 强调色 */
  --accent:   #1a1f2c;  /* 墨色（CTA）*/
  --accent2:  #c9a66b;  /* 金（高亮 / 焦点）*/
  --teal:     #0f766e;  /* 深青（次强调 / 主图）*/

  /* 语义色 */
  --green:    #15803d;  /* 成功 */
  --red:      #b91c1c;  /* 错误 */
  --warning:  #c2704b;  /* 警告 / 橙棕 */

  /* 阴影 */
  --shadow:    0 2px 12px rgba(26,31,44,.06);
  --shadow-lg: 0 8px 32px rgba(26,31,44,.10);
  --radius:    8px;
}
```

### 2.2 需要替换的硬编码清单

用 `grep_search` 检出的需清理项：

| 原值 | 替换为 | 出现位置 |
|---|---|---|
| `rgba(255,255,255,.1)` / `.18)` / `.05)` | `var(--bg3)` 或 `var(--bg4)` | .btn-icon hover、某些半透明背景 |
| `rgba(0,0,0,.7)` | `rgba(26,31,44,.45)` + blur | 旧 Modal 遮罩（已部分改） |
| `rgba(0,0,0,.85)` | `rgba(26,31,44,.82)` + blur | 图片预览 Modal |
| `#f87171` | `var(--red)` | clearAllCache 按钮文字色 |
| `color:#fff` 在**浅色背景上**的元素 | `var(--text)` | 需逐处审视 |
| `.img-type{background:rgba(22,119,255,.85)}` | `background:var(--teal); color:#fff` | 主图标签（用深青替代旧蓝）|
| `.img-type.aplus{background:rgba(245,158,11,.85)}` | `background:var(--accent2); color:#fff` | A+标签用金 |
| `.data-table tr:hover td{background:rgba(22,119,255,.05)}` | `background:var(--bg4)` | 表格行 hover |
| `.copy-btn:hover{border-color:var(--accent); color:var(--accent); background:rgba(22,119,255,.1)}` | 改用 `var(--accent2)` + `rgba(201,166,107,.12)` | 复制按钮悬停 |
| `.result-card .actions a:hover{background:rgba(22,119,255,.1);color:var(--accent)}` | 同上 | 结果卡动作按钮 |

### 2.3 焦点态 (focus ring)

```css
input:focus, textarea:focus, select:focus {
  border-color: var(--accent2);
  box-shadow: 0 0 0 3px rgba(201,166,107,.15);
  outline: none;
}
```

---

## 3. R3 · GEO 6 维度卡片设计

### 3.1 数据契约（后端已就绪）

`build_cosmo_title(context)` 返回结构：

```json
{
  "cosmo_analysis": { ... },
  "geo_audit": {
    "total_score": 78,
    "max_score": 100,
    "overall_grade": "B — 大体匹配...",
    "dimensions": {
      "scenario_coverage":      { "score": 8,  "max": 20, "level": "weak",     "gap": ["kitchen", "small", "kids"] },
      "audience_match":         { "score": 12, "max": 15, "level": "adequate" },
      "decision_drivers":       { "score": 16, "max": 20, "level": "adequate", "gap": ["price_value"] },
      "positioning":            { "score": 15, "max": 15, "level": "excellent", "note": "类目竞争..." },
      "user_language":          { "score": 15, "max": 15, "level": "excellent" },
      "ai_readable_structure":  { "score": 12, "max": 15, "level": "adequate" }
    },
    "recommendations": [
      { "priority": "high", "area": "场景覆盖", "action": "...", "evidence": "..." },
      ...
    ],
    "audit_method": "geo-listing-auditor v1 · ..."
  },
  ...
}
```

### 3.2 卡片布局

**位置**：`renderTitle()` 渲染的容器里，在 `标题 COSMO 评分` 卡之后、`标题结构检测` 卡之前。

**结构**：

```
┌─ expert-card（新增）─────────────────────────┐
│ 📐 GEO 6 维度审计                            │
│                                             │
│    78  / 100                                │
│   B — 大体匹配...                            │
│                                             │
│  场景覆盖   ✗ weak        [==========      ] 8/20   │
│             缺：kitchen、small、kids                │
│  人群匹配   ~ adequate   [==============  ] 12/15 │
│  决策因素   ~ adequate   [===============]16/20   │
│             缺：price_value                        │
│  定位差异化  ✓ excellent  [===============]15/15   │
│             类目竞争不算拥挤...                    │
│  用户语言   ✓ excellent  [===============]15/15   │
│  AI 可读   ~ adequate   [============   ]12/15   │
│                                             │
│ ──────────────────────────────                │
│ 🎯 优化建议（按优先级）                       │
│ 🔴 [high] 场景覆盖                           │
│    把 Rufus 高频场景「kitchen」加进...        │
│    证据：Rufus scene_heatmap: [...]          │
│ 🟡 [medium] ...                             │
└─────────────────────────────────────────────┘
```

### 3.3 实现要点

**进度条颜色映射**（按 level）：
- `excellent` → `var(--green)`
- `adequate` → `var(--accent2)`（金色）
- `weak` → `var(--red)`

**总分等级色**：
- `total_score >= 80` → `--green`
- `total_score >= 65` → `--accent2`
- `total_score >= 50` → `--warning`
- 否则 → `--red`

**维度名中文映射**（JS 端）：

```js
const DIM_LABELS = {
  scenario_coverage:      '场景覆盖',
  audience_match:         '人群匹配',
  decision_drivers:       '决策因素',
  positioning:            '定位差异化',
  user_language:          '用户语言',
  ai_readable_structure:  'AI 可读'
};
```

**隐藏条件**：`if (!geo_audit || !geo_audit.total_score) { skip card }`（R3.6）。

### 3.4 伪代码

```js
function renderGeoAuditCard(ga) {
  if (!ga || ga.total_score == null) return '';
  const scoreColor =
    ga.total_score >= 80 ? 'var(--green)' :
    ga.total_score >= 65 ? 'var(--accent2)' :
    ga.total_score >= 50 ? 'var(--warning)' : 'var(--red)';

  let html = `<div class="expert-card">
    <div class="expert-label">📐 GEO 6 维度审计</div>
    <div style="text-align:center;margin:8px 0;">
      <span style="font-size:2.4rem;font-weight:800;color:${scoreColor};">
        ${ga.total_score}<span style="font-size:.8rem;">/100</span>
      </span>
      <div style="font-size:.7rem;color:var(--muted);margin-top:4px;">
        ${escHtml(ga.overall_grade||'')}
      </div>
    </div>`;

  for (const [key, label] of Object.entries(DIM_LABELS)) {
    const d = (ga.dimensions||{})[key] || {};
    const pct = d.max > 0 ? Math.round(d.score / d.max * 100) : 0;
    const lv  = d.level || 'adequate';
    const lvIcon = { excellent:'✓', adequate:'~', weak:'✗' }[lv] || '?';
    const barColor =
      lv === 'excellent' ? 'var(--green)' :
      lv === 'weak'      ? 'var(--red)'   : 'var(--accent2)';

    html += `<div style="margin:10px 0;">
      <div style="display:flex;justify-content:space-between;font-size:.7rem;margin-bottom:3px;">
        <span><span style="color:${barColor};">${lvIcon}</span> ${label}</span>
        <span style="color:${barColor};font-weight:600;">${d.score||0}/${d.max||'?'}</span>
      </div>
      <div class="score-bar">
        <div class="score-bar-fill" style="width:${pct}%;background:${barColor};"></div>
      </div>`;

    if (d.gap && d.gap.length) {
      html += `<div style="font-size:.62rem;color:var(--muted);margin-top:3px;">
        缺：${escHtml(d.gap.slice(0,3).join('、'))}
      </div>`;
    } else if (d.note) {
      html += `<div style="font-size:.62rem;color:var(--muted);margin-top:3px;">
        ${escHtml(d.note.substring(0,80))}
      </div>`;
    }
    html += '</div>';
  }

  // 建议区（前 3 条）
  const recs = ga.recommendations || [];
  if (recs.length) {
    html += `<div style="margin-top:14px;padding-top:10px;border-top:1px solid var(--border-light);">
      <div style="font-size:.72rem;font-weight:700;color:var(--text);margin-bottom:6px;">
        🎯 优化建议（按优先级）
      </div>`;
    for (const r of recs.slice(0, 3)) {
      const icon = { high:'🔴', medium:'🟡', low:'🟢' }[r.priority] || '⚪';
      html += `<div style="padding:6px 8px;background:var(--bg3);border-radius:6px;margin-bottom:4px;">
        <div style="font-size:.68rem;"><span>${icon}</span>
          <strong>[${r.priority||'?'}] ${escHtml(r.area||'')}</strong></div>
        <div style="font-size:.66rem;color:var(--text);margin-top:2px;">
          ${escHtml(r.action||'')}</div>
        ${r.evidence ?
          `<div style="font-size:.58rem;color:var(--muted);margin-top:2px;">
             证据：${escHtml(r.evidence.substring(0,100))}</div>` : ''}
      </div>`;
    }
    html += '</div>';
  }

  html += '</div>';
  return html;
}
```

将 `html += renderGeoAuditCard(ts.geo_audit)` 注入到现有 `renderTitle()` 的合适位置。

---

## 4. R4 · Rufus Probe Strategy 卡片设计

### 4.1 数据契约（后端已就绪）

`build_rufus_qa(context)` 返回结构：

```json
{
  "qa_pairs": [ ... ],   // 原有
  "total": 8,            // 原有
  "probing_strategy": {
    "framework": "rufus-listing-probe · 5 类型自适应分配（最多 10 题）",
    "priority": {
      "primary":   "comparison_substitution",
      "secondary": "user_feedback_friction",
      "tertiary":  "shopper_language",
      "reason":    "对比与替代（弱点：...）/ 用户反馈 /..."
    },
    "weakness_scores": {
      "scenario_persona":        { "score": 8,  "reason": "...", "label": "场景与人群" },
      "decision_drivers":        { "score": 5,  "reason": "...", "label": "决策因素" },
      "comparison_substitution": { "score": 0,  "reason": "...", "label": "对比与替代" },
      "user_feedback_friction":  { "score": 4,  "reason": "...", "label": "用户反馈 / 摩擦" },
      "shopper_language":        { "score": 4,  "reason": "...", "label": "买家自然语言" }
    },
    "allocation": {
      "comparison_substitution": 3,
      "user_feedback_friction":  3,
      "shopper_language":        2,
      "decision_drivers":        2
    },
    "questions": {
      "comparison_substitution": [
        { "q": "For a outdoor user, how does this compare with ...",
          "purpose": "position the product relative to its most-queried alternative" },
        ...
      ],
      "user_feedback_friction": [ ... ],
      ...
    },
    "total": 10
  }
}
```

### 4.2 卡片布局

**位置**：`renderQa()` 渲染的容器**最开头**，在 `🤖 Rufus 智能 Q&A` 标题卡之前。

**结构**：

```
┌─ expert-card（新增）─────────────────────────┐
│ 🎯 Rufus 探针策略                   [▼ 展开] │
│ rufus-listing-probe · 5 类型自适应分配（最多 10 题）│
│                                             │
│  优先攻击维度                                │
│  [primary] 对比与替代（弱点：...）             │
│  [secondary] 用户反馈 / 摩擦（弱点：...）      │
│  [tertiary] 买家自然语言（弱点：...）          │
│                                             │
│  5 类维度弱点（分数越低越弱）                   │
│  场景与人群      [========        ] 8/10      │
│  决策因素        [=====           ] 5/10      │
│  对比与替代      [                ] 0/10      │
│  用户反馈 / 摩擦 [====            ] 4/10      │
│  买家自然语言    [====            ] 4/10      │
│                                             │
│  [▼ 展开 10 个探针问题]                       │
│                                             │
│  [📋 复制到 Rufus 调研 tab]                   │
└─────────────────────────────────────────────┘
```

展开后：

```
  comparison_substitution (3)
    Q1: For a outdoor user, how does this compare with window squeegee?
        🎯 position the product relative to its most-queried alternative
    Q2: What type of shopper should choose ...
    Q3: When does buying this make more sense than ...

  user_feedback_friction (3)
    Q4: ...
  ...
```

### 4.3 实现要点

**弱点进度条颜色**：
- `score <= 3` → `var(--red)`（弱）
- `score <= 6` → `var(--accent2)`（中）
- `score > 6`  → `var(--green)`（强）

**默认折叠**（R4.5 + 开放问题 2）：
- 卡片展示 priority + weakness_scores，**默认不展开 questions**
- 点击 `[▼ 展开 10 个探针问题]` 切换显示

**复制按钮行为**（R4.8 + 开放问题 3）：
- 点击先 `confirm()` 询问"将 10 个问题复制到 Rufus 调研 tab（当前 Rufus tab 已有内容会被覆盖）"
- 确认后：
  - 切换主 tab 到 `rufus`
  - 把问题数组写入 `window.rufusQuestions`
  - 调用 `rufusRenderPasteForm()` 重新渲染手动粘贴表单
  - `rufusAsinInput` 自动填当前 COSMO 分析的 ASIN

**隐藏条件**：`if (!qs.probing_strategy) { skip card }`（R4.6）。

### 4.4 priority 标签色

| priority | 背景 | 文字 |
|---|---|---|
| primary | `rgba(185,28,28,.1)` | `var(--red)` |
| secondary | `rgba(194,112,75,.1)` | `var(--warning)` |
| tertiary | `rgba(15,118,110,.1)` | `var(--teal)` |

---

## 5. R5 · Rufus 调研 tab 浅色化

### 5.1 要改的具体元素

定位到 `#mainTabRufus` 容器内：

- 所有 inline `style="background:var(--bg3)"` 的 textarea / input 保持不变（已对 `--bg3`）
- `#rufusChromeStatus` 内三种状态的文字色：
  - `✓ 可接管` → `color:var(--green)`
  - `⚠ 未开启调试端口` → `color:var(--warning)`
  - `✗ 检测失败` → `color:var(--red)`
- `#rufusQuestionsArea` 里的 priority 小 label → 用 4.4 的标签色
- 报告卡（`#rufusReportArea` 动态生成）的分数条颜色 → 用 3.3 的映射

### 5.2 回归策略

- 跑 `rufus_regression.py` 5 个 phase
- 浏览器手动按 Step 1 → Step 3 的流程走一遍（mock 答案）

### 5.3 不改之处

- Step 2 自动模式的逻辑一概不动（CDP / Stealth / CAPTCHA 检测等）
- `rufusCheckChrome()` / `rufusGenerateQuestions()` / `rufusPasteSubmit()` 的 JS 不改

---

## 6. R6 · SQP tab 浅色化

### 6.1 要改的具体元素

`#mainTabSqp` 容器内：

- `#sqpDropZone` hover / dragover 的颜色已经用 `var(--accent2)`
- 概览卡的 4 个数字块：
  - 分析周数 → `color:var(--accent)`（墨色）
  - 高转化词 → `color:var(--green)`
  - WoW 新入列 → `color:var(--warning)`（由金改警告橙）
  - WoW 跌出列 → `color:var(--red)`
- 品牌总量 4 格的背景 → `var(--bg3)`
- 历史 session 列表的分隔线 → `border-bottom:1px solid var(--border-light)`

### 6.2 回归策略

- 浏览器手动：上传 2 个 mock CSV → 看 4 个数字 → 点一个下载链接
- `sqp_report.py` 本身不改

---

## 7. R7 · Modals 浅色化

### 7.1 Settings Modal

已经基本浅色化，只剩几处细节：
- `.settings-field input` focus ring → 金色
- 「Step X：...」的 `var(--accent2)` 标题色保持
- 「必选」红字保持 `var(--red)`
- Init Guide 里的 5 个"注册"按钮已经是 `var(--accent)` 墨色，`var(--green)` 免费试用按钮保持

### 7.2 Activation Modal

- 输入框 background 从 `var(--bg3)` 保持
- 提交按钮 `var(--accent2)` 金色保持
- 状态文字红 / 金 / 绿三色已定

### 7.3 Preview Modal（图片预览）

- 已改为 `rgba(26,31,44,.82)` + `blur(6px)` 保持

---

## 8. 改动范围与文件清单

**唯一要改的文件**：

```
src/templates/index.html   (单文件改动)
```

**分块编辑**：

| 段落 | 行范围估计 | 改动类型 |
|---|---|---|
| `<style>` 顶部 `:root` | ~11-32 | 变量已定义，审视一遍 |
| `<style>` 中部 | ~50-340 | 扫描硬编码色、批量替换 |
| `<style>` 新增 | 新增焦点 ring 规则 | 追加到底部 |
| `renderTitle()` 函数 | ~1325-1380 | 注入 `renderGeoAuditCard()` 调用 |
| `renderQa()` 函数 | ~1405-1415 | 注入 `renderProbeStrategyCard()` 调用 |
| 新增两个 render 函数 | 放在 render 系列后面 | 新增 |
| Rufus 调研 tab 的 inline style | tab 内部 | 小范围替换 |
| SQP tab 的 render 函数 `sqpRenderResult()` | 已有函数 | 小范围调色 |

**不动的文件**：

- `src/app.py`
- `src/expert_suggestions.py`
- `src/tools/*`
- `src/agent/*`（按你要求暂时保留）
- `tools_user/*`

---

## 9. 实施顺序

建议按这个顺序做，每步完成后立刻跑一次冒烟测试（浏览器刷新 + 请求首页看 HTTP 200）：

1. **CSS 批量清理**（R1）—— 把硬编码深色替换完
2. **焦点态 / hover 态 / 按钮样式一致化**（R1.6 / R1.8 / R1.9）
3. **产品素材 tab 皮肤验证**（R2）—— 仅视觉 review，无代码改动
4. **Rufus 调研 tab 小修**（R5）—— inline style 调色
5. **SQP tab 小修**（R6）—— `sqpRenderResult()` 调色
6. **Modals 小修**（R7）
7. **新增 `renderGeoAuditCard()` + 挂到 `renderTitle()`**（R3）
8. **新增 `renderProbeStrategyCard()` + 挂到 `renderQa()`**（R4）
9. **端到端回归**：`rufus_regression.py` + 手动跑 ASIN 看 5 子 tab

---

## 10. 风险与回退

### 主要风险

1. **硬编码色替换漏网**：某个 inline style 有深色值没清
   - **缓解**：最后用 `grep_search` 扫 `#0f1117|#1a1d27|#22263a|#2d3348|#1677ff|#f59e0b` 确认零命中
2. **新增两张卡片破坏了 `renderTitle/Qa` 的现有逻辑**
   - **缓解**：用字符串拼接 + 插入到明确位置；若后端返回 null，卡片隐藏
3. **SQP tab 里的趋势图 PNG 是 matplotlib 生成的**，PNG 本身是彩色，和浅色 UI 颜色不一致
   - **缓解**：本次不改 matplotlib 色板（太细枝）；若看起来突兀，后续可以单独优化

### 回退

单文件改动，回退方案：

```
git diff src/templates/index.html      # 看改了什么
git checkout src/templates/index.html  # 整体回退
```

或改完先复制 `index.html.bak` 备份。

---

## 11. 设计验收清单

实施完成后，按以下顺序验收（对应 Requirements 里的成功标准）：

### 视觉
- [ ] 刷新 `http://127.0.0.1:5173/`，header / 4 个 tab / 3 个 Modal 都是浅色
- [ ] hover 态、focus 态、disabled 态视觉一致
- [ ] 没有蓝色 / 橙色的 Ant Design 感残留

### 代码（grep）
- [ ] `grep_search` 对 `#0f1117`、`#1a1d27`、`#22263a`、`#2d3348`、`#e2e8f0`、`#8892a4`、`#1677ff`、`#f59e0b` **全部零命中**
- [ ] `grep_search` 对 `rgba(0,0,0,.7)`、`rgba(0,0,0,.85)` **全部零命中**

### 功能（端到端）
- [ ] 跑 `python rufus_regression.py` 5 phase 全绿
- [ ] 浏览器上传一对 SQP CSV → 能看到 4 个概览数字 → 能下载至少 1 个 CSV
- [ ] 提交一个 ASIN → Rufus & COSMO 专家建议 tab 的「标题优化」子 tab 里看到**新增的 GEO 6 维度卡**，且数据来源是后端 `geo_audit` 字段
- [ ] 「Q&A 建议」子 tab 里看到**新增的 Probe Strategy 卡**，点击展开能看到 10 个问题
- [ ] Probe 卡里点"复制到 Rufus 调研"，确认后跳到 Rufus 调研 tab，Step 3 表单已预填问题

满足以上 3 类验收即视为交付完成。
