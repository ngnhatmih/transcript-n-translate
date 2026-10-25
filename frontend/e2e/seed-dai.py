"""Gieo them MOT BAN GHI DAI vao DB e2e — de do CAI GIA cua ban va D4 (Task 12, T7).

Vi sao can: vong gom no Task 11 dua `currentSegment` vao tap GHIM cua danh sach ao hoa
(`EditScreen.tsx -> windowFor`). He qua CHUA AI DO: khi `editingSegment` va `currentSegment` XA
nhau, cua so phai render TOAN BO khoang giua chung ⇒ mot cum `N`/`J`/`K` nhay xa tren ban ghi dai
co the render hang tram hang.

Script nay chi gieo DU LIEU; phep do nam trong ke hoach Chrome (`plans/`), vi "so hang co trong
DOM" la mot phep do DOM THAT, khong phai mot suy luan tu so hoc.

🔴 VONG SUA 1 (`I4e`): ban gieo nay dat `suspect=True` o **HAI** doan — `i=1` (TRONG cua so ban dau)
va `i=481` (NGOAI cua so, ngoai ca TRAN ghim). Ly do DO DUOC: luot T7 truoc gieo 600 doan **khong co
doan `suspect` nao**, nen buoc "bam `n`" khong co DICH ⇒ do duoc `is-current` van la 0 sau 4 lan bam
`n`, va 17 hang trong DOM khong noi gi ve cai gia cua ghim. Phim `n` di tu doan nghi ngo nay sang doan
nghi ngo KE TIEP, nen hai moc nay cho dung canh `1 -> 481` ma `D4` nham toi — **khong can cuon tay**.

Dung: `<venv python> seed-dai.py <backend_dir> <db_path> [so_doan] [media]`
"""
import sys

BACKEND, DB = sys.argv[1], sys.argv[2]
SO_DOAN = int(sys.argv[3]) if len(sys.argv) > 3 else 600

sys.path.insert(0, BACKEND)

from app.adapters.clock_system import SystemClock  # noqa: E402
from app.adapters.persist.sqlite_repos import SqliteRepos  # noqa: E402
from app.domain.models import Segment  # noqa: E402

repos = SqliteRepos(DB, clock=SystemClock())
repos.init_schema()

# `media_path` phai TON TAI: Transport lay `src` tu `GET /api/media/{id}`, mot tep khong co lam
# trinh phat 404 — hong vi ly do chang lien quan gi toi bo cuc.
media = sys.argv[4] if len(sys.argv) > 4 else "seed.wav"
sid = repos.add_source(
    kind="file", origin=f"ban-ghi-dai-{SO_DOAN}.wav", media_path=media, lang="zh",
    duration=float(SO_DOAN),
)
# Hai doan NGHI NGO: `i=1` (trong cua so ban dau) va `i=481` (ngoai cua so ⇒ phai CUON toi). Xem
# docblock: thieu chung thi buoc `n` cua ke hoach khong co dich, va phep do tro thanh vo nghia.
NGHI_NGO = {1, 481}
segs = [
    Segment(
        i=i, start=float(i - 1), end=float(i), text=f"doan {i} 今天我們來說一個很重要的問題。",
        suspect=i in NGHI_NGO,
    )
    for i in range(1, SO_DOAN + 1)
]
tid = repos.add_transcript(source_id=sid, engine="fw-small", lang="zh", segments=segs)
# Mot ban dich `done` de man Doi chieu co du lieu cho ban ghi dai (khong bat buoc cho T7).
repos.add_translation(
    transcript_id=tid, transcript_version=1, engine="opus-mt", target_lang="vi",
    prompt_version="opus-p1", status="done",
    segments=[Segment(i=i, start=float(i - 1), end=float(i), text=f"doan {i}") for i in range(1, SO_DOAN + 1)],
)
print(f"[seed-dai] source={sid} transcript={tid} so_doan={SO_DOAN}")
