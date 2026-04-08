#!/usr/bin/env python

import asyncio
import gzip
import ssl
import warnings

from click.testing import CliRunner

import crawlsmith.crawlsmith as crawlsmith_module
from crawlsmith import cli
from crawlsmith.crawlsmith import (ERROR_TYPE_BLOCKED, ERROR_TYPE_HTTP_403,
                                   ERROR_TYPE_HTTP_429, BlockDetector,
                                   CurlCffiScraper, FetchResult,
                                   _classify_exception, _classify_status,
                                   _convert_html_to_markdown,
                                   _extract_response_text, _header_map,
                                   _is_gzip_payload, _looks_like_xml_document,
                                   generate_fingerprint)


class DummyResponse:
    def __init__(self, *, content=None, text=None, headers=None):
        self.content = content
        self.text = text
        self.headers = headers or {}


class DummyCurlError(Exception):
    pass


def test_fetch_result_to_dict_preserves_fields():
    result = FetchResult(
        ok=True,
        url="https://example.com",
        status=200,
        content="payload",
        markdown=None,
        metadata=None,
        content_length=7,
    )

    assert result.to_dict() == {
        "ok": True,
        "url": "https://example.com",
        "status": 200,
        "content": "payload",
        "markdown": None,
        "metadata": None,
        "error_type": None,
        "error": None,
        "via_proxy": False,
        "proxy_url": None,
        "content_length": 7,
        "is_blocked": False,
    }


def test_classify_status_maps_http_families():
    assert _classify_status(403) == ERROR_TYPE_HTTP_403
    assert _classify_status(429) == ERROR_TYPE_HTTP_429
    assert _classify_status(404) == crawlsmith_module.ERROR_TYPE_HTTP_4XX
    assert _classify_status(503) == crawlsmith_module.ERROR_TYPE_HTTP_5XX
    assert _classify_status(302) == crawlsmith_module.ERROR_TYPE_UNKNOWN


def test_block_detector_flags_known_interstitial():
    response_text = "<html><title>Attention Required! | Cloudflare</title></html>"

    assert BlockDetector.is_blocked(response_text, 200) is True
    assert BlockDetector.get_block_reason(response_text) is not None


def test_block_detector_does_not_flag_xml_feeds():
    response_text = (
        """<?xml version="1.0"?><rss><channel><title>Feed</title></channel></rss>"""
    )

    assert BlockDetector.is_blocked(response_text, 200) is False


def test_block_detector_handles_empty_and_soft_signals():
    assert BlockDetector.is_blocked("", 403) is True
    assert BlockDetector.is_blocked("", None) is False
    assert BlockDetector.is_blocked("<html>cf-turnstile</html>", 520) is False
    assert BlockDetector.is_blocked("<html>cf-turnstile</html>", 200) is True
    assert BlockDetector.get_block_reason("") is None


def test_extract_response_text_decompresses_gzip_payloads():
    payload = gzip.compress(b"compressed text")
    response = DummyResponse(
        content=payload,
        headers={"content-type": "application/x-gzip"},
    )

    assert (
        _extract_response_text(response, "https://example.com/feed.xml.gz")
        == "compressed text"
    )


def test_extract_response_text_handles_bytearray_plain_bytes_and_empty():
    bytearray_response = DummyResponse(content=bytearray(b"plain text"), headers={})
    bytes_response = DummyResponse(content=b"plain bytes", headers={})
    empty_response = DummyResponse(content=None, text=None, headers={})

    assert (
        _extract_response_text(bytearray_response, "https://example.com")
        == "plain text"
    )
    assert (
        _extract_response_text(bytes_response, "https://example.com") == "plain bytes"
    )
    assert _extract_response_text(empty_response, "https://example.com") == ""


def test_extract_response_text_falls_back_when_invalid_gzip():
    response = DummyResponse(
        content=b"\x1f\x8bnot-really-gzip",
        text="fallback text",
        headers={"content-type": "application/x-gzip"},
    )

    assert (
        _extract_response_text(response, "https://example.com/file.gz")
        == "fallback text"
    )


def test_convert_html_to_markdown_extracts_readable_text():
    html = (
        "<html><body><h1>Title</h1><p>Hello <strong>world</strong>.</p></body></html>"
    )

    markdown = _convert_html_to_markdown(html)

    assert "# Title" in markdown
    assert "Hello **world**." in markdown


def test_convert_html_to_markdown_skips_xml_warning_path():
    xml = """<?xml version="1.0"?><rss><channel><title>Feed Title</title></channel></rss>"""
    original = crawlsmith_module.html_to_markdown

    def should_not_be_called(*args, **kwargs):
        raise AssertionError("markdownify should not be called for XML content")

    crawlsmith_module.html_to_markdown = should_not_be_called

    try:
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            markdown = _convert_html_to_markdown(xml)
    finally:
        crawlsmith_module.html_to_markdown = original

    assert "Feed Title" in markdown
    assert caught == []


def test_helper_functions_cover_headers_gzip_xml_and_fingerprint():
    response = DummyResponse(headers={"Content-Type": "text/plain", "X-Test": 1})
    headers = _header_map(response)
    fingerprint = generate_fingerprint()

    assert headers == {"content-type": "text/plain", "x-test": "1"}
    assert (
        _is_gzip_payload(
            "https://example.com",
            {"content-disposition": "attachment; filename=data.gz"},
            b"abc",
        )
        is True
    )
    assert _looks_like_xml_document("<?xml version='1.0'?><feed></feed>") is True
    assert _looks_like_xml_document("<html></html>") is False
    assert fingerprint["http2"] is True
    assert "User-Agent" in fingerprint["headers"]


def test_extract_metadata_collects_document_social_and_http_fields():
    html = """
    <html lang="en">
      <head>
        <title>Example Title</title>
        <meta name="description" content="Example description" />
        <meta name="author" content="Alice" />
        <meta name="keywords" content="security,news" />
        <meta property="og:title" content="OG Title" />
        <meta property="og:image" content="https://example.com/og.png" />
        <meta name="twitter:card" content="summary_large_image"/>
        <meta name="twitter:title" content="Twitter Title" />
        <link rel="canonical" href="https://example.com/post" />
      </head>
      <body><h1>Title</h1></body>
    </html>
    """
    response = DummyResponse(
        headers={
            "content-type": "text/html; charset=utf-8",
            "server": "example",
        }
    )

    metadata = crawlsmith_module._extract_metadata(
        response,
        html,
        requested_url="https://example.com/source",
        final_url="https://example.com/post",
        status=200,
    )

    assert metadata["document"]["title"] == "Example Title"
    assert metadata["document"]["description"] == "Example description"
    assert metadata["document"]["author"] == "Alice"
    assert metadata["document"]["canonical_url"] == "https://example.com/post"
    assert metadata["document"]["lang"] == "en"
    assert metadata["open_graph"]["title"] == "OG Title"
    assert metadata["open_graph"]["image"] == "https://example.com/og.png"
    assert metadata["twitter"]["card"] == "summary_large_image"
    assert metadata["twitter"]["title"] == "Twitter Title"
    assert metadata["http"]["status"] == 200
    assert metadata["http"]["final_url"] == "https://example.com/post"
    assert metadata["http"]["requested_url"] == "https://example.com/source"
    assert metadata["http"]["headers"]["content-type"] == "text/html; charset=utf-8"


def test_extract_metadata_tolerates_parser_failure(monkeypatch):
    class BrokenParser:
        document = {}
        open_graph = {}
        twitter = {}

        def feed(self, html):
            raise ValueError("boom")

    monkeypatch.setattr(crawlsmith_module, "_MetadataHTMLParser", BrokenParser)

    metadata = crawlsmith_module._extract_metadata(
        DummyResponse(headers={}),
        "<html></html>",
        requested_url="https://example.com/source",
        final_url=None,
        status=200,
    )

    assert metadata["http"]["final_url"] == "https://example.com/source"


def test_cli_help_renders():
    runner = CliRunner()

    result = runner.invoke(cli.main, ["--help"])

    assert result.exit_code == 0
    assert "URL to fetch" in result.output
    assert "--markdown" not in result.output


def test_cli_without_url_prints_help():
    runner = CliRunner()

    result = runner.invoke(cli.main, [])

    assert result.exit_code == 0
    assert "Usage:" in result.output


def test_cli_prints_json_and_optional_content(monkeypatch):
    class FakeScraper:
        def __init__(self, **kwargs):
            self.kwargs = kwargs

        async def fetch(self, url):
            return FetchResult(
                ok=True,
                url=url,
                status=200,
                content="body",
                markdown="body",
                metadata={"http": {"status": 200}},
            )

    monkeypatch.setattr(cli, "CurlCffiScraper", FakeScraper)
    runner = CliRunner()

    result = runner.invoke(cli.main, ["https://example.com", "--print-content"])

    assert result.exit_code == 0
    assert '"status": 200' in result.output
    assert "body" in result.output


def test_cli_returns_non_zero_for_failed_fetch(monkeypatch):
    class FakeScraper:
        def __init__(self, **kwargs):
            self.kwargs = kwargs

        async def fetch(self, url):
            return FetchResult(ok=False, url=url, error_type="CONNECTION", error="nope")

    monkeypatch.setattr(cli, "CurlCffiScraper", FakeScraper)
    runner = CliRunner()

    result = runner.invoke(cli.main, ["https://example.com"])

    assert result.exit_code == 1


def test_library_exports_public_api():
    from crawlsmith import CurlCffiScraper

    assert CurlCffiScraper is not None


def test_error_type_blocked_constant_is_publicly_usable():
    assert ERROR_TYPE_BLOCKED == "BLOCKED"


def test_fetch_returns_markdown_by_default(monkeypatch):
    class Response:
        status_code = 200
        url = "https://example.com/final"
        headers = {"content-type": "text/html; charset=utf-8"}
        content = b"<html><body><h1>Title</h1><p>Hello <strong>world</strong>.</p></body></html>"
        text = "<html><body><h1>Title</h1><p>Hello <strong>world</strong>.</p></body></html>"

    def fake_get(*args, **kwargs):
        return Response()

    monkeypatch.setattr(
        crawlsmith_module,
        "curl_requests",
        type("Requests", (), {"get": staticmethod(fake_get)})(),
    )

    scraper = CurlCffiScraper()
    result = asyncio.run(scraper.fetch("https://example.com"))

    assert result.ok is True
    assert result.content is not None
    assert result.markdown is not None
    assert result.metadata is not None
    assert result.metadata["http"]["status"] == 200
    assert result.metadata["http"]["final_url"] == "https://example.com/final"
    assert "# Title" in result.markdown


def test_scraper_does_not_expose_fetch_markdown_alias():
    scraper = CurlCffiScraper()

    assert not hasattr(scraper, "fetch_markdown")


def test_fetch_handles_missing_dependency(monkeypatch):
    monkeypatch.setattr(crawlsmith_module, "curl_requests", None)

    scraper = CurlCffiScraper()
    result = asyncio.run(scraper.fetch("https://example.com"))

    assert result.ok is False
    assert result.error == "curl_cffi is not installed"


def test_classify_exception_branches(monkeypatch):
    timeout_error = _classify_exception(asyncio.TimeoutError())
    unknown_error = _classify_exception(RuntimeError("boom"))

    monkeypatch.setattr(crawlsmith_module, "_CURL_INVALID_URL", DummyCurlError)
    monkeypatch.setattr(crawlsmith_module, "_CURL_SSL_ERROR", DummyCurlError)
    monkeypatch.setattr(crawlsmith_module, "_CURL_PROXY_ERROR", DummyCurlError)
    monkeypatch.setattr(crawlsmith_module, "_CURL_CONNECTION_ERROR", DummyCurlError)
    monkeypatch.setattr(crawlsmith_module, "_CURL_REQUESTS_ERROR", (DummyCurlError,))

    invalid_url = _classify_exception(DummyCurlError("invalid"))
    ssl_error = _classify_exception(ssl.SSLError("ssl"))

    assert timeout_error == (crawlsmith_module.ERROR_TYPE_TIMEOUT, "Request timed out")
    assert unknown_error == (crawlsmith_module.ERROR_TYPE_UNKNOWN, "Unknown error")
    assert invalid_url == (crawlsmith_module.ERROR_TYPE_INVALID_URL, "Invalid URL")
    assert ssl_error == (crawlsmith_module.ERROR_TYPE_SSL, "TLS/SSL error")


def test_fetch_handles_blocked_http_error_and_exception_paths(monkeypatch):
    class BlockedResponse:
        status_code = 403
        url = "https://example.com/final"
        headers = {"content-type": "text/html"}
        content = b"<html><title>Access Denied</title></html>"
        text = "<html><title>Access Denied</title></html>"

    class ErrorResponse:
        status_code = 503
        url = "https://example.com/final"
        headers = {"content-type": "text/html"}
        content = b"<html><body>down</body></html>"
        text = "<html><body>down</body></html>"

    responses = [BlockedResponse(), ErrorResponse()]

    def fake_get(*args, **kwargs):
        return responses.pop(0)

    monkeypatch.setattr(
        crawlsmith_module,
        "curl_requests",
        type("Requests", (), {"get": staticmethod(fake_get)})(),
    )

    scraper = CurlCffiScraper()
    blocked = asyncio.run(scraper.fetch("https://example.com/blocked"))
    errored = asyncio.run(scraper.fetch("https://example.com/error"))

    assert blocked.error_type == crawlsmith_module.ERROR_TYPE_BLOCKED
    assert blocked.is_blocked is True
    assert errored.error_type == crawlsmith_module.ERROR_TYPE_HTTP_5XX

    monkeypatch.setattr(
        crawlsmith_module, "_CURL_REQUESTS_AND_TIMEOUT_TYPES", (DummyCurlError,)
    )

    def raising_get(*args, **kwargs):
        raise DummyCurlError("boom")

    monkeypatch.setattr(
        crawlsmith_module,
        "curl_requests",
        type("Requests", (), {"get": staticmethod(raising_get)})(),
    )
    monkeypatch.setattr(
        crawlsmith_module,
        "_classify_exception",
        lambda exc: (crawlsmith_module.ERROR_TYPE_CONNECTION, "HTTP client error"),
    )

    exception_result = asyncio.run(scraper.fetch("https://example.com/exception"))

    assert exception_result.ok is False
    assert exception_result.error == "HTTP client error"


def test_fetch_with_proxies_returns_non_retryable_result(monkeypatch):
    class Response:
        def __init__(self, status_code, text, url="https://example.com/final"):
            self.status_code = status_code
            self.text = text
            self.content = text.encode("utf-8")
            self.headers = {"content-type": "text/html; charset=utf-8"}
            self.url = url

    responses = [
        Response(200, "<html><body>short</body></html>"),
        Response(404, "<html><body>missing</body></html>"),
        Response(404, "<html><body>missing</body></html>"),
    ]

    def fake_get(*args, **kwargs):
        return responses.pop(0)

    monkeypatch.setattr(
        crawlsmith_module,
        "curl_requests",
        type("Requests", (), {"get": staticmethod(fake_get)})(),
    )
    monkeypatch.setattr(crawlsmith_module.random, "shuffle", lambda items: None)

    short_scraper = CurlCffiScraper(proxies=["p1", "p2"], min_content_length=100)
    short_result = asyncio.run(short_scraper.fetch("https://example.com/short"))

    non_retryable_scraper = CurlCffiScraper(proxies=["p1", "p2"])
    non_retryable_result = asyncio.run(
        non_retryable_scraper.fetch("https://example.com/missing")
    )

    assert short_result.status == 404
    assert short_result.proxy_url == "p2"
    assert non_retryable_result.status == 404


def test_fetch_with_proxies_returns_last_result_when_all_attempts_fail(monkeypatch):
    class Response:
        def __init__(self, status_code, text, url="https://example.com/final"):
            self.status_code = status_code
            self.text = text
            self.content = text.encode("utf-8")
            self.headers = {"content-type": "text/html; charset=utf-8"}
            self.url = url

    responses = [
        Response(500, "<html><body>server-1</body></html>"),
        Response(500, "<html><body>server-2</body></html>"),
    ]

    def fake_get(*args, **kwargs):
        return responses.pop(0)

    monkeypatch.setattr(
        crawlsmith_module,
        "curl_requests",
        type("Requests", (), {"get": staticmethod(fake_get)})(),
    )
    monkeypatch.setattr(crawlsmith_module.random, "shuffle", lambda items: None)

    scraper = CurlCffiScraper(proxies=["p1", "p2"])
    result = asyncio.run(scraper.fetch("https://example.com/server"))

    assert result.status == 500
    assert result.proxy_url == "p2"
