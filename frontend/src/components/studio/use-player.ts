/**
 * Phát video/âm thanh trên phần tử `<video>` THẬT + đọc dạng sóng âm THẬT.
 *
 * 🔴 NGUỒN GỐC: bản chuyển `_lovable-code/src/components/studio/use-player.ts` (144 dòng).
 * Bản gốc có hai thứ phải đổi, và cả hai đều vì "đo được":
 *
 *  1. **`fakePeaks`** — bản gốc sinh dạng sóng GIẢ từ `SAMPLE_SEGMENTS` khi chưa nạp tệp,
 *     và `decodePeaks` chỉ chạy khi người dùng tự chọn tệp từ máy. Repo thì video đã nằm
 *     trên máy chủ (`/api/media/{source_id}`), nên `decodePeaks` phải chạy được trên URL
 *     đó. Nếu không đọc được thì trả mảng RỖNG — KHÔNG bịa sóng. Một dải thời gian vẽ sóng
 *     giả là một lời nói dối về dữ liệu (cùng lý do `EditScreen` từ chối vẽ vân "nghi ngờ"
 *     khi backend không gửi `suspect`).
 *
 *  2. **`usePlayer` tự giữ `src`** — bản gốc gọi `player.load(f)` với `File` của trình
 *     duyệt. Repo phát từ URL máy chủ, nên `src` là PROP; hook không tự quyết "phát cái gì".
 *
 * ## Vì sao có `loop` là một KHOẢNG, không phải một cờ
 *
 * Bản gốc: `player.setLoop({start, end})` — lặp ĐÚNG một đoạn. Đó là hành vi đúng cho
 * "nghe lại đoạn đang sửa", và nó là thứ người dùng cần khi soát phụ đề. Một cờ `loop`
 * trần chỉ lặp cả tệp, tức không giúp gì cho việc duyệt từng đoạn.
 *
 * ## Vì sao dùng `requestAnimationFrame` chứ không `timeupdate`
 *
 * `timeupdate` bắn ~4 lần/giây (đo được trong Chrome: 250 ms). Đầu phát trên dải thời gian
 * nhảy từng 250 ms trông giật, và phép "đoạn nào đang phát" sẽ trễ tới 1/4 giây — đủ để
 * một dòng phụ đề 0,8 giây KHÔNG BAO GIỜ được tô sáng. `rAF` cho ~60 lần/giây, đúng bằng
 * nhịp vẽ của trình duyệt.
 */
import { useCallback, useEffect, useRef, useState } from "react";

/** Số mẫu sóng mặc định — 2 400 mẫu cho ~2 200 px bề rộng dải (đo trên bản đã duyệt). */
export const SO_SONG = 2400;

export interface DoanLap {
  start: number;
  end: number;
}

export interface Player {
  /** Phần tử `<video>` — gắn vào `ref` của thẻ. */
  videoRef: React.RefObject<HTMLVideoElement | null>;
  /** Đang phát hay không (theo SỰ KIỆN của phần tử, không theo ý định của người dùng). */
  playing: boolean;
  /** Vị trí đầu phát, giây. Cập nhật theo `requestAnimationFrame`. */
  time: number;
  /** Tổng dài tệp, giây. `0` khi chưa biết (chưa `loadedmetadata`). */
  duration: number;
  /** Đoạn đang lặp, hoặc `null`. */
  loop: DoanLap | null;
  toggle: () => void;
  play: () => void;
  pause: () => void;
  seek: (t: number) => void;
  setLoop: (d: DoanLap | null) => void;
}

/**
 * Đọc dạng sóng âm của một URL bằng `AudioContext.decodeAudioData`.
 *
 * Trả `number[]` độ dài `soMau`, mỗi phần tử ∈ [0, 1] = biên độ đỉnh của lát đó.
 * ⚠️ Trả MẢNG RỖNG khi không đọc được (CORS, định dạng lạ, `AudioContext` không có) —
 * người gọi phải vẽ "chưa có sóng", không được bịa.
 *
 * ⚠️ `AudioContext` phải `close()` sau khi dùng: mỗi `AudioContext` giữ một luồng âm thanh
 * của hệ điều hành, và để rò 6 cái (một lần đổi kênh × 6) là mất tiếng trên Windows.
 */
export async function docSong(url: string, soMau: number = SO_SONG): Promise<number[]> {
  const Ctx: typeof AudioContext | undefined =
    typeof window === "undefined"
      ? undefined
      : window.AudioContext ?? (window as unknown as { webkitAudioContext?: typeof AudioContext }).webkitAudioContext;
  if (Ctx === undefined) return [];
  let ctx: AudioContext | null = null;
  try {
    const tra = await fetch(url);
    if (!tra.ok) return [];
    const dem = await tra.arrayBuffer();
    ctx = new Ctx();
    const am = await ctx.decodeAudioData(dem);
    // Gộp mọi kênh thành MỘT dãy đỉnh: dải thời gian chỉ có một hàng sóng, và một kênh
    // phải toàn số 0 thì kênh kia vẫn phải hiện ra.
    const kenh = am.numberOfChannels;
    const dai = am.length;
    const buoc = Math.max(1, Math.floor(dai / soMau));
    const ra: number[] = [];
    const duLieu: Float32Array[] = [];
    for (let c = 0; c < kenh; c++) duLieu.push(am.getChannelData(c));
    for (let m = 0; m < soMau; m++) {
      const dau = m * buoc;
      const cuoi = Math.min(dai, dau + buoc);
      let dinh = 0;
      for (let c = 0; c < kenh; c++) {
        const k = duLieu[c];
        for (let j = dau; j < cuoi; j++) {
          const v = Math.abs(k[j]);
          if (v > dinh) dinh = v;
        }
      }
      ra.push(dinh);
    }
    return ra;
  } catch {
    return [];
  } finally {
    if (ctx !== null) void ctx.close();
  }
}

/**
 * Hook phát. `src` là PROP — hook KHÔNG tự quyết phát cái gì (xem khối đầu tệp, mục 2).
 *
 * ⚠️ `duration` lấy từ `loadedmetadata` của CHÍNH phần tử, không từ `Source.duration`
 * của máy chủ: hai con số có thể lệch (máy chủ đo bằng `ffprobe` trên tệp gốc, trình duyệt
 * đo trên luồng nó giải mã được), và đầu phát phải nằm trong hệ toạ độ của trình duyệt —
 * nếu không, tua tới `duration` của máy chủ có thể vượt quá cuối tệp thật.
 */
export function usePlayer(src: string | null): Player {
  const videoRef = useRef<HTMLVideoElement | null>(null);
  const [playing, setPlaying] = useState(false);
  const [time, setTime] = useState(0);
  const [duration, setDuration] = useState(0);
  const [loop, datLoop] = useState<DoanLap | null>(null);

  // `loop` đọc trong vòng `rAF` — phải là ref, nếu không vòng lặp bị dựng lại mỗi lần đổi
  // đoạn lặp và sẽ có một khung hình dùng giá trị cũ.
  const loopRef = useRef<DoanLap | null>(null);
  loopRef.current = loop;

  const play = useCallback(() => {
    const v = videoRef.current;
    if (v === null) return;
    // `play()` trả Promise bị từ chối khi trình duyệt chặn tự phát (chính sách autoplay).
    // Bắt lỗi để không có "unhandled rejection" trong console — người dùng vẫn thấy nút
    // `Phát` ở trạng thái chưa phát, đó là sự thật.
    void v.play().catch(() => undefined);
  }, []);

  const pause = useCallback(() => {
    videoRef.current?.pause();
  }, []);

  const toggle = useCallback(() => {
    const v = videoRef.current;
    if (v === null) return;
    if (v.paused) void v.play().catch(() => undefined);
    else v.pause();
  }, []);

  const seek = useCallback((t: number) => {
    const v = videoRef.current;
    if (v === null) return;
    const tran = Number.isFinite(v.duration) ? v.duration : t;
    v.currentTime = Math.min(Math.max(0, t), Math.max(0, tran));
    setTime(v.currentTime);
  }, []);

  const setLoop = useCallback((d: DoanLap | null) => {
    datLoop(d);
  }, []);

  // Gắn sự kiện của phần tử. `playing` theo SỰ KIỆN (`play`/`pause`), không theo ý định —
  // nhờ vậy khi trình duyệt chặn tự phát, giao diện nói đúng "chưa phát".
  useEffect(() => {
    const v = videoRef.current;
    if (v === null) return;
    const onPlay = () => setPlaying(true);
    const onPause = () => setPlaying(false);
    const onMeta = () => {
      setDuration(Number.isFinite(v.duration) ? v.duration : 0);
      setTime(v.currentTime);
    };
    const onTime = () => setTime(v.currentTime);
    const onEnded = () => setPlaying(false);
    v.addEventListener("play", onPlay);
    v.addEventListener("pause", onPause);
    v.addEventListener("loadedmetadata", onMeta);
    v.addEventListener("durationchange", onMeta);
    v.addEventListener("timeupdate", onTime);
    v.addEventListener("ended", onEnded);
    // Nếu `src` đã sẵn sàng TRƯỚC khi effect này chạy (tệp trong cache), `loadedmetadata`
    // đã bắn rồi và sẽ không bắn lại ⇒ đọc trực tiếp một lần.
    if (v.readyState >= 1) onMeta();
    return () => {
      v.removeEventListener("play", onPlay);
      v.removeEventListener("pause", onPause);
      v.removeEventListener("loadedmetadata", onMeta);
      v.removeEventListener("durationchange", onMeta);
      v.removeEventListener("timeupdate", onTime);
      v.removeEventListener("ended", onEnded);
    };
  }, [src]);

  // Vòng `rAF`: cập nhật `time` mỗi khung hình và THI HÀNH đoạn lặp.
  useEffect(() => {
    if (!playing) return;
    let huy = false;
    let ma = 0;
    const buoc = () => {
      if (huy) return;
      const v = videoRef.current;
      if (v !== null) {
        const d = loopRef.current;
        if (d !== null && (v.currentTime >= d.end || v.currentTime < d.start - 0.25)) {
          v.currentTime = d.start;
        }
        setTime(v.currentTime);
      }
      ma = requestAnimationFrame(buoc);
    };
    ma = requestAnimationFrame(buoc);
    return () => {
      huy = true;
      cancelAnimationFrame(ma);
    };
  }, [playing]);

  // Đổi `src` ⇒ đầu phát về 0 và dừng. Không làm thì `time` của tệp CŨ còn nằm trên dải
  // của tệp MỚI — đúng lớp lỗi "hiện dữ liệu kênh A trong khung kênh B".
  useEffect(() => {
    setTime(0);
    setDuration(0);
    setPlaying(false);
    datLoop(null);
  }, [src]);

  return { videoRef, playing, time, duration, loop, toggle, play, pause, seek, setLoop };
}
