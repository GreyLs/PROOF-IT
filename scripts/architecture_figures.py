"""Searchable vector component and interaction figures for existing PDF books."""
import math
from reportlab.lib import colors
from reportlab.platypus import Flowable

PURPLE=colors.HexColor('#492AFF');INK=colors.HexColor('#182342');MUTED=colors.HexColor('#66718A')

class ArchitectureFigure(Flowable):
    def __init__(self,kind):
        super().__init__();self.kind=kind;self.width=487;self.height=530 if kind in ('components','runtime') else 435
    def text(self,x,y,text,size=7.6,bold=False,color=INK,center=False):
        c=self.canv;c.setFillColor(color);c.setFont('BodyBold' if bold else 'Body',size)
        if center:c.drawCentredString(x,y,text)
        else:c.drawString(x,y,text)
    def box(self,x,y,w,h,title,lines,fill='#F5F2FF',stroke='#9F8AEF'):
        c=self.canv;c.setFillColor(colors.HexColor(fill));c.setStrokeColor(colors.HexColor(stroke));c.setLineWidth(.8);c.roundRect(x,y,w,h,7,fill=1,stroke=1)
        self.text(x+10,y+h-18,title,8.3,True)
        for i,line in enumerate(lines):self.text(x+10,y+h-33-i*11,line,7.0)
    def arrow(self,x1,y1,x2,y2,label=None,dashed=False):
        c=self.canv;c.setStrokeColor(PURPLE);c.setFillColor(PURPLE);c.setLineWidth(1)
        c.setDash([3,3] if dashed else [])
        c.line(x1,y1,x2,y2);c.setDash([])
        angle=math.atan2(y2-y1,x2-x1)
        p=c.beginPath();p.moveTo(x2,y2);p.lineTo(x2-5*math.cos(angle-.45),y2-5*math.sin(angle-.45));p.lineTo(x2-5*math.cos(angle+.45),y2-5*math.sin(angle+.45));p.close();c.drawPath(p,fill=1,stroke=0)
        if label:self.text((x1+x2)/2,(y1+y2)/2+7,label,6.8,color=MUTED,center=True)
    def draw(self):
        if self.kind=='components':self.components()
        elif self.kind=='runtime':self.runtime()
        elif self.kind=='twin':self.twin()
        else:self.sequence()
    def components(self):
        self.text(0,515,'КОМПОНЕНТЫ И ГРАНИЦЫ ДОВЕРИЯ',10,True,color=PURPLE)
        self.box(0,453,150,45,'Кандидат',['Собственные данные и согласия'])
        self.box(168,453,150,45,'Работодатель',['Свои вакансии и процессы'])
        self.box(336,453,151,45,'Одобренный эксперт',['Независимый scoped review'])
        self.box(168,365,150,53,'React / TypeScript',['Один origin /api + SPA','Навигация и объяснения'])
        for x in (75,243,411):self.arrow(x,453,243,418)
        self.box(168,276,150,53,'Rust Gateway · 1717',['Host / квоты / inflight','Cookie / Bearer forwarding'])
        self.arrow(243,365,243,329,'HTTPS / TLS ingress')
        self.box(337,365,150,53,'Keycloak · 9091',['OIDC / PKCE / JWKS','Master/admin не публичны'],fill='#EFF8F4',stroke='#A3D2BD')
        self.arrow(318,393,337,393,'OIDC',True)
        self.box(0,163,216,73,'7 Rust-доменов · 8082–8088',['Identity / Talent / Recruitment','Documents / Integrations / Platform','Intelligence: ownership, CAS, audit'])
        self.arrow(197,276,108,236,'Маршрутизация / Actor')
        self.box(271,163,216,73,'CPU Intelligence · 8092',['CAT / GraphSAGE / twins / TOST','GitHub read adapter / uncertainty','Нет credentials PostgreSQL'])
        self.arrow(216,197,271,197,'Bounded RPC')
        self.box(0,59,216,64,'PostgreSQL 17 / storage',['Users, consent, evidence, jobs, ledger','Транзакции, FK, неизменяемые снимки','Файлы выдаются только владельцу'],fill='#EEF5FC',stroke='#ACBFDC')
        self.arrow(108,163,108,123,'Параметризованный SQL')
        self.box(271,72,216,51,'Публичный GitHub',['REST / GraphQL read-only','Fixed origin, quota, body bounds'],fill='#FFF8EC',stroke='#DECAA2')
        self.arrow(379,163,379,123,'Внешнее ограниченное чтение')
        self.text(0,34,'ДОЛГИЕ / СПЕЦИАЛИЗИРОВАННЫЕ ВЫЧИСЛЕНИЯ',8.1,True,color=PURPLE)
        self.text(0,18,'Processor 8081 · PDF/OCR; Workbench 8091 · Docker; Forecast 8090 · CatBoost',7.4)
        self.text(0,4,'Контроллер очереди имеет DB-доступ; вычислительные сервисы — отдельная граница.',7.2,color=MUTED)
    def runtime(self):
        self.text(0,515,'ОЧЕРЕДИ, СЕКРЕТЫ И ВЫЧИСЛИТЕЛЬНАЯ ИЗОЛЯЦИЯ',9.5,True,color=PURPLE)
        self.box(0,417,216,65,'Rust domain handlers',['Identity / ownership / admission','Durable intelligence jobs + ledger','Cheap retrieval не исполняет OCR'])
        self.box(271,417,216,65,'PostgreSQL + storage',['Document state / leases / exact IDs','Intelligence job state / decisions','Подтверждённые поля и результаты'],fill='#EEF5FC',stroke='#ACBFDC')
        self.arrow(216,450,271,450,'SQL / state')
        self.box(0,287,216,65,'Trusted queue-controller',['worker.main / process_job','Имеет DB-доступ и lease token','Передаёт выбранный документ'])
        self.arrow(326,417,180,352,'Lease / bounded job state',True)
        self.box(271,287,216,65,'Processor · 8081',['Private token / PDF body bound','OCR / extraction / optional review','Без DB и SMTP credentials'],fill='#EFF8F4',stroke='#A3D2BD')
        self.arrow(216,318,271,318,'POST /process')
        self.box(0,155,216,67,'Rust intelligence worker',['Ограниченный payload и job lease','Сохраняет результат / audit','Раздельный контур от PDF-очереди'])
        self.box(271,155,216,67,'CPU engine / Forecast',['8092: CAT / graph / twins / A/B','8090: frozen CatBoost time prior','Bounded compute; нет DB credentials'],fill='#EFF8F4',stroke='#A3D2BD')
        self.arrow(216,188,271,188,'Internal RPC')
        self.box(0,29,216,68,'Workbench · 8091',['Контракт задачи / код / тесты','Валидация / task-scoped fingerprints','Вызов от Rust по owned workflow'])
        self.box(271,29,216,68,'Docker sandbox',['Нет сети; CPU / RAM / time bounds','Недоверенный код не в host process','Hidden tests остаются серверными'],fill='#FFF8EC',stroke='#DECAA2')
        self.arrow(216,61,271,61,'Изолированный run')
        self.text(0,8,'Файлы и результаты не доступны напрямую из SPA. Endpoint visibility ≠ разрешение владельца.',7.1,color=MUTED)
    def sequence(self):
        self.text(0,420,'ЗАЩИТА ПУБЛИЧНОГО PR: ВЗАИМОДЕЙСТВИЯ',10,True,color=PURPLE)
        actors=[('Браузер',49),('Rust + PG',176),('CPU engine',307),('GitHub API',438)]
        for index,(title,x) in enumerate(actors):
            self.box(x-47,358,94,43,title,[["Кандидат / reviewer"],["Ownership / CAS"],["Bounded compute"],["Public read-only"]][index])
            self.canv.setStrokeColor(colors.HexColor('#D5D0E3'));self.canv.setDash([3,3]);self.canv.line(x,358,x,44);self.canv.setDash([])
        rows=[(0,1,'1. PR + собственное резюме + opt-in'),(1,2,'2. Ограниченный запрос публичного снимка'),(2,3,'3. Files / commits / PR discussion'),(3,2,'4. Public metadata + current head SHA'),(2,1,'5. Digest, SHA и адресные вопросы'),(0,1,'6. Ответы + question IDs + revision / CAS'),(0,1,'7. Независимый reviewer: критерии и причина'),(1,2,'8. Fresh head check перед решением'),(2,1,'9. Ролевая матрица / eligibility'),(1,0,'10. Scoped result + audit + certificate ID')]
        for index,(source,target,label) in enumerate(rows):
            y=333-index*29
            self.arrow(actors[source][1],y,actors[target][1],y)
            self.text(8,y+8,label,7.1,color=MUTED)
        self.text(0,23,'Шаг 7: другая одобренная identity; обычный работодатель не получает право аттестации.',7.2)
        self.text(0,8,'Rust отдельно проверяет knowledge, identity, SHA, критерии и ограничения. Нет auto-grade.',7.2)
    def twin(self):
        self.text(0,420,'ЦИКЛ ЦИФРОВОГО ДВОЙНИКА: ОТ ФАКТА К ДЕЙСТВИЮ',9.5,True,color=PURPLE)
        self.box(0,312,216,73,'1. Текущее состояние',['Роль / условия / доказательства','Своя identity и доступный рынок','Заявление ≠ подтверждённый навык'])
        self.box(271,312,216,73,'2. Ограниченная модель',['Graph: source → skill → requirement','CatBoost prior + finite-pool simulation','Нет психологического профилирования'])
        self.arrow(216,348,271,348,'Снимок')
        self.box(271,182,216,74,'3. What-if, не mutation',['Изменение условий задаётся явно','Общие случайные воздействия','Baseline и scenario сохраняют разницу'])
        self.arrow(379,312,379,256,'Сценарный payload')
        self.box(0,182,216,74,'4. Объяснимый результат',['Кривые, квантили, пробелы','Опора источников, версия, допущения','Null вместо выдуманного срока'])
        self.arrow(271,220,216,220,'Сравнение')
        self.box(0,57,216,74,'5. Решение пользователя',['Адресная практика / обсуждение условий','Обычный отклик / предложение','Никаких автоматических изменений'])
        self.arrow(108,182,108,131,'Явное действие')
        self.box(271,57,216,74,'6. Новое наблюдение',['Проверенный артефакт / 30–60–90','Раздельные ответы обеих сторон','Новый snapshot; прежний trace сохранён'])
        self.arrow(216,94,271,94,'Обновление')
        self.text(0,29,'Новые факты обновляют следующий расчёт. Историческое решение не переписывается.',7.7)
        self.text(0,12,'Результат модели не равен исходу найма: наблюдения и допущения имеют разные контуры.',7.4,color=MUTED)
