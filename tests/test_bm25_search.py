"""Tests for BM25 fallback search in MemoryStore."""

import sys
from pathlib import Path
from typing import Any

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from bao.agent.memory import MemoryStore


# ---------------------------------------------------------------------------
# _tokenize
# ---------------------------------------------------------------------------


class TestTokenize:
    def test_basic(self):
        assert MemoryStore._tokenize("Hello World") == ["hello", "world"]

    def test_filters_short(self):
        assert MemoryStore._tokenize("I am a dev") == ["am", "dev"]

    def test_empty(self):
        assert MemoryStore._tokenize("") == []

    def test_single_char_words(self):
        assert MemoryStore._tokenize("a b c") == []

    def test_mixed_case(self):
        tokens = MemoryStore._tokenize("Git Rebase MERGE conflict")
        assert tokens == ["git", "rebase", "merge", "conflict"]

    def test_punctuation_stripped(self):
        """Punctuation at word boundaries should be stripped so 'error' matches 'error.'"""
        tokens = MemoryStore._tokenize("Found an error. Fix it!")
        assert "error" in tokens
        assert "it" in tokens
        assert "error." not in tokens

    def test_brackets_stripped(self):
        tokens = MemoryStore._tokenize("[Task] configure (server)")
        assert "task" in tokens
        assert "configure" in tokens
        assert "server" in tokens
        assert "[task]" not in tokens



# ---------------------------------------------------------------------------
# _bm25_rank
# ---------------------------------------------------------------------------


def _make_doc(content: str) -> dict[str, Any]:
    return {"content": content, "type": "experience", "key": "k", "updated_at": ""}



class TestBm25Rank:
    def test_empty_query(self):
        docs = [_make_doc("hello world")]
        assert MemoryStore._bm25_rank("", docs) == []

    def test_empty_docs(self):
        assert MemoryStore._bm25_rank("hello", []) == []

    def test_exact_match_ranks_higher(self):
        docs = [
            _make_doc("python web framework flask"),
            _make_doc("git rebase merge conflict resolution"),
            _make_doc("python flask deployment production server"),
        ]
        ranked = MemoryStore._bm25_rank("python flask", docs)
        contents = [r["content"] for _, r in ranked]
        # Both python+flask docs should rank above git doc
        assert "git rebase" not in contents[0]
        assert len(ranked) == 2  # git doc has 0 overlap

    def test_term_frequency_matters(self):
        docs = [
            _make_doc("error error error in the code"),
            _make_doc("one error found"),
        ]
        ranked = MemoryStore._bm25_rank("error", docs)
        # Doc with more 'error' occurrences should rank higher
        assert "error error error" in ranked[0][1]["content"]

    def test_no_match_returns_empty(self):
        docs = [_make_doc("alpha beta gamma")]
        assert MemoryStore._bm25_rank("xyz", docs) == []

    def test_idf_prefers_rare_terms(self):
        """A rare term should contribute more to the score than a common one."""
        docs = [
            _make_doc("the common word appears here"),
            _make_doc("the common word and rare_token here"),
            _make_doc("the common word also here"),
        ]
        ranked = MemoryStore._bm25_rank("rare_token", docs)
        assert len(ranked) == 1
        assert "rare_token" in ranked[0][1]["content"]

    def test_scores_are_positive(self):
        docs = [_make_doc("test content here")]
        ranked = MemoryStore._bm25_rank("test", docs)
        assert all(score > 0 for score, _ in ranked)

    def test_synonym_partial_overlap(self):
        """BM25 still matches on partial keyword overlap (shared tokens)."""
        docs = [
            _make_doc("[Task] git branch cleanup\n[Lessons] use rebase for linear history"),
            _make_doc("[Task] database migration\n[Lessons] always backup first"),
        ]
        # Query shares 'branch' with doc 0 but not doc 1
        ranked = MemoryStore._bm25_rank("branch strategy", docs)
        assert len(ranked) == 1
        assert "git branch" in ranked[0][1]["content"]

    def test_punctuation_matches_in_bm25(self):
        """BM25 should match 'error' against doc containing 'error.' (punctuation stripped)."""
        docs = [_make_doc("Found an error. Please fix it.")]
        ranked = MemoryStore._bm25_rank("error", docs)
        assert len(ranked) == 1