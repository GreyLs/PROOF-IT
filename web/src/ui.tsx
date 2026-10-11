import React, {
  createContext,
  useContext,
  useEffect,
  useState,
  useRef,
} from "react";
import {
  X,
  LoaderCircle,
  CheckCircle2,
  AlertCircle,
  ArrowUpRight,
  ChevronRight,
  ShieldCheck,
  LockKeyhole,
} from "lucide-react";
import { api, Meta, User, grade, statuses } from "./api";
export type Context = {
  user: User;
  meta: Meta;
  notify: (s: string, error?: boolean) => void;
  navigate: (page: string) => void;
  demoWorkspace?: {id:string;shared:boolean;candidate_id:string;company_id:string} | null;
};
export const AppContext = createContext<Context>(null!);
export const useApp = () => useContext(AppContext);
export function useData<T = any>(path: string | null, deps: unknown[] = []) {
  const [data, setData] = useState<T | null>(null),
    [error, setError] = useState(""),
    [loading, setLoading] = useState(true),
    [revision, setRevision] = useState(0);
  useEffect(() => {
    let live = true;
    if (!path) {
      setLoading(false);
      return;
    }
    setLoading(true);
    setError("");
    api<T>(path)
      .then((v) => {
        if (live) setData(v);
      })
      .catch((e) => {
        if (live) setError(e.message);
      })
      .finally(() => {
        if (live) setLoading(false);
      });
    return () => {
      live = false;
    };
  }, [path, revision, ...deps]);
  return {
    data,
    error,
    loading,
    reload: () => setRevision((x) => x + 1),
    setData,
  };
}
export function Loading() {
  return (
    <div className="loading">
      <LoaderCircle className="spin" size={24} />
      <span>Загружаем данные…</span>
    </div>
  );
}
export function ErrorBox({
  message,
  retry,
}: {
  message: string;
  retry?: () => void;
}) {
  return (
    <div className="error-box" role="alert">
      <AlertCircle size={20} />
      <div>
        {message}
        {retry && (
          <button className="text-button" onClick={retry}>
            Повторить
          </button>
        )}
      </div>
    </div>
  );
}
export function Empty({
  title,
  text,
  action,
}: {
  title: string;
  text: string;
  action?: React.ReactNode;
}) {
  return (
    <div className="empty">
      <div className="empty-symbol">
        <ArrowUpRight size={27} />
      </div>
      <h3>{title}</h3>
      <p>{text}</p>
      {action}
    </div>
  );
}
export function Badge({
  children,
  tone = "neutral",
}: {
  children: React.ReactNode;
  tone?: string;
}) {
  return <span className={"badge " + tone}>{children}</span>;
}
export function Grade({ value }: { value: string | null }) {
  return <Badge tone={value ? "violet" : "neutral"}>{grade(value)}</Badge>;
}
export function Status({ value }: { value: string }) {
  return (
    <Badge
      tone={
        ["accepted", "passed", "completed", "reviewed"].includes(value)
          ? "green"
          : ["declined", "failed", "rejected"].includes(value)
            ? "red"
            : ["sent", "pending", "review", "submitted"].includes(value)
              ? "amber"
              : "neutral"
      }
    >
      {statuses[value] || value}
    </Badge>
  );
}
export function FspBadge({ status }: { status: string }) {
  return status === "verified" ? (
    <Badge tone="green">
      <ShieldCheck size={13} />
      ФСП подтверждено
    </Badge>
  ) : status === "mock_verified" ? (
    <Badge tone="violet">
      <ShieldCheck size={13} />
      ФСП · демо
    </Badge>
  ) : status === "pending" ? (
    <Badge tone="amber">ФСП · ждёт проверки</Badge>
  ) : (
    <Badge>Без истории ФСП</Badge>
  );
}
export function Modal({
  title,
  subtitle,
  children,
  onClose,
  wide = false,
}: {
  title: string;
  subtitle?: string;
  children: React.ReactNode;
  onClose: () => void;
  wide?: boolean;
}) {
  const ref = useRef<HTMLDivElement>(null);
  useEffect(() => {
    const old = document.activeElement as HTMLElement;
    const prev = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    ref.current?.focus();
    const key = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
      if (e.key === "Tab") {
        const focus = ref.current?.querySelectorAll<HTMLElement>(
          'button:not([disabled]),input,select,textarea,a[href],[tabindex="0"]',
        );
        if (!focus?.length) return;
        const first = focus[0],
          last = focus[focus.length - 1];
        if (e.shiftKey && document.activeElement === first) {
          e.preventDefault();
          last.focus();
        } else if (!e.shiftKey && document.activeElement === last) {
          e.preventDefault();
          first.focus();
        }
      }
    };
    document.addEventListener("keydown", key);
    return () => {
      document.body.style.overflow = prev;
      document.removeEventListener("keydown", key);
      old?.focus();
    };
  }, []);
  return (
    <div
      className="modal-backdrop"
      onMouseDown={(e) => {
        if (e.target === e.currentTarget) onClose();
      }}
    >
      <div
        className={"modal " + (wide ? "wide" : "")}
        role="dialog"
        aria-modal="true"
        aria-label={title}
        ref={ref}
        tabIndex={-1}
      >
        <div className="modal-head">
          <div>
            <h2>{title}</h2>
            {subtitle && <p>{subtitle}</p>}
          </div>
          <button
            className="icon-button"
            aria-label="Закрыть"
            onClick={onClose}
          >
            <X size={21} />
          </button>
        </div>
        {children}
      </div>
    </div>
  );
}
export function Field({
  label,
  hint,
  children,
}: {
  label: string;
  hint?: string;
  children: React.ReactNode;
}) {
  return (
    <label className="field">
      <span>{label}</span>
      {children}
      {hint && <small>{hint}</small>}
    </label>
  );
}
export function PageHead({
  eyebrow,
  title,
  description,
  actions,
}: {
  eyebrow?: string;
  title: string;
  description?: string;
  actions?: React.ReactNode;
}) {
  return (
    <div className="page-heading">
      <div>
        {eyebrow && <div className="eyebrow">{eyebrow}</div>}
        <h1>{title}</h1>
        {description && <p>{description}</p>}
      </div>
      {actions && <div className="heading-actions">{actions}</div>}
    </div>
  );
}
export function Skills({
  items,
  matched,
  limit = 7,
}: {
  items: string[];
  matched?: string[];
  limit?: number;
}) {
  return (
    <div className="skills">
      {items.slice(0, limit).map((x, i) => (
        <span className={matched?.includes(x) ? "matched" : ""} key={x + i}>
          {x}
        </span>
      ))}
      {items.length > limit && <span>+{items.length - limit}</span>}
    </div>
  );
}
export function Score({ score }: { score: number }) {
  return (
    <div className="score">
      <svg viewBox="0 0 46 46">
        <circle cx="23" cy="23" r="19" className="score-track" />
        <circle
          cx="23"
          cy="23"
          r="19"
          className="score-value"
          style={{ strokeDasharray: `${score * 1.194} 119.4` }}
        />
      </svg>
      <strong>{score}</strong>
    </div>
  );
}
export function Stat({
  label,
  value,
  caption,
  icon,
}: {
  label: string;
  value: string | number;
  caption: string;
  icon?: React.ReactNode;
}) {
  return (
    <div className="stat-card">
      <div className="stat-top">
        <span>{label}</span>
        {icon}
      </div>
      <strong>
        {typeof value === "number" ? value.toLocaleString("ru-RU") : value}
      </strong>
      <small>{caption}</small>
    </div>
  );
}
export function PrivacyNote() {
  return (
    <div className="privacy-note">
      <LockKeyhole size={17} />
      <span>
        Контакты откроются только после согласия кандидата на ваше предложение.
      </span>
    </div>
  );
}
