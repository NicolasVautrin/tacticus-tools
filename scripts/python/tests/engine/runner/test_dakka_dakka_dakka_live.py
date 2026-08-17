"""DakkaDakkaDakka (1171, `orksKillaKan` << Snappawrecka >>, Orks) -- FACE COMBAT, confront LIVE.

CE QUE CE FICHIER FERME : le gisement `[-D]` (la face DECISION etait portee -- l'IA PREDIT
`nrOfHits` coups via `_SPECIAL_ABILITY_CLASSES` et CHOISIT l'ability -- pendant que la face COMBAT
etait un NO-OP silencieux : `AbilityHandler.visit_ActiveAbilityMessage` ne trouvait pas la classe,
posait `unported`, executait quand meme les flags de tour, et ne mutait RIEN).

`IdunBattleLogic.Entities.Abilities.Active.Loki.DakkaDakkaDakkaAbility$$ExecuteBehaviour` (DECOMPILE,
mirror 1:1 -- l'arbre complet est en tete de section dans `engine/runner/abilities/orks.py`) :

    main     = AttackWithAttackDamage(caster, target, MinMaxDamage, profile, GetNumHits())
    numLeft  = Cache(NumLeftOverHits(target, AbilityOrEffect(+0x10)))
    picked   = Cache(PickRandomly(PossibleLeftoverHitsTargets(),
                                  RandomAmount(1, Min(numLeft, Count(possible)))))
    hitsPer  = If(AreEqual(First(picked), It@0x180), Sum(q, rem), q)   q = Divide(numLeft, cnt, Floor)
    leftAtk  = AttackWithAttackDamage(caster, picked, MEME damage/profil, hitsPer)
    selfLoss = ChangeStat(caster, Health, Subtract,
                          PercentageOf(StatAmount(caster, Health, MAXIMUM=2), ConfigConst(healthPct)))
    Execute(op_and(op_and(main, If(numLeft, leftAtk, null)), If(IsAlive(caster), selfLoss, null)))

i2 : << Deals 6x [dmg] Projectile Damage to an enemy within range 3. Adds +2 hits for each time
Snappawrecka was repaired this battle, but cannot exceed 16 hits in total. If the target is defeated,
leftover hits are allocated to random enemies within 3 hexes. Snappawrecka also loses 15% of his
maximum Health. >>

LES QUATRE CAS, et pourquoi ILS SONT DISCRIMINANTS (aucun ne rend le meme observable, donc aucun
scalaire fitte ne peut passer les quatre) :

  (A) CIBLE QUI SURVIT -> le cast frappe UNE unite, `numLeft == 0`, AUCUN volet leftover.
      Per-coup LIVE == per-coup OFFLINE, coup par coup, sur le meme MT.
  (B) SELF-LOSS -> le caster perd `round_half_even(maxHP * healthPct / 100)` PV. Assertion contre le
      PV **MAXIMUM** (pas le courant) : c'est le seul point ou `StatPart.MAXIMUM` (2) se distingue de
      `StatPart.CURRENT` (0), et il se voit des que le caster n'est pas a pleine vie -> le cas 2 du
      test le monte EXPRES (caster blesse), sinon les deux lectures coincideraient.
  (C) CIBLE TUEE -> `numLeft > 0` et le volet leftover frappe d'AUTRES unites. Cardinal et
      identite des cibles LIVE == OFFLINE (c'est le canal `RandomAmount` + `PickRandomly`, donc
      aussi la preuve que la CONSOMMATION RNG du port est calee).
  (D) GARDE ROUGE (mutation adversariale) -- le MEME snapshot rejoue avec 1171 RETIRE de
      `ABILITY_CLASSES` : zero degat, zero self-loss, `ported=False`. C'est l'etat d'AVANT ce port.
      Le test PROUVE dans le meme souffle que le montage n'est pas rate (piege mesure 4x : un
      `applyAction` peut rendre `ok=True` sans rien muter) : le MEME cast, MEME snapshot, avec le
      registre intact, MUTE. Un montage rate rendrait 0 des DEUX cotes.

Drive les positions des DEUX camps (`applyAction` ignore la propriete). Montage via la fixture NOMMEE
`ability_cast_harness` (`_ability_cast_replay.py`). Aucune tuile/RVA hardcodee. ASCII only.
"""
from __future__ import annotations

import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(__file__))      # helpers siblings
from _ability_cast_replay import ability_cast_harness   # noqa: E402,F401  (fixture)

import hexgeo                                            # noqa: E402
import gameconfig as GC                                  # noqa: E402
from engine.runner.runner import Runner                  # noqa: E402
from engine.runner.messages import ActiveAbilityMessage  # noqa: E402
from engine.runner.components import (HealthComponent, PositionComponent,   # noqa: E402
                                      UnitComponent)
from engine.runner.abilities import handler as HANDLER   # noqa: E402

SNAPPA = "orksKillaKan"
ABILITY = 1171
# Cibles VANILLA (`python unit_map.py vanilla-target` : aucun trait/ability qui modifie ou reduit le
# degat). Deux rosters ont ete ECARTES par la mesure, et pour des raisons DIFFERENTES :
#   * `orksNob` (`BeastSlayer_ExtraDmg`/`ExtraBlock`) + `tyranTyrantGuard` (`BigTarget_AdjacentEffect`,
#     `CrushingStrike`) : modificateurs de degat etrangers a ce qu'on mesure ;
#   * `astraCreed` : son `SwornProtector` fait APPARAITRE Kell pendant la cascade et REMPLACE la cible
#     (`ActiveAbilityOperation$$ExecuteForReplacedTarget`) -> 86 evenements, aucun coup attribue a
#     u77 (mesure `probe_ddd_1171_cast.py --a-units astraCreed,...`). Excellent stress-test du
#     chemin #120bis, mauvais banc pour mesurer le canal de degat.
ENEMIES = "eldarFarseer,tauAunShi,ultraApothecary"
# Confonds neutralises au build : `--crit 0,0` et `--block-target 0,0` retirent les tirages de
# crit/block (le flux MT reste celui des seuls degats), `--hp-target` regle la SURVIE de la cible.
NO_NOISE = ["--crit", "0,0", "--block-target", "0,0"]
BUILD_TANKY = NO_NOISE + ["--hp-target", "500000"]     # (A)/(B)/(D) : la cible SURVIT -> numLeft = 0
BUILD_FRAGILE = NO_NOISE + ["--hp-target", "600"]      # (C) : la cible MEURT -> volet leftover

# CONFOND MESURE, et c'est le seul du montage : Snappawrecka porte le trait `GetStuckIn` -- << For
# every 2 hits this unit scores with an attack against an enemy **within range 2**, it has a
# {chance}% chance to score an additional hit >>. Ce trait tire un `Maybe(chance)` TOUS LES 2 COUPS,
# donc DANS le flux MT de l'ability, et il est EXTERIEUR a `DakkaDakkaDakkaAbility$$ExecuteBehaviour`.
# Depuis la PR #177 (`EvaluateAfterHitTriggers` est inconditionnel et vaut pour les DEUX familles de
# factory), ce canal `On(8)` est CABLE cote port sur le vecteur ABILITY -- il roule donc pendant ce
# cast, exactement comme le natif.
#
# LES DEUX GATES COINCIDENT DESORMAIS PARTOUT, et le montage n'a plus a se placer nulle part :
#   * gate NATIF  = `GetStuckInAbility$$CreateTrigger` -> `!(MinDistance > 2)`, une distance **HEX**
#     (`IdunBattleLogic.Entities.DSLFormulas$$MinDistance` -> `MinDistanceFormula$$Calculate` -> `PositionComponent$$Distance`
#     = `AxialCoordinate$$ToCubeCoordinate` x2 + `CubeCoordinate$$Distance`) ;
#   * gate PORTE  = `damage_model.getstuckin_combat_chance` et son jumeau PREDICTION
#     `GetStuckInTrait.as_attacker_bonus_hits`, tous deux sur `entities.traits.combat.min_distance`
#     = `hexgeo.distance` -- **le meme mirror sur les deux faces**.
#
# HISTORIQUE DE LA MESURE QUI A FERME LE GAP (`probe_ddd_1171_getstuckin.py`, 3 regimes). Le port
# mesurait alors en CHEBYSHEV sur (col, row), qui SOUS-ESTIME toujours la distance hex :
#
#   dist demandee | caster  cible  | hex | cheby | gate porte | gate natif | prefixe commun
#   ------------- | ------  -----  | --- | ----- | ---------- | ---------- | --------------
#   2             | (1,0)   (0,1)  |  2  |   1   | ACTIF (30) | ACTIF      | **6 / 6**
#   3             | (1,0)   (0,2)  |  3  |   2   | ACTIF (30) | INACTIF    | 2 / 6      <- divergeait
#   4             | (1,0)   (0,3)  |  4  |   3   | INACTIF    | INACTIF    | (hors portee)
#
# La ligne « dist 3 » est desormais VERTE (`test_min_distance_metric_live.py` la garde sur son propre
# axe, avec un temoin), d'ou les DEUX distances ci-dessous plutot qu'une seule :
#   * 2 -> les deux gates ACTIFS : exerce EN PLUS le canal after-hit cable par #177 ;
#   * 3 -> les deux gates INACTIFS : c'est EXACTEMENT la bande qui divergeait, et la seule ou une
#          regression de metrique se verrait. La garder ici est ce qui empeche le gap de revenir
#          par le montage qui l'avait revele.
GETSTUCKIN_DISTS = (2, 3)
GETSTUCKIN_AGREED_DIST = GETSTUCKIN_DISTS[0]   # cas B/C/D : la distance n'y est pas le sujet


def _cfg(key):
    """Constante de la config 1171 -- ORACLE, jamais un litteral ecrit dans le test."""
    return int(((GC.ability("DakkaDakkaDakka") or {}).get("constants") or {}).get(key))


def _hp(state, uid):
    e = state.get_entity(uid)
    hc = e.get_component(HealthComponent) if e is not None else None
    return (hc.hp, hc.hp_max) if hc is not None else (None, None)


def _alive(state, uid):
    e = state.get_entity(uid)
    uc = e.get_component(UnitComponent) if e is not None else None
    return bool(uc is not None and uc.alive)


def _offline_cast(state, caster, target):
    """Rejoue le cast par le VRAI point d'entree (`Runner.apply` -> `AbilityHandler`), donc a travers
    les gates de ciblage et les vecteurs d'operation -- pas par un appel direct a
    `execute_behaviour`."""
    runner = Runner(state).install_default_handlers(20)
    runner.apply(ActiveAbilityMessage(caster_id=caster, target_id=target, ability_type=ABILITY))
    return runner.ability_handler.last or {}


def _setup(h, target_dist, move_others=False):
    """Monte la geometrie du cast avec **UN SEUL `move`**, et c'est le point important.

    * `move_others=False` (cas A/B/D) : on rapproche la CIBLE a distance hex EXACTEMENT
      `target_dist` du caster, qui ne bouge pas. Le pool leftover reste vide (les autres ennemis
      sont loin), ce qui est exactement ce que ces cas veulent.
    * `move_others=True` (cas C) : on deplace le CASTER a `target_dist` de la cible **et** a portee
      `range_2` d'au moins un AUTRE ennemi -- les ennemis restent groupes comme au spawn, donc le
      pool du volet leftover est peuple SANS avoir a les bouger un par un.

    Pourquoi UN SEUL `move` : chaque `move` consomme l'activation de l'unite deplacee ; des que
    TOUTES les unites d'un camp ont agi, le tour BASCULE, et un cast tente ensuite est refuse EN
    SILENCE (`ok=True`, aucune mutation -- signature #111). Bouger les trois ennemis, c'est
    precisement declencher ce basculement : mesure faite, le cas C skippait sur
    << cast live NON MUTANT >>.

    Rend `(snappa_id, target_id, [autres ids])` ou None."""
    dv = h.dview()
    snappa = h.by_visual(SNAPPA, dv)
    if snappa is None:
        return None
    h.my_player = snappa.get("owner")
    ens = h.enemies_of(h.my_player, dv)
    if not ens:
        return None
    rng2 = _cfg("range_2")
    C = (snappa["pos"]["col"], snappa["pos"]["row"])
    target_id = ens[0]["id"]
    others = [e["id"] for e in ens[1:]]

    slots = h.free_neighbours(C, target_dist, exclude=[u["id"] for u in h.alive()])
    if not slots or not h.place(target_id, slots[0]):
        return None
    placed = [slots[0]]
    if move_others:
        # Cas (C) : peupler le POOL du volet leftover avec **UN SEUL** autre ennemi -- deux `move`
        # adverses sur trois, donc la 3e unite garde son activation et le tour NE BASCULE PAS
        # (bouger les trois faisait skipper le cas sur << cast live NON MUTANT >>).
        #
        # CONTRAINTE OBLIGATOIRE, mesuree : cet ennemi ne doit PAS etre adjacent au caster. Le masque
        # de 1171 porte `forceMeleeTarget = True` -> `TargetingQuery$$GetRange` fait
        # `if (ForceMeleeTarget && ShouldApplyRangedInMelee(caster)) { v = Min(1, v); }` : un caster
        # ranged AU CONTACT voit sa portee ramenee a **1**, et la cible a distance 2 sort de portee
        # -> cast refuse EN SILENCE.
        dest = None
        for r in range(2, rng2 + 1):               # >= 2 : jamais au contact du caster
            free = [c for c in h.free_neighbours(C, r, exclude=[u["id"] for u in h.alive()])
                    if c not in placed]
            if free:
                dest = free[0]
                break
        if dest is None or not h.place(others[0], dest):
            return None
        placed.append(dest)
    dv = h.reach_my_turn()                         # tour NEUF pour le caster (cf. `place`)
    if dv is None or snappa["id"] not in (dv.get("toActivate") or []):
        # Le caster n'a plus d'activation ce tour-la (les `move` en ont consomme) -> tout cast serait
        # refuse EN SILENCE. On le dit ICI plutot que de l'attribuer au port plus tard.
        return None
    return snappa["id"], target_id, others


def _live_damage(live, uid):
    return list(live["damage_by_target"].get(uid) or [])


def _assert_live_mutated(live):
    """PIEGE DE HARNAIS (mesure 4x) : `applyAction` peut rendre `ok=True` SANS rien muter (unite pas
    dans `toActivate`, pas son tour, un `move` a fait basculer le joueur courant...). La signature
    est IDENTIQUE a celle du no-op qu'on veut mesurer -> on exige `mutated` avant de conclure quoi
    que ce soit sur le port. Skip (montage), jamais fail (ce n'est pas le port qui est en cause)."""
    a0 = ((live.get("raw") or {}).get("actions") or [{}])[0]
    if not a0.get("mutated"):
        pytest.skip("cast live NON MUTANT (montage) : ok=%s events=%d -- ce n'est PAS le no-op mesure"
                    % (a0.get("ok"), len(a0.get("events") or [])))


# ------------------------------------------------------------------ (A) volee principale

@pytest.mark.parametrize("target_dist", GETSTUCKIN_DISTS)
def test_dakka_main_volley_live_equals_offline(ability_cast_harness, target_dist):
    """(A) La cible SURVIT -> `numLeft == 0`, aucun volet leftover, et le per-coup OFFLINE est
    IDENTIQUE au per-coup LIVE, coup par coup. Le nombre de coups est confronte a
    `constants.nrOfHits` (oracle config) : `GetNumHits` = `Min(nrOfHits + TimesRepaired*extraHits,
    maxNrOfHits)` et `TimesRepaired` vaut 0 au cast.

    Joue aux DEUX distances de `GETSTUCKIN_DISTS` : a 2 le gate `GetStuckIn` est ACTIF des deux
    cotes (le canal after-hit de #177 est exerce), a 3 il est INACTIF des deux cotes -- et c'est
    la bande ou le port divergeait tant qu'il mesurait en Chebyshev."""
    h = ability_cast_harness(p_units=SNAPPA, a_units=ENEMIES, extra=BUILD_TANKY)
    geom = _setup(h, target_dist=target_dist)
    if geom is None:
        pytest.skip("geometrie non montable sur ce board")
    snappa, target, others = geom
    snap = h.snapshot()
    live = h.cast_live(snappa, target, ABILITY)
    if not live["ok"]:
        pytest.skip("cast live refuse par le natif: %s" % str(live["raw"])[:200])
    _assert_live_mutated(live)

    st = h.offline_state(snap)
    last = _offline_cast(st, snappa, target)
    assert last.get("ported") is True, "1171 non routee par le handler: %s" % last

    off_main = ((last.get("main_attack") or {}).get("per_hit")) or []
    live_main = _live_damage(live, target)
    print("\n[DDD A dist=%d] snappa=u%d cible=u%d autres=%s" % (target_dist, snappa, target, others))
    print("[DDD A] live=%s" % live_main)
    print("[DDD A] off =%s" % off_main)
    print("[DDD A] hits=%s numLeft=%s picked=%s" % (last.get("hits"), last.get("num_left"),
                                                    last.get("picked")))

    n_hits = _cfg("nrOfHits")
    assert last.get("hits") == n_hits, \
        "GetNumHits() = %s != constants.nrOfHits = %d" % (last.get("hits"), n_hits)
    assert len(live_main) == n_hits, \
        "%d coups live != constants.nrOfHits = %d" % (len(live_main), n_hits)
    assert off_main == live_main, "per-coup offline %s != live %s" % (off_main, live_main)
    # cible tanky -> elle survit -> AUCUN leftover (ni live ni offline)
    assert _alive(st, target), "la cible devait survivre (--hp-target eleve) : setup a revoir"
    assert last.get("num_left") == 0, "numLeft=%s alors que la cible survit" % last.get("num_left")
    assert not last.get("leftover"), "volet leftover joue sans cible morte: %s" % last.get("leftover")
    assert set(live["damage_by_target"]) == {target}, \
        "live frappe %s, une seule cible attendue" % sorted(live["damage_by_target"])


# ------------------------------------------------------------------ (B) self-loss = % du PV MAXIMUM

def test_dakka_self_loss_is_pct_of_max_health(ability_cast_harness):
    """(B) `ChangeStat(caster, Health, Subtract, PercentageOf(StatAmount(caster, Health,
    StatPart.MAXIMUM), ConfigConst(healthPct)))`.

    DISCRIMINANT `MAXIMUM` vs `CURRENT` : le meme cast est rejoue DEUX FOIS sur le meme snapshot,
    une fois caster a PLEINE VIE, une fois caster BLESSE (PV courant force a la moitie). La perte
    doit etre la MEME dans les deux cas (elle est indexee sur le MAX) -- un port qui lirait le PV
    COURANT rendrait deux valeurs differentes, et c'est exactement ce que ce test refuse."""
    h = ability_cast_harness(p_units=SNAPPA, a_units=ENEMIES, extra=BUILD_TANKY)
    geom = _setup(h, target_dist=GETSTUCKIN_AGREED_DIST)
    if geom is None:
        pytest.skip("geometrie non montable sur ce board")
    snappa, target, _others = geom
    snap = h.snapshot()
    pct = _cfg("healthPct")

    # --- regime 1 : caster a PLEINE VIE
    st1 = h.offline_state(snap)
    hp1_before, hp_max = _hp(st1, snappa)
    _offline_cast(st1, snappa, target)
    hp1_after, _ = _hp(st1, snappa)
    lost1 = hp1_before - hp1_after

    # --- regime 2 : caster BLESSE (PV courant = moitie du max) sur le MEME snapshot
    st2 = h.offline_state(snap)
    hc = st2.get_entity(snappa).get_component(HealthComponent)
    hc.hp = int(hp_max) // 2
    hp2_before = hc.hp
    _offline_cast(st2, snappa, target)
    hp2_after, _ = _hp(st2, snappa)
    lost2 = hp2_before - hp2_after

    from fractions import Fraction
    from engine.dsl.base import _round_fix64
    expected = _round_fix64(Fraction(int(hp_max) * pct, 100), 0)
    print("\n[DDD B] maxHP=%s healthPct=%d attendu=%s | pleine vie: %s -> %s (perte %s)"
          % (hp_max, pct, expected, hp1_before, hp1_after, lost1))
    print("[DDD B] blesse (%s PV) : %s -> %s (perte %s)" % (hp2_before, hp2_before, hp2_after, lost2))

    assert lost1 == expected, \
        "perte %s != round_half_even(maxHP %s * %d%%) = %s" % (lost1, hp_max, pct, expected)
    assert lost2 == lost1, \
        ("perte %s (caster blesse) != %s (pleine vie) -> le pourcentage est pris sur le PV COURANT, "
         "alors que `StatAmount(caster, Health, StatPart.MAXIMUM=2)` impose le MAXIMUM" % (lost2, lost1))


# ------------------------------------------------------------------ (C) volet leftover (cible tuee)

def test_dakka_leftover_hits_live_equals_offline(ability_cast_harness):
    """(C) La cible MEURT -> `numLeft > 0` et les coups gaspilles partent sur des ennemis TIRES dans
    `Damageable(Unobscured(SurroundingEnemies(caster, range_2)))`. Confronte au LIVE : l'ENSEMBLE des
    unites frappees et le per-coup de chacune. C'est le seul cas qui exerce le canal
    `RandomAmount` + `PickRandomly` -- donc aussi la preuve que la consommation MT du port est calee
    (un tirage de trop ou de moins decalerait tous les degats suivants)."""
    h = ability_cast_harness(p_units=SNAPPA, a_units=ENEMIES, extra=BUILD_FRAGILE)
    geom = _setup(h, target_dist=GETSTUCKIN_AGREED_DIST, move_others=True)
    if geom is None:
        pytest.skip("geometrie non montable sur ce board")
    snappa, target, others = geom
    snap = h.snapshot()
    live = h.cast_live(snappa, target, ABILITY)
    if not live["ok"]:
        pytest.skip("cast live refuse par le natif: %s" % str(live["raw"])[:200])
    _assert_live_mutated(live)

    st = h.offline_state(snap)
    last = _offline_cast(st, snappa, target)
    assert last.get("ported") is True, "1171 non routee par le handler: %s" % last
    if _alive(st, target):
        pytest.skip("la cible a survecu offline (--hp-target trop haut) : pas de volet leftover")

    off_by = {target: ((last.get("main_attack") or {}).get("per_hit")) or []}
    for lo in (last.get("leftover") or []):
        off_by.setdefault(lo["target"], []).append(lo["total"])
    print("\n[DDD C] snappa=u%d cible=u%d autres=%s" % (snappa, target, others))
    print("[DDD C] numLeft=%s picked=%s hits_per=%s" % (last.get("num_left"), last.get("picked"),
                                                        last.get("hits_per")))
    print("[DDD C] live cibles=%s" % sorted(live["damage_by_target"]))
    print("[DDD C] off  cibles=%s" % sorted(off_by))

    assert last.get("num_left", 0) > 0, \
        "cible morte mais numLeft=%s : `NumLeftOverHits` ne compte rien" % last.get("num_left")
    assert last.get("picked"), "numLeft > 0 mais aucune cible piquee (pool vide ?)"
    # Les cibles LEFTOVER sortent du pool `SurroundingEnemies(caster, range_2)` : elles sont donc a
    # distance <= range_2 du caster ET differentes de la cible principale morte n'est PAS exclue du
    # pool par le natif (aucun `op_Subtraction`), mais elle n'y est plus : `Damageable` retire les
    # cadavres. On verifie les deux proprietes.
    rng2 = _cfg("range_2")
    cpos = st.get_entity(snappa).get_component(PositionComponent)
    for uid in last["picked"]:
        p = st.get_entity(uid).get_component(PositionComponent)
        d = hexgeo.distance((cpos.col, cpos.row), (p.col, p.row))
        assert d <= rng2, "u%d pique a distance %d > range_2 = %d" % (uid, d, rng2)
        assert uid != target, "la cible morte ne doit plus etre dans `Damageable(...)`"
    # LE discriminant de ce cas : l'ENSEMBLE des unites frappees. Il est produit par la chaine
    # `NumLeftOverHits` -> `RandomAmount(1, Min(numLeft, Count(pool)))` -> `PickRandomly(pool, n)` ;
    # un tirage de trop ou de moins, un pool mal ancre ou un `numLeft` faux le change.
    assert set(live["damage_by_target"]) == set(off_by), \
        ("live frappe %s, offline %s -> le pool, le tirage ou la consommation MT divergent"
         % (sorted(live["damage_by_target"]), sorted(off_by)))
    # Chaque cible piquee recoit `hits_per` coups OFFLINE (`GetLeftoverHitsPerTargetFormula`).
    for uid in last["picked"]:
        assert len([lo for lo in last["leftover"] if lo["target"] == uid]) >= 1, \
            "u%d pique mais aucune attaque leftover emise" % uid
    # ⚠ Le PER-COUP n'est PAS comparable dans ce regime, et ce n'est pas un ecart de port : les
    # cibles sont a `--hp-target 600` et meurent au 1er coup ; le natif rapporte le degat APPLIQUE
    # (clampe aux PV : `Amount = 600`) puis `ApplyDamageOperation$$Execute` retourne des l'entree sur
    # `UnitFlag.Overkilled` -> plus AUCUN evenement pour les coups suivants, alors que le port expose
    # le degat DEMANDE coup par coup (residu deja nomme dans `ChainLeftOverHitsAttackDamage` : << le
    # `total` rapporte pour l'iteration fatale est sur-estime (diagnostic) >>). L'egalite per-coup est
    # mesuree par le cas (A), sur une cible qui SURVIT.
    assert len(_live_damage(live, target)) >= 1, "la cible principale doit avoir encaisse"


# ------------------------------------------------------------------ (D) GARDE ROUGE

def test_dakka_unported_is_a_silent_noop(ability_cast_harness, monkeypatch):
    """(D) MUTATION ADVERSARIALE = l'etat d'AVANT ce port. Le MEME snapshot, le MEME cast, avec 1171
    RETIRE d'`ABILITY_CLASSES` : `ported=False`, ZERO degat, ZERO self-loss -- et pourtant le cast
    est ACCEPTE (les flags de tour sont poses par le handler, comme le natif).

    C'est aussi la preuve que le montage n'est PAS rate (piege du harnais : un `applyAction` peut
    rendre `ok=True` sans rien muter). Le MEME snapshot rejoue avec le registre INTACT mute -- si le
    montage etait rate, les deux branches rendraient 0."""
    h = ability_cast_harness(p_units=SNAPPA, a_units=ENEMIES, extra=BUILD_TANKY)
    geom = _setup(h, target_dist=GETSTUCKIN_AGREED_DIST)
    if geom is None:
        pytest.skip("geometrie non montable sur ce board")
    snappa, target, _others = geom
    snap = h.snapshot()

    # --- branche ROUGE : registre ampute (etat d'avant le port)
    amputee = dict(HANDLER.ABILITY_CLASSES)
    amputee.pop(ABILITY, None)
    monkeypatch.setattr(HANDLER, "ABILITY_CLASSES", amputee)
    st_red = h.offline_state(snap)
    hp_t_before, _ = _hp(st_red, target)
    hp_c_before, _ = _hp(st_red, snappa)
    last_red = _offline_cast(st_red, snappa, target)
    hp_t_red, _ = _hp(st_red, target)
    hp_c_red, _ = _hp(st_red, snappa)
    print("\n[DDD D-rouge] ported=%s flags=%s | cible %s -> %s | caster %s -> %s"
          % (last_red.get("ported"), last_red.get("flags"), hp_t_before, hp_t_red,
             hp_c_before, hp_c_red))
    assert last_red.get("ported") is False, \
        "la mutation adversariale n'a pas pris (1171 encore dans le registre) : %s" % last_red
    assert hp_t_red == hp_t_before, "NO-OP attendu : la cible a perdu des PV sans classe portee"
    assert hp_c_red == hp_c_before, "NO-OP attendu : le caster a perdu des PV sans classe portee"
    assert last_red.get("flags") is not None, \
        ("le cast doit rester ACCEPTE (flags de tour poses) meme non porte -- sinon on mesure un "
         "montage rate, pas le no-op silencieux")

    # --- branche VERTE : MEME snapshot, registre INTACT -> ca mute
    monkeypatch.undo()
    st_green = h.offline_state(snap)
    last_green = _offline_cast(st_green, snappa, target)
    hp_t_green, _ = _hp(st_green, target)
    hp_c_green, _ = _hp(st_green, snappa)
    print("[DDD D-verte] ported=%s | cible %s -> %s | caster %s -> %s"
          % (last_green.get("ported"), hp_t_before, hp_t_green, hp_c_before, hp_c_green))
    assert last_green.get("ported") is True, "1171 devait etre routee apres `monkeypatch.undo()`"
    assert hp_t_green < hp_t_before, \
        ("MONTAGE RATE (et non no-op) : le cast ne fait rien meme registre intact -- caster u%d, "
         "cible u%d" % (snappa, target))
    assert hp_c_green < hp_c_before, "le self-loss doit retirer des PV au caster"
