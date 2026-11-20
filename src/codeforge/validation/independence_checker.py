"""Test independence checks: hidden tests should verify the specification, not mirror one
implementation. Produces an auditable list of findings (errors reject, warnings inform)."""

from __future__ import annotations

import ast
import re
from dataclasses import dataclass, field

from codeforge.schemas.task import TaskSpec, TestCaseTrace


@dataclass
class IndependenceReport:
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    ac_coverage: dict[str, list[str]] = field(default_factory=dict)
    test_functions: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.errors


def check_python_tests(
    test_source: str,
    spec: TaskSpec,
    traceability: list[TestCaseTrace],
    existing_names: set[str],
    reference_new_names: set[str],
) -> IndependenceReport:
    report = IndependenceReport()
    try:
        tree = ast.parse(test_source)
    except SyntaxError as exc:
        report.errors.append(f"test file has a syntax error: {exc}")
        return report

    contract = {c.name.split(".")[-1] for c in spec.contract}
    funcs = [n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef)
             and n.name.startswith("test")]
    report.test_functions = [f.name for f in funcs]
    if not funcs:
        report.errors.append("no test functions found")

    imported: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            for alias in node.names:
                imported.add(alias.name)
        elif isinstance(node, ast.Import):
            for alias in node.names:
                imported.add(alias.name.split(".")[0])
    private = sorted(n for n in imported if n.startswith("_") and n != "__future__")
    if private:
        report.warnings.append(f"tests import private names: {private}")
    # Names the reference introduced that the contract does not define = implementation detail.
    leaked = sorted((imported & reference_new_names) - contract)
    if leaked:
        report.errors.append(f"tests depend on implementation-only names not in the contract: "
                             f"{leaked}")
    unknown = sorted(n for n in imported - contract - existing_names
                     if n[:1].isupper() or "_" in n)
    stdlib_like = {"pytest", "Decimal", "dataclass", "field", "ROUND_HALF_UP", "ROUND_HALF_EVEN",
                   "ROUND_DOWN", "ROUND_UP", "ROUND_FLOOR", "ROUND_CEILING", "InvalidOperation",
                   "Enum", "Path", "datetime", "date", "timedelta"}
    unknown = [n for n in unknown if n not in stdlib_like]
    if unknown:
        report.warnings.append(f"tests import names that are neither in the contract nor in the "
                               f"repository: {unknown}")

    for f in funcs:
        has_assert = any(isinstance(n, ast.Assert) for n in ast.walk(f))
        uses_raises = any(isinstance(n, ast.Attribute) and n.attr == "raises"
                          for n in ast.walk(f))
        if not has_assert and not uses_raises:
            report.errors.append(f"{f.name} has no assertions")
        for deco in f.decorator_list:
            text = ast.unparse(deco)
            if "skip" in text or "xfail" in text:
                report.errors.append(f"{f.name} is skipped or xfail ({text})")
    mocks = len(re.findall(r"\b(mock|MagicMock|monkeypatch|patch)\b", test_source))
    if mocks > 3:
        report.warnings.append(f"heavy mocking ({mocks} occurrences)")

    names = set(report.test_functions)
    for ac in spec.acceptance_criteria:
        report.ac_coverage[ac.id] = sorted(t.test_name for t in traceability
                                           if ac.id in t.criteria and t.test_name in names)
    uncovered = [ac for ac, tests in report.ac_coverage.items() if not tests]
    if uncovered:
        report.errors.append(f"acceptance criteria without tests: {uncovered}")
    phantom = sorted({t.test_name for t in traceability} - names)
    if phantom:
        report.warnings.append(f"traceability lists tests that do not exist: {phantom}")
    return report
