#!/usr/bin/env python3
"""FastAPI search server for Symbolics Genera documentation.

Provides semantic, keyword, and hybrid search over the generated
documentation site. Also serves the static files.

Usage:
    ./venv-search/bin/python3 search_server.py --output output --port 8000
"""

import argparse
import json
import os
import sys

import numpy as np
import uvicorn
from fastapi import FastAPI, Query
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from sentence_transformers import SentenceTransformer

from doc_search import slugify, load_keyword_index, kw_search as _kw_search


app = FastAPI(title="Genera Documentation Search")

# Global state loaded at startup
model = None
embeddings = None
chunks = None
keyword_index = None


def load_data(output_dir, model_name):
    """Load all search data and the embedding model."""
    global model, embeddings, chunks, keyword_index

    # Load semantic index
    index_dir = os.path.join(output_dir, 'semantic-index')
    emb_path = os.path.join(index_dir, 'embeddings.npz')
    chunks_path = os.path.join(index_dir, 'chunks.json')

    if os.path.exists(emb_path) and os.path.exists(chunks_path):
        print("Loading semantic index...")
        data = np.load(emb_path)
        embeddings = data['embeddings'].astype(np.float32)
        with open(chunks_path, 'r', encoding='utf-8') as f:
            chunks = json.load(f)
        print(f"  {len(chunks)} chunks, embedding dim={embeddings.shape[1]}")

        print(f"Loading model {model_name}...")
        model = SentenceTransformer(model_name)
        print("  Model loaded")
    else:
        print("Warning: No semantic index found. Semantic search disabled.")
        print(f"  Expected: {emb_path}")

    # Load keyword index
    keyword_index = load_keyword_index(output_dir)
    if keyword_index:
        print(f"  Keyword index: {len(keyword_index)} entries")
    else:
        print("Warning: No keyword index found.")


def semantic_search(query, limit=30):
    """Embed query and find nearest chunks by dot product."""
    if model is None or embeddings is None:
        return []

    query_emb = model.encode([query], normalize_embeddings=True)
    scores = embeddings @ query_emb.T
    scores = scores.flatten()

    top_indices = np.argsort(scores)[::-1][:limit * 2]

    # Deduplicate by html_path + unique_id (keep best score per record)
    seen = set()
    results = []
    for idx in top_indices:
        idx = int(idx)
        chunk = chunks[idx]
        key = (chunk['html_path'], chunk['unique_id'])
        if key in seen:
            continue
        seen.add(key)
        path = chunk['html_path']
        slug = slugify(chunk['name'])
        if slug:
            path = path + '#' + slug
        results.append({
            'title': chunk['name'],
            'type': chunk['type'],
            'path': path,
            'score': float(scores[idx]),
            'source': 'semantic',
        })
        if len(results) >= limit:
            break

    return results


def kw_search(query, limit=30):
    """Multi-term keyword matching replicating search.js scoring."""
    return _kw_search(keyword_index, query, limit=limit)


def hybrid_search(query, limit=30, k=60):
    """Reciprocal rank fusion of semantic and keyword results."""
    sem_results = semantic_search(query, limit=limit)
    kw_results = kw_search(query, limit=limit)

    # RRF: score = sum(1 / (k + rank)) across lists
    scores = {}  # path -> {score, result}

    for rank, r in enumerate(sem_results):
        path = r['path']
        rrf = 1.0 / (k + rank + 1)
        if path not in scores:
            scores[path] = {'score': 0.0, 'result': r}
            scores[path]['result']['source'] = 'semantic'
        scores[path]['score'] += rrf

    for rank, r in enumerate(kw_results):
        path = r['path']
        rrf = 1.0 / (k + rank + 1)
        if path not in scores:
            scores[path] = {'score': 0.0, 'result': r}
            scores[path]['result']['source'] = 'keyword'
        else:
            scores[path]['result']['source'] = 'both'
            # Carry over text snippet from keyword result if missing
            if r.get('text') and not scores[path]['result'].get('text'):
                scores[path]['result']['text'] = r['text']
        scores[path]['score'] += rrf

    merged = sorted(scores.values(), key=lambda x: x['score'], reverse=True)
    results = []
    for item in merged[:limit]:
        r = item['result']
        r['score'] = item['score']
        results.append(r)

    return results


@app.get('/api/search')
async def api_search(
    q: str = Query('', description='Search query'),
    mode: str = Query('hybrid', description='Search mode: semantic, keyword, or hybrid'),
    limit: int = Query(30, ge=1, le=100, description='Max results'),
):
    """Search the documentation."""
    if not q.strip():
        return JSONResponse({'results': [], 'mode': mode})

    if mode == 'semantic':
        results = semantic_search(q, limit=limit)
    elif mode == 'keyword':
        results = kw_search(q, limit=limit)
    else:
        results = hybrid_search(q, limit=limit)

    return JSONResponse({
        'results': results,
        'mode': mode,
        'query': q,
        'has_semantic': model is not None,
    })


@app.get('/api/status')
async def api_status():
    """Check server capabilities."""
    return JSONResponse({
        'ok': True,
        'has_semantic': model is not None,
        'has_keyword': keyword_index is not None,
        'chunks': len(chunks) if chunks else 0,
        'keyword_entries': len(keyword_index) if keyword_index else 0,
    })


def main():
    parser = argparse.ArgumentParser(description='Genera documentation search server')
    parser.add_argument('--output', default='output', help='Output directory to serve')
    parser.add_argument('--port', type=int, default=8000, help='Port to listen on')
    parser.add_argument('--host', default='0.0.0.0', help='Host to bind to')
    parser.add_argument('--model', default='BAAI/bge-large-en-v1.5',
                        help='Sentence transformer model name')
    args = parser.parse_args()

    if not os.path.isdir(args.output):
        print(f"Error: {args.output} is not a directory", file=sys.stderr)
        sys.exit(1)

    load_data(args.output, args.model)

    # Mount static files AFTER API routes are registered
    app.mount('/', StaticFiles(directory=args.output, html=True), name='static')

    print(f"Serving on http://{args.host}:{args.port}")
    uvicorn.run(app, host=args.host, port=args.port)


if __name__ == '__main__':
    main()
