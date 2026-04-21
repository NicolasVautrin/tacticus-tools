"""Emit Java class/method text from parsed Methods + il2cpp metadata."""
from __future__ import annotations
import re
from pathlib import Path

from .mapping import Mapping
from .parser import Method, _split_class_method
from .walker import Walker
from .naming import _camel_case_method, _clean_field_name


# Cache for top-level class resolution (avoid walking the chain repeatedly)
_TOP_CLASS_CACHE: dict[tuple[int, str], str] = {}


def simple_class_name(class_fqn: str) -> str:
    name = class_fqn.rsplit('.', 1)[-1]
    return (name.replace('`', '_T').replace('<', '_').replace('>', '_')
                 .replace(',', '_').replace(' ', ''))


def derive_package(class_fqn: str, mapping: Mapping) -> str:
    """`IdunBattle.Configuration.AbilityConfiguration` -> `tacticus.idunbattle.configuration`.
    Renames Java-keyword segments (e.g. `enum` -> `enums`).
    """
    def map_pkg(p: str) -> str:
        return Mapping._JAVA_KEYWORD_PACKAGE_MAP.get(p.lower(), p.lower())

    for ns, jp in mapping.namespaces.items():
        if class_fqn.startswith(ns):
            rest = class_fqn[len(ns):]
            parts = rest.split('.')
            if len(parts) > 1:
                return jp.rstrip('.') + '.' + '.'.join(map_pkg(p) for p in parts[:-1])
            return jp.rstrip('.')
    parts = class_fqn.split('.')
    if len(parts) > 1:
        return '.'.join(map_pkg(p) for p in parts[:-1])
    return ''


def _top_level_class_of(decl: str, mapping: Mapping) -> str:
    """Walk the declaring_type chain and return the outermost class FQN."""
    if not decl:
        return ''
    cache_key = (id(mapping), decl)
    if cache_key in _TOP_CLASS_CACHE:
        return _TOP_CLASS_CACHE[cache_key]
    visited: set[str] = set()
    cur = decl
    while cur and cur not in visited:
        visited.add(cur)
        cls = mapping.il2cpp_classes.get(cur)
        if not cls:
            break
        parent_decl = cls.get('decl')
        if not parent_decl:
            break
        cur = parent_decl
    _TOP_CLASS_CACHE[cache_key] = cur
    return cur


def emit_method_skeleton(m: Method, mapping: Mapping, inline_class_name: str | None = None) -> str:
    """Emit a Java method declaration for the given extracted method.
    Signature is sourced from il2cpp_methods.tsv when available (real C# types),
    falling back to Ghidra's parsed params. This matters because we apply void*
    sigs to Ghidra — m.params all look like `Object`, but il2cpp has the real types.
    """
    il2 = mapping.il2cpp_methods.get(m.rva)
    is_static = bool(il2.get('s')) if il2 else False

    if il2 and il2.get('p') is not None:
        ret = mapping.rewrite_type(il2.get('r', m.return_type))
        explicit_params = [(p.get('t', 'System.Object'), p.get('n', f'p{i}'))
                           for i, p in enumerate(il2.get('p', []))]
    else:
        ret = mapping.rewrite_type(m.return_type)
        explicit_params = list(m.params)
        if explicit_params and explicit_params[0][1] == 'this':
            explicit_params = explicit_params[1:]

    java_params = [(mapping.rewrite_type(t), mapping.rewrite_identifier(n)) for t, n in explicit_params]
    sig_params = ', '.join(f'{jt} {jn}' for jt, jn in java_params)

    # Detect bare generic type parameters (e.g. `T`, `TKey`, `TValue`) referenced in the
    # signature but not declared on the class — emit them as method-level generics.
    type_vars: list[str] = []
    def _collect_type_vars(txt: str) -> None:
        for tok in re.findall(r'\b([A-Z][A-Za-z0-9]*)\b', txt):
            if re.fullmatch(r'T[A-Z0-9a-z]*', tok) and tok not in type_vars:
                type_vars.append(tok)
    for jt, _ in java_params:
        _collect_type_vars(jt)
    _collect_type_vars(ret)
    generic_decl = f'<{", ".join(type_vars)}> ' if type_vars else ''

    method_name = m.method_name
    is_ctor = False
    if method_name == '.ctor':
        method_name = inline_class_name or simple_class_name(m.class_fqn)
        ret = ''
        is_ctor = True
        generic_decl = ''
    elif method_name == '.cctor':
        method_name = 'staticInit'
    else:
        if method_name and method_name[0].isupper():
            method_name = method_name[0].lower() + method_name[1:]

    mod = 'public static' if is_static else 'public'
    ret_part = '' if is_ctor else f'{ret} '

    if m.body_node is not None:
        walker = Walker(m.src, mapping, class_fqn=m.class_fqn, method=m)
        body = walker.emit_body(m.body_node, is_top=True)
    else:
        body = f'    // TODO: no body (RVA 0x{m.rva:X})'

    return f'{mod} {generic_decl}{ret_part}{method_name}({sig_params}) {{\n{body}\n}}'


def emit_stub_method(rva: int, m: dict, mapping: Mapping, inline_class_name: str) -> str:
    """Emit a Java method stub for an il2cpp method dict (from Frida dump).
    Used when Ghidra failed to decompile the body (TIMEOUT/NULL) or the method
    was compiler-elided to a vtable slot only."""
    fqn = m.get('n', '')
    _, method_name = _split_class_method(fqn)
    ret = mapping.rewrite_type(m.get('r', 'System.Void'))
    is_static = bool(m.get('s'))
    params = m.get('p', [])
    sig = ', '.join(
        f'{mapping.rewrite_type(p.get("t", "System.Object"))} {mapping.rewrite_identifier(p.get("n", f"p{i}"))}'
        for i, p in enumerate(params)
    )
    mod = 'public static' if is_static else 'public'
    is_ctor = False
    if method_name == '.ctor':
        java_name = inline_class_name
        ret_part = ''
        is_ctor = True
    elif method_name == '.cctor':
        java_name = 'staticInit'
        ret_part = f'{ret} '
    else:
        java_name = _camel_case_method(method_name)
        ret_part = f'{ret} '
    if is_ctor:
        throw_body = '    throw new UnsupportedOperationException("decompile failed");'
    elif ret == 'void':
        throw_body = '    // decompile failed'
    else:
        throw_body = '    throw new UnsupportedOperationException("decompile failed");'
    return (f'{mod} {ret_part}{java_name}({sig}) {{\n'
            f'    // TODO: decompile failed or stub (RVA 0x{rva:X})\n'
            f'{throw_body}\n'
            f'}}')


def _resolve_class_meta(class_fqn: str, mapping: Mapping) -> tuple[str, dict]:
    # Ghidra renames generic classes `Foo`1` -> `Foo_T1`. The C header uses the renamed
    # name but il2cpp metadata keys use the backtick form. Try a series of fallbacks.
    cls = mapping.il2cpp_classes.get(class_fqn)
    meta_fqn = class_fqn
    if cls is None:
        m = re.match(r'^(.*)_T(\d+)$', class_fqn)
        if m:
            candidate = f'{m.group(1)}`{m.group(2)}'
            cls = mapping.il2cpp_classes.get(candidate)
            if cls is not None:
                meta_fqn = candidate
    if cls is None:
        return class_fqn, {}
    # If this is a generic def (offsets all 0), also fetch one inflated instance and
    # return a merged view so fields carry real offsets.
    is_generic_def = bool(cls.get('gen')) or (
        cls.get('size') == 0 and cls.get('fields')
        and all(f.get('o', 0) == 0 for f in cls.get('fields', []))
    )
    if is_generic_def:
        inflated_names = mapping.inflated_by_def.get(meta_fqn, [])
        if inflated_names:
            inflated = mapping.il2cpp_classes.get(inflated_names[0], {})
            if inflated.get('fields'):
                merged = dict(cls)
                merged['fields'] = inflated['fields']
                merged['size'] = inflated.get('size', cls.get('size', 0))
                return meta_fqn, merged
    return meta_fqn, cls


def emit_class(class_fqn: str, methods: list[Method], mapping: Mapping) -> str:
    """Emit a complete Java class file: package + class declaration + fields + methods."""
    pkg = derive_package(class_fqn, mapping)
    sname = simple_class_name(class_fqn)
    meta_fqn, cls_meta = _resolve_class_meta(class_fqn, mapping)
    parent = cls_meta.get('parent')
    is_enum = class_fqn in mapping.il2cpp_enums or meta_fqn in mapping.il2cpp_enums

    extends = ''
    # `System.ValueType` is the C# base class for structs — Java has no equivalent; skip.
    # `System.Object` is Java's implicit superclass; skip.
    if parent and parent not in ('System.Object', 'System.ValueType', 'System.Enum'):
        extends = f' extends {mapping.rewrite_type(parent)}'

    simple_name = meta_fqn.rsplit('.', 1)[-1]
    # Prefer the exact flags from IL2CPP runtime (dump-il2cpp-full.js captures them).
    # Fall back to a name heuristic when the dump pre-dates the flag addition.
    if 'iface' in cls_meta:
        is_interface = bool(cls_meta.get('iface'))
    else:
        is_interface = (
            cls_meta.get('size') == 0
            and cls_meta.get('parent') is None
            and not cls_meta.get('fields')
            and len(simple_name) >= 2
            and simple_name[0] == 'I'
            and simple_name[1].isupper()
        )
    # `abs` is set on every interface — only mark `abstract` when the class is NOT an
    # interface (Java interfaces are implicitly abstract).
    is_abstract = bool(cls_meta.get('abs')) and not is_interface

    lines = [f'package {pkg};', '']

    if is_enum:
        enum_values = mapping.il2cpp_enums.get(class_fqn, {})
        lines.append(f'public enum {sname} {{')
        entries = [f'    {name}({value})' for value, name in enum_values.items()]
        lines.append(',\n'.join(entries) + ';')
        lines.append('    public final int value;')
        lines.append(f'    {sname}(int value) {{ this.value = value; }}')
        lines.append('}')
        return '\n'.join(lines)

    # We keep `public class` even for detected interfaces: the .c dump contains bodies
    # (vtable/trampoline thunks) which can't go on a Java interface. The detection is
    # kept as a marker comment.
    if is_interface:
        lines.append('// C# interface — emitted as class because the dump has bodies')
    cls_kw = 'public abstract class' if is_abstract else 'public class'
    lines.append(f'{cls_kw} {sname}{extends} {{')

    fields = cls_meta.get('fields', [])
    if fields:
        # Generic definitions have all offsets at 0 across ≥2 fields (concrete layout is
        # per-instantiation). A single field legitimately at offset 0 is not a generic marker.
        all_zero = len(fields) >= 2 and all(f.get('o', 0) == 0 for f in fields)
        lines.append('')
        if all_zero:
            lines.append('    // ===== Fields (generic def — offsets unresolved) =====')
        else:
            lines.append('    // ===== Fields (from il2cpp_full.json) =====')
        for f in fields:
            fname = f['n']
            ftype = mapping.rewrite_type(f['t'])
            offset = f.get('o', 0)
            clean_name = _clean_field_name(fname)
            if all_zero:
                lines.append(f'    public {ftype} {clean_name};')
            else:
                lines.append(f'    public {ftype} {clean_name};  // +0x{offset:x}')

    # Collect methods that belong to this top-level class (nested classes included)
    expected_rvas: dict[int, dict] = {}
    for rva, m_dict in mapping.il2cpp_methods.items():
        if _top_level_class_of(m_dict.get('d', ''), mapping) == class_fqn:
            expected_rvas[rva] = m_dict
    parsed_rvas = {m.rva for m in methods}
    missing_rvas = sorted(rva for rva in expected_rvas if rva not in parsed_rvas)

    if methods or missing_rvas:
        lines.append('')
        lines.append('    // ===== Methods (transpiled from Ghidra .c) =====')
        for m in methods:
            lines.append('')
            body = emit_method_skeleton(m, mapping, inline_class_name=sname)
            for ln in body.split('\n'):
                lines.append('    ' + ln if ln else '')
        if missing_rvas:
            lines.append('')
            lines.append('    // ===== Method stubs (decompile failed — signature from il2cpp_full.json) =====')
            for rva in missing_rvas:
                m_dict = expected_rvas[rva]
                lines.append('')
                body = emit_stub_method(rva, m_dict, mapping, sname)
                for ln in body.split('\n'):
                    lines.append('    ' + ln if ln else '')

    lines.append('}')
    return '\n'.join(lines)
