"""Playbook de MOUVEMENT de `1319 LegacyOfCombat` (passif de `custoBladeChampion` << Kariyan >>).
Tache #928, face DECISION.

Famille << corps propre >> : `IdunBattle.AI.Playbook.Loki.LegacyOfCombatPlaybook` derive de
`IdunBattle.AI.Playbook.TriggeredAbilityPlaybook<LegacyOfCombatAbility>` (parente LUE dans
`data/symbols/<build>/frida/classes.tsv`), **PAS** d'`AdjacentUnitPreferenceTriggeredAbilityPlaybook`
ni d'`AdjacentToOwnerNonOwnerPlaybook` -- elle n'override donc AUCUN accesseur de poids : elle a son
propre iterateur. Deux consequences directes :

  * elle n'a **aucune face NON-OWNER** (aucune entree dans
    `data/symbols/<build>/metadata/non_owner_slot4.tsv`, comme l'exige sa parente) ;
  * le corps compte des **ENNEMIS**, la ou les deux modules voisins de la meme famille
    (`friends_in_range.py`) comptent des AMIS -- et sans aucune inclusion de self, puisque le natif
    demande les ennemis de l'unite qui bouge.

## Le corps natif, LU

`IdunBattle.AI.Playbook.Loki.LegacyOfCombatPlaybook.u003CCalculateMovementUtilityInStepsInternalu003Ed__2$$MoveNext` :

    tile  = IdunBattle.AI.Utilities.UtilityMovementCase$$get_MovementTile(case)   // TUILE CANDIDATE
    units = IBattleQuery.<slot 127>(tile, case.unit@0x10, false)                  // GetAdjacentEnemies
    yield Fix64.FromInt( GetUtilityValue("LegacyOfCombat_LikesAdjacentEnemies") * units.Count )

  * **`get_MovementTile`, pas `get_CasterTile`** : c'est un `UtilityMovementCase` (la feuille de
    TUILE `TriggeredAbilitiesUtility(2)`), pas un `UtilityAttackCase`.
  * Le slot 127 est l'une des **QUATRE** surcharges de `GetAdjacentEnemies` de l'interface (slots
    125..128, toutes d'arite 3, `data/symbols/<build>/metadata/interface_slots.tsv`). Celle-ci prend
    `(from, unit, ignoreSteppables)` -- l'ancre est une TUILE et le second argument l'UNITE (aucun
    `OwnerComponent$$get_CurrentPlayerEntityId` dans le corps, contrairement au corps commun
    d'`AdjacentUnitPreference`, qui appelle la surcharge `playerEntityId`).
  * **AUCUN filtre, AUCUN cap, AUCUNE exclusion** : le terme est un produit plat.

## La cle BC

`LegacyOfCombat_LikesAdjacentEnemies`, RESOLUE au litteral de `global-metadata.dat` (slot de
metadata usage -> `probe_212_bc_key_literals.py --symbol <le MoveNext>`), pas devinee par prefixe.
Elle vaut **10** dans la capture `data/seed-bc.json` ET dans le gameconfig VIVANT
(`catalog_inject.ai_utilities_from_gameconfig`) -- le refresh ne la change donc pas, contrairement a
`KustomForceFieldReworked` (#271).

## La face ATTAQUE est DEAD

`...LegacyOfCombatPlaybook.<CalculateAttackUtilityInStepsInternal>d__3$$MoveNext` a pour corps
ENTIER `yield return Fix64.op_Implicit(0)` : un zero CONSTANT, sans lecture d'etat, sans appel autre
que la conversion. Elle n'entre donc PAS dans `psyker.TRIGGERED_ATTACK_PLAYBOOKS` -- absence == 0,
exactement la meme valeur, et le verdict est grave par `test_928_legacy_of_combat_offline.py` (qui
le RE-DERIVE du binaire au lieu de le citer).
"""
from __future__ import annotations

from .. import battle_query as bq
from ..entities.triggered_ability_type import TriggeredAbilityType


class LegacyOfCombatPlaybook:
    """`LegacyOfCombatPlaybook` (`IdunBattle.AI.Playbook.Loki.LegacyOfCombatPlaybook$$.ctor` :
    littéral `0x527` = 1319 `LegacyOfCombat`).

    Terme = 10 x |ennemis a distance 1 de la tuile candidate|. Il est CROISSANT avec le nombre
    d'ennemis adjacents, ce qui est coherent avec le passif qu'il sert (l'attaque supplementaire
    frappe CHAQUE ennemi adjacent quand aucun Big Target n'est la) -- mais le corps d'utilite, lui,
    ne connait ni `BigTarget` ni le compte de coups : il ne pese que le NOMBRE de voisins ennemis.

    L'adjacence passe par `battle_query.is_adjacent` (liste de voisinage STOCKEE + porte
    d'elevation `|delta| < 2` d'`IdunBattle.Core.Services.TileQuery.
    u003CIterateAdjacentTilesu003Ed__8$$MoveNext`), le meme foyer que toutes les feuilles ring-1 --
    et non `hexgeo.distance == 1`, qui SUR-COMPTE au bord d'une marche (#271)."""

    ABILITY_ID = TriggeredAbilityType.LegacyOfCombat                     # 0x527 = 1319
    WEIGHT_KEY = "LegacyOfCombat_LikesAdjacentEnemies"                   # = 10 (capture ET vivant)

    def calculate_movement_utility_in_steps(self, tile, ctx: dict, wt) -> float:
        w = wt.sub("TriggeredAbilities", self.WEIGHT_KEY)
        if not w:
            return 0.0
        ctx = ctx or {}
        # `enemy_units` = les unites NON controlees, vivantes et positionnees (`utilities/tile.py::
        # _adjacent_units`). Le natif demande les ennemis de `case.unit`, donc AUCUNE inclusion de
        # self ici -- contraste avec la famille `friends_in_range`, ou l'unite qui evalue compte
        # pour elle-meme parce qu'elle est sa propre alliee.
        n = bq.count_adjacent(tile, [u["pos"] for u in (ctx.get("enemy_units") or ()) if u.get("pos")],
                              ctx.get("elev_by_pos"), bq.neigh_map(ctx))
        return float(w * n)
