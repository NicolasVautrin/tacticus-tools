"""`FirstAmongTraitors` (passif de `blackAbaddon` << Abaddon the Despoiler >>,
`TriggeredAbilityType` 0x428 = 1064) -- face COMBAT : l'effet-AURA `FirstAmongTraitors_ExtraDmg`.

Tache #926. Les DEUX faces DECISION vivent ailleurs :
  * NON-OWNER `playbook/non_owner.py::FirstAmongTraitorsNonOwnerPlaybook` (#477-r37, deja portee) ;
  * OWNER     `playbook/friends_in_range.py::FirstAmongTraitorsPlaybook` (#926).

i2 : « Friendly Chaos units within 2 hexes deal +<n> Damage with attacks. This bonus increases
each time Abaddon attacks. »

================================================================================================
RE (decompile ghidra, build `rnca9r7q6c`) -- decompile = verite
================================================================================================

## 0. L'ABILITY -- `IdunBattleLogic.Entities.Abilities.Active.Loki.FirstAmongTraitorsAbility`

Parent LU dans `data/symbols/<build>/frida/classes.tsv` :
`IdunBattle.Entities.Abilities.AOwnerEffectTriggeredAbility`. La classe ne DECLARE que deux corps :

    IdunBattleLogic...FirstAmongTraitorsAbility$$GetEffectType   ->  `return 0x427`   (= 1063)
    IdunBattleLogic...FirstAmongTraitorsAbility$$GetRange        ->  `AbilityConfiguration
                                                                      .GetNumberConstant(cfg, 0x16)`

Aucun `CreateTrigger` / `CreateBehaviour` propre : ce sont les corps de BASE
(`IdunBattle.Entities.Abilities.AOwnerEffectTriggeredAbility$$CreateTrigger` =
`OnOwnerSpecificAbilityInit(this.AbilityType)`, `$$CreateBehaviour` = `AddEffect(GetEffectType(),
AbilityStateReference, source = Owner, targets = Owner)`), d'ou le canal de port
`ABILITY_INIT_OWNER_EFFECTS` (pose) + `EFFECT_CLASSES` (comportement), JAMAIS `ABILITY_TRIGGERS`
ni `ABILITY_CLASSES` (ce n'est pas une active -- le namespace `...Abilities.Active.Loki` du
symbole ne dit RIEN de la voie : la classe derive d'un `...TriggeredAbility`, et le gameconfig la
range en `passiveAbilities`).

`0x16` est un **`AbilityConstantType`** (`range`), pas un `AbilityVariableType` : le discriminant
est l'ACCESSEUR (`GetNumberConstant`), pas l'ordinal. Gameconfig vivant :
`abilities.FirstAmongTraitors.constants.range = 2`.

## 1. L'EFFET -- `IdunBattle.Entities.Effects.Loki.FirstAmongTraitors_ExtraDmgEffect`

Parent LU dans `classes.tsv` : `IdunBattle.Entities.Effects.BaseEffect`.
`$$.ctor` = `BaseEffect(AbilityOrEffect(...), hasAutomaticActivation = true)`.

### `...FirstAmongTraitors_ExtraDmgEffect$$CreateTargetSelector`

    range = DSLFormulas.ConfigConst( 0x16 = AbilityConstantType.range, config@0x60 )
    sel   = DSLSelectors.SurroundingFriends( unit = Owner@DSLSelectors+0x30, range,
                                             unique = true, unitSelectionType = 3 )
    return  DSLSelectors.UnitsWithTrait( sel, 0x7ea = UnitTrait.Chaos, selectionType = 3 )

⚠ **LE PORTEUR EST EXCLU, et c'est LA difference avec ses voisins de forme.**
`IdunBattleLogic.Entities.DSLSelectors$$SurroundingFriends(unit, range, unique, selType)`
(surcharge a 5 arguments, LUE : le call-site en passe 5) se deplie en

    Friends( unit, Units( SurroundingTiles(unit, 1, range) - Tiles(unit), unique, selType ), selType )

-- la soustraction `- Tiles(unit)` retire les tuiles du porteur. Il n'y a **AUCUN `op_Addition
Owner`** ici, contrairement a `DestroyTheWitch_ExtraDamage` (`SurroundingFriends(Owner,1) + Owner`)
et a `IconOfObstinacy_ExtraDmg` (`Owner + UnitsWithTrait(AdjacentFriends(Owner), ...)`). Abaddon ne
touche donc PAS son propre bonus, alors meme qu'il porte le trait `Chaos` : **une seule patte de
port** (`create_aura_attack_damage_bonus_for_ally`), et surtout PAS de
`create_effect_damage_bonus_for_attack`, qui SUR-COMPTERAIT le porteur.

`0x7ea` = 2026 = `UnitTrait.Chaos` -- le pseudo-trait de GRANDE-ALLIANCE (`idun.Idun.Source.Shared.
GrandAlliance$$GetTrait` : Imperial -> 26, Xenos -> 0x3ee, Chaos -> 0x7ea). Il est ABSENT de
`gameconfig.unit().traits` et present dans le substrat d'ENTITE (`BaseUnitComponent+0x40`), ou le
BC l'a pose : c'est bien ce que `IdunBattle.Entities.UnitExtensions$$HasTrait` interroge, et c'est
la raison pour laquelle un recensement par gameconfig avait conclu a tort « 0 porteur » sur la
face non-owner (cf. `playbook/non_owner.py::FirstAmongTraitorsNonOwnerPlaybook`).

### `...FirstAmongTraitors_ExtraDmgEffect$$CurrentDamageBonus(effect)`

    base     = DSLFormulas.ConfigVar( 0x428, EffectSource(effect), 0x08 = extraDmg   )
    perHit   = DSLFormulas.ConfigVar( 0x428, EffectSource(effect), 0x09 = extraDmg_2 )
    cap      = DSLFormulas.ConfigVar( 0x428, EffectSource(effect), 0x0d = maxDmg     )
    n        = DSLFormulas.TotalAttacksMade( EffectSource(effect) )
    return DSLFormulas.Min( DSLFormulas.Sum(base, DSLFormulas.Multiply(n, perHit)), cap )

⚠ Les QUATRE noeuds lisent `EffectSource(effect)`, c.-a-d. **ABADDON**, jamais le beneficiaire :
la surcharge appelee est `ConfigVar(abilityType, unit, variableType)` (4 arguments, tranchee par
l'ARITE du call-site -- `DSLFormulas` en porte cinq), qui indexe la config de l'ability `0x428` sur
l'`AbilityState` de cette UNITE-la. La magnitude est donc IDENTIQUE pour tous les beneficiaires et
entierement calculable depuis le seul porteur -- meme structure que `IconOfObstinacy_ExtraDmg`.

`n` = `IdunBattle.Entities.Formulas.TotalAttacksMadeFormula$$Calculate` = `ActorStatisticsComponent
+0x20` d'Abaddon. Ce n'est NI `+0x30` (`TotalTurnsWithAttacksMade`, ce que lit
`MartialInspiration_ExtraDamage`) NI `+0x24` (`AmountOfAttacksMadeThisTurn`, remis a 0 chaque tour).
Le champ `+0x20` n'etait pas porte cote COMBAT : #926 l'ajoute
(`runner/components.py::register_attack_made` / `unit_total_attacks_made`), sans quoi le terme
croissant serait fige a 0 en combat alors que la PREDICTION, elle, le lit deja par son capteur.

Gameconfig vivant (`variablesAffectedByRarityBonus = [extraDmg, extraDmg_2, maxDmg]` -- les TROIS
sont scalees par le multiplicateur de rarete du PORTEUR) : `extraDmg[50] = 277`,
`extraDmg_2[50] = 55`, `maxDmg[50] = 992`. Le cap tombe exactement a `n = 13`
(`277 + 55 x 13 = 992`), ce que la constante `buffMaxLevel = 13` corrobore.

### `...FirstAmongTraitors_ExtraDmgEffect$$CreateEffectDamageBonusForAttack`

    return EffectBonus.ForAddition( DSLTriggers.get_OwnerIsCaster,
                                    CurrentDamageBonus( Effect@DSLSelectors+0x38 ) )

UN SEUL noeud de trigger : ni `IsMeleeAttack`, ni `IsRangedAttack`, ni `IsNormalAttack`, ni
`CurrentAbilityIs`, ni `HasTrait(Target, ...)`. Le bonus s'applique donc a **TOUTES** les attaques
du beneficiaire (normales ET abilities, melee ET distance), canal ADDITIF PRE-percage
(`DamageModifiers.Add` -> `additive`), comme `LordOfTheHost_ExtraDamage`.

### `...FirstAmongTraitors_ExtraDmgEffect$$GetRefreshTriggers`

    new RefreshEffectTrigger[2] { 5 = UnitsChanged, 7 = UnitPositionChanged }

-- l'aura est RE-EVALUEE a chaque mouvement et a chaque changement de roster ; le port la
re-derive a la lecture (les agregateurs rejouent le selecteur par candidat), il ne la fige pas.

### `...FirstAmongTraitors_ExtraDmgEffect$$GetLocalizationDataInternal`

    { AbilityParam(0x15) : Calculate(CurrentDamageBonus(Effect@0x38)) }

-- pur affichage, aucune consequence de simulation ; non porte.

================================================================================================
QUALIFICATION DES ENUMS (le meme id nomme autre chose ailleurs)
================================================================================================

    EffectType           1063 FirstAmongTraitors_ExtraDmg != TriggeredAbilityType 1063 ListenUpMaggots
                                                          != ActiveAbilityType     1063 FireAndReposition
    TriggeredAbilityType 1064 FirstAmongTraitors          != EffectType           1064 SpotterReworked_HeavyWeapon
                                                          != ActiveAbilityType     1064 Loki_SwoopingHawk
    UnitTrait            2026 Chaos                       (grande-alliance derivee, cf. §1)
"""
from __future__ import annotations

from collections.abc import Mapping

from ..base import BaseEffect
from ..magnitude import ability_var
from ...ability_constant_type import AbilityConstantType
from ...traits.unit_trait import UnitTrait
from ....services.effect_bonus import EffectBonus

#: Cle gameconfig du passif -- `ability_var` s'en sert pour indexer `variables` par niveau ET pour
#: appliquer le multiplicateur de rarete (les trois variables sont dans
#: `variablesAffectedByRarityBonus`, c'est `ability_var` qui porte ce gate).
FIRST_AMONG_TRAITORS = "FirstAmongTraitors"

EXTRA_DMG_VAR = "extraDmg"        # `AbilityVariableType` 0x08 = 8
EXTRA_DMG_2_VAR = "extraDmg_2"    # `AbilityVariableType` 0x09 = 9
MAX_DMG_VAR = "maxDmg"            # `AbilityVariableType` 0x0d = 13

#: `GetNumberConstant(config, 0x16)` du `CreateTargetSelector` -- la CONSTANTE, pas son ordinal nu.
RANGE_CONSTANT = AbilityConstantType.range        # 0x16 = 22

#: `UnitsWithTrait(SurroundingFriends(Owner, range), 0x7ea, 3)` -- grande-alliance Chaos.
CHAOS_TRAIT = UnitTrait.Chaos                     # 0x7ea = 2026


def first_among_traitors_range() -> "int | None":
    """`DSLFormulas.ConfigConst(0x16 = AbilityConstantType.range, config@0x60)` =
    `FirstAmongTraitors.constants.range` (= 2).

    `None` = constante absente -> `GetNumberConstant` LEVE cote natif ; le port se degrade en
    « aucun beneficiaire » plutot que d'inventer un rayon."""
    v = ability_var(FIRST_AMONG_TRAITORS, RANGE_CONSTANT.name, is_constant=True)
    return None if v is None else int(v)


class FirstAmongTraitorsExtraDmgEffect(BaseEffect):
    """`IdunBattle.Entities.Effects.Loki.FirstAmongTraitors_ExtraDmgEffect` (EffectType 0x427 = 1063).

    AURA cote SOURCE : l'effet-entite vit sur `blackAbaddon` (pose a l'init de l'ability, cf. §0) et
    accorde un bonus de degat ADDITIF PAR COUP a ses allies **Chaos** a `<= range` hexes, **le
    porteur EXCLU** (cf. §1). UNE SEULE patte de port, donc : `create_aura_attack_damage_bonus_for_ally`.

    ⚠ PAS de `create_effect_damage_bonus_for_attack` -- et c'est MESURE au selecteur, pas suppose :
    `SurroundingFriends` retire `Tiles(Owner)` et rien ne re-ajoute `Owner`. Declarer cette patte
    donnerait a Abaddon un bonus que le natif ne lui donne pas."""

    def _current_damage_bonus(self, total_attacks_made: "int | None") -> "int | None":
        """`CurrentDamageBonus(effect)` (§1) :

            Min( Sum(ConfigVar(extraDmg), Multiply(TotalAttacksMade(EffectSource), ConfigVar(extraDmg_2))),
                 ConfigVar(maxDmg) )

        Les trois `ConfigVar` sont indexees sur l'`AbilityState` de l'`EffectSource` = le PORTEUR de
        l'instance, donc sur `self.ability_level` / `self.ability_variables_multiplier`.

        TRI-ETAT sur `total_attacks_made` : `None` = le canal n'a pas publie le compteur du porteur
        -> le terme croissant est OMIS et le resultat est le seul terme LISIBLE (`extraDmg`, borne
        par `maxDmg`). Degradation NOMMEE : il manque, il n'est pas remplace par une valeur devinee.
        Le sens de l'ecart est alors toujours un MANQUE, jamais un sur-compte.

        `ability_level is None` (aucun `AbilityState` capte) -> `None` : « present != applique »,
        meme regime que `LionHelm_ExtraDmg` / `DestroyTheWitch_ExtraDamage`."""
        if self.ability_level is None:                 # ConfigVar sans AbilityState -> pas de magnitude
            return None
        mult = self.ability_variables_multiplier
        base = int(ability_var(FIRST_AMONG_TRAITORS, EXTRA_DMG_VAR, self.ability_level,
                               multiplier_pct=mult) or 0)
        per_hit = int(ability_var(FIRST_AMONG_TRAITORS, EXTRA_DMG_2_VAR, self.ability_level,
                                  multiplier_pct=mult) or 0)
        cap = ability_var(FIRST_AMONG_TRAITORS, MAX_DMG_VAR, self.ability_level,
                          multiplier_pct=mult)
        amt = base + int(total_attacks_made or 0) * per_hit     # Sum(base, Multiply(n, perHit))
        if cap is not None:
            amt = min(amt, int(cap))                            # Min(., cap)
        return amt or None

    def create_aura_attack_damage_bonus_for_ally(self, ctx: Mapping | None = None) -> "EffectBonus | None":
        """PATTE **ALLIES** (la seule) : `UnitsWithTrait(SurroundingFriends(Owner, ConfigConst(range),
        unique, OnlyAliveAndTargetable), Chaos, OnlyAliveAndTargetable)`, RE-EVALUE PAR CANDIDAT
        contre le ctx de l'agregateur (`GetRefreshTriggers` = UnitsChanged | UnitPositionChanged :
        le natif lui-meme re-derive a chaque mouvement).

        `get_OwnerIsCaster` est STRUCTURELLEMENT satisfait sur ce canal : l'agregateur n'interroge
        cette patte que pour l'unite qui porte le coup courant, et `Owner` designe le BENEFICIAIRE
        (le membre du `CreateTargetSelector`), pas la source de l'effet.

        `att_traits` est le substrat d'ENTITE (traits accordes en bataille compris) -- c'est ce
        qu'interroge `UnitExtensions$$HasTrait`, et c'est le SEUL substrat ou le pseudo-trait de
        grande-alliance `Chaos` existe (cf. §1).

        ⚠ **AUCUN gate `is_targetable` ici, et c'est MESURE, pas un oubli.** Le selecteur porte
        `unitSelectionType = 3 = OnlyAliveAndTargetable` sur ses DEUX noeuds, et ce volet est REEL
        sur un AUTRE canal du binaire (`LionHelm`, canal stat-mod : `darkaTerminator` en
        `TeleportStrike_TeleportingIn` ne recoit RIEN). Sur CE canal, la mesure dit l'inverse --
        montage `blackTerminator` (Chaos + `TeleportStrike`) a distance 1 d'Abaddon : le port lui
        accorde le bonus et l'oracle NATIF est en ACCORD sur les 25 tuiles candidates. Ajouter le
        gate serait un ecart RESTRICTIF. Cran : `test_926_first_among_traitors_live.py::
        test_un_ami_NON_CIBLABLE_recoit_quand_meme_le_bonus`.

        ⚠ **ET L'ASYMETRIE N'EST PAS DANS LE SELECTEUR (#926-r1)** : les deux `CreateTargetSelector`
        ont ete decompiles COTE A COTE et ouvrent sur le MEME
        `IdunBattleLogic.Entities.DSLSelectors$$SurroundingFriends(Owner@+0x30, <range>, unique = 1,
        unitSelectionType = 3)` -- celui-ci n'ajoute qu'un `UnitsWithTrait(_, 0x7ea, 3)`. Ce qui
        differe est la FENETRE de re-evaluation : `...FirstAmongTraitors_ExtraDmgEffect$$GetRefreshTriggers`
        RESTREINT a `{ UnitsChanged = 5, UnitPositionChanged = 7 }` (ecrit INLINE, donc lisible ;
        `EffectsChanged = 4` en est ABSENT) la ou les deux `LionHelm_*` ne declarent AUCUNE surcharge
        -- defaut `null`, que `BaseEffect$$ShouldRefreshForTrigger` traite comme << tout trigger >>.
        Sur-ensemble STRICT. Le raisonnement complet, la refutation de la cause << flag pas encore
        visible >>, et ce qui reste ouvert : `entities/effects/aura_selectors.py::is_targetable`."""
        c = ctx or {}
        if c.get("att_id") == c.get("owner_id"):
            return None                                # `- Tiles(Owner)` : le porteur est exclu
        if c.get("owner_team") is None or c.get("owner_team") != c.get("att_team"):
            return None                                # `Friends` = meme equipe que le porteur
        rng = first_among_traitors_range()
        if rng is None:
            return None                                # constante absente -> aucun beneficiaire
        opos, apos = c.get("owner_pos"), c.get("att_pos")
        if not opos or not apos:
            return None
        import hexgeo
        if hexgeo.distance(tuple(opos), tuple(apos)) > int(rng):   # `SurroundingTiles(Owner, range)`
            return None
        if CHAOS_TRAIT.name not in (c.get("att_traits") or ()):    # `UnitsWithTrait(0x7ea)`
            return None
        # `TotalAttacksMade(EffectSource)` -- map PAR PORTEUR publiee par le site d'agregation,
        # `owner_id` etant pose par `aura_attack_damage_bonus_from_allies` dans le ctx par-carrier.
        # Cle absente -> None -> seul `extraDmg` est rendu (cf. `_current_damage_bonus`).
        amt = self._current_damage_bonus(
            (c.get("owner_total_attacks_made") or {}).get(c.get("owner_id")))
        # `EffectBonus.ForAddition(get_OwnerIsCaster, .)` -> canal ADDITIF, cote ATTAQUANT.
        return EffectBonus("Addition", int(amt), True) if amt else None
