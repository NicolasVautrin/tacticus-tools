"""Mirror d'`IdunBattle.Entities.TileExtensions` — les lectures d'une TUILE et de son occupant.

POURQUOI CE MODULE EXISTE, et pourquoi son emplacement est FONCTIONNEL et non cosmetique (#477-r35) :

`GetSteppableUnit` vivait dans `engine.utilities.tile` sous le nom `_steppable_occupant`, avec un
seul consommateur (`apply_tile_attributes`). `HaywireMineNonOwnerPlaybook` en est devenu un second
— et `engine.playbook.non_owner` ne peut PAS importer `engine.utilities.tile` : c'est `tile` qui
importe `non_owner`, pas l'inverse. Le dupliquer aurait donne deux lectures du meme natif libres de
diverger sans que rien ne le dise.

DEUX EMPLACEMENTS ONT ETE ESSAYES ET MESURES AVANT CELUI-CI. Les deux CASSAIENT un import qui
marchait sur master, et **aucune passe pytest ne pouvait le voir** (un cycle Python est sensible a
l'ORDRE : il se dissout des qu'un appelant importe `engine.entities` en premier, ce que font tous
nos tests). C'est un probe VERSIONNE, `probe_433_r1_identity_shortcircuit.py`, qui importe
`engine.battle_query` en tete, qui a paye les deux.

1. **`engine/battle_query.py`** -- `python -c "import engine.battle_query"` LEVE. Ce module a
   besoin d'`UnitTrait`, donc d'`engine.entities`, dont l'`__init__.py` cascade
   `effects_state` -> `effects/__init__` -> `factory` -> `loki/__init__` ->
   `ability_modifications` -> `selectors/units.py` -> `from ...battle_query import
   is_target_tile_obscured`, sur un `battle_query` PARTIELLEMENT initialise. `battle_query` doit
   donc rester SANS aucune dependance `engine.entities` -- c'est ce qui le rend importable en
   premier.
2. **`engine/tile_extensions.py`** (racine du paquet) -- `python -c "import
   engine.tile_extensions"` LEVE a son tour, par une arete RETOUR : la meme cascade atteint
   `selectors/tiles.py` -> `engine/utilities/__init__` -> `engine/utilities/tile.py`, qui importe
   ce foyer au niveau module. Un module de la RACINE d'`engine` qui depend d'`entities` est donc
   re-entre par la cascade, quel que soit son nom.

**ICI, sous `engine/entities/`, il n'y a plus d'arete.** Quand la cascade atteint
`utilities/tile.py` et que celui-ci fait `from ..entities.tile_extensions import
get_steppable_unit`, `engine.entities` est partiel mais CE sous-module n'est pas encore commence :
il se charge INTEGRALEMENT (il ne depend que de `.traits.unit_trait`, deja charge a ce stade) et
rend son symbole. Le cycle est **SUPPRIME, pas retarde** -- les trois consommateurs
(`utilities/tile.py`, `playbook/non_owner.py`, et ce module) importent tous au NIVEAU MODULE, et
**aucun import differe n'existe dans cette chaine**. Un differe aurait seulement cache la question.

C'est exactement le patron que le `CLAUDE.md` documente deja pour `AbilityConstantType` /
`AbilityVariableType` : « leur EMPLACEMENT est fonctionnel, pas cosmetique [...] ils vivent donc
sous `engine/entities/`, comme `effect_type.py` ». Meme cause, meme remede.

⚠ Le garde de ce placement est `probe_477r35_import_isole.py` : il importe CHAQUE module
`engine.*` SEUL, en process frais, et compare a un checkout TEMOIN. C'est le seul dispositif du
depot qui voit ce gisement.

Et le nom est celui du natif : `IdunBattle.Entities.TileExtensions`, pas `BattleQuery`.
"""
from __future__ import annotations

from .traits.unit_trait import UnitTrait


def get_steppable_unit(pos, lc: dict) -> "dict | None":
    """`IdunBattle.Entities.TileExtensions$$GetSteppableUnit(tile, matchState, out steppableUnit)`
    cote offline : l'OCCUPANT de `pos` s'il porte `UnitTrait.Steppable` (0x1b), sinon `None`.

        unit = UnitExtensions.GetUnit(tile, matchState);      // TileContentComponent.IsFilled
        return unit != null && unit.BaseUnitComponent?.HasTrait(0x1b) == true;

    Une tuile n'a qu'UN occupant (le `TileContentComponent` porte un seul id) : trouver une unite
    NON steppable sur `pos` fait donc rendre `None`, pas continuer a chercher.

    Rend `{is_friend, is_enemy, is_decoy, triggered, vis}` :
      * les quatre premieres cles sont les lectures que `SteppableUnitUtility` fait ensuite sur `u`
        (`IsFriend`/`IsEnemy` contre `case.unit`, `HasTrait(0x41d)`, `HasTriggeredAbility`).
        `is_friend`/`is_enemy` sont DEUX booleens et non l'un la negation de l'autre par principe :
        le natif interroge des predicats DIFFERENTS selon la branche. Ici ils sont complementaires,
        comme le natif quand `case.unit != null` ;
      * `vis` (#477-r35) est l'id d'unite de l'occupant, l'argument de
        `IdunBattle.Entities.UnitExtensions$$HasUnitId(unit, unitId, state)` que lit
        `HaywireMineNonOwnerPlaybook`. Ce champ ne coute rien aux deux feuilles historiques (elles
        ne le lisent pas) et il est le SEUL canal par lequel un playbook peut IDENTIFIER
        l'occupant ; sans lui la face 1531 rendrait 0 partout.

    Le MOVER est traite a part : `_adjacent_units` l'EXCLUT de `friend_units` (self-exclu), or sur
    sa tuile d'ORIGINE c'est lui l'occupant -- `IsFriend(self, self)` est vrai (meme playerId)."""
    if lc.get("self_pos") == pos:
        traits = set(lc.get("unit_traits") or ())            # ids (`entity_trait_ids`)
        if int(UnitTrait.Steppable) not in traits:
            return None
        return {"is_friend": True, "is_enemy": False,
                "is_decoy": int(UnitTrait.Decoy) in traits,
                "triggered": tuple(lc.get("unit_triggered_abilities") or ()),
                "vis": lc.get("self_vis")}
    for units, is_friend in ((lc.get("friend_units") or (), True),
                             (lc.get("enemy_units") or (), False)):
        for u in units:
            if u.get("pos") != pos:
                continue
            names = u.get("traits") or ()                    # noms (`entity_trait_names`)
            if UnitTrait.Steppable.name not in names:
                return None                                  # occupant NON steppable -> false
            return {"is_friend": is_friend, "is_enemy": not is_friend,
                    "is_decoy": UnitTrait.Decoy.name in names,
                    "triggered": tuple(u.get("triggered") or ()),
                    "vis": u.get("vis")}
    return None
