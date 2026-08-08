"""GARDE LIVE de #BL-1020r et #120bis-spawn -- les deux MESURES, jouees contre le natif.

Les gardes OFFLINE (`test_bl_1020r_herald_extra_damage_offline.py`,
`test_120bis_spawn_tile_offline.py`) figent la STRUCTURE du port : registre, gates, ordinal, signe
du poids. Elles ne peuvent pas dire que le resultat est celui du jeu. Ce fichier-ci confronte, et
il n'existe que parce que les deux probes portent chacun leur CONTRE-EPREUVE -- sans elle, un
accord ne separerait pas << le port fait la bonne chose >> de << ni le port ni le natif ne font
rien >> :

  * `probe_bl_1020r_herald_extra_damage.py` -- coups offline == coups live BIT-EXACT ; PLUS la
    contre-epreuve interne (classe 1027 neutralisee -> le total CHANGE de `6 x extraDmg[L50] x
    mult`) ; PLUS le retrait, verifie des deux cotes. Le probe REFUSE de conclure si la classe ne
    mord pas.
  * `probe_120bis_spawn_tile.py` -- `d(attaquant, creed)` apres la cascade, offline vs live, sur
    TROIS positions d'attaquant. Le probe ECARTE tout montage a moins de 2 tuiles libres autour de
    Creed (regime degenere : le tri coincide avec l'enumeration) et REFUSE de conclure si le natif
    rend la meme distance partout.

Chacun monte ses propres runners et les dispose. RE : `docs/rl/case-bl-1029-1020.md` Sec.7.2 et
`docs/rl/case-120bis-flailswing-haze-confound.md` Sec.8. ASCII only.
"""
from __future__ import annotations

#: Ce qui doit changer pour que ce FICHIER de test puisse changer de verdict (#486-r15).
DECLENCHEUR = {
    "chemins": (
        # SOCLE COMMUN a TOUT fichier de test : la cascade des `conftest.py` et sa fermeture.
        "scripts/python/conftest.py", "scripts/python/tests/conftest.py",
        "scripts/python/tests/engine/conftest.py",
        "scripts/python/tests/engine/runner/conftest.py",
        "scripts/python/green_skip_guard.py", "scripts/python/declencheur_guard.py",
        "scripts/python/catalog_inject.py",
        "scripts/python/gameconfig.py", "scripts/python/enum_maps.py",
        "scripts/python/host_inputs.py", "scripts/python/rl_collect_batch.py",
        "scripts/python/stream_events.py", "scripts/python/symbols_layout.py",
        "scripts/python/engine/runner/snapshot.py",
        # Les DEUX probes que ce fichier joue, et tout le moteur qu'ils exercent.
        "scripts/python/probe_bl_1020r_herald_extra_damage.py",
        "scripts/python/probe_120bis_spawn_tile.py",
        "scripts/python/rl_duel.py", "scripts/python/hexgeo.py",
        "scripts/python/engine/*.py",
        "scripts/python/engine/**/*.py",
        "data/seed-bc.json", "data/boards/**", "data/symbols/**",
    ),
    "build": True,
    # LIVE : le verdict depend de la session Frida et du binaire du jeu, que ce dict ne peut pas
    # enumerer. `toujours` est donc l'aveu honnete du perimetre, pas une commodite.
    "toujours": True,
    "raison": "Confront LIVE : les deux probes montent des runners et comparent le port au natif "
              "(magnitude bit-exacte + contre-epreuve chiffree pour 1027 ; accord de "
              "`d(att, creed)` sur trois geometries pour la tuile de spawn). Le verdict depend de "
              "la session Frida et du binaire charge -- aucune liste de chemins ne le borne.",
}

import importlib


def test_1027_magnitude_bit_exacte_retrait_et_contre_epreuve_live():
    """`PROBE OK` exige les TROIS : coups offline == coups live, la classe MORD (contre-epreuve),
    et 1027 present avant / absent apres, des deux cotes."""
    probe = importlib.import_module("probe_bl_1020r_herald_extra_damage")
    assert probe.main([]) == 0


def test_la_tuile_de_spawn_accorde_avec_le_natif_sur_trois_geometries_live():
    """`PROBE OK` exige l'accord de `d(att, creed)` sur les trois montages NON DEGENERES, et le
    probe rend `2` (ni OK ni KO) plutot que de conclure si le natif rend la meme distance partout."""
    probe = importlib.import_module("probe_120bis_spawn_tile")
    assert probe.main([]) == 0
