/**
 * VÙNG KÊNH — danh sách nguồn đã nạp + lối nạp tệp MỚI.
 *
 * 🔴 TỆP NÀY TỒN TẠI VÌ MỘT LỖ HỔNG ĐO ĐƯỢC (2026-10-30). Khi bốn màn cũ và `app.css` bị
 * xoá, `ChannelZone` cũ cũng bị xoá theo — nhưng đó là nơi DUY NHẤT có `input type="file"`.
 * Phép đo trên bản build mới: `document.querySelectorAll('button').length = 17`, và
 * `querySelectorAll('[class*=kenh], [class*=ch__]').length = 0` ⇒ **không có nút chọn kênh
 * nào**, nên `App` không bao giờ có `channelId`, nên `transcript` là `null`, nên bàn làm
 * việc trống vĩnh viễn. App đã trông đúng nhưng KHÔNG DÙNG ĐƯỢC — đúng lớp lỗi tệ nhất.
 *
 * ## Vì sao vùng này nằm trong cột TRÁI, trên hộp việc
 *
 * Bản đã duyệt dành 260px cột trái cho hộp việc. Kênh phải ở CÙNG cột đó chứ không phải cột
 * thứ tư: thêm một cột là đổi hình học đã đo (260 / 1fr / 44) và làm hẹp bàn làm việc.
 * Kênh ở trên, việc ở dưới — chọn tệp trước, rồi mới có việc để xử lý.
 *
 * ## Cái KHÔNG làm
 *
 *  - **Không tự `fetch`**: `sources` là prop (cùng luật với mọi màn — `App` là nơi duy nhất
 *    đọc API).
 *  - **Không tự chèn hàng sau khi nạp**: hàng kênh mới chỉ đến từ `sources.reload()` của
 *    `App`. Một bản sao dữ liệu máy chủ ở client là nguồn sự thật thứ hai.
 *  - **Không tự chọn kênh**: `onChon` báo lên, `App` dispatch.
 */

import { useRef, useState } from "react";

import type { Source, SourceLang } from "../../api/types.ts";
import { formatTimecode } from "../../lib/timecode.ts";

/** Một kết quả nạp — cùng hình dạng `KetQuaNap` của `App`. */
export interface KetQuaNap {
  ten: string;
  ok: boolean;
  sourceId?: number;
  loi?: string;
}

export interface ChannelZoneProps {
  sources: readonly Source[];
  /** Kênh đang mở; `null` = chưa chọn. */
  selectedId: number | null;
  loading: boolean;
  /** Câu lỗi của lần đọc danh sách, nguyên văn. */
  error: string | null;
  onSelect: (id: number) => void;
  /** Nạp tệp — ĐI QUA `App` (nó giữ `sources` và việc đọc lại). */
  onNapTep: (files: File[], lang: SourceLang) => Promise<KetQuaNap[]>;
  /** Xoá một kênh. Ném khi máy chủ từ chối — câu của nó hiện nguyên văn. */
  onXoa: (id: number) => Promise<void>;
}

/** Ngôn ngữ nguồn — hai lựa chọn của backend (`SourceLang`). */
const NGON_NGU: ReadonlyArray<{ id: SourceLang; nhan: string }> = [
  { id: "zh", nhan: "Trung" },
  { id: "en", nhan: "Anh" },
];

export function ChannelZone({
  sources,
  selectedId,
  loading,
  error,
  onSelect,
  onNapTep,
  onXoa,
}: ChannelZoneProps) {
  const oTepRef = useRef<HTMLInputElement | null>(null);
  const [ngonNgu, datNgonNgu] = useState<SourceLang>("zh");
  const [dangNap, datDangNap] = useState(false);
  const [ketQua, datKetQua] = useState<KetQuaNap[] | null>(null);
  /** Kênh đang có MỘT lệnh xoá BAY — khoá nút của chính nó. */
  const [dangXoa, datDangXoa] = useState<number | null>(null);
  const [loiXoa, datLoiXoa] = useState<string | null>(null);

  const nap = async (danhSach: File[]) => {
    if (danhSach.length === 0) return;
    datDangNap(true);
    datKetQua(null);
    try {
      const kq = await onNapTep(danhSach, ngonNgu);
      datKetQua(kq);
    } finally {
      datDangNap(false);
      // Xoá `value` của ô tệp: không xoá thì chọn CÙNG một tệp lần hai không bắn `change`
      // (trình duyệt coi là không đổi), và người dùng thấy nút im lặng.
      if (oTepRef.current !== null) oTepRef.current.value = "";
    }
  };

  const xoa = async (id: number) => {
    datDangXoa(id);
    datLoiXoa(null);
    try {
      await onXoa(id);
    } catch (loi: unknown) {
      datLoiXoa(loi instanceof Error ? loi.message : String(loi));
    } finally {
      datDangXoa(null);
    }
  };

  return (
    <section className="kenh" aria-label="Kênh">
      <div className="kenh__dau">
        <span className="nhan-khac">Kênh</span>
        <span className="num kenh__dem">{sources.length}</span>
      </div>

      {/* LỐI NẠP — đường vào DUY NHẤT của app. `input` là phần tử THẬT (Tab tới được,
          `change` bắn), nút chỉ bấm hộ nó. */}
      <div className="kenh__nap">
        <div className="kenh__ngon-ngu" role="radiogroup" aria-label="Ngôn ngữ nguồn">
          {NGON_NGU.map((n) => (
            <label key={n.id} className="kenh__ngon-ngu-o">
              <input
                type="radio"
                name="ngon-ngu-nguon"
                value={n.id}
                checked={ngonNgu === n.id}
                onChange={() => datNgonNgu(n.id)}
              />
              <span>{n.nhan}</span>
            </label>
          ))}
        </div>
        <input
          ref={oTepRef}
          className="kenh__o-tep"
          type="file"
          accept="audio/*,video/*"
          multiple
          onChange={(e) => {
            void nap([...(e.target.files ?? [])]);
          }}
        />
        <button
          type="button"
          className="kenh__nap-nut"
          disabled={dangNap}
          onClick={() => oTepRef.current?.click()}
        >
          {dangNap ? "đang nạp…" : "Nạp tệp"}
        </button>
      </div>

      {/* KẾT QUẢ NẠP — từng tệp một dòng, đúng §12.2 ("nạp 3 tệp cùng lúc" phải thấy rõ
          TỪNG tệp). `loi` là câu tiếng Việt của backend, NGUYÊN VĂN. */}
      {ketQua === null ? null : (
        <ul className="kenh__ket-qua">
          {ketQua.map((k) => (
            <li key={k.ten} className={k.ok ? "kenh__kq" : "kenh__kq is-loi"}>
              <span className="kenh__kq-ten">{k.ten}</span>
              <span className="kenh__kq-tt">{k.ok ? "xong" : k.loi ?? "lỗi"}</span>
            </li>
          ))}
        </ul>
      )}

      {error === null ? null : <p className="kenh__loi">{error}</p>}
      {loiXoa === null ? null : <p className="kenh__loi">{loiXoa}</p>}

      {/* DANH SÁCH KÊNH */}
      <ul className="kenh__ds">
        {loading && sources.length === 0 ? (
          <li className="kenh__trong">đang đọc danh sách…</li>
        ) : null}
        {!loading && sources.length === 0 ? (
          <li className="kenh__trong">chưa có kênh nào — nạp một tệp ở trên</li>
        ) : null}
        {sources.map((s) => (
          <li key={s.id} className={s.id === selectedId ? "kenh__dong is-chon" : "kenh__dong"}>
            <button
              type="button"
              className="kenh__chon"
              onClick={() => onSelect(s.id)}
              aria-current={s.id === selectedId}
            >
              <span className="kenh__ten">{s.origin}</span>
              <span className="num kenh__meta">
                {s.duration === null ? "—" : formatTimecode(s.duration)}
                {s.lang === null ? "" : ` · ${s.lang}`}
              </span>
            </button>
            <button
              type="button"
              className="kenh__xoa"
              aria-label={`Xoá kênh ${s.id}`}
              title="Xoá kênh"
              disabled={dangXoa === s.id}
              onClick={() => {
                void xoa(s.id);
              }}
            >
              {dangXoa === s.id ? "…" : "×"}
            </button>
          </li>
        ))}
      </ul>
    </section>
  );
}
