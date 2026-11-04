# IntelliLead AI, Phase 1: Data Intelligence Engine

Upload a CSV of companies, get structured company info and publicly detectable technologies back.

## Run

    python -m venv .venv && source .venv/bin/activate
    pip install -r requirements.txt
    python -m pytest -q
    uvicorn app.main:app --reload

API docs at http://localhost:8000/docs

## Use

    curl -F "file=@data/sample_companies.csv" http://localhost:8000/v1/jobs
    curl http://localhost:8000/v1/jobs/<job_id>
    curl -OJ "http://localhost:8000/v1/jobs/<job_id>/download?format=xlsx"

Input CSV needs a domain column (domain, website, url, ...). A company name column is optional.

## Design notes

- domain.py: normalises URLs, emails and bare hosts, rejects IPs and malformed hosts.
- ingestion.py: dedupes, keeps rejected rows with a reason, enforces a row limit.
- fetcher.py: respects robots.txt, caps response size, follows redirects manually and blocks
  private or internal addresses at every hop (SSRF guard).
- detector.py: signature rules over script URLs, HTML markers, meta generator and headers.
  Every detection keeps its evidence and a heuristic confidence.
- extractor.py: title, description, LinkedIn link, keyword based industry hint (a hint, not truth).
- export.py: CSV and Excel, with formula injection protection for scraped text.
- main.py: async job API. Jobs live in memory for the MVP.

## Known limits

- Homepage only, no JavaScript rendering. Playwright fallback comes later.
- DNS rebinding between the SSRF check and the connection is not fully closed. Run the
  service in a network with no route to internal hosts when deploying.
- No auth, no persistence, no rate limiting per client yet (Phase 4).
- Only scrape sites you are permitted to. Configure INTELLILEAD_USER_AGENT with a real contact URL.

## Config (env vars, prefix INTELLILEAD_)

CONCURRENCY, TIMEOUT_S, MAX_BYTES, MAX_ROWS, RESPECT_ROBOTS, BLOCK_PRIVATE, USER_AGENT
