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

    return dsl.DslContext(units=units, caster=caster, board=scene.board,
                          elev_by_pos=scene.elev_by_pos,
                          has_trait=_has_trait, get_stat=_get_stat)
