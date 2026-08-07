"""CONFRONT LIVE du foyer `IdunBattle.Entities.Effects.APendingAttackEffect` et de la PHASE 2 de
`1069 SeekerMissileFrequencyLock` -- #513 (residu #491-r1).

Ce que ce fichier GARDE, et pourquoi chaque garde existe :

  * LE MISSILE PART, et il part AU TOUR DU CASTER. #491 avait porte la phase 1 (trois effets poses,
    zero degat) et laisse le degat a une TRIGGERED non portee : le verrouillage etait pose et rien
    n'en sortait JAMAIS. La garde exige un degat NON NUL et EGAL au natif -- un port qui reposerait
    le marqueur sans jamais tirer repasserait tous les tests de #491.
  * LE TEMOIN NEGATIF est aussi important que le positif : au tour ENNEMI, RIEN ne doit partir.
    `GetAttackingUnitSelector` a deux candidats (`Owner` = le porteur, `BondedEntity` = le caster)
    qui appartiennent ici a DEUX JOUEURS -- sans ce temoin, un port qui tirerait sur le mauvais
    selecteur passerait la garde de degat un tour trop tard, avec la meme valeur.
  * LES TIRAGES, pas seulement le degat. Un accord sur un scalaire ne prouve rien : deux
    implementations peuvent tomber juste en decalant le flux MT. La garde compare le nombre de
    tirages consommes des deux cotes, sur un MT CALE sur le live.
  * LE CAST RESTE CE QU'IL ETAIT (non-regression #491) : meme empreinte d'effets, memes porteurs.
  * LES DEUX EFFETS DISPARAISSENT au tir -- `1123` par le `RemoveEffect(Effect)` du foyer commun,
    `1136` par le `RemoveEffect(Caster, 1136)` de l'arbre de phase 2. Deux foyers distincts, donc
    deux facons independantes de casser le retrait.
  * LE RECENSEMENT de la famille reste COHERENT : `probe_513_pending_attack_family.py` verifie que
    la table des `GetTriggeredAbilityType` couvre EXACTEMENT la fermeture transitive lue dans
    `classes.tsv`. Une classe d'effet neuve au prochain build fait donc rougir ici plutot que de
    disparaitre en silence.

Le montage et TOUTES les lectures vivent dans `scripts/python/probe_513_seeker_phase2.py` (mesure)
et `probe_513_generalisation.py` (contre-epreuves) : une seule implementation, aucune divergence
possible entre ce qui est mesure et ce qui est garde.

Lit l'etat LIVE, aucune RVA ni tuile hardcodee, ASCII only.
"""
from __future__ import annotations

import pytest

import probe_513_pending_attack_family as F
import probe_513_seeker_phase2 as P

#: Ce qui doit changer pour que ce FICHIER de test puisse changer de verdict (#486-r15).
DECLENCHEUR = {
    # PERIMETRE LARGE, pour la meme raison MESUREE que `test_seeker_missile_frequency_lock_live.py` :
    # ce fichier importe le probe, qui importe `ABILITY_CLASSES` -- sa fermeture d'import atteint la
    # quasi-totalite de `scripts/python`. Declarer etroit produirait un FAUX VERT.
    # ⚠ Les DEUX formes sont necessaires : `**/` exige un SEGMENT, donc `scripts/python/**/*.py`
    # ne voit PAS `scripts/python/board.py`.
    "chemins": ("scripts/python/*.py", "scripts/python/**/*.py",
                "data/seed-bc.json", "data/boards/**", "data/symbols/**"),
    "build": True,
    "toujours": False,
    "raison": "Confrontation LIVE port-vs-natif de la phase 2 de 1069 et du foyer "
              "APendingAttackEffect. L'oracle est le jeu lui-meme (degat, tirages, retrait des "
              "effets), donc un changement de build peut faire changer d'avis sans qu'une ligne du "
              "port bouge ; et le recensement lit `data/symbols/<build>`.",
}


@pytest.fixture(scope="module")
def mesure(rpc_session_id):
    m, dispose = P.measure(rpc_session_id, state_name="test_513_pending_attack")
    try:
        yield m
    finally:
        dispose()


def test_cast_inchange(mesure):
    """NON-REGRESSION #491 : le cast pose les MEMES trois effets, sur les MEMES porteurs, et le port
    est bien ROUTE (sans quoi le cast serait un no-op silencieux)."""
    assert mesure["ported"] is True
    assert not mesure["cast_error"]
    assert mesure["off_cast"] == mesure["live_cast"]
    cid, tid = mesure["caster"], mesure["target"]
    assert {k: set(v) for k, v in mesure["off_cast"].items()} == {
        cid: {P.SEEKER_AIMING}, tid: {P.MARKERLIGHT, P.SEEKER_TARGET}}


def test_rien_ne_part_au_tour_ennemi(mesure):
    """TEMOIN NEGATIF : `IsTurnOf(GetAttackingUnitSelector())` porte sur l'entite BONDEE (le caster),
    pas sur le PORTEUR de l'effet. Au tour du porteur, rien ne part -- des DEUX cotes -- et l'effet
    1123 est encore la."""
    assert mesure["off_ennemi"] == []
    assert P._hp_delta(*mesure["off_hp_ennemi"]) == {}
    assert P._hp_delta(*mesure["live_hp_ennemi"]) == {}
    assert P.SEEKER_TARGET in (mesure["live_foot_ennemi"].get(mesure["target"]) or {})


def test_missile_part_au_tour_du_caster(mesure):
    """Le missile part au debut du tour du CASTER, et il fait du degat. Un port qui poserait le
    verrouillage sans jamais tirer (l'etat d'avant #513) echoue ici."""
    d_live = P._hp_delta(*mesure["live_hp"])
    assert d_live, "REGIME DEGENERE : le natif n'a inflige AUCUN degat -- rien a confronter"
    assert set(d_live) == {mesure["target"]}
    assert len(mesure["off_tir"]) == 1
    tir = mesure["off_tir"][0]
    assert tir["attacker"] == mesure["caster"] and tir["owner"] == mesure["target"]
    assert tir["triggered"] == P.SEEKER_ATTACK


def test_degat_egal_au_natif(mesure):
    """La valeur, a l'unite pres, sur un MT CALE sur le live."""
    dmg_off = {k: v[0] - v[1] for k, v in P._hp_delta(*mesure["off_hp"]).items()}
    dmg_live = {k: v[0] - v[1] for k, v in P._hp_delta(*mesure["live_hp"]).items()}
    assert dmg_live, "temoin NON NUL exige"
    assert dmg_off == dmg_live


def test_tirages_egaux(mesure):
    """Le FLUX MT, pas seulement la valeur : un accord de scalaire ne prouve rien."""
    live = mesure["live_draws"][1] - mesure["live_draws"][0]
    assert live > 0, "temoin NON NUL exige (un pas sans tirage ne discrimine rien)"
    assert mesure["off_draws"] == live


def test_les_deux_effets_sont_retires(mesure):
    """`1123` par le `RemoveEffect(Effect@0x38)` du foyer commun `APendingAttackEffect` ; `1136` par
    le `RemoveEffect(Caster, 0x470)` de l'arbre de phase 2. Deux foyers, deux gardes."""
    cid, tid = mesure["caster"], mesure["target"]
    off_a, off_b = mesure["off_foot"]
    live_a, live_b = mesure["live_foot"]
    for a, b, etiquette in ((off_a, off_b, "port"), (live_a, live_b, "natif")):
        assert P.SEEKER_TARGET in (a.get(tid) or {}), etiquette
        assert P.SEEKER_TARGET not in (b.get(tid) or {}), etiquette
        assert P.SEEKER_AIMING in (a.get(cid) or {}), etiquette
        assert P.SEEKER_AIMING not in (b.get(cid) or {}), etiquette


def test_recensement_de_la_famille_coherent():
    """OFFLINE. La table des `GetTriggeredAbilityType` doit couvrir EXACTEMENT la fermeture
    transitive des derivees d'`APendingAttackEffect` lue dans `classes.tsv`, et chaque valeur doit
    NOMMER un membre de `TriggeredAbilityType`. Une classe neuve au prochain build fait rougir ici
    au lieu de disparaitre en silence."""
    r = F.recense()
    derivees = {it["classe"] for it in r["items"]}
    assert derivees == set(F.GTAT_LU), (
        "fermeture non couverte : manquantes=%s / en trop=%s"
        % (sorted(derivees - set(F.GTAT_LU)), sorted(set(F.GTAT_LU) - derivees)))
    assert len(derivees) >= 20, "la famille a RETRECI -- verifier le build"
    sans_nom = [it["court"] for it in r["items"]
                if isinstance(it["gtat"], int) and it["triggered_nom"] is None]
    assert sans_nom == [], "gtat absent de TriggeredAbilityType : %s" % sans_nom


def test_la_phase2_de_1069_est_inscrite():
    """OFFLINE. Les DEUX inscriptions que le port doit porter ENSEMBLE : l'effet 1123 dans
    `EFFECT_TRIGGERS` (le declencheur) et la triggered 1127 dans `TRIGGERED_ABILITY_BEHAVIOURS`
    (l'arbre de degat). L'une sans l'autre est une degradation SILENCIEUSE -- le noeud
    `TriggerAbility` rendrait `dispatched: False` et le `RemoveEffect` du meme `Triggered()`
    effacerait quand meme le marqueur : un verrouillage qui disparait sans que rien ne frappe."""
    from engine.runner.abilities.behaviours.lifecycle import TRIGGERED_ABILITY_BEHAVIOURS
    from engine.runner.operations.triggers.dispatch.registry import EFFECT_TRIGGERS
    from engine.runner.operations.triggers.pending_attack import (
        PENDING_ATTACK_EFFECTS, PendingAttackOnAttackersTurn)
    for et, spec in PENDING_ATTACK_EFFECTS.items():
        assert PendingAttackOnAttackersTurn in (EFFECT_TRIGGERS.get(et) or []), et
        assert spec.triggered_ability in TRIGGERED_ABILITY_BEHAVIOURS, (
            "effect_type %d inscrit SANS sa phase 2 (%d) : le marqueur serait efface sans degat"
            % (et, spec.triggered_ability))
