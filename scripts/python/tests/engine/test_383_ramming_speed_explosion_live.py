"""#383 -- les batchs 3/4 (EXPLOSION) de `RammingSpeed` (1059) confrontes au LIVE.

MEME greffe que `#353` (aucune unite du gameconfig ne porte 1059), plus les TROIS conditions de
montage que `#361`/`#381` ont fait payer :

  1. la GATE `!self.Any(p => p.Prediction.WillBeKill)` doit etre OUVERTE -- `--hp-player 60` fait
     que le recul (`nrOfHits_2` coups) tue le caster ;
  2. le caster doit AVOIR LA MAIN (`ensure_turn` apres le drive) -- sinon
     `MovementQuery$$FindAnyOrAllMoveableTiles` repart sur un `OrderedSet` VIDE (garde FLAG) et les
     batchs manquent POUR UNE RAISON DE MONTAGE ;
  3. le voisinage de la tuile d'arrivee doit porter un AMI **et** un ENNEMI.

Le probe DERIVE son verdict des champs mesures et REFUSE de conclure si l'une des trois manque --
ces tests lisent ce verdict, ils ne le re-fabriquent pas.

GENERALISATION : quatre couples (board, seed), dont un ou le caster est BLESSE (`hp_current`), le
seul regime ou l'axe `StatPart` de `StatAmount(Owner, Health, part = 2 -> MAXIMUM)` est OBSERVABLE
(`--hp-player` pose `Health` ET `RemainingHealth`, donc courant == max). C'est ce bras-la qui a
trouve le bug de port.

ASCII only.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

PYDIR = Path(__file__).resolve().parents[2]                 # scripts/python
sys.path.insert(0, str(PYDIR))

import probe_383_ramming_speed_explosion_port as P          # noqa: E402

MONTAGES = {
    "mc167": dict(seed=38300, level=8, board="MC1_67"),
    "mc167_blesse": dict(seed=38300, level=8, board="MC1_67", hp_current=30),
    "c120": dict(seed=38603, level=8, board="C1_20"),
    "mc163": dict(seed=38704, level=8, board="MC1_63"),
}


@pytest.fixture(scope="module")
def measured():
    out = {}
    for key, m in MONTAGES.items():
        r = P.run(verbose=False, **m)
        assert not r.get("error"), "%s KO : %s" % (key, r["error"])
        out[key] = r
    return out


def test_the_montage_reaches_the_regime(measured):
    """Pre-condition : sans les trois conditions, un accord ne dirait RIEN du natif -- c'est
    exactement le faux verrou de `#353-r1` (2 events pour 5 attendus, quatre hypotheses fausses)."""
    for key, r in measured.items():
        assert r.get("native_playbook") == "RammingSpeedPlaybook", (
            "%s : playbook natif = %r" % (key, r.get("native_playbook")))
        assert r.get("caster_has_turn") is True, "%s : le caster n'a pas la main" % key
        assert r.get("n_native", 0) > 2, (
            "%s : le natif rend %s events -- les batchs 3/4 sont vides, rien a confronter"
            % (key, r.get("n_native")))
        rp = r.get("ring_port") or {}
        assert rp.get("friends") and rp.get("enemies"), (
            "%s : l'anneau de la tuile d'arrivee ne porte pas un AMI ET un ENNEMI (%s) -- les deux "
            "batchs ne se distinguent pas" % (key, rp))


def test_the_port_equals_the_native_event_for_event(measured):
    for key, r in measured.items():
        assert r["port_sig"] == r["native_sig"], (
            "%s : port %s != natif %s" % (key, r["port_sig"], r["native_sig"]))
        assert r["ok"], "%s : verdict du probe = ECHEC (%s)" % (key, r.get("verdict"))


def test_the_charge_tile_is_the_one_the_native_lands_on(measured):
    """L'etage TUILE, confronte par le CAST REEL (`ExecuteBehaviour` = `If(!IsAdjacent(caster,
    target), MoveUnit(caster, GetTileToMoveTo()))`). Il est SEPARE de l'etage SELECTEUR : sans lui,
    un ecart d'events ne dirait pas lequel des deux a bouge."""
    for key, r in measured.items():
        assert r.get("native_tile"), "%s : le cast reel n'a pas abouti" % key
        assert r.get("tile_match"), (
            "%s : tuile du port %s != tuile ou le natif POSE le caster %s"
            % (key, r.get("port_tile"), r.get("native_tile")))


def test_the_explosion_amount_is_a_share_of_MAX_health(measured):
    """`PercentageOf(StatAmount(Owner, Health, MAXIMUM), Sum(ConfigConst(1021, 0xf), ...))`.

    Le bras `mc167_blesse` a `hp != hpMax` : c'est le SEUL ou cet axe est observable, et c'est lui
    qui a fait tomber le port (`UnitContext.get_stat(Health, 2)` rend le COURANT)."""
    import gameconfig as GC
    pct = int(((GC.trait("Explodes") or {}).get("variables") or {}).get("explodesDmg"))
    blesse = measured["mc167_blesse"]
    assert blesse["caster_hp"] != blesse["caster_hpmax"], "bras non discriminant : hp == hpMax"
    for key, r in measured.items():
        assert r["explosion_amount"] == round(r["caster_hpmax"] * pct / 100), (
            "%s : amount %s != %d%% du maxPV (%s)"
            % (key, r["explosion_amount"], pct, r["caster_hpmax"]))
    assert blesse["explosion_amount"] != round(blesse["caster_hp"] * pct / 100), (
        "le bras BLESSE ne separe pas la base MAX de la base COURANTE")
