#!/usr/bin/env python3
"""MCP server providing access to Symbolics Genera documentation.

Exposes keyword search, entry lookup, and topic listing over the
generated documentation via the Model Context Protocol.

Usage:
    ./venv/bin/python3 mcp_server.py [--output OUTPUT_DIR]

Requires: pip install fastmcp lxml
"""

import argparse
import os
import sys
from typing import Annotated

from fastmcp import FastMCP

from doc_search import (
    extract_records_from_xml,
    kw_search,
    load_keyword_index,
)

# ---------------------------------------------------------------------------
# Globals loaded at startup
# ---------------------------------------------------------------------------
keyword_index: list[dict] = []
output_dir: str = "output"

# ---------------------------------------------------------------------------
# MCP Server
# ---------------------------------------------------------------------------
mcp = FastMCP(
    "Symbolics Genera Documentation",
    instructions=(
        "Provides access to Symbolics Genera (Lisp Machine) documentation "
        "converted from SAB files. Use search_docs to find entries, "
        "read_entry to get full text of a specific entry, and "
        "list_topics to browse available documentation files."
    ),
)


@mcp.tool
def search_docs(
    query: Annotated[str, "Search query (space-separated terms, all must match)"],
    limit: Annotated[int, "Maximum number of results to return"] = 20,
) -> list[dict]:
    """Search the Symbolics Genera documentation by keyword.

    Returns matching entries with title, type, path, and a text snippet.
    All search terms must appear in the title, type, or text of an entry.
    """
    results = kw_search(keyword_index, query, limit=limit, snippet_len=300)
    # Drop 'source' key — not meaningful for MCP consumers
    for r in results:
        r.pop('source', None)
    return results


@mcp.tool
def read_entry(
    name: Annotated[str, "Exact or partial name of the documentation entry to read"],
) -> list[dict]:
    """Read the full text of a documentation entry by name.

    Searches across all XML files for records matching the given name
    (case-insensitive substring match). Returns the full text content
    of matching records.
    """
    name_lower = name.lower()

    # Find candidate XML files from the keyword index
    candidate_files: set[str] = set()
    for entry in keyword_index:
        title = (entry.get("title") or "").lower()
        if name_lower in title:
            path = entry.get("path", "").split("#")[0]
            if path.endswith(".html"):
                candidate_files.add(path[:-5] + ".xml")

    if not candidate_files:
        return [{"error": f"No entries found matching '{name}'"}]

    results = []
    for rel_xml in candidate_files:
        abs_xml = os.path.join(output_dir, rel_xml)
        if not os.path.exists(abs_xml):
            continue
        for rec in extract_records_from_xml(abs_xml):
            if name_lower in rec["name"].lower():
                results.append({
                    "name": rec["name"],
                    "type": rec["type"],
                    "text": rec["text"] if rec["text"] else "(no text content)",
                    "file": rel_xml,
                })

    if not results:
        return [{"error": f"No records found matching '{name}'"}]

    # Deduplicate and limit
    seen = set()
    unique = []
    for r in results:
        key = (r["name"], r["type"])
        if key not in seen:
            seen.add(key)
            unique.append(r)
        if len(unique) >= 20:
            break

    return unique


@mcp.tool
def list_topics(
    category: Annotated[
        str,
        "Optional filter: substring to match against file paths (e.g. 'network', 'lisp', 'window')"
    ] = "",
) -> list[dict]:
    """List available documentation topics/files.

    Returns the documentation files with entry counts and the types of
    entries they contain. Optionally filter by a substring in the file path.
    """
    file_counts: dict[str, dict] = {}
    for entry in keyword_index:
        path = entry.get("path", "").split("#")[0]
        if not path:
            continue
        if category and category.lower() not in path.lower():
            continue
        if path not in file_counts:
            file_counts[path] = {"path": path, "entries": 0, "types": set()}
        file_counts[path]["entries"] += 1
        if entry.get("type"):
            file_counts[path]["types"].add(entry["type"])

    results = []
    for path in sorted(file_counts):
        info = file_counts[path]
        results.append({
            "path": info["path"],
            "entries": info["entries"],
            "types": sorted(info["types"]),
        })

    return results


@mcp.tool
def lookup_symbol(
    symbol: Annotated[str, "Symbol name to look up (e.g. 'make-instance', 'defmethod', 'tcp:open-stream')"],
    type_filter: Annotated[str, "Optional type filter (e.g. 'function', 'variable', 'macro', 'flavor')"] = "",
) -> list[dict]:
    """Look up a Lisp symbol in the documentation.

    Searches for functions, variables, macros, flavors, and other symbol
    types by name. Returns matching entries with their documentation text.
    """
    sym_lower = symbol.lower()
    bare_name = sym_lower.split(":")[-1] if ":" in sym_lower else sym_lower

    candidates = []
    for entry in keyword_index:
        title = (entry.get("title") or "").lower()
        etype = (entry.get("type") or "").lower()

        if type_filter and type_filter.lower() not in etype:
            continue

        title_bare = title.split(":")[-1] if ":" in title else title
        if bare_name == title_bare or bare_name == title:
            score = 100
        elif bare_name in title:
            score = 50
        else:
            continue

        if any(t in etype for t in ("function", "variable", "macro", "special form",
                                     "flavor", "method", "generic", "message",
                                     "init option", "condition")):
            score += 20

        candidates.append({
            "title": entry.get("title", ""),
            "type": entry.get("type", ""),
            "path": entry.get("path", ""),
            "text": (entry.get("text") or "")[:400],
            "score": score,
        })

    candidates.sort(key=lambda r: r["score"], reverse=True)
    return candidates[:20]


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main():
    global keyword_index, output_dir

    parser = argparse.ArgumentParser(description="MCP server for Genera documentation")
    parser.add_argument("--output", default="output", help="Output directory with generated docs")
    args = parser.parse_args()

    output_dir = os.path.abspath(args.output)
    if not os.path.isdir(output_dir):
        print(f"Error: {output_dir} is not a directory", file=sys.stderr)
        sys.exit(1)

    keyword_index = load_keyword_index(output_dir) or []
    print(f"Loaded {len(keyword_index)} keyword index entries", file=sys.stderr)

    mcp.run()


if __name__ == "__main__":
    main()
