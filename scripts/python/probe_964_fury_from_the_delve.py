"""Probe #964 -- `FuryFromTheDelve` (TriggeredAbilityType 1528, `votanBeserk`) confronte LIVE.

Le passif a DEUX bras, et le discriminant est un FLAG PERSISTANT ecrit AVANT le coup :

  * `On(0x2a = PreUnitAbility) & IsNormalAttack & OwnerIsActor`
      -> `SetPersistentData(1528, Owner, "TARGET_HEALTH_ABOVE_HALF",
          AmountIsGreater(Health.Current(Target), PercentageOf(Health.Maximum(Target), hpPct)))`
  * `On(0x26 = NormalAttack) & OwnerIsActor & IsAlive(Target)`
      -> `If(<flag> > 0, AddEffect(1065 Pinned, nrOfRounds), AttackWithAttackDamage(nrOfHits,
          Eviscerate, minDmg/maxDmg))`

RE complete : l'en-tete de `engine/runner/operations/triggers/loki/fury_from_the_delve.py`.

## LE MONTAGE, ET CE QU'IL REND SEPARABLE

`votanBeserk` est un HERO **hors pool** -> `catalog_inject.write_augmented_seed_bc` (case-92 §6).

Deux cibles, MEME max de PV force, RATIOS opposes -- c'est la seule chose qui distingue les deux
regimes, et elle est ECRITE, pas subie :

    SAINE   `orksNob`      Health = HP_MAX, RemainingHealth = HP_MAX      -> 100 % > hpPct
    BLESSEE `necroWarden`  Health = HP_MAX, RemainingHealth = HP_LOW      ->  20 % < hpPct

`HP_MAX` est pris TRES grand pour que la cible BLESSEE **survive** au coup : sans quoi le gate
`IsAlive(Target)` du bras 2 fermerait et on mesurerait un silence au lieu d'une attaque.

OBSERVABLE, et il est BINAIRE :

    regime A (cible saine)   -> la cible porte `Pinned` APRES le coup, et AUCUN coup supplementaire
    regime B (cible blessee) -> la cible ne porte PAS `Pinned`, et `nrOfHits` coups EN PLUS

ETAGES :
  [1] MONTAGE  -- le porteur est la, il porte 1528, et les deux ratios de PV sont ceux voulus ;
  [2] REGIME A -- natif vs port : effet `Pinned` et nombre de coups ;
  [3] REGIME B -- natif vs port : pas de `Pinned`, coups supplementaires ;
  [4] MUTANTS  -- retirer une des deux classes du registre DOIT faire diverger le port du natif.
                  Un mutant inerte dit que le montage est aveugle, pas que le port est bon.

Usage :
    python probe_964_fury_from_the_delve.py --state-file <chemin ABSOLU>
    python probe_964_fury_from_the_delve.py --state-file <...> --runner <id>   # runner deja monte

ASCII only (console cp1252).
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import hexgeo                                                            # noqa: E402
from rl_collect_batch import _resolve_session, _rpc                      # noqa: E402
from engine.entities.effect_type import EffectType                       # noqa: E402
from engine.entities.pathfinding.board import Board                      # noqa: E402
from engine.runner.components import HealthComponent                     # noqa: E402
from engine.runner.messages import AttackUnitMessage                     # noqa: E402
from engine.runner.prng import IntBasedMersenneTwister                   # noqa: E402
from engine.runner.runner import Runner                                  # noqa: E402
from engine.runner.snapshot import load_state                            # noqa: E402

CARRIER = "votanBeserk"
HEALTHY = "orksNob"          # cible SAINE   -> flag = 1 -> Pinned
WOUNDED = "necroWarden"      # cible BLESSEE -> flag = 0 -> attaque supplementaire
BOARD = "MC1_67"
SEED = 777
#: `Health` (maximum) commun aux deux cibles : assez grand pour qu'aucune ne meure du coup, sinon
#: le gate `IsAlive(Target)` du bras 2 fermerait et le regime B ne mesurerait rien.
HP_MAX = 4000000
#: `RemainingHealth` de la cible BLESSEE = 10 % de son maximum, donc franchement sous `hpPct = 50`.
HP_LOW = 400000
PINNED = EffectType.Pinned.name


def _seed_rng(s):
    rng = IntBasedMersenneTwister()
    rng.mt = list(s["mt"])
    rng.mti = s["mti"]
    return rng


def _pos(u):
    p = u.get("pos") or {}
    return (p.get("col"), p.get("row"))


def _tags(ev):
    try:
        return json.loads(ev.get("tags") or "{}")
    except Exception:                                          # noqa: BLE001
        return {}


def _cascade(r):
    out = list(r.get("cascade") or [])
    for a in (r.get("actions") or []):
        out += list(a.get("events") or [])
    return out


def _flat_hits(obj, out=None):
    """Sequence PLATE des coups OFFLINE (toute liste sous une cle `per_hit`, dans l'ordre de
    composition du handler)."""
    if out is None:
        out = []
    if isinstance(obj, dict):
        for k, v in obj.items():
            if k == "per_hit" and isinstance(v, list):
                out += [int(x) for x in v if isinstance(x, (int, float))]
            else:
                _flat_hits(v, out)
    elif isinstance(obj, list):
        for v in obj:
            _flat_hits(v, out)
    return out


def _normal_attack_type(dv, uid):
    """L'id CONCRET de l'attaque normale de `uid` (`decisionView.units[].abilities`, kind
    `normal`). ⚠ Surtout pas le 17 SYNTHETIQUE du bridge offline : `ActiveAbilityMessage` exige
    l'id que porte l'unite."""
    for u in (dv.get("units") or []):
        if int(u.get("id", -1)) == int(uid):
            for a in (u.get("abilities") or []):
                if a.get("kind") == "normal" and a.get("id") is not None:
                    return int(a["id"])
    return None


def build(state_file: Path) -> int:
    import catalog_inject as CI
    state_file.parent.mkdir(parents=True, exist_ok=True)
    state_file.unlink(missing_ok=True)
    seed_bc = state_file.with_name(state_file.stem + "-seedbc.json")
    CI.write_augmented_seed_bc(str(seed_bc), [CARRIER])
    stat = ("%s:Health=%d,RemainingHealth=%d;%s:Health=%d,RemainingHealth=%d"
            % (HEALTHY, HP_MAX, HP_MAX, WOUNDED, HP_MAX, HP_LOW))
    argv = ["build", "--seed", str(SEED), "--board", BOARD,
            "--state-file", str(state_file), "--seed-bc", str(seed_bc),
            "--p-units", CARRIER, "--a-units", "%s,%s" % (HEALTHY, WOUNDED),
            "--unit-stat", stat]
    p = subprocess.run([sys.executable, str(HERE / "rl_duel.py")] + argv,
                       cwd=str(HERE), capture_output=True, text=True,
                       encoding="utf-8", errors="replace")
    if not state_file.exists():
        print(p.stdout[-2000:])
        print(p.stderr[-1200:])
        raise SystemExit("[1] MONTAGE KO -- build rc=%d" % p.returncode)
    return int(json.loads(state_file.read_text(encoding="utf-8"))["runnerId"])


class Case:
    """Etat courant du montage : ids, board, et les accesseurs RPC."""

    def __init__(self, rpc, rid, board):
        self.rpc, self.rid, self.board = rpc, rid, board

    def dview(self):
        return self.rpc("decisionView",
                        {"runnerId": self.rid, "allAbilities": True, "maxRank": 1}, 150)

    def unit(self, dv, visual):
        return next((u for u in (dv.get("units") or [])
                     if u.get("alive") and u.get("visualId") == visual), None)

    def effects_of(self, dv, uid):
        u = next((x for x in (dv.get("units") or []) if x.get("id") == uid), None)
        return [e.get("name") for e in ((u or {}).get("effects") or [])]

    def ensure_turn(self, owner) -> bool:
        """Rend la main quand c'est au tour d'`owner` (au plus 12 `endturn`)."""
        for _ in range(12):
            if self.dview().get("currentPlayer") == owner:
                return True
            self.rpc("applyAction", {"runnerId": self.rid, "action": {"kind": "endturn"}}, 90)
        return self.dview().get("currentPlayer") == owner

    def place_adjacent(self, mover_id, anchor_pos) -> tuple:
        """DEPLACE `mover_id` sur une tuile libre adjacente a `anchor_pos` -- la geometrie est
        FORCEE, jamais subie (une cible qui n'est pas a portee ne mesure rien)."""
        dv = self.dview()
        alive = [u for u in (dv.get("units") or []) if u.get("alive")]
        occ = {_pos(u) for u in alive if u.get("id") != mover_id}
        here = next((_pos(u) for u in alive if u.get("id") == mover_id), None)
        if here is not None and hexgeo.distance(here, anchor_pos) == 1:
            return here
        for t in sorted(self.board.by_id):
            c = self.board.coord(t)
            if (self.board.walkable(t) and c not in occ
                    and hexgeo.distance(c, anchor_pos) == 1):
                self.rpc("applyAction", {"runnerId": self.rid, "action": {
                    "kind": "move", "unitId": mover_id, "to": {"col": c[0], "row": c[1]}}}, 90)
                return c
        return None


def measure(case: Case, caster_vis: str, target_vis: str) -> dict:
    """UN regime, sur UN SEUL snapshot : le port (non mute PUIS chaque mutant) rejoue l'attaque
    normale sur l'etat GELE, ensuite seulement le natif la joue.

    ⚠ L'ORDRE EST LOAD-BEARING. Les mutants tournaient d'abord sur un etat re-capture apres coup ;
    entre-temps la cible BLESSEE remontait au-dessus de `hpPct` (mesure : 20 % -> 59 %) et le
    mutant `statpart_confondus` cessait de mordre -- il n'y avait plus de regime pour l'exercer.
    Sur le MEME snapshot que la mesure, la contre-epreuve voit exactement le regime confronte."""
    rpc, rid = case.rpc, case.rid
    dv = case.dview()
    cst = case.unit(dv, caster_vis)
    tgt = case.unit(dv, target_vis)
    if cst is None or tgt is None:
        raise SystemExit("[x] %s ou %s absent du plateau" % (caster_vis, target_vis))
    ab = _normal_attack_type(dv, cst["id"])
    if ab is None:
        raise SystemExit("[x] %s n'expose aucune attaque normale" % caster_vis)

    ob = rpc("observeBattle", {"runnerId": rid}, 60)
    snap = rpc("combatSnapshot", {"runnerId": rid}, 60)
    s0 = rpc("dumpRng", {"runnerId": rid}, 30)
    pre_hp = {u["id"]: u.get("hp") for u in (dv.get("units") or []) if u.get("alive")}
    snapshot = (dv, ob, snap, s0)

    def replay(mutant=None) -> dict:
        """Un rejeu COTE PORT sur une copie FRAICHE du meme snapshot (RNG recale a l'identique)."""
        st = load_state(dv, ob, snap, board=case.board)
        if s0 and s0.get("mt"):
            st.rng = _seed_rng(s0)
        before = set(_port_effect_names(st, tgt["id"]))
        restore = _apply_mutant(mutant) if mutant else (lambda: None)
        try:
            # ⚠ L'attaque NORMALE emprunte `AttackUnitMessage` -> `DamageHandler`, PAS
            # `ActiveAbilityMessage` -> `AbilityHandler` : le port a DEUX portes pour l'unique
            # site natif `InputMessageProcessor$$Visit(ActiveAbilityMessage)` (#120 /
            # #429-r1-r3-r1), et c'est celle-ci que prend une normale. Passer par l'autre rend
            # `last = None` EN SILENCE -- mesure faite.
            r = Runner(st).install_default_handlers(20)
            r.apply(AttackUnitMessage(attacker_id=cst["id"], target_id=tgt["id"]))
            lst = {"main": r.damage_handler.last or {},
                   "after_hit": list(r.damage_handler.after_hit or [])}
        finally:
            restore()
        e = st.get_entity(tgt["id"])
        hc = e.get_component(HealthComponent) if e is not None else None
        now = set(_port_effect_names(st, tgt["id"]))
        return {"hits": _flat_hits(lst),
                "dhp": (pre_hp.get(tgt["id"]) - hc.hp)
                       if (hc is not None and pre_hp.get(tgt["id"]) is not None) else None,
                # `pinned` = PRESENCE de l'effet apres le coup (une re-pose est un no-op, donc
                # `placed` seul ne distinguerait pas les deux bras sur une cible deja Pinned).
                "pinned": PINNED in now, "posed": PINNED in (now - before),
                "ratio": _ratio(st, tgt["id"])}

    port = replay()
    mutants = {name: replay(name) for name in sorted(MUTANTS)}

    # --- NATIF ---------------------------------------------------------------------------------
    r = rpc("applyAction", {"runnerId": rid, "action": {
        "kind": "ability", "casterId": cst["id"], "targetId": tgt["id"], "abilityType": ab}}, 240)
    a0 = ((r or {}).get("actions") or [{}])[0]
    if not a0.get("ok"):
        raise SystemExit("[x] attaque LIVE refusee : %s" % str(r)[:400])
    casc = _cascade(r)
    live_hits = [int(t["Amount"]) for t in (_tags(ev) for ev in casc)
                 if t.get("Amount") is not None and t.get("Target_Id") == tgt["id"]
                 and t.get("Effect_Type") is None]
    dv2 = case.dview()
    live = {"hits": live_hits, "pinned": PINNED in case.effects_of(dv2, tgt["id"]),
            "effects": case.effects_of(dv2, tgt["id"])}
    return {"ability": ab, "caster": cst["id"], "target": tgt["id"], "port": port,
            "live": live, "mutants": mutants, "snapshot": snapshot}


#: Les QUATRE contre-epreuves, une par LECTURE que le port fait et que rien d'autre ne garde.
MUTANTS = ("sans_bras_pre_attaque", "sans_bras_normal_attack",
           "statpart_confondus", "comparaison_inversee")


def _apply_mutant(name: str):
    """Monkeypatch CIBLE d'une seule lecture. Rend le callable de restauration."""
    import engine.runner.operations.triggers.dispatch.registry as REG
    import engine.runner.operations.triggers.loki.fury_from_the_delve as M
    from engine.entities.formulas import PercentageOf, StatAmount
    from engine.entities.selectors.accessors import Target
    from engine.entities.stats import StatPart, StatType
    from engine.entities.triggers import AmountIsGreater
    from engine.dsl.base import Const

    saved = list(REG.ABILITY_TRIGGERS[M.FURY_FROM_THE_DELVE])
    saved_fn = M.target_health_above_threshold_trigger

    def restore():
        REG.ABILITY_TRIGGERS[M.FURY_FROM_THE_DELVE] = saved
        M.target_health_above_threshold_trigger = saved_fn

    if name == "sans_bras_pre_attaque":
        # Le flag n'est plus jamais ecrit -> `GetPersistentData` rend 0 -> branche ATTAQUE
        # TOUJOURS. C'est le mutant qui etablit que le bras 1 est LOAD-BEARING.
        REG.ABILITY_TRIGGERS[M.FURY_FROM_THE_DELVE] = [M.FuryFromTheDelveAttackOrPinAbility]
    elif name == "sans_bras_normal_attack":
        REG.ABILITY_TRIGGERS[M.FURY_FROM_THE_DELVE] = [M.FuryFromTheDelveCheckTargetHealthAbility]
    elif name == "statpart_confondus":
        # `StatPart.Current` a la place de `StatPart.Maximum` : le test devient `PV > PV x hpPct%`,
        # donc TOUJOURS vrai des que `hpPct < 100` -> plus jamais d'attaque supplementaire.
        M.target_health_above_threshold_trigger = lambda pct: AmountIsGreater(
            StatAmount(Target(), int(StatType.HEALTH), int(StatPart.CURRENT)),
            PercentageOf(Const(int(pct)),
                         StatAmount(Target(), int(StatType.HEALTH), int(StatPart.CURRENT)), 0))
    elif name == "comparaison_inversee":
        M.target_health_above_threshold_trigger = lambda pct: AmountIsGreater(
            PercentageOf(Const(int(pct)),
                         StatAmount(Target(), int(StatType.HEALTH), int(StatPart.MAXIMUM)), 0),
            StatAmount(Target(), int(StatType.HEALTH), int(StatPart.CURRENT)))
    else:
        raise SystemExit("mutant inconnu : %r" % name)
    return restore


def _hp_pct():
    """`GetNumberConstant(0x12 = hpPct)` LU au gameconfig du passif -- jamais code en dur ici."""
    import gameconfig as GC
    raw = ((GC.ability("FuryFromTheDelve") or {}).get("constants") or {}).get("hpPct")
    try:
        return int(raw)
    except (TypeError, ValueError):
        return None


def _port_effect_names(state, uid) -> list:
    fx = getattr(state, "effects", None)
    if fx is None:
        return []
    out = []
    for inst in (getattr(fx, "by_unit", {}) or {}).get(int(uid), ()) or ():
        nm = getattr(inst, "name", None) or (inst.get("name") if isinstance(inst, dict) else None)
        if nm:
            out.append(nm)
    return out


def _ratio(state, uid):
    e = state.get_entity(int(uid))
    hc = e.get_component(HealthComponent) if e is not None else None
    if hc is None or not hc.hp_max:
        return None
    return round(100.0 * float(hc.hp) / float(hc.hp_max), 2)


def _verdict(tag, ok, msg):
    print("[%s] %s -- %s" % (tag, "OK  " if ok else "KO  ", msg))
    return bool(ok)


def main(argv) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--state-file", required=True, help="chemin ABSOLU, nom unique")
    ap.add_argument("--runner", type=int, default=None)
    args = ap.parse_args(argv)

    state_file = Path(args.state_file)
    rid = args.runner if args.runner is not None else build(state_file)
    sid = _resolve_session()

    def rpc(m, b, t=90):
        return (_rpc(sid, m, [b], timeout=t).get("result") or {})

    bg = rpc("boardGraph", {"runnerId": rid}, 60)
    case = Case(rpc, rid, Board(bg["tiles"], adjacency="native_sym"))
    ok = True

    # ---------------------------------------------------------------- [1] MONTAGE
    dv = case.dview()
    cst = case.unit(dv, CARRIER)
    if cst is None:
        return _verdict("1", False, "%s absent -- injection catalogue KO" % CARRIER) or 2
    passives = [a.get("name") for a in (cst.get("abilities") or [])]
    ok &= _verdict("1", True, "porteur %s id=%s abilities=%s"
                   % (CARRIER, cst["id"], json.dumps(passives)[:200]))
    case.ensure_turn(cst.get("owner"))

    hp_pct = _hp_pct()
    ok &= _verdict("1", hp_pct is not None,
                   "gameconfig `FuryFromTheDelve.constants.hpPct` = %r" % hp_pct)

    # ⚠ ORDRE : la cible BLESSEE PASSE EN PREMIER. Mesure : entre deux tours elle remonte de 20 %
    # a 59 % de ses PV max (soin/regeneration adverses), donc son regime DISPARAIT si on la mesure
    # apres. La cible SAINE, elle, reste au-dessus du seuil quoi qu'il arrive (4 000 000 PV).
    results = {}
    for tag, vis in (("2", WOUNDED), ("3", HEALTHY)):
        dv = case.dview()
        cst = case.unit(dv, CARRIER)
        if cst is None:
            ok &= _verdict(tag, False, "le porteur est mort avant le regime")
            break
        if case.unit(dv, vis) is None:
            ok &= _verdict(tag, False, "cible %s absente" % vis)
            continue
        case.ensure_turn(cst.get("owner"))
        case.place_adjacent(case.unit(case.dview(), vis)["id"], _pos(cst))
        res = measure(case, CARRIER, vis)
        results[vis] = res
        p, l = res["port"], res["live"]
        # L'ATTENDU EST DERIVE DU RATIO MESURE, jamais suppose : `AmountIsGreater` est STRICT, donc
        # `Pinned` ssi `PV_courants > hpPct % du max` AU MOMENT du snapshot.
        expect = (p["ratio"] is not None and hp_pct is not None and p["ratio"] > float(hp_pct))
        print("    %s ratio_PV=%s%% (seuil %s%%) | PORT hits=%s pinned=%s | LIVE hits=%s "
              "pinned=%s fx=%s"
              % (vis, p["ratio"], hp_pct, p["hits"], p["pinned"], l["hits"], l["pinned"],
                 json.dumps(l["effects"])[:150]))
        ok &= _verdict(tag, l["pinned"] == expect,
                       "NATIF : Pinned=%s, attendu %s d'apres le ratio mesure %s%% vs %s%%"
                       % (l["pinned"], expect, p["ratio"], hp_pct))
        ok &= _verdict(tag, p["pinned"] == l["pinned"],
                       "ACCORD Pinned port==natif (%s vs %s)" % (p["pinned"], l["pinned"]))
        ok &= _verdict(tag, p["hits"] == l["hits"],
                       "ACCORD coups port==natif (%s vs %s)" % (p["hits"], l["hits"]))
        # ------------------------------------------------------- [4] MUTANTS, MEME SNAPSHOT
        for name in sorted(MUTANTS):
            g = res["mutants"][name]
            moved = (g["hits"] != p["hits"]) or (g["pinned"] != p["pinned"])
            print("      mutant %-22s -> pinned=%s coups=%d %s"
                  % (name, g["pinned"], len(g["hits"]), "DEPLACE" if moved else "inerte"))

    # ------------------------------------------------------------- [4] chaque mutant MORD quelque part
    for name in sorted(MUTANTS):
        bites = [vis for vis, r in results.items()
                 if (r["mutants"][name]["hits"] != r["port"]["hits"]
                     or r["mutants"][name]["pinned"] != r["port"]["pinned"])]
        ok &= _verdict("4", bool(bites),
                       "mutant %-22s DEPLACE le port dans au moins un regime (%s)"
                       % (name, ",".join(bites) or "AUCUN"))

    # ------------------------------------------------------------- [5] SEPARABILITE des deux bras
    seen = {vis: r["live"]["pinned"] for vis, r in results.items()}
    ok &= _verdict("5", set(seen.values()) == {True, False},
                   "les DEUX bras sont exerces par le montage (Pinned par cible : %r) -- si les "
                   "deux regimes tombaient du meme cote du seuil, l'accord ne prouverait rien"
                   % seen)
    if len(results) == 2 and set(seen.values()) == {True, False}:
        pin = next(v for v, p in seen.items() if p)
        att = next(v for v, p in seen.items() if not p)
        na, nb = len(results[pin]["live"]["hits"]), len(results[att]["live"]["hits"])
        ok &= _verdict("5", nb > na,
                       "le bras ATTAQUE porte PLUS de coups que le bras PINNED (%d > %d, ecart = "
                       "nrOfHits)" % (nb, na))

    print("[=] VERDICT : %s" % ("OK" if ok else "KO"))
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
