import { useCallback, useEffect, useRef, useState } from "react";

/**
 * ĐỒNG HỒ PHÁT — nạp thẳng URL media của máy chủ.
 *
 * 🔴 NGUỒN GỐC: `_lovable-code/src/components/studio/use-player.ts` (144 dòng).
 *
 * ## Ba thay đổi, và vì sao mỗi thay đổi là BẮT BUỘC
 *
 *  1. **Nhận `media: string | null` thay vì `fallbackDuration: number`.**
 *     Bản gốc nhận một ĐỘ DÀI MẪU (`SAMPLE_DURATION = 55`) rồi tự chạy đồng hồ mô
 *     phỏng khi chưa có tệp. Ở đây độ dài là số ĐO của trình duyệt trên tệp thật
 *     (`loadedmetadata`), và trước khi có nó thì `duration = 0` — "chưa biết",
 *     KHÔNG phải "55 giây". Bịa một độ dài làm thanh thời gian vẽ đúng chiều rộng
 *     của một con số không có thật.
 *
 *  2. **Không còn `load(file)` tạo blob URL.** URL đã có sẵn từ `mediaUrl(sourceId)`
 *     (`/api/media/{id}`), và backend phục vụ `Range` nên trình duyệt tự seek được.
 *     Tạo blob là tải cả tệp vào bộ nhớ lần nữa — với một video 238 MB thì đó là
 *     một bản sao thừa.
 *
 *  3. **Không còn `fakePeaks`.** Hàm đó sinh sóng từ 18 đoạn mẫu; dải thời gian
 *     hoặc vẽ sóng của tệp đang mở, hoặc để trống. Vẽ một hình ngẫu nhiên trông
 *     như sóng âm là nói dối về dữ liệu.
 *
 * ⚠️ Đồng hồ mô phỏng được GIỮ NGUYÊN: khi `src === null` mà người dùng bấm Phát,
 * vẫn có một đầu phát chạy để xem dải thời gian, và nó KHÔNG tuyên bố là đang phát
 * tệp nào. Đó là hành vi của bản gốc, không phải dữ liệu bịa.
 */
export function usePlayer(media: string | null, giongLong: string | null = null) {
  const videoRef = useRef<HTMLVideoElement | null>(null);
  //: Lớp ÂM của bản lồng tiếng — phát ĐÈ lên hình gốc, hình không đổi.
  const audioRef = useRef<HTMLAudioElement | null>(null);
  const [src, setSrc] = useState<string | null>(null);
  const [time, setTime] = useState(0);
  const [playing, setPlaying] = useState(false);
  const [duration, setDuration] = useState(0);
  const loopRef = useRef<{ start: number; end: number } | null>(null);
  const [loop, setLoopState] = useState<{ start: number; end: number } | null>(null);
  const timeRef = useRef(0);

  const setLoop = useCallback((l: { start: number; end: number } | null) => {
    loopRef.current = l;
    setLoopState(l);
  }, []);

  /**
   * `media` (URL của máy chủ) → `src` của thẻ `<video>`.
   *
   * `null` = chưa chọn kênh ⇒ `src = null`, và đồng hồ về 0 để trình phát KHÔNG
   * giữ tệp của kênh trước. Không revoke gì: đây không phải blob URL.
   */
  useEffect(() => {
    setSrc(media);
    setPlaying(false);
    timeRef.current = 0;
    setTime(0);
    setDuration(0);
  }, [media]);

  // Đồng hồ mô phỏng — chỉ chạy khi KHÔNG có tệp.
  useEffect(() => {
    if (src !== null || !playing) return;
    let raf = 0;
    let last = performance.now();
    const tick = (now: number) => {
      let t = timeRef.current + (now - last) / 1000;
      last = now;
      const l = loopRef.current;
      if (l !== null && t >= l.end) t = l.start;
      // `duration === 0` là "chưa biết" — không cắt đồng hồ ở 0.
      if (duration > 0 && t >= duration) {
        t = duration;
        setPlaying(false);
      }
      timeRef.current = t;
      setTime(t);
      raf = requestAnimationFrame(tick);
    };
    raf = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(raf);
  }, [src, playing, duration]);

  // Đồng hồ THẬT — đọc `currentTime`/`duration` của thẻ video.
  //
  // 🔴 SỬA MỘT LỖI ĐÃ ĐO ĐƯỢC: dải thời gian vẽ ở `duration = 0` trong khi ô phát
  // hiện `20:49.24`. Nguyên nhân KHÔNG phải route media (đo `Range: bytes=0-1023`
  // qua web 3100 -> `206`, `len=1024`, `Accept-Ranges: bytes`), mà là thứ tự:
  // trình duyệt bắt đầu tải ngay khi `src` được gán, nên `loadedmetadata` có thể
  // nổ TRƯỚC khi effect này kịp gắn listener. Listener gắn sau một sự kiện đã nổ
  // thì không bao giờ được gọi lại.
  //
  // Hai lớp sửa, cả hai đều cần:
  //   1. Đọc `v.duration` NGAY khi effect chạy — nếu trình duyệt đã có metadata thì
  //      lấy luôn, không chờ sự kiện nào nữa.
  //   2. Đọc lại `v.duration` trong vòng `requestAnimationFrame`: `loadedmetadata`
  //      vẫn là đường chính, nhưng vòng lặp là lưới an toàn nếu nó nổ lần nữa.
  //      Chỉ `setDuration` khi số ĐỔI, nên không có lượt vẽ thừa mỗi frame.
  useEffect(() => {
    const v = videoRef.current;
    if (src === null || v === null) return;

    let raf = 0;
    const docMeta = () => {
      const d = Number.isFinite(v.duration) && v.duration > 0 ? v.duration : 0;
      setDuration((cu) => (cu === d ? cu : d));
    };

    const tick = () => {
      const l = loopRef.current;
      if (l !== null && v.currentTime >= l.end) v.currentTime = l.start;
      timeRef.current = v.currentTime;
      setTime(v.currentTime);
      // Lưới an toàn: metadata có thể đã có mà sự kiện đã nổ trước khi gắn listener.
      if (v.readyState >= 1) docMeta();
      raf = requestAnimationFrame(tick);
    };
    raf = requestAnimationFrame(tick);

    const onMeta = () => docMeta();
    // 🔴 `tick` chay bang `requestAnimationFrame`, va rAF DUNG HOAN TOAN khi tab bi
    // an. DO DUOC tren Chrome that (`document.hidden = true`):
    //
    //     RAF: {"so_frame": 0, "ms": "timeout", "hidden": true}
    //
    // Khong mot frame nao trong 3 giay. Khi do `setTime` khong bao gio duoc goi,
    // `player.time` dung yen trong khi video van chay — va khoi duoc to, `currentId`,
    // tu dong phat deu tre theo. Do dung la thu chu du an thay: vach da cham khoi nhung
    // current chua toi.
    //
    // `timeupdate` la su kien cua CHINH the video, trinh duyet ban ~4 lan/giay BAT KE
    // rAF va bat ke tab an. No la luoi an toan cho `tick`, khong thay `tick`: rAF cho
    // do muot 60 fps khi tab hien, `timeupdate` giu time dung khi tab an.
    const onTime = () => {
      timeRef.current = v.currentTime;
      setTime(v.currentTime);
    };
    const onPlay = () => setPlaying(true);
    const onPause = () => setPlaying(false);
    v.addEventListener("loadedmetadata", onMeta);
    v.addEventListener("durationchange", onMeta);
    v.addEventListener("play", onPlay);
    v.addEventListener("pause", onPause);
    v.addEventListener("timeupdate", onTime);
    // Trình duyệt có thể đã tải xong metadata trước lượt effect này.
    if (v.readyState >= 1) docMeta();

    return () => {
      cancelAnimationFrame(raf);
      v.removeEventListener("loadedmetadata", onMeta);
      v.removeEventListener("durationchange", onMeta);
      v.removeEventListener("play", onPlay);
      v.removeEventListener("pause", onPause);
      v.removeEventListener("timeupdate", onTime);
    };
  }, [src]);

  // ── LỚP ÂM BẢN LỒNG ────────────────────────────────────────────────────────
  //
  // 🔴 VÌ SAO PHẢI CÓ: sau khi lồng tiếng xong, khung xem vẫn phát TIẾNG GỐC của video —
  // người dùng bấm Phát để nghe bản lồng và không nghe thấy gì khác. `dub-<tid>.wav` đã
  // nằm trên đĩa, chỉ là chưa có đường phát nó cùng hình.
  //
  // Cách làm: TẮT tiếng của `<video>` (giữ nguyên hình, `currentTime`, mọi thứ khác) và
  // phát một `Audio` riêng cùng mốc thời gian. Không đổi `src` của video sang
  // `dub-<tid>.mp4` vì tệp đó đã BURN phụ đề — hai lớp phụ đề chồng nhau.
  //
  // `new Audio(...)` không gắn vào DOM: chỉ để phát. Mọi thứ dọn trong cleanup.
  useEffect(() => {
    const v = videoRef.current;
    if (giongLong === null) {
      const cu = audioRef.current;
      audioRef.current = null;
      cu?.pause();
      if (v !== null) v.muted = false;
      return;
    }
    // `document.createElement("audio")` chứ KHÔNG `new Audio(src)`: đo được trong harness
    // test (jsdom) `Audio` KHÔNG tồn tại ⇒ `ReferenceError: Audio is not defined`, và 4 bài
    // của `Studio` đỏ. Thẻ audio tạo bằng DOM thì cả jsdom lẫn trình duyệt đều có.
    const a = document.createElement("audio");
    a.preload = "auto";
    a.src = giongLong;
    //: 🔴 NẾU TỆP LỒNG KHÔNG TẢI ĐƯỢC thì BẬT LẠI tiếng gốc. Không có dòng này, một tệp
    //: thiếu/hỏng làm `<video>` câm VĨNH VIỄN — người dùng nghe im lặng và tưởng hỏng cả app,
    //: trong khi đúng ra chỉ là "bản lồng không có ở đó". Hỏng to thì vẫn phải nghe được cái
    //: cũ.
    a.addEventListener("error", () => {
      const vv = videoRef.current;
      if (vv !== null) vv.muted = false;
    }, { once: true });
    audioRef.current = a;
    if (v !== null) v.muted = true;
    return () => {
      a.pause();
      a.src = "";
      if (audioRef.current === a) audioRef.current = null;
      const vv = videoRef.current;
      if (vv !== null) vv.muted = false;
    };
  }, [giongLong, src]);

  /**
   * Bám mốc: chạy/dừng theo hình, và kéo lại khi lệch quá 0,3 s.
   *
   * `0,3 s` là ngưỡng ĐO ĐƯỢC bằng tai: dưới mức đó không nghe ra lệch, trên mức đó nghe
   * thành "tiếng đi trước hình". `play()` có thể bị từ chối (chính sách autoplay) nên
   * nuốt lỗi — hình vẫn chạy, chỉ thiếu tiếng, KHÔNG được làm sập trình phát.
   */
  useEffect(() => {
    const a = audioRef.current;
    const v = videoRef.current;
    if (a === null || v === null) return;
    // Khẳng định lại mỗi lượt: `<video>` có thể được dựng lại (đổi `src`) và mang
    // `muted = false` mặc định của thẻ mới — đo được: quên dòng này thì bản lồng phát
    // CHỒNG lên tiếng gốc.
    if (!v.muted) v.muted = true;
    if (Math.abs(a.currentTime - v.currentTime) > 0.3) a.currentTime = v.currentTime;
    if (playing) {
      const p = a.play() as Promise<void> | undefined;
      if (p !== undefined && typeof p.catch === "function") p.catch(() => {});
    } else {
      a.pause();
    }
  }, [playing, time]);

  const seek = useCallback(
    (t: number) => {
      const c = Math.max(0, duration > 0 ? Math.min(duration, t) : t);
      timeRef.current = c;
      setTime(c);
      if (src !== null && videoRef.current !== null) videoRef.current.currentTime = c;
    },
    [duration, src],
  );

  const toggle = useCallback(() => {
    const v = videoRef.current;
    if (src !== null && v !== null) {
      if (v.paused) void v.play();
      else v.pause();
    } else {
      if (duration > 0 && timeRef.current >= duration) timeRef.current = 0;
      setPlaying((p) => !p);
    }
  }, [src, duration]);

  const play = useCallback(() => {
    const v = videoRef.current;
    if (src !== null && v !== null) void v.play();
    else setPlaying(true);
  }, [src]);

  return { videoRef, audioRef, src, time, playing, duration, seek, toggle, play, loop, setLoop };
}

/**
 * ĐỈNH SÓNG ÂM — giải mã tệp THẬT.
 *
 * Bản gốc có thêm `fakePeaks()` sinh sóng giả từ 18 đoạn mẫu. Hàm đó KHÔNG được
 * chuyển sang: dải thời gian hoặc vẽ sóng của tệp đang mở, hoặc để trống.
 */
export async function decodePeaks(file: File, buckets: number): Promise<number[]> {
  const buf = await file.arrayBuffer();
  const ctx = new AudioContext();
  const audio = await ctx.decodeAudioData(buf);
  void ctx.close();
  const data = audio.getChannelData(0);
  const step = Math.floor(data.length / buckets) || 1;
  const out: number[] = [];
  for (let i = 0; i < buckets; i++) {
    let max = 0;
    for (let j = i * step; j < (i + 1) * step && j < data.length; j += 16) {
      const v = Math.abs(data[j]);
      if (v > max) max = v;
    }
    out.push(max);
  }
  const top = Math.max(...out, 0.001);
  return out.map((v) => v / top);
}
