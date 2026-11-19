"""Extract definitions, signatures, imports and references from source files with tree-sitter."""

from __future__ import annotations

from dataclasses import dataclass, field

import tree_sitter as ts

from codeforge.repository import parser
from codeforge.schemas.repository import ImportRef, Symbol

_DEF_NODES = {
    "python": {"function_definition": "function", "class_definition": "class"},
    "javascript": {
        "function_declaration": "function", "class_declaration": "class",
        "method_definition": "method", "generator_function_declaration": "function",
    },
}
_IMPORT_NODES = {
    "python": ("import_statement", "import_from_statement"),
    "javascript": ("import_statement",),
}
_IDENT_NODES = {"identifier", "property_identifier", "type_identifier"}


@dataclass
class FileSymbols:
    definitions: list[Symbol] = field(default_factory=list)
    references: dict[str, int] = field(default_factory=dict)   # identifier -> count
    imports: list[ImportRef] = field(default_factory=list)
    syntax_errors: int = 0


def _text(node: ts.Node | None) -> str:
    return node.text.decode("utf-8", errors="replace") if node is not None and node.text else ""


def _signature(node: ts.Node, lang: str) -> str:
    """First line of a definition up to its body, e.g. `def total(self, x: int) -> int`."""
    body = node.child_by_field_name("body")
    end = body.start_byte if body is not None else node.end_byte
    src = node.text[: end - node.start_byte] if node.text else b""
    sig = " ".join(src.decode("utf-8", errors="replace").split())
    return sig.rstrip(":{ ").strip()[:200]


def _count_errors(node: ts.Node) -> int:
    if not node.has_error:
        return 0
    count = 1 if node.type == "ERROR" or node.is_missing else 0
    return count + sum(_count_errors(c) for c in node.children)


def extract(rel_path: str, lang: str, source: bytes, is_test: bool = False) -> FileSymbols:
    result = FileSymbols()
    tree = parser.parse(lang, source)
    if tree is None:
        return result
    root = tree.root_node
    result.syntax_errors = _count_errors(root)
    def_types = _DEF_NODES.get(lang, {})
    import_types = _IMPORT_NODES.get(lang, ())

    def walk(node: ts.Node, parent: str | None) -> None:
        kind = def_types.get(node.type)
        if kind:
            name = _text(node.child_by_field_name("name"))
            if name:
                if kind == "function" and parent and lang == "python":
                    kind = "method"
                result.definitions.append(Symbol(
                    name=name, kind=kind, file=rel_path, line=node.start_point[0] + 1,
                    signature=_signature(node, lang), parent=parent, is_test=is_test,
                ))
                child_parent = name if kind == "class" else parent
                for child in node.children:
                    walk(child, child_parent)
                return
        if node.type in import_types:
            module = _text(node.child_by_field_name("module_name") or
                           node.child_by_field_name("source") or node)
            result.imports.append(ImportRef(file=rel_path, module=module.strip("'\"")[:200],
                                            line=node.start_point[0] + 1))
        elif node.type in _IDENT_NODES:
            name = _text(node)
            result.references[name] = result.references.get(name, 0) + 1
        for child in node.children:
            walk(child, parent)

    walk(root, None)

    # Top-level assignments of UPPER_CASE constants are useful extension points.
    if lang == "python":
        for child in root.children:
            if child.type == "expression_statement" and child.children:
                assign = child.children[0]
                if assign.type == "assignment":
                    left = assign.child_by_field_name("left")
                    name = _text(left)
                    if left is not None and left.type == "identifier" and name.isupper():
                        result.definitions.append(Symbol(
                            name=name, kind="constant", file=rel_path,
                            line=child.start_point[0] + 1, signature=_text(child)[:120],
                            is_test=is_test,
                        ))
    # Prefer the vendored tags query for references: it keeps only real reference sites
    # (calls, attribute access, class bases) instead of every identifier.
    query = parser.get_tags_query(lang)
    if query is not None:
        tag_refs: dict[str, int] = {}
        for cap, nodes in parser.run_query(query, root).items():
            if cap.startswith("name.reference."):
                for node in nodes:
                    name = _text(node)
                    tag_refs[name] = tag_refs.get(name, 0) + 1
        # Keep identifier references for names the query misses (e.g. plain name loads),
        # but weight tagged references more strongly.
        for name, n in tag_refs.items():
            result.references[name] = result.references.get(name, 0) + 2 * n
    # Definitions are not references to themselves.
    for sym in result.definitions:
        if result.references.get(sym.name):
            result.references[sym.name] -= 1
            if not result.references[sym.name]:
                del result.references[sym.name]
    return result
