"""#449-r2 -- INVENTAIRE AST des porteurs de variance d'arme de la face COMBAT.

Pourquoi un AST et pas un grep : sur ce motif precis, un grep textuel MENT DANS LE SENS
RASSURANT. Mesure du 2026-08-02 sur ce depot : `spread_pct=0` apparait 6 fois dans
`engine/`, dont 5 en COMMENTAIRE ou DOCSTRING et UNE SEULE dans du code executable. Un
inventaire par texte aurait donc rendu 6 sites a trancher dont 5 fantomes -- et, pire, il
rate integralement le gisement REEL : les call-sites qui OMETTENT le mot-cle et prennent
le DEFAUT du constructeur (`AttackWithAttackDamage(..., amount_spread_pct=0)` est le
defaut, donc l'absence du mot-cle EST une decision de portage, invisible au grep).

Ce que le probe recense, et qui sont les deux seules portes d'entree de la variance
d'arme cote COMBAT (le byte natif `AttackDamageBehaviourOptions+6`, cf.
`docs/rl/case-449-r2-spread-face-combat.md`) :

  R1. `AttackWithAttackDamage(...)` / `AbilityAttack(...)` construits en MODE `amount`
      (kwarg `amount=` present) -- la variance y est pilotee par `amount_spread_pct`,
      defaut 0. Un site sans le mot-cle est classe DEFAUT-0.
  R2. `execute_normal_like(...)` -- la variance y est pilotee par `spread_pct`,
      defaut 20. Un site sans le mot-cle est classe DEFAUT-20.
  R3. les foyers d'etalement eux-memes (`get_base_damage_fix64`, `spread_to_min_max`,
      `HitDamage.from_base`) -- tout appelant qui y poserait un `spread_pct` litteral
      nul court-circuiterait les deux rails ci-dessus.

Le probe ne juge PAS la fidelite (c'est le decompile qui tranche, ability par ability) :
il rend l'inventaire EXHAUSTIF a trancher, et il rougit si un site executable apparait
hors de la liste attendue -- c'est-a-dire si notre propre cadence de portage ouvre un
nouveau porteur de variance sans qu'on l'ait tranche au decompile.

Usage :
    python probe_449r2_spread_inventory.py            # inventaire + verdict
    python probe_449r2_spread_inventory.py --list     # detail par site
"""
from __future__ import annotations

import argparse
import ast
import sys
from pathlib import Path

# Racine = le repertoire `engine/` DE CE CHECKOUT (jamais une remontee vers l'arbre
# principal : cf. #434, un cliquet ne balaie que son propre checkout).
ENGINE = Path(__file__).resolve().parent / "engine"

# Constructeurs dont le mode `amount` porte la variance via `amount_spread_pct`.
AMOUNT_CTORS = ("AttackWithAttackDamage", "AttackWithAbilityDamage")
# Operation dont la variance passe par `spread_pct`.
NORMAL_LIKE = "execute_normal_like"
# Foyers d'etalement : tout appelant qui y pose un `spread_pct` litteral court-circuite
# les deux rails ci-dessus.
SPREAD_FOYERS = ("get_base_damage_fix64", "spread_to_min_max", "from_base",
                 "calculate_damage_spread")


def _callee_name(node: ast.Call) -> str:
    f = node.func
    if isinstance(f, ast.Name):
        return f.id
    if isinstance(f, ast.Attribute):
        return f.attr
    return ""


def _kw(node: ast.Call, name: str):
    for k in node.keywords:
        if k.arg == name:
            return k
    return None


def _literal_int(node):
    """Rend l'int si le noeud est un litteral entier, sinon None (expression dynamique)."""
    if isinstance(node, ast.Constant) and isinstance(node.value, int) and not isinstance(node.value, bool):
        return node.value
    return None


def collect(root: Path):
    """Rend (sites_amount, sites_normal_like, sites_foyer), chacun une liste de dicts."""
    amount_sites, nl_sites, foyer_sites = [], [], []
    for path in sorted(root.rglob("*.py")):
        try:
            src = path.read_text(encoding="utf-8")
        except OSError:
            continue
        try:
            tree = ast.parse(src, filename=str(path))
        except SyntaxError:
            continue
        rel = path.relative_to(root.parent).as_posix()
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            name = _callee_name(node)
            if name in AMOUNT_CTORS:
                # mode `amount` seulement : hors mode `amount`, `amount_spread_pct` est INERTE
                # (le mode bornes route par `execute_ability_attack`, qui ne le lit pas).
                if _kw(node, "amount") is None:
                    continue
                kw = _kw(node, "amount_spread_pct")
                amount_sites.append({
                    "file": rel, "line": node.lineno, "callee": name,
                    "explicit": kw is not None,
                    "value": _literal_int(kw.value) if kw is not None else 0,
                    "dynamic": kw is not None and _literal_int(kw.value) is None,
                })
            elif name == NORMAL_LIKE:
                kw = _kw(node, "spread_pct")
                nl_sites.append({
                    "file": rel, "line": node.lineno, "callee": name,
                    "explicit": kw is not None,
                    "value": _literal_int(kw.value) if kw is not None else 20,
                    "dynamic": kw is not None and _literal_int(kw.value) is None,
                })
            elif name in SPREAD_FOYERS:
                kw = _kw(node, "spread_pct")
                if kw is None:
                    continue          # defaut du foyer (20) : rien a trancher ici
                foyer_sites.append({
                    "file": rel, "line": node.lineno, "callee": name,
                    "explicit": True,
                    "value": _literal_int(kw.value),
                    "dynamic": _literal_int(kw.value) is None,
                })
    return amount_sites, nl_sites, foyer_sites


# --- Liste ATTENDUE des sites qui rendent une variance NULLE (spread 0) --------------
# Chaque entree porte la RAISON LUE AU DECOMPILE. Un site qui rend 0 sans figurer ici
# fait ROUGIR : c'est un port qui a suppose l'absence de variance sans l'avoir lue.
# Cle = (fichier, nom de l'appele). La LIGNE n'entre pas dans la cle (elle bouge a
# chaque edition du fichier ; c'est le SITE qui est garde, pas sa position).
EXPECTED_ZERO = {
    ("engine/runner/operations/triggers/loki/psyker.py", "AttackWithAttackDamage"):
        "IdunBattleLogic.Entities.Abilities.Active.Loki.PsykerExtraAttackAbility$$"
        "CreateBehaviour passe le 8e argument Nullable<AttackDamageBehaviourOptions> VIDE "
        "(les 0x28 octets sont mis a zero juste avant l'appel a "
        "IdunBattleLogic.Entities.DSLBehaviors$$AttackWithAttackDamage).",
    ("engine/runner/operations/triggers/loki/cursed_plague_bell.py", "AttackWithAttackDamage"):
        "IdunBattleLogic.Entities.Abilities.Active.Loki.CursedPlagueBellAttackAbility$$"
        "CreateBehaviour : meme forme, 8e argument Nullable VIDE (0x28 octets a zero).",
    ("engine/runner/operations/triggers/loki/haze_of_corruption.py", "AttackWithAttackDamage"):
        "IdunBattle.Entities.Effects.Loki.HazeOfCorruption_DamageTransferEffect$$"
        "CreateTargetTriggerBehaviour : chaque feuille est un "
        "IdunBattleLogic.Entities.DSLBehaviors$$AttackDamage dont le 8e argument "
        "Nullable<AttackDamageBehaviourOptions> est VIDE (0x28 octets a zero).",
}

# Ce que ces trois entrees ont en commun, et pourquoi le ZERO y est un RESULTAT : le byte
# natif qui aiguille plate-vs-spread est `AttackDamageBehaviourOptions + 6`. Il n'est
# jamais constant cote COMBAT -- contre-preuve LUE :
# `IdunBattleLogic.Entities.Abilities.Active.Loki.SkyStrikeAbility$$ExecuteBehaviour` le
# pose a 1 en dur sur la meme struct (seul octet non nul), et le port lui donne bien 20
# (`engine/runner/abilities/sisterhood.py`). Un Nullable VIDE passe par
# `IdunBattle.Entities.Behaviours.AttackDamageBehaviour$$.ctor`, qui appelle
# `Nullable<T>.GetValueOrDefault` -> tous les champs a zero.


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--list", action="store_true", help="detail par site")
    args = ap.parse_args()

    if not ENGINE.is_dir():
        print("FAIL: engine/ introuvable sous %s" % ENGINE)
        return 1

    amount_sites, nl_sites, foyer_sites = collect(ENGINE)

    print("=== R1 -- constructeurs en mode `amount` (variance = amount_spread_pct, defaut 0) ===")
    print("sites: %d" % len(amount_sites))
    zero, nonzero, dyn = [], [], []
    for s in amount_sites:
        if s["dynamic"]:
            dyn.append(s)
        elif int(s["value"]) == 0:
            zero.append(s)
        else:
            nonzero.append(s)
    print("  variance NULLE (0)      : %d" % len(zero))
    print("  variance NON NULLE      : %d" % len(nonzero))
    print("  variance DYNAMIQUE      : %d" % len(dyn))
    if args.list:
        for s in amount_sites:
            v = "dyn" if s["dynamic"] else str(s["value"])
            print("    %s:%d  %s  spread=%s  %s"
                  % (s["file"], s["line"], s["callee"], v,
                     "explicite" if s["explicit"] else "DEFAUT"))

    print("=== R2 -- execute_normal_like (variance = spread_pct, defaut 20) ===")
    print("sites: %d" % len(nl_sites))
    nl_zero = [s for s in nl_sites if not s["dynamic"] and int(s["value"]) == 0]
    print("  variance NULLE (0)      : %d" % len(nl_zero))
    if args.list:
        for s in nl_sites:
            v = "dyn" if s["dynamic"] else str(s["value"])
            print("    %s:%d  %s  spread=%s  %s"
                  % (s["file"], s["line"], s["callee"], v,
                     "explicite" if s["explicit"] else "DEFAUT"))

    print("=== R3 -- foyers d'etalement avec spread_pct EXPLICITE ===")
    print("sites: %d" % len(foyer_sites))
    f_zero = [s for s in foyer_sites if not s["dynamic"] and int(s["value"]) == 0]
    print("  variance NULLE (0)      : %d" % len(f_zero))
    if args.list:
        for s in foyer_sites:
            v = "dyn" if s["dynamic"] else str(s["value"])
            print("    %s:%d  %s  spread=%s" % (s["file"], s["line"], s["callee"], v))

    # --- verdict, BIDIRECTIONNEL ------------------------------------------------------
    # Sens 1 -- tout site a variance NULLE doit etre JUSTIFIE au decompile.
    # Sens 2 -- tout site JUSTIFIE doit ETRE a variance nulle. Sans ce second sens, le
    #   garde ne rougit PAS quand on retire un zero juste : mesure du 2026-08-02, le
    #   mutant `amount_spread_pct=20` pose sur les TROIS porteurs laissait ce probe VERT
    #   (il ne voyait plus aucun zero, donc plus rien a justifier). C'est exactement la
    #   forme du trou nomme en #449 §8 : une garde qui ne porte que sur ce qu'elle
    #   OBSERVE, jamais sur ce qu'elle ATTEND, ne peut pas rougir sur une regression.
    all_zero = zero + nl_zero + f_zero
    reds = []
    for s in all_zero:
        key = (s["file"], s["callee"])
        if key not in EXPECTED_ZERO:
            reds.append(("non justifie", s))
    zero_keys = {(s["file"], s["callee"]) for s in all_zero}
    by_key = {}
    for s in amount_sites + nl_sites + foyer_sites:
        by_key.setdefault((s["file"], s["callee"]), []).append(s)
    for key in EXPECTED_ZERO:
        if key in by_key and key not in zero_keys:
            for s in by_key[key]:
                reds.append(("regression: attendu 0", s))
    print("=== VERDICT ===")
    if reds:
        print("ROUGE: %d site(s) en desaccord avec la lecture du decompile." % len(reds))
        for why, s in reds:
            v = "dyn" if s["dynamic"] else str(s["value"])
            print("  [%s] %s:%d  %s  spread=%s" % (why, s["file"], s["line"], s["callee"], v))
        print("  -> lire l'artefact natif (8e arg Nullable<AttackDamageBehaviourOptions>)")
        print("     et inscrire la raison dans EXPECTED_ZERO, ou corriger le port.")
        return 1
    # Le pendant : une entree attendue qui a DISPARU du code est aussi un signal (le
    # garde ne doit pas survivre a son gisement en silence).
    seen = {(s["file"], s["callee"]) for s in amount_sites + nl_sites + foyer_sites}
    stale = [k for k in EXPECTED_ZERO if k not in seen]
    if stale:
        print("ROUGE: %d entree(s) de EXPECTED_ZERO ne correspond(ent) plus a un site." % len(stale))
        for k in stale:
            print("  %s :: %s" % k)
        return 1
    print("VERT: les %d site(s) a variance nulle sont tous justifies au decompile."
          % (len(zero) + len(nl_zero) + len(f_zero)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
