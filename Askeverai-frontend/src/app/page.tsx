"use client";

import { useState, useCallback } from "react";
import { useRouter } from "next/navigation";
import { WelcomeLoader } from "@/components/loader/WelcomeLoader";
import { LoginForm, type LoginCredentials } from "@/components/auth/LoginForm";
import { setSessionUser } from "@/lib/session";

type FlowStep = "intro" | "login" | "chat";

const API_BASE_URL =
  process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

export default function HomePage() {
  const router = useRouter();
  const [step, setStep] = useState<FlowStep>("intro");
  const [loginError, setLoginError] = useState("");
  const [isSubmitting, setIsSubmitting] = useState(false);

  const handleIntroReveal = useCallback(() => {
    setStep("login");
  }, []);

  const handleLogin = useCallback(
    async ({ username, password }: LoginCredentials) => {
      setIsSubmitting(true);
      setLoginError("");

      try {
        const response = await fetch(`${API_BASE_URL}/login`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ username, password }),
        });

        if (!response.ok) {
          const detail = await response
            .json()
            .then((body) => body?.detail)
            .catch(() => null);
          setLoginError(
            typeof detail === "string" && detail
              ? detail
              : "Invalid username or password",
          );
          return;
        }

        const account = await response.json();
        if (!account?.token) {
          setLoginError("Sign-in failed. Please try again.");
          return;
        }

        setSessionUser({
          username: account.username ?? username,
          name: account.name,
          token: account.token,
          expiresAt: account.expires_at,
        });
        setStep("chat");
        router.replace("/chat");
      } catch {
        setLoginError(
          "Could not reach the server. Check your connection and try again.",
        );
      } finally {
        setIsSubmitting(false);
      }
    },
    [router],
  );

  return (
    <>
      {step !== "chat" && (
        <WelcomeLoader
          onReveal={handleIntroReveal}
          isOverlayVisible={step === "login"}
        />
      )}
      {step === "login" && (
        <LoginForm
          onSubmit={handleLogin}
          errorMessage={loginError}
          onDismissError={() => setLoginError("")}
          isSubmitting={isSubmitting}
        />
      )}
    </>
  );
}
