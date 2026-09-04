# voice_typing/update/checker.py
"""Check GitHub Releases for a newer VoiceType build. Fail-open, no raises."""
from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass

import aiohttp

LATEST_URL = "https://api.github.com/repos/Sirawit-Thong/VoiceType/releases/latest"


@dataclass
class UpdateResult:
    available: bool
    latest_tag: str = ""
    url: str = ""
    error: str = ""


def parse_tag(tag: str) -> tuple[int, ...]:
    cleaned = (tag or "").strip()
    if cleaned.startswith(("v", "V")):
        cleaned = cleaned[1:]
    parts: list[int] = []
    for seg in cleaned.split("."):
        try:
            parts.append(int(seg))
        except ValueError:
            parts.append(0)
    return tuple(parts) or (0,)


def is_newer(local: str, remote_tag: str) -> bool:
    a = parse_tag(local)
    b = parse_tag(remote_tag)
    n = max(len(a), len(b))
    a = a + (0,) * (n - len(a))
    b = b + (0,) * (n - len(b))
    return b > a


async def _default_http_get(url: str) -> tuple[int, dict]:
    timeout = aiohttp.ClientTimeout(total=10)
    headers = {"User-Agent": "VoiceType", "Accept": "application/vnd.github+json"}
    async with aiohttp.ClientSession(timeout=timeout) as session, session.get(url, headers=headers) as resp:
        try:
            data = await resp.json()
        except Exception:
            data = {}
        return resp.status, data if isinstance(data, dict) else {}


HttpGet = Callable[[str], Awaitable[tuple[int, dict]]]


async def check_for_updates(current: str, http_get: HttpGet | None = None) -> UpdateResult:
    get = http_get or _default_http_get
    try:
        status, data = await get(LATEST_URL)
    except Exception as exc:
        return UpdateResult(available=False, error=str(exc)[:200] or "network error")
    if status != 200 or not isinstance(data, dict):
        return UpdateResult(available=False, error=f"HTTP {status}")
    tag = str(data.get("tag_name", "") or "")
    url = str(data.get("html_url", "") or "")
    if not tag:
        return UpdateResult(available=False, error="missing tag_name")
    try:
        available = is_newer(current, tag)
    except Exception:
        return UpdateResult(available=False, error="bad version")
    return UpdateResult(available=available, latest_tag=tag, url=url)
