"""#407 -- la failed-block list est-elle portee par l'ATTAQUE ou par la SERIE de coups ?

QUESTION (binaire) : une source de block qui a ECHOUE pendant les coups d'ARME est-elle
RE-TIREE par les coups ADDITIONNELS de la meme attaque, ou reste-t-elle EXCLUE ?

RE (decompile = verite, rnca9r7q6c), chaine LUE de bout en bout :
  * `IdunBattle.Core.OngoingAttack$$.ctor` cree `+0x48 = new List<int>()` (`FailedBlockIds`),
    NEUVE par attaque -- exactement comme `+0x40 = 1` (`isCriticalDamageAllowed`) ;
  * `IdunBattle.Operations.ADamageOperation$$GetFailedBlockIds` la rend
    (`HasCurrentAttack() ? GetCurrentAttack().FailedBlockIds : new List<int>()`) ;
  * `IdunBattle.Operations.ADamageOperation$$SetupHitGroup` la seme PAR REFERENCE dans
    `OngoingHitGroup+0x60` ;
  * `IdunBattle.Operations.AttackDamageOperation$$ExecuteHits` la passe a chaque coup
    (`options[+0x30] = hitGroup[+0x60]`) et `ADamageOperation$$RegisterBlocks` y AddRange les ids
    echoues du coup (`hitGroup[+0x60].AddRange(result[+0x28])`) ;
  * `IdunBattle.Core.Services.DamageCalculations$$CalculateBlockChances` EXCLUT toute source dont
    l'id y figure (`Contains(failedBlockIds, id)` -> `continue`) => **0 tirage** pour elle.

`AttackDamageOperation$$Execute` ne construit qu'UN `OngoingHitGroup`, partage par la phase
d'arme, les coups bonus et `ExecuteAdditionalHitsWithoutDamageProfileType` ; et la voie A PROFIL
(`ExecuteAdditionalHitsWithDamageProfileTypeOperation$$Execute` -> nouvelle
`AttackDamageOperation$$Execute` -> nouveau `SetupHitGroup`) RE-LIT la MEME liste de
l'`OngoingAttack`. => l'exclusion traverse TOUTE l'attaque.

⚠ POLARITE -- ce n'est PAS le gate crit (#440). Le crit a un booleen d'attaque qui TOMBE au premier
coup non-crite (`attack[+0x40] &= hitGroup[+0x3c]` en fin d'`Execute`) ; cote block il n'existe
AUCUN booleen equivalent -- `Execute` ne fait qu'un OR COLLANT `attack[+0x39] |= hitGroup[+0x3e]`,
jamais relu comme gate. L'extinction est PAR SOURCE et seulement sur ECHEC : une source qui REUSSIT
sort d'`ApplyRandomBlockDamage` en `return`, AVANT `BlockDamageInfo$$AddFailedBlockId`, donc elle
reste jouable au coup suivant.

L'OBSERVABLE : un roll SAUTE ne consomme pas de tirage. Le port d'AVANT #407 repartait d'un set
VIDE a chaque `_run_hits` (donc a chaque groupe additionnel) -> il RE-TIRAIT la source exclue,
consommait 1 tirage `next_bool` de trop, et DECALAIT tout le flux RNG du groupe. Les valeurs
per-coup du groupe suffisent donc a trancher.

MONTAGE `--case squig` : `orksRuntherd` (passif `SquigHound` -> effet 0x50c, 2 coups PREDEFINED
profil `Physical` PiercingRatio 1) attaque au CONTACT `ultraApothecary`, cible forcee en regime
PERCAGE-DOMINANT (`--armor-target 6000`) ET porteuse d'une source de block de BASE
(`--block-target <chance>,<amount>`), chance BASSE pour que le coup d'arme la fasse ECHOUER.
`--crit 0,0` : aucun crit-roll, donc la seule variable du flux est le block.

Discipline runner : state-file UNIQUE en chemin ABSOLU sous logs/, `--board` explicite, dispose
en fin. ASCII only (cp1252).
"""
from __future__ import annotations

import argparse
import sys

from probe_r6_round_materialize import (_build, _drive_normal, _live_amounts,   # noqa: F401
                                        _mkrpc)

CARRIER = "orksRuntherd"
TARGET = "ultraApothecary"
BOARD = "MC1_67"


def no_thread_variant(port=None):
    """CONTREFACTUEL #407 = le port d'AVANT le fix : `failed_block0` **AVALE**, donc chaque groupe
    additionnel repart d'un etat block VIDE.

    Il APPELLE le port livre, UN GROUPE A LA FOIS, en lui passant `failed_block0=None` : la seule
    chose qui change entre les deux rejeux est donc l'etat block threade -- aucun autre etage n'est
    recopie (ni le max-out, ni les limites, ni la materialisation), ce qui evite qu'une divergence
    vienne d'ailleurs.

    ⚠ Cette substitution AVALE `failed_block0` **EXPRES** : c'est SA variable. Elle ne doit donc
    PAS etre enrolee dans `test_la_substitution_TRANSMET_failed_block0`
    (`tests/test_additional_hits_variant_signatures_offline.py`), qui verifie l'inverse pour les
    contrefactuels dont l'etat block n'est PAS la variable. Sa SIGNATURE, elle, reste sous le
    cliquet `test_toute_substitution_suit_la_signature_du_port`.

    `port` = le port livre a appeler. Capture A LA CONSTRUCTION (defaut = l'import courant) : les
    harnais de rejeu REMPLACENT `additional_hits.execute_additional_hits` pendant le run, donc un
    import a l'APPEL rebouclerait sur la substitution elle-meme (RecursionError mesuree).
    """
    from engine.runner.operations.additional_hits import execute_additional_hits as _default
    _port = port or _default

    def _exec(state, attacker_id, target_id, tgt, thc, groups, mods, def_mods, armor, hit_mult,
              block_sources, shc, spread_pct=20, extra_pierce=0,
              bonus_hit_chance=None, hit_index0=0, crit_allowed0=True, attack_profile=None,
              hit_interceptor=None, failed_block0=None, damaging_done0=False,
              source_ability=None, attacker_mods_for_profile=None):
        # #488-r3 : `attacker_mods_for_profile` (re-collecte des mods ATTAQUANT au profil DU
        # GROUPE) complete la signature du port. Cette variante REIMPLEMENTE le canal et ne fait
        # varier que le chainage de `failed_block` -- accepte et NON LU, comme `source_ability`.
        # #1020-r6 : `source_ability` (`AbilityEntities+0x60`/`+0x98`) fait partie de la
        # signature du port. Cette variante ne fait varier que le chainage de `failed_block` --
        # le parametre est donc accepte et NON LU, comme `damaging_done0` juste avant.
        # MEME ordre que le port : groupes sans profil d'abord (#227), tri STABLE.
        ordered = ([g for g in groups if g.get("profile") is None]
                   + [g for g in groups if g.get("profile") is not None])
        agg = {"groups": 0, "hits": 0, "total": 0, "per_hit": [], "rolls": [], "profiles": [],
               "death": None}
        hit_index, crit_allowed = int(hit_index0), bool(crit_allowed0)
        for g in ordered:
            r = _port(state, attacker_id, target_id, tgt, thc, [g], mods, def_mods, armor,
                      hit_mult, block_sources, shc, spread_pct=spread_pct,
                      extra_pierce=extra_pierce, bonus_hit_chance=bonus_hit_chance,
                      hit_index0=hit_index, crit_allowed0=crit_allowed,
                      attack_profile=attack_profile, hit_interceptor=hit_interceptor,
                      failed_block0=None,          # <-- LA VARIABLE : etat block JAMAIS threade
                      # #963-r2 : `isFirstDamagingHit`. TRANSMIS tel quel -- ce n'est PAS la
                      # variable de ce contrefactuel, et l'avaler ferait diverger un SECOND etage.
                      damaging_done0=damaging_done0)
            if r is None:
                continue
            hit_index, crit_allowed = r["next_hit_index"], r["crit_allowed"]
            for k in ("groups", "hits", "total"):
                agg[k] += r[k]
            for k in ("per_hit", "rolls", "profiles"):
                agg[k] += r[k]
            agg["death"] = agg["death"] or r["death"]
        agg["next_hit_index"], agg["crit_allowed"] = hit_index, crit_allowed
        agg["failed_block"] = set(failed_block0 or ())
        return agg if agg["groups"] else None
    return _exec


def replay_block_scope(dv, ob, snap, board, rng0, caster_id, target_id, moved):
    """Rejoue le MEME coup offline (meme etat, meme flux RNG) sous le PORT LIVRE et sous le
    contrefactuel SANS threading. Rend `{"shipped": [...], "no_thread": [...], "arme": [...]}`."""
    from engine.runner.snapshot import load_state
    from engine.runner.runner import Runner
    from engine.runner.messages import AttackUnitMessage
    from engine.runner.prng import IntBasedMersenneTwister
    from engine.runner.components import set_moved_flag
    from engine.runner.operations import additional_hits as _ah_mod
    from engine.runner.operations.damage_ops import normal as _dnormal
    from engine.runner.operations.damage_ops import ability as _dability

    def _one(impl):
        st = load_state(dv, ob, snap, board=board)
        if moved:
            set_moved_flag(st, caster_id)
        rng = IntBasedMersenneTwister()
        rng.mt = list(rng0["mt"])
        rng.mti = rng0["mti"]
        st.rng = rng
        per_hit: list = []
        arme: list = []
        o_ah = _ah_mod.execute_additional_hits
        o_n, o_a = _dnormal.execute_additional_hits, _dability.execute_additional_hits

        def _rec(*a, **kw):
            out = (impl or o_ah)(*a, **kw)
            if out:
                per_hit.extend(out.get("per_hit") or [])
            return out

        _ah_mod.execute_additional_hits = _rec
        _dnormal.execute_additional_hits = _rec
        _dability.execute_additional_hits = _rec
        try:
            runner = Runner(st).install_default_handlers(20)
            runner.apply(AttackUnitMessage(caster_id, target_id))
            last = getattr(getattr(runner, "damage_handler", None), "last", None)
            if isinstance(last, dict):
                arme.extend(last.get("per_hit") or [])
            return per_hit, arme
        finally:
            _ah_mod.execute_additional_hits = o_ah
            _dnormal.execute_additional_hits = o_n
            _dability.execute_additional_hits = o_a

    ship = _one(None)
    nt = _one(no_thread_variant())
    return {"shipped": ship[0], "no_thread": nt[0], "arme": ship[1]}


def run_case(rpc, seed, block, armor):
    """Un montage complet : build -> drive -> attaque -> rejeu double. Rend un dict de mesure."""
    from engine.entities.pathfinding.board import Board
    rid, sf = _build(seed, CARRIER, TARGET,
                     extra=["--crit", "0,0", "--block-target", block,
                            "--armor-target", str(armor)])
    if rid is None:
        return {"seed": seed, "skip": "build KO"}
    try:
        bg = rpc("boardGraph", {"runnerId": rid}, 60)
        if not (isinstance(bg, dict) and bg.get("tiles")):
            return {"seed": seed, "skip": "boardGraph indispo"}
        board = Board(bg["tiles"], adjacency="native_sym")
        cid, tid, moved = _drive_normal(rpc, rid, board, CARRIER, TARGET)
        if cid is None:
            return {"seed": seed, "skip": "pas de contact"}
        dv = rpc("decisionView", {"runnerId": rid, "allAbilities": True}, 120)
        ob = rpc("observeBattle", {"runnerId": rid}, 60)
        snap = rpc("combatSnapshot", {"runnerId": rid}, 90)
        rng0 = rpc("dumpRng", {"runnerId": rid}, 30)
        if not (isinstance(rng0, dict) and rng0.get("mt")):
            return {"seed": seed, "skip": "dumpRng indispo"}
        cu = next((u for u in (dv.get("units") or []) if u.get("id") == cid), {})
        nrm = next((a for a in (cu.get("abilities") or []) if a.get("kind") == "normal"), None)
        if nrm is None:
            return {"seed": seed, "skip": "pas d'attaque normale"}
        res = rpc("applyAction", {"runnerId": rid, "action": {
            "kind": "ability", "casterId": cid, "targetId": tid,
            "abilityType": nrm["id"]}, "captureEvents": True}, 120)
        if not (isinstance(res, dict) and res.get("ok")):
            return {"seed": seed, "skip": "attaque KO %s" % str(res)[:100]}
        live, dirty = _live_amounts(res, tid)
        off = replay_block_scope(dv, ob, snap, board, rng0, cid, tid, moved)
        return {"seed": seed, "live": live, "dirty": dirty, **off}
    finally:
        try:
            rpc("disposeRunner", {"runnerId": rid}, 30)
        except Exception:
            pass


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--case", default="squig", choices=["squig"])
    ap.add_argument("--seeds", default="12345,314159,88,777,31337")
    ap.add_argument("--block", default="10,5",
                    help="BlockChance,BlockDamage forces sur la cible (chance BASSE = echec quasi "
                         "sur au coup d'arme, donc source EXCLUE pour la suite de l'attaque)")
    ap.add_argument("--armor", type=int, default=6000)
    a = ap.parse_args()
    rpc = _mkrpc()
    n_disc = n_ship = n_nt = 0
    for seed in [s for s in a.seeds.split(",") if s]:
        m = run_case(rpc, seed, a.block, a.armor)
        if m.get("skip"):
            print("[%s] SKIP %s" % (seed, m["skip"]))
            continue
        arme, live = m["arme"], m["live"]
        n = len(arme)
        print("[%s] live=%s arme_off=%s dirty=%s" % (seed, live, arme, m["dirty"]))
        print("      groupe: livre=%s no_thread=%s" % (m["shipped"], m["no_thread"]))
        if live[:n] != arme:
            print("      [!] coups d'ARME desalignes -> mesure NON portante")
            continue
        if len(live) <= n:
            print("      [!] groupe non emis")
            continue
        g_live = live[n:n + len(m["shipped"])]
        # DISCRIMINANT sur la FENETRE du groupe : le tirage de block en trop est consomme APRES le
        # `GetDamage`/resolve du 1er coup, donc c'est le 2e coup qui bouge -- comparer le seul 1er
        # coup rendrait la mesure aveugle (mesure : 0/5 seeds discriminants a l'index 0, 5/5 sur
        # la fenetre).
        disc = m["shipped"][:len(g_live)] != m["no_thread"][:len(g_live)]
        n_disc += int(disc)
        ok_ship = m["shipped"][:len(g_live)] == g_live
        ok_nt = m["no_thread"][:len(g_live)] == g_live
        n_ship += int(ok_ship)
        n_nt += int(ok_nt)
        print("      groupe live=%s | DISCRIMINANT=%s livre_ok=%s no_thread_ok=%s"
              % (g_live, disc, ok_ship, ok_nt))
    print("TOTAL discriminants=%d livre_ok=%d no_thread_ok=%d" % (n_disc, n_ship, n_nt))
    return 0


if __name__ == "__main__":
    sys.exit(main())
