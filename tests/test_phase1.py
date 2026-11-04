import asyncio
import io

import httpx
import pandas as pd
import pytest

from app.config import Settings
from app.detector import detect_technologies
from app.domain import normalize_domain
from app.export import sanitize, to_csv_bytes, to_excel_bytes
from app.extractor import extract_company_info
from app.ingestion import load_companies
from app.pipeline import run_pipeline

HTML = """
<html lang="en"><head>
<title>Acme Cloud Platform</title>
<meta name="description" content="Acme is a cloud software platform with an API for developers and analytics automation.">
<meta name="generator" content="WordPress 6.4">
<script src="https://www.googletagmanager.com/gtm.js?id=GTM-1"></script>
<script src="//js.hs-scripts.com/123.js"></script>
<script src="https://js.stripe.com/v3/"></script>
</head><body><h1>Software for teams</h1>
<a href="https://www.linkedin.com/company/acme">LinkedIn</a>
<img src="/wp-content/uploads/logo.png"></body></html>
"""


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("https://www.Stripe.com/pricing?x=1", "stripe.com"),
        ("shopify.com", "shopify.com"),
        ("  HTTP://Sub.Example.co.in:8080/a ", "sub.example.co.in"),
        ("sales@acme.io", "acme.io"),
        ("bücher.de", "xn--bcher-kva.de"),
        ("not a domain", None),
        ("localhost", None),
        ("192.168.1.10", None),
        ("", None),
        (None, None),
        ("nan", None),
        ("-bad-.com", None),
    ],
)
def test_normalize_domain(raw, expected):
    assert normalize_domain(raw) == expected


def test_detector_signals_and_evidence():
    headers = {"Server": "cloudflare", "CF-Ray": "abc", "X-Powered-By": "Next.js"}
    techs = {t.name: t for t in detect_technologies(HTML, headers)}
    for name in ["WordPress", "Google Tag Manager", "HubSpot", "Stripe", "Cloudflare", "Next.js"]:
        assert name in techs
    assert techs["Cloudflare"].confidence >= 0.93  # two header hits
    assert any(e.startswith("generator:") for e in techs["WordPress"].evidence)
    assert "Shopify" not in techs


def test_detector_empty_input():
    assert detect_technologies(None, None) == []
    assert detect_technologies("", {}) == []


def test_extractor():
    info = extract_company_info(HTML)
    assert info["page_title"] == "Acme Cloud Platform"
    assert info["linkedin_url"].endswith("/company/acme")
    assert info["industry_hint"] == "Software and SaaS"
    assert info["language"] == "en"


def test_extractor_social_and_email():
    html = """
    <html><head><title>Test Tech</title></head><body>
    <a href="https://twitter.com/testtech">Twitter</a>
    <a href="https://github.com/testtech/repo">GitHub</a>
    <a href="mailto:contact@testtech.io?subject=Hi">Email</a>
    </body></html>
    """
    info = extract_company_info(html)
    assert info["twitter_url"] == "https://twitter.com/testtech"
    assert info["github_url"] == "https://github.com/testtech/repo"
    assert info["contact_email"] == "contact@testtech.io"


def test_ingestion_dedupe_and_rejects():
    csv = (
        "Company Name,Website\n"
        "Stripe,https://stripe.com\nStripe Dup,STRIPE.com/x\nBad,not a domain\n,hubspot.com\n"
    )
    res = load_companies(io.StringIO(csv))
    assert list(res.valid["domain"]) == ["stripe.com", "hubspot.com"]
    assert res.valid.loc[1, "company_name"] == "Hubspot"
    assert set(res.rejected["reason"]) == {"invalid_domain", "duplicate_domain"}
    assert res.stats["valid"] == 2 and res.stats["duplicates"] == 1 and res.stats["invalid"] == 1


def test_ingestion_errors():
    with pytest.raises(ValueError):
        load_companies(io.StringIO("foo,bar\n1,2\n"))
    with pytest.raises(ValueError):
        load_companies(io.StringIO("domain\na.com\nb.com\n"), max_rows=1)


def _cfg(**kw):
    return Settings(block_private=False, **kw)


def _client(handler):
    return httpx.AsyncClient(transport=httpx.MockTransport(handler), follow_redirects=False)


def test_pipeline_end_to_end_with_mock_transport():
    def handler(request: httpx.Request):
        host, path = request.url.host, request.url.path
        if host == "blocked.com" and path == "/robots.txt":
            return httpx.Response(200, text="User-agent: *\nDisallow: /")
        if path == "/robots.txt":
            return httpx.Response(404)
        if host == "acme.com":
            return httpx.Response(200, text=HTML, headers={"content-type": "text/html", "server": "cloudflare"})
        if host == "moved.com":
            return httpx.Response(301, headers={"location": "https://acme.com/"})
        if host == "down.com":
            raise httpx.ConnectError("boom")
        if host == "pdf.com":
            return httpx.Response(200, content=b"%PDF", headers={"content-type": "application/pdf"})
        return httpx.Response(500)

    companies = pd.DataFrame(
        {
            "company_name": ["Acme", "Blocked", "Moved", "Down", "Pdf", "Err"],
            "domain": ["acme.com", "blocked.com", "moved.com", "down.com", "pdf.com", "err.com"],
        }
    )

    async def go():
        async with _client(handler) as c:
            return await run_pipeline(companies, _cfg(), client=c)

    out = asyncio.run(go()).set_index("domain")
    assert out.loc["acme.com", "status"] == "ok"
    assert "HubSpot" in out.loc["acme.com", "technologies"]
    assert out.loc["acme.com", "tech_count"] >= 5
    assert out.loc["blocked.com", "status"] == "blocked_by_robots"
    assert out.loc["moved.com", "status"] == "ok"
    assert out.loc["moved.com", "source_url"] == "https://acme.com/"
    assert out.loc["down.com", "status"] == "unreachable"
    assert out.loc["pdf.com", "status"] == "not_html"
    assert out.loc["err.com", "status"] == "http_error"


def test_ssrf_guard_blocks_private_targets():
    def handler(request):
        raise AssertionError("must not be requested")

    companies = pd.DataFrame({"company_name": ["Loop"], "domain": ["127.0.0.1"]})

    async def go():
        async with _client(handler) as c:
            return await run_pipeline(companies, Settings(block_private=True), client=c)

    assert asyncio.run(go()).loc[0, "status"] == "blocked_host"


def test_export_sanitizes_formulas():
    df = pd.DataFrame({"a": ["=HYPERLINK(\"x\")", "ok", "+1"]})
    assert list(sanitize(df)["a"]) == ["'=HYPERLINK(\"x\")", "ok", "'+1"]
    assert to_csv_bytes(df).startswith(b"\xef\xbb\xbf")
    xlsx = to_excel_bytes(df, pd.DataFrame({"value": ["x"], "reason": ["invalid_domain"]}))
    sheets = pd.ExcelFile(io.BytesIO(xlsx)).sheet_names
    assert sheets == ["Companies", "Rejected"]


def test_api_health_and_bad_upload():
    from fastapi.testclient import TestClient
    from app.main import app

    c = TestClient(app)
    health = c.get("/health").json()
    assert health["status"] == "ok"
    assert "db_ok" in health
    assert "db_connected" in health

    root = c.get("/")
    assert root.status_code == 200
    assert "IntelliLead AI" in root.text

    sample = c.get("/v1/samples/companies.csv")
    assert sample.status_code == 200
    assert "text/csv" in sample.headers["content-type"]

    r = c.post("/v1/jobs", files={"file": ("x.csv", b"foo,bar\n1,2\n", "text/csv")})
    assert r.status_code == 422
    assert c.get("/v1/jobs/nope").status_code == 404
