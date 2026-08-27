"use client";

import { useState, useCallback, useEffect } from "react";

export interface FeedbackSectionProps {
  messageId: string;
  onFeedback?: (messageId: string, rating: number, comment: string) => void;
  className?: string;
}

const StarIcon = ({ filled }: { filled: boolean }) => (
  <svg
    className={`h-6 w-6 shrink-0 ${filled ? "text-amber-400" : "text-slate-300"}`}
    fill={filled ? "currentColor" : "none"}
    stroke="currentColor"
    strokeWidth={1.5}
    viewBox="0 0 24 24"
    aria-hidden
  >
    <path
      strokeLinecap="round"
      strokeLinejoin="round"
      d="M11.48 3.499a.562.562 0 011.04 0l2.125 5.111a.563.563 0 00.475.345l5.518.442c.499.04.701.663.321.988l-4.204 3.602a.563.563 0 00-.182.557l1.285 5.385a.562.562 0 01-.84.61l-4.725-2.885a.563.563 0 00-.586 0L6.982 20.54a.562.562 0 01-.84-.61l1.285-5.386a.562.562 0 00-.182-.557l-4.204-3.602a.563.563 0 01.321-.988l5.518-.442a.563.563 0 00.475-.345L11.48 3.5z"
    />
  </svg>
);

const SparkleIcon = ({ className = "w-4 h-4" }: { className?: string }) => (
  <svg className={`shrink-0 ${className}`} fill="none" stroke="currentColor" strokeWidth={1.8} viewBox="0 0 24 24" aria-hidden>
    <path strokeLinecap="round" strokeLinejoin="round" d="M9.813 15.904L9 18.75l-.813-2.846a4.5 4.5 0 00-3.09-3.09L2.25 12l2.846-.813a4.5 4.5 0 003.09-3.09L9 5.25l.813 2.846a4.5 4.5 0 003.09 3.09L15.75 12l-2.846.813a4.5 4.5 0 00-3.09 3.09zM18.259 8.715L18 9.75l-.259-1.035a3.375 3.375 0 00-2.455-2.456L14.25 6l1.036-.259a3.375 3.375 0 002.455-2.456L18 2.25l.259 1.035a3.375 3.375 0 002.456 2.456L21.75 6l-1.035.259a3.375 3.375 0 00-2.456 2.456zM16.894 20.567L16.5 21.75l-.394-1.183a2.25 2.25 0 00-1.423-1.423L13.5 18.75l1.183-.394a2.25 2.25 0 001.423-1.423l.394-1.183.394 1.183a2.25 2.25 0 001.423 1.423l1.183.394-1.183.394a2.25 2.25 0 00-1.423 1.423z" />
  </svg>
);

function FeedbackModalContent({
  onClose,
  onSubmit,
}: {
  onClose: () => void;
  onSubmit: (rating: number, comment: string) => void;
}) {
  const [rating, setRating] = useState(0);
  const [comment, setComment] = useState("");

  const handleSubmit = useCallback(() => {
    if (rating === 0) return;
    onSubmit(rating, comment);
  }, [rating, comment, onSubmit]);

  const handleKeyDown = useCallback(
    (e: React.KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    },
    [onClose]
  );

  return (
    <div
      className="relative w-full max-w-xl animate-modal-in overflow-hidden rounded-3xl border border-slate-200 bg-white shadow-2xl shadow-slate-900/20"
      onKeyDown={handleKeyDown}
      role="dialog"
      aria-modal="true"
      aria-labelledby="feedback-modal-title"
    >
      <div className="absolute inset-0 pointer-events-none overflow-hidden" aria-hidden>
        <div className="absolute inset-0 bg-gradient-to-br from-indigo-50/80 via-white to-cyan-50/70" />
        <div className="absolute left-1/4 top-0 h-64 w-64 animate-pulse-soft rounded-full bg-indigo-300/20 blur-3xl" />
        <div className="absolute bottom-0 right-1/4 h-48 w-48 animate-pulse-soft rounded-full bg-cyan-300/20 blur-3xl" style={{ animationDelay: "1s" }} />
      </div>
      <div className="relative px-6 py-6 sm:px-8 sm:py-8">
        <div className="mb-5 flex items-center justify-between gap-4">
          <div className="flex items-center gap-3">
            <span className="flex h-11 w-11 animate-bounce-soft items-center justify-center rounded-xl border border-indigo-100 bg-indigo-50 text-indigo-600 shadow-sm">
              <SparkleIcon className="w-6 h-6" />
            </span>
            <h2 id="feedback-modal-title" className="text-xl font-semibold text-slate-950">
              Rate this response
            </h2>
          </div>
          <button
            type="button"
            onClick={onClose}
            className="rounded-lg p-2 text-slate-500 transition-colors hover:bg-slate-100 hover:text-slate-950 focus:outline-none focus-visible:ring-2 focus-visible:ring-indigo-500/40"
            aria-label="Close"
          >
            <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
            </svg>
          </button>
        </div>

        <p className="mb-6 text-sm leading-6 text-slate-600 sm:text-base">Your feedback helps improve Sequel AI.</p>

        <div className="flex items-center gap-1.5 mb-6">
          {[1, 2, 3, 4, 5].map((value) => (
            <button
              key={value}
              type="button"
              onClick={() => setRating(value)}
              className="rounded-md p-1 transition-transform hover:scale-105 focus:outline-none focus-visible:ring-2 focus-visible:ring-indigo-500/50 focus-visible:ring-offset-2 focus-visible:ring-offset-white"
              aria-pressed={rating === value}
              aria-label={`${value} star${value === 1 ? "" : "s"}`}
            >
              <StarIcon filled={value <= rating} />
            </button>
          ))}
        </div>

        <textarea
          value={comment}
          onChange={(e) => setComment(e.target.value)}
          placeholder="What worked well or could be improved?"
          rows={5}
          className="mb-6 min-h-[112px] w-full resize-y rounded-xl border border-slate-200 bg-white px-4 py-3 text-sm text-slate-900 shadow-sm placeholder:text-slate-500 focus:border-indigo-400 focus:outline-none focus:ring-4 focus:ring-indigo-500/10"
          aria-label="Additional feedback (optional)"
        />

        <div className="flex gap-3">
          <button
            type="button"
            onClick={onClose}
            className="flex-1 rounded-xl border border-slate-200 bg-white px-5 py-3 text-sm font-medium text-slate-700 transition-colors hover:border-slate-300 hover:bg-slate-50 hover:text-slate-950 focus:outline-none focus-visible:ring-2 focus-visible:ring-indigo-500/40"
          >
            Cancel
          </button>
          <button
            type="button"
            onClick={handleSubmit}
            disabled={rating === 0}
            className="flex-1 rounded-xl bg-indigo-600 px-5 py-3 text-sm font-medium text-white shadow-lg shadow-indigo-500/20 transition-all hover:bg-indigo-500 focus:outline-none focus-visible:ring-2 focus-visible:ring-indigo-500 focus-visible:ring-offset-2 focus-visible:ring-offset-white disabled:cursor-not-allowed disabled:opacity-50 disabled:shadow-none"
          >
            Submit feedback
          </button>
        </div>
      </div>
    </div>
  );
}

export function FeedbackSection({
  messageId,
  onFeedback,
  className = "",
}: FeedbackSectionProps) {
  const [isOpen, setIsOpen] = useState(false);
  const [submitted, setSubmitted] = useState(false);

  const handleSubmitFromModal = useCallback(
    (rating: number, comment: string) => {
      onFeedback?.(messageId, rating, comment);
      setSubmitted(true);
      setIsOpen(false);
    },
    [messageId, onFeedback]
  );

  useEffect(() => {
    if (!isOpen) return;
    const handleEscape = (e: KeyboardEvent) => {
      if (e.key === "Escape") setIsOpen(false);
    };
    window.addEventListener("keydown", handleEscape);
    return () => window.removeEventListener("keydown", handleEscape);
  }, [isOpen]);

  if (submitted) {
    return (
      <div
        className={`flex items-center gap-2 text-sm text-slate-600 ${className}`}
        role="status"
        aria-label="Feedback submitted"
      >
        <span className="text-emerald-600" aria-hidden>✓</span>
        Thanks for your feedback
      </div>
    );
  }

  return (
    <>
      <button
        type="button"
        onClick={() => setIsOpen(true)}
        className={`inline-flex w-fit items-center gap-1.5 rounded-full border border-slate-200 bg-white px-2.5 py-1.5 text-xs font-medium text-slate-600 shadow-sm transition-all duration-200 hover:border-indigo-200 hover:bg-indigo-50 hover:text-indigo-700 focus:outline-none focus-visible:ring-2 focus-visible:ring-indigo-500/40 focus-visible:ring-offset-2 focus-visible:ring-offset-white ${className}`}
        aria-label="Rate this response"
      >
        <span className="animate-bounce-soft inline-flex">
          <SparkleIcon />
        </span>
        <span>Rate response</span>
      </button>

      {isOpen && (
        <div
          className="fixed inset-0 z-50 flex animate-backdrop-in items-center justify-center bg-slate-950/35 p-4 backdrop-blur-sm"
          role="presentation"
          onClick={() => setIsOpen(false)}
        >
          <div
            className="transition-all duration-200 origin-center"
            onClick={(e) => e.stopPropagation()}
          >
            <FeedbackModalContent onClose={() => setIsOpen(false)} onSubmit={handleSubmitFromModal} />
          </div>
        </div>
      )}
    </>
  );
}
