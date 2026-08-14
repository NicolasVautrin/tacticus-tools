"""`HunterOfSouls_ExtraDamage` (`EffectType 0x5d7 = 1495`) -- le bonus de degat du passif
`HunterOfSouls` (`TriggeredAbilityType 0x5d9 = 1497`) de `thousSmnDaemonPrince` (Z'Kar).

ARTEFACT NATIF, LU TERME A TERME sur `rnca9r7q6c` --
`IdunBattle.Entities.Effects.Loki.HunterOfSouls_ExtraDamageEffect$$CreateEffectDamageBonusForAttack` :

    EffectBonus.ForAddition(
        get_OwnerIsCaster,
        Multiply( ConfigVar(AbilityVariableType 8 = extraDmg, GetAbilityState(this), <this+0x60>),
                  Count( UnitsWithTrait( AdjacentFriends(Owner@<DSLSelectors+0x30>, unique: 1, 3),
                                         UnitTrait 0x3ea = Psyker, 3 ) ) ) )

Le corps entier tient dans ces trois appels. CE QUE LE DECOMPILE N'A PAS, et qu'un voisin de forme
aurait fait recopier -- toutes ces absences sont VERIFIEES, pas supposees :

  * **aucun etage `NonSteppableOrObjectUnits`**. C'est LA difference avec le jumeau structurel
    `EnmityForTheUnworthy_ExtraDamageEffect` (1400, #948), dont le compteur passe ses deux
    selecteurs par ce filtre. Le recopier ici retirerait des amis Psyker `Steppable`/`Object` que
    le natif COMPTE -- un sous-comptage silencieux ;
  * **aucune `CreateActiveCondition`**. Enmity en porte une (`AmountIsGreaterThanZero(<compteur>)`),
    `HunterOfSouls` non : il n'y a AUCUN symbole `$$CreateActiveCondition` pour cette classe. On ne
    porte donc PAS `active_condition_ported`, et `is_active` reste celui de `BaseEffect` ;
  * **aucun filtre de faction, de rarete, de profil de degat, ni de nature de coup**. Le seul
    noeud de declenchement est `get_OwnerIsCaster`, structurellement satisfait sur ce canal (la
    boucle native n'itere que les effets de l'ATTAQUANT).

Le natif porte deux methodes de plus, toutes deux LUES :

  * `$$GetUnits(dsl)` = le MEME compteur, sans `ConfigVar` ni `ForAddition` -- c'est ce que lit la
    face DECISION (`aiUtilities.Default.UnitEffectsAdjacent.HunterOfSouls_ExtraDamage` = 20) ;
  * `$$GetDamageBonusMultiplier(dsl, bonusMultiplier, abilityState, config)` =
    `Multiply(ConfigVar(8, abilityState, config), bonusMultiplier)`.

L'ABILITY SOURCE est lue DANS LES OCTETS du `.ctor`, pas deduite du nom : le corps commence par
`mov edx, 0x5d9` avant `AbilityOrEffect$$op_Implicit`, et `0x5d9 = 1497 =
TriggeredAbilityType.HunterOfSouls`. C'est cette config que `ConfigVar` indexe. `extraDmg` est
dans son `variablesAffectedByRarityBonus`, donc la valeur scale par le multiplicateur du porteur.

PORTEUR : `thousSmnDaemonPrince` (Z'Kar) -- un **SUMMON**, donc confrontable en amenant son
summoner (doctrine : un summon compte, meme absent de `--list-pool`).
"""
from __future__ import annotations

from collections.abc import Mapping

from ....dsl.base import Const
from ....services.effect_bonus import EffectBonus, for_addition
from ...selectors.accessors import Owner
from ...selectors.units import AdjacentFriends, UnitsWithTrait
from ...traits.unit_trait import UnitTrait
from ...unit_selection_type import UnitSelectionType
from ..base import BaseEffect
from ..magnitude import ability_var

#: cle gameconfig de l'ability -- l'`AbilityOrEffect` que le `.ctor` passe a `BaseEffect`
#: (`mov edx, 0x5d9` = `TriggeredAbilityType.HunterOfSouls = 1497`, LU dans les octets), donc la
#: config que `ConfigVar` indexe.
ABILITY_ID = "HunterOfSouls"
#: `AbilityVariableType 8`, resolu par son NOM (l'ordinal 8 est aussi un membre valide
#: d'`AbilityConstantType`, ou il nomme autre chose).
VAR_EXTRA_DMG = "extraDmg"
#: `UnitSelectionType 3` -- le litteral que le natif propage aux DEUX etages du compteur.
_SEL = int(UnitSelectionType.OnlyAliveAndTargetable)
#: cle du contexte per-coup. MEME nom et MEME semantique sur les DEUX faces (combat et decision) --
#: la poser d'un seul cote creerait un fork silencieux, exactement ce que #1025-r1 a du reparer
#: pour `tgt_rarity`/`team_by_id`.
CTX_ADJACENT_PSYKER_FRIENDS = "adjacent_psyker_friends"


def adjacent_psyker_friends_selector():
    """L'ARBRE de `HunterOfSouls_ExtraDamageEffect$$GetUnits` (doctrine #149 : l'artefact natif est
    un SELECTEUR, donc le port est un arbre) :

        Count( UnitsWithTrait( AdjacentFriends(Owner@<DSLSelectors+0x30>, unique: 1, 3),
                               UnitTrait.Psyker = 0x3ea, 3 ) )

    `reference=Owner()` est passe EXPLICITEMENT a `AdjacentFriends` : la reference d'equipe du
    `Friends` natif EST le centre, et le defaut du port (`ctx.caster`) ne coinciderait que tant que
    le contexte est bati sur le porteur -- meme precaution que `deathwing` et `enmity`.

    ⚠ AUCUN `NonSteppableOrObjectUnits` : c'est ce qui distingue ce compteur de celui d'Enmity.
    Import PARESSEUX de `Count` : `entities/formulas` est assemble APRES le package
    `entities/effects` (meme garde anti-cycle que `enmity_for_the_unworthy`)."""
    from ...formulas import Count

    return Count(UnitsWithTrait(AdjacentFriends(Owner(), Const(1), Owner(), _SEL),
                                int(UnitTrait.Psyker), _SEL))


class HunterOfSoulsExtraDamageEffect(BaseEffect):
    """`IdunBattle.Entities.Effects.Loki.HunterOfSouls_ExtraDamageEffect` (`EffectType 0x5d7 = 1495`,
    nom capte `HunterOfSouls_ExtraDamage`).

    Canal `+0x10` Addition (`for_addition`), applique PAR COUP. Compteur = les amis **Psyker**
    adjacents ; variable `extraDmg`, dans `variablesAffectedByRarityBonus`.

    ⚠ PAS d'`active_condition_ported` : le natif n'a AUCUNE `CreateActiveCondition` pour cette
    classe (contrairement a son jumeau Enmity). L'instance reste donc active meme quand le compteur
    est nul -- c'est la MAGNITUDE qui rend `None`, et l'observable est identique (le natif y
    produirait `ForAddition(gate, 0)`, un additif de zero)."""

    def _count(self, ctx: "Mapping | None") -> "int | None":
        """`Count(<selecteur>)` lu au contexte per-coup. TRI-ETAT : cle absente ou `None` =>
        `None` = << non mesure >>, JAMAIS 0 -- un 0 invente ferait passer un bonus reel pour son
        absence."""
        n = (ctx or {}).get(CTX_ADJACENT_PSYKER_FRIENDS)
        return None if n is None else int(n)

    def _amount(self, ctx: "Mapping | None") -> "int | None":
        """`Multiply( ConfigVar(extraDmg, GetAbilityState(this), config@+0x60), Count(<compteur>) )`.

        `MultiplyAmount$$Calculate` est un produit d'ENTIERS : `ability_var` arrondit AVANT.
        `GetAbilityState(this)` sur un `AbilityOrEffect` TRIGGERED resout le niveau du PASSIF du
        porteur -> `self.ability_level` (jamais `active_ability_level`)."""
        n = self._count(ctx)
        if not n or n <= 0:
            return None
        if self.ability_level is None:                  # ConfigVar sans AbilityState -> inerte
            return None
        per = ability_var(ABILITY_ID, VAR_EXTRA_DMG, self.ability_level,
                          multiplier_pct=self.ability_variables_multiplier)
        if not per:
            return None
        return int(per) * int(n)

    def create_effect_damage_bonus_for_attack(self, is_ranged: bool | None = None,
                                              has_moved: bool | None = None,
                                              target_traits: "frozenset[str] | None" = None,
                                              is_prediction: bool = False,
                                              is_normal_attack: bool | None = True,
                                              target_armor_reduced: bool | None = None,
                                              att_ctx=None) -> EffectBonus | None:
        """`ForAddition( get_OwnerIsCaster, Multiply(...) )` -- UN SEUL noeud trigger, satisfait
        STRUCTURELLEMENT sur ce canal (l'agregateur n'itere que les effets de l'ATTAQUANT).
        Aucun re-gate de nature de coup, de profil ni de rarete : le decompile n'en porte AUCUN."""
        amt = self._amount(att_ctx)
        return for_addition(True, amt) if amt else None
