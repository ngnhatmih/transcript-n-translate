/**
 * Ghim hai LUẬT đã bị một **lượt dùng thật** bác (ERRATA #50) — và cả hai đều là loại mà
 * `npm test` **không** tự chạm tới:
 *
 *  1. `.ch__ten` phải NGẮT ĐƯỢC giữa một token (`overflow-wrap: anywhere`). Đo trong Chrome
 *     thật: thiếu khai báo này, ở trạng thái xác nhận xoá `.ch__ten` có `scrollW 127 /
 *     clientW 105` ⇒ chữ VẼ RA NGOÀI hộp và đè lên nút `xóa?`. jsdom không có layout, nên
 *     không bài DOM nào thấy được — chỉ văn bản CSS là thứ ghim được.
 *  2. `nginx.conf` phải (a) nâng `client_max_body_size` (mặc định **1 MB** của nginx chặn mọi
 *     tệp thật — đo được `413` với tệp 8,5 MB), (b) trả **JSON** cho `413` để `ApiError.detail`
 *     là câu tiếng Việt chứ không phải `statusText` tiếng Anh, và (c) `no-cache` cho bản tĩnh,
 *     vì Rollup xuất tên CỐ ĐỊNH nên trình duyệt có quyền chạy bản cũ sau khi build lại ảnh.
 *
 * Khuôn đọc tệp là khuôn CÓ SẴN của giai đoạn: `ChannelZone.test.tsx`, `CompareScreen.test.tsx`
 * và `BangPhim.test.tsx` đều `readFileSync` chính `app.css` để ghim "lớp có LUẬT thật".
 */
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { describe, it } from "node:test";

/**
 * Bóc CHÚ THÍCH trước khi đọc. Không phải cho đẹp: chú thích của `app.css` nằm NGAY TRƯỚC
 * khối nó nói về, nên nếu để nguyên thì "danh sách selector" của khối đó dính cả đoạn văn
 * (đo được ở lượt viết bài này: `.ch__dong > .ch__item` không khớp) — và tệ hơn, một chú
 * thích có thể VÔ TÌNH làm phép khẳng định xanh (nó chứa chính chuỗi đang tìm).
 */
const appCss = readFileSync(new URL("./app.css", import.meta.url), "utf8")
  .replace(/\/\*[\s\S]*?\*\//g, "");
const nginxConf = readFileSync(new URL("../../nginx.conf", import.meta.url), "utf8")
  .replace(/^[ \t]*#.*$/gm, "");

/**
 * Thân của MỌI khối `{ … }` mà danh sách selector của nó chứa ĐÚNG `selector`.
 *
 * "ĐÚNG" chứ không phải "chứa chuỗi": `.ch__ten` không được khớp với `.ch__ten-nao-do`.
 * Trả về theo thứ tự xuất hiện trong tệp để phép khẳng định ĐỌC ĐƯỢC luật "khai báo sau
 * thắng" của CSS khi độ đặc hiệu bằng nhau.
 */
function thanKhoi(css: string, selector: string): string[] {
  const ra: string[] = [];
  for (const manh of css.split("}")) {
    const mo = manh.lastIndexOf("{");
    if (mo < 0) continue;
    // Phần selector là đoạn SAU dấu `}` gần nhất (nếu có) để không dính khối trước.
    const danhSach = manh
      .slice(0, mo)
      .split("}")
      .pop()
      ?.split(",")
      .map((s) => s.trim()) ?? [];
    if (danhSach.includes(selector)) ra.push(manh.slice(mo + 1));
  }
  return ra;
}

/** Mọi giá trị đã khai cho `thuocTinh` trong các khối của `selector` (giá trị CSS đã trim). */
function khaiBao(css: string, selector: string, thuocTinh: string): string[] {
  const re = new RegExp(`(?:^|[;{\\s])${thuocTinh}\\s*:\\s*([^;]+);`, "g");
  return thanKhoi(css, selector).flatMap((than) =>
    [...than.matchAll(re)].map((m) => m[1].trim()),
  );
}

describe(".ch__ten: tên tệp phải ngắt được giữa một token (ERRATA #50 mục 2)", () => {
  it("có `overflow-wrap: anywhere` — `break-word` KHÔNG đủ (không hạ được `min-content`)", () => {
    const giaTri = khaiBao(appCss, ".ch__ten", "overflow-wrap");
    assert.deepEqual(
      giaTri,
      ["anywhere"],
      "`.ch__ten` phải có ĐÚNG một khai báo `overflow-wrap: anywhere`. Thiếu nó thì tên tệp "
        + "không có chỗ ngắt (vd `8f4b5304daf42569.wav`) VẼ RA NGOÀI hộp khi nút xoá thu hẹp "
        + "`.ch__item`, và đè lên nút `xóa?` — đo được ở Chrome thật: scrollW 127 / clientW 105. "
        + "`break-word` cũng bị từ chối ở đây vì nó không hạ `min-content` xuống một ký tự.",
    );
  });

  it("đi kèm `min-width: 0` trên flex item (nếu không, hộp không được phép co nhỏ hơn nội dung)", () => {
    const item = thanKhoi(appCss, ".ch__dong > .ch__item");
    assert.equal(item.length > 0, true, "phải còn khối `.ch__dong > .ch__item`");
    assert.equal(
      /min-width\s*:\s*0/.test(item.join("\n")),
      true,
      "`.ch__dong > .ch__item` phải giữ `min-width: 0` — thiếu nó thì flex item không co được "
        + "và nút xoá bị đẩy xuống dòng thứ hai (đo được trong Chrome thật, xem chú thích tại chỗ)",
    );
  });
});

describe("nginx.conf: đường web phải NHẬN được tệp thật (ERRATA #50 mục 1, 3)", () => {
  it("`client_max_body_size` đã nâng lên ÍT NHẤT 1024 MB", () => {
    const m = /client_max_body_size\s+(\d+)m\s*;/.exec(nginxConf);
    assert.notEqual(m, null, "nginx.conf phải có `client_max_body_size …m;`");
    const soMb = Number(m?.[1]);
    assert.equal(
      soMb >= 1024,
      true,
      `client_max_body_size phải >= 1024 MB, đang là ${String(soMb)} MB. Mặc định của nginx là `
        + "1 MB và nó chặn MỌI tệp thật ở proxy (đo được: 413 với tệp 8,5 MB) trong khi backend "
        + "nhận đủ — và câu lỗi người dùng đọc là `statusText` tiếng Anh của nginx.",
    );
  });

  it("`413` trả JSON đúng khuôn FastAPI, KHÔNG để body HTML của nginx", () => {
    assert.equal(
      /error_page\s+413\s*=?\s*@/.test(nginxConf),
      true,
      "phải có `error_page 413` trỏ tới một location có tên",
    );
    assert.equal(
      /return\s+413\s+'\{"detail":/.test(nginxConf),
      true,
      "`413` phải trả body `{\"detail\": …}` — `client.ts` chỉ đọc được `detail` khi body là "
        + "JSON; body HTML làm nó rơi về `statusText` và người dùng đọc câu tiếng Anh "
        + "`Request Entity Too Large` mà không biết phải làm gì",
    );
    assert.equal(
      nginxConf.includes("tệp quá lớn"),
      true,
      "câu `detail` phải nói bằng TIẾNG VIỆT và nêu giới hạn",
    );
  });

  it("bản tĩnh có `Cache-Control: no-cache` (tên tệp KHÔNG hash ⇒ không được để bản cũ)", () => {
    const soLan = (nginxConf.match(/Cache-Control\s+"no-cache"/g) ?? []).length;
    assert.equal(
      soLan >= 2,
      true,
      "phải có `no-cache` cho cả /assets/ và / — đo được: sau khi build lại ảnh, Chrome vẫn "
        + "chạy CSS cũ (báo `overflow-wrap: normal` trong khi CSS trong ảnh có `anywhere`), "
        + `tức một lượt kiểm hình thức có thể SAI. Đang có ${String(soLan)} khai báo.`,
    );
    assert.equal(
      /location\s+\/assets\/\s*\{[^}]*Cache-Control/.test(nginxConf),
      true,
      "khối `/assets/` phải là chỗ khai `no-cache` (đó là nơi `index.css`/`index.js` được phục vụ)",
    );
  });
});
