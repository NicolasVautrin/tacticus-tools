"""`WayOfTheShortBlade` (`TriggeredAbilityType` 0x5db-1 ... cf. plus bas) -- passif de kit de
`tauFarsight` << Commander Farsight >> (HERO T'au, `lineup` mais HORS POOL : le porteur entre par
`catalog_inject.write_augmented_seed_bc` + `rl_duel build --seed-bc`, cf.
`docs/rl/case-92-catalog-injection.md` §6). RE : decompile ghidra, build `rnca9r7q6c` (#1019).

i2 (`Abilities/WayOfTheShortBlade_CurrentLevelDescription`) :
« Normal ranged attacks of other friendly Characters within {range} hexes against enemies that are
adjacent to a friendly Character ignore {armorIgnored} Armour and deal +{extraDmgPct}% Damage,
except attacks that deal Psychic Damage. -- Commander Farsight and other friendly T'au Empire
Characters within {range} hexes that perform a melee attack immediately perform a normal ranged
attack against the same unit, even if they are adjacent to it. »

===================================================================================================
LE KIT NATIF -- QUATRE classes, DEUX effets, et l'appariement est LU
===================================================================================================

| classe native                                                                | role |
|------------------------------------------------------------------------------|------|
| `IdunBattleLogic.Entities.Abilities.Triggered.Loki.WayOfTheShortBlade_InitAbility`   | pose les DEUX effets sur le PORTEUR |
| `IdunBattleLogic.Entities.Abilities.Triggered.Loki.WayOfTheShortBlade_AttackAbility` | l'attaque supplementaire |
| `IdunBattle.Entities.Effects.Loki.WayOfTheShortBladeEffect`                          | effet 0x5db = 1499 `WayOfTheShortBlade_DamageBuff` |
| `IdunBattle.Entities.Effects.Loki.WayOfTheShortBlade_AdditionalAttackMarkerEffect`   | effet 0x5dc = 1500 `WayOfTheShortBlade_AdditionalAttackMarker` |

`...WayOfTheShortBlade_InitAbility$$CreateTrigger` =

    OnOwnerSpecificAbilityInit(this.AbilityType)

`...WayOfTheShortBlade_InitAbility$$CreateBehaviour` =

    AddEffect( 0x5db, BaseTriggeredAbility.get_AbilityStateReference(this),
               source = Owner@<DSLSelectors+0x30>, targets = Owner@<+0x30>, turns = <zeroe> )
    op_BitwiseAnd
    AddEffect( 0x5dc, ..., source = Owner@<+0x30>, targets = Owner@<+0x30>, turns = <zeroe> )

Les DEUX effets vivent donc sur FARSIGHT et se PROJETTENT par leur `CreateTargetSelector` -- canal
AURA cote SOURCE, exactement le patron `DefenderOfTheGreaterGood_ExtraDmg` / `SpotterReworked`.
CONFIRME LIVE (runner `--seed-bc` avec `tauFarsight` injecte, board MC1_67) : `decisionView.effects`
porte les deux effets sur `u81 [tauFarsight]` et **sur personne d'autre**, alors meme que deux
autres T'au (`tauCrisis`, `tauMarksman`) etaient a portee.

===================================================================================================
1499 `WayOfTheShortBlade_DamageBuff` -- le volet porte par ce module
===================================================================================================

## Le SELECTEUR -- `WayOfTheShortBladeEffect$$CreateTargetSelector`

    A = UnitsWithTrait( SurroundingFriends(Owner@<+0x30>, range = GetNumberConstant(0x16), 1, 3),
                        0x10 = UnitTrait.Hero, 3 )
    return Unique( UnitsWithRangedWeapons(A)  op_Addition  UnitsFromFaction(A, 9 = UnitFaction.Tau, 3) )

Trois lectures qui ne se devinent pas :

  1. **`SurroundingFriends` EXCLUT le porteur** (`SurroundingTiles(range) - Tiles(self)`, mesure
     deja etablie par `PathOfCommandExtraDmgEffect`), et **ce selecteur-ci n'ajoute PAS `+ Owner`**
     -- contrairement a son jumeau 1500, qui l'ajoute explicitement. Farsight ne recoit donc PAS
     son propre buff de degat, ce que l'i2 dit deja par « of **other** friendly Characters ».
     Recopier le jumeau ici donnerait un bonus de plus, silencieusement.
  2. **L'UNION n'est PAS une intersection** : `UnitsWithRangedWeapons(A) + UnitsFromFaction(A, Tau)`
     (`TargetsSelector$$op_Addition`), puis `Unique`. Un T'au SANS arme de portee est donc buffe --
     et c'est coherent, puisque 1500 va lui faire tirer une attaque normale a distance.
  3. **`range` est la CONSTANTE `0x16` du gameconfig** (`AbilityConstantType.range` = 2), pas un
     litteral DSL -- meme lecture que `PathOfCommand` / `LordOfTheHost` / `SpotterReworked`.

## La CONDITION -- `WayOfTheShortBladeEffect$$IsValidAttackForBonus`

    get_OwnerIsCaster
      & IsNormalAttack
      & IsRangedAttack
      & !CurrentAttackDamageProfileIs( 0xd = DamageProfileType.Psychic )
      & AmountIsGreaterThanZero( UnitsWithTrait( Friends( Owner@<+0x30>,
                                                          AdjacentUnits(Target@<+0x60>, 1, 3), 3 ),
                                                 0x10 = Hero, 3 ) )

`get_OwnerIsCaster` dans un contexte d'AURA = « ce chemin n'est appele que pour l'attaque du
BENEFICIAIRE » (mesure deja ecrite pour `DefenderOfTheGreaterGood_ExtraDmgEffect`). Le dernier
noeud est le terme qui DISCRIMINE : la cible doit avoir au moins un `Hero` ami du beneficiaire
ADJACENT -- « against enemies that are adjacent to a friendly Character ».

## La MAGNITUDE -- deux corps, DEUX canaux, et un seul est branche

    `...$$CreateEffectDamageBonusForAttack` = EffectBonus.ForPercentIncrease( IsValidAttackForBonus(),
                                                  ConfigVar(0xa = extraDmgPct, GetAbilityState(this), cfg) )
    `...$$IgnoreArmor`                      = ConfigVar(0x40 = armorIgnored, GetAbilityState(this), cfg)

`ForPercentIncrease` ecrit son montant a `EffectBonus+0x08` (contre `+0x10` pour `ForAddition`) :
c'est le canal POURCENT, pas l'additif. `extraDmgPct` n'est PAS dans
`variablesAffectedByRarityBonus` (`armorIgnored` l'est, seul) -- `ability_var` applique donc le
multiplicateur a l'un et pas a l'autre, sans qu'on ait a le coder ici.

⚠ **`WayOfTheShortBladeEffect$$IgnoreArmor` PARTAGE SON CORPS** (`1059b60`) avec
`Helspear_IgnoreArmorEffect$$IgnoreArmor` et quatre autres classes -- 6 xrefs DATA (six slots de
vtable), 0 xref CODE. C'est le piege « l'ABSENCE d'une methode dans les tables ne prouve RIEN » pris
par l'autre bout : ici la table nomme `WayOfTheShortBladeEffect` comme proprietaire, et #1008 a
etabli que le corps sert AUSSI `Helspear`. Le corps est le meme, `ConfigVar(0x40 = armorIgnored)`,
et les DEUX gameconfigs portent bien une variable `armorIgnored` -- l'attribution ne change donc
rien a la lecture.

===================================================================================================
CE QUE CE MODULE NE PORTE PAS -- residus NOMMES, pas des oublis
===================================================================================================

* **`#1019-r1` -- la PENETRATION D'ARMURE n'atteint pas le calcul.** `ignore_armor()` est expose et
  LU (ci-dessous) mais n'est PAS branche : cote port, `BaseEffect.get_armor_penetration` n'est
  appele que par `_attacker_effect_bonuses` (`entities/effects/__init__.py`), la boucle des effets
  de l'ATTAQUANT -- or cet effet-ci vit sur FARSIGHT, et n'entre que par les agregateurs d'AURA,
  qui n'ont AUCUN canal armure cote attaquant. C'est le MEME etage que `#1008-r2`, pris par l'autre
  face (defenseur la-bas, aura ici). Le brancher sur le canal attaquant serait un no-op silencieux.
  Consequence arithmetique reelle : le port rend le `+extraDmgPct%` mais pas les `armorIgnored`
  points de percage.
* **`#1019-r2` -- l'effet 1500 `WayOfTheShortBlade_AdditionalAttackMarker` et son
  `WayOfTheShortBlade_AttackAbility`.** RE complete dans `docs/rl/case-1019-way-of-the-short-blade.md`
  §3 ; ce module porte la classe d'effet (pour que la couverture voie l'effet et que son selecteur
  soit lisible) mais AUCUN comportement de combat.
"""
from __future__ import annotations

from collections.abc import Mapping

import hexgeo

from ....services.effect_bonus import EffectBonus, for_percent_increase
from ...damage_profile_type import DamageProfileType
from ...traits.unit_trait import UnitTrait
from ...unit_faction import UnitFaction
from ..base import BaseEffect
from ..magnitude import ability_var

#: Le NOM d'ability sous lequel le gameconfig indexe la config lue par les deux `ConfigVar`
#: (`effet+0x60`), et par le `GetNumberConstant(0x16 = range)` du selecteur.
ABILITY_ID = "WayOfTheShortBlade"

#: `AbilityVariableType` 0xa / 0x40 -- LUS au decompile, jamais deduits du nom.
EXTRA_DMG_PCT_KEY = "extraDmgPct"          # ConfigVar(0xa)  -- HORS variablesAffectedByRarityBonus
ARMOR_IGNORED_KEY = "armorIgnored"         # ConfigVar(0x40) -- DANS variablesAffectedByRarityBonus
#: `AbilityConstantType.range` = 0x16 -- `GetNumberConstant(cfg, 0x16)` du `SurroundingFriends`.
RANGE_CONSTANT_KEY = "range"

#: `UnitsWithTrait(..., 0x10, 3)` -- `UnitTrait.Hero` = 16 (« Character » dans l'i2).
_HERO = UnitTrait.Hero.name                                   # "Hero"
#: `UnitsFromFaction(A, 9, 3)` -- `UnitFaction.Tau` = 9 ; cote gameconfig le `FactionId` vaut "Tau".
_TAU = UnitFaction.Tau.name                                   # "Tau"
#: `!CurrentAttackDamageProfileIs(0xd)` -- `DamageProfileType.Psychic` = 13.
_PSYCHIC = DamageProfileType.Psychic.name                     # "Psychic"


class WayOfTheShortBladeDamageBuffEffect(BaseEffect):
    """`WayOfTheShortBladeEffect` -- effet 0x5db = 1499 `WayOfTheShortBlade_DamageBuff`, pose sur
    FARSIGHT a l'init de son passif et PROJETE sur ses amis par `CreateTargetSelector` (canal AURA
    cote SOURCE, meme patron que `DefenderOfTheGreaterGoodExtraDmgEffect`).

    Le port porte le canal POURCENT (`create_aura_attack_damage_bonus_for_ally`) et EXPOSE la
    magnitude de percage sans la brancher -- residu `#1019-r1`, cf. l'en-tete."""

    def _range(self) -> int:
        """`GetNumberConstant(cfg, 0x16 = range)` -- CONSTANTE du gameconfig (aucun niveau, aucun
        multiplicateur), lue par le `SurroundingFriends` du selecteur."""
        rng = ability_var(ABILITY_ID, RANGE_CONSTANT_KEY, is_constant=True)
        return int(rng) if rng else 2

    def aura_selector_covers(self, ctx: Mapping | None = None) -> bool:
        """`WayOfTheShortBladeEffect$$CreateTargetSelector` (cf. l'en-tete §Le SELECTEUR) :

            Unique( UnitsWithRangedWeapons(A) + UnitsFromFaction(A, Tau) )
            avec A = UnitsWithTrait( SurroundingFriends(Owner, range, 1, 3), Hero )

        Methode SEPAREE du gate d'attaque parce que ce sont deux artefacts natifs DISTINCTS
        (`CreateTargetSelector` vs `IsValidAttackForBonus`) et que les melanger rendrait la
        structure native illisible -- meme decoupage que `DefenderOfTheGreaterGood`."""
        c = ctx or {}
        if c.get("att_id") == c.get("owner_id"):
            return False                                  # SurroundingFriends EXCLUT le porteur
        if c.get("owner_team") is None or c.get("owner_team") != c.get("att_team"):
            return False                                  # ...Friends = meme equipe que Farsight
        op, ap = c.get("owner_pos"), c.get("att_pos")
        if not op or not ap:
            return False
        if hexgeo.distance(op, ap) > self._range():       # SurroundingFriends(range = 2)
            return False
        if _HERO not in (c.get("att_traits") or frozenset()):
            return False                                  # UnitsWithTrait(0x10 = Hero)
        # UNION, pas intersection (en-tete §2) : arme de portee OU faction T'au.
        return bool(c.get("att_has_ranged_weapon")) or c.get("att_faction") == _TAU

    def _is_valid_attack_for_bonus(self, c: Mapping) -> bool:
        """`WayOfTheShortBladeEffect$$IsValidAttackForBonus` -- les CINQ noeuds, dans l'ordre du
        decompile. `get_OwnerIsCaster` est STRUCTUREL sur ce canal (l'agregateur n'appelle cette
        methode que pour l'attaque du beneficiaire) et n'a donc pas de terme propre.

        POLARITES des cles absentes -- elles ne sont PAS toutes les memes, et ca ne se devine pas :
          * `is_melee` : TRI-ETAT, seul `False` OUVRE (`IsRangedAttack`). `None` FERME -- le port ne
            devine pas la nature du coup. MEME convention que `DefenderOfTheGreaterGood`.
          * `is_normal_attack` : seul `False` FERME (`IsNormalAttack`). Absent -> OUVERT, meme
            convention que `DoomExtraDmgEffect`, qui lit la meme cle sur le meme agregateur.
          * `damage_profile` : absent -> gate OUVERT (le natif compare a l'ordinal 13, et un
            contexte sans profil vaut `DamageProfileType.None_`, hors egalite).
          * `friend_heroes_adjacent_to_target` : absent (`None`) -> FERME. C'est un compte, pas un
            booleen : le natif ecrit `AmountIsGreaterThanZero(...)`, et un canal NON MESURE n'est
            pas un canal VIDE (meme discipline tri-etat que `Scene.is_effect_target`)."""
        if c.get("is_melee") is not False:                          # IsRangedAttack
            return False
        if c.get("is_normal_attack") is False:                      # IsNormalAttack
            return False
        if (c.get("damage_profile") or None) == _PSYCHIC:           # !CurrentAttackDamageProfileIs(0xd)
            return False
        # AmountIsGreaterThanZero( UnitsWithTrait( Friends(Owner, AdjacentUnits(Target)), Hero ) )
        n = c.get("friend_heroes_adjacent_to_target")
        return n is not None and int(n) > 0

    def create_aura_attack_damage_bonus_for_ally(self, ctx: Mapping | None = None) -> EffectBonus | None:
        """`WayOfTheShortBladeEffect$$CreateEffectDamageBonusForAttack` =
        `EffectBonus.ForPercentIncrease( IsValidAttackForBonus(), ConfigVar(0xa = extraDmgPct) )`.

        Canal POURCENT (montant a `EffectBonus+0x08`), pas additif -- lu a la DISPOSITION des champs,
        comme pour `DefenderOfTheGreaterGood` (qui, lui, ecrit a `+0x10`)."""
        c = ctx or {}
        if not self._is_valid_attack_for_bonus(c):
            return None
        if not self.aura_selector_covers(c):
            return None
        lvl = self.ability_level if self.ability_level is not None else self.level
        if lvl is None:                                   # ConfigVar sans AbilityState -> pas de magnitude
            return None
        pct = ability_var(ABILITY_ID, EXTRA_DMG_PCT_KEY, lvl,
                          multiplier_pct=self.ability_variables_multiplier)
        if not pct:
            return None
        return for_percent_increase(True, abs(int(pct)))

    def ignore_armor(self, unit_state: Mapping | None = None) -> int | None:
        """`WayOfTheShortBladeEffect$$IgnoreArmor` =
        `ConfigVar(0x40 = armorIgnored, BaseEffect.GetAbilityState(this), cfg@this+0x60)`.

        EXPOSE, PAS BRANCHE -- residu `#1019-r1` (l'en-tete dit pourquoi : le seul lecteur porte de
        `get_armor_penetration` est la boucle des effets de l'ATTAQUANT, et cet effet-ci vit sur
        Farsight). `get_armor_penetration` n'est deliberement PAS surcharge : le trou reste VISIBLE
        au lieu d'etre un no-op qui se lit comme « porte »."""
        lvl = self.ability_level if self.ability_level is not None else self.level
        return ability_var(ABILITY_ID, ARMOR_IGNORED_KEY, lvl,
                           multiplier_pct=self.ability_variables_multiplier)


class WayOfTheShortBladeAdditionalAttackMarkerEffect(BaseEffect):
    """`WayOfTheShortBlade_AdditionalAttackMarkerEffect` -- effet 0x5dc = 1500, pose sur FARSIGHT
    par le MEME `WayOfTheShortBlade_InitAbility$$CreateBehaviour`, et projete par son propre
    selecteur :

        `...$$CreateTargetSelector` =
            UnitsFromFaction( UnitsWithTrait( SurroundingFriends(Owner@<+0x30>, range, 1, 3),
                                              0x10 = Hero, 3 ),
                              9 = UnitFaction.Tau, 3 )
            op_Addition  Owner@<+0x30>

        `...$$CreateActiveCondition` = `<DSLTriggers+0x40>`  (constante VRAIE : toujours actif)
        `...$$.ctor`                 = `BaseEffect( AbilityOrEffect(<litteral>), hasAutomaticActivation = 1 )`

    ⚠ `+ Owner` EST ECRIT ICI et PAS dans le selecteur du jumeau 1499 : Farsight se marque LUI-MEME
    (« Commander Farsight **and** other friendly T'au Empire Characters »), alors qu'il ne recoit
    pas son propre bonus de degat. Les deux selecteurs se ressemblent a un noeud pres, et ce noeud
    change qui est concerne -- ne jamais recopier l'un sur l'autre.

    ⚠ La FACTION est filtree ICI (`UnitsFromFaction(..., Tau)` en INTERSECTION) alors que le jumeau
    1499 l'utilise en UNION avec les porteurs d'arme de portee. Meme vocabulaire, semantique
    opposee.

    AUCUN canal de degat : cette classe existe pour que l'effet soit NOMME et son selecteur LISIBLE.
    Le comportement (l'attaque normale supplementaire apres une attaque de melee) vit dans
    `WayOfTheShortBlade_AttackAbility` -- NON PORTE, residu `#1019-r2`, RE complete dans
    `docs/rl/case-1019-way-of-the-short-blade.md` §3."""

    def aura_selector_covers(self, ctx: Mapping | None = None) -> bool:
        """`WayOfTheShortBlade_AdditionalAttackMarkerEffect$$CreateTargetSelector`, mirror 1:1.

        `+ Owner@<+0x30>` = la branche qui inclut Farsight lui-meme -- testee EN PREMIER, comme
        l'`op_Addition` du natif la rend inconditionnelle."""
        c = ctx or {}
        if c.get("owner_team") is None or c.get("owner_team") != c.get("att_team"):
            return False
        if c.get("att_id") == c.get("owner_id"):
            return True                                   # `op_Addition Owner@<+0x30>`
        op, ap = c.get("owner_pos"), c.get("att_pos")
        if not op or not ap:
            return False
        rng = ability_var(ABILITY_ID, RANGE_CONSTANT_KEY, is_constant=True)
        if hexgeo.distance(op, ap) > int(rng if rng else 2):        # SurroundingFriends(range)
            return False
        if _HERO not in (c.get("att_traits") or frozenset()):       # UnitsWithTrait(0x10 = Hero)
            return False
        return c.get("att_faction") == _TAU                          # UnitsFromFaction(9 = Tau)
