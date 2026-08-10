"""`IdunBattleLogic.Entities.Abilities.Triggered.Loki.SpecialIssueCombiMelta_AddEffectAbility` --
la TROISIEME portee du kit `SpecialIssueCombiMelta` (`TriggeredAbilityType` 1545), la seule qui
vive sur une ABILITY et non sur un effet : le `Pinned` (`EffectType` 0x429 = 1065, << Suppressed >>
cote joueur) pose sur la cible d'une attaque NORMALE portee a la distance **3 EXACTEMENT**.

Porteurs (`units.passiveAbilities == ['SpecialIssueCombiMelta']`, LU au gameconfig) :
`darkaSternguard` << Ramus >> (HERO, `kind` lineup) et le npc `darkaBossSternguardLHE`.

Les deux autres portees sont deja portees et vivent cote EFFET (canal #179 / bonus de degat) :
`SpecialIssueCombiMelta_AdditionalHitsEffect` (1563, d == 2) et `..._ExtraDmgEffect` (1564,
d == 1). Cf. `docs/rl/case-419-r1-tr11-special-issue-combi-melta.md`.

## Les DEUX corps natifs, LUS VERBATIM sur `rnca9r7q6c`

`...SpecialIssueCombiMelta_AddEffectAbility$$CreateTrigger` :

    On( 0x26 = NormalAttack, ownerNeedsToBeAlive: 1 )
      op_BitwiseAnd  get_OwnerIsCaster
      op_BitwiseAnd  IsAtRange( <DSLSelectors+0x48 = Caster>,
                                <DSLSelectors+0x60 = Target>,
                                DSLFormulas.Get(3) )

`...SpecialIssueCombiMelta_AddEffectAbility$$CreateBehaviour` (feuille E UNIQUE) :

    DSLBehaviors.AddEffect( 0x429 = 1065 Pinned,
                            AbilityStateReference,
                            targets = <DSLSelectors+0x60 = Target>,
                            turns   = null )

## TROIS lectures qui ne se devinent pas

1. **`IsAtRange` compare par EGALITE**, pas par `<=`. Corps entier de
   `IdunBattle.Entities.Triggers.IsAtRangeAbilityTrigger$$ShouldTrigger` :
   `attendu = <formule this+0x28>.Calculate(entities)` ; `d = query.<slot 0x6f = GetDistance>(
   <this+0x18>.Select(entities), <this+0x20>.Select(entities))` ; `return d == attendu`.
   Foyer de port PARTAGE avec les deux effets : `entities/effects/base.py::is_at_range`.
2. **Le litteral de portee est un `Get(3)` construit AU CALL-SITE**, contrairement aux deux effets,
   dont la formule est un CHAMP pre-construit de l'instance `DSLFormulas`
   (`IdunBattleLogic.Entities.DSLFormulas$$.ctor` : `+0x20 = Const(1)`, `+0x28 = Const(2)`). Les
   trois portees 1 / 2 / 3 sont donc lues sur TROIS artefacts distincts, jamais deduites l'une de
   l'autre. `IdunBattleLogic.Entities.DSLFormulas$$Get(int)` fabrique un montant CONSTANT.
3. **Le selecteur SOURCE est NUL, donc la source de l'effet EST LA CIBLE** -- pas le caster. La
   surcharge appelee est `DSLBehaviors.AddEffect(effectType, abilityState, targets, turns)`
   (5 arguments avec le `this`), et les DEUX surcharges 5-args passent litteralement `0` en
   `param_5` a `IdunBattle.Entities.Behaviours.AddEffectBehaviour$$.ctor`. Le fallback est LU dans
   `IdunBattle.Entities.Behaviours.AddEffectBehaviour$$Execute` : `+0x60` (source) et `+0x68`
   (cibles) sont deux selecteurs ; la boucle sur les cibles fait
   `src = <cible courante>; if (<Select(+0x60)> != 0) src = <ce resultat>;`. D'ou
   `source_from_target=True` -- le meme parametre que `BrazierOfHolyFire` / `RadBombardment`.
   ⚠ CONTRASTE avec `SuppressiveFireAbility$$CreateBehaviour`, qui pose le MEME effet 1065 : lui
   appelle la surcharge 6-args avec `source = <DSLSelectors+0x30 = Owner>`, donc source = caster.
   Recopier le patron sans relire la surcharge aurait ecrit la mauvaise source.

⚠ Offsets `DSLSelectors` de ce build : `Owner` 0x30, `Caster` 0x48, `Target` 0x60, `Current` 0x68,
`TargetTiles` 0x78 (les fiches ecrites sur `gqfc5mff6c` portent +0x118 sur chacun).

## MONTAGE -- `ABILITY_TRIGGERS`, et c'est ce qui manquait (`#419-r1-tr11-r4`)

La fiche d'origine pistait `StaticBattleRules.ActiveAbility$$GetDerivedTriggeredAbilities` (patron
`Hailstrike` / `Drachnyen`). **C'EST FAUX, et les deux dicts natifs ont ete LUS** :

* `StaticBattleRules.ActiveAbility$$GetDerivedTriggeredAbilities` est indexe par
  `ActiveAbilityType` ; l'active de `darkaSternguard` est `SternguardFocus`, pas 1545 ;
* `StaticBattleRules.TriggeredAbility$$GetDerivedTriggeredAbilities` (dict `<statics>+0x88`, peuple
  par `StaticBattleRules.TriggeredAbility$$.cctor`) ne compte que **DEUX** entrees, toutes deux
  lues verbatim en fin de cctor : `0x3ef -> [0x3fc]` (1007 LivingLightning -> 1020
  LivingLightning_MoveEffect) et `0x48e -> [0x491]` (1166 TheWrathfulDead -> 1169
  TheWrathfulDead_Overkill). **`0x609` (1545) n'y figure pas.**

Le montage est donc le chemin ORDINAIRE d'une passiveAbility : `units.passiveAbilities` porte le
nom `SpecialIssueCombiMelta`, qui designe la triggered 1545, dont la classe est instanciee avec ses
soeurs -- exactement la forme `LetTheGalaxyBurnAbility` / `LetTheGalaxyBurn_ResetAbility`, deux
classes natives pour UN nom de kit. Cote port : `ABILITY_TRIGGERS["SpecialIssueCombiMelta"]`.

`SpecialIssueCombiMelta_InitAbility` (la soeur, `AddEffect(0x61b) & AddEffect(0x61c)` a l'init du
porteur) n'est PAS portee et n'entre PAS au registre : le port ne rejoue aucun spawn, les deux
effets 1563/1564 arrivent deja poses par `load_state`. Une entree vide serait un mensonge de
couverture.

## CE QUE CE PORT N'ETABLIT PAS

* Le MULTI-HEX : `IdunBattle.Core.Services.MovementQuery$$GetDistance` prend le MIN sur les paires
  de PIEDS ; le port compare les MAIN TILES (meme approximation que les deux effets et que la face
  DECISION -- residu `#419-r1-tr11-r1`, non confronte, aucune MoW au montage).
* Le gate `!HasFlag(unit, 6 = Dead)` de `AddEffectBehaviour$$Execute` : il est porte par le noeud
  `AddEffect` / `AddEffectOperation` PARTAGE, pas ici.
"""
from __future__ import annotations

from typing import Optional

from ....state import State
from ....components import OwnerComponent, PositionComponent, UnitComponent
from ....abilities.behaviours.context import entities_from_state
from ....abilities.behaviours.effects import AddEffect
from .....entities.selectors.accessors import Target
from .....entities.effect_type import EffectType
from .....entities.effects.base import is_at_range
from .....entities.triggered_ability_type import TriggeredAbilityType
from .....dsl.effects import ExecutionContext
from .....dsl.event_trigger_type import EventTriggerType
from ..base import TriggeredAbility, TriggerEvent

#: Cle du registre `ABILITY_TRIGGERS` = le NOM gameconfig de la passiveAbility porteuse.
SPECIAL_ISSUE_COMBI_MELTA = "SpecialIssueCombiMelta"

PINNED = int(EffectType.Pinned)                        # 0x429 = 1065 -- UI << Suppressed >>
#: `DSLFormulas.Get(3)` du call-site -- montant CONSTANT, compare par EGALITE (cf. en-tete).
_RANGE_EXACT = 3


def special_issue_combi_melta_pinned_tree():
    """Feuille de `...SpecialIssueCombiMelta_AddEffectAbility$$CreateBehaviour` (MIRROR 1:1) :

        AddEffect( effectType = 0x429 = Pinned,
                   source     = <selecteur NUL>  ->  la CIBLE elle-meme,
                   cible      = Target@DSLSelectors+0x60,
                   turns      = null )

    `duration_rounds=None` = pas de `TurnsFromRounds` (le 5e argument natif est `0`) ->
    `DefaultAmountOfRounds(0x429)`, comme le Pinned de `SuppressiveFire` / `CrushingClaws`.
    `source_from_target=True` = le fallback natif de `AddEffectBehaviour$$Execute` quand le
    selecteur source (`+0x60` de l'instance) est nul -- cf. en-tete, point 3."""
    return AddEffect(PINNED, "Pinned", Target(), duration_rounds=None,
                     source_from_target=True)


def _pos_of(state: State, uid: Optional[int]):
    """`<selecteur>.Select(entities)` puis `MovementQuery$$GetDistance` : le port compare les MAIN
    TILES (`PositionComponent`). Position absente -> None -> `is_at_range` rend FAUX."""
    e = state.get_entity(uid) if uid is not None else None
    pc = e.get_component(PositionComponent) if e is not None else None
    return None if pc is None else (pc.col, pc.row)


class SpecialIssueCombiMeltaAddEffectAbility(TriggeredAbility):
    """`SpecialIssueCombiMelta_AddEffectAbility` (triggered 1545, passiveAbility
    `SpecialIssueCombiMelta`) -- cf. l'en-tete du module pour les deux arbres natifs.

    `On(0x26 = NormalAttack) & OwnerIsCaster & IsAtRange(Caster, Target, Get(3))`
    -> `AddEffect(1065 Pinned, targets = Target, source = la cible)`."""
    event_id = int(EventTriggerType.NormalAttack)              # 0x26 = 38
    TRIGGERED_ABILITY_ID = TriggeredAbilityType.SpecialIssueCombiMelta

    def matches(self, state: State, ev: TriggerEvent) -> bool:
        if ev.actor_id is None or int(ev.actor_id) != int(self.owner_id):
            return False                                       # get_OwnerIsCaster
        if ev.target_id is None or state.get_entity(ev.target_id) is None:
            return False
        owner = state.get_entity(self.owner_id)
        uc = owner.get_component(UnitComponent) if owner is not None else None
        if uc is None or not uc.alive:                          # On(..., ownerNeedsToBeAlive = 1)
            return False
        # `IsAtRange(Caster@+0x48, Target@+0x60, Get(3))` -- EGALITE EXACTE. Foyer PARTAGE avec les
        # deux effets du meme kit (`entities/effects/base.py::is_at_range`) : un seul endroit ou la
        # lecture `==` peut deriver.
        return is_at_range(_pos_of(state, self.owner_id),
                           _pos_of(state, ev.target_id), _RANGE_EXACT)

    def execute_behaviour(self, state: State, ev: TriggerEvent) -> Optional[dict]:
        """Behaviour = arbre DSL `special_issue_combi_melta_pinned_tree()` (mirror 1:1)."""
        if state.effects is None:
            return None                                        # pas d'EffectsState -> pose impossible
        if ev.target_id is None or state.get_entity(ev.target_id) is None:
            return None
        ectx = ExecutionContext(state=state, rng=state.rng)
        special_issue_combi_melta_pinned_tree().execute(
            entities_from_state(state, self.owner_id, ev.target_id), ectx)
        placed = any(p.get("placed") for n, p in ectx.emitted if n == "AddEffect")
        return {"ability": SPECIAL_ISSUE_COMBI_MELTA, "owner": int(self.owner_id),
                "suppressed": int(ev.target_id), "placed": bool(placed),
                "distance": _RANGE_EXACT, "on_event": ev.event_id}


def _team_of(state: State, uid: Optional[int]):
    """Helper de DIAGNOSTIC seulement. ⚠ Le trigger natif ne porte AUCUN `AreEnemies` -- le kit
    n'en a pas besoin (une attaque normale ne vise pas un allie), et en ajouter un serait recabler
    une gate que le decompile ne contient pas."""
    e = state.get_entity(uid) if uid is not None else None
    oc = e.get_component(OwnerComponent) if e is not None else None
    return oc.team if oc is not None else None
