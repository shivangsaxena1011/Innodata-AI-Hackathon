import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tests" / "fixtures"))

from codeforge.repository import git_manager  # noqa: E402

SAMPLE = ROOT / "examples" / "sample_target_repository"


@pytest.fixture(scope="session")
def sample_checkout(tmp_path_factory):
    ws = tmp_path_factory.mktemp("ws")
    repo = git_manager.materialize_sample(SAMPLE, ws / "samples" / "shopcart")
    return git_manager.checkout(str(repo), ws)


@pytest.fixture(scope="session")
def sample_profile(sample_checkout):
    from codeforge.repository.repository_profiler import profile_repository

    return profile_repository(sample_checkout)
