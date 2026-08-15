"""#576-r2 -- QUELLES classes d'effet le gate de pose d'`AddStaticStatModifierEffect` peut-il MORDRE ?

Le gate (`runner/abilities/behaviours/effects.py`, feuille `AddStaticStatModifierEffect`) ne change
rien pour un effet dont la classe ne surcharge PAS `is_active` : `BaseEffect.is_active` rend `True`
par DEFAUT, donc le gate passe et la contribution est appliquee comme avant.

Il ne peut mordre que sur l'INTERSECTION :

    {effect_type poses par cette feuille}  INTER  {classes surchargeant `is_active`}

et c'est cette intersection qu'il faut lire AVANT de livrer, pour une raison precise : le driver
`refresh_stat_modifier_effects` **NE RE-APPLIQUE JAMAIS** une instance portant un `stat_mod_source`
(il ne fait que la RETIRER). Donc si le gate ferme sur une classe dont la condition est DYNAMIQUE,
la contribution est perdue A VIE au lieu d'etre appliquee quand la condition devient vraie -- ce
serait une REGRESSION, pas une fidelite.

Pour une condition CONSTANTE (comme `1369 BloodChalice_ExtraPiercing`, dont la
`CreateActiveCondition` est structurellement fausse, #576-r1), il n'y a rien a perdre : le natif ne
l'applique jamais non plus.

METHODE -- statique (AST), pas d'execution des arbres :
  * on visite tout `engine/**`, on retient chaque appel `AddStaticStatModifierEffect(...)` /
    `AddOrUpdateStaticStatModifierEffect(...)` / `add_or_update_static_stat_modifier_effect(...)` ;
  * on resout le 2e argument positionnel (`effect_type`) contre les constantes du module ET contre
    l'enum `EffectType`, en important REELLEMENT le module (donc les alias locaux du genre
    `BLOOD_CHALICE_EXTRA_PIERCING` sont resolus a leur valeur) ;
  * un argument non resolvable sort en `NON RESOLU` -- il est COMPTE et AFFICHE, jamais tu : un
    recenseur qui tait ce qu'il n'a pas su lire rend un zero qui se lit comme une absence.

Sortie ASCII (cp1252). Aucun runner, aucun RPC.
"""
from __future__ import annotations

import argparse
import ast
import importlib
import os
import pathlib
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

FEUILLES = ("AddStaticStatModifierEffect",
            "AddOrUpdateStaticStatModifierEffect",
            "add_or_update_static_stat_modifier_effect")

# Le fichier qui DEFINIT les feuilles : ses occurrences sont les definitions et la composition
# interne (`AddOrUpdateStaticStatModifierEffect` reutilise `AddStaticStatModifierEffect`), pas des
# call-sites porteurs d'un effect_type de gameplay.
FOYER = "engine/runner/abilities/behaviours/effects.py"


def _module_de(path: pathlib.Path) -> str:
    return str(path.with_suffix("")).replace(os.sep, ".").replace("/", ".")


def _valeurs_de_lattribut(arbre, mod, nom, effect_type_enum):
    """SUR-APPROXIMATION d'un `self.<NOM>` : toutes les affectations `<NOM> = <...>` du fichier.

    C'est ce qui ferme le call-site `AddStaticStatModifierEffect(Caster(), self.
    HIT_REDUCTION_EFFECT_TYPE, ...)` de `reactivate_overwatch.py` -- le vslot natif
    `GetHitReductionEffectType()` (+0x758) est surcharge par chaque sous-classe, donc l'ensemble des
    valeurs POSSIBLES est l'ensemble des affectations. Sur-approximer est le bon sens de l'erreur :
    on rend le gate suspect sur PLUS d'effets qu'il n'en touche, jamais sur moins."""
    out = set()
    for n in ast.walk(arbre):
        cible = None
        if isinstance(n, ast.Assign) and len(n.targets) == 1 and isinstance(n.targets[0], ast.Name):
            cible, val = n.targets[0].id, n.value
        elif isinstance(n, ast.AnnAssign) and isinstance(n.target, ast.Name):
            cible, val = n.target.id, n.value
        if cible != nom or val is None:
            continue
        v, _ = _resoudre(val, mod, effect_type_enum)
        if v is not None and v >= 0:            # `-1` = le sentinel « classe de base abstraite »
            out.add(int(v))
    return out


def _valeurs_du_parametre(racine, fonction, position, effect_type_enum):
    """SUR-APPROXIMATION d'un PARAMETRE : toutes les valeurs passees a `fonction` par ses appelants.

    Ferme les deux call-sites de `power_up.py`, ou `effect_type` est un parametre des factories
    `add_pct_based_boost_tree` / `add_absolute_boost_tree` alimentees par les 22 `PowerUp_*`.
    On lit l'argument NOMME s'il existe, sinon l'argument POSITIONNEL."""
    out, non_lus = set(), 0
    for p in sorted(pathlib.Path(racine).rglob("*.py")):
        try:
            arbre = ast.parse(p.read_text(encoding="utf-8", errors="replace"))
        except SyntaxError:
            continue
        appels = [n for n in ast.walk(arbre)
                  if isinstance(n, ast.Call)
                  and ((isinstance(n.func, ast.Name) and n.func.id == fonction)
                       or (isinstance(n.func, ast.Attribute) and n.func.attr == fonction))]
        if not appels:
            continue
        try:
            mod = importlib.import_module(_module_de(p))
        except Exception:                                # noqa: BLE001
            non_lus += len(appels)
            continue
        for a in appels:
            arg = None
            for kw in a.keywords:
                if kw.arg == "effect_type":
                    arg = kw.value
            if arg is None and len(a.args) > position:
                arg = a.args[position]
            if arg is None:
                non_lus += 1
                continue
            v, _ = _resoudre(arg, mod, effect_type_enum)
            if v is None:
                non_lus += 1
            else:
                out.add(int(v))
    return out, non_lus


def _valeurs_par_tuples_de_classe(mod, effect_type_enum):
    """DERNIER RECOURS, et il est DYNAMIQUE : les ordinaux d'`EffectType` atteignables via les
    TUPLES de configuration portes par les classes du module.

    Ferme les deux call-sites de `power_up.py`, ou la chaine est
    `AddStaticStatModifierEffect(..., int(effect_type), ...)` <- parametre de
    `add_pct_based_boost_tree` <- `int(eff)` <- deballage de `self.PCT_BASED_STAT_BOOST`
    (`(stat, effectType)`) / `self.ABSOLUTE_STAT_BOOST` (`(const_key, stat, effectType)`), soit
    DEUX indirections de plus que ce que l'AST suit. L'ATTRIBUT DE CLASSE, lui, se lit directement :
    on balaie toutes les classes du module et on retient tout element de ces tuples qui est un
    ordinal d'`EffectType` valide. C'est encore une SUR-APPROXIMATION (un `stat_type` qui
    coinciderait avec un ordinal d'effet serait retenu a tort), donc du bon cote de l'erreur."""
    out = set()
    valides = {int(m) for m in effect_type_enum}
    for nom in dir(mod):
        klass = getattr(mod, nom, None)
        if not isinstance(klass, type):
            continue
        for attr in dir(klass):
            if "BOOST" not in attr and "EFFECT" not in attr:
                continue
            val = getattr(klass, attr, None)
            elems = val if isinstance(val, (tuple, list)) else (val,)
            for e in elems:
                if isinstance(e, int) and not isinstance(e, bool) and int(e) in valides:
                    out.add(int(e))
    return out


def _resoudre(node, mod, effect_type_enum):
    """Rend (valeur_int, comment) ou (None, raison). On ne DEVINE pas : tout ce qui n'est pas
    litteral, attribut d'enum ou nom de module resolu sort en non-resolu."""
    if isinstance(node, ast.Constant) and isinstance(node.value, int):
        return int(node.value), "litteral"
    if isinstance(node, ast.Call):                      # int(X) / EffectType(X)
        if node.args:
            return _resoudre(node.args[0], mod, effect_type_enum)
        return None, "appel sans argument"
    if isinstance(node, ast.Attribute):                 # EffectType.Foo / EffectType.Foo.value
        if node.attr == "value":
            return _resoudre(node.value, mod, effect_type_enum)
        base = node.value
        if isinstance(base, ast.Name) and base.id == "EffectType":
            m = getattr(effect_type_enum, node.attr, None)
            return (int(m), "EffectType.%s" % node.attr) if m is not None else (
                None, "EffectType.%s inconnu" % node.attr)
        # <Classe>.CONSTANTE -- on tente l'attribut sur le module
        obj = getattr(mod, base.id, None) if isinstance(base, ast.Name) else None
        v = getattr(obj, node.attr, None) if obj is not None else None
        return (int(v), "attribut") if isinstance(v, int) else (None, "attribut non resolu")
    if isinstance(node, ast.Name):                      # constante de module
        v = getattr(mod, node.id, None)
        if isinstance(v, int):
            return int(v), "constante %s" % node.id
        return None, "nom %s non resolu" % node.id
    return None, "noeud %s" % type(node).__name__


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--racine", default="engine")
    args = ap.parse_args()

    from engine.entities.effect_type import EffectType
    from engine.entities.effects.base import BaseEffect
    from engine.entities.effects.factory import EFFECT_CLASSES

    surchargent = {n: c for n, c in EFFECT_CLASSES.items()
                   if c.is_active is not BaseEffect.is_active}
    par_ordinal = {}
    for nom in surchargent:
        m = getattr(EffectType, nom, None)
        if m is not None:
            par_ordinal[int(m)] = nom

    poses = {}                       # ordinal -> [(fichier, ligne)]
    non_resolus = []
    sur_approx = []                  # call-sites fermes par SUR-APPROXIMATION (dits, pas tus)
    for p in sorted(pathlib.Path(args.racine).rglob("*.py")):
        rel = str(p).replace(os.sep, "/")
        if rel.endswith(FOYER.split("engine/", 1)[-1]) and "behaviours/effects.py" in rel:
            continue
        try:
            arbre = ast.parse(p.read_text(encoding="utf-8", errors="replace"))
        except SyntaxError:
            continue
        appels = [n for n in ast.walk(arbre)
                  if isinstance(n, ast.Call) and isinstance(n.func, ast.Name)
                  and n.func.id in FEUILLES]
        if not appels:
            continue
        try:
            mod = importlib.import_module(_module_de(p))
        except Exception as exc:                        # noqa: BLE001 -- on DIT l'echec
            non_resolus.append((rel, 0, "import impossible: %s" % type(exc).__name__))
            continue
        for a in appels:
            # `AddStaticStatModifierEffect(unit_sel, effect_type, stat_type, amount, ...)`
            arg = a.args[1] if len(a.args) > 1 else None
            if arg is None:
                non_resolus.append((rel, a.lineno, "moins de 2 arguments positionnels"))
                continue
            val, why = _resoudre(arg, mod, EffectType)
            if val is None:
                # SUR-APPROXIMATION avant d'abandonner : `self.<NOM>` (vslot surcharge par les
                # sous-classes) et parametre de factory (valeurs passees par les appelants).
                sur = set()
                origine = None
                if (isinstance(arg, ast.Attribute) and isinstance(arg.value, ast.Name)
                        and arg.value.id == "self"):
                    sur = _valeurs_de_lattribut(arbre, mod, arg.attr, EffectType)
                    origine = "self.%s" % arg.attr
                elif isinstance(arg, ast.Name):
                    fn = None
                    for f in ast.walk(arbre):
                        if (isinstance(f, ast.FunctionDef)
                                and any(x.arg == arg.id for x in f.args.args)
                                and f.lineno <= a.lineno <= (f.end_lineno or a.lineno)):
                            fn = f
                    if fn is not None:
                        pos = [x.arg for x in fn.args.args].index(arg.id)
                        sur, manques = _valeurs_du_parametre(args.racine, fn.name, pos, EffectType)
                        origine = "parametre %s de %s()%s" % (
                            arg.id, fn.name, (" [%d appel(s) non lus]" % manques) if manques else "")
                        if not sur:
                            sur = _valeurs_par_tuples_de_classe(mod, EffectType)
                            origine = ("parametre %s de %s() -- via les TUPLES de classe du module"
                                       % (arg.id, fn.name))
                if sur:
                    for v in sorted(sur):
                        poses.setdefault(int(v), []).append((rel, a.lineno))
                    sur_approx.append((rel, a.lineno, origine, sorted(sur)))
                    continue
                non_resolus.append((rel, a.lineno, why))
                continue
            poses.setdefault(int(val), []).append((rel, a.lineno))

    print("=== #576-r2 -- RAYON DU GATE DE POSE ===")
    print("classes surchargeant is_active  : %d" % len(surchargent))
    print("effect_type poses par la feuille: %d (resolus)" % len(poses))
    print("call-sites NON RESOLUS          : %d" % len(non_resolus))
    for rel, ln, why in non_resolus:
        print("   NON RESOLU %s:%s -- %s" % (rel, ln, why))
    print("call-sites SUR-APPROXIMES       : %d" % len(sur_approx))
    for rel, ln, origine, vals in sur_approx:
        print("   SUR-APPROX %s:%s -- %s -> %s" % (rel, ln, origine, vals))

    mordus = sorted(set(poses) & set(par_ordinal))
    print("\n--- INTERSECTION (le gate peut MORDRE ici, et NULLE PART ailleurs) : %d ---"
          % len(mordus))
    for o in mordus:
        nom = par_ordinal[o]
        sites = ", ".join("%s:%s" % (f, l) for f, l in poses[o])
        print("   %-5d %-40s %s" % (o, nom, sites))
    if not mordus:
        print("   (aucune)")

    print("\n--- les %d autres effect_type poses n'ont PAS de condition portee -> gate PASSANT ---"
          % (len(poses) - len(mordus)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
