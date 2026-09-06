from __future__ import annotations

import ast
from pathlib import Path

from research_platform.governance.architecture.source_scan import SourceInvariantViolation, imports, violation


def _pipeline_boundary(root: Path, sem: Path) -> list[SourceInvariantViolation]:
    rows: list[SourceInvariantViolation] = []
    pipeline = sem / "evolution" / "pipeline.py"
    if not pipeline.exists():
        return rows
    for module, line in imports(pipeline):
        if module.rsplit(".", 1)[-1] in {"eligibility", "compiler"}:
            rows.append(violation(
                root, pipeline, "sem_evolution_pipeline_provider_firewall", line,
                f"evolution pipeline imports concrete stage provider {module}",
            ))
    tree = ast.parse(pipeline.read_text(encoding="utf-8"), filename=str(pipeline))
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == "__init__":
            for default in (*node.args.defaults, *[x for x in node.args.kw_defaults if x is not None]):
                if isinstance(default, ast.Constant) and default.value is None:
                    rows.append(violation(
                        root, pipeline, "sem_evolution_pipeline_explicit_stages", default.lineno,
                        "evolution pipeline stage dependency may not default to None",
                    ))
    return rows


def _explicit_composition(root: Path, sem: Path) -> list[SourceInvariantViolation]:
    rows: list[SourceInvariantViolation] = []
    implementation = sem / "implementation.py"
    if implementation.exists():
        tree = ast.parse(implementation.read_text(encoding="utf-8"), filename=str(implementation))
        for node in tree.body:
            if not isinstance(node, ast.ClassDef) or node.name != "SelfEvolvingMemoryImplementation":
                continue
            for child in node.body:
                if not isinstance(child, ast.FunctionDef) or child.name != "__init__":
                    continue
                positional = list(child.args.args)
                positional_defaults = [None] * (len(positional) - len(child.args.defaults)) + list(child.args.defaults)
                keyword_only = list(zip(child.args.kwonlyargs, child.args.kw_defaults, strict=True))
                args = list(zip(positional, positional_defaults, strict=True)) + keyword_only
                for arg, default in args:
                    if arg.arg in {"evolution_factory", "evolution_provider_id"} and default is not None:
                        rows.append(violation(
                            root, implementation, "sem_evolution_explicit_composition",
                            getattr(default, "lineno", child.lineno),
                            f"SEM implementation may not default {arg.arg}; treatment evolution must be explicitly composed",
                        ))

    composition = sem / "composition.py"
    if composition.exists():
        tree = ast.parse(composition.read_text(encoding="utf-8"), filename=str(composition))
        for node in tree.body:
            if not isinstance(node, ast.FunctionDef) or node.name != "build_self_evolving_memory_method":
                continue
            positional = list(node.args.args)
            positional_defaults = [None] * (len(positional) - len(node.args.defaults)) + list(node.args.defaults)
            keyword_only = list(zip(node.args.kwonlyargs, node.args.kw_defaults, strict=True))
            args = list(zip(positional, positional_defaults, strict=True)) + keyword_only
            for arg, default in args:
                if arg.arg in {"evolution_factory", "evolution_provider_id"} and default is not None:
                    rows.append(violation(
                        root, composition, "sem_evolution_explicit_composition",
                        getattr(default, "lineno", node.lineno),
                        f"self-evolving treatment may not default {arg.arg}",
                    ))
            for child in ast.walk(node):
                if isinstance(child, ast.Name) and child.id == "DisabledSessionEvolutionFactory":
                    rows.append(violation(
                        root, composition, "sem_evolution_explicit_composition", child.lineno,
                        "self-evolving treatment may not bind disabled evolution",
                    ))
    return rows


def audit_sem_evolution_invariants(root: Path, sem: Path) -> list[SourceInvariantViolation]:
    return _pipeline_boundary(root, sem) + _explicit_composition(root, sem)


__all__ = ["audit_sem_evolution_invariants"]
