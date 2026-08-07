"""#522-r1 -- QUAND le natif applique le +15 de `ThrillSeekers` : APRES le crit du coup 0.

LA LOI, lue dans le decompile (build `rnca9r7q6c`), et c'est elle qui commande :

  * `IdunBattle.Operations.AttackDamageOperation$$ExecuteHits` boucle PAR COUP sur
    `IdunBattle.Operations.AttackDamageOperation$$ExecuteHit` ;
  * dans `ExecuteHit`, l'ordre est : slot 0xad (profil) -> `AttackHit..ctor` ->
    **slot 0xa `RollCritical`** -> `AbilityEntities..ctor` -> `EnqueueOperation(6)` =
    `On(PreAttackHit)` -> `EnqueueOperation(7)` -> sub-op `0x42` -> `EvaluateAfterHitTriggers` ;
  * `IdunBattle.Core.Services.DamagePrediction$$RollCritical` relit
    `UnitExtensions.GetStat(attacker, 0x9 = CritChance, 0 = Current)` **a chaque appel**, y ajoute
    `GetCritChanceBonusFromEffects`, sort SANS tirage si `cc < 1`, clampe a 100, puis `NextBool`.

=> le stat-mod « Thrilled » (0x59a = 1434, +15 CRIT_CHANCE) pose par
`...ThrillSeekersAbility$$CreateBehaviour` sur `On(PreAttackHit) & IsFirstHitInSeries`
**n'affecte JAMAIS le coup qui l'a declenche**, et **affecte tous les coups suivants**, ceux de la
MEME salve compris.

Ce que ces bras GARDENT :

  * `test_roll_crit_coup0_offline`   -- le foyer `_run_hits` applique `crit_chance_after` aux coups
    `idx != 0` et **seulement** a eux. Deterministe, sans runner : `crit_chance=0` (donc
    `RollCritical` sort avant tout tirage) et `crit_chance_after=100` (crit certain) rendent une
    sequence de crits `[False, True, True]` -- toute autre repartition est une violation de la loi ;
  * `test_ordre_vecteurs_offline`    -- les TROIS vecteurs d'attaque mesurent la crit chance AVANT
    d'emettre `On(PreAttackHit)`, puis la relisent. C'est l'ORDRE qui est garde, pas un scalaire ;
  * `test_thrill_seekers_bit_exact_live` -- natif vs port sur un porteur MULTI-COUPS a crit chance
    de BASE nulle : le coup 0 ne doit consommer AUCUN tirage de crit. C'est le bras qui rougissait
    avant le correctif, **en DEGAT** et pas seulement en compteur.

⚠ Le regime live est choisi pour que la loi soit OBSERVABLE, pas pour qu'elle passe : a
`--crit "0,700"` le natif ne tire pas au coup 0 (`cc < 1`) alors que l'ancien port tirait a 15 --
le tirage excedentaire DECALE tout le flux RNG de la salve, donc les montants divergent. Mesure du
2026-08-07 avant correctif : natif **2737** / port **2724**, tirages **3** / **4**.
"""
from __future__ import annotations

#: Ce qui doit changer pour que ce FICHIER de test puisse changer de verdict (#486-r15).
DECLENCHEUR = {
    "chemins": (
        "scripts/python/conftest.py", "scripts/python/tests/conftest.py",
        "scripts/python/tests/engine/conftest.py",
        "scripts/python/tests/engine/runner/conftest.py",
        "scripts/python/green_skip_guard.py", "scripts/python/declencheur_guard.py",
        "scripts/python/catalog_inject.py",
        "scripts/python/gameconfig.py", "scripts/python/enum_maps.py",
        "scripts/python/host_inputs.py", "scripts/python/rl_collect_batch.py",
        "scripts/python/stream_events.py", "scripts/python/symbols_layout.py",
        "scripts/python/engine/runner/snapshot.py",
        # PROPRE A CE FICHIER, pris LARGE : le canal CRIT traverse les trois vecteurs d'attaque,
        # le dispatch de triggers, le PRNG et le registre de traits. Foyers load-bearing pour la
        # relecture humaine : `operations/damage_hits.py` (`_run_hits`, `_roll_crit`),
        # `operations/damage.py` (`_crit_params`), `operations/damage_ops/{normal,normal_like,
        # ability}.py` (l'ORDRE event/mesure), `operations/triggers/loki/thrill_seekers.py`.
        "scripts/python/engine/**/*.py",
        "scripts/python/*.py",
    ),
    "build": True,
    "toujours": False,
    "raison": "Confrontation LIVE port-vs-natif du TIMING d'un stat-mod de crit chance pose "
              "pendant la salve : l'oracle est le jeu lui-meme (degat, ORDRE des tirages). Un "
              "changement de build peut faire changer ce fichier d'avis sans qu'une ligne du port "
              "bouge.",
}

import pytest

from engine.entities.effect_type import EffectType
from engine.entities.pathfinding.board import Board
from engine.runner.components import HealthComponent
from engine.runner.messages import AttackUnitMessage
from engine.runner.operations.damage import AttackDamageOperation
from engine.runner.operations.damage_hits import HitDamage
from engine.runner.prng import IntBasedMersenneTwister
from engine.runner.runner import Runner
from engine.runner.snapshot import load_state

BOARD = "MC1_67"
SEED = "5221"
CASTER = "emperNoiseMarine"       # porteur `ThrillSeekers` MULTI-COUPS, et DANS le pool
ALLY = "ultraTitus"
FOE = "necroWarden"
FOE_B = "orksNob"
CRIT_BASE = 0                     # crit chance de BASE nulle : le +15 est la SEULE source
THRILLED = int(EffectType.ThrillSeekers)      # 0x59a = 1434


# ------------------------------------------------------------------------------- OFFLINE

def test_roll_crit_coup0_offline():
    """Le coup 0 prend `crit_chance`, les coups 1+ prennent `crit_chance_after`. DETERMINISTE.

    ⚠ **LE SENS DU TEST EST CONTRAINT PAR L'EXTINCTION DU CRIT**, et c'est une lecture native, pas
    une commodite : `IdunBattle.Operations.AttackDamageOperation$$ExecuteHits` eteint
    `isCriticalDamageAllowed` (`hitGroup+0x3c`) des qu'un coup NE CRITE PAS, et le propage a
    l'attaque (`attack[+0x40] &= hitGroup[+0x3c]`). Un coup 0 qui ne crite pas prive donc TOUS les
    coups suivants de leur `RollCritical` -- le bonus de `ThrillSeekers` ne peut mordre QUE si le
    coup 0 a crite avec la crit chance de BASE. Le couple qui exerce la loi est donc
    `cc=100 / cc_after=0`, jamais `cc=0 / cc_after=100` (ce dernier rend `[False, False, False]`
    par extinction, et ne mesurerait RIEN)."""
    plat = HitDamage(100, 100)            # bornes degenerees : le tirage de valeur ne varie pas
    r = AttackDamageOperation._run_hits(
        IntBasedMersenneTwister(12345), plat, plat, 100, True, 3, [],
        crit_chance_after=0, crit_enabled_after=False)
    assert r["crits"] == [True, False, False], (
        "loi #522-r1 : le coup 0 prend `crit_chance` (100 -> crite), les coups 1+ prennent "
        "`crit_chance_after` (0 -> ne critent pas, puis extinction) -- obtenu %r" % (r["crits"],))

    # CONTRE-EPREUVE 1 : sans les deux parametres, le comportement est INCHANGE (strict no-op) --
    # c'est ce qui borne le rayon du correctif a ses seuls appelants.
    r2 = AttackDamageOperation._run_hits(
        IntBasedMersenneTwister(12345), plat, plat, 100, True, 3, [])
    assert r2["crits"] == [True, True, True], (
        "sans `crit_chance_after`, `_run_hits` doit garder la valeur unique sur tous les coups "
        "-- obtenu %r" % (r2["crits"],))

    # CONTRE-EPREUVE 2 : le regime que l'extinction rend AVEUGLE. Il est verifie ici pour que la
    # contrainte ci-dessus soit MESUREE et non affirmee -- si un jour l'extinction changeait, ce
    # bras rougirait et le premier couple ne serait plus le seul discriminant.
    r3 = AttackDamageOperation._run_hits(
        IntBasedMersenneTwister(12345), plat, plat, 0, False, 3, [],
        crit_chance_after=100, crit_enabled_after=True)
    assert r3["crits"] == [False, False, False], (
        "un coup 0 non-crite ETEINT le crit de toute la salve (`isCriticalDamageAllowed`), donc "
        "`crit_chance_after` y est inobservable -- obtenu %r" % (r3["crits"],))


def test_ordre_vecteurs_offline():
    """Les TROIS vecteurs mesurent la crit chance AVANT d'emettre `On(PreAttackHit)`, puis la
    relisent. C'est l'ORDRE des lignes qui est garde : un fix qui se contenterait d'ajouter le
    parametre a `_run_hits` sans deplacer la mesure serait un no-op silencieux."""
    import inspect
    from engine.runner.operations.damage_ops import ability, normal, normal_like

    for mod in (normal, normal_like, ability):
        src = inspect.getsource(mod)
        i_avant = src.find("crit_avant")
        i_event = src.find("pre_attack_hit_triggers(state")
        i_apres = src.find("crit_apres")
        nom = mod.__name__.rsplit(".", 1)[-1]
        assert i_avant >= 0, "%s : la mesure PRE-event (`crit_avant`) est absente" % nom
        assert i_event >= 0, "%s : l'emission de `On(PreAttackHit)` est introuvable" % nom
        assert i_apres >= 0, "%s : la relecture POST-event (`crit_apres`) est absente" % nom
        assert i_avant < i_event, (
            "%s : la crit chance du coup 0 doit etre mesuree AVANT l'emission de "
            "`On(PreAttackHit)` -- sinon le coup 0 voit un stat-mod que le natif lui refuse" % nom)
        assert i_event < i_apres, (
            "%s : la relecture doit suivre l'emission, sinon les coups 1+ ne voient jamais le "
            "stat-mod que le natif leur accorde" % nom)
        assert "crit_chance_after=crit_apres[0]" in src, (
            "%s : la valeur relue doit etre passee a `_run_hits`" % nom)


def test_porteurs_du_trait_offline():
    """Le RAYON du correctif, RE-COMPTE par le code : les porteurs du trait `ThrillSeekers`.

    Ce n'est pas decoratif -- c'est ce qui dit combien d'unites changent de comportement. Le trait
    est le SEUL ecouteur porte de `On(PreAttackHit)`/`On(PreAttackDamageHit)` du registre, donc
    hors de ces porteurs le correctif est un strict no-op."""
    import unit_map
    porteurs = sorted(k.get("id") for k in unit_map.all_kits()
                      if "ThrillSeekers" in (k.get("traits") or []))
    assert porteurs, "aucun porteur -- le recensement est casse, la garde serait VACUE"
    assert CASTER in porteurs, "%s doit porter le trait (montage live)" % CASTER


# ---------------------------------------------------------------------------------- LIVE

@pytest.fixture(scope="module")
def env(live_session, rpc, build_runner):
    """Porteur MULTI-COUPS a crit chance de BASE nulle, cible a PLEINE VIE (gate `NOT IsWounded`)."""
    built = build_runner(SEED, extra=[
        "--board", BOARD, "--rank", "17", "--no-ai",
        "--crit", "%d,700" % CRIT_BASE, "--hp-target", "400000",
        "--p-units", "%s,%s" % (CASTER, ALLY), "--a-units", "%s,%s" % (FOE, FOE_B),
        "--place", "%s:4,5" % CASTER, "--place", "%s:4,7" % ALLY,
        "--a-place", "%s:4,6" % FOE, "--a-place", "%s:0,3" % FOE_B], keep=True)
    rid = built["rid"]
    dv = rpc("decisionView", {"runnerId": rid, "allAbilities": True}, 150)
    u = {x.get("visualId"): x for x in (dv.get("units") or []) if x.get("alive")}
    for v in (CASTER, FOE):
        assert v in u, "%s absent du plateau -- montage KO" % v
    bg = rpc("boardGraph", {"runnerId": rid}, 60)
    assert isinstance(bg, dict) and bg.get("tiles"), "boardGraph KO"
    na = next((a["id"] for a in (u[CASTER].get("abilities") or [])
               if a.get("kind") == "normal" and a.get("id") is not None), None)
    assert na is not None, "attaque normale introuvable -- montage non conforme"
    return {"rid": rid, "board": Board(bg["tiles"], adjacency="evenq"),
            "cid": u[CASTER]["id"], "tid": u[FOE]["id"], "na": int(na)}


@pytest.fixture(scope="module")
def salve(env, rpc):
    """UNE salve, mesuree des deux cotes : degat, tirages consommes, et pose de 1434."""
    rid, board = env["rid"], env["board"]
    cid, tid = env["cid"], env["tid"]

    dv = rpc("decisionView", {"runnerId": rid, "allAbilities": True}, 150)
    ob = rpc("observeBattle", {"runnerId": rid}, 90)
    snap = rpc("combatSnapshot", {"runnerId": rid}, 120)
    ab = rpc("unitAbilityStates", {"runnerId": rid}, 90)
    rng0 = rpc("dumpRng", {"runnerId": rid}, 30)
    assert isinstance(rng0, dict) and rng0.get("mt"), "dumpRng KO -- MT non calable"
    st = load_state(dv, ob, snap, board=board, ability_states=ab)
    rng = IntBasedMersenneTwister()
    rng.mt, rng.mti = list(rng0["mt"]), rng0["mti"]
    st.rng = rng

    def _hp_nat(o):
        for x in ((o or {}).get("units") or []):
            if x.get("squadId") == tid and not x.get("isDead"):
                return x.get("hp")
        return None

    def _hp_off():
        e = st.get_entity(tid)
        hc = e.get_component(HealthComponent) if e is not None else None
        return hc.hp if hc is not None else None

    hp0_nat, hp0_off = _hp_nat(ob), _hp_off()
    res = rpc("applyAction", {"runnerId": rid,
                              "action": {"kind": "ability", "casterId": cid, "targetId": tid,
                                         "abilityType": env["na"]}}, 240)
    a0 = ((res or {}).get("actions") or [{}])[0]
    assert a0.get("ok") and a0.get("mutated"), "le natif REFUSE l'attaque : %r" % (a0,)
    rng1 = rpc("dumpRng", {"runnerId": rid}, 30)
    ob2 = rpc("observeBattle", {"runnerId": rid}, 90)
    Runner(st).install_default_handlers(20).apply(AttackUnitMessage(cid, tid))

    def _tirages(mt_c, mti_c, cap=6000):
        r = IntBasedMersenneTwister()
        r.mt, r.mti = list(rng0["mt"]), rng0["mti"]
        for n in range(cap + 1):
            if r.mti == mti_c and r.mt == list(mt_c):
                return n
            r.genrand_int32()
        return None

    dv2 = rpc("decisionView", {"runnerId": rid, "allAbilities": True}, 150)
    eff = sorted(e.get("effectType") for x in (dv2.get("units") or []) if x.get("id") == cid
                 for e in (x.get("effects") or []) if isinstance(e, dict))
    return {"nat": (hp0_nat or 0) - (_hp_nat(ob2) or 0),
            "off": (hp0_off or 0) - (_hp_off() or 0),
            "n_nat": _tirages(rng1.get("mt"), rng1.get("mti")),
            "n_off": _tirages(st.rng.mt, st.rng.mti),
            "eff_caster": eff}


def test_regime_exerce_la_loi_live(salve):
    """Sans 1434 pose par le NATIF, ce fichier ne mesurerait rien -- le regime serait VACUE."""
    assert THRILLED in salve["eff_caster"], (
        "le natif n'a pas pose `Thrilled` (1434) : le trigger n'a pas fire (cible pas a pleine "
        "vie ?), donc la loi n'est PAS exercee -- effets du caster = %r" % (salve["eff_caster"],))
    assert salve["nat"] > 0, "temoin NUL -- aucun degat, un accord ne prouverait rien"


def test_thrill_seekers_bit_exact_live(salve):
    """Le coup 0 ne consomme AUCUN tirage de crit a cc de base nulle -- donc port == natif."""
    assert salve["n_nat"] is not None and salve["n_off"] is not None, (
        "etat RNG cible non atteint -- mesure MUETTE")
    assert salve["n_off"] == salve["n_nat"], (
        "le port consomme %s tirage(s) contre %s au natif : le coup 0 voit un stat-mod que "
        "`ExecuteHit` lui refuse (`RollCritical` PRECEDE `On(PreAttackHit)`)"
        % (salve["n_off"], salve["n_nat"]))
    assert salve["off"] == salve["nat"], (
        "DEGAT divergent (port %s vs natif %s) : le tirage excedentaire du coup 0 decale tout le "
        "flux RNG de la salve" % (salve["off"], salve["nat"]))
