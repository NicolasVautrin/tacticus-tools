"""GARDE de `1087 ExemplarOfTheKauyon` (#488) -- la face COMBAT, etage par etage.

Avant #488 l'ability etait un **NO-OP SILENCIEUX** : absente d'`ABILITY_CLASSES`, donc la decision
la choisissait et l'execution l'ignorait -- 0 deplacement, 0 spawn, 0 degat, AUCUNE erreur. Ce
fichier garde les trois observables que le port doit desormais produire, chacun confronte au NATIF
sur le MEME substrat (le port rejoue le cast depuis le snapshot pris juste avant le cast natif) :

  E1 TELEPORT -- le caster atterrit sur la TUILE CIBLE ;
  E2 SPAWN    -- un `tauSmnDroneCommandLink` `Stationary` apparait sur l'EX-tuile du caster ;
  E3 COUPS    -- la SEQUENCE de coups est identique (arme puis les `nrOfHits` coups additionnels de
                 l'effet 1181 que le cast pose et retire autour de l'attaque).

MESURE = `probe_488_exemplar_of_the_kauyon.py` (ce fichier ne duplique NI le montage NI les
criteres : il appelle le probe, foyer unique -- meme discipline que
`test_exemplar_of_the_kauyon_hits_live.py` vis-a-vis de `probe_366r1`).

Le montage vient lui-meme de `probe_366r1_exemplar_kauyon_hits.build_extra` : crit/block a 0 et PV
a 300000 des DEUX cotes, donc aucun confond de crit, de block ou de mort ne peut deplacer la
sequence de coups.
"""
from __future__ import annotations

#: Ce qui doit changer pour que ce FICHIER de test puisse changer de verdict (#486-r15).
DECLENCHEUR = {
    "chemins": (
        # SOCLE COMMUN a TOUT fichier de test : la cascade des deux `conftest.py` et sa fermeture.
        # La cascade ENTIERE des `conftest.py` jusqu'a ce repertoire : `tests/engine/conftest.py`
        # et `tests/engine/runner/conftest.py` portent des fixtures `autouse` dont le verdict de
        # CHAQUE test de ce fichier depend, et aucun test ne les IMPORTE (semantique pytest).
        "scripts/python/conftest.py", "scripts/python/tests/conftest.py",
        "scripts/python/tests/engine/conftest.py",
        "scripts/python/tests/engine/runner/conftest.py",
        "scripts/python/green_skip_guard.py", "scripts/python/declencheur_guard.py",
        "scripts/python/catalog_inject.py",
        "scripts/python/gameconfig.py", "scripts/python/enum_maps.py",
        "scripts/python/host_inputs.py", "scripts/python/rl_collect_batch.py",
        "scripts/python/stream_events.py", "scripts/python/symbols_layout.py",
        "scripts/python/engine/runner/snapshot.py",
        # PROPRE A CE FICHIER -- le probe qui porte le montage ET les criteres, et son foyer de
        # montage (#366-r1) :
        "scripts/python/probe_488_exemplar_of_the_kauyon.py",
        "scripts/python/probe_366r1_exemplar_kauyon_hits.py",
        # LE MOTEUR ENTIER, deliberement : l'etage E3 REJOUE le cast hors-ligne sur un `Runner`
        # complet (`load_state` -> `ActiveAbilityMessage` -> attaque normale + effet 1181), donc
        # sa fermeture d'imports MESUREE couvre 140 modules de plus que les seuls fichiers touches
        # par la tranche -- pipeline de degat, PRNG, pathfinding, generateurs d'action IA compris,
        # tous capables de deplacer une valeur bit-exacte. Enumerer les fichiers de #488 serait
        # DECLARER TROP ETROIT, et un declencheur trop etroit est un FAUX VERT ; large est sain.
        # Les deux formes de glob sont necessaires : `**/` exige un segment, donc `engine/*.py`
        # (racine du paquet) ne serait pas couvert par `engine/**/*.py` seul.
        "scripts/python/*.py",
        "scripts/python/engine/*.py",
        "scripts/python/engine/**/*.py",
    ),
    "build": True,
    "toujours": False,
    "raison": "Le port de 1087 (arbre DSL dans `tau.py`, feuille `Teleport`, `DirectDisplaceOperation` "
              "case 4, resolution de tuile de `PerformAIAttack`), son cablage (registre, attack-type, "
              "masque et regle dynamique migres), l'effet 1181 qu'il pose -- et tout le moteur que le "
              "rejeu hors-ligne traverse. `build: True` parce que les quatre etages confrontent le "
              "NATIF : un changement de build deplace les valeurs d'arme comme les tuiles legales.",
}

import os
import sys

import pytest

_PY = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
if _PY not in sys.path:
    sys.path.insert(0, _PY)

import probe_488_exemplar_of_the_kauyon as P                # noqa: E402
import probe_366r1_exemplar_kauyon_hits as P366             # noqa: E402

BOARD = "MC1_67"
SEED = "777"


@pytest.fixture(scope="module")
def mesure():
    """Un SEUL cast natif + un SEUL rejeu porte pour les trois etages (le runner est cher)."""
    from engine.entities.pathfinding.board import Board
    sid = P366._sid()
    sf = os.path.join(os.environ.get("TEMP", "."), "t488_%s.json" % os.getpid())
    rid = P366.build(SEED, BOARD, sf)
    if rid is None:
        pytest.skip("build KO -- session/host indisponible")
    try:
        bg = P366._rpc(sid, "boardGraph", {"runnerId": rid}, 90)
        board = Board(bg["tiles"], adjacency="native_sym")
        rec = P.cast_natif(sid, rid, board, verbose=False)
        if rec is None:
            pytest.skip("geometrie du montage introuvable sur %s" % BOARD)
        port = P.rejeu_porte(rec, board)
        yield rec, port
    finally:
        P366._rpc(sid, "disposeRunner", {"runnerId": rid}, 60)
        try:
            os.remove(sf)
        except OSError:
            pass


def test_le_cast_est_porte_et_le_natif_a_bien_frappe(mesure):
    """Garde le PREALABLE des trois etages : sans lui, un `KO` ne dirait pas de quel cote il vient."""
    rec, port = mesure
    assert rec["ok"] is True, "le cast NATIF a echoue -- montage a revoir avant de juger le port"
    assert rec["n_hits"] > 0, "le natif n'a porte AUCUN coup : l'etage E3 serait vide et vert"
    assert (port["last"] or {}).get("ported") is True, (
        "l'ability 1087 n'est pas portee (retour du handler : %r) -- c'est le NO-OP SILENCIEUX "
        "d'avant #488" % (port["last"],))


def test_e1_le_caster_se_teleporte_sur_la_tuile_cible(mesure):
    """`Teleport(caster@0x48, target@0x60)` -> `DisplaceUnitOperation` case 4 (`Direct`)."""
    rec, port = mesure
    assert rec["carrier_after"] == rec["dst"], (
        "NATIF : le caster est en %s, pas sur la tuile cible %s" % (rec["carrier_after"], rec["dst"]))
    assert port["carrier_after"] == rec["dst"], (
        "PORT : le caster est en %s, pas sur la tuile cible %s" % (port["carrier_after"], rec["dst"]))


def test_e2_un_drone_stationary_apparait_sur_l_ex_tuile_du_caster(mesure):
    """`Spawn(caster@0x48, First(CanAddUnit(exTile + ...), 1), unitId, opts{AddTrait(Stationary)})`.

    L'EX-tuile est `AbilityEntities+0x40 = casterTile`, capturee AVANT le teleport : c'est ce qui
    fait atterrir le drone la ou Shadowsun etait, et non la ou elle arrive."""
    rec, port = mesure
    nat = [u for u in rec["spawned"] if u["visualId"] == P.SUMMON_VISUAL]
    prt = [u for u in port["spawned"] if u["visualId"] == P.SUMMON_VISUAL]
    assert len(nat) == 1, "NATIF : %d drone(s) au lieu d'un seul (%r)" % (len(nat), rec["spawned"])
    assert len(prt) == 1, "PORT : %d drone(s) au lieu d'un seul (%r)" % (len(prt), port["spawned"])
    assert nat[0]["pos"] == rec["ex_tile_pos"], (
        "NATIF : drone en %s, ex-tuile du caster %s" % (nat[0]["pos"], rec["ex_tile_pos"]))
    assert prt[0]["pos"] == rec["ex_tile_pos"], (
        "PORT : drone en %s, ex-tuile du caster %s" % (prt[0]["pos"], rec["ex_tile_pos"]))
    assert P.STATIONARY in nat[0]["traits"], "NATIF : le drone n'a pas le trait Stationary"
    assert prt[0]["stationary"] is True, "PORT : le drone n'a pas le trait Stationary"


def test_e3_la_sequence_de_coups_est_identique(mesure):
    """`AddEffect(1181, scale_from_source) & PerformAIAttackFromCurrentPosition & RemoveEffect(1181)`.

    On compare la SEQUENCE, jamais un total agrege : deux coups justes et deux faux peuvent donner
    la meme somme. La phase ARME et les coups additionnels sont donc gardes SEPAREMENT par leur
    position dans la liste."""
    rec, port = mesure
    seq_nat = [h["amount"] for h in rec["detail"]]
    seq_prt = []
    for d in port["detail"]:
        seq_prt += list(d["per_hit"]) + list(d["additional"])
    assert seq_nat == seq_prt, "sequence NATIVE %s != sequence PORTEE %s" % (seq_nat, seq_prt)
    assert rec["targets"] == sorted(set(port["targets"])), (
        "cibles NATIVES %s != cibles PORTEES %s" % (rec["targets"], sorted(set(port["targets"]))))


def test_e3bis_les_coups_additionnels_portent_le_niveau_du_caster(mesure):
    """LE CRAN SOUS E3, et il a MORDU (#488) : sans `scale_from_source=True` sur l'`AddEffect`, les
    coups additionnels retombaient au niveau 1 -- **40** au lieu de **3979** -- alors que la phase
    ARME etait deja bit-exacte. Un test qui ne regarderait que le COMPTE de coups serait reste VERT.

    L'`AbilityStateReference` (2e argument natif d'`AddEffect`) est ce qui transporte le niveau :
    `...ExemplarOfTheKauyon_AdditionalHitsEffectEffect$$CreateAdditionalHits` lit son degat par
    `DSLFormulas.ConfigVar(0xb = dmg, GetAbilityState(effet), config)`."""
    rec, port = mesure
    add = []
    for d in port["detail"]:
        add += list(d["additional"])
    assert add, "aucun coup additionnel porte : l'effet 1181 n'a pas ete pose par le cast"
    # Les coups additionnels sont les DERNIERS de la sequence native (l'arme d'abord).
    attendus = [h["amount"] for h in rec["detail"]][-len(add):]
    assert add == attendus, (
        "coups additionnels PORTES %s != NATIFS %s -- un niveau d'ability qui retombe sur 1 donne "
        "des valeurs d'ordre 40" % (add, attendus))
