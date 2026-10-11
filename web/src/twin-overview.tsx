import React from 'react';
import {ArrowRight, Database, GitBranch, ScanLine, ShieldCheck} from 'lucide-react';
import {useApp} from './ui';
import {money} from './api';

export function TwinOverview({employer,entity}:{employer:boolean;entity?:any}){
  const {navigate}=useApp();
  return <section className="twin-overview" aria-label="Как работает цифровой двойник">
    <div className="twin-intro"><span className="eyebrow">DIGITAL TWIN · DECISION WORKSPACE</span><h2>{employer?'Проверьте решение до изменения условий найма':'Проверьте карьерный шаг до изменения своих условий'}</h2>
      <p>Цифровой двойник — обновляемая рабочая модель, а не копия личности. Он связывает вашу цель, доказательства и доступный рынок, чтобы сравнивать конкретные варианты действий.</p></div>
    <div className="twin-flow">
      <article><Database size={21}/><span className="twin-step">01 · ВХОД</span><h3>{employer?'Вакансия и команда':'Цель и доказательства'}</h3><p>{employer?'Роль, грейд, вилка, требования и явно заданный рабочий процесс.':'Целевое резюме, условия поиска и проверенные артефакты навыков.'}</p></article>
      <ArrowRight className="twin-flow-arrow" aria-hidden="true"/>
      <article><GitBranch size={21}/><span className="twin-step">02 · МОДЕЛЬ</span><h3>Рынок и ограничения</h3><p>{employer?'Доступный пул, подтверждённость требований, бюджет и этапы отбора.':'Доступные вакансии, пробелы в доказательствах и переносимые навыки.'}</p></article>
      <ArrowRight className="twin-flow-arrow" aria-hidden="true"/>
      <article><ScanLine size={21}/><span className="twin-step">03 · РЕШЕНИЕ</span><h3>Сравнение сценариев</h3><p>Текущие условия → вариант изменений → сроки, неопределённость и следующий проверяемый шаг.</p></article>
    </div>
    {entity&&<div className="twin-snapshot"><div><small>Выбранная цель</small><strong data-no-translate>{entity.title||entity.target_position}</strong></div><div><small>{employer?'Зарплатная вилка':'Ожидание по оплате'}</small><strong>{employer?`${money(entity.salary_from)} – ${money(entity.salary_to)}`:money(entity.expected_salary)}</strong></div><div><small>{employer?'Требования вакансии':'Заявлено в резюме'}</small><span data-no-translate>{(entity.skills||[]).slice(0,5).join(' · ')||'Не указано'}</span></div></div>}
    <div className="twin-boundary"><ShieldCheck size={18}/><p>Сценарий не изменяет резюме, вакансию или грейд. Заявленный навык не становится подтверждённым от перемещения ползунка. Решение и применение условий остаются за вами.</p></div>
    <div className="twin-shortcuts"><button type="button" onClick={()=>navigate(employer?'evidence':'proof-graph')}>{employer?'Проверить требования и распределение':'Посмотреть источники и пробелы'} <ArrowRight size={15}/></button><button type="button" onClick={()=>navigate(employer?'research-lab':'evidence')}>{employer?'Открыть радар рынка':'Выбрать следующее доказательство'} <ArrowRight size={15}/></button></div>
  </section>;
}

export function TwinComparison({result}:{result:any}){
  const a=result.baseline,b=result.scenario;
  const daysKnown=a.median_days!=null&&b.median_days!=null;
  const delta=daysKnown?a.median_days-b.median_days:null;
  const probabilityDelta=(b.completion_probability-a.completion_probability)*100;
  return <section className="twin-comparison" aria-label="Что изменилось в сценарии">
    <div className="twin-comparison-head"><h3>Что изменилось в вашем сценарии</h3><span>{result.trials} модельных траекторий · {result.horizon_days} дней</span></div>
    <div className="twin-compare-grid">{[{label:'Текущие условия',value:a,tone:'baseline'},{label:'Выбранный сценарий',value:b,tone:'scenario'}].map(row=><article key={row.tone}><span>{row.label}</span><strong>{row.value.median_days==null?'Не определяется':<>{row.value.median_days} дн.</>}</strong><small>Медиана срока в модели</small><small>Диапазон 10–90%: {row.value.p10_days??'Не определяется'} – {row.value.p90_days??'за пределами рынка'} дн.</small><div className={'twin-probability '+row.tone}><i style={{width:`${Math.max(0,Math.min(100,row.value.completion_probability*100))}%`}}/></div><p>{Math.round(row.value.completion_probability*100)}% модельных траекторий завершились к выбранному дню</p></article>)}</div>
    <div className="twin-change-summary"><strong>{delta==null?'Медиана не определяется при текущей достижимости рынка':delta>0?<>Срок в сценарии короче на {delta.toFixed(1)} дн.</>:delta<0?<>Срок в сценарии длиннее на {Math.abs(delta).toFixed(1)} дн.</>:'Медианный срок не изменился'}</strong><span>Изменение модельной доли завершения: {probabilityDelta>0?'+':''}{probabilityDelta.toFixed(1)} п.п.</span></div>
    <details className="twin-assumptions"><summary>Допущения, происхождение и границы результата</summary><p>Временной prior — замороженная CatBoost-модель; сравнение использует одинаковые случайные воздействия. Граф и доступный рынок дают контекст. Кривая показывает сценарное распределение, не подтверждённую на реальных наймах вероятность и не причинный эффект изменения условий.</p><p>Базовый процесс модели: ответ за 3 дня и 3 этапа интервью. Квантили 10–90% включают недостижимые траектории. Если порог не достигнут, срок не подменяется средним среди успешных случаев.</p><dl><dt>Версия метода</dt><dd data-no-translate>{result.version}</dd><dt>Seed</dt><dd data-no-translate>{result.seed}</dd><dt>Идентификатор решения</dt><dd data-no-translate>{result.decision_id||'Сохраняется в журнале решений'}</dd></dl></details>
  </section>;
}
