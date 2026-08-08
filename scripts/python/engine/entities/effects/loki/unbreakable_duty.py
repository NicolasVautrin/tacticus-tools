"""Les TROIS effets de l'active `UnbreakableDuty` (1061) de `templAncient` (« Thoread ») :
`UnbreakableDuty_Health` (1251 = 0x4e3), `UnbreakableDuty_Damage` (1256 = 0x4e8) — les deux
self-buffs PERMANENTS — et `UnbreakableDuty_DamageReduction` (1097 = 0x449), l'AURA de reduction
de degat posee inconditionnellement au cast.

ARTEFACT NATIF des deux self-buffs : aucune classe d'effet dediee — deux instances GENERIQUES
`IdunBattle.Entities.Effects.StaticStatModifierEffect`, posees par la feuille
`IdunBattleLogic.Entities.DSLBehaviors$$AddStaticStatModifierEffectToOwner`
(signature `(effectType, statType, amount, turns, isHidden)`) de
`IdunBattleLogic.Entities.Abilities.Active.Loki.UnbreakableDutyAbility$$ExecuteBehaviour` :

    AddStaticStatModifierEffectToOwner(0x4e3 = 1251, stat = 5    HEALTH,
                                       ConfigVar(0x1e = extraHp,  abilityState), turns = NULL)
    + ChangeStat(Owner, Position(HEALTH, part 0), mode 2 = Add, <le MEME ConfigVar>, ...,
                 OnlyAliveAndTargetable)
    AddStaticStatModifierEffectToOwner(0x4e8 = 1256, stat = 0    ATTACK,
                                       ConfigVar(8    = extraDmg, abilityState), turns = NULL)

le tout sous `If(AmountIsEqualOrGreater(Count(UnitsWithTraits(Friends(AllDeadOrResurrectedUnits),
[0x1a, 0x10])), Direct(2)), <les buffs + l'attaque libre>, null)` — il faut >= 2 allies morts. Le
`ChangeStat` qui accompagne 1251 monte la sante COURANTE du meme montant (c'est le patron « +max HP
ET +HP courants ») ; il n'appartient pas a l'entite-effet et vit donc dans la feuille DSL
(`runner/abilities/behaviours/stats.py::ChangeStat`, branche HEALTH), pas ici.

⚠ Les DEUX litteraux corriges le 2026-08-08 (#572) : le mode du `ChangeStat` est `2 = Add`
(`IdunBattle.Entities.Behaviours.ChangeStatMode`, pas `Modify` qui vaut 4) et son
`unitSelectionType` est `3 = OnlyAliveAndTargetable` (pas `1 = OnlyAlive`). Aucun des deux n'etait
executable ici — c'etaient des CITATIONS fausses, corrigees en portant la face COMBAT.

`turns = NULL` => **PERMANENTS**. Le bug de DUREE que ferme le lot G1 (case-371) ne les concerne
donc PAS : rien ne les fait expirer. Ce que leur inscription ferme est l'**ATTRIBUTION** — sans elle,
les deux contributions tombent dans le RESIDU OPAQUE (`CAPTURED_SOURCE`) de `seed_unit_stats`, ou
elles ne sont ni verifiables (aucune confrontation « somme des magnitudes config == statDelta natif »)
ni retirables si un chemin de retrait apparait. Avec elle, `residu == 0` sur les deux stats devient
une validation NON CIRCULAIRE : le montant vient de gameconfig, le delta vient du natif.

⚠ CONTRE-EPREUVE OBLIGATOIRE (garde `test_static_statmod_g1_expiry.py`) : declares, ils ne doivent
RIEN perdre au tick de duree. `EffectComponent$$RemoveOneTurn` a pour gate `!Removed && HasTurns`,
et `remaining <= 0` est materialise `None` (PERMANENT) par `EffectFactory` — meme regime que
`ProtectorImperative`.

MAGNITUDES : `ConfigVar(0x1e)` et `ConfigVar(8)` == `UnbreakableDuty.variables.extraHp[level]` /
`.extraDmg[level]`. L'index 0x1e est tranche par ELIMINATION STRICTE sur les TROIS variables de
l'ability : `extraDmg` = 8 (index etabli par une dizaine de ports), `dmgReductionPct` = 0x46 (lu
sur `IdunBattleLogic.Entities.Abilities.Active.Loki.UnbreakableDuty_DamageReductionEffect$$CreateEffectDamageMalusForDefense`,
meme index que `SereneUnifierSenseOfStoneEffect`), donc 0x1e = `extraHp` — la seule restante, et la
seule dont la semantique va sur le stat HEALTH. Les DEUX sont dans `variablesAffectedByRarityBonus`
-> scalees par l'`AbilityVariablesMultiplierPercentage`.

`UnbreakableDuty` est une ability ACTIVE -> le niveau est `active_ability_level` (patron
`StandVigilExtraArmorEffect`), avec repli passif puis stack level.
"""
from __future__ import annotations

from collections.abc import Mapping

from ..base import BaseEffect
from ..magnitude import ability_var
from ....entities.stats import StatType   # #270-r1-r1-r3
from ....services.effect_bonus import EffectBonus, for_percent_decrease

_ABILITY_ID = "UnbreakableDuty"


def _active_level(eff: BaseEffect) -> int | None:
    """Niveau indexant les `variables[level]` d'une ability ACTIVE (mirror `StandVigil`)."""
    if eff.active_ability_level is not None:
        return eff.active_ability_level
    return eff.ability_level if eff.ability_level is not None else eff.level


class UnbreakableDutyHealthEffect(BaseEffect):
    """`UnbreakableDuty_Health` (0x4e3 = 1251) — +`extraHp` sur HEALTH, PERMANENT (turns = NULL)."""

    def get_stat_modification_stat(self) -> int | None:
        return StatType.HEALTH                                     # StatType.HEALTH

    def get_stat_modification_amount(self) -> int | None:
        return ability_var(_ABILITY_ID, "extraHp", _active_level(self),
                           multiplier_pct=self.ability_variables_multiplier)


class UnbreakableDutyDamageEffect(BaseEffect):
    """`UnbreakableDuty_Damage` (0x4e8 = 1256) — +`extraDmg` sur ATTACK, PERMANENT (turns = NULL)."""

    def get_stat_modification_stat(self) -> int | None:
        return 0                                     # StatType.ATTACK

    def get_stat_modification_amount(self) -> int | None:
        return ability_var(_ABILITY_ID, "extraDmg", _active_level(self),
                           multiplier_pct=self.ability_variables_multiplier)


class UnbreakableDutyDamageReductionEffect(BaseEffect):
    """`IdunBattleLogic.Entities.Abilities.Active.Loki.UnbreakableDuty_DamageReductionEffect`
    (0x449 = 1097) — l'AURA de reduction de degat que `UnbreakableDuty` pose INCONDITIONNELLEMENT
    (hors du `If` des deux morts). i2 : « Ancient Thoread and all friendly units within 2 hexes
    receive -33% Damage until the start of their next turn. »

    MIRROR des deux methodes de la classe native :

        $$CreateEffectDamageMalusForDefense :
            EffectBonus.ForPercentDecrease( DSLTriggers.get_OwnerIsTarget,
                                            DSLFormulas.ConfigVar(0x46 = dmgReductionPct,
                                                                  GetAbilityState(effet), config@+0x60),
                                            Nullable<AbilityOrEffect>(...) )
        $$CreateTargetSelector :
            TargetsSelector.op_Addition( Owner@DSLSelectors+0x30,
                                         DSLSelectors.SurroundingFriends(
                                             unit = Owner@+0x30,
                                             range = ConfigConst(0x16 = range, config@+0x60),
                                             unique = 1, unitSelectionType = 3) )

    AUCUN autre noeud : pas de gate melee/ranged, pas de gate profil de degat, pas
    d'`ActiveCondition`. => -`dmgReductionPct`% sur TOUT degat recu, quel qu'en soit le vecteur.
    Jumeau STRUCTUREL de `SereneUnifierSenseOfStoneEffect` (meme `ForPercentDecrease(OwnerIsTarget
    seul, ConfigVar 0x46)`) — a UNE difference DECISIVE pres, et c'est elle qui impose deux pattes :
    SereneUnifier n'a AUCUN `CreateTargetSelector` (sa selection est faite UNE FOIS a la pose, par
    l'`AddEffect(..., targets = <selecteur>)` du poseur, donc l'effet est MATERIALISE sur chaque
    beneficiaire), alors qu'ici l'`AddEffect` natif cible `Owner@+0x30` — UNE seule entite-effet,
    portee par le caster — et la projection vit dans le `CreateTargetSelector` de l'EFFET.

    DEUX PATTES DISJOINTES, meme decoupage que `DestroyTheWitch_ExtraDamage` /
    `PsychicStalk_FriendlyChaosExtraDamage` (cf. `effects/__init__.py::
    aura_attack_damage_bonus_from_allies`), et pour la meme raison : les DEUX agregateurs
    state-wide (`damage_model.defender_modifiers`, `playbook/prediction/_shared.py`) ECARTENT le
    porteur de la liste des `carriers` quand il EST la cible du coup.
      * `create_effect_damage_malus_for_defense` = la patte SELF, celle du `op_Addition(<Owner>, …)`
        du selecteur : quand le porteur est LUI-MEME le defenseur, l'effet est dans SA liste et la
        boucle DEFENSEUR standard le voit ;
      * `create_aura_defense_damage_malus_for_ally` = la patte PROJETEE, celle du
        `SurroundingFriends(Owner, range)` : les amis a distance <= `range` du porteur.
    Ni trou, ni double-compte.

    MAGNITUDE : `ConfigVar(0x46)` = `dmgReductionPct` de la config de `UnbreakableDuty`
    (25 -> 33, plateau a 33 des L36 ; **HORS** `variablesAffectedByRarityBonus` (= ['extraDmg',
    'extraHp']) => multiplier INERTE, passe pour la forme comme sur `VexillaMagnifica` /
    `SereneUnifier`). `UnbreakableDuty` est l'ability ACTIVE de `templAncient` => le niveau est
    l'`active_ability_level` (meme `_active_level` que les deux self-buffs ci-dessus), la ou
    SereneUnifier (passif) lit `ability_level`.

    DUREE : `TurnsFromRounds(1)` au poseur = « until the start of their next turn ». Elle appartient
    a l'`AddEffect`, pas a la classe.

    RESIDU NOMME (#572) : le volet `Targetable` du `unitSelectionType = 3` n'est PAS evalue ici --
    le `ctx` de l'agregateur aura ne porte pas le `State`, donc `aura_selectors.is_targetable` n'est
    pas appelable. Ecart PERMISSIF et **borne** : il ne mordrait que sur un beneficiaire portant un
    effet `UntargetableEffect` (teleport-in), qui par construction n'encaisse aucun degat pendant sa
    disparition. MEME limite que `PsychicFortress_DmgReduction` sur le meme canal."""

    def _dmg_reduction_pct(self) -> "int | None":
        """`ConfigVar(0x46 = dmgReductionPct, GetAbilityState(effet), mult@+0x60)`."""
        return ability_var(_ABILITY_ID, "dmgReductionPct", _active_level(self),
                           multiplier_pct=self.ability_variables_multiplier)

    def create_effect_damage_malus_for_defense(self, is_melee: bool | None = None,
                                               damage_profile: str | None = None,
                                               attacker_ctx: Mapping | None = None) -> "EffectBonus | None":
        # Patte SELF (`op_Addition(<Owner>, SurroundingFriends(...))`) : le natif n'a QUE
        # `get_OwnerIsTarget` -> aucun gate (ni melee/ranged, ni profil, ni normal-only).
        pct = self._dmg_reduction_pct()
        if not pct:
            return None
        return for_percent_decrease(False, abs(int(pct)))   # owner = defenseur (l'effet est sur lui)

    def create_aura_defense_damage_malus_for_ally(self, ctx: Mapping | None = None) -> "EffectBonus | None":
        c = ctx or {}
        # Le porteur lui-meme est servi par la patte SELF ci-dessus (foyers DISJOINTS). Les deux
        # agregateurs excluent deja ce carrier ; la garde le DIT au lieu de s'y fier.
        if c.get("tgt_id") == c.get("owner_id"):
            return None
        # `SurroundingFriends` = meme equipe que le porteur.
        if c.get("owner_team") is None or c.get("owner_team") != c.get("tgt_team"):
            return None
        op, tp = c.get("owner_pos"), c.get("t_pos")
        if not op or not tp:
            return None
        rng = ability_var(_ABILITY_ID, "range", is_constant=True)   # ConfigConst(0x16) = 2
        if rng is None:
            return None
        import hexgeo
        if hexgeo.distance(tuple(op), tuple(tp)) > int(rng):
            return None
        pct = self._dmg_reduction_pct()
        if not pct:
            return None
        return for_percent_decrease(False, abs(int(pct)))
