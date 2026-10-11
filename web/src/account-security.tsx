import { useState } from "react";
import { api, send } from "./api";
import { ErrorBox, Field, PageHead, useApp, useData } from "./ui";

export function RecoveryForm({ onCancel }: { onCancel: () => void }) {
  const token = new URLSearchParams(location.search).get("reset");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [result, setResult] = useState<any>(null);
  return <form onSubmit={async (event) => {
    event.preventDefault(); setBusy(true); setError("");
    try { setResult(await send(token ? "/auth/reset-confirm" : "/auth/reset-request", token ? {token, password} : {email})); }
    catch (error) { setError((error as Error).message); }
    finally { setBusy(false); }
  }}>
    {result ? <div className="notice"><div><p>{result.message}</p>
      {result.development_mail && <a href={result.development_mail.link}>Открыть письмо в локальной песочнице</a>}
    </div></div> : <>
      {token ? <Field label="Новый пароль" hint="От 10 до 256 символов"><input type="password" autoComplete="new-password" minLength={10} maxLength={256} required value={password} onChange={event => setPassword(event.target.value)} /></Field>
        : <Field label="Адрес электронной почты"><input type="email" autoComplete="email" maxLength={254} required value={email} onChange={event => setEmail(event.target.value)} /></Field>}
      <button className="button primary full" disabled={busy}>{busy ? "Подождите…" : token ? "Сохранить новый пароль" : "Отправить ссылку"}</button>
    </>}
    {error && <ErrorBox message={error}/>}
    <button className="text-button" type="button" onClick={onCancel}>Вернуться ко входу</button>
  </form>;
}

export function AccountSecurityPage() {
  const { user, notify } = useApp();
  const [password, setPassword] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  return <>
    <PageHead eyebrow="ВАШИ ДАННЫЕ ПОД ВАШИМ КОНТРОЛЕМ" title="Доступ и безопасность." description="Управляйте сессиями, доступом к контактам и своими данными." />
    <div className="two-columns">
      <section className="panel"><h2>Учётная запись</h2><p>{user.email}</p>
        <p>Завершите сессии на всех устройствах, если использовали общий компьютер или подозреваете посторонний вход.</p>
        <button className="button secondary" onClick={async () => {try {await send("/auth/logout-all");location.assign("/");} catch(error) {notify((error as Error).message,true);}}}>Выйти на всех устройствах</button>
      </section>
      <section className="panel"><h2>Копия ваших данных</h2><p>Профиль, сведения о документах и события безопасности в JSON. Оригиналы файлов и результаты распознавания доступны в разделе «Документы».</p>
        <button className="button secondary" onClick={async () => {
          try {const data = await api("/account/export");const url=URL.createObjectURL(new Blob([JSON.stringify(data,null,2)],{type:"application/json"}));const a=document.createElement("a");a.href=url;a.download="fsp-account.json";a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);}
          catch(error) {notify((error as Error).message,true);}
        }}>Скачать мои данные</button>
      </section>
    </div>
    {user.role === "candidate" && <ContactAccess/>}
    {!user.synthetic && <section className="panel history-panel"><h2>Удаление аккаунта</h2>
      <p>Профиль, документы и рабочие связи будут удалены, все сессии завершатся. События безопасности без содержимого профиля и резервные копии хранятся по политике оператора.</p>
      <form onSubmit={async event => {event.preventDefault();if(!window.confirm("Удалить аккаунт и его данные? Это действие нельзя отменить в кабинете."))return;setBusy(true);setError("");try {await api("/account",{method:"DELETE",body:JSON.stringify({password})});location.assign("/");} catch(error){setError((error as Error).message);} finally {setBusy(false);}}}>
        <Field label="Подтвердите текущий пароль"><input type="password" required value={password} onChange={e=>setPassword(e.target.value)} autoComplete="current-password"/></Field>
        <button className="button secondary" disabled={busy}>Удалить мой аккаунт</button>
      </form>{error && <ErrorBox message={error}/>}
    </section>}
  </>;
}

function ContactAccess() {
  const result=useData<{items:{company_id:string;company_name:string;revoked:boolean}[]}>("/account/contact-access");
  const {notify}=useApp();
  return <section className="panel history-panel"><h2>Кому доступны контакты</h2>
    <p>Вы можете закрыть доступ компании независимо от статуса предложения. Уже полученную компанией копию контактов сервис отозвать не может.</p>
    {result.error && <ErrorBox message={result.error}/>}
    {result.data?.items.length===0 && <p className="muted">Вы ещё не открывали контакты компаниям.</p>}
    {result.data?.items.map(item=><div className="section-heading" key={item.company_id}><div><strong>{item.company_name}</strong><p>{item.revoked?"Контакты закрыты":"Доступ разрешён вами"}</p></div>
      <button className="button secondary" onClick={async()=>{try {await send("/account/contact-access",{company_id:item.company_id,restore:item.revoked});result.reload();}catch(error){notify((error as Error).message,true);}}}>{item.revoked?"Открыть снова":"Закрыть контакты"}</button>
    </div>)}
  </section>;
}
