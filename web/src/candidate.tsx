import React, { useState, useEffect } from "react";
import {
  ArrowUpRight,
  ArrowRight,
  Check,
  CheckCircle2,
  ShieldCheck,
  FileScan,
  Download,
  LockKeyhole,
  Eye,
  Clock3,
  Code2,
  Mail,
  ClipboardCheck,
  UserRound,
  Target,
  ChevronRight,
  Info,
} from "lucide-react";
import { api, send, money, grade, date } from "./api";
import { EmploymentStatus } from "./employment";
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
  Stat,
} from "./ui";

export function CandidateHome() {
  const { meta, navigate } = useApp();
  const profile = useData("/profile");
  const dash = useData("/dashboard");
  if (profile.loading || dash.loading) return <Loading />;
  if (profile.error || dash.error)
    return <ErrorBox message={profile.error || dash.error} />;
  const p = profile.data?.profile;
  if (!p) return null;
  const spec =
    meta.specializations.find((x) => x.id === p.specialization)?.label ||
    "Выберите направление";
  const steps = [
    {
      title: "Расскажите о себе",
      text: "Профиль, стек и ожидания",
      done: !!p.specialization && !!p.full_name,
      page: "profile",
    },
    {
      title: "Подтвердите уровень",
      text: "Разбор проекта и три кейса",
      done: !!p.confirmed_grade,
      page: "assessment",
    },
    {
      title: "Откройтесь предложениям",
      text: "Управляйте видимостью профиля",
      done: p.visibility === "employer_searchable" && p.consent_publication,
      page: "profile",
    },
  ];
  return (
    <>
      <PageHead
        eyebrow="НАВЫКИ ОТКРЫВАЮТ ВОЗМОЖНОСТИ"
        title="Ваша карьера. Ваш ход."
        description="Покажите, что умеете, и получайте предложения на своих условиях."
        actions={
          <button
            className="button primary"
            onClick={() => navigate("profile")}
          >
            Открыть профиль
            <ArrowUpRight size={17} />
          </button>
        }
      />
      <div className="candidate-home-hero">
        <div>
          <Badge tone="light">ПРУФ-ИТ · ВАШ ПРОФИЛЬ</Badge>
          <h2>
            {p.confirmed_grade ? "Уровень подтверждён." : "Сделайте навыки"}
            <br />
            <span>
              {p.confirmed_grade ? "Следующий шаг — ваш." : "видимыми."}
            </span>
          </h2>
          <p>
            {p.confirmed_grade
              ? `${spec} · ${grade(p.confirmed_grade)}`
              : "Обсудите свой опыт с ассистентом, получите категорию и откройте профиль для работодателей."}
          </p>
          <button
            className="button dark"
            onClick={() =>
              navigate(p.confirmed_grade ? "invitations" : "assessment")
            }
          >
            {p.confirmed_grade ? "Смотреть предложения" : "Подтвердить уровень"}
            <ArrowRight size={17} />
          </button>
        </div>
        <div className="talent-pass">
          <div className="pass-top">
            <span>ПАСПОРТ НАВЫКОВ</span>
            <ShieldCheck size={25} />
          </div>
          <div className="pass-score">
            {p.test_score || "—"}
            <small>/ 100</small>
          </div>
          <strong>{spec}</strong>
          <div>
            <Grade value={p.confirmed_grade} />
            <FspBadge status={p.fsp_status} />
          </div>
          <div className="pass-footer">
            <span>{p.id}</span>
            <span>{p.synthetic ? "ДЕМО-ПРОФИЛЬ" : "ЛИЧНЫЙ ПРОФИЛЬ"}</span>
          </div>
        </div>
      </div>
      <div className="onboarding-steps">
        {steps.map((s, i) => (
          <button
            className={s.done ? "done" : ""}
            key={s.title}
            onClick={() => navigate(s.page)}
          >
            <span>
              {s.done ? <Check size={20} /> : String(i + 1).padStart(2, "0")}
            </span>
            <div>
              <strong>{s.title}</strong>
              <small>{s.text}</small>
            </div>
            <ArrowUpRight size={18} />
          </button>
        ))}
      </div>
      <div className="stats-grid three">
        <Stat
          label="Предложения работы"
          value={dash.data.stats.invitations}
          caption={`${dash.data.stats.new_invitations} новых · зарплата указана заранее`}
          icon={<Mail size={20} />}
        />
        <Stat
          label="Ваши отклики"
          value={dash.data.stats.applications}
          caption="Вы можете проявить инициативу"
          icon={<ArrowUpRight size={20} />}
        />
        <Stat
          label="Короткие задания"
          value={dash.data.stats.tasks}
          caption="Практика поддерживает актуальность"
          icon={<Code2 size={20} />}
        />
      </div>
      <EmploymentStatus/>
      <div className="two-columns">
        <section className="panel">
          <div className="section-heading">
            <h2>Что видит работодатель</h2>
            <Eye size={20} />
          </div>
          <div className="visibility-preview">
            <strong>{spec}</strong>
            <div>
              <Grade value={p.confirmed_grade} />
              <FspBadge status={p.fsp_status} />
            </div>
            <Skills items={p.skills || []} />
            <p>Ожидание от {money(p.expected_salary || 0)}</p>
            <Badge
              tone={
                p.visibility === "employer_searchable" && p.consent_processing && p.consent_publication && !p.employment_blocked
                  ? "green"
                  : "amber"
              }
            >
              {p.visibility === "employer_searchable" && p.consent_processing && p.consent_publication && !p.employment_blocked
                ? "Доступен в подборе"
                : p.employment_blocked ? "Показы приостановлены до исправления резюме" : "Ещё не опубликован в подборе"}
            </Badge>
          </div>
          <div className="privacy-note">
            <LockKeyhole size={18} />
            Ваше имя и контакты откроются только выбранной компании после
            согласия или отклика.
          </div>
        </section>
        <section className="panel">
          <div className="section-heading">
            <h2>Контроль остаётся у вас</h2>
            <ShieldCheck size={20} />
          </div>
          <ul className="reasons spacious">
            <li>
              <CheckCircle2 size={19} />
              Зарплата известна до первого сообщения.
            </li>
            <li>
              <CheckCircle2 size={19} />
              Недостаток сведений в диалоге не понизит грейд автоматически.
            </li>
            <li>
              <CheckCircle2 size={19} />
              История ФСП дополняет профиль. Её отсутствие не закрывает доступ.
            </li>
            <li>
              <CheckCircle2 size={19} />
              Публикацию профиля можно отключить.
            </li>
          </ul>
          <button className="text-button" onClick={() => navigate("profile")}>
            Настроить приватность
            <ArrowRight size={16} />
          </button>
        </section>
      </div>
    </>
  );
}
export function ProfilePage() {
  const { meta, notify, navigate } = useApp();
  const result = useData("/profile");
  const [p, setP] = useState<any>(null),
    [busy, setBusy] = useState(false),
    [error, setError] = useState("");
  useEffect(() => {
    if (result.data) setP(result.data.profile);
  }, [result.data]);
  if (result.loading) return <Loading />;
  if (result.error) return <ErrorBox message={result.error} />;
  if (!p) return null;
  const change = (key: string, value: unknown) =>
    setP((prev: any) => ({ ...prev, [key]: value }));
  const save = async (e: React.FormEvent) => {
    e.preventDefault();
    setBusy(true);
    setError("");
    try {
      const r = await send("/profile", p, "PUT");
      setP(r.profile);
      notify("Профиль и настройки видимости сохранены");
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  };
  const exportPDF = async () => {
    try {
      await send("/documents/export-profile");
      notify("Создаём ваш PDF-профиль. Он появится в документах.");
      navigate("documents");
    } catch (e) {
      notify((e as Error).message, true);
    }
  };
  return (
    <>
      <PageHead
        eyebrow="ВАШ ПРОФЕССИОНАЛЬНЫЙ ПРОФИЛЬ"
        title="Покажите сильные стороны."
        description="Заполните профиль вручную или начните с готового резюме."
        actions={
          <>
            <button
              className="button secondary"
              onClick={() => navigate("documents")}
            >
              <FileScan size={18} />
              Загрузить резюме
            </button>
            <button className="button secondary" onClick={exportPDF}>
              <Download size={18} />
              PDF-профиль
            </button>
          </>
        }
      />
      <form onSubmit={save} className="profile-layout">
        <div>
          <EmploymentStatus/>
          <section className="panel">
            <div className="section-heading">
              <h2>Личные данные</h2>
              <Badge>
                <LockKeyhole size={13} />
                Закрыты до согласия
              </Badge>
            </div>
            <Field label="ФИО">
              <input
                value={p.full_name}
                onChange={(e) => change("full_name", e.target.value)}
                maxLength={250}
              />
            </Field>
            <div className="form-grid">
              <Field label="Контактный email">
                <input
                  type="email"
                  value={p.email}
                  onChange={(e) => change("email", e.target.value)}
                />
              </Field>
              <Field label="Телефон">
                <input
                  type="tel"
                  value={p.phone}
                  onChange={(e) => change("phone", e.target.value)}
                  placeholder="+7 …"
                />
              </Field>
            </div>
          </section>
          <section className="panel">
            <div className="section-heading">
              <h2>Специализация и навыки</h2>
              <Code2 size={20} />
            </div>
            <div className="form-grid">
              <Field label="Отрасль">
                <input
                  required
                  value={p.industry}
                  onChange={(e) => change("industry", e.target.value)}
                  placeholder="ИТ / финтех / образование"
                />
              </Field>
              <Field
                label="Специализация"
                hint="Смена направления потребует нового подтверждения категории."
              >
                <select
                  value={p.specialization}
                  onChange={(e) => { const id=e.target.value; change("specialization",id); const allowed=meta.specializations.find(s=>s.id===id)?.allowed_grades; if((allowed?.length && !allowed.includes(p.declared_grade)) || (id==="software_architecture" && p.declared_grade==="junior")) change("declared_grade",allowed?.[0]||"middle"); }}
                >
                  <option value="">Выберите направление</option>
                  {meta.specializations.map((s) => (
                    <option key={s.id} value={s.id}>
                      {s.label}
                    </option>
                  ))}
                </select>
              </Field>
              <Field label="Предполагаемый грейд">
                <select
                  value={p.declared_grade}
                  onChange={(e) => change("declared_grade", e.target.value)}
                >
                  {meta.grades.filter(g=>{const allowed=meta.specializations.find(s=>s.id===p.specialization)?.allowed_grades;return (!allowed?.length||allowed.includes(g)) && !(p.specialization==="software_architecture" && g==="junior");}).map((g) => (
                    <option key={g} value={g}>
                      {grade(g)}
                    </option>
                  ))}
                </select>
              </Field>
              <Field label="Опыт, лет">
                <input
                  type="number"
                  min={0}
                  max={80}
                  step={0.1}
                  value={p.experience_years}
                  onChange={(e) =>
                    change("experience_years", Number(e.target.value))
                  }
                />
              </Field>
            </div>
            <Field
              label="Стек и профессиональные навыки"
              hint="Перечислите через запятую. Список навыков — ваши сведения; категория определяется по результатам экспертного диалога."
            >
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
            <Field label="Софт-скиллы, через запятую">
              <input
                value={p.soft_skills.join(", ")}
                onChange={(e) =>
                  change(
                    "soft_skills",
                    e.target.value.split(",").map((x) => x.trim()),
                  )
                }
              />
            </Field>
            <Field label="О себе и своей роли в команде">
              <textarea
                rows={5}
                value={p.about}
                onChange={(e) => change("about", e.target.value)}
                placeholder="Какие задачи решали? Что хотите делать дальше?"
              />
            </Field>
          </section>
          <section className="panel">
            <div className="section-heading">
              <h2>Ожидания и условия</h2>
              <Target size={20} />
            </div>
            <div className="form-grid">
              <Field label="Минимальное ожидание, ₽ / месяц">
                <input
                  type="number"
                  min={0}
                  value={p.expected_salary || ""}
                  onChange={(e) =>
                    change("expected_salary", Number(e.target.value))
                  }
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
            </div>
          </section>
          {error && <ErrorBox message={error} />}
          <div className="form-save">
            <span>Изменения применяются после сохранения</span>
            <button className="button primary" disabled={busy}>
              {busy ? "Сохраняем…" : "Сохранить профиль"}
              <Check size={18} />
            </button>
          </div>
        </div>
        <aside>
          <section className="panel profile-status">
            <div className="eyebrow">ПОДТВЕРЖДЁННАЯ КАТЕГОРИЯ</div>
            <div className="profile-status-score">
              <Score score={p.test_score} />
              <div>
                <Grade value={p.confirmed_grade} />
                <small>Оценка опыта</small>
              </div>
            </div>
            <p>
              {meta.specializations.find((s) => s.id === p.specialization)
                ?.label || "Направление не выбрано"}
            </p>
            {p.test_valid_until && (
              <small>
                Результат действителен до {date(p.test_valid_until)}
              </small>
            )}
            <button
              className="button secondary full"
              type="button"
              onClick={() => navigate("assessment")}
            >
              Обсудить опыт
              <ArrowUpRight size={17} />
            </button>
          </section>
          <section className="panel privacy-settings">
            <div className="section-heading">
              <h2>Приватность</h2>
              <LockKeyhole size={19} />
            </div>
            <label className="checkbox">
              <input
                type="checkbox"
                checked={p.consent_processing}
                onChange={(e) => {
                  change("consent_processing", e.target.checked);
                  if (!e.target.checked) change("visibility", "private");
                }}
              />
              <span>Согласие на обработку данных для работы сервиса</span>
            </label>
            <label className="checkbox">
              <input
                type="checkbox"
                checked={p.consent_publication}
                onChange={(e) => {
                  change("consent_publication", e.target.checked);
                  if (!e.target.checked) change("visibility", "private");
                }}
              />
              <span>
                Согласие на публикацию обезличенного профессионального профиля
              </span>
            </label>
            <Field label="Видимость работодателям">
              <select
                value={p.visibility}
                onChange={(e) => change("visibility", e.target.value)}
              >
                <option value="private">Профиль скрыт</option>
                <option value="employer_searchable">
                  Участвовать в подборе
                </option>
              </select>
            </Field>
            <small>
              Для подбора также нужен действующий подтверждённый грейд. Контакты
              останутся закрытыми.
            </small>
          </section>
          <section className="panel">
            <div className="section-heading">
              <h2>Ваш ФСП ID</h2>
              <ShieldCheck size={20} />
            </div>
            <Field label="ID участника ФСП">
              <input
                value={p.fsp_id || ""}
                onChange={(e) => change("fsp_id", e.target.value || null)}
                placeholder="Если вы участник ФСП"
              />
            </Field>
            <FspBadge status={p.fsp_status} />
            <p className="muted">
              Указание ID не подтверждает достижения автоматически. Для реальной
              проверки потребуется подключение реестра ФСП.
            </p>
            <small>
              Нет истории ФСП? Можно полноценно пользоваться платформой без неё.
            </small>
          </section>
        </aside>
      </form>
    </>
  );
}
