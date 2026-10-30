import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { Outlet, Link, createRootRouteWithContext, useRouter, type ErrorComponentProps } from "@tanstack/react-router";

/**
 * GỐC CỦA CÂY ĐỊNH TUYẾN.
 *
 * 🔴 NGUỒN GỐC: `_lovable-code/src/routes/__root.tsx` (131 dòng). Tệp này giữ nguyên
 * phần hiển thị (404, màn lỗi, QueryClientProvider, `Outlet`) và BỎ ĐÚNG BA thứ chỉ
 * tồn tại vì Lovable chạy TanStack Start:
 *
 *  1. `HeadContent` / `Scripts` / `shellComponent` / `head()` — API của **TanStack Start**
 *     (SSR: nó dựng thẻ `<head>` và nhúng script trên máy chủ). App này là SPA do Vite
 *     dựng; `<head>` nằm trong `index.html`, và bản Lovable cũng có sẵn thẻ `<title>`
 *     tương ứng ở đó. Giữ `shellComponent` mà không có Start thì React nhận một cây
 *     `<html>` lồng trong `<div id="root">` — hỏng bố cục.
 *  2. `import appCss from "../styles.css?url"` — Start dùng URL đó để chèn `<link>`.
 *     Vite import thẳng `../styles.css` trong `main.tsx`; Tailwind biên dịch ở đó.
 *  3. `reportLovableError` — báo lỗi về máy chủ Lovable. Không có máy chủ đó ở đây, và
 *     gọi vào một endpoint không tồn tại thì màn lỗi tự sinh thêm lỗi mạng.
 *
 * ⚠️ `lang="en"` của bản gốc là SAI và tôi sửa: toàn bộ chữ trong app là tiếng Việt
 * (nút "Phát", "Duyệt", "Lồng tiếng"). `lang` quyết định cách trình đọc màn hình phát
 * âm và cách trình duyệt chọn font cho chữ Hán khi hiển thị bản gốc tiếng Trung. Bản
 * Lovable khai `en` vì đó là mặc định của khuôn TanStack, không phải quyết định thiết kế.
 */
function NotFoundComponent() {
  return (
    <div className="flex min-h-screen items-center justify-center bg-background px-4">
      <div className="max-w-md text-center">
        <h1 className="text-7xl font-bold text-foreground">404</h1>
        <h2 className="mt-4 text-xl font-semibold text-foreground">Không có trang này</h2>
        <p className="mt-2 text-sm text-muted-foreground">
          Đường dẫn không tồn tại hoặc đã bị chuyển đi.
        </p>
        <div className="mt-6">
          <Link
            to="/"
            className="inline-flex items-center justify-center rounded-md bg-primary px-4 py-2 text-sm font-medium text-primary-foreground transition-colors hover:bg-primary/90"
          >
            Về trang chính
          </Link>
        </div>
      </div>
    </div>
  );
}

function ErrorComponent({ error, reset }: ErrorComponentProps) {
  console.error(error);
  const router = useRouter();

  return (
    <div className="flex min-h-screen items-center justify-center bg-background px-4">
      <div className="max-w-md text-center">
        <h1 className="text-xl font-semibold tracking-tight text-foreground">
          Trang này không tải được
        </h1>
        <p className="mt-2 text-sm text-muted-foreground">
          Có lỗi ở phía máy chủ. Thử tải lại, hoặc về trang chính.
        </p>
        <div className="mt-6 flex flex-wrap justify-center gap-2">
          <button
            onClick={() => {
              router.invalidate();
              reset();
            }}
            className="inline-flex items-center justify-center rounded-md bg-primary px-4 py-2 text-sm font-medium text-primary-foreground transition-colors hover:bg-primary/90"
          >
            Thử lại
          </button>
          <a
            href="/"
            className="inline-flex items-center justify-center rounded-md border border-input bg-background px-4 py-2 text-sm font-medium text-foreground transition-colors hover:bg-accent"
          >
            Về trang chính
          </a>
        </div>
      </div>
    </div>
  );
}

export const Route = createRootRouteWithContext<{ queryClient: QueryClient }>()({
  component: RootComponent,
  notFoundComponent: NotFoundComponent,
  errorComponent: ErrorComponent,
});

function RootComponent() {
  const { queryClient } = Route.useRouteContext();

  return (
    <QueryClientProvider client={queryClient}>
      {/* Bắt buộc: các route con hiển thị ở đây. Bỏ <Outlet /> là mọi route con mất. */}
      <Outlet />
    </QueryClientProvider>
  );
}
