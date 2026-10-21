# sentinel-remediate: an LLM agent proposes incident fixes; verifiers gate every fix before it runs.
# The assistant's knowledge of the codebase: module docstrings + blueprint/README sections, searchable.
# Every doc answer the assistant gives is built from (and cites) these snippets.
"""Codebase knowledge base (ASSISTANT_BLUEPRINT.md §4).

Indexes (a) the module docstring of every file under src/sentinel/ and (b) each heading-delimited
section of the configured markdown docs. Search is BM25 over word tokens (snake_case split too), with
title matches weighted up. Deterministic and dependency-free, so offline answers are reproducible.
"""

from __future__ import annotations

import ast
import math
import re
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path

_WORD = re.compile(r"[a-z0-9_]+")
_STOP = frozenset(
    "a an and are as at be by can do does for from how i in is it its of on or the this to was what "
    "when where which who why will with you your me my we our it's there their about into".split()
)
_HEADING = re.compile(r"^(#{1,3})\s+(.*)$", re.M)


def tokens(text: str) -> list[str]:
    out = []
    for word in _WORD.findall(text.lower()):
        parts = [word, *[p for p in word.split("_") if p and p != word]]
        out.extend(p for p in parts if len(p) > 1 and p not in _STOP)
    return out


@dataclass(frozen=True)
class Doc:
    source: str
    title: str
    text: str
    terms: Counter = field(compare=False, hash=False, repr=False, default_factory=Counter)


def _slug(heading: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", heading.lower()).strip("-")


def markdown_docs(path: Path, rel: str) -> list[Doc]:
    text = path.read_text(encoding="utf-8")
    marks = list(_HEADING.finditer(text))
    docs = []
    for i, m in enumerate(marks):
        end = marks[i + 1].start() if i + 1 < len(marks) else len(text)
        body = text[m.end() : end].strip()
        if body:
            docs.append(Doc(f"{rel}#{_slug(m.group(2))}", m.group(2).strip(), body))
    return docs


def module_doc(path: Path, rel: str) -> Doc | None:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    docstring = ast.get_docstring(tree)
    if not docstring:
        return None
    public = [
        n.name
        for n in tree.body
        if isinstance(n, ast.FunctionDef | ast.ClassDef | ast.AsyncFunctionDef) and not n.name.startswith("_")
    ]
    defs = f"\n\nDefines: {', '.join(public)}" if public else ""
    module = rel.removeprefix("src/").removesuffix(".py").replace("/", ".")
    return Doc(rel, module, docstring + defs)


class KnowledgeBase:
    def __init__(self, docs: list[Doc], *, k1: float = 1.2, b: float = 0.75) -> None:
        self.docs = [
            Doc(d.source, d.title, d.text, Counter(tokens(f"{d.title} {d.title} {d.text}"))) for d in docs
        ]
        self._k1, self._b = k1, b
        n = len(self.docs) or 1
        df = Counter(t for d in self.docs for t in d.terms)
        self._idf = {t: math.log(1 + (n - c + 0.5) / (c + 0.5)) for t, c in df.items()}
        self._avg = sum(sum(d.terms.values()) for d in self.docs) / n

    @classmethod
    def from_repo(cls, root: Path, doc_files: list[str]) -> KnowledgeBase:
        docs: list[Doc] = []
        for name in doc_files:
            path = root / name
            if path.exists():
                docs.extend(markdown_docs(path, name))
        for path in sorted((root / "src" / "sentinel").rglob("*.py")):
            doc = module_doc(path, path.relative_to(root).as_posix())
            if doc is not None:
                docs.append(doc)
        return cls(docs)

    def _score(self, doc: Doc, query: list[str]) -> float:
        length = sum(doc.terms.values()) or 1
        score = 0.0
        for term in query:
            tf = doc.terms.get(term, 0)
            if tf:
                norm = tf * (self._k1 + 1) / (tf + self._k1 * (1 - self._b + self._b * length / self._avg))
                score += self._idf.get(term, 0.0) * norm
        return score

    def search(self, query: str, k: int = 3) -> list[tuple[Doc, float]]:
        terms = tokens(query)
        if not terms:
            return []
        scored = [(d, self._score(d, terms)) for d in self.docs]
        scored = [(d, s) for d, s in scored if s > 0]
        return sorted(scored, key=lambda x: (-x[1], x[0].source))[:k]


def excerpt(doc: Doc, query: str, max_chars: int = 700) -> str:
    """The paragraph of `doc` that best matches `query`, trimmed."""
    wanted = set(tokens(query))
    paragraphs = [p.strip() for p in re.split(r"\n\s*\n", doc.text) if p.strip()]
    if not paragraphs:
        return ""
    best = max(paragraphs, key=lambda p: (len(wanted & set(tokens(p))), -paragraphs.index(p)))
    return best if len(best) <= max_chars else best[: max_chars - 1].rstrip() + "…"
