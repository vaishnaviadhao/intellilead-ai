import os
from dataclasses import dataclass


def _env(name: str, default, cast=str):
    raw = os.getenv(f"INTELLILEAD_{name}")
    if raw is None:
        return default
    if cast is bool:
        return raw.strip().lower() in {"1", "true", "yes"}
    return cast(raw)


@dataclass
class Settings:
    concurrency: int = 10
    timeout_s: float = 10.0
    max_bytes: int = 1_500_000
    max_rows: int = 5000
    max_upload_bytes: int = 5_000_000
    respect_robots: bool = True
    block_private: bool = True  # SSRF protection, keep True outside tests
    user_agent: str = "IntelliLeadBot/0.1 (research; respects robots.txt)"
    robots_token: str = "IntelliLeadBot"


def get_settings() -> Settings:
    d = Settings()
    return Settings(
        concurrency=_env("CONCURRENCY", d.concurrency, int),
        timeout_s=_env("TIMEOUT_S", d.timeout_s, float),
        max_bytes=_env("MAX_BYTES", d.max_bytes, int),
        max_rows=_env("MAX_ROWS", d.max_rows, int),
        max_upload_bytes=_env("MAX_UPLOAD_BYTES", d.max_upload_bytes, int),
        respect_robots=_env("RESPECT_ROBOTS", d.respect_robots, bool),
        block_private=_env("BLOCK_PRIVATE", d.block_private, bool),
        user_agent=_env("USER_AGENT", d.user_agent),
        robots_token=_env("ROBOTS_TOKEN", d.robots_token),
    )
