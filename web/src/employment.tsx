import { useEffect } from "react";
import { ShieldCheck, AlertCircle } from "lucide-react";
import { useApp, useData, Badge } from "./ui";

export function EmploymentReport({check,blocked=false}:{check:any;blocked?:boolean}) {
  if(!check)return null;
  const labels:Record<string,string>={aligned:"Содержание согласуется",mismatch:"Есть расхождения",insufficient:"Недостаточно данных",invalid_document:"Выписка не распознана",queued:"Сверка выполняется",failed:"Сверка не завершена",source_removed:"Нужна новая сверка",not_provided:"Необязательно"};
  return <section className="panel employment-status" aria-live="polite">
    <div className="section-heading"><h3>{blocked?<AlertCircle size={19}/>:<ShieldCheck size={19}/>} Сверка трудовой истории</h3><Badge tone={check.status==="aligned"?"green":"amber"}>{labels[check.status]||check.status}</Badge></div>
    <p>{check.message || "Можно добровольно загрузить выписку СТД-СФР, СТД-ПФР или СТД-Р. Отсутствие файла не снижает видимость."}</p>
    {blocked&&<p className="error-text"><strong>Показы работодателям приостановлены.</strong> Скорректируйте резюме и дождитесь повторной сверки. Грейд сохраняется.</p>}
    {!!check.differences?.length&&<div className="employment-differences">{check.differences.map((d:any,i:number)=><article key={i}><strong>{d.resume.company}</strong><p>Резюме: {d.resume.position} · {d.resume.start} — {d.resume.end||"по настоящее время"}</p><p>Выписка: {d.record.position} · {d.record.start} — {d.record.end||"увольнение не указано"}</p><small>Проверьте: {(d.fields||[]).map((f:string)=>({position:"должность",start:"начало работы",end:"окончание работы"}[f]||f)).join(", ")}</small></article>)}</div>}
    {!!check.matches?.length&&<p>Согласовано записей: {check.matches.length}. Эквивалентные названия должностей и точность записи дат учтены.</p>}
    <small className="muted">{check.notice||"Сверяется содержание. Подлинность документа и электронная подпись не удостоверяются. Выписка доступна только вам."}</small>
  </section>;
}
export function EmploymentStatus(){
  const {navigate}=useApp();const data=useData("/profile");
  useEffect(()=>{const timer=setInterval(data.reload,5000);return()=>clearInterval(timer);},[]);
  const p=data.data?.profile;if(!p)return null;
  return <><EmploymentReport check={p.employment_check} blocked={p.employment_blocked}/><div className="employment-actions"><button type="button" className="text-button" onClick={()=>navigate("documents")}>Загрузить или проверить выписку</button>{p.employment_blocked&&<button type="button" className="text-button" onClick={()=>navigate("profile")}>Исправить резюме</button>}</div></>;
}
