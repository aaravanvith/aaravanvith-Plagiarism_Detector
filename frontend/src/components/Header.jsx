import { ShieldCheck } from "lucide-react";

export default function Header({ view, setView }) {
  return (
    <header className="border-b border-ink-100 bg-white">
      <div className="mx-auto max-w-6xl px-6 py-5 flex items-center justify-between">
        <div className="flex items-center gap-3">
          <div className="h-10 w-10 rounded-full bg-ink-800 flex items-center justify-center">
            <ShieldCheck className="h-5 w-5 text-seal-400" strokeWidth={2} />
          </div>
          <div>
            <h1 className="font-display text-xl font-semibold text-ink-900 leading-tight">
              Plagiarism Detector
            </h1>
            <p className="text-xs text-ink-400 tracking-wide uppercase">
              VTU Project Report Plagiarism Detector
            </p>
          </div>
        </div>
        <nav className="flex gap-1">
          <button
            onClick={() => setView("analyze")}
            className={`px-4 py-2 rounded-md text-sm font-medium transition ${
              view === "analyze"
                ? "bg-ink-800 text-white"
                : "text-ink-600 hover:bg-ink-50"
            }`}
          >
            Analyze
          </button>
          <button
            onClick={() => setView("history")}
            className={`px-4 py-2 rounded-md text-sm font-medium transition ${
              view === "history"
                ? "bg-ink-800 text-white"
                : "text-ink-600 hover:bg-ink-50"
            }`}
          >
            Submission History
          </button>
          <button
            onClick={() => setView("repository")}
            className={`px-4 py-2 rounded-md text-sm font-medium transition ${
              view === "repository"
                ? "bg-ink-800 text-white"
                : "text-ink-600 hover:bg-ink-50"
            }`}
          >
            Repository
          </button>
        </nav>
      </div>
    </header>
  );
}
