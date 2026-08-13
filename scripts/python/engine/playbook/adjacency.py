"""Foyer PARTAGE de l'adjacence d'ENTITE cote DECISION -- `#419-r1-tr10-r2` (multi-tuiles) et
`#419-r1-tr10-r4` (`UnitSelectionType`).

Trois comptages portes ecrivaient CHACUN leur boucle << pour chaque unite vivante, si
`is_adjacent(pos_du_sujet, pos_de_l_unite)` >> : `righteous_repugnance.count_additional_targets`,
`boltstorm.count_all_targets`, `fire_of_absolution.count_adjacent_by_camp`. Les trois portaient donc
la MEME approximation sur les DEUX axes ci-dessous. Trois corps auraient ete un fork.

## 1. L'axe MULTI-TUILES -- ce que le natif itere, et ce que le port sait

`IdunBattleLogic.Entities.DSLSelectors$$AdjacentTiles(origin)` construit un
`IdunBattle.Entities.Selectors.AdjacentTilesSelector`, dont le `$$Select` est LU verbatim :

    result = new OrderedSet<ITile>();
    inner  = this.<+0x20 = origin>.Select(entities);          // les tuiles du SUJET
    foreach (t in inner) {
        foreach (n in battleQuery.<slot +0x50 = IterateAdjacentTiles>(t, false, true, true))
            if (!inner.Contains(n)) result.Add(n);            // le ring-1 MOINS l'empreinte
    }
    return result;

et `inner` remonte, pour une ENTITE, a `IdunBattle.Entities.EntityExtensions$$IterateTiles(entity,
state)` -- **TOUTES** les tuiles de l'entite, dans l'ordre des pieds, pas la seule MainTile. Sur une
unite a 3 ou 7 pieds (MACHINE OF WAR), le voisinage natif est donc l'union des ring-1 de chaque
pied, prive de l'empreinte elle-meme.

⚠ **Le port ne peut pas le savoir de lui-meme, et c'est un trou de SEEDING, pas de logique.** Le
substrat existe cote COMBAT (`runner.components.get_unit_feet`, mirror de
`UnitExtensions$$GetUnitFeet`, qui lit `UnitComponent._feet`) ; cote DECISION, **aucun RPC ne
publie la liste des tuiles d'une unite** -- `state.ts` ne projette que la PREMIERE tuile d'une
`UnitPosition`, et `engine/runner/ability_range.py` porte deja le meme constat pour
`GetFeetCount`. `iterate_tiles` ci-dessous lit donc la cle `feet` **si l'appelant la porte** (dict
d'unite venu du runner, `_unit_dict`) et retombe sur `[MainTile]` sinon : le comportement d'avant,
EXACTEMENT, quand le canal est muet.

## 2. L'axe `UnitSelectionType` -- le litteral `3` n'est pas << vivante >>

Les trois arbres passent `unitSelectionType: 3` a leurs primitives (`AdjacentEnemies`,
`AdjacentUnits`, `SurroundingEnemies`, `SelectUniqueUnits`). `3` est
`UnitSelectionType.OnlyAliveAndTargetable`, et son foyer natif
`IdunBattle.Entities.UnitExtensions$$MatchesUnitSelectionType` rend
`IsAlive(unit) && !HasFlag(unit, UnitFlag.Untargetable)` -- DEUX clauses. Le port n'en portait
qu'une (`alive`), donc il comptait une unite en cours de deep-strike que le natif ecarte
(degradation PERMISSIVE). Le mirror du foyer vit dans
`engine.entities.unit_selection_type.matches_unit_selection_type` ; le domaine offline du flag est
`UNTARGETABLE_EFFECT_TYPES` (le meme que `engine.ai.state_bridge._is_untargetable` -- le flag
`0x11` est pose par `UntargetableEffect$$ApplyInternal`, donc il se lit par ses effets).
"""
from __future__ import annotations

from .. import battle_query as bq
from ..entities.effects.aura_selectors import UNTARGETABLE_EFFECT_TYPES
from ..entities.unit_selection_type import UnitSelectionType, matches_unit_selection_type


def iterate_tiles(scene, uid) -> list:
    """`IdunBattle.Entities.EntityExtensions$$IterateTiles(entity, state)` -- les tuiles de TOUS les
    pieds de l'entite, dans l'ordre des pieds (`feet[0]` EST la MainTile).

    Canal du port, dans l'ordre :
      * `scene.feet_by_id` -- le capteur DECISION `#419-r1-tr10-r2`
        (`decisionView.units[].feet` / `.mows[].{feet,platformTiles}`, mirror de
        `IdunBattle.Entities.EntityExtensions$$GetTiles`). C'est le SEUL canal qui couvre les
        MACHINES OF WAR, absentes de `scene.units` par construction (canal `.mows` separe) ;
      * la cle `feet` du dict d'unite -- ce que `runner.components.get_unit_feet` materialise
        (`UnitComponent._feet`), present des que la scene vient d'un etat runner. Elle porte des
        COUPLES (`(col,row)`), la table ci-dessus aussi : les deux formes sont normalisees ici ;
      * a defaut, `[scene.pos(uid)]` -- la MainTile SEULE, c.-a-d. la degradation d'avant
        `#419-r1-tr10-r2`. Elle est EXACTE pour toute unite a un pied (le cas nominal) et
        SOUS-ESTIME le voisinage d'une MACHINE OF WAR.

    Rend `[]` si l'unite n'a pas de position -- ce que rend aussi le natif pour une entite sans
    tuile (`GetUnitFeetIds` sur une non-unite, une MoW hors plateau)."""
    if uid is None:
        return []
    tbl = getattr(scene, "feet_by_id", None) or {}
    feet = tbl.get(int(uid))
    if not feet:
        u = next((x for x in (scene.units or ()) if x.get("id") == uid), None)
        feet = (u or {}).get("feet")
    if feet:
        return [_as_pos(f) for f in feet]
    p = scene.pos(uid)
    return [] if p is None else [(p[0], p[1])]


def _as_pos(f) -> tuple:
    """Normalise une tuile venue de l'un ou l'autre canal : couple `(col,row)` cote COMBAT,
    dict `{"col","row"}` cote hook (`readTileCoord`). Aucune supposition sur le canal appelant."""
    if isinstance(f, dict):
        return (int(f["col"]), int(f["row"]))
    return (int(f[0]), int(f[1]))


def is_targetable(scene, uid) -> bool | None:
    """`!UnitExtensions$$HasFlag(unit, UnitFlag.Untargetable)`, lu OFFLINE par le domaine
    `UNTARGETABLE_EFFECT_TYPES` (le flag `0x11` est pose/retire par
    `IdunBattle.Entities.Effects.Common.UntargetableEffect$$ApplyInternal`/`$$RevertInternal`, donc
    porter l'un de ces effets EST porter le flag -- meme lecture que
    `engine.ai.state_bridge._is_untargetable`, dont c'est le pendant DECISION).

    Rend `None` -- **PAS MESURE** -- quand la scene ne porte pas d'etat d'effets. Le tri-etat est ce
    qui interdit d'inventer un `True` (qui compterait une unite que le natif ecarte) ou un `False`
    (qui en ecarterait une qu'il compte) : `matches_unit_selection_type` degrade alors la clause en
    VRAI, c.-a-d. le comportement d'avant cette tranche."""
    es = getattr(scene, "eff_state", None)
    if es is None:
        return None
    return not any(es.has_effect(int(uid), int(t)) for t in UNTARGETABLE_EFFECT_TYPES)


def unit_matches(scene, u: dict,
                 selection_type=UnitSelectionType.OnlyAliveAndTargetable) -> bool:
    """`IdunBattle.Entities.UnitExtensions$$MatchesUnitSelectionType(unit, selectionType, state)`
    applique a une entree de `scene.units`. `alive` vient du dict (canal de toute la face
    DECISION), `targetable` de `is_targetable` ci-dessus."""
    uid = u.get("id")
    if uid is None:
        return False
    return matches_unit_selection_type(selection_type, alive=bool(u.get("alive")),
                                       targetable=is_targetable(scene, uid))


def adjacent_positions(scene, uid, neigh=None) -> set:
    """`DSLSelectors$$AdjacentTiles(entity)` = l'UNION des ring-1 de chaque tuile de l'entite, MOINS
    son empreinte (`if (!inner.Contains(n))` du `$$Select`).

    Le ring-1 est celui de `IdunBattle.Core.Services.TileQuery.u003CIterateAdjacentTilesu003Ed__8$$MoveNext`,
    donc `battle_query.is_adjacent` **sans** la porte d'elevation : celle-ci vit dans `is_adjacent`
    et depend de la tuile de DEPART, ce qui interdit de pre-calculer un set commun. Les appelants
    passent donc par `is_adjacent_to_entity` ci-dessous, qui teste pied par pied."""
    tiles = iterate_tiles(scene, uid)
    if not tiles:
        return set()
    nm = neigh if neigh is not None else bq.neigh_map(scene)
    foot = set(tiles)
    out = set()
    for t in tiles:
        for n in (nm.get(t) or ()):
            if n not in foot:
                out.add(n)
    return out


def subject_tiles_at(scene, subject_uid, at_pos) -> "list|None":
    """Les pieds du sujet REPOSITIONNE sur `at_pos` -- le substrat de la tuile CANDIDATE (#948-r1).

    POURQUOI CE MECANISME EXISTE, et il est LU : `IdunBattle.Operations.SimulateEffectsOperation$$
    DoActionInSimulatedTile` DEPLACE REELLEMENT l'unite avant d'executer l'action de prediction --
    il appelle le slot du processor qui la pose sur la tuile, puis
    `$$SimulateMoveUnitTriggers`, puis `$$RefreshSimulatedEffects`, PUIS invoque l'action, et
    restaure tout ensuite. Un selecteur `AdjacentUnits(Owner)` evalue pendant l'action part donc de
    `EntityExtensions$$IterateTiles(owner)` -- c'est-a-dire de la tuile CANDIDATE, puisque l'entite
    y a ete physiquement deplacee dans l'etat simule.

    `at_pos is None` -> `None` : l'appelant garde les pieds REELS (aucun changement).

    ⚠ **MONO-PIED SEULEMENT, et c'est une DEGRADATION NOMMEE.** Reconstruire l'empreinte d'une
    entite MULTI-TUILES a une position d'arrivee demanderait de connaitre son orientation et sa
    forme a cette tuile, qu'aucun canal offline ne publie. Un sujet multi-pieds rend donc `None`
    (= pieds reels), ce qui est exactement le comportement d'avant : jamais une empreinte
    INVENTEE, qui compterait des voisins que le natif ne voit pas. Residu #948-r3."""
    if at_pos is None:
        return None
    reels = iterate_tiles(scene, subject_uid)
    if len(reels) != 1:
        return None                      # multi-tuiles (MoW) -> pieds REELS, cf. l'avertissement
    return [(at_pos[0], at_pos[1])]


def is_adjacent_to_entity(scene, subject_uid, pos, elev=None, neigh=None,
                          subject_tiles=None) -> bool:
    """`pos` appartient-elle a `AdjacentTiles(subject)` ? = il existe un pied du sujet dont `pos`
    est voisine au sens NATIF (`battle_query.is_adjacent`, qui porte la porte d'elevation
    `|delta| < 2`), et `pos` n'est pas elle-meme un pied du sujet.

    Sur une unite a UN pied, c'est exactement `is_adjacent(scene.pos(subject), pos)` -- le port
    d'avant. Le seul delta est le sujet MULTI-TUILES.

    `subject_tiles` (#948-r1) SUBSTITUE les pieds du sujet -- la tuile CANDIDATE d'un plan, cf.
    `subject_tiles_at`. `None` = pieds reels, le comportement d'avant."""
    tiles = subject_tiles if subject_tiles is not None else iterate_tiles(scene, subject_uid)
    if not tiles:
        return False
    p = (pos[0], pos[1])
    if p in tiles:                       # `- Tiles(unit)` / `!inner.Contains(n)`
        return False
    nm = neigh if neigh is not None else bq.neigh_map(scene)
    ev = elev if elev is not None else getattr(scene, "elev_by_pos", None)
    return any(bq.is_adjacent(t, p, ev, nm) for t in tiles)


def unit_in_adjacent_tiles(scene, subject_uid, other_uid, elev=None, neigh=None,
                           subject_tiles=None) -> bool:
    """`Units(AdjacentTiles(subject), unique, sel).Contains(other)` -- la question que posent les
    trois comptages, une fois developpees leurs primitives.

    Les DEUX cotes sont multi-tuiles, et c'est ce que la version << position contre position >>
    ratait : `Units(tiles)` resout l'OCCUPANT de chaque tuile, donc `other` y figure des qu'UN de
    ses pieds tombe dans `AdjacentTiles(subject)` -- lui-meme l'union des ring-1 de TOUS les pieds
    de `subject`. Sur deux unites a un pied, la question se reduit a
    `is_adjacent(pos(subject), pos(other))`, le port d'avant."""
    if other_uid is None:
        return False
    others = iterate_tiles(scene, other_uid)
    if not others:
        return False
    nm = neigh if neigh is not None else bq.neigh_map(scene)
    ev = elev if elev is not None else getattr(scene, "elev_by_pos", None)
    return any(is_adjacent_to_entity(scene, subject_uid, p, ev, nm, subject_tiles)
               for p in others)


__all__ = ["iterate_tiles", "is_targetable", "unit_matches", "adjacent_positions",
           "is_adjacent_to_entity", "unit_in_adjacent_tiles", "subject_tiles_at"]
