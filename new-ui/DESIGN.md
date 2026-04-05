# Design System Document: The Editorial Authority

## 1. Overview & Creative North Star

### Creative North Star: "The Digital Curator"
This design system moves beyond the utility of a standard project management tool and enters the realm of a high-end editorial experience. Inspired by the precision of elite legal firms and the minimalist clarity of Harvey.ai, the system is designed to convey **Quiet Authority**. 

We reject the "boxed-in" look of traditional SaaS. Instead, we embrace a "Digital Curator" aesthetic: a sophisticated, airy, and intentional workspace that treats legal data with the reverence of a gallery. The system breaks the template through:
*   **Intentional Asymmetry:** Strategic use of whitespace to guide the eye, rather than filling every pixel.
*   **Tonal Depth:** Replacing harsh lines with shifts in surface temperature.
*   **High-Contrast Typography:** Marrying the technical precision of *Inter* with the authoritative, display-ready impact of *Public Sans*.

---

## 2. Colors

The palette is anchored in deep authority and warmth. We utilize a "Paper and Ink" philosophy where the background isn't just white, but a curated linen-tinted surface (`#fcf9f7`) that reduces eye strain and feels premium.

### Primary Roles
*   **Authority (Primary/Primary Container):** Deep navy (`#081942`) and black (`#000000`). Used for navigation and core information.
*   **Legal Precision (Secondary):** A sophisticated 'Legal Blue' (`#3e608e`) used for interactive elements and timeline milestones.
*   **The Warmth Accent (Tertiary):** A subtle gold/mustard (`#fabc4b`) derived from classic legal pad aesthetics, used sparingly for critical alerts or highlights.

### The "No-Line" Rule
**Explicit Instruction:** Designers are prohibited from using 1px solid borders for sectioning or layout containment. 
*   **Boundaries** must be defined by background color shifts. For example, a `surface-container-low` sidebar sitting against a `surface` main content area.
*   **Nesting:** Depth is created by stacking. Place a `surface-container-lowest` card on top of a `surface-container` background to create a soft, natural lift.

### Signature Textures
*   **The Glass Rule:** For floating modals or search bars, use Glassmorphism: `surface` color at 80% opacity with a `20px` backdrop-blur. This keeps the legal context visible behind the action.
*   **Tactile Gradients:** Main CTAs should use a subtle linear gradient from `primary` to `primary_container` (Top-to-Bottom) to add a "pressed ink" feel.

---

## 3. Typography

The typography scale is designed to feel like a modern legal brief: readable, structured, and unmistakably professional.

*   **Display & Headlines (Public Sans):** Used for "Projects" titles and high-level dashboard metrics. It provides a geometric, architectural feel that commands attention.
*   **Titles & Body (Inter):** Used for all functional data. *Inter* provides exceptional legibility in dense data tables and long-form legal text.
*   **Functional Hierarchy:**
    *   **Headline-LG (2rem):** Reserved for page headers only.
    *   **Title-MD (1.125rem):** Used for Project Card titles and section headers.
    *   **Label-MD (0.75rem):** Used for metadata, timeline dates, and secondary captions.

---

## 4. Elevation & Depth

We achieve hierarchy through **Tonal Layering** rather than structural scaffolding.

*   **The Layering Principle:** Use the `surface-container` tiers (Lowest to Highest) to define importance.
    *   `surface-container-lowest`: Active cards, input fields.
    *   `surface`: Global background.
    *   `surface-dim`: Deep background for sidebars or inactive states.
*   **Ambient Shadows:** For "floating" components like the Project Timeline or a Search Popover, use extra-diffused shadows:
    *   *Blur:* 32px | *Opacity:* 6% | *Color:* Derived from `on-surface` (not pure black).
*   **The Ghost Border:** If a boundary is required for accessibility (e.g., in a high-density data table), use `outline-variant` at **15% opacity**. High-contrast borders are strictly forbidden.

---

## 5. Components

### Project Cards
Forbid divider lines. Use `surface-container-lowest` as the card background against a `surface-container` section.
*   **Padding:** 24px (1.5rem) consistent internal spacing.
*   **Corner Radius:** `md` (0.375rem) for a sharp, tailored look.

### Sophisticated Timeline
The timeline (as seen in the project dashboard) must feel like a "living document."
*   **The Axis:** Use a 2px `secondary` line.
*   **Milestones:** Use `secondary_container` for event markers. 
*   **Interactivity:** Hovering over a timeline event should trigger a `Glassmorphic` tooltip with 40% `surface_variant` transparency.

### Buttons & Inputs
*   **Primary Button:** `primary` background, `on_primary` text. No border. Subtle vertical gradient.
*   **Input Fields:** `surface-container-lowest` background with a `Ghost Border`. On focus, the border transitions to a 1.5px `secondary` (Legal Blue).
*   **Chips:** Use for "Show Emails" or "Show Attachments." These should be pill-shaped (`full` roundedness) using `secondary_fixed` with `on_secondary_fixed` text for a subtle, integrated look.

### Data Tables
No vertical or horizontal lines. Use row-hover states (`surface-container-high`) to define the user's focus. Use `label-sm` for headers in all-caps with 0.05em letter spacing for an editorial feel.

---

## 6. Do's and Don'ts

### Do
*   **Do** use extreme whitespace (48px+) between major sections to let the legal "Project Title" breathe.
*   **Do** use `Public Sans` for numerals in data tables; its geometric nature aligns numbers perfectly.
*   **Do** use Tonal Layering (Surface Shifts) to separate the Timeline from the Project Details.

### Don't
*   **Don't** use 100% black text on a 100% white background. Use `on_surface` on `surface`.
*   **Don't** use "Drop Shadows" that look like shadows. They should look like "Ambient Glows."
*   **Don't** use icons without labels in core navigation. This is a tool for precision; ambiguity is the enemy.
*   **Don't** use "Social Media Blue." Stick strictly to the `secondary` Legal Blue (`#3e608e`).