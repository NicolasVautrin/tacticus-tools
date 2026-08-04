"""#462-r4e-o -- le tag `Amount` per-coup est BORNE aux PV restants, pas le degat brut.

Le natif n'ecrit JAMAIS le degat demande dans le tag `Amount` (TagKey 225) de l'event
`UnitDamaged`. `IdunBattle.Core.Services.StreamHelper$$GetDamageTags` le lit dans le champ @+0 de
la valeur de retour d'`IdunBattle.Operations.ApplyDamageOperation$$Execute`, un accumulateur
alimente par EXACTEMENT deux termes, tous deux des retraits REELLEMENT appliques :

    amount  = FillUpStatComponent.Reduce(healthComponent, dar.healthDamage, ignoreMinimum:false)
    amount += ApplyDamageOperation.ReduceShield(unit, dar.shieldDamage)

et l'ETAGE QUI BORNE est `IdunBattle.Entities.Components.FillUpStatComponent$$Reduce` :
`Min(Max(0, damage), Current)`, plus le plancher `Minimum` (`Nullable<int>` @+0x1c). Le surplus part
dans le compteur @+0x24, PAS dans le retour. Port : `damage_amount_applied` (`damage_hits.py`).

CE QUE CE FICHIER GARDE, et pourquoi CES regimes -- un seul coup letal ne separe PAS
« borner le coup letal » de « borner aux PV restants A CHAQUE COUP » (regime degenere) :

  * `letal`     (MC1_67 / 31337) : la cible meurt au DERNIER coup, un seul coup est ecrete ;
  * `cadavre`   (C3_01  / 777)   : la cible meurt au coup 3 -- ecrete PARTIELLEMENT -- et le coup 4
                                   tombe sur un cadavre (`Amount` 0). C'est LE regime qui tranche :
                                   sans borne per-coup le port rendait `[.., 2289, 2203]` la ou le
                                   natif ecrit `[.., 979, 0]` ;
  * `survivant` (MC1_67 / 31337, `--hp-target` eleve) : la cible SURVIT, la borne est INACTIVE et
                                   `per_hit` reste le degat brut -- temoin de non-regression.

Chaque test ASSERTE d'abord que son regime est bien celui qu'il croit mesurer (mort / coup a 0 /
survie), pour qu'un montage devenu degenere rougisse au lieu de passer pour une preuve.

Contre-epreuve (probe, hors pytest) :
`python scripts/python/probe_462_r4e_o_overkill_amount.py --mutate brut` restaure le port d'avant
et fait diverger `letal` et `cadavre`, jamais `survivant`.
"""
from __future__ import annotations

import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__)))))
sys.path.insert(0, os.path.dirname(__file__))      # tests/engine/runner -> helper sibling

from _combat_replay import replay_normal_attack  # noqa: E402

ATTACKER = "astraBullgryn"       # 4 coups melee, profil vanilla (aucun modificateur de degat)
TARGET = "eldarFarseer"          # cible vanille du catalogue #462-r4e


def _replay(build_runner, rpc, board, seed, extra=None):
    r = replay_normal_attack(rpc, build_runner, ATTACKER, target=TARGET,
                             extra=(["--board", board] + list(extra or [])), seed=seed)
    if not r["ok"]:
        pytest.fail(f"montage KO ({board}/{seed}): {r['reason']}", pytrace=False)
    if r["did_crit"] or r["did_block"] or r["did_evade"]:
        pytest.fail(f"coup non propre (crit/block/evade live) sur {board}/{seed} -- le regime "
                    "mesure n'est plus celui que ce fichier garde", pytrace=False)
    print(f"\n[{board}/{seed}] live={r['live_ph']} off={r['off_ph']} "
          f"hp_before={r['hp_before']} after live={r['live_after']} off={r['off_after']}")
    return r


def test_amount_borne_aux_pv_sur_le_coup_letal(live_session, rpc, build_runner):
    """La salve depasse les PV : la somme des `Amount` vaut EXACTEMENT les PV de depart."""
    r = _replay(build_runner, rpc, "MC1_67", "31337")
    assert r["live_after"] == 0, "regime non OVERKILL : la cible survit, ce test ne mesure rien"
    assert sum(r["live_ph"]) == r["hp_before"], (
        f"le natif ne borne pas ici : somme des Amount {sum(r['live_ph'])} != PV {r['hp_before']}")
    assert r["exact"], (f"degat offline != live -- per_hit off={r['off_ph']} live={r['live_ph']} "
                        f"(off_after={r['off_after']} live_after={r['live_after']})")


def test_amount_nul_sur_un_coup_apres_la_mort(live_session, rpc, build_runner):
    """Regime DISCRIMINANT : un coup tombe apres que les PV sont a 0 -> `Amount` 0, et le coup
    letal est ecrete PARTIELLEMENT (aux PV qui restaient), pas au dernier index."""
    r = _replay(build_runner, rpc, "C3_01", "777")
    assert r["live_after"] == 0, "regime non OVERKILL : la cible survit"
    assert r["live_ph"][-1] == 0, (
        f"aucun coup apres la mort dans ce montage (live={r['live_ph']}) -- le regime ne "
        "discrimine plus « borne au coup letal » de « borne aux PV restants par coup »")
    assert sum(r["live_ph"]) == r["hp_before"], (
        f"somme des Amount {sum(r['live_ph'])} != PV {r['hp_before']}")
    assert r["exact"], (f"degat offline != live -- per_hit off={r['off_ph']} live={r['live_ph']} "
                        f"(off_after={r['off_after']} live_after={r['live_after']})")


def test_amount_inchange_quand_la_cible_survit(live_session, rpc, build_runner):
    """Temoin de NON-REGRESSION : hors overkill la borne est inactive et `per_hit` reste le brut."""
    r = _replay(build_runner, rpc, "MC1_67", "31337", ["--hp-target", "999999"])
    assert r["live_after"] > 0, "la cible meurt : ce temoin ne teste plus le regime NON borne"
    assert sum(r["live_ph"]) < r["hp_before"], "la salve depasse les PV -- temoin invalide"
    assert r["exact"], (f"degat offline != live HORS overkill -- per_hit off={r['off_ph']} "
                        f"live={r['live_ph']}")
