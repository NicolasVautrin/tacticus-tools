"""#159 (a) -- BORNES COMBAT du canal COUPS ADDITIONNELS (#179) pour un descripteur "amount".

QUESTION (binaire) : a tirage CALE (meme etat PRNG), la sequence de consommation du canal #179
offline est-elle celle du natif -- meme nombre de tirages, meme ordre, MEMES BORNES ?

RE (decompile = verite, gqfc5mff6c). Le descripteur natif porte DEUX noeuds de degat, et
`IdunBattle.Entities.Effects.BaseEffect$$AdditionalHits(this, entities, useDisplay)` choisit :

    if (!d.condition.ShouldTrigger(entities))  return default          # slot 5
    count  = d.countNode.Calculate(entities)                           # +0x18, slot 1
    amount = d.minNode.<slot 4>(entities)                              # +0x10  (noeud DISPLAY)
    min = max = amount
    if (!useDisplay) {                                                 # <- FACE COMBAT
        min = d.amountNode.<slot 2>(entities)                          # +0x08  (noeud ROLL)
        max = d.amountNode.<slot 3>(entities)
    }
    return AdditionalHitsInfo{ MinMax = MinMaxDamage(min, max), amount, count, profile, ... }

et `IdunBattle.Operations.AdditionalHitsFromEffects$$GetAdditionalHitsData` bat l'AttackData de
chaque groupe par `IdunBattle.Core.HitDamage$$.ctor(min, Nullable(max))` DEPUIS CE MinMaxDamage.

Qui passe quoi pour `useDisplay` :
  * COMBAT -- `IdunBattle.Operations.AttackDamageOperation$$ExecuteAdditionalHitsWithoutDamage
    ProfileType` appelle `...AdditionalHitsFromEffects$$GetAdditionalHitsFromEffectsInternal` avec
    l'octet EXPLICITEMENT MIS A ZERO (`in_stack & 0xffffff00`) -> **useDisplay = FALSE**, donc
    bornes = le noeud ROLL ;
  * PREDICTION -- `IdunBattle.Entities.Abilities.AActiveAbility$$GetAdditionalHitsFromEffects
    ForPrediction` -> `...$$GetAdditionalHitsFromEffects` -> cellule DEGENEREE (amount, amount),
    que le pipeline de prediction etale ensuite (`DamageCalculations$$CalculateDamageSpread`).

Pour `FleshmetalGuns` les deux noeuds sont lus verbatim dans
`IdunBattle.Entities.Effects.Loki.BaseFleshmetalGunsEffect$$CreateAdditionalHits` :

    rollNode    = BaseEffect$$GetMinMaxDamage(this, 0, keyMin, keyMax)
    displayNode = BaseEffect$$GetMinMaxDamage(this, 1, keyMin, keyMax)

et `IdunBattle.Entities.Effects.BaseEffect$$GetMinMaxDamage(this, useAverage, keyMin, keyMax)` :

    a = ConfigVar(keyMin, AbilityStateFromEffect(...)) ; b = ConfigVar(keyMax, ...)
    return useAverage ? DSLFactory.Average(a, b) : DSLFactory.RandomAmount(a, b)

=> bornes COMBAT = **[minDmg_sfx, maxDmg_sfx]** (x multiplier de rarete), PAS `Average +-20 %`.

MONTAGE DISCRIMINANT -- le porteur est `blackObliterator` (Volk, passif `FleshmetalGuns`), et
seule la variante **WarpHail** discrimine : ses deux bornes ne sont PAS une paire +-20 % exacte
autour de leur moyenne (les deux autres le sont, et les deux modeles y coincident au round pres).

    variante           natif [min,max]   port `amount` -> +-20 %   discriminant ?
    Melta    (mult180) [997,1495]        [997,1495]                NON
    Flame    (mult180) [797,1197]        [798,1196]                marginal (+-1)
    WarpHail (mult180) [698,1096]        [718,1076]                OUI (largeur 399 vs 359)

La rotation est `UnitTurnsStarted(Self) mod 3` (`FleshMetalGunsAbility$$CreateBehaviour`) :
1 -> Melta, 2 -> Flame, **0 -> WarpHail**. Le probe endturn jusqu'a ce que l'effet 1221 soit
porte par Volk.

Le meme montage MESURE aussi #159 (b) : `LetTheGalaxyBurnAbility$$CreateTrigger` roule son
`Maybe(33)` au `On(PreAttack=5)` de CHAQUE attaque de Volk (il porte le trait 1058), et son
verdict vaut +-1 COUP D'ARME. A flux RNG cale, le nombre de coups d'arme natif vs offline EST
le verdict du `Maybe`.

Discipline runner : state-file UNIQUE absolu sous logs/, `--board` explicite, dispose en fin.
ASCII only (cp1252).

CLI (depuis scripts/python) :
  python probe_159_ah_bounds.py --seeds 777,31337,12345
  python probe_159_ah_bounds.py --seeds 777 --variant Melta      # temoin NON discriminant
"""
from __future__ import annotations

import argparse
import json
import sys

from probe_r6_round_materialize import _build, _live_amounts, _mkrpc   # noqa: F401

CARRIER = "blackObliterator"          # Volk -- passif FleshmetalGuns + trait LetTheGalaxyBurn (1058)
DEFAULT_TARGET = "necroWarden"        # temoin NEUTRE : aucun trait mordant le canal de coups
BOARD = "MC1_67"
# EffectType des 3 variantes du cycle (cf. `FLESHMETAL_CYCLE`, triggers/loki/fleshmetal_guns.py)
CYCLE = {"Melta": 1067, "Flame": 1212, "WarpHail": 1221}


def _eff_ids(unit):
    return {e.get("effectType") for e in (unit or {}).get("effects") or ()}


def _unit(dv, vis):
    return next((u for u in (dv.get("units") or []) if u.get("visualId") == vis and u.get("alive")),
                None)


def _pos(u):
    p = (u or {}).get("pos") or {}
    return (p.get("col"), p.get("row")) if p.get("col") is not None else None


def _drive_ranged(rpc, rid, want_eff, target_vis, max_turns=40):
    """Amene Volk a un tour ou (a) c'est SON tour, (b) il porte la variante VOULUE du cycle,
    (c) son attaque normale est LEGALE depuis sa position COURANTE sur la cible.

    Volk n'est JAMAIS deplace quand c'est evitable (case-101 #6 : `applyAction move` pose
    `UnitFlag.Moved`, que le natif lit pour desarmer `HeavyWeapon_ExtraDmg` -- x1.25 de mesure).
    S'il faut se rapprocher, on le fait et on rend `moved=1` pour que le rejeu offline pose le
    meme flag. On garde une distance >= 2 : le trigger du canal est `IsRangedAttack`."""
    from collections import deque
    import hexgeo
    my, moved = None, 0
    for _ in range(max_turns):
        dv = rpc("decisionView", {"runnerId": rid, "allAbilities": True}, 120)
        cst = _unit(dv, CARRIER)
        tg = _unit(dv, target_vis)
        if cst is None or tg is None:
            return None, None, 0, "caster/cible absent"
        if my is None:
            my = cst.get("owner")
        if dv.get("currentPlayer") != my:
            rpc("applyAction", {"runnerId": rid, "action": {"kind": "endturn"}}, 60)
            moved = 0          # `UnitFlag.Moved` est PER-TOUR : un move d'un tour precedent ne
            continue           # doit PAS etre rejoue offline (sinon HeavyWeapon_ExtraDmg x1.25
        # de mesure -- c'est le defaut qui a fait echouer la 1re passe).
        nrm = next((a for a in (cst.get("abilities") or []) if a.get("kind") == "normal"), None)
        if nrm is None:
            return None, None, 0, "attaque normale introuvable"
        cpos, tpos = _pos(cst), _pos(tg)
        at = rpc("abilityTargets", {"runnerId": rid, "unitId": cst["id"],
                                    "abilityType": nrm["id"]}, 120)
        ab = next((x for u in (at.get("units") or []) for x in (u.get("abilities") or [])
                   if x.get("abilityId") == nrm["id"]), {})
        here = [x.get("targetId") for x in (ab.get("fromHere") or [])]
        in_range = tg["id"] in here and hexgeo.distance(cpos, tpos) >= 2
        if in_range and CYCLE[want_eff] in _eff_ids(cst):
            return cst["id"], tg["id"], moved, nrm["id"]
        if in_range:                       # bonne portee, mauvaise phase du cycle -> laisser tourner
            rpc("applyAction", {"runnerId": rid, "action": {"kind": "endturn"}}, 60)
            moved = 0
            continue
        # se rapprocher SANS aller au contact (on veut une attaque RANGED)
        ttile = board_id(rpc, rid, tpos)
        dist, q = {ttile: 0}, deque([ttile])
        brd = _board(rpc, rid)
        while q:
            x = q.popleft()
            for n in brd.neighbours(x):
                if n not in dist and brd.walkable(n):
                    dist[n] = dist[x] + 1
                    q.append(n)
        mt = rpc("aiMovableTiles", {"runnerId": rid, "side": "friendly"}, 60)
        cmt = next((x for x in (mt.get("units") or []) if x.get("unitId") == cst["id"]), None)
        reach = {brd.id_at(t["col"], t["row"]): (t["col"], t["row"])
                 for t in ((cmt or {}).get("tiles") or [])}
        pool = [t for t in reach if dist.get(t, 99) >= 2]
        if not pool:
            rpc("applyAction", {"runnerId": rid, "action": {"kind": "endturn"}}, 60)
            continue
        col, row = reach[min(pool, key=lambda t: dist[t])]
        rpc("applyAction", {"runnerId": rid, "action": {
            "kind": "move", "unitId": cst["id"], "to": {"col": col, "row": row}}}, 60)
        moved += 1
    return None, None, 0, "cycle/portee non atteints en %d tours" % max_turns


def _genrand_steps(before, after, limit=400):
    """Nombre de `genrand_int32` consommes par le NATIF entre deux `dumpRng` : on re-simule le
    Mersenne Twister depuis `before` et on compte les pas jusqu'a retomber sur `after`. Le nombre
    de PAS EST le nombre de tirages (methode de `case-o4a`). -1 = non retrouve dans `limit` pas."""
    from engine.runner.prng import IntBasedMersenneTwister
    if not (isinstance(before, dict) and before.get("mt")
            and isinstance(after, dict) and after.get("mt")):
        return -1
    m = IntBasedMersenneTwister()
    m.mt = list(before["mt"])
    m.mti = before["mti"]
    tgt = (list(after["mt"]), after["mti"])
    for k in range(limit + 1):
        if (m.mt, m.mti) == tgt:
            return k
        m.genrand_int32()
    return -1


_BOARD_CACHE = {}


def _board(rpc, rid):
    if rid not in _BOARD_CACHE:
        from engine.entities.pathfinding.board import Board
        bg = rpc("boardGraph", {"runnerId": rid}, 60)
        _BOARD_CACHE[rid] = Board(bg["tiles"], adjacency="native_sym")
    return _BOARD_CACHE[rid]


def board_id(rpc, rid, pos):
    return _board(rpc, rid).id_at(pos[0], pos[1])


def _bounds_variant(mode):
    """Fabrique une implementation de `_BaseFleshmetalGunsEffect.additional_hit_groups` pour un
    MODELE de bornes donne -- c'est le seul etage qui varie entre les rejeux :

      `display` : le descripteur ne porte QUE le noeud DISPLAY (`amount` = Average), que
                  `execute_additional_hits` etale a +-20 %. C'est le port HISTORIQUE.
      `roll`    : le descripteur porte AUSSI les bornes du noeud ROLL
                  (`RandomAmount(ConfigVar(keyMin), ConfigVar(keyMax))`) = la lecture native de
                  `BaseEffect$$AdditionalHits` en `useDisplay = false` (cf. en-tete)."""
    from engine.entities.effects.magnitude import ability_var

    def _groups(self, ctx=None):
        if not ctx or ctx.get("is_melee") is not False:
            return None
        lvl = self.ability_level if self.ability_level is not None else self.level
        sfx = self._SUFFIX
        mn = ability_var("FleshmetalGuns", "minDmg" + sfx, lvl,
                         multiplier_pct=self.ability_variables_multiplier)
        mx = ability_var("FleshmetalGuns", "maxDmg" + sfx, lvl,
                         multiplier_pct=self.ability_variables_multiplier)
        count = ability_var("FleshmetalGuns", "nrOfHits" + sfx, is_constant=True)
        if mn is None or mx is None or not count or count <= 0:
            return None
        try:
            import gameconfig as _GC
            profile = ((_GC.ability("FleshmetalGuns") or {}).get("constants") or {}) \
                .get("damageProfile" + sfx) or self._FALLBACK_PROFILE
        except Exception:
            profile = self._FALLBACK_PROFILE
        g = {"count": int(count), "amount": (int(mn) + int(mx)) / 2, "profile": profile}
        if mode == "roll":
            g["min"], g["max"] = int(mn), int(mx)
        return [g]
    return _groups


def _replay(dv, ob, snap, board, rng0, cid, tid, moved):
    """Rejoue la MEME attaque normale OFFLINE sur le MEME flux RNG sous deux modeles de BORNES
    du canal #179 -- le port LIVRE et le contrefactuel `display` (amount +-20 %). Rend aussi les
    coups d'ARME (verdict du `Maybe` LetTheGalaxyBurn) et les bornes effectivement utilisees."""
    from engine.runner.snapshot import load_state
    from engine.runner.runner import Runner
    from engine.runner.messages import AttackUnitMessage
    from engine.runner.prng import IntBasedMersenneTwister
    from engine.runner.components import set_moved_flag
    from engine.runner.operations import additional_hits as _ah_mod
    from engine.runner.operations.damage_ops import normal as _dnormal
    from engine.runner.operations.damage_ops import ability as _dability
    from engine.entities.effects.loki.hits import _BaseFleshmetalGunsEffect

    def _one(groups_impl):
        st = load_state(dv, ob, snap, board=board)
        if moved:
            set_moved_flag(st, cid)
        # compteur de `genrand_int32` OFFLINE -- meme unite que `_genrand_steps` cote natif, pour
        # confronter la CONSOMMATION et pas seulement les valeurs (decomposition par etage).
        cnt = [0]

        class _Counting(IntBasedMersenneTwister):
            __slots__ = ()

            def genrand_int32(self):
                cnt[0] += 1
                return IntBasedMersenneTwister.genrand_int32(self)

        rng = _Counting()
        rng.mt = list(rng0["mt"])
        rng.mti = rng0["mti"]
        st.rng = rng
        grp, bounds = [], []
        o_ah = _ah_mod.execute_additional_hits
        o_n, o_a = _dnormal.execute_additional_hits, _dability.execute_additional_hits
        o_g = _BaseFleshmetalGunsEffect.additional_hit_groups

        def _rec(*a, **kw):
            for g in (a[5] if len(a) > 5 else kw.get("groups")) or ():
                bounds.append({k: g.get(k) for k in ("count", "min", "max", "amount", "profile")})
            out = o_ah(*a, **kw)
            if out:
                grp.extend(out.get("per_hit") or [])
            return out

        _ah_mod.execute_additional_hits = _rec
        _dnormal.execute_additional_hits = _rec
        _dability.execute_additional_hits = _rec
        if groups_impl is not None:
            _BaseFleshmetalGunsEffect.additional_hit_groups = groups_impl
        # CELLULE de l'ARME effectivement roulee (reduce-then-roll -> bornes DEJA reduites) :
        # sert a tester si le coup natif surnumeraire est un tirage DANS cette cellule ou autre chose.
        from engine.runner.operations.damage import AttackDamageOperation as _ADO
        o_rh = _ADO._run_hits
        cells = []

        def _rh(rng_, hit_nc, hit_cr, *a, **kw):
            cells.append((getattr(hit_nc, "min", None), getattr(hit_nc, "max", None)))
            return o_rh(rng_, hit_nc, hit_cr, *a, **kw)
        _ADO._run_hits = staticmethod(_rh)
        try:
            runner = Runner(st).install_default_handlers(20)
            runner.apply(AttackUnitMessage(cid, tid))
            last = getattr(getattr(runner, "damage_handler", None), "last", None)
            arme = list((last or {}).get("per_hit") or []) if isinstance(last, dict) else []
            return arme, grp, bounds, cnt[0], cells
        finally:
            _ah_mod.execute_additional_hits = o_ah
            _dnormal.execute_additional_hits = o_n
            _dability.execute_additional_hits = o_a
            _BaseFleshmetalGunsEffect.additional_hit_groups = o_g
            _ADO._run_hits = staticmethod(o_rh)

    return {"shipped": _one(None),
            "display": _one(_bounds_variant("display")),
            "roll": _one(_bounds_variant("roll"))}


def _run_seed(rpc, seed, args):
    rid, sf = _build(seed, CARRIER, args.target,
                     extra=["--crit", "0,0", "--block-target", "0,0",
                            "--hp-target", str(args.hp)], rank=args.rank)
    if rid is None:
        return None
    try:
        cid, tid, moved, nrm_or_err = _drive_ranged(rpc, rid, args.variant, args.target,
                                                    max_turns=args.max_turns)
        if cid is None:
            print("[159a] seed %s: drive KO -- %s" % (seed, nrm_or_err))
            return None
        board = _board(rpc, rid)
        dv = rpc("decisionView", {"runnerId": rid, "allAbilities": True}, 120)
        ob = rpc("observeBattle", {"runnerId": rid}, 60)
        snap = rpc("combatSnapshot", {"runnerId": rid}, 90)
        rng0 = rpc("dumpRng", {"runnerId": rid}, 30)
        res = rpc("applyAction", {"runnerId": rid, "action": {
            "kind": "ability", "casterId": cid, "targetId": tid,
            "abilityType": nrm_or_err}, "captureEvents": True}, 120)
        rng1 = rpc("dumpRng", {"runnerId": rid}, 30)
        n_native = _genrand_steps(rng0, rng1)
        live, dirty = _live_amounts(res, tid, verbose=args.verbose)
        profiles = []
        for act in (res.get("actions") or []):
            for e in (act.get("events") or []):
                td = e.get("tags")
                td = json.loads(td) if isinstance(td, str) else (td or {})
                if td.get("Target_Id") == tid and "Amount" in td:
                    profiles.append(td.get("DamageProfileType"))
        if dirty:
            print("[159a] seed %s: coup SALE (crit/block/evade) -- ignore" % seed)
            return None
        off = _replay(dv, ob, snap, board, rng0, cid, tid, moved)
        return {"seed": seed, "live": live, "profiles": profiles, "off": off, "moved": moved,
                "n_native": n_native}
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
    ap.add_argument("--seeds", default="777,31337,12345,314159")
    ap.add_argument("--target", default=DEFAULT_TARGET)
    ap.add_argument("--variant", default="WarpHail", choices=sorted(CYCLE))
    ap.add_argument("--rank", type=int, default=None)
    ap.add_argument("--hp", type=int, default=90000)
    ap.add_argument("--max-turns", dest="max_turns", type=int, default=40)
    ap.add_argument("--verbose", action="store_true")
    args = ap.parse_args()
    rpc = _mkrpc()
    n = m_ship = m_disp = m_roll = disc = 0
    n_arme_ok = 0
    for seed in [s for s in args.seeds.split(",") if s.strip()]:
        row = _run_seed(rpc, seed, args)
        if row is None:
            continue
        n += 1
        live, off = row["live"], row["off"]
        arme_s, grp_s, bnd_s, n_s, cells = off["shipped"]
        _a_d, grp_d, _b_d, n_d, _c = off["display"]
        _a_r, grp_r, bnd_r, n_r, _c2 = off["roll"]
        k = len(arme_s)
        grp_live = live[k:k + len(grp_r or grp_s or ())]
        print("[159a %s] seed %s moved=%d" % (args.variant, seed, row["moved"]))
        print("   genrand NATIF=%s | offline shipped=%d display=%d roll=%d"
              % (row["n_native"], n_s, n_d, n_r))
        c0 = cells[0] if cells else (None, None)
        print("   cellule ARME (reduite) = %s   midpoint=%s" % (
            c0, None if c0[0] is None else (c0[0] + c0[1]) // 2))
        print("   live            = %s   (profils %s)" % (live, row["profiles"]))
        print("   arme offline    = %s -> groupe live = %s" % (arme_s, grp_live))
        print("   bornes port     = %s" % (bnd_s,))
        print("   bornes ROLL     = %s" % (bnd_r,))
        print("   groupe SHIPPED  = %s" % (grp_s,))
        print("   groupe DISPLAY  = %s   (amount +-20%%)" % (grp_d,))
        print("   groupe ROLL     = %s   (RandomAmount(min,max) natif)" % (grp_r,))
        if live[:k] != arme_s:
            print("   [!] coups d'ARME desalignes (verdict Maybe LetTheGalaxyBurn ?) "
                  "live_arme=%s offline_arme=%s" % (live[:k], arme_s))
        else:
            n_arme_ok += 1
        m_ship += int(bool(grp_live) and grp_s == grp_live)
        m_disp += int(bool(grp_live) and grp_d == grp_live)
        m_roll += int(bool(grp_live) and grp_r == grp_live)
        disc += int(grp_r != grp_d)
    print()
    print("[159a %s] BILAN %d montages : coups d'ARME alignes %d/%d | groupe SHIPPED %d/%d | "
          "DISPLAY %d/%d | ROLL %d/%d | montages discriminants %d/%d"
          % (args.variant, n, n_arme_ok, n, m_ship, n, m_disp, n, m_roll, n, disc, n))
    return 0


if __name__ == "__main__":
    sys.exit(main())
