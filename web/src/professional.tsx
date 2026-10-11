import React, { useEffect, useRef, useState } from "react";
import { ShieldCheck, Sparkles, Timer, ArrowRight, Check } from "lucide-react";
import { api, send } from "./api";
import {
  useApp,
  useData,
  PageHead,
  Field,
  Loading,
  ErrorBox,
  Badge,
  Empty,
} from "./ui";
import "./professional.css";

const base = "/intelligence/assessment";
const topics: Record<string, string> = {
  engineering: "Инженерия и надёжность",
  data: "Данные и измерения",
  delivery: "Поставка и принятие решений",
  pilot: "Дополнительный вопрос",
};
const labels: Record<string, string> = {
  junior: "Junior",
  middle: "Middle",
  senior: "Senior",
};

function ExpertEditor({
  draft,
  busy,
  submit,
}: {
  draft: any;
  busy: boolean;
  submit: (content: any, note: string) => void;
}) {
  const [content, setContent] = useState({ ...draft.content }),
    [note, setNote] = useState("");
  return (
    <details className="cat-editor">
      <summary>Проверить и уточнить вопрос</summary>
      <Field label="Условие">
        <textarea
          value={content.prompt}
          maxLength={3000}
          onChange={(e) => setContent({ ...content, prompt: e.target.value })}
        />
      </Field>
      {content.options.map((option: string, i: number) => (
        <Field key={i} label={`Вариант ${String.fromCharCode(65 + i)}`}>
          <input
            value={option}
            maxLength={600}
            onChange={(e) =>
              setContent({
                ...content,
                options: content.options.map((v: string, j: number) =>
                  j === i ? e.target.value : v,
                ),
              })
            }
          />
        </Field>
      ))}
      <Field label="Правильный вариант">
        <select
          value={content.correct}
          onChange={(e) =>
            setContent({ ...content, correct: Number(e.target.value) })
          }
        >
          {content.options.map((_: string, i: number) => (
            <option key={i} value={i}>
              {String.fromCharCode(65 + i)}
            </option>
          ))}
        </select>
      </Field>
      <Field label="Обоснование">
        <textarea
          value={content.rationale}
          onChange={(e) =>
            setContent({ ...content, rationale: e.target.value })
          }
        />
      </Field>
      <Field label="Заключение эксперта">
        <textarea
          value={note}
          maxLength={2000}
          onChange={(e) => setNote(e.target.value)}
        />
      </Field>
      <button
        className="button primary"
        disabled={busy || note.trim().length < 10}
        onClick={() => submit(content, note)}
      >
        Сохранить проверку и принять в пилот
      </button>
    </details>
  );
}

function NeedPreview() {
  const { meta } = useApp();
  const [text, setText] = useState(""),
    [result, setResult] = useState<any>(null),
    [busy, setBusy] = useState(false),
    [error, setError] = useState("");
  return (
    <section className="panel">
      <h2>От короткого запроса — к точной потребности</h2>
      <p className="muted">
        Проверьте направление, обязательный стек и условия до создания вакансии.
        Неоднозначность не превращается в выдуманные требования.
      </p>
      <Field label="Кого ищете">
        <textarea
          value={text}
          maxLength={4000}
          placeholder="Нужен Python / Backend, Middle, Python, SQL, PostgreSQL. 180–250 тыс руб. Удалённо."
          onChange={(e) => setText(e.target.value)}
        />
      </Field>
      <button
        className="button secondary"
        disabled={busy || text.trim().length < 3}
        onClick={async () => {
          setBusy(true);
          setError("");
          try {
            setResult(await send(base + "/need-preview", { text }));
          } catch (e: any) {
            setError(e.message);
          } finally {
            setBusy(false);
          }
        }}
      >
        {busy ? "Разбираем запрос…" : "Разобрать потребность"}
      </button>
      {error && <ErrorBox message={error} />}{" "}
      {result && (
        <div className="cat-preview">
          <h3>
            {meta.specializations.find((s) => s.id === result.specialization)
              ?.label || "Уточните профессиональное направление"}
          </h3>
          <p>
            {result.grade || "Уровень не указан"} ·{" "}
            {result.work_format || "Формат не указан"}
          </p>
          <p>
            Обязательные навыки:{" "}
            {result.required_skills.join(", ") || "не указаны"}
          </p>
          {result.optional_skills.length > 0 && (
            <p>Будет плюсом: {result.optional_skills.join(", ")}</p>
          )}
          {result.salary_from && (
            <p>
              Вознаграждение: {result.salary_from.toLocaleString("ru-RU")}–
              {result.salary_to.toLocaleString("ru-RU")} ₽
            </p>
          )}
          {result.needs_confirmation.length > 0 && (
            <p className="muted">
              Перед публикацией уточните:{" "}
              {result.needs_confirmation
                .map(
                  (v: string) =>
                    (
                      ({
                        specialization: "направление",
                        grade: "уровень",
                        salary: "вознаграждение",
                        work_format: "формат работы",
                      }) as any
                    )[v],
                )
                .join(", ")}
              .
            </p>
          )}
          <p className="muted">
            Это разбор запроса. Вакансия не создана и не опубликована.
          </p>
        </div>
      )}
    </section>
  );
}

export function ProfessionalAssessment() {
  const { meta, user, navigate } = useApp();
  const history = useData<any>(base + "/attempts");
  const oidc = useData<any>(base + "/oidc");
  const [active, setActive] = useState<any>(null),
    [spec, setSpec] = useState("backend_python"),
    [mode, setMode] = useState("express"),
    [extra, setExtra] = useState(false),
    [choice, setChoice] = useState<number | null>(null),
    [busy, setBusy] = useState(false),
    [error, setError] = useState(""),
    [now, setNow] = useState(Date.now()),
    [notice, setNotice] = useState("");
  const booted = useRef(false);
  const guest = user.email.endsWith("@guest.proofit.invalid");
  useEffect(() => {
    const timer = setInterval(() => setNow(Date.now()), 1000);
    return () => clearInterval(timer);
  }, []);
  useEffect(() => {
    if (history.data && !booted.current) {
      booted.current = true;
      const row = history.data.items.find((x: any) => x.status === "active");
      if (row) setActive(row);
      else if (guest) void start("express");
    }
  }, [history.data]);
  useEffect(() => {
    if (!active || active.status !== "active") return;
    const signal = (kind: string) => {
      void send(base + `/attempts/${active.id}/signals`, {
        kind,
        count: 1,
      }).catch(() => {});
      if (kind === "paste")
        setNotice(
          "Вставка отмечена в журнале. Сигнал рассматривается вместе с решением и пояснениями.",
        );
    };
    const copy = () => signal("copy"),
      paste = () => signal("paste"),
      visibility = () => {
        if (document.hidden) signal("visibility_hidden");
      },
      keys = (e: KeyboardEvent) => {
        if (e.key === "PrintScreen") signal("print_screen");
      };
    document.addEventListener("copy", copy);
    document.addEventListener("paste", paste);
    document.addEventListener("visibilitychange", visibility);
    document.addEventListener("keydown", keys);
    return () => {
      document.removeEventListener("copy", copy);
      document.removeEventListener("paste", paste);
      document.removeEventListener("visibilitychange", visibility);
      document.removeEventListener("keydown", keys);
    };
  }, [active?.id, active?.status]);
  async function start(selectedMode = mode) {
    setBusy(true);
    setError("");
    try {
      const row = await send(base + "/attempts", {
        specialization: spec,
        mode: selectedMode,
        extra_time: extra,
      });
      setActive(row);
      setChoice(null);
      history.reload();
    } catch (e: any) {
      setError(e.message);
    } finally {
      setBusy(false);
    }
  }
  async function answer() {
    if (choice === null || !active) return;
    setBusy(true);
    setError("");
    try {
      const row = await send(base + `/attempts/${active.id}/answer`, {
        question_id: active.contract.question.id,
        answer: choice,
        revision: active.revision,
      });
      setActive(row);
      setChoice(null);
      setNotice("");
      if (row.status === "completed") history.reload();
    } catch (e: any) {
      setError(e.message);
      history.reload();
    } finally {
      setBusy(false);
    }
  }
  const result = active?.result;
  const q = active?.contract.question;
  const seconds = q
    ? Math.max(
        0,
        Math.ceil(
          (Date.parse(active.item_started_at) +
            q.time_limit_seconds * 1000 -
            now) /
            1000,
        ),
      )
    : 0;
  return (
    <>
      <PageHead
        eyebrow="PROOF ASSESSMENT"
        title="Проверьте свой профессиональный уровень"
        description="Персональные вопросы, рабочие ситуации и понятный профиль сильных сторон."
      />
      {error && <ErrorBox message={error} />}
      {!active && (
        <section className="panel cat-start">
          <h2>Выберите цель</h2>
          <div className="cat-fields">
            <Field label="Направление оценки">
              <select
                aria-label="Направление оценки"
                value={spec}
                onChange={(e) => setSpec(e.target.value)}
              >
                {meta.specializations.map((s) => (
                  <option key={s.id} value={s.id}>
                    {s.label}
                  </option>
                ))}
              </select>
            </Field>
            <Field label="Формат оценки">
              <select
                aria-label="Формат оценки"
                value={mode}
                onChange={(e) => setMode(e.target.value)}
              >
                <option value="express">Экспресс · 8 вопросов</option>
                <option value="full">
                  Развёрнутая оценка · до 32 вопросов
                </option>
              </select>
            </Field>
          </div>
          <label className="checkbox">
            <input
              type="checkbox"
              checked={extra}
              onChange={(e) => setExtra(e.target.checked)}
            />
            <span>Нужно дополнительное время на чтение</span>
          </label>
          <button
            className="button primary"
            disabled={busy}
            onClick={() => start()}
          >
            <Sparkles size={18} />
            {busy ? "Подготавливаем…" : "Начать оценку"}
          </button>
          <p className="muted">
            Результат дополняет ваш профиль навыков. Подтверждённая квалификация
            и опубликованное резюме сохраняются под вашим контролем.
          </p>
        </section>
      )}
      {q && active.status === "active" && (
        <section className="panel cat-question">
          <div className="section-heading">
            <Badge>
              Вопрос {active.contract.answered + 1} · {topics[q.topic]}
            </Badge>
            <span className="cat-timer">
              <Timer size={17} />
              {Math.floor(seconds / 60)}:{String(seconds % 60).padStart(2, "0")}
            </span>
          </div>
          <div
            className="cat-progress"
            role="progressbar"
            aria-label="Прогресс оценки"
            aria-valuenow={active.contract.answered}
            aria-valuemin={0}
            aria-valuemax={active.contract.max_questions}
          >
            <span
              style={{
                width: `${(100 * active.contract.answered) / active.contract.max_questions}%`,
              }}
            />
          </div>
          <h2>{q.prompt}</h2>
          <div
            className="cat-options"
            role="radiogroup"
            aria-label="Варианты ответа"
          >
            {q.options.map((v: string, i: number) => (
              <label key={i} className={choice === i ? "selected" : ""}>
                <input
                  type="radio"
                  name="cat-answer"
                  value={i}
                  checked={choice === i}
                  onChange={() => setChoice(i)}
                />
                <span>{String.fromCharCode(65 + i)}</span>
                <div>{v}</div>
                {choice === i && <Check size={17} />}
              </label>
            ))}
          </div>
          {notice && (
            <p role="status" className="muted">
              {notice}
            </p>
          )}
          <div className="cat-actions">
            <button
              className="button primary"
              disabled={busy || choice === null}
              onClick={answer}
            >
              {busy ? "Сохраняем…" : "Ответить"}
              <ArrowRight size={17} />
            </button>
            <button
              className="button text"
              disabled={busy}
              onClick={async () => {
                try {
                  await send(base + `/attempts/${active.id}/abandon`);
                  setActive(null);
                  history.reload();
                } catch (e: any) {
                  setError(e.message);
                }
              }}
            >
              Завершить позже
            </button>
          </div>
          <p className="muted">
            Фиксируются только события смены вкладки и копирования. Содержимое
            буфера, изображение экрана и личные данные не собираются. Сигналы
            требуют проверки человеком.
          </p>
        </section>
      )}
      {result && (
        <section className="panel cat-result">
          <Badge tone="green">Оценка готова</Badge>
          <h2>Ваш профиль: {labels[result.suggested_grade]}</h2>
          <p className="muted">
            Распределение уровней и областей помогает выбрать следующую
            практику.
          </p>
          <div className="cat-grades">
            {Object.entries(result.grade_probabilities).map(([k, v]) => (
              <div key={k}>
                <span>{labels[k]}</span>
                <strong>{Math.round(Number(v) * 100)}%</strong>
                <div className="cat-progress">
                  <span style={{ width: `${Number(v) * 100}%` }} />
                </div>
              </div>
            ))}
          </div>
          <div className="cat-domains">
            {Object.entries(result.domains).map(([k, v]: [string, any]) => (
              <article key={k}>
                <h3>{topics[k]}</h3>
                <strong>
                  {v.correct}/{v.answered}
                </strong>
                <small>решённых вопросов</small>
              </article>
            ))}
          </div>
          {result.review_required && (
            <p className="muted">
              Некоторые события требуют контекстной проверки. Вы можете оспорить
              запись в журнале решений.
            </p>
          )}
          <div className="cat-actions">
            <button
              className="button primary"
              onClick={() => navigate("career-route")}
            >
              Построить карьерный маршрут
            </button>
            <button
              className="button secondary"
              onClick={() => {
                setActive(null);
                setChoice(null);
              }}
            >
              Выбрать следующую цель
            </button>
          </div>
        </section>
      )}
      <section className="panel cat-identity">
        <div>
          <ShieldCheck size={23} />
          <h2>ФСП ID</h2>
          <p className="muted">
            Привязка удостоверяет связь с внешним профилем. Достижения
            подтверждаются отдельно.
          </p>
        </div>
        <button
          className="button secondary"
          disabled={busy || !oidc.data?.enabled}
          onClick={async () => {
            setBusy(true);
            try {
              const r = await send(base + "/oidc");
              location.assign(r.authorization_url);
            } catch (e: any) {
              setError(e.message);
              setBusy(false);
            }
          }}
        >
          {oidc.data?.linked ? "Обновить привязку" : "Привязать ФСП ID"}
        </button>
      </section>
      {history.loading ? (
        <Loading />
      ) : (
        <section className="panel">
          <h2>История оценок</h2>
          {!history.data?.items.length ? (
            <Empty
              title="Первая оценка впереди"
              text="Выберите направление и начните с восьми вопросов."
            />
          ) : (
            <div className="cat-history">
              {history.data.items.map((x: any) => (
                <button
                  className="button secondary"
                  key={x.id}
                  onClick={() => {
                    setActive(x);
                    setChoice(null);
                  }}
                >
                  {meta.specializations.find((s) => s.id === x.specialization)
                    ?.label || x.specialization}{" "}
                  · {x.mode === "express" ? "Экспресс" : "Полная"} ·{" "}
                  {x.status === "completed"
                    ? labels[x.result.suggested_grade]
                    : x.status === "active"
                      ? "Продолжить"
                      : "Архив"}
                </button>
              ))}
            </div>
          )}
        </section>
      )}
      {guest && (
        <p className="muted">
          Гостевая сессия действует 30 минут. Профиль приватен.{" "}
          <button
            className="text-button"
            onClick={async () => {
              try {
                await send("/account", { password: "" }, "DELETE");
                location.reload();
              } catch (e: any) {
                setError(e.message);
              }
            }}
          >
            Удалить гостевой профиль
          </button>
        </p>
      )}
    </>
  );
}

export function AssessmentLab() {
  const { meta, user } = useApp();
  const bank = useData<any>(base + "/bank"),
    drafts = useData<any>(base + "/drafts");
  const [spec, setSpec] = useState("backend_python"),
    [topic, setTopic] = useState("Идемпотентность API и транзакции"),
    [busy, setBusy] = useState(false),
    [error, setError] = useState(""),
    [status, setStatus] = useState("");
  async function action(path: string, payload: any = {}) {
    setBusy(true);
    setError("");
    try {
      const r = await send(base + path, payload);
      drafts.reload();
      bank.reload();
      return r;
    } catch (e: any) {
      setError(e.message);
    } finally {
      setBusy(false);
    }
  }
  async function generate() {
    setBusy(true);
    setError("");
    setStatus("Готовим черновик для экспертной проверки…");
    try {
      const created = await send(base + "/drafts/generate", {
        specialization: spec,
        topic,
      });
      for (let i = 0; i < 300; i++) {
        const j = await api<any>("/intelligence/jobs/" + created.job_id);
        if (j.status === "done") {
          setStatus(
            "Черновик готов. Проверьте корректность условий и вариантов.",
          );
          drafts.reload();
          break;
        }
        if (j.status === "failed")
          throw new Error(j.error || "Не удалось подготовить вопрос");
        await new Promise((r) => setTimeout(r, 1000));
      }
    } catch (e: any) {
      setError(e.message);
    } finally {
      setBusy(false);
    }
  }
  if (bank.loading) return <Loading />;
  return (
    <>
      <PageHead
        eyebrow="ASSESSMENT LAB"
        title="Качество профессиональной оценки"
        description="Экспертная проверка вопросов, контролируемый пилот и наблюдение за решаемостью."
      />
      {(error || bank.error) && (
        <ErrorBox message={error || bank.error || ""} />
      )}
      <div className="cat-grades">
        {[
          ["Семейства вопросов", bank.data?.families],
          ["Уровневые формы", bank.data?.difficulty_forms],
          ["Экспресс-вопросы", bank.data?.express_questions],
        ].map(([label, v]) => (
          <section className="panel" key={label as string}>
            <span>{label}</span>
            <h2>{v || "—"}</h2>
          </section>
        ))}
      </div>
      <NeedPreview />
      <section className="panel">
        <h2>Новый вопрос</h2>
        <div className="cat-fields">
          <Field label="Специализация черновика">
            <select
              aria-label="Специализация черновика"
              value={spec}
              onChange={(e) => setSpec(e.target.value)}
            >
              {meta.specializations.map((s) => (
                <option key={s.id} value={s.id}>
                  {s.label}
                </option>
              ))}
            </select>
          </Field>
          <Field label="Рабочая тема">
            <input
              value={topic}
              onChange={(e) => setTopic(e.target.value)}
              maxLength={120}
            />
          </Field>
        </div>
        <button
          className="button primary"
          disabled={busy || topic.trim().length < 3 || !!bank.error}
          onClick={generate}
        >
          <Sparkles size={17} />
          {busy ? "Подготавливаем…" : "Подготовить черновик"}
        </button>
        {status && <p role="status">{status}</p>}
        <p className="muted">
          Автор и проверяющий — разные эксперты. Пилотные вопросы не меняют
          результат оценки. Активация требует данных калибровки и решения
          проверяющего.
        </p>
      </section>
      <div className="cat-drafts">
        {drafts.data?.items.map((d: any) => (
          <section className="panel" key={d.id}>
            <Badge tone={d.status === "active" ? "green" : "amber"}>
              {
                (
                  {
                    draft: "На проверке",
                    pilot: "Пилот",
                    active: "В ротации",
                    rejected: "Отклонён",
                    quarantined: "Выведен из ротации",
                  } as any
                )[d.status]
              }
            </Badge>
            <h3>{d.content.prompt}</h3>
            <ol type="A">
              {d.content.options.map((v: string, i: number) => (
                <li key={i}>
                  {v}
                  {d.content.correct === i && " · правильный ответ"}
                </li>
              ))}
            </ol>
            <p className="muted">{d.content.rationale}</p>
            {d.status === "draft" && d.author_id !== user.id && (
              <ExpertEditor
                draft={d}
                busy={busy}
                submit={(content, note) =>
                  void action(`/drafts/${d.id}/review`, {
                    decision: "pilot",
                    content,
                    note,
                  })
                }
              />
            )}
            {d.status === "draft" && d.author_id !== user.id && (
              <div className="cat-actions">
                <button
                  className="button primary"
                  disabled={busy}
                  onClick={() =>
                    action(`/drafts/${d.id}/review`, {
                      decision: "pilot",
                      note: "Условие, варианты и обоснование проверены экспертом. Допущено к пилотному сбору ответов.",
                    })
                  }
                >
                  Принять в пилот
                </button>
                <button
                  className="button secondary"
                  disabled={busy}
                  onClick={() =>
                    action(`/drafts/${d.id}/review`, {
                      decision: "rejected",
                      note: "Необходимо уточнить условие и критерий единственного правильного ответа.",
                    })
                  }
                >
                  Вернуть на доработку
                </button>
              </div>
            )}
            {d.status === "pilot" && d.reviewer_id === user.id && (
              <div className="cat-actions">
                <button
                  className="button secondary"
                  disabled={busy}
                  onClick={() => action(`/drafts/${d.id}/calibrate`)}
                >
                  Оценить параметры
                </button>
                <button
                  className="button primary"
                  disabled={busy || !d.calibration}
                  onClick={() => action(`/drafts/${d.id}/activate`)}
                >
                  Активировать после проверки
                </button>
              </div>
            )}
            {d.calibration && (
              <p className="muted">
                Ответов: {d.calibration.responses} · диапазонов уровня:{" "}
                {d.calibration.occupied_bins}
              </p>
            )}
          </section>
        ))}
      </div>
      <section className="panel">
        <h2>Наблюдение за вопросами</h2>
        <div className="cat-table">
          <table>
            <thead>
              <tr>
                <th>Семейство / форма</th>
                <th>Ответы</th>
                <th>Решаемость</th>
                <th>Ожидание</th>
                <th>Сдвиг</th>
              </tr>
            </thead>
            <tbody>
              {bank.data?.items.map((x: any) => (
                <tr key={x.item_id}>
                  <td>{x.item_id}</td>
                  <td>{x.responses}</td>
                  <td>{Math.round(x.correct_rate * 100)}%</td>
                  <td>{Math.round(x.expected_rate * 100)}%</td>
                  <td>{Number(x.drift_z).toFixed(2)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <p className="muted">
          При устойчивом росте решаемости относительно ожидаемой семейство
          выводится из новой ротации для проверки. Данные профилей и ответы
          конкретных людей здесь не публикуются.
        </p>
      </section>
    </>
  );
}
