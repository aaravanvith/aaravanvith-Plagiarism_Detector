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

export async function correctSentence(sentence, matched_source, similarity, rewrite_strength = "moderate", start_offset, end_offset) {
  const res = await fetch(`${BASE_URL}/api/correct`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ sentence, matched_source, similarity, rewrite_strength, start_offset, end_offset }),
  });
  return handle(res);
}

export async function autoCorrectDocument(file, corrections) {
  const form = new FormData();
  form.append("file", file);
  form.append("corrections", JSON.stringify(corrections));
  const response = await fetch(`${BASE_URL}/api/auto-correct`, { method: "POST", body: form });
  if (!response.ok) {
    let detail = response.statusText;
    try { detail = (await response.json()).detail || detail; } catch (_) {}
    throw new Error(detail);
  }

  const applied = Number.parseInt(response.headers.get("x-applied-corrections") || "0", 10) || 0;
  const skippedCount = Number.parseInt(response.headers.get("x-skipped-corrections") || "0", 10) || 0;
  return {
    blob: await response.blob(),
    filename: filenameFromDisposition(response.headers.get("content-disposition")),
    summary: {
      applied,
      // The current UI renders skipped entries as warning rows. The direct
      // file response supplies counts only, so retain that compatible shape.
      skipped: Array.from({ length: skippedCount }, () => ({ reason: "A correction could not be applied." })),
    },
  };
}

function filenameFromDisposition(disposition) {
  const match = disposition?.match(/filename="?([^";]+)"?/i);
  return match?.[1] || "Corrected_Report";
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

export async function repositoryStats() {
  return handle(await fetch(`${BASE_URL}/api/repository/stats`));
}

export async function listRepositoryDocuments({ q = "", department = "", subject = "" } = {}) {
  const params = new URLSearchParams();
  if (q) params.set("q", q);
  if (department) params.set("department", department);
  if (subject) params.set("subject", subject);
  return handle(await fetch(`${BASE_URL}/api/repository/documents?${params}`));
}

export async function uploadRepositoryDocument(file, metadata = {}) {
  const form = new FormData();
  form.append("file", file);
  Object.entries(metadata).forEach(([key, value]) => form.append(key, value || ""));
  return handle(await fetch(`${BASE_URL}/api/repository/documents`, { method: "POST", body: form }));
}

export async function archiveRepositoryDocument(id) {
  return handle(await fetch(`${BASE_URL}/api/repository/documents/${id}/archive`, { method: "POST" }));
}

export async function coreStatus() {
  return handle(await fetch(`${BASE_URL}/api/repository/core/status`));
}

export async function importFromCore(query, limit = 5) {
  const params = new URLSearchParams({ query, limit: String(limit) });
  return handle(await fetch(`${BASE_URL}/api/repository/core/import?${params}`, { method: "POST" }));
}
