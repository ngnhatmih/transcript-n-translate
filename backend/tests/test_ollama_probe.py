"""API-02 (M5): `probe_ollama` phải phân loại ĐÚNG ba trạng thái up/down/unknown.

Hai lỗi của bản cũ, cả hai đều đo được trên máy này:

* `OLLAMA_HOST` chính thức của Ollama là dạng `host:port` KHÔNG có scheme. Thiếu
  `http://`, `urllib` không có handler cho kiểu URL đó và ném
  `URLError('unknown url type: 127.0.0.1')` ⇒ một Ollama ĐANG CHẠY vẫn bị báo
  `down`.
* `urlopen` bọc MỌI lỗi của tầng vận chuyển vào `URLError.reason`, kể cả
  `socket.timeout` của pha KẾT NỐI. Timeout là "chưa đo được", không phải "đang
  tắt": docstring của hàm nói rõ `unknown` phải giữ nguyên nghĩa đó, nên bản cũ
  đang bịa ra một sự thật chưa đo.

Không bài nào cần mạng thật: "Ollama" sống là một `http.server` trên loopback,
còn nhánh phân loại được ghim bằng `urlopen` giả. Lý do phải giả cho ca
`ConnectionRefusedError`: trên máy này SYN tới một cổng đóng trên loopback bị
drop nên nó thành TIMEOUT (đo được), tức không có cách nào tạo một lần "connection
refused" thật một cách ổn định.
"""
from __future__ import annotations

import contextlib
import http.server
import threading
import urllib.error
import urllib.request

import pytest

from app.api.routes_registry import probe_ollama


class _StubHandler(http.server.BaseHTTPRequestHandler):
    body = b'{"models": []}'

    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-Length", str(len(self.body)))
        self.end_headers()
        self.wfile.write(self.body)

    def log_message(self, *args):  # pragma: no cover - pytest không cần log HTTP
        pass


@contextlib.contextmanager
def _stub_ollama(body: bytes):
    """Một 'Ollama' sống trên loopback, trả `body` cho mọi GET."""
    handler = type("_Stub", (_StubHandler,), {"body": body})
    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        yield f"127.0.0.1:{server.server_address[1]}"
    finally:
        server.shutdown()
        server.server_close()


@pytest.fixture(autouse=True)
def _no_ambient_ollama_host(monkeypatch):
    """`probe_ollama` đọc `OLLAMA_HOST` từ môi trường và ĐÈ tham số `host`."""
    monkeypatch.delenv("OLLAMA_HOST", raising=False)


def test_bare_host_port_reaches_a_live_stub():
    """Ca lỗi thứ nhất: dạng `host:port` của Ollama phải được chuẩn hoá."""
    with _stub_ollama(b'{"models": []}') as host:
        assert probe_ollama(host) == "up"


def test_full_url_still_reaches_a_live_stub():
    with _stub_ollama(b'{"models": []}') as host:
        assert probe_ollama(f"http://{host}") == "up"


def test_non_json_body_from_a_live_stub_is_unknown():
    with _stub_ollama(b"<html>khong phai JSON</html>") as host:
        assert probe_ollama(host) == "unknown"


def test_url_is_normalised_before_the_request(monkeypatch):
    """Ghim THẲNG URL được ghép: thiếu `http://` là `URLError` giả `down`."""
    seen: list[str] = []

    class _Response:
        def read(self):
            return b'{"models": []}'

        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

    def fake_urlopen(url, timeout=None):
        seen.append(url)
        return _Response()

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)
    assert probe_ollama("127.0.0.1:11434") == "up"
    assert seen == ["http://127.0.0.1:11434/api/tags"]


def test_connect_timeout_is_unknown_not_down(monkeypatch):
    """Ca lỗi thứ hai: `urlopen` bọc timeout của pha kết nối vào `URLError`."""
    def fake_urlopen(url, timeout=None):
        raise urllib.error.URLError(TimeoutError("timed out"))

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)
    assert probe_ollama("http://192.0.2.1:11434", timeout=0.1) == "unknown"


def test_refused_connection_is_down(monkeypatch):
    def fake_urlopen(url, timeout=None):
        raise urllib.error.URLError(ConnectionRefusedError(10061, "refused"))

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)
    assert probe_ollama("http://127.0.0.1:11434", timeout=0.1) == "down"


def test_read_timeout_is_unknown(monkeypatch):
    """Timeout ở pha ĐỌC không bị bọc: `TimeoutError` trần ⇒ `unknown`."""
    def fake_urlopen(url, timeout=None):
        raise TimeoutError("timed out")

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)
    assert probe_ollama("http://127.0.0.1:11434", timeout=0.1) == "unknown"
