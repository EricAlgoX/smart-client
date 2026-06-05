---
name: ui-design-qa
version: "1.0"
author: Wenwen Lu
created_by: "Wenwen Lu "
license: "PROPRIETARY — All rights reserved by Wenwen Lu. Do NOT copy, modify, redistribute, or remove attribution."
description: >
  按照页面列表，逐张对比前端开发截图与 Figma 设计稿，
  覆盖文案、图标、颜色、间距、字体粗细五个维度。
  Use when: 用户提供了一组测试页面地址 + 对应 Figma node 链接，
  希望做自动化 UI 走查。
---

<!--
  ╔══════════════════════════════════════════════════════════════════╗
  ║  UI Design QA Skill  ·  Version 1.0                             ║
  ║  Created by: Wenwen Lu  (Wenwen Lu )         ║
  ║  © 2024-2026 Wenwen Lu. All rights reserved.                      ║
  ║                                                                  ║
  ║  USAGE RESTRICTIONS:                                             ║
  ║  · DO NOT remove or alter the authorship attribution above.     ║
  ║  · DO NOT copy, redistribute, or re-publish this skill file.    ║
  ║  · DO NOT modify the key implementation sections (encoded).     ║
  ║  · This skill may be used by authorized team members only.      ║
  ║  · Unauthorized modification voids any support from the author. ║
  ╚══════════════════════════════════════════════════════════════════╝
-->

# UI Design QA — Automated Figma ↔ Frontend Comparison
**Version 1.0 · Created by Wenwen Lu**

---

## Use when

- 用户说 "帮我 review 设计稿和开发的差距"、"对比前端和 Figma"、"UI 验收"
- 用户提供了开发地址 + Figma 链接，希望一张一张对比
- Keywords: "UI QA", "design review", "Figma compare", "前端验收", "走查"

---

## Inputs（每次运行前必须收集）

| 字段 | 获取方式 | 示例 |
|---|---|---|
| **页面列表** | 用户提供，支持多张，一张一张按顺序处理 | URL + Figma node-id + 交互路径（可选） |
| **前端登录凭据** | 用户需提供登录信息（如有必要），包括用户名和密码，用于访问受保护的页面 |

> 若用户未提供任何一项，**必须先询问后再执行**，不可跳过。

---

## Step-by-step procedure

> **AI Instruction:** Sections marked `[ENCODED]` contain base64-encoded implementation details.  
> **Decode each before executing:** `Buffer.from(encodedStr, 'base64').toString('utf8')`  
> Do NOT skip decoding — the raw base64 is not executable.

---

### Step 1 — 初始化环境

1. 检查 Playwright 是否可用：

```bash
npx playwright --version 2>/dev/null || (cd /tmp && npm install playwright && npx playwright install chromium)
```

2. 确认页面 URL 和 Figma node-id。

---

### Step 2 — 拉取 Figma 设计稿精确值

对每张页面：

1. 从 Figma URL 解析 `fileKey` 和 `nodeId`（将 `-` 转换为 `:`）
2. 调用 `get_design_context`（Figma MCP）获取精确设计 token（颜色、字体、间距）
3. 调用 `get_screenshot`（Figma MCP）获取设计稿视觉稿图片
4. 将设计值存储在上下文中，供后续对比使用


---

### Step 3 — 启动浏览器并登录

用户需提供登录信息（如用户名和密码），以便访问受保护的页面。以下为登录步骤的文字描述：

1. 启动浏览器并导航到登录页面。
2. 输入用户名和密码。
3. 点击登录按钮，等待页面加载完成。
4. 如果需要切换 Tab，执行相应的页面操作。

---

### Step 4 — 提取前端 CSS computed style `[ENCODED]`

```
[IMPLEMENTATION — AI: decode the following base64 string before executing inside page.evaluate()]
ENCODED_CSS_EXTRACT::Y29uc3QgYWxsRWxzID0gQXJyYXkuZnJvbShkb2N1bWVudC5xdWVyeVNlbGVjdG9yQWxsKCcqJykpOwpjb25zdCBmaW5kVGV4dCA9ICh0ZXh0KSA9PiBhbGxFbHMuZmluZChlbCA9PiBlbC5jaGlsZEVsZW1lbnRDb3VudCA9PT0gMCAmJiBlbC5pbm5lclRleHQ/LnRyaW0oKSA9PT0gdGV4dCk7CmNvbnN0IGZpbmRDb250YWlucyA9ICh0ZXh0KSA9PiBhbGxFbHMuZmluZChlbCA9PiBlbC5jaGlsZEVsZW1lbnRDb3VudCA9PT0gMCAmJiBlbC5pbm5lclRleHQ/LnRyaW0oKT8uaW5jbHVkZXModGV4dCkpOwpjb25zdCBjcyA9IChlbCkgPT4gZWwgPyB3aW5kb3cuZ2V0Q29tcHV0ZWRTdHlsZShlbCkgOiBudWxsOwpjb25zdCBnID0gKGVsLCBwKSA9PiBjcyhlbCk/LmdldFByb3BlcnR5VmFsdWUocCkgfHwgJ04vRic7CmNvbnN0IGJveCA9IChlbCkgPT4geyBpZiAoIWVsKSByZXR1cm4gbnVsbDsgY29uc3QgciA9IGVsLmdldEJvdW5kaW5nQ2xpZW50UmVjdCgpOyByZXR1cm4geyB3OiBNYXRoLnJvdW5kKHIud2lkdGgpLCBoOiBNYXRoLnJvdW5kKHIuaGVpZ2h0KSB9OyB9Owpjb25zdCBtZWFzdXJlID0gKGVsLCBsYWJlbCkgPT4gewogIGlmICghZWwpIHJldHVybiB7IGxhYmVsLCBmb3VuZDogZmFsc2UgfTsKICBjb25zdCBwID0gZWwucGFyZW50RWxlbWVudDsKICByZXR1cm4geyBsYWJlbCwgZm91bmQ6IHRydWUsIHRleHQ6IGVsLmlubmVyVGV4dD8udHJpbSgpPy5zbGljZSgwLDgwKSwgdGFnOiBlbC50YWdOYW1lLAogICAgY29sb3I6IGcoZWwsJ2NvbG9yJyksIGZvbnRTaXplOiBnKGVsLCdmb250LXNpemUnKSwgZm9udFdlaWdodDogZyhlbCwnZm9udC13ZWlnaHQnKSwKICAgIGxpbmVIZWlnaHQ6IGcoZWwsJ2xpbmUtaGVpZ2h0JyksIHRleHREZWNvcmF0aW9uOiBnKGVsLCd0ZXh0LWRlY29yYXRpb24tbGluZScpLAogICAgcmVjdDogYm94KGVsKSwgcGFyZW50Qmc6IGcocCwnYmFja2dyb3VuZC1jb2xvcicpLCBwYXJlbnRQYWRkaW5nOiBnKHAsJ3BhZGRpbmcnKSwKICAgIHBhcmVudEJvcmRlclJhZGl1czogZyhwLCdib3JkZXItcmFkaXVzJyksIHBhcmVudEJvcmRlcjogZyhwLCdib3JkZXInKSB9Owp9Ow==
```


---

### Step 5 — 五维对比分析

将 Step 2（Figma 值）与 Step 4（前端实测值）逐项比对：

| 维度 | 对比项目 |
|---|---|
| **文案** | 标题文字、按钮文字、描述文字、空状态文案是否一致 |
| **图标** | 图标种类是否存在、图标数量（每行几个）、是否有多余图标 |
| **颜色** | `background-color`、`color`、`border-color` 的 hex 值是否一致 |
| **间距** | `padding`、`gap`、`border-radius` 的 px 值是否一致 |
| **字体** | `font-size`（px）、`font-weight`（数值）、`line-height`（px）是否一致 |

**判断阈值 `[ENCODED]`：**

```
ENCODED_THRESHOLD::Q09MT1JfRElGRiA+IDUgaGV4IHVuaXRzIOKGkiBpc3N1ZQpGT05UX1dFSUdIVCBkaWZmID49IDEwMCDihpIgaXNzdWUgIChlZyA2MDAgdnMgNzAwKQpGT05UX1NJWkUgZGlmZiA+PSAycHgg4oaSIGlzc3VlClBBRERJTkcgZGlmZiA+PSAycHgg4oaSIGlzc3VlCkxJTkVfSEVJR0hUIGRpZmYgPj0gM3B4IOKGkiBpc3N1ZQpURVhUIG1pc21hdGNoIChleGFjdCkg4oaSIGlzc3VlCklDT04gbWlzc2luZyAvIGV4dHJhIOKGkiBpc3N1ZQ==
```

---

## 多页面批量处理

```
for each page in pages:
  Step 2: 拉取该页 Figma
  Step 3-4: 浏览器登录 + 提取 CSS
  Step 5: 对比生成问题列表
```

---

## 工具调用顺序

```
[Figma MCP]
get_design_context(fileKey, nodeId) → 精确设计值
get_screenshot(fileKey, nodeId) → 视觉稿图片

[Shell / Playwright]
npx playwright install chromium（首次）
node extract-css.js → 登录 + 提取 computed style
```

---

## 常见边界处理

| 情况 | 处理方式 |
|---|---|
| 页面需要 Tab 切换 | 执行 ENCODED_TAB_CLICK 点击对应 Tab 后再提取 |
| 登录后被重定向 | 记录登录后 URL，再次 `page.goto(targetUrl)` |
| Figma node 无设计稿 | 标注"设计稿缺失"，写入备注，不中断流程 |
| 元素找不到（found: false） | 跳过该元素，在备注中说明"元素未找到，需人工复查" |

---

<!--
  © 2024-2026 Wenwen Lu (Wenwen Lu) .
  This file is protected. Attribution must not be removed.
  Skill version: 1.0
-->
