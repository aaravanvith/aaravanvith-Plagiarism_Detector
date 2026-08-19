import { useEffect, useRef, useState } from "react";
import { Archive, Database, FileUp, Search } from "lucide-react";
import {
  archiveRepositoryDocument,
  coreStatus,
  importFromCore,
  listRepositoryDocuments,
  repositoryStats,
  uploadRepositoryDocument,
} from "../api";

const initialMetadata = { title: "", department: "", subject: "", project_type: "Research Paper" };

export default function RepositoryPanel() {
  const [documents, setDocuments] = useState([]);
  const [stats, setStats] = useState(null);
  const [query, setQuery] = useState("");
  const [departmentFilter, setDepartmentFilter] = useState("");
  const [subjectFilter, setSubjectFilter] = useState("");
  const [metadata, setMetadata] = useState(initialMetadata);
  const [file, setFile] = useState(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [coreReady, setCoreReady] = useState(false);
  const [coreQuery, setCoreQuery] = useState("");
  const inputRef = useRef(null);

  const load = async (q = query) => {
    const [items, totals] = await Promise.all([listRepositoryDocuments({ q, department: departmentFilter, subject: subjectFilter }), repositoryStats()]);
    setDocuments(items);
    setStats(totals);
  };

  useEffect(() => {
    load().catch((e) => setError(e.message));
    coreStatus().then((status) => setCoreReady(status.configured)).catch(() => setCoreReady(false));
  }, []);

  const submit = async (event) => {
    event.preventDefault();
    if (!file) return;
    setBusy(true); setError("");
    try {
      await uploadRepositoryDocument(file, metadata);
      setFile(null); setMetadata(initialMetadata);
      if (inputRef.current) inputRef.current.value = "";
      await load();
    } catch (e) { setError(e.message); } finally { setBusy(false); }
  };

  const archive = async (id) => {
    await archiveRepositoryDocument(id);
    await load();
  };

  const importCore = async () => {
    if (!coreQuery.trim()) return;
    setBusy(true); setError("");
    try { await importFromCore(coreQuery); await load(); } catch (e) { setError(e.message); } finally { setBusy(false); }
  };

  return (
    <div className="space-y-6">
      <div className="grid sm:grid-cols-4 gap-4">
        <Stat label="Documents" value={stats?.total_documents ?? "—"} />
        <Stat label="Paragraphs" value={stats?.total_paragraphs ?? "—"} />
        <Stat label="Words indexed" value={stats?.total_words?.toLocaleString?.() ?? "—"} />
        <Stat label="Pending approval" value={stats?.pending_approval ?? "—"} />
      </div>

      <div className="grid lg:grid-cols-[360px_1fr] gap-6">
        <form onSubmit={submit} className="bg-white rounded-xl border border-ink-100 p-6 space-y-4">
          <div className="flex items-center gap-2"><Database className="h-5 w-5 text-seal-500" /><h2 className="font-display text-xl">Add reference material</h2></div>
          <p className="text-xs text-ink-400">PDF, DOCX, TXT, Markdown, or RTF. Stored locally and indexed by paragraphs.</p>
          <input ref={inputRef} type="file" accept=".pdf,.docx,.txt,.md,.markdown,.rtf" onChange={(e) => setFile(e.target.files?.[0] || null)} className="block w-full text-sm text-ink-600" />
          {file && <p className="text-xs text-ink-500">{file.name}</p>}
          <Field label="Title" value={metadata.title} onChange={(title) => setMetadata({ ...metadata, title })} />
          <Field label="Department" value={metadata.department} onChange={(department) => setMetadata({ ...metadata, department })} />
          <Field label="Subject" value={metadata.subject} onChange={(subject) => setMetadata({ ...metadata, subject })} />
          <Field label="Type" value={metadata.project_type} onChange={(project_type) => setMetadata({ ...metadata, project_type })} />
          {error && <p className="text-xs text-risk-high">{error}</p>}
          <button disabled={!file || busy} className="w-full rounded-md bg-ink-800 text-white py-2.5 text-sm font-medium disabled:opacity-40">
            <FileUp className="inline h-4 w-4 mr-2" />{busy ? "Indexing…" : "Add to repository"}
          </button>
        </form>

        <div className="bg-white rounded-xl border border-ink-100 p-6">
          <div className="flex gap-2 mb-3">
            <input value={query} onChange={(e) => setQuery(e.target.value)} onKeyDown={(e) => e.key === "Enter" && load()} placeholder="Search title, keyword, student, or USN" className="flex-1 rounded-md border border-ink-100 px-3 py-2 text-sm" />
            <button onClick={() => load()} className="rounded-md border border-ink-100 px-3 text-ink-600"><Search className="h-4 w-4" /></button>
          </div>
          <div className="mb-5 grid gap-2 sm:grid-cols-2">
            <input value={departmentFilter} onChange={(e) => setDepartmentFilter(e.target.value)} onKeyDown={(e) => e.key === "Enter" && load()} placeholder="Filter by department" aria-label="Filter by department" className="rounded-md border border-ink-100 px-3 py-2 text-sm" />
            <input value={subjectFilter} onChange={(e) => setSubjectFilter(e.target.value)} onKeyDown={(e) => e.key === "Enter" && load()} placeholder="Filter by subject" aria-label="Filter by subject" className="rounded-md border border-ink-100 px-3 py-2 text-sm" />
          </div>
          <div className="space-y-2">
            {documents.length === 0 ? <p className="text-sm text-ink-400 py-8 text-center">No repository documents found.</p> : documents.map((doc) => (
              <div key={doc.id} className="border border-ink-100 rounded-lg p-4 flex items-start justify-between gap-4">
                <div><p className="font-medium text-ink-800">{doc.title || doc.filename}</p><p className="text-xs text-ink-400 mt-1">{doc.filename} · {doc.word_count} words · {doc.project_type || "Document"}</p><p className="text-xs text-ink-500 mt-2">{doc.keywords.join(", ")}</p></div>
                <button onClick={() => archive(doc.id)} title="Archive" className="text-ink-400 hover:text-risk-high"><Archive className="h-4 w-4" /></button>
              </div>
            ))}
          </div>
        </div>
      </div>

      <div className="bg-white rounded-xl border border-ink-100 p-6 flex flex-col sm:flex-row sm:items-center gap-4">
        <div className="flex-1"><h3 className="font-display text-lg text-ink-900">Import open-access papers from CORE</h3><p className="text-xs text-ink-400 mt-1">{coreReady ? "Uses the server-side CORE key and imports papers into your local repository." : "Add CORE_API_KEY to backend/.env to enable this optional importer."}</p></div>
        <div className="flex gap-2"><input value={coreQuery} onChange={(e) => setCoreQuery(e.target.value)} placeholder="e.g. machine learning plagiarism" disabled={!coreReady || busy} className="w-64 rounded-md border border-ink-100 px-3 py-2 text-sm disabled:bg-ink-50" /><button onClick={importCore} disabled={!coreReady || !coreQuery.trim() || busy} className="rounded-md bg-ink-800 text-white px-4 text-sm disabled:opacity-40">Import</button></div>
      </div>
    </div>
  );
}

function Stat({ label, value }) { return <div className="bg-white border border-ink-100 rounded-xl p-4"><p className="text-xs uppercase tracking-wide text-ink-400">{label}</p><p className="font-mono text-2xl text-ink-800 mt-1">{value}</p></div>; }
function Field({ label, value, onChange }) { return <label className="block text-xs text-ink-500">{label}<input value={value} onChange={(e) => onChange(e.target.value)} className="mt-1 w-full rounded-md border border-ink-100 px-3 py-2 text-sm text-ink-800" /></label>; }
