from types import SimpleNamespace

from ftl_bench.session import AgentSession


def test_menu_read_race_does_not_issue_in_game_reset(tmp_path, monkeypatch):
    session = AgentSession(tmp_path)
    menu = SimpleNamespace(game_started=False)
    calls = []
    monkeypatch.setattr(session, "observe", lambda: (_ for _ in ()).throw(PermissionError("sharing")))
    monkeypatch.setattr(session, "_wait_for", lambda predicate, **kwargs: menu)
    monkeypatch.setattr(session, "start_game", lambda mode, seed: calls.append((mode, seed)) or "started")
    monkeypatch.setattr(session, "_write_action_atomic", lambda payload: calls.append(payload))
    assert session.reset_episode(seed=7) == "started"
    assert calls == [("new", 7)]


def test_unreadable_reset_never_dispatches_blindly(tmp_path, monkeypatch):
    import pytest
    session = AgentSession(tmp_path)
    calls = []
    monkeypatch.setattr(session, "observe", lambda: (_ for _ in ()).throw(PermissionError("sharing")))
    monkeypatch.setattr(session, "_wait_for", lambda *args, **kwargs: (_ for _ in ()).throw(TimeoutError("unreadable")))
    monkeypatch.setattr(session, "_write_action_atomic", lambda payload: calls.append(payload))
    with pytest.raises(TimeoutError, match="unreadable"):
        session.reset_episode(seed=7)
    assert calls == []



def reset_stream(tmp_path, monkeypatch, observations):
    """Exercise real reset polling and the real dispatched packet without a game."""
    import json
    session = AgentSession(tmp_path, poll_interval=0)
    session.action_seq = 4
    monkeypatch.setattr(session, "observe", lambda: SimpleNamespace(game_started=True))
    monkeypatch.setattr(session, "_sync_seq", lambda: None)
    sequence = iter(observations)
    monkeypatch.setattr(session.client, "read_latest", lambda: next(sequence))
    result = session.reset_episode(seed=7)
    packet = json.loads(session.action_path.read_text())
    assert packet == {"seq": 5, "advance_frames": 0, "actions": [{"type": "reset_episode", "seed": 7}]}
    return result


def test_headless_reset_marker_admits_new_run_without_observing_brief_menu(tmp_path, monkeypatch):
    old = SimpleNamespace(game_started=True, raw={"reset_done_seq": 4})
    new = SimpleNamespace(game_started=True, raw={"reset_done_seq": 5})
    assert reset_stream(tmp_path, monkeypatch, [old, new]) is new


def test_legacy_reset_requires_menu_before_accepting_started_state(tmp_path, monkeypatch):
    old = SimpleNamespace(game_started=True, raw={})
    menu = SimpleNamespace(game_started=False, raw={})
    new = SimpleNamespace(game_started=True, raw={})
    assert reset_stream(tmp_path, monkeypatch, [old, menu, new]) is new


def test_reset_marker_must_match_current_dispatch_even_after_menu(tmp_path, monkeypatch):
    menu = SimpleNamespace(game_started=False, raw={"reset_done_seq": 4})
    stale = SimpleNamespace(game_started=True, raw={"reset_done_seq": 4})
    new = SimpleNamespace(game_started=True, raw={"reset_done_seq": 5})
    assert reset_stream(tmp_path, monkeypatch, [menu, stale, new]) is new
