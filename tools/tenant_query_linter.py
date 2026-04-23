'''Tenant-scope linter for raw SQL (T1-14).

Walks `shoplift_detector/` for calls to `text("""...""")` and similar
raw-SQL builders. Every query against a tenant-scoped table must
either filter by `tenant_id` or carry an explicit `-- NO_TENANT_SCOPE`
marker in the SQL body.

Runs as a CI step. Exit code 1 on any violation. Usable as a module:

    $ python tools/tenant_query_linter.py

or:

    from tools.tenant_query_linter import lint_tree, LintViolation
    violations = lint_tree(repo_root)

The AST walk is intentionally restrictive — we scan only for
`text("...")` calls with a *literal* string argument (the 99%
pattern in this codebase). Dynamically-built SQL is a security
smell on its own and gets flagged via a separate rule.
'''

from __future__ import annotations

import ast
import pathlib
import re
import sys
from dataclasses import dataclass
from typing import Iterable

# Tables that carry a `tenant_id` column after T1-03. A query touching
# any of these in a FROM/JOIN/UPDATE/DELETE must scope by tenant_id
# (or carry the escape marker).
TENANT_SCOPED_TABLES = frozenset({
    "stores",
    "cameras",
    "alerts",
    "alert_feedback",
    "cases",
    "sync_packs",
    "inference_metrics",
    "camera_health",
})

# The only legal way to opt out of the tenant_id rule. Callers must
# spell it exactly — `--noscope`, `-- no tenant scope`, etc. don't
# count. This keeps the audit trail greppable.
BYPASS_MARKER = "-- NO_TENANT_SCOPE"

# Keywords that introduce table references. We look for any of the
# tenant-scoped tables immediately (or one comma away) after these.
_TABLE_INTRODUCERS = re.compile(
    r"\b(?:FROM|JOIN|UPDATE|INTO|DELETE\s+FROM)\s+([A-Za-z_][A-Za-z0-9_]*)",
    re.IGNORECASE,
)

# `tenant_id` referenced anywhere in the query body. Not just WHERE —
# CTEs, subqueries, and ON clauses all count as long as the token
# appears somewhere, since RLS + the column FK make a leak harder to
# slip past if it's mentioned at all.
_TENANT_ID_REFERENCE = re.compile(r"\btenant_id\b")


@dataclass(frozen=True)
class LintViolation:
    path: pathlib.Path
    lineno: int
    table: str
    snippet: str

    def format(self, repo_root: pathlib.Path) -> str:
        try:
            rel = self.path.relative_to(repo_root)
        except ValueError:
            rel = self.path
        return (
            f"{rel}:{self.lineno}: query touches `{self.table}` "
            f"without tenant_id filter or {BYPASS_MARKER} marker\n"
            f"    {self.snippet}"
        )


def _iter_text_literals(tree: ast.AST) -> Iterable[tuple[int, str]]:
    """Yield (lineno, literal) for every `text("...")` call in `tree`
    whose single positional arg is a string literal."""
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        if isinstance(func, ast.Name) and func.id == "text":
            pass
        elif isinstance(func, ast.Attribute) and func.attr == "text":
            pass
        else:
            continue
        if len(node.args) != 1:
            continue
        arg = node.args[0]
        if isinstance(arg, ast.Constant) and isinstance(arg.value, str):
            yield arg.lineno, arg.value


def _referenced_tables(sql: str) -> set[str]:
    """Return the subset of TENANT_SCOPED_TABLES mentioned in the SQL."""
    tables: set[str] = set()
    for match in _TABLE_INTRODUCERS.finditer(sql):
        name = match.group(1).lower()
        if name in TENANT_SCOPED_TABLES:
            tables.add(name)
    return tables


def _has_tenant_scope(sql: str) -> bool:
    """True if the query filters by tenant_id *or* explicitly opts out."""
    if BYPASS_MARKER in sql:
        return True
    return bool(_TENANT_ID_REFERENCE.search(sql))


def lint_file(path: pathlib.Path) -> list[LintViolation]:
    """Return every violation in a single .py file."""
    try:
        source = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return []
    try:
        tree = ast.parse(source, filename=str(path))
    except SyntaxError:
        return []

    violations: list[LintViolation] = []
    for lineno, sql in _iter_text_literals(tree):
        tables = _referenced_tables(sql)
        if not tables:
            continue
        if _has_tenant_scope(sql):
            continue
        snippet = sql.strip().splitlines()[0][:120]
        for table in sorted(tables):
            violations.append(
                LintViolation(
                    path=path, lineno=lineno, table=table, snippet=snippet
                )
            )
    return violations


def lint_tree(
    root: pathlib.Path,
    *,
    ignore: Iterable[str] = ("tests", "tools", "alembic"),
) -> list[LintViolation]:
    """Walk `root` for .py files and aggregate violations.

    `ignore` names top-level directories to skip — tests hold fixture
    SQL that deliberately bypasses tenant scope, migrations predate
    the tenant_id column, and this linter itself lives in `tools/`.
    """
    ignored = {part.strip("/") for part in ignore}
    out: list[LintViolation] = []
    for py_file in sorted(root.rglob("*.py")):
        # Skip ignored top-level trees.
        try:
            rel_parts = py_file.relative_to(root).parts
        except ValueError:
            continue
        if rel_parts and rel_parts[0] in ignored:
            continue
        out.extend(lint_file(py_file))
    return out


def main(argv: list[str]) -> int:
    root = pathlib.Path(argv[1]) if len(argv) > 1 else pathlib.Path.cwd()
    violations = lint_tree(root)
    if not violations:
        print("tenant_query_linter: OK")
        return 0
    print(f"tenant_query_linter: {len(violations)} violation(s)")
    for v in violations:
        print(v.format(root))
    return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv))
