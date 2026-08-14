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
P_UNITS = "adeptCanoness,adeptHospitaller"
A_UNITS = "necroWarden,necroDestroyer,orksNob"
#: Les allies sont mis a l'ecart -- ils n'entrent dans AUCUN terme de la formule.
_PLACE = ["adeptCanoness:0,0", "adeptHospitaller:0,1"]

#: DEUX MONTAGES, et c'est la POSITION DES ENNEMIS qui les separe -- on DEPLACE les unites, on ne
#: subit pas la geometrie de spawn. Le regime B ne peut PAS se monter par `applyAction` : mesure
#: (1re passe de ce probe) -- `aiMovableTiles` rend **0 tuile** pour une unite de l'equipe adverse
#: quand ce n'est pas son tour, donc le move ne mordait pas et le regime B n'existait pas. Deux
#: BUILDS separes contournent cela sans rien presumer de l'ordre des tours.
#:
#: Le regime **C** n'est pas un troisieme point de mesure de confort : c'est celui qui rend la
#: CIBLE confrontable. `bucketAction.targetLow` etant un demi-pointeur (cf. `_port`), l'accord des
#: cibles ne se deduit de l'accord des utilites que si l'argmax est UNIQUE -- et sur A comme sur B
#: il ne l'est pas (6 et 11 tuiles ex-aequo, MESURE). Le placement de C a ete CHERCHE pour cela,
#: en faisant varier les ennemis sur le contexte d'un runner reel.
#: ⚠ Et la recherche doit patcher `epos` **ET** `obs_units` : une premiere passe ne bougeait que
#: `epos`, donc le gate `IsFreeTile` voyait encore l'occupation de l'ANCIEN montage -- le placement
#: qu'elle proposait rendait 2 ex-aequo une fois construit pour de vrai. En patchant les deux,
#: `((0,6), (2,6), (4,2))` rend un maximum de `8` sur la SEULE tuile `(1,6)`.
MONTAGES = (
    ("A: ennemis groupes", ["necroWarden:3,4", "necroDestroyer:3,5", "orksNob:4,4"]),
    ("B: ennemis disperses", ["necroWarden:3,4", "necroDestroyer:0,5", "orksNob:6,1"]),
    ("C: argmax UNIQUE", ["necroWarden:0,6", "necroDestroyer:2,6", "orksNob:4,2"]),
)


def _rpc_mod():
    from rl_collect_batch import _resolve_session, _rpc
    return _resolve_session, _rpc


def _r(rpc, sid, m, b, t=120):
    return (rpc(sid, m, [b], timeout=t).get("result") or {})


def build(state_file: Path, seed: int, board: str, a_place: list, verbose: bool) -> int:
    state_file.parent.mkdir(parents=True, exist_ok=True)
    state_file.unlink(missing_ok=True)
    cmd = [sys.executable, "rl_duel.py", "build", "--seed", str(seed), "--board", board,
           "--state-file", str(state_file), "--no-ai",
           "--p-units", P_UNITS, "--p-mow", MOW, "--a-units", A_UNITS]
    for p in _PLACE:
        cmd += ["--place", p]
    for p in a_place:
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
        is_wall_by_pos=getattr(c, "is_wall_by_pos", None) or {},
        is_in_fog_by_pos=getattr(c, "is_in_fog_by_pos", None) or {},
        obs_units=c.obs_units, tile_id_by_pos=c.tile_id_by_pos,
        active_levels=c.active_ability_levels, ability_config=c.heal_config,
        # `AiDecisionContext.cur` = `TurnComponent._currentPlayerId` -- le nom du champ ici est
        # `current_player` ; c'est le MEME appariement que `NonComparableGenerator.generate`, dont
        # ce montage est la copie (toute divergence ferait mesurer un contexte qui n'existe pas).
        current_player=getattr(c, "cur", None),
        machine_of_war_position=c.machine_of_war_position,
        triggered_kits=getattr(c, "live_triggered_kits", None),
        units=c.units, cast_from_tiles=c.cast_from_tiles, scene=c.scene)


def _port(rpc, sid, rid: int, caster_id: int) -> dict:
    """Le port, ET le PROFIL COMPLET de ses utilites -- pas seulement son argmax.

    ⚠ POURQUOI LE PROFIL. `bucketAction.targetLow` du natif est `UnitAction+0x18` lu en U32,
    c.-a-d. la MOITIE BASSE D'UN POINTEUR `IEntity` (mesure : `2211594688` la ou les entites-tuiles
    de ce board ont des ids `12..74`). Ce n'est PAS un id d'entite : le comparer a `tile_id_by_pos`
    fabriquerait une fausse divergence, et le hook ne resout pas ce pointeur. La CIBLE n'est donc
    pas directement confrontable par ce canal.

    Le cran qui la remplace, et qui est MESURE plutot que suppose : `n_ex_aequo`, le nombre de
    tuiles qui atteignent le maximum cote port. Quand il vaut **1**, l'argmax est UNIQUE, donc
    l'egalite des UTILITES implique l'egalite des CIBLES -- une autre tuile aurait rendu une autre
    valeur. Le verdict l'exige."""
    import engine.playbook.tile_targets as TT
    from engine.playbook import noncomparable as PB
    from engine.playbook.noncomparable import _base as NCB
    nc = _nc_context(rpc, sid, rid, caster_id)
    pb = PB.PLAYBOOKS[MACRO]
    cands = pb.generate_candidates(nc)
    from_here, union = NCB.eligible_target_tiles(nc, MACRO)
    tuiles = from_here or union
    profil = {}
    for t in tuiles:
        u = pb.evaluate_non_comparable(nc.origin, t, nc)
        if u is not None:
            profil[t] = u
    top = max(profil.values()) if profil else None
    # `|zone|` de la tuile RETENUE : le PLANCHER `1 + |zone|`, qu'il faut connaitre pour dire si le
    # terme d'adjacence a REELLEMENT ete exerce (sinon l'accord serait DEGENERE).
    zone = None
    if cands:
        dctx = TT.dsl_context_for_tile_target(nc, machine_caster=True)
        tid = cands[0]["target"]
        if dctx is not None and tid is not None:
            zone = len(pb._area(dctx, int(tid)))
    return {"candidats": cands, "n_eligibles": len(tuiles), "zone": zone,
            "n_ex_aequo": (sum(1 for v in profil.values() if abs(v - top) < 1e-9)
                           if top is not None else 0),
            "n_evalues": len(profil), "top": top,
            "util": (cands[0]["pred"] if cands else None),
            "target": (cands[0]["target"] if cands else None)}


def _mesurer(rpc, sid, rid, caster_id, libelle, verbose) -> dict:
    nat = _oracle_natif(rpc, sid, rid, caster_id)
    prt = _port(rpc, sid, rid, caster_id)
    row = {"libelle": libelle, "natif_util": nat["util"], "natif_target": nat["targetLow"],
           "natif_actions": nat["actions"], "natif_vide": nat["vide"], "natif_via": nat["via"],
           "port_util": prt["util"], "port_target": prt["target"], "port_zone": prt["zone"],
           "n_eligibles": prt["n_eligibles"], "n_ex_aequo": prt["n_ex_aequo"],
           "n_evalues": prt["n_evalues"]}
    if verbose:
        print("  [%s] NATIF util=%s actions=%s | PORT util=%s tuile=%s |zone|=%s ex-aequo=%d | "
              "eligibles=%d evaluees=%d"
              % (libelle, row["natif_util"], row["natif_actions"], row["port_util"],
                 row["port_target"], row["port_zone"], row["n_ex_aequo"], row["n_eligibles"],
                 row["n_evalues"]))
    return row


def _positions_ennemies(rpc, sid, rid: int) -> list:
    """L'etat MESURE, jamais presume : ou sont REELLEMENT les ennemis apres le build.

    Un `--a-place` peut etre reloge par le natif (tuile occupee/invalide) ; sans cette lecture, le
    montage serait DECLARE et non constate."""
    # Filtre par visualId, PAS par `teamId` : une premiere passe lisait `teamId == 1` et rendait
    # [(0,0), (0,1)] -- les positions des ALLIES. Le visualId est le seul discriminant qu'on ait
    # ECRIT nous-memes dans le montage.
    vis = {p.split(":")[0] for p in A_UNITS.split(",")}
    o = _r(rpc, sid, "observeBattle", {"runnerId": rid})
    return sorted((u.get("col"), u.get("row")) for u in (o.get("units") or [])
                  if not u.get("isDead") and u.get("visualId") in vis)


def run(state_file: str, seed: int = 777, board: str = "MC1_67", verbose: bool = True) -> dict:
    sf = Path(state_file).resolve()
    resolve, rpc = _rpc_mod()
    sid = resolve()
    out = {"board": board, "seed": seed, "regimes": [], "erreurs": [], "runners": []}
    for libelle, a_place in MONTAGES:
        rid = build(sf.with_name(sf.stem + "_" + libelle[0] + sf.suffix), seed, board,
                    a_place, verbose)
        out["runners"].append(rid)
        try:
            caster_id, _dv = _mow_caster_id(rpc, sid, rid)
            if caster_id is None:
                out["erreurs"].append("MoW %s absente de decisionView.mows (%s)" % (MOW, libelle))
                continue
            out["casterId"] = caster_id
            if verbose:
                print("[1066/live] [%s] runner %d, MoW casterId=%s ; ennemis %s"
                      % (libelle, rid, caster_id, _positions_ennemies(rpc, sid, rid)))
            out["regimes"].append(_mesurer(rpc, sid, rid, caster_id, libelle, verbose))
        finally:
            try:
                _r(rpc, sid, "disposeRunner", {"runnerId": rid}, 60)
                if verbose:
                    print("[1066/live] runner %d dispose" % rid)
            except Exception as exc:                  # pragma: no cover
                out["erreurs"].append("dispose KO: %s" % exc)
    return out


def verdict(r: dict) -> list:
    """Les fautes, une chaine par faute. Vide == confrontation OK."""
    f = list(r.get("erreurs") or [])
    regs = {x["libelle"][0]: x for x in (r.get("regimes") or [])}
    A, B, C = regs.get("A"), regs.get("B"), regs.get("C")
    if not A or not B or not C:
        return f + ["regimes incomplets -- NON CONFRONTE"]
    for tag, row in (("A", A), ("B", B), ("C", C)):
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
        if row["n_eligibles"] < 2 or row["n_evalues"] < 2:
            f.append("MONTAGE CREUX en regime %s : %d cible(s) eligible(s), %d evaluee(s) -- "
                     "l'argmax ne distingue rien" % (tag, row["n_eligibles"], row["n_evalues"]))
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
    if A["port_target"] is not None and A["port_target"] == B["port_target"] \
            and A["port_util"] == B["port_util"]:
        f.append("LE MONTAGE NE SEPARE PAS COTE PORT : meme tuile et meme utilite dans les deux "
                 "regimes (%s, %s)" % (A["port_target"], A["port_util"]))
    # LA CIBLE. `bucketAction.targetLow` etant un demi-pointeur, elle ne se confronte que par
    # DEDUCTION : sur un argmax UNIQUE, l'egalite des utilites vaut egalite des cibles. C'est la
    # raison d'etre du regime C -- si son argmax cesse d'etre unique, ce cran DOIT rougir plutot
    # que de laisser croire que la cible est couverte.
    if C["n_ex_aequo"] != 1:
        f.append("CIBLE NON CONFRONTEE : l'argmax du regime C n'est PAS unique (%d tuiles "
                 "ex-aequo) -- l'accord des utilites n'implique alors rien sur la cible"
                 % C["n_ex_aequo"])
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
