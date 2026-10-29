import { useEffect, useState } from "react";
import { CheckCircle2, Download, Layers, ScanSearch } from "lucide-react";
import Header from "./components/Header";
import UploadPanel from "./components/UploadPanel";
import ScoreSeal from "./components/ScoreSeal";
import SentenceReport from "./components/SentenceReport";
import CorrectionPanel from "./components/CorrectionPanel";
import HistoryTable from "./components/HistoryTable";
import RepositoryPanel from "./components/RepositoryPanel";
import { analyzeReport, autoCorrectDocument } from "./api";
import LandingPage from "./components/LandingPage";

export default function App() {
  const [path, setPath] = useState(() => window.location.pathname);
  useEffect(() => { const onPopState = () => setPath(window.location.pathname); window.addEventListener("popstate", onPopState); return () => window.removeEventListener("popstate", onPopState); }, []);
  if (path !== "/analysis") return <LandingPage />;
  return <AnalysisWorkspace />;
}

function AnalysisWorkspace() {
  const [view, setView] = useState("analyze");
  const [loading, setLoading] = useState(false), [error, setError] = useState(null), [result, setResult] = useState(null);
  const [activeSentence, setActiveSentence] = useState(null), [uploadedFile, setUploadedFile] = useState(null);
  const [appliedCorrections, setAppliedCorrections] = useState([]), [previewText, setPreviewText] = useState("");
  const [autoCorrecting, setAutoCorrecting] = useState(false), [autoCorrectError, setAutoCorrectError] = useState(""), [autoCorrectSummary, setAutoCorrectSummary] = useState(null);

  const handleAnalyze = async (file, online = false) => {
    setLoading(true);
    setError(null);
    try {
      const res = await analyzeReport(file, online);
      setResult(res);
      setActiveSentence(null);
      setUploadedFile(file);
      setAppliedCorrections([]);
      setAutoCorrectSummary(null);
      setPreviewText(res.extracted_text || "");
    } catch (e) {
      setError(e.message || "Analysis failed. Please try again.");
    } finally {
      setLoading(false);
    }
  };
  const applyCorrection = (correction) => setAppliedCorrections((current) => { const next = [...current.filter((item) => item.start_offset !== correction.start_offset), correction]; setPreviewText([...next].sort((a, b) => b.start_offset - a.start_offset).reduce((text, item) => text.slice(0, item.start_offset) + item.corrected + text.slice(item.end_offset), result?.extracted_text || "")); return next; });
  const downloadCorrectedDocument = async () => { if (!appliedCorrections.length || !uploadedFile) { setAutoCorrectError("Select at least one correction first."); return; } setAutoCorrecting(true); setAutoCorrectError(""); setAutoCorrectSummary(null); try { const { blob, filename, summary } = await autoCorrectDocument(uploadedFile, appliedCorrections); setAutoCorrectSummary(summary); const url = URL.createObjectURL(blob); const link = document.createElement("a"); link.href = url; link.download = filename; document.body.appendChild(link); link.click(); link.remove(); setTimeout(() => URL.revokeObjectURL(url), 60000); } catch (e) { setAutoCorrectError(e.message || "Could not generate the corrected report."); } finally { setAutoCorrecting(false); } };

  const handleSelectSentence = (sentence) => {
    // Only flagged sentences can be opened for correction
    if (sentence && sentence.flagged) {
      setActiveSentence(sentence);
    }
  };

  return <div className="analysis-shell min-h-screen bg-paper app-grid"><Header view={view} setView={setView} /><main className="mx-auto max-w-[1440px] px-5 py-7 sm:px-8 lg:ml-72 lg:px-10 lg:py-10">{view === "analyze" && <div className="grid gap-7 xl:grid-cols-[410px_minmax(0,1fr)]"><div className="space-y-6"><UploadPanel onAnalyze={handleAnalyze} loading={loading} error={error} />{!result && <div className="analysis-note rounded-xl border border-ink-100 bg-white p-6 text-sm leading-relaxed text-ink-500"><div className="mb-2 flex items-center gap-2 font-medium text-ink-800"><Layers className="h-4 w-4 text-seal-500" /> Vaidya Chaya Audit evidence layer</div>Review uses sentence-level evidence. The exact method shown in your results reflects the analysis returned by the platform.</div>}</div><div>{result ? <Results result={result} activeSentence={activeSentence} onSelectSentence={handleSelectSentence} corrections={appliedCorrections} preview={previewText} busy={autoCorrecting} autoError={autoCorrectError} summary={autoCorrectSummary} download={downloadCorrectedDocument} /> : <EmptyState />}</div></div>}{view === "history" && <HistoryTable />}{view === "repository" && <RepositoryPanel />}</main>{activeSentence && activeSentence.flagged && <><button aria-label="Close correction panel" className="fixed inset-0 z-40 bg-ink-900/20" onClick={() => setActiveSentence(null)} /><CorrectionPanel sentence={activeSentence} onClose={() => setActiveSentence(null)} onApply={applyCorrection} isApplied={appliedCorrections.some((item) => item.start_offset === activeSentence.start_offset)} /></>}</div>;
}

function Results({ result, activeSentence, onSelectSentence, corrections, preview, busy, autoError, summary, download }) {
  return (
    <div className="space-y-6">
      <section className="rounded-xl border border-ink-100 bg-white p-6 shadow-[0_8px_30px_rgba(15,23,48,.04)] sm:p-8">
        <div className="flex flex-col items-center gap-8 sm:flex-row">
          <ScoreSeal score={result.plagiarism_score} verdict={result.verdict} />
          <div className="flex-1">
            <div className="flex items-center gap-2">
              <p className="text-xs font-semibold uppercase tracking-[.14em] text-seal-600">Analysis complete</p>
              {result.analysis_mode && (
                <span className={`inline-flex items-center rounded-full px-2 py-0.5 text-[11px] font-medium ${
                  result.analysis_mode === "online" && result.online_sources_compared > 0
                    ? "bg-seal-50 text-seal-700 border border-seal-200"
                    : "bg-ink-100 text-ink-700 border border-ink-200"
                }`}>
                  {result.analysis_mode === "online" && result.online_sources_compared > 0
                    ? "Online Mode · Academic Search"
                    : "Offline Mode · Local Corpus"}
                </span>
              )}
            </div>
            <h2 className="font-display text-2xl text-ink-900">{result.filename}</h2>
            <p className="mt-2 text-sm text-ink-500">
              {result.flagged_sentence_count} of {result.total_sentences} sentences flagged ·{" "}
              {result.analysis_mode === "online" && result.online_sources_compared > 0 ? (
                <span>
                  <strong className="text-seal-700 font-semibold">{result.total_sources_compared} sources compared</strong>{" "}
                  ({result.online_sources_compared} online from CORE + {result.local_sources_compared} local)
                </span>
              ) : (
                <span>
                  <strong className="text-ink-700 font-semibold">{result.total_sources_compared} local sources compared</strong>
                </span>
              )}
            </p>
            <p className="mt-3 text-xs text-ink-400">{result.similarity_method?.semantic_available ? "Hybrid score: TF-IDF, cosine similarity, and semantic similarity." : "TF-IDF cosine scoring is active. Semantic scoring is unavailable or disabled."}</p>
          </div>
        </div>
      </section>

      <Methodology semantic={result.similarity_method?.semantic_available} />

      <SentenceReport
        plagiarismScore={result.plagiarism_score}
        sourcesCompared={result.total_sources_compared}
        sentences={result.all_sentences || result.flagged_sentences || []}
        onSelect={onSelectSentence}
        activeSentence={activeSentence}
      />

      <section className="rounded-xl border border-ink-100 bg-white p-6">
        <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
          <div>
            <div className="flex items-center gap-2">
              <CheckCircle2 className="h-5 w-5 text-seal-500" />
              <h3 className="font-display text-lg text-ink-900">Corrected Report</h3>
            </div>
            <p className="text-sm text-ink-500">
              {corrections.length} selected correction{corrections.length === 1 ? "" : "s"}. Open a flagged sentence, review the source passage, then click Apply to include its rewrite in the download. PDF exports contain extracted text and do not preserve the original images or layout.
            </p>
          </div>
          <button type="button" disabled={busy || !corrections.length} onClick={download} className="rounded-md bg-ink-800 px-4 py-2 text-sm font-semibold text-white hover:bg-ink-900 disabled:opacity-40">
            <Download className="mr-2 inline h-4 w-4" />{busy ? "Generating corrected report..." : "Generate Corrected Report"}
          </button>
        </div>
        {busy && <p className="mt-3 text-sm text-ink-500">Generating corrected report...</p>}
        {autoError && <p role="alert" className="mt-3 text-sm text-risk-high">{autoError}</p>}
        {summary && (
          <div role="status" className="mt-3 rounded-md bg-ink-50 p-3 text-sm text-ink-700">
            <p>Applied corrections: {summary.applied}</p>
            <p>Skipped corrections: {summary.skipped.length}</p>
          </div>
        )}
        <pre className="mt-4 max-h-64 overflow-auto whitespace-pre-wrap rounded-md bg-ink-50 p-3 font-sans text-sm text-ink-700">{preview}</pre>
      </section>
    </div>
  );
}

function EmptyState() {
  return (
    <div className="flex min-h-[480px] flex-col items-center justify-center rounded-xl border border-dashed border-ink-200 bg-white/80 p-10 text-center">
      <div className="mb-4 grid h-14 w-14 place-items-center rounded-full bg-seal-400/10">
        <ScanSearch className="h-7 w-7 text-seal-500" />
      </div>
      <p className="font-display text-lg text-ink-600">No report analyzed yet</p>
      <p className="mt-1 max-w-sm text-sm text-ink-400">Upload a project report to generate an explainable plagiarism report.</p>
    </div>
  );
}

function Methodology({ semantic }) {
  return (
    <section className="rounded-xl border border-ink-100 bg-white p-6">
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
        <div>
          <p className="text-xs font-semibold uppercase tracking-[.14em] text-seal-600">Analysis methodology</p>
          <h3 className="mt-1 font-display text-lg text-ink-900">How the plagiarism analysis works</h3>
          <p className="mt-1 text-sm text-ink-500">Sentence-level similarity analysis against the selected academic reference corpus.</p>
        </div>
        <div className="flex flex-wrap items-center gap-2 text-xs font-medium text-ink-600">
          <span className="rounded bg-ink-50 px-2.5 py-2">TF-IDF</span>
          <span>→</span>
          <span className="rounded bg-ink-50 px-2.5 py-2">Cosine similarity</span>
          {semantic && (
            <>
              <span>→</span>
              <span className="rounded bg-seal-400/10 px-2.5 py-2 text-seal-600">Semantic similarity</span>
            </>
          )}
          <span>→</span>
          <span className="rounded bg-ink-900 px-2.5 py-2 text-white">Explainable result</span>
        </div>
      </div>
    </section>
  );
}
