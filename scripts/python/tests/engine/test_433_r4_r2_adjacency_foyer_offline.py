"""GARDES #433-r4-r2 -- les deux consommateurs qui tranchaient l'adjacence HORS du foyer mirror.

CE QUE CES GARDES PROTEGENT :

1. **`EarlyWarningOverridePlaybook` doit passer par `are_entities_adjacent`** (le mirror de
   `IdunBattle.Core.Services.MovementUtil$$AreTilesAdjacent`), pas par une distance hex nue.
   Le natif tranche `adj = TileExtensions.IsAdjacentTo(GetMainTile(caster), GetTiles(otherUnit))`
   -- surcharge `(tile, otherTiles)`, un `exists` dont chaque paire passe par la primitive
   SCALAIRE `(|dElev| < 2) & (t1 == t2 || IsNeighbour)`. Ce booleen choisit la BRANCHE de
   l'utilite, donc l'oublier ne casse rien : ca fait juste evaluer l'autre branche, en silence.

2. **`MasterOfTheTutelariesPlaybook._nearest_enemy_tile` doit passer par le MEME foyer.** Son
   natif, `IdunBattle.Core.Services.BattleQuery$$GetNearestEnemy`, appelle
   `$$AreEntitiesAdjacent` DIRECTEMENT -- et non `$$AreUnitsInMelee` (passe-plat d'une ligne vers
   la meme fonction), et surtout pas `TileQuery$$IterateAdjacentTiles`, dont `is_adjacent` est le
   mirror. L'ecart observable du re-pointage est NUL (le seul terme qui separe les deux foyers est
   le court-circuit d'identite, inatteignable entre deux unites VIVANTES distinctes) : ces gardes
   verrouillent donc le FOYER, pas une valeur.

3. **`is_adjacent` ne doit PAS etre aligne.** #433-r1 §4 en fait un contre-exemple explicite :
   l'aligner ferait compter chaque unite comme sa propre voisine, et gonflerait silencieusement
   toutes les utilites de voisinage. Une garde le fixe dans les deux sens.

Detail et mesures live : `docs/rl/case-433-r4-r2-consommateurs-hors-foyer.md`. ASCII only.
"""
from __future__ import annotations

import dataclasses

import pytest

import hexgeo
from counterproof import assert_channel_counterproof_ctx
from engine import battle_query as bq
from engine.playbook.noncomparable._base import NCContext
from engine.playbook.noncomparable.early_warning_override import (EarlyWarningOverridePlaybook,
                                                                  _ranged_weapon_threshold)
from engine.services import ability_range
from engine.playbook.noncomparable.master_of_the_tutelaries import MasterOfTheTutelariesPlaybook

ABILITY = 1077
RANGED = "tauMarksman"          # arme a distance de portee 3 : branche A et branche B DIFFERENT
O = (3, 2)


def _neighbours(p):
    return list(hexgeo.neighbors(p[0], p[1]))


def _ctx(origin, enemies_pos, elev, reach=(), visual=RANGED, uid=79):
    """`NCContext` minimal : ce que les deux consommateurs lisent reellement."""
    return NCContext(
        uid=uid, origin=origin, reach_nc=list(reach),
        epos=[tuple(p) for p in enemies_pos],
        fpos=[], plan={}, hp_cur_by_id={},
        enemies=[{"id": 900 + i, "visualId": visual, "pos": {"col": p[0], "row": p[1]}}
                 for i, p in enumerate(enemies_pos)],
        elev_by_pos=dict(elev),
        ability_targets=lambda u, a: {"units": [{"unitId": uid, "abilities": [
            {"abilityId": a, "targets": [{"kind": "unit", "targetId": uid}]}]}]})


# --------------------------------------------------------------------------- 1. EarlyWarning

def test_early_warning_partition_follows_the_elevation_gate():
    """La bascule de branche suit `|dElev| < 2`, et elle bascule DANS LES DEUX SENS.

    Voisin PLAT -> branche B (le natif le declare adjacent) ; voisin a `|dElev| >= 2` -> branche A.
    La NON-REGRESSION est aussi importante que le fix : un faux negatif d'adjacence supprimerait
    des actions legales."""
    pb = EarlyWarningOverridePlaybook()
    nb = _neighbours(O)
    flat, high = nb[0], nb[1]
    elev = {O: 2, flat: 2, high: 4}
    for pos, expected, label in ((flat, True, "voisin PLAT"), (high, False, "voisin |dElev|=2")):
        ctx = _ctx(O, [pos], elev)
        got = pos in pb.adjacent_at_origin(ctx, pb.enemies_of(ctx))
        assert got is expected, "%s %s : adjacent=%s attendu %s" % (label, pos, got, expected)


def test_early_warning_keeps_the_identity_short_circuit():
    """`AreTilesAdjacent` rend VRAI sur `t1 == t2` (et `|dElev| = 0 < 2` ne peut pas le
    contredire). Regime inatteignable en bataille -- deux unites vivantes ne partagent pas une
    tuile -- mais mirrore par FIDELITE, comme partout ailleurs sur cette primitive."""
    pb = EarlyWarningOverridePlaybook()
    ctx = _ctx(O, [O], {O: 2})
    assert O in pb.adjacent_at_origin(ctx, pb.enemies_of(ctx))


def test_early_warning_without_the_channel_degrades_to_bare_distance():
    """Canal absent -> borne SUPERIEURE (distance hex nue), jamais une adjacence retiree a
    l'aveugle. C'est exactement l'etat d'AVANT le fix, et c'est ce que la contre-epreuve live
    utilise comme second bras.

    #433-r4-r2-r4-r1 : l'ATTRIBUTION passe d'abord. Si un jour `elev_by_pos` cesse d'etre le seul
    canal a porter cette exclusion, c'est `InertCounterproof` qui parle -- pas un rouge qui accuse
    le port, comme le 2026-08-04."""
    pb = EarlyWarningOverridePlaybook()
    nb = _neighbours(O)
    high = nb[1]
    ctx = _ctx(O, [high], {O: 2, high: 4})
    assert_channel_counterproof_ctx(
        lambda c: frozenset(pb.adjacent_at_origin(c, pb.enemies_of(c))), ctx, "elev_by_pos")
    assert high not in pb.adjacent_at_origin(ctx, pb.enemies_of(ctx))
    for degraded in (None, {}):
        ctx2 = dataclasses.replace(ctx, elev_by_pos=degraded)
        assert high in pb.adjacent_at_origin(ctx2, pb.enemies_of(ctx2)), \
            "canal %r : le port doit retomber sur la distance hex nue" % (degraded,)


def test_early_warning_non_neighbour_is_never_in_branch_B():
    pb = EarlyWarningOverridePlaybook()
    far = (O[0] + 3, O[1])
    ctx = _ctx(O, [far], {O: 2, far: 2})
    assert pb.adjacent_at_origin(ctx, pb.enemies_of(ctx)) == set()


def test_early_warning_two_branches_are_the_native_predicates():
    """`utility_at` mirror : branche A `+50 si NON IsTileInRangeOfAnyAbility(E, P)`, branche B
    `+50 si threshold(E) < d`, puis `-10 * d` dans les deux cas. Les DEUX branches, MEME ennemi.

    Sur `tauMarksman` les deux seuils DIFFERENT (#433-r4-r2-r1 + -r2, fermes ensemble) : la zone
    d'ability porte a 5 (`SeekerMissileFrequencyLock`, `constants.range = 5`), l'arme a distance
    a 3. C'est ce qui rend le partage A/B observable dans le PORT."""
    pb = EarlyWarningOverridePlaybook()
    E = (0, 0)
    # Les deux derniers termes sont l'etat d'abilities de l'ennemi et l'id de son attaque normale
    # (#433-r4-r2-r1-r1-c) : vides ici, donc AUCUN gate CASTER ne mord et les seuils sont ceux que
    # ce test etalonnait deja. `enemies_of` les remplit depuis `decisionView`.
    enemies = [(E, RANGED, _ranged_weapon_threshold(RANGED), {}, None)]
    reach = ability_range.unit_threat_reach(RANGED)
    assert (reach, enemies[0][2]) == (5, 3), \
        "les deux seuils doivent DIFFERER, sinon le partage A/B est indiscernable dans le port"
    for d, P in ((1, (1, 0)), (2, (2, 0)), (4, (4, 0)), (6, (6, 0))):
        assert hexgeo.distance(P, E) == d, "geometrie du test cassee"
        assert pb.utility_at(P, enemies, set()) == (50.0 if d > reach else 0.0) - 10.0 * d
        assert pb.utility_at(P, enemies, {E}) == (50.0 if d > 3 else 0.0) - 10.0 * d


def test_early_warning_emitted_action_changes_with_the_gate():
    """Bout en bout : la porte change l'action EMISE, pas seulement un booleen interne.

    RE-ETALONNE par #433-r4-r2-r1/-r2 (les DEUX seuils ont change, donc les deux verdicts) :
      * SANS canal -> tous adjacents -> branche B, `threshold = FindRangedWeapon.Range = 3` :
        la 1re position qui verse `+50` est `d = 4`, d'ou `50 - 40 = 10` (et non plus `d = 2`,
        `30`, qui supposait le `threshold` fige a 1) ;
      * AVEC canal -> `|dElev| = 2` -> branche A, zone d'ability de portee 5 : AUCUNE position du
        sweep (`d <= 4`) n'est hors portee, donc aucun `+50`, l'utilite reste NEGATIVE.

    ⚠ **RE-ETALONNE UNE SECONDE FOIS par `#433-r4-r2-r3`, ET LA PREMISSE PRECEDENTE ETAIT FAUSSE.**
    Ce test attendait `on == []` -- << l'utilite reste NEGATIVE et `MIN_UTILITY` la rejette >>. Or
    `EarlyWarningOverridePlaybook` n'a AUCUNE borne : son `Bucket` est construit par la surcharge a
    DEUX arguments de `Bucket<T>$$.ctor` (donc `minUtility.HasValue == false`, et `AddAction`
    accepte TOUT), et la classe ne declare que trois methodes -- personne ne lit le `Fix64(1)` de
    son `.cctor`. Le natif EMET donc l'action a utilite negative, ce que `ncEvaluate` mesurait deja
    (`best` negatif a chaque position du sweep) sans que le port le reproduise.

    Ce que ce test garde reste EXACTEMENT le meme : la porte d'elevation BASCULE le consommateur
    d'une branche a l'autre, et cela se lit sur l'action EMISE. Le discriminant `on != off` est
    inchange ; seule la valeur attendue du bras `on` passe de << rien >> a << l'action a l'utilite
    de la branche A >>. C'est la difference entre un test qui garde une MECANIQUE et un test qui a
    fige un SEUIL faux."""
    pb = EarlyWarningOverridePlaybook()
    nb = _neighbours(O)
    high = nb[1]
    # sweep explicite : une tuile a chaque distance 2..4 de l'ennemi, derivee par hexgeo
    ring = {}
    for col in range(O[0] - 5, O[0] + 6):
        for row in range(O[1] - 5, O[1] + 6):
            ring.setdefault(hexgeo.distance((col, row), high), (col, row))
    reach = [O] + [ring[d] for d in (2, 3, 4) if d in ring]
    elev = {O: 2, high: 4}
    ctx = _ctx(O, [high], elev, reach=reach)
    # #433-r4-r2-r4-r1 : ATTRIBUER avant d'assertionner. `on != off` ci-dessous ne sait pas dire
    # POURQUOI les deux bras coincident ; le helper, si (canal concurrent vs etat hors regime).
    assert_channel_counterproof_ctx(pb.generate_candidates, ctx, "elev_by_pos")
    ctx_off = dataclasses.replace(ctx, elev_by_pos=None)
    on = pb.generate_candidates(ctx)
    off = pb.generate_candidates(ctx_off)
    assert on != off, "la porte n'a aucun effet sur l'action emise -- montage a re-etalonner"
    assert off and off[0]["pred"] == 10.0, \
        "branche B attendue SANS canal (threshold 3 -> 50 - 10*4 = 10), obtenu %r" % (off,)
    # Branche A AVEC canal : la zone d'ability porte a 5, aucune position du sweep (`d <= 4`) n'est
    # hors portee -> aucun `+50`, l'utilite est PUREMENT le terme de distance. L'action est EMISE
    # quand meme -- ce playbook n'a aucune borne d'utilite (`#433-r4-r2-r3`, cf. la docstring).
    assert on and on[0]["pred"] < 0.0, \
        "branche A attendue AVEC canal (aucun +50 sur d <= 4 -> utilite NEGATIVE emise), obtenu %r" % (on,)
    assert on[0]["pred"] == -10.0 * min(hexgeo.distance(P, high) for P in reach), \
        ("l'utilite de la branche A doit etre `-10 x d` a la MEILLEURE position du sweep, "
         "obtenu %r" % (on,))


# --------------------------------------------------------------------------- 2. Tutelaries

def test_tutelaries_nearest_enemy_uses_the_are_entities_adjacent_foyer(monkeypatch):
    """GARDE DE FOYER. `GetNearestEnemy` appelle `AreEntitiesAdjacent`, pas `IterateAdjacentTiles`.
    L'ecart observable etant nul (cf. le test suivant), c'est le SEUL moyen de verrouiller le
    re-pointage : on compte les appels."""
    calls = {"are": 0, "is": 0}
    real_are, real_is = bq.are_entities_adjacent, bq.is_adjacent

    # Signature TRANSPARENTE (`*a`) : ce cran compte des APPELS, il ne fige pas l'arite du foyer.
    # Une signature recopiee a la main faisait rougir ce test des que le foyer gagnait un canal
    # (#433-r4-r1-r4-r2 : `neigh_by_pos`) -- un faux rouge qui accuse le MONTAGE, pas le port.
    def spy_are(*a, **kw):
        calls["are"] += 1
        return real_are(*a, **kw)

    def spy_is(*a, **kw):
        calls["is"] += 1
        return real_is(*a, **kw)

    monkeypatch.setattr(bq, "are_entities_adjacent", spy_are)
    monkeypatch.setattr(bq, "is_adjacent", spy_is)
    pb = MasterOfTheTutelariesPlaybook()
    nb = _neighbours(O)
    ctx = _ctx(O, [nb[0], (O[0] + 4, O[1])], {O: 2, nb[0]: 2})
    pb._nearest_enemy_tile(ctx)
    assert calls["are"] == 2, \
        "le terme melee doit passer par `are_entities_adjacent` (%r)" % (calls,)


def test_tutelaries_melee_priority_respects_the_elevation_gate():
    """La priorite MELEE de `GetNearestEnemy` (`adj && !bestAdj`) supplante la distance -- mais un
    ennemi a hex-distance 1 separe de `|dElev| >= 2` n'est PAS adjacent, donc pas prioritaire."""
    pb = MasterOfTheTutelariesPlaybook()
    nb = _neighbours(O)
    near, far = nb[0], (O[0] + 3, O[1])
    # `far` enumere en PREMIER : seule la priorite melee peut faire gagner `near` a egalite d'ordre
    ctx_flat = _ctx(O, [far, near], {O: 2, near: 2, far: 2})
    ctx_step = _ctx(O, [far, near], {O: 2, near: 4, far: 2})
    assert pb._nearest_enemy_tile(ctx_flat) == near, "voisin PLAT : le plus proche gagne"
    assert pb._nearest_enemy_tile(ctx_step) == near, \
        "a distance 1 il reste le plus PROCHE : la porte ne doit pas lui retirer ca"
    # la porte ne se lit que sur le drapeau melee, pas sur la distance : on l'isole en mettant les
    # deux ennemis a la MEME distance, ou seul `adj` peut departager
    same = [q for q in _neighbours(O) if q != near][0]
    ctx_a = _ctx(O, [same, near], {O: 2, near: 2, same: 4})
    assert pb._nearest_enemy_tile(ctx_a) == near, \
        "a distance egale, l'ennemi ADJACENT (porte passee) doit supplanter celui a |dElev| >= 2"


def test_tutelaries_repointing_is_inert_on_distinct_tiles():
    """L'ecart observable du re-pointage est NUL par COMPOSITION : les deux foyers ne different que
    par le court-circuit d'identite, et `ctx.epos` ne porte que des ennemis VIVANTS
    (`engine.ai.context._enemies` filtre `alive`), donc jamais la tuile du caster.

    Ce test le PROUVE plutot que de l'affirmer : sur toutes les paires distinctes d'un voisinage
    a relief, les deux primitives rendent le meme verdict."""
    elev = {}
    pts = []
    for col in range(0, 5):
        for row in range(0, 5):
            pts.append((col, row))
            elev[(col, row)] = (col + 2 * row) % 5      # relief dense : des |dElev| >= 2 partout
    n_diff = 0
    for a in pts:
        for b in pts:
            if a == b:
                continue
            if bq.is_adjacent(a, b, elev) != bq.are_entities_adjacent(a, b, elev):
                n_diff += 1
    assert n_diff == 0, "%d paires DISTINCTES separent les deux foyers" % n_diff


def test_is_adjacent_stays_the_counter_example():
    """#433-r1 §4 : `is_adjacent` mirrore `IterateAdjacentTiles`, qui ne rend JAMAIS la tuile
    source. L'aligner « par coherence » ferait compter chaque unite comme sa propre voisine."""
    p = (2, 2)
    assert bq.is_adjacent(p, p, {p: 3}) is False
    assert bq.are_entities_adjacent(p, p, {p: 3}) is True


def test_both_consumers_reject_the_bare_hex_distance():
    """GARDE ANTI-RETOUR. Si un jour l'un des deux revenait a `hexgeo.distance == 1`, la porte
    d'elevation redeviendrait muette : on le detecte en NEUTRALISANT le foyer et en verifiant que
    les deux consommateurs changent de verdict."""
    pb_ew = EarlyWarningOverridePlaybook()
    pb_mt = MasterOfTheTutelariesPlaybook()
    nb = _neighbours(O)
    high = nb[1]
    elev = {O: 2, high: 4}
    ctx = _ctx(O, [high], elev)
    assert_channel_counterproof_ctx(
        lambda c: frozenset(pb_ew.adjacent_at_origin(c, pb_ew.enemies_of(c))), ctx, "elev_by_pos",
        remede="ce test NEUTRALISE le foyer pour verifier que les deux consommateurs le lisent ; "
               "si un second canal porte la meme exclusion, neutraliser celui-ci ne prouve plus "
               "rien -- couper les DEUX, ou muter le foyer lui-meme")
    assert pb_ew.adjacent_at_origin(ctx, pb_ew.enemies_of(ctx)) == set()
    assert pb_mt._nearest_enemy_tile(ctx) == high      # seul ennemi : il gagne par distance
    ctx_bare = dataclasses.replace(ctx, elev_by_pos=None)
    assert pb_ew.adjacent_at_origin(ctx_bare, pb_ew.enemies_of(ctx_bare)) == {high}, \
        "sans canal le port doit retomber sur la distance nue -- sinon la contre-epreuve est vide"


@pytest.mark.parametrize("d_elev,expected", [(0, True), (1, True), (2, False), (3, False)])
def test_the_gate_threshold_is_strictly_two(d_elev, expected):
    """`|dElev| < 2` : `1` passe, `2` ne passe pas. Le seuil, pas une inegalite approchee."""
    a, b = O, _neighbours(O)[0]
    assert bq.are_entities_adjacent(a, b, {a: 2, b: 2 + d_elev}) is expected
