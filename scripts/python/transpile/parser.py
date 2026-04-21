"""tree-sitter parsing: Method dataclass, RVA headers, declarator extraction."""
from __future__ import annotations
import re
from pathlib import Path
import tree_sitter_c as tsc
from tree_sitter import Language, Node, Parser


# --- Tree-sitter singleton (threadsafe for single-process use) ---
_LANG = Language(tsc.language())
_PARSER = Parser(_LANG)


# Pattern to extract the RVA comment that precedes each method
_RVA_HEADER = re.compile(rb'//\s*===\s*(?P<fqn>[^(]+?)\s*\(RVA:\s*0x(?P<rva>[0-9A-Fa-f]+)\)\s*===')


def node_text(node: Node, src: bytes) -> str:
    return src[node.start_byte:node.end_byte].decode('utf-8', errors='replace')


def extract_rva_headers(src: bytes) -> list[tuple[str, int, int]]:
    """Return list of (fqn, rva, byte_offset) tuples for each // === marker."""
    out = []
    for m in _RVA_HEADER.finditer(src):
        fqn = m.group('fqn').decode('utf-8').strip()
        rva = int(m.group('rva').decode('utf-8'), 16)
        out.append((fqn, rva, m.end()))
    return out


class Method:
    """Parsed method signature + body AST node."""
    __slots__ = ('class_fqn', 'method_name', 'ghidra_name', 'return_type',
                 'params', 'body_node', 'src', 'rva')

    def __init__(self, class_fqn: str, method_name: str, ghidra_name: str,
                 return_type: str, params: list[tuple[str, str]],
                 body_node: Node | None, src: bytes, rva: int = 0):
        self.class_fqn = class_fqn
        self.method_name = method_name
        self.ghidra_name = ghidra_name
        self.return_type = return_type
        self.params = params
        self.body_node = body_node
        self.src = src
        self.rva = rva


def _split_class_method(csharp_fqn: str) -> tuple[str, str]:
    """`IdunBattle.AI.Playbook.HealPlaybook.CreateBehaviour` -> (class_fqn, method_name).
    Handles ctor `.ctor` and static ctor `.cctor`.
    """
    if csharp_fqn.endswith('..ctor'):
        return csharp_fqn[:-len('..ctor')], '.ctor'
    if csharp_fqn.endswith('..cctor'):
        return csharp_fqn[:-len('..cctor')], '.cctor'
    idx = csharp_fqn.rfind('.')
    if idx < 0:
        return '', csharp_fqn
    return csharp_fqn[:idx], csharp_fqn[idx+1:]


def _parse_declarator(declarator: Node, src: bytes) -> tuple[str, list[tuple[str, str]]]:
    """Recursively descend into nested declarators to extract name + params."""
    name = ''
    params: list[tuple[str, str]] = []

    def walk(n: Node):
        nonlocal name, params
        if n.type == 'function_declarator':
            inner_decl = n.child_by_field_name('declarator')
            param_list = n.child_by_field_name('parameters')
            if inner_decl:
                walk(inner_decl)
            if param_list:
                for p in param_list.children:
                    if p.type == 'parameter_declaration':
                        t_node = p.child_by_field_name('type')
                        d_node = p.child_by_field_name('declarator')
                        t = node_text(t_node, src) if t_node else ''
                        n_text = ''
                        cur = d_node
                        while cur is not None:
                            if cur.type == 'pointer_declarator':
                                t = t + '*'
                                cur = cur.child_by_field_name('declarator')
                            else:
                                n_text = node_text(cur, src)
                                break
                        params.append((t.strip(), n_text.strip()))
        elif n.type == 'identifier':
            name = node_text(n, src)
        elif n.type == 'pointer_declarator':
            inner = n.child_by_field_name('declarator')
            if inner:
                walk(inner)
        else:
            for c in n.children:
                walk(c)

    walk(declarator)
    return name, params


_WBARRIER_IDIOM = re.compile(
    rb'''(?P<ind>[ \t]*)
    (?P<ta>\w+)\s*=\s*(?P<fn>(?:thunk_)?FUN_[0-9a-f]+)\(\*\((?P<ty>[\w\s*]+?)\s*\*\)\((?P<src>\w+)\s*\+\s*(?P<off1>0x[0-9a-fA-F]+|\d+)\)\);\s*
    (?P<tb>\w+)\s*=\s*\*\((?P=ty)\s*\*\)\((?P=src)\s*\+\s*(?P=off1)\);\s*
    \*\((?P=ty)\s*\*\)\((?P<dst>\w+)\s*\+\s*(?P<off2>0x[0-9a-fA-F]+|\d+)\)\s*=\s*(?P=ta);\s*
    (?P<tail_ta>\w+\s*=\s*)?(?P=fn)\((?P=tb)\);
    ''',
    re.VERBOSE | re.DOTALL,
)
# Same idiom but with the leading thunk-call reduced to no args (Ghidra lost the arg).
_WBARRIER_IDIOM_NOARG = re.compile(
    rb'''(?P<ind>[ \t]*)
    (?P<ta>\w+)\s*=\s*(?P<fn>(?:thunk_)?FUN_[0-9a-f]+)\(\);\s*
    (?P<tb>\w+)\s*=\s*\*\((?P<ty>[\w\s*]+?)\s*\*\)\((?P<src>\w+)\s*\+\s*(?P<off1>0x[0-9a-fA-F]+|\d+)\);\s*
    \*\((?P=ty)\s*\*\)\((?P<dst>\w+)\s*\+\s*(?P<off2>0x[0-9a-fA-F]+|\d+)\)\s*=\s*(?P=ta);\s*
    (?P<tail_ta>\w+\s*=\s*)?(?P=fn)\((?P=tb)\);
    ''',
    re.VERBOSE | re.DOTALL,
)
_WBARRIER_TRAILING = re.compile(
    rb'(?P<ind>[ \t]*)\*\((?P<ty>[\w\s*]+?)\s*\*\)\((?P<dst>\w+)\s*\+\s*(?P<off>0x[0-9a-fA-F]+|\d+)\)\s*=\s*(?P<rhs>[^;]+?);\s*(?P<fn>(?:thunk_)?FUN_[0-9a-f]+)\(\);',
    re.DOTALL,
)


def _collapse_wbarrier_idiom(src: bytes) -> bytes:
    """IL2CPP generates 4-statement GC-write-barrier idioms for every reference store.
    Collapse them to a single `*dst = *src` assignment so the rest of the pipeline can
    resolve fields normally.
    Idiom (per reference field store):
        ta = thunk_FUN_X(*(T *)(SRC + N));
        tb = *(T *)(SRC + N);
        *(T *)(DST + N) = ta;
        thunk_FUN_X(tb);
    Becomes: `*(T *)(DST + N) = *(T *)(SRC + N);`
    """
    def _replace(m: re.Match) -> bytes:
        ind, ty, src, off1, dst, off2 = m.group('ind'), m.group('ty'), m.group('src'), m.group('off1'), m.group('dst'), m.group('off2')
        tail_ta = m.group('tail_ta')
        # If the final thunk call was assigned to a var, keep that assignment as a
        # pass-through so the temp is still defined for any later use.
        stmt = b'%s*(%s *)(%s + %s) = *(%s *)(%s + %s); /* wbarrier-collapsed */' % (
            ind, ty, dst, off2, ty, src, off1)
        if tail_ta:
            stmt += b'\n%s%s*(%s *)(%s + %s); /* was: last wbarrier retval */' % (
                ind, tail_ta, ty, src, off1)
        return stmt

    src = _WBARRIER_IDIOM.sub(_replace, src)
    src = _WBARRIER_IDIOM_NOARG.sub(_replace, src)

    def _trailing_replace(m: re.Match) -> bytes:
        # `*dst = rhs; thunk();` — drop the dangling zero-arg wbarrier call
        return b'%s*(%s *)(%s + %s) = %s; /* wbarrier-collapsed (trailing) */' % (
            m.group('ind'), m.group('ty'), m.group('dst'), m.group('off'), m.group('rhs'))

    src = _WBARRIER_TRAILING.sub(_trailing_replace, src)
    return src


def parse_file(path: Path) -> list[Method]:
    with open(path, 'rb') as f:
        src = f.read()
    src = _collapse_wbarrier_idiom(src)
    tree = _PARSER.parse(src)

    rva_headers = extract_rva_headers(src)

    def find_header_before(byte_offset: int) -> tuple[str, int] | None:
        best = None
        for fqn, rva, hdr_end in rva_headers:
            if hdr_end <= byte_offset:
                best = (fqn, rva)
            else:
                break
        return best

    methods: list[Method] = []
    for child in tree.root_node.children:
        if child.type != 'function_definition':
            continue
        header = find_header_before(child.start_byte)
        if header is None:
            continue
        csharp_fqn, rva = header

        declarator = child.child_by_field_name('declarator')
        body = child.child_by_field_name('body')
        ret_type_node = child.child_by_field_name('type')
        if declarator is None or body is None:
            continue

        ret_type = node_text(ret_type_node, src) if ret_type_node else 'void'
        ghidra_name, params = _parse_declarator(declarator, src)
        class_fqn, method_name = _split_class_method(csharp_fqn)

        methods.append(Method(
            class_fqn=class_fqn,
            method_name=method_name,
            ghidra_name=ghidra_name,
            return_type=ret_type,
            params=params,
            body_node=body,
            src=src,
            rva=rva,
        ))
    return methods
