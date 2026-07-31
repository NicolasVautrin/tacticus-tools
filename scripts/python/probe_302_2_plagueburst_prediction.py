"""probe #302 tranche 2 -- le terme de PREDICTION de `1169 PlagueburstMortar` (cible TUILE).

CE QUE CE PROBE ETABLIT
-----------------------
`IdunBattle.AI.Playbook.PlagueburstMortarPlaybook$$MakeDamagePredictions` (MIRROR du decompile
`rnca9r7q6c`) :

    GenerateMultiHitAttackPredictions(
        caster, casterPosition, target,
        targetsSelector = PlagueburstMortarAbility$$GetMainDamageTarget,
        damage          = VigilanceEternalAbility$$GetDamage   # corps DEDUPLIQUE de
                                                               # AActiveAbility$$MinMaxDamage(avg)
        hits            = AActiveAbility$$GetHits              # GetNumberConstant(0x2f = nrOfHits)
        profile         = Nullable(AActiveAbility$$GetDamageProfile),
        weightSelector  = null)

et `IdunBattleLogic.Entities.Abilities.Active.PlagueburstMortarAbility$$GetMainDamageTarget` =
`Filter( Enemies(Caster, Target, 3), GetIsValidAdjacentEnemyTrigger )`.

TROIS lectures decident du verdict, et aucune n'est deductible du nom :

1. **Le batch de prediction ne couvre QUE l'occupant de la tuile VISEE** -- `GetAdjacentDamageTargets`
   (les ennemis des tuiles adjacentes) n'entre PAS dans `MakeDamagePredictions`, alors qu'il entre
   dans `ExecuteBehaviour`. La face DECISION voit donc les voisins par le terme CUSTOM
   (`GetAdjacentEnemies` x poids, tranche 1) et le seul occupant par le terme PREDICTION.
2. `IdunBattle.Entities.Selectors.UnitsByTeamSelector$$CountOrAdd` teste l'equipe sur
   `UnitExtensions$$GetUnitOrMachine(entity)` mais **ajoute l'entite BRUTE** -- avec `Target` = une
   entite TUILE, l'ensemble natif est fait de TUILES. MESURE (`--stage`) :
   `pairUtility(caster, <tuile>, 1169)` == `pairUtility(caster, <unite qui l'occupe>, 1169)` a la
   derniere decimale, donc la resolution materialisee du port (`Enemies(Units(target_sel))`) est
   value-identique sur ce chemin.
3. Le predicat est FAUX sur un board frais, mais il n'est PAS structurellement mort (contraste avec
   1148, cf. `case-302` §8.4) : sa branche AURA s'allume par le seul DEPLACEMENT d'un porteur du
   trait `ContagionsOfNurgle` du camp du caster a portee de l'occupant. C'est le regime que la
   tranche 1 nommait « le port SOUS-ESTIME ».

L'ORACLE PAR ETAGE EXISTE (contrairement a ce que disait `case-302` §7 tranche 5) : depuis le
commit hooks `#302-t5`, `pairUtility` resout sa cible sur TOUS les `EntityType` et publie
`targetEntityType`. `pairUtility(caster, <tileEntityId>, 1169)` EST donc
`ComparablePlaybook$$CalculateUtilityFromPredictions` sur une cible tuile -- exactement le terme
que cette tranche porte (le CUSTOM n'y est pas). Le probe le verifie AVANT de mesurer et le dit
franchement si le bundle injecte est anterieur.

MONTAGE (le seul qui discrimine, cf. `docs/rl/case-302-2-prediction-tile-target.md`)
------------------------------------------------------------------------------------
Anneau hex autour de `CENTER = (3,4)` : trois ennemis sur trois voisins CONSECUTIFS
(`(3,5) - (4,4) - (4,3)`), caster `deathTyphus` (porteur du trait `ContagionsOfNurgle`) AU CENTRE.

| tuile visee | custom (10 x adjacents) | prediction | total |
|---|---|---|---|
| `CENTER (3,4)` | **30** (3 ennemis adjacents) | 0 (occupant = un ALLIE) | 30 |
| `(4,4)` (l'ennemi du MILIEU) | 20 | **> 0** | > 30 |

Sans le terme de prediction, l'argmax est `CENTER` ; avec, c'est `(4,4)`. La mutation qui vide
`MakeDamagePredictions` DOIT donc faire changer la TUILE choisie -- c'est la preuve que la garde
sait virer au rouge.

Usage (depuis scripts/python, ASCII only) :
    python probe_302_2_plagueburst_prediction.py --stage       # domaine + oracle PAR ETAGE
    python probe_302_2_plagueburst_prediction.py --decision    # decision complete + 3 bras
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
LOGS = HERE.parents[1] / "logs"

PLAGUEBURST = 1169
NORMAL = 69

CASTER_VID = "deathTyphus"          # porteur du trait 0x7eb = 2027 ContagionsOfNurgle
A_VID = "orksWarboss"               # l'ennemi du MILIEU de la chaine -> la tuile que la prediction gagne
B_VID = "necroWarden"
C_VID = "astraCreed"

CENTER = (3, 4)                     # voisins (ordre d'ANNEAU) : (3,5)-(4,4)-(4,3)-(3,3)-(2,3)-(2,4)
E_MID = (4, 4)                      # A : adjacent aux DEUX autres -> custom 20
E_LEFT = (3, 5)                     # B
E_RIGHT = (4, 3)                    # C
FAR = (0, 2)                        # bras TEMOIN : caster hors de portee d'aura

HP_TARGET = 20000                   # regime ou le terme de prediction pese > 10 (le pas du custom)


def _duel(args, state: Path, rid=None) -> None:
    extra = ["--runner", str(rid)] if rid is not None else []
    subprocess.run([sys.executable, "rl_duel.py"] + args + ["--state-file", str(state)] + extra,
                   cwd=str(HERE), stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False)


def _units(rid: int) -> dict:
    import probe_27_3_live as L
    dv = L._rpc("decisionView", [{"runnerId": rid, "allAbilities": True}])
    out = {}
    for u in (dv.get("units") or []):
        p = u.get("pos") or {}
        out[u.get("id")] = {"vid": u.get("visualId"), "pos": (p.get("col"), p.get("row")),
                            "team": u.get("team"), "hp": u.get("hp")}
    return out


def _caster_state(rid: int):
    import probe_27_3_live as L
    dv = L._rpc("decisionView", [{"runnerId": rid, "allAbilities": True}])
    c = next((u for u in (dv.get("units") or []) if u.get("visualId") == CASTER_VID), None)
    if c is None:
        return None, None, None
    ab = next((a for a in (c.get("abilities") or []) if a.get("id") == PLAGUEBURST), None)
    return c.get("id"), (ab or {}).get("cooldown"), dv.get("toActivate")


def build(state_name: str, caster_tile, hp_target: int = HP_TARGET) -> int:
    """Monte l'anneau discriminant PUIS purge le cooldown initial de 1169.

    Reprend la greffe de la tranche 1 (`probe_27_4g.write_graft_seed_bc` : `deathTyphus` porte 1169
    et RIEN d'autre) et le board `MC1_67`, mais place les unites en CHAINE autour de `CENTER` --
    c'est ce qui separe l'argmax-sans-prediction de l'argmax-avec.

    Les fins de tour ne sont pas cosmetiques : 1169 arrive avec `RemainingCooldownTurns = 1`, et un
    cooldown non purge se lit EXACTEMENT comme un refus de decision (lecon `case-302` §5)."""
    import probe_27_4g_plagueburst_route as G

    state = LOGS / state_name
    G.write_graft_seed_bc()
    _duel(["build", "--seed", str(G.SEED), "--board", G.BOARD, "--rank", G.RANK,
           "--seed-bc", str(G.SEED_BC), "--p-units", G.P_UNITS, "--a-units", G.A_UNITS,
           "--hp-target", str(hp_target)], state)
    rid = int(json.loads(state.read_text(encoding="utf-8"))["runnerId"])
    ids = {v["vid"]: i for i, v in _units(rid).items()}
    for vid, pos in ((A_VID, E_MID), (B_VID, E_LEFT), (C_VID, E_RIGHT),
                     (CASTER_VID, tuple(caster_tile))):
        _duel(["act", "move", "--unit", str(ids[vid]), "--to", "%d,%d" % pos], state, rid)
    for _ in range(4):
        _duel(["act", "endturn"], state, rid)
        cid, cd, to_act = _caster_state(rid)
        if cid is not None and cd in (None, 0) and cid in (to_act or []):
            return rid
    raise SystemExit("cooldown de 1169 jamais purge sur le runner %d" % rid)


def dispose(rid: int) -> None:
    import probe_27_3_live as L
    try:
        L._rpc("disposeRunner", [{"runnerId": rid}])
    except Exception:                                       # noqa: BLE001
        pass


def _ctx(rid: int, cid: int):
    """Contexte de DECISION du port sur l'etat courant du runner (meme montage que `engine_decide`)."""
    import engine_validate as EV
    import probe_27_3_live as L
    from engine import weights as W
    from engine.ai import context as AICTX
    from engine.playbook import scene as _scene

    sid = L.INV._session_id()
    rpc = lambda m, b, t: EV._r(sid, m, b, t)               # noqa: E731
    dv = rpc("decisionView", {"runnerId": rid, "allAbilities": True, "maxRank": 32}, 180)
    mov = rpc("aiMovableTiles", {"runnerId": rid}, 60)
    mov_by_unit = {u.get("unitId"): u for u in (mov.get("units") or [])}
    wt = W.load()
    predictor = _scene.build_predictor(rpc, rid)
    return sid, rpc, dv, mov_by_unit, wt, predictor, AICTX.build(rpc, rid, dv, mov_by_unit, cid,
                                                                 wt, predictor)


def per_tile(rid: int, cid: int, ctx) -> list:
    """Confrontation PAR ETAGE, tuile par tuile : `pairUtility` natif (=
    `ComparablePlaybook$$CalculateUtilityFromPredictions`) vs le meme terme cote port."""
    import engine.playbook as PB
    import probe_27_3_live as L

    pb = PB.REGISTRY[PLAGUEBURST]
    pos_by_tid = {t: p for p, t in (ctx.tile_id_by_pos or {}).items()}
    rows = []
    for tid in pb.eligible_targets(ctx, PLAGUEBURST):
        evs = pb.make_damage_predictions(ctx, ctx.origin, tid, PLAGUEBURST) or []
        port = (pb.calculate_utility_from_predictions(ctx, ctx.origin, tid, PLAGUEBURST, evs)[0]
                if evs else 0.0)
        r = L._rpc("pairUtility", [{"runnerId": rid, "unitId": cid, "targetId": tid,
                                    "abilityType": PLAGUEBURST}])
        rows.append({"tile": tid, "pos": pos_by_tid.get(tid), "nev": len(evs),
                     "custom": pb.calculate_custom_utility(ctx, ctx.origin, tid, PLAGUEBURST),
                     "port": port, "nat": r.get("utility"), "natType": r.get("targetEntityType"),
                     "err": r.get("error"),
                     "fields": [e.composite_fields() for e in evs]})
    return rows


def stage(hp_target: int) -> int:
    import probe_27_3_live as L

    rid = build("rs_302_2_stage.json", CENTER, hp_target)
    try:
        um = _units(rid)
        cid = next(i for i, v in um.items() if v["vid"] == CASTER_VID)
        print("runner=%d caster=u%d @%s hp-target=%d" % (rid, cid, um[cid]["pos"], hp_target))
        for i, v in sorted(um.items()):
            print("   u%-4s %-16s pos=%-8s team=%s hp=%s" % (i, v["vid"], v["pos"], v["team"],
                                                             v["hp"]))
        _sid, _rpc, _dv, _mov, _wt, _pred, ctx = _ctx(rid, cid)
        rows = per_tile(rid, cid, ctx)

        # [0] le harnais porte-t-il l'oracle par etage (hooks #302-t5) ?
        bad = [r for r in rows if r["err"]]
        print("\n[0] oracle PAR ETAGE (pairUtility sur cible TUILE) : %s"
              % ("INDISPONIBLE -- bundle injecte anterieur a #302-t5 : %s" % bad[0]["err"]
                 if bad else "OK (targetEntityType=%s = Tile)" % rows[0]["natType"]))
        if bad:
            return 2

        # [1] tuiles a terme NON NUL + accord
        nz = [r for r in rows if (r["nat"] or 0) or (r["port"] or 0)]
        print("\n[1] tuiles a terme de prediction NON NUL : %d / %d" % (len(nz), len(rows)))
        occ = {v["pos"]: v["vid"] for v in um.values()}
        for r in sorted(nz, key=lambda x: -(x["nat"] or 0)):
            d = (r["nat"] or 0.0) - (r["port"] or 0.0)
            print("    tile=%-4s pos=%-8s occ=%-14s nev=%d port=%.8f nat=%.8f delta=%+.3e"
                  % (r["tile"], r["pos"], occ.get(r["pos"], "-"), r["nev"], r["port"],
                     r["nat"] or 0.0, d))

        # [2] equivalence TUILE <-> UNITE qui l'occupe (lecture 2 de l'en-tete)
        print("\n[2] pairUtility(TUILE) vs pairUtility(UNITE occupante) :")
        for r in nz:
            uid = next((i for i, v in um.items() if v["pos"] == r["pos"]), None)
            if uid is None:
                continue
            ru = L._rpc("pairUtility", [{"runnerId": rid, "unitId": cid, "targetId": uid,
                                         "abilityType": PLAGUEBURST}])
            print("    pos=%-8s tuile=%.10f  unite u%d=%s  identiques=%s"
                  % (r["pos"], r["nat"], uid, ru.get("utility"),
                     abs((ru.get("utility") or 0) - (r["nat"] or 0)) < 1e-12))

        # [3] ATTRIBUTION du residu : `MinMaxDamage$$Avg` arrondit, le port garde le .5
        print("\n[3] attribution du residu (`IdunBattle.Core.Services.MinMaxDamage$$Avg`) :")
        for r in nz:
            for f in r["fields"]:
                s = int(f["healthDmgMin"]) + int(f["healthDmgMax"])
                print("    pos=%-8s min=%-6d max=%-6d somme %s -> port avg=%.1f, natif Round(avg,"
                      "MidpointRounding=0)=%d" % (r["pos"], f["healthDmgMin"], f["healthDmgMax"],
                                                  "PAIRE" if s % 2 == 0 else "IMPAIRE", s / 2.0,
                                                  _banker(s / 2.0)))
        return 0
    finally:
        dispose(rid)


def _banker(x: float) -> int:
    """`FixMath.NET.Fix64$$Round(value, midpointRounding = 0)` : demi vers le PAIR (le corps teste
    `((value >> 0x20) & 1) == 0` sur la partie entiere quand la fraction vaut exactement 0x80000000)."""
    import decimal
    return int(decimal.Decimal(x).quantize(0, rounding=decimal.ROUND_HALF_EVEN))


def _native_choice(rid: int, cid: int) -> tuple:
    import probe_27_3_live as L
    dr = L._rpc("aiDryRunAllUnits", [{"runnerId": rid}])
    for u in (dr.get("units") or []):
        if u.get("unitId") != cid:
            continue
        for m in (u.get("proposed") or []):
            if m.get("cls") == "ActiveAbilityMessage":
                return (m.get("abilityType"), m.get("targetId"))
    return (None, None)


def _arm(rid: int, label: str) -> dict:
    """Un bras de confrontation : natif, moteur, et le bras de MUTATION (terme de prediction vide)."""
    import engine_validate as EV
    import engine.playbook as PB

    um = _units(rid)
    cid = next(i for i, v in um.items() if v["vid"] == CASTER_VID)
    sid, _rpc, dv, mov_by_unit, wt, predictor, ctx = _ctx(rid, cid)
    pb = PB.REGISTRY[PLAGUEBURST]
    nat = _native_choice(rid, cid)
    on = EV.engine_decide(sid, rid, dv, mov_by_unit, cid, wt, predictor)
    orig = type(pb).make_damage_predictions
    type(pb).make_damage_predictions = lambda self, c, tile, target, aid: []
    try:
        mut = EV.engine_decide(sid, rid, dv, mov_by_unit, cid, wt, predictor)
    finally:
        type(pb).make_damage_predictions = orig
    rows = per_tile(rid, cid, ctx)
    pos_by_tid = {t: p for p, t in (ctx.tile_id_by_pos or {}).items()}
    print("\n=== bras %s === (caster u%d @%s)" % (label, cid, um[cid]["pos"]))
    print("  natif            = %s  (tuile %s)" % (nat, pos_by_tid.get(nat[1])))
    print("  moteur           = (%s, %s) to=%s  (tuile %s)"
          % (on.get("ability"), on.get("target"), on.get("to"), pos_by_tid.get(on.get("target"))))
    print("  moteur SANS pred = (%s, %s) to=%s  (tuile %s)"
          % (mut.get("ability"), mut.get("target"), mut.get("to"),
             pos_by_tid.get(mut.get("target"))))
    top = sorted(rows, key=lambda r: -(r["custom"] + r["port"]))[:4]
    for r in top:
        print("    tile=%-4s pos=%-8s custom=%5.1f pred_port=%9.4f pred_nat=%-20s total=%9.4f"
              % (r["tile"], r["pos"], r["custom"], r["port"], r["nat"],
                 r["custom"] + r["port"]))
    return {"caster": cid, "native": nat, "engine": (on.get("ability"), on.get("target")),
            "mutated": (mut.get("ability"), mut.get("target")),
            "accord": nat == (on.get("ability"), on.get("target")),
            "rows": rows}


def decision(hp_target: int) -> int:
    rid_a = build("rs_302_2_disc.json", CENTER, hp_target)
    try:
        a = _arm(rid_a, "DISCRIMINANT (caster au centre de l'anneau)")
    finally:
        dispose(rid_a)
    rid_b = build("rs_302_2_temoin.json", FAR, hp_target)
    try:
        b = _arm(rid_b, "TEMOIN (caster hors portee d'aura -> predicat FAUX partout)")
    finally:
        dispose(rid_b)
    print("\n=== VERDICT ===")
    print("  DISCRIMINANT : accord natif/moteur = %s | mutation change la cible = %s"
          % (a["accord"], a["engine"] != a["mutated"]))
    print("  TEMOIN       : accord natif/moteur = %s | mutation INERTE = %s (terme nul hors regime)"
          % (b["accord"], b["engine"] == b["mutated"]))
    ok = a["accord"] and b["accord"] and a["engine"] != a["mutated"] and b["engine"] == b["mutated"]
    print("  -> %s" % ("OK" if ok else "ECHEC"))
    return 0 if ok else 1


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--stage", action="store_true")
    ap.add_argument("--decision", action="store_true")
    ap.add_argument("--hp-target", type=int, default=HP_TARGET)
    a = ap.parse_args()
    if a.stage:
        return stage(a.hp_target)
    if a.decision:
        return decision(a.hp_target)
    ap.print_help()
    return 1


if __name__ == "__main__":
    sys.exit(main())
