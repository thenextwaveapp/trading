#!/usr/bin/env python3
"""Dashboard for the LIVE bot — http://localhost:8788. Stdlib only.

Reads live/state.json, trades.csv, bot.log fresh per request. Shows mode
(LIVE / dry / HALTED), the frozen spec, equity, open positions marked to
live prices, trades, BTC gate, log. Controls (loopback only): pause/resume
entries, restart bot (launchd), and a two-step FLATTEN EVERYTHING button
(writes live/FLATTEN; the bot's watcher closes all positions within ~10s
and halts). A watchdog pushes a phone alert if the bot process dies.

Usage: python3 dashboard.py [--port N] [--lan]
"""
import csv
import fcntl
import json
import os
import subprocess
import sys
import threading
import time
import urllib.request
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from bot import (CFG, CAPS, RISKC, BOOKS, SHORT_BOOK, STATE, TRADES,  # noqa: E402
                 LOGF, ARMED, HALTED, PAUSED, FLATTEN, M15, btc_bear,
                 ntfy_topic, notify, load_state, load_events, dial_state)

PX_API = "https://fapi.binance.com/fapi/v1/ticker/price"
UNI = json.load(open(os.path.join(HERE, "universe.json")))
BOT_SVC = f"gui/{os.getuid()}/com.trading.livebot"
START_DRY = CAPS["start_equity_dry"]


def bot_running():
    path = os.path.join(HERE, "bot.lock")
    if not os.path.exists(path):
        return None
    try:
        f = open(path)
        fcntl.flock(f, fcntl.LOCK_EX | fcntl.LOCK_NB)
        fcntl.flock(f, fcntl.LOCK_UN)
        f.close()
        return False
    except OSError:
        return True


_px_cache = {}


def live_px(symbol):
    c = _px_cache.get(symbol)
    if c and time.time() - c[0] < 30:
        return c[1]
    try:
        with urllib.request.urlopen(f"{PX_API}?symbol={symbol}",
                                    timeout=5) as r:
            px = float(json.loads(r.read())["price"])
        _px_cache[symbol] = (time.time(), px)
        return px
    except Exception:
        return None


def read_trades():
    if not os.path.exists(TRADES):
        return []
    out = []
    for r in list(csv.reader(open(TRADES)))[1:]:
        try:
            out.append(dict(coin=r[0], book=r[1], side=int(r[2]),
                            t_sig=int(float(r[3])), entry=float(r[4]),
                            stop=float(r[5]), exit_t=int(float(r[6])),
                            kind=r[7], net=float(r[8]), pnl=float(r[9]),
                            notional=float(r[10]), equity_after=float(r[11]),
                            mode=r[12]))
        except (ValueError, IndexError):
            continue
    return out


def payload():
    now = int(time.time() * 1000)
    st = load_state()
    trades = sorted(read_trades(), key=lambda t: t["exit_t"], reverse=True)
    live_cfg = bool(CFG.get("live"))
    armed = os.path.exists(ARMED) and open(ARMED).read().strip() == "YES"
    keys = os.path.exists(os.path.join(HERE, "keys.env"))
    is_live = live_cfg and armed and keys
    opens = []
    for p in st["positions"]:
        px = live_px(UNI.get(p["coin"], ""))
        upct = p["side"] * (px / p["entry"] - 1) if px else None
        opens.append(dict(coin=p["coin"], book=p["book"],
                          side="long" if p["side"] == 1 else "short",
                          entry=p["entry"], px=px, upct=upct,
                          upnl=p["notional"] * upct if upct is not None
                          else None,
                          stop=p["stop"], notional=round(p["notional"], 2),
                          t_sig=p["t_sig"],
                          exits_at=p["t_sig"] + p["hold"] * M15))
    nets = [t["net"] for t in trades]
    start_eq = START_DRY if not is_live else None
    state_age = round(time.time() - os.path.getmtime(STATE)) \
        if os.path.exists(STATE) else None
    tail = []
    if os.path.exists(LOGF):
        with open(LOGF) as f:
            tail = [ln.rstrip() for ln in f.readlines()[-30:]]
    curve = [[t["exit_t"], t["equity_after"]]
             for t in sorted(trades, key=lambda x: x["exit_t"])]
    # regime monitor: stop-out rate of the last 20 short-book trades
    # (~40% in-regime, drifting toward ~55% = the edge dying; dd depth is
    # order-luck and says nothing — the shuffle-test finding)
    s_trades = [t for t in trades if t["book"] == SHORT_BOOK][:20]
    stopout = round(sum(1 for t in s_trades if t["kind"] == "sl")
                    / len(s_trades) * 100) if len(s_trades) >= 5 else None
    size_eq = min(st["equity"], CAPS["equity_cap_usd"]) if is_live \
        else st["equity"]
    gross = round(sum(p["notional"] for p in st["positions"]), 2)
    return dict(
        dial=dial_state(load_events()), stopout=stopout,
        stopout_n=len(s_trades),
        gross=gross, gross_cap=round(
            RISKC.get("max_gross_frac", 1.0) * size_eq, 2),
        now=now, mode="LIVE" if is_live else "DRY",
        live_cfg=live_cfg, armed=armed, keys=keys,
        halted=os.path.exists(HALTED), paused=os.path.exists(PAUSED),
        flatten_pending=os.path.exists(FLATTEN),
        running=bot_running(), state_age_s=state_age,
        bear=btc_bear(), equity=round(st["equity"], 2), start_eq=start_eq,
        pnl=round(st["equity"] - START_DRY, 2) if not is_live else None,
        kill_until=st["kill_until"], positions=opens,
        unreal=round(sum(p["upnl"] for p in opens
                         if p["upnl"] is not None), 2),
        trades=trades[:200], closed=len(trades),
        win=round(sum(1 for n in nets if n > 0) / len(nets) * 100)
        if nets else None,
        avg=round(sum(nets) / len(nets) * 100, 3) if nets else None,
        curve=curve, ntfy=ntfy_topic() or "",
        books={k: dict(v) for k, v in BOOKS.items()},
        caps=CAPS, log=tail)


def set_flag(path, on, text="set via dashboard\n"):
    if on:
        with open(path, "w") as f:
            f.write(text)
    else:
        try:
            os.remove(path)
        except FileNotFoundError:
            pass
    return True, "done"


def run_cmd(cmd):
    try:
        p = subprocess.run(cmd, capture_output=True, text=True, timeout=20)
        return p.returncode == 0, (p.stdout + p.stderr).strip()
    except Exception as e:
        return False, repr(e)


ACTIONS = {
    "pause_on": lambda b: set_flag(PAUSED, True),
    "pause_off": lambda b: set_flag(PAUSED, False),
    "unhalt": lambda b: set_flag(HALTED, False),
    "flatten": lambda b: set_flag(
        FLATTEN, True, "flatten requested via dashboard\n") and
        (True, "FLATTEN requested — bot closes everything within ~10s"),
    "bot_restart": lambda b: run_cmd(
        ["/bin/launchctl", "kickstart", "-k", BOT_SVC]),
}


def watchdog():
    prev = bot_running()
    while True:
        time.sleep(60)
        cur = bot_running()
        if cur is False and prev:
            notify("LIVE BOT DOWN", "the live bot process is not running",
                   priority="urgent", tags="rotating_light")
        if cur and prev is False:
            notify("Live bot back up", "cycles resumed",
                   tags="white_check_mark")
        prev = cur


PAGE = """<!DOCTYPE html>
<html><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>LIVE Bot</title>
<style>
:root{--bg:#0d1117;--card:#161b22;--line:#30363d;--fg:#e6edf3;--dim:#8b949e;
--green:#3fb950;--red:#f85149;--amber:#d29922;--blue:#58a6ff}
*{box-sizing:border-box;margin:0}
body{background:var(--bg);color:var(--fg);font:14px/1.5 ui-monospace,SFMono-Regular,Menlo,monospace;padding:16px;max-width:1100px;margin:0 auto}
h1{font-size:18px;margin-bottom:10px}
h2{font-size:13px;color:var(--dim);text-transform:uppercase;letter-spacing:.08em;margin:22px 0 8px}
#banner{border-radius:8px;padding:10px 16px;font-size:15px;font-weight:600;margin-bottom:12px;border:1px solid}
#banner.green{background:rgba(63,185,80,.1);border-color:#238636;color:var(--green)}
#banner.amber{background:rgba(210,153,34,.1);border-color:#9e6a03;color:var(--amber)}
#banner.red{background:rgba(248,81,73,.12);border-color:#da3633;color:var(--red)}
#banner.live{background:rgba(88,166,255,.12);border-color:#1f6feb;color:var(--blue)}
.hero{display:flex;gap:10px;flex-wrap:wrap;margin-bottom:4px}
.stat{background:var(--card);border:1px solid var(--line);border-radius:8px;padding:8px 16px;min-width:130px;flex:1}
.stat .v{font-size:22px;font-weight:650}
.stat .l{font-size:10px;color:var(--dim);text-transform:uppercase;letter-spacing:.06em}
.stat .s{font-size:11px;color:var(--dim)}
.pills{display:flex;gap:8px;flex-wrap:wrap;margin:10px 0;align-items:center}
.pill{border:1px solid var(--line);border-radius:999px;padding:2px 12px;font-size:12px;background:var(--card)}
.ok{color:var(--green)}.bad{color:var(--red)}.warn{color:var(--amber)}.dim{color:var(--dim)}.blue{color:var(--blue)}
table{width:100%;border-collapse:collapse;background:var(--card);border:1px solid var(--line);border-radius:8px;overflow:hidden;font-size:13px}
th,td{padding:5px 10px;text-align:right;border-bottom:1px solid var(--line);white-space:nowrap}
th{color:var(--dim);font-weight:500;font-size:11px;text-transform:uppercase}
td:first-child,th:first-child{text-align:left}
tr:last-child td{border-bottom:none}
.scroll{overflow-x:auto;border-radius:8px}
#chart{width:100%;height:200px;background:var(--card);border:1px solid var(--line);border-radius:8px}
pre{background:var(--card);border:1px solid var(--line);border-radius:8px;padding:10px;font-size:12px;overflow-x:auto;color:var(--dim)}
.muted{color:var(--dim);font-size:12px}
button{cursor:pointer;background:#21262d;border:1px solid var(--line);color:var(--fg);border-radius:6px;padding:4px 14px;font:inherit;font-size:13px}
button:hover{background:#30363d}
button.danger{border-color:#da3633;color:var(--red);font-weight:600}
button.go{border-color:#2b5a30;color:var(--green)}
</style></head><body>
<h1>Live Bot — pump-short + capitulation-long</h1>
<div id="banner">loading…</div>
<div class="hero" id="hero"></div>
<div class="pills" id="pills"></div>
<div class="pills" id="controls"></div>
<div class="muted" id="ctlmsg"></div>
<h2>Open positions (live)</h2><div class="scroll"><table id="positions"></table></div>
<h2>Equity</h2><svg id="chart"></svg>
<h2>Trades</h2><div class="scroll"><table id="trades"></table></div>
<h2>The spec (frozen — config.json)</h2><div class="scroll"><table id="spec"></table></div>
<h2>Bot log</h2><pre id="log"></pre>
<p class="muted" id="foot"></p>
<script>
const fmt=t=>new Date(t).toISOString().slice(5,16).replace("T"," ");
const pct=(v,d=2)=>v==null?"–":(v>0?"+":"")+v.toFixed(d)+"%";
const usd=v=>v==null?"–":(v<0?"−$":"+$")+Math.abs(v).toFixed(2).replace(/\\B(?=(\\d{3})+(?!\\d))/g,",");
const cls=v=>v>0?"ok":v<0?"bad":"dim";
const left=t=>{const m=Math.round((t-Date.now())/60000);
  return m<=0?"closing…":m<60?m+"m":Math.floor(m/60)+"h "+(m%60)+"m";};
function esc(s){return String(s).replace(/[&<>]/g,c=>({"&":"&amp;","<":"&lt;",">":"&gt;"}[c]))}
let FLARM=false;

function render(d){
  const bn=document.getElementById("banner");
  if(d.halted){bn.className="red";bn.textContent="⛔ HALTED — breaker or manual flatten tripped. rm live/HALTED (or Unhalt button) after review.";}
  else if(d.running===false){bn.className="red";bn.textContent="⚠ BOT NOT RUNNING";}
  else if(d.paused){bn.className="amber";bn.textContent="⏸ entries PAUSED — open positions still managed";}
  else if(d.mode==="LIVE"){bn.className="live";bn.textContent="● LIVE — real orders on Hyperliquid. Caps: $"+d.caps.equity_cap_usd+" equity / $"+d.caps.max_notional_usd+" per trade.";}
  else{bn.className="green";bn.textContent="● DRY RUN — full pipeline, simulated fills. Ready for keys ("+(d.keys?"keys ✓":"no keys.env")+", "+(d.live_cfg?"config live ✓":"config live:false")+", "+(d.armed?"ARMED ✓":"not armed")+").";}

  document.getElementById("hero").innerHTML=
    `<div class="stat"><div class="l">equity (${d.mode.toLowerCase()})</div>
      <div class="v">$${d.equity.toFixed(2)}</div>
      <div class="s">${d.pnl!=null?("P&L "+usd(d.pnl)):"from Hyperliquid account"}</div></div>`+
    `<div class="stat"><div class="l">open / unrealized</div>
      <div class="v ${cls(d.unreal)}">${usd(d.unreal)}</div>
      <div class="s">${d.positions.length} position${d.positions.length===1?"":"s"}</div></div>`+
    `<div class="stat"><div class="l">closed trades</div>
      <div class="v">${d.closed}</div>
      <div class="s">${d.win==null?"–":d.win+"% win"} · avg ${pct(d.avg,3)}</div></div>`;

  const btc=d.bear==null?'<b class="warn">?</b>':d.bear?'<b class="bad">BEAR</b> — capit gate open':'<b class="ok">BULL</b> — capit gate closed';
  const dl=d.dial,dm=dl.m==null?"n/a":pct(dl.m*100);
  const dial=dl.short?`<b class="bad">SHORT OPEN</b>`:`<b class="warn">closed</b>`;
  const so=d.stopout==null?`<span class="dim">n/a (${d.stopout_n} trades)</span>`
    :`<b class="${d.stopout<48?"ok":d.stopout<55?"warn":"bad"}">${d.stopout}%</b>`;
  document.getElementById("pills").innerHTML=
    `<span class="pill">mode: <b class="${d.mode==="LIVE"?"blue":"dim"}">${d.mode}</b></span>`+
    `<span class="pill">pump dial: ${dial} (n=${dl.n}, m=${dm})</span>`+
    `<span class="pill">BTC 4h: ${btc}</span>`+
    `<span class="pill">stop-out rate (regime monitor): ${so}</span>`+
    `<span class="pill">gross: $${d.gross.toFixed(0)} / $${d.gross_cap.toFixed(0)}</span>`+
    `<span class="pill">bot: <b class="${d.running?"ok":"bad"}">${d.running===true?"running":d.running===false?"DOWN":"?"}</b>${d.state_age_s!=null?" · "+Math.round(d.state_age_s/60)+"m":""}</span>`+
    (d.kill_until>d.now?`<span class="pill"><b class="bad">KILL-SWITCH until ${fmt(d.kill_until)}</b></span>`:"")+
    `<span class="pill dim">alerts: ${esc(d.ntfy)||"off"}</span>`+
    `<span class="pill dim">updated ${new Date(d.now).toUTCString().slice(17,25)} UTC</span>`;

  let ctl=(d.paused
    ?`<button class="go" onclick="ctl('pause_off')">&#9654; resume entries</button>`
    :`<button onclick="ctl('pause_on')">&#10074;&#10074; pause entries</button>`)
    +`<button onclick="ctl('bot_restart')">&#8635; restart bot</button>`;
  if(d.halted)ctl+=`<button class="go" onclick="ctl('unhalt')">unhalt (after review)</button>`;
  ctl+=FLARM
    ?`<button class="danger" onclick="ctl('flatten');FLARM=false">&#9888; CONFIRM — close ALL positions now</button>
      <button onclick="FLARM=false;render(LAST)">cancel</button>`
    :`<button class="danger" onclick="FLARM=true;render(LAST)">flatten everything…</button>`;
  if(d.flatten_pending)ctl+='<span class="pill"><b class="warn">flatten pending…</b></span>';
  document.getElementById("controls").innerHTML=ctl;

  let h="<tr><th>book</th><th>coin</th><th>side</th><th>entry</th><th>now</th><th>uP&amp;L</th><th>net</th><th>stop</th><th>time exit in</th><th>notional</th><th>since (UTC)</th></tr>";
  if(!d.positions.length)h+='<tr><td colspan="11" class="dim">none — scanning</td></tr>';
  d.positions.forEach(p=>{h+=`<tr><td>${p.book}</td><td><b>${esc(p.coin)}</b></td>
    <td class="${p.side==="short"?"bad":"ok"}">${p.side}</td><td>${p.entry}</td>
    <td>${p.px==null?"–":p.px}</td><td class="${cls(p.upnl)}"><b>${usd(p.upnl)}</b></td>
    <td class="${cls(p.upct)}">${p.upct==null?"–":pct(p.upct*100)}</td>
    <td>${p.stop?p.stop.toPrecision(6):"none"}</td><td>${left(p.exits_at)}</td>
    <td>${p.notional.toFixed(0)}</td><td>${fmt(p.t_sig)}</td></tr>`;});
  document.getElementById("positions").innerHTML=h;

  let h2="<tr><th>exit (UTC)</th><th>book</th><th>coin</th><th>kind</th><th>net</th><th>pnl</th><th>notional</th><th>equity</th><th>mode</th></tr>";
  if(!d.trades.length)h2+='<tr><td colspan="9" class="dim">none yet</td></tr>';
  d.trades.forEach(t=>{h2+=`<tr><td>${fmt(t.exit_t)}</td><td>${t.book}</td><td>${esc(t.coin)}</td><td>${t.kind}</td><td class="${cls(t.net)}">${pct(t.net*100)}</td><td class="${cls(t.pnl)}">${t.pnl.toFixed(2)}</td><td>${t.notional.toFixed(0)}</td><td>${t.equity_after.toFixed(2)}</td><td class="${t.mode==="live"?"blue":"dim"}">${t.mode}</td></tr>`;});
  document.getElementById("trades").innerHTML=h2;

  let h3="<tr><th>book</th><th style='text-align:left'>rule</th></tr>";
  Object.entries(d.books).forEach(([k,b])=>{
    const rule=b.side===-1
      ?`SHORT: runup ≥ ${b.runup*100}%/4h + first red close + vol ≥ ${b.vol}× → short at close${b.dial_gate?" · pump-dial gate (30d mean fwd < 0)":""} · stop = 4h high (on exchange) · time exit ${b.hold/4}h`
      :`LONG: 24h return ≤ −${b.depth*100}% fresh crossing${b.btc_bear_gate?" + BTC 4h EMA20≤EMA50 bear gate":""} → long at close · ${b.stop==="none"?"no stop":"stop "+b.stop} · time exit ${b.hold/4}h · sized on 2×NATR24`;
    h3+=`<tr><td>${esc(k)}</td><td style="text-align:left" class="dim">${rule}</td></tr>`;});
  h3+=`<tr><td>risk</td><td style="text-align:left" class="dim">0.75% equity risk/trade · 20% notional cap · live caps $${d.caps.equity_cap_usd} equity / $${d.caps.max_notional_usd} per trade · max 6 concurrent · kill-switch 7d −5% → 3d pause · breakers 24h −5% flatten+halt / 7d −12% full halt</td></tr>`;
  document.getElementById("spec").innerHTML=h3;

  document.getElementById("log").textContent=d.log.join("\\n")||"(empty)";
  document.getElementById("foot").textContent="auto-refresh 60s · controls work from this Mac only · live/README.md is the runbook";
  chart(d);
}

function chart(d){
  const svg=document.getElementById("chart"),W=svg.clientWidth,H=svg.clientHeight;
  svg.setAttribute("viewBox",`0 0 ${W} ${H}`);
  let pts=d.curve.slice();
  if(d.start_eq!=null)pts.unshift([pts.length?pts[0][0]-86400000:d.now-86400000,d.start_eq]);
  pts.push([d.now,d.equity]);
  if(pts.length<2){svg.innerHTML="";return;}
  const t0=pts[0][0],t1=pts[pts.length-1][0];
  let y0=Math.min(...pts.map(p=>p[1])),y1=Math.max(...pts.map(p=>p[1]));
  const pad=(y1-y0)*0.1||50;y0-=pad;y1+=pad;
  const X=t=>35+(t-t0)/(t1-t0||1)*(W-50),Y=v=>H-18-(v-y0)/(y1-y0)*(H-30);
  let s="";
  for(let i=0;i<=3;i++){const v=y0+(y1-y0)*i/3,y=Y(v);
    s+=`<line x1="35" x2="${W-15}" y1="${y}" y2="${y}" stroke="#21262d"/>`+
       `<text x="2" y="${y+4}" fill="#8b949e" font-size="10">${Math.round(v)}</text>`;}
  s+=`<polyline points="${pts.map(p=>X(p[0]).toFixed(1)+","+Y(p[1]).toFixed(1)).join(" ")}" fill="none" stroke="#58a6ff" stroke-width="1.8"/>`;
  [t0,t1].forEach(t=>{s+=`<text x="${X(t)}" y="${H-4}" fill="#8b949e" font-size="10" text-anchor="middle">${fmt(t).slice(0,11)}</text>`;});
  svg.innerHTML=s;
}

let LAST=null;
async function ctl(action){
  const el=document.getElementById("ctlmsg");
  el.textContent="working…";
  try{
    const r=await fetch("/ctl",{method:"POST",
      headers:{"Content-Type":"application/json"},
      body:JSON.stringify({action})});
    const d=await r.json();
    el.textContent=d.ok?("done"+(d.msg&&d.msg!=="done"?" — "+d.msg:"")):"failed: "+d.msg;
  }catch(e){el.textContent="failed: "+e;}
  setTimeout(tick,1500);
  setTimeout(()=>{el.textContent=""},10000);
}
async function tick(){
  try{const r=await fetch("/api");LAST=await r.json();render(LAST);}
  catch(e){const bn=document.getElementById("banner");bn.className="red";
    bn.textContent="⚠ dashboard server unreachable";}
}
tick();setInterval(tick,60000);
</script></body></html>
"""


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path.split("?")[0] == "/api":
            body, ctype = json.dumps(payload()).encode(), "application/json"
        elif self.path.split("?")[0] == "/":
            body, ctype = PAGE.encode(), "text/html; charset=utf-8"
        else:
            self.send_error(404)
            return
        self.send_response(200)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self):
        if self.path != "/ctl":
            self.send_error(404)
            return
        if self.client_address[0] not in ("127.0.0.1", "::1"):
            self.send_error(403)
            return
        try:
            n = int(self.headers.get("Content-Length", 0))
            body = json.loads(self.rfile.read(n))
            action = body.get("action")
        except Exception:
            body, action = {}, None
        if action not in ACTIONS:
            self.send_error(400)
            return
        ok, msg = ACTIONS[action](body)
        out = json.dumps(dict(ok=ok, msg=msg)).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(out)))
        self.end_headers()
        self.wfile.write(out)

    def log_message(self, *a):
        pass


def main():
    host = "0.0.0.0" if "--lan" in sys.argv else "127.0.0.1"
    port = int(CFG["ops"].get("dashboard_port", 8788))
    if "--port" in sys.argv:
        port = int(sys.argv[sys.argv.index("--port") + 1])
    threading.Thread(target=watchdog, daemon=True).start()
    srv = ThreadingHTTPServer((host, port), Handler)
    print(f"live dashboard: http://localhost:{port}")
    srv.serve_forever()


if __name__ == "__main__":
    main()
