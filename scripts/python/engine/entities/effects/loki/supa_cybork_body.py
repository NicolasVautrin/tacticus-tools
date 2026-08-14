"""`SupaCyborkBody_CritDmgReduction` (`EffectType` 0x5bc = 1468) -- l'etage qui manquait sous #503-r4.

POURQUOI CE MODULE EXISTE, ET COMMENT IL A ETE TROUVE
======================================================
#503-r4 tenait un ecart de magnitude sur la 2e cible du tir differe `1237` : `u81` **8761 ==
8761 bit-exact**, `u83` port **12693** contre natif **10957**. Quatre causes avaient ete
eliminees (block, ordre des cibles, un crit de trop, puis -- par `hit-trace` -- le CARDINAL et
l'ORDRE des coups, natif `{81: 2, 83: 2}` / `[81,81,83,83]`, identiques au port). Restait
« un etage d'APPLICATION », non nomme.

L'etage est ICI, et ce qui l'a nomme est la comparaison des EFFETS PORTES par les deux cibles au
moment du tir : `u83` en porte **trois** que `u81` n'a pas (`1078 SquigHound_IgnoreBattleFatigue`,
`1292 SquigHound_AdditionalHits`, **`1468 SupaCyborkBody_CritDmgReduction`**), et le port ne
portait AUCUN mirror du troisieme. Or c'est exactement le discriminant : le port fait CRITER les
DEUX coups sur `u83` (`crits [true, true]`) et un seul sur `u81` (`[true, false]`) -- une
reduction du DEGAT DE CRIT ne pouvait donc se voir que sur `u83`. C'est la forme de degradation
la plus dangereuse : PERMISSIVE (le port frappe plus fort qu'il ne devrait) et SILENCIEUSE.

L'ARTEFACT, LU EN ENTIER (build `rnca9r7q6c`)
=============================================
`IdunBattle.Entities.Effects.Loki.SupaCyborkBody_CritDmgReductionEffect` porte QUATRE methodes, et
les quatre sont mirrorees ou explicitement declarees non portables :

    $$.ctor                    = BaseEffect..ctor(this, AbilityOrEffect(0x5c3), 1)
    $$CreateCritDamageBonus    = EffectBonus.ForSubtraction( get_OwnerIsTarget,
                                                             GetCritDamageReduction() )
    $$GetCritDamageReduction   = DSLFormulas.Multiply(
                                     ConfigVar(0x97 = critDmgReduction, GetAbilityState(effet),
                                               config@+0x60),
                                     DSLFormulas.EffectLevel(Effect@DSLSelectors+0x38) )
    $$CreateActiveCondition    = DSLTriggers.HasAdjacentEnemies( Owner@DSLSelectors+0x30,
                                                                 DSLSelectors.Tiles(Owner) )
    $$GetCalculateLevel        = DSLFormulas.Count( DSLSelectors.AdjacentEnemies(
                                     Owner@DSLSelectors+0x30, unique: 1, selectionType: 3 ) )

`0x5c3 = 1475` est le littéral du `.ctor`, relu A L'ASSEMBLEUR (`ba c3 05 00 00` = `mov edx,0x5c3`)
et non dans le decompile, ou ghidra perd le registre dans `AbilityOrEffect$$op_Implicit` -- meme
piege et meme parade que `AmuletOfTheVoidwyrm` (`0x5b8`). `TriggeredAbilityType 1475 =
SupaCyborkBody`, dont le gameconfig porte `variables.critDmgReduction` (10 paliers, 390 -> 579) et
AUCUN `variablesAffectedByRarityBonus` -- le multiplicateur de rarete ne mord donc pas, mais on le
passe quand meme, parce que c'est `ability_var` (donc la config) qui decide, jamais ce module.

`AbilityVariableType 0x97 = 151 = critDmgReduction` -- la MEME cle que
`AmuletOfTheVoidwyrm_CritDamageReductionEffect`, dont cet effet est le jumeau de forme : meme
canal `CreateCritDamageBonus`, meme `ForSubtraction`, meme trigger `get_OwnerIsTarget` NU (aucun
`op_BitwiseAnd`). La SEULE difference de structure est le second facteur du `Multiply` : le
compteur y est INLINE (`GetAdjacentFriendlySummonsAndDecoysCount()`), ici c'est
`EffectLevel(effet)` -- une LECTURE du niveau STOCKE.

`EffectLevel`, ET POURQUOI LE PORT LE RECALCULE
===============================================
`DSLFormulas.EffectLevel` lit `EffectComponent+0x68`. Ce champ n'est pas fige : il est REECRIT par
`IdunBattle.Operations.RefreshEffectsOperation$$UpdateLevel`, qui appelle le slot `CalculateLevel`
de l'effet (`IdunBattle.Entities.Effects.BaseEffect$$CalculateLevel`, formule `this+0x88`) avec un
`AbilityEntities` frais, compare au champ et l'ECRIT s'il differe. Le niveau stocke EST donc, a
tout instant ou le refresh a tourne, la valeur de `GetCalculateLevel` -- c'est-a-dire le nombre
d'ennemis adjacents au porteur.

Le port lit `self.level`, qui est le niveau CAPTE (`decisionView.effects[].level`), et retombe sur
le compteur RECALCULE quand le contexte le permet. Les deux sont la meme grandeur ; les garder
tous les deux est ce qui rend l'etage FALSIFIABLE : si le port se met a diverger du natif apres un
deplacement, c'est le compteur qui le dira, pas un scalaire seede.

Meme arbitrage que `AmuletOfTheVoidwyrm` pour la condition d'activite : `active_condition_ported`,
parce que la condition est GEOMETRIQUE et rebascule des qu'une unite bouge -- le flag `IsActive`
capte est un instantane, la condition portee fait foi.

ASCII only.
"""
from __future__ import annotations

from collections.abc import Mapping

from ..base import BaseEffect
from ..magnitude import ability_var
from ....dsl.base import Const
from ...selectors.accessors import Owner
from ...selectors.units import AdjacentEnemies
from .. import ctx_keys as _ctx_keys      # #1042-r5 : foyer UNIQUE des chaines de cle de ctx

#: `TriggeredAbilityType 0x5c3 = 1475` -- le litteral du `.ctor`, relu a l'assembleur. C'est la
#: CONFIG que `GetAbilityState(effet)` resout, pas l'`EffectType` 1468.
_ABILITY_ID = "SupaCyborkBody"
#: `AbilityVariableType 0x97 = 151` (`enums.tsv`, jamais recopie du decompile).
_VAR_KEY = "critDmgReduction"
#: cle du compteur, posee par `runner/components.py::adjacent_enemies_count`
CARRIER_COUNT_KEY = "adjacent_enemies"
#: callable `(owner_id) -> int | None` pose dans le contexte du canal CRIT par `_crit_board`
CTX_COUNT_OF = "adjacent_enemies_of"
#: callable `(owner_id, ability_name) -> (level, multiplier)` -- mirror de `GetAbilityState(effet)`
CTX_ABILITY_STATE_OF = _ctx_keys.CTX_TERTIARY_ABILITY_STATE_OF


def adjacent_enemies_selector():
    """L'ARBRE DSL de `...SupaCyborkBody_CritDmgReductionEffect$$GetCalculateLevel`, noeud par noeud
    (doctrine #149 : l'artefact natif est un SELECTEUR, donc le port est un arbre) :

        Count( AdjacentEnemies(Owner@DSLSelectors+0x30, unique: 1, selectionType: 3) )

    C'est la MEME surcharge d'`AdjacentEnemies` (ancree sur l'UNITE, 4 arguments) que celle de
    `overwhelming_wrath_attack_tree` et de `RighteousRepugnanceAbility$$GetAdditionalTargets` -- elle
    se lit au call-site : le 2e argument est `*(DSLSelectors + 0x30)`, une UNITE (ici `Owner`, et
    non `Caster`), pas un selecteur de TUILES.

    Import PARESSEUX de `Count` : `entities/formulas` est assemble APRES le package
    `entities/effects` (meme garde anti-cycle et meme convention que `amulet_of_the_voidwyrm`)."""
    from ...formulas import Count

    return Count(AdjacentEnemies(Owner(), Const(1)))


class SupaCyborkBodyCritDmgReductionEffect(BaseEffect):
    """`SupaCyborkBody_CritDmgReduction` (0x5bc = 1468) -- owner-effect du passif `SupaCyborkBody` :
    quand son porteur est la CIBLE d'un coup CRITIQUE, le degat de crit de l'attaquant est reduit de
    `critDmgReduction[niveau de l'ability] x <nombre d'ennemis adjacents au porteur>`.

    Deuxieme implementeur porte de l'axe REDUCTION du canal crit-DEGAT (`ForSubtraction`), apres
    `AmuletOfTheVoidwyrmCritDamageReductionEffect`."""

    # La `CreateActiveCondition` est GEOMETRIQUE (`HasAdjacentEnemies`) : elle rebascule des qu'une
    # unite bouge, et le natif la reevalue (`RefreshEffectsOperation$$RefreshEffect` ->
    # `Activate`/`DeactivateEffect`). La condition PORTEE fait donc foi sur le flag `IsActive` capte
    # -- meme arbitrage qu'`AmuletOfTheVoidwyrm`, dont la condition est de la meme famille.
    active_condition_ported = True

    @staticmethod
    def _adjacent_enemies(ctx: "Mapping | None") -> "int | None":
        """`GetCalculateLevel()` EVALUE pour le PORTEUR de CETTE instance.

        Le canal pose `owner_id` par porteur (mirror de l'ecriture `AbilityEntities+0x18` que la
        boucle native fait a chaque iteration), et `_crit_board` pose le callable
        `adjacent_enemies_of` -- paresseux, donc rien n'est calcule tant qu'aucune instance ne le
        demande.

        TRI-ETAT : callable ou `owner_id` ABSENT => `None` = « non mesure », JAMAIS 0. Un 0 invente
        annulerait le produit et ferait passer une reduction reelle pour une absence de reduction."""
        c = ctx or {}
        fn = c.get(CTX_COUNT_OF)
        oid = c.get("owner_id")
        if fn is None or oid is None:
            return None
        n = fn(oid)
        return None if n is None else int(n)

    def _effect_level(self, ctx: "Mapping | None") -> "int | None":
        """`DSLFormulas.EffectLevel(Effect@DSLSelectors+0x38)` = `EffectComponent+0x68`.

        Ce champ est tenu EGAL a `GetCalculateLevel` par
        `IdunBattle.Operations.RefreshEffectsOperation$$UpdateLevel` (il appelle le slot
        `CalculateLevel`, compare, et ECRIT si ca differe). Le port privilegie donc le compteur
        RECALCULE, qui suit l'etat courant du board, et retombe sur le niveau CAPTE quand aucun
        `state` n'est threade (probe/test offline).

        ⚠ Ce niveau n'est PAS le niveau d'ability : `self.level` est le niveau de l'EFFET
        (`decisionView.effects[].level`), `_ability_state` rend l'autre. Les confondre lirait
        `critDmgReduction[1] = 390` au lieu du palier reel."""
        n = self._adjacent_enemies(ctx)
        if n is not None:
            return n
        return None if self.level is None else int(self.level)

    def _ability_state(self, ctx: "Mapping | None") -> tuple:
        """`GetAbilityState(effet)` -> `(level, multiplier)` de l'`AbilityState` bake a la pose.

        L'effet est pose SUR son Owner par le passif `SupaCyborkBody` : source == porteur, donc le
        couple se relit sur le porteur (`owner_id`) par le foyer UNIQUE
        `runner/operations/triggers/base.py::triggered_ability_state` (#357), qui rend l'etat
        TERTIAIRE si l'ability y est montee et l'etat PASSIF sinon.

        Callable absent (contexte sans `state`) -> repli sur les niveaux que l'effet porte deja,
        comme toutes les autres classes d'effet."""
        c = ctx or {}
        fn, oid = c.get(CTX_ABILITY_STATE_OF), c.get("owner_id")
        if fn is not None and oid is not None:
            lvl, mult = fn(oid, _ABILITY_ID)
            if lvl is not None:
                return int(lvl), int(mult if mult is not None else 100)
        lvl = self.ability_level if self.ability_level is not None else self.level
        return lvl, int(self.ability_variables_multiplier or 100)

    def _owner_is_target(self, att_ctx: "Mapping | None" = None) -> bool:
        """`IdunBattleLogic.Entities.DSLTriggers$$get_OwnerIsTarget` = `AreEqual(Owner@+0x30,
        Target@+0x60)`. Identite NON PROUVEE (une des deux cles absente) => noeud FAUX, jamais
        permissif -- meme foyer de raisonnement qu'`AmuletOfTheVoidwyrmCritDamageReductionEffect`."""
        c = att_ctx or {}
        oid, tid = c.get("owner_id"), c.get("tgt_id")
        return oid is not None and tid is not None and oid == tid

    def is_active(self, unit_state: "Mapping | None" = None) -> bool:
        """`CreateActiveCondition` = `HasAdjacentEnemies(Owner, Tiles(Owner))`.

        Le port l'exprime par le MEME compteur que `GetCalculateLevel` (le natif interroge la meme
        geometrie : « au moins un ennemi adjacent au porteur » == « le compte est > 0 »), donc la
        CONDITION et la MAGNITUDE ne peuvent pas diverger.

        Cle ABSENTE = **non mesure** -> on NE FERME PAS (degradation fidele, meme regime
        qu'`AmuletOfTheVoidwyrm`)."""
        n = (unit_state or {}).get(CARRIER_COUNT_KEY)
        return True if n is None else int(n) > 0

    def create_effect_crit_damage_bonus_for_attack(self, att_ctx: "Mapping | None" = None) -> "int | None":
        """MIRROR de `...SupaCyborkBody_CritDmgReductionEffect$$CreateCritDamageBonus` :

            EffectBonus.ForSubtraction( get_OwnerIsTarget,
                                        Multiply( ConfigVar(0x97 = critDmgReduction,
                                                            GetAbilityState(effet), config@+0x60),
                                                  EffectLevel(Effect@+0x38) ) )

        Retour ENTIER NEGATIF : `IdunBattle.Core.Services.DamagePrediction$$
        GetCritDamageBonusFromEffects` accumule litteralement `addition - subtraction`, et son
        consommateur est `Math.Max(0, GetStat(10) + somme)` dans `$$CalculateCriticalDamage`.

        Les etages sont SEPARES et chacun peut se taire independamment (aucun scalaire fitte) :
          1. `get_OwnerIsTarget`  -- le porteur est-il le defenseur ?
          2. `EffectLevel`        -- tri-etat, `None` = non mesure ;
          3. l'`AbilityState`     -- niveau/multiplicateur du passif sur le porteur ;
          4. `ConfigVar`          -- `critDmgReduction[niveau]`, relu du gameconfig ;
          5. `Multiply`           -- le produit, puis le signe de `ForSubtraction`."""
        if not self._owner_is_target(att_ctx):                 # 1
            return None
        n = self._effect_level(att_ctx)                        # 2
        if n is None:
            return None
        lvl, mult = self._ability_state(att_ctx)               # 3
        v = ability_var(_ABILITY_ID, _VAR_KEY, lvl, multiplier_pct=mult)   # 4  ConfigVar(0x97)
        if v is None:
            return None
        amount = int(v) * int(n)                               # 5  Multiply
        return -amount if amount else None                     #    ForSubtraction
