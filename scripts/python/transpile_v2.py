"""V2 transpiler — Ghidra (post-apply-il2cpp-symbols) .c → Java.

This is a thin shim; the real code lives in the `transpile/` package:
  - transpile.mapping  → Mapping class (csharp↔java tables + il2cpp indexes + ptr_dat map)
  - transpile.parser   → tree-sitter singleton, Method, parse_file
  - transpile.walker   → Walker (AST → Java body)
  - transpile.emitter  → emit_class / emit_method_skeleton / emit_stub_method
  - transpile.cli      → main(), run_batch, transpile_one_file
  - transpile.naming   → camelCase / Java-keyword / generic-split helpers
  - transpile.paths    → PROJECT paths

The shim exists so existing invocations `python scripts/python/transpile_v2.py ...`
still work.
"""
from __future__ import annotations
import sys
from pathlib import Path

# Make the `transpile` package importable when this shim is run directly.
sys.path.insert(0, str(Path(__file__).resolve().parent))

from transpile.cli import main  # noqa: E402


if __name__ == '__main__':
    main()
