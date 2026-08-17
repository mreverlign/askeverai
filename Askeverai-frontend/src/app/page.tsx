"use client";

import { useState, useCallback } from "react";
import { useRouter } from "next/navigation";
import { WelcomeLoader } from "@/components/loader/WelcomeLoader";
import { NameEntryForm } from "@/components/name-entry/NameEntryForm";
import { setSessionUser } from "@/lib/session";

type FlowStep = "intro" | "name-entry" | "chat";

export default function HomePage() {
  const router = useRouter();
  const [step, setStep] = useState<FlowStep>("intro");

  const handleIntroReveal = useCallback(() => {
    setStep("name-entry");
  }, []);

  const handleNameSubmit = useCallback(
    async (name: string) => {
      setSessionUser(name);
      try {
        const apiUrl =
          process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";
        await fetch(`${apiUrl}/login`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ username: name }),
        });
      } catch {
        // proceed even if backend is unreachable
      }
      setStep("chat");
      router.replace("/chat");
    },
    [router],
  );

  return (
    <>
      {step !== "chat" && (
        <WelcomeLoader
          onReveal={handleIntroReveal}
          isOverlayVisible={step === "name-entry"}
        />
      )}
      {step === "name-entry" && <NameEntryForm onSubmit={handleNameSubmit} />}
    </>
  );
}
