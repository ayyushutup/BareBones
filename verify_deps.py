#!/usr/bin/env python3
"""
verify_deps.py — Dependency Proof Script for BareBones

Scans all Python source files in the project and verifies that every import
is either a Python standard library module or an internal project module.
Exits with code 0 on success, 1 if any third-party dependency is found.

Usage:
    python3 verify_deps.py
"""

import os
import sys
import ast
import importlib.util

# Modules that are part of the barebones project itself
PROJECT_MODULES = {"barebones"}

# Known stdlib module names (Python 3.x). We detect dynamically using
# sys.stdlib_module_names (Python 3.10+) or fall back to a curated list.
def get_stdlib_modules():
    if hasattr(sys, "stdlib_module_names"):
        return set(sys.stdlib_module_names)
    # Fallback for Python < 3.10
    return {
        "abc", "aifc", "argparse", "array", "ast", "asyncio", "atexit",
        "base64", "bdb", "binascii", "binhex", "bisect", "builtins",
        "bz2", "calendar", "cgi", "cgitb", "chunk", "cmath", "cmd",
        "code", "codecs", "codeop", "collections", "colorsys", "compileall",
        "concurrent", "configparser", "contextlib", "contextvars", "copy",
        "copyreg", "cProfile", "crypt", "csv", "ctypes", "curses",
        "dataclasses", "datetime", "dbm", "decimal", "difflib", "dis",
        "distutils", "doctest", "email", "encodings", "enum", "errno",
        "faulthandler", "fcntl", "filecmp", "fileinput", "fnmatch",
        "fractions", "ftplib", "functools", "gc", "getopt", "getpass",
        "gettext", "glob", "grp", "gzip", "hashlib", "heapq", "hmac",
        "html", "http", "idlelib", "imaplib", "imghdr", "imp",
        "importlib", "inspect", "io", "ipaddress", "itertools", "json",
        "keyword", "lib2to3", "linecache", "locale", "logging", "lzma",
        "mailbox", "mailcap", "marshal", "math", "mimetypes", "mmap",
        "modulefinder", "multiprocessing", "netrc", "nis", "nntplib",
        "numbers", "operator", "optparse", "os", "ossaudiodev",
        "pathlib", "pdb", "pickle", "pickletools", "pipes", "pkgutil",
        "platform", "plistlib", "poplib", "posix", "posixpath", "pprint",
        "profile", "pstats", "pty", "pwd", "py_compile", "pyclbr",
        "pydoc", "queue", "quopri", "random", "re", "readline", "reprlib",
        "resource", "rlcompleter", "runpy", "sched", "secrets", "select",
        "selectors", "shelve", "shlex", "shutil", "signal", "site",
        "smtpd", "smtplib", "sndhdr", "socket", "socketserver", "sqlite3",
        "ssl", "stat", "statistics", "string", "stringprep", "struct",
        "subprocess", "sunau", "symtable", "sys", "sysconfig", "syslog",
        "tabnanny", "tarfile", "telnetlib", "tempfile", "termios", "test",
        "textwrap", "threading", "time", "timeit", "tkinter", "token",
        "tokenize", "trace", "traceback", "tracemalloc", "tty", "turtle",
        "turtledemo", "types", "typing", "unicodedata", "unittest",
        "urllib", "uu", "uuid", "venv", "warnings", "wave", "weakref",
        "webbrowser", "winreg", "winsound", "wsgiref", "xdrlib", "xml",
        "xmlrpc", "zipapp", "zipfile", "zipimport", "zlib",
        # Common sub-packages that appear as top-level imports
        "_thread", "ntpath", "posixpath", "genericpath",
    }

def get_top_level_module(name):
    """Extract top-level module from a dotted import path."""
    return name.split(".")[0]

def scan_file(filepath, stdlib_modules):
    """Parse a Python file and return all imported top-level module names."""
    with open(filepath, "r", encoding="utf-8") as f:
        try:
            tree = ast.parse(f.read(), filename=filepath)
        except SyntaxError as e:
            print(f"  ⚠ Syntax error in {filepath}: {e}")
            return set()

    imports = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                imports.add(get_top_level_module(alias.name))
        elif isinstance(node, ast.ImportFrom):
            if node.module and node.level == 0:  # Absolute imports only
                imports.add(get_top_level_module(node.module))
    return imports

def main():
    print("=" * 60)
    print("  BareBones Dependency Verification")
    print("=" * 60)
    print()

    stdlib_modules = get_stdlib_modules()
    source_dir = os.path.dirname(os.path.abspath(__file__))

    all_imports = {}
    third_party = {}

    for root, dirs, files in os.walk(source_dir):
        # Skip hidden dirs and __pycache__
        dirs[:] = [d for d in dirs if not d.startswith(".") and d != "__pycache__"]
        for fname in files:
            if fname.endswith(".py"):
                fpath = os.path.join(root, fname)
                rel_path = os.path.relpath(fpath, source_dir)
                imports = scan_file(fpath, stdlib_modules)
                all_imports[rel_path] = imports

                for mod in imports:
                    if mod not in stdlib_modules and mod not in PROJECT_MODULES:
                        if rel_path not in third_party:
                            third_party[rel_path] = set()
                        third_party[rel_path].add(mod)

    # Report
    total_files = len(all_imports)
    unique_imports = set()
    for imps in all_imports.values():
        unique_imports.update(imps)

    stdlib_used = sorted(unique_imports - PROJECT_MODULES)

    print(f"  Files scanned:       {total_files}")
    print(f"  Unique imports:      {len(unique_imports)}")
    print(f"  Stdlib modules used: {len(stdlib_used)}")
    print(f"  Project modules:     {sorted(PROJECT_MODULES)}")
    print()

    print("  Standard library modules used:")
    for mod in stdlib_used:
        print(f"    ✓ {mod}")
    print()

    if third_party:
        print("  ❌ THIRD-PARTY DEPENDENCIES DETECTED:")
        for fpath, mods in sorted(third_party.items()):
            for mod in sorted(mods):
                print(f"    ✗ {mod} (in {fpath})")
        print()
        print("  RESULT: FAIL — third-party dependencies found.")
        return 1
    else:
        print("  ✅ RESULT: PASS — zero third-party dependencies.")
        print("     All imports resolve to Python standard library or project modules.")
        return 0

if __name__ == "__main__":
    sys.exit(main())
