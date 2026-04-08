![Crawlsmith banner](banner.png)

# CrawlSmith

Crawlsmith is a Python scraping toolkit for fetching web pages with
`curl_cffi`, extracting readable content, detecting common anti-bot
interstitials, and returning structured metadata in a single result object.

It is designed for Python developers who want a small, pragmatic interface for:

- fetching HTML or XML content
- converting HTML to Markdown
- rotating browser impersonation profiles
- trying multiple proxies
- classifying HTTP and network failures
- extracting document, Open Graph, Twitter, and HTTP metadata

## Features

- Async-first Python API built around `CurlCffiScraper`
- Structured `FetchResult` object with success state, content, Markdown, and metadata
- Automatic browser fingerprint headers and `curl_cffi` impersonation support
- Proxy rotation with early success and retry limits
- Detection of common anti-bot challenge pages such as Cloudflare-style interstitials
- Gzip payload handling for compressed responses and feeds
- Built-in CLI for quick fetch, inspection, and debugging

## Installation

Install from PyPI:

```bash
pip install crawlsmith
```

Requirements:

- Python 3.10+

## Quick Start

```python
import asyncio

from crawlsmith import CurlCffiScraper


async def main() -> None:
    scraper = CurlCffiScraper()
    result = await scraper.fetch("https://example.com")

    if result.ok:
        print(result.status)
        print(result.content[:200])
        print(result.markdown[:200])
    else:
        print(result.error_type, result.error)


asyncio.run(main())
```

## Python Usage

### Basic Fetch

```python
import asyncio

from crawlsmith import CurlCffiScraper


async def main() -> None:
    scraper = CurlCffiScraper()
    result = await scraper.fetch("https://example.com")

    if not result.ok:
        raise RuntimeError(f"{result.error_type}: {result.error}")

    print("Status:", result.status)
    print("URL:", result.url)
    print("Content length:", result.content_length)


asyncio.run(main())
```

### Read HTML and Markdown

When a request succeeds with HTTP `200`, Crawlsmith returns both the raw response
body and a Markdown representation.

```python
import asyncio

from crawlsmith import CurlCffiScraper


async def main() -> None:
    scraper = CurlCffiScraper()
    result = await scraper.fetch("https://example.com")

    if result.ok:
        html = result.content
        markdown = result.markdown
        print(html[:300])
        print(markdown[:300])


asyncio.run(main())
```

### Access Structured Metadata

Each result includes metadata extracted from the response body and headers.

```python
import asyncio

from crawlsmith import CurlCffiScraper


async def main() -> None:
    scraper = CurlCffiScraper()
    result = await scraper.fetch("https://example.com")

    metadata = result.metadata or {}
    document = metadata.get("document", {})
    open_graph = metadata.get("open_graph", {})
    twitter = metadata.get("twitter", {})
    http = metadata.get("http", {})

    print("Title:", document.get("title"))
    print("Description:", document.get("description"))
    print("Canonical URL:", document.get("canonical_url"))
    print("OG Title:", open_graph.get("title"))
    print("Twitter Card:", twitter.get("card"))
    print("Final URL:", http.get("final_url"))


asyncio.run(main())
```

### Use Proxies

Pass a list of proxies. Crawlsmith will shuffle them, try up to three unique
entries, and return as soon as one succeeds with enough content.

```python
import asyncio

from crawlsmith import CurlCffiScraper


async def main() -> None:
    scraper = CurlCffiScraper(
        proxies=[
            "http://user:pass@proxy-1.example:8080",
            "http://user:pass@proxy-2.example:8080",
            "proxy-3.example:8080",
        ],
        min_content_length=2000,
    )

    result = await scraper.fetch("https://example.com")
    print(result.ok, result.via_proxy, result.proxy_url)


asyncio.run(main())
```

### Control Browser Impersonation

You can force a specific `curl_cffi` impersonation profile instead of using the
default randomized behavior.

```python
import asyncio

from crawlsmith import CurlCffiScraper


async def main() -> None:
    scraper = CurlCffiScraper(impersonate="chrome120")
    result = await scraper.fetch("https://example.com")
    print(result.status, result.error_type)


asyncio.run(main())
```

### Configure TLS and Timeouts

```python
import asyncio

from crawlsmith import CurlCffiScraper


async def main() -> None:
    scraper = CurlCffiScraper(
        verify=True,
        connect_timeout=5,
        read_timeout=20,
    )
    result = await scraper.fetch("https://example.com")
    print(result.to_dict())


asyncio.run(main())
```

If you need to disable TLS certificate verification for a controlled internal
environment, set `verify=False`.

### Handle Errors Explicitly

Failures are returned as structured results instead of raising request errors in
normal operation.

```python
import asyncio

from crawlsmith import CurlCffiScraper


async def main() -> None:
    scraper = CurlCffiScraper()
    result = await scraper.fetch("https://example.com")

    if result.ok:
        print("Fetched successfully")
        return

    print("Error type:", result.error_type)
    print("Error message:", result.error)
    print("HTTP status:", result.status)
    print("Blocked:", result.is_blocked)


asyncio.run(main())
```

Common error types include:

- `TIMEOUT`
- `CONNECTION`
- `SSL`
- `INVALID_URL`
- `BLOCKED`
- `HTTP_403`
- `HTTP_429`
- `HTTP_4XX`
- `HTTP_5XX`
- `UNKNOWN`

### Serialize Results

`FetchResult` can be converted directly into a plain dictionary for logging,
storage, or JSON serialization.

```python
import asyncio
import json

from crawlsmith import CurlCffiScraper


async def main() -> None:
    scraper = CurlCffiScraper()
    result = await scraper.fetch("https://example.com")
    print(json.dumps(result.to_dict(), indent=2))


asyncio.run(main())
```

## CLI Usage

The package installs a `crawlsmith` command for quick fetches from the terminal.

### Basic CLI Request

```bash
crawlsmith https://example.com
```

The CLI prints a JSON-serialized `FetchResult` to stdout.

### Print the Response Body

```bash
crawlsmith https://example.com --print-content
```

### Use One or More Proxies

```bash
crawlsmith https://example.com \
  --proxy http://user:pass@proxy-1.example:8080 \
  --proxy http://user:pass@proxy-2.example:8080 \
  --min-content-length 2000
```

### Force an Impersonation Profile

```bash
crawlsmith https://example.com --impersonate chrome120
```

### Change Timeout or Disable TLS Verification

```bash
crawlsmith https://example.com --timeout 20
```

```bash
crawlsmith https://example.com --insecure
```

### CLI Exit Codes

- `0` when the request succeeds
- `1` when the request fails

### CLI Help

```bash
crawlsmith --help
```

## Result Model

`FetchResult` exposes the following fields:

- `ok`: whether the request was considered successful
- `url`: requested URL
- `status`: HTTP status code when available
- `content`: raw response text when successful
- `markdown`: Markdown conversion of the response body when successful
- `metadata`: extracted document and HTTP metadata
- `error_type`: normalized error classification
- `error`: human-readable error summary
- `via_proxy`: whether the successful or failed attempt used a proxy
- `proxy_url`: proxy used for the final attempt, if any
- `content_length`: UTF-8 byte length of the extracted text
- `is_blocked`: whether the response looks like an anti-bot interstitial


## Support & Connect

* ⭐ **Star the repo** if you found it useful
* ☕ **Support me:** Say thanks by buying me a coffee! [https://buymeacoffee.com/juanmcristobal](https://buymeacoffee.com/juanmcristobal)
* 💼 **Open to work:** [https://www.linkedin.com/in/jmcristobal/](https://www.linkedin.com/in/jmcristobal/)
