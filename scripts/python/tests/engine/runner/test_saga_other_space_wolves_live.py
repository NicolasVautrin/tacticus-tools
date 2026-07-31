"""CLIQUET #366-r1 -- `SagaOfTheWarriorBorn_OtherSpaceWolves` (1224) sur un ALLIE Space Wolf.

1224 n'est PAS un calque de 1223 : c'est la MEME CLASSE NATIVE. Les deux fabriques
`IdunBattle.Core.Services.EffectsDatabase.u003Cu003Ec$$u003CInitializeEffectsu003Eb__14_241` (1223)
et `…b__14_242` (1224) sont bit-identiques -- meme slot `Il2CppClass*`, meme
`IdunBattle.Entities.Effects.Loki.SagaOfTheWarriorBorn_OwnerEffect$$.ctor`, aucun argument variable
-- et sur les 607 enregistrements ce slot ne couvre QUE ces deux ids. Le registre du port pointe
donc la MEME classe depuis les deux entrees ; `test_registry_shares_one_class` verrouille ce fait,
qui est le coeur du port.

POSE (face SEPAREE, non portee -- residu nomme) :

    IdunBattleLogic.Entities.Abilities.Triggered.Loki.SagaOfTheWarriorBorn_KillAbility$$CreateTrigger
        = OnDeath(triggerOnOverkill: 1, triggerOnSteppable: 0) & get_OwnerIsActor
          & HasTrait(Target, 0x10 = UnitTrait.Hero)
    …$$CreateBehaviour
        = AddEffect(0x4c8, AbilityStateReference, source = Owner,
                    targets = UnitsFromFaction(Friends(Owner, <pool>, OnlyAlive) - Owner,
                                               0xd = UnitFaction.SpaceWolves, OnlyAlive))

Le montage EXERCE donc le natif : Ragnar execute un Hero ennemi, le jeu pose 1224 sur l'allie.

CARRE 2x2 -- c'est le CROISEMENT qui fait la preuve, aucune case ne suffit seule :

    |            | 1224 PRESENT (kill) | 1224 ABSENT (temoin) |
    | CHARGE     |  6 coups            |  3 coups             |
    | STEP_ADJ.  |  3 coups            |  3 coups             |

La contribution n'est comptee QUE dans la case (present, chargeant). Une case seule serait
ininterpretable : 6 vs 3 sur la ligne CHARGE isole l'EFFET, 6 vs 3 sur la colonne kill isole le
GATE `IsCharging`.

MESURE (MC1_67 / seed 777, `spaceWulfen` <<Ulf>> -- 3 coups d'arme, `extraHits[50]` = 3, donc
l'effet DOUBLE la salve : le rapport le plus large des quatre receveurs possibles).
VUE ROUGE par MUTATION (inscription retiree d'`EFFECT_CLASSES`), verbatim :

    [KILL/CHARGE] LIVE    n=6 [2679, 3724, 2879, 3771, 3273, 3750]
    [KILL/CHARGE] OFFLINE n=3 [2679, 3724, 2879]
    [KILL/CHARGE] VERDICT hits DIVERGE | per_hit DIVERGE

Les 3 premiers coups etaient DEJA bit-exacts : la divergence est localisee au NOMBRE de coups, pas
a leur valeur. `KILL/STEP_ADJACENT` restait VERT sous la meme mutation -- la garde discrimine donc
l'inscription de 1224, et rien d'autre.

Probe de mesure : `probe_366_r1_saga_other_space_wolves.py` (foyer unique du montage `execute_hero`,
importe ici plutot que re-transcrit : deux transcriptions du meme montage finissent par diverger).

ASCII only.
"""
from __future__ import annotations

import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(__file__))      # helpers siblings
from _charge_regime import (CHARGE, STEP_ADJACENT,                 # noqa: E402,F401  (fixture)
                            charge_regime)

from engine.entities.effects.factory import EFFECT_CLASSES         # noqa: E402
from engine.entities.effects.loki import SagaOfTheWarriorBornOwnerEffect   # noqa: E402
from probe_366_r1_saga_other_space_wolves import execute_hero      # noqa: E402

_ALLY = "spaceWulfen"               # <<Ulf>>, Space Wolf du pool, RECEVEUR de 1224
_RAGNAR = "spaceBlackmane"          # <<Ragnar>>, seul porteur de l'ability (poseur)
_VICTIM = "necroOverlord"           # Hero ennemi execute par Ragnar (trait 0x10)
_EFFECT_NAME = "SagaOfTheWarriorBorn_OtherSpaceWolves"
#: PV de la victime : assez bas pour tomber en un echange, assez haut pour ne pas mourir d'un
#: deplacement. `--hp-target` vaut pour TOUT le camp -> seul le per-unit garde un encaisseur.
_VICTIM_HP = ["--unit-stat", "%s:Health=400,RemainingHealth=400" % _VICTIM]


def _names(u):
    return [e.get("name") for e in (u.get("effects") or []) if isinstance(e, dict)]


def _wolves(charge_regime, seed, board, a_units, do_kill):
    h = charge_regime(p_units="%s,%s" % (_RAGNAR, _ALLY), a_units=a_units,
                      seed=seed, board=board, extra=(_VICTIM_HP if do_kill else None))
    ally = h.by_visual(_ALLY)
    victim = h.by_visual(_VICTIM)
    if ally is None or (do_kill and victim is None):
        pytest.fail("roster incomplet : ally=%s victim=%s" % (ally is not None, victim is not None))
    if do_kill:
        # ECHEC FORT, jamais un skip : un kill non obtenu veut dire que le regime n'est pas
        # atteint, et un skip VERT mentirait sur une garde qui n'a rien garde.
        assert execute_hero(h, _RAGNAR, victim["id"]), \
            "Ragnar n'a pas execute %s -- le trigger OnDeath & OwnerIsActor n'est pas exerce" % _VICTIM
        assert _EFFECT_NAME in _names(h.by_visual(_ALLY)), (
            "%s absent de l'allie apres le kill -- le natif n'a pas pose l'effet, "
            "il n'y a rien a confronter (effets vus : %s)"
            % (_EFFECT_NAME, _names(h.by_visual(_ALLY))))
    else:
        assert _EFFECT_NAME not in _names(ally), \
            "%s present SANS kill -- le temoin serait vacu" % _EFFECT_NAME
    return h


@pytest.fixture(scope="module")
def wolves(charge_regime):
    """BRAS KILL -- Ragnar execute un Hero ennemi, le natif pose 1224 sur `spaceWulfen`."""
    return _wolves(charge_regime, "777", "MC1_67", "%s,necroWarden" % _VICTIM, True)


@pytest.fixture(scope="module")
def wolves_nokill(charge_regime):
    """BRAS TEMOIN -- personne ne meurt, 1224 n'existe pas. Meme roster, memes cibles, PV pleins."""
    return _wolves(charge_regime, "777", "MC1_67", "%s,necroWarden" % _VICTIM, False)


@pytest.fixture(scope="module")
def wolves_alt(charge_regime):
    """GENERALISATION -- meme invariant, AUTRE board (`C1_25`), AUTRE seed (31337)."""
    return _wolves(charge_regime, "31337", "C1_25", "%s,necroWarden" % _VICTIM, True)


def _run(h, regime):
    rec = h.run(caster_visual=_ALLY, regime=regime)
    if rec is None:
        pytest.skip("geometrie %s non realisable sur ce board" % regime)
    if not rec["live_ok"] or not rec["live_per_hit"]:
        pytest.skip("attaque normale live refusee/vide (%s)" % regime)
    # Une cible MORTE tronque le flux d'evenements (l'overkill est cape aux PV restants) : `n`
    # mesurerait la mort, pas les coups. On REFUSE plutot que de mesurer en degrade.
    assert any(u.get("id") == rec["target"] for u in h.alive()), (
        "la cible u%s est morte pendant la salve (%s) -- `n` live tronque" % (rec["target"], regime))
    return rec, h.replay_offline(rec)


def _carried(rec, off):
    """1224 doit etre MATERIALISE offline sur le caster -- sinon le test compare deux absences."""
    st = off["state"]
    return [e for e in (st.effects.by_unit.get(rec["caster"]) or [])
            if e.effect_type == 1224 or e.name == _EFFECT_NAME]


def test_registry_shares_one_class():
    """Garde STRUCTURELLE (offline, sans jeu) -- LE fait que ce port etablit.

    Le natif n'a qu'UNE classe pour 1223 et 1224 ; le port doit pointer LA MEME instance de classe
    depuis les deux entrees. Une seconde classe (meme parfaitement recopiee) introduirait une
    distinction que le natif n'a pas, et divergerait au premier changement de l'une des deux."""
    assert EFFECT_CLASSES.get("SagaOfTheWarriorBorn_Owner") is SagaOfTheWarriorBornOwnerEffect
    assert EFFECT_CLASSES.get(_EFFECT_NAME) is SagaOfTheWarriorBornOwnerEffect
    assert EFFECT_CLASSES[_EFFECT_NAME] is EFFECT_CLASSES["SagaOfTheWarriorBorn_Owner"], \
        "1223 et 1224 partagent UN slot Il2CppClass* -- le port doit partager UNE classe"


def test_gate_is_tristate_offline():
    """Le gate est TRI-ETAT : contexte absent -> rien (le natif commence par `AreEntitiesAdjacent`,
    donc sans positions il rend FAUX, jamais VRAI). Une contribution rendue sans charge PROUVEE
    serait un bonus inconditionnel."""
    e = SagaOfTheWarriorBornOwnerEffect(name=_EFFECT_NAME, effect_type=1224, level=1,
                                        ability_level=50)
    assert e.create_effect_hits_bonus_for_attack(True, None) is None
    assert e.create_effect_hits_bonus_for_attack(True, {"is_charging": False}) is None
    got = e.create_effect_hits_bonus_for_attack(True, {"is_charging": True})
    assert got is not None and got.kind == "Addition" and got.value > 0, \
        "charge PROUVEE -> ForAddition(extraHits) ; obtenu %r" % (got,)


def test_charge_grants_extra_hits(wolves):
    """CAS ROUGE AVANT LE FIX -- l'allie qui PORTE 1224 et qui CHARGE gagne `extraHits`."""
    rec, off = _run(wolves, CHARGE)
    assert _carried(rec, off), \
        "1224 n'est pas materialise offline sur l'allie -- le test comparerait deux absences"
    assert rec["target"] in off["charged"], (
        "la cible DOIT entrer dans ChargedUnitIds ; charged=%s target=%s"
        % (off["charged"], rec["target"]))
    assert len(off["per_hit"]) == len(rec["live_per_hit"]), (
        "CHARGE : le port ne compte pas la contribution de 1224 -- live n=%d %s offline n=%d %s "
        "(delta hits=%d)" % (len(rec["live_per_hit"]), rec["live_per_hit"],
                             len(off["per_hit"]), off["per_hit"],
                             len(off["per_hit"]) - len(rec["live_per_hit"])))
    assert off["per_hit"] == rec["live_per_hit"], (
        "CHARGE : meme nombre de coups mais valeurs differentes -- live=%s offline=%s"
        % (rec["live_per_hit"], off["per_hit"]))


def test_step_adjacent_grants_nothing(wolves):
    """REGIME DISCRIMINANT -- 1224 est PRESENT, l'allie BOUGE, mais la cible etait DEJA adjacente.

    `MoveUnitOperation$$UpdateCharging` n'inscrit que les unites NOUVELLEMENT adjacentes :
    `IsCharging` FAUX alors que `UnitFlag.Moved` est VRAI. Un gate `has_moved` accorderait ici."""
    rec, off = _run(wolves, STEP_ADJACENT)
    assert _carried(rec, off), "1224 doit etre present (sinon le gate n'est pas exerce)"
    assert rec["target"] not in off["charged"], (
        "la cible ne doit PAS entrer dans ChargedUnitIds ; charged=%s target=%s"
        % (off["charged"], rec["target"]))
    assert len(off["per_hit"]) == len(rec["live_per_hit"]), (
        "STEP_ADJACENT : le port sur-applique 1224 (gate `has_moved` ?) -- live n=%d %s "
        "offline n=%d %s" % (len(rec["live_per_hit"]), rec["live_per_hit"],
                             len(off["per_hit"]), off["per_hit"]))
    assert off["per_hit"] == rec["live_per_hit"], (
        "STEP_ADJACENT : live=%s offline=%s" % (rec["live_per_hit"], off["per_hit"]))


def test_witness_without_kill(wolves_nokill):
    """TEMOIN -- sans kill, 1224 n'existe pas : la charge du MEME allie rend la salve NUE.

    Verrouille que le port ne fabrique pas de coups quand l'effet est absent."""
    rec, off = _run(wolves_nokill, CHARGE)
    assert not _carried(rec, off), "1224 ne doit pas exister sans kill"
    assert rec["target"] in off["charged"]
    assert off["per_hit"] == rec["live_per_hit"], (
        "TEMOIN CHARGE : live=%s offline=%s" % (rec["live_per_hit"], off["per_hit"]))


def test_effect_actually_bites_live(wolves, wolves_nokill):
    """Le natif SEPARE bien les deux bras -- sinon les tests ci-dessus passeraient pour une raison
    TRIVIALE (aucun bonus nulle part, deux zeros qui s'accordent). On compare deux mesures LIVE,
    jamais le port : c'est ce qui rend le regime PROBANT."""
    rec_kill, _ = _run(wolves, CHARGE)
    rec_wit, _ = _run(wolves_nokill, CHARGE)
    assert len(rec_kill["live_per_hit"]) > len(rec_wit["live_per_hit"]), (
        "le natif doit porter PLUS de coups avec 1224 qu'sans -- KILL n=%d, TEMOIN n=%d "
        "(si egal, le montage n'exerce pas l'effet et la garde ne garde rien)"
        % (len(rec_kill["live_per_hit"]), len(rec_wit["live_per_hit"])))


def test_charge_other_board(wolves_alt):
    """GENERALISATION du cas rouge : autre board (`C1_25`), autre seed (31337)."""
    rec, off = _run(wolves_alt, CHARGE)
    assert _carried(rec, off)
    assert rec["target"] in off["charged"]
    assert off["per_hit"] == rec["live_per_hit"], (
        "CHARGE (C1_25/31337) : live n=%d %s offline n=%d %s"
        % (len(rec["live_per_hit"]), rec["live_per_hit"], len(off["per_hit"]), off["per_hit"]))


def test_step_adjacent_other_board(wolves_alt):
    """GENERALISATION du regime discriminant."""
    rec, off = _run(wolves_alt, STEP_ADJACENT)
    assert _carried(rec, off)
    assert rec["target"] not in off["charged"]
    assert off["per_hit"] == rec["live_per_hit"], (
        "STEP_ADJACENT (C1_25/31337) : live n=%d %s offline n=%d %s"
        % (len(rec["live_per_hit"]), rec["live_per_hit"], len(off["per_hit"]), off["per_hit"]))
