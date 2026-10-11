"""Extend the existing validation book/dossier with measured assurance evidence."""
import hashlib
import json
from pathlib import Path
import xml.etree.ElementTree as ET

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'validation/reports/current'

def extension(section):
    report=json.loads((OUT/'advanced-assurance.json').read_text(encoding='utf-8'))
    assert report['passed'] and report['reproducibility']['all_deterministic_results_equal'] is True
    suites=list(ET.parse(OUT/'advanced-assurance-tests.xml').getroot().iter('testsuite'))
    counts={key:sum(int(s.get(key,0)) for s in suites) for key in ('tests','failures','errors')}
    assert counts['failures']==counts['errors']==0
    for name,digest in report['source_sha256'].items():
        assert hashlib.sha256((ROOT/name).read_bytes()).hexdigest()==digest,name
    r=report['results'];ab=r['ab_equivalence'];mutations=r['mutation_controls']
    pct=lambda value:format(value*100,'.2f')+'%'
    number=lambda value:format(value,'.3g')
    history=list((OUT/'advanced-assurance-attempts').glob('*.json'))
    first_failed=[path for path in history if json.loads(path.read_text(encoding='utf-8')).get('passed') is False]
    methods=[['Слой','Независимый контроль','Критерий'],
        ['GraphSAGE','Перестановки узлов/рёбер; переименование; исключённые атрибуты; disconnected component','Сохранение score по объекту, неизменность входа, конечность'],
        ['Градиенты','Центральные разности независимо суммируемой scalar loss','Все 1105 координат; шаг 1e-5; допуск 2e-8'],
        ['Назначение','Полный перебор физических людей и независимые eligibility/utility','Оптимальная цель, один человек/slot, неизменность hard constraints'],
        ['Ролевая практика','Булева таблица четырёх gates; провал каждого обязательного критерия','Нельзя компенсировать отсутствие review, identity или практики'],
        ['A/B','Положительная эквивалентность, boundary-null, явный сдвиг, planned looks','TOST, α-budget, Wilson interval; без автоматического допуска'],
        ['Ledger','Настоящие Rust/PostgreSQL HTTP races и rollback','Exactly-one freeze, causal order, sealed outcome, ownership'],
        ['Чувствительность tests','Исполняемые семантические мутации','Намеренная ошибка должна приводить к отказу контракта']]
    results=[['Проверяемое свойство','Результат текущего среза','Область доказательства'],
        ['Новые pytest checks',str(counts['tests'])+' passed; 0 failures/errors','CPU + 9 live HTTP cases; повторные запуски не складываются'],
        ['GNN metamorphic',str(r['graph_metamorphic']['graphs'])+' graphs; max Δ='+number(r['graph_metamorphic']['permutation_max_absolute_error']),'400 identity/attribute и 400 disconnected controls'],
        ['Градиенты',str(r['gradient_audit']['parameters_checked'])+'/1105; max |error|='+number(r['gradient_audit']['max_absolute_gradient_error']),'Один полный численный аудит на заданной topology/weights'],
        ['Assignment',str(r['assignment_oracle']['markets'])+' markets; '+str(r['assignment_oracle']['enumerated_assignments'])+' exhaustive choices; error=0','8 резюме / 4 человека / 3 вакансии; 420 непустых optimum'],
        ['Hard constraints','0 нарушений; 0 повторных назначений человека','Независимо проверены salary, role, grade, evidence'],
        ['Ролевые gates',str(r['role_gates']['role_grade_gate_cases'])+' cases; 0 ложных подтверждений','5 coding-role matrices × 3 grades; не human psychometrics'],
        ['Proper scores',str(r['proper_scores']['probability_outcome_pairs'])+' pairs; '+str(r['proper_scores']['auc_pairwise_comparisons'])+' AUC comparisons','Brier/LogLoss/AUC/ECE; max |error|='+number(r['proper_scores']['score_max_absolute_error'])],
        ['Mutation sensitivity',str(mutations['killed'])+'/'+str(mutations['targeted_mutants'])+' killed; '+str(mutations['survived'])+' survived','Заданные семантические ошибки, не whole-repo mutation coverage'],
        ['Воспроизводимость','Два последовательных запуска: все deterministic results совпали','Сравнение включает все results; duration не объявляется детерминированным']]
    ab_rows=[['Истинный сдвиг','Принята эквивалентность','95% Wilson interval','Смысл']]
    for row in ab['conditions']:
        low,high=row['wilson_95']
        ab_rows.append([str(row['true_shift']),str(row['equivalence_acceptances'])+'/'+str(row['trials'])+' ('+pct(row['acceptance_rate'])+')',pct(low)+'–'+pct(high),
            'Мощность при одинаковой шкале' if row['true_shift']==0 else ('Boundary-null: ошибка I рода' if abs(row['true_shift'])==.2 else 'Разделённые формы: negative control')])
    sequential=ab['planned_four_looks_boundary'];coverage=r['posterior_coverage'];responses=r['response_review']
    return [
        section('13. Расширенная стратегия assurance: проверка утверждений, а не объёма тестов',
            'Новый контур построен вокруг независимых oracle, метаморфных отношений и отрицательных controls. Число зелёных тестов отдельно не принимается за качество модели: проверяется, способен ли тест отличить корректный результат от известной семантической ошибки. Seed '+str(report['protocol']['seed'])+', размеры серий, пороги и модель генерации сохранены в validation/advanced_protocol.json; текущий срез: '+report['measured_at']+'.',
            'Контрольные популяции, рынки и ответы создаются алгоритмически. Они подтверждают вычислительные контракты и поведение процедуры при заданных предпосылках, но не превращаются в результаты реальных кандидатов. Исторические workload и ranking benchmark не перезапускались: новый срез имеет отдельный протокол и не подменяет прежние измерения.', rows=methods,
            diagram=[['Fixed protocol / seed\nsource hashes / thresholds','Independent CPU oracles\nmetamorphic / exact enumeration'],['Executable semantic mutants\nnegative controls','Real Rust / PostgreSQL\nbounded races / rollback'],['Complete JSON + JUnit\nattempt history / repeat','Validation PDF\ntraceable interpretation']]),
        section('14. Фактические результаты независимых проверок',
            'Каждая строка имеет самостоятельный знаменатель. 36 500 перебранных вариантов назначения — не 36 500 пользователей; 4000 probability/outcome pairs — не 4000 реальных наймов. Связанные perturbations одного графа не учитываются как независимые популяционные наблюдения. Численные допуски и свойства проверены отдельно от качества predictive labels.',rows=results),
        section('15. Проверка A/B-процедуры на положительных, граничных и отрицательных controls',
            'Welch-TOST проверен в четырёх заранее определённых условиях: истинный сдвиг 0, +0.2, −0.2 и +0.4; по 400 независимых Monte Carlo trials. В каждой группе 240 ответов Normal с SD=0.4; margin=0.2, α=0.05. Результаты проверяют статистическую реализацию на описанном response process, а не эквивалентность ролевого банка на людях. Различие «не найдено различие» и «подтверждена заданная эквивалентность» сохранено.',
            'На самой границе эквивалентности формальный null истинный: доли 5.00% и 4.50% — ожидаемые false equivalence acceptances, а не дефект, который следует скрыть. Wilson intervals отражают неопределённость конечного числа симуляций. При сдвиге 0.4 принято 0/400; верхняя граница 95% interval не равна нулю.',rows=ab_rows),
        section('16. Planned looks, uncertainty и безопасная трактовка сигналов',
            'Для '+str(sequential['trials'])+' независимых trials на boundary shift=0.2 проверены четыре вложенных просмотра одной пары групп: n=120/160/200/240. Применён declared alpha budget α/4. Хотя бы одно ложное принятие эквивалентности получено в '+str(sequential['familywise_acceptances'])+' trials: '+pct(sequential['familywise_rate'])+'; Wilson 95% '+pct(sequential['wilson_95'][0])+'–'+pct(sequential['wilson_95'][1])+'. Четыре просмотра не складываются как четыре независимые выборки. Отдельный crafted control различает planned_looks=1 и planned_looks=20; удаление α-budget обнаруживается мутационным тестом.',
            'Beta posterior: '+str(coverage['simulations'])+' prior-predictive simulations, p~Uniform(0,1), 80 Bernoulli наблюдений на trial. Покрытие nominal 90% credible interval = '+pct(coverage['observed_coverage'])+'; Wilson 95% '+pct(coverage['coverage_wilson_95'][0])+'–'+pct(coverage['coverage_wilson_95'][1])+'. Это математическая согласованность prior-predictive модели, не доказательство полевой калибровки вероятности согласия.',
            'Screening: по '+str(responses['profiles_per_class'])+' authored profiles в каждой группе. Clean timings имеют lognormal median 6500 ms / σ=0.9; rapid/constant control — 24 правильных ответа по 100 ms при expected_correct=0.25. Доли review: '+pct(responses['authored_clean_review_rate'])+' и '+pct(responses['rapid_constant_review_rate'])+'; automatic sanctions = 0. Верхняя Wilson граница clean-review rate: '+pct(responses['clean_review_wilson_95'][1])+'. Такие controls проверяют маршрутизацию на независимый разбор, а не подтверждают «100% обнаружение мошенничества».'),
        section('17. Мутационный анализ: тесты обнаруживают намеренно нарушенную семантику',
            '13 явно специфицированных mutants исполняются в отдельных Python namespace в памяти. Производственные исходники, веса и работающие процессы не меняются. Мутации охватывают denominator posterior, нижнюю Fréchet boundary, AND→OR hard gates, physical-person grouping, цену недопустимого assignment, all→any role conditions, minimum sample, planned alpha, silent activation, automatic accusation, Brier, AUC ties и нормализацию graph relations.',
            'Текущий результат: '+str(mutations['killed'])+'/'+str(mutations['targeted_mutants'])+' обнаружены. В первом диагностическом срезе один control не обнаруживал ошибку нижней Fréchet boundary: пары marginals были взаимодополняющими и не проверяли положительную нижнюю границу. Добавлена несимметричная контрольная серия; production метод не исправлялся, поскольку ошибочным был только специально внесённый mutant. Первый failed artifact сохранён; число archived failed attempts: '+str(len(first_failed))+'. Это наблюдаемая обратная связь о качестве самих тестов, а не выбор только удобных запусков.',
            'Killing rate относится исключительно к указанным 13 mutations. Он не объявляется coverage всей кодовой базы. Все типы исключений, выявившие нарушение, сохранены в rows; успешное выполнение немодифицированных controls является обязательным условием интерпретации.'),
        section('18. Конкурентный и транзакционный контроль настоящего ledger',
            'Девять новых live HTTP cases работают с настоящими Rust handlers и PostgreSQL на синтетических scoped fixtures. Восемь одновременных попыток freeze одной пары дают ровно один 200 и семь 409, с одной записью в БД. В шести отдельных races freeze конкурирует с первым намерением кандидата: допустим либо снимок раньше обоих решений, либо отказ 409 без записи. Клиент не задаёт server timestamp и вероятность.',
            'После фиксации парного outcome 12 конкурентных смен намерений с четырьмя worker threads не переписывают первый outcome. Экспорт ограничен владельцем; кандидат не получает employer validation export. Недопустимый UPDATE вызывает PostgreSQL immutable trigger; транзакция откатывается, данные совпадают с исходным снимком, а следующий authorized freeze другой стадии успешно выполняется. Проверка не исчерпывает все возможные schedules и не называется формальным доказательством distributed linearizability.',
            'Все записи создаются в disposable identity/process scope и очищаются exact-ID fixture cleanup. Рабочая БД, prepared accounts, quota policy и сервисы не перезапускаются. Это bounded concurrency contract check, не нагрузочный benchmark и не замена длительного fault-injection испытания инфраструктуры.'),
        section('19. Воспроизведение, evidence chain и первичные основания',
            'Запуски: python -m scripts.advanced_assurance; python -m pytest tests/test_advanced_assurance.py tests/test_advanced_assurance_http.py --junitxml=validation/reports/current/advanced-assurance-tests.xml. Два последовательных CPU runs с одинаковыми SHA-256 источников дают равные results; latency/duration исключены из equality. Все прошлые CPU attempts сохраняются в advanced-assurance-attempts с именем SHA-256 самого artifact. Пороговые условия не изменялись по результатам симуляции.',
            'Evidence: advanced-assurance.json — параметры, scores, intervals, mutants, версия Python и hashes; advanced-assurance-tests.xml — именованные pytest/HTTP cases; validation/advanced_protocol.json — контракт; scripts/advanced_assurance.py — независимые checks. Документ воспроизводит текущие artifacts и перед сборкой проверяет соответствие hashes исполняемым источникам.',
            '<a href="https://vuir.vu.edu.au/36919/" color="#492AFF">Chen et al., 2018: Metamorphic Testing — A Review of Challenges and Opportunities</a> — проверка результатов через отношения между преобразованными входами.',
            '<a href="https://discovery.ucl.ac.uk/id/eprint/10056704/" color="#492AFF">Papadakis et al., 2019: Mutation Testing Advances — An Analysis and Survey</a> — оценивание adequacy тестов через выявление внесённых ошибок; DOI 10.1016/bs.adcom.2018.03.015.',
            '<a href="https://pmc.ncbi.nlm.nih.gov/articles/PMC5502906/" color="#492AFF">Lakens, 2017: Equivalence Tests — A Practical Primer</a> — TOST, заранее определённые bounds и различение equivalence от отсутствия significant difference. Источники проверены 10 октября 2026 года; они обосновывают методику, не являются независимой сертификацией Proofit.')
    ]
