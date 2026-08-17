"use client";

import { useEffect } from "react";
import { useRouter } from "next/navigation";
import { getSessionUser } from "@/lib/session";
import { ChatPage } from "@/components/chat/ChatPage";

export default function ChatRoute() {
  const router = useRouter();

  useEffect(() => {
    const user = getSessionUser();
    if (!user?.name) {
      router.replace("/");
      return;
    }
  }, [router]);

  return <ChatPage />;
}
