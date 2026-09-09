import type { Metadata } from "next";
import localFont from "next/font/local";
import Link from "next/link";
import "./globals.css";

const geistSans = localFont({
  src: "./fonts/GeistVF.woff",
  variable: "--font-geist-sans",
  weight: "100 900",
});
const geistMono = localFont({
  src: "./fonts/GeistMonoVF.woff",
  variable: "--font-geist-mono",
  weight: "100 900",
});

export const metadata: Metadata = {
  title: "Coverage Amplifier — AI Coverage Activation",
  description:
    "Turn media coverage into verified, client-ready marketing assets. Grounded in source quotes.",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en">
      <body
        className={`${geistSans.variable} ${geistMono.variable} antialiased bg-gray-50 text-gray-900 min-h-screen flex flex-col font-sans`}
      >
        {/* Navigation Bar */}
        <header className="bg-white border-b border-gray-200 sticky top-0 z-50">
          <div className="max-w-5xl mx-auto px-4 h-16 flex items-center justify-between">
            <Link href="/" className="flex items-center gap-2 group">
              <span className="w-8 h-8 rounded-lg bg-blue-600 text-white font-black text-base flex items-center justify-center shadow-sm">
                CA
              </span>
              <div>
                <span className="text-base font-bold text-gray-900 group-hover:text-blue-600 transition tracking-tight">
                  Coverage Amplifier
                </span>
                <span className="hidden sm:inline-block ml-2 text-[10px] font-semibold uppercase tracking-wider text-blue-700 bg-blue-50 px-1.5 py-0.5 rounded border border-blue-200">
                  v1.0
                </span>
              </div>
            </Link>

            <nav className="flex items-center gap-4 text-sm font-medium">
              <Link
                href="/"
                className="text-gray-600 hover:text-gray-900 transition-colors px-2 py-1 rounded"
              >
                Intake
              </Link>
              <Link
                href="/library"
                className="text-gray-600 hover:text-gray-900 transition-colors px-2 py-1 rounded"
              >
                Library
              </Link>
            </nav>
          </div>
        </header>

        {/* Main Content */}
        <main className="flex-1">{children}</main>

        {/* Footer */}
        <footer className="border-t border-gray-200 bg-white py-6 text-center text-xs text-gray-500">
          <div className="max-w-5xl mx-auto px-4 flex flex-col sm:flex-row items-center justify-between gap-2">
            <p>
              Coverage Amplifier &copy; 2026. Coverage activation, not reporting.
            </p>
            <p className="text-[11px] text-gray-400">
              Grounded AI copy with per-claim source citations.
            </p>
          </div>
        </footer>
      </body>
    </html>
  );
}
