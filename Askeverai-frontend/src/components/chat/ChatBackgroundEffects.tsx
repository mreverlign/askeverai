export function ChatBackgroundEffects() {
  return (
    <div className="pointer-events-none absolute inset-0 z-0 overflow-hidden" aria-hidden>
      <div className="absolute inset-0 bg-[linear-gradient(180deg,rgba(255,255,255,0.88)_0%,rgba(250,251,255,0.72)_48%,rgba(248,249,253,0.92)_100%)]" />
      <div className="absolute -bottom-40 left-[8%] h-[420px] w-[420px] rounded-full bg-[#7376f2]/[0.075] blur-[100px]" />
      <div className="absolute -bottom-44 right-[2%] h-[440px] w-[440px] rounded-full bg-[#7fe0e6]/[0.08] blur-[110px]" />
      <div className="absolute bottom-[-18%] left-[38%] h-[360px] w-[360px] rounded-full bg-[#f3df9f]/[0.07] blur-[100px]" />
      <div className="absolute left-1/2 top-[18%] h-56 w-56 -translate-x-1/2 rounded-full bg-[#8d8ff8]/[0.035] blur-[80px]" />
    </div>
  );
}
