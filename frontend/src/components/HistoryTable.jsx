import { useEffect, useState } from "react";
import { Trash2 } from "lucide-react";
import { listReports, deleteReport } from "../api";

const VERDICT_COLOR = {
  HIGH: "text-risk-high bg-risk-highBg",
  MODERATE: "text-risk-medium bg-risk-mediumBg",
  LOW: "text-risk-low bg-risk-lowBg",
};

export default function HistoryTable() {
  const [reports, setReports] = useState([]);
  const [loading, setLoading] = useState(true);

  const load = () => {
    setLoading(true);
    listReports().then(setReports).finally(() => setLoading(false));
  };

  useEffect(load, []);

  const remove = async (id) => {
    await deleteReport(id);
    load();
  };

  if (loading) return <p className="text-sm text-ink-400">Loading submission history…</p>;

  if (reports.length === 0) {
    return (
      <div className="bg-white rounded-xl border border-ink-100 p-10 text-center">
        <p className="text-ink-400 text-sm">No reports analyzed yet.</p>
      </div>
    );
  }

  return (
    <div className="bg-white rounded-xl border border-ink-100 overflow-hidden">
      <table className="w-full text-sm">
        <thead>
          <tr className="border-b border-ink-100 text-left text-xs uppercase tracking-wide text-ink-400">
            <th className="px-5 py-3">File</th>
            <th className="px-5 py-3">Student</th>
            <th className="px-5 py-3">USN</th>
            <th className="px-5 py-3">Plagiarism</th>
            <th className="px-5 py-3">AI-likelihood</th>
            <th className="px-5 py-3">Submitted</th>
            <th className="px-5 py-3"></th>
          </tr>
        </thead>
        <tbody>
          {reports.map((r) => (
            <tr key={r.id} className="border-b border-ink-100 last:border-0">
              <td className="px-5 py-3 font-medium text-ink-800">{r.filename}</td>
              <td className="px-5 py-3 text-ink-600">{r.student_name || "—"}</td>
              <td className="px-5 py-3 font-mono text-ink-600">{r.usn || "—"}</td>
              <td className="px-5 py-3">
                <span className={`px-2 py-0.5 rounded-full text-xs font-semibold ${VERDICT_COLOR[r.verdict]}`}>
                  {r.plagiarism_score}% · {r.verdict}
                </span>
              </td>
              <td className="px-5 py-3 text-ink-600">{r.ai_probability}% ({r.ai_label})</td>
              <td className="px-5 py-3 text-ink-400 text-xs">
                {new Date(r.created_at).toLocaleString()}
              </td>
              <td className="px-5 py-3">
                <button onClick={() => remove(r.id)} className="text-ink-400 hover:text-risk-high">
                  <Trash2 className="h-4 w-4" />
                </button>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
