#!/usr/bin/env python
"""#933 -- les PREMISSES DE REGIME perimees par la bascule « items Best-In-Slot ».

POURQUOI CE PROBE EXISTE
------------------------
Depuis #419-r5/-r6, `_normalize_and_extract_pool` equipe les items Best-In-Slot PAR DEFAUT.
Aucun code de moteur n'a bouge, et pourtant tout test ecrit AVANT cette bascule qui presuppose
un porteur A ZERO est devenu rouge -- ou, pire, TROMPEUR-MAIS-VERT. Cinq victimes connues au
2026-08-11, dont TROIS trouvees PAR HASARD en jouant une regression sans rapport.

`probe_419r6_perimetre_bascule.py` a derive le perimetre par TROIS canaux (coup propre exige /
deja neutralise / valeur en dur > 100). Ce probe-ci ouvre le QUATRIEME, celui qu'aucun des trois
ne voit : l'ASSERTION SUR UNE STAT TOTALE SENSIBLE AU REGIME.

LES DEUX FORMES, ET POURQUOI ELLES SONT LA MEME
------------------------------------------------
  (Z) PREMISSE-ZERO   `assert stat(...) == 0`, `== (0, 0)`, `not crit_chance`
      -> devient ROUGE des que la base cesse d'etre nulle. Se voit dans un `rc`.
  (P) ATTENDU-POSITIF `assert stat(...) > 0`
      -> reste VERT, et cesse de mesurer quoi que ce soit : avec une base non nulle, il passe
         MEME SI le mecanisme teste est mort. Aucun `rc` ne le signale. C'est la forme
         dangereuse, et c'est exactement le cas des deux `seed[...] > 0` de
         `test_lion_helm_block_aura_live.py`, dont le voisin `== (0, 0)` etait rouge.

Les deux ont le MEME remede : rendre la base nulle AU MONTAGE (`--unit-stat <u>:<Stat>=0`),
ce qui fait de la stat TOTALE la CONTRIBUTION -- la seule grandeur que ces tests visent.
Pas `TACTICUS_BIS_ITEMS=0`, qui deshabille tout le roster : c'est l'instrument de DIAGNOSTIC
(mode `--jouer`), jamais le remede (#914 §3.3).

CE QU'IL VISITE, ET CE QU'IL NE VISITE PAS -- imprime, jamais tu
-----------------------------------------------------------------
Il visite TOUS les `test_*.py` de `scripts/python/tests/`, classe live/offline par les memes
marqueurs de harnais que #419-r6, et pour chaque LIVE derive ses comparaisons. Il ne visite PAS
la face DECISION hors tests (`engine_validate.py`, `predict_sweep.py`), ni ce qu'un test atteint
via la fixture d'un autre paquet.

⚠ LE MONTAGE N'EST PAS DANS LE FICHIER DE TEST -- il est dans le MODULE QU'IL IMPORTE, et c'est
mesure (#10024, 2026-08-18). `_classe_fichier` avait deja rencontre ce gisement sur l'axe
LIVE/OFFLINE (« ils prennent leur fixture dans un module PARTAGE ») et l'avait ferme la ; il
restait GRAND OUVERT sur l'axe NEUTRALISATION, qui ne lisait que la source du test. Mesure :
**9 des 39 suspects** portent leur `--unit-stat`/`--crit`/`--block-*` dans un module importe --
`test_1001_votann_relics_live.py` en tete, dont le `probe_1001_votann_relics.py` ecrit
`--unit-stat votanUthar:CritChance=<0|100>` et le DOCUMENTE (« n'est pas un confort : sans lui
Uthar peut CRITER pendant... »). Le recenseur les accusait donc de ne pas declarer un regime
qu'ils declarent. `_montage_importe` suit ces imports, sur **UN SEUL niveau** (le module importe
par le TEST, pas ce que ce module importe a son tour) : le cout d'une fermeture transitive n'est
pas justifie tant qu'aucune victime ne l'exige, et ce qui est suivi est IMPRIME
(`neutralise_via`), donc l'angle mort restant est visible.

Aucune assertion : c'est un probe, il MESURE. La garde vit dans
`tests/engine/test_933_premisse_regime_offline.py`.
"""
from __future__ import annotations

import argparse
import ast
import json
import os
import re
import subprocess
import sys
from collections import Counter
from pathlib import Path

_HERE = Path(__file__).resolve().parent
_TESTS = _HERE / "tests"

# ---------------------------------------------------------------------------
# 1. LES STATS SENSIBLES AU REGIME -- derivees, jamais recopiees
# ---------------------------------------------------------------------------
# Ces deux jeux sont le RESULTAT de `--stats` (etage LIVE ci-dessous) sur le seed BC au rank 17 :
# les champs de `BC.Units[]` dont la valeur DIFFERE entre `equip_items=False` et
# `equip_items=True`. Ils sont ecrits ici pour que le recensement STATIQUE et le cliquet tournent
# OFFLINE ; `--stats` les re-derive et DIT s'ils ont bouge (c'est le cran qui empeche cette liste
# de se perimer en silence, exactement comme la premisse qu'elle sert a garder).
#
# LA DISTINCTION EST LE COEUR DU TRI, et elle est MESUREE, pas supposee (2026-08-11, 106 unites) :
#
#   champ            bouge   0->x    x->0
#   CritDamage          98     98       0      <- ZERO OUVERT
#   CritChance          98     98       0      <- ZERO OUVERT
#   BlockChance         46     46       0      <- ZERO OUVERT
#   BlockDamage         46     46       0      <- ZERO OUVERT
#   FixedArmor          49      0       0
#   Health               4      0       0
#   RemainingHealth      4      0       0
#
# Une stat dont AUCUNE unite ne passe de 0 a non-0 ne peut PAS perimer une premisse `== 0`, et
# un `> 0` ecrit sur elle etait deja vrai avant la bascule -- donc ni rouge ni trompeur par CE
# canal. Les quatre stats a ZERO OUVERT, elles, periment les DEUX formes d'un coup.
# `FixedArmor`/`Health` restent sensibles par le canal (C) « valeur en dur » de #419-r6, qui a
# ete balaye par `probe_419r6_perimetre_bascule.py` : ce probe-ci ne le redouble pas.
_STATS_ZERO_OUVERT = ("CritChance", "CritDamage", "BlockChance", "BlockDamage")
_STATS_QUI_BOUGENT = ("FixedArmor", "Health", "RemainingHealth")
_STATS_SENSIBLES = _STATS_ZERO_OUVERT + _STATS_QUI_BOUGENT

# Les noms sous lesquels ces memes stats s'ecrivent dans un test : cote `combatSnapshot`
# (camelCase), cote `StatType` (SCREAMING_SNAKE), et les abreviations d'usage. Le
# rapprochement se fait sur le TEXTE de l'expression comparee -- c'est une heuristique de NOM,
# et elle est declaree comme telle dans la sortie.
_MOTS_PAR_STAT = {
    "CritChance": ("critchance", "crit_chance", "crit_chances", "CRIT_CHANCE", "critC", "cc"),
    "CritDamage": ("critdamage", "crit_damage", "CRIT_DAMAGE", "critD", "cd"),
    "BlockChance": ("blockchance", "block_chance", "BLOCK_CHANCE", "blockC", "bc"),
    "BlockDamage": ("blockdamage", "block_damage", "BLOCK_DAMAGE", "blockD", "bd"),
    "FixedArmor": ("fixedarmor", "fixed_armor", "FIXED_ARMOR", "armour", "armor"),
    "Health": ("health", "hp", "HEALTH", "maxhealth", "max_health"),
    "RemainingHealth": ("remaininghealth", "remaining_health"),
}
# Un mot de 2 a 4 lettres (`cc`, `bd`, `hp`) est AMBIGU en identifiant nu : mesure sur le corpus,
# `cc` designe aussi des coordonnees de caster (`hexgeo.distance(cc, tc)`) et `bc` le
# BattleConfiguration. On ne l'accepte donc QUE comme CHAINE LITTERALE (`d["cc"]`), qui est la
# forme sous laquelle nos tests s'en servent comme cle. Les identifiants nus sont ECARTES et
# COMPTES (`ecartes_mot_court`) : un filtre qui ne dit pas ce qu'il jette se lit comme un zero.
_MOTS_COURTS = {m for ms in _MOTS_PAR_STAT.values() for m in ms if len(m) <= 4}

# Le montage qui NEUTRALISE la base d'une stat sensible, sous ses DEUX formes ecrites :
#   * `--unit-stat <u>:<Stat>=0`  -- per-unit, le remede etabli (#912, #914, #923) ;
#   * `--crit 0,0` / `--crit-target 0,0` / `--block-player 0,0` / `--block-target 0,0` -- par
#     CAMP. `_patch_combat_stat` de `rl_duel.py` ECRIT `CritChance`/`CritDamage` (resp.
#     `BlockChance`/`BlockDamage`) du BC : a `0,0` c'est bien la BASE qui tombe a zero, pas
#     seulement le tirage.
# ⚠ LES QUATRE FACES, et c'est mesure (#419-r6 §3.1) : `--crit` n'epingle que les p-units et
# `--crit-target` que les a-units. Une seule des deux laisse l'autre camp au regime courant --
# « deux faces sur quatre suffisaient PAR ACCIDENT » y a deja coute deux montages.
# CE QUE CE PROBE EN FAIT, et pourquoi il ne l'ERIGE PAS en condition : ce cliquet garde la
# DECLARATION du regime, pas l'exactitude du montage -- laquelle depend de QUEL camp porte la
# mecanique, indecidable statiquement. Exiger les deux faces pousserait a des montages plus
# larges que la premisse (le contraire de `_stats_concernees`) et, surtout, laisserait les
# fichiers REPARES par une seule face DANS la liste attestee : perdre leur levier ne rougirait
# alors PLUS. Une face suffit donc a declarer ; les neutralisations PARTIELLES sont COMPTEES et
# IMPRIMEES, jamais tues.
_RE_NEUTRALISE = re.compile(
    r"(?:--unit-stat|unit_stat|explicit-stats|explicit_stats)", re.I)
_RE_NEUTRALISE_STAT = re.compile(
    r"(CritChance|CritDamage|BlockChance|BlockDamage|FixedArmor|Health|Armor)\s*=\s*0\b")
# ⚠ La face compte des qu'elle est POSEE, quelle que soit sa VALEUR -- pas seulement a `0,0`.
# `_patch_combat_stat` de `rl_duel.py` ECRIT `u[field] = valeur` : `--block-target "100,300"`
# ECRASE la base autant que `0,0`. Ce qui perime une premisse, c'est une base SUBIE ; une base
# ECRITE par le montage est declaree, quelle que soit sa valeur. Exiger `0,0` faisait sortir
# `test_damage_block_live.py` en faux positif, alors que son `--block-target "100,300"` est
# precisement le montage qui maitrise le canal.
# ⚠ LE DRAPEAU DOIT ETRE UN ARGUMENT, PAS UNE MENTION -- et ce cran a ete trouve par la
# CONTRE-EPREUVE, pas par la relecture : un premier detecteur cherchait `--crit` n'importe ou dans
# la source. Retirer pour de vrai le `"--crit", "0,0"` du montage de `test_savage_echoes_live.py`
# laissait alors le cliquet VERT, parce que le COMMENTAIRE qui explique le levier contient le mot.
# Un cliquet qui se contente d'une mention garde une INTENTION, pas un montage.
_RE_FACE = {
    "crit_p": re.compile(r"""["']--crit["']"""),
    "crit_a": re.compile(r"""["']--crit-target["']"""),
    "block_p": re.compile(r"""["']--block-player["']"""),
    "block_a": re.compile(r"""["']--block-target["']"""),
}
# `--hp-target`/`--hp-player`/`--armor-target` ecrivent eux aussi `Armor`/`FixedArmor`/`Health`
# du BC : ce sont des neutralisations de base a part entiere, sur ces stats-la.
_RE_NEUTRALISE_LEVIER = re.compile(r"--(?:hp-target|hp-player|armor-target|dmg-target)")

_MARQUEURS_LIVE = ("build_runner", "live_session", '"rl_duel.py", "build"',
                   "'rl_duel.py', 'build'")


# ---------------------------------------------------------------------------
# 2. RECENSEMENT STATIQUE -- toutes les comparaisons, role DERIVE du noeud
# ---------------------------------------------------------------------------
def _texte(src_lignes: list[str], noeud) -> str:
    try:
        return ast.get_source_segment("\n".join(src_lignes), noeud) or ""
    except Exception:                                             # noqa: BLE001
        return ""


_ECARTES_MOT_COURT: Counter = Counter()


def _stats_nommees(txt: str) -> list[str]:
    """Quelles stats sensibles le TEXTE de cette expression nomme-t-il ?

    Heuristique de NOM, declaree : un test qui lit une stat sans jamais l'ecrire (via un
    helper opaque, un index numerique, un `*u`) n'est PAS vu ici. C'est la premiere des
    portees imprimees par `--recenser`.
    """
    bas = txt.lower()
    litteraux = {s for s in re.findall(r"""["']([A-Za-z_][A-Za-z_0-9]*)["']""", txt)}
    tokens = set(re.findall(r"[A-Za-z_][A-Za-z_0-9]*", txt))
    out = []
    for stat, mots in _MOTS_PAR_STAT.items():
        for m in mots:
            if m in _MOTS_COURTS:
                if m in litteraux:
                    out.append(stat)
                    break
                if m in tokens:
                    _ECARTES_MOT_COURT[m] += 1
            elif m.lower() in bas:
                out.append(stat)
                break
    return out


def _est_zero(noeud) -> bool:
    """`0`, `(0, 0)`, `[0, 0]`, `0.0` -- la valeur nulle sous ses formes ecrites."""
    if isinstance(noeud, ast.Constant):
        return isinstance(noeud.value, (int, float)) and not isinstance(noeud.value, bool) \
            and noeud.value == 0
    if isinstance(noeud, (ast.Tuple, ast.List)):
        return bool(noeud.elts) and all(_est_zero(e) for e in noeud.elts)
    return False


def _est_positif(noeud) -> bool:
    if isinstance(noeud, ast.Constant):
        return isinstance(noeud.value, (int, float)) and not isinstance(noeud.value, bool) \
            and noeud.value >= 0
    if isinstance(noeud, (ast.Tuple, ast.List)):
        return bool(noeud.elts) and all(_est_positif(e) for e in noeud.elts)
    return False


def _premisses(path: Path, src: str) -> list[dict]:
    """Toutes les comparaisons a une valeur NULLE ou POSITIVE, dans un fichier qui LIT une stat.

    ⚠ LE LIEN NOM <-> VALEUR NE SE FAIT PAS DANS L'EXPRESSION, et c'est la faute que la premiere
    ecriture de ce probe a commise : elle exigeait que l'expression comparee NOMME la stat, et
    ratait donc son propre cas d'entree -- `assert seed[az] == (0, 0)` de
    `test_lion_helm_block_aura_live.py`, ou le mot « block » n'apparait que dans le nom de la
    FONCTION qui a produit `seed`. Un recenseur qui ne voit pas la victime connue ne peut rien
    dire des inconnues.

    Le rattachement se fait donc au niveau du FICHIER (`_lit_stats`), et ce sont TOUTES les
    comparaisons a 0 / a un positif qui sont recensees. Le fait que l'expression nomme elle-meme
    la stat devient un ATTRIBUT (`nomme`), utile pour trier, jamais un filtre.

    Le role est DERIVE de l'operateur et de la valeur comparee, pas choisi dans une liste blanche
    de formes ; une comparaison inconnue sort sous `autre`. La somme des roles est imprimee comme
    partition exhaustive des comparaisons VISITEES.
    """
    out: list[dict] = []
    try:
        arbre = ast.parse(src)
    except SyntaxError:
        return out
    lignes = src.splitlines()

    # (C) LE SCALAIRE GRAVE -- le gisement que ce recenseur ne pouvait pas voir (#933-r4).
    # `NEURO_ATTACK2 = 4448` puis `assert port == NEURO_ATTACK2` : la comparaison porte sur un
    # `ast.Name`, pas sur un `ast.Constant`, donc ni le role `valeur-en-dur` ni la lecture de PROSE
    # ne l'attrapaient -- et le fichier restait VERT au cliquet alors qu'il etait ROUGE en regime
    # nominal. Une ATTESTATION CHIFFREE mesuree sous un regime EST une premisse de regime, qu'une
    # phrase l'accompagne ou non ; c'est meme la forme la plus repandue, parce qu'elle se lit comme
    # une constante de code et non comme une hypothese.
    _scalaires: dict[str, int] = {}
    for n in arbre.body:                                   # NIVEAU MODULE seulement
        if not isinstance(n, (ast.Assign, ast.AnnAssign)):
            continue
        val = n.value
        if not (isinstance(val, ast.Constant) and isinstance(val.value, int)
                and not isinstance(val.value, bool)):
            continue
        cibles = n.targets if isinstance(n, ast.Assign) else [n.target]
        for c in cibles:
            if isinstance(c, ast.Name):
                _scalaires[c.id] = int(val.value)

    # LES COMPARAISONS QUI GARDENT UN `assert` (ou un `skip`) -- le patron le plus dangereux, et
    # celui qui a effectivement mordu : `if cc == 0: assert port_ph == live_hits` de
    # `test_savage_echoes_live.py`. Le caster porte desormais `CritChance = 20` : la garde SAUTE,
    # l'assertion la plus forte du fichier n'est PLUS JAMAIS evaluee, et le fichier reste VERT.
    # Aucun `rc` ne le signale -- c'est la definition meme du trompeur-mais-vert.
    gardiennes: set[int] = set()
    for n in ast.walk(arbre):
        if not isinstance(n, ast.If):
            continue
        corps = list(n.body) + list(n.orelse)
        protege = any(isinstance(c, ast.Assert) for b in corps for c in ast.walk(b)) or \
            any(isinstance(c, ast.Attribute) and c.attr == "skip"
                for b in corps for c in ast.walk(b))
        if not protege:
            continue
        for c in ast.walk(n.test):
            if isinstance(c, ast.Compare):
                gardiennes.add(id(c))

    for n in ast.walk(arbre):
        if not isinstance(n, ast.Compare):
            continue
        txt = _texte(lignes, n)
        nomme = sorted(set(_stats_nommees(txt)))
        for op, comp in zip(n.ops, n.comparators):
            role = None
            if isinstance(op, ast.Eq) and _est_zero(comp):
                role = "premisse-zero"
            elif isinstance(op, ast.NotEq) and _est_zero(comp):
                role = "attendu-non-nul"
            elif isinstance(op, (ast.Gt, ast.GtE)) and _est_positif(comp):
                role = "attendu-positif"
            elif isinstance(op, (ast.Lt, ast.LtE)) and _est_positif(comp):
                role = "borne-superieure"
            elif isinstance(op, ast.Eq) and isinstance(comp, ast.Constant) \
                    and isinstance(comp.value, int) and not isinstance(comp.value, bool):
                role = "valeur-en-dur"
            elif isinstance(op, ast.Eq) and isinstance(comp, ast.Name) \
                    and comp.id in _scalaires:
                role = "constante-de-module"          # (C) le SCALAIRE GRAVE (#933-r4)
            elif isinstance(op, ast.Eq) and isinstance(n.left, ast.Name) \
                    and n.left.id in _scalaires:
                role = "constante-de-module"          # ... et dans l'autre sens
            if role is None:
                continue
            if id(n) in gardiennes and role in ("premisse-zero", "attendu-non-nul",
                                                "attendu-positif"):
                role = "garde-qui-protege-un-assert"
            out.append({
                "ligne": n.lineno,
                "role": role,
                "nomme": nomme,
                "src": (lignes[n.lineno - 1].strip()[:118] if n.lineno <= len(lignes) else ""),
            })
    return out


# Les noms sous lesquels un fichier LIT une stat a zero ouvert -- y compris les predicats natifs
# derives (`CouldCrit`/`CouldBlock`) et les tags d'evenement (`didCrit`), qui sont FAUX par
# construction tant que la stat vaut 0 et deviennent atteignables apres la bascule.
_LECTURES_ZERO_OUVERT = (
    "critchance", "crit_chance", "CRIT_CHANCE", "critdamage", "crit_damage", "CRIT_DAMAGE",
    "blockchance", "block_chance", "BLOCK_CHANCE", "blockdamage", "block_damage", "BLOCK_DAMAGE",
    "could_crit", "couldcrit", "could_block", "couldblock",
    "did_crit", "didcrit", "did_block", "didblock", "mightcrit", "might_crit",
)


# (B) LA PREMISSE ECRITE EN PROSE -- le gisement que #914 §4.1 a nomme sans l'outiller.
# « Ces deux phrases etaient VRAIES le jour ou elles ont ete ecrites. Rien ne les a confrontees
# au harnais depuis, parce qu'une premisse en commentaire n'est PAS executable. » Un recenseur
# qui ne lit que les `assert` ne peut par construction pas les voir : elles ne sont dans AUCUNE
# comparaison. On les cherche donc dans le TEXTE, et le remede est le meme -- neutraliser au
# montage, ce qui rend la phrase vraie A NOUVEAU au lieu de la reecrire.
_RE_PROSE = re.compile(
    r"(?:"
    r"(?:crit|block)\s*(?:chance|damage|dmg)?\s*(?:=|==)\s*0\b"
    r"|sans\s+crit\b|sans\s+block\b"
    r"|aucun(?:e)?\s+(?:source\s+de\s+)?(?:crit|block)"
    r"|aucune\s+unite\s+n'a\s+de\s+(?:crit|block)"
    r"|ne\s+peu(?:t|vent)\s+pas\s+(?:crit|bloqu)"
    r"|jamais\s+de\s+crit|crit\s+(?:structurellement\s+)?impossible"
    r"|nocrit|no_crit|no-crit"
    r")", re.I)


def _prose(src: str) -> list[dict]:
    out = []
    for i, ligne in enumerate(src.splitlines(), 1):
        if _RE_PROSE.search(ligne):
            out.append({"ligne": i, "role": "premisse-en-prose", "nomme": [],
                        "src": ligne.strip()[:118]})
    return out


def _lit_stats(src: str) -> list[str]:
    bas = src.lower()
    return sorted({m for m in _LECTURES_ZERO_OUVERT if m.lower() in bas})


def _stats_concernees(lectures: list[str]) -> set[str]:
    """De QUELLES stats la lecture depend-elle ? -- ce qu'il faut neutraliser, et rien de plus.

    Un fichier qui ne lit que le BLOCK n'a aucune raison d'epingler le CRIT : exiger les quatre
    ferait du bruit et pousserait a des montages plus larges que la premisse. Les predicats
    derives (`could_crit`, `did_block`) sont rattaches a leur paire.
    """
    out: set[str] = set()
    for m in lectures:
        b = m.lower()
        if "crit" in b:
            out |= {"CritChance", "CritDamage"}
        if "block" in b:
            out |= {"BlockChance", "BlockDamage"}
    return out


#: Les imports d'un fichier de test qui peuvent PORTER son montage. On ne resout pas des paquets :
#: un test importe son montage comme un module PLAT (`import probe_1001_votann_relics as P`,
#: `from _pierce_floor_regime import ...`), et ce module vit soit a cote du probe
#: (`scripts/python/`), soit a cote du test.
_RE_IMPORT_PLAT = re.compile(
    r"^\s*(?:import\s+([A-Za-z_][A-Za-z0-9_]*)|from\s+([A-Za-z_][A-Za-z0-9_]*)\s+import)", re.M)


def _neutralise_de_source(src: str) -> set:
    """Les stats dont le montage ECRIT la base, lues dans UNE source (test OU module importe)."""
    out: set = set()
    if _RE_NEUTRALISE.search(src):
        out |= set(_RE_NEUTRALISE_STAT.findall(src))
    if _RE_NEUTRALISE_LEVIER.search(src):
        out |= {"Health", "FixedArmor", "Armor"}
    for cle, rex in _RE_FACE.items():
        if rex.search(src):
            out |= ({"CritChance", "CritDamage"} if cle.startswith("crit")
                    else {"BlockChance", "BlockDamage"})
    return out


#: Cache `chemin -> stats neutralisees`. Un meme probe de montage est importe par plusieurs tests,
#: et le recensement balaie ~900 fichiers : sans lui, le cliquet passe de 30 s a 125 s (mesure).
_CACHE_MONTAGE: dict = {}


def _montage_importe(src: str, chemin: "Path | None") -> dict[str, list[str]]:
    """Les stats neutralisees par les MODULES QUE LE TEST IMPORTE (cf. l'en-tete, #10024).

    Un seul niveau, et deux emplacements seulement -- `scripts/python/<mod>.py` (les probes de
    montage) et le repertoire du test lui-meme (les helpers `_x.py`). Rend `{module: [stats]}` :
    la PROVENANCE est imprimee, parce qu'un elargissement de perimetre qui ne dit pas d'ou il tire
    sa conclusion est indistinguable d'un relachement du critere.
    """
    trouve: dict[str, list[str]] = {}
    voisins = [_HERE] + ([chemin.parent] if chemin is not None else [])
    for m in _RE_IMPORT_PLAT.findall(src):
        mod = m[0] or m[1]
        if not mod or mod in ("os", "re", "sys", "json", "pytest", "engine", "typing", "pathlib",
                              "subprocess", "collections", "math", "random", "time", "itertools",
                              "__future__"):
            continue
        for base in voisins:
            p = base / (mod + ".py")
            if not p.exists():
                continue
            cle = str(p)
            if cle not in _CACHE_MONTAGE:
                _CACHE_MONTAGE[cle] = sorted(
                    _neutralise_de_source(p.read_text(encoding="utf-8", errors="replace")))
            if _CACHE_MONTAGE[cle]:
                trouve[mod] = list(_CACHE_MONTAGE[cle])
            break
    return trouve


def _classe_fichier(src: str, nom: str = "", chemin: "Path | None" = None) -> dict:
    """LIVE = marqueur de harnais OU suffixe `_live.py`.

    Le suffixe n'est pas une commodite : mesure du 2026-08-11, se fier aux SEULS marqueurs de
    #419-r6 classait OFFLINE des fichiers qui montent bel et bien un runner -- ils prennent leur
    fixture dans un module PARTAGE (`_pierce_floor_regime.py`, `_summon_montage.py`) ou par la
    fixture `rpc`, et le mot `build_runner` n'apparait alors nulle part chez eux.
    `test_448r2dr2_titanhammer_active_live.py`, dont l'en-tete DECLARE pourtant
    « `BlockChance = 0` sur un terminator », en faisait partie. Un recenseur qui rate la moitie
    de sa population ne peut pas rendre zero sur elle.
    """
    neutralise_stats = set()
    if _RE_NEUTRALISE.search(src):
        neutralise_stats |= {m for m in _RE_NEUTRALISE_STAT.findall(src)}
    if _RE_NEUTRALISE_LEVIER.search(src):
        neutralise_stats |= {"Health", "FixedArmor", "Armor"}
    faces = {k: bool(r.search(src)) for k, r in _RE_FACE.items()}
    partielles = []
    if faces["crit_p"] or faces["crit_a"]:
        neutralise_stats |= {"CritChance", "CritDamage"}
        if not (faces["crit_p"] and faces["crit_a"]):
            partielles.append("crit:" + ("p" if faces["crit_p"] else "a"))
    if faces["block_p"] or faces["block_a"]:
        neutralise_stats |= {"BlockChance", "BlockDamage"}
        if not (faces["block_p"] and faces["block_a"]):
            partielles.append("block:" + ("p" if faces["block_p"] else "a"))
    # `_offline.py` PREVAUT sur les marqueurs : un cliquet offline qui CITE `build_runner` dans un
    # temoin synthetique (c'est le cas de `test_933_premisse_regime_offline.py` lui-meme) serait
    # sinon classe LIVE et se recenserait -- un recenseur qui se compte lui-meme derive.
    live = (not nom.endswith("_offline.py")
            and (any(m in src for m in _MARQUEURS_LIVE) or nom.endswith("_live.py")))
    # Le montage DELEGUE a un module importe compte autant que celui ecrit ici (cf. l'en-tete).
    via = _montage_importe(src, chemin) if live else {}
    for stats in via.values():
        neutralise_stats |= set(stats)
    return {
        "live": live,
        "neutralise": sorted(neutralise_stats),
        "partielles": partielles,
        "neutralise_via": via,
    }


def recenser(racine: "Path | None" = None) -> dict:
    racine = racine or _TESTS
    fichiers = sorted(racine.rglob("test_*.py"))
    vus = {"fichiers": 0, "offline": 0, "live": 0, "live_sans_lecture": 0, "live_lecteur": 0}
    roles: Counter = Counter()
    par_fichier: dict[str, dict] = {}
    scalaires: dict[str, list] = {}
    for p in fichiers:
        src = p.read_text(encoding="utf-8", errors="replace")
        rel = str(p.relative_to(racine)).replace("\\", "/")
        vus["fichiers"] += 1
        c = _classe_fichier(src, p.name, p)
        if not c["live"]:
            vus["offline"] += 1
            continue
        vus["live"] += 1
        lectures = _lit_stats(src)
        # (C) LE SCALAIRE GRAVE SE RECENSE **HORS** DE LA PORTE `_lit_stats` (#933-r4).
        # Les deux rouges qui ont ouvert ce residu -- `test_462_..._neuroparasite_pose_live` et
        # `test_462_..._tile_owner_gate_live` -- ne NOMMENT aucune des quatre stats a zero ouvert :
        # leur dependance au regime passe par la `FixedArmor` (que ce probe imprime deja comme
        # « bouge sans passer par 0 ») et par un TOTAL de degat. Ils n'etaient donc PAS visites, et
        # le role (C) seul n'y changeait rien -- l'angle mort etait la PORTE, pas le critere.
        # Un test LIVE qui compare une valeur mesuree a une CONSTANTE DE MODULE est regime-dependant
        # PAR CONSTRUCTION, quelle que soit la stat qu'il lit : la constante a ete gravee sous UN
        # regime. C'est un gisement DISTINCT (aucune neutralisation de stat ne le repare -- le
        # remede est de re-mesurer et d'ECRIRE le regime a cote de la valeur), donc un bucket a part.
        graves = [e for e in _premisses(p, src) if e["role"] == "constante-de-module"]
        if graves:
            scalaires[rel] = graves
        if not lectures:
            vus["live_sans_lecture"] += 1
            continue
        vus["live_lecteur"] += 1
        prem = _premisses(p, src) + _prose(src)
        for e in prem:
            roles[e["role"]] += 1
        if prem:
            par_fichier[rel] = {"premisses": prem, "neutralise": c["neutralise"],
                                "lectures": lectures, "partielles": c.get("partielles") or [],
                                "neutralise_via": c.get("neutralise_via") or {}}
    return {"vus": vus, "roles": roles, "par_fichier": par_fichier, "scalaires": scalaires}


_ROLES_PERIMABLES = ("premisse-zero", "attendu-positif", "attendu-non-nul", "valeur-en-dur",
                     "premisse-en-prose", "garde-qui-protege-un-assert",
                     # (C) #933-r4 : `assert port == NEURO_ATTACK2` avec `NEURO_ATTACK2 = 4448` au
                     # module. Angle mort STRUCTUREL des deux premiers criteres, et probablement la
                     # forme la plus repandue -- une attestation chiffree ne porte pas de phrase.
                     "constante-de-module")


def _suspects(rec: dict) -> dict[str, list[dict]]:
    """Les fichiers qui LISENT une stat a zero ouvert, COMPARENT a 0 / a un positif, et dont la
    base n'est PAS neutralisee au montage.

    Un fichier qui neutralise deja les 4 stats a zero ouvert est ecarte -- c'est le remede, et
    le compter comme suspect ferait du bruit qui noie les vrais.
    """
    out: dict[str, list[dict]] = {}
    for rel, info in rec["par_fichier"].items():
        besoin = _stats_concernees(info["lectures"])
        if besoin and besoin <= set(info["neutralise"]):
            continue
        gardes = [e for e in info["premisses"] if e["role"] in _ROLES_PERIMABLES]
        if gardes:
            out[rel] = gardes
    return out


# ---------------------------------------------------------------------------
# 3. ETAGE LIVE -- re-deriver les stats sensibles (le jeu par defaut ci-dessus)
# ---------------------------------------------------------------------------
def mesurer_unites(rank: int, visual_ids: list[str]) -> None:
    """Les 4 stats a zero ouvert d'unites NOMMEES, dans les DEUX regimes.

    C'est le geste qui remplace « ce porteur ne peut pas critiquer / bloquer » par une mesure.
    """
    sys.path.insert(0, str(_HERE))
    import rl_collect_batch as R                                   # noqa: E402

    sid = R._resolve_session()
    seed = R._load_seed_bc()
    tpl_t, _, _ = R._normalize_and_extract_pool(sid, seed, rank, equip_items=False)
    tpl_c, _, _ = R._normalize_and_extract_pool(sid, seed, rank, equip_items=True)
    t_by = {u["Id"]: u for u in tpl_t["Units"]}
    c_by = {u["Id"]: u for u in tpl_c["Units"]}
    if visual_ids == ["block"] or visual_ids == ["crit"]:
        # Le mot-cle rend la POPULATION, pas une unite : « qui a une base non nulle
        # aujourd'hui ? » est la question qu'on se pose pour CHOISIR un temoin non
        # tautologique -- un temoin dont la base serait nulle sans le levier ne peut pas
        # montrer que le levier mord.
        cle = "BlockChance" if visual_ids == ["block"] else "CritChance"
        vus = [(uid, u.get(cle) or 0) for uid, u in sorted(c_by.items())
               if (u.get(cle) or 0) > 0]
        print("=== #933 -- unites a %s > 0 en regime COURANT : %d ===" % (cle, len(vus)))
        for uid, v in vus:
            print("  %-26s %s=%s" % (uid, cle, v))
        return
    print("=== #933 -- stats a ZERO OUVERT par unite (rank %d) ===" % rank)
    print("  %-26s %-30s %s" % ("unite", "TEMOIN (sans items)", "COURANT (BiS)"))
    for vid in visual_ids:
        a, b = t_by.get(vid), c_by.get(vid)
        if a is None or b is None:
            print("  %-26s ABSENTE du template normalise (npc / hors pool ?)" % vid)
            continue
        f = lambda u: "cc %-5s cd %-6s bc %-5s bd %-6s" % (          # noqa: E731
            u.get("CritChance"), u.get("CritDamage"),
            u.get("BlockChance"), u.get("BlockDamage"))
        print("  %-26s %-30s %s" % (vid, f(a), f(b)))


def mesurer_stats(rank: int) -> dict:
    sys.path.insert(0, str(_HERE))
    import rl_collect_batch as R                                   # noqa: E402

    sid = R._resolve_session()
    seed = R._load_seed_bc()
    tpl_t, pool_t, mow_t = R._normalize_and_extract_pool(sid, seed, rank, equip_items=False)
    tpl_c, _, _ = R._normalize_and_extract_pool(sid, seed, rank, equip_items=True)
    ids = sorted(set(pool_t) | set(mow_t))
    t_by = {u["Id"]: u for u in tpl_t["Units"]}
    c_by = {u["Id"]: u for u in tpl_c["Units"]}

    bouge: Counter = Counter()
    zero_vers_non_zero: Counter = Counter()
    non_zero_vers_zero: Counter = Counter()
    champs = set()
    for uid in ids:
        a, b = t_by.get(uid, {}), c_by.get(uid, {})
        champs |= {k for k, v in a.items() if isinstance(v, (int, float))
                   and not isinstance(v, bool)}
    for uid in ids:
        a, b = t_by.get(uid, {}), c_by.get(uid, {})
        for k in champs:
            va, vb = a.get(k), b.get(k)
            if not isinstance(va, (int, float)) or not isinstance(vb, (int, float)):
                continue
            if va == vb:
                continue
            bouge[k] += 1
            if va == 0 and vb != 0:
                zero_vers_non_zero[k] += 1
            elif va != 0 and vb == 0:
                non_zero_vers_zero[k] += 1
    return {"sid": sid, "n_unites": len(ids), "bouge": bouge,
            "zero_vers_non_zero": zero_vers_non_zero,
            "non_zero_vers_zero": non_zero_vers_zero}


# ---------------------------------------------------------------------------
# 4. ETAGE DE DIAGNOSTIC -- jouer un fichier dans les DEUX regimes
# ---------------------------------------------------------------------------
_BILAN = re.compile(r"(\d+) (passed|failed|skipped|error)")


def _jouer_un(rel: str, regime: str | None) -> dict:
    env = dict(os.environ)
    if regime is None:
        env.pop("TACTICUS_BIS_ITEMS", None)
    else:
        env["TACTICUS_BIS_ITEMS"] = regime
    p = subprocess.run([sys.executable, "-m", "pytest", "tests/" + rel,
                        "-q", "--tb=no", "-p", "no:randomly"],
                       cwd=str(_HERE), capture_output=True, text=True,
                       encoding="utf-8", errors="replace", env=env)
    compte = {k: 0 for k in ("passed", "failed", "skipped", "error")}
    for n, k in _BILAN.findall(p.stdout or ""):
        compte[k] = int(n)
    compte["rc"] = p.returncode
    compte["inerte"] = bool(compte["passed"] == 0 and compte["skipped"] > 0)
    compte["fichier"] = rel
    compte["regime"] = "defaut" if regime is None else regime
    return compte


def _jouer(rels: list[str], regime: str | None, workers: int,
           journal: "Path | None" = None) -> list[dict]:
    from concurrent.futures import ThreadPoolExecutor
    import threading

    deja: dict[str, dict] = {}
    if journal is not None and journal.exists():
        for ligne in journal.read_text(encoding="utf-8", errors="replace").splitlines():
            try:
                r = json.loads(ligne)
            except Exception:                                     # noqa: BLE001
                continue
            if r.get("fichier"):
                deja[r["fichier"]] = r
    a_jouer = [r for r in rels if r not in deja]
    if journal is not None:
        print("  [journal] %s : %d deja mesure(s), %d a jouer"
              % (journal.name, len(rels) - len(a_jouer), len(a_jouer)))
        journal.parent.mkdir(parents=True, exist_ok=True)
    verrou = threading.Lock()

    def _un(rel):
        r = _jouer_un(rel, regime)
        if journal is not None:
            with verrou, journal.open("a", encoding="utf-8") as f:
                f.write(json.dumps(r) + "\n")
        return r

    with ThreadPoolExecutor(max_workers=max(1, min(workers, 4))) as ex:
        joues = list(ex.map(_un, a_jouer))
    return [deja[r] for r in rels if r in deja] + joues


# ---------------------------------------------------------------------------
def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--recenser", action="store_true",
                    help="balayage STATIQUE exhaustif des tests (offline)")
    ap.add_argument("--lister", choices=["suspects", "tout"], default=None)
    ap.add_argument("--attester", action="store_true",
                    help="imprime le bloc Python `_ATTESTES` du cliquet "
                         "(tests/engine/test_933_premisse_regime_offline.py) -- il se REGENERE, "
                         "il ne se tient pas a la main")
    ap.add_argument("--arbre", default=None,
                    help="racine de tests a recenser (defaut : scripts/python/tests). Sert a "
                         "recenser un arbre TEMOIN -- p. ex. l'etat d'avant une reparation, "
                         "pour verifier que le recenseur voit bien la victime CONNUE")
    ap.add_argument("--stats", action="store_true",
                    help="LIVE : re-derive les stats sensibles au regime (diff des templates)")
    ap.add_argument("--rank", type=int, default=17)
    ap.add_argument("--unites", default=None,
                    help="LIVE : imprime les 4 stats a zero ouvert de ces VisualId (virgules), "
                         "dans les DEUX regimes -- remplace « ce porteur ne peut pas bloquer » "
                         "par une mesure")
    ap.add_argument("--jouer", default=None,
                    help="LIVE : joue une liste explicite (rel. a tests/, virgules) ; "
                         "`suspects` joue les fichiers suspects du recensement")
    ap.add_argument("--regime", choices=["0", "1", "defaut"], default="defaut")
    ap.add_argument("--workers", type=int, default=4)
    ap.add_argument("--journal", default=None)
    ap.add_argument("--depuis", type=int, default=0)
    ap.add_argument("--jusqu-a", type=int, default=0)
    a = ap.parse_args(argv)

    if not any((a.recenser, a.stats, a.jouer, a.unites, a.attester)):
        a.recenser = True
    if a.attester:
        a.recenser = True

    rec = None
    if a.recenser or a.jouer == "suspects":
        if not _TESTS.exists():
            print("[933] ARBRE DE TESTS INTROUVABLE : %s -- aucune mesure" % _TESTS)
            return 2
        rec = recenser(Path(a.arbre) if a.arbre else None)
        susp = _suspects(rec)
        v = rec["vus"]
        print("=== #933 -- PREMISSES DE REGIME (balayage STATIQUE) ===")
        print("  arbre                               : %s" % (a.arbre or str(_TESTS)))
        print("  fichiers de test visites            : %d" % v["fichiers"])
        print("    dont OFFLINE (hors perimetre)     : %d" % v["offline"])
        print("    dont LIVE (montent un runner)     : %d" % v["live"])
        print("      dont LISANT une stat a zero ouvert : %d" % v["live_lecteur"])
        print("      dont n'en lisant AUCUNE            : %d  (ECARTES : rien a perimer)"
              % v["live_sans_lecture"])
        print("  stats a ZERO OUVERT (0 -> non-0)    : %s" % ", ".join(_STATS_ZERO_OUVERT))
        print("  stats qui BOUGENT sans passer par 0 : %s  (canal (C) de #419-r6)"
              % ", ".join(_STATS_QUI_BOUGENT))
        total = sum(rec["roles"].values())
        print("  comparaisons a 0 / a un positif, dans les fichiers LECTEURS : %d" % total)
        print("  -- partition EXHAUSTIVE par role (somme = %d) --" % total)
        for role, n in rec["roles"].most_common():
            print("     %-18s %d" % (role, n))
        print("  ECARTES : mots courts en identifiant NU (ambigus, cf. en-tete) : %s"
              % (dict(_ECARTES_MOT_COURT) if _ECARTES_MOT_COURT else "(aucun)"))
        print("  fichiers LECTEURS portant au moins une comparaison : %d"
              % len(rec["par_fichier"]))
        print("  fichiers SUSPECTS -- lecteur, comparaison perimable, base NON neutralisee : %d"
              % len(susp))
        part = {r: v2["partielles"] for r, v2 in rec["par_fichier"].items() if v2["partielles"]}
        print("  neutralisations PARTIELLES (une face sur deux) : %d fichier(s)%s"
              % (len(part), (" -- " + ", ".join("%s [%s]" % (r.rsplit("/", 1)[-1], ",".join(v))
                                                for r, v in sorted(part.items())))
                 if part else ""))
        # (C) LE GISEMENT DES SCALAIRES GRAVES -- recense HORS de la porte `_lit_stats` (#933-r4).
        sc = rec.get("scalaires") or {}
        hors = sorted(set(sc) - set(rec["par_fichier"]))
        print("  SCALAIRES GRAVES -- fichiers LIVE comparant une valeur a une CONSTANTE DE MODULE :"
              " %d fichier(s), %d comparaison(s)" % (len(sc), sum(len(v) for v in sc.values())))
        print("    dont INVISIBLES a la porte `_lit_stats` (ne nomment aucune stat a zero ouvert) :"
              " %d" % len(hors))
        print("    ^ gisement DISTINCT : aucune neutralisation de stat ne le repare -- le remede est"
              " de RE-MESURER et d'ECRIRE le regime a cote de la valeur.")
        for rel in hors:
            print("      %s  lignes %s" % (rel, [e["ligne"] for e in sc[rel]]))
        print("  --- CE QUE CE BALAYAGE NE COUVRE PAS ---")
        print("   * une stat lue SANS que son nom soit ecrit (helper opaque, index numerique,")
        print("     deballage `*u`) : le rapprochement est une HEURISTIQUE DE NOM ;")
        print("   * les probes `scripts/python/probe_*.py` (ils mesurent, ils ne gardent rien) ;")
        print("   * la face DECISION hors tests (`engine_validate.py`, `predict_sweep.py`) ;")
        print("   * ce qu'un test atteint via la fixture d'un AUTRE paquet ;")
        print("   * les stats sensibles AUTRES que les %d listees -- `--stats` les re-derive."
              % len(_STATS_SENSIBLES))
        if a.attester:
            print("=== bloc `_ATTESTES` a recopier dans le cliquet (%d) ===" % len(susp))
            print("_ATTESTES = (")
            for rel in sorted(susp):
                print("    \"%s\"," % rel)
            print(")")
        if a.lister:
            cible = susp if a.lister == "suspects" else {
                k: v2["premisses"] for k, v2 in rec["par_fichier"].items()}
            print("=== liste : %s (%d fichier(s)) ===" % (a.lister, len(cible)))
            for rel in sorted(cible):
                neutres = rec["par_fichier"][rel]["neutralise"]
                print("  %s%s" % (rel, ("   [neutralise: %s]" % ",".join(neutres))
                                  if neutres else ""))
                for e in cible[rel]:
                    print("      L%-5d %-18s %-24s %s"
                          % (e["ligne"], e["role"], ",".join(e["nomme"]) or "-", e["src"]))

    if a.unites:
        mesurer_unites(a.rank, [s.strip() for s in a.unites.split(",") if s.strip()])

    if a.stats:
        m = mesurer_stats(a.rank)
        print("=== #933 -- STATS SENSIBLES, RE-DERIVEES (session %d, %d unites, rank %d) ==="
              % (m["sid"], m["n_unites"], a.rank))
        print("  champ                 bouge   0->x    x->0")
        for k, n in m["bouge"].most_common():
            print("  %-20s %5d  %5d  %5d"
                  % (k, n, m["zero_vers_non_zero"].get(k, 0),
                     m["non_zero_vers_zero"].get(k, 0)))
        mesure = {k for k in m["bouge"]}
        ecrite = set(_STATS_SENSIBLES)
        if mesure != ecrite:
            print("  ATTENTION -- le jeu ECRIT dans ce probe DIFFERE de la mesure :")
            print("     mesurees et non ecrites : %s" % sorted(mesure - ecrite))
            print("     ecrites et non mesurees : %s" % sorted(ecrite - mesure))
        else:
            print("  le jeu ECRIT dans ce probe est CONFORME a la mesure (%d stats)"
                  % len(ecrite))

    if a.jouer:
        if a.jouer == "suspects":
            rels = sorted(_suspects(rec))
        else:
            rels = [s.strip() for s in a.jouer.split(",") if s.strip()]
        fin = a.jusqu_a or len(rels)
        rels = rels[a.depuis:fin]
        regime = None if a.regime == "defaut" else a.regime
        print("=== JEU : %d fichier(s), TACTICUS_BIS_ITEMS=%s ===" % (len(rels), a.regime))
        res = _jouer(rels, regime, a.workers, Path(a.journal) if a.journal else None)
        n_inerte = n_rouge = n_vert = 0
        for r in sorted(res, key=lambda x: x["fichier"]):
            if r["failed"] or r["error"] or r["rc"] not in (0, 1):
                etat, n_rouge = "ROUGE ", n_rouge + 1
            elif r["inerte"]:
                etat, n_inerte = "INERTE", n_inerte + 1
            else:
                etat, n_vert = "vert  ", n_vert + 1
            print("  %s %-62s p=%-3d s=%-3d f=%-3d e=%-3d rc=%d"
                  % (etat, r["fichier"], r["passed"], r["skipped"], r["failed"],
                     r["error"], r["rc"]))
        print("  BILAN : %d vert, %d INERTE (garde #455), %d ROUGE"
              % (n_vert, n_inerte, n_rouge))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
