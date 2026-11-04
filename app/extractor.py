import re
from urllib.parse import unquote, urlparse
from bs4 import BeautifulSoup

INDUSTRY_KEYWORDS = {
    "Software and SaaS": ["software", "saas", "platform", "api", "cloud", "developer", "automation", "analytics"],
    "E-commerce and Retail": ["shop", "store", "cart", "checkout", "retail", "products", "shipping", "fashion"],
    "Financial Services": ["bank", "payments", "finance", "loan", "insurance", "invest", "fintech", "credit"],
    "Healthcare and Life Sciences": ["health", "patient", "clinical", "medical", "pharma", "hospital", "care"],
    "Education": ["learn", "course", "student", "university", "education", "training", "school"],
    "Manufacturing and Industrial": ["manufactur", "industrial", "engineering", "machinery", "equipment", "factory"],
    "Marketing and Advertising": ["marketing", "advertising", "agency", "brand", "seo", "campaign", "creative"],
    "Consulting and Professional Services": ["consulting", "advisory", "strategy", "professional services", "audit"],
    "Logistics and Transport": ["logistics", "freight", "shipping", "supply chain", "fleet", "delivery", "warehouse"],
    "Real Estate": ["real estate", "property", "properties", "homes", "realty", "mortgage", "listing"],
}

MIN_HITS = 3
EMAIL_REGEX = re.compile(r"[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+")


def _meta(soup, **attrs):
    tag = soup.find("meta", attrs=attrs)
    return (tag.get("content") or "").strip() if tag else ""


def extract_company_info(html: str | None) -> dict:
    soup = BeautifulSoup(html or "", "html.parser")

    title = soup.title.get_text(strip=True) if soup.title else ""
    description = _meta(soup, name="description") or _meta(soup, property="og:description")
    site_name = _meta(soup, property="og:site_name")
    h1 = soup.find("h1")
    h1_text = h1.get_text(" ", strip=True) if h1 else ""
    lang = (soup.html.get("lang") if soup.html else "") or ""

    linkedin = ""
    twitter = ""
    github = ""
    contact_email = ""

    for a in soup.find_all("a", href=True):
        href = a["href"].strip()
        href_lower = href.lower()

        # LinkedIn
        if not linkedin and "linkedin.com/company" in href_lower:
            linkedin = href

        # Twitter / X (ignore share intents)
        if not twitter and ("twitter.com/" in href_lower or "x.com/" in href_lower):
            if "intent/" not in href_lower and "share?" not in href_lower:
                twitter = href

        # GitHub
        if not github and "github.com/" in href_lower:
            parsed = urlparse(href)
            path_parts = [p for p in parsed.path.strip("/").split("/") if p]
            if path_parts and path_parts[0] not in ("features", "pricing", "enterprise", "join", "login", "signup"):
                github = href

        # Contact Email via mailto:
        if not contact_email and href_lower.startswith("mailto:"):
            raw_email = href[7:].split("?")[0].strip()
            raw_email = unquote(raw_email)
            if EMAIL_REGEX.match(raw_email):
                contact_email = raw_email

    for t in soup(["script", "style", "noscript"]):
        t.decompose()
    body_text = soup.get_text(" ", strip=True)[:3000]

    # Fallback email extraction from visible text if not found in mailto
    if not contact_email:
        found_emails = EMAIL_REGEX.findall(body_text)
        for em in found_emails:
            em_lower = em.lower()
            if not any(em_lower.endswith(ext) for ext in (".png", ".jpg", ".jpeg", ".gif", ".svg", ".webp")):
                contact_email = em
                break

    corpus = " ".join([title, description, h1_text, body_text]).lower()

    scores = {ind: sum(1 for kw in kws if kw in corpus) for ind, kws in INDUSTRY_KEYWORDS.items()}
    best, hits = max(scores.items(), key=lambda kv: kv[1])
    industry = best if hits >= MIN_HITS else "Unknown"

    return {
        "page_title": title[:300],
        "meta_description": description[:500],
        "site_name": site_name[:200],
        "headline": h1_text[:300],
        "language": lang[:10],
        "linkedin_url": linkedin[:300],
        "twitter_url": twitter[:300],
        "github_url": github[:300],
        "contact_email": contact_email[:200],
        "industry_hint": industry,
    }
