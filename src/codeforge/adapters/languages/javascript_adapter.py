"""Node.js adapter (experimental): projects tested with node:test, vitest or jest.

Repository analysis is fully supported for JavaScript. Execution uses each framework's own
JUnit reporter. AST mutation is not implemented for JavaScript; CodeForge reports it as
unsupported and relies on LLM-generated semantic mutants for test-quality evidence.
"""

from __future__ import annotations

import re

from codeforge.adapters.languages.base import LanguageAdapter
from codeforge.schemas.repository import RepositoryProfile


class JavaScriptAdapter(LanguageAdapter):
    name = "node"
    language = "javascript"
    supports_ast_mutation = False

    def __init__(self, framework: str | None = None):
        self.framework = framework or "node:test"

    def base_image(self, profile: RepositoryProfile) -> str:
        return "node:22-slim"

    def dockerfile(self, profile: RepositoryProfile, base_image: str) -> str:
        pm = profile.package_manager or "npm"
        install = {"npm": "npm ci || npm install", "yarn": "corepack enable && yarn install "
                   "--frozen-lockfile", "pnpm": "corepack enable && pnpm install --frozen-lockfile"}
        return (
            f"FROM {base_image}\n\nWORKDIR /app\nCOPY repo/ /app/\n\n"
            f"RUN {install.get(pm, install['npm'])}\n"
        )

    def test_shell(self, test_paths: list[str], junit_path: str) -> str:
        paths = " ".join(test_paths)
        if self.framework == "vitest":
            return f"npx vitest run --reporter=junit --outputFile={junit_path} {paths}"
        if self.framework == "jest":
            return (f"JEST_JUNIT_OUTPUT_FILE={junit_path} npx jest --ci "
                    f"--reporters=default --reporters=jest-junit {paths}")
        return (f"node --test --test-reporter=junit --test-reporter-destination={junit_path} "
                f"{paths}")

    def feature_test_path(self, profile: RepositoryProfile, slug: str) -> str:
        base = profile.test_dirs[0] if profile.test_dirs else "test"
        safe = re.sub(r"[^a-z0-9-]", "-", slug.lower())
        return f"{base}/codeforge-{safe}.test.js"

    def test_style_hint(self, profile: RepositoryProfile) -> str:
        return f"Write {self.framework} tests using the project's module system."
