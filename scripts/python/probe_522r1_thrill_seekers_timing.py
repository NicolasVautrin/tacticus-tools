#!/usr/bin/env python
"""probe #522-r1 -- QUAND le natif applique le +15 de `ThrillSeekers` ? Le decompile tranche.

LA LOI, LUE (build `rnca9r7q6c`) -- et c'est elle qui commande, pas le compte de tirages
------------------------------------------------------------------------------------------
`IdunBattle.Operations.AttackDamageOperation$$ExecuteHits` boucle PAR COUP
(`while (compteur < numHits) { ... ExecuteHit(...) ... compteur++ }`) et appelle
`IdunBattle.Operations.AttackDamageOperation$$ExecuteHit` a chaque tour.

Dans `ExecuteHit`, l'ordre est (mirror du decompile, sans rien reordonner) :

    1.  slot 0xad de `IBattleQuery`            -> le `DamageProfile` du coup
    2.  `AttackHit..ctor(damage, abilityOrEffect)` -> ecrit dans `<comp>+0x98`
    3.  **slot 0xa d'`IDamagePrediction` = `RollCritical`**            <-- LE CRIT EST TIRE ICI
    4.  `AbilityEntities..ctor(...)`
    5.  `EnqueueOperation(..., 6, entities)`   = `On(PreAttackHit)`    <-- L'EVENT EST EMIS ICI
    6.  `EnqueueOperation(..., 7, entities)`   = `On(PreAttackDamageHit)`
    7.  ... `IsAttackMaxOutDamage`, slot 0xb (`GetHitDamage`) ...
    8.  sub-operation `0x42` (application du degat)
    9.  `ADamageOperation$$EvaluateAfterHitTriggers`

et `IdunBattle.Core.Services.DamagePrediction$$RollCritical(this, attacker, defender,
abilityOrEffect, hitIndex)` est, terme a terme :

    cc = UnitExtensions.GetStat(attacker, 0x9 = CritChance, 0 = Current, 0)      <-- RELU A CHAQUE COUP
       + DamagePrediction.GetCritChanceBonusFromEffects(attacker, defender, ..., hitIndex)
    if (cc < 1)   return false          # AUCUN tirage
    if (cc > 100) cc = 100
    return NextBool(cc)                 # 1 tirage

=> **DEUX faits, et c'est leur CONJONCTION qui fait la loi** :
   (a) `GetStat(9)` est **relu par coup**, donc un stat-mod pose pendant la salve mord sur les
       coups SUIVANTS de la MEME attaque ;
   (b) `On(PreAttackHit)` est emis **APRES** le `RollCritical` du coup courant.

   => le stat-mod « Thrilled » (0x59a = 1434, +15 CRIT_CHANCE) pose par
      `...ThrillSeekersAbility$$CreateBehaviour` sur `On(PreAttackHit) & IsFirstHitInSeries`
      **n'affecte JAMAIS le coup qui l'a declenche**, et **affecte tous les coups suivants**.

CE QUE LE PORT FAIT, ET POURQUOI C'EST FAUX
--------------------------------------------
Les trois vecteurs (`damage_ops/{normal,normal_like,ability}.py`) emettent
`pre_attack_hit_triggers(...)` **AVANT** `AttackDamageOperation._crit_params(...)`, et
`_crit_params` est appele **UNE FOIS par attaque**, avant `_run_hits`. Le port applique donc le
+15 a **TOUS** les coups, coup 0 compris. Le natif ne l'applique qu'a partir du coup 1.

⚠ Deux docstrings du port AFFIRMENT le contraire, et disent d'ou vient le faux :
  * `runner/operations/triggers/loki/thrill_seekers.py` : « vecteur `pre_attack_hit_triggers`
    (emis par les 3 vecteurs d'attaque AVANT `_crit_params` = **la place NATIVE** : `ExecuteHit`
    emet `On(6)` **en TETE**, avant le calcul du crit de CE coup) ». `On(6)` est en QUEUE.
  * `runner/operations/damage.py::_crit_params` : « crit-chance constante sur les coups d'UNE
    attaque => `_crit_params` (avant `_run_hits`) == valeur re-lue par coup. **Rien a porter.** »
    Son argument est une **recherche gameconfig sur 559 ABILITIES** (« AUCUNE cle per-hit ») --
    or `ThrillSeekers` est un **TRAIT**, structurellement hors du corpus fouille. Le recensement
    ne pouvait pas voir son propre contre-exemple.

CE QUE CE PROBE MESURE (board `MC1_67`, positions FORCEES)
----------------------------------------------------------
Porteur **MULTI-COUPS** : le regime ou la loi est la plus visible, parce que l'ecart porte sur le
SEUL coup 0 et que les coups suivants doivent, eux, RESTER identiques.

    `--crit "0,700"` : crit chance de BASE nulle.
      natif  : coup 0 -> cc = 0   -> `RollCritical` sort AVANT tout tirage  (0 tirage)
               coups 1+ -> cc = 15 -> 1 tirage chacun
      port   : tous les coups -> cc = 15 -> 1 tirage chacun

    => l'ecart n'est pas qu'un compteur : le tirage EXCEDENTAIRE du coup 0 **decale tout le flux
       RNG** de la salve, donc les MONTANTS des coups suivants divergent aussi. C'est une
       divergence de DEGAT, deterministe, pas un ecart probabiliste.

Usage (depuis `scripts/python`, ASCII only) :
    python probe_522r1_thrill_seekers_timing.py
    python probe_522r1_thrill_seekers_timing.py --porteur emperLucius
    python probe_522r1_thrill_seekers_timing.py --keep
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import tempfile
import urllib.request

HOST = "http://127.0.0.1:8765"
PYDIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, PYDIR)

BOARD = "MC1_67"
SEED = 5221
#: Les CINQ porteurs du trait `UnitTrait.ThrillSeekers` (1056), mesures sur `unit_map.all_kits()`,
#: avec le nombre de coups de leur arme -- c'est lui qui decide de la visibilite de l'ecart.
PORTEURS = {"emperNoiseMarine": 9, "emperLucius": 6, "emperKakophonist": 3,
            "emperFlawlessBlade": 3, "emperExultant": 1}
DEFAUT = "emperNoiseMarine"          # 9 coups, et DANS le pool `--list-pool` (aucune injection)
ALLY = "ultraTitus"
FOE = "necroWarden"
FOE_B = "orksNob"
CRIT = "0,700"                       # crit chance de BASE nulle : le +15 est la SEULE source
HP_TARGET = 400000                   # la cible doit SURVIVRE, et etre a PLEINE VIE (gate IsWounded)


def _sid():
    with urllib.request.urlopen(HOST + "/api/admin/status", timeout=20) as r:
        return json.loads(r.read().decode("utf-8"))["session"]["id"]


def _rpc(sid, method, body=None, timeout=120):
    payload = json.dumps({"method": method, "args": [body] if body is not None else []}).encode()
    req = urllib.request.Request("%s/api/scripts/%s/rpc" % (HOST, sid), data=payload,
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        out = json.loads(r.read().decode("utf-8"))
    return out.get("result") if isinstance(out, dict) and "result" in out else out


def _duel(args, timeout=500):
    return subprocess.run([sys.executable, "rl_duel.py"] + args, cwd=PYDIR,
                          capture_output=True, text=True, timeout=timeout)


def tirages(rng0, mt_c, mti_c, cap=6000):
    """Nombre de `genrand_int32` pour aller de l'etat INITIAL a l'etat CIBLE. Une soustraction de
    `mti` serait FAUSSE (le MT19937 se recharge tous les 624 tirages)."""
    from engine.runner.prng import IntBasedMersenneTwister
    r = IntBasedMersenneTwister()
    r.mt, r.mti = list(rng0["mt"]), rng0["mti"]
    for n in range(cap + 1):
        if r.mti == mti_c and r.mt == list(mt_c):
            return n
        r.genrand_int32()
    return None


def build(state_file, porteur, seed_bc):
    argv = ["build", "--seed", str(SEED), "--board", BOARD, "--crit", CRIT,
            "--hp-target", str(HP_TARGET),
            "--p-units", "%s,%s" % (porteur, ALLY), "--a-units", "%s,%s" % (FOE, FOE_B),
            "--place", "%s:4,5" % porteur, "--place", "%s:4,7" % ALLY,
            "--a-place", "%s:4,6" % FOE, "--a-place", "%s:0,3" % FOE_B,
            "--state-file", state_file]
    if seed_bc:
        argv += ["--seed-bc", seed_bc]
    p = _duel(argv)
    if p.returncode != 0:
        print("[build] rc=%s\n%s\n%s" % (p.returncode, p.stdout[-2000:], p.stderr[-1000:]))
        return None
    with open(state_file, "r", encoding="utf-8") as f:
        return int(json.load(f)["runnerId"])


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--porteur", default=DEFAUT, choices=sorted(PORTEURS))
    ap.add_argument("--keep", action="store_true")
    args = ap.parse_args()
    porteur = args.porteur

    import catalog_inject
    from engine.entities.effect_type import EffectType
    from engine.entities.pathfinding.board import Board
    from engine.runner.components import HealthComponent
    from engine.runner.messages import AttackUnitMessage
    from engine.runner.prng import IntBasedMersenneTwister
    from engine.runner.runner import Runner
    from engine.runner.snapshot import load_state

    tmp = tempfile.mkdtemp(prefix="p522r1_")
    state_file = os.path.join(tmp, "st_%s.json" % porteur)
    seed_bc = None
    # `emperNoiseMarine` est DANS le pool ; les autres porteurs sont hors catalogue.
    if porteur != "emperNoiseMarine":
        seed_bc = os.path.join(tmp, "sbc.json")
        catalog_inject.write_augmented_seed_bc(seed_bc, [porteur])

    sid = _sid()
    rid = build(state_file, porteur, seed_bc)
    if rid is None:
        print("[522-r1] BUILD KO -- aucune mesure")
        return 2
    print("[522-r1] runner=%s porteur=%s (arme %s coups) board=%s"
          % (rid, porteur, PORTEURS[porteur], BOARD))
    ok = True
    try:
        dv = _rpc(sid, "decisionView", {"runnerId": rid, "allAbilities": True}, 150)
        u = {x.get("visualId"): x for x in (dv.get("units") or [])}
        for v in (porteur, FOE):
            if v not in u:
                print("[522-r1] MONTAGE INVALIDE -- %s absent" % v)
                return 2
        cid, tid = u[porteur]["id"], u[FOE]["id"]
        na = next((a["id"] for a in (u[porteur].get("abilities") or [])
                   if a.get("kind") == "normal" and a.get("id") is not None), None)
        if na is None:
            print("[522-r1] attaque normale introuvable -- montage non conforme")
            return 2

        ob = _rpc(sid, "observeBattle", {"runnerId": rid}, 90)
        snap = _rpc(sid, "combatSnapshot", {"runnerId": rid}, 120)
        ab = _rpc(sid, "unitAbilityStates", {"runnerId": rid}, 90)
        tiles = _rpc(sid, "boardGraph", {"runnerId": rid}, 90)["tiles"]
        rng0 = _rpc(sid, "dumpRng", {"runnerId": rid}, 60)
        st = load_state(dv, ob, snap, board=Board(tiles, adjacency="evenq"), ability_states=ab)
        r = IntBasedMersenneTwister()
        r.mt, r.mti = list(rng0["mt"]), rng0["mti"]
        st.rng = r

        def hp_nat(o):
            for x in ((o or {}).get("units") or []):
                if x.get("squadId") == tid and not x.get("isDead"):
                    return x.get("hp")
            return None

        def hp_off():
            e = st.get_entity(tid)
            hc = e.get_component(HealthComponent) if e is not None else None
            return hc.hp if hc is not None else None

        hp0_nat, hp0_off = hp_nat(ob), hp_off()
        # Le porteur doit etre a PLEINE VIE cote CIBLE (gate `NOT IsWounded(target)`), sinon le
        # trigger ne fire pas et le regime ne mesure RIEN.
        print("[522-r1] cible %s(%s) hp=%s ; caster=%s(%s)" % (FOE, tid, hp0_nat, porteur, cid))

        p2 = _duel(["act", "ability", "--caster", str(cid), "--ability", str(int(na)),
                    "--target", str(tid), "--state-file", state_file, "--runner", str(rid)])
        sortie = (p2.stdout or "") + (p2.stderr or "")
        if p2.returncode != 0 or "mutated" not in sortie.lower():
            print("[522-r1] attaque REFUSEE (rc=%s) :\n%s" % (p2.returncode, sortie[-1500:]))
            return 2
        rng1 = _rpc(sid, "dumpRng", {"runnerId": rid}, 60)
        ob2 = _rpc(sid, "observeBattle", {"runnerId": rid}, 90)
        d_nat = (hp0_nat or 0) - (hp_nat(ob2) or 0)

        Runner(st).install_default_handlers(20).apply(AttackUnitMessage(cid, tid))
        d_off = (hp0_off or 0) - (hp_off() or 0)
        n_nat = tirages(rng0, rng1.get("mt"), rng1.get("mti"))
        n_off = tirages(rng0, st.rng.mt, st.rng.mti)

        eff = _rpc(sid, "decisionView", {"runnerId": rid, "allAbilities": True}, 150)
        thrilled = [e.get("effectType") for x in (eff.get("units") or []) if x.get("id") == cid
                    for e in (x.get("effects") or []) if isinstance(e, dict)]

        print("\n-- E1 degat de la salve ------------------------------------")
        print("    natif delta=%s   port delta=%s" % (d_nat, d_off))
        print("    tirages genrand_int32 : natif=%r  port=%r" % (n_nat, n_off))
        print("    effets du CASTER apres la salve : %r (1434 = Thrilled)" % (sorted(thrilled),))
        if d_nat <= 0:
            print("    ECHEC : temoin NUL -- aucun degat, le regime ne mesure rien")
            ok = False
        if int(EffectType.ThrillSeekers) not in thrilled:
            print("    ECHEC : le natif n'a PAS pose 1434 -- le trigger n'a pas fire, donc le")
            print("            regime n'exerce PAS la loi (cible pas a pleine vie ?)")
            ok = False
        if n_nat is None or n_off is None:
            print("    ECHEC : etat RNG cible non atteint -- mesure MUETTE")
            ok = False
        elif n_off != n_nat:
            print("    ECHEC : le port consomme %d tirage(s) de plus que le natif." % (n_off - n_nat))
            print("            LOI : `RollCritical` PRECEDE `On(PreAttackHit)` dans `ExecuteHit`,")
            print("            donc le coup 0 ne voit PAS le +15 -- a cc de base 0 il ne tire meme")
            print("            pas (`cc < 1` sort avant le tirage).")
            ok = False
        if d_off != d_nat:
            print("    ECHEC : DEGAT divergent (port %s vs natif %s) -- le tirage excedentaire du"
                  % (d_off, d_nat))
            print("            coup 0 DECALE tout le flux RNG de la salve.")
            ok = False
    finally:
        if not args.keep:
            _duel(["dispose", "--state-file", state_file])

    print("\n[522-r1] %s" % ("PROBE OK" if ok else "PROBE KO"))
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
