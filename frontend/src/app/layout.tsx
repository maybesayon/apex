import type { Metadata, Viewport } from "next";
import { SessionProvider, ThemeProvider } from "@/components/providers";
import "./globals.css";

export const metadata: Metadata = {
  title: "APEX",
  description:
    "Technical analysis, strategy backtesting and honestly-validated price forecasting.",
};

export const viewport: Viewport = {
  themeColor: [
    { media: "(prefers-color-scheme: light)", color: "#f5f5f7" },
    { media: "(prefers-color-scheme: dark)", color: "#0c0d11" },
  ],
};

/**
 * Applies the stored theme before first paint.
 *
 * Without this the page renders light, then React swaps to dark a frame
 * later — a visible flash. It has to be inline and blocking; there is no
 * other way to beat the first paint.
 */
const NO_FLASH = `
(function(){try{
  var t = localStorage.getItem('apex-theme');
  if(!t) t = matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light';
  document.documentElement.setAttribute('data-theme', t);
  document.documentElement.style.colorScheme = t;
}catch(e){}})();
`;

export default function RootLayout({
  children,
}: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en" suppressHydrationWarning>
      <head>
        <script dangerouslySetInnerHTML={{ __html: NO_FLASH }} />
      </head>
      <body>
        <ThemeProvider>
          <SessionProvider>{children}</SessionProvider>
        </ThemeProvider>
      </body>
    </html>
  );
}
