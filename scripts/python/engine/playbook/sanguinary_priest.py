"""`SanguinaryPriestPlaybook` (triggered 1296 `SanguinaryPriest`, `bloodSanguinary` -- #921-r1).

## Corps PROPRE, et il n'herite PAS d'`AdjacentUnitPreferenceTriggeredAbilityPlaybook`

`IdunBattle.AI.Playbook.SanguinaryPriestPlaybook` porte ses DEUX faces en propre :

* `<CalculateAttackUtilityInStepsInternal>d__4$$MoveNext` rend `Fix64.op_Implicit(0)` -- **aucune**
  utilite d'attaque. Ce n'est pas un trou du port : c'est le corps ;
* `<CalculateMovementUtilityInStepsInternal>d__3$$MoveNext`, structure LUE (l'imbrication du second
  `if` DANS le premier est du decompile, pas une simplification) :

      util = Fix64.op_Implicit(0)
      foreach u in query.<slot 0x7a>(UtilityMovementCase.get_MovementTile(case),
                                     case.<+0x10 = Unit>, null, false):
          if (UnitExtensions.IsAffectedByHealType(u, HealType.NonMechanical = 0)) {
              util += Fix64.op_Implicit(GetUtilityValue("SanguinaryPriest_AdjacentNonMechanicalFriend"));
              if (UnitExtensions.IsDamagedUnit(u))
                  util += Fix64.op_Implicit(GetUtilityValue("SanguinaryPriest_AdjacentDamagedNonMechanicalFriend"));
          }
      yield return util

Slot `0x7a` = **122** (`metadata/interface_slots.tsv` : `IBattleQuery 122 GetAdjacentUnits 4 param`).

## Les trois natifs feuilles, LUS

`IdunBattle.Core.Services.BattleQuery$$GetAdjacentUnits(from, friendsOf, enemiesOf, ignoreSteppables)`
= `GetUnitsOnTiles(IterateAdjacentTiles(from, null, true, true), friendsOf, enemiesOf,
ignoreSteppables)`, et `IdunBattle.Core.Services.BattleQuery$$CountOrGetUnitsOnTiles` filtre, par
tuile : `GetUnit(t) != null`, puis `!(ignoreSteppables && IsSteppable(u))`, puis
`friendsOf != null => IsFriend(u, friendsOf)`, puis `enemiesOf != null => IsEnemy(u, enemiesOf)`.

⚠ **AUCUN `RemoveAll(u.Id == case.Unit.Id)`** -- contrairement a `SereneUnifierPlaybook` (#456-r1).
Et `IdunBattle.Entities.UnitExtensions$$IsFriend` **n'ecarte pas l'egalite** : le mover est son
propre ami. Comme il est encore SUR SON ORIGINE pendant tout le sweep, **il se compte lui-meme** des
que cette origine tombe en ring-1 de la tuile candidate -- meme regime que la famille
`friends_in_range.py`, l'inverse exact de `SereneUnifier`. D'ou les cles `self_hp`/`self_hp_max`
(#983) : sans elles le terme DAMAGED du mover serait muet.

⚠ `ignoreSteppables = false` : les Steppables sont **INCLUS**.

`IdunBattle.Entities.UnitExtensions$$IsAffectedByHealType(u, healType)` :

    base = GetBaseUnitComponent(u)
    if (base != null && base.HasTrait(0x421)) return true;          // AffectedByHealAndRepair
    if (healType == 0 /* NonMechanical */) { if (IsMechanical(u)) return false; }
    else if (healType == 1 /* Mechanical */) { if (!IsMechanical(u)) return false; }
    return true;

`IdunBattle.Entities.UnitExtensions$$IsMechanical(u)` = `HasTrait(0x5 Mechanical)
|| HasTrait(0x3e8 LivingMetal) || HasTrait(0x405 Vehicle)` -- les TROIS, lues au decompile.

`IdunBattle.Entities.UnitExtensions$$IsDamagedUnit(u)` =
`GetStat(u, StatType.Health = 5, StatPart.Missing = 4, null) > 0`, c'est-a-dire `hp_max - hp > 0`.

## Les deux poids

Cles CONFIRMEES dans `BC.Utilities.Default.TriggeredAbilities` du seed : **5** pour
`SanguinaryPriest_AdjacentNonMechanicalFriend`, **6** pour
`SanguinaryPriest_AdjacentDamagedNonMechanicalFriend`. Elles se CUMULENT sur un ami blesse (11),
puisque le second `+=` est imbrique dans le premier `if`.

## Confrontabilite du porteur

`bloodSanguinary` est un HERO du pool (`rl_duel build --list-pool`, rank courant) : etat 1 de la
gate de confrontabilite, ni greffe ni injection ni relique.

## Registre

Ability TRIGGERED : ni `TARGETING_OPTIONS` ni `ABILITY_ATTACK_TYPE` (ces deux donnees sont celles
d'`ABILITY_CLASSES`, le registre des ACTIVES castables). L'entree se fait dans
`TRIGGERED_MOVE_PLAYBOOKS` (`adjacent_unit_preference.py`), homologue de
`IdunBattle.AI.PlaybookDatabase$$LoadPlaybook`. La face ATTACK n'est PAS enregistree : son corps
natif rend `0`, donc l'absence d'entree EST le mirror.
"""
from __future__ import annotations

from .. import battle_query as bq
from ..entities.traits.unit_trait import UnitTrait
from ..entities.triggered_ability_type import TriggeredAbilityType

#: `HasTrait(0x421)` du court-circuit d'`IsAffectedByHealType` -- il PRECEDE le test mecanique et le
#: rend inoperant (une unite Mechanical qui porte ce trait est quand meme "affected").
TRAIT_AFFECTED_BY_HEAL_AND_REPAIR = UnitTrait.AffectedByHealAndRepair      # 0x421 = 1057
#: Les TROIS traits d'`UnitExtensions$$IsMechanical`, lus au decompile (aucun n'est deductible des
#: deux autres : `LivingMetal` est Necrons, `Vehicle` les chassis, `Mechanical` le trait nu).
TRAITS_MECHANICAL = (UnitTrait.Mechanical,        # 0x5
                     UnitTrait.LivingMetal,       # 0x3e8
                     UnitTrait.Vehicle)           # 0x405

#: Cles de `BC.Utilities.Default.TriggeredAbilities` (litteraux `metadata/string_literals.tsv`).
WEIGHT_KEY_ADJACENT = "SanguinaryPriest_AdjacentNonMechanicalFriend"
WEIGHT_KEY_ADJACENT_DAMAGED = "SanguinaryPriest_AdjacentDamagedNonMechanicalFriend"


def _trait_names(rec) -> frozenset:
    """Les NOMS de traits d'un enregistrement de voisin (`_unit_record` / `_adjacent_units`)."""
    return frozenset(rec.get("traits") or ())


def _is_mechanical_by_names(names) -> bool:
    """`UnitExtensions$$IsMechanical` sur des NOMS de traits (substrat des voisins)."""
    return any(t.name in names for t in TRAITS_MECHANICAL)


def _is_affected_by_heal_type_names(names) -> bool:
    """`UnitExtensions$$IsAffectedByHealType(u, HealType.NonMechanical)` sur des NOMS de traits.

    L'ORDRE compte et il est LU : le court-circuit `AffectedByHealAndRepair` passe AVANT le test
    mecanique, donc une unite Mechanical qui le porte reste soignable."""
    if TRAIT_AFFECTED_BY_HEAL_AND_REPAIR.name in names:
        return True
    return not _is_mechanical_by_names(names)


def _is_affected_by_heal_type_ids(ids) -> bool:
    """Meme predicat, sur les IDS de traits -- la forme que `ctx["unit_traits"]` publie pour le
    MOVER (les voisins, eux, portent des NOMS). Deux formes de substrat, un seul predicat."""
    s = {int(t) for t in (ids or ())}
    if int(TRAIT_AFFECTED_BY_HEAL_AND_REPAIR) in s:
        return True
    return not any(int(t) in s for t in TRAITS_MECHANICAL)


def _is_damaged(hp, hp_max) -> bool:
    """`UnitExtensions$$IsDamagedUnit` = `GetStat(u, Health, Missing) > 0`.

    TRI-ETAT en entree : l'un des deux non mesure -> `False`. Degradation RESTRICTIVE et NOMMEE (le
    terme DAMAGED se tait), jamais un `0` invente qui ferait passer l'unite pour intacte -- ce qui
    rendrait le meme `False` mais en le presentant comme une mesure."""
    if hp is None or hp_max is None:
        return False
    return (int(hp_max) - int(hp)) > 0


class SanguinaryPriestPlaybook:
    """`IdunBattle.AI.Playbook.SanguinaryPriestPlaybook` (triggered 1296). Sans etat, comme les
    autres entrees du registre MOVE (le natif n'en tient qu'UN singleton par type d'ability,
    `PlaybookDatabase$$LoadPlaybook`, cache dict)."""

    ability_id: int = int(TriggeredAbilityType.SanguinaryPriest)      # 1296 = 0x510

    def calculate_movement_utility_in_steps(self, tile, ctx: dict, wt) -> float:
        """Mirror de `<CalculateMovementUtilityInStepsInternal>d__3$$MoveNext` (cf. en-tete).

        `GetAdjacentUnits(tile, friendsOf: case.Unit, enemiesOf: null, ignoreSteppables: false)` :
        les AMIS du mover poses sur une tuile adjacente a la tuile CANDIDATE -- **self INCLUS**,
        parce que le corps ne fait aucun `RemoveAll` et qu'`IsFriend` n'ecarte pas l'egalite.

        Les deux poids se CUMULENT sur un ami blesse : le second `+=` est imbrique dans le premier
        `if`, donc un ami Mechanical sans `AffectedByHealAndRepair` ne rapporte RIEN, meme blesse."""
        w_adj = wt.sub("TriggeredAbilities", WEIGHT_KEY_ADJACENT)
        w_dmg = wt.sub("TriggeredAbilities", WEIGHT_KEY_ADJACENT_DAMAGED)
        if not w_adj and not w_dmg:
            return 0.0
        ctx = ctx or {}
        elev = ctx.get("elev_by_pos")
        neigh = bq.neigh_map(ctx)
        total = 0
        for u in (ctx.get("friend_units") or ()):
            p = u.get("pos")
            if not p or not bq.is_adjacent(tile, p, elev, neigh):
                continue
            if not _is_affected_by_heal_type_names(_trait_names(u)):
                continue                                  # `IsAffectedByHealType(u, NonMechanical)`
            total += int(w_adj or 0)
            if _is_damaged(u.get("hp"), u.get("hp_max")):
                total += int(w_dmg or 0)                  # `IsDamagedUnit(u)` -- CUMULE
        # SELF : cf. l'en-tete -- le corps natif n'exclut PAS `case.Unit`, et le mover est encore
        # sur son origine pendant tout le sweep. `ctx["unit_traits"]` porte des IDS (pas des noms).
        sp = ctx.get("self_pos")
        if sp and bq.is_adjacent(tile, tuple(sp), elev, neigh) \
                and _is_affected_by_heal_type_ids(ctx.get("unit_traits")):
            total += int(w_adj or 0)
            if _is_damaged(ctx.get("self_hp"), ctx.get("self_hp_max")):
                total += int(w_dmg or 0)
        return float(total)
