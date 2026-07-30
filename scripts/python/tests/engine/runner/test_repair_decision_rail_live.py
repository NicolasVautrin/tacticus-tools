"""#298 -- le rail de DECISION de la REPARATION, confronte au LIVE.

CE QUE CES TESTS VERROUILLENT, et pourquoi ils existent. #278 avait laisse un residu :
« `PredictRepair` n'est JAMAIS appele malgre 2 cibles legales », d'ou le soupcon d'un rail
inatteignable depuis le harnais runner. La mesure dit l'inverse -- le rail EXISTE, il est
COMPLET, et l'IA PROPOSE la reparation -- a une condition d'etat pres, qui est le vrai gate :

    `IdunBattle.Core.Services.AttackQuery$$EntityCanBeRepaired` exige
    `IdunBattle.Core.Services.AttackQuery$$IsDamagedUnit(entity)` ET
    `IdunBattle.Entities.UnitExtensions$$IsAffectedByHealType(entity, 1)`.

Une cible a 100 % de PV n'est donc PAS une cible de reparation, et rien en aval ne s'execute.
C'est un no-op SILENCIEUX : ni erreur, ni event -- exactement la forme qui se lit a tort
comme « le rail n'existe pas ».

Les trois tests separent une seule variable a la fois (meme roster, meme board, meme seed,
memes tuiles de spawn -- `advance=0`, aucun tour IA joue) :

  1. l'ability de reparation est-elle dans `IdunBattle.Entities.Components.ActiveAbilityComponent`
     (`Abilities` @0x20) et pas seulement dans le slot scalaire `RepairType` (@0x2c) ?
  2. cible MECANIQUE BLESSEE  -> l'IA propose l'`ActiveAbilityMessage` de reparation ;
  3. meme montage, cible a 100 % -> zero cible, aucune reparation proposee.

Le montage vit dans la fixture NOMMEE `repair_stage` (`tests/conftest.py` ->
`_repair_stage.build_stage`), jamais inline : le probe `probe_298_repair_rail.py` consomme
le MEME montage pour la mesure par etage (traces L1/L2).

ASCII only (console cp1252).
"""
from __future__ import annotations

import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(__file__))
from _repair_stage import REGULAR_REPAIR_IDS, build_stage   # noqa: E402


def _repair_entry(rpc, rid: int, unit_id: int) -> dict | None:
    """Entree `abilityTargets` de la reparation reguliere du repareur, ou None."""
    r = rpc("abilityTargets",
            {"runnerId": rid, "unitId": unit_id, "allAbilities": True},
            timeout=90)
    units = (r or {}).get("units") or []
    for a in (units[0].get("abilities") if units else []) or []:
        if a.get("abilityId") in REGULAR_REPAIR_IDS:
            return a
    return None


def _proposed_abilities(rpc, rid: int, unit_id: int) -> list[int]:
    """abilityTypes des `ActiveAbilityMessage` que l'IA propose pour `unit_id`."""
    dry = rpc("aiDryRunAllUnits", {"runnerId": rid}, timeout=300)
    for u in (dry or {}).get("units") or []:
        if u.get("unitId") == unit_id:
            return [a.get("abilityType") for a in (u.get("proposed") or [])
                    if a.get("cls") == "ActiveAbilityMessage"]
    return []


def test_repair_ability_lives_in_the_active_ability_component(repair_stage, rpc):
    """E0 -- la reparation derivee du trait `Mechanic` EST une entree d'`Abilities`.

    Elle sort en `kind="granted"` et non `"active"` : `ActiveAbilityComponent$$GetActives`
    la filtre (elle n'est pas une active « du kit »), `…$$GetUnusedAbilities` la rend. Les
    deux iterent la MEME collection -- donc
    `IdunBattle.AI.ActionGenerators.ActiveAbilityActionGenerator$$GetUnitAbilitiesInOrder`,
    qui itere cette collection SANS ce filtre, la voit. C'est ce qui rend le rail atteignable.
    """
    entry = _repair_entry(rpc, repair_stage["rid"], repair_stage["repairer"])
    assert entry is not None, (
        "aucune ability de reparation reguliere sur le repareur -- "
        f"{REGULAR_REPAIR_IDS} attendus")
    assert entry["kind"] == "granted", (
        "la reparation derivee doit sortir par GetUnusedAbilities (kind=granted) ; "
        f"kind={entry['kind']}")
    assert entry["fromHereCount"] >= 1, (
        "cible mecanique blessee et adjacente : le cast doit etre legal SANS bouger")


def test_ai_proposes_repair_when_a_mechanical_friend_is_damaged(repair_stage, rpc):
    """E2/E3 -- l'IA CHOISIT la reparation. Le rail va du generateur au message applique."""
    entry = _repair_entry(rpc, repair_stage["rid"], repair_stage["repairer"])
    assert entry is not None
    proposed = _proposed_abilities(rpc, repair_stage["rid"], repair_stage["repairer"])
    assert entry["abilityId"] in proposed, (
        f"l'IA devait proposer la reparation {entry['abilityId']} "
        f"({entry['ability']}) ; propose={proposed}")


def test_no_repair_target_when_the_mechanical_friend_is_at_full_health(build_runner, rpc):
    """Le CONTROLE : meme montage, seule la sante de la cible change.

    Sans ce test, le precedent ne prouve rien -- « ca marche » et « ca marche toujours »
    rendent le meme vert. Ici la cible est a 100 % : `AttackQuery$$IsDamagedUnit` est FAUX,
    `AttackQuery$$EntityCanBeRepaired` refuse, la reparation n'a aucune cible.
    """
    stage = build_stage(rpc, build_runner=build_runner,
                        hp_player=None, advance=0, damaged_repairee=None)
    entry = _repair_entry(rpc, stage["rid"], stage["repairer"])
    assert entry is not None, "l'ability reste dans Abilities meme sans cible"
    assert entry["targetCount"] == 0 and entry["fromHereCount"] == 0, (
        "une cible a 100 % de PV n'est pas reparable ; "
        f"targets={entry['targetCount']} fromHere={entry['fromHereCount']}")
    proposed = _proposed_abilities(rpc, stage["rid"], stage["repairer"])
    assert not (set(proposed) & set(REGULAR_REPAIR_IDS)), (
        f"aucune reparation ne doit etre proposee ; propose={proposed}")


@pytest.mark.parametrize("repairer,expected_id", [
    ("admecManipulus", 1119),        # passif GalvanicField -> Repair_GalvanicField
    ("admecDominus", 28),            # trait Mechanic seul   -> Repair
])
def test_both_regular_repair_ids_are_reachable(build_runner, rpc, monkeypatch,
                                               repairer, expected_id):
    """GENERALISATION -- les DEUX membres de `StaticBattleRules.ActiveAbility$$IsRegularRepair`.

    `{0x1c=28, 0x45f=1119}` : le trait `Mechanic` derive `Repair` (28) ; un passif qui
    specialise le slot `RepairType` (@0x2c) le remplace -- `GalvanicField` du Manipulus donne
    `Repair_GalvanicField` (1119). Un port qui n'aurait vu QUE le porteur du lot manquerait
    l'autre id, et le manquerait SILENCIEUSEMENT.
    """
    import _repair_stage as S
    monkeypatch.setattr(S, "REPAIRER_VIS", repairer)
    stage = S.build_stage(rpc, build_runner=build_runner,
                          hp_player=None, advance=0, damaged_repairee=2000)
    entry = _repair_entry(rpc, stage["rid"], stage["repairer"])
    assert entry is not None and entry["abilityId"] == expected_id, (
        f"{repairer} devait porter la reparation {expected_id} ; entry={entry}")
    proposed = _proposed_abilities(rpc, stage["rid"], stage["repairer"])
    assert expected_id in proposed, (
        f"l'IA devait proposer {expected_id} pour {repairer} ; propose={proposed}")
