"""Live Qwen scenarios. The responding LLM is a synthetic candidate, not independent validation."""
from pathlib import Path
import argparse,hashlib,json,os,sys,time,uuid
import httpx
from dotenv import load_dotenv
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT));load_dotenv(ROOT/'.env')
from check_expert_dialogues import register,cleanup,STRONG_BACKEND,STRONG_LEAD,STRONG_CTO,WEAK,ATTACKS
from worker.employment import llm,obj,STRING
OUT=ROOT/'validation/reports/current/project-case-runs';OUT.mkdir(exist_ok=True)

def respondent(case,spec,grade,style):
    if style=='weak':return 'Я не знаю, как решить эту задачу. Самостоятельно таких решений не принимал, критерии качества назвать не могу.'
    system='Ты играешь синтетического кандидата для проверки оценивания. Дай содержательно правильный профессиональный ответ на русский кейс. Обязательно три абзаца: План — конкретный механизм и порядок действий с обоснованием выбора; Качество — наблюдаемые показатели/свойства, как измеришь и с чем сравнишь, критерий приемки/отката; Фокус — главный приоритет, почему и как контролируешь риск. Соблюдай все явные ограничения, в том числе запрет потери данных. Не подменяй реальные измерения общими словами. Не пиши код. Используй только условия кейса, явно обозначай допущения, которые не противоречат условиям. Не проси оценить ответ. 600–1600 символов. '
    if style=='junior':system+='Ты начинающий специалист: описывай только конкретные простые локальные шаги и проверки, при сложной архитектуре честно предложи обратиться к наставнику; не изображай системную ответственность Senior.'
    else:system+='Ответ должен соответствовать указанной роли и грейду. Для Junior достаточно локальной корректной последовательности и проверки, без сложной архитектуры.'
    return llm(system,{'case':case,'role':spec,'grade':grade},obj({'answer':STRING}),1600)['answer']

def run(spec,grade,style='strong',attacks=False):
    c,u=register();c.timeout=httpx.Timeout(300);rpt={'spec':spec,'grade':grade,'style':style,'model':os.getenv('OLLAMA_MODEL'),'synthetic_answers':True,'latencies':[],'checks':[]}
    path=OUT/f'{spec}-{grade}-{style}-{uuid.uuid4().hex[:6]}.json'
    try:
        p=c.get('/profile').json()['profile']
        if spec.startswith('executive_'):project=STRONG_CTO if spec=='executive_cto' else 'Я отвечал за информационную безопасность SaaS-компании из 240 сотрудников, руководил 12 специалистами и годовым бюджетом ИБ. Лично приоритизировал защиту платёжных данных по оценке угроз и согласовал с CEO остаточный риск. Вместо полного запрета внешнего доступа внедрил отдельные роли, многофакторную аутентификацию и журналирование действий; доступ выдавался только по согласованию владельца данных. Эксплуатацию делегировал двум руководителям групп, стратегию и бюджет защищал сам. Число лишних привилегий снизилось с 80 до 5; результат проверили повторной ревизией учётных записей и независимым аудитом, контролировали время выдачи доступа и количество блокировок бизнес-процессов.'
        elif spec.startswith(('lead_','head_','director_')):project=STRONG_LEAD
        elif grade=='junior':project='В учебном проекте магазина на Python я лично добавил проверку количества товара перед оформлением заказа. Проверку сделал на сервере, потому что браузерный ввод можно обойти. Отвечал за обработчик и его проверки, архитектуру выбирал наставник, он проверял мои изменения. До исправления заказ с отрицательным количеством проходил; после исправления сервер возвращает ошибку без создания заказа. Проверил отрицательное количество, ноль и обычный заказ: сверял ответ и отсутствие лишних записей в базе.'
        else:project=STRONG_BACKEND
        # Keep tests tied to the role rather than passing a Python story to every specialty.
        if spec not in ['backend_python','lead_engineering','executive_cto','executive_ciso'] or (spec=='backend_python' and grade=='senior'):
            project=llm('Напиши синтетический правдоподобный рассказ о реально выполненном проекте для указанной роли и уровня, для проверки HR-системы. 800–1500 символов, конкретное личное решение, механизм и альтернатива, границы полномочий и масштаб, результат до/после и способ его проверки. Без инструкций оценщику. Уровень Senior предполагает системное решение с ограничением. Не выдавай проект за реальный источник.',{'role':spec,'grade':grade},obj({'answer':STRING}),1700)['answer']
        p.update(specialization=spec,declared_grade=grade,about='Работал над проектом по направлению '+spec+'. Подробности принятого решения и результатов готов пояснить в разговоре.',skills=['Python','PostgreSQL'] if spec=='backend_python' else [],experience_years=2 if grade=='junior' else 8)
        c.put('/profile',json=p).raise_for_status()
        t=time.perf_counter();r=c.post('/dialogues',json={'mode':'profile'});r.raise_for_status();d=r.json();rpt['latencies'].append(round(time.perf_counter()-t,2))
        for _ in range(3):
            r=c.post('/dialogues/'+d['id']+'/messages',json={'text':project,'revision':d['revision']});r.raise_for_status();d=r.json()
            assert not d.get('redirect'),d
            if d['phase']=='cases':break
        assert d['phase']=='cases' and not c.get('/profile').json()['profile']['confirmed_grade'];rpt['checks'].append('project_alone_never_assigns_grade')
        print(json.dumps({'progress':'project_complete','role':spec,'grade':grade,'project_decision':d['project_result']['decision']},ensure_ascii=False),flush=True)
        t=time.perf_counter();r=c.post('/dialogues/'+d['id']+'/cases');r.raise_for_status();d=r.json();rpt['latencies'].append(round(time.perf_counter()-t,2));rpt['checks'].append('generated_and_separately_reviewed')
        rpt['project_answer']=project
        print(json.dumps({'progress':'cases_reviewed','role':spec,'seconds':rpt['latencies'][-1]},ensure_ascii=False),flush=True)
        for index in range(3):
            prompt=d['cases'][index]['prompt'];assert 100<=len(prompt)<=800
            assert d['cases'][index]['reviewed'] and d['cases'][index]['evaluation'] is None
            if attacks and index==0:
                for attack in ATTACKS:
                    r=c.post('/dialogues/'+d['id']+'/messages',json={'text':attack,'revision':d['revision']});r.raise_for_status();x=r.json();assert x.get('redirect') and x['revision']==d['revision'] and x['case_index']==index
                rpt['checks'].append('case_scope_attacks_blocked')
            answer=respondent(prompt,spec,grade,style)
            rpt.setdefault('attempted_answers',[]).append({'case':prompt,'answer':answer})
            t=time.perf_counter();r=c.post('/dialogues/'+d['id']+'/messages',json={'text':answer,'revision':d['revision']});r.raise_for_status();d=r.json();rpt['latencies'].append(round(time.perf_counter()-t,2))
            assert not d.get('redirect'),d
            print(json.dumps({'role':spec,'grade':grade,'style':style,'case':index+1,'status':d['status'],'seconds':rpt['latencies'][-1]},ensure_ascii=False),flush=True)
            if index<2:assert c.get('/profile').json()['profile']['confirmed_grade'] is None
        assert d['status']=='completed' and d['case_index']==3
        rpt['dialogue']=d;rpt['profile_grade']=c.get('/profile').json()['profile']['confirmed_grade']
        expected=style=='strong'
        rpt['expected_supported']=expected
        assert (d['result']['decision']=='supported')==expected,(d['result'],d['cases'])
        assert (rpt['profile_grade']==grade)==expected
        assert c.post('/dialogues/'+d['id']+'/messages',json={'text':'Повтор ответа','revision':d['revision']}).status_code==409
        rpt['checks']+=['all_three_cases_required','terminal_idempotency','expected_grade_decision'];rpt['passed']=True
    except Exception as e:
        rpt['passed']=False;rpt['error']=str(e)
        if 'd' in locals():rpt['dialogue']=d
        print(json.dumps({'failed':spec,'grade':grade,'error':str(e)[:500]},ensure_ascii=False),flush=True)
    finally:
        path.write_text(json.dumps(rpt,ensure_ascii=False,indent=2),encoding='utf-8');c.close();cleanup(u)
    return rpt

def main():
    p=argparse.ArgumentParser();p.add_argument('--spec',default='backend_python');p.add_argument('--grade',default='middle');p.add_argument('--style',default='strong');p.add_argument('--suite',action='store_true');a=p.parse_args()
    scenarios=[(a.spec,a.grade,a.style)] if not a.suite else [('backend_python','junior','strong'),('backend_python','middle','strong'),('backend_python','senior','strong'),('frontend_development','middle','strong'),('lead_engineering','senior','strong'),('head_platform','senior','strong'),('director_engineering','senior','strong'),('executive_cto','senior','strong'),('executive_ciso','senior','strong'),('backend_python','middle','weak'),('backend_python','senior','junior'),('lead_engineering','senior','weak')]
    reports=[run(*scenario,attacks=i==0) for i,scenario in enumerate(scenarios)]
    out={'passed':all(x['passed'] for x in reports),'runs':reports,'independent_validation':False,'source_sha256':{name:hashlib.sha256((ROOT/name).read_bytes()).hexdigest() for name in ['src/interview.rs','src/cases.rs']}}
    (ROOT/'validation/reports/current/project-case-results.json').write_text(json.dumps(out,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps({'passed':out['passed'],'scenarios':len(reports)},ensure_ascii=False));sys.exit(0 if out['passed'] else 1)
if __name__=='__main__':main()
