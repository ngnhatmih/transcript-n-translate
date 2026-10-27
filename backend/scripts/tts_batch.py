"""TTS batch — chạy trong venv RIÊNG (`.venv-tts`), không phải venv của app.

Vì sao venv riêng: `pip install vieneu` kéo `huggingface_hub 2.x` + `starlette 1.x`, và
`transformers 4.46` của app đòi `huggingface_hub <1.0` + `tokenizers <0.21` — hai bộ không ở
chung một venv được (đo được: pip cài xong thì `import transformers` ném ImportError). Nên TTS
sống trong `.venv-tts`, app gọi nó qua ĐÚNG MỘT tiến trình cho cả lượt: nạp model 62 s, nên
spawn mỗi dòng một lần là 461 lượt nạp.

Vào/ra (JSON, cả hai qua tệp để không đụng encoding của console Windows):

    { "items": [{"i": 0, "text": "..."}], "voice": "Minh Quân", "out_dir": "..." }

    {"ok": [{"i": 0, "seconds": 3.36, "path": "..."}], "loi": [{"i": 5, "error": "..."}]}
"""
import json
import pathlib
import sys


def main(viec: pathlib.Path) -> int:
    yeu_cau = json.loads(viec.read_text(encoding="utf-8"))
    out_dir = pathlib.Path(yeu_cau["out_dir"])
    out_dir.mkdir(parents=True, exist_ok=True)

    from vieneu import Vieneu

    tts = Vieneu()
    giong = yeu_cau.get("voice")
    ok, loi = [], []
    # ── BATCH, KHÔNG TỪNG CÂU ───────────────────────────────────────────────────────────────
    # ⚠️ ĐO ĐƯỢC trên RTX 3070 với chính model này (100 câu, 475,0 giây tiếng):
    #   `infer_batch(batch_size=16)` → 9,36 s  ⇒ RTF **0,020**
    #   `infer` từng câu (30 câu)    → 18,2 s  ⇒ RTF **0,132**
    # Tức gọi từng câu CHẬM HƠN 6,7 LẦN so với batch, vì mỗi lượt `infer` trả giá khởi động
    # graph/kernel riêng. Với cả file 434 dòng (803,8 s audio): batch ≈ 0,26 phút, từng câu
    # ≈ 1,77 phút. Vòng lặp từng câu cũ bỏ phí đúng khoản đó.
    #
    # ⚠️ VÌ SAO VẪN PHẢI GIỮ CÁCH LY LỖI TỪNG DÒNG: hợp đồng với `dub.py` là mỗi dòng hỏng
    # được báo riêng trong `loi`, không làm hỏng cả lượt. `infer_batch` ném cho CẢ LÔ, nên khi
    # một lô ném ta quay lại gọi từng câu trong lô đó — chậm cho lô hỏng, nhưng đúng hợp đồng
    # và không mất dòng nào.
    import soundfile as sf

    LO = 16

    def _luu(i: int, audio) -> dict:
        dich = out_dir / f"{i:05d}.wav"
        tts.save(audio, str(dich))
        du_lieu, sr = sf.read(str(dich))
        return {"i": i, "seconds": len(du_lieu) / sr, "path": str(dich)}

    items = yeu_cau["items"]
    for dau in range(0, len(items), LO):
        lo = items[dau:dau + LO]
        try:
            am = tts.infer_batch([x["text"] for x in lo], voice=giong, batch_size=LO)
        except Exception:  # noqa: BLE001
            # Lô hỏng ⇒ rơi về từng câu để biết CHÍNH XÁC dòng nào hỏng và vì sao.
            am = None
        if am is not None and len(am) == len(lo):
            for item, audio in zip(lo, am):
                try:
                    ok.append(_luu(item["i"], audio))
                except Exception as exc:  # noqa: BLE001
                    loi.append({"i": item["i"], "error": f"{type(exc).__name__}: {exc}"[:300]})
            continue
        for item in lo:
            try:
                audio = tts.infer(item["text"], voice=giong) if giong else tts.infer(item["text"])
                ok.append(_luu(item["i"], audio))
            except Exception as exc:  # noqa: BLE001 - một dòng hỏng không làm hỏng cả lượt
                loi.append({"i": item["i"], "error": f"{type(exc).__name__}: {exc}"[:300]})

    ra = pathlib.Path(yeu_cau["result"])
    ra.write_text(json.dumps({"ok": ok, "loi": loi}, ensure_ascii=False), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(pathlib.Path(sys.argv[1])))
