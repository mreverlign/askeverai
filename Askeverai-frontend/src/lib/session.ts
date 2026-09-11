"use client";

import type { SessionUser } from "./types";
import { SESSION_COOKIE_NAME } from "./authConstants";

const SESSION_STORAGE_KEY = "askever_session_user";
export { SESSION_COOKIE_NAME };

function writeCookie(token: string, expiresAt: number): void {
  const secure = window.location.protocol === "https:" ? "; Secure" : "";
  const expires = new Date(expiresAt * 1000).toUTCString();
  document.cookie = `${SESSION_COOKIE_NAME}=${encodeURIComponent(
    token,
  )}; Path=/; Expires=${expires}; SameSite=Lax${secure}`;
}

function deleteCookie(): void {
  const secure = window.location.protocol === "https:" ? "; Secure" : "";
  document.cookie = `${SESSION_COOKIE_NAME}=; Path=/; Max-Age=0; SameSite=Lax${secure}`;
}

export function getSessionUser(): SessionUser | null {
  if (typeof window === "undefined") return null;
  try {
    const raw = sessionStorage.getItem(SESSION_STORAGE_KEY);
    if (!raw) return null;
    const user = JSON.parse(raw) as SessionUser;
    if (!user?.username || !user?.token) return null;
    if (user.expiresAt && Date.now() >= user.expiresAt * 1000) {
      clearSessionUser();
      return null;
    }
    return user;
  } catch {
    return null;
  }
}

export function setSessionUser(session: {
  username: string;
  name?: string;
  token: string;
  expiresAt: number;
}): void {
  if (typeof window === "undefined") return;
  const account = session.username.trim();
  const user: SessionUser = {
    name: session.name?.trim() || account,
    username: account,
    token: session.token,
    expiresAt: session.expiresAt,
    createdAt: Date.now(),
  };
  sessionStorage.setItem(SESSION_STORAGE_KEY, JSON.stringify(user));
  writeCookie(session.token, session.expiresAt);
}

export function clearSessionUser(): void {
  if (typeof window === "undefined") return;
  sessionStorage.removeItem(SESSION_STORAGE_KEY);
  deleteCookie();
}

/** Authorization header for a protected API call, or {} when signed out. */
export function authHeaders(): Record<string, string> {
  const token = getSessionUser()?.token;
  return token ? { Authorization: `Bearer ${token}` } : {};
}
