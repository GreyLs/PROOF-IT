import React from 'react';
import {Activity, BriefcaseBusiness, Building2, FileScan, LayoutDashboard, Layers3, MessageCircle, ShieldCheck, UserRound} from 'lucide-react';

type Entry={page:string;label:string};
export type NavGroup={id:string;label:string;icon:typeof Activity;entries:Entry[]};
export function workspaceNavigation(employer:boolean):NavGroup[]{
  return [
    {id:'home',label:employer?'Обзор':'Мой кабинет',icon:LayoutDashboard,entries:[{page:'overview',label:employer?'Обзор':'Мой кабинет'}]},
    {id:'market',label:employer?'Подбор и воронка':'Вакансии и отклики',icon:BriefcaseBusiness,entries:employer?
      [{page:'search',label:'Поиск кандидатов'},{page:'vacancies',label:'Вакансии'},{page:'applications',label:'Отклики'},{page:'invitations',label:'Приглашения'}]:
      [{page:'vacancies',label:'Вакансии'},{page:'applications',label:'Мои отклики'},{page:'invitations',label:'Предложения'}]},
    {id:'twin',label:'Цифровой двойник',icon:Layers3,entries:employer?
      [{page:'horizon',label:'Сценарии и сроки'},{page:'evidence',label:'Команда и доказательства'},{page:'strategy',label:'Стратегия найма'},{page:'research-lab',label:'Радар рынка'}]:
      [{page:'horizon',label:'Сценарии и сроки'},{page:'proof-graph',label:'Граф доказательств'},{page:'evidence',label:'Следующий шаг'},{page:'career-route',label:'Карьерный маршрут'},{page:'career',label:'Консультант'}]},
    {id:'assessment',label:employer?'Оценка кандидатов':'Проверка навыков',icon:ShieldCheck,entries:employer?
      [{page:'assessment-lab',label:'Лаборатория оценок'},{page:'tasks',label:'Практические задания'}]:
      [{page:'resumes',label:'Резюме и знания'},{page:'arena',label:'ProofLab'},{page:'research-lab',label:'Вклад в GitHub'},{page:'professional-assessment',label:'Тренировка CAT'},{page:'assessment',label:'Проекты и интервью'},{page:'tasks',label:'Практические задания'}]},
    {id:'profile',label:employer?'Компания и документы':'Профиль и документы',icon:employer?Building2:UserRound,entries:employer?
      [{page:'company',label:'Компания'},{page:'documents',label:'Документы'}]:
      [{page:'profile',label:'Мой профиль'},{page:'documents',label:'Документы'}]},
    {id:'messages',label:'Сообщения',icon:MessageCircle,entries:[{page:'messages',label:'Сообщения'}]},
    {id:'settings',label:'Доступ и качество',icon:FileScan,entries:[{page:'security',label:'Доступ и данные'},{page:'validation',label:'Качество и данные'}]},
  ];
}
export function SectionTabs({group,page,navigate}:{group:NavGroup;page:string;navigate:(page:string)=>void}){
  if(group.entries.length<2)return null;
  return <nav className="section-tabs" aria-label="Инструменты раздела" data-section={group.id}>
    {group.entries.map(entry=><button key={entry.page} type="button" aria-current={page===entry.page?'page':undefined} className={page===entry.page?'active':''} onClick={()=>navigate(entry.page)}>{entry.label}</button>)}
  </nav>;
}
