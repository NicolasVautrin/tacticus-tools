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

#: Ce qui doit changer pour que ce cliquet puisse changer d'avis.
DECLENCHEUR = {
    "chemins": ("scripts/python/probe_443r2_only_active_callsites.py",
                "scripts/python/engine/*.py", "scripts/python/engine/**/*.py"),
    "build": False,
    "toujours": False,
    "raison": (
        "Il ne lit RIEN hors d'`engine/` : l'inventaire est `ENGINE.rglob('*.py')` et les vecteurs "
        "d'inactivite aussi. Aucun import du moteur (il ne fait que le PARSER), donc pas de "
        "fermeture d'imports a couvrir -- d'ou l'absence du glob racine, contrairement aux cliquets "
        "voisins qui, eux, importent. Le verdict est la somme de l'auto-test (sources SYNTHETIQUES "
        "de son propre source) et de la conformite substrat/litteral, laquelle se decide FICHIER "
        "PAR FICHIER : une declaration `onlyActive` s'attache toujours dans la portee du call-site. "
        "Le vocabulaire (SUBSTRATS, NOEUDS_NATIFS, LITTERAL_REGIME) vit dans son propre source. "
        "Rien du build : les effectTypes sont lus par MEMBRE (`EffectType.<Nom>`), jamais par "
        "ordinal, donc `enums.tsv` n'entre pas au verdict."),
}

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

#: Substrat INLINE : une portee qui lit `EffectsState.by_unit` en direct au lieu d'appeler un
#: foyer nomme. RECENSE, jamais confronte au litteral -- et ce n'est PAS un formalisme : le gate
#: d'activite d'un substrat inline peut venir d'un AUTRE artefact natif que le `onlyActive` cite.
#: MESURE : `master_of_the_tutelaries._master_effect_is_carried_and_active` declare
#: `HasEffect(owner, 0x4ad, onlyActive=0)` ET lit `any(e.active ...)` -- le gate y mirroire le
#: couplage `DeactivateEffect -> UpdateEffectTargets(vide) -> Revert -> RemoveTriggeredAbility`
#: (#231), pas le 4e argument. Un verdict mecanique le rougirait a tort.
SUBSTRAT_INLINE = "by_unit"

#: Tokens de noeud natif. Une mention `onlyActive` qui n'en porte AUCUN parle d'autre chose que du
#: call-site du fichier (contraste, note de doctrine) -- c'est ce filtre qui separe les deux.
NOEUDS_NATIFS = ("HasEffect", "HasEffectOfType", "IsOwnerOfEffect", "IsOwnerOfEffectOfType",
                 "IsTargetOfEffect", "IsTargetOfEffectOfType", "IsEffectTarget", "HasOneOfEffects")

#: `onlyActive` suivi d'un LITTERAL. Sans litteral (`onlyActive` nu) la mention ne declare rien.
RX_DECL = re.compile(r"onlyActive\s*[:=]+\s*[`*]*(TRUE|FALSE|true|false|null|None|[01])\b")

#: Regime porte par chaque litteral. `null` = `Nullable<bool>` vide == meme octet bas que `false`.
LITTERAL_REGIME = {"0": "PRESENCE", "false": "PRESENCE", "null": "PRESENCE", "none": "PRESENCE",
                   "1": "ACTIVITE", "true": "ACTIVITE"}

#: Les deux etapes balaient le MEME arbre : sans ce cache, `engine/**` est lu et parse DEUX fois
#: (mesure : 11,3 s -> 6,0 s). Cle = chemin resolu.
_CACHE: dict = {}


def _source(path: Path) -> tuple:
    """(texte, lignes, AST) du fichier, parse UNE seule fois. AST `None` si le fichier ne parse pas
    -- l'appelant l'ecarte, il ne devine pas."""
    k = str(path)
    if k not in _CACHE:
        src = path.read_text(encoding="utf-8", errors="replace")
        try:
            tree = ast.parse(src)
        except SyntaxError:
            tree = None
        _CACHE[k] = (src, src.splitlines(), tree)
    return _CACHE[k]


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


def lectures_inline(tree: ast.AST) -> list:
    """(ligne,) de chaque lecture DIRECTE de `EffectsState.by_unit` -- le substrat re-implemente
    localement, que `appels_substrat` ne peut pas voir (il n'y a aucun appel de foyer)."""
    out = []
    for n in ast.walk(tree):
        if isinstance(n, ast.Attribute) and n.attr == SUBSTRAT_INLINE:
            out.append(n.lineno)
    return sorted(set(out))


def _docstrings(tree: ast.AST) -> list:
    """(debut, fin) de chaque docstring (module, classe, fonction). C'est l'unite de CITATION :
    une declaration `onlyActive` y est rattachable au token natif de la MEME docstring, meme si
    les deux sont a plusieurs lignes d'ecart (`components.has_effect_of_type` : token L1616,
    litteral L1620)."""
    out = []
    for n in ast.walk(tree):
        body = getattr(n, "body", None)
        if not isinstance(body, list) or not body:
            continue
        first = body[0]
        if isinstance(first, ast.Expr) and isinstance(first.value, ast.Constant) \
                and isinstance(first.value.value, str):
            out.append((first.lineno, getattr(first, "end_lineno", first.lineno) or first.lineno))
    return sorted(set(out))


def declarations_docstring(lignes: list, tree: ast.AST) -> list:
    """(debut_docstring, fin_docstring, {litteraux}) pour chaque docstring qui CITE un noeud natif
    et declare au moins un litteral. C'est le MODE 2 d'attachement -- il ne sert que si le mode 1
    (contexte immediat) n'a rien attache, et seulement si les litteraux y sont UNANIMES."""
    out = []
    for a, b in _docstrings(tree):
        bloc = "\n".join(lignes[a - 1:b])
        if not any(tok in bloc for tok in NOEUDS_NATIFS):
            continue
        lits = {m.group(1).lower() for m in RX_DECL.finditer(bloc)}
        if lits:
            out.append((a, b, lits))
    return out


RX_EFFECT_TYPE = re.compile(r"EffectType\.([A-Za-z_][A-Za-z0-9_]*)")


def constantes_effect_type(tree: ast.AST) -> dict:
    """{nom de constante MODULE -> `EffectType.<Nom>`}. Les call-sites passent une constante
    (`_MARKERLIGHT = int(EffectType.Markerlight)`), jamais le membre d'enum en clair : sans cette
    table, l'effectType interroge reste invisible."""
    out = {}
    for n in getattr(tree, "body", []):
        if not isinstance(n, ast.Assign) or len(n.targets) != 1:
            continue
        t = n.targets[0]
        if not isinstance(t, ast.Name):
            continue
        for sub in ast.walk(n.value):
            if isinstance(sub, ast.Attribute) and isinstance(sub.value, ast.Name) \
                    and sub.value.id == "EffectType":
                out[t.id] = sub.attr
                break
    return out


def _effect_types_appel(node: ast.Call, consts: dict) -> list:
    """`EffectType.<Nom>` reellement passes A CET APPEL -- membre en clair ou constante de module."""
    vus = []
    for arg in list(node.args) + [k.value for k in node.keywords]:
        for sub in ast.walk(arg):
            nom = None
            if isinstance(sub, ast.Attribute) and isinstance(sub.value, ast.Name) \
                    and sub.value.id == "EffectType":
                nom = sub.attr
            elif isinstance(sub, ast.Name) and sub.id in consts:
                nom = consts[sub.id]
            if nom and nom not in vus:
                vus.append(nom)
    return vus


def _effect_types_visibles(lignes: list, debut: int, fin: int) -> list:
    """`EffectType.<Nom>` cites dans l'intervalle -- repli quand l'appel ne porte aucun argument
    resolvable (constante locale, entier litteral)."""
    vus = []
    for ligne in lignes[max(0, debut - 1):fin]:
        for m in RX_EFFECT_TYPE.finditer(ligne):
            if m.group(1) not in vus:
                vus.append(m.group(1))
    return vus


def _effect_types_portee(lignes: list, consts: dict, debut: int, fin: int) -> list:
    """`EffectType.<Nom>` de la portee, membres EN CLAIR plus constantes de module CITEES."""
    vus = _effect_types_visibles(lignes, debut, fin)
    bloc = "\n".join(lignes[max(0, debut - 1):fin])
    for nom_const, membre in consts.items():
        if re.search(r"\b%s\b" % re.escape(nom_const), bloc) and membre not in vus:
            vus.append(membre)
    return vus


def _prend_effect_type(tree: ast.AST, debut: int) -> bool:
    """La fonction qui commence a `debut` recoit-elle son effectType en PARAMETRE ? Alors c'est un
    FOYER : l'effectType interroge n'est pas une propriete de ce call-site."""
    for n in ast.walk(tree):
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.lineno == debut:
            noms = [a.arg for a in list(n.args.args) + list(n.args.kwonlyargs)]
            return any(x in ("effect_type", "effectType", "effect_types", "requestedEffectType")
                       for x in noms)
    return False


def _attache(decls, decls_doc, portees, pdeb, pnom, lineno):
    """(litteral, ligne, mode) attache a l'appel de la ligne `lineno`, ou (None, None, None).

    MODE 1 -- contexte IMMEDIAT : la declaration la plus proche AU-DESSUS, dans la meme portee.
      C'est ce qui donne le bon verdict quand une portee porte PLUSIEURS lectures d'effet dont une
      seule est le `HasEffect` cite (`reactivate_overwatch.matches` : le `has_effect` du gate
      << rien a retirer >> precede le `active_effects` du noeud `onlyActive=true`).
    MODE 2 -- DOCSTRING de la portee : n'intervient que si le mode 1 n'a rien attache, et seulement
      si les litteraux de la docstring sont UNANIMES. Il rattrape les citations dont le token natif
      et le litteral sont a plusieurs lignes d'ecart.
    """
    cands = [d for d in decls if pdeb <= d[0] <= lineno]
    if not cands and pnom == "<module>":
        cands = [d for d in decls if d[0] <= lineno]
    if cands:
        return cands[-1][1], cands[-1][0], 1
    pfin = next((b for a, b, n in portees if a == pdeb and n == pnom), lineno)
    for a, b, lits in decls_doc:
        if pdeb <= a and b <= max(pfin, lineno) and len(lits) == 1:
            return next(iter(lits)), a, 2
    return None, None, None


def inventaire_source(src: str, rel: str) -> list:
    """Les call-sites d'UNE source : un appel de substrat (ou une lecture INLINE) + sa declaration.
    Foyer UNIQUE -- l'auto-test passe par ici, sinon il garderait un detecteur qui a diverge."""
    if not any(s in src for s in SUBSTRATS) and SUBSTRAT_INLINE not in src:
        return []
    try:
        tree = ast.parse(src)
    except SyntaxError:
        return []
    lignes = src.splitlines()
    portees = _portees(tree)
    decls = declarations(lignes)
    decls_doc = declarations_docstring(lignes, tree)
    consts = constantes_effect_type(tree)
    appels = {n.lineno: n for n in ast.walk(tree)
              if isinstance(n, ast.Call) and isinstance(getattr(n, "func", None),
                                                        (ast.Attribute, ast.Name))}
    out = []
    entrees = [(l, s, SUBSTRATS[s]) for l, s in appels_substrat(tree)]
    entrees += [(l, SUBSTRAT_INLINE, "INLINE") for l in lectures_inline(tree)]
    for lineno, substrat, regime in sorted(entrees):
        pdeb, pnom = portee_de(portees, lineno)
        lit, lit_ligne, mode = _attache(decls, decls_doc, portees, pdeb, pnom, lineno)
        pfin = next((b for a, b, n in portees if a == pdeb and n == pnom), lineno)
        node = appels.get(lineno)
        # effectType(s) interroges : d'abord les ARGUMENTS de l'appel (resolution exacte), sinon
        # la PORTEE -- un `active_effects(uid, st)` filtre son type APRES l'appel
        # (`if e.effect_type == _MARKERLIGHT`), donc l'argument seul ne dit rien.
        ets = _effect_types_appel(node, consts) if node is not None else []
        if not ets:
            ets = _effect_types_portee(lignes, consts, pdeb or 1, pfin or lineno)
        # FOYER GENERIQUE : la portee ne fixe aucun type et recoit `effect_type` en parametre --
        # l'atteignabilite s'y juge chez l'APPELANT, pas ici.
        foyer = (not ets) and _prend_effect_type(tree, pdeb)
        out.append({
            "fichier": rel, "ligne": lineno, "portee": pnom, "substrat": substrat,
            "regime_substrat": regime, "litteral": lit, "ligne_decl": lit_ligne, "mode": mode,
            "effect_types": ets, "foyer": bool(foyer),
        })
    return out


def inventaire_fichier(path: Path) -> list:
    src, _lignes, _tree = _source(path)
    return inventaire_source(src, path.relative_to(REPO).as_posix())


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
        _src, lignes, tree = _source(p)
        if tree is None:
            continue
        portees = _portees(tree)
        consts = constantes_effect_type(tree)

        def _ets(ligne: int) -> list:
            """effectType(s) du vecteur : ceux cites dans SA portee, plus ceux qu'y designent les
            constantes de module. REPLI AU FICHIER quand la portee ne fixe rien -- l'ecriture du
            flag est souvent DEPORTEE d'un cran (`_set_ranged_auto_attack_active` ecrit
            `e.active`, c'est `_ranged_auto_attack_instances` qui nomme l'effectType). La
            granularite est alors le FICHIER, et c'est assume : un vecteur mal attribue ELARGIT
            l'atteignabilite (donc n'en cache aucune), il ne la retrecit pas."""
            pdeb, pnom = portee_de(portees, ligne)
            pfin = next((b for a, b, n in portees if a == pdeb and n == pnom), ligne)
            vus = _effect_types_portee(lignes, consts, pdeb or 1, pfin or ligne)
            if not vus:
                vus = _effect_types_portee(lignes, consts, 1, len(lignes))
            return vus

        for n in ast.walk(tree):
            if isinstance(n, ast.ClassDef):
                for b in n.body:
                    if isinstance(b, (ast.FunctionDef, ast.AsyncFunctionDef)) and b.name == "is_active":
                        fin = getattr(n, "end_lineno", n.lineno) or n.lineno
                        et = _effect_types_visibles(lignes, n.lineno, fin)
                        bloc = "\n".join(lignes[n.lineno - 1:fin])
                        for nom_const, membre in consts.items():
                            if re.search(r"\b%s\b" % re.escape(nom_const), bloc) and membre not in et:
                                et.append(membre)
                        cond.append({"fichier": rel, "classe": n.name, "ligne": n.lineno,
                                     "effect_types": et})
            # `<x>.active = False` -- l'ecriture directe du flag.
            if isinstance(n, ast.Assign):
                for t in n.targets:
                    if isinstance(t, ast.Attribute) and t.attr == "active":
                        flag.append({"fichier": rel, "ligne": n.lineno,
                                     "code": lignes[n.lineno - 1].strip()[:100],
                                     "effect_types": _ets(n.lineno)})
            # `DeactivateEffect(...)` -- la feuille DSL qui ecrit `+0x5c = 0`.
            if isinstance(n, ast.Call):
                f = n.func
                nom = f.attr if isinstance(f, ast.Attribute) else (f.id if isinstance(f, ast.Name) else None)
                if nom == "DeactivateEffect":
                    flag.append({"fichier": rel, "ligne": n.lineno,
                                 "code": lignes[n.lineno - 1].strip()[:100],
                                 "effect_types": _ets(n.lineno)})
    return {"condition": cond, "flag": flag}


def atteignabilite(sites: list, vec: dict) -> list:
    """Pour chaque call-site PORTE : par quel vecteur un effet de CE type peut-il etre
    PRESENT-mais-INACTIF ? C'est la question qui decide si `onlyActive` y a un contenu OBSERVABLE.

    Trois etats, du plus fort au plus faible :
      FLAG      -- un vecteur PORTE ecrit `IsActive` a faux pour cet effectType : le regime
                   s'atteint EN JEU, sans canal special.
      CONDITION -- l'effectType a une `CreateActiveCondition` portee : l'inactivite se recalcule
                   A LA LECTURE, donc elle s'atteint en changeant l'ETAT, sans canal special.
      SEED      -- ni l'un ni l'autre cote port : reste le canal `includeInactive`, qui publie
                   l'instance inerte si le NATIF la rend inerte. Generique, jamais une preuve.
    """
    par_flag, par_cond = {}, {}
    for f in vec["flag"]:
        for t in f.get("effect_types") or []:
            par_flag.setdefault(t, []).append(f)
    for c in vec["condition"]:
        for t in c.get("effect_types") or []:
            par_cond.setdefault(t, []).append(c)
    out = []
    for s in sites:
        if s["litteral"] is None:
            continue
        ts = s["effect_types"]
        f = [t for t in ts if t in par_flag]
        c = [t for t in ts if t in par_cond]
        if f:
            etat = "FLAG"
        elif c:
            etat = "CONDITION"
        elif ts:
            etat = "SEED"
        elif s.get("foyer"):
            etat = "FOYER"          # l'effectType vient de l'APPELANT : rien a conclure ici
        else:
            etat = "INDETERMINE"
        out.append({**s, "atteignabilite": etat, "via": (f or c or ts)})
    return out


# ==========================================================================================
#  ETAPE 3 -- conformite
# ==========================================================================================

def conformite(sites: list) -> list:
    """Les call-sites PORTES dont le substrat contredit le litteral declare."""
    ko = []
    for s in sites:
        lit = s["litteral"]
        if lit is None or s["regime_substrat"] in ("TARGET", "INLINE"):
            continue                       # non declare / `IsTargetOfEffect` / substrat inline
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


_SELF_DOC_ECARTEE = '''
def _porte(state, uid):
    """`DSLTriggers$$HasEffect(sel, 1013, onlyActive, 6)` -> `HasOneOfEffects(...)`.

    Le litteral vaut ici `onlyActive = 0` : le natif ne consulte pas `IsActive @+0x5c`.
    """
    return state.effects.has_effect(uid, effect_type=1013)
'''

_SELF_INLINE = '''
def _porte(state, uid):
    """`HasEffect(Owner, 0x4cb, onlyActive: false, 6)` -- PRESENCE seule."""
    return any(e.effect_type == 0x4cb and e.active for e in state.effects.by_unit.get(uid, []))
'''


def self_test(verbose: bool) -> int:
    """Un cliquet dont le detecteur a cesse de mordre rend VERT sur un depot fautif : l'auto-test
    fait partie du verdict, il n'est pas un mode a part."""
    ko = 0
    cas = [
        ("conforme  (onlyActive true -> active_effects)", _SELF_OK, 0, "true"),
        ("fautif    (onlyActive true -> has_effect)", _SELF_KO, 1, "true"),
        ("contraste (la 2e mention ne s'attache PAS)", _SELF_CONTRASTE, 0, "false"),
        ("mode 2    (litteral loin du token, en docstring)", _SELF_DOC_ECARTEE, 0, "0"),
        ("inline    (`by_unit` + `.active` : RECENSE, jamais rouge)", _SELF_INLINE, 0, "false"),
    ]
    for nom, src, attendu, lit_attendu in cas:
        sites = inventaire_source(src, "<self>")
        got = len(conformite(sites))
        lit = sites[0]["litteral"] if sites else None
        bon = (got == attendu) and (lit == lit_attendu)
        if not bon:
            ko += 1
        if verbose or not bon:
            print("  [self-test] %s %-52s rouges attendu=%d obtenu=%d | litteral attendu=%r "
                  "obtenu=%r" % ("OK " if bon else "KO ", nom, attendu, got, lit_attendu, lit))
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

    print("\n[1] INVENTAIRE -- %d lecture(s) d'effet sous engine/, dont %d PORTE(S) "
          "(litteral `onlyActive` attache)" % (len(sites), len(declares)))
    print("    %-52s %-5s %-6s %-9s %s"
          % ("fichier::portee", "lit.", "mode", "substrat", "effectType(s)"))
    print("    " + "-" * 92)
    for s in sorted(declares, key=lambda x: (x["fichier"], x["ligne"])):
        rel = s["fichier"].replace("scripts/python/engine/", "")
        print("    %-52s %-5s %-6s %-9s %s" % (
            ("%s::%s" % (rel, s["portee"]))[:52], s["litteral"], "mode%d" % s["mode"],
            s["regime_substrat"][:9], ", ".join(s["effect_types"][:3]) or "-"))
    print("    -> %d PRESENCE (onlyActive 0/false/null), %d ACTIVITE (1/true), %d INLINE, "
          "%d branche TARGET" % (
              sum(1 for s in declares if s["regime_substrat"] == "PRESENCE"),
              sum(1 for s in declares if s["regime_substrat"] == "ACTIVITE"),
              sum(1 for s in declares if s["regime_substrat"] == "INLINE"),
              sum(1 for s in declares if s["regime_substrat"] == "TARGET")))
    print("    -> %d lecture(s) NON DECLAREE(S) (aucun noeud `HasEffect` cite en portee) -- "
          "hors gisement, residu #443-r2-c1" % len(non_dec))
    print("    -> %d lecture(s) sur la branche `IsTargetOfEffect` (active-only INCONDITIONNEL "
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

    att = atteignabilite(sites, vec)
    print("\n[3] ATTEIGNABILITE -- un etat PRESENT-mais-INACTIF est-il atteignable "
          "a chaque call-site PORTE ?")
    print("    %-52s %-5s %-11s %s" % ("fichier::portee", "lit.", "atteignable", "via"))
    print("    " + "-" * 92)
    for s in sorted(att, key=lambda x: (x["atteignabilite"] != "FLAG", x["fichier"], x["ligne"])):
        rel = s["fichier"].replace("scripts/python/engine/", "")
        via = ", ".join(dict.fromkeys(
            [v if isinstance(v, str) else (v.get("classe") or v.get("code", ""))[:34]
             for v in s["via"]])) if s["via"] else "-"
        print("    %-52s %-5s %-11s %s" % (("%s::%s" % (rel, s["portee"]))[:52], s["litteral"],
                                           s["atteignabilite"], via[:32]))
    print("    -> %d FLAG (regime atteignable EN JEU), %d CONDITION, %d SEED, %d INDETERMINE"
          % (sum(1 for s in att if s["atteignabilite"] == "FLAG"),
             sum(1 for s in att if s["atteignabilite"] == "CONDITION"),
             sum(1 for s in att if s["atteignabilite"] == "SEED"),
             sum(1 for s in att if s["atteignabilite"] == "INDETERMINE")))

    ko = conformite(sites)
    print("\n[4] CONFORMITE substrat <-> litteral -- %d ecart(s)" % len(ko))
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
