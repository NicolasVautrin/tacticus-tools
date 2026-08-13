"""#1033 -- CONFRONTATION LIVE de `1107 Reveal` : le GATE NATIF contre le port.

POURQUOI CE DISCRIMINANT-LA. Le seul porteur de 1107 est `eldarNpc2Warlock` (npc, hors pool), donc
on GREFFE l'ability sur une unite du pool (`case-92` §5bis) : le natif charge le playbook et
l'ability PAR ABILITY (`PlaybookDatabase.LoadPlaybook(abilityType)`), jamais par unite -- le code
exerce est donc bien celui de `RevealAbility`. La condition de greffe est verifiee : ni
`...RevealAbility$$ExecuteBehaviour` ni son `GetDynamicInvalidTargetReason` ne lisent une stat ou
un trait du CASTER (ils lisent son EQUIPE, via `IsFriend`, ce que la greffe preserve).

CE QU'ON MESURE, et pourquoi c'est le point le plus separant : `abilityTargets` demande AU JEU
quelles cibles il accepte pour l'ability. C'est donc
`IdunBattleLogic.Entities.Abilities.Active.Loki.RevealAbility$$GetDynamicInvalidTargetReason`
NATIF qu'on interroge, et on le confronte a
`engine.runner.abilities.loki.reveal.RevealAbility.get_dynamic_invalid_target_reason`.

DEUX REGIMES, et le second est ce qui donne sa valeur au premier :
  A. AUCUN Aeldari ami defait   -> le natif doit REFUSER toute cible.
  B. un Aeldari ami defait par X -> le natif doit ACCEPTER X (et lui seul parmi les ennemis).
Un accord obtenu dans le SEUL regime A ne prouverait rien : les deux cotes diraient « refuse »
pour des raisons possiblement differentes (regime degenere). Le regime B est le temoin NON NUL.

Usage (depuis `scripts/python`) :
    python probe_1033_reveal_live.py [--board MC1_67] [--state-file <absolu>]
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

import requests

PYDIR = Path(__file__).resolve().parent
#: Le host Node du depot (`frida/host`). Meme littéral que les autres probes (`probe_895`, ...).
HOST = os.environ.get("TACTICUS_HOST", "http://127.0.0.1:8765")

#: L'unite du pool qui recoit la greffe. AELDARI comme le porteur natif -- ce n'est pas requis par
#: le code (aucun gate ne lit la faction du CASTER) mais ca garde le scenario lisible.
GREFFE_SUR = "eldarAutarch"
#: La VICTIME : un Aeldari ami, dont la mort par un ennemi ouvre le gate.
VICTIME = "eldarRanger"
#: L'adversaire : deux unites, pour que « la cible qui a tue » se distingue de « une cible ».
ADVERSAIRES = "orksWarboss,orksNob"

REVEAL_ID = 1107


def _session() -> int:
    st = requests.get("%s/api/admin/status" % HOST, timeout=20).json()
    return int(st["session"]["id"])


def rpc(sid: int, method: str, body: dict, timeout: int = 90):
    r = requests.post("%s/api/scripts/%d/rpc" % (HOST, sid),
                      json={"method": method, "args": [body], "timeout": int(timeout * 1000)},
                      timeout=timeout + 5).json()
    return r.get("result", r)


def greffer(out: Path) -> Path:
    """`case-92` §5bis -- remplacer `ActiveAbilities` d'une unite DU POOL par `[1107]`, dans une
    COPIE du seed BC (jamais le seed partage : `data/` ne recoit AUCUNE sortie de run)."""
    import rl_duel as R
    bc = R._load_seed_bc(None)
    touche = 0
    for u in bc["Units"]:
        if u.get("Id") == GREFFE_SUR:
            u["ActiveAbilities"] = [REVEAL_ID]
            touche += 1
    if not touche:
        raise SystemExit("[1033] %s absent du seed BC -- greffe impossible" % GREFFE_SUR)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(bc), encoding="utf-8")
    print("[1033] greffe : %s.ActiveAbilities = [%d] (%d entree(s)) -> %s"
          % (GREFFE_SUR, REVEAL_ID, touche, out.name))
    return out


def build(state_path: Path, args: list) -> int:
    state_path.parent.mkdir(parents=True, exist_ok=True)
    if state_path.exists():
        state_path.unlink()
    p = subprocess.run([sys.executable, "rl_duel.py", "build", "--state-file", str(state_path)]
                       + args, cwd=str(PYDIR), capture_output=True, text=True,
                       encoding="utf-8", errors="replace")
    if not state_path.exists() or p.returncode != 0:
        print((p.stderr or p.stdout or "")[-2500:])
        raise SystemExit("[1033] build KO (rc=%s)" % p.returncode)
    return int(json.loads(state_path.read_text())["runnerId"])


def charger(sid: int, rid: int):
    """L'etat OFFLINE reconstruit depuis les memes canaux que le runner -- c'est lui que le port
    interroge, de sorte que la comparaison porte sur la REGLE, pas sur deux substrats differents."""
    from engine.entities.pathfinding.board import Board
    from engine.runner.snapshot import load_state
    bg = rpc(sid, "boardGraph", {"runnerId": rid}, 60)
    board = Board(bg["tiles"], adjacency="evenq")
    dec = rpc(sid, "decisionView", {"runnerId": rid, "maxRank": 1, "allAbilities": True}, 90)
    ob = rpc(sid, "observeBattle", {"runnerId": rid}, 40)
    snap = rpc(sid, "combatSnapshot", {"runnerId": rid}, 60)
    tiles = rpc(sid, "tileMeta", {"runnerId": rid}, 60)
    return load_state(dec, ob, snap, board=board, tiles=tiles), dec, ob


def temoin(sid: int, rid: int, caster_uid: int, autre_ability: int):
    """CONTROLE-TEMOIN, sans lequel un `fromHere = []` sur 1107 ne prouve RIEN : si l'etat courant
    n'autorise AUCUN cast (ce n'est pas le tour du caster, il a deja agi, il est mort...), toutes
    les abilities rendent zero et le verdict est vide -- « accord en regime DEGENERE = zero preuve ».
    On interroge donc une AUTRE ability du meme caster dans le MEME etat."""
    at = rpc(sid, "abilityTargets",
             {"runnerId": rid, "unitId": int(caster_uid), "abilityType": int(autre_ability)}, 90) or {}
    row = next((u for u in (at.get("units") or []) if u.get("unitId") == int(caster_uid)), None)
    ab = next((x for x in ((row or {}).get("abilities") or [])
               if int(x.get("abilityId", -1)) == int(autre_ability)), {})
    return len(ab.get("fromHere") or []), len(ab.get("targets") or [])


def cibles_natives(sid: int, rid: int, caster_uid: int):
    """Les cibles que LE JEU accepte pour 1107 depuis la position COURANTE du caster.

    `fromHere` et pas `targets` : c'est la liste SUR PLACE, donc celle que le gate dynamique a
    filtree pour la position reelle -- meme lecture que `probe_895`."""
    at = rpc(sid, "abilityTargets",
             {"runnerId": rid, "unitId": int(caster_uid), "abilityType": REVEAL_ID}, 90) or {}
    row = next((u for u in (at.get("units") or []) if u.get("unitId") == int(caster_uid)), None)
    ab = next((x for x in ((row or {}).get("abilities") or [])
               if int(x.get("abilityId", -1)) == REVEAL_ID), {})
    return {int(t["targetId"]) for t in (ab.get("fromHere") or []) if t.get("targetId") is not None}, at


def cibles_portees(state, caster_uid: int, ennemis) -> set:
    from engine.runner.abilities.loki.reveal import RevealAbility
    ab = RevealAbility()
    return {int(e) for e in ennemis
            if ab.get_dynamic_invalid_target_reason(state, int(caster_uid), int(e)) == 0}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--board", default="C1_74")
    ap.add_argument("--state-file", default=str(PYDIR.parent.parent / "logs" / "probe_1033.json"))
    ap.add_argument("--max-tours", type=int, default=14)
    a = ap.parse_args()

    sid = _session()
    print("[1033] session %d ; board %s" % (sid, a.board))
    bc = greffer(PYDIR.parent.parent / "logs" / "probe_1033_seed_greffe.json")
    state_path = Path(a.state_file)
    # La VICTIME est rendue mortelle en UN coup : c'est ce qui rend le regime B ATTEIGNABLE en
    # quelques tours d'IA au lieu d'etre laisse au hasard. On ne touche qu'a ses PV -- le gate
    # mesure ne lit ni PV ni armure.
    # GEOMETRIE PILOTEE, jamais subie (`feedback_drive_positions_dont_blame_geometry`) : aux
    # SpawnPoints du board, le caster nait en (1,0) et les orks en rangee 5-8 -- le natif rendait
    # alors `fromHere = []` pour une raison de PORTEE, pas de gate, et le regime B etait
    # ininterpretable. On place donc le tueur ADJACENT a la victime ET a 2 hexes du caster
    # (`constants.range` = 2), c.-a-d. la configuration ou le gate dynamique est SEUL a decider.
    rid = build(state_path, ["--seed-bc", str(bc), "--board", a.board,
                             "--p-units", "%s,%s" % (GREFFE_SUR, VICTIME),
                             "--a-units", ADVERSAIRES,
                             "--place", "%s:3,2" % GREFFE_SUR,
                             "--place", "%s:3,3" % VICTIME,
                             "--a-place", "%s:3,4" % ADVERSAIRES.split(",")[0],
                             "--a-place", "%s:4,4" % ADVERSAIRES.split(",")[1],
                             "--unit-stat", "%s:Health=1,RemainingHealth=1" % VICTIME])
    print("[1033] runner %d" % rid)
    rc = 0
    try:
        st, dec, ob = charger(sid, rid)
        par_vid = {}
        for u in (dec.get("units") or []):
            par_vid.setdefault(u.get("visualId"), []).append(int(u["id"]))
        caster = par_vid.get(GREFFE_SUR, [None])[0]
        victime = par_vid.get(VICTIME, [None])[0]
        if caster is None:
            raise SystemExit("[1033] le caster greffe n'est pas en bataille")
        # L'ability est-elle REELLEMENT montee ? La greffe echoue en SILENCE si non -- et un
        # `abilityTargets` VIDE se lirait alors comme « le gate refuse », ce qui serait FAUX.
        row = next((u for u in (dec.get("units") or []) if int(u["id"]) == caster), {})
        brut_ab = row.get("abilities") or []
        if brut_ab and isinstance(brut_ab[0], dict):
            print("[1033] cles d'une entree `abilities` : %s" % sorted(brut_ab[0]))
        montees = sorted({int(x.get("abilityId", x.get("type", x.get("id", -1))))
                          if isinstance(x, dict) else int(x) for x in brut_ab})
        print("[1033] caster=%s victime=%s ; abilities montees=%s ; 1107 monte=%s"
              % (caster, victime, montees, REVEAL_ID in montees))
        if REVEAL_ID not in montees:
            raise SystemExit("[1033] la greffe n'a PAS monte 1107 -- toute lecture du gate serait "
                             "un faux refus. Regime NON CONFRONTE.")

        equipes = {int(u["id"]): u.get("team") for u in (dec.get("units") or [])}
        mon_team = equipes.get(caster)
        ennemis = [uid for uid, t in equipes.items() if t != mon_team]

        # ---- REGIME A : aucun Aeldari ami defait -----------------------------------------
        autre = next((x for x in montees if x != REVEAL_ID), None)
        t_a = temoin(sid, rid, caster, autre) if autre is not None else (0, 0)
        print("[1033] TEMOIN ability %s (fromHere, targets) = %s" % (autre, t_a))
        nat_a, brut = cibles_natives(sid, rid, caster)
        port_a = cibles_portees(st, caster, ennemis)
        print("[1033] REGIME A (aucun mort)  natif=%s  port=%s" % (sorted(nat_a), sorted(port_a)))
        if nat_a or port_a:
            print("[1033]   brut abilityTargets = %s" % json.dumps(brut)[:400])
        # ⚠ L'ACCORD NE COMPTE QUE SI LE TEMOIN EST NON NUL. Mesure du 2026-08-13 : au tour 0 le
        # temoin vaut (0, 0) -- le natif n'autorise AUCUN cast dans cet etat --, donc le
        # `natif=[] port=[]` du regime A etait un FAUX VERT. Il est desormais rendu NON CONCLUANT.
        ok_a = (not nat_a) and (not port_a) and t_a != (0, 0)
        if t_a == (0, 0):
            print("[1033] REGIME A NON CONCLUANT : temoin NUL (aucun cast possible dans cet etat) "
                  "-- l'accord des deux zeros ne prouve rien.")

        # ---- on FAIT MOURIR la victime : l'IA adverse joue jusqu'a ce qu'elle tombe -------
        mort_par = None
        for tour in range(a.max_tours):
            p = subprocess.run([sys.executable, "rl_duel.py", "aiturn",
                                "--state-file", str(state_path)],
                               cwd=str(PYDIR), capture_output=True, text=True,
                               encoding="utf-8", errors="replace")
            st, dec, ob = charger(sid, rid)
            # `observeBattle.units[].squadId` est l'id d'unite (meme lecteur que `probe_895.hp_live`) ;
            # `isDead` y est la source d'autorite sur la mort (`decisionView` GARDE les morts).
            morts = {int(u["squadId"]) for u in (ob.get("units") or []) if u.get("isDead")}
            vivants = {int(u["squadId"]): u.get("hp") for u in (ob.get("units") or [])}
            print("[1033]   tour %d : aiturn rc=%s ; hp=%s ; morts=%s"
                  % (tour, p.returncode, vivants, sorted(morts)))
            if victime in morts:
                from engine.runner.components import UnitComponent
                uc = st.get_entity(victime)
                ds = uc.get_component(UnitComponent).death_source if uc is not None else None
                mort_par = None if ds is None else ds[0]
                # LE CANAL LIVE : `decisionView.units[].killerId` (`DamageSource$$get_KillerId`,
                # cf. `entities/effects_state.py`). C'est ce que le SUBSTRAT publie ; `death_source`
                # est ce que le PORT en a fait.
                ligne = next((u for u in (dec.get("units") or [])
                              if int(u["id"]) == victime), {})
                killer_live = ligne.get("killerId")
                print("[1033] tour %d : %s est MORTE ; port.death_source=%s ; "
                      "decisionView.killerId=%s" % (tour, VICTIME, ds, killer_live))
                if mort_par is None and killer_live is not None:
                    print("[1033] SEEDING : le canal PUBLIE le tueur, le port ne le porte pas dans "
                          "`UnitComponent.death_source` -- residu `#1033-r3`. Le gate porte est donc "
                          "STRUCTURELLEMENT aveugle aux morts survenues AVANT/HORS du runner Python.")
                    mort_par = int(killer_live)
                break
        if mort_par is None:
            print("[1033] REGIME B NON ATTEINT -- la victime n'est pas morte en %d tours, ou son "
                  "tueur n'est pas imputable ni publie. L'accord du regime A seul ne prouve RIEN "
                  "(regime degenere)." % a.max_tours)
            return 2 if ok_a else 1

        # ---- REGIME B : un Aeldari ami defait --------------------------------------------
        equipes = {int(u["id"]): u.get("team") for u in (dec.get("units") or [])}
        ennemis = [uid for uid, t in equipes.items() if t != mon_team]
        if autre is not None:
            t = temoin(sid, rid, caster, autre)
            print("[1033] TEMOIN ability %d (fromHere, targets) = %s" % (autre, t))
            if t == (0, 0):
                print("[1033] TEMOIN NUL -- dans cet etat le natif n'autorise AUCUN cast (ce n'est "
                      "pas le tour du caster, ou il a deja agi). Un `fromHere = []` sur 1107 n'y "
                      "prouve donc RIEN : regime NON CONCLUANT, pas un accord.")
        nat_b, brut_b = cibles_natives(sid, rid, caster)
        port_b = cibles_portees(st, caster, ennemis)
        print("[1033] REGIME B (tueur=%s)   natif=%s  port=%s"
              % (mort_par, sorted(nat_b), sorted(port_b)))
        ok_b = (nat_b == port_b) and bool(nat_b)
        if not ok_b:
            print("[1033]   brut abilityTargets = %s" % json.dumps(brut_b)[:600])
        print()
        print("[1033] A (refus des deux cotes, temoin non nul) : %s"
              % ("OK" if ok_a else "NON CONCLUANT"))
        print("[1033] B (le natif ACCEPTE une cible, natif == port) : %s"
              % ("OK" if ok_b else "NON ATTEINT"))
        if not nat_b:
            print("[1033] ETAT DU CAS : le natif REFUSE encore, dans un etat ou le cast est "
                  "possible (temoin non nul). Les deux cotes rendent [] mais pour des raisons "
                  "possiblement DIFFERENTES -- le port par manque de seeding (`#1033-r3`), le natif "
                  "pour une raison NON ETABLIE. Ce n'est PAS un accord : c'est un regime NON "
                  "CONFRONTE, et le prochain etage a lire est `UnitExtensions$$IsFriend` sur une "
                  "unite MORTE (`GetCurrentPlayer` peut y rendre null) -- residu `#1033-r4`.")
        rc = 0 if (ok_a and ok_b) else 1
    finally:
        try:
            rpc(sid, "disposeRunner", {"runnerId": rid}, 30)
            print("[1033] runner %d dispose" % rid)
        except Exception as e:                                  # noqa: BLE001
            print("[1033] dispose KO : %s" % e)
    return rc


if __name__ == "__main__":
    sys.exit(main())
