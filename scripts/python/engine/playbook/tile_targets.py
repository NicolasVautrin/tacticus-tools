"""Socle commun de la route de decision a cibles TUILE (case-302).

Ce module ne porte AUCUNE mecanique d'ability : il fournit le contexte DSL qu'un playbook
tile-target doit presenter a ses selecteurs, cote DECISION. Le pendant COMBAT existe deja
(`engine.runner.abilities.*` evalue les memes arbres sur un `State`) ; ici la source d'etat est la
`Scene` de prediction portee par `ctx.scene`, exactement comme pour `resurrection_orb`.

Rappel de ce que le natif fait (detail : `docs/rl/case-302-route-cible-tuile.md` §1) :
`IdunBattle.AI.Playbook.BasePlaybook$$GetEligibleTargetsEntities` rend une liste d'`IEntity` NON
TYPEE, et `IdunBattle.AI.Playbook.BasePlaybook$$GenerateAction` la passe telle quelle a
`IdunBattle.AI.ActionGenerators.UnitAction$$.ctor(position, target, abilityType)`. Une cible TUILE
circule donc dans le MEME slot qu'une cible unite — il n'y a pas de « format d'action tuile ».
"""
from __future__ import annotations

from .. import dsl
from ..entities.traits.unit_trait import entity_trait_names, has_trait


def dsl_context_for_tile_target(ctx):
    """`SelectorContext` de la face DECISION pour un playbook TILE-TARGET.

    `CalculateCustomUtility` d'un playbook tile-target construit un `AbilityEntities` a
    `owner = caster = <le caster>` et `target = <l'entite tuile>`. Le `target` n'est PAS pose ici :
    il est passe par le vehicule de collapse `FixedTileIds([tileId])` au selecteur, parce que le
    contexte DSL du port porte des dicts d'UNITE et qu'une entite-tuile n'en est pas une. C'est le
    meme montage que la face COMBAT (`deathguard.execute_plagueburst_mortar`).

    ⚠ Le caster n'est PAS repositionne sur la tuile candidate (contrairement a
    `resurrection_orb._dsl_context`) : c'est une difference NATIVE, pas une simplification. Le
    `AbilityEntities` de `PlagueburstMortarPlaybook$$CalculateCustomUtility` ne porte pas
    `casterPosition` — un playbook tile-target dont le custom LIT `casterPosition` devra construire
    son propre contexte, comme 1009 le fait.

    Rend `None` si la `Scene` ou son board manquent (`combatSnapshot` indisponible) : l'appelant
    retombe alors sur `0.0`, jamais sur une valeur inventee."""
    scene = getattr(ctx, "scene", None)
    if scene is None or getattr(scene, "board", None) is None:
        return None
    units = list(scene.units or [])
    caster = next((u for u in units if u.get("id") == ctx.uid), None)
    if caster is None:
        return None
    vis_by_id = {u.get("id"): u.get("visualId") for u in units}

    def _has_trait(u, trait) -> bool:
        uid = (u or {}).get("id")
        return has_trait(entity_trait_names(scene.ctx(uid), vis_by_id.get(uid)), trait)

    def _get_stat(u, stat_type, variant, level) -> int:
        uc = scene.ctx((u or {}).get("id"))
        return int(uc.get_stat(int(stat_type), int(variant or 0))) if uc is not None else 0

    # `IsPositionMachineForCurrentPlayer` (`IsPositionMachineForPlayerTrigger$$ShouldTrigger`)
    # compare `BattleQuery.GetPositionMachineForPlayer(<joueur COURANT>)` -- une propriete du
    # PLATEAU (le groupe de spawn du joueur), PAS le slot d'une machine deployee. La cascade vit
    # dans `AiDecisionContext.machine_of_war_position` ; `None` = non mesure -> predicat False.
    # Sans ce fil, l'arbre de 1148 prendrait TOUJOURS la branche `else` de son `If` -- une
    # degradation SILENCIEUSE qui deplace la zone-triangle (dir 4 au lieu de 1). MESURE : sur
    # `MC1_67`/`SpawnPointSetIndex 1`, le natif vise le triangle `{S, SE}`, donc position 2.
    mow_pos = ctx.machine_of_war_position() if hasattr(ctx, "machine_of_war_position") else None

    return dsl.DslContext(units=units, caster=caster, board=scene.board,
                          elev_by_pos=scene.elev_by_pos,
                          current_player_machine_position=mow_pos,
                          has_trait=_has_trait, get_stat=_get_stat)


def unit_on_tile(dctx, tile_id):
    """`IdunBattle.Entities.UnitExtensions$$GetUnit(entity, state)` restreint au domaine TUILE.

    Le natif (surcharge `GetUnit(entity, state)`) dispatche par TYPE d'entite :
    `UnitEntity` -> elle-meme ; `TileEntity` -> `TileContentComponent.IsFilled ? state.GetEntity(
    tileContent.UnitId) : null` ; `FootEntity` -> l'unite du pied. C'est le resolveur qu'appelle
    la boucle de `IdunBattle.AI.Playbook.Loki.DaemonicOrdnancePlaybook$$CalculateCustomUtility`
    sur chaque entite-tuile rendue par son selecteur de zone.

    Ici on n'a que le substrat DECISION (des dicts d'unite portant leur `pos`), donc on resout
    l'occupant PAR POSITION -- exactement ce que fait deja le noeud `Units`
    (`IdunBattle.Entities.Selectors.UnitsOnTilesSelector$$Select`). Vivantes seulement (#57m : un
    mort n'occupe plus sa tuile, `KillUnitOperation` la libere).

    ⚠ RESIDU NOMME, mesurable et non couvert : le natif resout par `TileContentComponent`, qui est
    rempli pour CHAQUE pied d'une unite multi-tuiles (`AddUnitOperation` fait un `AddFoot` par
    tuile), alors que `dv.units` ne porte que la MAIN tile. Une unite a plusieurs pieds dont seul un
    pied SECONDAIRE tombe dans la zone est donc vue par le natif et pas par ce port. Les heros du
    pool sont mono-tuile ; les MoW (multi-plateformes) n'ont pas de ligne dans `dv.units`.

    Rend le dict d'unite, ou `None` si la tuile est vide / hors board."""
    board = getattr(dctx, "board", None)
    if board is None or tile_id is None:
        return None
    try:
        tid = int(tile_id)
    except (TypeError, ValueError):
        return None
    if tid not in board.by_id:
        return None
    c = board.coord(tid)
    if c is None:
        return None
    pos = (int(c[0]), int(c[1]))
    for u in (dctx.units or []):
        if not (bool(u.get("alive", True)) and (u.get("hp") or 0) > 0):
            continue
        p = u.get("pos")
        if p and (p.get("col"), p.get("row")) == pos:
            return u
    return None
