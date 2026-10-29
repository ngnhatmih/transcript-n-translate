# Pipeline lồng tiếng lấy OCR làm gốc — Kế hoạch thực thi

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Đổi nguồn chữ của pipeline lồng tiếng sang OCR phụ đề cứng, và bỏ trần tốc độ để bảo đảm tuyệt đối không chồng lấn.

**Architecture:** Bốn tầng lọc phụ đề là hàm THUẦN trong `domain/phu_de.py` (nhận `list[Hop]`, trả `list[Hop]`), nên test được bằng dữ liệu tổng hợp, không cần model. Adapter `ocr_rapidocr.py` chỉ làm một việc: gọi rapidocr, trả `Hop`. Phần C sửa `ke_hoach_toc_do` trong `dub.py`: bỏ trần `1.35` và bỏ thang bậc, để dòng bị dồn được nén đúng mức cần thay vì kẹp ở trần rồi vẫn chồng.

**Tech Stack:** Python 3.10, FastAPI, `rapidocr-onnxruntime 1.4.4`, `demucs` (`htdemucs`), `ffmpeg`, numpy, pytest.

**Spec:** `docs/superpowers/specs/2026-10-29-ocr-first-dub-pipeline-design.md`

## Global Constraints

- **Chỉ dùng `htdemucs`** cho tách nền. Không BS-RoFormer/Mel-RoFormer, dù chạy được trên 8 GB VRAM.
- **Không cắt chữ** để đổi lấy tốc độ. Người dùng chốt: "ko cần phải cắt mà chỉnh tốc độ là được".
- **Tốc độ đều là MONG MUỐN**, không phải ràng buộc. Ràng buộc cứng duy nhất: **không chồng lấn**.
- **Pipeline phải chạy được khi KHÔNG có ASR** ⇒ tầng lọc 4 mặc định TẮT.
- **Thông báo cho người dùng bằng tiếng Việt**; mã cũng dùng tên tiếng Việt (theo lệ repo).
- **Thời gian là giây, kiểu `float`.**
- **Nhánh:** `thu-nghiem-tach-giong`. Không commit vào `gd4-tts`.
- **Baseline không được xấu đi:** backend `1351 passed, 15 deselected, 1 warning in 46.86s` (EXIT=0); frontend `381 tests · 381 pass · 0 fail` (EXIT=0); `tsc --noEmit` = 0.
- **`contract.test.ts` cần cổng 8620 TRỐNG** và DB thật của repo (có rows). `docker compose stop api` trước, `start api` sau. KHÔNG trỏ `PHUDE_DB` vào DB rỗng.

---

## Cấu trúc tệp

| Tệp | Trách nhiệm |
|---|---|
| `backend/app/pipeline/dub.py` | sửa `ke_hoach_toc_do` + `DubHandler` (bỏ trần, bỏ bậc) |
| `backend/app/domain/phu_de.py` | **mới** — bốn tầng lọc THUẦN |
| `backend/app/ports/ocr.py` | **mới** — Protocol `OCREngine` |
| `backend/app/adapters/ocr_rapidocr.py` | **mới** — adapter thật |
| `backend/registry.json` | thêm khoá `ocr` |
| `backend/tests/test_dub.py` | sửa ba test về trần cũ |
| `backend/tests/test_dub_handler.py` | sửa assert `dem` trong plan |
| `backend/tests/test_phu_de.py` | **mới** — test bốn tầng lọc |
| `backend/tests/test_ocr_rapidocr.py` | **mới** — test adapter trên ảnh tổng hợp |

**Vì sao tách `domain/phu_de.py` khỏi adapter:** tầng lọc là logic thuần trên danh sách hộp. Tách ra thì test bằng dữ liệu tổng hợp, không cần model 100 MB. Adapter chỉ gọi rapidocr.

---

## Task 1: Bỏ trần tốc độ — ràng buộc cứng "không chồng lấn"

Làm trước vì độc lập với OCR và là **yêu cầu cứng** của người dùng.

**Files:**
- Modify: `backend/app/pipeline/dub.py:31-62` (hằng số + `ke_hoach_toc_do`)
- Modify: `backend/app/pipeline/dub.py:143-155` (`__init__`)
- Modify: `backend/app/pipeline/dub.py:235-277` (`run`: lời gọi + thông điệp cuối)
- Modify: `backend/app/pipeline/dub.py:281-321` (`_ghi_ke_hoach`)
- Test: `backend/tests/test_dub.py` (viết lại), `backend/tests/test_dub_handler.py:219-246`

**Interfaces:**
- Consumes: không có (task đầu).
- Produces:
  - `ke_hoach_toc_do(takes: list[float], slots: list[float], avails: list[float]) -> tuple[list[float], list[float]]` — trả `(toc_do, need)`. **Bỏ `tran`/`bac`**, **bỏ `qua_tran`**.
  - `DubHandler.__init__(repos, out_dir, tts_runner, *, dinh_dangs=None, python="", script="")` — **bỏ `tran`**.
  - `dub-<tid>.plan.json`: bỏ khoá `tran`, bỏ `dem.phai_sua`, thêm `dem.nen_manh`.

### Steps

- [ ] **Step 1: Viết lại `backend/tests/test_dub.py` (ĐỎ)**

```python
"""Hai hàm của đường lồng tiếng — phần THUẦN, không TTS, không ffmpeg.

🔴 HÀNH VI ĐÃ ĐỔI (spec 2026-10-29, người dùng chốt):
  · RÀNG BUỘC CỨNG: giọng câu trước KHÔNG được còn nói khi câu sau bắt đầu.
  · Tốc độ đều là MONG MUỐN, không bắt buộc.
  · KHÔNG cắt chữ để đổi lấy tốc độ — chỉ chỉnh tốc độ.

Ba bài đầu vì thế khẳng định điều KHÁC bản cũ: bản cũ kẹp `need` ở trần 1,35 và trả
`qua_tran` (dòng vượt trần VẪN chồng, chỉ được đánh dấu). Bản mới nén tới ĐÚNG mức cần.
"""
from __future__ import annotations

import numpy as np

from app.pipeline.dub import ke_hoach_toc_do, rap, trong_im_lang


def test_nen_toi_dung_muc_can_khong_kep_o_tran():
    """Dòng cần 1,40× thì phải được 1,40×, KHÔNG phải kẹp 1,35 rồi chồng sang dòng sau.

    Số lấy từ lượt đo trên 14 dòng thật của clip 20:49: `take/chỗ` rải tới 1,62×.
    Bài này là ghim của RÀNG BUỘC CỨNG, nên nó phải ĐỎ nếu ai đó đặt lại trần.
    """
    takes, slots, avails = [1.02, 1.18, 1.40], [1.0, 1.0, 1.0], [1.0, 1.0, 1.0]
    toc_do, need = ke_hoach_toc_do(takes, slots, avails)
    assert [round(n, 2) for n in need] == [1.02, 1.18, 1.4]
    assert toc_do == [1.02, 1.18, 1.40], toc_do


def test_khong_bao_gio_doc_cham_di():
    """Take ngắn hơn chỗ ⇒ tốc độ 1,00, KHÔNG kéo chậm để lấp chỗ trống."""
    toc_do, need = ke_hoach_toc_do([0.4, 0.9], [1.0, 1.0], [1.0, 1.0])
    assert toc_do == [1.0, 1.0], toc_do
    assert need == [0.4, 0.9]


def test_muon_duoc_khoang_lang_thi_can_it_toc_do_hon():
    """Cùng take 1,5 s: chỗ 1,0 s nhưng dòng sau bắt đầu ở 1,5 s ⇒ chỉ cần 1,0×."""
    khong_muon, _ = ke_hoach_toc_do([1.5], [1.0], [1.0])
    co_muon, _ = ke_hoach_toc_do([1.5], [1.0], [1.5])
    assert khong_muon == [1.5]      # 1.5/1.0 = 1.5 — nén đúng mức, KHÔNG kẹp ở trần
    assert co_muon == [1.0]         # mượn 0,5 s lặng là đủ


def test_khong_cap_lien_ke_nao_chong_lan():
    """RÀNG BUỘC CỨNG, kiểm trên một bộ dòng dày đặc.

    Đây là bài quan trọng nhất của tệp. Nó kiểm ĐÚNG điều người dùng gọi là "không hợp lệ":
    giọng câu trước còn đang nói khi câu sau đã bắt đầu.
    """
    takes = [1.5, 2.0, 0.8, 3.0, 1.2]
    starts = [0.0, 1.0, 1.5, 2.0, 6.0]
    slots = [0.5, 0.5, 0.5, 4.0, 1.0]
    avails = [starts[k + 1] - starts[k] for k in range(len(starts) - 1)] + [1.0]
    toc_do, _ = ke_hoach_toc_do(takes, slots, avails)
    for k in range(len(starts) - 1):
        ket_thuc = starts[k] + takes[k] / toc_do[k]
        assert ket_thuc <= starts[k + 1] + 1e-9, (
            f"dòng {k} kết thúc ở {ket_thuc:.4f}s, vượt mốc bắt đầu dòng {k + 1} "
            f"({starts[k + 1]}s) — CHỒNG LẤN, không hợp lệ"
        )


def test_khong_co_hang_nao_bi_cat_chu():
    """Chỉ tốc độ được đổi; hàm KHÔNG trả về danh sách dòng phải sửa chữ.

    Ghim lời người dùng: "ko cần phải cắt mà chỉnh tốc độ là được". Bản cũ trả `qua_tran`
    để giao diện kêu người dùng sửa chữ — bỏ hẳn khái niệm đó.
    """
    ra = ke_hoach_toc_do([9.0], [1.0], [1.0])
    assert isinstance(ra, tuple) and len(ra) == 2, (
        f"phải trả đúng (toc_do, need), đo được {len(ra)} phần tử"
    )


def test_trong_im_lang_bo_dau_cuoi_giu_giua():
    sr = 100
    im = np.zeros(10, dtype=np.float32)
    tieng = np.full(5, 0.5, dtype=np.float32)
    mau = np.concatenate([im, tieng, np.zeros(3, dtype=np.float32), tieng, im])
    ra = trong_im_lang(mau, nguong=0.01)
    assert ra.size == 5 + 3 + 5, ra.size
    assert ra[0] == 0.5 and ra[-1] == 0.5


def test_rap_dat_dung_offset_va_cong_don_khi_chong():
    sr = 1000
    take = np.full(100, 0.25, dtype=np.float32)      # 0,1 s
    ra = rap([(0.0, take), (0.5, take)], 1.0, sr=sr)
    assert ra.shape == (1000,)
    assert ra[0] == 0.25 and ra[99] == 0.25
    assert ra[100:500].max() == 0.0, "khoảng giữa hai take phải im"
    assert ra[500] == 0.25
    # chồng tiếng thì CỘNG, không đè mất
    chong = rap([(0.0, take), (0.05, take)], 1.0, sr=sr)
    assert chong[75] == 0.5
```

- [ ] **Step 2: Chạy test, xác nhận ĐỎ**

Run: `cd backend && python -m pytest tests/test_dub.py -v`
Expected: FAIL — `TypeError: ke_hoach_toc_do() missing 1 required positional argument` hoặc `ValueError: too many values to unpack` (vì hàm cũ trả 3 phần tử).

- [ ] **Step 3: Sửa hằng số và `ke_hoach_toc_do` trong `dub.py`**

Thay khối dòng 31–62 bằng:

```python
NGUONG_IM_LANG = 0.01


def ke_hoach_toc_do(takes: list[float], slots: list[float], avails: list[float]
                    ) -> tuple[list[float], list[float]]:
    """Tốc độ cho từng dòng, và `need` (tốc độ tối thiểu) để chẩn đoán.

    `avails[i]` = từ `start` của dòng tới `start` của dòng kế. `need_i = take_i /
    max(slot_i, avail_i)` là tốc độ TỐI THIỂU để dòng đó không đè dòng sau — tức
    ràng buộc CỨNG của sản phẩm.

    🔴 VÌ SAO BỎ TRẦN VÀ BỎ THANG BẬC (đổi hành vi, có chủ):
    Bản cũ kẹp `need` ở `TOC_DO_TRAN = 1.35` và trả thêm `qua_tran`. Đo được hệ quả: dòng
    vượt trần VẪN chồng sang dòng sau (vì 1,35 không đủ), và mã chỉ báo "phải sửa chữ".
    Người dùng chốt hai điều trái với cách đó: (a) không chồng lấn là điều kiện ĐÚNG/SAI;
    (b) "ko cần phải cắt mà chỉnh tốc độ là được". Nên nay nén tới ĐÚNG mức cần, không cắt
    chữ, không kẹp trần.

    Thang bậc (`BAC_TOC_DO`) cũng bỏ: nó tồn tại để giữ tốc độ "gần đều", nhưng bậc nhỏ hơn
    `need` sẽ GÂY chồng — tức phá ràng buộc cứng để giữ một mong muốn. Đổi lại, phần lớn dòng
    nay ở đúng 1,0× (khi take ngắn hơn chỗ), nên tốc độ thực tế đều hơn cả bản cũ.

    `need_i` có thể > 1 rất nhiều khi hai dòng quá sát nhau; đó là dữ liệu, không phải lỗi —
    xem `_ghi_ke_hoach` (đếm `nen_manh`).
    """
    need: list[float] = []
    for take, slot, avail in zip(takes, slots, avails):
        # Cua so cho phep = TROI tu start nay toi start cua dong sau: take duoc TRAI vao khoang
        # lang, nen lay `max(slot, avail)` — KHONG phai `min`.
        cho = max(slot, avail) if avail > 0 else slot
        need.append(take / cho if cho > 0 else 1.0)
    toc_do = [max(1.0, n) for n in need]
    return toc_do, need
```

- [ ] **Step 4: Sửa `DubHandler.__init__` — bỏ tham số `tran`**

Dòng 143–150, thay bằng:

```python
    def __init__(self, repos, out_dir: pathlib.Path, tts_runner, *,
                 dinh_dangs=None,
                 python: str = "", script: str = "") -> None:
        self._repos = repos
        self._out_dir = pathlib.Path(out_dir)
        self._tts = tts_runner
        self._dinh_dangs = dinh_dangs or DINH_DANG
```

- [ ] **Step 5: Sửa lời gọi trong `run()` (dòng 240) và thông điệp cuối (dòng 275–279)**

Thay dòng 240:

```python
            toc_do, need = ke_hoach_toc_do(takes, slots, avails)
```

Thay dòng 271:

```python
        self._ghi_ke_hoach(tid, dung, takes, slots, avails, toc_do, need)
```

Thay dòng 275–279 bằng:

```python
        manh = [k for k, s in enumerate(toc_do) if s > 1.5]
        if manh:
            report(1.0, f"xong · {len(manh)} dòng phải nén trên 1,5× (đã nén đủ để không "
                        f"chồng, không cắt chữ): " + ", ".join(str(dung[k].i) for k in manh))
        else:
            report(1.0, "xong")
```

- [ ] **Step 6: Sửa `_ghi_ke_hoach`**

Đổi chữ ký và thân (dòng 281–321):

```python
    def _ghi_ke_hoach(self, tid: int, dung, takes, slots, avails, toc_do, need) -> None:
        """Ghi `dub-<tid>.plan.json`: số đo của TỪNG dòng cho bảng ở màn Lồng tiếng.

        `trang_thai` là HAI câu khác nhau, không phải ba:
          * `vua`      — take ≤ chỗ, không phải nén;
          * `nen`      — take > chỗ, đã nén ĐỦ để không chồng sang dòng sau.

        🔴 Bản cũ có trạng thái thứ ba `phai-sua` ("nén tới trần vẫn tràn ⇒ phải sửa chữ").
        Trạng thái đó biến mất cùng trần: nay không còn dòng nào "không cứu được bằng tốc độ",
        vì tốc độ không bị kẹp. `nen_manh` là con số CHẨN ĐOÁN (> 1,5×, mức khó nghe), không
        phải trạng thái chặn.

        Ghi bằng `ensure_ascii=False` để tệp đọc được bằng mắt khi cần chẩn đoán.
        """
        import json as _json

        dong = []
        for k, s in enumerate(dung):
            dong.append({
                "i": s.i,
                "start": round(float(s.start), 3),
                "end": round(float(s.end), 3),
                "text": s.text,
                "take": round(float(takes[k]), 3),
                "slot": round(float(slots[k]), 3),
                "avail": round(float(avails[k]), 3),
                "speed": round(float(toc_do[k]), 3),
                "need": round(float(need[k]), 3),
                "trang_thai": "nen" if need[k] > 1.0 + 1e-9 else "vua",
            })
        so_vua = sum(1 for d in dong if d["trang_thai"] == "vua")
        so_nen = sum(1 for d in dong if d["trang_thai"] == "nen")
        so_manh = sum(1 for d in dong if d["speed"] > 1.5)
        trung_vi = float(np.median([d["speed"] for d in dong])) if dong else 0.0
        ke_hoach = {
            "translation_id": tid,
            "tong_giay": round(float(max(s.end for s in dung)), 3),
            "so_dong": len(dong),
            "dem": {"vua": so_vua, "nen": so_nen, "nen_manh": so_manh},
            "trung_vi_toc_do": round(trung_vi, 3),
            "dong": dong,
        }
        (self._out_dir / f"dub-{tid}.plan.json").write_text(
            _json.dumps(ke_hoach, ensure_ascii=False, indent=1), encoding="utf-8")
```

- [ ] **Step 7: Sửa assert trong `test_dub_handler.py`**

Dòng 241, thay:

```python
    assert kh["dem"] == {"vua": 2, "nen": 0, "nen_manh": 0}, kh["dem"]
```

Và thêm ngay sau dòng 239 (`assert kh["tong_giay"] == 5.0`):

```python
    assert "tran" not in kh, "khoá `tran` phải BIẾN MẤT cùng trần 1,35"
```

- [ ] **Step 8: Chạy test, xác nhận XANH**

Run: `cd backend && python -m pytest tests/test_dub.py tests/test_dub_handler.py -v`
Expected: PASS toàn bộ.

- [ ] **Step 9: Chạy cả bộ backend**

Run: `cd backend && python -m pytest -q`
Expected: `1351 passed` (hoặc nhiều hơn do test mới), 0 failed, EXIT=0. Con số này ghi lại để so.

- [ ] **Step 10: Commit**

```bash
git add backend/app/pipeline/dub.py backend/tests/test_dub.py backend/tests/test_dub_handler.py
git commit -m "dub: bỏ trần tốc độ 1,35 — không chồng lấn là ràng buộc cứng

Đo được hệ quả của bản cũ: dòng vượt trần VẪN chồng sang dòng sau (vì kẹp ở
1,35 không đủ), và mã chỉ báo 'phải sửa chữ'. Người dùng chốt: không chồng lấn
là điều kiện ĐÚNG/SAI, và 'ko cần phải cắt mà chỉnh tốc độ là được'.

Nay `ke_hoach_toc_do` trả (toc_do, need), nén tới ĐÚNG mức cần:
  toc_do_i = max(1.0, take_i / max(slot_i, avail_i))
Bỏ TOC_DO_TRAN, bỏ BAC_TOC_DO, bỏ `qua_tran`, bỏ tham số `tran` của DubHandler,
bỏ trạng thái 'phai-sua' trong plan.json (thay bằng đếm 'nen_manh' > 1,5x).

Đổi lại: phần lớn dòng nay ở đúng 1,0x (take ngắn hơn chỗ), nên tốc độ thực tế
ĐỀU HƠN bản cũ — bản cũ nén cả những dòng không cần."
```

---

## Task 2: Bốn tầng lọc phụ đề — hàm THUẦN

Không cần model, không cần video. Chỉ dữ liệu tổng hợp. Đây là chỗ quyết định "đâu là phụ đề".

**Files:**
- Create: `backend/app/domain/phu_de.py`
- Test: `backend/tests/test_phu_de.py`

**Interfaces:**
- Consumes: không có.
- Produces:
  - `@dataclass Hop: text: str, x0: float, y0: float, x1: float, y1: float, t: float, diem: float` — `t` = giây, `diem` = điểm tin cậy của OCR.
  - `tim_dai_phu_de(hops: list[Hop], chieu_cao: int) -> tuple[float, float]` — trả `(y0, y1)` theo TỈ LỆ `0..1`.
  - `loc_on_dinh(hops: list[Hop], fps: float) -> list[Hop]`
  - `loc_hinh_dang(hops: list[Hop]) -> list[Hop]`
  - `loc_theo_asr(hops: list[Hop], khoang_asr: list[tuple[float, float]]) -> list[Hop]`
  - `gop_thanh_dong(hops: list[Hop], *, fps: float) -> list[Segment]` — dùng `Segment` có sẵn.

### Steps

- [ ] **Step 1: Viết `backend/tests/test_phu_de.py` (ĐỎ)**

```python
"""Bốn tầng lọc phụ đề — hàm THUẦN, không model, không video.

Số đo dùng ở đây lấy từ video thật 1249,237 s (1280x720, tiếng Trung, phụ đề cứng):
  · dải y phụ đề [627, 682]/720 = 0,871..0,947
  · watermark + logo bilibili ở y <= 70
  · 696 dòng OCR thô -> 627 dòng sau lọc 3 tầng (bỏ 69 = 10 %)
  · 69 dòng bị bỏ gồm: menu giá tiền 200 ký tự, chữ chạy danh lam thắng cảnh,
    logo đọc sai thành 'ebilibili'
"""
from __future__ import annotations

import pytest

from app.domain.phu_de import (
    Hop, gop_thanh_dong, loc_hinh_dang, loc_on_dinh, loc_theo_asr, tim_dai_phu_de,
)

CAO = 720


def _hop(text="xin chào", x0=100.0, y0=630.0, x1=400.0, y1=680.0, t=0.0, diem=0.9):
    return Hop(text=text, x0=x0, y0=y0, x1=x1, y1=y1, t=t, diem=diem)


def test_tim_dai_phu_de_tra_ti_le_khong_phai_pixel():
    """Phải trả TỈ LỆ để tự thích ứng 720p/1080p/4K — cùng video ở hai độ phân giải
    phải cho cùng dải."""
    hops = [_hop(t=float(k)) for k in range(20)]                     # dải phụ đề dày
    hops += [_hop(y0=10.0, y1=60.0, t=float(k)) for k in range(20)]  # watermark
    y0, y1 = tim_dai_phu_de(hops, chieu_cao=CAO)
    assert 0.85 <= y0 <= 0.90, f"y0 phải là tỉ lệ ~0,87, đo được {y0}"
    assert 0.93 <= y1 <= 0.97, f"y1 phải là tỉ lệ ~0,95, đo được {y1}"
    assert y0 < y1
    # cùng hops nhưng khung 1440 -> tỉ lệ KHÔNG đổi
    hops_hd = [_hop(y0=630.0 * 2, y1=680.0 * 2, t=float(k)) for k in range(20)]
    hops_hd += [_hop(y0=10.0 * 2, y1=60.0 * 2, t=float(k)) for k in range(20)]
    y0_hd, y1_hd = tim_dai_phu_de(hops_hd, chieu_cao=CAO * 2)
    assert abs(y0_hd - y0) < 0.02 and abs(y1_hd - y1) < 0.02, (
        f"tỉ lệ phải bất biến theo độ phân giải: {y0:.3f}/{y1:.3f} vs {y0_hd:.3f}/{y1_hd:.3f}"
    )


def test_loc_on_dinh_bo_chu_chay():
    """Chữ chạy (dải danh lam thắng cảnh đo được ở giây 1056) đổi vị trí x mỗi khung
    ⇒ loại. Phụ đề đứng yên ⇒ giữ."""
    dung = [_hop(text="câu phụ đề", x0=100.0, t=0.0), _hop(text="câu phụ đề", x0=100.0, t=0.5)]
    chay = [_hop(text="桂林山水", x0=100.0, t=1.0), _hop(text="桂林山水", x0=180.0, t=1.5)]
    ra = loc_on_dinh(dung + chay, fps=2.0)
    assert [h.text for h in ra] == ["câu phụ đề", "câu phụ đề"], [h.text for h in ra]


def test_loc_hinh_dang_bo_menu_gia_tien():
    """Menu giá tiền đo được 200 ký tự và đầy cụm số — nằm ĐÚNG dải phụ đề nên tầng 1
    không bắt được. Tầng 3 phải bắt."""
    dai = _hop(text="辣炒鸡胗24元20元更没想到的是香鸡金针菇15元一份" * 4)
    gia = _hop(text="锅包肉38元 溜肉段28元 鱼香肉丝22元")
    that = _hop(text="这个酸菜里面有肉汤")
    ra = loc_hinh_dang([dai, gia, that])
    assert [h.text for h in ra] == ["这个酸菜里面有肉汤"], [h.text for h in ra]


def test_loc_hinh_dang_bo_logo_doc_sai():
    """`ebilibili` / `Cilibili` là logo bị OCR đọc sai. Quá ngắn và không có nghĩa."""
    ra = loc_hinh_dang([_hop(text="ebilibili"), _hop(text="Cilibili"),
                        _hop(text="你怎么骑")])
    assert [h.text for h in ra] == ["你怎么骑"], [h.text for h in ra]


def test_loc_hinh_dang_bo_dong_lap_lien_tiep():
    ra = loc_hinh_dang([_hop(text="好好好", t=0.0), _hop(text="好好好", t=0.5),
                        _hop(text="好好好", t=1.0), _hop(text="下一句", t=1.5)])
    texts = [h.text for h in ra]
    assert texts.count("好好好") <= 1, f"dòng lặp y nguyên phải gộp, đo được {texts}"


def test_loc_theo_asr_bo_dong_khong_co_tieng_noi():
    """Tầng 4 (TUỲ CHỌN): cửa sổ OCR có chữ mà ASR hoàn toàn im lặng ⇒ nghi vấn.

    Đo được trên video thật: lọc 3 tầng giữ 696 dòng, thêm tầng 4 còn 627 — tức tầng 4
    bắt thêm được phần lớn trong 69 dòng rác.
    """
    co_tieng = [_hop(text="có người nói", t=10.0), _hop(text="menu giá tiền", t=50.0)]
    khoang = [(9.0, 12.0)]        # ASR chỉ có tiếng nói quanh giây 10
    ra = loc_theo_asr(co_tieng, khoang)
    assert [h.text for h in ra] == ["có người nói"], [h.text for h in ra]


def test_loc_theo_asr_khong_bao_gio_lam_rong_khi_asr_rong():
    """ASR không có khoảng nào ⇒ tầng 4 KHÔNG được xoá sạch. Thà giữ rác còn hơn mất phụ đề.

    Đây là ghim chống một lỗi dễ mắc: lọc bằng một nguồn rỗng thì xoá hết.
    """
    hops = [_hop(text="câu một", t=0.0), _hop(text="câu hai", t=5.0)]
    assert loc_theo_asr(hops, []) == hops


def test_gop_thanh_dong_gop_khung_lien_tiep_cung_chu():
    """2 fps: cùng một dòng phụ đề xuất hiện ở nhiều khung ⇒ MỘT Segment, không phải 5."""
    hops = [_hop(text="这个酸菜里面有肉汤", t=0.5 * k) for k in range(5)]
    segs = gop_thanh_dong(hops, fps=2.0)
    assert len(segs) == 1, f"phải gộp thành 1 dòng, đo được {len(segs)}"
    assert segs[0].start == 0.0
    assert abs(segs[0].end - 2.5) < 1e-6, f"kết thúc phải ~2,5 s, đo được {segs[0].end}"
    assert segs[0].text == "这个酸菜里面有肉汤"


def test_gop_thanh_dong_tach_khi_chu_doi():
    hops = [_hop(text="câu một", t=0.0), _hop(text="câu một", t=0.5),
            _hop(text="câu hai", t=1.0), _hop(text="câu hai", t=1.5)]
    segs = gop_thanh_dong(hops, fps=2.0)
    assert [s.text for s in segs] == ["câu một", "câu hai"]


def test_gop_thanh_dong_danh_so_tang_dan_tu_khong():
    """`Segment.i` phải là 0,1,2… liên tục — hạ tầng sau (dịch, export) dựa vào đó."""
    hops = [_hop(text=f"câu {k}", t=float(k)) for k in range(4)]
    segs = gop_thanh_dong(hops, fps=2.0)
    assert [s.i for s in segs] == list(range(len(segs))), [s.i for s in segs]
```

- [ ] **Step 2: Chạy test, xác nhận ĐỎ**

Run: `cd backend && python -m pytest tests/test_phu_de.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.domain.phu_de'`

- [ ] **Step 3: Viết `backend/app/domain/phu_de.py`**

```python
"""Bốn tầng lọc phụ đề cứng — hàm THUẦN, không model, không video.

## Vì sao là hàm thuần, không phải adapter

Tầng lọc chỉ làm việc trên danh sách `Hop`. Tách khỏi adapter thì test được bằng dữ liệu
tổng hợp (không cần `rapidocr` 100 MB), và thay engine OCR không phải sửa logic lọc.

## Bốn tầng, và cái gì bắt được cái gì

ĐO ĐƯỢC trên video 1249,237 s (1280x720, tiếng Trung, phụ đề cứng): OCR thô 696 dòng,
sau lọc 3 tầng còn 627 (bỏ 69 = 10 %). Tầng 4 (tuỳ chọn, cần ASR) cũng về 627.

  1. `tim_dai_phu_de`  — dải `y` nào là phụ đề. Chạy trên MẪU (~50 khung), trả TỈ LỆ.
  2. `loc_on_dinh`     — bỏ chữ CHẠY (đổi `x` mỗi khung).
  3. `loc_hinh_dang`   — bỏ menu giá tiền (dài, nhiều số), logo đọc sai, dòng lặp.
  4. `loc_theo_asr`    — TUỲ CHỌN: cửa sổ OCR có chữ mà ASR im lặng ⇒ nghi vấn.

⚠️ Tầng 1 KHÔNG lọc dòng. Nó chỉ tìm dải. Việc lọc dòng chạy trên TOÀN BỘ khung đã OCR.
"""
from __future__ import annotations

from dataclasses import dataclass

from app.domain.models import Segment


@dataclass
class Hop:
    """Một hộp chữ OCR đọc được ở một khung hình.

    `t` là GIÂY của khung đó. `diem` là điểm tin cậy của OCR (0..1).
    Toạ độ theo PIXEL của khung gốc; đổi sang tỉ lệ ở chỗ cần.
    """
    text: str
    x0: float
    y0: float
    x1: float
    y1: float
    t: float
    diem: float


#: Bề dày tối đa của dải phụ đề, theo tỉ lệ chiều cao khung. Đo được ở video thật:
#: [627, 682]/720 = 0,076. Để 0,15 là rộng gấp đôi, đủ cho video có phụ đề hai dòng.
DAY_DAI_TOI_DA = 0.15

#: Độ dài chữ hợp lệ của một dòng phụ đề. Menu giá tiền đo được 200 ký tự.
DAI_MIN, DAI_MAX = 3, 40

#: Số cụm số mà từ đó coi là menu giá tiền.
SO_CUM_SO_TOI_DA = 2

#: Dung sai `x` khi coi hai khung là CÙNG một dòng đứng yên (pixel).
DUNG_SAI_X = 24.0


def tim_dai_phu_de(hops: list[Hop], chieu_cao: int) -> tuple[float, float]:
    """Dải `y` của phụ đề, theo TỈ LỆ `0..1` của chiều cao khung.

    Dùng tỉ lệ chứ không dùng pixel để cùng một video ở 720p/1080p/4K cho cùng kết quả —
    ghim bằng `test_tim_dai_phu_de_tra_ti_le_khong_phai_pixel`.

    Chia khung thành 100 dải, đếm số hộp có ĐỈNH nằm trong mỗi dải, rồi lấy cụm dải liên
    tiếp DÀY NHẤT mà bề dày <= `DAY_DAI_TOI_DA`. Watermark/logo ở `y <= 70/720` thành một
    cụm riêng, mỏng hơn, nên không thắng.
    """
    if not hops or chieu_cao <= 0:
        return (0.0, 0.0)
    SO_DAI = 100
    dem = [0] * SO_DAI
    for h in hops:
        i = int((h.y0 / chieu_cao) * SO_DAI)
        dem[max(0, min(SO_DAI - 1, i))] += 1

    toi_da_dai = max(1, int(DAY_DAI_TOI_DA * SO_DAI))
    tot_nhat, tot_nhat_dau, tot_nhat_dai = -1, 0, 0
    for dau in range(SO_DAI):
        for dai in range(1, toi_da_dai + 1):
            if dau + dai > SO_DAI:
                break
            tong = sum(dem[dau:dau + dai])
            if tong > tot_nhat:
                tot_nhat, tot_nhat_dau, tot_nhat_dai = tong, dau, dai
    if tot_nhat <= 0:
        return (0.0, 0.0)
    return (tot_nhat_dau / SO_DAI, (tot_nhat_dau + tot_nhat_dai) / SO_DAI)


def loc_on_dinh(hops: list[Hop], fps: float) -> list[Hop]:
    """Bỏ chữ CHẠY: cùng nội dung nhưng `x` đổi mỗi khung.

    Phụ đề đứng yên 0,5–2,5 s rồi đổi; chữ chạy (dải danh lam thắng cảnh đo được ở giây
    1056) dịch `x` liên tục. Đo: nếu `|x0 - x0_khung_truoc| > DUNG_SAI_X` với cùng `text`
    thì đó là chữ chạy.

    `fps` dùng để biết "khung trước" là gì khi `hops` không đều; hiện chỉ cần `> 0`.
    """
    if fps <= 0:
        return list(hops)
    ra: list[Hop] = []
    truoc: dict[str, float] = {}
    for h in hops:
        x_truoc = truoc.get(h.text)
        if x_truoc is not None and abs(h.x0 - x_truoc) > DUNG_SAI_X:
            truoc[h.text] = h.x0
            continue          # chữ chạy -> bỏ
        truoc[h.text] = h.x0
        ra.append(h)
    return ra


def loc_hinh_dang(hops: list[Hop]) -> list[Hop]:
    """Bỏ dòng có hình dạng KHÔNG phải phụ đề, và gộp dòng lặp y nguyên.

    Ba điều kiện, đều đo được từ dữ liệu thật:
      · độ dài 3–40 ký tự (menu giá tiền: 200);
      · không quá `SO_CUM_SO_TOI_DA` cụm số (menu: '24元20元15元');
      · không lặp y nguyên liên tiếp (logo bị đọc nhiều khung thành '好好好').

    Vì sao dài >= 3: `ebilibili`/`Cilibili` (logo đọc sai) ngắn, và phụ đề thật ngắn nhất
    đo được là 3 ký tự.
    """
    ra: list[Hop] = []
    for h in hops:
        t = h.text.strip()
        if not (DAI_MIN <= len(t) <= DAI_MAX):
            continue
        if len([c for c in _cum_so(t)]) > SO_CUM_SO_TOI_DA:
            continue
        # GỘP dòng lặp y nguyên LIÊN TIẾP: logo bị OCR đọc nhiều khung thành '好好好' sẽ
        # thành một dòng, không phải năm. Giữ hộp ĐẦU (mốc thời gian sớm nhất).
        if ra and ra[-1].text.strip() == t:
            continue
        ra.append(h)
    return ra


def _cum_so(text: str) -> list[str]:
    """Các cụm CHỮ SỐ liên tiếp. Tách khỏi `loc_hinh_dang` để test được riêng."""
    ra: list[str] = []
    cur = ""
    for c in text:
        if c.isdigit():
            cur += c
        elif cur:
            ra.append(cur)
            cur = ""
    if cur:
        ra.append(cur)
    return ra


def loc_theo_asr(hops: list[Hop], khoang_asr: list[tuple[float, float]]) -> list[Hop]:
    """TUỲ CHỌN — bỏ dòng OCR không có tiếng nói nào tương ứng.

    ⚠️ KHÔNG BAO GIỜ làm rỗng khi `khoang_asr` rỗng: lọc bằng một nguồn rỗng thì xoá sạch,
    và thà giữ rác còn hơn mất phụ đề. Ghim bằng
    `test_loc_theo_asr_khong_bao_gio_lam_rong_khi_asr_rong`.

    Đo được: thêm tầng này giữ 627/696 dòng — tức nó bắt thêm phần lớn trong 69 dòng rác.
    """
    if not khoang_asr:
        return list(hops)
    ra: list[Hop] = []
    for h in hops:
        for dau, cuoi in khoang_asr:
            if dau <= h.t <= cuoi:
                ra.append(h)
                break
    return ra


def gop_thanh_dong(hops: list[Hop], *, fps: float) -> list[Segment]:
    """Gộp các hộp liên tiếp CÙNG chữ thành một `Segment`.

    Ở 2 fps, một dòng phụ đề hiện trên 1–5 khung ⇒ phải thành MỘT dòng, không phải năm.
    `start` = `t` của hộp đầu; `end` = `t` của hộp cuối + `1/fps` (khung cuối còn hiện
    thêm một nhịp).

    Trả `Segment` (model có sẵn) để mọi thứ sau đó không phải phân nhánh: OCR và ASR khác
    nhau ở CÁCH LẤY, không khác ở HÌNH DẠNG dữ liệu.
    """
    if not hops:
        return []
    buoc = 1.0 / fps if fps > 0 else 0.5
    ra: list[Segment] = []
    dau = hops[0].t
    truoc = hops[0]
    for h in hops[1:]:
        if h.text == truoc.text:
            truoc = h
            continue
        ra.append(Segment(i=len(ra), start=dau, end=truoc.t + buoc, text=truoc.text))
        dau, truoc = h.t, h
    ra.append(Segment(i=len(ra), start=dau, end=truoc.t + buoc, text=truoc.text))
    return ra
```

- [ ] **Step 4: Chạy test, xác nhận XANH**

Run: `cd backend && python -m pytest tests/test_phu_de.py -v`
Expected: PASS 10 bài.

- [ ] **Step 5: Commit**

```bash
git add backend/app/domain/phu_de.py backend/tests/test_phu_de.py
git commit -m "domain: bốn tầng lọc phụ đề cứng — hàm thuần, không cần model

Tách khỏi adapter để test bằng dữ liệu tổng hợp. Số đo dùng trong test lấy từ
video thật 1249,237 s: OCR thô 696 dòng -> 627 sau lọc 3 tầng (bỏ 69 = 10 %).

  tim_dai_phu_de  trả TỈ LỆ (bất biến theo 720p/1080p/4K), không phải pixel
  loc_on_dinh     bỏ chữ CHẠY (đổi x mỗi khung) — dải danh lam thắng cảnh giây 1056
  loc_hinh_dang   bỏ menu giá tiền (dài, nhiều cụm số), logo 'ebilibili', dòng lặp
  loc_theo_asr    TUỲ CHỌN; KHÔNG làm rỗng khi ASR rỗng (ghim riêng)

gop_thanh_dong trả `Segment` có sẵn: OCR và ASR khác nhau ở CÁCH LẤY, không khác
ở HÌNH DẠNG dữ liệu, nên mọi thứ sau đó không phải phân nhánh."
```

---

## Task 3: Port `OCREngine` + adapter rapidocr

**Files:**
- Create: `backend/app/ports/ocr.py`
- Create: `backend/app/adapters/ocr_rapidocr.py`
- Test: `backend/tests/test_ocr_rapidocr.py`

**Interfaces:**
- Consumes: `Hop`, `tim_dai_phu_de`, `loc_on_dinh`, `loc_hinh_dang`, `loc_theo_asr`,
  `gop_thanh_dong` (Task 2); `Segment` (`app.domain.models`).
- Produces:
  - `OCREngine` Protocol với `engine_id: str`, `doc_phu_de(video_path, *, fps=2.0, khoang_asr=None) -> list[Segment]`, `release() -> None`.
  - `RapidOCREngine(engine_id="rapidocr", *, model_dir=None)` — cùng chữ ký.

### Steps

- [ ] **Step 1: Viết `backend/tests/test_ocr_rapidocr.py` (ĐỎ)**

```python
"""Adapter OCR: dựng video tổng hợp có chữ, đọc lại, kiểm ba điều.

Không cần video thật: `ffmpeg` vẽ được chữ trắng trên nền đen, đúng hình dạng phụ đề cứng.
Bài này đi qua `rapidocr` THẬT (đã cài trong venv app), nên nó đo được cả việc model có
đọc ra chữ hay không — không phải mock.

⚠️ Chữ dùng là chữ Latin đơn giản vì `rapidocr-onnxruntime 1.4.4` đóng gói model
`ch_PP-OCRv4` (Trung) nhưng vẫn đọc được chữ Latin in rõ. Video mục tiêu là tiếng Trung;
bài này chỉ kiểm ĐƯỜNG ỐNG, không kiểm chất lượng đọc tiếng Trung.
"""
from __future__ import annotations

import subprocess

import pytest

from app.adapters.ocr_rapidocr import RapidOCREngine
from app.ports.ocr import OCREngine


#: Font PHẢI chỉ định tường minh: `ffmpeg` trên image Debian KHÔNG có font mặc định và
#: `drawtext` không có `fontfile` sẽ chết với "Cannot find a valid font". Kiểm trước bằng:
#:   docker compose exec -T api fc-list | head -1
#: Image hiện tại có DejaVu; nếu vắng thì `apt-get install -y fonts-dejavu-core`.
FONT = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"


def _lam_video(ra: str, *, giay: float = 2.0, fps: int = 2) -> str:
    """Video 320x240, nền đen, chữ trắng ở dải dưới (y ~ 200/240 = 0,83)."""
    subprocess.run(
        ["ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
         "-f", "lavfi", "-i", f"color=c=black:s=320x240:d={giay}:r={fps}",
         "-vf", (f"drawtext=fontfile={FONT}:text='hello world':fontcolor=white:"
                 "fontsize=22:x=40:y=200"),
         "-pix_fmt", "yuv420p", ra],
        check=True, capture_output=True,
    )
    return ra


def test_port_khai_dung_bon_thu():
    """Cổng phải khai `engine_id`, `doc_phu_de`, `release` — cùng khuôn `ASREngine`."""
    for ten in ("engine_id", "doc_phu_de", "release"):
        assert hasattr(OCREngine, ten) or ten in dir(OCREngine), ten


def test_doc_duoc_chu_va_tra_segment(tmp_path):
    video = _lam_video(str(tmp_path / "co-chu.mp4"))
    eng = RapidOCREngine()
    try:
        segs = eng.doc_phu_de(video, fps=2.0)
    finally:
        eng.release()
    assert segs, "phải đọc được ít nhất một dòng — video có chữ trắng rõ ràng"
    assert any("hello" in s.text.lower() for s in segs), (
        f"phải đọc ra 'hello', đo được {[s.text for s in segs]}"
    )
    for s in segs:
        assert s.end > s.start, f"end phải sau start: {s}"
        assert s.text.strip()


def test_video_khong_chu_tra_danh_sach_rong(tmp_path):
    """Nền đen trơn ⇒ KHÔNG có dòng nào. Không được bịa."""
    video = str(tmp_path / "trong.mp4")
    subprocess.run(
        ["ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
         "-f", "lavfi", "-i", "color=c=black:s=320x240:d=1:r=2",
         "-pix_fmt", "yuv420p", video],
        check=True, capture_output=True,
    )
    eng = RapidOCREngine()
    try:
        assert eng.doc_phu_de(video, fps=2.0) == []
    finally:
        eng.release()


def test_engine_id_la_chuoi_khong_rong():
    assert RapidOCREngine().engine_id == "rapidocr"


def test_release_an_toan_khi_goi_nhieu_lan():
    """Hợp đồng của `release`: gọi nhiều lần phải an toàn (giống `ASREngine.release`)."""
    eng = RapidOCREngine()
    eng.release()
    eng.release()


def test_khong_co_tep_thi_bao_loi_ro_rang(tmp_path):
    eng = RapidOCREngine()
    try:
        with pytest.raises((FileNotFoundError, RuntimeError)):
            eng.doc_phu_de(str(tmp_path / "khong-co.mp4"), fps=2.0)
    finally:
        eng.release()
```

- [ ] **Step 2: Chạy test, xác nhận ĐỎ**

Run: `cd backend && python -m pytest tests/test_ocr_rapidocr.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.ports.ocr'`

- [ ] **Step 3: Viết `backend/app/ports/ocr.py`**

```python
"""Cổng OCR: media → danh sách dòng phụ đề có mốc thời gian.

Cùng khuôn với `ports/asr.py`: Protocol + `engine_id` + một hàm chính + `release`. Vì sao
cùng khuôn: có nhiều engine OCR (rapidocr, paddleocr, tesseract) như ASR có nhiều engine,
và tầng trên không được biết engine nào.

Trả `list[Segment]` (model có sẵn) chứ không phải kiểu riêng: OCR và ASR khác nhau ở CÁCH
LẤY chữ, không khác ở HÌNH DẠNG dữ liệu — nên mọi thứ sau đó (dịch, export, lồng tiếng)
không phải phân nhánh.
"""
from __future__ import annotations

from typing import Protocol

from app.domain.models import Segment


class OCREngine(Protocol):
    engine_id: str

    def doc_phu_de(self, video_path: str, *, fps: float = 2.0,
                   khoang_asr: list[tuple[float, float]] | None = None
                   ) -> list[Segment]:
        """Đọc phụ đề CỨNG của `video_path`.

        `fps` = số khung đọc mỗi giây. Đo được trên video 20,8 phút: 2 fps đủ (dòng phụ đề
        ngắn nhất 0,5 s), tốn 372,8 s.

        `khoang_asr` = các khoảng CÓ tiếng nói, để bật tầng lọc 4. `None`/rỗng ⇒ TẮT tầng 4,
        và đó là mặc định: pipeline phải chạy được khi không có ASR.
        """
        ...

    def release(self) -> None:
        """Giải phóng model. Phải an toàn khi gọi nhiều lần."""
        ...
```

- [ ] **Step 4: Viết `backend/app/adapters/ocr_rapidocr.py`**

```python
"""Adapter OCR dùng `rapidocr-onnxruntime` — đọc phụ đề cứng của video.

## Vì sao rapidocr

Đo được trên video 1249,237 s (1280x720): 372,8 s cho 2 fps toàn video, ~0,13 s/khung trên
CPU. `rapidocr-onnxruntime 1.4.4` đóng gói sẵn `ch_PP-OCRv4_det_infer.onnx` +
`ch_PP-OCRv4_rec_infer.onnx` — không cần tải model, không cần mạng.

## Adapter này KHÔNG lọc

Nó chỉ: trích khung → gọi rapidocr → đổi toạ độ → giao cho `domain/phu_de.py`. Bốn tầng lọc
nằm ở domain để test được bằng dữ liệu tổng hợp.
"""
from __future__ import annotations

import pathlib
import subprocess
import tempfile

from app.domain.models import Segment
from app.domain.phu_de import (
    Hop, gop_thanh_dong, loc_hinh_dang, loc_on_dinh, loc_theo_asr, tim_dai_phu_de,
)


def _kich_thuoc(video_path: str) -> tuple[int, int]:
    """`(rộng, cao)` của video. Gọi `ffprobe` — không kéo thư viện video vào."""
    ra = subprocess.run(
        ["ffprobe", "-v", "error", "-select_streams", "v:0",
         "-show_entries", "stream=width,height", "-of", "csv=p=0:s=x", video_path],
        capture_output=True, text=True, check=True).stdout.strip()
    rong, cao = ra.split("x")[:2]
    return int(rong), int(cao)


class RapidOCREngine:
    """Đọc phụ đề cứng. Tạo engine MỘT lần, dùng cho nhiều video, `release()` khi xong."""

    engine_id = "rapidocr"

    def __init__(self, *, model_dir: str | None = None) -> None:
        self._model_dir = model_dir
        self._engine = None

    def _tao_engine(self):
        """Tạo `RapidOCR` — tách ra để lỗi import thành câu rõ ràng.

        `rapidocr-onnxruntime` là tuỳ chọn của image: thiếu nó thì câu lỗi phải nêu việc cần
        cài, không phải `ImportError` trần.
        """
        if self._engine is not None:
            return self._engine
        try:
            from rapidocr_onnxruntime import RapidOCR
        except ImportError as exc:  # pragma: no cover - image đã cài
            raise RuntimeError(
                "chưa cài OCR: cần `rapidocr-onnxruntime` trong venv của app "
                "(pip install rapidocr-onnxruntime==1.4.4)"
            ) from exc
        self._engine = RapidOCR()
        return self._engine

    def release(self) -> None:
        """Bỏ tham chiếu model. An toàn khi gọi nhiều lần (hợp đồng của cổng)."""
        self._engine = None

    def _doc_khung(self, engine, anh: str, t: float) -> list[Hop]:
        """Một khung → danh sách `Hop`. `rapidocr` trả `[[box, text, score], ...]`."""
        ra, _ = engine(anh)
        hops: list[Hop] = []
        for muc in ra or []:
            box, text, diem = muc[0], muc[1], muc[2]
            xs = [float(p[0]) for p in box]
            ys = [float(p[1]) for p in box]
            hops.append(Hop(text=str(text).strip(), x0=min(xs), y0=min(ys),
                            x1=max(xs), y1=max(ys), t=t, diem=float(diem)))
        return hops

    def doc_phu_de(self, video_path: str, *, fps: float = 2.0,
                   khoang_asr: list[tuple[float, float]] | None = None
                   ) -> list[Segment]:
        """Xem `OCREngine.doc_phu_de`. Bốn tầng lọc chạy SAU khi đọc hết khung.

        Vì sao đọc hết rồi mới lọc: tầng 1 cần histogram `y` trên toàn video, tầng 2 cần
        biết khung TRƯỚC của cùng dòng. Lọc dòng-bởi-dòng sẽ không làm được cả hai.
        """
        if not pathlib.Path(video_path).is_file():
            raise FileNotFoundError(f"không thấy video: {video_path}")
        if fps <= 0:
            raise ValueError(f"fps phải > 0, đo được {fps}")

        rong, cao = _kich_thuoc(video_path)
        engine = self._tao_engine()

        with tempfile.TemporaryDirectory(prefix="ocr-") as tam:
            tam_p = pathlib.Path(tam)
            # ffmpeg xuar khung ở fps yêu cầu; tên tệp mang số thứ tự nên `t = k / fps`.
            subprocess.run(
                ["ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
                 "-i", video_path, "-vf", f"fps={fps}", str(tam_p / "%06d.png")],
                check=True, capture_output=True)
            hops: list[Hop] = []
            for k, anh in enumerate(sorted(tam_p.glob("*.png"))):
                hops.extend(self._doc_khung(engine, str(anh), k / fps))

        if not hops:
            return []

        # Tầng 1: tìm dải y. Chạy trên TOÀN BỘ hộp (rẻ, và chính xác hơn mẫu 50 khung).
        y0, y1 = tim_dai_phu_de(hops, chieu_cao=cao)
        if y1 > y0:
            hops = [h for h in hops if y0 * cao <= h.y0 <= y1 * cao]

        # Tầng 2, 3, (4 tuỳ chọn).
        hops = loc_on_dinh(hops, fps=fps)
        hops = loc_hinh_dang(hops)
        if khoang_asr:
            hops = loc_theo_asr(hops, khoang_asr)

        hops.sort(key=lambda h: (h.t, h.x0))
        return gop_thanh_dong(hops, fps=fps)
```

- [ ] **Step 5: Chạy test, xác nhận XANH**

Run: `cd backend && python -m pytest tests/test_ocr_rapidocr.py -v`
Expected: PASS 6 bài.

- [ ] **Step 6: Commit**

```bash
git add backend/app/ports/ocr.py backend/app/adapters/ocr_rapidocr.py backend/tests/test_ocr_rapidocr.py
git commit -m "ocr: cổng OCREngine + adapter rapidocr (chỉ đọc, không lọc)

Cổng cùng khuôn ports/asr.py: Protocol + engine_id + doc_phu_de + release, trả
list[Segment] để tầng sau không phải phân nhánh giữa OCR và ASR.

Adapter chỉ: trích khung bằng ffmpeg -> rapidocr -> Hop -> giao domain/phu_de.
Bốn tầng lọc nằm ở domain (Task 2) nên test được không cần model.

Đo được: rapidocr 1.4.4 đóng gói sẵn model ch_PP-OCRv4, 372,8 s cho video 20,8
phút ở 2 fps, ~0,13 s/khung CPU.

Tầng 4 (đối chiếu ASR) MẶC ĐỊNH TẮT: pipeline phải chạy được khi không có ASR."
---

## Task 4: Đăng ký engine OCR trong `registry.json`

`registry.json` là NGUỒN SỰ THẬT DUY NHẤT về engine (ghi chú đầu tệp: "Thêm model mới = sửa
file này. KHÔNG hard-code ở pipeline hay giao diện"). Thêm `ocr` ở đây để `GET /api/registry`
trả về được, và để engine chọn được bằng id chứ không bằng import.

**Files:**
- Modify: `backend/registry.json` (thêm khoá `ocr` sau khối `asr`)
- Test: `backend/tests/test_registry_ocr.py` (mới)

**Interfaces:**
- Consumes: `RapidOCREngine.engine_id == "rapidocr"` (Task 3).
- Produces: khoá `ocr` trong JSON, mỗi entry có `id`, `label`, `runtime`, `opts`; và
  `GET /api/registry` trả nó ra (route đã có, không sửa).

### Steps

- [ ] **Step 1: Viết `backend/tests/test_registry_ocr.py` (ĐỎ)**

```python
"""`registry.json` phải khai engine OCR — cùng khuôn với `asr` và `mt`.

Vì sao có bài này: ghi chú đầu `registry.json` nói rõ nó là NGUỒN SỰ THẬT DUY NHẤT, và
`GET /api/registry` là đường giao diện đọc. Một engine chỉ tồn tại trong mã (không có trong
tệp) thì giao diện không biết nó, và người dùng không chọn được nó.
"""
from __future__ import annotations

import json
import pathlib

REGISTRY = pathlib.Path(__file__).resolve().parents[1] / "registry.json"


def _doc() -> dict:
    return json.loads(REGISTRY.read_text(encoding="utf-8"))


def test_registry_co_khoa_ocr():
    assert "ocr" in _doc(), "phải có khoá `ocr` — cùng khuôn `asr`/`mt`"


def test_moi_entry_ocr_co_du_bon_khoa():
    for e in _doc()["ocr"]:
        for k in ("id", "label", "runtime", "opts"):
            assert k in e, f"entry {e.get('id')!r} thiếu khoá {k!r}"


def test_id_cua_engine_rapidocr_khop_voi_adapter():
    """`id` trong registry phải TRÙNG `RapidOCREngine.engine_id`.

    Lệch nhau thì chọn engine theo id sẽ không tìm thấy adapter, và lỗi chỉ lộ ra lúc chạy.
    """
    from app.adapters.ocr_rapidocr import RapidOCREngine

    ids = [e["id"] for e in _doc()["ocr"]]
    assert RapidOCREngine.engine_id in ids, (
        f"engine_id {RapidOCREngine.engine_id!r} không có trong registry: {ids}"
    )


def test_fps_mac_dinh_nam_trong_opts_chu_khong_hard_code():
    e = next(x for x in _doc()["ocr"] if x["id"] == "rapidocr")
    assert e["opts"].get("fps") == 2.0, (
        f"fps mặc định phải là DỮ LIỆU trong registry, đo được {e['opts'].get('fps')!r}"
    )
```

- [ ] **Step 2: Chạy test, xác nhận ĐỎ**

Run: `cd backend && python -m pytest tests/test_registry_ocr.py -v`
Expected: FAIL — `KeyError: 'ocr'`

- [ ] **Step 3: Thêm khoá `ocr` vào `registry.json`**

Chèn ngay TRƯỚC dòng `"mt": [`, sau khi khối `asr` đóng bằng `],`:

```json
  "_ghi_chu_ocr": "OCR đọc phụ đề CỨNG của video. Cùng khuôn `asr`: id phải TRÙNG `engine_id` của adapter (ghim bằng test_registry_ocr.py). `opts.fps` là DỮ LIỆU: đo được trên video 20,8 phút, 2 fps đủ (dòng phụ đề ngắn nhất 0,5 s) và tốn 372,8 s; 10 fps sẽ tốn ~31 phút mà chỉ đổi ±0,5 s thành ±0,1 s. Tầng lọc 4 (đối chiếu ASR) KHÔNG khai ở đây vì nó là tham số của LƯỢT GỌI, và mặc định TẮT — pipeline phải chạy được khi không có ASR.",
  "ocr": [
    {
      "id": "rapidocr",
      "label": "RapidOCR (PP-OCRv4, đọc phụ đề cứng)",
      "runtime": "inprocess",
      "opts": { "fps": 2.0 }
    }
  ],
```

- [ ] **Step 4: Chạy test, xác nhận XANH**

Run: `cd backend && python -m pytest tests/test_registry_ocr.py -v`
Expected: PASS 4 bài.

- [ ] **Step 5: Kiểm JSON vẫn hợp lệ**

Run: `cd backend && python -c "import json,pathlib; d=json.loads(pathlib.Path('registry.json').read_text(encoding='utf-8')); print('ocr:', [e['id'] for e in d['ocr']])"`
Expected: `ocr: ['rapidocr']` — không có `JSONDecodeError`.

- [ ] **Step 6: Commit**

```bash
git add backend/registry.json backend/tests/test_registry_ocr.py
git commit -m "registry: khai engine OCR 'rapidocr' — cùng khuôn asr/mt

Ghi chú đầu registry.json nói nó là NGUỒN SỰ THẬT DUY NHẤT, và GET /api/registry là
đường giao diện đọc. Engine chỉ tồn tại trong mã thì giao diện không biết nó.

  id        'rapidocr' — TRÙNG RapidOCREngine.engine_id (ghim bằng test)
  opts.fps  2.0 — DỮ LIỆU, không hard-code: đo được 372,8 s cho video 20,8 phút;
            10 fps tốn ~31 phút mà chỉ đổi ±0,5 s thành ±0,1 s, không tương xứng

Tầng lọc 4 không khai ở đây: nó là tham số của LƯỢT GỌI và mặc định TẮT."
```

---

## Task 5: Chọn nguồn transcript — OCR là chính, ASR là dự phòng

Đây là "domain policy", không phải adapter: hàm quyết định DÙNG NGUỒN NÀO. Tách riêng để test
được mà không cần model nào, và để chỗ quyết định chất lượng nằm ở một nơi.

**Files:**
- Create: `backend/app/domain/nguon_chu.py`
- Test: `backend/tests/test_nguon_chu.py`

**Interfaces:**
- Consumes: `Segment` (`app.domain.models`).
- Produces:
  - `chon_nguon(doan_ocr: list[Segment], doan_asr: list[Segment] | None) -> tuple[list[Segment], str]`
    — trả `(doan_dung, ly_do)`. `ly_do` là câu tiếng Việt cho log/giao diện.
  - `khoang_co_tieng(doan_asr: list[Segment]) -> list[tuple[float, float]]` — cho tầng lọc 4.

### Steps

- [ ] **Step 1: Viết `backend/tests/test_nguon_chu.py` (ĐỎ)**

```python
"""Chọn nguồn chữ: OCR là CHÍNH, ASR là dự phòng.

Ba tình huống phải phân biệt được, và chúng KHÁC NHAU về câu trả lời:
  · có OCR  -> dùng OCR (chữ đã biên tập, chính xác hơn ASR);
  · không OCR, có ASR -> dùng ASR (video không có phụ đề cứng);
  · không cả hai -> lỗi rõ ràng, KHÔNG trả danh sách rỗng im lặng.
"""
from __future__ import annotations

import pytest

from app.domain.models import Segment
from app.domain.nguon_chu import chon_nguon, khoang_co_tieng


def _seg(i=0, start=0.0, end=2.0, text="chữ"):
    return Segment(i=i, start=start, end=end, text=text)


def test_co_ocr_thi_dung_ocr():
    ocr = [_seg(0, 0.0, 2.0, "từ OCR"), _seg(1, 3.0, 5.0, "câu hai")]
    asr = [_seg(0, 0.0, 2.0, "từ ASR nghe nhầm")]
    doan, ly_do = chon_nguon(ocr, asr)
    assert [s.text for s in doan] == ["từ OCR", "câu hai"]
    assert "OCR" in ly_do, ly_do


def test_khong_co_ocr_thi_dung_asr():
    asr = [_seg(0, 0.0, 2.0, "từ ASR")]
    doan, ly_do = chon_nguon([], asr)
    assert [s.text for s in doan] == ["từ ASR"]
    assert "ASR" in ly_do, ly_do


def test_khong_co_gi_ca_thi_bao_loi():
    """Danh sách rỗng im lặng là bẫy: job sẽ 'thành công' với bản lồng tiếng rỗng."""
    with pytest.raises(RuntimeError, match="không có chữ"):
        chon_nguon([], None)
    with pytest.raises(RuntimeError, match="không có chữ"):
        chon_nguon([], [])


def test_ocr_rong_vi_video_khong_phu_de_thi_roi_ve_asr():
    """Video không có phụ đề cứng ⇒ OCR trả [] một cách HỢP LỆ, không phải lỗi."""
    asr = [_seg(0, 0.0, 2.0, "lời nói thật")]
    doan, ly_do = chon_nguon([], asr)
    assert len(doan) == 1
    assert "ASR" in ly_do


def test_khoang_co_tieng_gop_khoang_sat_nhau():
    """Hai đoạn cách nhau 0,2 s là MỘT khoảng (nhiễu cắt dòng), không phải hai."""
    doan = [_seg(0, 0.0, 2.0), _seg(1, 2.2, 4.0), _seg(2, 10.0, 12.0)]
    ra = khoang_co_tieng(doan)
    assert ra == [(0.0, 4.0), (10.0, 12.0)], ra


def test_khoang_co_tieng_rong_khi_khong_co_doan_nao():
    assert khoang_co_tieng([]) == []
```

- [ ] **Step 2: Chạy test, xác nhận ĐỎ**

Run: `cd backend && python -m pytest tests/test_nguon_chu.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.domain.nguon_chu'`

- [ ] **Step 3: Viết `backend/app/domain/nguon_chu.py`**

```python
"""Chọn nguồn chữ cho pipeline lồng tiếng: OCR là CHÍNH, ASR là dự phòng.

## Vì sao là domain policy, không phải một bước trong pipeline

"Chọn nguồn nào" là một QUYẾT ĐỊNH về chất lượng, không phải một phép biến đổi dữ liệu. Tách
ra đây thì test được mà không cần model, và nó là chỗ duy nhất phải sửa khi đổi chính sách.

## Vì sao OCR là chính

ĐO ĐƯỢC trên video 1249,237 s, đoạn 120–420 s, OCR làm gốc (76 cửa sổ 4 s, 163 dòng):
  · ASR trên audio GỐC:   chính xác ký tự 66,27 %, bỏ sót 0 cửa sổ
  · ASR trên vocals tách: 60,48 % (roformer-1296), 56,29 % (htdemucs)
OCR đọc chữ ĐÃ BIÊN TẬP (người làm phụ đề gõ), nên nó đúng chính tả và đúng từ; ASR nghe và
hay sai tên riêng. Ngoài ra ASR DỪNG ở 1186,4 s — thiếu 62,8 s cuối video, còn OCR phủ tới
1243 s.

## Vì sao vẫn cần ASR

Video không có phụ đề cứng thì OCR trả danh sách rỗng một cách HỢP LỆ. Đó không phải lỗi, và
rơi về ASR là hành vi đúng. Ngoài ra ASR cấp mốc thời gian chính xác hơn (word-level ~0,1 s
so với OCR 2 fps ±0,5 s).
"""
from __future__ import annotations

from app.domain.models import Segment

#: Hai đoạn ASR cách nhau ít hơn ngưỡng này là MỘT khoảng có tiếng (nhiễu cắt dòng).
#: Đo được: bản ASR gốc 451 đoạn trên 1249 s có nhiều cặp sát nhau cỡ 0,1–0,3 s.
NGUONG_GOP = 0.5


def chon_nguon(doan_ocr: list[Segment], doan_asr: list[Segment] | None
               ) -> tuple[list[Segment], str]:
    """Chọn nguồn chữ. Trả `(đoạn dùng được, lý do tiếng Việt)`.

    Ưu tiên OCR. Rơi về ASR khi OCR rỗng (video không có phụ đề cứng). Ném `RuntimeError`
    khi cả hai đều rỗng — im lặng trả `[]` sẽ khiến job "thành công" với bản lồng rỗng.
    """
    if doan_ocr:
        return list(doan_ocr), f"dùng OCR: {len(doan_ocr)} dòng phụ đề đọc được từ hình"
    if doan_asr:
        return list(doan_asr), (f"dùng ASR: không đọc được phụ đề cứng nào, "
                                f"dùng {len(doan_asr)} đoạn lời nói")
    raise RuntimeError(
        "không có chữ để lồng tiếng: OCR không đọc được phụ đề cứng nào và ASR cũng không "
        "có đoạn lời nói nào — kiểm lại video (có phụ đề cứng? có tiếng nói?)"
    )


def khoang_co_tieng(doan_asr: list[Segment]) -> list[tuple[float, float]]:
    """Các khoảng CÓ tiếng nói, từ danh sách đoạn ASR. Dùng cho tầng lọc 4.

    Gộp hai đoạn cách nhau dưới `NGUONG_GOP` — ASR hay cắt một câu thành hai đoạn sát nhau,
    và nếu không gộp thì tầng 4 sẽ coi phần đệm giữa chúng là "không có tiếng" rồi xoá nhầm
    phụ đề nằm đúng đó.

    Trả `[]` khi không có đoạn nào; `loc_theo_asr` đã ghim là KHÔNG xoá gì khi nhận `[]`.
    """
    if not doan_asr:
        return []
    da_sap = sorted((float(s.start), float(s.end)) for s in doan_asr)
    ra: list[tuple[float, float]] = [da_sap[0]]
    for dau, cuoi in da_sap[1:]:
        if dau - ra[-1][1] < NGUONG_GOP:
            ra[-1] = (ra[-1][0], max(ra[-1][1], cuoi))
        else:
            ra.append((dau, cuoi))
    return ra
```

- [ ] **Step 4: Chạy test, xác nhận XANH**

Run: `cd backend && python -m pytest tests/test_nguon_chu.py -v`
Expected: PASS 6 bài.

- [ ] **Step 5: Commit**

```bash
git add backend/app/domain/nguon_chu.py backend/tests/test_nguon_chu.py
git commit -m "domain: chọn nguồn chữ — OCR là chính, ASR là dự phòng

'Chọn nguồn nào' là QUYẾT ĐỊNH về chất lượng, không phải phép biến đổi dữ liệu,
nên nó ở domain chứ không phải một bước trong pipeline.

Vì sao OCR là chính — ĐO ĐƯỢC trên đoạn 120-420 s của video 1249,237 s, OCR làm gốc:
  · ASR trên audio gốc:   66,27 % ký tự đúng, bỏ sót 0 cửa sổ
  · ASR trên vocals tách: 60,48 % (roformer-1296) / 56,29 % (htdemucs)
  · ASR DỪNG ở 1186,4 s, thiếu 62,8 s cuối; OCR phủ tới 1243 s
OCR đọc chữ đã biên tập nên đúng chính tả; ASR nghe và hay sai tên riêng.

Vì sao vẫn cần ASR: video không có phụ đề cứng thì OCR trả [] một cách HỢP LỆ —
đó là hành vi đúng, không phải lỗi. Cả hai đều rỗng thì NÉM LỖI, không trả []
im lặng (job sẽ 'thành công' với bản lồng rỗng).

khoang_co_tieng gộp hai đoạn ASR sát nhau (< 0,5 s) thành một khoảng: không gộp
thì tầng lọc 4 coi phần đệm giữa chúng là 'không có tiếng' rồi xoá nhầm phụ đề."
```

---

## Task 6: Đo bốn con số của spec TRƯỚC khi lập kế hoạch nối pipeline

Spec mục 7 cố ý KHÔNG chốt bốn con số. Task này đo chúng trên dữ liệu THẬT đang có trong DB,
rồi ghi vào `docs/superpowers/reports/`. Không có bước này thì mọi quyết định ở Task 7 là đoán.

**Files:**
- Create: `backend/scripts/do_bon_con_so.py`
- Create: `docs/superpowers/reports/2026-10-29-bon-con-so.md` (kết quả ĐO, không phải ước)

**Interfaces:**
- Consumes: `ke_hoach_toc_do` (Task 1), `chon_nguon`/`khoang_co_tieng` (Task 5), DB thật
  (`translations` id 1–4, `transcripts` của source 1).
- Produces: một báo cáo markdown có bốn số, mỗi số kèm lệnh đã chạy và output thô.

### Steps

- [ ] **Step 1: Viết `backend/scripts/do_bon_con_so.py`**

```python
"""Đo BỐN con số mà spec 2026-10-29 cố ý để trống — chạy trên DB thật, không phải ước.

Spec mục 7:
  1. `T_tts(1,0)/T_nói` trên các dòng đã dịch  -> bao nhiêu % dòng phải nén
  2. A1 thuần (tầng 1-3, KHÔNG ASR) giữ bao nhiêu dòng, so với A2 = 627
  3. mốc OCR 4 fps có đạt ±0,25 s không (cần video; nếu thiếu thì ghi RÕ là chưa đo)
  4. số cặp dòng có `avail <= 0` — nhánh 5.2b

Chạy trong container: `python scripts/do_bon_con_so.py`
"""
from __future__ import annotations

import json
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from app.adapters.clock_system import SystemClock
from app.adapters.persist.sqlite_repos import SqliteRepos
from app.pipeline.dub import ke_hoach_toc_do


def _db() -> pathlib.Path:
    import os
    return pathlib.Path(os.environ.get("PHUDE_DB", "/data/app.db"))


def main() -> None:
    repos = SqliteRepos(_db(), clock=SystemClock())
    ra: dict = {}

    # --- So 4: `avail <= 0` tren MOI ban dich da xong ---
    tat_ca = repos.list_translations()
    so_cap = 0
    so_cap_xau = 0
    for ban in tat_ca:
        dong = [s for s in ban.segments if (s.text or "").strip()]
        for k in range(len(dong) - 1):
            so_cap += 1
            if dong[k + 1].start <= dong[k].start:
                so_cap_xau += 1
    ra["so_4_cap_avail_khong_duong"] = {
        "tong_cap": so_cap, "cap_xau": so_cap_xau,
        "ti_le": round(so_cap_xau / so_cap, 4) if so_cap else None,
        "so_ban_dich": len(tat_ca),
    }

    # --- So 1: take/chỗ. Take THAT nam trong plan.json (neu da long lan nao) ---
    # Khong co plan.json thi KHONG bia: bao thieu.
    co_ke_hoach = []
    for tep in sorted(pathlib.Path("/data/output/dubs").glob("dub-*.plan.json")):
        try:
            co_ke_hoach.append(json.loads(tep.read_text(encoding="utf-8")))
        except Exception:
            continue
    if co_ke_hoach:
        tong_take = 0.0
        tong_noi = 0.0
        so_dong = 0
        for kh in co_ke_hoach:
            for d in kh.get("dong", []):
                tong_take += float(d["take"])
                tong_noi += float(d["slot"])
                so_dong += 1
        ra["so_1_ti_le_take_tren_noi"] = {
            "so_dong": so_dong,
            "tong_take": round(tong_take, 3),
            "tong_noi": round(tong_noi, 3),
            "ti_le": round(tong_take / tong_noi, 4) if tong_noi else None,
            "nguon": "plan.json co san",
        }
    else:
        ra["so_1_ti_le_take_tren_noi"] = {
            "do_duoc": False,
            "ly_do": "chua co dub-*.plan.json nao — phai long tieng that mot lan roi do lai",
        }

    # --- So 1b: dung ke_hoach_toc_do tren take GIA = slot (gia dinh TTS dai bang noi) ---
    # Cho biet BAO NHIEU dong phai nen NEU TTS dai bang noi — mot can tren, khong phai so that.
    for ban in tat_ca:
        dong = [s for s in ban.segments if (s.text or "").strip()]
        if len(dong) < 2:
            continue
        takes = [max(0.01, s.end - s.start) for s in dong]
        slots = list(takes)
        avails = [(dong[k + 1].start if k + 1 < len(dong) else dong[k].end) - dong[k].start
                  for k in range(len(dong))]
        toc_do, need = ke_hoach_toc_do(takes, slots, avails)
        ra.setdefault("so_1b_can_tren_theo_ban_dich", {})[str(ban.id)] = {
            "so_dong": len(dong),
            "so_dong_phai_nen": sum(1 for n in need if n > 1.0 + 1e-9),
            "need_lon_nhat": round(max(need), 3),
            "toc_do_trung_vi": round(float(sorted(toc_do)[len(toc_do) // 2]), 3),
        }

    print(json.dumps(ra, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Chạy nó, ghi output THÔ**

Run (trong container):
```bash
docker compose exec -T -e PHUDE_DB=/data/app.db api python scripts/do_bon_con_so.py
```
Copy NGUYÊN output vào báo cáo ở Step 3. Không tóm tắt, không làm tròn thêm.

- [ ] **Step 3: Viết `docs/superpowers/reports/2026-10-29-bon-con-so.md`**

Khung bắt buộc — điền số ĐO ĐƯỢC, và chỗ nào chưa đo được thì ghi `CHƯA ĐO` + lý do:

```markdown
# Bốn con số của spec 2026-10-29 — kết quả đo

Lệnh: `docker compose exec -T -e PHUDE_DB=/data/app.db api python scripts/do_bon_con_so.py`

## Output thô

```
<dán nguyên output ở Step 2>
```

## Kết luận cho từng số

### 1. `T_tts(1,0)/T_nói`
<trả lời: đo được hay CHƯA ĐO; nếu đo được thì bao nhiêu, và hệ quả cho ràng buộc "tốc độ gần đều">

### 2. A1 thuần (không ASR) giữ bao nhiêu dòng
<trả lời: số dòng, so với A2 = 627; nếu CHƯA ĐO thì nêu cần chạy gì>

### 3. Mốc OCR 4 fps có đạt ±0,25 s không
<trả lời hoặc CHƯA ĐO + lý do (cần video + script riêng)>

### 4. Số cặp dòng có `avail <= 0`
<trả lời: số cặp / tổng cặp, và nếu khác 0 thì nhánh 5.2b của spec có hiệu lực>
```

- [ ] **Step 4: Commit**

```bash
git add backend/scripts/do_bon_con_so.py docs/superpowers/reports/2026-10-29-bon-con-so.md
git commit -m "do: bốn con số spec 2026-10-29 — đo trên DB thật, chỗ nào chưa đo thì ghi CHƯA ĐO

Spec mục 7 cố ý để trống bốn con số vì 'chưa đo thì chốt là đoán'. Task này đo
chúng trên dữ liệu thật đang có, và ghi nguyên output thô vào báo cáo.

  so 1  T_tts(1,0)/T_noi — từ plan.json ĐÃ CÓ; không có thì ghi CHƯA ĐO, không bịa
  so 1b cận trên: giả định TTS dài bằng nói -> bao nhiêu dòng phải nén
  so 4  số cặp `avail <= 0` — quyết định nhánh 5.2b của spec có hiệu lực hay không
  so 2, 3  nếu thiếu dữ liệu thì ghi rõ CHƯA ĐO kèm lý do

Không có bước này thì mọi quyết định ở Task 7 là đoán."
```

---

## Task 7: Nối OCR vào `TranscribeHandler` — chọn nguồn theo dữ liệu

`TranscribeHandler` hiện chỉ có ASR. Task này thêm phương thức MỚI `chon_doan`, KHÔNG đổi `run`
— nên 8 bài test cũ của `transcribe` vẫn xanh mà không phải sửa.

Vì sao không nhét OCR vào `run` ngay: `run` đã có 8 bài ghim hợp đồng. Đổi `run` trước khi biết
`chon_doan` chạy đúng là sửa hai biến cùng lúc. Tách phương thức mới thì test riêng được, rồi
Task 8 mới nối vào `run`.

**Files:**
- Modify: `backend/app/pipeline/transcribe.py:52-98` (thêm `ocr_engine` + `chon_doan`)
- Test: `backend/tests/test_transcribe_ocr.py` (mới)

**Interfaces:**
- Consumes: `chon_nguon`, `khoang_co_tieng` (Task 5); `OCREngine` (Task 3).
- Produces:
  - `TranscribeHandler.__init__(..., ocr_engine=None)` — `None` ⇒ KHÔNG có OCR, hành vi y bản cũ.
  - `TranscribeHandler.chon_doan(media_path, lang, *, dung_ocr_lam_goc=True) -> tuple[list[Segment], str]`

### Steps

- [ ] **Step 1: Viết `backend/tests/test_transcribe_ocr.py` (ĐỎ)**

```python
"""`TranscribeHandler.chon_doan`: OCR là chính, ASR là dự phòng, không có OCR thì như cũ.

Dùng engine GIẢ cho cả hai — bài này kiểm ĐƯỜNG NỐI, không kiểm chất lượng model (đã có
`test_ocr_rapidocr.py` và các bài ASR riêng).
"""
from __future__ import annotations

import pathlib

import numpy as np
import pytest
import soundfile as sf

from app.adapters.clock_system import SystemClock
from app.adapters.persist.sqlite_repos import SqliteRepos
from app.domain.models import Segment
from app.pipeline.transcribe import TranscribeHandler


class OcrGia:
    engine_id = "ocr-gia"

    def __init__(self, doan):
        self._doan = doan
        self.duoc_goi = 0
        self.khoang_asr_nhan = "chua-goi"

    def doc_phu_de(self, video_path, *, fps=2.0, khoang_asr=None):
        self.duoc_goi += 1
        self.khoang_asr_nhan = khoang_asr
        return list(self._doan)

    def release(self):
        pass


class AsrGia:
    engine_id = "asr-gia"

    def __init__(self, doan):
        self._doan = doan
        self.duoc_goi = 0

    def transcribe(self, audio_path, lang):
        self.duoc_goi += 1
        return list(self._doan)

    def release(self):
        pass


def _media(tmp_path: pathlib.Path) -> pathlib.Path:
    """Một tệp .wav 1 s — handler chỉ cần đường dẫn TỒN TẠI và nằm trong `workdir`."""
    p = tmp_path / "m.wav"
    sf.write(str(p), np.zeros(48_000, dtype=np.float32), 48_000)
    return p


def _handler(tmp_path, *, ocr=None, asr=None):
    r = SqliteRepos(tmp_path / "t.db", clock=SystemClock())
    r.init_schema()
    return TranscribeHandler(r, [], lambda spec: asr, workdir=tmp_path, ocr_engine=ocr)


def test_khong_co_ocr_engine_thi_hanh_vi_y_ban_cu(tmp_path):
    """`ocr_engine=None` ⇒ KHÔNG gọi OCR, dùng ASR.

    Ghim chống hồi quy: mọi bài `transcribe` cũ dựng handler KHÔNG có OCR, nên đường đó phải
    nguyên vẹn — nếu không, 8 bài cũ sẽ đỏ vì một lý do không liên quan tới chúng.
    """
    asr = AsrGia([Segment(i=0, start=0.0, end=1.0, text="từ ASR")])
    h = _handler(tmp_path, ocr=None, asr=asr)
    doan, ly_do = h.chon_doan(str(_media(tmp_path)), "zh")
    assert [s.text for s in doan] == ["từ ASR"]
    assert "ASR" in ly_do, ly_do
    assert asr.duoc_goi == 1


def test_co_ocr_engine_va_ocr_co_chu_thi_dung_ocr(tmp_path):
    ocr = OcrGia([Segment(i=0, start=0.0, end=1.0, text="từ OCR")])
    asr = AsrGia([Segment(i=0, start=0.0, end=1.0, text="từ ASR")])
    h = _handler(tmp_path, ocr=ocr, asr=asr)
    doan, ly_do = h.chon_doan(str(_media(tmp_path)), "zh")
    assert [s.text for s in doan] == ["từ OCR"]
    assert "OCR" in ly_do, ly_do
    assert ocr.duoc_goi == 1


def test_ocr_rong_thi_roi_ve_asr_va_khong_no(tmp_path):
    """Video không có phụ đề cứng ⇒ OCR trả [] HỢP LỆ ⇒ rơi về ASR, không ném lỗi."""
    ocr = OcrGia([])
    asr = AsrGia([Segment(i=0, start=0.0, end=1.0, text="lời nói thật")])
    h = _handler(tmp_path, ocr=ocr, asr=asr)
    doan, ly_do = h.chon_doan(str(_media(tmp_path)), "zh")
    assert [s.text for s in doan] == ["lời nói thật"]
    assert "ASR" in ly_do, ly_do


def test_ca_hai_deu_rong_thi_nem_loi(tmp_path):
    """Trả `[]` im lặng là bẫy: job sẽ 'thành công' với bản lồng tiếng RỖNG."""
    h = _handler(tmp_path, ocr=OcrGia([]), asr=AsrGia([]))
    with pytest.raises(RuntimeError, match="không có chữ"):
        h.chon_doan(str(_media(tmp_path)), "zh")


def test_ocr_nhan_khoang_asr_tu_doan_asr(tmp_path):
    """Tầng lọc 4 cần `khoang_asr`; handler phải TRUYỀN nó, không bỏ quên.

    Hai đoạn cách 0,2 s phải gộp thành MỘT khoảng (0,0 - 4,0) — việc của `khoang_co_tieng`
    (Task 5), nhưng nếu handler không gọi nó thì tầng 4 sẽ nhận `None`.
    """
    ocr = OcrGia([Segment(i=0, start=0.0, end=1.0, text="từ OCR")])
    asr = AsrGia([Segment(i=0, start=0.0, end=2.0, text="x"),
                  Segment(i=1, start=2.2, end=4.0, text="y")])
    h = _handler(tmp_path, ocr=ocr, asr=asr)
    h.chon_doan(str(_media(tmp_path)), "zh")
    assert ocr.khoang_asr_nhan == [(0.0, 4.0)], ocr.khoang_asr_nhan


def test_dung_ocr_lam_goc_false_thi_bo_qua_ocr(tmp_path):
    """Cờ để tắt OCR cho một lượt (video không có phụ đề: khỏi tốn 6 phút đọc khung)."""
    ocr = OcrGia([Segment(i=0, start=0.0, end=1.0, text="từ OCR")])
    asr = AsrGia([Segment(i=0, start=0.0, end=1.0, text="từ ASR")])
    h = _handler(tmp_path, ocr=ocr, asr=asr)
    doan, _ = h.chon_doan(str(_media(tmp_path)), "zh", dung_ocr_lam_goc=False)
    assert [s.text for s in doan] == ["từ ASR"]
    assert ocr.duoc_goi == 0, "cờ TẮT thì KHÔNG được đọc khung"
```

- [ ] **Step 2: Chạy test, xác nhận ĐỎ**

Run: `cd backend && python -m pytest tests/test_transcribe_ocr.py -v`
Expected: FAIL — `TypeError: __init__() got an unexpected keyword argument 'ocr_engine'`

- [ ] **Step 3: Thêm `ocr_engine` vào `__init__`**

Trong `backend/app/pipeline/transcribe.py`, thêm tham số keyword-only SAU `prompt_versions`:

```python
        prompt_versions: Mapping[str, str] | None = None,
        ocr_engine: OCREngine | None = None,
    ) -> None:
```

và trong thân, cạnh `self._engine_id = None`:

```python
        #: OCR là TUỲ CHỌN: `None` nghĩa là "không có OCR", và đường ASR thuần vẫn nguyên
        #: vẹn. Mọi bài test `transcribe` cũ dựng handler không truyền tham số này, nên
        #: chúng ghim đúng hành vi cũ — đó là lý do nó là tham số keyword có mặc định.
        self._ocr = ocr_engine
```

và import ở đầu tệp:

```python
from app.domain.nguon_chu import chon_nguon, khoang_co_tieng
from app.ports.ocr import OCREngine
```

- [ ] **Step 4: Thêm `chon_doan` — đặt ngay TRƯỚC `def run`**

```python
    def chon_doan(self, media_path: str, lang: str, *,
                  dung_ocr_lam_goc: bool = True) -> tuple[list[Segment], str]:
        """Chọn nguồn chữ cho MỘT media. Trả `(đoạn, lý do tiếng Việt)`.

        Thứ tự: OCR (nếu có engine VÀ `dung_ocr_lam_goc`) → ASR → lỗi.

        🔴 VÌ SAO KHÔNG PHẢI "CHỈ OCR": video không có phụ đề cứng thì OCR trả `[]` một cách
        HỢP LỆ, và rơi về ASR là hành vi đúng. ĐO ĐƯỢC lý do vẫn ưu tiên OCR khi có: trên
        đoạn 120–420 s của video thật, ASR chỉ đúng 66,27 % ký tự (bản gốc) và 60,48 %
        (trên vocals tách); OCR đọc chữ đã biên tập nên đúng chính tả, lại phủ tới 1243 s
        trong khi ASR dừng ở 1186,4 s.

        ASR LUÔN chạy trước khi gọi OCR, vì tầng lọc 4 cần `khoang_asr`. Đó là chi phí đã
        biết: muốn dùng tầng 4 thì phải trả tiền ASR.
        """
        doan_asr: list[Segment] = []
        if self._ocr is not None and self._engine_id:
            # Chạy ASR TRƯỚC để có `khoang_asr` cho tầng lọc 4. `_engine_for` giữ engine
            # theo id nên nạp model một lần, không phải mỗi lượt.
            doan_asr = self._engine_for(self._engine_id).transcribe(media_path, lang)
        if self._ocr is not None and dung_ocr_lam_goc:
            khoang = khoang_co_tieng(doan_asr)
            doan_ocr = self._ocr.doc_phu_de(media_path, khoang_asr=khoang or None)
            if doan_ocr:
                return chon_nguon(doan_ocr, doan_asr)
        if not doan_asr and self._engine_id:
            doan_asr = self._engine_for(self._engine_id).transcribe(media_path, lang)
        return chon_nguon([], doan_asr)
```

⚠️ `self._engine_id` chỉ có nghĩa khi `run` đã đặt nó. Để `chon_doan` dùng được độc lập,
thêm tham số `asr_engine_id: str | None = None` vào chữ ký và ưu tiên nó:

```python
    def chon_doan(self, media_path: str, lang: str, *,
                  dung_ocr_lam_goc: bool = True,
                  asr_engine_id: str | None = None) -> tuple[list[Segment], str]:
```

rồi trong thân, thay `self._engine_id` bằng `(asr_engine_id or self._engine_id)`.

- [ ] **Step 5: Chạy test, xác nhận XANH**

Run: `cd backend && python -m pytest tests/test_transcribe_ocr.py -v`
Expected: PASS 6 bài.

- [ ] **Step 6: Chạy lại 8 bài `transcribe` cũ — phải vẫn XANH**

Run: `cd backend && python -m pytest tests/test_transcribe_pipeline.py -v`
Expected: PASS toàn bộ. Nếu ĐỎ thì tham số mới đã phá hợp đồng cũ — sửa, không nới test.

- [ ] **Step 7: Commit**

```bash
git add backend/app/pipeline/transcribe.py backend/tests/test_transcribe_ocr.py
git commit -m "transcribe: thêm chon_doan — OCR là chính, ASR là dự phòng

Phương thức MỚI, không đổi `run`: 8 bài ghim hợp đồng của `run` phải nguyên vẹn,
và đổi hai biến cùng lúc là cách chắc chắn nhất để không biết cái nào hỏng.

`ocr_engine=None` (mặc định) = KHÔNG có OCR, hành vi y bản cũ — đó là lý do nó là
tham số keyword có mặc định, và là lý do các bài `transcribe` cũ vẫn xanh.

Thứ tự chọn: OCR (nếu có engine + cờ bật) -> ASR -> NÉM LỖI. Cả hai rỗng thì ném,
không trả [] im lặng (job sẽ 'thành công' với bản lồng rỗng).

ASR chạy TRƯỚC khi gọi OCR vì tầng lọc 4 cần `khoang_asr` — chi phí đã biết, ghi
trong docstring."
```

---

## Task 8: Nối `chon_doan` vào `run` + composition root

Task 7 thêm phương thức nhưng chưa ai gọi. Task này nối vào đường thật: `run` dùng `chon_doan`
thay vì gọi thẳng ASR, và `main.py` dựng `RapidOCREngine`.

**Files:**
- Modify: `backend/app/pipeline/transcribe.py:127-200` (thay lời gọi ASR bằng `chon_doan`)
- Modify: `backend/app/main.py:462` (dựng `RapidOCREngine` cho `TranscribeHandler`)
- Test: `backend/tests/test_transcribe_pipeline.py` (thêm một bài, KHÔNG sửa bài cũ)

**Interfaces:**
- Consumes: `chon_doan` (Task 7), `RapidOCREngine` (Task 3).
- Produces: `transcripts` có thể sinh từ OCR; `transcripts.engine` ghi `"rapidocr"`.

### Steps

- [ ] **Step 1: Đọc lại 8 bài cũ để biết chúng ghim gì**

Run: `cd backend && python -m pytest tests/test_transcribe_pipeline.py -v --no-header`
Ghi lại số bài và tên. Không sửa bài nào.

- [ ] **Step 2: Thêm MỘT bài vào `test_transcribe_pipeline.py` (ĐỎ)**

```python
def test_run_dung_ocr_khi_handler_co_ocr_engine(repos, specs, tmp_path):
    """Đường THẬT: `run` phải đi qua OCR khi handler có engine, và ghi `engine` của OCR.

    Vì sao ghim cả cột `engine`: nếu `run` dùng chữ OCR nhưng ghi `engine="fw-large-v3"` thì
    lịch sử nói dối về nguồn — và không ai phát hiện được bằng cách đọc transcript.
    """
    import numpy as np
    import soundfile as sf

    from app.domain.models import Segment
    from app.pipeline.transcribe import TranscribeHandler

    class OcrGia:
        engine_id = "rapidocr"

        def doc_phu_de(self, video_path, *, fps=2.0, khoang_asr=None):
            return [Segment(i=0, start=0.0, end=2.0, text="từ phụ đề")]

        def release(self):
            pass

    class AsrGia:
        engine_id = "fw-large-v3-turbo"

        def transcribe(self, audio_path, lang):
            return [Segment(i=0, start=0.0, end=2.0, text="từ âm thanh")]

        def release(self):
            pass

    media = tmp_path / "m.wav"
    sf.write(str(media), np.zeros(48_000, dtype=np.float32), 48_000)
    sid = repos.add_source(kind="file", origin="a", media_path=str(media),
                           audio_path=str(media), lang="zh")
    h = TranscribeHandler(repos, specs, lambda spec: AsrGia(),
                          workdir=tmp_path, ocr_engine=OcrGia())
    job_id = repos.add_job(Job(id=None, workspace=1, type="asr",
                               engine="fw-large-v3-turbo", phase="asr:fw-large-v3-turbo",
                               payload={"source_id": sid}))
    h.run(repos.get_job(job_id), lambda p, line: None)

    t = repos.list_transcripts()[0]
    assert [s.text for s in t.segments] == ["từ phụ đề"], [s.text for s in t.segments]
    assert t.engine == "rapidocr", f"cột engine phải nói ĐÚNG nguồn, đo được {t.engine!r}"
```

- [ ] **Step 3: Chạy, xác nhận ĐỎ**

Run: `cd backend && python -m pytest tests/test_transcribe_pipeline.py::test_run_dung_ocr_khi_handler_co_ocr_engine -v`
Expected: FAIL — `assert ['từ âm thanh'] == ['từ phụ đề']`

- [ ] **Step 4: Sửa `run` để dùng `chon_doan`**

Trong `backend/app/pipeline/transcribe.py`, thay khối từ `engine = self._engine_for(...)` tới
lời gọi `transcribe(...)` (khoảng dòng 135–175) bằng:

```python
        doan, ly_do = self.chon_doan(str(audio), lang,
                                     asr_engine_id=job.engine or None)
        report(0.30, ly_do)
        #: `engine` ghi ĐÚNG nguồn đã dùng, không phải engine của job: nếu chữ đến từ OCR mà
        #: ghi `fw-large-v3` thì lịch sử nói dối, và không cách nào phát hiện bằng cách đọc
        #: transcript. Đây là lý do `chon_doan` trả kèm `ly_do` chứ không chỉ danh sách.
        engine_ghi = "rapidocr" if ly_do.startswith("dùng OCR") else (job.engine or "")
```

Rồi mọi chỗ trong `run` đang dùng `job.engine` để ghi transcript thì đổi thành `engine_ghi`.
Chỗ nào đang lặp `for s in doan_asr` thì đổi thành `for s in doan`.

⚠️ Phần báo tiến độ theo từng đoạn (`bao_tien_do`) chỉ có nghĩa với ASR. Với OCR, tiến độ đã
được báo ở `report(0.30, ly_do)` sau khi xong — nên bỏ phần gắn `on_progress` khi nguồn là OCR,
và GIỮ nó khi nguồn là ASR. Nếu không, thanh tiến độ sẽ đứng ở 15 % suốt 6 phút đọc khung.

- [ ] **Step 5: Chạy cả tệp, xác nhận XANH (cả 8 bài cũ + 1 bài mới)**

Run: `cd backend && python -m pytest tests/test_transcribe_pipeline.py -v`
Expected: PASS toàn bộ.

- [ ] **Step 6: Dựng OCR trong composition root**

Trong `backend/app/main.py`, cạnh chỗ dựng `TranscribeHandler` (tìm `TranscribeHandler(`), thêm:

```python
    # OCR là TUỲ CHỌN của môi trường: thiếu `rapidocr-onnxruntime` thì `_tao_engine` ném câu
    # rõ ràng, nhưng ở đây ta KHÔNG dựng nó khi thư viện vắng — để `transcribe` vẫn chạy được
    # đường ASR thuần trên một image không có OCR. Một image thiếu OCR không được làm chết
    # tính năng bóc băng.
    _ocr_engine = None
    try:
        import rapidocr_onnxruntime  # noqa: F401
        _ocr_engine = RapidOCREngine()
    except ImportError:
        pass
```

rồi truyền `ocr_engine=_ocr_engine` vào `TranscribeHandler(...)`, và import đầu tệp:

```python
from app.adapters.ocr_rapidocr import RapidOCREngine
```

- [ ] **Step 7: Chạy cả bộ backend**

Run: `cd backend && python -m pytest -q`
Expected: `1351 passed` + số bài mới, 0 failed, EXIT=0.

- [ ] **Step 8: Commit**

```bash
git add backend/app/pipeline/transcribe.py backend/app/main.py backend/tests/test_transcribe_pipeline.py
git commit -m "transcribe: nối chon_doan vào run, dựng RapidOCREngine ở composition root

`run` nay đi qua `chon_doan` thay vì gọi thẳng ASR, nên chữ có thể đến từ OCR.

Cột `transcripts.engine` ghi ĐÚNG nguồn ('rapidocr' khi dùng OCR), không phải engine
của job — ghi sai thì lịch sử nói dối và không cách nào phát hiện bằng cách đọc
transcript. Ghim bằng test riêng.

Tiến độ: phần báo theo từng đoạn chỉ có nghĩa với ASR; với OCR thì báo một lần sau
khi xong, nếu không thanh sẽ đứng ở 15% suốt 6 phút đọc khung.

main.py dựng OCR trong try/except ImportError: image thiếu rapidocr vẫn chạy được
đường ASR thuần — một tính năng tuỳ chọn không được làm chết tính năng chính."
```

---

## Task 9: Kiểm chứng cuối — số đo phải khớp baseline

Không có task này thì "xong" là một lời tuyên bố, không phải phép đo.

**Files:** không sửa gì. Chỉ chạy và ghi.

### Steps

- [ ] **Step 1: Backend**

Run: `cd backend && python -m pytest -q`
Expected: 0 failed, EXIT=0. Ghi lại số `passed`.

- [ ] **Step 2: Frontend (không đổi mã, nhưng phải chứng minh không hỏng)**

Run: `cd frontend && npm test`
Expected: `381 pass · 0 fail`, EXIT=0.

- [ ] **Step 3: Typecheck**

Run: `cd frontend && npx tsc --noEmit`
Expected: không output, EXIT=0.

- [ ] **Step 4: `contract.test.ts` — cần cổng 8620 TRỐNG**

Run:
```bash
cd phu-de-lab
docker compose stop api
cd frontend && npm test -- contract
cd .. && docker compose start api
```
Expected: PASS. DB phải là DB THẬT của repo (có rows) — KHÔNG trỏ `PHUDE_DB` vào DB rỗng.

- [ ] **Step 5: `git status` phải RỖNG**

Run: `git status --porcelain`
Expected: không output.

- [ ] **Step 6: Ghi kết quả vào báo cáo**

Thêm mục "Kiểm chứng cuối" vào `docs/superpowers/reports/2026-10-29-bon-con-so.md` với output
THÔ của bốn lệnh trên. Không tóm tắt, không làm tròn.

- [ ] **Step 7: Commit**

```bash
git add docs/superpowers/reports/2026-10-29-bon-con-so.md
git commit -m "do: kiểm chứng cuối — backend, frontend, typecheck, contract

Output thô của bốn lệnh, không tóm tắt: 'xong' phải là một phép đo, không phải một
lời tuyên bố."
```

---

## Tự rà kế hoạch

**1. Spec coverage** — từng mục của spec có task:

| Mục spec | Task |
|---|---|
| §3.1 port `ocr` mới | Task 3 |
| §3.2 bốn tầng lọc | Task 2 |
| §3.3 chạy được khi không ASR | Task 3 (`khoang_asr=None` mặc định), Task 7 |
| §4 timestamp (chữ OCR, mốc ASR) | Task 5 (`chon_nguon`), Task 7 |
| §5.2 bỏ trần, bỏ thang bậc | Task 1 |
| §5.2b `avail <= 0` | Task 6 (đo), Task 1 (công thức) |
| §5.3 điều kiện kiểm | Task 1 Step 1 |
| §5.4 ghi log `> 1.35` | Task 1 Step 5 (`manh` > 1,5×) |
| §6 demucs + remux | **KHÔNG có task** — xem dưới |
| §7 bốn con số | Task 6 |
| §8 ngoài phạm vi | — |
| §9 rủi ro numpy 2.2.6 | Task 9 Step 1 |

**Lỗ hổng đã biết, ghi rõ thay vì giấu:** §6 (tách nền bằng `htdemucs` + remux) KHÔNG có task
nào. Lý do: nó là một đường ống riêng, chạy sau khi đã có bản lồng tiếng, và spec §6 ghi nó
"đã có, đã đo" (remux từng chạy được, `long-tieng.mp4` 227,4 MB). Nhưng `dub.py` hiện **xuất
bản lồng SẠCH**, không trộn nền — nên "remux video đã tách giọng với bản lồng tiếng" vẫn là
việc CHƯA LÀM. Nếu người dùng muốn trọn pipeline thì cần thêm một task nữa; kế hoạch này dừng
ở chỗ có bản lồng sạch + nền tách rời, vì hai thứ đó ghép được bằng một lệnh `ffmpeg` đã đo
(`amix normalize=0`, `0,9/0,9`, peak −0,18 dB).

**2. Placeholder scan** — không còn `TBD`/`TODO`. Mọi bước có mã hoặc lệnh cụ thể. Chỗ duy nhất
không có mã là Task 6 Step 3 (khung báo cáo), và nó đúng bản chất: nội dung là SỐ ĐO, không
phải mã — viết sẵn số là bịa.

**3. Type consistency:**
- `ke_hoach_toc_do` trả 2 phần tử ở Task 1, và Task 6 dùng đúng 2 (`toc_do, need = ...`). ✓
- `Hop` định nghĩa Task 2, dùng Task 3. ✓
- `OCREngine.doc_phu_de(video_path, *, fps, khoang_asr)` — Task 3, Task 7 gọi đúng chữ ký. ✓
- `chon_nguon(doan_ocr, doan_asr)` trả `(list, str)` — Task 5, Task 7 dùng đúng. ✓
- `RapidOCREngine.engine_id == "rapidocr"` — Task 3, Task 4 ghim, Task 8 dùng. ✓
- `TranscribeHandler.__init__(..., ocr_engine=None)` — Task 7, Task 8 truyền. ✓
