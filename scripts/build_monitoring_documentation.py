"""Evidence-linked operations PDF; no regeneration of unrelated validation books."""
import hashlib
import json
from pathlib import Path
import xml.etree.ElementTree as ET
from scripts import build_pdf_documentation as pdf

ROOT = Path(__file__).resolve().parents[1]

def main():
    report = json.loads((pdf.REPORTS / 'monitoring-live.json').read_text(encoding='utf-8'))
    unit = ET.parse(pdf.REPORTS / 'monitoring-unit.xml').getroot().find('testsuite')
    assert report['passed'] and int(unit.get('failures')) == 0 and int(unit.get('errors')) == 0
    hashes = {}
    for path in sorted((ROOT / 'deploy/monitoring').rglob('*')):
        if path.is_file():
            hashes[path.relative_to(ROOT).as_posix()] = hashlib.sha256(path.read_bytes()).hexdigest()
    for name in ('monitoring_exporter', 'prepare_monitoring', 'start_monitoring', 'stop_monitoring', 'check_monitoring_live', 'build_monitoring_documentation'):
        path = ROOT / 'scripts' / (name + '.py')
        hashes[path.relative_to(ROOT).as_posix()] = hashlib.sha256(path.read_bytes()).hexdigest()
    for name in ('tests/test_monitoring.py', 'requirements.monitoring.txt', 'scripts/private_runtime.py'):
        hashes[name] = hashlib.sha256((ROOT / name).read_bytes()).hexdigest()
    fingerprint = hashlib.sha256(json.dumps(hashes, sort_keys=True).encode()).hexdigest()
    sections = [
        pdf.section('1. Эксплуатационная задача и границы наблюдения',
            'Наблюдаемость Proofit отделена от бизнес-запроса: отказ системы мониторинга не останавливает поиск, аттестацию или расчёт сценария. Нативный сборщик читает фиксированные локальные readiness-endpoints и существующие CPU-счётчики, ресурсы ОС и агрегированную статистику PostgreSQL. Prometheus хранит временные ряды; Grafana визуализирует наблюдения; Alertmanager группирует операционные сигналы.',
            'Контур обслуживает девять целей: gateway, семь Rust-доменов и CPU Intelligence. Проверка готовности Rust включает SELECT 1; CPU health подтверждает ответ процесса, но не качество модели. Отдельные OCR, Workbench, LLM, прогнозный процесс и Keycloak не включены в девять readiness-проб; их нельзя считать проверенными по зелёному статусу этой панели. Полные пользовательские сценарии остаются самостоятельным уровнем валидации.'),
        pdf.section('2. Архитектура и потоки наблюдений',
            'Сбор выполняется каждые 10 секунд; девять readiness-запросов запускаются с ограничением в девять потоков, тайм-аутом 3 секунды и пределом ответа 64 KiB. Используются фиксированные loopback-адреса, без перенаправлений и системного HTTP proxy. Снимок заменяется атомарно; scrape не инициирует дорогие SQL или probe-операции. Prometheus опрашивает сборщик каждые 15 секунд с тайм-аутом 5 секунд.',
            diagram=[['9 private readiness targets\nRust + CPU; fixed loopback','Bounded native collector\n9198 / bearer / snapshot'],['OS + pg_stat_database\nno business rows','Prometheus 3.5.0\n15 s scrape / 14 d retention'],['Grafana 12.1.1\n16 provisioned panels','Alertmanager 0.28.1\ngrouping / inhibition']]),
        pdf.section('3. Каталог сигналов и измерительные контракты', rows=[
            ['Группа','Сигнал / источник','Корректная интерпретация'],
            ['Доступность','proofit_service_up; 9 fixed labels','Ответ readiness, а не успешный найм или полная готовность AI'],
            ['Readiness latency','proofit_health_probe_duration_seconds; cumulative histogram','P95 синтетических health-проб, не P95 пользовательского API'],
            ['CPU-контур','operations_total, errors_total, cache_hits_total, processing_seconds_total','Счётчики из текущего процесса CPU; сброс при перезапуске корректно обрабатывается rate'],
            ['Ресурсы','host CPU, available RAM, свободный диск; RSS и CPU seconds процессов','Хостовые показатели включают стороннюю нагрузку; процессные проверяют имя PID'],
            ['PostgreSQL','соединения, commits, rollbacks, blks_hit/read, deadlocks','Агрегаты системной статистики; rollback не тождественен ошибке'],
            ['Целостность','collector timestamp, duration, cpu_metrics_up, database_enabled/up','Доступность exporter не заменяет свежесть его данных']]),
        pdf.section('4. Формулы и различение смыслов',
            'Ошибки вычислений = rate(errors) / max(rate(operations)+rate(errors)+rate(cache_hits), 0.001). Это доля в зарегистрированных CPU-исходах, а не доля всех HTTP-запросов: отказы авторизации и ранние отклонения входа могут не попасть в CPU counters. Суммарное processing time включает разные ветви; оно не объявляется точной средней задержкой выполнения задачи.',
            'P95 readiness = histogram_quantile(0.95, sum by(service,le)(rate(probe_duration_bucket[5m]))). Границы histogram: 5/10/25/50/100/250/500/1000/2000/4000 ms и +Inf. Квантиль является оценкой по бакетам; низкий объём наблюдений ограничивает интерпретацию. При отсутствии данных панель показывает отсутствие данных, а не искусственный ноль.',
            'PostgreSQL cache ratio = rate(blks_hit)/(rate(blks_hit)+rate(blks_read)), с безопасным нижним ограничением знаменателя. Это попадания shared buffers, не доля всех физических чтений диска. Использование соединений = все backend-процессы кластера / max_connections: знаменатель не сравнивается лишь с одной БД. Rate cumulative counters учитывает сброс процесса; gauge не дифференцируется.'),
        pdf.section('5. Сигналы инцидента и операционные действия',
            'В конфигурации 12 правил: два recording rules и десять alert rules. Пороги являются эксплуатационными стартовыми настройками, а не доказанным SLA. Внешняя доставка в почту или мессенджер не активируется без явной настройки получателя; firing-сигналы доступны в приватных UI Prometheus/Alertmanager.', rows=[
            ['Условие','Выдержка','Действие оператора'],
            ['Exporter или service readiness отсутствует','1 минута','Listener, PID, Host-policy, DB; не отключать perimeter'],
            ['Снимок старше 45 секунд','1 минута','Проверить loop сборщика: scrape может работать при старом снимке'],
            ['CPU counters недоступны','2 минуты','Схема и доступность фиксированного /metrics CPU'],
            ['CPU error ratio >5%; минимум 20 исходов/5 мин','3 минуты','Ошибка вычислений, входной контракт, cache; не делать вывод из единичного запроса'],
            ['Available RAM / free disk <10%','5 минут','Ресурсы процессов, конкурирующая нагрузка, политика retention'],
            ['DB collector отказал / connections >80%','1 / 3 минуты','Выделенная роль, соединения, суммарный бюджет domain pools'],
            ['Новый deadlock за 5 минут','Без дополнительной выдержки','Порядок транзакций и блокировки; не объявлять потерю данных']]),
        pdf.section('6. Безопасность, приватность и минимизация',
            'Публичная маршрутизация Proofit не изменена. Prometheus: localhost:9095; Grafana: localhost:3001; Alertmanager: localhost:9096. Контейнерные порты опубликованы только на 127.0.0.1, сборщик по умолчанию слушает 127.0.0.1:9198. Его /metrics требует bearer-secret длиной не менее 32 символов; отсутствующий или неверный секрет возвращает 401. Grafana запрещает anonymous login и регистрацию; стартовый пароль генерируется независимо и хранится вне исходников.',
            'Метрики не содержат email, идентификаторов кандидата, вакансии, резюме, SQL-текста или токенов. Единственная пользовательская размерность — фиксированное имя сервисной цели. Ошибки соединения не выводятся в exposition или журнал вместе с DSN. Нативные CPU-счётчики с некорректными, отрицательными или неполными значениями отклоняются; старый снимок counters не подставляется вместо текущего отказа.',
            'Выделенная роль proofit_monitor имеет pg_read_all_stats без SELECT на users и resume_profiles, без superuser/createdb/createrole/replication. default_transaction_read_only=on; statement_timeout=2s; lock_timeout=1s. Клиент дополнительно включает read-only transaction и connect_timeout=3s. Статистическая роль может видеть расширенные системные сведения: exporter использует только фиксированные числовые SELECT. Перед production-подключением DBA проверяет отсутствие inherited/public-grants на бизнес-таблицы.'),
        pdf.section('7. Ресурсные бюджеты и жизненный цикл',
            'Prometheus: 512 MiB и 1 CPU, retention 14 дней с дополнительным ограничением 2 GB. Grafana: 384 MiB и 1 CPU. Alertmanager: 128 MiB. Данные хранятся в отдельных persistent volumes. Контейнеры имеют read-only root filesystem, cap_drop=ALL и no-new-privileges. Grafana использует временный /tmp и writable data volume. Версии образов закреплены; изменение версии требует проверки release notes и повторной проверки конфигураций.',
            'Секреты не регенерируются при повторном prepare/start. Доступ с другой машины к Grafana или Prometheus намеренно не опубликован: для операторского доступа нужен отдельный защищённый административный канал. Grafana HTTP на loopback не объявляется публичным защищённым endpoint; для удалённого размещения необходимы TLS, identity и ACL. Публичная ссылка продукта не предоставляет служебные панели.'),
        pdf.section('8. Запуск и воспроизводимая проверка', rows=[
            ['Операция','Команда / место','Контроль'],
            ['Зависимости','python -m pip install -r requirements.monitoring.txt','Pinned monitoring dependencies'],
            ['Запуск','python -m scripts.start_monitoring','Collector без рестарта приложения; compose up -d'],
            ['Остановка','python -m scripts.stop_monitoring','Только monitoring: volumes, роль и секреты сохраняются'],
            ['Grafana','http://localhost:3001; user proofit-admin','Пароль: runtime/monitoring/grafana-password; не публиковать'],
            ['Prometheus / alerts','localhost:9095 / localhost:9096','Targets=up; rules; active alerts'],
            ['Unit','python -m pytest tests/test_monitoring.py','Token gate, schemas, stale omission, semantics'],
            ['Live / browser','python -m scripts.check_monitoring_live','Access controls, queries, DB least privilege, Grafana'],
            ['Правила','promtool check config; check rules; test rules','deploy/monitoring/rules.test.yml'],
            ['PDF','python -m scripts.build_monitoring_documentation','Обновляет только настоящий документ']]),
        pdf.section('9. Фактическая приёмка текущего контура',
            'Измерение: '+report['measured_at']+'. Пройдены '+unit.get('tests')+' unit-тестов и '+str(len(report['checks']))+' live-проверок без участия LLM. Prometheus принимает '+str(report['metric_families'])+' metric families / '+str(report['metric_samples'])+' samples; девять readiness-целей доступны. Все 16 PromQL выражений приняты API; provisioned dashboard открыт в настоящем браузере. Время конкретного цикла сбора: '+format(report['collection_duration_seconds'],'.3f')+' s; это один измеренный цикл, не P95 и не benchmark платформы.',
            'Promtool подтвердил синтаксис Prometheus-конфигурации и 12 правил. Тестовые ряды отдельно проверили срабатывание ExporterDown и ServiceDown после выдержки, а также отсутствие DatabaseDown при выключенном DB collector. Секретный доступ 200 и два отказа 401 проверены live. Выделенная статистическая роль действительно read-only и не читает users/resume_profiles. Протоколы: monitoring-unit.xml, monitoring-live.json; визуальный артефакт: monitoring-grafana.png.',
            'Сбор наблюдений не является нагрузочным тестом и не подтверждает снижение времени найма. Доступность, ресурсный бюджет и качество бизнес-прогноза — разные измерительные задачи. Интеграция не требует изменения графа, Horizon или логики квалификации.'),
        pdf.section('10. Первичные источники и привязка к реализации',
            '<a href="https://prometheus.io/docs/practices/instrumentation/" color="#492AFF">Prometheus: Instrumentation</a> — типы метрик, ограничение labels, различение counters и gauges, контроль свежести наблюдений.',
            '<a href="https://prometheus.io/docs/prometheus/latest/configuration/configuration/" color="#492AFF">Prometheus: Configuration</a> — scrape, credentials_file, recording/alert rules и Alertmanager.',
            '<a href="https://grafana.com/docs/grafana/latest/administration/provisioning/" color="#492AFF">Grafana: Provisioning</a> — воспроизводимое управление datasource и dashboards. Первичные документы проверены 10 октября 2026 года; они обосновывают механизм, а не подтверждают независимый production SLA Proofit.',
            'Реализация: scripts/monitoring_exporter.py; start_monitoring.py; prepare_monitoring.py; deploy/monitoring/. Evidence manifest: validation/reports/current/monitoring-source.json. SHA-256 среза monitoring source: '+fingerprint+'.')
    ]
    pdf.setup()
    path = pdf.OUT / '13_Observability_and_Monitoring.pdf'
    pdf.render(pdf.document('13_Observability_and_Monitoring', 'Наблюдаемость и эксплуатационный контроль',
               'Prometheus, Grafana и Alertmanager: метрики, приватность, диагностические контракты и воспроизводимая приёмка.', sections), path, include_toc=True)
    (pdf.REPORTS / 'monitoring-source.json').write_text(json.dumps({'fingerprint': fingerprint, 'files': hashes,
                 'pdf_sha256': hashlib.sha256(path.read_bytes()).hexdigest()}, indent=2), encoding='utf-8')
    print('Created docs/13_Observability_and_Monitoring.pdf; source '+fingerprint)

if __name__ == '__main__':
    main()
