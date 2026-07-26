"""ThriceBlessedConflagrationPlaybook — buff sur un ALLIE + beam en ligne NonComparable (util = les
ennemis CONTINUS alignes depuis la tuile de l'allie vise, dans la MEILLEURE direction du DISQUE r=1).

Meme FAMILLE que `dark_talon_strike.py` (`GetTilesInBestLine` + `SortByFormula(count, DESC)`) mais
TROIS differences LUES au decompile, dont deux changent le resultat :
  (a) `ring = SurroundingTiles(target@0x178, includeCenter=0, r=1, 0, 0)` et NON `AdjacentTiles`
      -> `IsTileValidForList(tile, src, 1, 0)` = walkable SANS porte d'elevation (DarkTalon, lui,
      passe par `IterateAdjacentTiles` et sa porte INCONDITIONNELLE `|Delta elev| < 2`) ;
  (b) UN SEUL `SortByFormula` (le compte) : PAS de tri par angle -> le tie-break est directement
      l'ordre du disque (`(cube.x, cube.y)` croissant), pas l'ecart angulaire ;
  (c) `settings` de `TilesBehindInLine` = `+0x10 = 0` (1 octet) et `+0x11` laisse au ctor
      -> `checkWalkable = updateReference = False` (DarkTalon : `0x101` = 1/1).
Un copier-coller de la feuille DarkTalonStrike serait donc FAUX sur les trois axes.
"""
from __future__ import annotations

from engine import battle_query as bq
from engine.entities.active_ability_type import ActiveAbilityType

from ._base import NCContext, NonComparablePlaybook


def _line_enemy_count(aim: tuple, direction: tuple, enemy_set: set,
                      walkable_at, elevation_at, tile_exists) -> int:
    """`Count( GetTilesInLine(direction) )` = la longueur du prefixe d'ennemis CONTIGUS partant de
    `aim` vers `direction`.

    `IdunBattleLogic.Entities.Abilities.Active.Loki.ThriceBlessedConflagrationAbility$$GetTilesInLine(from)` :

        settings = new TilesBehindInLineSettings ; settings+0x10 = 0        # 1 octet, +0x11 intact
        pred     = HasUnit(Subject@0x180) & AreEnemies(Owner@0x148, Units(Subject@0x180))
        start    = First( SortByDistance( Tiles(Target@0x178), from ), 1 )
        return     FilterContinuous( TilesBehindInLine(start, from, settings, null), pred )

    `start` : SortByDistance + First sur les tuiles de la CIBLE — l'IDENTITE pour une cible
    mono-tuile (le seul cas confronte) -> `frm = aim`. La ligne part donc de la tuile de l'allie
    vise et S'ELOIGNE de lui dans la direction `direction`, la 1re tuile rendue etant `direction`
    elle-meme (`get_tiles_behind` : `tile_k = cube(to) + k*(cube(to) - cube(frm))`).

    `settings` 0/0 = les DEFAUTS de `get_tiles_behind` (inventaire des 4 call-sites, #117) : PAS de
    gate walkable ni d'elevation sur la ligne — contrairement a DarkTalonStrike (1/1). Le
    `FilterContinuous` casse au 1er trou : c'est LUI qui borne la ligne ici."""
    line = bq.get_tiles_behind(aim, direction, max_count=None, check_walkable=False,
                               update_reference=False, walkable_at=walkable_at,
                               elevation_at=elevation_at, tile_exists=tile_exists)
    cnt = 0
    for tile in line:
        if tile not in enemy_set:
            break                                 # FilterContinuous : prefixe contigu d'ennemis
        cnt += 1
    return cnt


def _best_line_direction(aim: tuple, enemy_set: set,
                         walkable_at, elevation_at, tile_exists) -> tuple | None:
    """`best` de `IdunBattleLogic.Entities.Abilities.Active.Loki.ThriceBlessedConflagrationAbility$$GetTilesInBestLine`
    (MIRROR 1:1 de l'arbre DSL, meme structure que la face COMBAT
    `engine.runner.abilities.sisterhood.thrice_blessed_get_tiles_in_best_line`) :

        ring  = SurroundingTiles(target@0x178, includeCenter=0, radius=1, 0, 0)
        count = Count( GetTilesInLine(Subject@0x180) )
        best  = First( SortByFormula(ring, count, 0 = DESC), 1 )

    UN SEUL `SortByFormula`, flag `0` -> `IdunBattle.Entities.Selectors.SortByFormulaSelector$$Select`
    delegue a `Enumerable.OrderByDescending` (flag `+0x28`: 0 -> DESCENDING). Tri STABLE -> a comptes
    EGAUX c'est l'ordre du `ring` qui tranche, et cet ordre est celui de la triple boucle cube de
    `TileQuery.u003CIterateSurroundingTilesu003Ed__6$$MoveNext` = `(cube.x, cube.y)` croissant, que
    `bq.get_surrounding_tiles` mirrore. (DarkTalonStrike, lui, intercale un tri par ANGLE ASC ; 1187
    n'en a PAS — la lecture est faite, ce n'est pas une simplification.)

    `ring` n'est PAS le ring-1 de `AdjacentTiles` : `SurroundingTiles` filtre par
    `IsTileValidForList(tile, src, checkWalkable=1, checkElevation=0)` — walkable OUI, porte
    d'elevation NON. Une tuile a +2 d'elevation reste une direction de beam LEGALE ici.

    Rend `None` si le ring est vide (aucune direction legale)."""
    ring = bq.get_surrounding_tiles(aim, radius=1, include_center=False, check_walkable=True,
                                    walkable_at=walkable_at, elevation_at=elevation_at,
                                    tile_exists=tile_exists)
    if not ring:
        return None
    scored = [(x, _line_enemy_count(aim, x, enemy_set, walkable_at, elevation_at, tile_exists))
              for x in ring]
    scored.sort(key=lambda s: -s[1])               # SortByFormula(count, DESC) — stable
    return scored[0][0]                            # First(1)


def _beam_count(aim: tuple, enemy_set: set,
                walkable_by_pos: dict | None = None, elev_by_pos: dict | None = None) -> int:
    """`|Enemies(Owner, GetTilesInBestLine())|` = l'utilite NonComparable d'une cible `aim`.

    `GetTilesInBestLine` rend `target@0x178 op_Addition GetTilesInLine(best)` ; `GetAttackTargets`
    l'enveloppe dans `Enemies(Owner@0x148, ..., 3)`. La tuile de la CIBLE entre donc dans l'ensemble
    mais en est retiree par `Enemies` des lors que la cible est un ALLIE — ce qui est le cas
    nominal (l'ability buffe un allie). Le terme est neanmoins mirrore tel quel : si le ciblage
    natif admettait un ennemi, il compterait.

    L'utilite consommee par le playbook est le `.Count` du selecteur rendu par `GetAttackTargets`
    (slot 2 de l'interface, `FUN_1801e40c0(selector, <iface>, 2)` dans `EvaluateNonComparable`),
    converti par `FixMath.NET.Fix64$$FromInt` — un ENTIER, jamais une prediction de degat."""
    walkable_at, elevation_at, tile_exists = bq.tiles_behind_accessors(walkable_by_pos, elev_by_pos)
    cnt = 1 if aim in enemy_set else 0             # `target@0x178 op_Addition ...` (allie -> 0)
    best = _best_line_direction(aim, enemy_set, walkable_at, elevation_at, tile_exists)
    if best is not None:
        cnt += _line_enemy_count(aim, best, enemy_set, walkable_at, elevation_at, tile_exists)
    return cnt


class ThriceBlessedConflagrationPlaybook(NonComparablePlaybook):
    """`IdunBattle.AI.Playbook.Loki.ThriceBlessedConflagrationPlaybook$$EvaluateNonComparable`
    (id 0x4a3 = 1187, `adeptExorcist` — Exorcist, Adepta Sororitas, MACHINE OF WAR).

    Structure native (mirror `EvaluateNonComparable`) : `Bucket.ctor(bucket, 0, Nullable(Fix64(1)))`
    — `IdunBattle.AI.Playbook.Loki.ThriceBlessedConflagrationPlaybook$$.cctor` pose
    `**(DAT+0xb8) = Fix64.FromInt(1)` -> **MIN_UTILITY = 1** (DarkTalonStrike : 2). Par position
    balayee, enumere `GetEligibleTargetsSelectable(unit, position)` ; pour CHAQUE cible eligible T :

        bestLine      = ThriceBlessedConflagrationAbility$$GetTilesInBestLine(ability)
        attackTargets = ThriceBlessedConflagrationAbility$$GetAttackTargets(ability, bestLine)
                      = Enemies(Owner@0x148, bestLine, 3)
        util          = Fix64.FromInt( <slot 2>(attackTargets, ctx(T)) )
        GenerateAction(position, T, util) + Bucket.AddAction   (argmax STRICT `>`, keep-first au tie)

    `IdunBattle.AI.Playbook.Loki.ThriceBlessedConflagrationPlaybook$$.ctor` =
    `NonComparablePlaybook<T>(0x4a3)` -> 1er arg = ability_id. PRIORITY = 0 (#115 : aucun playbook
    n'override `get_Priority`).

    - cible = une UNITE ALLIEE (le buff `ThriceBlessedConflagration_ExtraPctDamage` 1401 /
      `_RangedExtraPctDamage` 1436 se pose sur elle) ; le DEGAT part sur la ligne d'ennemis issue de
      sa tuile. La cible emise est donc l'id d'unite, pas une entite-tuile (contraste DarkTalon).
    - util = #ennemis CONTIGUS alignes depuis la tuile de la cible dans la meilleure direction.
    - MIN_UTILITY = 1 : UN seul ennemi aligne suffit a proposer le cast — donc a PRIMER sur toute
      Comparable (les NC gagnent par ORDRE de generateur, pas par utilite comparee).
    - position : sweep ORIGINE-FIRST keep-first (l'utilite ne depend PAS de la position du caster —
      seule la tuile de la CIBLE l'ancre) -> cast EN PLACE (`to = None`). Consequence directe de la
      structure native : `GetTilesInBestLine` ne lit ni `Caster@0x160` ni `CasterTile@0x168`.

    FLAGS VALIDATEUR (approximations assumees) :
      * AIM depuis l'ORIGINE uniquement (`fromHere`) : le natif balaie aussi les tuiles de MOVE. Le
        set de cibles peut donc etre plus large apres deplacement (portee), mais l'UTILITE d'une
        cible donnee est position-INDEPENDANTE -> un cast propose en place l'est aussi par le natif.
      * cible multi-tuiles : `start` (`First(SortByDistance(Tiles(target), from), 1)`) et le
        `- Tiles(entity)` du ring degenerent en la tuile unique. Non exerce (aucun porteur
        multi-tuiles confronte)."""
    ABILITY_ID = int(ActiveAbilityType.ThriceBlessedConflagration)   # 0x4a3 = 1187
    MIN_UTILITY = 1.0     # `ThriceBlessedConflagrationPlaybook$$.cctor` = Fix64.FromInt(1)
    PRIORITY = 0

    def generate_candidates(self, ctx: NCContext) -> list[dict]:
        # PAS de gate `ctx.origin is None` (contraste DarkTalonStrike, dont l'angle a besoin du
        # caster) : `GetTilesInBestLine` de 1187 ne lit NI `Caster@0x160` NI `CasterTile@0x168` --
        # tout est ancre a `Target@0x178`. Le porteur natif est une MACHINE OF WAR, entite SANS
        # `PositionComponent` (`observeBattle` : `pos = null` by design) : exiger une origine
        # rendrait la feuille morte sur son SEUL porteur.
        if ctx.ability_targets is None:
            return []
        at = ctx.ability_targets(ctx.uid, self.ABILITY_ID) or {}
        # cibles eligibles DEPUIS L'ORIGINE (`fromHere`) = mirror `GetEligibleTargetsSelectable`.
        # `abilityTargets` rend ici des entrees `kind == "unit"` (ALLIES, mesure live : le natif ne
        # propose que mes unites) portant leur `pos` -> la tuile d'ancrage du beam est celle de la
        # CIBLE. `ctx.units` sert de repli quand la projection n'a pas inline la position.
        aims: list[tuple] = []                     # (targetId, position de la cible)
        pos_by_id = {u.get("id"): ((u.get("pos") or {}).get("col"), (u.get("pos") or {}).get("row"))
                     for u in (ctx.units or []) if u.get("id") is not None and u.get("pos")}
        for u in (at.get("units") or []):
            if u.get("unitId") != ctx.uid:
                continue
            for a in (u.get("abilities") or []):
                if a.get("abilityId") != self.ABILITY_ID:
                    continue
                for t in (a.get("fromHere") or []):
                    tid = t.get("targetId")
                    src = t.get("pos") or t.get("tile") or {}
                    p = ((src.get("col"), src.get("row")) if src.get("col") is not None
                         else pos_by_id.get(tid))
                    if tid is not None and p and p[0] is not None:
                        aims.append((tid, (p[0], p[1])))
        if not aims:
            return []
        enemy_set = {ep for ep in (ctx.epos or []) if ep and ep[0] is not None}
        scored = [(tid, _beam_count(p, enemy_set, ctx.walkable_by_pos, ctx.elev_by_pos))
                  for tid, p in aims]
        best_id, best_c = None, None
        for tid, c in scored:                      # keep-first au tie (ordre GetEligibleTargets)
            if best_c is None or c > best_c:       # strict > : 1re cible du max gagne
                best_id, best_c = tid, c
        if best_id is None or best_c < self.MIN_UTILITY:
            return []
        if ctx.debug:
            import sys
            print(f"    [dbg NC u{ctx.uid}] ThriceBlessedConflagration target={best_id} "
                  f"beam={best_c} scored={scored}", file=sys.stderr)
        # cast EN PLACE : l'utilite est ancree a la tuile de la CIBLE, pas a celle du caster.
        return [{"target": best_id, "ability": self.ABILITY_ID, "to": None, "pred": float(best_c)}]
