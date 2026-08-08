"""Minimal, optional client for importing open-access records from CORE.

The client uses Python's standard library and never exposes ``CORE_API_KEY``
in API responses or logs. CORE is a reference-corpus source, not a training
database: imported documents are stored in the local repository first.
"""
from __future__ import annotations

import json
import threading
import time
from dataclasses import dataclass
from urllib.parse import urlencode
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from ..settings import CORE_API_KEY, CORE_API_URL

_lock = threading.Lock()
_last_request_at = 0.0
_MIN_REQUEST_INTERVAL_SECONDS = 2.1  # CORE free tier: at most 5 single requests / 10 seconds.


class CoreConfigurationError(RuntimeError):
    pass


class CoreRequestError(RuntimeError):
    pass


@dataclass
class CoreWork:
    title: str
    text: str
    authors: str = ""
    year: str = ""
    doi: str = ""


def configured() -> bool:
    return bool(CORE_API_KEY)


def _rate_limit() -> None:
    global _last_request_at
    with _lock:
        delay = _MIN_REQUEST_INTERVAL_SECONDS - (time.monotonic() - _last_request_at)
        if delay > 0:
            time.sleep(delay)
        _last_request_at = time.monotonic()


def search_works(query: str, limit: int = 5) -> list[CoreWork]:
    if not configured():
        raise CoreConfigurationError("CORE_API_KEY is not configured on this server")
    if not query.strip():
        raise CoreRequestError("A CORE search query is required")

    print(">>> CORE SEARCH QUERY:", query)
    print(">>> CORE SEARCH LIMIT:", limit)

    _rate_limit()
    params = urlencode({"q": query.strip(), "limit": min(max(limit, 1), 20)})
    request = Request(
        f"{CORE_API_URL}?{params}",
        headers={
            "Authorization": f"Bearer {CORE_API_KEY}",
            "Accept": "application/json",
            "User-Agent": "VTU-Plagiarism-Detector/1.0",
        },
    )
    try:
        with urlopen(request, timeout=20) as response:
            raw_response = response.read().decode("utf-8")

            print(">>> CORE HTTP STATUS:", response.status)
            print(">>> CORE RESPONSE:", raw_response[:2000])

            payload = json.loads(raw_response)
    except HTTPError as exc:
        if exc.code == 401:
            raise CoreRequestError("CORE rejected the configured API key. Generate a new key and update backend/.env.") from exc
        if exc.code == 429:
            raise CoreRequestError("CORE rate limit reached. Wait before importing more papers.") from exc
        raise CoreRequestError(f"CORE request failed with HTTP {exc.code}") from exc
    except Exception as exc:
        raise CoreRequestError("CORE request failed; check the configured API key and network access") from exc

    records = payload.get("results") or payload.get("data") or []
    works: list[CoreWork] = []
    for record in records:
        title = record.get("title") or "Untitled CORE record"
        abstract = record.get("abstract") or ""
        full_text = record.get("fullText") or record.get("fullTextText") or ""
        text = f"{title}\n\n{abstract}\n\n{full_text}".strip()
        if len(text.split()) < 4:
            continue
        authors = record.get("authors") or record.get("authorsText") or ""
        if isinstance(authors, list):
            authors = ", ".join(str(author.get("name", author)) if isinstance(author, dict) else str(author) for author in authors)
        works.append(CoreWork(
            title=title,
            text=text,
            authors=str(authors),
            year=str(record.get("publishedDate") or record.get("yearPublished") or ""),
            doi=str(record.get("doi") or ""),
        ))
    return works
