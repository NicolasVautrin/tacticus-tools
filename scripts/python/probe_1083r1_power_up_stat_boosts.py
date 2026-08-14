"""#1083-r1 -- CONFRONTATION des CINQ passifs `PowerUp_*` de boost de stat (natif vs port).

Le montage est celui de `docs/rl/case-1083-powerup-le-board-ne-confronte-rien.md` §4 (le BOARD n'y
est pour RIEN) : `catalog_inject --units powup<X>` puis `rl_duel build --seed-bc ...
--explicit-stats powup<X> --a-units "powup<X>,..."`. On y ajoute un `--a-place` / `--place` pour
poser le power-up A COTE du ramasseur : sans ca il faudrait plusieurs tours de marche, et le
`decisionView` intermediaire laisserait l'IA adverse bouger.

MECANIQUE CONFRONTEE : le power-up est une unite `Steppable` a 0 PV. Quand une unite MARCHE sur sa
tuile, `MoveUnitOperation$$KillSteppableUnits` la tue par `KillUnitOperationOptions$$ForSteppable`,
ce qui grave `DamageReason.Steppable` puis publie `On(1 = PreUnitDeath)` -- le vecteur sur lequel
`APowerUpAbility$$CreateTrigger` s'accroche. Le ramasseur recoit alors, dans l'ordre natif :
`AddShield` (commun aux cinq) puis le boost propre au power-up.

CE QUE LE PROBE MESURE, des DEUX cotes, sur la MEME capture :
  * le power-up est-il MORT ;
  * le BOUCLIER du ramasseur (`combatSnapshot.units[].shields` cote natif, `ShieldComponent` cote
    port) -- attendu `shieldPct % de sa HP INITIALE` ;
  * la STAT ciblee (`stats.attack` / `stats.health` / `stats.extraHits` / `stats.extraHitsMelee` /
    `stats.fixedArmor`) AVANT et APRES.

TEMOIN NON DEGENERE : le probe assertionne que le delta attendu est NON NUL avant de comparer quoi
que ce soit (`--attendu`), et il imprime les deux valeurs brutes. Un accord a zero ne prouverait
rien -- c'est exactement le regime ou un port INERTE passerait pour juste.

CONTRE-EPREUVE (`--regime hors-tuile`) : le ramasseur se deplace sur une tuile VOISINE du power-up
au lieu de la sienne. Le natif comme le port doivent alors ne RIEN faire (power-up VIVANT, aucun
bouclier, stat inchangee). C'est ce bras qui separe << le port a joue le trigger >> de << le port
buffe a chaque deplacement >>.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

_PYDIR = Path(__file__).resolve().parent
sys.path.insert(0, str(_PYDIR))

from rl_collect_batch import _rpc, _resolve_session                      # noqa: E402
from engine.entities.effect_type import EffectType                       # noqa: E402
from engine.entities.stats import StatPart, StatType                     # noqa: E402
from engine.runner.components import ShieldComponent, StatsComponent, UnitComponent  # noqa: E402
from engine.runner.messages import MoveUnitMessage                       # noqa: E402
from engine.runner.prng import IntBasedMersenneTwister                   # noqa: E402
from engine.runner.runner import Runner                                  # noqa: E402
from engine.runner.snapshot import bind_live_rpc, load_state             # noqa: E402

#: Les CINQ, avec la cle `combatSnapshot.units[].stats` a lire et le `StatType` du port.
CAS = {
    "armor":     ("powupArmor",     "PowerUp_Armor",     "fixedArmor",      StatType.FIXED_ARMOR),
    "damage":    ("powupDamage",    "PowerUp_Damage",    "attack",          StatType.ATTACK),
    "health":    ("powupHealth",    "PowerUp_Health",    "health",          StatType.HEALTH),
    "hits":      ("powupHits",      "PowerUp_Hits",      "extraHits",       StatType.EXTRA_HITS),
    "meleehits": ("powupMeleeHits", "PowerUp_MeleeHits", "extraHitsMelee",  StatType.EXTRA_HITS_MELEE),
}
#: `EffectType` pose sur le RAMASSEUR par chacun (jamais le `TriggeredAbilityType` homonyme : les
#: deux enums divergent, `1138` est `PowerUp_MeleeHits` d'un cote et `PowerUp_Armor` de l'autre).
EFFET = {
    "armor": EffectType.PowerUp_Armor, "damage": EffectType.PowerUp_Damage,
    "health": EffectType.PowerUp_Health, "hits": EffectType.PowerUp_Hits,
    "meleehits": EffectType.PowerUp_MeleeHits,
}

BOARD, SEED = "MC1_67", "777"
#: Le RAMASSEUR : un HERO du pool, MON equipe. Il n'entre dans aucun conjoint du trigger sauf
#: `!HasTrait(Steppable)` et `IsAlive` -- n'importe quel hero fait l'affaire.
RAMASSEUR = "ultraCalgar"
#: Deux tuiles ADJACENTES et libres du board MC1_67 (verifiees a l'execution par la distance).
TUILE_POWUP = (2, 1)
TUILE_HERO = (1, 1)
#: CONTRE-EPREUVE : une tuile voisine du hero qui n'est PAS celle du power-up.
TUILE_VOISINE = (0, 1)


def _unwrap(r):
    return r.get("result") if isinstance(r, dict) and "result" in r else r


def build(state_file: Path, powup: str, seed_bc: Path) -> int:
    args = [sys.executable, "rl_duel.py", "build", "--seed", SEED, "--board", BOARD, "--no-ai",
            "--seed-bc", str(seed_bc), "--state-file", str(state_file),
            "--explicit-stats", powup,
            "--p-units", RAMASSEUR, "--a-units", "%s,orksNob" % powup,
            "--a-place", "%s:%d,%d" % (powup, TUILE_POWUP[0], TUILE_POWUP[1]),
            "--place", "%s:%d,%d" % (RAMASSEUR, TUILE_HERO[0], TUILE_HERO[1])]
    p = subprocess.run(args, cwd=str(_PYDIR), capture_output=True, text=True)
    if p.returncode != 0:
        print("BUILD KO rc=%d" % p.returncode)
        print((p.stderr or p.stdout or "")[-1500:])
    return p.returncode


def injecter(seed_bc: Path, powup: str) -> int:
    p = subprocess.run([sys.executable, "catalog_inject.py", "--units", powup,
                        "--out", str(seed_bc)], cwd=str(_PYDIR), capture_output=True, text=True)
    if p.returncode != 0:
        print("INJECT KO rc=%d\n%s" % (p.returncode, (p.stderr or "")[-800:]))
    return p.returncode


def _snap_unit(snap, uid):
    return next((u for u in (snap.get("units") or []) if u.get("entityId") == uid), None)


def _shield_natif(snap, uid) -> int:
    u = _snap_unit(snap, uid) or {}
    tot = 0
    for s in (u.get("shields") or []):
        v = s.get("amount") if isinstance(s, dict) else s
        tot += int(v or 0)
    return tot


def _shield_port(state, uid) -> int:
    e = state.get_entity(int(uid))
    sh = e.get_component(ShieldComponent) if e is not None else None
    return 0 if sh is None else int(sh.get_total_shield() or 0)


def _stat_port(state, uid, stat_type) -> "int | None":
    """La valeur COURANTE du stat, lue par le MEME dispatch que le moteur ecrit.

    ⚠ DEUX RESERVOIRS, ET C'EST STRUCTUREL : un stat FILL-UP (`Health`, `Armor`,
    `NumberOfMembers`) vit dans un composant d'ENTITE (`HealthComponent`), pas dans
    `UnitStats.components`. `stat_ops.apply_change_stat` y route explicitement
    (`_fillup_component` d'abord, `ctx.stats` sinon) -- lire `ctx.stats` pour `Health` rend donc la
    valeur SEEDEE, immobile, et un port juste passerait pour inerte. C'est exactement le faux
    negatif qu'a rendu la premiere version de ce probe."""
    from engine.runner.operations.stat_ops import _fillup_component       # noqa: PLC0415
    hc = _fillup_component(state, int(uid), int(stat_type))
    if hc is not None:
        return int(hc.get_stat_part(int(StatPart.CURRENT)))
    e = state.get_entity(int(uid))
    sc = e.get_component(StatsComponent) if e is not None else None
    if sc is None or getattr(sc, "ctx", None) is None:
        return None
    return int(sc.ctx.get_stat(int(stat_type), int(StatPart.CURRENT)))


def _hp_port(state, uid) -> "int | None":
    """Les PV COURANTS (`HealthComponent.hp`) -- le second volet du `PctBasedStatBoost` HEALTH est
    un `ChangeStat(Health, Add)`, qui vise cette grandeur-la et pas le MAXIMUM."""
    from engine.runner.components import HealthComponent                  # noqa: PLC0415
    e = state.get_entity(int(uid))
    hc = e.get_component(HealthComponent) if e is not None else None
    return None if hc is None else int(hc.hp)


def _vivant(dv, uid) -> "bool | None":
    u = next((x for x in (dv.get("units") or []) if x.get("id") == uid), None)
    return None if u is None else bool(u.get("alive"))


def mesurer(rid: int, rpc, cas: str, regime: str) -> dict:
    powup_id, passif, cle_snap, stat_type = CAS[cas]
    dv = rpc("decisionView", {"runnerId": rid, "maxRank": 1, "allAbilities": True,
                              "includeInactive": True}, 90)
    units = dv.get("units") or []
    pw = next((u for u in units if (u.get("visualId") or "") == powup_id), None)
    he = next((u for u in units if (u.get("visualId") or "") == RAMASSEUR), None)
    if pw is None or he is None:
        return {"erreur": "montage: powup=%s hero=%s" % (pw is not None, he is not None)}
    ppos, hpos = pw.get("pos") or {}, he.get("pos") or {}
    cible = ((ppos.get("col"), ppos.get("row")) if regime == "nominal" else TUILE_VOISINE)
    # GEOMETRIE ASSERTIONNEE : le hero doit pouvoir atteindre la tuile visee en UN move.
    d = abs(int(hpos.get("col")) - int(cible[0])) + abs(int(hpos.get("row")) - int(cible[1]))
    if d < 1 or d > 3:
        return {"erreur": "geometrie: hero=%s cible=%s d=%d" % ((hpos.get("col"), hpos.get("row")),
                                                                cible, d)}

    ob = rpc("observeBattle", {"runnerId": rid}, 60)
    snap = rpc("combatSnapshot", {"runnerId": rid}, 60)
    from engine.entities.pathfinding.board import Board                   # noqa: PLC0415
    bg = rpc("boardGraph", {"runnerId": rid}, 60)
    if not (isinstance(bg, dict) and bg.get("tiles")):
        return {"erreur": "boardGraph indisponible -- AUCUNE mesure n'a eu lieu"}
    board = Board(bg["tiles"], adjacency="native_sym")
    state = load_state(dv, ob, snap, board=board)
    if getattr(state, "effects", None) is None:
        return {"erreur": "pas d'EffectsState -- l'effet serait indecidable"}
    sc = state.get_entity(pw["id"]).get_component(StatsComponent)
    passifs = list(getattr(getattr(sc, "ctx", None), "passive_abilities", None) or [])
    if passif not in passifs:
        return {"erreur": "passif %s non monte cote port (passifs=%s)" % (passif, passifs)}

    avant_nat = (_snap_unit(snap, he["id"]) or {}).get("stats", {}).get(cle_snap)
    avant_port = _stat_port(state, he["id"], stat_type)
    sh_avant_nat, sh_avant_port = _shield_natif(snap, he["id"]), _shield_port(state, he["id"])
    hp_avant_nat, hp_avant_port = he.get("hp"), _hp_port(state, he["id"])

    # --- PORT : rejoue le MEME deplacement depuis la MEME capture -------------------------------
    s0 = rpc("dumpRng", {"runnerId": rid}, 30)
    if isinstance(s0, dict) and s0.get("ok"):
        rng = IntBasedMersenneTwister()
        rng.mt, rng.mti = list(s0["mt"]), s0["mti"]
        state.rng = rng
    runner = Runner(state).install_default_handlers(20)
    runner.apply(MoveUnitMessage(he["id"], (int(cible[0]), int(cible[1]))))
    apres_port = _stat_port(state, he["id"], stat_type)
    sh_apres_port = _shield_port(state, he["id"])
    hp_apres_port = _hp_port(state, he["id"])
    pwe = state.get_entity(pw["id"])
    puc = pwe.get_component(UnitComponent) if pwe is not None else None
    powup_vivant_port = None if puc is None else bool(puc.alive)
    eff_port = sorted({str(getattr(e, "name", "") or "")
                       for e in ((state.effects.by_unit.get(he["id"]) or [])
                                 if state.effects else [])})

    # --- NATIF ----------------------------------------------------------------------------------
    res = rpc("applyAction", {"runnerId": rid, "action": {
        "kind": "move", "unitId": he["id"], "to": {"col": int(cible[0]), "row": int(cible[1])}}}, 90)
    if not (isinstance(res, dict) and res.get("ok")):
        return {"erreur": "move live KO: %s" % str(res)[:220]}
    dv2 = rpc("decisionView", {"runnerId": rid, "maxRank": 1, "allAbilities": True,
                               "includeInactive": True}, 90)
    snap2 = rpc("combatSnapshot", {"runnerId": rid}, 60)
    apres_nat = (_snap_unit(snap2, he["id"]) or {}).get("stats", {}).get(cle_snap)
    sh_apres_nat = _shield_natif(snap2, he["id"])
    he2 = next((u for u in (dv2.get("units") or []) if u.get("id") == he["id"]), None)
    # `decisionView` publie l'effet par son NOM d'`EffectType`, pas par son ordinal (une premiere
    # version de ce probe lisait une cle `type` inexistante et rendait TOUJOURS `[]` -- un canal
    # muet qui se serait lu comme << le natif ne pose rien >>).
    eff_nat = sorted({str(e.get("name")) for e in ((he2 or {}).get("effects") or [])
                      if e.get("name")})

    return {"cas": cas, "regime": regime, "powup": pw["id"], "hero": he["id"],
            "tuile_visee": list(cible), "d": d,
            "powup_vivant_natif": _vivant(dv2, pw["id"]), "powup_vivant_port": powup_vivant_port,
            "stat": cle_snap,
            "natif_avant": avant_nat, "natif_apres": apres_nat,
            "port_avant": avant_port, "port_apres": apres_port,
            "shield_natif": [sh_avant_nat, sh_apres_nat],
            "shield_port": [sh_avant_port, sh_apres_port],
            "hp_natif": [hp_avant_nat, (he2 or {}).get("hp")],
            "hp_port": [hp_avant_port, hp_apres_port],
            "effet_attendu": EFFET[cas].name,
            "effet_pose_natif": EFFET[cas].name in eff_nat,
            "effet_pose_port": EFFET[cas].name in eff_port,
            "effets_natif": eff_nat, "effets_port": eff_port}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--cas", required=True, choices=sorted(CAS))
    ap.add_argument("--state-file", required=True)
    ap.add_argument("--seed-bc", required=True)
    ap.add_argument("--regime", default="nominal", choices=("nominal", "hors-tuile"))
    ap.add_argument("--no-build", action="store_true")
    ap.add_argument("--keep", action="store_true")
    a = ap.parse_args()

    powup_id = CAS[a.cas][0]
    sf, sbc = Path(a.state_file), Path(a.seed_bc)
    if not a.no_build:
        if not sbc.exists() and injecter(sbc, powup_id):
            return 2
        if build(sf, powup_id, sbc):
            return 2
    if not sf.exists():
        print("ABSENT: %s" % sf)
        return 2
    rid = int(json.loads(sf.read_text(encoding="utf-8"))["runnerId"])
    sess = _resolve_session()

    def rpc(name, params, to=90):
        return _unwrap(_rpc(sess, name, params, to))

    bind_live_rpc(lambda m, b=None, t=60: rpc(m, b if b is not None else {}, int(t)))
    print("runner=%d session=%s cas=%s regime=%s" % (rid, sess, a.cas, a.regime))
    out = mesurer(rid, rpc, a.cas, a.regime)
    for k in sorted(out):
        print("  %-22s %s" % (k, out[k]))

    rc = 3 if "erreur" in out else 0
    if rc == 0:
        d_nat = (None if None in (out["natif_avant"], out["natif_apres"])
                 else int(out["natif_apres"]) - int(out["natif_avant"]))
        d_port = (None if None in (out["port_avant"], out["port_apres"])
                  else int(out["port_apres"]) - int(out["port_avant"]))
        ds_nat = out["shield_natif"][1] - out["shield_natif"][0]
        ds_port = out["shield_port"][1] - out["shield_port"][0]
        dh_nat = (None if None in out["hp_natif"] else out["hp_natif"][1] - out["hp_natif"][0])
        dh_port = (None if None in out["hp_port"] else out["hp_port"][1] - out["hp_port"][0])
        print("  DELTA stat   natif=%s port=%s" % (d_nat, d_port))
        print("  DELTA shield natif=%s port=%s" % (ds_nat, ds_port))
        print("  DELTA hp     natif=%s port=%s" % (dh_nat, dh_port))
        if a.regime == "nominal":
            # TEMOIN NON DEGENERE : un accord a zero ne prouverait rien.
            if not d_nat and not ds_nat:
                print("  VERDICT: TEMOIN DEGENERE -- le natif n'a RIEN fait, la comparaison est vide")
                rc = 4
            elif not (out["effet_pose_natif"] and out["effet_pose_port"]):
                print("  VERDICT: DIVERGENCE -- l'effet %s n'est pas pose des DEUX cotes "
                      "(natif=%s port=%s)" % (out["effet_attendu"], out["effet_pose_natif"],
                                              out["effet_pose_port"]))
                rc = 1
            elif d_nat == d_port and ds_nat == ds_port and dh_nat == dh_port:
                print("  VERDICT: ACCORD")
            else:
                print("  VERDICT: DIVERGENCE")
                rc = 1
        else:
            # CONTRE-EPREUVE : les DEUX doivent etre inertes, ET le power-up doit avoir survecu.
            if out["powup_vivant_natif"] is not True:
                print("  VERDICT: CONTRE-EPREUVE INVALIDE -- le power-up est mort quand meme")
                rc = 4
            elif (d_nat, ds_nat, d_port, ds_port, dh_nat, dh_port) == (0, 0, 0, 0, 0, 0):
                print("  VERDICT: ACCORD (les deux INERTES hors tuile)")
            else:
                print("  VERDICT: DIVERGENCE hors tuile")
                rc = 1
    if not a.keep:
        try:
            rpc("disposeRunner", {"runnerId": rid}, 30)
            print("  runner %d dispose" % rid)
        except Exception as e:                       # noqa: BLE001 -- on DIT l'echec
            print("  dispose KO: %s" % str(e)[:160])
    return rc


if __name__ == "__main__":
    raise SystemExit(main())
