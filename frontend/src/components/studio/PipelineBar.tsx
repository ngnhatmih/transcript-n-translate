import { Check, Loader2, Lock } from "lucide-react";
import type { BuocDuongOng } from "@/lib/studio";
import { cn } from "@/lib/utils";

/**
 * THANH CAC BUOC XU LY — mot hang ngang, khong bao gio xuong dong.
 *
 * 🔴 YEU CAU: "ten cac buoc o thanh tren cung khong bi xuong dong nua".
 *
 * Van de that nam o CHO NAO duoc phep xuong dong. Ban cu co
 * `whitespace-nowrap` tren `<li>` — tuc la no DA cam ten buoc xuong dong.
 * Nhung `whitespace-nowrap` chi cam NGAT DONG BEN TRONG mot khoi; no khong cam
 * mot khoi bi bop hep. Khi khung qua hep, `flex` van CO `<li>` lai, va den mot
 * muc nao do phan chu bi CAT CUT (`overflow: hidden` ngam cua flex item) chu
 * khong phai xuong dong.
 *
 * Do tren khung 375 px: sau khi tru tieu de va hai nut, thanh buoc con ~200 px.
 * Buoc dai nhat ("Long tieng · vieu-v3-turbo") ~ 170 px, cong bon buoc con lai
 * ~ 380 px nua => 550 px can, 200 px co. Ban cu cat cut phan chuoi.
 *
 * Cach sua, va vi sao khong phai "thu nho chu":
 *   · `shrink-0` tren tung `<li>`  -> khoi KHONG bi bop, nen khong bao gio cut chu.
 *   · `overflow-x-auto` o khung ngoai -> phan thua CUON NGANG, va nguoi dung
 *     vuot de xem buoc cuoi. Do la hanh vi dung cho mot day buoc dai: giu nguyen
 *     kich thuoc chu de doc duoc, thay vi thu nho den muc khong doc noi.
 *   · `whitespace-nowrap` tren CA HAI dong (ten va ghi chu) -> khong ngat giua
 *     chung. Ban cu chi dat o `<li>`, nen dong `note` van co the xuong dong rieng
 *     va lam khoi cao len bat thuong so voi cac khoi khac.
 *
 * `items-stretch` + `h-full` giu cac khoi cao bang nhau du mot khoi co ghi chu
 * dai — neu khong, khoi co `note` dai se cao hon va thanh buoc bi rang cua.
 */
export function PipelineBar({ steps, onStep }: { steps: BuocDuongOng[]; onStep: (id: string) => void }) {
  return (
    <ol className="flex min-w-0 items-stretch overflow-x-auto" aria-label="Các bước xử lý">
      {steps.map((s, i) => (
        <li key={s.id} className="flex shrink-0 items-center whitespace-nowrap">
          {i > 0 && <span className="mx-1 h-px w-4 shrink-0 bg-rule" aria-hidden />}
          <button
            onClick={() => onStep(s.id)}
            title={s.note}
            className={cn(
              "flex h-full items-center gap-2 whitespace-nowrap rounded-sm px-2 py-1 text-left transition-colors hover:bg-panel-2",
              s.id === "export" && s.state !== "blocked" && "bg-signal text-primary-foreground hover:bg-signal/90",
            )}
          >
            <span
              className={cn(
                "grid size-4 shrink-0 place-items-center rounded-full border text-[9px]",
                s.state === "done" && "border-ok bg-ok text-panel-0",
                s.state === "running" && "border-signal text-signal",
                s.state === "blocked" && "border-ink-2 text-ink-2",
                s.state === "todo" && "border-ink-2",
                s.id === "export" && s.state !== "blocked" && "border-panel-0 text-panel-0",
              )}
            >
              {s.state === "done" && <Check className="size-2.5" />}
              {s.state === "running" && <Loader2 className="size-2.5 animate-spin" />}
              {s.state === "blocked" && <Lock className="size-2" />}
            </span>
            <span className="whitespace-nowrap leading-tight">
              <span className="block whitespace-nowrap text-[12px] font-medium">{s.name}</span>
              <span
                className={cn(
                  "num block whitespace-nowrap text-[9.5px]",
                  s.id === "export" && s.state !== "blocked"
                    ? "text-panel-0"
                    : s.state === "blocked"
                      ? "text-signal"
                      : "text-ink-2",
                )}
              >
                {s.note}
              </span>
            </span>
          </button>
        </li>
      ))}
    </ol>
  );
}
