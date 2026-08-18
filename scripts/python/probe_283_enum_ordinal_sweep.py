#!/usr/bin/env python
"""Probe #283 -- les QUATRE enums RENUMEROTES par la MAJ `gqfc5mff6c` -> `rnca9r7q6c`.

POURQUOI CE PROBE EXISTE
------------------------
La MAJ de build a renumerote QUATRE enums (tache #252) : `IdunBattle.DSL.EventTriggerType`,
`IdunBattle.Configuration.UtilityType`, `IdunBattle.Streams.StepType` et
`IdunBattle.Operations.DisplaceDirection`. Un ordinal fige en dur ne rend alors pas « rien » :
il designe UN AUTRE MEMBRE, sans erreur ni trace.

Ce n'est pas un probleme de documentation. #272 a trouve la meme derive dans du code
EXECUTABLE : `CAPTURE_POINT = 24` (juste sur `gqfc5mff6c`) designait `MoltenForm` apres le
decalage -- une feuille qui rendait `0.0` en SILENCE, sans jamais lever.

LE PIEGE QUI INTERDIT TOUT `sed` GLOBAL
---------------------------------------
Un meme nombre a plusieurs sens. `0x2b` est a la fois `EventTriggerType.UnitHealed` et la CLE
DE CONFIG `extraHit` (`GetNumberConstant(cfg, 0x2b)`), presente ~100 fois et parfaitement
legitime. Le probe ne signale donc JAMAIS un nombre nu : il exige la CO-OCCURRENCE avec le nom
d'un membre (ou un contexte syntaxique qui nomme l'enum). Les homonymes sont comptes a part.

CE QUE LE PROBE FAIT (chaque etape est autonome, `--step`)
----------------------------------------------------------
`diff`   : etape 0 -- diffe les 4 enums entre les deux builds VERSIONNES. Entierement offline
           et exact : `data/symbols/<build>/frida/enums.tsv` est versionnee. Aucun decalage
           n'est suppose uniforme -- ils sont LUS (insertion en milieu de table pour
           `UtilityType`, retrait en milieu pour les trois autres).
`mirror` : etape 1 -- toute classe `IntEnum` du depot qui porte le nom d'un des 4 enums est
           confrontee MEMBRE PAR MEMBRE a la table du build courant. C'est LE gisement
           executable : le moteur lit ces membres, jamais un littéral.
`exec`   : etape 2 -- balayage AST de `scripts/python` : littéral entier dans un contexte qui
           NOMME l'un des 4 enums (annotation `# <Enum>.<Membre>`, comparaison sur un alias
           `trigger`/`utility`/`direction`, index d'un registre keye par membre), ou argument
           POSITIONNEL d'un appelable dont la SIGNATURE le nomme (#315 : `TriggerEvent(61, ...)`
           ne nomme rien sur sa ligne -- deux tels sites vivaient pendant que l'etape rendait
           `0 a lire`).
`tables` : etape 3 -- toute table `{ordinal: "Nom"}` / `["Nom", ...]` (Python, TS, JS) dont les
           valeurs appartiennent a l'un des 4 enums est confrontee positionnellement. C'est le
           motif par lequel `STEP_NAMES` mentait en #254b-b : aucune annotation, aucun nom
           d'enum, et pourtant 100 % executable.
`prose`  : etape 4 -- inventaire TEXTUEL (tokenize : COMMENT/STRING seulement) des paires
           <membre> ~ <nombre>. Inerte a l'execution, mais c'est ce qui a contamine l'enonce de
           trois taches. Ne fait PAS echouer le verdict (c'est un residu chiffre).
           `4bis` (meme scan, GATE) -- separateur LARGE, mais critere PROUVE : le nombre vaut
           EXACTEMENT l'ordinal du membre sur le build ARCHIVE. #420 a trouve par la 12 citations
           (`` `...,0x37` UnitDefeated ``, `On(UnitRevived = 45 = 0x2e)`) que le separateur
           etroit de l'etape 4 ne voyait pas. Exemption : un token qui NOMME le build archive
           est un rappel historique volontaire.
`on`     : etape 5 -- ordinaux NUS, sur DEUX ancres : `On(<n>)` et la QUOTE VERBATIM du helper
           de publication (`FUN_<addr>(0x4d|0x50|0x51|.., .., <n>)`). COMPTEUR tant que
           l'ancre est NUE : l'ancre est sure, le verdict ne l'est pas. GATE des que la ligne
           porte l'annotation `On(<Membre>)` (#420-r5) -- l'auteur a alors DECLARE quel
           evenement la quote publie, donc l'ordinal devient confrontable, et il le restera au
           prochain changement de build sans qu'une ligne du depot ait bouge.

VERDICT : FAIL si `mirror`, `exec`, `tables`, `4bis` signalent quoi que ce soit hors allowlist,
ou si une ancre ANNOTEE de l'etape 5 cite l'ordinal ARCHIVE du membre qu'elle nomme.
L'etape 4 et les ancres NUES de l'etape 5 sont des COMPTEURS, pas des gates.

ASCII only (console Windows cp1252).
Usage: python probe_283_enum_ordinal_sweep.py [--step diff|mirror|exec|tables|prose|all] [-v]
"""
from __future__ import annotations

import argparse
import ast
import io
import os
import re
import sys
import token as T
import tokenize
from pathlib import Path

PYDIR = Path(__file__).resolve().parent
REPO = PYDIR.parents[1]
sys.path.insert(0, str(PYDIR))

import repo_read  # noqa: E402
from symbols_layout import (archived_builds, build_generated, builds_sans_date,  # noqa: E402
                            current_build)

#: Ce qui doit changer pour que ce cliquet puisse changer d'avis.
#:
#: Ce fichier porte SIX entrees de banque (`--step diff|mirror|exec|tables|prose|on`) aux
#: perimetres DIFFERENTS. Ce `DECLENCHEUR`-ci est leur UNION STRICTE -- il vaut pour
#: `--step all` et sert de REPLI a toute entree qui ne s'affine pas ; la ventilation, elle,
#: vit dans `DECLENCHEUR_PAR_ENTREE` juste en dessous (#486-r19).
#:
#: `build: True` n'est pas de la marge : `main` lit `current_build()` et `archived_builds()` a
#: CHAQUE etape, et `mirror` / `exec` / `tables` / `prose` comparent a des ORDINAUX qui viennent
#: de `enums.tsv`. Une table qui bouge fait basculer le verdict sans qu'une ligne de code change
#: -- c'est litteralement le gisement (220 citations invalidees par une MAJ, #420).
DECLENCHEUR = {
    "chemins": ("*.py", "**/*.py", "*.ts", "**/*.ts", "*.js", "**/*.js",
                "scripts/python/*.md", "scripts/python/**/*.md"),
    "build": True,
    "toujours": False,
    "raison": "UNION des six etapes : tout `.py`/`.ts`/`.js` du depot (mirror, tables), "
              "`scripts/python/**` en `.py`/`.md` (exec, prose, on), et les tables "
              "`data/symbols/<build>/frida/enums.tsv` dont chaque etape tire ses ordinaux. "
              "Aucune etape ne lit `docs/**` ni aucune autre extension.",
}

#: La VENTILATION, entree de banque par entree de banque (#486-r19). Perimetres LUS dans le
#: code de chaque `step_*` ; couts ISOLES mesures le 2026-08-07 (#486-r14) :
#:
#:   etape    cout     perimetre REEL
#:   ------   ------   --------------------------------------------------------------------
#:   diff      1,1 s   `data/symbols/<build>/frida/enums.tsv` des DEUX builds archives. RIEN
#:                     d'autre -- aucun fichier de code n'est ouvert. (COMPTEUR)
#:   mirror   32,6 s   TOUT `.py` du depot (`_fichiers_du_depot`) + la table du build courant.
#:   exec     80,0 s   `scripts/python/**/*.py` SEULEMENT (`REPO/"scripts"/"python"`.rglob).
#:   tables   12,3 s   TOUT `.py` / `.ts` / `.js` du depot + les tables.
#:   prose    66,1 s   `scripts/python/**` en `.py`/`.md`/`.ts`/`.js` (arg `--racine`).
#:   on       15,7 s   `scripts/python/**` en `.py`/`.md`.
#:
#: Sous l'UNION seule, un `.ts` de `frida/` rejouait `exec`, `prose` et `on` (161,8 s) qui ne le
#: lisent pas, et un changement de `data/symbols` seul rejouait les six alors que `diff` suffit.
#:
#: ⚠ NE PAS scinder ce fichier en six pour obtenir la meme finesse : les six etapes partagent
#: `_fichiers_du_depot` et `_sources`, et c'est la memoisation de ces deux-la qui tient leur
#: cout (la lecture parallele de #457-r6 n'est payee QU'UNE FOIS par process).
#:
#: ⚠ `--racine` (defaut `scripts/python`) est un ARGUMENT : `prose` et `on` peuvent etre pointes
#: ailleurs (`--racine docs`, cf. #283-r2). Ces declarations decrivent l'entree de banque TELLE
#: QU'ELLE EST DANS `ratchets.ps1`, qui ne passe pas `--racine` -- c'est le contrat mesure par
#: `probe_486r12`, qui rejoue exactement l'argv de la banque.
DECLENCHEUR_PAR_ENTREE = {
    # ⚠ CETTE ENTREE A ETE MESUREE FAUSSE, et c'est la premiere prise de la forme #486-r19.
    # Sa 1re redaction disait << n'ouvre AUCUN fichier de code, le seul .py qu'il touche est le
    # sien >> -- ce qui est vrai de `step_diff`, et FAUX de l'entree de banque : le MODULE, en
    # se chargeant, importe `repo_read` et `symbols_layout` (`_ARCHIVES = tuple(archived_builds())`
    # s'evalue a l'import). L'etage 2 l'a nomme des le premier passage --
    # `LU hors perimetre : scripts/python/symbols_layout.py`. Sous l'UNION, cette faute etait
    # STRUCTURELLEMENT invisible : `**/*.py` couvre tout.
    "probe_283:diff": {
        "chemins": ("scripts/python/repo_read.py", "scripts/python/symbols_layout.py",
                    "scripts/python/il2cpp_provenance.py"),
        "build": True,
        "toujours": False,
        "raison": "`step_diff` n'ouvre AUCUN fichier de code : il ne lit que "
                  "`data/symbols/<build>/frida/enums.tsv` des deux builds archives, apporte "
                  "par `build: True`. Restent les modules que le CHARGEMENT du fichier "
                  "importe -- MESURES, pas supposes : `repo_read`, `symbols_layout`, et depuis "
                  "#10023-r2 `il2cpp_provenance`, dont `symbols_layout` tire l'estampille qui "
                  "ORDONNE les archives (un changement du parseur change donc `previous_build`).",
    },
    "probe_283:mirror": {
        "chemins": ("*.py", "**/*.py"),
        "build": True,
        "toujours": False,
        "raison": "`step_mirror` parse TOUT `.py` du depot (`_fichiers_du_depot('.py')`) pour "
                  "y trouver les classes IntEnum homonymes des quatre enums, et confronte "
                  "leurs membres a la table du build courant. Ni `.ts`, ni `.js`, ni `.md`.",
    },
    "probe_283:exec": {
        "chemins": ("scripts/python/*.py", "scripts/python/**/*.py"),
        "build": True,
        "toujours": False,
        "raison": "`step_exec` ne balaie que `scripts/python/**/*.py` (rglob explicite sur "
                  "`REPO/scripts/python`) : AST + prose par ligne, plus les ordinaux des deux "
                  "builds. Il ne sort jamais de `scripts/python`, et ne lit aucun `.ts`/`.js`.",
    },
    "probe_283:tables": {
        "chemins": ("*.py", "**/*.py", "*.ts", "**/*.ts", "*.js", "**/*.js"),
        "build": True,
        "toujours": False,
        "raison": "`step_tables` cherche les tables `{ordinal: \"Nom\"}` dans TOUT le depot, "
                  "sur les trois suffixes de `_SUFFIXES` -- c'est la seule etape qui lit du "
                  "TypeScript (le motif `UTILITY_TYPE_NAMES` du hook `ai-utility-trace`).",
    },
    "probe_283:prose": {
        "chemins": ("scripts/python/*.py", "scripts/python/**/*.py",
                    "scripts/python/*.md", "scripts/python/**/*.md",
                    "scripts/python/*.ts", "scripts/python/**/*.ts",
                    "scripts/python/*.js", "scripts/python/**/*.js"),
        "build": True,
        "toujours": False,
        "raison": "`step_prose` (etapes 4 et 4bis) rglob sur `REPO/<racine>` avec les QUATRE "
                  "suffixes `.py`/`.md`/`.ts`/`.js`, `<racine>` valant `scripts/python` sous "
                  "l'argv de la banque. Les ordinaux compares viennent des deux tables.",
    },
    "probe_283:on": {
        "chemins": ("scripts/python/*.py", "scripts/python/**/*.py",
                    "scripts/python/*.md", "scripts/python/**/*.md"),
        "build": True,
        "toujours": False,
        "raison": "`step_on` rglob sur `REPO/<racine>` en `.py` et `.md` seulement (pas de "
                  "`.ts`/`.js`), et compare aux ordinaux `EventTriggerType` des deux builds "
                  "-- c'est ce qui separe une ancre `stable` d'une ancre `decalee`.",
    },
}

# Les quatre enums renumerotes, par leur nom PLEINEMENT QUALIFIE (= la cle de `enums.tsv`,
# et le type du 1er argument du symbole natif correspondant).
#   `IdunBattle.DSL.EventTriggerType`        -> `IdunBattleLogic.Entities.DSLTriggers$$On`
#   `IdunBattle.Configuration.UtilityType`   -> `UtilitiesDatabase$$GetUtility`
#   `IdunBattle.Streams.StepType`            -> `IdunBattle.Streams.StreamDispatcher$$Action`
#   `IdunBattle.Operations.DisplaceDirection`-> `IdunBattle.Operations.DisplaceUnitOperation$$Execute`
ENUMS = {
    "EventTriggerType": "IdunBattle.DSL.EventTriggerType",
    "UtilityType": "IdunBattle.Configuration.UtilityType",
    "StepType": "IdunBattle.Streams.StepType",
    "DisplaceDirection": "IdunBattle.Operations.DisplaceDirection",
}

# Racines de noms de variable qui trahissent un de ces enums dans une comparaison / affectation.
_ROOTS = {
    "EventTriggerType": ("event_trigger", "trigger_type", "event_id", "trigger_id", "evt_id"),
    "UtilityType": ("utility_type", "utility_id", "util_type"),
    "StepType": ("step_type", "step_id"),
    "DisplaceDirection": ("displace_dir", "displace_direction", "direction_type"),
}

# Fichiers exemptes, avec la RAISON. Un fichier n'entre ici que s'il ne PEUT pas resoudre par
# nom -- jamais « parce que c'est vieux ».
ALLOWLIST = {
    "scripts/python/probe_283_enum_ordinal_sweep.py":
        "ce probe (ses entiers SONT les donnees du balayage)",
    "scripts/python/engine/dsl/event_trigger_type.py":
        "DEFINIT le mirror EventTriggerType -- confronte par l'etape mirror, pas par exec",
    "scripts/python/engine/utilities/utility_type.py":
        "DEFINIT le mirror UtilityType -- confronte par l'etape mirror, pas par exec",
    "scripts/python/enum_maps.py":
        "genere par regen_enum_maps.py, garde par probe_275_enum_maps_drift.py",
    "scripts/python/tests/test_enum_ordinal_ratchet_offline.py":
        "le cliquet : ses citations `On(0x2b = PreUnitAbility)` sont les DONNEES qui prouvent "
        "que le detecteur mord -- les corriger desarmerait le test",
    "scripts/python/tests/test_1031_appariements_de_sondes_offline.py":
        "meme raison que la ligne au-dessus, pour les crans de #1031 : ses echantillons "
        "PORTENT une quote perimee (`FUN_...(0x4d, .., 0x2b)` + `On(PreUnitAbility)`) et une "
        "ligne a DEUX ancres pour une annotation. Ce sont les DONNEES qui prouvent que le gate "
        "mord ENCORE apres restriction aux quotes, et que le cran d'ambiguite n'est pas inerte "
        "-- les corriger desarmerait les deux contre-epreuves",
    "scripts/python/probe_443r1c_ordinal_index_perime.py":
        "meme raison : sa docstring REPRODUIT la ligne fautive de #443-r1c "
        "(`leaves.get(8)  # 8=Elevation`) et son echantillon d'auto-test la PORTE -- les "
        "corriger desarmerait le detecteur. Confirmation croisee au passage : cette docstring, "
        "elle, NOMME `UtilityType`, donc l'etape 4 y admet les membres ambigus et la voit ; "
        "c'est l'exacte difference avec la ligne d'origine, qui ne le nommait pas",
}

# `hooks-legacy/` est VERSIONNE mais rien de vivant n'en depend : inventorie a part.
INFO_PREFIXES = ("hooks-legacy/",)

# ⚠ Filtre a appliquer au chemin RELATIF au depot, JAMAIS a `p.parts` (absolu) : un agent
# tourne dans `.claude/worktrees/agent-<id>/`, donc TOUT chemin absolu contient `worktrees`.
# Mesure : la 1re version de ce probe rendait « 0 classe trouvee -- aucun mirror Python » et
# `VERDICT: PASS`. Un balayage qui rend zero se lit comme « rien a signaler » ; c'est le meme
# piege que l'exclusion par sous-chaine `engine` mesuree en #281.
_SKIP_PARTS = (".git", "node_modules", "logs", "sources_win", "dist", ".venv")

# ... et c'est CE MEME relatif qui rend correcte, DANS LES DEUX SENS, l'exclusion des
# worktrees IMBRIQUES (#434). Depuis l'arbre principal, `.claude/worktrees/agent-<id>/` est un
# AUTRE checkout du depot : hors perimetre. Depuis un worktree, `REPO` EST ce checkout, donc le
# relatif ne porte pas ce prefixe et le probe ne s'auto-exclut pas. Exclu par CHEMIN COMPLET,
# jamais par le segment `worktrees` seul, pour la meme raison.
#
# Mesure du 2026-08-01, arbre principal a 8 worktrees vivants : 13 501 `.py` dont 11 702 chez
# eux (87 %) et 279 dans `node_modules` -- vrai perimetre 1 514 ; 3 352 `.ts`/`.js` dont 2 296
# chez eux. Les deux SEULES etapes qui balayent la RACINE (`mirror`, `tables`) parsaient donc
# ~9x trop, et leur cout croissait avec le nombre d'agents en vol : elles TENAIENT le mur de la
# banque depuis l'arbre principal (427,2 s et 410,1 s pour un mur de 428,5 s), alors que la
# banque ENTIERE vaut 91,3 s depuis un worktree (qui, lui, n'imbrique aucun autre checkout).
#
# Le trou n'etait pas qu'un cout, et c'est le point principal : un cliquet lance depuis l'arbre
# principal LISAIT le code en cours des autres agents. `logs/ratchets/probe_283_mirror.log` du
# 2026-08-01 19:42 porte 16 lignes de rapport sur 29 sous `.claude/worktrees/` (24 sur 30 pour
# `tables`). Elles etaient vertes ce jour-la ; un agent qui edite SON `event_trigger_type.py`
# aurait fait rougir la banque de l'arbre principal pour une mutation qui n'y est pas.
_SKIP_RELS = (".claude/worktrees",)

# Suffixes reellement balayes. La liste est FIXE parce que le cache ci-dessous range par
# suffixe : y ajouter une extension sans l'ajouter ici rendrait une liste VIDE, pas une erreur.
_SUFFIXES = (".py", ".ts", ".js")

# Builds ARCHIVES, resolus UNE seule fois : `archived_builds()` fait de l'I/O disque.
_ARCHIVES = tuple(archived_builds())


def _ignore(p: Path) -> "str | None":
    """Chemin relatif POSIX du fichier, ou None s'il est hors perimetre."""
    try:
        rel = p.relative_to(REPO).as_posix()
    except ValueError:
        return None
    if any(seg in _SKIP_PARTS for seg in rel.split("/")):
        return None
    return None if any(rel == r or rel.startswith(r + "/") for r in _SKIP_RELS) else rel


# {racine: {suffixe: [chemins tries]}} -- keye sur `REPO` et non global, pour qu'un appelant
# qui repointe la racine (bench, contre-epreuve) ne relise pas le cache de l'autre arbre.
_FICHIERS: dict = {}


def _fichiers_du_depot(suffixe: str) -> list:
    """Fichiers `*<suffixe>` de TOUT le depot -- MEME liste et MEME ordre que
    `sorted(REPO.rglob("*" + suffixe))`, mais elagues A LA SOURCE.

    `rglob` descend PARTOUT puis on filtre : la traversee de `.git`, de `node_modules` et des
    worktrees imbriques etait payee integralement, et leurs fichiers etaient lus et parses.
    `os.walk` laisse elaguer `dirnames` EN PLACE -- on n'y entre jamais. Bonus non recherche :
    il ne suit pas les points de reparse (junction), la ou `rglob` y descend.

    La comparaison de suffixe est INSENSIBLE A LA CASSE, comme `Path.glob` sous Windows :
    `rglob("*.py")` y ramene aussi `Foo.PY`. Un `endswith` strict retirerait ce fichier du
    perimetre en silence."""
    par_suffixe = _FICHIERS.get(REPO)
    if par_suffixe is None:
        par_suffixe = {s: [] for s in _SUFFIXES}
        for dirpath, dirnames, filenames in os.walk(REPO):
            d = Path(dirpath)
            dirnames[:] = [n for n in dirnames if _ignore(d / n) is not None]
            for n in filenames:
                bas = n.lower()
                for s in _SUFFIXES:
                    if bas.endswith(s):
                        par_suffixe[s].append(d / n)
                        break
        for v in par_suffixe.values():
            v.sort()
        _FICHIERS[REPO] = par_suffixe
    return par_suffixe[suffixe]


# ------------------------------------------------------------------------------------------
# Lecture des tables versionnees
# ------------------------------------------------------------------------------------------

# {(racine, suffixe, brut): {Path: texte | None}} -- `None` = illisible ou non-UTF-8.
_SOURCES: dict = {}


def _sources(suffixe: str, brut: bool = False) -> dict:
    """Textes des fichiers `*<suffixe>` du perimetre, LUS EN PARALLELE (#457-r6).

    Les cinq etapes de ce probe relisaient chacune l'arbre, en SERIE et depuis un process
    distinct (une entree de banque par etape). Mesure du 2026-08-03 : l'ouverture d'un fichier
    sous `scripts/` coute ~7 ms (filtre systeme sur les extensions executables), soit ~13 s
    par etape rien qu'a ouvrir -- devant `ast.parse` (7,1 s pour tout `scripts/python/**`).

    `brut=False` reproduit `io.open(p, encoding="utf-8")` (fins de ligne universelles) ;
    `brut=True` reproduit `io.open(p, encoding="utf-8", newline="")`, que les etapes `prose`
    et `on` exigent -- `--fix` REECRIT ces fichiers, et une traduction des fins de ligne y
    serait une modification silencieuse de tout l'arbre.
    """
    cle = (REPO, suffixe, brut)
    cache = _SOURCES.get(cle)
    if cache is not None:
        return cache
    fichiers = _fichiers_du_depot(suffixe)
    out: dict = {}
    for p, data in zip(fichiers, repo_read.read_bytes_many(fichiers)):
        if data is None:
            out[p] = None
            continue
        try:
            texte = data.decode("utf-8")
        except UnicodeDecodeError:
            out[p] = None
            continue
        out[p] = texte if brut else texte.replace("\r\n", "\n").replace("\r", "\n")
    _SOURCES[cle] = out
    return out


def enum_map(build: str, fq: str) -> dict:
    """{ordinal: NOM} d'un enum, lu dans `data/symbols/<build>/frida/enums.tsv`."""
    p = REPO / "data" / "symbols" / build / "frida" / "enums.tsv"
    if not p.is_file():
        return {}
    with p.open(encoding="utf-8") as f:
        for line in f:
            if line.startswith(fq + "\t"):
                out = {}
                for kv in line.rstrip("\n").split("\t", 1)[1].split(","):
                    o, _, n = kv.partition("=")
                    if n:
                        out[int(o)] = n
                return out
    return {}


def all_enums(build: str) -> dict:
    """{nom pleinement qualifie: {ordinal: MEMBRE}} -- TOUTE la table du build.

    Sert a mesurer l'AMBIGUITE d'un nom de membre : `Attack` appartient a une douzaine
    d'enums differents avec des ordinaux differents. Un tel nom ne peut pas, seul, designer
    l'un de nos quatre -- c'est ce calcul qui evite le faux positif de masse."""
    p = REPO / "data" / "symbols" / build / "frida" / "enums.tsv"
    out = {}
    if not p.is_file():
        return out
    with p.open(encoding="utf-8") as f:
        for line in f:
            if line.startswith("#!") or "\t" not in line:
                continue
            fq, _, corps = line.rstrip("\n").partition("\t")
            membres = {}
            for kv in corps.split(","):
                o, _, n = kv.partition("=")
                if n:
                    try:
                        membres[int(o)] = n
                    except ValueError:
                        pass
            if membres:
                out[fq] = membres
    return out


def _by_name(m: dict) -> dict:
    return {v: k for k, v in m.items()}


#: Table dont TOUT ce probe depend. Un repertoire de build qui ne la porte pas ne peut RIEN
#: dire des enums -- c'est un archivage fait pour un AUTRE usage.
_TABLE_ENUMS = ("frida", "enums.tsv")


def builds_sans_table_enums() -> list:
    """Les builds archives qui n'ont PAS `frida/enums.tsv`. Rendus pour etre DITS, pas ignores."""
    return [b for b in archived_builds()
            if not (REPO / "data" / "symbols" / b).joinpath(*_TABLE_ENUMS).is_file()]


def previous_build() -> "str | None":
    """Le build archive le PLUS RECENT QUI PORTE LA TABLE DES ENUMS, ou `None`.

    ⚠ CE N'EST PAS << le dernier repertoire de `data/symbols` >>, et le raccourci a coute
    (#484). `630a9c59` (#482-r3, 2026-08-06) archive `kqkbjqfb6c` pour un usage TOUT AUTRE --
    conserver l'empreinte STRUCTURELLE d'un binaire avant sa disparition -- donc ce repertoire
    ne porte que `BUILD`, `fingerprints/functions.tsv` et `ghidra/functions.tsv`. Aucun
    `frida/enums.tsv` : le binaire n'etait plus la pour le produire.

    `arch[-1]` le designait pourtant comme << le build precedent >>, et `enum_map` rendait `{}`
    pour les QUATRE enums, sans erreur. Effet mesure : **5 tests** de
    `test_enum_ordinal_ratchet_offline.py` rouges sur `master` -- dont trois auto-controles qui
    disaient exactement << le detecteur ne mord plus : l'exemption ne prouverait rien >>.

    ⚠ << LE PLUS RECENT >> EST DESORMAIS UNE MESURE, ET NE L'ETAIT PAS (#10023-r2). Ce foyer lit
    `reversed(archived_builds())`, dont l'ordre venait du NOM du repertoire -- or un hash de build
    est ALEATOIRE. L'accord des deux ordres etait une COINCIDENCE, et il est deja rompu sur le
    depot (`kqkbjqfb6c`, entre le 2026-08-06, precede `rnca9r7q6c`, entre le 2026-07-29, sous le
    tri par nom). Depuis, `symbols_layout.archived_builds()` ordonne par l'estampille de
    provenance des tables. Ici le resultat ne CHANGE pas -- `kqkbjqfb6c` etait deja ecarte par le
    filtre `frida/enums.tsv` -- mais il est FONDE au lieu d'etre chanceux.

    ⚠ ET UN BUILD NON DATABLE N'EST PLUS ELU EN SILENCE : `archived_builds()` place les non-dates
    EN FIN par convention de tri total, donc `reversed(...)` les visite EN PREMIER. Les elire y
    serait exactement le faux vert qu'on repare. Ils sont sautes, et `builds_sans_date()` les
    ENUMERE. Le cas est structurellement rare (l'estampille vit DANS `frida/enums.tsv`, donc un
    build qui porte la table la porte aussi) mais pas impossible : une table produite AVANT la
    mise en place de la provenance n'en a pas, et `il2cpp_provenance.read_stamp` le dit en toutes
    lettres.

    Le filtre porte sur la TABLE, pas sur une liste de hashs a la main : un futur archivage
    partiel (meme motif, autre binaire) sera ecarte tout seul. Et ce qui est ecarte est
    ENUMERABLE (`builds_sans_table_enums`) -- un filtre muet redeviendrait le meme faux vert.
    """
    sans_date = set(builds_sans_date())
    for b in reversed(archived_builds()):
        if b in sans_date:
            continue                       # non ordonnable -> jamais elu << le plus recent >>
        if (REPO / "data" / "symbols" / b).joinpath(*_TABLE_ENUMS).is_file():
            return b
    return None


def builds_avec_table_enums() -> list:
    """Les builds ARCHIVES qui portent `frida/enums.tsv` -- la MEMOIRE disponible, dans l'ordre
    du repertoire. `previous_build()` n'en est que le dernier element."""
    return [b for b in archived_builds()
            if (REPO / "data" / "symbols" / b).joinpath(*_TABLE_ENUMS).is_file()]


def memoire_archivee(fq: str) -> dict:
    """{MEMBRE: frozenset(ordinaux portes sur AU MOINS UN build archive)} -- la source de `olds`.

    ⚠ CE N'EST PAS `previous_build()`, ET LA DIFFERENCE EST TOUT LE SUJET (#10023). Un ordinal
    fige dans le depot y a ete recopie d'un build DONNE, qui n'est pas forcement l'avant-dernier :
    la citation, elle, ne bouge plus, alors que << le build precedent >> AVANCE a chaque
    archivage. Prendre la seule table de `previous_build()` fait donc OUBLIER, en silence, tout
    renumerotage anterieur d'un cran.

    Mesure du 2026-08-17, qui ouvre le dossier : `t6dpr4k06g` (courant) est IDENTIQUE a
    `rnca9r7q6c` (= `previous_build()`) sur les quatre enums -- 0 ordinal divergent. Le seul
    renumerotage jamais mesure est `gqfc5mff6c -> rnca9r7q6c` (**171** membres deplaces :
    36 + 73 + 55 + 7). Sous `previous_build()` seul, le detecteur voyait **0** couple decale et
    devenait donc VACANT : `_compile_larges` rendait `None`, `annotation_de_ligne` ne pouvait plus
    rendre `perimee`, et l'origine d'une citation retombait sur `inconnu`. Sept tests de
    `test_enum_ordinal_ratchet_offline.py` l'ont dit en ROUGE -- c'est exactement ce pour quoi ils
    assertionnent leur propre non-vide.

    L'UNION est MONOTONE : un build archive de plus ne peut qu'AJOUTER de la memoire. C'est ce qui
    rend le detecteur insensible a la cadence des builds, la propriete que la lecture par
    `previous_build()` n'avait pas."""
    out = {}
    for b in builds_avec_table_enums():
        for m, o in _by_name(enum_map(b, fq)).items():
            out.setdefault(m, set()).add(o)
    return {m: frozenset(v) for m, v in out.items()}


def memoire_archivee_par_enum() -> dict:
    """{nom court: memoire_archivee(fq)} pour les QUATRE enums -- ce que les etapes appellent
    `olds`."""
    return {court: memoire_archivee(fq) for court, fq in ENUMS.items()}


def _ords(x) -> frozenset:
    """Normalise une entree de `olds` en ensemble d'ordinaux.

    Les deux formes coexistent VOLONTAIREMENT : `memoire_archivee` rend un `frozenset` par membre
    (plusieurs builds archives), tandis qu'un appelant qui veut confronter a UN build precis passe
    encore un `int` (`_by_name(enum_map(<build>, fq))`). Accepter les deux evite de dupliquer
    chaque consommateur -- et un `None` (membre inconnu de toute archive) rend l'ensemble VIDE,
    jamais une exception."""
    if x is None:
        return frozenset()
    if isinstance(x, int):
        return frozenset((x,))
    return frozenset(x)


# ------------------------------------------------------------------------------------------
# Etape 0 -- le diff
# ------------------------------------------------------------------------------------------

def step_diff(verbose: bool) -> int:
    cur, prev = current_build(), previous_build()
    print("[283] etape 0 : diff des 4 enums -- %s -> %s" % (prev or "(aucun archive)", cur))
    if prev is None:
        print("   un seul build versionne : diff impossible (ce n'est pas une erreur)")
        return 0
    for court, fq in ENUMS.items():
        o, n = enum_map(prev, fq), enum_map(cur, fq)
        div = [i for i in sorted(set(o) | set(n)) if o.get(i) != n.get(i)]
        on, nn = _by_name(o), _by_name(n)
        moved = [(m, on[m], nn[m]) for m in sorted(set(on) & set(nn)) if on[m] != nn[m]]
        gone = sorted(set(on) - set(nn))
        added = sorted(set(nn) - set(on))
        print("   %-18s %s(%d) -> %s(%d) : %d ordinaux divergents, %d membres deplaces"
              % (court, prev, len(o), cur, len(n), len(div), len(moved)))
        print("       retires : %s ; ajoutes : %s ; 1er ordinal divergent : %s"
              % (", ".join("%s(%d)" % (g, on[g]) for g in gone) or "-",
                 ", ".join("%s(%d)" % (a, nn[a]) for a in added) or "-",
                 ("%d (%s -> %s)" % (div[0], o.get(div[0]), n.get(div[0]))) if div else "-"))
        if verbose:
            for m, a, b in moved:
                print("         %-42s %3d -> %3d" % (m, a, b))
    return 0


# ------------------------------------------------------------------------------------------
# Etape 1 -- les MIRRORS Python
# ------------------------------------------------------------------------------------------

def _int_enum_classes(tree: ast.AST) -> dict:
    """{nom de classe: {MEMBRE: valeur}} pour toute `class X(IntEnum)` / `class X(Enum)`."""
    out = {}
    for node in ast.walk(tree):
        if not isinstance(node, ast.ClassDef):
            continue
        bases = {b.id if isinstance(b, ast.Name) else
                 (b.attr if isinstance(b, ast.Attribute) else "") for b in node.bases}
        if not (bases & {"IntEnum", "Enum", "IntFlag"}):
            continue
        membres = {}
        for st in node.body:
            cible = None
            if isinstance(st, ast.Assign) and len(st.targets) == 1 \
                    and isinstance(st.targets[0], ast.Name):
                cible, val = st.targets[0].id, st.value
            elif isinstance(st, ast.AnnAssign) and isinstance(st.target, ast.Name) \
                    and st.value is not None:
                cible, val = st.target.id, st.value
            if cible is None:
                continue
            if isinstance(val, ast.Constant) and isinstance(val.value, int) \
                    and not isinstance(val.value, bool):
                membres[cible] = val.value
        if membres:
            out[node.name] = membres
    return out


def _echappe(nom: str) -> str:
    """`None_` -> `None` : le mirror echappe le mot-clef Python, le jeu ne l'echappe pas.

    ⚠ REGLE ETROITE, ET C'EST VOLONTAIRE. Un `rstrip("_")` general masquerait une vraie
    divergence -- un membre `Foo_` du build et un `Foo` du mirror sont deux noms DIFFERENTS.
    Seul `None` ne peut PAS s'ecrire en Python. Jumeau : `probe_313_enum_mirror_bijection._echappe`,
    qui portait deja cette regle -- c'est son absence ici qui rendait `master` ROUGE sur
    `StepType.None_` (build `rnca9r7q6c` : `0=None`) depuis l'arrivee du mirror (#477-r15)."""
    return nom[:-1] if nom == "None_" else nom


_CACHE_MIRROR = None

#: ⚠ MODE ESPION, pose par `--verifier-cache` (#486-r17). A `True`, les DEUX caches sont
#: construits avec `relire=False` : le fichier est charge mais jamais servi, donc tout est
#: recalcule et `verdict_cache.verifier` peut confronter le disque au calcul. C'est le SEUL
#: controle qui voie une entree FALSIFIEE DE FACON COHERENTE -- un verdict faux ecrit en face du
#: hash JUSTE. Aucune cle ne peut la voir, par construction.
_ESPION = False

#: Les caches que ce run a REECRITS. `main` leur demande ensuite si l'ecriture a CHANGE le
#: fichier VERSIONNE (cran de fraicheur #486-r22). Deux caches, et `--step` n'en ecrit qu'un a la
#: fois : c'est pourquoi c'est une liste alimentee au fil de l'eau et pas un couple fixe.
_ECRITS: list = []


def _cache_mirror():
    """Cache PAR FICHIER de l'EXTRACTION de `step_mirror` (#1029).

    ⚠ SON CONTEXTE NE PORTE PAS LE BUILD, et c'est deliberé : ce qu'on cache est
    `_int_enum_classes(tree)` -- les membres qu'un fichier DECLARE -- une fonction pure de son
    contenu. La confrontation aux tables du build se fait APRES, hors cache. Un changement de build
    fait donc bouger le VERDICT sans invalider une seule entree, ce qui est exact : le fichier n'a
    pas change. Mettre le build au contexte aurait vide le cache a chaque re-dump, pour rien.
    """
    global _CACHE_MIRROR
    if _CACHE_MIRROR is None:
        import verdict_cache
        ici = Path(__file__).resolve().parent
        _CACHE_MIRROR = verdict_cache.CacheCliquet(
            "probe_283_step_mirror",
            contexte=verdict_cache.sha_fichiers_texte(ici / "probe_283_enum_ordinal_sweep.py"),
            relire=not _ESPION,
            notes=("# On cache l'EXTRACTION (`_int_enum_classes` restreinte aux 4 enums), PAS le",
                   "# verdict : elle ne depend que du contenu du fichier. La comparaison aux tables",
                   "# du build reste hors cache, donc un re-dump ne perime AUCUNE entree."))
    return _CACHE_MIRROR


def step_mirror(verbose: bool) -> list:
    """Confronte chaque mirror Python d'un des 4 enums, MEMBRE PAR MEMBRE, a `enums.tsv`."""
    cur = current_build()
    refs = {court: _by_name(enum_map(cur, fq)) for court, fq in ENUMS.items()}
    bad, vus = [], []
    textes = _sources(".py")
    import verdict_cache
    cache = _cache_mirror()
    for p in _fichiers_du_depot(".py"):
        rel = _ignore(p)
        if rel is None:
            continue
        src = textes.get(p)
        if src is None:
            continue
        declares = cache.obtenir(rel, "mirror", verdict_cache.sha_texte(src))
        if declares is verdict_cache.MANQUE:
            try:
                tree = ast.parse(src, filename=rel)
            except SyntaxError:
                declares = {}
            else:
                declares = {c: m for c, m in _int_enum_classes(tree).items() if c in ENUMS}
            cache.poser(rel, "mirror", verdict_cache.sha_texte(src), declares)
        for cls, membres in declares.items():
            ref = refs[cls]
            faux = [(m, v, ref.get(_echappe(m))) for m, v in sorted(membres.items())
                    if ref.get(_echappe(m)) != v]
            vus.append((rel, cls, len(membres), len(ref), len(faux)))
            for m, v, attendu in faux:
                bad.append((rel, cls, m, v, attendu))
    print("[283] etape 1 : mirrors Python des 4 enums -- %d classe(s) trouvee(s)" % len(vus))
    for rel, cls, n, nref, nfaux in vus:
        print("   %-58s %s : %d/%d membres, %d divergent(s)" % (rel, cls, n, nref, nfaux))
    for court in ENUMS:
        if not any(v[1] == court for v in vus):
            print("   (aucun mirror Python de %s -- resolution par nom uniquement)" % court)
    for rel, cls, m, v, attendu in bad:
        print("   FAIL %s : %s.%s = %s ; le build %s dit %s"
              % (rel, cls, m, v, cur, attendu if attendu is not None else "MEMBRE ABSENT"))
    #: MODE ESPION : ce run sert a CONFRONTER le disque, pas a le refaire. Reecrire effacerait
    #: precisement l'entree falsifiee qu'on cherche a voir.
    if not _ESPION:
        cache.enregistrer()
        _ECRITS.append(cache)
    return bad


# ------------------------------------------------------------------------------------------
# Etape 2 -- litteraux EXECUTABLES (AST)
# ------------------------------------------------------------------------------------------

_ANNOT = re.compile(
    r"\b(?P<enum>%s)\s*[.:]\s*(?P<membre>[A-Za-z_][A-Za-z0-9_]*)" % "|".join(ENUMS))


def _lit(node) -> "list | None":
    if isinstance(node, ast.Constant) and isinstance(node.value, int) \
            and not isinstance(node.value, bool):
        return [node.value]
    if isinstance(node, (ast.Tuple, ast.List, ast.Set)):
        out = []
        for e in node.elts:
            if isinstance(e, ast.Constant) and isinstance(e.value, int) \
                    and not isinstance(e.value, bool):
                out.append(e.value)
            else:
                return None
        return out or None
    return None


def _root_of(node) -> "str | None":
    """Nom d'enum devine depuis le NOM de la variable/attribut/cle comparee."""
    nom = None
    if isinstance(node, ast.Name):
        nom = node.id
    elif isinstance(node, ast.Attribute):
        nom = node.attr
    elif isinstance(node, ast.Subscript) and isinstance(node.slice, ast.Constant) \
            and isinstance(node.slice.value, str):
        nom = node.slice.value
    elif isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) \
            and node.func.attr == "get" and node.args \
            and isinstance(node.args[0], ast.Constant) \
            and isinstance(node.args[0].value, str):
        nom = node.args[0].value
    if not nom:
        return None
    bas = nom.lower()
    for court, racines in _ROOTS.items():
        if any(r in bas for r in racines):
            return court
    return None


def _membre_enum_du_code(node, court: str) -> "str | None":
    """Le membre `<court>.<Membre>` ECRIT DANS LE CODE de `node`, ou `None`.

    ⚠ CE N'EST PAS UN DOUBLON DE `_membre_vise`, ET LA DIFFERENCE EST TOUT LE SUJET (#1031).
    `_membre_vise` lit la PROSE de la ligne (tokens COMMENT/STRING), et c'est volontaire : une
    ANNOTATION est du commentaire. Mais le depot ecrit aussi le motif inverse -- le membre est
    dans le CODE, en EGALITE avec le littéral :

        assert BOF.BookOfFateAbility.event_id == 38 == int(EventTriggerType.NormalAttack)

    Ce site n'est PAS un ordinal en dur : c'est le FIGEAGE que la doctrine EXIGE (<< le registre
    ne suffit pas -- il faut aussi FIGER l'ordinal ECRIT AU SITE >>, le cran que `probe_313` ne
    peut pas voir puisqu'il redevient vert des qu'on regenere le mirror). Le convertir le rendrait
    TAUTOLOGIQUE (`int(E.X) == int(E.X)`), donc inerte -- on detruirait le cliquet en croyant
    l'appliquer. Mesure du 2026-08-13 : 3 des 4 sites que l'etape 2 reclamait sont de cette forme.

    La chaine ENTIERE est visitee (`ast.walk`), pas les deux cotes d'un `op` : `a == 38 ==
    int(E.X)` a trois operandes et `visit_Compare` s'arrete au premier couple qui mord.
    Restreint au nom PLEIN de l'enum : un alias (`E.X`) ne prouve pas de quel enum il s'agit,
    et deviner ici, c'est exactement la faute que ce probe existe pour empecher."""
    for n in ast.walk(node):
        if isinstance(n, ast.Attribute) and isinstance(n.value, ast.Name) \
                and n.value.id == court:
            return n.attr
    return None


def _prose_par_ligne(src: str) -> dict:
    """{lineno: texte des tokens COMMENT/STRING commencant sur cette ligne}.

    LE TOKEN-AWARENESS EST ICI, et il est indispensable dans LES DEUX SENS :

    * chercher l'annotation dans la ligne BRUTE fait prendre `TILE_LEAVES[
      UtilityType.CapturePoint][1]` pour « le littéral 1 doit valoir CapturePoint » -- 7 faux
      positifs mesures, tous sur du code DEJA correct (il utilise le MEMBRE) ;
    * ne la chercher que dans les commentaires raterait
      `assert t.event_id == 19, "le trigger ecoute On(0x13=TurnStart_Other)"`, ou le membre
      vise n'est nomme que dans le MESSAGE.

    D'ou : commentaires ET chaines, jamais le code."""
    out: dict = {}
    try:
        toks = list(tokenize.generate_tokens(io.StringIO(src).readline))
    except (tokenize.TokenError, IndentationError, SyntaxError):
        return out
    for tk in toks:
        if tk.type in (T.COMMENT, T.STRING):
            out[tk.start[0]] = out.get(tk.start[0], "") + " " + tk.string
    return out


def _signatures_positionnelles(arbres: dict) -> dict:
    """{nom appelable: (index de l'argument, enum court)} pour tout `def`/ctor du perimetre dont
    un PARAMETRE porte l'une des racines de `_ROOTS`.

    POURQUOI CETTE PASSE EXISTE (#315). Les quatre motifs d'origine (compare / assign / index /
    kwarg) partagent une hypothese : le nom de l'enum est VISIBLE sur la ligne du littéral. Un
    argument POSITIONNEL le cache derriere la signature de l'appele -- `TriggerEvent(61, 1, 2,
    ...)` ne nomme rien, et deux tels sites vivaient dans `test_effect_trigger_channels.py`
    pendant que le probe rendait `0 a lire`. Le contrat est pourtant aussi sur que celui d'un
    kwarg : c'est la MEME heuristique `_ROOTS`, lue sur le parametre au lieu du mot-cle.

    On DERIVE la table du depot, jamais d'une liste ecrite a la main : un appelable renomme ou
    ajoute est couvert sans toucher au probe.

    ⚠ La table est GLOBALE, donc un HOMONYME la empoisonne -- et le depot en est plein de petits
    helpers locaux. Mesure #420 : `_ev` a **5 definitions**, dont UNE SEULE typee
    (`_ev(event_id, actor)` de `test_448_r2_teleporting_in_offline.py`) ; elle faisait lire le
    `_ev(0)` de `test_stream_events_offline.py` -- ou le 1er parametre s'appelle `step` -- comme
    un `EventTriggerType` fige, et le VERDICT tombait a FAIL. Un nom n'entre donc dans la table
    que si TOUTES ses definitions du perimetre s'accordent sur le meme (index, enum)."""
    vus: dict = {}
    for _rel, tree in arbres.items():
        for nom, specs in contribs_signatures(tree).items():
            vus.setdefault(nom, set()).update(tuple(s) if s is not None else None
                                              for s in specs)
    # un nom AMBIGU (plusieurs definitions qui ne s'accordent pas, `None` compris) est ecarte
    return {nom: next(iter(s)) for nom, s in vus.items()
            if len(s) == 1 and next(iter(s)) is not None}


def contribs_signatures(tree) -> dict:
    """`{nom: [spec, ...]}` pour UN SEUL arbre -- la contribution de ce fichier a la table globale.

    EXTRAITE de `_signatures_positionnelles` (#1029) pour la rendre CACHABLE PAR FICHIER : la
    table finale n'est qu'un MERGE de ces contributions, donc chacune ne depend QUE de son propre
    fichier. La reconciliation -- un nom dont les definitions ne s'accordent pas est ecarte --
    reste GLOBALE, dans la fonction ci-dessus : c'est elle qui a besoin de tout le perimetre, pas
    l'extraction.

    UNE SEULE passe de `ast.walk` (#486-r5) : il y en avait DEUX, la premiere ne servant qu'a
    construire `classe_de`. Sur ce corpus (2090 fichiers, 3,9 M de noeuds), le walk complet coute
    ~7 s -- soit ~11 s des 22,3 s de cette fonction, mesure du 2026-08-06. Les `def` sont accumules
    puis traites APRES la boucle : le resultat ne depend donc d'AUCUNE hypothese sur l'ordre de
    parcours de `ast.walk`.
    """
    classe_de, defs = {}, []
    for m in ast.walk(tree):
        if isinstance(m, ast.ClassDef):
            for st in m.body:
                classe_de[id(st)] = m.name
        elif isinstance(m, (ast.FunctionDef, ast.AsyncFunctionDef)):
            defs.append(m)
    out: dict = {}
    for n in defs:
        args = [a.arg for a in (n.args.posonlyargs + n.args.args)]
        lie = 1 if (args and args[0] in ("self", "cls")) else 0
        # un ctor s'appelle par le nom de la CLASSE, et `self` ne compte pas
        nom = classe_de.get(id(n)) if n.name == "__init__" else n.name
        if not nom:
            continue
        spec = None
        for i, a in enumerate(args):
            bas = a.lower()
            court = next((c for c, racines in _ROOTS.items()
                          if any(r in bas for r in racines)), None)
            if court is None:
                continue
            if i - lie >= 0:
                spec = (i - lie, court)
            break
        out.setdefault(nom, []).append(spec)
    return out


class _ExecSweep(ast.NodeVisitor):
    """Trois motifs, et seulement ceux-la :

    * comparaison / affectation / index / kwarg dont un cote porte un NOM qui trahit l'enum
      (`t.event_id == 19`, `EVENT_ID = 0x2a`) ;
    * littéral dont la PROSE de la ligne porte une annotation `<Enum>.<Membre>` -- c'est le
      motif exact de #272 (`CAPTURE_POINT = 24  # UtilityType.CapturePoint`) ;
    * argument POSITIONNEL passe a un appelable dont la SIGNATURE nomme l'enum (#315) -- le seul
      des trois ou rien, sur la ligne du littéral, ne trahit l'enum.

    TOUT littéral trouve est un DEFAUT, meme s'il est juste aujourd'hui (doctrine `#254b-b`) :
    rien ne signalera son invalidation au prochain build. Le probe dit lequel des deux c'est."""

    def __init__(self, prose: dict, refs: dict, sigs: "dict | None" = None,
                 olds: "dict | None" = None):
        self.prose = prose
        self.refs = refs
        self.sigs = sigs or {}
        # valeurs qui EXISTENT dans l'enum, sur le build courant OU sur un build archive. Un
        # littéral hors de cet ensemble ne DESIGNE aucun membre : ce n'est pas un ordinal.
        # `_ords` : une entree de `olds` est soit un ordinal (un build precis), soit l'ensemble
        # des ordinaux archives du membre (`memoire_archivee`, #10023).
        self.connues = {c: set(r.values()) | {o
                                              for v in (olds or {}).get(c, {}).values()
                                              for o in _ords(v)}
                        for c, r in refs.items()}
        self.hits: list = []
        self.hors: list = []
        #: Les littéraux CONFRONTES au membre nomme dans le CODE (#1031) -- comptes et imprimes,
        #: jamais rendus au verdict : ce sont des CLIQUETS, pas des defauts. Cf.
        #: `_membre_enum_du_code`. Un figeage qui MENT, lui, part en `hits` avec `ok = False`.
        self.confrontes: list = []

    def _membre_vise(self, lineno: int, enum: "str | None"):
        """(enum, membre) cite par la PROSE de la ligne, ou (None, None)."""
        txt = self.prose.get(lineno, "")
        if not txt:
            return None, None
        m = _ANNOT.search(txt)
        if m:
            return m.group("enum"), m.group("membre")
        if enum:
            # membre NU d'un enum deja identifie par le nom de la variable ; on retient le
            # plus LONG (un nom court peut etre le prefixe d'un autre).
            cands = [n for n in self.refs.get(enum, {}) if re.search(r"\b%s\b" % re.escape(n), txt)]
            if cands:
                return enum, max(cands, key=len)
        return None, None

    def _check(self, lineno: int, vals: list, court: "str | None", quoi: str,
               membre_code: "str | None" = None):
        e_cite, membre = self._membre_vise(lineno, court)
        enum = court or e_cite
        if enum is None:
            return
        ref = self.refs.get(enum, {})
        inv = {o: n for n, o in ref.items()}
        #: ⚠ LE FIGEAGE CONFRONTE PASSE AVANT TOUT LE RESTE (#1031), et il n'est un vert QUE
        #: parce qu'il est VERIFIE : le membre ecrit dans le code doit valoir EXACTEMENT le
        #: littéral sur le build COURANT. S'il ne le vaut pas, la ligne fige un ordinal que le
        #: nom qu'elle porte ne designe plus -- c'est un FAIL, et le plus grave des trois
        #: (le site se croit garde). On ne se contente donc jamais de la PRESENCE du membre.
        if membre_code is not None and membre_code in ref:
            for v in vals:
                if ref[membre_code] == v:
                    self.confrontes.append((lineno, enum, quoi, v, membre_code))
                else:
                    self.hits.append((lineno, enum, quoi, v, inv.get(v, "?"),
                                      membre_code, ref[membre_code], False))
            return
        for v in vals:
            if v not in self.connues.get(enum, set()):
                # HORS PLAGE : aucun membre ne porte cette valeur, ni sur le build courant ni
                # sur un archive -- donc ce n'est pas un ordinal fige, c'est une SENTINELLE.
                # Mesure : `WeightedUtility(utility_type=99999)` de
                # `test_353r1_ramming_speed_charge_tile_offline.py` EXIGE un type hors base (il
                # verifie que `UtilityDecider.CalculateUtility` LEVE au lieu de compter 0). Sans
                # ce gate, l'unique faux positif du probe faisait echouer le verdict sur
                # `origin/master`, ce qui interdisait d'en faire un cliquet permanent.
                self.hors.append((lineno, enum, quoi, v))
                continue
            attendu = ref.get(membre) if (membre and e_cite == enum) else None
            ok = (attendu == v) if attendu is not None else None
            self.hits.append((lineno, enum, quoi, v, inv.get(v, "?"), membre, attendu, ok))

    def visit_Compare(self, node):
        sides = [node.left] + list(node.comparators)
        for i in range(len(node.ops)):
            for a, b in ((sides[i], sides[i + 1]), (sides[i + 1], sides[i])):
                court = _root_of(a)
                vals = _lit(b)
                if court and vals:
                    #: Le membre est cherche sur la chaine ENTIERE, pas sur le couple qui a
                    #: mordu : `x == 38 == int(E.NormalAttack)` place le membre au 3e operande,
                    #: que la boucle ci-dessus n'atteint jamais (elle `break` au premier couple).
                    self._check(node.lineno, vals, court, "compare",
                                _membre_enum_du_code(node, court))
                    break
        self.generic_visit(node)

    def visit_Assign(self, node):
        vals = _lit(node.value)
        if vals:
            court = None
            for t in node.targets:
                court = court or _root_of(t)
            self._check(node.lineno, vals, court, "assign")
        self.generic_visit(node)

    def visit_AnnAssign(self, node):
        if node.value is not None:
            vals = _lit(node.value)
            if vals:
                self._check(node.lineno, vals, _root_of(node.target), "assign")
        self.generic_visit(node)

    def visit_Subscript(self, node):
        vals = _lit(node.slice)
        if vals:
            self._check(node.lineno, vals, _root_of(node.value), "index")
        self.generic_visit(node)

    def visit_keyword(self, node):
        vals = _lit(node.value)
        if vals and node.arg:
            bas = node.arg.lower()
            for court, racines in _ROOTS.items():
                if any(r in bas for r in racines):
                    self._check(node.value.lineno, vals, court, "kwarg")
                    break
        self.generic_visit(node)

    def visit_Call(self, node):
        f = node.func
        nom = (f.id if isinstance(f, ast.Name)
               else f.attr if isinstance(f, ast.Attribute) else None)
        spec = self.sigs.get(nom) if nom else None
        if spec:
            idx, court = spec
            if 0 <= idx < len(node.args):
                vals = _lit(node.args[idx])
                if vals:
                    self._check(node.args[idx].lineno, vals, court, "posarg")
        # ACCESSEUR de dict : `d.get(3)` porte EXACTEMENT le meme contrat que `d[3]`, que
        # `visit_Subscript` sert deja -- l'asymetrie n'etait qu'un oubli, et #443-r1c l'a payee
        # (`leaves.get(8)` invisible ici). Meme heuristique `_root_of` sur le RECEPTEUR, donc
        # aucune regle nouvelle. A 0 site le jour ou elle est posee : elle ferme la forme, elle
        # ne rattrape rien -- ce qui a rattrape #443-r1c est `probe_443r1c` (la ligne CITE ses
        # membres en prose ; `leaves` ne porte aucune racine `_ROOTS`).
        if isinstance(f, ast.Attribute) and f.attr in ("get", "pop", "setdefault") and node.args:
            vals = _lit(node.args[0])
            if vals:
                self._check(node.args[0].lineno, vals, _root_of(f.value), "accesseur")
        self.generic_visit(node)


_CACHE_283: dict = {}


def _cache_283(cur: str, prev):
    """Le cache PAR FICHIER de `step_exec` (#1029), un par JEU DE TABLES.

    ⚠ LE CONTEXTE PORTE TOUS LES BUILDS LUS, et c'est ce qui rend le cache sur : `step_exec`
    compare les litteraux aux ordinaux du build COURANT **et** de TOUTES les archives (`refs` et
    `olds`, #10023 -- c'etait la seule archive la plus recente avant). Un cache servi sous un autre
    jeu attesterait une comparaison faite contre d'autres tables -- le meme vice que partager un
    verdict entre deux ancrages de grille. `prev` est donc une LISTE de builds, pas un seul :
    archiver une table de plus doit INVALIDER le cache, puisqu'elle change ce qui est connu.
    """
    cle = "%s|%s" % (cur, ",".join(prev) if isinstance(prev, (list, tuple)) else (prev or "-"))
    if cle not in _CACHE_283:
        import verdict_cache
        ici = Path(__file__).resolve().parent
        # LES BUILDS VONT DANS LE CONTEXTE, PAS DANS LE NOM DE FICHIER. Un nom qui les porte
        # laisserait un ORPHELIN versionne a chaque mise a jour du jeu ; dans le contexte, un
        # couple different vide simplement le cache -- meme forme que `probe_313`.
        _CACHE_283[cle] = verdict_cache.CacheCliquet(
            "probe_283_step_exec",
            contexte=verdict_cache.sha_texte(
                verdict_cache.sha_fichiers_texte(ici / "probe_283_enum_ordinal_sweep.py")
                + "|" + cle),
            relire=not _ESPION,
            notes=("# DEUX appels par fichier : `sigs` (contribution a la table des signatures,",
                   "# cle = sha du fichier SEUL) et `hits` (cle = sha du fichier COMPOSE avec celui",
                   "# de la table globale, dont les hits dependent). Un port ordinaire ne change",
                   "# aucune signature, donc `sha_sigs` est stable et les fichiers inchanges",
                   "# restent chauds."))
    return _CACHE_283[cle]


def step_exec(verbose: bool) -> list:
    cur = current_build()
    refs = {court: _by_name(enum_map(cur, fq)) for court, fq in ENUMS.items()}
    olds = memoire_archivee_par_enum()      # TOUTES les archives, pas la derniere (#10023)
    fails, infos, oks, hors, confrontes = [], [], [], [], []
    # Lecture PARALLELE (#457-r6) : l'ouverture pese ~7 ms par fichier sous `scripts/`, soit
    # ~13 s des ~37 s de cette etape. L'ordre du rapport ne change pas -- il vient du
    # `sorted(...)` plus bas, pas de l'ordre de lecture. La lecture RESTE inconditionnelle : c'est
    # elle qui donne le sha, donc la cle du cache -- pas de mtime, pas de taille (heuristiques que
    # `verdict_cache` proscrit).
    a_lire = [p for p in sorted((REPO / "scripts" / "python").rglob("*.py"))
              if _ignore(p) is not None]
    octets = {}
    for p, data in zip(a_lire, repo_read.read_bytes_many(a_lire)):
        if data is not None:
            octets[_ignore(p)] = data

    import verdict_cache
    cache = _cache_283(cur, builds_avec_table_enums())
    shas = {rel: verdict_cache.sha_texte(repr(data)) for rel, data in octets.items()}
    arbres, sources = {}, {}

    def _arbre(rel):
        """Parse A LA DEMANDE : un fichier dont les DEUX entrees sont chaudes n'est jamais parse."""
        if rel not in arbres:
            try:
                src = octets[rel].decode("utf-8").replace("\r\n", "\n").replace("\r", "\n")
                arbres[rel] = ast.parse(src, filename=rel)
                sources[rel] = src
            except (SyntaxError, UnicodeDecodeError):
                arbres[rel] = None
        return arbres[rel]

    # PASSE 1 -- les CONTRIBUTIONS de signatures. Elles ne dependent QUE du fichier, donc leur cle
    # est son seul sha. La table globale est le MERGE ; elle a besoin de tout le perimetre, mais
    # plus de tous les ARBRES.
    contribs = {}
    for rel in sorted(octets):
        v = cache.obtenir(rel, "sigs", shas[rel])
        if v is verdict_cache.MANQUE:
            tree = _arbre(rel)
            v = contribs_signatures(tree) if tree is not None else {}
            cache.poser(rel, "sigs", shas[rel], v)
        contribs[rel] = v
    vus: dict = {}
    for c in contribs.values():
        for nom, specs in c.items():
            vus.setdefault(nom, set()).update(tuple(s) if s is not None else None for s in specs)
    sigs = {nom: next(iter(s)) for nom, s in vus.items()
            if len(s) == 1 and next(iter(s)) is not None}
    if verbose:
        print("   (signatures positionnelles derivees : %d appelable(s))" % len(sigs))
        for nom in sorted(sigs):
            print("      %-42s arg#%d = %s" % (nom, sigs[nom][0], sigs[nom][1]))

    # PASSE 2 -- les HITS. Ils dependent du fichier ET de la table globale : la cle compose donc les
    # deux shas. Un port ordinaire ne change AUCUNE signature -> `sha_sigs` est stable -> tous les
    # fichiers inchanges restent chauds.
    sha_sigs = verdict_cache.sha_texte(repr(sorted(sigs.items())))
    for rel in sorted(octets):
        if rel in ALLOWLIST:
            continue
        cle = verdict_cache.sha_texte(shas[rel] + "|" + sha_sigs)
        v = cache.obtenir(rel, "hits", cle)
        if v is verdict_cache.MANQUE:
            tree = _arbre(rel)
            if tree is None:
                continue
            sw = _ExecSweep(_prose_par_ligne(sources[rel]), refs, sigs, olds)
            sw.visit(tree)
            v = {"hits": [list(h) for h in sw.hits], "hors": [list(h) for h in sw.hors],
                 "confrontes": [list(c) for c in sw.confrontes]}
            cache.poser(rel, "hits", cle, v)
        for lineno, enum, quoi, val, nom_courant, membre, attendu, ok in v["hits"]:
            row = (rel, lineno, enum, quoi, val, nom_courant, membre, attendu, ok)
            (fails if ok is False else oks if ok is True else infos).append(row)
        for lineno, enum, quoi, val in v["hors"]:
            hors.append((rel, lineno, enum, quoi, val))
        #: `.get` : une entree de cache ECRITE AVANT #1031 ne porte pas cette cle. Le contexte du
        #: cache compose deja le sha de CE fichier, donc le cas ne peut pas survenir en service --
        #: mais un appelant qui repointe le cache ne doit pas lever, il doit compter zero.
        for lineno, enum, quoi, val, membre in v.get("confrontes", []):
            confrontes.append((rel, lineno, enum, quoi, val, membre))
    if not _ESPION:                                    # cf. `step_mirror`
        cache.enregistrer()
        _ECRITS.append(cache)
    print("[283] etape 2 : litteraux EXECUTABLES en contexte enum -- %d FAUX aujourd'hui, "
          "%d justes-mais-figes, %d a lire (+%d hors plage, NON comptes) "
          "(+%d CONFRONTES au membre ecrit dans le code, NON comptes)"
          % (len(fails), len(oks), len(infos), len(hors), len(confrontes)))
    for rel, ln, enum, quoi, v, membre in (confrontes if verbose else confrontes[:6]):
        print("   CONF %s:%d  %s [%s] = %s == %s.%s -- FIGEAGE confronte dans le code, "
              "le cliquet que probe_313 ne voit pas" % (rel, ln, quoi, enum, v, enum, membre))
    for rel, ln, enum, quoi, v in (hors if verbose else hors[:6]):
        print("   hors %s:%d  %s [%s] = %s -- aucun membre ne porte cette valeur (sentinelle)"
              % (rel, ln, quoi, enum, v))
    for rel, ln, enum, quoi, v, nom, membre, attendu, _ in fails:
        print("   FAIL %s:%d  %s [%s] = %s -> designe %s.%s ; la prose vise %s (= %s)"
              % (rel, ln, quoi, enum, v, enum, nom, membre, attendu))
    for rel, ln, enum, quoi, v, nom, membre, attendu, _ in oks:
        print("   FIGE %s:%d  %s [%s] = %s = %s.%s -- juste aujourd'hui, faux au prochain build"
              % (rel, ln, quoi, enum, v, enum, nom))
    for rel, ln, enum, quoi, v, nom, membre, attendu, _ in infos:
        print("   ???  %s:%d  %s [%s] = %s -> designe %s.%s (prose muette : a lire)"
              % (rel, ln, quoi, enum, v, enum, nom))
    return fails + oks + infos


# ------------------------------------------------------------------------------------------
# Etape 3 -- tables de NOMS indexees par ordinal
# ------------------------------------------------------------------------------------------

_TAB_DICT = re.compile(r"(\d+)\s*:\s*[\"']([A-Za-z_][A-Za-z0-9_.]*)[\"']")
_TAB_STR = re.compile(r"[\"']([A-Za-z_][A-Za-z0-9_.]*)[\"']")
# Affectation `<NOM> [: type] = {` ou `= [` -- Python, TS et JS partagent la forme.
_TAB_HEAD = re.compile(r"\b(?P<nom>[A-Za-z_][A-Za-z0-9_]*)\s*(?::[^=\n]+)?=\s*(?P<open>[\{\[])")
# Une SEQUENCE positionnelle n'est une table d'ordinaux que si son nom le dit. Sinon c'est une
# simple liste de noms : `cats.lifecycle = ["AddUnit", "AddMachine", ...]` de `battle-log.js`
# est un mapping nom->categorie, PAS une table indexee -- 8 faux positifs mesures sans ce gate.
_TAB_SEQ_NOM = re.compile(r"(LABEL|LABELS|NAMES|NOMS)\b")


def _bloc(src: str, i: int, ouvrant: str) -> str:
    """Sous-chaine equilibree depuis `src[i] == ouvrant` (approximation : les delimiteurs
    dans des chaines sont rares dans ces tables et ne changent pas le classement)."""
    fermant = "}" if ouvrant == "{" else "]"
    prof, j = 0, i
    while j < len(src):
        if src[j] == ouvrant:
            prof += 1
        elif src[j] == fermant:
            prof -= 1
            if prof == 0:
                return src[i:j + 1]
        j += 1
    return src[i:]


def _classe_table(paires: list, refs: dict) -> "tuple | None":
    """Une table {ordinal: nom} appartient-elle a l'un des 4 enums ? Si oui, rend
    (enum, [divergences]). Le critere est la MAJORITE des noms, pas leur position :
    une table decalee garde ses noms, c'est justement ce qui la rend muette."""
    if len(paires) < 4 or len({nom for _, nom in paires}) < 3:
        return None                       # table a valeur quasi-constante : pas un enum
    meilleur, score = None, 0
    for court, ref in refs.items():
        if any(o not in set(ref.values()) for o, _ in paires):
            # une cle HORS PLAGE prouve que la table n'est pas indexee par CET enum.
            # Sans ce gate, `_PLAYBOOK_PROFILE_OVERRIDE = {1020: "None", 1066: "Psychic", ...}`
            # passait pour une table `StepType` : `None` EST le membre 0 de StepType, et 7
            # valeurs sur 8 suffisaient au seuil de 80 %.
            continue
        n = sum(1 for _, nom in paires if nom.replace(".", "_") in ref)
        if n > score:
            meilleur, score = court, n
    if meilleur is None or score < max(4, int(0.8 * len(paires))):
        return None
    ref = refs[meilleur]
    inv = {o: n for n, o in ref.items()}
    div = [(o, nom, inv.get(o)) for o, nom in paires
           if inv.get(o, "").replace(".", "_") != nom.replace(".", "_")]
    return meilleur, div


def step_tables(verbose: bool) -> list:
    cur = current_build()
    refs = {court: _by_name(enum_map(cur, fq)) for court, fq in ENUMS.items()}
    # les tables du build portent `System.Void` etc. : on normalise `.` -> `_` des deux cotes
    refs = {c: {n.replace(".", "_"): o for n, o in r.items()} for c, r in refs.items()}
    fails, vues = [], []

    def _scan_texte(rel: str, src: str):
        for tete in _TAB_HEAD.finditer(src):
            nom_tab, ouvrant = tete.group("nom"), tete.group("open")
            corps = _bloc(src, tete.start("open"), ouvrant)
            if ouvrant == "{":
                paires = [(int(a), b) for a, b in _TAB_DICT.findall(corps)]
            elif _TAB_SEQ_NOM.search(nom_tab):
                paires = list(enumerate(_TAB_STR.findall(corps)))
            else:
                continue
            r = _classe_table(paires, refs)
            if r is None:
                continue
            enum, div = r
            ligne = src[:tete.start()].count("\n") + 1
            vues.append((rel, ligne, nom_tab, enum, len(paires), len(div)))
            for o, nom, attendu in div:
                fails.append((rel, ligne, nom_tab, enum, o, nom, attendu))

    for suf in _SUFFIXES:
        textes = _sources(suf)
        for p in _fichiers_du_depot(suf):
            rel = _ignore(p)
            if rel is None or rel in ALLOWLIST or rel.startswith(INFO_PREFIXES):
                continue
            src_txt = textes.get(p)
            if src_txt is None:
                continue
            _scan_texte(rel, src_txt)

    print("[283] etape 3 : tables de noms indexees par ordinal -- %d table(s), %d entree(s) "
          "divergente(s)" % (len(vues), len(fails)))
    for rel, ligne, nom_tab, enum, n, nd in vues:
        print("   %-58s:%-5d %-24s %s : %d entrees, %d divergentes"
              % (rel, ligne, nom_tab, enum, n, nd))
    montre = fails if verbose else fails[:12]
    for rel, ligne, nom_tab, enum, o, nom, attendu in montre:
        print("   FAIL %s:%d  %s[%d] = %r ; le build %s dit %r"
              % (rel, ligne, nom_tab, o, nom, cur, attendu))
    if len(fails) > len(montre):
        print("   ... (+%d ; -v pour tout)" % (len(fails) - len(montre)))
    return fails


# ------------------------------------------------------------------------------------------
# Etape 4 -- inventaire de la PROSE (token-aware)
# ------------------------------------------------------------------------------------------

_NUM = r"(?:0x[0-9a-fA-F]+|\d{1,3})"


def _ambigus(build: str) -> set:
    """Noms de membre qui appartiennent a PLUSIEURS enums du build avec des ordinaux
    differents. Un tel nom ne peut pas, seul, designer l'un de nos quatre : le signaler
    produirait du faux positif de masse (`Attack`, `Spawn`, `Damage`, `Info`, `Push`...)."""
    par_nom = {}
    for fq, membres in all_enums(build).items():
        for o, n in membres.items():
            par_nom.setdefault(n, set()).add(o)
    return {n for n, ords_ in par_nom.items() if len(ords_) > 1}


def _compile_prose(membres: dict, amb: set) -> tuple:
    """Deux regex par enum et par regime d'ambiguite -- PAS une par membre.

    La version naive (2 regex compilees pour chacun des ~230 membres, sur chaque token de
    chaque fichier) ne terminait pas en 120 s. L'alternance triee par longueur decroissante
    garantit que `TurnStart_EffectActivation` l'emporte sur un eventuel prefixe."""
    def alt(noms):
        return "|".join(re.escape(n) for n in sorted(noms, key=len, reverse=True))

    def paire(noms):
        if not noms:
            return None, None
        a = alt(noms)
        # Forme AVANT (`0x1c=ArrivedAtFinalTile`) : separateur SANS parenthese fermante --
        # sinon `UnitMovement(6) = Tile(7)` apparie `Tile` au 6 de son VOISIN (mesure).
        return (re.compile(r"\b(%s)\b[\s=:(\[]{0,4}(%s)\b" % (a, _NUM)),
                re.compile(r"\b(%s)\b[\s=:]{0,4}(%s)\b" % (_NUM, a)))

    surs = [m for m in membres if m not in amb]
    return {"surs": paire(surs), "tous": paire(list(membres))}


def _compile_larges(membres: dict, anciens: dict, amb: set) -> "tuple | None":
    """(rx_apres, rx_avant, rx_triple, attendu, ambigus) -- UNE regex par sens, pas une par
    membre.

    Separateur LARGE (tout non-mot, jusqu'a 8) + forme TRIPLE du depot
    `On(<Membre> = <hex> = <dec>)`. Un separateur large SEUL produit du faux positif de masse
    (`On(X = Membre, 1)` apparie `Membre` au `1` du 2e argument -- 36 faux positifs mesures) :
    ce qui rend la passe sure, c'est que le NOMBRE doit valoir EXACTEMENT l'ordinal ARCHIVE
    du membre apparie. Un tel nombre n'a aucune autre explication qu'une citation perimee.
    Ce dernier appariement est verifie APRES coup (`attendu`), pas par la regex : sans quoi il
    faudrait une regex par membre.

    PERF -- c'est ce qui rend l'etape payable dans un cliquet. Trois restrictions, chacune
    mesuree :
    * seuls les membres dont l'ordinal a CHANGE entrent dans l'alternation (les autres ne
      peuvent produire aucune paire prouvee) ;
    * le nombre est une alternation de LITTERAUX (les ordinaux archives), pas `\\d{1,3}` ;
    * la direction MEMBRE-d'abord est ECARTEE, et ce n'est pas une perte de couverture : les
      13 citations trouvees par #420 sont TOUTES en forme nombre-d'abord (`` `...,0x37`
      UnitDefeated ``, `` `0x2f` UnitResurrected ``, `On(0x35 = UnitFled`) ou TRIPLE
      (`On(UnitRevived = 45 = 0x2e)`) -- la forme membre-d'abord serree est deja couverte par
      l'etape 4. Elle coute cher parce que les membres d'`UtilityType` sont des mots COURANTS
      (`Damage`, `Attack`, `Heal`) : l'alternation mordait des milliers de fois par fichier.
    Deux formes mesurees et ECARTEES : l'alternation generique membres x `_NUM` (etape prose
    46 s -> >300 s) et la boucle par membre avec pre-filtre `membre in txt` (171 tests de
    sous-chaine par token, >120 s)."""
    # `anciens[m]` porte l'ENSEMBLE des ordinaux archives du membre (#10023) : un membre peut
    # avoir ete renumerote plusieurs fois, et chacune de ses valeurs passees est un candidat de
    # citation perimee. `_ords` accepte aussi la forme a un seul ordinal.
    couples = [(m, o_arch) for m, o in membres.items()
               for o_arch in sorted(_ords(anciens.get(m))) if o_arch != o]
    if not couples:
        return None
    a = "|".join(re.escape(m) for m in sorted({m for m, _ in couples}, key=len, reverse=True))
    n = "|".join(sorted({x for _, o in couples for x in ("0x%x" % o, "%d" % o)},
                        key=len, reverse=True))
    attendu = {}
    for m, o in couples:
        attendu.setdefault(m, set()).add(o)
    # La VIRGULE et le SLASH sont exclus du separateur : ils SEPARENT une liste, ils ne LIENT
    # pas. Deux mesures, meme forme : `"SummonDislikeDoorOpening 30, HeroLikeDoorOpening 31"`
    # et `(SummonDislikeDoorOpening 30 / HeroLikeDoorOpening 31)` appariaient `30` a
    # `HeroLikeDoorOpening` (dont 30 est l'ordinal archive) alors que `30` etiquette l'element
    # PRECEDENT et que les deux lignes sont JUSTES. Aucune des 13 citations vraies de #420 ne
    # porte de virgule ni de slash entre le nombre et le membre.
    return (re.compile(r"\b(%s)\b[^\w\n,/]{0,8}(%s)\b" % (n, a)),
            re.compile(r"\b(%s)\b\s*=\s*%s\s*=\s*(%s)\b" % (a, _NUM, n)),
            attendu, {m for m, _ in couples if m in amb})


def _paires_prose(txt: str, rx: dict, enum_nomme: bool) -> list:
    """(membre, texte du nombre, span du NOMBRE dans `txt`). Deux formes seulement :
       `<Membre>` <sep court> `<nombre>`   et   `<nombre>` <sep court> `<Membre>`.
    Les membres AMBIGUS (presents dans plusieurs enums a des ordinaux differents) ne comptent
    que si la prose NOMME l'enum -- sans quoi `Attack`, `Spawn`, `Damage`, `Push`... noieraient
    le rapport."""
    apres, avant = rx["tous" if enum_nomme else "surs"]
    out = []
    if apres is None:
        return out
    for g in apres.finditer(txt):
        out.append((g.group(1), g.group(2), g.span(2)))
    for g in avant.finditer(txt):
        out.append((g.group(2), g.group(1), g.span(1)))
    return out


def _offsets(src: str) -> list:
    """Offset absolu du 1er caractere de chaque ligne (1-indexee)."""
    out, o = [0, 0], 0
    for ligne in src.splitlines(keepends=True):
        o += len(ligne)
        out.append(o)
    return out


def _zones_prose(src: str, suffixe: str) -> "list | None":
    """Les zones du fichier ou une citation d'ordinal est INERTE, sous forme
    [(offset absolu, texte)]. None = fichier illisible.

    * `.py`  -> tokenize : COMMENT et STRING, jamais un NUMBER ni un NAME. C'est LE
      token-awareness, et il est ce qui separe `# UtilityType.CapturePoint` (inerte) de
      `TILE_LEAVES[24]` (executable) ;
    * `.md`  -> le fichier ENTIER est de la prose ;
    * autres (`.ts`, `.js`) -> le fichier entier est INVENTORIE, mais jamais reecrit : un
      littéral y peut etre executable (c'est le cas d'`UTILITY_TYPE_NAMES`), et separer code
      et commentaires en TS demanderait un vrai parseur."""
    if suffixe != ".py":
        return [(0, src)]
    try:
        toks = list(tokenize.generate_tokens(io.StringIO(src).readline))
    except (tokenize.TokenError, IndentationError, SyntaxError):
        return None
    debut = _offsets(src)
    return [(debut[tk.start[0]] + tk.start[1], tk.string)
            for tk in toks if tk.type in (T.COMMENT, T.STRING)]


def _ligne_de(src: str, off: int) -> int:
    return src.count("\n", 0, off) + 1


_ON_AVANT = re.compile(r"\bOn\(\s*$")


def _historique(src: str, ligne: int, rayon: int = 3) -> bool:
    """Un rappel HISTORIQUE volontaire : le build ARCHIVE est nomme a portee de la citation
    (« cette table portait `55: UnitDefeated`, juste sur `gqfc5mff6c` »). La corriger
    detruirait justement ce qu'elle documente -- seule exemption admise au gate 4bis.

    La portee est en LIGNES, pas en tokens : un bloc de commentaire `#` est decoupe en un
    token PAR LIGNE, donc un test au token rate le cas mesure (le nom du build est sur la
    ligne SUIVANTE)."""
    if not _ARCHIVES:
        return False
    lignes = src.split("\n")
    a, b = max(0, ligne - 1 - rayon), min(len(lignes), ligne + rayon)
    fenetre = "\n".join(lignes[a:b])
    return any(x in fenetre for x in _ARCHIVES)


def _paires_larges(txt: str, larges: "tuple | None", enum_nomme: bool,
                   est_event: bool = True) -> list:
    """(membre, texte du nombre, offset) des citations PROUVEES perimees d'un token.

    Le post-filtre `attendu[m] == v` est ce qui rend le separateur large exploitable : une paire
    <membre, nombre> qui ne s'apparie pas est un croisement fortuit de l'alternation."""
    if larges is None:
        return []
    avant, triple, attendu, ambigus = larges
    out = []
    for rx, gm, gn in ((avant, 2, 1), (triple, 1, 2)):
        for g in rx.finditer(txt):
            m, num = g.group(gm), g.group(gn)
            if m in ambigus and not enum_nomme:
                continue
            # Un nombre precede de `On(` est TYPE par le contrat natif `IdunBattleLogic.Entities.DSLTriggers$$On(
            # EventTriggerType, ...)` : il ne peut pas etre l'ordinal d'un AUTRE enum. Sans ce
            # gate, `` `On(0x12)` -> ActivateEffect `` rougissait comme `StepType.ActivateEffect`
            # (dont 0x12 est l'ordinal archive) alors que 0x12 est un EventTriggerType JUSTE --
            # 3 faux positifs mesures, tous sur la meme forme.
            if not est_event and _ON_AVANT.search(txt, 0, g.start(gn)):
                continue
            v = int(num, 16) if num.lower().startswith("0x") else int(num)
            if v in attendu.get(m, ()):
                out.append((m, num, g.start(gn)))
    return out


def _scan_prose_fichier(src: str, refs: dict, olds: dict, rxs: dict,
                        suffixe: str = ".py", larges_rx: "dict | None" = None) -> tuple:
    """(citations, nb justes). Une citation =
    (ligne, enum, membre, texte du nombre, ordinal courant, origine, offset debut, offset fin).
    `origine` vaut `ancien` quand le nombre cite est EXACTEMENT l'ordinal du membre sur le
    build precedent -- c'est la PREUVE qu'il s'agit d'une citation d'ordinal perimee, et non
    d'un homonyme. Seules celles-la sont reecrivables sans lecture humaine."""
    zones = _zones_prose(src, suffixe)
    if zones is None:
        return [], 0, []
    cites, justes, larges = [], 0, []
    for base, txt in zones:
        for court, ref in refs.items():
            nomme = court in txt
            for m, num, (a, b) in _paires_prose(txt, rxs[court], nomme):
                v = int(num, 16) if num.lower().startswith("0x") else int(num)
                if ref[m] == v:
                    justes += 1
                    continue
                anc = _ords(olds.get(court, {}).get(m))
                # Ligne REELLE de la citation, calculee depuis l'offset ABSOLU : la ligne
                # d'OUVERTURE du token pointe la 1re ligne du module pour toute docstring, ce
                # qui rendait 10 sites illisibles dans le rapport.
                cites.append((_ligne_de(src, base + a), court, m, num, ref[m],
                              "ancien" if v in anc else "inconnu", base + a, base + b))
            if not larges_rx:
                continue
            for m, num, a in _paires_larges(txt, larges_rx.get(court), nomme,
                                            court == "EventTriggerType"):
                v = int(num, 16) if num.lower().startswith("0x") else int(num)
                ln = _ligne_de(src, base + a)
                if ref[m] == v or _historique(src, ln):
                    continue                  # juste, ou rappel historique volontaire
                larges.append((ln, court, m, num, ref[m]))
    return cites, justes, larges


def step_prose(verbose: bool, racine: str = "scripts/python", fix: bool = False) -> tuple:
    cur = current_build()
    amb = _ambigus(cur)
    refs = {c: _by_name(enum_map(cur, fq)) for c, fq in ENUMS.items()}
    olds = memoire_archivee_par_enum()      # TOUTES les archives, pas la derniere (#10023)
    rxs = {c: _compile_prose(r, amb) for c, r in refs.items()}
    larges_rx = {c: _compile_larges(r, olds.get(c, {}), amb) for c, r in refs.items()}

    # `.ts`/`.js` sont INVENTORIES mais jamais reecrits (un littéral y peut etre executable) ;
    # `.md` est integralement de la prose.
    FIXABLES = (".py", ".md")
    fichiers = sorted(q for suf in (".py", ".md", ".ts", ".js")
                      for q in (REPO / racine).rglob("*" + suf))
    derive, justes, corriges, prouves = [], 0, 0, []
    # Lecture PARALLELE (#457-r6), en mode BRUT. `newline=""` DANS LES DEUX SENS : sans lui, la
    # lecture texte traduit CRLF -> LF et la reecriture reposerait tout le fichier en LF. Le
    # depot est en `autocrlf` (les fichiers sont CRLF sur disque) : le diff porterait alors sur
    # TOUTES les lignes, ce qui noierait la correction et la rendrait irrelisable. Decoder les
    # octets SANS traduction reproduit exactement `newline=""`.
    a_lire = [p for p in fichiers if _ignore(p) is not None and _ignore(p) not in ALLOWLIST]
    for p, data in zip(a_lire, repo_read.read_bytes_many(a_lire)):
        rel = _ignore(p)
        if data is None:
            continue
        try:
            src = data.decode("utf-8")
        except UnicodeDecodeError:
            continue
        cites, n_ok, larges = _scan_prose_fichier(src, refs, olds, rxs, p.suffix, larges_rx)
        justes += n_ok
        for c in cites:
            derive.append((rel,) + c)
        for lg in larges:
            prouves.append((rel,) + lg)
        if not fix or p.suffix not in FIXABLES:
            continue
        # Reecriture : SEULEMENT les `ancien`, en ordre decroissant d'offset (les positions
        # des precedentes restent valides). La base est conservee (hex -> hex, dec -> dec) :
        # une citation de decompile s'ecrit en hex, et la relire dans Ghidra doit rester direct.
        rempl = sorted([c for c in cites if c[5] == "ancien"], key=lambda c: -c[6])
        if not rempl:
            continue
        for _ligne, _court, _m, num, attendu, _o, a, b in rempl:
            neuf = ("0x%x" % attendu) if num.lower().startswith("0x") else str(attendu)
            src = src[:a] + neuf + src[b:]
            corriges += 1
        io.open(p, "w", encoding="utf-8", newline="").write(src)

    anc = sum(1 for d in derive if d[6] == "ancien")
    print("[283] etape 4 : PROSE (commentaires/docstrings de %s) -- %d citation(s) derivee(s) "
          "(%d = ancien ordinal, %d a lire), %d justes"
          % (racine, len(derive), anc, len(derive) - anc, justes))
    if fix:
        print("       --fix : %d citation(s) reecrite(s) (les `ancien` seulement)" % corriges)
    par_fichier = {}
    for rel, ln, court, m, num, attendu, orig, _a, _b in derive:
        par_fichier.setdefault(rel, []).append((ln, court, m, num, attendu, orig))
    for rel in sorted(par_fichier):
        items = sorted(par_fichier[rel])
        print("   %-62s %d" % (rel, len(items)))
        for ln, court, m, num, attendu, orig in (items if verbose else items[:3]):
            print("        :%d  %s.%s cite %s ; vaut %d (%s)"
                  % (ln, court, m, num, attendu, orig))
        if not verbose and len(items) > 3:
            print("        ... (+%d)" % (len(items) - 3))

    # --- etape 4bis : le GATE -----------------------------------------------------------
    # Meme scan, separateur LARGE, mais critere PROUVE : le nombre vaut EXACTEMENT l'ordinal
    # du membre sur le build ARCHIVE. C'est ce qui manquait -- #420 a trouve 12 citations de
    # cette forme (`` `...,0x37` UnitDefeated ``, `On(UnitRevived = 45 = 0x2e)`) que le
    # separateur etroit de l'etape 4 ne voyait PAS, et qui donc ne rougissaient nulle part.
    vus = sorted({p for p in prouves})
    print("[283] etape 4bis : citations NOMMEES a separateur large et PROUVEES perimees "
          "(nombre == un ordinal ARCHIVE : %s) -- %d"
          % (", ".join(builds_avec_table_enums()) or "-", len(vus)))
    for rel, ln, court, m, num, attendu in vus:
        print("   FAIL %s:%d  %s.%s cite %s ; le build %s dit %d" % (rel, ln, court, m, num,
                                                                     cur, attendu))
    return derive, justes, vus


# ------------------------------------------------------------------------------------------
# Etape 5 -- le residu INDECIDABLE : `On(<n>)` sans son membre
# ------------------------------------------------------------------------------------------

_ON_NU = re.compile(r"\bOn\(\s*(0x[0-9a-fA-F]+|\d{1,3})\s*[,)&]")
_ON_NOMME = re.compile(r"\bOn\(\s*(?:0x[0-9a-fA-F]+|\d{1,3})\s*=\s*[A-Za-z_]")
# 2e ancre, ajoutee par #420 : la QUOTE VERBATIM du helper de publication DSL, recopiee du
# decompile. Son DERNIER littéral d'argument est un `EventTriggerType`, exactement comme le
# 1er argument d'`On(...)` -- mais aucune des cinq etapes ne la voyait : ni ancre `On(`, ni
# membre accole. Mesure #420 : 18 de ces quotes portaient un ordinal PERIME, en silence.
# Le nom `FUN_<addr>` change a chaque build et n'est donc PAS dans le motif ; ce qui rend
# l'ancre sure, c'est la TETE de la liste d'arguments. Elle a TROIS formes, et les deux
# dernieres sont les residus #420-r2 et #420-r3 :
#
#   `0x4d`  publish simple            -> `(0x4d, <static>, <events>, <eventType>)`
#   `0x50`  publish avec entities     -> `(0x50, .., <eventType>, <entities>)`
#   `0x51`  publish avec `&args`      -> `(0x51, .., <eventType>, &args)`   (#420-r2)
#   `..`    slot ELIDE par NOUS       -> `FUN_<addr>(.., <eventType>)`      (#420-r3)
#
# L'extraction est la MEME pour les quatre : le DERNIER littéral ENTIER de la liste. Le
# residu #420-r2 la decrivait comme un obstacle (<< le littéral y est l'AVANT-dernier
# argument >>), et c'est vrai de la POSITION -- mais `&args`, comme `entities`, n'est PAS un
# littéral, donc l'avant-dernier argument EST le dernier littéral. Rien a changer sauf le slot.
#
# LE SLOT `0x51` EST LU AU DECOMPILE, pas deduit (2026-08-07, build `rnca9r7q6c`). Il porte un
# AUTRE helper que les deux premiers -- 8 arguments au lieu de 4/5 :
#   `IdunBattle.Operations.FinishUnitTurnOperation$$Execute` : TROIS publications
#       `FUN_1800284a0(0x51, <static>, <events>, unit, unit, unit, 0x1c, &args)` puis `0x28`
#       (sous `UnitFlagsComponent$$Add(3)`) puis `0x29` (sous `isTerminated == 0`) ;
#   `IdunBattle.Operations.ResurrectUnitOperation$$Execute` : `.., 0x2e, &args`.
# `0x4d`/`0x50` sont, eux, `FUN_1800280e0` (cf. `ActiveAbilityOperation$$ExecuteInternal` :
# `0x2a` -> `0xb` -> `0xc` -> `0xe`, par adresse croissante). Le motif ne nomme donc AUCUN
# helper -- ni `FUN_1800280e0`, ni `FUN_1800284a0` : ces noms changent a chaque build, et
# c'est le SLOT qui reste.
#
# CE QUE CETTE EXTENSION RATTRAPE, MESURE : `0x51` a **0 site** dans `scripts/python`
# aujourd'hui -- l'ancre y est PREVENTIVE, pour la citation qu'on ecrira. Le seul `0x51` du
# depot est un dispatch d'interface (`FUN_180003bd0(0x51, itf, service, caster)`,
# `BattleQuery$$GetFreeAdjacentTiles`), et il n'a AUCUN littéral dans ses arguments, donc rien
# n'y est ancre. L'elision, elle, a **2** sites (`probe_120:231`, `sworn_protector.py:110`).
# ⚠ Un slot n'est un identifiant que DANS une interface : `0x51` d'`IBattleQuery` n'a aucun
# rapport avec `0x51` du dispatcher d'evenements. C'est pourquoi l'ancre seule n'est JAMAIS un
# gate -- elle COMPTE. Le gate exige une ANNOTATION posee a la main (cf. `_ON_MEMBRE_NU`).
# `…` = l'ellipse UNICODE, ecrite en echappement : le depot en porte (`FUN_...(0x50, …,
# 0x3d)`), et un caractere non-ASCII dans un motif est ce qu'on relit le plus mal.
_FUN_PUB = re.compile(
    r"\bFUN_[0-9a-fA-F]{6,}\s*\(\s*(?:0x(?:4d|50|51)|\.{2,3}|\u2026)\s*,([^)\n]*)\)")
_FUN_LIT = re.compile(r"^(0x[0-9a-fA-F]+|\d{1,3})$")

# ANNOTATION de decidabilite (#420-r5). Une quote verbatim ne peut pas porter son membre :
# l'ecrire DEDANS falsifierait la citation. Le membre se pose donc A COTE, sur la MEME LIGNE,
# sous la forme `On(<Membre>)` -- membre NU, sans nombre, ce qui la distingue de la forme
# nommee `On(<n> = <Membre>)` que l'etape 4 confronte deja.
#
# POURQUOI PAS LE SEPARATEUR, qui etait la piste ecrite en #420 §9. Mesure du 2026-08-07 sur
# les deux quotes qui portaient DEJA un commentaire de fin de ligne : `anvil_shield.py:39`
# ecrit `...0x3c)      # UnitBlocked` (8 caracteres de separateur -- la limite EXACTE de
# 4bis) et `martial_superiority.py:61` ecrit `...0x2a);` puis **21 espaces** d'alignement
# avant `# On(PreUnitAbility)`. Un critere de PROXIMITE TEXTUELLE ne peut pas tenir contre le
# padding d'un bloc de decompile recopie ; le critere est donc la LIGNE, comme `_historique`
# (meme lecon, meme fichier : << la portee est en LIGNES, pas en tokens >>).
#
# POURQUOI PAS LE VOISINAGE HEURISTIQUE non plus, mesure et ECARTE. Chercher dans +/-3 lignes
# un membre dont l'ordinal vaut la valeur de l'ancre rendait 11/18 quotes decidables -- mais
# applique aux ancres `On(` du meme balayage il produisait **3 << perimees prouvees >>, 3
# FAUX** : `On(0x29)` apparie a l'`UnitFinishedTurn` qui etiquette le `0x28` de la ligne
# PRECEDENTE (`probe_462..._haywire_pose.py:124`), et deux `On(0x36)` apparies au
# `PostUnitKill` qui etiquette le `0x35` voisin (`movement.py:14` et `:385`). C'est le faux
# positif de VOISINAGE que 4bis avait deja paye sur la virgule et le slash. Un gate ne se
# fonde donc pas sur ce qu'un texte porte PRES, mais sur ce qu'un auteur a DECLARE.
_ON_MEMBRE_NU = re.compile(r"\bOn\(\s*([A-Za-z_][A-Za-z0-9_]*)\s*\)")


def annotation_de_ligne(ligne: str, v: int, ref: dict, old: dict,
                        n_ancres: int = 1, quoi: str = "FUN") -> tuple:
    """(etat, membre) pour une ancre de valeur `v` posee sur `ligne`.

    Etats, dans l'ordre ou ils sont cherches -- le premier qui s'applique gagne, et c'est ce
    qui rend le critere MONOTONE (jamais un rouge quand un vert est disponible) :

      `ancree`   un `On(<Membre>)` de la ligne a pour ordinal COURANT exactement `v` ;
      `perimee`  aucun ne l'a, mais l'un a pour ordinal ARCHIVE exactement `v` -- meme critere
                 PROUVE que le gate 4bis : le nombre cite est l'ordinal d'AVANT du membre que
                 l'auteur a nomme, ce qui n'a aucune autre explication qu'une citation
                 recopiee d'un build perime ;
      `ambigue`  la ligne porte PLUSIEURS ancres nues pour UNE annotation (cf. `n_ancres`) ;
      `nue`      la ligne ne porte aucun `On(<Membre>)` qui soit un membre d'EventTriggerType.

    Un membre annote qui n'est NI courant NI archive pour cette valeur est ignore (il ne dit
    rien de `v`) : on ne rougit pas sur une annotation qu'on ne comprend pas.

    ⚠ `n_ancres` -- LES DEUX ETATS N'ONT PAS LA MEME FORCE, ET C'EST CE QUI TRANCHE (#1031).
    `ancree` est CONFIRME par la valeur (`ref[m] == v` : le membre nomme vaut CE nombre
    aujourd'hui) ; il reste donc sur meme si la ligne porte dix ancres. `perimee`, lui, est une
    INFERENCE -- << aucun membre nomme ne vaut `v` aujourd'hui, mais l'un le valait avant, DONC
    la citation est recopiee >>. Cette inference suppose que l'annotation se rapporte a CETTE
    ancre-la. Des que la ligne porte plus d'ancres nues que d'annotations, c'est faux.

    Mesure (le rouge de `master`) -- `test_981_vecteurs_de_fuite_offline.py:136` ecrit :

        `On(PreUnitFled)` passe la fuyarde TROIS FOIS (...) ; `On(0x34)` et `On(0x36)` passent ...

    UNE annotation, DEUX ancres nues -- et la phrase les OPPOSE. `0x34` est `UnitFled` et `0x36`
    est `UnitDefeated` (le meme fichier les FIGE quatre lignes plus haut) ; ni l'un ni l'autre
    n'est `PreUnitFled`. Le gate accusait donc le depot d'une peremption que le depot n'a pas
    ecrite. Le probe le disait pourtant lui-meme deux paragraphes plus haut : << un gate ne se
    fonde pas sur ce qu'un texte porte PRES, mais sur ce qu'un auteur a DECLARE >> -- une
    annotation pour deux ancres ne DECLARE rien sur laquelle des deux.

    L'etat rendu est `ambigue` et NON `nue` : ce qui est ecarte doit etre COMPTE et IMPRIME,
    sinon c'est une exemption muette -- exactement ce que ce probe existe pour interdire.

    ⚠ `quoi` -- L'ANNOTATION N'ANNOTE QUE LES QUOTES, ET C'EST LA RAISON MEME DE SA CREATION.
    #420-r5 l'a introduite pour un manque PRECIS : << une quote verbatim ne peut pas porter son
    membre DEDANS sans cesser d'etre verbatim ; le membre se pose donc A COTE >>. Une ancre
    `On(<n>)`, elle, n'a pas ce manque -- sa voie declarative propre est la forme NOMMEE
    `On(<n> = <Membre>)`, que l'etape 4 confronte, et c'est celle que #420 a posee sur 220 sites.
    Etendre l'annotation aux ancres `On(<n>)` revient donc a apparier DEUX MENTIONS d'un meme
    motif dans une phrase -- du VOISINAGE, que ce probe s'interdit explicitement deux
    paragraphes plus haut.

    MESURE DU 2026-08-13, ET ELLE TOMBE DES DEUX COTES. Le depot ne portait que DEUX ancres
    `On(<n>)` appariees a un `On(<Membre>)` de la meme ligne, toutes deux en prose NARRATIVE :

      `martial_apotheosis.py:34`  << Vecteur porte = ... (`On(TurnStart_Actions)`). `On(0x16)`
                                     verifie : ... >>            -> `ancree`, JUSTE par accident
      `test_981_vecteurs_de_fuite_offline.py:136`
                                  << `On(PreUnitFled)` passe la fuyarde TROIS FOIS ; `On(0x34)`
                                     et `On(0x36)` passent ... >> -> `perimee`, FAUX par accident

    Ni l'une ni l'autre n'est une annotation : ce sont deux SUJETS de phrase. Un mecanisme dont
    la moitie des verdicts est un accident ne garde rien -- il tire a pile ou face, et c'est le
    rouge de `master`. Les 23 autres ancrees sont toutes des quotes `FUN_`, ou l'annotation est
    bien ce que l'auteur a pose POUR elles."""
    membres = ([m for m in _ON_MEMBRE_NU.findall(ligne) if m in ref or m in old]
               if quoi == "FUN" else [])
    for m in membres:
        if ref.get(m) == v:
            return "ancree", m
    for m in membres:
        if v in _ords(old.get(m)) and ref.get(m) != v:
            return ("perimee", m) if n_ancres <= 1 else ("ambigue", m)
    return "nue", None


def step_on(verbose: bool, racine: str = "scripts/python") -> tuple:
    """`On(<n>)` NU en prose : l'ancre est sure, le verdict ne l'est PAS -- SAUF si l'auteur a
    pose l'annotation `On(<Membre>)` sur la ligne, et c'est alors un GATE (#420-r5).

    L'ancre `On(` est le contrat natif `IdunBattleLogic.Entities.DSLTriggers$$On(EventTriggerType,
    ...)` : le nombre EST un `EventTriggerType`, sans ambiguite d'homonyme. Mais rien ne dit de
    QUEL build il vient, et c'est ce qui interdit la correction automatique :

      * `probe_281_pre_unit_ability_shortcut.py` ecrit `On(0x2a)` -- JUSTE, ecrit apres la MAJ ;
      * `engine/runner/abilities/handler.py` ecrit `On(0x2b)` -- FAUX, recopie d'avant.

    Les deux sont des ordinaux « dont le proprietaire a change » : le critere qui tranche
    l'etape 4 (le NOM accole donne l'attendu) n'existe pas ici. Le `git blame` ne tranche pas non
    plus -- MESURE : sur les 7 sites ecrits APRES la migration, 6 recopiaient l'ancienne valeur.

    CE QUI A CHANGE (#420-r5). Une citation `On(<n>)` se REECRIT en `On(<n> = <Membre>)` et
    sort alors de cette etape pour entrer dans l'etape 4 : c'est ce que #420 a fait pour 220
    sites. Une QUOTE VERBATIM, elle, ne le peut pas -- ecrire le membre dedans falsifierait la
    citation, et c'est exactement ce qui laissait 16 quotes INDECIDABLES. Le membre se pose
    donc A COTE, `On(<Membre>)` sur la meme ligne, et la quote devient confrontable :

      * annotation coherente avec le build courant -> `ANCREE`, elle sort des ambigus ;
      * annotation dont l'ordinal ARCHIVE vaut le nombre cite -> `FAIL`, citation PROUVEE
        perimee (c'est le cran qui mordra au PROCHAIN changement de build, sans qu'une seule
        ligne du depot ait bouge -- le gisement exact de #283).

    Le GATE ne mord donc QUE la ou quelqu'un a DECLARE le membre. Une ancre nue reste un
    compteur, et une ancre mal ancree ne peut pas fabriquer de faux rouge : c'est ce qui
    autorise l'ancre elargie (`0x51`, slot elide) sans risquer un rouge structurel.

    MEMOISE (#941-r2). DEUX tests de `test_enum_ordinal_ratchet_offline.py` appellent cette
    fonction avec les MEMES arguments et lisent chacun une position DIFFERENTE du meme tuple
    (`decales` pour les quotes indecidables, `fails` pour les ancres perimees) : deux verdicts,
    un seul balayage. Mesure du 2026-08-11, fichier joue seul : 34,7 s + 30,5 s. Le memo porte
    sur le BALAYAGE seul -- l'impression, qui depend de `verbose`, reste rejouee a chaque appel,
    et le retour est RE-CONSTRUIT pour qu'un appelant ne puisse pas muter ce que verra le
    suivant (meme regle que `probe_514.etape_1`)."""
    res = _ON_CACHE.get(racine)
    if res is None:
        res = _balayer_step_on(racine)
        _ON_CACHE[racine] = res
    cur = current_build()
    archives = ", ".join(builds_avec_table_enums()) or "-"
    stables = res[0]
    decales, ancrees, fails, ambigues = [list(x) for x in res[1:]]
    n_on = sum(1 for d in decales if d[5] == "On")
    n_anc_fun = sum(1 for a in ancrees if a[4] == "FUN")
    print("[283] etape 5 : ordinaux NUS en prose de %s (ancres `On(` et quote de publication) "
          "-- %d stables, %d ANCRES par annotation (%d quote `FUN_`), %d AMBIGUS "
          "(%d `On(`, %d quote `FUN_`), %d NON ATTRIBUABLES"
          % (racine, stables, len(ancrees), n_anc_fun, len(decales), n_on,
             len(decales) - n_on, len(ambigues)))
    print("       ambigu = l'ordinal a change de proprietaire ; sans le NOM accole, on ne peut")
    print("       pas savoir de quel build vient la citation. NON corrige (residu #283-r1).")
    print("       ancre  = la ligne porte `On(<Membre>)` et le membre vaut CE nombre sur le")
    print("       build courant -- une citation decidable, donc gardee (residu #420-r5 ferme).")
    par_fichier = {}
    for rel, ln, s, a, b, quoi in decales:
        par_fichier.setdefault(rel, []).append((ln, s, a, b, quoi))
    for rel in sorted(par_fichier):
        items = sorted(par_fichier[rel])
        print("   %-62s %d" % (rel, len(items)))
        for ln, s, a, b, quoi in (items if verbose else items[:2]):
            print("        :%d  %s(%s) : etait %s, vaut %s"
                  % (ln, "On" if quoi == "On" else "FUN_...", s, a, b))
        if not verbose and len(items) > 2:
            print("        ... (+%d)" % (len(items) - 2))
    if verbose:
        for rel, ln, s, membre, quoi in sorted(ancrees):
            print("   ANCREE %s:%d  %s(%s) = On(%s)"
                  % (rel, ln, "On" if quoi == "On" else "FUN_...", s, membre))
    for rel, ln, s, membre, anc, courant, quoi in sorted(fails):
        print("   FAIL %s:%d  %s(%s) annote `On(%s)` -- %s valait %s sur les archives (%s) et "
              "vaut %s sur %s"
              % (rel, ln, "On" if quoi == "On" else "FUN_...", s, membre, membre, anc,
                 archives, courant, cur))
    #: COMPTE ET IMPRIME, jamais muet : une annotation qui ne peut pas etre attribuee est un
    #: ECART, pas un vert. Si ce compte enfle, c'est que le depot ecrit des lignes ou plusieurs
    #: evenements se disputent une seule annotation -- il faut alors les separer, pas relacher.
    for rel, ln, s, membre, n, quoi in sorted(ambigues):
        print("   AMBIGU %s:%d  %s(%s) : la ligne porte %d ancres pour l'annotation `On(%s)` "
              "-- non attribuable, l'ancre reste un COMPTEUR"
              % (rel, ln, "On" if quoi == "On" else "FUN_...", s, n, membre))
    return stables, decales, ancrees, fails, ambigues


#: Le releve de l'etape 5, par racine balayee. Des TUPLES : ce qui est retenu est immuable, et
#: `step_on` en rend une copie -- un memo qui partagerait ses listes laisserait un test muter le
#: releve du suivant (le vice que `test_486r5_balayages_memoises_offline.py` etage 2 garde).
_ON_CACHE: dict = {}


def _balayer_step_on(racine: str) -> tuple:
    """Le BALAYAGE de l'etape 5, sans une seule impression. Foyer unique, appele par `step_on`.

    Rend `(stables, decales, ancrees, fails, ambigues)`, les quatre derniers en TUPLE."""
    cur = current_build()
    new = enum_map(cur, ENUMS["EventTriggerType"])
    ref_n = _by_name(new)
    #: MEMOIRE de TOUTES les archives, pas seulement `previous_build()` (#10023) : une quote du
    #: depot cite l'ordinal du build ou elle a ete ecrite, qui n'avance pas avec l'archivage.
    old_n = memoire_archivee(ENUMS["EventTriggerType"])
    #: {ordinal: {noms qu'il a portes sur les archives}} -- `None` compris quand un build archive
    #: ne portait PAS cet ordinal (c'est ce qui distinguait deja un ordinal NEUF d'un stable).
    proprios: dict = {}
    for b in builds_avec_table_enums():
        table = enum_map(b, ENUMS["EventTriggerType"])
        for v in set(table) | set(new):
            proprios.setdefault(v, set()).add(table.get(v))
    stables, decales, ancrees, fails, ambigues = 0, [], [], [], []
    for suf in (".py", ".md"):
        # Lecture PARALLELE (#457-r6), mode BRUT (`newline=""`) comme l'etape 4.
        a_lire = [p for p in sorted((REPO / racine).rglob("*" + suf))
                  if _ignore(p) is not None and _ignore(p) not in ALLOWLIST]
        for p, data in zip(a_lire, repo_read.read_bytes_many(a_lire)):
            rel = _ignore(p)
            if data is None:
                continue
            try:
                src = data.decode("utf-8")
            except UnicodeDecodeError:
                continue
            zones = _zones_prose(src, suf)
            if zones is None:
                continue
            lignes = src.split("\n")
            #: ⚠ LE COMPTE DES ANCRES SE FAIT SUR TOUT LE FICHIER, PAS PAR ZONE (#1031). Une
            #: meme ligne peut etre couverte par plusieurs zones de prose (docstring + un `#`
            #: de fin de ligne) ; compter par zone sous-estimerait la pluralite et rendrait
            #: le gate a l'inference qu'on vient de lui retirer.
            releve = []
            for base, txt in zones:
                ancres = [(g.start(1), g.group(1), "On")
                          for g in _ON_NU.finditer(txt)
                          if not _ON_NOMME.match(txt, g.start())]
                for g in _FUN_PUB.finditer(txt):
                    args, off = g.group(1), g.start(1)
                    pos, dernier = 0, None
                    for brut in args.split(","):
                        s = brut.strip()
                        if _FUN_LIT.match(s):
                            dernier = (off + pos + brut.index(s), s)
                        pos += len(brut) + 1
                    if dernier is not None:
                        ancres.append((dernier[0], dernier[1], "FUN"))
                for pos, s, quoi in ancres:
                    # La LIGNE du fichier, pas le token : une quote vit dans une docstring
                    # (un seul token pour des dizaines de lignes) et son annotation est sur
                    # SA ligne. Meme raison que `_historique`.
                    releve.append((_ligne_de(src, base + pos), s, quoi))
            par_ligne: dict = {}
            for ln, _s, _quoi in releve:
                par_ligne[ln] = par_ligne.get(ln, 0) + 1
            for ln, s, quoi in releve:
                v = int(s, 16) if s.lower().startswith("0x") else int(s)
                etat, membre = annotation_de_ligne(
                    lignes[ln - 1] if 0 < ln <= len(lignes) else "", v, ref_n, old_n,
                    par_ligne[ln], quoi)
                if etat == "perimee":
                    fails.append((rel, ln, s, membre,
                                  ",".join(str(x) for x in sorted(_ords(old_n.get(membre)))),
                                  ref_n.get(membre), quoi))
                elif etat == "ancree":
                    ancrees.append((rel, ln, s, membre, quoi))
                elif etat == "ambigue":
                    ambigues.append((rel, ln, s, membre, par_ligne[ln], quoi))
                elif proprios.get(v, {new.get(v)}) == {new.get(v)}:
                    stables += 1   # AUCUNE archive ne donne un autre proprietaire a cet ordinal
                else:
                    decales.append((rel, ln, s,
                                    "/".join(sorted(str(x) for x in proprios.get(v, ()))),
                                    new.get(v), quoi))
    return stables, tuple(decales), tuple(ancrees), tuple(fails), tuple(ambigues)


# ------------------------------------------------------------------------------------------
# Etape 6 -- confrontation LIVE : la table versionnee colle-t-elle au binaire CHARGE ?
# ------------------------------------------------------------------------------------------

# (asm, namespace, classe) de chaque enum, pour le RPC `dumpEnum` d'`introspect.ts`.
_LIVE = {
    "EventTriggerType":  ("BattleLogicAssembly.dll", "IdunBattle.DSL", "EventTriggerType"),
    "UtilityType":       ("BattleLogicAssembly.dll", "IdunBattle.Configuration", "UtilityType"),
    "StepType":          ("BattleLogicAssembly.dll", "IdunBattle.Streams", "StepType"),
    "DisplaceDirection": ("BattleLogicAssembly.dll", "IdunBattle.Operations",
                          "DisplaceDirection"),
}


def step_live(verbose: bool) -> int:
    """Seconde source INDEPENDANTE : `dumpEnum` lit la metadata du binaire CHARGE, la ou tout
    le reste du probe lit `enums.tsv`. Si les deux s'accordent, la table versionnee n'est pas
    seulement coherente avec elle-meme -- elle decrit le jeu qui tourne.

    Ne (re)injecte RIEN : `introspect.ts` est deja dans le bundle, on l'appelle. Exige une
    session vivante et WARMEE.

    ⚠ `values` est un DICT `{nom: "valeur"}`, pas une liste. Le parser naif (iteration comme
    sur une liste de dicts) rend `live=0` pour les quatre enums, et un `0 divergent` qui se lit
    « OK » -- mesure faite ici meme. Un compte de zero est verifie, jamais interprete."""
    sys.path.insert(0, str(PYDIR))
    import rl_collect_batch as R                      # noqa: E402  (import lourd, a la demande)
    sid = R._resolve_session()
    cur = current_build()
    print("[283] etape 6 : confrontation LIVE (dumpEnum, binaire charge) vs enums.tsv de %s"
          % cur)
    ko = 0
    for court, (asm, ns, cls) in _LIVE.items():
        r = R._rpc(sid, "dumpEnum", [{"asm": asm, "ns": ns, "cls": cls}], timeout=60)
        res = r.get("result") if isinstance(r, dict) and "result" in r else r
        vals = (res or {}).get("values")
        if not isinstance(vals, dict) or not vals:
            print("   FAIL %-18s le RPC n'a rien rendu : %s" % (court, str(res)[:120]))
            ko += 1
            continue
        live = {n: int(v) for n, v in vals.items()}
        tsv = _by_name(enum_map(cur, ENUMS[court]))
        div = sorted(n for n in set(tsv) & set(live) if tsv[n] != live[n])
        manque = sorted(set(tsv) - set(live))
        extra = sorted(set(live) - set(tsv))
        print("   %-18s live=%-4d tsv=%-4d  DIVERGENTS=%-3d absents-du-live=%-3d "
              "absents-du-tsv=%d" % (court, len(live), len(tsv), len(div), len(manque),
                                     len(extra)))
        for n in div[:6] + manque[:3] + extra[:3]:
            print("        %-42s live=%s tsv=%s" % (n, live.get(n), tsv.get(n)))
        ko += len(div) + len(manque) + len(extra)
    print("[283] etape 6 : %s" % ("les 4 tables collent au binaire CHARGE"
                                  if ko == 0 else "DIVERGENCE (%d)" % ko))
    return ko


# ------------------------------------------------------------------------------------------

def main(argv) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--step", default="all",
                    choices=("all", "diff", "mirror", "exec", "tables", "prose", "on", "live"))
    ap.add_argument("--racine", default="scripts/python",
                    help="perimetre de l'etape prose (defaut scripts/python)")
    ap.add_argument("--fix", action="store_true",
                    help="etape prose : reecrit les citations dont le nombre vaut EXACTEMENT "
                         "l'ordinal du build precedent (les seules prouvees perimees)")
    ap.add_argument("-v", "--verbose", action="store_true")
    ap.add_argument("--verifier-cache", action="store_true",
                    help="RECALCULE tout en ignorant les caches versionnes des etapes `mirror` "
                         "et `exec`, et les confronte entree par entree (#486-r1) -- le seul "
                         "controle qui voie une entree falsifiee de facon coherente")
    args = ap.parse_args(argv)

    global _ESPION
    _ESPION = args.verifier_cache

    #: L'ORDRE EST DIT, pas suppose (#10023-r2) : chaque archive sort avec l'horodatage qui la
    #: classe, et un `?` la ou il n'y en a pas. Un libelle qui n'affiche qu'une liste laisse
    #: croire qu'elle est chronologique -- c'est precisement ce que ce residu reprochait.
    _arch = archived_builds()
    print("[283] build courant : %s ; archives (ordre CHRONOLOGIQUE par estampille) : %s"
          % (current_build(),
             ", ".join("%s(%s)" % (b, build_generated(b) or "? NON DATE") for b in _arch) or "-"))
    _sd = [b for b in builds_sans_date() if b in set(_arch)]
    if _sd:
        print("      %d archive(s) NON DATABLE(s), placee(s) en fin par convention de tri et "
              "jamais elue(s) comme << la plus recente >> : %s" % (len(_sd), ", ".join(_sd)))
    ko = 0
    if args.step in ("all", "diff"):
        step_diff(args.verbose)
    if args.step in ("all", "mirror"):
        ko += len(step_mirror(args.verbose))
    if args.step in ("all", "exec"):
        ko += len(step_exec(args.verbose))
    if args.step in ("all", "tables"):
        ko += len(step_tables(args.verbose))
    if args.step in ("all", "prose"):
        # etape 4 = COMPTEUR ; etape 4bis (3e valeur) = GATE, car le critere y est PROUVE.
        ko += len(step_prose(args.verbose, args.racine, args.fix)[2])
    if args.step in ("all", "on"):
        # COMPTEUR sur les ancres NUES (rien ne dit de quel build vient le nombre) ; GATE sur
        # les seules ancres ANNOTEES `On(<Membre>)` -- la ou l'auteur a DECLARE le membre,
        # donc la ou l'ordinal cite est confrontable (#420-r5).
        ko += len(step_on(args.verbose, args.racine)[3])
    if args.step == "live":                # hors `all` : exige une session vivante et warmee
        ko += step_live(args.verbose)
    if args.verifier_cache:
        import verdict_cache
        print()
        print("=== VERIFICATION DES CACHES VERSIONNES (#486-r1) ===")
        divergences = []
        for c in (_CACHE_MIRROR, *_CACHE_283.values()):
            if c is None:
                continue
            d = verdict_cache.verifier(c)
            print("  %-24s entrees sur disque : %5d   recalculees : %5d"
                  % (c.nom, len(c._sur_disque), len(c._vues)))
            divergences += ["%s : %s" % (c.nom, x) for x in d]
        for d in divergences:
            print("  DIVERGENCE %s" % d)
        if divergences:
            #: rc DEDIE : ce n'est pas le verdict du cliquet sur le depot, c'est le CACHE qui
            #: ment. Les confondre ferait corriger le code a la place de l'artefact.
            print("  rc=3 -- un cache versionne n'atteste PAS ce que le calcul rend. Le")
            print("  REGENERER : python scripts/python/probe_283_enum_ordinal_sweep.py --step all")
            return 3
        print("  OK -- chaque entree vaut ce que le recalcul integral produit.")

    print("[283] VERDICT: %s" % ("PASS" if ko == 0 else "FAIL (%d)" % ko))
    if ko:
        return 1
    #: CRAN DE FRAICHEUR (#486-r22) -- MESURE du 2026-08-15 : jouer `--step mirror` reecrivait
    #: `probe_283_step_mirror.tsv` (402 lignes ajoutees, 237 retirees) et rendait `rc=0`. Ce
    #: cliquet est dans la banque, donc cette derive se produisait a CHAQUE passe sans que rien ne
    #: la signale -- exactement le regime que #486-r22 disait avoir ferme, sur un cliquet que son
    #: cran ne couvrait pas.
    #:
    #: ⚠ LA GARDE EST ECRITE SUR `args.step`, PAS SUR `_ECRITS`, ET C'EST STRUCTUREL. Seules ces
    #: deux etapes ecrivent un cache, donc `if _ECRITS:` serait juste a l'execution -- mais
    #: OPAQUE a `probe_439_cliquet_peut_rougir`, qui evalue les valeurs d'arguments de CHAQUE
    #: entree de banque pour confirmer qu'un COMPTEUR assume reste incapable de rougir. Mesure :
    #: sans cette condition, `probe_439` passait de PASS a `FAIL (1)` en declarant MORTE la
    #: declaration `Rougit = 'compteur'` de `probe_283:diff` -- une entree qui, elle, n'ecrit
    #: aucun cache. Un cran qui fait rougir un AUTRE cliquet a tort se fait desarmer.
    if args.step in ("all", "mirror", "exec"):
        import verdict_cache
        for c in _ECRITS:
            rc = verdict_cache.rendre_compte_du_cache(c, 0)
            if rc:
                return rc
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
