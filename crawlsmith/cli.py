"""Console script for crawlsmith."""

from __future__ import annotations

import asyncio
import json
import sys

import click

from crawlsmith.crawlsmith import (DEFAULT_READ_TIMEOUT_SECONDS,
                                   MIN_CONTENT_LENGTH, CurlCffiScraper)


@click.command()
@click.argument("url", required=False)
@click.option("--proxy", multiple=True, help="Proxy URL. Can be passed multiple times.")
@click.option("--impersonate", help="curl_cffi impersonation, e.g. chrome120")
@click.option(
    "--timeout",
    default=DEFAULT_READ_TIMEOUT_SECONDS,
    type=int,
    show_default=True,
    help="Read timeout in seconds",
)
@click.option(
    "--min-content-length",
    default=MIN_CONTENT_LENGTH,
    type=int,
    show_default=True,
    help="Minimum content length for proxy success",
)
@click.option("--insecure", is_flag=True, help="Disable TLS verification")
@click.option("--print-content", is_flag=True, help="Print the response body")
def main(
    url: str | None,
    proxy: tuple[str, ...],
    impersonate: str | None,
    timeout: int,
    min_content_length: int,
    insecure: bool,
    print_content: bool,
) -> int:
    """Fetch a URL using the library scraper.

    URL to fetch.
    """
    if not url:
        click.echo(click.get_current_context().get_help())
        return 0

    scraper = CurlCffiScraper(
        proxies=list(proxy),
        impersonate=impersonate,
        verify=not insecure,
        min_content_length=min_content_length,
        read_timeout=timeout,
    )
    result = asyncio.run(scraper.fetch(url))

    click.echo(json.dumps(result.to_dict(), ensure_ascii=True))
    if print_content and result.content:
        click.echo(result.content)

    raise SystemExit(0 if result.ok else 1)


if __name__ == "__main__":
    sys.exit(main())  # pragma: no cover
