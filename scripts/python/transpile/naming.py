"""Name-mangling helpers: camelCase conversion, Java keyword handling, generic splitting."""
from __future__ import annotations
import re


_JAVA_KEYWORDS_FOR_METHODS = {
    'if', 'else', 'for', 'while', 'do', 'switch', 'case', 'default', 'break',
    'continue', 'return', 'new', 'class', 'interface', 'enum', 'extends',
    'implements', 'throw', 'throws', 'try', 'catch', 'finally', 'static',
    'final', 'abstract', 'native', 'synchronized', 'volatile', 'transient',
    'public', 'private', 'protected', 'package', 'import', 'instanceof',
    'this', 'super', 'null', 'true', 'false', 'void', 'int', 'long', 'short',
    'byte', 'char', 'boolean', 'float', 'double', 'const', 'goto', 'assert',
}

# Java keywords used in field-name sanitisation — broader set including all reserved words.
_JAVA_KEYWORDS_FIELDS = {
    'abstract', 'assert', 'boolean', 'break', 'byte', 'case', 'catch',
    'char', 'class', 'const', 'continue', 'default', 'do', 'double',
    'else', 'enum', 'extends', 'final', 'finally', 'float', 'for',
    'goto', 'if', 'implements', 'import', 'instanceof', 'int',
    'interface', 'long', 'native', 'new', 'null', 'package',
    'private', 'protected', 'public', 'return', 'short', 'static',
    'strictfp', 'super', 'switch', 'synchronized', 'this', 'throw',
    'throws', 'transient', 'true', 'false', 'try', 'void', 'volatile',
    'while', 'yield', 'var', 'record', 'sealed', 'permits', 'non-sealed',
}

_PRIMITIVE_WRAPPERS = {
    'byte': 'Byte', 'short': 'Short', 'int': 'Integer', 'long': 'Long',
    'float': 'Float', 'double': 'Double', 'char': 'Character', 'boolean': 'Boolean',
    'void': 'Void',
}

_BACKING_FIELD_RE = re.compile(r'^<(\w+)>k__BackingField$')


def _camel_case_method(name: str) -> str:
    """PascalCase method name → camelCase. Handles special cases like `.ctor`/`.cctor`.
    Java keyword method names get a trailing underscore to avoid syntax errors.
    """
    if name == '.ctor':
        return '<init>'  # replaced by caller with the constructor name
    if name == '.cctor':
        return 'staticInit'
    if name.startswith('get_') and len(name) > 4:
        return 'get' + name[4:]
    if name.startswith('set_') and len(name) > 4:
        return 'set' + name[4:]
    name = re.sub(r'`\d+', '', name)
    if name and name[0].isupper():
        name = name[0].lower() + name[1:]
    if name in _JAVA_KEYWORDS_FOR_METHODS:
        name += '_'
    return name


def _primitive_to_wrapper(t: str) -> str:
    """In Java generics, primitives must be wrapped: int -> Integer, etc."""
    return _PRIMITIVE_WRAPPERS.get(t, t)


def _split_generic_args(s: str) -> list[str]:
    """Split `A, B, C<D, E>, F[]` at top-level commas only."""
    out = []
    depth = 0
    cur: list[str] = []
    for ch in s:
        if ch == '<':
            depth += 1
            cur.append(ch)
        elif ch == '>':
            depth -= 1
            cur.append(ch)
        elif ch == ',' and depth == 0:
            out.append(''.join(cur).strip())
            cur = []
        else:
            cur.append(ch)
    if cur:
        out.append(''.join(cur).strip())
    return out


def _sanitize_label(label: str) -> str:
    """FUN_0320ae24 or LAB_02b1fa1c → label_<addr>."""
    for prefix in ('FUN_', 'LAB_', 'switchD_'):
        if label.startswith(prefix):
            return f'label_{label[len(prefix):]}'
    return 'label_' + re.sub(r'[^A-Za-z0-9_]', '_', label)


def _clean_field_name(csharp_name: str) -> str:
    """Convert C# field name to Java camelCase.

    - `<Foo>k__BackingField` → `foo`
    - `MyField` → `myField`
    - `_internal` → `_internal` (leading underscore preserved)
    - field that's a Java keyword → suffixed with `_`
    """
    m = _BACKING_FIELD_RE.match(csharp_name)
    if m:
        n = m.group(1)
    else:
        n = csharp_name
    # Preserve leading underscore(s): _foo → _foo, __bar → __bar
    leading = ''
    i = 0
    while i < len(n) and n[i] == '_':
        leading += '_'
        i += 1
    body = n[i:]
    # Detect UPPER_SNAKE_CASE constants (MIN_UTILITY, MAX_VALUE, PI, etc.) — keep them intact
    is_constant = bool(body) and body.isupper() and (
        '_' in body or len(body) <= 2 or all(c.isupper() or c.isdigit() or c == '_' for c in body)
    )
    if not is_constant and body and body[0].isupper():
        body = body[0].lower() + body[1:]
    out = leading + body
    out = re.sub(r'[^A-Za-z0-9_]', '_', out)
    if out in _JAVA_KEYWORDS_FIELDS:
        out += '_'
    return out


def _csharp_to_camel_field(csharp_name: str) -> str:
    """Thin alias — used when we need the camelCase Java field name from a C# identifier."""
    return _clean_field_name(csharp_name)
