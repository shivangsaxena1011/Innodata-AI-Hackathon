"""Diff-scoped mutation testing.

CodeForge mutates ONLY the lines the reference solution added or changed, so the mutation
score measures how well the hidden feature tests pin down the new behaviour (a whole-repo
mutation run would mostly measure the original test suite).

Operators follow the classic mutmut / mutation-testing families: comparison boundary and
negation, arithmetic, boolean connectives, constant perturbation (including Decimal("..")
string thresholds), return-value replacement, condition negation and exception removal.
Mutants are produced by splicing the mutated node back into the original source by
position, so diffs stay minimal and readable. JavaScript and other languages report
`unsupported` here and rely on LLM semantic mutants instead.
"""

from __future__ import annotations

import ast
import difflib
import hashlib
import random
from dataclasses import dataclass

COMPARE_SWAPS = {
    ast.Lt: ast.LtE, ast.LtE: ast.Lt, ast.Gt: ast.GtE, ast.GtE: ast.Gt,
    ast.Eq: ast.NotEq, ast.NotEq: ast.Eq, ast.In: ast.NotIn, ast.NotIn: ast.In,
    ast.Is: ast.IsNot, ast.IsNot: ast.Is,
}
BINOP_SWAPS = {ast.Add: ast.Sub, ast.Sub: ast.Add, ast.Mult: ast.Div, ast.Div: ast.Mult,
               ast.FloorDiv: ast.Mult, ast.Mod: ast.Mult}


@dataclass
class Mutant:
    mutant_id: str
    operator: str
    file: str
    line: int
    description: str
    content: str
    diff: str


def _segment_bounds(lines: list[str], node: ast.AST) -> tuple[int, int]:
    """Absolute character offsets for a node (ast offsets are UTF-8 byte columns)."""
    def offset(lineno: int, col: int) -> int:
        prefix = sum(len(line) for line in lines[: lineno - 1])
        line_bytes = lines[lineno - 1].encode("utf-8")
        return prefix + len(line_bytes[:col].decode("utf-8", errors="ignore"))
    return offset(node.lineno, node.col_offset), offset(node.end_lineno, node.end_col_offset)


def _enum_members(tree: ast.AST) -> dict[str, list[str]]:
    """UPPER_CASE attributes used per base name (e.g. OrderStatus -> [PAID, SHIPPED])."""
    members: dict[str, set[str]] = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.Attribute) and isinstance(node.value, ast.Name) and \
                node.attr.isupper():
            members.setdefault(node.value.id, set()).add(node.attr)
    return {k: sorted(v) for k, v in members.items() if len(v) > 1}


def _structural(tree: ast.AST, lines_of_interest: set[int]):
    """Operators for state machines and component interactions: collection element removal,
    enum/constant member swap, call-statement deletion and augmented-assignment swap."""
    members = _enum_members(tree)
    for node in ast.walk(tree):
        line = getattr(node, "lineno", None)
        if line is None or line not in lines_of_interest:
            continue
        if isinstance(node, ast.Set | ast.List | ast.Tuple) and 1 <= len(node.elts) <= 8:
            for i, elt in enumerate(node.elts):
                rest = node.elts[:i] + node.elts[i + 1:]
                if isinstance(node, ast.Set) and not rest:
                    new = "set()"
                else:
                    new = ast.unparse(type(node)(elts=rest, ctx=ast.Load()))
                    if isinstance(node, ast.Tuple):
                        new = f"({new.strip('()')}{',' if len(rest) == 1 else ''})" if rest \
                            else "()"
                yield node, "collection", f"remove element {ast.unparse(elt)}", new
        elif isinstance(node, ast.Dict) and 1 <= len(node.keys) <= 10:
            for i, key in enumerate(node.keys):
                if key is None:
                    continue
                d = ast.Dict(keys=node.keys[:i] + node.keys[i + 1:],
                             values=node.values[:i] + node.values[i + 1:])
                yield node, "collection", f"remove entry {ast.unparse(key)}", ast.unparse(d)
        elif isinstance(node, ast.Attribute) and isinstance(node.value, ast.Name) and \
                node.value.id in members and node.attr in members[node.value.id] and \
                isinstance(node.ctx, ast.Load):
            options = members[node.value.id]
            other = options[(options.index(node.attr) + 1) % len(options)]
            yield node, "enum_swap", f"{node.value.id}.{node.attr} -> {other}", \
                f"{node.value.id}.{other}"
        elif isinstance(node, ast.Expr) and isinstance(node.value, ast.Call):
            yield node, "statement", f"delete call {ast.unparse(node.value.func)}(...)", "pass"
        elif isinstance(node, ast.AugAssign) and type(node.op) in BINOP_SWAPS:
            new = BINOP_SWAPS[type(node.op)]
            yield node, "arithmetic", f"{type(node.op).__name__}= -> {new.__name__}=", \
                ast.unparse(ast.AugAssign(node.target, new(), node.value))


def _candidates(tree: ast.AST, lines_of_interest: set[int]):
    yield from _structural(tree, lines_of_interest)
    for node in ast.walk(tree):
        line = getattr(node, "lineno", None)
        if line is None or line not in lines_of_interest:
            continue
        if isinstance(node, ast.Compare):
            for i, op in enumerate(node.ops):
                new = COMPARE_SWAPS.get(type(op))
                if new:
                    mutated = ast.Compare(node.left, list(node.ops), list(node.comparators))
                    mutated.ops[i] = new()
                    yield node, "compare", f"{type(op).__name__} -> {new.__name__}", \
                        "(" + ast.unparse(mutated) + ")"
        elif isinstance(node, ast.BinOp):
            new = BINOP_SWAPS.get(type(node.op))
            if new:
                yield node, "arithmetic", f"{type(node.op).__name__} -> {new.__name__}", \
                    "(" + ast.unparse(ast.BinOp(node.left, new(), node.right)) + ")"
        elif isinstance(node, ast.BoolOp):
            new_op = ast.Or() if isinstance(node.op, ast.And) else ast.And()
            yield node, "boolean", f"{type(node.op).__name__} -> {type(new_op).__name__}", \
                "(" + ast.unparse(ast.BoolOp(new_op, node.values)) + ")"
        elif isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.Not):
            yield node, "negation", "remove not", "(" + ast.unparse(node.operand) + ")"
        elif isinstance(node, ast.Constant):
            v = node.value
            if isinstance(v, bool):
                yield node, "constant", f"{v} -> {not v}", repr(not v)
            elif isinstance(v, int | float):
                yield node, "constant", f"{v} -> {v + 1}", repr(v + 1)
            elif isinstance(v, str) and _is_number(v) and len(v) < 20:
                bumped = _bump_numeric_string(v)
                yield node, "constant", f"'{v}' -> '{bumped}'", repr(bumped)
        elif isinstance(node, ast.Return) and node.value is not None and \
                not (isinstance(node.value, ast.Constant) and node.value.value is None):
            yield node, "return", "return value -> None", "return None"
        elif isinstance(node, ast.If | ast.While):
            yield node.test, "condition", "negate condition", \
                "not (" + ast.unparse(node.test) + ")"
        elif isinstance(node, ast.Raise):
            yield node, "raise", "remove raise", "pass"


def _is_number(s: str) -> bool:
    try:
        float(s)
        return True
    except ValueError:
        return False


def _bump_numeric_string(s: str) -> str:
    if "." in s:
        whole, frac = s.split(".", 1)
        step = 10 ** -len(frac) if frac else 1
        return f"{float(s) + step:.{len(frac)}f}"
    return str(int(float(s)) + 1)


def generate_mutants(
    path: str, source: str, changed: set[int], max_mutants: int = 30, seed: int = 1337
) -> list[Mutant]:
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return []
    lines = source.splitlines(keepends=True)
    seen: set[str] = set()
    found: list[Mutant] = []
    for node, operator, desc, replacement in _candidates(tree, changed):
        try:
            start, end = _segment_bounds(lines, node)
        except (IndexError, AttributeError):
            continue
        mutated = source[:start] + replacement + source[end:]
        digest = hashlib.sha256(mutated.encode()).hexdigest()[:10]
        if digest in seen or mutated == source:
            continue
        try:
            compile(mutated, path, "exec")
        except SyntaxError:
            continue
        seen.add(digest)
        diff = "".join(difflib.unified_diff(source.splitlines(keepends=True),
                                            mutated.splitlines(keepends=True),
                                            fromfile=f"a/{path}", tofile=f"b/{path}", n=1))
        found.append(Mutant(f"m{digest}", operator, path, node.lineno, desc, mutated, diff))
    if len(found) <= max_mutants:
        return found
    # Deterministic, operator-balanced sample.
    rng = random.Random(seed)
    by_op: dict[str, list[Mutant]] = {}
    for m in found:
        by_op.setdefault(m.operator, []).append(m)
    for group in by_op.values():
        rng.shuffle(group)
    picked: list[Mutant] = []
    while len(picked) < max_mutants:
        for group in by_op.values():
            if group and len(picked) < max_mutants:
                picked.append(group.pop())
    return sorted(picked, key=lambda m: (m.file, m.line, m.mutant_id))
