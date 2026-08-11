"""#919 -- CONFRONTATION LIVE du passif `IconOfObstinacy` (1552, `astarLysander`).

Le montage et la mesure vivent dans `probe_919_icon_of_obstinacy.py` (un seul foyer : le probe
MESURE, ce fichier ASSERTE). Deux montages, tous deux a positions FORCEES (`--place`) et porteur
INJECTE au catalogue (il est hors du pool par defaut) :

  1. les DEUX gates de selection, ATTRIBUES separement -- un ami adjacent SANS `TerminatorArmour`
     et un porteur du trait HORS du ring-1 ;
  2. le gate `AmountIsZero(TimesAttackMadeThisTurn(Actor, null))` -- un ami eligible qui ATTAQUE
     avant de clore son tour.

⚠ Le second montage a d'abord rendu un ROUGE qui n'en etait pas un (l'attaque n'avait pas eu lieu :
`--ability` attend un ID et `act ability` prend son lanceur par `--caster`). Le probe porte depuis
un CONTROLE DE MONTAGE explicite (degat inflige > 0) et rend `ok = None` = NON MESURE ; ce fichier
SKIPPE alors en le NOMMANT, il ne conclut pas.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

#: #486-r15 -- les chemins dont une modification DOIT rejouer ce fichier. Perimetre : le probe qui
#: porte le montage et la mesure, le port des deux effets et du trigger, les registres, et les deux
#: foyers du canal `BlockDamage du porteur` (combat + prediction).
DECLENCHEUR = {
    "chemins": (
        "scripts/python/conftest.py", "scripts/python/tests/conftest.py",
        "scripts/python/tests/engine/conftest.py",
        "scripts/python/tests/engine/runner/conftest.py",
        "scripts/python/probe_919_icon_of_obstinacy.py",
        "scripts/python/catalog_inject.py",
        "scripts/python/engine/entities/effects/loki/icon_of_obstinacy.py",
        "scripts/python/engine/runner/operations/triggers/loki/icon_of_obstinacy.py",
        "scripts/python/engine/runner/operations/triggers/dispatch/registry.py",
        "scripts/python/engine/runner/operations/triggers/dispatch/turn.py",
        "scripts/python/engine/runner/operations/turnflow.py",
        "scripts/python/engine/runner/damage_model.py",
        "scripts/python/engine/entities/effects/factory.py",
        "scripts/python/engine/runner/snapshot.py",
    ),
    "build": True,
    "toujours": False,
    "raison": "Live : monte DEUX runners a positions FORCEES (injection catalogue d'`astarLysander`, "
              "hors pool), fait clore les tours et confronte le port au natif sur les PORTEURS et "
              "sur les MONTANTS. Le perimetre est pris LARGE parce que l'accord depend de toute la "
              "chaine -- le trigger et son vecteur `On(0x28)`, les deux registres, la classe "
              "d'effet et sa magnitude, le seeding, et le canal `BlockDamage du porteur` du "
              "modele de degat.",
}

PYDIR = Path(__file__).resolve().parents[3]
if str(PYDIR) not in sys.path:
    sys.path.insert(0, str(PYDIR))

import probe_919_icon_of_obstinacy as P     # noqa: E402

CARRIER, TERMINATOR, PLAIN, FAR = P.CARRIER, P.TERMINATOR, P.PLAIN, P.FAR


@pytest.fixture(scope="module")
def mesure(tmp_path_factory):
    """UN seul montage pour tout le module : build + quatre `FinishUnitTurn` + les deux lectures."""
    state = tmp_path_factory.mktemp("i919") / "st-919-live.json"
    P.STATE = state
    rid = P.build(state)
    try:
        cap = P.capture(rid)
        by_vis = P.ids_by_visual(cap)
        nat = P.etage2(rid, cap)
        prt = P.etage3(cap, by_vis)
        yield {"rid": rid, "natif": nat["rows"], "port": prt["rows"], "by_vis": by_vis}
    finally:
        P._duel(["dispose", "--state-file", str(state)])


def test_le_porteur_et_l_ami_terminator_adjacent_recoivent_le_buff(mesure):
    for vis in (CARRIER, TERMINATOR):
        n = mesure["natif"][vis]
        assert n["a_effet"], "%s devait porter IconOfObstinacy_ExtraArmor" % vis
        assert n["fixed_armor_mod"], "%s : aucun stat-mod FixedArmor mesure" % vis


def test_le_gate_TRAIT_mord_un_ami_ADJACENT_sans_TerminatorArmour_ne_recoit_RIEN(mesure):
    """`ultraTitus` est a DISTANCE 1 du porteur -- l'absence de buff ne peut donc pas venir de la
    geometrie. C'est le trait qui l'ecarte, et cette moitie-la est ce qui ATTRIBUE."""
    n = mesure["natif"][PLAIN]
    assert n["dist"] == 1, "temoin NUL : %s n'est pas adjacent (dist=%s)" % (PLAIN, n["dist"])
    assert not n["a_effet"] and not n["fixed_armor_mod"]


def test_le_gate_DISTANCE_mord_un_TERMINATOR_hors_ring1_ne_recoit_RIEN(mesure):
    """`thousTerminator` PORTE `TerminatorArmour` -- l'absence de buff ne peut donc pas venir du
    trait. Symetrique exact du test precedent : les deux gates sont attribues separement."""
    n = mesure["natif"][FAR]
    assert n["dist"] and n["dist"] > 1, "temoin NUL : %s est adjacent (dist=%s)" % (FAR, n["dist"])
    assert not n["a_effet"] and not n["fixed_armor_mod"]


def test_le_port_rend_les_MEMES_porteurs_et_les_MEMES_montants(mesure):
    """Accord natif/port sur les QUATRE unites, porteur ET montant. Le montant est le point : un
    accord sur le seul ensemble des porteurs laisserait passer une magnitude fausse."""
    ecarts = []
    for vis in (CARRIER, TERMINATOR, PLAIN, FAR):
        n, p = mesure["natif"][vis], mesure["port"][vis]
        if bool(n["a_effet"]) != bool(p["a_effet"]) or \
                (n["fixed_armor_mod"] or 0) != (p["fixed_armor_mod"] or 0):
            ecarts.append((vis, n, p))
    assert not ecarts, "ecarts natif/port : %r" % (ecarts,)


def test_le_montant_est_flat_plus_pourcentage_du_blockdamage_MESURE(mesure):
    """Decomposition PAR ETAGE : le montant natif se re-derive de la seule formule et du
    `BlockDamage` LU dans le snapshot -- aucun scalaire fitte."""
    for vis in (CARRIER, TERMINATOR):
        n = mesure["natif"][vis]
        assert n["block_damage"] > 0, "temoin NUL : %s a un BlockDamage nul" % vis
        attendu = P.expected_amount(n["block_damage"], 50, 180)
        assert n["fixed_armor_mod"] == attendu, \
            "%s : natif=%s attendu=%s (BD=%s)" % (vis, n["fixed_armor_mod"], attendu,
                                                  n["block_damage"])


def test_le_gate_ATTAQUE_mord_des_DEUX_cotes(tmp_path):
    """`AmountIsZero(TimesAttackMadeThisTurn(Actor@0x40, rangeType = null))` : un ami eligible qui
    a ATTAQUE ce tour ne recoit PAS le buff en cloturant. Montage DEDIE (le principal laisse ce
    gate en regime degenere : personne n'y attaque)."""
    g = P.etage5(tmp_path / "st-919-atk.json")
    if g["ok"] is None:
        pytest.skip("montage NON MESURE (l'attaque n'a pas eu lieu) -- aucune conclusion")
    assert g["natif"][CARRIER]["a_effet"], "temoin NUL : le porteur non plus n'a pas eu son buff"
    assert not g["natif"][TERMINATOR]["a_effet"], \
        "l'ami qui a ATTAQUE ne doit PAS recevoir le buff"
    assert g["ok"], "ecart natif/port sur le gate ATTAQUE : %r" % (g,)
