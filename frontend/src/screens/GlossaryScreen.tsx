/**
 * §4.4 Tab THUẬT NGỮ — bảng thuật ngữ + form, và số bản ghi bị ảnh hưởng hiện ra
 * TRƯỚC khi bấm lưu (spec UI §4.4 và tiêu chí §12.3).
 *
 * SÁU quyết định của tệp này, cả sáu đều có lý do ĐO ĐƯỢC:
 *
 * 1. **Màn này TỰ GỌI API** (không nhận dữ liệu qua prop). Đó là điểm khác biệt có
 *    chủ ý với `EditScreen`/`CompareScreen`/`Transport`: ba màn kia nhận prop vì
 *    người gọi chúng là đường CHỌN KÊNH (chưa tồn tại), còn tab Thuật ngữ là một màn
 *    ĐỘC LẬP — nó không phụ thuộc kênh nào. Hệ quả cho test: `render(<GlossaryScreen/>)`
 *    không truyền gì, nên con số ảnh hưởng **PHẢI đến từ ROUTE THẬT**; một stub ở
 *    tầng `endpoints` sẽ xanh kể cả khi URL ghép sai (xem `GlossaryScreen.test.tsx`).
 * 2. **KHÔNG tính lại số ảnh hưởng ở client.** Con số đến từ
 *    `GET /api/glossary/affected` (`endpoints.affectedPreview`), route gọi LẠI chính
 *    `affected_segments` mà `POST`/`PATCH` dùng. Tính ở client là nguồn sự thật thứ
 *    hai cho đúng đại lượng mà Giai đoạn 2 đã phải vá hai lần (spec frontend §2).
 * 3. **ĐƠN VỊ của con số là BẢN GHI (transcript), không phải bản dịch.** Đo được:
 *    `routes_glossary._recompute_affected` trả id TRANSCRIPT, và `_enqueue_retranslate`
 *    mới là chỗ suy ra từng bản dịch. Nhãn ở đây nói đúng đơn vị đó. Spec §4.4 viết
 *    "bản dịch bị đánh dấu lỗi thời"; muốn con số BẢN DỊCH thì ROUTE phải trả nó —
 *    client tự nhân/chia là tính lại thứ backend đã tính (đúng khuôn Task 8: *"nếu
 *    endpoint không đủ thì đó là lỗi của endpoint"*). Nợ đã khai ở báo cáo task.
 * 4. **`approved` là một phần của phép XEM TRƯỚC, không phải nhãn trang trí.** Bỏ
 *    duyệt một thuật ngữ ĐANG DUYỆT là GỠ một ràng buộc ⇒ bản dịch cũ sai ⇒ CÓ ảnh
 *    hưởng; còn một thuật ngữ CHƯA DUYỆT thì không ràng buộc gì. Vì vậy nhánh "chưa
 *    duyệt" nói bằng CHỮ người dùng đọc được, không phải bằng một màu khác.
 *    (Đo được ở `routes_glossary.affected_preview` + `GlossaryScreen.test.tsx`: cùng
 *    `term` + cùng `translation`, chỉ `approved` khác nhau, cho hai câu trả lời khác nhau.)
 * 5. **KHÔNG gọi gì để "tăng version".** `POST /api/glossary` đã tự tăng
 *    `glossary_version` bên trong `upsert_term` (ruling T6 GĐ2). Muốn BIẾT version
 *    thì đọc `GET /api/glossary/version`; gọi thêm một lần bump là tăng hai lần mỗi
 *    lần sửa, và mọi bản dịch trông "lỗi thời" sớm hơn thực tế. Test ghim đẳng thức
 *    "một lần Lưu ⇒ version +1" qua ROUTE THẬT.
 * 6. **Glyph `⚠` và `✕` là của SPEC, không phải emoji trang trí.** §4.4 nguyên văn:
 *    *"Thanh trên: … `⚠` đổi glossary → …"* và *"Hàng chưa có bản dịch có chip `✕ trống`
 *    màu lỗi."* ERRATA #19 mục 7 chốt: spec UI là nguồn có thẩm quyền về HÌNH THỨC,
 *    và luật "không emoji" của plan NHƯỜNG cho một glyph được spec chỉ định làm dấu
 *    hiệu NỘI DUNG. Không có glyph nào khác được thêm vào.
 *
 * ⚠️ TRẦN CỦA LƯỢT NÀY (`ponytail:`), ba lớp, cả ba đều là trạng thái THẬT:
 *   (a) **KHỐI DƯỚI của §4.4** (*"thuật ngữ đang chọn xuất hiện ở đâu — liệt kê mốc
 *       thời gian theo từng kênh"*) **CHƯA LÀM**: không route nào trả một thuật ngữ
 *       xuất hiện ở đoạn nào. `GET /api/transcripts` cố ý KHÔNG kèm `segments`
 *       (`TranscriptSummary`), nên dữ liệu đó không có nguồn HTTP. ĐƯỜNG NÂNG CẤP:
 *       một route `GET /api/glossary/{id}/occurrences` trả `(transcript_id, i)`.
 *   (b) **Sửa một hàng** chỉ đưa hàng đó vào form rồi `PATCH`; chưa có XOÁ thuật ngữ
 *       (backend cũng không có route xoá). ĐƯỜNG NÂNG CẤP: `DELETE /api/glossary/{id}`
 *       + nút xoá trong `.gl__anh-huong`.
 *   (c) **Chưa ai nhìn thấy màn này trong trình duyệt thật**: jsdom không có layout
 *       và không có CSS thật, nên "lề amber", "chip màu lỗi" chỉ được ghim ở tầng
 *       LUẬT CSS (một bài ĐỌC `app.css`), không phải ở tầng hình.
 */
import { useEffect, useState } from "react";

import { endpoints } from "../api/endpoints.ts";
import type { Term } from "../api/types.ts";

/** Chờ trước khi hỏi route xem trước — gõ liên tục thì chỉ hỏi MỘT lần. */
const CHO_GO_MS = 200;

/** Ngôn ngữ nguồn của glossary. `zh`/`en` là hai giá trị backend thật sự phục vụ. */
const NGUON = ["zh", "en"] as const;

const KHONG_CO_GI: Term[] = [];

export function GlossaryScreen() {
  const [terms, setTerms] = useState<Term[] | null>(null);
  const [loiNap, datLoiNap] = useState<string | null>(null);
  const [lanNap, setLanNap] = useState(0);

  // FORM — bốn trường của `TermIn` cộng `editingId` (`null` = thuật ngữ MỚI).
  const [lang, datLang] = useState<string>(NGUON[0]);
  const [term, datTerm] = useState("");
  const [translation, datTranslation] = useState("");
  const [note, datNote] = useState("");
  const [approved, datApproved] = useState(true);
  const [editingId, datEditingId] = useState<number | null>(null);

  // XEM TRƯỚC — con số của ROUTE, cộng trạng thái lỗi của chính lời gọi đó.
  const [affected, datAffected] = useState<number[] | null>(null);
  const [loiXemTruoc, datLoiXemTruoc] = useState<string | null>(null);

  const [dangLuu, datDangLuu] = useState(false);
  const [daLuu, datDaLuu] = useState<number | null>(null);
  const [loiLuu, datLoiLuu] = useState<string | null>(null);

  // NẠP BẢNG — một lượt đọc `GET /api/glossary`. `lanNap` tăng sau mỗi lần lưu để
  // bảng hiện đúng thứ vừa ghi, thay vì tự vá hàng trong bộ nhớ (hai đường ghi).
  useEffect(() => {
    let con = true;
    datLoiNap(null);
    endpoints.listTerms().then(
      (rows) => {
        if (con) setTerms(rows);
      },
      (error: unknown) => {
        if (!con) return;
        setTerms(KHONG_CO_GI);
        datLoiNap(error instanceof Error ? error.message : String(error));
      },
    );
    return () => {
      con = false;
    };
  }, [lanNap]);

  // XEM TRƯỚC — gọi ROUTE THẬT, có debounce. Bỏ lời gọi `affectedPreview` ở đây là
  // bỏ hẳn tính năng §12.3 (đó chính là mutation `G5` của brief).
  useEffect(() => {
    if (term.trim() === "") {
      datAffected(null);
      datLoiXemTruoc(null);
      return;
    }
    let con = true;
    const hen = setTimeout(() => {
      endpoints.affectedPreview({ lang, term, translation, approved }).then(
        (body) => {
          if (!con) return;
          datAffected(body.affected);
          datLoiXemTruoc(null);
        },
        (error: unknown) => {
          if (!con) return;
          datAffected(null);
          datLoiXemTruoc(error instanceof Error ? error.message : String(error));
        },
      );
    }, CHO_GO_MS);
    return () => {
      con = false;
      clearTimeout(hen);
    };
  }, [lang, term, translation, approved]);

  function moHang(t: Term): void {
    datEditingId(t.id);
    datLang(t.lang);
    datTerm(t.term);
    datTranslation(t.translation);
    datNote(t.note ?? "");
    datApproved(t.approved);
    datDaLuu(null);
    datLoiLuu(null);
  }

  function luu(): void {
    datDangLuu(true);
    datLoiLuu(null);
    datDaLuu(null);
    // KHÔNG gọi gì để tăng version: `upsert_term` đã tăng nó trong cùng giao dịch.
    const viec = editingId === null
      ? endpoints.createTerm({ lang, term, translation, note, approved })
      : endpoints.patchTerm(editingId, { translation, note, approved });
    viec.then(
      (body) => {
        datDangLuu(false);
        datDaLuu(body.affected.length);
        datAffected(body.affected);
        datEditingId(body.id);
        setLanNap((n) => n + 1);
      },
      (error: unknown) => {
        datDangLuu(false);
        datLoiLuu(error instanceof Error ? error.message : String(error));
      },
    );
  }

  const soDuyet = (terms ?? []).filter((t) => t.approved).length;

  /**
   * Hàng đang sửa (nếu có) — cần nó để phân biệt HAI ca rất khác nhau của `approved=false`:
   *
   *   - **nháp**: thuật ngữ chưa từng được duyệt ⇒ sửa nó KHÔNG ràng buộc gì ⇒ `[]`;
   *   - **BỎ DUYỆT**: hàng ĐANG duyệt bị gỡ ràng buộc ⇒ bản dịch cũ sai ⇒ CÓ ảnh hưởng.
   *
   * Đo được trên route thật: cùng `term` + cùng `translation`, chỉ khác `approved`, cho
   * `{"affected":[1]}` khi bỏ duyệt và `[]` khi giữ duyệt. Nói "không ảnh hưởng gì" cho
   * ca thứ hai là một câu NÓI SAI — đúng lớp lỗi "nhãn đảo" của ERRATA #10 mục 9.
   */
  const hangDangSua = (terms ?? []).find((t) => t.id === editingId) ?? null;
  const dangBoDuyet = approved === false && hangDangSua !== null && hangDangSua.approved;

  /** Con số hiện TRƯỚC khi lưu: bốn nhánh, nhánh "chưa duyệt" là CHỮ. */
  function noiXemTruoc(): string {
    if (approved === false && !dangBoDuyet) {
      return "Thuật ngữ CHƯA DUYỆT: đổi nó không ảnh hưởng gì — bản nháp không đi vào "
        + "prompt, nên không bản ghi nào bị đánh dấu lỗi thời.";
    }
    if (term.trim() === "") return "Gõ thuật ngữ để xem trước số bản ghi bị ảnh hưởng.";
    if (loiXemTruoc !== null) return `Không đọc được số ảnh hưởng: ${loiXemTruoc}`;
    if (affected === null) return "đang đếm…";
    // Bỏ duyệt là GỠ một ràng buộc, không phải "đổi": câu chữ phải nói đúng việc sắp xảy ra.
    const viec = dangBoDuyet ? "bỏ duyệt glossary" : "đổi glossary";
    return `⚠ ${viec} → ${affected.length} bản ghi bị đánh dấu lỗi thời`;
  }

  return (
    <section className="gl">
      {/* Năm con ỔN ĐỊNH của lưới `.gl` — thông báo nằm trong `.gl__tin` để số hàng
          của lưới không đổi theo trạng thái (một `grid-template-rows` cứng mà số con
          đổi thì hàng cuối trôi lên chỗ hàng `1fr`). */}
      <p className="gl__dem" data-testid="dem">
        {terms === null ? "đang nạp…" : `${terms.length} thuật ngữ · ${soDuyet} đã duyệt`}
      </p>

      {/* Số ảnh hưởng TRƯỚC khi lưu (§12.3). Văn bản đến từ MỘT hàm, nên nhánh "chưa
          duyệt" không thể trôi khỏi nhánh "có số". */}
      <p className="gl__xem-truoc" data-testid="affected-preview">{noiXemTruoc()}</p>

      <form
        className="gl__form"
        data-testid="form"
        onSubmit={(su) => {
          su.preventDefault();
          luu();
        }}
      >
        <span className="gl__o">
          <label className="gl__nhan" htmlFor="gl-lang">Nguồn</label>
          <select
            className="gl__nhap"
            id="gl-lang"
            data-testid="o-lang"
            value={lang}
            onChange={(e) => datLang(e.target.value)}
          >
            {NGUON.map((n) => <option key={n} value={n}>{n}</option>)}
          </select>
        </span>

        <span className="gl__o">
          <label className="gl__nhan" htmlFor="gl-term">Thuật ngữ</label>
          <input
            className="gl__nhap"
            id="gl-term"
            data-testid="o-thuat-ngu"
            value={term}
            onChange={(e) => datTerm(e.target.value)}
          />
        </span>

        <span className="gl__o">
          <label className="gl__nhan" htmlFor="gl-translation">Bản dịch</label>
          <input
            className="gl__nhap"
            id="gl-translation"
            data-testid="o-ban-dich"
            value={translation}
            onChange={(e) => datTranslation(e.target.value)}
          />
        </span>

        <span className="gl__o">
          <label className="gl__nhan" htmlFor="gl-note">Ghi chú</label>
          <input
            className="gl__nhap"
            id="gl-note"
            data-testid="o-ghi-chu"
            value={note}
            onChange={(e) => datNote(e.target.value)}
          />
        </span>

        <span className="gl__o gl__o--duyet">
          <label className="gl__nhan" htmlFor="gl-approved">Đã duyệt</label>
          <input
            className="gl__duyet"
            type="checkbox"
            id="gl-approved"
            data-testid="o-da-duyet"
            checked={approved}
            onChange={(e) => datApproved(e.target.checked)}
          />
        </span>

        <button className="gl__luu" data-testid="luu" type="submit" disabled={dangLuu}>
          {editingId === null ? "Lưu thuật ngữ" : "Lưu thay đổi"}
        </button>

        {/* Lỗi nằm DƯỚI ô nhập (checklist của plan: lỗi DƯỚI input), trong khi nhãn
            nằm TRÊN (`.gl__nhan`). */}
        {loiLuu !== null ? (
          <p className="gl__loi" data-testid="loi-luu">{loiLuu}</p>
        ) : null}
      </form>

      <div className="gl__tin">
        {/* Thông báo của lần GHI mang `affected` từ CHÍNH response của lần ghi — không
            phải một lời gọi xem trước thứ hai. */}
        {daLuu !== null ? (
          <p className="gl__da-luu" data-testid="da-luu">
            {`Đã lưu. Máy chủ báo ${daLuu} bản ghi bị đánh dấu lỗi thời.`}
          </p>
        ) : null}

        {loiNap !== null ? (
          <p className="gl__loi" data-testid="loi-nap">
            {`Không đọc được bảng thuật ngữ: ${loiNap}`}
          </p>
        ) : null}
      </div>

      <div className="gl__cuon">
        <table className="gl__bang" data-testid="bang">
          <thead>
            <tr className="gl__dau">
              {/* §4.4 ghi năm cột: `Nguồn zh | Bản dịch vi | Loại | Trạng thái | Ảnh hưởng`.
                  Cột "Loại" KHÔNG có trường dữ liệu nào trong `Term`
                  (`routes_glossary._json`: id, lang, term, translation, note, approved,
                  created_at) ⇒ cột thứ ba ở đây là `Ghi chú`, tức trường THẬT gần nhất,
                  thay vì một cột rỗng bịa ra. */}
              <th className="gl__cot">Nguồn</th>
              <th className="gl__cot">Bản dịch</th>
              <th className="gl__cot">Ghi chú</th>
              <th className="gl__cot">Trạng thái</th>
              <th className="gl__cot">Ảnh hưởng</th>
            </tr>
          </thead>
          <tbody>
            {(terms ?? []).map((t) => (
              <tr
                key={t.id}
                className={"gl__hang" + (t.approved ? "" : " is-cho-duyet")}
                data-testid={`hang-${t.id}`}
              >
                <td className="gl__nguon">{t.term}</td>
                <td className="gl__dich">
                  {/* §4.4: "Hàng chưa có bản dịch có chip `✕ trống` màu lỗi." Một ô rỗng
                      không nói được là "chưa dịch" hay "lỗi vẽ", nên chip là thông tin. */}
                  {t.translation === ""
                    ? <span className="gl__trong" data-testid={`trong-${t.id}`}>✕ trống</span>
                    : t.translation}
                </td>
                <td className="gl__ghichu">{t.note ?? ""}</td>
                <td className="gl__trang-thai">{t.approved ? "đã duyệt" : "chờ duyệt"}</td>
                <td className="gl__anh-huong" data-testid={`anh-huong-${t.id}`}>
                  {/* Cột "Ảnh hưởng" chỉ có nghĩa cho HÀNG ĐANG SỬA: con số xem trước là
                      "nếu tôi lưu hàng này thì sao". Hàng khác chưa đo ⇒ `—`, không bịa 0.
                      Con số hiện cả khi `approved` đang TẮT, vì tắt nó trên một hàng ĐANG
                      duyệt chính là ca BỎ DUYỆT — ca CÓ ảnh hưởng. */}
                  {editingId === t.id && affected !== null
                    ? String(affected.length)
                    : "—"}
                  {/* Đưa hàng vào form bằng một NÚT, không phải `<tr onClick>`: một đường
                      chỉ-bấm-chuột-được là một đường không tồn tại với bàn phím (spec §7). */}
                  <button
                    className="gl__sua"
                    type="button"
                    data-testid={`sua-${t.id}`}
                    onClick={() => moHang(t)}
                  >
                    Sửa
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>

        {terms !== null && terms.length === 0 && loiNap === null ? (
          <p className="gl__rong" data-testid="rong">
            Chưa có thuật ngữ nào. Điền form bên trên để thêm thuật ngữ đầu tiên.
          </p>
        ) : null}
      </div>
    </section>
  );
}
