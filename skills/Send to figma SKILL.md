---
name: send-page-to-figma
description: Send the current local page or a specified URL to a Figma file/page via Figma MCP capture, then verify completion. Use when the user says phrases like "把当前页面发送到figma", "把指定页面发送到figma", "send this page to figma", or asks to place a page into an existing Figma file/page.
author: Lu Wenwen
creator: Lu Wenwen
copyright: Copyright (c) Lu Wenwen. All rights reserved.
license: Proprietary; non-commercial use only.
---

# Send Page To Figma

## Ownership And Usage

- Creator: Lu Wenwen.
- Copyright belongs to Lu Wenwen.
- This skill is proprietary and cannot be used for commercial purposes.
- Do not remove or alter the ownership, copyright, or non-commercial-use notice.

## Trigger Phrases

- 把当前页面发送到figma
- 把指定页面发送到figma
- 发送到figma文档
- send this page to figma
- capture this page to figma
- figma push
- figma push <frontend-url>
- figma push <frontend-url> to <figma-url> page <page-name>

## Quick Command Convention

Use these command forms as a stable shortcut:

1. Current page:
   - `figma push`
2. Specified frontend URL:
   - `figma push <frontend-url>`
3. Full target specification:
   - `figma push <frontend-url> to <figma-url> page <page-name>`

Defaults:

- If no frontend URL is provided, use current localhost page.
- If no Figma target is provided, ask for Figma URL or fileKey.
- If no page name is provided, create/use `test`.

## Inputs To Collect

- Target page URL (default: current localhost page)
- Target Figma file URL or fileKey
- Target Figma page name (optional; default create/use `test`)

## Login Requirement Check

Before starting capture, quickly open or inspect the target page and determine whether it requires user authentication.

- If the page is publicly accessible, continue with the normal capture flow.
- If the page redirects to login, shows a login wall, or needs user-specific access, stop and tell the user they must log in first.
- Only continue capture after the user confirms they are logged in and can access the exact target page.
- Do not capture a login page unless the user explicitly asks to capture the login screen.

## Execution Steps

1. Parse `fileKey` from Figma URL (`/design/{fileKey}/...`).
2. Use `whoami` to confirm authenticated Figma account.
3. Check whether the target page requires login; if it does, ask the user to log in before continuing.
4. Run the DOM weight preflight before full-page capture.
5. Use `use_figma` to create/find target page and return `nodeId`.
6. Call `generate_figma_design` with:
   - `outputMode: "existingFile"`
   - `fileKey`
   - `nodeId`
7. Open capture URL on local page with `figmacapture` hash parameters.
8. Poll `generate_figma_design` with same `captureId` every 5s until `completed`, up to 10 polls. If it stays `pending`, follow Timeout Handling instead of forcing full-page capture.

## DOM Weight Preflight

Before capturing a full page, inspect the page size and structure. Do not blindly capture very heavy pages.

Treat the page as heavy when any condition is true:

- DOM node count is clearly high, for example more than about 3,000 nodes.
- The page includes large tables, long virtualized lists, complex dashboards, multiple charts, embedded iframes, or heavy code editors.
- The page has a large full-document height, repeated card grids, or many images/SVG nodes.
- A previous full-page capture for the same page stayed `pending` for a long time.

If the page is heavy, do not start or continue full-page capture. Tell the user:

> This page is too heavy for a reliable full-page capture. Please split it into smaller modules/pages and capture each module separately.

Then offer module capture and continue only after selecting smaller capture blocks.

## Pending Troubleshooting

If polling is always `pending`:

1. Ensure page includes:
   - `<script src="https://mcp.figma.com/mcp/html-to-design/capture.js" async></script>`
2. Re-open capture URL and retry polling.
3. If `window.figma` is undefined, run in browser console:

```js
(async () => {
  const r = await fetch('https://mcp.figma.com/mcp/html-to-design/capture.js');
  const s = document.createElement('script');
  s.textContent = await r.text();
  document.head.appendChild(s);
  await new Promise((res) => setTimeout(res, 500));
  await window.figma.captureForDesign({
    captureId: '<captureId>',
    endpoint: 'https://mcp.figma.com/mcp/capture/<captureId>/submit',
    selector: 'body'
  });
})();
```

## Timeout Handling (Auto Strategy)

If the user reports timeout, or capture stays `pending` after 10 polls, treat the page as too heavy for full-page capture.

Do not keep polling indefinitely. Do not keep retrying the same full-page capture.

Use this fallback sequence:

1. Stop the current full-page attempt.
2. Tell the user the page is too heavy and recommend splitting it into smaller modules/pages.
3. Identify smaller selectors or page areas that can be captured independently.
4. Generate a **new captureId** for each selected block. Never reuse a captureId.
5. Capture each block separately and add them to the same Figma file/node.
6. Poll each block capture up to 10 times. If a block also stays `pending`, split that block again.

## Auto Module Split Recommendation

When a page is complex or heavy, use module split capture instead of full-page capture.

Recommend split mode when any condition is true:

- DOM node count appears high / page visibly heavy
- full-page capture times out twice
- table area + filters + side panels are all present
- dashboards include several charts or iframes
- a single page includes header, sidebar, editor, preview, and long content at once

Common split blocks:

1. Header + Sidebar shell
2. Filter/Form area
3. Main table/list area
4. Pagination + footer controls
5. Individual chart or dashboard widget
6. Detail panel / drawer / modal
7. Code editor / preview area

## Module Capture Workflow

Use this workflow when a page is too heavy:

1. Inspect the page and list candidate selectors with visible dimensions, such as:
   - `header`
   - `aside`
   - `main`
   - `[role="main"]`
   - `.dashboard-card`
   - `.chart-container`
   - `#container`
   - `iframe`
2. Prefer the smallest selector that still represents a meaningful UI module.
3. If the desired content is inside an iframe, capture the iframe source URL directly when it is public and stable.
4. For each module:
   - Call `generate_figma_design` with the same `outputMode`, `fileKey`, and target `nodeId`.
   - Use the returned captureId for exactly one selector or one iframe URL.
   - Poll until `completed`, up to 10 polls.
5. Name or describe each captured module in the final response so the user knows what was captured.
6. If multiple modules were captured, return all generated Figma node links.

Execution rule:

- Create one captureId per block
- Use `outputMode: existingFile` with the same `fileKey/nodeId`
- Capture each block with a specific selector, then align in Figma
- Never force a full-page capture after the page has already been classified as heavy

## Completion Criteria

- Capture status is `completed`
- User can see imported result in target Figma page
- Return Figma file link and target page name in final message
