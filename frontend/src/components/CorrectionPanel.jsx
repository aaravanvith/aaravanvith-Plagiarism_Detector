import { useEffect, useState } from "react";
import { Sparkles, MessageCircle, Send, X, Quote } from "lucide-react";
import { correctSentence, sendChat } from "../api";

export default function CorrectionPanel({ sentence, onClose }) {
  const [correction, setCorrection] = useState(null);
  const [loading, setLoading] = useState(true);
  const [messages, setMessages] = useState([]);
  const [input, setInput] = useState("");
  const [sending, setSending] = useState(false);

  useEffect(() => {
    if (!sentence) return;
    setLoading(true);
    setMessages([]);
    correctSentence(sentence.sentence, sentence.matched_source, sentence.similarity)
      .then((res) => {
        setCorrection(res);
        setMessages([
          { from: "agent", text: res.explanation },
        ]);
      })
      .finally(() => setLoading(false));
  }, [sentence]);

  const send = async (e) => {
    e.preventDefault();
    if (!input.trim()) return;
    const userMsg = input;
    setMessages((m) => [...m, { from: "user", text: userMsg }]);
    setInput("");
    setSending(true);
    try {
      const res = await sendChat(userMsg, sentence.sentence, sentence.matched_source, sentence.similarity);
      setMessages((m) => [...m, { from: "agent", text: res.reply }]);
    } finally {
      setSending(false);
    }
  };

  if (!sentence) return null;

  return (
    <div className="fixed inset-y-0 right-0 w-full sm:w-[420px] bg-white border-l border-ink-100 shadow-2xl flex flex-col z-50">
      <div className="flex items-center justify-between px-5 py-4 border-b border-ink-100">
        <div className="flex items-center gap-2">
          <Sparkles className="h-4 w-4 text-seal-500" />
          <h3 className="font-display text-lg text-ink-900">Correction Agent</h3>
        </div>
        <button onClick={onClose} className="text-ink-400 hover:text-ink-800">
          <X className="h-5 w-5" />
        </button>
      </div>

      <div className="flex-1 overflow-y-auto px-5 py-4 space-y-5">
        <div className="rounded-lg bg-ink-50 p-3">
          <p className="text-xs uppercase tracking-wide text-ink-400 mb-1">Flagged sentence</p>
          <p className="text-sm text-ink-800">{sentence.sentence}</p>
          <p className="text-xs text-ink-400 mt-2">
            Matched <span className="font-mono">{sentence.matched_source}</span> ·{" "}
            <span className="font-mono">{sentence.similarity}%</span> similarity
          </p>
        </div>

        {loading && <p className="text-sm text-ink-400">Generating explanation…</p>}

        {correction && (
          <>
            <Section title="Suggested rewrite">
              <p className="text-sm text-ink-800 bg-risk-lowBg rounded-md p-3">
                {correction.rewritten}
              </p>
            </Section>

            <Section title="Citation guidance" icon={<Quote className="h-3.5 w-3.5" />}>
              <p className="text-xs font-mono text-ink-600 bg-ink-50 rounded p-2 mb-1">
                APA: {correction.citation_apa}
              </p>
              <p className="text-xs font-mono text-ink-600 bg-ink-50 rounded p-2">
                IEEE: {correction.citation_ieee}
              </p>
            </Section>
          </>
        )}

        <Section title="Ask the agent" icon={<MessageCircle className="h-3.5 w-3.5" />}>
          <div className="space-y-2">
            {messages.map((m, i) => (
              <div
                key={i}
                className={`text-sm rounded-lg px-3 py-2 max-w-[90%] ${
                  m.from === "agent"
                    ? "bg-ink-50 text-ink-800"
                    : "bg-ink-800 text-white ml-auto"
                }`}
              >
                {m.text}
              </div>
            ))}
            {sending && <p className="text-xs text-ink-400">Thinking…</p>}
          </div>
        </Section>
      </div>

      <form onSubmit={send} className="border-t border-ink-100 p-3 flex gap-2">
        <input
          value={input}
          onChange={(e) => setInput(e.target.value)}
          placeholder="Why is this sentence flagged?"
          className="flex-1 rounded-md border border-ink-100 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-seal-400"
        />
        <button
          type="submit"
          className="rounded-md bg-ink-800 text-white px-3 py-2 hover:bg-ink-900"
        >
          <Send className="h-4 w-4" />
        </button>
      </form>
    </div>
  );
}

function Section({ title, icon, children }) {
  return (
    <div>
      <p className="flex items-center gap-1.5 text-xs uppercase tracking-wide text-ink-400 mb-2">
        {icon}
        {title}
      </p>
      {children}
    </div>
  );
}
