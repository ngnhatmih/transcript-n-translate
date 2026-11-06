import { useCallback, useEffect, useState } from "react";

import { getModelSettings, putModelSettings } from "@/api/endpoints";
import type { ModelSettings, ModelSettingsIn, ModelTask } from "@/api/types";

/**
 * BẢNG "CÀI ĐẶT MODEL" — mở từ bảng lệnh (Ctrl+K → "Cài đặt model").
 *
 * ## Ngôn ngữ thị giác: LẤY TỪ CHÍNH ỨNG DỤNG, không phải từ một bộ UI mẫu
 *
 * Ứng dụng này là "phòng thu biên tập": graphite ấm, MỘT màu nhấn amber, chữ Archivo +
 * IBM Plex Mono, bán kính 2 px, đường kẻ 1 px (`--rule`), nhãn nhỏ chữ hoa giãn chữ
 * (`label-engraved`), số canh cột (`num`). Bảng này vẽ bằng ĐÚNG sáu token đó — không
 * bo tròn lớn, không bóng đổ, không thẻ (card) lồng nhau:
 *
 *   · mỗi VIỆC là MỘT DÒNG của một bảng đặc tả: số thứ tự mono, tên việc, hai ô chọn;
 *   · nhóm việc là một nhãn khắc + đường kẻ, KHÔNG phải hộp có viền;
 *   · chỉ amber cho thứ "đang chạy", và chỉ hiện khi nó KHÁC ô đang chọn.
 *
 * ## Bốn luật hành vi (mỗi luật một lần đã trả giá)
 *
 * 1. **Danh sách ứng viên do BACKEND trả** — thêm model = thêm dữ liệu, không sửa tệp này.
 * 2. **`locked` thì KHÔNG vẽ ô dự phòng**: ô chỉ có một lựa chọn là ô nói dối rằng có thể
 *    chọn. Việc đó vẫn hiện, kèm chữ "chỉ có một model".
 * 3. **Chỉ hiện "đang chạy" khi nó KHÁC điều đang chọn.** Bản đầu in "đang chạy: X" cho cả
 *    sáu dòng — với dòng đang dùng đúng model đã chọn thì đó là câu lặp lại y nguyên ô chọn
 *    ngay trên nó, sáu lần. Nay dòng đó chỉ xuất hiện khi model đang chọn KHÔNG chạy được và
 *    hệ thống đã lấy dự phòng (hoặc không còn đường nào) — tức chỉ khi nó nói thêm điều gì.
 * 4. **Chỉ gửi việc đã đổi**: bấm Lưu mà gửi cả bảng thì mọi dòng chưa ai đụng bị ghi đè
 *    bằng giá trị đang hiện, kể cả khi backend vừa đổi mặc định.
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

  //: Escape đóng bảng. `CommandPalette` đã có phím này; thiếu ở đây thì bảng cài đặt là
  //: hộp thoại DUY NHẤT trong ứng dụng bắt người dùng đi tìm chuột.
  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open, onClose]);

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
    // "Khôi phục" = ghi lại ĐÚNG giá trị mặc định backend trả (`mac_dinh`), không xoá khoá
    // nào: một khoá bị xoá và một khoá mang giá trị mặc định là hai trạng thái khác nhau
    // trong DB, và chỉ cái thứ hai là thứ nút này hứa.
    if (du === null) return;
    const tatCa: Record<string, { used: string | null; fallback: string | null }> = {};
    for (const t of du.tasks) tatCa[t.id] = { ...t.mac_dinh };
    setNhap(tatCa);
    setNhomDich(du.nhom_dich);
    setDaLuu(false);
  };

  //: Nhóm theo `task.nhom`, GIỮ ĐÚNG thứ tự backend trả (thứ tự khai trong domain).
  //:
  //: ⚠️ CỐ Ý KHÔNG dùng `useMemo`: khối này nằm SAU `if (!open) return null` ở trên, nên
  //: một hook ở đây làm số hook của lần render "đóng" khác lần render "mở" → React ném
  //: *"Rendered more hooks than during the previous render"* và CẢ TRANG thành "Trang này
  //: không tải được". ĐO ĐƯỢC đúng thế ở lượt đầu của bản này: mở panel từ Ctrl+K làm sập
  //: trang. Sáu dòng thì tính thẳng, không cần nhớ.
  const nhom: Array<{ ten: string; viec: ModelTask[] }> = [];
  for (const t of du?.tasks ?? []) {
    const cuoi = nhom[nhom.length - 1];
    if (cuoi !== undefined && cuoi.ten === t.nhom) cuoi.viec.push(t);
    else nhom.push({ ten: t.nhom, viec: [t] });
  }

  const giaTri = (t: ModelTask, khoa: "used" | "fallback") =>
    nhap[t.id]?.[khoa] ?? t[khoa] ?? "";

  /**
   * Ứng viên để vẽ. Việc `dich` lọc theo NHÓM đang chọn, NHƯNG luôn giữ giá trị đang lưu:
   * đổi sang LLM khi đang dùng `opus-mt` mà bỏ nó khỏi danh sách thì ô chọn hiện TRỐNG và
   * người dùng mất lựa chọn cũ mà không hiểu vì sao — `select` của React không có giá trị
   * nằm ngoài `options` thì hiển thị ô rỗng.
   */
  const ungVien = (t: ModelTask) => {
    const tatCa = t.candidates;
    if (t.id !== "dich" || nhomDich === null) return tatCa;
    const loc = tatCa.filter((u) => u.nhom === null || u.nhom === nhomDich);
    const dangDung = giaTri(t, "used");
    const conThieu = tatCa.find((u) => u.id === dangDung && !loc.some((l) => l.id === u.id));
    return conThieu ? [conThieu, ...loc] : loc;
  };

  const soThuTu = (id: string) => {
    const i = (du?.tasks ?? []).findIndex((t) => t.id === id);
    return i < 0 ? "" : String(i + 1).padStart(2, "0");
  };

  const nutPhu =
    "rounded-sm border border-rule px-3 py-1.5 text-[12px] text-ink-1 transition-colors " +
    "duration-150 hover:border-ink-1 hover:text-ink-0 active:translate-y-px disabled:opacity-40";
  const oChon =
    "h-8 w-full appearance-none rounded-sm border border-rule bg-panel-0 px-2 pr-7 " +
    "text-[12.5px] text-ink-0 transition-colors duration-150 hover:border-ink-2 " +
    "disabled:opacity-50";

  return (
    <div
      className="fixed inset-0 z-50 grid place-items-start justify-center overflow-y-auto bg-panel-0/80 py-[8vh] backdrop-blur-[2px]"
      onClick={onClose}
    >
      {/*: Vệt amber 2 px ở mép trên: cùng dấu hiệu "bề mặt đang mở" mà panel Hàng đợi dùng,
          để bảng này thuộc về ứng dụng chứ không phải một hộp thoại lạc vào. */}
      <div
        className="w-[720px] max-w-[94vw] border border-rule bg-panel-1 shadow-2xl"
        onClick={(e) => e.stopPropagation()}
        role="dialog"
        aria-modal="true"
        aria-label="Cài đặt model"
      >
        <div className="h-[2px] bg-signal/70" />

        <header className="flex items-start justify-between gap-6 px-6 pb-4 pt-5">
          <div className="min-w-0">
            <h2 className="text-[17px] font-semibold leading-none tracking-tight text-ink-0">
              Cài đặt model
            </h2>
            <p className="mt-2 max-w-[52ch] text-[12px] leading-relaxed text-ink-2">
              Model sử dụng được ưu tiên. Khi nó không chạy được trên máy này, hệ thống tự
              chuyển sang model dự phòng và ghi rõ ở dòng đó.
            </p>
          </div>
          <div className="flex shrink-0 items-center gap-2">
            <span className="kbd">Esc</span>
            <button
              onClick={onClose}
              aria-label="Đóng cài đặt model"
              className="grid size-7 place-items-center rounded-sm border border-rule text-[15px] leading-none text-ink-2 transition-colors duration-150 hover:border-ink-1 hover:text-ink-0 active:translate-y-px"
            >
              ×
            </button>
          </div>
        </header>

        {loi !== null && (
          <p
            role="alert"
            className="hatch-left border-y border-rule bg-signal-soft px-6 py-2 text-[12px] text-ink-0"
          >
            {loi}
          </p>
        )}

        <div className="max-h-[64vh] overflow-y-auto">
          {/*: TIÊU ĐỀ CỘT MỘT LẦN cho cả bảng, dính trên cùng khi cuộn. Bản trước để nó
              trong TỪNG nhóm, nên bốn nhóm là bốn lần cùng một hàng chữ — cột đã thẳng
              hàng thì không cần nhắc lại; nhãn nhóm đủ để tách. */}
          {du !== null && (
            <div className="sticky top-0 z-10 grid grid-cols-[26px_132px_1fr_1fr] items-end gap-x-3 border-b border-rule bg-panel-1 px-6 pb-1 pt-2">
              <span className="num text-[10px] text-ink-2">#</span>
              <span className="label-engraved">việc</span>
              <span className="label-engraved">Model sử dụng</span>
              <span className="label-engraved">Model mặc định (dự phòng)</span>
            </div>
          )}
          {du === null && loi === null && (
            /*: Skeleton ĐÚNG hình dạng bảng (3 nhóm × 2 dòng), không phải một vòng xoay:
                vòng xoay không cho biết cái gì sắp hiện ra và nhảy layout khi dữ liệu về. */
            <div className="px-6 py-4" aria-busy="true" aria-label="Đang nạp cài đặt model">
              {[0, 1, 2].map((g) => (
                <div key={g} className="mb-5">
                  <div className="mb-2 h-[9px] w-24 animate-pulse rounded-sm bg-panel-3" />
                  {[0, 1].map((r) => (
                    <div key={r} className="flex items-center gap-3 border-t border-rule/60 py-2.5">
                      <div className="h-3 w-4 animate-pulse rounded-sm bg-panel-3" />
                      <div className="h-3 w-28 animate-pulse rounded-sm bg-panel-3" />
                      <div className="ml-auto h-8 w-44 animate-pulse rounded-sm bg-panel-2" />
                      <div className="h-8 w-44 animate-pulse rounded-sm bg-panel-2" />
                    </div>
                  ))}
                </div>
              ))}
            </div>
          )}

          {nhom.map((g) => (
            <section key={g.ten}>
              <h3 className="flex items-center gap-3 px-6 pb-1 pt-4">
                <span className="label-engraved">{g.ten}</span>
                <span aria-hidden="true" className="h-px flex-1 bg-rule/60" />
              </h3>
              {g.ten === "Dịch" && (
                <div className="flex flex-wrap items-center gap-x-5 gap-y-1 border-b border-rule/60 bg-panel-2/40 px-6 py-2 text-[11.5px] text-ink-1">
                  <span className="label-engraved">Dịch bằng</span>
                  {(["mt", "llm"] as const).map((n) => {
                    const chon = nhomDich === n;
                    return (
                      <label
                        key={n}
                        className={
                          "flex cursor-pointer items-center gap-1.5 transition-colors duration-150 " +
                          (chon ? "text-ink-0" : "hover:text-ink-0")
                        }
                      >
                        <input
                          type="radio"
                          name="nhom-dich"
                          className="size-3 accent-[var(--signal)]"
                          checked={chon}
                          onChange={() => {
                            setDaLuu(false);
                            setNhomDich(n);
                          }}
                        />
                        {n === "mt" ? "MT (dịch máy)" : "LLM (mô hình ngôn ngữ)"}
                      </label>
                    );
                  })}
                  <span className="text-ink-2">chỉ lọc danh sách hiện ra</span>
                </div>
              )}

              {g.viec.map((t) => {
                const duPhong = t.hieu_luc.ly_do === "du-phong";
                const khongCo = t.hieu_luc.ly_do === "khong-co";
                return (
                  <div
                    key={t.id}
                    className="grid grid-cols-[26px_132px_1fr_1fr] items-center gap-x-3 gap-y-1 border-b border-rule/60 px-6 py-2.5 transition-colors duration-150 last:border-b-0 hover:bg-panel-2/30"
                  >
                    <span className="num text-[10.5px] text-ink-2">{soThuTu(t.id)}</span>
                    <span className="text-[12.5px] text-ink-0">{t.label}</span>

                    <span className="relative block min-w-0">
                      <select
                        aria-label={`model sử dụng của ${t.label}`}
                        className={oChon}
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
                      <span
                        aria-hidden="true"
                        className="pointer-events-none absolute right-2 top-1/2 -translate-y-1/2 text-[9px] text-ink-2"
                      >
                        ▾
                      </span>
                    </span>

                    {t.locked ? (
                      <span className="min-w-0 self-center text-[11px] text-ink-2">
                        chỉ có một model
                      </span>
                    ) : (
                      <span className="relative block min-w-0">
                        <select
                          aria-label={`model dự phòng của ${t.label}`}
                          className={oChon}
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
                        <span
                          aria-hidden="true"
                          className="pointer-events-none absolute right-2 top-1/2 -translate-y-1/2 text-[9px] text-ink-2"
                        >
                          ▾
                        </span>
                      </span>
                    )}

                    {/*: Chỉ hiện khi câu này NÓI THÊM ĐIỀU GÌ: model đang chạy khác model
                        đang chọn (đã rơi về dự phòng), hoặc không còn đường nào chạy. */}
                    {(duPhong || khongCo) && (
                      <p className="col-span-4 mt-0.5 flex items-center gap-2 text-[11px] leading-tight">
                        <span
                          aria-hidden="true"
                          className={
                            "size-1.5 rounded-full " +
                            (khongCo ? "bg-fault" : "bg-signal")
                          }
                        />
                        <span className={khongCo ? "text-fault" : "text-ink-1"}>
                          {khongCo
                            ? "chưa chạy được: model đang chọn không hoạt động và chưa có dự phòng"
                            : "đang chạy bằng model dự phòng: "}
                        </span>
                        {!khongCo && (
                          <code className="num text-[11px] text-ink-0">
                            {t.hieu_luc.engine}
                          </code>
                        )}
                      </p>
                    )}
                  </div>
                );
              })}
            </section>
          ))}
        </div>

        <footer className="flex items-center gap-3 border-t border-rule bg-panel-0/40 px-6 py-3">
          <button
            onClick={() => void luu()}
            disabled={dangLuu || du === null}
            className="rounded-sm bg-signal px-3.5 py-1.5 text-[12px] font-semibold text-panel-0 transition-transform duration-150 hover:brightness-110 active:translate-y-px disabled:opacity-40"
          >
            {dangLuu ? "Đang lưu…" : "Lưu cài đặt"}
          </button>
          <button onClick={khoiPhuc} disabled={du === null} className={nutPhu}>
            Khôi phục
          </button>
          {daLuu && (
            <span role="status" className="animate-flash num px-2 py-0.5 text-[11px] text-ok">
              đã lưu
            </span>
          )}
          <span className="ml-auto text-[11px] text-ink-2">
            {Object.keys(nhap).length > 0
              ? `${Object.keys(nhap).length} việc chưa lưu`
              : "chưa có thay đổi"}
          </span>
        </footer>
      </div>
    </div>
  );
}
