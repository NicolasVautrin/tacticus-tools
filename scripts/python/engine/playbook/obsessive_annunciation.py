"""Playbook de MOUVEMENT de `1443 ObsessiveAnnunciation` (passif de kit d'`emperKakophonist`
<< Adamatar >>). Tache #954, face DECISION.

Famille << corps propre >> : `IdunBattle.AI.Playbook.Loki.ObsessiveAnnunciationPlaybook` derive de
`IdunBattle.AI.Playbook.TriggeredAbilityPlaybook<ObsessiveAnnunciationAbility>` (parente LUE dans
`data/symbols/<build>/frida/classes.tsv`), **PAS** d'`AdjacentUnitPreferenceTriggeredAbilityPlaybook`
ni d'`AdjacentToOwnerNonOwnerPlaybook` -- elle n'override donc aucun accesseur de poids : elle a son
propre iterateur, et **aucune face NON-OWNER** (aucune entree dans
`data/symbols/<build>/metadata/non_owner_slot4.tsv`).

## Le corps natif, LU

`IdunBattle.AI.Playbook.Loki.ObsessiveAnnunciationPlaybook.u003CCalculateMovementUtilityInStepsInternalu003Ed__2$$MoveNext` :

    units = IBattleQuery.<slot 128>( case.<+0x18 = movementPosition>, case.<+0x10 = unit>, false )
    yield Fix64.FromInt( GetUtilityValue("ObsessiveAnnunciation_LikesAdjacentEnemy") * units.Count )

  * `UtilityMovementCase..ctor(unit, movementPosition, closestEnemy, abilityType, parent, target)`
    -> `+0x10 = unit`, `+0x18 = movementPosition` (layout d'objet C#, en-tete `0x10`). Le corps LIT
    ces deux champs DIRECTEMENT, sans passer par un accesseur.
  * Le slot **128** est la QUATRIEME des quatre surcharges de `GetAdjacentEnemies` de l'interface
    (slots 125..128, toutes d'arite 3, `data/symbols/<build>/metadata/interface_slots.tsv`) :
    `(from: UnitPosition, unit: IEntity, ignoreSteppables: bool)`. Son corps
    (`IdunBattle.Core.Services.BattleQuery$$GetAdjacentEnemies` = `0x115a7f0`) delegue a
    `...$$GetAdjacentUnits(tiles: IList<IEntity>, friendsOf, enemiesOf, ignoreSteppables)`
    (`0x115b3d0`) apres avoir developpe la position en LISTE de tuiles.
    ⚠ **Ce n'est PAS le slot 127 de `LegacyOfCombat`** (#928), qui prend `(from: IEntity, unit,
    ignoreSteppables)` et passe par `get_MovementTile(case)`. Le pseudo-C est identique dans les deux
    cas ; le discriminant est le litteral `mov r8d, 0x80` contre `mov r8d, 0x7f` juste avant
    `il2cpp_codegen_get_interface_invoke_data`, relu aux OCTETS cote a cote.
  * **AUCUN filtre, AUCUN cap, AUCUNE exclusion** : le terme est un produit plat.

## La cle BC

`ObsessiveAnnunciation_LikesAdjacentEnemy`, RESOLUE au litteral de `global-metadata.dat` (slot de
metadata `0x3351440` -> `metadata/string_literals.tsv`), pas devinee par prefixe. Elle vaut **10**
dans la capture `data/seed-bc.json` (`Utilities.Default.TriggeredAbilities`).

## La face ATTAQUE est DEAD

`...ObsessiveAnnunciationPlaybook.<CalculateAttackUtilityInStepsInternal>d__3$$MoveNext` a pour
corps ENTIER `yield return Fix64.op_Implicit(0)` : un zero CONSTANT, sans lecture d'etat, sans appel
autre que la conversion. Elle n'entre donc PAS dans `psyker.TRIGGERED_ATTACK_PLAYBOOKS` --
absence == 0, exactement la meme valeur.

## Contraste ASSUME avec le natif

`case.movementPosition` peut porter PLUSIEURS tuiles (une MACHINE OF WAR) ; le port passe la tuile
candidate SEULE, comme `LegacyOfCombat` avant lui. Sur une unite a un pied -- le cas d'Adamatar --
les deux lectures coincident exactement.
"""
from __future__ import annotations

from .. import battle_query as bq
from ..entities.triggered_ability_type import TriggeredAbilityType


class ObsessiveAnnunciationPlaybook:
    """`ObsessiveAnnunciationPlaybook` (`IdunBattle.AI.Playbook.Loki.ObsessiveAnnunciationPlaybook$$
    .ctor` : litteral `0x5a3` = 1443 `ObsessiveAnnunciation`).

    Terme = 10 x |ennemis a distance 1 de la tuile candidate|. Il est COHERENT avec le passif qu'il
    sert (les deux auras ne mordent que sur les ennemis ADJACENTS au porteur), mais le corps
    d'utilite ne connait ni le gate `IsRangedAttack` ni le gate `HasTrait(Chaos)` : il ne pese que
    le NOMBRE de voisins ennemis.

    L'adjacence passe par `battle_query.is_adjacent` (liste de voisinage STOCKEE + porte d'elevation
    `|delta| < 2` d'`IdunBattle.Core.Services.TileQuery.u003CIterateAdjacentTilesu003Ed__8$$
    MoveNext`), le meme foyer que toutes les feuilles ring-1 -- et non `hexgeo.distance == 1`, qui
    SUR-COMPTE au bord d'une marche (#271)."""

    ABILITY_ID = TriggeredAbilityType.ObsessiveAnnunciation               # 0x5a3 = 1443
    WEIGHT_KEY = "ObsessiveAnnunciation_LikesAdjacentEnemy"               # = 10 (capture)

    def calculate_movement_utility_in_steps(self, tile, ctx: dict, wt) -> float:
        w = wt.sub("TriggeredAbilities", self.WEIGHT_KEY)
        if not w:
            return 0.0
        ctx = ctx or {}
        # `enemy_units` = les unites NON controlees, vivantes et positionnees (`utilities/tile.py::
        # _adjacent_units`). Le natif demande les ennemis de `case.unit`, donc AUCUNE inclusion de
        # self -- meme forme que `legacy_of_combat`, dont ce corps est le decalque a la CLE et au
        # SLOT pres.
        n = bq.count_adjacent(tile, [u["pos"] for u in (ctx.get("enemy_units") or ()) if u.get("pos")],
                              ctx.get("elev_by_pos"), bq.neigh_map(ctx))
        return float(w * n)
