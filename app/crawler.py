"""Bounded, same-host, robots-aware multi-page company crawler.

This crawler only requests public HTTP(S) pages, respects robots.txt when enabled,
does not execute JavaScript, and applies page/depth/byte limits.
"""
import asyncio
import ipaddress
import re
from collections import deque
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from urllib.parse import urldefrag, urljoin, urlparse, urlunparse
from urllib.robotparser import RobotFileParser

import httpx
from bs4 import BeautifulSoup

from .detector import detect_technologies
from .extractor import extract_company_info
from .fetcher import BlockedHost, TooManyRedirects, _get, fetch_homepage
from .config import Settings


SKIP_EXTENSIONS = {
    ".jpg", ".jpeg", ".png", ".gif", ".webp", ".svg", ".ico",
    ".pdf", ".zip", ".gz", ".mp4", ".mp3", ".mov", ".avi",
    ".css", ".js", ".map", ".woff", ".woff2", ".ttf", ".eot",
    ".xlsx", ".xls", ".doc", ".docx", ".ppt", ".pptx",
}
SKIP_PATH_PARTS = {
    "logout", "log-out", "cart", "checkout", "account", "login",
    "signin", "sign-in", "register", "search", "wp-admin",
    "privacy-preferences", "unsubscribe",
}
PRIORITY_PATHS = (
    ("/about", 0), ("/company", 0), ("/products", 0),
    ("/solutions", 0), ("/services", 0), ("/platform", 0),
    ("/technology", 0), ("/pricing", 1), ("/customers", 1),
    ("/case-studies", 1), ("/blog", 2), ("/careers", 2),
)


@dataclass
class PageRecord:
    url: str
    depth: int
    status: str
    http_status: int | None = None
    title: str = ""
    page_type: str = "other"
    technologies: list[dict] = field(default_factory=list)
    error: str = ""


@dataclass
class CrawlResult:
    domain: str
    status: str
    homepage_url: str = ""
    pages_crawled: int = 0
    pages_discovered: int = 0
    pages_blocked_by_robots: int = 0
    bytes_downloaded: int = 0
    pages: list[dict] = field(default_factory=list)
    technologies: list[dict] = field(default_factory=list)
    company_info: dict = field(default_factory=dict)
    errors: list[str] = field(default_factory=list)

    def as_dict(self):
        return asdict(self)


def _host_key(url: str) -> str:
    host = (urlparse(url).hostname or "").lower().rstrip(".")
    return host[4:] if host.startswith("www.") else host


def _clean_url(base_url: str, href: str, allowed_host: str) -> str | None:
    if not href:
        return None
    candidate = urljoin(base_url, href.strip())
    candidate, _fragment = urldefrag(candidate)
    parsed = urlparse(candidate)

    if parsed.scheme.lower() not in {"http", "https"}:
        return None
    if parsed.username or parsed.password:
        return None
    if _host_key(candidate) != allowed_host:
        return None
    if parsed.port not in (None, 80, 443):
        return None

    path = parsed.path or "/"
    lower_path = path.lower()
    if any(part in SKIP_PATH_PARTS for part in lower_path.split("/")):
        return None
    if any(lower_path.endswith(ext) for ext in SKIP_EXTENSIONS):
        return None

    # Remove query strings to avoid crawl traps and duplicate tracking URLs.
    normalized = urlunparse((
        parsed.scheme.lower(),
        parsed.netloc.lower(),
        re.sub("/{2,}", "/", path),
        "",
        "",
        "",
    ))
    return normalized


def _page_type(url: str) -> str:
    path = urlparse(url).path.lower().strip("/")
    if not path:
        return "homepage"
    first = path.split("/", 1)[0]
    mapping = {
        "about": "about", "company": "about", "who-we-are": "about",
        "product": "products", "products": "products", "solutions": "solutions",
        "services": "services", "platform": "technology", "technology": "technology",
        "pricing": "pricing", "blog": "blog", "resources": "resources",
        "case-studies": "case_studies", "customers": "customers",
        "careers": "careers",
    }
    return mapping.get(first, "other")


def _link_priority(url: str) -> tuple[int, str]:
    path = urlparse(url).path.lower()
    for prefix, priority in PRIORITY_PATHS:
        if path == prefix or path.startswith(prefix + "/") or path.startswith(prefix + "-"):
            return priority, url
    return 3, url


async def _robots_parser(client: httpx.AsyncClient, domain: str, cfg: Settings):
    parser = RobotFileParser()
    robots_url = f"https://{domain}/robots.txt"
    try:
        code, _headers, body, _final, enc = await _get(client, robots_url, cfg)
        if code == 200:
            parser.parse(body.decode(enc or "utf-8", errors="replace").splitlines())
            return parser
    except (httpx.HTTPError, BlockedHost, TooManyRedirects, UnicodeError):
        pass
    # Conservative fallback follows the existing fetcher behavior: unavailable
    # robots.txt is treated as no published disallow rule.
    parser.parse(["User-agent: *", "Allow: /"])
    return parser


async def crawl_company(
    client: httpx.AsyncClient,
    domain: str,
    cfg: Settings,
    max_pages: int | None = None,
    max_depth: int | None = None,
    max_total_bytes: int | None = None,
) -> CrawlResult:
    """Crawl a bounded set of internal pages and aggregate evidence per company."""
    max_pages = max_pages or getattr(cfg, "max_pages_per_company", 15)
    max_depth = max_depth if max_depth is not None else getattr(cfg, "max_crawl_depth", 2)
    max_total_bytes = max_total_bytes or getattr(cfg, "max_total_bytes_per_company", 10_000_000)

    result = CrawlResult(domain=domain, status="unreachable")
    homepage = await fetch_homepage(client, domain, cfg)
    if homepage.status != "ok" or not homepage.html:
        result.status = homepage.status
        if homepage.error:
            result.errors.append(homepage.error)
        return result

    start_url = homepage.final_url or homepage.url or f"https://{domain}/"
    result.homepage_url = start_url
    allowed_host = _host_key(start_url)
    robots = await _robots_parser(client, domain, cfg) if cfg.respect_robots else None

    queue = deque([(start_url, 0)])
    seen = set()
    page_records: list[PageRecord] = []
    tech_by_name: dict[str, dict] = {}
    company_info: dict = {}
    total_bytes = 0
    discovered = 1
    per_company_limit = max(1, int(max_pages))
    max_depth = max(0, int(max_depth))

    while queue and len(page_records) < per_company_limit:
        url, depth = queue.popleft()
        if url in seen:
            continue
        seen.add(url)

        if robots and not robots.can_fetch(cfg.robots_token, url):
            result.pages_blocked_by_robots += 1
            page_records.append(PageRecord(url=url, depth=depth, status="blocked_by_robots"))
            continue

        try:
            if url == start_url:
                code = homepage.status_code or 200
                headers = homepage.headers or {}
                html = homepage.html or ""
                final_url = homepage.final_url or url
                body_size = len(html.encode("utf-8", errors="replace"))
            else:
                code, headers, body, final_url, enc = await _get(client, url, cfg)
                body_size = len(body)
                ctype = headers.get("content-type", "").lower()
                if code >= 400:
                    page_records.append(PageRecord(
                        url=url, depth=depth, status="http_error", http_status=code,
                        page_type=_page_type(url), error=f"HTTP {code}",
                    ))
                    continue
                if ctype and "html" not in ctype:
                    page_records.append(PageRecord(
                        url=url, depth=depth, status="not_html", http_status=code,
                        page_type=_page_type(url), error=f"Content-Type: {ctype}",
                    ))
                    continue
                html = body.decode(enc or "utf-8", errors="replace")

            if total_bytes + body_size > max_total_bytes:
                result.errors.append("max_total_bytes_reached")
                break
            total_bytes += body_size

            # Redirects must remain on the original host; _get checks public IPs
            # at every redirect hop, and this check prevents off-site content use.
            if _host_key(final_url) != allowed_host:
                page_records.append(PageRecord(
                    url=url, depth=depth, status="external_redirect",
                    page_type=_page_type(url), error="Redirect left the original host",
                ))
                continue

            info = extract_company_info(html)
            if not company_info:
                company_info = info
            else:
                for key, value in info.items():
                    if not company_info.get(key) and value:
                        company_info[key] = value

            detections = detect_technologies(html, headers)
            page_techs = []
            for detection in detections:
                item = detection.as_dict()
                item["evidence_urls"] = [final_url]
                page_techs.append(item)
                existing = tech_by_name.get(detection.name)
                if existing:
                    existing["confidence"] = max(existing["confidence"], detection.confidence)
                    existing["evidence"] = sorted(set(existing["evidence"] + item["evidence"]))
                    existing["evidence_urls"] = sorted(set(existing["evidence_urls"] + [final_url]))
                    existing["pages_seen"] += 1
                else:
                    item["pages_seen"] = 1
                    tech_by_name[detection.name] = item

            soup = BeautifulSoup(html, "html.parser")
            page_title = soup.title.get_text(" ", strip=True)[:300] if soup.title else ""
            page_records.append(PageRecord(
                url=final_url, depth=depth, status="ok", http_status=code,
                title=page_title, page_type=_page_type(final_url),
                technologies=page_techs,
            ))

            if depth < max_depth and len(page_records) < per_company_limit:
                candidates = []
                for anchor in soup.find_all("a", href=True):
                    candidate = _clean_url(final_url, anchor.get("href"), allowed_host)
                    if candidate and candidate not in seen:
                        candidates.append(candidate)
                candidates = sorted(set(candidates), key=_link_priority)
                for candidate in candidates:
                    if candidate not in seen:
                        queue.append((candidate, depth + 1))
                        discovered += 1

        except BlockedHost:
            page_records.append(PageRecord(url=url, depth=depth, status="blocked_host"))
        except TooManyRedirects as exc:
            page_records.append(PageRecord(
                url=url, depth=depth, status="redirect_error", error=str(exc)[:300]
            ))
        except (httpx.HTTPError, UnicodeError, ValueError) as exc:
            page_records.append(PageRecord(
                url=url, depth=depth, status="fetch_error",
                page_type=_page_type(url), error=type(exc).__name__,
            ))
        except Exception as exc:
            # A single malformed page must not abort the whole company crawl.
            page_records.append(PageRecord(
                url=url, depth=depth, status="processing_error",
                page_type=_page_type(url), error=type(exc).__name__,
            ))

    result.pages = [asdict(page) for page in page_records]
    result.pages_crawled = sum(1 for page in page_records if page.status == "ok")
    result.pages_discovered = discovered
    result.bytes_downloaded = total_bytes
    result.technologies = sorted(tech_by_name.values(), key=lambda x: (x["category"], x["name"]))
    result.company_info = company_info
    result.errors.extend(
        f"{page['status']}:{page['url']}" for page in result.pages
        if page["status"] not in {"ok", "blocked_by_robots"}
    )
    result.status = "ok" if result.pages_crawled else "crawl_failed"
    return result
