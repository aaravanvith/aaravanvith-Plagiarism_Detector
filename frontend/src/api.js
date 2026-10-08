const BASE_URL = (import.meta.env.VITE_API_URL || "https://vidya-chaya-audit.onrender.com").replace(/\/+$/, "");
let readiness = null;

async function waitForBackend() {
  if (!readiness) {
    readiness = (async () => {
      const deadline = Date.now() + 120000;
      while (Date.now() < deadline) {
        try {
          const res = await globalThis.fetch(`${BASE_URL}/api/health`, {
            signal: AbortSignal.timeout(10000), cache: "no-store",
          });
          if (res.ok && (await res.json()).status === "ok") return;
        } catch (_) {
          // Render can return a loading page or a network error during startup.
        }
        await new Promise((resolve) => setTimeout(resolve, 3000));
      }
      throw new Error("The backend did not start within two minutes. Please try again or check the Render service logs.");
    })().finally(() => { readiness = null; });
  }
  return readiness;
}

async function fetch(url, options = {}) {
  await waitForBackend();
  try {
    const res = await globalThis.fetch(url, {
      ...options, signal: AbortSignal.timeout(180000),
    });
    if ([502, 503, 504].includes(res.status)) {
      throw new Error("The backend is temporarily unavailable. Please try again after it finishes starting.");
    }
    return res;
  } catch (error) {
    if (error.name === "TimeoutError") {
      throw new Error("The backend took too long to respond. Try a smaller report or check the Render logs.");
    }
    if (error instanceof TypeError) {
      throw new Error("Unable to reach the backend. Check your connection and the Render service status.");
    }
    throw error;
  }
}

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

export async function analyzeReport(file, studentName, usn, online = false) {
  const form = new FormData();
  form.append("file", file);
  form.append("student_name", studentName || "");
  form.append("usn", usn || "");
  form.append("online", online ? "true" : "false");

  const res = await fetch(`${BASE_URL}/api/analyze`, {
    method: "POST",
    body: form,
  });

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
