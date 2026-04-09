"""
AI / LLM provider abstraction layer.

This package is intentionally small and dependency-light:
- OpenAI calls use HTTP via `requests` (no `openai` SDK required).
- Ollama calls use HTTP via `requests`.
"""

