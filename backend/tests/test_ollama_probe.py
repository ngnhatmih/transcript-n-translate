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
import socket
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


def test_dns_failure_is_unknown_not_down(monkeypatch):
    """API-02/F2 · không phân giải được tên ⇒ CHƯA hỏi được ai ⇒ `unknown`.

    `urlopen` bọc `socket.gaierror` của pha phân giải tên vào `URLError.reason`.
    Nhánh `else` của bản cũ biến nó thành `down`, tức báo một trạng thái CHƯA ĐO
    thành một trạng thái ĐÃ ĐO — đúng thứ docstring của hàm cấm.
    """
    def fake_urlopen(url, timeout=None):
        raise urllib.error.URLError(socket.gaierror(11001, "getaddrinfo failed"))

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)
    assert probe_ollama("http://khong-ton-tai.invalid:11434", timeout=0.1) == "unknown"


def test_empty_host_is_unknown_because_nobody_was_asked():
    """API-02/F2 · host rỗng ⇒ URL không dựng nổi (`'no host given'`).

    Đo THẬT, không mock: `urlopen` ném ngay ở khâu dựng URL nên chưa có câu hỏi
    nào được gửi đi. Bản cũ trả `down` cho ca này, tức lại bịa một sự thật chưa đo.
    """
    assert probe_ollama("") == "unknown"


# ---------------------------------------------------------------------------
# M-10: MỘT resolver URL Ollama — ba đường phải cùng trỏ về `OLLAMA_HOST`
# ---------------------------------------------------------------------------

def test_one_resolver_feeds_the_probe_the_availability_check_and_the_engine(
        monkeypatch):
    """M-10 · đặt `OLLAMA_HOST` ⇒ CẢ BA đường đi đúng host đó, không chỉ một.

    Ba đường này từng mã hoá endpoint riêng và BẤT ĐỒNG: `probe_ollama` (cho
    `/api/status`) đọc env; `ollama_available` ghim `127.0.0.1` ngay lúc ĐỊNH
    NGHĨA hàm; còn `OllamaMtEngine` — cái gọi HTTP thật để dịch — không đọc
    `OLLAMA_HOST` chút nào. Hệ quả trong sản xuất: `available` được tính theo
    env trong khi mọi lời gọi dịch đi `127.0.0.1`, nên mọi engine Ollama đọc
    `available: false` ⇒ tạo job bị 409.

    Hai đường đầu được đo bằng một HTTP server THẬT trên loopback (không mock):
    chúng chỉ trả lời đúng nếu thực sự gọi vào host trong env. Đường thứ ba quan
    sát bằng bản ghi `OllamaMtEngine` — cùng cách
    `tests/test_mt_wiring.py::_RecordingMtEngine` ghim dây nối của composition
    root, vì ở đó địa chỉ là thứ `main.py` TRUYỀN VÀO chứ không phải thứ adapter
    tự đoán.

    `host` của stub KHÔNG có scheme, đúng dạng chính thức của `OLLAMA_HOST`, nên
    phép chuẩn hoá `http://` cũng được đo luôn.
    """
    from app import main
    from app.config import OLLAMA_DEFAULT_BASE_URL, resolve_ollama_base_url
    from app.registry import EngineSpec, ollama_available

    model = "qwen2.5:3b-instruct-q4_K_M"
    with _stub_ollama(f'{{"models": [{{"name": "{model}"}}]}}'.encode()) as host:
        monkeypatch.setenv("OLLAMA_HOST", host)

        assert probe_ollama() == "up", (
            "`/api/status` phải hỏi host trong OLLAMA_HOST, không phải 127.0.0.1"
        )
        assert ollama_available() == {model}, (
            "phép dò availability phải hỏi host trong OLLAMA_HOST và đọc tên "
            "model từ chính phản hồi đó"
        )

        spec = EngineSpec(id="qwen2.5-3b", label="Qwen 3B", kind="mt",
                          runtime="ollama", model_ref=model, vram_mb=2600,
                          langs=("zh", "vi"),
                          capabilities={"available": True, "glossary_prompt": True},
                          opts={})
        seen: list[dict] = []

        class _RecordingMtEngine:
            def __init__(self, *args, **kwargs):
                seen.append({"args": args, "kwargs": kwargs})

        monkeypatch.setattr(main, "OllamaMtEngine", _RecordingMtEngine)
        engines = main._build_mt_engines([spec])  # noqa: SLF001 - chính dây nối

        assert set(engines) == {spec.id}, "engine `available` phải được dựng"
        assert seen and seen[0]["kwargs"].get("base_url") == f"http://{host}", (
            "engine mà composition root dựng phải nhận `base_url` từ CÙNG "
            f"resolver: {seen}"
        )

    # Vế đối chứng: KHÔNG đặt env thì mặc định phải y nguyên (đây là thứ
    # `tests/test_mt_ollama.py:403` ghim trên đường HTTP thật của adapter).
    monkeypatch.delenv("OLLAMA_HOST", raising=False)
    assert resolve_ollama_base_url() == OLLAMA_DEFAULT_BASE_URL == (
        "http://127.0.0.1:11434")
    assert resolve_ollama_base_url("127.0.0.1:9999/") == "http://127.0.0.1:9999", (
        "thiếu `://` thì thêm `http://`, và bỏ `/` cuối"
    )
