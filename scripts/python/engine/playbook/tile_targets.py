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
from .. import battle_query as _bq
from ..entities.stats import StatType as _ST


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

    # `ctx.has_negative_modifier` (`IdunBattle.Entities.Triggers.HasNegativeModifier$$ShouldTrigger`)
    # et `ctx.is_in_team_aura` (`IdunBattle.Entities.Triggers.IsInAuraRangeTrigger$$ShouldTrigger` ->
    # `IdunBattle.Core.Services.BattleQuery$$IsInTeamAuraRange`) : les DEUX branches du predicat
    # `PlagueburstMortarAbility$$GetIsValidAdjacentEnemyTrigger`, que la face COMBAT cable deja dans
    # `runner/abilities/behaviours/context.entities_from_state`. Sans eux, ce predicat rendait
    # FAUX D'OFFICE cote DECISION (les deux accesseurs absents -> `False` par degradation), donc le
    # `Filter` de `GetMainDamageTarget` vidait l'ensemble et le terme de PREDICTION de 1169 valait
    # 0 PARTOUT -- y compris dans le regime ou le natif, lui, predit du degat (MESURE : caster
    # `deathTyphus` au CONTACT, `pairUtility(tuile occupee) = 1.178` la ou le port rendait 0).
    # Meme substrat que le COMBAT, deux sources d'etat : l'ECS la-bas, la `Scene` ici.
    def _has_negative_modifier(u, stat_types) -> bool:
        uc = scene.ctx((u or {}).get("id"))
        st = getattr(uc, "stats", None) if uc is not None else None
        return bool(st.has_negative_modifier(stat_types)) if st is not None else False

    def _turns_started(u) -> int:
        """`StatAmount(Owner, 0xc = TurnsStarted)` -- l'entree de `GetCurrentRange` d'un `IAuraEffect`.
        Canal MESURE d'abord (`combatSnapshot`, table `Scene.turns_started_by_id`), repli sur le
        `UnitContext` (froid) : jamais un 0 invente quand la table est simplement absente."""
        uid = (u or {}).get("id")
        v = scene.turns_started(uid) if uid is not None else None
        if v is not None:
            return int(v)
        return int(_get_stat(u, int(_ST.TURNS_STARTED), 0, None) or 0)

    def _is_in_team_aura(u, effect_type, team_reference) -> bool:
        team = (team_reference or {}).get("team")
        if team is None:
            return False                       # `GetCurrentTeamId(ref)` indisponible -> pas d'aura
        return _bq.is_in_team_aura_range(int(effect_type), int(team), u, units,
                                         _has_trait, _turns_started)

    # `IsPositionMachineForCurrentPlayer` (`IsPositionMachineForPlayerTrigger$$ShouldTrigger`)
    # compare `BattleQuery.GetPositionMachineForPlayer(<joueur COURANT>)` -- une propriete du
    # PLATEAU (le groupe de spawn du joueur), PAS le slot d'une machine deployee. La cascade vit
    # dans `AiDecisionContext.machine_of_war_position` ; `None` = non mesure -> predicat False.
    # Sans ce fil, l'arbre de 1148 prendrait TOUJOURS la branche `else` de son `If` -- une
    # degradation SILENCIEUSE qui deplace la zone-triangle (dir 4 au lieu de 1). MESURE : sur
    # `MC1_67`/`SpawnPointSetIndex 1`, le natif vise le triangle `{S, SE}`, donc position 2.
    # #979 : `hasattr` ne suffit PLUS -- `NCContext` porte desormais un CHAMP de meme nom, qui vaut
    # `None` quand le canal n'a pas ete cable (probes, tests, chemin offline). `None()` aurait leve
    # `TypeError`. Le test est donc `callable`, et l'absence rend `None` = non mesure.
    _mow = getattr(ctx, "machine_of_war_position", None)
    mow_pos = _mow() if callable(_mow) else None

    # `HasEffect(<entite-tuile>, 5 = Fire)` -- branche TUILE de
    # `IdunBattle.Entities.EntityExtensions$$HasOneOfEffects`, lue par le `Filter` de
    # `DaemonicOrdnanceAbility$$GetAllDamageableTargets`. Le substrat est le MEME
    # `Scene.tile_effects_by_pos` que le gate de cible principale et que le set AoE de la face
    # PREDICTION : un seul foyer (`_tile_has_effect_from_scene`, #359-r1), donc la route de DECISION
    # et la face PREDICTION ne peuvent pas se contredire sur « cette tuile brule ».
    # Carte d'effets absente -> l'helper rend `None` -> le noeud `HasEffect` rend False lui-meme
    # (feu INCONNU, jamais suppose) : c'est le regime du natif sur tout board frais.
    # Import LOCAL : `playbook.prediction` tire tout le registre d'abilities, dont ce socle n'a pas
    # besoin au chargement.
    from .prediction.abilities import _tile_has_effect_from_scene

    return dsl.DslContext(units=units, caster=caster, board=scene.board,
                          elev_by_pos=scene.elev_by_pos,
                          current_player_machine_position=mow_pos,
                          tile_has_effect=_tile_has_effect_from_scene(scene),
                          has_trait=_has_trait, get_stat=_get_stat,
                          has_negative_modifier=_has_negative_modifier,
                          is_in_team_aura=_is_in_team_aura)


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
