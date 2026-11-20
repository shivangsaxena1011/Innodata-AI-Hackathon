import pytest

from codeforge.repository import git_manager, parser
from codeforge.repository.repo_mapper import RepoMapper, estimate_tokens, pagerank
from codeforge.repository.symbol_extractor import extract
from codeforge.schemas.repository import DirtyPolicy

SAMPLE_SHA = "e4eee2fdf7755a6ffef7253e9b11621f85fd92f2"


def test_sample_commit_is_deterministic(sample_checkout):
    assert sample_checkout.sha == SAMPLE_SHA
    assert not (sample_checkout.snapshot_dir / ".git").exists()


def test_dirty_repository_refused(sample_checkout, tmp_path):
    (sample_checkout.repo_dir / "scratch.txt").write_text("dirty")
    try:
        with pytest.raises(git_manager.RepositoryError):
            git_manager.checkout(str(sample_checkout.repo_dir), tmp_path / "ws")
        co = git_manager.checkout(str(sample_checkout.repo_dir), tmp_path / "ws2",
                                  dirty_policy=DirtyPolicy.USE_HEAD)
        assert co.sha == SAMPLE_SHA
    finally:
        (sample_checkout.repo_dir / "scratch.txt").unlink()


def test_profile_detects_python_pytest(sample_profile):
    p = sample_profile
    assert p.primary_language == "python"
    assert p.test_framework == "pytest" and p.adapter == "python-pytest" and p.supported
    assert p.test_dirs == ["tests"] and p.source_dirs == ["shopcart"]
    assert "pyproject.toml" in p.dependency_files
    assert p.build_command == ["pip", "install", "-e", "."]


def test_tags_queries_compile():
    assert parser.get_tags_query("python") is not None
    assert parser.get_tags_query("javascript") is not None


def test_symbol_extraction_python():
    src = b"LIMIT = 3\nclass A(Base):\n    def f(self, x: int) -> int:\n        return g(x)\n"
    r = extract("m.py", "python", src)
    kinds = {(d.kind, d.name) for d in r.definitions}
    assert {("constant", "LIMIT"), ("class", "A"), ("method", "f")} <= kinds
    method = next(d for d in r.definitions if d.name == "f")
    assert method.parent == "A" and method.signature == "def f(self, x: int) -> int"
    assert r.references.get("g") and r.references.get("Base")
    assert r.syntax_errors == 0


def test_symbol_extraction_javascript_and_syntax_errors():
    r = extract("a.js", "javascript", b"class Cart { total() { return sum(this.items) } }\n"
                                       b"function f( {")
    assert ("class", "Cart") in {(d.kind, d.name) for d in r.definitions}
    assert r.syntax_errors > 0


def test_pagerank_properties():
    rank = pagerank(["a", "b", "c"], {("a", "b"): 1.0, ("c", "b"): 1.0})
    assert abs(sum(rank.values()) - 1.0) < 1e-6
    assert rank["b"] > rank["a"] and rank["b"] > rank["c"]


def test_repo_map_ranks_core_module_and_respects_budget(sample_checkout):
    from codeforge.utils.fs import iter_repo_files

    files = list(iter_repo_files(sample_checkout.snapshot_dir))
    rm = RepoMapper().build(sample_checkout.snapshot_dir, files, sample_checkout.sha,
                            token_budget=300)
    assert estimate_tokens(rm.rendered) <= 300
    top = list(rm.file_rank)[:3]
    assert "shopcart/money.py" in top  # used by every other module
    assert rm.extension_points and rm.dependency_edges
