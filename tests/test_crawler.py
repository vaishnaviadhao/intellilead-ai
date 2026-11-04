from app.crawler import _clean_url, _page_type
from app.detector import detect_technologies


def test_clean_url_keeps_same_host_and_drops_fragment_query():
    got = _clean_url("https://example.com/about", "/products?utm_source=x#top", "example.com")
    assert got == "https://example.com/products"


def test_clean_url_rejects_external_host():
    assert _clean_url("https://example.com/", "https://evil.example/path", "example.com") is None


def test_clean_url_rejects_non_http_schemes():
    assert _clean_url("https://example.com/", "mailto:test@example.com", "example.com") is None


def test_clean_url_rejects_assets():
    assert _clean_url("https://example.com/", "/assets/logo.png", "example.com") is None


def test_page_type_classification():
    assert _page_type("https://example.com/about/team") == "about"
    assert _page_type("https://example.com/pricing") == "pricing"
    assert _page_type("https://example.com/") == "homepage"


def test_page_limit_configuration_defaults():
    from app.config import Settings
    cfg = Settings()
    assert cfg.max_pages_per_company == 15
    assert cfg.max_crawl_depth == 2
    assert cfg.max_total_bytes_per_company > 0


def test_crawler_detector_uses_evidence_engine():
    html = '<html><script src="https://js.stripe.com/v3/"></script></html>'
    detections = detect_technologies(html, {})
    assert any(d.name == "Stripe" for d in detections)
