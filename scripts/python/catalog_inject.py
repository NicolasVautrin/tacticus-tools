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
    p = Path(out_path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(bc), encoding="utf-8")
    return p, added, added_ab


def missing_from_seed_bc(seed_bc: dict) -> list:
    """Ids `units.lineup` du gameconfig absents du catalogue capture (= porteurs bloques)."""
    have = {u["Id"].split(":")[0] for u in seed_bc.get("Units") or []}
    return sorted(k for k in G._index()["lineup"] if k not in have)


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
    a = ap.parse_args(argv)

    seed = _load_seed(a.seed_bc)

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

    if not a.units:
        ap.print_help()
        return 2
    ids = [x.strip() for x in a.units.split(",") if x.strip()]
    bc, added, added_ab, unresolved = augment(seed, ids, a.rank, a.ability_level,
                                              a.ability_mult_pct)
    print(f"[inject] {len(added)} unites ajoutees: {added}")
    print(f"[inject] catalogue Units: {len(seed['Units'])} -> {len(bc['Units'])} entrees")
    print(f"[inject] {len(added_ab)} configs d'ability ajoutees: {added_ab}")
    if unresolved:
        print(f"[inject] traits MARQUEURS sans config (absence normale, cf. les 175 capturees): "
              f"{unresolved}")
    if not a.out:
        print("[error] --out <chemin> requis pour ecrire le seed BC augmente", file=sys.stderr)
        return 2
    outp = Path(a.out)
    outp.parent.mkdir(parents=True, exist_ok=True)
    outp.write_text(json.dumps(bc), encoding="utf-8")
    print(f"[inject] ecrit {outp} ({outp.stat().st_size} octets)")
    print(f"[inject] usage: python rl_duel.py build --seed-bc {outp} --board <id> ...")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
