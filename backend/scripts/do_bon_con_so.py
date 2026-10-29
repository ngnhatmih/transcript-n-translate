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

    # --- So 1: take/chỗ. Take THẬT nằm trong plan.json (nếu đã lồng lần nào) ---
    # Không có plan.json thì KHÔNG bịa: báo thiếu.
    #
    # 🔴 ĐỌC ĐƯỢC CẢ HAI HÌNH DẠNG. Đo được trên đĩa lúc viết task: ba tệp duy nhất có
    # trong /data/output/dubs là dub-2, dub-4, dub-10 — CẢ BA do dub.py BẢN CŨ ghi, nên
    # chúng có `tran` + `dem.phai_sua` + `trang_thai == "phai-sua"`. dub.py mới (Task 1) bỏ
    # `tran`, đổi `phai_sua` thành `nen_manh`, và `trang_thai` chỉ còn vua/nen. Script chỉ
    # đọc hình dạng mới sẽ KeyError hoặc lặng lẽ đếm thiếu. Nên đếm theo CẢ HAI tên, và ghi
    # rõ tệp nào là hình dạng cũ để báo cáo không trộn số của hai chính sách khác nhau.
    #
    # `take`/`slot` thì giống nhau ở cả hai hình dạng — đó là số đo thô của TTS, không phải
    # kết luận của chính sách, nên dùng chung được.
    co_ke_hoach = []
    for tep in sorted(pathlib.Path("/data/output/dubs").glob("dub-*.plan.json")):
        try:
            kh = json.loads(tep.read_text(encoding="utf-8"))
        except Exception:
            continue
        kh["_tep"] = tep.name
        kh["_hinh_dang"] = "cu" if "tran" in kh else "moi"
        co_ke_hoach.append(kh)
    if co_ke_hoach:
        tong_take = 0.0
        tong_noi = 0.0
        so_dong = 0
        dem_trang_thai: dict[str, int] = {}
        so_dong_bi_kep_tran = 0
        for kh in co_ke_hoach:
            for d in kh.get("dong", []):
                tong_take += float(d["take"])
                tong_noi += float(d["slot"])
                so_dong += 1
                tt = d.get("trang_thai")
                if tt:
                    dem_trang_thai[tt] = dem_trang_thai.get(tt, 0) + 1
                # Trần cũ kẹp speed ở 1,35: đếm xem nó THẬT SỰ kẹp bao nhiêu dòng.
                if float(d.get("speed") or 1.0) >= 1.35 - 1e-9:
                    so_dong_bi_kep_tran += 1
        ra["so_1_ti_le_take_tren_noi"] = {
            "so_dong": so_dong,
            "tong_take": round(tong_take, 3),
            "tong_noi": round(tong_noi, 3),
            "ti_le": round(tong_take / tong_noi, 4) if tong_noi else None,
            "nguon": "plan.json co san",
            "cac_tep": [{"tep": kh["_tep"], "hinh_dang": kh["_hinh_dang"],
                         "so_dong": len(kh.get("dong", []))} for kh in co_ke_hoach],
            "dem_trang_thai": dem_trang_thai,
            "so_dong_bi_kep_tran_cu": so_dong_bi_kep_tran,
        }
    else:
        ra["so_1_ti_le_take_tren_noi"] = {
            "do_duoc": False,
            "ly_do": "chua co dub-*.plan.json nao — phai long tieng that mot lan roi do lai",
        }

    # --- So 1b: phan bo `need` tren take THAT, khong phai take GIA ---
    #
    # 🔴 BẢN ĐẦU CỦA KHỐI NÀY VÔ NGHĨA — ghi lại để không ai viết lại như thế.
    # Nó đặt `takes = slots` rồi gọi `need_i = take_i / max(slot_i, avail_i)`. Với
    # `take_i == slot_i` thì `need_i <= 1` LUÔN ĐÚNG (chứng minh: nếu `avail >= slot` thì
    # `slot/avail <= 1`; nếu `avail < slot` thì `slot/slot = 1`). Nên `so_dong_phai_nen`
    # luôn bằng 0 bất kể dữ liệu — đo được 0 ở cả bốn bản dịch, và đó là hệ quả TOÁN HỌC
    # của cách dựng phép đo, không phải phát hiện về dữ liệu.
    #
    # Phép đo CÓ NGHĨA: lấy `take` THẬT từ plan.json (số đo của TTS), ghép với `slot` và
    # `avail` từ bản dịch, rồi hỏi `need` vượt 1 ở bao nhiêu dòng. Đây mới là câu hỏi
    # "bao nhiêu dòng phải nén" mà spec mục 7 muốn.
    #
    # Ghép theo `i` của Segment: plan.json ghi `dong` theo đúng thứ tự dòng của bản dịch,
    # nên ghép theo CHỈ SỐ, không theo `start` (start có thể lệch giữa hai lần chạy).
    take_that: dict[int, list[float]] = {}
    for kh in co_ke_hoach:
        for d in kh.get("dong", []):
            i = d.get("i")
            if i is None:
                continue
            take_that.setdefault(int(i), []).append(float(d["take"]))
    if take_that:
        phan_bo: dict[str, dict] = {}
        for ban in tat_ca:
            dong = [s for s in ban.segments if (s.text or "").strip()]
            if len(dong) < 2:
                continue
            # `take` that neu co, khong thi bo dong do (KHONG bia).
            cap = [(k, take_that[k][0]) for k in range(len(dong)) if k in take_that]
            if len(cap) < 2:
                continue
            chi_so = [k for k, _ in cap]
            takes = [t for _, t in cap]
            slots = [max(0.01, dong[k].end - dong[k].start) for k in chi_so]
            avails = [(dong[k + 1].start if k + 1 < len(dong) else dong[k].end)
                      - dong[k].start for k in chi_so]
            toc_do, need = ke_hoach_toc_do(takes, slots, avails)
            phan_bo[str(ban.id)] = {
                "so_dong_ghep_duoc": len(cap),
                "so_dong_cua_ban": len(dong),
                "so_dong_phai_nen": sum(1 for n in need if n > 1.0 + 1e-9),
                "need_lon_nhat": round(max(need), 3),
                "need_trung_vi": round(float(sorted(need)[len(need) // 2]), 3),
                "toc_do_lon_nhat": round(max(toc_do), 3),
                "toc_do_trung_vi": round(float(sorted(toc_do)[len(toc_do) // 2]), 3),
            }
        ra["so_1b_need_tren_take_that"] = phan_bo
    else:
        ra["so_1b_need_tren_take_that"] = {
            "do_duoc": False,
            "ly_do": "plan.json khong co truong `i` — khong ghep duoc theo chi so dong",
        }

    print(json.dumps(ra, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
