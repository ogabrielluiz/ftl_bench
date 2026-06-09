"""Tests for pure, unit-testable helpers in the adapter LLM agent — chiefly _extract_thought,
which captures the model's reasoning for the thoughts log. adapter/ isn't an installed package,
so it's put on sys.path here (mirroring how run_benchmark.py wires it up)."""
import sys
from pathlib import Path

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


def test_command_to_action_unknown_verb_raises():
    with pytest.raises(ValueError):
        llm_agent.command_to_action("frobnicate", [])
