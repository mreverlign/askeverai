"use client";

import { useState, useEffect } from "react";

const STEPS = [
  "Analyzing your question...",
  "Searching databases...",
  "Generating SQL...",
  "Running query...",
  "Processing results...",
];

const STEP_INTERVAL = 2200;

export function ThinkingIndicator({ message = "Processing..." }: { message?: string }) {
  const [currentStep, setCurrentStep] = useState(0);

  useEffect(() => {
    const interval = setInterval(() => {
      setCurrentStep((prev) => (prev + 1 < STEPS.length ? prev + 1 : prev));
    }, STEP_INTERVAL);
    return () => clearInterval(interval);
  }, []);

  return (
    <div
      className="py-3 animate-block-in"
      role="status"
      aria-live="polite"
      aria-label={message}
    >
      <div className="flex items-start gap-3">
        <div className="relative mt-1">
          <div className="h-5 w-5 animate-spin rounded-full border-2 border-indigo-200 border-t-indigo-600" />
          <div className="absolute inset-0 h-5 w-5 animate-pulse-soft rounded-full bg-indigo-500/10" />
        </div>
        <div className="flex-1 space-y-2.5">
          <p className="text-[15px] font-medium text-slate-800">{STEPS[currentStep]}</p>

          <div className="space-y-1.5">
            {STEPS.map((step, i) => {
              if (i > currentStep) return null;
              const isDone = i < currentStep;

              return (
                <div
                  key={i}
                  className="flex items-center gap-2 animate-step-in"
                  style={{ animationDelay: `${i * 30}ms`, animationFillMode: "backwards" }}
                >
                  {isDone ? (
                    <svg className="h-3.5 w-3.5 animate-check-in text-emerald-600" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2.5} d="M5 13l4 4L19 7" />
                    </svg>
                  ) : (
                    <div className="flex h-3.5 w-3.5 items-center justify-center">
                      <div className="h-1.5 w-1.5 animate-pulse-soft rounded-full bg-indigo-600" />
                    </div>
                  )}
                  <span className={`text-xs ${isDone ? "text-slate-500" : "font-medium text-slate-700"}`}>
                    {step}
                  </span>
                </div>
              );
            })}
          </div>

          <div className="h-1 max-w-xs overflow-hidden rounded-full bg-slate-200">
            <div
              className="h-full rounded-full bg-gradient-to-r from-indigo-600 to-cyan-400 transition-all duration-700 ease-out"
              style={{ width: `${((currentStep + 1) / STEPS.length) * 100}%` }}
            />
          </div>
        </div>
      </div>
    </div>
  );
}
