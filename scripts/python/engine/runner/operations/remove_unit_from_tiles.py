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
  * etape 6 : **`@+0x98` EST DESORMAIS PORTE (#448-r1-r1-r3-r1) -- LE LECTEUR EXISTAIT.** La note qui
    vivait ici (« NON PORTEE, faute de lecteur ; aucun consommateur porte ne lit une derniere
    position connue ») a ete rendue FAUSSE par #1082 sans que personne ne la relise :
    `movement._movement_start_position` LIT exactement ce slot (`GetPreviousPositionThisTurn`), pour
    le `movementStartPosition` de `MoveUnitOperation$$Execute`. Le canal etait complet des deux
    bouts SAUF ici -- l'ecrivain manquait, et c'est ce qui rendait le second bras inatteignable en
    simulation pure (il ne survivait que par le SEEDING live, `snapshot._load_units` ->
    `movement.previousPositionThisTurn`). Sans cette ecriture, une unite retiree du plateau repart
    avec la position d'AVANT SON DERNIER MOUVEMENT -- ou `None` -- au lieu de la tuile qu'elle vient
    de quitter.
    ⚠ Le natif ecrit **DEUX** slots avec la MEME valeur (`@+0x88` puis `@+0x98`, deux
    `Nullable<UnitPositionId>` du `MovementComponent`, qui SURVIT au retrait). Cote port, seul
    `@+0x98` est representable : son jumeau `@+0x88` est loge sur la `PositionComponent`, que
    `set_unit_feet(uid, [])` SUPPRIME. `PreviousTileSelector` (`components.previous_tiles`, qui lit
    `@+0x88`) rend donc `[]` apres un retrait de plateau la ou le natif rend la tuile quittee.
    RESIDU **#448-r7** -- il demande de deloger `previous` de la `PositionComponent`, ce qui est un
    changement de FOYER, pas une ligne.
  * etape 6 (le gate `cVar2 == '\0'`) : l'ecriture, le STEP de vue et l'event de match partagent le
    MEME predicat (slot `0xb` du `MatchState`, celui qui commute aussi la branche courte de
    `MoveUnitOperation$$Execute`). Le port n'a pas ce mode -- il porte le regime NORMAL, qui est
    celui ou le gate est faux.
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
        # etape 6 -- `@+0x98`, ECRIT APRES les boucles comme le natif (il capture `before`, pris en
        # etape 2 AVANT elles). L'ordre importe : `set_unit_feet(uid, [])` retire la
        # `PositionComponent`, et `@+0x98` vit sur le `UnitComponent` PRECISEMENT pour y survivre.
        # ⚠ L'ECRITURE EST INCONDITIONNELLE, y compris sur une empreinte VIDE, et ce n'est pas un
        # detail : le natif construit `new UnitPositionId(pos)` sans gate (contrairement a
        # `SetUnitPositionOperation$$SavePreviousPosition`, qui lui REFUSE `Count < 1`). Retirer
        # deux fois de suite une entite deja hors plateau doit donc EFFACER la position gardee, pas
        # la conserver -- sinon `_movement_start_position` prendrait son second bras sur une tuile
        # que l'unite a quittee il y a longtemps. Cote natif la valeur ecrite est un `Nullable`
        # PORTEUR d'une empreinte vide, que `UnitPosition.IsEmpty` rejette ensuite : le `[]` du port
        # est le meme comportement observable.
        uc = e.get_component(UnitComponent)
        if uc is not None:
            uc.previous_position_this_turn = [(int(c), int(r)) for c, r in before]
        return {"unit": int(unit_id), "tiles": list(before), "applied": True,
                "remove_tile_from_unit": True}
