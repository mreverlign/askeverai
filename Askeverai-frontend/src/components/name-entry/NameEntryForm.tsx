"use client";

import { useEffect, useState } from "react";

export interface NameEntryFormProps {
  onSubmit: (name: string) => void;
}

export function NameEntryForm({ onSubmit }: NameEntryFormProps) {
  const [name, setName] = useState("");
  const [error, setError] = useState("");
  const [visible, setVisible] = useState(false);

  useEffect(() => {
    const timer = setTimeout(() => setVisible(true), 50);
    return () => clearTimeout(timer);
  }, []);

  function handleSubmit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const trimmedName = name.trim();

    if (!trimmedName) {
      setError("Please enter your name");
      return;
    }

    setError("");
    onSubmit(trimmedName);
  }

  return (
    <main className="fixed inset-0 z-[60] overflow-y-auto bg-transparent px-4 py-5 sm:px-7 sm:py-8 lg:px-10">
      <div className="relative flex min-h-full items-center justify-center">
        <section
          className={`grid w-full max-w-[440px] overflow-hidden rounded-[28px] border border-white/70 bg-transparent shadow-[0_32px_100px_rgba(30,31,55,0.24)] transition-all duration-700 sm:rounded-[34px] lg:min-h-[660px] lg:max-w-[1200px] lg:grid-cols-[1.06fr_0.94fr] ${
            visible
              ? "translate-y-0 scale-100 opacity-100"
              : "translate-y-4 scale-[0.985] opacity-0"
          }`}
        >
          <div className="relative hidden overflow-hidden border-r border-white/10 bg-[#0a0e20] lg:flex lg:flex-col">
            <div
              className="pointer-events-none absolute inset-0 bg-[radial-gradient(circle_at_18%_18%,rgba(41,243,253,0.15),transparent_32%),radial-gradient(circle_at_82%_72%,rgba(125,80,254,0.2),transparent_36%)]"
              aria-hidden
            />
            <div
              className="pointer-events-none absolute -left-24 top-24 h-80 w-80 rounded-full border border-white/[0.06]"
              aria-hidden
            />
            <div
              className="pointer-events-none absolute -right-16 bottom-12 h-64 w-64 rounded-full border border-white/[0.05]"
              aria-hidden
            />
            <div
              className="pointer-events-none absolute inset-x-0 bottom-0 h-[72%] bg-gradient-to-t from-[#060a18]/95 via-[#080c1c]/65 to-transparent"
              aria-hidden
            />

            <p className="relative m-10 text-xs font-semibold uppercase tracking-[0.3em] text-white/55 xl:m-12">
              AskEver AI
            </p>

            <div className="relative mt-auto max-w-[530px] p-10 pt-24 xl:p-14 xl:pt-28">
              <h2 className="text-[44px] font-semibold leading-[1.06] tracking-[-0.05em] text-white drop-shadow-[0_3px_20px_rgba(0,0,0,0.3)] xl:text-[51px]">
                Your data has answers.
                <span className="mt-1 block bg-gradient-to-r from-[#9cf5f7] via-[#9ca9ff] to-[#b795ff] bg-clip-text text-transparent">
                  AskEver makes them clear.
                </span>
              </h2>
              <p className="mt-5 max-w-md text-sm leading-7 text-white/70">
                Ask questions naturally and get clear, traceable answers with
                the generated SQL and source data behind them.
              </p>
            </div>
          </div>

          <div className="relative flex flex-col bg-white/[0.94] px-5 py-7 backdrop-blur-xl sm:px-9 sm:py-9 lg:bg-[#fcfcfd] lg:px-12 lg:py-11 lg:backdrop-blur-none xl:px-14 xl:py-12">
            <p className="text-[13px] font-bold uppercase tracking-[0.28em] text-[#343948]">
              Everlign
            </p>

            <div className="my-9 w-full sm:my-11 lg:my-auto">
              <h1 className="text-[29px] font-semibold tracking-[-0.04em] text-[#242735] sm:text-[34px]">
                Welcome to AskEver
              </h1>
              <p className="mt-3 text-sm leading-6 text-[#666c7b]">
                Tell us what to call you to personalize your workspace.
              </p>

              <form
                onSubmit={handleSubmit}
                className="mt-8"
                aria-label="Enter your name to get started"
              >
                <label
                  htmlFor="display-name"
                  className="text-[13px] font-medium text-[#454b5a]"
                >
                  Your name
                </label>
                <div className="mt-2.5">
                  <input
                    id="display-name"
                    type="text"
                    placeholder="Enter your name"
                    value={name}
                    onChange={(event) => {
                      setName(event.target.value);
                      setError("");
                    }}
                    autoComplete="name"
                    autoFocus
                    aria-describedby={error ? "display-name-error" : undefined}
                    aria-invalid={Boolean(error)}
                    className={`h-[54px] w-full rounded-2xl border bg-[#f8f8fb] px-4 text-[15px] text-[#252936] shadow-[inset_0_1px_0_rgba(255,255,255,0.8)] placeholder:text-[#9298a7] transition-all focus:outline-none focus:ring-4 focus:ring-[#7772df]/10 ${
                      error
                        ? "border-[#df7890] focus:border-[#df7890]"
                        : "border-[#dfe1e9] hover:border-[#cdd0dc] focus:border-[#7772df]"
                    }`}
                  />
                  {error && (
                    <p
                      id="display-name-error"
                      role="alert"
                      className="mt-2 text-xs font-medium text-[#b83b57]"
                    >
                      {error}
                    </p>
                  )}
                </div>

                <button
                  type="submit"
                  className="group mt-4 inline-flex h-[52px] w-full items-center justify-center gap-2 rounded-2xl bg-[#242837] px-5 text-sm font-semibold text-white shadow-[0_14px_34px_rgba(43,45,62,0.22)] transition-all hover:-translate-y-0.5 hover:bg-[#171a25] hover:shadow-[0_18px_40px_rgba(43,45,62,0.28)] focus:outline-none focus-visible:ring-2 focus-visible:ring-[#7772df] focus-visible:ring-offset-2 focus-visible:ring-offset-white"
                >
                  Continue
                  <svg
                    className="h-4 w-4 transition-transform group-hover:translate-x-0.5"
                    fill="none"
                    stroke="currentColor"
                    viewBox="0 0 24 24"
                    aria-hidden
                  >
                    <path
                      strokeLinecap="round"
                      strokeLinejoin="round"
                      strokeWidth={2}
                      d="m9 18 6-6-6-6"
                    />
                  </svg>
                </button>
              </form>
            </div>

            <p className="text-center text-[11px] leading-5 text-[#7b8190] lg:text-left">
              No account required. Your name is used only for this session.
            </p>
          </div>
        </section>
      </div>
    </main>
  );
}
