"""Les TROIS effets du passif `RealityUnbound` (`thousTzaangor` « Yazaghor ») — 1205 / 1206 / 1207.

ARTEFACT NATIF : aucune classe d'effet dediee cote jeu — les trois entites-effet sont des
`IdunBattle.Entities.Effects.StaticStatModifierEffect` GENERIQUES, instanciees par la feuille
`IdunBattleLogic.Entities.DSLBehaviors$$AddStaticStatModifierEffect` des deux `CreateBehaviour` du
passif (cf. `runner/operations/triggers/loki/reality_unbound.py`, qui porte les arbres) :

    RealityUnboundAbility$$CreateBehaviour
        AddStaticStatModifierEffect(Self, 0x4b5 = 1205, stat = 1    = MOVEMENT,
                                    GetNumberConstant(0xe = extraMovement), turns = Nullable(1))
      + AddStaticStatModifierEffect(Self, 0x4b6 = 1206, stat = 0x18 = EXTRA_RANGE,
                                    GetNumberConstant(0xd = extraRange),    turns = Nullable(1))
    RealityUnboundExtraMaxDamageAbility$$CreateBehaviour
        AddStaticStatModifierEffect(Self, 0x4b7 = 1207, stat = 0x19 = EXTRA_MAX_DAMAGE,
                                    GetVariableForLevel(0x49 = extraMaxDmg), turns = Nullable(1))

Le couple (stat, montant) est BAKE dans le `StatModificationComponent` de l'entite-effet
(`IdunBattle.Entities.Effects.AStatModifierEffect$$GetStatModificationStat` = champ +0x10,
`IdunBattle.Entities.Effects.StaticStatModifierEffect$$GetStatModificationAmount` = champ +0x14).

POURQUOI CES CLASSES EXISTENT COTE PORT — deux raisons distinctes :

1. **SEEDING** (#118, meme motif que `ThrillSeekersEffect`) : `decisionView.effects` n'expose NI le
   stat NI le montant d'un effet CAPTE. Un buff RealityUnbound deja actif au chargement d'un `State`
   arriverait sans stat-modification declaree -> sa contribution resterait dans le residu opaque de
   `seed_unit_stats`, non attribuee donc **non retirable** a l'expiration. Declarer ici le couple
   (stat, montant), RE-DERIVE de la MEME source que le natif (la config d'ability), rend l'expiration
   exacte.
2. **STACK** pour le seul 1207 : cf. `RealityUnboundExtraMaxDamageEffect`.
"""
from __future__ import annotations

from ..base import BaseEffect
from ..magnitude import ability_var
from ....entities.stats import StatType   # #270-r1-r1-r3

_ABILITY_ID = "RealityUnbound"


class RealityUnboundMovementEffect(BaseEffect):
    """`RealityUnbound_Movement` (1205 = 0x4b5) — +`extraMovement` MOVEMENT pour 1 tour, pose quand
    >= 3 ennemis DISTINCTS ont encaisse du degat Psychic dans le tour.

    C'est AUSSI le marqueur d'anti-re-trigger du volet A : son `CreateTrigger` est
    `WeaverOfFateAbility$$GetTrigger(0x4b5)`, dont le dernier noeud est
    `Not(HasEffect(self, 0x4b5))` — le natif reutilise l'effet Movement au lieu d'un marqueur dedie.

    MAGNITUDE : `GetNumberConstant(cfg, 0xe = extraMovement)` == gameconfig
    `RealityUnbound.constants.extraMovement` (=1). CONSTANTE -> NON scalee par
    l'`AbilityVariablesMultiplierPercentage` (source unique partagee avec
    `runner/operations/triggers/loki/reality_unbound.py::reality_unbound_extra_movement`)."""

    def get_stat_modification_stat(self) -> int | None:
        return 1                                     # StatType.MOVEMENT

    def get_stat_modification_amount(self) -> int | None:
        return ability_var(_ABILITY_ID, "extraMovement", is_constant=True)


class RealityUnboundRangeEffect(BaseEffect):
    """`RealityUnbound_Range` (1206 = 0x4b6) — +`extraRange` EXTRA_RANGE (stat 0x18) pour 1 tour, pose
    par le MEME `CreateBehaviour` que 1205 (les deux feuilles sont jointes par un `op_Addition`).

    Le stat 0x18 est consomme par `IdunBattle.Core.Services.TargetingQuery$$GetRange`
    (`range = GetStat(u, 0x18) + FindLongestRangedWeapon(u).range`, branche ranged UNIQUEMENT) —
    mirror cote port dans `runner/operations/triggers/base.py::_max_attack_range`.

    MAGNITUDE : `GetNumberConstant(cfg, 0xd = extraRange)` == `RealityUnbound.constants.extraRange`
    (=1), constante -> non scalee."""

    def get_stat_modification_stat(self) -> int | None:
        return StatType.EXTRA_RANGE                                    # StatType.EXTRA_RANGE (0x18)

    def get_stat_modification_amount(self) -> int | None:
        return ability_var(_ABILITY_ID, "extraRange", is_constant=True)


class RealityUnboundExtraMaxDamageEffect(BaseEffect):
    """`RealityUnbound_ExtraMaxDamage` (1207 = 0x4b7) — +`extraMaxDmg` EXTRA_MAX_DAMAGE (stat 0x19)
    pour 1 tour, pose une fois par ennemi DISTINCT ayant encaisse du Psychic ce tour.

    **EMPILABLE** (`stacks_stat_mod_on_add = True`, patron `ActOfFaithBuffEffect`) : l'i2 dit « FOR
    EACH different enemy unit ... +181 Maximum Damage », et le natif appelle
    `AddStaticStatModifierEffect` une fois par ennemi distinct **sans `RemoveEffect` prealable** —
    contraste EXPLICITE avec `MasterAnnihilator` et `FleshmetalGuns`, dont les `CreateBehaviour`
    font Remove-puis-Add precisement pour NE PAS empiler. Sans ce flag, le gate « deja-present »
    d'`AddEffectOperation` no-operait toutes les poses apres la premiere et le bonus plafonnait a
    un seul cran. On reproduit l'observable additif par N instances (chacune son `stat_mod_source`,
    donc revert exact a l'expiration), pas par le compteur `UpdateExistingEffect` natif (source-
    matching non porte, meme divergence de REPRESENTATION que celle deja flaggee pour ActOfFaith).

    MAGNITUDE : `GetVariableForLevel(cfg, 0x49 = extraMaxDmg, abilityState)` — VARIABLE per-niveau,
    et `extraMaxDmg` figure dans `variablesAffectedByRarityBonus` -> scalee par le multiplicateur de
    rarete. Cette classe ne connait PAS le porteur : elle rend la valeur au niveau/multiplicateur
    portes par l'instance d'effet (champs seedes par `EffectFactory.create`), comme les autres effets
    a `ConfigVar` ; la pose EN COMBAT, elle, passe la valeur deja resolue
    (`reality_unbound_extra_max_damage`) a la feuille."""

    stacks_stat_mod_on_add = True

    def get_stat_modification_stat(self) -> int | None:
        return StatType.EXTRA_MAX_DAMAGE                                    # StatType.EXTRA_MAX_DAMAGE (0x19)

    def get_stat_modification_amount(self) -> int | None:
        return ability_var(_ABILITY_ID, "extraMaxDmg", self.ability_level,
                           multiplier_pct=self.ability_variables_multiplier)
