"""`MartialSuperiority_Visual` (0x4e7 = 1255) — le MARQUEUR « riposte armee » du passif
`MartialSuperiority` (TriggeredAbilityType 0x444 = 1092) de `templChampion` (<< Brother Jaeger >>,
Black Templars). case-366-r1.

Le nom dit « Visual » ; ce n'est PAS ce qui tranche. Ce qui tranche est le corps natif, et il porte
une `CreateActiveCondition` REELLE (pas un stub) -- l'effet est donc un PREDICAT observable, pas un
no-op. Ce qui le rend sans effet de bord, c'est autre chose : AUCUN consommateur logique ne lit
l'`EffectType` 1255 (mesure exhaustive, cf. « CONSOMMATEURS » plus bas).

================================================================================================
RE (decompile ghidra, build `rnca9r7q6c`) -- decompile = verite
================================================================================================

## Le POSEUR

`classes.tsv` :

    IdunBattleLogic.Entities.Abilities.Triggered.Loki.MartialSuperiorityAddEffectAbility
        : IdunBattle.Entities.Abilities.AOwnerEffectTriggeredAbility : BaseTriggeredAbility
    IdunBattle.Entities.Effects.Loki.MartialSuperiority_VisualEffect
        : IdunBattle.Entities.Effects.BaseEffect                                (taille 0x480)

La classe d'ABILITY n'a AUCUNE ligne dans les deux tables de symboles -- ce qui ne prouve RIEN
(dedup par adresse). Son seul override est `GetEffectType`, dont le corps `b8 e7 04 00 00 c3`
(`mov eax, 0x4e7 ; ret`) est **UNIQUE dans tout le PE** (balayage du binaire) et porte DEUX entrees
dans la table `methodPointers` : l'une dans la region des EFFETS (c'est
`IdunBattle.Entities.Effects.Loki.GazeOfMagnusEffect$$GetTriggeredAbilityType`, a qui les deux
tables l'attribuent -- `TriggeredAbilityType 1255 = GazeOfMagnus_Attack`, homonymie d'id), l'autre
dans la region des ABILITIES, **immediatement avant les trois methodes de
`MartialSuperiorityAbility`** (`CreateTrigger`/`CreateBehaviour`/`GetInitialTarget`, entrees
contigues) : les deux classes soeurs sont declarees cote a cote, donc contigues en ordre de
metadonnees.

Le comportement du poseur vient ENTIEREMENT de la base (aucun override) :

    IdunBattle.Entities.Abilities.AOwnerEffectTriggeredAbility$$CreateTrigger
        = OnOwnerSpecificAbilityInit(this.Id@+0x10)
    IdunBattle.Entities.Abilities.AOwnerEffectTriggeredAbility$$CreateCondition
        = <DSLTriggers+0x70>                         # trigger sans champ, size 16 => YesTrigger
    IdunBattle.Entities.Abilities.AOwnerEffectTriggeredAbility$$CreateBehaviour
        = If( CreateCondition(abilityState),
              AddEffect( GetEffectType() = 0x4e7,
                         AbilityState(Owner@<Sel+0x30>, <AbilityType>),
                         targets = Owner@<Sel+0x30>,
                         source  = Owner@<Sel+0x30>,
                         <duree ZEROEE> ) )

=> owner-effect PERMANENT, pose a l'init de l'ability sur le PORTEUR.

## Le `.ctor` de l'effet -- lu a l'ASSEMBLEUR (le decompilateur masque l'immediat)

`IdunBattle.Entities.Effects.Loki.MartialSuperiority_VisualEffect$$.ctor` :

    ba 44 04 00 00      mov  edx, 0x444                  ; 1092
    e8 ..               call IdunBattle.Core.AbilityOrEffect$$op_Implicit
    41 b0 01            mov  r8b, 1                       ; hasAutomaticActivation = TRUE
    e8 ..               call IdunBattle.Entities.Effects.BaseEffect$$.ctor

⚠ QUALIFICATION D'ENUM -- le `0x444` n'est PAS un `EffectType`. La surcharge d'`op_Implicit` visee
par le `call` est celle dont `methods.tsv` donne la signature
`op_Implicit(triggeredAbility: IdunBattle.Entities.Enum.TriggeredAbilityType)` : c'est la LECTURE
qui qualifie, jamais le nom de la fonction. `1092` y vaut `MartialSuperiority` -- l'ability SOURCE
de l'effet, celle dont la config sera lue. Aux memes ids : `EffectType 1092 = HolyDuel_ExtraDmg`,
`ActiveAbilityType 1092 = DarkTalonStrike`. Trois enums, un nombre.

`BaseEffect$$.ctor(abilityOrEffect, hasAutomaticActivation: System.Boolean)` (signature `methods.tsv`)
recoit **TRUE** : contrairement a `WireweaveNet_CounterAttackEffect` (`PlayerTurnEffect`, qui passe
`activationFrequency == 0` donc FALSE et exige une machine a etats), cet effet s'arme TOUT SEUL a la
pose -- il n'a AUCUN trigger d'activation/desactivation, sa seule horloge est sa condition.

## La `CreateActiveCondition` -- le SEUL comportement de la classe

`IdunBattle.Entities.Effects.Loki.MartialSuperiority_VisualEffect$$CreateActiveCondition` :

    return op_LogicalNot( <DSLTriggers+0x28> )        # = NOT IsTurnOf(Owner)

`<DSLTriggers+0x28>` = `IsTurnOf(Owner)` -- identification etablie par case-366-r1 (§2) et par le
corps PARTAGE de ce meme `CreateActiveCondition` avec `AReactivateOverwatchEffect` (case-133 §1 :
un corps FONDU que les deux tables mislabellent differemment).

=> l'effet est ACTIF exactement pendant le tour ADVERSE, c'est-a-dire exactement la fenetre du gate
`NOT IsTurnOf(Owner)` de `MartialSuperiorityAbility$$CreateTrigger` (la riposte, portee par #133).
C'est le halo « riposte armee ».

La classe n'a qu'UN troisieme slot dans son bloc `methodPointers`, et son corps est le
`return <DSLSelectors+0x30>` partage par ~250 classes d'effet (l'unique proprietaire nomme est
`IdunBattle.Entities.Effects.Loki.WhisperingWebEffect$$CreateTargetSelector`) : `CreateTargetSelector
= Owner`. Structurel (un owner-effect se cible lui-meme), aucune semantique propre. AUCUN
`CreateEffect*`, AUCUN stat-mod, AUCUN `ApplyInternal`.

================================================================================================
CONSOMMATEURS -- mesure EXHAUSTIVE, pas une absence d'observable
================================================================================================

Balayage du PE pour TOUTE occurrence de l'immediat 4 octets `0x4e7` dans les sections de code
(methode validee sur un CONTROLE : le meme balayage sur `0x457 = 1111 WireweaveNet` retrouve bien
son consommateur IA `IdunBattle.AI.Utilities.WireweaveNet_FirstAttack.
<EvaluateAttackInSteps>d__1$$MoveNext`, son `.ctor` d'effet et ses 4 sites d'enregistrement).

Pour `0x4e7`, les SEULS sites sont des sites d'ENREGISTREMENT ou de table statique :

    IdunBattle.Entities.Effects.Loki.GazeOfMagnusEffect$$GetTriggeredAbilityType   (le corps partage)
    IdunBattle.Core.Services.AbilitiesDatabase$$InitializeTriggeredAbilities       (TriggeredAbilityType 1255)
    IdunBattle.Core.Services.EffectsDatabase$$InitializeEffects                    (EffectType 1255 -> fabrique)
    idun.Idun.Source.Shared.Battle.StaticBattleRules.StaticBattleRules.Effect$$.cctor
    idun.Idun.Source.Shared.Battle.StaticBattleRules.StaticBattleRules.TriggeredAbility$$.cctor  (x2)

=> AUCUN gate `HasEffect`, AUCUNE utilite IA, AUCUN canal de bonus/malus, AUCUN selecteur ne lit
1255. Confirme independamment cote DONNEES : la chaine `MartialSuperiority` apparait **une seule
fois** dans le BattleConfiguration (la config d'ability), et aucun bucket de `BC.Utilities.Default`
-- ni `UnitEffectsAdjacent`/`UnitEffectsRanged`/`UnitEffectsSurrounding` (les trois utilites
GENERIQUES keyees par NOM D'EFFET), ni `TileEffects`, ni `TriggeredAbilities` -- ne porte de cle
`MartialSuperiority*`. `RemoveEffectsBehaviour$$ExecuteByOwner` filtre par
`StaticBattleRules.Effect$$GetReplaceableEffectType` + `EffectType` explicite : rien ne balaie en
aveugle.

CONSEQUENCE POUR LE PORT : la contribution de cette classe est de FIDELITE (le flag `IsActive` de
l'instance suit desormais la meme condition que le natif), pas de comportement -- rayon de souffle
NUL sur les axes DEGAT / DECISION tant qu'aucun consommateur de 1255 n'existe. Elle est portee
parce que le predicat est LU, pas devine, et parce qu'un port qui laisse `BaseEffect.is_active`
rendre `True` INCONDITIONNELLEMENT publierait le halo « riposte armee » pendant le tour de Jaeger,
ou le natif l'eteint.

## SEED -- volontairement PAS d'entree `ABILITY_INIT_OWNER_EFFECTS`

Meme raisonnement que `WireweaveNet` (case-366-r1b §7ter), et la raison est ici encore plus forte :
l'instance n'est lue par RIEN, donc la materialiser quand le canal de capture ne l'a pas vue
n'apporte aucun observable -- alors qu'elle exposerait au piege #312 (`spawn._seed_ability_owner_
effects` lit les passives du KIT gameconfig, pas de la MESURE : un montage qui RETIRE le passif du
BC verrait le port materialiser quand meme l'effet).
"""
from __future__ import annotations

from collections.abc import Mapping

from ..base import BaseEffect


class MartialSuperiorityVisualEffect(BaseEffect):
    """`MartialSuperiority_VisualEffect` (1255) -- cf. en-tete. La classe native n'override QUE
    `CreateActiveCondition` (+ le `CreateTargetSelector = Owner` structurel) : ce port n'override
    donc QUE `is_active`."""

    def is_active(self, unit_state: "Mapping | None" = None) -> bool:
        """`MartialSuperiority_VisualEffect$$CreateActiveCondition` =
        `op_LogicalNot(<DSLTriggers+0x28>)` = `NOT IsTurnOf(Owner)` -- mirror LITTERAL.

        `is_turn_of_owner` = le MEME noeud natif que le canal `att_ctx["is_turn_of_owner"]`
        (`entities/effects/base.py::is_turn_of_owner`), pose ici sur le canal `unit_state` par les
        DEUX faces : COMBAT `runner/components.py::UnitEffectStateView` (`OwnerComponent.player ==
        State.current_player_id`) et DECISION `playbook/scene.py::Scene.unit_state` (via
        `Scene.is_turn_of`, qui LIT `decisionView.units[].ctrl`).

        Cle ABSENTE ou `None` = « non mesure » -> `True` : degradation fidele, on ne masque pas
        l'effet a tort (meme regime que les 13 autres `is_active` portees)."""
        v = (unit_state or {}).get("is_turn_of_owner")
        if v is None:
            return True
        return not bool(v)
