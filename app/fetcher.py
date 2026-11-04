import asyncio
import ipaddress
import socket
from dataclasses import dataclass
from datetime import datetime, timezone
from urllib.parse import urlparse
from urllib.robotparser import RobotFileParser

import httpx

from .config import Settings


class BlockedHost(Exception):
    pass


class TooManyRedirects(Exception):
    pass


@dataclass
class FetchResult:
    domain: str
    status: str  # ok, blocked_by_robots, blocked_host, unreachable, http_error, not_html
    url: str | None = None
    final_url: str | None = None
    status_code: int | None = None
    html: str | None = None
    headers: dict | None = None
    error: str | None = None
    fetched_at: str = ""


async def is_public_host(host: str) -> bool:
    """SSRF guard: every resolved address must be globally routable."""
    try:
        ipaddress.ip_address(host)
        ips = {host}
    except ValueError:
        loop = asyncio.get_running_loop()
        try:
            infos = await loop.getaddrinfo(host, None, type=socket.SOCK_STREAM)
        except socket.gaierror:
            return True  # unresolvable, the request itself will fail as unreachable
        ips = {i[4][0] for i in infos}
    return all(ipaddress.ip_address(ip.split("%")[0]).is_global for ip in ips)


async def _get(client: httpx.AsyncClient, url: str, cfg: Settings, max_redirects: int = 5):
    """GET with manual redirects so every hop is checked, and a hard body size cap."""
    for _ in range(max_redirects + 1):
        host = urlparse(url).hostname or ""
        if cfg.block_private and not await is_public_host(host):
            raise BlockedHost(host)
        async with client.stream("GET", url) as resp:
            if resp.is_redirect:
                loc = resp.headers.get("location")
                if not loc:
                    raise TooManyRedirects("redirect without location")
                url = str(resp.url.join(loc))
                continue
            body = bytearray()
            async for chunk in resp.aiter_bytes():
                body.extend(chunk)
                if len(body) >= cfg.max_bytes:
                    break
            return resp.status_code, dict(resp.headers), bytes(body), url, resp.encoding
    raise TooManyRedirects(url)


async def robots_allowed(client: httpx.AsyncClient, domain: str, cfg: Settings) -> bool:
    """Allowed unless a readable robots.txt disallows the homepage for our bot."""
    try:
        status, _, body, _, enc = await _get(client, f"https://{domain}/robots.txt", cfg)
    except BlockedHost:
        raise
    except (httpx.HTTPError, TooManyRedirects):
        return True
    if status != 200:
        return True
    rp = RobotFileParser()
    rp.parse(body.decode(enc or "utf-8", errors="replace").splitlines())
    return rp.can_fetch(cfg.robots_token, f"https://{domain}/")


def _decode(body: bytes, enc: str | None) -> str:
    try:
        return body.decode(enc or "utf-8", errors="replace")
    except LookupError:
        return body.decode("utf-8", errors="replace")


async def fetch_homepage(client: httpx.AsyncClient, domain: str, cfg: Settings) -> FetchResult:
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    res = FetchResult(domain=domain, status="unreachable", fetched_at=now)

    if cfg.respect_robots:
        try:
            if not await robots_allowed(client, domain, cfg):
                res.status = "blocked_by_robots"
                return res
        except BlockedHost:
            res.status = "blocked_host"
            return res

    for scheme in ("https", "http"):
        url = f"{scheme}://{domain}/"
        res.url = url
        try:
            code, headers, body, final_url, enc = await _get(client, url, cfg)
        except BlockedHost:
            res.status = "blocked_host"
            return res
        except (httpx.HTTPError, TooManyRedirects) as e:
            res.error = type(e).__name__
            continue

        res.status_code, res.headers, res.final_url = code, headers, final_url
        ctype = headers.get("content-type", "").lower()
        if code >= 400:
            res.status, res.error = "http_error", f"HTTP {code}"
        elif ctype and "html" not in ctype:
            res.status, res.error = "not_html", ctype.split(";")[0]
        else:
            res.status, res.error = "ok", None
            res.html = _decode(body, enc)
        return res
    return res
