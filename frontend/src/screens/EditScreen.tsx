/**
 * §4.1 Man BIEN TAP — man hinh DAU TIEN cua ban lam viec.
 *
 * Ba thu cua spec UI:
 *  1. **Rail thoi gian + danh sach doan AO HOA** (§4.1, §8.2: transcript 2 gio ≈ 2000
 *     dong). Cua so tinh bang HAI ham thuan cua Task 5 (`src/lib/window.ts`), va co DEM
 *     hai dau — thieu dem thi chieu cao cuon chi bang cua so, tuc KHONG cuon duoc qua
 *     danh sach dai.
 *  2. **Dong dang sua duoc GHIM** (§5.3/U6): ao hoa khong duoc thao dong dang go ra khoi
 *     DOM, vi the la MAT FOCUS giua luc nguoi dung dang go.
 *  3. **`suspect` la VAN, khong phai MAU** (§2.5) va di kem LY DO bang CHU (§7: thong tin
 *     khong duoc chi nam o mau — nguoi mu mau se mat no). Van nam trong CSS (`app.css`),
 *     khong nam trong logic: lop `is-suspect` chi la cai TEN, con hinh dang van la viec cua
 *     `--suspect-hatch-*` trong `tokens.css`.
 *
 * ## LY DO nghi ngo lay tu dau — va cai KHONG lam
 *
 * Hai nguon, ca hai deu la TRUONG CO SAN tren `Segment` (`src/api/types.ts`):
 *  - `events`: ma su kien cua engine. Bo ma "dang nghi" do CHINH BACKEND dinh nghia
 *    (`backend/app/adapters/asr/sensevoice.py`, hang `SUSPICIOUS_EVENTS`) — o day chi DICH
 *    ma do sang chu, khong tu quyet dinh the nao la nghi ngo.
 *  - `qa`: ma QA cua backend (vi du `thieu_dau`), cung chi duoc DICH sang chu.
 *  - Khong co ma nao dich duoc ⇒ nhan CHUNG `nghi ngo`, dung co `suspect` ma backend da tinh.
 *
 * ⚠️ KHONG tinh lai o client thu backend da tinh (Global Constraints cua plan): man nay
 * TUYET DOI khong ap lai nguong `SUSPECT_NO_SPEECH_PROB`/`SUSPECT_AVG_LOGPROB` len
 * `no_speech_prob`/`avg_logprob` de "suy ra" nghi ngo. Co `suspect` la du lieu backend
 * gui, va no la thu duy nhat quyet dinh VAN. Hai noi cung tinh mot dai luong la dung thu
 * Giai doan 2 vua phai di va.
 *
 * `ponytail:` TRAN cua bang dich ma: ma la khong co trong bang se bi BO (khong bia chu).
 * Tran nay se lo ra khi mot engine tra ma moi — luc do bang phai lon len, hoac tot hon:
 * de BACKEND gui kem nhan chu.
 *
 * ## Nhung gi man nay KHONG lam (khai ra, khong che)
 *
 *  - **Khong do `clientHeight`** cua khung cuon: xem `VIEWPORT_H`.
 *  - **Khong nap du lieu**: `transcript` la PROP (brief §1a) — man nay khong tu `fetch`.
 *  - **TRANG THAI RONG nay LA KHUNG §4.2** (Task W2): truoc W2, `uploadSource` co **0 luot
 *    goi** va `frontend/src` **khong co** `type="file"`/`onDrop` nao ⇒ ve khung "KÉO TỆP VÀO
 *    ĐÂY" ma tha tep vao khong co gi xay ra la mot giao dien **NOI DOI**, nen Task 6 co y
 *    khong ve no. Nay duong NAP CO THAT (`App.napTep`), nen loi hua do duoc giu: vung giua
 *    cua trang thai rong la `<IntakeFrame/>` — khung ke net dut + dong mono §4.2.
 *    ⚠️ Man nay **KHONG** tu goi API: no chi TRUYEN `onNapTep` xuong (MOT ham nap o `App`,
 *    dung cho ca hai loi vao — xem `src/shell/IntakeFrame.tsx`).
 *  - **Khong xu ly BANG PHIM DAY DU** (`J`/`K`/`Space`/`N`, spec UI §5.1): do la Task 11. Man nay
 *    chi co HAI phim gan voi CHINH o dang mo (`Enter` luu, `Esc` huy) va duong CHUOT (bam dong ⇒
 *    xin mo o sua). ⚠️ `[`/`]` (nudge moc) do `App` bat o cap `window` — cung MOT duong GHI
 *    (`PATCH /api/transcripts/{id}`) voi nut `luu`, va man nay chi BAO bang `onNudge`.
 *  - **Khong GHI gi**: moi thao tac ghi (`luu`, `nudge`) la mot CALLBACK ra ngoai. Man nay khong
 *    `fetch`, khong tu sua `Segment`, khong giu ban sao du lieu may chu, va KHONG tu clamp moc
 *    thoi gian (phep kep giay am nam o `formatTimecode`).
 */
import { useState } from "react";

import type { Segment, Transcript } from "../api/types.ts";
import { formatTimecode } from "../lib/timecode.ts";
import { visibleRange, withPinned } from "../lib/window.ts";
import { IntakeFrame } from "../shell/IntakeFrame.tsx";
import type { NapTep } from "../shell/IntakeFrame.tsx";

/** Cao mot hang (spec UI §2.3: 32px mot dong, 44px hai dong — mac dinh hai dong). */
export const ROW_H = 44;
/** So hang thua hai dau khi ao hoa — de cuon nhanh khong thay khoang trang. */
export const OVERSCAN = 5;

/**
 * Cao khung nhin mac dinh cho ao hoa.
 *
 * `ponytail:` TRAN — man nay KHONG do `clientHeight` cua khung that. jsdom khong co
 * layout (ERRATA #5 muc 4.4), nen duong do do KHONG kiem duoc o moi truong nay, va them
 * mot duong khong kiem duoc vao san pham la thu du an nay cam. ⇒ gia tri nay la THAM SO
 * co mac dinh, va no van phai giu vai tro mac dinh ke ca khi co duong do (luc khung chua
 * co kich thuoc). Duong nang cap: `ResizeObserver` tren `.ed__khung`, cong mac dinh nay.
 */
export const VIEWPORT_H = 480;

/** Nhan chu cho ma su kien cua engine (`sensevoice.py`, hang `SUSPICIOUS_EVENTS`). */
const NHAN_SU_KIEN: Record<string, string> = {
  bgm: "nhạc nền",
  laughter: "tiếng cười",
  cry: "tiếng khóc",
  applause: "vỗ tay",
};

/** Nhan chu cho ma `qa` cua backend (vi du `thieu_dau` trong test backend). */
const NHAN_QA: Record<string, string> = {
  thieu_dau: "thiếu dấu câu",
  too_long: "câu quá dài",
  check: "cần kiểm lại",
};

/** Nhan chung khi khong ma nao dich duoc — KHONG bia nguyen nhan. */
export const LY_DO_CHUNG = "nghi ngờ";

/**
 * LY DO hien canh doan nghi ngo, hoac `null` khi doan khong bi nghi ngo.
 *
 * `null` (khong phai chuoi rong) la co y: no phan biet "khong co gi de noi" voi "co noi
 * nhung noi rong", va nho vay nhan chi ton tai khi that su co ly do.
 */
function lyDoNghiNgo(seg: Segment): string | null {
  if (!seg.suspect) return null;
  const nhan: string[] = [];
  for (const ma of seg.events ?? []) {
    const chu = NHAN_SU_KIEN[ma];
    if (chu !== undefined) nhan.push(chu);
  }
  for (const ma of seg.qa ?? []) {
    const chu = NHAN_QA[ma];
    if (chu !== undefined) nhan.push(chu);
  }
  return nhan.length === 0 ? LY_DO_CHUNG : nhan.join(" · ");
}

/** Ky tu moi dong dung de UOC luong so dong cua o sua (xem `soDong`). */
const KY_TU_MOI_DONG = 60;

/**
 * So dong uoc luong cua o sua — thu lam cho `<textarea>` TU GIAN.
 *
 * `ponytail:` TRAN — day la uoc luong theo DO DAI CHU, khong phai theo NGAT DONG THAT:
 * ngat dong that phu thuoc font, be rong cot va ky tu trong chuoi, khong co cai nao do
 * duoc o jsdom (khong layout). ⇒ voi chu toan ky tu rong, o sua co the cao hon hoac thap
 * hon mot chut so voi noi dung. Duong nang cap: `field-sizing: content` (CSS) hoac do
 * `scrollHeight` trong `useLayoutEffect` — ca hai deu phai do tren trinh duyet THAT.
 */
function soDong(text: string): number {
  return Math.max(1, Math.ceil(text.length / KY_TU_MOI_DONG));
}

/**
 * Cua so hang can render: `visibleRange` + GHIM dong dang sua, ROI KEP `end` theo SO DOAN.
 *
 * ⚠️ Vi sao phai kep (no `M4` cua review Task 5): `withPinned` **KHONG** kep theo `count`
 * — do duoc `withPinned({start: 100, end: 120}, 500)` ⇒ `end = 501`. Chi so ghim lon hon
 * so doan la chuyen CO THAT (ban ghi vua doi, hoac `editingSegment` cu con lai), va `end`
 * o day duoc dung de tinh DEM CUOI `(soDoan - end) * ROW_H`: `end > soDoan` ⇒ dem AM ⇒
 * chieu cao cuon co lai (va trong trinh duyet mot chieu cao am bi CSS loai bo, nen danh
 * sach mat doan cuon). `window.ts` da duoc review `PASS` va KHONG duoc sua trong task nay,
 * nen phep kep nam o DAY, tai cho goi, va co bai test ghim rieng.
 */
export function windowFor(
  scrollTop: number,
  viewportH: number,
  rowH: number,
  soDoan: number,
  overscan: number,
  pinned: number | null,
): { start: number; end: number; pinned: boolean } {
  const cuaSo = withPinned(visibleRange(scrollTop, viewportH, rowH, soDoan, overscan), pinned);
  return { start: cuaSo.start, end: Math.min(cuaSo.end, soDoan), pinned: cuaSo.pinned };
}

export interface EditScreenProps {
  /** Ban ghi dang bien tap; `null` = chua co ban ghi nao (xem TRANG THAI RONG o dau tep). */
  transcript: Transcript | null;
  /**
   * HÀM NẠP TỆP dùng chung — do `App` cài đặt và truyền xuống (brief W2: **MỘT** hàm, hai lối
   * vào). Màn này KHÔNG tự nạp: nó chỉ đặt khung §4.2 vào vùng giữa của trạng thái rỗng.
   *
   * ⚠️ BẮT BUỘC, không phải tuỳ chọn: một khung kéo-thả không có gì để gọi là một lời hứa suông
   * (đúng thứ Task 6 đã từ chối vẽ), nên không có nhánh "khung rỗng ruột" nào ở đây.
   */
  onNapTep: NapTep;
  /** Doan dang phat (`UiState.currentSegment`) — le trai amber, spec UI §4.1. */
  currentSegment?: number | null;
  /** Doan dang sua (`UiState.editingSegment`) — duoc GHIM, spec UI §5.3/U6. */
  editingSegment?: number | null;
  /** Goi khi nguoi dung BAM mot dong. Chu trang thai "dang sua dong nao" la BEN GOI. */
  onStartEdit?: (i: number) => void;
  /** Goi khi nguoi dung LUU (`Enter`/nut `luu`) voi chu MOI; ban nhap khong nam trong DOM. */
  onCommitEdit?: (i: number, text: string) => void;
  /**
   * Goi khi nguoi dung HUY (`Esc`/nut `huy`). ⚠️ HUY KHONG GHI GI: no chi bao cho ben goi biet
   * de `endEdit` — va day la duong DUY NHAT khong di qua `onCommitEdit`.
   */
  onCancelEdit?: () => void;
  /**
   * Nudge mot MOC cua dong DANG SUA: `"start"` = mốc bắt đầu −0,1s, `"end"` = mốc kết thúc +0,1s.
   * ⚠️ Bảng phím này là **của BRIEF D1**, KHÔNG phải của spec UI: spec UI §5.1 gán `[`/`]` cho
   * *"đặt mốc tại đầu đọc"* và nudge cho `Shift/Alt+←/→` (ERRATA #44 mục 3) — việc đổi khoá thuộc
   * **Task 11**. ⚠️ Man nay KHONG tu sua mốc: nó chỉ BÁO, còn ben goi mới là người GHI
   * (`PATCH /api/transcripts/{id}`) — và khi KHÔNG có dòng nào đang sửa thì ben goi KHÔNG LÀM GÌ.
   */
  onNudge?: (moc: "start" | "end") => void;
  /** Đang ghi (PATCH đang bay) — trạng thái phải NÓI RA, không chỉ đổi màu. */
  dangLuu?: boolean;
  /** Lỗi ghi, **NGUYÊN VĂN `ApiError.message`** (`"<status>: <detail>"`). `null` = không có. */
  loiGhi?: string | null;
  /**
   * Câu nói ra rằng BẢN DỊCH ĐÃ LỖI THỜI so với bản ghi — do `App` QUYẾT và truyền CÂU xuống
   * (cùng khuôn `Transport.xuatCho`): truyền `stale` xuống sẽ để màn này quyết lần thứ hai.
   */
  cauLoiThoi?: string | null;
  /** Vi tri cuon KHOI TAU; sau do man tu giu theo su kien `scroll` cua khung. */
  scrollTop?: number;
  /** Cao khung nhin — mac dinh `VIEWPORT_H` (xem TRAN o do). */
  viewportH?: number;
  /** Cao mot hang — mac dinh `ROW_H`. */
  rowH?: number;
  /** So hang thua hai dau — mac dinh `OVERSCAN`. */
  overscan?: number;
}

export function EditScreen({
  transcript,
  onNapTep,
  currentSegment = null,
  editingSegment = null,
  onStartEdit,
  onCommitEdit,
  onCancelEdit,
  onNudge,
  dangLuu = false,
  loiGhi = null,
  cauLoiThoi = null,
  scrollTop = 0,
  viewportH = VIEWPORT_H,
  rowH = ROW_H,
  overscan = OVERSCAN,
}: EditScreenProps) {
  // Trang thai CUON la chuyen cua khung nhin, khong phai chuyen cua reducer: no khong
  // thuoc ve "kenh nao / doan nao / che do nao" (xem `src/state/reducer.ts`).
  const [cuon, setCuon] = useState(scrollTop);
  // BAN NHAP cua o dang sua: giu trong STATE, khong phai trong DOM (spec UI §5.3). No
  // nam o MAN chu khong o hang, nen ao hoa thao hang ra thi ban nhap van con.
  const [banNhap, setBanNhap] = useState<{ i: number; text: string } | null>(null);

  if (transcript === null) {
    // TRẠNG THÁI RỖNG = KHUNG §4.2 Ở VÙNG GIỮA (spec UI §4.2: *"Vùng giữa là khung kẻ nét
    // đứt… Không phải một thẻ nhỏ giữa màn hình"*).
    //
    // ⚠️ `.ed` khai `grid-template-rows: 1fr` và nhánh này vẫn có **ĐÚNG MỘT** con
    // (`.ed__rong-boc`) — thêm một con thứ hai vào một lưới có số track cố định là một thay đổi
    // BỐ CỤC (ERRATA #31 mục 1 / #36 mục 3), và chỗ đó không có bài ghim nào. Câu "chưa có bản
    // ghi để biên tập" Ở LẠI (nó là sự thật của trạng thái này), nhưng nó không còn là thứ duy
    // nhất trong vùng giữa.
    return (
      <div className="ed">
        <div className="ed__rong-boc">
          {/* SU THAT, khong phai loi hua: duong NAP CO THAT (xem `IntakeFrame`). */}
          <p className="ed__rong">chưa có bản ghi để biên tập</p>
          <IntakeFrame napTep={onNapTep} />
        </div>
      </div>
    );
  }

  const soDoan = transcript.segments.length;
  const cuaSo = windowFor(cuon, viewportH, rowH, soDoan, overscan, editingSegment);
  const hang = transcript.segments.slice(cuaSo.start, cuaSo.end);

  return (
    <div className="ed">
      {/* ⚠️ CÂU "ĐÃ LỖI THỜI" LÀ **CON THỨ HAI** CỦA `.ed` — một lưới trước đây khai ĐÚNG MỘT
          track (`grid-template-rows: 1fr`). Thêm một con vào một lưới có số track cố định là
          một thay đổi BỐ CỤC (ERRATA #31 mục 1 / #36 mục 3): nay `.ed` khai HAI track và MỖI con
          khai `grid-row` tường minh trong `app.css`. Khi câu này vắng, track `auto` co lại bằng
          không và khung danh sách VẪN ở track `1fr` — điều đó chỉ đúng vì có `grid-row` tường minh.
          Nguồn của câu: `stale` TÍNH Ở MÁY CHỦ (`is_stale`), `App` chỉ đọc cờ đó. */}
      {cauLoiThoi === null ? null : (
        <p className="ed__loi-thoi" data-testid="loi-thoi" role="status">
          {cauLoiThoi}
        </p>
      )}
      <div
        className="ed__khung"
        onScroll={(suKien) => setCuon(suKien.currentTarget.scrollTop)}
      >
        {/* DEM DAU/CUOI: chieu cao cuon phai bang CA danh sach, khong phai bang cua so.
            Dem cuoi dung `cuaSo.end` DA KEP theo so doan (`M4`) ⇒ khong bao gio am. */}
        <div className="ed__dem-dau" style={{ height: cuaSo.start * rowH }} aria-hidden />
        <ul className="ed__danh-sach">
          {hang.map((seg) => {
            const dangSua = editingSegment === seg.i;
            const lyDo = lyDoNghiNgo(seg);
            const lop = ["ed__item"];
            if (seg.suspect) lop.push("is-suspect");
            if (seg.i === currentSegment) lop.push("is-current");
            if (dangSua) lop.push("is-editing");
            const chuHienTai = banNhap !== null && banNhap.i === seg.i ? banNhap.text : seg.text;
            return (
              <li key={seg.i} data-i={seg.i} className={lop.join(" ")}>
                <span className="ed__rail">{formatTimecode(seg.start)}</span>
                {dangSua ? (
                  // Ô SỬA + NÚT + DẤU NUDGE + CÂU TRẠNG THÁI nằm trong MỘT con (`.ed__sua-boc`)
                  // của hàng: `.ed__item` khai BA cột (`var(--rail) 1fr auto`) và hai con đầu là
                  // rail + ô sửa — thêm ba con nữa làm hàng thứ tư rơi vào CỘT ẩn (ERRATA #31
                  // mục 1). Một con bọc giữ nguyên số con của lưới.
                  //
                  // `<textarea>` chu KHONG `contentEditable` (plan Task 6 Step 4): kiem soat
                  // duoc focus, khong de HTML nguoi dung dan vao thanh DOM cua app.
                  <div className="ed__sua-boc">
                    <textarea
                      className="ed__sua"
                      data-testid="o-sua"
                      aria-label={`sửa đoạn ${seg.i}`}
                      rows={soDong(chuHienTai)}
                      value={chuHienTai}
                      onChange={(suKien) => setBanNhap({ i: seg.i, text: suKien.target.value })}
                      onKeyDown={(suKien) => {
                        // `Esc` HUY: xoá bản nháp và báo cho `App` `endEdit` — KHÔNG ghi gì.
                        if (suKien.key === "Escape") {
                          suKien.preventDefault();
                          setBanNhap(null);
                          onCancelEdit?.();
                          return;
                        }
                        // `Enter` luu; `Shift+Enter` de xuong dong trong cau dai.
                        if (suKien.key !== "Enter" || suKien.shiftKey) return;
                        suKien.preventDefault();
                        // ⚠️ KHÔNG xoá bản nháp ở đây: việc ghi là BẤT ĐỒNG BỘ, và xoá ngay thì
                        // một lượt ghi LỖI sẽ nuốt mất chữ người dùng vừa gõ. Bản nháp được giữ
                        // tới khi `App` đóng ô sửa (thành công) hoặc người dùng tự huỷ.
                        onCommitEdit?.(seg.i, chuHienTai);
                      }}
                    />
                    {/* HAI MỐC của dòng đang sửa — nudge mà không NHÌN THẤY kết quả là một phép
                        đo mù. `formatTimecode` KẸP giây âm về 0, và nudge KHÔNG tự kẹp lần hai. */}
                    <p className="ed__moc" data-testid="moc-doan">
                      {`${formatTimecode(seg.start)} → ${formatTimecode(seg.end)}`}
                    </p>
                    <div className="ed__sua-thanh">
                      {/* DẤU NUDGE: `[` = mốc BẮT ĐẦU −0,1s; `]` = mốc KẾT THÚC +0,1s (BẢNG PHÍM CỦA
                          BRIEF D1 — spec UI §5.1 gán `[`/`]` cho "đặt mốc tại đầu đọc", xem ERRATA
                          #44 mục 3; đổi khoá là việc của Task 11). Hai nút này là lối CHUỘT của
                          cùng hai phím `[`/`]` — và cả hai đều đi qua CÙNG một hàng đợi ghi của `App`. */}
                      <button
                        type="button"
                        className="ed__nudge"
                        data-testid="nudge-start"
                        title="đẩy mốc bắt đầu lùi 0,1 giây"
                        disabled={dangLuu}
                        onClick={() => onNudge?.("start")}
                      >
                        [ −0,1s
                      </button>
                      <button
                        type="button"
                        className="ed__nudge"
                        data-testid="nudge-end"
                        title="đẩy mốc kết thúc tới 0,1 giây"
                        disabled={dangLuu}
                        onClick={() => onNudge?.("end")}
                      >
                        ] +0,1s
                      </button>
                      <button
                        type="button"
                        className="ed__nut ed__nut--luu"
                        data-testid="luu-doan"
                        disabled={dangLuu}
                        onClick={() => onCommitEdit?.(seg.i, chuHienTai)}
                      >
                        lưu
                      </button>
                      <button
                        type="button"
                        className="ed__nut ed__nut--huy"
                        data-testid="huy-doan"
                        onClick={() => {
                          setBanNhap(null);
                          onCancelEdit?.();
                        }}
                      >
                        huỷ
                      </button>
                    </div>
                    {/* TRẠNG THÁI GHI nói ra bằng CHỮ (§7: thông tin không được chỉ nằm ở màu).
                        Lỗi là `ApiError.message` NGUYÊN VĂN (`"<status>: <detail>"` — câu tiếng
                        Việt của backend), không phải một câu chung. */}
                    {dangLuu ? (
                      <p className="ed__ghi" data-testid="dang-luu">
                        đang lưu…
                      </p>
                    ) : null}
                    {loiGhi === null ? null : (
                      <p className="ed__ghi ed__ghi--loi" data-testid="loi-ghi">
                        {loiGhi}
                      </p>
                    )}
                  </div>
                ) : (
                  <button
                    type="button"
                    className="ed__chu"
                    onClick={() => {
                      // Mở ô sửa ⇒ BỎ bản nháp cũ (nếu có): mỗi lượt sửa bắt đầu từ chữ CỦA MÁY CHỦ.
                      setBanNhap(null);
                      onStartEdit?.(seg.i);
                    }}
                  >
                    {seg.text}
                  </button>
                )}
                {/* LY DO bang CHU, khong phai tooltip va khong phai mau (§7). */}
                {lyDo === null ? null : <span className="ed__ly-do">{lyDo}</span>}
              </li>
            );
          })}
        </ul>
        <div className="ed__dem-cuoi" style={{ height: (soDoan - cuaSo.end) * rowH }} aria-hidden />
      </div>
    </div>
  );
}
