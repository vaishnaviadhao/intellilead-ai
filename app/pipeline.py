import asyncio
import json

import httpx
import pandas as pd

from .config import Settings
from .crawler import crawl_company

OUTPUT_COLUMNS = [
    "company_name", "domain", "status", "error",
    "page_title", "meta_description", "site_name", "headline",
    "language", "linkedin_url", "twitter_url", "github_url", "contact_email",
    "industry_hint", "industry_confidence", "industry_evidence",
    "technologies", "tech_categories", "tech_count", "tech_details",
    "pages_crawled", "pages_discovered", "pages_blocked_by_robots",
    "bytes_downloaded", "page_details", "crawl_errors",
    "source_url", "http_status", "extracted_at",
]


async def _enrich_one(client, row, cfg, company_sem, on_progress):
    async with company_sem:
        try:
            crawl = await crawl_company(client, row["domain"], cfg)
            info = crawl.company_info or {}
            technologies = crawl.technologies or []
            homepage = next(
                (p for p in crawl.pages if p.get("page_type") == "homepage" and p.get("status") == "ok"),
                {},
            )
            record = {column: "" for column in OUTPUT_COLUMNS}
            record.update(
                company_name=row["company_name"],
                domain=row["domain"],
                status=crawl.status,
                error="; ".join(crawl.errors),
                source_url=crawl.homepage_url,
                http_status=homepage.get("http_status", ""),
                extracted_at=pd.Timestamp.now(tz="UTC").isoformat(),
                technologies="; ".join(t["name"] for t in technologies),
                tech_categories="; ".join(sorted({t["category"] for t in technologies})),
                tech_count=len(technologies),
                tech_details=json.dumps(technologies, ensure_ascii=False),
                pages_crawled=crawl.pages_crawled,
                pages_discovered=crawl.pages_discovered,
                pages_blocked_by_robots=crawl.pages_blocked_by_robots,
                bytes_downloaded=crawl.bytes_downloaded,
                page_details=json.dumps(crawl.pages, ensure_ascii=False),
                crawl_errors=json.dumps(crawl.errors, ensure_ascii=False),
            )
            for key, value in info.items():
                if key in record:
                    record[key] = value
            return record
        except Exception as exc:
            record = {column: "" for column in OUTPUT_COLUMNS}
            record.update(
                company_name=row.get("company_name", ""),
                domain=row.get("domain", ""),
                status="processing_error",
                error=type(exc).__name__,
                extracted_at=pd.Timestamp.now(tz="UTC").isoformat(),
            )
            return record
        finally:
            if on_progress:
                on_progress()


async def run_pipeline(
    companies: pd.DataFrame,
    cfg: Settings,
    client: httpx.AsyncClient | None = None,
    on_progress=None,
) -> pd.DataFrame:
    own_client = client is None
    if own_client:
        client = httpx.AsyncClient(
            headers={
                "User-Agent": cfg.user_agent,
                "Accept": "text/html,application/xhtml+xml",
            },
            timeout=httpx.Timeout(cfg.timeout_s),
            follow_redirects=False,
            limits=httpx.Limits(max_connections=max(2, cfg.concurrency * 3)),
        )
    try:
        company_sem = asyncio.Semaphore(cfg.concurrency)
        tasks = [
            _enrich_one(client, row, cfg, company_sem, on_progress)
            for row in companies.to_dict("records")
        ]
        records = await asyncio.gather(*tasks)
    finally:
        if own_client:
            await client.aclose()
    return pd.DataFrame(records, columns=OUTPUT_COLUMNS)
