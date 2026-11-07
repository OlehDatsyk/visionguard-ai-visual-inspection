import { AlertTriangle, CheckCircle2, CircleDashed, CircleHelp, Eye, Loader2, ShieldCheck, ShieldQuestion, X, XCircle, type LucideIcon } from "lucide-react";
import { createContext, useCallback, useContext, useEffect, useRef, useState, type ButtonHTMLAttributes, type ReactNode } from "react";
import { useAuthedImage } from "../hooks/useApi";
import type { Band, ProjectStatus, ReviewStatus } from "../types";
import { BAND_LABELS, REVIEW_LABELS, STATUS_LABELS } from "../utils/format";

type Variant = "primary" | "secondary" | "ghost" | "danger";
const VARIANTS: Record<Variant, string> = {
  primary: "bg-accent text-ink-950 hover:bg-accent-strong font-semibold",
  secondary: "border border-ink-600 bg-ink-800 text-text-1 hover:bg-ink-700",
  ghost: "text-text-2 hover:bg-ink-800 hover:text-text-1",
  danger: "border border-red-500/40 bg-red-500/10 text-red-300 hover:bg-red-500/20",
};

interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: Variant;
  icon?: LucideIcon;
  busy?: boolean;
  small?: boolean;
}

export function Button({ variant = "secondary", icon: Icon, busy, small, children, className = "", disabled, type = "button", ...rest }: ButtonProps) {
  return (
    <button
      type={type}
      disabled={disabled || busy}
      className={`inline-flex items-center justify-center gap-1.5 whitespace-nowrap rounded-md transition-colors disabled:cursor-not-allowed disabled:opacity-50 ${small ? "h-7 px-2 text-xs" : "h-9 px-3 text-sm"} ${VARIANTS[variant]} ${className}`}
      {...rest}
    >
      {busy ? <Loader2 className="h-4 w-4 animate-spin" /> : Icon ? <Icon className="h-4 w-4" /> : null}
      {children}
    </button>
  );
}

export function Spinner({ label = "Loading" }: { label?: string }) {
  return (
    <div role="status" className="flex items-center justify-center gap-2 p-10 text-sm text-text-3">
      <Loader2 className="h-4 w-4 animate-spin" /> {label}
    </div>
  );
}

export function ErrorNote({ message, onRetry }: { message: string; onRetry?: () => void }) {
  return (
    <div role="alert" className="flex items-center justify-between gap-3 rounded-md border border-red-500/40 bg-red-500/10 px-3 py-2 text-sm text-red-200">
      <span>{message}</span>
      {onRetry && <Button small onClick={onRetry}>Retry</Button>}
    </div>
  );
}

export function Empty({ icon: Icon, title, children, action }: { icon: LucideIcon; title: string; children?: ReactNode; action?: ReactNode }) {
  return (
    <div className="flex flex-col items-center gap-2 px-6 py-12 text-center">
      <Icon className="h-7 w-7 text-text-3" />
      <h3 className="text-sm text-text-1">{title}</h3>
      {children && <p className="max-w-md text-sm text-text-3">{children}</p>}
      {action && <div className="mt-2 flex flex-wrap justify-center gap-2">{action}</div>}
    </div>
  );
}

export function PageHeader({ title, description, actions }: { title: string; description?: ReactNode; actions?: ReactNode }) {
  return (
    <header className="mb-5 flex flex-wrap items-start justify-between gap-3">
      <div className="min-w-0">
        <h1 className="text-xl text-text-1">{title}</h1>
        {description && <p className="mt-0.5 max-w-3xl text-sm text-text-3">{description}</p>}
      </div>
      {actions && <div className="flex flex-wrap items-center gap-2">{actions}</div>}
    </header>
  );
}

export function Card({ title, actions, children, className = "", bodyClass = "p-4" }: { title?: ReactNode; actions?: ReactNode; children: ReactNode; className?: string; bodyClass?: string }) {
  return (
    <section className={`card ${className}`}>
      {title && (
        <div className="flex items-center justify-between gap-2 border-b border-ink-700 px-4 py-2.5">
          <h2 className="text-[13px] text-text-1">{title}</h2>
          {actions}
        </div>
      )}
      <div className={bodyClass}>{children}</div>
    </section>
  );
}

const pill = "inline-flex items-center gap-1 whitespace-nowrap rounded px-1.5 py-0.5 text-[11px] font-medium";
const BAND_STYLE: Record<Band, { cls: string; icon: LucideIcon }> = {
  high: { cls: "bg-emerald-500/15 text-emerald-300", icon: ShieldCheck },
  medium: { cls: "bg-sky-500/15 text-sky-300", icon: ShieldCheck },
  low: { cls: "bg-amber-500/15 text-amber-300", icon: ShieldQuestion },
  unverified: { cls: "bg-slate-500/20 text-slate-300", icon: CircleHelp },
};

export function BandBadge({ band }: { band: Band }) {
  const { cls, icon: Icon } = BAND_STYLE[band];
  return <span className={`${pill} ${cls}`}><Icon className="h-3 w-3" />{BAND_LABELS[band]}</span>;
}

const REVIEW_STYLE: Record<ReviewStatus, { cls: string; icon: LucideIcon }> = {
  unreviewed: { cls: "bg-slate-500/20 text-slate-300", icon: CircleDashed },
  confirmed: { cls: "bg-red-500/15 text-red-300", icon: AlertTriangle },
  false_positive: { cls: "bg-slate-500/20 text-slate-300", icon: XCircle },
  needs_review: { cls: "bg-amber-500/15 text-amber-300", icon: Eye },
  resolved: { cls: "bg-emerald-500/15 text-emerald-300", icon: CheckCircle2 },
};

export function ReviewBadge({ status }: { status: ReviewStatus }) {
  const { cls, icon: Icon } = REVIEW_STYLE[status];
  return <span className={`${pill} ${cls}`}><Icon className="h-3 w-3" />{REVIEW_LABELS[status]}</span>;
}

const STATUS_STYLE: Record<ProjectStatus, string> = {
  draft: "bg-slate-500/20 text-slate-300",
  processing: "bg-sky-500/15 text-sky-300",
  completed: "bg-emerald-500/15 text-emerald-300",
  requires_review: "bg-amber-500/15 text-amber-300",
  archived: "bg-slate-600/30 text-slate-400",
};

export function StatusBadge({ status }: { status: ProjectStatus }) {
  return <span className={`${pill} ${STATUS_STYLE[status]}`}>{STATUS_LABELS[status]}</span>;
}

export function DemoBadge() {
  return <span className={`${pill} border border-amber-400/40 bg-amber-400/10 text-amber-200`}>Demo data</span>;
}

export function Modal({ title, onClose, children, wide }: { title: string; onClose: () => void; children: ReactNode; wide?: boolean }) {
  const ref = useRef<HTMLDivElement>(null);
  useEffect(() => {
    const onKey = (event: KeyboardEvent) => { if (event.key === "Escape") onClose(); };
    document.addEventListener("keydown", onKey);
    ref.current?.focus();
    return () => document.removeEventListener("keydown", onKey);
  }, [onClose]);
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-4" onMouseDown={(e) => { if (e.target === e.currentTarget) onClose(); }}>
      <div ref={ref} tabIndex={-1} role="dialog" aria-modal="true" aria-label={title}
        className={`card flex max-h-[92vh] w-full flex-col outline-none ${wide ? "max-w-5xl" : "max-w-md"}`}>
        <div className="flex items-center justify-between border-b border-ink-700 px-4 py-3">
          <h2 className="text-sm">{title}</h2>
          <button aria-label="Close" onClick={onClose} className="rounded p-1 text-text-3 hover:bg-ink-700 hover:text-text-1"><X className="h-4 w-4" /></button>
        </div>
        <div className="overflow-auto p-4">{children}</div>
      </div>
    </div>
  );
}

export function ConfirmDialog({ title, body, confirmLabel, onConfirm, onClose, busy }: { title: string; body: ReactNode; confirmLabel: string; onConfirm: () => void; onClose: () => void; busy?: boolean }) {
  return (
    <Modal title={title} onClose={onClose}>
      <div className="text-sm text-text-2">{body}</div>
      <div className="mt-4 flex justify-end gap-2">
        <Button onClick={onClose}>Cancel</Button>
        <Button variant="danger" busy={busy} onClick={onConfirm}>{confirmLabel}</Button>
      </div>
    </Modal>
  );
}

export function AuthedImage({ path, alt, className, fallback }: { path: string | null; alt: string; className?: string; fallback?: ReactNode }) {
  const { src, failed } = useAuthedImage(path);
  if (failed || !path) return <>{fallback ?? <div className={`bg-ink-800 ${className ?? ""}`} />}</>;
  if (!src) return <div className={`animate-pulse bg-ink-800 ${className ?? ""}`} />;
  return <img src={src} alt={alt} className={className} />;
}

export function Pagination({ page, pageSize, total, onChange }: { page: number; pageSize: number; total: number; onChange: (page: number) => void }) {
  const pages = Math.max(1, Math.ceil(total / pageSize));
  if (pages <= 1) return null;
  return (
    <div className="flex items-center justify-between border-t border-ink-700 px-4 py-2 text-xs text-text-3">
      <span>{total} results</span>
      <div className="flex items-center gap-2">
        <Button small disabled={page <= 1} onClick={() => onChange(page - 1)}>Previous</Button>
        <span className="data">{page} / {pages}</span>
        <Button small disabled={page >= pages} onClick={() => onChange(page + 1)}>Next</Button>
      </div>
    </div>
  );
}

interface Toast { id: number; message: string; kind: "ok" | "error" }
const ToastContext = createContext<(message: string, kind?: Toast["kind"]) => void>(() => undefined);
export const useToast = () => useContext(ToastContext);

export function ToastProvider({ children }: { children: ReactNode }) {
  const [toasts, setToasts] = useState<Toast[]>([]);
  const push = useCallback((message: string, kind: Toast["kind"] = "ok") => {
    const id = Date.now() + Math.random();
    setToasts((all) => [...all, { id, message, kind }]);
    setTimeout(() => setToasts((all) => all.filter((t) => t.id !== id)), kind === "error" ? 7000 : 3500);
  }, []);
  return (
    <ToastContext.Provider value={push}>
      {children}
      <div aria-live="polite" className="fixed bottom-4 right-4 z-[60] flex w-80 max-w-[calc(100vw-2rem)] flex-col gap-2">
        {toasts.map((t) => (
          <div key={t.id} data-toast className={`rounded-md border px-3 py-2 text-sm shadow-lg ${t.kind === "error" ? "border-red-500/50 bg-red-950 text-red-100" : "border-ink-600 bg-ink-800 text-text-1"}`}>
            {t.message}
          </div>
        ))}
      </div>
    </ToastContext.Provider>
  );
}
