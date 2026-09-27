/**
 * `useApi` — một lượt `fetch` có trạng thái loading/lỗi, cộng nút `reload`.
 *
 * Vì sao cần: ba màn hình đều có cùng ba trạng thái (đang đọc / có dữ liệu / lỗi), và
 * viết tay ba lần thì mỗi lần quên một nhánh khác nhau. Ở đây chỉ có MỘT nhánh.
 *
 * Vì sao KHÔNG nằm trong `useJobStream`: cái đó là MỘT subscription SSE sống lâu cho
 * cả app; cái này là một request-rồi-xong. Gộp hai thứ có vòng đời khác nhau vào một
 * hook là cách chắc chắn nhất để có hai nguồn sự thật cho cùng một hàng dữ liệu.
 *
 * `ponytail:` TRẦN — (a) KHÔNG cache: mỗi lần mount (và mỗi lần `reload`) là một
 * request thật, kể cả khi hai component hỏi cùng một endpoint; (b) KHÔNG dedupe hai
 * request đang bay; (c) KHÔNG có `reload` theo chu kỳ. Chưa đo được nhu cầu, nên chưa
 * dựng. Nâng cấp: một map `url -> promise` dùng chung, thêm khi có màn hình thật sự
 * hỏi trùng.
 *
 * `AbortSignal` được truyền vào `fn`, nhưng KHÔNG phải hàm nào cũng dùng nó:
 * `endpoints.listSources()` không nhận tham số, nên `abort()` lúc cleanup KHÔNG huỷ
 * được request HTTP đó — nó chỉ báo cho hàm nào biết lắng nghe. Hệ quả đo được: sau
 * khi unmount, request vẫn chạy tới cùng; thứ chặn cập nhật state là cờ `disposed`.
 * Đây là một dòng ĐÚNG NHƯNG CHƯA QUAN SÁT ĐƯỢC, khai ra thay vì gán cho nó một bài
 * test giả (ERRATA #7 mục 5).
 */
import { useCallback, useEffect, useRef, useState } from "react";

export interface KetQuaApi<T> {
  data: T | null;
  error: string | null;
  loading: boolean;
  reload: () => void;
}

function messageOf(loi: unknown): string {
  // `ApiError.message` đã là "<status>: <detail>" (xem `api/client.ts`), nên nhánh này
  // giữ được cả mã HTTP lẫn câu tiếng Việt của backend.
  if (loi instanceof Error) return loi.message;
  return String(loi);
}

/**
 * @param fn   hàm gọi API. Nhận `AbortSignal` (có thể bỏ qua) và trả một Promise.
 * @param deps danh sách phụ thuộc do NƠI GỌI khai — y như đối số thứ hai của `useEffect`.
 */
export function useApi<T>(
  fn: (signal: AbortSignal) => Promise<T>,
  deps: readonly unknown[],
): KetQuaApi<T> {
  const [ketQua, setKetQua] = useState<{ data: T | null; error: string | null; loading: boolean }>({
    data: null,
    error: null,
    loading: true,
  });
  // `reload` chỉ là một con số tăng dần: nó khiến effect dưới đây chạy lại, không cần
  // thêm một đường gọi API thứ hai nào.
  const [lan, setLan] = useState(0);

  // `fn` là closure MỚI ở mỗi lần render (ví dụ `() => endpoints.listSources()`), nên
  // đưa nó vào danh sách phụ thuộc là một vòng lặp vô hạn. Ref giữ bản mới nhất mà
  // KHÔNG kéo theo việc chạy lại effect; thứ quyết định chạy lại là `deps` của nơi gọi.
  const fnRef = useRef(fn);
  fnRef.current = fn;

  useEffect(() => {
    const controller = new AbortController();
    let disposed = false;
    setKetQua((cu) => ({ ...cu, loading: true, error: null }));

    fnRef.current(controller.signal)
      .then((data) => {
        if (disposed) return;
        setKetQua({ data, error: null, loading: false });
      })
      .catch((loi: unknown) => {
        if (disposed) return;
        // Lỗi KHÔNG xoá `data` cũ thành rỗng một cách âm thầm: `error` được đặt, và
        // giao diện chọn hiện lỗi hay hiện dữ liệu cũ (xem `ChannelZone`).
        setKetQua({ data: null, error: messageOf(loi), loading: false });
      });

    return () => {
      disposed = true;
      controller.abort();
    };
    // Kích thước mảng này KHÔNG đổi giữa các lần render: `deps` do nơi gọi khai một lần.
  }, [...deps, lan]);

  const reload = useCallback(() => {
    setLan((n) => n + 1);
  }, []);

  return { data: ketQua.data, error: ketQua.error, loading: ketQua.loading, reload };
}
