"""Property-based tests (Hypothesis) for CodeForge's core invariants."""

import ast

from hypothesis import given, settings
from hypothesis import strategies as st

from codeforge.discovery.novelty_checker import jaccard
from codeforge.repository.repo_mapper import pagerank
from codeforge.utils import fs
from codeforge.validation.mutation_validator import generate_mutants

names = st.text(alphabet="abcdefgh", min_size=1, max_size=3)


@given(st.lists(names, min_size=1, max_size=8, unique=True),
       st.lists(st.tuples(names, names, st.floats(0.1, 10)), max_size=20))
def test_pagerank_is_a_distribution(nodes, raw_edges):
    edges = {(a, b): w for a, b, w in raw_edges if a in nodes and b in nodes and a != b}
    rank = pagerank(nodes, edges)
    assert set(rank) == set(nodes)
    assert all(v >= 0 for v in rank.values())
    assert abs(sum(rank.values()) - 1.0) < 1e-6


@given(st.text(max_size=40))
def test_safe_relpath_never_escapes(path):
    try:
        rel = fs.safe_relpath(path)
    except fs.UnsafePathError:
        return
    assert not rel.startswith("/") and ".." not in rel.split("/") and not rel.startswith(".git")


@given(st.sets(names), st.sets(names))
def test_jaccard_bounds_and_symmetry(a, b):
    v = jaccard(a, b)
    assert 0.0 <= v <= 1.0 and v == jaccard(b, a)


ops = st.sampled_from(["<", "<=", ">", ">=", "==", "!="])


@settings(max_examples=40)
@given(ops, st.integers(-5, 100), st.sampled_from(["+", "-", "*"]), st.integers(1, 9))
def test_mutants_always_compile_and_differ(op, threshold, arith, k):
    src = (f"def f(x):\n    if x {op} {threshold}:\n        return x {arith} {k}\n"
           f"    raise ValueError('no')\n")
    mutants = generate_mutants("m.py", src, {2, 3, 4}, max_mutants=50)
    assert mutants
    for m in mutants:
        ast.parse(m.content)
        assert m.content != src
