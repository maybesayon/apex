"use client";

/**
 * Design-system primitives.
 *
 * Small, composable, and theme-agnostic: every colour is a token, so the
 * same component renders correctly in light and dark without branching.
 */

import { motion } from "motion/react";
import * as React from "react";
import { cn, percent, toneClass } from "@/lib/utils";

// ── Card ──────────────────────────────────────────────────────────────────────

export function Card({
  className,
  interactive = false,
  ...props
}: React.HTMLAttributes<HTMLDivElement> & { interactive?: boolean }) {
  return (
    <div
      className={cn(
        "rounded-[var(--radius-card)] border border-line bg-surface shadow-card",
        interactive &&
          "transition-[transform,box-shadow] duration-300 ease-[var(--ease-out-apple)] hover:-translate-y-0.5 hover:shadow-card-lg",
        className,
      )}
      {...props}
    />
  );
}

/**
 * `level` sets the heading rank. Every page needs exactly one h1 or screen
 * readers see a document that starts at h2, so the first heading on a page
 * passes level={1}. The visual size is identical either way.
 */
export function SectionHeading({
  title,
  action,
  level = 2,
}: {
  title: string;
  action?: React.ReactNode;
  level?: 1 | 2;
}) {
  const Tag = level === 1 ? "h1" : "h2";
  return (
    <div className="mb-3 flex items-baseline justify-between gap-4">
      <Tag className="text-[17px] font-semibold tracking-[-0.02em] text-ink">
        {title}
      </Tag>
      {action}
    </div>
  );
}

// ── Button ────────────────────────────────────────────────────────────────────

type ButtonProps = React.ButtonHTMLAttributes<HTMLButtonElement> & {
  variant?: "primary" | "secondary" | "ghost";
  loading?: boolean;
};

export function Button({
  className,
  variant = "secondary",
  loading = false,
  disabled,
  children,
  ...props
}: ButtonProps) {
  return (
    <button
      disabled={disabled || loading}
      className={cn(
        "inline-flex items-center justify-center gap-2 rounded-full px-5 py-2.5",
        "text-[14.5px] font-medium tracking-[-0.01em]",
        "transition-[transform,box-shadow,background-color,opacity] duration-200 ease-[var(--ease-out-apple)]",
        "active:scale-[0.97] disabled:pointer-events-none disabled:opacity-50",
        "focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent",
        variant === "primary" &&
          "bg-up text-[var(--color-on-up)] hover:brightness-105",
        variant === "secondary" &&
          "border border-line-strong bg-surface text-ink shadow-card hover:-translate-y-px hover:shadow-card-lg",
        variant === "ghost" && "text-muted hover:bg-surface-2 hover:text-ink",
        className,
      )}
      {...props}
    >
      {loading && <Spinner className="size-4" />}
      {children}
    </button>
  );
}

export function Spinner({ className }: { className?: string }) {
  return (
    <svg
      className={cn("animate-spin", className)}
      viewBox="0 0 24 24"
      fill="none"
      aria-hidden
    >
      <circle
        cx="12"
        cy="12"
        r="9"
        stroke="currentColor"
        strokeWidth="2.5"
        opacity="0.2"
      />
      <path
        d="M21 12a9 9 0 0 0-9-9"
        stroke="currentColor"
        strokeWidth="2.5"
        strokeLinecap="round"
      />
    </svg>
  );
}

// ── Input ─────────────────────────────────────────────────────────────────────

export const Input = React.forwardRef<
  HTMLInputElement,
  React.InputHTMLAttributes<HTMLInputElement> & { label?: string }
>(function Input({ className, label, id, ...props }, ref) {
  const inputId = id ?? props.name;
  return (
    <div className="w-full">
      {label && (
        <label
          htmlFor={inputId}
          className="mb-1.5 block text-[13px] font-medium text-muted"
        >
          {label}
        </label>
      )}
      <input
        ref={ref}
        id={inputId}
        className={cn(
          "w-full rounded-xl border border-line-strong bg-surface px-3.5 py-2.5",
          "text-[15px] text-ink placeholder:text-faint",
          "transition-[border-color,box-shadow] duration-200",
          "focus:border-accent focus:outline-none focus:ring-[3.5px] focus:ring-accent-soft",
          className,
        )}
        {...props}
      />
    </div>
  );
});

// ── Feedback ──────────────────────────────────────────────────────────────────

export function Delta({
  value,
  className,
  showBackground = false,
}: {
  value: number | null | undefined;
  className?: string;
  showBackground?: boolean;
}) {
  const up = (value ?? 0) >= 0;
  return (
    <span
      className={cn(
        "tnum inline-flex items-center gap-1 text-[13px] font-medium",
        toneClass(value),
        showBackground &&
          cn(
            "rounded-full px-2.5 py-1",
            up ? "bg-up-soft" : "bg-down-soft",
          ),
        className,
      )}
    >
      {value !== null && value !== undefined && (
        <span aria-hidden>{up ? "▲" : "▼"}</span>
      )}
      {percent(value)}
    </span>
  );
}

export function Pill({
  children,
  tone = "neutral",
}: {
  children: React.ReactNode;
  tone?: "neutral" | "up" | "down" | "accent";
}) {
  return (
    <span
      className={cn(
        "inline-flex items-center rounded-full px-2.5 py-1 text-[11.5px] font-medium",
        tone === "neutral" && "border border-line bg-surface-2 text-muted",
        tone === "up" && "bg-up-soft text-up",
        tone === "down" && "bg-down-soft text-down",
        tone === "accent" && "bg-accent-soft text-accent",
      )}
    >
      {children}
    </span>
  );
}

/** Monogram avatar — a logo stand-in that needs no image hosting. */
export function SymbolMark({
  symbol,
  size = 38,
}: {
  symbol: string;
  size?: number;
}) {
  return (
    <div
      className="flex shrink-0 items-center justify-center rounded-full bg-accent-soft font-semibold tracking-[-0.02em] text-accent"
      style={{ width: size, height: size, fontSize: size * 0.34 }}
      aria-hidden
    >
      {symbol.slice(0, 2).toUpperCase()}
    </div>
  );
}

export function Skeleton({ className }: { className?: string }) {
  return (
    <div
      className={cn("animate-pulse rounded-lg bg-surface-2", className)}
      aria-hidden
    />
  );
}

export function EmptyState({
  title,
  body,
  action,
}: {
  title: string;
  body?: string;
  action?: React.ReactNode;
}) {
  return (
    <Card className="px-6 py-12 text-center">
      <p className="text-[16px] font-semibold text-ink">{title}</p>
      {body && <p className="mx-auto mt-1.5 max-w-sm text-[14px] text-muted">{body}</p>}
      {action && <div className="mt-5">{action}</div>}
    </Card>
  );
}

export function ErrorState({
  message,
  onRetry,
}: {
  message: string;
  onRetry?: () => void;
}) {
  return (
    <Card className="border-down/25 px-6 py-8 text-center">
      <p className="text-[15px] font-medium text-ink">Something went wrong</p>
      <p className="mx-auto mt-1.5 max-w-md text-[13.5px] text-muted">{message}</p>
      {onRetry && (
        <Button className="mt-4" onClick={onRetry}>
          Try again
        </Button>
      )}
    </Card>
  );
}

/** Wraps page content so route changes fade in rather than snapping. */
export function PageTransition({ children }: { children: React.ReactNode }) {
  return (
    <motion.div
      initial={{ opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.34, ease: [0.32, 0.72, 0, 1] }}
    >
      {children}
    </motion.div>
  );
}
