"""One-shot: peek inside the en.resource bundle to see how strings are stored."""
import UnityPy

import build_pin

UnityPy.config.FALLBACK_UNITY_VERSION = "6000.3.8f1"

# Racine d'installation : le build INSTALLE (`TACTICUS_INSTALL` reste l'echappatoire).
# Le defaut etait `nb3o9lmt6c`, un build desinstalle depuis longtemps -- le glob rendait
# alors zero bundle, ce qui se lit comme « pas de langue » (#431).
INSTALL = build_pin.install_dir()
src = INSTALL / "Tacticus_Data/StreamingAssets/Bundles/languages"
en_bundle = next(src.glob("en_*.resource"), None)
if not en_bundle:
    raise SystemExit(f"no en bundle in {src}")

print(f"loading {en_bundle.name}")
env = UnityPy.load(str(en_bundle))
print(f"objects: {len(env.objects)}")
for obj in env.objects[:30]:
    print(f"  {obj.type.name}", end="")
    try:
        d = obj.read()
        nm = getattr(d, "m_Name", "") or getattr(d, "name", "")
        print(f"  m_Name={nm!r}", end="")
    except Exception as exc:
        print(f"  read-fail: {exc}", end="")
    print()

# I2 Localization MonoBehaviour — read typetree to get the term table.
mb = next((o for o in env.objects if o.type.name == "MonoBehaviour"), None)
if mb:
    tree = mb.read_typetree()
    print(f"\n=== typetree top-level keys ===")
    for k in tree:
        v = tree[k]
        if isinstance(v, list):
            print(f"  {k}: list[{len(v)}]")
        elif isinstance(v, dict):
            print(f"  {k}: dict({list(v.keys())[:5]}…)")
        else:
            preview = str(v)[:80]
            print(f"  {k}: {preview}")
    # Sample a term
    src = tree.get("mSource") or {}
    terms = src.get("mTerms") or []
    print(f"\n=== mTerms count: {len(terms)} ===")
    if terms:
        sample = terms[0]
        print(f"\n=== sample term ===")
        for k, v in sample.items():
            preview = str(v)[:120]
            print(f"  {k}: {preview}")
        # Find a buff term to check format
        rapid_terms = [t for t in terms
                       if isinstance(t.get("Term"), str)
                       and "rapidassault" in t["Term"].lower()]
        if rapid_terms:
            print(f"\n=== {len(rapid_terms)} rapid_assault terms ===")
            for t in rapid_terms[:5]:
                langs = t.get("Languages", [])
                first_str = next((x for x in langs if isinstance(x, str)), None)
                print(f"  {t['Term']!r} → {first_str!r}")
