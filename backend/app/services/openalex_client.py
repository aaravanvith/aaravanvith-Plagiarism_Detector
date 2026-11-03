
"""OpenAlex client for retrieving academic research papers."""

import logging
from urllib.parse import urlencode
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError

from ..settings import (
    OPENALEX_API_URL,
    OPENALEX_API_KEY,
    ONLINE_PROVIDER_TIMEOUT,
)

logger = logging.getLogger(__name__)


class OpenAlexRequestError(RuntimeError):
    pass


def search_works(query: str, limit: int = 10) -> list[dict]:
    """Search OpenAlex and return normalized academic records."""

    if not query.strip():
        raise OpenAlexRequestError("OpenAlex search query is empty.")

    params = {
        "search": query.strip(),
        "per-page": min(max(limit, 1), 25),
    }

    if OPENALEX_API_KEY:
        params["api_key"] = OPENALEX_API_KEY

    url = f"{OPENALEX_API_URL}?{urlencode(params)}"

    request = Request(
        url,
        headers={
            "Accept": "application/json",
            "User-Agent": "VaidyaChayaAudit/1.0",
        },
    )

    try:
        with urlopen(
            request,
            timeout=ONLINE_PROVIDER_TIMEOUT
        ) as response:
            import json
            payload = json.loads(response.read().decode("utf-8"))

    except (HTTPError, URLError, TimeoutError, OSError) as exc:
        logger.warning("OpenAlex request failed: %s", exc)
        raise OpenAlexRequestError(
            f"OpenAlex request failed: {exc}"
        ) from exc

    except Exception as exc:
        logger.exception("Unexpected OpenAlex error")
        raise OpenAlexRequestError(
            f"Could not process OpenAlex response: {exc}"
        ) from exc

    works = []

    for record in payload.get("results", []):
        title = record.get("title") or "Untitled OpenAlex paper"

        abstract = ""

        inverted_index = record.get("abstract_inverted_index")

        if isinstance(inverted_index, dict):
            positions = []

            for word, indexes in inverted_index.items():
                for index in indexes:
                    positions.append((index, word))

            abstract = " ".join(
                word for _, word in sorted(positions)
            )

        text = f"{title}\n\n{abstract}".strip()

        if len(text.split()) < 20:
            continue

        doi = record.get("doi") or ""

        works.append({
            "title": title,
            "text": text,
            "doi": doi,
            "year": str(record.get("publication_year") or ""),
            "source": "OpenAlex",
            "id": str(record.get("id") or ""),
        })

    logger.info("OpenAlex returned %d usable papers", len(works))

    return works
