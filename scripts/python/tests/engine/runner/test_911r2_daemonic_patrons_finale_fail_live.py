"""#911-r2 -- CONFRONTATION LIVE de la face FAIL de `DaemonicPatrons_Finale` (triggered 1473).

PORTE PYTEST du montage `probe_911r2_daemonic_patrons_finale_fail_live.py` : le probe MESURE (seed
BC augmente d'`emperFlawlessBlade`, positions DRIVEES, cast reel de 1203, ticks de fin de tour un
par un jusqu'au retrait de 1465, puis rejeu OFFLINE du MEME tick sur le meme flux PRNG), ce module
ASSERTE. Aucun montage n'est duplique ici.

## CE QUE CE FICHIER GARDE, ET POURQUOI IL N'EXISTAIT PAS AVANT

`#911-r1` a confronte la face SUCCESS (`On(0x36 = UnitDefeated)`). La face FAIL a un vecteur
DIFFERENT -- `On(0x40 = EffectRemoved) & get_OwnerIsTarget & CurrentAbilityIs(AbilityOrEffect(
0x5b9 = 1465)) & NOT CanUseAbility(Owner, 0x4b3 = 1203)` -- donc un montage different : il faut
attendre l'EXPIRATION de 1465, la ou le probe `-r1` s'arrete au kill. Elle restait en verdict
ANALYTIQUE (portee, jamais opposee au natif).

## LE TEMOIN N'EST PAS DEGENERE -- deux bras

  * `FAIL`   -- 1203 caste (donc 1465 pose ET l'actif consomme), aucun kill : au tick qui retire
    1465, le natif inflige `hpPct` % des PV COURANTS ;
  * `TEMOIN` -- MEMES ticks, MEME unite, AUCUN cast : ni 1465 a retirer, ni actif consomme. Aucune
    perte ne doit tomber. Sans lui, une chute de PV venue de tout AUTRE canal (DoT, effet de tuile,
    IA) se lirait comme la face FAIL.

Et la contre-epreuve `NOPORT` retire la classe `DaemonicPatronsFinaleFailAbility` de l'entree
`"DaemonicPatrons"` d'`ACTIVE_ABILITY_TRIGGERS` -- le registre qui materialise
`GetDerivedTriggeredAbilities[0x4b3] = [0x5c1]`. Elle DOIT changer l'observable, sinon l'accord ne
prouve rien.

MESURE (2026-08-18, `MC1_67` / seed 777, Hascule a 900 000 PV) : LIVE `900000 -> 630000`
(perte **270 000** = 30 % des PV COURANTS), OFFLINE **identique**, `NOPORT` **0**, TEMOIN **0** des
deux cotes.

ASCII only (console cp1252).
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

_PY = Path(__file__).resolve().parents[3]
if str(_PY) not in sys.path:
    sys.path.insert(0, str(_PY))
if str(Path(__file__).resolve().parent) not in sys.path:
    sys.path.insert(0, str(Path(__file__).resolve().parent))

import probe_911r2_daemonic_patrons_finale_fail_live as P     # noqa: E402

#: Ce qui doit changer pour que ce FICHIER de test puisse changer de verdict (#486-r15).
#: `build: True` : la mesure est LIVE (binaire du jeu + gameconfig : paliers de `hpPct`,
#: `GetDerivedTriggeredAbilities`, duree posee par 1203).
DECLENCHEUR = {
    "chemins": (
        "scripts/python/probe_911r2_daemonic_patrons_finale_fail_live.py",
        "scripts/python/probe_911r1_daemonic_patrons_finale_live.py",
        # Les DEUX faces portees de la triggered derivee, et le registre qui les materialise.
        "scripts/python/engine/runner/operations/triggers/loki/daemonic_patrons.py",
        "scripts/python/engine/runner/operations/triggers/dispatch/registry.py",
        "scripts/python/engine/runner/abilities/emperorschildren.py",
        "scripts/python/engine/entities/effects/loki/daemonic_patrons.py",
        # Le VECTEUR de la face FAIL : l'expiration par timer publie `On(0x40 = EffectRemoved)`
        # depuis le foyer de retrait, appele par le tick de fin de tour.
        "scripts/python/engine/entities/effects_state.py",
        "scripts/python/engine/runner/operations/remove_effects.py",
        "scripts/python/engine/runner/operations/turnflow.py",
        "scripts/python/engine/runner/operations/triggers/dispatch/move_death.py",
        # Le behaviour : `DirectDamage(PercentageOf(StatAmount(Owner, HEALTH), hpPct))`.
        "scripts/python/engine/runner/abilities/behaviours/combat.py",
        "scripts/python/engine/runner/operations/damage.py",
        "scripts/python/engine/runner/components.py",
        # Le harnais qui monte la bataille et rejoue le tick offline.
        "scripts/python/tests/engine/runner/_charge_regime.py",
        "scripts/python/rl_duel.py", "scripts/python/catalog_inject.py",
        "scripts/python/tests/conftest.py",
    ),
    "build": True,
    "toujours": False,
    "raison": ("Confrontation LIVE de la face FAIL de 1473 : tout ce qui change la derivation de la "
               "triggered, les quatre conjoints de son trigger, le vecteur d'expiration d'effet ou "
               "le calcul du degat direct peut retourner le verdict. `build: True` parce que la "
               "mesure lit le jeu."),
}


class _Args:
    """Les memes defauts que le CLI du probe -- un objet plutot qu'un `argparse.Namespace` pour
    que le montage du test soit LISIBLE au site."""

    def __init__(self, temoin_sans_cast: bool):
        self.seed = "777"
        self.board = "MC1_67"
        self.target_unit = "necroWarden"
        self.other_unit = "necroSpyder"
        self.hp_target = 900000
        self.hp_player = 900000
        self.hp_pct = 30
        self.temoin_pas = 3
        self.temoin_sans_cast = temoin_sans_cast
        self.verbose = False


@pytest.fixture(scope="module")
def _seed_bc():
    """Seed BC AUGMENTE d'`emperFlawlessBlade` : le porteur est HORS pool et HORS seed BC, et ce
    n'est PAS un refus (aucun `data/unspawnable_rank*.json` ne le nomme)."""
    p = P.seed_bc_avec_hascule()
    yield p
    Path(p).unlink(missing_ok=True)


def _mesure(rpc, build_runner, seed_bc, temoin_sans_cast: bool):
    a = _Args(temoin_sans_cast)
    r = build_runner(seed=a.seed, board=a.board, extra=[
        "--seed-bc", seed_bc,
        "--p-units", "%s,%s" % (P.CARRIER, P.ALLY),
        "--a-units", "%s,%s" % (a.target_unit, a.other_unit),
        "--hp-target", str(a.hp_target), "--hp-player", str(a.hp_player),
        "--no-ai", "--crit", "0,0", "--block-target", "0,0"])
    from engine.entities.pathfinding.board import Board
    from _charge_regime import ChargeRegimeHarness
    return P.mesurer(a, rpc, Board, ChargeRegimeHarness, r["rid"])


@pytest.fixture(scope="module")
def bras_fail(rpc, build_runner, _seed_bc):
    return _mesure(rpc, build_runner, _seed_bc, temoin_sans_cast=False)


@pytest.fixture(scope="module")
def bras_temoin(rpc, build_runner, _seed_bc):
    return _mesure(rpc, build_runner, _seed_bc, temoin_sans_cast=True)


def _exige_regime(m):
    """Un montage rate n'est PAS un accord : il doit FAIRE ECHOUER, jamais passer en silence."""
    if not m.get("ok"):
        pytest.fail("regime NON ATTEINT (%s) : %s" % (m.get("bras"), m.get("why")), pytrace=False)
    for cote, d in (("live", m["live"]), ("offline", m["offline"])):
        if d.get("hp_avant") is None or d.get("hp_apres") is None:
            pytest.fail("PV NON MESURES cote %s (%s) : %s" % (cote, m.get("bras"), d),
                        pytrace=False)


def _perte(d):
    return int(d["hp_avant"]) - int(d["hp_apres"])


def test_le_tick_mesure_est_bien_celui_qui_RETIRE_1465(bras_fail):
    """Sans retrait de 1465, `On(0x40 = EffectRemoved)` ne porte pas le bon `CurrentAbility` et
    aucun des deux cotes n'a rien a faire : les deux concorderaient sur un NO-OP."""
    _exige_regime(bras_fail)
    assert bras_fail["live"]["retire"] is True, bras_fail["live"]["trace"]


def test_le_natif_INFLIGE_au_retrait_de_1465(bras_fail):
    """`DirectDamage(Owner, Owner, PercentageOf(StatAmount(Owner, HEALTH), hpPct))` -- les PV
    COURANTS, pas le maximum (`variant = 0`)."""
    _exige_regime(bras_fail)
    perte = _perte(bras_fail["live"])
    assert perte > 0, bras_fail["live"]
    # `hpPct` vaut 30 au palier du runner : on borne l'ordre de grandeur SANS en faire l'oracle
    # (l'oracle est le natif, compare au port par le test suivant).
    attendu = int(round(int(bras_fail["live"]["hp_avant"]) * 0.30))
    assert perte == attendu, ("perte natif=%d, 30%% des PV COURANTS=%d" % (perte, attendu))


def test_le_port_rend_la_MEME_perte_que_le_natif(bras_fail):
    _exige_regime(bras_fail)
    nat, port = _perte(bras_fail["live"]), _perte(bras_fail["offline"])
    assert port == nat, ("port=%d natif=%d" % (port, nat))


def test_la_CONTRE_EPREUVE_mord(bras_fail):
    """Retirer `DaemonicPatronsFinaleFailAbility` de l'entree `"DaemonicPatrons"` d'
    `ACTIVE_ABILITY_TRIGGERS` = la vue d'AVANT ce port. Elle DOIT changer l'observable.

    ⚠ La comparaison porte sur `NOPORT != PORT`, pas sur `NOPORT == 0` : ecrite ainsi, elle
    << mordrait >> aussi sur un port qui ne firerait pas -- donc sur un port et un mutant
    STRICTEMENT IDENTIQUES."""
    _exige_regime(bras_fail)
    port, noport = _perte(bras_fail["offline"]), _perte(bras_fail["noport"])
    assert noport != port, ("NOPORT rend la MEME perte que le port (%d) -- l'accord ne prouve "
                            "rien" % port)


def test_le_TEMOIN_sans_cast_ne_perd_RIEN(bras_temoin):
    """MEMES ticks, MEME unite, AUCUN cast : ni 1465 a retirer, ni actif consomme. Une perte ici
    signalerait que l'observable du bras FAIL vient d'un AUTRE canal."""
    _exige_regime(bras_temoin)
    assert _perte(bras_temoin["live"]) == 0, bras_temoin["live"]["trace"]
    assert _perte(bras_temoin["offline"]) == 0, bras_temoin["offline"]
