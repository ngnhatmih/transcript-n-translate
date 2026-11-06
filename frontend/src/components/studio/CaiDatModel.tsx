import { useCallback, useEffect, useState } from "react";

import { getModelSettings, putModelSettings } from "@/api/endpoints";
import type { ModelSettings, ModelSettingsIn, ModelTask } from "@/api/types";

/**
 * BẢNG "CÀI ĐẶT MODEL" — mở từ bảng lệnh (Ctrl+K → "Cài đặt model").
 *
 * Hai ô cho mỗi việc, đúng câu của chủ dự án: *"Làm 2 mục là model mặc định và model sử
 * dụng. Model mặc định được dùng khi model sử dụng ko thể hoạt động."*
 *
 * Bốn luật của bảng này, mỗi luật là một quyết định đã trả giá:
 *
 * 1. **Danh sách ứng viên đến từ BACKEND**, không viết cứng: `GET /api/model-settings`
 *    dựng từ `registry.json` + hai bộ mã hoá burn. Thêm model mới = thêm dữ liệu, không
 *    sửa tệp này.
 * 2. **`locked` thì KHÔNG vẽ ô dự phòng.** Việc chỉ có một ứng viên (OCR/TTS/Tách giọng)
 *    vẫn hiện — người dùng cần thấy nó đang chạy model nào — nhưng một ô "dự phòng" chỉ
 *    có một lựa chọn là ô nói dối rằng có thể chọn.
 * 3. **`hieu_luc` do backend trả.** Dòng "đang chạy: X (dự phòng)" là câu trả lời của
 *    chính resolver mà worker dùng; giao diện tự suy từ `available` sẽ có ngày nói một
 *    đằng làm một nẻo.
 * 4. **Chỉ gửi việc đã đổi.** Bấm Lưu mà gửi cả bảng thì mọi dòng chưa ai đụng cũng bị
 *    ghi đè bằng giá trị đang hiện — kể cả khi backend vừa đổi mặc định.
 */
export function CaiDatModel({ open, onClose }: { open: boolean; onClose: () => void }) {
  const [du, setDu] = useState<ModelSettings | null>(null);
  const [loi, setLoi] = useState<string | null>(null);
  const [dangLuu, setDangLuu] = useState(false);
  const [daLuu, setDaLuu] = useState(false);
  /** Bản nháp: `task_id -> {used, fallback}`. Chỉ chứa dòng NGƯỜI DÙNG đã đổi. */
  const [nhap, setNhap] = useState<Record<string, { used: string | null; fallback: string | null }>>({});
  const [nhomDich, setNhomDich] = useState<"mt" | "llm" | null>(null);

  const nap = useCallback(async () => {
    setLoi(null);
    try {
      const d = await getModelSettings();
      setDu(d);
      setNhap({});
      setNhomDich(d.nhom_dich);
    } catch (e) {
      setLoi(e instanceof Error ? e.message : String(e));
    }
  }, []);

  useEffect(() => {
    if (open) {
      setDaLuu(false);
      void nap();
    }
  }, [open, nap]);

  if (!open) return null;

  const doi = (task: ModelTask, khoa: "used" | "fallback", gia: string) => {
    setDaLuu(false);
    setNhap((cu) => ({
      ...cu,
      [task.id]: {
        used: cu[task.id]?.used ?? task.used,
        fallback: cu[task.id]?.fallback ?? task.fallback,
        [khoa]: gia === "" ? null : gia,
      },
    }));
  };

  const luu = async () => {
    setDangLuu(true);
    setLoi(null);
    try {
      const body: ModelSettingsIn = { tasks: nhap };
      if (nhomDich !== null && nhomDich !== du?.nhom_dich) body.nhom_dich = nhomDich;
      const moi = await putModelSettings(body);
      setDu(moi);
      setNhap({});
      setNhomDich(moi.nhom_dich);
      setDaLuu(true);
    } catch (e) {
      setLoi(e instanceof Error ? e.message : String(e));
    } finally {
      setDangLuu(false);
    }
  };

  const khoiPhuc = () => {
    // "Khôi phục" = ghi lại ĐÚNG giá trị mặc định backend trả (`mac_dinh`), không xoá
    // khoá nào: một khoá bị xoá và một khoá mang giá trị mặc định là hai trạng thái khác
    // nhau trong DB, và chỉ cái thứ hai là thứ nút này hứa.
    if (du === null) return;
    const tatCa: Record<string, { used: string | null; fallback: string | null }> = {};
    for (const t of du.tasks) tatCa[t.id] = { ...t.mac_dinh };
    setNhap(tatCa);
    setNhomDich(du.nhom_dich);
    setDaLuu(false);
  };

  //: Nhóm theo `task.nhom` GIỮ ĐÚNG THỨ TỰ backend trả (thứ tự khai trong domain).
  const nhom: Array<{ ten: string; viec: ModelTask[] }> = [];
  for (const t of du?.tasks ?? []) {
    const cuoi = nhom[nhom.length - 1];
    if (cuoi !== undefined && cuoi.ten === t.nhom) cuoi.viec.push(t);
    else nhom.push({ ten: t.nhom, viec: [t] });
  }

  const giaTri = (t: ModelTask, khoa: "used" | "fallback") =>
    nhap[t.id]?.[khoa] ?? t[khoa] ?? "";

  /** Ứng viên để vẽ: việc `dich` lọc theo NHÓM đang chọn (nhưng vẫn giữ giá trị đã lưu). */
  const ungVien = (t: ModelTask) => {
    if (t.id !== "dich" || nhomDich === null) return t.candidates;
    return t.candidates.filter((u) => u.nhom === null || u.nhom === nhomDich);
  };

  return (
    <div
      className="fixed inset-0 z-50 grid place-items-start justify-center overflow-y-auto bg-panel-0/70 py-10 backdrop-blur-[2px]"
      onClick={onClose}
    >
      <div
        className="w-[680px] max-w-[94vw] rounded-sm border border-rule bg-panel-1 shadow-2xl"
        onClick={(e) => e.stopPropagation()}
        role="dialog"
        aria-label="Cài đặt model"
      >
        <header className="flex items-baseline justify-between border-b border-rule px-5 py-4">
          <div>
            <h2 className="text-[16px] font-semibold text-ink-0">Cài đặt model</h2>
            <p className="mt-1 text-[12px] text-ink-2">
              Model sử dụng được ưu tiên. Nếu nó không hoạt động, hệ thống chuyển sang model
              mặc định (dự phòng).
            </p>
          </div>
          <button onClick={onClose} className="text-[12px] text-ink-2 hover:text-ink-0">
            Đóng
          </button>
        </header>

        {loi !== null && (
          <p className="border-b border-rule bg-signal-soft px-5 py-2 text-[12px] text-ink-0">
            {loi}
          </p>
        )}

        <div className="max-h-[62vh] overflow-y-auto px-5 py-3">
          {du === null && loi === null && <p className="py-6 text-[12px] text-ink-2">Đang nạp…</p>}
          {nhom.map((g) => (
            <section key={g.ten} className="mb-4 rounded-sm border border-rule">
              <h3 className="border-b border-rule px-4 py-2 text-[12.5px] font-medium text-ink-0">
                {g.ten}
              </h3>
              {g.ten === "Dịch" && (
                <div className="flex items-center gap-4 border-b border-rule px-4 py-2 text-[12px] text-ink-1">
                  <span>Dịch bằng:</span>
                  {(["mt", "llm"] as const).map((n) => (
                    <label key={n} className="flex items-center gap-1.5">
                      <input
                        type="radio"
                        name="nhom-dich"
                        checked={nhomDich === n}
                        onChange={() => {
                          setDaLuu(false);
                          setNhomDich(n);
                        }}
                      />
                      {n === "mt" ? "MT (dịch máy)" : "LLM (mô hình ngôn ngữ)"}
                    </label>
                  ))}
                </div>
              )}
              {g.viec.map((t) => (
                <div
                  key={t.id}
                  className="grid grid-cols-[120px_1fr_1fr] items-center gap-3 border-b border-rule px-4 py-2 last:border-b-0"
                >
                  <span className="text-[12.5px] text-ink-0" title={t.note || undefined}>
                    {t.label}
                  </span>
                  <label className="text-[11px] text-ink-2">
                    Model sử dụng
                    <select
                      aria-label={`model sử dụng của ${t.label}`}
                      className="mt-0.5 w-full rounded-sm border border-rule bg-panel-0 px-2 py-1 text-[12px] text-ink-0"
                      value={giaTri(t, "used")}
                      onChange={(e) => doi(t, "used", e.target.value)}
                    >
                      {ungVien(t).map((u) => (
                        <option key={u.id} value={u.id}>
                          {u.label}
                          {u.available ? "" : " — chưa sẵn sàng"}
                        </option>
                      ))}
                    </select>
                  </label>
                  {t.locked ? (
                    <span className="text-[11px] text-ink-2">chỉ có một model</span>
                  ) : (
                    <label className="text-[11px] text-ink-2">
                      Model mặc định (dự phòng)
                      <select
                        aria-label={`model dự phòng của ${t.label}`}
                        className="mt-0.5 w-full rounded-sm border border-rule bg-panel-0 px-2 py-1 text-[12px] text-ink-0"
                        value={giaTri(t, "fallback")}
                        onChange={(e) => doi(t, "fallback", e.target.value)}
                      >
                        <option value="">— không đặt —</option>
                        {ungVien(t)
                          .filter((u) => u.id !== giaTri(t, "used"))
                          .map((u) => (
                            <option key={u.id} value={u.id}>
                              {u.label}
                              {u.available ? "" : " — chưa sẵn sàng"}
                            </option>
                          ))}
                      </select>
                    </label>
                  )}
                  <span className="col-span-3 text-[11px] text-ink-2">
                    {t.hieu_luc.engine === null
                      ? "chưa chạy được: model đang chọn không hoạt động và chưa có dự phòng"
                      : `đang chạy: ${t.hieu_luc.engine}` +
                        (t.hieu_luc.ly_do === "du-phong" ? " (model dự phòng)" : "")}
                  </span>
                </div>
              ))}
            </section>
          ))}
        </div>

        <footer className="flex items-center gap-3 border-t border-rule px-5 py-3">
          <button
            onClick={() => void luu()}
            disabled={dangLuu || du === null}
            className="rounded-sm bg-ink-0 px-3 py-1.5 text-[12px] font-medium text-panel-1 disabled:opacity-50"
          >
            {dangLuu ? "Đang lưu…" : "Lưu cài đặt"}
          </button>
          <button
            onClick={khoiPhuc}
            disabled={du === null}
            className="rounded-sm border border-rule px-3 py-1.5 text-[12px] text-ink-1 disabled:opacity-50"
          >
            Khôi phục
          </button>
          {daLuu && <span className="text-[11.5px] text-ink-2">đã lưu</span>}
        </footer>
      </div>
    </div>
  );
}
