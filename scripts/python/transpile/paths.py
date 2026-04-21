"""Filesystem paths used across the transpiler package."""
from pathlib import Path

PROJECT = Path(__file__).resolve().parent.parent.parent.parent
DECOMPILED_DIR = PROJECT / 'data' / 'decompiled_tacticus'
IL2CPP_DUMP = PROJECT / 'data' / 'il2cpp_full.json'
PTR_DAT_MAP = PROJECT / 'data' / 'ptr_dat_map.json'
MAPPING_FILE = PROJECT / 'scripts' / 'python' / 'csharp_to_java_mapping.json'
TRANSPILED_DIR = PROJECT / 'data' / 'transpiled_tacticus'
