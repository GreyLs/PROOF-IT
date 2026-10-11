import React, { useEffect, useRef, useState } from "react";
import { Compass, Play, ShieldCheck, Sparkles, TrendingUp } from "lucide-react";
import { api, send, money } from "./api";
import {
  useApp,
  useData,
  Loading,
  ErrorBox,
  PageHead,
  Field,
  Badge,
  Empty,
} from "./ui";
import "./intelligence.css";
import {TwinOverview, TwinComparison} from './twin-overview';
import {GraphExplorer} from './graph-explorer';
import {isGenericITResume} from './horizon-targets';

const prefix = "/intelligence";
function useJob() {
  const [result, setResult] = useState<any>(null),
    [busy, setBusy] = useState(false),
    [error, setError] = useState(""),
    [status, setStatus] = useState("");
  const revision = useRef(0);
  useEffect(
    () => () => {
      revision.current++;
    },
    [],
  );
  async function start(path: string, payload: any = {}) {
    const request = ++revision.current;
    setBusy(true);
    setError("");
    setStatus("Расчёт в очереди");
    try {
      const response = await send(prefix + path, payload);
      for (let step = 0; step < 360; step++) {
        if (revision.current !== request) return;
        const job = await api<any>(prefix + "/jobs/" + response.job_id);
        if (revision.current !== request) return;
        if (job.status === "done") {
          setResult(job.result);
          setStatus("Готово");
          return job.result;
        }
        if (job.status === "failed")
          throw new Error(job.error || "Не удалось завершить расчёт");
        setStatus(
          job.status === "running"
            ? "Рассчитываем ваш сценарий…"
            : "Ожидаем свободный расчётный слот…",
        );
        await new Promise((resolve) => setTimeout(resolve, 1000));
      }
      throw new Error(
        "Расчёт продолжается. Результат появится в журнале решений.",
      );
    } catch (e: any) {
      if (revision.current === request) setError(e.message);
    } finally {
      if (revision.current === request) setBusy(false);
    }
  }
  return { result, busy, error, status, start };
}

function Curve({ result }: { result: any }) {
  const width = 640,
    height = 215,
    pad = 34;
  const points = (curve: any[]) =>
    curve
      .map(
        (x) =>
          `${pad + (x.day / result.horizon_days) * (width - pad * 2)},${height - pad - x.probability * (height - pad * 2)}`,
      )
      .join(" ");
  return (
    <div className="horizon-curve">
      <svg
        viewBox={`0 0 ${width} ${height}`}
        role="img"
        aria-label="Вероятность завершения поиска по дням: текущий и выбранный сценарий"
      >
        {[0, 0.25, 0.5, 0.75, 1].map((x) => (
          <g key={x}>
            <line
              x1={pad}
              x2={width - pad}
              y1={height - pad - x * (height - 2 * pad)}
              y2={height - pad - x * (height - 2 * pad)}
              stroke="#e5e9f2"
            />
            <text
              x={4}
              y={height - pad - x * (height - 2 * pad) + 3}
              fontSize="10"
            >
              {x * 100}%
            </text>
          </g>
        ))}
        <polyline
          points={points(result.baseline.curve)}
          fill="none"
          stroke="#9ba6ba"
          strokeWidth="3"
        />
        <polyline
          points={points(result.scenario.curve)}
          fill="none"
          stroke="#513cf3"
          strokeWidth="4"
        />
        {[0, 0.25, 0.5, 0.75, 1].map((x) => (
          <text
            key={x}
            x={pad + x * (width - 2 * pad)}
            y={height - 8}
            textAnchor="middle"
            fontSize="10"
          >
            {Math.round(result.horizon_days * x)} дн.
          </text>
        ))}
      </svg>
      <div className="curve-legend">
        <span>● Текущие условия</span>
        <span>● Ваш сценарий</span>
      </div>
    </div>
  );
}

function Metric({
  label,
  value,
  note,
}: {
  label: string;
  value: React.ReactNode;
  note?: string;
}) {
  return (
    <div className="horizon-metric">
      <span>{label}</span>
      <strong>{value}</strong>
      {note && <small>{note}</small>}
    </div>
  );
}

export function HorizonPage() {
  const { user } = useApp();
  const employer = user.role === "employer";
  const entities = useData(
    employer ? "/vacancies?mine=true&limit=50" : "/resumes",
  );
  const targetItems = (entities.data?.items || []).filter(
    (item: any) => employer || !isGenericITResume(item),
  );
  const [entity, setEntity] = useState(""),
    [reward, setReward] = useState(0),
    [response, setResponse] = useState(3),
    [stages, setStages] = useState(3),
    [flex, setFlex] = useState(0.65),
    [proof, setProof] = useState(0),
    [focus, setFocus] = useState(0),
    [days, setDays] = useState(60);
  const job = useJob();
  const workFormat = String(
    targetItems.find((x: any) => x.id === entity)?.work_format || "",
  ).toLowerCase();
  const currentFlex = workFormat.includes("удал")
    ? 1
    : workFormat.includes("гибрид")
      ? 0.65
      : 0.25;
  useEffect(() => {
    if (entity) setFlex(currentFlex);
  }, [entity, currentFlex]);
  useEffect(() => {
    if (!targetItems.some((item: any) => item.id === entity))
      setEntity(targetItems[0]?.id || "");
  }, [entities.data, employer, entity]);
  if (entities.loading) return <Loading />;
  return (
    <>
      <PageHead
        eyebrow="PROOF-IT HORIZON"
        title={
          employer ? "Цифровой двойник найма" : "Цифровой двойник карьеры"
        }
        description="Данные → модель → сравнение условий → обоснованное действие. Один сценарий не меняет реальные данные."
      />
      {entities.error && <ErrorBox message={entities.error} />}
      <TwinOverview employer={employer} entity={targetItems.find((x:any)=>x.id===entity)}/>
      {!targetItems.length ? (
        <Empty
          title={
            employer ? "Создайте первую вакансию" : "Добавьте целевое резюме"
          }
          text="Horizon учитывает конкретную цель и текущий рынок платформы."
        />
      ) : (
        <div className="horizon-layout">
          <section className="horizon-controls">
            <h2>
              <Compass size={20} /> Настройте сценарий
            </h2>
            <Field label={employer ? "Вакансия" : "Целевое резюме"}>
              <select
                value={entity}
                onChange={(e) => setEntity(e.target.value)}
              >
                {targetItems.map((x: any) => (
                  <option key={x.id} value={x.id}>
                    {x.title || x.target_position}
                  </option>
                ))}
              </select>
            </Field>
            <Range
              label={
                employer ? "Увеличение вознаграждения" : "Изменение ожиданий"
              }
              value={reward}
              min={employer ? 0 : -20}
              max={employer ? 40 : 0}
              step={1}
              suffix="%"
              onChange={setReward}
            />
            <Range
              label="Ответ в течение"
              value={response}
              min={0.5}
              max={14}
              step={0.5}
              suffix="дн."
              onChange={setResponse}
            />
            <Range
              label="Этапы интервью"
              value={stages}
              min={1}
              max={7}
              step={1}
              onChange={setStages}
            />
            <Field label="Расширение формата работы">
              <select
                aria-label="Расширение формата работы"
                value={flex}
                onChange={(e) => setFlex(Number(e.target.value))}
              >
                <option value={0.25} disabled={currentFlex > 0.25}>
                  Офис
                </option>
                <option value={0.65} disabled={currentFlex > 0.65}>
                  Гибрид
                </option>
                <option value={1}>Удалённо / гибко</option>
              </select>
            </Field>
            {employer ? (
              <Range
                label="Убрать второстепенные требования"
                value={focus}
                min={0}
                max={3}
                step={1}
                onChange={setFocus}
              />
            ) : (
              <Range
                label="Усиление доказательств в сценарии"
                value={proof*100}
                min={0}
                max={35}
                step={5}
                suffix="п.п."
                onChange={value=>setProof(value/100)}
              />
            )}
            <Field label="Горизонт поиска">
              <select
                value={days}
                onChange={(e) => setDays(Number(e.target.value))}
              >
                <option value={30}>30 дней</option>
                <option value={60}>60 дней</option>
                <option value={90}>90 дней</option>
                <option value={180}>180 дней</option>
              </select>
            </Field>
            <button
              className="button primary"
              disabled={job.busy || !entity}
              onClick={() =>
                job.start("/horizon", {
                  entity_id: entity,
                  changes: {
                    reward_change_percent: reward,
                    response_days: response,
                    interview_stages: stages,
                    flexibility: flex,
                    proof_gain: proof,
                    skill_focus: focus,
                    horizon_days: days,
                  },
                  idempotency_key: crypto.randomUUID(),
                })
              }
            >
              <Sparkles size={17} />{" "}
              {job.busy ? "Рассчитываем…" : "Рассчитать сценарий"}
            </button>
            {job.busy && <p role="status">{job.status}</p>}{" "}
            {job.error && <ErrorBox message={job.error} />}
          </section>
          <section className="horizon-output">
            {job.result ? (
              <>
                {job.result.empty_market && (
                  <ErrorBox message="Сейчас нет доступного рынка для этой цели. Расширьте направление или дождитесь новых предложений." />
                )}
                <TwinComparison result={job.result}/>
                <Curve result={job.result} />
                <h3>Действия с ожидаемым эффектом</h3>
                <div className="horizon-actions">
                  {job.result.interventions.map((x: any) => (
                    <div key={x.action}>
                      <TrendingUp size={18} />
                      <span>{x.action}</span>
                      <strong>−{x.gain_days} дн.</strong>
                    </div>
                  ))}
                  {!job.result.interventions.length && (
                    <p>
                      Текущие условия уже конкурентны в рассмотренных сценариях.
                    </p>
                  )}
                </div>
                {job.result.bottlenecks.length > 0 && (
                  <div className="horizon-bottlenecks">
                    <h3>Узкие места</h3>
                    {job.result.bottlenecks.map((x: string) => (
                      <Badge key={x} tone="amber">
                        {x}
                      </Badge>
                    ))}
                  </div>
                )}
                <p className="horizon-note">
                  Результат описывает выбранный сценарий и его неопределённость.
                  Изменения условий применяются только по вашему решению.
                </p>
              </>
            ) : (
              <div className="horizon-placeholder">
                <Compass size={52} />
                <h2>Посмотрите на несколько шагов вперёд</h2>
                <p>
                  Ваши данные, текущие предложения и конкретные изменения
                  условий формируют персональный сценарий.
                </p>
                <div className="horizon-placeholder-grid">
                  <span>Диапазон сроков</span>
                  <span>Вероятность по дням</span>
                  <span>Эффект действий</span>
                </div>
              </div>
            )}
          </section>
        </div>
      )}
      <DecisionLedger revision={job.result?.decision_id} />
    </>
  );
}

function Range({
  label,
  value,
  min,
  max,
  step,
  suffix = "",
  onChange,
}: {
  label: string;
  value: number;
  min: number;
  max: number;
  step: number;
  suffix?: string;
  onChange: (n: number) => void;
}) {
  return (
    <label className="horizon-range">
      <span>
        {label}
        <strong>
          {Number(value.toFixed(2))} {suffix}
        </strong>
      </span>
      <input
        aria-label={label}
        type="range"
        min={min}
        max={max}
        step={step}
        value={value}
        onChange={(e) => onChange(Number(e.target.value))}
      />
    </label>
  );
}

export function ProofGraphPage() {
  const graph = useData(prefix + "/graph");
  const targets=useData('/resumes');
  const { notify } = useApp();
  if (graph.loading) return <Loading />;
  const data = graph.data;
  return (
    <>
      <PageHead
        eyebrow="PROOF GRAPH"
        title="Граф доказательств и карьерных направлений"
        description="Выберите направление и навык: увидите конкретные источники, достаточность опоры и что проверить следующим."
      />
      {graph.error && <ErrorBox message={graph.error} />}
      {data && (
        <>
          <GraphView graph={data} initialRole={targets.data?.items?.[0]?.specialization}/>
          <div className="proof-columns">
            <section>
              <h2>Ваши доказательства</h2>
              {(data.evidence_inventory||data.evidence).length ? (
                (data.evidence_inventory||data.evidence).map((e: any) => (
                  <div className="proof-evidence" key={e.id}>
                    <div>
                      <h3>{e.title}</h3>
                      <p>{e.skills.join(" · ")}</p>
                      <Badge
                        tone={e.status === "declared" ? "neutral" : "green"}
                      >
                        {e.status === "declared"
                          ? "Заявлено в резюме"
                          : "Подтверждающий артефакт"}
                      </Badge>
                      {e.disputed && <Badge tone="amber">Оспаривается</Badge>}
                      {e.hidden && <Badge>Скрыто · не участвует в графе</Badge>}
                    </div>
                    <div className="proof-control">
                      <label>
                        <input
                          type="checkbox"
                          checked={!e.hidden}
                          onChange={async (event) => {
                            try {
                              await send(
                                prefix +
                                  "/evidence/" +
                                  encodeURIComponent(e.id),
                                {
                                  hidden: !event.target.checked,
                                  disputed: e.disputed,
                                },
                                "PUT",
                              );
                              graph.reload();
                            } catch (error: any) {
                              notify(error.message, true);
                            }
                          }}
                        />{" "}
                        Показывать
                      </label>
                      <button
                        className="text-button"
                        onClick={async () => {
                          const reason = window.prompt(
                            "Почему вы оспариваете этот артефакт?",
                          );
                          if (!reason) return;
                          try {
                            await send(
                              prefix + "/evidence/" + encodeURIComponent(e.id),
                              { hidden: e.hidden, disputed: true, reason },
                              "PUT",
                            );
                            graph.reload();
                          } catch (error: any) {
                            notify(error.message, true);
                          }
                        }}
                      >
                        Оспорить
                      </button>
                    </div>
                  </div>
                ))
              ) : (
                <Empty
                  title="Создайте первый proof"
                  text="Добавьте резюме или выполните задачу в ProofLab."
                />
              )}
            </section>
            <section>
              {data.neural&&<div className="proof-evidence graph-neural-audit"><h3>Typed GraphSAGE</h3><p>{data.neural.architecture} · {data.neural.parameter_count} обучаемых параметров</p><p>Состояние: {data.neural.status}. Нейросеть ранжирует структурную связанность; подтверждённые навыки и грейд определяются только источниками доказательств.</p></div>}
              <details className="graph-method"><summary>Переносимые направления</summary>
              {data.opportunities.map((o: any) => (
                <div className="proof-role" key={o.id}>
                  <h3>{o.label}</h3>
                  <div className="proof-progress">
                    <i style={{ width: `${o.coverage * 100}%` }} />
                  </div>
                  <p>Покрытие навыков: {Math.round(o.coverage * 100)}%</p>
                  <small>Переносится: {o.transferable_skills.join(", ")}</small>
                  {o.missing_skills.length > 0 && (
                    <p>Доработать: {o.missing_skills.join(", ")}</p>
                  )}
                </div>
              ))}
              </details>
            </section>
          </div>
        </>
      )}
    </>
  );
}

export function GraphView({ graph,initialRole }: { graph: any;initialRole?:string }) {
  return <GraphExplorer graph={graph} initialRole={initialRole}/>;
}

export function CareerRoutePage() {
  const { meta, notify } = useApp();
  const prefs = useData(prefix + "/preferences");
  const job = useJob();
  const [value, setValue] = useState<any>({
    target_role: "",
    weekly_hours: 5,
    collaboration: "",
    pace: "",
    growth: "",
  });
  useEffect(() => {
    if (prefs.data) setValue({ ...value, ...prefs.data.preferences });
  }, [prefs.data]);
  function select(key: string, label: string, options: [string, string][]) {
    return (
      <Field label={label}>
        <select
          value={value[key]}
          onChange={(e) => setValue({ ...value, [key]: e.target.value })}
        >
          {options.map(([id, text]) => (
            <option key={id} value={id}>
              {text}
            </option>
          ))}
        </select>
      </Field>
    );
  }
  return (
    <>
      <PageHead
        eyebrow="CAREER NAVIGATION"
        title="Маршрут 14 / 30 / 90"
        description="Соберите реалистичный маршрут из переносимых навыков, профессиональных доказательств и добровольных рабочих предпочтений."
      />
      <div className="horizon-layout">
        <section className="horizon-controls">
          <h2>Что важно вам</h2>
          {select("target_role", "Целевое направление", [
            ["", "Предложить по моим навыкам"],
            ...meta.specializations.map(
              (x) => [x.id, x.label] as [string, string],
            ),
          ])}
          {select("collaboration", "Совместная работа", [
            ["", "Не указывать"],
            ["team", "Команда и обратная связь"],
            ["independent", "Автономия"],
          ])}
          {select("pace", "Предпочтительный темп", [
            ["", "Не указывать"],
            ["stable", "Предсказуемый"],
            ["dynamic", "Разнообразные задачи"],
          ])}
          {select("growth", "Следующий рост", [
            ["", "Не указывать"],
            ["expert", "Углубить экспертизу"],
            ["leadership", "Координировать команду"],
            ["explore", "Попробовать новое"],
          ])}
          <Range
            label="Часов в неделю"
            min={2}
            max={20}
            step={1}
            value={value.weekly_hours}
            onChange={(n) => setValue({ ...value, weekly_hours: n })}
          />
          <p className="horizon-note">
            Предпочтения видны только вам и помогают составить удобный план. Они
            не изменяют рейтинг и не передаются работодателям.
          </p>
          <button
            className="button primary"
            disabled={job.busy}
            onClick={async () => {
              try {
                await send(prefix + "/preferences", value, "PUT");
                await job.start("/career-route");
              } catch (error: any) {
                notify(error.message, true);
              }
            }}
          >
            <Compass size={16} />{" "}
            {job.busy ? job.status : "Создать мой маршрут"}
          </button>
          {job.error && <ErrorBox message={job.error} />}
        </section>
        <section className="horizon-output">
          {job.result ? (
            <>
              <h2>
                {job.result.target?.label || "Первый профессиональный проект"}
              </h2>
              {job.result.working_preferences.map((x: string) => (
                <Badge key={x}>{x}</Badge>
              ))}
              {job.result.effects && (
                <div className="horizon-metrics">
                  <Metric
                    label="Поиск при текущих условиях"
                    value={
                      job.result.effects.baseline.median_days === null
                        ? "Не определяется"
                        : `${job.result.effects.baseline.median_days} дн.`
                    }
                  />
                  <Metric
                    label="После подтверждения навыков"
                    value={
                      job.result.effects.scenario.median_days === null
                        ? "Не определяется"
                        : `${job.result.effects.scenario.median_days} дн.`
                    }
                    note="Сценарий результата практики"
                  />
                  <Metric
                    label="Ожидаемый эффект"
                    value={`${job.result.effects.gain_days} дн.`}
                    note="Эффект зависит от выполнения плана и доступного рынка"
                  />
                </div>
              )}
              <div className="career-timeline">
                {job.result.milestones.map((x: any) => (
                  <article key={x.day}>
                    <strong>
                      {x.day}
                      <small>дней</small>
                    </strong>
                    <div>
                      <h3>{x.title}</h3>
                      <ul>
                        {x.actions.map((a: string) => (
                          <li key={a}>{a}</li>
                        ))}
                      </ul>
                      <p>
                        <ShieldCheck size={16} /> {x.deliverable}
                      </p>
                    </div>
                  </article>
                ))}
              </div>
              <div className="career-question">{job.result.next_question}</div>
            </>
          ) : (
            <div className="horizon-placeholder">
              <Compass size={48} />
              <h2>Один опыт — несколько путей</h2>
              <p>
                План помогает проверить направление небольшим действием, собрать
                артефакт и выйти к подходящим предложениям.
              </p>
            </div>
          )}
        </section>
      </div>
    </>
  );
}

export function StrategyPage() {
  const job = useJob();
  const [budget, setBudget] = useState(0);
  return (
    <>
      <PageHead
        eyebrow="HIRING STRATEGY STUDIO"
        title="Портфель найма"
        description="Распределите внимание и дополнительный бюджет между активными вакансиями. Посмотрите, какие изменения дают наибольший ожидаемый эффект."
      />
      <section className="strategy-settings">
        <Field label="Дополнительный месячный бюджет, ₽">
          <input
            aria-label="Дополнительный бюджет"
            type="number"
            min={0}
            max={100000000}
            value={budget}
            onChange={(e) => setBudget(Number(e.target.value))}
          />
        </Field>
        <button
          className="button primary"
          disabled={job.busy}
          onClick={() => job.start("/strategy", { extra_budget: budget })}
        >
          {job.busy ? job.status : "Построить план найма"}
          <TrendingUp size={17} />
        </button>
      </section>
      {job.error && <ErrorBox message={job.error} />}
      {job.result && (
        <>
          <div className="horizon-metrics">
            <Metric
              label="Активные вакансии"
              value={job.result.vacancies.length}
            />
            <Metric
              label="Распределено"
              value={money(job.result.allocated_budget)}
            />
            <Metric label="Резерв" value={money(job.result.remaining_budget)} />
          </div>
          <div className="strategy-table">
            <table>
              <thead>
                <tr>
                  <th>Вакансия</th>
                  <th>Медиана срока</th>
                  <th>Быстрый процесс</th>
                  <th>План</th>
                </tr>
              </thead>
              <tbody>
                {job.result.vacancies.map((x: any) => (
                  <tr key={x.vacancy_id}>
                    <td>
                      <strong>{x.title}</strong>
                      {x.empty_market && <p>Расширить рынок поиска</p>}
                    </td>
                    <td>
                      {x.median_days ?? "Нет рынка"}
                      {x.median_days !== null && " дн."}
                    </td>
                    <td>{x.process_days ?? "—"} дн.</td>
                    <td>
                      {x.allocated ? (
                        <>
                          <Badge tone="green">
                            Инвестировать {money(x.extra_monthly_cost)}
                          </Badge>
                          <p>Ожидаемый срок {x.reward_days} дн.</p>
                        </>
                      ) : (
                        "Ускорить обратную связь и убрать повторные этапы"
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <div className="horizon-actions">
            {job.result.recommendations.map((x: string) => (
              <div key={x}>
                <ShieldCheck size={18} />
                <span>{x}</span>
              </div>
            ))}
          </div>
        </>
      )}
      <DecisionLedger />
    </>
  );
}

export function ArenaPage() {
  const list = useData(prefix + "/arena"),
    job = useJob();
  const { notify } = useApp();
  const [active, setActive] = useState<any>(null),
    [code, setCode] = useState(""),
    [run, setRun] = useState<any>(null),
    [answer, setAnswer] = useState(""),
    [busy, setBusy] = useState(false);
  const kinds = [
    ["python", "Python", "Проверяемое исполнение"],
    ["sql", "SQL", "Запросы и крайние случаи"],
    ["typescript", "TypeScript", "Код и автотесты"],
    ["incident", "Инцидент", "Диагностика и восстановление"],
    ["design", "Системный дизайн", "Архитектура и риски"],
    ["review", "PR review", "Надёжность и права"],
    ["adaptive", "Адаптивная практика", "Вопросы по силе ответа"],
  ];
  const text =
    active && ["incident", "design", "review"].includes(active.contract.kind);
  const execute = async (path: string, payload: any) => {
    setBusy(true);
    try {
      const result = await send(prefix + path, payload);
      return result;
    } catch (e: any) {
      notify(e.message, true);
    } finally {
      setBusy(false);
    }
  };
  return (
    <>
      <PageHead
        eyebrow="PROOFLAB"
        title="Покажите, как вы решаете"
        description="Практические задачи, адаптивные вопросы и инженерные ситуации. Результаты формируют ваш граф доказательств; общий грейд сохраняется."
      />
      <div className="arena-formats">
        {kinds.map(([kind, label, description]) => (
          <button
            key={kind}
            disabled={busy || job.busy}
            onClick={async () => {
              const r = await execute("/arena", { kind });
              if (r) {
                setActive(r);
                setCode(r.contract.starter_code || "");
                setRun(null);
                setAnswer("");
              }
            }}
          >
            <Play size={18} />
            <strong>{label}</strong>
            <span>{description}</span>
          </button>
        ))}
      </div>
      {active && (
        <section className="arena-workspace">
          <div className="arena-brief">
            <Badge tone="violet">
              {kinds.find((x) => x[0] === active.contract.kind)?.[1]}
            </Badge>
            <h2>{active.contract.title}</h2>
            <p>{active.contract.prompt}</p>
            {active.contract.public_tests?.length > 0 && (
              <>
                <h3>Открытые примеры</h3>
                <pre>
                  {JSON.stringify(active.contract.public_tests, null, 2)}
                </pre>
              </>
            )}
            {active.contract.question && (
              <>
                <h3>{active.contract.question.skill}</h3>
                <p>{active.contract.question.prompt}</p>
                <p>
                  Вопрос {active.contract.answered + 1} / до{" "}
                  {active.contract.max_questions}
                </p>
              </>
            )}
          </div>
          <div className="arena-editor">
            {active.contract.kind === "adaptive" ? (
              <>
                <Field label="Числовой ответ">
                  <input
                    aria-label="Числовой ответ"
                    inputMode="decimal"
                    value={answer}
                    onChange={(e) => setAnswer(e.target.value)}
                    disabled={active.status === "completed"}
                  />
                </Field>
                <button
                  className="button primary"
                  disabled={
                    busy || active.status === "completed" || !answer.trim()
                  }
                  onClick={async () => {
                    const result = await execute(
                      "/arena/" + active.id + "/answer",
                      {
                        question_id: active.contract.question.id,
                        answer: Number(answer.replace(",", ".")),
                        revision: active.revision,
                      },
                    );
                    if (result) {
                      setActive(result);
                      setAnswer("");
                      if (result.result) {
                        setRun(result.result);
                        list.reload();
                      }
                    }
                  }}
                >
                  Ответить
                </button>
              </>
            ) : (
              <>
                <label htmlFor="arena-code">
                  {text ? "Ваш разбор" : "Ваше решение"}
                </label>
                <textarea
                  id="arena-code"
                  spellCheck={false}
                  value={code}
                  onChange={(e) => setCode(e.target.value)}
                  disabled={active.status === "completed" || job.busy}
                  placeholder={
                    text
                      ? "Опишите решение, критерии проверки и риски…"
                      : "Напишите решение…"
                  }
                />
                <div className="arena-buttons">
                  {!text && (
                    <button
                      className="button"
                      disabled={
                        busy || job.busy || active.status === "completed"
                      }
                      onClick={async () => {
                        const r = await execute(
                          "/arena/" + active.id + "/run",
                          { code },
                        );
                        if (r) setRun(r);
                      }}
                    >
                      Запустить
                    </button>
                  )}
                  <button
                    className="button primary"
                    disabled={
                      busy ||
                      job.busy ||
                      active.status === "completed" ||
                      code.length < 10
                    }
                    onClick={async () => {
                      const r = await job.start(
                        "/arena/" + active.id + "/submit",
                        { code },
                      );
                      if (r) {
                        setRun(r);
                        setActive({ ...active, status: "completed" });
                        list.reload();
                      }
                    }}
                  >
                    {job.busy ? job.status : "Готово — получить review"}
                  </button>
                </div>
              </>
            )}
            {job.error && <ErrorBox message={job.error} />}
            {run && (
              <div className="arena-verdict">
                <h3>
                  {run.score !== undefined
                    ? `Результат: ${run.score}/100`
                    : `Открытые тесты: ${run.passed}/${run.total}`}
                </h3>
                {run.error && <p>Выполнение остановлено: {run.error}</p>}
                {run.hidden_total !== undefined && (
                  <p>
                    Скрытые тесты: {run.hidden_passed}/{run.hidden_total}
                  </p>
                )}
                <p>{run.review?.feedback || run.feedback}</p>
                {run.integrity?.review_recommended && (
                  <p className="muted">
                    Есть структурное сходство с другим решением. Это сигнал для
                    обсуждения авторства, не обвинение и не автоматическое
                    снижение оценки.
                  </p>
                )}
                {run.standard_error !== undefined && (
                  <p>
                    Оценка практики: θ {run.theta}, стандартная ошибка{" "}
                    {run.standard_error}. Грейд не изменён.
                  </p>
                )}
                {(run.review?.improvements || run.improvements || []).map(
                  (x: string) => (
                    <p key={x}>→ {x}</p>
                  ),
                )}
              </div>
            )}
          </div>
        </section>
      )}
      <h2>История практики</h2>
      {list.error && <ErrorBox message={list.error} />}
      <div className="arena-history">
        {list.data?.items?.map((x: any) => (
          <button
            key={x.id}
            onClick={() => {
              setActive(x);
              setCode(x.contract.starter_code || "");
              setRun(x.result);
            }}
          >
            <strong>{x.contract.title}</strong>
            <span>
              {x.status === "completed"
                ? `Завершено · ${x.result?.score ?? "—"}/100`
                : "Продолжить"}
            </span>
          </button>
        ))}
      </div>
    </>
  );
}

export function CandidateProof({ candidateId }: { candidateId: string }) {
  const graph = useData(
    prefix + "/graph/candidate/" + encodeURIComponent(candidateId),
  );
  return (
    <section>
      <h3>Профессиональные доказательства</h3>
      {graph.loading ? (
        <Loading />
      ) : graph.error ? (
        <p>Граф пока недоступен</p>
      ) : (
        graph.data && <GraphView graph={graph.data} />
      )}
    </section>
  );
}

function DecisionLedger({ revision }: { revision?: string } = {}) {
  const ledger = useData(prefix + "/decisions", [revision]),
    { notify } = useApp();
  const quality = useData(prefix + "/quality");
  return (
    <section className="decision-ledger">
      <h2>
        <ShieldCheck size={19} /> Журнал решений
      </h2>
      <p>
        Расчёты сохраняются с версией правил и основанием. Вы можете оспорить
        результат.
      </p>
      {ledger.data?.items?.slice(0, 6).map((d: any) => (
        <details key={d.id}>
          <summary>
            {(
              {
                horizon: "Сценарий Horizon",
                strategy: "Портфель найма",
                career_route: "Карьерный маршрут",
                arena: "Ревью практики",
                match: "Совместимость",
                adaptive_practice: "Адаптивная практика",
              } as any
            )[d.kind] || d.kind}{" "}
            · {new Date(d.created_at).toLocaleDateString("ru")}{" "}
            {d.status === "disputed" && "· Оспаривается"}
          </summary>
          <p>Версия: {d.version}</p>
          <p>Идентификатор основания: {d.input_hash.slice(0, 16)}</p>
          {d.kind === "horizon" && (
            <button
              className="text-button"
              onClick={async () => {
                const value = window.prompt(
                  "За сколько дней фактически завершился поиск? Результат виден только вам.",
                );
                if (!value) return;
                try {
                  await send(prefix + "/outcomes", {
                    decision_id: d.id,
                    actual_days: Number(value.replace(",", ".")),
                  });
                  quality.reload();
                  notify("Фактический срок записан");
                } catch (e: any) {
                  notify(e.message, true);
                }
              }}
            >
              Записать фактический срок
            </button>
          )}
          <button
            className="text-button"
            disabled={d.status === "disputed"}
            onClick={async () => {
              const reason = window.prompt(
                "Что в результате требует проверки? Не менее 10 символов.",
              );
              if (!reason) return;
              try {
                await send(prefix + "/decisions/" + d.id + "/dispute", {
                  reason,
                });
                ledger.reload();
              } catch (error: any) {
                notify(error.message, true);
              }
            }}
          >
            Передать на разбор
          </button>
        </details>
      ))}
      {quality.data?.forecast_accuracy?.outcomes > 0 && (
        <p>
          Записано исходов: {quality.data.forecast_accuracy.outcomes}. Средняя
          абсолютная ошибка срока:{" "}
          {quality.data.forecast_accuracy.mae_days?.toFixed(1) ?? "—"} дн.
        </p>
      )}
      {ledger.error && <ErrorBox message={ledger.error} />}
    </section>
  );
}

export function MatchExplanation({
  resumeId,
  vacancyId,
}: {
  resumeId: string;
  vacancyId: string;
}) {
  const [result, setResult] = useState<any>(null),
    [error, setError] = useState(""),
    [busy, setBusy] = useState(false);
  return (
    <section className="mutual-match">
      <button
        type="button"
        className="button"
        disabled={!resumeId || busy}
        onClick={async () => {
          setBusy(true);
          setError("");
          try {
            const response = await send(prefix + "/match", {
              resume_id: resumeId,
              vacancy_id: vacancyId,
            });
            setResult(response.explanation);
          } catch (e: any) {
            setError(e.message);
          } finally {
            setBusy(false);
          }
        }}
      >
        Объяснить совместимость обеих сторон
      </button>
      {error && <ErrorBox message={error} />}
      {result && (
        <div className="horizon-metrics">
          <Metric
            label="Покрытие требуемых навыков"
            value={`${Math.round(result.skill_coverage * 100)}%`}
            note={`Уточнить: ${result.missing_skills.join(", ") || "нет пробелов по стеку"}`}
          />
          <Metric
            label="Работодателю"
            value={result.same_direction ? "В одной роли" : "Другой фокус"}
            note={result.employer_view.next_step}
          />
          <Metric
            label="Кандидату"
            value={
              result.salary_compatible ? "Условия подходят" : "Обсудить вилку"
            }
            note={result.candidate_view.conditions}
          />
        </div>
      )}
    </section>
  );
}
