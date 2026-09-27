/**
 * §4.3 Màn ĐỐI CHIẾU — hai cột (nguồn / bản dịch) + CỘT CPS, segmented control chọn
 * bản dịch, GHIM bản B, và đánh dấu dòng VƯỢT NGƯỠNG ĐỌC (spec UI §4.3, §12.4).
 *
 * BA quyết định của tệp này, cả ba đều là hệ quả của một phép đo:
 *
 * 1. **KHÔNG tính CPS ở client.** `TranslationDetail.cps` đến từ
 *    `GET /api/translations/{id}`, nơi con số được sinh bởi CÙNG hàm `mt_qa.cps_row`
 *    đã sinh chuỗi `cps:` trong `qa_issues` (xem `domain/mt_qa.py`). Tính lại ở đây là
 *    dựng nguồn sự thật thứ hai cho đúng đại lượng mà spec frontend §2 cấm — và
 *    `over` phải đọc từ backend vì nó so trên giá trị CHƯA làm tròn.
 * 2. **KHÔNG hiển thị `Infinity`/`NaN`.** Backend trả `cps: null` khi không đo được
 *    (cả hai cửa sổ đều không dương, `mt_qa` gọi là `nowindow`). Hiện `0` ở đó là bịa
 *    một tốc độ; hiện `—` là sự thật.
 * 3. **Màn KHÔNG tự `fetch`.** Dữ liệu vào qua PROP — cùng khuôn với `EditScreen`
 *    (Task 6) và `Transport` (Task 7): một chỗ gọi API cho mỗi màn là hai nguồn sự
 *    thật. Người gọi là đường CHỌN KÊNH, hiện CHƯA có (ERRATA #18 mục 4).
 *
 * ⚠️ TRẦN CỦA LƯỢT NÀY (`ponytail:`): trong app, `App` truyền `transcript={null}` và
 * `translations={[]}` vì chưa có đường CHỌN KÊNH, nên màn chỉ render TRẠNG THÁI RỖNG
 * NÓI THẬT. Mọi khẳng định về hai cột đến từ test truyền prop.
 *
 * `ponytail:` GHIM là state CỤC BỘ của màn này. `UiState.pinnedB` + action `pinB` đã có
 * sẵn trong `state/reducer.ts` nhưng **thiếu action BỎ GHIM**, nên nối vào reducer là
 * việc của task CHỌN KÊNH (nó phải sở hữu cả `channelId` lẫn bản dịch đang chọn).
 * ĐƯỜNG NÂNG CẤP: truyền `pinnedB`/`onPinB` xuống và thêm một action bỏ ghim.
 */
import { useState } from "react";

import type { TranslationDetail, Transcript } from "../api/types.ts";

interface Props {
  /** Bản ghi đang mở; `null` = chưa chọn kênh (trạng thái THẬT của app hôm nay). */
  transcript: Transcript | null;
  /** Bản dịch của bản ghi đó, ĐÃ kèm `segments` + `cps` (`TranslationDetail`). */
  translations: TranslationDetail[];
}

/** Cột nào đang được chọn làm bản A (bản dịch hiện ở cột phải). */
export function CompareScreen({ transcript, translations }: Props) {
  const [chonId, datChonId] = useState<number | null>(translations[0]?.id ?? null);
  const [ghim, datGhim] = useState(false);

  if (transcript === null) {
    // Trạng thái rỗng NÓI THẬT: không bịa một bản ghi nào để màn trông đầy đủ.
    return (
      <section className="cmp">
        <p className="cmp__rong" data-testid="rong">
          Chưa chọn kênh. Vùng KÊNH chưa có đường chọn bản ghi, nên chưa có gì để đối chiếu.
        </p>
      </section>
    );
  }

  // Bản A: id đang chọn, nhưng PHẢI kiểm nó còn trong danh sách — prop đổi thì id cũ
  // có thể trỏ vào hư không, và một `find` trả `undefined` là chỗ dễ vẽ ra màn trống.
  const chon = translations.find((tr) => tr.id === chonId) ?? translations[0] ?? null;
  // Bản B: bản KHÁC bản A. Ghim chính bản đang chọn là so một hàng với chính nó
  // (`reducer.pinB` từ chối đúng ca đó) — ở đây đơn giản là không có gì để ghim.
  const ghimBan = ghim ? translations.find((tr) => tr.id !== chon?.id) ?? null : null;

  const dichTheoI = new Map((chon?.segments ?? []).map((s) => [s.i, s]));
  const cpsTheoI = new Map((chon?.cps.rows ?? []).map((r) => [r.i, r]));
  const ghimTheoI = new Map((ghimBan?.segments ?? []).map((s) => [s.i, s]));

  return (
    <section className="cmp">
      {/* Segmented control (U7: KHÔNG phải N tab) + nút ghim. */}
      <div className="cmp__thanh" role="radiogroup" aria-label="Bản dịch">
        {translations.map((tr, k) => (
          <button
            key={tr.id}
            type="button"
            role="radio"
            aria-checked={tr.id === chon?.id}
            className="cmp__chon"
            data-testid={`pick-${tr.id}`}
            data-stale={String(tr.stale)}
            onClick={() => datChonId(tr.id)}
          >
            bản dịch {k + 1} · {tr.engine}
            {tr.stale ? " · lỗi thời" : ""}
          </button>
        ))}
        <button
          type="button"
          className="cmp__ghim"
          data-testid="ghim"
          aria-pressed={ghimBan !== null}
          // Một bản dịch thì không có "bản B" nào để ghim: nút VÔ HIỆU thay vì im lặng
          // làm một việc không có kết quả.
          disabled={translations.length < 2}
          onClick={() => datGhim((cu) => !cu)}
        >
          Ghim bản B
        </button>
      </div>

      {chon === null ? (
        <p className="cmp__rong" data-testid="chua-dich">
          Bản ghi này chưa có bản dịch nào. Cột NGUỒN bên dưới là dữ liệu thật.
        </p>
      ) : (
        <p className="cmp__nguong" data-testid="nguong">
          ngưỡng {chon.cps.max_cps} CPS · nguồn: {chon.cps.rows.length} đoạn đã đo
        </p>
      )}

      <div className={"cmp__dau" + (ghimBan !== null ? " is-pinned" : "")}>
        <span className="cmp__nhan">Nguồn</span>
        <span className="cmp__nhan">Bản dịch</span>
        <span className="cmp__nhan">CPS</span>
        {ghimBan !== null ? <span className="cmp__nhan">Bản B</span> : null}
      </div>

      <ol className={"cmp__danh-sach" + (ghimBan !== null ? " is-pinned" : "")}>
        {transcript.segments.map((seg) => {
          const cps = cpsTheoI.get(seg.i);
          const over = cps?.over === true;
          return (
            <li
              key={seg.i}
              className={"cmp__dong" + (over ? " is-over" : "")}
              data-testid={`row-${seg.i}`}
              data-over-cps={String(over)}
            >
              <span className="cmp__goc" data-testid="col-left">{seg.text}</span>
              {/* Không có đoạn dịch tương ứng thì để TRỐNG: một chữ bịa ở đây là nói
                  rằng bản dịch có nội dung mà nó không có. */}
              <span className="cmp__dich" data-testid="col-right">
                {dichTheoI.get(seg.i)?.text ?? ""}
              </span>
              <span className="cmp__cps" data-testid="col-cps">
                {cps === undefined || cps.cps === null ? "—" : cps.cps.toFixed(1)}
                <span className="cmp__don-vi">CPS</span>
              </span>
              {ghimBan !== null ? (
                <span className="cmp__ghim-cot" data-testid="col-pinned">
                  {ghimTheoI.get(seg.i)?.text ?? ""}
                </span>
              ) : null}
            </li>
          );
        })}
      </ol>
    </section>
  );
}
