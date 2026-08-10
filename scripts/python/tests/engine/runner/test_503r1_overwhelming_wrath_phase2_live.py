"""CONFRONT LIVE de la PHASE 2 de `1141 OverwhelmingWrath` -- #503-r1 (residu de #503).

Ce que ce fichier GARDE, et pourquoi chaque garde existe :

  * LES COUPS PARTENT, et ils partent AU TOUR DU PORTEUR. #503 avait porte la phase 1 (trois effets
    poses, ZERO degat) et laisse le `2x Eviscerate` du kit a une TRIGGERED non portee : l'effet
    `1300` etait un marqueur qui ne produisait JAMAIS rien. Un port qui reposerait le marqueur sans
    tirer repasserait tous les tests de #503 -- pas celui-ci.
  * LE TEMOIN NEGATIF est aussi important que le positif : au tour ENNEMI, RIEN ne doit partir.
    Sans lui, un port qui frapperait a CHAQUE debut de tour passerait la garde de degat.
  * LE CARDINAL >= 2. C'est ce qui exerce `multi=True` (UN `AttackBehaviour` portant N cibles ->
    `OrderBy(b__5_0)`). A une seule cible, `multi` True et False sont indistinguables et l'accord ne
    prouverait RIEN -- exactement le regime degenere que la doctrine interdit d'invoquer.
  * LES TIRAGES, pas seulement le degat. Un accord sur un scalaire ne prouve rien : deux
    implementations peuvent tomber juste en decalant le flux MT.
  * LE CAST RESTE CE QU'IL ETAIT (non-regression #503) : meme empreinte d'effets, memes porteurs.
  * L'ENSEMBLE DES CIBLES est celui du natif. C'est la garde du SELECTEUR
    (`AdjacentEnemies(Caster@DSLSelectors+0x48, unique: 1, sel: 3)`), ancre sur le CASTER et non
    sur la cible du cast.

⚠ LA MAGNITUDE EST GARDEE SUR **TOUTES** LES CIBLES DEPUIS LA RESOLUTION DE #503-r4 (2026-08-10),
ET LE CLIQUET D'ECART EST A **ZERO**. La garde ne portait que sur la PREMIERE cible tant que
`u83` divergeait (port 12693 brut / 12049 applique contre natif 10957) ; l'etage manquant est
nomme et porte -- `IdunBattle.Entities.Effects.Loki.SupaCyborkBody_CritDmgReductionEffect$$
CreateCritDamageBonus` (`EffectType` 1468), qu'`orksRuntherd` porte et qu'`orksNob` ne porte pas,
d'ou une divergence visible sur UNE seule des deux cibles. Le port rend desormais
`u81 8761 == 8761` et `u83 10957 == 10957`, coup a coup `[5663, 5294]`.
CE SCENARIO EST LE TEMOIN DE CET EFFET-LA autant que de la phase 2 : retirer 1468 du registre
fait rougir `test_magnitude_bit_exacte_sur_toutes_les_cibles` de +1736 PV, dans le sens PERMISSIF
(le port TUAIT une cible que le natif laisse a 1092 PV).

Le montage et TOUTES les lectures vivent dans `scripts/python/probe_503r1_overwhelming_wrath_phase2.py`
(mesure) : une seule implementation, aucune divergence possible entre ce qui est mesure et ce qui
est garde.

Lit l'etat LIVE, aucune RVA ni tuile hardcodee, ASCII only.
"""
from __future__ import annotations

import pytest

import probe_503r1_overwhelming_wrath_phase2 as P

#: Ce qui doit changer pour que ce FICHIER de test puisse changer de verdict (#486-r15).
DECLENCHEUR = {
    # PERIMETRE LARGE, pour la meme raison MESUREE que `test_513_pending_attack_live.py` : ce
    # fichier importe le probe, dont la fermeture d'import atteint la quasi-totalite de
    # `scripts/python`. Declarer etroit produirait un FAUX VERT.
    # ⚠ Les DEUX formes sont necessaires : `**/` exige un SEGMENT, donc `scripts/python/**/*.py`
    # ne voit PAS `scripts/python/board.py`.
    "chemins": ("scripts/python/*.py", "scripts/python/**/*.py",
                "data/seed-bc.json", "data/boards/**", "data/symbols/**"),
    "build": True,
    "toujours": False,
    "raison": "Confrontation LIVE port-vs-natif de la phase 2 de 1141 (triggered 1237) et de son "
              "rang dans le foyer APendingAttackEffect. L'oracle est le jeu lui-meme (cibles, "
              "degat, tirages, retrait de l'effet), donc un changement de build peut faire changer "
              "d'avis sans qu'une ligne du port bouge.",
}

#: L'ECART TOTAL port-vs-natif. RESSERRE A **ZERO** le 2026-08-10 avec la resolution de #503-r4
#: (il valait 1092). Ce n'est pas une tolerance : c'est un CLIQUET, et un cliquet a zero ne peut
#: plus que rougir. Le remonter exigerait de nommer l'etage qui l'a rouvert.
ECART_ATTENDU_MAX = 0


@pytest.fixture(scope="module")
def mesure(live_session):
    """UN SEUL runner pour tout le fichier : le cast et les passages de tour ne sont pas rejouables
    (ils consomment l'actif et l'effet), donc les gardes relisent la MEME mesure."""
    m, dispose = P.measure(live_session, state_name="test_503r1_overwhelming_wrath_phase2")
    try:
        yield m
    finally:
        dispose()


def test_cast_inchange(mesure):
    """NON-REGRESSION #503 : le cast pose les MEMES effets sur les MEMES porteurs, et le port est
    bien ROUTE (sans quoi le cast serait un no-op silencieux)."""
    assert mesure["ported"] is True
    assert not mesure["cast_error"]
    assert mesure["off_cast"] == mesure["live_cast"]
    cid = mesure["caster"]
    assert P.OW_PENDING_ATTACK in (mesure["off_cast"].get(cid) or {})
    assert P.OW_RANGE_DMG_REDUCTION in (mesure["off_cast"].get(cid) or {})


def test_rien_ne_part_au_tour_ennemi(mesure):
    """TEMOIN NEGATIF : `On(0x15 = TurnStart_DelayedAttacks) & IsTurnOf(...)` ne doit rien produire
    au tour de l'adversaire -- des DEUX cotes."""
    assert mesure["off_ennemi"] == []
    assert P._hp_delta(*mesure["off_hp_ennemi"]) == {}
    assert P._hp_delta(*mesure["live_hp_ennemi"]) == {}


def test_les_coups_partent_au_tour_du_porteur(mesure):
    """Les coups partent, ils font du degat, et c'est bien la triggered 1237 qui est dispatchee.
    Un port qui poserait le marqueur sans jamais tirer (l'etat d'avant cette tranche) echoue ici."""
    d_live = P._hp_delta(*mesure["live_hp"])
    assert d_live, "REGIME DEGENERE : le natif n'a inflige AUCUN degat -- rien a confronter"
    tirs = [t for t in (mesure["off_tir"] or []) if t]
    assert len(tirs) == 1
    assert tirs[0]["triggered"] == P.OW_ATTACK
    assert tirs[0]["attacker"] == mesure["caster"]


def test_ensemble_des_cibles_egal_au_natif(mesure):
    """LA GARDE DU SELECTEUR : `AdjacentEnemies(Caster@+0x48, unique: 1, sel: 3)` est ancre sur le
    CASTER, pas sur la cible du cast. Un port qui frapperait la seule cible du cast, ou qui
    ancrerait sur elle, echoue ici."""
    cibles_off = set(P._hp_delta(*mesure["off_hp"]))
    cibles_live = set(P._hp_delta(*mesure["live_hp"]))
    assert cibles_live, "temoin NON NUL exige"
    assert cibles_off == cibles_live


def test_cardinal_au_moins_deux_cibles(mesure):
    """C'est ce qui EXERCE `multi=True`. A une seule cible, `multi` True et False rendent le meme
    resultat : l'accord des autres gardes ne prouverait alors rien sur ce point."""
    assert len(set(P._hp_delta(*mesure["live_hp"]))) >= 2, (
        "montage DEGENERE : moins de deux ennemis adjacents au caster -- le placement force du "
        "probe doit etre revu, ce n'est pas un resultat")


def test_magnitude_bit_exacte_sur_toutes_les_cibles(mesure):
    """La MAGNITUDE, sur TOUTES les cibles (#503-r4 resolu). C'est aussi le TEMOIN LIVE de
    `SupaCyborkBody_CritDmgReductionEffect$$CreateCritDamageBonus` : `orksRuntherd` le porte,
    `orksNob` non, donc son absence ne fait diverger QU'UNE des deux cibles -- et dans le sens
    permissif (+1736 PV, cible tuee au lieu de survivre a 1092)."""
    dmg_off = {k: v[0] - v[1] for k, v in P._hp_delta(*mesure["off_hp"]).items()}
    dmg_live = {k: v[0] - v[1] for k, v in P._hp_delta(*mesure["live_hp"]).items()}
    assert dmg_live, "regime DEGENERE : aucun degat natif, l'accord ne prouverait rien"
    assert dmg_off == dmg_live


def test_premiere_cible_bit_exacte(mesure):
    """La MAGNITUDE, sur la premiere cible frappee (ordre = id, mirror de l'`OrderBy(b__5_0)`).
    GARDE CONSERVEE malgre celle du dessus : elle nomme la cible et resiste a une reecriture qui
    n'attaquerait que l'egalite globale."""
    dmg_off = {k: v[0] - v[1] for k, v in P._hp_delta(*mesure["off_hp"]).items()}
    dmg_live = {k: v[0] - v[1] for k, v in P._hp_delta(*mesure["live_hp"]).items()}
    assert dmg_live, "temoin NON NUL exige"
    premiere = sorted(dmg_live)[0]
    assert dmg_off[premiere] == dmg_live[premiere]


def test_ecart_total_ne_saggrave_pas(mesure):
    """CLIQUET du residu #503-r4 : l'ecart total port-vs-natif ne doit pas AUGMENTER. S'il tombe a
    zero, le residu est resolu et cette garde doit etre resserree -- elle le dit."""
    dmg_off = {k: v[0] - v[1] for k, v in P._hp_delta(*mesure["off_hp"]).items()}
    dmg_live = {k: v[0] - v[1] for k, v in P._hp_delta(*mesure["live_hp"]).items()}
    ecart = sum(abs(dmg_off.get(k, 0) - v) for k, v in dmg_live.items())
    assert ecart <= ECART_ATTENDU_MAX, (
        "l'ecart de magnitude a AUGMENTE : %d > %d (residu #503-r4)" % (ecart, ECART_ATTENDU_MAX))


def test_tirages_egaux(mesure):
    """Le FLUX MT, pas seulement la valeur : un accord de scalaire ne prouve rien. C'est cette garde
    qui etablit que l'ecart de #503-r4 est un etage d'APPLICATION et non de TIRAGE."""
    live = int(mesure["rng_apres"][0] or 0) - int(mesure["rng_avant"][0] or 0)
    assert live > 0, "temoin NON NUL exige (un pas sans tirage ne discrimine rien)"
    assert mesure["off_draws"] == live


def test_effet_1300_retire_des_deux_cotes(mesure):
    """Le `RemoveEffect(Effect@DSLSelectors+0x38)` du `Triggered()` d'`APendingAttackEffect`. Le
    `CreateBehaviour` de 1237 n'en porte AUCUN -- contraste LU avec la phase 2 de 1069."""
    off_a, off_b = mesure["off_foot"]
    live_a, live_b = mesure["live_foot"]
    cid = mesure["caster"]
    for a, b, etiquette in ((off_a, off_b, "port"), (live_a, live_b, "natif")):
        assert P.OW_PENDING_ATTACK in (a.get(cid) or {}), etiquette
        assert P.OW_PENDING_ATTACK not in (b.get(cid) or {}), etiquette
