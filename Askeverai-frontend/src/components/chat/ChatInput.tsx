"use client";

import { useEffect, useRef } from "react";

export interface ChatInputProps {
  value: string;
  onChange: (value: string) => void;
  onSubmit: () => void;
  disabled?: boolean;
  placeholder?: string;
  variant?: "default" | "hero";
  "aria-label"?: string;
}

function SparkleIcon() {
  return (
    <svg
      className="h-5 w-5"
      fill="none"
      stroke="currentColor"
      strokeWidth={1.8}
      viewBox="0 0 24 24"
      aria-hidden
    >
      <path
        strokeLinecap="round"
        strokeLinejoin="round"
        d="M9.813 15.904 9 18.75l-.813-2.846a4.5 4.5 0 0 0-3.09-3.09L2.25 12l2.846-.813a4.5 4.5 0 0 0 3.09-3.09L9 5.25l.813 2.846a4.5 4.5 0 0 0 3.09 3.09L15.75 12l-2.846.813a4.5 4.5 0 0 0-3.09 3.09ZM18.259 8.715 18 9.75l-.259-1.035a3.375 3.375 0 0 0-2.455-2.456L14.25 6l1.036-.259a3.375 3.375 0 0 0 2.455-2.456L18 2.25l.259 1.035a3.375 3.375 0 0 0 2.456 2.456L21.75 6l-1.035.259a3.375 3.375 0 0 0-2.456 2.456Z"
      />
    </svg>
  );
}

export function ChatInput({
  value,
  onChange,
  onSubmit,
  disabled,
  placeholder = "Ask anything about your data...",
  variant = "default",
  "aria-label": ariaLabel = "Chat message",
}: ChatInputProps) {
  const inputRef = useRef<HTMLTextAreaElement>(null);
  const isHero = variant === "hero";

  useEffect(() => {
    const element = inputRef.current;
    if (!element) return;

    element.style.height = "auto";
    element.style.height = `${Math.min(element.scrollHeight, isHero ? 220 : 160)}px`;
  }, [isHero, value]);

  function handleKeyDown(event: React.KeyboardEvent<HTMLTextAreaElement>) {
    if (event.key === "Enter" && !event.shiftKey) {
      event.preventDefault();
      onSubmit();
    }
  }

  return (
    <div className={`mx-auto w-full ${isHero ? "max-w-[790px]" : "max-w-[900px]"}`}>
      <div
        className={`group relative overflow-hidden border bg-white/90 backdrop-blur-xl transition-all duration-300 focus-within:border-[#a4a6fb] focus-within:bg-white focus-within:ring-4 focus-within:ring-[#7779f5]/10 ${
          isHero
            ? "min-h-[142px] rounded-[24px] border-[#e2e3f2] shadow-[0_20px_60px_rgba(80,83,155,0.11),0_0_0_8px_rgba(119,121,245,0.025)] sm:min-h-[158px]"
            : "min-h-[62px] rounded-[20px] border-[#e1e4eb] shadow-[0_12px_36px_rgba(52,61,90,0.08)]"
        }`}
      >
        <span
          className={`pointer-events-none absolute left-5 text-[#7477ec] transition-transform duration-300 group-focus-within:scale-110 ${
            isHero ? "top-[21px] sm:left-6 sm:top-6" : "top-[21px]"
          }`}
        >
          <SparkleIcon />
        </span>

        <textarea
          ref={inputRef}
          value={value}
          onChange={(event) => onChange(event.target.value)}
          onKeyDown={handleKeyDown}
          disabled={disabled}
          placeholder={placeholder}
          aria-label={ariaLabel}
          rows={1}
          className={`block w-full resize-none bg-transparent text-[15px] leading-6 text-[#303541] placeholder:text-[#8992a1] focus:outline-none disabled:cursor-not-allowed disabled:opacity-60 ${
            isHero
              ? "min-h-[142px] max-h-[220px] px-5 pb-[68px] pl-12 pt-5 sm:min-h-[158px] sm:px-6 sm:pb-[72px] sm:pl-14 sm:pt-6"
              : "min-h-[60px] max-h-[160px] px-5 pb-4 pl-12 pr-[72px] pt-[18px]"
          }`}
        />

        {isHero && (
          <span className="pointer-events-none absolute bottom-5 left-5 hidden text-[11px] font-medium text-[#9aa2af] sm:left-6 sm:block">
            Press Enter to send · Shift + Enter for a new line
          </span>
        )}

        <button
          type="button"
          onClick={onSubmit}
          disabled={disabled || !value.trim()}
          className={`absolute flex items-center justify-center bg-[#696cf0] text-white shadow-[0_8px_22px_rgba(105,108,240,0.28)] transition-all duration-200 hover:-translate-y-0.5 hover:bg-[#5b5ee4] hover:shadow-[0_10px_26px_rgba(105,108,240,0.34)] focus:outline-none focus-visible:ring-2 focus-visible:ring-[#696cf0] focus-visible:ring-offset-2 disabled:translate-y-0 disabled:cursor-not-allowed disabled:bg-[#c9cbe8] disabled:shadow-none ${
            isHero
              ? "bottom-4 right-4 h-11 w-11 rounded-[14px] sm:bottom-5 sm:right-5"
              : "bottom-[9px] right-[10px] h-11 w-11 rounded-[14px]"
          }`}
          aria-label="Send message"
        >
          <svg className="h-5 w-5" fill="none" stroke="currentColor" viewBox="0 0 24 24" aria-hidden>
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="m5 12 14-7-4.5 14-3-6.5L5 12Zm6.5.5L19 5" />
          </svg>
        </button>
      </div>
    </div>
  );
}
