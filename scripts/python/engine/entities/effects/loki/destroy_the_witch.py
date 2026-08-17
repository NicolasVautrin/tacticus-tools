"""`DestroyTheWitch` (passif de `templHelbrecht` << High Marshal Helbrecht >>, TriggeredAbilityType
0x443 = 1091) -- les DEUX owner-effects du passif anti-Psyker. Module dedie : les deux classes
PARTAGENT leur `CreateActiveCondition` (corps NATIF FONDU, cf. plus bas), et ce partage est le fait
le moins intuitif du cas.

i2 : « Gains +1 Movement when there's an enemy Psyker on the battlefield. This unit and friendly
adjacent units deal +1091 Damage with melee attacks against Psykers. »

================================================================================================
RE (decompile ghidra, build `gqfc5mff6c`) -- decompile = verite
================================================================================================

## `IdunBattleLogic.Entities.Abilities.Triggered.Loki.DestroyTheWitchAbility$$CreateBehaviour`

    AddStaticStatModifierEffectToOwner( 0x440 = 1088 DestroyTheWitch_ExtraMove,
                                        stat = 1 (MOVEMENT),
                                        Direct( GetNumberConstant(cfg, 0xe) = extraMovement = 1 ) )
    &  AddEffect( 0x441 = 1089 DestroyTheWitch_ExtraDamage,
                  AbilityStateReference, cible = Owner@0x148 )

(`AbilityBehaviour.op_BitwiseAnd` des deux feuilles ; slots `AbilityEntities` de
`IdunBattleLogic.Entities.DSLSelectors$$InitializeShared` : `0x80 AllUnits · 0xc0 Direct(1) ·
0x148 Owner · 0x178 Target`.)

## `CreateActiveCondition` -- UN SEUL CORPS NATIF POUR LES DEUX EFFETS (folding IL2CPP)

    AmountIsEqualOrGreater( Enemies( Owner@0x148,
                                     UnitsWithTrait( AllUnits@0x80, 0x3ea = 1002 Psyker, 3 ), 3 ),
                            One@0xc0 )

= « au moins UN Psyker ENNEMI (du porteur) sur le plateau ».

⚠ PIEGE DE TABLE, resolu -- les DEUX tables de symboles nomment cette MEME adresse DIFFEREMMENT :
  * `data/symbols/<build>/frida/methods.tsv`  -> `DestroyTheWitch_ExtraMoveEffect.CreateActiveCondition`
  * `data/symbols/<build>/ghidra/functions.tsv` -> `DestroyTheWitch_ExtraDamageEffect$$CreateActiveCondition`
Ce n'est PAS « l'une des deux ment » : IL2CPP **fond les corps de methode identiques** (une seule
adresse pour N methodes), et les deux tables sont DEDUPLIQUEES PAR ADRESSE (mesure : 121 501 lignes
pour 121 501 RVA distinctes cote frida) -> chacune ne garde qu'UN representant du groupe fondu, et
elles n'ont pas garde le meme. Meme signature exactement au meme endroit pour
`MartialSuperiority_VisualEffect.CreateActiveCondition` (frida) vs
`AReactivateOverwatchEffect$$CreateActiveCondition` (ghidra) -- corps `NOT IsTurnOf(owner@0xa0)`,
trivialement partageable.

GROUND TRUTH LIVE (probe_133_destroy_the_witch.py, 3 configurations, board MC1_67 seed 777) :
  * a-units = astraPrimarisPsy + orksNob        -> Helbrecht porte 1088 ET 1089
  * a-units = orksNob + orksRuntherd            -> Helbrecht ne porte NI 1088 NI 1089
  * p-units = Helbrecht + astraPrimarisPsy (Psyker ALLIE), a-units sans Psyker
                                                -> Helbrecht ne porte NI 1088 NI 1089
=> la condition porte bien sur les Psykers **ENNEMIS**, et elle gouverne LES DEUX effets. Le corps
fondu est donc bien celui des DEUX `CreateActiveCondition` : il est porte ici sur les deux classes.

## `DestroyTheWitch_ExtraMoveEffect : StaticStatModifierEffect` (classes.tsv)

Aucune autre methode : le stat-mod est celui de la feuille `AddStaticStatModifierEffectToOwner`
(stat 1 = MOVEMENT, montant `extraMovement`). Confirme live -- `decisionView.units[].effects` de
Helbrecht : `statMod = {StatType: 1, Amount: 1, IsDynamic: 0}`.

## `DestroyTheWitch_ExtraDamageEffect : BaseEffect` (classes.tsv) -- volet DEGAT

`IdunBattle.Entities.Effects.Loki.DestroyTheWitch_ExtraDamageEffect$$CreateTargetSelector` :

    Unique( SurroundingFriends(Owner@0x148, radius=1, 3)  op_Addition  Owner@0x148 )

`IdunBattleLogic.Entities.DSLSelectors$$SurroundingFriends(sel, r, ...)` =
`Friends(sel, Units( SurroundingTiles(sel, r) - Tiles(sel) ))` -> ANNEAU-1, porteur EXCLU ; le
`op_Addition Owner` le RE-AJOUTE. Beneficiaires = **Helbrecht + ses allies hex-adjacents**.

`...DestroyTheWitch_ExtraDamageEffect$$CreateEffectDamageBonusForAttack` :

    EffectBonus{ amount = ConfigVar(8 = extraDmg, GetAbilityState(effet), effet+0x60),
                 trigger = get_OwnerIsCaster & IsMeleeAttack & HasTrait(Target@0x178, 0x3ea Psyker) }

-> +`extraDmg[niveau PASSIF de Helbrecht] x multiplier` PLAT par coup (canal additif
`DamageModifiers.Add`, meme canal que SmashaEad/LordOfTheHost), sur les attaques **MELEE** des
beneficiaires **contre une cible portant le trait Psyker**.

================================================================================================
FORME DU PORT
================================================================================================
- Volet MOVE  = canal stat-mod DECLARATIF (`get_stat_modification_stat/amount` + `reverted_stats`),
  comme `AnvilShield_BlockChanceBelowHealthCap` : la contribution entre/sort du `UnitStats` selon
  `is_active`, via `runner/operations/refresh_effects.py`.
- Volet DEGAT = DEUX pattes, comme tout effet-aura a `CreateTargetSelector` :
  `create_effect_damage_bonus_for_attack` (le PORTEUR attaque : le selecteur contient `Owner`) et
  `create_aura_attack_damage_bonus_for_ally` (un ALLIE ADJACENT attaque). Pas de double-compte :
  l'agregateur d'auras (`damage_model._apply_ally_attack_damage_auras` / prediction
  `_apply_ally_attack_dmg_bonus`) EXCLUT deja `uid == att_id`.

RESIDUS EXPLICITES :
 * `is_active` lit `unit_state["enemy_psykers_alive"]`, renseigne par
   `runner/operations/refresh_effects._unit_state` (qui, lui, a l'etat complet). Les appelants qui
   ne passent qu'un `{"hp": ...}` laissent la cle ABSENTE -> l'effet est considere ACTIF (le seed
   live ne capte QUE les effets actifs : « present == actif », invariant case-160/case-127).
 * Le driver `refresh_stat_modifier_effects` n'est appele aujourd'hui que sur l'unite qui vient de
   PRENDRE des degats (`operations/damage.py`). La mort du DERNIER Psyker ennemi ne revoque donc pas
   le +1 MOVEMENT de Helbrecht offline tant que le driver n'est pas elargi (elargissement = modif de
   driver PARTAGE, hors perimetre de ce cas). Sans consequence sur l'axe DEGAT (cf. ci-dessous).
 * Le volet DEGAT n'a PAS besoin du conjoint « >=1 Psyker ennemi » pour etre exact : son propre gate
   `HasTrait(Target, Psyker)` le SUBSUME (une attaque vise un ennemi du beneficiaire, donc une cible
   Psyker EST un Psyker ennemi). Le conjoint est neanmoins porte (fidelite au corps fondu).
"""
from __future__ import annotations

from collections.abc import Mapping

from ....services.effect_bonus import EffectBonus, for_addition
from ..base import BaseEffect
from ..magnitude import ability_var
from ...stats import StatType

DESTROY_THE_WITCH = "DestroyTheWitch"
PSYKER_TRAIT = "Psyker"          # UnitTrait 0x3ea = 1002 (`UnitsWithTrait(AllUnits, 0x3ea)`)


def _enemy_psyker_on_battlefield(unit_state: Mapping | None) -> bool:
    """MIRROR du corps natif FONDU `CreateActiveCondition` (cf. en-tete) :
    `AmountIsEqualOrGreater( Enemies(Owner, UnitsWithTrait(AllUnits, Psyker)), One )`.

    Lit `unit_state["enemy_psykers_alive"]` (compte des unites VIVANTES d'une equipe adverse au
    porteur portant le trait `Psyker`), renseigne par `refresh_effects._unit_state`. Cle ABSENTE =
    contexte non fourni -> True (« present == actif », l'effet seede vient d'une capture live qui
    n'expose QUE les actifs)."""
    if unit_state is None or "enemy_psykers_alive" not in unit_state:
        return True
    return int(unit_state.get("enemy_psykers_alive") or 0) >= 1


class DestroyTheWitchExtraMoveEffect(BaseEffect):
    """`DestroyTheWitch_ExtraMove` (EffectType 0x440 = 1088) -- `StaticStatModifierEffect` pose sur
    Helbrecht par `DestroyTheWitchAbility$$CreateBehaviour`
    (`AddStaticStatModifierEffectToOwner(1088, stat=1 MOVEMENT, Direct(GetNumberConstant(0xe)
    = extraMovement))`), ACTIF tant qu'au moins un Psyker ENNEMI est sur le plateau.

    Canal DECLARATIF (`get_stat_modification_stat`/`_amount`, PAS `applied_stat_mods`) : c'est ce
    qui met la contribution sous le pilotage de `RefreshEffectsOperation`
    (`runner/operations/refresh_effects.py`), comme `AnvilShield_BlockChanceBelowHealthCap` -- la
    seule autre famille a `CreateActiveCondition` + stat-mod. Ground truth live : `statMod =
    {StatType: 1, Amount: 1}` sur Helbrecht des qu'un Psyker ennemi est present."""

    def is_active(self, unit_state: Mapping | None = None) -> bool:
        return _enemy_psyker_on_battlefield(unit_state)

    def get_stat_modification_stat(self) -> "int | None":
        return int(StatType.MOVEMENT)                       # statType 1 de la feuille native

    def get_stat_modification_amount(self) -> "int | None":
        # `Direct(GetNumberConstant(cfg, 0xe))` = constante gameconfig `extraMovement` (= 1).
        return ability_var(DESTROY_THE_WITCH, "extraMovement", is_constant=True)

    def reverted_stats(self) -> "list":
        return [StatType.MOVEMENT]


class DestroyTheWitchExtraDamageEffect(BaseEffect):
    """`DestroyTheWitch_ExtraDamage` (EffectType 0x441 = 1089) -- effet-AURA pose sur Helbrecht,
    projete sur **lui-meme + ses allies hex-adjacents** (`CreateTargetSelector` =
    `Unique(SurroundingFriends(Owner, 1) + Owner)`), qui gagnent +`extraDmg` PLAT par coup sur leurs
    attaques MELEE **contre une cible Psyker** (`CreateEffectDamageBonusForAttack` =
    `get_OwnerIsCaster & IsMeleeAttack & HasTrait(Target@0x178, Psyker)`).

    Niveau/multiplier = ceux du PORTEUR (l'effet-entite vit sur Helbrecht et porte son
    `passiveAbilityLevel` / `abilityVariablesMultiplier`), comme LordOfTheHost/BeaconOfRage."""

    def _amount(self) -> "int | None":
        """`ConfigVar(8 = extraDmg, GetAbilityState(effet))` x multiplier du PORTEUR
        (`extraDmg` est dans `variablesAffectedByRarityBonus`). `ability_level` absent (pas
        d'AbilityState capte) -> None = pas de contribution (« present != applique »)."""
        if self.ability_level is None:
            return None
        return ability_var(DESTROY_THE_WITCH, "extraDmg", self.ability_level,
                           multiplier_pct=self.ability_variables_multiplier)

    def create_effect_damage_bonus_for_attack(self, is_ranged: bool | None = None,
                                              has_moved: bool | None = None,
                                              target_traits=None,
                                              is_prediction: bool = False,
                                              is_normal_attack: bool | None = True,
                                              target_armor_reduced: bool | None = None,
                                              att_ctx=None) -> EffectBonus | None:
        """PATTE SELF du selecteur (`op_Addition Owner@0x148`) : Helbrecht lui-meme attaque.
        Gates natifs : `IsMeleeAttack` (-> `is_ranged` faux) et `HasTrait(Target, Psyker)`.
        `get_OwnerIsCaster` est vrai par construction sur ce canal (il n'est appele que pour les
        attaques du porteur, cf. `_attacker_effect_bonuses`)."""
        if is_ranged:                                       # IsMeleeAttack
            return None
        if PSYKER_TRAIT not in (target_traits or ()):       # HasTrait(Target@0x178, 0x3ea)
            return None
        amt = self._amount()
        return for_addition(True, amt) if amt else None

    def create_aura_attack_damage_bonus_for_ally(self, ctx: Mapping | None = None) -> EffectBonus | None:
        """PATTE AURA du selecteur (`SurroundingFriends(Owner@0x148, 1)`) : un ALLIE HEX-ADJACENT du
        porteur attaque. Memes gates de coup (`IsMeleeAttack`, cible Psyker) + la geometrie du
        selecteur, RE-EVALUEE PAR CANDIDAT (l'agregateur passe la tuile d'attaque evaluee)."""
        c = ctx or {}
        if not c.get("is_melee"):                           # IsMeleeAttack
            return None
        if c.get("att_id") == c.get("owner_id"):            # SurroundingFriends EXCLUT le porteur
            return None                                     # (patte SELF ci-dessus)
        if c.get("owner_team") is None or c.get("owner_team") != c.get("att_team"):
            return None                                     # Friends = meme equipe que le porteur
        if PSYKER_TRAIT not in (c.get("tgt_traits") or ()):  # HasTrait(Target@0x178, 0x3ea)
            return None
        op, ap = c.get("owner_pos"), c.get("att_pos")
        if not op or not ap:
            return None
        import hexgeo
        if hexgeo.distance(op, ap) > 1:                     # SurroundingTiles(owner, radius 1)
            return None
        amt = self._amount()
        return for_addition(True, amt) if amt else None

    def is_active(self, unit_state: Mapping | None = None) -> bool:
        """Corps natif FONDU partage avec `DestroyTheWitch_ExtraMoveEffect` (cf. en-tete) -- porte par
        fidelite ; le gate `HasTrait(Target, Psyker)` du bonus le SUBSUME deja."""
        return _enemy_psyker_on_battlefield(unit_state)
