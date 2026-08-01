"""Retrait d'une unite de SES TUILES -- `IdunBattle.Operations.RemoveUnitFromTilesOperation$$Execute`
(mutateur ECS IMPERATIF). L'unite quitte le PLATEAU sans mourir ni etre despawnee : ni PV touches, ni
flag `Dead`, ni flag `Removed`, aucun vecteur on-death, aucun event `On(...)`.

Deux surcharges natives, toutes deux presentes dans la table de symboles VERSIONNEE :

    Execute(unit  : IdunBattle.Core.IEntity,               removeTileFromUnit : bool)
    Execute(units : IList<IdunBattle.Core.IEntity>,        removeTileFromUnit : bool)   # boucle sur la 1re

La surcharge LISTE n'a qu'un appelant (`Core.Services.OperationProcessor$$RemoveUnitsFromTiles`) et
n'est qu'une boucle ; elle n'est pas portee separement (le port itere son selecteur en amont, dans la
feuille DSL, comme `RemoveUnit`).

SEQUENCE de la surcharge UNITE, LUE au decompile (`this+0x10` = `MatchState`, `+0x18` = journal
d'events, `+0x20` = flux de steps de vue) :

  1. si le flux de vue est actif : emission d'un STEP `RemoveUnitFromTiles` portant l'unite
     (`IdunBattle.View.BattleStream.StepHandlers.RemoveUnitFromTilesStepHandler`) -- PURE VUE.
  2. `pos = IdunBattle.Entities.EntityExtensions$$GetUnitPosition(unit, state)`  (sauvegarde)
  3. `feet = IdunBattle.Entities.UnitExtensions$$GetUnitFeet(unit, state)` ; `null` -> NRE (le natif
     LEVE ; cf. le gate du port plus bas)
  4. **BOUCLE 1, inconditionnelle** -- pour chaque pied : `tile = GetMainTile(pied, state)` ; si le
     `TileComponent` de cette tuile designe CE pied (`comp@+0x10 == pied.Id`), on l'efface (`= 0`).
     C'est le lien TUILE -> PIED (l'occupation).
  5. **BOUCLE 2, si `removeTileFromUnit`** -- pour chaque pied : `UnitFootComponent@+0x14 = 0`.
     C'est le lien PIED -> TUILE.
  6. `UnitComponent` de l'unite : DEUX `Nullable<UnitPositionId>` (`@+0x88..0x97` et `@+0x98..0xa7`)
     recoivent la position sauvegardee en 2 (`IdunBattle.Core.UnitPositionId$$.ctor(pos)`).
  7. event de MATCH `0x1b` avec la charge utile `{0x85 : removeTileFromUnit}` -- c'est le
     `RemoveUnitFromTiles ... Clear_Unit_Tiles=1` visible dans la cascade live du cast de
     `TunnelingHorror` (mesure #366-r1).

COLLAPSES ET RESIDUS NOMMES du port :
  * **Les boucles 4 et 5 sont LA MEME ARETE cote port.** Le natif materialise le lien dans les deux
    sens (la tuile pointe le pied, le pied pointe la tuile) ; le port a COLLAPSE la chaine
    `pied -> UnitFootComponent.TileId -> tuile` en un simple `(col,row)` (cf. `UnitComponent.feet`),
    et son occupation est DERIVEE (`_occupied` / `CanAddUnit` balaient les positions des unites
    vivantes) -- il n'existe donc qu'une arete a couper. `set_unit_feet(state, uid, [])` la coupe :
    `feet = []` materialise + retrait de la `PositionComponent`.
  * **`remove_tile_from_unit=False` n'est donc PAS representable** : ce serait « les tuiles sont
    liberees mais l'unite y reste », un etat que le collapse ci-dessus interdit. Le port ne mute rien
    et le DIT (`applied: False` dans la trace) plutot que de mentir. Aucune regression : l'UNIQUE
    appelant natif qui passe `false` est l'etape 6 de `IdunBattle.Operations.RemoveUnitOperation$$Execute`,
    dont le port collapse deja le retrait de tuiles en `UnitComponent.alive = False`
    (cf. `operations/remove_unit.py`), et il n'appelle pas cette Operation.
  * etape 1 (STEP de vue) et etape 7 (event de match) : le port n'a ni flux de vue ni journal de
    match -- non portes, comme partout ailleurs dans `operations/`.
  * etape 6 (les deux `Nullable<UnitPositionId>`) : **NON PORTEE, faute de lecteur**. Aucun
    consommateur porte ne lit une « derniere position connue » ; le seul candidat natif serait le
    repli `MoveUnit(Owner, <repli>)` de
    `IdunBattleLogic.Entities.Abilities.Active.Loki.TunnelingHorror_AppearAbility$$ExecuteBehaviour`
    (active 1060), hors perimetre de ce foyer. A porter EN MEME TEMPS que 1060, pas avant.
  * etape 3 : le natif LEVE une NRE quand l'entite n'est pas une unite (`GetUnitFeet` rend `null`).
    Le port rend `None` -- un refus TRACE, aligne sur les autres Operations portees
    (`RemoveUnitOperation` rend `None` sur chacun de ses gates) plutot qu'une exception qui ferait
    tomber un tour entier.

Frontiere DSL (#149) : la feuille `IdunBattleLogic.Entities.DSLBehaviors$$RemoveUnitFromItsTiles`
(-> `IdunBattle.Entities.Behaviours.RemoveUnitFromItsTilesBehaviour$$Execute`, au-dessus,
structurelle) APPELLE cette Operation (en-dessous, imperative), unite par unite.
RE : `docs/rl/case-366-r1-tunneling-horror-pending-summon.md`.
"""
from __future__ import annotations

from typing import Optional

from ..state import State
from ..components import UnitComponent, get_unit_feet, set_unit_feet


class RemoveUnitFromTilesOperation:
    """Mirror `IdunBattle.Operations.RemoveUnitFromTilesOperation$$Execute` (surcharge UNITE).

    `remove_tile_from_unit` = le `param_3` natif. Rend `None` quand un gate refuse (entite inconnue,
    entite qui n'est pas une unite) -- aucune mutation ; sinon un dict de trace.
    """
    __slots__ = ()

    @staticmethod
    def execute(state: State, unit_id: Optional[int], *,
                remove_tile_from_unit: bool = True) -> Optional[dict]:
        if state is None or unit_id is None:
            return None
        e = state.get_entity(int(unit_id))
        if e is None:
            return None
        if e.get_component(UnitComponent) is None:
            # etape 3 : `GetUnitFeet` rend `null` sur une entite qui n'est pas une unite -> NRE
            # native. Le port refuse en le tracant (cf. docstring de module).
            return None
        before = get_unit_feet(state, int(unit_id))     # etape 2 : la position AVANT
        if not remove_tile_from_unit:
            # Boucle 4 SEULE : non representable apres le collapse (cf. docstring de module).
            return {"unit": int(unit_id), "tiles": list(before), "applied": False,
                    "remove_tile_from_unit": False}
        set_unit_feet(state, int(unit_id), [])          # boucles 4 + 5 (arete unique cote port)
        return {"unit": int(unit_id), "tiles": list(before), "applied": True,
                "remove_tile_from_unit": True}
