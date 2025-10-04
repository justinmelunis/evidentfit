"""
Get Papers Agent - LLM-free paper fetching and selection

This module provides fast, high-recall paper fetching from PubMed without any LLM calls.
It handles search, parsing, scoring, and diversity-based selection, writing results
to local JSONL for subsequent processing by the paper_processor agent.
"""

__version__ = "1.0.0"

