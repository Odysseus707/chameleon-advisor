"""chi-edge-advisor: allocation-aware resource advisor for Chameleon CHI@Edge.

Pipeline: read (availability + inventory) -> retrieve (artifacts) ->
reason (LLM) -> validate (traps) -> emit (python-chi lease spec).

This package is designed to later become an MCP server plugged into the
ChameleonCloud/RAG-docs-chameleon chatbot, so it mirrors that stack where
practical (FAISS, BAAI/bge-large-en-v1.5, an OpenAI-compatible client).
"""

__version__ = "0.1.0"
