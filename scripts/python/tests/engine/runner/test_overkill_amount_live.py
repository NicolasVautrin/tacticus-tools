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
                                   `per_hit` reste le degat brut -- temoin de non-regression ;
  * `multi_cadavre` (MC1_67 / 31337, `--hp-target 2000`) : la cible tombe DES LE 1er coup et DEUX
                                   coups au moins tombent derriere elle. Ce regime ne garde pas la
                                   borne mais la CARDINALITE (#462-r4e-o-r1) : le SITE (A) d'
                                   `IdunBattle.Operations.ApplyDamageOperation$$Execute`
                                   (`if (UnitExtensions.HasFlag(target, 8 = Overkilled)) { ... ;
                                   return; }`) PRECEDE toute emission, donc les coups qui suivent la
                                   pose du flag n'emettent RIEN. Le port en emettait un par coup :
                                   `[2000, 0, 0, 0]` la ou le natif rend `[2000, 0]`.

Chaque test ASSERTE d'abord que son regime est bien celui qu'il croit mesurer (mort / coup a 0 /
survie / au moins deux coups apres la mort), pour qu'un montage devenu degenere rougisse au lieu de
passer pour une preuve.

Contre-epreuves (probe, hors pytest) :
`python scripts/python/probe_462_r4e_o_overkill_amount.py --mutate brut` restaure le port d'avant
#462-r4e-o et fait diverger `letal` et `cadavre`, jamais `survivant` ;
`... --mutate cardinalite --only multi_cadavre` ouvre le SITE (A) (port d'avant #462-r4e-o-r1) et
fait re-apparaitre EXACTEMENT `[2000, 0, 0, 0]`.
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


# Confonds NEUTRALISES AU BUILD (#419-r6). ARBITRAGE : ce fichier ne skippe pas sur un coup non
# propre -- il ECHOUE, en disant lui-meme que « le regime mesure n'est plus celui que ce fichier
# garde ». C'est exact : ce qu'il verrouille est la BORNE de `Amount` aux PV restants, et cette
# borne se lit sur l'egalite `sum(live_ph) == hp_before`, donc sur des montants NUS. Il obtenait
# ses coups propres SANS RIEN DEMANDER tant que le canal crit/block etait globalement muet, et
# depuis que le defaut equipe (#419-r6) les 4 tests tombaient. Les QUATRE faces
# (`--crit`/`--block-player` n'epinglent que les p-units, `--crit-target`/`--block-target` que
# les a-units).
_NO_NOISE = ["--crit", "0,0", "--crit-target", "0,0",
             "--block-target", "0,0", "--block-player", "0,0"]


def _replay(build_runner, rpc, board, seed, extra=None):
    r = replay_normal_attack(rpc, build_runner, ATTACKER, target=TARGET,
                             extra=(["--board", board] + _NO_NOISE + list(extra or [])),
                             seed=seed)
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


def test_cardinalite_deux_coups_apres_la_mort_ne_donnent_QU_UN_event(
        live_session, rpc, build_runner):
    """#462-r4e-o-r1 -- le SITE (A) COUPE l'emission. La cible tombe au 1er coup ; le natif emet le
    coup letal, PUIS un seul event a `Amount` 0 (le coup qui POSE `UnitFlag.Overkilled` emet encore,
    la pose precede l'emission dans le MEME `Execute`), et RIEN pour les coups suivants.

    Le montage est ASSERTE : il faut une arme d'au moins 3 coups et une mort des le 1er, sinon le
    regime ne discrimine plus « le coup letal coupe tout » de « le coup d'APRES coupe »."""
    r = _replay(build_runner, rpc, "MC1_67", "31337", ["--hp-target", "2000"])
    assert r["live_after"] == 0, "la cible survit : ce regime ne mesure aucune cardinalite"
    assert (r["hits"] or 0) >= 3, (
        f"montage degenere : {r['hits']} coups -- il en faut >= 3 pour qu'AU MOINS DEUX tombent "
        "apres la mort (avec un seul, la coupure est invisible)")
    assert len(r["live_ph"]) < (r["hits"] or 0), (
        f"le natif emet {len(r['live_ph'])} events pour {r['hits']} coups : aucun coup n'est gate, "
        "le flag `Overkilled` n'a pas ete pose -- montage a revoir")
    assert r["live_ph"][-1] == 0 and sum(r["live_ph"]) == r["hp_before"], (
        f"forme inattendue du live {r['live_ph']} (PV {r['hp_before']})")
    assert r["off_ph"] == r["live_ph"], (
        f"CARDINALITE : off={r['off_ph']} live={r['live_ph']} -- meme somme "
        f"({sum(r['off_ph'])}/{sum(r['live_ph'])}) et meme etat "
        f"({r['off_after']}/{r['live_after']}), mais {len(r['off_ph']) - len(r['live_ph'])} "
        "event(s) en trop : le SITE (A) ne gate plus")
