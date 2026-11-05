"""`POST /api/subtitles/lines` — chỗ giao diện HỎI bẻ dòng (ERRATA #73).

Vì sao có route này: bản burn bẻ dòng bằng Pillow, còn bản xem trước trên web từng bẻ
bằng `canvas.measureText` của trình duyệt. Hai bộ đo lệch ~10 % bề ngang chữ ở đúng chỗ
quyết định bẻ dòng, nên cùng một câu ra SỐ DÒNG khác nhau — đo được với `co 91`:

    burn  2 dòng 919 + 345   → hộp 938 × 180
    xem   3 dòng 872/947/122 → hộp 969 × 214

Nay giao diện hỏi route này, nên hai bên dùng CHUNG một phép bẻ.
"""
from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api import routes_subtitles


def _client() -> TestClient:
    app = FastAPI()
    app.include_router(routes_subtitles.router)
    return TestClient(app)


def test_tra_du_hinh_dang_ma_giao_dien_doc():
    """Hợp đồng: `lines/rong/cao/co/vien/le/rong_kha_dung` — `PhuDeOverlay` đọc đúng chúng."""
    with _client() as c:
        r = c.post("/api/subtitles/lines", json={
            "text": "Xin chào",
            "khung": [1080, 1920],
            "style": {"co": 91, "vien": 20, "dam": True},
        })
    assert r.status_code == 200, r.text
    d = r.json()
    assert set(d) == {"lines", "rong", "cao", "co", "vien", "le", "rong_kha_dung"}, d
    assert isinstance(d["lines"], list) and d["lines"], "luôn có ít nhất một dòng"
    assert "".join(d["lines"]), "không được trả danh sách dòng rỗng"
    # Cỡ chữ / viền / lề là số ĐÃ NHÂN TỈ LỆ theo khung, đúng như `to_ass`:
    # 1080×1920 -> tiLe = 0,5625 -> co 91 -> 51, vien 20 -> 11.
    assert d["co"] == 51, f"co phải là 91 × 0,5625 = 51, đo được {d['co']}"
    assert d["vien"] == 11, f"vien phải là 20 × 0,5625 = 11, đo được {d['vien']}"


def test_khong_co_font_thi_tra_MOT_dong_chu_khong_bo_cau(monkeypatch):
    """Máy không có file font: KHÔNG đo được, nhưng KHÔNG được bỏ câu.

    `_do_khoi_chu` trả `(0, 0, 0, [])` khi thiếu font. Route phải trả nguyên câu thành một
    dòng, `rong = 0` — bên gọi thấy `rong == 0` thì giữ đường dự phòng, không vẽ hộp rỗng.

    ⚠️ Chặn `_duong_font`, KHÔNG chỉ `_FONT_CHO_DUONG`: từ ERRATA #79 phép đo còn một đường
    dự phòng trong repo (`backend/app/assets/fonts`), nên làm rỗng bảng đường hệ thống là
    chưa đủ để mô phỏng máy không có font — và bài test sẽ kiểm nhầm điều nó tuyên bố.
    """
    from app.domain import subtitle_format as sf

    monkeypatch.setattr(sf, "_duong_font", lambda font: None)
    with _client() as c:
        r = c.post("/api/subtitles/lines", json={
            "text": "Xin chào các bạn", "khung": [1080, 1920], "style": {"co": 54},
        })
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["lines"] == ["Xin chào các bạn"], d["lines"]
    assert d["rong"] == 0, "không đo được thì rong = 0, KHÔNG phải một con số bịa"
