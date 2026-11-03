
"""Semantic Scholar API client for academic research retrieval."""

import json
import logging
from urllib.parse import urlencode
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError

from ..settings import (
    SEMANTIC_SCHOLAR_API_URL,
    SEMANTIC_SCHOLAR_API_KEY,
    ONLINE_PROVIDER_TIMEOUT,
)

logger = logging.getLogger(__name__)


class SemanticScholarRequestError(RuntimeError):
    pass


def search_works(query: str, limit: int = 10) -> list[dict]:
    """Search Semantic Scholar and return normalized academic records."""

    if not query.strip():
        raise SemanticScholarRequestError(
            "Semantic Scholar search query is empty."
        )

    params = {
        "query": query.strip(),
        "limit": min(max(limit, 1), 20),
        "fields": "title,abstract,year,externalIds,openAccessPdf",
    }

    url = f"{SEMANTIC_SCHOLAR_API_URL}?{urlencode(params)}"

    headers = {
        "Accept": "application/json",
        "User-Agent": "VaidyaChayaAudit/1.0",
    }

    if SEMANTIC_SCHOLAR_API_KEY:
        headers["x-api-key"] = SEMANTIC_SCHOLAR_API_KEY

    request = Request(url, headers=headers)

    try:
        with urlopen(
            request,
            timeout=ONLINE_PROVIDER_TIMEOUT
        ) as response:
            payload = json.loads(
                response.read().decode("utf-8")
            )

    except HTTPError as exc:
        logger.warning(
            "Semantic Scholar HTTP error: %s",
            exc.code
        )

        raise SemanticScholarRequestError(
            f"Semantic Scholar returned HTTP {exc.code}"
        ) from exc

    except (URLError, TimeoutError, OSError) as exc:
        logger.warning(
            "Semantic Scholar connection failed: %s",
            exc
        )

        raise SemanticScholarRequestError(
            f"Semantic Scholar request failed: {exc}"
        ) from exc

    except Exception as exc:
        logger.exception(
            "Unexpected Semantic Scholar error"
        )

        raise SemanticScholarRequestError(
            f"Could not process Semantic Scholar response: {exc}"
        ) from exc

    works = []

    for record in payload.get("data", []):
        title = record.get("title") or "Untitled Semantic Scholar paper"

        abstract = record.get("abstract") or ""

        text = f"{title}\n\n{abstract}".strip()

        # Require enough actual text for meaningful comparison.
        if len(text.split()) < 20:
            continue

        external_ids = record.get("externalIds") or {}

        doi = external_ids.get("DOI") or ""

        works.append({
            "title": title,
            "text": text,
            "doi": doi,
            "year": str(record.get("year") or ""),
            "source": "Semantic Scholar",
            "id": str(record.get("paperId") or ""),
        })

    logger.info(
        "Semantic Scholar returned %d usable papers",
        len(works)
    )

    return works
