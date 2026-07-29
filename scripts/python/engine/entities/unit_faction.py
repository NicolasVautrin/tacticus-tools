"""engine.entities.unit_faction -- enum natif `UnitFaction` (id <-> nom) + resolution offline.

Mirror 1:1 de `IdunBattle.Entities.Enum.UnitFaction` (21 membres), transcrit depuis la table de
symboles VERSIONNEE du build (`data/symbols/<build>/frida/enums.tsv`, ligne
`IdunBattle.Entities.Enum.UnitFaction`). Meme precedent que `UnitTrait` (#146),
`TriggeredAbilityType` (#158) et `utilities/utility_type.py` : un enum natif standalone -> son
propre module, foyer unique du mapping.

POURQUOI un module et pas un litteral : `IdunBattle.Entities.UnitExtensions$$HasFaction(unit,
<UnitFaction>)` ne compare PAS un entier. Il fait `System.Enum.ToString(UnitFaction)` puis
`String.Equals` contre `FactionComponent+0x30` -- la faction est une CHAINE cote natif. Le pendant
offline de ce champ est le `FactionId` du gameconfig ; c'est cet enum qui fait le pont
`FactionId (str) <-> valeur d'enum (int)` que les gates du port expriment en entier
(ex. `AttractToDecoysUtility` : `HasFaction(case.unit, 0xf)` = `UnitFaction.Genestealers`).
"""
from __future__ import annotations

import functools
from enum import IntEnum


class UnitFaction(IntEnum):
    """`IdunBattle.Entities.Enum.UnitFaction`. Valeur == valeur d'enum natif ; nom == `FactionId`
    gameconfig (le `System.Enum.ToString` que `HasFaction` compare)."""
    Ultramarines = 0
    Sisterhood = 1
    AstraMilitarum = 2
    BlackLegion = 3
    DeathGuard = 4
    Orks = 5
    BlackTemplars = 6
    Necrons = 7
    Aeldari = 8
    Tau = 9
    DarkAngels = 10
    ThousandSons = 11
    Tyranids = 12
    SpaceWolves = 13
    BloodAngels = 14
    Genestealers = 15
    AdeptusMechanicus = 16
    WorldEaters = 17
    Custodes = 18
    EmperorsChildren = 19
    LeaguesOfVotann = 20


UNIT_FACTION_NAMES: dict = {int(f): f.name for f in UnitFaction}
UNIT_FACTION_VALUES: dict = {f.name: int(f) for f in UnitFaction}


@functools.lru_cache(maxsize=None)
def faction_value(visual_id: str | None):
    """Valeur d'enum `UnitFaction` de l'unite `visual_id`, ou `None` si inconnue.

    Substrat offline = `gameconfig.unit(visual_id)["FactionId"]` (la chaine que le natif compare) ;
    meme source que `engine.playbook.adjacent_unit_preference._unit_faction` et que le selecteur
    `UnitsFromFaction`. Un `FactionId` absent de l'enum (unite d'environnement, objet de plateau)
    rend `None` -- le gate appelant retombe alors sur son cas « pas cette faction »."""
    if not visual_id:
        return None
    import gameconfig as GC                       # lazy : engine ne depend pas de gameconfig a l'import
    name = (GC.unit(visual_id) or {}).get("FactionId")
    return UNIT_FACTION_VALUES.get(name) if name else None
