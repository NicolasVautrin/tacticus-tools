"""case-366-r1-camo-seed -- INVENTAIRE du gisement << effet condition-gated absent de la capture >>.

LA QUESTION, exactement. Un effet dont la `CreateActiveCondition` est FAUSSE au moment de la
capture est DROPPE par le canal `decisionView` PAR DEFAUT (`readEffectsByUnit` filtre
`EffectComponent.IsActive`). Un etat charge depuis ce canal n'a donc AUCUNE instance -- et si la
simulation fait ensuite entrer l'effet dans sa condition, le port n'a RIEN a rallumer, alors que le
natif, lui, n'a jamais cesse de porter l'entite-effet.

⚠ LA DISTINCTION QUI FONDE TOUT : **INERTE n'est pas ABSENT**. Le natif POSE l'instance et la laisse
inerte ; c'est le CAPTEUR qui la cache. Mesure directe (`probe_366_r1_camo_seed.py`) : hors couvert,
canal DEFAUT = pas de `1014`, canal `includeInactive` = `1014` avec `active: false`.

DEUX CONJOINTS decident si une classe est EXPOSEE, et il faut les DEUX :

  (A) POSE -- le natif materialise-t-il l'instance meme quand la condition est fausse ? C'est le
      `<X>Ability$$CreateBehaviour` qui tranche, PAS le comportement observe : un `AddEffect(...)`
      NU (sans `If(...)`) sur le trigger d'INIT pose inconditionnellement. Si la pose est un
      vecteur RUNTIME (attaque, cast), l'absence a la capture est FIDELE : le natif n'a pas
      d'instance non plus.
  (B) BASCULE -- la condition peut-elle passer de FAUSSE a VRAIE pendant la simulation ? Une
      condition sur un TRAIT ne bascule jamais ; une condition sur la position, les PV, le tour ou
      un effet voisin, si.

TROIS COMPENSATIONS existent cote port, et elles sont MECANIQUEMENT lisibles :
  * `factory.ABILITY_INIT_OWNER_EFFECTS` (+ `ABILITY_OWNER_EFFECTS`) -> `spawn._seed_ability_owner_
    effects`, appele par `runner/snapshot.py::load_state` : materialise l'instance quel que soit le
    canal ;
  * le canal `includeInactive` lui-meme (`snapshot.decision_view_seed_body`), quand le SITE DE
    CAPTURE le demande ;
  * `BaseEffect.active_condition_ported` + `seed_witness_effect` -> pendant DECISION
    (`playbook/scene.py::_seed_condition_gated_owner_effects`).

Ce probe RE-DERIVE la partie mecanique depuis le code (jamais un compte recopie) et la croise avec
le verdict de RE (table `POSE_VECTOR`, un symbole natif par entree). Il **ECHOUE** (rc 1) si une
classe surchargeant `is_active` n'a pas son verdict de pose : c'est le CLIQUET -- toute classe qui
entre au registre doit avoir ete lue au decompile sur cet axe.

Usage :
    python probe_366_camo_seed_inventory.py            # table + comptes + cliquet
    python probe_366_camo_seed_inventory.py --csv      # une ligne par classe

ASCII only (cp1252). Aucun RPC : 100 % offline.
"""
from __future__ import annotations

import argparse
import sys

#: Ce qui doit changer pour que ce cliquet puisse changer d'avis.
DECLENCHEUR = {
    "chemins": ("scripts/python/probe_366_camo_seed_inventory.py",
                "scripts/python/engine/*.py", "scripts/python/engine/**/*.py",
                "scripts/python/*.py",
                "data/seed-bc.json"),
    "build": False,
    "toujours": False,
    "raison": (
        "Le verdict est `EFFECT_CLASSES` moins celles dont `is_active` est encore celui de "
        "`BaseEffect` : il depend donc du registre (`engine/entities/effects/factory.py`), de la "
        "BASE, de toute classe qui surcharge `is_active` OU QUI CESSE DE LE FAIRE, et des deux "
        "tables de seed (ABILITY_INIT_OWNER_EFFECTS / ABILITY_OWNER_EFFECTS) ; la table de RE "
        "(POSE_VECTOR) vit dans son propre source. Le glob n'est PAS borne a "
        "`engine/entities/effects/**` : une classe inscrite peut vivre ailleurs, et la fermeture "
        "d'imports MESUREE de `scan()` est de 99 modules engine/ plus `gameconfig.py` et "
        "`hexgeo.py` a la racine. `data/seed-bc.json` y entre parce que "
        "`engine/services/damage_modifiers.py` le lit AU NIVEAU MODULE (`_DMG_CFG`) et que "
        "`engine/entities/effects/__init__.py` tire ce module -- trouve a la TRACE d'audit, pas a "
        "la lecture. Rien du build : le critere est une identite de fonction Python."),
}

# --------------------------------------------------------------------------------------------
# VERDICT DE RE, par classe d'effet qui surcharge `is_active`. Chaque entree est LUE au
# decompile du `<X>Ability$$CreateBehaviour` (build rnca9r7q6c) -- jamais deduite du nom ni du
# comportement observe.
#
#   pose  : "init"    = `AddEffect`/`AddStaticStatModifierEffectToOwner`/... NU sur le trigger
#                       d'init de l'ability -> l'instance existe TOUJOURS cote natif ;
#           "runtime" = pose par un vecteur d'execution (attaque, cast) -> l'absence a la
#                       capture est FIDELE.
#   flip  : "sim"     = la condition peut passer de FAUSSE a VRAIE pendant la simulation ;
#           "static"  = elle ne bascule pas (trait) ;
#           "one-way" = elle ne bascule que de VRAIE a FAUSSE dans les regimes atteignables.
# --------------------------------------------------------------------------------------------
POSE_VECTOR: dict[str, tuple[str, str, str, str]] = {
    # effet                                   pose       flip       symbole natif de la POSE / condition
    # #589-r1-r1-r2-r1 -- `AmuletOfTheVoidwyrmAbility` derive d'`AOwnerEffectTriggeredAbility`
    # (`classes.tsv`) et n'en surcharge QUE `GetEffectType` (-> 0x5b4). Le corps de BASE est
    # `If(<CreateCondition>, AddEffect(0x5b4, AbilityState(Owner, <cette ability>), source = Owner,
    # targets = Owner, turns = <zeroe>))` sur `CreateTrigger = OnOwnerSpecificAbilityInit` ; la
    # `CreateCondition` de base rend `<DSLTriggers+0x70>`, une instance de la MEME classe que
    # `<+0x40>` (dont `<+0x48>` est le `op_LogicalNot`), donc la pose est INCONDITIONNELLE.
    # MEME vecteur exact qu'`HammerOfWrath_ConditionalDamage` et `MartialSuperiority_Visual`.
    "AmuletOfTheVoidwyrm_CritDamageReduction": (
        "init", "sim",
        "IdunBattle.Entities.Abilities.AOwnerEffectTriggeredAbility$$CreateBehaviour"
        " (AmuletOfTheVoidwyrmAbility)",
        "AmountIsGreaterThanZero(summons/decoys allies ADJACENTS -- geometrique)"),
    # #547-r2 -- les DEUX classes entrees par la PR #867 sans verdict de pose. Toutes deux sont
    # posees par le `ExecuteBehaviour` d'une ability ACTIVE (un CAST), jamais par un trigger d'init
    # : leur absence a la capture est donc FIDELE, et le rail de seed n'a rien a couvrir.
    "BloodChalice_ExtraPiercing": (
        "runtime", "static",
        "IdunBattleLogic.Entities.Abilities.Active.BloodChaliceAbility$$ExecuteBehaviour"
        " (AddStaticStatModifierEffect(GetTargets(), 0x559, 0x15 = ExtraPierceMelee, ...))",
        "IsCharging(Owner@0x30, Target@0x60) -- et `Target@ctx+0x10` est ZERO dans le contexte de "
        "`RefreshEffectsOperation$$ShouldBeActive`, donc la condition y est CONSTANTE FAUSSE : "
        "elle ne bascule pas"),
    "MindControl_Taunter": (
        "runtime", "one-way",
        "IdunBattleLogic.Entities.Abilities.Active.Loki.MindControlAbility$$ExecuteBehaviour"
        " (AddBondEffect(0x557 = 1367, targets = cache, bondedEntity = Target))",
        "HasEffect(bonded, 0x1b = 27 Taunted_OnlySpecificTargets, selectionType 6) & "
        "AreEqual(BondedEntityFromEffect(EffectFromOwner(bonded, 0x1b)), Owner@0x30) -- le taunt "
        "n'est pose QU'UNE fois par le cast : une fois perdu il ne revient pas"),
    # #547-r2 -- arrivee avec la PR #874, sans verdict de pose. MEME FORME EXACTE que
    # `AmuletOfTheVoidwyrm_CritDamageReduction` ci-dessus, et ce n'est pas une ressemblance de nom :
    # `classes.tsv` (build `rnca9r7q6c`) donne
    # `IdunBattleLogic.Entities.Abilities.Triggered.Loki.SupaCyborkBodyAbility` comme derivant de
    # `IdunBattle.Entities.Abilities.AOwnerEffectTriggeredAbility`, et `methods.tsv` ne lui connait
    # QU'UN corps propre -- `GetEffectType`. Son `CreateBehaviour` est donc celui de la BASE :
    # `If(<CreateCondition>, AddEffect(<GetEffectType>, source = Owner, targets = Owner))` sur
    # `OnOwnerSpecificAbilityInit`, avec une `CreateCondition` de base qui rend le noeud toujours
    # vrai -> pose INCONDITIONNELLE a l'init. Le `.ctor` de l'effet cite `AbilityOrEffect(0x5c3 =
    # 1475 SupaCyborkBody)`, ce qui referme la chaine.
    # `flip: sim` -- `CreateActiveCondition = HasAdjacentEnemies(Owner, Tiles(Owner))` est
    # GEOMETRIQUE : elle rebascule des qu'une unite bouge (le port le dit deja, mot pour mot).
    "SupaCyborkBody_CritDmgReduction": (
        "init", "sim",
        "IdunBattle.Entities.Abilities.AOwnerEffectTriggeredAbility$$CreateBehaviour"
        " (SupaCyborkBodyAbility)",
        "HasAdjacentEnemies(Owner@0x30, Tiles(Owner)) -- geometrique"),
    "AnvilShield_BlockChanceBelowHealthCap": (
        "init", "sim",
        "IdunBattleLogic.Entities.Abilities.Triggered.Loki.AnvilShieldAbility_"
        "ApplyAdditionalBlockAndBlockChance$$CreateBehaviour",
        "HealthPct <= healthCap"),
    "CamoCloak_DmgReduction": (
        "init", "sim",
        "IdunBattleLogic.Entities.Abilities.Active.Loki.CamoCloakAbility$$CreateBehaviour",
        "HasEffect(Owner, 1013) | IsEffectTarget(Owner, 1026)"),
    "ContagionsOfNurgle_ArmorReduction1": (
        "init", "sim",
        "IdunBattleLogic.Entities.Abilities.Active.Loki."
        "ContagionsOfNurgle_AddEffectInitially_Ability$$CreateBehaviour",
        "ContagionsOfNurgleAmount dans [min, max] (aura, geometrique)"),
    "ContagionsOfNurgle_ArmorReduction2": (
        "init", "sim",
        "IdunBattleLogic.Entities.Abilities.Active.Loki."
        "ContagionsOfNurgle_AddEffectInitially_Ability$$CreateBehaviour",
        "ContagionsOfNurgleAmount dans [min, max] (aura, geometrique)"),
    # #943 -- les DEUX effets de `1203 DaemonicPatrons` (#911), entres au registre sans verdict de
    # pose. Ils sont poses par le `ExecuteBehaviour` d'une ability ACTIVE (un CAST sur le CASTER),
    # jamais par un trigger d'init : leur absence a la capture est donc FIDELE, et le rail de seed
    # n'a rien a couvrir. `flip: sim` -- `ADaemonicPatronsEffect$$CreateActiveCondition` compte les
    # ennemis ADJACENTS TAUNTES, donc elle rebascule des qu'une unite bouge ou qu'un taunt tombe.
    "DaemonicPatrons_DmgReduction": (
        "runtime", "sim",
        "IdunBattleLogic.Entities.Abilities.Active.Loki.DaemonicPatronsAbility$$ExecuteBehaviour"
        " (AddEffect(0x5b9 = 1465, targets = Caster))",
        "AmountIsGreaterThanZero(Count(Filter(AdjacentEnemies(Owner@0x30), "
        "HasEffect(It@0x68, 0x1b = 27 Taunted_OnlySpecificTargets, onlyActive: 0)))) -- "
        "geometrique ET dependante du taunt"),
    "DaemonicPatrons_ExtraDamage": (
        "runtime", "sim",
        "IdunBattleLogic.Entities.Abilities.Active.Loki.DaemonicPatronsAbility$$ExecuteBehaviour"
        " (AddEffect(0x5b8 = 1464, targets = Caster))",
        "AmountIsGreaterThanZero(<le MEME compteur que 1465>) -- corps FONDU : condition et "
        "magnitude partagent le compteur, elles ne peuvent pas diverger"),
    "DestroyTheWitch_ExtraDamage": (
        "init", "sim",
        "IdunBattleLogic.Entities.Abilities.Triggered.Loki.DestroyTheWitchAbility$$CreateBehaviour",
        "un Psyker ENNEMI est vivant"),
    "DestroyTheWitch_ExtraMove": (
        "init", "sim",
        "IdunBattleLogic.Entities.Abilities.Triggered.Loki.DestroyTheWitchAbility$$CreateBehaviour",
        "un Psyker ENNEMI est vivant"),
    # #962 -- les DEUX effets de `1314 EnmityForTheUnworthy` (#948), entres au registre sans verdict
    # de pose. `EnmityForTheUnworthyAbility$$CreateBehaviour` est LU verbatim (build `rnca9r7q6c`) :
    #     AddEffect(<DSLBehaviors>, 0x578 = 1400, AbilityStateReference, targets = Owner@<+0x90>+0x30,
    #               turns = null)
    #       op_Addition
    #     AddEffect(<DSLBehaviors>, 0x577 = 1399, AbilityStateReference, targets = Owner, turns = null)
    # AUCUN `If` n'enveloppe les deux `AddEffect` -- la pose est donc INCONDITIONNELLE, et la classe
    # n'a AUCUN `CreateTrigger` propre (bloc `methodPointers` : `CreateBehaviour` seul), donc elle
    # herite `On(AbilityInit) & get_OwnerIsActor` de `BaseTriggeredAbility` -> pose a l'INIT, ce que
    # l'inscription en `ABILITY_INIT_OWNER_EFFECTS` referme. L'absence offline serait un TROU.
    # `flip: sim` -- les deux `CreateActiveCondition` sont
    # `AmountIsGreaterThanZero(<compteur d'adjacents>)`, donc GEOMETRIQUES : elles rebasculent des
    # qu'une unite bouge ou meurt.
    "EnmityForTheUnworthy_ExtraDamage": (
        "init", "sim",
        "IdunBattleLogic.Entities.Abilities.Triggered.Loki."
        "EnmityForTheUnworthyAbility$$CreateBehaviour",
        "AmountIsGreaterThanZero(AdjacentFriendlyDarkaUnitsAmount()) -- "
        "Count(NonSteppableOrObjectUnits(UnitsFromFaction(AdjacentFriends(Owner@0x30), "
        "DarkAngels))), geometrique"),
    "EnmityForTheUnworthy_ExtraDamagePct": (
        "init", "sim",
        "IdunBattleLogic.Entities.Abilities.Triggered.Loki."
        "EnmityForTheUnworthyAbility$$CreateBehaviour",
        "AmountIsGreaterThanZero(AdjacentUnitsAmount()) -- "
        "Count(NonSteppableOrObjectUnits(AdjacentUnits(Owner@0x30))), geometrique"),
    # #962 -- les DEUX auras de `1490 GrimEfficiency` (#959), entrees au registre sans verdict de
    # pose. `GrimEfficiencyAbility$$CreateBehaviour` est LU verbatim (build `rnca9r7q6c`) :
    #     AddDynamicStatModifierEffectToOwner(0x5cf = 1487, statType 0x10 = FixedArmor, turns null,
    #                                         isHidden false)
    #       op_BitwiseAnd
    #     AddDynamicStatModifierEffectToOwner(0x5d0 = 1488, statType 0x1a = ExtraPierce, turns null,
    #                                         isHidden false)
    # AUCUN `If` -- pose INCONDITIONNELLE ; et son `CreateTrigger` est le corps ICF de
    # `OnOwnerSpecificAbilityInit(this.AbilityType)`, d'ou l'inscription en
    # `ABILITY_INIT_OWNER_EFFECTS`. L'absence offline serait donc un TROU.
    # `flip: sim` -- les deux `CreateActiveCondition` sont
    # `HasEffect(EffectSource(Effect@+0x38), <marqueur de STANCE>, onlyActive: 0, Both)`, et les
    # stances du trait `PrioritisedEfficiency` (1059) basculent en cours de partie : les deux auras
    # les PARTITIONNENT, donc elles ne sont jamais actives ensemble.
    "GrimEfficiency_ExtraArmor": (
        "init", "sim",
        "IdunBattleLogic.Entities.Abilities.Triggered.Loki.GrimEfficiencyAbility$$CreateBehaviour",
        "HasEffect(EffectSource(Effect@+0x38), 0x5c7 = 1479 "
        "PrioritisedEfficiency_HostileAcquisition_Stance, onlyActive: 0, targetType 6 = Both)"),
    "GrimEfficiency_ExtraPierce": (
        "init", "sim",
        "IdunBattleLogic.Entities.Abilities.Triggered.Loki.GrimEfficiencyAbility$$CreateBehaviour",
        "HasEffect(EffectSource(Effect@+0x38), 0x5c8 = 1480 "
        "PrioritisedEfficiency_FortifyTakeover_Stance, onlyActive: 0, targetType 6 = Both)"),
    "HammerOfWrath_ConditionalDamage": (
        "init", "sim",
        "IdunBattle.Entities.Abilities.AOwnerEffectTriggeredAbility$$CreateBehaviour",
        "HealthPct <= healthPct"),
    "InescapableAccuracy_extraCritChance": (
        "init", "sim",
        "IdunBattleLogic.Entities.Abilities.Triggered.Loki."
        "InescapableAccuracyAbility$$CreateBehaviour",
        "NOT HasFlag(Owner, Moved)"),
    "InescapableAccuracy_extraCritDmg": (
        "init", "sim",
        "IdunBattleLogic.Entities.Abilities.Triggered.Loki."
        "InescapableAccuracyAbility$$CreateBehaviour",
        "NOT HasFlag(Owner, Moved)"),
    "InescapableAccuracy_overrideHits": (
        "init", "sim",
        "IdunBattleLogic.Entities.Abilities.Triggered.Loki."
        "InescapableAccuracyAbility$$CreateBehaviour",
        "NOT HasFlag(Owner, Moved)"),
    # #943 -- `1459 IntoxicatingElixir` (#919). MEME base et MEME forme qu'`AmuletOfTheVoidwyrm` /
    # `SupaCyborkBody` : `classes.tsv` donne `IntoxicatingElixirAbility` fille
    # d'`AOwnerEffectTriggeredAbility`, qu'elle n'override QUE par `GetEffectType` (`return 0x5b3`,
    # corps ENTIER). Le `CreateBehaviour` joue est donc celui de la BASE --
    # `If(OnOwnerSpecificAbilityInit(0x5b7), AddEffect(0x5b3, source = targets = Owner@0x30))` --
    # donc pose d'init INCONDITIONNELLE : l'instance existe TOUJOURS cote natif.
    # ⚠ Aucune entree `ABILITY_INIT_OWNER_EFFECTS` ne la couvre, et c'est MESURE : le seed lit le KIT
    # gameconfig (`activeAbilities + passiveAbilities`), or c'est une RELIQUE -- elle arrive par
    # `BC.Units[].TertiaryAbility`. `flip: sim` : le compteur est GEOMETRIQUE.
    "IntoxicatingElixir": (
        "init", "sim",
        "IdunBattle.Entities.Abilities.AOwnerEffectTriggeredAbility$$CreateBehaviour"
        " (IntoxicatingElixirAbility)",
        "AmountIsGreaterThanZero(Min(Count(EntitiesWithAnyEffect(SurroundingUnits(Tiles(Owner), "
        "range, includeCenter: 1), [Pinned, Stunned, Taunted_OnlySpecificTargets, ThrillSeekers])), "
        "nrOfUnits)) -- geometrique"),
    "MartialSuperiority_Visual": (
        "init", "sim",
        "IdunBattle.Entities.Abilities.AOwnerEffectTriggeredAbility$$CreateBehaviour"
        " (MartialSuperiorityAddEffectAbility)",
        "NOT IsTurnOf(Owner)"),
    # #943 -- `1461 MawClawsOfThyrax_ExtraCritDmg` (#917). MEME base, MEME forme et MEME mesure de
    # non-couverture que `IntoxicatingElixir` ci-dessus (`MawClawsOfThyraxAbility` n'override que
    # `GetEffectType`, `return 0x5b5`). Pose d'init INCONDITIONNELLE ; compteur GEOMETRIQUE.
    "MawClawsOfThyrax_ExtraCritDmg": (
        "init", "sim",
        "IdunBattle.Entities.Abilities.AOwnerEffectTriggeredAbility$$CreateBehaviour"
        " (MawClawsOfThyraxAbility)",
        "AmountIsGreaterThanZero(Count(Unique(UnitsWithTrait(AdjacentUnits(Owner@0x30), "
        "0x2 = UnitTrait.Summon)))) -- geometrique, et SANS filtre d'equipe"),
    "ModifiedExoarmour_ExtraDmg": (
        "init", "sim",
        "IdunBattleLogic.Entities.Abilities.Triggered.Loki.ModifiedExoarmourAbility$$CreateBehaviour",
        "AmountIsGreaterThanZero(TilesMovedThisTurn(Self))"),
    # #943 -- `1455 NetherRealmCasket_CritDamageReduction` (#909). Sa POSE est lue directement (elle
    # n'emprunte PAS `AOwnerEffectTriggeredAbility` : `classes.tsv` la donne fille directe de
    # `BaseTriggeredAbility` et elle ecrit son propre `CreateBehaviour`, qui pose DEUX effets) --
    #     AddEffect(0x5af = 1455, source = targets = Owner@0x30, options = <32 octets ZEROES>)
    #     op_BitwiseAnd AddEffect(0x5b0 = 1456, <memes arguments>)
    # AUCUN `If` : la pose est INCONDITIONNELLE, et les options zeroees la rendent PERMANENTE.
    # ⚠ Son `CreateTrigger` n'est PAS lisible (la classe ne porte que deux corps dans le binaire, et
    # aucun des 20 appelants d'`OnOwnerSpecificAbilityInit` n'est elle) -- residu #589-r1-r1-r2-r1-r1,
    # partage avec `AmuletOfTheVoidwyrm`. Ce qui est ETABLI et suffit a cet axe-ci : le vecteur n'est
    # PAS un cast, et l'`AddEffect` est NU.
    "NetherRealmCasket_CritDamageReduction": (
        "init", "sim",
        "IdunBattleLogic.Entities.Abilities.Triggered.Loki.NetherRealmCasketAbility$$CreateBehaviour",
        "AmountIsGreaterThanZero(AdjacentMechanicalUnits()) -- geometrique"),
    "Pinned": (
        "runtime", "static",
        "pose par le vecteur d'ATTAQUE (Suppression), pas par un init d'ability",
        "NOT HasTrait(Self, TerminatorArmour) -- un trait ne bascule pas"),
    "PowerTrip_FullHealth": (
        "init", "sim",
        "IdunBattleLogic.Entities.Abilities.Triggered.Loki.PowerTrip_InitAbility$$CreateBehaviour",
        "PV courants == PV max"),
    "PsychicStalk_VisualEffect": (
        "init", "one-way",
        "IdunBattleLogic.Entities.Abilities.Triggered.Loki."
        "PsychicStalk_ExtraAttackDamageAbility$$CreateBehaviour",
        "NOT IsDead(Owner) -- VRAIE pour tout porteur vivant, ne se rouvre pas"),
    "ReinforcedHiveNode_ExtraArmor": (
        "init", "sim",
        "IdunBattleLogic.Entities.Abilities.Triggered.Loki."
        "ReinforcedHiveNodeAbility$$CreateBehaviour",
        "AmountIsOdd(Sum(RoundsStarted(Owner), 1))"),
    # Le MEME `CreateBehaviour` pose les DEUX d'un bloc (`op_BitwiseAnd`) :
    # `AddStaticStatModifierEffectToOwner(0x454 = 1108, stat 0x10 FixedArmor, PercentageOf(...))`
    # ET `AddStatOverrideEffectToOwner(0x455 = 1109, stat 7 BlockChance, Direct(ConfigConst 0x2d))`
    # -- aucun `If`, donc pose INCONDITIONNELLE pour les deux. Condition FONDUE avec celle de 1108.
    "ReinforcedHiveNode_ExtraBlock": (
        "init", "sim",
        "IdunBattleLogic.Entities.Abilities.Triggered.Loki."
        "ReinforcedHiveNodeAbility$$CreateBehaviour",
        "AmountIsOdd(Sum(RoundsStarted(Owner), 1)) -- corps FONDU avec celui de 1108"),
    # #943 -- `1529 RitesOfMorkai_ExtraDamage` (#904/#906). Pose par le `ExecuteBehaviour` de
    # l'ACTIVE `1211 RitesOfMorkai`, sur le sous-ensemble de sa zone FILTRE par le meme predicat que
    # la condition -- donc un vecteur de CAST, jamais un trigger d'init : l'absence a la capture est
    # FIDELE. `flip: sim` : le second disjonct est un `HasEffect` sur 1454, qui se pose et se retire
    # en cours de partie (le premier, `HasTrait`, lui, ne bascule pas).
    "RitesOfMorkai_ExtraDamage": (
        "runtime", "sim",
        "IdunBattleLogic.Entities.Abilities.Active.Loki.RitesOfMorkaiAbility$$ExecuteBehaviour"
        " (AddEffect(0x5f9 = 1529, targets = <zone FILTREE par HasAnyKindOfFinalVengeance>))",
        "HasTrait(Owner@0x30, 0x3f6 = 1014 UnitTrait.FinalJustice) op_BitwiseOr "
        "HasEffect(Owner@0x30, 0x5ae = 1454 EffectType.FinalVengeance_UnitEffect, onlyActive: 0, "
        "effectTargetType: 6 = Both)"),
    # #962 -- `1263 Skullsmasher_ExtraDamage` (#953/#954), entre au registre sans verdict de pose.
    # `Skullsmasher_DamageEffectAbility` derive d'`AOwnerEffectTriggeredAbility` (`classes.tsv`) et
    # n'a QU'UN corps propre -- `GetEffectType` (`return 0x4ef`). Son `CreateBehaviour` est donc celui
    # de la BASE, LU verbatim : `If(<CreateCondition>, AddEffect(<GetEffectType>,
    # AbilityState(Owner, this), source = Owner, targets = Owner, turns = <zeroe>))` sur
    # `OnOwnerSpecificAbilityInit`. La `CreateCondition` de base a pour corps ENTIER
    # `return <DSLTriggers+0x70>` (aucun test) -> pose INCONDITIONNELLE a l'init, MEME vecteur exact
    # qu'`AmuletOfTheVoidwyrm_CritDamageReduction` / `SupaCyborkBody_CritDmgReduction` ci-dessus.
    # `flip: sim` -- `CreateActiveCondition = AmountIsGreaterThanZero(GetMissingHealthSteps())`
    # (decompile), donc elle bascule des que le porteur perd ou regagne des PV.
    "Skullsmasher_ExtraDamage": (
        "init", "sim",
        "IdunBattle.Entities.Abilities.AOwnerEffectTriggeredAbility$$CreateBehaviour"
        " (Skullsmasher_DamageEffectAbility)",
        "AmountIsGreaterThanZero(GetMissingHealthSteps()) -- "
        "Divide(Percent(Health.Missing, Health.Maximum), ConfigConst(hpPct), Floor), donc elle "
        "bascule au premier degat subi comme au premier soin"),
    "StructuralAnalyser_Visual": (
        "init", "sim",
        "IdunBattleLogic.Entities.Abilities.Triggered.Loki."
        "StructuralAnalyser_AddDamageBuffAbility$$CreateBehaviour",
        "AmountIsGreaterThanZero(AdjacentFriends + SurroundingFriends(2) Tau)"),
    "VisionsOfHeresy_ExtraPierceMelee": (
        "init", "sim",
        "IdunBattleLogic.Entities.Abilities.Triggered.Loki."
        "VisionsOfHeresy_ExtraPierceAbility$$CreateBehaviour",
        "HealthPctIsBelowOrEqual(Owner, healthPct)"),
    "VisionsOfHeresy_ExtraPierceRanged": (
        "init", "sim",
        "IdunBattleLogic.Entities.Abilities.Triggered.Loki."
        "VisionsOfHeresy_ExtraPierceAbility$$CreateBehaviour",
        "HealthPctIsBelowOrEqual(Owner, healthPct)"),
}


def scan() -> dict:
    """RE-DERIVE tout ce qui est mecanique depuis le code (jamais un compte recopie)."""
    from engine.entities.effects.base import BaseEffect
    from engine.entities.effects.factory import (EFFECT_CLASSES, ABILITY_INIT_OWNER_EFFECTS,
                                                 ABILITY_OWNER_EFFECTS)
    seeded = {n for names in ABILITY_INIT_OWNER_EFFECTS.values() for n in names}
    seeded |= {n for names in ABILITY_OWNER_EFFECTS.values() for n in names}
    rows = []
    for name in sorted(EFFECT_CLASSES):
        klass = EFFECT_CLASSES[name]
        if klass.is_active is BaseEffect.is_active:
            continue
        pose, flip, symbol, cond = POSE_VECTOR.get(name, ("?", "?", "", ""))
        if pose == "?":
            verdict = "INCONNU"
        elif name in seeded:
            verdict = "COUVERT-SEED"
        elif pose != "init" or flip != "sim":
            verdict = "NON-EXPOSE"
        else:
            verdict = "EXPOSE"
        rows.append({"effect": name, "class": klass.__name__, "pose": pose, "flip": flip,
                     "seeded": name in seeded,
                     "acp": bool(getattr(klass, "active_condition_ported", False)),
                     "witness": getattr(klass, "seed_witness_effect", None),
                     "verdict": verdict, "symbol": symbol, "condition": cond})
    return {"n_effect_classes": len(EFFECT_CLASSES), "rows": rows,
            "unknown": [r["effect"] for r in rows if r["verdict"] == "INCONNU"]}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(
        description="case-366-r1-camo-seed : inventaire des effets condition-gated exposes au "
                    "trou de capture")
    ap.add_argument("--csv", action="store_true", help="une ligne CSV par classe")
    a = ap.parse_args(argv)

    r = scan()
    rows = r["rows"]
    if a.csv:
        print("effect,class,pose,flip,seeded,active_condition_ported,verdict")
        for x in rows:
            print("%s,%s,%s,%s,%s,%s,%s" % (x["effect"], x["class"], x["pose"], x["flip"],
                                            x["seeded"], x["acp"], x["verdict"]))
    else:
        print("EFFECT_CLASSES = %d ; surchargent `is_active` = %d"
              % (r["n_effect_classes"], len(rows)))
        print("")
        print("%-38s %-8s %-8s %-6s %s" % ("effet", "pose", "flip", "seed", "verdict"))
        for x in rows:
            print("%-38s %-8s %-8s %-6s %s"
                  % (x["effect"], x["pose"], x["flip"], "oui" if x["seeded"] else "-",
                     x["verdict"]))
        print("")
        for v in ("COUVERT-SEED", "NON-EXPOSE", "EXPOSE", "INCONNU"):
            n = sum(1 for x in rows if x["verdict"] == v)
            print("  %-14s %d" % (v, n))
        print("")
        print("EXPOSE = le natif porte l'instance (pose d'init INCONDITIONNELLE) ET la condition")
        print("  peut basculer en cours de sim, MAIS le port ne materialise l'instance que si le")
        print("  SITE DE CAPTURE demande `includeInactive` (`snapshot.decision_view_seed_body`).")

    if r["unknown"]:
        print("")
        print("[CLIQUET ROUGE] %d classe(s) surchargent `is_active` sans verdict de POSE dans "
              "POSE_VECTOR :" % len(r["unknown"]))
        for n in r["unknown"]:
            print("    %s" % n)
        print("  -> LIRE son `<X>Ability$$CreateBehaviour` au decompile (pose inconditionnelle ou")
        print("     vecteur runtime ?) et l'inscrire. Ne jamais deduire du comportement observe.")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
