# History


## 0.2.0 (2026-06-04)

* Switch from `markdownify` to [`domdown`](https://github.com/juanmcristobal/domdown) for HTML-to-Markdown conversion
  - YAML frontmatter with extracted metadata (title, author, tags, etc.)
  - Article body extraction and image/table/code block preservation
* Add `--print-markdown` CLI flag for printing Markdown output
* Restructure CLI: `@click.group()` with `fetch` subcommand
* Add `markdown_length` field to `FetchResult`
* Update README examples to use `crawlsmith fetch --url ...`
* Update tests for CLI and [`domdown`](https://github.com/juanmcristobal/domdown) changes


## 0.1.0 (2026-04-07)

* First release.
