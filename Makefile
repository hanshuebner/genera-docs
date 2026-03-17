SAB_DIR     ?= /opt/symbolics/lib/rel-9-0/sys.sct
OUTPUT_DIR  ?= output
PORT        ?= 8000

.PHONY: all site embeddings serve serve-static serve-mcp clean setup setup-search setup-mcp

# Full rebuild: HTML + XML + embeddings
all: site embeddings

# One-time: create converter venv
setup: venv/.done

venv/.done:
	python3 -m venv venv
	./venv/bin/pip install lxml Pillow
	@touch $@

# One-time: install MCP server dependencies into converter venv
setup-mcp: venv/.done
	./venv/bin/pip install fastmcp

# One-time: create search venv (CPU-only PyTorch, ~2.3 GB)
setup-search: venv-search/.done

venv-search/.done:
	python3 -m venv venv-search
	./venv-search/bin/pip install torch --index-url https://download.pytorch.org/whl/cpu
	./venv-search/bin/pip install sentence-transformers fastapi uvicorn[standard]
	@touch $@

# Generate HTML site + XML (needed for embeddings)
site: venv/.done
	./venv/bin/python3 convert.py site $(SAB_DIR) -o $(OUTPUT_DIR) --xml

# Build semantic search embeddings from XML (~15-25 min on M3 MacBook)
embeddings: venv-search/.done site
	./venv-search/bin/python3 build_embeddings.py $(OUTPUT_DIR)

# Serve site with semantic + keyword search
serve: venv-search/.done
	./venv-search/bin/python3 search_server.py --output $(OUTPUT_DIR) --port $(PORT)

# Serve site without search server (static files only)
serve-static:
	cd $(OUTPUT_DIR) && python3 -m http.server $(PORT)

# Run MCP server (stdio transport for Claude Code / IDE integration)
serve-mcp: venv/.done
	./venv/bin/python3 mcp_server.py --output $(OUTPUT_DIR)

clean:
	rm -rf $(OUTPUT_DIR)
