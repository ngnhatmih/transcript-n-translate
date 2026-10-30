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
export function usePlayer(media: string | null) {
  const videoRef = useRef<HTMLVideoElement | null>(null);
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
    const onPlay = () => setPlaying(true);
    const onPause = () => setPlaying(false);
    v.addEventListener("loadedmetadata", onMeta);
    v.addEventListener("durationchange", onMeta);
    v.addEventListener("play", onPlay);
    v.addEventListener("pause", onPause);
    // Trình duyệt có thể đã tải xong metadata trước lượt effect này.
    if (v.readyState >= 1) docMeta();

    return () => {
      cancelAnimationFrame(raf);
      v.removeEventListener("loadedmetadata", onMeta);
      v.removeEventListener("durationchange", onMeta);
      v.removeEventListener("play", onPlay);
      v.removeEventListener("pause", onPause);
    };
  }, [src]);

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

  return { videoRef, src, time, playing, duration, seek, toggle, play, loop, setLoop };
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
