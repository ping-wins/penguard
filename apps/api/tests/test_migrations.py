from __future__ import annotations

import ast
from pathlib import Path


def _string_value(node: ast.AST | None) -> str | None:
    if node is None:
        return None
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    return None


def _revision_values(path: Path) -> tuple[str, tuple[str, ...]]:
    module = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    revision: str | None = None
    down_revisions: tuple[str, ...] = ()

    for statement in module.body:
        target_name: str | None = None
        value: ast.AST | None = None
        if isinstance(statement, ast.Assign) and len(statement.targets) == 1:
            target = statement.targets[0]
            if isinstance(target, ast.Name):
                target_name = target.id
                value = statement.value
        elif isinstance(statement, ast.AnnAssign) and isinstance(statement.target, ast.Name):
            target_name = statement.target.id
            value = statement.value

        if target_name == "revision":
            revision = _string_value(value)
        elif target_name == "down_revision":
            if isinstance(value, ast.Tuple | ast.List):
                down_revisions = tuple(
                    item
                    for element in value.elts
                    if (item := _string_value(element)) is not None
                )
            else:
                down_revision = _string_value(value)
                down_revisions = (down_revision,) if down_revision else ()

    if revision is None:
        raise AssertionError(f"{path.name} does not declare a revision")
    return revision, down_revisions


def test_alembic_migration_graph_is_linear() -> None:
    versions_dir = Path(__file__).resolve().parents[1] / "migrations" / "versions"
    revision_files = sorted(
        path for path in versions_dir.glob("*.py") if path.name != "__init__.py"
    )

    revisions: dict[str, Path] = {}
    duplicates: dict[str, list[str]] = {}
    down_revisions: set[str] = set()

    for path in revision_files:
        revision, parents = _revision_values(path)
        if revision in revisions:
            duplicates.setdefault(revision, [revisions[revision].name]).append(path.name)
        else:
            revisions[revision] = path
        down_revisions.update(parents)

    assert duplicates == {}

    missing_parents = sorted(parent for parent in down_revisions if parent not in revisions)
    assert missing_parents == []

    heads = sorted(revision for revision in revisions if revision not in down_revisions)
    assert len(heads) == 1
