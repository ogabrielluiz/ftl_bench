"""Tests for pure, unit-testable helpers in the adapter LLM agent — chiefly _extract_thought,
which captures the model's reasoning for the thoughts log. adapter/ isn't an installed package,
so it's put on sys.path here (mirroring how run_benchmark.py wires it up)."""
import sys
import copy
from pathlib import Path
from types import SimpleNamespace

import pytest

_ADAPTER = Path(__file__).resolve().parents[2] / "adapter"
if str(_ADAPTER) not in sys.path:
    sys.path.insert(0, str(_ADAPTER))

import llm_agent  # noqa: E402


def test_extract_thought_drops_the_action_line():
    reply = "I should power weapons and fire on their shields.\nACTION: fire 0 1"
    assert llm_agent._extract_thought(reply) == "I should power weapons and fire on their shields."


def test_extract_thought_collapses_multiline_and_uses_last_action():
    # Mirrors parse_action: the LAST `action:` line is the command; everything before is reasoning.
    reply = "First, drop their shields.\nThen target the helm.\nACTION: fire 1 3"
    t = llm_agent._extract_thought(reply)
    assert t == "First, drop their shields. Then target the helm."
    assert "ACTION" not in t and "\n" not in t


def test_extract_thought_caps_length():
    t = llm_agent._extract_thought("x" * 500 + "\nACTION: wait", max_len=240)
    assert len(t) <= 240 and t.endswith("…")


def test_extract_thought_empty_or_action_only_is_none():
    assert llm_agent._extract_thought("") is None
    assert llm_agent._extract_thought("ACTION: wait") is None   # action line only, no reasoning


# --------------------------------------------------------------------------- #
# parse_plan — multi-action 'plan' turns
# --------------------------------------------------------------------------- #
def test_parse_plan_multi_line_block_with_advance_and_comments():
    reply = (
        "I'll fight the fire and shoot their weapons.\n"
        "ACTION:\n"
        "  power 3 3        # max weapons\n"
        "  crew 0 8         # fight the fire\n"
        "  doors close 9\n"
        "  fire 1 3\n"
        "  advance 150\n"
    )
    cmds, adv = llm_agent.parse_plan(reply)
    assert cmds == [("power", ["3", "3"]), ("crew", ["0", "8"]),
                    ("doors", ["close", "9"]), ("fire", ["1", "3"])]
    assert adv == 150


def test_parse_plan_single_action_line_is_backward_compatible():
    cmds, adv = llm_agent.parse_plan("reasoning here\nACTION: jump 3")
    assert cmds == [("jump", ["3"])]
    assert adv is None                     # no advance directive -> caller defaults


def test_parse_plan_strips_bullets_and_uses_wait_as_advance():
    reply = "ACTION:\n- power 0 2\n- wait 600"
    cmds, adv = llm_agent.parse_plan(reply)
    assert cmds == [("power", ["0", "2"])]
    assert adv == 600                       # `wait N` is the advance directive, not an action


def test_parse_plan_no_action_block_returns_empty():
    cmds, adv = llm_agent.parse_plan("just musing, no commands")
    assert cmds == [] and adv is None


def test_parse_plan_accepts_giveup_aliases():
    assert llm_agent.parse_plan("ACTION: giveup")[0] == [("giveup", [])]
    assert llm_agent.parse_plan("ACTION: surrender")[0] == [("surrender", [])]


# --------------------------------------------------------------------------- #
# _plan_advance — floors + caps
# --------------------------------------------------------------------------- #
def test_plan_advance_honors_request_and_floors():
    assert llm_agent._plan_advance([("power", ["3", "3"])], 90) == 90       # honored
    assert llm_agent._plan_advance([("power", ["3", "3"])], None) == 90     # default
    assert llm_agent._plan_advance([("fire", ["1", "3"])], 30) == 150       # fire floor
    assert llm_agent._plan_advance([("jump", ["3"])], 30) == 260            # warp floor
    assert llm_agent._plan_advance([("power", ["3", "3"])], 99999) == 1200  # cap


# --------------------------------------------------------------------------- #
# command_to_action — batchable converter (mirrors apply_command)
# --------------------------------------------------------------------------- #
def test_command_to_action_builds_dicts_and_wait_is_none():
    assert llm_agent.command_to_action("power", ["3", "2"]) == {
        "type": "set_system_power", "system_id": 3, "level": 2}
    assert llm_agent.command_to_action("fire", ["1", "3"])["type"] == "fire_weapon"
    assert llm_agent.command_to_action("jump", ["5"]) == {"type": "jump", "beacon_index": 5}
    assert llm_agent.command_to_action("wait", []) is None      # pure advance, no action
    assert llm_agent.command_to_action("giveup", []) == {"type": "give_up"}


def test_command_to_action_unknown_verb_raises():
    with pytest.raises(ValueError):
        llm_agent.command_to_action("frobnicate", [])


def test_plan_limit_still_reads_the_advance_directive():
    reply = "ACTION:\n" + "power 3 3\n" * 13 + "advance 600"
    commands, advance = llm_agent.parse_plan(reply)
    assert len(commands) == 12
    assert advance == 600


class SimulatedSession:
    """Exercise the real agent loop without launching a game or calling a model."""

    def __init__(self, *, charge=False, terminal_after=None):
        self.steps = 0
        self.pending_thought = None
        self.charge = charge
        self.terminal_after = terminal_after
        self.state = {
            "sector": 0, "hull": "30/30", "scrap": 0, "oxygen_pct": 100,
            "crew": [], "systems": [], "enemy": None,
            "map": {"current_pos": {"x": 0, "y": 0}},
            "weapons": [{"slot": 0, "powered": True, "charge": 0, "charge_max": 25}],
        }

    def observe(self):
        return copy.deepcopy(self.state)

    def step(self, actions, advance_frames):
        self.steps += 1
        if self.charge:
            self.state["weapons"][0]["charge"] += advance_frames / 60
        if self.terminal_after and self.steps >= self.terminal_after:
            self.state.update(game_status="GAME_OVER", game_over=True, victory=True)
        return self.observe()

    def abandon_to_menu(self):
        return self.observe()


def stub_model(monkeypatch, reply):
    monkeypatch.setattr(llm_agent, "compact", lambda state: state)
    monkeypatch.setattr(llm_agent, "anthropic_complete", lambda *a, **k: reply)
    monkeypatch.setattr(llm_agent.time, "sleep", lambda _: None)


def test_charging_does_not_trigger_a_false_stall_loss(monkeypatch):
    stub_model(monkeypatch, "ACTION: advance 30")
    sess = SimulatedSession(charge=True, terminal_after=20)
    result = llm_agent.make_llm_agent(play_to_gameover=True)(
        sess, SimpleNamespace(budget_jumps=40), lambda _: None)
    assert result["reason"] == "win"
    assert sess.steps == 20


def test_true_idle_is_bounded_by_the_stall_guard(monkeypatch):
    stub_model(monkeypatch, "ACTION: advance 30")
    sess = SimulatedSession()
    result = llm_agent.make_llm_agent(play_to_gameover=True, stall_limit=3)(
        sess, SimpleNamespace(budget_jumps=40), lambda _: None)
    assert result["reason"] == "stalled"
    assert sess.steps == 4


@pytest.mark.parametrize("changed", ["fuel", "distress_on", "waiting", "reactor_level", "system_level"])
def test_native_economy_and_fuel_state_changes_reset_noop_signatures(changed):
    before = {"fuel": 0, "economy": {"upgrade_available": True,
        "systems": [{"system_id": 8, "current_max_power": 1}],
        "reactor": {"current_max_power": 10},
        "fuel_recovery": {"out_of_fuel": True, "distress_on": False, "can_wait": True, "waiting": False}}}
    after = copy.deepcopy(before)
    if changed == "fuel":
        after["fuel"] = 1
    elif changed in {"distress_on", "waiting"}:
        after["economy"]["fuel_recovery"][changed] = True
    elif changed == "reactor_level":
        after["economy"]["reactor"]["current_max_power"] += 1
    else:
        after["economy"]["systems"][0]["current_max_power"] += 1
    assert llm_agent._progress_sig(before) != llm_agent._progress_sig(after)
    assert llm_agent._state_sig(before) != llm_agent._state_sig(after)
    after = copy.deepcopy(before)
    after.update(action_feedback=[{"status": "rejected", "reason": "native_fuel_recovery_refused"}], render_count=100)
    assert llm_agent._progress_sig(before) == llm_agent._progress_sig(after)


@pytest.mark.parametrize("field", ["can_jump", "enemy_defeat_pending", "drive_current", "drive_max", "reason"])
def test_authoritative_navigation_and_drive_progress_reset_both_stall_signatures(field):
    before = {"economy": {"navigation": {"can_jump": False, "enemy_defeat_pending": True,
               "drive_current": 41, "drive_max": 85, "reason": "drive_charging"}}}
    after = copy.deepcopy(before)
    after["economy"]["navigation"][field] = {"can_jump": True, "enemy_defeat_pending": False,
        "drive_current": 62, "drive_max": 90, "reason": "modal_open"}[field]
    assert llm_agent._state_sig(before) != llm_agent._state_sig(after)
    assert llm_agent._progress_sig(before) != llm_agent._progress_sig(after)


def test_observed_fuel_recovery_transitions_do_not_trigger_false_stall(monkeypatch):
    stub_model(monkeypatch, "ACTION: waitfuel\nadvance 30")
    class RecoverySession(SimulatedSession):
        def step(self, actions, advance_frames):
            obs = super().step(actions, advance_frames)
            self.state["economy"] = {"fuel_recovery": {
                "out_of_fuel": True, "waiting": self.steps % 2 == 1,
                "distress_on": False, "can_wait": self.steps % 2 == 0}}
            return self.observe()
    sess = RecoverySession(terminal_after=8)
    result = llm_agent.make_llm_agent(play_to_gameover=True, stall_limit=3)(
        sess, SimpleNamespace(budget_jumps=40), lambda _: None)
    assert result["reason"] == "win" and sess.steps == 8


def test_pending_native_fuel_animation_is_not_a_static_observation_stall(monkeypatch):
    prompts = []
    stub_model(monkeypatch, "ACTION: advance 20")
    monkeypatch.setattr(llm_agent, "anthropic_complete", lambda system, user, model: prompts.append(user) or "ACTION: advance 20")
    sess = SimulatedSession(terminal_after=12)
    sess.state["economy"] = {"fuel_recovery": {"waiting": True, "can_wait": False, "out_of_fuel": True}}
    result = llm_agent.make_llm_agent(play_to_gameover=True, stall_limit=3)(
        sess, SimpleNamespace(budget_jumps=40), lambda _: None)
    assert result["reason"] == "win" and sess.steps == 12
    assert all("IDENTICAL plan" not in prompt and "state has not changed" not in prompt for prompt in prompts)


def test_refused_jumps_do_not_consume_the_jump_budget(monkeypatch):
    stub_model(monkeypatch, "ACTION: jump 3")
    sess = SimulatedSession()
    result = llm_agent.make_llm_agent(step_mult=3)(
        sess, SimpleNamespace(budget_jumps=2), lambda _: None)
    assert result["jumps"] == 0
    assert sess.steps == 6


def test_backend_failure_is_returned_as_an_error_outcome(monkeypatch):
    stub_model(monkeypatch, "")
    def unavailable(*a, **k):
        raise RuntimeError("model unavailable")
    monkeypatch.setattr(llm_agent, "anthropic_complete", unavailable)
    sess = SimulatedSession()
    result = llm_agent.make_llm_agent()(sess, SimpleNamespace(budget_jumps=2), lambda _: None)
    assert result["status"] == "failed"
    assert result["reason"] == "model_error"
    assert sess.steps == 0


def test_unreadable_observation_ends_with_an_explicit_error(monkeypatch):
    stub_model(monkeypatch, "ACTION: advance 30")
    sess = SimulatedSession()
    def unreadable():
        raise ValueError("corrupt observation")
    monkeypatch.setattr(sess, "observe", unreadable)
    result = llm_agent.make_llm_agent(play_to_gameover=True)(
        sess, SimpleNamespace(budget_jumps=40), lambda _: None)
    assert result["status"] == "failed"
    assert result["reason"] == "observation_error"


def test_codex_sends_large_prompts_on_stdin(monkeypatch):
    calls = {}
    def execute(cmd, **kwargs):
        calls.update(cmd=cmd, **kwargs)
        Path(cmd[cmd.index("-o") + 1]).write_text("ACTION: giveup", encoding="utf-8")
        return SimpleNamespace(returncode=0, stdout="", stderr="")
    monkeypatch.setattr(llm_agent.subprocess, "run", execute)
    monkeypatch.setattr(llm_agent, "_codex_bin", lambda: "codex")
    manual = "x" * 40000
    assert llm_agent.codex_complete(manual, "observation", "test-model") == "ACTION: giveup"
    assert calls["cmd"][-1] == "-"
    assert manual in calls["input"]
    assert all(len(arg) < 1000 for arg in calls["cmd"])


def test_codex_nonzero_exit_rejects_even_a_partial_message(monkeypatch):
    def execute(cmd, **kwargs):
        Path(cmd[cmd.index("-o") + 1]).write_text("partial message", encoding="utf-8")
        return SimpleNamespace(returncode=1, stdout="", stderr="transport failed")
    monkeypatch.setattr(llm_agent.subprocess, "run", execute)
    monkeypatch.setattr(llm_agent, "_codex_bin", lambda: "codex")
    with pytest.raises(RuntimeError, match="transport failed"):
        llm_agent.codex_complete("system", "user", None)


def test_windows_codex_from_wsl_translates_output_and_retains_response_metadata(monkeypatch, tmp_path):
    import os

    calls = []
    output = {}
    native_mkstemp = llm_agent.tempfile.mkstemp

    def create_output(**kwargs):
        assert kwargs["dir"] == str(tmp_path)
        fd, path = native_mkstemp(**kwargs)
        output["path"] = path
        return fd, path

    def execute(cmd, **kwargs):
        calls.append((cmd, kwargs))
        if cmd[0] == "wslpath":
            assert cmd == ["wslpath", "-w", output["path"]]
            return SimpleNamespace(stdout="C:\\visible\\codex-message.txt\n")
        assert cmd[cmd.index("-o") + 1] == "C:\\visible\\codex-message.txt"
        Path(output["path"]).write_text("ACTION: giveup", encoding="utf-8")
        return SimpleNamespace(returncode=0, stdout="", stderr="")

    # Replace this module's OS view only: changing global os.name would make
    # pathlib and pytest select the wrong host path implementation.
    monkeypatch.setattr(llm_agent, "os", SimpleNamespace(
        name="posix", environ={"CODEX_TMPDIR": str(tmp_path)}, close=os.close, unlink=os.unlink))
    monkeypatch.setattr(llm_agent.tempfile, "mkstemp", create_output)
    monkeypatch.setattr(llm_agent.subprocess, "run", execute)
    monkeypatch.setattr(llm_agent, "_codex_bin", lambda: "C:\\Codex\\codex.exe")
    reply = llm_agent.codex_complete("system", "observation", "test-model")
    assert reply == "ACTION: giveup"
    assert reply.metadata["provider"] == "codex"
    assert reply.metadata["model"] == "test-model"
    assert reply.metadata["latency_seconds"] >= 0
    assert len(calls) == 2 and calls[1][0][-1] == "-"
    assert "observation" in calls[1][1]["input"]
    assert not Path(output["path"]).exists()


def test_claude_cli_preserves_multiaction_contract_and_disables_tools(monkeypatch):
    calls = {}
    def execute(cmd, **kwargs):
        calls.update(cmd=cmd, **kwargs)
        return SimpleNamespace(returncode=0, stdout="ACTION:\n  fire 0 3\n  fire 1 3\n  advance 150", stderr="")
    monkeypatch.setattr(llm_agent.subprocess, "run", execute)
    reply = llm_agent.claude_cli_complete("system", "user", "sonnet")
    assert len(llm_agent.parse_plan(reply)[0]) == 2
    assert reply.metadata["provider"] == "claude-cli"
    assert calls["cmd"][:4] == ["claude", "-p", "--tools", ""]
    assert "multi-command" in calls["input"]


def test_anthropic_records_usage_and_uses_its_own_auth_headers(monkeypatch):
    import model_backend
    monkeypatch.setenv("ANTHROPIC_API_KEY", "fixture-key")
    def request(endpoint, body, key, **kwargs):
        assert key == "fixture-key" and kwargs["headers"]["x-api-key"] == key
        assert "Authorization" not in kwargs["headers"]
        return {"stop_reason": "end_turn", "content": [{"type": "text", "text": "ACTION: wait"}]}, {
            "provider": "anthropic", "usage": {"input_tokens": 20, "output_tokens": 3}}
    monkeypatch.setattr(model_backend, "post_json", request)
    reply = llm_agent.anthropic_complete("system", "state", "model")
    assert reply == "ACTION: wait" and reply.metadata["usage"]["input_tokens"] == 20


def test_anthropic_truncated_plans_cannot_be_applied(monkeypatch):
    import model_backend
    monkeypatch.setenv("ANTHROPIC_API_KEY", "fixture-key")
    monkeypatch.setattr(model_backend, "post_json", lambda *a, **k: (
        {"stop_reason": "max_tokens", "content": [{"type": "text", "text": "ACTION: fire"}]}, {}))
    with pytest.raises(RuntimeError, match="did not complete"):
        llm_agent.anthropic_complete("system", "state", "model")
