"use client";

import { useEffect, useState } from "react";

export interface LoginCredentials {
  username: string;
  password: string;
}

export interface LoginFormProps {
  onSubmit: (credentials: LoginCredentials) => void;
  /** Message from a rejected sign-in attempt. */
  errorMessage?: string;
  /** Called when the user edits a field, so a stale rejection can be cleared. */
  onDismissError?: () => void;
  isSubmitting?: boolean;
}

const INPUT_BASE =
  "h-[54px] w-full rounded-2xl border bg-[#f8f8fb] px-4 text-[15px] text-[#252936] shadow-[inset_0_1px_0_rgba(255,255,255,0.8)] placeholder:text-[#9298a7] transition-all focus:outline-none focus:ring-4 focus:ring-[#7772df]/10 disabled:opacity-60";

function inputClasses(hasError: boolean, extra = "") {
  const state = hasError
    ? "border-[#df7890] focus:border-[#df7890]"
    : "border-[#dfe1e9] hover:border-[#cdd0dc] focus:border-[#7772df]";
  return `${INPUT_BASE} ${state} ${extra}`;
}

export function LoginForm({
  onSubmit,
  errorMessage,
  onDismissError,
  isSubmitting = false,
}: LoginFormProps) {
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [showPassword, setShowPassword] = useState(false);
  const [fieldError, setFieldError] = useState("");
  const [visible, setVisible] = useState(false);

  useEffect(() => {
    const timer = setTimeout(() => setVisible(true), 50);
    return () => clearTimeout(timer);
  }, []);

  const error = fieldError || errorMessage || "";

  function handleFieldChange(setValue: (value: string) => void) {
    return (event: React.ChangeEvent<HTMLInputElement>) => {
      setValue(event.target.value);
      setFieldError("");
      onDismissError?.();
    };
  }

  function handleSubmit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (isSubmitting) return;

    const trimmedUsername = username.trim();

    if (!trimmedUsername) {
      setFieldError("Please enter your username");
      return;
    }
    if (!password) {
      setFieldError("Please enter your password");
      return;
    }

    setFieldError("");
    onSubmit({ username: trimmedUsername, password });
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
              Sequel AI
            </p>

            <div className="relative mt-auto max-w-[530px] p-10 pt-24 xl:p-14 xl:pt-28">
              <h2 className="text-[44px] font-semibold leading-[1.06] tracking-[-0.05em] text-white drop-shadow-[0_3px_20px_rgba(0,0,0,0.3)] xl:text-[51px]">
                Your data has answers.
                <span className="mt-1 block bg-gradient-to-r from-[#9cf5f7] via-[#9ca9ff] to-[#b795ff] bg-clip-text text-transparent">
                  Sequel AI makes them clear.
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
                Sign in to Sequel AI
              </h1>
              <p className="mt-3 text-sm leading-6 text-[#666c7b]">
                Enter the credentials issued to you to open your workspace.
              </p>

              <form
                onSubmit={handleSubmit}
                className="mt-8"
                aria-label="Sign in to Sequel AI"
              >
                <label
                  htmlFor="username"
                  className="text-[13px] font-medium text-[#454b5a]"
                >
                  Username
                </label>
                <div className="mt-2.5">
                  <input
                    id="username"
                    name="username"
                    type="text"
                    placeholder="Enter your username"
                    value={username}
                    onChange={handleFieldChange(setUsername)}
                    autoComplete="username"
                    autoFocus
                    disabled={isSubmitting}
                    aria-invalid={Boolean(error)}
                    aria-describedby={error ? "login-error" : undefined}
                    className={inputClasses(Boolean(error))}
                  />
                </div>

                <label
                  htmlFor="password"
                  className="mt-5 block text-[13px] font-medium text-[#454b5a]"
                >
                  Password
                </label>
                <div className="relative mt-2.5">
                  <input
                    id="password"
                    name="password"
                    type={showPassword ? "text" : "password"}
                    placeholder="Enter your password"
                    value={password}
                    onChange={handleFieldChange(setPassword)}
                    autoComplete="current-password"
                    disabled={isSubmitting}
                    aria-invalid={Boolean(error)}
                    aria-describedby={error ? "login-error" : undefined}
                    className={inputClasses(Boolean(error), "pr-16")}
                  />
                  <button
                    type="button"
                    onClick={() => setShowPassword((shown) => !shown)}
                    className="absolute inset-y-0 right-0 flex items-center rounded-r-2xl px-4 text-[12px] font-semibold text-[#7b8190] transition-colors hover:text-[#454b5a] focus:outline-none focus-visible:ring-2 focus-visible:ring-[#7772df]"
                  >
                    {showPassword ? "Hide" : "Show"}
                  </button>
                </div>

                {error && (
                  <p
                    id="login-error"
                    role="alert"
                    className="mt-3 text-xs font-medium text-[#b83b57]"
                  >
                    {error}
                  </p>
                )}

                <button
                  type="submit"
                  disabled={isSubmitting}
                  className="group mt-6 inline-flex h-[52px] w-full items-center justify-center gap-2 rounded-2xl bg-[#242837] px-5 text-sm font-semibold text-white shadow-[0_14px_34px_rgba(43,45,62,0.22)] transition-all hover:-translate-y-0.5 hover:bg-[#171a25] hover:shadow-[0_18px_40px_rgba(43,45,62,0.28)] focus:outline-none focus-visible:ring-2 focus-visible:ring-[#7772df] focus-visible:ring-offset-2 focus-visible:ring-offset-white disabled:pointer-events-none disabled:opacity-70"
                >
                  {isSubmitting ? "Signing in..." : "Sign in"}
                  {!isSubmitting && (
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
                  )}
                </button>
              </form>
            </div>

            <p className="text-center text-[11px] leading-5 text-[#7b8190] lg:text-left">
              Access is limited to approved accounts. Contact your administrator
              if you need credentials.
            </p>
          </div>
        </section>
      </div>
    </main>
  );
}
