"""`MastersOfManoeuvre` -- ability **MYTHIQUE** de Machine of War (`TriggeredAbilityType`
0x5e4 = **1508**), porteurs `darkaStormSpeeder` (MoW `lineup`, Dark Angels) et
`darkaNpcMowStormSpeeder` (MoW `npc`). Voie TERTIAIRE (`BC.Units[].TertiaryAbility`), montage
ECRIT `rl_duel build --equip-mythic "darkaStormSpeeder:MastersOfManoeuvre:<lvl>"` (#999) --
`darkaStormSpeeder` est HORS du seed, donc l'injection catalogue est necessaire, et elle est
INTEGREE a `--equip-mythic`.

===================================================================================================
LES ARTEFACTS NATIFS (decompile ghidra, build `rnca9r7q6c`)
===================================================================================================

`IdunBattleLogic.Entities.Abilities.Triggered.Loki.MastersOfManoeuvreAbility` -- parent
`IdunBattle.Entities.Abilities.BaseTriggeredAbility` (`frida/classes.tsv`), et elle DECLARE ses
deux methodes (pas d'heritage `AOwnerEffect*` ici, contrairement a son jumeau
`ContemptuousDisregard`) :

    $$CreateBehaviour = DSLBehaviors.AddEffect(
            EffectType.MastersOfManoeuvre = 0x5e6 = 1510,
            get_AbilityStateReference(this),
            source  = Owner@<DSLSelectors+0x30>,
            targets = Actor@<DSLSelectors+0x40>,                <- l'ACTEUR, pas l'Owner
            turns   = TurnsFromRounds( GetNumberConstant(
                          AbilityConstantType.nrOfRounds = 0x45 ) ) )

    $$CreateTrigger = op_BitwiseOr( <A>, <B> ), avec

        COMMUN = DSLTriggers.AreFriends( Actor@<+0x40>, Owner@<+0x30>, 0, false )
               & DSLTriggers.HasRarity( Actor@<+0x40>, idun.meta.Rarity.Mythic = 5 )
               & op_LogicalNot( DSLTriggers.HasEffect( Actor@<+0x40>,
                                    EffectType.MastersOfManoeuvre = 0x5e6, null, 6 ) )

        <A> = DSLTriggers.On( EventTriggerType.UnitAfterMove = 4, alive: true ) & COMMUN
              & DSLTriggers.AmountIsEqualOrGreater(
                    DSLFormulas.TilesMovedThisTurn( Actor@<+0x40> ),
                    DSLFormulas.Get( GetNumberConstant(
                        AbilityConstantType.tilesTraversed = 0x88 ) ) )

        <B> = DSLTriggers.On( EventTriggerType.UnitFinishedTurn = 0x28, alive: true ) & COMMUN
              & DSLTriggers.AmountIsGreaterThanZero(
                    DSLSelectors.Filter(
                        DSLSelectors.AdjacentFriends( Actor@<+0x40>, true, 3 ),
                        DSLTriggers.HasRarity( Candidate@<+0x68>, 5 )
                      & DSLTriggers.HasFaction( Candidate@<+0x68>, 0xa, 3 ) ) )

⚠ **LES ORDINAUX SONT QUALIFIES PAR LEUR TYPE DECLARE, PAS PAR LEUR VALEUR.**
`frida/methods.tsv` donne `DSLTriggers.HasRarity(actor: ITargetsSelector, rarity: idun.meta.Rarity)`
-- l'enum est **`idun.meta.Rarity`** (`0=Common .. 5=Mythic`), et non `UnitRarity`, qui existe
aussi (`IdunMetaLogic.UserProgress.Model.UnitRarity`, memes membres) mais n'est PAS le type de ce
parametre. Meme discipline pour `0x45`/`0x88`, qui sont des `AbilityConstantType`
(`nrOfRounds`/`tilesTraversed`) et NON des `AbilityVariableType` (69/136 y nomment
`summonArmor_2`/`spawnArmor_5`). Le `3` de `HasFaction`/`AdjacentFriends`/`UnitsWithRarity` est le
mode de recherche partage, pas un id.

`IdunBattle.Entities.Effects.Loki.MastersOfManoeuvreEffect` (`EffectType` 0x5e6 = **1510**),
parent `IdunBattle.Entities.Effects.BaseEffect` (`frida/classes.tsv`). UNE face propre dans
`frida/methods.tsv` :

    $$CreateEffectDamageMalusForDefense :
        montant = DSLFormulas.ConfigVar( AbilityVariableType.dmgReductionPct = 0x46,
                                         BaseEffect.GetAbilityState(this), config@this+0x60 )
        trigger = DSLTriggers.get_OwnerIsTarget
                & DSLTriggers.IsRangedAttack()
        -> EffectBonus.ForPercentDecrease( trigger, montant )       <- appel EXPLICITE

⚠ **AUCUN gate de rarete SUR L'EFFET.** Toute la rarete vit dans le TRIGGER de l'ability, c.-a-d.
dans la decision de POSER l'effet -- jamais dans sa consommation. C'est ce qui rend la face DEGAT
portable alors que la face POSE ne l'est pas.

===================================================================================================
CE QUI EST PORTE ICI, ET CE QUI NE L'EST PAS
===================================================================================================

PORTE -- la face DEGAT de l'effet (`create_effect_damage_malus_for_defense`), gatee
`IsRangedAttack`.

PORTE AUSSI, DEPUIS #999-r1 -- la POSE (`$$CreateTrigger` + `$$CreateBehaviour`), dans
`engine/runner/operations/triggers/loki/masters_of_manoeuvre.py` (deux classes, une par disjoint
d'`On()`), inscrite a `RELIC_ABILITY_TRIGGERS["MastersOfManoeuvre"]`.

⚠ **LE PARAGRAPHE QUI VIVAIT ICI DECLARAIT CETTE FACE NON PORTABLE, ET IL ETAIT PERIME.** Il est
conserve en substance parce qu'il dit encore ce qu'il FAUT verifier, mais son verdict est INVERSE :
il affirmait que `HasRarity(Actor, Mythic)` -- conjoint du gate COMMUN aux DEUX vecteurs, lisant
`UnitExtensions$$GetBaseUnitComponent(entity) + 0x74` -- n'etait << publie par AUCUN canal du
port >>. C'etait vrai sur le build `rnca9r7q6c` ; ca ne l'est plus :
  * le capteur existe -- `combatSnapshot.units[].rarity` (#1039), y compris sur `unitsNotAlive[]` ;
  * il entre dans le port par le foyer `UnitContext.rarity` (#999-r3), via
    `entities/rarity.py::measured_rarity` (tri-etat STRICT, jamais `0` en repli) ;
  * le noeud DSL `HasRarity` est porte (`entities/triggers.py`) et lit la cle `rarity` du dict
    d'unite (`runner/abilities/behaviours/context.py::_unit_dict`), avec repli sur
    `UnitComponent.rarity` pour les cadavres (#999-r3-r2).
Il ne restait donc qu'un noeud absent, `DSLFormulas$$TilesMovedThisTurn`, ajoute a
`entities/formulas.py` par #999-r1 -- une enveloppe mince, son substrat (`ActorStatisticsComponent
+0xf0`) etant deja ecrit et lu par le port.

⚠ **REGIME DEGENERE, a connaitre avant toute validation** : `rl_duel build` pose `targetRarity = 5`,
donc dans un runner standard TOUTE unite est Mythic et les deux `HasRarity(., Mythic)` sont
uniformement VRAIS -- un port qui les oublierait serait d'accord avec le natif dans tous les bras
par defaut. Le bras qui SEPARE se monte par `--unit-stat "<vis>:Rarity=4"` (#1024 : la valeur
ATTEINT bien `BaseUnitComponent.Rarity`, contre-epreuve live qui ETEINT le gate).

CE QUE LA POSE PORTEE CHANGE : sur un runner live le natif posait deja l'effet et
`decisionView.effects` le publiait -> le port le CONSOMMAIT (regime de
`VexillaMagnifica_DmgReduction`). Sur un chemin purement OFFLINE (rollout self-play, etat monte
sans capture), l'effet n'apparaissait JAMAIS -- c'est ce MANQUE que le port de la pose ferme.

⚠ FACE DECISION -- `IdunBattle.AI.Playbook.Loki.MastersOfManoeuvreNonOwnerPlaybook`
(`$$CalculateMovementUtilityInSteps`) existe et n'est PAS portee : elle est l'un des 11 items du
residu `#433-r4-r3-r1-r1`, et son gate est le MEME `HasRarity` (cf. `case-477r33` : << MoW +
canal `rarity` absent du `ctx` >>). Le blocage est donc COMMUN aux deux faces, et il n'y a rien
a arbitrer entre elles.

===================================================================================================
MAGNITUDE -- le niveau est celui de la TERTIAIRE, jamais celui des passifs
===================================================================================================

`ConfigVar(0x46)` est resolu contre `GetAbilityState(this)` = l'`AbilityStateReference` **BAKEE**
dans `EffectComponent+0x18` a la pose (#382) -- celle de la MoW POSEUSE, pas du porteur de
l'effet (ici les deux DIFFERENT par construction : `targets = Actor`, `source = Owner`). Pour une
ability TERTIAIRE, ce couple est `level 1..4 / mult 100`, la ou les passifs portent `50 / 180` en
runner normalise (#1005/#1009).

Gameconfig `MastersOfManoeuvre` : `dmgReductionPct = [10, 13, 16, 20]` (4 paliers),
`variablesAffectedByRarityBonus = ['dmgReductionPct']`, `constants = {nrOfRounds: 1,
tilesTraversed: 2}`.

⚠ AUCUN repli sur `self.level` (niveau de STACK capte) : ce n'est pas un `AbilityState`.
"""
from __future__ import annotations

from collections.abc import Mapping

from ....services.effect_bonus import EffectBonus, for_percent_decrease
from ..base import BaseEffect
from ..magnitude import ability_var

#: Cle gameconfig de l'ability -- la config qu'indexe `ConfigVar`.
ABILITY_ID = "MastersOfManoeuvre"

#: `AbilityVariableType` 0x46 = 70 (`frida/enums.tsv`), resolu par son NOM.
VAR_DMG_REDUCTION_PCT = "dmgReductionPct"


class MastersOfManoeuvreEffect(BaseEffect):
    """`IdunBattle.Entities.Effects.Loki.MastersOfManoeuvreEffect$$CreateEffectDamageMalusForDefense`
    (`EffectType` 0x5e6 = 1510, nom capte `MastersOfManoeuvre`).

    MIRROR 1:1 : `EffectBonus.ForPercentDecrease( get_OwnerIsTarget & IsRangedAttack(),
    ConfigVar(0x46) )`. Cf. l'en-tete du module pour l'arbre natif complet.

    OBSERVABLE : le porteur de l'effet encaisse `-dmgReductionPct %` sur les seules attaques
    **A DISTANCE** ; en melee la reduction est MUETTE. C'est le contraste ENTIER avec son jumeau
    `ContemptuousDisregard_DamageReduction` (meme fabrique, meme variable, meme famille), qui n'a
    aucun gate de nature de coup."""

    def create_effect_damage_malus_for_defense(self, is_melee: bool | None = None,
                                               damage_profile: str | None = None,
                                               attacker_ctx: Mapping | None = None) -> EffectBonus | None:
        # `IsRangedAttack()` : le coup doit etre PROUVE a distance. `None` = nature inconnue ->
        # le gate se TAIT (<< present != applique >>), meme degradation que `MarkerlightEffect`.
        if is_melee is not False:
            return None
        # `get_OwnerIsTarget` est satisfait structurellement sur ce canal (la boucle defenseur
        # n'itere que les effets de la CIBLE du coup).
        lvl = self.ability_level
        if lvl is None:
            return None                       # `ConfigVar` sans `AbilityState` -> inerte
        red = ability_var(ABILITY_ID, VAR_DMG_REDUCTION_PCT, lvl,
                          multiplier_pct=self.ability_variables_multiplier)
        if not red:
            return None
        return for_percent_decrease(False, abs(int(red)))   # owner=defenseur (l'effet est sur la cible)
