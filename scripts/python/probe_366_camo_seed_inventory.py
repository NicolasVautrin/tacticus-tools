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
    # #1015-r1 -- `CloseCombatWeakness_AddEffectAbility` (TriggeredAbilityType 0x46a = 1130, derivee
    # du TRAIT `CloseCombatWeakness` 0x40b par le dict `GetTriggeredAbility` du `.cctor` de
    # `StaticBattleRules.Trait`) derive d'`AOwnerEffectSpecificTriggeredAbility` et n'en surcharge
    # QUE `$$GetEffectType`, dont le corps ENTIER est `return 0x46a`. Le reste vient de la BASE :
    # `$$CreateTrigger = OnOwnerSpecificAbilityInit(this.AbilityType)` -> `AddEffect(owner,
    # GetEffectType())` NU. La pose est donc d'INIT et INCONDITIONNELLE : l'instance existe TOUJOURS
    # cote natif des que le porteur a le trait, et son absence a la capture serait un TROU -- c'est
    # exactement ce que couvre `ABILITY_INIT_OWNER_EFFECTS["CloseCombatWeakness"]`.
    # `flip = "sim"` : la condition est GEOMETRIQUE (`HasAdjacentEnemies(Caster, CasterTile)`), donc
    # elle passe de FAUSSE a VRAIE des que la prediction simule une tuile AU CONTACT -- meme famille
    # qu'`AmuletOfTheVoidwyrm` et `SupaCyborkBody`, et c'est la raison meme du drapeau
    # `active_condition_ported`.
    "CloseCombatWeakness_ReduceDmg": (
        "init", "sim",
        "IdunBattle.Entities.Abilities.AOwnerEffectSpecificTriggeredAbility$$CreateTrigger"
        " (CloseCombatWeakness_AddEffectAbility, OnOwnerSpecificAbilityInit(0x46a))",
        "NOT HasEffect(Owner@+0x30, 0x478 SuppressCloseCombatWeakness) & "
        "(HasAdjacentEnemies(Caster@+0x48, CasterTile@+0x50) | "
        "HasEffect(Owner@+0x30, 0x469 CloseCombatWeakness_StartedTurnAdjacentToEnemy)) -- "
        "geometrique, donc elle bascule a la tuile SIMULEE"),
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
    # #547-r11 -- `1060 Lifewards_BondEffect`, entree au registre avec #963-r3 sans verdict de pose.
    # `IdunBattleLogic.Entities.Abilities.Triggered.LifewardsAddEffectAbility$$CreateBehaviour`
    # RELU VERBATIM (build `t6dpr4k06g`) : corps ENTIER =
    #     If( op_LogicalNot(HasEffect(Owner@<DSLSelectors+0x30>, 0x424, onlyActive: 0,
    #                                 effectTargetType: 6)),
    #         AddBondEffect(0x424, get_AbilityStateReference(this), source = Owner@+0x30,
    #                       targets = Owner@+0x30, bondedEntity = Parent(Owner@+0x30, root: 0),
    #                       options = <ZEROEES>) )
    # Le seul gate est `NOT HasEffect(<lui-meme>)`, c.-a-d. un gate d'IDEMPOTENCE, pas une condition
    # metier : a la premiere evaluation l'instance n'existe pas, donc la pose est INCONDITIONNELLE.
    # Son trigger est le corps ICF-deduplique `...Active.Loki.SummaryExecutionAddBaseEffectAbility$$
    # CreateTrigger`, RELU AUSSI : `return <DSLTriggers+0x30>` = `On(0x21 = AbilityInit) &
    # <+0x70 = YesTrigger> & get_OwnerIsActor` -> pose d'INIT. MEME vecteur qu'`AllIsDust`,
    # `SynapticInsight` et `LegendaryCommander`, qui partagent ce corps de trigger.
    # `flip: sim` -- `IdunBattle.Entities.Effects.Loki.LifewardsBondEffect$$CreateActiveCondition`,
    # RELUE VERBATIM, a pour corps ENTIER `IsAdjacent(Owner@<DSLSelectors+0x30>, Parent(Owner),
    # UnitSelectionType.OnlyAliveAndTargetable = 3)` : GEOMETRIQUE, donc elle rebascule des qu'une
    # unite bouge -- meme famille qu'`AmuletOfTheVoidwyrm` et `SupaCyborkBody`.
    # -> verdict `COUVERT-SEED` : le rail existe, mais par le canal BOND
    # (`ABILITY_INIT_OWNER_BOND_EFFECTS["Lifewards"]`, #963-r5), que l'inventaire ne visitait pas
    # avant cette tranche -- cf. `canaux_de_seed`.
    "Lifewards_BondEffect": (
        "init", "sim",
        "IdunBattleLogic.Entities.Abilities.Triggered.LifewardsAddEffectAbility$$CreateBehaviour"
        " (trigger `<DSLTriggers+0x30>` = On(0x21 AbilityInit), corps ICF de"
        " SummaryExecutionAddBaseEffectAbility$$CreateTrigger)",
        "IsAdjacent(Owner@<DSLSelectors+0x30>, Parent(Owner@+0x30), "
        "UnitSelectionType.OnlyAliveAndTargetable = 3) -- geometrique, donc elle bascule des "
        "qu'une des deux unites bouge"),
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
    # #1049 -- `1322 RedThirst_ExtraDamageAndHit` (passif du summon `bloodSmnIntercessor`).
    # `IdunBattleLogic.Entities.Abilities.Triggered.Loki.RedThirstAbility` derive
    # d'`AOwnerEffectTriggeredAbility` (`frida/classes.tsv`) et n'en surcharge QUE `$$GetEffectType`,
    # dont le corps ENTIER est `return 0x52a` : MEME vecteur de pose EXACT que
    # `HammerOfWrath_ConditionalDamage` juste au-dessus, et MEME condition (`HealthPctIsBelowOrEqual`
    # sur `ConfigConst(0x4f = healthPct)`, ici 50 %). Le seed offline est
    # `ABILITY_INIT_OWNER_EFFECTS["RedThirst"]`.
    "RedThirst_ExtraDamageAndHit": (
        "init", "sim",
        "IdunBattle.Entities.Abilities.AOwnerEffectTriggeredAbility$$CreateBehaviour"
        " (RedThirstAbility)",
        "HealthPct <= healthPct"),
    # #1015-r1 -- `1235 InstinctiveBehaviour_BlockMovement`, l'owner-effet du trait
    # `InstinctiveBehaviour` (UnitTrait 0x7e5 = 2021, 23 porteurs : 18 npc + 5 summons Tyranides).
    # Les TROIS etages sont LUS au decompile `rnca9r7q6c` :
    #   1. VECTEUR -- `IdunBattleLogic.Entities.Abilities.Active.Loki.InstinctiveBehaviour_
    #      InitAbility$$.ctor` = `AOwnerEffectSpecificTriggeredAbility$$.ctor(this, 0x413)`, donc
    #      `CreateTrigger = OnOwnerSpecificAbilityInit(0x413 = TriggeredAbilityType.
    #      InstinctiveBehaviour)` : le trigger d'INIT de l'ability que le trait DERIVE
    #      (`AddTraitOperation$$AddDerivedAbilities`, dict `Trait +0x0`). L'ability elle-meme
    #      n'override QUE `$$GetEffectType`, dont le corps ENTIER est `return 0x4d3` (= 1235) --
    #      l'appariement ability -> effet est LU, pas devine.
    #   2. POSE INCONDITIONNELLE -- le corps herite est
    #      `IdunBattle.Entities.Abilities.AOwnerEffectTriggeredAbility$$CreateBehaviour` =
    #      `If(<CreateCondition>, AddEffect(GetEffectType(), AbilityState(Owner, this),
    #      targets = Owner@<DSLSelectors+0x30>, source = Owner, <options a ZERO>), null)`, et la
    #      `CreateCondition` de base rend `<DSLTriggers+0x70>` -- le MEME slot constant-vrai que
    #      pour `AmuletOfTheVoidwyrm` / `HammerOfWrath` ci-dessus. Donc `pose = "init"` : l'instance
    #      existe TOUJOURS cote natif, et son absence offline serait un TROU.
    #   3. FLIP `"sim"` -- la condition bascule de FAUSSE a VRAIE des que la cible forcee entre a
    #      portee, ce qui est exactement ce qu'une simulation de tuile candidate change. MESURE
    #      (probe_1015r1) : natif 12 tuiles a d=3, **0** a d=1, temoin sans le trait jamais bloque.
    # VERDICT ATTENDU `COUVERT-SEED` : `ABILITY_INIT_OWNER_EFFECTS["InstinctiveBehaviour"]` le
    # materialise (chaine `TRAIT_DERIVED_ABILITIES` -> `_seed_derived_ability_owner_effects`), sur
    # les DEUX voies -- SPAWN (`operations/spawn.py`) et CAPTURE (`snapshot.load_state`, ou la
    # boucle TRAITS de `InitializeActorAbilitiesOperation$$Execute` manquait avant #1015-r1).
    "InstinctiveBehaviour_BlockMovement": (
        "init", "sim",
        "IdunBattle.Entities.Abilities.AOwnerEffectTriggeredAbility$$CreateBehaviour"
        " (InstinctiveBehaviour_InitAbility, GetEffectType -> 0x4d3)",
        "IsTurnOf(Owner)@<DSLTriggers+0x28> & Any(Tiles(Owner), IsWalkable(It)) & "
        "AmountIsGreaterThanZero(ForcedAttackTargets(Owner)) & "
        "Any(ForcedAttackTargets(Owner), IsInAttackOrAbilityRange(Owner, It))"),
    # #1045 -- `1568 HeadwoppasKillchoppa_ExtraDmg` (#1012-r1), entree au registre sans verdict de
    # pose : c'etait l'unique `INCONNU` du cliquet. Les TROIS etages sont LUS au decompile
    # `rnca9r7q6c`, aucun deduit du nom ni du comportement :
    #   1. VECTEUR -- `HeadwoppasKillchoppaAbility` est fille DIRECTE de `BaseTriggeredAbility`
    #      (`frida/classes.tsv`) et ne porte QU'UN corps propre dans `frida/methods.tsv`
    #      (`CreateBehaviour`). Son `CreateTrigger` est un corps DEDUPLIQUE -- donc absent de la
    #      table, ce qui ne prouve rien -- et son appartenance est etablie SLOT A SLOT dans le bloc
    #      `methodPointers`, ou les triplets `[.ctor, CreateTrigger, CreateBehaviour]` se suivent
    #      dans l'ordre alphabetique des types : `Haywire`MineSteppable (les DEUX slots nommes par
    #      Ghidra), puis `Headwoppas`Killchoppa (`.ctor` dedup, `CreateTrigger` = le corps dont le
    #      proprietaire NOMME est `WayOfTheShortBlade_InitAbility$$CreateTrigger`, `CreateBehaviour`
    #      = le sien), puis `Healing`Balms, puis `Heavy`GravCannon -- les quatre voisins sont nommes,
    #      donc l'encadrement est ferme des deux cotes. Ce corps partage est
    #      `OnOwnerSpecificAbilityInit( <this+0x10> )`, ou `this+0x10` est le champ que
    #      `BaseTriggeredAbility$$Init` ecrit depuis `abilityConfigId` (l'AbilityType) -- Ghidra le
    #      mislabelle `CenterSpace.Free.MersenneTwister$$get_Count`, dont le corps ENTIER est
    #      `return *(undefined4 *)(param_1 + 0x10)`.
    #   2. POSE NUE -- `$$CreateBehaviour` = `AddEffect(0x620 = 1568, get_AbilityStateReference(this),
    #      source = targets = Owner@DSLSelectors+0x30, options)`. AUCUN `If` n'enveloppe l'appel (le
    #      seul `DSLBehaviors$$*` du corps est cet `AddEffect`) -> pose INCONDITIONNELLE a l'init.
    #   3. NIVEAU 0 -- les `options` sont `{+0x00 = null, +0x08 = null, +0x10 = <DSLFormulas+0x18>}`,
    #      et `DSLFormulas$$.ctor` construit `+0x18` avec le scalaire `0` (les slots voisins valent
    #      1, 2, 100, -1) : c'est `Direct(0)`. `AddEffectOperation$$Execute` ecrit ce 3e champ dans
    #      `EffectComponent+0x68` (defaut 1 quand il est nul), `+0x00` etant la DUREE (repli sur
    #      `StaticBattleRules.Effect$$DefaultAmountOfRounds`) -- et `+0x68` est bien le NIVEAU,
    #      puisque c'est le champ qu'`IncreaseEffectLevelOperation$$Execute` incremente sous garde
    #      `StaticBattleRules.Effect$$HasLevel`.
    # `flip: sim` n'est donc PAS un defaut de prudence, il se DERIVE de 3 : la condition
    # `AmountIsGreaterThanZero(EffectLevel)` est FAUSSE a la pose et devient VRAIE au premier kill du
    # porteur (`EFFECT_TRIGGERS[1568]`, `On(0x36 = 54 UnitDefeated)`). Si le niveau pose avait ete 1,
    # elle serait vraie d'emblee et ne rebasculerait jamais (aucun `DecreaseEffectLevel` sur 1568).
    # Verdict `COUVERT-SEED` : `ABILITY_INIT_OWNER_EFFECTS["HeadwoppasKillchoppa"]` la materialise
    # deja, ce qui est LOAD-BEARING -- la relique arrive par la voie TERTIAIRE et `decisionView` ne
    # publie l'instance qu'avec `includeInactive`, puisqu'elle naît inactive.
    "HeadwoppasKillchoppa_ExtraDmg": (
        "init", "sim",
        "IdunBattleLogic.Entities.Abilities.Triggered.Loki.HeadwoppasKillchoppaAbility$$"
        "CreateBehaviour (AddEffect(0x620, ..., options{+0x10 = <DSLFormulas+0x18> = Direct(0)}) NU ;"
        " CreateTrigger = corps DEDUPLIQUE OnOwnerSpecificAbilityInit(this.AbilityType))",
        "AmountIsGreaterThanZero(EffectLevel(Effect@DSLSelectors+0x38)) -- le compteur de kills, "
        "pose a 0 donc FAUSSE a l'init, montee par IncreaseEffectLevel sur UnitDefeated"),
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


def canaux_de_seed() -> dict:
    """{table de `factory`: set(noms d'effet)} -- **DERIVE DU CONSOMMATEUR**, jamais enumere.

    ⚠ POURQUOI CETTE FONCTION EXISTE (#547-r11). `scan()` calculait `seeded` sur DEUX tables
    ECRITES A LA MAIN (`ABILITY_INIT_OWNER_EFFECTS`, `ABILITY_OWNER_EFFECTS`). Le seed en consomme
    QUATRE : `#963-r5` a ajoute `ABILITY_INIT_OWNER_BOND_EFFECTS` (le canal qui ecrit `bonded`, sans
    lequel la pose d'init de `Lifewards` restait refusee) et `TRAIT_OWNER_EFFECTS` n'y avait jamais
    ete. Consequence MESUREE : `Lifewards_BondEffect`, seede par le canal BOND, sortait en `EXPOSE`
    -- c.-a-d. << le natif porte l'instance et le port ne la materialise pas >> -- alors que le port
    la materialise. Un inventaire ecrit a la main ne peut pas montrer la table qu'il a oubliee ;
    c'est le vice recense par le CLAUDE.md (<< un recenseur ne peut pas rendre zero sur ce qu'il ne
    visite pas >>), ici dans sa variante << une LISTE DE TABLES au lieu des REGISTRES >>.

    LA DERIVATION, en trois crans, tous mecaniques :
      1. le CONSOMMATEUR (`runner/operations/spawn.py`, le seul foyer des `_seed_*_owner_effects`)
         est parse a l'AST -- on prend tout nom qu'il importe de `entities/effects/factory.py`,
         **imports DIFFERES compris** (`get_owner_bond_effects_added_on_ability_init` etait importe
         DANS une fonction : un balayage des seuls imports de tete l'aurait rate), **ET les noms
         qu'il consomme par ACCES ATTRIBUTAIRE sur une liaison de MODULE** (forme B) ;

    ⚠ LA FORME B EST UNE VOIE DE CONSOMMATION, ET ELLE NE LAISSE AUCUNE TRACE DANS UN RECENSEMENT
    D'`ImportFrom` (#10036). Ce cran ne lisait que les `ImportFrom` visant `...factory`. Or
    `spawn.py` est passe en **forme B** -- `from ...entities.effects import factory as _factory`,
    puis `_factory.get_owner_bond_effects_added_on_ability_init(ab)` -- qui est *exactement* la
    forme que le CLAUDE.md PRESCRIT (la seule des trois qui morde sous `monkeypatch.setattr`).
    L'`ImportFrom` y lie le nom `factory`, pas les accesseurs : le recenseur a donc perdu DEUX
    canaux d'un coup -- `ABILITY_INIT_OWNER_BOND_EFFECTS` (celui dont l'absence reclassait
    `Lifewards_BondEffect` en `EXPOSE` a tort, le defaut meme que cette fonction existe pour
    fermer) et `ABILITY_INIT_OWNER_FLAGS`. Le recenseur penalisait la doctrine qu'il est cense
    servir ; le remede est qu'il SUIVE l'indirection, pas qu'on remette un nom en dur au site.

    ⚠ ET IL LA SUIT SANS DEVENIR PERMISSIF : l'attribut n'est retenu que si son porteur RESOUT,
    DANS SA PORTEE, vers `engine.entities.effects.factory` -- `MIG.ResolveurDeModules`, le foyer
    unique de cette question (#485-r2), celui-la meme qui a du reparer deux faux positifs nes
    d'une table PLATE. Un `<n_importe_quoi>.get_owner_bond_effects_added_on_ability_init` sur un
    objet qui n'est pas ce module ne compte pas. Le cran 2 borne le reste : un nom qui n'est ni un
    accesseur `return <TABLE>.get(...)` ni un `dict` de module part dans `ecartes`, et y est COMPTE.
      2. chaque nom est resolu contre `factory` -- un accesseur `def get_x(k): return <TABLE>.get(k)`
         rend `<TABLE>` (appariement par l'AST du `return`, pas par le nom), un `dict` de module se
         rend lui-meme, tout le reste est ECARTE et COMPTE ;
      3. les valeurs sont aplaties (un element `tuple` porte le nom d'effet en position 0, forme du
         canal BOND) et filtrees par appartenance a `EFFECT_CLASSES`.

    ⚠ CE QUE LE CRAN 3 FILTRE, et c'est MESURE, pas suppose : `TRAIT_DERIVED_ABILITIES` est
    consommee par `_seed_derived_ability_owner_effects` mais ses valeurs sont des noms d'ABILITY,
    pas d'effet -- elle RE-ENTRE dans `get_owner_effects_added_on_ability_init`, donc son apport
    reel est deja compte. L'intersection de ses valeurs avec `EFFECT_CLASSES` est **VIDE**, donc le
    filtre ne perd rien et n'ajoute rien ; `--csv`/la sortie l'IMPRIMENT (`ecartes`), pour qu'une
    collision de nom future soit visible au lieu d'etre silencieuse.
    """
    import ast as _ast
    import inspect as _inspect
    from pathlib import Path as _Path
    import migrate_485r1_barils_reexport as _MIG
    from engine.entities.effects import factory as _factory
    from engine.runner.operations import spawn as _spawn

    # -- cran 1 : ce que le CONSOMMATEUR consomme de `factory`, PAR LES DEUX VOIES ----------------
    # La racine du paquet se DERIVE du couple (chemin, nom pointe) : `engine.runner.operations.spawn`
    # a 4 segments, donc `parents[3]`. Ecrit ainsi, un deplacement du module ne fabrique pas une
    # racine fausse en silence -- il ne peut plus y avoir de desaccord entre les deux.
    _chemin = _Path(_inspect.getsourcefile(_spawn)).resolve()
    _racine = _chemin.parents[len(_spawn.__name__.split(".")) - 1]
    _arbre_s = _ast.parse(_chemin.read_text(encoding="utf-8"))
    _mod_s = _MIG.nom_module(_chemin, _racine)
    _resolveur = _MIG.ResolveurDeModules(_arbre_s, _mod_s, _racine)
    CIBLE = "engine.entities.effects.factory"

    importes: set[str] = set()
    for n in _ast.walk(_arbre_s):
        # voie 1 -- `from ...entities.effects.factory import <nom>` (formes A et C). Le module vise
        # est RESOLU EN ABSOLU (`cible_absolue`) et compare exactement : un `endswith` sur le module
        # relatif accepterait un homonyme d'un autre paquet.
        if isinstance(n, _ast.ImportFrom):
            if _MIG.cible_absolue(_mod_s, n, _racine) == CIBLE:
                importes |= {a.name for a in n.names}
        # voie 2 -- FORME B : `<alias lie au MODULE factory>.<nom>`. Le porteur est resolu DANS SA
        # PORTEE ; tout autre porteur, meme homonyme, est ignore.
        elif isinstance(n, _ast.Attribute) and isinstance(n.value, _ast.Name):
            if _resolveur.resoudre(n.value.id, n.value) == CIBLE:
                importes.add(n.attr)

    # -- cran 2 : accesseur -> table, par l'AST du `return <TABLE>.get(...)` ----------------------
    table_de: dict[str, str] = {}
    dicts_de_module: set[str] = set()
    arbre_f = _ast.parse(_inspect.getsource(_factory))
    for n in arbre_f.body:
        if isinstance(n, _ast.FunctionDef):
            for st in n.body:
                if not (isinstance(st, _ast.Return) and isinstance(st.value, _ast.Call)):
                    continue
                f = st.value.func
                if (isinstance(f, _ast.Attribute) and f.attr == "get"
                        and isinstance(f.value, _ast.Name)):
                    table_de[n.name] = f.value.id
        elif isinstance(n, (_ast.Assign, _ast.AnnAssign)):
            cibles = (n.targets if isinstance(n, _ast.Assign) else [n.target])
            for c in cibles:
                if isinstance(c, _ast.Name) and isinstance(n.value, _ast.Dict):
                    dicts_de_module.add(c.id)

    tables, ecartes = {}, []
    for nom in sorted(importes):
        t = table_de.get(nom) or (nom if nom in dicts_de_module else None)
        if t is None:
            ecartes.append(nom)                       # `EffectFactory`, une constante, ... : COMPTE
            continue
        tables[t] = getattr(_factory, t, None)

    # -- cran 3 : aplatir, puis filtrer par appartenance a `EFFECT_CLASSES` -----------------------
    connus = set(_factory.EFFECT_CLASSES)
    par_table, hors_registre = {}, {}
    for t, d in tables.items():
        plat = set()
        for v in (d or {}).values():
            for x in (v or ()):
                plat.add(x[0] if isinstance(x, tuple) else x)
        par_table[t] = {n for n in plat if isinstance(n, str) and n in connus}
        # `ABILITY_INIT_OWNER_FLAGS` porte des ENTIERS (des `UnitFlag`, pas des effets) : le tri par
        # `str` evite de comparer int et str, et l'affichage les rend tels quels -- ce qui EST
        # l'information (ce canal ne materialise aucune instance d'effet).
        reste = {n for n in plat if not (isinstance(n, str) and n in connus)}
        if reste:
            hors_registre[t] = sorted(reste, key=str)
    return {"tables": par_table, "ecartes": sorted(ecartes), "hors_registre": hors_registre}


def scan() -> dict:
    """RE-DERIVE tout ce qui est mecanique depuis le code (jamais un compte recopie)."""
    from engine.entities.effects.base import BaseEffect
    from engine.entities.effects.factory import EFFECT_CLASSES
    canaux = canaux_de_seed()
    seeded = set().union(*canaux["tables"].values()) if canaux["tables"] else set()
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
            "unknown": [r["effect"] for r in rows if r["verdict"] == "INCONNU"],
            "canaux": canaux}


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
        # LES CANAUX SONT DERIVES : on les IMPRIME, avec ce qu'ils ECARTENT (#547-r11). Un
        # inventaire qui ne dit pas ce qu'il filtre ne peut pas montrer ce qu'il a oublie.
        c = r["canaux"]
        print("CANAUX DE SEED derives de `runner/operations/spawn.py` (le CONSOMMATEUR) : %d"
              % len(c["tables"]))
        for t in sorted(c["tables"]):
            print("  %-36s %d effet(s)" % (t, len(c["tables"][t])))
        print("  importes de `factory` mais SANS table (ecartes) : %s"
              % (", ".join(c["ecartes"]) or "(aucun)"))
        for t, noms in sorted(c["hors_registre"].items()):
            print("  ECARTES PAR LE FILTRE `in EFFECT_CLASSES` -- %s : %s"
                  % (t, ", ".join(str(x) for x in noms)))
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
