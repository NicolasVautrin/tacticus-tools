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
   si le port peut la RENDRE comme code de refus (`return int(TR.<X>)`, en POSITION DE VALEUR --
   cf. `_tr_reason_codes`, resserre par #10012 sur une composition de masque prise pour un refus).
   C'est la colonne qui se perime en silence dans une table ecrite, donc c'est celle qu'on ne
   saisit jamais. Ce que la position de valeur ECARTE est NOMME (`rules_dropped_by_value_position`),
   imprime par le rapport et garde par un test : un filtre muet est le meme vice que les trois
   inventaires remplaces.
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


def _tr_int_calls_anywhere(node: ast.AST) -> set:
    """Les `int(TR.<Nom>)` N'IMPORTE OU dans un sous-arbre -- le TOTAL a partitionner.

    Ce n'etait pas un helper mais LE critere (`_tr_reason_codes` d'avant #10012) : tout
    `int(TR.<X>)` sous un `return` etait compte comme un CODE DE REFUS rendu. Il est conserve
    ici parce que la PARTITION doit rester exhaustive -- un `int(TR.<X>)` que la position de
    valeur ecarte doit rester COMPTE quelque part, jamais disparaitre en silence."""
    out = set()
    for n in ast.walk(node):
        if (isinstance(n, ast.Call) and isinstance(n.func, ast.Name) and n.func.id == "int"
                and len(n.args) == 1):
            out |= _tr_names(n.args[0])
    return out


def _tr_reason_codes(node: ast.AST) -> set:
    """Les `int(TR.<Nom>)` en POSITION DE VALEUR RENDUE -- la forme EXACTE d'un CODE DE REFUS.

    TROIS resserrements successifs, chacun sur une FAUSSE POSITIVE MESUREE :

    1. « un `TR.<X>` sous un `return` » captait les getters DECLARATIFS du masque
       (`return self.has(TR.CasterIsPossibleTarget)`), qui ne refusent rien -- il classait
       `TargetIsEnemy`/`CasterIsPossibleTarget` portes par de simples lectures ;
    2. « un `int(TR.<X>)` N'IMPORTE OU sous un `return` » captait une COMPOSITION DE MASQUE
       (#10012) : `targeting.py::targeting_options_for_continue` rend un `TargetingOptions`, pas
       un code, et son `rules=int(options.rules) | int(TR.AllowIgnoreForcedAttackTarget)` est le
       mirror 1:1 d'`IdunBattle.Entities.Abilities.AActiveAbility$$GetTargetingOptionsForContinue`
       (`opts.<+0x28 rules> |= 0x10000000000`). Le natif POSE ce bit ; il ne le REND jamais ;
    3. d'ou le critere d'aujourd'hui : le `int(TR.<X>)` doit etre CE QUE LE `return` REND. On
       descend depuis `Return.value` par les seuls noeuds VALEUR-TRANSPARENTS -- `IfExp`
       (`body`/`orelse`, jamais `test` : ce qu'un test LIT n'est pas ce qui est RENDU) et
       `BoolOp`. Tout le reste (argument d'appel, operande de `|`, indice, element de
       conteneur) N'EST PAS la valeur rendue.

    ANCRAGE NATIF du resserrement 3 : `IdunBattle.Core.Services.TargetingQuery$$GetInvalidTargetReason`
    (surcharge 7 args) termine par `GenericBrokenTargetingRule(rule)` avec UNE regle -- chacun de
    ses ~30 `rule = <litteral>` est un membre SIMPLE. Un refus natif ne porte jamais une
    COMBINAISON, donc un `int(TR.<X>)` operande d'un `|` ne peut pas etre un code de refus.

    CE QU'IL NE VOIT PAS, et c'est dit plutot que tu : un code de refus rendu a travers un
    WRAPPER (`return _broken(int(TR.<X>))`). Aucun site du port n'a cette forme aujourd'hui
    (mesure du 2026-08-15 : sur les 117 sites `(nom, fichier, ligne)` de l'ancien critere, les
    116 retenus sont tous `return int(TR.X)` ou `return ... if ... else int(TR.X)`, et le SEUL
    ecarte est la composition de masque ci-dessus -- `nouveau \\ ancien` est VIDE, donc le
    resserrement ne fabrique aucune entree), et le sens de la degradation est le bon -- une
    telle forme serait comptee NON
    PORTEE, donc SUR-declaree en trou, jamais tue. La contrepartie est gardee : ce que ce
    critere ECARTE est NOMME par `rules_dropped_by_value_position`, et un ecarte NEUF fait
    rougir `test_targeting_rule_inventory.py`."""
    if isinstance(node, ast.IfExp):
        return _tr_reason_codes(node.body) | _tr_reason_codes(node.orelse)
    if isinstance(node, ast.BoolOp):
        out = set()
        for v in node.values:
            out |= _tr_reason_codes(v)
        return out
    if (isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == "int"
            and len(node.args) == 1):
        return _tr_names(node.args[0])
    return set()


def _port_modules() -> list:
    return sorted(p for p in ABILITIES.rglob("*.py") if p.name != "targeting_rule.py")


def _returns_du_port():
    """[(fichier, fonction porteuse la PLUS INTERNE, noeud `Return`)] des modules du port.

    Descente explicite plutot qu'`ast.walk` imbrique : `ast.walk(<fonction externe>)` traverse
    AUSSI les closures, donc chaque `return` de closure y apparaitrait DEUX fois, une fois sous
    le nom de la fonction externe. Le port en a (les fabriques de regles dynamiques), et le nom
    de la fonction porteuse est ce qui identifie un ecarte."""
    def descendre(node, porteuse, acc):
        for enfant in ast.iter_child_nodes(node):
            if isinstance(enfant, (ast.FunctionDef, ast.AsyncFunctionDef)):
                descendre(enfant, enfant.name, acc)
            else:
                if isinstance(enfant, ast.Return) and enfant.value is not None:
                    acc.append((porteuse, enfant))
                descendre(enfant, porteuse, acc)

    res = []
    for f in _port_modules():
        try:
            tree = ast.parse(f.read_text(encoding="utf-8"))
        except SyntaxError:
            continue
        acc = []
        descendre(tree, "<module>", acc)
        res.extend((f, nom, n) for nom, n in acc)
    return res


def rules_returned_by_port() -> dict:
    """{nom de regle: [fichier:ligne]} -- les regles que le port peut RENDRE comme code de refus.

    Critere = `int(TR.<X>)` en POSITION DE VALEUR d'un `return` (cf. `_tr_reason_codes`). C'est la
    definition OPERATIONNELLE de « portee » : le natif rend la 1re regle rompue, donc une regle que
    le port ne rend jamais ne refuse jamais (degradation PERMISSIVE)."""
    out = {}
    for f, _fn, n in _returns_du_port():
        for nom in _tr_reason_codes(n.value):
            out.setdefault(nom, []).append("%s:%d" % (f.name, n.lineno))
    return out


def rules_dropped_by_value_position() -> set:
    """{(nom, fichier, fonction)} -- les `int(TR.<X>)` sous un `return` que la POSITION DE VALEUR
    ecarte : le port les ECRIT (dans un masque, un argument...), il ne les REND pas.

    La partition `rules_returned_by_port` + celle-ci est EXHAUSTIVE par construction (difference
    d'ensembles sur le meme `return`). Elle existe pour que rien ne disparaisse en silence : un
    filtre qui ne DIT PAS ce qu'il filtre est exactement le mode de defaillance que #429 a ferme
    sur les trois inventaires qu'il remplace."""
    out = set()
    for f, fn, n in _returns_du_port():
        for nom in _tr_int_calls_anywhere(n.value) - _tr_reason_codes(n.value):
            out.add((nom, f.name, fn))
    return out


def rules_ported_by_delegation() -> dict:
    """{nom: "<fichier>:<fonction>"} -- les regles portees par DELEGATION ou par COURT-CIRCUIT.

    Le critere `int(TR.<X>)` de `rules_returned_by_port` est STRUCTURELLEMENT aveugle a quatre
    regles, parce que le NATIF ne rend jamais leur code (cf. `Role.ported_by`) : le court-circuit
    `AddCaster`, et les trois points d'extension, dont le natif rend le code de la DELEGUE.

    La derivation reste une derivation : pour chaque entree a `ported_by = (fonction, jeton)`, on
    cherche la FONCTION nommee dans les modules du port et le JETON dans SON corps -- soit un
    APPEL de ce nom, soit un `TR.<jeton>`. La granularite « fonction porteuse » n'est pas
    cosmetique : `get_dynamic_invalid_caster_reason` a DEUX foyers d'appel distincts
    (`get_invalid_caster_reason` sous le bit 2, `get_caster_not_added_reason` sous le bit 3), et un
    critere « la methode est appelee quelque part » compterait le second porte alors que seul le
    premier l'etait."""
    besoins = {n: r.ported_by for n, r in RULE_ROLE.items() if r.ported_by}
    out = {}
    for f in _port_modules():
        try:
            tree = ast.parse(f.read_text(encoding="utf-8"))
        except SyntaxError:
            continue
        fns = {n.name: n for n in ast.walk(tree)
               if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))}
        for nom, (fn_name, jeton) in besoins.items():
            fn = fns.get(fn_name)
            if fn is None or nom in out:
                continue
            appels = {n.func.attr for n in ast.walk(fn)
                      if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)}
            if jeton in appels or jeton in _tr_names(fn):
                out[nom] = "%s:%s" % (f.name, fn_name)
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
    deleguees = rules_ported_by_delegation()
    testees = rules_tested_by_port()
    gates = [n for n in noms
             if RULE_ROLE.get(n) is not None
             and RULE_ROLE[n].kind in ("GATE_TARGET", "GATE_CASTER", "GATE_ADD_CASTER")]
    portees = [n for n in gates if RULE_ROLE[n].code(n) in rendues or n in deleguees]
    print("")
    print("--- CE QUE LE PORT PORTE (derive de l'AST) ------------------------------")
    print("  regles GATE : %d ; PORTEES : %d (dont %d par DELEGATION/COURT-CIRCUIT) ; "
          "NON PORTEES : %d"
          % (len(gates), len(portees), len([n for n in portees if n in deleguees]),
             len(gates) - len(portees)))

    masks = collect_masks()
    print("  masques lisibles au registre : %d" % len(masks))

    # Un filtre DIT ce qu'il filtre : les `int(TR.<X>)` sous un `return` que la POSITION DE
    # VALEUR ecarte (le port les ECRIT, il ne les REND pas) sont NOMMES, jamais tus.
    ecartes = rules_dropped_by_value_position()
    print("  ECARTES PAR LA POSITION DE VALEUR : %d occurrence(s) -- le port les ECRIT "
          "(masque, argument), il ne les REND pas" % len(ecartes))
    for nom, fichier, fonction in sorted(ecartes):
        print("      %-42s %s::%s" % (nom, fichier, fonction))

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
            if n in deleguees:
                # Le natif ne rend JAMAIS le code de ces regles-la (court-circuit ou point
                # d'extension) : leur port se lit dans la FONCTION porteuse, pas dans un `int(TR.X)`.
                print("  %-42s %s   [DELEGATION/COURT-CIRCUIT]" % (n, deleguees[n]))
                continue
            # La cle de `rendues` est le CODE RENDU, pas le nom de la regle -- les deux different
            # des qu'une regle rend un litteral qui n'est pas le sien (`TargetIsTile` -> `1` =
            # `ValidRequest`, cf. `Role.reason_code`). `rendues[n]` levait donc un `KeyError` sur
            # cette seule entree, et le mode par defaut du probe ne rendait JAMAIS son dernier
            # bloc. Le selecteur ligne 236 employait deja `code(n)` : c'est ici qu'il manquait.
            print("  %-42s %s"
                  % (n, ", ".join(sorted(set(rendues[RULE_ROLE[n].code(n)]))[:3])))
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
