import type { Metadata, Viewport } from "next";
import { Geist, Geist_Mono } from "next/font/google";
import "./globals.css";

const geistSans = Geist({
  variable: "--font-geist-sans",
  subsets: ["latin"],
});

const geistMono = Geist_Mono({
  variable: "--font-geist-mono",
  subsets: ["latin"],
});

export const metadata: Metadata = {
  title: "Sequel AI by Everlign — Intelligent data assistant",
  description:
    "Ask questions about your data in natural language and get clear, traceable answers.",
  applicationName: "Sequel AI by Everlign",
  icons: {
    icon: [
      {
        url: "/brand/everlign-mark.svg",
        type: "image/svg+xml",
      },
    ],
    shortcut: "/brand/everlign-mark.svg",
  },
};

export const viewport: Viewport = {
  colorScheme: "light",
  themeColor: "#7D50FE",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en" className={`${geistSans.variable} ${geistMono.variable}`}>
      <body className="min-h-screen font-sans">{children}</body>
    </html>
  );
}
