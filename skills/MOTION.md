# 🌠 Advanced Motion & Physics Standards

As an elite UI Architect, you do not build static screens. Motion is a fundamental material of interaction design. When generating code, you must default to **physics-based motion** rather than linear, time-based tweens.

## 1. Springs over Tweens
Always prefer physics simulation (springs) over absolute duration transitions for state changes (scaling, translating).

**❌ Rejected (Linear Tweening):**
```tsx
// Stiff, unnatural, disconnected from physics
<motion.div initial={{ y: 20 }} animate={{ y: 0 }} transition={{ duration: 0.3, ease: 'easeOut' }} />
```

**✅ Accepted (Physics Spring):**
```tsx
// Fluid, lifelike, organic
<motion.div initial={{ y: 20, opacity: 0 }} animate={{ y: 0, opacity: 1 }} transition={{ type: "spring", stiffness: 300, damping: 20 }} />
```

## 2. Micro-Interactions (Tailwind)
For simple hover states where Framer Motion is overkill, use Tailwind's transition utilities with appropriate timing functions. Always combine `scale` and `shadow` for tactile response.

**✅ Elite Button Interaction:**
```tsx
<button className="active:scale-[0.98] transition-all duration-300 hover:-translate-y-1 hover:shadow-xl hover:shadow-primary/25">
  Interactive Element
</button>
```

## 3. Staggered Entrance Animations
Never load a list of items simultaneously. Apply layout waterfalls.

**✅ Setup via Framer Motion:**
```tsx
const container = {
  hidden: { opacity: 0 },
  show: {
    opacity: 1,
    transition: { staggerChildren: 0.1 }
  }
};

const item = {
  hidden: { y: 20, opacity: 0 },
  show: { y: 0, opacity: 1, transition: { type: "spring" } }
};

// Usage:
<motion.ul variants={container} initial="hidden" animate="show">
  {items.map(i => <motion.li key={i} variants={item} />)}
</motion.ul>
```

## 4. Respect Reduced Motion
Never make animations so extreme they cause motion sickness. Always respect system preferences.

**✅ Tailwind implementation:**
```tsx
<div className="hover:rotate-180 transition-transform duration-700 motion-reduce:transition-none motion-reduce:hover:rotate-0" />
```
**✅ Framer Motion implementation:** Use `useReducedMotion()` hook provided by `framer-motion` to dynamically disable heavy physics simulations when necessary.
