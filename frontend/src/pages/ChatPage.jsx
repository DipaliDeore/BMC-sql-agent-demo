/**
 * ChatPage.jsx — ChatGPT-style sessions backed by API + Postgres
 */

import React, { useCallback, useEffect, useState } from "react";
import { submitFeedback } from "../api/agent";
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

  // ✅ MAIN SEND FUNCTION (FIXED)
  async function handleSend(question) {
    if (!activeChatId) return;

    // 🔥 No-feedback tracking
    const lastAssistant = [...messages]
      .reverse()
      .find((m) => m.role === "assistant" && !m.streaming);

    if (lastAssistant && !lastAssistant.feedbackGiven) {
      try {
        await submitFeedback(
          lastAssistant.original_question || "",
          lastAssistant.explanation || lastAssistant.content || "",
          "none",
          { sql: lastAssistant.sql || "" }
        );
      } catch (e) {}
    }

    const userMessage = {
      id: `local-u-${Date.now()}`,
      role: "user",
      content: question,
    };

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

    const nextMessages = [...messages, userMessage];

    setMessages([...nextMessages, streamingPlaceholder]);
    setLoading(true);

    try {
      const forApi = mapMessagesForApi([...nextMessages, streamingPlaceholder]);

      await streamQuery(question, activeChatId, "AUTO", forApi, {
        onEvent: (evt) => {
          setMessages((prev) =>
            prev.map((m) => {
              if (m.id !== assistantId) return m;

              if (evt.type === "status") {
                const labels = {
                  thinking: "Thinking…",
                  generating_sql: "Generating SQL…",
                  executing_sql: "Executing query…",
                  done: "Wrapping up…",
                };
                return {
                  ...m,
                  streamStatus: labels[evt.content] || evt.content,
                };
              }

              if (evt.type === "token") {
                return {
                  ...m,
                  streamText: (m.streamText || "") + evt.content,
                };
              }

              if (evt.type === "sql") {
                return { ...m, streamSql: evt.content };
              }

              if (evt.type === "data") {
                return {
                  ...m,
                  streamRows: [...(m.streamRows || []), evt.content],
                };
              }

              if (evt.type === "final") {
                const d = evt.content || {};
                return {
                  id: assistantId,
                  serverMessageId: d.assistant_message_id ?? null,
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
                  errorText: evt.content || "Something went wrong",
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

  // ✅ Sidebar Handlers (FIXED)
  const handleNewChat = async () => {
    const c = await createChat();
    setChats((prev) => [c, ...prev]);
    setActiveChatId(c.id);
    setMessages([]);
  };

  const handleSelectChat = async (id) => {
    setActiveChatId(id);
    await loadMessages(id);
  };

  const handleRenameChat = async (id, name) => {
    await renameChat(id, name);
    await refreshChats();
  };

  const handleDeleteChat = async (id) => {
    await deleteChat(id);
    const list = await refreshChats();
    if (list.length > 0) {
      setActiveChatId(list[0].id);
      await loadMessages(list[0].id);
    } else {
      setMessages([]);
    }
  };

  // ✅ INITIAL LOAD
  useEffect(() => {
    (async () => {
      try {
        let list = await listChats();

        if (list.length === 0) {
          const c = await createChat();
          list = [c];
        }

        setChats(list);
        setActiveChatId(list[0].id);
        await loadMessages(list[0].id);
      } catch (err) {
        setInitError(getApiErrorMessage(err));
      }
    })();
  }, []);

  if (initError && !activeChatId) {
    return (
      <div className="app-shell" style={{ padding: 24 }}>
        <p>Could not load chats</p>
        <p>{initError}</p>
        <button onClick={() => window.location.reload()}>Retry</button>
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