# phu-de-lab

Bàn làm việc phiên âm và dịch video Trung → Việt. Backend Python (FastAPI), frontend Vite + React 19 + TypeScript.

## Chạy frontend

Hai tiến trình, hai cổng: **backend 8620**, **frontend 3100**.

```powershell
# 1) backend — http://127.0.0.1:8620
backend\.venv\Scripts\python.exe backend\run_api.py

# 2) frontend — http://127.0.0.1:3100
cd frontend
npm install
npm run dev
```

Mở **http://127.0.0.1:3100**.

Vite proxy `/api` sang `http://127.0.0.1:8620`, nên tầng frontend luôn gọi đường dẫn tương đối
`/api/...` và không có CORS trong lúc phát triển.

`strictPort: true` — nếu 3100 đang bị chiếm, Vite **báo lỗi** chứ không tự nhảy sang cổng khác:
backend chỉ cho CORS đúng hai origin `http://localhost:3100` và `http://127.0.0.1:3100`.

`host: "127.0.0.1"` — mặc định của Vite là `localhost`, mà trên Windows Node phân giải
`localhost` thành `::1`, tức chỉ IPv6 được bind và `http://127.0.0.1:3100` bị từ chối kết nối.
Đặt host tường minh để cả hai origin trong danh sách CORS đều dùng được.

### Script khác trong `frontend/package.json`

| Lệnh | Việc | Trạng thái |
|---|---|---|
| `npm run build` | `tsc -b && vite build` | |
| `npm test` | `vitest run` | contract test cần backend đang chạy ở 8620; Vitest được thêm ở task 2 |
| `npm run e2e` | `playwright test` | cần `npx playwright install`; Playwright được thêm ở task 12 |

Cấu hình frontend: `frontend/vite.config.ts` (cổng, host, proxy) và token thiết kế ở
`frontend/src/styles/tokens.css` (giá trị chép từ `docs/superpowers/specs/2026-09-25-phu-de-lab-ui-design.md` §2).

Chi tiết backend: `backend/README.md`.
