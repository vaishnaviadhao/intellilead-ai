"""Rule based technology detection from publicly visible homepage signals.

Signals: script/link/img/iframe URLs, inline HTML markers, meta generator, response headers.
Each detection carries its evidence and a heuristic confidence, so results stay explainable.
"""
import re
from dataclasses import dataclass, asdict

from bs4 import BeautifulSoup

CMS = "CMS"
ECOM = "E-commerce"
ANALYTICS = "Analytics"
MARKETING = "Marketing Automation"
SUPPORT = "Support and Chat"
FRONTEND = "Frontend Framework"
CLOUD = "Cloud, CDN and Hosting"
SERVER = "Web Server"
PAYMENTS = "Payments"
SECURITY = "Security and Consent"
SCHEDULING = "Scheduling"


def _sig(name, category, res=(), html=(), header=None, generator=()):
    return {
        "name": name,
        "category": category,
        "res": tuple(res),
        "html": tuple(html),
        "header": header or {},
        "generator": tuple(generator),
    }


SIGNATURES = [
    # Analytics and tracking
    _sig("Google Analytics", ANALYTICS, res=["google-analytics.com", "googletagmanager.com/gtag"]),
    _sig("Google Tag Manager", ANALYTICS, res=["googletagmanager.com/gtm.js"]),
    _sig("Meta Pixel", ANALYTICS, res=["connect.facebook.net"], html=["fbq("]),
    _sig("Segment", ANALYTICS, res=["cdn.segment.com"]),
    _sig("Hotjar", ANALYTICS, res=["static.hotjar.com"]),
    _sig("Mixpanel", ANALYTICS, res=["cdn.mxpnl.com", "mixpanel.com/libs"]),
    _sig("Amplitude", ANALYTICS, res=["cdn.amplitude.com"]),
    # Marketing automation and CRM
    _sig("HubSpot", MARKETING, res=["js.hs-scripts.com", "js.hs-analytics.net", "js.hsforms.net"]),
    _sig("Marketo", MARKETING, res=["munchkin.marketo.net"]),
    _sig("Pardot", MARKETING, res=["pi.pardot.com"]),
    _sig("Mailchimp", MARKETING, res=["chimpstatic.com"]),
    # Support and chat
    _sig("Intercom", SUPPORT, res=["widget.intercom.io"]),
    _sig("Drift", SUPPORT, res=["js.driftt.com"]),
    _sig("Zendesk", SUPPORT, res=["static.zdassets.com"]),
    _sig("Freshchat", SUPPORT, res=["wchat.freshchat.com"]),
    # CMS and site builders
    _sig("WordPress", CMS, html=["/wp-content/", "/wp-includes/"], generator=["wordpress"]),
    _sig("Drupal", CMS, generator=["drupal"], header={"x-generator": "drupal"}),
    _sig("Wix", CMS, res=["static.parastorage.com"], generator=["wix.com"]),
    _sig("Squarespace", CMS, res=["static1.squarespace.com"], generator=["squarespace"]),
    _sig("Webflow", CMS, html=["data-wf-site"], generator=["webflow"]),
    # E-commerce
    _sig("Shopify", ECOM, res=["cdn.shopify.com"], header={"x-shopify-stage": "."}),
    _sig("WooCommerce", ECOM, html=["woocommerce"]),
    _sig("Magento", ECOM, html=["/static/frontend/magento", "mage-cache-storage"]),
    # Payments
    _sig("Stripe", PAYMENTS, res=["js.stripe.com"]),
    _sig("PayPal", PAYMENTS, res=["paypal.com/sdk", "paypalobjects.com"]),
    _sig("Razorpay", PAYMENTS, res=["checkout.razorpay.com"]),
    # Frontend
    _sig("Next.js", FRONTEND, res=["/_next/static"], html=["__next_data__"], header={"x-powered-by": "next\\.js"}),
    _sig("Nuxt", FRONTEND, res=["/_nuxt/"], html=["__nuxt"]),
    _sig("React", FRONTEND, html=["data-reactroot"]),
    _sig("Angular", FRONTEND, html=["ng-version"]),
    _sig("Vue.js", FRONTEND, res=["vue.min.js", "vue.global", "/vue.js"]),
    _sig("jQuery", FRONTEND, res=["jquery"]),
    _sig("Bootstrap", FRONTEND, res=["bootstrap.min", "bootstrap.bundle"]),
    # Cloud, CDN, hosting
    _sig("Cloudflare", CLOUD, header={"server": "cloudflare", "cf-ray": "."}),
    _sig("Amazon CloudFront", CLOUD, header={"x-amz-cf-id": ".", "via": "cloudfront"}),
    _sig("AWS S3", CLOUD, header={"server": "amazons3"}),
    _sig("Akamai", CLOUD, header={"server": "akamaighost", "x-akamai-transformed": "."}),
    _sig("Fastly", CLOUD, header={"x-fastly-request-id": ".", "x-served-by": "cache-"}),
    _sig("Vercel", CLOUD, header={"server": "vercel", "x-vercel-id": "."}),
    _sig("Netlify", CLOUD, header={"server": "netlify", "x-nf-request-id": "."}),
    _sig("Azure", CLOUD, header={"x-azure-ref": ".", "x-ms-request-id": "."}),
    _sig("Google Cloud", CLOUD, header={"via": "google", "x-goog-generation": "."}),
    # Web servers
    _sig("Nginx", SERVER, header={"server": "nginx"}),
    _sig("Apache", SERVER, header={"server": "apache"}),
    _sig("Microsoft IIS", SERVER, header={"server": "microsoft-iis"}),
    # Security and consent
    _sig("reCAPTCHA", SECURITY, res=["google.com/recaptcha"]),
    _sig("OneTrust", SECURITY, res=["cdn.cookielaw.org"]),
    _sig("Cookiebot", SECURITY, res=["consent.cookiebot.com"]),
    # Scheduling
    _sig("Calendly", SCHEDULING, res=["assets.calendly.com"]),
]

_WEIGHT = {"header": 0.90, "resource": 0.90, "generator": 0.95, "html": 0.70}


@dataclass
class Detection:
    name: str
    category: str
    confidence: float
    evidence: list

    def as_dict(self):
        return asdict(self)


def detect_technologies(html: str | None, headers: dict | None = None) -> list[Detection]:
    headers = {str(k).lower(): str(v).lower() for k, v in (headers or {}).items()}
    html = html or ""
    soup = BeautifulSoup(html, "html.parser")

    urls = []
    for tag in soup.find_all(["script", "link", "img", "iframe"]):
        val = tag.get("src") or tag.get("href")
        if val:
            urls.append(str(val).lower())
    resources = " ".join(urls)

    generator = " ".join(
        str(m.get("content", ""))
        for m in soup.find_all("meta", attrs={"name": re.compile(r"^generator$", re.I)})
    ).lower()
    html_l = html.lower()

    found = []
    for sig in SIGNATURES:
        ev = []  # (kind, label)
        for p in sig["res"]:
            if p in resources:
                ev.append(("resource", p))
        for p in sig["html"]:
            if p in html_l:
                ev.append(("html", p))
        for p in sig["generator"]:
            if p in generator:
                ev.append(("generator", p))
        for h, pat in sig["header"].items():
            val = headers.get(h)
            if val is not None and re.search(pat, val):
                ev.append(("header", h))
        if not ev:
            continue
        base = max(_WEIGHT[k] for k, _ in ev)
        conf = round(min(0.99, base + 0.03 * (len(ev) - 1)), 2)
        found.append(Detection(sig["name"], sig["category"], conf, [f"{k}:{lbl}" for k, lbl in ev]))

    found.sort(key=lambda d: (d.category, d.name))
    return found
