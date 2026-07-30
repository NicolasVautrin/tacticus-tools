"""probe #27-4e -- A/B causal LIVE de SorcerousFacade (1100), la route ALLIEE.

CE QUI EST TESTE, et pourquoi ce n'est pas « le moteur choisit la meme chose »

1100 porte un `damageProfile` (Psychic) mais son masque de ciblage vaut
`0x402 = TargetIsFriendly | TargetMatchesDynamicRule` : depuis #217, le VETO de
`engine.ai.state_bridge._is_attack_ability` la sort de la route ENNEMIE, donc elle n'entre JAMAIS
dans `plans` et `ComparableAbilityGenerator._best_attack` ne la voit pas. Avant ce port, le moteur ne
pouvait donc **structurellement pas** proposer 1100, quelle que soit la geometrie -- et il ne devait
surtout pas la reprendre par la route ennemie. Ce probe mesure les DEUX faces DANS LE MEME MONTAGE :

  * la route ALLIEE marche (bras `route OFF` = `NONATTACK_PLAYBOOKS` vide -> controle de deblocage) ;
  * la route ENNEMIE reste FERMEE (`plans` natif ET offline ne portent aucune eval (1100, ennemi)).

FORMULE PORTEE (`IdunBattle.AI.Playbook.Loki.SorcerousFacadePlaybook$$CalculateCustomUtility`) :

    GetUtility(UtilityType.Tile).EvaluateMovement(case(caster, GetMainTile(target)))
  - GetUtility(UtilityType.Tile).EvaluateMovement(case(caster, casterPosition))

soit `Tile(tuile de la CIBLE) - Tile(tuile candidate)`. Comme la route ajoute ensuite
`u_full = u + Tile(tuile candidate)`, l'utilite d'action porte EXACTEMENT
`Tile(tuile de la CIBLE) + <predictions>` : le terme de la tuile candidate S'ANNULE. C'est la tuile
que le caster occupera APRES l'echange de positions.

MONTAGE (board MC1_67, dont l'elevation va de 1 a 4 -- `Tile` y vaut 5 / 20 / 30 / 50) :

  Le caster `thousTzaangor` est place et **fige** (un `act move` consomme son mouvement ->
  `aiMovableTiles` rend 0 tuile, donc le sweep de tuiles est reduit a sa tuile courante et le terme
  Tile de l'attaque normale concurrente est CONSTANT). `ultraTitus` est colle a d=1 pour que la regle
  dynamique de 1100 soit satisfaite (`SorcerousFacadeAbility$$GetDynamicInvalidTargetReason` exige
  que le caster puisse porter son attaque normale) et pour que `GetTarget` rende un `sel` non nul.
  SEUL l'allie Psyker `thousSorcerer` bouge, sur QUATRE tuiles d'elevations 1/2/3/4 **toutes a la
  MEME distance 4 du caster** (donc aucune n'entre dans une feuille d'adjacence : la geometrie que
  voit l'attaque normale est rigoureusement identique dans les quatre bras).

  CONTROLE CROISE (ce qui exclut un terme « booleen sur la tuile de l'allie ») : la MEME tuile
  d'allie (elevation 4) est rejouee avec le caster sur une tuile d'elevation 4. Un terme qui ne
  regarderait que la tuile de la CIBLE donnerait le meme choix dans les deux configurations ; un
  terme en DIFFERENCE bascule. C'est le pendant du test de linearite de HeavyWarpFlamer.

Usage :
    python probe_27_4e_facade_ab.py            # build + mesure + contre-epreuves moteur
    python probe_27_4e_facade_ab.py --keep     # ne dispose pas les runners
ASCII only ; exit 0 = tout conforme.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

import probe_27_3_live as L

HERE = Path(__file__).resolve().parent
LOGS = HERE.parents[1] / "logs"
BOARD = "MC1_67"
SEED = 1100
FACADE = 1100

P_UNITS = "thousTzaangor,thousSorcerer"
A_UNITS = "ultraTitus,ultraCalgar"
CASTER_VID = "thousTzaangor"
ALLY_VID = "thousSorcerer"
TGT_VID = "ultraTitus"
FAR_VID = "ultraCalgar"
FAR_TILE = "6,0"

# Les deux configurations. `tile` = valeur ATTENDUE du composite Tile(7) a cette elevation sur
# MC1_67 (min 1 / max 4) -- recalculee live par le probe, jamais codee en dur dans le moteur.
CONFIGS = {
    # caster sur elevation 1 (Tile = 5) : toute tuile d'allie plus haute donne un custom POSITIF.
    "caster_bas": {"state": "rs_facade_low.json", "caster": "2,7", "tgt": "3,7",
                   "ally": [("e1", "6,8"), ("e2", "5,5"), ("e3", "1,4"), ("e4", "2,3")]},
    # caster sur elevation 4 (Tile = 50) : la MEME tuile d'allie e4 donne un custom NUL.
    "caster_haut": {"state": "rs_facade_high.json", "caster": "2,3", "tgt": "3,3",
                    "ally": [("e4", "6,3")]},
}


def _run(args) -> None:
    subprocess.run([sys.executable, "rl_duel.py"] + args, cwd=str(HERE),
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False)


def _units(rid: int) -> dict:
    dv = L._rpc("decisionView", [{"runnerId": rid, "allAbilities": True}])
    out = {}
    for u in (dv.get("units") or []):
        p = u.get("pos") or {}
        out[u.get("visualId")] = (u.get("id"), (p.get("col"), p.get("row")))
    return out


def _move(rid: int, state: Path, unit: int, to: str) -> None:
    _run(["act", "move", "--unit", str(unit), "--to", to,
          "--state-file", str(state), "--runner", str(rid)])


def _assert_placed(rid: int, want) -> None:
    """Un `act move` REFUSE ne leve rien : les bras degenerent en UN seul etat et l'accord
    moteur<->natif y est trivialement vrai. On VERIFIE les positions obtenues."""
    pos = {i: p for _v, (i, p) in _units(rid).items()}
    bad = [(u, to, pos.get(u)) for u, to in want
           if pos.get(u) != tuple(int(x) for x in to.split(","))]
    if bad:
        raise SystemExit("placement REFUSE -- montage invalide, pas de mesure : %s"
                         % ["u%s voulu=%s obtenu=%s" % (u, to, got) for u, to, got in bad])


def build(cfg: dict) -> tuple:
    state = LOGS / cfg["state"]
    _run(["build", "--seed", str(SEED), "--board", BOARD, "--rank", "17",
          "--p-units", P_UNITS, "--a-units", A_UNITS, "--state-file", str(state)])
    rid = int(json.loads(state.read_text(encoding="utf-8"))["runnerId"])
    ids = {v: i for v, (i, _p) in _units(rid).items()}
    # ORDRE : la cible et le lointain d'abord, l'allie ensuite, le CASTER EN DERNIER (son `act move`
    # fige son sweep de tuiles ; le fixer avant les autres ne changerait rien mais brouille la lecture).
    want = ((ids[TGT_VID], cfg["tgt"]), (ids[FAR_VID], FAR_TILE),
            (ids[ALLY_VID], cfg["ally"][0][1]), (ids[CASTER_VID], cfg["caster"]))
    for unit, to in want:
        _move(rid, state, unit, to)
    _assert_placed(rid, want)
    return rid, state


def _normal_id(rid: int, caster: int) -> int:
    """L'id CONCRET de l'attaque normale du caster (per-unite : jamais 17). Lu des `attackPlans`
    natifs -- l'ability non-1100 qui y figure."""
    dv = L._rpc("decisionView", [{"runnerId": rid, "allAbilities": True}])
    for pl in (dv.get("attackPlans") or []):
        if pl.get("unitId") != caster:
            continue
        for ev in (pl.get("evals") or []):
            if ev.get("abilityId") != FACADE:
                return int(ev["abilityId"])
    raise SystemExit("aucune ability d'attaque dans les attackPlans du caster -- montage invalide")


def _facade_evals_native(rid: int, caster: int) -> list:
    """Re-preuve #217 cote LIVE : les evals `(1100, cible)` presentes dans `decisionView.attackPlans`
    et leur `rankCount`. Le gate natif `AttackQuery$$GetBestTileToAttackFrom` rend `null` pour toute
    cible ennemie d'une ability `TargetIsFriendly` -> `rankCount` doit valoir 0 partout."""
    dv = L._rpc("decisionView", [{"runnerId": rid, "allAbilities": True}])
    out = []
    for pl in (dv.get("attackPlans") or []):
        if pl.get("unitId") != caster:
            continue
        for ev in (pl.get("evals") or []):
            if ev.get("abilityId") == FACADE:
                out.append((ev.get("targetId"), ev.get("rankCount")))
    return out


def _native(rid: int, caster: int, normal: int, enemies: list, ally: int) -> tuple:
    pairs = {}
    for tgt in enemies:
        r = L._rpc("pairUtility", [{"runnerId": rid, "unitId": caster,
                                    "targetId": tgt, "abilityType": normal}])
        pairs[tgt] = r.get("utility")
    # `pairUtility(1100, <allie>)` = l'etage PREDICTION du playbook natif, SANS le custom ni le
    # terme Tile (preuve L3 #64). C'est la seule facon de comparer `MakeDamagePredictions` etage par
    # etage au lieu de fitter la bascule.
    pairs["ability%d" % FACADE] = L._rpc(
        "pairUtility", [{"runnerId": rid, "unitId": caster,
                         "targetId": ally, "abilityType": FACADE}]).get("utility")
    dr = L._rpc("aiDryRunAllUnits", [{"runnerId": rid}])
    chosen = (None, None)
    for u in (dr.get("units") or []):
        if u.get("unitId") != caster:
            continue
        for m in (u.get("proposed") or []):
            if m.get("cls") == "ActiveAbilityMessage":
                chosen = (m.get("abilityType"), m.get("targetId"))
    return pairs, chosen


def _engine(rid: int, caster: int) -> dict:
    """Decisions MOTEUR sur le MEME etat, plus les deux contre-epreuves :
      * `on`      : telle quelle ;
      * `zero`    : custom de 1100 force a 0 -> le terme est-il NECESSAIRE ?
      * `noroute` : `NONATTACK_PLAYBOOKS` vide -> etat d'AVANT le port (controle de deblocage).
    Rend aussi le custom, les deux termes Tile qui le composent, et la re-preuve #217 OFFLINE."""
    import engine_validate as EV
    import engine.playbook as PB
    from engine import weights as W
    from engine.playbook import scene as _scene
    from engine.playbook import nonattack as NA
    from engine.playbook.base import tile_utility
    from engine.ai import context as AICTX
    from engine.ai import state_bridge as SB

    sid = L.INV._session_id()
    rpc = lambda m, b, t: EV._r(sid, m, b, t)          # noqa: E731
    dv = rpc("decisionView", {"runnerId": rid, "allAbilities": True, "maxRank": 32}, 180)
    mov = rpc("aiMovableTiles", {"runnerId": rid}, 60)
    mov_by_unit = {u.get("unitId"): u for u in (mov.get("units") or [])}
    wt = W.load()
    predictor = _scene.build_predictor(rpc, rid)
    ctx = AICTX.build(rpc, rid, dv, mov_by_unit, caster, wt, predictor)

    pb = PB.REGISTRY.get(FACADE)
    targets = pb.eligible_targets(ctx, FACADE)
    ally = targets[0] if targets else None
    custom = pb.calculate_custom_utility(ctx, ctx.origin, ally, FACADE) if ally is not None else None
    tile_caster = tile_utility(ctx, ctx.origin)
    from engine.playbook.loki_custom import _main_tile_of
    apos = _main_tile_of(ctx, ally) if ally is not None else None
    tile_ally = tile_utility(ctx, apos) if apos is not None else None
    sel = pb._get_target(ctx, ctx.origin)
    should = pb.should_execute(ctx, ctx.origin, ally, FACADE, 0.0) if ally is not None else None
    events = (pb.make_damage_predictions(ctx, ctx.origin, ally, FACADE) or []) \
        if ally is not None else []
    n_ev = len(events)
    # ETAGE PREDICTION du port, a comparer bit a bit avec `pairUtility(1100)` natif.
    u_pred, bk = pb.calculate_utility_from_predictions(ctx, ctx.origin, ally, FACADE, events) \
        if events else (0.0, [])

    on = EV.engine_decide(sid, rid, dv, mov_by_unit, caster, wt, predictor)
    orig = type(pb).calculate_custom_utility
    type(pb).calculate_custom_utility = lambda self, c, tile, target, aid: 0.0
    try:
        zero = EV.engine_decide(sid, rid, dv, mov_by_unit, caster, wt, predictor)
    finally:
        type(pb).calculate_custom_utility = orig
    saved = dict(NA.NONATTACK_PLAYBOOKS)
    NA.NONATTACK_PLAYBOOKS.clear()
    try:
        noroute = EV.engine_decide(sid, rid, dv, mov_by_unit, caster, wt, predictor)
    finally:
        NA.NONATTACK_PLAYBOOKS.update(saved)

    # Re-preuve #217 OFFLINE, DANS CE MEME ETAT : 1100 ne doit ni etre classee ATTAQUE, ni figurer
    # dans les abilities d'attaque du porteur, ni produire une paire (1100, ennemi) dans `plans`.
    _n, _cfg = SB._resolve_ability(FACADE)
    offline = {
        "is_attack": SB._is_attack_ability(FACADE, _cfg),
        "kind": SB._ability_kind(FACADE, _n, _cfg),
        "in_attack_abilities": FACADE in [a for a, _r in SB._attack_abilities(CASTER_VID)],
        "plans_1100": [(ev.get("targetId"), ev.get("rankCount"))
                       for ev in ((ctx.plans.get(caster) or {}).get("evals") or [])
                       if ev.get("abilityId") == FACADE],
    }
    return {"on": (on.get("ability"), on.get("target")), "to": on.get("to"),
            "zero": (zero.get("ability"), zero.get("target")),
            "noroute": (noroute.get("ability"), noroute.get("target")),
            "custom": custom, "tile_caster": tile_caster, "tile_ally": tile_ally,
            "ally": ally, "sel": sel, "should_execute": should, "n_events": n_ev,
            "u_pred": u_pred, "bk": bk,
            "ev": [(e.target, (e.composite_fields() or {}).get("healthDmgMin"),
                    (e.composite_fields() or {}).get("healthDmgMax")) for e in events],
            "targets": targets, "offline217": offline}


def measure(rid: int, label: str) -> dict:
    u = _units(rid)
    caster = u[CASTER_VID][0]
    normal = _normal_id(rid, caster)
    enemies = [u[TGT_VID][0], u[FAR_VID][0]]
    pairs, chosen = _native(rid, caster, normal, enemies, u[ALLY_VID][0])
    ev1100 = _facade_evals_native(rid, caster)
    e = _engine(rid, caster)
    print("  --- %s ---" % label)
    print("      positions : caster=%s allie=%s cible=%s lointain=%s"
          % (u[CASTER_VID][1], u[ALLY_VID][1], u[TGT_VID][1], u[FAR_VID][1]))
    print("      Tile(caster)=%.4f Tile(allie)=%.4f -> custom=%.4f"
          % (e["tile_caster"], e["tile_ally"], e["custom"]))
    print("      pairUtility(%d) natives : %s" % (normal, pairs))
    print("      natif  : ability=%s target=%s" % chosen)
    print("      moteur : on=%s to=%s | custom=0 -> %s | route OFF -> %s"
          % (e["on"], e["to"], e["zero"], e["noroute"]))
    print("      selecteur GetTarget -> sel=%s | ShouldExecute=%s | events=%d | cibles=%s"
          % (e["sel"], e["should_execute"], e["n_events"], e["targets"]))
    print("      ETAGE PREDICTION : natif pairUtility(%d)=%s | moteur u_pred=%.6f  bk=%s  ev=%s"
          % (FACADE, pairs.get("ability%d" % FACADE), e["u_pred"], e["bk"], e["ev"]))
    print("      #217 natif : evals (1100, cible)=%s | offline : %s" % (ev1100, e["offline217"]))
    return {"native": chosen, "engine": e, "pairs": pairs, "normal": normal,
            "ev1100_native": ev1100, "caster": caster}


def run_ab() -> tuple:
    """Monte les deux configurations, joue TOUS les bras et rend `(rows, runners)`. Les runners NE
    SONT PAS disposes : c'est a l'appelant (le probe le fait en fin de `main`, le test dans son
    teardown)."""
    LOGS.mkdir(parents=True, exist_ok=True)
    rows, runners = {}, []
    for cname, cfg in CONFIGS.items():
        rid, state = build(cfg)
        runners.append(rid)
        print("\n=== configuration %s (runner %d) ===" % (cname, rid))
        u = _units(rid)
        for label, tile in cfg["ally"]:
            if _units(rid)[ALLY_VID][1] != tuple(int(x) for x in tile.split(",")):
                _move(rid, state, u[ALLY_VID][0], tile)
                _assert_placed(rid, ((u[ALLY_VID][0], tile),))
            rows["%s/%s" % (cname, label)] = measure(rid, "allie %s @%s" % (label, tile))
    return rows, runners


def verdicts(rows: dict) -> list:
    """Les invariants que le port doit tenir. Rend la liste des echecs (vide = conforme)."""
    fails = []
    print("\n=== verdicts ===")
    for key, r in rows.items():
        nat_ab = r["native"][0]
        eng_ab = r["engine"]["on"][0]
        if nat_ab != eng_ab:
            fails.append("%s : natif=%s moteur=%s (DESACCORD)" % (key, nat_ab, eng_ab))
        # la route ENNEMIE doit rester fermee dans TOUS les bras
        if any((rc or 0) > 0 for _t, rc in r["ev1100_native"]):
            fails.append("%s : le natif rend une eval (1100, ennemi) a rankCount > 0" % key)
        o = r["engine"]["offline217"]
        # `plans_1100` porte les evals NATIVES a `rankCount = 0` (le gate
        # `AttackQuery$$GetBestTileToAttackFrom` a fait son travail) : `_best_attack` les saute.
        # Ce qui serait une REGRESSION, c'est un `rankCount > 0`, ou la promotion de 1100 en
        # ability d'ATTAQUE du porteur.
        if o["is_attack"] or o["kind"] != "ally" or o["in_attack_abilities"] \
                or any((rc or 0) > 0 for _t, rc in o["plans_1100"]):
            fails.append("%s : REGRESSION #217 offline -> %s" % (key, o))
        print("  %-22s custom=%+8.3f natif=%-5s moteur=%-5s zero=%-5s noroute=%-5s"
              % (key, r["engine"]["custom"], nat_ab, eng_ab,
                 r["engine"]["zero"][0], r["engine"]["noroute"][0]))

    # bascule attendue DANS la configuration `caster_bas` : custom nul -> attaque normale ;
    # custom positif -> 1100. On ne l'IMPOSE pas bras par bras (c'est le natif qui tranche) ; on
    # exige que natif et moteur basculent ENSEMBLE (deja verifie ci-dessus) et que le terme soit
    # NECESSAIRE la ou 1100 gagne.
    for key, r in rows.items():
        if r["native"][0] == FACADE:
            if r["engine"]["zero"][0] == FACADE:
                fails.append("%s : 1100 gagne encore avec custom=0 -> le terme n'est PAS necessaire"
                             % key)
            if r["engine"]["noroute"][0] == FACADE:
                fails.append("%s : 1100 gagne encore route OFF -> la route n'est PAS le deblocage"
                             % key)
    if not any(r["native"][0] == FACADE for r in rows.values()):
        fails.append("aucun bras ou le natif joue 1100 -- le montage ne discrimine rien")
    if not any(r["native"][0] != FACADE for r in rows.values()):
        fails.append("aucun bras ou le natif REFUSE 1100 -- le montage ne discrimine rien")
    return fails


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--keep", action="store_true")
    args = ap.parse_args()
    rows, runners = run_ab()
    fails = verdicts(rows)
    if not args.keep:
        for rid in runners:
            try:
                L._rpc("disposeRunner", [{"runnerId": rid}])
            except Exception as exc:                      # noqa: BLE001
                print("  (dispose runner %d : %s)" % (rid, exc))
    if fails:
        print()
        for f in fails:
            print("FAIL:", f)
        return 1
    print("\nOK: natif et moteur basculent ENSEMBLE sur tous les bras ; le terme custom est "
          "NECESSAIRE et la route ALLIEE est le deblocage ; la route ENNEMIE (#217) reste fermee "
          "dans le meme montage (natif ET offline).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
