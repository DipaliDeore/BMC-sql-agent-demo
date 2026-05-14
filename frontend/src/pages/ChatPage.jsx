/**
 * ChatPage.jsx — ChatGPT-style sessions backed by API + Postgres
 */

import React, { useCallback, useEffect, useMemo, useState } from "react";
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

/** API may return JSONB as object or (rarely) JSON string. */
function normalizeMessagePayload(payload) {
  if (payload == null) return {};
  if (typeof payload === "string") {
    try {
      const o = JSON.parse(payload);
      return typeof o === "object" && o !== null ? o : {};
    } catch {
      return {};
    }
  }
  return typeof payload === "object" ? payload : {};
}

function fromApiMessage(row) {
  if (row.role === "user") {
    const p = normalizeMessagePayload(row.payload);
    const atts = p.image_attachments || p.imageAttachments;
    let attachmentPreviews;
    if (Array.isArray(atts) && atts.length > 0) {
      attachmentPreviews = atts.map((a) => {
        const mime = (a.media_type || "image/png").trim() || "image/png";
        const b64 = String(a.data_base64 || "").replace(/\s/g, "");
        return `data:${mime};base64,${b64}`;
      });
    }
    return {
      id: `db-${row.id}`,
      role: "user",
      content: row.content,
      ...(attachmentPreviews ? { attachmentPreviews } : {}),
    };
  }

  const p = normalizeMessagePayload(row.payload);
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
    excel_download_url: p.excel_download_url ?? null,
    chart_config: p.chart_config ?? null,
  };
}

export default function ChatPage({ theme, toggleTheme }) {
  const [chats, setChats] = useState([]);
  const [activeChatId, setActiveChatId] = useState(null);
  const [messagesByChat, setMessagesByChat] = useState({});
  const [loadingByChat, setLoadingByChat] = useState({});
  const [inputValue, setInputValue] = useState("");
  const [pendingImages, setPendingImages] = useState([]);
  const [initError, setInitError] = useState(null);

  const activeMessages = useMemo(
    () => (activeChatId ? messagesByChat[activeChatId] || [] : []),
    [activeChatId, messagesByChat],
  );
  const activeLoading = activeChatId ? !!loadingByChat[activeChatId] : false;

  const setChatMessages = useCallback((chatId, next) => {
    setMessagesByChat((prev) => {
      const current = prev[chatId] || [];
      const resolved = typeof next === "function" ? next(current) : next;
      return { ...prev, [chatId]: resolved };
    });
  }, []);

  const setChatLoading = useCallback((chatId, value) => {
    setLoadingByChat((prev) => ({ ...prev, [chatId]: value }));
  }, []);

  const mergeServerMessages = useCallback((existing, rawRows) => {
    const serverMessages = rawRows.map(fromApiMessage);
    const localStreaming = (existing || []).filter((m) => m?.streaming);
    const localIds = new Set(serverMessages.map((m) => String(m.id)));
    const pendingStreaming = localStreaming.filter((m) => !localIds.has(String(m.id)));
    return [...serverMessages, ...pendingStreaming];
  }, []);

  const refreshChats = useCallback(async () => {
    const list = await listChats();
    setChats(list);
    return list;
  }, []);

  const loadMessages = useCallback(async (chatId) => {
    const raw = await getChatMessages(chatId);
    setMessagesByChat((prev) => ({
      ...prev,
      [chatId]: mergeServerMessages(prev[chatId] || [], raw),
    }));
  }, [mergeServerMessages]);

  // ✅ FIXED handleSend
  async function handleSend(question) {
    if (!activeChatId) return;
    const chatId = activeChatId;

    const snapshot = [...pendingImages];
    const qText = question.trim();
    const userMessage = {
      id: `local-u-${Date.now()}`,
      role: "user",
      content: qText || (snapshot.length ? "(Image)" : ""),
      attachmentPreviews: snapshot.map((p) => p.preview),
    };

    const assistantId = `local-a-${chatId}-${Date.now()}`;

    const streamingPlaceholder = {
      id: assistantId,
      role: "assistant",
      streaming: true,
      streamText: "",
      streamStatus: "Thinking…",
      streamSql: "",
      streamRows: [],
      original_question: qText || (snapshot.length ? "(Image only)" : question),
    };

    const currentMessages = messagesByChat[chatId] || [];
    const nextMessages = [...currentMessages, userMessage];

    setChatMessages(chatId, [...nextMessages, streamingPlaceholder]);
    setChatLoading(chatId, true);

    try {
      const forApi = mapMessagesForApi(nextMessages);

      const imagePayload =
        snapshot.length > 0
          ? snapshot.map(({ media_type, data_base64 }) => ({ media_type, data_base64 }))
          : null;

      await streamQuery(
        qText || (snapshot.length ? "(Image only)" : question),
        chatId,
        "AUTO",
        forApi,
        {
          onEvent: (evt) => {
            setChatMessages(chatId, (prev) =>
              prev.map((m) => {
                if (m.id !== assistantId) return m;

                if (evt.type === "status") {
                  const labels = {
                    thinking: "Thinking…",
                    generating_sql: "Generating SQL…",
                    executing_sql: "Executing query…",
                    done: "Wrapping up…",
                    analyzing_image: "Analyzing image…",
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
                    original_question: qText || (snapshot.length ? "(Image only)" : question),
                    cache_doc_id: d.cache_doc_id ?? null,
                    chart_config: d.chart_config ?? null,
                    excel_download_url: d.excel_download_url ?? null,
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
              }),
            );
          },
        },
        imagePayload,
      );

      setPendingImages([]);
      await refreshChats();
      await loadMessages(chatId);
    } catch (error) {
      setChatMessages(chatId, (prev) =>
        prev.map((m) =>
          m.id === assistantId
            ? {
                id: assistantId,
                role: "assistant",
                error: true,
                errorText: getApiErrorMessage(error),
              }
            : m,
        ),
      );
    } finally {
      setChatLoading(chatId, false);
    }
  }

  // ✅ Sidebar Handlers
  const handleNewChat = async () => {
    const c = await createChat();
    setChats((prev) => [c, ...prev]);
    setActiveChatId(c.id);
    setMessagesByChat((prev) => ({ ...prev, [c.id]: [] }));
    setLoadingByChat((prev) => ({ ...prev, [c.id]: false }));
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
      setMessagesByChat({});
      setLoadingByChat({});
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
        messages={activeMessages}
        loading={activeLoading}
        onSend={handleSend}
        inputValue={inputValue}
        setInputValue={setInputValue}
        pendingImages={pendingImages}
        onPendingImagesChange={setPendingImages}
      />
    </div>
  );
}
