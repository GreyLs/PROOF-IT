import { getLocale } from './i18n';
export type User = {
  id: string;
  email: string;
  role: "candidate" | "employer";
  subject_id: string;
  synthetic: boolean;
};
export type Spec = {
  id: string;
  label: string;
  family: string;
  skills: string[];
  allowed_grades?: string[];
  leadership_level?: string;
};
export type Meta = {
  name: string;
  demo: boolean;
  specializations: Spec[];
  grades: string[];
  upload_limit_mb: number;
  grade_change_cooldown_days: number;
};
export type Candidate = {
  id: string;
  resume_id: string;
  target_position: string;
  display_name: string;
  specialization: string;
  confirmed_grade: string | null;
  grade_evidence?: "qualification_test" | "expert_dialogue" | "synthetic_scenario" | "unconfirmed";
  category_scope?: "role-knowledge" | "role-reviewed" | "expert-dialogue" | "synthetic-scenario" | null;
  category_proof_id?: string | null;
  verified_skills?: string[];
  graph_score?: number;
  experience_years: number;
  skills: string[];
  expected_salary: number;
  work_format: string;
  test_score: number;
  fsp_status: string;
  fsp_score: number;
  achievements: Record<string, unknown>[];
  employment_confirmed?: boolean;
  qualification_passed?: boolean;
  fsp_event_verified?: boolean;
  synthetic: boolean;
  profile_updated_at: string;
  test_valid_until: string;
  relevance?: number;
  reasons?: string[];
  matched_skills?: string[];
  missing_skills?: string[];
  salary_compatible?: boolean | null;
};
export type Vacancy = {
  id: string;
  company_id: string;
  company_name: string;
  title: string;
  description: string;
  specialization: string;
  grade: string;
  skills: string[];
  salary_from: number;
  salary_to: number;
  work_format: string;
  status: string;
  origin: string;
  synthetic: boolean;
  source_ref: string;
  application_count?: number;
};
export type Invitation = {
  id: string;
  company_id: string;
  candidate_id: string;
  candidate_name?: string;
  company_name: string;
  title: string;
  description: string;
  salary_from: number;
  salary_to: number;
  status: string;
  contact: string;
  created_at: string;
};
export type DocumentRecord = {
  id: string;
  kind: string;
  filename: string;
  status: string;
  progress: number;
  error: string | null;
  created_at: string;
  result?: ExtractionResult;
};
export type ExtractionResult = {
    employment_check?: any;
    fields: Record<string, unknown>;
    reviewed_fields?: Record<string, unknown>;
    pages?: {
      page: number;
      text: string;
      method: string;
      confidence: number;
    }[];
    warnings?: string[];
    engine?: string;
    provenance?: Record<
      string,
      { page: number; quote: string; method: string }
    >;
    output_key?: string;
    profiles?: ExtractionResult[];
    page_from?: number;
    page_to?: number;
    reviewed_profile_index?: number;
};
export async function api<T = any>(
  path: string,
  init: RequestInit = {},
): Promise<T> {
  const headers = new Headers(init.headers);
  if (init.body && !(init.body instanceof FormData))
    headers.set("Content-Type", "application/json");
  const res = await fetch("/api" + path, {
    ...init,
    headers,
    credentials: "same-origin",
  });
  const text = await res.text();
  let data: any;
  try {
    data = JSON.parse(text);
  } catch {
    data = { error: { message: "Сервис вернул некорректный ответ" } };
  }
  if (!res.ok) throw new Error(data?.error?.message || `Ошибка ${res.status}`);
  return data;
}
export const send = <T = any>(
  path: string,
  data: unknown = {},
  method = "POST",
) => api<T>(path, { method, body: JSON.stringify(data) });
export const money = (v: number) =>
  new Intl.NumberFormat(getLocale()).format(v) + " ₽";
export const band = (a: number, b: number) =>
  `${new Intl.NumberFormat(getLocale()).format(a)}–${new Intl.NumberFormat(getLocale()).format(b)} ₽`;
export const date = (v: string) =>
  new Date(v).toLocaleDateString(getLocale(), {
    day: "numeric",
    month: "short",
    year: "numeric",
  });
export const grade = (g: string | null) =>
  g ? g[0].toUpperCase() + g.slice(1) : "Не подтверждён";
export const statuses: Record<string, string> = {
  sent: "Отправлено",
  viewed: "Просмотрено",
  accepted: "Принято",
  declined: "Отклонено",
  interview: "Интервью",
  rejected: "Отказ",
  withdrawn: "Отозвано",
  pending: "Ждёт решения",
  submitted: "На проверке",
  reviewed: "Проверено",
  queued: "В очереди",
  processing: "Распознавание",
  review: "Проверьте поля",
  completed: "Готово",
  failed: "Ошибка",
  passed: "Уровень подтверждён",
  expired: "Время истекло",
  completed_seed: "Демонстрационный результат",
  in_progress: "В процессе",
};
