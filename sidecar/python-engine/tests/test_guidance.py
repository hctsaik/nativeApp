"""Operator-facing error guidance (core.guidance)."""

from __future__ import annotations

from core import guidance


def test_connection_refused_maps_to_server_card():
    card = guidance.diagnose("HTTPConnectionPool: Max retries exceeded "
                             "(Caused by ConnectionRefusedError(10061, ...))")
    assert card and "連不上" in card["title"]
    assert any("8765" in s or "測試連線" in s for s in card["steps"])


def test_401_maps_to_auth_card():
    card = guidance.diagnose("server returned HTTP 401 Unauthorized")
    assert card and "認證" in card["title"]
    assert any("token" in s.lower() for s in card["steps"])


def test_missing_tenant_maps_to_register_card():
    card = guidance.diagnose("無可用的外部系統")
    assert card and "Tenant" in card["title"]


def test_timeout_maps_to_timeout_card():
    assert guidance.diagnose("read operation timed out")["title"] == "連線逾時"


def test_already_claimed_maps_to_claimed_card():
    assert guidance.diagnose("此任務已被他人認領（ant_id=A1）")["title"] == "任務已被認領"
    assert guidance.diagnose("ConflictError: task already claimed")["title"] == "任務已被認領"


def test_unknown_error_returns_none():
    assert guidance.diagnose("some totally unrelated ValueError") is None
    assert guidance.diagnose("") is None
    assert guidance.diagnose(None) is None


def test_render_uses_fake_st_and_reports_recognition():
    class _Exp:
        def __enter__(self): return self
        def __exit__(self, *a): return False

    class _FakeSt:
        def __init__(self): self.errors = []
        def error(self, m): self.errors.append(m)
        def caption(self, m): pass
        def markdown(self, m): pass
        def code(self, m): pass
        def expander(self, *a, **k): return _Exp()

    st = _FakeSt()
    assert guidance.render("ConnectionRefusedError 10061", st) is True
    assert st.errors and "連不上" in st.errors[0]
    assert guidance.render("unrelated", _FakeSt()) is False
