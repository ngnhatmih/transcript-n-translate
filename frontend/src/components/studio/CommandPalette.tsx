import { useEffect, useMemo, useRef, useState } from "react";
import { cn } from "@/lib/utils";

export interface Command {
  id: string;
  label: string;
  hint?: string;
  run: () => void;
}

export function CommandPalette({
  open,
  onClose,
  commands,
}: {
  open: boolean;
  onClose: () => void;
  commands: Command[];
}) {
  const [q, setQ] = useState("");
  const [idx, setIdx] = useState(0);
  const inputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    if (open) {
      setQ("");
      setIdx(0);
      setTimeout(() => inputRef.current?.focus(), 0);
    }
  }, [open]);

  const list = useMemo(() => {
    const n = q.trim().toLowerCase();
    return n ? commands.filter((c) => c.label.toLowerCase().includes(n)) : commands;
  }, [q, commands]);

  if (!open) return null;

  const run = (c?: Command) => {
    if (!c) return;
    onClose();
    c.run();
  };

  return (
    <div
      className="fixed inset-0 z-50 grid place-items-start justify-center bg-panel-0/70 pt-[15vh] backdrop-blur-[2px]"
      onClick={onClose}
    >
      <div
        className="w-[520px] max-w-[92vw] overflow-hidden rounded-sm border border-rule bg-panel-1 shadow-2xl"
        onClick={(e) => e.stopPropagation()}
        role="dialog"
        aria-label="Bảng lệnh"
      >
        <input
          ref={inputRef}
          value={q}
          onChange={(e) => {
            setQ(e.target.value);
            setIdx(0);
          }}
          onKeyDown={(e) => {
            if (e.key === "Escape") onClose();
            if (e.key === "ArrowDown") {
              e.preventDefault();
              setIdx((i) => Math.min(list.length - 1, i + 1));
            }
            if (e.key === "ArrowUp") {
              e.preventDefault();
              setIdx((i) => Math.max(0, i - 1));
            }
            if (e.key === "Enter") run(list[idx]);
          }}
          placeholder="Gõ lệnh…"
          className="w-full border-b border-rule bg-transparent px-4 py-3 text-[14px] text-ink-0 outline-none placeholder:text-ink-2"
        />
        <ul className="max-h-80 overflow-y-auto py-1">
          {list.map((c, i) => (
            <li key={c.id}>
              <button
                onMouseEnter={() => setIdx(i)}
                onClick={() => run(c)}
                className={cn(
                  "flex w-full items-center justify-between px-4 py-2 text-left text-[13px]",
                  i === idx ? "bg-signal-soft text-ink-0" : "text-ink-1",
                )}
              >
                {c.label}
                {c.hint && <span className="kbd">{c.hint}</span>}
              </button>
            </li>
          ))}
          {list.length === 0 && <li className="px-4 py-3 text-ink-2">Không có lệnh nào khớp</li>}
        </ul>
      </div>
    </div>
  );
}
