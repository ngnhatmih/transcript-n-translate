/**
 * Hộp HIỂN THỊ THẬT của video trong khung chứa.
 *
 * ## Vì sao cần (lỗi thật, chủ dự án chỉ ra)
 *
 * `<video>` dùng `object-contain`, nên khi tỉ lệ video khác tỉ lệ khung chứa thì video
 * KHÔNG phủ kín khung — nó nằm giữa, hai bên (hoặc trên dưới) là viền đen. Mọi lớp đè
 * (`PhuDeOverlay`, `VungDocKhung`) lại đặt theo `%` của KHUNG CHỨA, nên:
 *
 *   · hộp vùng đọc OCR trải hết bề ngang khung chứa, TRÀN ra ngoài video;
 *   · chữ phụ đề xem trước to và lệch so với bản burn thật;
 *   · các tay kéo vùng đọc nằm ngoài hình, không ai nhắm tới được.
 *
 * Đo được trên video dọc 1080×1920 trong khung 16:9: video chỉ chiếm ~31 % bề ngang khung
 * chứa, nên mọi toạ độ `%` của khung chứa lệch gần 3,2 lần theo trục ngang.
 *
 * ## Công thức
 *
 * `tiLe = min(rongChua / rongVideo, caoChua / caoVideo)` — trục nào chật hơn thì quyết
 * định, đúng cách `object-contain` co hình. Hai bên dư ra chia đôi, nên hình luôn ở GIỮA.
 */
export interface HopVideo {
  trai: number;
  tren: number;
  rong: number;
  cao: number;
}

/**
 * Trả hộp hiển thị của video trong khung chứa. Mọi số theo PIXEL của khung chứa.
 *
 * Chưa biết kích thước video (`videoWidth = 0`, metadata chưa nạp) thì trả ĐÚNG KHUNG
 * CHỨA — cùng hành vi cũ. Trả `0×0` chỉ khi khung chứa chưa có kích thước, và bên gọi phải
 * coi đó là "chưa vẽ được" chứ không phải "hộp rỗng ở góc".
 */
export function hopVideo(
  rongChua: number,
  caoChua: number,
  rongVideo: number,
  caoVideo: number,
): HopVideo {
  if (!(rongChua > 0 && caoChua > 0)) return { trai: 0, tren: 0, rong: 0, cao: 0 };
  if (!(rongVideo > 0 && caoVideo > 0)) {
    return { trai: 0, tren: 0, rong: rongChua, cao: caoChua };
  }
  const tiLe = Math.min(rongChua / rongVideo, caoChua / caoVideo);
  const rong = rongVideo * tiLe;
  const cao = caoVideo * tiLe;
  return { trai: (rongChua - rong) / 2, tren: (caoChua - cao) / 2, rong, cao };
}
