"""#429 -- RE-DERIVE l'etat de port des regles de ciblage, et CONFRONTE les recensements du depot.

CE QUE CA REPOND
----------------
« Quelles regles de `TargetingRule` ne sont pas portees, et chez combien d'abilities mordent-elles
reellement ? » -- une question a laquelle le depot repondait par TROIS tables saisies a la main,
qui ne couvraient ni le meme perimetre ni les memes membres.

TROIS DERIVATIONS, aucune saisie
--------------------------------
1. **L'ENUM** vient de `data/symbols/<build qui fait foi>/frida/enums.tsv` (via `symbols_layout`),
   jamais d'une liste ecrite ici.
2. **CE QUE LE PORT PORTE** vient de l'AST de `engine/runner/abilities/` : une regle est PORTEE
   si le port peut la RENDRE comme code de refus (`return int(TR.<X>)`). C'est la colonne qui se
   perime en silence dans une table ecrite, donc c'est celle qu'on ne saisit jamais.
3. **L'ARMEMENT** vient de `targeting_rule_inventory.RULE_ROLE[...].armed_by`, relu au decompile.
   Il change tout : TROIS regles du filtre statique ne sont PAS armees par leur propre bit, et
   compter « les porteurs du bit » y donne un compte structurellement FAUX -- c'est la faute que
   les trois tables partageaient.

Ce probe MESURE. La GARDE (echec sur divergence) est
`tests/engine/runner/test_targeting_rule_inventory.py`.

Sortie ASCII only (console Windows cp1252).
"""
from __future__ import annotations

import argparse
import ast
import os
import sys
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import symbols_layout  # noqa: E402
from engine.runner.abilities.targeting_rule import TargetingRule as TR  # noqa: E402
from engine.runner.abilities.targeting_rule_inventory import RULE_ROLE, KINDS  # noqa: E402

REPO = Path(__file__).resolve().parents[2]
ABILITIES = REPO / "scripts" / "python" / "engine" / "runner" / "abilities"
ENUM_NAME = "IdunBattle.Core.Services.TargetingRule"


# ------------------------------------------------------------------------------------------
# 1. L'ENUM, depuis le dump du build qui FAIT FOI
# ------------------------------------------------------------------------------------------
def enum_members(build: str | None = None) -> list:
    """[(nom, valeur)] verbatim du dump -- la SEULE source de noms de bits."""
    p = symbols_layout.build_dir(build) / "frida" / "enums.tsv"
    for ln in p.open(encoding="utf-8"):
        if ln.startswith(ENUM_NAME + "\t"):
            out = []
            for kv in ln.rstrip("\n").split("\t", 1)[1].split(","):
                raw, nom = kv.split("=", 1)
                out.append((nom, int(raw)))
            return out
    raise RuntimeError("%s absent de %s" % (ENUM_NAME, p))


# ------------------------------------------------------------------------------------------
# 2. CE QUE LE PORT PORTE -- derive de l'AST, jamais saisi
# ------------------------------------------------------------------------------------------
def _tr_names(node: ast.AST) -> set:
    """Les `TR.<Nom>` cites dans un sous-arbre."""
    out = set()
    for n in ast.walk(node):
        if isinstance(n, ast.Attribute) and isinstance(n.value, ast.Name) and n.value.id == "TR":
            out.add(n.attr)
    return out


def _tr_reason_codes(node: ast.AST) -> set:
    """Les `int(TR.<Nom>)` d'un sous-arbre -- la forme EXACTE d'un CODE DE REFUS rendu.

    Le critere large « un `TR.<X>` sous un `return` » est FAUX : il capte aussi les getters
    DECLARATIFS du masque (`return self.has(TR.CasterIsPossibleTarget)`), qui ne refusent rien.
    Mesure : le critere large classait `TargetIsEnemy`/`CasterIsPossibleTarget` comme portes par
    des lignes qui sont de simples lectures."""
    out = set()
    for n in ast.walk(node):
        if (isinstance(n, ast.Call) and isinstance(n.func, ast.Name) and n.func.id == "int"
                and len(n.args) == 1):
            out |= _tr_names(n.args[0])
    return out


def _port_modules() -> list:
    return sorted(p for p in ABILITIES.rglob("*.py") if p.name != "targeting_rule.py")


def rules_returned_by_port() -> dict:
    """{nom de regle: [fichier:ligne]} -- les regles que le port peut RENDRE comme code de refus.

    Critere = `int(TR.<X>)` dans l'expression d'un `return`. C'est la definition OPERATIONNELLE de
    « portee » : le natif rend la 1re regle rompue, donc une regle que le port ne rend jamais ne
    refuse jamais (degradation PERMISSIVE)."""
    out = {}
    for f in _port_modules():
        try:
            tree = ast.parse(f.read_text(encoding="utf-8"))
        except SyntaxError:
            continue
        for n in ast.walk(tree):
            if isinstance(n, ast.Return) and n.value is not None:
                for nom in _tr_reason_codes(n.value):
                    out.setdefault(nom, []).append("%s:%d" % (f.name, n.lineno))
    return out


def rules_tested_by_port() -> dict:
    """{nom: [fichier:ligne]} -- les regles dont le port TESTE le bit (`options.has(TR.<X>)`)."""
    out = {}
    for f in _port_modules():
        try:
            tree = ast.parse(f.read_text(encoding="utf-8"))
        except SyntaxError:
            continue
        for n in ast.walk(tree):
            if (isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)
                    and n.func.attr == "has"):
                for a in n.args:
                    for nom in _tr_names(a):
                        out.setdefault(nom, []).append("%s:%d" % (f.name, n.lineno))
    return out


# ------------------------------------------------------------------------------------------
# 3. L'ARMEMENT -- qui declenche reellement l'evaluation de la regle
# ------------------------------------------------------------------------------------------
def _is_unit_targeting(r: int) -> bool:
    """`TargetingOptions$$get_IsUnitTargeting` = ABSENCE des trois autres tetes de domaine."""
    return not (r & (int(TR.TargetIsTile) | int(TR.TargetIsMachine) | int(TR.TargetIsActor)))


# Un predicat par regle dont `armed_by` n'est PAS son propre bit. La garde exige la bijection
# entre ces cles et les entrees de `RULE_ROLE` a `armed_by is not None` : une regle dont
# l'armement est declare non trivial mais dont le predicat manque ferait un compte faux.
ARMED_BY = {
    "TargetIsAllowedForCaster":
        lambda r: bool((r & (int(TR.TargetIsEnemy) | int(TR.TargetIsCasterOrEnemy)))
                       and not (r & int(TR.AllowIgnoreForcedAttackTarget))),
    "TargetIsTargetable":
        lambda r: not (r & int(TR.AllowUntargetableTarget)),
    "TargetIsUnit":
        lambda r: _is_unit_targeting(r),
    "TargetIsNotSteppable":
        lambda r: bool((r & int(TR.TargetIsNotSteppable))
                       or (_is_unit_targeting(r) and not (r & int(TR.AllowSteppableUnit)))),
    # Le volet PORTEE n'est gate par aucun bit : il tourne des que l'ability a un `TargetingRange`.
    "TargetIsInRange": lambda r: True,
    "TargetIsAtRange": lambda r: True,
    # La ligne de vue tourne inconditionnellement hors `ignoreRangeChecks`.
    "TargetIsUnobscured": lambda r: True,
}

# Les regles armees chez (quasi) TOUT le registre parce que rien ne les gate. Les separer du
# rapport n'est pas cosmetique : sans cette coupure, « 103/103 abilities touchees » masque les
# gisements CIBLES, qui sont les seuls actionnables ability par ability.
ARMED_BY_DEFAULT = ("TargetIsNotSteppable", "TargetIsAllowedForCaster", "TargetIsUnobscured",
                    "TargetIsUnit", "TargetIsTargetable", "TargetIsInRange", "TargetIsAtRange")


def armed_carriers(nom: str, masks: dict) -> list:
    """Les abilities du registre chez qui la regle est ARMEE (pas « qui posent son bit »)."""
    pred = ARMED_BY.get(nom)
    if pred is None:
        bit = getattr(TR, nom, None)
        if bit is None:
            return []
        pred = (lambda b: (lambda r: bool(r & int(b))))(bit)
    return sorted(aid for aid, (rules, _n) in masks.items() if pred(int(rules)))


def collect_masks() -> dict:
    """(aid -> (rules, source)) pour les DEUX sources de masque du port."""
    from engine.runner.abilities.handler import ABILITY_CLASSES
    from engine.runner.abilities.targeting import TARGETING_OPTIONS_UNPORTED
    out = {}
    for aid, klass in sorted(ABILITY_CLASSES.items()):
        opts = getattr(klass, "TARGETING_OPTIONS", None)
        if opts is not None:
            out[int(aid)] = (int(opts.rules), klass.__name__)
    for aid, opts in sorted(TARGETING_OPTIONS_UNPORTED.items()):
        if int(aid) not in out:
            out[int(aid)] = (int(opts.rules), "UNPORTED-table")
    return out


# ------------------------------------------------------------------------------------------
# Rapport
# ------------------------------------------------------------------------------------------
def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--only-gaps", action="store_true",
                    help="n'imprime que les regles GATE non portees et leurs porteurs armes")
    args = ap.parse_args()

    build = symbols_layout.current_build()
    membres = enum_members(build)
    noms = [n for n, _v in membres]
    print("build qui fait foi : %s" % build)
    print("enum %s : %d membres (%d bits simples, %d composite(s), 1 zero)"
          % (ENUM_NAME, len(membres),
             sum(1 for _n, v in membres if v > 0 and not (v & (v - 1))),
             sum(1 for _n, v in membres if v > 0 and (v & (v - 1)))))

    # --- couverture de l'inventaire, DEUX directions -------------------------------------
    manquants = [n for n in noms if n not in RULE_ROLE]
    fantomes = [n for n in RULE_ROLE if n not in noms]
    print("inventaire : %d entrees ; enum \\ inventaire = %d ; inventaire \\ enum = %d"
          % (len(RULE_ROLE), len(manquants), len(fantomes)))
    for n in manquants:
        print("  NON CLASSE (direction VIVANTE) : %s" % n)
    for n in fantomes:
        print("  ENTREE MORTE (direction MORTE) : %s" % n)

    # --- ventilation par categorie -------------------------------------------------------
    par_kind = {}
    for n in noms:
        role = RULE_ROLE.get(n)
        if role is not None:
            par_kind.setdefault(role.kind, []).append(n)
    print("")
    print("--- VENTILATION PAR ROLE NATIF ------------------------------------------")
    for k in KINDS:
        v = par_kind.get(k, [])
        print("  %-16s %2d" % (k, len(v)))

    # --- ce que le port porte, DERIVE ----------------------------------------------------
    rendues = rules_returned_by_port()
    testees = rules_tested_by_port()
    gates = [n for n in noms
             if RULE_ROLE.get(n) is not None
             and RULE_ROLE[n].kind in ("GATE_TARGET", "GATE_CASTER", "GATE_ADD_CASTER")]
    portees = [n for n in gates if RULE_ROLE[n].code(n) in rendues]
    print("")
    print("--- CE QUE LE PORT PORTE (derive de l'AST) ------------------------------")
    print("  regles GATE : %d ; RENDUES par le port : %d ; NON PORTEES : %d"
          % (len(gates), len(portees), len(gates) - len(portees)))

    masks = collect_masks()
    print("  masques lisibles au registre : %d" % len(masks))

    print("")
    print("--- REGLES GATE NON PORTEES x PORTEURS ARMES ----------------------------")
    touchees, touchees_ciblees = set(), set()
    lignes = []
    for n in gates:
        if n in portees:
            continue
        carriers = armed_carriers(n, masks)
        touchees.update(carriers)
        if n not in ARMED_BY_DEFAULT:
            touchees_ciblees.update(carriers)
        lignes.append((len(carriers), n, carriers, RULE_ROLE[n].armed_by))
    for cnt, n, carriers, arme in sorted(lignes, key=lambda t: (-t[0], t[1])):
        print("  %-42s %3d ability(s) armee(s)%s%s"
              % (n, cnt, "  [DEFAUT]" if n in ARMED_BY_DEFAULT else "",
                 "" if arme is None else "   [ARME PAR : %s]" % arme))
        if not args.only_gaps and carriers:
            print("        " + ", ".join(str(a) for a in carriers[:24])
                  + (" ..." if len(carriers) > 24 else ""))
    print("")
    print("  abilities touchees par >= 1 regle GATE non portee : %d / %d"
          % (len(touchees), len(masks)))
    print("  ... hors regles ARMEES PAR DEFAUT (le gisement CIBLE, actionnable) : %d / %d"
          % (len(touchees_ciblees), len(masks)))

    if not args.only_gaps:
        print("")
        print("--- REGLES PORTEES (le port les rend) ----------------------------------")
        for n in portees:
            print("  %-42s %s" % (n, ", ".join(sorted(set(rendues[n]))[:3])))
        inertes = sorted(set(testees) - set(rendues))
        if inertes:
            print("")
            print("--- BITS TESTES MAIS JAMAIS RENDUS (permissions / aiguillages) ---------")
            for n in inertes:
                k = RULE_ROLE[n].kind if n in RULE_ROLE else "?"
                print("  %-42s %-16s %s" % (n, k, ", ".join(sorted(set(testees[n]))[:2])))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
