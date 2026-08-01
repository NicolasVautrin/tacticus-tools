"""#445 -- MONTAGE NOMME des regimes de `AvalancheOfMuscle` (1028) sur la face ATTACK, et mesure
natif contre port.

`IdunBattle.AI.Playbook.Loki.AvalancheOfMusclePlaybook.u003CCalculateAttackUtilityInStepsInternalu003Ed__2$$MoveNext`
a SEPT sorties. Quatre sont ATTEIGNABLES par un montage live et se distinguent par la TUILE
d'attaque et la POSITION du caster -- pas par les stats :

  R_CHARGE   caster loin, tuile au contact de la cible   -> etat 7, terme > 0
  R_KILL     idem, mais la cible est a 1 PV              -> etat 7, terme AUTRE (KillUnit/Overkill)
  R_ALREADY  caster DEJA au contact, il change de tuile  -> etat 6, terme 0 (`CameIntoContact` faux)
  R_STAY     tuile d'attaque == tuile courante           -> etat 3, terme 0 (le caster ne bouge pas)

R_CHARGE et R_KILL sont DEUX points de la MEME chaine (extraDmg -> prediction slot 0x23 ->
composite Damage) : un seul point se fitterait, deux ne se fittent pas. R_ALREADY et R_STAY sont
les deux gates qui distinguent ce playbook d'un simple << au contact >>.

Ne sont PAS atteignables live, et le probe le DIT au lieu de faire semblant :
  * etat 1 (`case.AbilityType == (AbilityOrEffect)(TriggeredAbilityType)1028`) -- anti-recursion,
    sans chemin cote port (cf. la case-doc) ;
  * etat 2 (`!IsUnit(case.Target)`) -- `pairUtility` prend un `targetId` d'unite ;
  * etat 4 (tuile d'attaque hors contact) -- hors portee d'arme, `pairUtility` et le port ne
    mesurent pas la meme chose (constat #438) ; couvert offline par les gardes ;
  * etat 5 (aucune arme) -- `astraBullgryn` est melee et en a toujours une.

Usage :
    python scripts/python/probe_445_avalanche_of_muscle_pair_term.py --state-file <chemin ABSOLU>
    ... [--mutate-before] [--mutate-move] [--mutate-extra]

Les trois `--mutate-*` sont des CONTRE-EPREUVES : elles cassent un etage precis du port et le
probe doit alors rendre des ecarts NON NULS. Un vert sous mutation est le resultat SUSPECT.
ASCII only. Garde jumelle : `scripts/python/tests/engine/test_445_avalanche_of_muscle_pair_term_live.py`.
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

import hexgeo                                                    # noqa: E402
import probe_124_line_elevation_decision as P124                 # noqa: E402
from engine import battle_query as bq                            # noqa: E402
from engine import weights as W                                  # noqa: E402
from engine.ai import context as _ai_ctx                         # noqa: E402
from engine.entities.triggered_ability_type import TriggeredAbilityType   # noqa: E402
from engine.playbook import scene as _scene                      # noqa: E402
from engine.playbook.common import NORMAL_ATTACK_PLAYBOOK        # noqa: E402

BOARD = "MC1_67"
SEED = "41504"
CASTER = "astraBullgryn"        # HERO au pool ; `AvalancheOfMuscle` est dans son kit PASSIF
TGT_FULL = "astraCreed"         # a distance -> R_CHARGE (PV pleins)
TGT_KILL = "astraDreir"         # a distance, PV cales a 1 -> R_KILL
TGT_NEAR = "admecDestroyer"     # ADJACENT au caster -> R_ALREADY / R_STAY
FOES = (TGT_FULL, TGT_KILL, TGT_NEAR)
ABILITY = int(TriggeredAbilityType.AvalancheOfMuscle)         # 0x404 = 1028
EPS = 1e-4                      # Fix64 natif contre float du port


def build_args(board: str, foes: tuple) -> list[str]:
    return ["--board", board, "--p-units", CASTER, "--a-units", ",".join(foes),
            "--unit-stat", f"{foes[1]}:Health=1,RemainingHealth=1"]


class MontageError(RuntimeError):
    """Le montage ne s'installe pas -- la mesure n'a PAS eu lieu (jamais un vert silencieux)."""


# --------------------------------------------------------------------------- oracles

def pair_native(rpc, rid, cid, tgt, ab, tile) -> float:
    r = rpc("pairUtility", {"runnerId": rid, "unitId": cid, "targetId": tgt,
                            "abilityType": ab, "col": tile[0], "row": tile[1]}, 90)
    v = (r or {}).get("utility")
    if not isinstance(v, (int, float)):
        raise MontageError(f"pairUtility natif indisponible pour {tile} / cible {tgt}: {r}")
    return float(v)


def pair_port(ctx, ab, tgt, tile) -> float:
    cand = NORMAL_ATTACK_PLAYBOOK.calculate_action_utility(ctx, tile, tgt, ab)
    if cand is None:
        raise MontageError(f"le port ne produit AUCUNE action depuis {tile} sur {tgt}")
    return float(cand["u"])


# --------------------------------------------------------------------------- montage

def _pick_geometry(walk, elev, mv: int = 3):
    """Une etoile `(P, near, far1, far2)` : `P` la tuile du caster, `near` un VOISIN de `P`, et
    `far1`/`far2` deux tuiles a distance HEX **2** de `P` -- chacune devant garder au moins un
    voisin walkable DISTINCT de `P` (la tuile de charge). `near` doit lui aussi avoir un voisin
    walkable autre que `P` (la tuile de R_ALREADY).

    On DEPLACE les unites pour obtenir cette configuration ; on n'accuse jamais la geometrie de
    spawn."""
    cells = sorted(p for p, w in walk.items() if w and elev.get(p) is not None)
    if not cells:
        raise MontageError("montage NON INSTALLE : boardGraph sans tuile walkable")
    ctr = (sum(c for c, _ in cells) / len(cells), sum(r for _, r in cells) / len(cells))

    def ring(p, iso=None):
        """Voisins walkables de `p`. `iso` = elevation imposee -- le montage se tient sur un
        PALIER UNIQUE : le gate melee natif refuse deja une cible a `|delta elev| == 1` sur
        certains boards (MESURE : `C3_26`, `pairUtility` natif = 0), et un montage a relief ne
        mesurerait plus les gates de CE playbook. Le regime ELEVATION reste donc non couvert,
        et c'est dit."""
        return [q for q in hexgeo.neighbors(p[0], p[1])
                if walk.get(q) and elev.get(q) is not None
                and (elev[q] == iso if iso is not None else abs(elev[q] - elev[p]) < 2)]

    for p in sorted(cells, key=lambda q: (q[0] - ctr[0]) ** 2 + (q[1] - ctr[1]) ** 2):
        e0 = elev[p]
        r0 = ring(p, e0)          # anneau 1 de `p` : ces tuiles sont A COUP SUR des tuiles d'action

        def has_contact(dest):
            """Existe-t-il une tuile de contact de `dest` **dans l'anneau 1 de `p`** ? Prendre la
            tuile de charge a distance 1 du caster est ce qui garantit qu'elle sera dans
            `ctx.action_tiles` : une tuile plus lointaine depend du pathfinding reel (obstacles),
            et un montage bati dessus echoue sur les boards cloisonnes (MESURE : `C3_22`)."""
            return any(t != p and hexgeo.distance(t, dest) == 1 for t in r0)

        near_c = [n for n in r0 if has_contact(n)]
        far_c = [q for q in cells
                 if hexgeo.distance(p, q) == 2 and elev.get(q) == e0 and has_contact(q)]
        for near in near_c:
            for i, a in enumerate(far_c):
                for b in far_c[i + 1:]:
                    return p, near, a, b
    raise MontageError("montage NON INSTALLE : aucune etoile (tuile + 1 voisin + 2 tuiles a "
                       "distance 2, sur un palier unique, chacune avec une tuile de contact dans "
                       "l'anneau 1 du caster) sur ce board")


def _stage(sid, rpc, rid: int, foes: tuple = FOES) -> dict:
    """Installe l'etoile, atteste le cablage, et rend le contexte de decision + les tuiles.

    `foes` = `(cible LOIN a PV pleins, cible LOIN a 1 PV, cible ADJACENTE)` -- les trois roles
    geometriques du montage, parametrables pour rejouer sur un autre board / d'autres unites."""
    t_full, t_kill, t_near = foes
    elev, walk, _tid = P124._board(sid, rid)
    dv = rpc("decisionView", {"runnerId": rid, "allAbilities": True, "maxRank": 32}, 180)
    units = dv.get("units") or []
    mine = [u for u in units if u.get("ctrl") and u.get("alive")]
    cid = next((u["id"] for u in mine if u.get("visualId") == CASTER), None)
    if cid is None:
        raise MontageError(f"montage NON INSTALLE : {CASTER} absent du roster")
    myplayer = mine[0].get("owner")
    tgt = {}
    for vis in foes:
        u = next((x for x in units if x.get("owner") != myplayer and x.get("alive")
                  and x.get("visualId") == vis), None)
        if u is None:
            raise MontageError(f"montage NON INSTALLE : {vis} absent du roster adverse")
        tgt[vis] = u["id"]

    # (a) LE PASSIF EST-IL DANS L'AbilitiesComponent ? Sans 1028 dedans, le dispatcher ne l'itere
    #     pas et la mesure ne prouverait rien (moitie CABLAGE du patron #419).
    st = rpc("unitAbilityStates", {"runnerId": rid, "unitId": cid}, 60) or {}
    live_ids = [i for u in (st.get("units") or []) for t in (u.get("triggered") or [])
                for i in [((t.get("raw") or [None])[0])] if isinstance(i, int)]
    if ABILITY not in live_ids:
        raise MontageError(
            f"montage NON INSTALLE : {ABILITY} n'est PAS dans l'AbilitiesComponent de {CASTER} "
            f"-- triggered live lus = {sorted(set(live_ids))}")

    p, near, far1, far2 = _pick_geometry(walk, elev)
    wanted = {cid: p, tgt[t_near]: near, tgt[t_full]: far1, tgt[t_kill]: far2}
    if not P124._drive_to(sid, rid, walk, elev, wanted):
        _dv, pos = P124._positions(sid, rid)
        raise MontageError(f"montage NON INSTALLE : placement incomplet -- voulu {wanted}, "
                           f"obtenu { {u: pos.get(u) for u in wanted} }")
    P124._give_turn_back(sid, rid, myplayer)

    dv = rpc("decisionView", {"runnerId": rid, "allAbilities": True, "maxRank": 32}, 180)
    mov = rpc("aiMovableTiles", {"runnerId": rid}, 60)
    mbu = {u.get("unitId"): u for u in (mov.get("units") or [])}
    ctx = _ai_ctx.build(rpc, rid, dv, mbu, cid, W.load(), _scene.build_predictor(rpc, rid))
    ab = next(iter(ctx.normal_ids or ()), None)
    if ab is None:
        raise MontageError("montage NON INSTALLE : aucune attaque normale sur le caster")

    tiles = {t for t in (ctx.action_tiles or []) if t and t[0] is not None}
    if p not in tiles:
        raise MontageError(f"montage NON INSTALLE : la tuile COURANTE {p} du caster n'est pas une "
                           f"tuile d'action -- le regime R_STAY est inatteignable")

    def charge_tile(dest, label):
        """Une tuile d'action ADJACENTE a `dest`, DIFFERENTE de la tuile courante `p`, sur le meme
        palier. Adjacence NATIVE (porte d'elevation `|delta| < 2`), jamais la distance hex nue :
        sur un board a relief, deux tuiles voisines peuvent etre NON adjacentes pour le moteur."""
        cands = sorted(t for t in tiles
                       if t != p and elev.get(t) == elev.get(p) and bq.is_adjacent(t, dest, elev)
                       and hexgeo.distance(t, p) == 1)
        if not cands:
            raise MontageError(f"montage NON INSTALLE : aucune tuile d'action au contact de "
                               f"{label} en {dest} et distincte de {p}")
        return cands[0]

    cases = {
        # R_CHARGE / R_KILL : le caster part de `p` (a distance 2 de la cible) vers une tuile au
        # contact -> `CameIntoContactWithEnemy` VRAI, mouvement reel.
        "R_CHARGE": {"tgt": t_full, "tile": charge_tile(far1, t_full), "nonzero": True},
        "R_KILL": {"tgt": t_kill, "tile": charge_tile(far2, t_kill), "nonzero": True},
        # R_ALREADY : le caster est DEJA au contact de `near` et change simplement de tuile ->
        # `!AreAdjacent(GetTiles(caster), targetTiles)` FAUX -> etat 6.
        "R_ALREADY": {"tgt": t_near, "tile": charge_tile(near, t_near), "nonzero": False},
        # R_STAY : tuile d'attaque == tuile courante -> etat 3.
        "R_STAY": {"tgt": t_near, "tile": p, "nonzero": False},
    }
    # Attestation GEOMETRIQUE des gates -- positions LUES du runner, adjacence NATIVE (elevation).
    _dv2, pos = P124._positions(sid, rid)
    if pos.get(cid) != p:
        raise MontageError(f"montage NON ATTESTE : le caster est en {pos.get(cid)} et non {p}")
    if not bq.is_adjacent(p, pos[tgt[t_near]], elev):
        raise MontageError(f"montage NON ATTESTE : {t_near} devait etre ADJACENT au caster "
                           f"(porte d'elevation incluse) -- R_ALREADY/R_STAY seraient faux")
    for vis in (t_full, t_kill):
        if bq.is_adjacent(p, pos[tgt[vis]], elev):
            raise MontageError(f"montage NON ATTESTE : {vis} est DEJA au contact du caster "
                               f"(sinon R_CHARGE n'est pas une CHARGE)")

    # Attestation par l'ORACLE : depuis sa tuile courante, le caster DOIT pouvoir frapper la cible
    # adjacente (`pairUtility` non nul). Un 0 natif signifie que la cible n'est pas a portee cote
    # moteur -- alors R_STAY ne mesure PAS le gate << le caster ne bouge pas >>, il mesure un
    # hors-portee. MESURE : c'est exactement ce qui s'est produit sur un premier essai `C3_26`.
    if abs(pair_native(rpc, rid, cid, tgt[t_near], ab, p)) <= EPS:
        raise MontageError(f"montage NON ATTESTE : `pairUtility` natif rend 0 sur {t_near} depuis "
                           f"la tuile courante {p} -- la cible n'est pas a portee, R_STAY ne "
                           f"mesurerait pas le gate vise")
    return {"rid": rid, "cid": cid, "tgt": tgt, "ab": ab, "ctx": ctx, "cases": cases,
            "home": p, "pos": pos}


def measure(rpc, case: dict) -> list[dict]:
    """Une ligne par regime : natif, port, port SANS le playbook 1028."""
    import engine.playbook.psyker as PSY
    out = []
    for name, c in case["cases"].items():
        uid = case["tgt"][c["tgt"]]
        tile = c["tile"]
        nat = pair_native(rpc, case["rid"], case["cid"], uid, case["ab"], tile)
        port = pair_port(case["ctx"], case["ab"], uid, tile)
        saved = PSY.TRIGGERED_ATTACK_PLAYBOOKS.pop(ABILITY, None)
        if saved is None:
            raise MontageError("le playbook 1028 n'est PAS au registre -- rien a muter")
        try:
            muted = pair_port(case["ctx"], case["ab"], uid, tile)
        finally:
            PSY.TRIGGERED_ATTACK_PLAYBOOKS[ABILITY] = saved
        out.append({"regime": name, "target": c["tgt"], "tile": tile, "nonzero": c["nonzero"],
                    "native": nat, "port": port, "port_muted": muted})
    return out


def verdict(rows: list[dict]) -> tuple[bool, list[str]]:
    """PASS ssi (a) port == natif partout, (b) le terme du playbook est NON NUL sur les regimes
    qui doivent l'etre et NUL sur les autres, et (c) R_CHARGE != R_KILL (deux points de la MEME
    chaine -- sans quoi la mesure ne serait qu'un scalaire fitte)."""
    errs = []
    for r in rows:
        term = r["port"] - r["port_muted"]
        if abs(r["port"] - r["native"]) > EPS:
            # DIAGNOSTIC : si le playbook ne verse RIEN sur cette ligne, l'ecart ne vient pas de
            # lui -- c'est un residu PREEXISTANT du moteur sur ce montage, et le dire evite de
            # l'imputer a la tranche (MESURE : premier essai `C3_26` / `orksNob`).
            src = ("residu PREEXISTANT (le playbook verse 0 sur cette ligne)"
                   if abs(term) <= EPS else "ecart imputable au playbook")
            errs.append(f"{r['regime']}: port {r['port']:.6f} != natif {r['native']:.6f} -- {src}")
        if r["nonzero"] and abs(term) <= EPS:
            errs.append(f"{r['regime']}: le playbook ne verse RIEN ({term:+.6f}) -- regime degenere")
        if not r["nonzero"] and abs(term) > EPS:
            errs.append(f"{r['regime']}: le playbook verse {term:+.6f} alors que le gate natif "
                        f"doit rendre 0")
    by = {r["regime"]: r["port"] - r["port_muted"] for r in rows}
    if "R_CHARGE" in by and "R_KILL" in by and abs(by["R_CHARGE"] - by["R_KILL"]) <= EPS:
        errs.append(f"R_CHARGE et R_KILL versent le MEME terme ({by['R_CHARGE']:.6f}) -- un seul "
                    f"point mesure, la chaine n'est pas discriminee")
    return (not errs), errs


# --------------------------------------------------------------------------- mutations

def apply_mutation(kind: str) -> None:
    """Contre-epreuves : chacune casse UN etage nomme du port. La mutation est appliquee sur
    l'objet du REGISTRE, donc elle mord le meme chemin que la mesure."""
    import engine.playbook.psyker as PSY
    pb = PSY.TRIGGERED_ATTACK_PLAYBOOKS[ABILITY]
    if kind == "before":
        # retire le conjonct `!AreAdjacent(GetTiles(caster), targetTiles)` -> R_ALREADY doit rougir
        pb._came_into_contact_with_enemy = staticmethod(
            lambda scene, caster_pos, attack_tile, tgt_pos: bool(
                __import__("engine.battle_query", fromlist=["is_adjacent"]).is_adjacent(
                    attack_tile, tgt_pos, getattr(scene, "elev_by_pos", None))))
    elif kind == "move":
        # retire le gate etat 3 (`casterTile == mainTile`) -> R_STAY doit rougir
        orig = type(pb).calculate_attack_utility_in_steps

        def patched(self, ctx, attacker_uid, ability_id, case_tgt_id, attack_tile, prediction=None):
            sc = getattr(ctx, "scene", None)
            if sc is not None and attack_tile is not None:
                cur = sc.pos(attacker_uid)
                if cur is not None and tuple(attack_tile) == tuple(cur):
                    # on FEINT un mouvement en decalant la tuile courante lue
                    class _Shim:
                        def __getattr__(_s, n):
                            return getattr(sc, n)

                        def pos(_s, uid):
                            return (-99, -99) if uid == attacker_uid else sc.pos(uid)
                    ctx = type("C", (), {k: getattr(ctx, k) for k in dir(ctx)
                                         if not k.startswith("__")})()
                    ctx.scene = _Shim()
            return orig(self, ctx, attacker_uid, ability_id, case_tgt_id, attack_tile, prediction)
        pb.calculate_attack_utility_in_steps = patched.__get__(pb, type(pb))
    elif kind == "extra":
        # magnitude x2 -> R_CHARGE et R_KILL doivent rougir (l'etage `extraDmg`)
        orig_extra = type(pb)._extra_damage
        pb._extra_damage = (lambda self, scene, uid: (lambda v: None if v is None else int(v) * 2)(
            orig_extra(self, scene, uid))).__get__(pb, type(pb))
    else:
        raise MontageError(f"mutation inconnue : {kind}")


# --------------------------------------------------------------------------- CLI

def _build(state_file: str, seed: str, extra: list[str]) -> int:
    argv = [sys.executable, "rl_duel.py", "build", "--seed", str(seed),
            "--state-file", state_file, *extra]
    p = subprocess.run(argv, cwd=_HERE, capture_output=True, text=True,
                       encoding="utf-8", errors="replace")
    if p.returncode != 0:
        raise MontageError(f"rl_duel build a echoue (rc={p.returncode}) : "
                           f"{(p.stderr or p.stdout or '')[-800:]}")
    return int(json.load(open(state_file, encoding="utf-8"))["runnerId"])


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--state-file", required=True,
                    help="chemin ABSOLU du state-file (le probe construit SON runner dessus)")
    ap.add_argument("--mutate-before", action="store_true",
                    help="contre-epreuve : retire le conjonct << pas deja au contact >>")
    ap.add_argument("--mutate-move", action="store_true",
                    help="contre-epreuve : retire le gate << le caster bouge >>")
    ap.add_argument("--mutate-extra", action="store_true",
                    help="contre-epreuve : double la magnitude extraDmg")
    ap.add_argument("--board", default=BOARD, help="board de montage (defaut MC1_67)")
    ap.add_argument("--seed", default=SEED, help="seed de build (defaut 41504)")
    ap.add_argument("--foes", default=",".join(FOES),
                    help="trois visualIds adverses : LOIN-PV-pleins,LOIN-1PV,ADJACENT")
    args = ap.parse_args()
    foes = tuple(x.strip() for x in args.foes.split(",") if x.strip())
    if len(foes) != 3:
        raise SystemExit("--foes attend EXACTEMENT trois visualIds")

    from rl_collect_batch import _resolve_session, _rpc
    sid = _resolve_session()

    def rpc(method, body=None, timeout=90):
        r = _rpc(sid, method, [body] if body is not None else [], timeout=timeout)
        return r["result"] if isinstance(r, dict) and "result" in r else r

    rid = _build(args.state_file, args.seed, build_args(args.board, foes))
    case = _stage(sid, rpc, rid, foes)
    for kind, on in (("before", args.mutate_before), ("move", args.mutate_move),
                     ("extra", args.mutate_extra)):
        if on:
            apply_mutation(kind)
            print(f"[MUTATION] {kind} -- des ecarts NON NULS sont ATTENDUS")

    from engine.playbook.avalanche_of_muscle import AvalancheOfMusclePlaybook
    amt = AvalancheOfMusclePlaybook()._extra_damage(case["ctx"].scene, case["cid"])
    print(f"runner {rid} | board {args.board} seed {args.seed} | caster u{case['cid']} {CASTER} "
          f"en {case['home']} | ab={case['ab']} | extraDmg porte = {amt}")
    rows = measure(rpc, case)
    for r in rows:
        term = r["port"] - r["port_muted"]
        d = r["port"] - r["native"]
        print(f"  {r['regime']:<10} {r['target']:<16} @{str(r['tile']):<9} "
              f"nat={r['native']:.6f} port={r['port']:.6f} d={d:+.6f} | "
              f"mute={r['port_muted']:.6f} terme={term:+.6f} attendu={'>0' if r['nonzero'] else '0'}")
    ok, errs = verdict(rows)
    for e in errs:
        print(f"  [X] {e}")
    print("VERDICT: " + ("PASS" if ok else "FAIL"))
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
