# Paper Fleet — colors & surface system

Pulled from the color-system mockup and `paper-fleet/*.dc.html`. Core tokens
already live in `web/src/styles/theme.css`; the **8-hue fleet palette** and the
**glass / keycap / glow recipes** below are the parts not yet fully in code.

_Last updated: 2026-10-24_

---

## The fleet palette

**Fleet = hue · bot in a fleet = shade · pinned bots = slots 1–8.** `300` is the
default "slot" shade.

| Slot | Hue | 100 | 200 | **300** | 400 | 500 |
|---|---|---|---|---|---|---|
| 1 | Blue | `#97c1f7` | `#65a1ec` | **`#3a81d7`** | `#2463ae` | `#144782` |
| 2 | Amber | `#f8cb98` | `#e5a65a` | **`#cb8315`** | `#a66800` | `#7f4e00` |
| 3 | Violet | `#b59be5` | `#9b73da` | **`#814ec6`** | `#62349c` | `#441f72` |
| 4 | Teal | `#a0e2e5` | `#63c6cc` | **`#19a9b0`** | `#00888e` | `#00686d` |
| 5 | Magenta | `#e99cc1` | `#d970a5` | **`#c04688`** | `#982e6a` | `#701c4c` |
| 6 | Olive | `#d4d69b` | `#b5b760` | **`#979828`** | `#797a11` | `#5c5c07` |
| 7 | Indigo | `#8a9cd3` | `#657bc7` | **`#455bb2`** | `#2e408b` | `#1a2761` |
| 8 | Orange | `#f7b198` | `#e78765` | **`#cf6139`** | `#a74824` | `#7e3216` |

Fixed roles:

| Role | Hex | Use |
|---|---|---|
| Base | `#E9ECF1` | the "always on" bot / primary text / keycap face |
| Everyone else | `#2A313C` | the un-pinned crowd, 1px lines |
| Gain | `#3DDC97` | **numbers only** (`--up`) |
| Loss | `#FF5C6C` | **numbers only** (`--down`) |

> ⚠️ Code gap: `theme.css` chart palette `--c0…--c11` is still the old
> GitHub-ish set, and some charts use hardcoded JS color arrays. Rolling this
> 8-hue palette app-wide = update the CSS tokens **and** those JS arrays together
> so it isn't half-applied.

## Surfaces, lines, text (in `theme.css`)

```
--bg #06080b        app canvas        body #07090C (mockup)
--sidebar-top #0b0f14
--card-top #10151c  --card-bottom #0a0d12   (card gradient)
--line #151920  --line-2 #1b212a  --border #262c36  --border-hover #3a4250
--fg #e9ecf1  --fg-2 #b4bac4  --muted #8b919b  --muted-2 #7d838d  --muted-3 #6b717b
```

Background glow wash (on `.main` / hero):
```css
background:
  radial-gradient(900px 440px at 12% -8%, rgba(58,129,215,.12), transparent 65%),
  radial-gradient(760px 420px at 100% -4%, rgba(129,78,198,.07), transparent 60%),
  #06080B;
```

## Glass (frosted panel over a blurred live dashboard)

```css
.glass {              /* full-screen overlay */
  background: rgba(7,9,12,.42);
  backdrop-filter: blur(26px) saturate(150%);
}
.panel {              /* the floating dialog */
  border-radius: 28px;
  background: rgba(18,22,29,.66);
  border: 1px solid rgba(255,255,255,.09);
  box-shadow: 0 30px 80px rgba(0,0,0,.45);
}
```

Used on the landing hero chart + command panel (`Landing.module.css`). The
mockups also use it for Login/Signup as a modal over the blurred fleet — not
built yet.

## Cards / panels (gradient + inset highlight + depth)

```css
background: linear-gradient(180deg, #10151C 0%, #0A0D12 100%);
border-color: #1B212A;
box-shadow:
  inset 0 1px 0 rgba(255,255,255,.065),   /* top highlight */
  0 1px 0 rgba(0,0,0,.6),
  0 14px 30px -14px rgba(0,0,0,.7);        /* soft drop */
/* hover: inset 0 1px 0 rgba(255,255,255,.09), 0 22px 40px -16px rgba(0,0,0,.85) */
```

## Keycap primary button (the tactile white press)

```css
background: #E9ECF1; color: #07090C; border: none;
box-shadow:
  inset 0 1px 0 rgba(255,255,255,.95),
  inset 0 -2px 0 rgba(7,9,12,.10),
  0 3px 0 #7D838D,                 /* the 3D edge */
  0 6px 14px rgba(0,0,0,.45);
/* :hover background #F6F7F9 · :active translateY(3px) + collapse the edge */
```
Danger variant swaps the edge to `0 3px 0 #8E2633`, hover `#FF7280`.

## Glowing data lines

Equity/curve strokes get a colored `drop-shadow` glow:

```css
svg path[stroke="#3a81d7"] { filter: drop-shadow(0 0 6px rgba(58,129,215,.55)); } /* blue */
svg path[stroke="#cb8315"] { filter: drop-shadow(0 0 6px rgba(203,131,21,.45)); } /* amber */
svg path[stroke="#814ec6"] { filter: drop-shadow(0 0 6px rgba(129,78,198,.50)); } /* violet */
svg path[stroke="#E9ECF1"], svg path[stroke="#3DDC97"] { filter: drop-shadow(0 0 5px rgba(233,236,241,.25)); }
```

Big hero numbers use clipped gradient text: `linear-gradient(180deg,#FFFFFF 35%,#9AA4B2 100%)`.

## Type

| Role | Font | Notes |
|---|---|---|
| Display / headings | **DM Sans** 700 | tight tracking `-0.03…-0.045em` |
| Body / UI | **Figtree** 400/500 | |
| Numbers | **Geist Mono** 400/500 | `font-feature-settings: 'zero' 1, 'tnum' 1` |

## Radii

panel `28px` · cards/bot tiles `14px` · inputs `14px` · buttons `10–12px`
