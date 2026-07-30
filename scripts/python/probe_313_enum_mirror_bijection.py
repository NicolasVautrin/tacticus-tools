#!/usr/bin/env python3
"""#313 -- les mirrors `IntEnum` du moteur sont-ils en BIJECTION avec `enums.tsv` ?

LA QUESTION BINAIRE
-------------------
Pour chaque classe `IntEnum` du port qui recopie un enum natif : l'ensemble de ses membres
coincide-t-il EXACTEMENT avec celui de `data/symbols/<CURRENT>/frida/enums.tsv`, **dans les deux
sens** ? Le second sens est celui qu'on oublie, et c'est celui qui produit du code mort qui a
l'air vivant.

LES TROIS SENS, ET POURQUOI AUCUN CLIQUET NE LES COUVRAIT
----------------------------------------------------------
  MANQUANT   -- valeur du jeu absente du port. Le port ne SAIT PAS nommer ce que le jeu emet.
                C'est le trou de #313 : 8 ids de `TriggeredAbilityType` presents dans le build
                `rnca9r7q6c` et absents du mirror. La degradation est MUETTE tant qu'aucun
                playbook porte ne lit ces ids -- et c'est ce qui la rend durable.
  MORT       -- valeur du port absente du jeu. Aucune erreur, jamais : le jeu ne l'emet pas. Ce
                sont des membres qui ONT L'AIR vivants, qu'un solveur peut citer de bonne foi.
                #270 en avait compte 75 sur `ActiveAbilityType`.
  RENUMEROTE -- meme valeur, autre nom. Le pire : il resout, pointe ailleurs, rien ne proteste.

Le cliquet #283 (`probe_283_enum_ordinal_sweep.step_mirror`) ne verifie QUE le troisieme sens, et
seulement sur ses quatre enums : il compare `ref.get(membre) != valeur` pour les membres PRESENTS
dans le mirror -- un membre que le port n'a pas ne peut pas diverger, il est invisible. Le cliquet
#275 (`probe_275_enum_maps_drift`) fait bien les trois sens, mais sur `enum_maps.py` UNIQUEMENT :
son etape 4 range explicitement les mirrors `engine/entities/*_type.py` en " informatif, hors
perimetre ". Personne ne gardait donc les mirrors du MOTEUR -- ceux que le code executable lit.

CE QUE LA SONDE FAIT
--------------------
  Etape 1  DECOUVERTE : toute classe `IntEnum`/`IntFlag` sous `scripts/python/engine/` est classee
           -- APPARIEE (mapping explicite vers une cle de `enums.tsv`) ou HORS-MIRROR (justifiee).
           Une classe ni l'une ni l'autre est un ECART BLOQUANT : c'est par la que le trou se
           re-creuse. L'appariement est LU, jamais devine -- le nom court ne suffit pas
           (`UtilityType` vit dans `IdunBattle.Configuration`, pas `IdunBattle.Entities.Enum`), et
           un appariement au juge produirait un diff massif et FAUX.
  Etape 2  BIJECTION par mirror apparie : manquants / morts / renumerotes.
  Etape 3  REFERENCES QUALIFIEES : chaque `<Classe>.<membre>` ecrit dans du Python suivi doit
           (a) resoudre dans le mirror -- sinon `AttributeError` a l'execution -- et (b) pour un
           mirror STRICT, designer un membre que le BUILD COURANT connait encore. (b) est le
           garde-fou du piege #270 : c'est lui qui dit si un membre mort peut etre retire sans
           casser du code vivant, et lui qui rattrape une citation devenue fausse.
  Etape 4  PORTEURS (`--porteurs`) : le mirror n'est pas qu'une table, c'est un DICTIONNAIRE
           consomme par nom -- `triggered_ability_ids()` fait
           `TriggeredAbilityType.__members__.get(nom_gameconfig)` et jette silencieusement ce
           qu'il ne connait pas (`if m is not None`). Un membre manquant n'est donc pas inerte :
           il RETIRE des passifs du kit porte. L'etape confronte donc le mirror au gameconfig
           dans les deux sens -- quelles unites portent un membre MANQUANT (la file de portage),
           et quel membre MORT le gameconfig nommerait encore (aucun ne doit l'etre, sinon le
           retirer casserait la conversion).

Sortie 0 = tous les mirrors SOUS GARDE sont bijectifs et toutes les references resolvent ; 1 sinon.
ASCII only (console Windows cp1252).
"""
from __future__ import annotations

import argparse
import ast
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "scripts"/"python"))

from symbols_layout import build_dir, current_build  # noqa: E402

PY = REPO / "scripts"/"python"
ENGINE = PY / "engine"

# Attributs qui ne designent PAS un membre : l'API `Enum` elle-meme.
API_ENUM = {"name", "value", "_value_", "_name_", "_member_map_", "_missing_",
            "__members__", "__name__", "__doc__", "__class__", "mro"}


class Mirror:
    """Une entree du registre. Les champs sont LUS, jamais devines.

    strict  -- les NOMS du port doivent etre ceux du jeu. Faux pour `StatType`, dont le port
               reconventionne (`CRIT_CHANCE` pour `CriticalChance`, UPPER_CASE partout) : sa
               docstring le declare, et la garde y porte sur les VALEURS seules.
    garde   -- la bijection doit etre PARFAITE (le cliquet rougit sinon).
    dette   -- (manquants, morts, renumerotes) EXACTS pour un mirror hors garde. Le compte est
               fige et controle DANS LES DEUX SENS : il rougit si la dette s'aggrave, et il
               rougit aussi si elle est resorbee -- auquel cas la reponse est de passer le
               mirror SOUS GARDE, pas de rafraichir le nombre.
    """

    def __init__(self, cls, rel, cle, strict=True, garde=True, dette=None, raison=""):
        self.cls, self.rel, self.cle = cls, rel, cle
        self.strict, self.garde, self.dette, self.raison = strict, garde, dette, raison


# ---------------------------------------------------------------------------- le registre
REGISTRE: list[Mirror] = [
    # --- SOUS GARDE : bijection parfaite exigee.
    Mirror("ActiveAbilityType", "engine/entities/active_ability_type.py",
           "IdunBattle.Entities.Enum.ActiveAbilityType"),
    Mirror("TriggeredAbilityType", "engine/entities/triggered_ability_type.py",
           "IdunBattle.Entities.Enum.TriggeredAbilityType"),
    Mirror("DamageProfileType", "engine/entities/damage_profile_type.py",
           "IdunBattle.Entities.Enum.DamageProfileType"),
    Mirror("UnitTrait", "engine/entities/traits/unit_trait.py",
           "IdunBattle.Entities.Enum.UnitTrait"),
    Mirror("UnitFaction", "engine/entities/unit_faction.py",
           "IdunBattle.Entities.Enum.UnitFaction"),
    Mirror("DamageTrait", "engine/entities/damage_trait.py",
           "IdunBattle.Entities.Enum.DamageTrait"),
    Mirror("EventTriggerType", "engine/dsl/event_trigger_type.py",
           "IdunBattle.DSL.EventTriggerType"),
    Mirror("StatType", "engine/entities/stats.py",
           "IdunBattle.Entities.Enum.StatType", strict=False,
           raison="port UPPER_CASE + abreviations (CRIT_CHANCE <- CriticalChance) : convention "
                  "declaree dans sa docstring ; la garde porte sur les VALEURS"),
    # #318 : les deux dernieres dettes declarees par #313 sont RESORBEES et passent sous garde.
    # `EffectType` (20 manquants, 73 morts, 2 RENUMEROTES) et `UtilityType` (15 manquants) ont ete
    # regeneres par `regen_enum_mirrors.py`. La forme qui comptait est le RENUMEROTE : 1563/1564
    # rendaient `DA_Hero6_Passive_1`/`_2`, placeholders absents des DEUX builds versionnes, la ou
    # le jeu dit `SpecialIssueCombiMelta_AdditionalHits` / `_ExtraDmg` -- il RESOLVAIT et pointait
    # ailleurs. Memes placeholders que ceux corriges dans `TriggeredAbilityType` par la case-219.
    Mirror("EffectType", "engine/entities/effect_type.py",
           "IdunBattle.Entities.Enum.EffectType"),
    Mirror("UtilityType", "engine/utilities/utility_type.py",
           "IdunBattle.Configuration.UtilityType"),
]

# HORS-MIRROR : classes `IntEnum`/`IntFlag` du moteur qui ne recopient AUCUN enum natif. Chacune
# porte sa raison -- c'est ce qui interdit d'y ranger un vrai mirror "parce qu'il derive".
HORS_MIRROR: dict[str, str] = {
    "StatPart": "decomposition maison d'un stat (Current/Initial/Modification/Override) -- "
                "l'enum natif homonyme n'existe pas dans enums.tsv",
    "TargetingRule": "IntFlag maison : les BITS du masque `TargetingOptions`, pas un enum natif",
}

PAR_CLS = {m.cls: m for m in REGISTRE}


# ------------------------------------------------------------------------- sources natives

def enum_natif(build: str, cle: str) -> dict[int, set[str]]:
    """{valeur: {noms}} depuis `data/symbols/<build>/frida/enums.tsv`.

    Un ENSEMBLE de noms : plusieurs membres partagent parfois une valeur (mesure sur
    `ActiveAbilityType` : 9999 porte `STRIPPED` ET `testAssetBundles`). Comparer a un nom UNIQUE
    ferait crier le cliquet sur une table pourtant juste."""
    p = build_dir(build) / "frida"/"enums.tsv"
    for ligne in p.open(encoding="utf-8"):
        if ligne.startswith(cle + "\t"):
            out: dict[int, set[str]] = {}
            for paire in ligne.rstrip("\n").split("\t", 1)[1].split(","):
                v, _, n = paire.partition("=")
                if n:
                    try:
                        out.setdefault(int(v), set()).add(n)
                    except ValueError:
                        pass
            return out
    raise SystemExit("cle absente de enums.tsv : %s" % cle)


# --------------------------------------------------------------------------------- le depot

def _echappe(nom: str) -> str:
    """`None_` -> `None` : le mirror echappe le mot-clef Python, le jeu ne l'echappe pas."""
    return nom[:-1] if nom == "None_" else nom


def classes_intenum(tree: ast.Module) -> dict[str, dict[int, set[str]]]:
    """{classe: {valeur: {noms}}} pour chaque `IntEnum`/`IntFlag` d'un arbre.

    Lu par AST, pas par regex : un `IntEnum` declare des ALIAS (deux noms, meme valeur), et une
    table `{valeur: nom}` en ecraserait un en silence -- exactement le motif qu'on traque."""
    out: dict[str, dict[int, set[str]]] = {}
    for node in ast.walk(tree):
        if not isinstance(node, ast.ClassDef):
            continue
        bases = {b.id for b in node.bases if isinstance(b, ast.Name)}
        bases |= {b.attr for b in node.bases if isinstance(b, ast.Attribute)}
        if not (bases & {"IntEnum", "IntFlag"}):
            continue
        membres: dict[int, set[str]] = {}
        for st in node.body:
            if not (isinstance(st, ast.Assign) and len(st.targets) == 1
                    and isinstance(st.targets[0], ast.Name)):
                continue
            v, nom = st.value, _echappe(st.targets[0].id)
            if isinstance(v, ast.Constant) and isinstance(v.value, int) \
                    and not isinstance(v.value, bool):
                membres.setdefault(v.value, set()).add(nom)
            elif isinstance(v, ast.UnaryOp) and isinstance(v.op, ast.USub) \
                    and isinstance(v.operand, ast.Constant) \
                    and isinstance(v.operand.value, int):
                membres.setdefault(-v.operand.value, set()).add(nom)
        if membres:
            out[node.name] = membres
    return out


def membres_mirror(rel: str, cls: str) -> dict[int, set[str]]:
    p = PY / rel
    if not p.is_file():
        return {}
    return classes_intenum(ast.parse(p.read_text(encoding="utf-8"), filename=rel)).get(cls, {})


def intenums_du_moteur() -> dict[str, str]:
    """{classe: chemin relatif a scripts/python} -- TOUTE classe `IntEnum`/`IntFlag` sous
    `engine/`. C'est l'etape qui empeche le trou de se re-creuser : un mirror ajoute demain sans
    entrer au registre est signale, au lieu d'echapper silencieusement a la garde."""
    out: dict[str, str] = {}
    for p in sorted(ENGINE.rglob("*.py")):
        rel = p.relative_to(PY).as_posix()
        try:
            tree = ast.parse(p.read_text(encoding="utf-8"), filename=rel)
        except (SyntaxError, UnicodeDecodeError, OSError):
            continue
        for cls in classes_intenum(tree):
            out[cls] = rel
    return out


# ------------------------------------------------------------------------------ le calcul

def bijection(port: dict[int, set[str]], jeu: dict[int, set[str]],
              strict: bool = True) -> tuple[list, list, list]:
    """(manquants, morts, renumerotes) -- LE calcul du cliquet, isole pour qu'un test puisse le
    nourrir de tables truquees et verifier qu'il MORD.

    manquants   : [(valeur, noms du jeu)]   -- le jeu les emet, le port ne sait pas les nommer
    morts       : [(valeur, noms du port)]  -- le port les cite, le jeu ne les emet plus
    renumerotes : [(valeur, nom du port, noms du jeu)] -- meme valeur, le port nomme AUTRE CHOSE

    Un ALIAS n'est PAS une derive : le port n'a pas besoin de porter tous les noms d'une valeur
    (le jeu donne 9999 = {STRIPPED, testAssetBundles}), il doit seulement n'en porter AUCUN de
    faux -- d'ou l'inclusion `noms_port <= noms_jeu`, jamais l'egalite.

    `strict=False` : la garde porte sur les VALEURS seules (mirror qui reconventionne ses noms).
    """
    manquants = [(v, sorted(jeu[v])) for v in sorted(set(jeu) - set(port))]
    morts = [(v, sorted(port[v])) for v in sorted(set(port) - set(jeu))]
    renum = ([(v, n, sorted(jeu[v])) for v in sorted(set(port) & set(jeu))
              for n in sorted(port[v]) if n not in jeu[v]] if strict else [])
    return manquants, morts, renum


# ---------------------------------------------------------- etape 3 : references qualifiees

def fichiers_python_suivis() -> list[str]:
    out = subprocess.run(["git", "-C", str(REPO), "ls-files", "*.py"],
                         capture_output=True, text=True, encoding="utf-8").stdout
    return [x for x in out.splitlines() if x.endswith(".py")]


def references_qualifiees() -> list[tuple[str, int, str, str]]:
    """[(fichier, ligne, classe, membre)] -- chaque `<Classe>.<membre>` ecrit dans du Python suivi.

    AST, pas regex : les exemples de docstring (`TriggeredAbilityType.X` dans
    `audit_passive_ability_coverage.py`) sont du TEXTE, pas du code -- les compter ferait un faux
    positif permanent, et les exclure a la main serait une allowlist de plus a maintenir."""
    out = []
    for rel in fichiers_python_suivis():
        p = REPO / rel
        if not p.is_file():
            continue
        try:
            tree = ast.parse(p.read_text(encoding="utf-8"), filename=rel)
        except (SyntaxError, UnicodeDecodeError, OSError):
            continue
        for node in ast.walk(tree):
            if (isinstance(node, ast.Attribute) and isinstance(node.value, ast.Name)
                    and node.value.id in PAR_CLS and node.attr not in API_ENUM
                    and not node.attr.startswith("_")):
                out.append((rel, node.lineno, node.value.id, node.attr))
    return out


def references_cassees(build: str) -> tuple[list, list]:
    """(introuvables, mortes).

    introuvables : la reference ne resout meme pas dans le mirror -> `AttributeError` a
                   l'execution. C'est ce qui arriverait si on retirait un membre encore cite.
    mortes       : elle resout dans le mirror, mais le BUILD COURANT ne connait plus ce nom ->
                   du code qui a l'air vivant et ne peut plus rien matcher. Piege #270.
    """
    noms_port = {m.cls: {n for ns in membres_mirror(m.rel, m.cls).values() for n in ns}
                 for m in REGISTRE}
    noms_jeu = {m.cls: {n for ns in enum_natif(build, m.cle).values() for n in ns}
                for m in REGISTRE}
    introuvables, mortes = [], []
    for rel, k, cls, membre in references_qualifiees():
        if _echappe(membre) not in noms_port[cls]:
            introuvables.append((rel, k, cls, membre))
        elif PAR_CLS[cls].strict and _echappe(membre) not in noms_jeu[cls]:
            mortes.append((rel, k, cls, membre))
    return introuvables, mortes


# -------------------------------------------------------------------- etape 4 : porteurs

# Quelle liste du gameconfig alimente quel mirror. `TriggeredAbilityType` <- `passiveAbilities`
# (le namespace natif est `Abilities.Triggered.Loki.*Ability`), `ActiveAbilityType` <-
# `activeAbilities`. Les autres mirrors ne sont pas nommes par le gameconfig.
LISTE_GAMECONFIG = {
    "TriggeredAbilityType": "passiveAbilities",
    "ActiveAbilityType": "activeAbilities",
}


def porteurs_par_nom(champ: str) -> dict[str, list[tuple[str, str]]]:
    """{nom d'ability: [(unite, kind)]} depuis le gameconfig du build courant.

    `kind` vient de `gameconfig.unit()` : lineup / npc / summons. Il VENTILE, il ne TRANCHE pas --
    la gate hero/MoW est `rl_duel build --list-pool`, jamais `kind == lineup` (qui ment). Un
    porteur `summons` est confrontable malgre son absence du pool (on spawne son summoner)."""
    import gameconfig as GC
    idx = GC._index()
    out: dict[str, list[tuple[str, str]]] = {}
    for kind in ("lineup", "npc", "summons"):
        for uid, u in (idx.get(kind) or {}).items():
            for nom in (u.get(champ) or []):
                out.setdefault(nom, []).append((uid, kind))
    return out


def etape_porteurs(build: str) -> int:
    print("ETAPE 4 -- PORTEURS (gameconfig du build %s)" % build)
    rouge = 0
    for m in REGISTRE:
        champ = LISTE_GAMECONFIG.get(m.cls)
        if champ is None:
            continue
        port = membres_mirror(m.rel, m.cls)
        jeu = enum_natif(build, m.cle)
        manquants, morts, _ = bijection(port, jeu, m.strict)
        pn = porteurs_par_nom(champ)
        print("  %s <- gameconfig.%s" % (m.cls, champ))
        for v, ns in manquants:
            for n in ns:
                ps = pn.get(n) or []
                kinds = sorted({k for _, k in ps})
                print("    MANQUANT %-6d %-44s porteurs=%d %s"
                      % (v, n, len(ps),
                         ("[%s] %s" % (",".join(kinds),
                                       ", ".join(u for u, _ in ps[:6])))
                         if ps else "-- AUCUN porteur au gameconfig"))
        nommes = [(v, n) for v, ns in morts for n in ns if n in pn]
        print("    membres MORTS encore nommes par le gameconfig : %d %s"
              % (len(nommes), nommes[:8] if nommes else ""))
        rouge += len(nommes)
    print("")
    return rouge


# ------------------------------------------------------------------------------ la sortie

def rapport(verbose: bool, porteurs: bool = False) -> int:
    build = current_build()
    print("build : %s" % build)
    print("")
    rouge = 0

    # ---- Etape 1 : decouverte
    trouves = intenums_du_moteur()
    orphelins = sorted(c for c in trouves if c not in PAR_CLS and c not in HORS_MIRROR)
    absents = sorted(m.cls for m in REGISTRE if m.cls not in trouves)
    print("ETAPE 1 -- DECOUVERTE : %d classe(s) IntEnum/IntFlag sous engine/" % len(trouves))
    print("  APPARIEES=%d  HORS-MIRROR=%d  ORPHELINES=%d"
          % (sum(1 for c in trouves if c in PAR_CLS),
             sum(1 for c in trouves if c in HORS_MIRROR), len(orphelins)))
    for c in orphelins:
        print("  ORPHELINE %-24s %s -- ni apparie, ni justifie HORS-MIRROR" % (c, trouves[c]))
    for c in absents:
        print("  AU REGISTRE MAIS INTROUVABLE : %s (%s)" % (c, PAR_CLS[c].rel))
    rouge += len(orphelins) + len(absents)
    print("")

    # ---- Etape 2 : bijection
    print("ETAPE 2 -- BIJECTION mirror <-> enums.tsv (les DEUX sens)")
    for m in sorted(REGISTRE, key=lambda x: (not x.garde, x.cls)):
        port = membres_mirror(m.rel, m.cls)
        if not port:
            print("  ROUGE  %-22s classe introuvable dans %s" % (m.cls, m.rel))
            rouge += 1
            continue
        jeu = enum_natif(build, m.cle)
        manquants, morts, renum = bijection(port, jeu, m.strict)
        compte = (len(manquants), len(morts), len(renum))
        if m.garde:
            etat = "OK"if compte == (0, 0, 0) else"ROUGE"
            tag = "[SOUS GARDE]" + (""if m.strict else" valeurs seules")
            rouge += 0 if compte == (0, 0, 0) else 1
        else:
            etat = "dette"if compte == m.dette else"ROUGE"
            tag = "[dette declaree %s]" % (m.dette,)
            rouge += 0 if compte == m.dette else 1
        print("  %-6s %-22s port=%-4d jeu=%-4d  MANQUANTS=%-4d MORTS=%-4d RENUMEROTES=%-3d %s"
              % (etat, m.cls, len(port), len(jeu), *compte, tag))
        if verbose or (m.garde and compte != (0, 0, 0)):
            for v, ns in manquants[:12]:
                print("           MANQUANT   %-6d le jeu dit %s"% (v,",".join(ns)))
            if len(manquants) > 12:
                print("           ... %d manquant(s) de plus" % (len(manquants) - 12))
            for v, ns in morts[:12]:
                print("           MORT       %-6d le port dit %s"% (v,",".join(ns)))
            if len(morts) > 12:
                print("           ... %d mort(s) de plus" % (len(morts) - 12))
            for v, n, ns in renum[:8]:
                print("           RENUMEROTE %-6d le port dit %-32s le jeu dit %s"
                      % (v, n, ",".join(ns)))
    print("")

    # ---- Etape 3 : references qualifiees
    introuvables, mortes = references_cassees(build)
    print("ETAPE 3 -- REFERENCES QUALIFIEES `<Classe>.<membre>` dans du Python suivi")
    print("  total=%d  INTROUVABLES=%d (AttributeError)  MORTES=%d (le build ne connait plus)"
          % (len(references_qualifiees()), len(introuvables), len(mortes)))
    for rel, k, cls, membre in introuvables[:20]:
        print("  INTROUVABLE %s:%d  %s.%s" % (rel, k, cls, membre))
    for rel, k, cls, membre in mortes[:20]:
        print("  MORTE       %s:%d  %s.%s" % (rel, k, cls, membre))
    rouge += len(introuvables) + len(mortes)
    print("")

    # ---- Etape 4 : porteurs (optionnelle : elle charge le gameconfig)
    if porteurs:
        rouge += etape_porteurs(build)

    if rouge:
        print("%d ecart(s) BLOQUANT(s) -- voir ci-dessus" % rouge)
    else:
        dettes = sum(1 for m in REGISTRE if not m.garde)
        print("les %d mirror(s) SOUS GARDE sont en bijection avec le build %s ; %s"
              % (sum(1 for m in REGISTRE if m.garde), build,
                 ("%d dette(s) declaree(s) au compte attendu" % dettes) if dettes else
                 "AUCUNE dette declaree ne subsiste (les 2 dernieres resorbees par #318)"))
    return 1 if rouge else 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--verbose", action="store_true",
                    help="detailler manquants/morts/renumerotes de TOUS les mirrors")
    ap.add_argument("--porteurs", action="store_true",
                    help="etape 4 : confronter le mirror au gameconfig (file de portage)")
    a = ap.parse_args()
    return rapport(a.verbose, a.porteurs)


if __name__ == "__main__":
    raise SystemExit(main())
