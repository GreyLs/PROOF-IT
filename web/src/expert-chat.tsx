import { useEffect, useRef, useState } from "react";
import { ArrowUpRight, MessageSquare, Send, ShieldCheck } from "lucide-react";
import { api, send } from "./api";
import { useApp, useData, PageHead, ErrorBox, Badge, Loading } from "./ui";

type Dialogue = {
  id: string; mode: string; status: string; revision: number; question_count: number;
  phase: string; case_index: number; cases: {number:number;axis:string;prompt:string;reviewed:boolean;evaluation?:any}[];
  project_result?: {decision:string;score:number};
  messages: { role: string; content: string; question_number?: number;case_number?:number }[];
  evidence: { label: string; status: string; quote: string; reason: string }[];
  result?: { decision: string; score: number; message: string; evidence_basis: string; grade_changed: boolean };
  redirect?: string; created_at: string; model: string;
};
const labels: Record<string,string> = { supported: "Подкреплено рассказом", partial: "Нужна конкретика", missing: "Нет сведений", contradicted: "Есть несоответствие" };

export function ExpertChat({vacancyId, title}: {vacancyId?: string; title?: string}) {
  const { navigate } = useApp();
  const history = useData<{items: Dialogue[]}>("/dialogues");
  const [chat,setChat] = useState<Dialogue|null>(null);
  const [draft,setDraft] = useState("");
  const [busy,setBusy] = useState(false);
  const [error,setError] = useState("");
  const [redirect,setRedirect] = useState("");
  const end = useRef<HTMLDivElement>(null);
  useEffect(()=>{end.current?.scrollIntoView({behavior:"smooth",block:"nearest"});},[chat?.revision,busy]);
  async function start(){
    setBusy(true);setError("");setRedirect("");
    try {setChat(await send("/dialogues",{mode:vacancyId?"vacancy":"profile",vacancy_id:vacancyId}));history.reload();}
    catch(e){setError((e as Error).message);}finally{setBusy(false);}
  }
  async function reply(e:React.FormEvent){
    e.preventDefault();if(!chat||!draft.trim()||busy)return;
    setBusy(true);setError("");setRedirect("");
    try{
      const next = await send("/dialogues/"+chat.id+"/messages",{text:draft,revision:chat.revision});
      setChat(next);setRedirect(next.redirect||"");
      if(!next.redirect)setDraft("");history.reload();
    }catch(e){setError((e as Error).message);}finally{setBusy(false);}
  }
  async function prepare(){setBusy(true);setError("");try{setChat(await send("/dialogues/"+chat!.id+"/cases"));history.reload();}catch(e){setError((e as Error).message);}finally{setBusy(false);}}
  return <div className="expert-chat">
    {!chat ? <section className="panel expert-intro">
      <div className="expert-icon"><MessageSquare size={28}/></div>
      <Badge tone="purple">{vacancyId?"ВАШ ОПЫТ И КОНКРЕТНАЯ ВАКАНСИЯ":"ПЕРСОНАЛЬНЫЙ АССИСТЕНТ"}</Badge>
      <h2>{title||"Разберём ваш опыт по существу"}</h2>
      <p>{vacancyId?"Сопоставим требования этой вакансии с вашим резюме. Уточним только факты, которых не хватает для решения.":"Сначала разберём реальный проект: ваши решения, ответственность и результат. Затем — три коротких индивидуальных кейса на логику и архитектуру по вашей роли и заявленному уровню."}</p>
      <div className="expert-promise"><span>До 3 уточнений опыта</span><span>{vacancyId?"По требованиям вакансии":"3 кейса · без написания кода"}</span><span>Ваш грейд не понижается</span></div>
      {!vacancyId&&<p className="muted">В каждом кейсе — до 800 символов. Расскажите порядок действий, как проверите качество и на чём сосредоточитесь. Уровень подтверждается после обоих этапов; критерии — логика, качество и приоритеты.</p>}
      <p className="muted">Описывайте реальные проекты. Можно не называть заказчика и закрытые цифры. Если опыта нет, сообщите об этом.</p>
      <button className="button primary" onClick={start} disabled={busy}>{busy?"Изучаем профиль…":"Начать экспертный диалог"}<ArrowUpRight size={17}/></button>
      {!vacancyId&&<button className="button text" onClick={()=>navigate("profile")}>Проверить профиль и заявленный уровень</button>}
    </section>:<>
      <div className="expert-toolbar"><Badge tone="purple">{vacancyId?"Соответствие вакансии":chat.phase==="cases"?"Кейсы по вашей роли":"Разбор проекта"}</Badge><span>{chat.phase==="cases"?chat.cases?.length?`Кейс ${Math.min(3,chat.case_index+1)} из 3 · текст проверен` : "Следующий этап: 3 кейса":`Уточнения опыта: ${chat.question_count} из максимум 3`}</span><span className="muted">{chat.status==="completed"?"Оценка завершена":chat.phase==="cases"?"Объясните решение словами":"Обсуждаем ваш опыт"}</span><button className="text-button" disabled={busy} onClick={()=>{setChat(null);setDraft("");setError("");setRedirect("");}}>К списку диалогов</button></div>
      <div className="expert-messages" aria-live="polite" aria-busy={busy}>
        {chat.messages.map((m,i)=><div className={"expert-bubble "+m.role} key={i}><small>{m.role==="user"?"Вы":"Персональный ассистент"}{m.case_number?` · кейс ${m.case_number}`:m.question_number?` · уточнение ${m.question_number}`:""}</small><p>{m.content}</p>{m.role==="assistant"&&m.case_number&&<small>{Array.from(m.content).length}/800 символов · без кода</small>}</div>)}
        {busy&&<div className="expert-bubble assistant"><p>{chat.phase==="cases"&&!chat.cases?.length?"Готовлю три ситуации и отдельно проверяю понятность каждой…":"Проверяю ход рассуждения и соответствие критериям…"}</p></div>}
        {redirect&&<div className="notice" role="status">{redirect}</div>}
        <div ref={end}/>
      </div>
      {chat.status==="active"&&chat.phase==="cases"&&!chat.cases?.length&&<section className="panel"><h3>Опыт разобран. Перейдём к трём кейсам.</h3><p>Короткие ситуации по вашей роли. Ответьте словами: порядок действий, проверка качества и главный приоритет. Подготовка включает отдельную проверку текста и может занять около минуты.</p><button className="button primary" disabled={busy} onClick={prepare}>{busy?"Готовим и проверяем…":"Подготовить три кейса"}</button></section>}
      {chat.status==="active"&&(chat.phase!=="cases"||!!chat.cases?.length)&&<form className="expert-compose" onSubmit={reply}><label htmlFor={"expert-reply-"+chat.id}>{chat.phase==="cases"?"Как вы решите эту задачу?":"Ваш ответ о профессиональном опыте"}</label><textarea id={"expert-reply-"+chat.id} rows={4} maxLength={450} value={draft} onChange={e=>setDraft(e.target.value)} disabled={busy} placeholder={chat.phase==="cases"?"Порядок действий → проверка качества → главный приоритет. Кратко, без кода.":"Конкретный проект, ваше действие и наблюдаемый результат…"}/><div><small>{draft.length}/450 · Короткий конкретный ответ повышает точность оценки</small><button className="button primary" disabled={busy||!draft.trim()}><Send size={16}/>Отправить ответ</button></div></form>}
      {!!chat.result&&<section className="panel expert-result"><ShieldCheck size={25}/><h3>{chat.result.message}</h3><p>{chat.result.evidence_basis}</p>{chat.result.grade_changed&&<p>Категория подтверждена на 90 дней. Для предложений включите публикацию профиля.</p>}{chat.project_result&&<p>Разбор проекта: {chat.project_result.decision==="supported"?"опыт раскрыт по критериям роли":"остались пробелы или противоречия"}.</p>}<button className="button text" onClick={()=>{setChat(null);setError("");}}>Вернуться к диалогам</button></section>}
      {chat.status==="completed"&&chat.cases?.map(c=><details className="panel expert-evidence" key={c.number}><summary>Кейс {c.number}: {c.axis}</summary>{["logic","quality","focus"].map((key,i)=><article key={key}><strong>{["Логика и последовательность","Как проверяется качество","Приоритеты и риски"][i]} · {c.evaluation?.[key]?.rating ?? "—"}/3</strong><p>{c.evaluation?.[key]?.reason}</p>{c.evaluation?.[key]?.quote&&<blockquote>{c.evaluation[key].quote}</blockquote>}</article>)}</details>)}
      {!!chat.evidence?.length&&<details className="panel expert-evidence" open={chat.status==="completed"}><summary>На чём основан вывод</summary>{chat.evidence.map((e,i)=><article key={i}><strong>{e.label}</strong><Badge tone={e.status==="supported"?"green":"amber"}>{labels[e.status]||e.status}</Badge><p>{e.reason}</p>{e.quote&&<blockquote>{e.quote}</blockquote>}</article>)}</details>}
    </>}
    {error&&<ErrorBox message={error}/ >}
    {!chat&&!!history.data?.items.length&&<section className="panel"><h3>Ваши предыдущие диалоги</h3>{history.data.items.filter((x:any)=>vacancyId?x.vacancy_id===vacancyId:x.mode==="profile").slice(0,8).map(x=><button className="expert-history" key={x.id} disabled={busy} onClick={async()=>{setError("");try{setChat(await api("/dialogues/"+x.id));}catch(e){setError((e as Error).message);}}}><span>{new Date(x.created_at).toLocaleString("ru-RU")}</span><span>{x.status==="completed"?"Посмотреть результат":"Продолжить"}</span><ArrowUpRight size={16}/></button>)}</section>}
  </div>;
}

export function ExpertProfilePage(){return <><PageHead eyebrow="ПРОФЕССИОНАЛЬНЫЙ ОПЫТ И ХОД МЫШЛЕНИЯ" title="Подтвердите уровень в диалоге" description="Разбор реального проекта и три понятных кейса по вашей роли — без написания кода."/><ExpertChat/></>;}
