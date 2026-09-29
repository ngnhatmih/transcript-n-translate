/**
 * Thanh TRANSPORT — nut phat, timecode mono, track co dau doc, ba nut xuat (spec UI §4.1).
 *
 * Tieu chi cua task nay khong chi la "co mot thanh o day": phat toi **moc cuoi cua
 * doan** thi **tu nhay sang doan ke**. Cu nhay do nam trong `src/lib/playback.ts`
 * (ham thuan, ghim bang `node:test` thuong); tep nay chi NOI DAY: gan `timeupdate`,
 * goi ham thuan, roi dat lai vi tri phat.
 *
 * ⚠️ He qua cua CUNG mot quy tac, do duoc trong luc viet test: vi tri phat VUOT
 * `segment.end` (vi du `currentSegment` con la doan cu) ⇒ lan `timeupdate` ke tiep dat
 * lai vi tri ve `start` cua doan KE, ke ca khi do la mot buoc LUI. Do la chu "tu nhay
 * doan" chu khong phai loi, nhung no chi dung khi `currentSegment` duoc cap nhat theo
 * nguoi dung. ⚠️ CAU CU O DAY ("viec do thuoc ve duong CHON DOAN (Task 11), chua co o
 * day") NAY SAI: Task 11 da noi duong do qua BAN PHIM — `J`/`K` (dong truoc / dong sau,
 * spec UI §5.1) va `N` (doan nghi ngo ke tiep) dispatch `setCurrentSegment` tu `App`.
 *
 * ## `ponytail:` TRAN — dung phan tu media GOC, khong dung player library
 *
 * `<audio>` la phan tu goc cua trinh duyet va backend da phuc vu `Range`
 * (`backend/app/api/routes_media.py`: 206 + `Content-Range`, doc theo khoi 256 KB),
 * nen moi thu "tua" la cua trinh duyet. Mot player library se mang theo mot tang
 * trang tri, mot API thu hai va mot he CSS thu hai — doi lai khong co gi cho tieu chi
 * nay. TRAN: **`<video>` thi khong co khung hinh rieng** — nguon video duoc phat bang
 * chinh `<audio>` nay (trinh duyet van phat duoc vet tieng cua mp4), nen nguoi dung
 * khong NHIN thay hinh. Duong nang cap: doi the theo duoi `media_path` cua `Source`
 * (`.mp4/.mkv/.webm` ⇒ `<video>`) va them mot khung hinh — ca hai deu phai do tren
 * trinh duyet THAT.
 *
 * ## `ponytail:` TRAN — cai KHONG do duoc o moi truong nay
 *
 * **jsdom KHONG hien thuc `play()`/`pause()`** (do duoc o `Transport.test.tsx`: chung
 * log `Not implemented: HTMLMediaElement's play() method` va `play()` tra `undefined`
 * chu khong phai Promise), khong co layout va khong ap CSS. ⇒ **"seek trong trinh
 * duyet that" CHUA CHUNG MINH** o bat ky dau trong giao dien; thu duy nhat duoc do la
 * phia MAY CHU (HTTP `Range` ⇒ 206), va no nam o bao cao task. Bon thu duoc do o day
 * la HANH VI: cai gi co trong DOM, lop nao, chu nao, va `style.left` nao.
 *
 * ## Trang thai: vi sao `playing`/`currentSegment` la PROP
 *
 * Trang thai client cua ban lam viec nam trong MOT reducer (`src/state/reducer.ts`:
 * `playing`, `currentSegment`), nen thanh nay la component DIEU KHIEN: no khong giu
 * ban sao thu hai cua "dang phat hay khong". Rieng **vi tri phat (giay)** la trang
 * thai CUC BO — `UiState` khong co truong giay nao, va `timeupdate` ban ra ~4 lan/giay
 * nen keo no vao reducer la mot luong action khong ai doc.
 *
 * ## Duong CHON KENH nay DA CO (Task W1) — va vi tri phat thi chua
 *
 * Vung KENH (Task 4) truoc day moi CHI HIEN kenh; Task W1 them duong CHON kenh, nen `App`
 * truyen `sourceId={ui.channelId}` + `segments` + `duration` + `translationId` THAT. Truoc
 * do bon prop do luon `null`/`[]` ⇒ nut phat VO HIEU, khong `src`, ba nut xuat khong `href`.
 *
 * ⚠️ NHUNG vi tri phat (`viTriPhat`) la state CUC BO, nen khi `sourceId` doi no KHONG tu
 * biet ⇒ dau doc giu vi tri cua kenh CU. Do la NO `M5` cua Task 7 (hom do chua voi toi
 * duoc vi chua co duong chon kenh) va W1 dong no bang MOT effect reset — xem "DOI KENH"
 * ngay duoi phan khai bao state.
 */
import { useEffect, useRef, useState } from "react";
import type { SyntheticEvent } from "react";

import { endpoints } from "../api/endpoints.ts";
import type { ExportFormat } from "../api/endpoints.ts";
import type { Segment } from "../api/types.ts";
import { nextSegmentAfter, readheadPercent } from "../lib/playback.ts";
import { formatTimecode } from "../lib/timecode.ts";

/**
 * Ba dinh dang xuat cua spec §11, theo THU TU hien thi.
 *
 * Ten dinh dang la du lieu cua `pipeline/export.py::FORMATS`; o day chi la NHAN.
 * URL khong duoc ghep tai cho — xem `endpoints.exportUrl` (route `format` sai ten la 422).
 */
const DINH_DANG_XUAT: ReadonlyArray<{ dinhDang: ExportFormat; nhan: string }> = [
  { dinhDang: "srt", nhan: "SRT" },
  { dinhDang: "vtt", nhan: "VTT" },
  { dinhDang: "ass", nhan: "ASS" },
];

/** Chuoi thay cho tong thoi luong khi chua biet (`Source.duration === null`). */
export const CHUA_BIET_THOI_LUONG = "--:--.--";

/** Giay HUU HAN va khong am: `currentTime` cua trinh duyet co the la `NaN` khi chua nap xong. */
function giayAnToan(giay: number): number {
  return Number.isFinite(giay) && giay > 0 ? giay : 0;
}

export interface TransportProps {
  /** Id `sources` dang chon; `null` = chua chon kenh (xem NO o dau tep). */
  sourceId: number | null;
  /** Doan cua ban ghi dang mo — nguon cua "moc cuoi cua doan". */
  segments: Segment[];
  /**
   * **BẢN DỊCH ĐANG XEM** — CÙNG MỘT BIỂU THỨC với `CompareScreen.macDinhId` (bat bien `I2`
   * cua review W3, ERRATA #36 muc 4), do `App` tra loi MOT lan.
   *
   * ⚠️ Trước vòng sửa, prop này là `banDichXuat.id` (`status === "done"` mới nhất): hai
   * vùng tiêu thụ đọc HAI biểu thức khác nhau, nên vùng Đối chiếu có thể đang xem bản `13`
   * (`queued`) trong khi ba nút xuất trỏ bản `11` — và **không chữ nào** trên màn nói bản nào
   * sẽ được xuất. Mutant `W3-17` (đổi prop này sang biến kia) từng cho **0 bài đỏ**.
   */
  translationId: number | null;
  /**
   * Bản dịch SẼ ĐƯỢC XUẤT — câu trả lời cho một câu hỏi KHÁC: *"bản nào có nội dung để xuất"*.
   *
   * ⚠️ Đây KHÔNG phải điểm quyết định thứ hai cho "bản dịch đang xem" (điểm đó là
   * `translationId`, và nó có bài ghim `SAME`). Nó được **BÊN GỌI** (`App`) quyết theo một luật
   * đã đo được: **bản đang xem đã `done` ⇒ xuất CHÍNH NÓ**; ngược lại mới lấy bản `done` mới nhất.
   * Nhờ vậy `exportableId !== translationId` chỉ còn **MỘT** nghĩa: bản đang xem **CHƯA** dịch xong.
   *
   * ⚠️ MẶC ĐỊNH là `translationId` (không phải `null`): không truyền prop này thì hành vi
   * **y hệt trước vòng sửa** — "bản đang xem cũng là bản xuất được". Đó là điều kiện để 12
   * bài sẵn có của tệp này (`Transport.test.tsx`) vẫn đo đúng cái chúng đo, thay vì bị đổi
   * nghĩa âm thầm thành "không xuất được gì".
   */
  exportableId?: number | null;
  /**
   * CÂU NÓI RA khi ba nút xuất trỏ vào một bản KHÁC bản đang xem — **do `App` quyết** (MỘT
   * nguồn quyết định), `Transport` chỉ render.
   *
   * ⚠️ VÌ SAO KHÔNG TỰ DỰNG CÂU Ở ĐÂY (vòng sửa W3 #2, `Important` F2): thanh này KHÔNG nhận
   * `status` của bản đang xem, nên nó không phân biệt được hai lý do của sự lệch id — và bản cũ
   * đã in ra một câu **SAI SỰ THẬT** (`"bản đang xem (11) chưa dịch xong — xuất bản 13"` trong khi
   * 11 đã `done`). Câu chỉ được nói khi bản đang xem THẬT SỰ chưa `done`, và điều kiện đó chỉ đọc
   * được ở nơi có `status` (`App`).
   */
  xuatCho?: string | null;
  /** Thoi luong that cua nguon (`Source.duration`), `null` khi backend chua do duoc. */
  duration?: number | null;
  /** `UiState.playing` — component DIEU KHIEN, khong giu ban sao. */
  playing?: boolean;
  /** `UiState.currentSegment` — doan dang phat, `null` = khong phat doan nao. */
  currentSegment?: number | null;
  /** Xuat kem ban goc (`exportUrl(..., bilingual)`); backend nhan `int` 0/1. */
  bilingual?: boolean;
  /** Yeu cau doi trang thai phat — BEN GOI giu su that (reducer). */
  onPlayingChange?: (playing: boolean) => void;
  /** Bao da nhay sang doan `i` — BEN GOI ghi lai vao `UiState.currentSegment`. */
  onSegmentChange?: (i: number) => void;
  /**
   * BÁO VỊ TRÍ ĐẦU ĐỌC (giây) cho `App` — thanh này là nơi DUY NHẤT chạm `currentTime` của phần
   * tử media.
   *
   * ⚠️ VÌ SAO `App` CẦN (Task 11): `[`/`]` = **đặt mốc start/end TẠI ĐẦU ĐỌC** (spec UI §5.1 dòng
   * 296 + §5.2 dòng 310) — muốn vậy phải có `media.currentTime`, mà phần tử media sống ở ĐÂY.
   * `App` giữ nó trong một `useRef` (KHÔNG phải `useState`): `timeupdate` bắn ~4 lần/giây, và một
   * luồng action vào reducer cho mỗi nhịp là một đường không ai đọc (cùng lý do `viTriPhat` ở đây
   * là state CỤC BỘ).
   *
   * ⚠️ TRẦN đã khai: giá trị `App` giữ là nhịp `timeupdate` **GẦN NHẤT** (≤250 ms cũ), KHÔNG phải
   * một lần đọc `currentTime` ĐỒNG BỘ lúc bấm phím. Đường đồng bộ tuyệt đối sẽ là một tham chiếu
   * thứ hai tới chính phần tử media (hai đường vào cùng một dữ liệu), và jsdom không có audio để
   * đo cái nào đúng — nên nó được KHAI ra thay vì thêm vào. Chưa phát lần nào ⇒ đầu đọc là 0, tức
   * đúng `currentTime` ban đầu của phần tử.
   */
  onDauDoc?: (giay: number) => void;
  /**
   * YÊU CẦU **NGHE LẠI QUANH MỐC VỪA NUDGE** (spec UI §5.2 dòng 309: *"mỗi lần nudge phát lại
   * 300ms quanh mốc mới để nghe ngay"*) — do `App` phát ra SAU khi lệnh ghi đã được máy chủ nhận.
   *
   * ⚠️ VÌ SAO LÀ PROP chứ không phải một hàm `App` gọi vào: phần tử media sống Ở ĐÂY, và `App`
   * không được giữ một tham chiếu thứ hai tới nó (hai đường vào cùng một dữ liệu). `App` nói
   * *"nghe lại quanh mốc này"*, `Transport` quyết CÁCH (tua + `play()` + dừng sau 300 ms).
   *
   * ⚠️ `lan` (số thứ tự yêu cầu) là một phần của HỢP ĐỒNG, không phải trang trí: hai yêu cầu cùng
   * `giay` vẫn phải là hai yêu cầu (xem `App.datNgheLai`).
   */
  ngheLai?: { giay: number; lan: number } | null;
}

/**
 * ĐỘ DÀI cửa sổ nghe lại sau một lần nudge — **300 ms**, nguyên văn spec UI §5.2 dòng 309.
 *
 * Xuất ra để bài test nói được "300 ms" bằng CHÍNH hằng số của sản phẩm thay vì chép lại con số
 * (hai bản chép tay sẽ trôi khỏi nhau). Bài test KHÔNG chờ bằng `sleep`: nó chờ TÍN HIỆU
 * (`data-nghe-lai` mở rồi đóng + `pause()` được gọi), deadline chỉ là TRẦN — ERRATA #35/#38/#39.
 */
export const NGHE_LAI_MS = 300;

export function Transport({
  sourceId,
  segments,
  translationId,
  exportableId,
  xuatCho = null,
  duration = null,
  playing = false,
  currentSegment = null,
  bilingual = false,
  onPlayingChange,
  onSegmentChange,
  onDauDoc,
  ngheLai = null,
}: TransportProps) {
  // Xem ghi chu o `TransportProps.exportableId`: khong truyen ⇒ "ban dang xem la ban xuat duoc".
  const idXuatDuoc = exportableId === undefined ? translationId : exportableId;
  const phanTuMedia = useRef<HTMLAudioElement | null>(null);
  // Vi tri phat: trang thai CUC BO (xem "Trang thai" o dau tep).
  const [viTriPhat, datViTriPhat] = useState(0);
  // Da tung YEU CAU phat chua. Dung de KHONG goi `pause()` luc mount: mot lan goi
  // `pause()` tren phan tu vua dung la mot loi im lang, va duoi jsdom no do
  // "Not implemented" ra `console.error` — thu ma `App.test.tsx` ghim la khong duoc co.
  const daPhat = useRef(false);

  /**
   * CỬA SỔ NGHE LẠI đang MỞ hay không (sau một lần nudge) — trạng thái CỤC BỘ, và nó được PHƠI RA
   * DOM (`data-nghe-lai` trên phần tử media) vì đây là **tín hiệu kết thúc** của một khoảng thời
   * gian: bài test cần một TÍN HIỆU để chờ, không phải một `sleep` (ERRATA #35 mục 2: điều kiện
   * thoát là hàm của ĐỒNG HỒ thì luôn trở thành đúng, nên nó không chứng minh gì).
   */
  const [dangNgheLai, datDangNgheLai] = useState(false);
  /**
   * `playing` của LƯỢT RENDER NÀY, đọc được từ trong một callback của `setTimeout`.
   *
   * ⚠️ Gán trong THÂN render, KHÔNG trong effect: callback của hẹn giờ chạy ở một lượt SAU, và giá
   * trị nó cần là giá trị MỚI NHẤT (cùng lý do `App.banGhiMoiNhat` — ERRATA #46 mục 10b).
   */
  const playingRef = useRef(playing);
  playingRef.current = playing;

  const coNguon = sourceId !== null;
  /** Thoi luong dung duoc: `null`/`0`/khong huu han deu la "chua biet" (xem `readheadPercent`). */
  const tongThoiLuong =
    duration !== null && Number.isFinite(duration) && duration > 0 ? duration : null;

  /**
   * DOI KENH ⇒ vi tri phat cua kenh CU phai bi XOA (no cua Task 7, `M5`).
   *
   * `viTriPhat` la state CUC BO (xem "Trang thai" o dau tep), nen no khong tu biet rang
   * `sourceId` vua doi: khong co effect nay thi dau doc dung nguyen cho cua kenh truoc, va
   * timecode doc ra mot vi tri KHONG thuoc kenh nao ca.
   *
   * ⚠️ Vi sao khong can mot co che DUNG thu hai: `selectChannel` cua reducer da dat
   * `playing = false` (`state/reducer.ts`), nen effect phat ngay duoi day thay
   * `playing !== daPhat.current` va tu goi `el.pause()` dung MOT lan. Them mot lan
   * `pause()` nua o day la co che dung thu hai — va o lan MOUNT (chua co gi de dung) no
   * con do "Not implemented" ra `console.error`, thu ma `App.test.tsx` ghim la khong duoc co.
   * `datViTriPhat(0)` luc mount la mot phep gan vo hai (React bo qua khi gia tri khong doi).
   */
  useEffect(() => {
    datViTriPhat(0);
  }, [sourceId]);

  useEffect(() => {
    const el = phanTuMedia.current;
    if (el === null || sourceId === null) return;
    if (playing === daPhat.current) return;
    daPhat.current = playing;
    if (playing) {
      // `play()` tra Promise o trinh duyet THAT va `undefined` o jsdom ⇒ `Promise.resolve`
      // cho ca hai duong cung chay, va loi tu choi (autoplay) tra trang thai ve BEN GOI.
      Promise.resolve(el.play()).catch(() => onPlayingChange?.(false));
    } else {
      el.pause();
    }
  }, [playing, sourceId, onPlayingChange]);

  /**
   * **NGHE LẠI QUANH MỐC MỚI SAU MỘT LẦN NUDGE** — spec UI §5.2 dòng 309: *"mỗi lần nudge phát lại
   * 300ms quanh mốc mới để nghe ngay"*. Vòng sửa 1 của Task 11 HIỆN THỰC nó (`I-3`): trước đó hành
   * vi này được khai TRẦN với lý do SAI (*"jsdom không hiện thực `play()`"* — điều đó chặn việc
   * NGHE, không chặn việc GHIM: chính `App.test.tsx` đã bịt `play()`/`pause()` để tắt tiếng ồn,
   * nên một spy đếm được lời gọi).
   *
   * Ba vế của một cửa sổ nghe lại:
   *  1. **TUA** đầu đọc tới mốc mới (mốc do `App` chốt từ CHÍNH đoạn nó đã gửi lên máy chủ);
   *  2. **PHÁT** (`play()`);
   *  3. **DỪNG sau `NGHE_LAI_MS`** — nhưng CHỈ khi người dùng không đang phát: một cú nudge trong
   *     lúc đang nghe không được CẮT việc đang nghe (`ui.playing` vẫn `true`, và nút phát vẫn nói
   *     đúng). Yêu cầu mới (nudge tiếp) huỷ hẹn giờ CŨ và mở lại cửa sổ từ mốc MỚI NHẤT.
   *
   * ⚠️ HAI ĐIỀU NÓI RA THAY VÌ GIẤU: (a) ĐÂY KHÔNG PHẢI nguồn sự thật thứ hai của `playing`: cửa
   * sổ nghe lại KHÔNG đi qua reducer, vì đưa nó qua đó nghĩa là mỗi cú nudge `dispatch(setPlaying)`
   * — và ở vế "đang phát" nó sẽ DỪNG việc người dùng đang nghe, còn ở vế "đang dừng" nút phát sẽ
   * nhấp nháy theo một đoạn 300 ms. Hệ quả đã biết: trong 300 ms đó phần tử media đang phát trong
   * khi `ui.playing === false` — một lệch TẠM THỜI, có chủ ý, và nó tự hết ở vế (3). (b) `jsdom`
   * không có âm thanh: thứ đo được ở đây là `play()`/`pause()`/`currentTime`, không phải TIẾNG.
   */
  useEffect(() => {
    if (ngheLai === null) return;
    const el = phanTuMedia.current;
    if (el === null) return;
    const giay = giayAnToan(ngheLai.giay);
    el.currentTime = giay;
    datViTriPhat(giay);
    datDangNgheLai(true);
    // `play()` trả Promise ở trình duyệt THẬT và `undefined` ở jsdom ⇒ cùng cách xử lý như effect
    // phát/tạm dừng ở trên; lỗi từ chối (autoplay) không được thành một `unhandledRejection`.
    Promise.resolve(el.play()).catch(() => {});
    const hen = setTimeout(() => {
      if (!playingRef.current) el.pause();
      datDangNgheLai(false);
    }, NGHE_LAI_MS);
    return () => clearTimeout(hen);
  }, [ngheLai]);

  /**
   * `timeupdate` cua phan tu media — DAY NOI duy nhat cua "tu nhay doan".
   *
   * Quyet dinh nam o `nextSegmentAfter` (ham thuan); o day chi con ba buoc: doc vi tri
   * THAT tu phan tu, hoi ham thuan, roi dat lai vi tri phat ve `start` cua doan ke.
   * Buoc thu ba moi la CU NHAY: khoang lang giua hai doan bi bo qua, thay vi de
   * phan tu phat het khoang do roi moi "phat hien" doan sau.
   */
  function khiThoiGian(suKien: SyntheticEvent<HTMLAudioElement>): void {
    const el = suKien.currentTarget;
    const giay = giayAnToan(el.currentTime);
    datViTriPhat(giay);
    // BÁO LÊN `App` đầu đọc GẦN NHẤT (`[`/`]` đặt mốc tại đây — xem `TransportProps.onDauDoc`).
    onDauDoc?.(giay);

    const ke = nextSegmentAfter(giay, segments, currentSegment);
    // Kiem lai bang SO: `segments[ke] === undefined` la mot phep so sanh ma kieu o day
    // khong cho phep (`noUncheckedIndexedAccess` khong bat), nhung bien `ke` thi kiem duoc.
    if (ke === null || ke >= segments.length) return;

    el.currentTime = segments[ke].start;
    datViTriPhat(giayAnToan(segments[ke].start));
    onSegmentChange?.(ke);
  }

  const nhan = playing ? "tạm dừng" : "phát";

  return (
    <div className="tp">
      {/* Phan tu media GOC: `src` chi duoc dat khi CO nguon — mot `src` tro vao
          `/api/media/null` la mot request 422 ma khong ai doc. `src` tuong doi vi
          trinh duyet di qua proxy 3100 (xem `endpoints.mediaUrl`). */}
      <audio
        ref={phanTuMedia}
        className="tp__media"
        src={sourceId === null ? undefined : endpoints.mediaUrl(sourceId)}
        onTimeUpdate={khiThoiGian}
        /* TÍN HIỆU KẾT THÚC của cửa sổ nghe lại (xem `dangNgheLai`): bài test chờ nó ĐÓNG, không
           chờ đồng hồ. Vắng mặt khi không có cửa sổ nào đang mở (`undefined` ⇒ React bỏ thuộc tính). */
        data-nghe-lai={dangNgheLai ? "1" : undefined}
      />
      <button
        type="button"
        className="tp__phat"
        aria-pressed={playing}
        disabled={!coNguon}
        onClick={() => onPlayingChange?.(!playing)}
      >
        {nhan}
      </button>
      {/* Timecode mono `0:04.12 / 12:04.30` (spec UI §4.1). Tong so lay tu BACKEND
          (`Source.duration`), khong do lai tu phan tu media: `duration` cua phan tu la
          `NaN` cho tới khi tai xong metadata, va client do lai la hai nguon su that. */}
      <span className="tp__timecode">
        {`${formatTimecode(viTriPhat)} / ${
          tongThoiLuong === null ? CHUA_BIET_THOI_LUONG : formatTimecode(tongThoiLuong)
        }`}
      </span>
      {/* Track + dau doc: HINH THUC trang tri — thong tin nam o timecode (chu), khong
          chi o vi tri (spec UI §7). Luat CSS that nam o `app.css` va duoc ghim bang
          mot bai test DOC tep do (ERRATA #15 muc 3). */}
      <div className="tp__track" aria-hidden>
        <div
          className="tp__readhead"
          style={{ left: `${readheadPercent(viTriPhat, tongThoiLuong)}%` }}
        />
      </div>
      {coNguon ? null : <p className="tp__rong">chưa chọn kênh để nghe</p>}
      {/* ⚠️ BẢN ĐANG XEM ≠ BẢN XUẤT ĐƯỢC ⇒ phải NÓI RA (bat bien `I2`, ERRATA #36 muc 4).
          Sau khi bấm "dịch", bản đang xem là bản VỪA TẠO (`queued`, chưa có đoạn nào) nên
          nó KHÔNG có nội dung để xuất. Im lặng cho ba nút trỏ vào bản `done` khác chính là
          lỗi mà `W3-17` để lọt: người dùng không có câu nào nói bản nào sẽ được xuất.
          ⚠️ CÂU do `App` quyết (`xuatCho`), KHÔNG dựng ở đây: thanh này không nhận `status` của
          bản đang xem nên bản cũ đã nói NGƯỢC sự thật khi bản đang xem ĐÃ `done` mà không phải
          bản `done` mới nhất (probe `RR-PROBE-2`, vòng sửa W3 #2). Không có gì để nói ⇒ `null`. */}
      {xuatCho === null ? null : (
        <p className="tp__xuat-cho" data-testid="xuat-cho">{xuatCho}</p>
      )}
      <div className="tp__nhom-xuat">
        {DINH_DANG_XUAT.map(({ dinhDang, nhan: nhanXuat }) => (
          <a
            key={dinhDang}
            className="tp__xuat"
            aria-label={`xuất ${nhanXuat}`}
            aria-disabled={idXuatDuoc === null ? "true" : undefined}
            // ⚠️ `data-translation-id` la `token` MAY DOC DUOC cua bat bien `I2`: no la CHINH
            // gia tri `translationId` (ban dang xem), de bai `SAME` trong `App.test.tsx` so
            // duoc no voi ban ma vung Doi chieu dang chon — hai con so, mot bieu thuc.
            data-translation-id={translationId === null ? "" : String(translationId)}
            // URL do `endpoints.exportUrl` sinh ra: client KHONG tu ghep, vi `format`
            // sai ten la 422 va thu tu tham so la chuyen cua backend.
            href={
              idXuatDuoc === null
                ? undefined
                : endpoints.exportUrl(idXuatDuoc, dinhDang, bilingual)
            }
            download
          >
            {nhanXuat}
          </a>
        ))}
      </div>
    </div>
  );
}
