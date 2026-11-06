import { useCallback, useEffect, useState } from "react";

import { getModelSettings, putModelSettings } from "@/api/endpoints";
import type { ModelCandidate, ModelSettings, ModelSettingsIn, ModelTask } from "@/api/types";

import { ChonModel, ChonNhom } from "./ChonModel";

/**
 * BẢNG "CÀI ĐẶT MODEL" — mở từ bảng lệnh (Ctrl+K → "Cài đặt model").
 *
 * ## Ngôn ngữ thị giác: LẤY TỪ CHÍNH ỨNG DỤNG, không phải từ một bộ UI mẫu
 *
 * Ứng dụng này là "phòng thu biên tập": graphite ấm, MỘT màu nhấn amber, chữ Archivo +
 * IBM Plex Mono, bán kính 2 px, đường kẻ 1 px (`--rule`), nhãn nhỏ chữ hoa giãn chữ
 * (`label-engraved`), số canh cột (`num`). Bảng này vẽ bằng ĐÚNG sáu token đó — không bo
 * tròn lớn, không bóng đổ, không thẻ (card) lồng nhau.
 *
 * ## Luật hành vi (mỗi luật một lần đã trả giá)
 *
 * 1. **Danh sách ứng viên do BACKEND trả** — thêm model = thêm dữ liệu, không sửa tệp này.
 * 2. **`locked` thì KHÔNG vẽ ô dự phòng**: ô chỉ có một lựa chọn là ô nói dối rằng có thể
 *    chọn. Việc đó vẫn hiện, kèm chữ "chỉ có một model".
 * 3. **Chỉ hiện "đang chạy" khi nó KHÁC điều đang chọn** — nếu không thì đó là câu lặp lại
 *    y nguyên ô chọn ngay trên nó, sáu lần.
 * 4. **Chỉ gửi việc đã đổi**: bấm Lưu mà gửi cả bảng thì mọi dòng chưa ai đụng bị ghi đè,
 *    kể cả khi backend vừa đổi mặc định.
 * 5. **Nhóm MT/LLM LỌC THẬT danh sách, và phải đổi được cả giá trị đang chọn.** Bản trước
 *    giữ lại model đang lưu kể cả khi nó khác nhóm (để ô không bị rỗng) — hậu quả: đang ở
 *    MT mà danh sách vẫn có `hy-mt-1.5-7b` (một engine LLM), đúng câu chủ dự án báo. Nay
 *    đổi nhóm thì danh sách chỉ còn engine CỦA NHÓM ĐÓ, và nếu model đang chọn không thuộc
 *    nhóm mới thì nó được đổi sang ứng viên đầu của nhóm (thành thay đổi chưa lưu).
 * 6. **Nhóm MỞ ĐẦU lấy theo model đang chạy**, không lấy mù theo `nhom_dich` đã lưu: model
 *    đang chạy mới là sự thật, còn nhóm đã lưu có thể cũ (đổi `default_mt` trong registry
 *    là đủ để lệch). Nếu lấy mù, mở bảng ra sẽ thấy ô chọn trống ngay từ đầu.
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
      setNhomDich(nhomTheoModelDangChay(d));
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

  //: Escape đóng bảng. `CommandPalette` đã có phím này; thiếu ở đây thì bảng cài đặt là hộp
  //: thoại DUY NHẤT trong ứng dụng bắt người dùng đi tìm chuột.
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
    setNhomDich(nhomTheoModelDangChay(du));
    setDaLuu(false);
  };

  /** Ứng viên của một việc, ĐÃ LỌC theo nhóm đang chọn (việc `dich`). */
  const ungVien = (t: ModelTask): ModelCandidate[] => {
    if (t.id !== "dich" || nhomDich === null) return t.candidates;
    return t.candidates.filter((u) => u.nhom === null || u.nhom === nhomDich);
  };

  /** Giá trị đang hiện trong ô: bản nháp → giá trị đã lưu → ứng viên đầu của danh sách. */
  const giaTri = (t: ModelTask, khoa: "used" | "fallback"): string => {
    const ds = ungVien(t);
    const muon = nhap[t.id]?.[khoa] ?? t[khoa] ?? "";
    if (muon !== "" && ds.some((u) => u.id === muon)) return muon;
    return khoa === "used" ? (ds[0]?.id ?? "") : "";
  };

  /**
   * Đổi nhóm dịch: lọc lại danh sách VÀ đổi giá trị nếu model đang chọn không thuộc nhóm mới.
   *
   * Vì sao phải đổi giá trị chứ không chỉ lọc danh sách: listbox không hiển thị được một giá
   * trị nằm ngoài danh sách — ô sẽ TRỐNG, và người dùng mất lựa chọn cũ mà không hiểu vì
   * sao. Đổi sang ứng viên đầu của nhóm là hành vi nói thẳng: "nhóm này không có model đó".
   * Bản nháp được đánh dấu đổi, nên bấm Lưu là ghi thật.
   */
  const doiNhom = (n: "mt" | "llm") => {
    setDaLuu(false);
    setNhomDich(n);
    const t = du?.tasks.find((x) => x.id === "dich");
    if (t === undefined) return;
    const ds = t.candidates.filter((u) => u.nhom === null || u.nhom === n);
    const dau = ds[0]?.id ?? null;
    const usedHienTai = nhap[t.id]?.used ?? t.used ?? "";
    const fbHienTai = nhap[t.id]?.fallback ?? t.fallback ?? null;
    const usedMoi = ds.some((u) => u.id === usedHienTai) ? usedHienTai : dau;
    const fbMoi = fbHienTai !== null && ds.some((u) => u.id === fbHienTai) ? fbHienTai : null;
    setNhap((cu) => ({ ...cu, [t.id]: { used: usedMoi, fallback: fbMoi } }));
  };

  //: Nhóm theo `task.nhom`, GIỮ ĐÚNG thứ tự backend trả (thứ tự khai trong domain).
  //:
  //: ⚠️ CỐ Ý KHÔNG dùng `useMemo`: khối này nằm SAU `if (!open) return null` ở trên, nên
  //: một hook ở đây làm số hook của lần render "đóng" khác lần render "mở" → React ném
  //: *"Rendered more hooks than during the previous render"* và CẢ TRANG thành "Trang này
  //: không tải được". ĐO ĐƯỢC đúng thế ở lượt đầu của bản này. Sáu dòng thì tính thẳng.
  const nhom: Array<{ ten: string; viec: ModelTask[] }> = [];
  for (const t of du?.tasks ?? []) {
    const cuoi = nhom[nhom.length - 1];
    if (cuoi !== undefined && cuoi.ten === t.nhom) cuoi.viec.push(t);
    else nhom.push({ ten: t.nhom, viec: [t] });
  }

  const nhanCua = (t: ModelTask, id: string) =>
    t.candidates.find((u) => u.id === id)?.label ?? id;

  const soThuTu = (id: string) => {
    const i = (du?.tasks ?? []).findIndex((t) => t.id === id);
    return i < 0 ? "" : String(i + 1).padStart(2, "0");
  };

  const nutPhu =
    "rounded-sm border border-rule px-3 py-1.5 text-[12px] text-ink-1 transition-colors " +
    "duration-150 hover:border-ink-1 hover:text-ink-0 active:translate-y-px disabled:opacity-40";

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
          {/*: TIÊU ĐỀ CỘT MỘT LẦN cho cả bảng, dính trên cùng khi cuộn. Để nó trong TỪNG
              nhóm thì bốn nhóm là bốn lần cùng một hàng chữ — cột đã thẳng hàng thì không
              cần nhắc lại; nhãn nhóm đủ để tách. */}
          {du !== null && (
            <div className="sticky top-0 z-10 grid grid-cols-[26px_150px_1fr_1fr] items-end gap-x-3 border-b border-rule bg-panel-1 px-6 pb-1 pt-2">
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
                <div className="flex flex-wrap items-center gap-x-4 gap-y-2 border-b border-rule/60 bg-panel-2/40 px-6 py-2">
                  <span className="label-engraved">Dịch bằng</span>
                  <ChonNhom
                    nhan="nhóm dịch"
                    giaTri={nhomDich ?? "mt"}
                    luaChon={[
                      { id: "mt", label: "MT" },
                      { id: "llm", label: "LLM" },
                    ]}
                    onChon={(n) => doiNhom(n === "llm" ? "llm" : "mt")}
                  />
                  <span className="text-[11px] text-ink-2">
                    MT chạy trong máy · LLM chạy qua Ollama hoặc endpoint
                  </span>
                </div>
              )}

              {g.viec.map((t) => {
                const duPhong = t.hieu_luc.ly_do === "du-phong";
                const khongCo = t.hieu_luc.ly_do === "khong-co";
                const used = giaTri(t, "used");
                const fb = giaTri(t, "fallback");
                return (
                  <div
                    key={t.id}
                    className="grid grid-cols-[26px_150px_1fr_1fr] items-center gap-x-3 gap-y-1 border-b border-rule/60 px-6 py-2.5 transition-colors duration-150 last:border-b-0 hover:bg-panel-2/30"
                  >
                    <span className="num self-start pt-2 text-[10.5px] text-ink-2">
                      {soThuTu(t.id)}
                    </span>

                    {/*: TÊN VIỆC + TÊN MODEL ngay dưới nó. Đây là câu chủ dự án yêu cầu:
                        *"phần header của task phải hiện các tên model tương ứng ở dưới"*.
                        Cột chọn bên phải bị cắt bằng dấu ba chấm khi tên dài, nên tên đầy
                        đủ ở đây là chỗ ĐỌC ĐƯỢC, không phải chỗ trang trí. */}
                    <div className="min-w-0 self-start pt-1.5">
                      <span className="block text-[12.5px] text-ink-0">{t.label}</span>
                      <span
                        className="mt-0.5 block truncate text-[10.5px] leading-tight text-ink-2"
                        title={
                          nhanCua(t, used) + (fb !== "" ? ` · dự phòng: ${nhanCua(t, fb)}` : "")
                        }
                      >
                        {used === "" ? "chưa đặt" : nhanCua(t, used)}
                        {fb !== "" && <span> · dự phòng: {nhanCua(t, fb)}</span>}
                      </span>
                    </div>

                    <ChonModel
                      nhan={`model sử dụng của ${t.label}`}
                      giaTri={used}
                      ungVien={ungVien(t)}
                      onChon={(id) => doi(t, "used", id)}
                    />

                    {t.locked ? (
                      <span className="min-w-0 self-center text-[11px] text-ink-2">
                        chỉ có một model
                      </span>
                    ) : (
                      <ChonModel
                        nhan={`model dự phòng của ${t.label}`}
                        giaTri={fb}
                        ungVien={ungVien(t).filter((u) => u.id !== used)}
                        onChon={(id) => doi(t, "fallback", id)}
                        choPhepRong
                      />
                    )}

                    {/*: Chỉ hiện khi câu này NÓI THÊM ĐIỀU GÌ: model đang chạy khác model
                        đang chọn (đã rơi về dự phòng), hoặc không còn đường nào chạy. */}
                    {(duPhong || khongCo) && (
                      <p className="col-span-4 mt-0.5 flex items-center gap-2 text-[11px] leading-tight">
                        <span
                          aria-hidden="true"
                          className={"size-1.5 rounded-full " + (khongCo ? "bg-fault" : "bg-signal")}
                        />
                        <span className={khongCo ? "text-fault" : "text-ink-1"}>
                          {khongCo
                            ? "chưa chạy được: model đang chọn không hoạt động và chưa có dự phòng"
                            : "đang chạy bằng model dự phòng: "}
                        </span>
                        {!khongCo && (
                          <code className="num text-[11px] text-ink-0">{t.hieu_luc.engine}</code>
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

/**
 * Nhóm MỞ ĐẦU của việc `dich`: theo NHÓM CỦA MODEL ĐANG CHẠY, không theo `nhom_dich` đã lưu.
 *
 * ĐO ĐƯỢC (dữ liệu thật của máy này): `nhom_dich = "mt"` nhưng model đang chạy là
 * `hy-mt-1.5-7b` — một engine LLM (registry khai `runtime: ollama`). Mở bảng ra với nhóm
 * "mt" thì danh sách MT không chứa model đó, ô chọn TRỐNG ngay từ giây đầu. Nhóm đã lưu là
 * ý định cũ; model đang chạy là sự thật.
 */
function nhomTheoModelDangChay(d: ModelSettings): "mt" | "llm" {
  const dich = d.tasks.find((t) => t.id === "dich");
  const nhomCuaModel = dich?.candidates.find((u) => u.id === dich.used)?.nhom;
  if (nhomCuaModel === "mt" || nhomCuaModel === "llm") return nhomCuaModel;
  return d.nhom_dich;
}
