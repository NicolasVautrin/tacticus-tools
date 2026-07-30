"""probe #289 -- ResurrectionOrb (1009, `necroOverlord` « Anuphet ») : la route non-attaque + les
TROIS etages de `IdunBattle.AI.Playbook.Loki.ResurrectionOrbPlaybook$$CalculateCustomUtility`.

CE QUI EST MESURE, et pourquoi ce n'est pas « le moteur choisit la meme chose »

L'utilite custom native vaut

    u = 90 x [ Count(GetPossibleResurrectTargets) > 0 ET Count(GetPossibleSpawnOrResurrectTiles) > 0 ]
      + 10 x GetNumSummonsFormula()

(poids `ResurrectionOrb_LikesResurrection` / `_LikesSummoning`, lus de `BC.Utilities`). Trois etages
qui se MESURENT SEPAREMENT, au lieu d'un scalaire a fitter :

  * `numSummons` = `Min(maxSummons, Count(tiles) - [hasResurrectTarget])` -> varie avec le NOMBRE DE
    HEX LIBRES adjacents a la TUILE CANDIDATE, donc d'une tuile a l'autre du balayage ;
  * `maxSummons` = `Min(Count(amis MORTS mecaniques) + TURNS_STARTED(caster), maxSummons_config)` ->
    monte d'un cran par ROUND et par mort mecanique amie ;
  * le forfait 90 est BOOLEEN et conditionne a une CONJONCTION (>=1 cible resurrectable ET >=1 tuile).

BRAS

  [1] VERROU     -- `_best_attack` ne peut PAS rendre 1009 : `make_damage_predictions` rend `[]`
                    (aucun `damageProfile`) donc `calculate_action_utility` rend `None`. Re-mesure a
                    chaque run : c'est ce qui distingue « le port marche » de « l'accord vient
                    d'ailleurs ». ⚠ Ce bras a CORRIGE une formulation repandue : « Comparable ABSENTE
                    de `ctx.plans` » n'est vrai que du cote OFFLINE -- en LIVE, `decisionView.
                    attackPlans` LISTE bien 1009 (a `rankCount = 0`, et sur des ENNEMIS alors que la
                    cible retenue est le CASTER). cf. `_verrou`.
  [2] VIVANT     -- aucun allie mort. `nResurrect = 0` -> le forfait 90 est ETEINT, u = 10 x numSummons.
                    Un ennemi one-shottable est colle au caster : l'attaque normale vaut plus que
                    10 x numSummons -> le natif ATTAQUE.
  [3] MORT       -- le MEME montage, l'allie `necroWarden` (Hero + Mechanical) en moins : `nResurrect`
                    passe a 1, u gagne 90 + un cran de `maxSummons` -> le natif CASTE 1009.
                    La BASCULE entre [2] et [3] est causee par le seul terme resurrection.
  [4] LINEARITE  -- le custom releve TUILE PAR TUILE : il doit valoir 10 x min(maxSummons, libres-hasRes),
                    donc DIFFERER entre un coin (peu de voisins) et le centre. Un terme booleen ou
                    constant est exclu par cette mesure.

Bras de CONTROLE moteur, dans chaque etat : `zero` (custom force a 0) et `noroute`
(`NONATTACK_PLAYBOOKS` vide = l'etat d'AVANT le port). Si aucun des deux ne fait diverger le moteur,
le terme ou la route est INERTE et l'accord ne prouve rien.

Usage :
    python probe_289_resurrection_orb.py --build [--engine]
    python probe_289_resurrection_orb.py --engine          # re-joue sur les runners des state-files
ASCII only.
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import probe_27_3_live as L

HERE = Path(__file__).resolve().parent
LOGS = HERE.parents[1] / "logs"
STATE_V = LOGS / "rs_289_vivant.json"      # bras [2] : allie VIVANT
STATE_M = LOGS / "rs_289_mort.json"        # bras [3] : allie MORT
BOARD = "MC1_67"
SEED = 909
ORB = 1009
NORMAL = 69

CASTER_VID = "necroOverlord"     # Anuphet -- porteur de 1009, DANS le pool rank 17
ALLY_VID = "necroWarden"         # Makhotep -- Hero + LivingMetal(-> Mechanical) : la cible du forfait 90
BAIT_VID = "ultraCalgar"         # l'attaque normale concurrente (colle au caster)

# ⚠ Le CASTER n'est JAMAIS deplace : un `act move` consomme son mouvement, et `aiMovableTiles` ne
# rend alors plus AUCUNE tuile pour lui -- `reach_nc` degenere en {origine} et le bras [4] LINEARITE
# (le custom d'une tuile a l'autre) devient impossible a mesurer. On lit sa tuile de SPAWN, qui est
# un coin du board (donc peu de voisins : c'est justement ce qui fait varier `numSummons`).
CASTER_TILE = "1,0"              # tuile de SPAWN du caster sur MC1_67 -- VERIFIEE, pas imposee
BAIT_TILE = "1,1"                # adjacent au caster -> attaque normale legale sans bouger
ALLY_SAFE = "0,2"                # bras [2] : hors d'atteinte du tour adverse, l'allie SURVIT
ALLY_BAIT = "4,6"                # bras [3] : au contact, l'IA adverse le tue au 1er tour

# PV des a-units. L'utilite de degat est ~ degat/PVmax : les baisser MONTE la `pairUtility` de
# l'attaque normale concurrente, donc DEPLACE le point de bascule -- on ne fitte aucun scalaire du
# port, on choisit ou l'on MESURE. Vise : pair + 1 (custom NormalAttack) entre 10 x numSummons
# (bras VIVANT) et 90 + 10 x numSummons (bras MORT).
# CALIBRE PAR MESURE, pas devine : a 2200 PV la `pairUtility` vaut 239.9 -> l'attaque normale ecrase
# les DEUX bras et rien ne bascule. L'utilite de degat etant ~ degat/PVmax, on la ramene par simple
# proportion dans la fenetre voulue : pair + 1 doit tomber ENTRE le custom du bras VIVANT (20) et
# celui du bras MORT (100 a l'origine, 120 au mieux).
HP_TARGET = 22000
HP_PLAYER = 300                  # p-units fragiles -> mort DETERMINISTE de l'allie au bras [3]
DMG_TARGET = 6000


def _run(args) -> None:
    subprocess.run([sys.executable, "rl_duel.py"] + args, cwd=str(HERE),
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False)


def _rid(state: Path) -> int:
    return int(json.loads(state.read_text(encoding="utf-8"))["runnerId"])


def _units(rid: int) -> dict:
    """{visualId: (id, (col,row), alive)} depuis `decisionView` -- aucun id hardcode."""
    dv = L._rpc("decisionView", [{"runnerId": rid, "allAbilities": True}])
    out = {}
    for u in (dv.get("units") or []):
        p = u.get("pos") or {}
        out[u.get("visualId")] = (u.get("id"), (p.get("col"), p.get("row")), bool(u.get("alive")))
    return out


def _move(rid: int, state: Path, unit: int, to: str) -> None:
    _run(["act", "move", "--unit", str(unit), "--to", to,
          "--state-file", str(state), "--runner", str(rid)])


def _assert_placed(rid: int, want) -> None:
    """Un `act move` REFUSE ne leve rien : les deux bras degenereraient en UN seul etat, ou l'accord
    est trivialement vrai. On refuse de MESURER plutot que de mesurer un montage invalide."""
    pos = {i: p for _v, (i, p, _a) in _units(rid).items()}
    bad = [(u, to, pos.get(u)) for u, to in want
           if pos.get(u) != tuple(int(x) for x in to.split(","))]
    if bad:
        raise SystemExit("placement REFUSE -- montage invalide, pas de mesure : %s"
                         % ["u%s voulu=%s obtenu=%s" % (u, to, got) for u, to, got in bad])


def _build(state: Path) -> int:
    _run(["build", "--seed", str(SEED), "--board", BOARD, "--rank", "17",
          "--p-units", "%s,%s" % (CASTER_VID, ALLY_VID),
          "--a-units", "tauCrisis,orksWarboss,%s" % BAIT_VID,
          "--hp-target", str(HP_TARGET), "--hp-player", str(HP_PLAYER),
          "--dmg-target", str(DMG_TARGET), "--state-file", str(state)])
    return _rid(state)


def _one_arm(state: Path, ally_to: str, expect_ally_alive: bool) -> int:
    """Monte UN bras. Les deux bras sont RIGOUREUSEMENT identiques -- meme seed, meme board, meme
    tour adverse joue (donc meme `TURNS_STARTED(caster)`, donc meme `maxSummons` hors morts) -- a
    UNE chose pres : la tuile ou part l'allie, qui decide s'il meurt. C'est ce qui fait de l'ecart
    entre les deux bras une MESURE du seul terme resurrection, et pas d'un melange de causes."""
    rid = _build(state)
    u = _units(rid)
    if u[CASTER_VID][1] != tuple(int(x) for x in CASTER_TILE.split(",")):
        raise SystemExit("le caster ne spawne pas en %s mais en %s -- le montage suppose sa tuile de "
                         "SPAWN (on ne le deplace pas, cf. CASTER_TILE)"
                         % (CASTER_TILE, u[CASTER_VID][1]))
    _move(rid, state, u[ALLY_VID][0], ally_to)          # SEULE difference entre les deux bras
    _run(["act", "endturn", "--state-file", str(state), "--runner", str(rid)])
    _run(["aiturn", "--state-file", str(state), "--runner", str(rid)])
    u = _units(rid)
    if u[ALLY_VID][2] != expect_ally_alive:
        raise SystemExit(
            "l'allie est alive=%s, attendu %s -- le bras n'existe pas, aucune mesure "
            "(ajuster ALLY_BAIT/ALLY_SAFE ou DMG_TARGET)" % (u[ALLY_VID][2], expect_ally_alive))
    want = ((u[BAIT_VID][0], BAIT_TILE),)               # l'appat vient au contact du caster
    for unit, to in want:
        _move(rid, state, unit, to)
    _assert_placed(rid, want)
    return rid


def build_vivant() -> int:
    """Bras [2] : l'allie part LOIN des ennemis -- il survit au tour adverse, `nResurrect` reste 0."""
    return _one_arm(STATE_V, ALLY_SAFE, expect_ally_alive=True)


def build_mort() -> int:
    """Bras [3] : l'allie part AU CONTACT -- l'IA adverse le tue (PV 300 vs frappe 6000) et il
    devient la cible resurrectable (Hero + LivingMetal => Mechanical), `nResurrect` passe a 1."""
    return _one_arm(STATE_M, ALLY_BAIT, expect_ally_alive=False)


def _native(rid: int, caster: int, bait: int) -> tuple[float, tuple, list]:
    pair = L._rpc("pairUtility", [{"runnerId": rid, "unitId": caster,
                                   "targetId": bait, "abilityType": NORMAL}]).get("utility")
    dr = L._rpc("aiDryRunAllUnits", [{"runnerId": rid}])
    chosen, msgs = (None, None), []
    for u in (dr.get("units") or []):
        if u.get("unitId") != caster:
            continue
        msgs = u.get("proposed") or []
        for m in msgs:
            if m.get("cls") == "ActiveAbilityMessage":
                chosen = (m.get("abilityType"), m.get("targetId"))
    return pair, chosen, msgs


def _engine(rid: int, caster: int) -> dict:
    """Decision MOTEUR + DECOMPOSITION PAR ETAGE, sur le meme etat.

    Les trois etages (`nResurrect` / `nTiles` / `maxSummons` / `numSummons` / `turnsStarted`) sont
    releves SEPAREMENT via les arbres DSL de l'ability -- c'est ce qui permet de localiser une
    divergence au lieu d'ajuster le total."""
    import engine_validate as EV
    import engine.playbook as PB
    from engine import weights as W
    from engine.playbook import scene as _scene
    from engine.playbook import nonattack as NA
    from engine.playbook.base import tile_utility
    from engine.playbook.resurrection_orb import _dsl_context
    from engine.entities.formulas import Count
    from engine.runner.abilities import necrons as N
    from engine.ai import context as AICTX

    sid = L.INV._session_id()
    rpc = lambda m, b, t: EV._r(sid, m, b, t)          # noqa: E731
    dv = rpc("decisionView", {"runnerId": rid, "allAbilities": True, "maxRank": 32}, 180)
    mov = rpc("aiMovableTiles", {"runnerId": rid}, 60)
    mov_by_unit = {u.get("unitId"): u for u in (mov.get("units") or [])}
    wt = W.load()
    predictor = _scene.build_predictor(rpc, rid)
    ctx = AICTX.build(rpc, rid, dv, mov_by_unit, caster, wt, predictor)
    pb = PB.REGISTRY[ORB]

    dctx = _dsl_context(ctx, ctx.origin)
    stages = {}
    if dctx is not None:
        stages = {
            "nResurrect": Count(N.resurrection_orb_possible_resurrect_targets()).evaluate(dctx),
            "nTiles": Count(N.resurrection_orb_possible_spawn_or_resurrect_tiles()).evaluate(dctx),
            "maxSummons": N.resurrection_orb_max_summons_formula().evaluate(dctx),
            "numSummons": N.resurrection_orb_num_summons_formula().evaluate(dctx),
            "turnsStarted": dctx.get_stat(dctx.caster, 12, 0, None),
        }
    # Le custom TUILE PAR TUILE : c'est la que la LINEARITE en `numSummons` se voit.
    per_tile = [(T, pb.calculate_custom_utility(ctx, T, caster, ORB), pb.is_caster_added(ctx, T))
                for T in (ctx.reach_nc or [])]

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
    return {"on": (on.get("ability"), on.get("target")), "to": on.get("to"),
            "zero": (zero.get("ability"), zero.get("target")),
            "noroute": (noroute.get("ability"), noroute.get("target")),
            "custom_origin": pb.calculate_custom_utility(ctx, ctx.origin, caster, ORB),
            "tile": tile_utility(ctx, ctx.origin), "stages": stages,
            "per_tile": per_tile, "targets": pb.eligible_targets(ctx, ORB),
            "verrou": _verrou(ctx)}


def _verrou(ctx) -> dict:
    """[1] VERROU : par quelle porte 1009 arrive-t-elle -- et surtout par laquelle elle N'ARRIVE PAS ?

    ⚠ MESURE du 2026-07-30, contre-intuitive et donc explicitement relevee ici : **en LIVE, 1009 EST
    listee dans `decisionView.attackPlans`** (le canal que `ctx.plans` recopie). Le critere « Comparable
    ABSENTE de `ctx.plans` » n'est donc exact que du cote OFFLINE (`state_bridge._is_attack_ability`
    rend False : pas de `damageProfile` ET masque `TargetIsCaster`). En live, l'ability y figure avec
    `rankCount = 0` sur CHAQUE ennemi -- et sur des ENNEMIS uniquement, alors que la cible que le natif
    retient est le CASTER lui-meme, qui n'apparait dans aucun eval.

    Le critere OPERANT, vrai dans les DEUX regimes, est donc : **`_best_attack` ne peut pas la rendre**.
    Il s'y casse deux fois -- `make_damage_predictions` rend `[]` (aucun `damageProfile`), donc
    `calculate_action_utility` rend `None` ; et aucun eval ne porte la bonne cible. On mesure CELA,
    pas la presence dans une table."""
    from engine.ai import action_generators as AG
    evals = [(ev.get("abilityId"), ev.get("targetId"), ev.get("rankCount"))
             for ev in ((ctx.plans.get(ctx.uid) or {}).get("evals") or [])]
    pb = PB_REGISTRY()[ORB]
    best = AG.ComparableAbilityGenerator()._best_attack(ctx)
    return {"in_plans": any(a == ORB for a, _t, _r in evals),
            "plans_orb_ranks": [(t, r) for a, t, r in evals if a == ORB],
            "best_attack_ability": (best[3] if best else None),
            "action_utility_is_none":
                pb.calculate_action_utility(ctx, ctx.origin, ctx.uid, ORB) is None}


def PB_REGISTRY():
    import engine.playbook as PB
    return PB.REGISTRY


def measure(rid: int, label: str, engine: bool) -> dict:
    u = _units(rid)
    caster, bait = u[CASTER_VID][0], u[BAIT_VID][0]
    pair, chosen, msgs = _native(rid, caster, bait)
    print("  --- %s ---" % label)
    print("      positions : caster=%s appat=%s | allie=%s alive=%s"
          % (u[CASTER_VID][1], u[BAIT_VID][1], u[ALLY_VID][1], u[ALLY_VID][2]))
    print("      pairUtility(69) native vs appat : %s" % pair)
    print("      natif  : ability=%s target=%s  (messages=%s)"
          % (chosen[0], chosen[1], [m.get("cls") for m in msgs]))
    row = {"pair": pair, "native": chosen, "caster": caster, "ally_alive": u[ALLY_VID][2]}
    if engine:
        e = _engine(rid, caster)
        row["engine"] = e
        print("      moteur : on=%s to=%s | custom(origine)=%s tile=%.4f"
              % (e["on"], e["to"], e["custom_origin"], e["tile"]))
        print("      etages : %s" % e["stages"])
        print("      controles : custom force a 0 -> %s | route DESACTIVEE -> %s"
              % (e["zero"], e["noroute"]))
        v = e["verrou"]
        print("      verrou : in_plans(LIVE)=%s ranks=%s | _best_attack rend %s | "
              "calculate_action_utility(1009)=None : %s"
              % (v["in_plans"], v["plans_orb_ranks"], v["best_attack_ability"],
                 v["action_utility_is_none"]))
        vals = sorted({c for _T, c, _a in e["per_tile"]})
        print("      custom par tuile : %d tuiles, valeurs distinctes=%s" % (len(e["per_tile"]), vals))
    return row


def run_arms(rv: int, rm: int, engine: bool) -> dict:
    """Deroule les DEUX bras sur des runners deja montes et rend les mesures. Extrait de `main` pour
    que la garde `tests/engine/test_resurrection_orb_decision_live.py` les rejoue sans dupliquer le
    montage (meme convention que `probe_27_4b_chronometron_ab.run_ab`)."""
    return {"vivant": measure(rv, "[2] VIVANT : aucun allie mort -> nResurrect=0", engine),
            "mort": measure(rm, "[3] MORT : allie Hero+Mechanical mort -> nResurrect=1", engine)}


def main() -> int:
    argv = sys.argv[1:]
    engine = "--engine" in argv
    if "--build" in argv:
        rv, rm = build_vivant(), build_mort()
    else:
        rv, rm = _rid(STATE_V), _rid(STATE_M)
    print("runners : VIVANT=%d MORT=%d | board=%s seed=%d hp-target=%d"
          % (rv, rm, BOARD, SEED, HP_TARGET))
    rows = run_arms(rv, rm, engine)

    print("\n=== SYNTHESE ===")
    ok = True
    for k in ("vivant", "mort"):
        nat = rows[k]["native"]
        line = "  %-7s : natif -> ability=%s target=%s" % (k, nat[0], nat[1])
        if engine:
            e = rows[k]["engine"]
            agree = (e["on"] == nat)
            ok = ok and agree
            line += " | moteur -> %s %s" % (e["on"], "MATCH" if agree else "DIVERGE")
        print(line)
    basc = (rows["vivant"]["native"][0] != ORB and rows["mort"]["native"][0] == ORB)
    print("  [3] BASCULE native causee par le forfait resurrection (VIVANT n'est pas 1009, MORT l'est) : %s"
          % ("OUI" if basc else "NON -- montage non concluant, ne rien conclure"))
    ok = ok and basc
    if engine:
        ev, em = rows["vivant"]["engine"], rows["mort"]["engine"]
        vv, vm = ev["verrou"], em["verrou"]
        verrou_ok = all(x["action_utility_is_none"] and x["best_attack_ability"] != ORB
                        for x in (vv, vm))
        print("  [1] VERROU  : `_best_attack` ne peut PAS rendre 1009 dans les deux bras "
              "(action_utility=None) : %s" % ("OUI" if verrou_ok else "NON -- la route est FAUSSE"))
        print("              (rappel MESURE : 1009 EST dans ctx.plans en LIVE -- %s -- "
              "mais a rankCount 0 et sur des ENNEMIS seulement)" % (vm["plans_orb_ranks"],))
        ok = ok and verrou_ok
        nec = em["zero"] != em["on"]
        deb = em["noroute"] != em["on"]
        print("  terme NECESSAIRE (custom=0 fait diverger le moteur au bras MORT)   : %s"
              % ("OUI" if nec else "NON -- le terme est INERTE"))
        print("  route NECESSAIRE (sans elle le moteur ne peut pas dire 1009)       : %s"
              % ("OUI" if deb else "NON -- la route est INERTE"))
        ok = ok and nec and deb
        s_v, s_m = ev["stages"], em["stages"]
        print("  [3] etage resurrection : nResurrect %s -> %s (attendu 0 -> 1)"
              % (s_v.get("nResurrect"), s_m.get("nResurrect")))
        ok = ok and s_v.get("nResurrect") == 0 and s_m.get("nResurrect") == 1
        # Le forfait est BOOLEEN : l'ecart de custom doit valoir 90 + un multiple de 10, jamais 90 x n.
        print("  [3] custom : %s (VIVANT) -> %s (MORT) ; ecart=%s"
              % (ev["custom_origin"], em["custom_origin"],
                 em["custom_origin"] - ev["custom_origin"]))
        vals = sorted({c for _T, c, _a in em["per_tile"]})
        lin = len(vals) > 1
        print("  [4] LINEARITE : le custom prend %d valeurs distinctes sur les tuiles %s : %s"
              % (len(vals), vals,
                 "un terme CONSTANT est exclu" if lin
                 else "NON ETABLIE sur ce montage (toutes les tuiles ont le meme nb de libres)"))
    print("(pense a disposer les runners : rl_duel.py dispose --state-file <...>)")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())

