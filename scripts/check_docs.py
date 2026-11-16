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
EXTRA_SKIP = {".git", ".github"}  # db_analysis joins later


def iter_py_files(only=None):
    """遍历项目内待检查的 .py 文件。

    只走未被 SKIP_DIRS / EXTRA_SKIP 排除的目录；only 给出相对路径列表
    时只检查这些文件（build_docs.ps1 按 docs/*.rst automodule 列表传入）。

    :param only: 相对路径列表（None = 全仓库扫描）。
    :type only: list 或 None
    :yield: 待检查的 .py 相对路径。
    """

    if only:
        for rel in only:
            yield os.path.join(ROOT, rel)
        return
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
    """True only if some return statement yields a non-None value.

    裸 return 与 return None 都不算"返回值"（它们不产生 doc 要求的
    :return: 字段）。

    :param fn: 函数 AST 节点。
    :type fn: ast.FunctionDef
    :return: 函数体是否有真正返回值的 return。
    :rtype: bool
    """
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
    """检查单个文件的 docstring 卫生，返回问题列表。

    三类问题：缺 docstring；doc 声明 :return: 但函数体无返回值；函数体
    有返回值但 doc 没有 :return:。

    :param path: 文件绝对路径。
    :type path: str
    :return: [(行号, 函数名, 问题描述), ...]。
    :rtype: list
    """
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
    """CLI 入口：扫描并打印问题清单，0 = 全绿，1 = 有问题。

    只读检查，从不改文件。只给具体文件参数时只查这些文件。

    :return: 0 = 全绿，1 = 有问题。
    """
    only = sys.argv[1:] or None
    total = 0
    bad = 0
    for path in sorted(iter_py_files(only)):
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
