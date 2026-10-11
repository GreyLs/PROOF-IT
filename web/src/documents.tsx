import React, { useState, useEffect, useRef } from "react";
import {
  Upload,
  FileScan,
  FileText,
  ArrowUpRight,
  Check,
  Download,
  RefreshCw,
  ShieldCheck,
  Clock3,
  AlertCircle,
  ArrowRight,
  Quote,
  Layers3,
  Activity,
  Database,
  CheckCircle2,
  ExternalLink,
  Trash2,
} from "lucide-react";
import { api, send, DocumentRecord, date, grade } from "./api";
import {
  useApp,
  useData,
  PageHead,
  Loading,
  ErrorBox,
  Empty,
  Badge,
  Status,
  Modal,
  Field,
  Stat,
} from "./ui";
import { VacancyEditor } from "./employer";
import { EmploymentReport, EmploymentStatus } from "./employment";

export function DocumentsPage() {
  const { user, notify, navigate } = useApp();
  const result = useData<{ items: DocumentRecord[] }>("/documents");
  const [kind, setKind] = useState(
      user.role === "candidate" ? "resume" : "vacancy",
    ),
    [busy, setBusy] = useState(false),
    [error, setError] = useState(""),
    [selected, setSelected] = useState<DocumentRecord | null>(null),
    [drag, setDrag] = useState(false);
  const file = useRef<HTMLInputElement>(null);
  useEffect(() => {
    const timer = setInterval(() => {
      if (
        result.data?.items.some((x) =>
          ["queued", "processing"].includes(x.status),
        )
      )
        result.reload();
    }, 2500);
    return () => clearInterval(timer);
  }, [result.data]);
  const upload = async (files: FileList | File[]) => {
    setBusy(true);
    setError("");
    try {
      for (const f of Array.from(files)) {
        if (f.size > 20 * 1024 * 1024)
          throw new Error(`${f.name}: размер больше 20 МБ`);
        const data = new FormData();
        data.append("file", f);
        const r = await api("/documents?kind=" + kind, {
          method: "POST",
          body: data,
        });
        notify(
          r.duplicate
            ? "Этот документ уже загружен. Открыт существующий результат."
            : `Документ «${f.name}» добавлен в обработку.`,
        );
      }
      result.reload();
    } catch (e) {
      setError((e as Error).message);
      result.reload();
    } finally {
      setBusy(false);
      if (file.current) file.current.value = "";
    }
  };
  return (
    <>
      <PageHead
        eyebrow="ОТ ДОКУМЕНТА — К СТРУКТУРИРОВАННОМУ ПРОФИЛЮ"
        title="Документы без ручной рутины."
        description="PDF с текстом, сканы и изображения. Извлечём сведения и покажем их источник."
      />
      {user.role==="candidate"&&<EmploymentStatus/>}
      <div className="document-layout">
        <section>
          <div
            className={"dropzone " + (drag ? "drag" : "")}
            onDragOver={(e) => {
              e.preventDefault();
              setDrag(true);
            }}
            onDragLeave={() => setDrag(false)}
            onDrop={(e) => {
              e.preventDefault();
              setDrag(false);
              if (!busy) upload(e.dataTransfer.files);
            }}
          >
            <div className="upload-symbol">
              <FileScan size={35} />
              <span>
                <Upload size={15} />
              </span>
            </div>
            <h2>Перетащите документы сюда</h2>
            <p>или выберите файлы на устройстве</p>
            {user.role==="candidate"&&<><div className="segmented"><button className={kind==="resume"?"selected":""} onClick={()=>setKind("resume")}>Резюме</button><button className={kind==="employment"?"selected":""} onClick={()=>setKind("employment")}>Выписка из трудовой</button></div>{kind==="employment"&&<p>Добровольная сверка должностей и дат с сохранённым резюме. При выявленном расхождении показы приостанавливаются до исправления. Можно загрузить PDF или читаемый скан.</p>}</>}
            {user.role === "employer" && (
              <div className="segmented">
                <button
                  className={kind === "vacancy" ? "selected" : ""}
                  onClick={() => setKind("vacancy")}
                >
                  Вакансия
                </button>
                <button
                  className={kind === "resume" ? "selected" : ""}
                  onClick={() => setKind("resume")}
                >
                  Резюме кандидата
                </button>
              </div>
            )}
            <input
              ref={file}
              type="file"
              multiple
              accept="application/pdf,image/png,image/jpeg"
              hidden
              onChange={(e) => {
                if (e.target.files) upload(e.target.files);
              }}
            />
            <button
              className="button primary"
              disabled={busy}
              onClick={() => file.current?.click()}
            >
              <Upload size={18} />
              {busy ? "Загружаем…" : "Выбрать документы"}
            </button>
            <small>
              PDF, PNG, JPEG · до 20 МБ · до 40 страниц · до 5 файлов в очереди
            </small>
          </div>
          {error && <ErrorBox message={error} />}
          <div className="section-heading document-list-head">
            <h2>Ваши документы</h2>
            <button
              className="icon-button"
              aria-label="Обновить документы"
              onClick={result.reload}
            >
              <RefreshCw size={18} />
            </button>
          </div>
          {result.loading && !result.data ? (
            <Loading />
          ) : result.error ? (
            <ErrorBox message={result.error} />
          ) : !result.data?.items.length ? (
            <Empty
              title="Всё начинается с документа"
              text="Загрузите PDF или изображение. Здесь появятся статус обработки и проверяемый черновик."
            />
          ) : (
            <div className="document-list">
              {result.data.items.map((d) => (
                <article className="document-item" key={d.id}>
                  <div className="document-icon">
                    <FileText size={25} />
                  </div>
                  <div className="document-info">
                    <strong>{d.filename}</strong>
                    <small>
                      {d.kind === "vacancy"
                        ? "Вакансия"
                        : d.kind === "employment" ? "Выписка из трудовой" : d.kind === "profile_export"
                          ? "Ваш PDF-профиль"
                          : "Резюме"}{" "}
                      · {date(d.created_at)}
                    </small>
                    {["queued", "processing"].includes(d.status) && (
                      <div className="progress-track">
                        <div style={{ width: `${Math.max(5, d.progress)}%` }} />
                      </div>
                    )}
                    {d.error && <small className="error-text">{d.error}</small>}
                  </div>
                  <Status value={d.status} />
                  {d.kind === "profile_export" && d.status === "completed" ? (
                    <a
                      className="button secondary"
                      href={"/api/documents/" + d.id + "/file"}
                      target="_blank"
                      rel="noreferrer"
                    >
                      <Download size={17} />
                      Открыть PDF
                    </a>
                  ) : ["review", "completed"].includes(d.status) ? (
                    <button
                      className="button secondary"
                      onClick={() => setSelected(d)}
                    >
                      Проверить
                      <ArrowUpRight size={16} />
                    </button>
                  ) : d.status === "failed" ? (
                    <button
                      className="button secondary"
                      onClick={async () => {
                        try {
                          await send("/documents/" + d.id + "/retry");
                          result.reload();
                        } catch (e) {
                          notify((e as Error).message, true);
                        }
                      }}
                    >
                      <RefreshCw size={16} />
                      Повторить
                    </button>
                  ) : null}
                  {d.status !== "processing" && <button className="icon-button" aria-label={"Удалить документ " + d.filename} title="Удалить документ" onClick={async () => {
                    if (!window.confirm("Удалить документ и результаты его распознавания?")) return;
                    try { await api("/documents/" + d.id, {method:"DELETE"}); result.reload(); notify("Документ удалён. Файл будет очищен из хранилища в течение минуты."); }
                    catch (error) { notify((error as Error).message, true); }
                  }}><Trash2 size={17}/></button>}
                </article>
              ))}
            </div>
          )}
        </section>
        <aside>
          <section className="panel">
            <div className="eyebrow">КАК ЭТО РАБОТАЕТ</div>
            <h2>
              Источник рядом
              <br />с каждым фактом.
            </h2>
            <div className="journey compact">
              <div>
                <span>01</span>
                <article>
                  <h3>Прочитаем документ</h3>
                  <p>
                    Текстовый PDF или распознавание скана на русском и
                    английском.
                  </p>
                </article>
              </div>
              <div>
                <span>02</span>
                <article>
                  <h3>Соберём черновик</h3>
                  <p>
                    Стек, опыт, роль и условия. Необычные поля и исходный текст
                    сохранятся.
                  </p>
                </article>
              </div>
              <div>
                <span>03</span>
                <article>
                  <h3>Вы проверите результат</h3>
                  <p>
                    Исправьте неточности перед переносом в профиль или вакансию.
                  </p>
                </article>
              </div>
            </div>
          </section>
          <div className="notice vertical">
            <ShieldCheck size={22} />
            <strong>Резюме — начало пути</strong>
            <p>
              Распознанный грейд остаётся заявленным. Подтверждённая категория
              появляется после разбора проекта и трёх профессиональных кейсов.
            </p>
          </div>
        </aside>
      </div>
      {selected?.kind==="employment"?<Modal title="Сверка выписки с резюме" onClose={()=>setSelected(null)}><EmploymentReport check={selected.result?.employment_check} blocked={selected.result?.employment_check?.status==="mismatch"}/><p>Это результат сверки на момент обработки документа. Текущий статус показан в профиле.</p><a className="button secondary" href={"/api/documents/"+selected.id+"/file"}>Скачать свой документ</a><p className="muted">Для исправления измените резюме либо загрузите актуальную выписку. Удаление файла само по себе не снимает выявленное расхождение.</p></Modal>:selected && (
        <DocumentReview
          document={selected}
          onClose={() => setSelected(null)}
          onSaved={() => {
            setSelected(null);
            result.reload();
          }}
        />
      )}
    </>
  );
}
function DocumentReview({
  document: d,
  onClose,
  onSaved,
}: {
  document: DocumentRecord;
  onClose: () => void;
  onSaved: () => void;
}) {
  const { user, meta, notify, navigate } = useApp();
  const profiles = d.result?.profiles || [];
  const [profileIndex, setProfileIndex] = useState(d.result?.reviewed_profile_index ?? -1);
  const [drafts, setDrafts] = useState<Record<number, Record<string, any>>>({});
  const active = profiles.length ? profiles[profileIndex] : d.result;
  const selectionRequired = profiles.length > 0 && profileIndex < 0;
  const [fields, setFields] = useState<Record<string, any>>(
      active?.reviewed_fields || active?.fields || {},
    ),
    [tab, setTab] = useState("fields"),
    [busy, setBusy] = useState(false),
    [error, setError] = useState(""),
    [vacancy, setVacancy] = useState(false);
  const change = (key: string, value: any) => {
    const updated = {...fields, [key]:value};
    setFields(updated);
    if (profiles.length) setDrafts(prev => ({...prev, [profileIndex]:updated}));
  };
  const save = async () => {
    if (selectionRequired) throw new Error("Выберите резюме из файла");
    await send("/documents/" + d.id, { fields, ...(profiles.length ? {profile_index:profileIndex} : {}) }, "PUT");
  };
  const apply = async () => {
    setBusy(true);
    setError("");
    try {
      await save();
      if (d.kind === "vacancy") {
        setVacancy(true);
        return;
      }
      if (user.role === "candidate") {
        const { profile: p } = await api("/profile");
        const updated = {
          ...p,
          full_name: fields.full_name || p.full_name,
          email: fields.email || p.email,
          phone: fields.phone || p.phone,
          specialization: fields.specialization || p.specialization,
          declared_grade: fields.grade || p.declared_grade,
          experience_years: fields.experience_years ?? p.experience_years,
          skills: fields.skills?.length ? fields.skills : p.skills,
          soft_skills: fields.soft_skills?.length
            ? fields.soft_skills
            : p.soft_skills,
          about: fields.description || p.about,
          expected_salary: fields.salary_from || p.expected_salary,
          work_format: fields.work_format || p.work_format,
        };
        await send("/profile", updated, "PUT");
        notify(
          "Черновик перенесён в ваш профиль. Проверьте настройки публикации.",
        );
        onSaved();
        navigate("profile");
      } else {
        notify(
          "Разбор резюме сохранён. Для участия в подборе кандидат должен зарегистрироваться и пройти тест.",
        );
        onSaved();
      }
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  };
  const evidence = (key: string) => {
    const p = active?.provenance?.[key];
    return p ? (
      <div className="field-evidence">
        <Quote size={12} />
        <span>
          {p.page ? `стр. ${p.page} · ` : ""}
          {p.quote}
        </span>
      </div>
    ) : null;
  };
  return (
    <>
      {!vacancy && (
        <Modal
          title="Проверьте распознанные сведения"
          subtitle={d.filename}
          wide
          onClose={onClose}
        >
          <div className="review-tabs">
            <div className="tabs">
              <button
                className={tab === "fields" ? "active" : ""}
                onClick={() => setTab("fields")}
              >
                Поля и источники
              </button>
              <button
                className={tab === "text" ? "active" : ""}
                onClick={() => setTab("text")}
              >
                Исходный текст
              </button>
              <button
                className={tab === "extra" ? "active" : ""}
                onClick={() => setTab("extra")}
              >
                Другие сведения
              </button>
            </div>
            <a
              className="button text"
              target="_blank"
              rel="noreferrer"
              href={"/api/documents/" + d.id + "/file"}
            >
              Оригинал
              <ExternalLink size={16} />
            </a>
          </div>
          {profiles.length > 0 && <Field label="Резюме в файле" hint="Выберите одно резюме: его поля, источники и исправления сохраняются отдельно.">
            <select value={profileIndex} onChange={event => {
              const index=Number(event.target.value);
              setProfileIndex(index);
              setFields(drafts[index] || profiles[index]?.reviewed_fields || profiles[index]?.fields || {});
              setError("");
            }}>
              <option value={-1}>Выберите резюме</option>
              {profiles.map((profile,index) => <option value={index} key={index}>{String(profile.fields.full_name || `Резюме ${index+1}`)} · стр. {profile.page_from}{profile.page_to!==profile.page_from ? `–${profile.page_to}` : ""}</option>)}
            </select>
          </Field>}
          {[...(d.result?.warnings || []), ...(profiles.length ? active?.warnings || [] : [])].map((w, i) => (
            <div className="review-warning" key={i}>
              <AlertCircle size={15} />
              <span>{w}</span>
            </div>
          ))}
          {selectionRequired && tab !== "text" ? <Empty title="В файле несколько резюме" text="Выберите нужное выше, чтобы проверить сведения и перенести их в профиль."/> : tab === "fields" ? (
            <div className="review-fields">
              <div className="form-grid">
                {(d.kind === "resume"
                  ? [
                      ["full_name", "ФИО"],
                      ["email", "Email"],
                      ["phone", "Телефон"],
                      ["experience_years", "Опыт, лет"],
                    ]
                  : [
                      ["title", "Название вакансии"],
                      ["work_format", "Формат работы"],
                    ]
                ).map(([key, label]) => (
                  <div key={key}>
                    <Field label={label}>
                      <input
                        value={fields[key] ?? ""}
                        onChange={(e) =>
                          change(
                            key,
                            key === "experience_years"
                              ? Number(e.target.value)
                              : e.target.value,
                          )
                        }
                        placeholder="Не найдено — можно заполнить"
                      />
                    </Field>
                    {evidence(key)}
                  </div>
                ))}
                <div>
                  <Field label="Специализация">
                    <select
                      value={fields.specialization || ""}
                      onChange={(e) => change("specialization", e.target.value)}
                    >
                      <option value="">Выберите направление</option>
                      {meta.specializations.map((s) => (
                        <option key={s.id} value={s.id}>
                          {s.label}
                        </option>
                      ))}
                    </select>
                  </Field>
                  {evidence("specialization")}
                </div>
                <div>
                  <Field label="Заявленный грейд">
                    <select
                      value={fields.grade || ""}
                      onChange={(e) => change("grade", e.target.value)}
                    >
                      <option value="">Не указан</option>
                      {meta.grades.map((g) => (
                        <option value={g} key={g}>
                          {grade(g)}
                        </option>
                      ))}
                    </select>
                  </Field>
                  {evidence("grade")}
                </div>
                {[
                  ["salary_from", "Зарплата от, ₽"],
                  ["salary_to", "Зарплата до, ₽"],
                ].map(([key, label]) => (
                  <div key={key}>
                    <Field label={label}>
                      <input
                        type="number"
                        min={0}
                        value={fields[key] ?? ""}
                        onChange={(e) =>
                          change(
                            key,
                            e.target.value ? Number(e.target.value) : null,
                          )
                        }
                        placeholder="Не указана"
                      />
                    </Field>
                    {evidence(key)}
                  </div>
                ))}
              </div>
              <Field label="Стек, через запятую">
                <input
                  value={(Array.isArray(fields.skills)
                    ? fields.skills
                    : []
                  ).join(", ")}
                  onChange={(e) =>
                    change(
                      "skills",
                      e.target.value.split(",").map((x) => x.trim()),
                    )
                  }
                />
              </Field>
              {evidence("skills")}
              <Field label="Софт-скиллы, через запятую">
                <input
                  value={(Array.isArray(fields.soft_skills)
                    ? fields.soft_skills
                    : []
                  ).join(", ")}
                  onChange={(e) =>
                    change(
                      "soft_skills",
                      e.target.value.split(",").map((x) => x.trim()),
                    )
                  }
                />
              </Field>
              <Field label="Описание">
                <textarea
                  rows={5}
                  value={fields.description || ""}
                  onChange={(e) => change("description", e.target.value)}
                />
              </Field>
            </div>
          ) : tab === "text" ? (
            <div className="source-pages">
              {(active?.pages || d.result?.pages)?.map((p) => (
                <section key={p.page}>
                  <div>
                    <Badge>Страница {p.page}</Badge>
                    <small>
                      {p.method === "pdf_text"
                        ? "Текстовый слой PDF"
                        : `OCR · техническая уверенность ${Math.round(p.confidence * 100)}%`}
                    </small>
                  </div>
                  <pre>{p.text}</pre>
                </section>
              ))}
            </div>
          ) : (
            <div className="extra-fields">
              {Object.entries(fields.extra_fields || {}).length ? (
                Object.entries(fields.extra_fields).map(([key, value]) => (
                  <div key={key}>
                    <strong>{key}</strong>
                    <span>
                      {typeof value === "object"
                        ? JSON.stringify(value)
                        : String(value)}
                    </span>
                  </div>
                ))
              ) : (
                <Empty
                  title="Дополнительные поля не найдены"
                  text="Полный исходный текст сохранён на соседней вкладке."
                />
              )}
            </div>
          )}
          {error && <ErrorBox message={error} />}
          <div className="modal-actions">
            <button
              className="button secondary"
              disabled={busy || selectionRequired}
              onClick={async () => {
                try {
                  await save();
                  notify("Проверенный черновик сохранён");
                  onSaved();
                } catch (e) {
                  setError((e as Error).message);
                }
              }}
            >
              Сохранить черновик
            </button>
            <button className="button primary" disabled={busy || selectionRequired} onClick={apply}>
              {busy
                ? "Сохраняем…"
                : d.kind === "vacancy"
                  ? "Создать вакансию / потребность"
                  : user.role === "candidate"
                    ? "Перенести в мой профиль"
                    : "Завершить разбор"}
              <ArrowRight size={17} />
            </button>
          </div>
        </Modal>
      )}
      {vacancy && (
        <VacancyEditor
          initial={{
            title: fields.title || "",
            description: fields.description || "",
            specialization: fields.specialization || meta.specializations[0].id,
            grade: fields.grade || "middle",
            skills: fields.skills || [],
            salary_from: fields.salary_from || 0,
            salary_to: fields.salary_to || 0,
            work_format: fields.work_format || "удалённо",
            status: "draft",
          }}
          title="Потребность из документа"
          draft
          onClose={() => setVacancy(false)}
          onSaved={() => {
            notify(
              "Потребность создана. Выберите её в банке талантов для подбора.",
            );
            onSaved();
            navigate("search");
          }}
        />
      )}
    </>
  );
}
export function ValidationPage() {
  const result=useData<any>("/validation");
  if(result.loading)return <Loading/>;
  if(result.error)return <ErrorBox message={result.error}/>;
  const audit=result.data?.audit,ranking=result.data?.benchmark,timing=result.data?.load;
  return <>
    <PageHead eyebrow="QUALITY & TRUST" title="Проверяемые результаты" description="Качество подбора, скорость ответа и понятные границы измерений."/>
    <div className="stats-grid">
      <Stat label="Профилей в контрольном наборе" value={audit?.candidates||"—"} caption="Проверены идентификаторы и целостность" icon={<Database size={19}/>}/>
      <Stat label="Вакансий в контрольном наборе" value={audit?.vacancies||"—"} caption="Проверены условия и связи" icon={<FileText size={19}/>}/>
      <Stat label="Направлений" value={audit?.specializations||"—"} caption="Профессиональная таксономия" icon={<Layers3 size={19}/>}/>
      <Stat label="Размеченных пар" value={audit?.gold_pairs?.toLocaleString("ru-RU")||"—"} caption="Контрольная разметка не читается рабочим API" icon={<ShieldCheck size={19}/>}/>
    </div>
    <div className="two-columns">
      <section className="panel"><h2>Точность подбора</h2>{ranking?<><div className="metric-pair"><div><strong>{(ranking.precision_at_5*100).toFixed(1)}%</strong><span>Precision@5</span></div><div><strong>{(ranking.ndcg_at_5*100).toFixed(2)}%</strong><span>nDCG@5</span></div></div><p>Проверено запросов: {ranking.queries}. Полное совпадение top-5: {(ranking.exact_top5_rate*100).toFixed(2)}%.</p></>:<p className="muted">Текущий отчёт ещё не загружен.</p>}<p className="muted">Измерена фактическая выдача API по фиксированной контрольной разметке. Это не измеренный процент успешных наймов.</p></section>
      <section className="panel"><h2>Время ответа API</h2>{timing?<><div className="metric-pair"><div><strong>{timing.median_ms?.toFixed(2)} мс</strong><span>медиана</span></div><div><strong>{timing.p95_ms?.toFixed(2)} мс</strong><span>95-й процентиль</span></div></div><p>Запросов: {timing.requests}; ошибок: {timing.errors}. Минимум: {timing.min_ms?.toFixed(2)} мс.</p><p className="muted">Последовательная локальная серия, один клиент. Обработка документов и интеллектуальные диалоги измеряются отдельно.</p></>:<p className="muted">Отчёт времени ответа ещё не загружен.</p>}</section>
    </div>
    <section className="panel history-panel"><h2>Контроль качества решений</h2><p>Квалификация, профессиональная практика и подтверждение опыта — отдельные доказательства. Пилотные вопросы не влияют на балл; спорные события рассматриваются в контексте решения.</p><p className="muted">Надёжность шкалы на реальных специалистах и фактическая ёмкость инфраструктуры требуют отдельной приёмки. Контактные данные не входят в публичные отчёты.</p><a href="/api/openapi.json" target="_blank" rel="noreferrer" className="button secondary">Спецификация API <ExternalLink size={16}/></a></section>
  </>;
}
