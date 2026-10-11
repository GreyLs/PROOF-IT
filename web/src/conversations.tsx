import { useEffect, useState, type FormEvent } from "react";
import {
  CheckCheck,
  LockKeyhole,
  MessageCircle,
  RefreshCw,
  Send,
} from "lucide-react";
import { send } from "./api";
import "./conversations.css";
import {
  Badge,
  Empty,
  ErrorBox,
  Loading,
  PageHead,
  useApp,
  useData,
} from "./ui";

type Conversation = {
  id: string;
  candidate_id: string;
  company_id: string;
  vacancy_id: string | null;
  resume_id: string | null;
  origin: "invitation" | "application";
  vacancy_title: string;
  resume_title: string;
  created_at: string;
  last_message_at: string | null;
  other_name: string;
  other_kind: "candidate" | "company";
  contact_revoked: boolean;
  unread_count: number;
  last_message_preview: string | null;
  last_message_sender_id: string | null;
};
type Message = {
  id: string;
  sender_user_id: string;
  body: string;
  created_at: string;
  read_at: string | null;
};
type Detail = { conversation: Conversation; messages: Message[] };

const when = (value: string) =>
  new Intl.DateTimeFormat("ru-RU", {
    day: "numeric",
    month: "short",
    hour: "2-digit",
    minute: "2-digit",
  }).format(new Date(value));

function contextLabel(item: Conversation) {
  if (item.vacancy_title && item.resume_title)
    return `${item.vacancy_title} · ${item.resume_title}`;
  return item.vacancy_title || item.resume_title || "Обсуждение предложения";
}

export function ConversationsPage() {
  const { user, notify } = useApp();
  const threads = useData<{ items: Conversation[] }>("/conversations");
  const [selected, setSelected] = useState("");
  const detail = useData<Detail>(
    selected ? `/conversations/${selected}` : null,
    [selected],
  );
  const [body, setBody] = useState("");
  const [sending, setSending] = useState(false);

  useEffect(() => {
    const first = threads.data?.items[0]?.id || "";
    if (!selected && first) setSelected(first);
    if (
      selected &&
      threads.data &&
      !threads.data.items.some((item) => item.id === selected)
    ) {
      setSelected(first);
    }
  }, [threads.data, selected]);

  useEffect(() => {
    const current = detail.data?.conversation;
    if (!current || current.unread_count === 0) return;
    send(`/conversations/${current.id}/read`)
      .then(() => {
        detail.reload();
        threads.reload();
      })
      .catch(() => undefined);
  }, [detail.data?.conversation.id, detail.data?.conversation.unread_count]);

  useEffect(() => {
    const timer = window.setInterval(() => {
      threads.reload();
      if (selected) detail.reload();
    }, 15000);
    return () => window.clearInterval(timer);
  }, [selected]);

  const sendMessage = async (event: FormEvent) => {
    event.preventDefault();
    if (!selected || !body.trim()) return;
    setSending(true);
    try {
      await send(`/conversations/${selected}/messages`, { body });
      setBody("");
      detail.reload();
      threads.reload();
    } catch (error) {
      notify((error as Error).message, true);
    } finally {
      setSending(false);
    }
  };

  const active = detail.data?.conversation;
  return (
    <>
      <PageHead
        eyebrow="ЛИЧНЫЙ КАНАЛ СВЯЗИ"
        title="Сообщения"
        description="Переписка доступна только участникам отклика или приглашения. Это отдельный тет-а-тет канал по вакансии и резюме."
        actions={
          <button
            className="button secondary"
            onClick={() => {
              threads.reload();
              detail.reload();
            }}
          >
            <RefreshCw size={16} /> Обновить
          </button>
        }
      />
      {threads.error ? (
        <ErrorBox message={threads.error} retry={threads.reload} />
      ) : threads.loading ? (
        <Loading />
      ) : !threads.data?.items.length ? (
        <Empty
          title="Диалогов пока нет"
          text="Чат появится автоматически после вашего отклика на вакансию или приглашения от компании."
        />
      ) : (
        <div className="conversation-layout">
          <aside className="conversation-list panel" aria-label="Диалоги">
            {threads.data.items.map((item) => (
              <button
                key={item.id}
                className={"conversation-row " + (selected === item.id ? "active" : "")}
                onClick={() => setSelected(item.id)}
              >
                <span className="conversation-avatar">
                  <MessageCircle size={18} />
                </span>
                <span className="conversation-summary">
                  <strong>{item.other_name}</strong>
                  <small>{contextLabel(item)}</small>
                  <em>
                    {item.last_message_preview ||
                      (item.origin === "application"
                        ? "Отклик отправлен"
                        : "Приглашение отправлено")}
                  </em>
                </span>
                <span className="conversation-meta">
                  <small>{when(item.last_message_at || item.created_at)}</small>
                  {item.unread_count > 0 && (
                    <b>{item.unread_count > 99 ? "99+" : item.unread_count}</b>
                  )}
                </span>
              </button>
            ))}
          </aside>
          <section className="conversation-panel panel" aria-live="polite">
            {detail.error ? (
              <ErrorBox message={detail.error} retry={detail.reload} />
            ) : detail.loading || !active ? (
              <Loading />
            ) : (
              <>
                <header className="conversation-head">
                  <div>
                    <h2>{active.other_name}</h2>
                    <p>{contextLabel(active)}</p>
                  </div>
                  <Badge tone="violet">
                    {active.origin === "application"
                      ? "По отклику"
                      : "По приглашению"}
                  </Badge>
                </header>
                {active.contact_revoked && (
                  <div className="conversation-privacy">
                    <LockKeyhole size={17} />
                    <span>
                      {user.role === "candidate"
                        ? "Прямые контакты закрыты. Внутренний чат остаётся приватным и доступен только этой компании."
                        : "Кандидат закрыл прямые контакты. Используйте этот закрытый чат; контактные данные недоступны."}
                    </span>
                  </div>
                )}
                <div className="conversation-messages" aria-label="История сообщений">
                  {!detail.data?.messages.length && (
                    <p className="conversation-empty">
                      Диалог открыт. Напишите первое сообщение по этой вакансии.
                    </p>
                  )}
                  {detail.data?.messages.map((message) => {
                    const own = message.sender_user_id === user.id;
                    return (
                      <article
                        key={message.id}
                        className={"chat-message " + (own ? "own" : "incoming")}
                      >
                        <p>{message.body}</p>
                        <footer>
                          {when(message.created_at)}{" "}
                          {own &&
                            (message.read_at ? (
                              <span title="Прочитано">
                                <CheckCheck size={14} /> Прочитано
                              </span>
                            ) : (
                              <span>Отправлено</span>
                            ))}
                        </footer>
                      </article>
                    );
                  })}
                </div>
                <form className="conversation-compose" onSubmit={sendMessage}>
                  <textarea
                    value={body}
                    onChange={(event) => setBody(event.target.value)}
                    placeholder="Напишите сообщение по вакансии…"
                    maxLength={4000}
                    rows={3}
                    aria-label="Сообщение"
                  />
                  <div>
                    <small>{body.trim().length}/4000</small>
                    <button
                      className="button primary"
                      disabled={sending || !body.trim()}
                    >
                      <Send size={16} /> {sending ? "Отправляем…" : "Отправить"}
                    </button>
                  </div>
                </form>
              </>
            )}
          </section>
        </div>
      )}
    </>
  );
}
