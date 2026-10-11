"""Role-specific executable mini-cases with deterministic parameter oracles."""
import hashlib,random

FAMILIES={
 'python':('py_slice','py_alias','py_defaults','py_filter','py_counts','py_bounds'),
 'sql':('sql_where','sql_null','sql_having','sql_rank','sql_distinct','sql_left'),
 'typescript':('ts_filter','ts_map','ts_reduce','ts_nullish','ts_slice','ts_unique'),
 'quality':('qa_boundaries','qa_pairs','qa_mutation','qa_retries'),
 'operations':('ops_capacity','ops_quorum','ops_availability','ops_backlog'),
 'leadership':('lead_capacity','lead_budget','lead_wip','lead_path'),
}

def render(family,tier,seed):
 rng=random.Random(int(hashlib.sha256(f'{family}:{tier}:{seed}'.encode()).hexdigest()[:16],16))
 n=rng.randint(4,9)+2*tier;a=rng.randint(2,9);b=rng.randint(2,8)
 values=[rng.randint(-3,12) for _ in range(n)]
 if family=='py_slice':prompt=f'Python: values={values}. Чему равен sum(values[1:{n-1}:2])?';answer=sum(values[1:n-1:2])
 elif family=='py_alias':prompt=f'Python: a=[{a}]; alias=a; copy=a.copy(); alias.extend(range({b})); copy.extend(range({n})); чему равна сумма len(a)+len(alias)+len(copy)?';answer=3+2*b+n
 elif family=='py_defaults':prompt=f'Python: def add(x, bag=[]): bag.append(x); return len(bag). Выполнены {a} вызовов add(1), затем {b} вызовов add(1, []); какое число вернёт следующий add(1)?';answer=a+1
 elif family=='py_filter':prompt=f'Python: values={values}. Чему равен sum(x*x for x in values if x%2==0 and x>0)?';answer=sum(x*x for x in values if x%2==0 and x>0)
 elif family=='py_counts':prompt=f'Python: keys={values}. Словарь counts считает каждое значение. Сколько различных ключей будет после полного прохода?';answer=len(set(values))
 elif family=='py_bounds':prompt=f'Python: sum(range({a}, {a+n}, {b})). Найдите результат; правая граница range не включается.';answer=sum(range(a,a+n,b))
 elif family=='sql_where':prompt=f'SQL: таблица t(x) содержит {values}. Найдите SUM(x) WHERE x>{a}.';answer=sum(x for x in values if x>a)
 elif family=='sql_null':prompt=f'SQL: {n} строк, поле amount у {a%n} строк равно NULL. Сколько вернёт COUNT(amount)?';answer=n-a%n
 elif family=='sql_having':prompt=f'SQL: группам A/B/C принадлежат {a}, {b}, {n} строк. SELECT key FROM t GROUP BY key HAVING COUNT(*)>{b}. Сколько строк в результате?';answer=sum(x>b for x in (a,b,n))
 elif family=='sql_rank':prompt=f'SQL: scores={values}. Каков максимальный DENSE_RANK() OVER(ORDER BY score DESC)?';answer=len(set(values))
 elif family=='sql_distinct':prompt=f'SQL: значения x={values}. Что вернёт COUNT(DISTINCT x)?';answer=len(set(values))
 elif family=='sql_left':prompt=f'SQL: {a} клиентов имеют по {b} заказов, ещё {n} клиентов без заказов. Сколько строк возвращает LEFT JOIN clients ON orders.client_id=clients.id?';answer=a*b+n
 elif family=='ts_filter':prompt=f'TypeScript: const xs={values}; xs.filter(x=>x>{a}).length. Найдите результат.';answer=sum(x>a for x in values)
 elif family=='ts_map':prompt=f'TypeScript: const xs={values}; xs.map(x=>x*{a}).reduce((s,x)=>s+x,0). Найдите результат.';answer=sum(values)*a
 elif family=='ts_reduce':prompt=f'TypeScript: const xs={values}; xs.reduce((s,x)=>s+Math.max(x,0),{b}). Найдите результат.';answer=b+sum(max(0,x) for x in values)
 elif family=='ts_nullish':
  b=rng.randint(2,500);prompt=f'TypeScript: const a=0; const b={b}; чему равно (a ?? b)+(a || b)?';answer=b
 elif family=='ts_slice':prompt=f'TypeScript: массив из {n} элементов; xs.slice({a%n},{n}).length. Найдите результат.';answer=n-a%n
 elif family=='ts_unique':prompt=f'TypeScript: const xs={values}; new Set(xs).size. Найдите результат.';answer=len(set(values))
 elif family=='qa_boundaries':
  width=rng.randint(1,4);prompt=f'Поле допускает целые значения от {a} до {a+width} включительно. Для граничной проверки берут min-1,min,min+1,max-1,max,max+1. Сколько уникальных значений проверяется?';answer=len({a-1,a,a+1,a+width-1,a+width,a+width+1})
 elif family=='qa_pairs':prompt=f'Проверяются все сочетания {a} браузеров и {b} форматов документа. Сколько тестов содержит полное декартово покрытие?';answer=a*b
 elif family=='qa_mutation':prompt=f'{n*10} мутантов, {a} эквивалентны, {b} выжили. Сколько неэквивалентных мутантов убито тестами?';answer=n*10-a-b
 elif family=='qa_retries':prompt=f'Первый запуск и до {a} повторов каждого из {b} тестов. Каково максимальное число запусков?';answer=(a+1)*b
 elif family=='ops_capacity':prompt=f'{a} реплик обслуживают по {b*100} RPS. Потеряна одна реплика; резерв 20% от оставшейся ёмкости. Каков допустимый RPS?';answer=(a-1)*b*80
 elif family=='ops_quorum':
  a=rng.randint(2,31);prompt=f'Кластер из {2*a+1} узлов требует строгого большинства для записи. Сколько отказов он выдерживает, сохраняя кворум?';answer=a
 elif family=='ops_availability':prompt=f'Три последовательных сервиса имеют бюджеты простоя {a}, {b}, {n} минут. Без перекрытия отказов найдите общий бюджет простоя.';answer=a+b+n
 elif family=='ops_backlog':prompt=f'Очередь содержит {n*100} сообщений. Поступает {a} в секунду, обрабатывается {a+b} в секунду. За сколько секунд очередь опустеет? Округлите вверх.';answer=(n*100+b-1)//b
 elif family=='lead_capacity':prompt=f'{a} инженеров доступны по {b} часов. Обязательные работы занимают {n} часов. Сколько часов остаётся для плановой поставки?';answer=a*b-n
 elif family=='lead_budget':prompt=f'Месячный бюджет {n*100000} ₽. Уже распределено {a*10000} ₽ и резерв {b*10000} ₽. Найдите свободный бюджет.';answer=n*100000-a*10000-b*10000
 elif family=='lead_wip':prompt=f'Средний throughput {a} задач в неделю, среднее время цикла {b} недель. По закону Литтла найдите средний WIP.';answer=a*b
 elif family=='lead_path':prompt=f'После задачи A ({a} дней) параллельно идут B ({b} дней) и C ({n} дней); затем D (2 дня). Найдите длительность критического пути.';answer=a+max(b,n)+2
 else:raise ValueError('family')
 alternatives={answer};deltas=[-1,1,-a,a,-b,b,-max(2,abs(answer)//2),max(2,abs(answer)//2)]
 rng.shuffle(deltas)
 for d in deltas:
  alternatives.add(answer+d)
  if len(alternatives)==4:break
 options=sorted(alternatives);rng.shuffle(options)
 group=next(k for k,v in FAMILIES.items() if family in v)
 skill={'python':'Python','sql':'SQL','typescript':'TypeScript','quality':'Testing','operations':'DevOps','leadership':'Leadership'}[group]
 return {'id':f'{family}:{tier}','family':family,'topic':group,'skill':skill,'tier':tier,'prompt':prompt,'options':[str(x) for x in options],'correct':options.index(answer),'answer_value':answer,'a':1.2,'b':(-.8,0,.8)[tier],'c':.25,'status':'authored','time_limit_seconds':120+30*tier}

def groups(spec):
 if any(k in spec for k in ('frontend','mobile')):return ('typescript','quality')
 if any(k in spec for k in ('data','analyst','ml')):return ('sql','python')
 if any(k in spec for k in ('lead','head','cto','director','manager','product','project')):return ('leadership','operations')
 if any(k in spec for k in ('devops','sre','security','architecture')):return ('operations','python')
 if 'qa' in spec:return ('quality','python')
 return ('python','sql')
