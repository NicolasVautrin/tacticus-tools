"""CLIQUET `IsCharging` du canal COUPS (residu N16) -- `UnstoppableFerocity_OwnerEffect` (1032).

DEUXIEME consommateur de charge du canal `CreateEffectHitsBonusForAttack` a etre porte, apres
`SagaOfTheWarriorBorn_Owner` (1223, `case-ischarging-hits`). MIRROR de
`IdunBattle.Entities.Effects.Loki.UnstoppableFerocityOwnerEffect$$CreateEffectHitsBonusForAttack` :

    EffectBonus.ForAddition( get_OwnerIsCaster & IsCharging(caster@0x160, target@0x178),
                             Direct( AbilityConfiguration.GetNumberConstant(config@+0x60,
                                                                           0x2b = extraHit) ) )

DEUX noeuds trigger : ni `IsNormalAttack`, ni `IsMeleeAttack`. Magnitude = la CONSTANTE `extraHit`
de l'ability source (`ABondEffect..ctor(this, 1, 0, AbilityOrEffect(0x40b =
TriggeredAbilityType.UnstoppableFerocity))`), donc **+1 coup**, ni indexee par niveau ni
rarity-scalee.

CE QUI DIFFERE DE 1223, ET C'EST TOUT LE MONTAGE : le porteur n'est pas un hero du pool mais le
SUMMON `blackSmnBloodletter`, amene par l'`Incursion` (1021) d'Archimatos. **Un summon ne se pilote
pas** (`applyAction {kind:"ability"}` rend `mutated=False` : son activation est consommee par son
auto-deplacement). On OBSERVE donc l'IA le jouer et on LIT les `changes` de l'`endturn` -- detail
mesure, pieges de roster et forme des donnees : `_bloodletter_montage.py`.

L'observable est le NOMBRE DE COUPS, DISCRET : l'arme du Bloodletter porte **1 coup**, donc
1 -> 2 est un DOUBLEMENT, hors de portee de tout bruit d'armure, de percage ou de crit. Et comme le
MT est recale sur le dump PRE-`endturn` et que le pas ne consomme aucun tirage, la confrontation est
BIT-EXACTE sur le total, pas seulement encadrante.

TROIS OBSERVATIONS, TROIS ROLES DISTINCTS -- mesure live verbatim (runner 6/7, seed 1357, MC1_67,
cibles `orksNob,tyranTyrantGuard`) :

  * TEMOIN `on-appearance`  -- le summon apparait AU CONTACT et frappe, sans AUCUN
                              `MoveUnitOperation` -> `IsCharging` FAUX.   live = **1 coup, 1721**.
  * `CHARGE`                -- pose a distance 2, l'IA l'amene au contact -> `IsCharging` VRAI.
                              live delta = **3285** ; offline AVEC 1032 = n=2 [1707, 1578] total
                              **3285** (MATCH) ; offline SANS 1032 = n=1 total **1707** (DIVERGE).
                              C'est le CAS ROUGE AVANT LE FIX, verbatim.
  * `ADJACENT`              -- pose DEJA au contact, cible AMENEE en dernier (c'est SA liste
                              `ChargedUnitIds` qui s'ecrit, pas celle du caster) : le caster a
                              BOUGE mais n'a PAS charge. live delta = **1707**, offline n=1 total
                              **1707**, `charged=[]`. REGIME DISCRIMINANT : un gate `has_moved` y
                              accorderait le +1.

⚠ CIBLE NON PSYKER : le meme kit porte un SECOND effet, `UnstoppableFerocity_ExtraHit` (0x4a8=1192)
= `ForAddition(HasTrait(target@0x178, 0x3ea = Psyker) & get_OwnerIsCaster, Direct(1))`, SANS aucun
noeud `IsCharging`. Sur une cible Psyker les deux +1 se confondraient. Garde explicite ci-dessous.

ASCII only.
"""
from __future__ import annotations

import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(__file__))      # helpers siblings
from _bloodletter_montage import (EFFECT_ID, EFFECT_NAME, SAFE_ENEMIES,   # noqa: E402
                                  SAFE_TARGET, SUMMONER, SUMMON_VIS,
                                  BloodletterHarness, on_appearance_hits,
                                  replay_attack_offline, summon_bloodletters)

from engine.entities.effects.factory import EFFECT_CLASSES        # noqa: E402
from engine.entities.effects.loki import UnstoppableFerocityOwnerEffect   # noqa: E402

_PSYKER_TRAIT = "Psyker"                             # UnitTrait 0x3ea -- gate de l'effet 1192
_ALT_ENEMIES = "admecMarshall,astraBullgryn"         # generalisation : ni Psyker ni Overwatch
_ALT_TARGET = "admecMarshall"                        # ni Healer ni aura defensive passive


# ---------------------------------------------------------------- gardes STRUCTURELLES (offline) #

def test_registry_carries_the_effect():
    """Garde STRUCTURELLE (offline, sans jeu) : l'effet est enregistre SOUS SON NOM CAPTE, et son
    gate est TRI-ETAT. Une contribution rendue sans `is_charging` PROUVE serait un bonus
    inconditionnel -- exactement la regression permissive que le CLAUDE.md decrit."""
    assert EFFECT_CLASSES.get(EFFECT_NAME) is UnstoppableFerocityOwnerEffect
    e = UnstoppableFerocityOwnerEffect(name=EFFECT_NAME, effect_type=EFFECT_ID, level=1,
                                       ability_level=50)
    assert e.create_effect_hits_bonus_for_attack(True, None) is None, \
        "contexte ABSENT -> aucune contribution (le natif commence par AreEntitiesAdjacent)"
    assert e.create_effect_hits_bonus_for_attack(True, {"is_charging": False}) is None
    got = e.create_effect_hits_bonus_for_attack(True, {"is_charging": True})
    assert got is not None and got.kind == "Addition" and got.value == 1, \
        "charge PROUVEE -> ForAddition(GetNumberConstant(0x2b = extraHit) = 1) ; obtenu %r" % (got,)


def test_no_normal_attack_gate():
    """Le decompile n'a que DEUX noeuds : le bonus vaut aussi pour une attaque NON normale.
    Poser un `IsNormalAttack` (copie reflexe de `PowerTrip_FullHealth`, qui LUI en a un) rendrait
    le port faux sur le vecteur ability-attack."""
    e = UnstoppableFerocityOwnerEffect(name=EFFECT_NAME, effect_type=EFFECT_ID, level=1)
    assert e.create_effect_hits_bonus_for_attack(False, {"is_charging": True}) is not None


def test_targets_are_not_psykers():
    """CONFOND ECARTE : l'effet JUMEAU `UnstoppableFerocity_ExtraHit` (1192) donne LUI AUSSI +1 coup,
    mais gate `HasTrait(target, Psyker)` et SANS `IsCharging`. Si une cible de ce fichier etait
    Psyker, le regime discriminant mesurerait la somme des deux et ne discriminerait plus rien.

    Le meme balayage verifie l'AUTRE condition de realisabilite du montage (cf.
    `_bloodletter_montage`) : ni `Overwatch` ni porteur de zone de danger, sinon le Bloodletter
    (3888 PV, non gonfles) meurt pendant les poses."""
    import gameconfig as GC
    for vid in (SAFE_ENEMIES + "," + _ALT_ENEMIES).split(","):
        traits = (GC.unit(vid) or {}).get("traits") or []
        assert _PSYKER_TRAIT not in traits, (
            "%s porte %s -> l'effet 1192 ajouterait un +1 coup NON gate par la charge, "
            "confondu avec 1032" % (vid, _PSYKER_TRAIT))
        assert "Overwatch" not in traits, (
            "%s porte Overwatch -> il abat le Bloodletter pendant les poses du montage" % vid)


# ----------------------------------------------------------------------------- montage live      #

def _observe(rpc, build_runner, regime, seed, board_id, a_units, enemy):
    """Monte UN runner FRAIS (obligatoire : aucun `FinishUnitTurn` ne purge les `ChargedUnitIds`
    entre deux regimes), amene le summon, pose la geometrie, laisse l'IA jouer, et rejoue offline."""
    from engine.entities.pathfinding.board import Board
    rid = build_runner(seed, extra=["--p-units", SUMMONER, "--a-units", a_units,
                                    "--hp-target", "120000", "--hp-player", "120000"],
                       board=board_id)["rid"]
    bg = rpc("boardGraph", {"runnerId": rid}, 60)
    if not (isinstance(bg, dict) and bg.get("tiles")):
        pytest.skip("boardGraph indispo")
    board = Board(bg["tiles"], adjacency="native_sym")
    s, err = summon_bloodletters(rpc, rid, enemy)
    if err:
        pytest.skip("montage summon KO : %s" % err)
    h = BloodletterHarness(rpc, rid, board)
    smn = [u for u in s["new"] if u.get("visualId") == SUMMON_VIS]
    if not smn:
        pytest.skip("aucun %s apparu" % SUMMON_VIS)
    bid, tid = smn[0]["id"], s["target_id"]
    h.my_player = smn[0].get("owner")
    out = {"h": h, "rid": rid, "board": board, "caster": bid, "target": tid,
           "summon_effect_names": {e.get("name") for e in (smn[0].get("effects") or [])},
           "on_appearance": on_appearance_hits(s["cast"], [bid], tid)}
    plan = h.arrange_regime(bid, tid, regime)
    if plan is None:
        pytest.skip("geometrie %s non realisable (summon vivant=%s)"
                    % (regime, any(u["id"] == bid for u in h.alive())))
    out["plan"] = plan
    snap = h.snapshot()
    out["snap"] = snap
    obs = h.observe_endturn(bid, tid)
    if not obs["target_delta"]:
        pytest.skip("l'IA n'a pas fait attaquer le summon (%s)" % regime)
    mv = obs["caster_to"] if obs["caster_moved"] else None
    out["obs"] = obs
    out["with"] = replay_attack_offline(snap, board, bid, tid, move_to=mv)
    out["without"] = replay_attack_offline(snap, board, bid, tid, move_to=mv, force_no_charge=True)
    return out


@pytest.fixture(scope="module")
def charge(rpc, build_runner):
    """Le caster est pose a distance 2 : c'est l'IA qui l'amene AU CONTACT -> `IsCharging` VRAI."""
    return _observe(rpc, build_runner, "CHARGE", "1357", "MC1_67", SAFE_ENEMIES, SAFE_TARGET)


@pytest.fixture(scope="module")
def adjacent(rpc, build_runner):
    """REGIME DISCRIMINANT : caster pose DEJA au contact, cible AMENEE en dernier."""
    return _observe(rpc, build_runner, "ADJACENT", "1357", "MC1_67", SAFE_ENEMIES, SAFE_TARGET)


@pytest.fixture(scope="module")
def charge_alt(rpc, build_runner):
    """GENERALISATION : autre board, autre seed, autres cibles."""
    return _observe(rpc, build_runner, "CHARGE", "31337", "C1_25", _ALT_ENEMIES, _ALT_TARGET)


# ------------------------------------------------------------------------------ les observations #

def test_summon_carries_the_passive_live(charge):
    """Le summon frais porte l'effet 1032 cote LIVE (pose a l'init de l'ability) -- c'est ce qui
    rend le port ATTEIGNABLE : `load_state` le reconstruit depuis `decisionView.effects`, sans
    qu'aucune face SUMMON offline soit requise."""
    assert EFFECT_NAME in charge["summon_effect_names"], (
        "le Bloodletter ne porte pas %s live ; effets vus = %s"
        % (EFFECT_NAME, sorted(charge["summon_effect_names"])))
    assert charge["with"]["effect_present"], \
        "l'effet 1032 n'est pas materialise offline -- le test comparerait deux absences"


def test_on_appearance_is_not_a_charge(charge):
    """TEMOIN : le summon apparait AU CONTACT et frappe sans aucun `MoveUnitOperation`. Le spawn ne
    passe donc PAS par `UpdateCharging` -> un seul coup, alors que la cible est adjacente. Sans ce
    temoin, « adjacent » et « a charge » resteraient confondus."""
    hits = charge["on_appearance"].get(charge["caster"]) or []
    assert len(hits) == 1, (
        "on-appearance : le natif doit porter l'arme NUE (1 coup) ; obtenu n=%d %s"
        % (len(hits), hits))


def test_charge_grants_extra_hit(charge):
    """CAS ROUGE AVANT LE FIX -- la charge ajoute `extraHit` = 1 coup, et le port le rend
    BIT-EXACTEMENT. La borne `off-1032` rend le MATCH probant : sans elle, un accord pourrait etre
    le MATCH trivial « aucun bonus des deux cotes »."""
    d = charge
    assert d["obs"]["caster_moved"], "l'IA n'a pas deplace le summon -- ce n'est pas une charge"
    assert d["target"] in d["with"]["charged"], (
        "la cible DOIT entrer dans ChargedUnitIds (nouvellement adjacente) ; charged=%s target=%s"
        % (d["with"]["charged"], d["target"]))
    assert len(d["with"]["per_hit"]) == 2, (
        "CHARGE : le port doit porter 2 coups (arme 1 + extraHit 1) ; obtenu n=%d %s"
        % (len(d["with"]["per_hit"]), d["with"]["per_hit"]))
    assert d["with"]["total"] == d["obs"]["target_delta"], (
        "CHARGE : le port n'applique pas le +extraHit de charge -- live delta=%s, "
        "offline AVEC 1032 n=%d %s total=%s, offline SANS 1032 n=%d %s total=%s"
        % (d["obs"]["target_delta"], len(d["with"]["per_hit"]), d["with"]["per_hit"],
           d["with"]["total"], len(d["without"]["per_hit"]), d["without"]["per_hit"],
           d["without"]["total"]))
    assert d["without"]["total"] != d["obs"]["target_delta"], (
        "la borne SANS l'effet doit DIVERGER, sinon le MATCH ci-dessus est trivial "
        "(live=%s, off-1032=%s)" % (d["obs"]["target_delta"], d["without"]["total"]))


def test_adjacent_grants_nothing(adjacent):
    """REGIME DISCRIMINANT -- le caster a ete DEPLACE par le montage (flag `Moved` VRAI) mais la
    cible est arrivee APRES lui, donc c'est la liste de LA CIBLE qui s'est ecrite : `IsCharging`
    FAUX. Un gate `has_moved` accorderait le +1 ici."""
    d = adjacent
    assert d["with"]["effect_present"], "l'effet 1032 doit etre present (sinon le gate n'est pas exerce)"
    assert d["target"] not in d["with"]["charged"], (
        "la cible ne doit PAS entrer dans les ChargedUnitIds du caster ; charged=%s target=%s"
        % (d["with"]["charged"], d["target"]))
    assert len(d["with"]["per_hit"]) == 1, (
        "ADJACENT : le port sur-applique le +extraHit (gate `has_moved` ?) -- n=%d %s"
        % (len(d["with"]["per_hit"]), d["with"]["per_hit"]))
    assert d["with"]["total"] == d["obs"]["target_delta"], (
        "ADJACENT : live delta=%s, offline n=%d %s total=%s"
        % (d["obs"]["target_delta"], len(d["with"]["per_hit"]), d["with"]["per_hit"],
           d["with"]["total"]))


def test_step_adjacent_is_moved_but_not_charging(adjacent):
    """REGIME `STEP_ADJACENT` -- le SEUL qui separe `IsCharging` de `HasFlag(UnitFlag.Moved)`.

    POURQUOI IL EST CONSTRUIT OFFLINE SUR UN ETAT LIVE, et pas observe : le caster est un SUMMON,
    donc c'est l'IA qui joue son activation, et elle ATTAQUE SANS BOUGER quand elle est deja au
    contact (mesure : `caster_moved=None` sur le regime `ADJACENT`). Le pas de MONTAGE, lui, a lieu
    au tour PRECEDENT -- et `StartTurnOperation$$ResetUnit` purge le flag `Moved` a l'entree du tour,
    si bien qu'au moment de l'attaque le natif a `Moved` FAUX : la situation « a bouge mais n'a pas
    charge » n'existe simplement PAS dans une activation pilotee par l'IA.

    On la fabrique donc a partir du snapshot LIVE du regime `ADJACENT` (caster reellement au contact,
    effet 1032 reellement porte, `ChargedUnitIds` reellement vide) en rejouant un pas
    ADJACENT -> ADJACENT par le MOTEUR (`MoveUnitMessage`, donc `update_charging` + `set_moved_flag`
    poses par le moteur, jamais declares) :

        `Moved` = VRAI  et  `IsCharging(caster, target)` = FAUX

    Un port gate par le proxy `has_moved` rendrait 2 coups ici ; le port correct en rend 1.
    C'est CETTE assertion que la mutation adversariale du gate fait tomber."""
    import hexgeo
    from engine.runner.components import unit_has_moved

    d = adjacent
    h, board = d["h"], d["board"]
    tp = d["plan"]["target_pos"]
    cp = d["plan"]["caster_pos"]
    # une AUTRE tuile encore adjacente a la MEME cible, a un hex du caster
    cands = [c for c in h.free_tiles(tp, 1, exclude=(d["caster"], d["target"]))
             if c != cp and hexgeo.distance(c, cp) == 1]
    if not cands:
        pytest.skip("aucune tuile adjacente alternative a un hex du caster")
    step_to = cands[0]
    o = replay_attack_offline(d["snap"], board, d["caster"], d["target"], move_to=step_to)
    assert unit_has_moved(o["state"], d["caster"]) is True, (
        "le pas n'a pas pose le flag `Moved` -- le regime ne separe alors plus rien")
    assert d["target"] not in o["charged"], (
        "la cible etait DEJA adjacente avant le pas : `UpdateCharging` ne doit PAS l'ajouter ; "
        "charged=%s target=%s" % (o["charged"], d["target"]))
    assert len(o["per_hit"]) == 1, (
        "STEP_ADJACENT : le port sur-applique le +extraHit (gate `has_moved` ?) -- "
        "caster deplace de %s vers %s (cible en %s, deja adjacente), attendu n=1, obtenu n=%d %s"
        % (cp, step_to, tp, len(o["per_hit"]), o["per_hit"]))


def test_charge_beats_adjacent_live(charge, adjacent):
    """Le NATIF separe bien les deux regimes -- sinon les tests ci-dessus passeraient pour une
    raison triviale (aucun bonus nulle part). On compare deux mesures LIVE, pas le port."""
    assert charge["obs"]["target_delta"] > adjacent["obs"]["target_delta"], (
        "le natif doit infliger PLUS en charge qu'en simple adjacence -- CHARGE=%s, ADJACENT=%s"
        % (charge["obs"]["target_delta"], adjacent["obs"]["target_delta"]))


# ------------------------------------------------------------------------------- generalisation #

def test_charge_other_board(charge_alt):
    """GENERALISATION du cas rouge : autre board (`C1_25`), autre seed (31337), autres cibles."""
    d = charge_alt
    assert d["obs"]["caster_moved"], "l'IA n'a pas deplace le summon"
    assert d["target"] in d["with"]["charged"]
    assert d["with"]["total"] == d["obs"]["target_delta"], (
        "CHARGE (C1_25/31337) : live delta=%s, off+1032 n=%d %s total=%s, off-1032 total=%s"
        % (d["obs"]["target_delta"], len(d["with"]["per_hit"]), d["with"]["per_hit"],
           d["with"]["total"], d["without"]["total"]))
    assert d["without"]["total"] != d["obs"]["target_delta"], (
        "borne SANS effet non discriminante (live=%s, off-1032=%s)"
        % (d["obs"]["target_delta"], d["without"]["total"]))
