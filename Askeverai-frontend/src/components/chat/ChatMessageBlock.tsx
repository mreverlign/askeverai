"use client";

import { useState, type ReactNode } from "react";
import type { ChatMessage, TrajectoryStep } from "@/lib/types";
import { ThinkingIndicator } from "./ThinkingIndicator";
import { GeneratedSqlBlock } from "./GeneratedSqlBlock";
import { ResultsSection } from "./ResultsSection";
import { FeedbackSection } from "@/components/feedback/FeedbackSection";

export interface ChatMessageBlockProps {
  message: ChatMessage;
  onFeedback?: (messageId: string, rating: number, comment: string) => void;
  onDownloadCsv?: (messageId: string) => void;
}

interface TrailStep {
  text: string;
  status: "success" | "fail" | "info";
}

const HEADING_PATTERN = /^(#{1,3})\s+(.+)$/;
const UNORDERED_LIST_PATTERN = /^\s*[-*]\s+(.+)$/;
const ORDERED_LIST_PATTERN = /^\s*\d+\.\s+(.+)$/;
const QUOTE_PATTERN = /^\s*>\s?(.+)$/;
const FENCE_PATTERN = /^```(?:[\w-]+)?\s*$/;

function renderInlineMarkdown(text: string, keyPrefix: string): ReactNode[] {
  const nodes: ReactNode[] = [];
  const tokenPattern = /(\*\*[^*\n]+?\*\*|`[^`\n]+?`)/g;
  let cursor = 0;
  let tokenIndex = 0;
  let match: RegExpExecArray | null;

  while ((match = tokenPattern.exec(text)) !== null) {
    if (match.index > cursor) {
      nodes.push(text.slice(cursor, match.index));
    }

    const token = match[0];
    if (token.startsWith("**")) {
      nodes.push(
        <strong
          key={`${keyPrefix}-strong-${tokenIndex}`}
          className="font-semibold text-slate-950"
        >
          {token.slice(2, -2)}
        </strong>,
      );
    } else {
      nodes.push(
        <code
          key={`${keyPrefix}-code-${tokenIndex}`}
          className="rounded bg-slate-100 px-1.5 py-0.5 font-mono text-[0.9em] text-indigo-700 ring-1 ring-slate-200/80"
        >
          {token.slice(1, -1)}
        </code>,
      );
    }

    cursor = tokenPattern.lastIndex;
    tokenIndex += 1;
  }

  if (cursor < text.length) {
    nodes.push(text.slice(cursor));
  }

  return nodes;
}

function MarkdownText({ content, className = "" }: { content: string; className?: string }) {
  const lines = content.replace(/\r\n?/g, "\n").split("\n");
  const blocks: ReactNode[] = [];
  let lineIndex = 0;

  while (lineIndex < lines.length) {
    const line = lines[lineIndex];

    if (!line.trim()) {
      lineIndex += 1;
      continue;
    }

    if (FENCE_PATTERN.test(line)) {
      const codeLines: string[] = [];
      const blockKey = `code-block-${lineIndex}`;
      lineIndex += 1;

      while (lineIndex < lines.length && !FENCE_PATTERN.test(lines[lineIndex])) {
        codeLines.push(lines[lineIndex]);
        lineIndex += 1;
      }

      if (lineIndex < lines.length) lineIndex += 1;
      blocks.push(
        <pre
          key={blockKey}
          className="overflow-x-auto rounded-xl border border-slate-200 bg-slate-50 px-4 py-3 font-mono text-[13px] leading-6 text-slate-700"
        >
          <code>{codeLines.join("\n")}</code>
        </pre>,
      );
      continue;
    }

    const heading = line.match(HEADING_PATTERN);
    if (heading) {
      const headingClasses =
        heading[1].length === 1
          ? "text-xl font-semibold"
          : heading[1].length === 2
            ? "text-lg font-semibold"
            : "text-base font-semibold";
      blocks.push(
        <h3 key={`heading-${lineIndex}`} className={`${headingClasses} text-slate-950`}>
          {renderInlineMarkdown(heading[2], `heading-${lineIndex}`)}
        </h3>,
      );
      lineIndex += 1;
      continue;
    }

    if (UNORDERED_LIST_PATTERN.test(line)) {
      const items: { text: string; sourceIndex: number }[] = [];
      while (lineIndex < lines.length) {
        const item = lines[lineIndex].match(UNORDERED_LIST_PATTERN);
        if (!item) break;
        items.push({ text: item[1], sourceIndex: lineIndex });
        lineIndex += 1;
      }
      blocks.push(
        <ul key={`unordered-list-${items[0].sourceIndex}`} className="list-disc space-y-1.5 pl-5 marker:text-indigo-400">
          {items.map((item) => (
            <li key={item.sourceIndex}>
              {renderInlineMarkdown(item.text, `unordered-${item.sourceIndex}`)}
            </li>
          ))}
        </ul>,
      );
      continue;
    }

    if (ORDERED_LIST_PATTERN.test(line)) {
      const items: { text: string; sourceIndex: number }[] = [];
      while (lineIndex < lines.length) {
        const item = lines[lineIndex].match(ORDERED_LIST_PATTERN);
        if (!item) break;
        items.push({ text: item[1], sourceIndex: lineIndex });
        lineIndex += 1;
      }
      blocks.push(
        <ol key={`ordered-list-${items[0].sourceIndex}`} className="list-decimal space-y-1.5 pl-5 marker:font-medium marker:text-indigo-500">
          {items.map((item) => (
            <li key={item.sourceIndex}>
              {renderInlineMarkdown(item.text, `ordered-${item.sourceIndex}`)}
            </li>
          ))}
        </ol>,
      );
      continue;
    }

    if (QUOTE_PATTERN.test(line)) {
      const quoteLines: string[] = [];
      const blockKey = `quote-${lineIndex}`;
      while (lineIndex < lines.length) {
        const quote = lines[lineIndex].match(QUOTE_PATTERN);
        if (!quote) break;
        quoteLines.push(quote[1]);
        lineIndex += 1;
      }
      blocks.push(
        <blockquote
          key={blockKey}
          className="border-l-2 border-indigo-200 pl-4 text-slate-600"
        >
          {renderInlineMarkdown(quoteLines.join("\n"), blockKey)}
        </blockquote>,
      );
      continue;
    }

    const paragraphStart = lineIndex;
    const paragraphLines = [line];
    lineIndex += 1;
    while (
      lineIndex < lines.length &&
      lines[lineIndex].trim() &&
      !FENCE_PATTERN.test(lines[lineIndex]) &&
      !HEADING_PATTERN.test(lines[lineIndex]) &&
      !UNORDERED_LIST_PATTERN.test(lines[lineIndex]) &&
      !ORDERED_LIST_PATTERN.test(lines[lineIndex]) &&
      !QUOTE_PATTERN.test(lines[lineIndex])
    ) {
      paragraphLines.push(lines[lineIndex]);
      lineIndex += 1;
    }
    blocks.push(
      <p key={`paragraph-${paragraphStart}`} className="whitespace-pre-wrap">
        {renderInlineMarkdown(paragraphLines.join("\n"), `paragraph-${paragraphStart}`)}
      </p>,
    );
  }

  return <div className={`space-y-3 ${className}`}>{blocks}</div>;
}

function ProcessTrail({ message }: { message: ChatMessage }) {
  const steps: TrailStep[] = [];
  const tables = message.relevantTables?.slice(0, 3).join(", ") || "";

  if (message.fallbackUsed) {
    steps.push({ text: "Searched OLAP", status: "fail" });
    steps.push({
      text: "Couldn't find data in OLAP, switching to OLTP",
      status: "info",
    });
    if (tables) {
      steps.push({ text: `Found in ${tables}`, status: "success" });
    }
    steps.push({ text: "Query executed on OLTP", status: "success" });
  } else if (message.recommendedDb === "OLTP" && message.dbSource === "OLTP") {
    steps.push({ text: "Detected explanation query", status: "info" });
    steps.push({ text: "Queried OLTP for memo details", status: "success" });
    if (tables) {
      steps.push({ text: `Found in ${tables}`, status: "success" });
    }
    steps.push({ text: "Query executed", status: "success" });
  } else {
    steps.push({
      text: `Searched ${message.dbSource || "OLAP"}`,
      status: "success",
    });
    if (tables) {
      steps.push({ text: `Found in ${tables}`, status: "success" });
    }
    steps.push({ text: "Generated SQL", status: "success" });
    steps.push({ text: "Query executed", status: "success" });
  }

  if (steps.length === 0) return null;

  return (
    <div
      className="flex flex-wrap items-center gap-x-1.5 gap-y-2 rounded-xl border border-slate-200/80 bg-white/75 px-3 py-2 text-xs text-slate-600 shadow-sm shadow-slate-200/40 animate-block-in"
      style={{ animationFillMode: "backwards" }}
    >
      {steps.map((step, i) => (
        <span key={i} className="flex items-center gap-1">
          {i > 0 && (
            <svg
              className="h-3 w-3 text-slate-300"
              fill="none"
              stroke="currentColor"
              viewBox="0 0 24 24"
              aria-hidden
            >
              <path
                strokeLinecap="round"
                strokeLinejoin="round"
                strokeWidth={2}
                d="M9 5l7 7-7 7"
              />
            </svg>
          )}
          {step.status === "success" && (
            <svg
              className="h-3.5 w-3.5 text-emerald-600"
              fill="none"
              stroke="currentColor"
              viewBox="0 0 24 24"
              aria-hidden
            >
              <path
                strokeLinecap="round"
                strokeLinejoin="round"
                strokeWidth={2.5}
                d="M5 13l4 4L19 7"
              />
            </svg>
          )}
          {step.status === "fail" && (
            <svg
              className="h-3.5 w-3.5 text-amber-600"
              fill="none"
              stroke="currentColor"
              viewBox="0 0 24 24"
              aria-hidden
            >
              <path
                strokeLinecap="round"
                strokeLinejoin="round"
                strokeWidth={2}
                d="M6 18L18 6M6 6l12 12"
              />
            </svg>
          )}
          {step.status === "info" && (
            <svg
              className="h-3.5 w-3.5 text-indigo-500"
              fill="none"
              stroke="currentColor"
              viewBox="0 0 24 24"
              aria-hidden
            >
              <path
                strokeLinecap="round"
                strokeLinejoin="round"
                strokeWidth={2}
                d="M13 16h-1v-4h-1m1-4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z"
              />
            </svg>
          )}
          <span>{step.text}</span>
        </span>
      ))}
    </div>
  );
}

function TrajectorySection({ trajectory }: { trajectory: TrajectoryStep[] }) {
  const [isOpen, setIsOpen] = useState(false);

  if (!trajectory.length) return null;

  return (
    <div className="overflow-hidden">
      <button
        type="button"
        onClick={() => setIsOpen(!isOpen)}
        className="flex items-center gap-2 rounded-lg py-1 text-xs font-medium text-slate-600 transition-colors hover:text-slate-950 focus:outline-none focus-visible:ring-2 focus-visible:ring-indigo-400/50"
        aria-expanded={isOpen}
      >
        <svg
          className={`w-3.5 h-3.5 transition-transform ${isOpen ? "rotate-90" : ""}`}
          fill="none"
          stroke="currentColor"
          viewBox="0 0 24 24"
        >
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 5l7 7-7 7" />
        </svg>
        View reasoning ({trajectory.length} steps)
      </button>
      {isOpen && (
        <div className="mt-3 space-y-2 rounded-xl border border-slate-200 bg-slate-50/80 p-3">
          {trajectory.map((step, idx) => (
            <div
              key={idx}
              className="rounded-lg border border-slate-200/70 bg-white px-3 py-2.5"
            >
              <div className="flex items-center gap-2 mb-1">
                {step.type === "thought" && (
                  <span className="text-[10px] font-semibold uppercase tracking-wider text-indigo-600">
                    Thought
                  </span>
                )}
                {step.type === "action" && (
                  <span className="text-[10px] font-semibold uppercase tracking-wider text-emerald-700">
                    Action: {step.tool || "sql_query"}
                  </span>
                )}
                {step.type === "answer" && (
                  <span className="text-[10px] font-semibold uppercase tracking-wider text-violet-700">
                    Answer
                  </span>
                )}
              </div>
              <div className="text-xs leading-relaxed text-slate-600">
                {step.type === "action" ? (
                  <>
                    <pre className="mt-1 overflow-x-auto whitespace-pre-wrap rounded-lg border border-slate-200 bg-slate-50 p-2.5 font-mono text-[11px] text-slate-700">
                      {step.input}
                    </pre>
                    {step.output && (
                      <div className="mt-1.5">
                        {step.output.success ? (
                          <span className="text-[11px] font-medium text-emerald-700">
                            {step.output.message}
                          </span>
                        ) : (
                          <span className="text-[11px] font-medium text-red-600">
                            {step.output.error}
                          </span>
                        )}
                      </div>
                    )}
                  </>
                ) : (
                  <span className="whitespace-pre-wrap">{step.content}</span>
                )}
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

function SourceBadges({ message }: { message: ChatMessage }) {
  const items: { label: string; muted?: boolean }[] = [];

  if (message.dbSource) {
    items.push({ label: message.dbSource });
  }
  if (message.fallbackUsed) {
    items.push({ label: "Fallback" });
  }
  if (message.metadata?.row_count != null) {
    items.push({
      label: `${message.metadata.row_count.toLocaleString()} rows`,
      muted: true,
    });
  }
  if (message.metadata?.total_time != null) {
    items.push({ label: `${message.metadata.total_time.toFixed(2)}s`, muted: true });
  }
  if (message.metadata?.iterations != null) {
    items.push({ label: `${message.metadata.iterations} steps`, muted: true });
  }

  if (items.length === 0) return null;

  return (
    <div className="flex flex-wrap items-center gap-1.5">
      {items.map((item, idx) => (
        <span
          key={idx}
          className={`inline-flex items-center rounded-md border px-2 py-1 text-[11px] font-medium ${
            item.muted
              ? "border-slate-200 bg-slate-50 text-slate-600"
              : "border-indigo-100 bg-indigo-50 text-indigo-700"
          }`}
        >
          {item.label}
        </span>
      ))}
    </div>
  );
}

export function ChatMessageBlock({
  message,
  onFeedback,
  onDownloadCsv,
}: ChatMessageBlockProps) {
  const isUser = message.role === "user";

  if (isUser) {
    return (
      <article className="py-2.5" aria-label="Your message">
        <div className="flex items-start gap-3.5">
          <div className="mt-0.5 flex h-8 w-8 flex-shrink-0 items-center justify-center rounded-full border border-indigo-100 bg-indigo-50 shadow-sm">
            <svg
              className="h-4 w-4 text-indigo-600"
              fill="none"
              stroke="currentColor"
              viewBox="0 0 24 24"
              aria-hidden
            >
              <path
                strokeLinecap="round"
                strokeLinejoin="round"
                strokeWidth={2}
                d="M16 7a4 4 0 11-8 0 4 4 0 018 0zM12 14a7 7 0 00-7 7h14a7 7 0 00-7-7z"
              />
            </svg>
          </div>
          <div className="min-w-0 flex-1 pt-1">
            <p className="break-words text-[15px] font-semibold leading-7 text-slate-950">
              {message.content}
            </p>
          </div>
        </div>
      </article>
    );
  }

  const showProcessTrail =
    !message.isLoading && (message.dbSource || message.fallbackUsed);

  return (
    <article className="py-2.5" aria-label="Assistant response">
      <div className="flex items-start gap-3.5">
        <div className="mt-0.5 flex h-8 w-8 flex-shrink-0 items-center justify-center rounded-full border border-indigo-100 bg-gradient-to-br from-indigo-50 via-violet-50 to-cyan-50 shadow-sm">
          <svg
            className="h-4 w-4 text-indigo-600"
            fill="none"
            stroke="currentColor"
            strokeWidth={1.7}
            viewBox="0 0 24 24"
            aria-hidden
          >
            <path
              strokeLinecap="round"
              strokeLinejoin="round"
              d="M9.813 15.904L9 18.75l-.813-2.846a4.5 4.5 0 00-3.09-3.09L2.25 12l2.846-.813a4.5 4.5 0 003.09-3.09L9 5.25l.813 2.846a4.5 4.5 0 003.09 3.09L15.75 12l-2.846.813a4.5 4.5 0 00-3.09 3.09z"
            />
          </svg>
        </div>
        <div className="min-w-0 flex-1 space-y-3.5 pt-0.5">
          {message.isLoading && <ThinkingIndicator />}

          {showProcessTrail && <ProcessTrail message={message} />}

          {!message.isLoading && message.answer && (
            <div
              className="animate-block-in"
              style={{ animationFillMode: "backwards" }}
            >
              <MarkdownText
                content={message.answer}
                className="break-words text-[15px] leading-7 text-slate-700"
              />
            </div>
          )}

          {!message.isLoading && !message.answer && message.content && (
            <MarkdownText
              content={message.content}
              className="break-words text-[15px] leading-7 text-slate-700"
            />
          )}

          {!message.isLoading && <SourceBadges message={message} />}

          {!message.isLoading && message.generatedSql && (
            <div
              className="animate-block-in"
              style={{
                animationDelay: "50ms",
                animationFillMode: "backwards",
              }}
            >
              <GeneratedSqlBlock sql={message.generatedSql} />
            </div>
          )}

          {!message.isLoading && message.results && (
            <div
              className="animate-block-in"
              style={{
                animationDelay: "100ms",
                animationFillMode: "backwards",
              }}
            >
              <ResultsSection
                result={message.results}
                onDownloadCsv={
                  onDownloadCsv ? () => onDownloadCsv(message.id) : undefined
                }
              />
            </div>
          )}

          {!message.isLoading &&
            message.trajectory &&
            message.trajectory.length > 0 && (
              <TrajectorySection trajectory={message.trajectory} />
            )}

          {!message.isLoading && message.queryId && (
            <FeedbackSection messageId={message.id} onFeedback={onFeedback} />
          )}
        </div>
      </div>
    </article>
  );
}
