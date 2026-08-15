"""`LegendaryCommander_ExtraDamage` (`EffectType` 0x572 = 1394) -- la face DEGAT du passif
`LegendaryCommander` (`TriggeredAbilityType` 0x51e = 1310) de `custoTrajann`. #419-r1-tr9-r4-r1-r2-r1c-r1.

Son JUMEAU sur l'axe COUPS, `LegendaryCommander_ExtraHits` (0x573 = 1395), est porte depuis
#419-r1-tr9-r4-r1-r2-r1 (`entities/effects/loki/hits.py`). Les DEUX effets sont poses d'un bloc a
l'init du porteur -- `IdunBattleLogic.Entities.Abilities.Triggered.Loki.LegendaryCommanderAbility$$CreateBehaviour`
= `AddEffect(0x572, <abilityStateRef>, Owner@<DSLSelectors+0x30>, Owner@+0x30, <turns VIDE>)
   & AddEffect(0x573, <idem>)` -- et `ABILITY_INIT_OWNER_EFFECTS["LegendaryCommander"]` seede bien
les deux. 1394 etait donc VISIBLE dans la liste d'effets et INERTE sur le degat, faute de classe :
`EffectFactory` en faisait un `BaseEffect` NU. Meme vice que #1002-r1 sur `1454`.

i2 `Abilities/LegendaryCommander_CurrentLevelDescription` : << Whenever a friendly unit uses an
Active ability, enemies adjacent to it take +[extraDmg] damage from friendly Characters. If the
affected enemies are also adjacent to Trajann, friendly Characters score [nrOfHits] additional hits
against them with their first attack that is not a normal attack. >>

===================================================================================================
L'ARTEFACT NATIF, LU TERME A TERME (build `t6dpr4k06g`)
===================================================================================================

`IdunBattle.Entities.Effects.Loki.LegendaryCommander_ExtraDamageEffect$$CreateEffectDamageBonusForAttack` ::

    EffectBonus.ForAddition(
        get_OwnerIsTarget
          & AreFriends( Caster@<DSLSelectors+0x48>,
                        EffectSource(<DSLSelectors+0x38>),
                        comparisonType = 0 (ByCurrentTeam),
                        anyEntity = false ),
        ConfigVar( AbilityVariableType 8 = extraDmg, GetAbilityState(this), <config@this+0x60> ) )

CE QUE LE DECOMPILE N'A PAS -- absences VERIFIEES, pas supposees, et chacune aurait ete recopiee
d'un voisin de forme :

  * **AUCUN `HasTrait(Caster, 0x10 = Hero)`** -- l'i2 dit << from friendly **Characters** >>, le
    natif ne teste QUE `AreFriends`. L'i2 SUR-SPECIFIE ; c'est le decompile qui fait foi. Poser un
    gate Hero fermerait le bonus pour tout allie non-Hero que le natif sert ;
  * **AUCUN `IsMeleeAttack` / `IsRangedAttack` / `IsNormalAttack`** -- contraste son jumeau 1395,
    dont le trigger porte `!IsNormalAttack`, et contraste `MoreGitzOverEre_ExtraDamagePct` (1449),
    qui porte `IsMeleeAttack & IsNormalAttack`. Le bonus de 1394 vaut pour TOUT vecteur d'attaque ;
  * **AUCUN `HasRarity`** (contraste 1449 / 1444, dont c'est le gate discriminant) ;
  * **AUCUNE `CreateTargetSelector` propre** : 1394 prend celle de sa base
    `ALegendaryCommander_BaseEffect$$CreateTargetSelector` (TROIS noeuds). C'est `1395` qui SURCHARGE
    (`LegendaryCommander_ExtraHitsEffect$$CreateTargetSelector`, symbole distinct) pour ajouter un
    QUATRIEME noeud `Filter(., IsAdjacent(Owner@+0x30, Subject@+0x68, 3))`. **NE PAS le recopier
    ici** : c'est exactement le << If the affected enemies are ALSO adjacent to Trajann >> de l'i2,
    propre a la face COUPS.

`ALegendaryCommander_BaseEffect$$CreateTargetSelector` -- le TRONC PARTAGE, lu verbatim ::

    sel = Friends( of = Owner@<DSLSelectors+0x30>, entities = AllUnits@<+0x20>, selectionType = 3 )
    sel = Filter( sel, HasUsedActiveAbilityThisTurn(Subject@<+0x68>) )
    sel = AdjacentEnemies( unit = sel, unique = 1, selectionType = 3 )

et `IdunBattleLogic.Entities.DSLSelectors$$AdjacentEnemies(unit, unique, selectionType)` (overload
a QUATRE arguments -- pas celui a `unitTile`) est LITTERALEMENT ::

    Enemies( unit, Units(AdjacentTiles(unit), unique, selectionType) - unit, selectionType )

donc la population visee est : **les ENNEMIS de `sel` qui occupent une tuile adjacente a `sel`**.
`Friends(Owner, AllUnits)` ne SOUSTRAIT PAS le porteur (`UnitExtensions$$IsFriend(u, u)` est VRAI),
donc le propre cast d'active de Trajann arme l'aura -- et comme `sel` est inclus dans les amis du
porteur, << ennemi de `sel` >> et << ennemi du porteur >> coincident.

`ALegendaryCommander_BaseEffect$$CreateActiveCondition` rend le trigger CONSTANT `<DSLTriggers+0x28>`
(aucun noeud lu sur l'etat) : rien a porter, `is_active` reste celui de `BaseEffect`.

===================================================================================================
CANAL DE PORT -- `create_aura_defense_damage_malus_for_ally`, face NATIVE << attacker >>
===================================================================================================

MEME arbitrage que `MoreGitzOverEre_ExtraDamagePct` (1449, #1025-r1),
`OnMyPosition_ExtraDamagePct` (1444, #1024-r2) et `DaughterOfTheAbyss_ExtraDamagePct`
(#437-r1-r1-r1), et pour la MEME raison structurelle :

  * le slot natif est ATTAQUANT (`$$CreateEffectDamageBonusForAttack` -- le natif verse dans
    `attackModifiers`), d'ou `AURA_DEFENSE_MALUS_NATIVE_FACE = "attacker"` ;
  * mais le BENEFICIAIRE du selecteur est la **CIBLE DU COUP** (`get_OwnerIsTarget` : la boucle
    native ecrit `AbilityEntities+0x18 (Owner) <- CHAQUE CIBLE du selecteur`), et le SEUL agregateur
    du port qui balaie les porteurs TIERS pour une cible donnee est la boucle state-wide
    `EffectWithTarget` du builder DEFENSEUR
    (`IdunBattle.Core.Services.DamageCalculations$$CalculateDefenderModifiersForPrediction`).

⚠ Ce n'est donc PAS le canal de son jumeau 1395, qui passe par
`create_aura_hits_bonus_for_attack` (terme de `AttackHitsWithModifiersFormula$$Calculate`, servi par
`build_hits_board`). Un artefact natif, deux axes, deux canaux : les deux faces ne partagent que
l'ability source et le tronc de selecteur.

⚠ `AreFriends(Caster, EffectSource)` est VRAI quand `Caster == EffectSource` : **Trajann qui attaque
lui-meme un ennemi marque TOUCHE le bonus**. L'agregateur DEFENSE n'exclut PAS `att_id == owner_id`
(il n'exclut que `uid == tgt_id`), donc ce chemin est servi sans code special -- et on n'ajoute
surtout pas d'exclusion, qui serait un ecart au natif.

===================================================================================================
SUBSTRAT DU SELECTEUR -- deux cles, toutes deux DEJA NOMMEES ailleurs (aucun nommage neuf)
===================================================================================================

  * `tgt_adjacent_unit_profiles` = `(uid, team, visual_id, rarity, is_hero)` pour
    `AdjacentUnits(<la cible>, unique, 3)` -- foyers `damage_model._adjacent_unit_profiles` /
    `prediction/_shared._adjacent_unit_profiles`, donc l'adjacence **NATIVE** (liste stockee +
    porte d'elevation), jamais un `hexgeo.distance == 1`. Arrive avec #1025-r1 ;
  * `used_active_by_id` = `HasUsedActiveAbilityThisTurn(Subject@+0x68)` = `HasFlag(unit, 2)` --
    MEME store (`UnitFlagsComponent`) et MEME foyer (`components.unit_has_used_active_ability` /
    `Scene.has_used_active_ability`) que la cle homonyme deja posee par `build_hits_board` pour le
    jumeau 1395. Ce residu ne fait que la relayer au ctx du canal AURA-DEFENSE.

L'adjacence native etant SYMETRIQUE (liste stockee ET porte `|dElev| < 2`), << la cible est dans les
voisins d'un ami ayant caste >> et << un ami ayant caste est dans les voisins de la cible >> sont la
MEME question -- c'est l'argument deja mesure pour la branche A de `MoreGitzOverEre`.

TRI-ETAT STRICT sur les deux cles : `None` = NON MESURE -> le gate se FERME (jamais un booleen ni un
ensemble vide inventes). Un tuple VIDE, lui, est une mesure : << aucun voisin >>.

⚠ FAIT MESURE, pour qui relira ce garde : sur CE selecteur, rabattre `None` sur `()` / `{}` serait
**observationnellement EQUIVALENT** -- une boucle vide ferme deja le gate, et `{}.get(uid)` rend
`None`, donc faux. La mutation correspondante NE MORD PAS, et ce n'est pas un trou du test : les deux
ecritures calculent la meme chose. Ce qui change reellement le comportement, et que le test
`test_10_gates_fermants` attrape, c'est le rabattement **PERMISSIF** (`None` -> le gate passe). Le
`return False` explicite est donc de la LISIBILITE et une protection si la boucle change de forme --
pas ce qui produit la degradation restrictive aujourd'hui.

===================================================================================================
MAGNITUDE
===================================================================================================

`ConfigVar(8 = extraDmg)` -- une VARIABLE par niveau de l'ability `LegendaryCommander`
(`gameconfig.abilities.LegendaryCommander.variables.extraDmg` = [11, 13, 15, ... 609 @L50]), et
`extraDmg` EST dans `variablesAffectedByRarityBonus` -> `ability_var` applique le multiplier de
rarete du porteur. `GetAbilityState(this)` sur un `AbilityOrEffect` TRIGGERED resout le niveau du
PASSIF du porteur -> `self.ability_level` (jamais `active_ability_level`).

Canal `EffectBonus` `+0x10` = ADDITION (`ForAddition`), donc un additif PLAT par coup -- contraste
`MoreGitzOverEre`, qui est un `ForPercentIncrease`.

PORTEUR : `custoTrajann` -- un HERO. Confrontation live : le porteur seede ses deux effets a l'init
(mesure #419-r1-tr9-r4-r1-r2-r1c : `decisionView` rend bien les DEUX sur `u81 [custoTrajann]`).
"""
from __future__ import annotations

from collections.abc import Mapping

from ....services.effect_bonus import EffectBonus, for_addition
from ..base import BaseEffect
from ..magnitude import ability_var
# `AdjacentUnits(<la cible>, unique, 3)` enrichi -- foyer de NOMMAGE `extra_damage_aura` (#1025-r1).
# Import du NOM plutot que re-declaration de la chaine : une seconde chaine litterale serait un fork
# silencieux le jour ou la cle bouge. Aucun cycle -- `extra_damage_aura` n'importe pas ce module.
from .extra_damage_aura import CTX_TGT_ADJACENT_UNIT_PROFILES

#: cle gameconfig de l'ability source -- l'`AbilityOrEffect` que le `.ctor` passe a `BaseEffect`.
#: ⚠ `LegendaryCommander_ExtraHitsEffect$$.ctor` est le corps DEDUPLIQUE des DEUX classes (les
#: lambdas `EffectsDatabase.<InitializeEffects>b__14_403` / `b__14_404` l'appellent sur des
#: `Il2CppClass*` DISTINCTS) : le nom du ctor ne dit donc PAS l'identite de classe
#: (`reference_ctor_name_is_not_class_identity`). C'est la config de l'ABILITY `LegendaryCommander`
#: (`TriggeredAbilityType` 0x51e = 1310) que `ConfigVar` indexe, pour les deux effets.
ABILITY_ID = "LegendaryCommander"
#: `AbilityVariableType 8`, resolu par son NOM : l'ordinal 8 est AUSSI un membre valide
#: d'`AbilityConstantType`, ou il nomme autre chose (piege mesure de #270-r1-r1-r3).
VAR_EXTRA_DMG = "extraDmg"
#: `HasUsedActiveAbilityThisTurn(Subject@<DSLSelectors+0x68>)` -- MEME cle, MEME store et MEME foyer
#: que celle que `runner/damage_model.py::build_hits_board` pose deja pour le jumeau 1395.
CTX_USED_ACTIVE_BY_ID = "used_active_by_id"


class LegendaryCommanderExtraDamageEffect(BaseEffect):
    """`IdunBattle.Entities.Effects.Loki.LegendaryCommander_ExtraDamageEffect` (`EffectType`
    0x572 = 1394, nom capte `LegendaryCommander_ExtraDamage`).

    Voir l'en-tete du module pour l'arbre natif terme a terme, le canal et le substrat."""

    # Le slot natif est `$$CreateEffectDamageBonusForAttack` -- le natif verse dans
    # `attackModifiers` -- alors que le port l'evalue par le canal AURA-DEFENSE (le seul qui balaie
    # les porteurs TIERS pour une cible donnee). CONSEQUENCE ARITHMETIQUE REELLE : canal ADDITIF
    # ATTAQUANT, pas defenseur. MEME arbitrage que `MoreGitzOverEre` / `OnMyPosition` /
    # `DaughterOfTheAbyss_ExtraDamagePct` (#437-r1-r1-r1).
    AURA_DEFENSE_MALUS_NATIVE_FACE = "attacker"

    def selector_covers_target(self, ctx: "Mapping | None" = None) -> bool:
        """`ALegendaryCommander_BaseEffect$$CreateTargetSelector` -- la CIBLE DU COUP appartient-elle
        au selecteur ? Les TROIS noeuds du tronc, dans l'ordre du corps natif.

        ⚠ **SANS** le quatrieme noeud `Filter(., IsAdjacent(Owner, Subject, 3))`, qui n'existe que
        sur la surcharge de 1395 : ici, l'ennemi marque n'a PAS besoin d'etre adjacent a Trajann."""
        c = ctx or {}
        # `AdjacentEnemies(sel, ...)` = `Enemies(sel, Units(AdjacentTiles(sel)) - sel, 3)` : la
        # cible est ENNEMIE des amis-du-porteur qui ont caste. `sel` etant inclus dans
        # `Friends(Owner, AllUnits)`, << ennemi de sel >> == << ennemi du porteur >>.
        oteam, tteam = c.get("owner_team"), c.get("tgt_team")
        if oteam is None or tteam is None or oteam == tteam:
            return False
        prof = c.get(CTX_TGT_ADJACENT_UNIT_PROFILES)
        used = c.get(CTX_USED_ACTIVE_BY_ID)
        if prof is None or used is None:            # canal NON MESURE -> gate FERME
            return False
        for p in prof:
            uid, team = p[0], p[1]
            # `Friends( of = Owner@+0x30, entities = AllUnits@+0x20, 3 )` -- aucune soustraction du
            # porteur : Trajann est ami de lui-meme, donc SON propre cast arme l'aura.
            if team is None or team != oteam:
                continue
            # `Filter( ., HasUsedActiveAbilityThisTurn(Subject@+0x68) )`
            if used.get(uid):
                return True
        return False

    def create_aura_defense_damage_malus_for_ally(self, ctx: "Mapping | None" = None) \
            -> "EffectBonus | None":
        """`EffectBonus.ForAddition( get_OwnerIsTarget & AreFriends(Caster@+0x48,
        EffectSource(<+0x38>), 0, false), ConfigVar(8 = extraDmg) )`."""
        c = ctx or {}
        # `AreFriends( Caster@+0x48, EffectSource(<+0x38>), 0 = ByCurrentTeam, false )` -- l'ATTAQUANT
        # est un ami du PORTEUR. `EffectSource` = `EffectComponent.SourceUnit @+0x10` (=
        # `BaseEffect.source`), et l'`AddEffect` de la pose la met a `Owner@+0x30` : source ==
        # porteur == Trajann. On lit la source REELLE quand elle existe, le porteur sinon.
        # ⚠ AUCUN `HasTrait(Hero)` : l'i2 dit << friendly Characters >>, le natif ne le teste PAS.
        att_team, owner_team = c.get("att_team"), c.get("owner_team")
        if att_team is None or owner_team is None or att_team != owner_team:
            return None
        # `get_OwnerIsTarget` -- la cible de l'EFFET est la cible de l'attaque.
        if not self.selector_covers_target(c):
            return None
        amt = ability_var(ABILITY_ID, VAR_EXTRA_DMG, self.ability_level,
                          multiplier_pct=self.ability_variables_multiplier)   # ConfigVar 0x8
        return for_addition(True, int(amt)) if amt else None
