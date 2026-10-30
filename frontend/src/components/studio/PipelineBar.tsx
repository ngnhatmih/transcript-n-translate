import { Check, Loader2, Lock } from "lucide-react";
import type { BuocDuongOng } from "@/lib/studio";
import { cn } from "@/lib/utils";

export function PipelineBar({ steps, onStep }: { steps: BuocDuongOng[]; onStep: (id: string) => void }) {
  return (
    <ol className="flex min-w-0 items-stretch" aria-label="Các bước xử lý">
      {steps.map((s, i) => (
        <li key={s.id} className="flex items-center">
          {i > 0 && <span className="mx-1 h-px w-4 bg-rule" aria-hidden />}
          <button
            onClick={() => onStep(s.id)}
            title={s.note}
            className={cn(
              "flex items-center gap-2 rounded-sm px-2 py-1 text-left transition-colors hover:bg-panel-2",
              s.id === "export" && s.state !== "blocked" && "bg-signal text-primary-foreground hover:bg-signal/90",
            )}
          >
            <span
              className={cn(
                "grid size-4 place-items-center rounded-full border text-[9px]",
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
            <span className="leading-tight">
              <span className="block text-[12px] font-medium">{s.name}</span>
              <span
                className={cn(
                  "num block text-[9.5px]",
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
