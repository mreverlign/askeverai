"use client";

import type { Conversation } from "@/lib/types";
import { EverlignLogo } from "@/components/brand/EverlignLogo";

export interface ChatSidebarProps {
  conversations: Conversation[];
  activeConversationId: string | null;
  onSelectConversation: (id: string) => void;
  onCloseSidebar?: () => void;
  onSignOut: () => void;
  userName: string;
  isCollapsed?: boolean;
  className?: string;
}

export function ChatSidebar({
  conversations,
  activeConversationId,
  onSelectConversation,
  onCloseSidebar,
  onSignOut,
  userName,
  isCollapsed,
  className = "",
}: ChatSidebarProps) {
  if (isCollapsed) return null;

  const initial = userName.trim().charAt(0).toUpperCase() || "A";

  return (
    <aside
      className={`absolute inset-y-0 left-0 z-40 flex w-[282px] shrink-0 flex-col border-r border-[#e8eaf1] bg-[#f9fafc]/95 shadow-2xl shadow-slate-900/10 backdrop-blur-xl lg:relative lg:z-20 lg:shadow-none ${className}`}
      aria-label="Recent conversations"
    >
      <div className="flex h-[76px] shrink-0 items-center justify-between px-5">
        <div className="flex items-center gap-3">
          <span className="flex h-10 w-10 items-center justify-center rounded-[14px] bg-white shadow-[0_8px_24px_rgba(82,74,180,0.14)] ring-1 ring-[#e7e8f2]">
            <EverlignLogo
              variant="mark"
              decorative
              className="h-7 w-7"
            />
          </span>
          <div>
            <p className="text-[15px] font-semibold tracking-[-0.02em] text-[#252832]">
              AskEver AI
            </p>
            <p className="mt-0.5 text-[10px] font-medium tracking-[0.025em] text-[#8a91a0]">
              by Everlign
            </p>
          </div>
        </div>

        {onCloseSidebar && (
          <button
            type="button"
            onClick={onCloseSidebar}
            className="flex h-10 w-10 items-center justify-center rounded-xl text-[#697386] transition-colors hover:bg-white hover:text-[#303541] focus:outline-none focus-visible:ring-2 focus-visible:ring-[#7779f5] lg:hidden"
            aria-label="Close sidebar"
          >
            <svg className="h-5 w-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.8} d="M6 18 18 6M6 6l12 12" />
            </svg>
          </button>
        )}
      </div>

      <div className="px-5 pb-3 pt-4">
        <h2 className="text-[11px] font-semibold uppercase tracking-[0.14em] text-[#727c8d]">
          History
        </h2>
      </div>

      <nav className="min-h-0 flex-1 overflow-y-auto px-3 pb-4" aria-label="Conversation history">
        {conversations.length > 0 ? (
          <ul className="space-y-1">
            {conversations.map((conversation) => {
              const isActive = activeConversationId === conversation.id;

              return (
                <li key={conversation.id}>
                  <button
                    type="button"
                    onClick={() => onSelectConversation(conversation.id)}
                    className={`group flex w-full items-center gap-3 rounded-[13px] px-3 py-2.5 text-left text-[13px] font-medium transition-all focus:outline-none focus-visible:ring-2 focus-visible:ring-[#7779f5] ${
                      isActive
                        ? "bg-[#eeefff] text-[#3f438f] shadow-[inset_0_0_0_1px_rgba(119,121,245,0.08)]"
                        : "text-[#596273] hover:bg-white hover:text-[#303541]"
                    }`}
                    aria-label={`Open conversation: ${conversation.title}`}
                    aria-current={isActive ? "page" : undefined}
                  >
                    <span
                      className={`flex h-7 w-7 shrink-0 items-center justify-center rounded-lg ${
                        isActive
                          ? "bg-white/80 text-[#696cf0]"
                          : "bg-[#f0f2f6] text-[#818a99] group-hover:bg-[#f6f6ff] group-hover:text-[#696cf0]"
                      }`}
                    >
                      <svg className="h-3.5 w-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24" aria-hidden>
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.7} d="M8 12h.01M12 12h.01M16 12h.01M21 12c0 4.418-4.03 8-9 8a9.9 9.9 0 0 1-4.255-.949L3 20l1.395-3.72A7.2 7.2 0 0 1 3 12c0-4.418 4.03-8 9-8s9 3.582 9 8Z" />
                      </svg>
                    </span>
                    <span className="min-w-0 flex-1 truncate">{conversation.title}</span>
                  </button>
                </li>
              );
            })}
          </ul>
        ) : (
          <div className="mx-2 mt-2 rounded-2xl border border-dashed border-[#dfe3eb] bg-white/55 px-4 py-6 text-center">
            <span className="mx-auto flex h-9 w-9 items-center justify-center rounded-xl bg-[#f0f1ff] text-[#7275e9]">
              <svg className="h-4 w-4" fill="none" stroke="currentColor" viewBox="0 0 24 24" aria-hidden>
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.7} d="M8 12h.01M12 12h.01M16 12h.01M21 12c0 4.418-4.03 8-9 8a9.9 9.9 0 0 1-4.255-.949L3 20l1.395-3.72A7.2 7.2 0 0 1 3 12c0-4.418 4.03-8 9-8s9 3.582 9 8Z" />
              </svg>
            </span>
            <p className="mt-3 text-xs font-medium text-[#596273]">No conversations yet</p>
            <p className="mt-1 text-[11px] leading-5 text-[#8a93a1]">
              Your recent questions will appear here.
            </p>
          </div>
        )}
      </nav>

      <div className="shrink-0 border-t border-[#eaecf2] p-3">
        <div className="flex items-center gap-3 rounded-2xl bg-white px-3 py-2.5 shadow-[0_6px_20px_rgba(40,50,80,0.05)] ring-1 ring-[#eceef3]">
          <span className="flex h-9 w-9 shrink-0 items-center justify-center rounded-full bg-gradient-to-br from-[#f0e9ff] to-[#dff7f8] text-sm font-semibold text-[#5659bf]">
            {initial}
          </span>
          <div className="min-w-0 flex-1">
            <p className="truncate text-[13px] font-semibold text-[#303541]">{userName}</p>
            <p className="text-[11px] text-[#7b8493]">Signed in</p>
          </div>
          <button
            type="button"
            onClick={onSignOut}
            className="flex h-9 w-9 shrink-0 items-center justify-center rounded-xl text-[#70798a] transition-colors hover:bg-[#f5f6fa] hover:text-[#333846] focus:outline-none focus-visible:ring-2 focus-visible:ring-[#7779f5]"
            aria-label="Sign out"
            title="Sign out"
          >
            <svg className="h-4 w-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.8} d="M15.75 9V5.25A2.25 2.25 0 0 0 13.5 3h-6a2.25 2.25 0 0 0-2.25 2.25v13.5A2.25 2.25 0 0 0 7.5 21h6a2.25 2.25 0 0 0 2.25-2.25V15M12 9l-3 3m0 0 3 3m-3-3h12.75" />
            </svg>
          </button>
        </div>
      </div>
    </aside>
  );
}
