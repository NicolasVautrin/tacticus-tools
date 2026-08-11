"""AlphaWarriorPlaybook (1112, `tyranWingedPrime`) -- face DECISION (#945).

Base `NonComparablePlaybook`1` -- LUE dans `data/symbols/<build>/frida/classes.tsv`.

LE CORPS, TERME A TERME
------------------------
`IdunBattle.AI.Playbook.Loki.AlphaWarriorPlaybook$$EvaluateNonComparable` (0x458 = 1112) :

    bucket = new Bucket<UnitAction>(0, Nullable(<statics+0x00>))       # `.cctor` : Fix64(1)
    if (this.ability@+0x68 == null) throw
    summonId = <AlphaWarriorAbility>$$GetSummonId(this.ability)        # corps DEDUPLIQUE, etiquete
                                                                      # `SporeMineLauncherAbility$$GetSummonId`
    foreach entities in BasePlaybook.GetEligibleTargetsSelectable(caster,
                                                                 casterPosition.get_MainTile()):
        b = battleQuery.<slot itf 195>(caster, summonId, entities@+0x10)
        bucket.AddAction(BasePlaybook.GenerateAction(casterPosition, entities@+0x10,
                                                     Fix64.op_Implicit(b ? 1 : 0)))

et `IdunBattle.AI.Playbook.Loki.AlphaWarriorPlaybook$$.cctor` = `Fix64.op_Implicit(1)` -> le
statique qui sert de `minUtility` au Bucket. **`MIN_UTILITY = 1` et l'utilite vaut 0 ou 1** : le
gate `AddAction` (`util >= min`) transforme donc le booleen en VETO. Une tuile depuis laquelle le
Warrior invoque n'aurait aucune cible n'est jamais proposee -- c'est tout le playbook.

Le slot **195 = 0xc3** est `HasSummonTargetInAttackRangeAtTile` (3 params) --
`data/symbols/<build>/metadata/interface_slots.tsv`, pas une deduction de nom. Son corps
(`IdunBattle.Core.Services.BattleQuery$$HasSummonTargetInAttackRangeAtTile`) :

    if (EntityExtensions.IsMachine(parent))
        return HasSummonTargetInAttackRangeAtTileWithMachineParent(parent, unitId, tile)
    nearest = GetNearestEnemy(parent, position: Nullable(new UnitPosition(tile)))
    return IsTargetInAttackRangeForSummon(parent, unitId, tile, nearest)

`IdunBattle.Core.Services.BattleQuery$$GetNearestEnemy(caster, position)` -- la `position` fournie
REMPLACE celle du caster (`if (position.HasValue) tilesA = position.Value else tilesA =
GetUnitPosition(caster)`), donc les distances sont mesurees DEPUIS LA TUILE DE SPAWN :

    best = null ; bestDist = int.MaxValue ; bestAdj = false
    foreach u in GetAllAliveUnits(null):
        if (!UnitExtensions.IsEnemy(caster, u, state)) continue
        if (UnitExtensions.IsIrrelevantObject(u)) continue
        d   = GetDistance(tilesA, u) ; adj = AreEntitiesAdjacent(tilesA, u)
        if (d < bestDist || (adj && !bestAdj)) { best = u ; bestDist = d ; bestAdj = adj }
    return best

`IdunBattle.Core.Services.BattleQuery$$IsTargetInAttackRangeForSummon(parent, unitId, tile, target)` :

    if (target == null || !UnitExtensions.IsTargetable(target)) return false
    range = 0
    foreach w in GetUnitConfig(unitId).weapons:  range = Math.Max(range, w.Range ?? 1)
    if (DamageCalculations.ShouldApplyRangedInMelee(parent, [tile], state, true)) {
        range = 1 ; if (!TileExtensions.IsAdjacentTo(tile, GetTiles(target))) return false
    } else if (range == 1) {
        if (!TileExtensions.IsAdjacentTo(tile, GetTiles(target))) return false
    }
    if (GetDistance(tile, target) > range) return false
    foreach t in GetTiles(target):
        if (!SetExtensions.IsNullOrEmpty(movementQuery.<slot itf 16>(tile, t, 6, 2))) return false
    if (range == 1 && !DamageCalculations.CanMeleeAttackOverElevationDifference(tile,
                                                    GetMainTile(target))) return false
    return true

Le slot **16 d'`IMovementQuery` est `GetTilesObscuringTerrain`** (4 params, meme table) : c'est un
test de LIGNE DE VUE, et un resultat NON VIDE fait echouer. Mask `6` = elevation + murs, seuil `2`
-- exactement les arguments que mirrore deja `battle_query.is_target_tile_obscured` (foyer partage,
aucun fork).

TROIS BRANCHES INERTES POUR CE PORTEUR, et c'est MESURE, pas suppose
---------------------------------------------------------------------
* `ShouldApplyRangedInMelee` est gate sur `HasTrait(attaquant, 0xb = UnitTrait.Ranged)`, trait
  qu'AUCUNE unite ne porte (0 dans gameconfig ET dans `BC.Units[].Traits`) -- mesure deja etablie
  et documentee par `playbook.prediction._shared._should_apply_ranged_in_melee`. La branche ne
  peut donc pas s'activer.
* `range == 1` : `tyranSmnWarrior` (le `unitId` constant de 1112) porte deux armes, l'une sans
  `Range` (melee -> 1) et l'autre `Range: 2` -> `Max` = **2**. Les deux gates `range == 1`
  (`IsAdjacentTo` et `CanMeleeAttackOverElevationDifference`) sont donc morts ici. Ils restent
  ECRITS dans `_is_target_in_attack_range_for_summon` : ils vivront si un autre porteur entre.
* `IsMachine(parent)` : `tyranWingedPrime` est une unite, pas une MACHINE OF WAR. La branche
  `...WithMachineParent` n'est pas portee -- residu `#945-r1`, nomme et non contourne.

VOIE D'ENUMERATION -- CIBLE TUILE
----------------------------------
Le 3e argument du slot 195 est un TILE, et `GenerateAction` emet cette meme entite : la cible de
1112 est une TUILE de spawn. Voie employee, la MEME que `DarkTalonStrikePlaybook` :
`abilityTargets(uid, 1112).fromHere` filtre sur `kind == "tile"`, puis `ctx.tile_id_by_pos` pour
l'id d'entite-tuile. Ecart NOMME (identique) : `fromHere` n'enumere que depuis l'ORIGINE.

LE GATE `ShouldEvaluate`, ET IL EST DEJA PORTE
----------------------------------------------
`IdunBattle.AI.Playbook.Loki.AlphaWarriorPlaybook$$ShouldEvaluate` est le corps FOLDE (COMDAT,
refcount 7) `GetStat(unit, 0xc = TurnsStarted) > 1` -- il ne figure PAS dans `frida/methods.tsv`
(corps partage, un seul proprietaire par RVA), et c'est precisement cette classe qui le NOMME.
Le port l'a deja sous `_base._turns_started_gate`, dont la docstring cite les vtables resolues
LIVE (#46) : TheQuickening(1151), HeroicFusillade(1180), VigilanceEternal(1202) **et
AlphaWarrior**. `AlphaWarriorPlaybook` n'evalue donc JAMAIS au premier tour de son porteur.
"""
from __future__ import annotations

import gameconfig as _gc
import hexgeo

from engine import battle_query as bq
from engine.entities.active_ability_type import ActiveAbilityType

from ._base import NCContext, NonComparablePlaybook, _turns_started_gate, _unit_cfg

#: `AbilityConfiguration` de 1112 : `constants.unitId` = l'unite que le natif passe au slot 195.
#: LU dans le gameconfig, jamais code en dur ici (`AlphaWarriorAbility$$GetSummonId` est le corps
#: DEDUPLIQUE etiquete `SporeMineLauncherAbility$$GetSummonId` : il lit cette meme constante).
_CONST_SUMMON_ID = "unitId"

#: `GetTilesObscuringTerrain(tile, t, 6, 2)` -- mask 6 (elevation + murs) et seuil 2, les MEMES
#: arguments que `battle_query.is_target_tile_obscured` porte deja.
_OBSCURE_MASK = 6


def _summon_id(ability_id: int) -> str | None:
    """`<AlphaWarriorAbility>$$GetSummonId(ability)` = `constants.unitId` de la config."""
    name = ActiveAbilityType(int(ability_id)).name
    cfg = _gc.ability(name) or {}
    v = (cfg.get("constants") or {}).get(_CONST_SUMMON_ID)
    return str(v) if v else None


def _summon_attack_range(summon_id: str | None) -> int | None:
    """`foreach w in GetUnitConfig(unitId).weapons: range = Max(range, w.Range ?? 1)`.

    ⚠ Le `?? 1` est LU : une arme de melee (pas de `Range`) compte pour **1**, pas pour 0. Une
    unite sans aucune arme rendrait `range = 0` cote natif ; ici, config introuvable -> `None`,
    que l'appelant traduit en « non mesure » plutot qu'en 0 (qui refuserait tout)."""
    if not summon_id:
        return None
    cfg = _unit_cfg(summon_id)
    weapons = cfg.get("weapons")
    if not weapons:
        return None
    return max(int(w.get("Range") or 1) for w in weapons)


class AlphaWarriorPlaybook(NonComparablePlaybook):
    """`IdunBattle.AI.Playbook.Loki.AlphaWarriorPlaybook$$EvaluateNonComparable` -- utilite
    BOOLEENNE (`Fix64(1)` / `Fix64(0)`) : le summon invoque sur cette tuile aurait-il une cible
    d'attaque a portee ? `MIN_UTILITY = 1` (le `.cctor`) en fait un VETO."""
    ABILITY_ID = int(ActiveAbilityType.AlphaWarrior)   # 0x458 = 1112
    MIN_UTILITY = 1.0   # `AlphaWarriorPlaybook$$.cctor` : `Fix64.op_Implicit(1)` -> statics+0x00
    PRIORITY = 0        # hors `NATIVE_PRIORITY` (defaut `AbilityPriority.Normal`, sweep #170)

    def should_evaluate(self, ctx: NCContext) -> bool:
        """Slot 4 = le corps FOLDE `AlphaWarriorPlaybook$$ShouldEvaluate` :
        `GetStat(unit, 0xc = TurnsStarted) > 1` -- l'ability n'est jamais evaluee au PREMIER tour
        de son porteur. Foyer partage `_base._turns_started_gate` (aucune copie locale)."""
        return _turns_started_gate(ctx)

    def _nearest_enemy(self, ctx: NCContext, frm: tuple):
        """`BattleQuery$$GetNearestEnemy(caster, position: <la tuile de spawn>)` -- rend
        `(id, position)` ou `None`.

        Le tie-break natif n'est PAS un simple `min` : `d < bestDist || (adj && !bestAdj)`. Un
        candidat ADJACENT evince donc un candidat plus proche non adjacent -- configuration
        impossible en distance hex (adjacent => d == 1 == minimum), mais le natif l'ecrit et le
        port le transcrit tel quel. `AreEntitiesAdjacent` (court-circuit d'identite + porte
        d'elevation, cf. #433-r1) et non `is_adjacent` : c'est ce corps-la que le natif appelle.

        `IsIrrelevantObject` n'est pas porte : `ctx.epos`/`ctx.enemies` ne publient pas le trait
        `Object`. Ecart PERMISSIF nomme (un decor pourrait etre elu « plus proche ennemi »)."""
        neigh = bq.neigh_map(ctx)
        best = None            # (id, pos, dist, adj)
        for e in (ctx.enemies or []):
            p = e.get("pos") or {}
            if p.get("col") is None:
                continue
            q = (p["col"], p["row"])
            d = hexgeo.distance(frm, q)
            adj = bq.are_entities_adjacent(frm, q, ctx.elev_by_pos, neigh)
            if best is None or d < best[2] or (adj and not best[3]):
                best = (e.get("id"), q, d, adj)
        return None if best is None else (best[0], best[1])

    def _is_target_in_attack_range_for_summon(self, ctx: NCContext, tile: tuple,
                                              rng: int | None, target_pos) -> bool:
        """`BattleQuery$$IsTargetInAttackRangeForSummon(parent, unitId, tile, target)`, etage par
        etage (cf. l'en-tete pour le corps natif complet et les trois branches inertes).

        `GetTiles(target)` = la seule tuile principale pour une unite mono-tuile (les seules
        multi-tuiles sont les plateformes de MoW, jamais elues ici)."""
        if target_pos is None:
            return False                       # `target == null` (et `IsTargetable` non porte :
            #                                     `ctx.enemies` ne publie que des unites vivantes)
        if rng is None:
            return False                       # portee non mesurable -> le port ne devine pas
        if rng == 1 and not bq.is_adjacent(tile, target_pos, ctx.elev_by_pos, bq.neigh_map(ctx)):
            return False                       # `range == 1 -> IsAdjacentTo(tile, GetTiles(target))`
        if hexgeo.distance(tile, target_pos) > rng:
            return False                       # `GetDistance(tile, target) > range`
        # `movementQuery.GetTilesObscuringTerrain(tile, t, 6, 2)` NON VIDE -> refus.
        if bq.is_target_tile_obscured(tile, target_pos, ctx.elev_by_pos):
            return False
        # `range == 1 && !CanMeleeAttackOverElevationDifference(...)` : INERTE pour `tyranSmnWarrior`
        # (range 2). Ecrit pour ne pas disparaitre si un autre porteur entre -- meme porte |d|<2.
        if rng == 1 and ctx.elev_by_pos:
            ef, et = ctx.elev_by_pos.get(tile), ctx.elev_by_pos.get(target_pos)
            if ef is not None and et is not None and abs(ef - et) >= 2:
                return False
        return True

    def has_summon_target_in_attack_range_at_tile(self, ctx: NCContext, tile: tuple) -> bool:
        """`IBattleQuery` slot 195 -- l'utilite booleenne, en clair.

        La branche `IsMachine(parent)` (`...WithMachineParent`) n'est pas portee : le porteur
        connu de 1112 n'est pas une MoW (residu `#945-r1`)."""
        rng = _summon_attack_range(_summon_id(self.ABILITY_ID))
        near = self._nearest_enemy(ctx, tile)
        if near is None:
            return False
        return self._is_target_in_attack_range_for_summon(ctx, tile, rng, near[1])

    def generate_candidates(self, ctx: NCContext) -> list[dict]:
        """`ActiveAbilityActionGenerator` + `Bucket$$ChooseAction` pour une cible TUILE.

        L'utilite ne vaut que 0 ou 1 et `MIN_UTILITY` vaut 1 : toutes les tuiles retenues sont a
        EGALITE, donc `AddAction` (remplacement STRICT) garde la PREMIERE de l'enumeration native
        -- d'ou l'arret des la premiere tuile qui passe."""
        if ctx.ability_targets is None:
            return []
        at = ctx.ability_targets(ctx.uid, self.ABILITY_ID) or {}
        for u in (at.get("units") or []):
            if u.get("unitId") != ctx.uid:
                continue
            for a in (u.get("abilities") or []):
                if a.get("abilityId") != self.ABILITY_ID:
                    continue
                for t in (a.get("fromHere") or []):
                    tl = t.get("tile")
                    if t.get("kind") != "tile" or not tl or tl.get("col") is None:
                        continue
                    pos = (tl["col"], tl["row"])
                    if not self.has_summon_target_in_attack_range_at_tile(ctx, pos):
                        continue               # util 0 < MIN_UTILITY 1 -> jamais dans le bucket
                    tile_id = (ctx.tile_id_by_pos or {}).get(pos)
                    if tile_id is None:
                        continue               # pas d'entite-tuile -> cible inemissible
                    if ctx.debug:
                        import sys
                        print("    [dbg NC u%s] AlphaWarrior tile=%s tileId=%s"
                              % (ctx.uid, pos, tile_id), file=sys.stderr)
                    return [{"target": tile_id, "ability": self.ABILITY_ID,
                             "to": None, "pred": self.MIN_UTILITY}]
        return []
