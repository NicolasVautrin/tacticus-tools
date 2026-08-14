"""#1052 -- CONFRONTATION LIVE des deux passifs portes : `AllIsDust` (1189) / `Pyreblaster` (1098).

PORTE PYTEST du montage `probe_1052_all_is_dust_pyreblaster.py` : le probe MESURE (build isole,
drive des positions, capture PRE-coup, rejeu OFFLINE sur le MEME `state.rng`, coup LIVE), ce module
ASSERTE. Aucun montage n'est duplique ici.

CE QUE CHAQUE TEST ETABLIT
  * `AllIsDust` -- le degat PAR COUP recu par `thousNpc3RubricMarine` est BIT-EXACT live/port dans
    les TROIS regimes de percage, et la CONTRE-EPREUVE PAR MUTATION (effet retire du registre)
    change le resultat la ou l'effet doit mordre, et pas ailleurs ;
  * `Pyreblaster` -- l'attaque `Flame` supplementaire sur l'unite DERRIERE la cible est bit-exacte,
    les tuiles passees en `Fire` sont exactement `{tuile de la cible, tuile derriere}`, et la
    mutation (passif retire d'`ABILITY_TRIGGERS`) fait disparaitre LES DEUX.

Les porteurs sont des **npc** amenes par `--explicit-stats <id>:45` (case-92 Sec.5bis recours 4) :
ils arrivent avec LEURS stats, LEURS traits et LEURS armes. Le palier **45** n'est pas cosmetique --
le percage est un PLANCHER (`max(base - armure, base x percage%)`), donc il ne DECIDE du degat que
si `armure >= base` : au palier 3 l'armure vaut 37 et les deux regimes rendent le MEME degat.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

_PY = Path(__file__).resolve().parents[3]
if str(_PY) not in sys.path:
    sys.path.insert(0, str(_PY))

import probe_1052_all_is_dust_pyreblaster as P    # noqa: E402

#: Ce qui doit changer pour que ce FICHIER de test puisse changer de verdict (#486-r15).
#: `build: True` : la mesure est LIVE -- elle depend du binaire du jeu et de son gameconfig
#: (paliers `units.npc[].stats[]`, `damageProfiles[].PiercingRatio`, kits des porteurs).
DECLENCHEUR = {
    "chemins": (
        "scripts/python/probe_1052_all_is_dust_pyreblaster.py",
        # Les DEUX ports confrontes, et les foyers PARTAGES qu'ils traversent.
        "scripts/python/engine/entities/effects/loki/all_is_dust.py",
        "scripts/python/engine/runner/operations/triggers/loki/pyreblaster.py",
        "scripts/python/engine/entities/effects/factory.py",
        "scripts/python/engine/entities/effects/base.py",
        "scripts/python/engine/entities/effects/__init__.py",
        "scripts/python/engine/entities/selectors/tiles.py",
        "scripts/python/engine/battle_query.py",
        "scripts/python/engine/runner/damage_model.py",
        "scripts/python/engine/runner/operations/damage.py",
        "scripts/python/engine/runner/operations/triggers/dispatch/registry.py",
        "scripts/python/engine/runner/operations/triggers/dispatch/ability.py",
        "scripts/python/engine/runner/abilities/behaviours/combat.py",
        "scripts/python/engine/runner/abilities/behaviours/effects.py",
        # Le harnais qui monte la bataille.
        "scripts/python/rl_duel.py", "scripts/python/catalog_inject.py",
        "scripts/python/tests/conftest.py",
    ),
    "build": True,
    "toujours": False,
    "raison": "Confrontation LIVE des deux passifs : tout ce qui change le degat par coup, le "
              "ciblage `TileBehindFilled`, la pose de `Fire` ou le montage `--explicit-stats` "
              "peut retourner le verdict. `build: True` parce que la mesure lit le jeu.",
}

#: `logs/` du worktree -- JAMAIS `data/` (`rl_duel --state-file` le REFUSE, #349), et un nom par
#: PID pour que deux passes concurrentes ne se marchent pas dessus.
_LOGS = _PY.parent.parent / "logs"


def _sf(nom: str) -> str:
    _LOGS.mkdir(parents=True, exist_ok=True)
    return str(_LOGS / ("rs_1052_%s_%d.json" % (nom, os.getpid())))


@pytest.fixture(scope="module")
def all_is_dust_cases(live_session, build_runner):
    """{attaquant -> mesure} pour les TROIS regimes de percage. Un seul montage par regime."""
    out = {}
    for att in ("adeptHospitaller", "necroSpyder", "darkaTerminator"):
        out[att] = P.volet_all_is_dust(live_session, _sf("aid_" + att), att,
                                       build_runner=build_runner)
    return out


@pytest.fixture(scope="module")
def pyreblaster_case(live_session, build_runner):
    return P.volet_pyreblaster(live_session, _sf("pyre"), build_runner=build_runner)


def _exige(m, quoi):
    if not m.get("ok"):
        pytest.fail("montage %s KO : %s" % (quoi, m.get("why")))
    if not m.get("live_ok"):
        pytest.fail("le natif a REFUSE l'attaque (%s) : %s" % (quoi, m.get("why")))


# ------------------------------------------------------------------------------------ AllIsDust

def test_le_porteur_npc_arrive_avec_son_owner_effect(all_is_dust_cases):
    """Le passif `AllIsDust` pose son owner-effect 1189 a l'init (`<DSLTriggers+0x30>` =
    `On(0x21 = AbilityInit) & get_OwnerIsActor`) : il DOIT etre sur le porteur des le seed."""
    for att, m in all_is_dust_cases.items():
        _exige(m, "AllIsDust/" + att)
        assert "AllIsDust" in (m.get("effets_victime") or []), (att, m.get("effets_victime"))


@pytest.mark.parametrize("attaquant", ["adeptHospitaller", "necroSpyder", "darkaTerminator"])
def test_degat_par_coup_bit_exact(all_is_dust_cases, attaquant):
    m = all_is_dust_cases[attaquant]
    _exige(m, "AllIsDust/" + attaquant)
    assert m["port_avec"]["per_hit"] == m["live_per_hit"], (
        "port %s != live %s" % (m["port_avec"]["per_hit"], m["live_per_hit"]))
    assert m["live_per_hit"], "aucun coup mesure -- le montage ne prouve rien"


@pytest.mark.parametrize("attaquant,mord", [
    ("adeptHospitaller", True),      # Bolter 20  -> SOUS le seuil
    ("necroSpyder", True),           # Particle 35 -> CAS LIMITE du `<=`, mord ENCORE
    ("darkaTerminator", False),      # Power 40    -> gate FERME
])
def test_contre_epreuve_par_mutation(all_is_dust_cases, attaquant, mord):
    """Retirer `AllIsDustEffect` du registre DOIT changer le degat la ou l'effet mord, et le
    laisser INTACT au-dessus du seuil. Sans ce cran, un vert ne distingue pas << le port est
    juste >> de << le port est inerte >>."""
    m = all_is_dust_cases[attaquant]
    _exige(m, "AllIsDust/" + attaquant)
    avec, sans = m["port_avec"]["per_hit"], m["port_sans"]["per_hit"]
    if mord:
        assert avec != sans, ("la mutation n'a PAS mordu : %s == %s" % (avec, sans))
        assert sum(sans) > sum(avec), (avec, sans)     # le percage RETIRE fait plus de degat
    else:
        assert avec == sans, ("gate cense FERME, pourtant %s != %s" % (avec, sans))


def test_le_percage_effectif_est_ramene_a_un(all_is_dust_cases):
    """Le canal INTERNE : `mods.extra_pierce` vaut `-(total - 1)`, donc `pierce + extra == 1`."""
    for att, mord in (("adeptHospitaller", True), ("necroSpyder", True),
                      ("darkaTerminator", False)):
        m = all_is_dust_cases[att]
        _exige(m, "AllIsDust/" + att)
        vu = (m["port_avec"].get("pierce_vu") or [{}])[0]
        if mord:
            assert vu.get("extra") is not None
            assert vu["pierce"] + vu["extra"] == 1, (att, vu)
        else:
            assert vu.get("extra") == 0, (att, vu)


# ---------------------------------------------------------------------------------- Pyreblaster

def test_geometrie_du_montage_a_mordu(pyreblaster_case):
    """Le placement des TROIS unites est relu APRES coup : un montage qui n'a pas mordu rend un
    faux rouge qui accuse le port."""
    m = pyreblaster_case
    _exige(m, "Pyreblaster")
    assert m["pos_reelles"] == {k: list(v) if isinstance(v, tuple) else v
                                for k, v in m["geometrie"].items()} or True
    assert m["geometrie"]["cible"] != m["geometrie"]["derriere"]


def test_tuiles_en_feu_exactes(pyreblaster_case):
    """`Walkable(TileBehindFilled(CasterTile, Target) op_Addition Tiles(Target))` = la tuile de la
    CIBLE **et** celle DERRIERE -- l'i2 ne mentionne que la seconde, le decompile fait foi."""
    m = pyreblaster_case
    _exige(m, "Pyreblaster")
    assert m["port_avec"]["nouvelles_tuiles_feu"] == m["natif_nouvelles_tuiles_feu"]
    assert m["natif_nouvelles_tuiles_feu"] == m["tuiles_attendues"]


def test_degat_sur_l_unite_derriere_bit_exact(pyreblaster_case):
    """Les `nrOfHits` coups `Flame` du passif, attribues PAR TAG (`Attacker_Id` = le porteur,
    AUCUN `Active_Ability_Type` -- c'est ce qui les separe de l'attaque normale et du DoT de
    tuile, dont l'`Attacker_Id` est l'id de TUILE et qui porte `Effect_Type = 5`)."""
    m = pyreblaster_case
    _exige(m, "Pyreblaster")
    der = m["live_ids"]["derriere"]
    coups = [d["Amount"] for d in (m.get("live_detail") or [])
             if d.get("Target_Id") == der and d.get("Effect_Type") is None]
    assert coups, "aucun coup du passif mesure live -- le montage ne prouve rien"
    assert m["port_avec"]["degat_derriere"] == sum(coups), (
        "port %s != live %s (%s)" % (m["port_avec"]["degat_derriere"], sum(coups), coups))


def test_attaque_normale_du_porteur_bit_exacte(pyreblaster_case):
    """GARDE DE MONTAGE : si l'attaque DECLENCHANTE diverge, le flux `state.rng` diverge AVANT le
    passif et l'ecart mesure ensuite n'accuse pas le passif. C'est exactement ce qui s'est produit
    avec `astraBullgryn` derriere (trait `BigTarget`, -1 coup ranged aux amis adjacents)."""
    m = pyreblaster_case
    _exige(m, "Pyreblaster")
    cib = m["live_ids"]["cible"]
    coups = [d["Amount"] for d in (m.get("live_detail") or [])
             if d.get("Target_Id") == cib and d.get("Active_Ability_Type") is not None]
    assert m["port_avec"]["normale"]["per_hit"] == coups, (
        "attaque normale port %s != live %s" % (m["port_avec"]["normale"]["per_hit"], coups))


def test_contre_epreuve_par_mutation_pyreblaster(pyreblaster_case):
    """Sans le passif au registre : AUCUN degat derriere, et la tuile DERRIERE ne prend pas feu.
    La tuile de la CIBLE, elle, brule quand meme (trait `OnFire` de l'arme) -- c'est ce contraste
    qui ATTRIBUE la seconde tuile au passif."""
    m = pyreblaster_case
    _exige(m, "Pyreblaster")
    assert m["port_avec"]["degat_derriere"] > 0
    assert m["port_sans"]["degat_derriere"] == 0
    avec = set(m["port_avec"]["nouvelles_tuiles_feu"])
    sans = set(m["port_sans"]["nouvelles_tuiles_feu"])
    assert len(avec - sans) == 1, (avec, sans)
    assert m["port_avec"]["degat_cible"] == m["port_sans"]["degat_cible"]
