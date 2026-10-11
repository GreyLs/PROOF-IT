"""Professional CAT, exposure control and pilot calibration.

IRT parameters start as authored hypotheses. These estimates are separate from
the established qualification grade and cannot silently replace it.
"""
from __future__ import annotations

import hashlib
import math
import random
from collections import Counter
from functools import lru_cache

import numpy as np
from scipy.optimize import minimize

VERSION = "professional-3.0.0"
GRID = np.linspace(-4, 4, 161)
GRADES = ("junior", "middle", "senior")
TOPICS = {
    "data": ("join", "left_join", "null_count", "grouping", "window", "precision", "recall", "f1", "sampling", "train_split", "temporal_leak", "experiment", "join_filter", "missingness"),
    "engineering": ("dedup", "batch", "binary_search", "complexity", "cache", "pagination", "retry", "pool", "quorum", "availability", "latency", "throughput", "backlog", "slo", "outbox", "partitions", "atomicity", "fencing", "deadlock", "lost_update", "cursor", "jwt", "xss", "async"),
    "delivery": ("capacity", "critical_path", "budget", "conversion", "retention", "rollback", "coverage", "mutation", "risk", "priority", "consent", "release", "leadership", "evaluation"),
}
FAMILIES = tuple(topic for values in TOPICS.values() for topic in values)

DECISIONS = {
 "atomicity": ("Платёж закоммичен, но процесс упал до публикации события. Как сохранить гарантию доставки без общей транзакции БД и брокера?", "Сохранить outbox в транзакции платежа и публиковать повторяемым relay", ["Публиковать событие перед коммитом и не делать повтор", "Логировать только в памяти процесса", "Считать HTTP 200 доказательством доставки события"]),
 "fencing": ("Lease задачи истёк, новый worker начал работу, а старый ещё завершает запись. Как исключить устаревший результат?", "Проверять monotonically increasing fencing token при записи результата", ["Проверять только PID старого worker", "Продлить timeout HTTP без проверки владельца", "Принимать последний пришедший ответ независимо от lease"]),
 "deadlock": ("Две транзакции блокируют A→B и B→A и периодически образуют deadlock. Как устранить цикл ожидания?", "Установить единый порядок блокировок и повторять откатившуюся транзакцию", ["Скрыть ошибку и считать обе операции успешными", "Удалить ограничения целостности", "Держать блокировки во время внешнего HTTP-вызова"]),
 "lost_update": ("Два запроса прочитали одну версию резюме и сохраняют разные изменения. Как явно предотвратить lost update?", "Обновлять с WHERE version=expected и проверять число изменённых строк", ["Всегда принимать последнее сохранение", "Добавить задержку в браузер", "Обновлять timestamp без проверки версии"]),
 "cursor": ("Во время листания ленты добавляются новые записи. Как избежать повторов из-за смещения offset?", "Использовать cursor по стабильной паре created_at,id", ["Каждый раз начинать с OFFSET 0", "Сортировать только по неуникальному имени", "Удалять увиденные записи из общей таблицы"]),
 "jwt": ("В JWT пришёл заголовок alg=none. Как должен действовать сервер проверки подписанного токена?", "Отклонить токен и использовать заранее разрешённый алгоритм и ключ", ["Довериться указанному в токене алгоритму", "Проверить только exp", "Разрешить none для любого известного issuer"]),
 "xss": ("Текст пользователя содержит <img onerror=...>. Как безопасно показать его в карточке?", "Отрисовать как текст; для ограниченного HTML использовать отдельную allowlist-санитизацию", ["Передать напрямую в innerHTML", "Удалить только слово script", "Разрешить любые inline event handlers"]),
 "async": ("Несколько независимых API-запросов нужны для экрана; часть может вернуть ошибку. Как собрать все результаты и ошибки?", "Использовать Promise.allSettled и обработать статус каждого результата", ["Запустить promises без ожидания и всегда показать успех", "Заменить async-функции синхронным циклом ожидания", "Игнорировать rejected promise"]),
 "temporal_leak": ("Прогнозируем срок закрытия вакансии на день публикации. В признаках есть дата принятого оффера. Как устранить leakage?", "Исключить сведения после момента прогноза и разделить выборки по времени", ["Разрешить признак, если растёт R²", "Добавить случайный seed и оставить признак", "Смешать будущие события во все fold"]),
 "experiment": ("Улучшенный подбор проверяют на разных ролях и грейдах. Как оценить эффект без перекоса состава групп?", "Рандомизировать и стратифицировать по роли/грейду, заранее определить метрику", ["Сравнить новые senior-профили со старыми junior", "Выбрать только пользователей с положительным исходом", "После эксперимента оставить только выгодные сегменты"]),
 "join_filter": ("LEFT JOIN должен сохранить счета без событий. Куда поместить фильтр по времени событий?", "В условие ON либо в предварительно отфильтрованный подзапрос правой таблицы", ["В WHERE правой таблицы без условия NULL", "В ORDER BY", "В HAVING COUNT(*)>0 для всех счетов"]),
 "missingness": ("Часть профилей не содержит зарплатных ожиданий. Как обработать их для модели с контролем качества?", "Разделить отсутствие и нулевую сумму, задать missing indicator и проверить сегмент", ["Считать отсутствие доказанной зарплатой 0", "Удалить все такие профили без аудита", "Заполнить ожидаемой целевой меткой"]),
 "consent": ("Кандидат отозвал согласие на раскрытие контактов компании. Что должно произойти с новым API-чтением?", "Немедленно запретить контакты и сохранить событие отзыва", ["Сохранить доступ до истечения общего cache TTL", "Открыть контакты всем компаниям", "Удалить только кнопку на фронтенде"]),
 "release": ("Canary повышает error rate сверх заранее определённого порога. Какое действие соответствует безопасному rollout?", "Остановить расширение, откатить canary и проверить причинность по журналам", ["Увеличить долю до 100% для накопления ошибок", "Понизить порог задним числом", "Удалить метрики до завершения выпуска"]),
 "leadership": ("Разработчик знает весь стек Team Lead, но не описал управление командой. Как оценить лидерские доказательства?", "Отдельно запросить решения об ответственности, команде и результате; не выводить leadership из стека", ["Назначить Team Lead только по количеству технологий", "Угадать психологический тип по фамилии", "Засчитать автоматический senior-статус как опыт руководства"]),
 "evaluation": ("Тесты исполняют 99% строк, но пропускают ошибки в граничных условиях. Чем дополнить оценку качества тестов?", "Mutation testing и независимыми примерами граничных бизнес-инвариантов", ["Числом комментариев в тестах", "Только увеличением числа повторов того же assert", "Скрытием неудачных прогонов"]),
}


def _problem(family, tier, rng):
    a, b, c = rng.randint(3, 25), rng.randint(2, 12), rng.randint(1, 8)
    n = a * b + c
    if family == "join":
        return f"У {a} заказов по {b} строк. Для {c} заказов добавлены ещё 2 строки. Сколько строк вернёт INNER JOIN orders с lines?", a*b+2*c
    if family == "left_join":
        return f"В accounts {a+c} строк. У {a} счетов по {b} событий, у {c} счетов событий нет. Сколько строк вернёт LEFT JOIN до агрегации?", a*b+c
    if family == "null_count":
        return f"После LEFT JOIN получено {n} строк, в {c} строках поле event_id равно NULL. Каков COUNT(event_id)?", n-c
    if family == "grouping":
        return f"Таблица содержит {n} строк и {a} различных account_id. Сколько строк вернёт GROUP BY account_id без HAVING?", a
    if family == "window":
        return f"Есть {a} ключей событий, каждый имеет {b} версий, и ещё {c} уникальных ключей. Сколько строк останется после ROW_NUMBER PARTITION BY key и rn=1?", a+c
    if family in ("precision", "recall", "f1"):
        tp, fp, fn = a*b, a+c, b+c
        value = tp/(tp+fp) if family=="precision" else tp/(tp+fn) if family=="recall" else 2*tp/(2*tp+fp+fn)
        return f"TP={tp}, FP={fp}, FN={fn}. Чему равна {family} в процентах? Округлите до ближайшего целого (0,5 вверх).", math.floor(100*value+.5)
    if family == "sampling":
        return f"В стратифицированной выборке нужно сохранить долю {b}% сегмента. Итоговая выборка — {a*100} наблюдений. Сколько наблюдений относится к сегменту?", a*b
    if family == "train_split":
        return f"Во временном holdout последние {b}% из {a*100} событий оставлены для проверки. Сколько событий останется для обучения?", a*(100-b)
    if family == "dedup":
        return f"Получено {a} различных idempotency_key по {b} раз и ещё {c} новых ключей. Сколько побочных эффектов допускает inbox с UNIQUE(key)?", a+c
    if family == "batch":
        return f"Нужно обработать {n} записей пакетами не более {b}. Сколько пакетов потребуется, включая неполный?", math.ceil(n/b)
    if family == "binary_search":
        power = b + tier
        return f"Отсортированный массив содержит {2**power} элементов. Сколько раз нужно разделить диапазон пополам, чтобы остался один элемент?", power
    if family == "complexity":
        return f"Два вложенных цикла выполняют {a+tier} и {b+tier} итераций. Внутри — одна операция, затем вне циклов ещё {c}. Сколько операций выполнится?", (a+tier)*(b+tier)+c
    if family == "cache":
        return f"Из {n*10} запросов {a*b*10} обслужены cache, остальные идут в origin. Сколько origin-запросов произошло?", c*10
    if family == "pagination":
        return f"Всего {n} записей. Cursor-page содержит не более {b} записей. Сколько непустых страниц нужно получить?", math.ceil(n/b)
    if family == "retry":
        return f"Backoff начинается с {a} мс и удваивается после отказа. Верхняя граница {a*4} мс. Какова суммарная задержка для первых {4+tier} повторов?", sum(min(a*2**i,a*4) for i in range(4+tier))
    if family == "pool":
        return f"{a} реплик держат по {b} соединений с БД; budget upstream равен {a*b+c}. Сколько соединений свободно?", c
    if family == "quorum":
        replicas=2*c+1
        return f"Для кворума требуется строгое большинство из {replicas} реплик. Сколько ответов нужно получить?", c+1
    if family == "availability":
        return f"В месячном окне {a*1000} минут сервис недоступен {a*c} минут. Сколько составляет доступность в промилле?", 1000-c
    if family == "latency":
        values=sorted(rng.randint(10,300) for _ in range(20+tier*10))
        return f"Задержки в мс: {values}. Найдите p95 методом nearest rank: позиция ceil(0,95×N), нумерация с 1.", values[math.ceil(.95*len(values))-1]
    if family == "throughput":
        return f"За {b} секунд обработано {a*b} запросов. Какова средняя пропускная способность в запросах/с?", a
    if family == "backlog":
        return f"В backlog {a*b} задач. Новых задач нет. Worker исполняет {b} задач/с. Сколько секунд нужно без учёта startup?", a
    if family == "slo":
        return f"В окне {a*1000} запросов допускается {c} ошибок на 1000. Уже было {a*c-b} ошибок. Сколько ошибок осталось в budget?", b
    if family == "outbox":
        return f"Транзакционно записано {a} outbox-событий. Relay доставил каждое {b} раз, получатель дедуплицирует id. Сколько уникальных уведомлений должен увидеть пользователь?", a
    if family == "partitions":
        return f"{a} partitions распределены поровну между {b} consumers с округлением вверх для самого загруженного. Сколько partitions максимум у одного consumer?", math.ceil(a/b)
    if family == "capacity":
        return f"В команде {c+2} человек по {a} часов. Резерв на сопровождение {b} часов на каждого. Сколько часов доступно для новых задач?", (c+2)*max(0,a-b)
    if family == "critical_path":
        return f"После общей задачи A ({a} дней) параллельно идут B ({b} дней) и C ({c} дней). Затем D ({tier+1} дней). Какова минимальная длительность проекта?", a+max(b,c)+tier+1
    if family == "budget":
        return f"Есть бюджет {a*10000} ₽. Уже занято {b*1000} ₽; новый слот стоит {c*1000} ₽. Сколько полных слотов можно добавить без превышения бюджета?", max(0,(a*10000-b*1000)//(c*1000))
    if family == "conversion":
        return f"Из {a*100} заинтересованных кандидатов {a*b} приняли приглашение. Какова конверсия в процентах?", b
    if family == "retention":
        return f"В когорте {a*100} пользователей; через месяц осталось {a*(100-b)}. Какова retention в процентах?", 100-b
    if family == "rollback":
        return f"Canary выпущен на {a*b} запросов и дал {a*c} ошибок. Порог rollback — {b} ошибок. На сколько ошибок превышен порог (минимум 0)?", max(0,a*c-b)
    if family == "coverage":
        return f"Исполнено {a*(100-b)} из {a*100} строк кода. Каков line coverage в процентах?", 100-b
    if family == "mutation":
        equivalent=min(c,b-1);killed=a*(b-equivalent-1)
        return f"Создано {a*b} мутаций, {a*equivalent} признаны эквивалентными, из оставшихся убито {killed}. Найдите mutation score в процентах, округлив 0,5 вверх.", math.floor(100*killed/(a*(b-equivalent))+.5)
    if family == "risk":
        return f"Риск имеет вероятность {b}% и ущерб {a*10000} ₽. Каков ожидаемый ущерб в ₽?", a*b*100
    if family == "priority":
        return f"RICE: reach={a*b}, impact={c}, confidence=1, effort={b}. Чему равен приоритет?", a*c
    raise ValueError("family")


def _domain(spec):
    if any(x in spec for x in ("data", "ml", "analyst")): return "data"
    if any(x in spec for x in ("lead", "head", "cto", "product", "project", "manager", "qa")): return "delivery"
    return "engineering"


def item(family, tier, seed):
    digest=int(hashlib.sha256(f"{family}:{tier}:{seed}".encode()).hexdigest()[:16],16)
    rng=random.Random(digest)
    if family in DECISIONS:
        prompt,value,wrong=DECISIONS[family]
        context=f"Сценарий {rng.randrange(1000,9999)}: {rng.randint(2,8)} реплик, {rng.randint(20,900)} операций/мин. "
        options=[value,*wrong];rng.shuffle(options)
        topic=next(group for group,values in TOPICS.items() if family in values)
        return {"id":f"{family}:{tier}","family":family,"topic":topic,"tier":tier,"prompt":context+prompt,"options":options,"correct":options.index(value),"answer_value":value,"a":1.25,"b":0.0,"c":.25,"status":"authored","time_limit_seconds":105}
    prompt, value=_problem(family,tier,rng)
    alternatives={value}
    deltas=[-max(1,abs(value)//3),-1,1,2,max(2,abs(value)//2)]
    rng.shuffle(deltas)
    for delta in deltas:
        if len(alternatives)==4: break
        alternatives.add(value+delta)
    options=sorted(alternatives);rng.shuffle(options)
    topic=next(group for group,values in TOPICS.items() if family in values)
    return {"id":f"{family}:{tier}","family":family,"topic":topic,"tier":tier,"prompt":prompt,"options":[str(v) for v in options],"correct":options.index(value),"answer_value":value,"a":1.25+.15*tier,"b":(-1.3,.0,1.3)[tier],"c":.25,"status":"authored","time_limit_seconds":75+30*tier}


def create(payload):
    mode=payload.get("mode","full")
    if mode not in ("express","full"): raise ValueError("mode")
    spec=payload.get("specialization","backend_python")
    if not isinstance(spec,str) or len(spec)>80: raise ValueError("specialization")
    seed=int(payload["seed"])
    primary=_domain(spec)
    blocked=set(payload.get("quarantined",[]))
    bank=[item(f,t,seed) for f in FAMILIES for t in range(3) if f not in blocked]
    # Include core engineering/data reasoning while prioritising the target area.
    for q in bank:
        q["priority"]=1.3 if q["topic"]==primary else .85
        q["exposure"]=int(payload.get("exposure",{}).get(q["id"],0))
    if len(bank)<3*(8 if mode=="express" else 20): raise ValueError("insufficient_bank")
    from intelligence.item_bank import FAMILIES as ROLE_FAMILIES,render,groups
    role_groups=groups(spec)
    for group in role_groups:
        for family in ROLE_FAMILIES[group]:
            if family in blocked:continue
            for tier in range(3):
                q=render(family,tier,seed);q['priority']=2.8;q['exposure']=int(payload.get('exposure',{}).get(q['id'],0));bank.append(q)
    pilots=[]
    for p in payload.get("pilots",[])[:12]:
        q=validate_draft(p)
        active=p.get("status")=="active" and bool(p.get("calibration"))
        fit=p.get("calibration") or {"a":1.,"b":0.,"c":.25}
        q.update(id=p["id"],family=p["id"],topic=primary if active else "pilot",tier=1,pilot=not active,a=fit["a"],b=fit["b"],c=.25,priority=.9 if active else .5,exposure=0,time_limit_seconds=120,status="pilot_estimate" if active else "pilot")
        pilots.append(q)
    bank.extend(pilots)
    variant=payload.get("form_variant","A")
    if variant not in ("A","B"):raise ValueError("form_variant")
    independent_forms=payload.get('independent_forms',False)
    if type(independent_forms) is not bool:raise ValueError('independent_forms')
    anchors=[]
    for q in bank:
        if sum(q["family"].encode())%4==0:
            anchors.append(q["family"]);continue
        if variant=="B":
            if independent_forms and q.get('status')=='authored':
                # Different task parameters, not merely a cosmetic option shuffle.
                # Anchors above remain byte-identical; pilots never become scored
                # alternate items through this mechanism.
                replacement=(item(q['family'],q['tier'],seed+1_000_003)
                             if q['family'] in FAMILIES else render(q['family'],q['tier'],seed+1_000_003))
                q.update({key:value for key,value in replacement.items()
                          if key not in ('priority','exposure')})
            order=list(range(len(q["options"])))
            random.Random("parallel-B:"+q["id"]).shuffle(order)
            q["options"]=[q["options"][i] for i in order];q["correct"]=order.index(q["correct"])
    form={"version":"training-surface-v1","variant":variant,"anchor_families":sorted(set(anchors)),"method":"same construct; randomized option surface; shared anchors","certificate_activation":False}
    if independent_forms:
        form.update(version='role-parameter-forms-v1',method='alternate authored task parameters; byte-identical shared anchors; counterbalanced prospective study',psychometric_equivalence_established=False)
    return {"version":VERSION,"kind":"professional","mode":mode,"specialization":spec,"seed":seed,"bank":bank,"answers":[],"events":[],"revision":0,"max_questions":8 if mode=="express" else 32,"minimum_questions":8 if mode=="express" else 20,"primary_topic":primary,"role_groups":role_groups,"parallel_form":form}


def probability(theta,q):
    return q["c"]+(1-q["c"])/(1+np.exp(-q["a"]*(np.asarray(theta)-q["b"])))


def estimate(contract):
    logw=-.5*GRID**2
    lookup={q["id"]:q for q in contract["bank"]}
    for a in contract["answers"]:
        q=lookup[a["question_id"]]
        if q.get("pilot"): continue
        p=np.clip(probability(GRID,q),1e-9,1-1e-9)
        logw+=np.log(p if a["correct"] else 1-p)
    weights=np.exp(logw-logw.max());weights/=weights.sum()
    theta=float(weights@GRID);se=float(np.sqrt(weights@((GRID-theta)**2)))
    probs={"junior":float(weights[GRID<-.5].sum()),"middle":float(weights[(GRID>=-.5)&(GRID<1)].sum()),"senior":float(weights[GRID>=1].sum())}
    return theta,se,probs,weights


def next_item(contract):
    theta,se,_,_=estimate(contract)
    answers=contract["answers"];used={x["question_id"] for x in answers}
    scoring=sum(not x.get("pilot",False) for x in answers)
    if scoring>=contract["max_questions"] or scoring>=contract["minimum_questions"] and se<=.38: return None
    candidates=[q for q in contract["bank"] if q["id"] not in used]
    if not candidates: return None
    if contract["mode"]=="full" and scoring==8 and not any(a.get("pilot") for a in answers):
        pilot=next((q for q in candidates if q.get("pilot")),None)
        if pilot:return pilot
    candidates=[q for q in candidates if not q.get("pilot")]
    counts=Counter(x["topic"] for x in answers if not x.get("pilot"))
    families=Counter(x["family"] for x in answers)
    def utility(q):
        s=1/(1+math.exp(-q["a"]*(theta-q["b"])))
        p=q["c"]+(1-q["c"])*s
        information=((1-q["c"])*q["a"]*s*(1-s))**2/max(1e-9,p*(1-p))
        return information*q["priority"]/(1+.25*counts[q["topic"]])/(1+1.5*families[q["family"]])/(1+.03*q["exposure"])
    # A family can appear only once in an attempt; changing tier is not a new
    # independent item and must not manufacture information or reliability.
    candidates=[q for q in candidates if not families[q["family"]]]
    if not candidates:return None
    group_counts=Counter(x['topic'] for x in answers)
    deficient=[g for g in contract.get('role_groups',[]) if group_counts[g]<min(4,1+scoring//4)]
    focused=[q for q in candidates if q['topic'] in deficient]
    ranked=sorted(focused or candidates,key=lambda q:(-utility(q),q["id"]))
    # Randomesque top-4 reduces identical paths while preserving information.
    rng=random.Random(f"{contract['seed']}:{len(answers)}")
    return ranked[rng.randrange(min(4,len(ranked)))]


def result(contract):
    theta,se,probs,_=estimate(contract)
    answers=contract["answers"]
    domains={}
    for topic in set(TOPICS)|set(contract.get('role_groups',[])):
        values=[x for x in answers if x["topic"]==topic]
        domains[topic]={"answered":len(values),"correct":sum(x["correct"] for x in values)}
    scored=[a for a in answers if not a.get("pilot")]
    flags=[]
    if len(scored)>=8 and sum(x["elapsed_ms"]<800 and x["correct"] for x in scored)>=6: flags.append("rapid_correct_sequence")
    if sum(x.get("count",1) for x in contract.get("events",[]) if x["kind"]=="visibility_hidden")>=4:flags.append("repeated_focus_loss")
    if any(x.get("timed_out") for x in scored):flags.append("time_limit_reached")
    from intelligence.response_patterns import analyze
    patterns=analyze({'answers':answers})
    flags=list(dict.fromkeys(flags+[x['kind'] for x in patterns['signals']]))
    return {"version":VERSION,"mode":contract["mode"],"theta":round(theta,4),"standard_error":round(se,4),"grade_probabilities":{k:round(v,5) for k,v in probs.items()},"suggested_grade":max(probs,key=probs.get),"answered":len(answers),"scored_questions":len(scored),"correct":sum(x["correct"] for x in scored),"domains":domains,"review_flags":flags,"grade_changed":False,"parameter_status":"authored-or-pilot","review_required":bool(flags),"response_pattern_review":patterns,"parallel_form":contract.get("parallel_form"),"professional_role_certified":False,"score":round(100*sum(x["correct"] for x in scored)/max(1,len(scored)),1)}


def public(contract):
    q=next_item(contract)
    qpublic={k:q[k] for k in ("id","prompt","options","topic","time_limit_seconds")} if q else None
    return {"version":VERSION,"kind":"professional","mode":contract["mode"],"specialization":contract["specialization"],"answered":len(contract["answers"]),"max_questions":contract["max_questions"],"question":qpublic,"result":result(contract) if q is None else None}


def step(payload):
    contract=payload["contract"]
    q=next_item(contract)
    if q is None or q["id"]!=payload["question_id"]:raise ValueError("stale_question")
    answer=payload.get("answer")
    if isinstance(answer,bool) or not isinstance(answer,int) or answer not in range(len(q["options"])):raise ValueError("answer")
    elapsed=int(payload["elapsed_ms"])
    if elapsed<0:raise ValueError("elapsed_ms")
    theta,_,_,_=estimate(contract)
    response={"question_id":q["id"],"family":q["family"],"topic":q["topic"],"correct":answer==q["correct"] and elapsed<=q["time_limit_seconds"]*1000,"timed_out":elapsed>q["time_limit_seconds"]*1000,"elapsed_ms":elapsed,"pilot":q.get("pilot",False),"theta_before":theta,"expected_correct":float(probability(theta,q)),"answer":answer}
    updated={**contract,"answers":[*contract["answers"],response]}
    completed=next_item(updated) is None
    return {"contract":updated,"public":public(updated),"result":result(updated) if completed else None,"completed":completed,"observation":response}


def validate_draft(payload):
    prompt=payload.get("prompt","")
    options=payload.get("options",[])
    correct=payload.get("correct")
    if not isinstance(prompt,str) or not 30<=len(prompt)<=3000:raise ValueError("prompt")
    if not isinstance(options,list) or len(options)!=4 or len(set(options))!=4 or any(not isinstance(v,str) or not 1<=len(v)<=500 for v in options):raise ValueError("options")
    if isinstance(correct,bool) or not isinstance(correct,int) or correct not in range(4):raise ValueError("correct")
    from worker.workbench import redact
    if redact(prompt)!=prompt or any(redact(v)!=v for v in options):raise ValueError("personal_data")
    rationale=payload.get("rationale","")
    if not isinstance(rationale,str) or len(rationale)>2000:raise ValueError("rationale")
    return {"prompt":prompt,"options":options,"correct":correct,"rationale":redact(rationale)}


def calibrate(payload):
    bins=payload["bins"]
    total=sum(int(x["total"]) for x in bins)
    occupied=[x for x in bins if x["total"]>=10]
    if total<120 or len(occupied)<3:raise ValueError("insufficient_pilot")
    theta=np.array([x["theta"] for x in bins]);n=np.array([x["total"] for x in bins]);k=np.array([x["correct"] for x in bins])
    if np.any(k<0) or np.any(k>n) or np.any(n<0):raise ValueError("bins")
    def loss(params):
        p=np.clip(.25+.75/(1+np.exp(-params[0]*(theta-params[1]))),1e-6,1-1e-6)
        return -float((k*np.log(p)+(n-k)*np.log(1-p)).sum())+.5*((params[0]-1.3)**2+params[1]**2)
    fit=minimize(loss,[1.3,0.],bounds=[(.4,3.5),(-3.5,3.5)],method="L-BFGS-B")
    if not fit.success:raise ValueError("calibration_fit")
    return {"a":round(float(fit.x[0]),5),"b":round(float(fit.x[1]),5),"c":.25,"responses":total,"occupied_bins":len(occupied),"negative_log_likelihood":round(float(fit.fun),4),"status":"pilot_estimate","activation_requires_expert":True}


def catalog(_):
    from intelligence.item_bank import FAMILIES as ROLE_FAMILIES
    count=len(FAMILIES)+sum(len(v) for v in ROLE_FAMILIES.values())
    return {"version":VERSION,"families":count,"difficulty_forms":count*3,"topics":{k:len(v) for k,v in TOPICS.items()},"express_questions":8,"full_questions":"20–32","parameter_status":"authored; pilot estimates require review"}
