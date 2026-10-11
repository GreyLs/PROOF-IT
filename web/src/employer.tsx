import React, { useState, useEffect } from "react";
import { CompanyReviews } from './evidence';
import { ExpertChat } from "./expert-chat";
import { CandidateProof, MatchExplanation } from "./intelligence";
import { VacancyTools, VacancyIntelligence, MarketBadge, TaskGenerator } from "./workbench";
import {
  Search,
  SlidersHorizontal,
  ArrowUpRight,
  ArrowRight,
  Plus,
  Mail,
  LockKeyhole,
  Check,
  Code2,
  Bookmark,
  GitCompareArrows,
  X,
  FileScan,
  ShieldCheck,
  MapPin,
  BriefcaseBusiness,
  Clock3,
  TrendingDown,
  CheckCircle2,
  ChevronLeft,
  ChevronRight,
  Send,
  Building2,
  ExternalLink,
  PlugZap,
  RefreshCw,
  Unplug,
  Link2,
} from "lucide-react";
import {
  api,
  send,
  Candidate,
  Vacancy,
  Invitation,
  money,
  band,
  grade,
  date,
} from "./api";
import {
  useApp,
  useData,
  PageHead,
  Loading,
  ErrorBox,
  Empty,
  Badge,
  Grade,
  Status,
  FspBadge,
  Modal,
  Field,
  Skills,
  Score,
  PrivacyNote,
} from "./ui";

export function SearchPage() {
  const { meta, notify, navigate } = useApp();
  const [spec, setSpec] = useState(
      () => sessionStorage.getItem("fsp_search_spec") || "",
    ),
    [g, setGrade] = useState(""),
    [q, setQ] = useState(""),
    [debounced, setDebounced] = useState(""),
    [fsp, setFsp] = useState(""),
    [skill, setSkill] = useState(""),
    [budget, setBudget] = useState(""),
    [vacancy, setVacancy] = useState(""),
    [offset, setOffset] = useState(0),
    [selected, setSelected] = useState<Candidate[]>([]),
    [detail, setDetail] = useState<Candidate | null>(null),
    [offer, setOffer] = useState<Candidate | null>(null),
    [compare, setCompare] = useState(false),
    [need, setNeed] = useState(false),
    [savedOpen, setSavedOpen] = useState(false);
  const vacancies = useData<{ items: Vacancy[] }>("/vacancies?limit=500");
  const saved = useData("/saved-searches");
  useEffect(() => {
    sessionStorage.removeItem("fsp_search_spec");
  }, []);
  useEffect(() => {
    const timer = setTimeout(() => setDebounced(q), 300);
    return () => clearTimeout(timer);
  }, [q]);
  const params = new URLSearchParams({ limit: "12", offset: String(offset) });
  if (spec) params.set("specialization", spec);
  if (g) params.set("grade", g);
  if (fsp) params.set("fsp", fsp);
  if (debounced) params.set("q", debounced);
  if (skill.trim()) params.set("skills", skill);
  if (budget) params.set("salary_to", budget);
  if (vacancy) params.set("vacancy_id", vacancy);
  const result = useData<{ items: Candidate[]; total: number; need: any }>(
    "/candidates?" + params.toString(),
  );
  const reset = () => {
    setSpec("");
    setGrade("");
    setFsp("");
    setQ("");
    setSkill("");
    setBudget("");
    setVacancy("");
    setOffset(0);
  };
  const toggle = (c: Candidate) =>
    setSelected((prev) =>
      prev.find((x) => x.resume_id === c.resume_id)
        ? prev.filter((x) => x.resume_id !== c.resume_id)
        : prev.length < 3
          ? [...prev, c]
          : prev,
    );
  const save = async () => {
    try {
      const label =
        meta.specializations.find(
          (x) => x.id === (result.data?.need.specialization || spec),
        )?.label || "Все направления";
      await send("/saved-searches", {
        name: `${label} · ${new Date().toLocaleDateString("ru-RU")}`,
        query: Object.fromEntries(params),
        candidate_ids: (result.data?.items || []).map((c) => c.id),
      });
      notify(
        "Подборка сохранена. Фильтры и состав первой страницы доступны в сохранённых.",
      );
      saved.reload();
    } catch (e) {
      notify((e as Error).message, true);
    }
  };
  return (
    <>
      <PageHead
        eyebrow="ПОДТВЕРЖДЁННЫЕ НАВЫКИ · ПОНЯТНЫЙ ВЫБОР"
        title="Банк талантов"
        description="Найдите специалиста под задачу. Начните диалог с предложения."
        actions={
          <>
            <button
              className="button secondary"
              onClick={() => setSavedOpen(true)}
            >
              <Bookmark size={17} />
              Сохранённые
            </button>
            <button className="button primary" onClick={() => setNeed(true)}>
              <Plus size={18} />
              Описать потребность
            </button>
          </>
        }
      />
      <div className="search-workspace">
        <aside className="filter-panel">
          <div className="filter-title">
            <SlidersHorizontal size={18} />
            <strong>Параметры подбора</strong>
            <button onClick={reset}>Сбросить</button>
          </div>
          <Field label="Вакансия или потребность">
            <select
              value={vacancy}
              onChange={(e) => {
                setVacancy(e.target.value);
                setSpec("");
                setGrade("");
                setOffset(0);
              }}
            >
              <option value="">Весь банк талантов</option>
              {vacancies.data?.items.map((v) => (
                <option key={v.id} value={v.id}>
                  {v.title}{v.grade ? ` · ${grade(v.grade)}` : " · руководящая роль"}
                  {v.origin !== "employer" ? " · демо" : ""}
                </option>
              ))}
            </select>
          </Field>
          <Field label="Специализация">
            <select
              value={spec}
              onChange={(e) => {
                setSpec(e.target.value);
                setOffset(0);
              }}
            >
              <option value="">Все направления</option>
              {meta.specializations.map((s) => (
                <option value={s.id} key={s.id}>
                  {s.label}
                </option>
              ))}
            </select>
          </Field>
          <Field label="Подтверждённый грейд">
            <div className="grade-options">
              {["junior", "middle", "senior"].map((v) => (
                <button
                  className={g === v ? "selected" : ""}
                  key={v}
                  onClick={() => {
                    setGrade(g === v ? "" : v);
                    setOffset(0);
                  }}
                >
                  {grade(v)}
                </button>
              ))}
            </div>
          </Field>
          <Field label="Стек" hint="Навыки через запятую">
            <input
              placeholder="Python, PostgreSQL"
              value={skill}
              onChange={(e) => {
                setSkill(e.target.value);
                setOffset(0);
              }}
            />
          </Field>
          <Field label="Бюджет до, ₽ / месяц">
            <input
              type="number"
              min="1"
              placeholder="Например, 250000"
              value={budget}
              onChange={(e) => {
                setBudget(e.target.value);
                setOffset(0);
              }}
            />
          </Field>
          <Field label="История ФСП">
            <select
              value={fsp}
              onChange={(e) => {
                setFsp(e.target.value);
                setOffset(0);
              }}
            >
              <option value="">Все кандидаты</option>
              <option value="with_history">С историей, включая демо</option>
              <option value="verified">Только подтверждённая</option>
              <option value="without_history">Без истории</option>
            </select>
          </Field>
          <div className="filter-note">
            <ShieldCheck size={19} />
            <p>
              Категория определяется тестом.
              <br />
              Резюме дополняет профиль.
            </p>
          </div>
          <button className="upload-mini" onClick={() => navigate("documents")}>
            <FileScan size={20} />
            <span>
              Есть PDF вакансии?<small>Распознаем и поможем заполнить</small>
            </span>
            <ArrowUpRight size={16} />
          </button>
        </aside>
        <section className="results">
          <div className="results-toolbar">
            <div className="search-input">
              <Search size={19} />
              <input
                aria-label="Поиск по навыку или ID"
                value={q}
                onChange={(e) => {
                  setQ(e.target.value);
                  setOffset(0);
                }}
                placeholder="Поиск по навыку или ID кандидата"
              />
            </div>
            <button
              className="button secondary"
              onClick={save}
              disabled={!result.data?.items.length}
            >
              <Bookmark size={17} />
              Сохранить
            </button>
          </div>
          <div className="results-summary">
            <strong>
              {result.data?.total.toLocaleString("ru-RU") || "—"}{" "}
              <span>специалистов</span>
            </strong>
            <span>Соответствие → тест → ФСП</span>
          </div>
          {result.loading ? (
            <Loading />
          ) : result.error ? (
            <ErrorBox message={result.error} retry={result.reload} />
          ) : !result.data?.items.length ? (
            <Empty
              title="Пока нет точного совпадения"
              text="Попробуйте расширить специализацию или снять часть фильтров. Сохранённая подборка останется доступна."
              action={
                <button className="button secondary" onClick={reset}>
                  Сбросить фильтры
                </button>
              }
            />
          ) : (
            <div className="candidate-list">
              {result.data.items.map((c, i) => (
                <article className="candidate-card" key={c.resume_id || c.id}>
                  <div className="candidate-head">
                    <span className="candidate-rank">
                      {String(offset + i + 1).padStart(2, "0")}
                    </span>
                    <div className="candidate-avatar">
                      <Code2 size={23} />
                    </div>
                    <div className="candidate-title">
                      <button onClick={() => setDetail(c)}>
                        {c.target_position || meta.specializations.find(
                          (s) => s.id === c.specialization,
                        )?.label || c.specialization}
                        <ArrowUpRight size={15} />
                      </button>
                      <div>
                        <span>{c.id}</span>
                        <span>·</span>
                        <span>{c.experience_years} лет опыта</span>
                        <span>·</span>
                        <span>{c.work_format}</span>
                      </div>
                    </div>
                    <Score score={c.test_score} />
                    <label
                      className="compare-check"
                      title="Добавить в сравнение"
                    >
                      <input
                        aria-label={`Сравнить ${c.id}`}
                        type="checkbox"
                        checked={selected.some((x) => x.resume_id === c.resume_id)}
                        disabled={
                          selected.length >= 3 &&
                          !selected.some((x) => x.resume_id === c.resume_id)
                        }
                        onChange={() => toggle(c)}
                      />
                    </label>
                  </div>
                  <div className="candidate-badges">
                    <Grade value={c.confirmed_grade} />
                    <FspBadge status={c.fsp_status} />
                    {c.employment_confirmed&&<Badge tone="green">Трудовая сверена</Badge>}
                    {c.qualification_passed&&<Badge tone="green">Тест по роли пройден</Badge>}
                    {c.synthetic && <Badge>Демонстрационный профиль</Badge>}
                  </div>
                  <Skills items={c.skills} matched={c.matched_skills} />
                  {!!c.verified_skills?.length && <p className="muted">Проверено доказательствами: {c.verified_skills.join(', ')}</p>}
                  {(vacancy || spec || skill || budget) && (
                    <div className="match-explanation">
                      <CheckCircle2 size={15} />
                      <span>
                        {c.relevance === 3
                          ? "Сильное соответствие"
                          : c.relevance === 2
                            ? "Подходит с уточнениями"
                            : "Есть различия с потребностью"}
                        {c.salary_compatible === false
                          ? " · ожидание выше бюджета"
                          : ""}
                      </span>
                      <button onClick={() => setDetail(c)}>Почему?</button>
                    </div>
                  )}
                  <div className="candidate-bottom">
                    <div>
                      <strong>от {money(c.expected_salary)}</strong>
                      <span>ожидание в месяц</span>
                    </div>
                    <div>
                      <button
                        className="button text"
                        onClick={() => setDetail(c)}
                      >
                        Профиль
                      </button>
                      <button
                        className="button invite"
                        onClick={() => setOffer(c)}
                      >
                        Пригласить
                        <ArrowUpRight size={16} />
                      </button>
                    </div>
                  </div>
                </article>
              ))}
            </div>
          )}
          <div className="pagination">
            <span>
              {result.data?.total
                ? `${offset + 1}–${Math.min(offset + 12, result.data.total)} из ${result.data.total}`
                : ""}
            </span>
            <button
              className="icon-button"
              disabled={offset === 0}
              onClick={() => setOffset(Math.max(0, offset - 12))}
              aria-label="Предыдущая страница"
            >
              <ChevronLeft size={19} />
            </button>
            <button
              className="icon-button"
              disabled={!result.data || offset + 12 >= result.data.total}
              onClick={() => setOffset(offset + 12)}
              aria-label="Следующая страница"
            >
              <ChevronRight size={19} />
            </button>
          </div>
        </section>
      </div>
      {selected.length > 0 && (
        <div className="comparison-bar">
          <div>
            <GitCompareArrows size={20} />
            <strong>{selected.length} из 3</strong>
            <span>кандидатов для сравнения</span>
          </div>
          <button className="button primary" onClick={() => setCompare(true)}>
            Сравнить
          </button>
          <button
            className="icon-button"
            aria-label="Очистить сравнение"
            onClick={() => setSelected([])}
          >
            <X size={18} />
          </button>
        </div>
      )}
      {detail && (
        <CandidateModal
          candidate={detail}
          vacancyId={vacancy}
          onClose={() => setDetail(null)}
          onInvite={() => {
            setOffer(detail);
            setDetail(null);
          }}
        />
      )}
      {offer && <OfferModal candidate={offer} onClose={() => setOffer(null)} />}{" "}
      {need && (
        <VacancyEditor
          title="Опишите потребность команды"
          draft
          onClose={() => setNeed(false)}
          onSaved={(v) => {
            setVacancy(v.id);
            setSpec("");
            setGrade("");
            setOffset(0);
            setNeed(false);
            vacancies.reload();
          }}
        />
      )}
      {compare && (
        <Modal
          title="Сравнение кандидатов"
          subtitle="Одинаковые критерии. Факты и условия рядом."
          wide
          onClose={() => setCompare(false)}
        >
          <div className="comparison-table">
            <table>
              <thead>
                <tr>
                  <th>Критерий</th>
                  {selected.map((c) => (
                    <th key={c.id}>{c.id}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {[
                  [
                    "Направление",
                    (c: Candidate) =>
                      meta.specializations.find(
                        (s) => s.id === c.specialization,
                      )?.label,
                  ],
                  ["Грейд", (c: Candidate) => grade(c.confirmed_grade)],
                  ["Тест", (c: Candidate) => `${c.test_score} / 100`],
                  ["Ожидание", (c: Candidate) => money(c.expected_salary)],
                  ["Стаж", (c: Candidate) => `${c.experience_years} лет`],
                  [
                    "ФСП",
                    (c: Candidate) =>
                      c.fsp_status === "mock_verified"
                        ? "Демо-история"
                        : c.fsp_status === "verified"
                          ? "Подтверждено"
                          : "Нет истории",
                  ],
                  [
                    "Совпавший стек",
                    (c: Candidate) =>
                      c.matched_skills?.join(", ") || "Потребность не задана",
                  ],
                ].map(([label, fn]) => (
                  <tr key={String(label)}>
                    <th>{String(label)}</th>
                    {selected.map((c) => (
                      <td key={c.id}>
                        {(fn as (c: Candidate) => React.ReactNode)(c)}
                      </td>
                    ))}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <PrivacyNote />
        </Modal>
      )}
      {savedOpen && (
        <Modal
          title="Сохранённые подборки"
          subtitle="Фильтры сохраняются вместе с составом первой страницы."
          onClose={() => setSavedOpen(false)}
        >
          {saved.data?.items?.length ? (
            saved.data.items.map((x: any) => (
              <div key={x.id}>
              <button
                className="saved-item"
                onClick={() => {
                  setSpec(x.query.specialization || "");
                  setGrade(x.query.grade || "");
                  setFsp(x.query.fsp || "");
                  setSkill(x.query.skills || "");
                  setBudget(x.query.salary_to || "");
                  setVacancy(x.query.vacancy_id || "");
                  setQ(x.query.q || "");
                  setOffset(0);
                  setSavedOpen(false);
                }}
              >
                <Bookmark size={19} />
                <div>
                  <strong>{x.name}</strong>
                  <small>
                    {x.candidate_ids.length} кандидатов в снимке ·{" "}
                    {date(x.created_at)}
                  </small>
                </div>
                <ArrowUpRight size={17} />
              </button>
              <details className="saved-snapshot">
                <summary>Состав сохранённой подборки</summary>
                <p>Снимок сохраняется при изменении фильтров. Нажмите ID, чтобы найти профиль; его текущая видимость может измениться.</p>
                <div className="skills">{x.candidate_ids.map((id:string)=><button className="button secondary" key={id} onClick={()=>{reset();setQ(id);setSavedOpen(false)}}>{id}</button>)}</div>
              </details>
              </div>
            ))
          ) : (
            <Empty
              title="Здесь будут ваши подборки"
              text="Настройте поиск и нажмите «Сохранить»."
            />
          )}
        </Modal>
      )}
    </>
  );
}
export function CandidateModal({
  candidate: c,
  onClose,
  onInvite,
  vacancyId,
}: {
  candidate: Candidate;
  onClose: () => void;
  onInvite: () => void;
  vacancyId?: string;
}) {
  const { meta } = useApp();
  const details = useData("/candidates/" + c.id);
  return (
    <Modal
      title={
        meta.specializations.find((s) => s.id === c.specialization)?.label ||
        c.id
      }
      subtitle={`${c.id} · ${c.experience_years} лет опыта · ${c.work_format}`}
      wide
      onClose={onClose}
    >
      <div className="profile-proof">
        <div>
          <Grade value={c.confirmed_grade} />
          <FspBadge status={c.fsp_status} />
        </div>
        <div className="proof-score">
          <Score score={c.test_score} />
          <span>
            Результат
            <br />
            экспертного диалога
          </span>
        </div>
      </div>
      <CandidateProof candidateId={c.id} />
      {vacancyId && c.resume_id && <MatchExplanation resumeId={c.resume_id} vacancyId={vacancyId} />}
      <div className="detail-grid">
        <section>
          <h3>Почему в подборке</h3>
          <ul className="reasons">
            {(
              c.reasons || ["Подтверждённый профиль доступен в банке талантов"]
            ).map((x, i) => (
              <li key={i}>
                <CheckCircle2 size={17} />
                {x.replace("Синтетический профиль и сценарная оценка", "Демонстрационный профиль").replace("синтетические записи", "демонстрационные записи")}
              </li>
            ))}
          </ul>
          <h3>Заявленный стек</h3>
          <Skills items={c.skills} matched={c.matched_skills} limit={30} />
          <p className="muted">Подтверждено: {c.verified_skills?.join(', ') || 'пока нет актуальных доказательств отдельных навыков'}. Указание в резюме не является подтверждением.</p>
          {!!c.missing_skills?.length && (
            <>
              <h3>Что стоит уточнить</h3>
              <Skills items={c.missing_skills} limit={30} />
            </>
          )}
          <h3>Достижения ФСП</h3>
          {c.achievements.length ? (
            c.achievements.map((a: any, i) => (
              <div className="achievement" key={i}>
                <ShieldCheck size={22} />
                <div>
                  <strong>{a.discipline}</strong>
                  <p>
                    {a.result} · {a.year}
                  </p>
                  <small>
                    {a.synthetic
                      ? "Демонстрационный пример интеграции"
                      : a.event}
                  </small>
                </div>
              </div>
            ))
          ) : (
            <p className="muted">
              История не связана. Это не мешает кандидату участвовать в подборе.
            </p>
          )}
        </section>
        <aside className="detail-conditions">
          <span className="eyebrow">ОЖИДАНИЯ КАНДИДАТА</span>
          <h2>от {money(c.expected_salary)}</h2>
          <p>в месяц · {c.work_format}</p>
          <hr />
          {details.loading ? (
            <Loading />
          ) : details.error ? (
            <ErrorBox message={details.error} />
          ) : details.data?.contacts_released ? (
            <>
              <Badge tone="green">
                <Check size={14} />
                Контакты открыты вам
              </Badge>
              <p>{details.data.contacts.full_name || "Имя не заполнено"}</p>
              <p>{details.data.contacts.email || "Email не заполнен"}</p>
              <p>{details.data.contacts.phone || "Телефон не заполнен"}</p>
            </>
          ) : (
            <PrivacyNote />
          )}
          <button className="button primary full" onClick={onInvite}>
            Предложить работу
            <ArrowUpRight size={17} />
          </button>
          <small>Действие доступно и без опубликованной вакансии.</small>
        </aside>
      </div>
    </Modal>
  );
}
export function OfferModal({
  candidate: c,
  onClose,
}: {
  candidate: Candidate;
  onClose: () => void;
}) {
  const { notify, meta } = useApp();
  const [title, setTitle] = useState(
      `Предложение · ${meta.specializations.find((s) => s.id === c.specialization)?.label || c.specialization}`,
    ),
    [description, setDescription] = useState(""),
    [from, setFrom] = useState(c.expected_salary),
    [to, setTo] = useState(Math.round(c.expected_salary * 1.2)),
    [busy, setBusy] = useState(false),
    [error, setError] = useState("");
  const [key] = useState(() => crypto.randomUUID());
  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    setBusy(true);
    try {
      await send("/invitations", {
        candidate_id: c.id,
        resume_id: c.resume_id,
        vacancy_id: null,
        title,
        description,
        salary_from: Number(from),
        salary_to: Number(to),
        idempotency_key: key,
      });
      notify(
        "Приглашение отправлено. Кандидат увидит условия до начала диалога.",
      );
      onClose();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  };
  return (
    <Modal
      title="Начните диалог с предложения"
      subtitle={`${c.id} · ${grade(c.confirmed_grade)} · ожидание от ${money(c.expected_salary)}`}
      onClose={onClose}
    >
      <form onSubmit={submit}>
        <Field label="Название предложения">
          <input
            required
            minLength={3}
            value={title}
            onChange={(e) => setTitle(e.target.value)}
          />
        </Field>
        <Field label="Команда, задачи и условия">
          <textarea
            required
            minLength={10}
            rows={5}
            placeholder="Расскажите, что предстоит делать, с кем работать и почему выбрали этого специалиста."
            value={description}
            onChange={(e) => setDescription(e.target.value)}
          />
        </Field>
        <div className="form-grid">
          <Field label="Зарплата от, ₽ / месяц">
            <input
              required
              type="number"
              min={1}
              value={from}
              onChange={(e) => setFrom(Number(e.target.value))}
            />
          </Field>
          <Field label="Зарплата до, ₽ / месяц">
            <input
              required
              type="number"
              min={from}
              value={to}
              onChange={(e) => setTo(Number(e.target.value))}
            />
          </Field>
        </div>
        <PrivacyNote />
        {error && <ErrorBox message={error} />}
        <div className="modal-actions">
          <button type="button" className="button secondary" onClick={onClose}>
            Отмена
          </button>
          <button className="button primary" disabled={busy}>
            {busy ? "Отправляем…" : "Отправить приглашение"}
            <Send size={17} />
          </button>
        </div>
      </form>
    </Modal>
  );
}
export function InvitationsPage() {
  const { user, notify } = useApp();
  const employer = user.role === "employer";
  const result = useData<{ items: Invitation[] }>("/invitations");
  const [filter, setFilter] = useState("all"),
    [contact, setContact] = useState<any>(null),
    [shareWithAts, setShareWithAts] = useState(false),
    [busy, setBusy] = useState("");
  const respond = async (id: string, status: string) => {
    setBusy(id);
    try {
      await send("/invitations/" + id, { status, share_with_ats: status === "accepted" && shareWithAts }, "PUT");
      notify(
        status === "accepted"
          ? "Приглашение принято. Контакты открыты этой компании."
          : status === "declined"
            ? "Приглашение отклонено."
            : "Приглашение отмечено как просмотренное.",
      );
      result.reload();
    } catch (e) {
      notify((e as Error).message, true);
    } finally {
      setBusy("");
    }
  };
  const items =
    result.data?.items.filter((x) => filter === "all" || x.status === filter) ||
    [];
  return (
    <>
      <PageHead
        eyebrow="ДИАЛОГ НАЧИНАЕТСЯ С ПРОЗРАЧНОСТИ"
        title={employer ? "Приглашения" : "Вам предлагают работу"}
        description={
          employer
            ? "Отслеживайте предложения и открывайте контакты после согласия."
            : "Задачи и зарплата известны заранее. Вы решаете, с кем продолжить общение."
        }
      />
      <div className="tabs">
        {[
          ["all", "Все"],
          ["sent", "Новые"],
          ["viewed", "Просмотрены"],
          ["accepted", "Приняты"],
          ["declined", "Отклонены"],
        ].map(([k, l]) => (
          <button
            className={filter === k ? "active" : ""}
            onClick={() => setFilter(k)}
            key={k}
          >
            {l}
            <span>
              {k === "all"
                ? result.data?.items.length || 0
                : result.data?.items.filter((x) => x.status === k).length || 0}
            </span>
          </button>
        ))}
      </div>
      {result.loading ? (
        <Loading />
      ) : result.error ? (
        <ErrorBox message={result.error} />
      ) : !items.length ? (
        <Empty
          title={
            employer
              ? "Первое приглашение — начало диалога"
              : "Хорошие предложения начинаются с профиля"
          }
          text={
            employer
              ? "Найдите специалиста в банке талантов и предложите работу с открытой зарплатой."
              : "Заполните профиль, подтвердите уровень и включите видимость для работодателей."
          }
        />
      ) : (
        <div className="offers-grid">
          {items.map((x) => (
            <article className="offer-card" key={x.id}>
              <div className="offer-top">
                <div className="company-avatar">
                  <Building2 size={23} />
                </div>
                <div>
                  <strong>{x.company_name}</strong>
                  <small>{date(x.created_at)}</small>
                </div>
                <Status value={x.status} />
              </div>
              <h2>{x.title}</h2>
              <div className="offer-salary">
                {band(x.salary_from, x.salary_to)}
                <span>в месяц</span>
              </div>
              <p className="offer-description">{x.description}</p>
              {!employer && <CompanyReviews companyId={x.company_id}/>}
              <div className="offer-meta">
                {employer
                  ? `Кандидат ${x.candidate_id}`
                  : `Связь с компанией: ${x.contact}`}
              </div>
              <div className="offer-actions">
                {employer ? (
                  x.status === "accepted" ? (
                    <button
                      className="button primary"
                      onClick={async () => {
                        try {
                          setContact(
                            await api("/candidates/" + x.candidate_id),
                          );
                        } catch (e) {
                          notify((e as Error).message, true);
                        }
                      }}
                    >
                      Открыть контакты
                      <ArrowUpRight size={17} />
                    </button>
                  ) : (
                    <div className="muted inline">
                      <LockKeyhole size={15} />
                      Контакты ждут согласия
                    </div>
                  )
                ) : ["sent", "viewed"].includes(x.status) ? (
                  <>
                    <label className="ats-consent">
                      <input
                        type="checkbox"
                        checked={shareWithAts}
                        onChange={(e) => setShareWithAts(e.target.checked)}
                      />
                      Если у компании подключён Talantix, разрешаю передать туда мой отклик и контакты для этой вакансии.
                    </label>
                    <button
                      disabled={busy === x.id}
                      className="button primary"
                      onClick={() => respond(x.id, "accepted")}
                    >
                      Принять и открыть контакты
                      <Check size={17} />
                    </button>
                    <button
                      disabled={busy === x.id}
                      className="button secondary"
                      onClick={() => respond(x.id, "declined")}
                    >
                      Отклонить
                    </button>
                    {x.status === "sent" && (
                      <button
                        className="text-button"
                        onClick={() => respond(x.id, "viewed")}
                      >
                        Отметить просмотренным
                      </button>
                    )}
                  </>
                ) : (
                  <span className="muted">
                    {x.status === "accepted"
                      ? "Вы открыли контакты этой компании. Можно продолжить общение."
                      : "Ваши контакты не раскрыты."}
                  </span>
                )}
              </div>
            </article>
          ))}
        </div>
      )}
      {contact && (
        <Modal
          title="Контакты кандидата"
          subtitle="Кандидат разрешил вашей компании связаться с ним."
          onClose={() => setContact(null)}
        >
          {contact.contacts_released ? (
            <div className="contact-block">
              <h3>{contact.contacts.full_name || contact.candidate.id}</h3>
              <p>{contact.contacts.email || "Email не заполнен"}</p>
              <p>{contact.contacts.phone || "Телефон не заполнен"}</p>
              {contact.candidate.synthetic && (
                <Badge>Контакты демонстрационные</Badge>
              )}
            </div>
          ) : (
            <PrivacyNote />
          )}
        </Modal>
      )}
    </>
  );
}
export function VacancyEditor({
  onClose,
  onSaved,
  initial,
  title = "Новая вакансия",
  draft = false,
}: {
  onClose: () => void;
  onSaved: (v: Vacancy) => void;
  initial?: Partial<Vacancy>;
  title?: string;
  draft?: boolean;
}) {
  const { meta } = useApp();
  const [p, setP] = useState({
    title: "",
    description: "",
    specialization: meta.specializations[0].id,
    grade: "middle",
    skills: [] as string[],
    salary_from: 0,
    salary_to: 0,
    work_format: "удалённо",
    status: draft ? "draft" : "published",
    ...initial,
  });
  const [busy, setBusy] = useState(false),
    [error, setError] = useState("");
  const leadership = Boolean(meta.specializations.find((s) => s.id === p.specialization)?.leadership_level);
  const change = (k: string, v: unknown) =>
    setP((prev) => ({ ...prev, [k]: v }));
  return (
    <Modal
      title={title}
      subtitle={
        draft
          ? "Создайте подборку под задачу. Публиковать вакансию необязательно."
          : "Укажите задачи, требования и обе границы зарплаты."
      }
      wide
      onClose={onClose}
    >
      <form
        onSubmit={async (e) => {
          e.preventDefault();
          setBusy(true);
          try {
            const r = await send(
              initial?.id ? "/vacancies/" + initial.id : "/vacancies",
              p,
              initial?.id ? "PUT" : "POST",
            );
            onSaved(r.vacancy);
          } catch (e) {
            setError((e as Error).message);
          } finally {
            setBusy(false);
          }
        }}
      >
        <Field label="Название роли или потребности">
          <input
            required
            minLength={3}
            value={p.title}
            onChange={(e) => change("title", e.target.value)}
            placeholder="Backend-разработчик в продуктовую команду"
          />
        </Field>
        <Field label="Чем занимается команда и какие задачи предстоят">
          <textarea
            required
            minLength={10}
            rows={5}
            value={p.description}
            onChange={(e) => change("description", e.target.value)}
          />
        </Field>
        <div className="form-grid">
          <Field label="Специализация">
            <select
              value={p.specialization}
              onChange={(e) => {
                change("specialization", e.target.value);
                const selected=meta.specializations.find(s=>s.id===e.target.value);
                const allowed=selected?.allowed_grades;
                if(selected?.leadership_level) change("grade","");
                else if((allowed?.length && !allowed.includes(p.grade)) || (e.target.value==="software_architecture" && p.grade==="junior") || !p.grade) change("grade",allowed?.[0]||"middle");
                change(
                  "skills",
                  meta.specializations
                    .find((s) => s.id === e.target.value)
                    ?.skills.slice(0, 6) || [],
                );
              }}
            >
              {meta.specializations.map((s) => (
                <option key={s.id} value={s.id}>
                  {s.label}
                </option>
              ))}
            </select>
          </Field>
          {!leadership&&<Field label="Целевой грейд">
            <select
              value={p.grade}
              onChange={(e) => change("grade", e.target.value)}
            >
              {meta.grades.filter(g=>{const allowed=meta.specializations.find(s=>s.id===p.specialization)?.allowed_grades;return (!allowed?.length||allowed.includes(g)) && !(p.specialization==="software_architecture" && g==="junior");}).map((g) => (
                <option key={g} value={g}>
                  {grade(g)}
                </option>
              ))}
            </select>
          </Field>}
          {leadership&&<Field label="Уровень роли"><p className="muted">Руководящая позиция: уровень задаётся масштабом ответственности, грейд не применяется.</p></Field>}
        </div>
        <Field label="Требуемый стек, через запятую">
          <input
            value={p.skills.join(", ")}
            onChange={(e) =>
              change(
                "skills",
                e.target.value.split(",").map((x) => x.trim()),
              )
            }
          />
        </Field>
        <div className="form-grid">
          <Field label="Зарплата от, ₽ / месяц">
            <input
              type="number"
              required
              min={1}
              value={p.salary_from || ""}
              onChange={(e) => change("salary_from", Number(e.target.value))}
            />
          </Field>
          <Field label="Зарплата до, ₽ / месяц">
            <input
              type="number"
              required
              min={p.salary_from || 1}
              value={p.salary_to || ""}
              onChange={(e) => change("salary_to", Number(e.target.value))}
            />
          </Field>
          <Field label="Формат работы">
            <select
              value={p.work_format}
              onChange={(e) => change("work_format", e.target.value)}
            >
              <option>удалённо</option>
              <option>гибрид</option>
              <option>офис</option>
            </select>
          </Field>
          <Field label="Видимость">
            <select
              value={p.status}
              onChange={(e) => change("status", e.target.value)}
            >
              <option value="draft">Только для подбора</option>
              <option value="published">Опубликовать вакансию</option>
              <option value="closed">Закрыта</option>
            </select>
          </Field>
        </div>
        {error && <ErrorBox message={error} />}
        <div className="modal-actions">
          <button type="button" className="button secondary" onClick={onClose}>
            Отмена
          </button>
          <button disabled={busy} className="button primary">
            {busy
              ? "Сохраняем…"
              : draft
                ? "Сформировать подборку"
                : "Сохранить вакансию"}
            <ArrowRight size={17} />
          </button>
        </div>
      </form>
    </Modal>
  );
}
type TimeForecast={forecast_days:number;forecast_weeks:number;target_reduction_percent:number;target_days:number;recommended_days:number;estimated_reduction_percent:number;target_achievable:boolean;recommendation:string;drivers:Record<string,number>};
function VacancyTimeForecast({vacancy}:{vacancy:Vacancy}){
  const result=useData<{forecast:TimeForecast}>(`/forecasts/vacancy/${encodeURIComponent(vacancy.id)}`);
  if(result.loading)return <section className="forecast-card forecast-loading"><Clock3 size={20}/><span>Рассчитываем прогноз закрытия вакансии…</span></section>;
  if(result.error||!result.data?.forecast)return null;
  const f=result.data.forecast;
  return <section className="forecast-card"><div className="forecast-heading"><div><span className="eyebrow">ПЛАН ЗАКРЫТИЯ ВАКАНСИИ</span><h3>Ориентир по сроку закрытия</h3></div><Clock3 size={23}/></div><div className="forecast-metrics"><div><strong>{f.forecast_days}</strong><span>дней</span></div><p>≈ {f.forecast_weeks.toLocaleString("ru-RU")} недели</p></div><div className="forecast-target"><TrendingDown size={17}/><span>Цель −{f.target_reduction_percent}%: <strong>{f.target_days} дней</strong></span></div><p className="forecast-recommendation">{f.recommendation}</p><p>Ожидаемый срок после изменений: <strong>{f.recommended_days} дней</strong> · сокращение {f.estimated_reduction_percent}%</p>{!f.target_achievable&&<small>Цель −10% пока не достигается доступными изменениями.</small>}<small>Релевантных кандидатов: {f.drivers.relevant_candidates} · оценка компании: {f.drivers.company_rating.toLocaleString("ru-RU")}/5</small></section>;
}

export function VacanciesPage() {
  const { user, meta, notify, demoWorkspace } = useApp();
  const employer = user.role === "employer";
  const [demoOnly,setDemoOnly]=useState(!!demoWorkspace&&!employer);
  const [mine, setMine] = useState(employer),
    [spec, setSpec] = useState(""),
    [edit, setEdit] = useState<Partial<Vacancy> | null>(null),
    [view, setView] = useState<Vacancy | null>(null),
    [message, setMessage] = useState(""),
    [resumeId, setResumeId] = useState(""),
    [shareWithAts, setShareWithAts] = useState(false),
    [busy, setBusy] = useState(false);
  const resumes = useData<{items:any[]}>(employer ? null : "/resumes");
  const result = useData<{ items: Vacancy[] }>(
    `/vacancies?limit=100${mine ? "&mine=true" : ""}${spec ? "&specialization=" + spec : ""}${demoOnly&&demoWorkspace&&!employer?'&company_id='+encodeURIComponent(demoWorkspace.company_id):''}`,
  );
  return (
    <>
      <PageHead
        eyebrow="ВОЗМОЖНОСТИ С ОТКРЫТЫМИ УСЛОВИЯМИ"
        title={employer ? "Ваши вакансии и потребности" : "Открытые вакансии"}
        description={
          employer
            ? "Публикуйте вакансии или сохраняйте потребности только для подбора."
            : "Можно проявить инициативу и откликнуться самостоятельно."
        }
        actions={
          employer && (
            <>
            <VacancyTools onDraft={setEdit} onImported={()=>{result.reload();notify("Вакансии загружены")}} />
            <button className="button primary" onClick={() => setEdit({})}>
              <Plus size={18} />
              Добавить вакансию
            </button>
            </>
          )
        }
      />
      <div className="list-controls">
        {!employer&&demoWorkspace&&<div className="segmented"><button className={demoOnly?'selected':''} onClick={()=>setDemoOnly(true)}>Демо-команда</button><button className={!demoOnly?'selected':''} onClick={()=>setDemoOnly(false)}>Все вакансии</button></div>}
        {employer && (
          <div className="segmented">
            <button
              className={mine ? "selected" : ""}
              onClick={() => setMine(true)}
            >
              Моя компания
            </button>
            <button
              className={!mine ? "selected" : ""}
              onClick={() => setMine(false)}
            >
              Все вакансии
            </button>
          </div>
        )}
        <select
          aria-label="Специализация вакансий"
          value={spec}
          onChange={(e) => setSpec(e.target.value)}
        >
          <option value="">Все направления</option>
          {meta.specializations.map((s) => (
            <option key={s.id} value={s.id}>
              {s.label}
            </option>
          ))}
        </select>
      </div>
      {result.loading ? (
        <Loading />
      ) : result.error ? (
        <ErrorBox message={result.error} />
      ) : !result.data?.items.length ? (
        <Empty
          title="Здесь появятся вакансии"
          text="Добавьте первую потребность или выберите другое направление."
        />
      ) : (
        <div className="vacancy-grid">
          {result.data.items.map((v) => (
            <article className="vacancy-card" key={v.id}>
              <div className="vacancy-top">
                <div className="company-avatar">
                  <Building2 size={20} />
                </div>
                <span>{v.company_name}</span>
                {v.grade&&<Grade value={v.grade} />}
              </div>
              <h2>{v.title}</h2>
              <strong className="vacancy-salary">
                {band(v.salary_from, v.salary_to)}
              </strong>
              {employer && v.company_id === user.subject_id && <MarketBadge id={v.id} />}
              <p>
                {
                  meta.specializations.find((s) => s.id === v.specialization)
                    ?.label
                }{" "}
                · {v.work_format}
              </p>
              <Skills items={v.skills} limit={5} />
              <div className="vacancy-origin">
                {v.origin === "trudvsem_snapshot"
                  ? "Снимок API «Работа России» · компания обезличена"
                  : v.origin === "calibrated_scenario" || v.origin === "authored_scenario"
                    ? "Калиброванный тестовый сценарий"
                    : v.status === "draft"
                      ? "Потребность для подбора"
                      : "Опубликовано работодателем"}
              </div>
              <div className="vacancy-bottom">
                <span className="muted">{v.id}</span>
                {employer && v.company_id === user.subject_id && <button className="text-button" onClick={()=>location.hash="applications"}>{v.application_count||0} откликов</button>}
                <button
                  className="button text"
                  onClick={() => {
                    setView(v);
                    setMessage("");
                    setResumeId("");
                  }}
                >
                  {employer ? "Подробнее" : "Посмотреть и откликнуться"}
                  <ArrowUpRight size={17} />
                </button>
                {employer && v.company_id === user.subject_id && (
                  <button className="text-button" onClick={() => setEdit(v)}>
                    Изменить
                  </button>
                )}
              </div>
            </article>
          ))}
        </div>
      )}
      {edit && (
        <VacancyEditor
          initial={edit}
          onClose={() => setEdit(null)}
          onSaved={() => {
            setEdit(null);
            result.reload();
            notify("Вакансия сохранена");
          }}
        />
      )}
      {view && (
        <Modal
          title={view.title}
          subtitle={`${view.company_name} · ${band(view.salary_from, view.salary_to)}`}
          wide
          onClose={() => setView(null)}
        >
          <div className="vacancy-description">{view.description}</div>
          <Skills items={view.skills} limit={30} />
          {employer && view.company_id === user.subject_id && <><VacancyIntelligence vacancy={view}/><VacancyTimeForecast vacancy={view} /><TaskGenerator vacancy={view} onSent={()=>notify("Задание отправлено кандидатам")}/></>}
          {!employer && <ExpertChat vacancyId={view.id} title="Насколько эта роль соответствует вашему опыту?" />}
          {!employer && (
            <form
              onSubmit={async (e) => {
                e.preventDefault();
                setBusy(true);
                try {
                  await send("/vacancies/" + view.id + "/apply", { message, resume_id: resumeId || undefined, share_with_ats: shareWithAts });
                  notify("Отклик отправлен. Контакты открыты этой компании.");
                  setView(null);
                } catch (e) {
                  notify((e as Error).message, true);
                } finally {
                  setBusy(false);
                }
              }}
            >
              <Field label="Резюме для этого отклика">
                <select value={resumeId} onChange={e=>setResumeId(e.target.value)} disabled={resumes.loading}>
                  <option value="">Подобрать по целевой роли автоматически</option>
                  {resumes.data?.items.filter(r=>r.status!=="archived").map(r=><option key={r.id} value={r.id}>{r.target_position} · {grade(r.declared_grade)}</option>)}
                </select>
              </Field>
              {resumeId && <MatchExplanation resumeId={resumeId} vacancyId={view.id} />}
              {!resumes.loading && !resumes.data?.items.some(r=>r.status!=="archived") && <div className="notice"><LockKeyhole size={18}/>Сначала добавьте целевое резюме: оно будет передано только выбранному работодателю вместе с откликом.</div>}
              <Field label="Сообщение работодателю">
                <textarea
                  rows={3}
                  value={message}
                  onChange={(e) => setMessage(e.target.value)}
                  placeholder="Почему вам интересна эта роль?"
                />
              </Field>
              <label className="ats-consent">
                <input
                  type="checkbox"
                  checked={shareWithAts}
                  onChange={(e) => setShareWithAts(e.target.checked)}
                />
                Если работодатель подключил Talantix, разрешаю передать туда мой отклик, резюме и контакты для этой вакансии.
              </label>
              <div className="notice">
                <LockKeyhole size={18} />
                Отправляя отклик, вы открываете этой компании контакты из своего
                профиля.
              </div>
              <div className="modal-actions">
                <button className="button primary" disabled={busy||resumes.loading||!resumes.data?.items.some(r=>r.status!=="archived")}>
                  Откликнуться
                  <ArrowUpRight size={17} />
                </button>
              </div>
            </form>
          )}
        </Modal>
      )}
    </>
  );
}
export function ApplicationsPage() {
  const { user, notify } = useApp();
  const employer = user.role === "employer";
  const result = useData<{items:any[];policy?:string}>("/applications");
  const [selected,setSelected]=useState<any>(null);
  const change = async (id: string, status: string) => {
    try {
      await send("/applications/" + id, { status }, "PUT");
      result.reload();
      notify("Статус отклика обновлён");
    } catch (e) {
      notify((e as Error).message, true);
    }
  };
  return (
    <>
      <PageHead
        title={employer ? "Входящие отклики" : "Мои отклики"}
        description={employer ? "Открывайте связанное резюме и проверяйте, из каких подтверждённых сигналов складывается соответствие." : "Дополнительный путь к знакомству: кандидат проявляет инициативу."}
      />
      {employer&&result.data?.policy&&<div className="notice"><ShieldCheck size={18}/>{result.data.policy}</div>}
      {result.loading ? (
        <Loading />
      ) : result.error ? (
        <ErrorBox message={result.error} />
      ) : !result.data?.items.length ? (
        <Empty
          title="Откликов пока нет"
          text="Здесь появятся сообщения по опубликованным вакансиям."
        />
      ) : !employer ? (
        <section className="panel table-scroll">
          <table className="data-table">
            <thead>
              <tr>
                <th>Вакансия</th>
                <th>Компания</th>
                <th>Статус</th>
                <th>Дата</th>
                <th>Действие</th>
              </tr>
            </thead>
            <tbody>
              {result.data.items.map((x: any) => (
                <tr key={x.id}>
                  <td>
                    <strong>{x.title}</strong>
                    {x.message && <small>{x.message}</small>}
                  </td>
                  <td>{x.company_name}</td>
                  <td>
                    <Status value={x.status} />
                  </td>
                  <td>{date(x.created_at)}</td>
                  <td>
                    {x.status !== "withdrawn" && (
                          <button
                            className="text-button"
                            onClick={() => change(x.id, "withdrawn")}
                          >
                            Отозвать
                          </button>
                        )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </section>
      ) : (
        <div className="offers-grid applications-grid">
          {result.data.items.map((x:any)=><article className="offer-card" key={x.id}>
            <div className="offer-top"><Badge tone={x.match.score>=75?"green":x.match.score>=50?"amber":"neutral"}>{x.match.score}% · {x.match.label}</Badge><Status value={x.status}/></div>
            <h2>{x.candidate.display_name || "Кандидат"}</h2>
            <p><strong>{x.resume.target_position}</strong> · отклик на «{x.vacancy.title}»</p>
            <Skills items={x.match.matched_skills||[]} limit={6}/>
            {x.message&&<p className="offer-description">{x.message}</p>}
            <small>{date(x.created_at)} · резюме {x.resume.id||"не прикреплено"}</small>
            <div className="offer-actions"><button className="button secondary" onClick={()=>setSelected(x)}>Открыть резюме и соответствие <ArrowUpRight size={16}/></button>{x.status!=="withdrawn"&&<select aria-label="Статус отклика" value={x.status} onChange={e=>change(x.id,e.target.value)}><option value="sent">Отправлен</option><option value="viewed">Просмотрен</option><option value="interview">Интервью</option><option value="rejected">Отказ</option></select>}</div>
          </article>)}
        </div>
      )}
      {selected&&<Modal title={selected.candidate.display_name||"Отклик кандидата"} subtitle={`${selected.resume.target_position} · ${selected.match.score}% соответствия`} wide onClose={()=>setSelected(null)}>
        <div className="profile-proof"><div><Badge tone={selected.match.score>=75?"green":"amber"}>{selected.match.label}</Badge><Grade value={selected.resume.declared_grade}/></div><div className="proof-score"><strong>{selected.match.score}</strong><span>из 100<br/>объяснимое соответствие</span></div></div>
        <div className="detail-grid"><section><h3>Резюме · {selected.resume.id||"не прикреплено"}</h3><p>{selected.resume.about||"Текст резюме недоступен: попросите кандидата обновить отклик."}</p><h3>Стек из резюме</h3><Skills items={selected.resume.skills||[]} matched={selected.match.matched_skills||[]} limit={30}/>{selected.match.missing_skills?.length>0&&<><h3>Что стоит уточнить</h3><Skills items={selected.match.missing_skills} limit={30}/></>}</section><aside className="detail-conditions"><span className="eyebrow">ПОДТВЕРЖДЕНИЯ И РАСЧЁТ</span>{selected.match.components.map((part:any)=><article className="match-explanation" key={part.key}><strong>{part.label}: {part.score}/{part.max}</strong>{part.details.map((detail:string,index:number)=><p key={index}>{detail}</p>)}</article>)}{selected.verification.fsp_event_verified&&<Badge tone="green"><ShieldCheck size={14}/>Участие ФСП подтверждено</Badge>}</aside></div>
      </Modal>}
    </>
  );
}
export function TasksPage() {
  const { user, notify } = useApp();
  const result = useData("/tasks");
  const [selected, setSelected] = useState<any>(null),
    [response, setResponse] = useState(""),
    [score, setScore] = useState(80),
    [feedback, setFeedback] = useState(""),
    [create, setCreate] = useState(false),
    [candidate, setCandidate] = useState("PC00057"),
    [title, setTitle] = useState(""),
    [prompt, setPrompt] = useState("");
  return (
    <>
      <PageHead
        eyebrow="НАВЫКИ В ДВИЖЕНИИ"
        title="Короткие задания"
        description="Решите практическую задачу или предложите подход. Обратная связь обновит актуальность профиля."
        actions={
          user.role === "employer" && (
            <button className="button primary" onClick={() => setCreate(true)}>
              <Plus size={17} />
              Предложить задание
            </button>
          )
        }
      />
      <div className="notice">
        <Clock3 size={19} />
        Не чаще одного задания в неделю от одной компании. Оценка задания не
        меняет подтверждённый грейд.
      </div>
      {result.loading ? (
        <Loading />
      ) : result.error ? (
        <ErrorBox message={result.error} />
      ) : !result.data?.items.length ? (
        <Empty
          title="Время для новой задачи"
          text={
            user.role === "employer"
              ? "Предложите кандидату небольшой кейс из практики вашей команды."
              : "Здесь появятся короткие задания от работодателей."
          }
        />
      ) : (
        <div className="offers-grid">
          {result.data.items.filter((t: any)=>!t.contract).map((t: any) => (
            <article className="offer-card" key={t.id}>
              <div className="offer-top">
                <Badge tone="violet">
                  <Code2 size={14} />
                  Практический кейс
                </Badge>
                <Status value={t.status} />
              </div>
              <h2>{t.title}</h2>
              <p>{t.prompt}</p>
              <small>
                {t.company_name || t.candidate_name} · {date(t.created_at)}
              </small>
              {t.response && (
                <div className="task-answer">
                  <strong>Решение кандидата</strong>
                  <p>{t.response}</p>
                </div>
              )}
              {t.feedback && (
                <div className="feedback-box">
                  <strong>{t.score} / 100 · обратная связь</strong>
                  <p>{t.feedback}</p>
                </div>
              )}
              {((user.role === "candidate" && t.status === "pending") ||
                (user.role === "employer" && t.status === "submitted")) && (
                <button
                  className="button primary"
                  onClick={() => {
                    setSelected(t);
                    setResponse("");
                    setFeedback("");
                  }}
                >
                  {user.role === "candidate"
                    ? "Предложить решение"
                    : "Проверить решение"}
                  <ArrowRight size={17} />
                </button>
              )}
            </article>
          ))}
        </div>
      )}
      {selected && (
        <Modal
          title={selected.title}
          subtitle={selected.prompt}
          onClose={() => setSelected(null)}
        >
          <form
            onSubmit={async (e) => {
              e.preventDefault();
              try {
                await send(
                  "/tasks/" + selected.id,
                  user.role === "candidate"
                    ? { response }
                    : { score, feedback },
                  "PUT",
                );
                setSelected(null);
                result.reload();
                notify("Задание обновлено");
              } catch (e) {
                notify((e as Error).message, true);
              }
            }}
          >
            {user.role === "candidate" ? (
              <Field label="Решение или подход">
                <textarea
                  required
                  minLength={10}
                  rows={8}
                  value={response}
                  onChange={(e) => setResponse(e.target.value)}
                />
              </Field>
            ) : (
              <>
                <Field label="Оценка 0–100">
                  <input
                    type="number"
                    required
                    min={0}
                    max={100}
                    value={score}
                    onChange={(e) => setScore(Number(e.target.value))}
                  />
                </Field>
                <Field label="Содержательная обратная связь">
                  <textarea
                    required
                    minLength={5}
                    rows={5}
                    value={feedback}
                    onChange={(e) => setFeedback(e.target.value)}
                  />
                </Field>
              </>
            )}
            <div className="modal-actions">
              <button className="button primary">
                Отправить
                <Send size={17} />
              </button>
            </div>
          </form>
        </Modal>
      )}
      {create && (
        <Modal
          title="Практическое задание кандидату"
          onClose={() => setCreate(false)}
        >
          <form
            onSubmit={async (e) => {
              e.preventDefault();
              try {
                await send("/tasks", {
                  candidate_id: candidate,
                  title,
                  prompt,
                });
                setCreate(false);
                result.reload();
                notify("Задание отправлено кандидату");
              } catch (e) {
                notify((e as Error).message, true);
              }
            }}
          >
            <Field label="ID кандидата">
              <input
                required
                value={candidate}
                onChange={(e) => setCandidate(e.target.value)}
              />
            </Field>
            <Field label="Название">
              <input
                required
                minLength={3}
                value={title}
                onChange={(e) => setTitle(e.target.value)}
              />
            </Field>
            <Field label="Условие и ожидаемый результат">
              <textarea
                required
                minLength={10}
                rows={6}
                value={prompt}
                onChange={(e) => setPrompt(e.target.value)}
              />
            </Field>
            <div className="modal-actions">
              <button className="button primary">Предложить задание</button>
            </div>
          </form>
        </Modal>
      )}
    </>
  );
}
export function CompanyPage() {
  const { notify } = useApp();
  const result = useData("/profile");
  const [p, setP] = useState<any>(null);
  useEffect(() => {
    if (result.data) setP(result.data.profile);
  }, [result.data]);
  return (
    <>
      <PageHead
        title="Профиль компании"
        description="Эти сведения увидит кандидат в вашем приглашении."
      />
      {result.loading ? (
        <Loading />
      ) : result.error ? (
        <ErrorBox message={result.error} />
      ) : (
        p && (
          <form
            className="panel profile-form"
            onSubmit={async (e) => {
              e.preventDefault();
              try {
                await send("/company", p, "PUT");
                notify("Профиль компании сохранён");
              } catch (e) {
                notify((e as Error).message, true);
              }
            }}
          >
            <div className="section-heading">
              <h2>Расскажите о команде</h2>
              <Badge>Верификация компании не выполнена</Badge>
            </div>
            {[
              ["name", "Название компании"],
              ["industry", "Направление деятельности"],
              ["contact", "Способ связи для кандидатов"],
            ].map(([key, label]) => (
              <Field label={label} key={key}>
                <input
                  required
                  value={p[key]}
                  onChange={(e) => setP({ ...p, [key]: e.target.value })}
                />
              </Field>
            ))}
            <Field label="Описание компании">
              <textarea
                rows={6}
                value={p.description}
                onChange={(e) => setP({ ...p, description: e.target.value })}
              />
            </Field>
            <div className="modal-actions">
              <button className="button primary">
                Сохранить изменения
                <Check size={17} />
              </button>
            </div>
          </form>
        )
      )}
      <TalantixPanel />
    </>
  );
}

type TalantixConnection = {
  connected: boolean;
  ready: boolean;
  status: string;
  source_id?: number | null;
  last_checked_at?: string;
  mapped_vacancies: number;
  outbox: Record<string, number>;
};
type TalantixCatalogue = {
  sources: { id: number; name: string }[];
  vacancies: { id: number; title: string; department?: string; status?: string }[];
  mappings: { vacancy_id: string; external_vacancy_id: number }[];
};

function TalantixPanel() {
  const { notify } = useApp();
  const state = useData<{ connection: TalantixConnection }>("/integrations/talantix");
  const localVacancies = useData<{ items: Vacancy[] }>("/vacancies?mine=true&limit=500");
  const [accessToken, setAccessToken] = useState("");
  const [refreshToken, setRefreshToken] = useState("");
  const [catalogue, setCatalogue] = useState<TalantixCatalogue | null>(null);
  const [busy, setBusy] = useState(false);
  const connection = state.data?.connection;
  const loadCatalogue = async () => {
    setBusy(true);
    try {
      setCatalogue(await api<TalantixCatalogue>("/integrations/talantix/catalogue"));
      state.reload();
      notify("Каталог Talantix обновлён.");
    } catch (error) {
      notify((error as Error).message, true);
    } finally {
      setBusy(false);
    }
  };
  const connect = async (event: React.FormEvent) => {
    event.preventDefault();
    setBusy(true);
    try {
      await send("/integrations/talantix", {
        access_token: accessToken,
        refresh_token: refreshToken || undefined,
        expires_in: 86400,
        refresh_token_expires_in: 10368000,
      }, "PUT");
      setAccessToken("");
      setRefreshToken("");
      state.reload();
      notify("Talantix подключён. Загрузите каталог и выберите источник кандидатов.");
    } catch (error) {
      notify((error as Error).message, true);
    } finally {
      setBusy(false);
    }
  };
  const setSource = async (sourceId: number) => {
    setBusy(true);
    try {
      await send("/integrations/talantix/source", { source_id: sourceId }, "PUT");
      state.reload();
      notify("Источник кандидатов Talantix выбран.");
    } catch (error) {
      notify((error as Error).message, true);
    } finally {
      setBusy(false);
    }
  };
  const mapVacancy = async (vacancyId: string, externalVacancyId: number) => {
    setBusy(true);
    try {
      await send(`/vacancies/${vacancyId}/integrations/talantix`, { external_vacancy_id: externalVacancyId }, "PUT");
      setCatalogue(await api<TalantixCatalogue>("/integrations/talantix/catalogue"));
      state.reload();
      notify("Вакансии связаны. Согласованные отклики будут передаваться в Talantix.");
    } catch (error) {
      notify((error as Error).message, true);
    } finally {
      setBusy(false);
    }
  };
  const disconnect = async () => {
    setBusy(true);
    try {
      await api("/integrations/talantix", { method: "DELETE" });
      setCatalogue(null);
      state.reload();
      notify("Интеграция Talantix отключена.");
    } catch (error) {
      notify((error as Error).message, true);
    } finally {
      setBusy(false);
    }
  };
  return (
    <section className="panel ats-panel">
      <div className="section-heading">
        <div>
          <span className="eyebrow">ИНТЕГРАЦИИ</span>
          <h2>Talantix ATS</h2>
        </div>
        <Badge tone={connection?.ready ? "green" : connection?.connected ? "amber" : "neutral"}>
          {connection?.ready ? "Готово к передаче" : connection?.connected ? "Выберите источник" : "Не подключён"}
        </Badge>
      </div>
      <p className="muted ats-intro">
        Платформа сопоставляет вакансии с Talantix. Кандидат передаётся в ATS только после отдельного подтверждения в отклике или приглашении; токены не выводятся в интерфейс и хранятся зашифрованными.
      </p>
      {state.loading ? <Loading /> : state.error ? <ErrorBox message={state.error} retry={state.reload} /> : !connection?.connected ? (
        <form className="ats-connect" onSubmit={connect}>
          <Field label="Access token Talantix">
            <input required type="password" autoComplete="off" value={accessToken} onChange={(e) => setAccessToken(e.target.value)} placeholder="Из JSON-файла токенов Talantix" />
          </Field>
          <Field label="Refresh token Talantix">
            <input type="password" autoComplete="off" value={refreshToken} onChange={(e) => setRefreshToken(e.target.value)} placeholder="Для автоматического продления доступа" />
          </Field>
          <div className="notice"><ShieldCheck size={18} />Перед сохранением платформа проверяет токен через официальный Talantix API. Его создаёт администратор Talantix с включённым API.</div>
          <button className="button primary" disabled={busy}><PlugZap size={17} />Проверить и подключить</button>
        </form>
      ) : (
        <>
          <div className="ats-toolbar">
            <div className="ats-meta">
              <span>Привязано вакансий: <strong>{connection.mapped_vacancies}</strong></span>
              {connection.last_checked_at && <span>Проверено: {date(connection.last_checked_at)}</span>}
              {!!connection.outbox?.sent && <span>Передано: {connection.outbox.sent}</span>}
              {!!connection.outbox?.needs_review && <span className="danger-text">Требует проверки: {connection.outbox.needs_review}</span>}
            </div>
            <div className="inline-actions">
              <button className="button secondary" disabled={busy} onClick={loadCatalogue}><RefreshCw size={16} />Загрузить каталог</button>
              <button className="text-button danger-text" disabled={busy} onClick={disconnect}><Unplug size={15} />Отключить</button>
            </div>
          </div>
          {catalogue ? (
            <div className="ats-catalogue">
              <Field label="Источник кандидатов в Talantix">
                <select value={connection.source_id || ""} onChange={(e) => e.target.value && setSource(Number(e.target.value))} disabled={busy}>
                  <option value="">Выберите источник</option>
                  {catalogue.sources.map((source) => <option key={source.id} value={source.id}>{source.name} · #{source.id}</option>)}
                </select>
              </Field>
              {connection.ready && (
                <div className="ats-mapping">
                  <h3><Link2 size={17} />Связать вакансии</h3>
                  <p className="muted">Выберите вакансию Talantix для каждой вакансии платформы.</p>
                  {!localVacancies.data?.items.length ? <Empty title="Нет локальных вакансий" text="Сначала создайте вакансию в кабинете." /> : (
                    <div className="table-scroll"><table className="data-table"><thead><tr><th>Вакансия платформы</th><th>Вакансия Talantix</th></tr></thead><tbody>
                      {localVacancies.data.items.map((vacancy) => {
                        const selected = catalogue.mappings.find((item) => item.vacancy_id === vacancy.id)?.external_vacancy_id || "";
                        return <tr key={vacancy.id}><td><strong>{vacancy.title}</strong><small>{vacancy.status}</small></td><td><select value={selected} disabled={busy} onChange={(e) => e.target.value && mapVacancy(vacancy.id, Number(e.target.value))}><option value="">Не привязана</option>{catalogue.vacancies.map((external) => <option key={external.id} value={external.id}>{external.title} · #{external.id}{external.department ? ` · ${external.department}` : ""}</option>)}</select></td></tr>;
                      })}
                    </tbody></table></div>
                  )}
                </div>
              )}
            </div>
          ) : <div className="notice"><RefreshCw size={18} />Загрузите каталог: будут прочитаны источники кандидатов и вакансии Talantix, без изменения данных в ATS.</div>}
        </>
      )}
    </section>
  );
}
