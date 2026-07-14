import { useState } from "react";
import Header from "./components/Header";
import UploadPanel from "./components/UploadPanel";
import ScoreSeal from "./components/ScoreSeal";
import AIDetectionCard from "./components/AIDetectionCard";
import SentenceReport from "./components/SentenceReport";
import CorrectionPanel from "./components/CorrectionPanel";
import HistoryTable from "./components/HistoryTable";
import RepositoryPanel from "./components/RepositoryPanel";
import { analyzeReport } from "./api";
import { FileSearch, Layers } from "lucide-react";

export default function App() {
  const [view, setView] = useState("analyze");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [result, setResult] = useState(null);
  const [activeSentence, setActiveSentence] = useState(null);

  const handleAnalyze = async (file, studentName, usn) => {
    setLoading(true);
    setError(null);
    try {
      const res = await analyzeReport(file, studentName, usn);
      setResult(res);
    } catch (e) {
      setError(e.message || "Analysis failed");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="min-h-screen bg-paper">
      <Header view={view} setView={setView} />

      <main className="mx-auto max-w-6xl px-6 py-10">
        {view === "analyze" && (
          <div className="grid lg:grid-cols-[380px_1fr] gap-8">
            <div className="space-y-6">
              <UploadPanel onAnalyze={handleAnalyze} loading={loading} error={error} />
              {!result && (
                <div className="bg-white rounded-xl border border-ink-100 p-6 text-sm text-ink-500 leading-relaxed">
                  <div className="flex items-center gap-2 mb-2 text-ink-800 font-medium">
                    <Layers className="h-4 w-4 text-seal-500" /> How scoring works
                  </div>
                  Every sentence in the report is vectorized with TF-IDF and compared
                  by cosine similarity against reference literature and prior VTU
                  submissions. Matches above the threshold are flagged with the exact
                  source line, so every score is explainable — never a black box.
                </div>
              )}
            </div>

            <div>
              {result ? (
                <div className="space-y-6">
                  <div className="bg-white rounded-xl border border-ink-100 p-8 flex flex-col sm:flex-row items-center gap-8">
                    <ScoreSeal score={result.plagiarism_score} verdict={result.verdict} />
                    <div className="flex-1">
                      <h2 className="font-display text-2xl text-ink-900 mb-1">{result.filename}</h2>
                      <p className="text-sm text-ink-500 mb-4">
                        {result.flagged_sentence_count} of {result.total_sentences} sentences flagged,
                        compared against {result.sources_compared.length} reference source
                        {result.sources_compared.length === 1 ? "" : "s"}.
                      </p>
                      <p className="text-xs text-ink-400 mb-3">
                        {result.similarity_method?.semantic_available
                          ? "Hybrid score: TF-IDF overlap + cosine similarity + SBERT semantic similarity."
                          : "TF-IDF cosine scoring is active. Semantic scoring is unavailable or disabled."}
                      </p>
                      <div className="flex flex-wrap gap-2">
                        {result.sources_compared.map((s) => (
                          <span key={s} className="text-xs font-mono bg-ink-50 text-ink-600 rounded px-2 py-1">
                            {s}
                          </span>
                        ))}
                      </div>
                    </div>
                  </div>

                  <AIDetectionCard aiDetection={result.ai_detection} />

                  <SentenceReport
                    sentences={result.all_sentences}
                    onSelect={setActiveSentence}
                    activeSentence={activeSentence}
                  />
                </div>
              ) : (
                <div className="h-full min-h-[420px] flex flex-col items-center justify-center text-center bg-white rounded-xl border border-dashed border-ink-200 p-10">
                  <FileSearch className="h-10 w-10 text-ink-200 mb-3" />
                  <p className="font-display text-lg text-ink-600">No report analyzed yet</p>
                  <p className="text-sm text-ink-400 max-w-sm mt-1">
                    Upload a project report on the left to generate an explainable
                    plagiarism and AI-content report.
                  </p>
                </div>
              )}
            </div>
          </div>
        )}

        {view === "history" && <HistoryTable />}
        {view === "repository" && <RepositoryPanel />}
      </main>

      {activeSentence && (
        <>
          <div
            className="fixed inset-0 bg-ink-900/20 z-40"
            onClick={() => setActiveSentence(null)}
          />
          <CorrectionPanel sentence={activeSentence} onClose={() => setActiveSentence(null)} />
        </>
      )}
    </div>
  );
}
