from __future__ import annotations

import socket
import sys
import threading
import time

import pytest

from engine import wait_for_port


def test_returns_true_when_port_listening() -> None:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as srv:
        srv.bind(("127.0.0.1", 0))
        port = srv.getsockname()[1]
        srv.listen(1)
        assert wait_for_port(port, timeout=5.0) is True


def test_returns_false_when_nothing_listening() -> None:
    # Bind and immediately close to get a port number that is not in use.
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]

    assert wait_for_port(port, timeout=0.5) is False


@pytest.mark.xfail(sys.platform == "win32", reason="Windows TCP stack refuses bound-not-listening ports immediately, race condition not reproducible")
def test_returns_true_after_delayed_listen() -> None:
    # Server binds immediately (reserving the port) but delays calling listen().
    # wait_for_port must retry until listen() is called.
    port_known = threading.Event()
    port_holder: list[int] = []

    def delayed_serve() -> None:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as srv:
            srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            srv.bind(("127.0.0.1", 0))
            port_holder.append(srv.getsockname()[1])
            port_known.set()
            time.sleep(0.4)
            srv.listen(1)
            srv.settimeout(5)
            try:
                conn, _ = srv.accept()
                conn.close()
            except OSError:
                pass

    t = threading.Thread(target=delayed_serve, daemon=True)
    t.start()
    port_known.wait(timeout=2)
    result = wait_for_port(port_holder[0], timeout=5.0, interval=0.1)
    t.join(timeout=2)
    assert result is True
