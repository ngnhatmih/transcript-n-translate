import { useEffect, useRef } from "react";

/**
 * Bản xem trước dùng **libass thật** (JASSUB = libass biên dịch sang WebAssembly).
 *
 * 🔴 VÌ SAO CÓ NHÁNH NÀY (chủ dự án: *"làm thêm 1 nhánh xử lý vấn đề này"*). Đường CSS
 * (`PhuDeOverlay`) phải TỰ MÔ PHỎNG libass: bẻ dòng, hệ số chữ 0,637, bước dòng, đệm hộp,
 * vị trí đáy… Mỗi hằng số sai một chút là lệch, và đã 6 lần phải sửa từng cái (xem
 * `docs/PHU-DE-QUY-TAC.md`). Ở nhánh này, hai bên dùng CHUNG một bộ máy render:
 *
 *     editor ──► to_ass() trên backend ──► .ass  ──┬──► JASSUB (wasm libass)  → preview
 *                                                  └──► ffmpeg `ass=` filter → burn
 *
 * Nghĩa là bẻ dòng, kerning, hình học hộp, vị trí — tất cả do libass quyết, không mô phỏng.
 *
 * Khác biệt còn lại (phải biết): phiên bản libass của JASSUB và của ffmpeg có thể khác;
 * font phải là CÙNG FILE (nên nạp từ `/fonts/…` do image web phục vụ, cùng file trong
 * `backend/app/assets/fonts/`). `PlayResX/Y` lấy từ chính `.ass` mà backend sinh, nên không
 * thể lệch hệ toạ độ.
 *
 * Nhánh này KHÔNG thay đường CSS: nó là lựa chọn (`bat` = công tắc trong hộp thoại kiểu
 * chữ). CSS là đường dự phòng khi wasm không nạp được (máy yếu, chặn wasm), và là đường
 * đang được đo trong mọi bài test giao diện.
 */
export function PhuDeLibass({
  assUrl,
  videoRef,
  bat,
  font,
}: {
  /** URL file `.ass` của CHÍNH bản dịch đang xem (kèm style hiện tại). */
  assUrl: string;
  videoRef: React.RefObject<HTMLVideoElement | null>;
  bat: boolean;
  font: string;
}) {
  const canvasRef = useRef<HTMLCanvasElement>(null);

  useEffect(() => {
    if (!bat) return;
    const video = videoRef.current;
    const canvas = canvasRef.current;
    if (video === null || canvas === null) return;

    let huy = false;
    let jassub: { destroy?: () => void } | null = null;

    void (async () => {
      try {
        //: 🔴 Asset của JASSUB phục vụ như TỆP TĨNH trong `/public/jassub/`, KHÔNG import
        //: bằng subpath của gói: `exports` của `jassub` chặn subpath, và đo được lỗi build
        //: `Rollup failed to resolve import "jassub/dist/worker/jassub-worker.js?url"`.
        //: Worker tự `import()` các chunk cạnh nó (`./renderers/*.js`), nên phải copy NGUYÊN
        //: thư mục `dist`, không chỉ worker + wasm.
        const mod = await import("jassub");
        if (huy) return;
        //: Dùng KIỂU do gói khai báo, không tự đặt lại: gói yêu cầu `canvas` (hoặc `video`)
        //: là trường BẮT BUỘC trong một union, nên một kiểu `Record<string, unknown>` tự
        //: viết sẽ bị `tsc` từ chối — đo được: "Property 'canvas' is missing".
        const JASSUB = mod.default;
        const tept = font === "IBM Plex Mono" ? "IBMPlexMono-Regular.ttf" : "Archivo.ttf";
        jassub = new JASSUB({
          video,
          canvas,
          //: Lấy `.ass` từ CHÍNH backend, không tự dựng: đó là toàn bộ ý tưởng của nhánh này.
          subUrl: assUrl,
          //: CÙNG FILE font mà bản burn dùng — không chỉ cùng tên font.
          fonts: [`/fonts/${tept}`],
          workerUrl: "/jassub/wasm/jassub-worker.js",
          wasmUrl: "/jassub/wasm/jassub-worker.wasm",
          modernWasmUrl: "/jassub/wasm/jassub-worker-modern.wasm",
          queryFonts: false,
          defaultFont: font,
        });
      } catch {
        //: Wasm/worker hỏng ⇒ để `PhuDeOverlay` (CSS) vẽ. Không làm sập khung xem.
        jassub = null;
      }
    })();

    return () => {
      huy = true;
      jassub?.destroy?.();
    };
  }, [assUrl, bat, font, videoRef]);

  if (!bat) return null;
  return (
    <canvas
      ref={canvasRef}
      className="pointer-events-none absolute inset-0 size-full"
      aria-hidden
    />
  );
}
