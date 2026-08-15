"""GARDE LIVE #523 -- `1227 HeavyWarpFlamer` (`thousSekhetar` « Sekhetar Robot », Thousand Sons),
face EXECUTION, confrontee au NATIF sur le MEME substrat.

Avant #523 l'ability etait un **NO-OP SILENCIEUX** : absente d'`ABILITY_CLASSES`, donc la face
DECISION la choisissait (playbook porte depuis #27) et l'execution l'ignorait -- 0 degat, 0 effet,
AUCUNE erreur. Ce fichier garde ce que le port doit desormais produire, le port rejouant le cast
depuis la capture prise juste AVANT le cast natif.

LA GEOMETRIE EST FABRIQUEE (`--place` / `--a-place`), PAS SUBIE -- c'est ce qui fait des verdicts
autre chose qu'une coincidence. L'ensemble de report natif est
`And(Damageable(AdjacentFriends(TARGET)), SurroundingEnemies(CASTER, range))` : le montage place
DEUX CONTRE-EXEMPLES, un ennemi adjacent a la cible mais HORS portee du caster (exclu par le 2e
volet) et un ennemi a portee du caster mais NON adjacent a la cible (exclu par le 1er). Chacun
entrerait dans la chaine si l'un des deux volets manquait au port.

TROIS REGIMES, qui exercent des chemins DIFFERENTS :

  R1 `survivant`  cible a 60 000 PV -> elle encaisse toute la salve, AUCUN coup n'est gaspille,
                  la chaine a UN maillon. C'est le seul regime NON CLAMPE : chaque coup applique
                  emet son event, donc la sequence per-coup ET le NOMBRE de coups appliques sont
                  confrontables valeur par valeur.
  R2 `chaine`     cible a 3 300 PV (elle tombe au 1er coup), relais a 90 000 (il SURVIT) -> le
                  report existe et son NOMBRE est lisible dans le live (un relais qui meurt
                  n'emet plus rien : son compte d'events ne dirait PAS combien de coups lui ont
                  ete demandes).
  R3 `tri`        DEUX relais eligibles, l'un a 90 000 PV et l'autre a 100 -> c'est
                  `SortTargetsByDamagePredictionSelector` seul qui tranche LEQUEL recoit le
                  report. Un port qui aurait saute le tri prendrait le premier de l'ordre
                  GEOMETRIQUE ; le verdict est l'accord ORDONNE offline/live.

MESURE = `probe_523_heavy_warp_flamer.py` (ce fichier ne duplique NI le montage NI les criteres :
il appelle le probe, foyer unique -- meme discipline que `test_504_kill_maim_burn_live.py`).

Le montage EXIGE ses regimes ; s'il ne les obtient pas, il ECHOUE, il ne skippe pas (#268) -- sauf
indisponibilite du host, qui n'est pas un verdict sur le port. ASCII only.
"""
from __future__ import annotations

#: Ce qui doit changer pour que ce FICHIER de test puisse changer de verdict (#486-r15).
DECLENCHEUR = {
    "chemins": (
        # SOCLE COMMUN a TOUT fichier de test : la cascade des `conftest.py` et sa fermeture.
        # Elles portent des fixtures `autouse` dont le verdict de CHAQUE test depend, et aucun
        # test ne les IMPORTE (semantique pytest) -- donc aucun graphe d'imports ne les verrait.
        "scripts/python/conftest.py", "scripts/python/tests/conftest.py",
        "scripts/python/tests/engine/conftest.py",
        "scripts/python/tests/engine/runner/conftest.py",
        "scripts/python/green_skip_guard.py", "scripts/python/declencheur_guard.py",
        "scripts/python/catalog_inject.py",
        "scripts/python/gameconfig.py", "scripts/python/enum_maps.py",
        "scripts/python/host_inputs.py", "scripts/python/rl_collect_batch.py",
        "scripts/python/stream_events.py", "scripts/python/symbols_layout.py",
        "scripts/python/engine/runner/snapshot.py",
        # PROPRE A CE FICHIER -- le probe qui porte le montage ET les mesures :
        "scripts/python/probe_523_heavy_warp_flamer.py",
        "scripts/python/probe_116_necrons.py",
        # LE MOTEUR ENTIER, deliberement : le rejeu passe par
        # `AbilityHandler.visit_ActiveAbilityMessage`, donc sa fermeture d'imports MESUREE traverse
        # le pipeline de degat, le PRNG, la cascade de ciblage, la prediction et la couche
        # d'effets -- tous capables de deplacer une valeur bit-exacte. Enumerer les seuls fichiers
        # de #523 serait DECLARER TROP ETROIT, et un declencheur trop etroit est un FAUX VERT.
        # ⚠ Les DEUX formes de glob sont necessaires : dans ce matcher `**/` exige un segment, donc
        # `engine/*.py` (racine du paquet) n'est PAS couvert par `engine/**/*.py` seul -- et
        # `scripts/python/**/*.py` seul raterait `scripts/python/board.py`.
        "scripts/python/*.py",
        "scripts/python/engine/*.py",
        "scripts/python/engine/**/*.py",
        "scripts/python/tests/**/*.py",
        # Le montage lit le gameconfig et le seed BC du BUILD (catalogue + magnitudes de 1227).
        "data/symbols/**",
        "data/seed-bc.json",
        "data/boards/**",
    ),
    "build": True,
    "toujours": False,
    "raison": "Le port de 1227 (arbre DSL `runner/abilities/thousandsons.py` : feuille partagee "
              "`ChainLeftOverHitsAttackDamage`, selecteurs `AdjacentFriends`/`SurroundingEnemies`/"
              "`Damageable`/`And`, noeud dynamique `GetNumTotalHits` avec `GetPersistentData`, "
              "selecteur `operations/damage_prediction_sort`), son cablage (registre "
              "`ABILITY_CLASSES`, `ABILITY_ATTACK_TYPE`, masque `targeting.py`) -- et tout le "
              "moteur que le rejeu hors-ligne traverse. `build: True` parce que la sequence "
              "per-coup est confrontee au NATIF au point pres, et que le porteur est amene par "
              "injection catalogue depuis le seed BC du build.",
}

import os
import sys

import pytest

_PY = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
if _PY not in sys.path:
    sys.path.insert(0, _PY)

import probe_523_heavy_warp_flamer as P                          # noqa: E402
from rl_collect_batch import _resolve_session                    # noqa: E402

# Les quatre `visualId` du montage, dans l'ordre T / B / D / E. `astraBullgryn` est la CIBLE parce
# que le nombre de coups REELLEMENT appliques depend d'elle (`AttackHitsWithModifiersFormula`) : sur
# `eldarRanger` la salve tombe a 2 coups, et `max(0, H - k - 1)` ne peut alors JAMAIS etre > 0 --
# le regime R2 serait inexercable. Choix MESURE, pas suppose.
FOES = "astraBullgryn,eldarRanger,tauCrisis,necroWarden"
# R1/R2 : un seul relais eligible + les DEUX contre-exemples.
POS_UN_RELAIS = [(0, 2), (1, 2), (0, 3), (2, 0)]
# R3 : DEUX relais eligibles (1,2)... non -- cible en (1,2), relais en (2,1) et (0,2), et le
# contre-exemple de PORTEE en (2,2) (d = 3 du caster).
POS_DEUX_RELAIS = [(1, 2), (2, 1), (0, 2), (2, 2)]


def _mesure(**kw):
    try:
        sid = _resolve_session()
    except Exception as e:                       # host injoignable != verdict du port
        pytest.skip("host indisponible (%s)" % (e,))
    sf = os.path.join(os.environ.get("TEMP", "."),
                      "t523_%s_%s.json" % (kw.pop("_tag"), os.getpid()))
    m = P.mesure(sid, sf, foes_ids=FOES, **kw)
    try:
        yield m
    finally:
        try:
            os.remove(sf)
        except OSError:
            pass


@pytest.fixture(scope="module")
def r1():
    """SURVIVANT -- le seul regime NON CLAMPE, donc le seul ou la sequence per-coup et le nombre de
    coups appliques sont confrontables valeur par valeur."""
    yield from _mesure(_tag="r1", hp_target=60000, foes_pos=POS_UN_RELAIS)


@pytest.fixture(scope="module")
def r2():
    """CHAINE -- la cible tombe au 1er coup et le relais SURVIT : le report est lisible."""
    yield from _mesure(_tag="r2", hp_target=3300, relay_hp=90000, foes_pos=POS_UN_RELAIS)


@pytest.fixture(scope="module")
def r3():
    """TRI -- deux relais eligibles, l'un intuable (90 000 PV) et l'autre a 100 PV."""
    yield from _mesure(_tag="r3", hp_target=100, relay_hp=90000, foes_pos=POS_DEUX_RELAIS,
                       caster_pos=(0, 0))


def _ordre_offline(m):
    return [int(c["target"]) for c in m["off_chain"]]


def _ordre_live(m):
    return list(m["live_per_hit"].keys())


# ------------------------------------------------------------------ le montage lui-meme

def test_r1_le_montage_a_bien_les_deux_contre_exemples(r1):
    """Sans eux, l'accord de la chaine ne prouverait RIEN : c'est leur ABSENCE du report qui
    separe les deux volets de `GetOtherTargets`."""
    assert r1 is not None
    ids, geo = r1["ids"], r1["geo"]
    assert r1["attendu"] == [ids["astraBullgryn"], ids["eldarRanger"]], (
        "l'ensemble geometrique attendu doit etre {cible, UN relais} : %r" % (r1["attendu"],))
    assert geo["tauCrisis"] == 3, "le contre-exemple de PORTEE doit etre a d=3 du caster"
    assert geo["necroWarden"] == 2, "le contre-exemple d'ADJACENCE doit etre a portee du caster"
    assert ids["necroWarden"] not in r1["attendu"], (
        "necroWarden est a portee mais NON adjacent a la cible -> hors report")


# ------------------------------------------------------------------ face DECISION (le masque)

def test_le_masque_de_ciblage_concorde_avec_le_natif(r1):
    """`abilityTargets(...).fromHere` = ce que le natif accepte SANS bouger. Le port doit rendre 0
    exactement sur ces entites-la. Un `TARGETING_OPTIONS` absent rendrait 0 PARTOUT, en silence."""
    ecarts = [(g["id"], g["visualId"], hex(g["reason"]), g["natif_legal"])
              for g in r1["gate"] if (g["reason"] == 0) != g["natif_legal"]]
    assert not ecarts, "masque de ciblage vs fromHere natif : %r" % (ecarts,)
    # Le caster lui-meme est REFUSE, et par le bon bit (`TargetIsEnemy`) : le masque ne porte pas
    # `CasterIsPossibleTarget`.
    moi = next(g for g in r1["gate"] if g["id"] == r1["caster"])
    assert moi["reason"] == 0x4000 and moi["natif_legal"] is False
    # Le contre-exemple de PORTEE est refuse par `TargetIsInRange`, pas par autre chose.
    hors = next(g for g in r1["gate"] if g["id"] == r1["ids"]["tauCrisis"])
    assert hors["reason"] == 0x8000000 and hors["natif_legal"] is False


# ------------------------------------------------------------------ R1 : regime SURVIVANT

def test_r1_le_cast_est_porte(r1):
    """Le prealable : sans lui, un desaccord ne dirait pas de quel cote il vient."""
    assert r1["port"].get("ported") is True, "1227 est ENCORE un no-op silencieux"
    assert r1["port"].get("dsl") is True
    assert r1["live"]["ok"] is True and not r1["live"]["errors"]


def test_r1_la_cible_survit_et_la_chaine_a_un_seul_maillon(r1):
    assert _ordre_offline(r1) == [r1["target"]]
    assert _ordre_live(r1) == [r1["target"]]


def test_r1_sequence_par_coup_et_nombre_de_coups_appliques(r1):
    """Regime NON CLAMPE : chaque coup applique emet son event, donc l'accord porte sur la
    SEQUENCE et sur le COMPTE -- jamais sur un total (un total resterait vert sur une
    redistribution des coups)."""
    t = r1["target"]
    off = r1["off_per_hit"][t]
    live = r1["live_per_hit"][t]
    assert off == live, "per-coup offline %r vs live %r" % (off, live)
    assert int(r1["off_chain"][0]["applied_hits"]) == len(live)
    assert r1["off_hp0"][t] > sum(off), "R1 doit etre le regime SURVIVANT"


def test_r1_le_noeud_de_coups_rend_nr_of_hits(r1):
    """`GetNumTotalHits` = `nrOfHits + min(compteur, maxNrOfHits - nrOfHits)`. Le compteur
    `(1227, "PSYCHIC_ATTACKS_KEY")` n'est ecrit que par la triggered 1546 (HORS #523) et aucune
    attaque alliee Psychic n'a eu lieu -> le noeud rend `nrOfHits`."""
    assert int(r1["off_chain"][0]["hits"]) == r1["nr_of_hits"]
    assert r1["nr_of_hits"] <= r1["max_nr_of_hits"]


# ------------------------------------------------------------------ R2 : la CHAINE

def test_r2_la_chaine_est_ordonnee_et_identique_au_natif(r2):
    assert r2["port"].get("ported") is True
    off, live = _ordre_offline(r2), _ordre_live(r2)
    assert len(live) == 2, "R2 doit EXERCER le report (chaine live = %r)" % (live,)
    assert off == live, "chaine offline %r vs live %r" % (off, live)
    assert live[0] == r2["target"] and live[1] == r2["eligible"]


def test_r2_aucune_cible_hors_de_l_ensemble_geometrique(r2):
    """LE verdict qui mord sur les deux contre-exemples : chacun entrerait dans la chaine si l'un
    des deux volets de `GetOtherTargets` manquait au port."""
    interdits = sorted((set(_ordre_live(r2)) | set(_ordre_offline(r2))) - set(r2["attendu"]))
    assert not interdits, "cibles hors de l'ensemble attendu %r : %r" % (r2["attendu"], interdits)


def test_r2_le_report_suit_la_loi_de_get_left_over_hits(r2):
    """`extraHitsAfterTargetKilled` est NULL -> report = `max(0, H - k) + 0` (#489-r1 : le `- 1`
    etait un coup de trop retire -- le compte natif est celui des entrees `LeftOverDamage` a flag
    `wasAlreadyDead` VRAI, donc les coups joues APRES le coup fatal). Le relais SURVIT (90 000 PV),
    donc son compte d'events LIVE EST son nombre de coups : c'est le verdict qui MORD, puisqu'il
    confronte le port au natif et non a la formule qui l'a produit."""
    H, k, attendu = P.left_over_attendu(r2["off_chain"][0])
    assert k is not None, "R2 doit TUER la cible du message"
    assert attendu > 0, "R2 doit produire un report NON NUL (baisser hp_target sinon)"
    assert int(r2["off_chain"][1]["hits"]) == attendu, "H=%s k=%s" % (H, k)
    assert len(r2["live_per_hit"][r2["eligible"]]) == attendu, (
        "le relais survit : son compte d'events live EST le nombre de coups reportes")


def test_r2_degats_par_cible_coup_par_coup(r2):
    """Par CIBLE, jamais sur un total. Le natif CESSE d'emettre des que
    `UnitExtensions.HasFlag(target, UnitFlag.Overkilled)` est vrai a l'entree
    d'`IdunBattle.Operations.ApplyDamageOperation$$Execute` : la sequence LIVE est un PREFIXE de la
    sequence offline clampee, dont la queue doit etre NULLE."""
    for t in sorted(set(r2["off_per_hit"]) | set(r2["live_per_hit"])):
        off = P.clamped(r2["off_per_hit"][t], r2["off_hp0"].get(t, 0))
        live = r2["live_per_hit"][t]
        assert len(off) >= len(live), "u%s offline %r vs live %r" % (t, off, live)
        assert off[:len(live)] == [int(x) for x in live], "u%s offline %r vs live %r" % (t, off, live)
        assert all(x == 0 for x in off[len(live):]), (
            "u%s : le port applique des coups NON NULS que le natif n'a pas emis (%r)" % (t, off))


# ------------------------------------------------------------------ R3 : le TRI de la chaine

def test_r3_deux_relais_eligibles_et_le_tri_tranche(r3):
    """Le report ne peut aller qu'a UN des deux, et c'est
    `SortTargetsByDamagePredictionSelector` qui le decide -- pas l'ordre geometrique de
    `AdjacentFriends`. L'accord ORDONNE offline/live est le seul verdict qui le mesure."""
    assert len(r3["attendu"]) == 3, (
        "R3 exige DEUX relais eligibles (ensemble attendu = %r)" % (r3["attendu"],))
    off, live = _ordre_offline(r3), _ordre_live(r3)
    assert len(live) == 2, "R3 doit EXERCER le report (chaine live = %r)" % (live,)
    assert off == live, "chaine offline %r vs live %r" % (off, live)
    # Le relais retenu est le TUABLE (100 PV), pas celui a 90 000 : c'est le rang `WillBeKill` du
    # selecteur de prediction qui le promeut.
    tuable = r3["ids"]["tauCrisis"]
    intuable = r3["ids"]["eldarRanger"]
    assert {tuable, intuable} <= set(r3["attendu"][1:])
    assert live[1] == tuable, (
        "le report doit aller au relais TUABLE u%s (PV %s), pas a u%s (PV %s)"
        % (tuable, r3["hp_of"].get(tuable), intuable, r3["hp_of"].get(intuable)))
