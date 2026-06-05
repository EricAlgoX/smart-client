# 🕵️ QA Validation Loop

Before Claude (you) outputs a single line of code in the final response, you MUST run this analytical checklist mentally. If any check fails, rewrite the code internally before generating the final message.

### Step 1: The Design Token Audit
- **Check:** Did I hardcode any hex colors (`#FF0000`) or magic numbers for layout spacing?
- **Action:** If yes, map them to `.css` `:root` variables or existing Tailwind theme classes (`text-primary`, `bg-muted`).

### Step 2: Form & Layout Resilience Check
- **Check:** Will this layout break if the text is 3x longer? Will it break on a 320px mobile viewport?
- **Action:** Ensure usage of `break-words`, `line-clamp-3`, and `grid-cols-1 sm:grid-cols-2 lg:grid-cols-3` instead of fixed `w-[500px]` widths.

### Step 3: The "Runt" Avoidance
- **Check:** Are paragraph tags and `<h1>` tags at risk of leaving a single word on the last line?
- **Action:** Apply `text-balance` for headings and `text-pretty` for paragraphs.

### Step 4: Visual Lifecycle & Motion
- **Check:** Does this component just sit there? Does it react to hovering, active clicking, or loading?
- **Action:** Add `transition-all`, active states (`active:scale-[0.98]`), hover gradients, and skeleton loaders if fetching data. 

### Step 5: Accessibility Verification
- **Check:** Are all icons labeled with `<span className="sr-only">`? Can users tab to every interactive element with a visible `focus-visible:ring-2`?
- **Action:** Update all raw SVGs to include `aria-hidden` and append screen-reader spans to icon buttons.

### Execution Output:
Once all 5 steps pass internally, generate the final pristine code artifact. Do not output the intermediate failure states.
