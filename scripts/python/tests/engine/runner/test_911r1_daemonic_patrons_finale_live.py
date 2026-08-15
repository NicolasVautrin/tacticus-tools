"""#911-r1 -- CONFRONTATION LIVE de la face SUCCESS de `DaemonicPatrons_Finale` (triggered 1473).

PORTE PYTEST du montage `probe_911r1_daemonic_patrons_finale_live.py` : le probe MESURE (seed BC
augmente d'`emperFlawlessBlade`, positions DRIVEES, cast reel de 1203, cycle de tour, kill live
puis rejeu OFFLINE sur le meme flux PRNG), ce module ASSERTE. Aucun montage n'est duplique ici.

## CE QUE CE FICHIER GARDE, ET POURQUOI IL N'EXISTAIT PAS AVANT

`1473` n'est **ni dans `activeAbilities` ni dans `passiveAbilities`** du kit d'`emperFlawlessBlade` :
elle est montee par `StaticBattleRules.ActiveAbility$$.cctor`, qui construit
`GetDerivedTriggeredAbilities[0x4b3 = 1203] = [0x5c1 = 1473]`. Cote port, c'est l'entree
`"DaemonicPatrons"` d'`ACTIVE_ABILITY_TRIGGERS` qui materialise la derivation -- **aucune entree de
kit ne la donnerait**. La contre-epreuve de ce fichier retire cette entree : c'est la seule facon de
montrer que l'accord ne vient pas d'un cycle de tour qui re-armerait tout seul.

La face SUCCESS restait NON CONFRONTEE tant que le port etait INERTE offline : il retirait le taunt
27 du mourant AVANT `On(UnitDefeated)`. Cet etage est leve par **#1088** (`IEffect` slot 4
`get_RemoveOnDeathStep` = `2 = AfterDeathTrigger` sur `TauntedEffect`, corps `b8 02 00 00 00 c3`) --
d'ou `scripts/python/engine/entities/effects/loki/status.py` dans le declencheur ci-dessous : c'est
lui qui rend ce fichier capable de changer de verdict.

## LE TEMOIN N'EST PAS DEGENERE -- deux bras, UN conjoint d'ecart

  * `TAUNTE`     -- Hascule acheve la victime QU'IL A TAUNTEE : les quatre conjoints de
    `...DaemonicPatrons_FinaleSuccessAbility$$CreateTrigger` sont vrais, le natif re-arme 1203 ;
  * `NON TAUNTE` -- meme kill, meme attaque normale, meme buff 1464 sur lui, mais la victime n'a
    jamais porte le taunt : `HasEffect(Target@<DSLSelectors+0x60>, 0x1b = 27, onlyActive 0, 6)`
    tombe, et le natif ne re-arme PAS.

Un port qui re-armerait sur TOUT kill concorderait sur le premier bras seul. Un port qui ne
re-armerait JAMAIS concorderait sur le second seul.

ASCII only (console cp1252).
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

_PY = Path(__file__).resolve().parents[3]
if str(_PY) not in sys.path:
    sys.path.insert(0, str(_PY))
if str(Path(__file__).resolve().parent) not in sys.path:
    sys.path.insert(0, str(Path(__file__).resolve().parent))

import probe_911r1_daemonic_patrons_finale_live as P     # noqa: E402

#: Ce qui doit changer pour que ce FICHIER de test puisse changer de verdict (#486-r15).
#: `build: True` : la mesure est LIVE (binaire du jeu + gameconfig : kit d'`emperFlawlessBlade`,
#: paliers de 1203, `GetDerivedTriggeredAbilities`).
DECLENCHEUR = {
    "chemins": (
        "scripts/python/probe_911r1_daemonic_patrons_finale_live.py",
        # Les DEUX faces portees de la triggered derivee, et le registre qui les materialise.
        "scripts/python/engine/runner/operations/triggers/loki/daemonic_patrons.py",
        "scripts/python/engine/runner/operations/triggers/dispatch/registry.py",
        "scripts/python/engine/runner/abilities/emperorschildren.py",
        "scripts/python/engine/entities/effects/loki/daemonic_patrons.py",
        # L'ETAGE #1088 : sans `AfterDeathTrigger` sur `TauntedEffect`, la face SUCCESS est INERTE
        # offline (le taunt du mourant part avant l'event) -- ce fichier rendrait un desaccord.
        "scripts/python/engine/entities/effects/loki/status.py",
        "scripts/python/engine/entities/effects/base.py",
        "scripts/python/engine/entities/kill_unit_step.py",
        "scripts/python/engine/runner/operations/remove_effects.py",
        # Le chemin de mort : c'est lui qui emet `On(UnitDeath)` / `On(UnitDefeated)`.
        "scripts/python/engine/runner/operations/damage.py",
        # `ResetActiveAbility` et son gate : l'observable EST l'etat d'utilisation de l'actif.
        "scripts/python/engine/runner/operations/ability_reset.py",
        "scripts/python/engine/runner/components.py",
        # Le harnais qui monte la bataille et rejoue le coup offline.
        "scripts/python/tests/engine/runner/_charge_regime.py",
        "scripts/python/rl_duel.py", "scripts/python/catalog_inject.py",
        "scripts/python/tests/conftest.py",
    ),
    "build": True,
    "toujours": False,
    "raison": ("Confrontation LIVE de la face SUCCESS de 1473 : tout ce qui change la derivation "
               "de la triggered, le predicat de son trigger, le step de retrait du taunt, le "
               "chemin de mort ou l'ecriture de l'actif peut retourner le verdict. `build: True` "
               "parce que la mesure lit le jeu."),
}


class _Args:
    """Les memes defauts que le CLI du probe -- un objet plutot qu'un `argparse.Namespace` pour
    que le montage du test soit LISIBLE au site."""

    def __init__(self, non_taunte: bool):
        self.seed = "777"
        self.board = "MC1_67"
        self.target_unit = "necroWarden"
        self.other_unit = "necroOverlord"
        self.third_unit = "necroSpyder"
        self.hp_target = 20000
        self.dmg = 400000
        self.non_taunte = non_taunte
        self.verbose = False


@pytest.fixture(scope="module")
def _seed_bc():
    """Seed BC AUGMENTE d'`emperFlawlessBlade` : le porteur est HORS pool et HORS seed BC, et ce
    n'est PAS un refus (aucun `data/unspawnable_rank*.json` ne le nomme)."""
    p = P.seed_bc_avec_hascule()
    yield p
    Path(p).unlink(missing_ok=True)


def _mesure(rpc, build_runner, seed_bc, non_taunte: bool):
    a = _Args(non_taunte)
    r = build_runner(seed=a.seed, board=a.board, extra=[
        "--seed-bc", seed_bc,
        "--p-units", "%s,%s" % (P.CARRIER, P.ALLY),
        "--a-units", "%s,%s,%s" % (a.target_unit, a.other_unit, a.third_unit),
        "--hp-target", str(a.hp_target), "--hp-player", "900000",
        "--unit-stat", "%s:Damage=%d" % (P.CARRIER, a.dmg),
        "--no-ai", "--crit", "0,0", "--block-target", "0,0"])
    from engine.entities.pathfinding.board import Board
    from _charge_regime import ChargeRegimeHarness
    return P.mesurer(a, rpc, Board, ChargeRegimeHarness, r["rid"])


@pytest.fixture(scope="module")
def bras_taunte(rpc, build_runner, _seed_bc):
    return _mesure(rpc, build_runner, _seed_bc, non_taunte=False)


@pytest.fixture(scope="module")
def bras_non_taunte(rpc, build_runner, _seed_bc):
    return _mesure(rpc, build_runner, _seed_bc, non_taunte=True)


def _exige_regime(m):
    """Un montage rate n'est PAS un accord : il doit FAIRE ECHOUER, jamais passer en silence."""
    if not m.get("ok"):
        pytest.fail("regime NON ATTEINT (%s) : %s" % (m.get("bras"), m.get("why")), pytrace=False)
    if not (m["live"] or {}).get("mort"):
        pytest.fail("la cible n'est pas morte LIVE (%s)" % m.get("bras"), pytrace=False)
    if not (m["offline"] or {}).get("mort"):
        pytest.fail("la cible n'est pas morte OFFLINE (%s) -- les deux cotes ne jouent pas le "
                    "meme coup, l'accord ne prouverait rien" % m.get("bras"), pytrace=False)


@pytest.mark.parametrize("bras", ["taunte", "non_taunte"])
def test_l_actif_est_bien_CONSOMME_avant_le_kill(bras, bras_taunte, bras_non_taunte):
    """Sans consommation prealable de 1203, `BattleQuery$$EntityCanHaveActiveAbilityReset` rend
    FAUX et `ResetActiveAbility` est un no-op : les deux bras rendraient le meme observable."""
    m = bras_taunte if bras == "taunte" else bras_non_taunte
    _exige_regime(m)
    assert (m["avant"] or {}).get("usable") is False, m["avant"]


def test_le_natif_RE_ARME_sur_un_kill_TAUNTE(bras_taunte):
    """Les quatre conjoints de `CreateTrigger` sont vrais -> `ResetActiveAbility(Owner,
    allowUseless: 1)`."""
    _exige_regime(bras_taunte)
    assert (bras_taunte["live"]["apres"] or {}).get("usable") is True, bras_taunte["live"]


def test_le_natif_NE_RE_ARME_PAS_sur_un_kill_NON_TAUNTE(bras_non_taunte):
    """Seul `HasEffect(Target, 27)` change entre les deux bras -- c'est lui qui doit mordre."""
    _exige_regime(bras_non_taunte)
    assert (bras_non_taunte["live"]["apres"] or {}).get("usable") is False, \
        bras_non_taunte["live"]


@pytest.mark.parametrize("bras", ["taunte", "non_taunte"])
def test_le_port_rend_le_MEME_verdict_que_le_natif(bras, bras_taunte, bras_non_taunte):
    m = bras_taunte if bras == "taunte" else bras_non_taunte
    _exige_regime(m)
    nat = (m["live"]["apres"] or {}).get("usable")
    port = (m["offline"]["apres"] or {}).get("usable")
    assert nat is not None and port is not None, (nat, port)   # NON MESURE != desaccord
    assert bool(port) == bool(nat), ("%s : port=%s natif=%s" % (m["bras"], port, nat))
    assert bool(nat) is bool(m["attendu"]), ("le NATIF ne fait pas ce que le bras attend : "
                                             "%s usable=%s" % (m["bras"], nat))


def test_la_CONTRE_EPREUVE_mord_sur_le_bras_taunte(bras_taunte):
    """Retirer `"DaemonicPatrons"` d'`ACTIVE_ABILITY_TRIGGERS` = la vue d'AVANT ce port (aucune
    `DaemonicPatronsFinaleSuccessAbility` instanciee). Elle DOIT changer l'observable.

    ⚠ La comparaison porte sur `NOPORT != PORT`, pas sur `NOPORT is False` : ecrite ainsi, elle
    rendrait << mord >> alors que le port ne firerait pas -- donc sur un port et un mutant
    STRICTEMENT IDENTIQUES. C'est un faux vert deja rencontre sur ce montage meme."""
    _exige_regime(bras_taunte)
    port = (bras_taunte["offline"]["apres"] or {}).get("usable")
    noport = (bras_taunte["noport"]["apres"] or {}).get("usable")
    assert noport != port, ("NOPORT rend le MEME observable que le port (%s) -- l'accord ne "
                            "prouve rien" % port)


def test_la_contre_epreuve_ne_mord_PAS_sur_le_bras_non_taunte(bras_non_taunte):
    """Symetrique : la ou le trigger ne devait pas fire, le retrait du registre ne change RIEN.
    Sans ce cran, une contre-epreuve qui mordrait PARTOUT signalerait un port qui re-arme a tort."""
    _exige_regime(bras_non_taunte)
    port = (bras_non_taunte["offline"]["apres"] or {}).get("usable")
    noport = (bras_non_taunte["noport"]["apres"] or {}).get("usable")
    assert noport == port, ("le retrait du registre change l'observable sur un kill NON taunte "
                            "(port=%s noport=%s)" % (port, noport))
