# -*- coding: utf-8 -*-
"""Docstring hygiene checker for Sphinx autodoc (v3.14.2).

Scans the package modules and reports, per function:
  - missing docstring
  - docstring claims a return value but the body never returns one
  - body returns a value but the docstring documents none

Exit code 0 = all clean, 1 = issues found. Read-only; never edits files.
"""
import ast
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SKIP_DIRS = {"tests", "docs", "build", "dist", "exports", "backups",
             "bin", "__pycache__", ".docs-venv"}
EXTRA_SKIP = {".git", ".github", "db_analysis"}  # db_analysis joins later


def iter_py_files():
    for dirpath, dirnames, filenames in os.walk(ROOT):
        rel = os.path.relpath(dirpath, ROOT)
        top = rel.split(os.sep)[0]
        if top in SKIP_DIRS or top in EXTRA_SKIP:
            dirnames[:] = []
            continue
        dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS]
        for fn in filenames:
            if fn.endswith(".py"):
                yield os.path.join(dirpath, fn)


def real_return(fn):
    """True only if some return statement yields a non-None value."""
    for node in ast.walk(fn):
        if isinstance(node, ast.Return):
            v = node.value
            if v is None:
                continue
            if isinstance(v, ast.Constant) and v.value is None:
                continue
            return True
    return False


def check_file(path):
    with open(path, encoding="utf-8") as f:
        tree = ast.parse(f.read())
    issues = []
    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        doc = ast.get_docstring(node) or ""
        claims = ":return:" in doc
        actual = real_return(node)
        if not doc.strip():
            issues.append((node.lineno, node.name, "missing docstring"))
        elif claims and not actual:
            issues.append((node.lineno, node.name,
                           "doc claims :return: but body returns None"))
        elif actual and not claims:
            issues.append((node.lineno, node.name,
                           "body returns a value but doc has no :return:"))
    return issues


def main():
    total = 0
    bad = 0
    for path in sorted(iter_py_files()):
        rel = os.path.relpath(path, ROOT)
        issues = check_file(path)
        total += 1
        if issues:
            bad += 1
            print(rel)
            for lineno, name, msg in issues:
                print(f"  L{lineno:<5} {name}: {msg}")
    if bad:
        print(f"\n{bad}/{total} files with issues")
        return 1
    print(f"all {total} files clean")
    return 0


if __name__ == "__main__":
    sys.exit(main())
