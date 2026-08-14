"""ItItchesPlaybook — poussee NonComparable (utilite = #ennemis affectes par la poussee)."""
from __future__ import annotations

from engine import battle_query as bq
from engine.entities.active_ability_type import ActiveAbilityType
from engine.entities.traits.unit_trait import entity_trait_names, has_any_trait
from engine.runner.components import NOT_DISPLACEABLE_TRAITS   # #498-r4 : foyer UNIQUE de la liste
from engine.runner.operations.displace import _dir_index, _step   # geometrie FindTileToPush partagee

from ._base import NCContext, NonComparablePlaybook, _sweep_origin_first

# `IdunBattle.Entities.UnitExtensions$$IsDisplaceable` : les traits BLOQUANTS (`BaseUnitComponent$$
# HasTrait` avec 0x11 `Immovable`, 0x3 `Hulking`, 0x3f9 `BigTarget`).
# #498-r4 -- CE TUPLE ETAIT LA TROISIEME COPIE du meme, apres `runner/components.py` et
# `loki_custom.py::MortisRoundPlaybook`. Il DELEGUE desormais au foyer runner : trois listes libres
# de diverger sont le gisement exact que #498-r3 a ferme cote RUNNER.
_NOT_DISPLACEABLE = NOT_DISPLACEABLE_TRAITS


class ItItchesPlaybook(NonComparablePlaybook):
    """`IdunBattle.AI.Playbook.Loki.ItItchesPlaybook$$EvaluateNonComparable` (id 0x461=1121, tyranParasiteOfMortrex).

    NonComparable a utilite ENTIERE (aucun `Make*Predictions` — reframe #34) : la Parasite pousse un
    ennemi adjacent ET les ennemis adjacents A LA FOIS a la cible et a elle-meme, puis fait apparaitre un
    Ripper Swarm dans chaque hex libere. L'utilite = COMBIEN d'ennemis la poussee affecte.

    - cibles = `GetEligibleTargetsSelectable(ctx, position)` : des TUILES, pas des unites (mesure live
      909 s14 : `abilityTargets` 1121 rend kind=tile = les tuiles des ennemis ; decompile : l'element
      est passe TEL QUEL a `GenerateAction` comme cible -> le natif emet un ID DE TUILE, ex. 63=(5,6)) ;
      l'unite est resolue depuis l'element via `UnitExtensions.GetUnit` (= l'occupant) pour les gates.
    - GATE 1 : `UnitExtensions.IsDisplaceable(occupant) == false -> continue` (IdunBattle.Entities.UnitExtensions$$IsDisplaceable : unite vivante,
      SANS `Immovable(17)` ni `Hulking(3)` ni `BigTarget(0x3f9=1017)`, et sans le FLAG runtime 0x19).
    - GATE 2 (`CanBePushed` inline, cf. IdunBattle.AI.Playbook.Loki.ItItchesPlaybook$$CanBePushed) : `IBattleQuery` slot 0x4d `(casterTile, target)` ->
      liste de tuiles, `FilterInPlace(<predicat du playbook>)`, `Count > 0` = il existe une destination de
      poussee. Porte par la GEOMETRIE REELLEMENT EXECUTEE (`DisplaceUnitOperation` /
      `IdunBattle.Operations.DisplaceUnitOperation$$FindTileToPush` : 1 pas dans la direction caster->cible, tuile walkable et libre) —
      c'est le mirror defendable ; l'identite exacte du slot 0x4d n'est PAS tranchee (ce n'est ni
      `GetAdjacentTiles`=0x4e ni `GetTilesBehind`=0x53, qui prennent d'autres arites) -> FLAG.
    - utilite = `Fix64.FromInt(Count(GetTargetUnits(cible)))` ou
      `IdunBattleLogic.Entities.Abilities.Active.Loki.ItItchesAbility$$GetTargetUnits` = `Enemies(Target + AdjacentTilesIntersection(caster,
      target))` = la cible ELLE-MEME + les ennemis adjacents A LA FOIS a la cible et au caster.
    - `MIN_UTILITY` = IdunBattle.AI.Playbook.Loki.ItItchesPlaybook$$.cctor = `Fix64.FromInt(1)` (toujours passe des que la cible est
      poussable : elle compte pour 1) ; `PRIORITY`=0 (defaut 0 = `AbilityPriority.Normal` ; ability hors `NATIVE_PRIORITY`, sweep exhaustif #170). `GenerateAction(position, element, util)`
      ou `element` = l'entite TUILE issue de la liste eligible (mirror : `ctx.tile_id_by_pos[T]`).

    Ecarts assumes : (1) le FLAG runtime `HasFlag(unit, 0x19)` d'`IsDisplaceable` n'est pas lisible
    offline (enum de flags d'entite, distinct des traits gameconfig) -> non teste ; (2) l'eligibilite
    par-position est reconstituee en filtrant l'union `abilityTargets` (tuiles) par adjacence a la
    position balayee ; (3) `IdunBattle.AI.Playbook.Loki.ItItchesPlaybook$$GetUseProbability` = `Fix64.FromIntFraction(GetMaxNumUnitsAffected,
    3)` (porte ALEATOIRE : ~n/3 de chances d'utiliser l'ability) — non modelisee (moteur deterministe),
    meme statut que ScarabSummon/BlackRage."""
    ABILITY_ID = int(ActiveAbilityType.ItItches)  # 1121
    MIN_UTILITY = 1.0     # IdunBattle.AI.Playbook.Loki.ItItchesPlaybook$$.cctor = Fix64(1)
    PRIORITY = 0

    def _eligible_target_tiles(self, ctx: NCContext) -> list[tuple]:
        """`GetEligibleTargetsSelectable` : union `abilityTargets` kind=tile (les tuiles des ennemis
        poussables — mesure live 909 s14 : 5 tuiles = les 5 positions ennemies), ordre preserve."""
        if ctx.ability_targets is None:
            return []
        at = ctx.ability_targets(ctx.uid, self.ABILITY_ID) or {}
        out: list[tuple] = []
        for u in (at.get("units") or []):
            for a in (u.get("abilities") or []):
                if a.get("abilityId") != self.ABILITY_ID:
                    continue
                for t in (a.get("targets") or []):
                    tl = t.get("tile") if t.get("kind") == "tile" else None
                    if tl and tl.get("col") is not None:
                        out.append((tl["col"], tl["row"]))
        return list(dict.fromkeys(out))

    @staticmethod
    def _is_displaceable(ctx: NCContext, unit: dict) -> bool:
        """`IdunBattle.Entities.UnitExtensions$$IsDisplaceable` : vivante, et sans aucun des trois
        traits refusants.

        ⚠ LE SUBSTRAT DE TRAITS A CHANGE (#498-r4), ET C'ETAIT UN ECART PERMISSIF. Ce site lisait
        `_traits(visualId)` -- le KIT gameconfig SEUL. Le natif lit
        `IdunBattle.Entities.Components.BaseUnitComponent$$HasTrait`, c'est-a-dire la collection
        `BaseUnitComponent+0x48`/`+0x40`, qui porte AUSSI les traits ACCORDES EN BATAILLE (leaf DSL
        `IdunBattleLogic.Entities.DSLFactory$$AddTrait` -> `IdunBattle.Operations.AddTraitOperation
        $$AddTrait`) et le pseudo-trait de grande-alliance. Le foyer porte est
        `entity_trait_names(ctx)`, exactement ce que lisent l'autre miroir de DECISION
        (`loki_custom.py::MortisRoundPlaybook._is_displaceable`) et le foyer RUNNER
        (`runner/components.py::unit_extensions_is_displaceable`). Une unite qui s'est vu ACCORDER
        `BigTarget`/`Immovable`/`Hulking` en cours de bataille etait donc jugee poussable ici,
        et refusee partout ailleurs.

        `ctx.scene` absent (contexte construit a la main) -> `entity_trait_names(None, visualId)`
        retombe sur le substrat STATIQUE, c'est-a-dire le comportement d'avant : une BORNE, pas une
        regression.

        Les deux conditions natives NON portees ici (`HasFlag(0x19)`, `EntityType == Unit`) sont
        MESUREES et documentees au site jumeau, `MortisRoundPlaybook._is_displaceable`."""
        if unit is None or unit.get("alive") is False:
            return False
        scene = getattr(ctx, "scene", None)
        uctx = scene.ctx(unit.get("id")) if scene is not None else None
        return not has_any_trait(entity_trait_names(uctx, unit.get("visualId")),
                                 _NOT_DISPLACEABLE)

    @staticmethod
    def _can_be_pushed(ctx: NCContext, pusher_pos: tuple, tpos: tuple) -> bool:
        """`IdunBattle.AI.Playbook.Loki.ItItchesPlaybook$$CanBePushed` : existe-t-il une destination de poussee ? Mirror de la geometrie
        EXECUTEE (`FindTileToPush`) : 1 pas dans la direction `pusher_pos -> tpos`, tuile connue du
        board, walkable et LIBRE. `walkable_by_pos` absent -> on se rabat sur les tuiles connues
        (`elev_by_pos`) pour ne pas gater a l'aveugle."""
        d = _dir_index(pusher_pos[0], pusher_pos[1], tpos[0], tpos[1])
        if d is None:
            return False           # pousseur non adjacent -> pas de direction unitaire
        dest = _step(tpos[0], tpos[1], d)
        if ctx.walkable_by_pos:
            if not ctx.walkable_by_pos.get(dest):
                return False
        elif ctx.elev_by_pos is not None and dest not in ctx.elev_by_pos:
            return False           # hors board
        # #969-r3 : PAR PIED (`TileContentComponent`). `pusher_pos` est ici l'ancre du site (le
        # POUSSEUR, pas forcement `ctx.origin`), donc il entre par `base` -- l'expansion ajoutera
        # ses propres pieds comme ceux de toute unite de l'univers.
        occupied = bq.occupied_positions(
            ctx, base=(set(ctx.epos or []) | set(ctx.fpos or []) | {pusher_pos}))
        return dest not in occupied

    def generate_candidates(self, ctx: NCContext) -> list[dict]:
        tiles = self._eligible_target_tiles(ctx)
        if not tiles:
            return []
        unit_by_pos = {}
        for u in (ctx.units or []):
            if u.get("alive") is False:
                continue
            p = u.get("pos")
            if p and p.get("col") is not None:
                unit_by_pos[(p["col"], p["row"])] = u
        eligible = set(tiles)
        best = None      # (util, position, targetTile)
        for P in _sweep_origin_first(ctx):
            # Ordre par-position NATIF : le selecteur enumere les tuiles adjacentes du caster dans
            # l'ordre `GetAdjacentTiles` (neigh_by_pos) — decisif au keep-first du Bucket a util egal
            # (mesure 909 s14 : voisins de (4,5) = [.., 63=(5,6), 62=(5,5), ..] -> natif garde 63).
            neigh = (ctx.neigh_by_pos or {}).get(P)
            ordered = ([T for T in neigh if T in eligible] if neigh else
                       [T for T in tiles if bq.is_adjacent(P, T, ctx.elev_by_pos, bq.neigh_map(ctx))])
            for T in ordered:
                tu = unit_by_pos.get(T)             # `GetUnit(element)` : l'occupant de la tuile
                if not self._is_displaceable(ctx, tu):
                    continue                        # GATE 1
                if not self._can_be_pushed(ctx, P, T):
                    continue                        # GATE 2
                # GetTargetUnits : la cible + les ennemis adjacents A LA FOIS a la cible et au caster.
                util = 1.0 + sum(1.0 for e in (ctx.epos or [])
                                 if e != T
                                 and bq.is_adjacent(T, e, ctx.elev_by_pos, bq.neigh_map(ctx))
                                 and bq.is_adjacent(P, e, ctx.elev_by_pos, bq.neigh_map(ctx)))
                if best is None or util > best[0]:  # Bucket.AddAction : remplacement STRICT `>`
                    best = (util, P, T)
        if best is None or best[0] < self.MIN_UTILITY:
            return []
        util, P, T = best
        if ctx.debug:
            import sys
            print(f"    [dbg ItItches u{ctx.uid}] pos={P} tile={T} "
                  f"tid={ctx.tile_id_by_pos.get(T)} util={util}", file=sys.stderr)
        return [{"target": ctx.tile_id_by_pos.get(T), "ability": self.ABILITY_ID,
                 "to": (P if P != ctx.origin else None), "pred": util}]
