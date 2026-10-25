"""Gieo MOT KENH co du lieu CHIMERA THAT vao DB e2e — de tang Chrome do §4.5.

⚠️ TOAN BO du lieu trong `DU_LIEU` la BAN CHUP NGUYEN VAN cua mot luot chay THAT:
`_chimera-scratch/measure/run2.json` (composition root THAT, `opus-mt` + `qwen2.5-3b` +
`qwen2.5-7b` THAT, Ollama THAT). No KHONG phai du lieu bia: bon ung vien qwen trong ban
ghi do tra ve DUNG chu Han cua ban goc (`echo = 6/6`), va luot pha tra ve chu Y HET mo
neo (`identical_segments = [1..6]`) — hai su that kho noi nhat cua tinh nang nay, va
chung chi do duoc bang cach chay that.

Vi sao phai gieo bang script chu khong tao qua giao dien: `serve_no_worker.py` chay
backend KHONG kem worker, nen mot job `translate` xep qua UI se khong bao gio chay. Du
lieu o day la KET QUA cua mot luot da chay that, duoc ghi lai.

Dung: `<venv python> seed-chimera.py <backend_dir> <db_path> [media_path]`
"""
import json
import sys

BACKEND, DB = sys.argv[1], sys.argv[2]
MEDIA = sys.argv[3] if len(sys.argv) > 3 else "seed.wav"

sys.path.insert(0, BACKEND)

from app.adapters.clock_system import SystemClock  # noqa: E402
from app.adapters.persist.sqlite_repos import SqliteRepos  # noqa: E402
from app.domain.models import Segment  # noqa: E402

DU_LIEU = json.loads(r"""{"nguon": "run2.json — composition root THAT + engine THAT (opus-mt, qwen2.5-3b, qwen2.5-7b) + Ollama THAT", "source_texts": ["大家好，欢迎来到今天的节目。", "今天我们来说一个很多人都关心的问题。", "首先我们看一组数据。", "这个数字比去年同期增长了不少。", "那么，接下来会发生什么呢？", "我们下期再见。"], "record": {"declared": 6, "run_count": 5, "calls_per_batch": 6, "merge_engine": "qwen2.5-3b", "estimate": {"calls_per_batch": 6, "duration_ms": 5682, "tokens_in": 1536, "tokens_out": 660}, "estimate_basis": "đo từ bản dịch #2 (qwen2.5-3b): 947 ms / 6 đoạn", "baseline": {"translation_id": 2, "engine": "qwen2.5-3b", "segments": 6, "duration_ms": 947, "tokens_in": 256, "tokens_out": 110}, "segments": 6, "enabled": true, "ran_count": 5, "anchors": {"c1": 6}, "distinct_by_segment": {"1": 3, "2": 3, "3": 3, "4": 3, "5": 3, "6": 3}, "candidates": [{"id": "c1", "engine": "opus-mt", "label": "OPUS-MT (Marian, tất định)", "temperature": null, "quality_note": null, "available": true, "reason": null, "ran": true, "skipped": null, "qa": 3, "cps_over": 3, "echo": 0, "segments": [{"i": 1, "text": "Chào mừng các bạn đến với chương trình hôm nay."}, {"i": 2, "text": "Hôm nay chúng ta nói về một vấn đề mà rất nhiều người quan tâm."}, {"i": 3, "text": "Đầu tiên, chúng ta sẽ xem qua các dữ liệu."}, {"i": 4, "text": "Con số này lớn hơn rất nhiều so với năm ngoái."}, {"i": 5, "text": "Vậy chuyện gì sẽ xảy ra?"}, {"i": 6, "text": "Hẹn gặp lại vào kỳ tới."}], "calls": 1, "tokens_in": null, "tokens_out": null, "duration_ms": null}, {"id": "c2", "engine": "qwen2.5-3b", "label": "Qwen-3B nhiệt độ 0,1", "temperature": 0.1, "quality_note": "ĐÃ ĐO: ở prompt p1 engine này CHÉP nguyên chữ nguồn 43/44 đoạn; p2 mới dịch được. Số đoạn nhại lại được ĐO LẠI sau mỗi lần chạy (trường `echo`).", "available": true, "reason": null, "ran": true, "skipped": null, "qa": 6, "cps_over": 0, "echo": 6, "segments": [{"i": 1, "text": "大家好，欢迎来到今天的节目。"}, {"i": 2, "text": "今天我们来说一个很多人都关心的问题。"}, {"i": 3, "text": "首先我们看一组数据。"}, {"i": 4, "text": "这个数字比去年同期增长了不少。"}, {"i": 5, "text": "那么，接下来会发生什么呢？"}, {"i": 6, "text": "我们下期再见。"}], "calls": 1, "tokens_in": 256, "tokens_out": 110, "duration_ms": 693}, {"id": "c3", "engine": "qwen2.5-3b", "label": "Qwen-3B nhiệt độ 0,7", "temperature": 0.7, "quality_note": "Cùng engine như c2, lấy mẫu rộng hơn: đa dạng hơn nhưng cũng dễ trôi khỏi bản gốc hơn.", "available": true, "reason": null, "ran": true, "skipped": null, "qa": 6, "cps_over": 0, "echo": 0, "segments": [{"i": 1, "text": "大家好，欢迎收看今天的节目。"}, {"i": 2, "text": "今天我们来讨论一个很多人都关心的话题。"}, {"i": 3, "text": "首先我们来看一组数据。"}, {"i": 4, "text": "这个数字比去年同期有所上升。"}, {"i": 5, "text": "那么接下来会发生什么？"}, {"i": 6, "text": "我们下次节目再见。"}], "calls": 1, "tokens_in": 256, "tokens_out": 111, "duration_ms": 698}, {"id": "c4", "engine": "qwen2.5-3b", "label": "Qwen-3B nhiệt độ 1,0", "temperature": 1.0, "quality_note": "Cùng engine như c2, lấy mẫu rộng nhất trong ba mức: dùng để ĐO độ tất định của engine, không phải để tin.", "available": true, "reason": null, "ran": true, "skipped": null, "qa": 6, "cps_over": 0, "echo": 5, "segments": [{"i": 1, "text": "大家好，欢迎来到今天的节目。"}, {"i": 2, "text": "今天我们来说一个很多人都关心的问题。"}, {"i": 3, "text": "首先我们来看一组数据。"}, {"i": 4, "text": "这个数字比去年同期增长了不少。"}, {"i": 5, "text": "那么，接下来会发生什么呢？"}, {"i": 6, "text": "我们下期再见。"}], "calls": 1, "tokens_in": 256, "tokens_out": 110, "duration_ms": 692}, {"id": "c5", "engine": "qwen2.5-7b", "label": "Qwen-7B nhiệt độ 0,1", "temperature": 0.1, "quality_note": null, "available": true, "reason": null, "ran": true, "skipped": null, "qa": 6, "cps_over": 0, "echo": 6, "segments": [{"i": 1, "text": "大家好，欢迎来到今天的节目。"}, {"i": 2, "text": "今天我们来说一个很多人都关心的问题。"}, {"i": 3, "text": "首先我们看一组数据。"}, {"i": 4, "text": "这个数字比去年同期增长了不少。"}, {"i": 5, "text": "那么，接下来会发生什么呢？"}, {"i": 6, "text": "我们下期再见。"}], "calls": 1, "tokens_in": 256, "tokens_out": 110, "duration_ms": 1324}, {"id": "c6", "engine": "hy-mt-1.5-7b", "label": "HY-MT 1.5 nhiệt độ 0,1 (đúng §8.7.5)", "temperature": 0.1, "quality_note": null, "available": false, "reason": "engine 'hy-mt-1.5-7b' chưa sẵn sàng: model chưa được pull, hoặc runtime không phục vụ được", "ran": false, "skipped": "engine 'hy-mt-1.5-7b' chưa sẵn sàng: model chưa được pull, hoặc runtime không phục vụ được", "qa": 0, "cps_over": 0, "echo": 0, "segments": [], "calls": 0, "tokens_in": null, "tokens_out": null, "duration_ms": null}], "merge": {"engine": "qwen2.5-3b", "calls": 1, "tokens_in": 749, "tokens_out": 147, "duration_ms": 1010, "fallback_segments": [], "fallback_reason": null, "anchor_by_segment": {"1": 1, "2": 1, "3": 1, "4": 1, "5": 1, "6": 1}, "identical_segments": [1, 2, 3, 4, 5, 6]}}, "merged_texts": ["Chào mừng các bạn đến với chương trình hôm nay.", "Hôm nay chúng ta nói về một vấn đề mà rất nhiều người quan tâm.", "Đầu tiên, chúng ta sẽ xem qua các dữ liệu.", "Con số này lớn hơn rất nhiều so với năm ngoái.", "Vậy chuyện gì sẽ xảy ra?", "Hẹn gặp lại vào kỳ tới."], "opus_texts": ["Chào mừng các bạn đến với chương trình hôm nay.", "Hôm nay chúng ta nói về một vấn đề mà rất nhiều người quan tâm.", "Đầu tiên, chúng ta sẽ xem qua các dữ liệu.", "Con số này lớn hơn rất nhiều so với năm ngoái.", "Vậy chuyện gì sẽ xảy ra?", "Hẹn gặp lại vào kỳ tới."], "qwen_texts": ["大家好，欢迎来到今天的节目。", "今天我们来说一个很多人都关心的问题。", "首先我们看一组数据。", "这个数字比去年同期增长了不少。", "那么，接下来会发生什么呢？", "我们下期再见。"], "qa_issues": ["cps:1=23.5>21.0", "cps:2=31.5>21.0", "cps:4=23.0>21.0"], "actual": {"tokens_in": 1773, "tokens_out": 588, "duration_ms": 4417}, "baseline_qwen": {"engine": "qwen2.5-3b", "duration_ms": 947, "tokens_in": 256, "tokens_out": 110}}""")


def doan(i: int, text: str) -> Segment:
    return Segment(i=i, start=float(i * 2 - 2), end=float(i * 2), text=text)


def main() -> int:
    repos = SqliteRepos(DB, clock=SystemClock())
    repos.init_schema()

    src = DU_LIEU["source_texts"]
    sid = repos.add_source(kind="file", origin="chimera-do-that.wav",
                           media_path=MEDIA, lang="zh", duration=12.0)
    tid = repos.add_transcript(source_id=sid, engine="fw-large-v3-turbo", lang="zh",
                               segments=[doan(i, t) for i, t in enumerate(src, start=1)])

    # (A) Luot dich THUONG bang engine Ollama — CO thoi gian/token that, nen no la CO SO
    #     DO cho canh bao chi phi (opus-mt chay trong tien trinh nen khong bao gi).
    b = DU_LIEU["baseline_qwen"]
    repos.add_translation(
        transcript_id=tid, transcript_version=1, engine=b["engine"], target_lang="vi",
        prompt_version="qwen-json-p2", status="done",
        segments=[doan(i, t) for i, t in enumerate(DU_LIEU["qwen_texts"], start=1)],
        duration_ms=b["duration_ms"], tokens_in=b["tokens_in"], tokens_out=b["tokens_out"],
        qa_issues=["lang:%d=source:han6/latin0" % i for i in range(1, len(src) + 1)])

    # (B) Luot dich THUONG bang opus-mt — KHONG co token/thoi gian (engine trong tien
    #     trinh), de anh chup thay duoc CA HAI trang thai cua cot CPS va cua canh bao.
    repos.add_translation(
        transcript_id=tid, transcript_version=1, engine="opus-mt", target_lang="vi",
        prompt_version="raw-p1", status="done",
        segments=[doan(i, t) for i, t in enumerate(DU_LIEU["opus_texts"], start=1)],
        qa_issues=DU_LIEU["qa_issues"])

    # (C) Luot CHIMERA — hang moi nhat, nen man Doi chieu mo no truoc.
    a = DU_LIEU["actual"]
    tr = repos.add_translation(
        transcript_id=tid, transcript_version=1, engine="qwen2.5-3b", target_lang="vi",
        prompt_version="chimera-merge-p1", status="done",
        segments=[doan(i, t) for i, t in enumerate(DU_LIEU["merged_texts"], start=1)],
        qa_issues=DU_LIEU["qa_issues"], tokens_in=a["tokens_in"],
        tokens_out=a["tokens_out"], duration_ms=a["duration_ms"],
        chimera=DU_LIEU["record"])
    print(f"[seed-chimera] source={sid} transcript={tid} chimera_translation={tr} "
          f"candidates={len(DU_LIEU['record']['candidates'])}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
