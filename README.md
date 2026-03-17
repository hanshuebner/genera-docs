# sab2html — Symbolics Genera Documentation

Converts the 851 SAB (Sage Abstract Browser) binary documentation files from Symbolics Genera into a browsable HTML site with cross-references, inline SVG graphics, and full-text search.

## Quick Start

```bash
make setup          # create venv, install lxml + Pillow
make all            # generate HTML/XML site + semantic search embeddings
make serve          # serve at http://localhost:8000 with search API
```

`make all` is the single command that does everything: it converts all SAB files to HTML and XML, then builds the semantic search index. The HTML conversion takes ~15 seconds on an i5-8350U; the embedding step takes 15–25 minutes on an M3 MacBook.

## Prerequisites

- Python 3.11+
- SAB files from a Genera 9.0 installation (default: `/opt/symbolics/lib/rel-9-0/sys.sct`)
- ~2.3 GB disk for the search venv (CPU-only PyTorch + sentence-transformers)

If your SAB files are elsewhere:

```bash
make all SAB_DIR=/path/to/sys.sct
```

## Step by Step

If you prefer running the steps individually:

```bash
# 1. Setup converter venv
make setup

# 2. Generate the HTML site (also emits XML, needed for embeddings)
make site

# 3. Setup search venv (downloads CPU-only PyTorch, ~2.3 GB)
make setup-search

# 4. Build semantic embeddings from XML (~15-25 min on M3 MacBook)
make embeddings

# 5. Serve with full search (semantic + keyword + hybrid)
make serve
```

## Serving

**With search server** (semantic + keyword search, requires embeddings):

```bash
make serve                  # default port 8000
make serve PORT=9000        # custom port
```

**Static files only** (client-side keyword search, no embeddings needed):

```bash
make serve-static
```

The site includes a fixed header bar on every page with the Symbolics logo, site title, and a search input. Typing in the header search bar shows a dropdown of results; pressing Enter goes to the full search page. When the search server is running, queries use semantic search powered by `BAAI/bge-large-en-v1.5` embeddings. Without the server, search falls back to client-side keyword matching.

## Installing as a systemd Service

To run the documentation server automatically at boot:

```bash
sudo cp genera-docs.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now genera-docs
```

Check status with `systemctl status genera-docs` and logs with `journalctl -u genera-docs`.

To change the port, edit the `ExecStart` line in `/etc/systemd/system/genera-docs.service` and run `sudo systemctl daemon-reload && sudo systemctl restart genera-docs`.

## Working with Individual Files

```bash
# Convert a single SAB file to HTML
./venv/bin/python3 convert.py single FILE.sab --format html

# Convert to XML
./venv/bin/python3 convert.py single FILE.sab --format xml

# Inspect a SAB file's internal structure
./venv/bin/python3 convert.py info FILE.sab
```

## Output

For the Genera 9.0 distribution (851 SAB files, ~52 MB):

- 851 HTML pages with a fixed header, cross-references, inline SVG, and base64 PNG images
- 851 XML intermediate files (with `--xml`)
- 17,671 search index entries
- 17,401 cross-file references resolved across 12,188 numeric indices
- Semantic search embeddings in `output/semantic-index/`

## Credits

Ported from the MIT Scheme implementation by [ecraven/sab-files](https://github.com/ecraven/sab-files).
