# ♿ Accessibility & Inclusivity Core

To achieve award-winning status (Awwwards/Webby), a design must be inclusive. Do not treat a11y as an afterthought; it is structurally embedded in your code output.

## 1. Focus Management
An interface must be fully navigable via keyboard without the focus ring looking "broken" or hidden.

**❌ Rejected:**
```css
/* Never remove focus rings without replacing them! */
*:focus { outline: none; }
```

**✅ Accepted (Shadcn/Tailwind default):**
```tsx
<button className="focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2">
  Navigable Button
</button>
```

## 2. Semantic HTML
Never use a `<div>` when a semantic tag is available.

- Use `<button>` for clickable actions, never `<div onClick={...}>`.
- Use `<nav>` for navigation links.
- Use `<main>` for primary page content.
- Use `<section>` with an `aria-labelledby` attribute for modular content blocks.

## 3. Screen Reader Visibility (`sr-only`)
When creating icon-only buttons, you must include a descriptive label that is visually hidden but read by screen readers.

**✅ Elite Icon Button:**
```tsx
<Button variant="ghost" size="icon">
  <Menu className="h-5 w-5" aria-hidden="true" />
  <span className="sr-only">Open navigation menu</span>
</Button>
```

## 4. Contrast Constraints
Unless specifically mapping a very subtle decorative element, ensure foreground-to-background contrast ratios exceed the WCAG AA minimum of **4.5:1**. 
- *Pro-tip:* When applying text to a variable background or image, apply a subtle gradient overlay or `backdrop-blur` behind the text to guarantee contrast.
