"""Effets `Effects.Loki` de `1203 DaemonicPatrons` (`emperFlawlessBlade` « Hascule ») -- #911.

Les DEUX effets que `...Active.Loki.DaemonicPatronsAbility$$ExecuteBehaviour` pose sur le CASTER,
pour `Sum(TurnsFromRounds(nrOfRounds), Const(1))` tours :

  * `DaemonicPatrons_ExtraDamage`   (0x5b8 = **1464**) -- `+extraDmg x n` au degat INFLIGE ;
  * `DaemonicPatrons_DmgReduction`  (0x5b9 = **1465**) -- `-min(100, dmgReductionPct x n) %` au
    degat RECU.

`n` est la MEME grandeur pour les deux, et c'est le seul etage qui les rend dynamiques :

    `IdunBattle.Entities.Effects.Loki.ADaemonicPatronsEffect$$GetNumAdjacentTauntedEnemies` (la BASE
    commune des deux classes natives) =
        Count( Filter( AdjacentEnemies(Owner@DSLSelectors+0x30, unique: 1, selectionType: 3),
                       HasEffect(ActiveTarget@DSLSelectors+0x68, 0x1b = 27 Taunted_OnlySpecificTargets,
                                 onlyActive: 0, targetType: 6) ) )

⚠ **CE N'EST PAS « les ennemis adjacents »** -- c'est leur sous-ensemble TAUNTE, et le filtre est ce
qui donne son sens a l'ability : le cast taunte UNE cible, donc `n` vaut 1 meme quand six ennemis
touchent le porteur. Un port qui collapserait le `Filter` rendrait `+extraDmg x <adjacents>`, soit
un sur-compte silencieux proportionnel a la melee. C'est exactement ce que le temoin live
discrimine (deux ennemis adjacents, un seul taunte).

⚠ **`onlyActive: 0`** : le 4e argument natif de `DSLTriggers$$HasEffect` est le flag ACTIVE-ONLY
(rectification #100), et il vaut **FAUX** ici -- un `Taunted_OnlySpecificTargets` desactive compte
quand meme. Le port passe donc `active_only=False`, jamais le defaut `True`.

⚠ **`ADaemonicPatronsEffect$$CreateActiveCondition`** = `AmountIsGreaterThanZero(<le meme compte>)`.
CONDITION et MAGNITUDE partagent donc le compteur : elles ne peuvent pas diverger, et `n == 0`
suffirait deja a rendre les deux effets inertes par la magnitude seule. On porte quand meme la
condition -- c'est ce que le natif ecrit, et c'est elle qui decide de la PUBLICATION de l'effet
(`readEffectsByUnit` DROPPE les entrees `IsActive == 0`, cf. #576).

Les DEUX magnitudes lisent leur variable par
`IdunBattleLogic.Entities.DSLFormulas$$ConfigVar(<var>, GetAbilityState(effet), config@+0x60)` --
la surcharge tranchee par les XREFS ENTRANTES du call-site (celle qui construit
`ConfigAmount(query = dsl+0x28, config, abilityState, variableType)`), donc l'`AbilityState` que
l'`AddEffect` a bake (`scale_from_source=True` cote port). Cascade de niveau
`active_ability_level -> ability_level -> level`, la meme que `ModifiedExoarmour_ExtraDmg`.

⚠ **SEUL `extraDmg` est dans `variablesAffectedByRarityBonus`** de 1203 : le multiplicateur de
rarete ne mord PAS sur `dmgReductionPct`. On le passe quand meme aux deux appels -- c'est la CONFIG
qui decide (`ability_var` ne scale que si la cle y est), jamais le site d'appel.

ASCII only.
"""
from __future__ import annotations

from collections.abc import Mapping

from ....services.effect_bonus import EffectBonus, for_addition, for_percent_increase
from ..base import BaseEffect
from ..magnitude import ability_var
from ....dsl.base import Const
from ...ability_variable_type import AbilityVariableType
from ...effect_type import EffectType
from ...selectors.accessors import Owner, Subject
from ...selectors.units import AdjacentEnemies, Filter

#: cle gameconfig de l'ability ACTIVE qui pose les deux effets -- c'est SA config que
#: `GetAbilityState(effet)` resout, jamais celle d'un passif.
_ABILITY_ID = "DaemonicPatrons"
#: `HasEffect(..., 0x1b, ...)` -- l'effet BOND `TauntedEffect`, celui que l'arbre de 1203 vient de
#: poser sur sa cible (et que posent aussi `LashOfTorment` / `CrushingClaws` / `GetEmRuntz` /
#: `OverwhelmingWrath` : le compte n'est PAS reserve au taunt de Hascule).
DP_TAUNTED = int(EffectType.Taunted_OnlySpecificTargets)             # 0x1b = 27
#: `ConfigVar(0x8, ...)` de `...DaemonicPatrons_ExtraDamageEffect$$GetCurrentExtraDamage`.
#: ⚠ QUALIFICATION D'ENUM : `0x8` est un `AbilityVariableType` -- c'est le type DECLARE du 1er
#: parametre de `DSLFormulas$$ConfigVar` (LU dans `frida/methods.tsv`) ; `AbilityConstantType(8)`
#: nomme `unitToSpawn`, une cle sans rapport, et 1203 n'a AUCUNE constante de ce nom.
DP_VAR_EXTRA_DMG = AbilityVariableType.extraDmg                      # 0x8 = 8
#: `ConfigVar(0x46, ...)` de `...DaemonicPatrons_DmgReductionEffect$$GetCurrentDamageReduction`.
#: ⚠ MEME qualification : `AbilityConstantType(70)` nomme `summonId`.
DP_VAR_DMG_REDUCTION_PCT = AbilityVariableType.dmgReductionPct       # 0x46 = 70
#: `Min(Const(100)@DSLFormulas+0x30, ...)` -- le plafond de la reduction, LU dans
#: `IdunBattleLogic.Entities.DSLFormulas$$.ctor` (`+0x18 = 0`, `+0x20 = 1`, `+0x28 = 2`,
#: `+0x30 = 100`, `+0x38 = -1`), pas devine d'un offset opaque ni d'une intuition « c'est un
#: pourcentage donc 100 ».
DP_REDUCTION_CAP = 100
#: cle du compteur dans le `unit_state` du PORTEUR, posee par
#: `runner/components.py::adjacent_taunted_enemies_count` (canal de la CONDITION D'ACTIVITE).
CARRIER_COUNT_KEY = "adjacent_taunted_enemies"
#: MEME cle dans le contexte des canaux de DEGAT (`att_ctx` / `attacker_ctx`), ou elle porte le
#: compte du **PORTEUR DE L'EFFET SUR CE CANAL** : l'ATTAQUANT pour 1464 (gate `get_OwnerIsCaster`),
#: le DEFENSEUR pour 1465 (gate `get_OwnerIsTarget`). Meme convention que `is_turn_of_owner`, qui est
#: deja calcule sur le porteur cote defenseur (`runner/damage_model.py`).
CTX_COUNT_KEY = "adjacent_taunted_enemies"


def adjacent_taunted_enemies_selector():
    """L'ARBRE DSL de `...ADaemonicPatronsEffect$$GetNumAdjacentTauntedEnemies`, noeud par noeud
    (doctrine #149 : l'artefact natif est un SELECTEUR + une FORMULE, donc le port est un arbre) :

        Count( Filter( AdjacentEnemies(Owner@0x30, unique: 1, selectionType: 3),
                       HasEffect(ActiveTarget@0x68, 27, onlyActive: 0, targetType: 6) ) )

    - `AdjacentEnemies` : la surcharge ancree sur l'UNITE (4 arguments), tranchee par les XREFS
      ENTRANTES du call-site -- la MEME que `supa_cybork_body.adjacent_enemies_selector` et que
      `overwhelming_wrath_attack_tree`. Son corps natif est
      `Enemies(unit, Units(AdjacentTiles(unit), unique, selectionType) - unit, selectionType)`.
    - `Filter(entities, trigger)` = `IdunBattleLogic.Entities.DSLSelectors$$Filter`, qui delegue
      litteralement a `FromTrigger(entities, filter, 0)`.
    - `Subject()` = `ActiveTarget@DSLSelectors+0x68`, l'element courant du filtre (meme slot que le
      `subject@0x180` de `case-117` : `DSLSelectors+0x68 == DSLFactory+0x180`).
    - `active_only=False` PORTE le `onlyActive: 0` du 4e argument natif.

    `selectionType: 3` (`OnlyAliveAndTargetable`) part au SELECTEUR et n'est pas encore consomme par
    la couche selecteur du port (residu NOMME `#433-r3-r2`, PARTAGE par tous les call-sites portes) :
    on l'ecrit comme `supa_cybork_body`, c'est-a-dire pas du tout, plutot que d'inventer un
    troisieme argument que le noeud ne lit pas. CONSEQUENCE, bornee : un cadavre encore pose sur sa
    tuile et toujours taunte serait compte par le port et pas par le natif.

    DEUX imports DIFFERES, tous deux **PORTEURS**, classes mecaniquement (charger la cible seule
    dans un process FRAIS et regarder si `engine.runner.components` y atterrit) :
      * `Count` -- `entities/formulas` est assemble APRES le package `entities/effects` ; meme
        mesure et meme convention que `supa_cybork_body` / `amulet_of_the_voidwyrm` ;
      * `HasEffect` -- `entities/triggers` tire `services/movement_query`, qui importe
        `runner/components` au niveau module ; or `runner/components` importe DEJA ce package
        d'effets (pour `adjacent_friendly_summons_and_decoys_selector`). MESURE : hisser cet import
        casse le chargement avec
        `ImportError: cannot import name 'OwnerComponent' from partially initialized module
        engine.runner.components`. Ni (1) deplacer ni (2) alleger l'`__init__` ne s'appliquent : le
        cycle passe par `movement_query`, un service partage par tout le moteur."""
    from ...formulas import Count
    from ...triggers import HasEffect

    return Count(Filter(AdjacentEnemies(Owner(), Const(1)),
                        HasEffect(Subject(), DP_TAUNTED, active_only=False)))


class _ADaemonicPatronsEffect(BaseEffect):
    """`IdunBattle.Entities.Effects.Loki.ADaemonicPatronsEffect` -- la BASE ABSTRAITE des deux
    effets, portee comme telle parce que le natif y met les DEUX membres partages
    (`GetNumAdjacentTauntedEnemies` et `CreateActiveCondition`). Aucune des deux sous-classes ne les
    surcharge : leurs seuls symboles propres sont `.ctor`, `GetCurrent*` et `CreateEffect*`."""

    # La `CreateActiveCondition` est GEOMETRIQUE **et** dependante des effets des voisins : elle
    # rebascule des qu'une unite bouge OU qu'un taunt expire, et le natif la reevalue
    # (`IdunBattle.Operations.RefreshEffectsOperation$$RefreshEffect` -> `Activate`/`DeactivateEffect`).
    # Le flag `EffectComponent.IsActive @+0x5c` capte est un instantane ; la condition PORTEE fait
    # foi -- meme arbitrage que `SupaCyborkBody_CritDmgReduction` et `ModifiedExoarmour_ExtraDmg`,
    # dont les conditions sont de la meme famille.
    active_condition_ported = True

    @staticmethod
    def _num_adjacent_taunted(ctx: "Mapping | None") -> "int | None":
        """`GetNumAdjacentTauntedEnemies()` EVALUE pour le PORTEUR de cette instance.

        Le canal de degat pose la cle pour le porteur DE CE CANAL (l'attaquant pour la face
        ATTAQUE, le defenseur pour la face DEFENSE), exactement comme il pose deja
        `is_turn_of_owner` sur le porteur cote defenseur.

        TRI-ETAT : cle ABSENTE => `None` = « non mesure », JAMAIS 0. Un 0 invente annulerait le
        produit et ferait passer un bonus reel pour une absence de bonus -- et rendrait le port
        VERT sur un montage ou il ne mesure rien."""
        n = (ctx or {}).get(CTX_COUNT_KEY)
        return None if n is None else int(n)

    def _config_level(self) -> "int | None":
        """Le niveau que `ConfigVar(<var>, GetAbilityState(effet), config)` indexe.

        `DaemonicPatrons` est l'ability ACTIVE du poseur, et l'`AddEffect` de son arbre bake
        l'`AbilityStateReference` (`scale_from_source=True`) : la cascade est donc
        `active_ability_level -> ability_level -> level`, la meme que `ModifiedExoarmour_ExtraDmg`."""
        if self.active_ability_level is not None:
            return self.active_ability_level
        return self.ability_level if self.ability_level is not None else self.level

    def is_active(self, unit_state: "Mapping | None" = None) -> bool:
        """`ADaemonicPatronsEffect$$CreateActiveCondition` =
        `AmountIsGreaterThanZero( GetNumAdjacentTauntedEnemies() )`.

        Cle ABSENTE = **non mesure** -> on NE FERME PAS (degradation fidele, meme regime que
        `SupaCyborkBody_CritDmgReduction` / `StructuralAnalyser_Visual`) : la magnitude, qui EST un
        produit par `n`, rend alors l'effet inerte toute seule."""
        n = (unit_state or {}).get(CARRIER_COUNT_KEY)
        return True if n is None else int(n) > 0


class DaemonicPatronsExtraDamageEffect(_ADaemonicPatronsEffect):
    """`DaemonicPatrons_ExtraDamage` (0x5b8 = **1464**) -- pose sur le CASTER par l'arbre de 1203.

    `...DaemonicPatrons_ExtraDamageEffect$$CreateEffectDamageBonusForAttack` (MIRROR du DECOMPILE,
    corps INLINE) :

        trigger = get_OwnerIsCaster
        montant = Multiply( ConfigVar(0x8 = extraDmg, GetAbilityState(effet), config@+0x60),
                            GetNumAdjacentTauntedEnemies() )

    KIND = **ForAddition** (additif PLAT) : la struct construite INLINE ecrit le montant au champ
    `+0x10` de l'`EffectBonus`, EXACTEMENT le slot qu'ecrit
    `IdunBattle.Entities.Effects.EffectBonus$$ForAddition` (`param_1[2] = amount`) -- distinct de
    ForPercentIncrease (`+0x08`), ForSubtraction (`+0x18`) et ForOverride (`+0x28`). Meme lecture
    que `ExemplarOfHateTargetEffect` / `ChronometronExtraDamageEffect`, dont les docstrings
    documentent la table des slots.

    AUCUN gate de nature de coup : ni `IsMeleeAttack`, ni `IsRangedAttack`, ni `IsNormalAttack` --
    le bonus vaut donc aussi pour les attaques d'ABILITY. Le seul conjoint est `get_OwnerIsCaster`,
    et c'est le builder cote ATTAQUANT qui le realise (la boucle n'enumere que les effets de
    l'attaquant). `owner_is_caster=True` transcrit ce trigger."""

    def create_effect_damage_bonus_for_attack(self, is_ranged: bool | None = None,
                                              has_moved: bool | None = None,
                                              target_traits: "frozenset[str] | None" = None,
                                              is_prediction: bool = False,
                                              is_normal_attack: bool | None = True,
                                              target_armor_reduced: bool | None = None,
                                              att_ctx=None) -> EffectBonus | None:
        n = self._num_adjacent_taunted(att_ctx)
        if not n or int(n) <= 0:               # non threade, ou aucun taunte adjacent -> inerte
            return None
        v = ability_var(_ABILITY_ID, DP_VAR_EXTRA_DMG.name, self._config_level(),
                        multiplier_pct=self.ability_variables_multiplier)
        if not v:
            return None
        # `MultiplyAmount$$Calculate` = produit d'ENTIERS : `v` est DEJA l'entier arrondi rendu par
        # `TryGetVariableArrayForLevel`, jamais un flottant a re-arrondir.
        return for_addition(True, int(v) * int(n))


class DaemonicPatronsDmgReductionEffect(_ADaemonicPatronsEffect):
    """`DaemonicPatrons_DmgReduction` (0x5b9 = **1465**) -- pose sur le CASTER par l'arbre de 1203.

    `...DaemonicPatrons_DmgReductionEffect$$CreateEffectDamageMalusForDefense` (MIRROR du DECOMPILE,
    corps INLINE) :

        trigger = get_OwnerIsTarget
        montant = Multiply( Const(-1)@DSLFormulas+0x38, GetCurrentDamageReduction() )
        avec  GetCurrentDamageReduction() =
              Min( Const(100)@DSLFormulas+0x30,
                   Multiply( ConfigVar(0x46 = dmgReductionPct, GetAbilityState(effet), config@+0x60),
                             GetNumAdjacentTauntedEnemies() ) )

    KIND = **ForPercentIncrease A MONTANT NEGATIF**, et ce n'est pas un detail de style : le corps
    inline ecrit au champ `+0x08` de l'`EffectBonus`, le slot de
    `IdunBattle.Entities.Effects.EffectBonus$$ForPercentIncrease`. Le natif n'appelle PAS
    `ForPercentDecrease` (qui est un AUTRE slot) -- il multiplie la magnitude par `Const(-1)`. Le
    mirror EXACT est donc `for_percent_increase(..., -reduction)`, pas `for_percent_decrease`.

    ⚠ **LE CAP EST SUR LE PRODUIT, PAS SUR LE FACTEUR** : `Min(100, pct x n)`. Avec
    `dmgReductionPct = 30`, quatre ennemis adjacents taunted donnent `min(100, 120) = 100`, pas
    `4 x 30`. Capper `pct` puis multiplier rendrait 100 des n >= 4 aussi, mais divergerait des que
    la config passe sous 25 -- on porte le `Min` la ou le natif l'ecrit.

    ⚠ **AUCUN gate de nature de coup** (ni `IsMeleeAttack` ni `IsRangedAttack`) : la reduction vaut
    contre TOUT degat recu. Le seul conjoint est `get_OwnerIsTarget`, realise par le builder cote
    DEFENSEUR ; `owner_is_caster=False` transcrit ce trigger.

    FACE : le natif implemente `CreateEffectDamageMalusForDefense` (slot 0x1a), donc la contribution
    sort par l'accumulateur DEFENSEUR -- le defaut `DEFENSE_MALUS_NATIVE_FACE = "defender"` de
    `BaseEffect` est le mirror exact, aucune surcharge a poser (contraste avec
    `ExemplarOfHate_Target` / `Markerlight`, qui implementent le slot ATTAQUANT)."""

    def create_effect_damage_malus_for_defense(self, is_melee: bool | None = None,
                                               damage_profile: str | None = None,
                                               attacker_ctx: Mapping | None = None) -> EffectBonus | None:
        n = self._num_adjacent_taunted(attacker_ctx)
        if not n or int(n) <= 0:               # non threade, ou aucun taunte adjacent -> inerte
            return None
        pct = ability_var(_ABILITY_ID, DP_VAR_DMG_REDUCTION_PCT.name, self._config_level(),
                          multiplier_pct=self.ability_variables_multiplier)
        if not pct:
            return None
        reduction = min(DP_REDUCTION_CAP, int(pct) * int(n))   # Min(Const(100), pct x n)
        return for_percent_increase(False, -reduction)         # Multiply(Const(-1), .) -> slot +0x08
