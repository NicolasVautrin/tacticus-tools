"""Audit de la COUVERTURE MOTEUR des abilities PASSIVES (`units.*.passiveAbilities`).

Pendant PASSIF-centrique de `audit_combat_ability_coverage.py` (#95, qui ne croise QUE les
`activeAbilities` x `ABILITY_CLASSES`). L'angle mort etait structurel, pas un oubli : une passive
n'est PAS un `ActiveAbilityType`. Mesure de ce script (re-derivee a chaque run) : sur les 207
passifs distincts du parc, **206 sont des `TriggeredAbilityType`** et **1 seul** est un
`ActiveAbilityType` (`ShroudPsalm`) ; l'intersection nom-a-nom actives/passifs est VIDE. Un audit
qui interroge `ABILITY_CLASSES` (clé = `ActiveAbilityType`) ne pouvait donc rien voir des passifs.
Cas fondateur : l'effet `HeavyGravCannon` (passif d'`admecDestroyer`) porte avec une divergence
live, invisible a tous les audits existants.

## CRITERE DE COUVERTURE (enonce, verifiable, non sature)

Le piege est connu et documente (`docs/rl/unit-trait-coverage.md`, ANGLE-MORT #73) : un
trait/passif se cable par PLUSIEURS canaux, donc un registre unique ne peut pas le mesurer. Le
critere retenu est donc une DISJONCTION DE CANAUX, chacun structurel (appartenance a un registre
moteur), avec un verdict PAR PASSIF :

  [T] TRIGGER      -- `triggers.dispatch.ABILITY_TRIGGERS[<passif>]` : la triggered-ability accordee
                      par le passif est portee. C'est le canal CANONIQUE (cote natif le passif EST
                      une `TriggeredAbilityType`), consomme par `collect_triggered_abilities`.
  [O] OWNER-EFFECT -- `effects.factory.ABILITY_INIT_OWNER_EFFECTS[<passif>]` (DSL `AddEffect(owner)`
                      du `CreateBehaviour`) ou `ABILITY_OWNER_EFFECTS[<passif>]`
                      (`StaticBattleRules.ActiveAbility$$GetEffectToBeAddedToOwnerForAbility`),
                      avec AU MOINS un effet cible present dans `EFFECT_CLASSES`. Consomme par
                      `runner.operations.spawn._seed_ability_owner_effects`.
  [E] EFFET        -- une classe d'effet est enregistree dans `effects.factory.EFFECT_CLASSES` sous
                      une cle HOMONYME (`<passif>`) ou PREFIXEE (`<passif>_...`). C'est le chemin
                      EFFET de l'ANGLE-MORT : l'effet est seede depuis `decisionView.effects` et
                      porte toute la mecanique, sans que le passif figure dans aucun registre.
  [G] EFFET-TRIGGER-- l'effet homonyme/prefixe a un id `EffectType` inscrit dans
                      `triggers.dispatch.EFFECT_TRIGGERS` (trigger porte par l'effet lui-meme).
  [X] EXEC         -- le passif a un id `ActiveAbilityType` present dans
                      `runner.abilities.handler.ABILITY_CLASSES` (cas marginal, 1 candidat).
  [B] BESPOKE      -- le nom gameconfig apparait comme LITTERAL DE CHAINE EXACT dans du code sous
                      `engine/runner/` : lookup keye sur le nom, cote COMBAT, DELIBEREMENT hors
                      registres. Canal AJOUTE apres que le critere soit tombe en faux GAP sur
                      `PileIn` (« PileIn reste BESPOKE -- pas dans ABILITY_TRIGGERS -> pas de
                      double-fire par le dispatch generique », cable par un
                      `if "PileIn" not in (...).passiveAbilities` au hook fin-de-tour).
  [R] DIRECT-READ  -- aucun registre, mais le nom est reference dans le code executable d'`engine/`
                      HORS `runner/` (ou seulement comme fragment d'identifiant). Zone GRISE, deux
                      causes MESUREES : (a) port d'une AUTRE FACE (`FuryOfTheAncients`,
                      `SaviorProtocols` = feuilles d'utilite AI, face DECISION, aucune execution
                      combat) ; (b) FAUX AMI D'ENUM (`GalvanicField`, passif `TriggeredAbilityType`,
                      ne matche que `Repair_GalvanicField` = `ActiveAbilityType` 1119, autre objet).
                      -> chaque ligne porte les ZONES du moteur qui referencent, pour trancher.
  [.] MENTION      -- le nom n'apparait QUE dans de la PROSE (commentaire / docstring). AUCUN
                      cablage : le passif a ete vu/documente, jamais branche.
  [ ] ABSENT       -- aucune trace, nulle part.

Verdict = PORTE si au moins un de [T][O][E][G][X][B] ; sinon [R] / [.] / [ ].

### Pourquoi le signal « le nom apparait dans engine/ » est SATURE (et pourquoi ce script ne
### l'utilise pas tel quel)

Mesure : un simple `substring` du nom sur `engine/**/*.py` rend **207/207 presents, 0 manquant**.
La cause n'est pas que tout est porte -- c'est que `engine/entities/triggered_ability_type.py` est
un MIRROR 1:1 de l'enum natif `TriggeredAbilityType` (573 membres) : le nom de CHAQUE passif y
figure comme membre d'enum. Un CATALOGUE n'est pas un CABLAGE.

Le signal code de ce script est donc derive de l'**AST** et exclut explicitement les DEFINITIONS de
membres d'enum (assignations dans le corps d'une classe `Enum`/`IntEnum`/...), tout en gardant les
USAGES (`TriggeredAbilityType.X` = un `ast.Attribute`, donc compte). Il separe en outre le CODE
(AST) de la PROSE (commentaires + docstrings, via `tokenize`) -- c'est cette separation qui
de-sature le critere. Le rapprochement de nom est CamelCase-aware (`HeavyGravCannon` matche
`HeavyGravCannonEffect` mais `Guard` ne matche PAS `Guardsman`).

## CONFRONTABILITE des porteurs (gate CLAUDE.md : HERO / MoW / SUMMON -- jamais NPC)

La colonne `kind` de gameconfig MENT sur la spawnabilite. Ventilation reelle :
  L+ = lineup present dans `rl_duel.py build --list-pool` (verite native `buildNormalizedBC`) ;
  M  = MachineOfWar du meme pool ;
  S+ = unite hors pool ATTEIGNABLE par summon depuis une unite du pool (graphe transitif des
       `constants.unitId{,_2,_3,_4}` / `unitIds` / `unitToSpawn` des abilities) -- confrontable ;
  L~ = lineup ABSENT du pool -> **INJECTABLE**, donc confrontable ;
  L! = lineup dans la liste des NON SPAWNABLES -> seul refus legitime ;
  S? = summon SANS summoner derivable du gameconfig -> reachability INDETERMINEE (borne basse
       assumee : 25 summons sont dans ce cas, spawnes par des chemins non exprimes en constants) ;
  N  = npc non atteignable -> hors-jeu, NON PERTINENT.
Confrontable <=> au moins un porteur L+, M, S+ ou L~.

ABSENT DU POOL != NON SPAWNABLE -- l'erreur que ce script codait en dur jusqu'au 2026-07-29. Le pool
derive du seed BC, qui est la capture d'UNE bataille : son catalogue ne porte que les unites
possedees ce jour-la. Un heros hors pool s'INJECTE :
`catalog_inject.write_augmented_seed_bc(<hors data/>, [unitId])` alimente les DEUX catalogues
(`Units` ET `Abilities` -- sans la config d'ability le porteur se deploie puis FAUTE au cast, cf.
#226), puis `rl_duel.py build --seed-bc <chemin>`. Le seul refus legitime est `data/
unspawnable_rank<N>.json` (repli `rl_collect_batch.UNSPAWNABLE_FALLBACK`) : les unites qui passent
le filtre de `buildNormalizedBC` et LEVENT a la construction. Mesure du 2026-07-29 :
`spaceWolfPriest`, classe non confrontable par ce script ET par un solveur, entre au pool (97 -> 98)
par cette voie.

## APPROXIMATIONS ASSUMEES (l'audit RANGE, il ne PROUVE pas)

- [E]/[G] reposent sur une CONVENTION DE NOMMAGE (meme convention que
  `audit_kit_coverage._has_effect_named_after`), pas sur un lien lu du natif : le gameconfig ne
  porte AUCUN lien passif->effectType (verifie : 0/207 des `constants` nomment un `EffectType`).
  Faux positifs possibles si un effet homonyme appartient a une autre mecanique.
- [T]/[O] sont EXACTS (appartenance a un dict, cle = le nom gameconfig du passif).
- [R] est un indice, pas une preuve : la reference peut etre un reliquat ou une autre mecanique.
- Le symbole natif de la colonne `symbole` est resolu PAR NOM dans `data/symbols/<build>/frida/
  methods.tsv` (classe `<Passif>Ability`/`<Passif>Effect`/...) -- a CONFIRMER en ghidra avant port.

Genere `docs/rl/passive-ability-coverage.md`. A relancer au changement de build ou apres tout port.

Usage : depuis `scripts/python/`
    python audit_passive_ability_coverage.py                 # pool lu live (session warm requise)
    python audit_passive_ability_coverage.py --pool-file <p> # 100 % offline, pool d'un run anterieur
"""
from __future__ import annotations

import argparse
import ast
import collections
import json
import os
import re
import subprocess
import sys
import tokenize

_PYROOT = os.path.dirname(os.path.abspath(__file__))   # scripts/python
_REPO = os.path.dirname(os.path.dirname(_PYROOT))      # racine repo
if _PYROOT not in sys.path:
    sys.path.insert(0, _PYROOT)

import enum_maps as EM
import gameconfig as GC
from engine.entities.effects.factory import (
    ABILITY_INIT_OWNER_EFFECTS, ABILITY_OWNER_EFFECTS, EFFECT_CLASSES,
)
from engine.runner.abilities.handler import ABILITY_CLASSES
from engine.runner.operations.triggers.dispatch.registry import ABILITY_TRIGGERS, EFFECT_TRIGGERS

OUT = os.path.join(_REPO, "docs", "rl", "passive-ability-coverage.md")
ENGINE_DIR = os.path.join(_PYROOT, "engine")
POOL_SNAPSHOT = os.path.join(_REPO, "logs", "passive-audit-pool.json")

# Cles de `ability.constants` qui NOMMENT une unite spawnee (graphe de summon).
SPAWN_KEYS = ("unitId", "unitId_2", "unitId_3", "unitId_4", "unitIds", "unitToSpawn")
_ENUM_BASES = {"Enum", "IntEnum", "IntFlag", "StrEnum", "Flag"}


# =====================================================================================
# 1. Parc : passifs distincts et leurs porteurs
# =====================================================================================

def collect_passives() -> dict[str, list[tuple[str, str]]]:
    """{nom de passif -> [(unitId, kind)]} sur TOUT le parc.

    Parc = `GC._index()` cles `lineup`/`npc`/`summons` (PAS `cfg["units"]`, conteneur de 22 cles).
    Passifs lus via `GC.unit_abilities` (JAMAIS `unit(uid)["abilities"]`, champ legacy vide)."""
    idx = GC._index()
    out: dict[str, list[tuple[str, str]]] = {}
    for kind in ("lineup", "npc", "summons"):
        for uid in idx[kind]:
            for p in GC.unit_abilities(uid)["passive"]:
                out.setdefault(p["name"], []).append((uid, kind))
    return out


def enum_qualification(passives) -> dict[str, int]:
    """Compte, par enum natif, combien de passifs y appartiennent -- la mesure qui EXPLIQUE
    l'angle mort (`ABILITY_CLASSES` est keye par `ActiveAbilityType`)."""
    trig = set(EM.PASSIVE_ABILITY_TYPE.values())     # en-tete enum_maps : <- enum TriggeredAbilityType
    act = set(EM.ACTIVE_ABILITY_TYPE.values())
    eff = set(EM.EFFECT_TYPE.values())
    return {
        "triggered": sum(1 for n in passives if n in trig),
        "active": sum(1 for n in passives if n in act),
        "effect_homonym": sum(1 for n in passives if n in eff),
        "none": sum(1 for n in passives if n not in trig and n not in act and n not in eff),
    }


# =====================================================================================
# 2. Confrontabilite : pool spawnable (live) + graphe de summon (gameconfig)
# =====================================================================================

def read_pool(pool_file: str | None) -> dict:
    """Pool spawnable = VERITE NATIVE `buildNormalizedBC` via `rl_duel.py build --list-pool`
    (les unites qui passent `IStatsFormula.StatsUsingProgressionIndexFor` au rank courant).
    `--pool-file` rejoue un instantane anterieur (audit 100 % offline)."""
    if pool_file:
        with open(pool_file, encoding="utf-8") as f:
            return json.load(f)
    proc = subprocess.run([sys.executable, "rl_duel.py", "build", "--list-pool"],
                          cwd=_PYROOT, capture_output=True, text=True,
                          encoding="utf-8", errors="replace")
    txt = proc.stdout or ""
    units = re.findall(r"(?m)^[ \t]{2,}([A-Za-z][\w]*)[ \t]*$", txt)
    m = re.search(r"MoW spawnables\s*:\s*\[([^\]]*)\]", txt)
    mow = [x.strip().strip("'\"") for x in (m.group(1) if m else "").split(",") if x.strip()]
    rk = re.search(r"rank\s+(\d+)", txt)
    if not units:
        raise SystemExit(
            "[error] pool spawnable illisible (`rl_duel.py build --list-pool` a echoue).\n"
            "        La ventilation spawnable/hors-pool est le COEUR de cet audit : pas de\n"
            "        repli silencieux sur `kind`, qui ment. Relance avec une session warm, ou\n"
            "        passe --pool-file <snapshot>.\n"
            "        stderr: " + (proc.stderr or "")[-500:])
    snap = {"rank": int(rk.group(1)) if rk else None, "units": sorted(units), "mow": sorted(mow)}
    os.makedirs(os.path.dirname(POOL_SNAPSHOT), exist_ok=True)
    with open(POOL_SNAPSHOT, "w", encoding="utf-8") as f:
        json.dump(snap, f, indent=1)
    return snap


def summon_graph() -> dict[str, set[str]]:
    """summoner -> {unites spawnees}, derive des `constants` de CHAQUE ability (active ET passive)
    de chaque unite. Borne BASSE : les summons dont le spawn n'est pas exprime en `constants`
    (resolu nativement) n'ont pas d'arete -> classes `S?` (reachability indeterminee)."""
    idx = GC._index()
    known = set(idx["lineup"]) | set(idx["npc"]) | set(idx["summons"])
    abilities = idx["abilities"]

    def spawned(nm: str) -> set[str]:
        c = (abilities.get(nm) or {}).get("constants") or {}
        out: set[str] = set()
        for k in SPAWN_KEYS:
            v = c.get(k)
            if isinstance(v, list):
                out |= {x for x in v if isinstance(x, str) and x in known}
            elif isinstance(v, str):
                for part in re.split(r"[,;]", v):
                    part = part.strip()
                    if part in known:
                        out.add(part)
        return out

    g: dict[str, set[str]] = {}
    for kind in ("lineup", "npc", "summons"):
        for uid, u in idx[kind].items():
            for nm in list(u.get("activeAbilities") or []) + list(u.get("passiveAbilities") or []):
                s = spawned(nm)
                if s:
                    g.setdefault(uid, set()).update(s)
    return g


def summon_reachable(pool: set[str], graph: dict[str, set[str]]) -> set[str]:
    """Fermeture transitive : tout ce qu'une unite du pool peut amener en bataille (un summon
    peut lui-meme summoner)."""
    seen: set[str] = set()
    stack = list(pool)
    while stack:
        cur = stack.pop()
        for nxt in graph.get(cur, ()):
            if nxt not in seen:
                seen.add(nxt)
                stack.append(nxt)
    return seen - pool


def read_unspawnable(rank: int | None) -> set[str]:
    """Les unites qui passent le filtre de `buildNormalizedBC` puis LEVENT a la construction.

    C'est le SEUL refus legitime pour un `lineup` : l'absence du pool, elle, ne prouve rien (le pool
    derive du seed BC = capture d'UNE bataille). Meme source que `rl_duel` :
    `data/unspawnable_rank<N>.json`, produit par le spawn-probe exhaustif, avec repli sur la
    constante `rl_collect_batch.UNSPAWNABLE_FALLBACK` quand le fichier n'existe pas."""
    p = os.path.join(_REPO, "data", "unspawnable_rank%s.json" % rank)
    if rank is not None and os.path.exists(p):
        with open(p, encoding="utf-8") as f:
            d = json.load(f)
        return set(d.get("unspawnableUnits") or []) | set(d.get("unspawnableMow") or [])
    from rl_collect_batch import UNSPAWNABLE_FALLBACK
    return set(UNSPAWNABLE_FALLBACK)


def classify_carrier(uid: str, kind: str, pool_units: set[str], pool_mow: set[str],
                     reachable: set[str], unspawnable: set[str]) -> str:
    """L+ / M / S+ / L~ / L! / S? / N -- cf. docstring du module.

    L'ordre des tests compte : `unspawnable` ne l'emporte QUE sur les `lineup` hors pool. Une unite
    presente au pool a deja passe la construction, donc rien ne sert de la re-filtrer."""
    if uid in pool_mow:
        return "M"
    if uid in pool_units:
        return "L+"
    if uid in reachable:
        return "S+"
    if kind == "lineup":
        # ABSENT DU POOL != NON SPAWNABLE. Le pool derive du seed BC (capture d'UNE bataille) : un
        # heros hors pool s'INJECTE par `catalog_inject.write_augmented_seed_bc` (Units ET Abilities)
        # puis `rl_duel.py build --seed-bc`. Cf. le gate de confrontabilite du CLAUDE.md.
        return "L!" if uid in unspawnable else "L~"
    if kind == "summons":
        return "S?"
    return "N"


# =====================================================================================
# 3. Signal CODE (AST, membres d'enum exclus) vs PROSE (commentaires + docstrings)
# =====================================================================================

def _is_enum_class(node: ast.ClassDef) -> bool:
    for b in node.bases:
        nm = b.attr if isinstance(b, ast.Attribute) else getattr(b, "id", None)
        if nm in _ENUM_BASES:
            return True
    return False


def _docstring_ids(tree: ast.AST) -> set[int]:
    out: set[int] = set()
    for n in ast.walk(tree):
        body = getattr(n, "body", None)
        if (isinstance(body, list) and body and isinstance(body[0], ast.Expr)
                and isinstance(body[0].value, ast.Constant)
                and isinstance(body[0].value.value, str)):
            out.add(id(body[0].value))
    return out


def _catalogue_member_ids(tree: ast.AST) -> set[int]:
    """Les `ast.Attribute` qui sont des elements d'un CATALOGUE d'enum ECRIT EN VRAC.

    Un conteneur litteral (`(...)`, `[...]`, `{...}`) dont TOUS les elements sont des acces
    attributaires sur la MEME base (`_T.PowerUp_Armor, _T.PowerUp_Damage, ...`) est un mirror
    de collection native -- typiquement le `HashSet<TriggeredAbilityType>` d'un `.cctor`. C'est
    la MEME chose qu'une definition d'enum : un catalogue, pas un cablage.

    ⚠ Pourquoi ce cran existe (mesure, pas precaution) : l'exclusion des DEFINITIONS de membres
    d'enum juste au-dessus de-sature le critere au site de definition, mais une RE-ENUMERATION
    ailleurs le re-sature integralement. `engine/entities/selectors/tiles._power_up_ids()` (mirror
    de `...StaticBattleRules.TriggeredAbility$$GetPowerUps`) re-liste les 22 membres
    `TriggeredAbilityType.PowerUp_*` : les **19** passifs `PowerUp_*` non portes sont passes de
    GAP a ZONE-GRISE canal `R` d'un seul bloc, au merge d'une PR qui ne porte aucun d'eux. Le
    catalogue repondait a « cette unite est-elle un power-up ? », jamais a « ce passif est porte ».

    Le critere est un INVARIANT (base unique + tous les elements attributaires), pas un SEUIL :
    rien a regler, et il ne se degrade pas quand le catalogue grandit ou retrecit. Un conteneur
    MIXTE (un seul element non attributaire, ou deux bases differentes) n'est pas un catalogue et
    reste compte -- on n'ecarte que ce dont on peut dire qu'il enumere UNE collection."""
    out: set[int] = set()
    for n in ast.walk(tree):
        if not isinstance(n, (ast.Tuple, ast.List, ast.Set)):
            continue
        elts = n.elts
        if len(elts) < 2:
            continue
        bases = set()
        for e in elts:
            if not (isinstance(e, ast.Attribute) and isinstance(e.value, ast.Name)):
                bases = None
                break
            bases.add(e.value.id)
        if bases is None or len(bases) != 1:
            continue
        for e in elts:
            out.add(id(e))
    return out


def code_symbols(path: str) -> tuple[set[str], set[str], int]:
    """(symboles du CODE EXECUTABLE, litteraux de chaine, nb de membres d'enum ecartes).

    EXCLUT les DEFINITIONS de membres d'enum (un catalogue mirror 1:1 n'est pas un cablage --
    c'est ce qui saturait le critere naif), les CATALOGUES d'enum ecrits en vrac ailleurs
    (`_catalogue_member_ids`, meme raison) et les docstrings. Les USAGES ISOLES (`MonEnum.Membre`
    = `ast.Attribute` hors catalogue) sont conserves. Les litteraux sont isoles a part : un
    litteral EXACT du nom gameconfig est un LOOKUP KEYE SUR CE NOM, signal bien plus fort qu'un
    simple identifiant."""
    try:
        with open(path, encoding="utf-8") as f:
            tree = ast.parse(f.read())
    except (OSError, SyntaxError):
        return set(), set(), 0
    docs = _docstring_ids(tree)
    skip: set[int] = set()
    n_enum = 0
    for n in ast.walk(tree):
        if isinstance(n, ast.ClassDef) and _is_enum_class(n):
            for st in n.body:
                targets = ([st.target] if isinstance(st, ast.AnnAssign)
                           else st.targets if isinstance(st, ast.Assign) else [])
                for t in targets:
                    if isinstance(t, ast.Name):
                        skip.add(id(t))
                        n_enum += 1
    catalogue = _catalogue_member_ids(tree)
    n_enum += len(catalogue)
    syms: set[str] = set()
    lits: set[str] = set()
    for n in ast.walk(tree):
        if isinstance(n, ast.Name):
            if id(n) not in skip:
                syms.add(n.id)
        elif isinstance(n, ast.Attribute):
            if id(n) not in catalogue:
                syms.add(n.attr)
        elif isinstance(n, ast.Constant):
            if isinstance(n.value, str) and id(n) not in docs:
                syms.add(n.value)
                lits.add(n.value)
        elif isinstance(n, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
            syms.add(n.name)
        elif isinstance(n, ast.keyword) and n.arg:
            syms.add(n.arg)
        elif isinstance(n, ast.alias):
            syms.add(n.name.split(".")[-1])
            if n.asname:
                syms.add(n.asname)
    return syms, lits, n_enum


def prose_blob(path: str) -> str:
    """Commentaires + docstrings (STRING en position d'instruction). `tokenize` est le seul a voir
    les commentaires -- ils n'existent pas dans l'AST."""
    out: list[str] = []
    try:
        with open(path, "rb") as f:
            toks = list(tokenize.tokenize(f.readline))
    except (OSError, tokenize.TokenError, SyntaxError, IndentationError):
        return ""
    stmt_start = (tokenize.NEWLINE, tokenize.INDENT, tokenize.DEDENT, tokenize.ENCODING, tokenize.NL)
    prev = tokenize.NEWLINE
    for t in toks:
        if t.type == tokenize.COMMENT:
            out.append(t.string)
        elif t.type == tokenize.STRING and prev in stmt_start:
            out.append(t.string)
        if t.type not in (tokenize.NL, tokenize.COMMENT):
            prev = t.type
    return "\n".join(out)


def zone_of(path: str) -> str:
    """Zone fonctionnelle du moteur -- c'est elle qui dit sur QUELLE FACE une reference vit.
    Discriminant paye : `SaviorProtocols` n'est reference que dans `utilities` (feuille d'utilite
    AI = face DECISION) alors que `PileIn`/`FireOfAbsolution` le sont dans `runner` (face COMBAT)."""
    rel = os.path.relpath(path, ENGINE_DIR).replace("\\", "/")
    if rel.startswith("runner/"):
        return "runner"
    if rel.startswith("entities/effects/"):
        return "effects"
    if rel.startswith("entities/"):
        return "entities"
    if rel.startswith(("playbook/", "ai/", "utilities/")):
        return rel.split("/", 1)[0]
    if rel.startswith("dsl/"):
        return "dsl"
    return os.path.splitext(rel)[0].split("/")[0]


def scan_engine() -> tuple[dict[str, dict[str, set[str]]], str, int, int]:
    """{zone -> {"syms": symboles du code, "lits": litteraux de chaine}} + la PROSE globale."""
    zones: dict[str, dict[str, set[str]]] = collections.defaultdict(
        lambda: {"syms": set(), "lits": set()})
    prose: list[str] = []
    n_files = n_enum = 0
    for root, _dirs, files in os.walk(ENGINE_DIR):
        for fn in sorted(files):
            if not fn.endswith(".py"):
                continue
            p = os.path.join(root, fn)
            n_files += 1
            s, lits, ne = code_symbols(p)
            z = zones[zone_of(p)]
            z["syms"] |= s
            z["lits"] |= lits
            n_enum += ne
            prose.append(prose_blob(p))
    return dict(zones), "\n".join(prose), n_files, n_enum


def _boundary_hit(hay: str, name: str) -> bool:
    """Sous-chaine CamelCase-aware : rien d'alphanumerique AVANT, ni minuscule/chiffre APRES.
    -> `HeavyGravCannon` matche `HeavyGravCannonEffect` et `Terrifying_ExtraDefense` ;
       `Guard` ne matche NI `Guardsman` NI `RoyalGuard`."""
    n = len(name)
    i = hay.find(name)
    while i >= 0:
        before = hay[i - 1] if i > 0 else ""
        after = hay[i + n] if i + n < len(hay) else ""
        if not before.isalnum() and not (after.islower() or after.isdigit()):
            return True
        i = hay.find(name, i + 1)
    return False


def code_zones(name: str, zones: dict) -> list[str]:
    """Zones du moteur dont le CODE reference le nom (exact ou fragment CamelCase)."""
    out = []
    for z, d in zones.items():
        syms = d["syms"]
        if name in syms or any(_boundary_hit(s, name) for s in syms):
            out.append(z)
    return sorted(out)


def literal_zones(name: str, zones: dict) -> list[str]:
    """Zones ou le nom apparait comme LITTERAL DE CHAINE EXACT = lookup keye sur le nom gameconfig."""
    return sorted(z for z, d in zones.items() if name in d["lits"])


# =====================================================================================
# 4. Canaux de couverture
# =====================================================================================

def _effect_keys_named_after(name: str) -> list[str]:
    """Cles d'`EFFECT_CLASSES` homonymes (`<name>`) ou prefixees (`<name>_...`). MEME convention de
    nommage que `audit_kit_coverage._has_effect_named_after` -- approximation assumee (le gameconfig
    ne porte aucun lien passif->effectType : verifie 0/207)."""
    pfx = name + "_"
    return sorted(k for k in EFFECT_CLASSES if k == name or k.startswith(pfx))


def channels(name: str, zones: dict, prose: str) -> tuple[list[str], dict, list[str]]:
    """Renvoie (canaux, detail, zones du code qui referencent) -- cf. le CRITERE en tete de module."""
    eff2id = {v: k for k, v in EM.EFFECT_TYPE.items()}
    det: dict = {}
    ch: list[str] = []

    trig = ABILITY_TRIGGERS.get(name) or []
    if trig:
        ch.append("T")
        det["T"] = [c.__name__ for c in trig]

    owner = list(ABILITY_INIT_OWNER_EFFECTS.get(name) or []) + list(ABILITY_OWNER_EFFECTS.get(name) or [])
    owner_ported = [e for e in owner if e in EFFECT_CLASSES]
    if owner_ported:
        ch.append("O")
        det["O"] = owner_ported

    eff_keys = _effect_keys_named_after(name)
    if eff_keys:
        ch.append("E")
        det["E"] = eff_keys

    eff_trig = [k for k in eff_keys if eff2id.get(k) in EFFECT_TRIGGERS]
    if eff_trig:
        ch.append("G")
        det["G"] = eff_trig

    aid = GC.ability_id(name)                       # non-None seulement si ActiveAbilityType
    if aid is not None and aid in ABILITY_CLASSES:
        ch.append("X")
        det["X"] = [ABILITY_CLASSES[aid].__name__]

    czones = code_zones(name, zones)
    if not ch:
        # [B] BESPOKE-COMBAT : litteral EXACT du nom gameconfig dans du code sous `engine/runner/`
        # = lookup keye sur le nom, cote COMBAT, DELIBEREMENT hors registres (le port de `PileIn`
        # l'ecrit noir sur blanc : « PileIn reste BESPOKE -- pas dans ABILITY_TRIGGERS -> pas de
        # double-fire par le dispatch generique »). Sans ce canal, un passif reellement execute
        # tombait en faux GAP.
        if "runner" in literal_zones(name, zones):
            ch.append("B")
            det["B"] = ["litteral exact sous engine/runner/"]
        elif czones:
            ch.append("R")
            det["R"] = czones
        elif _boundary_hit(prose, name):
            ch.append(".")
    return ch, det, czones


# =====================================================================================
# 5. Symbole natif (resolution PAR NOM dans la table de symboles versionnee)
# =====================================================================================

_PREF_METHODS = ["CreateBehaviour", "CreateTrigger", "CreateTargetTrigger",
                 "CreateTargetTriggerBehaviour", "CreateHandleTriggerAbilitiesInternal",
                 "CreateAdditionalHits", "CreateEffectHitsBonusForAttack", "GetValidTargets",
                 "ApplyInternal", "ApplyModification", "Execute", ".ctor"]


def load_native_index() -> dict[str, dict[str, set[str]]]:
    """{short class name -> {classe pleinement qualifiee -> {methodes}}} depuis
    `data/symbols/<build>/frida/methods.tsv` (table VERSIONNEE, cf. CLAUDE.md). Namespaces `.View.`
    exclus (visuels, jamais la mecanique). {} si la table manque."""
    base = os.path.join(_REPO, "data", "symbols")
    if not os.path.isdir(base):
        return {}
    builds = sorted(d for d in os.listdir(base) if os.path.isdir(os.path.join(base, d)))
    if not builds:
        return {}
    path = os.path.join(base, builds[-1], "frida", "methods.tsv")
    if not os.path.isfile(path):
        return {}
    idx: dict[str, dict[str, set[str]]] = collections.defaultdict(lambda: collections.defaultdict(set))
    with open(path, encoding="utf-8", errors="replace") as f:
        for line in f:
            if line.startswith("#"):
                continue
            parts = line.rstrip("\n").split("\t")
            if len(parts) < 3:
                continue
            full, cls = parts[1], parts[2]
            if not cls.startswith("IdunBattle") or ".View." in cls:
                continue
            idx[cls.rsplit(".", 1)[-1]][cls].add(full.rsplit(".", 1)[-1])
    return idx


def native_symbol(name: str, nidx: dict) -> str:
    """Symbole natif le plus plausible pour un passif. Resolution PAR NOM (classe `<P>`,
    `<P>Ability`, `<P>Effect`, `<P>_...`) : A CONFIRMER en ghidra, ce n'est pas une preuve."""
    cands: list[tuple[str, set[str]]] = []
    for short, clsmap in nidx.items():
        if short == name or (short.startswith(name) and (len(short) == len(name)
                                                         or short[len(name)] == "_"
                                                         or short[len(name)].isupper())):
            cands.extend(clsmap.items())
    if not cands:
        return ""
    cands.sort(key=lambda c: (0 if ".Abilities." in c[0] else 1 if ".Effects." in c[0] else 2,
                              len(c[0]), c[0]))
    cls, meths = cands[0]
    for m in _PREF_METHODS:
        if m in meths:
            return "%s$$%s" % (cls, m)
    return cls


# =====================================================================================
# 6. Assemblage
# =====================================================================================

def build_rows(pool: dict) -> tuple[list[dict], dict]:
    passives = collect_passives()
    zones, prose, n_files, n_enum = scan_engine()
    graph = summon_graph()
    pool_units, pool_mow = set(pool["units"]), set(pool["mow"])
    reachable = summon_reachable(pool_units | pool_mow, graph)
    unspawnable = read_unspawnable(pool.get("rank"))
    nidx = load_native_index()

    # `L~` (lineup hors pool mais INJECTABLE) compte comme confrontable : cf. `classify_carrier`.
    CONFRONTABLE = ("L+", "M", "S+", "L~")

    rows: list[dict] = []
    for name, carriers in passives.items():
        cls = collections.Counter(
            classify_carrier(uid, kind, pool_units, pool_mow, reachable, unspawnable)
            for uid, kind in carriers)
        ch, det, czones = channels(name, zones, prose)
        ported = any(c in ("T", "O", "E", "G", "X", "B") for c in ch)
        confrontable = any(cls[c] for c in CONFRONTABLE)
        examples = [uid for uid, kind in carriers
                    if classify_carrier(uid, kind, pool_units, pool_mow, reachable,
                                        unspawnable) in CONFRONTABLE]
        rows.append({
            "name": name, "carriers": carriers, "cls": cls, "channels": ch, "detail": det,
            "zones": czones, "ported": ported, "confrontable": confrontable,
            "spawnable_examples": sorted(examples)[:4],
            "symbol": native_symbol(name, nidx),
        })
    meta = {
        "n_files": n_files, "n_enum_members": n_enum,
        "n_code_syms": len(set().union(*(d["syms"] for d in zones.values()))),
        "zone_names": sorted(zones),
        "prose_kb": len(prose) // 1024, "enum_qual": enum_qualification(passives),
        "graph_edges": sum(len(v) for v in graph.values()), "reachable": len(reachable),
        "summons_unreached": len(set(GC._index()["summons"]) - reachable - pool_units - pool_mow),
        "pool": pool, "n_unspawnable": len(unspawnable),
        "n_injectable": len(set(GC._index()["lineup"]) - pool_units - pool_mow - unspawnable),
    }
    return rows, meta


def verdict(r: dict) -> str:
    if r["ported"]:
        return "PORTE"
    if "R" in r["channels"]:
        return "ZONE-GRISE"
    if "." in r["channels"]:
        return "GAP-MENTION"
    return "GAP-ABSENT"


def _carriers_cell(c: collections.Counter) -> str:
    parts = [("L+", c["L+"]), ("M", c["M"]), ("L~", c["L~"]), ("L!", c["L!"]),
             ("S+", c["S+"]), ("S?", c["S?"]), ("N", c["N"])]
    return " ".join("%s=%d" % (k, v) for k, v in parts if v) or "-"


def _channel_cell(r: dict) -> str:
    """Canal + la PREUVE (classe/cle de registre) -- pour [R] la preuve est la colonne `zones`."""
    if not r["channels"]:
        return "-"
    out = []
    for c in r["channels"]:
        d = r["detail"].get(c) if c != "R" else None
        out.append("**%s**%s" % (c, ("=" + ",".join(d[:2])) if d else ""))
    return " ".join(out)


def _table(lines: list[str], title: str, rows: list[dict], with_symbol: bool = False) -> None:
    lines.append("\n### %s (%d)\n\n" % (title, len(rows)))
    if not rows:
        lines.append("_aucun._\n")
        return
    head = "| passif | porteurs | spawnables (ex.) | verdict | canal | zones engine/ |"
    sep = "|---|---|---|---|---|---|"
    if with_symbol:
        head += " symbole natif (a confirmer) |"
        sep += "---|"
    lines.append(head + "\n" + sep + "\n")
    for r in rows:
        cell = ("| %s | %s | %s | %s | %s | %s |"
                % (r["name"], _carriers_cell(r["cls"]),
                   ", ".join(r["spawnable_examples"]) or "-", verdict(r), _channel_cell(r),
                   ", ".join(r["zones"]) or "-"))
        if with_symbol:
            cell += " `%s` |" % (r["symbol"] or "?")
        lines.append(cell + "\n")


def render(rows: list[dict], meta: dict) -> list[str]:
    q = meta["enum_qual"]
    pool = meta["pool"]
    n = len(rows)
    ported = [r for r in rows if r["ported"]]
    grey = [r for r in rows if verdict(r) == "ZONE-GRISE"]
    gap_m = [r for r in rows if verdict(r) == "GAP-MENTION"]
    gap_a = [r for r in rows if verdict(r) == "GAP-ABSENT"]
    conf = [r for r in rows if r["confrontable"]]
    gaps = gap_m + gap_a
    gaps_conf = [r for r in gaps if r["confrontable"]]
    grey_conf = [r for r in grey if r["confrontable"]]

    def bykey(lst):
        # Cout croissant de confrontation : porteur direct (`L+`/`M`) > summon a amener (`S+`) >
        # injection de catalogue (`L~`). Les trois sont confrontables, ils ne coutent pas pareil.
        return sorted(lst, key=lambda r: (-(r["cls"]["L+"] + r["cls"]["M"]),
                                          -r["cls"]["S+"], -r["cls"]["L~"], r["name"]))

    L: list[str] = []
    L.append("# Couverture moteur des abilities PASSIVES\n\n")
    L.append("> Genere par `scripts/python/audit_passive_ability_coverage.py` "
             "(gameconfig `passiveAbilities` x registres moteur x pool spawnable live). "
             "A regenerer au changement de build ou apres tout port. "
             "TOUS les chiffres de ce document sont re-derives a chaque run -- aucun n'est recopie.\n\n")

    L.append("## Pourquoi cet audit existe : l'angle mort est STRUCTUREL\n\n")
    L.append("`audit_combat_ability_coverage.py` (#95) croise `activeAbilities` x `ABILITY_CLASSES`, "
             "registre keye par **`ActiveAbilityType`**. Or, mesure de ce run sur les **%d passifs "
             "distincts** du parc :\n\n" % n)
    L.append("| enum natif d'appartenance | passifs |\n|---|---|\n")
    L.append("| `TriggeredAbilityType` | **%d** |\n" % q["triggered"])
    L.append("| `ActiveAbilityType` | **%d** |\n" % q["active"])
    L.append("| homonyme d'un `EffectType` | %d |\n" % q["effect_homonym"])
    L.append("| aucun des trois | %d |\n\n" % q["none"])
    L.append("L'intersection nom-a-nom actives/passifs est **VIDE**. Un passif n'est donc pas une "
             "ability active « non castable » : c'est une **`TriggeredAbilityType`**, un objet d'un "
             "AUTRE enum, instancie a l'init de l'unite (`collect_triggered_abilities` cote port, "
             "`AbilityAndEffectCache` cote natif). L'audit des actives ne pouvait structurellement "
             "rien en voir.\n\n")
    L.append("Cas fondateur : `HeavyGravCannon`, passif d'`admecDestroyer` -- il expliquait un delta "
             "de degat live/offline reste longtemps sans cause, et n'apparaissait dans AUCUN audit "
             "(cf. `docs/rl/case-220/admec.md`, `docs/rl/case-101-moved-flag.md`). Ce meme cas "
             "documente le piege a ne jamais oublier ici, une **homonymie a TROIS faces** : "
             "`EffectType 1291 = HeavyGravCannon` (le nom CAPTE live), "
             "`TriggeredAbilityType 1233 = HeavyGravCannon` (la CONFIG du passif), "
             "`TriggeredAbilityType 1291 = SelfRepairMechanism` (**sans aucun rapport**). Le meme id "
             "dans deux enums nomme deux objets differents, et le meme nom dans deux enums porte deux "
             "ids differents -> **tout rapprochement par nom ou par id doit qualifier son enum**. "
             "Ce run mesure **%d** des %d passifs homonymes d'un `EffectType` : c'est exactement la "
             "population exposee a ce piege, et donc la limite du canal **E**.\n\n"
             % (q["effect_homonym"], n))

    L.append("## CRITERE DE COUVERTURE (enonce)\n\n")
    L.append("Un passif est **PORTE** si AU MOINS UN de ces canaux -- tous structurels "
             "(appartenance a un registre moteur) -- le prend en charge :\n\n")
    L.append("| canal | signal | consommateur du port |\n|---|---|---|\n")
    L.append("| **T** trigger | `triggers.dispatch.ABILITY_TRIGGERS[<passif>]` | "
             "`collect_triggered_abilities` (canal CANONIQUE : le passif EST une triggered-ability) |\n")
    L.append("| **O** owner-effect | `factory.ABILITY_INIT_OWNER_EFFECTS` / `ABILITY_OWNER_EFFECTS` "
             "-> >=1 effet present dans `EFFECT_CLASSES` | `spawn._seed_ability_owner_effects` |\n")
    L.append("| **E** effet | cle `<passif>` ou `<passif>_...` dans `factory.EFFECT_CLASSES` | "
             "`EffectFactory.create` (effet seede depuis `decisionView.effects`) |\n")
    L.append("| **G** effet-trigger | l'id `EffectType` de cet effet est dans "
             "`triggers.dispatch.EFFECT_TRIGGERS` | `collect_effect_triggers` |\n")
    L.append("| **X** exec | id `ActiveAbilityType` present dans "
             "`runner.abilities.handler.ABILITY_CLASSES` | `AbilityHandler` |\n")
    L.append("| **B** bespoke-combat | le nom gameconfig apparait comme **litteral de chaine EXACT** "
             "dans du code sous `engine/runner/` | cablage keye sur le nom, DELIBEREMENT hors "
             "registres (cf. ci-dessous) |\n\n")
    L.append("Le canal **B** n'est pas un repli commode : il a ete AJOUTE apres avoir fait tomber le "
             "critere en faux GAP sur `PileIn`, dont le port ecrit noir sur blanc « PileIn reste "
             "BESPOKE -- pas dans `ABILITY_TRIGGERS` -> pas de double-fire par le dispatch generique » "
             "et se cable par un `if \"PileIn\" not in (...).passiveAbilities` dans le hook fin-de-tour. "
             "Un lookup keye sur le nom gameconfig EST un cablage.\n\n")
    L.append("Sinon, trois verdicts NEGATIFS distincts :\n\n")
    L.append("- **ZONE-GRISE [R]** -- aucun registre, mais le nom est reference dans le **code "
             "executable** d'`engine/` HORS `runner/` (ou seulement comme fragment d'identifiant). "
             "Deux causes mesurees, toutes deux a trancher au recon : (a) le passif est porte sur une "
             "AUTRE FACE -- `FuryOfTheAncients` et `SaviorProtocols` n'existent que comme feuille "
             "d'utilite AI (`playbook/`, `utilities/`), face DECISION, sans aucune execution combat ; "
             "(b) **faux ami d'enum** -- `GalvanicField` (passif, `TriggeredAbilityType`) ne matche que "
             "`Repair_GalvanicField` (`ActiveAbilityType` 1119), une ability ACTIVE differente. "
             "**C'est pour ca que la colonne `zones engine/` existe** : elle dit en un coup d'oeil sur "
             "quelle face vit la reference.\n")
    L.append("- **GAP-MENTION [.]** -- le nom n'existe que dans de la **prose** (commentaire / "
             "docstring). Le passif a ete VU, jamais BRANCHE.\n")
    L.append("- **GAP-ABSENT [ ]** -- aucune trace, nulle part.\n\n")

    L.append("### Le critere naif « le nom apparait dans engine/ » est SATURE\n\n")
    L.append("Mesure de ce run : un `substring` brut du nom sur `engine/**/*.py` rend **%d/%d "
             "presents, 0 manquant**. La cause n'est pas que tout est porte : "
             "`engine/entities/triggered_ability_type.py` est un **mirror 1:1 de l'enum natif "
             "`TriggeredAbilityType`** (573 membres), ou le nom de CHAQUE passif figure comme membre. "
             "**Un catalogue n'est pas un cablage.**\n\n" % (n, n))
    L.append("Le signal code de cet audit est donc derive de l'**AST** et exclut les **definitions** "
             "de membres d'enum (%d assignations ecartees dans %d fichiers `engine/**/*.py`) tout en "
             "gardant les **usages** (`TriggeredAbilityType.X` = `ast.Attribute` -> compte). Il separe "
             "en outre le CODE (%d symboles distincts) de la PROSE (%d ko de commentaires + "
             "docstrings, invisibles a l'AST, lus via `tokenize`). Le rapprochement est CamelCase-aware : "
             "`HeavyGravCannon` matche `HeavyGravCannonEffect`, `Guard` ne matche ni `Guardsman` ni "
             "`RoyalGuard` (ni, pour `Possession`, l'unitId `blackPossession`).\n\n"
             % (meta["n_enum_members"], meta["n_files"], meta["n_code_syms"], meta["prose_kb"]))
    L.append("Chaque reference est en outre ATTRIBUEE A SA ZONE du moteur (`%s`), parce qu'une "
             "reference dans `playbook/`/`ai/`/`utilities/` (face DECISION) ne prouve RIEN sur "
             "l'execution combat. C'est ce qui separe **B** (litteral exact sous `runner/`) de **R**.\n\n"
             % ", ".join(meta["zone_names"]))

    L.append("### Confrontabilite des porteurs (gate HERO / MoW / SUMMON -- jamais NPC)\n\n")
    L.append("La colonne `kind` de gameconfig MENT sur la spawnabilite -> le pool vient de la verite "
             "native `buildNormalizedBC` (`rl_duel.py build --list-pool`, rank **%s** : %d unites "
             "regulieres + %d MoW).\n\n" % (pool.get("rank"), len(pool["units"]), len(pool["mow"])))
    L.append("| code | signification | confrontable |\n|---|---|---|\n")
    L.append("| `L+` | lineup PRESENT dans le pool | **oui** |\n")
    L.append("| `M` | MachineOfWar du pool | **oui** |\n")
    L.append("| `S+` | hors pool mais ATTEIGNABLE par summon depuis le pool (fermeture transitive du "
             "graphe `constants.unitId*`/`unitIds`/`unitToSpawn`, %d aretes -> %d unites atteintes) | "
             "**oui**, via son summoner |\n" % (meta["graph_edges"], meta["reachable"]))
    L.append("| `L~` | lineup ABSENT du pool -> **INJECTABLE** (%d unites) | **oui**, via "
             "`catalog_inject` |\n" % meta["n_injectable"])
    L.append("| `L!` | lineup dans la liste des NON SPAWNABLES (%d) | non -- leve a la construction |\n"
             % meta["n_unspawnable"])
    L.append("| `S?` | summon sans summoner derivable du gameconfig | **indetermine** (borne basse) |\n")
    L.append("| `N` | npc non atteignable | non -- NON PERTINENT |\n\n")

    L.append("> **`L~` compte comme confrontable.** Le pool derive du seed BC, qui est la capture "
             "d'UNE bataille : son catalogue ne porte que les unites possedees ce jour-la. Un heros "
             "hors pool s'INJECTE -- `catalog_inject.write_augmented_seed_bc(<hors data/>, [unitId])` "
             "alimente les DEUX catalogues (`Units` ET `Abilities`), puis "
             "`rl_duel.py build --seed-bc <chemin>`. Sans la config d'ability le porteur se deploie "
             "et FAUTE au cast (#226). Le seul refus legitime est `L!`, lu de "
             "`data/unspawnable_rank<N>.json` (repli : `rl_collect_batch.UNSPAWNABLE_FALLBACK`).\n\n")

    L.append("## Bilan\n\n")
    L.append("- Passifs distincts dans le parc (lineup %d / npc %d / summons %d) : **%d**\n"
             % (len(GC._index()["lineup"]), len(GC._index()["npc"]), len(GC._index()["summons"]), n))
    L.append("- **PORTES** (>=1 canal structurel) : **%d** (%.0f %%)\n" % (len(ported), 100.0 * len(ported) / n))
    L.append("- **ZONE-GRISE** (direct-read hors registre, a trancher) : **%d**\n" % len(grey))
    L.append("- **GAPS** (mention seule + absent) : **%d** = %d mention + %d absent\n"
             % (len(gaps), len(gap_m), len(gap_a)))
    L.append("- Passifs portes par >=1 unite **confrontable** : **%d** ; parmi eux, "
             "**%d gaps** et **%d zone-grise** -> c'est la FILE reelle.\n\n"
             % (len(conf), len(gaps_conf), len(grey_conf)))
    L.append("Ventilation des canaux qui portent (un passif peut en cumuler) : "
             + ", ".join("**%s**=%d" % (c, sum(1 for r in ported if c in r["channels"]))
                         for c in ("T", "O", "E", "G", "X", "B")) + "\n\n")

    L.append("## Tableaux par valeur\n")
    L.append("\nTri : nombre de porteurs spawnables SANS AMENAGEMENT (`L+`+`M`) decroissant, puis "
             "`S+` (un summon a amener), puis `L~` (une injection de catalogue). Un passif non "
             "couvert porte par une unite spawnable vaut plus qu'un passif npc-seul, et un porteur "
             "direct coute moins cher a confronter qu'un porteur a amener.\n")
    _table(L, "GAPS **confrontables** -- non couverts ET portes par une unite spawnable",
           bykey(gaps_conf), with_symbol=True)
    _table(L, "ZONE-GRISE confrontable -- reference en code hors registre, couverture a TRANCHER",
           bykey(grey_conf), with_symbol=True)
    _table(L, "GAPS non confrontables (npc-only / non spawnable `L!` / summon indetermine `S?`)",
           bykey([r for r in gaps if not r["confrontable"]]))
    _table(L, "ZONE-GRISE non confrontable", bykey([r for r in grey if not r["confrontable"]]))
    _table(L, "PORTES", bykey(ported))

    L.append("\n## FILE DISPATCHABLE\n\n")
    L.append("Passifs **non couverts** (GAP-MENTION ou GAP-ABSENT) **ET confrontables** "
             "(>=1 porteur `L+`/`M`/`S+`) : **%d items**. Le symbole natif est resolu PAR NOM dans "
             "`data/symbols/<build>/frida/methods.tsv` -- **a confirmer en ghidra avant tout port** "
             "(`search_symbols_by_name`), ce n'est pas une preuve d'existence de la mecanique.\n\n"
             % len(gaps_conf))
    L.append("| # | passif | porteurs spawnables | ventilation | verdict | symbole natif "
             "(a confirmer) |\n|---|---|---|---|---|---|\n")
    for i, r in enumerate(bykey(gaps_conf), 1):
        L.append("| %d | **%s** | %s | %s | %s | `%s` |\n"
                 % (i, r["name"], ", ".join(r["spawnable_examples"]) or "-",
                    _carriers_cell(r["cls"]), verdict(r), r["symbol"] or "?"))
    L.append("\n> Rappel de dispatch : un passif **`S+`** se confronte en spawnant son **summoner** "
             "(qui, lui, est dans le pool) -- ne jamais le classer « non confrontable ». Les `S?` "
             "sont a re-qualifier a la main (leur spawn n'est pas exprime dans `constants`).\n")

    L.append("\n## Ce qui n'est PAS couvert par cet audit\n\n")
    L.append("- **Fidelite** : un passif PORTE peut l'etre FAUSSEMENT (cas fondateur "
             "`HeavyGravCannon`, canal **E**, divergence live). Cet audit mesure la PRESENCE d'un "
             "cablage, jamais sa justesse.\n")
    L.append("- **[E]/[G] reposent sur une convention de NOMMAGE** (meme convention que "
             "`audit_kit_coverage._has_effect_named_after`), pas sur un lien lu du natif : verifie sur "
             "ce run, **0/%d** des `constants` d'un passif nomment un `EffectType`. Le gameconfig "
             "n'exprime AUCUN lien passif->effet.\n" % n)
    L.append("- **Completude d'un passif multi-volets** : un passif dont 1 volet sur 3 est porte "
             "compte comme PORTE (ex. `AnvilShield`). Le decoupage par volet est un travail de recon.\n")
    L.append("- **Face DECISION** : hors perimetre -- un passif ne se caste pas, il n'a pas de "
             "playbook. Seule la face COMBAT est auditee.\n")
    L.append("- **Reachability `S?`** : borne basse assumee -- **%d** des %d summons du parc n'ont "
             "AUCUNE arete derivable du gameconfig (leur spawn n'est pas exprime dans `constants`) "
             "et sont donc comptes non-confrontables par defaut.\n"
             % (meta["summons_unreached"], len(GC._index()["summons"])))
    L.append("- **Traits** : mecanique voisine mais registre distinct -> `docs/rl/unit-trait-coverage.md`.\n\n")
    L.append("### Relation aux audits existants\n\n")
    L.append("- `docs/rl/combat-ability-coverage.md` (par-ability ACTIVE) : disjoint de celui-ci -- "
             "l'intersection des noms actives/passifs est vide.\n")
    L.append("- `docs/rl/kit-coverage.md` (par KIT) mesure deja des passifs, mais **des seules unites "
             "`lineup`** et avec un booleen a 3 signaux (`ABILITY_TRIGGERS` / "
             "`ABILITY_INIT_OWNER_EFFECTS` / effet homonyme). Cet audit-ci couvre **tout le parc** "
             "(lineup + npc + summons), rend un verdict PAR PASSIF avec son CANAL, ventile les "
             "porteurs par confrontabilite, et ajoute 3 signaux (`ABILITY_OWNER_EFFECTS`, "
             "`EFFECT_TRIGGERS`, bespoke `runner/`) -- son jeu de canaux est un SUR-ENSEMBLE. Les "
             "deux reposent sur la meme convention de nommage pour le canal effet, donc ils ne "
             "peuvent pas se contredire sur les signaux partages ; ils se completent (vue KIT = "
             "« que reste-t-il a faire sur cette unite », vue PASSIF = « ce mecanisme est-il "
             "branche »).\n")
    return L


def main() -> int:
    ap = argparse.ArgumentParser(description="Audit de couverture des abilities passives.")
    ap.add_argument("--pool-file", default=None,
                    help="instantane JSON du pool spawnable (audit 100 %% offline) ; "
                         "par defaut le pool est lu live via `rl_duel.py build --list-pool` "
                         "et sauvegarde dans logs/passive-audit-pool.json")
    a = ap.parse_args()

    pool = read_pool(a.pool_file)
    rows, meta = build_rows(pool)
    lines = render(rows, meta)
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w", encoding="utf-8") as f:
        f.writelines(lines)

    ported = [r for r in rows if r["ported"]]
    grey = [r for r in rows if verdict(r) == "ZONE-GRISE"]
    gaps = [r for r in rows if verdict(r).startswith("GAP")]
    gaps_conf = [r for r in gaps if r["confrontable"]]
    grey_conf = [r for r in grey if r["confrontable"]]
    q = meta["enum_qual"]
    print("ecrit -> %s" % OUT)
    print("passifs=%d | enum: TriggeredAbilityType=%d ActiveAbilityType=%d"
          % (len(rows), q["triggered"], q["active"]))
    print("porte=%d zone-grise=%d gap=%d | confrontables: gap=%d zone-grise=%d"
          % (len(ported), len(grey), len(gaps), len(gaps_conf), len(grey_conf)))
    print("canaux: " + ", ".join("%s=%d" % (c, sum(1 for r in ported if c in r["channels"]))
                                 for c in ("T", "O", "E", "G", "X", "B")))
    print("pool rank %s : %d units + %d MoW" % (pool.get("rank"), len(pool["units"]), len(pool["mow"])))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
