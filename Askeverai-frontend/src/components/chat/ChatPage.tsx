"use client";

import { useState, useCallback, useEffect, useRef } from "react";
import { useRouter } from "next/navigation";
import type { Conversation, ChatMessage } from "@/lib/types";
import { getSessionUser, clearSessionUser, authHeaders } from "@/lib/session";
import { ChatSidebar } from "./ChatSidebar";
import { ChatInput } from "./ChatInput";
import { ChatMessageBlock } from "./ChatMessageBlock";
import { ChatBackgroundEffects } from "./ChatBackgroundEffects";
import { EverlignLogo } from "@/components/brand/EverlignLogo";

const API_BASE_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

function generateId() {
  return `${Date.now()}-${Math.random().toString(36).slice(2, 9)}`;
}

function createConversation(title: string): Conversation {
  const id = generateId();
  return {
    id,
    title,
    messages: [],
    createdAt: new Date(),
    updatedAt: new Date(),
  };
}

function getGreeting() {
  const hour = new Date().getHours();
  if (hour < 12) return "Good morning";
  if (hour < 18) return "Good afternoon";
  return "Good evening";
}

export function ChatPage() {
  const router = useRouter();
  const [sessionUser, setSessionUser] =
    useState<ReturnType<typeof getSessionUser>>(null);
  const [conversations, setConversations] = useState<Conversation[]>([]);
  const [activeId, setActiveId] = useState<string | null>(null);
  const [inputValue, setInputValue] = useState("");
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const [mounted, setMounted] = useState(false);
  const messagesEndRef = useRef<HTMLDivElement>(null);

  const endExpiredSession = useCallback(() => {
    clearSessionUser();
    router.replace("/");
  }, [router]);

  useEffect(() => {
    const user = getSessionUser();
    setSessionUser(user);

    if (user) {
      fetch(`${API_BASE_URL}/me`, {
        headers: { Authorization: `Bearer ${user.token}` },
      })
        .then((response) => {
          if (response.status === 401) endExpiredSession();
        })
        .catch(() => {
          // Network trouble is not proof of a bad token; leave the session be.
        });
    }

    const desktopViewport = window.matchMedia("(min-width: 1024px)");
    const handleViewportChange = (event: MediaQueryListEvent) => {
      setSidebarOpen(event.matches);
    };

    setSidebarOpen(desktopViewport.matches);
    desktopViewport.addEventListener("change", handleViewportChange);
    const t = setTimeout(() => setMounted(true), 50);
    return () => {
      clearTimeout(t);
      desktopViewport.removeEventListener("change", handleViewportChange);
    };
  }, [endExpiredSession]);

  const activeConversation =
    activeId != null ? conversations.find((c) => c.id === activeId) : null;
  const messages = activeConversation?.messages ?? [];

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages.length]);

  const startNewChat = useCallback(() => {
    setActiveId(null);
    setInputValue("");
  }, []);

  const selectConversation = useCallback((id: string) => {
    setActiveId(id);
    if (window.matchMedia("(max-width: 1023px)").matches) {
      setSidebarOpen(false);
    }
  }, []);

  const sendMessage = useCallback(async () => {
    const text = inputValue.trim();
    if (!text || !sessionUser?.name) return;

    let conv = activeConversation;
    if (!conv) {
      conv = createConversation(
        text.slice(0, 50) + (text.length > 50 ? "…" : ""),
      );
      setConversations((prev) => [conv!, ...prev]);
      setActiveId(conv.id);
    }

    const userMsg: ChatMessage = {
      id: generateId(),
      role: "user",
      content: text,
      timestamp: new Date(),
    };

    const assistantMsgId = generateId();
    const assistantMsg: ChatMessage = {
      id: assistantMsgId,
      role: "assistant",
      content: "",
      timestamp: new Date(),
      isLoading: true,
    };

    const currentConvId = conv.id;

    setConversations((prev) =>
      prev.map((c) =>
        c.id === currentConvId
          ? {
              ...c,
              messages: [...c.messages, userMsg, assistantMsg],
              title:
                c.messages.length === 0
                  ? text.slice(0, 50) + (text.length > 50 ? "…" : "")
                  : c.title,
              updatedAt: new Date(),
            }
          : c,
      ),
    );
    setInputValue("");

    try {
      const currentConv =
        conversations.find((c) => c.id === currentConvId) || conv;
      const allMessages = [...currentConv.messages, userMsg];
      const convHistory = allMessages
        .filter(
          (m) => m.role === "user" || (m.role === "assistant" && m.answer),
        )
        .slice(-10)
        .map((m) => ({
          query: m.role === "user" ? m.content : "",
          answer: m.role === "assistant" ? m.answer || null : null,
          sql: m.role === "assistant" ? m.sqlQueries?.[0] || null : null,
        }))
        .filter((item) => item.query);

      const response = await fetch(`${API_BASE_URL}/query`, {
        method: "POST",
        headers: { "Content-Type": "application/json", ...authHeaders() },
        body: JSON.stringify({
          query: text,
          conversation_history: convHistory,
        }),
      });

      if (response.status === 401) {
        endExpiredSession();
        return;
      }
      if (!response.ok) throw new Error("Query failed");

      const data = await response.json();

      setConversations((prev) =>
        prev.map((c) =>
          c.id === currentConvId
            ? {
                ...c,
                messages: c.messages.map((m) =>
                  m.id === assistantMsgId
                    ? {
                        ...m,
                        content: data.answer || "No results found.",
                        isLoading: false,
                        answer: data.answer,
                        generatedSql:
                          data.formatted_sql?.[0] ||
                          data.sql_queries?.[0] ||
                          undefined,
                        formattedSql: data.formatted_sql,
                        sqlQueries: data.sql_queries,
                        results:
                          data.data?.length > 0
                            ? {
                                rows:
                                  data.metadata?.row_count || data.data.length,
                                columns: data.data[0]
                                  ? Object.keys(data.data[0]).length
                                  : 0,
                                data: data.data,
                              }
                            : undefined,
                        queryId: data.query_id,
                        dbSource: data.db_source,
                        fallbackUsed: data.fallback_used,
                        recommendedDb: data.recommended_db,
                        relevantTables: data.relevant_tables,
                        trajectory: data.trajectory,
                        metadata: data.metadata,
                      }
                    : m,
                ),
                updatedAt: new Date(),
              }
            : c,
        ),
      );
    } catch {
      setConversations((prev) =>
        prev.map((c) =>
          c.id === currentConvId
            ? {
                ...c,
                messages: c.messages.map((m) =>
                  m.id === assistantMsgId
                    ? {
                        ...m,
                        content: "Something went wrong. Please try again.",
                        isLoading: false,
                      }
                    : m,
                ),
                updatedAt: new Date(),
              }
            : c,
        ),
      );
    }
  }, [
    inputValue,
    sessionUser,
    activeConversation,
    conversations,
    endExpiredSession,
  ]);

  const handleFeedback = useCallback(
    async (messageId: string, rating: number, comment: string) => {
      if (!sessionUser?.name || !activeConversation) return;

      const msg = activeConversation.messages.find((m) => m.id === messageId);
      if (!msg?.queryId) return;

      try {
        const response = await fetch(`${API_BASE_URL}/feedback`, {
          method: "POST",
          headers: { "Content-Type": "application/json", ...authHeaders() },
          body: JSON.stringify({
            query_id: msg.queryId,
            rating,
            feedback_text: comment || null,
          }),
        });

        if (response.status === 401) {
          endExpiredSession();
          return;
        }

        if (response.ok) {
          setConversations((prev) =>
            prev.map((c) =>
              c.id === activeConversation.id
                ? {
                    ...c,
                    messages: c.messages.map((m) =>
                      m.id === messageId
                        ? { ...m, feedbackSubmitted: true }
                        : m,
                    ),
                  }
                : c,
            ),
          );
        }
      } catch (err) {
        console.error("Feedback failed:", err);
      }
    },
    [sessionUser, activeConversation, endExpiredSession],
  );

  const handleDownloadCsv = useCallback(
    (messageId: string) => {
      if (!activeConversation) return;
      const msg = activeConversation.messages.find((m) => m.id === messageId);
      if (!msg?.results?.data?.length) return;

      const data = msg.results.data;
      const headers = Object.keys(data[0]);
      const csvContent = [
        headers.join(","),
        ...data.map((row) =>
          headers.map((h) => JSON.stringify(row[h] ?? "")).join(","),
        ),
      ].join("\n");

      const blob = new Blob([csvContent], { type: "text/csv" });
      const url = window.URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `results_${Date.now()}.csv`;
      a.click();
      window.URL.revokeObjectURL(url);
    },
    [activeConversation],
  );

  function handleSignOut() {
    clearSessionUser();
    router.replace("/");
  }

  if (!sessionUser?.name) return null;

  const firstName = sessionUser.name.trim().split(/\s+/)[0];

  return (
    <div className="h-[100dvh] overflow-hidden bg-[#edf0f5] p-0 sm:p-3 lg:p-5">
      <div className="relative flex h-full overflow-hidden bg-[#fbfcfe] sm:rounded-[24px] sm:border sm:border-white/90 sm:shadow-[0_24px_80px_rgba(43,51,78,0.13)]">
        {sidebarOpen && (
          <button
            type="button"
            className="fixed inset-0 z-30 bg-[#1f2638]/20 backdrop-blur-[2px] lg:hidden"
            onClick={() => setSidebarOpen(false)}
            aria-label="Close sidebar"
          />
        )}

        <ChatSidebar
          conversations={conversations}
          activeConversationId={activeId}
          onSelectConversation={selectConversation}
          onCloseSidebar={() => setSidebarOpen(false)}
          onSignOut={handleSignOut}
          userName={sessionUser.name}
          isCollapsed={!sidebarOpen}
        />

        <div className="relative flex min-w-0 flex-1 flex-col bg-[#fbfcfe]">
        <header className="relative z-20 flex h-[72px] shrink-0 items-center justify-between border-b border-[#eceef3] bg-white/75 px-3 backdrop-blur-xl sm:px-5">
          <div className="flex min-w-0 items-center gap-3">
            <button
              type="button"
              onClick={() => setSidebarOpen((o) => !o)}
              className="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl text-[#626c7d] transition-colors hover:bg-[#f2f3f8] hover:text-[#303541] focus:outline-none focus-visible:ring-2 focus-visible:ring-[#7779f5]"
              aria-label="Toggle sidebar"
              aria-expanded={sidebarOpen}
            >
              <svg
                className="h-5 w-5"
                fill="none"
                stroke="currentColor"
                viewBox="0 0 24 24"
              >
                <path
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  strokeWidth={1.5}
                  d="M4 6h16M4 12h16M4 18h16"
                />
              </svg>
            </button>
            {!sidebarOpen && (
              <EverlignLogo
                variant="mark"
                decorative
                className="h-7 w-7 shrink-0 lg:hidden"
              />
            )}
            <div className="min-w-0">
              <p className="truncate text-[13px] font-semibold text-[#343946]">
                {activeConversation?.title || "New conversation"}
              </p>
              {!sidebarOpen && (
                <p className="hidden text-[11px] text-[#7d8695] sm:block">
                  Sequel AI <span className="text-[#a0a6b1]">by Everlign</span>
                </p>
              )}
            </div>
          </div>

          <button
            type="button"
            onClick={startNewChat}
            className="inline-flex h-10 shrink-0 items-center gap-2 rounded-xl bg-[#292d37] px-3.5 text-xs font-semibold text-white shadow-[0_8px_20px_rgba(28,32,43,0.16)] transition-all hover:-translate-y-0.5 hover:bg-[#191c24] focus:outline-none focus-visible:ring-2 focus-visible:ring-[#7779f5] focus-visible:ring-offset-2 sm:px-4"
            aria-label="Start a new chat"
          >
            <svg className="h-4 w-4" fill="none" stroke="currentColor" viewBox="0 0 24 24" aria-hidden>
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 5v14M5 12h14" />
            </svg>
            <span className="hidden sm:inline">New chat</span>
          </button>
        </header>

        <main className="relative isolate flex min-h-0 flex-1 flex-col overflow-hidden">
          <ChatBackgroundEffects />

          {messages.length === 0 ? (
            <div className="relative z-10 min-h-0 flex-1 overflow-y-auto">
              <div
                className={`mx-auto flex min-h-full w-full max-w-[920px] flex-col items-center justify-center px-5 py-10 text-center transition-all duration-700 sm:px-8 ${
                  mounted
                    ? "opacity-100 translate-y-0"
                    : "translate-y-4 opacity-0"
                }`}
              >
                <div className="mb-7 sm:mb-9">
                  <div className="assistant-orb mx-auto mb-7 flex h-[76px] w-[76px] items-center justify-center sm:h-[86px] sm:w-[86px]">
                    <svg
                      className="relative z-10 h-7 w-7 text-white/95 drop-shadow-[0_2px_8px_rgba(80,78,190,0.3)]"
                      fill="none"
                      stroke="currentColor"
                      strokeWidth={1.7}
                      viewBox="0 0 24 24"
                      aria-hidden
                    >
                      <path
                        strokeLinecap="round"
                        strokeLinejoin="round"
                        d="M9.813 15.904 9 18.75l-.813-2.846a4.5 4.5 0 0 0-3.09-3.09L2.25 12l2.846-.813a4.5 4.5 0 0 0 3.09-3.09L9 5.25l.813 2.846a4.5 4.5 0 0 0 3.09 3.09L15.75 12l-2.846.813a4.5 4.5 0 0 0-3.09 3.09ZM18.259 8.715 18 9.75l-.259-1.035a3.375 3.375 0 0 0-2.455-2.456L14.25 6l1.036-.259a3.375 3.375 0 0 0 2.455-2.456L18 2.25l.259 1.035a3.375 3.375 0 0 0 2.456 2.456L21.75 6l-1.035.259a3.375 3.375 0 0 0-2.456 2.456Z"
                      />
                    </svg>
                  </div>
                  <h1 className="text-[28px] font-semibold leading-[1.15] tracking-[-0.045em] text-[#292d36] sm:text-[38px] lg:text-[42px]">
                    <span className="block">{getGreeting()}, {firstName}</span>
                    <span className="mt-1.5 block">
                      How can I{" "}
                      <span className="bg-gradient-to-r from-[#686bf0] via-[#7779f5] to-[#5e78e9] bg-clip-text text-transparent">
                        assist you today?
                      </span>
                    </span>
                  </h1>
                  <p className="mx-auto mt-4 max-w-lg text-sm leading-6 text-[#697386] sm:text-[15px]">
                    Ask a question about your data and get a clear, traceable answer.
                  </p>
                </div>

                <div className="w-full">
                  <ChatInput
                    value={inputValue}
                    onChange={setInputValue}
                    onSubmit={sendMessage}
                    placeholder="Ask anything about your data..."
                    variant="hero"
                  />
                </div>
              </div>
            </div>
          ) : (
            <div className="relative z-10 flex min-h-0 flex-1 flex-col">
              <div className="min-h-0 flex-1 overflow-y-auto scroll-smooth">
                <div className="mx-auto w-full max-w-[940px] px-4 pb-12 pt-8 sm:px-8 sm:pt-10">
                  <ul className="space-y-7 sm:space-y-9">
                    {messages.map((msg, i) => (
                      <li
                        key={msg.id}
                        className="animate-message-in"
                        style={{
                          animationDelay: `${i * 40}ms`,
                          animationFillMode: "backwards",
                        }}
                      >
                        <ChatMessageBlock
                          message={msg}
                          onFeedback={handleFeedback}
                          onDownloadCsv={handleDownloadCsv}
                        />
                      </li>
                    ))}
                  </ul>
                  <div ref={messagesEndRef} />
                </div>
              </div>

              <div className="relative z-10 shrink-0 bg-gradient-to-t from-[#fbfcfe] via-[#fbfcfe]/95 to-transparent px-4 pb-4 pt-3 sm:px-8 sm:pb-6 sm:pt-5">
                <ChatInput
                  value={inputValue}
                  onChange={setInputValue}
                  onSubmit={sendMessage}
                  placeholder="Ask a follow-up question..."
                />
              </div>
            </div>
          )}
        </main>
        </div>
      </div>
    </div>
  );
}
