"use client";

import { useEffect, useState } from "react";

const FORM_REVEAL_DELAY_MS = 3500;

export interface WelcomeLoaderProps {
  onReveal: () => void;
  isOverlayVisible: boolean;
}

export function WelcomeLoader({
  onReveal,
  isOverlayVisible,
}: WelcomeLoaderProps) {
  const [isIntroVisible, setIsIntroVisible] = useState(false);

  useEffect(() => {
    if (isOverlayVisible) return;

    const prefersReducedMotion = window.matchMedia(
      "(prefers-reduced-motion: reduce)",
    ).matches;
    const entranceTimer = setTimeout(
      () => setIsIntroVisible(true),
      prefersReducedMotion ? 0 : 50,
    );
    const revealTimer = setTimeout(
      onReveal,
      prefersReducedMotion ? 400 : FORM_REVEAL_DELAY_MS,
    );

    return () => {
      clearTimeout(entranceTimer);
      clearTimeout(revealTimer);
    };
  }, [isOverlayVisible, onReveal]);

  return (
    <div
      className="fixed inset-0 z-0 overflow-hidden bg-[#070a16]"
      aria-hidden={isOverlayVisible}
    >
      {!isOverlayVisible && (
        <p className="sr-only" role="status">
          Opening Sequel AI by Everlign
        </p>
      )}

      <div className="pointer-events-none absolute inset-0" aria-hidden>
        <div className="absolute inset-0 bg-[radial-gradient(circle_at_50%_42%,rgba(93,102,232,0.2),transparent_34%),radial-gradient(circle_at_18%_22%,rgba(41,243,253,0.1),transparent_30%),radial-gradient(circle_at_84%_78%,rgba(125,80,254,0.12),transparent_34%)]" />
        <div className="absolute left-1/2 top-1/2 h-[min(72vw,760px)] w-[min(72vw,760px)] -translate-x-1/2 -translate-y-1/2 rounded-full border border-white/[0.04] shadow-[0_0_120px_rgba(105,108,240,0.08)]" />
        <div className="absolute left-1/2 top-1/2 h-[min(48vw,510px)] w-[min(48vw,510px)] -translate-x-1/2 -translate-y-1/2 rounded-full border border-white/[0.05]" />
      </div>

      <div
        className={`pointer-events-none absolute inset-0 z-[2] flex items-center justify-center px-5 transition-all duration-500 ease-out sm:px-10 ${
          isIntroVisible && !isOverlayVisible
            ? "translate-y-0 scale-100 opacity-100"
            : "translate-y-3 scale-[0.985] opacity-0"
        }`}
      >
        <div className="relative flex w-full max-w-[1120px] flex-col items-center justify-center py-12 sm:py-16">
          <div
            className="absolute inset-x-[3%] inset-y-0 rounded-[44px] bg-[radial-gradient(ellipse_at_center,rgba(11,17,36,0.74)_0%,rgba(11,17,36,0.42)_45%,rgba(11,17,36,0)_74%)] blur-sm"
            aria-hidden
          />

          <div className="relative z-10 text-center text-[clamp(4rem,11vw,10.5rem)] font-black leading-[0.86] tracking-[-0.075em] text-[#f7f8fc] drop-shadow-[0_18px_50px_rgba(0,0,0,0.34)]">
            <span>Sequel</span>
            <span className="bg-gradient-to-br from-[#26dbe8] via-[#8290ff] to-[#a47bff] bg-clip-text text-transparent">
              AI
            </span>
          </div>

          <p className="relative z-10 mt-7 text-xs font-semibold uppercase tracking-[0.28em] text-white/45 sm:text-sm">
            Intelligent answers from your data
          </p>
        </div>
      </div>

      <div
        className={`pointer-events-none absolute inset-0 bg-[#071019]/[0.12] transition-opacity duration-700 ${
          isOverlayVisible ? "opacity-100" : "opacity-0"
        }`}
        aria-hidden
      />
    </div>
  );
}
