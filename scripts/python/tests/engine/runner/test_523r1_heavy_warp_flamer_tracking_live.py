"""GARDE LIVE #523-r1 -- la triggered `1546 HeavyWarpFlamer_AttackTracking` confrontee au NATIF sur
le MEME substrat.

LE CRITERE : le compteur avance-t-il aux MEMES MOMENTS et de la MEME QUANTITE que chez le natif ?
Il n'a AUCUN canal de lecture live (`dumpEntityComponents` rend la MISE EN PAGE des composants, pas
leurs valeurs) -- son seul observable est le NOMBRE DE COUPS du `1227 HeavyWarpFlamer`. Le montage
est donc construit pour que ce nombre CHANGE entre deux casts successifs du MEME porteur :

    tour 1 : deux allies PSYCHIQUES attaquent (+1 chacun) + un allie PHYSIQUE (+0) -> nrOfHits + 2
    tour 2 : `On(TurnEnd)` a vide la cle, personne n'attaque avant le cast     -> nrOfHits

Un accord a valeur CONSTANTE ne prouverait rien : c'est le DELTA, mesure des DEUX cotes, qui est le
verdict (`VERDICT-4`). Les trois modes de panne sont separes par le meme montage -- ne rien compter
(delta 0), compter aussi le PHYSIQUE (3 au lieu de 2), ne pas VIDER (delta 0 avec un tour 2 haut).

CE QUI N'EST PAS CONFRONTE, ET POURQUOI C'EST MESURE : au tour 1 le prelude d'attaques DESALIGNE le
PRNG (mesure : `mti` live 3/5/11 vs offline 2/4/9) -- la MAGNITUDE par coup n'y est donc pas
comparable, et le probe le DIT au lieu de la comparer quand meme. Le desalignement n'appartient pas
a cette tranche : la 3e attaque (PHYSIQUE) ne declenche PAS 1546 et ajoute pourtant un tirage. Le
tour 2, lui, n'a AUCUN prelude -> la magnitude y est confrontee bit-exact (`VERDICT-6b`).

MESURE = `probe_523r1_heavy_warp_flamer_tracking.py` (ce fichier ne duplique NI le montage NI les
criteres : il appelle le probe, foyer unique -- meme discipline que `test_523_heavy_warp_flamer_live`).

Le montage EXIGE ses regimes ; s'il ne les obtient pas, il ECHOUE, il ne skippe pas (#268) -- sauf
indisponibilite du host, qui n'est pas un verdict sur le port. ASCII only.
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
        # PROPRE A CE FICHIER -- le probe qui porte le montage ET les mesures :
        "scripts/python/probe_523r1_heavy_warp_flamer_tracking.py",
        "scripts/python/probe_116_necrons.py",
        # LE MOTEUR ENTIER, deliberement : le rejeu passe par `Runner` + ses handlers par defaut
        # (attaques normales des allies PUIS `AbilityHandler.visit_ActiveAbilityMessage`), donc sa
        # fermeture d'imports MESUREE traverse le pipeline de degat, le PRNG, le bus de triggers, la
        # cascade de ciblage et la couche d'effets -- tous capables de deplacer une valeur
        # bit-exacte. Enumerer les seuls fichiers de #523-r1 serait DECLARER TROP ETROIT, et un
        # declencheur trop etroit est un FAUX VERT.
        # ⚠ Les DEUX formes de glob sont necessaires : dans ce matcher `**/` exige un segment, donc
        # `engine/*.py` (racine du paquet) n'est PAS couvert par `engine/**/*.py` seul -- et
        # `scripts/python/**/*.py` seul raterait `scripts/python/board.py`.
        "scripts/python/*.py",
        "scripts/python/engine/*.py",
        "scripts/python/engine/**/*.py",
        "scripts/python/tests/**/*.py",
        # Le montage lit le gameconfig (armes/profils des allies, constantes de 1227), le seed BC
        # du build (injection catalogue du porteur) et le board.
        "data/symbols/**",
        "data/seed-bc.json",
        "data/boards/**",
    ),
    "build": True,
    "toujours": False,
    "raison": "Le port de la triggered 1546 (`operations/triggers/loki/heavy_warp_flamer.py` : les "
              "deux disjoints `On(9)` / `On(TurnEnd)`, la feuille `SetPersistentData` et le noeud "
              "VALEUR `Sum(GetPersistentData, 1)`), son cablage (`ACTIVE_ABILITY_TRIGGERS`), le "
              "LECTEUR `GetNumTotalHits` de #523 -- et tout le moteur que le rejeu hors-ligne "
              "traverse. `build: True` parce que le nombre de coups ET la sequence per-coup du "
              "tour 2 sont confrontes au NATIF au point pres, et que le porteur est amene par "
              "injection catalogue depuis le seed BC du build.",
}

import os
import sys

import pytest

_PY = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
if _PY not in sys.path:
    sys.path.insert(0, _PY)

import probe_523r1_heavy_warp_flamer_tracking as P                # noqa: E402
from rl_collect_batch import _resolve_session                     # noqa: E402


@pytest.fixture(scope="module")
def m():
    """UN seul runner pour tout le fichier : il porte les DEUX tours, donc les deux bras du
    verdict de VARIATION."""
    try:
        sid = _resolve_session()
    except Exception as e:                       # host injoignable != verdict du port
        pytest.skip("host indisponible (%s)" % (e,))
    sf = os.path.join(os.environ.get("TEMP", "."), "t523r1_%s.json" % os.getpid())
    mes = P.mesure(sid, sf)
    try:
        yield mes
    finally:
        try:
            os.remove(sf)
        except OSError:
            pass


def _coups(m, tour):
    """(offline, live) = les sequences per-coup sur la CIBLE, pour le tour demande."""
    t = m["target"]
    if tour == 1:
        return (m["off_apres"]["per_hit"].get(t) or [], m["live1"].get(t) or [])
    off = m["tour2"]["off"]
    return ((off["per_hit"].get(t) if off else None) or [], m["tour2"]["live"].get(t) or [])


# ------------------------------------------------------------------ le montage lui-meme

def test_le_montage_a_bien_ses_trois_profils(m):
    """Sans le TEMOIN physique, l'accord ne separerait pas « compte les attaques PSYCHIQUES » de
    « compte toutes les attaques alliees ». Et c'est la DISTANCE (2) qui fait choisir l'arme RANGED
    `Psychic` des deux Thousand Sons plutot que leur arme de melee `Flame` -- on la LIT, on ne la
    suppose pas."""
    assert m is not None
    assert m["off_apres"]["profils"] == ["Psychic", "Psychic", "Physical"], (
        "profils REELLEMENT emis par les trois attaques d'allie : %r"
        % (m["off_apres"]["profils"],))
    assert m["geo"]["A1->cible"] == 2 and m["geo"]["A2->cible"] == 2
    assert m["geo"]["A3->cible"] == 1
    # Le caster n'est ADJACENT a aucun ennemi : sinon `ForceMeleeTarget` (preset `+0x140`) rabat la
    # portee a 1 et le cast a d = 2 deviendrait illegal pour une raison etrangere a la mesure.
    assert min(v for k, v in m["geo"].items() if k.startswith("C->")) == 2


# ------------------------------------------------------------------ le COMPTEUR, etage par etage

def test_le_compteur_avance_de_un_par_attaque_psychique_alliee(m):
    """La suite `[0, 1, 2, 2]` : +1, +1, puis RIEN sur le temoin PHYSIQUE. C'est le seul endroit ou
    le compteur lui-meme est lisible (offline) ; le live, lui, ne l'expose que par ses effets."""
    suite = [(t["compteur"] or 0) for t in m["off_apres"]["trace"]]
    assert suite == [0, 1, 2, 2], "suite du compteur : %r" % (suite,)


def test_le_noeud_de_coups_lit_le_compteur(m):
    """`GetNumTotalHits` = `nrOfHits + min(compteur, maxNrOfHits - nrOfHits)`."""
    nr, mx = m["nr_of_hits"], m["max_nr_of_hits"]
    assert m["off_base"]["hits"] == nr, "sans prelude, le noeud doit rendre `nrOfHits`"
    assert m["off_apres"]["hits"] == nr + min(m["off_apres"]["compteur_avant_cast"] or 0, mx - nr)
    assert m["off_apres"]["hits"] > nr, "le montage n'a rien ajoute : regime DEGENERE"


# ------------------------------------------------------------------ le NATIF, les deux tours

def test_tour1_le_nombre_de_coups_est_celui_du_natif(m):
    off, live = _coups(m, 1)
    assert m["live1_ok"] is True and not m["live1_err"]
    assert len(live) > 0, "aucun event de degat 1227 -- le cast natif n'a rien fait"
    assert len(off) == len(live), "tour 1 : offline %d coups vs live %d" % (len(off), len(live))


def test_tour2_le_nombre_de_coups_retombe_a_la_base(m):
    """Apres `On(TurnEnd)` cote natif, le cast SUIVANT ne beneficie plus d'aucun coup
    supplementaire. Le montage RE-FABRIQUE la geometrie si le tour adverse l'a defaite (le caster
    est deplace sur une tuile a d = 2 de la cible et a >= 2 de tout autre ennemi) : etre << bloque
    par la geometrie >> n'est pas un resultat."""
    assert m["tour2"]["off"] is not None, (
        "le 2e cast n'a PAS eu lieu (legal=%r, caster@%r cible@%r, repositionnement=%r) -- sans lui "
        "l'accord du tour 1 ne prouve RIEN sur la VARIATION"
        % (m["tour2"]["legal"], m["tour2"]["caster_pos"], m["tour2"]["target_pos"],
           m["tour2"]["repositionne"]))
    off, live = _coups(m, 2)
    assert len(live) > 0 and len(off) == len(live), (
        "tour 2 : offline %d coups vs live %d" % (len(off), len(live)))


def test_le_delta_entre_les_deux_tours_est_le_meme_des_deux_cotes(m):
    """LE VERDICT. Un accord a valeur constante serait DEGENERE : ce qui prouve que le compteur
    avance -- et qu'il est remis a zero -- c'est que le nombre de coups CHANGE, de la meme quantite
    chez le port et chez le natif."""
    off1, live1 = _coups(m, 1)
    off2, live2 = _coups(m, 2)
    d_off, d_live = len(off1) - len(off2), len(live1) - len(live2)
    assert d_off > 0, "regime DEGENERE : le nombre de coups n'a pas varie cote port"
    assert d_off == d_live, "delta offline %d vs live %d" % (d_off, d_live)
    assert d_live == 2, (
        "deux attaques PSYCHIQUES alliees, donc +2 coups -- %d signifie que le temoin PHYSIQUE a "
        "ete compte, ou qu'une psychique ne l'a pas ete" % d_live)


def test_tour2_la_magnitude_par_coup_est_bit_exacte(m):
    """Le tour 2 n'a AUCUN prelude : la capture est fraiche et le cast est la PREMIERE consommation
    de PRNG des deux cotes -- la magnitude y est donc comparable, et elle doit l'etre au point pres.
    Critere = celui de #523 : la sequence LIVE est un PREFIXE de la sequence offline CLAMPEE par les
    PV, dont la queue est NULLE (le natif cesse d'emettre des que
    `UnitExtensions.HasFlag(target, UnitFlag.Overkilled)` est vrai)."""
    assert m["tour2"]["off"] is not None
    off, live = _coups(m, 2)
    hp0 = (m["tour2"]["off"]["hp0"] or {}).get(m["target"], 0)
    clam = P.clamped(off, hp0)
    assert len(clam) >= len(live)
    assert clam[:len(live)] == [int(x) for x in live], "offline(clampe) %r vs live %r" % (clam, live)
    assert all(x == 0 for x in clam[len(live):]), (
        "le port applique des coups NON NULS que le natif n'a pas emis : %r" % (clam,))


def test_tour1_la_magnitude_n_est_pas_confrontee_et_le_probe_le_DIT(m):
    """Le prelude d'attaques desaligne le PRNG. Ce test ne blanchit RIEN : il fige que le
    desalignement est MESURE (positions du PRNG des deux cotes) et non suppose, et que le probe
    refuse alors de comparer des magnitudes plutot que d'imputer a cette tranche un ecart qui
    appartient au modele de degat des attaques du prelude."""
    rl = m.get("rng_live_avant_cast") or {}
    ro = m["off_apres"].get("rng_avant_cast") or {}
    assert rl.get("mti") is not None and ro.get("mti") is not None, (
        "sans les DEUX positions de PRNG, l'exemption du tour 1 ne serait pas mesuree")
    mti_live = [a.get("mti") for a in m["att_live"]]
    mti_off = [t.get("mti") for t in m["off_apres"]["trace"][1:]]
    assert all(x is not None for x in mti_live + mti_off)
    # Le desalignement n'est PAS imputable a 1546 : la 3e attaque (PHYSIQUE) ne declenche pas le
    # trigger et fait pourtant croitre l'ecart.
    ecarts = [int(a) - int(b) for a, b in zip(mti_live, mti_off)]
    assert ecarts[-1] >= ecarts[1], (
        "l'ecart de PRNG a cesse de croitre sur l'attaque PHYSIQUE (%r) : re-instruire le residu, "
        "il pourrait alors etre lie au trigger" % (ecarts,))
