"""R6-b'' -- le `Maybe` after-hit d'un trigger `On(8)` est-il roule sur les coups d'une attaque
d'ABILITY, comme il l'est sur ceux d'une attaque NORMALE ?

QUESTION (binaire). `IdunBattle.Operations.ADamageOperation$$EvaluateAfterHitTriggers` est le
seul emetteur de l'event `On(8)`. Le vecteur ABILITY passe-t-il par lui ?

RE (decompile = verite, gqfc5mff6c) -- chaine LUE, appelant par appelant :

  * `EvaluateAfterHitTriggers` a EXACTEMENT TROIS appelants (xref), tous en
    **UNCONDITIONAL_CALL** et tous en DERNIERE instruction de leur `ExecuteHit` :
      - `IdunBattle.Operations.AttackDamageOperation$$ExecuteHit`   (famille ATTACK)
      - `IdunBattle.Operations.AbilityDamageOperation$$ExecuteHit`  (famille ABILITY)
      - `IdunBattle.Operations.MachineDamageOperation$$ExecuteHit`
    Le vecteur ABILITY du port (`damage_ops/ability.py`) emprunte les DEUX premieres selon
    `is_attack_damage_op` -> le trigger part dans les deux cas. AUCUN gate de famille.
  * l'INDEX passe au trigger est `currentAttack+0x30`.
    `IdunBattle.Operations.AbilityDamageOperation$$ExecuteHits` le passe en 2e argument de son
    `ExecuteHit` (`ExecuteHit(ret, this, *(currentAttack+0x34), *(currentAttack+0x30), ...)`) et
    fait `*(currentAttack+0x30) += 1` apres CHAQUE coup -- mirror inline
    d'`ADamageOperation$$UpdateCurrentAttackAfterHit`, exactement comme
    `AttackDamageOperation$$ExecuteHits`. Il fait AUSSI le `List.AddRange(hitGroup+0x58,
    attacker+0xf0)` (= `UpdateHitGroupAfterHit`), et `AbilityDamageOperation$$Execute` re-boucle
    sur une COPIE de `hitGroup+0x58` -> les coups bonus DEFERES existent aussi cote ABILITY.
  * l'index DEMARRE A 0 POUR CHAQUE CIBLE : les deux factories emballent leur behaviour de degat
    dans un `AttackBehaviour` (`IdunBattleLogic.Entities.DSLBehaviors$$AttackWithAttackDamage` et
    `$$AttackWithAbilityDamage` finissent tous deux par
    `IdunBattle.Entities.Behaviours.AttackBehaviour$$.ctor(caster, targets, <behaviour>, options)`),
    et `IdunBattle.Entities.Behaviours.AttackBehaviour$$Execute` emet
    `Core.Services.OperationProcessor$$StartAttack` (slot 0x3a) avant CHAQUE cible et
    `$$FinishAttack` (slot 0x3b) apres -> un `IdunBattle.Operations.StartAttackOperation$$Execute`
    (= `new OngoingAttack` + Push sur `MatchState+0x60`) par cible.
  * le trigger : `IdunBattleLogic.Entities.Abilities.Triggered.Loki.GetStuckInAbility$$CreateTrigger`
    = `On(8,1) & AmountIsOdd(CurrentHitIndex()) & get_OwnerIsCaster &
    !AmountIsGreater(MinDistance(owner@0x160, target@0x178), Direct(2))` -- AUCUN `IsNormalAttack`,
    AUCUN `CurrentAbilityIs` ;
    `...$$CreateBehaviour` = `Maybe(AddBonusHitsToCurrentHitGroup(..., AbilityOrEffect(0x4d2)),
    GetBonusHitChance())` -> 1 `NextBool(chance)` a chaque passage.

=> REPONSE : OUI. Le port ne roulait ce `Maybe` que sur le vecteur NORMAL.

MONTAGE (`--case dakka`) : `orksKillaKan` (traits Hero/**GetStuckIn**/BigTarget/Explodes/Mechanical)
caste `DakkaDakkaDakka` (1171, `AttackWithAttackDamage` = famille ATTACK, **6 coups** Projectile)
sur une cible ADJACENTE (le gate du trigger est `MinDistance <= 2`, pas l'adjacence, mais
l'adjacence la satisfait sans ambiguite de metrique). 6 coups -> index 0..5 -> **3 index IMPAIRS**
(1, 3, 5) -> jusqu'a 3 tirages `Maybe` et jusqu'a 3 coups bonus DEFERES.

L'ability 1171 n'est PAS au registre `ABILITY_CLASSES` : le probe appelle donc
`AttackDamageOperation.execute_ability_attack` DIRECTEMENT, avec les parametres que sa feuille
`AttackWithAttackDamage` lui passerait (`MinMaxDamage(abilityState)` = minDmg/maxDmg au niveau du
caster, `GetNumHits()` = `Min(nrOfHits + TimesRepaired x extraHits, maxNrOfHits)` = nrOfHits a
TimesRepaired=0, profil `Projectile`, perce du profil + stats). C'est la DECOMPOSITION PAR ETAGE :
on mesure l'etage porte (le vecteur de degat d'ability), pas l'arbre DSL de l'ability -- et le
RATCHET (les coups doivent reproduire le live) refuse tout parametre faux.

TROIS MODELES rejoues sur le MEME etat et le MEME flux RNG :
  * `shipped`  = le port TEL QU'IL EST LIVRE ;
  * `no_maybe` = `bonus_hit_chance` force a None = le port D'AVANT R6-b'' ;
  * `parity`   = `hit_index0` decale de 1 = le `Maybe` roule sur les index PAIRS (modele
                 concurrent : il consomme le MEME nombre de tirages au total mais PAS aux memes
                 rangs -> il refute un ajustement « +k tirages »).

PREUVE COTE JEU, independante du port : un coup bonus GetStuckIn porte le tag live
`Additional_Hit_TriggeredAbility_Source: 1234` = `0x4d2`, le litteral EXACT passe par
`GetStuckInAbility$$CreateBehaviour` -- le voir dans le flux d'une attaque d'ABILITY EST la
reponse au critere, sans passer par le port.

TEMOIN (`--case temoin`) : `admecRuststalker` caste `CordClaw` (1122, 4x DirectDamage melee,
ability REGISTREE -> rejeu par `ActiveAbilityMessage` complet). Porteur SANS trigger after-hit ->
`shipped` et `no_maybe` DOIVENT coincider et reproduire le live : c'est ce qui prouve que le fix
n'ajoute pas un tirage partout.

Discipline runner : state-file UNIQUE en chemin ABSOLU sous logs/, `--board` explicite, dispose en
fin. ASCII only (cp1252).
"""
from __future__ import annotations

import argparse
import sys
from collections import deque

from probe_r6_round_materialize import _build, _mkrpc                      # noqa: F401
from probe_r6bp_after_hit_maybe_groups import live_hits_of_attacker

DAKKA_CARRIER = "orksKillaKan"     # Hero + GetStuckIn + ability OFFENSIVE 6 coups
DAKKA_ABILITY = 1171               # ActiveAbilityType.DakkaDakkaDakka
DAKKA_ABILITY_ID = "DakkaDakkaDakka"
DAKKA_TARGET = "ultraApothecary"   # ni BigTarget ni Vehicle ; survit au regime percage-dominant
CC_CARRIER = "admecRuststalker"    # TEMOIN : aucun trigger after-hit
CC_ABILITY = 1122                  # CordClaw (4x DirectDamage melee), REGISTREE
CC_TARGET = "necroWarden"


# --------------------------------------------------------------------------- variantes offline


def _patch_run_hits(mutate):
    """Installe un wrapper sur `AttackDamageOperation._run_hits` qui MUTE ses kwargs, et rend un
    callable de restauration. `mutate(kwargs) -> kwargs`. `None` = aucun patch (port LIVRE).

    `_run_hits` est HERITE de `_DamageHitsMixin` : on retire l'attribut pose sur la sous-classe a
    la restauration (le remettre en dur figerait la resolution par MRO)."""
    from engine.runner.operations.damage import AttackDamageOperation
    if mutate is None:
        return lambda: None
    orig = AttackDamageOperation._run_hits
    owned = "_run_hits" in AttackDamageOperation.__dict__

    def _wrapped(*a, **kw):
        return orig(*a, **mutate(dict(kw)))

    AttackDamageOperation._run_hits = staticmethod(_wrapped)

    def _restore():
        if owned:
            AttackDamageOperation._run_hits = staticmethod(orig)
        else:
            del AttackDamageOperation._run_hits
    return _restore


def _mut_no_maybe(kw):
    """CONTREFACTUEL « le port d'avant R6-b'' » : le vecteur ability ne roule aucun `Maybe`."""
    kw["bonus_hit_chance"] = None
    return kw


def _mut_parity(kw):
    """MODELE CONCURRENT : meme canal, index DECALE de 1 -> le `Maybe` roule sur les index PAIRS.
    Meme nombre de tirages a l'echelle de l'attaque, rangs differents."""
    if kw.get("bonus_hit_chance") is not None:
        kw["hit_index0"] = int(kw.get("hit_index0") or 0) + 1
    return kw


def _mut_always(kw):
    """MODELE CONCURRENT : le `Maybe` roule SANS le gate de distance du trigger
    (`!AmountIsGreater(MinDistance(owner, target), Direct(2))`). Rend le montage `far`
    (cible a >2 hex) DISCRIMINANT -- sinon `shipped` et `no_maybe` y coincident par
    construction et la mesure ne prouverait rien."""
    if kw.get("bonus_hit_chance") is None:
        from engine.entities.effects.magnitude import trait_var
        kw["bonus_hit_chance"] = int(trait_var("GetStuckIn", "getStuckInChance") or 0) or None
    return kw


VARIANTS = (("shipped", None), ("no_maybe", _mut_no_maybe), ("parity", _mut_parity),
            ("always", _mut_always))


# --------------------------------------------------------------------------- rejeu offline


def _load(dv, ob, snap, board, rng0, caster_id, moved):
    from engine.runner.snapshot import load_state
    from engine.runner.prng import IntBasedMersenneTwister
    from engine.runner.components import set_moved_flag
    st = load_state(dv, ob, snap, board=board)
    if moved:
        set_moved_flag(st, caster_id)
    rng = IntBasedMersenneTwister()
    rng.mt = list(rng0["mt"])
    rng.mti = rng0["mti"]
    st.rng = rng
    return st


def _dakka_params(st, cid, tid):
    """Parametres que la feuille `AttackWithAttackDamage` de `DakkaDakkaDakkaAbility$$
    ExecuteBehaviour` passe au vecteur de degat (LUS au decompile) :
      minmax  = `AActiveAbility$$MinMaxDamage(abilityState)` -> variables minDmg/maxDmg ;
      hits    = `DakkaDakkaDakkaAbility$$GetNumHits` = `Min(Sum(Direct(nrOfHits),
                Multiply(TimesRepaired(owner), Direct(extraHits))), ConfigConst(maxNrOfHits))`
                -- `TimesRepaired` = 0 hors reparation (non capte offline, cf. `dsl/base.py`) ;
      profil  = `AbilityConfiguration$$GetDamageProfile()` = constante `damageProfile` ;
      perce   = profil.PiercingRatio + ExtraPierce(+Ranged) du caster + EffectBonus."""
    from engine.runner.components import StatsComponent
    from engine.runner.abilities.base import profile_pierce, ability_pierce_effect_bonus
    from engine.entities.effects.magnitude import ability_var
    import gameconfig as GC
    e = st.get_entity(cid)
    sc = e.get_component(StatsComponent) if e is not None else None
    ctx = getattr(sc, "ctx", None)
    if ctx is None:
        return None
    lvl = ctx.active_ability_level
    mult = int(getattr(ctx, "ability_variables_multiplier", 100) or 100)
    cst = (GC.ability(DAKKA_ABILITY_ID) or {}).get("constants") or {}
    profile = cst.get("damageProfile")
    hits = int(ability_var(DAKKA_ABILITY_ID, "nrOfHits", is_constant=True) or 0)
    pb = ability_pierce_effect_bonus(st, cid, tid, DAKKA_ABILITY, is_ranged=True)
    return {"base_min": int(ability_var(DAKKA_ABILITY_ID, "minDmg", lvl, multiplier_pct=mult) or 0),
            "base_max": int(ability_var(DAKKA_ABILITY_ID, "maxDmg", lvl, multiplier_pct=mult) or 0),
            "hits": hits, "profile": profile, "level": lvl, "mult": mult,
            "pierce": profile_pierce(ctx, profile, ranged=True, effect_bonus=pb)}


def _replay_dakka(dv, ob, snap, board, rng0, cid, tid, moved):
    """Rejoue le MEME cast offline sous les trois modeles. Rend `{nom: per_hit}` + `params`."""
    from engine.runner.operations.damage import AttackDamageOperation
    out, params = {}, None
    for name, mut in VARIANTS:
        st = _load(dv, ob, snap, board, rng0, cid, moved)
        p = _dakka_params(st, cid, tid)
        if p is None:
            return None, None
        params = p
        restore = _patch_run_hits(mut)
        try:
            res = AttackDamageOperation.execute_ability_attack(
                st, cid, tid, p["base_min"], p["base_max"], p["pierce"], p["hits"],
                damage_profile=p["profile"], is_melee=False, ability_type=DAKKA_ABILITY,
                is_attack_damage_op=True)
        finally:
            restore()
        out[name] = list((res or {}).get("per_hit") or [])
    return out, params


def _replay_registered(dv, ob, snap, board, rng0, cid, tid, ability_id, moved):
    """Rejeu COMPLET (`ActiveAbilityMessage`) d'une ability REGISTREE, sous les trois modeles ;
    les per-coup sont captes en enveloppant `execute_ability_attack` (recorder)."""
    from engine.runner.runner import Runner
    from engine.runner.messages import ActiveAbilityMessage
    from engine.runner.operations.damage import AttackDamageOperation
    out = {}
    for name, mut in VARIANTS:
        st = _load(dv, ob, snap, board, rng0, cid, moved)
        per: list = []
        orig = AttackDamageOperation.execute_ability_attack
        owned = "execute_ability_attack" in AttackDamageOperation.__dict__

        def _rec(*a, **kw):
            res = orig(*a, **kw)
            if res:
                per.extend(res.get("per_hit") or [])
            return res

        AttackDamageOperation.execute_ability_attack = staticmethod(_rec)
        restore = _patch_run_hits(mut)
        try:
            Runner(st).install_default_handlers(20).apply(
                ActiveAbilityMessage(caster_id=cid, target_id=tid, ability_type=ability_id))
        finally:
            restore()
            if owned:
                AttackDamageOperation.execute_ability_attack = staticmethod(orig)
            else:
                del AttackDamageOperation.execute_ability_attack
        out[name] = per
    return out


# --------------------------------------------------------------------------- pilotage live


def _ring_dist(board, src):
    """Distance HEX (anneaux du graphe d'adjacence, obstacles IGNORES) depuis `src` -- c'est la
    metrique de `MinDistance` natif, pas la distance de PARCOURS."""
    d, q = {src: 0}, deque([src])
    while q:
        x = q.popleft()
        for n in board.neighbours(x):
            if n not in d:
                d[n] = d[x] + 1
                q.append(n)
    return d


def _drive_ability(rpc, rid, board, caster_vis, target_vis, ability_id, want, max_turns=25):
    """DEPLACE le caster jusqu'a une case qui satisfait `want(hexdist, cheby)` ET d'ou l'ability
    est LEGALE sur la cible (jamais « bloque par la geometrie de spawn »).

    `hexdist` = anneaux du graphe (metrique de `MinDistance` natif) ; `cheby` = le PROXY
    qu'utilise `getstuckin_combat_chance` cote port. On exige les DEUX pour que le montage porte
    sur le gate lui-meme et non sur l'ecart entre les deux metriques (gap pre-existant, hors sujet).
    Rend `(caster_id, target_id, moved)` ou `(None, None, 0)`."""
    my, moves = None, 0
    for _ in range(max_turns):
        dv = rpc("decisionView", {"runnerId": rid, "allAbilities": True}, 120)
        units = dv.get("units") or []
        cst = next((u for u in units if u.get("visualId") == caster_vis and u.get("alive")), None)
        tg = next((u for u in units if u.get("visualId") == target_vis and u.get("alive")), None)
        if cst is None or tg is None:
            return None, None, 0
        if my is None:
            my = cst.get("owner")
        if dv.get("currentPlayer") != my:
            rpc("applyAction", {"runnerId": rid, "action": {"kind": "endturn"}}, 60)
            continue
        cpos = (cst["pos"]["col"], cst["pos"]["row"])
        tpos = (tg["pos"]["col"], tg["pos"]["row"])
        ctile, ttile = board.id_at(*cpos), board.id_at(*tpos)
        ring = _ring_dist(board, ttile)
        cheby = max(abs(cpos[0] - tpos[0]), abs(cpos[1] - tpos[1]))
        if want(ring.get(ctile, 99), cheby):
            at = rpc("abilityTargets", {"runnerId": rid, "unitId": cst["id"],
                                        "abilityType": ability_id}, 90)
            ab = next((a for a in ((at.get("units") or [{}])[0].get("abilities") or [])
                       if a.get("abilityId") == ability_id), {})
            if tg["id"] in [x.get("targetId") for x in (ab.get("fromHere") or [])]:
                return cst["id"], tg["id"], moves
        # pas encore en place -> se rapprocher (BFS de PARCOURS, walkable)
        walk, q = {ttile: 0}, deque([ttile])
        while q:
            x = q.popleft()
            for n in board.neighbours(x):
                if n not in walk and board.walkable(n):
                    walk[n] = walk[x] + 1
                    q.append(n)
        mt = rpc("aiMovableTiles", {"runnerId": rid, "side": "friendly"}, 60)
        cmt = next((x for x in (mt.get("units") or []) if x.get("unitId") == cst["id"]), None)
        reach = {board.id_at(t["col"], t["row"]): (t["col"], t["row"])
                 for t in ((cmt or {}).get("tiles") or [])}
        good = sorted((t, cr) for t, cr in reach.items()
                      if t != ctile
                      and want(ring.get(t, 99), max(abs(cr[0] - tpos[0]), abs(cr[1] - tpos[1]))))
        if good:
            _t, (col, row) = good[0]
            rpc("applyAction", {"runnerId": rid, "action": {
                "kind": "move", "unitId": cst["id"], "to": {"col": col, "row": row}}}, 60)
            moves += 1
            continue                       # re-boucle : on re-verifie la place ET la legalite
        pool = [t for t in reach if t in walk]
        if not pool:
            rpc("applyAction", {"runnerId": rid, "action": {"kind": "endturn"}}, 60)
            continue
        best = min(pool, key=lambda t: walk[t])
        col, row = reach[best]
        rpc("applyAction", {"runnerId": rid, "action": {
            "kind": "move", "unitId": cst["id"], "to": {"col": col, "row": row}}}, 60)
        moves += 1
        if walk[best] > 1:
            rpc("applyAction", {"runnerId": rid, "action": {"kind": "endturn"}}, 60)
    return None, None, 0


def _want_close(hexdist, cheby):
    """Cible ADJACENTE : les deux metriques valent 1 -> gate `MinDistance <= 2` SATISFAIT."""
    return hexdist == 1 and cheby == 1


def _want_far(hexdist, cheby):
    """Cible a EXACTEMENT 3 hex (portee max de l'ability) et cheby >= 3 -> gate
    `MinDistance <= 2` FERME pour les DEUX metriques, tout en restant a portee de cast.
    Bande FERMEE (== 3, pas >= 3) : sinon le pilote se declarerait « en place » des le spawn,
    ou l'ability serait hors portee."""
    return hexdist == 3 and cheby >= 3


def _confront(label, seed, live, srcs, off, params=None):
    """Imprime la confrontation ; rend (shipped_ok, no_maybe_ok, parity_ok, discriminant, n_bonus).

    `live` est FILTRE sur l'`Attacker_Id` du porteur -> la comparaison est EXACTE EN NOMBRE."""
    ship = off["shipped"]
    n_bonus = sum(1 for s in srcs if s and s.startswith("trig:"))
    print("[%s] seed %-7s live=%s" % (label, seed, live))
    print("        sources =%s   (coups bonus GetStuckIn live: %d)" % (srcs, n_bonus))
    if params:
        print("        params  = bornes [%d,%d] hits=%d profil=%s perce=%d lvl=%s mult=%s"
              % (params["base_min"], params["base_max"], params["hits"], params["profile"],
                 params["pierce"], params["level"], params["mult"]))
    for name, _m in VARIANTS:
        print("        %-9s=%s" % (name, off[name]))
    ok = tuple(int(bool(off[n]) and off[n] == live) for n, _m in VARIANTS)
    disc = int(any(off[n] != ship for n, _m in VARIANTS))
    print("        -> %s  (discriminant: %s)"
          % ("  ".join("%s %s" % (n, "OK" if ok[i] else "MISMATCH")
                       for i, (n, _m) in enumerate(VARIANTS)), "oui" if disc else "NON"))
    return ok + (disc, n_bonus)


# --------------------------------------------------------------------------- montages


def _run_dakka(rpc, seed, armor, rank, target, want=_want_close, label="dakka"):
    from engine.entities.pathfinding.board import Board
    rid, sf = _build(seed, DAKKA_CARRIER, target,
                     extra=["--crit", "0,0", "--block-target", "0,0",
                            "--armor-target", str(armor)], rank=rank)
    if rid is None:
        return None
    try:
        bg = rpc("boardGraph", {"runnerId": rid}, 60)
        board = Board(bg["tiles"], adjacency="native_sym")
        cid, tid, moved = _drive_ability(rpc, rid, board, DAKKA_CARRIER, target,
                                         DAKKA_ABILITY, want)
        if cid is None:
            print("[%s] seed %s: drive KO" % (label, seed))
            return None
        dv = rpc("decisionView", {"runnerId": rid, "allAbilities": True}, 120)
        ob = rpc("observeBattle", {"runnerId": rid}, 60)
        snap = rpc("combatSnapshot", {"runnerId": rid}, 90)
        rng0 = rpc("dumpRng", {"runnerId": rid}, 30)
        res = rpc("applyAction", {"runnerId": rid, "action": {
            "kind": "ability", "casterId": cid, "targetId": tid,
            "abilityType": DAKKA_ABILITY}, "captureEvents": True}, 120)
        if not (isinstance(res, dict) and res.get("ok")):
            print("[%s] seed %s: cast KO %s" % (label, seed, str(res)[:140]))
            return None
        live, dirty, srcs = live_hits_of_attacker(res, tid, cid)
        if dirty:
            print("[%s] seed %s: coup SALE (crit/block/evade) -- ignore" % (label, seed))
            return None
        off, params = _replay_dakka(dv, ob, snap, board, rng0, cid, tid, moved)
        if off is None:
            print("[%s] seed %s: params offline indisponibles" % (label, seed))
            return None
        return _confront(label, seed, live, srcs, off, params)
    finally:
        try:
            rpc("disposeRunner", {"runnerId": rid}, 20)
        except Exception:
            pass
        try:
            sf.unlink()
        except Exception:
            pass


def _run_temoin(rpc, seed, armor, rank):
    from engine.entities.pathfinding.board import Board
    rid, sf = _build(seed, CC_CARRIER, CC_TARGET,
                     extra=["--crit", "0,0", "--block-target", "0,0",
                            "--armor-target", str(armor)], rank=rank)
    if rid is None:
        return None
    try:
        bg = rpc("boardGraph", {"runnerId": rid}, 60)
        board = Board(bg["tiles"], adjacency="native_sym")
        cid, tid, moved = _drive_ability(rpc, rid, board, CC_CARRIER, CC_TARGET, CC_ABILITY,
                                         _want_close)
        if cid is None:
            print("[temoin] seed %s: drive KO" % seed)
            return None
        dv = rpc("decisionView", {"runnerId": rid, "allAbilities": True}, 120)
        ob = rpc("observeBattle", {"runnerId": rid}, 60)
        snap = rpc("combatSnapshot", {"runnerId": rid}, 90)
        rng0 = rpc("dumpRng", {"runnerId": rid}, 30)
        res = rpc("applyAction", {"runnerId": rid, "action": {
            "kind": "ability", "casterId": cid, "targetId": tid,
            "abilityType": CC_ABILITY}, "captureEvents": True}, 120)
        if not (isinstance(res, dict) and res.get("ok")):
            print("[temoin] seed %s: cast KO %s" % (seed, str(res)[:140]))
            return None
        live, dirty, srcs = live_hits_of_attacker(res, tid, cid)
        if dirty:
            print("[temoin] seed %s: coup SALE -- ignore" % seed)
            return None
        off = _replay_registered(dv, ob, snap, board, rng0, cid, tid, CC_ABILITY, moved)
        return _confront("temoin", seed, live, srcs, off)
    finally:
        try:
            rpc("disposeRunner", {"runnerId": rid}, 20)
        except Exception:
            pass
        try:
            sf.unlink()
        except Exception:
            pass


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--case", default="dakka", choices=("dakka", "far", "temoin"))
    ap.add_argument("--seeds", default="777,31337,12345,314159,88")
    ap.add_argument("--target", default=DAKKA_TARGET)
    ap.add_argument("--rank", type=int, default=None)
    ap.add_argument("--armor", type=int, default=6000)
    args = ap.parse_args()
    rpc = _mkrpc()
    n = len(VARIANTS)
    tot, rows, bonus_hist = [0] * (n + 1), 0, {}
    for seed in [s for s in args.seeds.split(",") if s]:
        if args.case == "temoin":
            r = _run_temoin(rpc, seed, args.armor, args.rank)
        else:
            want = _want_close if args.case == "dakka" else _want_far
            r = _run_dakka(rpc, seed, args.armor, args.rank, args.target, want=want,
                           label=args.case)
        if r is None:
            continue
        tot = [a + b for a, b in zip(tot, r[:n + 1])]
        bonus_hist[r[n + 1]] = bonus_hist.get(r[n + 1], 0) + 1
        rows += 1
    print()
    print("[%s] BILAN %d montages : %s, montages discriminants %d/%d"
          % (args.case, rows,
             ", ".join("%s %d/%d" % (nm, tot[i], rows) for i, (nm, _m) in enumerate(VARIANTS)),
             tot[n], rows))
    print("[%s] regimes (coups bonus GetStuckIn observes LIVE) : %s"
          % (args.case, dict(sorted(bonus_hist.items()))))
    return 0


if __name__ == "__main__":
    sys.exit(main())
