# phu-de-lab

Bàn làm việc phiên âm và dịch video Trung → Việt. Backend Python (FastAPI), frontend React 19 + TypeScript
build bằng **Rollup** (Vite đã bị loại — xem mục "Không dùng Vite").

## Chạy frontend

Hai tiến trình, hai cổng: **backend 8620**, **frontend 3100**.

```powershell
# 1) backend — http://127.0.0.1:8620
backend\.venv\Scripts\python.exe backend\run_api.py

# 2) frontend — http://127.0.0.1:3100
cd frontend
npm run dev
```

Mở **http://127.0.0.1:3100**.

`npm run dev` chạy `frontend/dev-server.mjs`. Nó **tự build trước khi phục vụ**: Rollup được gọi
trong chính tiến trình đó (không `child_process`) và theo dõi tệp, rồi server phục vụ
`frontend/dist/` và proxy `/api/...` sang `http://127.0.0.1:8620` — nên lúc phát triển không có
CORS. Sửa mã → Rollup build lại (~0,3 s) → F5. **Không cần `npm run build` tay khi đang dev.**
Request đầu tiên chờ build đầu tiên xong; `GET /` trả `200`, không phải `404`.

Nếu cổng 3100 đang bị chiếm, dev-server **in thông báo rồi thoát** (`exit 1`), **không** tự nhảy
sang cổng khác: backend chỉ cho CORS đúng hai origin `http://localhost:3100` và
`http://127.0.0.1:3100`. Server bind tường minh `127.0.0.1` — trên Windows `localhost` phân giải
thành `::1`, chỉ bind IPv6 là hỏng một trong hai origin.

### Không dùng Vite

Môi trường dựng hiện tại chặn named pipe, mà Vite 6 không có đường pre-bundle dependency nào ngoài
`esbuild` (tiến trình con với `stdio:'pipe'` → `EPERM`). Rollup chạy trong tiến trình nên không
chạm named pipe. `vite.config.ts` **không còn** trong repo và đừng thêm lại.

### Script trong `frontend/package.json`

| Lệnh | Việc |
|---|---|
| `npm run dev` | `node dev-server.mjs` — build-on-demand + watch + proxy, cổng 3100 |
| `npm run build` | `tsc --noEmit && rollup -c` → `frontend/dist/` |
| `npm run typecheck` | `tsc --noEmit`, không sinh tệp |
| `npm test` | `node --test --test-isolation=none` + loader SWC trong tiến trình |
| `npm run e2e` | `playwright test` — cần `npx playwright install` một lần |

`npm run build` chạy `tsc --noEmit` **trước** `rollup -c`, vì `rollup -c` một mình không kiểm kiểu:
thiếu bước đó thì một "build xanh" vẫn có thể kèm type sai.

### Test chạy bằng gì

**Không có Vitest, không có jsdom, không có Testing Library** trong repo này: Vitest dựng trên Vite
nên cũng chết, còn `jsdom`/`@testing-library/*` không có sẵn và `npm i` bị chặn ở môi trường dựng
hiện tại. Test chạy bằng runner có sẵn của Node 24:

- `.ts`/`.tsx` do `frontend/test/swc-loader.mjs` bóc (`module.registerHooks` + `@swc/core`, chạy
  trong tiến trình, không spawn).
- Test cấu trúc component dùng `react-dom/server.renderToStaticMarkup` — render React thật, không
  cần DOM.
- Test đơn vị **không** mô phỏng được tương tác (click, focus, bàn phím, effect, state update).
  Những thứ đó chỉ Playwright trên backend thật chứng minh được.

Hai chi tiết của lệnh test đều **bắt buộc**, thiếu là chết:

- `--test-isolation=none` — không có nó, runner spawn tiến trình con cho mỗi tệp test và chết
  `EPERM`.
- `--import ./test/swc-loader.mjs` — không có nó, mọi tệp `.tsx` chết
  `ERR_UNKNOWN_FILE_EXTENSION`. Kèm theo đó, script truyền glob
  `"**/*.test.{ts,tsx,mjs,js}"` vì discovery mặc định của Node 24 có chạy `.test.ts` nhưng
  **không** chạy `.test.tsx`.

### Cài dependency

`frontend/node_modules/` **đã có sẵn** trong cây làm việc hiện tại. Trên một máy sạch thì bước đầu
là `cd frontend; npm install` — nhưng ở môi trường dựng hiện tại lệnh đó **có thể chết `EPERM`** ở
cache npm, nên đừng chạy lại khi `node_modules/` đã có. `package-lock.json` đang cũ (nó mô tả cây
Vite cũ), vì vậy `npm ci` sẽ fail cho tới khi có người `npm install` lại ở môi trường bình thường.

Cấu hình frontend: `frontend/rollup.config.mjs` (build) · `frontend/dev-server.mjs` (cổng, proxy,
watch) · `frontend/tsconfig.json` (kiểu) · `frontend/test/swc-loader.mjs` (loader test) · token
thiết kế ở `frontend/src/styles/tokens.css` (giá trị chép từ
`docs/superpowers/specs/2026-09-25-phu-de-lab-ui-design.md` §2).

Chi tiết backend: `backend/README.md`.
