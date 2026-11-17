import type { Metadata } from "next";
import { Hanken_Grotesk } from "next/font/google";
import type { ReactNode } from "react";
import { Shell } from "@/lib/session";
import "./globals.css";

const font = Hanken_Grotesk({ subsets: ["latin"], weight: ["400", "500", "700", "800"] });

export const metadata: Metadata = {
  title: "Splitkit",
  description: "Split shared expenses exactly and settle up in as few payments as possible.",
};

export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    <html lang="en">
      <body className={font.className}>
        <Shell>{children}</Shell>
      </body>
    </html>
  );
}
