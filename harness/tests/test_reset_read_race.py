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
