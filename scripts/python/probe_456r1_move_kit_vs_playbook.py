"""#456-r1 -- DEPARTAGER les deux causes de l'ecart de valeur du terme MOVE (9 lignes sur 102).

CE QUE #456 A LAISSE OUVERT. Son etage E5 a mesure que le port rend `0.0` la ou le natif produit
20/40/101/202/303, a LOCALISE l'etage (`load_playbook` rend `None` pour `1133 CyclicIonBlaster` et
`1145 SereneUnifier`) et a REFUSE de departager deux causes :

  (a) le PLAYBOOK de l'ability n'est pas porte cote Python -- le registre `TRIGGERED_MOVE_PLAYBOOKS`
      n'a pas d'entree pour elle, alors que le natif en a une ;
  (b) le KIT lu par le port est plus etroit que l'`AbilitiesComponent` que le natif itere -- le
      terme natif vient d'une ability que le canal du port ne publie PAS.

CE PROBE LES DEPARTAGE, PAR UNITE, SANS la decomposition par playbook (`contribs`, qui exige une
fenetre de reinject). Le discriminant est le KIT, pas la valeur :

    kit_natif  = `unitAbilityStates` -> `TriggeredAbility.AbilityName` (`raw[0]`) de CHAQUE entree
                 du `TriggeredAbilityComponent`. C'est LITTERALEMENT la collection que
                 `IdunBattle.AI.Utilities.TriggeredAbilitiesUtility.u003CEvaluateMovementInStepsu003Ed__2$$MoveNext`
                 enumere (`case.unit@+0x10` -> GetComponent -> `+0x18` -> GetEnumerator).
    kit_port   = `runner_tile_leaf_ctx(state, uid)["unit_triggered_abilities"]`, ce que la feuille
                 `TriggeredAbilitiesUtility.evaluate` du port boucle reellement.

    (b) mord si  kit_natif \\ kit_port  != {}                 -> le port ne VOIT pas l'ability
    (a) mord si  {ab in kit_natif : load_playbook(ab) is None} != {}   -> le port la voit et n'a
                                                                          pas son playbook

Les deux sont INDEPENDANTES et peuvent coexister sur la meme bataille, sur des unites differentes :
c'est precisement pourquoi #456 refusait de generaliser de l'une a l'autre.

Montage : celui de #443-r1a (`MC1_67`/777, greffe 1120 sur `tauCrisis`), pour que la mesure porte
sur LES MEMES 102 events -- un autre montage ne fermerait pas le meme residu.

Usage (depuis scripts/python) :
    python probe_456r1_move_kit_vs_playbook.py --state-file <ABSOLU> [--no-graft] [--keep]

ASCII only.
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from contextlib import contextmanager
from pathlib import Path

import requests

HOST = "http://127.0.0.1:8765"
_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _HERE)

BOARD = "MC1_67"
SEED = "777"
FALLBACK_P_UNITS = ["tauCrisis", "tauAunShi", "tauDarkstrider", "ultraTitus"]
FALLBACK_A_UNITS = ["tauShadowsun", "astraCreed"]


# ------------------------------------------------------------------ verdict (fonction PURE)

def check_kit_gap(rows) -> dict:
    """LE VERDICT DE TRANCHAGE. `rows` : une par unite vue dans les events du capteur, avec
    `unitId`, `visualId`, `kit_natif`, `kit_port`, `sans_playbook` (ids du kit NATIF que
    `load_playbook` ne charge pas) et `nat_owner` (totaux natifs DISTINCTS de la face OWNER).

    Rend `{"status", "message", "cause_b", "cause_a", "ecarte"}`.

    TROIS etats, et la dissymetrie entre eux est le coeur du probe :

      * **(b) DECIDABLE SEUL** -- `kit_natif \\ kit_port != {}`. Aucune valeur n'est requise : le
        port ne PRESENTE pas au dispatcher ce que le natif lui presente. C'est un fait de canal.

      * **(a) SUSPECTE, jamais ETABLIE ICI** -- une ability du kit natif sans playbook au registre
        du port, ALORS QUE le natif produit une valeur NON NULLE pour cette unite. « Suspecte »
        parce que le natif SKIPPE lui aussi toute ability sans playbook
        (`PlaybookDatabase$$LoadPlaybook` -> null -> `continue`) : tant que l'unite porte AUSSI une
        ability dont le playbook EST porte, l'imputation exige la decomposition. Ce qui tranche
        pour de bon est la CONFRONTATION DE VALEUR (E4), pas le kit.

      * **(a) ECARTEE PAR LA MESURE** -- des abilities sans playbook porte, mais le natif rend
        `0.0` PARTOUT pour cette unite. Le natif ne charge donc pas de playbook pour elles non
        plus : il n'y a AUCUN trou de portage, et le port a raison de rendre 0. C'est ce qui
        distingue « le port ignore une ability » de « le jeu n'a rien a en faire ». Sans cet etat,
        tout kit un peu fourni se lirait comme un trou -- et c'est exactement l'erreur que #456 a
        commise en nommant `1133 CyclicIonBlaster` : son `missing` derivait du kit PORT, et rien
        ne le confrontait au fait que le natif rend `0.0` pour son porteur.

    STATUT `no-rows` / `degenerate` : on ne conclut RIEN (ni « pas de trou », ni « trou partout »).
    Un kit natif vide se lit comme un canal MUET, pas comme une mesure."""
    if not rows:
        return {"status": "no-rows", "cause_a": {}, "cause_b": {}, "ecarte": {},
                "message": "aucune unite confrontee -- RIEN n'est conclu"}
    if not any(r.get("kit_natif") for r in rows):
        return {"status": "degenerate", "cause_a": {}, "cause_b": {}, "ecarte": {},
                "message": ("le kit NATIF est vide sur les %d unite(s) : le canal "
                            "`unitAbilityStates` est MUET ici, la comparaison serait degeneree "
                            "(vide == vide passerait)" % len(rows))}
    cause_b, cause_a, ecarte = {}, {}, {}
    for r in rows:
        nat, port = list(r.get("kit_natif") or ()), set(r.get("kit_port") or ())
        invisibles = [a for a in nat if a not in port]
        if invisibles:
            cause_b[r["unitId"]] = invisibles
        sp = [a for a in nat if a in port and a in set(r.get("sans_playbook") or ())]
        if not sp:
            continue
        if any(abs(float(x)) > 1e-6 for x in (r.get("nat_owner") or ())):
            cause_a[r["unitId"]] = sp
        else:
            ecarte[r["unitId"]] = sp
    if not cause_a and not cause_b:
        return {"status": "ok", "cause_a": {}, "cause_b": {}, "ecarte": ecarte,
                "message": ("%d unite(s) : kit natif == kit port PARTOUT ; les %d unite(s) portant "
                            "une ability sans playbook au registre rendent `0.0` cote NATIF -- le "
                            "jeu les skippe aussi, aucun trou de portage : %s"
                            % (len(rows), len(ecarte), json.dumps(ecarte, sort_keys=True)))}
    parts = []
    if cause_b:
        parts.append("CAUSE (b) KIT TROP ETROIT sur %d unite(s) : %s"
                     % (len(cause_b), json.dumps(cause_b, sort_keys=True)))
    if cause_a:
        parts.append("CAUSE (a) SUSPECTE (natif NON NUL + ability sans playbook) sur %d unite(s) : "
                     "%s -- a trancher par la confrontation de VALEUR"
                     % (len(cause_a), json.dumps(cause_a, sort_keys=True)))
    if ecarte:
        parts.append("(a) ECARTEE par la mesure sur %d unite(s) (natif == 0.0 partout) : %s"
                     % (len(ecarte), json.dumps(ecarte, sort_keys=True)))
    return {"status": "gap", "cause_a": cause_a, "cause_b": cause_b, "ecarte": ecarte,
            "message": " | ".join(parts)}


# ------------------------------------------------------------------ transport

def sid() -> int:
    return int(requests.get(f"{HOST}/api/admin/status", timeout=10).json()["session"]["id"])


def rpc(s: int, method: str, args=None, timeout: int = 60, tolerate_unknown: bool = False):
    r = requests.post(f"{HOST}/api/scripts/{s}/rpc",
                      json={"method": method, "args": [args or {}], "timeout": int(timeout) * 1000},
                      timeout=timeout + 30)
    if r.status_code >= 400:
        if tolerate_unknown:
            return None
        raise RuntimeError("%s HTTP %d: %s" % (method, r.status_code, r.text[:400]))
    body = r.json()
    if body.get("error"):
        if tolerate_unknown:
            return None
        raise RuntimeError(str(body["error"])[:400])
    return body.get("result")


def native_kits(s: int, rid: int) -> dict:
    """`{unitId: [TriggeredAbilityType]}` -- l'`AbilitiesComponent` REEL, toutes hierarchies
    confondues (`raw[0]` = `TriggeredAbility.AbilityName`). MEME lecture que
    `engine/ai/context.py::live_triggered_kits`, refaite ici pour que le probe ne depende pas du
    cache d'un autre module."""
    out: dict = {}
    r = rpc(s, "unitAbilityStates", {"runnerId": rid}, 60) or {}
    for u in (r.get("units") or []):
        uid = u.get("entityId")
        if uid is None:
            continue
        ids = []
        for t in (u.get("triggered") or []):
            raw = (t or {}).get("raw") or []
            v = raw[0] if raw else None
            if isinstance(v, int) and v > 0 and v not in ids:
                ids.append(v)
        out[int(uid)] = ids
    return out


@contextmanager
def _null_binder():
    """Contre-epreuve `--no-bind` : AUCUN transport ambiant, donc `_auto_ability_states` rend
    `no-transport` et le port lit le kit GAMECONFIG -- l'etat exact d'avant le cablage de #456-r1."""
    yield None


def _graft_seed_bc(tag: str, spec: str = "tauCrisis:SaviorProtocols"):
    """Greffe `replace=True` : elle REMPLACE les passifs du porteur. C'est ce qui rend le montage
    discriminant dans les DEUX sens -- le natif perd l'ability de kit ET gagne la greffee, donc le
    kit gameconfig devient faux par exces ET par defaut sur la meme unite."""
    import catalog_inject as CI
    out = os.path.join(os.path.dirname(_HERE), "..", "logs", "seedbc-456r1-%s.json" % tag)
    out = os.path.abspath(out)
    os.makedirs(os.path.dirname(out), exist_ok=True)
    return CI.write_grafted_seed_bc(out, [spec], replace=True)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--seed", default=SEED)
    ap.add_argument("--board", default=BOARD)
    ap.add_argument("--state-file", required=True)
    ap.add_argument("--no-graft", action="store_true")
    ap.add_argument("--graft", default="tauCrisis:SaviorProtocols", metavar="VISUALID:Ability",
                    help="greffe REMPLACANTE posee au seed BC (defaut : le montage de #443-r1a)")
    ap.add_argument("--no-bind", action="store_true",
                    help="CONTRE-EPREUVE (b) : ne lie AUCUN transport ambiant -> le port lit le "
                         "kit gameconfig (etat d'avant le cablage de #456-r1)")
    ap.add_argument("--drop-playbook", type=int, default=None, metavar="ABILITY_ID",
                    help="CONTRE-EPREUVE (a) : retire cette entree de TRIGGERED_MOVE_PLAYBOOKS "
                         "avant de confronter (ex. 1145) -- l'etat d'avant le port du playbook")
    ap.add_argument("--moves", default=None, metavar="VISUALID:COL,ROW;...",
                    help="DRIVE les positions avant de mesurer (`applyAction move`). C'est le "
                         "levier de GENERALISATION : la geometrie de spawn ne produit qu'UNE "
                         "configuration, et un port faux peut y passer.")
    ap.add_argument("--reuse", action="store_true")
    ap.add_argument("--keep", action="store_true")
    a = ap.parse_args()

    if a.drop_playbook is not None:
        # CONTRE-EPREUVE (a). On retire l'entree du registre AVANT tout appel a `load_playbook` :
        # `TRIGGERED_MOVE_PLAYBOOKS` est le dict module-level que `load_playbook` interroge, et le
        # retrait reproduit EXACTEMENT le regime d'avant le port (`load_playbook -> None` ->
        # `continue`, comme le natif quand `PlaybookDatabase$$LoadPlaybook` rend null).
        from engine.playbook.adjacent_unit_preference import TRIGGERED_MOVE_PLAYBOOKS
        gone = TRIGGERED_MOVE_PLAYBOOKS.pop(int(a.drop_playbook), None)
        print("   CONTRE-EPREUVE (a) : entree %d %s du registre MOVE"
              % (a.drop_playbook, "RETIREE" if gone is not None else "DEJA ABSENTE"))

    s = sid()
    st = rpc(s, "triggeredMoveTraceStatus", {}, 30, tolerate_unknown=True)
    if st is None:
        print("E0 canal   [not_reinjected] le capteur #443-r1a n'est PAS charge -- NON CONFRONTE")
        return 7
    print("E0 canal   [ok] capteur charge")

    seed_bc = None
    if not a.no_graft:
        try:
            seed_bc, _ = _graft_seed_bc(str(os.getpid()), a.graft)
        except Exception as e:                                            # noqa: BLE001
            print("   greffe 1120 INDISPONIBLE (%s) -- on continue sans" % str(e)[:160])

    if not a.reuse:
        argv = [sys.executable, "rl_duel.py", "build", "--seed", str(a.seed),
                "--board", a.board, "--state-file", a.state_file,
                "--p-units", ",".join(FALLBACK_P_UNITS),
                "--a-units", ",".join(FALLBACK_A_UNITS)]
        if seed_bc:
            argv += ["--seed-bc", str(seed_bc)]
        out = subprocess.run(argv, cwd=_HERE, capture_output=True, text=True,
                             encoding="utf-8", errors="replace")
        if out.returncode != 0:
            print("BUILD FAILED rc=%d" % out.returncode)
            print((out.stdout or "")[-1500:])
            print((out.stderr or "")[-1500:])
            return 1
    rid = json.loads(Path(a.state_file).read_text(encoding="utf-8"))["runnerId"]
    print("runnerId=%s board=%s seed=%s session=%s greffe=%s"
          % (rid, a.board, a.seed, s, bool(seed_bc)))

    try:
        if a.moves:
            # DRIVE des positions. `applyAction` ne verifie pas la propriete du `unitId` : on
            # positionne les deux camps a volonte, sans passer par l'IA ni par un tour. On lit le
            # mapping visualId -> entityId sur la vue de decision AVANT de bouger.
            dv0 = rpc(s, "decisionView", {"runnerId": rid, "maxRank": 1}, 90) or {}
            by_vis = {u.get("visualId"): u.get("id") for u in (dv0.get("units") or [])}
            for spec in a.moves.split(";"):
                spec = spec.strip()
                if not spec:
                    continue
                vis, cr = spec.split(":", 1)
                col, row = (int(x) for x in cr.split(","))
                uid = by_vis.get(vis.strip())
                if uid is None:
                    print("   move %-16s IGNORE -- visualId absent de la vue" % vis)
                    continue
                res = rpc(s, "applyAction",
                          {"runnerId": rid,
                           "action": {"kind": "move", "unitId": int(uid),
                                      "to": {"col": col, "row": row}}}, 90,
                          tolerate_unknown=True)
                # ⚠ `applyAction` rend `ok` meme quand la tuile est HORS du movable set : le move
                # est alors SILENCIEUSEMENT sans effet. Mesure du 2026-08-02 : sur 4 moves rendus
                # `ok`, UN n'avait pas pris (l'unite est restee a son spawn) -- et le montage
                # d'elevation qui en dependait rendait « branche non atteinte » alors que c'etait
                # le DRIVE qui n'avait pas mordu. On RELIT donc la position.
                got = None
                for u in ((rpc(s, "decisionView", {"runnerId": rid, "maxRank": 1}, 90)
                           or {}).get("units") or []):
                    if u.get("id") == uid:
                        p = u.get("pos") or {}
                        got = (p.get("col"), p.get("row"))
                pris = (got == (col, row))
                print("   move %-16s u%-4s -> (%d,%d)  %s (position relue %s)"
                      % (vis, uid, col, row,
                         "PRIS" if pris else "SANS EFFET (hors movable set)", got))
            # Deux `endturn` : une unite qui vient de bouger n'a plus d'activation, donc le sweep
            # `aiDryRunAllUnits` ne l'evaluerait plus. Faire le tour complet la rend au tour
            # suivant, AVEC ses nouvelles positions. `applyAction` ne fait jamais jouer l'IA : les
            # positions posees ici sont donc celles qu'on mesure.
            for _ in range(2):
                rpc(s, "applyAction", {"runnerId": rid, "action": {"kind": "endturn"}}, 90,
                    tolerate_unknown=True)

        rpc(s, "triggeredMoveTraceClear", {"runnerId": rid}, 30)
        rpc(s, "triggeredMoveTraceOn", {"runnerId": rid}, 60)
        rpc(s, "aiDryRunAllUnits", {"runnerId": rid}, 180, tolerate_unknown=True)
        dump = rpc(s, "triggeredMoveTraceDump", {"runnerId": rid, "max": 4000}, 60) or {}
        entries = dump.get("entries") or []
        print("E1 events  [%s] %d event(s) captes" % ("ok" if entries else "vide", len(entries)))

        kits = native_kits(s, rid)
        print("E2 kit natif : %d unite(s) dans `unitAbilityStates`" % len(kits))

        # ---- l'etat du port, MEME reconstruction que `probe_443r1a._port_rows` ---------------- #
        from engine.entities.pathfinding.board import Board
        from engine.playbook.adjacent_unit_preference import load_playbook
        from engine.runner.snapshot import live_rpc, load_state
        from engine.utilities.tile import runner_tile_leaf_ctx

        dv = rpc(s, "decisionView", {"runnerId": rid}, 120)
        ob = rpc(s, "observeBattle", {"runnerId": rid}, 60)
        snap = rpc(s, "combatSnapshot", {"runnerId": rid}, 60)
        bg = rpc(s, "boardGraph", {"runnerId": rid}, 90)
        # Transport ambiant : sans lui `_auto_ability_states` rend `no-transport` et le kit lu par
        # le port reste le kit GAMECONFIG. Avec `--no-bind`, c'est le regime d'AVANT le fix (b) --
        # la contre-epreuve du cablage, dans le meme probe.
        binder = (lambda: live_rpc(lambda m, ar=None, to=60: rpc(s, m, ar, to))) \
            if not a.no_bind else _null_binder
        with binder():
            state = load_state(dv, ob, snap, board=Board(bg["tiles"], adjacency="native_sym"))
        vis = {int(u["id"]): u.get("visualId") for u in (dv.get("units") or [])
               if u.get("id") is not None}

        uids = sorted({int(e["unitId"]) for e in entries if e.get("unitId") is not None})
        rows = []
        for uid in uids:
            try:
                leaf = runner_tile_leaf_ctx(state, uid, None)
            except Exception:                                             # noqa: BLE001
                leaf = None
            if leaf is None:
                continue
            kp = [int(x) for x in (leaf.get("unit_triggered_abilities") or ())]
            kn = [int(x) for x in (kits.get(uid) or ())]
            # Totaux NATIFS distincts de la face OWNER, par unite. C'est ce qui dit si une ability
            # SANS playbook cote port en a un cote NATIF : un kit reduit a UNE ability sans playbook
            # porte, dont le natif rend 0 partout, prouve que le natif la skippe LUI AUSSI
            # (`PlaybookDatabase$$LoadPlaybook` -> null -> `continue`) -- donc PAS de trou de portage.
            nats = sorted({round(float(e.get("total") or 0), 3) for e in entries
                           if e.get("unitId") == uid
                           and e.get("utility") == "TriggeredAbilitiesUtility"})
            rows.append({"unitId": uid, "visualId": vis.get(uid),
                         "kit_natif": kn, "kit_port": kp, "nat_owner": nats,
                         "sans_playbook": [x for x in kn if load_playbook(x) is None]})
        for r in rows:
            print("   u%-4s %-16s natif=%-28s port=%-16s sans_playbook=%-22s nat_owner=%s"
                  % (r["unitId"], r["visualId"], r["kit_natif"], r["kit_port"],
                     r["sans_playbook"], r["nat_owner"]))

        v = check_kit_gap(rows)
        print("E3 tranche [%s] %s" % (v["status"], v["message"]))

        # ---- E4 : LA VALEUR, sur les MEMES 102 events ---------------------------------------- #
        # C'est le seul etage qui ferme le residu : un kit exact + un registre complet ne valent
        # rien si la FORMULE portee diverge. On reutilise les deux fonctions de #456 telles quelles
        # (`_port_rows` reconstruit l'etat, `check_value` porte ses trois gardes contre l'accord
        # degenere) -- pas de variante locale qui pourrait diverger d'elles en silence.
        import probe_443r1a_triggered_move_anchor as P443
        prows = P443._port_rows(s, rid, entries, bind=not a.no_bind)
        v5 = P443.check_value(prows)
        print("E4 valeur  [%s] %s" % (v5["status"], v5["message"]))

        # ---- E5 : la PORTE D'ELEVATION a-t-elle ete EXERCEE ? --------------------------------- #
        # `TileQuery.<IterateAdjacentTiles>d__8$$MoveNext` applique un gate INCONDITIONNEL
        # `abs(delta elev) < 2`. Un accord obtenu sur un board PLAT ne dit RIEN de ce gate : il
        # n'aurait simplement jamais ete atteint. On COMPTE donc les couples (tuile candidate, ami
        # en ring-1 geometrique) que la porte a effectivement retires -- si le compte est 0, la
        # branche est NON CONFRONTEE, et on le DIT au lieu de laisser le vert le suggerer.
        import hexgeo
        elev = {(t["col"], t["row"]): t.get("elevation")
                for t in (bg.get("tiles") or []) if t.get("col") is not None}
        pos_by = {int(u["id"]): (u["pos"]["col"], u["pos"]["row"])
                  for u in (dv.get("units") or [])
                  if u.get("id") is not None and (u.get("pos") or {}).get("col") is not None}
        team_by = {int(u["id"]): u.get("team") for u in (dv.get("units") or [])
                   if u.get("id") is not None}
        porteurs = {r["unitId"] for r in rows if 1145 in (r.get("kit_natif") or ())}
        exerce = 0
        for e in entries:
            uid, t = e.get("unitId"), e.get("tile")
            if uid not in porteurs or e.get("utility") != "TriggeredAbilitiesUtility" or not t:
                continue
            tp = (int(t["col"]), int(t["row"]))
            for oid, op in pos_by.items():
                if oid == uid or team_by.get(oid) != team_by.get(int(uid)):
                    continue
                if hexgeo.distance(tp, op) != 1:
                    continue
                te, oe = elev.get(tp), elev.get(op)
                if te is not None and oe is not None and abs(int(te) - int(oe)) >= 2:
                    exerce += 1
        print("E5 elev    [%s] %d couple(s) (tuile candidate, ami ring-1) a |delta elev| >= 2 "
              "rencontres sur un porteur de 1145 -- la porte native les RETIRE%s"
              % ("exercee" if exerce else "NON CONFRONTEE", exerce,
                 "" if exerce else " ; sur ce board la branche n'est jamais atteinte"))

        # VERDICT. (b) est un fait de canal : un kit divergent rougit, sans appel. (a) n'est qu'une
        # SUSPICION tant que la valeur n'a pas parle -- et E4 la LEVE quand l'accord est total, car
        # une ability qui contribuerait cote natif et pas cote port produirait un ecart. Refuser de
        # lever la suspicion ferait rougir a jamais toute unite portant un passif sans playbook,
        # c.-a-d. presque toutes.
        if v["status"] in ("no-rows", "degenerate") or v5["status"] != "ok" or v["cause_b"]:
            print("\nVERDICT: NON FERME")
            return 8
        if v["cause_a"]:
            print("\nVERDICT: OK -- kit natif == kit port sur %d/%d unite(s), valeur en accord sur "
                  "%d/%d ligne(s). La suspicion (a) sur %s est LEVEE PAR LA VALEUR : une ability "
                  "qui contribuerait cote natif sans playbook cote port produirait un ecart."
                  % (len(rows), len(rows), len(prows), len(prows),
                     json.dumps(v["cause_a"], sort_keys=True)))
        else:
            print("\nVERDICT: OK -- kit natif == kit port, valeur en accord sur %d ligne(s)"
                  % len(prows))
        return 0
    finally:
        try:
            rpc(s, "triggeredMoveTraceOff", {"runnerId": rid}, 30, tolerate_unknown=True)
        except Exception:                                                 # noqa: BLE001
            pass
        if not a.keep:
            try:
                subprocess.run([sys.executable, "rl_duel.py", "dispose",
                                "--state-file", a.state_file], cwd=_HERE,
                               capture_output=True, text=True)
            except Exception:                                             # noqa: BLE001
                pass


if __name__ == "__main__":
    raise SystemExit(main())
