"""`DutyEternalPlaybook` (1158, `ultraDreadnought` -- MACHINE OF WAR) -- face DECISION.

Ferme le residu `#970-r5`. Sa fiche annoncait `BLOCAGE: etage` : l'adaptateur `NCContext -> board`
qu'exige `ThreeTileUnitSpawnShape` n'existait pas. Il existe depuis #978 (`CtxBoard`, ecrit pour
`AetherStride`) -- et ce sont les DEUX SEULES xrefs du selecteur dans le build, donc le partager
etait la seule reponse juste. Il a ete DEPLACE dans `_targets.py` par cette tranche.

BASE LUE, JAMAIS DEDUITE DU `.ctor`
-----------------------------------
`data/symbols/<build>/frida/classes.tsv` :

    IdunBattle.AI.Playbook.Loki.DutyEternalPlaybook | 112 | IdunBattle.AI.Playbook.NonComparablePlaybook`1

LE CORPS, TERME A TERME
------------------------
`IdunBattle.AI.Playbook.Loki.DutyEternalPlaybook$$EvaluateNonComparable`, lu verbatim :

    bucket = new Bucket<UnitAction>(0, Nullable(<premier statique de la classe>))
    foreach entities in BasePlaybook.GetEligibleTargetsSelectable(caster, casterPosition.MainTile):
        util = Fix64.op_Implicit(1)
        area = DutyEternalAbility.GetTargetAreaTiles(this.ability@+0x68).SelectTiles(entities)
        foreach t in area:
            foreach u in battleQuery.<slot 0x75 = 117>(t, 2, friendsOf: null, includeCenter: false):
                util += Fix64.op_Implicit( battleQuery.<slot 0x6c = 108>(u, t) < 2 ? 10 : 1 )
        bucket.AddAction(BasePlaybook.GenerateAction(casterPosition, entities.<+0x10 = target>, util))
    return bucket

`IdunBattle.AI.Playbook.Loki.DutyEternalPlaybook$$.cctor` : `<statique> = Fix64.op_Implicit(1)`
-> `MIN_UTILITY = 1`. Un seul ecrivain (`NonComparablePlaybook`1$$.cctor` N'EXISTE PAS dans le
build -- recherche de symboles VIDE), donc pas d'ecrasement a `Fix64(10)` comme dans la famille
COMPARABLE `static_threshold_gate`.

`IdunBattleLogic.Entities.Abilities.Active.Loki.DutyEternalAbility$$GetTargetAreaTiles` :

    return DSLSelectors.ThreeTileUnitSpawnShape(dsl, <DSLSelectors+0x60 = Target>)

-> l'empreinte a TROIS pieds, ancree sur la TUILE VISEE (jamais sur le caster), MEME artefact que
`AetherStride` -- foyer `engine.services.spawn_tile_shape.get_area`.

LES DEUX SLOTS, ET CE QUE LE 4e ARGUMENT CHANGE
------------------------------------------------
Slots LUS dans `data/symbols/<build>/metadata/interface_slots.tsv` (`IBattleQuery 117
GetSurroundingUnits 4`, `IBattleQuery 108 GetDistance 2`), jamais devines.

`IdunBattle.Core.Services.BattleQuery$$GetSurroundingUnits(from, range, friendsOf, includeCenter)`,
lu verbatim, et TROIS lectures y comptent :

  1. **`includeCenter = false`** -- l'appel passe `(t, 2, 0, 0)`. `IterateSurroundingTiles` EXCLUT
     donc `t` elle-meme. Une unite DEBOUT SUR `t` n'est pas comptee du tout, et par consequent la
     branche `distance < 2` ne peut valoir que `distance == 1` : le `10` est le bonus des
     unites ADJACENTES, jamais celui d'un occupant. Prendre `includeCenter = true` aurait ajoute
     un `+10` fantome par tuile occupee de l'empreinte.
  2. **`friendsOf = null`** -- AUCUN filtre de camp : le natif compte les ennemis ET les allies.
     `IsEnemy` n'est appele que si `friendsOf != null`. C'est ce qui distingue ce corps d'un
     comptage d'ennemis, et ca change le signe tactique : le Dreadnought prefere debarquer la ou
     il y a du MONDE, pas la ou il y a des cibles.
  3. **`OrderedSet`** -- distincts PAR APPEL, donc par tuile `t` de l'empreinte. Une unite voisine
     de DEUX tuiles de l'empreinte est comptee DEUX FOIS (une par appel), et c'est voulu : le
     natif accumule dans `util` a chaque iteration de la boucle externe.

Le disque est celui d'`IdunBattle.Core.Services.TileQuery.u003CIterateSurroundingTilesu003Ed__6
$$MoveNext` -- **AUCUNE porte d'elevation** (4e argument d'`IsTileValidForList` = `0`), contrairement
au ring-1 d'`IterateAdjacentTiles`. Le port passe donc par `battle_query.get_surrounding_tiles`,
le foyer qui porte deja ce quirk, et non par `is_adjacent`.

CE QUI N'EST PAS PORTE ICI, ET C'EST DIT
-----------------------------------------
* `GetUseProbability(unit, actionTiles)` =
  `Fix64.FromIntFraction((GetTurnsFinished(unit) - GetNumberConstant(0x68 = initialCooldownTurns)
  + 1) * 33, 100)` -- une RAMPE. `<= 0` refuse, `>= 1` accepte, entre les deux c'est un TIRAGE que
  le moteur deterministe du port ne peut pas reproduire. `should_evaluate` reste `True` : c'est
  l'ECART DEJA ASSUME par `NonComparablePlaybook` pour tous les `GetUseProbability` probabilistes
  (`BlackRage` 0.4, `ItItches`, `EmpyricAmbush` 0.5). Ses deux EXTREMITES sont deterministes et
  portables -- residu `#979-r1`.
* L'occupation lue par le port est `ctx.epos + ctx.fpos` (le foyer `_targets.occupied`), donc le
  CASTER en est exclu. Inerte ici : le porteur est une MoW sans `PositionComponent`.

VOIE D'ENUMERATION -- TILE-TARGETED, donc PAS le plan
------------------------------------------------------
`GetEligibleTargetsSelectable(caster, casterPosition.MainTile)` -- l'overload TUILE. Cote port,
`eligible_target_tiles` (`abilityTargets(uid, 1158).fromHere`, `kind == "tile"`), la MEME voie que
`TitanhammerSquad` et `AetherStride`. Le porteur est une MoW : `ctx.reach_nc` est VIDE, donc
l'ecart « `fromHere` n'enumere que depuis l'origine » est structurellement inerte.
"""
from __future__ import annotations

from engine import battle_query as bq
from engine.entities.active_ability_type import ActiveAbilityType
from engine.services import spawn_tile_shape as STS

import engine.playbook.noncomparable._targets as TGT      # FORME B, ABSOLU (#962)
from ._base import NCContext, NonComparablePlaybook, eligible_target_tiles


class DutyEternalPlaybook(NonComparablePlaybook):
    """`IdunBattle.AI.Playbook.Loki.DutyEternalPlaybook$$EvaluateNonComparable` -- utilite =
    `1 + Somme sur les 3 tuiles de l'empreinte, sur les unites (DES DEUX CAMPS) a <= 2 tuiles,
    de 10 si adjacente sinon 1`."""

    ABILITY_ID = int(ActiveAbilityType.DutyEternal)   # 0x486 = 1158
    #: `.cctor` : `Fix64.op_Implicit(1)` -> le `minUtility` du `Bucket` (gate `AddAction`).
    MIN_UTILITY = 1.0
    #: `Fix64.op_Implicit(1)` POSE AVANT la boucle -- plancher, pas un compte nu (contraste avec
    #: `AetherStride`, dont l'utilite part de `Fix64(0)` et devient donc un VETO).
    BASE_UTILITY = 1.0
    PRIORITY = 0        # hors `NATIVE_PRIORITY` (defaut `AbilityPriority.Normal`, sweep #170)

    #: `GetSurroundingUnits(t, 2, null, false)` -- le 2 est le LITTERAL du call-site.
    SURROUNDING_RANGE = 2
    #: `GetDistance(u, t) < 2` -- STRICT. Avec `includeCenter = false`, seule `distance == 1` y
    #: entre : le bonus est celui des unites ADJACENTES.
    NEAR_DISTANCE = 2
    NEAR_UTILITY = 10.0
    FAR_UTILITY = 1.0

    def _area(self, ctx: NCContext, anchor: tuple) -> list:
        """`ThreeTileUnitSpawnShape(Target).Select(entities)` = l'empreinte a 3 pieds ancree sur la
        tuile visee, ou `[]` si aucune des six directions ne porte d'aire valide.

        MEME foyer que `AetherStride` (`spawn_tile_shape.get_area` + l'adaptateur `CtxBoard`) : ce
        sont les deux seules xrefs natives du selecteur, elles ne peuvent pas diverger."""
        return STS.get_area(TGT.CtxBoard(ctx), TGT.occupied(ctx), anchor)

    def _units_by_pos(self, ctx: NCContext) -> dict:
        """`UnitExtensions.GetUnit(tile, state)` en domaine POSITION, DES DEUX CAMPS.

        `friendsOf = null` au call-site -> le natif n'appelle jamais `IsEnemy` : allies ET ennemis
        comptent. Substrat = `ctx.epos` + `ctx.fpos`, les deux canaux d'occupation de `NCContext`
        (le meme couple que `_targets.occupied`, dont l'ecart -- caster exclu -- est nomme au
        foyer)."""
        out = {}
        for src in (ctx.epos or [], ctx.fpos or []):
            for p in src:
                if p and p[0] is not None:
                    out[(p[0], p[1])] = True
        return out

    def evaluate_non_comparable(self, tile, target, ctx: NCContext):
        """`Fix64(1) + Somme_{t in area} Somme_{u in GetSurroundingUnits(t, 2, null, false)}
        (10 si GetDistance(u, t) < 2 sinon 1)`.

        `target` est une POSITION de tuile `(col, row)` (`eligible_target_tiles`), pas un id
        d'unite. `tile` n'entre PAS dans la formule : l'ancre est la tuile visee.

        Empreinte VIDE (canal muet, ou aucune des six directions valide) -> l'utilite se reduit au
        plancher `1`, ce qui est EXACTEMENT ce que le natif rendrait sur une aire vide. Le refus,
        lui, vient du gate `minUtility` du `Bucket`, qui laisse passer `1` : le port ne REFUSE donc
        rien de plus que le natif."""
        if target is None:
            return None
        area = self._area(ctx, (target[0], target[1]))
        occ = self._units_by_pos(ctx)
        walk = ctx.walkable_by_pos or {}
        util = self.BASE_UTILITY
        for t in area:
            # `IterateSurroundingTiles(t, 2, includeCenter: false)` -- disque cube SANS porte
            # d'elevation (4e argument d'`IsTileValidForList` = 0), foyer `get_surrounding_tiles`.
            for q in bq.get_surrounding_tiles(
                    t, radius=self.SURROUNDING_RANGE, include_center=False,
                    walkable_at=(lambda p: bool(walk.get(p, True))),
                    tile_exists=(lambda p: p in walk) if walk else None):
                if not occ.get((q[0], q[1])):
                    continue                          # `GetUnit(tile)` nul -> l'element est saute
                d = bq.get_distance([t], [q])
                util += self.NEAR_UTILITY if d < self.NEAR_DISTANCE else self.FAR_UTILITY
        return util

    def generate_candidates(self, ctx: NCContext) -> list[dict]:
        """`ActiveAbilityActionGenerator` + `Bucket$$ChooseAction` pour une ability TILE-TARGETED.

        L'ordre de `fromHere` EST celui du selecteur natif ; `Bucket$$AddAction` ne remplace que sur
        amelioration STRICTE, donc a utilite egale la PREMIERE tuile gagne."""
        from_here, _union = eligible_target_tiles(ctx, self.ABILITY_ID)
        best = None                                        # (tuile, utilite)
        for tpos in from_here:
            util = self.evaluate_non_comparable(ctx.origin, tpos, ctx)
            if util is None or util < self.MIN_UTILITY:
                continue                                   # gate `minUtility` du `Bucket`
            if best is None or util > best[1]:             # STRICT -> keep-first au tie
                best = (tpos, util)
        if best is None:
            return []
        if ctx.debug:
            import sys
            print("    [dbg NC u%s] DutyEternal tile=%s util=%s"
                  % (ctx.uid, best[0], best[1]), file=sys.stderr)
        return [{"target": best[0], "ability": self.ABILITY_ID, "to": None, "pred": best[1]}]


__all__ = ["DutyEternalPlaybook"]
