/**
 * MỘT DÒNG phụ đề — ba GÓC NHÌN, cùng một dòng.
 *
 * 🔴 NGUỒN GỐC: `_lovable-code/src/components/studio/SegmentRow.tsx` (206 dòng).
 *
 * 📏 SỐ ĐO trên bản đã duyệt (`getBoundingClientRect` trong Chrome, 1680×1050):
 *      dòng        : 1366×68, `display:grid`, cột **88px 1152,73px 61,27px**, gap-x 16px,
 *                    pad 10px 16px, `border-b 1px --rule`
 *      dòng ĐANG CHỌN: nền `bg-signal-soft` + một vạch 3px màu `--signal` ở mép trái
 *      cột trái    : hai mốc thời gian, mono 10,5px, line-height 16px
 *      cột phải    : `CPS 12,9` + nút `duyệt`, xếp dọc, canh phải
 *      chữ chính   : 15px / line-height 24px / `--ink-0` — đây là cỡ ĐỌC, không phải cỡ UI
 *
 * ## Ba góc nhìn là BA CÁCH HIỂN THỊ CÙNG MỘT DÒNG
 *
 * Bản gốc dùng `view: "edit" | "compare" | "dub"`. Repo giữ đúng mô hình đó
 * (`GocNhin` trong `lib/studio.ts`), nhưng nội dung từng góc phải đổi cho khớp dữ liệu thật:
 *
 *  - **Biên tập**: ô sửa chữ + dòng `gốc:` (bản phiên âm). Bản gốc cho sửa TRỰC TIẾP trong
 *    ô nhập và gọi `onText` mỗi phím. Ở đây giữ nguyên hình thức đó, nhưng quyền ghi vẫn
 *    thuộc `App` (`onSuaChu`) — dòng này KHÔNG tự lưu, và khi `dangLuu` thì ô bị khoá.
 *  - **Đối chiếu**: hai cột chữ. Bản gốc có HAI bản dịch cùng lúc (`opus`/`qwen`). Repo chỉ
 *    có MỘT bản dịch mỗi lần (`TranslationDetail`), nên hai cột là **bản gốc ↔ bản dịch** —
 *    đó mới là phép đối chiếu có nghĩa với dữ liệu thật. Từ khác nhau được tô.
 *  - **Lồng tiếng**: chữ bản dịch + thanh tỉ lệ nén + hai nút nghe thử / lồng lại.
 *
 * ## Vì sao KHÔNG có `withGlossary` như bản gốc
 *
 * Bản gốc gạch chân thuật ngữ bằng một mảng `GLOSSARY` viết cứng trong `lib/studio.ts`
 * (`phòng thu → studio`, ...). Repo có bảng thuật ngữ THẬT ở `/api/terms`. Gạch chân bằng
 * mảng cứng là dựng nguồn sự thật thứ hai cho cùng khái niệm "thuật ngữ", và nó sẽ gạch
 * những từ không có trong bảng của người dùng. Ở đây thuật ngữ đến qua prop `thuatNgu`
 * (do `App` đọc); rỗng thì không gạch gì.
 */
import { forwardRef } from "react";

import type { Segment } from "../../api/types.ts";
import {
  NHAN_LOAI_VIEC,
  soVi,
  tachTuKhac,
  tiLeNen,
  viecCuaDoan,
  type GocNhin,
  type Viec,
} from "../../lib/studio.ts";
import { formatTimecode } from "../../lib/timecode.ts";

/** Một thuật ngữ trong bảng của người dùng — chỉ cần hai trường để gạch chân. */
export interface ThuatNgu {
  term: string;
  meaning: string;
}

export interface SegmentRowProps {
  seg: Segment;
  /** Đang là đoạn ĐƯỢC CHỌN (nền amber nhạt + vạch trái). */
  current: boolean;
  /** Góc nhìn đang bật. */
  goc: GocNhin;
  /** Chữ bản dịch của đoạn này — `null` khi chưa có bản dịch. */
  banDich: string | null;
  /** Đoạn đã được người dùng duyệt chưa (tập duyệt thuộc `App`). */
  daDuyet: boolean;
  /** Take đã tạo, giây — `null` = chưa lồng tiếng đoạn này. */
  take: number | null;
  /** Mọi việc của đoạn này (đã lọc theo bộ lọc đang bật ở cột trái). */
  viec: readonly Viec[];
  /** Bảng thuật ngữ của người dùng; rỗng thì không gạch chân gì. */
  thuatNgu: readonly ThuatNgu[];
  /** Đang ghi dòng này — ô sửa bị khoá, có câu `đang lưu…`. */
  dangLuu: boolean;
  /** Lỗi ghi của dòng này, nguyên văn `ApiError.message`. */
  loiGhi: string | null;
  onSelect: () => void;
  /** Người dùng sửa chữ. Dòng KHÔNG tự lưu — `App` quyết lúc nào ghi. */
  onSuaChu: (chu: string) => void;
  onDuyet: () => void;
  /** Nghe thử: phát đúng đoạn này. */
  onNgheThu: () => void;
  /** Lồng lại câu này. */
  onLongLai: () => void;
}

/** `m:ss.xx` — mốc thời gian của dòng, mono. Dùng chung `formatTimecode` của repo. */
const moc = (t: number): string => formatTimecode(t);

/**
 * Gạch chân thuật ngữ trong một chuỗi, dùng BẢNG CỦA NGƯỜI DÙNG.
 *
 * ⚠️ So KHÔNG phân biệt hoa thường và bắt theo ranh giới từ: so chuỗi con trần sẽ gạch
 * "thu" bên trong "thuật" và làm rối cả câu. `\b` của JS không hiểu chữ có dấu, nên phải
 * tự kiểm hai đầu bằng lớp ký tự "không phải chữ cái".
 */
function gachThuatNgu(chu: string, bang: readonly ThuatNgu[]): React.ReactNode[] {
  if (bang.length === 0 || chu === "") return [chu];
  const thap = chu.toLowerCase();
  type Hit = { dau: number; cuoi: number; term: string; meaning: string };
  const hit: Hit[] = [];
  for (const t of bang) {
    const tim = t.term.trim().toLowerCase();
    if (tim === "") continue;
    let tu = 0;
    for (;;) {
      const i = thap.indexOf(tim, tu);
      if (i < 0) break;
      const truoc = i === 0 ? "" : thap[i - 1];
      const sau = i + tim.length >= thap.length ? "" : thap[i + tim.length];
      const ranhGioi = !/[\p{L}\p{N}]/u.test(truoc) && !/[\p{L}\p{N}]/u.test(sau);
      // Không chồng lên một chỗ đã gạch — hai thuật ngữ lồng nhau thì cái ĐẦU TIÊN thắng.
      const chong = hit.some((h) => i < h.cuoi && i + tim.length > h.dau);
      if (ranhGioi && !chong) hit.push({ dau: i, cuoi: i + tim.length, term: t.term, meaning: t.meaning });
      tu = i + tim.length;
    }
  }
  if (hit.length === 0) return [chu];
  hit.sort((a, b) => a.dau - b.dau);
  const ra: React.ReactNode[] = [];
  let viTri = 0;
  let khoa = 0;
  for (const h of hit) {
    if (h.dau > viTri) ra.push(chu.slice(viTri, h.dau));
    ra.push(
      <span key={`tn-${khoa++}`} className="dong__thuat-ngu" title={`Thuật ngữ: ${h.term} → ${h.meaning}`}>
        {chu.slice(h.dau, h.cuoi)}
      </span>,
    );
    viTri = h.cuoi;
  }
  if (viTri < chu.length) ra.push(chu.slice(viTri));
  return ra;
}

/** Dấu ✓ vẽ nội tuyến — không thêm thư viện icon cho một dấu tích. */
function Tick() {
  return (
    <svg viewBox="0 0 12 12" width="10" height="10" aria-hidden="true" focusable="false">
      <path d="M2 6.3 L4.6 9 L10 3.2" fill="none" stroke="currentColor" strokeWidth="1.7"
        strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}

/** Biểu tượng "phát" — tam giác đặc. */
function TamGiac() {
  return (
    <svg viewBox="0 0 12 12" width="11" height="11" aria-hidden="true" focusable="false">
      <path d="M3 2 L10 6 L3 10 Z" fill="currentColor" />
    </svg>
  );
}

/** Biểu tượng "lồng lại" — mũi tên vòng. */
function VongLai() {
  return (
    <svg viewBox="0 0 12 12" width="11" height="11" aria-hidden="true" focusable="false">
      <path d="M9.5 4.2 A4 4 0 1 0 10 7.6" fill="none" stroke="currentColor" strokeWidth="1.4"
        strokeLinecap="round" />
      <path d="M10.3 1.6 L10.2 4.6 L7.3 4.3" fill="none" stroke="currentColor" strokeWidth="1.4"
        strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}

export const SegmentRow = forwardRef<HTMLLIElement, SegmentRowProps>(function SegmentRow(
  {
    seg,
    current,
    goc,
    banDich,
    daDuyet,
    take,
    viec,
    thuatNgu,
    dangLuu,
    loiGhi,
    onSelect,
    onSuaChu,
    onDuyet,
    onNgheThu,
    onLongLai,
  },
  ref,
) {
  const dsViec = viecCuaDoan(viec, seg.i);
  const coNghiNgo = dsViec.some((v) => v.loai === "nghi-ngo");
  const tiLe = tiLeNen(take, seg);

  const lop = ["dong"];
  if (current) lop.push("is-chon");
  if (daDuyet) lop.push("is-da-duyet");
  if (coNghiNgo) lop.push("is-nghi-ngo");

  /** Nhãn CPS chỉ hiện khi MÁY CHỦ đã nói đoạn này vượt ngưỡng (cờ `over`). */
  const nhanCps = dsViec.find((v) => v.loai === "cps");
  const nhanNen = dsViec.find((v) => v.loai === "nen");

  return (
    <li ref={ref} className={lop.join(" ")} data-i={seg.i} onClick={onSelect}>
      {/* VẠCH TRÁI 3px: chỉ có khi đoạn đang chọn. Đây là tín hiệu THỨ HAI — nền
          `bg-signal-soft` là tín hiệu thứ nhất, và `aria-current` là tín hiệu máy đọc. */}
      {current ? <span className="dong__vach" aria-hidden="true" /> : null}

      {/* CỘT 1 — HAI MỐC, xếp dọc. */}
      <div className="dong__moc" aria-hidden="true">
        <div>{moc(seg.start)}</div>
        <div>{moc(seg.end)}</div>
      </div>

      {/* CỘT 2 — NỘI DUNG THEO GÓC NHÌN. */}
      <div className="dong__giua">
        {goc === "bien-tap" ? (
          <>
            <input
              className="dong__sua"
              value={banDich ?? seg.text}
              aria-label={`Phụ đề đoạn ${seg.i}`}
              disabled={dangLuu}
              onFocus={onSelect}
              onChange={(e) => onSuaChu(e.target.value)}
              onClick={(e) => e.stopPropagation()}
            />
            <p className="dong__goc">
              <span className="dong__goc-nhan">gốc:</span> {gachThuatNgu(seg.text, thuatNgu)}
            </p>
          </>
        ) : null}

        {goc === "doi-chieu" ? (
          <div className="dong__doi">
            <div className="dong__cot">
              <span className="nhan-khac">bản gốc</span>
              <p className="dong__chu-nguon">{seg.text}</p>
            </div>
            <div className="dong__cot">
              <span className="nhan-khac">bản dịch</span>
              <p className="dong__chu-dich">
                {banDich === null
                  ? <span className="dong__chua">chưa có bản dịch</span>
                  : tachTuKhac(seg.text, banDich).map((p, k) =>
                      p.khac ? <mark key={k}>{p.chu}</mark> : <span key={k}>{p.chu}</span>,
                    )}
              </p>
            </div>
          </div>
        ) : null}

        {goc === "long-tieng" ? (
          <div className="dong__long">
            <p className="dong__chu-doc">{banDich ?? seg.text}</p>
            <div className="dong__take" title="Take so với khung thời gian">
              <div
                className={
                  tiLe === null ? "dong__take-ruot" : tiLe > 1.5 ? "dong__take-ruot is-nen-manh" : tiLe > 1 ? "dong__take-ruot is-nen" : "dong__take-ruot is-vua"
                }
                style={{ width: tiLe === null ? "0%" : `${Math.min(100, (tiLe / 2) * 100)}%` }}
              />
            </div>
            <span className={tiLe !== null && tiLe > 1.5 ? "dong__ti-le is-canh-bao" : "dong__ti-le"}>
              {tiLe === null ? "—" : `${soVi(tiLe, 2)}×`}
            </span>
            <button
              type="button"
              className="dong__nut"
              aria-label="Nghe thử"
              title="Nghe thử đoạn này"
              onClick={(e) => {
                e.stopPropagation();
                onNgheThu();
              }}
            >
              <TamGiac />
            </button>
            <button
              type="button"
              className="dong__nut"
              aria-label="Lồng lại"
              title="Lồng lại câu này"
              onClick={(e) => {
                e.stopPropagation();
                onLongLai();
              }}
            >
              <VongLai />
            </button>
          </div>
        ) : null}

        {/* NHÃN VIỆC — chữ, không phải chỉ màu (§7). */}
        {dsViec.length > 0 ? (
          <div className="dong__viec">
            {dsViec.map((v) => (
              <span key={`${v.loai}`} className="nhan-khac nhan-khac--loi">
                {v.nhan}
              </span>
            ))}
          </div>
        ) : null}

        {dangLuu ? <p className="dong__tin">đang lưu…</p> : null}
        {loiGhi === null ? null : <p className="dong__tin dong__tin--loi">{loiGhi}</p>}
      </div>

      {/* CỘT 3 — CPS + NÚT DUYỆT, canh phải. */}
      <div className="dong__phai">
        <span
          className={nhanCps === undefined ? "dong__cps" : "dong__cps is-canh-bao"}
          title={nhanCps === undefined ? "Ký tự mỗi giây (máy chủ đo)" : "Vượt ngưỡng ký tự/giây của máy chủ"}
        >
          {nhanCps === undefined ? "—" : nhanCps.nhan.toLowerCase()}
        </span>
        <button
          type="button"
          className={daDuyet ? "dong__duyet is-roi" : "dong__duyet"}
          aria-pressed={daDuyet}
          onClick={(e) => {
            e.stopPropagation();
            onDuyet();
          }}
        >
          {daDuyet ? <Tick /> : null}
          {daDuyet ? "đã duyệt" : "duyệt"}
        </button>
        {nhanNen === undefined ? null : (
          <span className="nhan-khac nhan-khac--loi">{NHAN_LOAI_VIEC.nen}</span>
        )}
      </div>
    </li>
  );
});
