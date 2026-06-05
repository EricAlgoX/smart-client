# 📚 Code Standards & Architecture

As the Claude Autonomous UI Architect, you are bound by these strict technical standards. Deviation is not permitted.

## 1. Design Token Mapping in CSS

Never hardcode thematic colors or spacing in UI components. You must map them into root variables. 

### ✅ Correct Usage
**`app/globals.css`**
```css
@tailwind base;
@tailwind components;
@tailwind utilities;

@layer base {
  :root {
    --background: 0 0% 100%;
    --foreground: 222.2 84% 4.9%;
    --card: 0 0% 100%;
    --card-foreground: 222.2 84% 4.9%;
    --primary: 221.2 83.2% 53.3%;
    --primary-foreground: 210 40% 98%;
    --radius: 0.75rem;
    --spacing-layout: 2rem;
  }
}
```

**`tailwind.config.ts`**
```typescript
module.exports = {
  theme: {
    extend: {
      colors: {
        background: "hsl(var(--background))",
        foreground: "hsl(var(--foreground))",
        primary: {
          DEFAULT: "hsl(var(--primary))",
          foreground: "hsl(var(--primary-foreground))",
        },
      },
      borderRadius: {
        lg: "var(--radius)",
        md: "calc(var(--radius) - 2px)",
        sm: "calc(var(--radius) - 4px)",
      },
    },
  },
}
```

### ❌ Incorrect Usage
```tsx
<div className="bg-[#1e1e1e] text-[#f5f5f5] rounded-[12px] p-[24px]">
  Content
</div>
```

---

## 2. Component Composition (Blocks)

When building a section, do not put all the code in one file. Separate the data layer, the layout layer, and the visual elements.

### ✅ Correct Structure Example: Pricing Section

**`components/blocks/PricingSection.tsx`**
```tsx
import { SectionHeader } from "@/components/ui/section-header";
import { PricingCard } from "@/components/blocks/PricingCard";
import { PRICING_DATA } from "@/lib/constants/pricing";

export function PricingSection() {
  return (
    <section className="relative py-24 px-layout container mx-auto" aria-labelledby="pricing-heading">
      <SectionHeader 
        id="pricing-heading"
        title="Simple, transparent pricing" 
        subtitle="No hidden fees. No surprises."
      />
      <div className="mt-16 grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-8 items-center">
        {PRICING_DATA.map((tier) => (
          <PricingCard key={tier.id} {...tier} />
        ))}
      </div>
    </section>
  );
}
```

---

## 3. Logical Properties (RTL Support)

You must use logical properties to ensure designs work flawlessly when translated to Arabic, Hebrew, or other right-to-left languages.

### ❌ Bad (Physical Properties)
```tsx
<div className="ml-4 pl-8 border-l-2 text-left mr-auto hover:translate-x-2">
```

### ✅ Good (Logical Properties)
```tsx
<div className="ms-4 ps-8 border-s-2 text-start me-auto hover:translate-x-2 rtl:hover:-translate-x-2">
```

---

## 4. Typography & "Runts"

Text should wrap beautifully without leaving a single word on the final line ("runts").

### ✅ Correct Usage
```tsx
<h1 className="text-4xl font-extrabold tracking-tight text-balance">
  Revolutionize Your Workflow Today
</h1>

<p className="mt-4 text-muted-foreground text-pretty max-w-[60ch]">
  Experience the fastest, most reliable continuous integration pipeline 
  built specifically for modern agentic teams.
</p>
```

---

## 5. Micro-Interactions (Motion)

Buttons and cards must feel tactile. Avoid default states.

### ✅ Tactile Card Example
```tsx
<div className="group relative overflow-hidden rounded-xl border bg-background p-6 transition-all hover:shadow-xl hover:-translate-y-1 hover:border-primary/50 duration-300">
  <div className="absolute inset-0 bg-gradient-to-br from-primary/10 to-transparent opacity-0 transition-opacity group-hover:opacity-100" />
  <div className="relative z-10">
    {/* Content */}
  </div>
</div>
```
