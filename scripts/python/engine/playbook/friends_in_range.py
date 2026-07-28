"""Playbooks de MOUVEMENT qui COMPTENT DES AMIS AUTOUR DE LA TUILE CANDIDATE (famille « corps propre »).

Ces concrets NE sont PAS de la famille `AdjacentUnitPreferenceTriggeredAbilityPlaybook` : ils
n'overrident pas `GetAdjacent{Friend,Enemy}Utility` sur le corps partage, ils ont CHACUN leur
propre `CalculateMovementUtilityInStepsInternal` (iterateur dedie dans le binaire). Le dispatcher
est le meme (feuille de tuile `TriggeredAbilitiesUtility(2)` ->
`IdunBattle.AI.PlaybookDatabase$$LoadPlaybook(abilityType)`), d'ou l'enregistrement commun dans
`TRIGGERED_MOVE_PLAYBOOKS` (`adjacent_unit_preference.py`).

Motif commun aux deux corps natifs, LU au decompile :

    query   = <service IBattleQuery du playbook>
    tile    = UtilityAttackCase.get_CasterTile(case)         // la TUILE CANDIDATE
    units   = query.<slot>(tile, ..., case.unit@0x10, ...)   // amis AUTOUR de la tuile
    weight  = config[<cle BC>]                               // Utilities.Default.TriggeredAbilities[...]
    yield Fix64.FromInt(weight * units.Count)                // ou Sigma weight, meme chose

⚠ POINT DECISIF, mesure ET decompile concordants : ces deux corps N'EXCLUENT PAS l'unite qui
evalue. La query natives ne retire que les ENNEMIS (`GetSurroundingUnits` -> `IsEnemy`), et
`FirstAmongTraitorsPlaybook` — meme slot, meme forme — doit ecrire un `!= case.unit` EXPLICITE
pour s'exclure. Or l'unite qui evalue est encore SUR SON ORIGINE pendant tout le sweep : elle
compte donc pour elle-meme des que son origine tombe dans le voisinage de la tuile candidate.
C'est ce terme, invisible d'un raisonnement « une aura ne se compte pas elle-meme », qui rend le
residu POSITION-DEPENDANT (cf. `docs/rl/case-n13-tile-term-triggered-playbooks.md`).

Cette famille se distingue donc d'`AdjacentUnitPreference` sur DEUX axes a la fois (self compte /
self exclu, disque cube sans porte d'elevation / ring-1 avec porte) : ne PAS les fusionner.
"""
from __future__ import annotations

from .. import battle_query as bq
from ..entities.effects.magnitude import ability_var


def _friend_positions_including_self(ctx: dict) -> list:
    """Positions des AMIS VIVANTS de l'unite qui evalue, **self INCLUS a son origine**.

    Mirror du contenu de `IdunBattle.Core.Services.BattleQuery$$GetSurroundingUnits` filtre par
    `ListExtensions.FilterInPlace(!IsEnemy(u, unit))` : toutes les unites POSEES du camp de
    `unit`, l'unite comprise (la query travaille par TUILE et ne connait pas la notion de
    « soi »). `ctx` = le dict par-decision `tile_leaf_ctx` :
      * `friend_units` = allies vivants SELF-EXCLU ({pos, traits, effects}) ;
      * `self_pos`     = origine de l'unite qui evalue (None si hors plateau -> non comptee,
                         degradation fidele : sans MainTile le natif ne la trouve sur aucune tuile).
    """
    out = [u["pos"] for u in (ctx.get("friend_units") or ()) if u.get("pos")]
    sp = ctx.get("self_pos")
    if sp:
        out.append(tuple(sp))
    return out


class AstartesBannerPlaybook:
    """`AstartesBannerPlaybook` (`IdunBattle.AI.Playbook.Loki.AstartesBannerPlaybook$$.ctor` ; ability
    0x452 = 1106 AstartesBanner — passif des Ancients Astartes, ex. templAncient) ;
    `IdunBattle.AI.Playbook.Loki.AstartesBannerPlaybook.u003CCalculateMovementUtilityInStepsInternalu003Ed__2$$MoveNext` :

        tile  = UtilityAttackCase.get_CasterTile(case)
        range = AbilityConfiguration.GetNumberConstant(config, 0x16)          // "range" = 2
        units = IBattleQuery.<slot 0x74>(tile, range, case.unit, true)        // GetSurroundingFriends
        yield Fix64.FromInt( config["AstartesBanner_NearbyFriend"] * units.Count )

    Le dernier argument (`true`) est le flag `includeCenterTile` de
    `IdunBattle.Core.Services.TileQuery.u003CIterateSurroundingTilesu003Ed__6$$MoveNext` : l'ami
    DEBOUT SUR la tuile candidate compte (mesure `C4_09`/999 pas 14, tuile (6,4)). Aucun filtre de
    trait, aucune exclusion de self (cf. l'en-tete du module).

    Poids BC : `Utilities.Default.TriggeredAbilities["AstartesBanner_NearbyFriend"]` = 5."""

    ABILITY_ID = 1106
    CONST_RANGE = 0x16          # GetNumberConstant(0x16) -> gameconfig `constants.range`
    WEIGHT_KEY = "AstartesBanner_NearbyFriend"

    def get_range(self) -> int:
        """`AbilityConfiguration.GetNumberConstant(config, 0x16)` = `constants.range` (= 2)."""
        r = ability_var("AstartesBanner", "range", is_constant=True)
        return int(r) if r is not None else 0

    def calculate_movement_utility_in_steps(self, tile, ctx: dict, wt) -> float:
        w = wt.sub("TriggeredAbilities", self.WEIGHT_KEY)
        if not w:
            return 0.0
        n = bq.count_surrounding(tile, _friend_positions_including_self(ctx or {}),
                                 self.get_range(), include_center_tile=True)
        return float(w * n)


class KardiocoreGalvanusPlaybook:
    """`KardiocoreGalvanusPlaybook` (`IdunBattle.AI.Playbook.Loki.KardiocoreGalvanusPlaybook$$.ctor` ;
    ability 0x5b1 = 1457 KardiocoreGalvanus — RELIQUE, pas un passif de kit) ;
    `IdunBattle.AI.Playbook.Loki.KardiocoreGalvanusPlaybook.u003CCalculateMovementUtilityInStepsInternalu003Ed__2$$MoveNext` :

        tile  = UtilityAttackCase.get_CasterTile(case)
        units = IBattleQuery.<slot 0x82>(tile, case.unit)                     // GetAdjacentFriends
        foreach u in units:  val += config["KardiocoreGalvanus_LikesAdjacentMechanicalFriends"]
        yield Fix64.FromInt(val)

    ⚠ Le corps natif n'a **AUCUN filtre** : ni `HasTrait(Mechanical)`, ni `!= case.unit`. Le nom de
    la cle BC (« LikesAdjacentMechanicalFriends ») decrit l'EFFET de la relique (« +Crit Damage pour
    chaque unite Mecanique amie adjacente »), PAS l'utilite d'IA — l'utilite, elle, compte TOUS les
    amis adjacents. Ecart mesure et assume (`C4_09`/31337 pas 22 : les 3 amis comptes en (4,3) sont
    custoBladeChampion / bloodMephiston / eldarAutarch, aucun Mecanique).

    La query est un `GetAdjacentFriends` (ring-1 via `IterateAdjacentTiles`, tuile centrale EXCLUE,
    porte d'elevation `|Delta elev| < 2` — cf. `battle_query.is_adjacent`), la ou AstartesBanner passe
    par le disque `IterateSurroundingTiles`. Self compte des que l'origine est ring-1 de la tuile.

    Poids BC : `Utilities.Default.TriggeredAbilities["KardiocoreGalvanus_LikesAdjacentMechanicalFriends"]` = 5."""

    ABILITY_ID = 1457
    WEIGHT_KEY = "KardiocoreGalvanus_LikesAdjacentMechanicalFriends"

    def calculate_movement_utility_in_steps(self, tile, ctx: dict, wt) -> float:
        w = wt.sub("TriggeredAbilities", self.WEIGHT_KEY)
        if not w:
            return 0.0
        ctx = ctx or {}
        n = bq.count_adjacent(tile, _friend_positions_including_self(ctx),
                              ctx.get("elev_by_pos"))
        return float(w * n)
