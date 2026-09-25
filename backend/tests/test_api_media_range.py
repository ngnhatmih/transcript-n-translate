"""Test của Task 17: `GET /api/media/{source_id}` + HTTP Range.

Brief chỉ kiểm phần Range. Ở đây thêm một nhóm test cho ranh giới AN NINH:
route phục vụ một đường dẫn đến từ DB, nên trước khi mở tệp nó phải CHỨNG MINH
đường dẫn đã phân giải vẫn nằm trong `media_dir`. Thiếu nhóm đó thì một hàng
`media_path` trỏ ra ngoài (`..`, đường dẫn tuyệt đối, symlink/junction) biến
endpoint thành kênh đọc tệp tuỳ ý của máy chủ.
"""
from __future__ import annotations

import os
import pathlib
import subprocess

import pytest
from fastapi.testclient import TestClient

from app.adapters.clock_system import SystemClock
from app.adapters.persist.sqlite_repos import SqliteRepos
from app.api.app import create_app

PAYLOAD = bytes(range(256)) * 4          # 1024 byte xác định
SECRET = b"noi-dung-ngoai-media-dir"


def _make_dir_link(link: pathlib.Path, target: pathlib.Path) -> bool:
    """Tạo 'symlink' thư mục, trả `False` nếu hệ thống không cho.

    Windows từ chối `os.symlink` khi thiếu quyền (SeCreateSymbolicLinkPrivilege —
    đúng trạng thái của phiên chạy test này), nhưng junction thì không cần quyền
    đặc biệt và `Path.resolve()` đi theo nó y như symlink.
    """
    if os.name == "nt":
        proc = subprocess.run(
            ["cmd", "/c", "mklink", "/J", str(link), str(target)],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        )
        return proc.returncode == 0 and link.exists()
    try:
        os.symlink(target, link, target_is_directory=True)
    except OSError:
        return False
    return link.exists()


@pytest.fixture()
def client(tmp_path):
    media = tmp_path / "media"
    media.mkdir()
    video = media / "clip.mp4"
    video.write_bytes(PAYLOAD)

    repos = SqliteRepos(tmp_path / "t.db", clock=SystemClock())
    repos.init_schema()
    sid = repos.add_source(kind="file", origin="clip.mp4", media_path=str(video), lang="zh")

    app = create_app(repos=repos, specs=[], media_dir=media, out_dir=tmp_path / "o")
    with TestClient(app) as c:
        c.source_id = sid       # type: ignore[attr-defined]
        c.repos = repos         # type: ignore[attr-defined]
        c.media = media         # type: ignore[attr-defined]
        c.tmp = tmp_path        # type: ignore[attr-defined]
        yield c


def _add_source(client, media_path) -> int:
    return client.repos.add_source(
        kind="file", origin=pathlib.Path(str(media_path)).name,
        media_path=str(media_path), lang="zh",
    )


def _secret_file(client) -> pathlib.Path:
    """Tệp THẬT nằm NGOÀI `media_dir` — thứ không bao giờ được phục vụ."""
    outside = client.tmp / "ngoai"
    outside.mkdir(exist_ok=True)
    secret = outside / "secret.mp4"
    secret.write_bytes(SECRET)
    return secret


# --------------------------------------------------------------------------
# Tải toàn tệp
# --------------------------------------------------------------------------

def test_full_download_advertises_range_support(client):
    resp = client.get(f"/api/media/{client.source_id}")
    assert resp.status_code == 200, resp.text
    assert resp.headers["accept-ranges"] == "bytes"
    assert resp.content == PAYLOAD
    assert resp.headers["content-length"] == "1024"
    assert resp.headers["content-type"].startswith("video/mp4")

def test_head_matches_get_without_a_body(client):
    """RFC 9110 §9.3.2: nơi phục vụ GET thì phải phục vụ HEAD.

    `curl -I` hay trình phát hỏi trước kích thước/`Accept-Ranges` mà không tải
    phải nhận 405 nếu route chỉ khai `GET`: FastAPI `APIRoute` KHÔNG tự thêm HEAD
    như `Route` của Starlette. Câu trả lời phải GIỐNG GET ở status và header,
    chỉ khác thân rỗng.
    """
    get = client.get(f"/api/media/{client.source_id}")
    head = client.head(f"/api/media/{client.source_id}")

    assert head.status_code == get.status_code == 200, head.text
    assert head.content == b""
    for name in ("accept-ranges", "content-type", "content-length"):
        assert head.headers[name] == get.headers[name], name
    assert head.headers["content-length"] == "1024"


def test_range_request_returns_206_with_exact_slice(client):
    resp = client.get(f"/api/media/{client.source_id}", headers={"Range": "bytes=0-99"})
    assert resp.status_code == 206, resp.text
    assert resp.content == PAYLOAD[:100]
    assert resp.headers["content-range"] == "bytes 0-99/1024"
    assert resp.headers["content-length"] == "100"
    assert resp.headers["accept-ranges"] == "bytes"


def test_open_ended_range(client):
    resp = client.get(f"/api/media/{client.source_id}", headers={"Range": "bytes=1000-"})
    assert resp.status_code == 206, resp.text
    assert resp.content == PAYLOAD[1000:]
    assert resp.headers["content-range"] == "bytes 1000-1023/1024"


def test_suffix_range_returns_last_bytes(client):
    """Trình phát của trình duyệt dùng dạng này để đọc moov atom ở cuối mp4."""
    resp = client.get(f"/api/media/{client.source_id}", headers={"Range": "bytes=-64"})
    assert resp.status_code == 206, resp.text
    assert resp.content == PAYLOAD[-64:]
    assert resp.headers["content-range"] == "bytes 960-1023/1024"


def test_suffix_longer_than_the_file_returns_the_whole_file(client):
    """`bytes=-5000` trên tệp 1024 byte là CẢ tệp, không phải start âm.

    RFC 7233 §2.1: hậu tố dài hơn tệp thì lấy từ byte 0. Một `size - length`
    trần trụi cho start = -3976 rồi `seek(-3976)` — hoặc nổ, hoặc trả rác.
    """
    resp = client.get(f"/api/media/{client.source_id}", headers={"Range": "bytes=-5000"})
    assert resp.status_code == 206, resp.text
    assert resp.content == PAYLOAD
    assert resp.headers["content-range"] == "bytes 0-1023/1024"


def test_range_ending_past_eof_is_clamped(client):
    resp = client.get(f"/api/media/{client.source_id}", headers={"Range": "bytes=1000-5000"})
    assert resp.status_code == 206, resp.text
    assert resp.content == PAYLOAD[1000:]
    assert resp.headers["content-range"] == "bytes 1000-1023/1024"


def test_a_range_spanning_several_chunks_is_served_whole(client):
    """Một khối là 256 KB; khoảng 2,5 khối phải ra ĐỦ byte và đúng thứ tự.

    Vòng lặp chỉ đọc một khối (hoặc quên `seek`) vẫn qua được mọi test nhỏ ở
    trên vì tệp 1024 byte nằm gọn trong một khối.
    """
    big = bytes((i * 7 + 3) % 251 for i in range(600 * 1024 + 123))
    path = client.media / "to.mp4"
    path.write_bytes(big)
    sid = _add_source(client, path)

    start, end = 1024, 550 * 1024
    resp = client.get(f"/api/media/{sid}", headers={"Range": f"bytes={start}-{end}"})
    assert resp.status_code == 206, resp.text
    assert resp.content == big[start:end + 1]
    assert resp.headers["content-length"] == str(end - start + 1)


def test_unsatisfiable_range_returns_416_with_total(client):
    resp = client.get(f"/api/media/{client.source_id}", headers={"Range": "bytes=5000-6000"})
    assert resp.status_code == 416, resp.text
    assert resp.headers["content-range"] == "bytes */1024"
    assert resp.headers["accept-ranges"] == "bytes"


def test_reversed_range_is_416_with_total(client):
    """`start > end` là khoảng KHÔNG hợp lệ (RFC 7233 §2.1) -> 416, không phải
    một `end - start + 1` âm chảy xuống `Content-Length`.

    Không có test HTTP nào cho nhánh này: bỏ guard `start > end` chỉ giết đúng
    một dòng của bảng tham số hoá `parse_range`, nên nhánh không được ghim ở
    tầng giao thức.
    """
    resp = client.get(f"/api/media/{client.source_id}",
                      headers={"Range": "bytes=500-100"})
    assert resp.status_code == 416, resp.text
    assert resp.headers["content-range"] == "bytes */1024"
    assert resp.headers["accept-ranges"] == "bytes"
    assert resp.content == b""


def test_range_unit_is_case_insensitive(client):
    """`BYTES=` là cùng một range unit: token không phân biệt hoa thường.

    RFC 7233 §2.1 định nghĩa range unit là một `token`, và RFC 9110 §2.2 khiến
    token không phân biệt hoa/thường. Regex đang khớp `bytes=` chữ thường, nên
    `BYTES=0-99` rơi vào nhánh "header không hiểu được" -> 200 cả tệp: một yêu
    cầu range hợp lệ bị bỏ im lặng thay vì trả 206.
    """
    resp = client.get(f"/api/media/{client.source_id}",
                      headers={"Range": "BYTES=0-99"})
    assert resp.status_code == 206, f"BYTES= bị bỏ qua: {resp.status_code}"
    assert resp.content == PAYLOAD[:100]
    assert resp.headers["content-range"] == "bytes 0-99/1024"

    # Các dạng hoa thường khác của cùng một header phải cho cùng câu trả lời.
    mixed = client.get(f"/api/media/{client.source_id}",
                       headers={"Range": "Bytes=0-99"})
    assert mixed.status_code == 206, mixed.text
    assert mixed.content == PAYLOAD[:100]


def test_malformed_range_header_is_ignored_not_fatal(client):
    resp = client.get(f"/api/media/{client.source_id}", headers={"Range": "banana"})
    assert resp.status_code == 200, resp.text
    assert resp.content == PAYLOAD


def test_empty_header_value_is_ignored(client):
    resp = client.get(f"/api/media/{client.source_id}", headers={"Range": ""})
    assert resp.status_code == 200, resp.text
    assert resp.content == PAYLOAD


# --------------------------------------------------------------------------
# Tệp rỗng
# --------------------------------------------------------------------------

def test_empty_file_downloads_as_zero_bytes(client):
    empty = client.media / "rong.mp4"
    empty.write_bytes(b"")
    sid = _add_source(client, empty)

    resp = client.get(f"/api/media/{sid}")
    assert resp.status_code == 200, resp.text
    assert resp.content == b""
    assert resp.headers["content-length"] == "0"


def test_range_of_an_empty_file_is_416(client):
    empty = client.media / "rong.mp4"
    empty.write_bytes(b"")
    sid = _add_source(client, empty)

    resp = client.get(f"/api/media/{sid}", headers={"Range": "bytes=0-"})
    assert resp.status_code == 416, resp.text
    assert resp.headers["content-range"] == "bytes */0"


# --------------------------------------------------------------------------
# 404 / 410
# --------------------------------------------------------------------------

def test_unknown_source_is_404(client):
    assert client.get("/api/media/9999").status_code == 404


def test_missing_file_on_disk_is_410(client):
    missing = client.media / "bien-mat.mp4"
    sid = _add_source(client, missing)
    assert client.get(f"/api/media/{sid}").status_code == 410


def test_a_directory_is_never_served(client):
    """`media_path` trỏ vào một thư mục (nằm TRONG media_dir) là 410, không 500."""
    sid = _add_source(client, client.media)
    resp = client.get(f"/api/media/{sid}")
    assert resp.status_code == 410, resp.text


# --------------------------------------------------------------------------
# Ranh giới thư mục media (brief không có, nhưng đây là phần nguy hiểm nhất)
# --------------------------------------------------------------------------

def test_file_outside_the_media_root_is_refused(client):
    sid = _add_source(client, _secret_file(client))
    resp = client.get(f"/api/media/{sid}")
    assert resp.status_code == 403, resp.text
    assert SECRET not in resp.content


def test_the_403_body_does_not_disclose_server_paths(client, caplog):
    """Từ chối tệp ngoài gốc thì câu từ chối KHÔNG được liệt kê gốc media hay
    đường dẫn đã phân giải: endpoint tồn tại để chối, nên chính nó không được
    xác nhận vị trí tệp mà client không được phép gọi tên.

    Chi tiết vẫn phải còn cho người vận hành — chỉ đổi chỗ: server log.
    """
    import logging

    secret = _secret_file(client)
    sid = _add_source(client, secret)
    leaked = {str(client.media.resolve()), str(secret.resolve())}

    # `caplog` chỉ bắt được record từ logger của route nếu mức đó được ghi lại;
    # hạ mức trong lúc test rồi trả lại như cũ để không đổi test khác.
    logger = logging.getLogger("app.api.routes_media")
    old_level = logger.level
    logger.setLevel(logging.WARNING)
    try:
        resp = client.get(f"/api/media/{sid}")
    finally:
        logger.setLevel(old_level)

    assert resp.status_code == 403, resp.text
    for path in leaked:
        assert path not in resp.text, f"thân 403 lộ đường dẫn {path}"
    assert str(client.media.resolve()) not in resp.text
    assert secret.name not in resp.text
    # Bí mật phải nằm ở log, không phải ở câu trả lời.
    logged = "\n".join(r.getMessage() for r in caplog.records)
    assert str(secret.resolve()) in logged
    assert str(client.media.resolve()) in logged


def test_dotdot_cannot_escape_the_media_root(client):
    secret = _secret_file(client)
    sid = _add_source(client, client.media / ".." / "ngoai" / "secret.mp4")
    assert secret.exists(), "phép so phải là đường dẫn ĐÃ phân giải"

    resp = client.get(f"/api/media/{sid}")
    assert resp.status_code == 403, resp.text
    assert SECRET not in resp.content


def test_source_with_a_separate_drive_is_refused(client):
    """Đường dẫn ở ổ đĩa khác: `relative_to` ném ValueError, không được thành 500."""
    if os.name != "nt":
        pytest.skip("chỉ có ý nghĩa trên Windows")
    sid = _add_source(client, "D:\\media\\secret.mp4")
    resp = client.get(f"/api/media/{sid}")
    assert resp.status_code == 403, resp.text


def test_symlink_inside_the_media_root_pointing_outside_is_refused(client):
    """`media_dir` là thư mục do máy chủ sở hữu, nhưng nó có thể chứa link.

    Một junction/symlink nằm TRONG `media_dir` trỏ ra ngoài vượt qua mọi phép so
    chuỗi tiền tố; chỉ `Path.resolve()` mới lộ ra đích thật.
    """
    secret = _secret_file(client)
    link = client.media / "link-ngoai"
    if not _make_dir_link(link, secret.parent):
        pytest.skip("hệ thống không cho tạo symlink/junction")

    sid = _add_source(client, link / "secret.mp4")
    resp = client.get(f"/api/media/{sid}")
    assert resp.status_code == 403, resp.text
    assert SECRET not in resp.content


# --------------------------------------------------------------------------
# Hàm thuần: khoá hợp đồng của phần Range, không đi qua HTTP
# --------------------------------------------------------------------------

def test_parse_range_reads_both_ends_and_the_suffix_form():
    from app.api.routes_media import UNSATISFIABLE, parse_range

    assert parse_range("bytes=0-99", 1024) == (0, 99)
    assert parse_range("bytes=0-0", 1024) == (0, 0)
    assert parse_range("bytes=1000-", 1024) == (1000, 1023)
    assert parse_range("bytes=-64", 1024) == (960, 1023)
    # Hậu tố dài hơn tệp -> cả tệp (RFC 7233), KHÔNG phải start âm.
    assert parse_range("bytes=-5000", 1024) == (0, 1023)
    # End vượt EOF thì cắt về byte cuối cùng.
    assert parse_range("bytes=1000-5000", 1024) == (1000, 1023)
    assert UNSATISFIABLE == "unsatisfiable"


@pytest.mark.parametrize("header", [
    "banana", "bytes=", "items=0-10", "bytes=0-99,200-299", "bytes=--5", "",
])
def test_parse_range_ignores_headers_it_does_not_understand(header):
    """Header lạ -> `None` (bỏ qua, trả 200 toàn tệp), KHÔNG phải 416."""
    from app.api.routes_media import parse_range

    assert parse_range(header, 1024) is None


@pytest.mark.parametrize("header", ["bytes=5000-6000", "bytes=1024-", "bytes=5-3", "bytes=-0"])
def test_parse_range_marks_unsatisfiable_requests(header):
    from app.api.routes_media import UNSATISFIABLE, parse_range

    assert parse_range(header, 1024) == UNSATISFIABLE


def test_parse_range_on_an_empty_file_is_never_satisfiable():
    from app.api.routes_media import UNSATISFIABLE, parse_range

    assert parse_range("bytes=0-", 0) == UNSATISFIABLE
    assert parse_range("bytes=-1", 0) == UNSATISFIABLE


# --------------------------------------------------------------------------
# Hàm thuần: ranh giới thư mục
# --------------------------------------------------------------------------

def test_resolve_within_accepts_paths_inside_the_root(tmp_path):
    from app.domain.paths import resolve_within

    root = tmp_path / "media"
    root.mkdir()
    inside = root / "sub" / "clip.mp4"
    inside.parent.mkdir()
    inside.write_bytes(PAYLOAD)

    assert resolve_within(root, inside) == inside.resolve()
    # `..` mà đích cuối vẫn nằm trong gốc là hợp lệ: `media/sub/../clip.mp4`
    # phân giải về `media/clip.mp4` (KHÔNG bị từ chối chỉ vì có `..`).
    assert resolve_within(root, root / "sub" / ".." / "clip.mp4") == (root / "clip.mp4").resolve()
    assert resolve_within(root, root / "sub" / ".." / "sub" / "clip.mp4") == inside.resolve()


@pytest.mark.parametrize("escape", ["../ngoai/secret.mp4", "sub/../../ngoai/secret.mp4"])
def test_resolve_within_refuses_dotdot_escapes(tmp_path, escape):
    from app.domain.paths import PathOutsideRoot, resolve_within

    root = tmp_path / "media"
    (root / "sub").mkdir(parents=True)
    outside = tmp_path / "ngoai"
    outside.mkdir()
    (outside / "secret.mp4").write_bytes(SECRET)

    with pytest.raises(PathOutsideRoot):
        resolve_within(root, root / escape)


def test_resolve_within_refuses_an_absolute_path_outside(tmp_path):
    from app.domain.paths import PathOutsideRoot, resolve_within

    root = tmp_path / "media"
    root.mkdir()
    secret = tmp_path / "ngoai" / "secret.mp4"
    secret.parent.mkdir()
    secret.write_bytes(SECRET)

    with pytest.raises(PathOutsideRoot):
        resolve_within(root, secret)
    # Đường dẫn gốc của chính nó không phải là "ở trong" theo nghĩa phục vụ được
    # (route còn phải thấy đó là TỆP), nhưng phép kiểm ranh giới không được ném.
    assert resolve_within(root, root) == root.resolve()


def test_resolve_within_follows_a_link_out_of_the_root(tmp_path):
    from app.domain.paths import PathOutsideRoot, resolve_within

    root = tmp_path / "media"
    root.mkdir()
    outside = tmp_path / "ngoai"
    outside.mkdir()
    (outside / "secret.mp4").write_bytes(SECRET)
    link = root / "link-ngoai"
    if not _make_dir_link(link, outside):
        pytest.skip("hệ thống không cho tạo symlink/junction")

    with pytest.raises(PathOutsideRoot):
        resolve_within(root, link / "secret.mp4")


# --------------------------------------------------------------------------
# Hợp đồng về luồng: không đọc tệp trên event loop
# --------------------------------------------------------------------------

def test_the_media_endpoint_is_sync_so_fastapi_runs_it_in_a_threadpool():
    """`async def` + `open()`/`seek()`/`stat()` chặn = event loop đứng cho MỌI
    request khác trong lúc đọc đĩa. Endpoint phải là `def` (FastAPI đẩy sang
    threadpool), và thân 206 lặp trong threadpool qua `StreamingResponse`.
    """
    import inspect

    from app.api.routes_media import get_media

    assert not inspect.iscoroutinefunction(get_media), (
        "endpoint media phải là `def`, không phải `async def`")
