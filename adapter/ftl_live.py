"""ftl_bench live dashboard — a READ-ONLY web view of a benchmark run.

Run it (uses the harness venv so it can import the real scorer):

    harness/.venv/Scripts/python adapter/ftl_live.py      # then open http://127.0.0.1:8765

It tails harness/runs/benchmark/*.jsonl and serves one auto-updating page:
  - Browse every instance (left rail); click any to read its trajectory, or stay on ● LIVE to
    auto-follow whatever is currently playing.
  - Each turn renders reasoning FIRST, then the action it chose ("↳ did") and how many frames it
    chose to let the game run before looking again ("waited N frames" — the model's `advance`).
  - Per-instance ftl_score / solved come from the harness's own score_instance (cached by file
    mtime); the aggregate is scoped to the suite's instances so stale files don't skew it.

Never writes anything. Safe to run alongside a live benchmark.
Paths are repo-relative; override with $FTL_BENCH_DIR / $FTL_SUITE for testing elsewhere."""
import glob
import json
import os
import subprocess
import sys
from pathlib import Path
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse, parse_qs

HERE = Path(__file__).resolve().parent
REPO = HERE.parent
sys.path.insert(0, str(REPO / "harness" / "src"))

BENCH = Path(os.environ.get("FTL_BENCH_DIR") or (REPO / "harness" / "runs" / "benchmark"))
SUITE = Path(os.environ.get("FTL_SUITE") or (REPO / "scenarios" / "suite_v1.json"))
PORT = int(os.environ.get("FTL_LIVE_PORT", "8765"))
FEED_TAIL = 60

# Harness scorer (optional — degrade gracefully if run outside the venv).
try:
    from ftl_bench import load_suite, load_trajectory, score_instance
    SCEN = {s.id: s for s in load_suite(str(SUITE))}
except Exception:
    load_suite = load_trajectory = score_instance = None
    SCEN = {}

_score_cache = {}   # path -> (mtime, {"score","solved"} | None)
_meta_cache = {}    # path -> (mtime, meta dict | None)
RUN_WINDOW = 6 * 3600   # files within this of the live file (same agent) = "this run"


def meta_of(path):
    try:
        mt = os.path.getmtime(path)
    except OSError:
        return None
    hit = _meta_cache.get(path)
    if hit and hit[0] == mt:
        return hit[1]
    m = None
    try:
        with open(path, encoding="utf-8") as fh:
            rec = json.loads(fh.readline())
        if rec.get("kind") == "meta":
            m = rec.get("meta", {})
    except Exception:
        pass
    _meta_cache[path] = (mt, m)
    return m


def all_files():
    return sorted(glob.glob(str(BENCH / "*.jsonl")), key=os.path.getmtime, reverse=True)


def current_file():
    fs = all_files()
    return fs[0] if fs else None


def name_of(path):
    return os.path.basename(path)[:-6]            # strip .jsonl


def scenario_id_of(name):
    # files are "<id>.jsonl" or retry "<id>.a<n>.jsonl"
    base = name
    if "." in base:
        head, tail = base.rsplit(".", 1)
        if tail[:1] == "a" and tail[1:].isdigit():
            base = head
    return base


def read_records(path):
    recs = []
    try:
        with open(path, encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if line:
                    try:
                        recs.append(json.loads(line))
                    except Exception:
                        pass
    except OSError:
        pass
    return recs


def score_for(path, is_live):
    if is_live or score_instance is None:
        return None
    scen = SCEN.get(scenario_id_of(name_of(path)))
    if scen is None:
        return None
    mt = os.path.getmtime(path)
    hit = _score_cache.get(path)
    if hit and hit[0] == mt:
        return hit[1]
    out = None
    try:
        r = score_instance(load_trajectory(path), scen)
        out = {"score": int(r.get("ftl_score", 0)), "solved": bool(r.get("solved"))}
    except Exception:
        out = None
    _score_cache[path] = (mt, out)
    return out


def deep(d, *keys):
    for k in keys:
        d = d.get(k) if isinstance(d, dict) else None
    return d


def frame_of(obs):
    v = obs.get("render_count")
    return v if v is not None else obs.get("tick")


def ftl_alive():
    try:
        r = subprocess.run(["tasklist", "/fi", "imagename eq FTLGame.exe"],
                           capture_output=True, text=True, timeout=5)
        return "FTLGame.exe" in r.stdout
    except Exception:
        return None


def build(sel):
    cur = current_file()
    cur_name = name_of(cur) if cur else None
    cur_meta = meta_of(cur) if cur else None
    cur_agent = (cur_meta or {}).get("agent")
    cur_mtime = os.path.getmtime(cur) if cur else 0

    def is_current(p):
        """A file belongs to the run in progress if it shares the live instance's agent label
        and was written within the run's time window (excludes stale base files from old runs)."""
        if not cur_agent:
            return False
        m = meta_of(p)
        return bool(m) and m.get("agent") == cur_agent and (cur_mtime - os.path.getmtime(p)) <= RUN_WINDOW

    instances = []
    for p in all_files():
        nm = name_of(p)
        live = nm == cur_name
        sc = score_for(p, live)
        try:
            steps = sum(1 for _ in open(p, encoding="utf-8", errors="ignore")) - 1
        except OSError:
            steps = 0
        instances.append({"name": nm, "steps": max(steps, 0), "live": live,
                          "current": live or is_current(p),
                          "score": (sc or {}).get("score"), "solved": (sc or {}).get("solved")})

    following = sel in (None, "", "live")
    show_name = cur_name if following else sel
    show_path = str(BENCH / (show_name + ".jsonl")) if show_name else None

    header = {"instance": show_name, "scenario": None, "sector": None,
              "hull": None, "hull_max": None, "steps": 0, "enemy": None}
    feed = []
    if show_path and os.path.exists(show_path):
        recs = read_records(show_path)
        meta = next((r for r in recs if r.get("kind") == "meta"), None)
        if meta:
            m = meta.get("meta", {})
            header["scenario"] = f'{m.get("type")} · seed {m.get("seed")} · {m.get("difficulty","")}'
        steps = [r for r in recs if r.get("kind") == "step"]
        header["steps"] = len(steps)
        if steps:
            obs = steps[-1].get("obs", {})
            header["sector"] = deep(obs, "map", "sector")
            header["hull"] = deep(obs, "player_ship", "hull", "current")
            header["hull_max"] = deep(obs, "player_ship", "hull", "max")
            eh = deep(obs, "enemy_ship", "hull", "current")
            if eh is not None and deep(obs, "enemy_ship", "hull", "max"):
                header["enemy"] = f'{eh}/{deep(obs, "enemy_ship", "hull", "max")}'
        frames = [frame_of(s.get("obs", {})) for s in steps]
        start = max(0, len(steps) - FEED_TAIL)
        for idx in range(start, len(steps)):
            r = steps[idx]
            adv = None
            if idx > 0 and frames[idx] is not None and frames[idx - 1] is not None:
                adv = frames[idx] - frames[idx - 1]
            obs = r.get("obs", {})
            eh = deep(obs, "enemy_ship", "hull", "current")
            emax = deep(obs, "enemy_ship", "hull", "max")
            feed.append({"i": r.get("i"),
                         "thought": r.get("thought"),
                         "actions": [a.get("type", "") for a in (r.get("actions") or [])],
                         "advance": adv,
                         "enemy": (f"{eh}/{emax}" if eh is not None and emax else None)})

    suite_done = []
    for sid in SCEN:
        p = str(BENCH / (sid + ".jsonl"))
        if os.path.exists(p) and name_of(p) != cur_name and is_current(p):
            sc = score_for(p, False)
            if sc:
                suite_done.append(sc)
    agg = None
    if suite_done:
        agg = {"done": len(suite_done), "total": len(SCEN) or 12,
               "mean": round(sum(s["score"] for s in suite_done) / len(suite_done), 1),
               "solved": sum(1 for s in suite_done if s["solved"])}

    return {"instances": instances, "selected": show_name, "following_live": following,
            "header": header, "feed": feed, "agg": agg, "ftl_alive": ftl_alive()}


PAGE = r"""<!doctype html><html><head><meta charset="utf-8"><title>ftl_bench live</title>
<style>
  :root{color-scheme:dark}*{box-sizing:border-box}
  body{margin:0;background:#0b0e14;color:#c8d3e0;font:14px/1.55 -apple-system,Segoe UI,Roboto,sans-serif}
  header{position:sticky;top:0;background:#11151f;border-bottom:1px solid #1f2633;padding:10px 18px;display:flex;gap:20px;align-items:center;flex-wrap:wrap;z-index:5}
  header .ttl{font-weight:700;color:#7dd3fc;letter-spacing:.3px}
  .stat{display:flex;flex-direction:column}
  .stat b{font-size:11px;text-transform:uppercase;color:#5b6677;letter-spacing:.5px;font-weight:600}
  .stat span{font-size:15px;font-weight:600;color:#e6edf5}
  .wrap{display:grid;grid-template-columns:300px 1fr;height:calc(100vh - 58px)}
  aside{background:#0d1119;border-right:1px solid #1f2633;overflow-y:auto;padding:12px}
  aside h3{margin:4px 0 8px;font-size:12px;text-transform:uppercase;color:#5b6677;letter-spacing:.5px}
  .livebtn{display:block;width:100%;text-align:left;cursor:pointer;border:1px solid #243352;background:#10202e;color:#7dd3fc;border-radius:8px;padding:8px 10px;font-weight:700;margin-bottom:10px}
  .livebtn.on{background:#13313f;border-color:#2b6f8a;box-shadow:0 0 0 1px #2b6f8a inset}
  .inst{cursor:pointer;border:1px solid #161d29;border-radius:8px;padding:7px 9px;margin-bottom:6px;display:flex;justify-content:space-between;align-items:center;gap:8px}
  .inst:hover{border-color:#2b3650;background:#111722}
  .inst.sel{border-color:#3b82f6;background:#0f1b2e}
  .inst.old{opacity:.5}
  .inst .nm{font-size:12.5px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
  .inst .meta2{font-size:11px;color:#5b6677}
  .badge{font-size:11px;font-weight:700;padding:1px 7px;border-radius:9px;font-variant-numeric:tabular-nums}
  .badge.ok{background:#0f2a1b;color:#86efac;border:1px solid #204a2c}
  .badge.no{background:#241318;color:#fca5a5;border:1px solid #432028}
  .badge.run{background:#10202e;color:#7dd3fc;border:1px solid #243352}
  .dotlive{display:inline-block;width:7px;height:7px;border-radius:50%;background:#34d399;box-shadow:0 0 7px #34d399;margin-right:5px}
  .agg{margin-top:12px;padding-top:10px;border-top:1px solid #1f2633;font-size:13px}
  .agg div{display:flex;justify-content:space-between;padding:3px 0}.agg b{color:#7dd3fc}
  #feed{overflow-y:auto;padding:16px 20px}
  .turn{padding:11px 14px 12px;margin:0 0 11px;background:#11151f;border:1px solid #1b2230;border-radius:9px}
  .turn .top{display:flex;align-items:center;gap:8px;margin-bottom:5px}
  .turn .i{color:#46505f;font-weight:700;font-size:11.5px}
  .lab{font-size:10.5px;text-transform:uppercase;letter-spacing:.6px;color:#5b6677;font-weight:700}
  .reason{color:#dbe6f3}.reason.empty{color:#46505f;font-style:italic}
  .did{margin-top:9px;padding-top:8px;border-top:1px dashed #222b3a;display:flex;align-items:center;gap:8px;flex-wrap:wrap}
  .arrow{color:#5b6677;font-weight:700;font-size:12px}
  .chips{display:inline-flex;gap:5px;flex-wrap:wrap}
  .chip{font-size:11px;padding:2px 8px;border-radius:10px;background:#172033;color:#9ec5fe;border:1px solid #243352}
  .chip.fire{background:#2a1717;color:#fca5a5;border-color:#4a2020}
  .chip.jump{background:#172a1c;color:#86efac;border-color:#204a2c}
  .chip.power{background:#2a2417;color:#fcd9a5;border-color:#4a3f20}
  .waited{margin-left:auto;font-size:11px;color:#7a8aa0;background:#10151f;border:1px solid #1c2434;border-radius:9px;padding:1px 8px;white-space:nowrap}
  .enemy{font-size:11px;color:#fca5a5;background:#1c1214;border:1px solid #3a2024;border-radius:9px;padding:1px 8px}
</style></head><body>
<header>
  <span class="ttl">⟁ ftl_bench</span>
  <div class="stat"><b>viewing</b><span id="inst">—</span></div>
  <div class="stat"><b>scenario</b><span id="scen">—</span></div>
  <div class="stat"><b>sector</b><span id="sec">—</span></div>
  <div class="stat"><b>hull</b><span id="hull">—</span></div>
  <div class="stat"><b>enemy</b><span id="enemy">—</span></div>
  <div class="stat"><b>steps</b><span id="steps">—</span></div>
  <div class="stat"><b>ftl</b><span id="ftl">—</span></div>
</header>
<div class="wrap">
  <aside>
    <button class="livebtn on" id="livebtn" onclick="follow()">● LIVE — follow current</button>
    <h3>instances</h3>
    <div id="list"></div>
    <div class="agg" id="agg"></div>
  </aside>
  <div id="feed"></div>
</div>
<script>
let sel='live';
function follow(){sel='live';tick();}
function pick(n){sel=n;tick();}
function esc(s){return (s||'').replace(/[<>&]/g,c=>({'<':'&lt;','>':'&gt;','&':'&amp;'}[c]));}
function chipClass(t){if(t.indexOf('fire')>=0)return 'chip fire';if(t.indexOf('jump')>=0||t.indexOf('leave')>=0)return 'chip jump';if(t.indexOf('power')>=0)return 'chip power';return 'chip';}
async function tick(){
  let d; try{ d=await (await fetch('/data?sel='+encodeURIComponent(sel),{cache:'no-store'})).json(); }catch(e){ return; }
  const h=d.header||{};
  inst.textContent=d.selected||'—'; scen.textContent=h.scenario||'—';
  sec.textContent=(h.sector==null)?'—':('sector '+h.sector);
  hull.textContent=(h.hull==null)?'—':(h.hull+(h.hull_max?(' / '+h.hull_max):''));
  hull.style.color=(h.hull!=null&&h.hull<=10)?'#fca5a5':(h.hull!=null&&h.hull<=20?'#fcd9a5':'#86efac');
  enemy.textContent=h.enemy||'—';
  steps.textContent=h.steps;
  ftl.innerHTML=d.ftl_alive?'<span class="dotlive"></span>alive':'down';
  document.getElementById('livebtn').className='livebtn'+(d.following_live?' on':'');
  document.getElementById('list').innerHTML=(d.instances||[]).map(it=>{
    let badge=it.score==null?(it.live?'<span class="badge run">…</span>':'')
            :'<span class="badge '+(it.solved?'ok':'no')+'">'+it.score+(it.solved?' ✓':' ✗')+'</span>';
    const cls='inst'+((it.name===d.selected)?' sel':'')+(!it.current?' old':'');
    const livedot=it.live?'<span class="dotlive"></span>':'';
    return '<div class="'+cls+'" onclick="pick(\''+it.name+'\')"><div><div class="nm">'+livedot+esc(it.name)+
      '</div><div class="meta2">'+it.steps+' steps</div></div>'+badge+'</div>';
  }).join('');
  if(d.agg) document.getElementById('agg').innerHTML=
      '<div><span>done</span><b>'+d.agg.done+' / '+d.agg.total+'</b></div>'+
      '<div><span>mean ftl_score</span><b>'+d.agg.mean+'</b></div>'+
      '<div><span>solved</span><b>'+d.agg.solved+' / '+d.agg.done+'</b></div>';
  const f=document.getElementById('feed');
  const nearBottom=f.scrollHeight-f.scrollTop-f.clientHeight<90;
  f.innerHTML=(d.feed||[]).map(t=>{
    const chips=(t.actions||[]).map(a=>'<span class="'+chipClass(a)+'">'+a.replace(/_/g,' ')+'</span>').join('');
    const reason=t.thought?'<div class="reason">'+esc(t.thought)+'</div>':'<div class="reason empty">(no reasoning logged — pure advance)</div>';
    const waited=(t.advance!=null)?'<span class="waited">waited '+t.advance+' frames</span>':'';
    const en=t.enemy?'<span class="enemy">enemy '+t.enemy+'</span>':'';
    return '<div class="turn"><div class="top"><span class="i">#'+t.i+'</span><span class="lab">reasoned</span>'+en+'</div>'+
      reason+'<div class="did"><span class="arrow">↳</span><span class="lab">did</span><span class="chips">'+
      (chips||'<span class="chip">wait</span>')+'</span>'+waited+'</div></div>';
  }).join('');
  if(d.following_live&&nearBottom) f.scrollTop=f.scrollHeight;
}
tick(); setInterval(tick,2000);
</script></body></html>"""


class H(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def do_GET(self):
        parsed = urlparse(self.path)
        if parsed.path == "/data":
            sel = (parse_qs(parsed.query).get("sel", ["live"])[0]) or "live"
            body = json.dumps(build(sel)).encode("utf-8")
            ctype = "application/json"
        else:
            body = PAGE.encode("utf-8")
            ctype = "text/html; charset=utf-8"
        self.send_response(200)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


if __name__ == "__main__":
    print(f"ftl_bench live dashboard: http://127.0.0.1:{PORT}  (bench={BENCH}, scorer={'on' if score_instance else 'off'})")
    ThreadingHTTPServer(("127.0.0.1", PORT), H).serve_forever()
