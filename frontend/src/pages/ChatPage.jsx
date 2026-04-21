/**
 * ChatPage.jsx — ChatGPT-style sessions backed by API + Postgres (when configured)
 */

import React, { useCallback, useEffect, useState } from "react";
import Sidebar from "../components/Sidebar";
import ChatWindow from "../components/ChatWindow";
import {
  streamQuery,
  getApiErrorMessage,
  listChats,
  createChat,
  getChatMessages,
  renameChat,
  deleteChat,
  mapMessagesForApi,
} from "../api/agent";

function fromApiMessage(row) {
  if (row.role === "user") {
    return { id: `db-${row.id}`, role: "user", content: row.content };
  }
  const p = row.payload || {};
  return {
    id: `db-${row.id}`,
    serverMessageId: row.id,
    role: "assistant",
    content: row.content,
    explanation: p.explanation ?? row.content,
    sql: p.sql || "",
    results: p.results || [],
    row_count: p.row_count ?? 0,
    result_sentence: p.result_sentence ?? null,
    cache_references: p.cache_references ?? null,
    is_multi: p.is_multi ?? false,
    sub_responses: p.sub_responses ?? [],
    is_ambiguous: p.is_ambiguous ?? false,
    error: p.error ?? false,
    errorText: p.errorText,
    cache_doc_id: p.cache_doc_id ?? null,
  };
}

export default function ChatPage({ theme, toggleTheme }) {
  const [chats, setChats] = useState([]);
  const [activeChatId, setActiveChatId] = useState(null);
  const [messages, setMessages] = useState([]);
  const [loading, setLoading] = useState(false);
  const [inputValue, setInputValue] = useState("");
  const [initError, setInitError] = useState(null);

  const refreshChats = useCallback(async () => {
    const list = await listChats();
    setChats(list);
    return list;
  }, []);

  const loadMessages = useCallback(async (chatId) => {
    const raw = await getChatMessages(chatId);
    setMessages(raw.map(fromApiMessage));
  }, []);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        let list = await listChats();
        if (cancelled) return;
        if (list.length === 0) {
          const c = await createChat();
          list = [c];
        }
        setChats(list);
        const firstId = list[0].id;
        setActiveChatId(firstId);
        const raw = await getChatMessages(firstId);
        if (cancelled) return;
        setMessages(raw.map(fromApiMessage));
        setInitError(null);
      } catch (e) {
        if (!cancelled) setInitError(getApiErrorMessage(e));
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  async function handleNewChat() {
    try {
      const c = await createChat();
      setChats((prev) => [c, ...prev.filter((x) => x.id !== c.id)]);
      setActiveChatId(c.id);
      setMessages([]);
      setInputValue("");
      setInitError(null);
    } catch (e) {
      setInitError(getApiErrorMessage(e));
    }
  }

  async function handleSelectChat(chatId) {
    if (chatId === activeChatId || loading) return;
    try {
      setActiveChatId(chatId);
      await loadMessages(chatId);
      setInputValue("");
      setInitError(null);
    } catch (e) {
      setInitError(getApiErrorMessage(e));
    }
  }

  async function handleRenameChat(chatId, currentTitle) {
    const next = window.prompt("Chat name", currentTitle || "");
    if (next === null) return;
    const t = next.trim();
    if (!t) return;
    try {
      await renameChat(chatId, t);
      await refreshChats();
    } catch (e) {
      setInitError(getApiErrorMessage(e));
    }
  }

  async function handleDeleteChat(chatId) {
    if (!window.confirm("Delete this chat and its messages?")) return;
    try {
      await deleteChat(chatId);
      const list = await refreshChats();
      if (chatId === activeChatId) {
        if (list.length === 0) {
          const c = await createChat();
          setChats([c]);
          setActiveChatId(c.id);
          setMessages([]);
        } else {
          setActiveChatId(list[0].id);
          await loadMessages(list[0].id);
        }
      }
    } catch (e) {
      setInitError(getApiErrorMessage(e));
    }
  }

  async function handleSend(question) {
    if (!activeChatId) return;
    const userMessage = { id: `local-u-${Date.now()}`, role: "user", content: question };
    const nextMessages = [...messages, userMessage];
    const assistantId = `local-a-${Date.now()}`;
    const streamingPlaceholder = {
      id: assistantId,
      role: "assistant",
      streaming: true,
      streamText: "",
      streamStatus: "Thinking…",
      streamSql: "",
      streamRows: [],
      original_question: question,
    };
    setMessages([...nextMessages, streamingPlaceholder]);
    setLoading(false);

    try {
      const forApi = mapMessagesForApi([...nextMessages, streamingPlaceholder]);
      await streamQuery(question, activeChatId, "AUTO", forApi, {
        onEvent: (evt) => {
          setMessages((prev) =>
            prev.map((m) => {
              if (m.id !== assistantId) return m;
              if (evt.type === "status") {
                const key = String(evt.content || "");
                const labels = {
                  thinking: "Thinking…",
                  generating_sql: "Generating SQL…",
                  executing_sql: "Executing query…",
                  done: "Wrapping up…",
                };
                return {
                  ...m,
                  streamStatus: labels[key] || key || m.streamStatus,
                };
              }
              if (evt.type === "token") {
                return {
                  ...m,
                  streamText: (m.streamText || "") + String(evt.content || ""),
                };
              }
              if (evt.type === "sql") {
                return { ...m, streamSql: String(evt.content || "") };
              }
              if (evt.type === "data" && evt.content && typeof evt.content === "object") {
                return { ...m, streamRows: [...(m.streamRows || []), evt.content] };
              }
              if (evt.type === "final") {
                const d = evt.content || {};
                return {
                  id: assistantId,
                  serverMessageId:
                    d.assistant_message_id != null ? Number(d.assistant_message_id) : null,
                  role: "assistant",
                  sql: d.sql,
                  results: d.results,
                  explanation: d.explanation,
                  row_count: d.row_count,
                  result_sentence: d.result_sentence ?? null,
                  cache_references: d.cache_references ?? null,
                  is_multi: d.is_multi ?? false,
                  sub_responses: d.sub_responses ?? [],
                  is_ambiguous: d.is_ambiguous ?? false,
                  original_question: question,
                  cache_doc_id: d.cache_doc_id ?? null,
                };
              }
              if (evt.type === "error") {
                return {
                  id: assistantId,
                  role: "assistant",
                  error: true,
                  errorText: String(evt.content || "Something went wrong."),
                };
              }
              return m;
            })
          );
        },
      });
      await refreshChats();
    } catch (error) {
      setMessages((prev) =>
        prev.map((m) =>
          m.id === assistantId
            ? {
                id: assistantId,
                role: "assistant",
                error: true,
                errorText: getApiErrorMessage(error),
              }
            : m
        )
      );
    } finally {
      setLoading(false);
    }
  }

  if (initError && !activeChatId) {
    return (
      <div className="app-shell" style={{ alignItems: "center", justifyContent: "center", padding: 24 }}>
        <div className="ui-init-card msg-animate">
          <p style={{ marginBottom: 10, fontWeight: 600, fontSize: "16px" }}>Could not load chats</p>
          <p style={{ fontSize: "14px", color: "var(--text-muted)", marginBottom: 18, lineHeight: 1.5 }}>
            {initError}
          </p>
          <button type="button" className="ui-btn-primary" onClick={() => window.location.reload()}>
            Retry
          </button>
        </div>
      </div>
    );
  }

  return (
    <div className="app-shell">
      {initError && <div className="ui-toast-error">{initError}</div>}
      <Sidebar
        chats={chats}
        activeChatId={activeChatId}
        onNewChat={handleNewChat}
        onSelectChat={handleSelectChat}
        onRenameChat={handleRenameChat}
        onDeleteChat={handleDeleteChat}
      />
      <ChatWindow
        theme={theme}
        toggleTheme={toggleTheme}
        messages={messages}
        loading={loading}
        onSend={handleSend}
        inputValue={inputValue}
        setInputValue={setInputValue}
      />
    </div>
  );
}
