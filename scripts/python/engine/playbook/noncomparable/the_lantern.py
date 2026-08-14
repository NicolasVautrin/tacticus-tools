"""`TheLanternPlaybook` -- la face DECISION de `1094 TheLantern` (`deathBossMortarion`). #1030.

`IdunBattle.AI.Playbook.Loki.TheLanternPlaybook$$EvaluateNonComparable(caster, casterPosition,
abilityState)` -- MIRROR 1:1 du decompile, build `rnca9r7q6c` :

    bucket = new Bucket( 0, Nullable(<statics+0x00>) )                 # minUtility
    foreach (entities in BasePlaybook$$GetEligibleTargetsSelectable(caster, casterPosition)) {
        n = <ability>.GetTilesForTargetAreaFromTargetTile().<ITargetsSelector slot 2 Count>(entities)
        if ( !(Fix64(n) < Fix64(7)) )                                  # GATE : |zone| >= 7
            bucket.AddAction( BasePlaybook$$GenerateAction(casterPosition, <element>,
                                                           GetEnemiesHitUtilityForTarget(entities)) )
    }
    return bucket

et `...TheLanternPlaybook$$GetEnemiesHitUtilityForTarget(entities)` :

    units = <ability>.GetTilesForTargetAreaFromTargetTile()
                     .<ITargetsSelector slot 4 SelectUniqueUnits>(entities, selectionType = 3)
    units.FilterInPlace( u => UnitExtensions$$IsEnemy(u, <caster>, <matchState>) )   # b__0
    n1 = units.Count
    units.FilterInPlace( u => UnitExtensions$$HasTrait(u, 0x3ea = 1002 Psyker) )     # b__5_1
    n2 = units.Count
    return Fix64(n1) * <statics+0x00>  +  Fix64(n2) * <statics+0x08>

`...TheLanternPlaybook$$.cctor` (relu) : `<statics+0x00> = Fix64.op_Implicit(1)` = **1**,
`<statics+0x08> = Fix64.FromIntFraction(1, 10)` = **0,1**. Le PREMIER sert DEUX fois -- il est le
`minUtility` du `Bucket` ET le poids du terme d'ennemis : une seule constante, deux roles, et c'est
LU (le meme champ statique est charge aux deux sites).

`...TheLanternPlaybook$$ShouldEvaluate(unit)` = `<IBattleQuery slot 0x1b>(unit, 2)` =
`HasMinimumRemainingTurns(unit, 2)` -- slot NOMME par `metadata/interface_slots.tsv` (entree
VERSIONNEE, derivee du `global-metadata.dat`). Le gate a un SENS mecanique : le cast n'inflige RIEN,
son degat part au tour SUIVANT (`triggers/loki/the_lantern_attack.py`) ; l'ability est donc
INUTILE quand il ne reste pas deux tours.

⚠ `...TheLanternPlaybook$$.ctor` appelle `ComparablePlaybook<T>$$.ctor(this, 0x446 = 1094)` et
SURCHARGE pourtant `EvaluateNonComparable` : c'est la VOIE de la methode propre qui classe le
playbook (`decision_face_voies.VOIES`), pas le ctor de la base -- meme regle que le probe #1021.

QUATRE ECARTS, tous NOMMES

1. **L'EMPREINTE DU CASTER A LA POSITION BALAYEE.** La zone lit `<DSLSelectors+0x58> = CasterTiles`,
   c'est-a-dire les SEPT tuiles de Mortarion (le masque porte `CasterHas7Tiles`). Cote DECISION le
   port ne stocke de la position candidate que sa MAIN TILE (`ctx.origin` / `reach_nc` sont des
   `(col,row)`) -- c'est le residu `#459-r1`, et il MORD ici plus qu'ailleurs : le « pont »
   `ring2(T) & adj(casterTiles)` est calcule sur un caster mono-hex. A l'ORIGINE, l'empreinte reelle
   est reconstituee depuis `obs_units` quand elle y est publiee (plusieurs entrees a la meme
   `unitId`) ; sur une position de MOUVEMENT, elle ne peut pas l'etre. Residu **#1030-r2**.
2. **`GetEligibleTargetsSelectable` est reconstitue depuis `abilityTargets`** (kind=tile), comme
   `ItItchesPlaybook` : le natif enumere des ENTITES-TUILES et les passe TELLES QUELLES a
   `GenerateAction`, donc la cible emise est un ID DE TUILE.
3. **La porte `GetUseProbability`** n'existe pas ici (aucune surcharge propre) -> `should_evaluate`
   ne porte QUE `HasMinimumRemainingTurns`.
4. **`selectionType = 3`** (`OnlyAliveAndTargetable`) est LU au 2e argument du `SelectUniqueUnits` :
   une unite en DEEP STRIKE (`UnitFlag.Untargetable`) ne compte pas. Le port l'applique par
   `alive` + absence du flag quand `obs_units` le publie ; a defaut il compte l'unite (degradation
   PERMISSIVE, jamais un refus invente).

ASCII only.
"""
from __future__ import annotations

import hexgeo

from engine import battle_query as bq   # foyer `is_adjacent` / `neigh_map` (#1030-r2)
from engine.entities.active_ability_type import ActiveAbilityType
from engine.entities.traits.unit_trait import UnitTrait, entity_trait_names, has_any_trait
import engine.playbook.noncomparable._base as NCB   # FORME B : le foyer #1027-r5 reste patchable

from ._base import NCContext, NonComparablePlaybook, _sweep_origin_first

#: Le litteral `2` du call-site natif `<IBattleQuery slot 0x1b>(unit, 2)` -- un nombre de TOURS.
CASTER_MIN_REMAINING_TURNS = 2

#: `numFeet` du porteur (`deathBossMortarion`) -- la BRANCHE de
#: `MovementQuery$$GetPossibleTileListsFromMovableTiles` qui construit `{t} U GetAdjacentTiles(t)`,
#: et le bit `CasterHas7Tiles` (37) du masque de ciblage de 1094. Un CARDINAL, pas un id.
_CASTER_FEET_COUNT = 7

#: `<statics+0x00>` du `.cctor` -- `Fix64.op_Implicit(1)`. DEUX roles LUS : le `minUtility` du
#: `Bucket` et le poids du terme « ennemis touches ».
_W_ENEMY = 1.0
#: `<statics+0x08>` du `.cctor` -- `Fix64.FromIntFraction(1, 10)`. Le bonus par ennemi `Psyker`.
_W_PSYKER = 0.1
#: Le litteral du gate d'`EvaluateNonComparable` : `Fix64(n) < Fix64(7)` -> on GARDE `n >= 7`.
#: C'est un CARDINAL DE TUILES, il ne designe aucune entite du jeu -- hors regle d'enum.
_MIN_TILES_HIT = 7
#: `UnitExtensions$$HasTrait(u, 0x3ea)` du lambda `b__5_1`.
_PSYKER = UnitTrait.Psyker                                            # 0x3ea = 1002
#: 2e argument LU du `SelectUniqueUnits` (`ITargetsSelector` slot 4).
_SELECTION_ONLY_ALIVE_AND_TARGETABLE = 3


class TheLanternPlaybook(NonComparablePlaybook):
    """`IdunBattle.AI.Playbook.Loki.TheLanternPlaybook$$EvaluateNonComparable` (id 0x446 = 1094,
    `deathBossMortarion` « Mortarion » -- GUILD BOSS, kind `npc`). Cf. l'en-tete du module.

    Utilite = `|ennemis dans la ZONE| + 0,1 x |ceux d'entre eux qui sont Psyker|`, sous DEUX gates :
    `HasMinimumRemainingTurns(caster, 2)` en amont du sweep, et `|zone| >= 7` par cible.

    La ZONE est la MEME que celle de la face COMBAT -- le natif appelle litteralement
    `...TheLanternAbility$$GetTilesForTargetAreaFromTargetTile()`, qui republie mot pour mot la
    chaine de l'`ExecuteBehaviour`. Le port la re-derive ici en geometrie de DECISION
    (`hexgeo.disk` + le canal `neigh`/`walkable` du `NCContext`), faute d'un `State` : les deux
    ecritures doivent rester en phase, et c'est ce que garde
    `tests/engine/test_1030_the_lantern_offline.py` (etage 3, meme zone des deux cotes)."""
    ABILITY_ID = int(ActiveAbilityType.TheLantern)   # 1094
    MIN_UTILITY = _W_ENEMY        # `Bucket(0, Nullable(<statics+0x00>))` -- LA MEME constante
    PRIORITY = 0

    # ------------------------------------------------------------------ gate AMONT (slot 4)
    def should_evaluate(self, ctx: NCContext) -> bool:
        """`...TheLanternPlaybook$$ShouldEvaluate(unit)` = `<IBattleQuery slot 0x1b>(unit, 2)` =
        `IdunBattle.Core.Services.BattleQuery$$HasMinimumRemainingTurns(unit, 2)`.

        Le mirror du corps natif vit dans `engine.services.battle_query` (foyer UNIQUE, pose par
        `CasterHas2TurnsLeft` #287-r11-r1-r1) -- on l'APPELLE, on n'en ecrit pas un second.

        ⚠ Le parametre `unit` n'est PAS lu par le natif (le corps ne consulte que le plafond de
        rounds de la BC et le compteur de tours termines).

        ⚠ #1027-r5 -- ce site lisait `getattr(ctx, "state", None)`, un attribut que `NCContext` n'a
        JAMAIS porte : il valait toujours `None`, et le foyer retombait donc invariablement sur son
        defaut derive de `data/seed-bc.json`. Le substrat passe desormais par
        `_base.has_minimum_remaining_turns`, qui transporte les DEUX entrees du natif en tri-etat.
        Meme correction, meme regime que `SolarAtomizerPlaybook.should_evaluate`."""
        return NCB.has_minimum_remaining_turns(ctx, CASTER_MIN_REMAINING_TURNS)

    # ------------------------------------------------------------------ la ZONE
    @staticmethod
    def _ring(ctx: NCContext, centers, radius: int, exclude_main) -> set:
        """`DSLSelectors$$SurroundingTiles(origin, includeCenter = 0, range, onlyMovable = 0,
        includeNonWalkable = 0)` -- transpose en geometrie de DECISION.

        `centers` = l'empreinte de l'origine (`IterateTiles`), `exclude_main` = la MAIN TILE seule
        (`op_Subtraction Tiles(origin)` du natif ne retranche QUE celle-la, pas les pieds
        secondaires). Les DEUX filtres de `TileUtil$$IsTileValidForList` sont appliques dans l'ordre
        natif : le MUR d'abord (INCONDITIONNEL), puis la marchabilite (armee parce que
        `includeNonWalkable == 0`). Un substrat absent laisse la tuile passer -- meme degradation
        conservatrice que le noeud runner."""
        out = set()
        for c in centers:
            for p in hexgeo.disk(c[0], c[1], radius):
                if ctx.elev_by_pos is not None and p not in ctx.elev_by_pos:
                    continue                                   # hors board
                if (ctx.is_wall_by_pos or {}).get(p):
                    continue                                   # `tileComponent+0x41` -- INCONDITIONNEL
                w = (ctx.walkable_by_pos or {}).get(p)
                if w is False:
                    continue                                   # `checkWalkable = (incl == 0)`
                out.add(p)
        return out - set(exclude_main or ())

    def _measured_feet(self, ctx: NCContext) -> list:
        """Les pieds du caster A L'ORIGINE, LUS dans `obs_units` (une ligne par pied). Liste vide
        = le substrat ne publie qu'une ligne, donc rien de multi-hex n'est MESURE."""
        feet = [(u["pos"]["col"], u["pos"]["row"])
                for u in (ctx.obs_units or [])
                if u.get("id") == ctx.uid and isinstance(u.get("pos"), dict)
                and u["pos"].get("col") is not None]
        return list(dict.fromkeys(feet)) if len(feet) > 1 else []

    def _caster_footprint(self, ctx: NCContext, position: tuple) -> list:
        """`<DSLSelectors+0x58> = CasterTiles` -- l'EMPREINTE du caster a la position balayee.

        #1030-r2 -- CE N'EST PAS UNE TRANSLATION D'OFFSETS, ET C'EST LU.
        `IdunBattle.Core.Services.MovementQuery$$GetPossibleTileListsFromMovableTiles(movableTiles,
        numFeet)` branche sur le NOMBRE DE PIEDS et, pour `7`, fait exactement :

            foreach (t in movableTiles) {
                adj = <IBattleQuery slot 0x4f = GetAdjacentTiles>(t, 0, 1, 1);
                if (movableTiles.ContainsAll(adj)) {
                    set = new OrderedSet<Tile>(); set.Add(t); set.AddRange(adj);
                    result.Add(set);
                }
            }

        L'empreinte d'une `UnitPosition` a sept pieds est donc `{t} U GetAdjacentTiles(t)` --
        centre PUIS ring-1, RECALCULE a chaque position. L'ORDRE est celui du natif (`Add` avant
        `AddRange`), et il porte : `target_area` retranche `feet[:1]`, c'est-a-dire la MAIN TILE.
        (`numFeet == 1` -> `GetKCombs(.., 1)`, `== 3` -> `GetKCombs(.., 3)`, tout autre -> `null`.)

        Le ring-1 est celui de `GetAdjacentTiles(t, onlyEmptyOrSteppable: 0, onlyWalkableTiles: 1,
        allowTemporary: 1)` : liste STOCKEE des voisins + porte d'elevation `|dElev| < 2`
        INCONDITIONNELLE (`TileQuery.<IterateAdjacentTiles>d__8$$MoveNext`), filtre `IsWalkable`
        ARME, temporaires AUTORISEES, occupation NON filtree. C'est exactement le foyer
        `battle_query.is_adjacent` -- surtout pas `hexgeo.disk`, qui n'a pas de porte d'elevation
        (c'est `SurroundingTiles` qui n'en a pas, cf. `_ring`).

        ⚠ RESIDU QUI RESTE (`#1079-r1`) : le natif ECARTE une position dont les six voisines ne
        sont pas TOUTES dans `movableTiles` (`ContainsAll`). Le port balaie `ctx.reach_nc`, que le
        bridge construit par flood-fill SANS ce filtre -- il evalue donc des positions que le natif
        n'aurait pas produites (ecart PERMISSIF, dans le sens qui ajoute des candidates). Le
        corriger touche `action_tiles_for`, foyer PARTAGE par tous les NonComparable.

        Nombre de pieds NON MESURE (substrat mono-ligne) -> `[position]`, le comportement d'avant :
        le port n'INVENTE pas une empreinte a sept tuiles pour une unite dont il ignore la taille."""
        feet = self._measured_feet(ctx)
        if len(feet) != _CASTER_FEET_COUNT:
            return [position]            # `numFeet` hors du cas 7 -> aucune reconstruction
        if ctx.origin is not None and position == ctx.origin:
            return feet                  # a l'origine, la MESURE fait autorite sur la derivation
        neigh = bq.neigh_map(ctx)
        ring = [p for p in ((neigh or {}).get(position) or [])
                if bq.is_adjacent(position, p, ctx.elev_by_pos, neigh)
                and (ctx.walkable_by_pos or {}).get(p) is not False]
        return [position] + list(dict.fromkeys(ring))

    def target_area(self, ctx: NCContext, position: tuple, tile: tuple) -> set:
        """`...TheLanternAbility$$GetTilesForTargetAreaFromTargetTile()` -- MIRROR de la chaine :

            Unique( (Target + SurroundingTiles(Target,1)) + (SurroundingTiles(Target,2)
                    op_BitwiseAnd SurroundingTiles(CasterTiles,1)) )
        """
        feet = self._caster_footprint(ctx, position)
        ring1 = self._ring(ctx, [tile], 1, [tile])
        ring2 = self._ring(ctx, [tile], 2, [tile])
        cring1 = self._ring(ctx, feet, 1, feet[:1])
        return {tile} | ring1 | (ring2 & cring1)

    # ------------------------------------------------------------------ l'UTILITE
    def _enemies_hit_utility(self, ctx: NCContext, area: set) -> float:
        """`...TheLanternPlaybook$$GetEnemiesHitUtilityForTarget` -- cf. l'en-tete.

        L'ORDRE des deux `FilterInPlace` est LOAD-BEARING : le second filtre la liste DEJA reduite
        aux ennemis, donc `n2` compte les ennemis PSYKER, pas tous les psykers de la zone."""
        team = None
        for u in (ctx.obs_units or []):
            if u.get("id") == ctx.uid:
                team = u.get("teamId")
                break
        n1 = n2 = 0
        vus = set()
        for u in (ctx.obs_units or []):
            p = u.get("pos")
            if not isinstance(p, dict) or p.get("col") is None:
                continue
            if (p["col"], p["row"]) not in area or u.get("id") in vus:
                continue
            if u.get("isDead") or u.get("alive") is False:
                continue                                   # `selectionType = 3` : OnlyAlive...
            if u.get("isUntargetable"):
                continue                                   # ... AndTargetable
            if team is not None and u.get("teamId") == team:
                continue                                   # `IsEnemy(u, caster, state)` -- b__0
            vus.add(u.get("id"))
            n1 += 1
            scene = getattr(ctx, "scene", None)
            uctx = scene.ctx(u.get("id")) if scene is not None else None
            if has_any_trait(entity_trait_names(uctx, u.get("visualId")), (_PSYKER.name,)):
                n2 += 1                                    # `HasTrait(u, 0x3ea)` -- b__5_1
        return n1 * _W_ENEMY + n2 * _W_PSYKER

    # ------------------------------------------------------------------ le sweep
    def _eligible_target_tiles(self, ctx: NCContext) -> list:
        """`BasePlaybook$$GetEligibleTargetsSelectable` : union `abilityTargets` kind=tile (le cast
        est TILE-TARGET, `TargetIsTile` du masque), ordre PRESERVE -- meme voie qu'`ItItches`."""
        if ctx.ability_targets is None:
            return []
        at = ctx.ability_targets(ctx.uid, self.ABILITY_ID) or {}
        out = []
        for u in (at.get("units") or []):
            for a in (u.get("abilities") or []):
                if a.get("abilityId") != self.ABILITY_ID:
                    continue
                for t in (a.get("targets") or []):
                    tl = t.get("tile") if t.get("kind") == "tile" else None
                    if tl and tl.get("col") is not None:
                        out.append((tl["col"], tl["row"]))
        return list(dict.fromkeys(out))

    def generate_candidates(self, ctx: NCContext) -> list:
        """Mirror d'`EvaluateNonComparable` : sweep des positions (origine EN TETE, cf.
        `_sweep_origin_first`), puis des cibles eligibles ; gate `|zone| >= 7` ; `Bucket.AddAction`
        SEEDE le premier ajoute et ne remplace QUE si STRICTEMENT superieur -> au tie d'utilite, la
        PREMIERE position de l'ordre natif gagne, c'est-a-dire l'ORIGINE."""
        tiles = self._eligible_target_tiles(ctx)
        if not tiles:
            return []
        best = None                              # (util, position, tuile cible)
        for P in _sweep_origin_first(ctx):
            for T in tiles:
                area = self.target_area(ctx, P, T)
                if len(area) < _MIN_TILES_HIT:   # `if (!(Fix64(n) < Fix64(7)))`
                    continue
                util = self._enemies_hit_utility(ctx, area)
                if best is None or util > best[0]:
                    best = (util, P, T)
        if best is None or best[0] < self.MIN_UTILITY:
            return []
        util, P, T = best
        return [{"target": ctx.tile_id_by_pos.get(T), "ability": self.ABILITY_ID,
                 "to": (P if P != ctx.origin else None), "pred": util}]
