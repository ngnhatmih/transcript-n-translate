/**
 * §4.2 — CỬA VÀO CỦA WORKSPACE 1: **NẠP TỆP** (khung kẻ nét đứt ở vùng giữa) + **LỐI GỌN**
 * cho vùng KÊNH. Hai lối vào, **MỘT** hàm nạp.
 *
 * ## Vì sao tệp này tồn tại — đo được trước W2
 *
 * `endpoints.uploadSource` có **0 lượt gọi trong sản phẩm**, và trong `frontend/src` **không có**
 * `type="file"`, **không có** `onDrop`/`dataTransfer` ở đâu. Nghĩa là: **workspace 1 (audio → text)
 * KHÔNG CÓ CỬA VÀO** — người dùng không có cách nào đưa tệp của họ vào app. Spec UI §4.2 mô tả
 * chính chỗ này: *"Vùng giữa là khung kẻ nét đứt với chữ Archivo Expanded giãn rộng:
 * `KÉO TỆP VÀO ĐÂY` + dòng mono liệt kê định dạng nhận được. Không phải một thẻ nhỏ giữa màn hình."*
 *
 * ## ĐỊNH DẠNG: DÒNG MONO LÀ **THÔNG TIN**, KHÔNG PHẢI **THI HÀNH**
 *
 * ⚠️ ĐỌC MÃ BACKEND, KHÔNG ĐOÁN — `backend/app/api/routes_sources.py`:
 *   - `upload()` chỉ gọi `_safe_name(file.filename)` rồi ghi tệp;
 *   - `_safe_name()` (gọi `app.domain.paths.safe_basename`) **chỉ giữ phần TÊN TRẦN** và **giữ
 *     `suffix`** — nó KHÔNG kiểm phần mở rộng;
 *   - **không có** bất kỳ phép kiểm `content_type`/đuôi tệp nào trên đường nạp.
 *   ⇒ **Backend KHÔNG từ chối tệp nào** (ngoài tệp RỖNG 0 byte: `422 "tệp rỗng"`).
 * Vì vậy danh sách đuôi dưới đây là **những gì đường ống ffmpeg/faster-whisper đọc được** —
 * một **GỢI Ý**, không phải một lời hứa và không phải một bộ lọc. Cùng lý do đó, `client.ts`
 * KHÔNG được chặn tệp: chặn ở client trong khi backend nhận = **nguồn sự thật thứ hai**, và
 * người dùng mất một tệp mà backend vốn nhận. (Nếu ai đó cho rằng PHẢI chặn thì đó là **quyết
 * định sản phẩm** — báo lại, đừng tự làm.)
 *
 * ⚠️ Vì cùng lý do, `<input type="file">` ở đây **CỐ Ý KHÔNG có `accept=`**: `accept` là gợi ý
 * của trình chọn tệp **và kéo-thả BỎ QUA nó hoàn toàn**, nên nó không phải một phép kiểm — chỉ
 * là một bộ lọc nửa vời không có backend nào đứng sau.
 *
 * 🔴 **NỢ GHI Ở ĐÂY CHO NGƯỜI SỬA BACKEND (vòng sửa W2 #1, `M5` của review).** Sự thật *"backend
 * không chặn đuôi nào"* là sự thật của **MỘT TỆP KHÁC** (`backend/app/api/routes_sources.py`), và
 * nó **KHÔNG** được ghim bằng câu chữ cho người dùng nữa. Bản trước ghim nó bằng literal
 * `/backend không chặn đuôi nào/` trong TSX — một literal như thế **KHÔNG THỂ đỏ khi backend đổi**,
 * tức lời hứa về một hệ thống khác được ghim bằng **chính bản sao chữ của nó** (phép đo tự quy
 * chiếu). Nay câu cho người dùng chỉ nói về thứ **CLIENT** làm (gửi được mọi đuôi), và điều đó có
 * **bài ghim HÀNH VI** (tệp `.xyzla` đi tới server trong `App.test.tsx`).
 * ⇒ **NẾU backend thêm whitelist đuôi, PHẢI sửa `DINH_DANG` dưới đây.**
 *
 * ## HAI CHỖ "LẦN DÙNG THỨ HAI IM LẶNG" — đã sửa (vòng sửa W2 #1, `M3` của review)
 *
 * 1. `<input type="file">` **không bao giờ được reset `value`** ⇒ theo cơ chế HTML, chọn LẠI
 *    ĐÚNG tệp đó **không phát `change`**, nên lối gọn (không có nút) không có gì xảy ra. Nay cả
 *    hai lối **xoá `value` ngay sau khi đọc `files`**.
 *    ⚠️ **Mức bằng chứng:** *"mã không reset"* là **ĐO ĐƯỢC**; *"trình duyệt im lặng"* là **SUY
 *    LUẬN từ cơ chế HTML** — jsdom (`fireEvent.change`) phát thẳng sự kiện nên **không tái lập
 *    được** hành vi đó, và cũng không quan sát được `value=""` (RTL đặt `files` thành thuộc tính
 *    riêng trên node, che setter của jsdom).
 * 2. Khung giữa **giữ `chon`** sau lượt nạp ⇒ nút `nạp` vẫn mở ⇒ bấm lần hai **nạp trùng** cùng
 *    tệp. Nay `chon` được **XOÁ sau lượt nạp đã chạy** (nút trở lại vô hiệu, và câu "chưa chọn tệp
 *    nào" trở lại) — đó là vế **ĐO ĐƯỢC** của chỗ này.
 *    Và `useNapTep` **không còn bỏ im lặng** lượt chọn trong lúc đang nạp: nó nói ra (`boQua`).
 *
 * ## VÌ SAO `onDragOver` PHẢI `preventDefault`
 *
 * Mặc định của trình duyệt với một vùng thả là **MỞ tệp** (điều hướng sang `file://…`), và nó
 * chỉ phát sự kiện `drop` nếu `dragover` đã bị chặn mặc định. Thiếu đúng một dòng đó thì người
 * dùng kéo tệp vào và **mất luôn trang đang làm việc** — nên nó có bài ghim riêng, đo trên
 * `defaultPrevented` của chính sự kiện (jsdom không có điều hướng để mà đo hậu quả).
 *
 * ## MỘT hàm nạp, HAI lối vào (điểm thiết kế chính — đừng viết lần hai)
 *
 * `napTep(files, lang)` nằm ở `App` (nơi duy nhất đọc/ghi trạng thái của shell) và được TRUYỀN
 * XUỐNG cả hai lối: khung §4.2 (dưới đây) và lối gọn `NhapGon` (vùng KÊNH, cho §12.2 *"nạp 3 tệp
 * cùng lúc"* khi đã có kênh). Hai lối chỉ khác nhau ở HÌNH DÁNG; cả hai đi qua cùng một thân hàm,
 * nên không có bản sao thứ hai của luật "nạp lần lượt + làm mới danh sách + chọn kênh đầu tiên
 * thành công". `IntakeFrame.tsx`/`ChannelZone.tsx` **KHÔNG** được gọi `uploadSource` trực tiếp —
 * có bài ghim cấu trúc cho đúng điều đó (đếm call site trong chính mã nguồn).
 */
import { useState } from "react";

import type { SourceLang } from "../api/types.ts";

/** Hai ngôn ngữ DUY NHẤT mà backend nhận (`routes_sources.ALLOWED_LANGS = {"zh","en"}`). */
export const LANG_NHAN: ReadonlyArray<{ value: SourceLang; ten: string }> = [
  { value: "zh", ten: "zh — tiếng Trung" },
  { value: "en", ten: "en — tiếng Anh" },
];

/** Một tệp đã vào được máy chủ. `sourceId` là id KÊNH (`created.source.id`). */
export interface NapThanhCong {
  ten: string;
  ok: true;
  sourceId: number;
}

/** Một tệp bị từ chối. `loi` là **NGUYÊN VĂN** `ApiError.message` (`"<status>: <detail>"`). */
export interface NapThatBai {
  ten: string;
  ok: false;
  loi: string;
}

export type KetQuaNap = NapThanhCong | NapThatBai;

/**
 * Hàm nạp dùng chung — do `App` cài đặt, do cả HAI lối vào gọi.
 *
 * `Promise<KetQuaNap[]>` (không phải `KetQuaNap`): một lượt nạp là NHIỀU tệp (§12.2), và mỗi
 * tệp có kết quả RIÊNG — một tệp lỗi không được làm mờ kết quả của các tệp khác.
 */
export type NapTep = (files: File[], lang: SourceLang) => Promise<KetQuaNap[]>;

/**
 * Trạng thái nạp của MỘT lối vào: kết quả của lượt gần nhất + cờ đang nạp + câu nói ra khi một
 * lượt chọn bị BỎ QUA.
 *
 * Vì sao là hook chứ không phải hai bản `useState` chép tay: hai lối vào có CÙNG luật hiển thị
 * kết quả (kể cả lỗi), và luật "một tệp lỗi phải HIỆN RA bằng chữ" chỉ nên có một định nghĩa.
 *
 * ⚠️ `boQua` tồn tại vì `M3` của review (vòng sửa W2 #1): guard cũ `if (files.length === 0 ||
 * dangNap) return;` **bỏ im lặng** một lượt chọn — người dùng chọn tệp trong lúc đang nạp thì
 * KHÔNG có gì xảy ra và KHÔNG có gì nói vì sao. Nay mọi đường bỏ qua đều để lại một CÂU.
 */
export function useNapTep(napTep: NapTep): {
  ketQua: KetQuaNap[];
  dangNap: boolean;
  /** Câu nói ra khi lượt chọn vừa rồi KHÔNG được gửi; `null` = không có gì bị bỏ qua. */
  boQua: string | null;
  /** Trả `true` nếu lượt nạp THẬT SỰ đã chạy (để nơi gọi biết có nên xoá lựa chọn hay không). */
  nap: (files: readonly File[], lang: SourceLang) => Promise<boolean>;
} {
  const [ketQua, datKetQua] = useState<KetQuaNap[]>([]);
  const [dangNap, datDangNap] = useState(false);
  const [boQua, datBoQua] = useState<string | null>(null);

  async function nap(files: readonly File[], lang: SourceLang): Promise<boolean> {
    if (dangNap) {
      datBoQua(
        `đang nạp — ${files.length} tệp vừa chọn CHƯA được gửi; chờ lượt này xong rồi chọn lại`,
      );
      return false;
    }
    if (files.length === 0) {
      datBoQua("chưa chọn tệp nào — không có gì để nạp");
      return false;
    }
    datBoQua(null);
    datDangNap(true);
    try {
      // Kết quả của lượt NÀY thay thế lượt trước: danh sách là "vừa nạp gì", không phải một
      // nhật ký tích luỹ không bao giờ được xoá.
      datKetQua(await napTep([...files], lang));
      return true;
    } finally {
      datDangNap(false);
    }
  }

  return { ketQua, dangNap, boQua, nap };
}

/**
 * Kết quả TỪNG TỆP, bằng **CHỮ** — kể cả tệp lỗi.
 *
 * ⚠️ Chỉ đổi MÀU là không đủ (ERRATA #15 mục 3 + spec UI §7: thông tin không được chỉ nằm ở màu):
 * câu lỗi của backend phải đọc được. Và `loi` được in **NGUYÊN VĂN** — thay nó bằng "có lỗi xảy
 * ra" là bỏ mất đúng thông tin người dùng cần để sửa (`422 "tệp rỗng"` nói được điều mà "lỗi"
 * không nói được).
 */
export function KetQuaNapList({ ketQua }: { ketQua: KetQuaNap[] }) {
  return (
    // `role="status"` (review W2, `M4`): kết quả nạp là một VÙNG SỐNG — trình đọc màn hình phải
    // được THÔNG BÁO khi lượt nạp xong, chứ không phải chỉ đọc được nếu người dùng tự đi tìm.
    // Màu `--ok`/`--fault` vẫn chỉ là tín hiệu THỨ HAI: thông tin nằm ở CHỮ.
    <ul className="nap__ket-qua" data-testid="nap-ket-qua" role="status">
      {ketQua.map((kq, i) => (
        <li
          key={`${kq.ten}-${i}`}
          className={kq.ok ? "nap__kq nap__kq--xong" : "nap__kq nap__kq--loi"}
        >
          {kq.ok ? `${kq.ten}: đã nạp — kênh ${kq.sourceId}` : `${kq.ten}: LỖI — ${kq.loi}`}
        </li>
      ))}
    </ul>
  );
}

/**
 * Dòng mono của §4.2 — **thông tin**, không phải phép kiểm (xem khối đầu tệp).
 *
 * ⚠️ **CÂU NÀY CHỈ NÓI VỀ THỨ CLIENT LÀM** (vòng sửa W2 #1, `M5`): nó liệt kê những định dạng
 * `ffmpeg` đọc được như một GỢI Ý, và nói rằng **đuôi khác vẫn gửi được**. Vế thứ hai là một
 * khẳng định về CHÍNH ỨNG DỤNG NÀY (không có bộ lọc ở client), nên nó **đỏ được** — có bài ghim
 * hành vi: tệp `.xyzla` đi tới server trong `App.test.tsx`.
 *
 * ⚠️ Bản trước viết *"backend không chặn đuôi nào"*: đúng hôm nay, nhưng đó là một lời hứa về
 * **MỘT HỆ THỐNG KHÁC**, và nó được ghim bằng chính chuỗi chữ của mình ⇒ nếu backend thêm whitelist
 * thì câu thành lời nói dối mà bài test **vẫn XANH**. Nợ đó nay ghi ở khối đầu tệp (chỗ người sửa
 * backend đọc), không nằm trong chữ cho người dùng nữa.
 */
const DINH_DANG =
  "wav · mp3 · m4a · aac · flac · ogg · opus · wma · amr · mp4 · mkv · mov · webm · avi · ts"
  + " — định dạng thường dùng; tệp đuôi khác vẫn gửi được, cứ thử tệp của bạn";

/** Bộ chọn ngôn ngữ: CHỈ `zh`/`en`, đúng `ALLOWED_LANGS` của backend. */
function ChonLang({
  id,
  lang,
  onLang,
  className,
}: {
  id: string;
  lang: SourceLang;
  onLang: (lang: SourceLang) => void;
  className: string;
}) {
  return (
    <select
      id={id}
      className={className}
      data-testid={id}
      value={lang}
      onChange={(suKien) => {
        // Thu hẹp về ĐÚNG hai giá trị backend nhận: một giá trị lạ (đến từ DOM, không đến từ
        // danh sách `option`) KHÔNG được đi vào request — backend sẽ trả 422, nhưng cái phải
        // đúng ở đây là client không bao giờ GỬI một ngôn ngữ ngoài `ALLOWED_LANGS`.
        const chon = suKien.currentTarget.value;
        if (chon === "zh" || chon === "en") onLang(chon);
      }}
    >
      {LANG_NHAN.map((l) => (
        <option key={l.value} value={l.value}>{l.ten}</option>
      ))}
    </select>
  );
}

/**
 * §4.2 — KHUNG KẺ NÉT ĐỨT ở vùng giữa: chữ giãn rộng `KÉO TỆP VÀO ĐÂY` + dòng mono + ô chọn tệp
 * + chọn ngôn ngữ + nút `nạp`, cộng vùng kết quả TỪNG TỆP.
 *
 * Kéo-thả nạp NGAY (ngôn ngữ đang chọn); tệp chọn qua ô chọn tệp thì chờ bấm `nạp` — hai đường
 * vào cùng một hàm, và nút chỉ mở khoá khi đã có tệp.
 */
export function IntakeFrame({ napTep }: { napTep: NapTep }) {
  const [lang, datLang] = useState<SourceLang>("zh");
  const [chon, datChon] = useState<File[]>([]);
  const { ketQua, dangNap, boQua, nap } = useNapTep(napTep);

  return (
    <div className="nap" data-testid="khung-nap">
      <div
        className="nap__khung"
        data-testid="nap-khung-keo"
        // ⚠️ THIẾU DÒNG NÀY THÌ TRÌNH DUYỆT **MỞ TỆP** thay vì cho thả (xem khối đầu tệp).
        onDragOver={(suKien) => {
          suKien.preventDefault();
        }}
        onDrop={(suKien) => {
          // Chặn mặc định ở CẢ `drop`: không có nó thì tệp vẫn có thể bị trình duyệt mở.
          suKien.preventDefault();
          const tha = suKien.dataTransfer.files;
          void nap([...tha], lang);
        }}
      >
        <p className="nap__keo">KÉO TỆP VÀO ĐÂY</p>
        <p className="nap__dinh-dang" data-testid="nap-dinh-dang">{DINH_DANG}</p>
      </div>
      <div className="nap__chon">
        <label className="nap__nhan" htmlFor="nap-tep">chọn tệp</label>
        {/* `multiple`: §12.2 đòi nạp 3 tệp CÙNG LÚC. KHÔNG `accept` (xem khối đầu tệp). */}
        <input
          id="nap-tep"
          className="nap__o-tep"
          data-testid="nap-o-tep"
          type="file"
          multiple
          onChange={(suKien) => {
            // ⚠️ COPY `files` RA MẢNG TRƯỚC, rồi mới xoá `value`: xoá `value` làm `FileList` RỖNG
            // đi (`M3` của review).
            const tep = [...(suKien.currentTarget.files ?? [])];
            // ⚠️ RESET `value` (M3): `<input type=file>` chỉ phát `change` khi GIÁ TRỊ ĐỔI, nên
            // chọn LẠI đúng tệp đó sẽ KHÔNG phát sự kiện nào — người dùng không thấy gì xảy ra.
            suKien.currentTarget.value = "";
            datChon(tep);
          }}
        />
        <label className="nap__nhan" htmlFor="nap-tep-lang">ngôn ngữ</label>
        <ChonLang id="nap-tep-lang" lang={lang} onLang={datLang} className="nap__lang" />
        <button
          type="button"
          className="nap__nut"
          data-testid="nap-nut"
          disabled={dangNap || chon.length === 0}
          onClick={() => {
            // ⚠️ XOÁ lựa chọn sau lượt nạp ĐÃ CHẠY (`M3`): giữ `chon` thì nút `nạp` vẫn mở và bấm
            // lần hai là **nạp trùng** cùng tệp (đẻ kênh thứ hai). Lượt bị BỎ QUA thì giữ lại —
            // người dùng còn bấm lại được sau khi lượt đang chạy xong.
            void nap(chon, lang).then((daChay) => {
              if (daChay) datChon([]);
            });
          }}
        >
          nạp
        </button>
      </div>
      {/* SỰ THẬT của lượt đang chuẩn bị: đã chọn tệp nào. Không có nó thì nút `nạp` vô hiệu mà
          không nói vì sao. */}
      <p className="nap__chon-tam" data-testid="nap-da-chon">
        {chon.length === 0
          ? "chưa chọn tệp nào — kéo tệp vào khung hoặc bấm «chọn tệp»"
          : `đã chọn ${chon.length} tệp: ${chon.map((t) => t.name).join(" · ")}`}
      </p>
      {/* `M3`: lượt chọn bị BỎ QUA phải được NÓI RA, không được im lặng. */}
      {boQua !== null ? (
        <p className="nap__bo-qua" data-testid="nap-bo-qua">{boQua}</p>
      ) : null}
      {dangNap ? <p className="nap__cho" data-testid="nap-dang-nap">đang nạp…</p> : null}
      <KetQuaNapList ketQua={ketQua} />
    </div>
  );
}

/**
 * LỐI NẠP **GỌN** ở vùng KÊNH — tồn tại vì §12.2 đòi nạp được tệp thứ 2..N **khi đã có kênh**:
 * lúc đó vùng giữa đang hiện danh sách đoạn (không còn khung §4.2), nên nếu chỉ có khung giữa thì
 * **không còn cửa nào** để thêm tệp.
 *
 * ⚠️ Cùng `napTep` với khung giữa (hook `useNapTep` + hàm của `App`) — lối này KHÔNG tự gọi
 * `uploadSource`, và cũng KHÔNG tự chèn hàng vào state.
 *
 * Ngôn ngữ là một bộ chọn RIÊNG (mặc định `zh`, đúng `DEFAULT_LANG` của backend), không phải
 * trạng thái toàn cục: mỗi LƯỢT nạp có ngôn ngữ của nó (một người dùng nạp tệp tiếng Trung hôm
 * nay và tiếng Anh hôm sau), và `napTep(files, lang)` nhận nó như một THAM SỐ.
 */
export function NhapGon({ napTep }: { napTep: NapTep }) {
  const [lang, datLang] = useState<SourceLang>("zh");
  const { ketQua, dangNap, boQua, nap } = useNapTep(napTep);

  return (
    <div className="ch__nap" data-testid="ch-nap">
      <label className="ch__nap-nhan" htmlFor="ch-nap-tep">nạp tệp</label>
      {/* GỌN: chọn tệp là nạp NGAY (không nút trung gian) — đây là lối cho tệp thứ 2..N. */}
      <input
        id="ch-nap-tep"
        className="ch__nap-o"
        data-testid="ch-nap-o-tep"
        type="file"
        multiple
        onChange={(suKien) => {
          // Cùng `M3` như khung giữa: COPY ra mảng TRƯỚC, rồi XOÁ `value` để mọi lần chọn đều
          // phát `change` (lối này KHÔNG có nút, nên một lượt `change` bị nuốt là KHÔNG có gì xảy ra).
          const tep = [...(suKien.currentTarget.files ?? [])];
          suKien.currentTarget.value = "";
          void nap(tep, lang);
        }}
      />
      {/* Review W2 `M4`: lối gọn TỪNG thiếu nhãn cho bộ chọn ngôn ngữ (khung giữa có) — hai lối
          vào cùng một việc mà một lối không đọc được là sót, không phải chủ ý. */}
      <label className="ch__nap-nhan" htmlFor="ch-nap-lang">ngôn ngữ</label>
      <ChonLang id="ch-nap-lang" lang={lang} onLang={datLang} className="ch__nap-lang" />
      {/* `M3`: lượt chọn bị BỎ QUA phải được NÓI RA, không được im lặng. */}
      {boQua !== null ? (
        <p className="ch__nap-bo-qua" data-testid="ch-nap-bo-qua">{boQua}</p>
      ) : null}
      {dangNap ? <p className="ch__nap-cho">đang nạp…</p> : null}
      <KetQuaNapList ketQua={ketQua} />
    </div>
  );
}
