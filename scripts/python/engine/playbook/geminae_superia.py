"""`GeminaeSuperiaPlaybook` — le playbook de MOUVEMENT du passif `GeminaeSuperia` (1048).

Famille « corps propre » (comme `friends_in_range.py`) : il n'override pas les
`GetAdjacent{Friend,Enemy}Utility` du corps partage `AdjacentUnitPreferenceTriggeredAbilityPlaybook`,
il a SON PROPRE iterateur `CalculateMovementUtilityInStepsInternal`. Le dispatcher est le meme
(feuille de tuile `TriggeredAbilitiesUtility(2)` ->
`IdunBattle.AI.PlaybookDatabase$$LoadPlaybook(abilityType)`), d'ou l'enregistrement commun dans
`TRIGGERED_MOVE_PLAYBOOKS` (`adjacent_unit_preference.py`).

Ce que ce terme apporte, et pourquoi il est INVISIBLE la plupart du temps (case-165b) : il vaut
`10 x (nombre de voisins ring-1 LIBRES de la tuile candidate)`. En plein plateau toutes les
candidates ont 6 voisins libres -> le terme est CONSTANT et ne change aucun classement. Il ne
departage QUE la ou le voisinage est TRONQUE : bord de plateau, coin, ou voisins occupes. C'est
exactement la configuration ou le port rendait une autre tuile que le natif
(`docs/rl/case-165-collapse-tuile-plus-proche.md` §4).
"""
from __future__ import annotations

from .. import battle_query as bq
from ..entities.triggered_ability_type import TriggeredAbilityType   # #270-r1-r1-r3


def _occupied_positions(ctx: dict) -> set:
    """Positions que `CanAddUnit` voit OCCUPEES : toutes les unites vivantes POSEES, **self
    INCLUS** (l'unite qui evalue est encore sur son origine pendant tout le sweep, et
    `IdunBattle.Entities.Components.TileContentComponent$$IsEmpty` rend donc FAUX sur sa tuile).
    C'est precisement ce que le natif re-credite ensuite via `OwnerInAdjacentTile`."""
    occ = {tuple(u["pos"]) for u in (ctx.get("friend_units") or ()) if u.get("pos")}
    occ |= {tuple(u["pos"]) for u in (ctx.get("enemy_units") or ()) if u.get("pos")}
    sp = ctx.get("self_pos")
    if sp:
        occ.add(tuple(sp))
    return occ


class GeminaeSuperiaPlaybook:
    """`GeminaeSuperiaPlaybook` (`IdunBattle.AI.Playbook.Loki.GeminaeSuperiaPlaybook$$.ctor` : litteral
    `0x418` = 1048 `GeminaeSuperia`, passif d'`adeptCelestine`) ;
    `IdunBattle.AI.Playbook.Loki.GeminaeSuperiaPlaybook.u003CCalculateMovementUtilityInStepsInternalu003Ed__3$$MoveNext`
    remis en C# depuis le decompile :

        tile = IdunBattle.AI.Utilities.UtilityMovementCase$$get_MovementTile(case)  // la TUILE CANDIDATE
        free = CanAddUnit(AdjacentTiles(Get(tile)))
        val  = config["GEMINAESUPERIA_FreeAdjacentHex"] * free.Count(entities)
        if (Count(AdjacentUnits(Get(tile), 1, 3) & Get(case.unit)) == 1)  // = OwnerInAdjacentTile
            val += config["GEMINAESUPERIA_FreeAdjacentHex"]
        gem  = UnitsWithId( Friends(Get(case.unit), AdjacentUnits(Get(tile), 1, 3), 3),
                            AbilityConfiguration.GetStringConstant(config, 0), 3 )
        val += config["GEMINAESUPERIA_AdjacentAliveSummon"] * gem.Count(entities)
        yield Fix64.FromInt(val)

    Les DEUX cles BC sont dans `Utilities.Default.TriggeredAbilities` :
    `GEMINAESUPERIA_FreeAdjacentHex` = 10, `GEMINAESUPERIA_AdjacentAliveSummon` = 30.

    (⚠ La citation `UtilityAttackCase.get_CasterTile` qui vivait ici jusqu'a #963 etait FAUSSE : le
    decompile appelle `IdunBattle.AI.Utilities.UtilityMovementCase$$get_MovementTile` -- un
    `UtilityMovementCase`, pas un `UtilityAttackCase`. Le CODE, lui, etait juste : les TROIS termes
    ont ete re-confrontes au decompile pour #963 et sont fideles.)

    Terme 2 — `IdunBattle.AI.Playbook.Loki.GeminaeSuperiaPlaybook$$OwnerInAdjacentTile` est une
    methode NOMMEE du playbook (meme corps, inline dans l'iterateur) : « l'unite qui evalue est-elle
    DEBOUT sur une tuile ring-1 de la candidate ». C'est la COMPENSATION du terme 1 : la tuile
    d'origine est comptee occupee par `CanAddUnit`, alors qu'elle sera libre une fois l'unite partie
    -> le natif lui re-credite un hex, au meme poids.

    Terme 3 — `GetStringConstant(config, 0)` = `gameconfig.abilities.GeminaeSuperia.constants.unitId`
    = `adeptSmnGeminaeSuperia` (les deux Geminae invoquees). On matche l'id de CONFIG **et** l'id
    VISUEL, comme le noeud `UnitsWithIds` (`entities/formulas.py`) : le `visualId` offline porte l'id
    de config pour les unites spawnees par le moteur, l'id visuel pour celles seedees depuis le live.

    REDUCTION assumee du terme 1 : `CanAddUnit` est le predicat deja porte
    (`battle_query.can_add_unit` : walkable + tuile vide) et l'anneau est
    `battle_query.adjacent_addable_count` (`GetAdjacentTiles` + porte d'elevation `|Delta| < 2`),
    exactement le mirror live-valide de `|{n in GetAdjacentTiles : CanAddUnit(n)}|` deja utilise par
    `HammerOfWrathPlaybook` (#116). Sans `neigh_by_pos`/`walkable_by_pos` dans le `ctx`, ce mirror
    degrade (voisinage hexgeo, tuiles supposees placeables) -- meme degradation que partout ailleurs.
    """

    ABILITY_ID = TriggeredAbilityType.GeminaeSuperia                                   # 0x418 -- litteral du `..ctor`
    FREE_HEX_KEY = "GEMINAESUPERIA_FreeAdjacentHex"           # BC = 10
    ADJACENT_SUMMON_KEY = "GEMINAESUPERIA_AdjacentAliveSummon"  # BC = 30
    CONFIG_ID = "GeminaeSuperia"

    def summon_unit_ids(self) -> frozenset:
        """`AbilityConfiguration.GetStringConstant(config, 0)` = `constants.unitId` de l'ability,
        elargi a son id VISUEL (cf. `UnitsWithIds` / `VisualUnitIdFromUnitId`)."""
        import gameconfig as GC
        cfg = (GC.ability(self.CONFIG_ID) or {}).get("constants") or {}
        uid = cfg.get("unitId")
        if not uid:
            return frozenset()
        vis = (GC.unit(uid) or {}).get("visualId")
        return frozenset(x for x in (uid, vis) if x)

    def owner_in_adjacent_tile(self, tile, ctx: dict) -> bool:
        """`IdunBattle.AI.Playbook.Loki.GeminaeSuperiaPlaybook$$OwnerInAdjacentTile` :
        `Count(AdjacentUnits(Get(case.CasterTile), 1, 3) & Get(case.unit)) == 1`."""
        sp = (ctx or {}).get("self_pos")
        if not sp:
            return False
        return bq.is_adjacent(tuple(tile), tuple(sp), (ctx or {}).get("elev_by_pos"), bq.neigh_map(ctx))

    def calculate_movement_utility_in_steps(self, tile, ctx: dict, wt) -> float:
        ctx = ctx or {}
        w_free = wt.sub("TriggeredAbilities", self.FREE_HEX_KEY)
        w_gem = wt.sub("TriggeredAbilities", self.ADJACENT_SUMMON_KEY)
        tile = (tile[0], tile[1])
        occ = _occupied_positions(ctx)
        n_free = bq.adjacent_addable_count(tile, ctx.get("neigh_by_pos"),
                                           ctx.get("walkable_by_pos"), occ,
                                           ctx.get("elev_by_pos"))
        val = float(w_free) * n_free
        if self.owner_in_adjacent_tile(tile, ctx):
            val += float(w_free)
        if w_gem:
            ids = self.summon_unit_ids()
            if ids:
                elev = ctx.get("elev_by_pos")
                neigh = bq.neigh_map(ctx)
                n_gem = sum(1 for u in (ctx.get("friend_units") or ())
                            if u.get("vis") in ids and u.get("pos")
                            and bq.is_adjacent(tile, tuple(u["pos"]), elev, neigh))
                val += float(w_gem) * n_gem
        return val
