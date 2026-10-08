import { useRef, useState } from "react";
import { FileText, Loader2, UploadCloud, X } from "lucide-react";

export default function UploadPanel({ onAnalyze, loading, error }) {
  const [file, setFile] = useState(null);
  const [studentName, setStudentName] = useState("");
  const [usn, setUsn] = useState("");
  const [dragOver, setDragOver] = useState(false);
  const [online, setOnline] = useState(false);

  const inputRef = useRef(null);

  const submit = (e) => {
    e.preventDefault();

    if (file) {
      onAnalyze(file, studentName, usn, online);
    }
  };

  return (
    <form
      onSubmit={submit}
      className="bg-white rounded-xl border border-ink-100 p-6 shadow-[0_8px_30px_rgba(15,23,48,.04)] sm:p-8"
    >
      <h2 className="font-display text-2xl text-ink-900 mb-1">
        Submit Academic Report
      </h2>

      <p className="text-sm text-ink-400 mb-6">
        Analyze your healthcare or engineering report for plagiarism and AI-generated content.
      </p>

      {/* Analysis Mode */}
      <div className="mb-6">
        <label className="block text-xs font-medium text-ink-400 uppercase tracking-wide mb-2">
          Analysis mode
        </label>

        <div className="grid grid-cols-2 gap-3">

          {/* Offline */}
          <button
            type="button"
            onClick={() => setOnline(false)}
            className={`rounded-md border px-4 py-3 text-left transition ${
              !online
                ? "border-seal-500 bg-seal-400/10"
                : "border-ink-100 hover:border-ink-300"
            }`}
          >
            <p className="text-sm font-semibold text-ink-800">Offline</p><p className="mt-1 text-xs text-ink-400">Local Repository</p>
          </button>

          {/* Online */}
          <button
            type="button"
            onClick={() => setOnline(true)}
            className={`rounded-md border px-4 py-3 text-left transition ${
              online
                ? "border-seal-500 bg-seal-400/10"
                : "border-ink-100 hover:border-ink-300"
            }`}
          >
            <p className="text-sm font-semibold text-ink-800">Online</p><p className="mt-1 text-xs text-ink-400">Online Academic Search</p>
          </button>

        </div>
      </div>

      {/* File Upload */}
      <div
        onDragOver={(e) => {
          e.preventDefault();
          setDragOver(true);
        }}
        onDragLeave={() => setDragOver(false)}
        onDrop={(e) => {
          e.preventDefault();
          setDragOver(false);

          const droppedFile = e.dataTransfer.files?.[0];

          if (droppedFile) {
            setFile(droppedFile);
          }
        }}
        onClick={() => inputRef.current?.click()}
        className={`cursor-pointer rounded-lg border-2 border-dashed p-10 text-center transition ${
          dragOver
            ? "border-seal-500 bg-seal-400/5"
            : "border-ink-200 hover:border-ink-400"
        }`}
      >
        <input
          ref={inputRef}
          type="file"
          accept=".pdf,.docx,.txt"
          className="hidden"
          onChange={(e) => {
            setFile(e.target.files?.[0] || null);
          }}
        />

        {file ? (
          <div className="flex flex-col items-center gap-2">
            <FileText className="h-8 w-8 text-ink-600" />

            <p className="text-sm font-medium text-ink-800">
              {file.name}
            </p>

            <p className="text-xs text-ink-400">{(file.size / 1024 / 1024).toFixed(2)} MB · Click to change</p>
            <button type="button" onClick={(event) => { event.stopPropagation(); setFile(null); if (inputRef.current) inputRef.current.value = ""; }} className="inline-flex items-center gap-1 text-xs font-medium text-risk-high hover:underline"><X className="h-3 w-3" />Remove file</button>
          </div>
        ) : (
          <div className="flex flex-col items-center gap-2">
            <UploadCloud className="h-8 w-8 text-ink-400" />

            <p className="text-sm font-medium text-ink-600">
              Drop a report here, or click to browse
            </p>

            <p className="text-xs text-ink-400">
              .pdf · .docx · .txt
            </p>
          </div>
        )}
      </div>

      {/* Student Details */}
      <div className="grid grid-cols-2 gap-4 mt-6">

        <div>
          <label className="block text-xs font-medium text-ink-400 uppercase tracking-wide mb-1">
            Student name (optional)
          </label>

          <input
            value={studentName}
            onChange={(e) => setStudentName(e.target.value)}
            placeholder="Aarav Anvith S"
            className="w-full rounded-md border border-ink-100 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-seal-400"
          />
        </div>

        <div>
          <label className="block text-xs font-medium text-ink-400 uppercase tracking-wide mb-1">
            USN (optional)
          </label>

          <input
            value={usn}
            onChange={(e) => setUsn(e.target.value)}
            placeholder="1EW23CI001"
            className="w-full rounded-md border border-ink-100 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-seal-400"
          />
        </div>

      </div>

      {/* Error */}
      {error && (
        <p className="mt-4 text-sm text-risk-high bg-risk-highBg rounded-md px-3 py-2">
          {error}
        </p>
      )}

      {/* Analyze Button */}
      <button
        type="submit"
        disabled={!file || loading}
        className="mt-6 w-full flex items-center justify-center gap-2 rounded-md bg-ink-800 text-white py-3 text-sm font-semibold disabled:opacity-40 hover:bg-ink-900 transition"
      >
        {loading ? (
          <>
            <Loader2 className="h-4 w-4 animate-spin" />
            Connecting and analyzing report…
          </>
        ) : (
          "Run Academic Integrity Analysis"
        )}
      </button>
      {loading && <p role="status" className="mt-2 text-sm text-ink-500">The server may need up to two minutes to wake up before analysis starts.</p>}
    </form>
  );
}
