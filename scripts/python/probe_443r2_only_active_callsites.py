#!/usr/bin/env python
"""Probe #443-r2 -- le parametre `onlyActive` de `HasEffect` : inventaire DERIVE + conformite.

LA QUESTION
-----------
`IdunBattle.Entities.EntityExtensions$$HasEffect(entity, state, effectType, onlyActive)` =

    IsOwnerOfEffect(entity, state, type, onlyActive) || IsTargetOfEffect(entity, state, type)

et le 4e argument change ce que le natif REGARDE (decompile relu sur `rnca9r7q6c`) :

  * `IdunBattle.Entities.EntityExtensions$$IsOwnerOfEffect` -- boucle sur les effets PORTES ;
    `if ((char)onlyActive == 0)` -> aucune lecture d'`EffectComponent.IsActive @+0x5c` ; sinon
    `if (comp[0x5c] == 0) continue` AVANT la comparaison `comp[0x58] == requestedEffectType`.
    Le call-site `null` (`Nullable<bool>` vide) presente le meme octet bas que `false` : les
    trois litteraux `0` / `false` / `null` prennent donc la MEME branche.
  * `IdunBattle.Entities.EntityExtensions$$IsTargetOfEffect` -- balaye TOUTES les entites-effet
    du state et exige `comp[0x58] == type && comp[0x5c] != 0` INCONDITIONNELLEMENT : cette
    branche est deja active-only dans les deux regimes.

=> `HasEffect(e, T, onlyActive=0)` et `HasEffect(e, T, onlyActive=1)` DIVERGENT si et seulement si
`e` PORTE un effet de type `T` dont `IsActive` est FAUX (et n'est pas la cible d'un effet ACTIF de
ce type). Le parametre n'a donc de contenu observable que la ou un effet PRESENT-mais-INACTIF est
atteignable -- c'est exactement ce que ce probe rend mesurable.

CE QUE LE PROBE FAIT (100 % offline, aucun runner)
--------------------------------------------------
ETAPE 1 -- INVENTAIRE DES CALL-SITES, DERIVE DU CODE (jamais saisi : c'est le vice #426-r1).
  Une DECLARATION est une ligne (avec sa precedente, les citations sont multi-lignes) portant a la
  fois un TOKEN DE NOEUD NATIF (`HasEffect`, `IsOwnerOfEffect`, `IsTargetOfEffect`, ...) et
  `onlyActive` suivi d'un LITTERAL. Exiger le token ecarte mecaniquement les mentions de CONTRASTE
  -- « `onlyActive: true` ne verrait pas le marqueur qu'on vient de poser ; le natif a mis `false` »
  (`hateful_assault`) ou « ... sert les call-sites `onlyActive = 0` (le voisin) »
  (`savior_protocols`) -- qui parlent d'un AUTRE call-site que celui du fichier.
  Un CALL-SITE PORTE = un appel de SUBSTRAT (AST) auquel s'attache la declaration la plus proche
  AU-DESSUS, dans la meme portee (fonction, ou module).

ETAPE 2 -- VECTEURS D'INACTIVITE PORTES, PAR effectType. Un effet est PRESENT-mais-INACTIF si
  (a) FLAG : `EffectComponent.IsActive @+0x5c` ecrit a faux par un vecteur PORTE
      (`DeactivateEffect`, ecriture `e.active = False`) ;
  (b) CONDITION : la classe d'effet porte une `CreateActiveCondition` (surcharge de
      `BaseEffect.is_active`), reevaluee A LA LECTURE par `EffectsState.active_effects` ;
  (c) SEED : le canal `decisionView { includeInactive: true }` publie l'instance avec
      `active: false` -- generique, il ne depend d'aucun vecteur porte.
  (a) et (b) se DERIVENT du code ; (c) est structurel.

ETAPE 3 -- CONFORMITE substrat <-> litteral. Le port a DEUX substrats, et ils mirrorent des
  regimes OPPOSES de `IsOwnerOfEffect` :
      `EffectsState.has_effect`      -> filtre `consumed` seul          == onlyActive 0/false/null
      `EffectsState.active_effects`  -> `e.active` ET `e.is_active(...)` == onlyActive 1/true
  Un call-site qui lit le mauvais substrat est une divergence SILENCIEUSE : permissive dans un
  sens (le port voit un effet que le natif ignore), restrictive dans l'autre.

VERDICT FAIL si un call-site PORTE lit un substrat contraire a son litteral declare.
Les call-sites NON DECLARES sont INVENTORIES, jamais rouges : ce sont des lectures d'effet qui ne
citent aucun noeud `HasEffect` natif (stat-mods, gates de pose, ...), hors du gisement.

RESIDU NOMME `#443-r2-c1` : la conformite n'est gardee que la ou une declaration est ATTACHABLE.
Un mirror de `HasEffect` ecrit sans citer son litteral echappe a l'etape 3 -- il apparait en
`NON DECLARE` a l'etape 1, et c'est tout ce que ce probe sait en dire.

ASCII only (console Windows cp1252).
Usage: python probe_443r2_only_active_callsites.py [-v] [--self-test]
"""
from __future__ import annotations

import argparse
import ast
import re
import sys
from pathlib import Path

PYDIR = Path(__file__).resolve().parent
REPO = PYDIR.parents[1]
ENGINE = PYDIR / "engine"

# ------------------------------------------------------------------------------------------
#  Les DEUX substrats du port, et ce qu'ils mirrorent. Table de VOCABULAIRE, pas de perimetre :
#  le perimetre se derive du balayage AST.
# ------------------------------------------------------------------------------------------
#: substrat -> regime attendu du litteral natif ("PRESENCE" = onlyActive faux, "ACTIVITE" = vrai).
SUBSTRATS = {
    # `EffectsState.has_effect` et ses facades : filtre `consumed` SEUL.
    "has_effect": "PRESENCE",
    "has_effect_of_type": "PRESENCE",
    "scene_has_effect": "PRESENCE",
    "entity_has_effect": "PRESENCE",
    # `EffectsState.active_effects` : `e.active` (flag) ET `e.is_active(state)` (condition).
    "active_effects": "ACTIVITE",
    # La SECONDE branche du natif (`IsTargetOfEffect`) -- active-only INCONDITIONNELLEMENT, donc
    # son regime ne depend PAS d'`onlyActive`. Recensee, jamais confrontee au litteral.
    "is_effect_target": "TARGET",
}

#: Tokens de noeud natif. Une mention `onlyActive` qui n'en porte AUCUN parle d'autre chose que du
#: call-site du fichier (contraste, note de doctrine) -- c'est ce filtre qui separe les deux.
NOEUDS_NATIFS = ("HasEffect", "HasEffectOfType", "IsOwnerOfEffect", "IsOwnerOfEffectOfType",
                 "IsTargetOfEffect", "IsTargetOfEffectOfType", "IsEffectTarget", "HasOneOfEffects")

#: `onlyActive` suivi d'un LITTERAL. Sans litteral (`onlyActive` nu) la mention ne declare rien.
RX_DECL = re.compile(r"onlyActive\s*[:=]+\s*[`*]*(TRUE|FALSE|true|false|null|None|[01])\b")

#: Regime porte par chaque litteral. `null` = `Nullable<bool>` vide == meme octet bas que `false`.
LITTERAL_REGIME = {"0": "PRESENCE", "false": "PRESENCE", "null": "PRESENCE", "none": "PRESENCE",
                   "1": "ACTIVITE", "true": "ACTIVITE"}


# ==========================================================================================
#  Portees (AST) : a quelle fonction appartient une ligne ?
# ==========================================================================================

def _portees(tree: ast.AST) -> list:
    """(debut, fin, nom) de chaque fonction, triees. La portee la PLUS INTERNE gagne."""
    out = []
    for n in ast.walk(tree):
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)):
            out.append((n.lineno, getattr(n, "end_lineno", n.lineno) or n.lineno, n.name))
    return sorted(out)


def portee_de(portees: list, line: int) -> tuple:
    """(debut, nom) de la portee la plus interne contenant `line` ; (0, '<module>') sinon."""
    best = (0, "<module>")
    for a, b, name in portees:
        if a <= line <= b and a >= best[0]:
            best = (a, name)
    return best


# ==========================================================================================
#  ETAPE 1 -- declarations et call-sites
# ==========================================================================================

def declarations(lignes: list) -> list:
    """(ligne, litteral) de chaque DECLARATION du fichier.

    Le contexte est la ligne AVEC sa precedente : les citations de decompile sont coupees
    (`...HasEffect(entity, state, requestedEffectType,` / `onlyActive: null)...` dans
    `battle_query.scene_has_effect`), et exiger le token sur la seule ligne courante les perdrait.
    """
    out = []
    for i, ligne in enumerate(lignes, 1):
        m = RX_DECL.search(ligne)
        if not m:
            continue
        ctx = (lignes[i - 2] + " " + ligne) if i >= 2 else ligne
        if not any(tok in ctx for tok in NOEUDS_NATIFS):
            continue                       # mention de CONTRASTE : parle d'un autre call-site
        out.append((i, m.group(1).lower()))
    return out


def appels_substrat(tree: ast.AST) -> list:
    """(ligne, nom du substrat) de chaque appel AST a un substrat d'effet."""
    out = []
    for n in ast.walk(tree):
        if not isinstance(n, ast.Call):
            continue
        f = n.func
        nom = f.attr if isinstance(f, ast.Attribute) else (f.id if isinstance(f, ast.Name) else None)
        if nom in SUBSTRATS:
            out.append((n.lineno, nom))
    return sorted(out)


def _effect_types_visibles(lignes: list, debut: int, fin: int) -> list:
    """`EffectType.<Nom>` cites dans l'intervalle -- l'effectType interroge, tel que le code le
    NOMME. Derive du texte : les call-sites passent une constante de module (`_MARKERLIGHT`), dont
    la definition porte l'`EffectType`."""
    rx = re.compile(r"EffectType\.([A-Za-z_][A-Za-z0-9_]*)")
    vus = []
    for ligne in lignes[max(0, debut - 1):fin]:
        for m in rx.finditer(ligne):
            if m.group(1) not in vus:
                vus.append(m.group(1))
    return vus


def inventaire_fichier(path: Path) -> list:
    """Les call-sites PORTES du fichier : un appel de substrat + la declaration attachee."""
    src = path.read_text(encoding="utf-8", errors="replace")
    if not any(s in src for s in SUBSTRATS):
        return []
    try:
        tree = ast.parse(src)
    except SyntaxError:
        return []
    lignes = src.splitlines()
    portees = _portees(tree)
    decls = declarations(lignes)
    rel = path.relative_to(REPO).as_posix()
    out = []
    for lineno, substrat in appels_substrat(tree):
        pdeb, pnom = portee_de(portees, lineno)
        # La declaration ATTACHEE = la plus proche AU-DESSUS, DANS LA MEME PORTEE. Hors portee
        # (une declaration d'en-tete pour un appel de methode) elle n'est pas attachee : elle
        # decrit l'arbre natif du fichier, pas ce call-site precis.
        cands = [d for d in decls if pdeb <= d[0] <= lineno]
        decl = cands[-1] if cands else None
        # Le module entier fait portee pour un appel module-level.
        if decl is None and pnom == "<module>":
            cands = [d for d in decls if d[0] <= lineno]
            decl = cands[-1] if cands else None
        pfin = next((b for a, b, n in portees if a == pdeb and n == pnom), lineno)
        out.append({
            "fichier": rel, "ligne": lineno, "portee": pnom, "substrat": substrat,
            "regime_substrat": SUBSTRATS[substrat],
            "litteral": decl[1] if decl else None,
            "ligne_decl": decl[0] if decl else None,
            "effect_types": _effect_types_visibles(lignes, pdeb or 1, pfin or lineno),
        })
    return out


# ==========================================================================================
#  ETAPE 2 -- vecteurs d'INACTIVITE portes
# ==========================================================================================

def vecteurs_inactivite() -> dict:
    """{"condition": [...], "flag": [...]} -- ce qui, DANS LE PORT, peut rendre un effet
    PRESENT-mais-INACTIF.

    * CONDITION : une classe d'effet qui surcharge `is_active` porte une `CreateActiveCondition`
      native, reevaluee A CHAQUE LECTURE par `EffectsState.active_effects`. L'inactivite y est
      donc atteignable SANS aucun canal special : il suffit que l'etat sorte de la condition.
    * FLAG : une ecriture de `EffectComponent.IsActive @+0x5c` a faux -- feuille `DeactivateEffect`
      portee, ou affectation directe `<eff>.active = False`.
    """
    cond, flag = [], []
    for p in sorted((PYDIR / "engine").rglob("*.py")):
        rel = p.relative_to(REPO).as_posix()
        src = p.read_text(encoding="utf-8", errors="replace")
        try:
            tree = ast.parse(src)
        except SyntaxError:
            continue
        lignes = src.splitlines()
        for n in ast.walk(tree):
            if isinstance(n, ast.ClassDef):
                for b in n.body:
                    if isinstance(b, (ast.FunctionDef, ast.AsyncFunctionDef)) and b.name == "is_active":
                        et = _effect_types_visibles(lignes, n.lineno,
                                                    getattr(n, "end_lineno", n.lineno) or n.lineno)
                        cond.append({"fichier": rel, "classe": n.name, "ligne": n.lineno,
                                     "effect_types": et})
            # `<x>.active = False` -- l'ecriture directe du flag.
            if isinstance(n, ast.Assign):
                for t in n.targets:
                    if isinstance(t, ast.Attribute) and t.attr == "active":
                        flag.append({"fichier": rel, "ligne": n.lineno,
                                     "code": lignes[n.lineno - 1].strip()[:100]})
            # `DeactivateEffect(...)` -- la feuille DSL qui ecrit `+0x5c = 0`.
            if isinstance(n, ast.Call):
                f = n.func
                nom = f.attr if isinstance(f, ast.Attribute) else (f.id if isinstance(f, ast.Name) else None)
                if nom == "DeactivateEffect":
                    flag.append({"fichier": rel, "ligne": n.lineno,
                                 "code": lignes[n.lineno - 1].strip()[:100]})
    return {"condition": cond, "flag": flag}


# ==========================================================================================
#  ETAPE 3 -- conformite
# ==========================================================================================

def conformite(sites: list) -> list:
    """Les call-sites PORTES dont le substrat contredit le litteral declare."""
    ko = []
    for s in sites:
        lit = s["litteral"]
        if lit is None or s["regime_substrat"] == "TARGET":
            continue                       # non declare, ou branche `IsTargetOfEffect`
        attendu = LITTERAL_REGIME.get(lit)
        if attendu and attendu != s["regime_substrat"]:
            ko.append(s)
    return ko


# ==========================================================================================
#  AUTO-TEST -- un cliquet dont le detecteur a cesse de mordre rend VERT sur un depot fautif.
# ==========================================================================================

_SELF_OK = '''
def _porte(scene, uid):
    """`EntityExtensions.HasEffect(target, state, 1122, onlyActive: true)` -- mirror."""
    return any(e.effect_type == 1122 for e in scene.eff_state.active_effects(uid, None))
'''

_SELF_KO = '''
def _porte(scene, uid):
    """`EntityExtensions.HasEffect(target, state, 1122, onlyActive: true)` -- mirror."""
    return scene.eff_state.has_effect(uid, effect_type=1122)
'''

_SELF_CONTRASTE = '''
def _porte(scene, uid):
    """`HasEffect(Actor, 0x497, onlyActive: false, Both)` -- PRESENCE seule.

    `onlyActive: true` ne verrait pas le marqueur qu'on vient de poser.
    """
    return scene.eff_state.has_effect(uid, effect_type=0x497)
'''


def _analyse_source(src: str) -> list:
    tree = ast.parse(src)
    lignes = src.splitlines()
    portees = _portees(tree)
    decls = declarations(lignes)
    out = []
    for lineno, substrat in appels_substrat(tree):
        pdeb, pnom = portee_de(portees, lineno)
        cands = [d for d in decls if pdeb <= d[0] <= lineno]
        decl = cands[-1] if cands else None
        out.append({"fichier": "<self>", "ligne": lineno, "portee": pnom, "substrat": substrat,
                    "regime_substrat": SUBSTRATS[substrat],
                    "litteral": decl[1] if decl else None,
                    "ligne_decl": decl[0] if decl else None, "effect_types": []})
    return out


def self_test(verbose: bool) -> int:
    ko = 0
    cas = [
        ("conforme (onlyActive true -> active_effects)", _SELF_OK, 0),
        ("fautif   (onlyActive true -> has_effect)", _SELF_KO, 1),
        ("contraste (la 2e mention ne doit PAS s'attacher)", _SELF_CONTRASTE, 0),
    ]
    for nom, src, attendu in cas:
        sites = _analyse_source(src)
        got = len(conformite(sites))
        etat = "OK " if got == attendu else "KO "
        if got != attendu:
            ko += 1
        if verbose or got != attendu:
            print("  [self-test] %s %-52s attendu=%d obtenu=%d" % (etat, nom, attendu, got))
    # Le cas CONTRASTE doit en plus avoir attache le litteral `false`, pas `true`.
    s = _analyse_source(_SELF_CONTRASTE)
    lit = s[0]["litteral"] if s else None
    if lit != "false":
        print("  [self-test] KO  le litteral attache au cas CONTRASTE est %r, attendu 'false'" % lit)
        ko += 1
    elif verbose:
        print("  [self-test] OK  litteral attache au cas CONTRASTE = 'false'")
    return ko


# ==========================================================================================
#  main
# ==========================================================================================

def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("-v", "--verbose", action="store_true",
                    help="imprime l'inventaire COMPLET (call-sites non declares inclus)")
    ap.add_argument("--self-test", action="store_true", help="auto-test des detecteurs seul")
    args = ap.parse_args()

    print("=" * 92)
    print("PROBE #443-r2 -- `onlyActive` : inventaire DERIVE des call-sites + conformite")
    print("=" * 92)

    print("\n[0] AUTO-TEST des detecteurs")
    ko_self = self_test(args.verbose or args.self_test)
    print("    %s (%d ecart(s))" % ("OK" if ko_self == 0 else "ROUGE", ko_self))
    if args.self_test:
        return 1 if ko_self else 0

    sites = []
    for p in sorted(ENGINE.rglob("*.py")):
        sites.extend(inventaire_fichier(p))

    declares = [s for s in sites if s["litteral"] is not None]
    non_dec = [s for s in sites if s["litteral"] is None]
    cibles = [s for s in sites if s["regime_substrat"] == "TARGET"]

    print("\n[1] INVENTAIRE -- %d appel(s) de substrat sous engine/, dont %d PORTE(S) "
          "(litteral attache)" % (len(sites), len(declares)))
    print("    %-58s %-6s %-9s %s" % ("fichier::portee", "lit.", "substrat", "effectType(s) cites"))
    print("    " + "-" * 86)
    for s in sorted(declares, key=lambda x: (x["fichier"], x["ligne"])):
        rel = s["fichier"].replace("scripts/python/engine/", "")
        print("    %-58s %-6s %-9s %s" % (
            ("%s::%s" % (rel, s["portee"]))[:58], s["litteral"],
            "PRESENCE" if s["regime_substrat"] == "PRESENCE" else s["regime_substrat"][:9],
            ", ".join(s["effect_types"][:4]) or "-"))
    print("    -> %d call-site(s) PRESENCE (onlyActive 0/false/null), %d ACTIVITE (1/true), "
          "%d branche TARGET" % (
              sum(1 for s in declares if s["regime_substrat"] == "PRESENCE"),
              sum(1 for s in declares if s["regime_substrat"] == "ACTIVITE"),
              sum(1 for s in declares if s["regime_substrat"] == "TARGET")))
    print("    -> %d appel(s) NON DECLARE(S) (aucun noeud `HasEffect` cite en portee) -- "
          "hors gisement, residu #443-r2-c1" % len(non_dec))
    print("    -> %d appel(s) sur la branche `IsTargetOfEffect` (active-only INCONDITIONNEL "
          "cote natif : `onlyActive` ne la traverse pas)" % len(cibles))
    if args.verbose:
        print("\n    --- NON DECLARES ---")
        for s in sorted(non_dec, key=lambda x: (x["fichier"], x["ligne"])):
            rel = s["fichier"].replace("scripts/python/engine/", "")
            print("      %-62s L%-5d %s" % (("%s::%s" % (rel, s["portee"]))[:62],
                                            s["ligne"], s["substrat"]))

    vec = vecteurs_inactivite()
    print("\n[2] VECTEURS D'INACTIVITE PORTES -- ce qui rend un effet PRESENT-mais-INACTIF")
    print("    CONDITION (`is_active` surcharge = `CreateActiveCondition` portee) : %d classe(s)"
          % len(vec["condition"]))
    for c in sorted(vec["condition"], key=lambda x: (x["fichier"], x["ligne"])):
        rel = c["fichier"].replace("scripts/python/engine/", "")
        print("      %-46s %-38s %s" % (rel[:46], c["classe"][:38],
                                        ", ".join(c["effect_types"][:3]) or "-"))
    print("    FLAG (`DeactivateEffect` / `<eff>.active = ...`) : %d site(s)" % len(vec["flag"]))
    for f in sorted(vec["flag"], key=lambda x: (x["fichier"], x["ligne"])):
        rel = f["fichier"].replace("scripts/python/engine/", "")
        print("      %-46s L%-5d %s" % (rel[:46], f["ligne"], f["code"][:44]))
    print("    SEED : canal `decisionView { includeInactive: true }` "
          "(`runner/snapshot.py::decision_view_seed_body`) -- GENERIQUE, tout effectType.")

    ko = conformite(sites)
    print("\n[3] CONFORMITE substrat <-> litteral -- %d ecart(s)" % len(ko))
    for s in ko:
        rel = s["fichier"].replace("scripts/python/engine/", "")
        print("      ROUGE %s::%s L%d -- litteral `onlyActive=%s` (regime %s) mais substrat "
              "`%s` (regime %s)" % (rel, s["portee"], s["ligne"], s["litteral"],
                                    LITTERAL_REGIME.get(s["litteral"]), s["substrat"],
                                    s["regime_substrat"]))

    rc = ko_self + len(ko)
    print("\n" + "=" * 92)
    print("VERDICT: %s -- auto-test %d ecart(s), conformite %d ecart(s)"
          % ("FAIL" if rc else "PASS", ko_self, len(ko)))
    print("=" * 92)
    return rc


if __name__ == "__main__":
    sys.exit(main())
