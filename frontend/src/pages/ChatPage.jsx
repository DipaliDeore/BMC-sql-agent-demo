/**
 * ChatPage.jsx — ChatGPT-style sessions backed by API + Postgres (when configured)
 */

import React, { useCallback, useEffect, useState } from "react";
import Sidebar from "../components/Sidebar";
import ChatWindow from "../components/ChatWindow";
import {
  sendQuery,
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
    setMessages(nextMessages);
    setLoading(true);

    try {
      const forApi = mapMessagesForApi(nextMessages);
      const data = await sendQuery(question, activeChatId, "AUTO", forApi);

      const assistantMessage = {
        id: `local-a-${Date.now()}`,
        serverMessageId:
          data.assistant_message_id != null ? Number(data.assistant_message_id) : null,
        role: "assistant",
        sql: data.sql,
        results: data.results,
        explanation: data.explanation,
        row_count: data.row_count,
        result_sentence: data.result_sentence ?? null,
        cache_references: data.cache_references ?? null,
        is_multi: data.is_multi ?? false,
        sub_responses: data.sub_responses ?? [],
        is_ambiguous: data.is_ambiguous ?? false,
        original_question: question,
        cache_doc_id: data.cache_doc_id ?? null,
      };

      setMessages((prev) => [...prev, assistantMessage]);
      await refreshChats();
    } catch (error) {
      const errorMessage = {
        id: `local-e-${Date.now()}`,
        role: "assistant",
        error: true,
        errorText: getApiErrorMessage(error),
      };
      setMessages((prev) => [...prev, errorMessage]);
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
