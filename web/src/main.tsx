import React, { useState, useEffect } from "react";
import { createRoot } from "react-dom/client";
import {
  LayoutDashboard,
  Users,
  Mail,
  BriefcaseBusiness,
  FileScan,
  ShieldCheck,
  UserRound,
  ClipboardCheck,
  Settings2,
  ArrowUpRight,
  ArrowRight,
  LogOut,
  Check,
  Code2,
  ChevronDown,
  Menu,
  Activity,
  X,
  Building2,
  Layers3,
  Sparkles,
  MessageCircle,
} from "lucide-react";
import { api, send, Meta, User } from "./api";
import { EvidencePage } from './evidence';
import { ResearchLabPage } from './research-lab';
import { AuthVideo } from './auth-video';
import type { DemoWorkspace } from './demo';
import { LanguageSelector } from './language-selector';
import { workspaceNavigation, SectionTabs } from './navigation';
import { useLanguage } from './i18n';
import { AuthTechBackground } from './auth-tech-background';
import {
  AppContext,
  Loading,
  ErrorBox,
  Field,
  Badge,
  useData,
  PageHead,
  Stat,
} from "./ui";
import {
  SearchPage,
  InvitationsPage,
  VacanciesPage,
  TasksPage,
  CompanyPage,
  ApplicationsPage,
} from "./employer";
import { ProfilePage, CandidateHome } from "./candidate";
import { ResumesPage } from "./resumes";
import { ExpertProfilePage as AssessmentPage } from "./expert-chat";
import { DocumentsPage, ValidationPage } from "./documents";
import { RecoveryForm, AccountSecurityPage } from "./account-security";
import { ConversationsPage } from "./conversations";
import { CareerConsultant, PracticalTasks, Notifications } from "./workbench";
import { HorizonPage, ProofGraphPage, CareerRoutePage, StrategyPage, ArenaPage } from "./intelligence";
import { ProfessionalAssessment, AssessmentLab } from "./professional";
import "./styles.css";
import "./workbench.css";

function App() {
  useLanguage();
  const [meta, setMeta] = useState<Meta | null>(null),
    [user, setUser] = useState<User | null>(null),
    [boot, setBoot] = useState(true),
    [failure, setFailure] = useState(""),
    [page, setPage] = useState(location.hash.slice(1) || "overview"),
    [toast, setToast] = useState<{ text: string; error: boolean } | null>(null),
    [menu, setMenu] = useState(false);
  const [demoWorkspace,setDemoWorkspace]=useState<DemoWorkspace|null>(null);
  const [loggingOut,setLoggingOut]=useState(false);
  useEffect(()=>{let active=true;setDemoWorkspace(null);if(user&&meta?.demo)api('/auth/demo-context').then(r=>{if(active)setDemoWorkspace(r.workspace);}).catch(()=>{});return()=>{active=false};},[user?.id,meta?.demo]);
  const logout=async()=>{setLoggingOut(true);try{await send('/auth/logout');setUser(null);setToast(null);setDemoWorkspace(null);history.replaceState(null,'',location.pathname);setPage('overview');setMenu(false);}catch(e){notify('Не удалось завершить сессию. Попробуйте снова.',true);}finally{setLoggingOut(false);}};
  const notify = (text: string, error = false) => {
    setToast({ text, error });
    setTimeout(() => setToast(null), 6000);
  };
  const navigate = (p: string) => {
    location.hash = p;
    setPage(p);
    setMenu(false);
    window.scrollTo(0, 0);
  };
  useEffect(() => {
    const listener = () => setPage(location.hash.slice(1) || "overview");
    window.addEventListener("hashchange", listener);
    return () => window.removeEventListener("hashchange", listener);
  }, []);
  useEffect(() => {
    (async () => {
      try {
        const m = await api<Meta>("/meta");
        setMeta(m);
        const token = new URLSearchParams(location.search).get("verify");
        if (token) {
          const r = await send("/auth/verify", { token });
          setUser(r.user);
          history.replaceState(null, "", location.pathname + "#profile");
        } else {
          try {
            setUser((await api("/auth/me")).user);
          } catch {
            setUser(null);
          }
        }
      } catch (e) {
        setFailure((e as Error).message);
      } finally {
        setBoot(false);
      }
    })();
  }, []);
  if (boot)
    return (
      <div className="boot">
        <img src="/brand/logo_01w.svg" alt="Федерация спортивного программирования" />
        <Loading />
      </div>
    );
  if (failure || !meta)
    return (
      <div className="boot">
        <ErrorBox
          message={failure || "Не удалось загрузить сервис"}
          retry={() => location.reload()}
        />
      </div>
    );
  if (!user || new URLSearchParams(location.search).has("reset"))
    return (
      <Login
        onLogin={(u) => {
          setUser(u);
          navigate("overview");
        }}
      />
    );
  const employer = user.role === "employer";
  const groups = workspaceNavigation(employer);
  const activeGroup=groups.find(group=>group.entries.some(entry=>entry.page===page)) || groups[0];
  const activeLabel=activeGroup.entries.find(entry=>entry.page===page)?.label || activeGroup.label;
  return (
    <AppContext.Provider value={{ user, meta, notify, navigate, demoWorkspace }}>
      <div className="app-shell" key={user.id}>
        {menu && (
          <button
            className="sidebar-backdrop"
            onClick={() => setMenu(false)}
            aria-label="Закрыть меню"
          />
        )}
        <aside className={"sidebar " + (menu ? "open" : "")}>
          <a
            className="brand"
            href="#overview"
            onClick={() => navigate("overview")}
          >
            <img
              src="/brand/logo_01w.svg"
              alt="Федерация спортивного программирования"
            />
            <div>
              ПРУФ-ИТ<span>ПЛАТФОРМА ТАЛАНТОВ</span>
            </div>
          </a>
          <div className="workspace-label">
            {employer ? "КАБИНЕТ РАБОТОДАТЕЛЯ" : "КАБИНЕТ КАНДИДАТА"}
          </div>
          <nav aria-label="Разделы кабинета">
            {groups.map(({id,label,icon:Icon,entries}) => (
              <button
                className={activeGroup.id === id ? "active" : ""}
                key={id}
                data-nav-group={id}
                aria-current={activeGroup.id===id?'page':undefined}
                onClick={() => navigate(entries[0].page)}
              >
                <Icon size={19} />
                <span>{label}</span>
                {activeGroup.id === id && <i />}
              </button>
            ))}
          </nav>
          <div className="sidebar-bottom">
            <div className="sidebar-note">
              <span className="online-dot" />
              Навыки открывают возможности
            </div>
          </div>
        </aside>
        <div className="main-area">
          <header className="topbar">
            <div className="breadcrumbs">
              <button
                className="icon-button mobile-menu"
                onClick={() => setMenu(!menu)}
                aria-label="Меню"
                aria-expanded={menu}
              >
                <Menu />
              </button>
              <span>Рабочее пространство</span>
              <span className="slash">/</span>
              <strong>{activeLabel}</strong>
            </div>
            <div className="topbar-right">
              <LanguageSelector/>
              <Notifications />
              <div className="account-avatar">{employer ? "ВК" : "К"}</div>
              <button
                className="icon-button"
                title="Выйти"
                aria-label="Выйти"
                disabled={loggingOut}
                onClick={()=>void logout()}
              >
                <LogOut size={18} />
                <span className="logout-label">Выйти</span>
              </button>
            </div>
          </header>
          <main key={user.id+page}>
            <SectionTabs group={activeGroup} page={page} navigate={navigate}/>
            {page === "overview" ? (
              employer ? (
                <EmployerHome />
              ) : (
                <CandidateHome />
              )
            ) : page === "horizon" ? (
              <HorizonPage />
            ) : page === "proof-graph" && !employer ? (
              <ProofGraphPage />
            ) : page === "career-route" && !employer ? (
              <CareerRoutePage />
            ) : page === "arena" && !employer ? (
              <ArenaPage />
            ) : page === "professional-assessment" && !employer ? (
              <ProfessionalAssessment />
            ) : page === "assessment-lab" && employer ? (
              <AssessmentLab />
            ) : page === "strategy" && employer ? (
              <StrategyPage />
            ) : page === "search" && employer ? (
              <SearchPage />
            ) : page === "invitations" ? (
              <InvitationsPage />
            ) : page === "vacancies" ? (
              <VacanciesPage />
            ) : page === "applications" ? (
              <ApplicationsPage />
            ) : page === "messages" ? (
              <ConversationsPage />
            ) : page === "tasks" ? (
              <PracticalTasks />
            ) : page === "tasks-manual" ? (
              <TasksPage />
            ) : page === "career" && !employer ? (
              <CareerConsultant />
            ) : page === "profile" && !employer ? (
              <ProfilePage />
            ) : page === "resumes" && !employer ? (
              <ResumesPage />
            ) : page === "assessment" && !employer ? (
              <AssessmentPage />
            ) : page === "documents" ? (
              <DocumentsPage />
            ) : page === "company" && employer ? (
              <CompanyPage />
            ) : page === "evidence" ? (
              <EvidencePage />
            ) : page === "research-lab" ? (
              <ResearchLabPage />
            ) : page === "validation" ? (
              <ValidationPage />
            ) : page === "security" ? (
              <AccountSecurityPage />
            ) : (
              <EmployerHome />
            )}
          </main>
          <footer className="app-footer">
            <span>ПРУФ-ИТ · ФСП</span>
            <span>Навыки. Доверие. Возможности.</span>
            <a href="/api/openapi.json" target="_blank" rel="noreferrer">
              API ↗
            </a>
          </footer>
        </div>
        {toast && (
          <div
            className={"toast " + (toast.error ? "error" : "")}
            role={toast.error ? "alert" : "status"}
          >
            {toast.error ? <X size={18} /> : <Check size={18} />}
            <span>{toast.text}</span>
            <button
              onClick={() => setToast(null)}
              aria-label="Закрыть уведомление"
            >
              <X size={16} />
            </button>
          </div>
        )}
      </div>
    </AppContext.Provider>
  );
}
function Login({ onLogin }: { onLogin: (u: User) => void }) {
  const [mode, setMode] = useState(new URLSearchParams(location.search).has("reset") ? "recovery" : "login"),
    [role, setRole] = useState("employer"),
    [email, setEmail] = useState(""),
    [password, setPassword] = useState(""),
    [name, setName] = useState(""),
    [consent, setConsent] = useState(false),
    [busy, setBusy] = useState(false),
    [error, setError] = useState(""),
    [mail, setMail] = useState<any>(null);
  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    setBusy(true);
    setError("");
    try {
      if (mode === "register") {
        const r = await send("/auth/register", {
          email,
          password,
          role,
          name,
          consent_processing: consent,
        });
        setMail(
          r.development_mail || {
            notice:
              "Письмо отправлено на ваш email. Перейдите по ссылке для подтверждения.",
          },
        );
      } else onLogin((await send("/auth/login", { identifier: email, password })).user);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  };
  return (
    <div className="login-page">
      <div className="auth-language"><LanguageSelector/></div>
      <section className="login-story">
        <AuthVideo/>
        <div className="auth-network-shade" aria-hidden="true" />
        <AuthTechBackground/>
        <img src="/brand/logo_01w.svg" className="login-fsp" alt="ФСП" />
        <div className="login-eyebrow">ОТ НАВЫКОВ — К ВОЗМОЖНОСТЯМ</div>
        <h1>
          Те самые люди.
          <br style={{ display: "initial" }} />
          <em>Та самая работа</em>
        </h1>
        <p>
          Специалисты показывают, что умеют.
          <br />
          Работодатели приходят с предложением.
          <br />
          Зарплата известна с первого шага.
        </p>
        <div className="story-footer">
          <span>
            ФЕДЕРАЦИЯ СПОРТИВНОГО
            <br />
            ПРОГРАММИРОВАНИЯ РОССИИ
          </span>
          <span>01 / 2026</span>
        </div>
      </section>
      <section className="login-form">
        <div className="login-product">
          ПРУФ-ИТ <span>by ФСП</span>
        </div>
        <div className="login-form-content">
          <div className="eyebrow">НАВЫКИ. ДОВЕРИЕ. ВОЗМОЖНОСТИ.</div>
          <h2>{mode === "recovery" ? "Восстановим доступ." : mode === "login" ? "С возвращением." : "Начнём знакомство."}</h2>
          <p>
            {mode === "recovery" ? "Ссылка действует 30 минут. После смены пароля прежние сессии будут закрыты." : mode === "login"
              ? "Войдите, чтобы продолжить путь."
              : "Создайте профиль и подтвердите email."}
          </p>
          {mode === "recovery" ? <RecoveryForm onCancel={() => {
            if (new URLSearchParams(location.search).has("reset")) location.assign(location.pathname);
            else setMode("login");
          }}/> : mail ? (
            <div className="mail-preview">
              <Mail size={28} />
              <h3>Подтвердите адрес</h3>
              <p>{mail.notice}</p>
              {mail.token && (
                <button
                  className="button primary"
                  onClick={async () => {
                    try {
                      onLogin(
                        (await send("/auth/verify", { token: mail.token }))
                          .user,
                      );
                    } catch (e) {
                      setError((e as Error).message);
                    }
                  }}
                >
                  Открыть письмо и подтвердить <ArrowRight size={18} />
                </button>
              )}
            </div>
          ) : (
            <form onSubmit={submit}>
              {mode === "register" && (
                <>
                  <div className="segmented">
                    <button
                      type="button"
                      className={role === "employer" ? "selected" : ""}
                      onClick={() => setRole("employer")}
                    >
                      Работодатель
                    </button>
                    <button
                      type="button"
                      className={role === "candidate" ? "selected" : ""}
                      onClick={() => setRole("candidate")}
                    >
                      Кандидат
                    </button>
                  </div>
                  <Field
                    label={
                      role === "employer" ? "Название компании" : "Ваше имя"
                    }
                  >
                    <input
                      required
                      value={name}
                      onChange={(e) => setName(e.target.value)}
                      autoComplete="name"
                    />
                  </Field>
                </>
              )}
              <Field label={mode === "login" ? "Email или имя" : "Электронная почта"}>
                <input
                  type={mode === "login" ? "text" : "email"}
                  required
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  autoComplete={mode === "login" ? "username" : "email"}
                  placeholder={mode === "login" ? "you@company.ru или имя при регистрации" : "you@company.ru"}
                />
              </Field>
              <Field
                label="Пароль"
                hint={mode === "register" ? "Не менее 10 символов" : undefined}
              >
                <input
                  type="password"
                  required
                  minLength={mode === "register" ? 10 : 1}
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  autoComplete={
                    mode === "register" ? "new-password" : "current-password"
                  }
                />
              </Field>
              {mode === "register" && (
                <label className="checkbox">
                  <input
                    type="checkbox"
                    checked={consent}
                    onChange={(e) => setConsent(e.target.checked)}
                    required
                  />
                  <span>
                    Согласен на обработку данных профиля для работы сервиса.
                    Публикацию профиля выберу отдельно в настройках.
                  </span>
                </label>
              )}
              <button className="button primary full" disabled={busy}>
                {busy
                  ? "Подождите…"
                  : mode === "login"
                    ? "Войти в кабинет"
                    : "Создать аккаунт"}
                <ArrowRight size={18} />
              </button>
            </form>
          )}
          {error && <ErrorBox message={error} />}
          {mode === "login" && <p className="auth-toggle"><button className="text-button" onClick={() => {setMode("recovery");setError("");setMail(null);}}>Забыли пароль?</button></p>}
          <p className="auth-toggle">
            {mode === "login" ? "Ещё нет аккаунта?" : "Уже зарегистрированы?"}{" "}
            <button
              className="text-button"
              onClick={() => {
                setMode(mode === "login" ? "register" : "login");
                setMail(null);
                setError("");
              }}
            >
              {mode === "login" ? "Регистрация" : "Войти"}
            </button>
          </p>
        </div>
        <div className="login-bottom">
          <ShieldCheck size={16} />
          Контакты под вашим контролем
        </div>
      </section>
    </div>
  );
}
function EmployerHome() {
  const { data, error, loading } = useData("/dashboard");
  const ctx = React.useContext(AppContext);
  const invitations = useData("/invitations");
  if (loading) return <Loading />;
  if (error) return <ErrorBox message={error} />;
  const grouped = ctx.meta.specializations.map((spec) => ({
    ...spec,
    count: (data?.categories || [])
      .filter((x: any) => x.specialization === spec.id)
      .reduce((n: number, x: any) => n + x.count, 0),
  }));
  return (
    <>
      <PageHead
        eyebrow="ВАША КОМАНДА НАЧИНАЕТСЯ С ТАЛАНТА"
        title="Найдите тех, кто умеет."
        description="Подтверждённые навыки. Понятные категории. Прямой диалог."
        actions={
          <button
            className="button primary"
            onClick={() => ctx.navigate("search")}
          >
            Подобрать кандидатов
            <ArrowUpRight size={18} />
          </button>
        }
      />
      <div className="overview-hero">
        <div>
          <Badge tone="light">НОВЫЙ ПОДХОД К НАЙМУ</Badge>
          <h2>
            Сначала навыки.
            <br />
            <span>Потом знакомство.</span>
          </h2>
          <p>
            Соберите подборку по вашей задаче и пригласите
            <br className="desktop" /> подходящих специалистов с открытой
            зарплатой.
          </p>
          <button
            className="button dark"
            onClick={() => ctx.navigate("search")}
          >
            Открыть банк талантов
            <ArrowRight size={18} />
          </button>
        </div>
        <div className="hero-map" aria-hidden="true">
          <div className="map-grid" />
          <svg viewBox="0 0 420 240">
            <path d="M20 190H110V120H220V60H340V20" />
            <path
              d="M55 225V150H170V195H290V115H390"
              className="secondary-path"
            />
            <circle cx="110" cy="120" r="8" />
            <circle cx="220" cy="60" r="8" />
            <circle cx="340" cy="20" r="8" />
            <circle cx="290" cy="115" r="8" />
          </svg>
          <div className="floating-proof">
            <ShieldCheck size={22} />
            <div>
              <strong>Навыки подтверждены</strong>
              <small>Категория по экспертному диалогу</small>
            </div>
          </div>
          <div className="floating-offer">
            <span className="online-dot" />
            Диалог начинается с предложения
            <ArrowUpRight size={17} />
          </div>
        </div>
      </div>
      <div className="stats-grid">
        <Stat
          label="В банке талантов"
          value={data.stats.candidates}
          caption={
            ctx.meta.demo
              ? "Профили на демонстрационном стенде"
              : "Опубликованные подтверждённые профили"
          }
          icon={<Users size={20} />}
        />
        <Stat
          label="Ваши приглашения"
          value={data.stats.invitations}
          caption="Предложения с открытой зарплатой"
          icon={<Mail size={20} />}
        />
        <Stat
          label="Принято предложений"
          value={data.stats.accepted}
          caption="Кандидат готов к диалогу"
          icon={<Check size={20} />}
        />
        <Stat
          label="Открытые вакансии"
          value={data.stats.vacancies}
          caption="Опубликованы вашей компанией"
          icon={<BriefcaseBusiness size={20} />}
        />
      </div>
      <div className="two-columns">
        <section className="panel">
          <div className="section-heading">
            <div>
              <div className="eyebrow">17 НАПРАВЛЕНИЙ</div>
              <h2>Выберите специализацию</h2>
            </div>
            <button
              className="text-button"
              onClick={() => ctx.navigate("search")}
            >
              Все направления
              <ArrowUpRight size={16} />
            </button>
          </div>
          <div className="category-list">
            {grouped.slice(0, 6).map((s, i) => (
              <button
                key={s.id}
                onClick={() => {
                  sessionStorage.setItem("fsp_search_spec", s.id);
                  ctx.navigate("search");
                }}
              >
                <div className={"category-icon ci" + i}>
                  <Code2 size={20} />
                </div>
                <div>
                  <strong>{s.label}</strong>
                  <small>Junior · Middle · Senior</small>
                </div>
                <span>{s.count}</span>
                <ArrowUpRight size={17} />
              </button>
            ))}
          </div>
        </section>
        <section className="panel">
          <div className="section-heading">
            <div>
              <div className="eyebrow">ПРОСТО И ПРОЗРАЧНО</div>
              <h2>От задачи к команде</h2>
            </div>
            <span className="tiny-code">01 → 03</span>
          </div>
          <div className="journey">
            <div>
              <span>01</span>
              <article>
                <h3>Опишите потребность</h3>
                <p>
                  Направление, грейд, стек и бюджет. Можно загрузить PDF
                  вакансии.
                </p>
              </article>
            </div>
            <div>
              <span>02</span>
              <article>
                <h3>Изучите подтверждённый профиль</h3>
                <p>
                  Оценка опыта, совпавшие навыки и понятные причины
                  рекомендации.
                </p>
              </article>
            </div>
            <div>
              <span>03</span>
              <article>
                <h3>Пригласите к диалогу</h3>
                <p>
                  Кандидат увидит зарплату и решит, открыть ли вам контакты.
                </p>
              </article>
            </div>
          </div>
          <button
            className="subtle-cta"
            onClick={() => ctx.navigate("documents")}
          >
            <FileScan size={19} />
            Начать с PDF вакансии
            <ArrowRight size={18} />
          </button>
        </section>
      </div>
    </>
  );
}
createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>,
);
