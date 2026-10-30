import { forwardRef } from "react";
import { Check, Play, RotateCcw } from "lucide-react";

import {
  NGUONG_NEN,
  soVi,
  tachTuKhac,
  viecCuaDong,
  type Dong,
} from "@/lib/studio";
import { formatTimecode } from "@/lib/timecode";
import { cn } from "@/lib/utils";

/**
 * MOT DONG PHU DE — ba goc nhin: Bien tap / Doi chieu / Long tieng.
 *
 * NGUON GOC: `_lovable-code/src/components/studio/SegmentRow.tsx` (206 dong).
 *
 * ## Ba cho BIA da bi thay, va bang gi
 *
 *  1. **`cps(seg)`** — ban goc tu tinh `chu.length / (end-start)` voi `Math.max(0.01, ...)`,
 *     nen doan 1,2 s chua 66 ky tu luon bao "CPS cao" du ban dich hoan hao. Repo co CPS
 *     THAT tu `GET /api/translations/{id}` (bang `TranslationCps`, co co `over`). Doc
 *     `seg.cps` va `seg.cpsOver` — khong tu chia.
 *
 *  2. **`compressRatio(seg)`** — ban goc doc `seg.take` / `duration()`, va `seg.take` la
 *     mot so hang so trong `SAMPLE_SEGMENTS`. Repo co take THAT (`DubPlanRow.take`, do
 *     dai cau long tieng da tao) — `seg.tiLeNen` la ti le do, `null` khi CHUA long.
 *     `null` khac `0`: chua long khong phai "take dai 0 giay".
 *
 *  3. **`ENGINES` + `GLOSSARY`** — hai hang so cua ban mau. `ENGINES` gia dinh dung hai
 *     engine (`opus`, `qwen`) va `Segment.translations` giu BAN DICH CUA CA HAI cung luc.
 *     Backend khong lam the: mot ban dich = mot engine, va engine do la `TranslationDetail.engine`.
 *     `GLOSSARY` la ba thuat ngu viet tay. Ca hai khong duoc chuyen sang.
 *
 * Vi vay goc nhin "Doi chieu" o day so BAN GOC voi BAN DICH — hai cot THAT, khong phai
 * hai engine bia. `tachTuKhac` danh dau tu khac nhau giua hai ban.
 */

export type ViewMode = "edit" | "compare" | "dub";

interface Props {
  seg: Dong;
  /** So thu tu 1..N cua dong trong ban ghi — nhan nguoi doc, KHAC `seg.i`. */
  soThuTu: number;
  current: boolean;
  view: ViewMode;
  flash: boolean;
  onSelect: () => void;
  onText: (t: string) => void;
  onApprove: () => void;
  onPreview: () => void;
  onRedub: () => void;
}

export const SegmentRow = forwardRef<HTMLLIElement, Props>(function SegmentRow(
  { seg, soThuTu, current, view, flash, onSelect, onText, onApprove, onPreview, onRedub },
  ref,
) {
  const issues = viecCuaDong(seg);
  const banDich = seg.dich === "" ? seg.text : seg.dich;

  return (
    <li
      ref={ref}
      onClick={onSelect}
      className={cn(
        "relative grid grid-cols-[88px_1fr_auto] gap-x-4 border-b border-rule px-4 py-2.5 transition-colors",
        current ? "bg-signal-soft" : "hover:bg-panel-1",
        issues.length > 0 && "hatch-left",
        flash && "animate-flash",
      )}
    >
      {current && <span className="absolute inset-y-0 left-0 w-[3px] bg-signal" />}
      <div className={cn("num pt-1 text-[10.5px] leading-4", current ? "text-signal" : "text-ink-2")}>
        <div>{formatTimecode(seg.start)}</div>
        <div>{formatTimecode(seg.end)}</div>
      </div>

      <div className="min-w-0 space-y-1.5">
        {view === "edit" && (
          <>
            <input
              value={seg.dich}
              onChange={(e) => onText(e.target.value)}
              onFocus={onSelect}
              className="w-full bg-transparent text-[15px] leading-6 text-ink-0 outline-none focus:border-b focus:border-signal"
              aria-label={`Phụ đề đoạn ${seg.i}`}
              placeholder={seg.text}
            />
            <p className="text-[11.5px] text-ink-2">gốc: {seg.text}</p>
          </>
        )}
        {view === "compare" && (
          <div className="grid grid-cols-2 gap-3">
            <div className="rounded-sm border border-rule p-2 text-left">
              <span className="label-engraved mb-1 block">Bản gốc</span>
              <span className="text-[13.5px] leading-5 text-ink-1">{seg.text}</span>
            </div>
            <div className="rounded-sm border border-signal p-2 text-left">
              <span className="label-engraved mb-1 block">Bản dịch</span>
              <span className="text-[13.5px] leading-5 text-ink-0">
                {tachTuKhac(seg.text, banDich).map((p, i) =>
                  p.khac ? (
                    <mark key={i} className="rounded-sm bg-signal-soft px-0.5 text-ink-0">
                      {p.chu}
                    </mark>
                  ) : (
                    <span key={i}>{p.chu}</span>
                  ),
                )}
              </span>
            </div>
          </div>
        )}
        {view === "dub" && (
          <div className="flex items-center gap-3">
            <p className="flex-1 text-[14px] text-ink-0">{banDich}</p>
            <div className="h-1.5 w-32 overflow-hidden rounded-sm bg-panel-3" title="Take so với khung thời gian">
              <div
                className={cn(
                  "h-full",
                  seg.tiLeNen === null ? "bg-panel-3" : seg.tiLeNen > NGUONG_NEN ? "bg-signal" : seg.tiLeNen > 1 ? "bg-ink-1" : "bg-ok",
                )}
                style={{ width: `${seg.tiLeNen === null ? 0 : Math.min(100, (seg.tiLeNen / 2) * 100)}%` }}
              />
            </div>
            <span
              className={cn(
                "num w-12 text-right text-[10.5px]",
                seg.tiLeNen === null ? "text-ink-2" : seg.tiLeNen > NGUONG_NEN ? "text-signal" : "text-ink-1",
              )}
              title={seg.tiLeNen === null ? "chưa lồng đoạn này" : "độ dài take / khung thời gian"}
            >
              {seg.tiLeNen === null ? "—" : `${soVi(seg.tiLeNen, 2)}×`}
            </span>
            <button
              onClick={(e) => {
                e.stopPropagation();
                onPreview();
              }}
              className="rounded-sm border border-rule p-1.5 text-ink-1 hover:border-ink-1 hover:text-ink-0"
              aria-label="Nghe thử"
              title="Nghe thử"
            >
              <Play className="size-3" />
            </button>
            <button
              onClick={(e) => {
                e.stopPropagation();
                onRedub();
              }}
              className="rounded-sm border border-rule p-1.5 text-ink-1 hover:border-ink-1 hover:text-ink-0"
              aria-label="Lồng lại"
              title="Lồng lại câu này"
            >
              <RotateCcw className="size-3" />
            </button>
          </div>
        )}
        {/*
          NHAN VIEC — chi ve viec KHONG hien o cot phai.

          Cot phai (dong 173..) da in `34,3 cps`, nen ve them mot nhan "CPS 34,3" o day la
          cung mot con so hai lan tren cung mot dong. Ban dau khoi nay in CA BA loai, va
          anh do cho thay dung loi do: "CPS 34,3" xuat hien hai lan.

          Giu lai `nghi-ngo` (cot phai khong noi gi ve co nay) va `nen` (cot phai chi ve
          ti le, khong noi do la van de). Bo `cps` — no da co cho rieng.
        */}
        {issues.some((i) => i.loai !== "cps") && (
          <div className="flex flex-wrap gap-2">
            {issues
              .filter((i) => i.loai !== "cps")
              .map((i) => (
                <span key={i.loai} className="label-engraved !text-fault">
                  {i.nhan}
                </span>
              ))}
          </div>
        )}
      </div>

      <div className="flex flex-col items-end gap-1.5 pt-0.5">
        <span
          className={cn("num text-[10.5px]", seg.cpsOver ? "text-fault" : "text-ink-2")}
          title={
            seg.cps === null
              ? `đoạn ${soThuTu} · chưa có bản dịch — chưa đo được CPS`
              : `đoạn ${soThuTu} · ký tự mỗi giây · ngưỡng ${soVi(seg.maxCps, 1)}`
          }
        >
          {seg.cps === null ? "— cps" : `${soVi(seg.cps, 1)} cps`}
        </span>
        {/*
          NUT DUYET — dau ✓ CHI hien khi da duyet that.

          Ban dau `<Check>` ve vo dieu kien va chi doi mau chu, nen anh do cho thay
          CA 438 dong deu co dau ✓ xanh trong khi `da duyet 0/438 doan`. Mot dau ✓ la
          mot LOI HUA "dong nay xong roi"; ve no khi chua duyet la noi doi ve du lieu.
        */}
        <button
          onClick={(e) => {
            e.stopPropagation();
            onApprove();
          }}
          className={cn(
            "flex items-center gap-1 rounded-sm border px-2 py-0.5 text-[11px] transition-colors",
            seg.daDuyet
              ? "border-ok/60 text-ok"
              : "border-rule text-ink-1 hover:border-signal hover:text-signal",
          )}
          aria-pressed={seg.daDuyet}
          aria-label={seg.daDuyet ? `bo duyet doan ${soThuTu}` : `duyet doan ${soThuTu}`}
        >
          {seg.daDuyet && <Check className="size-3" />}
          {seg.daDuyet ? "đã duyệt" : "duyệt"}
        </button>
      </div>
    </li>
  );
});
