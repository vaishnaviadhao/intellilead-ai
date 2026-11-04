import asyncio
import json

import httpx
import pandas as pd

from .config import Settings
from .detector import detect_technologies
from .extractor import extract_company_info
from .fetcher import fetch_homepage

OUTPUT_COLUMNS = [
    "company_name", "domain", "status", "error", "page_title", "meta_description",
    "site_name", "headline", "language", "linkedin_url", "industry_hint",
    "technologies", "tech_categories", "tech_count", "tech_details",
    "source_url", "http_status", "extracted_at",
]


async def _enrich_one(client, row, cfg, sem, on_progress):
    async with sem:
        fetch = await fetch_homepage(client, row["domain"], cfg)

    rec = {c: "" for c in OUTPUT_COLUMNS}
    rec.update(
        company_name=row["company_name"],
        domain=row["domain"],
        status=fetch.status,
        error=fetch.error or "",
        source_url=fetch.final_url or fetch.url or "",
        http_status=fetch.status_code if fetch.status_code is not None else "",
        extracted_at=fetch.fetched_at,
        tech_count=0,
    )
    if fetch.status == "ok":
        rec.update(extract_company_info(fetch.html))
        techs = detect_technologies(fetch.html, fetch.headers)
        rec["technologies"] = "; ".join(t.name for t in techs)
        rec["tech_categories"] = "; ".join(sorted({t.category for t in techs}))
        rec["tech_count"] = len(techs)
        rec["tech_details"] = json.dumps([t.as_dict() for t in techs], ensure_ascii=False)
    if on_progress:
        on_progress()
    return rec


async def run_pipeline(
    companies: pd.DataFrame,
    cfg: Settings,
    client: httpx.AsyncClient | None = None,
    on_progress=None,
) -> pd.DataFrame:
    own_client = client is None
    if own_client:
        client = httpx.AsyncClient(
            headers={"User-Agent": cfg.user_agent, "Accept": "text/html,application/xhtml+xml"},
            timeout=httpx.Timeout(cfg.timeout_s),
            follow_redirects=False,  # redirects are followed manually so each hop is checked
            limits=httpx.Limits(max_connections=cfg.concurrency * 2),
        )
    try:
        sem = asyncio.Semaphore(cfg.concurrency)
        tasks = [
            _enrich_one(client, row, cfg, sem, on_progress)
            for row in companies.to_dict("records")
        ]
        records = await asyncio.gather(*tasks)
    finally:
        if own_client:
            await client.aclose()
    return pd.DataFrame(records, columns=OUTPUT_COLUMNS)
