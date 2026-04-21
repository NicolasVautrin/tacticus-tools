"""Walker: tree-sitter C AST → Java source for a single method body."""
from __future__ import annotations
import re
from tree_sitter import Node

from .mapping import Mapping
from .parser import Method, node_text, _split_class_method
from .naming import (
    _camel_case_method, _clean_field_name, _sanitize_label,
)


class Walker:
    """Walks a tree-sitter C AST and emits Java source for a single method.

    Dispatch: for a node of type X, look for `emit_X`. If not found, fall back
    to `emit_unknown` which emits a `// TODO` comment with the raw C source.
    """

    # Ghidra synthetic locals: unaff_xN (unaffiliated register), in_xN (incoming reg),
    # stack0xNNNNNNNN (stack spill), in_stack_NNNNNNNN (incoming stack arg), uStackN/lStackN
    _GHIDRA_SYNTHETIC_RE = re.compile(
        r'^(unaff_x\d+|in_x\d+|stack0x[0-9a-fA-F]+|in_stack_[0-9a-fA-F]+|'
        r'[ul]Stack[0-9a-fA-F]+|__return_storage_ptr__|__return_storage_ptr__[_0-9]*)$'
    )

    # Leaf statement types: check for synthetic usage, flag as TODO if present.
    _LEAF_STMT_TYPES = {
        'expression_statement', 'return_statement', 'goto_statement',
        'break_statement', 'continue_statement',
    }

    def __init__(self, src: bytes, mapping: Mapping, class_fqn: str | None = None,
                 method: Method | None = None):
        self.src = src
        self.m = mapping
        self.class_fqn = class_fqn
        self.method = method
        self.indent = 1
        self._synthetic_names: set[str] = set()
        self._field_rename: dict[str, str] = {}
        if class_fqn:
            self._build_field_rename(class_fqn)
        # ARM64 register alias: unaff_x19..unaff_x28 often hold caller-passed args
        # (x0..x9) saved in callee-saved registers. Empirically in IL2CPP-compiled code,
        # the first N of these match the method's N params 1:1.
        self._register_alias: dict[str, str] = self._build_register_alias()

    # ========== Initialisation helpers ==========

    def _build_register_alias(self) -> dict[str, str]:
        """ARM64 callee-saved register heuristic.

        Only `unaff_x19 → this` is reliable — the prologue typically saves x0 (the
        instance pointer) into x19 to preserve it across calls. The mapping
        `unaff_x20..x28 ≈ params[1..9]` is unreliable: the compiler freely uses
        these as temporaries, so aliasing them to parameters produces semantically
        wrong output (wrong types in assignments). We deliberately keep the mapping
        empty for those registers so the transpiler leaves them as `unaff_xN` and
        the reader can tell they're unresolved.
        """
        if self.method is None:
            return {}
        rva = self.method.rva
        il2 = self.m.il2cpp_methods.get(rva)
        if il2 is None:
            return {}
        if bool(il2.get('s')):
            return {}
        return {'unaff_x19': 'this'}

    def _build_field_rename(self, fqn: str) -> None:
        """Walk the inheritance chain and collect all field names, mapping to camelCase."""
        visited: set[str] = set()
        cur: str | None = fqn
        while cur and cur not in visited and cur != 'System.Object':
            visited.add(cur)
            cls = self.m.il2cpp_classes.get(cur)
            if not cls:
                break
            for f in cls.get('fields', []):
                csharp = f.get('n', '')
                if not csharp:
                    continue
                camel = _clean_field_name(csharp)
                if csharp != camel:
                    self._field_rename[csharp] = camel
            cur = cls.get('parent')

    # ========== Text helpers ==========

    def text(self, node: Node) -> str:
        return node_text(node, self.src)

    def ind(self) -> str:
        return '    ' * self.indent

    # ========== Public entry ==========

    def emit_body(self, body_node: Node, is_top: bool = False) -> str:
        """Emit the Java body."""
        if is_top:
            self._synthetic_names.clear()
            self._collect_synthetics(body_node)

        out: list[str] = []
        for ch in body_node.children:
            if ch.type in ('{', '}', 'comment'):
                continue
            s = self.emit_stmt(ch)
            if s is not None and s.strip():
                out.append(s)
        return '\n'.join(out)

    # ========== Synthetic-local tracking ==========

    def _collect_synthetics(self, node: Node):
        """Walk the AST, find declarations, mark synthetic local names."""
        if node.type == 'declaration':
            for ch in node.children:
                name = None
                if ch.type == 'init_declarator':
                    d = ch.child_by_field_name('declarator')
                    if d:
                        name = self._decl_name(d)
                elif ch.type in ('identifier', 'pointer_declarator'):
                    name = self._decl_name(ch)
                if name and self._is_ghidra_synthetic(name) and name not in self._register_alias:
                    # Alias-resolved names (e.g. unaff_x19 → this) are real params, not synthetic.
                    self._synthetic_names.add(name)
        for ch in node.children:
            self._collect_synthetics(ch)

    def _references_synthetic(self, node: Node) -> bool:
        """Check if any identifier in the subtree references a synthetic local.
        Alias-resolved names (unaff_xN → real param) are NOT synthetic.
        """
        if node.type == 'identifier':
            name = self.text(node)
            if name in self._register_alias:
                return False
            if name in self._synthetic_names:
                return True
            if self._is_ghidra_synthetic(name):
                return True
            return False
        for ch in node.children:
            if self._references_synthetic(ch):
                return True
        return False

    @classmethod
    def _is_ghidra_synthetic(cls, name: str) -> bool:
        return bool(cls._GHIDRA_SYNTHETIC_RE.match(name))

    # ========== Statements ==========

    def emit_stmt(self, node: Node) -> str | None:
        if node.type in self._LEAF_STMT_TYPES:
            if self._synthetic_names and self._references_synthetic(node):
                raw = self.text(node).replace('\n', ' ').strip()
                return f'{self.ind()}// TODO: uses Ghidra synthetic: {raw[:120]}'
        fn = getattr(self, f'emit_{node.type}', None)
        if fn is None:
            return self.emit_unknown(node)
        return fn(node)

    def emit_unknown(self, node: Node) -> str:
        raw = self.text(node).replace('\n', ' ').strip()
        return f'{self.ind()}// TODO: transpile {node.type}: {raw[:120]}'

    def emit_compound_statement(self, node: Node) -> str:
        self.indent += 1
        inner = self.emit_body(node)
        self.indent -= 1
        return f'{self.ind()}{{\n{inner}\n{self.ind()}}}'

    def emit_expression_statement(self, node: Node) -> str:
        for ch in node.children:
            if ch.type == ';':
                continue
            expr = self.emit_expr(ch)
            return f'{self.ind()}{expr};'
        return f'{self.ind()};'

    def emit_return_statement(self, node: Node) -> str:
        expr_node = None
        for ch in node.children:
            if ch.type in ('return', ';'):
                continue
            expr_node = ch
            break
        is_ctor = self.method is not None and self.method.method_name == '.ctor'
        if expr_node is None:
            return f'{self.ind()}return;'
        expr_str = self.emit_expr(expr_node)
        # Ctors in C#/IL2CPP return `this` by convention — Java ctors are void, so drop.
        if is_ctor:
            return f'{self.ind()}return; // drop: {expr_str}'
        return f'{self.ind()}return {expr_str};'

    def emit_if_statement(self, node: Node) -> str:
        cond_node = node.child_by_field_name('condition')
        cons_node = node.child_by_field_name('consequence')
        alt_node = node.child_by_field_name('alternative')
        cond = self.emit_expr(cond_node) if cond_node else 'true'
        cons = self.emit_stmt_as_block(cons_node) if cons_node else '{ }'
        result = f'{self.ind()}if ({cond}) {cons}'
        if alt_node is not None:
            else_stmt = alt_node
            for ch in alt_node.children:
                if ch.type not in ('else',):
                    else_stmt = ch
                    break
            alt_str = self.emit_stmt_as_block(else_stmt).lstrip()
            result += f' else {alt_str}'
        return result

    def emit_while_statement(self, node: Node) -> str:
        cond = node.child_by_field_name('condition')
        body = node.child_by_field_name('body')
        c = self.emit_expr(cond) if cond else 'true'
        b = self.emit_stmt_as_block(body) if body else '{ }'
        return f'{self.ind()}while ({c}) {b}'

    def emit_do_statement(self, node: Node) -> str:
        body = node.child_by_field_name('body')
        cond = node.child_by_field_name('condition')
        c = self.emit_expr(cond) if cond else 'true'
        b = self.emit_stmt_as_block(body) if body else '{ }'
        return f'{self.ind()}do {b} while ({c});'

    def emit_for_statement(self, node: Node) -> str:
        init = node.child_by_field_name('initializer')
        cond = node.child_by_field_name('condition')
        step = node.child_by_field_name('update')
        body = node.child_by_field_name('body')
        i = self.emit_expr(init) if init else ''
        c = self.emit_expr(cond) if cond else ''
        s = self.emit_expr(step) if step else ''
        b = self.emit_stmt_as_block(body) if body else '{ }'
        return f'{self.ind()}for ({i}; {c}; {s}) {b}'

    def emit_break_statement(self, node: Node) -> str:
        return f'{self.ind()}break;'

    def emit_continue_statement(self, node: Node) -> str:
        return f'{self.ind()}continue;'

    def emit_goto_statement(self, node: Node) -> str:
        label = ''
        for ch in node.children:
            if ch.type == 'statement_identifier':
                label = self.text(ch)
                break
        jlabel = _sanitize_label(label)
        return f'{self.ind()}// TODO: goto {jlabel};  — Java has no goto; convert to labeled break/continue'

    def emit_labeled_statement(self, node: Node) -> str:
        label = ''
        body = None
        for ch in node.children:
            if ch.type == 'statement_identifier':
                label = self.text(ch)
            elif ch.type == ':':
                continue
            else:
                body = ch
        jlabel = _sanitize_label(label)
        body_str = self.emit_stmt(body) if body is not None else ''
        return f'{self.ind()}{jlabel}:\n{body_str}'

    def emit_declaration(self, node: Node) -> str:
        """`Type var = expr;` or `Type var;`"""
        type_node = node.child_by_field_name('type')
        raw_ty = self.text(type_node) if type_node else ''
        ty = self.m.rewrite_type(raw_ty)
        parts: list[tuple[str, str | None]] = []
        for ch in node.children:
            if ch.type == 'init_declarator':
                name_node = ch.child_by_field_name('declarator')
                val_node = ch.child_by_field_name('value')
                name = self._decl_name(name_node) if name_node else '?'
                val = self.emit_expr(val_node) if val_node else None
                parts.append((name, val))
            elif ch.type in ('identifier', 'pointer_declarator'):
                name = self._decl_name(ch)
                parts.append((name, None))

        if not parts:
            return f'{self.ind()}// TODO: declaration {self.text(node)[:80]}'

        lines = []
        for name, val in parts:
            jname = self.m.rewrite_identifier(name)
            if self._is_ghidra_synthetic(name):
                if val:
                    lines.append(f'{self.ind()}// synthetic: {jname} = {val}  /* from Ghidra register analysis */')
                else:
                    lines.append(f'{self.ind()}// synthetic: {ty} {jname};')
                continue
            if val is not None:
                lines.append(f'{self.ind()}{ty} {jname} = {val};')
            else:
                lines.append(f'{self.ind()}{ty} {jname};')
        return '\n'.join(lines)

    def _decl_name(self, node: Node) -> str:
        """Drill through pointer_declarator layers to find the identifier."""
        cur = node
        while cur is not None:
            if cur.type == 'identifier':
                return self.text(cur)
            if cur.type == 'pointer_declarator':
                cur = cur.child_by_field_name('declarator')
            else:
                return self.text(cur).lstrip('*')
        return '?'

    def emit_stmt_as_block(self, node: Node) -> str:
        """Emit a single statement as a `{ ... }` block for if/while/for bodies."""
        if node.type == 'compound_statement':
            return self.emit_compound_statement(node)
        self.indent += 1
        inner = self.emit_stmt(node) or ''
        self.indent -= 1
        return f'{{\n{inner}\n{self.ind()}}}'

    # ========== Expressions ==========

    def emit_expr(self, node: Node) -> str:
        fn = getattr(self, f'expr_{node.type}', None)
        if fn is None:
            return self.expr_unknown(node)
        return fn(node)

    def expr_unknown(self, node: Node) -> str:
        raw = self.text(node).replace('\n', ' ').strip()
        return f'/* TODO_EXPR {node.type}: {raw[:80]} */'

    def expr_identifier(self, node: Node) -> str:
        name = self.text(node)
        if name in self._register_alias:
            return self._register_alias[name]
        return self.m.rewrite_identifier(name)

    def expr_number_literal(self, node: Node) -> str:
        return self.text(node)

    def expr_string_literal(self, node: Node) -> str:
        return self.text(node)

    def expr_char_literal(self, node: Node) -> str:
        return self.text(node)

    def expr_true(self, node: Node) -> str:
        return 'true'

    def expr_false(self, node: Node) -> str:
        return 'false'

    def expr_null(self, node: Node) -> str:
        return 'null'

    def expr_parenthesized_expression(self, node: Node) -> str:
        inner = None
        for ch in node.children:
            if ch.type not in ('(', ')'):
                inner = ch
                break
        return f'({self.emit_expr(inner)})' if inner else '()'

    def expr_binary_expression(self, node: Node) -> str:
        lhs = node.child_by_field_name('left')
        rhs = node.child_by_field_name('right')
        op_node = node.child_by_field_name('operator')
        op = self.text(op_node) if op_node else '?'
        # `base + offset` passed as an argument or assigned: try to interpret as field
        # access. If `base` is this/param and offset matches a known field, emit
        # `base.fieldName` — semantically the field (not its address, which Java can't
        # express anyway).
        if op == '+':
            resolved = self._try_resolve_field_deref(node)
            if resolved is not None:
                return resolved
        return f'{self.emit_expr(lhs)} {op} {self.emit_expr(rhs)}'

    def expr_unary_expression(self, node: Node) -> str:
        op_node = node.child_by_field_name('operator')
        arg = node.child_by_field_name('argument')
        op = self.text(op_node) if op_node else ''
        # Field-access pattern: *(T*)(base + offset) — emit `base.fieldName` when resolvable.
        if op == '*' and arg is not None:
            resolved = self._try_resolve_field_deref(arg)
            if resolved is not None:
                return resolved
        return f'{op}{self.emit_expr(arg)}' if arg else op

    def expr_pointer_expression(self, node: Node) -> str:
        """Tree-sitter-c emits `*expr` / `&expr` here (not unary_expression).
        Try the field-access pattern on `*` first, otherwise strip the operator
        (Java has no explicit dereference / address-of).
        """
        op = None
        operand = None
        for ch in node.children:
            if ch.type in ('*', '&') and op is None:
                op = ch.type
            elif ch.type not in ('*', '&'):
                operand = ch
        if op == '*' and operand is not None:
            resolved = self._try_resolve_field_deref(operand)
            if resolved is not None:
                return resolved
        if operand is not None:
            return self.emit_expr(operand)
        return op or ''

    def expr_cast_expression(self, node: Node) -> str:
        """`(Type)x` — Java cast: `(Type) x`. Drop pointer casts.
        If cast target is `Object` (i.e. void*, undefined*), drop it entirely.
        """
        type_node = node.child_by_field_name('type')
        val = node.child_by_field_name('value') or node.child_by_field_name('argument')
        ty_raw = self.text(type_node) if type_node else ''
        jt = self.m.rewrite_type(ty_raw) if ty_raw else 'Object'
        v = self.emit_expr(val) if val else ''
        if jt in ('Object', ''):
            return v
        return f'({jt}) {v}'

    def expr_update_expression(self, node: Node) -> str:
        arg = node.child_by_field_name('argument')
        op_node = node.child_by_field_name('operator')
        op = self.text(op_node) if op_node else '++'
        is_pre = node.children and node.children[0].type != (arg.type if arg else '')
        a = self.emit_expr(arg) if arg else ''
        return f'{op}{a}' if is_pre else f'{a}{op}'

    def expr_assignment_expression(self, node: Node) -> str:
        lhs = node.child_by_field_name('left')
        rhs = node.child_by_field_name('right')
        op_node = node.child_by_field_name('operator')
        op = self.text(op_node) if op_node else '='
        lhs_str = self.emit_expr(lhs)
        rhs_str = self.emit_expr(rhs)
        # Safety: Java forbids assignment to `this`, subscript-on-`this`, or the
        # unresolved `(base + offset)` pattern left behind when field lookup fails.
        if (lhs_str == 'this'
                or lhs_str.startswith('this[')
                or (lhs_str.startswith('(') and '+' in lhs_str)):
            return f'/* unresolved write: {lhs_str} {op} {rhs_str} */'
        return f'{lhs_str} {op} {rhs_str}'

    def expr_conditional_expression(self, node: Node) -> str:
        cond = node.child_by_field_name('condition')
        cons = node.child_by_field_name('consequence')
        alt = node.child_by_field_name('alternative')
        return f'{self.emit_expr(cond)} ? {self.emit_expr(cons)} : {self.emit_expr(alt)}'

    def expr_field_expression(self, node: Node) -> str:
        """`x->field` or `x.field` — both become `x.field` in Java.
        If `x` itself is a `(base + offset)` arithmetic expression, try to resolve
        it to the real field name first.
        """
        arg = node.child_by_field_name('argument')
        field_node = node.child_by_field_name('field')
        if arg is not None:
            resolved_obj = self._try_resolve_field_deref(arg)
            a = resolved_obj if resolved_obj is not None else self.emit_expr(arg)
        else:
            a = '?'
        f = self.text(field_node) if field_node else '?'
        java_name = self._field_rename.get(f, self.m.rewrite_identifier(f))
        return f'{a}.{java_name}'

    def expr_subscript_expression(self, node: Node) -> str:
        """`base[N]` is often field access in Ghidra void* output — treats `base` as
        an array of 8-byte pointers and `N` as the element index, i.e. `*(base + N*8)`.
        """
        arr = node.child_by_field_name('argument')
        idx_node = None
        seen_lbracket = False
        for ch in node.children:
            if ch.type == '[':
                seen_lbracket = True
                continue
            if ch.type == ']':
                break
            if seen_lbracket:
                idx_node = ch
                break
        if arr is not None and idx_node is not None and idx_node.type == 'number_literal':
            base_name = self.text(arr) if arr.type == 'identifier' else None
            if base_name in (self._register_alias or {}):
                base_name = self._register_alias[base_name]
            if base_name:
                try:
                    idx = int(self.text(idx_node), 0)
                except ValueError:
                    idx = None
                if idx is not None:
                    cls_fqn = self._resolve_param_class(base_name)
                    if cls_fqn:
                        fname = self._field_at_offset(cls_fqn, idx * 8)
                        if fname is not None:
                            return f'{base_name}.{_clean_field_name(fname)}'
        a = self.emit_expr(arr) if arr else '?'
        i = self.emit_expr(idx_node) if idx_node else '0'
        return f'{a}[{i}]'

    def expr_sizeof_expression(self, node: Node) -> str:
        return '/* TODO: sizeof not supported in Java */ 0'

    def expr_comma_expression(self, node: Node) -> str:
        parts = [self.emit_expr(ch) for ch in node.children if ch.type != ',']
        return ', '.join(parts)

    # ========== Call resolution ==========

    def expr_call_expression(self, node: Node) -> str:
        fn_node = node.child_by_field_name('function')
        args_node = node.child_by_field_name('arguments')
        fn_text = self.text(fn_node) if fn_node else '?'

        args: list[str] = []
        if args_node is not None:
            for a in args_node.children:
                if a.type in ('(', ')', ','):
                    continue
                args.append(self.emit_expr(a))

        # `(type)(expr)` parses as a call on `(type)` when `type` is not a known C
        # primitive (e.g. `ulong`, `ushort`). Detect and emit as cast.
        m = re.match(r'^\((\w[\w\s*]*)\)$', fn_text.strip())
        if m and len(args) == 1:
            jt = self.m.rewrite_type(m.group(1))
            if jt and jt != 'Object':
                return f'({jt}) {args[0]}'
            return args[0]

        method = self._resolve_call_to_method(fn_text)
        if method is not None:
            return self._emit_resolved_call(method, args)

        if fn_text in self.m.il2cpp_runtime:
            mapped = self.m.il2cpp_runtime[fn_text]
            if mapped.startswith('/*'):
                return f'/* {fn_text} elided */'
            return f'{mapped}({", ".join(args)})'

        if fn_text.startswith('FUN_') or fn_text.startswith('thunk_FUN_'):
            return f'{fn_text}({", ".join(args)}) /* unresolved */'
        return f'{fn_text}({", ".join(args)})'

    def _resolve_call_to_method(self, fn_text: str) -> dict | None:
        if fn_text.startswith('FUN_') or fn_text.startswith('thunk_FUN_'):
            hex_part = (fn_text[len('thunk_FUN_'):] if fn_text.startswith('thunk_FUN_')
                        else fn_text[len('FUN_'):])
            try:
                rva = int(hex_part, 16)
            except ValueError:
                return None
            return self.m.il2cpp_methods.get(rva)
        return self._resolve_by_dot_splits(fn_text)

    def _resolve_by_dot_splits(self, fn_text: str) -> dict | None:
        """Try splitting underscores progressively to find a matching FQN in the dump."""
        normalized = fn_text.replace('__', '\x01')
        underscore_positions = [i for i, c in enumerate(normalized) if c == '_']
        n = len(underscore_positions)

        def try_split(keep_last_k_underscores: int) -> dict | None:
            chars = list(normalized)
            for i, pos in enumerate(underscore_positions):
                if i >= n - keep_last_k_underscores:
                    continue
                chars[pos] = '.'
            candidate = ''.join(chars).replace('\x01', '.')
            entries = self.m.methods_by_fqn.get(candidate)
            if entries:
                return entries[0]
            if '.' in candidate:
                parts = candidate.rsplit('.', 2)
                if len(parts) >= 2:
                    suffix = '.'.join(parts[-2:])
                    entries = self.m.methods_by_suffix.get(suffix)
                    if entries:
                        return entries[0]
            return None

        for k in range(0, n + 1):
            hit = try_split(k)
            if hit is not None:
                return hit

        if '__' in fn_text:
            idx = fn_text.rfind('__')
            class_simple = fn_text[:idx]
            method_name = fn_text[idx + 2:]
            for suffix in (f'{class_simple}.{method_name}', f'{class_simple.replace("_", ".")}.{method_name}'):
                entries = self.m.methods_by_suffix.get(suffix)
                if entries:
                    return entries[0]
        return None

    def _emit_resolved_call(self, method: dict, args: list[str]) -> str:
        """Emit `receiver.methodName(args)` for instance, `Class.methodName(args)` for static."""
        fqn = method.get('n', '')
        is_static = bool(method.get('s'))
        class_fqn, method_simple = _split_class_method(fqn)
        method_java = _camel_case_method(method_simple)

        if fqn in self.m.fix64:
            return f'{self.m.fix64[fqn]}({", ".join(args)})'
        if fqn in self.m.system_methods:
            return f'{self.m.system_methods[fqn]}({", ".join(args)})'
        parts = fqn.rsplit('.', 1)
        if len(parts) == 2:
            outer_simple = parts[0].split('.')[-1].split('`')[0]
            key = f'{outer_simple}.{parts[1]}'
            if key in self.m.collection_methods:
                mapped = self.m.collection_methods[key]
                if is_static:
                    return f'{self.m.rewrite_type(class_fqn)}.{mapped}({", ".join(args)})'
                if args:
                    return f'{args[0]}.{mapped}({", ".join(args[1:])})'
                return f'{mapped}()'

        if is_static:
            java_class = self.m.rewrite_type(class_fqn)
            return f'{java_class}.{method_java}({", ".join(args)})'

        if not args:
            # No explicit receiver — if we're inside the same top-level class, assume `this`.
            if self.class_fqn and class_fqn == self.class_fqn:
                return f'this.{method_java}()'
            return f'{method_java}() /* orphan instance call */'
        receiver = args[0]
        return f'{receiver}.{method_java}({", ".join(args[1:])})'

    # ========== Field-access resolution ==========

    def _try_resolve_field_deref(self, arg: Node) -> str | None:
        """Match `(T *)(base + offset)` or `(base + offset)` or `base + offset` →
        `base.javaFieldName` when base is `this`/aliased param and il2cpp_classes has
        a field at that offset on base's C# type.
        """
        inner = arg
        for _ in range(4):
            if inner is None:
                return None
            if inner.type == 'parenthesized_expression':
                for ch in inner.children:
                    if ch.type not in ('(', ')'):
                        inner = ch
                        break
                continue
            if inner.type == 'cast_expression':
                v = inner.child_by_field_name('value') or inner.child_by_field_name('argument')
                inner = v
                continue
            break
        if inner is None or inner.type != 'binary_expression':
            return None
        op_node = inner.child_by_field_name('operator')
        if op_node is None or self.text(op_node) != '+':
            return None
        lhs = inner.child_by_field_name('left')
        rhs = inner.child_by_field_name('right')
        if lhs is None or rhs is None:
            return None
        # Peel (long) / (void *) / etc. from the lhs
        peeled_lhs = lhs
        for _ in range(3):
            if peeled_lhs.type == 'parenthesized_expression':
                for ch in peeled_lhs.children:
                    if ch.type not in ('(', ')'):
                        peeled_lhs = ch
                        break
                continue
            if peeled_lhs.type == 'cast_expression':
                v = peeled_lhs.child_by_field_name('value') or peeled_lhs.child_by_field_name('argument')
                if v is None:
                    break
                peeled_lhs = v
                continue
            break
        if peeled_lhs.type != 'identifier' or rhs.type != 'number_literal':
            return None
        base_name = self.text(peeled_lhs)
        if base_name in self._register_alias:
            base_name = self._register_alias[base_name]
        try:
            offset = int(self.text(rhs), 0)
        except ValueError:
            return None
        cls_fqn = self._resolve_param_class(base_name)
        if cls_fqn is None:
            return None
        fname = self._field_at_offset(cls_fqn, offset)
        if fname is None:
            return None
        return f'{base_name}.{_clean_field_name(fname)}'

    def _resolve_param_class(self, base_name: str) -> str | None:
        """Given 'this' or a real param name, return the C# class FQN of its type."""
        if self.method is None:
            return None
        if base_name == 'this':
            return self.method.class_fqn
        il2 = self.m.il2cpp_methods.get(self.method.rva)
        if il2 is None:
            return None
        for p in il2.get('p', []):
            if p.get('n') == base_name:
                t = p.get('t', '')
                return t.split('<', 1)[0].rstrip('*&') if t else None
        return None

    def _field_at_offset(self, cls_fqn: str, offset: int) -> str | None:
        """Walk inheritance chain to find the field at `offset` on `cls_fqn`.
        Fallbacks:
        - generic def (all fields at 0) → any inflated instance of the same def
        - interface (no fields) → concrete impl with same name minus leading `I`
        """
        cur: str | None = cls_fqn
        visited: set[str] = set()
        saw_any_real_offset = False
        while cur and cur not in visited and cur != 'System.Object':
            visited.add(cur)
            cls = self.m.il2cpp_classes.get(cur)
            if cls is None:
                # Generic def on parent chain — swap for an inflated instance.
                inflated = self.m.inflated_by_def.get(cur)
                if inflated:
                    cls = self.m.il2cpp_classes.get(inflated[0])
                    cur = inflated[0]
                if cls is None:
                    break
            for f in cls.get('fields', []):
                if f.get('o', 0) > 0:
                    saw_any_real_offset = True
                if f.get('o') == offset:
                    return f.get('n')
            # If this level is a generic def (size 0, all fields at 0), try inflated.
            is_generic_def = bool(cls.get('gen')) or (
                cls.get('size') == 0 and cls.get('fields')
                and all(f.get('o', 0) == 0 for f in cls.get('fields', []))
            )
            if is_generic_def:
                for inflated_name in self.m.inflated_by_def.get(cur, []):
                    inflated = self.m.il2cpp_classes.get(inflated_name, {})
                    for f in inflated.get('fields', []):
                        if f.get('o') == offset:
                            return f.get('n')
            cur = cls.get('parent')
        # Interface fallback: no field with a real offset anywhere in the chain, and
        # the name starts with `I<Upper>`.
        if not saw_any_real_offset:
            concrete = self._concrete_impl_for_interface(cls_fqn)
            if concrete is not None:
                return self._field_at_offset(concrete, offset)
        return None

    def _concrete_impl_for_interface(self, cls_fqn: str) -> str | None:
        """Heuristic: for `Ns.IFoo`, return `Ns.Foo` if present in il2cpp_classes."""
        parts = cls_fqn.rsplit('.', 1)
        if len(parts) != 2:
            return None
        ns, simple = parts
        if len(simple) < 2 or simple[0] != 'I' or not simple[1].isupper():
            return None
        candidate = f'{ns}.{simple[1:]}'
        if candidate in self.m.il2cpp_classes:
            return candidate
        return None
