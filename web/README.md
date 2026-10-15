# Paper Fleet — web app

The real product: a Vite + React + TypeScript app (CSS Modules), a reskin of the
paper-fleet dashboard built against the existing backend. Charts use
`lightweight-charts`. Installable as a PWA; wrap with Capacitor later for native.

## Data

Consumes the existing dashboard API (`/api`, `/candles`) — the same source
`fleet_dashboard.py` (:8787) serves, which proxies the live Hetzner paper fleet.
In dev, Vite proxies those paths to `VITE_API_TARGET` (default
`http://127.0.0.1:8787`). So the app shows identical numbers to :8787 whenever
that tunnel is up.

```bash
npm install
npm run dev            # http://localhost:5173  (proxies /api -> :8787)
VITE_API_TARGET=http://127.0.0.1:8789 npm run dev   # or point at the v2 proxy
npm run build          # -> dist/ (static, deploy anywhere with SPA fallback)
```

## Layout

```
src/
  api/      types.ts, client.ts, useFleet.ts (10s poll), context.ts
  lib/      format.ts (usd/pct/px/identicon/lt/… — ported 1:1 so figures match)
  components/ Sidebar, DataTable (sort+paginate), FleetChart (legend+solo),
              BotChart (vs fleet avg), CandleModal (context), cells (BotLink/Coin)
  routes/   FleetView, BotProfile  (+ more screens as ported)
  styles/   theme.css (tokens), global.css
```
