"""#229 -- INVENTAIRE : quels effet-triggers de `EFFECT_TRIGGERS` lisent le flag
`EffectComponent.IsActive @+0x5c` (`BaseEffect.active`) ?

100 % OFFLINE (aucun runner, aucune session Frida) : le probe importe le registre et
DERIVE les faits mecaniques (compte, porteur unite/tuile, lecture du flag par AST),
puis les CROISE avec le RAIL NATIF de chaque classe -- la seule donnee saisie a la main,
sourcee par SYMBOLE (colonne `rail`), etablie par lecture du decompile (cf.
`docs/rl/case-229-effect-triggers-active-inventory.md`).

CRITERE NATIF (lu, pas deduit) --
  * `IdunBattle.Operations.EvaluateTriggerOperation$$EvaluateEffectTriggerTargets` teste
    `EffectComponent.IsActive` DEUX fois (a l'entree, puis PAR CIBLE dans la boucle) avant
    d'evaluer `ShouldTrigger` : un trigger issu de `<Effect>$$CreateTargetTrigger` DOIT
    donc lire le flag ;
  * `IdunBattle.Operations.EvaluateTriggerOperation$$EvaluateEffectTriggerEffectAbilities`
    n'accede JAMAIS a `+0x5c` : les `Triggered()` de
    `<Effect>$$CreateHandleTriggerAbilitiesInternal` (et la greffe
    `<Effect>$$CreateRemoveEffectTrigger` que `IdunBattle.Entities.Effects.BaseEffect$$
    CreateHandleTriggerAbilities` ajoute au MEME `ArraySet`) ne doivent PAS le lire --
    les gater serait une infidelite (c'est ce rail qui RE-ACTIVE un effet eteint).

=> le probe est un CLIQUET : il ECHOUE si un effet-trigger du rail TARGETS (ou APPLY_REVERT)
entre au registre sans lire le flag, ou si un trigger du rail ARRAYSET se met a le lire.

Usage :  python probe_229_effect_triggers_active.py [--verbose]
"""
from __future__ import annotations

import argparse
import ast
import inspect
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from engine.runner.operations.triggers.dispatch.registry import EFFECT_TRIGGERS  # noqa: E402
from engine.runner.operations.triggers.base import EffectTrigger                 # noqa: E402


#: Ce qui doit changer pour que ce cliquet puisse changer d'avis.
DECLENCHEUR = {
    "chemins": ("scripts/python/probe_229_effect_triggers_active.py",
                "scripts/python/engine/*.py", "scripts/python/engine/**/*.py",
                "scripts/python/*.py",
                "data/seed-bc.json"),
    "build": False,
    "toujours": False,
    "raison": (
        "Il importe EFFECT_TRIGGERS et relit par `inspect.getsource` le `matches` de chaque classe "
        "portee -- resolu par la MRO, donc n'importe ou sous engine/ -- plus les helpers du MEME "
        "module. Ses trois tables (RAIL, EXPECTED_GAPS, ARRAYSET_READS_BY_TREE) vivent dans son "
        "propre source. Le glob racine `scripts/python/*.py` n'est pas decoratif : la fermeture "
        "d'imports MESUREE est de 274 modules engine/ PLUS `gameconfig.py` et `hexgeo.py`, et un "
        "import casse la-haut change le rc. `data/seed-bc.json` non plus : "
        "`engine/services/damage_modifiers.py` le lit AU NIVEAU MODULE (`_DMG_CFG`), donc toute "
        "cascade qui traverse `engine.entities.effects` l'ouvre -- fait MESURE par trace d'audit, "
        "et invisible a une lecture des imports. Rien du build : le verdict est purement "
        "syntaxique (aucun ordinal, aucun `enums.tsv`), et `gameconfig` est lazy (`lru_cache`) -- "
        "jamais atteint, verifie a la trace."),
}


# --- RAIL NATIF par classe portee -----------------------------------------------------------
# TARGETS      : `<Effect>$$CreateTargetTrigger`                -> gate IsActive NATIF -> DOIT lire
# ARRAYSET     : `<Effect>$$CreateHandleTriggerAbilitiesInternal`
#                (+ greffe `$$CreateRemoveEffectTrigger`)       -> AUCUN gate      -> NE DOIT PAS lire
# APPLY_REVERT : la triggered-ability est ajoutee/retiree par
#                `<Effect>$$ApplyInternal` / `$$RevertInternal`  -> l'effet INACTIF est reverte
#                (`RefreshEffectsOperation$$DeactivateEffect` -> `UpdateEffectTargets` avec une
#                liste de cibles VIDE -> `RemoveTargetsFromEffect`) -> DOIT lire
# ENV_ABILITY  : PAS un effet-trigger natif -- ability d'ENVIRONNEMENT
#                (`Env*TileAbility$$CreateTrigger` = `On(0x14) & Count(EntitiesWithAnyEffect(T))>0`),
#                inscrite au registre comme VEHICULE de collecte par tuile. Gate natif = le
#                selecteur, pas `EvaluateEffectTrigger*`.
TARGETS, ARRAYSET, APPLY_REVERT, ENV_ABILITY = "TARGETS", "ARRAYSET", "APPLY_REVERT", "ENV_ABILITY"

RAIL: dict[str, tuple[str, str]] = {
    # classe portee                          rail            symbole natif source
    "OverwatchAutoAttack":
        (TARGETS, "IdunBattle.Entities.Effects.RangedAutoAttackEffect$$CreateTargetTrigger"),
    "RangedAutoAttackActivateOnTurnStart":
        (ARRAYSET, "IdunBattle.Entities.Effects.RangedAutoAttackEffect$$CreateHandleTriggerAbilitiesInternal"),
    "RangedAutoAttackDeactivateOnTurnStart":
        (ARRAYSET, "IdunBattle.Entities.Effects.RangedAutoAttackEffect$$CreateHandleTriggerAbilitiesInternal"),
    "RangedAutoAttackDeactivateOnAttack":
        (ARRAYSET, "IdunBattle.Entities.Effects.RangedAutoAttackEffect$$CreateHandleTriggerAbilitiesInternal"),
    "HazeOfCorruptionDamageTransferTrigger":
        (TARGETS, "IdunBattle.Entities.Effects.Loki.HazeOfCorruption_DamageTransferEffect$$CreateTargetTrigger"),
    # #547-r2 -- inscrite APRES coup : la classe est entree au registre par #576 sans rail declare,
    # et le gate `IsActive` du rail TARGETS lui MANQUAIT (pose dans le meme commit). C'est
    # exactement le gisement que ce cliquet surveille : le probe ne pouvait rien dire d'une classe
    # absente de cette table.
    "BloodChaliceHealOnMeleeAttack":
        (TARGETS, "IdunBattle.Entities.Effects.Loki.BloodChalice_HealOnAttackEffect$$CreateTargetTrigger"),
    "ContaminatedTileEffect":
        (ARRAYSET, "IdunBattle.Entities.Effects.Loki.ContaminatedEffect$$CreateHandleTriggerAbilitiesInternal"),
    "FireTileDoT":
        (ENV_ABILITY, "IdunBattleLogic.Entities.Abilities.Active.Loki.EnvFireTileAbility$$CreateTrigger"),
    "DespoiledGroundTileDoT":
        (ENV_ABILITY, "IdunBattleLogic.Entities.Abilities.Active.Loki.EnvDespoiledGroundTileAbility$$CreateTrigger"),
    "MasterOfTheTutelariesSummonAbility":
        (APPLY_REVERT, "IdunBattle.Entities.Effects.Loki.MasterOfTheTutelariesEffect$$ApplyInternal"),
    "RitesOfMorkaiReviveTrigger":
        (TARGETS, "IdunBattle.Entities.Effects.ReviveEffect$$CreateTargetTrigger"),
    "ReanimationBeamReviveTrigger":
        (TARGETS, "IdunBattle.Entities.Effects.ReviveEffect$$CreateTargetTrigger"),
    "PhoenixGemReviveAbility":
        (ARRAYSET, "IdunBattle.Entities.Effects.Loki.PhoenixGem_CanReviveEffect$$CreateHandleTriggerAbilitiesInternal"),
    "PhoenixGemRemoveMarkerOnRevive":
        (ARRAYSET, "IdunBattle.Entities.Effects.Loki.PhoenixGem_CanReviveEffect$$CreateHandleTriggerAbilitiesInternal"),
    "PhoenixGemRemoveMarkerOnResurrect":
        (ARRAYSET, "IdunBattle.Entities.Effects.Loki.PhoenixGem_CanReviveEffect$$CreateHandleTriggerAbilitiesInternal"),
    "FuelledByFuryCanReviveActivateOnAbilityInit":
        (ARRAYSET, "IdunBattle.Entities.Effects.Loki.FuelledByFury_CanReviveEffect$$CreateHandleTriggerAbilitiesInternal"),
    "FuelledByFuryCanReviveActivateOnTurnStart":
        (ARRAYSET, "IdunBattle.Entities.Effects.Loki.FuelledByFury_CanReviveEffect$$CreateHandleTriggerAbilitiesInternal"),
    "FuelledByFuryCanReviveDeactivateOnRevive":
        (ARRAYSET, "IdunBattle.Entities.Effects.Loki.FuelledByFury_CanReviveEffect$$CreateHandleTriggerAbilitiesInternal"),
    "AnvilShieldFrozenAdvantageExpire":
        (TARGETS, "IdunBattle.Entities.Effects.Loki.AnvilShield_FrozenAttackerAdvantageEffect$$CreateTargetTrigger"),
    "InspiredToGreatnessOverrideLevelRemove":
        (ARRAYSET, "IdunBattle.Entities.Effects.Loki.InspiredToGreatness_OverrideLevelEffect$$CreateRemoveEffectTrigger"),
    "ChronometronExtraDamageRemove":
        (ARRAYSET, "IdunBattle.Entities.Effects.Loki.Chronometron_ExtraDamageEffect$$CreateRemoveEffectTrigger"),
    # #522 -- MEME forme que les deux ci-dessus : un `CreateRemoveEffectTrigger`, que
    # `IdunBattle.Entities.Effects.BaseEffect$$CreateHandleTriggerAbilities` GREFFE dans l'`ArraySet`
    # sous `Triggered(<lui>, GetRemoveEffectBehaviour())` quand le virtuel rend non nul. Corps RELU
    # (build `rnca9r7q6c`) : `On(9, alive) & get_OwnerIsTarget | On(0, alive) & AreEqual(sel+0x60,
    # EffectSource(sel+0x38))` -- aucun `CreateTargetTrigger` sur cette classe (les trois seules
    # methodes du namespace sont `.ctor`, `CreateCritChanceBonus`, `CreateRemoveEffectTrigger`).
    # Rail ARRAYSET => AUCUN gate `IsActive` natif => le port ne doit PAS lire le flag.
    "EuphoricStrikesExtraCritRemove":
        (ARRAYSET, "IdunBattle.Entities.Effects.Loki.EuphoricStrikes_ExtraCritEffect$$CreateRemoveEffectTrigger"),
    # ROUGE PREEXISTANT DE `master`, trouve par #549 en jouant ce garde. `#BL-1020r` a inscrit la
    # classe au registre sans lui declarer de rail, donc
    # `test_421_effect_active_gate_offline::test_the_probe_rail_covers_the_whole_registry` echouait
    # sur `origin/master` (verifie : la classe est dans `dispatch/registry.py` de master, absente
    # de CE dict). MEME forme que les trois entrees ci-dessus -- un `CreateRemoveEffectTrigger`
    # (`On(9) & OwnerIsTarget & IsUnit(caster@DSLSelectors+0x48)`) que
    # `IdunBattle.Entities.Effects.BaseEffect$$CreateHandleTriggerAbilities` GREFFE dans l'`ArraySet`
    # sous `Triggered(<lui>, GetRemoveEffectBehaviour())`. Rail ARRAYSET => AUCUN gate `IsActive`
    # natif => le port ne doit PAS lire le flag.
    "HeraldOfTheApocalypseExtraDamageRemove":
        (ARRAYSET, "IdunBattle.Entities.Effects.Loki.HeraldOfTheApocalypse_ExtraDamageEffect$$CreateRemoveEffectTrigger"),
    # #513 -- le `Triggered()` de la BASE `APendingAttackEffect`, PARTAGE par ses 20 derivees (une
    # seule classe portee, N effectTypes inscrits -- meme forme que `BondRemoveOnBondedEntityDeath`).
    # Corps RELU : il appelle d'abord `ABondEffect$$CreateHandleTriggerAbilitiesInternal`, puis clot
    # son propre `Triggered(On(0x15) & IsTurnOf(<klass+0x758>), TriggerAbility(...) & RemoveEffect(
    # sel+0x38))` par `Idun.Shared.Collections.ArraySet<T>$$Add(this, ...)` -- le MEME `ArraySet`
    # qu'enumere `EvaluateTriggerOperation$$EvaluateEffectTriggerEffectAbilities`, ou `+0x5c` n'est
    # jamais lu. Rail ARRAYSET, pas TARGETS.
    "PendingAttackOnAttackersTurn":
        (ARRAYSET, "IdunBattle.Entities.Effects.APendingAttackEffect$$CreateHandleTriggerAbilitiesInternal"),
    # #462-r4b-r1-r1-r1 -- les DEUX `Triggered()` que
    # `NeuroparasiteEffect$$CreateHandleTriggerAbilitiesInternal` ajoute a l'`ArraySet` (montee de
    # niveau sur frappe PSYCHIQUE `On(9)` et sur pose de `Pinned` `On(0x3d)`). Rail ARRAYSET : le
    # natif ne les fait PAS passer par `EvaluateEffectTriggerTargets`, donc aucun gate `IsActive` --
    # et le port ne doit pas en inventer un.
    "NeuroparasiteIncreaseLevelOnPsychicHit":
        (ARRAYSET, "IdunBattle.Entities.Effects.Loki.NeuroparasiteEffect$$CreateHandleTriggerAbilitiesInternal"),
    "NeuroparasiteIncreaseLevelOnPinned":
        (ARRAYSET, "IdunBattle.Entities.Effects.Loki.NeuroparasiteEffect$$CreateHandleTriggerAbilitiesInternal"),
    # #1012-r1 -- le `Triggered()` UNIQUE de l'`ArraySet` de
    # `HeadwoppasKillchoppaEffect$$CreateHandleTriggerAbilitiesInternal` (+1 niveau par unite
    # non-`Steppable` que le PORTEUR abat). Rail ARRAYSET, donc AUCUN gate `IsActive` natif -- et
    # ici ce n'est pas seulement << le port ne doit pas en inventer un >> : l'effet naît au NIVEAU
    # 0 (`options{+0x10} = <DSLFormulas+0x18> = Direct(0)`), donc INACTIF ; un gate `IsActive`
    # gelerait son compteur a zero POUR TOUJOURS.
    "HeadwoppasKillchoppaIncreaseLevelOnKill":
        (ARRAYSET, "IdunBattle.Entities.Effects.Loki.HeadwoppasKillchoppaEffect$$"
                   "CreateHandleTriggerAbilitiesInternal"),
    # #590-r3 (merge `19e1746d`, 2026-08-13) -- la PROPAGATION de `1209 AttemptedPossession_Possessed`.
    # ⚠ ENTREE AU REGISTRE SANS SON RAIL : `master` en est reste ROUGE
    # (`test_421_effect_active_gate_offline::test_the_probe_rail_covers_the_whole_registry`,
    # « classe(s) inscrite(s) sans rail declare »), trouve au REBASE par #934. C'est le gisement que
    # notre propre cadence de portage alimente, et ce rail-ci n'est PAS deduit par parente : l'en-tete
    # de `engine/runner/operations/triggers/loki/attempted_possession.py` le LIT et le NOMME --
    # « `CreateHandleTriggerAbilitiesInternal`, donc du rail `ArraySet` que
    # `EvaluateTriggerOperation$$EvaluateEffectTriggerEffectAbilities` sert », par opposition a
    # `EvaluateEffectTriggerTargets` (celui de `CreateTargetTrigger`) qui porte le gate.
    # Rail ARRAYSET => AUCUN gate `IsActive` natif => le port ne doit PAS lire le flag.
    "AttemptedPossessionPropagate":
        (ARRAYSET, "IdunBattle.Entities.Effects.Loki.AttemptedPossession_PossessedEffect$$"
                   "CreateHandleTriggerAbilitiesInternal"),
    # #462-r4b-r1-r1-r1-r1 -- le RETRAIT (a) herite d'`ABondEffect`, PARTAGE par toutes ses
    # derivees (une seule classe portee, N effectTypes inscrits : 1218 `Neuroparasite`, 1077
    # `HazeOfCorruption_DamageTransfer`). Rail ARRAYSET : c'est la BASE qui l'ajoute a l'`ArraySet`,
    # il ne passe donc PAS par `EvaluateEffectTriggerTargets` et n'a AUCUN gate `IsActive`. Le gate
    # qui decide de sa CONSTRUCTION est ailleurs -- le virtuel `<klass+0x748>
    # get_RemoveOnBondedEntityDeath`, porte par la table `BOND_REMOVAL_GATES`.
    "BondRemoveOnBondedEntityDeath":
        (ARRAYSET, "IdunBattle.Entities.Effects.ABondEffect$$CreateHandleTriggerAbilitiesInternal"),
    # #462-r4b-r1-r1-r1-r1-b-r2 -- le RETRAIT (b) `get_Range`, entre au registre par #462-r4b-r1-r1-r1-r1-b
    # sans son rail. MEME rail et MEME symbole que (a), et ce n'est PAS une deduction par parente :
    # le decompile de `ABondEffect$$CreateHandleTriggerAbilitiesInternal` (build `rnca9r7q6c`) porte
    # les TROIS `Triggered()` dans UN SEUL corps, chacun clos par le MEME
    # `ArraySet<T>.Add(this, <trigger>, <token>)` sur le MEME receveur `this` -- sites internes
    # mesures aux octets (`ghidra read_bytes` sur le corps, motifs `mov rcx,rbp ; call`) :
    #
    #     (a) gate `<klass+0x748> get_RemoveOnBondedEntityDeath` a +0x67   -> Add a +0x214
    #     (b) gate `<klass+0x728> get_Range` (HasValue a +0x222, get_Value a +0x2c9),
    #         `On(0x1d)` a +0x3b7                                          -> Add a +0x436
    #     (c) gate `<klass+0x738> get_Adjacent` a +0x444, `On(0x1d)` a +0x53d -> Add a +0x5b0
    #
    # Le receveur de ces trois `Add` est l'`ArraySet` que `BaseEffect$$CreateHandleTriggerAbilities`
    # recupere du virtuel `<+0x588>` puis publie dans le champ `Nullable` de l'effet -- le MEME
    # ArraySet que celui ou il greffe `<+0x5a8> CreateRemoveEffectTrigger`. C'est cet ArraySet
    # qu'enumere `EvaluateTriggerOperation$$EvaluateEffectTriggerEffectAbilities`, ou aucun acces a
    # `+0x5c` n'existe (relu ici in extenso). Rail ARRAYSET => AUCUN gate `IsActive` natif => le port
    # ne doit PAS lire le flag.
    #
    # ⚠ (b) N'EST PAS un `CreateTargetTrigger` : `ABondEffect` n'en declare aucun. Le seul gate de
    # (b) est le `Nullable<int> get_Range`, qui decide de sa CONSTRUCTION -- porte par la table
    # `BOND_REMOVAL_GATES` (champ `range`), exactement comme `<klass+0x748>` porte celui de (a).
    "BondRemoveOnRangeExceeded":
        (ARRAYSET, "IdunBattle.Entities.Effects.ABondEffect$$CreateHandleTriggerAbilitiesInternal"),
    # #549 -- (c) `<klass+0x738> get_Adjacent`, TROISIEME `Triggered()` du MEME
    # `CreateHandleTriggerAbilitiesInternal` : meme rail que (a) et (b), meme ArraySet, donc AUCUN
    # gate `IsActive` natif. Son seul gate de CONSTRUCTION est le virtuel booleen, porte par la
    # table `BOND_REMOVAL_GATES` (champ `adjacent`) -- exactement comme `<+0x748>` pour (a) et
    # `<+0x728>` pour (b). Inscrit depuis que le port POSE `HolyDuel_Taunt` (1091), le SEUL effet
    # de la famille a l'armer.
    "BondRemoveOnAdjacencyLost":
        (ARRAYSET, "IdunBattle.Entities.Effects.ABondEffect$$CreateHandleTriggerAbilitiesInternal"),
    "EarlyWarningOverrideReactivateOverwatch":
        (ARRAYSET, "IdunBattle.Entities.Effects.AReactivateOverwatchEffect$$CreateHandleTriggerAbilitiesInternal"),
    "EarlyWarningOverrideHitReductionPurge":
        (ARRAYSET, "IdunBattle.Entities.Effects.AReactivateOverwatchEffect$$CreateHandleTriggerAbilitiesInternal"),
    # #943 -- les DEUX classes de `InescapableDeathEffect` (1018), entrees au registre par #924 sans
    # rail declare, ce qui rendait `master` ROUGE sur
    # `test_421_effect_active_gate_offline::test_the_probe_rail_covers_the_whole_registry`.
    # Ce ne sont PAS des voisines de forme : `InescapableDeathReactivateOverwatch` et
    # `InescapableDeathHitReductionPurge` derivent, dans le PORT comme dans le NATIF, des memes
    # bases que le couple `EarlyWarningOverride*` ci-dessus -- ce sont les Triggered #1 et #2 du
    # MEME corps `AReactivateOverwatchEffect$$CreateHandleTriggerAbilitiesInternal` (les
    # sous-classes n'overrident que `GetHitReductionEffectType` / `LegitDeathReasons`, jamais le
    # `CreateHandleTriggerAbilitiesInternal`). MEME ArraySet => AUCUN gate `IsActive` natif.
    "InescapableDeathReactivateOverwatch":
        (ARRAYSET, "IdunBattle.Entities.Effects.AReactivateOverwatchEffect$$CreateHandleTriggerAbilitiesInternal"),
    "InescapableDeathHitReductionPurge":
        (ARRAYSET, "IdunBattle.Entities.Effects.AReactivateOverwatchEffect$$CreateHandleTriggerAbilitiesInternal"),
    # #943 -- le SECOND chemin de declenchement de `TheLionsWrath_PendingAttackEffect` (1521), entre
    # au registre par #892 sans rail declare. Le corps natif (cite verbatim dans
    # `engine/runner/operations/triggers/loki/lions_wrath_attack.py` Sec. 2) part de
    # `APendingAttackEffect$$CreateHandleTriggerAbilitiesInternal()` puis `set.Add(Triggered(
    # On(0x25 = UnitRemoved) & get_OwnerIsTarget, GetAttackBehaviour(effect)))` -- donc le MEME
    # ArraySet que celui qu'enumere `EvaluateTriggerOperation$$EvaluateEffectTriggerEffectAbilities`,
    # ou `+0x5c` n'est jamais lu. Rail ARRAYSET, pas TARGETS.
    "LionsWrathPendingAttackOnUnitRemoved":
        (ARRAYSET, "IdunBattle.Entities.Effects.Loki.TheLionsWrath_PendingAttackEffect$$CreateHandleTriggerAbilitiesInternal"),
    # #421 -- `GhostEffect` : UNE classe native, DEUX effectTypes depuis #366-r1 (1186 TimeFlux_Revive,
    # 1284 EchoesFromTheWarp_Revive). L'ancien trio de noms (`GhostEffectRevive`, `GhostRemove*`) est
    # devenu le nom des BASES ABSTRAITES, non inscrites : le RAIL a continue de les citer et est donc
    # devenu MUET sur les 12 classes reellement inscrites -- avec, en prime, un `EXPECTED_GAPS` qui
    # annoncait « resorbe » un gap qui avait en realite DOUBLE.
    "TimeFluxGhostEffectRevive":
        (TARGETS, "IdunBattle.Entities.Effects.Loki.GhostEffect$$CreateTargetTrigger"),
    "TimeFluxGhostRemoveOnSourceMoves":
        (ARRAYSET, "IdunBattle.Entities.Effects.Loki.GhostEffect$$CreateHandleTriggerAbilitiesInternal"),
    "TimeFluxGhostRemoveOnUnitAdded":
        (ARRAYSET, "IdunBattle.Entities.Effects.Loki.GhostEffect$$CreateHandleTriggerAbilitiesInternal"),
    "TimeFluxGhostRemoveOnUnitEnters":
        (ARRAYSET, "IdunBattle.Entities.Effects.Loki.GhostEffect$$CreateHandleTriggerAbilitiesInternal"),
    "TimeFluxGhostRemoveOnSourceDeathInactive":
        (ARRAYSET, "IdunBattle.Entities.Effects.Loki.GhostEffect$$CreateHandleTriggerAbilitiesInternal"),
    "TimeFluxGhostRemoveOnSourceRemoved":
        (ARRAYSET, "IdunBattle.Entities.Effects.Loki.GhostEffect$$CreateHandleTriggerAbilitiesInternal"),
    "EchoesFromTheWarpGhostEffectRevive":
        (TARGETS, "IdunBattle.Entities.Effects.Loki.GhostEffect$$CreateTargetTrigger"),
    "EchoesGhostRemoveOnSourceMoves":
        (ARRAYSET, "IdunBattle.Entities.Effects.Loki.GhostEffect$$CreateHandleTriggerAbilitiesInternal"),
    "EchoesGhostRemoveOnUnitAdded":
        (ARRAYSET, "IdunBattle.Entities.Effects.Loki.GhostEffect$$CreateHandleTriggerAbilitiesInternal"),
    "EchoesGhostRemoveOnUnitEnters":
        (ARRAYSET, "IdunBattle.Entities.Effects.Loki.GhostEffect$$CreateHandleTriggerAbilitiesInternal"),
    "EchoesGhostRemoveOnSourceDeathInactive":
        (ARRAYSET, "IdunBattle.Entities.Effects.Loki.GhostEffect$$CreateHandleTriggerAbilitiesInternal"),
    "EchoesGhostRemoveOnSourceRemoved":
        (ARRAYSET, "IdunBattle.Entities.Effects.Loki.GhostEffect$$CreateHandleTriggerAbilitiesInternal"),
    # #421 -- les SEPT autres classes que le RAIL ignorait. Rails LUS au decompile, pas deduits.
    "ShockAssaultBuffRemove":
        (ARRAYSET, "IdunBattle.Entities.Effects.Loki.ShockAssaultBuffEffect$$CreateRemoveEffectTrigger"),
    "HatefulAssaultAlreadyAttackedRemove":
        (ARRAYSET, "IdunBattle.Entities.Effects.Loki.UntilOfEndTurnEffect$$CreateRemoveEffectTrigger"),
    "WireweaveNetDeactivateOnOwnerTurnStart":
        (ARRAYSET, "IdunBattle.Entities.Effects.PlayerTurnEffect$$CreateHandleTriggerAbilitiesInternal"),
    "WireweaveNetActivateOnOwnerTurnEnd":
        (ARRAYSET, "IdunBattle.Entities.Effects.PlayerTurnEffect$$CreateHandleTriggerAbilitiesInternal"),
    "WireweaveNetCounterAttack":
        (TARGETS, "IdunBattle.Entities.Effects.CounterAttackEffect$$CreateTargetTrigger"),
    # #962 -- les DEUX autres membres portes de la famille CONTRE-ATTAQUE (`GrimRetribution` et
    # `UnwaveringSentinel`), entres au registre sans rail declare. Rails IDENTIQUES a ceux de
    # `WireweaveNet` ci-dessus, et ce n'est pas une analogie de nom : `frida/classes.tsv` donne les
    # trois `<X>_CounterAttackEffect` comme derivant de `CounterAttackEffect`, et leurs blocs
    # `methodPointers` ne portent AUCUN `CreateTargetTrigger` / `CreateHandleTriggerAbilitiesInternal`
    # propre (seulement `GetCounterAttackTrigger` / `GetCounterAttackCondition` /
    # `GetCounterAttackBehaviour`) -- les deux corps viennent donc des BASES.
    # La riposte est sur le rail TARGETS et LIT le flag (c'est lui qui porte le << une riposte par
    # tour ennemi >>) ; les deux `Triggered()` de boundary de tour sont sur le rail ARRAYSET et ne
    # doivent PAS le lire -- ce sont eux qui RE-ARMENT une instance eteinte.
    "GrimRetributionCounterAttack":
        (TARGETS, "IdunBattle.Entities.Effects.CounterAttackEffect$$CreateTargetTrigger"),
    "GrimRetributionActivateOnEnemyTurnStart":
        (ARRAYSET, "IdunBattle.Entities.Effects.PlayerTurnEffect$$CreateHandleTriggerAbilitiesInternal"),
    "GrimRetributionDeactivateOnEnemyTurnEnd":
        (ARRAYSET, "IdunBattle.Entities.Effects.PlayerTurnEffect$$CreateHandleTriggerAbilitiesInternal"),
    "UnwaveringSentinelCounterAttack":
        (TARGETS, "IdunBattle.Entities.Effects.CounterAttackEffect$$CreateTargetTrigger"),
    "UnwaveringSentinelActivateOnEnemyTurnStart":
        (ARRAYSET, "IdunBattle.Entities.Effects.PlayerTurnEffect$$CreateHandleTriggerAbilitiesInternal"),
    "UnwaveringSentinelDeactivateOnEnemyTurnEnd":
        (ARRAYSET, "IdunBattle.Entities.Effects.PlayerTurnEffect$$CreateHandleTriggerAbilitiesInternal"),
    # #962 -- les TROIS effet-triggers de `1432 ArmourOfShriekingSouls` (#960). Le bloc
    # `methodPointers` d'`IdunBattle.Entities.Effects.Loki.ArmourOfShriekingSoulsEffect` porte
    # QUATRE corps propres, dont les deux qui tranchent le rail : `CreateTargetTrigger` (decompile :
    # `On(0x16 = TurnStart_Actions, ownerNeedsToBeAlive: 1) op_BitwiseAnd <DSLTriggers+0x28 =
    # IsTurnOf(Owner)>`) pour le SAIGNEMENT, et `CreateHandleTriggerAbilitiesInternal` pour les deux
    # `Triggered()` (resurrection de Lucius au retrait, retrait de l'effet au retour de Lucius).
    # ⚠ Le gate `IsActive` du rail TARGETS MANQUAIT au saignement : pose dans le meme commit
    # (`_elated_instance(...).active`), exactement comme #547-r2 l'avait fait pour `BloodChalice`.
    "ArmourOfShriekingSoulsDrainOnTurnStart":
        (TARGETS, "IdunBattle.Entities.Effects.Loki.ArmourOfShriekingSoulsEffect$$CreateTargetTrigger"),
    "ArmourOfShriekingSoulsResurrectOnRemoved":
        (ARRAYSET,
         "IdunBattle.Entities.Effects.Loki.ArmourOfShriekingSoulsEffect$$CreateHandleTriggerAbilitiesInternal"),
    "ArmourOfShriekingSoulsRemoveOnSourceResurrected":
        (ARRAYSET,
         "IdunBattle.Entities.Effects.Loki.ArmourOfShriekingSoulsEffect$$CreateHandleTriggerAbilitiesInternal"),
    # #962 (second lot, apporte par le REBASE) -- les trois entrees de #961. Toutes viennent d'un
    # `$$CreateRemoveEffectTrigger`, que `IdunBattle.Entities.Effects.BaseEffect$$
    # CreateHandleTriggerAbilities` GREFFE sur le MEME `ArraySet` que les `Triggered()` : rail
    # ARRAYSET, AUCUN gate `IsActive` natif, donc ils ne doivent PAS le lire (meme forme exacte que
    # `HatefulAssaultAlreadyAttackedRemove` ci-dessus). Les DEUX classes `TimesplinterMantle*`
    # partagent un seul corps natif : le natif y exprime une DISJONCTION
    # (`On(9 = Attack) & get_OwnerIsTarget & IsUnit(Caster@+0x48)` op_BitwiseOr `On(0x17 = TurnEnd)`)
    # que le port doit scinder, le registre etant indexe par `event_id`.
    "TimesplinterMantleDamageReductionRemoveOnAttack":
        (ARRAYSET,
         "IdunBattle.Entities.Effects.Loki.TimesplinterMantle_DamageReductionEffect$$CreateRemoveEffectTrigger"),
    "TimesplinterMantleDamageReductionRemoveOnTurnEnd":
        (ARRAYSET,
         "IdunBattle.Entities.Effects.Loki.TimesplinterMantle_DamageReductionEffect$$CreateRemoveEffectTrigger"),
    "LivingLightningMovingRemoveOnArrived":
        (ARRAYSET,
         "IdunBattle.Entities.Effects.Loki.LivingLightning_MovingEffect$$CreateRemoveEffectTrigger"),
    # #1006 -- `1497 Maugetar_HasNotMoved`, relique unique d'`eldarMauganRa`. MEME forme exacte que
    # les trois entrees ci-dessus : un `$$CreateRemoveEffectTrigger` (`On(0x1f = PreUnitMove,
    # ownerNeedsToBeAlive: true) & get_OwnerIsActor`) que `IdunBattle.Entities.Effects.BaseEffect$$
    # CreateHandleTriggerAbilities` GREFFE sur le MEME `ArraySet` que les `Triggered()` -> rail
    # ARRAYSET, AUCUN gate `IsActive` natif, donc le port ne doit PAS lire le flag.
    "MaugetarHasNotMovedRemoveOnMove":
        (ARRAYSET,
         "IdunBattle.Entities.Effects.Loki.Maugetar_HasNotMovedEffect$$CreateRemoveEffectTrigger"),
    # #962 (troisieme lot, apporte par le REBASE) -- `HealingBalmsDelayedHeal` (`1508`, #966/#967).
    # Rail TARGETS : le bloc `methodPointers` d'`IdunBattle.Entities.Effects.Loki.HealingBalmsEffect`
    # porte `CreateTargetTrigger` ET `CreateTargetTriggerBehaviour` (verifie au binaire), et le port
    # LIT deja le flag -- c'est la seule des classes de ce lot qui arrivait avec son gate.
    "HealingBalmsDelayedHeal":
        (TARGETS, "IdunBattle.Entities.Effects.Loki.HealingBalmsEffect$$CreateTargetTrigger"),
    "HarlequinsPanoplyIgnoreHitsRemove":
        (TARGETS, "IdunBattle.Entities.Effects.Loki.HarlequinsPanoply_IgnoreHitsEffect$$CreateTargetTrigger"),
    # #432 -- 1147 TerminatorArmour_ReduceDmg. La CONSOMMATION vient de `CreateTargetTrigger` (rail
    # TARGETS -> gate `IsActive` natif -> DOIT lire le flag) ; les TROIS autres viennent de
    # l'`ArraySet` (`PlayerTurnEffect$$CreateHandleTriggerAbilitiesInternal` pour la fenetre de tour,
    # `TerminatorArmour_ReduceDmg_Effect$$CreateHandleTriggerAbilitiesInternal` pour le `On(0x3e)`)
    # -> rail ARRAYSET, AUCUN gate natif, donc ils ne doivent PAS le lire (c'est ce rail qui
    # RE-ACTIVE l'armure eteinte).
    "TerminatorArmourDeactivateOnAttack":
        (TARGETS, "IdunBattle.Entities.Effects.Loki.TerminatorArmour_ReduceDmg_Effect$$CreateTargetTrigger"),
    "TerminatorArmourActivateOnTurnStart":
        (ARRAYSET, "IdunBattle.Entities.Effects.PlayerTurnEffect$$CreateHandleTriggerAbilitiesInternal"),
    "TerminatorArmourDeactivateOnTurnEnd":
        (ARRAYSET, "IdunBattle.Entities.Effects.PlayerTurnEffect$$CreateHandleTriggerAbilitiesInternal"),
    "TerminatorArmourActivateOnEffectAdded":
        (ARRAYSET, "IdunBattle.Entities.Effects.Loki.TerminatorArmour_ReduceDmg_Effect$$CreateHandleTriggerAbilitiesInternal"),
    # 1098 : la classe n'a AUCUNE methode a son nom (corps dedupliques). Rail tranche par deux
    # lectures independantes, cf. le module `loki/ramming_speed.py` -- `BaseEffect$$
    # CreateHandleTriggerAbilities` teste `if (trigger != 0)` sur le slot `+0x5a8` alors que
    # `BaseEffect$$CreateTargetTrigger` rend NON nul (donc `+0x5a8` = `CreateRemoveEffectTrigger`),
    # et la partition mesuree `CreateTargetTrigger(Behaviour)` / `CreateRemoveEffectTrigger` est
    # d'intersection VIDE sur tout le binaire (28 / 26 / 16 classes).
    "RammingSpeedExtraExplodeRemove":
        (TARGETS, "IdunBattleLogic.Entities.Abilities.Active.Loki.RammingSpeed_ExtraExplodeEffect (bloc methodPointers)"),
    # #448-r2 -- les QUATRE `Triggered()` d'`ATeleportingEffect` + le trigger UNIQUE de son effet
    # compagnon. Tous rail ARRAYSET : ils viennent de `CreateHandleTriggerAbilitiesInternal`, donc
    # AUCUN gate `IsActive` natif -> ils ne doivent PAS lire le flag.
    "TeleportStrikeTeleportingInRemoveOnAfterMove":
        (ARRAYSET, "IdunBattle.Entities.Effects.Loki.ATeleportingEffect$$CreateHandleTriggerAbilitiesInternal"),
    "TeleportStrikeTeleportingInRemoveOnPreUnitAbility":
        (ARRAYSET, "IdunBattle.Entities.Effects.Loki.ATeleportingEffect$$CreateHandleTriggerAbilitiesInternal"),
    "TeleportStrikeTeleportingInRemoveOnUnitFinishedTurn":
        (ARRAYSET, "IdunBattle.Entities.Effects.Loki.ATeleportingEffect$$CreateHandleTriggerAbilitiesInternal"),
    "TeleportStrikeTeleportingInAddMovingOnPreMove":
        (ARRAYSET, "IdunBattle.Entities.Effects.Loki.ATeleportingEffect$$CreateHandleTriggerAbilitiesInternal"),
    "TeleportStrikeMovingRemoveOnAfterMove":
        (ARRAYSET, "IdunBattleLogic.Effects.TeleportMovingEffect$$CreateHandleTriggerAbilitiesInternal"),
    # Les DEUX autres derivees d'`ATeleportingEffect` inscrites au registre (#448-r2b pour 1140,
    # #448-r2c pour 1238/1241). MEME artefact natif que les cinq lignes ci-dessus, mot pour mot :
    # les quatre `Triggered()` viennent du `CreateHandleTriggerAbilitiesInternal` de la BASE (aucune
    # des deux ne le surcharge -- verifie au runtime par `resolveMethodPtr`, il resout a la
    # profondeur 1 sur `ATeleportingEffect`), et le `*_Moving` de `TeleportMovingEffect`. Rail
    # ARRAYSET => AUCUN gate `IsActive` natif => le port ne doit PAS lire le flag.
    "StormboyzStrikeTeleportingInRemoveOnAfterMove":
        (ARRAYSET, "IdunBattle.Entities.Effects.Loki.ATeleportingEffect$$CreateHandleTriggerAbilitiesInternal"),
    "StormboyzStrikeTeleportingInRemoveOnPreUnitAbility":
        (ARRAYSET, "IdunBattle.Entities.Effects.Loki.ATeleportingEffect$$CreateHandleTriggerAbilitiesInternal"),
    "StormboyzStrikeTeleportingInRemoveOnUnitFinishedTurn":
        (ARRAYSET, "IdunBattle.Entities.Effects.Loki.ATeleportingEffect$$CreateHandleTriggerAbilitiesInternal"),
    "StormboyzStrikeTeleportingInAddMovingOnPreMove":
        (ARRAYSET, "IdunBattle.Entities.Effects.Loki.ATeleportingEffect$$CreateHandleTriggerAbilitiesInternal"),
    # #448-r2c (1238 / 1241) -- MEMES DEUX fabriques natives que 1035 / 1036, donc memes rails.
    # La parente est tranchee par `data/symbols/<build>/frida/classes.tsv` et NON par le nom du
    # ctor : `FearOfTheUnseen_TeleportingInEffect$$.ctor` appelle un corps que ghidra nomme
    # `APsychicStalkEffect$$.ctor` (corps DEDUPLIQUE), alors que le champ parent dit
    # `IdunBattle.Entities.Effects.Loki.ATeleportingEffect`. Lire la STRUCTURE, jamais le nom.
    #
    # ⚠ Le vslot `+0x738` (surcharge `FearOfTheUnseen_TeleportingInEffect$$GetAdditionalRemoveTriggers`
    # = `AmountIsEqual(EffectRemainingTurns(EffectSelf), Direct(1))`) est conjoint aux QUATRE
    # `Triggered()`, **T4 compris** -- lu au decompile, 4 occurrences de `(**(code **)(*in_RDX +
    # 0x738))()` dans `ATeleportingEffect$$CreateHandleTriggerAbilitiesInternal`. C'est un noeud de
    # l'ARBRE, pas un gate d'evaluation : il ne change donc PAS le rail, et n'autorise aucune lecture
    # du flag `IsActive`.
    "FearOfTheUnseenTeleportingInRemoveOnAfterMove":
        (ARRAYSET, "IdunBattle.Entities.Effects.Loki.ATeleportingEffect$$CreateHandleTriggerAbilitiesInternal"),
    "FearOfTheUnseenTeleportingInRemoveOnPreUnitAbility":
        (ARRAYSET, "IdunBattle.Entities.Effects.Loki.ATeleportingEffect$$CreateHandleTriggerAbilitiesInternal"),
    "FearOfTheUnseenTeleportingInRemoveOnUnitFinishedTurn":
        (ARRAYSET, "IdunBattle.Entities.Effects.Loki.ATeleportingEffect$$CreateHandleTriggerAbilitiesInternal"),
    "FearOfTheUnseenTeleportingInAddMovingOnPreMove":
        (ARRAYSET, "IdunBattle.Entities.Effects.Loki.ATeleportingEffect$$CreateHandleTriggerAbilitiesInternal"),
    "FearOfTheUnseenMovingRemoveOnAfterMove":
        (ARRAYSET, "IdunBattleLogic.Effects.TeleportMovingEffect$$CreateHandleTriggerAbilitiesInternal"),
    # #448-r2d -- la QUATRIEME derivee (`1573`) et son `*_Moving` (`1574`). MEME `ArraySet`, MEME
    # rail : la specialisation ne porte que sur deux vslots (`GetMovingEffectType` = Nullable(0x626)
    # et `GetCustomMovingEffectCondition`), pas sur la provenance des triggers.
    "TitanhammerSquadTeleportingInRemoveOnAfterMove":
        (ARRAYSET, "IdunBattle.Entities.Effects.Loki.ATeleportingEffect$$CreateHandleTriggerAbilitiesInternal"),
    "TitanhammerSquadTeleportingInRemoveOnPreUnitAbility":
        (ARRAYSET, "IdunBattle.Entities.Effects.Loki.ATeleportingEffect$$CreateHandleTriggerAbilitiesInternal"),
    "TitanhammerSquadTeleportingInRemoveOnUnitFinishedTurn":
        (ARRAYSET, "IdunBattle.Entities.Effects.Loki.ATeleportingEffect$$CreateHandleTriggerAbilitiesInternal"),
    "TitanhammerSquadTeleportingInAddMovingOnPreMove":
        (ARRAYSET, "IdunBattle.Entities.Effects.Loki.ATeleportingEffect$$CreateHandleTriggerAbilitiesInternal"),
    "TitanhammerSquadMovingRemoveOnAfterMove":
        (ARRAYSET, "IdunBattleLogic.Effects.TeleportMovingEffect$$CreateHandleTriggerAbilitiesInternal"),
    # #419-r1-tr9-r4-r1-r2-r1 -- `LegendaryCommander_ExtraHits` (1395). Rail TARGETS : le trigger
    # vient de `$$CreateTargetTrigger` (`On(0xa = AttackDamageAttack) & IsValidAttack(Effect@0x38)`),
    # donc `EvaluateEffectTriggerTargets` lit `IsActive` avant de l'evaluer -> le port le lit aussi.
    "LegendaryCommanderExtraHitsMarkCaster":
        (TARGETS, "IdunBattle.Entities.Effects.Loki.LegendaryCommander_ExtraHitsEffect$$CreateTargetTrigger"),
}

# Classes du rail ARRAYSET qui lisent QUAND MEME le flag -- non par gate d'evaluation, mais
# parce que leur PROPRE ARBRE porte un noeud qui le lit (`DSLFactory$$IsEffectActive`,
# `DSLFactory$$HasEffect(..., onlyActive=1)`). Lire n'y est donc PAS une infidelite.
ARRAYSET_READS_BY_TREE = {
    "TimeFluxGhostRemoveOnSourceDeathInactive":   # `NOT IsEffectActive(self@0x150)`
        "IdunBattleLogic.Entities.DSLFactory$$IsEffectActive",
    "EchoesGhostRemoveOnSourceDeathInactive":     # idem -- MEME arbre natif, 2e effectType
        "IdunBattleLogic.Entities.DSLFactory$$IsEffectActive",
    "EarlyWarningOverrideHitReductionPurge":  # `NOT HasEffect(Owner, 0x3f1, onlyActive=1, Both)`
        "IdunBattleLogic.Entities.DSLFactory$$HasEffect",
    # #943 -- MEME arbre natif (Triggered #2 de `AReactivateOverwatchEffect`), second porteur : la
    # lecture du flag vient du noeud `HasEffect(..., onlyActive=1)` de l'arbre, pas d'un gate
    # d'evaluation. Le port herite du `matches` de la base, donc de la MEME lecture.
    "InescapableDeathHitReductionPurge":      # `NOT HasEffect(Owner, 0x3f1, onlyActive=1, Both)`
        "IdunBattleLogic.Entities.DSLFactory$$HasEffect",
}

# GAPS ATTENDUS : rail a gate natif dont le port ne lit pas le flag. Toute entree qui SORT ou
# ENTRE ici doit etre justifiee.
#
# Etat des lieux #229 (2026-07-29) : 6 entrees. CINQ RESORPTIONS INDEPENDANTES, toutes du
# 2026-07-29 (fusionnees au rebase) :
#
#   * `HazeOfCorruptionDamageTransferTrigger` (1077) -- rail TARGETS : son `matches` lit
#     desormais `inst.active`, mirror direct de la double lecture d'`IsActive` par
#     `IdunBattle.Operations.EvaluateTriggerOperation$$EvaluateEffectTriggerTargets`.
#
#   * `MasterOfTheTutelariesSummonAbility` (1197, #231) -- rail APPLY_REVERT, qui NE SE GATE PAS
#     PAREIL, et c'est le piege a ne pas transposer : le conjoint `HasEffect` de
#     `IdunBattleLogic.Entities.Abilities.Triggered.Loki.MasterOfTheTutelaries_SummonAbility$$
#     CreateTrigger` passe `onlyActive=**0**` -- l'arbre ne teste QUE la presence. L'activite mord
#     par un AUTRE chemin : `IdunBattle.Operations.RefreshEffectsOperation$$DeactivateEffect`
#     enchaine sur `UpdateEffectTargets` avec une liste de cibles VIDE ->
#     `RemoveTargetsFromEffect` -> `Revert` ->
#     `IdunBattle.Entities.Effects.Loki.MasterOfTheTutelariesEffect$$RevertInternal` ->
#     `RemoveTriggeredAbility(0x495)`. Effet inactif => triggered 1173 RETIREE. Le gate offline
#     (`_master_effect_is_carried_and_active`) mirroire CE couplage, pas un `onlyActive`.
#     Cf. `docs/rl/case-231-master-tutelaries-active-gate.md`.
#
#   * `AnvilShieldFrozenAdvantageExpire` (1201, #231) -- rail TARGETS : gate
#     `_frozen_advantage_flag_is_set` (`triggers/loki/anvil_shield.py`), meme modele que 1009.
#     Cf. `docs/rl/case-231-effect-1201-active-gate.md`.
#
#   * `RitesOfMorkaiReviveTrigger` (1502) -- rail TARGETS : gate pose dans son `matches`
#     (`triggers/loki/rites_of_morkai.py`). Cf. `docs/rl/case-229-1502-rites-of-morkai-active-gate.md`.
#
#   * `ReanimationBeamReviveTrigger` (1547, `case-1547`) -- rail TARGETS : son `matches` lit le
#     flag de l'instance 1547 AVANT de deleguer a `_ReviveEffectCore.matches`.
#     Cf. `docs/rl/case-1547-reanimation-beam-active-gate.md`.
#
#   1502 et 1547 sont des JUMEAUX : meme base `ReviveEffect`, meme rail, deux taches distinctes.
#   Chacun a pose son gate SUR SA PROPRE CLASSE, PAS sur la base partagee `ReviveEffectTrigger` --
#   c'est ce qui a permis aux deux de lander sans se marcher dessus. Les DEUX fiches concordent sur
#   la desambiguisation des deux lectures de `+0x5c` : la 1re, sur le composant recu, est un
#   FAST-PATH qu'un effet INACTIF TRAVERSE ; **la 2e, par cible, sur le composant RE-FETCH depuis
#   l'entite-effet, est LE gate**. Le jour ou l'on voudra factoriser, remonter le gate dans
#   `ReviveEffectTrigger.matches` est mecanique.
#
# #421 (2026-08-01) -- LE ZERO. Les quatre derniers gaps ont ete poses, tous rail TARGETS, tous
# decouverts en COMPLETANT le RAIL (le probe etait muet sur eux : ils n'y figuraient pas) :
#
#   * `TimeFluxGhostEffectRevive` (1186) et `EchoesFromTheWarpGhostEffectRevive` (1284) -- l'ancien
#     `GhostEffectRevive` d'`EXPECTED_GAPS`, scinde en DEUX par #366-r1. Le gap n'avait pas ete
#     resorbe : il avait DOUBLE, et l'entree perimee le faisait passer pour resolu. Gate pose sur la
#     BASE `GhostEffectRevive` (`triggers/loki/ghost_revive.py`), donc sur les deux instanciations.
#   * `HarlequinsPanoplyIgnoreHitsRemove` (1227) -- classe entree au registre par #366-r1 avec un
#     rail MAL LU (« monte par `CreateHandleTriggerAbilities` ») ; c'est un `CreateTargetTrigger`.
#   * `RammingSpeedExtraExplodeRemove` (1098) -- rail laisse AMBIGU par `case-389`, tranche ici.
#
# ⚠ Zero n'est pas un acquis, c'est un CLIQUET, et il ne tient QUE si le RAIL couvre le registre --
# une classe hors RAIL n'est comptee dans AUCUNE des deux listes ci-dessous. Le cliquet de couverture
# est `probe_421_rail_covers_registry.py` ; le faire passer AVANT celui-ci.
EXPECTED_GAPS: set[str] = set()


def _scan(tree: ast.AST) -> tuple[bool, bool, set]:
    """(lit `.active`, lit `.active_effects`, fonctions appelees). Couvre l'acces par attribut
    ET par `getattr(x, "active", ...)` -- la forme qu'emploie `GhostRemoveOnSourceDeathInactive`.

    Le 3e membre melange DEUX formes d'appel, et il le faut : un nom NU (`str`, ex. `_flag_is_set`)
    et un appel QUALIFIE (`(alias, attribut)`, ex. `_ca.flag_is_set`). La seconde n'etait pas
    distinguee -- seul l'attribut etait retenu -- donc une delegation vers un FOYER PARTAGE se
    perdait : `getattr(<module appelant>, "flag_is_set")` n'existe evidemment pas. cf. #962.
    """
    direct = indirect = False
    called: set = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Attribute):
            direct |= node.attr == "active"
            indirect |= node.attr == "active_effects"
        elif isinstance(node, ast.Call):
            if isinstance(node.func, ast.Name):
                called.add(node.func.id)
                if node.func.id == "getattr" and len(node.args) >= 2 \
                        and isinstance(node.args[1], ast.Constant):
                    direct |= node.args[1].value == "active"
                    indirect |= node.args[1].value == "active_effects"
            elif isinstance(node.func, ast.Attribute):
                called.add(node.func.attr)
                if isinstance(node.func.value, ast.Name):
                    called.add((node.func.value.id, node.func.attr))
    return direct, indirect, called


def _reads_active(cls: type) -> str:
    """Le GATE de la classe lit-il le flag ? Analyse AST du seul `matches` (pas de grep : ni
    commentaire ni docstring ne compte), plus les helpers du meme module qu'il appelle -- y
    compris les methodes (`_instance`, `_source`...). Renvoie 'direct' (`<inst>.active`),
    'via active_effects' (le lecteur qui conjugue FLAG + `CreateActiveCondition`), ou ''.

    POURQUOI `matches` SEUL : le gate natif (`EvaluateEffectTriggerTargets`) s'applique AVANT
    `ShouldTrigger`, donc son pendant offline est la condition, jamais le behaviour. Les
    `execute_behaviour` d'`ActivateEffect`/`DeactivateEffect` (1009, 1324) TOUCHENT le flag mais
    en ECRITURE -- `if bool(e.active) != value` y mirroire le no-op natif de
    `RefreshEffectsOperation$$DeactivateEffect`, ce n'est pas un gate. Les compter rendrait le
    cliquet faux."""
    fn = getattr(cls, "matches", None)        # resolu par la MRO (ex. `_ReviveEffectCore.matches`)
    if fn is None:
        return ""
    try:
        direct, indirect, called = _scan(ast.parse(_dedent(inspect.getsource(fn))))
    except (OSError, TypeError, SyntaxError):
        return ""
    owner_mod = getattr(fn, "__module__", cls.__module__)
    file = [(owner_mod, called)]
    vus: set = set()
    while file:
        mod_nom, noms = file.pop()
        mod = sys.modules.get(mod_nom)
        for name in noms:
            target = _resoudre_appele(mod, cls, name)
            if not (inspect.isfunction(target) or inspect.ismethod(target)):
                continue
            cible_mod = getattr(target, "__module__", None)
            if not _suivable(name, cible_mod, mod_nom):
                continue
            cle = (cible_mod, getattr(target, "__qualname__", str(target)))
            if cle in vus:
                continue
            vus.add(cle)
            try:
                d, i, c = _scan(ast.parse(_dedent(inspect.getsource(target))))
            except (OSError, TypeError, SyntaxError):
                continue
            direct |= d
            indirect |= i
            file.append((cible_mod, c))       # la delegation peut faire plus d'un saut
    return "direct" if direct else ("via active_effects" if indirect else "")


def _suivable(name, cible_mod: str | None, mod_nom: str) -> bool:
    """DEUX regimes, et l'asymetrie est le coeur de ce cliquet (#962).

      * appel NU (`_flag_is_set(...)`) -> le module APPELANT, comme depuis #229. L'elargir a tout
        `engine.**` fabrique des faux positifs : le `matches` de `PhoenixGemReviveAbility` appelle
        `can_be_revived`, qui lit le `.active` d'AUTRES effets -- ce n'est pas le gate
        `EffectComponent.IsActive @+0x5c` de SON instance, et le compter classerait a tort le rail
        ARRAYSET en << lit le flag >>.
      * appel QUALIFIE (`_ca.flag_is_set(...)`) -> tout `engine.**`. C'est une DELEGATION EXPLICITE
        vers un foyer, et depuis #946 les quatre lectures/ecritures de `PlayerTurnEffect` vivent
        precisement dans un foyer partage (`triggers/loki/counter_attack.py`) parce qu'elles
        n'appartiennent a aucun des trois membres de la famille. Borner au module appelant
        interdisait donc tout foyer partage : `WireweaveNetCounterAttack` (rail TARGETS) etait
        declare SANS gate alors qu'il en a un, et `master` en etait ROUGE.
    """
    if isinstance(name, tuple):
        return (cible_mod or "").startswith("engine.")
    return cible_mod == mod_nom


def _resoudre_appele(mod, cls, name):
    """Un element de `called` : nom NU (`str`) ou appel QUALIFIE (`(alias, attribut)`). Pour le
    second, l'alias est resolu sur le module APPELANT (`import <module> as <alias>`, forme B), donc
    la delegation vers un foyer partage devient suivable."""
    if isinstance(name, tuple):
        base = getattr(mod, name[0], None)
        return getattr(base, name[1], None) if base is not None else None
    return getattr(mod, name, None) or getattr(cls, name, None)


def _dedent(src: str) -> str:
    lines = src.splitlines()
    pad = min((len(l) - len(l.lstrip()) for l in lines if l.strip()), default=0)
    return "\n".join(l[pad:] if len(l) >= pad else l for l in lines)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--verbose", action="store_true")
    args = ap.parse_args()

    rows = []
    for etype, classes in sorted(EFFECT_TRIGGERS.items()):
        for cls in classes:
            name = cls.__name__
            rail, symbol = RAIL.get(name, ("?", "?"))
            reads = _reads_active(cls)
            tile = bool(getattr(cls, "owner_is_tile", False))
            rows.append((etype, name, rail, tile, reads, symbol))

    print("=== #229 EFFECT_TRIGGERS : lecture du flag EffectComponent.IsActive ===")
    print("effectTypes = %d ; classes = %d" % (len(EFFECT_TRIGGERS), len(rows)))
    print("")
    print("%-6s %-44s %-13s %-6s %s" % ("type", "classe portee", "rail", "tuile", "lit e.active"))
    for etype, name, rail, tile, reads, _sym in rows:
        print("%-6d %-44s %-13s %-6s %s" % (etype, name, rail, "yes" if tile else "-",
                                            reads or "no"))

    unknown = [n for _e, n, r, _t, _rd, _s in rows if r == "?"]
    must_read = [(e, n) for e, n, r, _t, rd, _s in rows
                 if r in (TARGETS, APPLY_REVERT) and not rd]
    must_not_read = [(e, n) for e, n, r, _t, rd, _s in rows
                     if r == ARRAYSET and rd and n not in ARRAYSET_READS_BY_TREE]

    print("")
    print("-- rail a gate natif (TARGETS/APPLY_REVERT) SANS lecture du flag : %d" % len(must_read))
    for etype, name in must_read:
        print("   %-6d %s" % (etype, name))
    print("-- rail ARRAYSET qui lit le flag hors noeud d'arbre : %d" % len(must_not_read))
    for etype, name in must_not_read:
        print("   %-6d %s" % (etype, name))

    # --- CLIQUETS -------------------------------------------------------------------------
    ok = True
    if unknown:
        print("FAIL: classe(s) sans rail declare (completer RAIL) : %s" % ", ".join(unknown))
        ok = False
    got = {n for _e, n in must_read}
    if got != EXPECTED_GAPS:
        print("FAIL: la liste des gaps a change.")
        print("      nouveaux : %s" % sorted(got - EXPECTED_GAPS))
        print("      resorbes : %s" % sorted(EXPECTED_GAPS - got))
        ok = False
    if must_not_read:
        print("FAIL: un trigger du rail ARRAYSET gate sur le flag -> infidelite "
              "(EvaluateEffectTriggerEffectAbilities n'a AUCUN gate IsActive).")
        ok = False
    print("")
    print("RESULT: %s" % ("OK" if ok else "FAIL"))
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
