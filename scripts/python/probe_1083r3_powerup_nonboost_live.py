"""#1083-r3 -- CONFRONTATION live des `PowerUp_*` NON-BOOST portes (natif vs port).

Meme montage que #1083-r1 (`docs/rl/case-1083-powerup-le-board-ne-confronte-rien.md` §4 -- le BOARD
n'y est pour RIEN) : `catalog_inject --units powup<X>` puis `rl_duel build --seed-bc ...
--explicit-stats powup<X> --a-units "powup<X>,..."`, avec `--a-place`/`--place` pour poser le
power-up A COTE du ramasseur.

CE QUE CE PROBE AJOUTE A CELUI DE LA TRANCHE 1 -- et c'est tout l'enjeu : les deux mecaniques de
cette tranche sont INOBSERVABLES sur un ramasseur au repos.

  * `PowerUp_Healing` soigne `HealPercentage` % des PV MAXIMAUX. Sur un ramasseur INTACT, le soin
    est plafonne a zero : natif et port rendent `+0` et l'accord serait VIDE. Le probe force donc
    un ramasseur BLESSE (`--unit-stat <hero>:RemainingHealth=<bas>`) et REFUSE de conclure si le
    delta attendu est nul.
  * `PowerUp_ReactivateAbility` re-arme une active. Sur un ramasseur dont l'active est DEJA
    disponible, le reset est un no-op : meme piege. Le probe CONSOMME donc l'active (un
    `applyAction` d'ability REEL) avant de capturer l'etat, et verifie que la consommation a
    MORDU avant d'aller plus loin.

C'est la lecon des deux faux negatifs de la tranche 1, appliquee en amont : un temoin degenere ne
prouve pas qu'un port est juste, il prouve qu'on n'a rien mesure.

CONTRE-EPREUVE (`--regime hors-tuile`) : le ramasseur va sur une tuile VOISINE. Natif et port
doivent etre INERTES et le power-up SURVIVRE -- ce bras separe << le port joue le trigger >> de
<< le port agit a chaque deplacement >>.
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
from engine.entities.stats import StatPart, StatType                     # noqa: E402
from engine.runner.components import (ActiveAbilitiesComponent, HealthComponent,  # noqa: E402
                                      ShieldComponent, StatsComponent, UnitComponent)
from engine.runner.messages import MoveUnitMessage                       # noqa: E402
from engine.runner.prng import IntBasedMersenneTwister                   # noqa: E402
from engine.runner.runner import Runner                                  # noqa: E402
from engine.runner.snapshot import bind_live_rpc, load_state             # noqa: E402

#: cas -> (unite-objet, nom gameconfig du passif)
CAS = {
    "healing": ("powupHealing", "PowerUp_Healing"),
    "reactivate": ("powupReactivateAbility", "PowerUp_ReactivateAbility"),
}
BOARD, SEED = "MC1_67", "777"
#: Le RAMASSEUR : un HERO du pool, MON equipe. Le trigger ne lui demande que `!HasTrait(Steppable)`
#: et `IsAlive`. `ultraCalgar` est celui de la tranche 1 -- meme porteur, comparaison facilitee.
RAMASSEUR = "ultraCalgar"
TUILE_POWUP = (2, 1)
TUILE_HERO = (1, 1)
TUILE_VOISINE = (0, 1)
#: Cas reactivate : l ennemi qui sert a CONSOMMER l active, place ADJACENT au ramasseur.
TUILE_NOB = (1, 0)
#: PV COURANTS forces sur le ramasseur pour le cas `healing`. Bas devant sa Health (~9537 au rank
#: 17) pour que le soin de 100 % des PV MAX ne soit PAS plafonne a zero.
HP_BLESSE = 500


def _unwrap(r):
    return r.get("result") if isinstance(r, dict) and "result" in r else r


def injecter(seed_bc: Path, powup: str) -> int:
    p = subprocess.run([sys.executable, "catalog_inject.py", "--units", powup,
                        "--out", str(seed_bc)], cwd=str(_PYDIR), capture_output=True, text=True)
    if p.returncode != 0:
        print("INJECT KO rc=%d\n%s" % (p.returncode, (p.stderr or "")[-800:]))
    return p.returncode


def build(state_file: Path, powup: str, seed_bc: Path, cas: str) -> int:
    args = [sys.executable, "rl_duel.py", "build", "--seed", SEED, "--board", BOARD, "--no-ai",
            "--seed-bc", str(seed_bc), "--state-file", str(state_file),
            "--explicit-stats", powup,
            "--p-units", RAMASSEUR, "--a-units", "%s,orksNob" % powup,
            "--a-place", "%s:%d,%d" % (powup, TUILE_POWUP[0], TUILE_POWUP[1]),
            "--place", "%s:%d,%d" % (RAMASSEUR, TUILE_HERO[0], TUILE_HERO[1])]
    if cas == "reactivate":
        # L'ennemi doit etre A PORTEE du ramasseur : sans lui, le cast de consommation part hors
        # portee et le natif rend `ok: true / mutated: false` -- un no-op silencieux qui laisse
        # l'active ARMEE, donc un temoin degenere. (`--a-place` se REPETE, il n'accepte pas `;`.)
        args += ["--a-place", "orksNob:%d,%d" % (TUILE_NOB[0], TUILE_NOB[1])]
    if cas == "healing":
        # TEMOIN NON DEGENERE : sans blessure, un soin de 100 % des PV MAX rend +0 des deux cotes.
        args += ["--unit-stat", "%s:RemainingHealth=%d" % (RAMASSEUR, HP_BLESSE)]
    p = subprocess.run(args, cwd=str(_PYDIR), capture_output=True, text=True)
    if p.returncode != 0:
        print("BUILD KO rc=%d" % p.returncode)
        print((p.stderr or p.stdout or "")[-1500:])
    return p.returncode


def _snap_unit(snap, uid):
    return next((u for u in (snap.get("units") or []) if u.get("entityId") == uid), None)


def _shield_natif(snap, uid) -> int:
    u = _snap_unit(snap, uid) or {}
    return sum(int((s.get("amount") if isinstance(s, dict) else s) or 0)
               for s in (u.get("shields") or []))


def _shield_port(state, uid) -> int:
    e = state.get_entity(int(uid))
    sh = e.get_component(ShieldComponent) if e is not None else None
    return 0 if sh is None else int(sh.get_total_shield() or 0)


def _hp_port(state, uid):
    e = state.get_entity(int(uid))
    hc = e.get_component(HealthComponent) if e is not None else None
    return None if hc is None else int(hc.hp)


def _actives_natif(dv, uid) -> dict:
    """`decisionView.units[].abilities` (avec `allAbilities: true`) -- MIRROR EXACT du lecteur
    `engine/runner/snapshot.py::_active_abilities`, pour que les deux cotes lisent LE MEME canal.

    ⚠ LES CLES NE SONT PAS CELLES QU'ON DEVINE, et la premiere version de ce probe s'y est fait
    prendre : le canal publie `{id, name, kind, usable, cooldown, disabled}` -- donc `id` (PAS
    `abilityType` ni `type`) et `usable` (PAS `canStillBeUsed`). Elle rendait `{}` cote natif
    pendant que le port rendait `{1000: ...}`, ce qui se serait lu comme << le natif n'a aucune
    active >> et aurait fait passer un TEMOIN DEGENERE pour une divergence. Meme famille de faux
    negatif que les deux de la tranche 1.

    Le filtre `kind in (active, granted)` est lui aussi repris : l'entree `normal` n'a ni `usable`
    ni `cooldown`, et le natif l'exclut de toute facon du reset
    (`StaticBattleRules.ActiveAbility$$IsRegularAttack`)."""
    u = next((x for x in (dv.get("units") or []) if x.get("id") == uid), None)
    out = {}
    for a in ((u or {}).get("abilities") or []):
        if a.get("kind") not in ("active", "granted") or a.get("id") is None:
            continue
        out[int(a["id"])] = (bool(a.get("usable", True)), a.get("cooldown"))
    return out


def _actives_port(state, uid) -> dict:
    e = state.get_entity(int(uid))
    c = e.get_component(ActiveAbilitiesComponent) if e is not None else None
    out = {}
    for a in (getattr(c, "abilities", None) or []):
        t = getattr(a, "ability_type", None)
        if t is None:
            continue
        out[int(t)] = (getattr(a, "can_still_be_used", None), getattr(a, "remaining_cooldown", None))
    return out


def _vivant(dv, uid):
    u = next((x for x in (dv.get("units") or []) if x.get("id") == uid), None)
    return None if u is None else bool(u.get("alive"))


def _consommer_active(rpc, rid, hero_id, dv):
    """Cas `reactivate` : CONSOMMER une active avant de capturer, sinon le reset est un no-op.

    Rend `(ok, detail)`. On ne devine pas quelle ability est castable : on lit celles que le
    `decisionView` declare utilisables, et on prend la premiere que le natif ACCEPTE."""
    avant = _actives_natif(dv, hero_id)
    castables = [t for t, (peut, _cd) in avant.items() if peut]
    if not castables:
        return False, "aucune active castable au depart (avant=%s)" % avant
    # Cibles candidates : les unites ADVERSES vivantes, power-up EXCLU (marcher dessus est
    # justement ce qu'on veut faire APRES, et le frapper le tuerait par un autre chemin).
    moi = next((u for u in (dv.get("units") or []) if u.get("id") == hero_id), {})
    cands = [u["id"] for u in (dv.get("units") or [])
             if u.get("team") != moi.get("team") and u.get("alive") is not False
             and not str(u.get("visualId") or "").startswith("powup")]
    essais = []
    for t in castables:
        for cible in cands:
            res = rpc("applyAction", {"runnerId": rid, "action": {
                "kind": "ability", "casterId": hero_id, "targetId": cible,
                "abilityType": int(t)}}, 90)
            a0 = (res.get("actions") or [{}])[0] if isinstance(res, dict) else {}
            # ⚠ `ok` NE SUFFIT PAS, et c'est mesure : un cast hors portee (ou sur une cible que
            # l'ability refuse) rend `ok: true` avec `mutated: false`, `changes: []` et
            # `actionConsumed: false` -- RIEN ne s'est passe. La premiere version de ce probe s'y
            # est fiee et a rendu un TEMOIN DEGENERE en croyant avoir consomme l'active. Le
            # discriminant est `mutated`.
            essais.append({"ability": int(t), "cible": cible, "ok": bool(res.get("ok"))
                           if isinstance(res, dict) else False,
                           "mutated": a0.get("mutated"), "consumed": a0.get("actionConsumed")})
            if a0.get("mutated"):
                return True, {"ability": int(t), "cible": cible, "essais": essais}
    return False, ("aucun cast n'a MUTE l'etat (ok sans mutated = no-op silencieux) : %s" % essais)


def mesurer(rid: int, rpc, cas: str, regime: str) -> dict:
    powup_id, passif = CAS[cas]
    dv = rpc("decisionView", {"runnerId": rid, "maxRank": 1, "allAbilities": True,
                              "includeInactive": True}, 90)
    units = dv.get("units") or []
    pw = next((u for u in units if (u.get("visualId") or "") == powup_id), None)
    he = next((u for u in units if (u.get("visualId") or "") == RAMASSEUR), None)
    if pw is None or he is None:
        return {"erreur": "montage: powup=%s hero=%s" % (pw is not None, he is not None)}

    consomme = None
    # ⚠ On consomme l'active DANS LES DEUX REGIMES, y compris hors-tuile. Une contre-epreuve qui
    # laisserait l'active ARMEE ne verifierait que les PV et le bouclier : elle ne pourrait PAS
    # distinguer << le port ne re-arme pas hors tuile >> de << il n'y avait rien a re-armer >>.
    # C'est le meme vice de temoin degenere, transpose au bras negatif.
    if cas == "reactivate":
        ok, detail = _consommer_active(rpc, rid, he["id"], dv)
        if not ok:
            return {"erreur": "TEMOIN DEGENERE impossible a monter : %s" % detail}
        consomme = detail
        dv = rpc("decisionView", {"runnerId": rid, "maxRank": 1, "allAbilities": True,
                                  "includeInactive": True}, 90)
        he = next((u for u in (dv.get("units") or []) if u.get("id") == he["id"]), he)

    ppos, hpos = pw.get("pos") or {}, he.get("pos") or {}
    cible = ((ppos.get("col"), ppos.get("row")) if regime == "nominal" else TUILE_VOISINE)
    d = abs(int(hpos.get("col")) - int(cible[0])) + abs(int(hpos.get("row")) - int(cible[1]))
    if d < 1 or d > 3:
        return {"erreur": "geometrie: hero=%s cible=%s d=%d"
                          % ((hpos.get("col"), hpos.get("row")), cible, d)}

    ob = rpc("observeBattle", {"runnerId": rid}, 60)
    snap = rpc("combatSnapshot", {"runnerId": rid}, 60)
    from engine.entities.pathfinding.board import Board                   # noqa: PLC0415
    bg = rpc("boardGraph", {"runnerId": rid}, 60)
    if not (isinstance(bg, dict) and bg.get("tiles")):
        return {"erreur": "boardGraph indisponible -- AUCUNE mesure n'a eu lieu"}
    state = load_state(dv, ob, snap, board=Board(bg["tiles"], adjacency="native_sym"))
    if getattr(state, "effects", None) is None:
        return {"erreur": "pas d'EffectsState -- l'effet serait indecidable"}
    sc = state.get_entity(pw["id"]).get_component(StatsComponent)
    passifs = list(getattr(getattr(sc, "ctx", None), "passive_abilities", None) or [])
    if passif not in passifs:
        return {"erreur": "passif %s non monte cote port (passifs=%s)" % (passif, passifs)}

    hp_avant_nat, hp_avant_port = he.get("hp"), _hp_port(state, he["id"])
    sh_avant_nat, sh_avant_port = _shield_natif(snap, he["id"]), _shield_port(state, he["id"])
    act_avant_nat, act_avant_port = _actives_natif(dv, he["id"]), _actives_port(state, he["id"])

    # --- PORT : rejoue le MEME deplacement depuis la MEME capture -------------------------------
    s0 = rpc("dumpRng", {"runnerId": rid}, 30)
    if isinstance(s0, dict) and s0.get("ok"):
        rng = IntBasedMersenneTwister()
        rng.mt, rng.mti = list(s0["mt"]), s0["mti"]
        state.rng = rng
    Runner(state).install_default_handlers(20).apply(
        MoveUnitMessage(he["id"], (int(cible[0]), int(cible[1]))))
    hp_apres_port, sh_apres_port = _hp_port(state, he["id"]), _shield_port(state, he["id"])
    act_apres_port = _actives_port(state, he["id"])
    pwe = state.get_entity(pw["id"])
    puc = pwe.get_component(UnitComponent) if pwe is not None else None
    powup_vivant_port = None if puc is None else bool(puc.alive)
    eff_port = sorted({str(getattr(e, "name", "") or "")
                       for e in ((state.effects.by_unit.get(he["id"]) or []) if state.effects else [])})

    # --- NATIF ----------------------------------------------------------------------------------
    res = rpc("applyAction", {"runnerId": rid, "action": {
        "kind": "move", "unitId": he["id"], "to": {"col": int(cible[0]), "row": int(cible[1])}}}, 90)
    if not (isinstance(res, dict) and res.get("ok")):
        return {"erreur": "move live KO: %s" % str(res)[:220]}
    dv2 = rpc("decisionView", {"runnerId": rid, "maxRank": 1, "allAbilities": True,
                               "includeInactive": True}, 90)
    snap2 = rpc("combatSnapshot", {"runnerId": rid}, 60)
    he2 = next((u for u in (dv2.get("units") or []) if u.get("id") == he["id"]), None)
    eff_nat = sorted({str(e.get("name")) for e in ((he2 or {}).get("effects") or []) if e.get("name")})

    return {"cas": cas, "regime": regime, "powup": pw["id"], "hero": he["id"],
            "consomme": consomme, "tuile_visee": list(cible), "d": d,
            "powup_vivant_natif": _vivant(dv2, pw["id"]), "powup_vivant_port": powup_vivant_port,
            "hp_natif": [hp_avant_nat, (he2 or {}).get("hp")],
            "hp_port": [hp_avant_port, hp_apres_port],
            "shield_natif": [sh_avant_nat, _shield_natif(snap2, he["id"])],
            "shield_port": [sh_avant_port, sh_apres_port],
            "actives_natif": [act_avant_nat, _actives_natif(dv2, he["id"])],
            "actives_port": [act_avant_port, act_apres_port],
            "effets_natif": eff_nat, "effets_port": eff_port}


def _verdict(out, cas, regime) -> int:
    dh_nat = (None if None in out["hp_natif"] else out["hp_natif"][1] - out["hp_natif"][0])
    dh_port = (None if None in out["hp_port"] else out["hp_port"][1] - out["hp_port"][0])
    ds_nat = out["shield_natif"][1] - out["shield_natif"][0]
    ds_port = out["shield_port"][1] - out["shield_port"][0]
    print("  DELTA hp     natif=%s port=%s" % (dh_nat, dh_port))
    print("  DELTA shield natif=%s port=%s" % (ds_nat, ds_port))

    av_n, ap_n = out["actives_natif"]
    av_p, ap_p = out["actives_port"]
    rearmees_nat = sorted(t for t in ap_n if av_n.get(t, (None, None))[0] is False
                          and ap_n[t][0] is True)
    rearmees_port = sorted(t for t in ap_p if av_p.get(t, (None, None))[0] is False
                           and ap_p[t][0] is True)

    if regime == "hors-tuile":
        if out["powup_vivant_natif"] is not True:
            print("  VERDICT: CONTRE-EPREUVE INVALIDE -- le power-up est mort quand meme")
            return 4
        if cas == "reactivate":
            # Le bras negatif n'a de valeur que si une active etait DESARMEE au depart : sinon
            # << rien n'a ete re-arme >> est vrai trivialement.
            desarmees = sorted(t for t, (peut, _c) in av_n.items() if peut is False)
            if not desarmees:
                print("  VERDICT: CONTRE-EPREUVE DEGENEREE -- aucune active desarmee au depart, "
                      "donc << non re-armee >> ne prouve rien (avant=%s)" % av_n)
                return 4
            print("  DESARMEES au depart : %s | RE-ARMEES natif=%s port=%s"
                  % (desarmees, rearmees_nat, rearmees_port))
            if rearmees_nat or rearmees_port:
                print("  VERDICT: DIVERGENCE hors tuile -- une active a ete re-armee sans crush")
                return 1
        if (dh_nat, dh_port, ds_nat, ds_port) == (0, 0, 0, 0):
            print("  VERDICT: ACCORD (les deux INERTES hors tuile)")
            return 0
        print("  VERDICT: DIVERGENCE hors tuile")
        return 1

    if cas == "healing":
        if not dh_nat and not ds_nat:
            print("  VERDICT: TEMOIN DEGENERE -- le natif n'a NI soigne NI pose de bouclier")
            return 4
        if dh_nat == dh_port and ds_nat == ds_port:
            print("  VERDICT: ACCORD")
            return 0
        print("  VERDICT: DIVERGENCE")
        return 1

    # reactivate : l'observable est l'ETAT DES ACTIVES, pas les PV (calcule en tete de fonction,
    # parce que la contre-epreuve hors-tuile s'en sert aussi).
    print("  RE-ARMEES natif=%s port=%s" % (rearmees_nat, rearmees_port))
    if not rearmees_nat:
        print("  VERDICT: TEMOIN DEGENERE -- le natif n'a re-arme AUCUNE active "
              "(avant=%s apres=%s)" % (av_n, ap_n))
        return 4
    if rearmees_nat == rearmees_port and ds_nat == ds_port:
        print("  VERDICT: ACCORD")
        return 0
    print("  VERDICT: DIVERGENCE")
    return 1


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
        if build(sf, powup_id, sbc, a.cas):
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
    rc = 3 if "erreur" in out else _verdict(out, a.cas, a.regime)
    if not a.keep:
        try:
            rpc("disposeRunner", {"runnerId": rid}, 30)
            print("  runner %d dispose" % rid)
        except Exception as e:                       # noqa: BLE001 -- on DIT l'echec
            print("  dispose KO: %s" % str(e)[:160])
    return rc


if __name__ == "__main__":
    raise SystemExit(main())
