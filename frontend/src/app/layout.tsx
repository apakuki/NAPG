import type { Metadata, Viewport } from "next";
import { Geist, Geist_Mono } from "next/font/google";
import { Nav } from "./_components/nav";
import { Providers } from "./_components/providers";
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
  title: "NAPG — Service Assurance Dashboard",
  description:
    "NOC-level Protocol Service Assurance for the Coinbase Base ecosystem.",
};

/**
 * Viewport tuned for the Base App in-app browser:
 *  - `viewportFit: "cover"` lets the page render edge-to-edge so the bottom
 *    nav and any safe-area-inset padding behave correctly under the iOS
 *    home indicator.
 *  - `themeColor` matches the in-app browser chrome to our background per
 *    color scheme; the Farcaster client uses this to colour its status bar.
 */
export const viewport: Viewport = {
  width: "device-width",
  initialScale: 1,
  viewportFit: "cover",
  themeColor: [
    { media: "(prefers-color-scheme: light)", color: "#fafafa" },
    { media: "(prefers-color-scheme: dark)", color: "#0a0a0a" },
  ],
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html
      lang="en"
      className={`${geistSans.variable} ${geistMono.variable} h-full antialiased`}
    >
      <body className="min-h-full flex flex-col">
        <Providers>
          <div className="flex-1">{children}</div>
          <Nav />
        </Providers>
      </body>
    </html>
  );
}
