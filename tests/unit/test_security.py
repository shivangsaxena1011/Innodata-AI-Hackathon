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
