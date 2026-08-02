import os
import time
import requests
from pathlib import Path
from xml.etree import ElementTree as ET

# -----------------------------
# Configuration
# -----------------------------

SEARCH_QUERY = "healthcare OR medicine OR disease"
MAX_PAPERS = 500
BATCH_SIZE = 100

SAVE_FOLDER = Path("backend/healthcare_datasets/pubmed")
SAVE_FOLDER.mkdir(parents=True, exist_ok=True)

SEARCH_URL = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi"
FETCH_URL = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi"
def search_pubmed(query, max_results):
    params = {
        "db": "pubmed",
        "term": query,
        "retmax": max_results,
        "retmode": "json",
    }

    response = requests.get(SEARCH_URL, params=params)
    response.raise_for_status()

    data = response.json()
    return data["esearchresult"]["idlist"]

def fetch_pubmed_abstracts(id_list):
    params = {
        "db": "pubmed",
        "id": ",".join(id_list),
        "retmode": "xml",
    }

    response = requests.get(FETCH_URL, params=params)
    response.raise_for_status()

    root = ET.fromstring(response.text)

    papers = []

    for article in root.findall(".//PubmedArticle"):
        try:
            pmid = article.find(".//PMID").text

            title = article.find(".//ArticleTitle")
            title = "".join(title.itertext()) if title is not None else ""

            abstract = article.find(".//Abstract")
            if abstract is not None:
                abstract = " ".join(
                    "".join(t.itertext()) for t in abstract.findall("AbstractText")
                )
            else:
                abstract = ""

            if abstract.strip():
                papers.append({
                    "pmid": pmid,
                    "title": title,
                    "abstract": abstract,
                })

        except Exception:
            continue

    return papers

def save_papers(papers):
    for paper in papers:
        filename = SAVE_FOLDER / f"{paper['pmid']}.txt"

        with open(filename, "w", encoding="utf-8") as f:
            f.write(paper["title"])
            f.write("\n\n")
            f.write(paper["abstract"])

def main():
    print("Searching PubMed...")

    ids = search_pubmed(SEARCH_QUERY, MAX_PAPERS)
    print(f"Found {len(ids)} papers")

    for i in range(0, len(ids), BATCH_SIZE):
        batch = ids[i:i + BATCH_SIZE]

        print(f"Downloading batch {i//BATCH_SIZE + 1}")

        papers = fetch_pubmed_abstracts(batch)
        save_papers(papers)

        time.sleep(0.5)

    print("Download Complete!")

if __name__ == "__main__":
    main()