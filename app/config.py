import os
from dataclasses import dataclass


def _env(name, default, cast=str):
    raw = os.getenv(f"INTELLILEAD_{name}")
    if raw is None:
        return default
    if cast is bool:
        return raw.strip().lower() in {"1", "true", "yes"}
    return cast(raw)


@dataclass
class Settings:
    concurrency: int = 5
    timeout_s: float = 15.0
    max_bytes: int = 1_500_000
    max_rows: int = 5000
    max_upload_bytes: int = 5_000_000
    respect_robots: bool = True
    block_private: bool = True
    user_agent: str = "IntelliLeadBot/0.2 (+contact: admin@example.com)"
    robots_token: str = "IntelliLeadBot"
    max_pages_per_company: int = 15
    max_crawl_depth: int = 2
    max_total_bytes_per_company: int = 10_000_000


def get_settings() -> Settings:
    d = Settings()
    settings = Settings(
        concurrency=_env("CONCURRENCY", d.concurrency, int),
        timeout_s=_env("TIMEOUT_S", d.timeout_s, float),
        max_bytes=_env("MAX_BYTES", d.max_bytes, int),
        max_rows=_env("MAX_ROWS", d.max_rows, int),
        max_upload_bytes=_env("MAX_UPLOAD_BYTES", d.max_upload_bytes, int),
        respect_robots=_env("RESPECT_ROBOTS", d.respect_robots, bool),
        block_private=_env("BLOCK_PRIVATE", d.block_private, bool),
        user_agent=_env("USER_AGENT", d.user_agent),
        robots_token=_env("ROBOTS_TOKEN", d.robots_token),
        max_pages_per_company=_env("MAX_PAGES_PER_COMPANY", d.max_pages_per_company, int),
        max_crawl_depth=_env("MAX_CRAWL_DEPTH", d.max_crawl_depth, int),
        max_total_bytes_per_company=_env(
            "MAX_TOTAL_BYTES_PER_COMPANY", d.max_total_bytes_per_company, int
        ),
    )
    if settings.concurrency < 1 or settings.timeout_s <= 0:
        raise ValueError("Concurrency and timeout must be positive")
    if min(settings.max_bytes, settings.max_rows, settings.max_upload_bytes,
           settings.max_pages_per_company, settings.max_total_bytes_per_company) < 1:
        raise ValueError("Configured limits must be positive")
    if settings.max_crawl_depth < 0:
        raise ValueError("MAX_CRAWL_DEPTH cannot be negative")
    return settings
