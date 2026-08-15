"""#1020-r5 -- confrontation LIVE de `RapidFire` (1135) : natif contre port, sur le MEME etat.

MONTAGE. Le porteur est le VRAI, pas un greffon : `ultraNpc4HeavyIntercessor` arrive par le chemin
de stats NPC (`--explicit-stats`, recours 4 de `case-92` SS5bis), donc avec SES stats, SES traits et
SON arme -- ce qui compte ici, parce que l'unique effet DAMAGE de cette ability passe par le trait
`HeavyWeapon` du caster, exactement ce qu'une greffe ne donnerait pas.

Les deux unites sont POSEES a portee l'une de l'autre (`--place` / `--a-place`) : le porteur doit
attaquer SANS BOUGER, sinon le conjoint `NOT HasFlag(Caster, Moved)` du trigger ferme et la mesure
serait degeneree. La cible recoit `--hp-target` pour survivre a la salve.

CE QUE LE PROBE MESURE, et pourquoi chaque observable est SEPARANT :

  1. **le natif publie lui-meme l'appariement** : `ChangeAbility ... Blocked=1
     Blocked_ReasonEffectType=1137` sur l'ACTIF, et `Blocked=0` sur l'attaque normale. C'est un
     TEMOIN INDEPENDANT du decompile -- il confirme a la fois que `1137` est bien de la famille
     `BlockActiveAbilityEffect` et que son `includeNormalAttack` vaut `0` ;
  2. **la duree** : `Effect_RemainingTurns = 1` -> `turns = Direct(1)`, deja en TOURS ;
  3. **le tour rouvert** : `UnitStats_TurnFinished` passe a `0` -> `ResetTurn` ;
  4. **la mobilite NON rendue** : le plan d'attaque passe de N tuiles a la SEULE tuile courante ->
     `resetMovement = 0` puis `AddFlag(Moved)` ;
  5. **l'effet DAMAGE indirect** : les bornes de l'attaque normale CHUTENT (`HeavyWeapon_ExtraDmg`
     s'eteint sur `HasFlag(Owner, Moved)`). C'est le seul canal numerique de cette ability ;
  6. **le port rejoue la MEME attaque** sur la capture PRE-attaque et doit poser le meme effet, la
     meme duree, le meme drapeau, et rouvrir le meme tour ;
  7. **CONTRE-EPREUVE** : `RapidFire` retire du registre de dispatch -> le port ne doit RIEN poser.
     Sans elle, un port qui poserait 1137 par un autre chemin passerait pour juste ;
  8. **CONTRE-EPREUVE du canal de blocage** : la reconnaissance par SUFFIXE `_CantUseAbility` (le
     regime d'avant #1020-r7) ne voit PAS 1137 -- la mesure montre la faute au lieu de la raconter.

Usage :
    python probe_10015_rapid_fire_live.py [--seed 777] [--board MC1_67]
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parent
REPO = ROOT.parents[1]
sys.path.insert(0, str(ROOT))

from rl_collect_batch import _resolve_session, _rpc  # noqa: E402

PORTEUR = "ultraNpc4HeavyIntercessor"      #: npc, l'un des 4 porteurs de `RapidFire`
CIBLE = "ultraEliminatorSgt"               #: Hero du pool, sert de sac de PV
BOARD = "MC1_67"
BLOCK_ABILITIES = 1137                     #: `EffectType.RapidFire_BlockAbilities`
NORMAL_ATTACK_FALLBACK = 69                #: `Loki_NormalAttack` -- relu au RPC, jamais devine


class MontageError(RuntimeError):
    pass


def _sid() -> int:
    return _resolve_session()


def _r(sid, method, body, t=90):
    return (_rpc(sid, method, [body], timeout=t) or {}).get("result") or {}


def stage(seed: int, board_id: str):
    """Monte le duo porteur/cible a portee, et rend `(runner_id, state_file)`."""
    sf = REPO / "logs" / "runners" / ("rf10015-%s.json" % uuid.uuid4().hex[:8])
    sf.parent.mkdir(parents=True, exist_ok=True)
    cmd = [sys.executable, "rl_duel.py", "build", "--seed", str(seed), "--board", board_id,
           "--state-file", str(sf),
           "--explicit-stats", PORTEUR,
           "--p-units", PORTEUR, "--place", "%s:3,3" % PORTEUR,
           "--a-units", CIBLE, "--a-place", "%s:3,5" % CIBLE,
           # La cible doit SURVIVRE aux deux attaques : une mort sortirait du regime par la
           # mauvaise porte (plus de plan d'attaque a comparer).
           "--hp-target", "60000"]
    p = subprocess.run(cmd, cwd=str(ROOT), capture_output=True, text=True, timeout=600)
    if p.returncode != 0:
        raise MontageError("build KO (rc=%d) : %s" % (p.returncode, (p.stderr or "")[-500:]))
    st = json.loads(sf.read_text(encoding="utf-8"))
    rid = st.get("runnerId")
    if rid is None:
        raise MontageError("build sans runnerId")
    return int(rid), sf


def _ids(sid, rid):
    dv = _r(sid, "decisionView", {"runnerId": rid, "allAbilities": True}, 150)
    out = {}
    for u in (dv.get("units") or []):
        vis = u.get("visualId") or u.get("unitId")
        if vis == PORTEUR:
            out["porteur"] = int(u["id"])
        elif vis == CIBLE:
            out["cible"] = int(u["id"])
    if len(out) < 2:
        raise MontageError("unites introuvables au decisionView : %r" % out)
    return out


def _normal_attack_id(sid, rid, uid) -> int:
    ab = _r(sid, "abilityTargets", {"runnerId": rid, "unitId": int(uid)}, 60)
    for e in (ab.get("units") or []):
        if int(e.get("id", -1)) != int(uid):
            continue
        for a in (e.get("abilities") or []):
            if a.get("kind") == "normal" and a.get("id") is not None:
                return int(a["id"])
    return NORMAL_ATTACK_FALLBACK


def _effets_de(dv, uid):
    """(effectType, remaining) des effets que le NATIF publie sur `uid`."""
    for u in (dv.get("units") or []):
        if int(u.get("id", -1)) == int(uid):
            return [(int(e["effectType"]), e.get("remaining"))
                    for e in (u.get("effects") or []) if e.get("effectType") is not None]
    return []


def _plan_bornes(dv, uid, ab_id):
    """(min, max, nb_tuiles) du plan d'attaque normale, tel que la vue DECISION le publie."""
    for u in (dv.get("units") or []):
        if int(u.get("id", -1)) != int(uid):
            continue
        for p in (u.get("attackPlans") or []):
            if int(p.get("abilityType", -1)) == int(ab_id):
                tuiles = p.get("tiles") or []
                if not tuiles:
                    continue
                return (tuiles[0].get("min"), tuiles[0].get("max"), len(tuiles))
    return (None, None, None)


def _tags(a0):
    """Les `tags` de chaque event de l'action, deja decodes."""
    out = []
    for e in (a0.get("events") or []):
        td = e.get("tags")
        if not td:
            continue
        out.append(json.loads(td) if isinstance(td, str) else td)
    return out


def mesure_native(sid, rid, ids, ab_id):
    """Joue l'attaque normale cote NATIF et rend AVANT/APRES + les temoins d'events."""
    dv0 = _r(sid, "decisionView", {"runnerId": rid, "allAbilities": True}, 150)
    ob0 = _r(sid, "observeBattle", {"runnerId": rid}, 90)
    snap0 = _r(sid, "combatSnapshot", {"runnerId": rid}, 120)
    rng0 = _r(sid, "dumpRng", {"runnerId": rid}, 30)
    res = _r(sid, "applyAction", {"runnerId": rid, "action": {
        "kind": "ability", "casterId": ids["porteur"], "targetId": ids["cible"],
        "abilityType": int(ab_id)}}, 120)
    a0 = (res.get("actions") or [{}])[0]
    tags = _tags(a0)
    dv1 = _r(sid, "decisionView", {"runnerId": rid, "allAbilities": True}, 150)

    # TEMOIN 1 : le natif NOMME lui-meme l'effet qui bloque, et par ability.
    blocages = [{"ability": t.get("UnitStats_ActiveAbility_Id"),
                 "blocked": t.get("UnitStats_ActiveAbility_Blocked"),
                 "reason": t.get("UnitStats_ActiveAbility_Blocked_ReasonEffectType")}
                for t in tags
                if t.get("UnitStats_ActiveAbility_Blocked_ReasonEffectType") is not None]
    # TEMOIN 2 : la duree publiee a la reception de l'effet.
    recus = [{"effect": t.get("Effect_Id"), "remaining": t.get("Effect_RemainingTurns")}
             for t in tags if t.get("Effect_Id") is not None
             and t.get("Effect_RemainingTurns") is not None]
    # TEMOIN 3 : la remise a zero du drapeau de fin de tour.
    turn_finished = [t.get("UnitStats_TurnFinished") for t in tags
                     if t.get("UnitStats_TurnFinished") is not None]
    return {"ok": bool(res.get("ok")) and bool(a0.get("ok")),
            "dv0": dv0, "ob0": ob0, "snap0": snap0, "rng0": rng0,
            "eff0": _effets_de(dv0, ids["porteur"]), "eff1": _effets_de(dv1, ids["porteur"]),
            "plan0": _plan_bornes(dv0, ids["porteur"], ab_id),
            "plan1": _plan_bornes(dv1, ids["porteur"], ab_id),
            "blocages": blocages, "recus": recus, "turn_finished": turn_finished,
            "a_activer": [int(x) for x in (dv1.get("toActivate") or [])]}


def mesure_port(nat, ids, board, sans_rail: bool = False):
    """Rejoue LA MEME attaque sur le MEME etat avec le moteur porte et le MEME etat MT."""
    from engine.runner.snapshot import load_state
    from engine.runner.components import UnitFlagsComponent
    from engine.runner.messages import AttackUnitMessage
    from engine.runner.prng import IntBasedMersenneTwister
    from engine.runner.runner import Runner
    from engine.entities.unit_flag import UnitFlag
    import engine.runner.operations.triggers.dispatch.registry as REG

    st = load_state(nat["dv0"], nat["ob0"], nat["snap0"], board=board)
    rng = IntBasedMersenneTwister()
    rng.mt, rng.mti = list(nat["rng0"]["mt"]), nat["rng0"]["mti"]
    rng.call_count = 0
    st.rng = rng
    sauve = None
    if sans_rail:
        sauve = REG.ABILITY_TRIGGERS.pop("RapidFire", None)
    try:
        uid = int(ids["porteur"])

        def flags():
            e = st.get_entity(uid)
            c = e.get_component(UnitFlagsComponent) if e is not None else None
            return sorted(int(f) for f in (getattr(c, "flags", None) or ())) if c else None

        avant = {"flags": flags(),
                 "effets": sorted(int(e.effect_type) for e in (st.effects.by_unit.get(uid) or ())
                                  if getattr(e, "effect_type", None) is not None)}
        rn = Runner(st).install_default_handlers(20)
        rn.apply(AttackUnitMessage(uid, int(ids["cible"])))
        # DECOMPOSITION PAR ETAGE : ce que le TRIGGER a rendu (les drapeaux qu'il a RETIRES) est un
        # canal distinct de l'etat FINAL. S'ils divergent, la faute n'est pas dans le trigger mais
        # dans ce qui tourne APRES lui.
        rapides = [r for r in (getattr(rn.damage_handler, "after_hit", None) or [])
                   if isinstance(r, dict) and r.get("passive") == "RapidFire"]
        poses = [e for e in (st.effects.by_unit.get(uid) or ())
                 if int(getattr(e, "effect_type", -1)) == BLOCK_ABILITIES]
        return {"avant": avant, "flags": flags(),
                "trigger_reset_flags": [r.get("reset_flags") for r in rapides],
                "effets": sorted(int(e.effect_type) for e in (st.effects.by_unit.get(uid) or ())
                                 if getattr(e, "effect_type", None) is not None),
                "pose_1137": len(poses),
                "remaining_1137": (None if not poses
                                   else getattr(poses[0], "remaining_turns", None)),
                "moved": bool(int(UnitFlag.Moved) in (flags() or ())),
                "active_ability_used": bool(
                    UnitFlagsComponent.ACTIVE_ABILITY_USED in (flags() or ()))}
    finally:
        if sauve is not None:
            REG.ABILITY_TRIGGERS["RapidFire"] = sauve


def _contre_epreuve_suffixe():
    """Le regime d'AVANT #1020-r7 : reconnaissance par SUFFIXE de nom. Il RATE 1137."""
    from engine.entities.effect_type import EffectType
    import engine.battle_query as BQ
    porteur = {"effects": [{"effectType": BLOCK_ABILITIES,
                            "name": EffectType.RapidFire_BlockAbilities.name}]}
    par_suffixe = any(str(e.get("name") or "").endswith("_CantUseAbility")
                      for e in porteur["effects"])
    return {"suffixe_voit": par_suffixe,
            "registre_voit": BQ.can_use_ability(porteur, {"kind": "active"}) is False,
            "registre_laisse_passer_la_normale":
                BQ.can_use_ability(porteur, {"kind": "normal"}) is True}


def run(seed: int = 777, board_id: str = BOARD, verbose: bool = True) -> dict:
    from engine.entities.pathfinding.board import Board
    sid = _sid()
    rid, sf = stage(seed, board_id)
    out = {"rid": rid, "seed": seed, "board": board_id}
    try:
        bg = _r(sid, "boardGraph", {"runnerId": rid}, 90)
        board = Board(bg["tiles"], adjacency="native_sym")
        ids = _ids(sid, rid)
        ab = _normal_attack_id(sid, rid, ids["porteur"])
        out["ids"], out["normal_attack"] = ids, ab
        nat = mesure_native(sid, rid, ids, ab)
        out["natif"] = {k: v for k, v in nat.items()
                        if k not in ("dv0", "ob0", "snap0", "rng0")}
        out["port"] = mesure_port(nat, ids, board)
        out["port_sans_rail"] = mesure_port(nat, ids, board, sans_rail=True)
        out["suffixe"] = _contre_epreuve_suffixe()
    finally:
        try:
            subprocess.run([sys.executable, "rl_duel.py", "dispose", "--state-file", str(sf)],
                           cwd=str(ROOT), capture_output=True, text=True, timeout=120)
        except Exception:
            pass
    if verbose:
        _imprimer(out)
    return out


def _imprimer(out: dict) -> None:
    n, p, sr = out.get("natif") or {}, out.get("port") or {}, out.get("port_sans_rail") or {}
    print("=== #1020-r5 RapidFire -- natif contre port (runner %s, seed %s, board %s) ==="
          % (out.get("rid"), out.get("seed"), out.get("board")))
    print("attaque normale : id %s ; ids %r" % (out.get("normal_attack"), out.get("ids")))
    print("")
    print("-- NATIF --")
    print("  action OK              : %s" % n.get("ok"))
    print("  effets AVANT           : %r" % (n.get("eff0"),))
    print("  effets APRES           : %r" % (n.get("eff1"),))
    print("  blocages publies       : %r" % (n.get("blocages"),))
    print("  effets recus (duree)   : %r" % (n.get("recus"),))
    print("  TurnFinished (flux)    : %r" % (n.get("turn_finished"),))
    print("  plan (min,max,tuiles)  : AVANT %r -> APRES %r"
          % (n.get("plan0"), n.get("plan1")))
    print("  a activer APRES        : %r" % (n.get("a_activer"),))
    print("")
    print("-- PORT (meme etat, meme MT) --")
    print("  effets AVANT           : %r" % ((p.get("avant") or {}).get("effets"),))
    print("  effets APRES           : %r" % (p.get("effets"),))
    print("  1137 pose (n, duree)   : %s, %s" % (p.get("pose_1137"), p.get("remaining_1137")))
    print("  drapeau Moved          : %s" % p.get("moved"))
    print("  drapeaux RETIRES par le trigger : %r" % (p.get("trigger_reset_flags"),))
    print("  ActiveAbilityUsed FINAL: %s (ResetTurn doit l'avoir RETIRE)"
          % p.get("active_ability_used"))
    print("  flags AVANT / APRES    : %r / %r" % ((p.get("avant") or {}).get("flags"),
                                                  p.get("flags")))
    print("")
    print("-- CONTRE-EPREUVE : RapidFire HORS du registre --")
    print("  1137 pose              : %s (doit valoir 0)" % sr.get("pose_1137"))
    print("  drapeau Moved          : %s (doit valoir False)" % sr.get("moved"))
    print("")
    print("-- CONTRE-EPREUVE : la CONVENTION de nom --")
    print("  %r" % (out.get("suffixe"),))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--seed", type=int, default=777)
    ap.add_argument("--board", default=BOARD)
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args()
    out = run(a.seed, a.board, verbose=not a.json)
    if a.json:
        print(json.dumps({k: v for k, v in out.items()}, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
