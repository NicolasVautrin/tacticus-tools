"""#462-r4b-r1-r1-r1-r1-b -- les triggers (b) `get_Range` et (c) `get_Adjacent` d'`ABondEffect`,
confrontes au natif.

LE CRITERE DISCRIMINANT, ENONCE AVANT LE MONTAGE
------------------------------------------------
Le bond tombe-t-il quand le BONDE s'eloigne ? Confronter sur un seul bras ne prouverait rien : un
port qui retirerait le taunt a CHAQUE mouvement -- ou jamais -- passerait la moitie des lignes. Il
faut donc DEUX bras qui jouent le MEME geste et DIVERGENT par la seule GEOMETRIE.

`DisplaceUnitOperation` pousse a l'oppose du pousseur. Soit V le taunte, T le taunteur (= le
`bondedEntity`) en `V + t`, et E le pousseur en `V + e` : la destination est `V - e`, donc
`dist(V - e, T) = |e + t|`.

    bras ELOIGNE : `e` a 1 cran de `t` -> distance 2 -> HORS portee (`get_Range = 1`)
    bras PROCHE  : `e` a 2 crans       -> distance 1 -> ENCORE a portee   <- LE CONTROLE

Le montage n'attend AUCUN tour, et c'est ce qui a debloque le residu. La passe precedente
concluait << inobservable >> parce que le taunt de `CrushingClaws` dure `TurnsFromRounds(1)` et
tombe au deuxieme `endturn` ; et le taunte, lui, ne peut PAS marcher (`Taunted_BlockMovement`). On
ne fait donc marcher personne : une SECONDE unite du meme camp caste `MortisRound` (1004), dont
l'arbre porte `PushUnit(Caster(), Target())`. Le push emet `On(0x1d)` cote natif
(`IdunBattle.Operations.DisplaceUnitOperation$$EventAndAbilitiesAndEffects`) ET change la distance.

TROIS BRAS, TROIS QUESTIONS DISTINCTES
--------------------------------------
  B. (b) `get_Range` sur l'effet 27 `Taunted_OnlySpecificTargets` -- les DEUX faces, natif et port,
     sur le MEME etat (capture apres le taunt, avant le push).
  C. (c) `get_Adjacent` sur l'effet 1091 `HolyDuel_Taunt` (`templChampion`, AU POOL) -- face NATIVE
     seulement : l'ability 1050 n'est pas dans `ABILITY_CLASSES`, donc le port ne pose JAMAIS 1091.
     Le test le DIT au lieu de le taire, et rougira le jour ou 1050 sera portee.
  A. (a) `get_RemoveOnBondedEntityDeath` sur ce MEME effet 27 -- effet de BORD de l'entree de table
     (le virtuel vaut `true`), donc confronte lui aussi. Vecteur : le friendly-fire de `FragBomb`
     (1017), dont le splash `AdjacentUnits(Target) - Caster` touche les ALLIES. Les deux bras ne
     different QUE par les PV du taunteur.

Un port qui ignorerait l'un des trois virtuels echoue forcement sur l'un de ces bras.

⚠ Ce fichier monte SIX runners (deux par bras), en SERIE, et les dispose. Il ne partage aucun
state-file avec un autre module.

ASCII only. Dispose SES runners (jamais ceux des autres).
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

PYDIR = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(PYDIR))

from engine.entities.effect_type import EffectType                              # noqa: E402
from engine.runner.operations.triggers.bond_removal import (                    # noqa: E402
    BOND_REMOVAL_GATES, BondRemoveOnRangeExceeded)
from engine.runner.operations.triggers.dispatch.registry import EFFECT_TRIGGERS  # noqa: E402

TAUNTED = int(EffectType.Taunted_OnlySpecificTargets)      # 27
FAMILY = [25, 26, 27, 1237]


def _sid():
    from rl_collect_batch import _resolve_session
    return _resolve_session()


@pytest.fixture(scope="module")
def bras_b():
    """(b) : les deux geometries, les DEUX faces. Un runner par geometrie."""
    import probe_462_r4b_r1_r1_r1_r1_b_bond_range as P
    sid = _sid()
    return {m: P.run_bras(sid, m) for m in ("eloigne", "proche")}


@pytest.fixture(scope="module")
def bras_c():
    """(c) : les deux geometries, face NATIVE."""
    import probe_462_r4b_r1_r1_r1_r1_b_bond_range as P
    sid = _sid()
    return {m: P.holyduel_bras(sid, m) for m in ("eloigne", "proche")}


@pytest.fixture(scope="module")
def bras_a27():
    """(a) sur l'effet 27 : taunteur increvable (CONTROLE) puis taunteur a 1 PV."""
    import probe_462_r4b_r1_r1_r1_r1_b_bond_range as P
    sid = _sid()
    return {"vivant": P.death_bras(sid, 400000), "mort": P.death_bras(sid, 1)}


# ================================================================================================
# BRAS B -- (b) `<+0x728> get_Range`
# ================================================================================================
def test_b_natif_retire_le_bond_hors_portee_et_le_garde_a_portee(bras_b):
    """NATIF, les deux geometries. Le bras PROCHE est ce qui rend le bras ELOIGNE attribuable a la
    PORTEE : meme cast, meme push, meme attaque -- seule la tuile du pousseur change."""
    e, p = bras_b["eloigne"], bras_b["proche"]
    assert e["moved"] and p["moved"], "montage : le push n'a pas eu lieu (%s / %s)" % (e, p)
    assert e["d_before"] == 1 and p["d_before"] == 1, "montage : le taunt n'est pas pose au contact"
    assert e["d_after"] == 2, "montage : le bras ELOIGNE doit sortir de la portee (d=%d)" % e["d_after"]
    assert p["d_after"] == 1, "montage : le bras PROCHE doit rester a portee (d=%d)" % p["d_after"]
    assert e["alive"] and p["alive"], "le taunte est mort -- (a) rendrait (b) inattribuable"
    assert [t[0] for t in e["taunt_before"]] == FAMILY
    assert not e["taunt_after"], (
        "NATIF : le bond survit a un eloignement au-dela de `get_Range` (%s)" % (e["taunt_after"],))
    assert [t[0] for t in p["taunt_after"]] == FAMILY, (
        "CONTROLE ROUGE : le bond tombe alors que la distance est ENCORE de 1 -- le retrait ne "
        "serait pas attribuable a la PORTEE")


def test_b_port_suit_le_natif_sur_les_deux_geometries(bras_b):
    """PORT, sur l'etat capture APRES le taunt et AVANT le push -- donc la meme question, au meme
    point. Le push est rejoue par `DisplaceUnitOperation`, l'Operation que le natif emet."""
    e, p = bras_b["eloigne"], bras_b["proche"]
    assert e["port_moved"] and p["port_moved"], "le push offline n'a pas eu lieu"
    assert e["port_bonded"] == e["ctx"]["taunter"], "le bond ne pointe pas le taunteur"
    assert e["port_d_after"] == 2 and p["port_d_after"] == 1, (
        "le push offline n'atterrit pas ou le natif l'a pose (%d / %d)"
        % (e["port_d_after"], p["port_d_after"]))
    assert e["port_before"] == FAMILY and p["port_before"] == FAMILY
    assert e["port_after"] == [], (
        "PORT : le bond survit hors portee alors que le natif le retire (%s)" % (e["port_after"],))
    assert p["port_after"] == FAMILY, (
        "PORT : le bond tombe alors que la distance est encore de 1")


def test_b_le_retrait_emporte_les_sous_effets_et_vide_les_cibles_forcees(bras_b):
    """Le composite part ENTIER, des deux cotes -- `RemoveEffectOperation$$RemoveSubEffects` -- et
    la liste de cibles forcees se vide avec lui (`TauntedEffect$$RevertInternal`).

    C'est le trou qu'a decouvert ce bras : le trigger retirait bien le 27, et `[25, 26, 1237]`
    restaient sur la cible. Un taunte ainsi ampute reste BLOQUE (25) et prive d'ability (26) pour
    toujours -- degradation invisible, jamais une erreur."""
    e, p = bras_b["eloigne"], bras_b["proche"]
    assert [t[0] for t in e["taunt_after"]] == [], "NATIF : famille residuelle"
    assert e["port_after"] == [], "PORT : sous-effets orphelins apres le retrait du parent"
    assert e["port_forced"] == [], (
        "PORT : la liste de cibles forcees survit au retrait du bond -- le taunte resterait "
        "contraint de n'attaquer que son ex-taunteur")
    assert p["port_forced"] == [p["ctx"]["taunter"]], (
        "CONTROLE : a portee, la liste doit TOUJOURS designer le taunteur")


# ================================================================================================
# BRAS C -- (c) `<+0x738> get_Adjacent`
# ================================================================================================
def test_c_natif_retire_le_bond_hors_adjacence_et_le_garde_adjacent(bras_c):
    """NATIF. `HolyDuelAbility$$ExecuteBehaviour` pose `AddBondEffect(0x443 = 1091)` sur la cible,
    `bondedEntity` = le caster, options VIDES (donc PERMANENT : aucune duree ne peut expliquer la
    disparition, contrairement au taunt de `CrushingClaws`)."""
    e, p = bras_c["eloigne"], bras_c["proche"]
    assert e["moved"] and p["moved"], "montage : le push n'a pas eu lieu"
    assert e["d_before"] == 1 and p["d_before"] == 1
    assert e["d_after"] == 2 and p["d_after"] == 1
    assert [t[0] for t in e["before"]] == [1091] and [t[0] for t in p["before"]] == [1091]
    assert not e["after"], "NATIF : le duel survit a la perte d'adjacence (%s)" % (e["after"],)
    assert [t[0] for t in p["after"]] == [1091], (
        "CONTROLE ROUGE : le duel tombe alors que l'adjacence est INTACTE")


def test_c_le_port_ne_pose_pas_1091_donc_ne_porte_aucun_trigger_c():
    """PORT : il n'y a RIEN a porter, et ce test le dit au lieu de le taire.

    `HolyDuel_TauntEffect` est la SEULE classe qui arme (c), et son `EffectType` 1091 ne vient que
    de l'ability 1050, absente d'`ABILITY_CLASSES`. Inscrire un trigger (c) serait du code
    qu'aucun etat ne peut atteindre. Ce test rougira le jour ou 1050 sera portee -- et c'est ce
    jour-la qu'il faudra ecrire `BondRemoveOnAdjacencyLost` (la mesure native, elle, est deja
    faite : cf. le bras ci-dessus)."""
    from engine.runner.abilities.handler import ABILITY_CLASSES
    assert 1050 not in ABILITY_CLASSES, (
        "`HolyDuelAbility` est portee : 1091 devient posable offline, le trigger (c) doit exister")
    assert 1091 not in BOND_REMOVAL_GATES, (
        "1091 est entre dans la table alors que le port ne le pose pas")
    assert not [et for et, g in BOND_REMOVAL_GATES.items() if g.adjacent]


# ================================================================================================
# BRAS A -- (a) `<+0x748> get_RemoveOnBondedEntityDeath` sur le MEME effet 27
# ================================================================================================
def test_a27_natif_retire_le_taunt_a_la_mort_du_taunteur(bras_a27):
    """NATIF. `TauntedEffect$$get_RemoveOnBondedEntityDeath` vaut `true` : entrer 27 dans la table
    inscrit AUSSI (a), donc (a) doit etre confronte sur CET effet -- pas seulement sur les trois
    porteurs de la passe precedente.

    Les deux bras jouent la MEME frag ; seuls les PV du taunteur changent."""
    mort, vivant = bras_a27["mort"], bras_a27["vivant"]
    assert mort["dead"], "montage : le friendly-fire n'a pas tue le taunteur"
    assert not vivant["dead"], "CONTROLE : le taunteur devait survivre"
    assert [t[0] for t in mort["before"]] == FAMILY
    assert not mort["after"], "NATIF : le taunt survit a la mort de son taunteur"
    assert [t[0] for t in vivant["after"]] == FAMILY, (
        "CONTROLE ROUGE : le taunt tombe alors que le taunteur est VIVANT -- le retrait ne serait "
        "pas attribuable a sa mort")


def test_a27_port_retire_sur_le_bonde_et_pas_sur_une_tierce(bras_a27):
    """PORT, `On(2 = PreUnitDeath_2)` par ses deux vecteurs, sur l'etat capture avant la frag.
    La mort d'une TIERCE est le controle du conjoint `IsEntityWithIdTarget(BondedEntity)`."""
    v = bras_a27["vivant"]
    assert v["port_tierce"] == FAMILY, (
        "PORT : une mort TIERCE a retire le taunt -- `IsEntityWithIdTarget` ne mord pas")
    assert v["port_bonde"] == [], "PORT : le taunt survit a `On(PreUnitDeath_2)` sur le taunteur"


def test_les_deux_triggers_sont_inscrits_pour_l_effet_27():
    """Le cablage se derive de la table : 27 arme (a) ET (b), donc DEUX classes."""
    inscrits = EFFECT_TRIGGERS.get(TAUNTED, [])
    assert BondRemoveOnRangeExceeded in inscrits
    assert BOND_REMOVAL_GATES[TAUNTED].range == 1
    assert BOND_REMOVAL_GATES[TAUNTED].remove_on_bonded_entity_death is True
