"""
Generate Java classes (records + enums) mirroring IdunBattle.Configuration.BattleConfiguration
from the il2cpp_full.json dump, targeting the JSON shape of
data/seed-bc.json (seed BC template; regenere par dump_boards.py, cf. #159).

- Walks the type graph starting from BattleConfiguration
- Emits Java records for classes (regular + value types with >=1 field)
- Emits Java enums (with int values) for C# enums
- Maps C# namespace to Java package (lowercased, with safe renames)
- Handles: primitives, strings, arrays, Nullable<T>, List<T>, Dictionary<K,V>,
  SortedDictionary<K,V>, inheritance (parent fields included), value types.
"""
from __future__ import annotations
import json
import re
from pathlib import Path

ROOT = Path('C:/Users/nicolasv/tacticus-tools')
DUMP = ROOT / 'data' / 'il2cpp_full.json'
ENUM_ATTRS = ROOT / 'data' / 'enum_json_converter.json'
OUT_BASE = ROOT / 'app' / 'src' / 'main' / 'java'

ROOT_TYPE = 'IdunBattle.Configuration.BattleConfiguration'

NAMESPACE_MAP = {
    'IdunBattle.':       'tacticus.idunbattle.',
    'IdunBattleLogic.':  'tacticus.idunbattlelogic.',
    'IdunShared.':       'tacticus.idunshared.',
    'idun.Shared.':      'tacticus.idun.shared.',
    'idun.meta.':        'tacticus.idun.meta.',
    'Idun.Shared.':      'tacticus.idun.shared.',
}

JAVA_KEYWORD_PACKAGE_MAP = {
    'enum': 'enums', 'class': 'classes', 'interface': 'interfaces',
    'package': 'packages', 'abstract': 'abstract_', 'final': 'final_',
    'static': 'static_', 'native': 'native_', 'new': 'new_',
    'public': 'public_', 'private': 'private_', 'protected': 'protected_',
}

JAVA_RESERVED = {
    'abstract','assert','boolean','break','byte','case','catch','char','class',
    'const','continue','default','do','double','else','enum','extends','final',
    'finally','float','for','goto','if','implements','import','instanceof','int',
    'interface','long','native','new','package','private','protected','public',
    'return','short','static','strictfp','super','switch','synchronized','this',
    'throw','throws','transient','try','void','volatile','while','true','false',
    'null','var','yield','record'
}

PRIMITIVE_MAP = {
    'System.Boolean': 'boolean',
    'System.Byte': 'int',          # unsigned in C#, widen
    'System.SByte': 'byte',
    'System.Int16': 'short',
    'System.UInt16': 'int',
    'System.Int32': 'int',
    'System.UInt32': 'long',
    'System.Int64': 'long',
    'System.UInt64': 'long',
    'System.Single': 'float',
    'System.Double': 'double',
    'System.Char': 'char',
    'System.String': 'String',
    'System.Object': 'Object',
    'System.Void': 'void',
    'System.Decimal': 'java.math.BigDecimal',
    'System.DateTime': 'java.time.Instant',
    'System.Guid': 'java.util.UUID',
}

BOXED_MAP = {
    'boolean': 'Boolean', 'byte': 'Byte', 'short': 'Short',
    'int': 'Integer', 'long': 'Long', 'float': 'Float',
    'double': 'Double', 'char': 'Character',
}

# State accumulated during generation
emitted_classes: dict[str, dict] = {}  # fqn -> class dict
emitted_enums: dict[str, dict] = {}    # fqn -> enum dict
queued: set[str] = set()
skipped_missing: set[str] = set()


def split_generic(s: str) -> tuple[str, list[str]]:
    """Split `Outer<A, B<X,Y>>` into ('Outer', ['A', 'B<X,Y>'])."""
    m = re.match(r'^([\w.`+]+)<(.+)>$', s.strip())
    if not m:
        return s.strip(), []
    outer = m.group(1)
    inner = m.group(2)
    args = []
    depth = 0
    current = ''
    for ch in inner:
        if ch == '<':
            depth += 1
            current += ch
        elif ch == '>':
            depth -= 1
            current += ch
        elif ch == ',' and depth == 0:
            args.append(current.strip())
            current = ''
        else:
            current += ch
    if current.strip():
        args.append(current.strip())
    return outer, args


def strip_arity(name: str) -> str:
    return re.sub(r'`\d+', '', name)


def csharp_to_java_package(ns: str) -> str:
    """Map a C# namespace to a Java package (all lowercase, with keyword renames)."""
    for prefix, jp in NAMESPACE_MAP.items():
        if ns.startswith(prefix):
            rest = ns[len(prefix):]
            parts = rest.split('.') if rest else []
            out = jp
            for p in parts:
                if not p:
                    continue
                out += JAVA_KEYWORD_PACKAGE_MAP.get(p.lower(), p.lower()) + '.'
            return out.rstrip('.')
    parts = ns.split('.')
    out_parts = [JAVA_KEYWORD_PACKAGE_MAP.get(p.lower(), p.lower()) for p in parts]
    return 'tacticus.' + '.'.join(out_parts)


def split_fqn(fqn: str) -> tuple[str, str]:
    """Split a C# FQN into (namespace, simple_name). Nested types use + or ., we keep the last segment."""
    fqn = strip_arity(fqn)
    # Nested type: Outer.Inner with a suffix that is itself a simple identifier.
    # For BattleLogic we have things like "UnitSpawningOverTimeConfiguration.Wave".
    # We flatten nested: outer becomes the namespace directory, name is the inner.
    # Actually safer: take last dot-split segment as simple name.
    if '.' in fqn:
        ns, name = fqn.rsplit('.', 1)
    else:
        ns, name = '', fqn
    return ns, name


def java_class_name(fqn: str) -> str:
    """The simple Java class name for a C# FQN (nested types are flattened)."""
    _, name = split_fqn(fqn)
    return name


def java_fqn(fqn: str) -> str:
    ns, name = split_fqn(fqn)
    pkg = csharp_to_java_package(ns)
    return f'{pkg}.{name}'


def sanitize_identifier(s: str) -> str:
    """Convert a C# name (PascalCase) to a valid Java identifier. Preserves case."""
    # Remove invalid chars
    s = re.sub(r'[^A-Za-z0-9_]', '_', s)
    if not s:
        return '_'
    if s[0].isdigit():
        s = '_' + s
    if s in JAVA_RESERVED:
        s = s + '_'
    return s


def camel_case(name: str) -> str:
    """PascalCase -> camelCase."""
    if not name:
        return name
    if name.isupper():
        return name.lower()
    return name[0].lower() + name[1:]


def field_java_name(csharp: str) -> str:
    """Java field name preserving PascalCase so Jackson UPPER_CAMEL_CASE aligns
    with the Newtonsoft output. Sanitized if it is a Java keyword."""
    name = sanitize_identifier(csharp)
    return name


# ---- Type translation ----

def translate_type(ctype: str, enums: dict, classes: dict, box_primitive: bool = False) -> str:
    """Translate a C# type string to a Java type string. Also queues referenced
    classes/enums for emission."""
    ctype = ctype.strip()
    # Array: `T[]`
    if ctype.endswith('[]'):
        inner = translate_type(ctype[:-2], enums, classes, box_primitive=False)
        return inner + '[]'

    # Generic
    outer, args = split_generic(ctype)
    if args:
        outer_clean = strip_arity(outer)
        # Nullable<T> → boxed T
        if outer_clean in ('System.Nullable', 'Nullable'):
            inner = translate_type(args[0], enums, classes, box_primitive=True)
            return inner
        # Collections
        if outer_clean in ('System.Collections.Generic.List',
                           'System.Collections.Generic.IList',
                           'System.Collections.Generic.IEnumerable',
                           'System.Collections.Generic.ICollection',
                           'System.Collections.Generic.IReadOnlyList',
                           'System.Collections.Generic.IReadOnlyCollection'):
            inner = translate_type(args[0], enums, classes, box_primitive=True)
            return f'java.util.List<{inner}>'
        if outer_clean in ('System.Collections.Generic.HashSet',
                           'System.Collections.Generic.ISet'):
            inner = translate_type(args[0], enums, classes, box_primitive=True)
            return f'java.util.Set<{inner}>'
        if outer_clean in ('System.Collections.Generic.Dictionary',
                           'System.Collections.Generic.IDictionary',
                           'System.Collections.Generic.IReadOnlyDictionary',
                           'System.Collections.Generic.SortedDictionary'):
            k = translate_type(args[0], enums, classes, box_primitive=True)
            v = translate_type(args[1], enums, classes, box_primitive=True)
            # Jackson can only deserialize map keys that are primitives/strings or enums.
            # Record/class keys are downgraded to String (Newtonsoft writes them via ToString).
            if not (k in ('String', 'Integer', 'Long', 'Short', 'Byte', 'Boolean',
                          'Character', 'Float', 'Double')):
                # Is it an enum?
                raw_k = args[0].strip()
                # Unwrap Nullable
                ok, oargs = split_generic(raw_k)
                if strip_arity(ok) in ('System.Nullable', 'Nullable') and oargs:
                    raw_k = oargs[0]
                if raw_k not in enums and classes.get(raw_k, {}).get('parent') != 'System.Enum':
                    k = 'String'
            return f'java.util.Map<{k}, {v}>'
        if outer_clean in ('System.Collections.Generic.KeyValuePair',):
            k = translate_type(args[0], enums, classes, box_primitive=True)
            v = translate_type(args[1], enums, classes, box_primitive=True)
            return f'java.util.Map.Entry<{k}, {v}>'
        if outer_clean in ('System.Tuple',):
            return 'Object'
        # Unknown generic — just use raw name
        return java_fqn(outer_clean)

    # Primitives
    if ctype in PRIMITIVE_MAP:
        java = PRIMITIVE_MAP[ctype]
        if box_primitive:
            return BOXED_MAP.get(java, java)
        return java

    # Interface (IInputMessage etc.) — treat as Object polymorphic
    if ctype.startswith('IdunBattle.Messages.IInputMessage'):
        return 'Object'

    # Value-type structs with custom ToString that Newtonsoft serializes as string
    # (observed for TriggeredAbilityConfigId -> "EnvEndBombardment" etc.).
    if ctype == 'IdunShared.TriggeredAbilityConfigId':
        return 'String'

    # Enum or class in dump?
    if ctype in enums:
        evals = enums[ctype]
        # Empty enum (no values captured) → downgrade to Integer.
        if not any(not str(k).startswith('_') for k in evals):
            return 'Integer'
        queue_type(ctype, enums, classes)
        return java_fqn(ctype)
    if ctype in classes:
        cls = classes[ctype]
        parent = cls.get('parent', '')
        if parent == 'System.Enum':
            # No enum values available for this class-marked-as-enum → Integer.
            return 'Integer'
        queue_type(ctype, enums, classes)
        return java_fqn(ctype)

    # Unknown — mark and emit as Object (caller can fix up)
    skipped_missing.add(ctype)
    return 'Object /* ' + ctype + ' */'


def queue_type(fqn: str, enums: dict, classes: dict):
    if fqn in emitted_classes or fqn in emitted_enums:
        return
    if fqn in queued:
        return
    # Skip primitives, system
    if fqn in PRIMITIVE_MAP or fqn.startswith('System.'):
        return
    # Enum in dump (value map) OR class whose parent = System.Enum
    if fqn in enums:
        emitted_enums[fqn] = enums[fqn]
        return
    c = classes.get(fqn)
    if c is None:
        skipped_missing.add(fqn)
        return
    if c.get('parent') == 'System.Enum':
        # Try to find enum map by same name
        if fqn in enums:
            emitted_enums[fqn] = enums[fqn]
            return
        emitted_enums[fqn] = {}  # empty enum marker — just placeholder
        return
    # Skip dictionary-custom types that extend Dictionary
    queued.add(fqn)
    emitted_classes[fqn] = c


# ---- Emission ----

def collect_fields(fqn: str, classes: dict) -> list[dict]:
    """Return all fields (inherited + own), ordered by offset."""
    fields = []
    current = fqn
    while current and current not in ('System.Object', 'System.ValueType'):
        c = classes.get(current, {})
        fields = list(c.get('fields', [])) + fields
        parent = c.get('parent', '')
        if parent in ('System.Object', 'System.ValueType', ''):
            break
        if parent == 'System.Enum':
            break
        # Do not walk into collection/base library parents — their fields are impl details.
        if parent.startswith('System.Collections.') or parent.startswith('System.'):
            break
        current = parent
    # Stable sort by offset
    fields.sort(key=lambda f: f.get('o', 0))
    # Dedup by name (child overrides parent)
    seen = set()
    out = []
    for f in reversed(fields):
        n = f['n']
        if n in seen or n.startswith('<'):
            continue
        seen.add(n)
        out.append(f)
    out.reverse()
    return out


def emit_class(fqn: str, cls: dict, enums: dict, classes: dict) -> str:
    pkg = csharp_to_java_package(split_fqn(fqn)[0])
    simple = java_class_name(fqn)
    fields = collect_fields(fqn, classes)
    parent = cls.get('parent', '')

    # Dictionary-subclass (e.g., UtilitiesConfiguration) — no field info available,
    # emit as LinkedHashMap<String, Object> subclass so Jackson can deserialize generically.
    own_fields = cls.get('fields', [])
    if parent.startswith('System.Collections.Generic.Dictionary') and not own_fields:
        lines = []
        lines.append(f'package {pkg};')
        lines.append('')
        lines.append('import java.util.LinkedHashMap;')
        lines.append('')
        lines.append('/** Generated from IL2CPP dump: ' + fqn + ' (Dictionary subclass) */')
        lines.append(f'public class {simple} extends LinkedHashMap<String, Object> {{}}')
        return '\n'.join(lines) + '\n'

    # Translate fields once
    field_entries = []  # [(jtype, jname)]
    for f in fields:
        jtype = translate_type(f['t'], enums, classes, box_primitive=True)
        jname = field_java_name(f['n'])
        field_entries.append((jtype, jname))

    lines = []
    lines.append(f'package {pkg};')
    lines.append('')
    lines.append('import com.fasterxml.jackson.annotation.JsonIgnoreProperties;')
    lines.append('')
    lines.append('/** Generated from IL2CPP dump: ' + fqn + ' */')
    lines.append('@JsonIgnoreProperties(ignoreUnknown = true)')

    if not fields:
        lines.append(f'public record {simple}() {{}}')
        return '\n'.join(lines) + '\n'

    params = [f'    {jt} {jn}' for jt, jn in field_entries]
    body = ',\n'.join(params)

    # Single-field value-type structs are typically serialized as a plain scalar
    # by Newtonsoft (e.g., Idun.Shared.Level -> int). Emit a scalar-delegating
    # creator alongside the canonical record constructor.
    is_value_type = cls.get('vtype') == 1
    scalar_kind = None
    scalar_java_type = None
    if is_value_type and len(field_entries) == 1:
        jt = field_entries[0][0]
        if jt == 'String':
            scalar_kind, scalar_java_type = 'string', 'String'
        elif jt in ('Integer', 'Long', 'Short', 'Byte', 'Float', 'Double'):
            scalar_kind, scalar_java_type = 'number', jt
        elif jt == 'Boolean':
            scalar_kind, scalar_java_type = 'boolean', 'Boolean'

    lines.append(f'public record {simple}(')
    lines.append(body)
    if scalar_kind is None:
        lines.append(') {}')
    else:
        _, field_jname = field_entries[0]
        lines.append(') {')
        # Accessor override with @JsonValue — serializes the record as the scalar.
        lines.append(f'    @com.fasterxml.jackson.annotation.JsonValue')
        lines.append(f'    public {scalar_java_type} {field_jname}() {{ return {field_jname}; }}')
        lines.append('')
        lines.append('    @com.fasterxml.jackson.annotation.JsonCreator(mode = com.fasterxml.jackson.annotation.JsonCreator.Mode.DELEGATING)')
        if scalar_kind == 'string':
            lines.append(f'    public static {simple} fromString(String v) {{')
            lines.append(f'        return new {simple}(v);')
        elif scalar_kind == 'number':
            conv = {
                'Integer': 'intValue', 'Long': 'longValue', 'Short': 'shortValue',
                'Byte': 'byteValue', 'Float': 'floatValue', 'Double': 'doubleValue',
            }[scalar_java_type]
            lines.append(f'    public static {simple} fromNumber(java.lang.Number v) {{')
            lines.append(f'        return new {simple}(v == null ? null : v.{conv}());')
        else:
            lines.append(f'    public static {simple} fromBoolean(Boolean v) {{')
            lines.append(f'        return new {simple}(v);')
        lines.append('    }')
        lines.append('}')
    return '\n'.join(lines) + '\n'


def scalar_info(fqn: str, cls: dict, enums: dict, classes: dict) -> tuple[str, int, str] | None:
    """If this value-type record is typically serialized as a scalar by Newtonsoft,
    return (scalar_kind, field_index, field_java_type). scalar_kind is 'string',
    'number' or 'boolean'. None if not applicable."""
    if cls.get('vtype') != 1:
        return None
    fields = collect_fields(fqn, classes)
    if not fields:
        return None
    entries = []
    for f in fields:
        jt = translate_type(f['t'], enums, classes, box_primitive=True)
        entries.append(jt)
    num_types = {'Integer', 'Long', 'Short', 'Byte', 'Float', 'Double'}
    for i, jt in enumerate(entries):
        if jt == 'String':
            return ('string', i, jt)
    for i, jt in enumerate(entries):
        if jt in num_types:
            return ('number', i, jt)
    for i, jt in enumerate(entries):
        if jt == 'Boolean':
            return ('boolean', i, jt)
    return None


def emit_module(scalar_records: list[tuple[str, str, int, str, int]]) -> str:
    """Emit a single Jackson module that registers scalar-tolerant deserializers
    for value-type records that can bind from either an object or a scalar."""
    lines = []
    lines.append('package tacticus;')
    lines.append('')
    lines.append('import com.fasterxml.jackson.core.JsonParser;')
    lines.append('import com.fasterxml.jackson.core.JsonToken;')
    lines.append('import com.fasterxml.jackson.databind.DeserializationContext;')
    lines.append('import com.fasterxml.jackson.databind.JavaType;')
    lines.append('import com.fasterxml.jackson.databind.JsonDeserializer;')
    lines.append('import com.fasterxml.jackson.databind.deser.BeanDeserializerModifier;')
    lines.append('import com.fasterxml.jackson.databind.module.SimpleModule;')
    lines.append('')
    lines.append('/**')
    lines.append(' * Jackson module: handles Newtonsoft value-type structs that serialize as scalars.')
    lines.append(' * For each registered record, deserialization from a scalar JSON token fills the')
    lines.append(' * first compatible field; objects still go through the canonical record constructor.')
    lines.append(' */')
    lines.append('public final class TacticusConfigModule extends SimpleModule {')
    lines.append('    public TacticusConfigModule() {')
    lines.append('        setDeserializerModifier(new Modifier());')
    lines.append('    }')
    lines.append('')
    lines.append('    private static final class Modifier extends BeanDeserializerModifier {')
    lines.append('        @Override')
    lines.append('        public JsonDeserializer<?> modifyDeserializer(')
    lines.append('                com.fasterxml.jackson.databind.DeserializationConfig config,')
    lines.append('                com.fasterxml.jackson.databind.BeanDescription beanDesc,')
    lines.append('                JsonDeserializer<?> base) {')
    lines.append('            Class<?> raw = beanDesc.getBeanClass();')
    for fqn, kind, idx, jt, arity in scalar_records:
        pkg = csharp_to_java_package(split_fqn(fqn)[0])
        simple = java_class_name(fqn)
        full = f'{pkg}.{simple}'
        lines.append(f'            if (raw == {full}.class) return new ScalarOrObject<{full}>(base, {idx}, {arity}, "{kind}", {full}.class);')
    lines.append('            return base;')
    lines.append('        }')
    lines.append('    }')
    lines.append('')
    lines.append('    private static final class ScalarOrObject<T> extends JsonDeserializer<T> {')
    lines.append('        private final JsonDeserializer<?> base;')
    lines.append('        private final int fieldIndex;')
    lines.append('        private final int arity;')
    lines.append('        private final String kind;')
    lines.append('        private final Class<T> cls;')
    lines.append('        ScalarOrObject(JsonDeserializer<?> base, int fi, int ar, String k, Class<T> c) {')
    lines.append('            this.base = base; this.fieldIndex = fi; this.arity = ar; this.kind = k; this.cls = c;')
    lines.append('        }')
    lines.append('        @SuppressWarnings("unchecked")')
    lines.append('        @Override public T deserialize(JsonParser p, DeserializationContext ctx) throws java.io.IOException {')
    lines.append('            JsonToken t = p.currentToken();')
    lines.append('            if (t == JsonToken.START_OBJECT || t == JsonToken.START_ARRAY || t == JsonToken.VALUE_NULL) {')
    lines.append('                return (T) base.deserialize(p, ctx);')
    lines.append('            }')
    lines.append('            Object[] args = new Object[arity];')
    lines.append('            if (kind.equals("string")) args[fieldIndex] = p.getValueAsString();')
    lines.append('            else if (kind.equals("number")) args[fieldIndex] = p.getNumberValue();')
    lines.append('            else if (kind.equals("boolean")) args[fieldIndex] = p.getBooleanValue();')
    lines.append('            try {')
    lines.append('                java.lang.reflect.Constructor<?>[] ctors = cls.getDeclaredConstructors();')
    lines.append('                for (java.lang.reflect.Constructor<?> c : ctors) {')
    lines.append('                    if (c.getParameterCount() == arity) { c.setAccessible(true); return (T) c.newInstance(coerce(c, args)); }')
    lines.append('                }')
    lines.append('                throw new IllegalStateException("no ctor of arity " + arity + " on " + cls);')
    lines.append('            } catch (ReflectiveOperationException e) { throw new java.io.IOException(e); }')
    lines.append('        }')
    lines.append('        private Object[] coerce(java.lang.reflect.Constructor<?> c, Object[] args) {')
    lines.append('            Class<?>[] types = c.getParameterTypes();')
    lines.append('            Object[] out = new Object[args.length];')
    lines.append('            for (int i = 0; i < args.length; i++) {')
    lines.append('                Object v = args[i];')
    lines.append('                if (v == null) { out[i] = null; continue; }')
    lines.append('                Class<?> tgt = types[i];')
    lines.append('                if (v instanceof Number n) {')
    lines.append('                    if (tgt == Integer.class || tgt == int.class) out[i] = n.intValue();')
    lines.append('                    else if (tgt == Long.class || tgt == long.class) out[i] = n.longValue();')
    lines.append('                    else if (tgt == Short.class || tgt == short.class) out[i] = n.shortValue();')
    lines.append('                    else if (tgt == Byte.class || tgt == byte.class) out[i] = n.byteValue();')
    lines.append('                    else if (tgt == Float.class || tgt == float.class) out[i] = n.floatValue();')
    lines.append('                    else if (tgt == Double.class || tgt == double.class) out[i] = n.doubleValue();')
    lines.append('                    else out[i] = v;')
    lines.append('                } else out[i] = v;')
    lines.append('            }')
    lines.append('            return out;')
    lines.append('        }')
    lines.append('    }')
    lines.append('}')
    return '\n'.join(lines) + '\n'


def emit_enum(fqn: str, evals: dict) -> str:
    pkg = csharp_to_java_package(split_fqn(fqn)[0])
    simple = java_class_name(fqn)
    # Enums with [JsonConverter(StringEnumConverter)] serialize as name.
    name_serialized = fqn in ENUM_STRING_SERIALIZED

    lines = []
    lines.append(f'package {pkg};')
    lines.append('')
    lines.append('import com.fasterxml.jackson.annotation.JsonCreator;')
    if not name_serialized:
        lines.append('import com.fasterxml.jackson.annotation.JsonValue;')
    lines.append('')
    marker = ' [JsonConverter]' if name_serialized else ''
    lines.append('/** Generated from IL2CPP dump: ' + fqn + marker + ' */')
    lines.append(f'public enum {simple} {{')

    # Sort by numeric key, keep collision-safe on name
    entries = []
    seen_names = set()
    for k, v in evals.items():
        if k.startswith('_'):
            continue
        try:
            i = int(k)
        except ValueError:
            continue
        raw = str(v)
        name = sanitize_identifier(raw)
        if name in seen_names:
            name = f'{name}_{i}'
        seen_names.add(name)
        entries.append((i, name, raw))
    entries.sort(key=lambda e: e[0])

    if not entries:
        # Empty marker — emit a placeholder UNKNOWN enum
        lines.append('    UNKNOWN(0);')
    else:
        for idx, (i, name, raw) in enumerate(entries):
            sep = ',' if idx < len(entries) - 1 else ';'
            lines.append(f'    {name}({i}){sep}')

    lines.append('')
    lines.append('    private final int value;')
    lines.append(f'    {simple}(int value) {{ this.value = value; }}')
    if name_serialized:
        # Default enum serialization (name) is used — no @JsonValue needed.
        lines.append('    public int value() { return value; }')
    else:
        lines.append('    @JsonValue public int value() { return value; }')
    lines.append('    @JsonCreator public static ' + simple + ' fromValue(Object v) {')
    lines.append('        if (v == null) return null;')
    lines.append('        if (v instanceof Number n) {')
    lines.append('            int iv = n.intValue();')
    lines.append(f'            for ({simple} e : values()) if (e.value == iv) return e;')
    lines.append('            return null;')
    lines.append('        }')
    lines.append('        String s = v.toString();')
    lines.append(f'        for ({simple} e : values()) if (e.name().equals(s)) return e;')
    lines.append('        return null;')
    lines.append('    }')
    lines.append('}')
    return '\n'.join(lines) + '\n'


def main():
    print('Loading il2cpp dump...')
    with open(DUMP, 'r', encoding='utf-8') as f:
        dump = json.load(f)
    classes = dump['classes']
    enums = dump['enums']
    print(f'Classes: {len(classes)}, enums: {len(enums)}')

    # Load per-enum JsonConverter info (dumped via dump-enum-attrs.js).
    # Any enum in this map is serialized by Newtonsoft as its name() rather
    # than its int value.
    global ENUM_STRING_SERIALIZED
    ENUM_STRING_SERIALIZED = set()
    if ENUM_ATTRS.exists():
        with open(ENUM_ATTRS, 'r', encoding='utf-8') as f:
            data = json.load(f)
        ENUM_STRING_SERIALIZED = {k for k, v in data.items() if v.get('conv')}
        print(f'Enums with JsonConverter (name-serialized): {len(ENUM_STRING_SERIALIZED)}')

    # Seed
    queue_type(ROOT_TYPE, enums, classes)
    # Process queue: translating fields adds more types
    while True:
        pending = [fqn for fqn in list(emitted_classes) if fqn in queued]
        if not pending:
            break
        for fqn in pending:
            queued.discard(fqn)
            cls = emitted_classes[fqn]
            # Touch all fields to trigger dependency collection
            for f in collect_fields(fqn, classes):
                translate_type(f['t'], enums, classes, box_primitive=True)

    print(f'Classes to emit: {len(emitted_classes)}')
    print(f'Enums to emit:   {len(emitted_enums)}')
    if skipped_missing:
        print(f'Types with no dump entry (emitted as Object): {len(skipped_missing)}')
        for t in sorted(skipped_missing)[:30]:
            print(' ', t)

    # Write files
    written = 0
    for fqn, cls in emitted_classes.items():
        pkg = csharp_to_java_package(split_fqn(fqn)[0])
        simple = java_class_name(fqn)
        out_dir = OUT_BASE / Path(*pkg.split('.'))
        out_dir.mkdir(parents=True, exist_ok=True)
        src = emit_class(fqn, cls, enums, classes)
        (out_dir / f'{simple}.java').write_text(src, encoding='utf-8')
        written += 1

    # Emit a Jackson module that handles enums as map keys by name.
    # With @JsonValue returning int, Jackson's default enum KeyDeserializer expects
    # the int form, but Newtonsoft writes map keys as the enum name. This module
    # installs a generic name->enum KeyDeserializer for every emitted enum.
    mod_lines = [
        'package tacticus;',
        '',
        'import com.fasterxml.jackson.core.JsonGenerator;',
        'import com.fasterxml.jackson.databind.JsonSerializer;',
        'import com.fasterxml.jackson.databind.KeyDeserializer;',
        'import com.fasterxml.jackson.databind.SerializerProvider;',
        'import com.fasterxml.jackson.databind.module.SimpleModule;',
        '',
        '/** Registers name-based KeyDeserializer/Serializer for every generated enum. */',
        'public final class TacticusConfigModule extends SimpleModule {',
        '    public TacticusConfigModule() {',
    ]
    for fqn in emitted_enums.keys():
        pkg = csharp_to_java_package(split_fqn(fqn)[0])
        simple = java_class_name(fqn)
        mod_lines.append(f'        addKeyDeserializer({pkg}.{simple}.class, new NameOrValueKey<>({pkg}.{simple}.class));')
        mod_lines.append(f'        addKeySerializer({pkg}.{simple}.class, new NameKey());')
    mod_lines += [
        '    }',
        '',
        '    private static final class NameKey extends JsonSerializer<Enum<?>> {',
        '        @Override public void serialize(Enum<?> v, JsonGenerator g, SerializerProvider s) throws java.io.IOException {',
        '            g.writeFieldName(v == null ? "" : v.name());',
        '        }',
        '    }',
        '',
        '    private static final class NameOrValueKey<E extends Enum<E>> extends KeyDeserializer {',
        '        private final Class<E> cls;',
        '        NameOrValueKey(Class<E> cls) { this.cls = cls; }',
        '        @Override public Object deserializeKey(String key, com.fasterxml.jackson.databind.DeserializationContext ctx) {',
        '            if (key == null || key.isEmpty()) return null;',
        '            // Try by value (int): look for a public int-returning "value()" method',
        '            try {',
        '                int iv = Integer.parseInt(key);',
        '                for (E e : cls.getEnumConstants()) {',
        '                    try { int v = (int) cls.getMethod("value").invoke(e); if (v == iv) return e; }',
        '                    catch (ReflectiveOperationException ignore) { break; }',
        '                }',
        '            } catch (NumberFormatException ignore) { /* fall through */ }',
        '            // Try by name',
        '            try { return Enum.valueOf(cls, key); } catch (IllegalArgumentException ignore) { /* fall */ }',
        '            // Sanitized-name fallback (already how we emit)',
        '            return null;',
        '        }',
        '    }',
        '}',
    ]
    mod_dir = OUT_BASE / 'tacticus'
    mod_dir.mkdir(parents=True, exist_ok=True)
    (mod_dir / 'TacticusConfigModule.java').write_text('\n'.join(mod_lines) + '\n', encoding='utf-8')
    written += 1
    for fqn, evals in emitted_enums.items():
        pkg = csharp_to_java_package(split_fqn(fqn)[0])
        simple = java_class_name(fqn)
        out_dir = OUT_BASE / Path(*pkg.split('.'))
        out_dir.mkdir(parents=True, exist_ok=True)
        src = emit_enum(fqn, evals)
        (out_dir / f'{simple}.java').write_text(src, encoding='utf-8')
        written += 1
    print(f'Wrote {written} Java files under {OUT_BASE}')


if __name__ == '__main__':
    main()
