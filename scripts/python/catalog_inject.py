#!/usr/bin/env python
"""catalog_inject -- INJECTION DE PORTEURS AU CATALOGUE `BattleConfiguration.Units`.

PROBLEME (cases #92 / #54). Le seed BC sur disque (`data/seed-bc.json`) est la capture d'UNE
bataille reelle : son `Units[]` ne contient que les 175 unites que le compte du joueur possedait
ce jour-la. 17 heros/MoW du gameconfig n'y sont PAS (les 4 Votann, thousDaemonPrince,
necroReanimator, darkaStormSpeeder, ...) -> `rl_duel build --p-units <id>` les refuse (hors pool)
et leurs abilities sont INCONFRONTABLES.

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


# --------------------------------------------------------------------------- enums per-build

def _build_hash() -> str:
    """Hash du build qui FAIT FOI, designe par `data/symbols/CURRENT`.

    Exigeait auparavant un repertoire UNIQUE sous data/symbols/ -- ce qui cassait des qu'une
    MAJ laissait l'ancien build a cote du neuf, alors qu'on le conserve EXPRES (son diff est
    le rapport de changement du jeu). Cf. `symbols_layout.py`."""
    from symbols_layout import current_build
    return current_build()


@functools.lru_cache(maxsize=8)
def enum_map(enum_name: str) -> dict:
    """{membre: id} d'un enum, lu dans data/symbols/<build>/frida/enums.tsv.

    C'est la SEULE source acceptable pour les ids d'ability : elle est estampillee
    per-build (`#!il2cpp-provenance ... build=<hash>`) et versionnee. `frida/hooks/data/
    ability-names.ts` NE l'est pas et se revele STALE sur gqfc5mff6c (il ignore
    ReanimationBeam=1223 / NanoscarabRepairProtocols=1224, les deux abilities de
    necroReanimator) -> l'utiliser produirait un porteur SANS ability, silencieusement.
    """
    p = SYMBOLS / _build_hash() / "frida" / "enums.tsv"
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


def _traits(gc: dict) -> list:
    """[GrandAlliance] + [Subfaction si presente] + traits (+ "NPC" pour un kind npc).

    Mirror de l'ordre observe dans les 175 entrees (l'alliance d'abord, la sous-faction
    ensuite : custoAtlacoya -> ['Imperial','SistersSilence','Hero','Parry','Terrifying']).
    """
    out = []
    if gc.get("GrandAllianceId"):
        out.append(gc["GrandAllianceId"])
    if gc.get("Subfaction"):
        out.append(gc["Subfaction"])
    out += list(gc.get("traits") or [])
    if gc.get("kind") == "npc":
        out.append("NPC")
    return out


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
        "ActiveAbilities": [active_ability_id(a) for a in (gc.get("activeAbilities") or [])],
        "PassiveAbilities": [triggered_ability_id(a) for a in (gc.get("passiveAbilities") or [])],
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
    """
    gc = G.unit(unit_id.split(":")[0]) or {}
    act = list(gc.get("activeAbilities") or [])
    pas = [n for n in (gc.get("passiveAbilities") or []) if G.ability(n) is not None]
    pas += [t for t in (gc.get("traits") or []) if G.ability(t) is not None]
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
    # SORTIE de run -> `logs/`, jamais `data/` (versionne, ENTREES seules) : #349.
    p = host_inputs.reject_data_output(out_path, "write_augmented_seed_bc(out_path=...)")
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(bc), encoding="utf-8")
    return p, added, added_ab


def missing_from_seed_bc(seed_bc: dict) -> list:
    """Ids `units.lineup` du gameconfig absents du catalogue capture (= porteurs bloques)."""
    have = {u["Id"].split(":")[0] for u in seed_bc.get("Units") or []}
    return sorted(k for k in G._index()["lineup"] if k not in have)


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
#      de relique du gameconfig, 3 SEULEMENT y sont (celles equipees au seed). Sans la config,
#      `IdunBattle.Configuration.AbilityConfiguration$$GetVariableForLevel` s'execute sur une
#      config nulle -> « system error » au cast. Meme verrou, meme parade que #226 pour un
#      porteur hors pool : c'est `synthesize_ability` qui la produit.
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
    n_lvl = ability_level_count(ability_name)
    return {
        "unitId": unit_id, "ability": ability_name, "abilityId": aid,
        "level": level, "levelsAvailable": n_lvl,
        "clamped": bool(n_lvl and level > n_lvl),
        "configAdded": config_added, "unitsPatched": len(hits),
        "allowedUnits": carriers,
    }


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

def refresh_ability_configs(bc: dict) -> tuple[list, list]:
    """RE-SYNTHETISE `BC.Abilities` depuis le gameconfig VIVANT, EN PLACE. Rend (rafraichies,
    ajoutees).

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
    refreshed, added = [], []
    for target in (act_node, pas_node):
        for name in list(target):
            if G.ability(name) is None:                 # config interne moteur : non derivable
                continue
            synth = synthesize_ability(name)
            if synth != target[name]:
                target[name] = synth
                refreshed.append(name)
    # Une ability AJOUTEE a une unite deja au catalogue n'a aucune config : meme faute, cause
    # symetrique. Mirror du peuplement de `BC.Abilities` (cf. `_ability_names`).
    for u in (bc.get("Units") or []):
        act, pas = _ability_names(u.get("Id") or "")
        for names, target in ((act, act_node), (pas, pas_node)):
            for n in names:
                if n in target:
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
    a = ap.parse_args(argv)

    seed = _load_seed(a.seed_bc)

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
        rc = 0
        n, diffs = validate(seed)
        print(f"[validate] catalogue UNITS : {n} entrees re-synthetisees depuis le gameconfig")
        if diffs:
            rc = 1
            for field, rows in sorted(diffs.items()):
                print(f"  MISMATCH {field}: {len(rows)}")
                for r in rows[:4]:
                    print(f"    {r[0]}: attendu={r[1]!r} capture={r[2]!r}")
        else:
            print("[validate] OK - 0 divergence sur les champs derives")
        nc, ni, adiffs = validate_abilities(seed)
        print(f"[validate] catalogue ABILITIES : {nc} entrees confrontees "
              f"({ni} internes moteur, non derivables, ignorees)")
        if adiffs:
            rc = 1
            for field, rows in sorted(adiffs.items()):
                print(f"  MISMATCH {field}: {len(rows)}")
                for r in rows[:4]:
                    print(f"    {r[0]}: attendu={json.dumps(r[1])[:160]} "
                          f"capture={json.dumps(r[2])[:160]}")
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
        return 0

    if a.show:
        print(json.dumps(synthesize(a.show, a.rank, a.ability_level, a.ability_mult_pct), indent=1))
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
    print(f"[inject] ecrit {outp} ({outp.stat().st_size} octets)")
    print(f"[inject] usage: python rl_duel.py build --seed-bc {outp} --board <id> ...")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
