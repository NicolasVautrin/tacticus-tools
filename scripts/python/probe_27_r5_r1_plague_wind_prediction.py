"""probe #27-r5-r1 -- les TROIS batchs de `MakeDamagePredictions` de 1035 et 1093.

CE QUI EST MESURE
-----------------
`IdunBattle.AI.Playbook.Loki.PlagueWindPlaybook$$MakeDamagePredictions` (1035) et
`IdunBattle.AI.Playbook.Loki.MortarionsPlagueWindPlaybook$$MakeDamagePredictions` (1093)
enchainent TROIS `ComparablePlaybook<T>$$GenerateMultiHitAttackPredictions` -- un par vague, avec
sa propre formule de degat et le MEME `GetHits()` -- puis `AddRange` des trois. Le port n'en rendait
qu'UN (chemin generique mono-cible). L'oracle est `aiPlaybookPredict`, qui invoque le
`MakeDamagePredictions` NATIF : on compare la LISTE ENTIERE d'events, par cible et par champ.

Le facteur `Summon` de 1093 (`If(HasTrait(<DSLSelectors+0x60> = Target, 2 = Summon),
Multiply(<avg>, <DSLFormulas+0x28> = Direct(2)), <avg>)`) porte sur la **CIBLE PRINCIPALE**, jamais
sur l'unite frappee : la formule est evaluee UNE FOIS, hors de la boucle de
`GenerateMultiHitAttackPredictions`, sur l'`AbilityEntities` du message. Les deux bras `summon_*`
existent pour trancher exactement ce point.

MONTAGE (board MC1_67, seed 909)
--------------------------------
UN seul build par bras, DEUX abilities mesurees dessus :
  * `deathTyphus`     porte 1035 nativement (present dans `rl_duel build --list-pool`) ;
  * `deathBlightlord` porte 1093 par GREFFE (`catalog_inject.write_grafted_seed_bc(kind="active")`
    -- 1093 est absente des `BC.Abilities.ActiveAbilities` du seed, et poser la seule liste de
    l'unite echoue EN SILENCE au build, cf. #27-r5).

Grappe d'ennemis en LIGNE, lue au `boardGraph` (porte d'elevation comprise) :
    T = (3,1)  cible principale       -> vague 1
    V = (3,2)  voisin de T            -> vague 2
    W = (3,3)  voisin de V, PAS de T  -> vague 3
    F = (0,1)  temoin, loin de tout   -> aucune vague
Une geometrie a 3 anneaux est ce qui rend les trois batchs SEPAREMENT observables : les trois
plages de degat de la config different (1093 : 1109-1385 / 1662-1939 / 2770-3878), donc un port qui
raterait une vague, ou qui melangerait deux bases, se voit sur les VALEURS et pas seulement sur le
compte.

BRAS
----
  plain        : aucun trait pose                -> facteur 1 partout, pour les DEUX abilities
  summon_T     : T porte `Summon`                -> 1093 : x2 sur les TROIS vagues (V et W ne sont
                                                    PAS des summons -- c'est le quirk) ; 1035 : x1
  summon_V     : V porte `Summon`, T non         -> 1093 : x1 PARTOUT, y compris sur V lui-meme
                                                    (le trait de l'unite frappee n'entre pas)

MUTATIONS ADVERSARIALES (le port, pas le natif)
-----------------------------------------------
  waves  : `_MAKE_DMG_EXTRA_EVENTS` vide pour 1035/1093 -> retour a UN event  => ROUGE partout
  summon : `wave_damage_formula` rend toujours l'avg nue                      => ROUGE sur summon_T
                                                                                 SEUL (deborde zero)
  quirk  : le `HasTrait` porte sur l'unite FRAPPEE au lieu de la cible        => ROUGE sur summon_T
                                                                                 ET summon_V

Usage (depuis scripts/python, ASCII only) :
    python probe_27_r5_r1_plague_wind_prediction.py --all
    python probe_27_r5_r1_plague_wind_prediction.py --arm plain
    python probe_27_r5_r1_plague_wind_prediction.py --dispose
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

import probe_27_3_live as L
from engine.entities.active_ability_type import ActiveAbilityType

HERE = Path(__file__).resolve().parent
LOGS = HERE.parents[1] / "logs"
SEED_BC = LOGS / "bc_27r5r1_plague_wind.json"
STATE = LOGS / "rs_27r5r1_plague_wind.json"
BOARD = "MC1_67"
SEED = 909

PW = int(ActiveAbilityType.PlagueWind)                    # 1035 = 0x40b
MPW = int(ActiveAbilityType.MortarionsPlagueWind)         # 1093 = 0x445

CASTER_PW = "deathTyphus"          # porteur NATIF de 1035 (pool)
CASTER_MPW = "deathBlightlord"     # porteur GREFFE de 1093 (pool, meme faction)
P_UNITS = "%s,%s" % (CASTER_PW, CASTER_MPW)

TGT = "necroWarden"                # T -- cible principale (vague 1)
SEC = "astraBullgryn"              # V -- vague 2
TER = "orksWarboss"                # W -- vague 3
FAR = "astraPrimarisPsy"           # F -- temoin hors de toute vague
A_UNITS = "%s,%s,%s,%s" % (TGT, SEC, TER, FAR)

T = (3, 1)
V = (3, 2)
W = (3, 3)
F = (0, 1)
LAYOUT = {TGT: T, SEC: V, TER: W, FAR: F}

# Champs compares event par event -- les MEMES que #305 (`probe_305_massdriver_splash`).
CMP_KEYS = ("appliedHits", "healthDmgMin", "healthDmgMax", "rawHealthDmgMin", "rawHealthDmgMax")

# Un bras = la ligne `BC.Units[].Traits` d'UNE unite (le reste est identique). `None` = aucun patch.
ARMS = {"plain": None, "summon_T": (TGT, ["Summon"]), "summon_V": (SEC, ["Summon"])}


def _run(args) -> subprocess.CompletedProcess:
    return subprocess.run([sys.executable, "rl_duel.py"] + args, cwd=str(HERE),
                          capture_output=True, text=True, check=False)


def _runner_id() -> int:
    return int(json.loads(STATE.read_text(encoding="utf-8"))["runnerId"])


def _dv(rid: int) -> dict:
    return L._rpc("decisionView", [{"runnerId": rid, "allAbilities": True}])


def _units(rid: int) -> dict:
    """{visualId: (id, (col,row))} -- aucun id n'est jamais code en dur."""
    return {u["visualId"]: (u["id"], (u["pos"]["col"], u["pos"]["row"]))
            for u in (_dv(rid).get("units") or []) if u.get("pos")}


def write_graft_seed_bc() -> None:
    """1093 sur `deathBlightlord`. DEUX ecritures, dont une dont l'oubli est SILENCIEUX au build :
    la config d'ability (absente des `BC.Abilities.ActiveAbilities` du seed) ET la liste de l'unite.
    `catalog_inject.write_grafted_seed_bc(kind="active")` fait les deux (cf. #27-r5, meme verrou
    que #226)."""
    import catalog_inject as C
    LOGS.mkdir(parents=True, exist_ok=True)
    _p, reports = C.write_grafted_seed_bc(SEED_BC, ["%s:MortarionsPlagueWind" % CASTER_MPW],
                                          kind="active")
    import probe_380_seed_bc_patch_survival as S
    S.assert_survives(str(SEED_BC))
    for r in reports:
        print("[graft] %s.ActiveAbilities %s -> %s (configAdded=%s)"
              % (r["unitId"], r["activeAbilitiesBefore"], r["activeAbilitiesAfter"],
                 r["configAdded"]))


def build(arm: str) -> int:
    write_graft_seed_bc()
    cmd = ["build", "--seed", str(SEED), "--board", BOARD, "--rank", "17",
           "--seed-bc", str(SEED_BC), "--p-units", P_UNITS, "--a-units", A_UNITS,
           # PV HAUTS : aucun event ne doit etre CAPE par les PV restants de sa cible, sinon les
           # trois bases se confondent au plafond et le bras ne mesure plus la base.
           "--hp-target", "400000",
           # Les deux casters sont FIGES : `Movement=0` fixe la tuile d'attaque (une seule), donc
           # le meme `casterPosition` des deux cotes, et aucune migration de spawn entre les bras.
           "--unit-stat", "%s:Movement=0" % CASTER_PW,
           "--unit-stat", "%s:Movement=0" % CASTER_MPW,
           "--state-file", str(STATE)]
    patch = ARMS[arm]
    if patch is not None:
        vid, traits = patch
        # `--unit-stat` separe les CHAMPS par une virgule : le JSON ne doit pas en contenir.
        cmd += ["--unit-stat", "%s:Traits=%s" % (vid, json.dumps(traits, separators=(",", ":")))]
    prev = _runner_id() if STATE.exists() else None
    cp = _run(cmd)
    if not STATE.exists():
        raise SystemExit("build KO:\n%s\n%s" % (cp.stdout[-2000:], cp.stderr[-2000:]))
    rid = _runner_id()
    if prev is not None and rid == prev:
        raise SystemExit("build KO (runner %d re-servi) :\n%s" % (rid, cp.stdout[-2000:]))
    return rid


def dispose() -> None:
    if STATE.exists():
        _run(["dispose", "--state-file", str(STATE), "--runner", str(_runner_id())])
        print("[dispose] runner du state-file libere")


def place(rid: int) -> None:
    u = _units(rid)
    for vid, to in LAYOUT.items():
        if vid not in u:
            raise SystemExit("unite %r absente du runner" % vid)
        _run(["act", "move", "--unit", str(u[vid][0]), "--to", "%d,%d" % to,
              "--state-file", str(STATE), "--runner", str(rid)])
    got = {v: p for v, (_i, p) in _units(rid).items()}
    bad = [(v, to, got.get(v)) for v, to in LAYOUT.items() if got.get(v) != to]
    if bad:
        # Un `act move` REFUSE ne leve rien (`rl_duel` rend `ok=False` sur une unite adverse alors
        # que le deplacement EST applique) : seule la position RELUE fait foi.
        raise SystemExit("placement REFUSE -- montage invalide, pas de mesure : %s" % bad)


def _native_events(rid: int, cid: int, tid: int, ability: int, tile) -> list:
    """`aiPlaybookPredict` = `<X>Playbook$$MakeDamagePredictions` NATIF depuis `tile`."""
    r = L._rpc("aiPlaybookPredict", [{"runnerId": rid, "unitId": cid, "targetId": tid,
                                      "abilityType": ability,
                                      "col": int(tile[0]), "row": int(tile[1])}])
    if not r.get("ok"):
        raise SystemExit("aiPlaybookPredict KO (ability %d) : %r" % (ability, r))
    return r.get("events") or []


def _nat_fields(ev: dict) -> dict:
    hp = ev.get("hpBefore") or 0
    return {"appliedHits": ev.get("appliedHits") or 0,
            "healthDmgMin": min(ev.get("healthDmgMin") or 0, hp),
            "healthDmgMax": min(ev.get("healthDmgMax") or 0, hp),
            "rawHealthDmgMin": ev.get("willKillDmg") or 0,
            "rawHealthDmgMax": ev.get("mightKillDmg") or 0}


def _by_target(rows: list) -> dict:
    out: dict = {}
    for tid, f in rows:
        out.setdefault(tid, []).append(f)
    return out


def _ctx_for(rid: int, cid: int):
    """`AiDecisionContext` du caster sur le runner vivant (meme couture qu'`engine_validate`)."""
    import engine_validate as EV
    from engine import weights as W
    from engine.playbook import scene as _scene
    from engine.ai import context as AICTX
    sid = L.INV._session_id()

    def rpc(m, b, t):
        return EV._r(sid, m, b, t)

    dv = rpc("decisionView", {"runnerId": rid, "allAbilities": True, "maxRank": 32}, 180)
    mov = rpc("aiMovableTiles", {"runnerId": rid}, 60)
    mov_by_unit = {u.get("unitId"): u for u in (mov.get("units") or [])}
    predictor = _scene.build_predictor(rpc, rid)
    return AICTX.build(rpc, rid, dv, mov_by_unit, cid, W.load(), predictor)


def confront(rid: int, ctx, cid: int, tid: int, ability: int, tile) -> dict:
    """Confronte la LISTE ENTIERE d'events (les trois vagues), par cible et par champ."""
    from engine.playbook import get_playbook_or_default
    nat = _by_target([(e.get("targetId"), _nat_fields(e))
                      for e in _native_events(rid, cid, tid, ability, tile)])
    pb = get_playbook_or_default(ability)
    off_evs = pb.make_damage_predictions(ctx, tile, tid, ability) or []
    off = _by_target([(e.target, {k: e.composite_fields().get(k) for k in CMP_KEYS})
                      for e in off_evs])
    deltas, missing, extra = [], [], []
    for t, nevs in nat.items():
        oevs = off.get(t)
        if not oevs:
            missing.append(t)
            continue
        if len(oevs) != len(nevs):
            deltas.append({"target": t, "field": "n_events", "nat": len(nevs), "off": len(oevs)})
        for nf, of in zip(nevs, oevs):
            for k in CMP_KEYS:
                if nf.get(k) != of.get(k):
                    deltas.append({"target": t, "field": k, "nat": nf.get(k), "off": of.get(k)})
    for t in off:
        if t not in nat:
            extra.append(t)
    return {"nat": nat, "off": off, "deltas": deltas, "missing": missing, "extra": extra,
            "match": not deltas and not missing and not extra}


def _label(u: dict, tid) -> str:
    for vid, (uid, _p) in u.items():
        if uid == tid:
            return vid
    return str(tid)


def measure(rid: int, verbose: bool = True) -> dict:
    """Mesure les DEUX abilities sur l'etat courant du runner."""
    u = _units(rid)
    tid = u[TGT][0]
    out = {}
    for ability, caster_vid in ((PW, CASTER_PW), (MPW, CASTER_MPW)):
        cid, tile = u[caster_vid]
        ctx = _ctx_for(rid, cid)
        res = confront(rid, ctx, cid, tid, ability, tile)
        out[ability] = res
        if verbose:
            print("  [%d %s] caster=%s@%s cible=%s  match=%s"
                  % (ability, caster_vid, cid, tile, tid, res["match"]))
            for t in sorted(res["nat"], key=lambda x: (x is None, x)):
                for i, nf in enumerate(res["nat"][t]):
                    of = (res["off"].get(t) or [{}])[i] if i < len(res["off"].get(t) or []) else {}
                    print("     -> %-20s nat hits=%s dmg=[%s,%s] raw=[%s,%s] | port hits=%s "
                          "dmg=[%s,%s] raw=[%s,%s]"
                          % (_label(u, t), nf["appliedHits"], nf["healthDmgMin"],
                             nf["healthDmgMax"], nf["rawHealthDmgMin"], nf["rawHealthDmgMax"],
                             of.get("appliedHits"), of.get("healthDmgMin"),
                             of.get("healthDmgMax"), of.get("rawHealthDmgMin"),
                             of.get("rawHealthDmgMax")))
            if not res["match"]:
                print("     DELTAS=%s missing=%s extra=%s"
                      % (res["deltas"][:8], res["missing"], res["extra"]))
    return out


# ---------------------------------------------------------------- mutations adversariales
def _mutate(kind: str):
    """Mute le PORT (jamais le natif) et rend le callable de restauration."""
    from engine.playbook.prediction import abilities as PA
    from engine.playbook.prediction import plague_wind as PWM
    if kind == "waves":
        saved = {a: PA._MAKE_DMG_EXTRA_EVENTS.pop(a) for a in (PW, MPW)}
        return lambda: PA._MAKE_DMG_EXTRA_EVENTS.update(saved)
    if kind == "summon":
        orig = PWM.wave_damage_formula

        def _bare(ability_id, mn, mx):
            return PWM.min_max_damage_average(mn, mx)
        PWM.wave_damage_formula = _bare

        def _restore():
            PWM.wave_damage_formula = orig
        return _restore
    if kind == "quirk":
        # LA LECTURE NAIVE, celle que le decompile refute : le `HasTrait` porterait sur l'unite
        # FRAPPEE. On ne peut pas l'exprimer en changeant l'ARBRE (le sujet du `HasTrait` natif est
        # le selecteur `Target`) -- il faut deplacer l'EVALUATION dans la boucle, avec l'unite
        # frappee comme `target` du contexte. C'est exactement le second etage de la structure
        # native : `GenerateMultiHitAttackPredictions` evalue sa formule UNE FOIS, HORS boucle.
        orig = PWM.wave_events

        def _per_hit(scene, caster_id, target_id, ability_id, ability_name, attack_pos, ab, cfg):
            from engine.playbook.prediction.abilities import generate_multi_hit_attack_prediction
            from engine.runner.abilities.deathguard import plague_wind_wave_selectors
            from engine.playbook.probable_damage_event import ProbableDamageEvent
            if cfg is None or ab is None:
                return []
            hits = int((cfg.constants or {}).get(PWM.HITS_CONST) or 0)
            dctx = PWM.dsl_context(scene, caster_id, target_id)
            if not hits or dctx is None or dctx.target is None:
                return []
            _t1, t2, t3 = plague_wind_wave_selectors()
            evs = []
            for wave, sel in ((1, t2), (2, t3)):
                for u in sel.evaluate(dctx):
                    tid = (u or {}).get("id")
                    if tid is None:
                        continue
                    hit_ctx = PWM.dsl_context(scene, caster_id, tid)      # <-- LA MUTATION
                    base = PWM._wave_base(int(ability_id), ab, cfg, wave, hit_ctx)
                    if base <= 0:
                        continue
                    dp = generate_multi_hit_attack_prediction(
                        scene, caster_id, tid, ability_id, ability_name, attack_pos=attack_pos,
                        base_override=base, hits_override=hits)
                    if dp is not None:
                        evs.append(ProbableDamageEvent(target=tid, prediction=dp))
            return evs
        PWM.wave_events = _per_hit

        def _restore():
            PWM.wave_events = orig
        return _restore
    raise SystemExit("mutation inconnue : %r" % kind)


EXPECT_MUTATION = {
    # mutation -> {bras: doit ROUGIR ?}. Une mutation qui ne rougit NULLE PART ne garde rien ;
    # une qui rougit PARTOUT ne discrimine pas ce qu'elle pretend garder.
    "waves": {"plain": True, "summon_T": True, "summon_V": True},
    "summon": {"plain": False, "summon_T": True, "summon_V": False},
    "quirk": {"plain": False, "summon_T": True, "summon_V": True},
}


def run_arm(arm: str, mutations: bool = True) -> dict:
    rid = build(arm)
    place(rid)
    print("[bras %s] runner=%d" % (arm, rid))
    base = measure(rid)
    ok = all(r["match"] for r in base.values())
    print("[bras %s] ACCORD natif<->port : %s" % (arm, "OK" if ok else "KO"))
    muts = {}
    if mutations:
        for kind, per_arm in sorted(EXPECT_MUTATION.items()):
            restore = _mutate(kind)
            try:
                red = not all(r["match"] for r in measure(rid, verbose=False).values())
            finally:
                restore()
            want = per_arm[arm]
            muts[kind] = {"red": red, "want": want, "ok": red == want}
            print("  [mutation %-6s] rouge=%s (attendu %s) %s"
                  % (kind, red, want, "OK" if red == want else "KO"))
    return {"arm": arm, "rid": rid, "ok": ok, "base": base, "mutations": muts}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--arm", choices=sorted(ARMS))
    ap.add_argument("--all", action="store_true")
    ap.add_argument("--no-mutations", action="store_true")
    ap.add_argument("--dispose", action="store_true")
    a = ap.parse_args()
    if a.dispose:
        dispose()
        return 0
    arms = sorted(ARMS) if a.all else ([a.arm] if a.arm else ["plain"])
    ok = True
    for arm in arms:
        r = run_arm(arm, mutations=not a.no_mutations)
        ok = ok and r["ok"] and all(m["ok"] for m in r["mutations"].values())
    print("VERDICT: %s" % ("PASS" if ok else "FAIL"))
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
