import { NextResponse, type NextRequest } from "next/server";
import { SESSION_COOKIE_NAME } from "@/lib/authConstants";

function base64UrlToBytes(value: string) {
  const padded = value.replace(/-/g, "+").replace(/_/g, "/");
  const binary = atob(padded + "=".repeat((4 - (padded.length % 4)) % 4));
  const bytes = new Uint8Array(new ArrayBuffer(binary.length));
  for (let index = 0; index < binary.length; index += 1) {
    bytes[index] = binary.charCodeAt(index);
  }
  return bytes;
}

function isUnexpired(body: string): boolean {
  try {
    const payload = JSON.parse(new TextDecoder().decode(base64UrlToBytes(body)));
    return (
      typeof payload?.exp === "number" &&
      typeof payload?.sub === "string" &&
      Boolean(payload.sub) &&
      Date.now() / 1000 < payload.exp
    );
  } catch {
    return false;
  }
}

async function isValidSession(token: string | undefined): Promise<boolean> {
  if (!token) return false;

  const [body, signature, ...rest] = token.split(".");
  if (!body || !signature || rest.length) return false;
  const secret = process.env.SESSION_SECRET;

  if (!secret) {
    console.warn(
      "SESSION_SECRET is not set — /chat is gated on token shape only.",
    );
    return isUnexpired(body);
  }

  try {
    const key = await crypto.subtle.importKey(
      "raw",
      new TextEncoder().encode(secret),
      { name: "HMAC", hash: "SHA-256" },
      false,
      ["verify"],
    );
    const signed = await crypto.subtle.verify(
      "HMAC",
      key,
      base64UrlToBytes(signature),
      new TextEncoder().encode(body),
    );
    return signed && isUnexpired(body);
  } catch {
    return false;
  }
}

export async function middleware(request: NextRequest) {
  const token = request.cookies.get(SESSION_COOKIE_NAME)?.value;

  if (await isValidSession(token)) {
    return NextResponse.next();
  }

  const loginUrl = new URL("/", request.url);
  const response = NextResponse.redirect(loginUrl);
  response.cookies.delete(SESSION_COOKIE_NAME);
  return response;
}

export const config = {
  matcher: ["/chat/:path*"],
};
