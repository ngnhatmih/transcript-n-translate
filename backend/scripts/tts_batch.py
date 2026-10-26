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
    for item in yeu_cau["items"]:
        dich = out_dir / f"{item['i']:05d}.wav"
        try:
            audio = tts.infer(item["text"], voice=giong) if giong else tts.infer(item["text"])
            tts.save(audio, str(dich))
            import soundfile as sf

            du_lieu, sr = sf.read(str(dich))
            ok.append({"i": item["i"], "seconds": len(du_lieu) / sr, "path": str(dich)})
        except Exception as exc:  # noqa: BLE001 - một dòng hỏng không làm hỏng cả lượt
            loi.append({"i": item["i"], "error": f"{type(exc).__name__}: {exc}"[:300]})

    ra = pathlib.Path(yeu_cau["result"])
    ra.write_text(json.dumps({"ok": ok, "loi": loi}, ensure_ascii=False), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(pathlib.Path(sys.argv[1])))
