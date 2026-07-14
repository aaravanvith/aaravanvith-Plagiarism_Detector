const BASE_URL = import.meta.env.VITE_API_URL || "http://localhost:8000";

async function handle(res) {
  if (!res.ok) {
    let detail = res.statusText;
    try {
      const body = await res.json();
      detail = body.detail || detail;
    } catch (_) {}
    throw new Error(detail);
  }
  return res.json();
}

export async function analyzeReport(file, studentName, usn) {
  const form = new FormData();
  form.append("file", file);
  form.append("student_name", studentName || "");
  form.append("usn", usn || "");
  const res = await fetch(`${BASE_URL}/api/analyze`, { method: "POST", body: form });
  return handle(res);
}

export async function correctSentence(sentence, matched_source, similarity) {
  const res = await fetch(`${BASE_URL}/api/correct`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ sentence, matched_source, similarity }),
  });
  return handle(res);
}

export async function sendChat(message, sentence, matched_source, similarity) {
  const res = await fetch(`${BASE_URL}/api/chat`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ message, sentence, matched_source, similarity }),
  });
  return handle(res);
}

export async function listReports() {
  const res = await fetch(`${BASE_URL}/api/reports`);
  return handle(res);
}

export async function deleteReport(id) {
  const res = await fetch(`${BASE_URL}/api/reports/${id}`, { method: "DELETE" });
  return handle(res);
}
