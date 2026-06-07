"""ftl_bench LLM agent track — a real frontier model plays the suite.

This is the agent that turns ftl_bench from "an env you poke by hand" into "a benchmark you
run": `make_llm_agent(model, backend)` returns an `agent_fn(sess, scenario, log)` that
`run_benchmark.py` drives exactly like the scripted/random baselines, so the same
trajectory -> score_instance -> aggregate pipeline emits GCS@1 / solve-rate automatically.

The model plays through the SAME surface a human-facing agent uses: each turn it receives the
decision-complete `compact()` observation + the scenario goal + a short history of its recent
actions, and replies with ONE play_cli command (`ACTION: <command>`), which is dispatched
through the SHARED `apply_command()` so the LLM and the CLI have identical action semantics.
The agent decides everything — no scripted policy (that's the benchmark's whole point).

Two backends (pick whichever you can run):
  - "anthropic": the canonical, portable track. Needs ANTHROPIC_API_KEY. `--model claude-...`.
  - "claude-cli": shells out to the local `claude -p` (no API key; uses your Claude Code
    auth). Slower per turn, but lets you validate the track end-to-end without a key.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))           # play_cli
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "harness" / "src"))

from play_cli import apply_command, compact  # noqa: E402
from ftl_bench.session import ftl_process_alive  # noqa: E402

PROMPTS_DIR = Path(__file__).resolve().parent.parent / "prompts"


def load_prompt(version: str = "v1") -> str:
    """Load the version-controlled FTL agent operating manual (the static rules + how-to-play).
    The per-scenario GOAL is appended separately at runtime, so this file is goal-agnostic and
    reusable across the suite. The version is part of the agent's identity (recorded in the run
    manifest) — a different manual is a different agent, not a comparable one."""
    path = PROMPTS_DIR / f"ftl_agent_{version}.md"
    if not path.exists():
        raise FileNotFoundError(
            f"prompt manual not found: {path} (available: "
            f"{[p.name for p in PROMPTS_DIR.glob('ftl_agent_*.md')]})")
    return path.read_text(encoding="utf-8")


# verbs apply_command accepts from an agent (used to salvage a non-prefixed reply)
KNOWN_VERBS = {"power", "fire", "beam", "jump", "event", "leave", "wait", "crew", "buy",
               "sell", "upgrade", "cloak", "doors", "mindcontrol", "battery", "hack",
               "drone", "dronerecall", "board", "recall"}
TERMINAL = {"GAME_OVER", "DESTROYED", "FROZEN_KILLED", "ALIVE_BUT_UNRESPONSIVE"}


def _attr(g, name, default=None):
    """Read a goal field whether it's a SubObjective dataclass or a plain dict."""
    return g.get(name, default) if isinstance(g, dict) else getattr(g, name, default)


def _goal_text(scenario) -> str:
    parts = []
    for g in (getattr(scenario, "goal", None) or []):
        op = "=" if _attr(g, "kind") == "boolean" else ">="
        parts.append(f"{_attr(g, 'key')} {op} {_attr(g, 'target')} "
                     f"(weight {_attr(g, 'weight', 1)})")
    return "; ".join(parts) or "(survive and progress)"


def build_system_prompt(scenario, manual: str, play_to_gameover: bool = False,
                        stall_limit: int = 10, reflection: str = "") -> str:
    """The manual + the ONE real objective: win the game. No artificial per-scenario sub-goals
    — the agent plays the actual game of FTL with its own intelligence, and we measure how far
    it gets toward beating the rebel flagship. The scenario only pins the seed (the map/RNG).

    In play-to-game-over mode there is no jump budget: play until the game actually ends. We
    expose the stall rule (no progress for `stall_limit` turns = the run ends in a loss) so the
    agent can avoid it — that's stating an eval rule, not scripting its moves.

    Both modes share the SAME win-framed core (the goal is to win the game of FTL). They differ
    only in how the run ends: a full game runs to a real win/death, a bounded probe runs within a
    jump budget. The budget is stated honestly so the words the agent reads match the loop it runs
    (the old default told the agent to "not count turns" while the harness silently ended the run
    on a jump count)."""
    win_core = (
        "## YOUR OBJECTIVE\n"
        "Play FTL to WIN: keep your ship and crew alive, fight and manage well, and advance "
        "toward destroying the rebel flagship (the win). The game stays PAUSED while you decide, "
        "so take all the thinking time you need each turn — deliberating and setting up (powering "
        "systems, positioning crew, targeting) costs nothing. The ONLY wasted turn is repeating an "
        "action that does nothing (a no-op). You know FTL; every decision is yours."
    )
    if play_to_gameover:
        objective = (
            f"{win_core}\n"
            f"This is a FULL game: there is NO jump limit — keep playing until the game actually "
            f"ends. You WIN by destroying the rebel flagship after sector 8; you LOSE if your ship "
            f"is destroyed.\n"
            f"STALL RULE: if you make NO progress for {stall_limit} turns in a row — the game "
            f"state stops changing (re-issuing actions that already took effect, or idling while "
            f"nothing happens) — the run is declared a LOSS and ends. Every turn, do something "
            f"that moves the game forward."
        )
    else:
        budget = getattr(scenario, "budget_jumps", None)
        budget_phrase = (f"about {budget} jumps" if budget else "a limited number of jumps")
        objective = (
            f"{win_core}\n"
            f"This run is a bounded probe: you have {budget_phrase} to get as far toward that goal "
            f"as you can. Don't waste them, but don't rush either — winning fights and keeping your "
            f"ship healthy is what gets you further (and raises the score); jumping for its own "
            f"sake does not."
        )
    lessons = ""
    if reflection:
        lessons = ("\n\n## LESSONS FROM YOUR PREVIOUS ATTEMPTS (same seed)\n"
                   "You have played this exact seed before without solving it. Apply what you "
                   "learned:\n" + reflection)
    return f"{manual}\n\n{objective}{lessons}"


def build_turn_prompt(c: dict, history: list[str], step: int, jumps: int, budget: int) -> str:
    hist = "\n".join(history[-8:]) if history else "(none yet)"
    return (
        f"Your recent actions:\n{hist}\n\n"
        f"OBSERVATION:\n{json.dumps(c, separators=(',', ':'))}\n\n"
        f"Decide ONE action. End with `ACTION: <command>`."
    )


def parse_action(text: str) -> tuple[str | None, list[str]]:
    """Extract a (command, args) from the model's reply. Prefer an `ACTION:` line; else the
    first line whose first token is a known verb. Returns (None, []) if nothing usable."""
    if not text:
        return None, []
    lines = [ln.strip() for ln in text.strip().splitlines() if ln.strip()]
    # 1) an explicit ACTION: line (last one wins — the model may restate)
    for ln in reversed(lines):
        low = ln.lower()
        if low.startswith("action:"):
            toks = ln.split(":", 1)[1].strip().strip("`").split()
            if toks and toks[0].lower() in KNOWN_VERBS:
                return toks[0].lower(), toks[1:]
    # 2) salvage: any line that starts with a known verb
    for ln in lines:
        toks = ln.strip("`").split()
        if toks and toks[0].lower() in KNOWN_VERBS:
            return toks[0].lower(), toks[1:]
    return None, []


def _summarize(step: int, cmd: str, args: list[str], c: dict) -> str:
    bits = [f"sector{c.get('sector')}", f"hull {c.get('hull')}"]
    if c.get("enemy"):
        bits.append("enemy:present")
    if c.get("scrap") is not None:
        bits.append(f"scrap{c.get('scrap')}")
    if c.get("game_status"):
        bits.append(c["game_status"])
    return f"step{step}: '{cmd} {' '.join(args)}' -> " + " ".join(bits)


def _state_sig(c: dict):
    """Signature of the salient game state. If it's unchanged after an action, that action made
    no progress — so the repeated-action nudge can fire on TRUE no-op loops (re-power a maxed
    system, re-fire an autofiring weapon) while NOT discouraging productive waiting (a repair or
    heal in progress changes `damage`/`hp`, so the signature changes and the nudge stays quiet)."""
    en = c.get("enemy") or {}
    sh = c.get("shots") or {}
    return (
        c.get("hull"), c.get("sector"), c.get("scrap"), c.get("fuel"), c.get("missiles"),
        c.get("oxygen_pct"),
        sum((s.get("damage") or 0) for s in c.get("systems", [])),
        tuple(sorted(str(cr.get("hp")) for cr in c.get("crew", []))),
        (en.get("hull") if en else None),
        (c.get("map") or {}).get("at_exit"),
        sh.get("fired"), sh.get("hit"),
    )


def _progress_sig(c: dict):
    """Did the agent meaningfully AFFECT the game this turn? The play-to-gameover stall guard
    resets whenever this changes; it only trips when NOTHING changes for `stall_limit` turns —
    a true idle / no-op loop. It counts BOTH goal progress (map move via sector/current_pos/
    at_exit, enemy damaged/gone, scrap gained) AND active ship-management (fires being fought,
    systems repaired, intruders cleared, hull/oxygen/crew-hp changing). The latter is crucial:
    an agent putting out fires, repairing, healing or repelling boarders is NOT stalling even
    though it isn't advancing the map — penalizing that was wrong. Only genuine inactivity
    (repeating an idempotent command, or idling at full health without jumping) is a stall."""
    en = c.get("enemy") or {}
    m = c.get("map") or {}
    return (
        # goal progress
        c.get("sector"), c.get("scrap"), m.get("current_pos"), m.get("at_exit"),
        bool(en), (en.get("hull") if en else None), c.get("game_status"),
        # active ship-management (handling a crisis is NOT a stall)
        c.get("hull"), c.get("oxygen_pct"),
        sum((s.get("damage") or 0) for s in (c.get("systems") or [])),
        sum(int(f.get("fires") or 0) for f in (c.get("fires") or [])),
        len(c.get("intruders") or []),
        tuple(sorted(str(cr.get("hp")) for cr in (c.get("crew") or []))),
    )


# --- backends -----------------------------------------------------------------------

def anthropic_complete(system: str, user: str, model: str, max_tokens: int = 700) -> str:
    """Canonical track: Anthropic Messages API over urllib (no SDK dependency). Retries a
    couple times on transient overload (429/529)."""
    import urllib.error
    import urllib.request

    # Tolerate a key set with surrounding quotes or stray whitespace (a common `setx KEY "..."`
    # / shell mistake on Windows that otherwise stores the quotes literally and yields a 401).
    key = (os.environ.get("ANTHROPIC_API_KEY") or "").strip().strip('"').strip("'")
    if not key:
        raise RuntimeError("ANTHROPIC_API_KEY not set (export it, or use --backend claude-cli)")
    body = json.dumps({
        "model": model, "max_tokens": max_tokens, "system": system,
        "messages": [{"role": "user", "content": user}],
    }).encode()
    req = urllib.request.Request(
        "https://api.anthropic.com/v1/messages", data=body,
        headers={"content-type": "application/json", "x-api-key": key,
                 "anthropic-version": "2023-06-01"})
    last = None
    for attempt in range(3):
        try:
            with urllib.request.urlopen(req, timeout=90) as r:
                data = json.loads(r.read())
            return "".join(b.get("text", "") for b in data.get("content", [])
                           if b.get("type") == "text")
        except urllib.error.HTTPError as e:  # noqa: PERF203
            last = e
            if e.code in (429, 500, 503, 529):
                time.sleep(2 * (attempt + 1)); continue
            raise
    raise RuntimeError(f"anthropic API failed after retries: {last}")


def claude_cli_complete(system: str, user: str, model: str | None) -> str:
    """No-key track: drive the local `claude -p` headless CLI (uses Claude Code auth). One
    self-contained prompt per turn; we parse one ACTION line out of stdout."""
    prompt = (f"{system}\n\n{user}\n\n"
              f"(Respond with one short reasoning sentence then a final `ACTION: <command>` "
              f"line. Do not use any tools or read any files — answer only from the prompt.)")
    cmd = ["claude", "-p", prompt]
    if model:
        cmd += ["--model", model]
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=180)
    return r.stdout or r.stderr


# --- retry / reflection -------------------------------------------------------------

def reflect(attempts, complete) -> str:
    """Reference reflection step (Reflexion): given the prior same-seed `Attempt`s the benchmark
    handed us, ask the model to name the key mistakes and a concrete plan for the next try, and
    return that as a short note to carry into the next attempt's context. Best-effort — a failure
    just yields no memory. Agents may use this, or do anything they like with the raw `attempts`."""
    if not attempts:
        return ""
    digests = "\n\n".join(a.digest() for a in attempts)
    system = (
        "You are getting better at the game FTL across retries of the SAME seed (identical map and "
        "events). Below is what you did on your previous attempt(s) at this exact seed and how each "
        "ended. Find the decisions and mistakes that cost you, and write a SHORT, concrete plan for "
        "the next attempt: specific tactics to change, things to do earlier, things to avoid. Be "
        "terse and actionable — it is a note to yourself. "
        "The objective is to WIN the game of FTL (keep your ship and crew alive, win fights, and "
        "advance toward beating the rebel flagship). ftl_score and jump counts are only how that is "
        "MEASURED — do NOT treat 'use more jumps' or 'raise the score' as the goal. Diagnose what "
        "went wrong in the GAME (combat lost, crew/oxygen/hull mismanaged, the enemy never killed) "
        "and how to play it better."
    )
    user = (f"{digests}\n\nWrite 3-6 short bullet points: the concrete lessons and your plan for "
            f"the next attempt at this seed.")
    try:
        return complete(system, user).strip()
    except Exception:  # noqa: BLE001 — reflection is best-effort
        return ""


def make_llm_agent(model: str | None = None, backend: str = "anthropic", step_mult: int = 8,
                   prompt_version: str = "v3", play_to_gameover: bool = False,
                   stall_limit: int = 10):
    """Return an agent_fn(sess, scenario, log) that plays via the chosen model/backend, using the
    version-controlled prompt manual `prompt_version`.

    Default mode: play up to `budget_jumps * step_mult` turns (the scenario's jump budget).
    `play_to_gameover` mode: ignore the jump budget and play until the game actually ends
    (DESTROYED / GAME_OVER / win) — but the run also ends in a LOSS if the agent STALLS, i.e.
    makes no progress (`_state_sig` unchanged) for `stall_limit` consecutive turns. This turns
    the dawdle failure mode (no-op loops, endless idling) into an automatic loss instead of
    burning the whole budget. A high hard cap still bounds pathological runs.

    The session is already reset to the scenario seed by run_instance; we just play."""
    if model is None:
        model = "claude-sonnet-4-6" if backend == "anthropic" else "sonnet"
    manual = load_prompt(prompt_version)  # load once; fail fast if the version is missing

    def complete(system: str, user: str) -> str:
        if backend == "claude-cli":
            return claude_cli_complete(system, user, model)
        return anthropic_complete(system, user, model)

    def agent_fn(sess, scenario, log, attempts=()) -> None:
        # Retry context: if the benchmark handed us prior same-seed attempts, reflect on them and
        # carry the lessons into this try's system prompt (Reflexion). First try: attempts is empty.
        reflection = reflect(attempts, complete) if attempts else ""
        if reflection:
            log(f"    [llm] reflection after {len(attempts)} prior attempt(s) at this seed "
                f"(carried into this try's system prompt):\n"
                f"    ----- reflection -----\n"
                + "\n".join("    " + ln for ln in reflection.splitlines())
                + "\n    ----- end reflection -----")
        system = build_system_prompt(scenario, manual, play_to_gameover, stall_limit,
                                     reflection=reflection)
        budget = scenario.budget_jumps
        history: list[str] = []
        jumps = 0
        prev_action = None   # repeated-action nudge: break no-op loops (wait/fire/power spam)
        prev_sig = None
        prev_prog = None     # progress signature for the stall guard (play-to-gameover)
        repeat_count = 0
        stall_count = 0      # consecutive turns with NO forward progress (play-to-gameover)
        timeouts = 0         # consecutive transient action-ack lags (reset on any success)
        HARD_CAP = 1500      # safety bound for play-to-gameover (a full FTL game is < this)
        max_steps = HARD_CAP if play_to_gameover else budget * step_mult
        for step in range(max_steps):
            if not play_to_gameover and jumps >= budget:
                log(f"    [llm] jump budget {budget} reached"); break
            try:
                o = sess.observe()
            except Exception:  # noqa: BLE001
                time.sleep(0.2); continue
            c = compact(o)
            status = c.get("game_status")
            if status in TERMINAL:
                log(f"    [llm] episode over: {status}"); break
            # resolve a blocking event automatically? No — the model decides (event is in obs).
            try:
                turn = build_turn_prompt(c, history, step, jumps, budget)
                # Factual nudge to break no-op loops (the recurring failure mode: re-issuing an
                # action that's already taken effect — power a system already at level, fire a
                # weapon already autofiring, wait with nothing changing). State the fact; the
                # agent still decides (no policy baked in).
                if repeat_count >= 2:
                    turn += (f"\n\nNOTE: you have issued the IDENTICAL action '{prev_action}' "
                             f"{repeat_count + 1} times in a row with no meaningful change in the "
                             f"observation — it has already taken effect or isn't possible now. "
                             f"Pick a DIFFERENT action to make progress toward the goal.")
                # Stall warning: as the no-progress streak approaches the limit, tell the agent
                # the run is about to end (exposing the eval rule — the agent still chooses).
                if play_to_gameover and stall_limit and stall_count >= max(2, stall_limit - 4):
                    turn += (f"\n\nWARNING: the game state has not changed for {stall_count} turns. "
                             f"The run ENDS in a LOSS at {stall_limit} stalled turns. Make a move "
                             f"that actually changes the game (jump to a new beacon, deal/take "
                             f"damage, resolve an event) — not another action that does nothing.")
                reply = complete(system, turn)
            except Exception as e:  # noqa: BLE001 — a model/transport error ends the episode
                log(f"    [llm] model error: {e}"); break
            cmd, cargs = parse_action(reply)
            if cmd is None:
                history.append(f"step{step}: (no parseable action; waited)")
                cmd, cargs = "wait", []
            action_str = (cmd + " " + " ".join(map(str, cargs))).strip()
            try:
                o2 = apply_command(sess, cmd, cargs)
            except TimeoutError:
                # An action ack can lag transiently (long warp/arrival, or slow file I/O on
                # native Windows where Defender/NTFS briefly locks the action/obs files). Only a
                # GONE process is truly frozen; tolerate a few consecutive lags and re-observe so
                # the agent can re-issue, matching the scripted baseline. Without this, ONE lag
                # propagates out and run_instance force-restarts FTL, truncating the whole episode.
                timeouts += 1
                dead = not ftl_process_alive()
                log(f"    [llm] action ack timed out [{timeouts}]"
                    + ("  — game frozen/dead" if dead else ""))
                if dead or timeouts >= 4:
                    raise  # real freeze: let run_instance relaunch + move on
                continue
            except Exception as e:  # noqa: BLE001 — bad args / illegal action: tell the model, continue
                history.append(f"step{step}: '{cmd} {' '.join(cargs)}' -> ERROR: {e}")
                # a repeated illegal action is a no-op loop too (state can't change)
                repeat_count = repeat_count + 1 if action_str == prev_action else 0
                prev_action = action_str
                continue
            timeouts = 0  # a successful ack clears the transient-lag streak
            if cmd in ("jump", "leave"):
                jumps += 1
            c2 = compact(o2)
            # No-op-loop detection. Non-`wait` commands are idempotent SETS (power a system to a
            # level, target a weapon, move crew to a room) — re-issuing the SAME one does nothing,
            # regardless of incidental state drift (e.g. oxygen creeping back up), so flag any
            # identical repeat. `wait` is the exception: repeating it is productive WHILE the state
            # is actually changing (a repair/heal in progress), so only flag a `wait` repeat when
            # the salient state is unchanged.
            sig = _state_sig(c2)
            same = (action_str == prev_action)
            productive_wait = (cmd == "wait" and sig != prev_sig)
            repeat_count = repeat_count + 1 if (same and not productive_wait) else 0
            # Stall = no FORWARD PROGRESS vs the previous turn (map didn't move, the enemy isn't
            # dying, no scrap gained). Catches both idling AND combat stalemates — "the agent is
            # paused" — without being reset by incidental damage/charge micro-changes.
            prog = _progress_sig(c2)
            stall_count = stall_count + 1 if (prev_prog is not None and prog == prev_prog) else 0
            prev_action, prev_sig, prev_prog = action_str, sig, prog
            # Direct feedback when the agent powers a BROKEN module: power can't restore a damaged
            # or on-fire system — it needs a crew member in its room to repair/extinguish. The
            # agent keeps re-powering broken modules because nothing tells it power is the wrong fix.
            broken_note = ""
            if cmd == "power" and cargs:
                try:
                    _tsys = next((sy for sy in c2.get("systems", [])
                                  if sy.get("id") == int(cargs[0])), None)
                    if _tsys and (_tsys.get("damage") or _tsys.get("on_fire")):
                        _cond = "ON FIRE" if _tsys.get("on_fire") else "DAMAGED"
                        broken_note = (f"  [NOTE: {_tsys.get('name')} is {_cond} — powering does NOT "
                                       f"fix a broken module; send a crew member to room "
                                       f"{_tsys.get('room')} to repair/extinguish it.]")
                except Exception:  # noqa: BLE001
                    pass
            history.append(_summarize(step, cmd, cargs, c2) + broken_note)
            _int = c2.get("interrupted_by")
            log(f"    [llm] step {step}: {cmd} {' '.join(cargs)} -> "
                f"sector {c2.get('sector')} hull {c2.get('hull')} jumps {jumps}"
                + (f"  [INTERRUPT:{_int}]" if _int else "")
                + (f"  [stall {stall_count}/{stall_limit}]"
                   if (play_to_gameover and stall_count) else ""))
            # Stall-out: no progress for stall_limit turns -> the run is over (a loss).
            if play_to_gameover and stall_limit and stall_count >= stall_limit:
                log(f"    [llm] STALLED {stall_count} turns with no progress -> GAME OVER")
                break
            # Natural end already handled at the top via game_status; play-to-gameover also stops
            # when the obs reports the game is over (DESTROYED/GAME_OVER).
            if play_to_gameover and (c2.get("game_status") in TERMINAL or c2.get("game_over")):
                log(f"    [llm] game over: {c2.get('game_status') or 'GAME_OVER'}"); break

        # Episode over (stall / death / win / cap): leave FTL cleanly at the menu instead of
        # paused mid-run, so the game is genuinely "over" and the next instance starts fresh.
        if play_to_gameover:
            try:
                sess.abandon_to_menu()
                log("    [llm] run over -> returned FTL to the menu")
            except Exception as e:  # noqa: BLE001
                log(f"    [llm] abandon_to_menu failed: {e}")

    return agent_fn
