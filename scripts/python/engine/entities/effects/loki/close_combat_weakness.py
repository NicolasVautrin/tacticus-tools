"""`CloseCombatWeakness` -- le trait T'AU (`UnitTrait.CloseCombatWeakness` 1035, **16 porteurs**, tous
`units.npc`) et les DEUX effets qu'il derive. #1015-r1.

CHAINE trait -> ability -> effet, LUE de bout en bout (aucun maillon deduit) :

    `units.npc.<u>.traits[] = "CloseCombatWeakness"`                       (gameconfig, 16 unites)
      -> `idun.Idun.Source.Shared.Battle.StaticBattleRules.StaticBattleRules.Trait$$.cctor`
         dict `GetTriggeredAbility` (+0x0) : cle `0x40b` (= UnitTrait 1035) -> valeur `0x46a`
      -> `IdunBattle.Entities.Factories.UnitFactory$$AddDerivedAbilities` (et son jumeau
         `IdunBattle.Operations.AddTraitOperation$$AddDerivedAbilities`) monte l'ability
         `TriggeredAbilityType.CloseCombatWeakness` (1130)
      -> `IdunBattleLogic.Entities.Abilities.Active.Loki.CloseCombatWeakness_AddEffectAbility$$.ctor`
         = `AOwnerEffectSpecificTriggeredAbility(0x46a)` ; son `$$GetEffectType` a pour corps ENTIER
         `return 0x46a` -> `EffectType.CloseCombatWeakness_ReduceDmg` (1130)
      -> `IdunBattle.Entities.Abilities.AOwnerEffectSpecificTriggeredAbility$$CreateTrigger`
         = `OnOwnerSpecificAbilityInit(0x46a)` -> `AddEffect(owner, 1130)` a l'init du porteur.

    MEME patron que `Terrifying` (#73) et `Diminutive` (#75) -- cf.
    `factory.TRAIT_DERIVED_ABILITIES` / `factory.ABILITY_INIT_OWNER_EFFECTS`.

L'EFFET `IdunBattle.Entities.Effects.Loki.CloseCombatWeakness_ReduceDmg_Effect`, noeud par noeud :

    $$NearbyEnemiesCondition =
        op_BitwiseAnd(
          op_LogicalNot( HasEffect(Owner@DSLSelectors+0x30, 0x478, onlyActive: true, targetType: 6) ),
          op_BitwiseOr(
            HasAdjacentEnemies(unit = Caster@+0x48, unitTile = CasterTile@+0x50,
                               includeObjects: false, includeSteppables: false),
            HasEffect(Owner@+0x30, 0x469, onlyActive: true, targetType: 6) ) )

      `0x478` = 1144 `EffectType.SuppressCloseCombatWeakness` (pose par `EarlyWarningOverride`,
      cf. `runner/abilities/tau.py`) ; `0x469` = 1129
      `EffectType.CloseCombatWeakness_StartedTurnAdjacentToEnemy`.

    $$CreateActiveCondition = `return NearbyEnemiesCondition()` (corps ENTIER, un seul appel).

    $$CreateEffectDamageBonusForAttack = **`EffectBonus.ForPercentIncrease`** (
        trigger = get_OwnerIsActor & NearbyEnemiesCondition & op_LogicalNot(CurrentAbilityIs(<self>)),
        pct     = If( IsMeleeAttack,
                      ConfigConst(0x4c = dmgPctReduction),
                      If( HasEffect(Caster@+0x48, 0x487, onlyActive: false, targetType: 6),
                          <DSLFormulas+0x18> = Direct(0),
                          ConfigConst(0x53 = dmgPctReduction_2) ) ) )

      `0x487` = 1159 `EffectType.SuppressRangeCloseCombatWeakness`.
      ⚠ La fabrique est **`ForPercentIncrease`, PAS `ForPercentDecrease`**, et ce n'est pas une
      lecture de nom : le corps INLINE ecrit `ret+0x00 = trigger`, `ret+0x08 = pct` puis ZEROTE
      `+0x10/+0x18/+0x20/+0x28` et le dword `+0x30` -- l'empreinte exacte de
      `IdunBattle.Entities.Effects.EffectBonus$$ForPercentIncrease`.
      `ForPercentDecrease`, lui, alloue un `Direct(-1)` et un `Multiply` (classes
      `DirectAmount`/`MultiplyAmount`) : ni l'un ni l'autre n'apparait dans le bloc d'init de classes
      de ce corps. Les DEUX constantes de config sont **negatives** (-50 / -25), donc le signe est
      DEJA dans la donnee -- un `ForPercentDecrease` l'aurait inverse.

    $$CreateTargetTrigger =
        op_BitwiseAnd( On(0x12 = EventTriggerType.TurnStart_EffectActivation, ownerNeedsToBeAlive: true),
                       HasAdjacentEnemies(Owner@+0x30, Tiles(Owner@+0x30), false, false) )
    $$CreateTargetTriggerBehaviour =
        AddEffect(0x469, abilityState = Direct(GetAbilityStateReference(this)),
                  source = Owner@+0x30, targets = Owner@+0x30, turns = <DSLFormulas+0x20> = Direct(1))

      -> au DEBUT de son tour, un porteur adjacent a un ennemi se pose le marqueur 1129 pour 1 tour ;
      la condition ci-dessus le relit, ce qui fait tenir le malus meme s'il s'ELOIGNE ensuite.
      C'est litteralement l'i2 : « Whenever this unit is adjacent - or started the turn adjacent - to
      enemy units, it deals {[dmgPctReduction]}% Damage with melee attacks and
      {[dmgPctReduction_2]}% Damage with ranged attacks. »

    $$GetRefreshTriggers = un `EventTriggerType[3]` initialise par `RuntimeHelpers.InitializeArray`
      -- **NON LU** (le contenu vit dans un blob de donnees statiques). Sans consequence ici : le port
      re-evalue la condition A LA LECTURE (`active_condition_ported`), il ne depend pas du cycle
      d'activation/desactivation natif.

`HasAdjacentEnemies` (`IdunBattleLogic.Entities.DSLTriggers$$HasAdjacentEnemies`), noeud par noeud :

    AmountIsEqualOrGreater(
        UnitsWithoutTrait(                                   # !includeSteppables
            UnitsWithoutTrait(                               # !includeObjects
                Enemies(of = unit, entities = AdjacentUnits(unitTile, unique: true, 3), 3),
                UnitTrait.Object = 0xd, 3),
            UnitTrait.Steppable = 0x1b, 3),
        Direct(1) )

⚠ Le comparateur est **INCLUSIF** (`minAmount <= amount`, donc **>= 1** ennemi adjacent), et c'est
MESURE, pas lu au nom : le `.ctor` visible au decompile est un corps TRIVIAL dedupplique par IL2CPP
(#293). `python probe_293_aura_predicate_comparator.py --inventory` classe
`IdunBattleLogic.Entities.DSLTriggers$$HasAdjacentEnemies` dans la famille **INCLUSIF**
(`AmountIsEqualOrGreaterAbilityTrigger`, encodage `setge`) -- prendre le nom du ctor aurait donne
`> 1`, c'est-a-dire « au moins DEUX ennemis adjacents », et le malus n'aurait jamais tire au contact
d'un seul ennemi.

MAGNITUDES -- `ConfigConst(<key>, <config de l'ability de trait>)`. La config d'une ability de TRAIT
vit dans `BC.Abilities.Traits["CloseCombatWeakness"].Constants`, que le SERVEUR derive des
`globalValues.traitVariables` du gameconfig en retirant le prefixe du nom de trait (mesure sur
`MartialKatah` : gameconfig `martialKatahDmgReductionPct`=20 / `martialKatahExtraDmgPct`=100 <->
BC `dmgReductionPct`/`extraDmgPct`). Cote port on lit donc la source AMONT, `trait_var(...)`, exactement
comme `MartialKatahDmgReductionEffect` le fait pour son `ConfigConst(0x72)` :

    `closeCombatWeaknessMeleeDmgPctReduction` = **-50**   <-> `dmgPctReduction`   (0x4c, branche melee)
    `closeCombatWeaknessRangeDmgPctReduction` = **-25**   <-> `dmgPctReduction_2` (0x53, branche autre)

L'appariement des DEUX constantes est CORROBORE par l'i2, qui cite litteralement les noms de membres
`AbilityConstantType` (`{[dmgPctReduction]}` pour la melee, `{[dmgPctReduction_2]}` pour le tir).

ASCII only (cp1252).
"""
from __future__ import annotations

from collections.abc import Mapping

from ....dsl.base import Const
from ....services.effect_bonus import EffectBonus, for_percent_increase
from ...effect_type import EffectType
from ...selectors import AdjacentUnits, CasterTile, Caster, Enemies, Owner, Tiles, UnitsWithoutTrait
from ...traits.unit_trait import UnitTrait
from ...unit_selection_type import UnitSelectionType
from ..base import BaseEffect, is_melee_attack, is_ranged_attack
from ..magnitude import trait_var

#: le NOM du trait dans `units.<u>.traits[]` et dans `globalValues.traitVariables`.
TRAIT_ID = "CloseCombatWeakness"
#: `ConfigConst(0x4c = dmgPctReduction)` / `ConfigConst(0x53 = dmgPctReduction_2)`, cotes gameconfig.
VAR_MELEE_PCT = "closeCombatWeaknessMeleeDmgPctReduction"
VAR_RANGE_PCT = "closeCombatWeaknessRangeDmgPctReduction"
#: `UnitSelectionType 3`, le litteral que `HasAdjacentEnemies` propage a TOUS ses etages.
_SEL = int(UnitSelectionType.OnlyAliveAndTargetable)

#: cle du contexte per-coup qui porte `HasAdjacentEnemies(Caster@+0x48, CasterTile@+0x50, false,
#: false)`. MEME nom et MEME semantique cote PREDICTION (`playbook/scene.py`) et cote COMBAT
#: (`runner/damage_model.py`) -- un seul noeud natif, deux substrats.
CTX_ADJACENT_ENEMIES = "close_combat_weakness_adjacent_enemies"


def has_adjacent_enemies_selector(unit=None, unit_tile=None):
    """L'ARBRE de `IdunBattleLogic.Entities.DSLTriggers$$HasAdjacentEnemies(unit, unitTile,
    includeObjects: false, includeSteppables: false)` -- SANS son etage terminal
    `AmountIsEqualOrGreater(..., Direct(1))`, que l'appelant applique en comparant `Count(...) >= 1`
    (doctrine #149 : l'artefact natif est un SELECTEUR, donc le port est un arbre).

    `unit` = le referent d'EQUIPE (`Enemies(of = unit, ...)`), `unit_tile` = le CENTRE geometrique
    (`AdjacentUnits(unitTile, ...)`). Les deux sont passes EXPLICITEMENT parce que le natif les
    dissocie : `NearbyEnemiesCondition` passe `Caster@+0x48` / `CasterTile@+0x50`, tandis que
    `CreateTargetTrigger` passe `Owner@+0x30` / `Tiles(Owner@+0x30)`.

    ⚠ Les deux `UnitsWithoutTrait` sont CHAINES (le natif re-affecte `pvVar2` a chaque etage), a la
    difference de `NonSteppableOrObjectUnits` qui est une INTERSECTION -- ne pas substituer l'un a
    l'autre. Sur ce noeud-ci les deux formes coincident, mais c'est le decompile qui le dit."""
    unit = unit if unit is not None else Caster()
    unit_tile = unit_tile if unit_tile is not None else CasterTile()
    return UnitsWithoutTrait(
        UnitsWithoutTrait(
            # ⚠ `Enemies(inner, reference, selection_type)` cote port : `inner` est l'ENSEMBLE a
            # filtrer, `reference` le referent d'EQUIPE. Le natif, lui, ecrit
            # `DSLSelectors$$Enemies(this, of, entities, selectionType)` -- l'ordre est INVERSE.
            # Les intervertir passe SILENCIEUSEMENT (les deux arguments sont des selecteurs) et
            # rend le CASTER filtre par son propre voisinage : mesure #1015-r1, l'etage
            # geometrique disparaissait et le compteur COMBAT rendait n'importe quoi.
            Enemies(AdjacentUnits(unit_tile, Const(1), selection_type=_SEL), unit, _SEL),
            int(UnitTrait.Object), selection_type=_SEL),
        int(UnitTrait.Steppable), selection_type=_SEL)


def target_trigger_adjacent_enemies_selector():
    """La face `CreateTargetTrigger` du MEME noeud : `HasAdjacentEnemies(Owner@+0x30,
    Tiles(Owner@+0x30), false, false)` -- referent d'equipe ET centre geometrique sont le PORTEUR."""
    return has_adjacent_enemies_selector(Owner(), Tiles(Owner()))


def _owner_has_effect(att_ctx: "Mapping | None", effect: EffectType) -> "bool | None":
    """`HasEffect(<selecteur>, <EffectType>, onlyActive, targetType: 6)` restreint au cas ou le
    selecteur designe l'ATTAQUANT -- ce qui est vrai des DEUX `HasEffect` de
    `NearbyEnemiesCondition` (`Owner@+0x30`) et de celui de la formule (`Caster@+0x48`) : sur ce
    canal, la boucle n'itere que les effets de l'attaquant, donc Owner == Caster == l'attaquant.

    Substrat : `att_ctx["owner_effect_names"]`, pose par le foyer UNIQUE
    `entities/effects/__init__.py::_attacker_effect_bonuses` -- la SEULE fonction qui tienne
    reellement la liste des effets de l'attaquant, et elle est PARTAGEE prediction/combat.

    TRI-ETAT : cle ABSENTE -> `None` = PAS MESURE (jamais un `False` invente, qui ferait passer une
    suppression reelle pour son absence)."""
    names = (att_ctx or {}).get("owner_effect_names")
    if names is None:
        return None
    return effect.name in names


class CloseCombatWeaknessReduceDmgEffect(BaseEffect):
    """`IdunBattle.Entities.Effects.Loki.CloseCombatWeakness_ReduceDmg_Effect` (`EffectType` 1130) --
    le volet DEGAT du trait `CloseCombatWeakness`. RE complete : en-tete du module.

    Canal PORT = `create_effect_damage_bonus_for_attack` : le slot natif est litteralement
    `CreateEffectDamageBonusForAttack` (l'effet vit sur l'ATTAQUANT, trigger `get_OwnerIsActor`), donc
    la face d'accumulateur est le defaut `"attacker"` -- rien a surcharger.

    Les trois gates du trigger natif, et ce que le port en fait :

      * `get_OwnerIsActor` -- ce canal n'itere QUE les effets de l'attaquant (cf.
        `_attacker_effect_bonuses`), le gate est donc STRUCTUREL, comme pour `RitesOfMorkai` /
        `MartialInspiration`.
      * `op_LogicalNot(CurrentAbilityIs(<self>))` -- `<self>` est l'`AbilityOrEffect` de CET effet,
        c'est-a-dire l'ability PASSIVE 1130 derivee du trait. Aucun vecteur d'attaque ne peut avoir
        1130 pour ability courante (elle n'a ni ciblage ni behaviour d'attaque : son unique role est
        `AddEffect(owner)` a l'init) -> le gate est TOUJOURS VRAI. Non porte, et c'est dit.
      * `NearbyEnemiesCondition` -- porte ci-dessous, terme par terme.

    ⚠ NATURE DU COUP INCONNUE -> AUCUNE contribution. Le natif n'a pas d'etat « inconnu »
    (`IsMeleeAttack` se derive de `GetAbilityAttackRangeType`), donc sa branche `else` du `If`
    couvre litteralement tout ce qui n'est pas melee. Cote port, `is_ranged is None` ne veut PAS dire
    « pas melee » mais « la facade appelante n'a pas threade la nature » (cf. `effects/base.py`,
    l'encadre `is_melee_attack`/`is_ranged_attack`) : appliquer -25 % dans ce regime imputerait a
    l'attaquant un malus que le natif ne lui met que sur un coup REELLEMENT non-melee. On se TAIT."""

    #: `CreateActiveCondition` = `NearbyEnemiesCondition` : la meme condition que le trigger de la
    #: formule, donc l'`EffectComponent.IsActive` capte est redondant avec ce que la magnitude
    #: evalue deja. Le port re-evalue A LA LECTURE (`create_effect_damage_bonus_for_attack` rend
    #: `None` des que la condition est fausse), exactement comme `EnmityForTheUnworthy`.
    active_condition_ported = True

    def nearby_enemies_condition(self, att_ctx: "Mapping | None" = None) -> "bool | None":
        """`$$NearbyEnemiesCondition` -- FOYER UNIQUE : le natif appelle le MEME corps depuis
        `CreateActiveCondition` et depuis le trigger de `CreateEffectDamageBonusForAttack`, donc les
        deux ne peuvent pas diverger.

            NOT HasEffect(Owner, SuppressCloseCombatWeakness)
            AND ( HasAdjacentEnemies(Caster, CasterTile) OR HasEffect(Owner, StartedTurnAdjacentToEnemy) )

        TRI-ETAT (`None` = pas mesure). Le membre GAUCHE est une NEGATION : ne pas savoir si la
        suppression est presente ne permet pas de conclure, donc `None`. Le membre DROIT est une
        DISJONCTION : un terme VRAI suffit, meme si l'autre est inconnu."""
        suppressed = _owner_has_effect(att_ctx, EffectType.SuppressCloseCombatWeakness)
        if suppressed is not False:                  # None (inconnu) ou True -> pas de conclusion
            return False if suppressed else None
        n_adj = (att_ctx or {}).get(CTX_ADJACENT_ENEMIES)
        started = _owner_has_effect(att_ctx, EffectType.CloseCombatWeakness_StartedTurnAdjacentToEnemy)
        if (n_adj is not None and int(n_adj) >= 1) or started:   # AmountIsEqualOrGreater(..., 1)
            return True
        if n_adj is None or started is None:
            return None
        return False

    def create_effect_damage_bonus_for_attack(self, is_ranged: "bool | None" = None,
                                              has_moved: "bool | None" = None,
                                              target_traits=None,
                                              is_prediction: bool = False,
                                              is_normal_attack: "bool | None" = True,
                                              target_armor_reduced: "bool | None" = None,
                                              att_ctx=None) -> "EffectBonus | None":
        if self.nearby_enemies_condition(att_ctx) is not True:
            return None
        if is_melee_attack(is_ranged):                          # If(IsMeleeAttack, ...)
            pct = trait_var(TRAIT_ID, VAR_MELEE_PCT)            # ConfigConst(0x4c) = -50
        elif is_ranged_attack(is_ranged):
            # If(HasEffect(Caster, SuppressRangeCloseCombatWeakness), Direct(0), ConfigConst(0x53))
            if _owner_has_effect(att_ctx, EffectType.SuppressRangeCloseCombatWeakness):
                return None                                     # Direct(0) -> aucune contribution
            pct = trait_var(TRAIT_ID, VAR_RANGE_PCT)            # ConfigConst(0x53) = -25
        else:
            return None                                         # nature inconnue -> on se tait
        if not pct:
            return None
        return for_percent_increase(True, int(pct))             # pct NEGATIF -> x0.50 / x0.75


class CloseCombatWeaknessStartedTurnAdjacentToEnemyEffect(BaseEffect):
    """`EffectType.CloseCombatWeakness_StartedTurnAdjacentToEnemy` (1129) -- MARQUEUR d'un tour,
    pose sur le porteur par le `CreateTargetTriggerBehaviour` de
    `CloseCombatWeakness_ReduceDmg_Effect` quand il COMMENCE son tour au contact
    (`On(TurnStart_EffectActivation) & HasAdjacentEnemies(Owner, Tiles(Owner))`, `turns = Direct(1)`).

    AUCUN canal : le binaire ne porte aucune classe `CloseCombatWeakness_StartedTurnAdjacentToEnemy*`
    -- l'id n'apparait qu'en ARGUMENT (l'`AddEffect(0x469)` du behaviour ci-dessus et les deux
    `HasEffect(0x469)` de `NearbyEnemiesCondition`). Sa seule semantique est donc d'EXISTER : c'est
    `CloseCombatWeaknessReduceDmgEffect.nearby_enemies_condition` qui le LIT, par
    `att_ctx["owner_effect_names"]`.

    Il est enregistre malgre tout pour que le canal de seed / de capture le materialise en instance
    NOMMEE plutot qu'en `BaseEffect` anonyme : sans entree au registre, un `decisionView.effects`
    portant 1129 rendrait un effet dont le `name` ne remonterait pas -- et le terme
    « ou a COMMENCE son tour adjacent » serait silencieusement mort."""
