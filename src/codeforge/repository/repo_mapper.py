"""Ranked repository map with a token budget.

The ranking algorithm is adapted from Aider's repository map (aider/repomap.py,
Apache-2.0, https://github.com/Aider-AI/aider): files are graph nodes, and an edge
A -> B is added for every identifier referenced in A and defined in B. Edges are weighted
by reference count with multipliers for meaningful names, then personalised PageRank ranks
the files and the rank flows to the definitions. This module is an independent
re-implementation on CodeForge's own data model; no Aider source code is included.
See THIRD_PARTY_NOTICES.md.
"""

from __future__ import annotations

import hashlib
import json
import logging
import math
from collections import defaultdict
from pathlib import Path

from codeforge.repository import language_detector, symbol_extractor
from codeforge.schemas.repository import FileSummary, RankedSymbol, RepositoryMap, Symbol
from codeforge.utils.fs import sha256_bytes

log = logging.getLogger(__name__)

EXTENSION_HINTS = ("registry", "policy", "rule", "handler", "plugin", "strategy", "config",
                   "validator", "router", "route", "command", "transition", "dispatch", "hook")


def pagerank(
    nodes: list[str],
    edges: dict[tuple[str, str], float],
    personalization: dict[str, float] | None = None,
    damping: float = 0.85,
    iterations: int = 100,
    tol: float = 1e-9,
) -> dict[str, float]:
    """Weighted personalised PageRank by power iteration (dangling mass follows the
    personalisation vector, matching the standard formulation)."""
    n = len(nodes)
    if n == 0:
        return {}
    pers = personalization or {v: 1.0 for v in nodes}
    total_p = sum(pers.get(v, 0.0) for v in nodes) or 1.0
    p = {v: pers.get(v, 0.0) / total_p for v in nodes}
    out_w: dict[str, float] = defaultdict(float)
    incoming: dict[str, list[tuple[str, float]]] = defaultdict(list)
    for (a, b), w in edges.items():
        out_w[a] += w
        incoming[b].append((a, w))
    rank = dict(p)
    for _ in range(iterations):
        dangling = sum(rank[v] for v in nodes if out_w[v] == 0)
        new = {}
        for v in nodes:
            flow = sum(rank[a] * w / out_w[a] for a, w in incoming[v])
            new[v] = (1 - damping) * p[v] + damping * (flow + dangling * p[v])
        delta = sum(abs(new[v] - rank[v]) for v in nodes)
        rank = new
        if delta < tol * n:
            break
    return rank


def estimate_tokens(text: str) -> int:
    return max(1, len(text) // 4)


def _edge_multiplier(ident: str, defined_in: int, mentioned: set[str]) -> float:
    mul = 1.0
    if ident in mentioned:
        mul *= 10
    is_snake = "_" in ident and any(c.isalpha() for c in ident)
    is_camel = any(c.isupper() for c in ident[1:]) and any(c.islower() for c in ident)
    if (is_snake or is_camel) and len(ident) >= 8:
        mul *= 10
    if ident.startswith("_"):
        mul *= 0.1
    if defined_in > 5:
        mul *= 0.1
    return mul


class RepoMapper:
    def __init__(self, cache_dir: Path | None = None):
        self.cache_dir = cache_dir

    def build(
        self,
        root: Path,
        files: list[str],
        commit_sha: str,
        token_budget: int = 2500,
        mentioned: set[str] | None = None,
        focus_files: set[str] | None = None,
    ) -> RepositoryMap:
        mentioned = mentioned or set()
        focus_files = focus_files or set()
        source_files = [f for f in files if language_detector.language_of(f)]
        hashes = {}
        blobs = {}
        for rel in source_files:
            data = (root / rel).read_bytes()
            blobs[rel] = data
            hashes[rel] = sha256_bytes(data)
        key_material = json.dumps([commit_sha, token_budget, sorted(mentioned),
                                   sorted(focus_files), hashes], sort_keys=True)
        cache_key = hashlib.sha256(key_material.encode()).hexdigest()[:24]
        cached = self._load(cache_key)
        if cached:
            return cached

        summaries: list[FileSummary] = []
        all_defs: list[Symbol] = []
        refs: dict[str, dict[str, int]] = {}
        imports = []
        lang_lines: dict[str, int] = defaultdict(int)
        for rel in source_files:
            lang = language_detector.language_of(rel) or "unknown"
            data = blobs[rel]
            is_test = language_detector.is_test_path(rel)
            fsyms = symbol_extractor.extract(rel, lang, data, is_test=is_test)
            n_lines = data.count(b"\n") + 1
            lang_lines[lang] += n_lines
            summaries.append(FileSummary(path=rel, language=lang, lines=n_lines,
                                         sha256=hashes[rel], is_test=is_test,
                                         syntax_errors=fsyms.syntax_errors))
            all_defs.extend(fsyms.definitions)
            refs[rel] = fsyms.references
            imports.extend(fsyms.imports)

        defines: dict[str, set[str]] = defaultdict(set)
        for d in all_defs:
            defines[d.name].add(d.file)

        edge_idents: dict[tuple[str, str], dict[str, float]] = defaultdict(dict)
        for referencer, counts in refs.items():
            for ident, n in counts.items():
                for definer in defines.get(ident, ()):
                    if definer == referencer:
                        continue
                    w = _edge_multiplier(ident, len(defines[ident]), mentioned) * math.sqrt(n)
                    edge_idents[(referencer, definer)][ident] = w
        edges = {k: sum(v.values()) for k, v in edge_idents.items()}

        personalization = None
        if focus_files:
            personalization = {f: (100.0 if f in focus_files else 1.0) for f in source_files}
        file_rank = pagerank(source_files, edges, personalization)

        # Distribute each file's rank across the definitions it points to.
        def_rank: dict[tuple[str, str], float] = defaultdict(float)
        out_total: dict[str, float] = defaultdict(float)
        for (src, _dst), w in edges.items():
            out_total[src] += w
        for (src, dst), idents in edge_idents.items():
            for ident, w in idents.items():
                def_rank[(dst, ident)] += file_rank.get(src, 0) * w / (out_total[src] or 1.0)

        ranked: list[RankedSymbol] = []
        for d in all_defs:
            base = def_rank.get((d.file, d.name), 0.0)
            score = base + file_rank.get(d.file, 0) * 0.05
            if d.is_test:
                score *= 0.2
            ranked.append(RankedSymbol(name=d.name, kind=d.kind, file=d.file, line=d.line,
                                       signature=d.signature, score=round(score, 6)))
        ranked.sort(key=lambda s: (-s.score, s.file, s.line))

        dep_edges = sorted({(a, b) for (a, b) in edge_idents})
        repo_map = RepositoryMap(
            files=summaries, symbols=all_defs, imports=imports,
            file_rank={k: round(v, 6) for k, v in sorted(file_rank.items(), key=lambda x: -x[1])},
            ranked_symbols=ranked, dependency_edges=dep_edges,
            language_distribution=dict(lang_lines), token_budget=token_budget,
            cache_key=cache_key,
        )
        repo_map.extension_points = self._extension_points(all_defs, file_rank)
        repo_map.rendered = self.render(repo_map, token_budget)
        self._save(cache_key, repo_map)
        return repo_map

    @staticmethod
    def _extension_points(defs: list[Symbol], file_rank: dict[str, float]) -> list[str]:
        points = []
        for d in defs:
            if d.is_test or d.name.startswith("_"):
                continue
            lname = d.name.lower()
            hint = any(h in lname for h in EXTENSION_HINTS)
            if d.kind == "class" or d.kind == "constant" or hint:
                points.append((file_rank.get(d.file, 0) + (0.5 if hint else 0), d))
        points.sort(key=lambda x: -x[0])
        return [f"{d.file}:{d.line} {d.kind} {d.name}" for _, d in points[:25]]

    @staticmethod
    def render(repo_map: RepositoryMap, token_budget: int) -> str:
        """Render the highest-ranked definitions grouped by file, fitting the token budget.
        Uses a binary search over the number of symbols (as Aider does)."""
        symbols = [s for s in repo_map.ranked_symbols]

        def text_for(n: int) -> str:
            chosen = symbols[:n]
            by_file: dict[str, list[RankedSymbol]] = defaultdict(list)
            for s in chosen:
                by_file[s.file].append(s)
            order = sorted(by_file, key=lambda f: -repo_map.file_rank.get(f, 0))
            out = []
            for f in order:
                out.append(f"{f}:")
                for s in sorted(by_file[f], key=lambda s: s.line):
                    indent = "    " if s.kind == "method" else "  "
                    out.append(f"{indent}{s.line:>4}| {s.signature or s.name}")
            return "\n".join(out)

        lo, hi, best = 0, len(symbols), ""
        while lo <= hi:
            mid = (lo + hi) // 2
            text = text_for(mid)
            if estimate_tokens(text) <= token_budget:
                best, lo = text, mid + 1
            else:
                hi = mid - 1
        return best

    def _load(self, key: str) -> RepositoryMap | None:
        if not self.cache_dir:
            return None
        path = self.cache_dir / "repomap" / f"{key}.json"
        if path.exists():
            try:
                return RepositoryMap.model_validate_json(path.read_text(encoding="utf-8"))
            except ValueError:
                return None
        return None

    def _save(self, key: str, repo_map: RepositoryMap) -> None:
        if not self.cache_dir:
            return
        path = self.cache_dir / "repomap" / f"{key}.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(repo_map.model_dump_json(), encoding="utf-8")
