"""Public scraping library built on top of curl_cffi."""

# flake8: noqa: E501

from __future__ import annotations

import asyncio
import gzip
import random
import re
import ssl
from dataclasses import asdict, dataclass
from html import unescape
from html.parser import HTMLParser
from typing import Any, Optional, cast

try:
    from curl_cffi import requests as curl_requests
    from curl_cffi.requests import errors as curl_errors
except ImportError:  # pragma: no cover - exercised only without dependency installed
    curl_requests = None
    curl_errors = None

try:
    from markdownify import markdownify as html_to_markdown
except ImportError:  # pragma: no cover - exercised only without dependency installed
    html_to_markdown = None


ERROR_TYPE_TIMEOUT = "TIMEOUT"
ERROR_TYPE_CONNECTION = "CONNECTION"
ERROR_TYPE_SSL = "SSL"
ERROR_TYPE_INVALID_URL = "INVALID_URL"
ERROR_TYPE_BLOCKED = "BLOCKED"
ERROR_TYPE_HTTP_403 = "HTTP_403"
ERROR_TYPE_HTTP_429 = "HTTP_429"
ERROR_TYPE_HTTP_4XX = "HTTP_4XX"
ERROR_TYPE_HTTP_5XX = "HTTP_5XX"
ERROR_TYPE_UNKNOWN = "UNKNOWN"
NON_RETRYABLE_HTTP_STATUSES = {404, 410}

DEFAULT_CONNECT_TIMEOUT_SECONDS = 5
DEFAULT_READ_TIMEOUT_SECONDS = 15
MIN_CONTENT_LENGTH = 5000

DEFAULT_USER_AGENTS = [
    # Windows and macOS User Agents
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:125.0) Gecko/20100101 Firefox/125.0",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36 Edg/125.0.2520.81",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36 OPR/109.0.0.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_5) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 14.5; rv:125.0) Gecko/20100101 Firefox/125.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_5_1) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.5.1 Safari/605.1.15",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_5_1) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36 OPR/109.0.0.0",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux i686; rv:125.0) Gecko/20100101 Firefox/125.0",
    # Android User Agents
    "Mozilla/5.0 (Linux; Android 14; K) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Mobile Safari/537.36",
    "Mozilla/5.0 (Linux; Android 14; K) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Linux; Android 14; K) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Mobile Safari/537.36,gzip(gfe)",
    "Mozilla/5.0 (Linux; Android 14; SM-S901B) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Mobile Safari/537.36",
    "Mozilla/5.0 (Linux; Android 14; SM-S901U) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Mobile Safari/537.36",
    "Mozilla/5.0 (Linux; Android 14; SM-S908B) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Mobile Safari/537.36",
    "Mozilla/5.0 (Linux; Android 14; SM-S908U) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Mobile Safari/537.36",
    "Mozilla/5.0 (Linux; Android 14; SM-G991B) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Mobile Safari/537.36",
    "Mozilla/5.0 (Linux; Android 14; SM-G991U) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Mobile Safari/537.36",
    "Mozilla/5.0 (Linux; Android 14; SM-G998B) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Mobile Safari/537.36",
    "Mozilla/5.0 (Linux; Android 14; SM-G998U) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Mobile Safari/537.36",
    "Mozilla/5.0 (Linux; Android 14; SM-A536B) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Mobile Safari/537.36",
    "Mozilla/5.0 (Linux; Android 14; SM-A536U) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Mobile Safari/537.36",
    "Mozilla/5.0 (Linux; Android 14; SM-A515F) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Mobile Safari/537.36",
    "Mozilla/5.0 (Linux; Android 14; SM-A515U) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Mobile Safari/537.36",
    "Mozilla/5.0 (Linux; Android 14; SM-G973F) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Mobile Safari/537.36",
    "Mozilla/5.0 (Linux; Android 14; SM-G973U) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Mobile Safari/537.36",
    "Mozilla/5.0 (Linux; Android 14; Pixel 6) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Mobile Safari/537.36",
    "Mozilla/5.0 (Linux; Android 14; Pixel 6a) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Mobile Safari/537.36",
    "Mozilla/5.0 (Linux; Android 14; Pixel 6 Pro) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Mobile Safari/537.36",
    "Mozilla/5.0 (Linux; Android 14; Pixel 7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Mobile Safari/537.36",
    "Mozilla/5.0 (Linux; Android 14; Pixel 7 Pro) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Mobile Safari/537.36",
    "Mozilla/5.0 (Linux; Android 14; moto g pure) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Mobile Safari/537.36",
    "Mozilla/5.0 (Linux; Android 14; moto g stylus 5G) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Mobile Safari/537.36",
    "Mozilla/5.0 (Linux; Android 14; moto g stylus 5G (2022)) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Mobile Safari/537.36",
    "Mozilla/5.0 (Linux; Android 14; moto g 5G (2022)) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Mobile Safari/537.36",
    "Mozilla/5.0 (Linux; Android 14; moto g power (2022)) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Mobile Safari/537.36",
    "Mozilla/5.0 (Linux; Android 14; Redmi Note 9 Pro) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Mobile Safari/537.36",
    "Mozilla/5.0 (Linux; Android 14; Redmi Note 8 Pro) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Mobile Safari/537.36",
    "Mozilla/5.0 (Linux; Android 14; VOG-L29) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Mobile Safari/537.36",
    "Mozilla/5.0 (Linux; Android 14; MAR-LX1A) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Mobile Safari/537.36",
    "Mozilla/5.0 (Linux; Android 14; M2101K6G) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Mobile Safari/537.36",
    "Mozilla/5.0 (Linux; Android 14; M2102J20SG) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Mobile Safari/537.36",
    "Mozilla/5.0 (Linux; Android 14; 2201116SG) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Mobile Safari/537.36",
    "Mozilla/5.0 (Linux; Android 14; DE2118) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Mobile Safari/537.36",
    # iPhone User Agents
    "Mozilla/5.0 (iPhone16,6; U; CPU iPhone OS 17_5 like Mac OS X) AppleWebKit/602.1.50 (KHTML, like Gecko) Version/10.0 Mobile/19E241 Safari/602.1",
    "Mozilla/5.0 (iPhone16,3; U; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/602.1.50 (KHTML, like Gecko) Version/10.0 Mobile/19A346 Safari/602.1",
    "Mozilla/5.0 (iPhone15,2; U; CPU iPhone OS 16_0 like Mac OS X) AppleWebKit/602.1.50 (KHTML, like Gecko) Version/10.0 Mobile/15E148 Safari/602.1",
    "Mozilla/5.0 (iPhone14,1; U; CPU iPhone OS 15_0 like Mac OS X) AppleWebKit/602.1.50 (KHTML, like Gecko) Version/10.0 Mobile/15E148 Safari/602.1",
    "Mozilla/5.0 (iPhone14,1; U; CPU iPhone OS 15_0 like Mac OS X) AppleWebKit/602.1.50 (KHTML, like Gecko) Version/10.0 Mobile/15E148 Safari/602.1",
    "Mozilla/5.0 (iPhone; CPU iPhone OS 14_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/12.0 Mobile/15E148 Safari/604.1",
    "Mozilla/5.0 (iPhone; CPU iPhone OS 14_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) CriOS/69.0.3497.105 Mobile/15E148 Safari/605.1",
    "Mozilla/5.0 (iPhone; CPU iPhone OS 14_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) FxiOS/13.2b11866 Mobile/16A366 Safari/605.1.15",
    "Mozilla/5.0 (iPhone; CPU iPhone OS 13_0 like Mac OS X) AppleWebKit/604.1.38 (KHTML, like Gecko) Version/11.0 Mobile/15A372 Safari/604.1",
    "Mozilla/5.0 (iPhone; CPU iPhone OS 13_0 like Mac OS X) AppleWebKit/604.1.34 (KHTML, like Gecko) Version/11.0 Mobile/15A5341f Safari/604.1",
    "Mozilla/5.0 (iPhone; CPU iPhone OS 13_0 like Mac OS X) AppleWebKit/604.1.38 (KHTML, like Gecko) Version/11.0 Mobile/15A5370a Safari/604.1",
    "Mozilla/5.0 (iPhone9,3; U; CPU iPhone OS 12_0_1 like Mac OS X) AppleWebKit/602.1.50 (KHTML, like Gecko) Version/10.0 Mobile/14A403 Safari/602.1",
    "Mozilla/5.0 (iPhone9,4; U; CPU iPhone OS 12_0_1 like Mac OS X) AppleWebKit/602.1.50 (KHTML, like Gecko) Version/10.0 Mobile/14A403 Safari/602.1",
    "Mozilla/5.0 (Apple-iPhone7C2/1202.466; U; CPU like Mac OS X; en) AppleWebKit/420+ (KHTML, like Gecko) Version/3.0 Mobile/1A543 Safari/419.3",
    # Windows Phone User Agents
    "Mozilla/5.0 (Windows Phone 10.0; Android 6.0.1; Microsoft; RM-1152) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/52.0.2743.116 Mobile Safari/537.36 Edge/15.15254",
    "Mozilla/5.0 (Windows Phone 10.0; Android 4.2.1; Microsoft; RM-1127_16056) AppleWebKit/537.36(KHTML, like Gecko) Chrome/42.0.2311.135 Mobile Safari/537.36 Edge/12.10536",
    "Mozilla/5.0 (Windows Phone 10.0; Android 4.2.1; Microsoft; Lumia 950) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/46.0.2486.0 Mobile Safari/537.36 Edge/13.1058",
    # Tablet User Agents
    "Mozilla/5.0 (Linux; Android 14; SM-X906C Build/QP1A.190711.020; wv) AppleWebKit/537.36 (KHTML, like Gecko) Version/4.0 Chrome/80.0.3987.119 Mobile Safari/537.36",
    "Mozilla/5.0 (Linux; Android 13; Lenovo YT-J706X) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/96.0.4664.45 Safari/537.36",
    "Mozilla/5.0 (Linux; Android 9; Pixel C Build/NRD90M; wv) AppleWebKit/537.36 (KHTML, like Gecko) Version/4.0 Chrome/52.0.2743.98 Safari/537.36",
    "Mozilla/5.0 (Linux; Android 8.1.0; SGP771 Build/32.2.A.0.253; wv) AppleWebKit/537.36 (KHTML, like Gecko) Version/4.0 Chrome/52.0.2743.98 Safari/537.36",
    "Mozilla/5.0 (Linux; Android 8.1.0; SHIELD Tablet K1 Build/MRA58K; wv) AppleWebKit/537.36 (KHTML, like Gecko) Version/4.0 Chrome/55.0.2883.91 Safari/537.36",
    "Mozilla/5.0 (Linux; Android 9; SM-T827R4 Build/NRD90M) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/60.0.3112.116 Safari/537.36",
    "Mozilla/5.0 (Linux; Android 7.0; SAMSUNG SM-T550 Build/LRX22G) AppleWebKit/537.36 (KHTML, like Gecko) SamsungBrowser/3.3 Chrome/38.0.2125.102 Safari/537.36",
    "Mozilla/5.0 (Linux; Android 4.4.3; KFTHWI Build/KTU84M) AppleWebKit/537.36 (KHTML, like Gecko) Silk/47.1.79 like Chrome/47.0.2526.80 Safari/537.36",
    "Mozilla/5.0 (Linux; Android 7.0; LG-V410/V41020c Build/LRX22G) AppleWebKit/537.36 (KHTML, like Gecko) Version/4.0 Chrome/34.0.1847.118 Safari/537.36",
    # Desktop User Agents
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/42.0.2311.135 Safari/537.36 Edge/12.246",
    "Mozilla/5.0 (X11; CrOS x86_64 8172.45.0) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/51.0.2704.64 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_11_2) AppleWebKit/601.3.9 (KHTML, like Gecko) Version/9.0.2 Safari/601.3.9",
    "Mozilla/5.0 (Windows NT 6.1; WOW64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/47.0.2526.111 Safari/537.36",
    "Mozilla/5.0 (X11; Ubuntu; Linux x86_64; rv:15.0) Gecko/20100101 Firefox/15.0.1",
]

_CURL_TIMEOUT_TYPES = tuple(
    t
    for t in (
        getattr(curl_errors, "Timeout", None),
        getattr(curl_errors, "TimeoutError", None),
        getattr(curl_errors, "ConnectTimeout", None),
        getattr(curl_errors, "ReadTimeout", None),
        getattr(curl_errors, "RequestsTimeout", None),
    )
    if t
)
_CURL_INVALID_URL = getattr(curl_errors, "InvalidURL", None)
_CURL_SSL_ERROR = getattr(curl_errors, "SSLError", None)
_CURL_PROXY_ERROR = getattr(curl_errors, "ProxyError", None)
_CURL_CONNECTION_ERROR = getattr(curl_errors, "ConnectionError", None)
_CURL_REQUESTS_ERROR = tuple(
    t
    for t in (
        getattr(curl_errors, "RequestsError", None),
        getattr(curl_errors, "RequestError", None),
    )
    if t
)
_CURL_REQUESTS_ERROR_TYPES = _CURL_REQUESTS_ERROR or (Exception,)
_CURL_REQUESTS_AND_TIMEOUT_TYPES = _CURL_REQUESTS_ERROR_TYPES + (
    asyncio.TimeoutError,
    ssl.SSLError,
)


@dataclass(frozen=True)
class FetchResult:
    ok: bool
    url: str
    status: int | None = None
    content: str | None = None
    markdown: str | None = None
    metadata: dict[str, Any] | None = None
    error_type: str | None = None
    error: str | None = None
    via_proxy: bool = False
    proxy_url: str | None = None
    content_length: int = 0
    is_blocked: bool = False

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class BlockDetector:
    STRONG_PATTERNS = [
        re.compile(r"Attention Required!\s*\|\s*Cloudflare", re.I),
        re.compile(r"Checking your browser", re.I),
        re.compile(r"Just a moment\.\.\.", re.I),
        re.compile(r"cf-chl-", re.I),
        re.compile(r"access\.denied\.\.DDoS\.Guard", re.I),
        re.compile(r"px-captcha", re.I),
        re.compile(r"distil_r_captcha", re.I),
        re.compile(r"distilnetworks", re.I),
        re.compile(r"whoa there, pardner!", re.I),
        re.compile(r"blocked due to a network policy", re.I),
    ]
    SOFT_PATTERNS = [
        re.compile(r"cf_challenge", re.I),
        re.compile(r"cf-turnstile", re.I),
        re.compile(r"g-recaptcha", re.I),
        re.compile(r"www\.google\.com/recaptcha", re.I),
        re.compile(r"recaptcha/api\.js", re.I),
        re.compile(r"hcaptcha\.com/1/api\.js", re.I),
        re.compile(r"hcaptcha", re.I),
    ]
    JS_CHALLENGE_PATTERNS = [
        re.compile(r"window\.location\.href\s*=.*challenge", re.I),
        re.compile(r"document\.cookie\s*=.*challenge", re.I),
        re.compile(r"challenge-platform", re.I),
        re.compile(r"challenge-form", re.I),
        re.compile(r"jschal-answer", re.I),
        re.compile(r"captcha-solution", re.I),
        re.compile(r"verification-token", re.I),
    ]
    SUSPICIOUS_PATTERNS = [
        re.compile(r"<title>Access Denied", re.I),
        re.compile(r"<title>403 Forbidden", re.I),
        re.compile(r"<title>429 Too Many Requests", re.I),
        re.compile(r"<title>You don't have permission", re.I),
        re.compile(r"please verify you are human", re.I),
        re.compile(r"please complete the security check", re.I),
    ]

    @classmethod
    def is_blocked(cls, response_text: str, status_code: Optional[int] = None) -> bool:
        if not response_text:
            return status_code in (403, 429) if status_code else False

        if status_code in (403, 429):
            return True

        if status_code in (520, 521, 522, 523, 524, 525, 526, 527):
            return False

        head = response_text.lstrip()[:500].lower()
        looks_like_xml = (
            head.startswith("<?xml")
            or head.startswith("<rss")
            or head.startswith("<feed")
            or head.startswith("<rdf:rdf")
            or head.startswith("<sitemapindex")
            or head.startswith("<urlset")
        )
        if looks_like_xml:
            return False

        text_only = re.sub(r"<[^>]+>", " ", response_text)
        text_only = re.sub(r"\s+", " ", text_only).strip()
        text_len = len(text_only)
        text_ratio = text_len / max(len(response_text), 1)
        looks_like_real_content = (text_len >= 1500) or (
            (text_len >= 800) and (text_ratio >= 0.01)
        )
        looks_like_interstitial = (text_len < 600) or (text_ratio < 0.008)

        for pattern in cls.STRONG_PATTERNS:
            if pattern.search(response_text):
                return True

        for pattern in (
            cls.SOFT_PATTERNS + cls.JS_CHALLENGE_PATTERNS + cls.SUSPICIOUS_PATTERNS
        ):
            if pattern.search(response_text):
                return looks_like_interstitial and not looks_like_real_content

        return False

    @classmethod
    def get_block_reason(cls, response_text: str) -> str | None:
        if not response_text:
            return None
        for pattern in (
            cls.STRONG_PATTERNS + cls.JS_CHALLENGE_PATTERNS + cls.SUSPICIOUS_PATTERNS
        ):
            if pattern.search(response_text):
                return pattern.pattern
        return None


def _classify_status(status: int) -> str:
    if status == 403:
        return ERROR_TYPE_HTTP_403
    if status == 429:
        return ERROR_TYPE_HTTP_429
    if 400 <= status <= 499:
        return ERROR_TYPE_HTTP_4XX
    if 500 <= status <= 599:
        return ERROR_TYPE_HTTP_5XX
    return ERROR_TYPE_UNKNOWN


def _header_map(response: Any) -> dict[str, str]:
    headers = getattr(response, "headers", {}) or {}
    return {str(k).lower(): str(v) for k, v in dict(headers).items()}


def _is_gzip_payload(url: str, headers: dict[str, str], body: bytes) -> bool:
    if body.startswith(b"\x1f\x8b"):
        return True
    if "gzip" in headers.get("content-type", "").lower():
        return True
    if ".gz" in headers.get("content-disposition", "").lower():
        return True
    if url.lower().endswith(".gz"):
        return True
    return False


def _extract_response_text(response: Any, url: str) -> str:
    body = getattr(response, "content", None)
    if isinstance(body, bytearray):
        body = bytes(body)

    if isinstance(body, bytes) and body:
        headers = _header_map(response)
        if _is_gzip_payload(url, headers, body):
            try:
                return gzip.decompress(body).decode("utf-8", errors="replace")
            except OSError:
                pass

    text = getattr(response, "text", None)
    if isinstance(text, str):
        return text

    if isinstance(body, bytes):
        return body.decode("utf-8", errors="replace")

    return ""


def _looks_like_xml_document(content: str) -> bool:
    head = content.lstrip()[:500].lower()
    return (
        head.startswith("<?xml")
        or head.startswith("<rss")
        or head.startswith("<feed")
        or head.startswith("<rdf:rdf")
        or head.startswith("<sitemapindex")
        or head.startswith("<urlset")
    )


def _convert_html_to_markdown(content: str) -> str:
    if html_to_markdown is not None and not _looks_like_xml_document(content):
        return html_to_markdown(content, heading_style="ATX").strip()

    text = content
    replacements = (
        (r"<h1[^>]*>(.*?)</h1>", r"# \1\n\n"),
        (r"<h2[^>]*>(.*?)</h2>", r"## \1\n\n"),
        (r"<strong[^>]*>(.*?)</strong>", r"**\1**"),
        (r"<b[^>]*>(.*?)</b>", r"**\1**"),
        (r"<em[^>]*>(.*?)</em>", r"*\1*"),
        (r"<i[^>]*>(.*?)</i>", r"*\1*"),
        (r"<p[^>]*>(.*?)</p>", r"\1\n\n"),
        (r"<br\s*/?>", "\n"),
    )
    for pattern, replacement in replacements:
        text = re.sub(pattern, replacement, text, flags=re.I | re.S)
    text = re.sub(r"<[^>]+>", "", text)
    text = unescape(text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    text = re.sub(r"[ \t]+\n", "\n", text)
    return text.strip()


class _MetadataHTMLParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.document: dict[str, Any] = {}
        self.open_graph: dict[str, Any] = {}
        self.twitter: dict[str, Any] = {}
        self._in_title = False
        self._title_parts: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attr_map = {key.lower(): (value or "") for key, value in attrs}

        if tag == "html" and attr_map.get("lang"):
            self.document["lang"] = attr_map["lang"]

        if tag == "title":
            self._in_title = True

        if tag == "meta":
            name = attr_map.get("name", "").strip().lower()
            prop = attr_map.get("property", "").strip().lower()
            content = attr_map.get("content", "").strip()
            if not content:
                return
            if name in {
                "description",
                "author",
                "keywords",
                "published_time",
                "modified_time",
            }:
                self.document[name] = content
            elif name.startswith("twitter:"):
                self.twitter[name.removeprefix("twitter:")] = content
            elif prop.startswith("og:"):
                self.open_graph[prop.removeprefix("og:")] = content

        if tag == "link":
            rel = attr_map.get("rel", "").strip().lower()
            href = attr_map.get("href", "").strip()
            if rel == "canonical" and href:
                self.document["canonical_url"] = href

    def handle_endtag(self, tag: str) -> None:
        if tag == "title":
            self._in_title = False
            title = "".join(self._title_parts).strip()
            if title:
                self.document["title"] = unescape(title)
            self._title_parts.clear()

    def handle_data(self, data: str) -> None:
        if self._in_title:
            self._title_parts.append(data)


def _extract_metadata(
    response: Any,
    html: str,
    *,
    requested_url: str,
    final_url: str | None,
    status: int | None,
) -> dict[str, Any]:
    parser = _MetadataHTMLParser()
    try:
        parser.feed(html)
    except Exception:
        pass

    headers = _header_map(response)
    return {
        "document": parser.document,
        "open_graph": parser.open_graph,
        "twitter": parser.twitter,
        "http": {
            "status": status,
            "requested_url": requested_url,
            "final_url": final_url or requested_url,
            "content_type": headers.get("content-type"),
            "content_encoding": headers.get("content-encoding"),
            "headers": headers,
        },
    }


def _classify_exception(exc: BaseException) -> tuple[str, str]:
    if isinstance(exc, asyncio.TimeoutError) or (
        _CURL_TIMEOUT_TYPES and isinstance(exc, _CURL_TIMEOUT_TYPES)
    ):
        return ERROR_TYPE_TIMEOUT, "Request timed out"
    if _CURL_INVALID_URL and isinstance(exc, _CURL_INVALID_URL):
        return ERROR_TYPE_INVALID_URL, "Invalid URL"
    if isinstance(exc, ssl.SSLError) or (
        _CURL_SSL_ERROR and isinstance(exc, _CURL_SSL_ERROR)
    ):
        return ERROR_TYPE_SSL, "TLS/SSL error"
    if _CURL_PROXY_ERROR and isinstance(exc, _CURL_PROXY_ERROR):
        return ERROR_TYPE_CONNECTION, "Proxy connection failed"
    if _CURL_CONNECTION_ERROR and isinstance(exc, _CURL_CONNECTION_ERROR):
        return ERROR_TYPE_CONNECTION, "Connection failed"
    if _CURL_REQUESTS_ERROR and isinstance(exc, _CURL_REQUESTS_ERROR):
        return ERROR_TYPE_CONNECTION, "HTTP client error"
    return ERROR_TYPE_UNKNOWN, "Unknown error"


def generate_fingerprint() -> dict[str, Any]:
    return {
        "headers": {
            "User-Agent": random.choice(DEFAULT_USER_AGENTS),
            "Accept-Encoding": "gzip, deflate, br, zstd",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
            "Accept-Language": (
                f"{random.choice(['en', 'es', 'fr'])}-"
                f"{random.choice(['US', 'ES', 'CA'])};q=0.{random.randint(5, 9)}"
            ),
            "Sec-Ch-Ua": f'"Chromium";v="{random.randint(120, 124)}", "Not.A/Brand";v="24"',
            "Sec-Ch-Ua-Mobile": "?0",
            "Sec-Ch-Ua-Platform": random.choice(['"Windows"', '"macOS"', '"Linux"']),
            "DNT": "1",
            "Sec-Fetch-Dest": "document",
            "Sec-Fetch-Mode": "navigate",
            "Sec-Fetch-Site": "none",
            "Upgrade-Insecure-Requests": "1",
            "Cache-Control": f"max-age={random.randint(0, 3600)}",
        },
        "http2": True,
    }


class StealthRequest:
    BROWSER_IMPERSONATIONS = [
        "chrome120",
        "chrome119",
        "chrome116",
        "safari15_5",
        "safari15_3",
    ]

    def __init__(
        self,
        proxies: Optional[list[str]] = None,
        verify: bool = True,
        impersonate: Optional[str] = None,
        min_content_length: int = MIN_CONTENT_LENGTH,
        connect_timeout: int = DEFAULT_CONNECT_TIMEOUT_SECONDS,
        read_timeout: int = DEFAULT_READ_TIMEOUT_SECONDS,
    ) -> None:
        self.proxies = list(proxies or [])
        self.verify = verify
        self.impersonate = impersonate or random.choice(self.BROWSER_IMPERSONATIONS)
        self.min_content_length = min_content_length
        self.connect_timeout = connect_timeout
        self.read_timeout = read_timeout

    async def fetch(self, url: str) -> FetchResult:
        if curl_requests is None:
            return FetchResult(
                ok=False,
                url=url,
                error_type=ERROR_TYPE_CONNECTION,
                error="curl_cffi is not installed",
            )

        headers = generate_fingerprint()["headers"]
        last_result: FetchResult | None = None

        async def _attempt(proxy_url: str | None) -> FetchResult:
            proxy = None
            if proxy_url:
                proxy = (
                    f"http://{proxy_url}"
                    if not proxy_url.startswith("http")
                    else proxy_url
                )

            try:
                proxy_dict = cast(
                    Any, {"http": proxy, "https": proxy} if proxy else None
                )
                response = await asyncio.to_thread(
                    curl_requests.get,
                    url,
                    headers=headers,
                    proxies=proxy_dict,
                    timeout=(self.connect_timeout, self.read_timeout),
                    verify=self.verify,
                    allow_redirects=True,
                    impersonate=cast(Any, self.impersonate),
                )
                status = response.status_code
                text = _extract_response_text(response, url)
                final_url = cast(str | None, getattr(response, "url", None))
                content_length = len(text.encode("utf-8"))
                is_blocked = BlockDetector.is_blocked(text, status)
                metadata = _extract_metadata(
                    response,
                    text,
                    requested_url=url,
                    final_url=final_url,
                    status=status,
                )

                if is_blocked:
                    return FetchResult(
                        ok=False,
                        url=url,
                        status=status,
                        error_type=ERROR_TYPE_BLOCKED,
                        error=BlockDetector.get_block_reason(text)
                        or "Anti-bot challenge detected",
                        metadata=metadata,
                        via_proxy=proxy is not None,
                        proxy_url=proxy_url,
                        content_length=content_length,
                        is_blocked=True,
                    )

                if status == 200:
                    return FetchResult(
                        ok=True,
                        url=url,
                        status=status,
                        content=text,
                        markdown=_convert_html_to_markdown(text),
                        metadata=metadata,
                        via_proxy=proxy is not None,
                        proxy_url=proxy_url,
                        content_length=content_length,
                        is_blocked=False,
                    )

                return FetchResult(
                    ok=False,
                    url=url,
                    status=status,
                    error_type=_classify_status(status),
                    error=f"HTTP {status}",
                    metadata=metadata,
                    via_proxy=proxy is not None,
                    proxy_url=proxy_url,
                    content_length=content_length,
                    is_blocked=False,
                )
            except _CURL_REQUESTS_AND_TIMEOUT_TYPES as exc:
                error_type, message = _classify_exception(exc)
                return FetchResult(
                    ok=False,
                    url=url,
                    status=None,
                    error_type=error_type,
                    error=message,
                    via_proxy=proxy is not None,
                    proxy_url=proxy_url,
                    is_blocked=False,
                )

        if self.proxies:
            to_try = list(dict.fromkeys(self.proxies))
            random.shuffle(to_try)
            for proxy_url in to_try[: min(3, len(to_try))]:
                result = await _attempt(proxy_url)
                last_result = result
                if result.status in NON_RETRYABLE_HTTP_STATUSES:
                    return result
                if (
                    result.ok
                    and not result.is_blocked
                    and result.content_length >= self.min_content_length
                ):
                    return result
            return last_result or FetchResult(
                ok=False,
                url=url,
                error_type=ERROR_TYPE_CONNECTION,
                error="All proxy attempts failed",
                via_proxy=True,
                proxy_url=to_try[0] if to_try else None,
            )

        return await _attempt(None)


class CurlCffiScraper:
    def __init__(
        self,
        proxies: Optional[list[str]] = None,
        impersonate: Optional[str] = None,
        verify: bool = True,
        min_content_length: int = MIN_CONTENT_LENGTH,
        connect_timeout: int = DEFAULT_CONNECT_TIMEOUT_SECONDS,
        read_timeout: int = DEFAULT_READ_TIMEOUT_SECONDS,
    ) -> None:
        self.stealth_request = StealthRequest(
            proxies=proxies,
            verify=verify,
            impersonate=impersonate,
            min_content_length=min_content_length,
            connect_timeout=connect_timeout,
            read_timeout=read_timeout,
        )

    async def fetch(self, url: str) -> FetchResult:
        return await self.stealth_request.fetch(url)
