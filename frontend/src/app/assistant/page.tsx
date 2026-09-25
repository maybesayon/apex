"use client";

import { motion } from "motion/react";
import { SendHorizontal } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { Card, PageTransition, SectionHeading, Spinner } from "@/components/ui";
import { API_BASE } from "@/lib/api";
import { cn } from "@/lib/utils";

type Message = { role: "user" | "assistant"; text: string; flagged?: boolean };

const SUGGESTIONS = [
  "Analyse NVDA",
  "How's the market today?",
  "What is RSI?",
  "Explain my portfolio",
];

/**
 * The backend emits light markdown (**bold**), so render that rather than
 * showing the asterisks. Deliberately not a full markdown parser: replies
 * are model output, and running arbitrary HTML from them would be unwise.
 */
function RichText({ text }: { text: string }) {
  return (
    <>
      {text.split(/(\*\*[^*]+\*\*)/g).map((part, i) =>
        part.startsWith("**") && part.endsWith("**") ? (
          <strong key={i} className="font-semibold">
            {part.slice(2, -2)}
          </strong>
        ) : (
          <span key={i}>{part}</span>
        ),
      )}
    </>
  );
}

function csrf() {
  return (
    document.cookie
      .split("; ")
      .find((c) => c.startsWith("apex_csrf="))
      ?.split("=")[1] ?? ""
  );
}

export default function AssistantPage() {
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState("");
  const [busy, setBusy] = useState(false);
  const endRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, busy]);

  async function send(text: string) {
    const trimmed = text.trim();
    if (!trimmed || busy) return;

    const history = messages.map((m) => ({ role: m.role, content: m.text }));
    setMessages((m) => [...m, { role: "user", text: trimmed }]);
    setInput("");
    setBusy(true);

    try {
      const res = await fetch(`${API_BASE}/chat`, {
        method: "POST",
        credentials: "include",
        headers: { "Content-Type": "application/json", "X-CSRF-Token": csrf() },
        body: JSON.stringify({ message: trimmed, history }),
      });
      if (!res.ok) throw new Error((await res.json())?.detail ?? "Request failed");
      const data = await res.json();
      setMessages((m) => [
        ...m,
        {
          role: "assistant",
          text: data.text ?? "No reply.",
          flagged: Boolean(data.emotion_flagged),
        },
      ]);
    } catch (e) {
      setMessages((m) => [
        ...m,
        {
          role: "assistant",
          text: e instanceof Error ? e.message : "Something went wrong.",
        },
      ]);
    } finally {
      setBusy(false);
    }
  }

  return (
    <PageTransition>
      <SectionHeading title="Assistant" />
      <p className="-mt-2 mb-4 max-w-2xl text-[13.5px] text-muted">
        Answers use your live quotes and your own holdings as context. Without
        an Anthropic API key it falls back to a built-in offline analyser.
      </p>

      <Card className="flex min-h-[58dvh] flex-col p-4">
        <div className="flex-1 space-y-3 overflow-y-auto">
          {messages.length === 0 && (
            <div className="flex h-full flex-col items-center justify-center gap-4 py-10 text-center">
              <p className="text-[14px] text-muted">
                Ask about a stock, a strategy, or your positions.
              </p>
              <div className="flex flex-wrap justify-center gap-2">
                {SUGGESTIONS.map((s) => (
                  <button
                    key={s}
                    onClick={() => void send(s)}
                    className="rounded-full border border-line-strong px-3.5 py-2 text-[13px] text-muted transition-colors hover:bg-surface-2 hover:text-ink"
                  >
                    {s}
                  </button>
                ))}
              </div>
            </div>
          )}

          {messages.map((m, i) => (
            <motion.div
              key={i}
              initial={{ opacity: 0, y: 6 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ duration: 0.24, ease: [0.32, 0.72, 0, 1] }}
              className={cn("flex", m.role === "user" ? "justify-end" : "justify-start")}
            >
              <div
                className={cn(
                  "max-w-[85%] whitespace-pre-wrap rounded-2xl px-4 py-2.5 text-[14px] leading-relaxed",
                  m.role === "user"
                    ? "bg-accent-soft text-ink"
                    : m.flagged
                      ? "bg-warn/10 text-ink"
                      : "bg-surface-2 text-ink",
                )}
              >
                <RichText text={m.text} />
              </div>
            </motion.div>
          ))}

          {busy && (
            <div className="flex items-center gap-2 px-1 text-[13px] text-muted">
              <Spinner className="size-3.5" />
              Thinking…
            </div>
          )}
          <div ref={endRef} />
        </div>

        <form
          onSubmit={(e) => {
            e.preventDefault();
            void send(input);
          }}
          className="mt-3 flex items-center gap-2 border-t border-line pt-3"
        >
          <input
            value={input}
            onChange={(e) => setInput(e.target.value)}
            placeholder="Ask anything about markets or your positions…"
            aria-label="Message"
            className="flex-1 rounded-full border border-line-strong bg-surface px-4 py-2.5 text-[15px] text-ink placeholder:text-faint focus:border-accent focus:outline-none focus:ring-[3.5px] focus:ring-accent-soft"
          />
          <button
            type="submit"
            disabled={busy || !input.trim()}
            aria-label="Send"
            className="flex size-10 shrink-0 items-center justify-center rounded-full bg-up text-white transition-transform active:scale-95 disabled:opacity-40"
          >
            <SendHorizontal className="size-[18px]" />
          </button>
        </form>
      </Card>

      <p className="mt-4 text-center text-[12px] text-faint">
        Replies are generated and may be wrong. Not financial advice.
      </p>
    </PageTransition>
  );
}
