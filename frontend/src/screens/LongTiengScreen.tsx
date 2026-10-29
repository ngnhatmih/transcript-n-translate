/**
 * §4.3+ Màn LỒNG TIẾNG — tab thứ tư, đúng bố cục demo `_demo-long-tieng/index.html`.
 *
 * BA TẦNG, không phải một dải:
 *   1. cột KÊNH (chọn nguồn đã dịch),
 *   2. DẢI THỜI GIAN — hàng trên là `chỗ`, hàng dưới là `take`; thanh amber nghĩa là take
 *      DÀI HƠN chỗ nên phải NÉN (đọc nhanh hơn) cho vừa. Nó KHÔNG có nghĩa là đè dòng sau:
 *      chồng lấn bị cấm bởi chính công thức `toc_do = max(1.0, take / max(slot, avail))`.
 *   3. BẢNG DÒNG — `#` · giờ · nguồn · dịch · take · so với chỗ · trạng thái, mỗi dòng mở được ô
 *      sửa có NGHE THỬ.
 *
 * ── VÌ SAO MÀN NÀY TỒN TẠI (một lỗi đã đo được) ────────────────────────────────────────
 *
 * Bản đầu đặt khối lồng tiếng vào TRONG `.cmp__bans` của màn Đối chiếu. Đo trên Chrome thật:
 * một job `dub` hỏng từ trước chiếm mất chỗ của cả bản dịch — khối rộng 2004 px, chữ tràn ra
 * ngoài khung, và ô giọng + nút biến mất (`co_o_giong: false`, `co_nut: false`) vì cả hai nằm
 * trong nhánh `dub === null`. Demo đã vẽ sẵn một TAB riêng (`mode__tab--moi`), nên chỗ đúng là
 * một màn riêng — mỗi màn một việc, và một job hỏng chỉ là một hàng trong lịch sử.
 *
 * ── VÌ SAO MÀN KHÔNG TỰ TÍNH `take`/`chỗ`/`tốc độ` ─────────────────────────────────────
 *
 * Bốn số đó chỉ tồn tại TRONG lượt chạy TTS. Chúng đến từ `GET /api/dubs/{id}/plan`, tức dẫn
 * xuất của chính handler (`dub-<id>.plan.json`). Tính lại ở client là nguồn sự thật thứ hai cho
 * cùng đại lượng — và nó SAI ngay, vì client không có take nào để đo.
 *
 * ⚠️ `plan === null` KHÁC "không có bản dịch" (lỗi HTTP) và KHÁC một kế hoạch rỗng: màn này nói
 * ba câu khác nhau, và câu "chưa có số đo" KHÔNG được kèm một con số bịa.
 */
import { Fragment, useEffect, useRef, useState } from "react";

import { dubTakeUrl, endpoints } from "../api/endpoints.ts";
import type { DubPlan, DubPlanRow, Job, TranslationDetail } from "../api/types.ts";

interface Props {
  /** Kênh đang chọn; `null` = chưa chọn (trạng thái THẬT khi mới mở app). */
  sourceId: number | null;
  /**
   * Mọi bản dịch của bản ghi đang mở, ĐÃ kèm `segments`.
   *
   * ⚠️ KHÔNG có `sources`/`onChonNguon` ở đây. Bản đầu nhận cả hai để tự vẽ một cột KÊNH — nhưng
   * shell đã có cột đó, nên mỗi tệp hiện hai lần với hai trạng thái chọn riêng. Kênh do shell
   * chọn và chỉ đi xuống qua `sourceId`; `sources` đã bị XOÁ khỏi props thay vì để nguyên một
   * tham số không ai đọc.
   */
  translations: TranslationDetail[];
  /**
   * `translations` còn ĐANG TẢI (`useApi(...).loading`).
   *
   * ⚠️ Phải phân biệt "chưa đọc xong" với "đọc xong và không có gì": ĐO ĐƯỢC trên ảnh chụp app
   * thật — trang vừa tải lại, `translations` chưa về, và màn nói "chưa có bản dịch nào cho kênh
   * này" trong khi kênh đó có bản dịch #10 với 434 dòng. Đó là `null ≠ 0` áp cho quyền sở hữu:
   * chưa biết KHÔNG được nói thành không có.
   */
  dangDocBanDich?: boolean;
  /** Bản dịch đang xem — quyết định của `App` (một chỗ trả lời), như màn Đối chiếu. */
  macDinhId?: number | null;
  onChonBanDich?: (id: number) => void;
  /** Job `dub` đang SỐNG của bản dịch đang chọn (`queued`/`running`/`done`), `null` = chưa lồng. */
  dubJob?: Job | null;
  onLongTieng?: (voice: string | null) => void;
  /** Huỷ lượt đang chạy — nút CHỈ hiện khi job đang `queued`/`running`. */
  onHuy?: () => void;
  /** Nguyên văn `ApiError.message` của lần xếp job (404/409 tiếng Việt). */
  loiLongTieng?: string | null;
}

/** Giây, hai chữ số — `—` khi KHÔNG ĐO ĐƯỢC (không phải `0,00`). */
function giay(x: number | null | undefined): string {
  return x === null || x === undefined ? "—" : `${x.toFixed(2)}s`;
}

/** Tốc độ dạng `1,15×` — dấu phẩy thập phân, như mọi số của giao diện tiếng Việt. */
function tocDo(x: number): string {
  return `${x.toFixed(2).replace(".", ",")}×`;
}

/** Câu của trạng thái — HAI câu KHÁC NHAU, không phải hai mức của một thang.
 *
 *  `"phai-sua"` đã bỏ cùng trần nén 1,35: tốc độ không còn bị kẹp nên không có dòng nào
 *  "không cứu được bằng tốc độ". Dòng nén mạnh vẫn là `nen` — đọc `speed` để biết mức. */
const NHAN_TRANG_THAI: Record<DubPlanRow["trang_thai"], string> = {
  vua: "vừa chỗ",
  nen: "nén",
};

export function LongTiengScreen({
  sourceId, translations, dangDocBanDich = false, macDinhId = null,
  onChonBanDich, dubJob = null, onLongTieng, onHuy, loiLongTieng = null,
}: Props) {
  // Bản dịch đang xem: lựa chọn của NGƯỜI DÙNG trước, rồi `macDinhId` của App, rồi hàng đầu.
  /**
   * Bản dịch NGƯỜI DÙNG bấm, `null` = chưa bấm (theo `macDinhId` của `App`).
   *
   * ⚠️ KHÔNG cần reset khi đổi kênh, và đây là ĐO ĐƯỢC chứ không phải suy đoán: id của kênh cũ
   * không có trong `translations` của kênh mới, nên `find` TRƯỢT và ba bước dưới tự rơi về
   * `macDinhId` rồi `translations[0]`. Đã thử thêm một `useEffect` reset theo `sourceId` và đo
   * lại bằng mutation: bỏ nó đi thì `aria-checked` của bản dịch kênh mới VẪN là `"true"` ⇒ nó
   * là mã chết, và đã bị xoá. Một `useEffect` "cho chắc" ở đây là nguồn sự thật thứ hai cho
   * cùng câu "bản nào đang xem".
   */
  const [chonId, datChonId] = useState<number | null>(null);

  const chon =
    translations.find((t) => t.id === chonId) ??
    translations.find((t) => t.id === macDinhId) ??
    translations[0] ??
    null;

  const [giong, datGiong] = useState("");
  const [plan, datPlan] = useState<DubPlan | null>(null);
  const [dangDocPlan, datDangDocPlan] = useState(false);
  const [loiPlan, datLoiPlan] = useState<string | null>(null);
  const [moDong, datMoDong] = useState<number | null>(null);
  /**
   * DÒNG ĐANG PHÁT (`null` = không phát), và câu lỗi phát của dòng đã sinh ra nó.
   *
   * ⚠️ BA LỖI ĐO ĐƯỢC, ghi lại vì mỗi lỗi đã từng là một bản sai:
   *
   * (1) Nút cũ là `<a href=… download>`, nên bấm vào là trình duyệt TẢI tệp wav — không có âm
   *     thanh nào phát ra trên trang. Đó không phải "nghe thử".
   *
   * (2) Bản kế tiếp dùng `<audio src=…>` + `play()`. Trên app thật nó KHÔNG BAO GIỜ phát:
   *     `readyState: 0`, `networkState: 2` (LOADING), `duration: null`, `currentTime: 0`, và
   *     Resource Timing RỖNG — chưa từng có request. Nguyên nhân thật là route trả
   *     `Content-Disposition: attachment` (sửa ở backend) VÀ, sau khi sửa header, phần tử
   *     `<audio>` của chính Chrome trong phiên này vẫn treo: WAV dựng trong bộ nhớ (blob URL,
   *     không mạng, không server) cũng `loadstart → stalled`. `canPlayType('audio/wav')` trả
   *     `"maybe"`, và `decodeAudioData` trên ĐÚNG tệp đó trả `ok · 48000 Hz · 2.56 s · 1 kênh`
   *     — nên tệp và bộ giải mã đều tốt, chỉ phần tử media là không khởi tạo được.
   *
   * (3) Vì (2), đường phát dùng **WebAudio**: `fetch` lấy byte → `decodeAudioData` →
   *     `AudioBufferSourceNode.start()`. Đây là API đã đo được `ok: 1` trên chính tệp này, và
   *     nó không phụ thuộc phần tử media. `AudioContext` đo được `state: "running"`, 48 kHz.
   */
  const [dangPhat, datDangPhat] = useState<number | null>(null);
  const [loiNghe, datLoiNghe] = useState<string | null>(null);
  /** Dòng đã sinh ra lỗi phát gần nhất — để câu lỗi không hiện ở MỌI dòng cùng lúc. */
  const loiNgheTheoDong = useRef<number | null>(null);
  /** Nguồn đang kêu. `stop()` nó là cách DUY NHẤT dừng một `AudioBufferSourceNode`. */
  const nguonDangKeu = useRef<AudioBufferSourceNode | null>(null);
  /** `AudioContext` tạo một lần cho cả màn; tạo mỗi lần bấm là rò rỉ tài nguyên âm thanh. */
  const ctxAm = useRef<AudioContext | null>(null);

  /** Dừng tiếng đang kêu (nếu có) và quên nó đi. An toàn khi gọi nhiều lần. */
  function dungTieng() {
    const n = nguonDangKeu.current;
    nguonDangKeu.current = null;
    if (n === null) return;
    try {
      n.onended = null;
      n.stop();
    } catch {
      // `stop()` trên nguồn đã dừng ném `InvalidStateError`; nuốt nó là ĐÚNG — mục đích là
      // "không còn kêu", và nó đã không còn kêu.
    }
  }

  /**
   * Phát / dừng take của MỘT dòng, ngay trên trang.
   *
   * Ba điều hàm này phải làm đúng:
   *   1. Bấm cùng một dòng lần hai ⇒ DỪNG, không tải lại tệp.
   *   2. Bấm dòng KHÁC ⇒ dòng cũ dừng hẳn TRƯỚC khi dòng mới bắt đầu.
   *   3. Lỗi (404, wav hỏng, trình duyệt chặn) phải HIỆN RA ở đúng dòng, không im lặng.
   */
  function ngheThu(i: number) {
    datLoiNghe(null);
    if (dangPhat === i) {
      dungTieng();
      datDangPhat(null);
      return;
    }
    // KHÔNG gọi `dungTieng()` ở đây: `phatDong` đã gọi nó NGAY TRƯỚC `start()`, và đo được rằng
    // bỏ dòng này không đổi hành vi nào (mutant SỐNG, `pass 10 / fail 0`) — nó chỉ là một khai
    // báo chết. Chỗ thật sự bảo vệ "không phát chồng" là `dungTieng()` trong `phatDong`, và
    // mutant xoá ĐÚNG chỗ đó thì chết (xem bài NGHE THỬ vế 4).
    loiNgheTheoDong.current = i;
    datDangPhat(i);
    void phatDong(i);
  }

  /** Nạp và phát take của dòng `i`. Tách khỏi `ngheThu` để phần đồng bộ chỉ còn trạng thái. */
  async function phatDong(i: number) {
    const baoLoi = (cau: string) => {
      loiNgheTheoDong.current = i;
      datLoiNghe(cau);
      datDangPhat(null);
    };
    try {
      const Ctx = window.AudioContext
        ?? (window as unknown as { webkitAudioContext?: typeof AudioContext }).webkitAudioContext;
      if (Ctx === undefined) {
        baoLoi("trình duyệt này không có WebAudio — không phát tại chỗ được");
        return;
      }
      const ctx = (ctxAm.current ??= new Ctx());
      // Trình duyệt có thể để `context` ở trạng thái `suspended` cho tới một cú bấm; cú bấm
      // CHÍNH LÀ hành động người dùng cần, nên `resume()` ở đây hợp lệ và cần thiết.
      if (ctx.state === "suspended") await ctx.resume();

      const resp = await fetch(dubTakeUrl(chon!.id, i));
      if (!resp.ok) {
        baoLoi(`không tải được take của dòng ${i + 1} (HTTP ${resp.status})`);
        return;
      }
      const byte = await resp.arrayBuffer();
      const buffer = await ctx.decodeAudioData(byte);
      // Đổi dòng trong lúc đang nạp: cú bấm sau đã thắng, đừng phát chồng.
      if (loiNgheTheoDong.current !== i) return;
      dungTieng();
      const nguon = ctx.createBufferSource();
      nguon.buffer = buffer;
      nguon.connect(ctx.destination);
      nguon.onended = () => {
        // `onended` bắn cả khi ta chủ động `stop()`; chỉ hạ trạng thái nếu ĐÚNG nguồn này còn
        // là nguồn đang kêu, nếu không ta sẽ xoá trạng thái của một lượt phát mới hơn.
        if (nguonDangKeu.current === nguon) {
          nguonDangKeu.current = null;
          datDangPhat(null);
        }
      };
      nguonDangKeu.current = nguon;
      nguon.start();
    } catch (e) {
      baoLoi(`không phát được take này (${e instanceof Error ? e.name : "lỗi lạ"})`);
    }
  }

  // Rời màn thì dừng tiếng và đóng context — không để âm thanh sống ngoài vòng đời component.
  useEffect(() => () => {
    dungTieng();
    const ctx = ctxAm.current;
    ctxAm.current = null;
    if (ctx !== null) void ctx.close();
  }, []);

  // Kế hoạch đọc lại khi ĐỔI BẢN DỊCH và khi job vừa XONG (đó là lúc tệp kế hoạch mới ra đời).
  // `dubJob?.state` nằm trong deps vì một job `done` là tín hiệu DUY NHẤT cho biết có số mới.
  const banId = chon?.id ?? null;
  const trangThaiJob = dubJob?.state ?? null;
  useEffect(() => {
    if (banId === null) {
      datPlan(null);
      datLoiPlan(null);
      return;
    }
    let con = true;
    datDangDocPlan(true);
    datLoiPlan(null);
    endpoints.getDubPlan(banId)
      .then((kq) => { if (con) datPlan(kq); })
      .catch((e: unknown) => {
        if (!con) return;
        datPlan(null);
        datLoiPlan(e instanceof Error ? e.message : String(e));
      })
      .finally(() => { if (con) datDangDocPlan(false); });
    return () => { con = false; };
  }, [banId, trangThaiJob]);

  const dong = chon?.segments ?? [];
  const keHoachTheoI = new Map((plan?.dong ?? []).map((d) => [d.i, d]));
  const dangChay = dubJob !== null && (dubJob.state === "queued" || dubJob.state === "running");

  return (
    <div className="lt" data-testid="lt-man">
      {/* ⚠️ KHÔNG có cột KÊNH ở đây. Bản đầu chép nguyên ba tầng của demo và vẽ lại danh sách
          kênh NGAY TRONG màn này — nhưng shell ĐÃ có cột kênh bên trái, nên mỗi tệp hiện HAI lần
          cách nhau một đường kẻ, và hai bản sao có hai trạng thái chọn riêng (`is-chon` của shell
          và `is-chon` của `.lt__nguon`) — nguồn sự thật thứ hai, đúng lớp lỗi `I2`. Đo được trên
          ảnh chụp app thật: `BV1BfBFB4Ebh_audio-Vocal.mp3` nằm ở cả hai cột.
          Demo tự vẽ cột kênh vì nó là một trang đứng một mình; app này thì không. Kênh do shell
          chọn và truyền xuống qua `sourceId` — MỘT câu trả lời. */}

      {/* ── HAI tầng còn lại: dải thời gian, rồi bảng dòng ────────────────────────── */}
      {/* ── TẦNG 2 + 3: dải thời gian, rồi bảng dòng ─────────────────────────────── */}
      <section className="lt__giua" aria-label="kế hoạch lồng tiếng">
        <div className="lt__thanh">
          <span className="nhan">Lồng tiếng</span>
          {dangChay ? (
            <>
              <span className="lt__tin" data-testid="lt-dang-chay">
                {dubJob?.state === "queued" ? "chờ tới lượt" : "đang lồng tiếng…"}{" "}
                {Math.round((dubJob?.progress ?? 0) * 100)}%
              </span>
              {onHuy !== undefined ? (
                <button type="button" className="lt__nut lt__nut--huy" data-testid="lt-huy"
                  onClick={onHuy}>
                  huỷ
                </button>
              ) : null}
            </>
          ) : (
            <>
              <input className="lt__giong" type="text" value={giong}
                placeholder="giọng (bỏ trống = mặc định)"
                aria-label="giọng đọc cho lượt lồng tiếng"
                onChange={(e) => datGiong(e.target.value)} />
              {onLongTieng !== undefined && chon !== null ? (
                <button type="button" className="lt__nut" data-testid="lt-nut"
                  onClick={() => onLongTieng(giong.trim() === "" ? null : giong.trim())}>
                  lồng tiếng
                </button>
              ) : null}
            </>
          )}
          {dubJob?.state === "done" ? (
            <span className="lt__tai" data-testid="lt-tai">
              đã có · tải:
              {["wav", "mp3", "aac", "m4a", "flac"].map((dd) => (
                <a key={dd} className="lt__nut-tai" data-testid={`lt-tai-${dd}`}
                  href={`/api/dubs/${chon?.id}/download?format=${dd}`} download>
                  {dd}
                </a>
              ))}
            </span>
          ) : null}
          {/* Lỗi xếp job: NGUYÊN VĂN câu của backend, ở chỗ riêng, KHÔNG xoá nút. */}
          {loiLongTieng === null ? null : (
            <span className="lt__loi" data-testid="lt-loi-tao">{loiLongTieng}</span>
          )}
          {/* Job ĐÃ HỎNG: câu backend có thể là cả một vết lỗi. `<summary>` nói trạng thái bằng
              chữ; mở ra thì NGUYÊN VĂN. Đo được: để nguyên nó trên một dòng làm khối rộng
              2004 px và chữ tràn ra ngoài khung. */}
          {dubJob !== null && dubJob.state === "failed" ? (
            <details className="lt__loi-hop" data-testid="lt-loi-hop">
              <summary className="lt__loi" data-testid="lt-loi">lỗi lồng tiếng — mở để xem</summary>
              <pre className="lt__loi-nguyen-van" data-testid="lt-loi-nguyen-van">
                {dubJob.error ?? dubJob.state}
              </pre>
            </details>
          ) : null}
        </div>

        {/* DẢI CHỌN BẢN DỊCH — hàng riêng, không nhét vào thanh công cụ: mỗi bản dịch thêm hai
            phần tử (chọn + xoá ở màn Đối chiếu) là thanh đó tràn ngang khi có vài bản, đúng lỗi
            đã đo được ở `.cmp__thanh`. Ở đây chỉ có nút CHỌN: xoá bản dịch là việc của màn Đối
            chiếu, và hai chỗ xoá cùng một thứ là hai nguồn sự thật.
            Bấm một bản ⇒ BÁO LÊN `App` (cùng lý do `I2`: `banDangXemId` là của App, màn không
            được giữ bản sao thứ hai của "bản nào đang xem"). */}
        {translations.length === 0 ? null : (
          <div className="lt__bans" data-testid="lt-bans">
            {translations.map((t) => (
              <button key={t.id} type="button"
                className={t.id === chon?.id ? "lt__ban is-chon" : "lt__ban"}
                role="radio" aria-checked={t.id === chon?.id}
                data-testid={`lt-ban-${t.id}`}
                onClick={() => { datChonId(t.id); onChonBanDich?.(t.id); }}>
                bản dịch #{t.id} · {t.engine} · {t.status}
              </button>
            ))}
          </div>
        )}

        {/* DẢI THỜI GIAN — chỉ vẽ khi CÓ số đo. Không có thì nói "chưa đo", không vẽ một dải
            rỗng trông như đã đo và mọi thứ đều vừa. */}
        {plan === null ? (
          <p className="lt__chua-do" data-testid="lt-chua-do">
            {dangDocPlan ? "đang đọc số đo…"
              : loiPlan !== null ? `không đọc được số đo: ${loiPlan}`
                // ⚠️ BỐN câu, không phải ba. ĐO ĐƯỢC trên ảnh chụp app thật: trang vừa tải lại
                // thì `translations` CHƯA VỀ, và màn nói "kênh này chưa có bản dịch" trong khi
                // kênh đó có bản dịch #10 với 434 dòng. "Chưa đọc xong" và "đọc xong, không có"
                // là hai sự thật khác nhau — `null ≠ 0` áp cho quyền sở hữu, không chỉ cho số.
                : sourceId === null ? "chọn một kênh ở cột bên trái"
                  : dangDocBanDich ? "đang đọc bản dịch…"
                    : chon === null ? "kênh này chưa có bản dịch — tạo một bản ở màn Đối chiếu"
                      : "chưa lồng lần nào — bấm “lồng tiếng” để có số đo từng dòng"}
          </p>
        ) : (
          <>
            <div className="lt__dai" data-testid="lt-dai"
              role="img"
              aria-label={`dải thời gian ${plan.tong_giay.toFixed(2)} giây: ${plan.dem.vua} dòng vừa chỗ, ${plan.dem.nen} dòng nén, trong đó ${plan.dem.nen_manh} dòng nén trên 1,5 lần`}>
              {plan.dong.map((d) => {
                const rongChỗ = (d.slot / plan.tong_giay) * 100;
                const rongTake = (d.take / plan.tong_giay) * 100;
                return (
                  <span key={d.i} className="lt__cap"
                    style={{ left: `${(d.start / plan.tong_giay) * 100}%`, width: `${rongChỗ}%` }}>
                    <span className="lt__cho" />
                    <span className={`lt__take lt__take--${d.trang_thai}${d.speed > 1.5 ? " lt__take--nen-manh" : ""}`}
                      style={{ width: `${rongTake}%` }}
                      title={`#${d.i} · chỗ ${giay(d.slot)} · take ${giay(d.take)} · ${tocDo(d.speed)}`} />
                  </span>
                );
              })}
            </div>
            <div className="lt__dau-dai">
              <span className="lt__tv">trung vị {tocDo(plan.trung_vi_toc_do)}</span>
              <span className="lt__dem-dai">
                vừa chỗ {plan.dem.vua} · nén {plan.dem.nen} · nén mạnh {plan.dem.nen_manh}
              </span>
              <span className="lt__canh-bao">thanh amber = take dài hơn chỗ, đã nén cho vừa (không đè dòng sau)</span>
              <span className="lt__tong">{giay(plan.tong_giay)}</span>
            </div>
          </>
        )}

        {/* BẢNG DÒNG — luôn có, vì câu của bản dịch là thứ người dùng cần đọc KỂ CẢ khi chưa đo. */}
        {chon === null ? (
          <p className="lt__rong lt__rong--giua">chưa có bản dịch nào cho kênh này</p>
        ) : (
          <div className="lt__cuon">
            <table className="lt__bang">
              <thead>
                <tr>
                  <th className="nhan">#</th>
                  <th className="nhan">giờ</th>
                  <th className="nhan">dịch (vi)</th>
                  <th className="nhan">take</th>
                  <th className="nhan">so với chỗ</th>
                  <th className="nhan">trạng thái</th>
                </tr>
              </thead>
              <tbody>
                {dong.map((s) => {
                  const kh = keHoachTheoI.get(s.i);
                  const mo = moDong === s.i;
                  // ⚠️ `Fragment` có `key`, KHÔNG dùng `<>…</>`: mỗi vòng `map` trả HAI phần tử
                  // (dòng + ô sửa), nên React cần một khoá trên chính mảnh đó. Đo được: dùng
                  // `<>` sinh cảnh báo "Each child in a list should have a unique key prop".
                  return (
                    <Fragment key={s.i}>
                      <tr className={mo ? "lt__dong is-mo" : "lt__dong"}
                        data-testid={`lt-dong-${s.i}`}
                        onClick={() => datMoDong(mo ? null : s.i)}>
                        {/* ⚠️ `s.i` là chỉ số 0-BASED (nó là khoá của `Segment`), nhưng NGƯỜI ĐỌC đếm dòng từ 1 —
                đo được trên ảnh chụp app thật: cột `#` hiện `00, 01, 02…`, tức lệch một so với cột
                `GIỜ` bên cạnh và với chính lời của người dùng. `i` chỉ đổi ở ĐÂY, không ở dữ liệu. */}
              <td className="lt__so">{String(s.i + 1).padStart(2, "0")}</td>
                        <td className="lt__gio">{s.start.toFixed(2)}</td>
                        <td className="lt__chu">{s.text}</td>
                        <td className="lt__take-so">{kh === undefined ? "—" : giay(kh.take)}</td>
                        <td className="lt__thanh">
                          {kh === undefined ? (
                            <span className="lt__ti-le">—</span>
                          ) : (
                            <>
                              <span className="lt__o-nen">
                                <span className={`lt__o-take lt__o-take--${kh.trang_thai}${kh.speed > 1.5 ? " lt__o-take--nen-manh" : ""}`}
                                  style={{ width: `${Math.min(100, (kh.take / Math.max(kh.slot, 0.01)) * 100)}%` }} />
                              </span>
                              <span className="lt__ti-le">{tocDo(kh.speed)}</span>
                            </>
                          )}
                        </td>
                        <td className="lt__trang-thai">
                          {kh === undefined ? "chưa đo" : (kh.speed > 1.5 ? "nén mạnh" : NHAN_TRANG_THAI[kh.trang_thai])}
                        </td>
                      </tr>
                      {mo ? (
                        <tr className="lt__sua-hang">
                          <td />
                          <td colSpan={5}>
                            <div className="lt__sua">
                              <span className="nhan">Dòng {String(s.i + 1).padStart(2, "0")}</span>
                              {kh === undefined ? (
                                <span className="lt__sua-ghi">chưa có take — lồng tiếng rồi mở lại</span>
                              ) : (
                                <>
                                  <span className="lt__sua-ghi">
                                    take {giay(kh.take)} / chỗ {giay(kh.slot)} — {tocDo(kh.speed)}
                                    {kh.speed > 1.5 ? " · nén mạnh, khó nghe" : ""}
                                  </span>
                                  <button type="button"
                                    className="lt__nut-nho"
                                    data-testid={`lt-nghe-${s.i}`}
                                    data-dang-phat={dangPhat === s.i ? "1" : "0"}
                                    onClick={() => ngheThu(s.i)}>
                                    {dangPhat === s.i ? "dừng" : "nghe take"}
                                  </button>
                                  {loiNghe !== null && dangPhat === null && loiNgheTheoDong.current === s.i ? (
                                    <span className="lt__dang-nghe lt__dang-nghe--loi">{loiNghe}</span>
                                  ) : null}
                                </>
                              )}
                            </div>
                          </td>
                        </tr>
                      ) : null}
                    </Fragment>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </section>
    </div>
  );
}

