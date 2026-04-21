"""Transpiler package: Ghidra (post-IL2CPP symbolisation) decompiled .c → Java.

Layout:
- paths      : filesystem constants
- naming     : name-mangling helpers (camelCase, Java keywords, generics)
- mapping    : Mapping class (csharp→java type table + il2cpp metadata indexes)
- parser     : tree-sitter singleton, Method, parse_file, declarator walker
- walker     : Walker class (AST → Java body)
- emitter    : emit_method_skeleton, emit_class, emit_stub_method + helpers
- cli        : main(), run_batch, transpile_one_file
"""
from .mapping import Mapping
from .parser import Method, parse_file
from .walker import Walker
from .emitter import emit_class, emit_method_skeleton, emit_stub_method, derive_package, simple_class_name
from .cli import main, run_batch, transpile_one_file

__all__ = [
    'Mapping', 'Method', 'parse_file', 'Walker',
    'emit_class', 'emit_method_skeleton', 'emit_stub_method',
    'derive_package', 'simple_class_name',
    'main', 'run_batch', 'transpile_one_file',
]
