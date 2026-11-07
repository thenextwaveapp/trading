# Paper Fleet — Access Model & Funnel Architecture

Status: design. Covers the visitor → Pro funnel, entitlement states, the free/Pro
feature split, screens, and how it maps onto the existing code.

## 1. The ladder (four states)

- **Visitor** — not authenticated. Browses the public showcase and the landing page. Goal: sign up.
- **Free** — authenticated, not entitled. Full app with two caps (1 fleet, 3 deployed bots). Goal: reach first value, generate data.
- **Trial** — one-time 7-day Pro, card captured up front. Full feature set. Goal: experience Pro.
- **Pro ($27/mo)** — full feature set, ongoing. Goal: convert and retain.

Movement between states (card-up-front trial, so there is no "free lapse"):

- Free user who never starts a trial → **stays Free** indefinitely.
- Trial runs its course without cancellation → **auto-converts to paid Pro** on day 7.
- Trial **cancelled** before day 7 → **Free** at day 7 (no charge).
- Pro **cancelled** → **Free** at `current_period_end`.
- A Free user is never locked out of the app — only the Pro-only capabilities are gated (§3, §6).

## 2. Entitlement — source of truth

Derived from `pf_subscriptions` (the Stripe mirror, written only by `stripe-webhook`) plus auth.

| State | Condition |
|---|---|
| `visitor` | not authenticated |
| `free` | authenticated; no `pf_subscriptions` row, or `status ∈ {canceled, incomplete_expired, unpaid}` |
| `trialing` | `status = 'trialing'` |
| `pro` | `status = 'active'` |

- **Entitled** (Pro feature set) = `status ∈ {trialing, active, past_due}`. `past_due` is a grace window (Stripe retrying a failed charge) shown with an "update payment" prompt; when retries are exhausted Stripe sets `canceled` → `free`.
- **Trial eligibility** (`trial_available`) = account has **never had a `pf_subscriptions` row**. First checkout creates the row and permanently consumes eligibility; any later re-subscribe is immediate paid (checkout omits `trial_period_days`).

`entitlementOf()` already returns `{ entitled, status, trialing, daysLeft, cancelAtPeriodEnd }`; add derived `trialAvailable`.

## 3. Feature matrix

| Capability (app surface) | visitor | free | trial / pro |
|---|---|---|---|
| Public browse: `/leaderboard`, `/market`, `/market/:symbol`, `/bot/:name`, `/builder/:handle`, `/challenges`, `/challenge/:slug` | ✅ | ✅ | ✅ |
| Activity feed `/feed` | — | ✅ | ✅ |
| Build a strategy (`/build/compose`) | — | ✅ | ✅ |
| Backtest / Training (`/build/training`) | — | ✅ unlimited | ✅ unlimited |
| Trials + Weather validation (`/build/trials`, `/build/weather`) | — | ✅ | ✅ |
| Custom universes, presets, timing/exit params | — | ✅ | ✅ |
| Challenges participation | — | ✅ | ✅ |
| Deployed bots (`pf_bots.stage='deployed'`, `/build/deploy`) | — | ✅ **max 3** | ✅ unlimited |
| Fleets (`pf_fleets`, FleetsPanel) | — | ✅ **1** | ✅ multiple |
| Feed / social signals in a spec (feed operands `FEED_SCORE`/`FEED_CONF` in Compose) | — | 🔒 | ✅ |
| AI co-pilot (Assistant + `parse-strategy` "Build it") | — | 🔒 (optional small taste quota, TBD) | ✅ unlimited |
| Live capital (future) | — | 🔒 | ✅ when shipped |

Caps map to `pf_plans`: Free row `max_fleets = 1`, deployed cap = 3 (`max_bots` or `features.max_deployed`); Pro row both null.

## 4. Routes & gating

- **Visitor:** `/` renders the landing. Public routes render normally. `/feed`, `/fleet`, `/build/*`, `/settings/*` → sign-in modal (`RequireAuth`, unchanged).
- **First-run:** authenticated users with `pf_profiles.onboarded_at IS NULL` are held at `/onboarding` until it completes (`RequireOnboarded` gate).
- **Free/Pro in-app:** **no route-level plan wall.** `RequirePlan` and the blurred full-screen paywall overlay are **removed**. The app is fully navigable at Free; Pro boundaries are per-action (§6).
- `/upgrade` stays as the standalone page / deep-link target for the upgrade content.

## 5. Screens

### 5a. Landing (`/`, visitor)
Visual conversion page. Hero = product output (live bot cards / leaderboard / a running fleet). Primary: "Start free" → sign-in modal. Secondary: browse the public showcase.

### 5b. Sign-in / sign-up (AuthModal)
Split layout: product showcase one side, auth the other (Google + email magic-link). Existing Supabase passwordless + Google flow, restyled.

### 5c. Onboarding (`/onboarding`, new)
Linear, runs once, gated on `onboarded_at`:
1. **Welcome** — one framing line.
2. **Questionnaire** — 4 questions (§5d), persisted to `onboarding_checklist`.
3. **Payoff** — "Building your starter strategy…" → a starter bot is pre-seeded (or template selected) from the answers, shown ready to run.
4. **Trial step** — Start 7-day trial (Checkout) or Skip. Either path sets `onboarded_at`. Skip → Free app at `/feed`.

### 5d. Onboarding questions
Each drives a downstream change:

| Q | Options | Downstream effect |
|---|---|---|
| What do you want to trade? | Crypto perps · Crypto spot · Stocks · FX | starter `market` + universe + Compose market glyph |
| How do you trade today? | By hand · I follow signals · I build my own systems · New to this | starter template complexity (New → guided preset; Builder → advanced/blank) |
| What do you want out of Paper Fleet? | Learn systematic trading · Build & backtest ideas · Climb the leaderboard · Eventually trade live | payoff + trial-step copy |
| How did you hear about us? | freeform / list | attribution only |

Q1 + Q3 echoed on the trial step.

## 6. Pro-boundary enforcement (pull, not push)

Checked at the action; surfaces the upgrade modal only on user intent. No proactive interruption, no persistent bar.

| Boundary | Check location | Trigger |
|---|---|---|
| Deploy 4th bot | `/build/deploy` deploy action (`setBotStage → deployed`) | count owner `pf_bots` with `stage='deployed'`; `free` and ≥3 → modal |
| Add 2nd fleet | FleetsPanel create-fleet | count `pf_fleets`; `free` and ≥1 → modal |
| Use feed signals | Compose feed-operand builder (locked) + save/deploy validation | spec has a feed operand and user is `free` → modal / block |
| AI co-pilot | Assistant send / "Build it" | `free` (over taste quota) → modal |

Modal primary action = start trial if `trial_available`, else "Upgrade to Pro" ($27, immediate).

## 7. Data model deltas

- `pf_profiles`: `onboarded_at` / `onboarding_step` / `onboarding_checklist` (exist) drive the funnel; `stripe_customer_id` (added).
- `pf_subscriptions`: mirror fields added (`status`, `trial_ends_at`, `current_period_end`, `cancel_at_period_end`, `stripe_subscription_id`).
- `pf_plans`: `free` (`max_fleets=1`, deployed cap=3) and `pro` (unlimited) seeded; adjust caps.
- `create-checkout-session`: include `trial_period_days: 7` only when `trial_available`.

## 8. Reuse vs. change (against current code)

- **Keep:** `create-checkout-session`, `create-portal-session`, `stripe-webhook`, the mirror, `entitlementOf`, Settings → Plan tab, upgrade content, the migration + RLS lockdown.
- **Remove:** `RequirePlan` route gating + blurred overlay; the persistent TopBar trial/upgrade chip.
- **Add:** `RequireOnboarded` + `/onboarding`; per-action Pro-boundary modals; `trial_available` logic in checkout + UI; visual landing + visual sign-in.

## 9. Build order

1. Free caps live + remove route wall → app is free-to-roam.
2. Onboarding flow (`/onboarding`, 4 questions, payoff, trial step) + `onboarded_at` gate.
3. Per-action Pro-boundary modals (deploy, fleet, feed signals, AI).
4. Visual landing + visual sign-in.
