"""`TerrorsLament` (`TriggeredAbilityType` 0x45e = **1118**) -- passif de kit d'`eldarJainZar`
(<< Jain Zar >>, HERO Aeldari, AU POOL) : les ennemis ADJACENTS a la porteuse infligent
`-dmgReduction` de degat et `-hitsReduction` coups **avec leurs attaques de MELEE**, plancher 1 coup.

i2 : << Adjacent enemy units deal -{[dmgReduction]} Damage and have -{[hitsReduction]} hits with
melee attacks, to a minimum of 1. >>

## UNE ABILITY, DEUX EFFETS, ET LES DEUX VIVENT SUR LA PORTEUSE

`IdunBattleLogic.Entities.Abilities.Triggered.Loki.TerrorsLamentAbility` (:
`IdunBattle.Entities.Abilities.BaseTriggeredAbility`, LU dans `frida/classes.tsv`). Bloc
`methodPointers` du PE (ancre sur `$$CreateBehaviour` ; les deux corps fondus par l'ICF resolus par
leur adresse) :

    TerrorsLamentAbility : [ CreateTrigger = <0xec98b0>, CreateBehaviour = <0x12ba210>,
                             .ctor = <0x2ea440> ]

    $$CreateTrigger   = <DSLTriggers+0x30>
                      = On(0x21 = AbilityInit) & <Yes@+0x70> & get_OwnerIsActor
    $$CreateBehaviour = AddEffect(0x45f, AbilityStateReference, targets = Owner@+0x30, turns = null)
                      + AddEffect(0x460, AbilityStateReference, targets = Owner@+0x30, turns = null)

La SURCHARGE d'`AddEffect` est tranchee par l'ADRESSE de la cible du `call` (`0xe9eca0` =
`(effectType, abilityState, targets, turns: System.Nullable<System.Int32>)`, et NON `0xe9e9b0`, la
surcharge a 5 parametres qui prend un `source` distinct). Les DEUX arguments de pile valent `0`
-> `turns` sans valeur -> **PERMANENT**, et **`targets = Owner`** : les deux effets sont poses sur
JAIN ZAR, pas sur les ennemis. Ce sont leurs TRIGGERS qui designent l'attaquant.

## LES DEUX EFFETS (build `rnca9r7q6c`) -- QUATRE corps chacun, dont trois DEDUPLIQUES

    IdunBattleLogic.Entities.Abilities.Triggered.Loki.TerrorsLament_DamageReductionEffect
        : IdunBattle.Entities.Effects.BaseEffect                      (`classes.tsv`)
        $$.ctor                  = BaseEffect..ctor(this, AbilityOrEffect(<lit>), hasAutomatic: 1)
        $$CreateActiveCondition  = <DSLTriggers+0x40>   <- DEDUPLIQUE, constante VRAIE
        $$CreateTargetSelector   = <DSLSelectors+0x30>  = Owner    <- DEDUPLIQUE (defaut)
        $$CreateEffectDamageMalusForDefense =
            EffectBonus.ForSubtraction(
                IsAdjacent(Caster@+0x48, Owner@+0x30, 3 = OnlyAliveAndTargetable)
                & AreEnemies(Owner@+0x30, Caster@+0x48, 0)
                & IsMeleeAttack,
                ConfigVar(0x12 = dmgReduction, GetAbilityState(effet), config@+0x60) )

    IdunBattleLogic.Entities.Abilities.Triggered.Loki.TerrorsLament_HitReductionEffect
        : IdunBattle.Entities.Effects.BaseEffect                      (`classes.tsv`)
        $$.ctor / $$CreateActiveCondition / $$CreateTargetSelector : les MEMES corps (ICF)
        $$CreateEffectHitsBonusForAttack =
            EffectBonus.ForAdditionWithMinimum(
                IsAdjacent(Caster, Owner, 3) & AreEnemies(Owner, Caster, 0) & IsMeleeAttack
                & NOT HasTrait(Caster@+0x48, 0x19 = UnitTrait.Immune),
                Multiply(<DSLFormulas+0x38>, ConfigConst(0x2c = hitsReduction, config@+0x60)),
                Direct(1) )

⚠ **LE CONJOINT SUPPLEMENTAIRE N'EST QUE SUR LA MOITIE COUPS.** `NOT HasTrait(Caster, Immune)`
n'existe PAS dans le trigger de la moitie DEGAT (relu aux DEUX decompiles : le premier enchaine
trois `op_BitwiseAnd`, le second QUATRE, avec un `op_LogicalNot` entre). Recopier un trigger sur
l'autre ferait porter la reduction de coups a une unite `Immune`, ou l'inverse eteindrait la
reduction de degat contre elle -- deux fautes silencieuses, aucune ne leve.

⚠ `<DSLFormulas+0x38>` = **`Direct(-1)`** : le `.ctor` de `DSLFormulas` y ecrit
`Direct(0xffffffff)` (les slots voisins sont `+0x18 = Direct(0)`, `+0x20 = Direct(1)`,
`+0x28 = Direct(2)`, `+0x30 = Direct(100)`). Le produit vaut donc `-hitsReduction`, exactement la
forme de `LightCover`/`Parry`/`Diminutive`. `hitsReduction` est une **CONSTANTE** (`ConfigConst`,
`constants.hitsReduction = "1"`), pas une variable per-niveau : elle ne scale ni au niveau ni a la
rarete -- d'ou `is_constant=True` et AUCUN `multiplier_pct`.

⚠ `<DSLTriggers+0x40>` : le `.ctor` de `DSLTriggers` y ecrit une instance NUE du meme type qu'en
`+0x70` (le `YesTrigger` deja identifie), et `+0x48` en est le `op_LogicalNot`. Les deux effets sont
donc **TOUJOURS ACTIFS**, donc TOUJOURS presents dans `decisionView.effects` (canal ACTIF-ONLY) :
pas d'`active_condition_ported`.

## LE PORT : DEUX PATTES PAR EFFET, ET LEURS POPULATIONS SONT DISJOINTES

Le trigger porte sur `(Caster, Owner)` -- JAMAIS sur la cible du coup. Or les DEUX boucles natives
qui consomment ces canaux sont BOARD-WIDE et ecrivent `AbilityEntities+0x18 (Owner) <- la cible de
l'effet` (ici : Jain Zar) :

  * `IdunBattle.Core.Services.EffectsQuery$$GetActiveEffectsWithBonuses` -> tous les effets ACTIFS
    de l'etat ayant au moins une cible, sans AUCUN scope ;
  * `IdunBattle.Core.Services.DamageCalculations$$CalculateDefenderModifiersForPrediction`
    (surcharge 4-args) et `IdunBattle.Core.Services.DamagePrediction$$GetAttackHits` iterent
    `effets x cibles` sur cette liste.

=> la reduction s'applique a **toute attaque de melee d'un ennemi adjacent a Jain Zar**, quelle que
soit sa cible. Le port scinde cet univers en DEUX pattes, parce que ses agregateurs le scindent :

    Owner == la CIBLE du coup   -> patte SELF  : `create_effect_damage_malus_for_defense`
                                                 `create_effect_hits_malus_for_defense`
    Owner != la CIBLE du coup   -> patte AURA  : `create_aura_defense_damage_malus_for_ally`
                                                 `create_aura_hits_bonus_for_attack`

Les populations sont DISJOINTES PAR CONSTRUCTION (les agregateurs d'aura excluent la cible, les
agregateurs SELF ne voient QU'elle) : ni trou, ni double-compte. Meme arbitrage explicite que
`DestroyTheWitch_ExtraDamage` et `PsychicStalk_FriendlyChaosExtraDamage`, dont le trigger natif
accorde aussi au porteur.

⚠ Jain Zar ATTAQUANTE : `AreEnemies(Owner, Caster)` avec `Owner == Caster` est FAUX
(`IdunBattle.Entities.UnitExtensions$$IsFriend` n'ecarte pas l'egalite, et `AreEnemies` est son
`op_LogicalNot`) -- aucun canal ATTAQUANT n'est donc implemente ici, et ce n'est pas un oubli.

ASCII only.
"""
from __future__ import annotations

from collections.abc import Mapping

from ..base import BaseEffect
from ..magnitude import ability_var
from ....services.effect_bonus import EffectBonus, for_addition, for_subtraction
from ...traits.unit_trait import UnitTrait
# #943-r7 -- les deux canaux du substrat d'adjacence NATIF, en FORME B (#485-r1-r1).
# `pathfinding.board` n'importe RIEN de `engine`, `engine.battle_query` n'importe que `hexgeo` +
# `.hex_corner`.
from ...pathfinding import board as _board
from .... import battle_query as _bq

#: Nom gameconfig du passif -- la CONFIG que `ConfigVar`/`ConfigConst(config@+0x60)` indexent.
#: (`TriggeredAbilityType 0x45e = 1118 = TerrorsLament`. Les `EffectType` 0x45f/0x460, eux, nomment
#: `MV71SniperDroneSquad` / `SaviorProtocols` dans l'enum des TRIGGERED -- deux abilities REELLES,
#: donc une confusion d'enum ne leverait pas : elle lirait la mauvaise config.)
_ABILITY_ID = "TerrorsLament"
#: `AbilityVariableType 0x12 = 18` (`enums.tsv`), DANS `variablesAffectedByRarityBonus`.
_DMG_VAR_KEY = "dmgReduction"
#: `AbilityConstantType 0x2c = 44` (`enums.tsv`) -- une CONSTANTE (`constants.hitsReduction = "1"`),
#: donc ni indexee par niveau ni scalee par la rarete.
_HITS_CONST_KEY = "hitsReduction"
#: `<DSLFormulas+0x38>` = `Direct(0xffffffff)` = `Direct(-1)`, le facteur gauche du `Multiply`.
_MINUS_ONE = -1
#: `IdunBattleLogic.Entities.DSLTriggers$$HasTrait(Caster@+0x48, 0x19)` -- le SEUL conjoint que la
#: moitie COUPS ajoute, en NEGATION.
_IMMUNE = int(UnitTrait.Immune)


def _adjacent_enemy_melee(owner_pos, owner_team, att_pos, att_team,
                          is_melee: "bool | None", board=None) -> bool:
    """Les TROIS conjoints PARTAGES par les deux effets, mirror 1:1 :

        IsAdjacent(Caster@+0x48, Owner@+0x30, 3 = OnlyAliveAndTargetable)
        & AreEnemies(Owner@+0x30, Caster@+0x48, 0)
        & IsMeleeAttack

    C'est une CONJONCTION : une entree non mesuree la ferme (degradation RESTRICTIVE), jamais un
    booleen devine -- le regime permissif inverse ferait porter la reduction a des attaques que le
    natif n'y soumet pas.

    ⚠ `IsAdjacent` N'EST PAS un ring-1 HEX, et la ligne qui le disait ici est REFUTEE par le
    decompile (#943-r4, 2026-08-12). `IdunBattle.Entities.Triggers.IsAdjacentAbilityTrigger$$ShouldTrigger`
    appelle, pour chaque paire (selecteur1 x selecteur2), le slot `0x60` d'`IBattleQuery` = slot 96
    = `AreEntitiesAdjacent` -> `MovementUtil$$AreTilesAdjacent` -> `ConnectivityComponent$$IsNeighbour` :
    le substrat est la liste d'adjacence STOCKEE, pas la couronne hex, qui la SUR-ATTEINT (mesure
    live : 22 aretes sur `MC2_60`, 8 sur `C4_69`, 0 dans l'autre sens). L'ecart est PERMISSIF, donc
    a contre-sens de la conjonction RESTRICTIVE ci-dessus.

    ⚠ **CABLE le 2026-08-15 (#943-r7)**, et le blocage ecrit ici (<< ce ctx d'aura ne publie aucun
    board >>) etait plus LARGE que le fait : sur les QUATRE call-sites de ce helper, deux passent le
    board de coups (`build_hits_board` / son pendant PREDICTION) et deux le ctx defenseur -- les
    quatre le publient depuis le meme commit, sur les DEUX faces, donc aucune ne peut diverger.
    L'ORDRE des arguments est LU, pas devine : `IsAdjacentAbilityTrigger$$.ctor` range `selector1`
    en `+0x20` et `selector2` en `+0x28`, et `ShouldTrigger` appelle
    `AreEntitiesAdjacent(<element de +0x20>, <element de +0x28>)` -- donc `IsAdjacent(Caster, Owner)`
    ENUMERE depuis la tuile du CASTER : `are_entities_adjacent(att_pos, owner_pos)`, pas l'inverse.
    `AreTilesAdjacent` porte AUSSI le court-circuit d'identite `t1 == t2` (#433-r1), que le foyer
    rend.

    Ce qui RESTE vrai de la ligne d'origine : l'approximation MONO-TUILE (une unite multi-tuile est
    reduite a sa main tile), commune a `BigTargetAdjacentEffect` et `Camouflage`.
    `AreEnemies` = `op_LogicalNot(AreFriendsAbilityTrigger)`, donc equipes DIFFERENTES.
    `IsMeleeAttack` suit la convention tri-etat #106 : `None` = nature non declaree -> le gate se
    ferme (meme lecture que `ParryEffect`).
    `board` absent -> `(None, None)` -> repli geometrique NOMME du foyer, le comportement d'avant."""
    if is_melee is not True:
        return False
    if owner_team is None or att_team is None or owner_team == att_team:
        return False
    if not owner_pos or not att_pos:
        return False
    elev_by_pos, neigh_by_pos = _board.adjacency_channels(board)
    return _bq.are_entities_adjacent(tuple(att_pos), tuple(owner_pos), elev_by_pos, neigh_by_pos)


def _caster_is_immune(att_traits) -> bool:
    """`HasTrait(Caster@+0x48, 0x19 = UnitTrait.Immune)` -- le conjoint (en NEGATION) propre a la
    moitie COUPS. Traits NON mesures (`None`) => le noeud rend FAUX, donc la negation rend VRAI :
    c'est la lecture du natif quand l'attaquant ne porte pas le trait, et la seule qui ne mente pas
    sur un board ou personne ne le porte."""
    return _IMMUNE in {int(t) for t in (att_traits or []) if isinstance(t, int)} \
        or UnitTrait.Immune.name in set(att_traits or ())


class TerrorsLamentDamageReductionEffect(BaseEffect):
    """`TerrorsLament_DamageReduction` (`EffectType` 0x45f = 1119) -- owner-effect PERMANENT de
    `TerrorsLament` : `-dmgReduction` PLAT sur le degat de toute attaque de MELEE portee par un
    ennemi ADJACENT a la porteuse. Cf. l'en-tete du module pour l'arbre natif.

    `EffectBonus.ForSubtraction` (adresse `0x1048090`, et NON `$$ForAddition` `0x1047dc0`) : le
    montant est une REDUCTION PLATE, versee dans `flat_reductions` cote port -- exactement le canal
    de `Nightshroud_DmgReduction`, dont le natif est le meme `ForSubtraction(ConfigVar(0x12))`."""

    def _amount(self) -> "int | None":
        """`ConfigVar(0x12 = dmgReduction, GetAbilityState(effet), config@+0x60)`.

        `AddEffect(..., targets = Owner)` pose l'effet sur la porteuse, et l'`AbilityState` bake est
        celui de SON passif -> `ability_level` / `ability_variables_multiplier` de l'instance, poses
        par le seed comme par la capture `decisionView.effects`. `dmgReduction` EST dans
        `variablesAffectedByRarityBonus` -> le multiplicateur mord."""
        lvl = self.ability_level if self.ability_level is not None else self.level
        v = ability_var(_ABILITY_ID, _DMG_VAR_KEY, lvl,
                        multiplier_pct=int(self.ability_variables_multiplier or 100))
        return int(v) if v else None

    def create_effect_damage_malus_for_defense(self, is_melee: "bool | None" = None,
                                               damage_profile: "str | None" = None,
                                               attacker_ctx: "Mapping | None" = None) -> "EffectBonus | None":
        """PATTE SELF (`Owner == la cible du coup`) -- `IdunBattleLogic.Entities.Abilities.Triggered.
        Loki.TerrorsLament_DamageReductionEffect$$CreateEffectDamageMalusForDefense`.

        Les cles lues sont des NOEUDS natifs, pas des commodites : `owner_team` (deja pose pour
        `DeathwingEffect`) est le membre GAUCHE d'`AreEnemies(Owner, Caster)`, `team` en est le
        membre DROIT, `att_pos`/`owner_pos` sont les deux arguments d'`IsAdjacent`. Une cle absente
        FERME la conjonction."""
        c = attacker_ctx or {}
        if not _adjacent_enemy_melee(c.get("owner_pos"), c.get("owner_team"),
                                     c.get("att_pos"), c.get("team"), is_melee,
                                     c.get("board")):
            return None
        v = self._amount()
        return for_subtraction(False, v) if v else None

    def create_aura_defense_damage_malus_for_ally(self, ctx: "Mapping | None" = None) -> "EffectBonus | None":
        """PATTE AURA (`Owner != la cible du coup`) -- MEME arbre natif, MEME slot 0x1a, servi par
        l'autre moitie de la boucle `effets x cibles` de
        `IdunBattle.Core.Services.DamageCalculations$$CalculateDefenderModifiersForPrediction`.

        `owner_pos`/`owner_team` sont poses PAR PORTEUR par l'agregateur (mirror de l'ecriture
        `AbilityEntities+0x18`) ; `att_pos`/`att_team`/`is_melee` decrivent le coup."""
        c = ctx or {}
        if not _adjacent_enemy_melee(c.get("owner_pos"), c.get("owner_team"),
                                     c.get("att_pos"), c.get("att_team"), c.get("is_melee"),
                                     c.get("board")):
            return None
        v = self._amount()
        return for_subtraction(False, v) if v else None


class TerrorsLamentHitReductionEffect(BaseEffect):
    """`TerrorsLament_HitReduction` (`EffectType` 0x460 = 1120) -- owner-effect PERMANENT de
    `TerrorsLament` : `-hitsReduction` coups (plancher 1) sur toute attaque de MELEE portee par un
    ennemi ADJACENT a la porteuse **et non `Immune`**. Cf. l'en-tete du module.

    `EffectBonus.ForAdditionWithMinimum(trigger, Multiply(Direct(-1), ConfigConst(0x2c)), Direct(1))`
    -- le plancher `min = Direct(1)` est applique CHEZ LE CONSOMMATEUR (`max(1, ...)` de
    `attack_hits_with_modifiers`), comme pour `LightCover`/`Parry`/`Camouflage`/`Diminutive` : rien
    a clamper ici."""

    def _amount(self) -> "int | None":
        """`Multiply(<DSLFormulas+0x38> = Direct(-1), ConfigConst(0x2c = hitsReduction))`.

        `ConfigConst` (et non `ConfigVar`) : la valeur vit dans `constants`, donc AUCUNE indexation
        par niveau et AUCUN scaling de rarete -- `is_constant=True`, pas de `multiplier_pct`."""
        v = ability_var(_ABILITY_ID, _HITS_CONST_KEY, is_constant=True)
        return _MINUS_ONE * int(v) if v else None

    def create_effect_hits_malus_for_defense(self, is_melee: "bool | None" = None,
                                             damage_profile: "str | None" = None,
                                             defender_on_cover: "bool | None" = None,
                                             dist: "int | None" = None,
                                             is_normal_attack: bool = True,
                                             att_ctx: "Mapping | None" = None) -> "EffectBonus | None":
        """PATTE SELF (`Owner == la cible du coup`) -- `IdunBattleLogic.Entities.Abilities.Triggered.
        Loki.TerrorsLament_HitReductionEffect$$CreateEffectHitsBonusForAttack`.

        PAS de gate `IsNormalAttack` : le trigger natif n'en porte pas -- la reduction s'applique
        aussi aux attaques d'ABILITY de la famille ATTACK.

        `att_ctx` = le `board` de `IdunBattle.Entities.Formulas.AttackHitsWithModifiersFormula`,
        THREADE jusqu'ici parce que ce trigger-ci ne porte NI sur la cible NI sur un selecteur : il
        lit l'ATTAQUANT (`att_pos`, `team_by_id[att_id]`, `att_traits`) et le PORTEUR
        (`t_pos`/`tgt_team`, qui SONT ceux du porteur sur cette patte, puisque `Owner == Target`)."""
        c = att_ctx or {}
        att_id = c.get("att_id")
        att_team = (c.get("team_by_id") or {}).get(att_id)
        if not _adjacent_enemy_melee(c.get("t_pos"), c.get("tgt_team"),
                                     c.get("attack_pos"), att_team, is_melee,
                                     c.get("board")):
            return None
        if _caster_is_immune(c.get("att_traits")):          # NOT HasTrait(Caster, Immune)
            return None
        v = self._amount()
        return for_addition(True, v) if v else None

    def create_aura_hits_bonus_for_attack(self, ctx: "Mapping | None" = None) -> "EffectBonus | None":
        """PATTE AURA (`Owner != la cible du coup`) -- MEME arbre natif, MEME slot, servi par l'autre
        moitie de la boucle `effets x cibles` de
        `IdunBattle.Core.Services.DamagePrediction$$GetAttackHits`.

        Le canal s'appelle `..._bonus_for_attack` parce qu'il MODIFIE LE NOMBRE DE COUPS DE
        L'ATTAQUANT ; la contribution, elle, est NEGATIVE (`Multiply(Direct(-1), ...)`). Le tri natif
        se fait au SIGNE de chaque bonus, pas au canal qui le produit -- c'est pourquoi
        `block_hits_reduction` (l'interrupteur `BaseEffect$$BlockHitsReduction`) l'eteint comme il
        eteint `Parry` : `_hits_contribution` s'en charge chez l'agregateur, pas ici."""
        c = ctx or {}
        if not _adjacent_enemy_melee(c.get("owner_pos"), c.get("owner_team"),
                                     c.get("att_pos"), c.get("att_team"), c.get("is_melee"),
                                     c.get("board")):
            return None
        if _caster_is_immune(c.get("att_traits")):          # NOT HasTrait(Caster, Immune)
            return None
        v = self._amount()
        return for_addition(True, v) if v else None
