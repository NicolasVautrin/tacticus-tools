"""#1066 (residus #906-r1 / #985-r1) -- CONFRONTATION LIVE de la face DECISION `1211 RitesOfMorkai`.

CE QUE CE PROBE CONFRONTE
================================================================================================
`util = 1 + 100 * |{f in GetSurroundingFriends(caster, casterPosition, range, includeCenter:false)
: f != caster}|`, sous le gate de cible `GetAdjacentEnemies(casterPosition, caster, false).Count
> 0` et le gate AMONT `ShouldEvaluate` = `adj.Any(IsFriend) && adj.Any(IsEnemy)`.

Aucun tirage : les deux cotes rendent un NOMBRE, donc on confronte le NOMBRE.

    NATIF  `ncPlaybookPredict(via="evaluate")` -> `bucketUtil` (ou `bucket == "empty"`)
    PORT   `PLAYBOOKS[1211].generate_candidates(NCContext)` -> `pred`

LE TEMOIN NON NUL, ET CE QUI SEPARE
================================================================================================
Le terme utile est un COMPTE d'amis : le faire varier fait varier l'utilite de 100 en 100, donc
les regimes sont separes par construction et non par chance.

  * **A** -- gate AMONT tombe (aucun ENNEMI adjacent au caster, alors qu'un ami l'est). Le natif
    ne doit produire AUCUNE action.
  * **B** -- 1 ennemi adjacent, 1 ami dans le rayon -> `1 + 100 * 1 = 101`.
  * **C** -- 1 ennemi adjacent, 2 amis dans le rayon -> `1 + 100 * 2 = 201`.

⚠ LE RAYON N'EST PAS UN LITTERAL DU PORT : il est lu au gameconfig
(`AbilityConfiguration$$GetNumberConstant(0x16 = range)`, = 1 pour cette ability). C'est ce qui
retire le `BLOCAGE: seeding` de la fiche `#985-r1`, laquelle le croyait non publie. On ne peut pas
le faire VARIER live (il n'y a qu'une valeur au gameconfig), mais on peut MUTER le port pour
verifier qu'il le consomme reellement -- c'est l'objet de `--mutant rayon`.

LE PORTEUR EST HORS POOL, ET CE N'EST PAS UN REFUS
================================================================================================
`spaceWolfPriest` n'est pas dans `rl_duel build --list-pool` : il entre par INJECTION CATALOGUE
(`catalog_inject.write_augmented_seed_bc` + `build --seed-bc`), la voie deja mesuree par
`probe_906_rites_of_morkai_live.py` pour la face COMBAT. << Hors pool >> n'est jamais
<< non confrontable >>.

    python probe_1066_rites_of_morkai_decision_live.py [--board MC1_67] [--seed 777]
                                                       [--mutant rayon|gate|centre]

Discipline runner : state-file ABSOLU sous `logs/`, runner DISPOSE en fin de run. ASCII only.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import catalog_inject as CI                                         # noqa: E402
from rl_collect_batch import _rpc, _resolve_session                 # noqa: E402
from engine.entities.active_ability_type import ActiveAbilityType   # noqa: E402

RITES = int(ActiveAbilityType.RitesOfMorkai)          # 0x4bb = 1211
CASTER_VIS = "spaceWolfPriest"
P_UNITS = "spaceWolfPriest,astraCreed,adeptCanoness"
A_UNITS = "orksNob,orksWarboss"
LOGS = HERE.parents[1] / "logs" / "ad948076"

#: Le caster est ancre en (3,4). (3,5) et (4,4) lui sont adjacentes sur `MC1_67` -- VERIFIE a la
#: mesure par `_voisinage`, jamais presume : un montage dont l'adjacence n'est pas constatee est
#: un montage CREUX, et le verdict le dit.
CASTER_POS = (3, 4)
MONTAGES = (
    # (libelle, place allies, place ennemis, utilite NATIVE attendue -- None = aucune action)
    ("A: gate AMONT tombe (aucun ennemi adjacent)",
     ["spaceWolfPriest:3,4", "astraCreed:3,5", "adeptCanoness:0,0"],
     ["orksNob:6,6", "orksWarboss:6,5"], None),
    ("B: 1 ennemi adjacent, 1 ami au rayon",
     ["spaceWolfPriest:3,4", "astraCreed:3,3", "adeptCanoness:0,0"],
     ["orksNob:3,5", "orksWarboss:6,5"], 101.0),
    ("C: 1 ennemi adjacent, 2 amis au rayon",
     ["spaceWolfPriest:3,4", "astraCreed:3,3", "adeptCanoness:4,4"],
     ["orksNob:3,5", "orksWarboss:6,5"], 201.0),
)


def _r(sid, m, b, t=180):
    return (_rpc(sid, m, [b], timeout=t).get("result") or {})


def build(state_file: Path, seed_bc: Path, seed: int, board: str,
          place: list, a_place: list, verbose: bool) -> int:
    state_file.parent.mkdir(parents=True, exist_ok=True)
    state_file.unlink(missing_ok=True)
    cmd = [sys.executable, "rl_duel.py", "build", "--seed", str(seed), "--board", board,
           "--seed-bc", str(seed_bc), "--state-file", str(state_file), "--no-ai",
           "--p-units", P_UNITS, "--a-units", A_UNITS]
    for p in place:
        cmd += ["--place", p]
    for p in a_place:
        cmd += ["--a-place", p]
    proc = subprocess.run(cmd, cwd=str(HERE), capture_output=True, text=True,
                          encoding="utf-8", errors="replace")
    if not state_file.exists():
        raise RuntimeError("build KO : %s" % ((proc.stderr or proc.stdout or "")[-2000:]))
    rid = int(json.loads(state_file.read_text())["runnerId"])
    if verbose:
        print("[1066/1211] runner %d" % rid)
    return rid


def _caster_id(sid, rid: int):
    dv = _r(sid, "decisionView", {"runnerId": rid, "allAbilities": True})
    for u in (dv.get("units") or []):
        if u.get("visualId") == CASTER_VIS:
            return u.get("id")
    return None


def _oracle_natif(sid, rid: int, caster_id: int) -> dict:
    """⚠ UN ECHEC RENDU N'EST PAS UNE MESURE : `ok: false` LEVE, sinon un capteur muet se lirait
    comme un refus du gate (la faute exacte que `probe_970r3` documente)."""
    r = _r(sid, "ncPlaybookPredict",
           {"runnerId": rid, "unitId": caster_id, "abilityType": RITES, "via": "evaluate"}, 300)
    if not r.get("ok"):
        raise RuntimeError("ncPlaybookPredict a ECHOUE (capteur muet, PAS un refus) : %s"
                           % json.dumps(r, default=str)[:400])
    if r.get("playbookClass") != "RitesOfMorkaiPlaybook":
        raise RuntimeError("le natif a charge %s, pas RitesOfMorkaiPlaybook" % r.get("playbookClass"))
    return {"util": (None if r.get("bucket") == "empty" else r.get("bucketUtil")),
            "actions": r.get("bucketActionCount"), "vide": r.get("bucket") == "empty"}


def _nc_context(sid, rid: int, caster_id: int):
    from engine.ai import context as _ai_ctx
    from engine.playbook import noncomparable as PB
    from engine.playbook import scene as _scene
    from engine import weights
    dv = _r(sid, "decisionView", {"runnerId": rid, "allAbilities": True, "maxRank": 32})
    mov = _r(sid, "aiMovableTiles", {"runnerId": rid}, 60)
    mov_by_unit = {u.get("unitId"): u for u in (mov.get("units") or [])}
    predictor = _scene.build_predictor(lambda m, b, t: _r(sid, m, b, t), rid)
    c = _ai_ctx.build(lambda m, b, t: _r(sid, m, b, t), rid, dv, mov_by_unit, caster_id,
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
        current_player=getattr(c, "cur", None),
        machine_of_war_position=c.machine_of_war_position,
        triggered_kits=getattr(c, "live_triggered_kits", None),
        units=c.units, cast_from_tiles=c.cast_from_tiles, scene=c.scene)


def _voisinage(nc) -> dict:
    """L'ETAT MESURE du montage : combien d'amis / d'ennemis sont REELLEMENT adjacents au caster,
    et combien d'amis sont dans le disque du rayon LU. Sans cela, un `--place` reloge par le natif
    ferait mesurer un regime qu'on croit monte et qui ne l'est pas."""
    from engine import battle_query as bq
    from engine.playbook import noncomparable as PB
    pb = PB.PLAYBOOKS[RITES]
    if nc.origin is None:
        return {"origin": None, "amis_adj": 0, "ennemis_adj": 0, "amis_rayon": 0, "rayon": None}
    neigh = bq.neigh_map(nc)
    rng = pb._range()
    return {"origin": nc.origin, "rayon": rng,
            "amis_adj": bq.count_adjacent(nc.origin, nc.fpos, nc.elev_by_pos, neigh),
            "ennemis_adj": bq.count_adjacent(nc.origin, nc.epos, nc.elev_by_pos, neigh),
            "amis_rayon": (bq.count_surrounding(nc.origin, nc.fpos, rng, include_center_tile=False)
                           if rng is not None else 0)}


def _mesurer(sid, rid, caster_id, libelle, attendu, verbose) -> dict:
    from engine.playbook import noncomparable as PB
    nat = _oracle_natif(sid, rid, caster_id)
    nc = _nc_context(sid, rid, caster_id)
    v = _voisinage(nc)
    cands = PB.PLAYBOOKS[RITES].generate_candidates(nc)
    row = {"libelle": libelle, "attendu": attendu, "natif_util": nat["util"],
           "natif_vide": nat["vide"], "natif_actions": nat["actions"],
           "port_util": (cands[0]["pred"] if cands else None),
           "port_target": (cands[0]["target"] if cands else None),
           "gate_amont": PB.PLAYBOOKS[RITES].should_evaluate(nc), **v}
    if verbose:
        print("  [%s]\n     etat : origin=%s rayon=%s amis_adj=%d ennemis_adj=%d amis_rayon=%d"
              % (libelle, v["origin"], v["rayon"], v["amis_adj"], v["ennemis_adj"],
                 v["amis_rayon"]))
        print("     NATIF util=%s (vide=%s actions=%s) | PORT util=%s cible=%s gate_amont=%s"
              % (row["natif_util"], row["natif_vide"], row["natif_actions"], row["port_util"],
                 row["port_target"], row["gate_amont"]))
    return row


def appliquer_mutant(nom: str) -> str:
    """CONTRE-EPREUVE : casse UN terme du port. Chaque mutant DOIT faire rougir le verdict ; un
    mutant qui laisse vert designe un terme que cette confrontation n'exerce pas."""
    from engine.playbook import noncomparable as PB
    from engine import battle_query as bq
    cls = type(PB.PLAYBOOKS[RITES])
    if nom == "rayon":                 # le rayon LU remplace par un litteral 2
        cls._range = lambda self: 2
        return "_range() force a 2 (au lieu du GetNumberConstant(0x16) = 1)"
    if nom == "gate":                  # gate AMONT desarme
        cls.should_evaluate = lambda self, ctx: True
        return "should_evaluate() force a True"
    if nom == "centre":                # `includeCenter` inverse
        orig = cls.evaluate_non_comparable

        def m(self, tile, target, ctx):
            if tile is None or bq.count_adjacent(tile, ctx.epos, ctx.elev_by_pos,
                                                 bq.neigh_map(ctx)) <= 0:
                return None
            rng = self._range()
            if rng is None:
                return None
            return self.BASE_UTILITY + self.FRIEND_UTILITY * float(
                bq.count_surrounding(tile, ctx.fpos, rng, include_center_tile=True))
        cls.evaluate_non_comparable = m
        return "include_center_tile force a True"
    raise SystemExit("mutant inconnu: %s" % nom)


def run(seed: int, board: str, verbose: bool = True) -> dict:
    LOGS.mkdir(parents=True, exist_ok=True)
    seed_bc = LOGS / "seed_bc_1066_swp.json"
    p, units, abils = CI.write_augmented_seed_bc(seed_bc, [CASTER_VIS])
    if verbose:
        print("[1066/1211] seed BC augmente (HORS data/) -> %s | units=%s abils=%s"
              % (p, units, abils))
    sid = _resolve_session()
    out = {"board": board, "seed": seed, "regimes": [], "erreurs": []}
    for libelle, place, a_place, attendu in MONTAGES:
        sf = LOGS / ("st_1066_rites_%s.json" % libelle[0])
        rid = build(sf, seed_bc, seed, board, place, a_place, verbose)
        try:
            cid = _caster_id(sid, rid)
            if cid is None:
                out["erreurs"].append("%s absent de decisionView (%s)" % (CASTER_VIS, libelle))
                continue
            out["casterId"] = cid
            out["regimes"].append(_mesurer(sid, rid, cid, libelle, attendu, verbose))
        finally:
            try:
                _r(sid, "disposeRunner", {"runnerId": rid}, 60)
                if verbose:
                    print("     runner %d dispose" % rid)
            except Exception as exc:                  # pragma: no cover
                out["erreurs"].append("dispose KO: %s" % exc)
    return out


def verdict(r: dict) -> list:
    f = list(r.get("erreurs") or [])
    regs = {x["libelle"][0]: x for x in (r.get("regimes") or [])}
    A, B, C = regs.get("A"), regs.get("B"), regs.get("C")
    if not A or not B or not C:
        return f + ["regimes incomplets -- NON CONFRONTE"]
    # MONTAGE CONSTATE, jamais declare.
    if A["ennemis_adj"] != 0 or A["amis_adj"] < 1:
        f.append("MONTAGE CREUX en A : amis_adj=%d ennemis_adj=%d (attendu >=1 et 0)"
                 % (A["amis_adj"], A["ennemis_adj"]))
    for tag, row, n in (("B", B, 1), ("C", C, 2)):
        if row["ennemis_adj"] < 1:
            f.append("MONTAGE CREUX en %s : aucun ennemi adjacent" % tag)
        if row["amis_rayon"] != n:
            f.append("MONTAGE CREUX en %s : amis_rayon=%d (attendu %d)"
                     % (tag, row["amis_rayon"], n))
    for tag, row in (("A", A), ("B", B), ("C", C)):
        att = row["attendu"]
        if att is None:
            if not row["natif_vide"]:
                f.append("LE NATIF EMET en regime %s (util=%s) : la RE du gate est FAUSSE"
                         % (tag, row["natif_util"]))
            if row["port_util"] is not None:
                f.append("LE PORT EMET en regime %s (util=%s) la ou le natif refuse"
                         % (tag, row["port_util"]))
            continue
        if row["natif_vide"] or row["natif_util"] is None:
            f.append("TEMOIN NUL en regime %s : le natif n'emet rien alors qu'on attend %s"
                     % (tag, att))
            continue
        if abs(float(row["natif_util"]) - att) > 1e-6:
            f.append("UTILITE NATIVE en regime %s : %s, attendu %s (la RE de la formule est "
                     "FAUSSE, pas le port)" % (tag, row["natif_util"], att))
        if row["port_util"] is None:
            f.append("le PORT n'emet rien en regime %s alors que le natif rend %s"
                     % (tag, row["natif_util"]))
            continue
        if abs(float(row["port_util"]) - float(row["natif_util"])) > 1e-6:
            f.append("PORT != NATIF en regime %s : port=%s natif=%s"
                     % (tag, row["port_util"], row["natif_util"]))
    # SEPARATION : sans deux valeurs distinctes, l'accord serait DEGENERE.
    if B["natif_util"] is not None and B["natif_util"] == C["natif_util"]:
        f.append("LE MONTAGE NE SEPARE PAS : B et C rendent la MEME utilite native (%s)"
                 % B["natif_util"])
    return f


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--seed", type=int, default=777)
    ap.add_argument("--board", default="MC1_67")
    ap.add_argument("--mutant", choices=("rayon", "gate", "centre"),
                    help="CONTRE-EPREUVE : casse un terme du port ; le verdict DOIT rougir")
    a = ap.parse_args()
    if a.mutant:
        print("[MUTANT] %s -> %s" % (a.mutant, appliquer_mutant(a.mutant)))
    r = run(a.seed, a.board, verbose=True)
    print()
    f = verdict(r)
    for x in f:
        print("[1066/1211] FAUTE : %s" % x)
    print("[1066/1211] VERDICT : %s" % ("OK" if not f else "FAUTES (%d)" % len(f)))
    if a.mutant:
        print("[1066/1211] MUTANT `%s` : %s" % (a.mutant, "MORD" if f else "NE MORD PAS (!!)"))
        return 0 if f else 1
    return 0 if not f else 1


if __name__ == "__main__":
    raise SystemExit(main())
