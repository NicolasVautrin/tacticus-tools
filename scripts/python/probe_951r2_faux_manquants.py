"""#951-r2 -- RECENSEUR des FAUX MANQUANTS des deux audits de couverture.

Question posee : combien d'entrees comptees MANQUANTES par `kit-coverage.md` /
`combat-ability-coverage.md` sont en realite PORTEES (ou n'ont RIEN a porter) ?

⚠ METHODE -- ce probe n'enumere PAS une liste blanche de registres. La lecon de #323
(`unit_map find --ability` lisait 2 voies d'attribution sur 5 et rendait des zeros qui ont fait
classer du vivant en DEAD) vaut a l'identique ici, sur l'axe PORT au lieu de l'axe ATTRIBUTION :
un recenseur qui n'interroge que les registres qu'il connait ne peut pas voir la voie qu'il a
oubliee -- et c'est exactement le mode de defaillance mesure sur `FireOfAbsolution`.

Il procede donc par INTROSPECTION EXHAUSTIVE :
  * il importe TOUS les modules `engine.**` (430 s'importent seuls, cf. CLAUDE.md) ;
  * pour chacun, il visite TOUT attribut de module qui est un conteneur (dict/set/list/tuple),
    aplati recursivement, et regarde si le NOM ou l'ID de l'item y figure -- donc tout registre,
    connu ou non, decouvert par sa FORME et pas par son nom ;
  * il visite en plus les SYMBOLES DEFINIS (def/class) dont le nom contient le nom de l'item en
    snake_case -- c'est la voie IMPERATIVE, qui n'a par construction aucun registre
    (`_fire_of_absolution_after_attack`).

Une trace n'est pas une preuve de cablage : c'est un CANDIDAT a trancher site par site. Zero
trace, en revanche, est un signal fort de vrai manquant.

Sortie ASCII. Usage : depuis `scripts/python/`
    python probe_951r2_faux_manquants.py [--detail]
"""
from __future__ import annotations

import importlib
import os
import pkgutil
import re
import sys
from collections import defaultdict

_PYROOT = os.path.dirname(os.path.abspath(__file__))
_REPO = os.path.dirname(os.path.dirname(_PYROOT))
if _PYROOT not in sys.path:
    sys.path.insert(0, _PYROOT)

import audit_kit_coverage as AKC             # noqa: E402
import audit_combat_ability_coverage as ACAC  # noqa: E402
import enum_maps as EM                       # noqa: E402

_ENGINE = os.path.join(_PYROOT, "engine")
_DOCS = os.path.join(_REPO, "docs", "rl")

#: les modules dont le contenu est un MIROIR D'ENUM (tout nom d'ability y figure par
#: construction) -- les compter comme registre rendrait 100 % de faux candidats.
MIROIRS = {
    "engine.entities.active_ability_type",
    "engine.entities.effect_type",
    "engine.entities.triggered_ability_type",
    "engine.entities.traits.unit_trait",
    "engine.dsl.event_trigger_type",
    "engine.entities.abilities.ability_constant_type",
    "engine.entities.abilities.ability_variable_type",
}


def _snake(nm: str) -> str:
    s = re.sub(r"(.)([A-Z][a-z]+)", r"\1_\2", nm)
    return re.sub(r"([a-z0-9])([A-Z])", r"\1_\2", s).lower()


def _docs() -> list[tuple[str, str]]:
    out = []
    for f in sorted(os.listdir(_DOCS)):
        if f.endswith(".md"):
            with open(os.path.join(_DOCS, f), encoding="utf-8") as fh:
                out.append((f, fh.read()))
    return out


def _modules() -> list[str]:
    out = []
    for m in pkgutil.walk_packages([_ENGINE], prefix="engine."):
        out.append(m.name)
    return sorted(out)


def _aplatir(o, prof=0, acc=None):
    """Aplatit un conteneur en un set de cles/elements HACHABLES (bornes en profondeur)."""
    if acc is None:
        acc = set()
    if prof > 3:
        return acc
    if isinstance(o, dict):
        for k, v in o.items():
            if isinstance(k, (str, int)):
                acc.add(k)
            _aplatir(v, prof + 1, acc)
    elif isinstance(o, (list, tuple, set, frozenset)):
        for v in o:
            if isinstance(v, (str, int)):
                acc.add(v)
            else:
                _aplatir(v, prof + 1, acc)
    elif isinstance(o, (str, int)):
        acc.add(o)
    return acc


def charger_registres() -> tuple[dict, dict, list]:
    """Rend (registres, symboles, erreurs).

    registres : (module, attribut) -> set d'elements hachables
    symboles  : nom_snake_defini -> [module...]  (def/class de premier niveau)
    """
    registres: dict[tuple[str, str], set] = {}
    symboles: dict[str, list[str]] = defaultdict(list)
    erreurs: list[tuple[str, str]] = []
    for name in _modules():
        try:
            mod = importlib.import_module(name)
        except Exception as exc:                       # module non importable seul : on le DIT
            erreurs.append((name, "%s: %s" % (type(exc).__name__, exc)))
            continue
        if name in MIROIRS:
            continue
        for attr in dir(mod):
            if attr.startswith("__"):
                continue
            try:
                val = getattr(mod, attr)
            except Exception:
                continue
            if isinstance(val, (dict, set, frozenset, list, tuple)) and val:
                plat = _aplatir(val)
                if plat:
                    registres[(name, attr)] = plat
            elif callable(val) and getattr(val, "__module__", None) == name:
                symboles[attr.lower()].append(name)
    return registres, symboles, erreurs


def population() -> list[dict]:
    """Tout ce que les deux audits comptent NON PORTE, toutes categories confondues."""
    pop: list[dict] = []
    rows = AKC.collect()
    for r in rows:
        for a in r["actives"]:
            if not a["combat"]:
                pop.append({"nom": a["name"], "id": a["id"], "cat": "active-combat",
                            "porteur": r["id"]})
            if not a["decision"]:
                pop.append({"nom": a["name"], "id": a["id"], "cat": "active-decision",
                            "porteur": r["id"]})
        for p in r["passives"]:
            if not p["covered"]:
                pop.append({"nom": p["name"], "id": None, "cat": "passif", "porteur": r["id"]})
        for t in r["traits"]:
            if not t["covered"]:
                pop.append({"nom": t["name"], "id": None, "cat": "trait", "porteur": r["id"]})
    name2id = {v: k for k, v in EM.ACTIVE_ABILITY_TYPE.items()}
    for c in AKC.collect_conditionnelles(name2id):
        if not c["covered"]:
            pop.append({"nom": c["name"], "id": c["id"], "cat": "conditionnelle-" + c["voie"],
                        "porteur": (c["carriers"] or ["?"])[0]})
    for aid, nm, st, _cl, _nu, _kinds in ACAC.collect():
        if st == "NO-OP":
            pop.append({"nom": nm, "id": aid, "cat": "combat-no-op", "porteur": "-"})
    vus: dict[tuple[str, str], dict] = {}
    for e in pop:
        k = (e["nom"], e["cat"])
        if k not in vus:
            e = dict(e)
            e["porteurs"] = [e.pop("porteur")]
            vus[k] = e
        else:
            vus[k]["porteurs"].append(e["porteur"])
    return sorted(vus.values(), key=lambda e: (e["cat"], e["nom"]))


def tracer(pop: list[dict], registres: dict, symboles: dict) -> None:
    for e in pop:
        nm, aid = e["nom"], e["id"]
        sn = _snake(nm)
        hits = []
        for (mod, attr), plat in registres.items():
            if nm in plat or (aid is not None and aid in plat):
                hits.append("%s.%s" % (mod, attr))
        e["registres"] = sorted(hits)
        syms = []
        for s, mods in symboles.items():
            if sn in s:
                syms.append("%s (%s)" % (s, mods[0]))
        e["symboles"] = sorted(syms)


#: marqueurs d'un VERDICT ecrit (cas 2 : « le natif n'a rien de propre / c'est mort »). La fenetre
#: est volontairement large : ce probe TRIE, il ne conclut pas.
MARQUEURS = (
    "rien a porter", "rien à porter", "sans contenu propre", "aucun code à écrire",
    "aucun code a ecrire", "registered-but-dead", "décompilé lu", "decompile lu",
    "rien à brancher", "dead, lu", "verdict mesuré", "verdict mesure",
)


def verdicts(pop: list[dict], docs: list[tuple[str, str]], fenetre: int = 12) -> None:
    """Pour chaque item, cherche un MARQUEUR de verdict a moins de `fenetre` lignes d'une mention
    de son nom. Signal de TRIAGE : un couple (doc, ligne) a lire, jamais une conclusion."""
    for e in pop:
        hits = []
        for fname, txt in docs:
            lignes = txt.splitlines()
            idx = [i for i, l in enumerate(lignes) if e["nom"] in l]
            for i in idx:
                bloc = "\n".join(lignes[max(0, i - fenetre):i + fenetre]).lower()
                for m in MARQUEURS:
                    if m in bloc:
                        hits.append("%s:%d (%s)" % (fname, i + 1, m))
                        break
        e["verdicts"] = sorted(set(hits))


def main() -> int:
    detail = "--detail" in sys.argv
    registres, symboles, erreurs = charger_registres()
    pop = population()
    tracer(pop, registres, symboles)
    verdicts(pop, _docs())

    par_cat: dict[str, list] = defaultdict(list)
    for e in pop:
        par_cat[e["cat"]].append(e)

    print("=== SUBSTRAT ===")
    print("  modules engine.** importes : %d ; NON importables : %d"
          % (len(_modules()) - len(erreurs), len(erreurs)))
    for m, msg in erreurs[:8]:
        print("    ECHEC %s -- %s" % (m, msg[:110]))
    print("  conteneurs de module visites : %d (mirrors d'enum exclus : %d modules)"
          % (len(registres), len(MIROIRS)))
    print()

    print("=== POPULATION (items comptes NON PORTES par les deux audits) ===")
    for cat in sorted(par_cat):
        print("  %-24s %d" % (cat, len(par_cat[cat])))
    print("  %-24s %d" % ("TOTAL (nom x categorie)", len(pop)))
    print()

    avec = [e for e in pop if e["registres"] or e["symboles"]]
    sans = [e for e in pop if not (e["registres"] or e["symboles"])]
    print("=== TRIAGE ===")
    print("  CANDIDATS (registre et/ou symbole dedie) : %d" % len(avec))
    print("  AUCUNE trace structurelle                : %d" % len(sans))
    print()
    print("=== CANDIDATS ===")
    for e in sorted(avec, key=lambda e: (e["cat"], e["nom"])):
        print("[%s] %s (id=%s) porteurs=%s"
              % (e["cat"], e["nom"], e["id"], ",".join(e["porteurs"][:3])))
        for r in e["registres"][:(20 if detail else 6)]:
            print("      reg: %s" % r)
        for s in e["symboles"][:(20 if detail else 6)]:
            print("      sym: %s" % s)
    print()
    print("=== AUCUNE TRACE STRUCTURELLE (vrais manquants probables) ===")
    for e in sorted(sans, key=lambda e: (e["cat"], e["nom"])):
        print("[%s] %s (id=%s) porteurs=%s"
              % (e["cat"], e["nom"], e["id"], ",".join(e["porteurs"][:3])))
    print()
    vdt = [e for e in pop if e["verdicts"]]
    print("=== VERDICT ECRIT a proximite (cas 2 candidat) : %d ===" % len(vdt))
    for e in sorted(vdt, key=lambda e: (e["cat"], e["nom"])):
        print("[%s] %s (id=%s)" % (e["cat"], e["nom"], e["id"]))
        for v in e["verdicts"][:(20 if detail else 5)]:
            print("      %s" % v)
    return 0


if __name__ == "__main__":
    sys.exit(main())
