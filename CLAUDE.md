# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Build & Run Commands

A Makefile drives the full pipeline. All commands use project venvs.

```bash
# Full rebuild: HTML + XML + semantic search embeddings
make all

# Just regenerate the HTML/XML site (~15s on i5-8350U)
make site

# Just rebuild embeddings (~15-25 min on M3 MacBook)
make embeddings

# Serve with search API at http://localhost:8000
make serve

# Serve static files only (client-side keyword search)
make serve-static

# Run MCP server (stdio transport)
make serve-mcp
```

Individual file commands (prefix with `./venv/bin/python3` or activate venv):

```bash
python3 convert.py single FILE.sab --format html
python3 convert.py single FILE.sab --format xml
python3 convert.py info FILE.sab
```

Take headless screenshots for visual verification:

```bash
chromium --headless --no-sandbox --disable-gpu --screenshot=/tmp/page.png --window-size=1200,3000 "file:///home/hans/genera-docs/output/path/to/file.html"
```

There are no tests.

## Architecture

Converts Symbolics Genera SAB (Sage Abstract Browser) binary documentation into browsable HTML. Ported from [ecraven/sab-files](https://github.com/ecraven/sab-files) (MIT Scheme).

### Two-Pass Pipeline

**Pass 1** (`cross_references.py`): Fast index-only scan of all SAB files via `read_sab_index_only()`. Builds a global `RecordRegistry` with three lookup maps (`by_id`, `by_index`, `by_name`) so cross-file references can be resolved.

**Pass 2** (`site_generator.py`): Full parse of each SAB file, then renders HTML (and optionally XML). The registry from Pass 1 is threaded through rendering for link resolution.

### Data Flow

```
SAB binary → sab_reader.py (46 type codes, dispatch table)
           → Parsed AST (SageRecord, SageEnvr, SageCommand, SageReference, SagePicture)
           → html_renderer.py (60+ environments, 30+ commands)
           → HTML pages with cross-references, inline SVG, search index
```

### Key Modules

- **`sab_reader.py`**: Dispatch-table parser. Each of 46 SAB type codes has a registered reader function. Uses `SabStream` (from `stream.py`) for binary I/O and `SymbolTable` (from `sab_types.py`) for symbol accumulation. A fresh symbol table is created per record.
- **`genera_charset.py`**: Maps Genera's character encoding to Unicode. Bytes 0x00-0x1F are special characters (Greek, math). Byte 0x8D is paragraph/line break marker. Byte 0x89 is a tab character expanded to spaces at 8-column stops. Bytes 0x7F-0x9F (except 0x89, 0x8D) are C1 controls that get stripped.
- **`html_renderer.py`**: Core rendering. `_render_sage()` dispatches on AST type. `_render_envr()` handles 60+ environment types. `_fix_up_special_markup()` converts paragraph markers and tab-to-tab-stop commands into proper HTML structure. Records are classified as structural (section/chapter) or entry types, with entry types getting indented body formatting.
- **`cross_references.py`**: `RecordRegistry` resolves references across files. `_resolve_href()` in the renderer uses it to generate relative paths with `#fragment` anchors.
- **`binary_graphics.py`** + **`svg_renderer.py`**: Decode a binary graphics sub-format (vector drawing ops) into SVG. Text elements in SVGs can be linked to documented symbols via a `link_resolver` callback.
- **`site_generator.py`**: Orchestrates batch conversion. Generates index page with category grouping, search page, and a JSON search index.

### HTML Rendering Patterns

- Paragraph/line break markers use Unicode Private Use Area sentinels (`\ue000`, `\ue001`) throughout the pipeline
- `_fix_up_special_markup()` transforms flat content lists into nested paragraph/tab-stop structures before rendering
- `LINE_BREAK_MARKER` renders as `\n` (collapses to space in flowing HTML, preserves breaks in `<pre>`)
- Record anchors use `_slugify()` for URL-safe IDs
- Path placeholders (`{{CSS_PATH}}`, `{{INDEX_PATH}}`, `{{LOGO_PATH}}`, `{{SEARCH_JS_PATH}}`) are replaced based on output file depth

## Semantic Search

Uses a separate venv with PyTorch + sentence-transformers (~2.3GB disk, CPU-only). Setup and build are handled by the Makefile (`make setup-search`, `make embeddings`).

- **`build_embeddings.py`**: Extracts text from `output/**/*.xml`, chunks, embeds with `BAAI/bge-large-en-v1.5`, saves to `output/semantic-index/`
- **`doc_search.py`**: Shared search logic used by both `search_server.py` and `mcp_server.py`. Provides `slugify()`, `load_keyword_index()`, `kw_search()`, and `extract_records_from_xml()`.
- **`search_server.py`**: FastAPI app with `/api/search?q=...&mode=semantic|keyword|hybrid` and `/api/status`. Mounts `output/` as static files.
- **`static/search-semantic.js`**: Client-side code on the search page that probes the API; falls back to keyword-only search.js if server is unavailable.
- **`static/header-search.js`**: Global dropdown search in the fixed header bar. Probes the API, falls back to client-side keyword search from `search-index.json`.

## MCP Server

An MCP (Model Context Protocol) server exposes the documentation to LLMs via stdio transport. It uses the lightweight converter venv (no PyTorch required).

```bash
make setup-mcp   # one-time: installs fastmcp into venv
make serve-mcp   # run the server
```

- **`mcp_server.py`**: FastMCP server providing four tools:
  - **`search_docs`**: Keyword search across all entries (same scoring as `search_server.py`)
  - **`read_entry`**: Read full text of a documentation entry by name (parses XML source)
  - **`list_topics`**: Browse available documentation files with entry counts and type breakdowns
  - **`lookup_symbol`**: Look up Lisp symbols with package-prefix-aware matching and optional type filtering

### Claude Code Setup

Add to `~/.claude/settings.json` or `.claude/settings.local.json`:

```json
{
  "mcpServers": {
    "genera-docs": {
      "command": "/absolute/path/to/genera-docs/venv/bin/python3",
      "args": ["mcp_server.py", "--output", "output"],
      "cwd": "/absolute/path/to/genera-docs"
    }
  }
}
```

## SAB Source Location

The Genera 9.0 SAB files are at `/opt/symbolics/lib/rel-9-0/sys.sct`. The build produces 851 HTML files in ~15 seconds on an i5-8350U.
