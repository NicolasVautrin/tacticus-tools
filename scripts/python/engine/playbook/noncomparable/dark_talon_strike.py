"""DarkTalonStrikePlaybook — beam en ligne NonComparable (cible = TILE ; util = la tuile visee +
les ennemis CONTINUS alignes dans la MEILLEURE direction issue de cette tuile — direction CHOISIE
par `_best_line_direction`, pas deduite du rayon caster -> visee, cf. #126)."""
from __future__ import annotations

import hexgeo
from engine import battle_query as bq
from engine.entities.active_ability_type import ActiveAbilityType

from ._base import NCContext, NonComparablePlaybook


def _line_enemy_count(aim: tuple, direction: tuple, enemy_set: set,
                      walkable_at, elevation_at, tile_exists) -> int:
    """`|Units(GetTilesInLine(direction))|` = la longueur du rayon partant de `aim` vers `direction`.

    `IdunBattleLogic.Entities.Abilities.Active.Loki.DarkTalonStrikeAbility$$GetTilesInLine(from)` =
    `FilterContinuous( TilesBehindInLine(from = target@0x178, to = <from>, settings{+0x10=1,
    +0x11=1}, count = null), HasUnit(subject) & AreEnemies(owner, Units(subject)) )`.

    Deux troncatures s'empilent, dans cet ordre :
      1. le GATE DE TUILE de `IdunBattle.Core.Services.TileUtil$$IsTileValidForList` (walkable +
         `|elev(ref) - elev(tile)| < 2`, reference qui SUIT la ligne : settings 1/1) -- porte par
         `engine.battle_query.get_tiles_behind`, mirror partage avec la face COMBAT (#117/#124) ;
      2. le `FilterContinuous` (prefixe contigu d'ennemis) : on s'arrete au 1er trou.
    Sans (1) le port SUR-ESTIME l'utilite d'un beam qui traverse une marche >= 2 (il compte des
    ennemis que l'attaque ne touchera jamais). La reference d'elevation initiale est la tuile `aim`
    (= `MainTileEntity(from)` avec `from = target@0x178`), donc la 1re marche testee est
    `aim -> direction`."""
    line = bq.get_tiles_behind(aim, direction, max_count=None, check_walkable=True,
                               update_reference=True, walkable_at=walkable_at,
                               elevation_at=elevation_at, tile_exists=tile_exists)
    cnt = 0
    for tile in line:
        if tile not in enemy_set:
            break                                 # FilterContinuous : prefixe contigu d'ennemis
        cnt += 1
    return cnt


def _best_line_direction(origin: tuple, aim: tuple, enemy_set: set,
                         walkable_at, elevation_at, tile_exists) -> tuple | None:
    """`best` de `IdunBattleLogic.Entities.Abilities.Active.Loki.DarkTalonStrikeAbility$$GetTilesInBestLine`
    (MIRROR 1:1 de l'arbre DSL, meme structure que la face COMBAT
    `engine.runner.abilities.darkangels.dark_talon_get_tiles_in_best_line`) :

        ring    = AdjacentTiles(target@0x178)
        nearest = First( SortByDistance(AdjacentTiles(caster@0x160), target@0x178), 1 )
        angle   = AngleBetweenLines(caster@0x160, nearest, target@0x178, subject@0x180)
        count   = Count( Units( GetTilesInLine(subject@0x180) ) )
        best    = First( SortByFormula( SortByFormula(ring, angle, ASC), count, DESC ), 1 )

    Les deux `SortByFormula` sont CHAINES et `IdunBattle.Entities.Selectors.SortByFormulaSelector$$Select`
    delegue a `Enumerable.OrderBy` / `OrderByDescending` (flag `+0x28` : 0 -> DESCENDING,
    non-nul -> ASCENDING), tris STABLES -> cle PRIMAIRE = nb d'ennemis alignes (DECROISSANT),
    tie-break = ecart ANGULAIRE a la direction d'approche du caster (CROISSANT), puis l'ordre de
    `ring`. `list.sort` Python est stable : deux tris successifs mirrorent l'empilement natif.

    `ring` n'est PAS le ring-1 geometrique : `AdjacentTiles` passe par
    `IdunBattle.Core.Services.TileQuery.u003CIterateAdjacentTilesu003Ed__8$$MoveNext`, qui filtre les
    non-walkables ET applique la porte `|Delta elev| < 2` (cf. `bq.get_adjacent_tiles`).

    L'angle n'a d'effet que sur le CHOIX de la direction a comptes EGAUX -- l'utilite de decision,
    elle, ne depend que du max. Rend `None` si `ring` est vide (aucune direction legale)."""
    ring = bq.get_adjacent_tiles(aim, walkable_at=walkable_at, elevation_at=elevation_at,
                                 tile_exists=tile_exists)
    if not ring:
        return None
    caster_ring = bq.get_adjacent_tiles(origin, walkable_at=walkable_at, elevation_at=elevation_at,
                                        tile_exists=tile_exists)
    # `First(SortByDistance(AdjacentTiles(caster), target), 1)` : OrderBy STABLE -> 1re du minimum.
    nearest = min(caster_ring, key=lambda p: hexgeo.distance(p, aim)) if caster_ring else None
    v1 = bq.get_vector(origin, nearest)           # BattleQuery.GetVector(caster@0x160, nearest)
    scored = [(x, bq.get_angle_between_vectors(v1, bq.get_vector(aim, x)),
               _line_enemy_count(aim, x, enemy_set, walkable_at, elevation_at, tile_exists))
              for x in ring]
    scored.sort(key=lambda s: s[1])               # SortByFormula(angle, ASC)  -- stable
    scored.sort(key=lambda s: -s[2])              # SortByFormula(count, DESC) -- stable
    return scored[0][0]                           # First(1)


def _beam_count(origin: tuple, aim: tuple, enemy_set: set,
                walkable_by_pos: dict | None = None, elev_by_pos: dict | None = None) -> int:
    """`|Enemies(Units(GetTilesInBestLine()))|` = l'utilite NonComparable d'une tuile visee `aim`.

    `IdunBattleLogic.Entities.Abilities.Active.Loki.DarkTalonStrikeAbility$$GetTilesInBestLine` rend
    `target@0x178 op_Addition GetTilesInLine(best)` : la tuile VISEE elle-meme (jamais gatee -- elle
    entre par `op_Addition`, hors de la ligne) PUIS la ligne partant de `best` en s'eloignant de la
    cible. La DIRECTION `best` est CHOISIE (`_best_line_direction`), pas deduite : #126 a remplace le
    prolongement `caster -> aim` par l'argmax natif. Le prolongement etait une BORNE INFERIEURE --
    il sous-evaluait l'utilite des le moment ou une autre direction alignait davantage d'ennemis (et
    `dir = cube(aim) - cube(origin)` n'est meme pas unitaire des que `aim` n'est pas adjacent au
    caster : le rayon SAUTAIT alors des tuiles)."""
    walkable_at, elevation_at, tile_exists = bq.tiles_behind_accessors(walkable_by_pos, elev_by_pos)
    cnt = 1 if aim in enemy_set else 0            # `target@0x178 op_Addition ...` (hors gate)
    best = _best_line_direction(origin, aim, enemy_set, walkable_at, elevation_at, tile_exists)
    if best is not None:
        cnt += _line_enemy_count(aim, best, enemy_set, walkable_at, elevation_at, tile_exists)
    return cnt


class DarkTalonStrikePlaybook(NonComparablePlaybook):
    """`IdunBattle.AI.Playbook.Loki.DarkTalonStrikePlaybook$$EvaluateNonComparable` (id 0x444=1092, Loki/darkaAzrael).
    Attaque en LIGNE (beam) : `IdunBattleLogic.Entities.Abilities.Active.Loki.DarkTalonStrikeAbility$$ExecuteBehaviour` tire un rayon qui
    frappe tous les ennemis alignes. La cible de DECISION = une TILE (l'aim du beam ; targetId natif =
    l'ENTITE-TUILE, id BAS ~43, PAS une unite).

    Structure native (mirror EvaluateNonComparable) : Bucket ctor 3-arg, min = Nullable(Fix64(2))
    (IdunBattle.AI.Playbook.Loki.DarkTalonStrikePlaybook$$.cctor pose `**(DAT_1831e5be8+0xb8)=Fix64(2)` -> MIN_UTILITY=2). Par position balayee,
    enumere `GetEligibleTargetsSelectable(MainTile=P)` (= tuiles-ennemi ou aimer, kind=tile) ; pour
    CHAQUE tuile eligible T :
      bestLine = `IdunBattleLogic.Entities.Abilities.Active.Loki.DarkTalonStrikeAbility$$GetTilesInBestLine(ability)` (DSL AdjacentTiles + SortByFormula angle/count
                  + First) ; `IdunBattleLogic.Entities.Abilities.Active.Loki.DarkTalonStrikeAbility$$GetAttackTargets(bestLine)` = `Enemies(Units(bestLineTiles))` ;
      `util = Fix64.FromInt( <slot2>(attackTargets, T) )` = #ennemis touches par le rayon vise sur T ;
      GenerateAction(P, T, util) + Bucket.AddAction (argmax STRICT `>`, keep-first au tie).

    RECONCILIATION LIVE (ncEvaluate, seed 54321 s11 u91 darkaAzrael, board MC1_67) : caster (3,3),
    tuiles eligibles fromHere = {(3,4),(4,3),(4,2)} (ennemis adjacents). util(aim (3,4)) = 5 = les 5
    ennemis CONTINUS sur la colonne 3 : u81(3,4), u140-decoy(3,5), u85(3,6), u77(3,7), u159(3,8) ;
    aim (4,3)/(4,2) = 1. Le natif caste EN PLACE (origine (3,3) = util 5 max) sur la tuile (3,4) =
    entity 43 (tgtLow 751647920 @ncEvaluate). La feuille beam offline reproduisait AU BIT les util
    5/1/1 -- avec le rayon DROIT de l'epoque, car sur cet etat la meilleure direction EST le
    prolongement (colonne 3). Le moteur ratait car 1092 absent du registre -> le traitait en attaque
    Comparable et visait une UNITE (t83).

    - cible = TILE : l'aim maximisant `_beam_count` depuis l'origine (fromHere) ; emise comme
      `tile_id_by_pos[aim]` (entity-tuile, ce que l'agreement compare = 43). util = beam count.
    - MIN_UTILITY=2 (cctor) : n'aime QUE si >= 2 ennemis alignes ; sinon fallback Comparable.
    - position : sweep ORIGINE-FIRST keep-first -> cast EN PLACE (to=None) quand l'origine porte l'aim
      max (cas s11 ; confirme par les castes en place de la tranche). PRIORITY=0 (#115).
    - IdunBattle.AI.Playbook.Loki.DarkTalonStrikePlaybook$$.ctor = `NonComparablePlaybook(0x444)` -> 1er arg=ability_id.

    GATE D'ELEVATION (#124) : la ligne consomme `engine.battle_query.get_tiles_behind` (settings
    `+0x10 = +0x11 = 1`, cf. `_line_enemy_count`) — MEME mirror que la face COMBAT (#117). Avant #124
    la feuille tirait un rayon cube droit SANS gate et sur-estimait l'utilite d'un beam traversant
    une marche >= 2.

    DIRECTION DU BEAM (#126) : `best` est CHOISI par `_best_line_direction` (argmax du nb d'ennemis
    alignes sur les `AdjacentTiles(target@0x178)`, tie-break angulaire), mirror de
    `DarkTalonStrikeAbility$$GetTilesInBestLine`. Avant #126 la feuille prenait le prolongement
    `caster -> aim` : BORNE INFERIEURE de l'utilite native (elle ne pouvait que SOUS-estimer le
    nombre d'ennemis alignes, donc rater des casts que le natif fait).

    FLAGS VALIDATEUR (approximations) :
      * AIM depuis l'ORIGINE uniquement (`fromHere`) : le natif balaie aussi les tuiles de MOVE (aimer
        apres deplacement). Non modelise -> si le natif MOVE+caste (meilleur beam ailleurs), le port
        caste en place (miss residuel). SUR : le port ne fire QUE si beam-origine >= 2, ce qui implique
        que le generateur NC natif etait NON-VIDE (global max >= 2) -> le natif caste AUSSI DarkTalon
        (jamais un cast d'ability parasite ; au pire une tuile/position residuelle differente)."""
    ABILITY_ID = int(ActiveAbilityType.DarkTalonStrike)  # 1092
    MIN_UTILITY = 2.0     # IdunBattle.AI.Playbook.Loki.DarkTalonStrikePlaybook$$.cctor = Fix64(2) -> aime ssi beam >= 2 ennemis alignes
    PRIORITY = 0

    def generate_candidates(self, ctx: NCContext) -> list[dict]:
        if ctx.ability_targets is None or ctx.origin is None:
            return []
        at = ctx.ability_targets(ctx.uid, self.ABILITY_ID) or {}
        # tuiles d'aim eligibles DEPUIS L'ORIGINE (fromHere, kind=tile) = GetEligibleTargetsSelectable.
        aims: list[tuple] = []
        for u in (at.get("units") or []):
            if u.get("unitId") != ctx.uid:
                continue
            for a in (u.get("abilities") or []):
                if a.get("abilityId") != self.ABILITY_ID:
                    continue
                for t in (a.get("fromHere") or []):
                    if t.get("kind") == "tile" and t.get("tile"):
                        aims.append((t["tile"]["col"], t["tile"]["row"]))
        if not aims:
            return []
        enemy_set = {ep for ep in (ctx.epos or []) if ep and ep[0] is not None}
        best_aim, best_c = None, None
        for T in aims:                            # keep-first au tie (ordre GetEligibleTargets)
            c = _beam_count(ctx.origin, T, enemy_set,
                            ctx.walkable_by_pos, ctx.elev_by_pos)   # gate d'elevation (#124)
            if best_c is None or c > best_c:      # strict > : 1re tuile du max gagne
                best_aim, best_c = T, c
        if best_aim is None or best_c < self.MIN_UTILITY:
            return []
        tile_id = (ctx.tile_id_by_pos or {}).get(best_aim)
        if tile_id is None:
            return []                             # pas d'entity-tuile -> ne peut pas emettre la cible
        if ctx.debug:
            import sys
            print(f"    [dbg NC u{ctx.uid}] DarkTalonStrike aim={best_aim} beam={best_c} "
                  f"tileId={tile_id}", file=sys.stderr)
        # cast EN PLACE (origine porte l'aim max ; sweep origine-first keep-first).
        return [{"target": tile_id, "ability": self.ABILITY_ID, "to": None, "pred": float(best_c)}]
