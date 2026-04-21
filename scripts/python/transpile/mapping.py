"""Mapping class: lookup tables for csharp_to_java_mapping + il2cpp_full.json + ptr_dat_map."""
from __future__ import annotations
import json
import re
from pathlib import Path

from .naming import _primitive_to_wrapper, _split_generic_args


class Mapping:
    """Lookup tables: csharp_to_java_mapping.json + indexed il2cpp_full.json."""

    # Java keywords that can appear as C# namespace segments — renamed to avoid collision
    _JAVA_KEYWORD_PACKAGE_MAP = {
        'enum': 'enums',
        'class': 'classes',
        'interface': 'interfaces',
        'package': 'packages',
        'abstract': 'abstract_',
        'final': 'final_',
        'static': 'static_',
        'native': 'native_',
        'new': 'new_',
    }

    def __init__(self, data: dict,
                 il2cpp_methods: dict[int, dict] | None = None,
                 il2cpp_classes: dict[str, dict] | None = None,
                 il2cpp_enums: dict[str, dict] | None = None,
                 ptr_dat_map: dict[int, dict] | None = None):
        self.primitives = data.get('primitives', {})
        self.collections = data.get('collections', {})
        self.collection_methods = data.get('collection_methods', {})
        self.system_methods = data.get('system_methods', {})
        self.il2cpp_runtime = data.get('il2cpp_runtime', {})
        self.fix64 = data.get('fix64', {})
        self.namespaces = data.get('namespaces', {})
        self.reserved_rename = data.get('reserved_rename', {})
        self.il2cpp_methods = il2cpp_methods or {}  # rva_int -> method dict
        self.il2cpp_classes = il2cpp_classes or {}  # csharp_fqn -> class dict
        self.il2cpp_enums = il2cpp_enums or {}      # csharp_fqn -> enum dict
        # PTR_DAT_xxxxxxxx data cells resolved at runtime via scan-ptr-dat.js.
        # rva_int -> {'k': 'class'|'method', 'n': full_name}
        self.ptr_dat_map = ptr_dat_map or {}
        # Reverse indexes for call resolution
        self.methods_by_fqn: dict[str, list[dict]] = {}
        self.methods_by_suffix: dict[str, list[dict]] = {}
        for m in self.il2cpp_methods.values():
            fqn = m.get('n')
            if not fqn:
                continue
            self.methods_by_fqn.setdefault(fqn, []).append(m)
            parts = fqn.rsplit('.', 2)
            if len(parts) >= 2:
                suffix = '.'.join(parts[-2:])
                self.methods_by_suffix.setdefault(suffix, []).append(m)
        # Index inflated instances by generic-def name (strip `<...>` and trailing `\`N`)
        # so a lookup on `Foo\`1` (all offsets at 0) can fall back to `Foo<T>` or
        # `Foo<SomeConcreteType>` which has real offsets.
        self.inflated_by_def: dict[str, list[str]] = {}
        for name, c in self.il2cpp_classes.items():
            if not c.get('infl'):
                continue
            base = name.split('<', 1)[0]
            # Convert `Foo` to `Foo`N` if the def has that arity
            for arity in (1, 2, 3, 4):
                candidate = f'{base}`{arity}'
                if candidate in self.il2cpp_classes:
                    self.inflated_by_def.setdefault(candidate, []).append(name)
                    break
            else:
                self.inflated_by_def.setdefault(base, []).append(name)

    @classmethod
    def load(cls, path: Path, il2cpp_dump_path: Path | None = None,
             ptr_dat_map_path: Path | None = None) -> 'Mapping':
        with open(path, 'r', encoding='utf-8') as f:
            mapping_data = json.load(f)
        il2cpp_methods: dict[int, dict] = {}
        il2cpp_classes: dict[str, dict] = {}
        il2cpp_enums: dict[str, dict] = {}
        if il2cpp_dump_path and il2cpp_dump_path.exists():
            with open(il2cpp_dump_path, 'r', encoding='utf-8') as f:
                dump = json.load(f)
            for rva_hex, m in dump.get('methods', {}).items():
                try:
                    il2cpp_methods[int(rva_hex, 16)] = m
                except ValueError:
                    continue
            il2cpp_classes = dump.get('classes', {})
            il2cpp_enums = dump.get('enums', {})
        ptr_dat_map: dict[int, dict] = {}
        if ptr_dat_map_path and ptr_dat_map_path.exists():
            with open(ptr_dat_map_path, 'r', encoding='utf-8') as f:
                raw = json.load(f)
            for rva_hex, entry in raw.items():
                try:
                    ptr_dat_map[int(rva_hex, 16)] = entry
                except ValueError:
                    continue
        return cls(mapping_data, il2cpp_methods, il2cpp_classes, il2cpp_enums, ptr_dat_map)

    def resolve_fun(self, fun_name: str) -> str | None:
        """Given a Ghidra-style `FUN_xxxxxxxx` or `thunk_FUN_xxxxxxxx`,
        look up the RVA in il2cpp_full.json and return the C# full name, or None.
        """
        hex_part = fun_name
        if hex_part.startswith('thunk_FUN_'):
            hex_part = hex_part[len('thunk_FUN_'):]
        elif hex_part.startswith('FUN_'):
            hex_part = hex_part[len('FUN_'):]
        else:
            return None
        try:
            rva = int(hex_part, 16)
        except ValueError:
            return None
        m = self.il2cpp_methods.get(rva)
        return m['n'] if m else None

    def rewrite_type(self, ghidra_type: str) -> str:
        """Translate a C/C# type string into a Java type string.
        Handles arrays, generics, primitives, namespace translation."""
        # Strip all pointer/ref markers — Java has no pointers or `ref`/`out` params
        t = ghidra_type.strip().replace('*', '').replace('&', '').strip()
        t = re.sub(r'\s+', ' ', t)
        if not t:
            return 'Object'

        if t.endswith('[]'):
            return self.rewrite_type(t[:-2]) + '[]'

        # Generic type: Outer<Arg1, Arg2, ...>
        m = re.match(r'^([\w.`]+)<(.+)>$', t)
        if m:
            outer_raw = m.group(1)
            args_raw = m.group(2)
            outer_clean = re.sub(r'`\d+', '', outer_raw)
            # System.Nullable<T> has no Java analogue — unwrap to T (boxed if primitive).
            if outer_clean in ('System.Nullable', 'Nullable'):
                inner_args = _split_generic_args(args_raw)
                if len(inner_args) == 1:
                    return _primitive_to_wrapper(self.rewrite_type(inner_args[0]))
            outer_java = self.collections.get(outer_clean) or self._map_namespace_type(outer_clean)
            args = [_primitive_to_wrapper(self.rewrite_type(a)) for a in _split_generic_args(args_raw)]
            return f'{outer_java}<{", ".join(args)}>'

        c_primitives = {
            'void': 'Object',
            'unsigned char': 'int', 'unsigned short': 'int', 'unsigned int': 'int',
            'unsigned long': 'long', 'unsigned long long': 'long', 'long long': 'long',
            'uint8_t': 'byte', 'uint16_t': 'short', 'uint32_t': 'int', 'uint64_t': 'long',
            'int8_t': 'byte', 'int16_t': 'short', 'int32_t': 'int', 'int64_t': 'long',
            'uchar': 'byte', 'ushort': 'short', 'uint': 'int', 'ulong': 'long',
            'size_t': 'long', 'ptrdiff_t': 'long', 'code': 'Object',
        }
        if t in c_primitives:
            return c_primitives[t]
        if t in ('byte', 'int', 'long', 'double', 'float', 'char', 'short', 'bool', 'boolean', 'String'):
            return t
        if t.startswith('undefined'):
            return 'Object'

        csharp = t.replace('_', '.')
        csharp = re.sub(r'`\d+', '', csharp)
        if csharp in self.primitives:
            return self.primitives[csharp]
        if csharp in self.fix64:
            return self.fix64[csharp]
        return self._map_namespace_type(csharp)

    def _map_namespace_type(self, csharp: str) -> str:
        """Apply namespace prefix remap + lowercased-package convention."""
        if csharp in self.primitives:
            return self.primitives[csharp]
        if csharp in self.fix64:
            return self.fix64[csharp]
        for ns, jp in self.namespaces.items():
            if csharp.startswith(ns):
                rest = csharp[len(ns):]
                parts = rest.split('.')
                if len(parts) > 1:
                    pkg_parts = [self._JAVA_KEYWORD_PACKAGE_MAP.get(p.lower(), p.lower()) for p in parts[:-1]]
                    return f'{jp}{".".join(pkg_parts)}.{parts[-1]}'
                return jp + rest
        return csharp

    def resolve_ptr_dat(self, name: str) -> str | None:
        """Resolve a Ghidra-style `PTR_DAT_xxxxxxxx` or `DAT_xxxxxxxx` identifier via the
        runtime scan map. Returns a Java-compilable expression or None if the name
        doesn't match the pattern.
        """
        for prefix in ('PTR_DAT_', 'DAT_'):
            if name.startswith(prefix):
                hex_part = name[len(prefix):]
                break
        else:
            return None
        try:
            rva = int(hex_part, 16)
        except ValueError:
            return None
        entry = self.ptr_dat_map.get(rva)
        if entry is None:
            return f'null /* unresolved {name} */'
        kind = entry.get('k', '')
        full = entry.get('n', '')
        if kind == 'class':
            return f'null /* class ref: {full} */'
        if kind == 'method':
            return f'null /* method ref: {full} */'
        return f'null /* {name} */'

    def rewrite_identifier(self, name: str) -> str:
        if name in self.reserved_rename:
            return self.reserved_rename[name]
        if name.startswith('PTR_DAT_') or name.startswith('DAT_'):
            resolved = self.resolve_ptr_dat(name)
            if resolved is not None:
                return resolved
        return name
