"""#419-r1-tr14-r5-r2-r1-r1-r1 -- le gate `ShouldExecute` qui refuse l'ability quand l'ATTAQUE
NORMALE tuerait deja la cible.

Trois corps natifs, DIX-SEPT classes de playbook Comparable (recensement niveau par niveau,
`resolveMethodPtr` -- cf. `engine/playbook/normal_attack_kill_gate.py`) :

    // IdunBattle.AI.Playbook.Loki.SpiritLeechPlaybook$$ShouldExecute            -- 14 classes
    return !BasePlaybook.WillNormalAttackKill(caster, target, casterTile);

    // IdunBattle.AI.Playbook.Loki.FragBombPlaybook$$ShouldExecute               --  2 classes
    target = UnitExtensions.GetUnit(target, this.<+0x20 = state>);
    return !BasePlaybook.WillNormalAttackKill(caster, target, casterTile);

    // IdunBattle.AI.Playbook.Loki.MultiThreatEliminatorPlaybook$$ShouldExecute  --  1 classe
    if (!(attackHealUtility > Fix64(0))) return false;
    return !BasePlaybook.WillNormalAttackKill(caster, target, casterTile);

Le gate vit au slot de vtable +0x328, appele par
`IdunBattle.AI.Playbook.ComparablePlaybooku003C__Il2CppFullySharedGenericTypeu003E$$CalculateActionUtility`
APRES `CalculateCustomUtility + CalculateUtilityFromPredictions` et AVANT les trois termes
positionnels ; `false` -> `Nullable` VIDE = AUCUNE action dans le `Bucket`.

`BasePlaybook$$WillNormalAttackKill` (surcharge 4-args) predit l'attaque NORMALE du caster DEPUIS
`casterTile` et rend `DamagePredictionResult.get_WillBeKill` (le SURE-kill). Consequence de montage,
et c'est ce que le premier sondage a montre : **le gate ne peut mordre que si la cible est a portee
de l'ATTAQUE NORMALE** -- un `astraOrdnance` qui bombarde depuis son spawn passe le gate quelles que
soient les PV de la cible, parce que son attaque normale ne porte pas jusque-la.

## LE DISCRIMINANT, ENONCE AVANT LA MESURE

Carre apparie **(ability x PV de la cible)**, meme board, meme seed, meme geometrie, memes casters :

  * axe CIBLE   : `adeptRetributor.Health/RemainingHealth` = PLEINS ou **1** (kill sur a la normale) ;
  * axe ABILITY : quatre abilities dont le playbook DECLARE le gate, et UNE dont le playbook declare
    le corps TRIVIAL `return true` (`FrenziedFiringPlaybook`, l'un des 35) -- le TEMOIN.

  | caster              | ability                  | bras `nokill` | bras `kill`  |
  |---------------------|--------------------------|---------------|--------------|
  | astraOrdnance       | 1026 BasiliskBarrage     | proposee      | **PAS**      |
  | tyranNeurothrope    | 1104 SpiritLeech         | proposee      | **PAS**      |
  | necroDestroyer      | 1006 MultiThreatElim.    | proposee      | **PAS**      |
  | ultraEliminatorSgt  | 1004 MortisRound         | proposee      | **PAS**      |
  | blackObliterator    | 1036 FrenziedFiring      | proposee      | proposee     |

Le TEMOIN est ce qui rend le bras `kill` concluant : sans lui, « plus aucune ability proposee a
1 PV » se lirait aussi bien comme « le gate mord » que comme « a 1 PV l'attaque normale gagne
l'argmax de toute facon ». Il porte la MEME baisse de PV et reste propose.

Canal NATIF : `aiDryRunAllUnits` (= `CalculateNextActionForUnit`, sans commit).
Canal PORT : `playbook.calculate_action_utility` depuis la tuile COURANTE (`None` = Nullable vide).
Contre-epreuve : le port avec `should_execute` remis au defaut de la base -- STRICTEMENT le port
d'avant cette tranche -- doit MORDRE sur les quatre gate-ees du bras `kill`, et SEULEMENT la.

Usage :
    python scripts/python/probe_419r1tr14r5r2r1r1r1_normal_attack_kill_gate.py \\
        --state-file <ABSOLU>.json

ASCII only.
"""
from __future__ import annotations

import argparse
import contextlib
import json
import os
import subprocess
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

import hexgeo                                                      # noqa: E402
from engine import weights as W                                    # noqa: E402
from engine.ai import context as _ai_ctx                           # noqa: E402
from engine.playbook import scene as _scene                        # noqa: E402
from engine.playbook import get_playbook_or_default                # noqa: E402

BOARD = "MC1_67"
SEED = "4242"
FOE = "adeptRetributor"

#: `(visualId du caster, ability, gate declare ?)`. Les quatre premieres portent l'un des trois
#: corps du gisement ; la derniere porte le corps TRIVIAL `return true` -- c'est le TEMOIN.
CASTERS = (
    ("orksKillaKan",       1171, True),    # SpiritLeechPlaybook$$ShouldExecute     (14 classes)
    ("astraPrimarisPsy",   1027, True),    # idem
    ("necroDestroyer",     1006, True),    # MultiThreatEliminatorPlaybook$$...     (1 classe)
    ("ultraEliminatorSgt", 1004, True),    # SpiritLeechPlaybook$$... via loki_custom
    ("blackObliterator",   1036, False),   # TEMOIN -- corps trivial, aucun gate
)

#: Volet PORTEE : deux casters dont l'ability porte BIEN PLUS LOIN que leur attaque normale, donc
#: qui castent depuis une tuile d'ou l'attaque normale n'atteint pas la cible -- exactement le
#: regime ou le port gatait A TORT (il predisait un `killSure` avec le degat PLANCHER). Les cibles
#: y sont a 1 PV : sans la borne `normal_attack_reaches`, le gate mord et le port REFUSE une action
#: que le natif CHOISIT. Aucune approche : ils tirent depuis leur spawn.
RANGE_CASTERS = (
    ("astraOrdnance",   1026, True),       # FragBombPlaybook$$ShouldExecute (2 classes)
    ("astraBullgryn",   1017, True),       # idem
    ("blackObliterator", 1036, False),     # TEMOIN
)

#: `(tag, PV forces sur les deux cibles ou None = PV pleins)`
ARMS = (("nokill", None), ("kill", 1))

MAX_APPROACH_TURNS = 8


class MontageError(RuntimeError):
    """Le montage n'est pas installe -- un bras qui ne mesure pas ce qu'il annonce."""


# --------------------------------------------------------------------------- plomberie

def _duel(*args) -> tuple:
    p = subprocess.run([sys.executable, "rl_duel.py", *args], cwd=_HERE, capture_output=True,
                       text=True, encoding="utf-8", errors="replace")
    return p.returncode, (p.stdout or "") + (p.stderr or "")


def _build(state_file: str, argv_tail: list) -> int:
    argv = [sys.executable, "rl_duel.py", "build", "--state-file", state_file, *argv_tail]
    p = subprocess.run(argv, cwd=_HERE, capture_output=True, text=True,
                       encoding="utf-8", errors="replace")
    if p.returncode != 0:
        raise MontageError("rl_duel build a echoue (rc=%s) : %s"
                           % (p.returncode, (p.stderr or p.stdout or "")[-800:]))
    return int(json.load(open(state_file, encoding="utf-8"))["runnerId"])


@contextlib.contextmanager
def range_bound_cut():
    """COUPE la BORNE DE PORT `normal_attack_reaches` -- le gate redevient « on predit l'attaque
    normale quelle que soit la portee ». C'est la contre-epreuve de la borne : elle doit MORDRE
    exactement sur les gate-ees du volet PORTEE (le port refuserait alors ce que le natif choisit)
    et rester inerte sur le carre, ou les casters sont a portee."""
    from engine.playbook import normal_attack_kill_gate as G
    saved = G.normal_attack_reaches
    G.normal_attack_reaches = lambda ctx, target, caster_tile: True
    try:
        yield
    finally:
        G.normal_attack_reaches = saved


def run_range(rpc, logs: str, verbose: bool = True) -> list:
    """Volet PORTEE : cibles a 1 PV, casters qui bombardent depuis une tuile d'ou leur ATTAQUE
    NORMALE ne porte pas. Sans la borne, le port REFUSE ce que le natif CHOISIT."""
    rows = []
    case = stage(rpc, logs, "range", 1, casters=RANGE_CASTERS, approach=False)
    try:
        nat = native_proposes(rpc, case, RANGE_CASTERS)
        for vis, ab, gated in RANGE_CASTERS:
            ctx = _ctx(rpc, case, case["ids"][vis])
            port = port_proposes(ctx, ab, case["foes"])
            with range_bound_cut():
                cut = port_proposes(ctx, ab, case["foes"])
            rows.append({"arm": "range", "caster": vis, "ability": ab, "gated": gated,
                         "reached": bool(case["reached"].get(vis)),
                         "native": nat[vis][0], "port": port, "port_range_cut": cut,
                         "msgs": nat[vis][1], "ok": not (nat[vis][0] and not port)})
    finally:
        _dispose(rpc, case["rid"])
    if verbose:
        for r in rows:
            print("  [range ] %-19s ab=%-5d gate=%-5s portee=%-5s natif=%-5s port=%-5s A=%s "
                  "(borne coupee -> port=%s %s)"
                  % (r["caster"], r["ability"], r["gated"], r["reached"], r["native"], r["port"],
                     "OK" if r["ok"] else "VIOLE", r["port_range_cut"],
                     "MORD" if r["port_range_cut"] != r["port"] else "inerte"))
    return rows


def _dispose(rpc, rid) -> None:
    try:
        rpc("disposeRunner", {"runnerId": rid}, 60)
    except Exception:
        pass


def _pos(u) -> tuple | None:
    p = u.get("pos") or {}
    return None if p.get("col") is None else (p["col"], p["row"])


def _normal_ids(u) -> set:
    return {a["id"] for a in (u.get("abilities") or ()) if a.get("kind") == "normal"
            and a.get("id") is not None}


def _has_normal_plan(dv, uid: int, from_here: bool = True) -> bool:
    """L'unite peut-elle porter son ATTAQUE NORMALE, et depuis quelle position ?

    `from_here=True` exige que sa tuile COURANTE figure dans les `ranked` d'un eval d'attaque
    normale -- c'est la condition de montage du bras `kill`, et elle est PLUS FORTE que
    `rankCount > 0`. Le piege a ete mesure : `rankCount > 0` compte les tuiles atteignables APRES
    deplacement, donc un `astraOrdnance` qui bombarde depuis son spawn passait pour « a portee »
    alors que son attaque normale ne porte pas de la ou il tire. Or `ShouldExecute` recoit la tuile
    CANDIDATE, et le port est interroge depuis `ctx.origin`.

    `from_here=False` = l'ancien critere (portee apres deplacement), utilise pour piloter l'approche."""
    nids, here = set(), None
    for u in (dv.get("units") or ()):
        if u.get("id") == uid:
            nids, here = _normal_ids(u), _pos(u)
    for pl in (dv.get("attackPlans") or ()):
        if pl.get("unitId") != uid:
            continue
        for ev in (pl.get("evals") or ()):
            if ev.get("abilityId") not in nids or not ev.get("rankCount"):
                continue
            if not from_here:
                return True
            if any((rk.get("col"), rk.get("row")) == here for rk in (ev.get("ranked") or ())):
                return True
    return False


# --------------------------------------------------------------------------- montage

def _approach(rpc, rid: int, sf: str, casters: dict, foes: list) -> dict:
    """Amene chaque caster a portee de son ATTAQUE NORMALE, en jouant NOS tours seulement
    (`--no-ai` : l'adversaire ne bouge jamais, la geometrie est PILOTEE, pas subie).

    A chaque tour, un caster dont l'attaque normale ne porte pas DEPUIS SA TUILE se deplace sur la
    tuile atteignable qui MINIMISE la distance hex a l'ennemi le plus proche. Un TOUR BLANC clot
    l'approche : sans lui, les unites qui viennent de bouger n'ont plus d'action et
    `aiDryRunAllUnits` rend `FinishUnitTurnMessage` -- mesure, c'est ce qui avait rendu deux lignes
    non concluantes. Rend `{visualId: bool a_portee_depuis_sa_tuile}`."""
    reached = {}
    for _turn in range(MAX_APPROACH_TURNS):
        dv = rpc("decisionView", {"runnerId": rid, "allAbilities": True, "maxRank": 32}, 300)
        epos = [_pos(u) for u in (dv.get("units") or ()) if u.get("id") in foes]
        epos = [p for p in epos if p]
        reached = {vis: _has_normal_plan(dv, uid) for vis, uid in casters.items()}
        if all(reached.values()):
            break
        mov = rpc("aiMovableTiles", {"runnerId": rid}, 90)
        mbu = {m.get("unitId"): m for m in (mov.get("units") or ())}
        moved = False
        for vis, uid in casters.items():
            if reached.get(vis):
                continue
            tiles = [(t.get("col"), t.get("row")) for t in ((mbu.get(uid) or {}).get("tiles") or ())]
            tiles = [t for t in tiles if t[0] is not None]
            if not tiles or not epos:
                continue
            best = min(tiles, key=lambda t: min(hexgeo.distance(t, e) for e in epos))
            rc, _out = _duel("act", "move", "--state-file", sf, "--unit", str(uid),
                             "--to", "%d,%d" % best)
            moved = moved or rc == 0
        if not moved:
            break
        for _ in range(4):
            if rpc("battleStatus", {"runnerId": rid}, 40).get("currentPlayer") == 3:
                break
            _duel("act", "endturn", "--state-file", sf, "--no-ai")
    # TOUR BLANC : on rend la main sans rien faire, pour que toutes les unites entrent dans la
    # mesure avec leur action INTACTE.
    _duel("act", "endturn", "--state-file", sf, "--no-ai")
    for _ in range(4):
        if rpc("battleStatus", {"runnerId": rid}, 40).get("currentPlayer") == 3:
            break
        _duel("act", "endturn", "--state-file", sf, "--no-ai")
    dv = rpc("decisionView", {"runnerId": rid, "allAbilities": True, "maxRank": 32}, 300)
    return {vis: _has_normal_plan(dv, uid) for vis, uid in casters.items()}


def stage(rpc, logs: str, tag: str, hp, casters=CASTERS, approach: bool = True) -> dict:
    """Monte UN bras et rend tout ce dont ses lignes dependent."""
    sf = os.path.join(logs, "tr14r5r2r1r1r1_%s.json" % tag)
    extra = ["--seed", SEED, "--board", BOARD, "--no-ai",
             "--p-units", ",".join(v for v, _a, _g in casters),
             "--a-units", "%s,%s" % (FOE, FOE)]
    if hp is not None:
        extra += ["--unit-stat", "%s:Health=%d,RemainingHealth=%d" % (FOE, hp, hp)]
    rid = _build(sf, extra)
    dv = rpc("decisionView", {"runnerId": rid, "allAbilities": True, "maxRank": 32}, 300)
    ids = {}
    foes = []
    for u in (dv.get("units") or ()):
        if u.get("visualId") == FOE:
            foes.append(u.get("id"))
        else:
            ids[u.get("visualId")] = u.get("id")
    missing = [v for v, _a, _g in casters if ids.get(v) is None]
    if missing or len(foes) != 2:
        _dispose(rpc, rid)
        raise MontageError("montage NON INSTALLE (bras %s) : casters absents=%s, cibles=%d"
                           % (tag, missing, len(foes)))
    reached = (_approach(rpc, rid, sf, ids, foes) if approach
               else {v: _has_normal_plan(dv, ids[v]) for v, _a, _g in casters})
    return {"tag": tag, "rid": rid, "state_file": sf, "hp": hp, "ids": ids, "foes": foes,
            "reached": reached}


# --------------------------------------------------------------------------- lectures

def native_proposes(rpc, case: dict, casters=CASTERS) -> dict:
    """`{visualId: (l'ability est-elle proposee ?, messages)}` -- `aiDryRunAllUnits` contre le MEME
    etat, sans appliquer."""
    dry = rpc("aiDryRunAllUnits", {"runnerId": case["rid"]}, 300)
    by_uid = {}
    for u in (dry.get("units") or ()):
        by_uid[u.get("unitId")] = [(m.get("cls"), m.get("abilityType"), m.get("targetId"))
                                   for m in (u.get("proposed") or ())]
    out = {}
    for vis, ab, _g in casters:
        msgs = by_uid.get(case["ids"][vis]) or []
        out[vis] = (any(c == "ActiveAbilityMessage" and a == ab for c, a, _t in msgs), msgs)
    return out


def _ctx(rpc, case: dict, uid: int):
    dv = rpc("decisionView", {"runnerId": case["rid"], "allAbilities": True, "maxRank": 32}, 300)
    mov = rpc("aiMovableTiles", {"runnerId": case["rid"]}, 90)
    mbu = {u.get("unitId"): u for u in (mov.get("units") or [])}
    return _ai_ctx.build(rpc, case["rid"], dv, mbu, uid, W.load(),
                         _scene.build_predictor(rpc, case["rid"]))


def port_proposes(ctx, ability: int, foes: list) -> bool:
    """Le PORT produit-il une action pour CETTE ability sur AU MOINS une des deux cibles, depuis la
    tuile COURANTE ? `calculate_action_utility` rend `None` = le `Nullable` VIDE natif."""
    pb = get_playbook_or_default(ability)
    return any(pb.calculate_action_utility(ctx, ctx.origin, t, ability) is not None for t in foes)


@contextlib.contextmanager
def gate_cut():
    """COUPE le gate des trois corps -- `should_execute` rend `True` quoi qu'il arrive, c.-a-d.
    STRICTEMENT le port d'avant cette tranche. On mute la METHODE, jamais le code livre.

    Seules les classes qui DECLARENT la methode sont mutees ; `FragBombPlaybook` en herite (elle ne
    la redeclare pas cote port, son delta natif -- `GetUnit` -- etant l'identite sur un `target` qui
    est deja une unite), donc la coupure de sa base la couvre."""
    from engine.playbook.base import ComparablePlaybook
    from engine.playbook import normal_attack_kill_gate as G
    from engine.playbook import loki_custom as L
    declarers = (G.SpiritLeechPlaybook, G.MultiThreatEliminatorPlaybook, L.MortisRoundPlaybook)
    saved = [(cls, cls.should_execute) for cls in declarers]
    for cls in declarers:
        cls.should_execute = ComparablePlaybook.should_execute
    try:
        yield
    finally:
        for cls, fn in saved:
            cls.should_execute = fn


# --------------------------------------------------------------------------- volet CARRE

def run_gate(rpc, logs: str, verbose: bool = True) -> list:
    rows = []
    for tag, hp in ARMS:
        case = stage(rpc, logs, tag, hp)
        try:
            nat = native_proposes(rpc, case)
            for vis, ab, gated in CASTERS:
                ctx = _ctx(rpc, case, case["ids"][vis])
                port = port_proposes(ctx, ab, case["foes"])
                with gate_cut():
                    cut = port_proposes(ctx, ab, case["foes"])
                reached = bool(case["reached"].get(vis))
                rows.append({"arm": tag, "caster": vis, "ability": ab, "gated": gated,
                             "reached": reached,
                             "native": nat[vis][0], "port": port, "port_gate_cut": cut,
                             "msgs": nat[vis][1],
                             # CRITERE A (necessite, symetrique) : le port ne doit JAMAIS refuser
                             # une ability que le natif CHOISIT. C'est le seul sens ou les deux
                             # canaux mesurent la meme chose -- `aiDryRunAllUnits` rend l'action
                             # GAGNANTE, `calculate_action_utility` rend « une action existe ».
                             "ok": not (nat[vis][0] and not port),
                             # CRITERE B (le gate mord cote NATIF) : dans le bras `kill`, un caster
                             # GATE-E et a portee ne doit PAS proposer son ability, alors que le
                             # TEMOIN, meme bras et memes PV, la propose.
                             "b_applies": tag == "kill" and reached,
                             "b_ok": (not nat[vis][0]) if (tag == "kill" and gated) else True})
        finally:
            _dispose(rpc, case["rid"])
    if verbose:
        for r in rows:
            print("  [%-6s] %-19s ab=%-5d gate=%-5s portee=%-5s natif=%-5s port=%-5s A=%s B=%s"
                  % (r["arm"], r["caster"], r["ability"], r["gated"], r["reached"],
                     r["native"], r["port"], "OK" if r["ok"] else "VIOLE",
                     ("OK" if r["b_ok"] else "VIOLE") if r["b_applies"] else "-"))
        print("  -- contre-epreuve gate-coupe (= le port d'avant) --")
        for r in rows:
            print("     [%-6s] %-19s -> port=%-5s %s"
                  % (r["arm"], r["caster"], r["port_gate_cut"],
                     "MORD" if r["port_gate_cut"] != r["port"] else "inerte"))
    return rows


# --------------------------------------------------------------------------- CLI

def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--state-file", required=True, help="chemin ABSOLU (prefixe des state-files)")
    ap.add_argument("--json-out", default=None)
    args = ap.parse_args()

    from rl_collect_batch import _resolve_session, _rpc
    sid = _resolve_session()

    def rpc(method, body=None, timeout=90):
        r = _rpc(sid, method, [body] if body is not None else [], timeout=timeout)
        return r["result"] if isinstance(r, dict) and "result" in r else r

    logs = os.path.dirname(os.path.abspath(args.state_file))
    os.makedirs(logs, exist_ok=True)

    print("session", sid)
    print("== carre apparie (ability gate-ee x PV de la cible) ==")
    rows = run_gate(rpc, logs)
    bad = [r for r in rows if not r["ok"]]
    print("   -> critere A (le port ne refuse jamais ce que le natif choisit) : %d/%d"
          % (len(rows) - len(bad), len(rows)))
    rc = 1 if bad else 0
    bset = [r for r in rows if r["b_applies"]]
    bbad = [r for r in bset if not r["b_ok"]]
    wit = [r for r in rows if r["arm"] == "kill" and not r["gated"]]
    print("   -> critere B (bras `kill`, caster a portee) : %d/%d gate-ees refusees par le natif ; "
          "temoin propose = %s"
          % (len(bset) - len(bbad), len(bset), [r["native"] for r in wit]))
    rc |= 1 if (bbad or not any(r["native"] for r in wit)) else 0
    # La contre-epreuve doit mordre EXACTEMENT sur les gate-ees du bras `kill`.
    wrong = [(r["arm"], r["caster"]) for r in rows
             if (r["port_gate_cut"] != r["port"]) != (r["arm"] == "kill" and r["gated"])]
    print("   -> contre-epreuve gate-coupe : %s"
          % ("conforme" if not wrong else "INATTENDUE sur " + str(wrong)))
    rc |= 1 if wrong else 0

    print("== volet PORTEE (l'ability porte plus loin que l'attaque normale, cibles a 1 PV) ==")
    rrows = run_range(rpc, logs)
    rows += rrows
    rbad = [r for r in rrows if not r["ok"]]
    print("   -> critere A : %d/%d" % (len(rrows) - len(rbad), len(rrows)))
    rc |= 1 if rbad else 0
    rwrong = [r["caster"] for r in rrows
              if (r["port_range_cut"] != r["port"]) != bool(r["gated"] and r["native"])]
    print("   -> contre-epreuve borne-coupee : %s"
          % ("conforme" if not rwrong else "INATTENDUE sur " + str(rwrong)))
    rc |= 1 if rwrong else 0

    if args.json_out:
        with open(args.json_out, "w", encoding="utf-8") as fh:
            json.dump(rows, fh, indent=1)
    return rc


if __name__ == "__main__":
    raise SystemExit(main())
