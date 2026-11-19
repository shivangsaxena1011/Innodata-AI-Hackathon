"""JUnit XML parsing. Nearly every test framework can emit JUnit XML, which gives CodeForge a
single language-agnostic way to obtain per-test results (FAIL_TO_PASS / PASS_TO_PASS)."""

from __future__ import annotations

import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class JUnitResult:
    passed: list[str] = field(default_factory=list)
    failed: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    skipped: list[str] = field(default_factory=list)
    parse_error: str | None = None


def test_id(classname: str, name: str, file: str | None = None) -> str:
    if file:
        return f"{file}::{name}" if not classname or classname.endswith(file) else \
            f"{file}::{classname.rsplit('.', 1)[-1]}::{name}" if "." in classname and \
            classname.rsplit(".", 1)[-1][:1].isupper() else f"{file}::{name}"
    return f"{classname}::{name}" if classname else name


def parse_junit(path: Path) -> JUnitResult:
    result = JUnitResult()
    if not path.exists() or path.stat().st_size == 0:
        result.parse_error = "missing junit report"
        return result
    try:
        root = ET.parse(path).getroot()
    except ET.ParseError as exc:
        result.parse_error = f"invalid junit xml: {exc}"
        return result
    for case in root.iter("testcase"):
        tid = test_id(case.get("classname", ""), case.get("name", ""), case.get("file"))
        if case.find("skipped") is not None:
            result.skipped.append(tid)
        elif case.find("error") is not None:
            result.errors.append(tid)
        elif case.find("failure") is not None:
            result.failed.append(tid)
        else:
            result.passed.append(tid)
    return result
