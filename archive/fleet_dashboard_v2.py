#!/usr/bin/env python3
"""Paper Fleet dashboard v2 — the mockup look, wired to the real fleet.

A second, read-only dashboard that reuses fleet_dashboard.payload() (the same
single source of truth: marks.csv, trades_*.csv, fleet_config.json) and serves
the new "paper fleet" visual design from mockup/ — fleet view + bot profile,
with the TradingView equity/candle charts, sortable + paginated tables and the
clickable legend ported from the original dashboard.

The original dashboard (fleet_dashboard.py, :8787) is left completely untouched
and keeps owning the mark sampler / controls. This one only reads.

    python3 fleet_dashboard_v2.py            # http://127.0.0.1:8789
    python3 fleet_dashboard_v2.py --port N   # pick a port
    python3 fleet_dashboard_v2.py --lan      # bind 0.0.0.0 (read-only anyway)
"""
import csv
import json
import os
import sys
import time
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import fleet_dashboard as fd   # reuse the data layer; no side effects at import

# The real paper fleet runs on the Hetzner server; the original dashboard
# (fleet_dashboard.py, :8787) is tunnelled to it. By default v2 PROXIES its
# data from that upstream so its numbers are identical to :8787, no matter
# where v2 itself runs. `--local` instead reads this machine's paper/fleet
# files directly (use that when v2 runs ON the server, next to the data).
UPSTREAM = "http://127.0.0.1:8787"

# ---------------------------------------------------------------- marks (RO)
# fleet_dashboard.load_marks() rewrites marks.csv; :8787 owns that write via its
# sampler. We only READ, so we populate fd.MARKS_MEM without touching the file.
_marks_mtime = 0


def refresh_marks():
    """Reload marks.csv into fd.MARKS_MEM when it changes. Never writes."""
    global _marks_mtime
    try:
        mt = os.path.getmtime(fd.MARKS)
    except OSError:
        return
    if mt == _marks_mtime and fd.MARKS_MEM:
        return
    _marks_mtime = mt
    cut = int(time.time() * 1000) - fd.MARK_KEEP_MS
    rows = []
    with open(fd.MARKS) as f:
        for r in csv.reader(f):
            try:
                t, name, eq = int(r[0]), r[1], float(r[2])
            except (ValueError, IndexError):
                continue
            if t >= cut and name in fd.VARIANTS:
                rows.append([t, name, eq])
    with fd.MARKS_LOCK:
        fd.MARKS_MEM[:] = rows


# ---------------------------------------------------------------- the page
PAGE = r"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Paper Fleet · live</title>
<link rel="icon" href="data:image/svg+xml,<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 200 200'><path d='M170 30 L30 95 L95 125 L170 30 Z' fill='%23E9ECF1'/><path d='M170 30 L107 131 L122 170 L137 137 L170 30 Z' fill='%235E8FD8'/></svg>">
<link href="https://fonts.googleapis.com/css2?family=DM+Sans:wght@700&family=Figtree:wght@400;500&family=Geist+Mono:wght@400;500&display=swap" rel="stylesheet">
<style>
body{margin:0;background:#06080B}
*{box-sizing:border-box}
a{color:inherit;text-decoration:none}
.n{font-family:'Geist Mono',monospace;font-feature-settings:'zero' 1,'tnum' 1}
.app{min-height:100vh;background:#06080B;color:#E9ECF1;font-family:'Figtree',sans-serif;display:flex;flex-wrap:wrap;align-items:stretch}
.side{flex:1 1 240px;max-width:264px;border-right:1px solid #151920;padding:22px 14px;display:flex;flex-direction:column;gap:22px;background:linear-gradient(180deg,#0B0F14 0%,#07090C 100%);box-shadow:inset -1px 0 0 rgba(255,255,255,.025)}
.wm{font-family:'DM Sans',sans-serif;font-weight:700;font-size:22px;letter-spacing:-0.04em;padding:0 10px;white-space:nowrap}
.cap{font-size:11px;color:#6B717B;padding:0 10px 8px;letter-spacing:.06em}
.fl{display:flex;align-items:center;gap:12px;padding:10px;border-radius:10px;color:#B4BAC4;cursor:pointer}
.ni{display:flex;align-items:center;gap:12px;padding:10px;border-radius:10px;color:#8B919B;font-size:14px;cursor:pointer}
.fl:hover,.ni:hover{background:#0F1319}
.on{background:linear-gradient(180deg,#171C25,#11151B);color:#E9ECF1;box-shadow:inset 0 1px 0 rgba(255,255,255,.06)}
.sq{width:10px;height:10px;border-radius:3px;flex:none}
.main{flex:999 1 640px;min-width:0;padding-bottom:72px;background:radial-gradient(900px 440px at 12% -8%,rgba(58,129,215,.12),transparent 65%),radial-gradient(760px 420px at 100% -4%,rgba(129,78,198,.07),transparent 60%),#06080B}
.top{display:flex;flex-wrap:wrap;gap:16px;justify-content:space-between;align-items:center;padding:18px 40px;border-bottom:1px solid #151920}
.btn{height:40px;padding:0 18px;border-radius:10px;border:1px solid #262C36;background:#10141A;color:#E9ECF1;font:inherit;font-size:13px;display:inline-flex;align-items:center;justify-content:center;gap:8px;cursor:pointer;white-space:nowrap;box-shadow:inset 0 1px 0 rgba(255,255,255,.06),0 2px 0 #030406;margin-bottom:2px}
.btn:hover{border-color:#3A4250}
.btn.sm{height:28px;padding:0 10px;font-size:12px}
.btn.pri{background:#E9ECF1;color:#07090C;border-color:#E9ECF1;font-weight:500}
.btn[disabled]{opacity:.45;cursor:not-allowed;box-shadow:none}
.card{border:1px solid #1B212A;border-radius:16px;background:linear-gradient(180deg,#10151C 0%,#0A0D12 100%);box-shadow:inset 0 1px 0 rgba(255,255,255,.065),0 1px 0 rgba(0,0,0,.6),0 14px 30px -14px rgba(0,0,0,.7)}
.lbl{font-size:12px;color:#7D838D}
.up{color:#3DDC97}.dn{color:#FF5C6C}.mut{color:#8B919B}
.chip{display:inline-flex;align-items:center;gap:6px;height:28px;padding:0 12px;border-radius:14px;border:1px solid #222731;font-size:12px;color:#B4BAC4}
.chip.cl{cursor:pointer}.chip.cl:hover{border-color:#3A4250}
h1,h2,h3{margin:0;font-weight:500}
@keyframes pulse{0%,100%{opacity:1}50%{opacity:.3}}
@keyframes glow{0%,100%{border-color:#2A4A75}50%{border-color:#5E9BE6}}
.live{width:7px;height:7px;border-radius:4px;background:#3DDC97;animation:pulse 2s infinite;flex:none}
.down{width:7px;height:7px;border-radius:4px;background:#FF5C6C;flex:none}
.tile{display:flex;flex-direction:column;gap:12px;padding:14px;border-radius:14px;border:1px solid #1B212A;background:linear-gradient(180deg,#10151C 0%,#0A0D12 100%);transition:transform .15s;box-shadow:inset 0 1px 0 rgba(255,255,255,.035),0 1px 0 rgba(0,0,0,.6);cursor:pointer}
.tile:hover{transform:translateY(-2px);border-color:#2A313C}
.tile.trade{animation:glow 2.4s infinite;background:linear-gradient(180deg,#132338 0%,#0B111A 100%)}
.tile.rest{background:transparent;opacity:.55;box-shadow:none}
.feed{display:flex;gap:14px;align-items:flex-start;padding:14px 0;border-top:1px solid #151920;font-size:14px;line-height:1.5}
table{border-collapse:collapse;width:100%}
th{font-weight:400;color:#7D838D;font-size:12px;text-align:right;padding:0 14px 12px;white-space:nowrap}
td{padding:12px 14px;border-top:1px solid #151920;text-align:right;white-space:nowrap;font-size:13px}
th:first-child,td:first-child{text-align:left}
th.s{cursor:pointer;user-select:none}th.s:hover{color:#B4BAC4}
.tt td:nth-child(1),.tt th:nth-child(1),.tt td:nth-child(2),.tt th:nth-child(2),.tt td:nth-child(3),.tt th:nth-child(3){text-align:left}
.ct td:nth-child(2),.ct th:nth-child(2),.ct td:nth-child(3),.ct th:nth-child(3),.ct td:nth-child(4),.ct th:nth-child(4){text-align:left}
.bt td:nth-child(1),.bt th:nth-child(1),.bt td:nth-child(4),.bt th:nth-child(4){text-align:left}
.coin{cursor:pointer;border-bottom:1px dashed #3A4250}.coin:hover{color:#8BB4E8}
a.lk{cursor:pointer}a.lk:hover{color:#8BB4E8}
.rng{display:flex;gap:4px}
.rng .rb{height:32px;padding:0 12px;border:none;border-radius:8px;background:transparent;color:#8B919B;font:inherit;font-size:13px;cursor:pointer}
.rng .rb.sel{background:#171C24;color:#E9ECF1}
.gradtext{background:linear-gradient(180deg,#FFFFFF 35%,#9AA4B2 100%);-webkit-background-clip:text;background-clip:text;color:transparent}
.pager{display:flex;gap:10px;align-items:center;margin:14px 2px 0;font-size:12px;color:#8B919B}
.pager button{height:28px;min-width:28px;padding:0 9px;border-radius:7px;border:1px solid #262C36;background:#10141A;color:#E9ECF1;font:inherit;font-size:13px;cursor:pointer;display:inline-flex;align-items:center;justify-content:center}
.pager button:hover:not(:disabled){border-color:#3A4250}
.pager button:disabled{opacity:.3;cursor:default}
.perpg{height:28px;background:#10141A;border:1px solid #262C36;color:#E9ECF1;border-radius:7px;font:inherit;font-size:12px;padding:0 6px 0 10px;cursor:pointer}
.perpg:hover{border-color:#3A4250}
.syslog{font-family:'Geist Mono',monospace;font-size:12px;line-height:1.75;color:#8B919B;background:#0A0D12;border:1px solid #1B212A;border-radius:12px;padding:14px 16px;max-height:300px;overflow:auto;white-space:pre-wrap;word-break:break-word}
.ecount{color:#FF5C6C}
.side{transition:max-width .18s ease,flex-basis .18s ease,padding .18s ease}
.sbhead{display:flex;align-items:center;justify-content:space-between;gap:8px;padding:0 2px 0 10px}
.sbtoggle{height:28px;width:28px;border-radius:8px;border:1px solid #1B212A;background:transparent;color:#6B717B;cursor:pointer;display:inline-flex;align-items:center;justify-content:center;flex:none}
.sbtoggle:hover{color:#B4BAC4;border-color:#2A313C}
.sbtoggle svg{transition:transform .18s ease}
.ni-ic{flex:none;color:#8B919B}
.ni.on .ni-ic{color:#E9ECF1}
.leg{transition:opacity .12s}.leg:hover{color:#E9ECF1}
.legclear{height:22px;padding:0 10px;border-radius:7px;border:1px solid #262C36;background:#10141A;color:#E9ECF1;font:inherit;font-size:11px;cursor:pointer}
.legclear:hover{border-color:#3A4250}
.seg2{display:flex;gap:2px;border:1px solid #1B212A;border-radius:9px;padding:2px;background:#0A0D12}
.vb{height:28px;width:36px;border:none;border-radius:7px;background:transparent;color:#8B919B;font:inherit;font-size:12px;cursor:pointer;display:inline-flex;align-items:center;justify-content:center}
.vb.sel{background:#171C24;color:#E9ECF1}
.vb:hover:not(.sel){color:#B4BAC4}
body.sbc .side{max-width:64px;flex-basis:64px;padding:20px 9px;gap:18px;align-items:center}
body.sbc .sb-text{display:none!important}
body.sbc .cap{display:none}
body.sbc .side>div,body.sbc .side>nav{width:100%}
body.sbc .fl,body.sbc .ni{justify-content:center;padding:10px 0;gap:0}
body.sbc .sbhead{flex-direction:column;gap:16px;align-items:center;padding:0}
body.sbc .wm{justify-content:center;padding:0}
body.sbc .sbtoggle{width:36px;height:30px;border-color:#232A33}
body.sbc .sbtoggle svg{transform:rotate(180deg)}
body.sbc .card{padding:12px 8px!important}
.lw{width:100%;height:300px}
.blk{display:flex;gap:10px;align-items:baseline;padding:10px 14px;border-radius:10px;background:#0F1319;font-size:13px}
.tag{font-family:'Geist Mono',monospace;font-size:10px;letter-spacing:.06em;color:#6B717B;width:74px;flex:none;text-transform:uppercase}
.statgrid{display:grid;grid-template-columns:repeat(auto-fit,minmax(170px,1fr));gap:1px;background:#1B212A;border:1px solid #1B212A;border-radius:16px;overflow:hidden}
.statcell{background:linear-gradient(180deg,#0F141B,#0A0D12);padding:22px 24px}
.ovl{position:fixed;inset:0;background:rgba(1,4,9,.72);display:none;align-items:center;justify-content:center;z-index:60}
.ovl .box{background:linear-gradient(180deg,#10151C,#0A0D12);border:1px solid #1B212A;border-radius:14px;padding:16px 18px;width:min(940px,94vw)}
.ovl .hd{display:flex;justify-content:space-between;align-items:center;gap:12px;margin-bottom:10px}
.ovl .x{height:30px;width:30px;border-radius:8px;border:1px solid #262C36;background:#10141A;color:#E9ECF1;cursor:pointer}
#cchart{width:100%;height:440px}
</style></head><body>
<div id="root" class="app"><div style="flex:1;display:flex;align-items:center;justify-content:center;color:#6B717B">Loading the fleet…</div></div>

<div class="ovl" id="covl"><div class="box">
  <div class="hd"><b id="ctitle" class="n"></b>
    <span class="rng" id="civ"></span>
    <button class="x" onclick="document.getElementById('covl').style.display='none'">✕</button></div>
  <div id="cchart"></div>
  <div class="lbl" style="margin-top:8px">scroll left to load older history · drag to pan · wheel to zoom</div>
</div></div>

<script src="/lw.js"></script>
<script>
const START=10000;
const esc=s=>String(s).replace(/[&<>"]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]));
function usd(n,s){ if(n==null||isNaN(n))return '–'; const a=Math.abs(n).toLocaleString('en-US',{minimumFractionDigits:2,maximumFractionDigits:2}); return (n<0?'−':(s?'+':''))+'$'+a; }
function dol(n){ return '$'+Number(n).toLocaleString('en-US',{minimumFractionDigits:2,maximumFractionDigits:2}); }
function pct(n,s){ if(n==null||isNaN(n))return '–'; return (n<0?'−':(s?'+':''))+Math.abs(n).toFixed(Math.abs(n)<10?2:1)+'%'; }
function px(x){ if(x==null||x===''||isNaN(x))return '–'; const a=Math.abs(x); const d=a>=100?2:a>=1?3:a>=0.01?4:6; return (+x).toFixed(d).replace(/\.?0+$/,m=>m.includes('.')?'':m); }
function clock(ms){ const d=new Date(ms); return String(d.getHours()).padStart(2,'0')+':'+String(d.getMinutes()).padStart(2,'0'); }
function dstr(ms){ return new Date(ms).toLocaleDateString('en-US',{month:'short',day:'numeric'}); }
function held(ms){ const m=Math.round(ms/60000); if(m<60)return m+'m'; const h=Math.floor(m/60),mm=m%60; if(h<48)return h+'h'+(mm?' '+String(mm).padStart(2,'0')+'m':''); return Math.round(h/24)+'d'; }
function dur(ms){ const m=Math.max(0,Math.round(ms/60000)); const h=Math.floor(m/60),mm=m%60; return (h?h+'h ':'')+String(mm).padStart(2,'0')+'m'; }
const REASON={sl:'Stop loss',time:'Time limit',tp:'Take profit',manual:'Closed manually',trail:'Trailing stop'};
const COLORS=["#58a6ff","#3fb950","#f85149","#d29922","#bc8cff","#39c5cf","#ff7b72","#7ee787","#ffa657","#79c0ff","#d2a8ff","#56d4dd"];
const DIRLBL={short:'Short',long:'Long',both:'Two-sided'};
const TZ=Intl.DateTimeFormat().resolvedOptions().timeZone;
const lt=t=>Math.floor(t/1000)-new Date(t).getTimezoneOffset()*60;  // LW shows UTC; feed local-shifted
function identicon(seed,size){ let h=7; for(const c of seed) h=(h*31+c.charCodeAt(0))>>>0; let d=''; const u=size/5; for(let y=0;y<5;y++)for(let x=0;x<3;x++){ h=(h*1103515245+12345)>>>0; if((h>>>16)&1){ d+='M'+x*u+' '+y*u+'h'+u+'v'+u+'h-'+u+'z'; if(x<2)d+='M'+(4-x)*u+' '+y*u+'h'+u+'v'+u+'h-'+u+'z'; } } return d||'M8 8h4v4h-4z'; }

let DATA=null, CUR={route:null,name:null}, RANGE=30, BRANGE=null;
let LSEL=new Set(), VSEL=null;   // legend solo/add selection (fleet chart)
let VIEW='cards';                // fleet view: 'cards' tiles | 'rows' table
const SORT={}, PG={};

function botStatus(v){
  if(v.kill) return {txt:'Paused · loss limit', cls:'rest', color:'#6B717B', shade:'#3A4250'};
  if(v.open && v.open.length){ return {txt:'In a trade · '+v.open.map(o=>o.ticker).join(', '), cls:'trade'}; }
  return {txt:'Watching', cls:''};
}
function vcolor(name){ const i=DATA?DATA.variants.findIndex(v=>v.name===name):0; return COLORS[(i<0?0:i)%COLORS.length]; }
const mkeq=v=>v.equity+v.open.reduce((a,p)=>a+(p.upnl||0),0);  // marked-to-market equity
function legSel(n){ if(LSEL.has(n))LSEL.delete(n); else if(!LSEL.size)LSEL=new Set([n]); else LSEL.add(n); VSEL=LSEL.size===1?[...LSEL][0]:null; paint(); }
function legClear(){ LSEL=new Set(); VSEL=null; paint(); }

// ---- generic sortable + paginated table -------------------------------
function tbl(key, klass, cols, rows){
  const S=SORT[key]||(SORT[key]={col:null,dir:-1});
  let r=rows.slice();
  if(S.col){ const c=cols.find(x=>x.k===S.col);
    r.sort((a,b)=>{ let x=c.val(a),y=c.val(b);
      if(x==null&&y==null)return 0; if(x==null)return 1; if(y==null)return -1;
      if(typeof x==='string')return x.localeCompare(y)*S.dir; return (x-y)*S.dir; }); }
  const P=PG[key]||(PG[key]={p:0,n:10}); const np=Math.max(1,Math.ceil(r.length/P.n));
  if(P.p>=np)P.p=np-1; if(P.p<0)P.p=0;
  const page=r.slice(P.p*P.n,(P.p+1)*P.n);
  const arr=k=>S.col===k?(S.dir>0?' ▲':' ▼'):'';
  const head='<thead><tr>'+cols.map(c=>`<th class="${c.s?'s':''}" ${c.s?`data-sort="${c.k}" data-tk="${key}"`:''} style="${c.align==='left'?'text-align:left':''}">${c.label}${c.s?arr(c.k):''}</th>`).join('')+'</tr></thead>';
  const body='<tbody>'+(page.length?page.map(x=>'<tr>'+cols.map(c=>c.cell(x)).join('')+'</tr>').join(''):`<tr><td colspan="${cols.length}" class="mut" style="text-align:center;padding:28px">none</td></tr>`)+'</tbody>';
  let pg='';
  if(r.length>10){
    pg=`<div class="pager"><span>${r.length} rows</span><span style="flex:1"></span>`+
      `<button data-pg="${key}" data-d="-1" ${P.p===0?'disabled':''} aria-label="previous page">‹</button>`+
      `<span>Page ${P.p+1} of ${np}</span>`+
      `<button data-pg="${key}" data-d="1" ${P.p>=np-1?'disabled':''} aria-label="next page">›</button>`+
      `<select class="perpg" data-per="${key}" aria-label="rows per page">`+
      [10,25,50,100].map(n=>`<option value="${n}" ${P.n===n?'selected':''}>${n} / page</option>`).join('')+`</select></div>`;
  }
  return `<div style="overflow-x:auto"><table class="${klass}">${head}${body}</table></div>${pg}`;
}
const coinCell=o=>`<a class="coin n" data-sym="${esc(DATA.symbols[o.ticker]||'')}" data-tsig="${o.t_sig}" data-entry="${o.entry}" data-stop="${o.stop||''}" data-tp="${o.tp??''}" data-exit="${o.exit_t||''}" data-kind="${o.kind||''}" data-side="${o.side||''}" data-tk="${esc(o.ticker)}" data-variant="${esc(o.variant||'')}">${esc(o.ticker)} <span style="opacity:.6">📈</span></a>`;
const botLink=n=>`<a class="lk" data-bot="${esc(n)}">${esc(n)}</a>`;

// ---- sidebar ----------------------------------------------------------
function sidebar(){
  const v=DATA.variants, N=v.length, budget=N*START;
  const fleetRet=DATA.hero.fleet_pnl/budget*100;
  const liveOk=DATA.running&&!DATA.paused;
  const fleetOn=CUR.route==='fleet';
  const age=DATA.state_age_s;
  const ago=age==null?'—':(age<90?age+'s ago':age<5400?Math.round(age/60)+'m ago':age<172800?Math.round(age/3600)+'h ago':Math.round(age/86400)+'d ago');
  const statusTxt=liveOk?'Fleet is live':(DATA.paused?'Fleet paused':'Fleet is down');
  const IC={
    fleet:'<svg class="ni-ic" width="17" height="17" viewBox="0 0 16 16" fill="none"><rect x="1.5" y="1.5" width="5" height="5" rx="1" stroke="currentColor" stroke-width="1.3"/><rect x="9.5" y="1.5" width="5" height="5" rx="1" stroke="currentColor" stroke-width="1.3"/><rect x="1.5" y="9.5" width="5" height="5" rx="1" stroke="currentColor" stroke-width="1.3"/><rect x="9.5" y="9.5" width="5" height="5" rx="1" stroke="currentColor" stroke-width="1.3"/></svg>',
    research:'<svg class="ni-ic" width="17" height="17" viewBox="0 0 16 16" fill="none"><path d="M6 1.8v4L2.6 11.4A1.6 1.6 0 0 0 4 13.9h8a1.6 1.6 0 0 0 1.4-2.5L10 5.8v-4" stroke="currentColor" stroke-width="1.3"/><path d="M5 1.8h6M4.6 9h6.8" stroke="currentColor" stroke-width="1.3"/></svg>',
    leaderboard:'<svg class="ni-ic" width="17" height="17" viewBox="0 0 16 16" fill="none"><path d="M2 14h12" stroke="currentColor" stroke-width="1.3"/><rect x="2.8" y="7" width="2.6" height="5" rx=".5" fill="currentColor"/><rect x="6.7" y="3.5" width="2.6" height="8.5" rx=".5" fill="currentColor"/><rect x="10.6" y="9" width="2.6" height="3" rx=".5" fill="currentColor"/></svg>',
    settings:'<svg class="ni-ic" width="17" height="17" viewBox="0 0 16 16" fill="none"><circle cx="8" cy="8" r="2.2" stroke="currentColor" stroke-width="1.3"/><path d="M8 1.2v2M8 12.8v2M1.2 8h2M12.8 8h2M3.2 3.2l1.4 1.4M11.4 11.4l1.4 1.4M12.8 3.2l-1.4 1.4M4.6 11.4 3.2 12.8" stroke="currentColor" stroke-width="1.15"/></svg>'};
  return `<aside class="side">
    <div class="sbhead">
      <div class="wm" style="display:flex;align-items:center;gap:9px">
        <svg width="23" height="23" viewBox="0 0 200 200" fill="none" aria-hidden="true" style="flex:none;filter:drop-shadow(0 2px 6px rgba(58,129,215,.4))">
          <path d="M170 30 L30 95 L95 125 L170 30 Z" fill="#E9ECF1"></path>
          <path d="M170 30 L107 131 L122 170 L137 137 L170 30 Z" fill="#5E8FD8"></path></svg>
        <span class="sb-text">paper fleet</span></div>
      <button class="sbtoggle" data-sbtoggle="1" aria-label="toggle sidebar" title="Collapse / expand"><svg width="15" height="15" viewBox="0 0 16 16" fill="none"><path d="M10 3 L5 8 L10 13" stroke="currentColor" stroke-width="1.6"/></svg></button>
    </div>
    <div><div class="cap sb-text">YOUR FLEETS</div>
      <div class="fl ${fleetOn?'on':''}" data-home="1" title="Paper Fleet"><span class="sq" style="background:#3a81d7"></span>
        <span class="sb-text" style="flex:1;min-width:0"><span style="display:block;font-size:14px">Paper Fleet</span>
        <span class="n" style="display:block;font-size:11px;color:#6B717B;margin-top:2px">${N} bots</span></span>
        <span class="sb-text n ${fleetRet>=0?'up':'dn'}" style="font-size:12px">${pct(fleetRet,true)}</span></div>
    </div>
    <nav style="display:flex;flex-direction:column;gap:2px"><div class="cap sb-text">PAPER FLEET</div>
      <a class="ni ${fleetOn?'on':''}" data-home="1" title="Fleet">${IC.fleet}<span class="sb-text">Fleet</span></a>
      <a class="ni" style="opacity:.5" title="Research (coming soon)">${IC.research}<span class="sb-text">Research</span></a>
      <a class="ni" style="opacity:.5" title="Leaderboard (coming soon)">${IC.leaderboard}<span class="sb-text">Leaderboard</span></a>
      <a class="ni" style="opacity:.5" title="Settings (coming soon)">${IC.settings}<span class="sb-text">Settings</span></a>
    </nav>
    <div style="flex:1"></div>
    <div class="card" style="padding:14px" title="${statusTxt} · updated ${ago}">
      <div style="display:flex;align-items:center;gap:8px;font-size:12px;color:#B4BAC4">
        <span class="${liveOk?'live':'down'}" style="flex:none"></span><span class="sb-text">${statusTxt}</span></div>
      <div class="lbl sb-text" style="margin-top:6px">Updated ${ago}</div>
    </div>
  </aside>`;
}
function refreshSidebar(){ const sb=document.querySelector('.side'); if(sb) sb.outerHTML=sidebar(); }

// ---- fleet view -------------------------------------------------------
function fleetSkeleton(){
  document.getElementById('root').innerHTML=sidebar()+`<div class="main">
    <header class="top" id="f-top"></header>
    <div style="padding:0 40px">
      <section id="f-hero" style="display:flex;flex-wrap:wrap;gap:40px;align-items:flex-end;padding:44px 0 40px;border-bottom:1px solid #151920"></section>
      <section style="padding-top:40px">
        <div style="display:flex;justify-content:space-between;align-items:center;flex-wrap:wrap;gap:12px">
          <h2 style="font-size:18px">The fleet <span class="mut" id="f-fleetcount" style="font-weight:400"></span></h2>
          <div style="display:flex;align-items:center;gap:18px;flex-wrap:wrap">
            <div id="f-legendcount" style="display:flex;gap:16px;font-size:12px;color:#8B919B;flex-wrap:wrap"></div>
            <div class="seg2" id="f-view"></div></div></div>
        <div id="f-fleetbody" style="margin-top:18px"></div>
      </section>
      <section style="padding-top:48px">
        <div style="display:flex;justify-content:space-between;align-items:center;flex-wrap:wrap;gap:16px">
          <h2 style="font-size:18px">Performance</h2>
          <div class="rng" id="f-range"></div></div>
        <div class="card" style="margin-top:18px;padding:18px 18px 14px">
          <div class="lw" id="perfchart"></div>
          <div id="perflegend" style="display:flex;gap:16px;flex-wrap:wrap;margin-top:12px;font-size:12px;color:#8B919B"></div></div>
      </section>
      <section style="padding-top:48px">
        <div style="margin-bottom:16px"><h2 style="font-size:18px" id="f-opentitle">Open trades</h2></div>
        <div id="f-open"></div>
      </section>
      <section style="padding-top:48px">
        <div style="margin-bottom:16px"><h2 style="font-size:18px" id="f-closedtitle">Closed trades</h2></div>
        <div id="f-closed"></div>
      </section>
      <section style="padding-top:48px">
        <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:12px"><h2 style="font-size:18px">System log</h2><span id="f-logmeta" class="lbl"></span></div>
        <div class="syslog" id="f-log"></div>
      </section>
    </div></div>`;
}

function paintFleet(){
  const d=DATA, v=d.variants, N=v.length, budget=N*START;
  const fleetPnl=d.hero.fleet_pnl, now=d.now;
  const dayStart=new Date(now); dayStart.setHours(0,0,0,0);
  const todayPnl=d.trades.filter(t=>t.exit_t>=dayStart.getTime()).reduce((a,t)=>a+t.pnl,0);
  const open=d.positions, openUnreal=d.hero.unreal;
  const top=[...v].sort((a,b)=>b.ret-a.ret)[0];
  const liveOk=d.running&&!d.paused;
  const log=d.log||[], errs=log.filter(l=>/error|exception|traceback|kill/i.test(l));
  const clearChip=VSEL?` <span class="chip cl" data-legclear="1" style="height:22px;cursor:pointer">${esc(VSEL)} ✕</span>`:'';

  document.getElementById('f-top').innerHTML=`
    <div style="display:flex;align-items:center;gap:14px;flex-wrap:wrap">
      <span class="sq" style="width:12px;height:12px;background:#3a81d7"></span>
      <h1 style="font-size:20px">Paper Fleet</h1>
      <span class="chip">Crypto · $10k each</span>
      <span class="chip"><span class="${liveOk?'live':'down'}"></span>${liveOk?'Live · checks every 15 min':(d.paused?'Paused':'Offline')}</span>
      ${d._source==='local-stale'?'<span class="chip ecount">⚠ upstream down · local copy</span>':d._source==='local'?'<span class="chip">local data</span>':''}
      ${errs.length?`<span class="chip ecount">⚠ ${errs.length} in log</span>`:''}</div>`;

  const h=d.hero, totalProfit=fleetPnl+openUnreal;   // marked-to-market: moves with live prices
  document.getElementById('f-hero').innerHTML=`
    <div style="flex:1 1 380px">
      <div class="lbl" style="font-size:13px">Fleet total profit</div>
      <div class="n gradtext" style="font-size:64px;letter-spacing:-0.045em;line-height:1.05;margin-top:12px">${usd(totalProfit,true)}</div>
      <div style="display:flex;gap:16px;margin-top:12px;flex-wrap:wrap;font-size:14px">
        <span class="n ${todayPnl>=0?'up':'dn'}">${usd(todayPnl,true)} today</span>
        <span class="mut">${h.closed} closed trades · since ${dstr(d.start)}</span></div></div>
    <div style="flex:2 1 460px;display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:12px">
      <div class="card" style="padding:18px;cursor:pointer" data-bot="${esc(top.name)}"><div class="lbl">Top bot</div>
        <div style="font-size:18px;margin-top:8px">${esc(top.name)}</div>
        <div class="n ${top.ret>=0?'up':'dn'}" style="font-size:13px;margin-top:4px">${pct(top.ret,true)} · ${dol(top.equity)}</div></div>
      <div class="card" style="padding:18px"><div class="lbl">Open · unrealized</div>
        <div class="n ${openUnreal>=0?'up':'dn'}" style="font-size:26px;margin-top:8px">${usd(openUnreal,true)}</div>
        <div class="lbl" style="margin-top:2px">${open.length} open position${open.length===1?'':'s'}</div></div>
      <div class="card" style="padding:18px"><div class="lbl">Last 7 days</div>
        <div class="n ${h.week_pnl>=0?'up':'dn'}" style="font-size:26px;margin-top:8px">${usd(h.week_pnl,true)}</div>
        <div class="lbl" style="margin-top:2px">closed P&L, all bots</div></div></div>`;

  const bots=[...v].sort((a,b)=>b.ret-a.ret).map(b=>({v:b,st:botStatus(b)}));
  const inTrade=bots.filter(b=>b.st.cls==='trade').length, paused=bots.filter(b=>b.st.cls==='rest').length;
  document.getElementById('f-legendcount').innerHTML=`
    <span style="display:flex;align-items:center;gap:6px"><span style="width:8px;height:8px;border-radius:4px;background:#3a81d7"></span>Watching · ${N-inTrade-paused}</span>
    <span style="display:flex;align-items:center;gap:6px"><span style="width:8px;height:8px;border-radius:4px;background:#8BB4E8;animation:pulse 1.4s infinite"></span>In a trade · ${inTrade}</span>
    <span style="display:flex;align-items:center;gap:6px"><span style="width:8px;height:8px;border-radius:4px;background:#2A313C"></span>Paused · ${paused}</span>`;
  document.getElementById('f-fleetcount').innerHTML=`(${N})${clearChip}`;
  const ICV={cards:'<svg width="15" height="15" viewBox="0 0 16 16" fill="none"><rect x="1.5" y="1.5" width="5.5" height="5.5" rx="1.3" fill="currentColor"></rect><rect x="9" y="1.5" width="5.5" height="5.5" rx="1.3" fill="currentColor"></rect><rect x="1.5" y="9" width="5.5" height="5.5" rx="1.3" fill="currentColor"></rect><rect x="9" y="9" width="5.5" height="5.5" rx="1.3" fill="currentColor"></rect></svg>',rows:'<svg width="15" height="15" viewBox="0 0 16 16" fill="none"><rect x="1.5" y="2.6" width="13" height="2.4" rx="1.2" fill="currentColor"></rect><rect x="1.5" y="6.8" width="13" height="2.4" rx="1.2" fill="currentColor"></rect><rect x="1.5" y="11" width="13" height="2.4" rx="1.2" fill="currentColor"></rect></svg>'};
  document.getElementById('f-view').innerHTML=[['cards','Cards'],['rows','Rows']].map(([vv,l])=>`<button class="vb ${VIEW===vv?'sel':''}" data-view="${vv}" title="${l} view" aria-label="${l} view">${ICV[vv]}</button>`).join('');
  const shownBots=VSEL?bots.filter(b=>b.v.name===VSEL):bots;
  const shades=['#3a81d7','#6FA2E8','#A9C8F2','#5E8FD8','#8BB4E8'];
  if(VIEW==='rows'){
    document.getElementById('f-fleetbody').innerHTML=tbl('fvar','vt',[
      {k:'name',label:'Bot',s:1,val:x=>x.name,cell:x=>`<td>${botLink(x.name)}${x.kill?' <span class="dn" style="font-size:11px">KILL</span>':''}</td>`},
      {k:'group',label:'Direction',s:1,align:'left',val:x=>x.group,cell:x=>`<td class="mut" style="text-align:left">${esc(DIRLBL[x.group]||x.group||'–')}</td>`},
      {k:'equity',label:'Equity',s:1,val:x=>x.equity,cell:x=>`<td class="n">${dol(x.equity)}</td>`},
      {k:'ret',label:'Return',s:1,val:x=>x.ret,cell:x=>`<td class="n ${x.ret>=0?'up':'dn'}">${pct(x.ret,true)}</td>`},
      {k:'open',label:'Open',s:1,val:x=>x.open.length,cell:x=>`<td class="n mut">${x.open.length}</td>`},
      {k:'closed',label:'Closed',s:1,val:x=>x.closed,cell:x=>`<td class="n mut">${x.closed}</td>`},
      {k:'win',label:'Win',s:1,val:x=>x.win,cell:x=>`<td class="n">${x.win==null?'–':x.win+'%'}</td>`},
      {k:'avg',label:'Avg net',s:1,val:x=>x.avg,cell:x=>`<td class="n ${(x.avg||0)>=0?'up':'dn'}">${pct(x.avg,true)}</td>`},
      {k:'bt',label:'Backtest',s:1,val:x=>x.bt,cell:x=>`<td class="n mut">${pct(x.bt)}</td>`},
    ], shownBots.map(b=>b.v));
  }else{
    document.getElementById('f-fleetbody').innerHTML=`<div class="grid" style="display:grid;grid-template-columns:repeat(auto-fill,minmax(150px,1fr));gap:10px">`+
      shownBots.map((b,i)=>{ const pos=b.v.ret>=0, st=b.st, shade=st.shade||shades[i%5], col=st.color||(pos?'#3DDC97':'#FF5C6C');
        return `<div class="tile${st.cls?' '+st.cls:''}" data-bot="${esc(b.v.name)}" title="${esc(b.v.params||'')}">
          <span style="display:flex;justify-content:space-between;align-items:flex-start">
            <svg width="30" height="30" viewBox="0 0 30 30"><rect width="30" height="30" rx="8" fill="#12161D"></rect><path d="${identicon(b.v.name,20)}" fill="${shade}" transform="translate(5 5)"></path></svg>
            <span class="n" style="font-size:13px;color:${col}">${pct(b.v.ret,true)}</span></span>
          <span><span style="display:block;font-size:14px;font-weight:500">${esc(b.v.name)}</span>
            <span style="display:block;font-size:12px;color:#7D838D;margin-top:3px">${esc(st.txt)}</span></span></div>`; }).join('')+`</div>`;
  }

  renderRange('f-range', RANGE, setFleetRange);
  drawPerf();

  const fopen=VSEL?open.filter(o=>o.variant===VSEL):open;
  const fopenUnreal=fopen.reduce((a,o)=>a+(o.upnl||0),0);
  document.getElementById('f-opentitle').innerHTML=`Open trades <span class="n mut" style="font-size:14px;font-weight:400;margin-left:4px">${fopen.length}</span> <span class="n ${fopenUnreal>=0?'up':'dn'}" style="font-size:14px;font-weight:400;margin-left:8px">${usd(fopenUnreal,true)}</span>${clearChip}`;
  document.getElementById('f-open').innerHTML=tbl('fopen','tt',[
    {k:'variant',label:'Bot',s:1,val:o=>o.variant,cell:o=>`<td>${botLink(o.variant)}</td>`},
    {k:'ticker',label:'Coin',s:1,val:o=>o.ticker,cell:o=>`<td style="font-weight:500">${coinCell(o)}</td>`},
    {k:'side',label:'Side',s:1,val:o=>o.side,cell:o=>`<td class="${o.side==='short'?'dn':'up'}">${o.side==='short'?'Short':'Long'}</td>`},
    {k:'entry',label:'Entry',s:1,val:o=>o.entry,cell:o=>`<td class="n">${px(o.entry)}</td>`},
    {k:'px',label:'Now',s:1,val:o=>o.px,cell:o=>`<td class="n">${px(o.px)}</td>`},
    {k:'upnl',label:'P&L',s:1,val:o=>o.upnl,cell:o=>`<td class="n ${(o.upnl||0)>=0?'up':'dn'}">${usd(o.upnl,true)}</td>`},
    {k:'upct',label:'Net',s:1,val:o=>o.upct,cell:o=>`<td class="n ${(o.upct||0)>=0?'up':'dn'}">${pct(o.upct!=null?o.upct*100:null,true)}</td>`},
    {k:'stop',label:'Stop',s:1,val:o=>o.stop,cell:o=>`<td class="n mut">${o.stop?px(o.stop):'–'}</td>`},
    {k:'tp',label:'Target',s:0,val:o=>o.tp,cell:o=>`<td class="n">${o.tp!=null?px(o.tp):'–'}</td>`},
    {k:'room',label:'Room',s:1,val:o=>o.room,cell:o=>`<td class="n mut">${o.stop&&o.room!=null?pct(o.room*100):'–'}</td>`},
    {k:'exits_at',label:'Time exit',s:1,val:o=>o.exits_at,cell:o=>{const l=o.exits_at-now;return `<td class="n mut">${l>0?dur(l):'due'}</td>`;}},
    {k:'notional',label:'Size',s:1,val:o=>o.notional,cell:o=>`<td class="n mut">${usd(o.notional)}</td>`},
  ], fopen);

  const tr=d.trades;
  document.getElementById('f-closedtitle').innerHTML=`Closed trades <span class="n mut" style="font-size:14px;font-weight:400;margin-left:4px">${VSEL?tr.filter(t=>t.variant===VSEL).length:d.hero.closed}</span>${clearChip}`;
  document.getElementById('f-closed').innerHTML=tbl('fclosed','ct',[
    {k:'exit_t',label:'Closed',s:1,val:t=>t.exit_t,cell:t=>`<td class="n mut">${clock(t.exit_t)}</td>`},
    {k:'variant',label:'Bot',s:1,val:t=>t.variant,cell:t=>`<td>${botLink(t.variant)}</td>`},
    {k:'ticker',label:'Coin',s:1,val:t=>t.ticker,cell:t=>`<td style="font-weight:500">${coinCell(t)}</td>`},
    {k:'kind',label:'Exit reason',s:1,val:t=>t.kind,cell:t=>`<td class="mut">${esc(REASON[t.kind]||t.kind)}</td>`},
    {k:'net',label:'Net',s:1,val:t=>t.net,cell:t=>`<td class="n ${t.pnl>=0?'up':'dn'}">${pct(t.net*100,true)}</td>`},
    {k:'pnl',label:'P&L',s:1,val:t=>t.pnl,cell:t=>`<td class="n ${t.pnl>=0?'up':'dn'}">${usd(t.pnl,true)}</td>`},
    {k:'notional',label:'Size',s:1,val:t=>t.notional,cell:t=>`<td class="n mut">${usd(t.notional)}</td>`},
    {k:'held',label:'Held',s:1,val:t=>t.exit_t-t.t_sig,cell:t=>`<td class="n mut">${held(t.exit_t-t.t_sig)}</td>`},
  ], VSEL?tr.filter(t=>t.variant===VSEL):tr);

  document.getElementById('f-log').textContent=log.length?log.join('\n'):'(no recent log lines)';
  document.getElementById('f-logmeta').textContent=`last ${log.length} lines · times in ${TZ}`;
}

// ---- equity charts (lightweight-charts) -------------------------------
const LWOPTS={layout:{background:{color:'transparent'},textColor:'#7D838D',fontSize:11,fontFamily:'Geist Mono, monospace'},
  grid:{vertLines:{color:'#141920'},horzLines:{color:'#141920'}},
  timeScale:{timeVisible:true,secondsVisible:false,borderColor:'#1B212A'},
  rightPriceScale:{borderColor:'#1B212A'},
  crosshair:{mode:LightweightCharts.CrosshairMode.Normal},autoSize:true};
let perfChart=null, perfMap={}, perfDrew=false;
let botChart=null, botAvg=null, botLine=null, botDrew=false;
function clearCharts(){ if(perfChart){perfChart.remove();perfChart=null;perfMap={};perfDrew=false;}
  if(botChart){botChart.remove();botChart=null;botAvg=null;botLine=null;botDrew=false;} }
function dedup(curve){ let last=-1; return curve.filter(c=>{const t=lt(c[0]); if(t<=last)return false; last=t; return true;}).map(c=>({time:lt(c[0]),value:c[1]})); }
function renderRange(id,cur,fn){ const el=document.getElementById(id); if(!el)return;
  el.innerHTML=[['1D',1],['1W',7],['1M',30],['All',null]].map(([l,dd])=>`<button class="rb ${cur===dd?'sel':''}" data-days="${dd}">${l}</button>`).join('');
  el._fn=fn; }
function applyRange(chart,days){ if(!chart)return; if(days==null)chart.timeScale().fitContent();
  else{const now=lt(Date.now());chart.timeScale().setVisibleRange({from:now-days*86400,to:now});} }
function setFleetRange(days){ RANGE=days; applyRange(perfChart,days); renderRange('f-range',RANGE,setFleetRange); }
function setBotRange(days){ BRANGE=days; applyRange(botChart,days); renderRange('b-range',BRANGE,setBotRange); }

function drawPerf(){
  const el=document.getElementById('perfchart'); if(!el)return;
  if(!perfChart){ perfChart=LightweightCharts.createChart(el,LWOPTS);
    DATA.variants.forEach(v=>{ perfMap[v.name]=perfChart.addLineSeries({lineWidth:2,priceLineVisible:false,lastValueVisible:false,crosshairMarkerVisible:true}); }); }
  // every variant its own colour (12-colour cycle, like the original); when a
  // legend solo/selection is active, only the selected lines are drawn.
  DATA.variants.forEach((v,i)=>{ const s=perfMap[v.name]; if(!s)return; const shown=!LSEL.size||LSEL.has(v.name);
    s.applyOptions({color:COLORS[i%COLORS.length],lineWidth:(LSEL.size&&LSEL.has(v.name))?2.5:2,title:v.name,lastValueVisible:false});
    s.setData(shown?dedup(v.curve):[]); });
  if(!perfDrew){ applyRange(perfChart,RANGE); perfDrew=true; }
  // full clickable legend: every variant, sorted by marked equity. first click
  // solos, further clicks add; a solo also filters the tables below.
  const sorted=[...DATA.variants].sort((a,b)=>mkeq(b)-mkeq(a));
  document.getElementById('perflegend').innerHTML=
    sorted.map(v=>{ const dim=LSEL.size&&!LSEL.has(v.name), sel=LSEL.has(v.name);
      return `<span class="leg" data-leg="${esc(v.name)}" title="click: show only this · click more: add · click again: remove" style="display:inline-flex;align-items:center;gap:6px;cursor:pointer;${dim?'opacity:.35;':''}"><i style="width:13px;height:3px;border-radius:2px;background:${vcolor(v.name)};flex:none"></i>${sel?'<b>'+esc(v.name)+'</b>':esc(v.name)} <span class="n" style="color:#B4BAC4">${mkeq(v).toFixed(0)}</span></span>`; }).join('')
    +(LSEL.size?`<button class="legclear" data-legclear="1">✕ clear (${LSEL.size})</button>`:'');
}

function curveAt(curve,t){ if(!curve.length)return START; if(t<=curve[0][0])return curve[0][1];
  let lo=0,hi=curve.length-1,ans=curve[0][1]; while(lo<=hi){const m=(lo+hi)>>1; if(curve[m][0]<=t){ans=curve[m][1];lo=m+1;}else hi=m-1;} return ans; }
function drawBot(v){
  const el=document.getElementById('botchart'); if(!el)return;
  if(!botChart){ botChart=LightweightCharts.createChart(el,LWOPTS);
    botAvg=botChart.addLineSeries({color:'#4B515A',lineWidth:1.5,priceLineVisible:false,lastValueVisible:false,title:'fleet avg'});
    botLine=botChart.addLineSeries({color:'#3a81d7',lineWidth:2.25,priceLineVisible:false,lastValueVisible:true,title:v.name}); }
  const ts=v.curve.map(c=>c[0]);
  botAvg.setData(ts.map(t=>({time:lt(t),value:+( DATA.variants.reduce((a,x)=>a+curveAt(x.curve,t),0)/DATA.variants.length ).toFixed(2)})).filter((p,i,a)=>i===0||p.time>a[i-1].time));
  botLine.setData(dedup(v.curve));
  const mk=DATA.trades.filter(t=>t.variant===v.name).map(t=>({time:lt(t.exit_t),position:'inBar',color:t.pnl>=0?'#3DDC97':'#FF5C6C',shape:'circle'}))
    .filter(m=>v.curve.length&&m.time>=lt(v.curve[0][0])).sort((a,b)=>a.time-b.time);
  const seen=new Set(); botLine.setMarkers(mk.filter(m=>{if(seen.has(m.time))return false;seen.add(m.time);return true;}));
  if(!botDrew){ applyRange(botChart,BRANGE); botDrew=true; }
}

// ---- bot profile view -------------------------------------------------
function botSkeleton(name){
  document.getElementById('root').innerHTML=sidebar()+`<div class="main">
    <div style="padding:18px 40px;border-bottom:1px solid #151920;font-size:14px"><a class="lk" data-home="1" style="display:inline-flex;align-items:center;gap:7px;color:#8B919B"><svg width="16" height="16" viewBox="0 0 16 16" fill="none"><path d="M9.5 3.5 5 8l4.5 4.5" stroke="currentColor" stroke-width="1.5"></path></svg>Fleet</a></div>
    <div style="padding:0 40px"><div id="b-main">
      <section id="b-head" style="display:flex;flex-wrap:wrap;gap:32px;align-items:center;padding:40px 0 36px"></section>
      <section id="b-stats" class="statgrid"></section>
      <section id="b-cmp" class="card" style="margin-top:24px;padding:20px 24px;display:flex;flex-wrap:wrap;gap:28px;align-items:center"></section>
      <section style="display:flex;flex-wrap:wrap;gap:24px;padding-top:32px;align-items:flex-start">
        <div style="flex:999 1 520px;min-width:0;display:flex;flex-direction:column;gap:28px">
          <div class="card" style="padding:20px 22px;display:flex;flex-direction:column">
            <div style="display:flex;justify-content:space-between;align-items:center;flex-wrap:wrap;gap:8px">
              <h2 style="font-size:16px">Equity</h2>
              <div style="display:flex;align-items:center;gap:16px;flex-wrap:wrap">
                <div style="display:flex;gap:16px;font-size:12px" class="mut"><span style="display:flex;align-items:center;gap:8px"><span style="width:14px;height:2px;background:#3a81d7"></span>${esc(name)}</span><span style="display:flex;align-items:center;gap:8px"><span style="width:14px;height:2px;background:#4B515A"></span>Fleet average</span></div>
                <div class="rng" id="b-range"></div></div></div>
            <div class="lw" id="botchart" style="height:300px;margin-top:14px"></div></div>
          <div>
            <div style="margin-bottom:14px"><h2 style="font-size:16px">Trades <span class="n mut" id="b-trcount" style="font-size:13px;font-weight:400;margin-left:4px"></span></h2></div>
            <div id="b-trades"></div>
          </div>
        </div>
        <div class="card" id="b-strategy" style="flex:1 1 300px;min-width:0;padding:22px;display:flex;flex-direction:column;gap:12px"></div>
      </section>
    </div></div></div>`;
  renderRange('b-range',BRANGE,setBotRange);
}
function stat(l,val,c,sub){ return `<div class="statcell"><div class="lbl">${l}</div><div class="n ${c||''}" style="font-size:26px;margin-top:8px">${val}</div><div class="lbl" style="margin-top:4px">${sub||''}</div></div>`; }

function paintBot(name){
  const v=DATA.variants.find(x=>x.name===name);
  if(!v){ document.getElementById('b-main').innerHTML=`<div style="padding:60px 0" class="mut">No bot named “${esc(name)}”. <a class="lk" data-home="1" style="color:#8BB4E8">Back to the fleet →</a></div>`; return; }
  const head=document.getElementById('b-head'); if(!head)return;
  const st=botStatus(v), pos=v.ret>=0, openN=v.open.length;
  const wins=v.win!=null?Math.round(v.win/100*v.closed):null, losses=wins!=null?v.closed-wins:null;
  const tradesSub=wins!=null?`${wins} wins · ${losses} losses · ${openN} open`:(openN?`${openN} open`:'no trades yet');
  const trs=DATA.trades.filter(t=>t.variant===name).slice().sort((a,b)=>a.exit_t-b.exit_t);
  let best=0,run=0,curStreak=0; trs.forEach(t=>{ if(t.pnl>0){run++;best=Math.max(best,run);}else run=0; }); for(let i=trs.length-1;i>=0;i--){ if(trs[i].pnl>0)curStreak++; else break; }
  let peak=START,dd=0; v.curve.forEach(c=>{ peak=Math.max(peak,c[1]); dd=Math.min(dd,c[1]/peak-1); });
  const sigs=trs.map(t=>t.t_sig).sort((a,b)=>a-b); let gaps=[]; for(let i=1;i<sigs.length;i++)gaps.push(sigs[i]-sigs[i-1]);
  const avgGap=gaps.length?gaps.reduce((a,b)=>a+b,0)/gaps.length/86400000:null;
  const grpLabel={short:'Short',long:'Long',both:'Two-sided'}[v.group]||v.group||'';

  head.innerHTML=`
    <svg width="104" height="104" viewBox="0 0 104 104"><rect width="104" height="104" rx="26" fill="#12161D"></rect><path d="${identicon(name,60)}" fill="#3a81d7" transform="translate(22 22)"></path></svg>
    <div style="flex:1 1 320px">
      <div style="display:flex;align-items:center;gap:12px;flex-wrap:wrap"><h1 style="font-size:40px;letter-spacing:-0.03em">${esc(name)}</h1>
        <span class="chip">${st.cls==='trade'?'<span style="width:7px;height:7px;border-radius:4px;background:#8BB4E8;animation:pulse 1.4s infinite"></span>':st.cls==='rest'?'<span style="width:7px;height:7px;border-radius:4px;background:#FF5C6C"></span>':'<span class="live"></span>'}${esc(st.txt)}</span></div>
      <div class="mut" style="font-size:15px;margin-top:8px">${esc(v.note||'A paper-trading strategy variant.')}</div>
      <div style="display:flex;gap:8px;margin-top:14px;flex-wrap:wrap">
        <span class="chip">Launched ${dstr(DATA.start)}</span><span class="chip">Crypto</span>${grpLabel?`<span class="chip">${esc(grpLabel)}</span>`:''}${v.kill?'<span class="chip" style="color:#FF5C6C">Kill-switch active</span>':''}</div></div>
    <div style="display:flex;gap:10px;flex-wrap:wrap">
      <button class="btn" disabled title="Controls live on :8787 — coming to v2 with the real backend">Pause</button></div>`;

  document.getElementById('b-stats').innerHTML=
    stat('Profit since launch', usd(v.equity-START,true), pos?'up':'dn', pct(v.ret,true)+' on '+dol(START))+
    stat('Trades', v.closed+openN, '', tradesSub)+
    stat('Win streak now', curStreak, '', 'best ever: '+best)+
    stat('Worst dip', pct(dd*100), dd<0?'dn':'', 'peak-to-trough')+
    stat('Between trades', avgGap!=null?avgGap.toFixed(1)+' d':'–', '', 'on average');

  document.getElementById('b-cmp').innerHTML=`
    <div style="flex:1 1 220px"><div style="font-size:15px;font-weight:500">Backtest vs live</div><div class="lbl" style="margin-top:4px">Live average net per trade against the pre-registered backtest</div></div>
    <div><div class="lbl">Backtest net</div><div class="n" style="font-size:15px;margin-top:4px">${pct(v.bt)}</div></div>
    <div><div class="lbl">Live avg net</div><div class="n ${(v.avg||0)>=0?'up':'dn'}" style="font-size:15px;margin-top:4px">${pct(v.avg,true)}</div></div>
    <div><div class="lbl">Win rate</div><div class="n" style="font-size:15px;margin-top:4px">${v.win==null?'–':v.win+'%'}</div></div>
    <div><div class="lbl">Closed trades</div><div class="n" style="font-size:15px;margin-top:4px">${v.closed}</div></div>`;

  document.getElementById('b-strategy').innerHTML=`
    <h2 style="font-size:16px">Strategy</h2>
    ${v.note?`<p style="margin:0;font-size:14px;line-height:1.6;color:#B4BAC4">${esc(v.note)}</p>`:''}
    <div class="blk"><span class="tag">Direction</span>${esc(grpLabel||'–')}</div>
    <div class="blk"><span class="tag">Params</span><span class="n" style="font-weight:400;font-size:12px;line-height:1.5">${esc(v.params||'–')}</span></div>
    ${Object.entries(v.cfg||{}).map(([k,val])=>`<div class="blk"><span class="tag">${esc(k)}</span><span class="n" style="font-weight:400;font-size:12px">${esc(JSON.stringify(val))}</span></div>`).join('')}`;

  drawBot(v);

  const now=DATA.now;
  const rows=v.open.map(o=>({...o,_open:true})).concat(DATA.trades.filter(t=>t.variant===name));
  document.getElementById('b-trcount').textContent=v.closed+v.open.length;
  document.getElementById('b-trades').innerHTML=tbl('btr','bt',[
    {k:'ticker',label:'Coin',s:1,val:r=>r.ticker,cell:r=>`<td style="font-weight:500">${coinCell(r)}</td>`},
    {k:'opened',label:'Opened',s:1,val:r=>r.t_sig,cell:r=>`<td class="n mut">${dstr(r.t_sig)} ${clock(r.t_sig)}</td>`},
    {k:'held',label:'Held',s:1,val:r=>r._open?now-r.t_sig:r.exit_t-r.t_sig,cell:r=>`<td class="n ${r._open?'up':'mut'}">${r._open?'open':held(r.exit_t-r.t_sig)}</td>`},
    {k:'reason',label:'Exit reason',s:1,val:r=>r._open?'Open':(REASON[r.kind]||r.kind),cell:r=>`<td class="mut">${r._open?'<span class="up">Open</span>':esc(REASON[r.kind]||r.kind)}</td>`},
    {k:'result',label:'Result',s:1,val:r=>r._open?(r.upnl||0):r.pnl,cell:r=>{const val=r._open?r.upnl:r.pnl;return `<td class="n ${(val||0)>=0?'up':'dn'}">${usd(val,true)}</td>`;}},
  ], rows);
}

// ---- per-trade candle chart modal -------------------------------------
let CW=null,CS=null,CK=[],CSYM=null,CO=null,CIV='15m',CLOADING=false,CMORE=true;
const IVMS={'15m':900000,'1h':3600000,'4h':14400000,'1d':86400000};
const snap=(t,iv)=>t-t%IVMS[iv];
function cset(){
  CS.setData(CK.map(c=>({time:lt(c.t),open:c.o,high:c.h,low:c.l,close:c.c})));
  const mk=[{time:lt(snap(CO.t_sig,CIV)),position:CO.side==='short'?'aboveBar':'belowBar',color:'#58a6ff',shape:CO.side==='short'?'arrowDown':'arrowUp',text:'in'}];
  if(CO.exit_t)mk.push({time:lt(snap(CO.exit_t,CIV)),position:'inBar',color:'#d29922',shape:'circle',text:CO.kind||'out'});
  CS.setMarkers(CK.length?mk.filter(m=>m.time>=lt(CK[0].t)).sort((a,b)=>a.time-b.time):[]);
}
async function cfetch(params){
  const qs=Object.entries(params).map(([k,v])=>`${k}=${encodeURIComponent(v)}`).join('&');
  const r=await fetch(`/candles?symbol=${encodeURIComponent(CSYM)}&interval=${CIV}&${qs}`);
  return await r.json();
}
async function cload(){
  CLOADING=true;CMORE=true; const iv=IVMS[CIV]; let k;
  if(CO.exit_t){ const start=snap(CO.t_sig,CIV)-60*iv; const limit=Math.min(Math.ceil((CO.exit_t-start)/iv)+40,1500); k=await cfetch({start,limit}); }
  else k=await cfetch({limit:420});
  CK=k;cset();CW.timeScale().fitContent();CLOADING=false;
}
async function colder(){
  if(CLOADING||!CMORE||!CK.length)return; CLOADING=true;
  const k=await cfetch({end:CK[0].t-1,limit:1000});
  if(!k.length)CMORE=false; else CK=k.concat(CK.filter(c=>c.t>k[k.length-1].t));
  cset();CLOADING=false;
}
function civ(iv){CIV=iv;renderCiv();cload();}
function renderCiv(){ document.getElementById('civ').innerHTML=Object.keys(IVMS).map(iv=>`<button class="rb ${CIV===iv?'sel':''}" data-civ="${iv}">${iv}</button>`).join(''); }
async function openCandle(o){
  if(!o.sym){ return; }
  document.getElementById('ctitle').textContent=o.title;
  document.getElementById('covl').style.display='flex';
  const el=document.getElementById('cchart'); if(CW){CW.remove();}
  CW=LightweightCharts.createChart(el,LWOPTS);
  CS=CW.addCandlestickSeries({upColor:'#3DDC97',downColor:'#FF5C6C',wickUpColor:'#3DDC97',wickDownColor:'#FF5C6C',borderVisible:false});
  const line=(p,col,lab)=>p&&CS.createPriceLine({price:p,color:col,lineWidth:1,lineStyle:LightweightCharts.LineStyle.Dashed,title:lab});
  line(o.entry,'#58a6ff','entry'); if(o.stop)line(o.stop,'#FF5C6C','stop'); if(o.tp)line(o.tp,'#3DDC97','tp');
  CSYM=o.sym;CO=o;CIV='15m';renderCiv();
  CW.timeScale().subscribeVisibleLogicalRangeChange(r=>{ if(r&&r.from<30)colder(); });
  await cload();
}
document.getElementById('covl').addEventListener('click',e=>{ if(e.target.id==='covl')e.target.style.display='none'; });
document.addEventListener('keydown',e=>{ if(e.key==='Escape')document.getElementById('covl').style.display='none'; });

// ---- routing + poll ---------------------------------------------------
function parseRoute(){ const h=location.hash||''; const m=h.match(/^#\/bot\/(.+)$/);
  if(m)return {route:'bot',name:decodeURIComponent(m[1])}; return {route:'fleet',name:null}; }
function mount(){ const r=parseRoute(); clearCharts();
  if(r.route==='bot')botSkeleton(r.name); else fleetSkeleton();
  CUR=r; }
function paint(){ if(!DATA)return; refreshSidebar(); const r=parseRoute();
  if(r.route==='bot')paintBot(r.name); else paintFleet(); }
function go(){ const r=parseRoute();
  if(r.route!==CUR.route||r.name!==CUR.name){ mount(); } paint(); window.scrollTo(0,0); }
window.addEventListener('hashchange',go);

// delegated clicks: nav, sorts, pagers, candles, legend, sidebar toggle
document.addEventListener('click',e=>{
  const sbt=e.target.closest('[data-sbtoggle]'); if(sbt){ const c=document.body.classList.toggle('sbc'); try{localStorage.setItem('sbc',c?'1':'0');}catch(_){} setTimeout(()=>window.dispatchEvent(new Event('resize')),210); return; }
  const leg=e.target.closest('[data-leg]'); if(leg){ legSel(leg.getAttribute('data-leg')); return; }
  const lc=e.target.closest('[data-legclear]'); if(lc){ legClear(); return; }
  const vw=e.target.closest('[data-view]'); if(vw){ VIEW=vw.getAttribute('data-view'); try{localStorage.setItem('fleetview',VIEW);}catch(_){} paint(); return; }
  const home=e.target.closest('[data-home]'); if(home){ e.preventDefault(); if(location.hash)location.hash=''; else go(); return; }
  const bot=e.target.closest('[data-bot]'); if(bot){ const n=bot.getAttribute('data-bot'); if(n){ e.preventDefault(); location.hash='#/bot/'+encodeURIComponent(n); } return; }
  const coin=e.target.closest('.coin'); if(coin){ const d=coin.dataset; openCandle({sym:d.sym,title:`${d.tk}${d.variant?' · '+d.variant:''}${d.exit?' (closed '+(d.kind||'')+')':' (open)'}`,t_sig:+d.tsig,entry:+d.entry,stop:d.stop?+d.stop:null,tp:d.tp?+d.tp:null,exit_t:d.exit?+d.exit:null,kind:d.kind||null,side:d.side||null}); return; }
  const th=e.target.closest('th.s'); if(th){ const key=th.getAttribute('data-tk'),col=th.getAttribute('data-sort'); const S=SORT[key]||(SORT[key]={col:null,dir:-1}); if(S.col===col)S.dir=-S.dir; else{S.col=col;S.dir=['variant','ticker','side','kind','reason'].includes(col)?1:-1;} paint(); return; }
  const civb=e.target.closest('[data-civ]'); if(civb){ civ(civb.getAttribute('data-civ')); return; }
  const rb=e.target.closest('.rb[data-days]'); if(rb){ const el=rb.closest('.rng'); const days=rb.getAttribute('data-days'); (el&&el._fn?el._fn:setFleetRange)(days==='null'?null:+days); return; }
  const pg=e.target.closest('[data-pg]'); if(pg){ const k=pg.getAttribute('data-pg'); PG[k].p+=+pg.getAttribute('data-d'); paint(); return; }
});
document.addEventListener('change',e=>{ const s=e.target.closest('select.perpg'); if(s){ const k=s.getAttribute('data-per'); if(PG[k]){ PG[k].n=+s.value; PG[k].p=0; paint(); } } });

try{ if(localStorage.getItem('sbc')==='1')document.body.classList.add('sbc'); const fv=localStorage.getItem('fleetview'); if(fv==='cards'||fv==='rows')VIEW=fv; }catch(_){}

async function poll(){
  try{ const r=await fetch('/api',{cache:'no-store'}); DATA=await r.json();
    if(CUR.route===null){ mount(); } paint(); }
  catch(e){ if(!DATA)document.getElementById('root').innerHTML='<div style="flex:1;display:flex;align-items:center;justify-content:center;color:#6B717B">Could not reach the fleet. Is paper_fleet running?</div>'; }
}
poll(); setInterval(poll,10000);
window.addEventListener('resize',()=>{ /* autoSize handles it */ });
</script></body></html>"""


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        path = self.path.split("?")[0]
        if path == "/":
            body, ctype = PAGE.encode(), "text/html; charset=utf-8"
        elif path == "/api":
            ctype = "application/json"
            if UPSTREAM:
                try:
                    raw = urllib.request.urlopen(UPSTREAM + "/api",
                                                 timeout=8).read()
                    d = json.loads(raw)
                    d["_source"] = "upstream"       # live Hetzner data via :8787
                except Exception:
                    refresh_marks()
                    d = fd.payload()
                    d["_source"] = "local-stale"    # upstream down -> local copy
            else:
                refresh_marks()
                d = fd.payload()
                d["_source"] = "local"
            body = json.dumps(d).encode()
        elif path == "/lw.js":
            body, ctype = fd.LWJS, "application/javascript"
        elif path == "/candles":
            ctype = "application/json"
            if UPSTREAM:
                try:
                    body = urllib.request.urlopen(UPSTREAM + self.path,
                                                  timeout=12).read()
                except Exception:
                    self.send_error(502)
                    return
            else:
                from urllib.parse import parse_qs, urlparse
                q = parse_qs(urlparse(self.path).query)
                sym = q.get("symbol", [""])[0]
                iv = q.get("interval", ["15m"])[0]
                if sym not in fd.UNI.values() or iv not in fd.IVALS:
                    self.send_error(404)
                    return
                try:
                    start = int(q.get("start", ["0"])[0]) or None
                    end = int(q.get("end", ["0"])[0]) or None
                    limit = max(10, min(int(q.get("limit", ["400"])[0]), 1500))
                except ValueError:
                    self.send_error(400)
                    return
                body = json.dumps(fd.fetch_candles(sym, iv, limit, start,
                                                   end)).encode()
        else:
            self.send_error(404)
            return
        self.send_response(200)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *a):
        pass


def main():
    global UPSTREAM
    host = "0.0.0.0" if "--lan" in sys.argv else "127.0.0.1"
    port = 8789
    if "--port" in sys.argv:
        port = int(sys.argv[sys.argv.index("--port") + 1])
    if "--local" in sys.argv:
        UPSTREAM = ""
    if "--upstream" in sys.argv:
        UPSTREAM = sys.argv[sys.argv.index("--upstream") + 1].rstrip("/")
    if not UPSTREAM:
        refresh_marks()
    srv = ThreadingHTTPServer((host, port), Handler)
    shown = "localhost" if host != "0.0.0.0" else host
    src = f"proxying {UPSTREAM}" if UPSTREAM else "local paper/fleet files"
    print(f"fleet dashboard v2: http://{shown}:{port}  (read-only; "
          f"data: {src})")
    srv.serve_forever()


if __name__ == "__main__":
    main()
