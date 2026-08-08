import { useRef, useState } from "react";
import { UploadCloud, FileText, Loader2 } from "lucide-react";

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
      className="bg-white rounded-xl border border-ink-100 p-8"
    >
      <h2 className="font-display text-2xl text-ink-900 mb-1">
        Submit a report for review
      </h2>

      <p className="text-sm text-ink-400 mb-6">
        PDF, DOCX, or TXT. Compare against the local reference corpus
        or expand the analysis with additional academic sources online.
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
            <p className="text-sm font-semibold text-ink-800">
              Offline
            </p>

            <p className="text-xs text-ink-400 mt-1">
              
            </p>
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
            <p className="text-sm font-semibold text-ink-800">
              Online
            </p>

            <p className="text-xs text-ink-400 mt-1">
              
            </p>
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

            <p className="text-xs text-ink-400">
              Click to choose a different file
            </p>
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
            Analyzing report…
          </>
        ) : (
          "Run plagiarism & AI-content analysis"
        )}
      </button>
    </form>
  );
}