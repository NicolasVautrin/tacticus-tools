"""GARDE de `1038 FoulInfusion` (#500) -- la face COMBAT, etage par etage.

Avant #500 l'ability etait un **NO-OP SILENCIEUX** : absente d'`ABILITY_CLASSES`, donc la decision
la choisissait et l'execution l'ignorait -- 0 effet, 0 degat, AUCUNE erreur. Ce fichier garde les
quatre observables que le port doit desormais produire, chacun confronte au NATIF sur le MEME
substrat (le port rejoue le cast depuis la capture prise juste avant le cast natif) :

  E1 BUFF      -- l'ensemble EXACT des porteurs de l'effet 0x432 = 1074 `FoulInfusion_ExtraHits` ;
  E2 CIBLE     -- l'ennemi tire par `PickRandomly(Attackable(AdjacentEnemies(Caster)), 1)` ;
  E3 MONTANT   -- le total inflige (arme + le coup additionnel `Toxic` que le buff ajoute) ;
  E4 SEQUENCE  -- le buff est pose AVANT l'attaque : c'est ce qui rend l'attaque LIBRE du cast
                  plus forte, et c'est la SEULE lecture qu'un critere sur le COMPTE de coups ne
                  verrait pas (AB2 rend le meme nombre de coups d'arme et un total different).

MESURE = `probe_500_foul_infusion.py` (ce fichier ne duplique NI le montage NI les criteres : il
appelle le probe, foyer unique -- meme discipline que `test_exemplar_of_the_kauyon_live.py`
vis-a-vis de `probe_488`).

Le montage EXIGE ses regimes ; s'il ne les obtient pas, il ECHOUE, il ne skippe pas (#268) --
sauf indisponibilite du host, qui n'est pas un verdict sur le port. ASCII only.
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
        # PROPRE A CE FICHIER -- le probe qui porte le montage ET les criteres :
        "scripts/python/probe_500_foul_infusion.py",
        # LE MOTEUR ENTIER, deliberement : le rejeu passe par `Runner.apply(ActiveAbilityMessage)`,
        # donc sa fermeture d'imports MESUREE traverse le pipeline de degat, le PRNG, le
        # pathfinding, la cascade de ciblage et la couche d'effets -- tous capables de deplacer une
        # valeur bit-exacte. Enumerer les seuls fichiers de #500 serait DECLARER TROP ETROIT, et un
        # declencheur trop etroit est un FAUX VERT ; large est sain.
        # ⚠ Les DEUX formes de glob sont necessaires : dans ce matcher `**/` exige un segment, donc
        # `engine/*.py` (racine du paquet) n'est PAS couvert par `engine/**/*.py` seul -- et
        # `scripts/python/**/*.py` seul raterait `scripts/python/board.py`.
        "scripts/python/*.py",
        "scripts/python/engine/*.py",
        "scripts/python/engine/**/*.py",
        "scripts/python/tests/**/*.py",
    ),
    "build": True,
    "toujours": False,
    "raison": "Le port de 1038 (arbre DSL `runner/abilities/loki/foul_infusion.py`, feuilles "
              "`AddEffect`/`UseActiveAbility`, formule d'aura `AuraEffectRange`, selecteurs "
              "`SurroundingFriends`/`UnitsWithTrait`/`AdjacentEnemies`/`PickRandomly`), son "
              "cablage (registre `ABILITY_CLASSES`, `ABILITY_ATTACK_TYPE`, masque et regle "
              "dynamique migres depuis `targeting.py`), l'effet 1074 qu'il pose "
              "(`entities/effects/loki/hits.py`) -- et tout le moteur que le rejeu hors-ligne "
              "traverse. `build: True` parce que les quatre etages confrontent le NATIF : un "
              "changement de build deplace les valeurs d'arme comme les traits d'alliance.",
}

import os
import sys

import pytest

_PY = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
if _PY not in sys.path:
    sys.path.insert(0, _PY)

import probe_500_foul_infusion as P                          # noqa: E402


@pytest.fixture(scope="module")
def mesure():
    """UN seul montage + UN seul cast natif + UN rejeu porte + les cinq contre-epreuves.

    Le runner est cher : tous les etages lisent la MEME mesure, et le probe le dispose lui-meme."""
    try:
        sid = P._sid()
    except Exception as e:                                    # host injoignable != verdict du port
        pytest.skip("host indisponible (%s)" % (e,))
    sf = os.path.join(os.environ.get("TEMP", "."), "t500_%s.json" % os.getpid())
    m = P.mesure(sid, sf, avec_ab=True)
    if m is None:
        pytest.skip("build KO -- session/host indisponible")
    try:
        yield m
    finally:
        try:
            os.remove(sf)
        except OSError:
            pass


def test_le_montage_est_discriminant(mesure):
    """LE PREALABLE. Chacune des six unites du montage sert a discriminer UNE lecture ; si l'une
    d'elles manquait a l'appel, l'accord des etages suivants ne prouverait plus la meme chose.

    Le pool d'attaque doit contenir DEUX ennemis : sur un pool de 1, `PickRandomly` rendrait la
    bonne cible sans que le tirage soit teste (AB5 le montre : sans tirage, la cible CHANGE)."""
    a = mesure["avant"]
    for vid in (P.CASTER, P.ALLY_CHAOS_NEAR, P.ALLY_CHAOS_FAR, P.ALLY_PLAIN, P.FOE_A, P.FOE_B):
        assert vid in a, "montage incomplet : %s absent" % vid
    ab = mesure["ab"]
    assert ab["AB5_sans_tirage"]["cible"] != ab["REF"]["cible"], (
        "pool d'attaque NON discriminant : sans tirage la cible serait la meme, donc "
        "`PickRandomly` ne serait pas mesure")


def test_le_cast_est_porte_et_le_natif_a_bien_agi(mesure):
    """Garde le prealable des quatre etages : sans lui, un `KO` ne dirait pas de quel cote il vient.

    `last['ported'] is True` est l'observable EXACTE qui distingue le port du NO-OP silencieux
    d'avant #500 -- le handler rend `ported=False` quand `ABILITY_CLASSES` n'a pas l'entree."""
    m = mesure
    assert (m["port"]["last"] or {}).get("ported") is True, (
        "l'ability 1038 n'est pas portee (retour du handler : %r) -- c'est le NO-OP SILENCIEUX "
        "d'avant #500" % (m["port"]["last"],))
    assert m["natif"]["buffes"], "le cast NATIF n'a pose AUCUN effet : rien a confronter"
    assert m["natif"]["delta"], "le cast NATIF n'a inflige AUCUN degat : l'etage E3 serait vide"


def test_e1_le_buff_va_au_caster_et_aux_seuls_allies_chaos_de_l_aura(mesure):
    """`op_Addition( UnitsWithTrait(SurroundingFriends(Caster, ContagionsOfNurgleRange(Owner)),
    0x7ea Chaos), Caster )`. Les TROIS exclusions sont testees dans le MEME etat :
      * l'allie Chaos a distance 2 est HORS de l'aura (rayon 1 au tour 1) ;
      * l'allie non-Chaos a distance 1 est filtre par `UnitsWithTrait` ;
      * aucun ennemi n'est buffe (`SurroundingFriends`)."""
    m = mesure
    ids = m["ids"]
    attendu = {ids[P.CASTER], ids[P.ALLY_CHAOS_NEAR]}
    assert set(m["natif"]["buffes"]) == attendu, (
        "NATIF : porteurs de 1074 = %r, attendu %r" % (sorted(m["natif"]["buffes"]), sorted(attendu)))
    assert set(m["port"]["buffes"]) == set(m["natif"]["buffes"]), (
        "PORT %r != NATIF %r" % (sorted(m["port"]["buffes"]), sorted(m["natif"]["buffes"])))


def test_e2_e3_la_cible_et_le_montant_sont_ceux_du_natif(mesure):
    """`PickRandomly(Attackable(AdjacentEnemies(Caster)), 1)` puis `UseNormalAttack`. Le delta de
    PV est compare A L'UNITE PRES : il porte la cible (E2) ET le montant (E3) d'un seul bloc, et le
    montant inclut le coup additionnel `Toxic` de l'effet pose juste avant."""
    m = mesure
    assert m["port"]["delta"] == m["natif"]["delta"], (
        "delta PV PORT=%r NATIF=%r" % (m["port"]["delta"], m["natif"]["delta"]))
    assert len(m["natif"]["delta"]) == 1, (
        "regime attendu : UNE seule unite touchee (l'ennemi tire) -- %r" % (m["natif"]["delta"],))


def test_e4_les_cinq_contre_epreuves_ecartent_toutes_du_natif(mesure):
    """LA garde du cas. Un accord ne vaut que si le desaccord etait POSSIBLE : chaque variante ne
    change QU'UNE lecture du mirror, et chacune doit s'ecarter du natif.

    AB2 (ordre inverse) est celle qui compte : le NOMBRE de coups d'arme y est IDENTIQUE, seule la
    SEQUENCE change -- un critere sur le compte serait reste VERT."""
    m = mesure
    ref = m["ab"]["REF"]
    nat_total = sum(m["natif"]["delta"].values())
    assert ref["total"] == nat_total, (
        "le mirror hors-ligne (%s) doit reproduire le total natif (%s)" % (ref["total"], nat_total))
    ecarts = {}
    for nom, r in m["ab"].items():
        if nom == "REF":
            continue
        ecarts[nom] = (r["buffes"] != ref["buffes"] or r["cible"] != ref["cible"]
                       or r["total"] != ref["total"])
    non_discriminantes = [n for n, ok in ecarts.items() if not ok]
    assert non_discriminantes == [], (
        "contre-epreuve(s) NON discriminante(s) -- la lecture correspondante n'est pas mesuree "
        "par ce montage : %r" % (non_discriminantes,))
    assert m["ab"]["AB2_ordre_inverse"]["cible"] == ref["cible"], (
        "AB2 doit differer par le MONTANT, pas par la cible -- sinon elle ne teste pas la SEQUENCE")
    assert m["ab"]["AB2_ordre_inverse"]["total"] < ref["total"], (
        "AB2 : sans le buff pose AVANT, l'attaque libre doit etre STRICTEMENT plus faible")
