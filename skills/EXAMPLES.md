# 💡 Architectural & Aesthetic Examples

Use these examples to understand the difference between acceptable code output and elite-level UI output.

## Scenario 1: A "Hero" Call to Action Button

**❌ Junior Output (Rejected)**
```tsx
<button className="bg-blue-500 text-white px-4 py-2 rounded-md hover:bg-blue-600">
  Get Started
</button>
```
*Critique: It's flat, boring physical padding, no focus state, no micro-interaction, and relies on generic Tailwind colors.*

**✅ Elite Architect Output (Accepted)**
```tsx
import { Button } from "@/components/ui/button";
import { ArrowRight } from "lucide-react";

export function HeroCta() {
  return (
    <Button 
      size="lg" 
      className="group relative overflow-hidden rounded-full px-8 py-6 text-base font-semibold transition-all duration-300 hover:shadow-[0_0_40px_-10px_rgba(var(--primary),0.5)] hover:-translate-y-0.5 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary focus-visible:ring-offset-2"
    >
      <span className="relative z-10 flex items-center gap-2">
        Get Started
        <ArrowRight className="h-4 w-4 transition-transform duration-300 group-hover:translate-x-1" />
      </span>
      {/* Glossy sweep effect */}
      <div className="absolute inset-0 z-0 h-full w-full bg-gradient-to-r from-transparent via-white/20 to-transparent -translate-x-[150%] skew-x-[30deg] transition-all duration-700 ease-out group-hover:translate-x-[150%]" />
    </Button>
  );
}
```
*Why this works: Utilizes the `Button` abstraction. Adds custom bounding box shadows, active scaling, hover states on child icons (`group-hover`), and a complex glossy micro-animation without relying on expensive JS.*

---

## Scenario 2: Image Placeholders & Skeletons

**❌ Junior Output (Rejected)**
```tsx
<div className="w-full h-80 bg-gray-300 flex items-center justify-center">
  No Image
</div>
```
*Critique: "Gray box syndrome." Completely ruins the visual aesthetic and user trust of a prototype.*

**✅ Elite Architect Output (Accepted)**
```tsx
export function MediaSkeleton() {
  return (
    <div className="relative w-full overflow-hidden rounded-2xl bg-muted/30 aspect-video ring-1 ring-border/50">
      {/* Shimmer gradient */}
      <div className="absolute inset-0 -translate-x-full animate-[shimmer_2s_infinite] bg-gradient-to-r from-transparent via-muted-foreground/10 to-transparent" />
      
      {/* Optional: Subtle wireframe icon or brand mark in center */}
      <div className="absolute inset-0 flex items-center justify-center text-muted-foreground/20">
        <svg className="w-12 h-12" fill="none" viewBox="0 0 24 24" stroke="currentColor">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1} d="M4 16l4.586-4.586a2 2 0 012.828 0L16 16m-2-2l1.586-1.586a2 2 0 012.828 0L20 14m-6-6h.01M6 20h12a2 2 0 002-2V6a2 2 0 00-2-2H6a2 2 0 00-2 2v12a2 2 0 002 2z" />
        </svg>
      </div>
    </div>
  );
}
```
*Why this works: Maintains dimensions (`aspect-video`), respects the theme (`bg-muted/30`), includes an elegant shimmer animation customized globally, and uses a subtle SVG instead of jarring text.*

---

## Scenario 3: Page Layout & Grid System

**❌ Junior Output (Rejected)**
```tsx
<div className="flex flex-col m-5">
  <div className="mb-4">Card 1</div>
  <div className="mb-4">Card 2</div>
  <div className="mb-4">Card 3</div>
</div>
```
*Critique: Flex-col with margins is brittle and unresponsive to wider viewports without mass-refactoring.*

**✅ Elite Architect Output (Accepted)**
```tsx
<div className="grid grid-cols-1 gap-6 sm:grid-cols-2 lg:grid-cols-3 xl:gap-8 p-layout">
  <CardBlock />
  <CardBlock />
  <CardBlock />
</div>
```
*Why this works: Implements a scalable, responsive CSS Grid that automates spacing with `gap`, easily shifting column counts based on viewport without manually overriding `.mb-4` margins.*
