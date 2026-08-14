"""#1066 (residu #970-r4) -- CONFRONTATION LIVE de la face DECISION `1159 MacroPlasmaIncinerator`.

CE QUE CE PROBE CONFRONTE, ET POURQUOI C'EST UN ACCORD NUMERIQUE
================================================================================================
L'utilite native est
`util = 1 + |zone| + Somme sur les tuiles LIBRES de la zone de |GetAdjacentEnemies(t, caster)|`
(`MacroPlasmaIncineratorPlaybook$$EvaluateNonComparable`, lu verbatim). Elle ne contient AUCUN
tirage -- contraste `1200 SquigLaunchas`, dont la confrontation ne pouvait porter que sur le gate.
Ici les deux cotes rendent un NOMBRE et une TUILE, donc on confronte les deux :

    NATIF  `ncPlaybookPredict(via="evaluate")` -> `bucketUtil` + `bucketAction.targetLow`
    PORT   `PLAYBOOKS[1159].generate_candidates(NCContext)` -> `pred` + `target`

Le masque de ciblage de 1159 est `RANGE_WHOLE_BOARD` (`.ctor` : `rules = 0x46000040`), donc
`fromHere` porte TOUTES les tuiles libres du plateau : l'argmax se joue sur des dizaines de
candidates aux utilites BIEN separees. Un accord y est beaucoup plus contraignant qu'un accord
sur deux ou trois cibles.

LE TEMOIN NON NUL, ET LA SEPARATION
================================================================================================
Deux regimes, et c'est la POSITION DES ENNEMIS qui les separe -- jamais la geometrie de spawn :

  * **A** -- etat initial. Les ennemis sont groupes ; la meilleure tuile est celle dont la
    zone-triangle en touche le plus.
  * **B** -- un ennemi est DEPLACE loin du groupe. Le terme d'adjacence change de place, donc
    l'utilite maximale et/ou la tuile retenue changent.

Le verdict EXIGE (a) `bucketUtil` strictement superieure au plancher `1 + |zone|` quelque part
(sinon le terme d'ennemis n'est jamais exerce et l'accord est DEGENERE), et (b) que les deux
regimes ne rendent pas exactement la meme mesure (sinon le montage ne separe rien).

⚠ `ncEvaluate` est STRUCTURELLEMENT AVEUGLE AUX MACHINES OF WAR (son hook filtre
`ty === EntityType.Unit`) et `ultraDreadnought` en est une : c'est `ncPlaybookPredict` qui accepte
`EntityType.Machine`. Un `ok: false` LEVE ici -- un echec RENDU se lirait comme un << 0 action >>.

CE QUE CE PROBE NE PROUVE PAS : le wrapper `Evaluate/3` donne l'utilite et la cible du `Bucket`,
pas la decision finale de l'IA (qui passe encore par les tiers de priorite -- 1159 est au tier
`-100 = Late`, donc derriere `1158 DutyEternal` du meme porteur). Un accord ici est necessaire,
pas suffisant.

    python probe_1066_macro_plasma_decision_live.py --state-file <abs> [--board MC1_67] [--seed 777]

Discipline runner : `--state-file` ABSOLU et propre, runner DISPOSE en fin de run. ASCII only.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

PYDIR = Path(__file__).resolve().parent
sys.path.insert(0, str(PYDIR))

from engine.entities.active_ability_type import ActiveAbilityType   # noqa: E402

MACRO = int(ActiveAbilityType.MacroPlasmaIncinerator)      # 0x487 = 1159
MOW = "ultraDreadnought"
P_UNITS = "ultraEudorian,adeptCanoness"
A_UNITS = "necroWarden,necroDestroyer,orksNob"
#: Placements : les TROIS ennemis GROUPES, pour qu'une zone-triangle puisse en toucher plusieurs.
#: Les allies sont mis a l'ecart -- ils n'entrent dans AUCUN terme de la formule.
_PLACE = ["ultraEudorian:0,0", "adeptCanoness:0,1"]
_A_PLACE = ["necroWarden:3,4", "necroDestroyer:3,5", "orksNob:4,4"]


def _rpc_mod():
    from rl_collect_batch import _resolve_session, _rpc
    return _resolve_session, _rpc


def _r(rpc, sid, m, b, t=120):
    return (rpc(sid, m, [b], timeout=t).get("result") or {})


def build(state_file: Path, seed: int, board: str, verbose: bool) -> int:
    state_file.parent.mkdir(parents=True, exist_ok=True)
    state_file.unlink(missing_ok=True)
    cmd = [sys.executable, "rl_duel.py", "build", "--seed", str(seed), "--board", board,
           "--state-file", str(state_file), "--no-ai",
           "--p-units", P_UNITS, "--p-mow", MOW, "--a-units", A_UNITS]
    for p in _PLACE:
        cmd += ["--place", p]
    for p in _A_PLACE:
        cmd += ["--a-place", p]
    proc = subprocess.run(cmd, cwd=str(PYDIR), capture_output=True, text=True,
                          encoding="utf-8", errors="replace")
    if not state_file.exists():
        raise RuntimeError("build KO : %s" % ((proc.stderr or proc.stdout or "")[-2000:]))
    rid = int(json.loads(state_file.read_text())["runnerId"])
    if verbose:
        print("[1066/live] runner %d, board %s, seed %d" % (rid, board, seed))
    return rid


def _mow_caster_id(rpc, sid, rid: int):
    """⚠ TROIS ids sur une MoW (`id` / `machineId` / `casterId`) et les RPC d'oracle n'acceptent
    que `casterId` (mesure #977)."""
    dv = _r(rpc, sid, "decisionView", {"runnerId": rid, "allAbilities": True}, 180)
    for m in (dv.get("mows") or []):
        if m.get("visualId") == MOW:
            return m.get("casterId"), dv
    return None, dv


def _oracle_natif(rpc, sid, rid: int, caster_id: int) -> dict:
    """`ncPlaybookPredict(via="evaluate")` -> l'action que `Bucket$$ChooseAction` retiendrait.

    ⚠ UN ECHEC RENDU N'EST PAS UNE MESURE : `ok: false` LEVE."""
    r = _r(rpc, sid, "ncPlaybookPredict",
           {"runnerId": rid, "unitId": caster_id, "abilityType": MACRO, "via": "evaluate"}, 300)
    if not r.get("ok"):
        raise RuntimeError("ncPlaybookPredict a ECHOUE (capteur muet, PAS un refus) : %s"
                           % json.dumps(r, default=str)[:400])
    if r.get("playbookClass") != "MacroPlasmaIncineratorPlaybook":
        raise RuntimeError("le natif a charge %s, pas MacroPlasmaIncineratorPlaybook"
                           % r.get("playbookClass"))
    act = r.get("bucketAction") or {}
    return {"util": r.get("bucketUtil"), "actions": r.get("bucketActionCount"),
            "targetLow": act.get("targetLow"), "ability": act.get("ability"),
            "vide": r.get("bucket") == "empty", "via": r.get("bucketVia")}


def _nc_context(rpc, sid, rid: int, caster_id: int):
    """Le `NCContext` de la face DECISION, monte par la MEME voie que le moteur (#970-r3)."""
    from engine.ai import context as _ai_ctx
    from engine.playbook import noncomparable as PB
    from engine.playbook import scene as _scene
    from engine import weights
    dv = _r(rpc, sid, "decisionView", {"runnerId": rid, "allAbilities": True, "maxRank": 32}, 180)
    mov = _r(rpc, sid, "aiMovableTiles", {"runnerId": rid}, 60)
    mov_by_unit = {u.get("unitId"): u for u in (mov.get("units") or [])}
    predictor = _scene.build_predictor(lambda m, b, t: _r(rpc, sid, m, b, t), rid)
    c = _ai_ctx.build(lambda m, b, t: _r(rpc, sid, m, b, t), rid, dv, mov_by_unit, caster_id,
                      weights.load(), predictor)
    return PB.NCContext(
        uid=c.uid, origin=c.origin, reach_nc=c.reach_nc, epos=c.epos, fpos=c.fpos,
        enemies=c.enemies, neigh_by_pos=c.neigh_by_pos, walkable_by_pos=c.walkable_by_pos,
        plan=c.plans.get(c.uid) or {}, plans=c.plans, hp_cur_by_id=c.hp_cur_by_id,
        elev_by_pos=c.elev_by_pos, ability_targets=c.ability_targets, wt=c.wt,
        is_temporary_by_pos=c.is_temporary_by_pos, effects_by_pos=c.effects_by_pos,
        is_wall_by_pos=c.is_wall_by_pos, obs_units=c.obs_units, tile_id_by_pos=c.tile_id_by_pos,
        active_levels=c.active_ability_levels, ability_config=c.heal_config,
        current_player=c.current_player, machine_of_war_position=c.machine_of_war_position,
        units=c.units, cast_from_tiles=c.cast_from_tiles, scene=c.scene)


def _port(rpc, sid, rid: int, caster_id: int) -> dict:
    from engine.playbook import noncomparable as PB
    from engine.playbook.noncomparable import _base as NCB
    nc = _nc_context(rpc, sid, rid, caster_id)
    cands = PB.PLAYBOOKS[MACRO].generate_candidates(nc)
    from_here, union = NCB.eligible_target_tiles(nc, MACRO)
    # `|zone|` de la tuile RETENUE : c'est le PLANCHER `1 + |zone|` du regime sans ennemi, qu'il
    # faut connaitre pour dire si le terme d'adjacence a REELLEMENT ete exerce.
    zone = None
    if cands:
        import engine.playbook.tile_targets as TT
        pb = PB.PLAYBOOKS[MACRO]
        dctx = TT.dsl_context_for_tile_target(nc)
        tid = cands[0]["target"]
        if dctx is not None and tid is not None:
            zone = len(pb._area(dctx, int(tid)))
    return {"candidats": cands, "n_eligibles": len(from_here or union), "zone": zone,
            "util": (cands[0]["pred"] if cands else None),
            "target": (cands[0]["target"] if cands else None)}


def _mesurer(rpc, sid, rid, caster_id, libelle, verbose) -> dict:
    nat = _oracle_natif(rpc, sid, rid, caster_id)
    prt = _port(rpc, sid, rid, caster_id)
    row = {"libelle": libelle, "natif_util": nat["util"], "natif_target": nat["targetLow"],
           "natif_actions": nat["actions"], "natif_vide": nat["vide"], "natif_via": nat["via"],
           "port_util": prt["util"], "port_target": prt["target"], "port_zone": prt["zone"],
           "n_eligibles": prt["n_eligibles"]}
    if verbose:
        print("  [%s] NATIF util=%s target=%s actions=%s | PORT util=%s target=%s |zone|=%s | "
              "cibles eligibles=%d"
              % (libelle, row["natif_util"], row["natif_target"], row["natif_actions"],
                 row["port_util"], row["port_target"], row["port_zone"], row["n_eligibles"]))
    return row


def _eloigner_un_ennemi(rpc, sid, rid: int, out: dict, verbose: bool) -> bool:
    """DEPLACE `necroDestroyer` LOIN du groupe -- on force la configuration, on ne la subit pas.

    La tuile d'arrivee est CHOISIE dans les atteignables les plus eloignees du groupe, jamais
    ecrite en dur, et l'ARRIVEE est VERIFIEE (`applyAction` rend un dict truthy meme quand rien
    n'a bouge)."""
    o = _r(rpc, sid, "observeBattle", {"runnerId": rid})
    vivants = [u for u in (o.get("units") or []) if not u.get("isDead")]
    cible = next((u for u in vivants if u.get("visualId") == "necroDestroyer"), None)
    if cible is None:
        out["erreurs"].append("necroDestroyer introuvable : REGIME B NON CONFRONTE")
        return False
    uid = cible.get("squadId") if cible.get("squadId") is not None else cible.get("id")
    ancre = (3, 4)
    mov = _r(rpc, sid, "aiMovableTiles", {"runnerId": rid}, 60)
    atteignables = []
    for u in (mov.get("units") or []):
        if u.get("unitId") != uid:
            continue
        for t in (u.get("tiles") or []):
            p = t if isinstance(t, (list, tuple)) else (t.get("col"), t.get("row"))
            if p and p[0] is not None:
                atteignables.append((p[0], p[1]))
    occupees = {(u.get("col"), u.get("row")) for u in vivants}
    libres = [p for p in atteignables if p not in occupees]
    if not libres:
        out["erreurs"].append("aucune tuile atteignable ET libre (atteignables=%d) -- REGIME B "
                              "NON CONFRONTE" % len(atteignables))
        return False
    import hexgeo
    dest = max(libres, key=lambda p: hexgeo.distance(p[0], p[1], ancre[0], ancre[1]))
    _r(rpc, sid, "applyAction",
       {"runnerId": rid, "action": {"kind": "move", "unitId": uid,
                                    "to": {"col": dest[0], "row": dest[1]}}}, 180)
    o2 = _r(rpc, sid, "observeBattle", {"runnerId": rid})
    arrivee = next(((u.get("col"), u.get("row")) for u in (o2.get("units") or [])
                    if (u.get("squadId") if u.get("squadId") is not None else u.get("id")) == uid
                    and not u.get("isDead")), None)
    out["move"] = {"unitId": uid, "vise": dest, "arrivee": arrivee, "a_mordu": arrivee == dest}
    if verbose:
        print("[1066/live] move necroDestroyer -> %s : arrivee=%s (a mordu: %s)"
              % (dest, arrivee, arrivee == dest))
    if arrivee != dest:
        out["erreurs"].append("le move n'a PAS mordu (arrivee=%s) -- REGIME B NON CONFRONTE"
                              % (arrivee,))
        return False
    return True


def run(state_file: str, seed: int = 777, board: str = "MC1_67", verbose: bool = True) -> dict:
    sf = Path(state_file).resolve()
    resolve, rpc = _rpc_mod()
    sid = resolve()
    rid = build(sf, seed, board, verbose)
    out = {"runnerId": rid, "board": board, "seed": seed, "regimes": [], "erreurs": []}
    try:
        caster_id, _dv = _mow_caster_id(rpc, sid, rid)
        if caster_id is None:
            out["erreurs"].append("MoW %s absente de decisionView.mows" % MOW)
            return out
        out["casterId"] = caster_id
        if verbose:
            print("[1066/live] MoW %s casterId=%s" % (MOW, caster_id))
        out["regimes"].append(_mesurer(rpc, sid, rid, caster_id, "A: ennemis groupes", verbose))
        if not _eloigner_un_ennemi(rpc, sid, rid, out, verbose):
            return out
        out["regimes"].append(_mesurer(rpc, sid, rid, caster_id, "B: un ennemi eloigne", verbose))
    finally:
        try:
            _r(rpc, sid, "disposeRunner", {"runnerId": rid}, 60)
            if verbose:
                print("[1066/live] runner %d dispose" % rid)
        except Exception as exc:                      # pragma: no cover
            out["erreurs"].append("dispose KO: %s" % exc)
    return out


def verdict(r: dict) -> list:
    """Les fautes, une chaine par faute. Vide == confrontation OK."""
    f = list(r.get("erreurs") or [])
    regs = {x["libelle"][0]: x for x in (r.get("regimes") or [])}
    A, B = regs.get("A"), regs.get("B")
    if not A or not B:
        return f + ["regimes incomplets -- NON CONFRONTE"]
    for tag, row in (("A", A), ("B", B)):
        if row["natif_vide"] or row["natif_util"] is None:
            f.append("TEMOIN NUL en regime %s : le natif n'emet AUCUNE action -- un accord y "
                     "serait degenere" % tag)
            continue
        if row["port_util"] is None:
            f.append("le PORT n'emet rien en regime %s alors que le natif emet (util=%s)"
                     % (tag, row["natif_util"]))
            continue
        if abs(float(row["port_util"]) - float(row["natif_util"])) > 1e-6:
            f.append("UTILITE en regime %s : port=%s natif=%s" % (tag, row["port_util"],
                                                                  row["natif_util"]))
        if row["natif_target"] is not None and row["port_target"] is not None \
                and int(row["natif_target"]) != int(row["port_target"]):
            f.append("CIBLE en regime %s : port=%s natif=%s (utilites port=%s natif=%s)"
                     % (tag, row["port_target"], row["natif_target"], row["port_util"],
                        row["natif_util"]))
        if row["n_eligibles"] < 2:
            f.append("MONTAGE CREUX en regime %s : %d cible(s) eligible(s) -- l'argmax ne "
                     "distingue rien" % (tag, row["n_eligibles"]))
    # TEMOIN NON NUL sur le TERME QUI NOUS INTERESSE : sans une utilite au-dessus du plancher
    # `1 + |zone|`, le terme d'ennemis adjacents n'est jamais exerce et l'accord ne dit rien de lui.
    exerce = [x for x in (A, B)
              if x["natif_util"] is not None and x["port_zone"] is not None
              and float(x["natif_util"]) > 1.0 + float(x["port_zone"]) + 1e-9]
    if not exerce:
        f.append("TEMOIN DEGENERE : nulle part l'utilite ne depasse le plancher `1 + |zone|` -- "
                 "le terme `GetAdjacentEnemies` n'est jamais exerce")
    if (A["natif_util"], A["natif_target"]) == (B["natif_util"], B["natif_target"]):
        f.append("LE MONTAGE NE SEPARE PAS : les deux regimes rendent la MEME mesure native "
                 "(util=%s target=%s)" % (A["natif_util"], A["natif_target"]))
    return f


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--state-file", required=True)
    ap.add_argument("--seed", type=int, default=777)
    ap.add_argument("--board", default="MC1_67")
    a = ap.parse_args()
    r = run(a.state_file, a.seed, a.board, verbose=True)
    print()
    f = verdict(r)
    for x in f:
        print("[1066/live] FAUTE : %s" % x)
    print("[1066/live] VERDICT : %s" % ("OK" if not f else "FAUTES (%d)" % len(f)))
    return 0 if not f else 1


if __name__ == "__main__":
    raise SystemExit(main())
