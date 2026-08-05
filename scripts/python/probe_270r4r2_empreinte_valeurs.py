"""#270-r4-r2 -- EMPREINTE value-preserving : la coupe des cycles n'a rien change des VALEURS.

Un recablage d'imports ne doit RIEN changer. On le prouve en hachant, pour tout module
d'`engine/`, la valeur de CHAQUE attribut de module ET de classe, puis en comparant a un
arbre TEMOIN extrait par `git archive` (arbre COMPLET, pas seulement `scripts/python` :
sans `data/`, les caches *lazy* alimentes par le gameconfig restent vides d'un seul cote
et rendent des divergences FAUSSES).

Deux pieges deja mesures dans ce depot, tous deux evites ici :
  * hacher la REPRESENTATION (`repr`) rougit sur `6` vs `<PathfinderType...: 6>` alors qu'un
    `IntEnum` EST un `int` -> on canonicalise par `int(x)`, RECURSIVEMENT dans les conteneurs ;
  * une LISTE de structures choisies ne peut pas montrer la valeur qu'elle a oubliee -> la
    portee est LARGE (tout attribut public de module et de classe).

Usage :
    python probe_270r4r2_empreinte_valeurs.py --emettre <fichier.json>
    python probe_270r4r2_empreinte_valeurs.py --comparer <temoin.json>
"""
from __future__ import annotations

import argparse
import hashlib
import importlib
import json
import pkgutil
import sys
from pathlib import Path

RACINE = Path(__file__).resolve().parent

_ATOMES = (bool, int, float, str, bytes, type(None))


def _canon(v, prof=0):
    """Canonicalise EN VALEUR. `int(x)` sur tout ce qui est un int (donc les IntEnum),
    recursivement dans les conteneurs. Ce qui n'est pas serialisable rend un marqueur de TYPE."""
    if prof > 6:
        return "<profondeur>"
    if isinstance(v, bool):
        return bool(v)
    if isinstance(v, int):
        return int(v)          # dissout IntEnum / IntFlag
    if isinstance(v, float):
        return "f:%.12g" % v
    if isinstance(v, (str, bytes, type(None))):
        return v.decode("utf-8", "replace") if isinstance(v, bytes) else v
    if isinstance(v, (list, tuple)):
        return [type(v).__name__] + [_canon(x, prof + 1) for x in v]
    if isinstance(v, (set, frozenset)):
        try:
            elems = sorted(_canon(x, prof + 1) for x in v)
        except TypeError:
            elems = sorted((repr(_canon(x, prof + 1)) for x in v))
        return [type(v).__name__] + elems
    if isinstance(v, dict):
        out = []
        for k in v:
            out.append([_canon(k, prof + 1), _canon(v[k], prof + 1)])
        try:
            out.sort(key=lambda p: repr(p[0]))
        except TypeError:
            pass
        return ["dict"] + out
    return "<%s>" % type(v).__name__


def _attributs(obj, prefixe: str, out: dict, prof: int) -> None:
    for nom in sorted(vars(obj) if hasattr(obj, "__dict__") else ()):
        if nom.startswith("__"):
            continue
        try:
            v = getattr(obj, nom)
        except Exception as e:                       # property qui leve, descripteur...
            out["%s.%s" % (prefixe, nom)] = "<ERR %s>" % type(e).__name__
            continue
        if isinstance(v, type):
            # CLASSE : on descend d'un cran (attributs de classe), une seule fois
            if prof == 0 and getattr(v, "__module__", "").startswith("engine"):
                _attributs(v, "%s.%s" % (prefixe, nom), out, prof + 1)
            out["%s.%s" % (prefixe, nom)] = "<class>"
            continue
        if callable(v) and not isinstance(v, _ATOMES):
            out["%s.%s" % (prefixe, nom)] = "<callable>"
            continue
        out["%s.%s" % (prefixe, nom)] = _canon(v)


def empreinte() -> dict:
    import engine
    mods = []
    for m in pkgutil.walk_packages(engine.__path__, prefix="engine."):
        mods.append(m.name)
    mods.append("engine")
    out: dict[str, object] = {}
    n_ok = n_ko = 0
    for nom in sorted(set(mods)):
        try:
            mod = importlib.import_module(nom)
        except Exception as e:
            out["!IMPORT!" + nom] = "%s: %s" % (type(e).__name__, e)
            n_ko += 1
            continue
        n_ok += 1
        _attributs(mod, nom, out, 0)
    out["!TEMOIN!modules_importes"] = n_ok
    out["!TEMOIN!modules_en_echec"] = n_ko
    out["!TEMOIN!attributs"] = len(out)
    return out


def _sha(d: dict) -> str:
    return hashlib.sha256(json.dumps(d, sort_keys=True, default=repr).encode("utf-8")).hexdigest()


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--emettre")
    ap.add_argument("--comparer")
    args = ap.parse_args()

    emp = empreinte()
    n_mod = emp["!TEMOIN!modules_importes"]
    n_ko = emp["!TEMOIN!modules_en_echec"]
    n_att = emp["!TEMOIN!attributs"]
    print("[270-r4-r2/empreinte] TEMOIN : %d modules importes, %d en echec, %d attributs haches"
          % (n_mod, n_ko, n_att))
    if n_mod == 0 or n_att < 100:
        print("[270-r4-r2/empreinte] ECHEC : portee VIDE ou derisoire -- un zero ne prouve RIEN")
        return 2

    if args.emettre:
        Path(args.emettre).write_text(json.dumps(emp, sort_keys=True, default=repr),
                                      encoding="utf-8")
        print("[270-r4-r2/empreinte] ecrit -> %s  (sha256 %s)" % (args.emettre, _sha(emp)[:16]))
        return 0

    if args.comparer:
        ref = json.loads(Path(args.comparer).read_text(encoding="utf-8"))
        cles = sorted((set(ref) | set(emp)) - {k for k in set(ref) | set(emp)
                                               if k.startswith("!TEMOIN!")})
        # TROIS categories, et une seule est une regression :
        #  * VALEUR  -- l'attribut existe des DEUX cotes et sa valeur a change -> ECHEC ;
        #  * APPARU  -- un NOM neuf au niveau module. C'est ce que produit un import HISSE
        #               (le nom importe devient attribut du module) : pas un changement de
        #               comportement, mais il doit etre LISTE, jamais tu ;
        #  * DISPARU -- un nom qui n'est plus la. Idem, liste.
        val, apparus, disparus = [], [], []
        for k in cles:
            a, b = ref.get(k, "<!ABSENT!>"), emp.get(k, "<!ABSENT!>")
            if a == b:
                continue
            if a == "<!ABSENT!>":
                apparus.append((k, b))
            elif b == "<!ABSENT!>":
                disparus.append((k, a))
            else:
                val.append((k, a, b))
        print("[270-r4-r2/empreinte] temoin : %s attributs / mesure : %s / compares : %d"
              % (ref.get("!TEMOIN!attributs"), n_att, len(cles)))
        print("[270-r4-r2/empreinte] NOMS apparus = %d, NOMS disparus = %d (effet attendu d'un "
              "import HISSE au niveau module)" % (len(apparus), len(disparus)))
        for k, b in apparus:
            print("   + %s = %s" % (k, repr(b)[:160]))
        for k, a in disparus:
            print("   - %s = %s" % (k, repr(a)[:160]))
        if val:
            print("[270-r4-r2/empreinte] ECHEC : %d divergence(s) de VALEUR" % len(val))
            for k, a, b in val[:60]:
                print("   %s\n      temoin : %s\n      mesure : %s" % (k, repr(a)[:200], repr(b)[:200]))
            return 1
        print("[270-r4-r2/empreinte] OK : 0 divergence de VALEUR sur %d attributs compares" % len(cles))
        return 0

    print("[270-r4-r2/empreinte] sha256 = %s" % _sha(emp))
    return 0


if __name__ == "__main__":
    sys.exit(main())
