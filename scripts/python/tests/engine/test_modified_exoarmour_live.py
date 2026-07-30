"""ModifiedExoarmour (1529, Kimm `votanChampion`) -- terme de MOUVEMENT `5 x |chemin|`, LIVE.

CE QUE CE TEST GARDE, et pourquoi il ne peut pas passer par accident
-------------------------------------------------------------------
`IdunBattle.AI.Playbook.Loki.ModifiedExoarmourPlaybook$$CalculateMovementUtilityInStepsInternal`
ajoute au composite Tile(7), via la feuille `TriggeredAbilitiesUtility(2)`,
`ModifiedExoarmour_LikesMovingPerTile` (= 5) x `path.Count`, ou `path` est le chemin
`IPathfinders.GetPath(unit, GetMainTile(unit), tuileCandidate, null)` du **WalkPathfinder** et
`Count` compte les NOEUDS, extremites INCLUSES. Rester sur place vaut **0** (court-circuit
`UtilityMovementCase$$StaysOnTile`), PAS `5 x 1`.

La confrontation est faite PAR ETAGE (cf. `probe_304_modified_exoarmour`) : l'etage PREDICTION est
pris au NATIF (`pairUtility`), l'etage TUILE au PORT. C'est indispensable ici -- sur ce montage, la
prediction de degat de l'attaque normale de Kimm depuis une tuile d'arrivee diverge (natif 44.395 vs
port 17.8 a `Damage=1000` sur MC1_67/909, residu ANTERIEUR et ETRANGER a #304) ; comparer des
DECISIONS COMPLETES conclurait sur ce residu-la.

Trois gardes, dont deux ADVERSARIALES :

  1. `test_engine_matches_native_argmax`   -- l'argmax `pair_natif + custom + Tile7_port` reproduit
     l'action ET la tuile que le natif joue, dans les 4 bras.
  2. `test_term_is_decisive`               -- LE ROUGE : terme RETIRE, l'argmax choisit 1222 sur
     place la ou le natif bouge. C'est exactement le fait qui a oblige #27-r1 a retirer le passif.
  3. `test_flat_term_model_is_refuted` + `test_weight_bracket_contains_five` -- les 4 bras imposent
     un encadrement sur le coefficient : NON VIDE et contenant 5 sous le modele `k x |chemin|`,
     **VIDE** sous le modele FORFAIT (`k` des qu'on bouge). Deux longueurs de chemin JOUEES par le
     natif (n=4 sur MC1_67/909, n=3 sur C4_09/31337) sont ce qui separe les deux modeles -- avec une
     seule, ils sont indistinguables.

MONTAGE : la fixture `MDA_FIXTURE` de #27-r1, bras `--passive-on` (kit REEL de Kimm). Confonds
neutralises : Kimm n'est JAMAIS deplacee (un `act move` rendrait 1222 illegale), la cible est a
distance >= 2, les porteurs d'aura de degat sont figes loin, les appats ne sont jamais poses sur la
tuile d'attaque du natif (verdict V0 de #27-r1).

PORTEUR HORS POOL : `votanChampion` est absent du seed BC capture -> injecte par `catalog_inject.py`
dans une COPIE sous `logs/` (jamais le seed partage).

Aucun scalaire de gameplay n'est fige : le poids vient de la BC re-synthetisee depuis le gameconfig
vivant, l'encadrement des `pairUtility` NATIVES du montage.

ASCII only.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

PYDIR = Path(__file__).resolve().parents[2]                 # scripts/python
sys.path.insert(0, str(PYDIR))

import probe_304_modified_exoarmour as PB                   # noqa: E402
import probe_27_r1_massdriver_custom as MDA                 # noqa: E402

# Les DEUX montages du cas. Les `Damage` encadrent la bascule 69 / 1222 de CHAQUE plateau (mesures) :
# sur chacun, un bras ou le natif RESTE sur place (borne HAUTE du coefficient) et un bras ou il BOUGE
# (borne BASSE). Les deux tuiles jouees ont des |chemin| DIFFERENTS -- c'est cela, et rien d'autre,
# qui separe `k x n` d'un forfait.
MONTAGES = [("MC1_67", 909, [900, 1000]),
            ("C4_09", 31337, [3000, 3600])]


@pytest.fixture(scope="module")
def bras():
    """Rejoue les 4 bras et rend `[(board, seed, damage, nat_ab, nat_tile, n, cons), ...]`."""
    try:
        MDA.ensure_seed_bcs()
    except Exception as exc:                                # noqa: BLE001
        pytest.skip("catalog_inject KO : porteur votanChampion non injectable (%s)" % exc)
    out = []
    rid = None
    for board, seed, damages in MONTAGES:
        geom = None
        for d in damages:
            ok, rid, geom, cons = PB.phase_a(d, board, seed, geom)
            out.append({"board": board, "seed": seed, "damage": d, "cons": cons})
    try:
        yield out
    finally:
        if rid is not None:
            try:
                PB.L._rpc("disposeRunner", [{"runnerId": rid}])
            except Exception:                               # noqa: BLE001
                pass


def _acc(bras, model):
    iv = (None, None)
    for b in bras:
        iv = PB._intersect(iv, b["cons"][model])
    return iv


def test_native_plays_two_distinct_path_lengths(bras):
    """Le montage exerce bien DEUX longueurs de chemin JOUEES par le natif (plus les bras ou il reste
    sur place). Sans cela, forfait et `k x n` sont indistinguables et les tests suivants ne
    prouveraient rien -- c'est le garde-fou du montage, pas du port."""
    moved = sorted({b["cons"]["n_played"] for b in bras if b["cons"]["n_played"]})
    assert len(moved) >= 2, (
        "le natif ne joue qu'une seule longueur de chemin %s sur les 4 bras -- re-calibrer les "
        "`Damage` ou changer de plateau, sinon la proportionnalite n'est pas testee" % moved)


def test_weight_bracket_contains_five(bras):
    """L'argmax NATIF des 4 bras impose `lo < k < hi` sous le modele `k x |chemin|`. Le poids LU au
    gameconfig (`ModifiedExoarmour_LikesMovingPerTile` = 5) doit y tomber."""
    from engine import weights as W
    w = W.load().sub("TriggeredAbilities", PB.WEIGHT_KEY)
    lo, hi = _acc(bras, "prop")
    assert (lo is None or lo < w) and (hi is None or w < hi), (
        "poids lu = %r hors de l'encadrement impose par le natif (%s, %s) -- la formule portee ou "
        "l'etage Tile(7) est faux" % (w, lo, hi))


def test_flat_term_model_is_refuted(bras):
    """MUTATION ADVERSARIALE STRUCTURELLE : sous un terme FORFAITAIRE (meme valeur des qu'on bouge),
    les memes choix natifs imposent un encadrement **VIDE**. Un coefficient est une constante du jeu :
    un intervalle vide REFUTE le modele. C'est ce qui rend la proportionnalite MESUREE."""
    lo, hi = _acc(bras, "flat")
    assert lo is not None and hi is not None and lo >= hi, (
        "le modele FORFAIT reste admissible (%s < k < %s) -- ce montage ne separe pas les deux "
        "hypotheses, il faut deux longueurs de chemin jouees plus contrastees" % (lo, hi))


def test_engine_matches_native_argmax(bras):
    """Accord etage-a-etage dans les 4 bras : `argmax [pair_natif + custom + Tile7_port]` == l'action
    ET la tuile que le natif JOUE. (`phase_a` le verifie bras par bras et rend `ok` faux sinon.)"""
    bad = [(b["board"], b["seed"], b["damage"]) for b in bras if not b["cons"].get("v2", True)]
    assert not bad, "argmax != natif sur les bras %s" % bad


def test_term_is_decisive(bras):
    """LE ROUGE : dans les bras ou le natif BOUGE, retirer le terme fait choisir 1222 SUR PLACE.
    Sans ce test, le port pourrait etre juste par accident (terme nul et natif immobile)."""
    seen = [b for b in bras if b["cons"].get("v3")]
    assert seen, (
        "aucun bras ou l'absence du terme change l'argmax -- le montage ne mesure pas le terme, "
        "il ne fait que ne pas le contredire")
