"""Shared search logic for Symbolics Genera documentation.

Used by both search_server.py (FastAPI) and mcp_server.py (MCP).
"""

import json
import os
import re
import xml.etree.ElementTree as ET

_SLUG_RE = re.compile(r'[^a-z0-9]+')


def slugify(name):
    """Convert a record name to a URL-safe anchor ID."""
    s = str(name).lower()
    s = _SLUG_RE.sub('-', s).strip('-')
    return s or 'section'


def load_keyword_index(output_dir):
    """Load the keyword search index from search-index.json."""
    path = os.path.join(output_dir, 'search-index.json')
    if not os.path.exists(path):
        return None
    with open(path, 'r', encoding='utf-8') as f:
        return json.load(f)


def kw_search(keyword_index, query, limit=30, snippet_len=200):
    """Multi-term keyword matching replicating search.js scoring.

    All terms must appear somewhere in the entry (title, type, or text).
    Returns a list of result dicts sorted by relevance score.
    """
    if not keyword_index or not query:
        return []

    terms = query.lower().split()
    terms = [t for t in terms if t]
    if not terms:
        return []

    results = []
    for entry in keyword_index:
        title = (entry.get('title') or '').lower()
        text = (entry.get('text') or '').lower()
        etype = (entry.get('type') or '').lower()

        score = 0
        matched = True
        for term in terms:
            if term in title:
                score += 10
            elif term in etype:
                score += 5
            elif term in text:
                score += 1
            else:
                matched = False
                break

        if matched and score > 0:
            results.append({
                'title': entry.get('title', ''),
                'type': entry.get('type', ''),
                'path': entry.get('path', ''),
                'text': (entry.get('text') or '')[:snippet_len],
                'score': score,
                'source': 'keyword',
            })

    results.sort(key=lambda r: r['score'], reverse=True)
    return results[:limit]


def extract_records_from_xml(xml_path):
    """Parse an XML doc file and return records with full text.

    Returns list of dicts with keys: name, type, unique_id, text.
    """
    try:
        tree = ET.parse(xml_path)
    except ET.ParseError:
        return []

    records = []
    for record_el in tree.getroot().iter('record'):
        name = record_el.get('name', '')
        rec_type = record_el.get('type', '')
        unique_id = record_el.get('unique-id', '')

        texts = []
        for field_el in record_el.findall('field'):
            if field_el.get('name') == 'contents':
                for text_el in field_el.iter('text'):
                    if text_el.text:
                        texts.append(text_el.text.strip())

        records.append({
            'name': name,
            'type': rec_type,
            'unique_id': unique_id,
            'text': ' '.join(texts),
        })
    return records
