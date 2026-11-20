import zipfile

import pytest

from codeforge.logging_config import redact
from codeforge.utils import fs
from codeforge.utils.proc import run


@pytest.mark.parametrize("bad", ["../x.py", "/etc/passwd", "a/../../b", "C:/win.ini", ".git/config",
                                 "", "~/.ssh/id_rsa"])
def test_safe_relpath_rejects_unsafe(bad):
    with pytest.raises(fs.UnsafePathError):
        fs.safe_relpath(bad)


def test_safe_relpath_normalises():
    assert fs.safe_relpath("./pkg\\mod.py") == "pkg/mod.py"


def test_zip_slip_rejected(tmp_path):
    archive = tmp_path / "evil.zip"
    with zipfile.ZipFile(archive, "w") as zf:
        zf.writestr("../escape.txt", "x")
    with pytest.raises(fs.UnsafePathError):
        fs.safe_extract_zip(archive, tmp_path / "out")
    assert not (tmp_path / "escape.txt").exists()


def test_run_requires_argument_list():
    with pytest.raises(TypeError):
        run("echo hi")  # type: ignore[arg-type]


def test_redaction(monkeypatch):
    monkeypatch.setenv("FAKE_API_KEY", "supersecretvalue123")
    assert "supersecretvalue123" not in redact("key=supersecretvalue123")
    assert "AIza" in redact("AIzaSyA1234567890abcdefghijklmnop") and \
        "1234567890abcdefghijklmnop" not in redact("AIzaSyA1234567890abcdefghijklmnop")


def test_write_text_lf(tmp_path):
    p = tmp_path / "s.sh"
    fs.write_text_lf(p, "a\r\nb\n", executable=True)
    assert p.read_bytes() == b"a\nb\n"


def test_load_dotenv_exports_without_overriding(tmp_path, monkeypatch):
    from codeforge.config import load_dotenv

    env = tmp_path / ".env"
    env.write_text("# c\nCF_TEST_A=one\nexport CF_TEST_B='two'\nCF_TEST_C=your_key_here\n"
                   "CF_TEST_D=\nCF_TEST_E=new\n", encoding="utf-8")
    monkeypatch.delenv("CF_TEST_A", raising=False)
    monkeypatch.delenv("CF_TEST_B", raising=False)
    monkeypatch.setenv("CF_TEST_E", "existing")
    loaded = load_dotenv(env)
    import os
    assert os.environ["CF_TEST_A"] == "one" and os.environ["CF_TEST_B"] == "two"
    assert "CF_TEST_C" not in os.environ and "CF_TEST_D" not in os.environ
    assert os.environ["CF_TEST_E"] == "existing"
    assert sorted(loaded) == ["CF_TEST_A", "CF_TEST_B"]
    monkeypatch.delenv("CF_TEST_A")
    monkeypatch.delenv("CF_TEST_B")


def test_dashboard_rejects_foreign_host_header():
    from fastapi.testclient import TestClient

    from codeforge.web.server import app

    client = TestClient(app, base_url="http://127.0.0.1")
    assert client.get("/api/tasks").status_code == 200
    assert client.get("/api/tasks", headers={"host": "evil.example"}).status_code == 400


def test_crosscheck_decodes_reference_from_solve_sh(tmp_path):
    from codeforge.harbor.solution_packager import write_solution
    from codeforge.reporting.crosscheck import reference_files
    from codeforge.schemas.task import FileChange, ReferenceSolution

    ref = ReferenceSolution(explanation="", unified_diff="", changes=[
        FileChange(path="pkg/a.py", action="modify", content="A = 1\n"),
        FileChange(path="pkg/b.py", action="create", content="def f():\n    return 'é'\n")])
    write_solution(tmp_path, ref)
    assert reference_files(tmp_path) == {"pkg/a.py": "A = 1\n",
                                         "pkg/b.py": "def f():\n    return 'é'\n"}
