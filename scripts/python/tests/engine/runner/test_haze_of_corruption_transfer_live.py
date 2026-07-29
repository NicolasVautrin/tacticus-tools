"""case-209 -- GARDE du report de degat de `HazeOfCorruption` (effet 0x435 = 1077).

Critere : quand la cible d'un `deathBlightlord` MEURT sous le coup, le RELAIS bonde encaisse-t-il
EXACTEMENT le meme degat cote port que cote natif ?

Les tests LIVE montent la geometrie CRAFTEE de `probe_207_haze_pool_ladder.py` (k = 1 : la cible
sur un voisin du porteur, UN ennemi sur un voisin commun) et font varier les PV pour separer les
deux regimes d'alimentation de `LeftOverDamage` :

  * PV 6000 -> la cible meurt au 3e coup, qui l'ENTAME (site C = `demande - applique`) ;
  * PV 5000 -> elle meurt au 2e, le 3e tombe sur le cadavre (site B = la BASE nominale) ;
  * PV 8000 -> elle SURVIT : aucun bond ne tire (garde anti-sur-tir).

Le regime 5000 est le discriminant : la BASE (2609) y est la MEME sur deux seeds aux jets d'arme
differents, ce qui refute « le leftover est le jet du coup ».

OFFLINE : les litteraux lus au decompile (event, effet, profil du coup bonus).
"""
from __future__ import annotations

import pytest

PROBE = "probe_209_haze_damage_transfer"


def _row(hp, seed="777"):
    import importlib
    P = importlib.import_module(PROBE)
    rpc = P._mkrpc()

    class _A:
        armor, k, dump_events = 0, 1, False
    r = P._run(rpc, seed, hp, _A())
    assert r is not None, "montage KO (seed %s hp %s)" % (seed, hp)
    return r


def _relay_damage(r):
    """(degat LIVE encaisse par le relais, degat PORT) -- le PORT part des PV forces `--hp-target`."""
    live = sum(int(td["tags"]["Amount"]) for td in r["events"]
               if "Amount" in td["tags"]
               and (td["tags"].get("Target_Id") == r["relay"]))
    port = None
    for e in r["off_entities"]:
        if e.get("id") == r["relay"] and e.get("hp") is not None:
            port = int(r["hp"]) - int(e["hp"])
    return live, port


# --------------------------------------------------------------------------- OFFLINE (litteraux)

def test_litteraux_lus_au_decompile():
    from engine.runner.operations.triggers.loki import haze_of_corruption as H
    from engine.dsl.event_trigger_type import EventTriggerType
    # `IdunBattleLogic.Entities.DSLFactory$$OnDeathEvent(eventId, allowOverkill, allowShield)` --
    # RELU VERBATIM (case-haze-bonded) : les deux enveloppes ne visent PAS le meme evenement.
    #   `OnPreDeath(1, 0)` -> `OnDeathEvent(**1** = PreUnitDeath, ...)`  [le coup BONUS]
    #   `OnDeath(1, 1)`    -> `OnDeathEvent(**0** = UnitDeath,    ...)`  [le REPORT 1077]
    # L'attendu precedent (les DEUX sur `PreUnitDeath`) transcrivait une lecture fautive de
    # `OnDeath` ; les 44 tests LIVE des quatre fichiers Haze restent verts apres la bascule.
    assert H.HazeCorruptionBonusHitAbility.event_id == int(EventTriggerType.PreUnitDeath)
    assert H.HazeOfCorruptionDamageTransferTrigger.event_id == int(EventTriggerType.UnitDeath)
    # `AddBondEffect(0x435, ...)` = EffectType 1077, la cle du registre effet-trigger.
    assert H.HazeOfCorruptionDamageTransferTrigger.effect_type == 0x435 == 1077
    # `GetDamageProfile(config)` de `HazeOfCorruption` (constante gameconfig).
    import gameconfig as GC
    assert ((GC.ability("HazeOfCorruption") or {}).get("constants") or {}).get("damageProfile") \
        == H.HAZE_BONUS_PROFILE
    assert ((GC.ability("HazeOfCorruption") or {}).get("constants") or {}).get("nrOfHits") == "1"


def test_les_deux_volets_sont_au_registre():
    from engine.runner.operations.triggers.dispatch.registry import (ABILITY_TRIGGERS,
                                                                     EFFECT_TRIGGERS)
    from engine.runner.operations.triggers.loki import haze_of_corruption as H
    assert H.HazeCorruptionBonusHitAbility in ABILITY_TRIGGERS["HazeOfCorruption"]
    assert H.HazeOfCorruptionDamageTransferTrigger in EFFECT_TRIGGERS[H.HAZE_DAMAGE_TRANSFER]


# --------------------------------------------------------------------------- LIVE

@pytest.mark.parametrize("hp", [6000, 5000])
def test_relais_encaisse_le_meme_degat_que_le_natif(hp):
    r = _row(hp)
    live, port = _relay_damage(r)
    assert live > 0, "la branche n'a pas tire (aucun degat sur le relais) : montage non concluant"
    assert port == live, "relais : port %s != natif %s (hp %s)" % (port, live, hp)


def test_cible_survivante_aucun_transfert():
    """Garde anti-sur-tir : la cible SURVIT -> aucun `LeftOverDamage`, aucun volet ne fire."""
    r = _row(8000)
    live, port = _relay_damage(r)
    assert live == 0 and port == 0
    assert r["trace"]["bonus_fire"] == 0 and r["trace"]["xfer_fire"] == 0


def test_base_nominale_invariante_sur_deux_seeds():
    """DISCRIMINANT : a PV 5000 la cible meurt au 2e coup et le 3e tombe sur le cadavre. Le montant
    reporte pour CE coup-la est la BASE nominale (site B), donc IDENTIQUE sur deux seeds dont les
    jets d'arme different -- ce qu'un modele « le leftover est le jet du coup » ne peut pas rendre."""
    a, b = _row(5000, "777"), _row(5000, "88")
    assert a["per_hit"] != b["per_hit"], "les deux seeds doivent avoir des jets DIFFERENTS"
    ea = [e for e in a["off_entities"] if e.get("id") == a["tid"]][0]["left_over"]
    eb = [e for e in b["off_entities"] if e.get("id") == b["tid"]][0]["left_over"]
    assert len(ea) == len(eb) == 3, "attendu 3 entrees (coup fatal + coup sur cadavre + coup bonus)"
    assert ea[1] == eb[1], "la 2e entree (site B) doit etre la MEME base sur les deux seeds"
    assert ea[2] == eb[2], "le coup bonus Toxic doit etre la MEME base sur les deux seeds"
    # et cette base doit etre le MILIEU de la cellule d'arme, pas un jet.
    lo, hi = a["cell"]
    assert ea[1]["amount"] == (int(lo) + int(hi)) // 2
