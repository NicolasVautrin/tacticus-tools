"""probe #225 -- INVENTAIRE des gates de TRAIT de la couche DECISION (playbook / utilities Tile)
et de leur atteignabilite par un trait accorde EN BATAILLE.

Deux volets, tous deux MESURES (rien n'est recopie a la main) :

  (1) ECRITURE -- quels traits le natif peut-il accorder/retirer PENDANT la bataille ?
      Le seul chemin d'ecriture est `IdunBattle.Operations.AddTraitOperation$$AddTrait` :

          comp = GetBaseUnitComponent(target)
          collection = isTemporary ? comp+0x48 : comp+0x40
          collection.Add(trait)

      donc un ajout PERMANENT ecrit la MEME collection `+0x40` que
      `IdunBattle.Entities.Factories.UnitFactory$$InitBaseComponent` seede depuis la
      BattleConfiguration. La lecture `IdunBattle.Entities.Components.BaseUnitComponent$$HasTrait` est
      `if (+0x50).Contains -> false ; return (+0x40).Contains || (+0x48).Contains`.

      Les sites d'ecriture sont ENUMERES par les xrefs de `IdunBattleLogic.Entities.DSLFactory$$AddTrait`
      (6 appelants, releve ghidra du 2026-07-29, build gqfc5mff6c) ; cinq portent un LITTERAL de trait,
      le sixieme (`EnhancementAddTraitAbility`) lit une constante d'ability -> ce volet-la se mesure
      ICI depuis le gameconfig.

  (2) LECTURE -- quels sites de la couche DECISION testent un trait, et depuis quelle SOURCE ?
      Le scan est un scan de SOURCE (AST-libre, regex sur les accesseurs connus) : il classe chaque
      site par ACCESSEUR, parce que c'est l'accesseur -- pas le site -- qui determine si le gate voit
      un trait dynamique.

Sortie ASCII pure (console cp1252).
"""
from __future__ import annotations

import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

_HERE = Path(__file__).resolve().parent
if str(_HERE) not in sys.path:
    sys.path.insert(0, str(_HERE))

ENGINE = _HERE / "engine"

# --------------------------------------------------------------------------------------------
# VOLET 1 -- les traits ECRITS en bataille (releve ghidra + gameconfig)
# --------------------------------------------------------------------------------------------
# Litteraux lus au decompile, un par appelant de `IdunBattleLogic.Entities.DSLFactory$$AddTrait` :
#   IdunBattleLogic.Entities.Abilities.Triggered.Loki.FloatingDeath_InitAbility$$CreateBehaviour
#       AddTrait(Actor, 0x41a, isTemporary=0)
#   IdunBattleLogic.Entities.Abilities.Triggered.Loki.SupaCyborkBodyAbility_AddTrait$$CreateBehaviour
#       AddTrait(Actor, 0x421, isTemporary=0)
#   IdunBattleLogic.Entities.Abilities.Active.Loki.DutyEternalAbility$$ExecuteBehaviour
#   IdunBattleLogic.Entities.Abilities.Active.Loki.AetherStrideAbility$$ExecuteBehaviour
#   IdunBattleLogic.Entities.Abilities.Active.Loki.ExemplarOfTheKauyonAbility$$ExecuteBehaviour
#       AddTrait(Target, 0x418, isTemporary=0)  -- pose dans le `SpawnUnitOptions` -> l'unite SPAWNEE
#   IdunBattleLogic.Entities.Abilities.Triggered.Loki.EnhancementAddTraitAbility$$CreateBehaviour
#       AddTrait(Target, GetEnumConstant(0x7f), isTemporary=1)  -- trait DATA-DRIVEN, cf. plus bas
NATIVE_ADDTRAIT_LITERALS = {
    0x41a: "FloatingDeath_InitAbility (Actor, permanent -> +0x40)",
    0x421: "SupaCyborkBodyAbility_AddTrait (Actor, permanent -> +0x40)",
    0x418: "DutyEternal / AetherStride / ExemplarOfTheKauyon (unite SPAWNEE, permanent -> +0x40)",
}


def enhancement_add_trait_traits() -> dict:
    """Traits accordes par `EnhancementAddTraitAbility` = la constante d'ability lue par
    `GetEnumConstant(0x7f)`. On balaie le gameconfig a la recherche des abilities dont une constante
    NOMME une valeur de l'enum `UnitTrait` -- c'est la seule forme data-driven du chemin d'ecriture."""
    import gameconfig as GC
    from engine.entities.traits.unit_trait import UnitTrait
    names = {m.name for m in UnitTrait}
    out: dict = {}
    for aid in (GC.all_ability_ids() if hasattr(GC, "all_ability_ids") else []):
        pass
    # `gameconfig` n'expose pas d'iterateur d'abilities -> on passe par le doc brut.
    doc = GC._doc() if hasattr(GC, "_doc") else None
    abilities = _all_abilities(doc)
    for aid, ab in abilities.items():
        for k, v in ((ab.get("constants") or {}).items()):
            if isinstance(v, str) and v in names:
                out.setdefault(v, []).append("%s.%s" % (aid, k))
    return out


def _all_abilities(doc) -> dict:
    """Toutes les abilities du gameconfig, {id: dict}. Traverse le doc sans presumer du schema."""
    import gameconfig as GC
    for attr in ("_abilities", "abilities_all", "all_abilities"):
        f = getattr(GC, attr, None)
        if callable(f):
            try:
                got = f()
                if isinstance(got, dict) and got:
                    return got
            except Exception:
                pass
    # Fallback : re-charger le json et retrouver le noeud des abilities.
    data = GC._load() if hasattr(GC, "_load") else None
    if data is None:
        return {}
    found: dict = {}

    def walk(node):
        if isinstance(node, dict):
            for k, v in node.items():
                if k in ("abilities", "abilityConfigurations") and isinstance(v, (list, dict)):
                    items = v.values() if isinstance(v, dict) else v
                    for it in items:
                        if isinstance(it, dict) and it.get("id"):
                            found[it["id"]] = it
                else:
                    walk(v)
        elif isinstance(node, list):
            for v in node:
                walk(v)

    walk(data)
    return found


# --------------------------------------------------------------------------------------------
# VOLET 2 -- les LECTURES de trait de la couche DECISION, classees par ACCESSEUR
# --------------------------------------------------------------------------------------------
# Chaque motif = un ACCESSEUR distinct. La colonne `dyn` dit si l'accesseur peut, PAR CONSTRUCTION,
# rendre un trait accorde en bataille :
#   * "gameconfig" : lecture directe `GC.unit(<visualId>).traits` -> STATIQUE par unite, jamais
#     l'etat de l'entite. AVEUGLE a tout `AddTraitOperation`.
#   * "vis-cache"  : `unit_trait_names/ids(visual_id)` (lru_cache PAR visualId) -> meme cecite, et
#     en prime un cache global qui interdirait de le rendre dynamique sans le supprimer.
#   * "ctx"        : `UnitContext.traits` -- liste PAR ENTITE, mutable. C'est le seul substrat du
#     port qui PEUT porter un trait dynamique (le verrou de `test_chain_after_refused_addeffect_live`
#     y accorde `Immune` a la main).
ACCESSORS = [
    ("gameconfig", re.compile(
        r"GC\.unit\([^)]*\)\s*or\s*\{\}\)\.get\(\"traits\"\)"
        r"|_GC\.unit\([^)]*\)\s*or\s*\{\}\)\.get\(\"traits\"\)"
        r"|\.get\(\"traits\"\)")),
    ("vis-cache", re.compile(r"unit_trait_(names|ids)\s*\(")),
    ("ctx", re.compile(r"getattr\(\s*[A-Za-z_.]*ctx[A-Za-z_.]*\s*,\s*\"traits\""
                       r"|\bctx\.traits\b|\.ctx\.traits\b")),
]

# Sites de GATE : une comparaison de trait (le nom du trait, ou un helper de test).
GATE_PAT = re.compile(
    r"has_trait\(|has_any_trait\(|_has_trait\(|units_without_trait\("
    r"|\"[A-Z][A-Za-z]+\"\s+(?:not\s+)?in\s+[A-Za-z_][A-Za-z_0-9.\[\]()\"]*traits"
    r"|UnitTrait\.[A-Za-z_]+\.name\s+(?:not\s+)?in\b"
    r"|HasTrait\(")

# Perimetre DECISION : la couche qui produit l'action de l'IA.
DECISION_ROOTS = ["playbook", "utilities/tile.py", "ai"]


def scan_decision_layer() -> list:
    rows = []
    for path in sorted(ENGINE.rglob("*.py")):
        rel = path.relative_to(ENGINE).as_posix()
        if not any(rel == r or rel.startswith(r + "/") for r in DECISION_ROOTS):
            continue
        for i, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            stripped = line.strip()
            if stripped.startswith("#") or stripped.startswith('"""'):
                continue
            if not GATE_PAT.search(line):
                continue
            acc = None
            for name, pat in ACCESSORS:
                if pat.search(line):
                    acc = name
                    break
            rows.append({"file": rel, "line": i, "acc": acc, "code": stripped[:150]})
    return rows


def scan_sources() -> list:
    """Les SOURCES de trait de la couche decision (la ou le set de traits est CONSTRUIT)."""
    rows = []
    src_pat = re.compile(r"\.get\(\"traits\"\)|unit_trait_(names|ids)\s*\(|\bctx\.traits\b")
    for path in sorted(ENGINE.rglob("*.py")):
        rel = path.relative_to(ENGINE).as_posix()
        if not any(rel == r or rel.startswith(r + "/") for r in DECISION_ROOTS):
            continue
        for i, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            stripped = line.strip()
            if stripped.startswith("#"):
                continue
            if src_pat.search(line):
                kind = ("vis-cache" if "unit_trait_" in line
                        else "ctx" if "ctx.traits" in line else "gameconfig")
                rows.append({"file": rel, "line": i, "kind": kind, "code": stripped[:150]})
    return rows


def main() -> int:
    from engine.entities.traits.unit_trait import UnitTrait

    print("=" * 92)
    print("#225 -- INVENTAIRE des gates de trait de la couche DECISION")
    print("=" * 92)

    print("\n[1] TRAITS ACCORDES EN BATAILLE (chemin d'ecriture natif AddTraitOperation)")
    print("    -- litteraux lus au decompile (xrefs de DSLFactory$$AddTrait) :")
    dyn_traits = set()
    for tid, who in sorted(NATIVE_ADDTRAIT_LITERALS.items()):
        nm = UnitTrait(tid).name
        dyn_traits.add(nm)
        print("      0x%-4x %-26s %s" % (tid, nm, who))
    print("    -- data-driven (EnhancementAddTraitAbility, GetEnumConstant(0x7f), isTemporary=1) :")
    try:
        eat = enhancement_add_trait_traits()
    except Exception as exc:                                   # gameconfig absent -> on le dit
        eat = {}
        print("      (gameconfig illisible : %s)" % exc)
    for nm, where in sorted(eat.items()):
        dyn_traits.add(nm)
        print("      %-26s <- %s" % (nm, ", ".join(sorted(where))[:110]))
    print("    => %d traits DYNAMIQUEMENT accordables : %s"
          % (len(dyn_traits), ", ".join(sorted(dyn_traits))))

    rows = scan_decision_layer()
    print("\n[2] GATES DE TRAIT de la couche DECISION : %d sites" % len(rows))
    by_acc = Counter(r["acc"] for r in rows)
    for acc, n in by_acc.most_common():
        print("      accesseur %-12s : %3d" % (str(acc), n))
    by_file = defaultdict(int)
    for r in rows:
        by_file[r["file"]] += 1
    print("    -- par fichier :")
    for f, n in sorted(by_file.items(), key=lambda kv: -kv[1]):
        print("      %-52s %3d" % (f, n))

    srcs = scan_sources()
    print("\n[3] SOURCES de trait (construction du set) : %d sites" % len(srcs))
    by_kind = Counter(s["kind"] for s in srcs)
    for k, n in by_kind.most_common():
        print("      %-12s : %3d" % (k, n))
    for s in srcs:
        print("      %-12s %s:%d  %s" % (s["kind"], s["file"], s["line"], s["code"][:80]))

    print("\n[4] DETAIL DES GATES")
    for r in rows:
        print("      %-12s %s:%d  %s" % (str(r["acc"]), r["file"], r["line"], r["code"][:90]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
