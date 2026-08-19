#!/usr/bin/env python
"""catalog_inject -- INJECTION DE PORTEURS AU CATALOGUE `BattleConfiguration.Units`.

PROBLEME (cases #92 / #54). Le seed BC sur disque (`data/seed-bc.json`) est la capture d'UNE
bataille reelle : son `Units[]` ne contient que les 175 unites que le compte du joueur possedait
ce jour-la. Des heros/MoW du gameconfig n'y sont PAS (les Votann, thousDaemonPrince,
necroReanimator, darkaStormSpeeder, ...) -> `rl_duel build --p-units <id>` les refuse (hors pool)
et leurs abilities sont INCONFRONTABLES.

⚠ LE COMPTE SE RE-DERIVE, IL NE SE CITE PAS : cette ligne annoncait « 17 » et en portait **21** a
la re-mesure du 2026-08-15 (#254-bc-r1). L'ecart se creuse a chaque MAJ du jeu, sans un mot ;
`catalog_gap` / `catalog_gap_report` et l'epingle `MISSING_LINEUP_ENTRIES` sont ce qui le DIT
desormais (`python catalog_inject.py --missing`).

POURQUOI `Units[]` EST LE CATALOGUE (RE, decompile = verite) :
  `IdunBattle.Core.Services.BattleQuery$$GetUnitConfig(this, string unitId)` resout un unitId en
  parcourant la liste `Units` de la BattleConfiguration (BC+0x80) et en comparant `UnitConfiguration.Id`
  (champ +0x10) ; si aucune entree ne matche il LOG une erreur et rend null. Toute la chaine de spawn
  (`IdunBattle.Messages.AddUnitMessage` -> `IdunBattle.Operations.AddUnitOperation$$Execute`,
  `IdunBattle.Messages.AddMachineMessage` pour les MoW) part de ce lookup.

  Cote jeu, cette liste est CONSTRUITE, pas figee :
  `Idun.Source.IdunBattle.View.BattleConfigBuilder$$AddMainPlayerUnitConfigs` /
  `...$$AddPredefinedUnitConfigs` / `...$$AddSummonUnitConfigs` appellent tous
  `Idun.Source.IdunBattle.View.BattleConfigBuilder$$GetUnitConfiguration(unit, universe, ...)` puis
  `List.Add(BC.Units, cfg)` (dedupe par Id via un OrderedSet). Ajouter une entree au catalogue
  n'est donc PAS un hack : c'est exactement ce que le jeu fait quand une unite entre en bataille.

CE QUE FAIT CE MODULE. Il MIRROR `GetUnitConfiguration` cote offline : il construit l'entree
`IdunBattle.Configuration.UnitConfiguration` d'un unitId DEPUIS LE GAMECONFIG (units.lineup / .npc /
.summons + units.damageProfiles + units.heroProgressionSteps[MoW]) et depuis la table d'enums
per-build `data/symbols/<build>/frida/enums.tsv` (ActiveAbilityType / TriggeredAbilityType).
Les 8 stats de combat (Health/Damage/Armor/FixedArmor/Crit*/Block*) NE sont PAS inventees : elles
sont laissees a 0 et RECALCULEES par le natif `IStatsFormula.StatsUsingProgressionIndexFor` au
travers du RPC `buildNormalizedBC` (cf. frida/hooks/features/normalize-bc/json-build.ts), au meme
titre que pour les 175 entrees deja presentes.

FIDELITE PROUVEE, PAS POSTULEE : `--validate` re-synthetise les 175 entrees du seed BC et diffe
champ par champ contre la capture reelle. Attendu : 0 divergence sur tous les champs derives
(VisualId, QuestUnitId, Faction, Subfaction, Traits, Movement, NumberOfMembers, Weapons +
DamageProfile complet, ActiveAbilities, PassiveAbilities, ConfigId).

USAGE
    python catalog_inject.py --validate
    python catalog_inject.py --show votanMemnyr
    python catalog_inject.py --missing                      # heros/MoW du gameconfig absents du seed BC
    python catalog_inject.py --units thousDaemonPrince,necroReanimator --out <chemin absolu>.json
    python rl_duel.py build --seed-bc <ce fichier> --board MC1_67 --p-mow thousDaemonPrince ...

Le seed BC PARTAGE (`data/seed-bc.json`) n'est JAMAIS modifie : on ecrit un fichier a part que
`rl_duel build --seed-bc` (et `rl_collect_batch._load_seed_bc(path)`) consomme deja.

DEPUIS UN TEST / PROBE PYTHON : appeler `write_augmented_seed_bc(<out>, [<ids>])` (pas le CLI en
subprocess, pas un clone de bloc Unit a la main -- cf. la docstring de cette fonction et #226).
"""
from __future__ import annotations

import argparse
import copy
import functools
import json
import sys
from pathlib import Path

import gameconfig as G
import host_inputs

ROOT = Path(__file__).resolve().parents[2]
SEED_BC = ROOT / "data" / "seed-bc.json"
SYMBOLS = ROOT / "data" / "symbols"

# UnitConfiguration : champs CONSTANTS sur les 175 entrees capturees (tous factions/kinds
# confondus). Ce sont des champs Idun legacy que le catalogue Tacticus n'utilise pas :
#   Affinity = 5 = IdunBattle.Entities.Enum.UnitAffinity.None
#   Class    = 4 = IdunBattle.Entities.Enum.UnitClass.NONE
#   DamageType = 0 (IdunBattle.Entities.Enum.DamageType.Physical) / ArmorType = 0
#   Range    = 0 (la portee reelle vit dans Weapons[].Range)  /  Shield = 0
_CONST_FIELDS = {
    "Shield": 0, "Range": 0, "CritChance": 0, "CritDamage": 0,
    "BlockChance": 0, "BlockDamage": 0,
    "DamageType": 0, "ArmorType": 0, "Affinity": 5, "Class": 4,
}

# Champs que `buildNormalizedBC` REECRIT (json-build.ts) -> leur valeur ici est un placeholder.
NORMALIZED_FIELDS = (
    "Health", "Damage", "Armor", "FixedArmor", "CritChance", "CritDamage",
    "BlockChance", "BlockDamage", "RemainingHealth",
    "Rarity", "Level", "Rank", "StarLevel",
    "ActiveAbilityLevel", "PassiveAbilityLevel", "TertiaryAbilityLevel",
)


# ═══ REGISTRE DES GREFFES DU PROCESSUS (#448-r3-r1-r1) ════════════════════════════════════════════
#
# POURQUOI IL EXISTE. Un montage qui GREFFE fabrique une `BattleConfiguration` qui S'ECARTE du
# gameconfig -- c'est tout son objet. Le port, lui, ne voit cet ecart que si le canal
# `unitAbilityStates` a parle (`snapshot.load_state`, seeds `passive_abilities` /
# `active_abilities` / `config_active_abilities` / `triggered_abilities`). Sans le canal,
# `triggers/dispatch/core.py::collect_triggered_abilities` retombe sur `gameconfig.unit(<greffon>)`,
# qui ne porte evidemment PAS la greffe : AUCUNE classe greffee n'est montee, et toute assertion
# NEGATIVE du montage (« l'effet n'est plus la », « aucun marqueur ») passe A VIDE, EN VERT.
#
# MESURE (2026-08-05, `probe_448_r2b_stormboyz_teleporting_in.py`) : 0 echec en CLI contre 3 sous
# pytest -- MEME code, MEME seed, MEME board. Le seul ecart etait le transport ambiant, que
# `tests/conftest.py::live_session` lie et qu'un lancement direct ne liait pas. La degradation est
# PERMISSIVE : elle ne rate pas, elle MENT.
#
# CE QUE LE REGISTRE PERMET. `load_state` ne peut pas deviner qu'un BC est greffe -- elle recoit des
# PAYLOADS, jamais le BC. Mais le processus qui greffe est, dans tous les montages du depot, celui
# qui charge. Declarer la greffe ICI rend donc le fait LISIBLE au choke point, qui REFUSE au lieu
# de se degrader (`snapshot._refuse_if_grafted`). L'echappatoire est `ability_states=False` -- le
# refus EXPLICITE, deja le vocabulaire du tri-etat de #363.
#
# CE QU'IL NE COUVRE PAS, et c'est nomme : une greffe faite par un AUTRE PROCESSUS (un probe qui
# recoit un seed BC deja greffe par `--seed-bc <chemin>`). Le registre est un fait de PROCESSUS.
_GRAFTS: list = []


def declare_graft(kind: str, unit_id: str, what: str) -> None:
    """Enregistre une greffe DIVERGENTE appliquee par ce processus. Appelee par les primitives
    elles-memes -- un appelant n'a jamais a y penser."""
    _GRAFTS.append({"kind": kind, "unitId": unit_id, "what": what})


def declared_grafts() -> list:
    """Les greffes declarees par ce processus, dans l'ordre. Lue par
    `engine.runner.snapshot._refuse_if_grafted`, qui n'importe PAS ce module (elle le lit dans
    `sys.modules` : pas de greffe possible si le module n'a jamais ete importe)."""
    return list(_GRAFTS)


def clear_declared_grafts() -> None:
    """Purge le registre. A appeler quand un montage greffe puis charge DELIBEREMENT un etat SANS
    greffe (contre-bras de controle) -- ou au teardown d'un test."""
    _GRAFTS.clear()


# --------------------------------------------- le registre PAR RUNNER, sur DISQUE (#448-r3-r1-r1-r1)
#
# CE QUE LE REGISTRE DE PROCESSUS NE COUVRE PAS, et que celui-ci ferme. Le patron mesure : un
# processus greffe et ECRIT un seed BC (`rl_duel build --graft`, `write_relic_seed_bc`, ...) ; un
# SECOND processus le recoit par `--seed-bc <chemin>` et charge l'etat sans canal
# `unitAbilityStates`. Cote consommateur, `_GRAFTS` est VIDE (la greffe a eu lieu ailleurs) et le
# refus de `snapshot._refuse_if_grafted` ne mord pas -- alors que c'est exactement le regime ou le
# port serait AMPUTE.
#
# GISEMENT CHIFFRE (#448-r3-r1-r1-r1) : **15** fichiers de `scripts/python/**` exposent `--seed-bc`
# en option CLI -- le seul regime ou un seed BC arrive d'un AUTRE processus -- et **13** ne portent
# aucune primitive de greffe : ce sont les points d'entree du patron.
#
# LA CLE EST LE RUNNER, et c'est le seul identifiant que les deux cotes partagent. `load_state` ne
# recoit ni la BC ni le state-file, mais elle connait le runner (`snapshot.runner_label` : tout
# payload de capture porte `runner: "build#<id>"`). Le greffeur ECRIT donc son registre sous ce
# label au moment ou il connait le `runnerId`, et le consommateur le RELIT par la meme cle.
#
# L'EMPLACEMENT est `logs/`, jamais `data/` (#349 : `data/` = ce qu'on LIT, et rien d'un run n'y
# va). Il vit donc dans le worktree du greffeur -- ce qui est exactement la portee voulue, puisque
# les deux processus d'un meme montage sont lances par le meme acteur, dans le meme checkout.
_GRAFT_REGISTRY_DIR = ROOT / "logs" / "runners" / "grafts"


def runner_graft_path(label: str) -> Path:
    """Fichier de registre d'un label de runner. `"build#37"` -> `logs/runners/grafts/build-37.json`.

    Le `#` est remplace : il est legal sous Windows mais penible en ligne de commande, et le label
    n'a pas d'autre caractere a echapper (`live` ou `build#<entier>`)."""
    return _GRAFT_REGISTRY_DIR / (str(label).replace("#", "-").replace("/", "_") + ".json")


def publish_runner_grafts(label: str, grafts=None) -> Path | None:
    """ECRIT les greffes de ce processus sous le label du runner qu'il vient de construire.

    Rend le chemin ecrit, ou `None` s'il n'y avait RIEN a publier -- on ne cree pas un fichier vide
    qui se lirait « mesure, et aucune greffe » alors que rien n'a ete monte. Un echec d'ecriture est
    AVALE : ce registre est un garde-fou, il ne doit jamais faire echouer un build par lui-meme.
    """
    items = list(_GRAFTS if grafts is None else grafts)
    if not items:
        return None
    p = runner_graft_path(label)
    try:
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(items), encoding="utf-8")
    except OSError:
        return None
    return p


def clear_runner_grafts(label: str) -> None:
    """Retire le registre d'un label -- a appeler quand le runner est DISPOSE, puisque son id peut
    etre recycle par un build ulterieur (meme raison que `snapshot.clear_ability_states_cache`)."""
    try:
        runner_graft_path(label).unlink()
    except OSError:
        pass


# ------------------------------------- les SECTIONS DE BC publiees par runner (#449-r2-r4-r1)
#
# MEME chainon, autre charge. `engine.runner.snapshot.load_state` ne recoit ni la BC ni le
# state-file : les sections de `BattleConfiguration` qui n'ont AUCUN RPC pour les publier
# (`Damage`, et de la meme famille `Targeting` #444) lui sont structurellement invisibles. Elle
# connait en revanche le RUNNER -- donc le montage, qui tient la BC, la depose sous ce label.
#
# CE QUE CA CHANGE, mesure : `damage_config` n'etait alimente par AUCUN appelant reel (seuls les
# deux `probe_449r2r4*` le passaient), si bien que tout runner retombait sur le defaut DERIVE de
# `data/seed-bc.json`. C'est exact tant qu'on part de cette seed, et FAUX -- silencieusement --
# des qu'un montage passe `--seed-bc` avec une section `Damage` modifiee.
_BC_SECTIONS_DIR = ROOT / "logs" / "runners" / "bc-sections"

#: Sections publiees. STRICTEMENT celles qu'un consommateur LIT : publier une section que personne
#: ne lit fabriquerait du code mort qui aurait l'air d'un canal.
#:   * `Damage`  -> `DamageConfiguration.from_bc` (#449-r2-r4-r1) ;
#:   * `Player`  -> `snapshot._facteur_tours_par_round` (#889-r9), qui itere `TurnOrder` et ecarte
#:                  `PlayerType == 2` comme `IdunBattle.Core.Services.BattleQuery$$ConvertRoundsToTurns`.
BC_SECTIONS_PUBLIEES = ("Damage", "Player")


def runner_bc_sections_path(label: str) -> Path:
    return _BC_SECTIONS_DIR / (str(label).replace("#", "-").replace("/", "_") + ".json")


def publish_runner_bc_sections(label: str, bc: dict) -> Path | None:
    """Depose les sections de CETTE BC sous le label du runner. `None` si aucune n'est presente.

    Une section absente de la BC n'est PAS ecrite comme `{}` : le tri-etat du lecteur distingue
    « pas mesure » (pas de cle -> defaut derive de la seed) de « la BC a parle et elle dit zero »
    (dict vide). Fabriquer le second a partir du premier est exactement le vice que ce canal
    ferme."""
    charge = {s: bc.get(s) for s in BC_SECTIONS_PUBLIEES if isinstance(bc.get(s), dict)}
    if not charge:
        return None
    p = runner_bc_sections_path(label)
    try:
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(charge), encoding="utf-8")
    except OSError:
        return None
    return p


def clear_runner_bc_sections(label: str) -> None:
    """Meme cycle de vie que le registre de greffes : l'id de runner est RECYCLE."""
    try:
        runner_bc_sections_path(label).unlink()
    except OSError:
        pass


# --------------------------------------------------------------------------- enums per-build

def _build_hash() -> str:
    """Hash du build qui FAIT FOI, designe par `data/symbols/CURRENT`.

    Exigeait auparavant un repertoire UNIQUE sous data/symbols/ -- ce qui cassait des qu'une
    MAJ laissait l'ancien build a cote du neuf, alors qu'on le conserve EXPRES (son diff est
    le rapport de changement du jeu). Cf. `symbols_layout.py`."""
    from symbols_layout import current_build
    return current_build()


@functools.lru_cache(maxsize=16)
def enum_map(enum_name: str, build: str | None = None) -> dict:
    """{membre: id} d'un enum, lu dans data/symbols/<build>/frida/enums.tsv.

    C'est la SEULE source acceptable pour les ids d'ability : elle est estampillee
    per-build (`#!il2cpp-provenance ... build=<hash>`) et versionnee. `frida/hooks/data/
    ability-names.ts` NE l'est pas et se revele STALE sur gqfc5mff6c (il ignore
    ReanimationBeam=1223 / NanoscarabRepairProtocols=1224, les deux abilities de
    necroReanimator) -> l'utiliser produirait un porteur SANS ability, silencieusement.

    `build` = un hash ARCHIVE (`symbols_layout.archived_builds()`) au lieu du build courant.
    Sert a ATTRIBUER une derive : un membre absent de l'enum d'un build ne peut pas avoir ete
    attribue par le gameconfig de ce build-la (cf. `STALE_UNIT_ENTRIES`).
    """
    p = SYMBOLS / (build or _build_hash()) / "frida" / "enums.tsv"
    if not p.exists():
        raise RuntimeError(f"table d'enums absente: {p}")
    with p.open(encoding="utf-8") as f:
        for line in f:
            if not line.startswith(enum_name + "\t"):
                continue
            out = {}
            for kv in line.rstrip("\n").split("\t", 1)[1].split(","):
                k, v = kv.split("=", 1)
                out[v] = int(k)
            return out
    raise RuntimeError(f"enum {enum_name!r} absent de {p}")


def ability_variable_id(name: str) -> int:
    m = enum_map("IdunBattle.Configuration.AbilityVariableType")
    return m[name.strip()]


def attack_range_type_id(name: str | None) -> int:
    if not name:
        return 0
    return enum_map("IdunBattle.Entities.Enum.AttackRangeType").get(name, 0)


def active_ability_id(name: str) -> int:
    m = enum_map("IdunBattle.Entities.Enum.ActiveAbilityType")
    if name not in m:
        raise KeyError(f"ActiveAbilityType.{name} inconnu du build courant")
    return m[name]


def triggered_ability_id(name: str) -> int:
    m = enum_map("IdunBattle.Entities.Enum.TriggeredAbilityType")
    if name not in m:
        raise KeyError(f"TriggeredAbilityType.{name} inconnu du build courant")
    return m[name]


# ═══ #894 : LA VOIE DU GAMECONFIG N'EST QU'UN *HINT* -- LE NATIF RESOUT PAR LE NOM ════════════════
#
# LE VERROU. `synthesize` resolvait `passiveAbilities` par `triggered_ability_id` et
# `activeAbilities` par `active_ability_id`, c.-a-d. « la VOIE dit l'enum ». Deux entrees du
# gameconfig contredisent cette equation, et l'une d'elles rendait `admecBossBelisarius`
# INMONTABLE (`KeyError: TriggeredAbilityType.ShroudPsalm inconnu du build courant`).
#
# CE QUE LE NATIF FAIT, LU (decompile = verite) --
# `Idun.Source.IdunBattle.View.BattleConfigBuilder$$SetupAbilities` itere UNE seule liste
# (`IdunMetaLogic.UserProgress.UnitProgression$$GetAllAbilities` = `GetAbilities(isActive:true)`
# PUIS `GetAbilities(isActive:false)`, dans cet ordre) de `IdunMetaLogic.UserProgress.Model.UnitAbility`,
# dont les champs sont ecrits par `IdunMetaLogic.UserProgress.UnitProgression$$GetAbility` :
#     +0x00 = abilityId (string)                                  <- LE NOM, seul discriminant
#     +0x0c = `activeAbilities.Contains(abilityId)`  (= IsActive) <- LE HINT DE VOIE
#     +0x0e = `Level.IsZero`  (= ability VERROUILLEE)
#     +0x10 = `IdunBattle.Entities.Enum.AbilityHierarchy` (3 = Tertiary/relique)
# et l'aiguillage est :
#     si +0x0e != 0                     -> l'entree est IGNOREE (verrouillee)
#     sinon si +0x0c != 0 (voie ACTIVE) -> `UnitAbility$$TryParseActiveAbilityType`
#           reussite -> `BattleConfigBuilder$$TrySetupActiveAbility`  -> `UnitConfiguration+0xa0`
#           ECHEC    -> **il TOMBE dans le chemin passif ci-dessous** (pas de `continue`)
#     chemin passif                     -> `BattleConfigBuilder$$TrySetupPassiveAbility`
#           = `UnitAbility$$TryParseTriggeredAbilityType`
#           reussite -> `UnitConfiguration+0xa8` (ou `+0xb0` si hierarchy == 3)
#           ECHEC    -> **RIEN N'EST AJOUTE** -- l'ability est ABANDONNEE, sans log
#
# ⇒ LE REPLI EST ASYMETRIQUE, et c'est LA chose a ne pas deviner : ACTIVE -> PASSIVE existe,
#   PASSIVE -> ACTIVE **n'existe pas**. Une resolution croisee symetrique (« essayer les deux
#   enums, retenir celui qui porte le nom ») serait donc INFIDELE dans un sens sur deux : elle
#   monterait `ShroudPsalm` que le jeu, lui, ne monte pas.
#
# LE GISEMENT, MESURE et non suppose (`probe_895_voie_vs_enum.py`, re-derive du gameconfig
# VIVANT et des deux tables d'enum du build courant) : sur 1382 occurrences / 422 noms des
# quatre voies (`activeAbilities`, `passiveAbilities`, `mythicAbilities`, `relicAbilities`),
# **2 occurrences** contredisent leur voie, **0** nom est ambigu (present dans les DEUX enums),
# **0** nom est absent des deux :
#     `Maugetar`    ecrit en `activeAbilities`  de `eldarBossMauganRaUltra` -> TriggeredAbilityType 1498
#     `ShroudPsalm` ecrit en `passiveAbilities` de `admecBossBelisarius`    -> ActiveAbilityType  1181
# `mythicAbilities` (11 noms) et `relicAbilities` (25 noms) sont 100 % `TriggeredAbilityType`.
#
# ⚠ POURQUOI L'ORDINAL NE PEUT PAS SERVIR DE RATTRAPAGE : `ActiveAbilityType.ShroudPsalm` = 1181
# est AUSSI `TriggeredAbilityType.GuardianOrganism`. Ecrire 1181 dans `PassiveAbilities` monterait
# donc un passif ETRANGER, sans la moindre erreur. C'est la forme silencieuse decrite au CLAUDE.md.


def route_configured_abilities(gc: dict) -> dict:
    """Mirror 1:1 de `Idun.Source.IdunBattle.View.BattleConfigBuilder$$SetupAbilities`.

    Rend `{"ActiveAbilities": [...ids], "PassiveAbilities": [...ids], "dropped": [...]}` pour
    l'entree gameconfig `gc` d'une unite. `dropped` liste les `(nom, voie)` que le natif
    ABANDONNE (nom d'aucun des deux enums par le chemin qui lui est ouvert) -- jamais en silence.

    Le niveau (`UnitAbility+0x0e`, ability verrouillee) n'est PAS mirrore : le catalogue synthetise
    vise une unite au niveau d'ability cible (>= 1), donc l'entree n'est jamais verrouillee ici.
    La `TertiaryAbility` (hierarchy 3) n'est pas mirroree non plus -- c'est de l'etat JOUEUR,
    pose par `equip_relic`, cf. `synthesize`.
    """
    act = enum_map("IdunBattle.Entities.Enum.ActiveAbilityType")
    tri = enum_map("IdunBattle.Entities.Enum.TriggeredAbilityType")
    active_names = list(gc.get("activeAbilities") or [])
    passive_names = list(gc.get("passiveAbilities") or [])
    # `UnitAbility+0x0c` = `activeAbilities.Contains(abilityId)` -- lu sur la LISTE, pas deduit de
    # la boucle : un nom present dans les deux voies serait `IsActive` dans les deux passages.
    is_active = set(active_names)
    out_active: list = []
    out_passive: list = []
    dropped: list = []
    # `GetAllAbilities` : actives d'abord, passives ensuite.
    for name, voie in ([(n, "activeAbilities") for n in active_names]
                       + [(n, "passiveAbilities") for n in passive_names]):
        if name in is_active and name in act:          # TryParseActiveAbilityType -> reussite
            out_active.append(act[name])
            continue
        if name in tri:                                # TrySetupPassiveAbility -> reussite
            out_passive.append(tri[name])
            continue
        dropped.append((name, voie))                   # le natif n'ajoute RIEN
    return {"ActiveAbilities": out_active, "PassiveAbilities": out_passive, "dropped": dropped}


def misfiled_ability_names() -> list:
    """Les `(unitId, voie, nom, enum_qui_le_porte)` du gameconfig VIVANT dont la voie contredit
    l'enum. Re-DERIVE a chaque appel -- ce compte bouge avec le gameconfig et le build."""
    act = enum_map("IdunBattle.Entities.Enum.ActiveAbilityType")
    tri = enum_map("IdunBattle.Entities.Enum.TriggeredAbilityType")
    attendu = {"activeAbilities": act, "passiveAbilities": tri,
               "mythicAbilities": tri, "relicAbilities": tri}
    out = []
    units = G._cfg()["units"]
    for kind in ("lineup", "npc", "summons"):
        for uid, u in (units.get(kind) or {}).items():
            for voie, table in attendu.items():
                for name in (u.get(voie) or []):
                    if name in table:
                        continue
                    porteur = ("ActiveAbilityType" if name in act else
                               "TriggeredAbilityType" if name in tri else None)
                    out.append((uid, voie, name, porteur))
    return sorted(out)


# --------------------------------------------------------------------------- helpers gameconfig

def _weapons(gc: dict) -> list:
    """Mirror du bloc Weapons : units.<kind>[id].weapons x units.damageProfiles.

    IsMelee/IsRanged sont derives de la presence de `Range` (une arme sans portee est melee) ;
    verifie exact sur les 175 entrees capturees.
    """
    profiles = G._index()["damageProfiles"]
    out = []
    for w in (gc.get("weapons") or []):
        pname = w.get("DamageProfile")
        prof = profiles.get(pname) or {}
        rng = w.get("Range")
        out.append({
            "DamageProfileType": pname,
            "DamageProfile": {
                "DamageProfileType": pname,
                "PiercingDamageRatio": prof.get("PiercingRatio", 0),
                "DamageTraits": list(prof.get("Traits") or []),
            },
            "Hits": w.get("hits"),
            "Range": rng,
            "IsMelee": rng is None,
            "IsRanged": rng is not None,
        })
    return out


@functools.lru_cache(maxsize=1)
def unit_trait_members() -> frozenset:
    """Noms des membres de `IdunBattle.Entities.Enum.UnitTrait` sur le build COURANT.

    C'est le VOCABULAIRE ferme de `UnitConfiguration.Traits` -- pas une convention de nommage :
    le champ est TYPE `List<IdunBattle.Entities.Enum.UnitTrait>`, cf. `_traits`.
    """
    return frozenset(enum_map("IdunBattle.Entities.Enum.UnitTrait"))


def _traits_raw(gc: dict) -> list:
    """[GrandAlliance] + [Subfaction si presente] + traits (+ "NPC" pour un npc NON-HERO), AVANT
    confrontation au vocabulaire de l'enum. Mirror de l'ordre observe dans les 175 entrees
    (l'alliance d'abord, la sous-faction ensuite :
    custoAtlacoya -> ['Imperial','SistersSilence','Hero','Parry','Terrifying']).

    ⚠ `NPC` N'EST PAS POSE A TOUT `kind == npc`, ET LE CROIRE COUTAIT 322 TRAITS EN TROP.
    Cette fonction l'ajoutait INCONDITIONNELLEMENT ; le natif, lui, ne le pose QUE si l'unite
    ne porte pas `Hero`. Mesure du 2026-08-19 sur les 508 entrees npc d'un catalogue forge par
    la fabrique native (`forge_seed_bc.py`) -- croisement (le gameconfig declare `Hero`) x
    (la BC porte `NPC`) :

        gc Hero=True  / BC NPC=False   322      gc Hero=True  / BC NPC=True     0
        gc Hero=False / BC NPC=True    186      gc Hero=False / BC NPC=False    0

    508/508, les deux cellules de contre-exemple a ZERO -- et la regle vaut aussi bien sur
    l'ENTREE (`gc["traits"]`) que sur la sortie. Les 322 concernes sont les `*Boss*` /
    `*Npc<Hero>` : des heros reemployes en boss, qui gardent `Hero`. Les 186 qui portent `NPC`
    sont les objets de plateau et le bestiaire (`LootObj_*`, `powup*`, termagants...).

    ⚠ POURQUOI `--validate` NE L'A JAMAIS VU, et pourquoi il restera vert apres ce correctif :
    il re-synthetise les 175 entrees du seed CAPTURE, qui n'en comptait que **4** de kind npc,
    toutes NON-`Hero`. Sur cet echantillon les deux regles rendent le meme resultat -- le temoin
    ne pouvait pas les distinguer. Ce n'est donc pas un controle qui a failli, c'est un REGIME
    DEGENERE : l'accord ne prouvait rien parce qu'aucun cas discriminant n'y figurait. Le cas
    n'est devenu observable qu'en amenant les 508 npc au catalogue.
    """
    out = []
    if gc.get("GrandAllianceId"):
        out.append(gc["GrandAllianceId"])
    if gc.get("Subfaction"):
        out.append(gc["Subfaction"])
    traits = list(gc.get("traits") or [])
    out += traits
    if gc.get("kind") == "npc" and "Hero" not in traits:
        out.append("NPC")
    return out


def dropped_traits(gc: dict) -> list:
    """Noms que `_traits_raw` produirait et que `UnitTrait` du build COURANT NE CONNAIT PAS.

    A regarder AVANT de conclure « ce porteur ne se deploie pas » : une liste non vide veut dire
    que le gameconfig est EN AVANCE sur le binaire (contenu pre-livre), pas que l'unite est cassee.
    """
    return [t for t in _traits_raw(gc) if t not in unit_trait_members()]


def _traits(gc: dict) -> list:
    """Bloc `UnitConfiguration.Traits` -- RESTREINT aux membres de `UnitTrait` du build courant.

    POURQUOI CE FILTRE, ET POURQUOI IL N'EST PAS COSMETIQUE (#270-d).
    `Traits` est TYPE `List<IdunBattle.Entities.Enum.UnitTrait>`, etabli au decompile en deux
    maillons :
      - `Idun.Source.IdunBattle.View.BattleConfigBuilder$$GetUnitConfiguration` recopie
        `UnitProperties+0x18` dans `UnitConfiguration+0xd0` (dernier champ, = `Traits` ; a defaut
        elle y pose une `List` neuve) ;
      - `IdunMetaLogic.UserProgress.Model.UnitPropertiesExtensions$$GetPlayerFacingTraits` lit ce
        MEME `UnitProperties+0x18` et rend un `List<IdunBattle.Entities.Enum.UnitTrait>`.
    Donc une valeur hors enum n'est pas « un trait que le natif ignorerait » : elle est
    INEXPRIMABLE dans ce champ. A la relecture du BC, `initAndStart` step=deserialize BC ->
    `Newtonsoft.Json.Converters.StringEnumConverter$$ReadJson` (token String) ->
    `Newtonsoft.Json.Utilities.EnumUtils$$ParseEnum` -> `$$MatchName` / `$$FindIndexByName`
    rendent un `Nullable` VIDE -> message bati par `Newtonsoft.Json.Utilities.StringUtils$$FormatWith`,
    `System.ArgumentException` construite puis LEVEE. Exception managee sous `invokeMethod` =>
    Frida rend « system error », d'ou `[error] initAndStart: system error`.

    CE QUI DECLENCHE LE CAS : le gameconfig VIVANT est livre EN AVANCE sur le binaire. Mesure du
    2026-07-31 (`rnca9r7q6c`) -- `astarLysander` (releaseStatus 2026-08-26) porte
    `Subfaction: ImperialFists`, et `UnitTrait` s'arrete a 4 sous-factions (`DeathKorpsKrieg` 9000,
    `FarsightEnclaves` 9001, `SistersSilence` 9002, `BloodRavens` 9003). C'est la SEULE des 669
    unites du gameconfig dont `_traits_raw` sort du vocabulaire, et le SEUL porteur de #270 qui ne
    se deployait pas.

    LE FILTRE NE PERD RIEN D'OBSERVABLE : aucun code natif de ce build ne peut tester un membre
    qui n'existe pas dans son propre enum. Il ne touche pas non plus la cohorte capturee -- sur
    les 175 entrees du seed BC, `_traits_raw` produit 0 nom hors enum, donc `--validate` est
    inchange. Ce qui est ecarte se lit par `dropped_traits`, jamais en silence.
    """
    members = unit_trait_members()
    return [t for t in _traits_raw(gc) if t in members]


def ability_multiplier_pct(rank: int, ability_level: int, is_mow: bool) -> int:
    """AbilityVariablesMultiplierPercentage -- mirror de
    `IdunMetaLogic.UserProgress.UnitConfigUtil$$GetAbilityVariablesMultiplierPercentageForProgressionIndex` :
    la fonction indexe `unitsConfig+0x80` (liste heros) ou `+0x88` (liste MoW, branche
    IsMachineOfWar) par le progression index et rend le champ +0x24. Cote gameconfig ces deux
    listes sont `units.heroProgressionSteps` / `units.heroProgressionStepsMoW`, et le champ
    est `abilityStatMultiplierPct`.

    On ne connait pas le progression index d'une unite non possedee : on prend le PREMIER
    palier qui couvre la cible (maxRank >= rank cote heros, maxAbilityLevel >= niveau
    d'ability cote MoW). A rank 17 ca rend 180 = exactement la valeur portee par les heros
    rank-17 du seed BC ; le champ n'est PAS recalcule par buildNormalizedBC, d'ou l'interet
    d'atterrir sur la meme valeur que la cohorte.
    """
    steps = G._cfg()["units"]["heroProgressionStepsMoW" if is_mow else "heroProgressionSteps"]
    key, target = ("maxAbilityLevel", ability_level) if is_mow else ("maxRank", rank)
    for s in steps:
        if s.get(key, 0) >= target:
            return s["abilityStatMultiplierPct"]
    return steps[-1]["abilityStatMultiplierPct"]


# --------------------------------------------------------------------------- synthese

def synthesize(unit_id: str, rank: int = 17, ability_level: int = 50,
               ability_mult_pct: int | None = None) -> dict:
    """Entree `IdunBattle.Configuration.UnitConfiguration` (JSON) pour `unit_id`.

    `unit_id` accepte le suffixe `:<level>` des variantes npc (mirror de
    `IdunBattle.Configuration.UnitConfigId$$CreateFromIdWithLevel`).
    Les 8 stats de combat sont a 0 : `buildNormalizedBC` les recalcule par le natif.
    """
    pure, _, lvl_sfx = unit_id.partition(":")
    gc = G.unit(pure)
    if gc is None:
        raise KeyError(f"{pure!r} absent du gameconfig (units.lineup/.npc/.summons)")
    visual = gc.get("visualId") or pure
    is_mow = "MachineOfWar" in (gc.get("traits") or [])
    mult = ability_mult_pct if ability_mult_pct is not None else \
        ability_multiplier_pct(rank, ability_level, is_mow)
    routed = route_configured_abilities(gc)
    e = {
        "Id": unit_id,
        "VisualId": visual,
        "QuestUnitId": gc.get("questUnitId") or visual,
        "Faction": gc.get("FactionId"),
        "Subfaction": gc.get("Subfaction"),
        # --- stats : placeholders, buildNormalizedBC les ECRASE (formule native) ---
        "Health": 0, "RemainingHealth": None, "Armor": 0, "FixedArmor": 0, "Damage": 0,
        # --- catalogue proprement dit ---
        "Movement": gc.get("Movement") or 0,
        "NumberOfMembers": gc.get("nrOfMembers") or 1,
        "Power": 0,
        "AbilityVariablesMultiplierPercentage": mult,
        "TertiaryAbilityVariablesMultiplierPercentage": 100,
        "Level": 1, "Rarity": 0, "Rank": 0, "StarLevel": 0,
        "Weapons": _weapons(gc),
        # Routage PAR NOM, mirror de `BattleConfigBuilder$$SetupAbilities` -- pas « la voie dit
        # l'enum », qui levait sur `admecBossBelisarius` (#894, cf. `route_configured_abilities`).
        "ActiveAbilities": routed["ActiveAbilities"],
        "PassiveAbilities": routed["PassiveAbilities"],
        # TertiaryAbility = l'ability du RELIQUE equipe : etat JOUEUR, pas gameconfig. Une unite
        # amenee sans relique porte null (171 des 175 entrees capturees).
        "TertiaryAbility": None,
        "ActiveAbilityLevel": 1, "PassiveAbilityLevel": 1, "TertiaryAbilityLevel": 0,
        "Traits": _traits(gc),
        "ConfigId": {
            "PureId": pure,
            "Rarity": None,
            "Level": int(lvl_sfx) if lvl_sfx else None,
            "IsBorrowed": False,
            "IsPvpOpponent": False,
        },
    }
    e.update(_CONST_FIELDS)
    return e


# ═══ CHEMIN DE STATS EXPLICITE -- NPC et SUMMON (#419-r1-tr12-r2) ═════════════════════════════════
#
# LE VERROU (case-92 §5bis). `buildNormalizedBC` calcule les 8 stats de combat par UN SEUL chemin :
# `IStatsFormula.StatsUsingProgressionIndexFor`, la formule des HEROS. Une unite sans table de
# progression de heros y LEVE, et le RPC la range dans `skipped` (« v2 patch: system error ») :
# elle n'entre jamais au pool de `--p-units`. C'est ce qui rendait tout porteur npc-only ou
# summon-only inconfrontable autrement que par GREFFE de son ability sur un heros du pool.
#
# LE NATIF A DEUX AUTRES CHEMINS, NOMMES, ET ILS NE SE RESSEMBLENT PAS :
#
#   NPC    `IdunMetaLogic.UserProgress.UnitProgression$$GetNpcStats(unitId, level)`
#          -> `$$GetTieredUnitConfig(unitId, kind=1)`
#          -> `idun.meta.extensions.UnitConfigExtensions$$GetStatsForLevel(config, level)`
#          -> `UnitStats.Init(stats, row)`.
#          La table est DANS LE GAMECONFIG (`units.npc[id].stats[]`) : 491/491 npc en portent une.
#          `GetStatsForLevel` = `stats[min(ToZeroBasedIndex(level), Count-1)]` -- clamp HAUT
#          seulement ; `idun.Idun.Source.Shared.UnitLevelExtensions$$ToZeroBasedIndex` LEVE sur
#          `level <= 0`. Le `level` est le suffixe `:<n>` de l'unitId
#          (`idun.shared.UnitNamingConventions$$GetLevelFromUnitId` : split ':', `Int32.TryParse`
#          de la 2e part, DEFAUT 1 -- pas 0, pas le dernier palier).
#
#   SUMMON `IdunMetaLogic.UserProgress.UnitProgression$$GetSummonStats(constantType, abilityConfig)`
#          Les stats ne sont PAS dans le catalogue de l'unite (les 65 entrees summon du gameconfig
#          n'ont AUCUN `stats[]`) : elles sont les VARIABLES `summon*` de l'ABILITY qui invoque,
#          au niveau de cette ability. Le natif lit, par `GetVariableForLevel` :
#              Health <- summonHp(41)          Damage <- summonDmg(42)
#              FixedArmor <- summonArmor(43)   CritChance <- summonCritChance(84)
#              BlockDmg <- summonBlockDmg(85)  BlockChance <- summonBlockChance(86)
#              CritDamage <- summonCritDmg(87)
#          en regime PRIMARY (`constantType` == `unitId`(0) ou `unitToSpawn`(8)), et les variantes
#          `_2` (67/68/69/88/89/90/91) sinon. Chaque variable NON NULLE ECRASE le champ ; une
#          variable a 0/absente laisse la valeur issue de la config de l'unite -- qui est 0 pour
#          un summon. Le second overload choisit le `constantType` : kind 0 essaie `unitToSpawn`
#          PUIS `unitId` ; kind 1 essaie `unitId_2`.
#
# ⚠ CE QUE LE CATALOGUE PORTE VRAIMENT POUR UN SUMMON, ET C'EST MESURE : le jeu ecrit
#   `Health=0` dans `BC.Units[]` pour **65 des 65** summons du seed BC capture. Donc poser des
#   stats non nulles sur une entree summon N'EST PAS un mirror du catalogue -- c'est un MONTAGE
#   de harnais qui reproduit l'etat POST-SPAWN (`SpawnUnitBehaviour$$GetStatsToOverride` pose ces
#   memes valeurs en `StatModifier` sur l'unite deja construite). Les deux voies sont donc
#   SEPAREES ici, et `explicit_stats` le DIT dans son champ `source`.
#
# ⚠⚠ LE POST-SPAWN A SON PROPRE ETAGE, ET SON REGIME NE SE DEDUIT PAS DE LA CONSTANTE D'ID
#    (#419-r1-tr12-r2-r1, lu au decompile le 2026-08-15 sur `t6dpr4k06g`). Ce que
#    `SpawnUnitBehaviour$$GetStatsToOverride` distribue, ce sont les `StatModifier` que le
#    BEHAVIOUR a places dans ses `SpawnUnitOptions` (`options+0x20`) ; et ces modificateurs sont
#    poses par une famille de fabriques distincte de la couche META :
#
#      `IdunBattle.Entities.Behaviours.SpawnUnitOptions$$WithStatsFromConfig(cfg, state, ordinal, ...)`
#          -> 7 appels a `IdunBattle.Entities.Behaviours.SpawnUnitOptions$$SetStatFromConfig`,
#             famille `summon*` : summonHp(0x29)->StatType 5, summonDmg(0x2a)->0,
#             summonArmor(0x2b)->0x10, summonBlockChance(0x56)->7, summonBlockDmg(0x55)->8,
#             summonCritChance(0x54)->9, summonCritDmg(0x57)->10.
#          Les trois wrappers FIGENT l'ordinal : `$$WithStatsFromConfig` (arite 4) = 1,
#          `$$WithStatsFromConfig2` = 2, `$$WithStatsFromConfig3` = 3.
#      `IdunBattle.Entities.Behaviours.SpawnUnitOptions$$WithStatsFromConfigSpawn(cfg, state, ordinal, ...)`
#          -> les MEMES 7 StatType, famille `spawn*` : spawnHp(0x6a), spawnDmg(0x69),
#             spawnArmor(0x6b), spawnBlockChance(0x6e), spawnBlockDmg(0x6f),
#             spawnCritChance(0x6c), spawnCritDmg(0x6d).
#
#    Le nom REEL de la variable est construit par
#    `IdunBattle.Configuration.AbilityConfiguration$$GetDynamicTypeu003C__Il2CppFullySharedGenericStructTypeu003E` :
#    `Enum.ToString(base)`, puis `Concat(nom, "_", ordinal)` SI `ordinal > 1`, puis
#    `Enum.TryParse` -- et il LEVE si le membre construit n'existe pas. C'est le meme foyer qui
#    sert `$$GetDynamicStringConstant(cfg, AbilityConstantType.unitId, ordinal)`, d'ou les ids
#    `unitId` / `unitId_2` / `unitId_3` / `unitId_4` du meme ordinal.
#
#    CONSEQUENCE, ET C'EST LE PIEGE : la couche META (`GetSummonStats`) deduit son regime de la
#    CONSTANTE (`isPrimary = ct == unitId(0) || ct == unitToSpawn(8)`) ; la couche BATAILLE, elle,
#    recoit un ORDINAL du behaviour. Les deux coincident pour l'immense majorite des abilities,
#    mais rien ne l'impose -- `SpiritualLeader` declare `genesSmnDecoy` par `unitId_2` (donc regime
#    `_2` cote META) tout en ne portant que `summonHp`/`summonDmg`/`summonArmor` NUS (donc
#    `WithStatsFromConfig`, ordinal 1, cote bataille). Un profil summon INTEGRALEMENT NUL est le
#    symptome de ce desalignement, ou d'une ability qui n'a aucune variable de stats du tout ;
#    `explicit_stats` REFUSE de le poser (cf. sa docstring).

# Les 8 stats de combat de `UnitConfiguration`, dans l'ordre du layout `UnitStats` meta
# (`IdunMetaLogic.UserProgress.Model.UnitStats$$Init` : +0x00 Health, +0x04 Damage, +0x0c Armor,
# +0x10 FixedArmor, +0x1c CritDamage, +0x20 CritChance, +0x24 BlockDamage, +0x28 BlockChance).
COMBAT_STAT_FIELDS = (
    "Health", "Damage", "Armor", "FixedArmor",
    "CritChance", "CritDamage", "BlockChance", "BlockDamage",
)

# `AbilityVariableType` -> champ `UnitConfiguration`, regime PRIMARY puis `_2`. Ordinaux LUS dans
# `data/symbols/<build>/frida/enums.tsv` ; les noms sont la source, l'ordinal n'est ecrit ici que
# pour rendre le decompile relisible.
SUMMON_STAT_VARS = (
    ("Health",       "summonHp",           "summonHp_2"),          # 41 / 67
    ("Damage",       "summonDmg",          "summonDmg_2"),         # 42 / 68
    ("FixedArmor",   "summonArmor",        "summonArmor_2"),       # 43 / 69
    ("CritChance",   "summonCritChance",   "summonCritChance_2"),  # 84 / 88
    ("BlockDamage",  "summonBlockDmg",     "summonBlockDmg_2"),    # 85 / 89
    ("BlockChance",  "summonBlockChance",  "summonBlockChance_2"), # 86 / 90
    ("CritDamage",   "summonCritDmg",      "summonCritDmg_2"),     # 87 / 91
)

# `AbilityConstantType` qui peuvent porter l'unitId d'un summon, et le regime que le natif en
# deduit. `GetSummonStats(kind, cfg)` : kind 0 -> `unitToSpawn`(8) puis `unitId`(0) ; kind 1 ->
# `unitId_2`(4). Le regime PRIMARY est `constantType in (0, 8)` -- lu tel quel au decompile.
SUMMON_ID_CONSTANTS = (("unitToSpawn", 8, True), ("unitId", 0, True), ("unitId_2", 4, False))

# --------------------------------------------- la voie DYNAMIQUE du spawn (#419-r1-tr12-r2-r1)
#
# Les 7 stats que `SpawnUnitOptions$$WithStatsFromConfig{,2,3}` (famille `summon*`) et
# `$$WithStatsFromConfigSpawn` (famille `spawn*`) posent en `StatModifier`, dans l'ordre des sept
# appels a `$$SetStatFromConfig` -- lu au decompile, y compris la valeur de `StatType`.
# Ce sont EXACTEMENT les memes 7 champs que `SUMMON_STAT_VARS` : la difference n'est pas la liste,
# c'est la FAMILLE de base et la facon dont l'ordinal est choisi (ordinal du BEHAVIOUR ici,
# constante d'id la-bas).
SPAWN_STAT_BASES = (
    ("Health",      "summonHp",          "spawnHp"),          # StatType 5
    ("Damage",      "summonDmg",         "spawnDmg"),         # StatType 0
    ("FixedArmor",  "summonArmor",       "spawnArmor"),       # StatType 0x10
    ("BlockChance", "summonBlockChance", "spawnBlockChance"), # StatType 7
    ("BlockDamage", "summonBlockDmg",    "spawnBlockDmg"),    # StatType 8
    ("CritChance",  "summonCritChance",  "spawnCritChance"),  # StatType 9
    ("CritDamage",  "summonCritDmg",     "spawnCritDmg"),     # StatType 10
)

#: Les constantes d'id que la voie DYNAMIQUE sait produire, par ordinal. Ce ne sont pas des
#: constantes « de plus » : c'est la MEME base `AbilityConstantType.unitId` passee a
#: `$$GetDynamicStringConstant` avec un ordinal, donc le nom se DERIVE (cf. `dynamic_member_name`).
#: L'enum du build s'arrete a `unitId_6` (125) -- au-dela, `Enum.TryParse` echoue et le natif LEVE.
DYNAMIC_ID_MAX_ORDINAL = 6


def dynamic_member_name(base: str, ordinal: int) -> str:
    """Mirror EXACT de la construction de nom de
    `IdunBattle.Configuration.AbilityConfiguration$$GetDynamicTypeu003C__Il2CppFullySharedGenericStructTypeu003E` :

        string name = Enum.ToString(base);
        if (ordinal > 1) name = String.Concat(name, "_", ordinal.ToString());
        if (!Enum.TryParse<T>(name, out t)) throw;   // GetDynamicTypeNotFoundErrorMessage

    L'ordinal 1 rend donc le nom NU (`unitId`, `summonHp`), et 2 rend `unitId_2` / `summonHp_2`.
    Le `> 1` est LU : un ordinal 0 rendrait lui aussi le nom nu, et le natif n'en produit pas.
    """
    o = int(ordinal)
    return base if o <= 1 else "%s_%d" % (base, o)


def unit_level_from_id(unit_id: str) -> int:
    """Mirror de `idun.shared.UnitNamingConventions$$GetLevelFromUnitId`.

    `split(':')` ; s'il y a au moins 2 parts, `Int32.TryParse` de la 2e -- et sur ECHEC de parse
    comme en l'absence de suffixe, le natif rend **1**, jamais 0 (0 ferait lever
    `ToZeroBasedIndex`) et jamais le dernier palier.
    """
    parts = str(unit_id).split(":")
    if len(parts) > 1:
        try:
            return int(parts[1])
        except ValueError:
            return 1
    return 1


def _to_zero_based_index(level: int) -> int:
    """Mirror de `idun.Idun.Source.Shared.UnitLevelExtensions$$ToZeroBasedIndex` : `level - 1`,
    et `InvalidOperationException` sur `level <= 0`. On LEVE aussi -- un clamp bas silencieux
    rendrait le palier 1 la ou le natif refuse."""
    if level <= 0:
        raise ValueError(
            f"unit level {level} <= 0 : ToZeroBasedIndex leve (InvalidOperationException)")
    return level - 1


def npc_stats_row(unit_id: str, level: int | None = None) -> dict:
    """Ligne `units.npc[id].stats[]` que le natif servirait -- mirror de
    `idun.meta.extensions.UnitConfigExtensions$$GetStatsForLevel(config, unitLevel)`.

    `idx = Math.Min(ToZeroBasedIndex(level), stats.Count - 1)` : clamp HAUT uniquement.
    """
    pure = str(unit_id).split(":")[0]
    gc = G.unit(pure)
    if gc is None:
        raise KeyError(f"{pure!r} absent du gameconfig")
    rows = gc.get("stats") or []
    if not rows:
        raise KeyError(f"{pure!r} n'a pas de table `stats[]` (les 65 summons sont dans ce cas)")
    lvl = unit_level_from_id(unit_id) if level is None else int(level)
    return rows[min(_to_zero_based_index(lvl), len(rows) - 1)]


def npc_progression_multiplier_pct(progression_index: int) -> int:
    """`AbilityVariablesMultiplierPercentage` d'un npc -- mirror EXACT de
    `IdunMetaLogic.UserProgress.UnitConfigUtil$$GetAbilityVariablesMultiplierPercentageForProgressionIndex` :
    la fonction INDEXE `unitsConfig+0x80` (= `units.heroProgressionSteps`) par le progression index
    et rend le champ +0x24 (`abilityStatMultiplierPct`).

    A la difference d'`ability_multiplier_pct` (qui doit DEVINER le palier d'un heros non possede
    en cherchant le premier `maxRank >= rank`), le progression index d'un npc est CONNU : il est
    ecrit dans sa ligne `stats[]`. Mesure sur le seed BC : `necroNpc3Deathmark:7` porte
    ProgressionIndex 4 et `AbilityVariablesMultiplierPercentage` 120 = `steps[4]`.
    """
    steps = G._cfg()["units"]["heroProgressionSteps"]
    idx = max(0, min(int(progression_index), len(steps) - 1))
    return steps[idx]["abilityStatMultiplierPct"]


def npc_stats(unit_id: str, level: int | None = None) -> dict:
    """Les 8 stats de combat d'un npc + ses champs de progression, mirror de
    `IdunMetaLogic.UserProgress.UnitProgression$$GetNpcStats`.

    Les champs de progression sont ceux que
    `Idun.Source.IdunBattle.View.BattleConfigBuilder$$GetUnitConfiguration` recopie dans l'entree :
    `Rank` <- row.Rank, `StarLevel` <- row.StarLevel, `Level` <- row.AbilityLevel.

    ⚠ `ActiveAbilityLevel` / `PassiveAbilityLevel` NE viennent PAS directement de la ligne.
    `Idun.Source.IdunBattle.View.BattleConfigBuilder$$SetupAbilities` les prend des slots `0x1c` /
    `0x1d` d'`IUnitModel` (`GetPrimaryAbility()` / `GetSecondaryAbility()`, champ `+0x08` = le
    niveau) et les ecrit en `UnitConfiguration+0xb8` / `+0xbc`. Sans ability de cette hierarchie il
    n'y a aucun niveau a lire, et le champ reste au DEFAUT 1.
    MESURE (les 4 npc du seed BC) : `necroNpc1Warrior:7` est le SEUL sans `activeAbilities` et le
    SEUL a porter `ActiveAbilityLevel = 1` ; les 3 autres portent `AbilityLevel` (17). La branche
    VIDE de `PassiveAbilityLevel` n'est PAS confrontee (les 4 npc ont un passif) : elle est ecrite
    par symetrie et reste sans consequence -- une liste d'abilities vide ne donne rien a niveler a
    `IdunBattle.Entities.Factories.UnitFactory$$AddConfiguredAbilities`.
    """
    pure = str(unit_id).split(":")[0]
    gc = G.unit(pure) or {}
    row = npc_stats_row(unit_id, level)
    out = {f: int(row.get(f) or 0) for f in COMBAT_STAT_FIELDS}
    ab = int(row.get("AbilityLevel") or 1)
    out.update({
        "Rank": int(row.get("Rank") or 0),
        "StarLevel": int(row.get("StarLevel") or 0),
        "Level": ab,
        "ActiveAbilityLevel": ab if (gc.get("activeAbilities") or []) else 1,
        "PassiveAbilityLevel": ab if (gc.get("passiveAbilities") or []) else 1,
        "AbilityVariablesMultiplierPercentage":
            npc_progression_multiplier_pct(row.get("ProgressionIndex") or 0),
    })
    return out


def summon_declaring_abilities(unit_id: str) -> list[tuple[str, str, bool]]:
    """(abilityName, constantKey, isPrimary) de toutes les abilities dont une constante d'id
    designe `unit_id`.

    ⚠ CE BALAYAGE N'EST PAS UN MIRROR : le natif ne cherche jamais l'ability, il la RECOIT
    (`GetSummonStats(constantType, abilityConfig)`). C'est le harnais qui doit la retrouver, et
    c'est exactement le recours 2 de `case-92` §5bis (« SUMMON SANS invocateur -- verifie par
    balayage »). Ce qui EST un mirror, c'est le regime primary/`_2` deduit du `constantType`.
    """
    pure = str(unit_id).split(":")[0]
    out = []
    for name, a in (G._cfg()["units"]["abilities"] or {}).items():
        consts = a.get("constants") or {}
        for key, _ordinal, primary in SUMMON_ID_CONSTANTS:
            if str(consts.get(key, "")).split(":")[0] == pure:
                out.append((name, key, primary))
    return out


def spawn_declaring_abilities(unit_id: str) -> list[tuple[str, str, int]]:
    """(abilityName, constantKey, ordinal) de la voie DYNAMIQUE -- `unitId` .. `unitId_6`.

    Pendant exact de `summon_declaring_abilities` sur l'autre etage. Le natif ne cherche pas
    davantage ici : il appelle
    `IdunBattle.Configuration.AbilityConfiguration$$GetDynamicStringConstant(cfg,
    AbilityConstantType.unitId, ordinal)` avec l'ordinal que le behaviour a choisi. C'est donc,
    comme le balayage voisin, un RECOURS DE HARNAIS (case-92 Sec.5bis, recours 2) : retrouver
    l'ability a partir du summon, ce que le jeu n'a jamais a faire.

    L'ordinal rendu est celui qui reconstruit le nom de la cle (`unitId` -> 1, `unitId_2` -> 2,
    ...), donc celui que `WithStatsFromConfig{,2,3}` / `WithStatsFromConfigSpawn` passeraient a
    `$$SetStatFromConfig` si le behaviour suivait la meme numerotation. ⚠ Rien ne l'IMPOSE : le
    behaviour choisit son ordinal de variable independamment (cf. le bloc RE en tete de section).
    """
    pure = str(unit_id).split(":")[0]
    out = []
    for name, a in (G._cfg()["units"]["abilities"] or {}).items():
        consts = a.get("constants") or {}
        for ordinal in range(1, DYNAMIC_ID_MAX_ORDINAL + 1):
            key = dynamic_member_name("unitId", ordinal)
            if str(consts.get(key, "")).split(":")[0] == pure:
                out.append((name, key, ordinal))
    return out


def summon_spawn_regimes(unit_id: str) -> dict:
    """RECENSEMENT des voies par lesquelles un summon peut recevoir des stats -- l'outil qui
    manquait pour trancher `#419-r1-tr12-r2-r1`.

    Rend `{"meta": [...], "dynamic": [...], "verdict": "<mot>"}` ou :

      * `meta`    = ce que `UnitProgression$$GetSummonStats` peut atteindre : les 3 constantes
        FIXES de `SUMMON_ID_CONSTANTS`, avec le regime PRIMARY/`_2` qu'il en deduit, et les
        variables `summon*` que l'ability porte REELLEMENT pour ce regime ;
      * `dynamic` = ce que la voie de BATAILLE peut atteindre : `unitId` .. `unitId_6`, avec les
        variables `summon*` ET `spawn*` de l'ordinal correspondant.
      * `verdict` : `meta` (au moins une variable lue non nulle par la voie META),
        `dynamic-only` (rien cote META, mais l'ability porte des variables a l'ordinal dynamique),
        `zero` (l'ability est trouvee mais ne porte AUCUNE variable de stats exploitable),
        `orphelin` (AUCUNE ability du gameconfig ne nomme ce summon).

    POURQUOI CE RECENSEMENT EXISTE. La fiche du residu classait 9 summons « hors portee des trois
    constantes » et proposait d'elargir `GetSummonStats`. La lecture du decompile dit que c'est le
    mauvais axe : `unitId_3`(109) / `unitId_4`(123) ne sont pas des constantes « oubliees » par
    l'overload de selection, ce sont les ordinaux 3 et 4 de la voie DYNAMIQUE, qui lit une AUTRE
    famille de variables. Elargir aurait fait rendre 8 zeros -- un zero qui se lit comme une mesure.
    """
    pure = str(unit_id).split(":")[0]
    meta, dyn = [], []
    for name, key, primary in summon_declaring_abilities(pure):
        a = G.ability(name) or {}
        variables = a.get("variables") or {}
        lues = {}
        for field, key_primary, key_secondary in SUMMON_STAT_VARS:
            vk = key_primary if primary else key_secondary
            if variables.get(vk):
                lues[field] = vk
        meta.append({"ability": name, "constant": key, "primary": primary, "variables": lues})
    for name, key, ordinal in spawn_declaring_abilities(pure):
        a = G.ability(name) or {}
        variables = a.get("variables") or {}
        smn = {f: dynamic_member_name(b_smn, ordinal) for f, b_smn, _b_spw in SPAWN_STAT_BASES
               if variables.get(dynamic_member_name(b_smn, ordinal))}
        spw = {f: dynamic_member_name(b_spw, ordinal) for f, _b_smn, b_spw in SPAWN_STAT_BASES
               if variables.get(dynamic_member_name(b_spw, ordinal))}
        dyn.append({"ability": name, "constant": key, "ordinal": ordinal,
                    "summonVariables": smn, "spawnVariables": spw})
    if not meta and not dyn:
        verdict = "orphelin"
    elif any(m["variables"] for m in meta):
        verdict = "meta"
    elif any(d["summonVariables"] or d["spawnVariables"] for d in dyn):
        verdict = "dynamic-only"
    else:
        verdict = "zero"
    return {"unitId": pure, "meta": meta, "dynamic": dyn, "verdict": verdict}


def summon_stats(unit_id: str, ability_name: str | None = None,
                 ability_level: int = 50, multiplier_pct: int | None = None) -> dict:
    """Les 8 stats de combat qu'un summon recoit A SON SPAWN -- mirror de
    `IdunMetaLogic.UserProgress.UnitProgression$$GetSummonStats`.

    Une variable `summon*` NULLE ou ABSENTE laisse le champ a sa valeur de config (0 pour un
    summon) : c'est le `if (var != 0) champ = var` du decompile, pas un defaut invente.

    `multiplier_pct` s'applique aux SEULES variables listees en `variablesAffectedByRarityBonus`
    (`VariablesAffectedByUnitRarityMultiplier` cote BC) -- meme regle que
    `engine.entities.effects.magnitude.ability_var`. Defaut : le multiplicateur du porteur, inconnu
    ici, donc 100 (pas de scaling) tant que l'appelant n'en fournit pas.
    """
    cands = summon_declaring_abilities(unit_id)
    if ability_name is None:
        if not cands:
            # ⚠ Le message NOMME l'etage, il ne se contente pas de constater (#419-r1-tr12-r2-r1) :
            # `summon_spawn_regimes` distingue le summon ORPHELIN (aucune ability du gameconfig ne
            # le nomme, donc le natif lui-meme n'a rien a lui donner) de celui que seule la voie
            # DYNAMIQUE atteint (`unitId_3` .. `unitId_6`), qui n'est PAS un elargissement de
            # `GetSummonStats` mais un AUTRE etage.
            reg = summon_spawn_regimes(unit_id)
            if reg["verdict"] == "orphelin":
                raise KeyError(
                    f"{unit_id!r} est un summon ORPHELIN : AUCUNE ability du gameconfig ne le "
                    f"nomme, ni par les constantes fixes {[c[0] for c in SUMMON_ID_CONSTANTS]} "
                    f"(voie META `UnitProgression$$GetSummonStats`) ni par un ordinal dynamique "
                    f"`unitId`..`unitId_{DYNAMIC_ID_MAX_ORDINAL}` (voie BATAILLE "
                    f"`SpawnUnitOptions$$WithStatsFromConfig*`). Il n'y a pas de stats a mirrorer.")
            raise KeyError(
                f"{unit_id!r} n'est atteint par AUCUNE des constantes fixes "
                f"{[c[0] for c in SUMMON_ID_CONSTANTS]} que "
                f"`UnitProgression$$GetSummonStats` interroge -- il est declare par la voie "
                f"DYNAMIQUE : {[(d['ability'], d['constant']) for d in reg['dynamic']]}. Cette "
                f"voie lit un ORDINAL de behaviour, pas une constante "
                f"(`SpawnUnitOptions$$WithStatsFromConfig{{,2,3}}` / `$$WithStatsFromConfigSpawn`), "
                f"et une autre famille de variables : elargir `GetSummonStats` a ces constantes "
                f"rendrait 8 zeros. Recenser d'abord : `summon_spawn_regimes({unit_id!r})`.")
        if len(cands) > 1:
            # Un summon peut etre declare par PLUSIEURS abilities (`necroSmnSwarm` l'est par
            # `ScarabHive` ET `ScarabSummon`), et elles n'ont aucune raison de porter les memes
            # variables. Prendre le premier en silence choisirait a la place de l'appelant :
            # on ne le tolere que si le choix est SANS CONSEQUENCE, et on le MESURE.
            profils = {
                n: tuple(summon_stats(unit_id, n, ability_level, multiplier_pct)[f]
                         for f in COMBAT_STAT_FIELDS)
                for n, _k, _p in cands
            }
            if len(set(profils.values())) > 1:
                raise KeyError(
                    f"{unit_id!r} est declare par {len(cands)} abilities aux stats DIFFERENTES "
                    f"{ {n: v for n, v in profils.items()} } -- nommer `ability_name`")
        ability_name, _key, primary = cands[0]
    else:
        match = [c for c in cands if c[0] == ability_name]
        if not match:
            raise KeyError(f"{ability_name!r} ne declare pas {unit_id!r}")
        primary = match[0][2]
    a = G.ability(ability_name)
    if a is None:
        raise KeyError(f"ability {ability_name!r} absente du gameconfig")
    variables = a.get("variables") or {}
    scaled = set(a.get("variablesAffectedByRarityBonus") or [])
    mult = 100 if multiplier_pct is None else int(multiplier_pct)
    out = {f: 0 for f in COMBAT_STAT_FIELDS}
    for field, key_primary, key_secondary in SUMMON_STAT_VARS:
        key = key_primary if primary else key_secondary
        arr = variables.get(key)
        if not arr:
            continue                                    # variable absente -> champ inchange
        idx = max(0, min(_to_zero_based_index(max(1, int(ability_level))), len(arr) - 1))
        base = int(arr[idx])
        if base == 0:
            continue                                    # `if (var != 0)` du decompile
        out[field] = round(base * mult / 100) if (mult != 100 and key in scaled) else base
    out["_ability"] = ability_name
    out["_primary"] = primary
    return out


def explicit_stats(unit_id: str, level: int | None = None,
                   ability_name: str | None = None, ability_level: int = 50,
                   multiplier_pct: int | None = None,
                   allow_zero_profile: bool = False) -> dict:
    """Patch de champs `UnitConfiguration` a poser pour un porteur que la formule HEROS refuse.

    Rend `{"source": "npc"|"summon-spawn", "fields": {...}}`. Le `source` n'est pas cosmetique :
      * `npc`          = mirror du CATALOGUE (ce que le jeu ECRIT dans `BC.Units[]`) ;
      * `summon-spawn` = MONTAGE, il reproduit l'etat POST-SPAWN. Le jeu, lui, ecrit 0 (65/65).

    ⚠ REFUS DU PROFIL INTEGRALEMENT NUL (#419-r1-tr12-r2-r1). Un patch `summon-spawn` dont les
    8 stats valent 0 ne « reproduit » rien : il pose un porteur a **0 PV** que le RPC
    `explicitStats` ecrit sans broncher (`_normalize_and_extract_pool` ne leve que si AUCUNE entree
    n'est honoree -- une entree honoree A ZERO passe). C'est un echec RENDU, donc lu comme une
    mesure. MESURE du 2026-08-15 sur `t6dpr4k06g` : **4** des 65 summons sont dans ce cas
    (`astarSmnHaywireMine`, `blackSmnBloodletterHSE`, `genesSmnDecoy`, `thousSmnPinkHorrorHSE`), et
    le refus d'ambiguite ne les protegeait PAS -- `genesSmnDecoy` a **5** abilities declarantes dont
    les 5 profils sont nuls, donc tous EGAUX : l'accord y est degenere.

    La cause est toujours l'une des deux, et `summon_spawn_regimes` la nomme : soit l'ability
    declarante ne porte AUCUNE variable de stats (`HaywireMine`), soit le regime deduit de la
    CONSTANTE n'est pas celui que le behaviour passe a `SpawnUnitOptions$$WithStatsFromConfig*`
    (`SpiritualLeader` declare par `unitId_2` mais ne porte que les variables NUES).

    `allow_zero_profile=True` est l'echappatoire EXPLICITE : elle vaut pour un montage qui veut
    seulement amener le summon AU POOL (la formule heros le refuserait) et ne mesure pas ses stats.
    Elle est NOMMEE au site d'appel, jamais un defaut.
    """
    pure = str(unit_id).split(":")[0]
    gc = G.unit(pure)
    if gc is None:
        raise KeyError(f"{pure!r} absent du gameconfig")
    if gc.get("stats"):
        return {"source": "npc", "fields": npc_stats(unit_id, level)}
    st = summon_stats(unit_id, ability_name, ability_level, multiplier_pct)
    ability = st.pop("_ability")
    st.pop("_primary")
    zero = not any(st[f] for f in COMBAT_STAT_FIELDS)
    if zero and not allow_zero_profile:
        reg = summon_spawn_regimes(pure)
        raise ValueError(
            f"{unit_id!r} : le patch `summon-spawn` derive de {ability!r} est INTEGRALEMENT NUL "
            f"(8 stats a 0) -- il poserait un porteur a 0 PV, pas un etat post-spawn. "
            f"Recensement des voies : verdict={reg['verdict']!r} meta={reg['meta']!r} "
            f"dynamic={reg['dynamic']!r}. Nommer `ability_name` si une autre declarante porte les "
            f"variables, ou passer `allow_zero_profile=True` si le montage veut seulement amener "
            f"le summon AU POOL sans mesurer ses stats.")
    st["ActiveAbilityLevel"] = ability_level
    st["PassiveAbilityLevel"] = ability_level
    return {"source": "summon-spawn", "fields": st, "ability": ability,
            "zeroProfile": zero}


# Champs que le TEMOIN npc confronte : les 8 stats de combat + les champs de progression que
# `BattleConfigBuilder$$GetUnitConfiguration` derive de la meme ligne `stats[]`.
NPC_WITNESS_FIELDS = COMBAT_STAT_FIELDS + (
    "Rank", "StarLevel", "Level", "ActiveAbilityLevel", "PassiveAbilityLevel",
    "AbilityVariablesMultiplierPercentage",
)


def npc_entries_of(bc: dict) -> list[dict]:
    """Entrees de `BC.Units[]` dont l'id PUR est un `units.npc` du gameconfig."""
    npc = G._cfg()["units"]["npc"]
    return [u for u in (bc.get("Units") or [])
            if str(u.get("Id", "")).split(":")[0] in npc]


def npc_witness_diff(bc: dict) -> tuple[list[tuple[str, dict]], int]:
    """TEMOIN NON DEGENERE du chemin npc : confronte `npc_stats` aux entrees npc que LE JEU a
    ecrites dans le seed BC capture.

    Ce n'est pas un accord entre deux lectures de la meme table : le cote gauche est calcule
    depuis `units.npc[id].stats[]` du gameconfig VIVANT, le cote droit est ce que
    `Idun.Source.IdunBattle.View.BattleConfigBuilder$$GetUnitConfiguration` a produit en bataille
    reelle et que la capture a fige. Rend `([(unitId, {champ: (attendu, capture)})], n_divergences)`.
    """
    rows, div = [], 0
    for u in npc_entries_of(bc):
        got = npc_stats(u["Id"])
        bad = {f: (got.get(f), u.get(f)) for f in NPC_WITNESS_FIELDS if got.get(f) != u.get(f)}
        rows.append((u["Id"], bad))
        div += len(bad)
    return rows, div


def apply_explicit_stats(bc: dict, unit_id: str, **kw) -> dict:
    """Ecrit le patch d'`explicit_stats` dans l'entree `BC.Units[]` de `unit_id`. Rend le rapport.

    `RemainingHealth` suit `Health` (meme regle que `json-build.ts`, qui la reinitialise pour que
    l'unite spawne a PV pleins).
    """
    rep = explicit_stats(unit_id, **kw)
    for u in bc.get("Units") or []:
        if u.get("Id") == unit_id:
            u.update(rep["fields"])
            if "RemainingHealth" in u:
                u["RemainingHealth"] = rep["fields"].get("Health")
            return rep
    raise KeyError(f"{unit_id!r} absent de BC.Units -- l'injecter d'abord (augment/synthesize)")


# --------------------------------------------------------- 2e catalogue : BC.Abilities

def synthesize_ability(name: str) -> dict:
    """Entree `IdunBattle.Configuration.AbilityConfiguration` (JSON) pour une ability/trait.

    POURQUOI CE SECOND CATALOGUE EST OBLIGATOIRE : `BattleConfiguration.Abilities`
    (`AbilitiesConfiguration`, keye par NOM) porte les Variables/Constants que le behaviour lit a
    l'execution -- `IdunBattle.Configuration.AbilityConfiguration$$GetVariableForLevel` /
    `$$GetNumberConstant` / `$$GetStringConstant` / `$$GetDamageProfile`. Le seed BC capture ne
    contient QUE les abilities des unites de CETTE bataille (131 actives / 194 passives). Injecter
    l'entree Unit sans sa config d'ability donne un porteur qui EXISTE, se deploie, expose ses
    abilities au decisionView... et FAUTE au cast (config nulle -> acces natif invalide).

    Mapping mesure sur les 325 entrees du seed BC (0 divergence hors 2 cles a espace parasite) :
      Variables                              <- gameconfig variables (valeurs en CHAINES)
      Constants                              <- gameconfig constants (valeurs en CHAINES)
      AttackRangeType                        <- IdunBattle.Entities.Enum.AttackRangeType
      VariablesAffectedByUnitRarityMultiplier<- variablesAffectedByRarityBonus, NOMS -> ids
                                                `IdunBattle.Configuration.AbilityVariableType`
      TutorialAbilityBehaviours              <- {} (vide sur les 325)
    """
    g = G.ability(name)
    if g is None:
        raise KeyError(f"ability {name!r} absente de gameconfig units.abilities")
    return {
        # les cles du gameconfig portent parfois un espace parasite ("nrOfUnits ") que le jeu
        # trimme : 2 cas sur 325 (HarbingerOfDestruction, GrapnelLauncher).
        "Variables": {k.strip(): [str(x) for x in v]
                      for k, v in (g.get("variables") or {}).items()},
        "Constants": {k.strip(): str(v) for k, v in (g.get("constants") or {}).items()},
        "AttackRangeType": attack_range_type_id(g.get("attackRangeType")),
        "VariablesAffectedByUnitRarityMultiplier": [
            ability_variable_id(x) for x in (g.get("variablesAffectedByRarityBonus") or [])],
        "TutorialAbilityBehaviours": {},
    }


def _ability_names(unit_id: str) -> tuple[list, list]:
    """(actives, passives+traits) d'un unitId, tels que le peuplement de BC.Abilities les attend.

    Regle MESUREE sur le seed BC : `ActiveAbilities` == exactement l'union des `activeAbilities`
    des unites du catalogue (131/131, 0 manquant 0 en trop) ; `PassiveAbilities` contient l'union
    des `passiveAbilities` PLUS les traits qui ont une entree `units.abilities` -- les traits sans
    entree gameconfig (Ambush, PrioritisedEfficiency, CrushingStrike, ...) sont configures ailleurs
    par le moteur et ne sont jamais derivables d'ici.

    ⚠ LA CLE DE CHAQUE NOEUD EST TYPEE PAR SON ENUM, et le routage se fait donc PAR NOM comme dans
    `route_configured_abilities` (#894). Le natif lit ces deux dicts par
    `IdunBattle.Configuration.AbilitiesConfiguration$$GetActive(ActiveAbilityType)` et
    `$$GetPassive(TriggeredAbilityType)` -- ce sont des `Dictionary<<enum>, AbilityConfiguration>`,
    donc une cle qui ne parse pas fait LEVER `Newtonsoft.Json.Utilities.EnumUtils$$ParseEnum` a la
    relecture du BC (meme mecanique que `_traits`, d'ou « [error] initAndStart: system error »).
    TEMOIN, sur la capture ecrite PAR LE JEU (`data/seed-bc.json`) : `ActiveAbilities` = 131/131
    membres d'`ActiveAbilityType`, `PassiveAbilities` = 194/194 membres de `TriggeredAbilityType`,
    **0 cle hors enum**. Le temoin DISCRIMINE : sur le meme BC, `EnvironmentAbilities` en porte 135
    hors enum (`EnvStatBoost:Chaos`, ...) et `Traits` 3 -- ces deux noeuds-la sont keyes par une
    string libre. Sans ce routage, `ShroudPsalm` (un `ActiveAbilityType`, ecrit en
    `passiveAbilities`) atterrissait comme cle de `PassiveAbilities`.
    """
    gc = G.unit(unit_id.split(":")[0]) or {}
    active_names = list(gc.get("activeAbilities") or [])
    cand = list(active_names)
    cand += [n for n in (gc.get("passiveAbilities") or []) if G.ability(n) is not None]
    cand += [t for t in (gc.get("traits") or []) if G.ability(t) is not None]
    act_tab = enum_map("IdunBattle.Entities.Enum.ActiveAbilityType")
    tri_tab = enum_map("IdunBattle.Entities.Enum.TriggeredAbilityType")
    is_active = set(active_names)
    act, pas = [], []
    for n in cand:
        if n in is_active and n in act_tab:
            act.append(n)
        elif n in tri_tab:
            pas.append(n)
        # sinon : aucun des deux noeuds ne peut porter cette cle -- ne rien ecrire (le natif,
        # lui, n'aurait de toute facon monte aucune ability de ce nom).
    return act, pas


def augment(seed_bc: dict, unit_ids, rank: int = 17, ability_level: int = 50,
            ability_mult_pct: int | None = None) -> dict:
    """COPIE du seed BC dont `Units` ET `Abilities` portent en plus ce qu'il faut aux ids demandes.

    Dedupe par Id (mirror de l'OrderedSet de `BattleConfigBuilder$$AddSummonUnitConfigs`) :
    un id deja au catalogue est laisse tel quel. Les configs d'ability manquantes sont ajoutees
    MEME pour un unitId deja present (une ability peut manquer independamment).
    """
    out = copy.deepcopy(seed_bc)
    have = {u.get("Id") for u in out.get("Units") or []}
    node = out.setdefault("Abilities", {})
    act_node = node.setdefault("ActiveAbilities", {})
    pas_node = node.setdefault("PassiveAbilities", {})
    added, added_abilities, unresolved = [], [], []
    for uid in unit_ids:
        if uid not in have:
            out["Units"].append(synthesize(uid, rank, ability_level, ability_mult_pct))
            have.add(uid)
            added.append(uid)
        act, pas = _ability_names(uid)
        for names, target in ((act, act_node), (pas, pas_node)):
            for n in names:
                if n in target:
                    continue
                try:
                    target[n] = synthesize_ability(n)
                    added_abilities.append(n)
                except KeyError:
                    unresolved.append(n)
        # Traits sans config nulle part (ni gameconfig, ni noeud capture) : MARQUEURS PURS
        # (Hero, MachineOfWar, Mechanical, Resilient, ...). Absence NORMALE -- 30 des 54 traits
        # portes par les 175 unites capturees sont dans ce cas. Rendus a titre informatif.
        gc = G.unit(uid.split(":")[0]) or {}
        for t in (gc.get("traits") or []):
            if G.ability(t) is None and t not in pas_node:
                unresolved.append(t)
    return out, added, added_abilities, sorted(set(unresolved))


def write_augmented_seed_bc(out_path, unit_ids, *, seed_bc: dict | None = None,
                            rank: int = 17, ability_level: int = 50,
                            ability_mult_pct: int | None = None,
                            restrict_abilities: dict | None = None):
    """POINT D'ENTREE des tests/probes qui ont besoin d'un porteur hors seed BC.

    Ecrit en `out_path` une COPIE du seed BC augmentee de `unit_ids` -- bloc `Units` **ET** configs
    `Abilities` (cf. `augment`). Rend `(Path, unites ajoutees, configs d'ability ajoutees)`.
    Le seed BC PARTAGE n'est jamais touche.

    NE JAMAIS RE-CLONER UN BLOC UNIT A LA MAIN. Le motif « `copy.deepcopy` d'une entree `Units`
    existante + reecriture des ids » produit un porteur qui se deploie, expose ses abilities au
    `decisionView`... et FAUTE au cast : `BattleConfiguration.Abilities` du seed capture ne contient
    QUE les abilities des unites de CETTE bataille, donc
    `IdunBattle.Configuration.AbilityConfiguration$$GetVariableForLevel` s'execute sur une config
    nulle et l'appelant rend « system error ». MESURE #226 (bloodTerminator / SavageEchoes 1230,
    board MC1_67, seed 777) -- meme bloc Unit, seules les configs changent :
        bloc Unit clone, 0 config      -> cast ok=False errors=['system error']
        bloc Unit clone + les configs  -> cast ok=True  hits=[3825, 3598, 3975, 3445]
        `write_augmented_seed_bc`      -> cast ok=True  hits=[3825, 3598, 3975, 3445]  (bit-identique)
    Ce « system error » avait ete impute au RANG du porteur puis a des arrays de variables « non
    materialises hors progression roster » : les deux diagnostics sont FAUX.

    `restrict_abilities` = `{unit_id: (actives, passives)}` -- ids d'ability a GARDER sur l'entree
    `Units` quand on veut ISOLER une ability (ex. tester SavageEchoes sans la passive RedRampage).
    Les CONFIGS restent toutes posees : une config qu'aucune unite ne porte est inerte.
    """
    seed = seed_bc if seed_bc is not None else _load_seed(None)
    bc, added, added_ab, _unresolved = augment(seed, unit_ids, rank, ability_level,
                                               ability_mult_pct)
    for uid, keep in (restrict_abilities or {}).items():
        act, pas = keep
        for u in bc["Units"]:
            if u.get("Id") == uid:
                u["ActiveAbilities"] = list(act)
                u["PassiveAbilities"] = list(pas)
                # #448-r3-r1-r1 : une RESTRICTION est une greffe en sens INVERSE -- le BC porte
                # MOINS que le gameconfig. Sans le canal `unitAbilityStates`, le port monte le kit
                # gameconfig COMPLET, c.-a-d. des abilities que la bataille n'a pas montees.
                declare_graft("restrict", uid, "actives=%s passives=%s" % (list(act), list(pas)))
    # SORTIE de run -> `logs/`, jamais `data/` (versionne, ENTREES seules) : #349.
    p = host_inputs.reject_data_output(out_path, "write_augmented_seed_bc(out_path=...)")
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(bc), encoding="utf-8")
    stamp_grafts(p)   # #448-r3-r1-r1-r1 : la marque voyage AVEC le fichier
    return p, added, added_ab


def missing_from_seed_bc(seed_bc: dict) -> list:
    """Ids `units.lineup` du gameconfig absents du catalogue capture (= porteurs bloques)."""
    have = {u["Id"].split(":")[0] for u in seed_bc.get("Units") or []}
    return sorted(k for k in G._index()["lineup"] if k not in have)


# ══ L'AXE AJOUT du catalogue capture (#254-bc-r1) ═════════════════════════════════════════════════
#
# CE QUE `STALE_UNIT_ENTRIES` NE COUVRE PAS. L'epingle voisine garde la derive des entrees
# PRESENTES dans la capture (une unite dont le gameconfig a change le kit). Une unite que le
# gameconfig a AJOUTEE depuis la capture n'y est pas du tout : elle releve de
# `missing_from_seed_bc`, qui ENUMERE sans comparer -- donc rien ne disait si l'ecart se CREUSAIT.
#
# ET IL S'EST CREUSE, EN SILENCE : la fiche du residu relevait **17** manquantes ; re-mesure le
# 2026-08-15 sur `t6dpr4k06g`, il y en a **21**. Le module lui-meme annonce encore « 17 » dans sa
# docstring d'en-tete. Personne n'a rien vu passer -- c'est exactement le regime que ce garde ferme.
#
# TROIS CATEGORIES, TROIS REGIMES DIFFERENTS -- et les confondre serait le vice du garde en SEUIL :
#
#   `lineup`  (127)  -> 21 absents. EPINGLES NOMINALEMENT ci-dessous, gardes dans les DEUX sens.
#                       Chacun est un porteur qui ne s'amene qu'en INJECTANT (case-92 Sec.6).
#   `summons` (65)   -> **0** absent. C'est un INVARIANT, pas un compte : il est ce qui rend la
#                       voie summon confrontable SANS injection (on spawne le summoner). Le jour ou
#                       le jeu en ajoute un, cette propriete tombe -- et il faut le savoir.
#   `npc`     (491)  -> 487 absents, et c'est NORMAL : la capture ne porte que les 4 npc de CETTE
#                       bataille, les autres s'injectent a la demande. Rapporte, jamais garde.
#
# CE GARDE N'EST PAS UN RATTRAPAGE. Comme #254-bc, il MESURE et il DIT ; injecter les 21 au seed
# partage changerait le pool spawnable de tous les tests live.
MISSING_LINEUP_ENTRIES = frozenset({
    "adeptCelestine", "astarCyrus", "astarLysander", "bloodTerminator", "darkaSternguard",
    "darkaStormSpeeder", "eldarLhykhis", "emperExultant", "emperFlawlessBlade", "emperLucius",
    "necroChronomancer", "necroReanimator", "spaceWolfPriest", "tauFarsight", "thousDaemonPrince",
    "thousSekhetar", "votanBeserk", "votanChampion", "votanIronmaster", "votanMemnyr", "votanUthar",
})


def catalog_gap(seed_bc: dict) -> dict:
    """`{kind: {"total": n, "missing": [...]}}` -- ce que le gameconfig VIVANT porte et que la
    capture n'a pas, ventile par categorie d'unite. Pendant de `stale_unit_entries` sur l'axe AJOUT.
    """
    have = {u["Id"].split(":")[0] for u in seed_bc.get("Units") or []}
    idx = G._index()
    out = {}
    for kind in ("lineup", "npc", "summons"):
        table = idx.get(kind) or {}
        out[kind] = {"total": len(table),
                     "missing": sorted(k for k in table if k not in have)}
    return out


def catalog_gap_report(seed_bc: dict) -> str | None:
    """Une ligne ASCII decrivant l'ecart d'AJOUT, ou `None` s'il est exactement celui qui est
    epingle. Les entrees hors `MISSING_LINEUP_ENTRIES` sont marquees, dans les DEUX sens.
    """
    gap = catalog_gap(seed_bc)
    lineup = set(gap["lineup"]["missing"])
    neuves = sorted(lineup - MISSING_LINEUP_ENTRIES)
    injectees = sorted(MISSING_LINEUP_ENTRIES - lineup)
    smn = gap["summons"]["missing"]
    if not neuves and not injectees and not smn:
        return None
    parts = []
    if neuves:
        parts.append("lineup NEUVES hors epingle (%d) : %s" % (len(neuves), ",".join(neuves)))
    if injectees:
        parts.append("lineup epinglees mais PRESENTES (%d) : %s"
                     % (len(injectees), ",".join(injectees)))
    if smn:
        parts.append("SUMMONS absents du catalogue (%d) : %s -- la voie summon n'est plus "
                     "confrontable sans injection pour eux" % (len(smn), ",".join(smn)))
    return ("ecart d'AJOUT catalogue<-gameconfig (#254-bc-r1) : " + " | ".join(parts))


# --------------------------------------------------------- 3e catalogue : la RELIQUE (#237)
#
# ETAT 2 de la gate de confrontabilite (« porteur au pool, relique NON equipee ») : 52 des 56
# unites eligibles du seed BC arrivent en bataille SANS leur relique. Le montage qui les equipe
# tient en TROIS ecritures, et il faut les TROIS -- chacune a son verrou natif :
#
#   1. `BC.Units[].TertiaryAbility` = id `TriggeredAbilityType`.
#      Lu par `IdunBattle.Entities.Factories.UnitFactory$$AddConfiguredAbilities` : quand le
#      `Nullable` a une valeur, l'ability entre par
#      `IdunBattle.Entities.Components.TriggeredAbilityComponent$$TryAdd(id, tertiaryState, 3)`
#      (le `3` = hierarchie Tertiary ; les passives entrent avec `2`). Champ nul = rien ne se
#      passe, SANS erreur : le montage se lit comme un succes.
#
#   2. `BC.Abilities.PassiveAbilities[<nom>]` = la config de l'ability.
#      Le seed BC ne porte que les abilities des unites de CETTE bataille : sur les 32 abilities
#      de relique du gameconfig, 3 SEULEMENT y sont (celles equipees au seed). Sans elle,
#      `AbilitiesDatabase.GetConfig` rend une config NON NULLE MAIS VIDE, et
#      `IdunBattle.Configuration.AbilityConfiguration$$GetVariableForLevel` n'y trouve aucun
#      tableau : le noeud DSL du behaviour (`IdunBattle.Entities.Formulas.ConfigAmount$$Calculate`)
#      l'appelle avec `fallbackToDefault = false`, donc il LEVE -> « system error » au cast.
#      MESURE : la relique est bien montee, mais `extraCritDmg` rend 0 au lieu de 749.
#      Meme verrou, meme parade que #226 : c'est `synthesize_ability` qui la produit.
#      NB `BC.Abilities` traverse `buildNormalizedBC` INTACT (le RPC ne touche que `Units`,
#      `Board`, `SpawnPointSetIndex`) -- cette ecriture-la n'a donc pas d'ordre impose.
#
#   3. `BC.Units[].TertiaryAbilityLevel` >= 1.  <-- LE VERROU QUI N'AVAIT PAS DE NOM
#      `IdunBattle.Configuration.AbilityConfiguration$$TryGetVariableArrayForLevel` -- le foyer
#      UNIQUE par lequel passent `GetVariableForLevel`, `TryGetVariableForLevel`,
#      `GetVariableArrayForLevel` et `GetAllVariablesForLevel` -- convertit le niveau par
#      `Idun.Shared.Level$$ToZeroBasedIndex`, qui LEVE `InvalidOperationException` des que
#      `level <= 0`. Or une entree `Units` sans relique porte `TertiaryAbilityLevel = 0` (les
#      171 du seed), et `synthesize` fait pareil : poser la relique SANS le niveau donne une
#      unite qui se deploie puis FAUTE a la premiere lecture de variable.
#      Borne HAUTE : il n'y en a pas. Le meme foyer CLAMPE (`idx >= len` -> `len - 1`), donc
#      `TertiaryAbilityLevel = 50` (ce qu'ecrit `buildNormalizedBC`) sur une ability de relique
#      a 10 paliers rend le palier 10. Pas d'erreur -- mais pas le niveau demande non plus.

def relic_items() -> dict:
    """`{itemId: {ability, allowedUnits, levels, rarity}}` des reliques du gameconfig.

    Une relique = une entree `items[*]` qui porte un `abilityId`. Le champ `allowedUnits` dit
    quels heros peuvent l'equiper -- c'est l'etat JOUEUR, pas une gate de bataille : le natif
    cote combat ne le relit jamais (`AddConfiguredAbilities` ne connait que le champ du BC).
    On s'en sert pour REFUSER un montage incoherent, pas parce que le moteur l'exigerait.
    """
    out = {}
    for item_id, it in (G._cfg().get("items") or {}).items():
        aid = it.get("abilityId")
        if not aid:
            continue
        out[item_id] = {
            "ability": aid,
            "allowedUnits": list(it.get("allowedUnits") or []),
            "levels": len(it.get("levels") or []),
            "rarity": it.get("rarity"),
        }
    return out


def relic_carriers(ability_name: str) -> list:
    """unitIds autorises a equiper la relique qui porte `ability_name` (union des items)."""
    out: set = set()
    for meta in relic_items().values():
        if meta["ability"] == ability_name:
            out.update(meta["allowedUnits"])
    return sorted(out)


def ability_level_count(ability_name: str) -> int:
    """Nombre de paliers de la plus longue variable de l'ability (0 si aucune variable).

    Sert a NOMMER la borne au-dela de laquelle `TryGetVariableArrayForLevel` clampe -- pas a
    refuser un niveau : le natif ne refuse rien par le haut.
    """
    g = G.ability(ability_name) or {}
    lens = [len(v) for v in (g.get("variables") or {}).values() if isinstance(v, list)]
    return max(lens) if lens else 0


def equip_relic(bc: dict, unit_id: str, ability_name: str, level: int = 1,
                *, allow_unlisted: bool = False) -> dict:
    """EQUIPE une relique a `unit_id` DANS `bc` (mute en place). Rend un rapport.

    Les trois ecritures du bloc ci-dessus, faites ensemble -- c'est le point : les separer est
    exactement ce qui produit un montage muet (rien ne se passe) ou un « system error ».

    `level` DOIT etre >= 1 (`Idun.Shared.Level$$ToZeroBasedIndex` leve sinon). Un niveau
    au-dela des paliers de l'ability est ACCEPTE et signale : le natif le clampe.
    """
    if level < 1:
        raise ValueError(
            f"TertiaryAbilityLevel={level} : le natif exige >= 1 "
            f"(Idun.Shared.Level$$ToZeroBasedIndex leve InvalidOperationException sur <= 0)")
    carriers = relic_carriers(ability_name)
    if carriers and unit_id.split(":")[0] not in carriers and not allow_unlisted:
        raise ValueError(
            f"{unit_id!r} n'est pas dans allowedUnits de la relique {ability_name!r} "
            f"({carriers}). Passer allow_unlisted=True pour GREFFER quand meme.")
    aid = triggered_ability_id(ability_name)
    hits = [u for u in (bc.get("Units") or []) if u.get("Id") == unit_id]
    if not hits:
        raise KeyError(f"{unit_id!r} absent de BC.Units -- injecter d'abord le porteur "
                       f"(write_augmented_seed_bc)")
    node = bc.setdefault("Abilities", {}).setdefault("PassiveAbilities", {})
    config_added = False
    if ability_name not in node:
        node[ability_name] = synthesize_ability(ability_name)
        config_added = True
    for u in hits:
        u["TertiaryAbility"] = aid
        u["TertiaryAbilityLevel"] = level
    declare_graft("relic", unit_id, ability_name)          # #448-r3-r1-r1, cf. `declare_graft`
    n_lvl = ability_level_count(ability_name)
    return {
        "unitId": unit_id, "ability": ability_name, "abilityId": aid,
        "level": level, "levelsAvailable": n_lvl,
        "clamped": bool(n_lvl and level > n_lvl),
        "configAdded": config_added, "unitsPatched": len(hits),
        "allowedUnits": carriers,
    }


def unequip_relic(bc: dict, unit_id: str) -> dict:
    """DESEQUIPE la relique de `unit_id` DANS `bc` (mute en place). Rend un rapport.

    Pendant exact d'`equip_relic`, et pour la raison SYMETRIQUE : **QUATRE unites du seed portent
    une `TertiaryAbility` sans que personne l'ait demandee** (`admecMarshall` et `admecRuststalker`
    partagent `KardiocoreGalvanus` 1457, `necroSpyder` a `NetherRealmCasket` 1462, `orksRuntherd`
    a **`SupaCyborkBody` 1475** -- et surtout PAS `MastersOfManoeuvre`, ce que #477-r31 avait ecrit
    a tort : `1475` n'a AUCUN `*NonOwnerPlaybook`, donc `orksRuntherd` n'arme rien). Un montage qui
    spawne l'une d'elles herite donc de sa relique -- et une
    relique porte souvent un `*NonOwnerPlaybook`, c.-a-d. un terme de tuile sur les VOISINS de son
    porteur, pas sur lui. Mesure #477-r31 : `admecMarshall` pose ainsi `+20` sur ses tuiles
    adjacentes (`KardiocoreGalvanus_AdjacentFriendly`) des que le mover est Mechanical -- soit
    exactement le meme profil que le terme mesure, sur exactement les memes tuiles.

    L'ecriture est SYMETRIQUE des deux du montage (`TertiaryAbility` + `TertiaryAbilityLevel`) : le
    niveau retombe a `0` = « verrouille » (`Idun.Shared.Level$$CreateValidOrLockedLevel`), ce que
    porte toute entree sans relique. La config d'ability laissee dans `BC.Abilities.PassiveAbilities`
    est INOFFENSIVE (elle n'est lue que si une unite la reference) et n'est donc pas retiree.

    `rien_a_faire=True` quand l'unite n'en portait pas : desequiper est IDEMPOTENT, mais un
    montage qui croit avoir retire une relique inexistante doit pouvoir le lire."""
    hits = [u for u in (bc.get("Units") or []) if u.get("Id") == unit_id]
    if not hits:
        raise KeyError(f"{unit_id!r} absent de BC.Units")
    before = [u.get("TertiaryAbility") for u in hits]
    for u in hits:
        u["TertiaryAbility"] = None
        u["TertiaryAbilityLevel"] = 0
    return {"unitId": unit_id, "unitsPatched": len(hits), "tertiaryBefore": before,
            "rien_a_faire": not any(before)}


def parse_relic_spec(spec: str) -> tuple[str, str, int]:
    """`'unitId:AbilityName[:level]'` -> `(unitId, ability, level)`. Niveau par defaut 1."""
    parts = [p.strip() for p in spec.split(":")]
    if len(parts) == 2:
        uid, ability = parts
        level = 1
    elif len(parts) == 3:
        uid, ability, lvl = parts
        level = int(lvl)
    else:
        raise ValueError(f"spec relique invalide {spec!r} -- attendu 'unitId:Ability[:level]'")
    if not uid or not ability:
        raise ValueError(f"spec relique invalide {spec!r} -- attendu 'unitId:Ability[:level]'")
    return uid, ability, level


def write_relic_seed_bc(out_path, specs, *, seed_bc: dict | None = None,
                        rank: int = 17, ability_level: int = 50,
                        allow_unlisted: bool = False):
    """FIXTURE : ecrit un seed BC ou chaque `spec` equipe sa relique. Rend `(Path, rapports)`.

    `specs` = iterable de `'unitId:AbilityName[:level]'` (ou de tuples deja parses). Le porteur
    est injecte au catalogue s'il en manque (`augment`), puis equipe (`equip_relic`).

    ⚠ ORDRE ET NIVEAU. Ce fichier est un seed BC, donc il passe ENSUITE par `buildNormalizedBC`,
    qui REECRIT `TertiaryAbilityLevel = targetAbilityLevel` (50) des que `TertiaryAbility` est
    non nul (`frida/hooks/features/normalize-bc/json-build.ts`). Le niveau ecrit ici n'est donc
    PAS celui qui arrive en bataille par cette voie : c'est 50, que le natif clampe au dernier
    palier. Pour un niveau EXACT, patcher le BC NORMALISE (`rl_duel build --equip-relic`, qui
    re-pose le couple apres la normalisation).
    """
    parsed = [parse_relic_spec(s) if isinstance(s, str) else tuple(s) for s in specs]
    seed = seed_bc if seed_bc is not None else _load_seed(None)
    bc, _added, _added_ab, _unres = augment(seed, [u for u, _a, _l in parsed], rank,
                                            ability_level)
    reports = [equip_relic(bc, uid, ability, lvl, allow_unlisted=allow_unlisted)
               for uid, ability, lvl in parsed]
    p = host_inputs.reject_data_output(out_path, "write_relic_seed_bc(out_path=...)")
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(bc), encoding="utf-8")
    stamp_grafts(p)   # #448-r3-r1-r1-r1 : la marque voyage AVEC le fichier
    return p, reports


# ------------------------------------------------- 4e catalogue : la MYTHIQUE de MoW (#999)
#
# CE QUI A ETE ETABLI, ET QUI N'ETAIT ECRIT NULLE PART. Le depot documentait le montage d'une
# RELIQUE (bloc #237 ci-dessus) et recensait 11 `mythicAbilities` comme une voie d'ATTRIBUTION
# (`unit_map.py`, case-323 §2), mais AUCUNE recette ne disait comment en amener une en bataille.
# La reponse tient en une phrase : **il n'y a PAS de voie mythique cote BATAILLE**. La mythique
# emprunte la voie TERTIAIRE, celle de la relique, au meme champ et avec les memes trois verrous.
#
# LA LECTURE QUI LE PROUVE -- `IdunMetaLogic.UserProgress.TertiaryAbilities$$GetTertiaryAbility`.
# Ce foyer (cote META, celui qui REMPLIT `BC.Units[].TertiaryAbility`) branche sur un unique test
# « ce porteur est-il une Machine of War ? » :
#
#     if (<test MoW>)  ->  GetMythicAbilityForMachineOfWar(progression, unitId, progressionData)
#     else             ->  <chemin RELIQUE : lit l'item equipe, progressionData+0x18>
#
# et **les DEUX branches ecrivent le MEME `Nullable` de retour**, celui qui devient
# `TertiaryAbility`. Le pendant du niveau, `TertiaryAbilities$$GetTertiaryAbilityLevelFromProgression
# Data`, a EXACTEMENT la meme forme : meme test, `Idun.Shared.Level$$.ctor(1)` du cote mythique,
# `GetAbilityLevel(<item>)` du cote relique. Cote BATAILLE, enfin,
# `IdunBattle.Entities.Factories.UnitFactory$$AddConfiguredAbilities` ne connait que TROIS voies --
# actives (liste), passives (dictionnaire), et **une seule tertiaire** (`Nullable`, `TryAdd(id,
# tertiaryAbilityState, 3)`). Aucune quatrieme. Le natif de combat ne sait donc PAS, et n'a aucun
# moyen de savoir, si la tertiaire qu'il monte vient d'une relique ou d'une mythique.
#
# CE QUI CHANGE MALGRE TOUT, ET POURQUOI CETTE FONCTION EXISTE AU LIEU D'UN `allow_unlisted=True` :
# la GARDE. `relic_carriers` derive de `items[*].allowedUnits` et rend **[] pour les 11 mythiques**
# (mesure : `probe_M_mythic_config.py` etage 2) -- donc `equip_relic` accepterait n'importe quel
# couple sans rien verifier, la garde etant desarmee par son propre `if carriers and ...`. La
# mythique a sa PROPRE source d'attribution, `units.<kind>.<id>.mythicAbilities`, et c'est elle qui
# doit refuser un montage incoherent. Une garde qui ne garde rien est pire que pas de garde.
#
# LES TROIS ECRITURES SONT LES MEMES, ET LES MEMES DEUX ECHOUENT EN SILENCE :
#   1. `BC.Units[].TertiaryAbility` = id `TriggeredAbilityType` (les 11 mythiques en sont, 11/11) ;
#   2. `BC.Abilities.PassiveAbilities[<nom>]` = la config -- **les 11 sont absentes du seed BC**
#      (mesure : `probe_M_mythic_seed.py` etage 3, `PassiveAbilities` = 194 entrees, 0 mythique),
#      donc cette ecriture-la n'est JAMAIS optionnelle pour une mythique, contrairement aux 3
#      reliques deja equipees au seed ;
#   3. `TertiaryAbilityLevel >= 1` (`Idun.Shared.Level$$ToZeroBasedIndex` leve sur <= 0).
#      Les 11 mythiques ont **4 paliers** chacune (et non 10 comme les reliques) : un niveau 50,
#      ce qu'ecrit `buildNormalizedBC`, est donc clampe au palier 4 par
#      `IdunBattle.Configuration.AbilityConfiguration$$TryGetVariableArrayForLevel`.
#
# LE PORTEUR. Les 11 sont portees par un couple (MoW `lineup`, MoW `npc`) -- 22 unites, 11
# abilities. Le `lineup` est le porteur legitime ; plusieurs sont HORS du pool du seed BC et
# exigent donc l'injection catalogue (`augment`) AVANT le montage, comme un heros hors pool.

def mythic_carriers(ability_name: str) -> list:
    """unitIds dont le gameconfig accorde `ability_name` par `mythicAbilities`.

    Pendant EXACT de `relic_carriers`, sur l'autre source d'attribution. Rend les DEUX membres du
    couple (MoW `lineup` et MoW `npc`) : c'est `buildNormalizedBC` qui refuse les npc, pas nous --
    les lister ici permet de dire au montage POURQUOI il refuse, au lieu de rendre une liste vide
    qui se lirait « cette ability n'a pas de porteur ».
    """
    out: set = set()
    for entries in (G._cfg().get("units") or {}).values():
        if not isinstance(entries, dict):
            continue
        for uid, u in entries.items():
            if isinstance(u, dict) and ability_name in (u.get("mythicAbilities") or []):
                out.add(uid)
    return sorted(out)


def mythic_abilities() -> dict:
    """`{abilityName: [unitIds]}` des mythiques du gameconfig (11 au build `rnca9r7q6c`).

    DERIVE, jamais code en dur : la liste bouge au changement de build, et une liste figee
    ecrirait un « 0 porteur » faux (exactement le vice de #323).
    """
    out: dict = {}
    for entries in (G._cfg().get("units") or {}).values():
        if not isinstance(entries, dict):
            continue
        for uid, u in entries.items():
            if not isinstance(u, dict):
                continue
            for name in (u.get("mythicAbilities") or []):
                out.setdefault(name, []).append(uid)
    return {k: sorted(v) for k, v in sorted(out.items())}


def equip_mythic(bc: dict, unit_id: str, ability_name: str, level: int = 1,
                 *, allow_unlisted: bool = False) -> dict:
    """DEBLOQUE la mythique d'une Machine of War DANS `bc` (mute en place). Rend un rapport.

    Les trois ecritures du bloc ci-dessus, faites ensemble. Cote BATAILLE c'est le montage de la
    relique -- meme champ `TertiaryAbility`, meme `TryAdd(..., 3)` -- parce que le natif n'a
    qu'UNE voie tertiaire (`UnitFactory$$AddConfiguredAbilities`). Ce qui differe est la GARDE :
    l'attribution vient de `units.<kind>.<id>.mythicAbilities`, pas d'`items[*].allowedUnits`.

    `level` DOIT etre >= 1 (`Idun.Shared.Level$$ToZeroBasedIndex` leve sinon). Un niveau au-dela
    des paliers (4 pour les 11 mythiques) est ACCEPTE et signale : le natif le clampe.
    """
    if level < 1:
        raise ValueError(
            f"TertiaryAbilityLevel={level} : le natif exige >= 1 "
            f"(Idun.Shared.Level$$ToZeroBasedIndex leve InvalidOperationException sur <= 0)")
    carriers = mythic_carriers(ability_name)
    if not carriers:
        raise ValueError(
            f"{ability_name!r} n'est accordee par AUCUNE unite via mythicAbilities. "
            f"Verifier le nom contre catalog_inject.mythic_abilities().")
    if unit_id.split(":")[0] not in carriers and not allow_unlisted:
        raise ValueError(
            f"{unit_id!r} ne porte pas la mythique {ability_name!r} "
            f"(porteurs : {carriers}). Passer allow_unlisted=True pour GREFFER quand meme.")
    aid = triggered_ability_id(ability_name)
    hits = [u for u in (bc.get("Units") or []) if u.get("Id") == unit_id]
    if not hits:
        raise KeyError(f"{unit_id!r} absent de BC.Units -- injecter d'abord le porteur "
                       f"(write_augmented_seed_bc) ; plusieurs MoW mythiques sont hors du pool")
    node = bc.setdefault("Abilities", {}).setdefault("PassiveAbilities", {})
    config_added = False
    if ability_name not in node:
        node[ability_name] = synthesize_ability(ability_name)
        config_added = True
    for u in hits:
        u["TertiaryAbility"] = aid
        u["TertiaryAbilityLevel"] = level
    declare_graft("mythic", unit_id, ability_name)          # meme raison qu'`equip_relic`
    n_lvl = ability_level_count(ability_name)
    return {
        "unitId": unit_id, "ability": ability_name, "abilityId": aid,
        "level": level, "levelsAvailable": n_lvl,
        "clamped": bool(n_lvl and level > n_lvl),
        "configAdded": config_added, "unitsPatched": len(hits),
        "carriers": carriers,
    }


def parse_mythic_spec(spec: str) -> tuple[str, str, int]:
    """`'unitId:AbilityName[:level]'` -> `(unitId, ability, level)`. Niveau par defaut 1.

    Accepte aussi `'unitId'` SEUL : la mythique du porteur est alors DERIVEE de son
    `mythicAbilities` -- il n'y en a jamais qu'une (mesure : 22 unites, 1 chacune), donc la
    nommer est une redondance qu'on n'impose pas a l'appelant.
    """
    parts = [p.strip() for p in spec.split(":")]
    if len(parts) == 1 and parts[0]:
        uid = parts[0]
        names = (G.unit(uid) or {}).get("mythicAbilities") or []
        if len(names) != 1:
            raise ValueError(
                f"spec mythique {spec!r} : {uid!r} porte {len(names)} mythique(s) {names} -- "
                f"nommer laquelle ('unitId:Ability[:level]')")
        return uid, names[0], 1
    if len(parts) == 2:
        uid, ability = parts
        level = 1
    elif len(parts) == 3:
        uid, ability, lvl = parts
        level = int(lvl)
    else:
        raise ValueError(f"spec mythique invalide {spec!r} -- attendu 'unitId[:Ability[:level]]'")
    if not uid or not ability:
        raise ValueError(f"spec mythique invalide {spec!r} -- attendu 'unitId[:Ability[:level]]'")
    return uid, ability, level


def write_mythic_seed_bc(out_path, specs, *, seed_bc: dict | None = None,
                         rank: int = 17, ability_level: int = 50,
                         allow_unlisted: bool = False):
    """FIXTURE : ecrit un seed BC ou chaque `spec` debloque sa mythique. Rend `(Path, rapports)`.

    `specs` = iterable de `'unitId[:AbilityName[:level]]'` (ou de tuples deja parses). Le porteur
    est injecte au catalogue s'il en manque (`augment`) -- ce qui est le cas COURANT ici, plusieurs
    MoW mythiques etant hors du pool du seed -- puis equipe (`equip_mythic`).

    ORDRE ET NIVEAU : identiques a `write_relic_seed_bc`. Ce fichier repasse par
    `buildNormalizedBC`, qui REECRIT `TertiaryAbilityLevel = targetAbilityLevel` (50) des que
    `TertiaryAbility` est non nul. Les mythiques n'ayant que 4 paliers, ce 50 est clampe au
    palier 4 -- le MAXIMUM, donc le regime le plus lisible. Pour un niveau EXACT, patcher le BC
    NORMALISE (`rl_duel build --equip-mythic`, qui re-pose le couple APRES la normalisation).
    """
    parsed = [parse_mythic_spec(s) if isinstance(s, str) else tuple(s) for s in specs]
    seed = seed_bc if seed_bc is not None else _load_seed(None)
    bc, _added, _added_ab, _unres = augment(seed, [u for u, _a, _l in parsed], rank,
                                            ability_level)
    reports = [equip_mythic(bc, uid, ability, lvl, allow_unlisted=allow_unlisted)
               for uid, ability, lvl in parsed]
    p = host_inputs.reject_data_output(out_path, "write_mythic_seed_bc(out_path=...)")
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(bc), encoding="utf-8")
    stamp_grafts(p)   # #448-r3-r1-r1-r1 : la marque voyage AVEC le fichier
    return p, reports


# --------------------------------------------- #366-r1 : GREFFER un PASSIF sur une unite du pool
#
# POURQUOI. `case-92` §5bis donne la recette de greffe pour une ability ACTIVE (remplacer
# `BC.Units[].ActiveAbilities`). Le pendant PASSIF est le seul chemin de confrontation d'une
# `TriggeredAbility` dont l'unique porteur est un **npc** : `buildNormalizedBC` refuse tout npc
# (`IdunMetaLogic.Formulas.StatsFormula$$StatsUsingProgressionIndexFor` -> `KeyNotFoundException`
# sur un lookup PAR UNITID qui ne couvre que le bucket `lineup`), et AUCUN enrichissement du seed
# BC ne peut lever ce refus. Premier cas : `EchoesFromTheWarp` (1219), passif unique de
# `thousNpc4Terminator` -- cf. `docs/rl/case-366r1-echoes-from-the-warp-revive.md`.
#
# DEUX ECRITURES, et l'une echoue EN SILENCE si on l'oublie :
#   1. `BC.Units[<greffon>].PassiveAbilities = [<TriggeredAbilityType>]` -- ce que
#      `IdunBattle.Entities.Factories.UnitFactory$$AddConfiguredAbilities` monte reellement ;
#   2. `BC.Abilities.PassiveAbilities[<nom>]` = la config de l'ability. Sans elle,
#      `AbilityConfiguration$$GetVariableForLevel`/`$$GetStringConstant` LEVENT -> « system error »
#      AU DEPLOIEMENT pour un passif (l'arbre DSL est bati a la creation de l'unite). C'est le
#      verrou #226/#254, et `refresh_ability_configs` ne le comble PAS tout seul : sa 2e boucle
#      derive les noms d'abilities de l'`Id` de l'unite au gameconfig, pas de la liste greffee.
#
# CE QUE LA GREFFE NE COUVRE PAS (a ecrire dans tout rapport) : les stats, traits et armes du VRAI
# porteur. Elle est donc legitime pour une mecanique qui ne les lit pas -- et quand elle lit une
# stat du caster, c'est celle du GREFFON qui sert, ce qui en fait un DISCRIMINANT (le montant
# attendu change avec le greffon) et non un confond.
#
# Le NIVEAU n'a pas ici le verrou de la relique : `buildNormalizedBC` pose
# `PassiveAbilityLevel = targetAbilityLevel` INCONDITIONNELLEMENT (json-build.ts), et ne touche
# JAMAIS la liste `PassiveAbilities` -- greffer avant ou apres la normalisation donne le meme
# niveau 50.

def graft_passive_ability(bc: dict, unit_id: str, ability_name: str,
                          *, replace: bool = True) -> dict:
    """GREFFE le passif `ability_name` sur `unit_id` DANS `bc` (mute en place). Rend un rapport.

    Les deux ecritures du bloc ci-dessus, faites ENSEMBLE. `replace=True` (defaut) REMPLACE la
    liste `PassiveAbilities` du greffon -- c'est ce qu'on veut pour isoler la mecanique mesuree ;
    `replace=False` l'AJOUTE aux passifs natifs du greffon.
    """
    aid = triggered_ability_id(ability_name)
    hits = [u for u in (bc.get("Units") or []) if u.get("Id") == unit_id]
    if not hits:
        raise KeyError(f"{unit_id!r} absent de BC.Units -- injecter d'abord le greffon "
                       f"(write_augmented_seed_bc)")
    node = bc.setdefault("Abilities", {}).setdefault("PassiveAbilities", {})
    config_added = False
    if ability_name not in node:
        node[ability_name] = synthesize_ability(ability_name)
        config_added = True
    before = []
    for u in hits:
        before = list(u.get("PassiveAbilities") or [])
        u["PassiveAbilities"] = [aid] if replace else sorted(set(before) | {aid})
    declare_graft("passive", unit_id, ability_name)        # #448-r3-r1-r1, cf. `declare_graft`
    return {"unitId": unit_id, "ability": ability_name, "abilityId": aid,
            "configAdded": config_added, "unitsPatched": len(hits),
            "passiveAbilitiesBefore": before,
            "passiveAbilitiesAfter": list(hits[0].get("PassiveAbilities") or [])}


# ------------------------------------ #447 : le pendant ACTIF de la meme greffe
#
# `case-92` §5bis DECRIT la greffe ACTIVE (recours 3) mais ne l'OUTILLE pas : seul le volet passif
# avait sa fonction. Les appelants la refaisaient a la main -- `u["ActiveAbilities"] = [aid]` en
# boucle sur `bc["Units"]` -- ou passaient par `write_augmented_seed_bc(restrict_abilities=...)`,
# qui RESTREINT (ecrase les deux listes) au lieu de greffer.
#
# MEMES DEUX ECRITURES que le volet passif, avec le catalogue et l'enum de l'autre famille :
#   1. `BC.Units[<greffon>].ActiveAbilities` <- `ActiveAbilityType` ;
#   2. `BC.Abilities.ActiveAbilities[<nom>]` = la config.
# Et le meme verrou natif en aval, qui vaut ici aussi :
# `IdunBattle.Core.Services.AttackQuery$$GetInvalidTargetReason` commence par
# `ActiveAbilityComponent$$GetOrNull(unit, abilityType)` et rend `broken(ValidRequest)` quand
# l'unite NE POSSEDE PAS l'ability -- c'est ce qui interdit d'interroger le natif sur une ability
# qu'on n'a pas greffee, et donc ce qui rend la greffe NECESSAIRE.
#
# CE QUE LA GREFFE COUVRE ICI : les `TargetingOptions` sont un champ de l'objet `AActiveAbility`
# resolu PAR TYPE (le natif les lit sur l'instance rendue par le service d'abilities, jamais sur
# l'unite) -- le masque exerce est donc EXACTEMENT celui du ctor de la classe visee. La limite
# habituelle (« ni les stats ni les traits ni les armes du vrai porteur ») ne mord que sur les
# regles qui les lisent ; pour un gate de cible arme par des bits de domaine, elle ne mord pas.

def graft_active_ability(bc: dict, unit_id: str, ability_name: str,
                         *, replace: bool = True) -> dict:
    """GREFFE l'ACTIVE `ability_name` sur `unit_id` DANS `bc` (mute en place). Rend un rapport.

    Pendant exact de `graft_passive_ability`, sur `ActiveAbilities` / `BC.Abilities.ActiveAbilities`
    et l'enum `ActiveAbilityType`. `replace=True` (defaut) REMPLACE la liste (isole la mecanique
    mesuree, et evite qu'une autre active du greffon reponde a la place) ; `replace=False` l'AJOUTE.
    """
    aid = active_ability_id(ability_name)
    hits = [u for u in (bc.get("Units") or []) if u.get("Id") == unit_id]
    if not hits:
        raise KeyError(f"{unit_id!r} absent de BC.Units -- injecter d'abord le greffon "
                       f"(write_augmented_seed_bc)")
    node = bc.setdefault("Abilities", {}).setdefault("ActiveAbilities", {})
    config_added = False
    if ability_name not in node:
        node[ability_name] = synthesize_ability(ability_name)
        config_added = True
    before = []
    for u in hits:
        before = list(u.get("ActiveAbilities") or [])
        u["ActiveAbilities"] = [aid] if replace else sorted(set(before) | {aid})
    declare_graft("active", unit_id, ability_name)         # #448-r3-r1-r1, cf. `declare_graft`
    return {"unitId": unit_id, "ability": ability_name, "abilityId": aid,
            "configAdded": config_added, "unitsPatched": len(hits),
            "activeAbilitiesBefore": before,
            "activeAbilitiesAfter": list(hits[0].get("ActiveAbilities") or [])}


# ---------------------------------- #419-r1-tr14-r5-r2-r1-r2-r1-r1-r4 : GREFFER un TRAIT
#
# POURQUOI. Certains regimes natifs ne sont gouvernes NI par une ability NI par une stat, mais par
# un TRAIT du caster -- et le gameconfig peut n'en avoir AUCUN porteur. Cas fondateur : le trait
# `Ranged` (0xb), que `IdunBattle.Entities.UnitExtensions$$IsRanged` lit en PREMIER
# (`HasTrait(unit, 0xb) || WeaponsComponent.HasRangedWeapon(unit)`) et qu'AUCUNE des 683 unites du
# gameconfig ne porte (constat #161). Sans porteur, `IsRanged` se reduit a « possede une arme a
# `Range` » -- et les deux termes deviennent INSEPARABLES, alors que le natif les distingue.
#
# C'est exactement ce qui verrouillait `#419-r1-tr14-r5-r2-r1-r2-r1-r1-r4` : le CLAMP DE MELEE de
# `IdunBattle.Core.Services.TargetingQuery$$GetRange` s'arme sur
# `RangedBoolExtensions.IsTrue(options.ForceMeleeTarget, caster)`, qui vaut `IfRangedCaster` pour
# l'attaque normale generique -- donc FAUX pour toute unite sans arme, c.-a-d. exactement celles
# dont la portee n'est pas observable. Poser le trait DISSOCIE les deux : sans arme (portee non
# observable) ET `IsRanged` vrai (clamp arme).
#
# UNE SEULE ECRITURE, ET LES DEUX MODELES LA VOIENT. `UnitConfiguration.Traits` est une
# `List<IdunBattle.Entities.Enum.UnitTrait>` (cf. `_traits`) que `buildNormalizedBC` LIT (detection
# MoW) mais n'ECRIT jamais -- l'injection survit donc a la normalisation. Le NATIF la lit par
# `HasTrait` sur l'entite ; le PORT la lit par `entity_trait_names(ctx, vid)`, dont le canal
# `ctx.traits` vient de `combatSnapshot.units[].traits`, lui-meme lu sur l'entite NATIVE. Substrat
# UNIQUE, donc aucune divergence de substrat a la `#419-r1-tr14-r5-r2-r1-r2-r1-r2`.
#
# L'ORDRE de la liste n'est pas signifiant (`HasTrait` est un `Contains`) : on ajoute a la fin,
# la ou `_traits_raw` place l'alliance en tete.

def add_unit_trait(bc: dict, unit_id: str, trait_name: str, *, replace: bool = False) -> dict:
    """AJOUTE le trait `trait_name` a `unit_id` DANS `bc` (mute en place). Rend un rapport.

    `trait_name` est confronte au vocabulaire de `UnitTrait` du build COURANT : un nom hors enum
    est INEXPRIMABLE dans ce champ et ferait lever `initAndStart` au deserialize (meme verrou que
    `_traits`, cf. sa docstring) -- on refuse donc TOT plutot que d'echouer en « system error ».
    `replace=True` REMPLACE la liste (utile pour RETIRER un trait) ; par defaut on AJOUTE.
    """
    members = unit_trait_members()
    if trait_name not in members:
        raise KeyError(f"{trait_name!r} n'est pas un membre de `UnitTrait` sur ce build "
                       f"-- inexprimable dans `UnitConfiguration.Traits`")
    hits = [u for u in (bc.get("Units") or []) if u.get("Id") == unit_id]
    if not hits:
        raise KeyError(f"{unit_id!r} absent de BC.Units -- injecter d'abord le porteur "
                       f"(write_augmented_seed_bc)")
    before = []
    for u in hits:
        before = list(u.get("Traits") or [])
        u["Traits"] = [trait_name] if replace else (
            before if trait_name in before else before + [trait_name])
    return {"unitId": unit_id, "trait": trait_name, "unitsPatched": len(hits),
            "traitsBefore": before, "traitsAfter": list(hits[0].get("Traits") or []),
            "alreadyPresent": trait_name in before}


def parse_trait_spec(spec: str) -> tuple[str, str]:
    """`'unitId:TraitName'` -> `(unitId, trait)`."""
    parts = [p.strip() for p in spec.split(":")]
    if len(parts) != 2 or not parts[0] or not parts[1]:
        raise ValueError(f"spec de trait invalide {spec!r} -- attendu 'unitId:TraitName'")
    return parts[0], parts[1]


def write_trait_seed_bc(out_path, specs, *, seed_bc: dict | None = None,
                        rank: int = 17, ability_level: int = 50, replace: bool = False):
    """FIXTURE : ecrit un seed BC ou chaque `spec` (`'unitId:TraitName'`) pose son trait.

    Rend `(Path, rapports)`. Le porteur est injecte au catalogue s'il en manque (`augment`), comme
    pour les greffes d'ability."""
    parsed = [parse_trait_spec(s) if isinstance(s, str) else tuple(s) for s in specs]
    seed = seed_bc if seed_bc is not None else _load_seed(None)
    bc, _added, _added_ab, _unres = augment(seed, [u for u, _t in parsed], rank, ability_level)
    reports = [add_unit_trait(bc, uid, trait, replace=replace) for uid, trait in parsed]
    p = host_inputs.reject_data_output(out_path, "write_trait_seed_bc(out_path=...)")
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(bc), encoding="utf-8")
    stamp_grafts(p)   # #448-r3-r1-r1-r1 : la marque voyage AVEC le fichier
    return p, reports


def parse_graft_spec(spec: str) -> tuple[str, str]:
    """`'unitId:AbilityName'` -> `(unitId, ability)`."""
    parts = [p.strip() for p in spec.split(":")]
    if len(parts) != 2 or not parts[0] or not parts[1]:
        raise ValueError(f"spec de greffe invalide {spec!r} -- attendu 'unitId:AbilityName'")
    return parts[0], parts[1]


def write_grafted_seed_bc(out_path, specs, *, seed_bc: dict | None = None,
                          rank: int = 17, ability_level: int = 50, replace: bool = True,
                          kind: str = "passive"):
    """FIXTURE : ecrit un seed BC ou chaque `spec` greffe son ability. Rend `(Path, rapports)`.

    `specs` = iterable de `'unitId:AbilityName'` (ou de tuples deja parses). Le greffon est
    injecte au catalogue s'il en manque (`augment`), puis greffe. `kind` choisit la famille :
    `"passive"` (defaut, `graft_passive_ability`) ou `"active"` (`graft_active_ability`).

    SURVIE AU RECHARGEMENT (#380) : `rl_collect_batch._load_seed_bc` rappelle
    `refresh_ability_configs`, dont la 1re boucle RE-SYNTHETISE les configs DEJA presentes. Celle
    qu'on vient de poser l'est donc aussi -- a l'identique, puisqu'elle sort de la MEME
    `synthesize_ability`. Rien n'est perdu, et `BC.Units[].PassiveAbilities` /
    `BC.Units[].ActiveAbilities` ne sont touches par aucune des deux boucles.
    """
    if kind not in ("passive", "active"):
        raise ValueError(f"kind invalide {kind!r} -- attendu 'passive' ou 'active'")
    graft = graft_active_ability if kind == "active" else graft_passive_ability
    parsed = [parse_graft_spec(s) if isinstance(s, str) else tuple(s) for s in specs]
    seed = seed_bc if seed_bc is not None else _load_seed(None)
    bc, _added, _added_ab, _unres = augment(seed, [u for u, _a in parsed], rank, ability_level)
    reports = [graft(bc, uid, ability, replace=replace) for uid, ability in parsed]
    p = host_inputs.reject_data_output(out_path, "write_grafted_seed_bc(out_path=...)")
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(bc), encoding="utf-8")
    stamp_grafts(p)   # #448-r3-r1-r1-r1 : la marque voyage AVEC le fichier
    return p, reports


# ------------------------------------------------- #369 : forcer un REGIME de variables d'ability
#
# POURQUOI CE MONTAGE EXISTE. Les deux formes de moyenne de la couche TRIGGERED (#350-r3b) ne
# divergent QUE lorsque `minDmg + maxDmg` vaut 3 mod 4 -- et au niveau 50 nominal AUCUNE des trois
# abilities concernees n'y est (`LightImUp` 831+1109 et 1496+1996, `MassiveScythingTalons`,
# `FuryOfTheAncients` : toutes ≡ 0, 1 ou 2). Un run live au niveau nominal ne conclurait donc RIEN.
# Atteindre le regime demande d'ECRIRE le couple dans le seed BC, exactement comme #237 ecrit une
# relique -- c'est le meme genre de montage, sur le meme catalogue.
#
# OU IL FAUT ECRIRE, lu au decompile : `IdunBattle.Configuration.AbilityConfiguration` porte
# `Variables[<nom>]` = un tableau PAR NIVEAU, et c'est ce que
# `IdunBattle.Configuration.AbilityConfiguration$$GetVariableForLevel` indexe apres conversion par
# `Idun.Shared.Level$$ToZeroBasedIndex` (clamp haut sur le dernier palier). Dans le BC c'est
# `BC.Abilities.PassiveAbilities[<ability>]["Variables"][<var>][level-1]`, en CHAINES.
#
# ⚠ LE MULTIPLICATEUR DE RARETE, ET POURQUOI ON LE NEUTRALISE. Une variable listee dans
# `VariablesAffectedByUnitRarityMultiplier` est lue `round(base * AbilityVariablesMultiplierPercentage
# / 100)` -- et `minDmg`/`maxDmg` y sont. Ecrire une valeur brute ne donnerait donc PAS la valeur
# effective, et la parite visee (le seul axe qui discrimine) serait perdue en silence. On retire donc
# ces deux variables de la liste : la valeur ecrite devient la valeur LUE, exactement.
# Ce que ce retrait NE change PAS : la STRUCTURE du noeud construit par
# `IdunBattle.Entities.Abilities.BaseTriggeredAbility$$MinMaxDamage{,Average}` ni le SLOT
# d'`IAmountFormula` que le playbook invoque -- c'est-a-dire precisement les deux etages que la
# mesure separe. Le montage deplace la VALEUR, pas la FORME.

def patch_ability_variables(bc: dict, ability_name: str, level: int, values: dict,
                            *, node: str = "PassiveAbilities",
                            neutralize_rarity: bool = True) -> dict:
    """Pose des variables d'ability A UN NIVEAU dans un BC. Rend le rapport de ce qui a ete ecrit.

    `values` = `{nom_de_variable: valeur_entiere}`. Le niveau est 1-based (mirror de
    `ToZeroBasedIndex`) et l'index est clampe au dernier palier, comme le natif.

    Leve si l'ability ou la variable est absente du BC : un patch qui ne s'applique pas doit
    ROUGIR, jamais rendre un BC inchange qu'on croirait patche (meme discipline que #237, ou deux
    des trois ecritures echouaient EN SILENCE).

    ⚠ CE PATCH EST INVISIBLE DU PORT (#366-r1-bcpatch-invisible). Il vit dans le BC, donc SEUL le
    natif le lit ; le moteur Python lit `gameconfig` (`engine/entities/effects/magnitude.py::
    ability_var`). Tant que l'effet vise n'est pas porte, la fixture passe pour une neutralisation ;
    le jour ou il l'est, le MEME geste devient une DESYNCHRONISATION -- mesure du 2026-08-01 :
    `InescapableAccuracy.extraCritDmg = 0` aurait rendu `1116` faux de 997 points. Croiser avant
    d'ecrire : `python probe_366_r1_bcpatch_port_blindspot.py`.
    """
    cfgs = (bc.get("Abilities") or {}).get(node) or {}
    cfg = cfgs.get(ability_name)
    if cfg is None:
        raise KeyError("ability %r absente de BC.Abilities.%s -- injecter sa config d'abord "
                       "(catalog_inject.augment)" % (ability_name, node))
    variables = cfg.get("Variables")
    if not isinstance(variables, dict):
        raise KeyError("BC.Abilities.%s[%r] n'a pas de noeud Variables" % (node, ability_name))
    written = {}
    for var, val in values.items():
        arr = variables.get(var)
        if not isinstance(arr, list) or not arr:
            raise KeyError("variable %r absente (ou vide) de %s[%r].Variables"
                           % (var, node, ability_name))
        idx = max(0, min((level - 1) if level and level > 0 else 0, len(arr) - 1))
        arr[idx] = str(int(val))
        written[var] = {"index": idx, "value": int(val), "levels": len(arr)}
    deaffected = []
    if neutralize_rarity:
        affected = cfg.get("VariablesAffectedByUnitRarityMultiplier")
        if isinstance(affected, list):
            drop = set()
            for var in values:
                try:
                    drop.add(ability_variable_id(var))
                except Exception:
                    continue
            if drop:
                keep = [x for x in affected if x not in drop]
                deaffected = [x for x in affected if x in drop]
                cfg["VariablesAffectedByUnitRarityMultiplier"] = keep
    return {"ability": ability_name, "node": node, "level": level,
            "written": written, "deaffected": deaffected,
            "rarity_neutralized": bool(deaffected)}


# ---------------------------------------------------------------- EPINGLAGE (#375)
#
# ⚠ LE PATCH DE VARIABLE NE SURVIVAIT PAS AU BUILD, ET C'EST SILENCIEUX.
# `rl_collect_batch._load_seed_bc` appelle `refresh_ability_configs` a CHAQUE chargement --
# y compris sur un seed BC CUSTOM. Le refresh remplace toute config qui differe du gameconfig
# vivant par `synthesize_ability(name)` : il ECRASE donc exactement les valeurs qu'une fixture
# vient d'y ecrire. Mesure du 2026-07-31 : `LightImUp.minDmg[49]` ecrit a `20000` sur disque,
# relu a `831` apres `_load_seed_bc` -- et `LightImUp` figure dans les « 4 rafraichies » a chaque
# build, patch ou pas. La fixture etait donc INERTE, et le regime discriminant jamais joue.
#
# Parade : un SIDECAR `<seed-bc>.pins.json` qui NOMME les configs deliberement patchees ; le
# loader les passe en `skip` au refresh. Deux proprietes voulues :
#   * l'epinglage est OPT-IN et NOMME (jamais une desactivation globale du rattrapage #254) ;
#   * la config epinglee est d'abord RE-SYNTHETISEE puis patchee, donc elle est fraiche PLUS le
#     patch -- on ne fige jamais une capture perimee, ce que #254 existe precisement pour eviter.
# Le sidecar vit HORS du BC : rien de non-jeu n'entre dans le payload envoye au runner.

# DEUXIEME FORME D'ECRASEMENT, MESUREE PAR #380 : ce n'est pas toujours une VALEUR qui est
# ecrasee -- c'est parfois une ABSENCE qui est COMBLEE. La 2e boucle de `refresh_ability_configs`
# balaie `bc["Units"]` et POSE toute config d'ability que le gameconfig attribue a une unite du
# catalogue. Une fixture dont le POINT EST l'absence d'une config voit donc son bras negatif
# NEUTRALISE, sans un mot -- exactement la meme signature que #375, sur l'axe oppose.
# MESURE du 2026-07-31 (`probe_380 --measure`) : `probe_226_seed_bc_ability_configs` bras A
# (« AUCUNE config d'ability posee, etat AVANT correctif ») repart du chargeur avec
# `ActiveAbilities/SavageEchoes` ET `PassiveAbilities/RedRampage` en place. Ses trois bras
# livrent alors la MEME chose au runner : la discrimination A KO / B OK / C OK a disparu.
# (Le verdict #226 lui-meme reste juste : il a ete mesure le 2026-07-29 a 00h38, et le rattrapage
#  #254 a ete pose a 19h17 le MEME jour -- 18 h plus tard. C'est le probe qui a cesse d'etre
#  reproductible, pas la conclusion qui a change.)
#
# Parade SYMETRIQUE de l'epingle, et de la meme nature : une cle `withheldAbilityConfigs` dans le
# MEME sidecar, OPT-IN et NOMMEE. Elle n'eteint rien globalement -- le filet #226 continue de
# couvrir toutes les autres abilities du meme BC. Une retenue CONTRADICTOIRE (la config est en
# fait presente dans le BC) LEVE, comme une epingle orpheline : une retenue qui ne retient rien
# est un montage faux, pas un no-op.

PINS_SUFFIX = ".pins.json"


def pins_path(seed_bc_path) -> Path:
    """Chemin du sidecar d'epinglage d'un seed BC custom."""
    return Path(str(seed_bc_path) + PINS_SUFFIX)


def _read_sidecar(seed_bc_path) -> dict:
    p = pins_path(seed_bc_path)
    if not p.is_file():
        return {}
    return json.loads(p.read_text(encoding="utf-8"))


def read_pins(seed_bc_path) -> list:
    """Les cles `"<node>/<ability>"` epinglees pour ce seed BC. `[]` si aucun sidecar."""
    data = _read_sidecar(seed_bc_path)
    if not data:
        return []
    pins = data.get("pinnedAbilityConfigs")
    if not isinstance(pins, list):
        raise ValueError("%s : cle 'pinnedAbilityConfigs' absente ou non-liste"
                         % pins_path(seed_bc_path))
    return [str(x) for x in pins]


def read_withheld(seed_bc_path) -> list:
    """Les cles `"<node>/<ability>"` dont l'ABSENCE est deliberee (#380). `[]` si aucun sidecar.

    Tolerante a la cle manquante : les sidecars ecrits avant #380 ne portent que les epingles.
    """
    data = _read_sidecar(seed_bc_path)
    if not data:
        return []
    w = data.get("withheldAbilityConfigs", [])
    if not isinstance(w, list):
        raise ValueError("%s : cle 'withheldAbilityConfigs' non-liste" % pins_path(seed_bc_path))
    return [str(x) for x in w]


def read_grafts(seed_bc_path) -> list:
    """Les greffes ESTAMPEES dans le sidecar de ce seed BC (#448-r3-r1-r1-r1). `[]` si aucune.

    C'est « faire porter la marque par le seed BC lui-meme », la piste que la fiche nomme en
    premier -- et c'est ce qui ferme le patron COMPLET : un processus greffe et ECRIT le fichier,
    un AUTRE le recoit par `--seed-bc` et n'a aucun moyen de savoir qu'il est greffe. Le registre
    par runner ne suffit pas seul, puisque le processus qui construit le runner peut n'avoir rien
    greffe lui-meme -- il ne fait que charger un BC deja greffe.

    Tolerante a la cle manquante : les sidecars ecrits avant ne portent que pins/withheld."""
    data = _read_sidecar(seed_bc_path)
    if not data:
        return []
    g = data.get("declaredGrafts", [])
    if not isinstance(g, list):
        raise ValueError("%s : cle 'declaredGrafts' non-liste" % pins_path(seed_bc_path))
    return [x for x in g if isinstance(x, dict)]


def stamp_grafts(seed_bc_path, grafts=None) -> Path | None:
    """ESTAMPE les greffes de ce processus dans le sidecar du seed BC ecrit.

    Lecture-modification-ecriture : les epingles (#375) et les retenues (#380) deja presentes sont
    PRESERVEES -- ce sidecar est partage par trois mecanismes et en ecraser un depuis l'autre
    ferait disparaitre un montage en silence, exactement le genre de panne que ces trois-la
    existent pour empecher.

    Rend `None` s'il n'y a RIEN a estamper : on ne cree pas un sidecar qui se lirait « mesure, et
    aucune greffe » alors que rien n'a ete monte."""
    items = list(_GRAFTS if grafts is None else grafts)
    if not items:
        return None
    p = pins_path(seed_bc_path)
    data = _read_sidecar(seed_bc_path) or {}
    data.setdefault("pinnedAbilityConfigs", [])
    data.setdefault("withheldAbilityConfigs", [])
    connues = {(g.get("kind"), g.get("unitId"), g.get("what"))
               for g in data.get("declaredGrafts", []) if isinstance(g, dict)}
    fusion = list(data.get("declaredGrafts") or [])
    for g in items:
        if (g.get("kind"), g.get("unitId"), g.get("what")) not in connues:
            connues.add((g.get("kind"), g.get("unitId"), g.get("what")))
            fusion.append(g)
    data["declaredGrafts"] = fusion
    try:
        p.write_text(json.dumps(data), encoding="utf-8")
    except OSError:
        return None
    return p


def redeclare_grafts_from(seed_bc_path) -> int:
    """RE-DECLARE dans CE processus les greffes estampees dans le sidecar. Rend le nombre ajoute.

    Appelee au chargement d'un seed BC custom (`_load_seed_bc`) : un processus qui recoit un BC
    deja greffe devient ainsi aussi informe que celui qui l'a greffe, sans avoir a le savoir. Les
    doublons exacts ne sont pas re-ajoutes -- greffer puis recharger son propre fichier ne doit pas
    gonfler le registre."""
    try:
        items = read_grafts(seed_bc_path)
    except ValueError:
        return 0
    connues = {(g.get("kind"), g.get("unitId"), g.get("what")) for g in _GRAFTS}
    n = 0
    for g in items:
        cle = (g.get("kind"), g.get("unitId"), g.get("what"))
        if cle not in connues:
            connues.add(cle)
            _GRAFTS.append({"kind": g.get("kind"), "unitId": g.get("unitId"),
                            "what": g.get("what")})
            n += 1
    return n


def write_pins(seed_bc_path, pins, withheld=()) -> Path:
    """Ecrit le sidecar. `pins` / `withheld` = iterables de `"<node>/<ability>"`.

    Les DEUX cles sont toujours ecrites (une liste vide reste une liste) : `read_pins` exige
    `pinnedAbilityConfigs`, et un sidecar qui ne porterait qu'une retenue la ferait lever.

    ⚠ Les greffes deja ESTAMPEES (#448-r3-r1-r1-r1) sont PRESERVEES. Le sidecar porte desormais
    trois mecanismes ; un ecrivain qui ecrase les deux autres ferait disparaitre un montage en
    silence -- precisement la panne que ces trois-la existent pour empecher.
    """
    p = pins_path(seed_bc_path)
    data = {"pinnedAbilityConfigs": sorted(set(pins)),
            "withheldAbilityConfigs": sorted(set(withheld))}
    deja = _read_sidecar(seed_bc_path) or {}
    if deja.get("declaredGrafts"):
        data["declaredGrafts"] = deja["declaredGrafts"]
    p.write_text(json.dumps(data), encoding="utf-8")
    return p


def write_variable_patched_seed_bc(out_path, patches, *, seed_bc: dict | None = None,
                                   unit_ids=(), rank: int = 17, ability_level: int = 50):
    """FIXTURE : ecrit un seed BC dont les variables d'ability demandees sont FORCEES.

    `patches` = iterable de `(ability_name, level, {var: value})`. `unit_ids` injecte au prealable
    les porteurs manquants (meme voie qu'une relique hors catalogue). Rend `(Path, rapports)`.

    Ecrit AUSSI le sidecar `<out_path>.pins.json` (#375) : sans lui le patch est ecrase par
    `refresh_ability_configs` au chargement, EN SILENCE. La config est re-synthetisee depuis le
    gameconfig vivant AVANT d'etre patchee -- on epingle du frais patche, jamais du perime.

    ⚠ ET C'EST EXACTEMENT CE QUI L'ARME COTE PORT (#366-r1-bcpatch-invisible) : le patch qui
    SURVIT est celui que le natif voit et que le moteur Python ne voit pas. Ne JAMAIS confronter
    une face PORT sur un seed BC produit ici sans avoir croise le couple patche avec les lectures
    du moteur -- `python probe_366_r1_bcpatch_port_blindspot.py` (cliquet, rc 0 attendu).
    """
    seed = seed_bc if seed_bc is not None else _load_seed(None)
    bc, _a, _b, _c = augment(seed, list(unit_ids), rank, ability_level)
    # Rattrapage #254 applique ICI, avant le patch : ce que l'on epingle est donc la config du
    # build COURANT, plus le patch -- et le `skip` du loader ne fige aucune capture perimee.
    refresh_ability_configs(bc)
    reports = [patch_ability_variables(bc, name, lvl, vals) for name, lvl, vals in patches]
    p = host_inputs.reject_data_output(out_path, "write_variable_patched_seed_bc(out_path=...)")
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(bc), encoding="utf-8")
    stamp_grafts(p)   # #448-r3-r1-r1-r1 : la marque voyage AVEC le fichier
    write_pins(p, [r["node"] + "/" + r["ability"] for r in reports])
    return p, reports


def relic_state_of_seed_bc(seed_bc: dict) -> dict:
    """Ventilation des TROIS etats de la gate « ability de relique » sur un BC donne.

    Rend `{equipped, eligible_no_relic, off_catalog}` -- `equipped` = les entrees `Units` qui
    portent deja `TertiaryAbility` ; `eligible_no_relic` = celles qu'un item relique autorise
    mais qui arrivent sans ; `off_catalog` = les porteurs autorises absents du catalogue.
    """
    have = {u.get("Id"): u for u in (seed_bc.get("Units") or [])}
    allowed: dict = {}
    for meta in relic_items().values():
        for uid in meta["allowedUnits"]:
            allowed.setdefault(uid, set()).add(meta["ability"])
    equipped, eligible, off = [], [], []
    for uid, abilities in sorted(allowed.items()):
        u = have.get(uid)
        if u is None:
            off.append(uid)
        elif u.get("TertiaryAbility"):
            equipped.append((uid, u["TertiaryAbility"], u.get("TertiaryAbilityLevel")))
        else:
            eligible.append((uid, sorted(abilities)))
    return {"equipped": equipped, "eligible_no_relic": eligible, "off_catalog": off}


# ------------------------------------------------- rafraichissement du 2e catalogue (#254)

def refresh_ability_configs(bc: dict, skip=(), withhold=()) -> tuple[list, list]:
    """RE-SYNTHETISE `BC.Abilities` depuis le gameconfig VIVANT, EN PLACE. Rend (rafraichies,
    ajoutees).

    `skip` (#375) = cles `"<node>/<ability>"` EPINGLEES : configs deliberement patchees par une
    fixture, que le rattrapage ne doit PAS ecraser. Opt-in et nomme -- jamais un interrupteur
    global. Cf. `write_variable_patched_seed_bc` / `read_pins`.

    `withhold` (#380) = cles `"<node>/<ability>"` dont l'ABSENCE est deliberee : la 2e boucle ne
    les pose pas. Meme discipline (opt-in, nomme) pour l'axe symetrique -- cf. `read_withheld`.

    POURQUOI (#254, MIGRATION DE BUILD). `data/seed-bc.json` est la capture d'UNE bataille, faite
    sur UN build ; `scripts/python/gameconfig.py`, lui, lit le fichier VIVANT de
    AppData/LocalLow/Snowprint, donc celui du build COURANT. Une mise a jour du jeu qui AJOUTE une
    variable ou une constante a une ability laisse la capture en arriere -- et le code natif NEUF la
    lit :

        `IdunBattle.Configuration.AbilityConfiguration$$GetStringConstant` fait un TryGetValue sur
        `Constants` (this+0x18) ; sur ECHEC il construit une `System.Exception` et la LEVE. Idem
        `$$GetNumberConstant` (qui delegue a GetStringConstant) et `$$GetVariableForLevel`.

    Une exception managee levee sous `invokeMethod` remonte cote Frida en « system error ». Selon
    l'endroit ou la cle est lue, la faute frappe soit le CAST, soit -- pour un PASSIF, dont l'arbre
    DSL est bati a la creation de l'unite -- le DEPLOIEMENT, donc `initAndStart` lui-meme.

    MESURE gqfc5mff6c -> rnca9r7q6c (2026-07-29), `probe_254_build_migration.py` :
      - `ShockAssault` (PASSIF de `ultraInceptorSgt`) gagne la constante `unitId=ultraSmnInceptor`,
        lue par `IdunBattleLogic.Entities.Abilities.Active.Loki.ShockAssaultAbility$$GetAffectedUnits`
        que `$$CreateTrigger` appelle a la construction du trigger
        -> tout `rl_duel build` dont un roster contient `ultraInceptorSgt` rendait
           « [error] initAndStart: system error ».
      - `ResurrectionOrb` (ACTIVE de `necroOverlord`) gagne la variable `hpPct` et la constante
        `maxSummons` ; `FearOfTheUnseen` (ACTIVE de `tyranDeathleaper`) gagne `initialCooldownTurns`
        -> ces deux-la se DEPLOIENT et fautent au CAST.
      Les 273 autres configs sont INCHANGEES : le refresh est un no-op mesure sur 273/277 entrees
      (`--validate` diffe champ a champ), il ne « reecrit » donc pas le catalogue, il le RATTRAPE.

    CE N'EST PAS UN HACK : `BC.Abilities` est construit par le jeu depuis SON gameconfig a chaque
    bataille. Re-synthetiser depuis le gameconfig courant, c'est refaire ce que le jeu fait --
    `synthesize_ability` en est le mirror, prouve par `--validate`.

    Les entrees dont `units.abilities` n'a AUCUN pendant (48 sur 325) sont des configs INTERNES au
    moteur (traits Ambush/PrioritisedEfficiency/..., abilities d'environnement) : non derivables,
    donc laissees telles quelles.
    """
    node = bc.setdefault("Abilities", {})
    act_node = node.setdefault("ActiveAbilities", {})
    pas_node = node.setdefault("PassiveAbilities", {})
    pinned = set(skip or ())
    refreshed, added = [], []
    for node_name, target in (("ActiveAbilities", act_node), ("PassiveAbilities", pas_node)):
        for name in list(target):
            if node_name + "/" + name in pinned:        # #375 : patch delibere, on n'ecrase pas
                continue
            if G.ability(name) is None:                 # config interne moteur : non derivable
                continue
            synth = synthesize_ability(name)
            if synth != target[name]:
                target[name] = synth
                refreshed.append(name)
    # Une ability AJOUTEE a une unite deja au catalogue n'a aucune config : meme faute, cause
    # symetrique. Mirror du peuplement de `BC.Abilities` (cf. `_ability_names`).
    held = set(withhold or ())
    for u in (bc.get("Units") or []):
        act, pas = _ability_names(u.get("Id") or "")
        for names, node_name, target in ((act, "ActiveAbilities", act_node),
                                         (pas, "PassiveAbilities", pas_node)):
            for n in names:
                if n in target:
                    continue
                if node_name + "/" + n in held:      # #380 : absence DELIBEREE, on ne comble pas
                    continue
                try:
                    target[n] = synthesize_ability(n)
                    added.append(n)
                except KeyError:
                    pass
    return sorted(set(refreshed)), sorted(set(added))


def ai_utilities_from_gameconfig() -> dict:
    """`BattleConfiguration.Utilities` synthetisee depuis le gameconfig VIVANT (`aiUtilities`).

    Mirror de `Idun.Source.IdunBattle.View.BattleConfigBuilder$$ParseAIUtilitiesConfiguration`
    (appelee par `...$$CreateBattleConfig`) : elle prend le dictionnaire `aiUtilities` du
    gameconfig, parse la cle EXTERIEURE en enum de jeu d'utilites (Default / MovementSuggestion),
    la cle INTERMEDIAIRE en `UtilityType` (ActiveAbilities, TriggeredAbilities, Elevation, ...) et
    recopie VERBATIM le dictionnaire `{nom: entier}` interieur. Les cles qui ne parsent pas sont
    IGNOREES avec un warning -- il n'y a aucune autre transformation : la table de la BC EST la
    table du gameconfig.
    """
    return copy.deepcopy(G._cfg().get("aiUtilities") or {})


def refresh_ai_utilities(bc: dict) -> tuple[list, list, list]:
    """RE-SYNTHETISE `BC.Utilities` depuis le gameconfig VIVANT, EN PLACE.
    Rend (ajoutees, changees, retirees) -- chaque element = "<set>/<categorie>/<cle>".

    POURQUOI (#27-4, MIGRATION DE BUILD -- pendant EXACT de `refresh_ability_configs`/#254 sur le
    3e catalogue). `data/seed-bc.json` est la capture d'UNE bataille faite sur UN build ; sa table
    `Utilities` est donc celle de CE build-la. Une mise a jour du jeu qui AJOUTE une ability ajoute
    aussi ses POIDS d'utilite -- et le playbook NEUF les lit :

        `IdunBattle.AI.Playbook.Playbooku003C__Il2CppFullySharedGenericTypeu003E$$GetUtilityValue`
        fait un `TryGetValue` sur le dict de la categorie ; sur ECHEC il LOGUE un warning et rend
        `Fix64(0)`.

    La degradation est donc SILENCIEUSE et PERMISSIVE : pas d'exception, pas de « system error » --
    le terme custom de l'ability neuve vaut simplement 0 cote NATIF comme cote moteur. Un port de
    ce terme serait alors INVALIDABLE (les deux bras d'un A/B rendraient la meme chose) et, pire,
    on conclurait a tort « le natif n'exerce pas cette branche ».

    MESURE gqfc5mff6c -> rnca9r7q6c (2026-07-30) : 16 cles AJOUTEES et 3 valeurs CHANGEES.
      - `Default/ActiveAbilities` +7 : HeavyWarpFlamer_LikesAdjacentEnemies=10,
        MassDriverAccelerator_AdjacentFriendly=5, ResurrectionOrb_LikesResurrection=90,
        ResurrectionOrb_LikesSummoning=10, TitanhammerSquad_{ChanceToUse=10,
        LikesTerminatorFriendsInRange=20, LikesToGoFirst=10} ;
      - `Default/TriggeredAbilities` +5 (EmpyricAmbush, IconOfObstinacy, ModifiedExoarmour,
        MyWillBeDoneOverlord, PropheticSentinel) et ~2 (KustomForceFieldReworked_
        LikesAdjacentFriends 0->10, Lakrimae_LikesNonMechanicalEnemies 0->5) ;
      - `Default/TriggeredAbilitiesNonOwner` +4 et ~1 (KustomForceFieldReworked_
        FriendsLikeToBeAdjacent 0->10).
      Les 54 categories et les 2 jeux sont sinon IDENTIQUES : aucune cle retiree.

    CE N'EST PAS UN HACK, c'est le meme argument que #254 : la BC construit sa table depuis SON
    gameconfig a chaque bataille. `ai_utilities_from_gameconfig` en est le mirror.
    """
    old = bc.get("Utilities") or {}
    new = ai_utilities_from_gameconfig()
    if not new:                                  # gameconfig sans aiUtilities : on ne casse rien
        return [], [], []
    added, changed, removed = [], [], []
    for sset in sorted(set(old) | set(new)):
        o_cats = old.get(sset) or {}
        n_cats = new.get(sset) or {}
        for cat in sorted(set(o_cats) | set(n_cats)):
            o_kv = o_cats.get(cat) if isinstance(o_cats.get(cat), dict) else {}
            n_kv = n_cats.get(cat) if isinstance(n_cats.get(cat), dict) else {}
            for k in sorted(set(o_kv) | set(n_kv)):
                path = "%s/%s/%s" % (sset, cat, k)
                if k not in o_kv:
                    added.append(path)
                elif k not in n_kv:
                    removed.append(path)
                elif o_kv[k] != n_kv[k]:
                    changed.append("%s %r->%r" % (path, o_kv[k], n_kv[k]))
    bc["Utilities"] = new
    return added, changed, removed


# --------------------------------------------------------------------------- validation

# Champs recalcules par buildNormalizedBC ou issus de l'etat JOUEUR (progression / relique
# equipee) -> hors perimetre de la synthese, donc exclus du diff.
_PLAYER_STATE_FIELDS = set(NORMALIZED_FIELDS) | {
    "Power", "AbilityVariablesMultiplierPercentage",
    "TertiaryAbilityVariablesMultiplierPercentage", "TertiaryAbility",
}


def validate(seed_bc: dict) -> tuple[int, dict]:
    """Re-synthetise chaque entree du catalogue capture et diffe champ a champ.

    Rend (nb entrees, {champ: [(id, attendu, obtenu), ...]}). Un dict vide = la synthese
    reproduit EXACTEMENT le catalogue que le jeu a construit, sur les 175 unites.
    """
    diffs: dict = {}
    units = seed_bc.get("Units") or []
    for real in units:
        try:
            synth = synthesize(real["Id"])
        except Exception as exc:                       # pragma: no cover - diagnostic
            diffs.setdefault("SYNTH_ERROR", []).append((real["Id"], str(exc), None))
            continue
        for k, v in synth.items():
            if k in _PLAYER_STATE_FIELDS:
                continue
            if real.get(k) != v:
                diffs.setdefault(k, []).append((real["Id"], v, real.get(k)))
    return len(units), diffs


def validate_abilities(seed_bc: dict) -> tuple[int, int, dict]:
    """Meme confrontation pour le catalogue d'ABILITIES : re-synthetise chaque entree de
    `BC.Abilities.{ActiveAbilities,PassiveAbilities}` depuis le gameconfig et diffe.

    Rend (nb confrontees, nb hors-gameconfig, diffs). Les entrees hors-gameconfig sont les
    configs INTERNES au moteur (traits Ambush/PrioritisedEfficiency/..., abilities
    d'environnement) : non derivables, comptees a part et JAMAIS synthetisees.
    """
    diffs: dict = {}
    checked = internal = 0
    for node in ("ActiveAbilities", "PassiveAbilities"):
        entries = (seed_bc.get("Abilities") or {}).get(node) or {}
        for name, real in entries.items():
            if G.ability(name) is None:
                internal += 1
                continue
            checked += 1
            synth = synthesize_ability(name)
            for k, v in synth.items():
                if real.get(k) != v:
                    diffs.setdefault(k, []).append((name, v, real.get(k)))
    return checked, internal, diffs


# ------------------------------ #449 : le PREMIER catalogue, lui, n'est PAS rattrape
#
# `refresh_ability_configs` (#254) et `refresh_ai_utilities` (#27-4) re-synthetisent DEUX des trois
# catalogues du BC a chaque chargement. Le TROISIEME -- `BC.Units`, celui que
# `IdunBattle.Core.Services.BattleQuery$$GetUnitConfig` parcourt et dont
# `IdunBattle.Entities.Factories.UnitFactory$$AddConfiguredAbilities` tire les passifs montes --
# reste la CAPTURE. Sa peremption etait donc parfaitement MUETTE : un runner bati sur ce seed
# deploie le kit du build de la capture, sans un mot, et rien ne le dit a personne.
#
# CE QUE CE SILENCE A COUTE (mesure, pas hypothese) : #354 a lu l'inertie qui en decoule comme un
# fait du jeu (« porteur retire »), puis SUPPRIME trois vecteurs de test valides ; #392 a du les
# restaurer. Le meme silence tient `MyWillBeDoneOverlord` INERTE dans tout runner bati sur ce seed
# (#392-r1), donc ses deux entrees de `ABILITY_TRIGGERS` ne sont jamais dispatchees par cette voie.
#
# CE MODULE NE RATTRAPE PAS -- il MESURE et il DIT. Rafraichir le bloc `Units` change le pool
# spawnable et les stats de reference de tous les tests live : c'est #254-bc, une decision
# d'arbitrage, pas un geste de passage.
#
# LA DERIVE ATTENDUE, ET SON ATTRIBUTION. `data/seed-bc.json` a UN SEUL commit (`f467e649`) : le
# bloc `Units` est reste celui de `gqfc5mff6c`. `necroOverlord` a change de kit a `rnca9r7q6c` --
# attribue mecaniquement par les DEUX tables d'enum versionnees :
#   * `MyWillBeDoneOverlord` est ABSENTE de `gqfc5mff6c/frida/enums.tsv` (468 membres de
#     `IdunBattle.Entities.Enum.TriggeredAbilityType`) et vaut 1556 dans `rnca9r7q6c` (477) ->
#     le gameconfig de `gqfc5mff6c` ne POUVAIT pas l'attribuer ; c'est donc la capture qui est en
#     arriere, pas la synthese qui invente. La capture porte `1045 MartialApotheosis`.
#   * `Resilient` (1009) existe dans les DEUX enums -> le trait gagne est un pur changement de
#     gameconfig, meme migration.
# Toute AUTRE derive est INATTENDUE : elle accuse la synthese (ou une capture re-faite), et doit
# etre lue avant d'etre inscrite ici.
STALE_UNIT_ENTRIES = {
    "necroOverlord": ("PassiveAbilities", "Traits"),
}


def stale_unit_entries(seed_bc: dict) -> dict:
    """`{unitId: {champ: (synthetise, capture)}}` -- les entrees `Units` que le gameconfig VIVANT
    ne rebatirait plus a l'identique. Dict vide = le bloc `Units` est a jour.

    Meme confrontation que `validate` (donc les memes champs exclus : etat JOUEUR et champs
    recalcules par `buildNormalizedBC`), re-indexee PAR UNITE : c'est l'unite qui arrive en
    bataille avec un kit perime, pas le champ.
    """
    out: dict = {}
    _n, diffs = validate(seed_bc)
    for field, rows in diffs.items():
        for uid, synth, real in rows:
            out.setdefault(uid, {})[field] = (synth, real)
    return out


def stale_unit_report(seed_bc: dict) -> str | None:
    """Une ligne ASCII decrivant la peremption du bloc `Units`, ou `None` s'il est a jour.

    Les entrees dont les champs derives sont EXACTEMENT ceux de `STALE_UNIT_ENTRIES` sont
    attendues (#254-bc) ; toute autre est marquee `INATTENDUE` -- jamais fondue dans le lot.
    """
    stale = stale_unit_entries(seed_bc)
    if not stale:
        return None
    parts = []
    for uid in sorted(stale):
        fields = sorted(stale[uid])
        attendu = STALE_UNIT_ENTRIES.get(uid)
        tag = "" if attendu is not None and fields == sorted(attendu) else " INATTENDUE"
        parts.append("%s{%s}%s" % (uid, ",".join(fields), tag))
    return ("bloc Units NON rattrape (#254-bc) : %d entree(s) perimee(s) vs le gameconfig courant "
            "-- %s" % (len(stale), " | ".join(parts)))


# --------------------------------------------------------------------------- CLI

def _load_seed(path: str | None) -> dict:
    p = Path(path) if path else SEED_BC
    if not p.exists():
        raise SystemExit(f"[error] seed BC absent: {p} (regenere: python dump_boards.py)")
    return json.loads(p.read_text(encoding="utf-8"))


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description="Injection de porteurs au catalogue BC.Units")
    ap.add_argument("--seed-bc", default=None, help="seed BC source (defaut data/seed-bc.json)")
    ap.add_argument("--units", default=None, help="ids a injecter, separes par des virgules")
    ap.add_argument("--out", default=None, help="chemin du seed BC augmente a ecrire")
    ap.add_argument("--rank", type=int, default=17)
    ap.add_argument("--ability-level", type=int, default=50)
    ap.add_argument("--ability-mult-pct", type=int, default=None,
                    help="force AbilityVariablesMultiplierPercentage (defaut: table de progression)")
    ap.add_argument("--show", default=None, help="affiche l'entree synthetisee d'un id")
    ap.add_argument("--validate", action="store_true",
                    help="re-synthetise le catalogue capture et diffe champ a champ")
    ap.add_argument("--missing", action="store_true",
                    help="liste les heros/MoW du gameconfig absents du catalogue")
    ap.add_argument("--equip-relic", action="append", default=None,
                    help="equipe une relique : 'unitId:AbilityName[:level]'. Repetable. Pose "
                         "TertiaryAbility + TertiaryAbilityLevel (>=1) ET injecte la config "
                         "d'ability dans BC.Abilities.PassiveAbilities. Combinable avec --units.")
    ap.add_argument("--allow-unlisted-relic", action="store_true",
                    help="--equip-relic : autorise un porteur hors allowedUnits (greffe)")
    ap.add_argument("--relic-state", action="store_true",
                    help="ventile les TROIS etats de la gate relique sur le seed BC")
    ap.add_argument("--list-relics", action="store_true",
                    help="liste les reliques du gameconfig (ability, paliers, porteurs)")
    ap.add_argument("--list-mythics", action="store_true",
                    help="liste les mythiques de MoW (ability, paliers, porteurs, presence au BC)")
    ap.add_argument("--explicit-stats", default=None, metavar="UNITID",
                    help="chemin de stats EXPLICITE d'un porteur npc/summon (#419-r1-tr12-r2) : "
                         "mirror de UnitProgression$$GetNpcStats / $$GetSummonStats")
    ap.add_argument("--explicit-stats-witness", action="store_true",
                    help="confronte le mirror NPC aux entrees npc du seed BC (ecrites PAR LE JEU)")
    ap.add_argument("--allow-zero-spawn-stats", action="store_true",
                    help="--explicit-stats : accepte un patch summon-spawn INTEGRALEMENT NUL "
                         "(porteur a 0 PV). A n'utiliser que pour amener le summon AU POOL sans "
                         "mesurer ses stats (#419-r1-tr12-r2-r1)")
    ap.add_argument("--summon-regimes", default=None, metavar="UNITID",
                    help="recense les voies de stats d'un summon : constantes FIXES "
                         "(UnitProgression$$GetSummonStats) vs ordinaux DYNAMIQUES "
                         "(SpawnUnitOptions$$WithStatsFromConfig*)")
    a = ap.parse_args(argv)

    seed = _load_seed(a.seed_bc)

    if a.summon_regimes:
        print(json.dumps(summon_spawn_regimes(a.summon_regimes), indent=2, sort_keys=True))
        return 0

    if a.explicit_stats:
        # Le refus de profil nul (#419-r1-tr12-r2-r1) doit sortir comme un DIAGNOSTIC, pas comme
        # une trace : c'est un fait mesure sur le gameconfig, pas un plantage de l'outil.
        try:
            rep = explicit_stats(a.explicit_stats, ability_level=a.ability_level,
                                 allow_zero_profile=a.allow_zero_spawn_stats)
        except (KeyError, ValueError) as exc:
            print(f"[error] --explicit-stats {a.explicit_stats}: {exc}", file=sys.stderr)
            return 2
        print(json.dumps(rep, indent=2, sort_keys=True))
        return 0

    if a.explicit_stats_witness:
        rows, div = npc_witness_diff(seed)
        for uid, bad in rows:
            print(("OK   " if not bad else "DIFF ") + uid
                  + ("" if not bad else "  " + json.dumps(bad, sort_keys=True)))
        print(f"[witness] npc du seed BC = {len(rows)}  divergences = {div}")
        if not rows:
            # Un temoin VIDE passerait pour un vert : c'est le regime degenere, on le refuse.
            print("[witness] AUCUN npc dans ce seed BC -- rien n'a ete confronte", file=sys.stderr)
            return 2
        return 0 if div == 0 else 1

    if a.list_relics:
        items = relic_items()
        by_ability: dict = {}
        for item_id, m in items.items():
            by_ability.setdefault(m["ability"], []).append((item_id, m))
        seed_pa = (seed.get("Abilities") or {}).get("PassiveAbilities") or {}
        print(f"[relics] {len(items)} items relique -> {len(by_ability)} abilities distinctes")
        for ability in sorted(by_ability):
            rows = by_ability[ability]
            carriers = sorted({u for _i, m in rows for u in m["allowedUnits"]})
            try:
                aid = triggered_ability_id(ability)
            except Exception:                              # pragma: no cover - diagnostic
                aid = None
            in_bc = "config-in-BC" if ability in seed_pa else "CONFIG ABSENTE du BC"
            print(f"  {ability:26s} id={aid} paliers={ability_level_count(ability):2d} "
                  f"{in_bc:22s} porteurs={carriers}")
        return 0

    if a.list_mythics:
        myth = mythic_abilities()
        seed_pa = (seed.get("Abilities") or {}).get("PassiveAbilities") or {}
        have = {u.get("Id") for u in (seed.get("Units") or [])}
        print(f"[mythics] {len(myth)} abilities mythiques (voie units.<kind>.<id>.mythicAbilities)")
        for ability in sorted(myth):
            carriers = myth[ability]
            try:
                aid = triggered_ability_id(ability)
            except Exception:                              # pragma: no cover - diagnostic
                aid = None
            in_bc = "config-in-BC" if ability in seed_pa else "CONFIG ABSENTE du BC"
            au_seed = sorted(u for u in carriers if u in have)
            print(f"  {ability:24s} id={aid} paliers={ability_level_count(ability):2d} "
                  f"{in_bc:22s} porteurs={carriers} au-seed={au_seed or 'AUCUN (augment requis)'}")
        return 0

    if a.relic_state:
        st = relic_state_of_seed_bc(seed)
        print(f"[relic-state] equipees au seed        : {len(st['equipped'])}")
        for uid, aid, lvl in st["equipped"]:
            print(f"    {uid:24s} TertiaryAbility={aid} TertiaryAbilityLevel={lvl}")
        print(f"[relic-state] au catalogue SANS relique: {len(st['eligible_no_relic'])}")
        print(f"[relic-state] porteurs hors catalogue  : {len(st['off_catalog'])} "
              f"{st['off_catalog']}")
        return 0

    if a.validate:
        # DEUX verdicts distincts, et les confondre a coute quatre jours de rouge mal attribue
        # (#254-bc) : la FIDELITE de la synthese (un defaut de CODE, rc=1) et la PEREMPTION de la
        # capture face au gameconfig VIVANT (un fait de DONNEE, rapporte, rc=0 tant qu'il est
        # epingle ou rattrape au chargement).
        rc = 0
        n, diffs = validate(seed)
        infidele = {}
        for field, rows in diffs.items():
            for uid, synth, real in rows:
                if field not in STALE_UNIT_ENTRIES.get(uid, ()):
                    infidele.setdefault(field, []).append((uid, synth, real))
        print(f"[validate] catalogue UNITS : {n} entrees re-synthetisees depuis le gameconfig")
        if infidele:
            rc = 1
            for field, rows in sorted(infidele.items()):
                print(f"  MISMATCH {field}: {len(rows)}")
                for r in rows[:4]:
                    print(f"    {r[0]}: attendu={r[1]!r} capture={r[2]!r}")
        else:
            print("[validate] OK - 0 divergence de FIDELITE sur les champs derives")
        rapport = stale_unit_report(seed)
        if rapport:
            print(f"[validate] PEREMPTION (pas un defaut de synthese) : {rapport}")
            for uid in sorted(stale_unit_entries(seed)):
                for field, (synth, real) in sorted(stale_unit_entries(seed)[uid].items()):
                    print(f"    {uid}.{field}: gameconfig={synth!r} capture={real!r}")
        nc, ni, adiffs = validate_abilities(seed)
        derivees = {name for rows in adiffs.values() for name, _s, _r in rows}
        print(f"[validate] catalogue ABILITIES : {nc} entrees confrontees "
              f"({ni} internes moteur, non derivables, ignorees)")
        if adiffs:
            for field, rows in sorted(adiffs.items()):
                print(f"  DERIVE {field}: {len(rows)}")
                for r in rows[:4]:
                    print(f"    {r[0]}: gameconfig={json.dumps(r[1])[:160]} "
                          f"capture={json.dumps(r[2])[:160]}")
        # Une derive de config n'est un DEFAUT que si le rattrapage #254 ne la repare pas : c'est
        # lui qui court-circuite le « system error » au cast/au deploiement.
        probe = copy.deepcopy(seed)
        refreshed, _added = refresh_ability_configs(probe)
        non_reparees = derivees - set(refreshed)
        if non_reparees:
            rc = 1
            print(f"  NON RATTRAPEES par refresh_ability_configs: {sorted(non_reparees)}")
        elif derivees:
            print(f"[validate] OK - les {len(derivees)} config(s) derivees sont rattrapees au "
                  f"chargement (#254): {sorted(derivees)}")
        else:
            print("[validate] OK - 0 divergence sur les configs d'ability")
        return rc

    if a.missing:
        miss = missing_from_seed_bc(seed)
        print(f"[missing] {len(miss)} unites lineup hors catalogue ({len(seed['Units'])} entrees):")
        for uid in miss:
            gc = G.unit(uid) or {}
            tag = "MoW" if "MachineOfWar" in (gc.get("traits") or []) else "   "
            print(f"  {tag} {uid:24s} {gc.get('FactionId','?'):18s} "
                  f"act={gc.get('activeAbilities')} pas={gc.get('passiveAbilities')}")
        # #254-bc-r1 : ENUMERER ne dit pas si l'ecart se CREUSE. On rend donc les trois categories
        # et on confronte `lineup` a l'epingle -- c'est ce qui manquait quand l'ecart est passe de
        # 17 a 21 sans un mot.
        gap = catalog_gap(seed)
        for kind in ("lineup", "npc", "summons"):
            g = gap[kind]
            print(f"[gap] {kind:8s} gameconfig={g['total']:4d}  absents du catalogue="
                  f"{len(g['missing']):4d}")
        rapport = catalog_gap_report(seed)
        print("[gap] " + (rapport if rapport else
                          "ecart d'AJOUT conforme a l'epingle (%d lineup, 0 summon)"
                          % len(MISSING_LINEUP_ENTRIES)))
        return 0

    if a.show:
        print(json.dumps(synthesize(a.show, a.rank, a.ability_level, a.ability_mult_pct), indent=1))
        drop = dropped_traits(G.unit(a.show.split(":")[0]) or {})
        if drop:
            # JAMAIS silencieux : c'est la signature « gameconfig EN AVANCE sur le binaire ».
            print(f"[traits] ECARTES (hors IdunBattle.Entities.Enum.UnitTrait du build "
                  f"{_build_hash()}) : {drop}")
        return 0

    if not a.units and not a.equip_relic:
        ap.print_help()
        return 2
    ids = [x.strip() for x in (a.units or "").split(",") if x.strip()]
    relic_specs = [parse_relic_spec(s) for s in (a.equip_relic or [])]
    ids += [uid for uid, _ab, _lvl in relic_specs if uid not in ids]
    bc, added, added_ab, unresolved = augment(seed, ids, a.rank, a.ability_level,
                                              a.ability_mult_pct)
    for uid, ability, lvl in relic_specs:
        try:
            rep = equip_relic(bc, uid, ability, lvl,
                              allow_unlisted=a.allow_unlisted_relic)
        except (ValueError, KeyError) as e:
            print(f"[error] --equip-relic {uid}:{ability}:{lvl} -> {e}", file=sys.stderr)
            return 2
        clamp = (f"  [clamp] niveau {rep['level']} > {rep['levelsAvailable']} paliers -> le "
                 f"natif rend le dernier" if rep["clamped"] else "")
        print(f"[relic] {uid} <- {ability} (id={rep['abilityId']}) niveau={rep['level']} "
              f"config{'+' if rep['configAdded'] else '='}BC{clamp}")
    print(f"[inject] {len(added)} unites ajoutees: {added}")
    print(f"[inject] catalogue Units: {len(seed['Units'])} -> {len(bc['Units'])} entrees")
    print(f"[inject] {len(added_ab)} configs d'ability ajoutees: {added_ab}")
    if unresolved:
        print(f"[inject] traits MARQUEURS sans config (absence normale, cf. les 175 capturees): "
              f"{unresolved}")
    if not a.out:
        print("[error] --out <chemin> requis pour ecrire le seed BC augmente", file=sys.stderr)
        return 2
    # CHOKE POINT (#349) : le seed BC augmente est une SORTIE de run -> `logs/`,
    # jamais `data/` (versionne, ENTREES seules ; y ecrire salit `git status`).
    try:
        host_inputs.reject_data_output(a.out, "--out")
    except host_inputs.DataOutputRefused as e:
        print(f"[error] {e}", file=sys.stderr)
        return 2
    outp = Path(a.out)
    outp.parent.mkdir(parents=True, exist_ok=True)
    outp.write_text(json.dumps(bc), encoding="utf-8")
    stamp_grafts(outp)   # #448-r3-r1-r1-r1 : la marque voyage AVEC le fichier
    print(f"[inject] ecrit {outp} ({outp.stat().st_size} octets)")
    print(f"[inject] usage: python rl_duel.py build --seed-bc {outp} --board <id> ...")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
