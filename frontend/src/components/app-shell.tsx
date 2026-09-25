"use client";

/**
 * Application chrome.
 *
 * Desktop gets a persistent left sidebar; mobile gets a bottom tab bar,
 * which is what a native financial app does — not a shrunken sidebar.
 * Both render the same route list from one definition.
 */

import { AnimatePresence, motion } from "motion/react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import {
  BriefcaseBusiness,
  Compass,
  FlaskConical,
  LineChart,
  LogOut,
  MessageSquare,
  Moon,
  NotebookPen,
  Star,
  Sun,
} from "lucide-react";
import { useEffect, useState } from "react";
import { useSession, useTheme } from "@/components/providers";
import { StockSearch } from "@/components/stock-search";
import { TickerTape } from "@/components/tradingview";
import { Button } from "@/components/ui";
import { api } from "@/lib/api";
import { cn } from "@/lib/utils";

/**
 * Primary destinations appear in both the sidebar and the mobile tab bar.
 * Five is the practical ceiling for a bottom bar before the labels stop
 * being readable, so the two tools live in the sidebar and are reachable
 * from cards on the Overview.
 */
export const NAV = [
  { href: "/", label: "Overview", icon: LineChart },
  { href: "/markets", label: "Markets", icon: Compass },
  { href: "/portfolio", label: "Portfolio", icon: BriefcaseBusiness },
  { href: "/watchlist", label: "Watchlist", icon: Star },
  { href: "/journal", label: "Journal", icon: NotebookPen },
] as const;

export const NAV_TOOLS = [
  { href: "/backtest", label: "Backtest", icon: FlaskConical },
  { href: "/assistant", label: "Assistant", icon: MessageSquare },
] as const;

function isActive(pathname: string, href: string) {
  return href === "/" ? pathname === "/" : pathname.startsWith(href);
}

export function ThemeToggle({ compact = false }: { compact?: boolean }) {
  const { theme, toggle } = useTheme();
  const dark = theme === "dark";
  return (
    <button
      onClick={toggle}
      aria-label={`Switch to ${dark ? "light" : "dark"} mode`}
      className={cn(
        "flex items-center gap-2 rounded-full text-muted transition-colors hover:bg-surface-2 hover:text-ink",
        compact ? "size-9 justify-center" : "px-3 py-2",
      )}
    >
      <AnimatePresence mode="wait" initial={false}>
        <motion.span
          key={theme}
          initial={{ rotate: -90, opacity: 0, scale: 0.7 }}
          animate={{ rotate: 0, opacity: 1, scale: 1 }}
          exit={{ rotate: 90, opacity: 0, scale: 0.7 }}
          transition={{ duration: 0.22, ease: [0.32, 0.72, 0, 1] }}
          className="flex"
        >
          {dark ? <Sun className="size-[18px]" /> : <Moon className="size-[18px]" />}
        </motion.span>
      </AnimatePresence>
      {!compact && <span className="text-[14px]">{dark ? "Light" : "Dark"}</span>}
    </button>
  );
}

function Sidebar() {
  const pathname = usePathname();
  const { user, signOut } = useSession();

  return (
    <aside className="fixed inset-y-0 left-0 hidden w-[248px] flex-col border-r border-line bg-surface px-4 py-6 md:flex">
      <div className="px-2 pb-6">
        <div className="text-[22px] font-bold tracking-[-0.035em] text-ink">
          APEX
        </div>
        {user && (
          <div className="mt-0.5 text-[12.5px] text-muted">
            Signed in as{" "}
            <span className="font-medium text-ink">{user.username}</span>
          </div>
        )}
      </div>

      <nav className="flex flex-1 flex-col gap-0.5">
        {NAV.map(({ href, label, icon: Icon }) => {
          const active = isActive(pathname, href);
          return (
            <Link
              key={href}
              href={href}
              className={cn(
                "relative flex items-center gap-3 rounded-xl px-3 py-2.5 text-[14.5px] transition-colors",
                active
                  ? "font-medium text-ink"
                  : "text-muted hover:bg-surface-2 hover:text-ink",
              )}
            >
              {active && (
                <motion.span
                  layoutId="nav-active"
                  className="absolute inset-0 -z-10 rounded-xl bg-surface-2"
                  transition={{ duration: 0.28, ease: [0.32, 0.72, 0, 1] }}
                />
              )}
              <Icon className="size-[18px]" />
              {label}
            </Link>
          );
        })}
        <div className="my-3 h-px bg-line" />
        {NAV_TOOLS.map(({ href, label, icon: Icon }) => {
          const active = isActive(pathname, href);
          return (
            <Link
              key={href}
              href={href}
              className={cn(
                "relative flex items-center gap-3 rounded-xl px-3 py-2.5 text-[14.5px] transition-colors",
                active
                  ? "font-medium text-ink"
                  : "text-muted hover:bg-surface-2 hover:text-ink",
              )}
            >
              {active && (
                <motion.span
                  layoutId="nav-active"
                  className="absolute inset-0 -z-10 rounded-xl bg-surface-2"
                  transition={{ duration: 0.28, ease: [0.32, 0.72, 0, 1] }}
                />
              )}
              <Icon className="size-[18px]" />
              {label}
            </Link>
          );
        })}
      </nav>

      <div className="flex items-center justify-between border-t border-line pt-3">
        <ThemeToggle />
        <button
          onClick={() => void signOut()}
          aria-label="Sign out"
          className="flex size-9 items-center justify-center rounded-full text-muted transition-colors hover:bg-surface-2 hover:text-ink"
        >
          <LogOut className="size-[17px]" />
        </button>
      </div>
    </aside>
  );
}

function MobileNav() {
  const pathname = usePathname();
  return (
    <nav
      className="fixed inset-x-0 bottom-0 z-40 border-t border-line bg-surface/85 backdrop-blur-xl md:hidden"
      style={{ paddingBottom: "env(safe-area-inset-bottom)" }}
    >
      <div className="flex">
        {NAV.map(({ href, label, icon: Icon }) => {
          const active = isActive(pathname, href);
          return (
            <Link
              key={href}
              href={href}
              className={cn(
                "flex flex-1 flex-col items-center gap-1 py-2.5 text-[10.5px] transition-colors",
                active ? "text-accent" : "text-faint",
              )}
            >
              <Icon className="size-[21px]" />
              {label}
            </Link>
          );
        })}
      </div>
    </nav>
  );
}

function MobileHeader() {
  return (
    <header className="sticky top-0 z-30 flex items-center justify-between border-b border-line bg-bg/80 px-4 py-3 backdrop-blur-xl md:hidden">
      <span className="text-[19px] font-bold tracking-[-0.03em] text-ink">
        APEX
      </span>
      <ThemeToggle compact />
    </header>
  );
}

/**
 * The scrolling price strip, fed by the user's own watchlist so it shows
 * what they actually follow rather than a fixed list.
 */
function Tape() {
  const [symbols, setSymbols] = useState<string[] | null>(null);

  useEffect(() => {
    api
      .watchlist()
      .then((items) => setSymbols(items.map((i) => i.symbol)))
      .catch(() => setSymbols([]));
  }, []);

  if (symbols === null) return <div className="h-[50px]" />;
  const list = Array.from(new Set(["SPY", "QQQ", ...symbols])).slice(0, 12);
  return <TickerTape symbols={list} />;
}

export function AppShell({ children }: { children: React.ReactNode }) {
  return (
    <div className="min-h-dvh bg-bg">
      <Sidebar />
      <MobileHeader />
      <main className="md:pl-[248px]">
        {/* Bottom padding clears the mobile tab bar. */}
        <div className="mx-auto w-full max-w-[1180px] px-4 pb-28 pt-4 md:px-8 md:pb-14 md:pt-6">
          <Tape />
          <div className="mb-6 max-w-[520px]">
            <StockSearch />
          </div>
          {children}
        </div>
      </main>
      <MobileNav />
    </div>
  );
}

export { Button };
