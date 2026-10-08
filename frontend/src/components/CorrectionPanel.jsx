import { useEffect, useState } from "react";
import { Sparkles, MessageCircle, Send, X, Quote } from "lucide-react";
import { correctSentence, sendChat } from "../api";

export default function CorrectionPanel({ sentence, onClose, onApply, isApplied }) {
  const [correction, setCorrection] = useState(null);
  const [rewriteMode, setRewriteMode] = useState("academic");
  const [rewriteStrength, setRewriteStrength] = useState("moderate");
  const [loading, setLoading] = useState(true);
  const [messages, setMessages] = useState([]);
  const [input, setInput] = useState("");
  const [sending, setSending] = useState(false);
  const [requestError, setRequestError] = useState("");

  useEffect(() => {
    if (!sentence) return;
    let cancelled = false;
    setCorrection(null);
    setLoading(true);
    setMessages([]);
    setRewriteMode("academic");
    setRequestError("");
    correctSentence(sentence.sentence, sentence.matched_source, sentence.similarity, rewriteStrength, sentence.start_offset, sentence.end_offset)
      .then((res) => {
        if (cancelled) return;
        setCorrection(res);
        setMessages([
          { from: "agent", text: sentence.flagged ? res.explanation : "This sentence is below the similarity flag threshold. You can still review and apply a suggested rewrite." },
        ]);
      })
      .catch((error) => { if (!cancelled) setRequestError(error.message || "Could not load the correction agent."); })
      .finally(() => { if (!cancelled) setLoading(false); });
    return () => { cancelled = true; };
  }, [sentence, rewriteStrength]);

  const send = async (e) => {
    e.preventDefault();
    if (!input.trim()) return;
    const userMsg = input;
    setMessages((m) => [...m, { from: "user", text: userMsg }]);
    setInput("");
    setRequestError("");
    setSending(true);
    try {
      const res = await sendChat(userMsg, sentence.sentence, sentence.matched_source, sentence.similarity);
      setMessages((m) => [...m, { from: "agent", text: res.reply }]);
    } catch (error) {
      setRequestError(error.message || "The correction agent could not answer right now.");
    } finally {
      setSending(false);
    }
  };

  if (!sentence) return null;

  return (
    <div role="dialog" aria-modal="true" aria-labelledby="correction-panel-title" className="fixed inset-y-0 right-0 w-full sm:w-[480px] bg-white border-l border-ink-100 shadow-2xl flex flex-col z-50">
      <div className="flex items-center justify-between px-5 py-4 border-b border-ink-100">
        <div className="flex items-center gap-2">
          <Sparkles className="h-4 w-4 text-seal-500" />
          <h3 id="correction-panel-title" className="font-display text-lg text-ink-900">Correction Chatbot</h3>
        </div>
        <button type="button" aria-label="Close correction chatbot" onClick={onClose} className="text-ink-400 hover:text-ink-800">
          <X className="h-5 w-5" />
        </button>
      </div>

      <div className="flex-1 overflow-y-auto px-5 py-4 space-y-5">
        <div className="rounded-lg bg-ink-50 p-3">
          <p className="text-xs uppercase tracking-wide text-ink-400 mb-1">{sentence.flagged ? "Potential similarity match — review the evidence" : "Selected sentence — optional rewrite"}</p>
          <p className="text-sm text-ink-800">{sentence.sentence}</p>
          <p className="text-xs text-ink-400 mt-2">
            Matched <span className="font-mono">{sentence.matched_source}</span> ·{" "}
            <span className="font-mono">{sentence.similarity}%</span> similarity
          </p>
          <p className="mt-3 text-xs uppercase tracking-wide text-ink-400">Matching source passage</p>
          <p className="mt-1 text-sm text-ink-700">{sentence.matched_text || "Source passage unavailable."}</p>
          <p className="mt-2 text-xs text-ink-500">Shared terminology alone does not establish plagiarism. Check the passage and citation before applying a rewrite.</p>
        </div>

        {loading && <p role="status" className="text-sm text-ink-400">Generating the corrected sentence…</p>}

        {correction && (
          <>
            <Section title="Corrected sentence">
              <label className="mb-2 flex items-center justify-between gap-3 text-xs text-ink-500">
                Rewrite strength
                <select
                  value={rewriteStrength}
                  onChange={(event) => setRewriteStrength(event.target.value)}
                  className="rounded border border-ink-100 bg-white px-2 py-1 text-xs text-ink-700 focus:outline-none focus:ring-2 focus:ring-seal-400"
                >
                  <option value="light">Light</option>
                  <option value="moderate">Moderate</option>
                  <option value="strong">Strong</option>
                  <option value="maximum">Maximum</option>
                </select>
              </label>
              <div className="flex gap-1 mb-2" role="tablist" aria-label="Rewrite mode">
                {[
                  ["academic", "Academic"],
                  ["human", "Human"],
                  ["simple", "Simple"],
                ].map(([mode, label]) => (
                  <button
                    key={mode}
                    type="button"
                    role="tab"
                    aria-selected={rewriteMode === mode}
                    onClick={() => setRewriteMode(mode)}
                    className={`rounded px-2.5 py-1 text-xs ${
                      rewriteMode === mode
                        ? "bg-ink-800 text-white"
                        : "bg-ink-50 text-ink-600 hover:bg-ink-100"
                    }`}
                  >
                    {label}
                  </button>
                ))}
              </div>
              <p className="mb-1 text-xs font-semibold capitalize text-seal-600">{rewriteMode} version</p>
              <p role="tabpanel" aria-live="polite" key={rewriteMode} className="text-sm text-ink-800 bg-risk-lowBg rounded-md p-3">
                {correction.rewrites?.[rewriteMode] || correction.rewritten}
              </p>
              <button
                type="button"
                disabled={loading || !Number.isInteger(correction.start_offset) || correction.end_offset <= correction.start_offset}
                onClick={() => onApply({
                  original: correction.original,
                  corrected: correction.rewrites?.[rewriteMode] || correction.rewritten,
                  start_offset: correction.start_offset,
                  end_offset: correction.end_offset,
                })}
                className="mt-2 w-full rounded-md bg-seal-500 px-3 py-2 text-sm font-medium text-white hover:bg-seal-600"
              >
                {isApplied ? "Update applied correction" : "Apply corrected sentence"}
              </button>
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
            {requestError && <p role="alert" className="text-xs text-risk-high">{requestError}</p>}
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
          disabled={sending}
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
