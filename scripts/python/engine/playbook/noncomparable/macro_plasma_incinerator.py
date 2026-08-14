"""`MacroPlasmaIncineratorPlaybook` (1159, `ultraDreadnought` -- MACHINE OF WAR) -- face DECISION.

Ferme le residu `#970-r4`, dont la fiche annoncait `BLOCAGE: etage`. Le blocage etait double, et
les DEUX etages sont arrives depuis, par d'AUTRES tranches -- c'est la mesure de fraicheur qui
ouvre ce port, pas une re-lecture du decompile :

  * la ZONE (`$$GetTargetAreaTiles`) n'existait que FONDUE dans l'arbre de la face COMBAT
    (`ultramarines.macro_plasma_incinerator_tree`). Elle en est EXTRAITE par cette tranche
    (`macro_plasma_incinerator_target_area_tiles`), donc les deux faces lisent le MEME arbre --
    exactement le montage que `1148 DaemonicOrdnance` utilise deja
    (`blacklegion.daemonic_ordnance_target_area_tiles`) ;
  * le `DslContext` cote DECISION existait deja (`playbook.tile_targets.dsl_context_for_tile_target`),
    et surtout son canal `current_player_machine_position` -- pose par #979 pour
    `DevastatingRefrain`, et publie a `NCContext.machine_of_war_position`. Sans lui le predicat
    `IsPositionMachineForCurrentPlayer(2)` rendrait `False` d'office, donc `dir = 4` TOUJOURS : la
    zone serait la mauvaise des que la MoW du joueur courant est en `Bottom`, EN SILENCE.

BASE LUE, JAMAIS DEDUITE DU `.ctor`
-----------------------------------
`data/symbols/<build>/frida/classes.tsv` :

    IdunBattle.AI.Playbook.Loki.MacroPlasmaIncineratorPlaybook | 112 | IdunBattle.AI.Playbook.NonComparablePlaybook`1

Son `.ctor` est etiquete `ComparablePlaybook<...>$$.ctor(this, 0x487)` par ghidra -- le corps
gshared DEDUPLIQUE, piege de #487-r1 / #945 / #957. `0x487` = 1159 est le seul litteral utile.

LE CORPS, TERME A TERME
------------------------
`IdunBattle.AI.Playbook.Loki.MacroPlasmaIncineratorPlaybook$$EvaluateNonComparable`, lu verbatim :

    bucket = new Bucket(0, Nullable(<premier statique de la classe>))
    foreach entities in BasePlaybook$$GetEligibleTargetsSelectable(caster, casterPosition):
        util = Fix64.op_Implicit(1)
        sel  = MacroPlasmaIncineratorAbility$$GetTargetAreaTiles(this.ability@+0x68)
        area = TargetsSelector.<Select>(sel, entities)
        util = util + Fix64.op_Implicit(area.Count)               # <-- +|zone|, LE terme oublie
        foreach t in area:
            if (TileExtensions$$IsFreeTile(t, this@+0x20, allowSteppable: 1,
                                           allowTemporaryTile: 0, allowAnyUnit: 0)) {
                n = battleQuery@+0x28.<slot itf 0x7f = GetAdjacentEnemies>(t, caster, false).Count
                util = util + Fix64.op_Implicit(n)
            }
        bucket.AddAction(BasePlaybook$$GenerateAction(casterPosition, entities.<+0x10 = target>, util))
    return bucket

`IdunBattle.AI.Playbook.Loki.MacroPlasmaIncineratorPlaybook$$.cctor` :
`<statique> = Fix64.op_Implicit(1)` -> `MIN_UTILITY = 1`. Un seul ecrivain
(`NonComparablePlaybook`1$$.cctor` N'EXISTE PAS dans le build), donc pas d'ecrasement a `Fix64(10)`
comme dans la famille COMPARABLE `static_threshold_gate`.

TROIS LECTURES QUI NE SE DEVINENT PAS
--------------------------------------
1. **`+ |zone|` EST UN TERME A PART ENTIERE**, et il est compte AVANT le gate `IsFreeTile` : le
   `area.Count` porte sur TOUTE la zone, y compris ses tuiles occupees. Le natif prefere donc une
   zone LARGE meme vide -- c'est ce qui separe une cible au centre du plateau (zone de 3) d'une
   cible au bord (zone de 1 ou 2), a ennemis egaux. Sans ce terme, le port serait plat sur toutes
   les cibles sans ennemi adjacent, et le tie retomberait sur l'ordre d'enumeration.
2. **LE GATE `IsFreeTile` PORTE SUR LES TUILES DE LA ZONE, PAS SUR LA CIBLE** (contraste
   `SquigMinePlaybook`, ou le meme appel gate la cible et fait `continue`). Ici il ne filtre QUE le
   terme d'ennemis adjacents : une zone integralement occupee rend quand meme `1 + |zone|`, et
   l'action est proposee.
3. **LE SLOT `0x7f` EST `GetAdjacentEnemies`, ARITE 3** -- `interface_slots.tsv` :
   `IBattleQuery 127 GetAdjacentEnemies 3`, ce que le call-site respecte (`(t, caster, false)`).
   La lecture << slot 0x7f = `GetNumAttackTargetsInPosition` >> qui vit dans
   `_base._get_num_attack_targets_in_position` est celle de `TheQuickeningPlaybook`, un AUTRE
   call-site d'une AUTRE arite : ne pas la recopier. Meme piege que pour `SquigMine`.

CE QUE `IsFreeTile` TESTE, ET CE QUE LE PORT EN VOIT
-----------------------------------------------------
`IdunBattle.Entities.TileExtensions$$IsFreeTile(tile, state, allowSteppable, allowTemporaryTile,
allowAnyUnit)`, branche `allowAnyUnit == 0` / `allowSteppable == 1`, lue verbatim :

    movement@+0x40 : if (movement[0x10] != 0) return false          # non marchable
    tileComp@+0x20 : if (tileComp[0x40] != 0) return false          # en BROUILLARD
    content@+0x38  : ok = content.IsEmpty()
                     || (GetUnit(tile, state) is u && u.HasTrait(0x1b = Steppable))
                     if (!ok) return false
    allowTemporaryTile == 0 -> return tileComp[0x2c] == 0           # tuile NON temporaire

Les quatre volets ont un substrat cote DECISION, et le port les pose tous les quatre :
`walkable_by_pos` (les deux premiers -- meme lecture que
`engine.entities.pathfinding.walk_pathfinder`, << `movement[0x10] && !fog` >>), l'occupation
(`occupant_team_by_pos`) avec sa DEROGATION `Steppable`, et `is_temporary_by_pos`.

⚠ La zone est DEJA filtree `Walkable` par l'arbre lui-meme, donc le volet marchabilite est
redondant ici -- il est ecrit quand meme, parce que c'est le gate NATIF et qu'un arbre qui
changerait le rendrait mordant.

ECART NOMME, ET SON SENS : `content.IsEmpty()` est l'ECS (`TileContentComponent`), rempli pour
CHAQUE pied d'une unite multi-tuiles ; `occupant_team_by_pos` vient d'`observeBattle.units`, qui
sous-declare l'occupation (MoW hors canal, bridge offline a une ligne par unite). Le port voit
donc des tuiles LIBRES la ou le natif en voit d'occupees -> il COMPTE plus d'ennemis adjacents,
jamais moins. Canal muet (`obs_units` vide) -> aucun refus, le gate laisse tout passer.

VOIE D'ENUMERATION -- TILE-TARGETED, donc PAS le plan
------------------------------------------------------
`GetEligibleTargetsSelectable(caster, casterPosition)` avec un masque `TargetIsTile` (le `.ctor`
d'ability : `rules = 0x46000040`). Cote port, `eligible_target_tiles` (`abilityTargets(uid,
1159).fromHere`, `kind == "tile"`) -- la MEME voie que `SquigMine`, `DutyEternal` et
`AetherStride`. Le porteur est une MoW : `ctx.origin is None` et `ctx.reach_nc == []`, donc `to =
None` et l'ecart << `fromHere` n'enumere que depuis l'origine >> est structurellement INERTE.

`PRIORITY` = **-100** (`AbilityPriority.Late`), deja dans `NATIVE_PRIORITY` -- 1159 y figurait
AVANT ce port, ce que `decision_face_voies.ECARTES` note explicitement (<< `1159`, `1200` et `1209`
y figurent alors que leur `EvaluateNonComparable` n'est pas porte >>). Cette phrase devient
partiellement fausse par cette tranche, et elle est corrigee au foyer.
"""
from __future__ import annotations

from engine import battle_query as bq
from engine.entities.active_ability_type import ActiveAbilityType
from engine.entities.selectors.accessors import FixedTileIds
from engine.entities.traits.unit_trait import UnitTrait
from engine.runner.abilities.ultramarines import \
    macro_plasma_incinerator_target_area_tiles
import engine.playbook.tile_targets as TT       # FORME B, ABSOLU (#962/#985-r1)

from ._base import (NCContext, NonComparablePlaybook, eligible_target_tiles, native_priority,
                    occupant_team_by_pos)


class MacroPlasmaIncineratorPlaybook(NonComparablePlaybook):
    """`IdunBattle.AI.Playbook.Loki.MacroPlasmaIncineratorPlaybook$$EvaluateNonComparable` --
    utilite = `1 + |zone| + Somme sur les tuiles LIBRES de la zone de |ennemis adjacents|`.
    cf. l'en-tete du module."""

    ABILITY_ID = int(ActiveAbilityType.MacroPlasmaIncinerator)      # 0x487 = 1159
    #: `...MacroPlasmaIncineratorPlaybook$$.cctor` : `Fix64.op_Implicit(1)` -> le `minUtility` du
    #: `Bucket` (gate d'`AddAction`).
    MIN_UTILITY = 1.0
    #: `Fix64.op_Implicit(1)` POSE AVANT tout comptage -- un PLANCHER, pas un compte nu.
    BASE_UTILITY = 1.0
    PRIORITY = native_priority(int(ActiveAbilityType.MacroPlasmaIncinerator))   # -100 = Late
    #: `TileExtensions$$IsFreeTile(..., allowSteppable: 1, ...)` -> une unite `Steppable` (0x1b)
    #: debout sur la tuile ne la rend PAS occupee.
    STEPPABLE = int(UnitTrait.Steppable)                            # 27 = 0x1b

    def _area(self, dctx, tile_id: int) -> list:
        """`GetTargetAreaTiles().Select(entities)` = la zone-triangle, ancree sur la TUILE VISEE.

        FOYER PARTAGE avec la face COMBAT (`macro_plasma_incinerator_target_area_tiles`) : le
        recopier ferait diverger les deux faces sur la geometrie. `FixedTileIds([tileId])` est le
        vehicule de collapse du role `Target`, exactement comme
        `DaemonicOrdnancePlaybook.calculate_custom_utility`."""
        return macro_plasma_incinerator_target_area_tiles(FixedTileIds([int(tile_id)])).select(dctx) or []

    def _is_free_tile(self, ctx: NCContext, dctx, tile_id: int, pos: tuple, occ: dict) -> bool:
        """`IdunBattle.Entities.TileExtensions$$IsFreeTile(t, state, allowSteppable: 1,
        allowTemporaryTile: 0, allowAnyUnit: 0)` -- les QUATRE volets, cf. l'en-tete du module.

        `occ` est PASSE, jamais stocke sur `self` : les playbooks sont des SINGLETONS partages
        (`PLAYBOOKS` en instancie un par ability, reutilise a chaque decision et par tous les
        casters), donc tout etat d'instance fuirait d'un appel a l'autre."""
        walk = ctx.walkable_by_pos or {}
        if walk and walk.get(pos) is False:
            return False                          # `movement[0x10] != 0` / brouillard
        if (ctx.is_temporary_by_pos or {}).get(pos):
            return False                          # `allowTemporaryTile == 0`
        if pos in occ:
            # `content.IsEmpty() || GetUnit(t).HasTrait(0x1b Steppable)` -- la DEROGATION est lue,
            # pas supposee : sans elle le port ecarterait une tuile que le natif accepte.
            u = TT.unit_on_tile(dctx, tile_id)
            if u is None:
                return True                       # occupation vue par `obs_units` seul -> ecart nomme
            return bool(dctx.has_trait(u, self.STEPPABLE)) if dctx.has_trait else False
        return True

    def evaluate_non_comparable(self, tile, target, ctx: NCContext):
        """`Fix64(1) + Fix64(|area|) + Somme_{t in area, IsFreeTile(t)} Fix64(|GetAdjacentEnemies(
        t, caster, false)|)`.

        `target` est une POSITION de tuile `(col, row)` (`eligible_target_tiles`). `tile` (la
        position du caster) n'entre PAS dans la formule : l'ancre est la tuile VISEE, et le
        `AbilityEntities` du natif ne porte pas `casterPosition` pour ce selecteur.

        Contexte DSL indisponible (`Scene` ou board absents) -> `None` : aucune utilite INVENTEE.
        Le natif, lui, rendrait au moins le plancher `1` -- la degradation est donc CONSERVATRICE
        (l'ability n'est pas proposee) et VISIBLE, jamais un score fabrique sur une zone imaginaire.
        """
        if target is None:
            return None
        dctx = TT.dsl_context_for_tile_target(ctx)
        if dctx is None:
            return None
        tid = (ctx.tile_id_by_pos or {}).get((target[0], target[1]))
        if tid is None:
            return None                           # pas d'entite-tuile -> le selecteur n'a rien a collapser
        area = self._area(dctx, tid)
        util = self.BASE_UTILITY + float(len(area))          # <-- `+ Fix64(area.Count)`
        board = getattr(dctx, "board", None)
        neigh = bq.neigh_map(ctx)
        occ = occupant_team_by_pos(ctx)
        epos = [(p[0], p[1]) for p in (ctx.epos or []) if p and p[0] is not None]
        for t in area:
            c = board.coord(int(t)) if board is not None else None
            if c is None:
                continue
            p = (int(c[0]), int(c[1]))
            if not self._is_free_tile(ctx, dctx, int(t), p, occ):
                continue
            # `<slot 0x7f = GetAdjacentEnemies>(t, caster, false).Count` -- ANCRE sur la tuile de
            # la zone, jamais sur le caster (une MoW n'a pas de position).
            util += float(bq.count_adjacent(p, epos, ctx.elev_by_pos, neigh))
        return util

    def generate_candidates(self, ctx: NCContext) -> list[dict]:
        """`ActiveAbilityActionGenerator` + `Bucket$$ChooseAction` pour une ability TILE-TARGETED.

        L'ordre de `fromHere` EST celui du selecteur natif ; `Bucket$$AddAction` ne remplace que sur
        amelioration STRICTE, donc a utilite egale la PREMIERE tuile gagne."""
        from_here, union = eligible_target_tiles(ctx, self.ABILITY_ID)
        tiles = from_here or union
        if not tiles:
            return []
        best = None                                          # (tuile, utilite)
        for tpos in tiles:
            util = self.evaluate_non_comparable(ctx.origin, tpos, ctx)
            if util is None or util < self.MIN_UTILITY:
                continue                                     # gate `minUtility` du `Bucket`
            if best is None or util > best[1]:               # STRICT -> keep-first au tie
                best = (tpos, util)
        if best is None:
            return []
        tid = (ctx.tile_id_by_pos or {}).get(best[0])
        if ctx.debug:
            import sys
            print("    [dbg NC u%s] MacroPlasmaIncinerator tile=%s util=%s"
                  % (ctx.uid, best[0], best[1]), file=sys.stderr)
        return [{"target": (tid if tid is not None else best[0]), "ability": self.ABILITY_ID,
                 "to": None, "pred": best[1]}]


__all__ = ["MacroPlasmaIncineratorPlaybook"]
