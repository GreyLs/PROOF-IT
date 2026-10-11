import React, { useState, useEffect, useRef } from "react";
import {
  Bell,
  Check,
  Clock3,
  Code2,
  Play,
  Send,
  Sparkles,
  TrendingUp,
  Users,
  Upload,
  ArrowRight,
  ShieldCheck,
  X,
} from "lucide-react";
import { api, send, Vacancy, money } from "./api";
import {
  useApp,
  useData,
  PageHead,
  Modal,
  Field,
  Loading,
  ErrorBox,
  Empty,
  Badge,
} from "./ui";

export function Notifications() {
  const { navigate } = useApp();
  const data = useData<{ items: any[]; unread: number }>("/notifications");
  const [open, setOpen] = useState(false);
  useEffect(() => {
    const t = setInterval(data.reload, 15000);
    return () => clearInterval(t);
  }, []);
  return (
    <div className="notification-root">
      <button
        className="icon-button notification-toggle"
        aria-label="Уведомления"
        onClick={() => setOpen(!open)}
      >
        <Bell size={19} />
        {!!data.data?.unread && <span>{data.data.unread}</span>}
      </button>
      {open && (
        <div className="notification-popover">
          <div className="section-heading">
            <strong>Уведомления</strong>
            <button
              className="icon-button"
              aria-label="Закрыть уведомления"
              onClick={() => setOpen(false)}
            >
              <X size={16} />
            </button>
          </div>
          {!data.data?.items.length ? (
            <p className="muted">Вы в курсе всех событий</p>
          ) : (
            data.data.items.map((n) => (
              <button
                className={"notification-item " + (!n.read_at ? "unread" : "")}
                key={n.id}
                onClick={async () => {
                  await send(`/notifications/${n.id}/read`, {});
                  data.reload();
                  setOpen(false);
                  navigate("tasks");
                }}
              >
                <span>{n.title}</span>
                <small>{new Date(n.created_at).toLocaleString("ru-RU")}</small>
              </button>
            ))
          )}
        </div>
      )}
    </div>
  );
}

// Render a small, explicit Markdown subset as React text nodes, never raw HTML.
function AdviceText({ content }: { content: string }) {
  const inline = (text: string) =>
    text
      .split(/(\*\*[^*]+\*\*|`[^`]+`)/g)
      .map((part, i) =>
        part.startsWith("**") && part.endsWith("**") ? (
          <strong key={i}>{part.slice(2, -2)}</strong>
        ) : part.startsWith("`") && part.endsWith("`") ? (
          <code key={i}>{part.slice(1, -1)}</code>
        ) : (
          part
        ),
      );
  return (
    <div className="career-advice">
      {content.split(/\n\s*\n/).map((block, i) => {
        const lines = block.trim().split("\n");
        const ordered = lines.every((line) => /^\d+[.)]\s/.test(line.trim()));
        const unordered = lines.every((line) => /^[-*]\s/.test(line.trim()));
        if (ordered || unordered) {
          const items = lines.map((line, j) => (
            <li key={j}>
              {inline(line.trim().replace(/^(?:\d+[.)]|[-*])\s+/, ""))}
            </li>
          ));
          return ordered ? <ol key={i}>{items}</ol> : <ul key={i}>{items}</ul>;
        }
        return <p key={i}>{inline(block.trim())}</p>;
      })}
    </div>
  );
}

export function CareerConsultant() {
  const history = useData<{ items: { role: string; content: string }[] }>(
    "/career-consultant",
  );
  const [text, setText] = useState(""),
    [busy, setBusy] = useState(false),
    [error, setError] = useState("");
  const end = useRef<HTMLDivElement>(null);
  useEffect(() => {
    end.current?.scrollIntoView({ behavior: "smooth", block: "nearest" });
  }, [history.data, busy]);
  async function ask(e: React.FormEvent) {
    e.preventDefault();
    if (busy || text.trim().length < 3) return;
    setBusy(true);
    setError("");
    const message = text;
    try {
      await send("/career-consultant", { text: message });
      setText("");
      history.reload();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  const prompts = [
    "Хочу сменить позицию. Какие навыки из моего опыта можно перенести?",
    "Я начинаю карьеру. Помоги выбрать направление и план первых шагов.",
    "Хочу расти горизонтально: какие смежные роли мне подходят?",
  ];
  return (
    <>
      <PageHead
        eyebrow="КАРЬЕРА С НОВОЙ ТОЧКИ ЗРЕНИЯ"
        title="Персональный hr-консультант"
        description="Разберите свой опыт, найдите смежную роль и составьте понятный план перехода."
      />
      <section className="career-panel panel">
        <div className="career-intro">
          <div className="ai-orb">
            <Sparkles size={26} />
          </div>
          <div>
            <h2>Ваш следующий шаг</h2>
            <p>
              Начнём с того, что вам уже удаётся, и того, что хочется
              попробовать.
            </p>
          </div>
        </div>
        <div className="career-prompts">
          {prompts.map((p) => (
            <button key={p} onClick={() => setText(p)}>
              {p}
              <ArrowRight size={16} />
            </button>
          ))}
        </div>
        <div className="career-transcript" aria-live="polite">
          {history.data?.items.map((m, i) => (
            <article className={"career-message " + m.role} key={i}>
              <small>{m.role === "user" ? "Вы" : "Ваш hr-консультант"}</small>
              {m.role === "assistant" ? (
                <AdviceText content={m.content} />
              ) : (
                <p>{m.content}</p>
              )}
            </article>
          ))}
          {busy && (
            <article className="career-message assistant">
              <small>Ваш hr-консультант</small>
              <p className="pulse">
                Разбираю ваш опыт и возможные направления…
              </p>
            </article>
          )}
          <div ref={end} />
        </div>
        {error && <ErrorBox message={error} />}
        <form className="career-composer" onSubmit={ask}>
          <textarea
            rows={3}
            value={text}
            maxLength={2000}
            onChange={(e) => setText(e.target.value)}
            placeholder="Что вам интересно? Какой опыт хотите использовать по-новому?"
            aria-label="Сообщение hr-консультанту"
          />
          <button
            className="button primary"
            disabled={busy || text.trim().length < 3}
          >
            <Send size={17} />
            {busy ? "Обдумываю…" : "Обсудить"}
          </button>
        </form>
        <p className="muted career-note">
          Консультация учитывает ваши целевые резюме. Для беседы достаточно
          профессионального опыта; контакты и ФИО не нужны.
        </p>
      </section>
    </>
  );
}

export function MarketBadge({ id }: { id: string }) {
  const r = useData<any>(`/vacancies/${id}/market`);
  return r.data ? (
    <Badge tone={r.data.salary_status === "raise" ? "amber" : "green"}>
      {r.data.salary_label}
    </Badge>
  ) : null;
}
export function VacancyIntelligence({ vacancy }: { vacancy: Vacancy }) {
  const r = useData<any>(`/vacancies/${vacancy.id}/market`);
  const [open, setOpen] = useState(true);
  if (r.loading) return <Loading />;
  if (r.error) return <ErrorBox message={r.error} />;
  const m = r.data;
  const max = Math.max(1, ...m.salary_distribution.map((x: any) => x.count));
  return (
    <section className="market-panel">
      <button
        className="market-toggle"
        onClick={() => setOpen(!open)}
        aria-expanded={open}
      >
        <div>
          <span className="eyebrow">РЫНОК ПОД ЭТУ ВАКАНСИЮ</span>
          <h3>Потенциал найма</h3>
        </div>
        <Badge tone={m.salary_status === "raise" ? "amber" : "green"}>
          {m.salary_label}
        </Badge>
      </button>
      {open && (
        <>
          <div className="market-kpis">
            <div>
              <Users size={20} />
              <strong>{m.relevant_candidates}</strong>
              <span>кандидатов в поиске</span>
            </div>
            <div>
              <ShieldCheck size={20} />
              <strong>{m.verified_candidates}</strong>
              <span>подтвердили навыки тестом</span>
            </div>
            <div>
              <TrendingUp size={20} />
              <strong>
                {m.candidate_salary.median
                  ? money(m.candidate_salary.median)
                  : "—"}
              </strong>
              <span>медиана ожиданий</span>
            </div>
          </div>
          {m.recommended_salary && (
            <div className="notice">
              <TrendingUp size={19} />
              Для конкурентного предложения рекомендуем ориентироваться на{" "}
              {money(m.recommended_salary)}. Условия можно повысить; снижение не
              предлагается.
            </div>
          )}
          <div className="market-charts">
            <section>
              <h4>Ожидания по вознаграждению</h4>
              {m.small_sample ? (
                <p className="muted">
                  Ожидания раскрываются в агрегате от 5 кандидатов.
                </p>
              ) : (
                <>
                  <p className="muted">
                    Средние 50%: {money(m.candidate_salary.p25)} –{" "}
                    {money(m.candidate_salary.p75)}
                  </p>
                  <div
                    className="salary-chart"
                    role="img"
                    aria-label="Распределение зарплатных ожиданий"
                  >
                    {m.salary_distribution.map((b: any, i: number) => (
                      <div className="salary-bin" key={i}>
                        <strong>{b.count}</strong>
                        <div
                          className="salary-bar"
                          style={{
                            height: `${Math.max(3, (110 * b.count) / max)}px`,
                          }}
                        />
                        <span>
                          {Math.round(b.from / 1000)}–{Math.round(b.to / 1000)}{" "}
                          тыс.
                        </span>
                      </div>
                    ))}
                  </div>
                </>
              )}
            </section>
            <section>
              <h4>Покрытие ключевого стека</h4>
              {m.skill_coverage.map((s: any) => (
                <div className="skill-market-row" key={s.skill}>
                  <div>
                    <span>{s.skill}</span>
                    <strong>
                      {s.count} / {m.relevant_candidates}
                    </strong>
                  </div>
                  <div className="skill-market-track">
                    <i
                      style={{
                        width: `${(100 * s.count) / Math.max(1, m.relevant_candidates)}%`,
                      }}
                    />
                  </div>
                </div>
              ))}
            </section>
          </div>
        </>
      )}
    </section>
  );
}

export function VacancyTools({
  onDraft,
  onImported,
}: {
  onDraft: (v: Partial<Vacancy>) => void;
  onImported: () => void;
}) {
  const [mode, setMode] = useState(""),
    [text, setText] = useState(""),
    [busy, setBusy] = useState(false),
    [error, setError] = useState(""),
    [rows, setRows] = useState<any[]>([]);
  async function generate() {
    setBusy(true);
    setError("");
    try {
      const r = await send("/vacancies/generate", { text });
      setMode("");
      onDraft(r.draft);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  async function read(file: File) {
    try {
      if (file.size > 1024 * 1024) throw Error("Файл должен быть меньше 1 МБ");
      const d = JSON.parse(await file.text());
      const a = Array.isArray(d) ? d : d.items;
      if (!Array.isArray(a) || !a.length || a.length > 50)
        throw Error("Нужен JSON-массив из 1–50 вакансий");
      setRows(a);
      setError("");
    } catch (e) {
      setError((e as Error).message);
    }
  }
  async function upload() {
    setBusy(true);
    setError("");
    try {
      await send("/vacancies/bulk", { items: rows });
      setMode("");
      setRows([]);
      onImported();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  return (
    <>
      <button
        className="button secondary"
        onClick={() => {
          setMode("generate");
          setError("");
        }}
      >
        <Sparkles size={17} />
        Создать по запросу
      </button>
      <button
        className="button secondary"
        onClick={() => {
          setMode("bulk");
          setError("");
        }}
      >
        <Upload size={17} />
        Загрузить до 50
      </button>
      {mode && (
        <Modal
          title={
            mode === "generate" ? "Вакансия из вашей идеи" : "Пакет вакансий"
          }
          onClose={() => setMode("")}
        >
          <p className="muted">
            {mode === "generate"
              ? "Опишите роль, основные задачи, стек и условия. Полученный черновик можно отредактировать перед публикацией."
              : "Все вакансии проверяются до сохранения. Если в строке ошибка, пакет не будет загружен частично."}
          </p>
          {mode === "generate" ? (
            <Field label="Кого вы ищете?">
              <textarea
                rows={6}
                value={text}
                onChange={(e) => setText(e.target.value)}
                maxLength={2000}
                placeholder="Middle Python-разработчик, FastAPI и PostgreSQL, удалённо, 180–250 тысяч рублей. Разрабатывать API и улучшать надёжность."
              />
            </Field>
          ) : (
            <>
              <Field label="JSON с вакансиями">
                <input
                  type="file"
                  accept=".json,application/json"
                  onChange={(e) =>
                    e.target.files?.[0] && read(e.target.files[0])
                  }
                />
              </Field>
              <a
                className="text-button"
                href="/vacancy-import-example.json"
                download
              >
                Скачать пример файла
              </a>
              {!!rows.length && (
                <p>{rows.length} вакансий готовы к проверке и загрузке</p>
              )}
            </>
          )}
          {error && <ErrorBox message={error} />}
          <button
            className="button primary"
            disabled={
              busy || (mode === "generate" ? text.length < 10 : !rows.length)
            }
            onClick={mode === "generate" ? generate : upload}
          >
            {busy
              ? "Подготавливаем…"
              : mode === "generate"
                ? "Создать черновик"
                : "Проверить и загрузить"}
            <ArrowRight size={17} />
          </button>
        </Modal>
      )}
    </>
  );
}

export function TaskGenerator({
  vacancy,
  onSent,
}: {
  vacancy: Vacancy;
  onSent?: () => void;
}) {
  const candidates = useData<{ items: any[] }>(
    `/vacancies/${vacancy.id}/task-recipients`,
  );
  const [open, setOpen] = useState(false),
    [draft, setDraft] = useState<any>(null),
    [instruction, setInstruction] = useState(""),
    [selected, setSelected] = useState<string[]>([]),
    [busy, setBusy] = useState(false),
    [error, setError] = useState("");
  async function generate() {
    setBusy(true);
    setError("");
    try {
      setDraft(
        await send("/tasks/generate", { vacancy_id: vacancy.id, instruction }),
      );
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  async function dispatch() {
    setBusy(true);
    setError("");
    try {
      await send("/tasks/dispatch", {
        draft_id: draft.draft_id,
        candidate_ids: selected,
      });
      setOpen(false);
      onSent?.();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  return (
    <>
      <button className="button secondary" onClick={() => setOpen(true)}>
        <Code2 size={17} />
        Тестовое под вакансию
      </button>
      {open && (
        <Modal
          title="Практическое задание"
          subtitle={vacancy.title}
          wide
          onClose={() => setOpen(false)}
        >
          <p className="muted">
            20–30 минут на практическую задачу. Перед отправкой условие и эталон
            проходят проверку запуска.
          </p>
          <Field label="Какие навыки проверить?">
            <textarea
              rows={2}
              value={instruction}
              maxLength={1500}
              onChange={(e) => setInstruction(e.target.value)}
              placeholder="Например: обработка данных, граничные случаи, чистый код"
            />
          </Field>
          <button className="button primary" disabled={busy} onClick={generate}>
            <Sparkles size={17} />
            {busy
              ? "Подготавливаем и проверяем…"
              : draft
                ? "Сгенерировать другой вариант"
                : "Сгенерировать задание"}
          </button>
          {draft && (
            <section className="generated-task">
              <h3>{draft.task.title}</h3>
              <p className="preserve-lines">{draft.task.prompt}</p>
              <Badge tone="green">
                Эталон прошёл {draft.task.validation?.reference_tests_passed}{" "}
                автотестов
              </Badge>
              <h4>Заинтересованные кандидаты</h4>
              {!candidates.data?.items.length ? (
                <p className="muted">
                  Кандидаты появятся после отклика или принятия приглашения по
                  этой вакансии.
                </p>
              ) : (
                candidates.data.items.map((c) => (
                  <label className="task-recipient" key={c.candidate_id}>
                    <input
                      type="checkbox"
                      checked={selected.includes(c.candidate_id)}
                      onChange={(e) =>
                        setSelected(
                          e.target.checked
                            ? [...selected, c.candidate_id]
                            : selected.filter((x) => x !== c.candidate_id),
                        )
                      }
                    />
                    {c.label || c.candidate_id}
                  </label>
                ))
              )}
              <button
                className="button primary"
                disabled={busy || !selected.length}
                onClick={dispatch}
              >
                <Send size={16} />
                Отправить выбранным ({selected.length})
              </button>
            </section>
          )}
          {error && <ErrorBox message={error} />}
        </Modal>
      )}
    </>
  );
}

export function PracticalTasks() {
  const { user, notify, navigate } = useApp();
  const data = useData<{ items: any[] }>("/tasks");
  const vacancies = useData<{ items: Vacancy[] }>(
    user.role === "employer" ? "/vacancies?mine=true&limit=50" : null,
  );
  const [task, setTask] = useState<any>(null),
    [code, setCode] = useState(""),
    [result, setResult] = useState<any>(null),
    [busy, setBusy] = useState(""),
    [error, setError] = useState(""),
    [vacancyId, setVacancyId] = useState("");
  const employer = user.role === "employer";
  async function decide(t: any, status: string) {
    try {
      await send(`/tasks/${t.id}/decision`, { status }, "PUT");
      data.reload();
      if (status === "accepted") {
        setTask({ ...t, status });
        setCode(t.contract?.starter_code || "def solve(data):\n    pass\n");
        setResult(null);
      }
    } catch (e) {
      notify((e as Error).message, true);
    }
  }
  async function run(final: boolean) {
    setBusy(final ? "review" : "run");
    setError("");
    try {
      const r = await send(`/tasks/${task.id}/${final ? "submit" : "run"}`, {
        code,
      });
      setResult(r);
      if (final) {
        setTask({
          ...task,
          status: "reviewed",
          review: r,
          score: r.score,
          feedback: r.review?.feedback,
        });
        data.reload();
        notify("Результат отправлен работодателю");
      }
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy("");
    }
  }
  const own = vacancies.data?.items.find((v) => v.id === vacancyId);
  return (
    <>
      <div className="section-heading">
        <a
          className="text-button"
          href="#tasks-manual"
          onClick={(e) => {
            e.preventDefault();
            navigate("tasks-manual");
          }}
        >
          Текстовые задания и ручное ревью →
        </a>
      </div>
      <PageHead
        eyebrow="ПОКАЖИТЕ НАВЫКИ В ДЕЛЕ"
        title="Практические задания"
        description={
          employer
            ? "Задания под вашу вакансию, объективные автотесты и содержательное ревью решения."
            : "Примите интересную задачу, выполните её в песочнице и сразу получите обратную связь."
        }
      />
      {employer && (
        <section className="panel task-vacancy-picker">
          <Field label="Вакансия для задания">
            <select
              value={vacancyId}
              onChange={(e) => setVacancyId(e.target.value)}
            >
              <option value="">Выберите свою вакансию</option>
              {vacancies.data?.items.map((v) => (
                <option key={v.id} value={v.id}>
                  {v.title}
                </option>
              ))}
            </select>
          </Field>
          {own && (
            <TaskGenerator
              vacancy={own}
              onSent={() => {
                data.reload();
                notify("Задание отправлено");
              }}
            />
          )}
        </section>
      )}
      {data.loading ? (
        <Loading />
      ) : data.error ? (
        <ErrorBox message={data.error} />
      ) : !data.data?.items.length ? (
        <Empty
          title="Заданий пока нет"
          text={
            employer
              ? "Выберите вакансию и отправьте задачу заинтересованным кандидатам."
              : "Приглашение на тестовое появится здесь и в уведомлениях."
          }
        />
      ) : (
        <div className="offers-grid">
          {data.data.items.map((t) => (
            <article className="offer-card practical-task" key={t.id}>
              <div className="offer-top">
                <Badge tone={t.status === "reviewed" ? "green" : "violet"}>
                  {(
                    {
                      pending: "Новое задание",
                      accepted: "В работе",
                      declined: "Отказ",
                      reviewing: "На проверке",
                      reviewed: "Проверено",
                      submitted: "Отправлено",
                    } as any
                  )[t.status] || t.status}
                </Badge>
                <Code2 size={18} />
              </div>
              <h2>{t.title}</h2>
              <p className="muted">
                {t.participant} {t.vacancy_title && `· ${t.vacancy_title}`}
              </p>
              <p className="task-excerpt">{t.prompt}</p>
              {t.score != null && (
                <div className="task-score">
                  <strong>{t.score}</strong>
                  <span>
                    / 100
                    <br />
                    результат проверки
                  </span>
                </div>
              )}
              {t.feedback && <p>{t.feedback}</p>}
              <div className="offer-actions">
                {!employer && t.status === "pending" && t.contract ? (
                  <>
                    <button
                      className="button primary"
                      onClick={() => decide(t, "accepted")}
                    >
                      <Check size={16} />
                      Принять
                    </button>
                    <button
                      className="button secondary"
                      onClick={() => decide(t, "declined")}
                    >
                      Отказаться
                    </button>
                  </>
                ) : (
                  <button
                    className="button secondary"
                    onClick={() => {
                      setTask(t);
                      setCode(t.response || t.contract?.starter_code || "");
                      setResult(t.review);
                      setError("");
                    }}
                  >
                    {!employer && t.status === "accepted"
                      ? "Открыть песочницу"
                      : "Условие и результат"}
                    <ArrowRight size={16} />
                  </button>
                )}
              </div>
            </article>
          ))}
        </div>
      )}
      {task && (
        <Modal
          title={task.title}
          subtitle={task.vacancy_title || task.participant}
          wide
          onClose={() => {
            if (!busy) setTask(null);
          }}
        >
          <div className="sandbox-layout">
            <section>
              <span className="eyebrow">УСЛОВИЕ</span>
              <p className="preserve-lines">{task.prompt}</p>
              {task.contract?.public_tests && (
                <details>
                  <summary>Примеры и открытые автотесты</summary>
                  <pre className="sandbox-tests">
                    {JSON.stringify(task.contract.public_tests, null, 2)}
                  </pre>
                </details>
              )}
            </section>
            <section>
              {!employer && task.status === "accepted" && task.contract ? (
                <>
                  <div className="sandbox-toolbar">
                    <Badge tone="violet">Python 3.12</Badge>
                    <small>solve(data) → JSON-результат</small>
                    <span>Без сети · изолированный запуск</span>
                  </div>
                  <textarea
                    className="code-editor"
                    spellCheck={false}
                    aria-label="Код решения"
                    value={code}
                    onChange={(e) => setCode(e.target.value)}
                    maxLength={20000}
                    rows={16}
                    onKeyDown={(e) => {
                      if (e.key === "Tab") {
                        e.preventDefault();
                        const el = e.currentTarget;
                        const pos = el.selectionStart;
                        setCode(
                          code.slice(0, pos) +
                            "    " +
                            code.slice(el.selectionEnd),
                        );
                        requestAnimationFrame(() => {
                          el.selectionStart = el.selectionEnd = pos + 4;
                        });
                      }
                    }}
                  />
                  <div className="sandbox-actions">
                    <button
                      className="button secondary"
                      disabled={!!busy}
                      onClick={() => run(false)}
                    >
                      <Play size={17} />
                      {busy === "run" ? "Выполняем…" : "Запустить автотесты"}
                    </button>
                    <button
                      className="button primary"
                      disabled={!!busy}
                      onClick={() => run(true)}
                    >
                      <Send size={17} />
                      {busy === "review" ? "Проверка и ревью…" : "Готово"}
                    </button>
                  </div>
                </>
              ) : (
                task.response && (
                  <pre className="code-readonly">{task.response}</pre>
                )
              )}
              {busy === "review" && (
                <p className="notice">
                  <Clock3 size={17} />
                  Проверяем открытые и скрытые случаи, затем готовим ревью. Это
                  может занять несколько минут.
                </p>
              )}
              {result && (
                <section className="sandbox-result" aria-live="polite">
                  <h3>
                    {result.score != null
                      ? `${result.score} / 100`
                      : "Результат запуска"}
                  </h3>
                  <p>
                    Автотесты: {result.passed} из {result.total}
                  </p>
                  {result.error && (
                    <p>
                      {result.error === "time_or_output_limit"
                        ? "Превышен лимит времени или вывода."
                        : result.error}
                    </p>
                  )}
                  {result.review?.feedback && <p>{result.review.feedback}</p>}
                  {result.integrity?.review_recommended && (
                    <p className="muted">
                      Структурное сходство требует проверки контекста. Результат
                      не понижен автоматически.
                    </p>
                  )}
                  {result.review?.improvements?.length > 0 && (
                    <>
                      <h4>Что улучшить</h4>
                      <ul>
                        {result.review.improvements.map(
                          (v: string, i: number) => (
                            <li key={i}>{v}</li>
                          ),
                        )}
                      </ul>
                    </>
                  )}
                </section>
              )}
              {error && <ErrorBox message={error} />}
            </section>
          </div>
        </Modal>
      )}
    </>
  );
}
