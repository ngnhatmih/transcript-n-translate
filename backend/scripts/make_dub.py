"""Lồng tiếng một bản dịch: TTS từng dòng → ép về timeline → xuất wav/flac/mp3/aac/m4a.

Chạy bằng venv CỦA APP; TTS chạy bằng venv riêng (xem `scripts/tts_batch.py` để biết vì sao).

    .\\.venv\\Scripts\\python.exe -B scripts\\make_dub.py --so-dong 12 --voice "Minh Quân"

Đọc dòng phụ đề và bản dịch từ **API đang chạy** (`--api`), không phải từ DB: TTS cần đúng bản
dịch người dùng đang thấy, và API là nguồn sự thật của nó — mở DB là nguồn thứ hai.
"""
import argparse
import json
import pathlib
import subprocess
import sys
import tempfile
import urllib.request

BACKEND = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))

import numpy as np  # noqa: E402
import soundfile as sf  # noqa: E402

from app.pipeline.dub import (DINH_DANG, doi_toc_do, ke_hoach_toc_do, rap,  # noqa: E402
                              trong_im_lang, xuat_dinh_dang)

SR = 48_000


def get(url: str):
    with urllib.request.urlopen(url, timeout=30) as r:
        return json.loads(r.read().decode("utf-8"))


def main(argv=None) -> int:
    p = argparse.ArgumentParser(prog="make_dub.py")
    p.add_argument("--api", default="http://127.0.0.1:3100")
    p.add_argument("--translation-id", type=int, default=3)
    p.add_argument("--so-dong", type=int, default=12, help="0 = cả bản dịch")
    p.add_argument("--voice", default=None, help="tên giọng dựng sẵn của VieNeu")
    p.add_argument("--tts-python", default=str(BACKEND / ".venv-tts" / "Scripts" / "python.exe"))
    p.add_argument("--out-dir", type=pathlib.Path, default=BACKEND / "data" / "dubs")
    p.add_argument("--nguong-manh", type=float, default=1.5, help="nguong coi la nen MANH (chi de bao cao, khong chan)")
    a = p.parse_args(argv)

    ban = get(f"{a.api}/api/translations/{a.translation_id}")
    dong = ban["segments"][: a.so_dong or None]
    if not dong:
        print("KHÔNG có dòng nào — dừng")
        return 2
    print(f"bản dịch #{a.translation_id}: {len(dong)} dòng · engine {ban['engine']}")

    lv = pathlib.Path(tempfile.mkdtemp(prefix="dub-"))
    viec, kq = lv / "viec.json", lv / "kq.json"
    viec.write_text(json.dumps({
        "items": [{"i": s["i"], "text": s["text"]} for s in dong],
        "voice": a.voice, "out_dir": str(lv / "wav"), "result": str(kq),
    }, ensure_ascii=False), encoding="utf-8")
    print(f"TTS: {a.tts_python}")
    r = subprocess.run([a.tts_python, "-B", str(BACKEND / "scripts" / "tts_batch.py"), str(viec)],
                       capture_output=True, text=True, encoding="utf-8", errors="replace")
    if not kq.exists():
        print("TTS không chạy được:\n" + (r.stderr or r.stdout)[-1500:])
        return 3
    data = json.loads(kq.read_text(encoding="utf-8"))
    lay = {x["i"]: x for x in data["ok"]}
    print(f"TTS xong: {len(data['ok'])} take · {len(data['loi'])} lỗi")
    for x in data["loi"][:3]:
        print(f"   lỗi dòng {x['i']}: {x['error']}")

    dung = [s for s in dong if s["i"] in lay]
    if not dung:
        print("không take nào — dừng")
        return 3
    takes = [lay[s["i"]]["seconds"] for s in dung]
    slots = [s["end"] - s["start"] for s in dung]
    avails = [(dung[k + 1]["start"] if k + 1 < len(dung) else dung[k]["end"]) - dung[k]["start"]
              for k in range(len(dung))]
    toc_do, need = ke_hoach_toc_do(takes, slots, avails)

    print(f"\n{'i':>4} {'chỗ':>6} {'take':>6} {'cần':>6} {'tốc độ':>7}  trạng thái")
    for k, s in enumerate(dung):
        nhan = "vừa chỗ" if need[k] <= 1.0 else ("nén mạnh" if toc_do[k] > a.nguong_manh else "nén")
        print(f"{s['i']:>4} {slots[k]:>6.2f} {takes[k]:>6.2f} {need[k]:>6.2f} {toc_do[k]:>7.2f}  {nhan}")

    dat: list[tuple[float, np.ndarray]] = []
    for k, s in enumerate(dung):
        goc = pathlib.Path(lay[s["i"]]["path"])
        mau, sr = sf.read(str(goc), dtype="float32", always_2d=False)
        if mau.ndim > 1:
            mau = mau.mean(axis=1)
        mau = trong_im_lang(mau)
        if abs(toc_do[k] - 1.0) > 1e-6:
            sped = lv / f"{s['i']:05d}-x.wav"
            doi_toc_do(goc, sped, toc_do[k])
            mau, sr = sf.read(str(sped), dtype="float32", always_2d=False)
            if mau.ndim > 1:
                mau = mau.mean(axis=1)
        dat.append((s["start"], mau.astype(np.float32)))

    tong = max(s["end"] for s in dung)
    master = rap(dat, tong, sr=SR)
    a.out_dir.mkdir(parents=True, exist_ok=True)
    ten = f"dub-{a.translation_id}-{len(dung)}dong"
    master_path = a.out_dir / f"{ten}.wav"
    sf.write(str(master_path), master, SR, subtype="PCM_16")
    print(f"\nmaster: {master_path} · {master.size / SR:.2f} s · {master_path.stat().st_size / 1024:.0f} kB")

    ra = xuat_dinh_dang(master_path, a.out_dir, DINH_DANG)
    for ten_dd, duong in ra.items():
        print(f"  {ten_dd:<5} {duong.stat().st_size / 1024:>8.0f} kB  {duong}")
    manh = [k for k in range(len(dung)) if toc_do[k] > a.nguong_manh]
    if manh:
        print(f"\n⚠ {len(manh)} dòng phải nén trên {a.nguong_manh}× "
              f"(đã nén ĐỦ để không chồng dòng sau): "
              + ", ".join(str(dung[k]["i"]) for k in manh))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

