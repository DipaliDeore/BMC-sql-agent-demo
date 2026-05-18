/**
 * ChatPage.jsx — ChatGPT-style sessions backed by API + Postgres
 */

import React, { useCallback, useEffect, useMemo, useRef, useState } from "react";
import Sidebar from "../components/Sidebar";
import ChatWindow from "../components/ChatWindow";
import ErrorBoundary from "../components/ErrorBoundary";
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
    response_kind: p.response_kind ?? null,
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
  const [boundaryKey, setBoundaryKey] = useState(0);

  const streamAbortRef = useRef(null);

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

  const abortActiveStream = useCallback(() => {
    if (streamAbortRef.current) {
      streamAbortRef.current.abort();
      streamAbortRef.current = null;
    }
  }, []);

  const refreshChats = useCallback(async () => {
    const list = await listChats();
    setChats(list);
    return list;
  }, []);

  const loadMessages = useCallback(async (chatId) => {
    const raw = await getChatMessages(chatId);
    setMessagesByChat((prev) => {
      const existing = prev[chatId] || [];
      const streamingOnly = existing.filter((m) => m?.streaming);
      if (streamingOnly.length > 0) {
        return {
          ...prev,
          [chatId]: [...raw.map(fromApiMessage), ...streamingOnly],
        };
      }
      return { ...prev, [chatId]: raw.map(fromApiMessage) };
    });
  }, []);

  const runStream = useCallback(
    async (chatId, question, { skipUserMessage = false, imageSnapshot = null } = {}) => {
      const snapshot = imageSnapshot ?? [...pendingImages];
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
      const baseMessages = skipUserMessage
        ? currentMessages.filter((m) => !(m.role === "assistant" && m.error))
        : [...currentMessages, userMessage];

      setChatMessages(chatId, [...baseMessages, streamingPlaceholder]);
      setChatLoading(chatId, true);

      abortActiveStream();
      const controller = new AbortController();
      streamAbortRef.current = controller;

      try {
        const forApi = mapMessagesForApi(
          skipUserMessage ? baseMessages : [...currentMessages, userMessage],
        );

        const imagePayload =
          snapshot.length > 0
            ? snapshot.map(({ media_type, data_base64 }) => ({
                media_type,
                data_base64,
              }))
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
                    const sid = d.assistant_message_id ?? null;
                    return {
                      id: sid ? `db-${sid}` : assistantId,
                      serverMessageId: sid,
                      role: "assistant",
                      streaming: false,
                      content: d.explanation ?? "",
                      sql: d.sql ?? "",
                      results: d.results ?? [],
                      explanation: d.explanation ?? "",
                      row_count: d.row_count ?? 0,
                      result_sentence: d.result_sentence ?? null,
                      cache_references: d.cache_references ?? null,
                      is_multi: d.is_multi ?? false,
                      sub_responses: d.sub_responses ?? [],
                      is_ambiguous: d.is_ambiguous ?? false,
                      original_question:
                        qText || (snapshot.length ? "(Image only)" : question),
                      cache_doc_id: d.cache_doc_id ?? null,
                      chart_config: d.chart_config ?? null,
                      excel_download_url: d.excel_download_url ?? null,
                      response_kind: d.response_kind ?? null,
                    };
                  }

                  if (evt.type === "error") {
                    return {
                      id: assistantId,
                      role: "assistant",
                      error: true,
                      errorText: evt.content || "Something went wrong",
                      original_question:
                        qText || (snapshot.length ? "(Image only)" : question),
                    };
                  }

                  return m;
                }),
              );
            },
          },
          imagePayload,
          controller.signal,
        );

        if (!skipUserMessage) setPendingImages([]);
        await refreshChats();
        await loadMessages(chatId);
      } catch (error) {
        if (error?.name === "AbortError") {
          setChatMessages(chatId, (prev) =>
            prev.filter((m) => m.id !== assistantId),
          );
        } else {
          setChatMessages(chatId, (prev) =>
            prev.map((m) =>
              m.id === assistantId
                ? {
                    id: assistantId,
                    role: "assistant",
                    error: true,
                    errorText: getApiErrorMessage(error),
                    original_question:
                      qText || (snapshot.length ? "(Image only)" : question),
                  }
                : m,
            ),
          );
        }
      } finally {
        if (streamAbortRef.current === controller) {
          streamAbortRef.current = null;
        }
        setChatLoading(chatId, false);
      }
    },
    [
      pendingImages,
      messagesByChat,
      setChatMessages,
      setChatLoading,
      abortActiveStream,
      refreshChats,
      loadMessages,
    ],
  );

  const handleSend = useCallback(
    (question) => {
      if (!activeChatId) return;
      runStream(activeChatId, question);
    },
    [activeChatId, runStream],
  );

  const handleStop = useCallback(() => {
    abortActiveStream();
    if (activeChatId) setChatLoading(activeChatId, false);
  }, [abortActiveStream, activeChatId, setChatLoading]);

  const handleRetry = useCallback(
    (question) => {
      if (!activeChatId || !question?.trim()) return;
      runStream(activeChatId, question, { skipUserMessage: true });
    },
    [activeChatId, runStream],
  );

  const handleNewChat = async () => {
    abortActiveStream();
    const c = await createChat();
    setChats((prev) => [c, ...prev]);
    setActiveChatId(c.id);
    setMessagesByChat((prev) => ({ ...prev, [c.id]: [] }));
    setLoadingByChat((prev) => ({ ...prev, [c.id]: false }));
  };

  const handleSelectChat = async (id) => {
    if (id !== activeChatId) abortActiveStream();
    setActiveChatId(id);
    await loadMessages(id);
  };

  const handleRenameChat = async (id, name) => {
    await renameChat(id, name);
    await refreshChats();
  };

  const handleDeleteChat = async (id) => {
    if (id === activeChatId) abortActiveStream();
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
  }, [loadMessages]);

  useEffect(() => {
    return () => abortActiveStream();
  }, [abortActiveStream]);

  if (initError && !activeChatId) {
    return (
      <div className="app-shell" style={{ padding: 24 }}>
        <p>Could not load chats</p>
        <p>{initError}</p>
        <button type="button" className="ui-btn-primary" onClick={() => window.location.reload()}>
          Retry
        </button>
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

      <ErrorBoundary key={boundaryKey} onReset={() => setBoundaryKey((k) => k + 1)}>
        <ChatWindow
          theme={theme}
          toggleTheme={toggleTheme}
          messages={activeMessages}
          loading={activeLoading}
          onSend={handleSend}
          onStop={handleStop}
          onRetry={handleRetry}
          inputValue={inputValue}
          setInputValue={setInputValue}
          pendingImages={pendingImages}
          onPendingImagesChange={setPendingImages}
        />
      </ErrorBoundary>
    </div>
  );
}
