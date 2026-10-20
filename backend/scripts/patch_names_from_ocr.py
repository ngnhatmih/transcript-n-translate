"""Vá tên riêng nghe nhầm trong transcript bằng caption OCR đốt trong hình.

Đây là đường CHẠY THẬT của module `experiments/accuracy_pipelines/name_patch.py`:
đưa một transcript của video MỚI và một tệp dòng OCR caption của chính video đó,
ra một transcript đã sửa chữ nguồn, giữ nguyên mọi khoá khác của tệp vào.

Vì sao CLI này KHÔNG đọc artefact của miner
    `data/experiments/.../ocr-glossary-candidates.json` và bản manual-approvals là
    đầu ra của MỘT lần đào trên MỘT clip. Đọc chúng ở đây nghĩa là video mới chỉ
    được vá những cặp đã gặp ở clip cũ — tức bước chạy thật chỉ là bước tra bảng,
    và mọi tên riêng chưa ai đào sẽ đi thẳng vào bản dịch với âm Hán-Việt của chữ
    SAI. Đầu vào của CLI đúng hai thứ: transcript và OCR của video đang xử lý.

Vì sao phải nêu `--engine`, và vì sao bỏ trống là CẢNH BÁO
    Bản vá sửa chữ NGUỒN, nên nó chỉ có lợi với engine đọc đúng chữ đã sửa. ĐO
    ĐƯỢC: áp bản vá rồi dịch bằng `opus-mt` làm **3 trong 7 câu TỆ ĐI**, trong khi
    `hy-mt-1.5-7b` được lợi. Vì vậy engine khai `capabilities.name_patch` trong
    `registry.json` (`hy-mt-1.5-7b`) mới được vá; id lạ hoặc thiếu khoá bị TỪ CHỐI
    trước khi đọc bất kỳ tệp nào, để không có tệp ra nào trông như đã vá xong.
    Bỏ trống `--engine` vẫn chạy (không có ngữ cảnh engine) nhưng in cảnh báo ra
    stderr: một lần chạy như vậy không phải đường chạy thật.

Vì sao phải ép UTF-8 cho stdout
    Console Windows mặc định cp1252 còn báo cáo in ra toàn chữ Hán: lần chạy thật
    đầu tiên sẽ `UnicodeEncodeError` ngay giữa báo cáo, sau khi đã ghi xong tệp —
    đúng kiểu hỏng im lặng khó lần. (Cùng lý do với `scripts/mine_ocr_glossary.py`
    và `scripts/smoke_asr.py`.)

Vì sao `pypinyin`/`opencc` được kiểm TRƯỚC khi đọc dữ liệu
    Thiếu gói là lỗi CÀI ĐẶT, phải báo ngay kèm lệnh cài, chứ không để nó nổ giữa
    lúc vá (khi đó tệp ra có thể đã ghi dở). Hai gói này là phụ thuộc ĐÁNH GIÁ,
    không thuộc app — chúng KHÔNG được thêm vào `requirements.txt`.

Vì sao log mặc định là `<out>.patch-log.json` chứ không phải cạnh transcript gốc
    Bản vá và bản ghi vết của nó phải đi cùng nhau: một mình tệp đã vá thì người
    đọc không biết chỗ nào bị đổi, còn log cạnh tên tệp ra thì không bao giờ lạc
    khi chạy nhiều biến thể decode trong cùng một thư mục.
"""
from __future__ import annotations

import argparse
import json
import pathlib
import sys

BACKEND_DIR = pathlib.Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from experiments.accuracy_pipelines.name_patch import (  # noqa: E402 - sau sys.path
    NAME_PATCH_CAPABILITY,
    PinyinUnavailable,
    T2sUnavailable,
    asr_segments_from_document,
    name_patch_allowed,
    ocr_rows_from_document,
    opencc_t2s,
    patch_transcript,
    pypinyin_syllables,
)

#: Sentinel riêng của CLI: `None` KHÔNG dùng được vì test cần bơm một hàm đồng
#: nhất (`lambda text: text`) để tắt OpenCC mà không nạp gói thật.
_AUTO = object()


def parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="patch_names_from_ocr.py",
        description=(
            "So caption OCR với transcript ASR trong cùng cửa sổ thời gian và vá "
            "chỗ nghe gần đồng âm của tên riêng trong chữ NGUỒN trước khi dịch."
        ),
    )
    parser.add_argument("--transcript", type=pathlib.Path, required=True,
                        help="transcript JSON (`segments` hoặc `source_segments`)")
    parser.add_argument("--ocr", type=pathlib.Path, required=True,
                        help="dòng OCR: `metadata.caption_observations` hoặc danh sách top level")
    parser.add_argument("--out", type=pathlib.Path, required=True,
                        help="transcript đã vá (giữ nguyên hình dạng tệp vào)")
    parser.add_argument("--log", type=pathlib.Path, default=None,
                        help="bản ghi vết (mặc định `<out>.patch-log.json`)")
    parser.add_argument("--window", type=float, default=0.5,
                        help="nới mỗi đầu đoạn ASR thêm bao nhiêu giây khi chọn dòng OCR")
    parser.add_argument("--threshold", type=float, default=0.5,
                        help="ngưỡng tỉ lệ khớp pinyin (> ngưỡng mới được vá)")
    parser.add_argument("--engine", default=None,
                        help="engine DỊCH sẽ dùng chữ đã vá (id trong registry.json). "
                             "Chỉ engine khai `capabilities.name_patch` mới được vá; "
                             "bỏ trống thì bản vá chạy KHÔNG kiểm capability")
    parser.add_argument("--report", action="store_true",
                        help="in từng câu đã vá dạng `i  start-end  TRƯỚC → SAU`")
    return parser.parse_args(argv)


def _engine_refused_message(engine_id: str) -> int:
    """Engine không khai `name_patch`: từ chối TRƯỚC khi đọc dữ liệu.

    ĐO ĐƯỢC lý do phải từ chối: áp bản vá rồi dịch bằng `opus-mt` làm **3 trong 7
    câu tệ đi**. Vá rồi mới phát hiện là đã ghi ra một tệp trông như thành công,
    nên cổng phải đóng ở đây — trước cả bước kiểm gói và bước đọc tệp.
    """
    allowed: list[str] = []
    try:
        from app.adapters.registry_file import load_registry
        allowed = [spec.id for spec in load_registry()
                   if getattr(spec, "kind", None) == "mt"
                   and spec.capabilities.get(NAME_PATCH_CAPABILITY)]
    except (OSError, ValueError, KeyError):
        pass
    print(
        f"KHÔNG chạy được: engine {engine_id!r} không khai "
        f"`capabilities.{NAME_PATCH_CAPABILITY}` trong registry.json.\n"
        "Bản vá sửa chữ NGUỒN nên chỉ có lợi với engine đọc đúng chữ đã sửa; "
        "đo trên `opus-mt` nó làm 3/7 câu TỆ ĐI.\n"
        f"Engine được phép vá hiện tại: {', '.join(allowed) or '(không có)'}.\n"
        "Chọn engine đó bằng --engine, hoặc bỏ --engine nếu chỉ muốn xem bản vá "
        "sinh ra gì (không dùng cho đường chạy thật).",
        file=sys.stderr,
    )
    return 2


def _force_utf8_streams() -> None:
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is not None:
            reconfigure(encoding="utf-8")


def _missing_package_message(package: str, install: str, hint: str = "") -> int:
    print(
        f"KHÔNG chạy được: thiếu gói `{package}` (chỉ dùng cho bước ĐÁNH GIÁ, "
        "không thuộc app).\n"
        f"Cài bằng: backend\\.venv\\Scripts\\python.exe -m pip install {install}\n"
        f"{hint}"
        "Gói này KHÔNG được thêm vào requirements của app.",
        file=sys.stderr,
    )
    return 2


def _read_json(path: pathlib.Path, what: str) -> object | None:
    if not path.exists():
        print(f"KHÔNG thấy {what}: {path}", file=sys.stderr)
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        print(f"KHÔNG đọc được {what} {path}: {exc}", file=sys.stderr)
        return None


def _segments_by_i(segments: list[dict]) -> dict:
    """`i` -> segment. Segment không có `i` thì dùng vị trí — đúng khoá mà module
    dùng khi ghi `changes[].i`, nên báo cáo vẫn tìm được mốc thời gian.

    Ghi theo `setdefault`: nếu hai segment trùng `i` (dữ liệu bẩn) thì bản vá đã
    lẫn, và dòng báo cáo không được phép chọn đại một mốc thời gian khác.
    """
    mapping: dict = {}
    for position, segment in enumerate(segments):
        mapping.setdefault(segment.get("i", position), segment)
    return mapping


def _print_report(changes: list[dict], segments: list[dict], limit: int = 100) -> None:
    """In mỗi CÂU đã vá đúng một lần: `i  start-end  TRƯỚC → SAU`.

    Giới hạn `limit`: một clip dài có thể vá hàng trăm câu, và một báo cáo dài
    cuộn mất phần tổng kết thì người đọc bỏ qua cả hai.
    """
    by_i = _segments_by_i(segments)
    order: list = []
    merged: dict = {}
    for change in changes:
        key = change["i"]
        if key not in merged:
            merged[key] = {"before": change["before"], "after": change["after"]}
            order.append(key)
        else:
            merged[key]["after"] = change["after"]

    print(f"câu đã vá ({len(order)}):")
    for key in order[:limit]:
        segment = by_i.get(key) or {}
        start, end = segment.get("start"), segment.get("end")
        print(
            f"{key}  {float(start):.2f}-{float(end):.2f}  "
            f"{merged[key]['before']} → {merged[key]['after']}"
        )
    if len(order) > limit:
        print(f"... còn {len(order) - limit} câu nữa (xem log)")


def _reason_summary(rejected: list[dict]) -> str:
    counts: dict[str, int] = {}
    for entry in rejected:
        counts[entry["reason"]] = counts.get(entry["reason"], 0) + 1
    if not counts:
        return "không có"
    return " · ".join(f"{reason} {counts[reason]}" for reason in sorted(counts))


def main(argv: list[str] | None = None, pinyin_fn=None, t2s_fn=_AUTO) -> int:
    _force_utf8_streams()
    args = parse_args(argv)

    # Cổng capability ĐẦU TIÊN, trước cả bước kiểm gói: engine không được phép vá
    # thì không có gì đáng cài thêm, và lý do từ chối phải hiện ra trước khi bất kỳ
    # tệp nào bị ghi (xem `_engine_refused_message`).
    if args.engine is None:
        print(
            "CẢNH BÁO: không có --engine nên bản vá KHÔNG kiểm capability "
            "`name_patch`. Đường chạy thật phải truyền --engine <id>; bỏ trống chỉ "
            "dùng để xem bản vá sinh ra gì.",
            file=sys.stderr,
        )
    elif not name_patch_allowed(args.engine):
        return _engine_refused_message(args.engine)

    # Kiểm gói TRƯỚC khi đọc dữ liệu: thiếu gói là lỗi cài đặt, phải báo ngay.
    if pinyin_fn is None:
        try:
            pypinyin_syllables("燕")
        except PinyinUnavailable:
            return _missing_package_message("pypinyin", "pypinyin")
        pinyin_fn = pypinyin_syllables

    if t2s_fn is _AUTO:
        try:
            opencc_t2s("國")
        except T2sUnavailable:
            return _missing_package_message(
                "opencc",
                "opencc-python-reimplemented",
                "Tên gói trên PyPI là `opencc-python-reimplemented` nhưng import là `opencc`.\n",
            )
        t2s_fn = opencc_t2s

    document = _read_json(args.transcript, "transcript")
    if document is None:
        return 2
    ocr_document = _read_json(args.ocr, "tệp OCR")
    if ocr_document is None:
        return 2

    try:
        key, segments = asr_segments_from_document(document)
        rows = ocr_rows_from_document(ocr_document)
    except ValueError as exc:
        print(f"KHÔNG chạy được: {exc}", file=sys.stderr)
        return 2

    result = patch_transcript(
        segments,        rows,
        pinyin_fn=pinyin_fn,
        t2s_fn=t2s_fn,
        window_s=args.window,
        threshold=args.threshold,
        # Cổng đã cho qua ở trên, nhưng `patch_transcript` tự kiểm LẠI: nó cũng là
        # đường vào của các pipeline thử nghiệm, và một lời gọi bỏ qua CLI không
        # được vá bằng engine chưa đo.
        engine_id=args.engine,
    )

    # Giữ NGUYÊN hình dạng tệp vào: chỉ thay đúng danh sách segment, mọi khoá khác
    # (`model`, `configuration`, `inference_seconds`, ...) đi ra y nguyên.
    document[key] = result.segments
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(
        json.dumps(document, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )

    log_path = args.log or pathlib.Path(str(args.out) + ".patch-log.json")
    log_path.parent.mkdir(parents=True, exist_ok=True)
    log_path.write_text(
        json.dumps(
            {
                "changes": result.changes,
                "rejected": result.rejected,
                "stats": result.stats,
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )

    stats = result.stats
    print(
        f"transcript: {stats['segments']} đoạn · OCR: {stats['ocr_rows']} dòng · "
        f"cặp chồng thời gian: {stats['overlaps']}"
    )
    print(f"engine: {args.engine or '(không nêu — không kiểm capability)'}"
          f" · name_patch: {stats.get('name_patch')}")
    print(f"vá: {stats['applied']} · loại: {stats['rejected']}")
    print(f"lý do loại: {_reason_summary(result.rejected)}")
    if args.report:
        print("")
        _print_report(result.changes, result.segments)
    print("")
    print(f"đã ghi {args.out}")
    print(f"đã ghi {log_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
