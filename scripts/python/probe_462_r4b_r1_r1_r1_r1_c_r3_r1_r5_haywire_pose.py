"""#462-r4b-r1-r1-r1-r1-c-r3-r1-r5 -- la POSE de la mine Haywire (`HaywireMineAbility` 1531).

MESURE, pas garde. Deux etapes :

  --step live   : monte un runner (`astarCyrus` injecte au catalogue, board au choix, `--no-ai`) et
                  observe QUAND et OU le NATIF pose ses mines. C'est ce qui tranche l'ordre
                  `On(0x28 = UnitFinishedTurn)` (le ClearPersistentData du `HaywireMine_Reset`)
                  vs `On(0x29 = UnitFinishedTurnNormally)` (la 2e branche du trigger de pose) --
                  que le decompile donne dans CET ordre
                  (`IdunBattle.Operations.FinishUnitTurnOperation$$Execute` publie `0x28` PUIS
                  `0x29`), mais dont la consequence observable doit etre CONSTATEE.
  --step port   : rejoue les MEMES gestes sur le port (etat charge depuis la capture live) et
                  confronte tuile a tuile.

Sortie ASCII (console cp1252).
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import uuid
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import hexgeo                                                          # noqa: E402

SUMMONER = "astarCyrus"                 # HERO `lineup` HORS seed BC -> catalog_inject
MINE_FRAGMENT = "HaywireMine"           # visualId du summon (`astarSmnHaywireMine` / npc)
DEFAULT_BOARD = "MC1_67"


# --------------------------------------------------------------------------- transport live

def _host():
    import rl_collect_batch as R
    return R


def _unwrap(r):
    return r.get("result") if isinstance(r, dict) and "result" in r else r


def _mk_rpc(R, sid):
    def _call(method, body=None, timeout=60):
        return _unwrap(R._rpc(sid, method, [body] if body is not None else [], timeout=timeout))
    return _call


def _build(board: str, seed: str, extra_units: str, extra: list | None = None) -> tuple:
    """`rl_duel build` avec `astarCyrus` injecte. Rend `(rid, state_path)`."""
    import subprocess
    import catalog_inject
    pyd = Path(__file__).resolve().parent
    tmp = Path(os.environ.get("TEMP") or os.environ.get("TMP") or ".")
    tag = uuid.uuid4().hex[:8]
    bc = tmp / ("haywire-pose-bc-%s.json" % tag)
    state = tmp / ("haywire-pose-state-%s.json" % tag)
    catalog_inject.write_augmented_seed_bc(str(bc), [SUMMONER])
    argv = [sys.executable, "rl_duel.py", "build", "--seed", seed,
            "--state-file", str(state), "--seed-bc", str(bc), "--board", board,
            "--rank", "17", "--no-ai",
            "--p-units", "%s,%s" % (SUMMONER, extra_units.split(",")[0]),
            "--a-units", ",".join(extra_units.split(",")[1:]), *(extra or [])]
    p = subprocess.run(argv, cwd=str(pyd), capture_output=True, text=True,
                       encoding="utf-8", errors="replace")
    if not state.exists():
        raise SystemExit("build KO: %s" % ((p.stderr or p.stdout or "")[-500:]))
    return json.loads(state.read_text())["runnerId"], state


# --------------------------------------------------------------------------- lecture d'etat

def _vue(rpc, rid):
    """`decisionView` -- LE canal de vivacite d'une mine (`observeBattle.isDead` la declare morte
    des la pose : une mine a 0 PV par construction, cf. la fiche de `-r3`)."""
    return rpc("decisionView", {"runnerId": rid, "maxRank": 1, "allAbilities": True}, 120)


def _units(dv):
    return [u for u in ((dv or {}).get("units") or []) if u.get("alive")]


def _uid(u):
    return u.get("id", u.get("squadId", u.get("entityId")))


def _pos(u):
    p = u.get("pos") or {}
    return (p.get("col"), p.get("row"))


def _by_vis(dv, vis):
    for u in _units(dv):
        if (u.get("visualId") or "") == vis:
            return u
    return None


def _mines(dv):
    return {_pos(u): _uid(u) for u in _units(dv)
            if MINE_FRAGMENT in (u.get("visualId") or "")}


def _movable(rpc, rid, unit_id):
    mov = rpc("aiMovableTiles", {"runnerId": rid}, 60) or {}
    for mu in (mov.get("units") or []):
        if mu.get("unitId") == unit_id:
            return {(t.get("col"), t.get("row")) for t in (mu.get("tiles") or [])
                    if t.get("col") is not None}
    return set()


def _act(rpc, rid, action, timeout=120):
    return rpc("applyAction", {"runnerId": rid, "action": action}, timeout)


def _persist(rpc, rid, unit_id):
    """Le `PersistentDataComponent` NATIF de l'unite, lu par introspection
    (`dumpEntityComponents`) -- c'est LUI qui tranche si `HaywireMine_ResetAbility`
    (`On(0x28 = UnitFinishedTurn)` -> `ClearPersistentData`) a mordu AVANT que la 2e branche du
    trigger de pose (`On(0x29)` -> `AmountIsZero(GetPersistentData(...))`) ne soit evaluee."""
    d = rpc("dumpEntityComponents", {"runnerId": rid, "entityId": int(unit_id),
                                     "withFields": True}, 60) or {}
    out = []
    for c in (d.get("components") or []):
        nom = c.get("name") or c.get("type") or ""
        if "Persistent" in nom:
            out.append({"name": nom, "fields": c.get("fields")})
    if out:
        return out
    noms = [(c.get("cls") or c.get("name")) for c in (d.get("components") or [])]
    return [{"aucun_persistent": True, "composants": noms or sorted(d.keys())}]


def _events(res) -> list:
    """Les evenements NATIFS d'un `applyAction`, aplatis en `(nom, tags)`.

    C'est LE canal qui tranche << l'ability a-t-elle fire ? >> independamment de l'existence d'une
    mine : une triggered-ability qui s'execute emet un `Ability_Power` porteur de son nom, MEME si
    son behaviour se termine sur un `TriggerAbilityDelayed` (aucune unite creee)."""
    out = []
    for act in ((res or {}).get("actions") or []):
        for e in (act.get("events") or []):
            td = e.get("tags")
            if isinstance(td, str):
                try:
                    td = json.loads(td)
                except Exception:
                    td = {"raw": td}
            out.append((e.get("name") or e.get("type") or e.get("event")
                        or e.get("kind") or e.get("id"), td or {}))
    return out


def _noms_events(res) -> list:
    """Signature COMPACTE d'une cascade : `name` seul ne porte que le genre de noeud de flux
    (`group`/`action`/`finish`) -- ce qui NOMME l'evenement vit dans ses `tags`."""
    out = []
    for nom, tags in _events(res):
        cle = None
        for k in ("Ability_Power", "AbilityId", "UnitStats_TriggeredAbility_Id", "AddUnit",
                  "Unit_IsSummoned", "Amount", "DamageProfileType"):
            if k in tags:
                cle = "%s=%s" % (k, tags[k])
                break
        if cle is None and tags:
            cle = "+".join(sorted(tags)[:4])
        out.append("%s[%s]" % (nom, cle or ""))
    return out


# --------------------------------------------------------------------------- etape LIVE

def step_live(board: str, seed: str, units: str) -> int:
    R = _host()
    sid = R._resolve_session()
    rpc = _mk_rpc(R, sid)
    rid, state = _build(board, seed, units)
    print("runner=%d board=%s seed=%s" % (rid, board, seed))
    try:
        dv = _vue(rpc, rid)
        cyrus = _by_vis(dv, SUMMONER)
        if cyrus is None:
            print("KO: %s absent du plateau" % SUMMONER)
            return 2
        cid = _uid(cyrus)
        print("cyrus=%s pos=%s mines_initiales=%d" % (cid, _pos(cyrus), len(_mines(dv))))

        # --- CAS A : Cyrus BOUGE d'un hex -----------------------------------------------
        avant = _pos(cyrus)
        reach = {t for t in _movable(rpc, rid, cid) if hexgeo.distance(t, avant) == 1}
        if not reach:
            print("KO: aucun pas legal pour cyrus")
            return 2
        dest = sorted(reach)[0]
        r = _act(rpc, rid, {"kind": "move", "unitId": cid,
                            "to": {"col": dest[0], "row": dest[1]}})
        dv = _vue(rpc, rid)
        m_apres_move = _mines(dv)
        print("A. move %s -> %s | mines=%d %s" %
              (avant, dest, len(m_apres_move), sorted(m_apres_move)))
        print("   PreviousTile attendue = %s ; presente = %s" %
              (avant, avant in m_apres_move))
        print("   events(move)   = %s" % _noms_events(r))

        # --- CAS B : Cyrus TERMINE son activation ---------------------------------------
        r = _act(rpc, rid, {"kind": "finish", "unitId": cid})
        dv = _vue(rpc, rid)
        m_apres_finish = _mines(dv)
        neuves = sorted(set(m_apres_finish) - set(m_apres_move))
        print("B. finish | mines=%d (neuves=%s)" % (len(m_apres_finish), neuves))
        print("   events(finish) = %s" % _noms_events(r))
        print("   composants(cyrus) = %s" % json.dumps(_persist(rpc, rid, cid))[:600])

        # --- CAS C..N : plusieurs tours, avec et sans deplacement -------------------------
        for tour in range(2, 6):
            _act(rpc, rid, {"kind": "endturn"}, 90)
            _act(rpc, rid, {"kind": "endturn"}, 90)
            dv = _vue(rpc, rid)
            m_avant = _mines(dv)
            cyrus = _by_vis(dv, SUMMONER)
            if cyrus is None:
                print("T%d. cyrus mort/absent -- arret" % tour)
                break
            pos_c = _pos(cyrus)
            bouge = (tour % 2 == 1)     # tours 3 et 5 : Cyrus BOUGE ; 2 et 4 : il ne bouge pas
            dest2 = None
            if bouge:
                r2 = {t for t in _movable(rpc, rid, cid) if hexgeo.distance(t, pos_c) == 1}
                r2 -= set(m_avant)      # ne pas ecraser une mine (le move traverse la tuile)
                if r2:
                    dest2 = sorted(r2)[0]
                    _act(rpc, rid, {"kind": "move", "unitId": cid,
                                    "to": {"col": dest2[0], "row": dest2[1]}})
            dv = _vue(rpc, rid)
            m_mid = _mines(dv)
            rf = _act(rpc, rid, {"kind": "finish", "unitId": cid})
            dv = _vue(rpc, rid)
            m_fin = _mines(dv)
            print("T%d. pos=%s move=%s | apres_move=+%s | apres_finish=+%s | ev(finish)=%s"
                  % (tour, pos_c, dest2,
                     sorted(set(m_mid) - set(m_avant)), sorted(set(m_fin) - set(m_mid)),
                     _noms_events(rf)))
        return 0
    finally:
        rpc("disposeRunner", {"runnerId": rid}, 20)
        try:
            state.unlink(missing_ok=True)
        except Exception:
            pass


def step_discriminant(board: str, seed: str, units: str) -> int:
    """LE BRAS QUI DISCRIMINE l'ordre `On(0x28)` / `On(0x29)`.

    Le bras `B` de `--step live` (finir un tour ou Cyrus a bouge) ne tranche PAS : la tuile
    precedente porte deja la mine, donc `CanAddUnit(PreviousTile) == []` et la 2e branche du
    trigger finirait de toute facon sur `TriggerAbilityDelayed` -- AUCUNE mine visible, que le
    `ClearPersistentData` ait mordu ou non.

    Ici on LIBERE la tuile precedente (l'allie marche sur la mine -> crush `Steppable`) AVANT de
    finir le tour de Cyrus :
      * si le `Clear` d'`On(0x28)` precede la lecture d'`On(0x29)` -> `AmountIsZero` VRAI -> une
        mine NEUVE apparait sur la tuile liberee ;
      * si la donnee persistante SURVIT a `On(0x28)` -> aucune mine neuve.
    """
    R = _host()
    sid = R._resolve_session()
    rpc = _mk_rpc(R, sid)
    allie_vis, ennemi_vis = units.split(",")[0], units.split(",")[1]
    rid, state = _build(board, seed, units, extra=[
        # PORTEE : l'ecraseur doit ATTEINDRE la tuile minee depuis son spawn.
        "--unit-stat", "%s:Movement=25" % ennemi_vis,
        # PV BAS : l'ecraseur est un ENNEMI, donc la mine lui EXPLOSE dessus. En le faisant
        # MOURIR sur place, `RemoveUnitFromTiles` retire les DEUX -- c'est le seul montage qui
        # LIBERE vraiment `PreviousTile` avant la fin d'activation de Cyrus (une traversee, elle,
        # se fait contourner par le pathfinder : mesure du 2026-08-05, allie (0,0)->(2,0), mine
        # intacte).
        "--hp-target", "300"])
    print("runner=%d board=%s seed=%s  [BRAS DISCRIMINANT]" % (rid, board, seed))
    try:
        dv = _vue(rpc, rid)
        cyrus = _by_vis(dv, SUMMONER)
        allie = _by_vis(dv, ennemi_vis)
        if cyrus is None or allie is None:
            print("KO: montage incomplet (cyrus=%s ecraseur=%s)" % (cyrus, allie))
            return 2
        cid, aid = _uid(cyrus), _uid(allie)
        avant = _pos(cyrus)
        reach = {t for t in _movable(rpc, rid, cid) if hexgeo.distance(t, avant) == 1}
        if not reach:
            print("KO: aucun pas legal pour cyrus")
            return 2
        dest = sorted(reach)[0]
        _act(rpc, rid, {"kind": "move", "unitId": cid, "to": {"col": dest[0], "row": dest[1]}})
        m1 = _mines(_vue(rpc, rid))
        print("1. cyrus %s -> %s ; mines=%s" % (avant, dest, sorted(m1)))
        if avant not in m1:
            print("KO: pas de mine sur la tuile precedente -- montage invalide")
            return 2

        # L'ENNEMI marche SUR la mine : elle l'ecrase (crush `Steppable`) ET lui explose dessus
        # (gate `AreEnemies`). A PV bas il MEURT -> `RemoveUnitFromTiles` retire les deux, la
        # tuile est LIBRE. `applyAction` ne verifie pas la propriete du `unitId` (runner.md §4).
        apos = _pos(allie)
        _act(rpc, rid, {"kind": "move", "unitId": aid, "to": {"col": avant[0], "row": avant[1]}})
        dv = _vue(rpc, rid)
        m3 = _mines(dv)
        a2 = _by_vis(dv, ennemi_vis)
        print("2. ecraseur %s -> %s ; mines=%s ; ecraseur=%s"
              % (apos, avant, sorted(m3), _pos(a2) if a2 else "MORT"))
        if avant in m3:
            print("KO: la mine n'a pas ete ecrasee -- bras NON arme, rien n'est conclu")
            return 3
        occup = {_pos(u) for u in _units(_vue(rpc, rid))}
        if avant in occup:
            print("KO: la tuile %s reste OCCUPEE -- bras NON arme, rien n'est conclu" % (avant,))
            return 3

        r = _act(rpc, rid, {"kind": "finish", "unitId": cid})
        m4 = _mines(_vue(rpc, rid))
        neuves = sorted(set(m4) - set(m3))
        print("3. finish(cyrus) | mines %d -> %d ; neuves=%s" % (len(m3), len(m4), neuves))
        print("   events(finish) = %s" % _noms_events(r))
        print("VERDICT: %s" % (
            "On(0x29) FIRE apres le Clear d'On(0x28) -- mine reposee sur PreviousTile"
            if avant in neuves else
            "AUCUNE pose : soit la donnee survit a On(0x28), soit le selecteur reste vide"))
        return 0
    finally:
        rpc("disposeRunner", {"runnerId": rid}, 20)
        try:
            state.unlink(missing_ok=True)
        except Exception:
            pass


def main(argv) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--step", default="live", choices=["live", "discriminant"])
    ap.add_argument("--board", default=DEFAULT_BOARD)
    ap.add_argument("--seed", default="777")
    ap.add_argument("--units", default="ultraTitus,orksNob",
                    help="allie,ennemi[,ennemi2] (roster minimal autour de Cyrus)")
    a = ap.parse_args(argv)
    if a.step == "discriminant":
        # Le bras discriminant TUE son ecraseur : il faut un SECOND ennemi, sinon la bataille se
        # termine et `applyAction` refuse la suite (stage != 1) -- mesure du 2026-08-05, le
        # `finish` rendait une cascade VIDE et le verdict etait donc sans objet.
        u = a.units if len(a.units.split(",")) >= 3 else (a.units + ",necroWarden")
        return step_discriminant(a.board, a.seed, u)
    return step_live(a.board, a.seed, a.units)


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
