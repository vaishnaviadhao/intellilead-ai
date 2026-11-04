import ipaddress
import re
from urllib.parse import urlparse

_LABEL = re.compile(r"^(?!-)[a-z0-9-]{1,63}(?<!-)$")
_EMPTY = {"", "nan", "none", "null", "n/a", "na", "-"}


def is_valid_domain(host: str) -> bool:
    if not host or len(host) > 253 or "." not in host:
        return False
    try:
        ipaddress.ip_address(host)
        return False  # raw IPs are not company domains
    except ValueError:
        pass
    labels = host.split(".")
    if not all(_LABEL.match(label) for label in labels):
        return False
    tld = labels[-1]
    return len(tld) >= 2 and not tld.isdigit()


def normalize_domain(raw) -> str | None:
    """Turn a URL, email or bare host into a lowercase host.

    Returns None when the value cannot be a valid public domain.
    """
    if raw is None:
        return None
    s = str(raw).strip().lower()
    if s in _EMPTY:
        return None
    if "@" in s and "//" not in s:
        s = s.split("@", 1)[1]
    if "//" not in s:
        s = "//" + s
    try:
        host = urlparse(s).hostname
    except ValueError:
        return None
    if not host:
        return None
    host = host.rstrip(".")
    if host.startswith("www."):
        host = host[4:]
    try:
        host = host.encode("idna").decode("ascii")
    except UnicodeError:
        return None
    return host if is_valid_domain(host) else None
