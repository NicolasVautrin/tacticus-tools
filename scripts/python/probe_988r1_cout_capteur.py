"""`#988-r1` -- le COUT du capteur `playbookUtilityTrace`, MESURE et non plus derive.

    python probe_988r1_cout_capteur.py [--state-file <absolu>] [--repet 3]

L'en-tete du capteur portait une borne DERIVEE de la structure du generateur d'actions
(« dizaines a quelques centaines d'appels par tour »). Une borne derivee qui reste ecrite apres
qu'on a pu l'observer devient une citation perimee. Ce probe l'OBSERVE.

DEUX AXES, INDEPENDANTS -- et il faut dire lequel mord :

  * LATENCE. Le mode de defaillance documente (27 000 appels/s -> frame > 960 ms -> le detecteur
    de freeze d'Unity tue le process) est un regime de LATENCE, ancre sur un getter appele par les
    serialisations Newtonsoft. Ce n'est PAS notre point d'ancrage, donc il ne nous donne pas notre
    borne -- il donne l'ordre de grandeur ou ca casse. On mesure donc la duree d'un tour d'IA
    complet, capteur DESARME puis ARME, sur le MEME montage.

  * VOLUME de trace. L'anneau est borne (`RING_MAX`), donc le volume ne peut pas faire enfler la
    memoire ; ce qu'il peut faire, c'est ECRASER la mesure (`diag.dropped` > 0 = des appels sont
    sortis de l'anneau). C'est une perte d'information, pas un risque pour le jeu.

TROIS REGIMES d'armement, parce que le filtre du capteur est le CHOIX DES ADRESSES :
  1. desarme                      -- la reference ;
  2. arme sur UN playbook         -- l'usage normal ;
  3. arme sur TOUS (`all:true`)   -- les 163 ancres, le pire cas.
Si le regime 3 mord et pas le 2, c'est que le filtrage par adresse est ce qui rend le capteur
utilisable, et il faut l'ecrire.

⚠ Ce probe ne conclut RIEN d'un ecart de duree non reproductible : il repete chaque regime et rend
le MEDIAN, plus le min/max. Un tour d'IA n'est pas deterministe en temps.
"""
from __future__ import annotations

import argparse
import json
import statistics
import subprocess
import sys
import time
from pathlib import Path

PYDIR = Path(__file__).resolve().parent
sys.path.insert(0, str(PYDIR))
ROOT = PYDIR.parents[1]

#: Meme montage que `probe_988_ancres_utilite_playbook.py` -- positions FORCEES, donc le regime ou
#: le natif retient effectivement l'ability et ou les playbooks tournent pour de vrai.
FIXTURE = {
    "seed": 777, "board": "MC1_67", "rank": 5,
    "p_units": "worldJakhal,worldEightbound,genesPatriarch,templSwordBrother",
    "a_units": "necroWarden,necroDestroyer,tauCrisis,ultraTitus",
    "place": ["worldJakhal:3,4", "worldEightbound:2,5", "genesPatriarch:1,4",
              "templSwordBrother:4,3"],
    "a_place": ["necroWarden:3,5", "necroDestroyer:4,4", "tauCrisis:2,4", "ultraTitus:5,4"],
}

#: Le playbook du regime normal : celui de `1043 ThunderousAssault`.
UN_PLAYBOOK = ["ThunderousAssaultPlaybook"]


def _rpc_mod():
    from rl_collect_batch import _resolve_session, _rpc          # noqa: E402
    return _resolve_session, _rpc


def _r(rpc, sid, m, b, t=120):
    return (rpc(sid, m, [b], timeout=t).get("result") or {})


def _build(state_file: Path) -> int:
    state_file.parent.mkdir(parents=True, exist_ok=True)
    state_file.unlink(missing_ok=True)
    cmd = [sys.executable, "rl_duel.py", "build", "--seed", str(FIXTURE["seed"]),
           "--board", FIXTURE["board"], "--rank", str(FIXTURE["rank"]),
           "--state-file", str(state_file), "--no-ai",
           "--p-units", FIXTURE["p_units"], "--a-units", FIXTURE["a_units"]]
    for p in FIXTURE["place"]:
        cmd += ["--place", p]
    for p in FIXTURE["a_place"]:
        cmd += ["--a-place", p]
    proc = subprocess.run(cmd, cwd=str(PYDIR), capture_output=True, text=True,
                          encoding="utf-8", errors="replace")
    if not state_file.exists():
        raise RuntimeError("build KO : %s" % ((proc.stderr or proc.stdout or "")[-900:]))
    return int(json.loads(state_file.read_text(encoding="utf-8"))["runnerId"])


def _tour_ia(rpc, sid, rid: int) -> float:
    """Un tour d'IA complet, chronometre COTE APPELANT (donc RPC compris). C'est la duree que le
    joueur subirait : on ne cherche pas a isoler le temps natif, on cherche a savoir si le capteur
    rend le tour perceptiblement plus lent."""
    t0 = time.perf_counter()
    _r(rpc, sid, "aiDryRunAllUnits", {"runnerId": rid}, 300)
    return time.perf_counter() - t0


def _mesure(rpc, sid, rid: int, repet: int) -> dict:
    ds = [_tour_ia(rpc, sid, rid) for _ in range(repet)]
    return {"median_s": round(statistics.median(ds), 3),
            "min_s": round(min(ds), 3), "max_s": round(max(ds), 3),
            "n": len(ds)}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--state-file", default=str(ROOT / "logs" / "probe_988r1_cout.json"))
    ap.add_argument("--repet", type=int, default=3)
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args()

    try:
        resolve_session, rpc = _rpc_mod()
        sid = resolve_session()
    except Exception as e:                                          # noqa: BLE001
        print("[988-r1] NON CONFRONTE -- plateforme indisponible : %s" % e)
        return 0

    # Etat de depart PROPRE : si un armement traine d'un run precedent, la reference serait faussee.
    _r(rpc, sid, "playbookUtilityTrace", {"action": "disarm"}, 60)

    inventaire = _r(rpc, sid, "playbookUtilityTrace", {"action": "list"}, 240)
    if not inventaire.get("ok"):
        print("[988-r1] NON CONFRONTE -- capteur absent du bundle injecte "
              "(RPC `playbookUtilityTrace` indisponible)")
        return 0

    res = {"playbookCount": inventaire.get("playbookCount"),
           "anchorCount": inventaire.get("anchorCount")}
    print("[988-r1] capteur present : %s playbook(s), %s ancre(s)"
          % (res["playbookCount"], res["anchorCount"]))

    rid = _build(Path(a.state_file))
    try:
        # --- regime 1 : DESARME (la reference) ---
        res["desarme"] = _mesure(rpc, sid, rid, a.repet)

        # --- regime 2 : UN playbook ---
        arm1 = _r(rpc, sid, "playbookUtilityTrace",
                  {"action": "arm", "playbooks": UN_PLAYBOOK}, 240)
        res["arm_un"] = {"ok": arm1.get("ok"), "anchors": arm1.get("anchorCount")}
        if arm1.get("ok"):
            _r(rpc, sid, "playbookUtilityTrace", {"action": "status", "clear": True}, 60)
            res["un_playbook"] = _mesure(rpc, sid, rid, a.repet)
            st = _r(rpc, sid, "playbookUtilityTrace", {"action": "status"}, 60)
            d = st.get("diag") or {}
            res["un_playbook"]["fires_total"] = d.get("fires")
            res["un_playbook"]["fires_par_tour"] = (
                round((d.get("fires") or 0) / max(1, a.repet), 1))
            res["un_playbook"]["byMethod"] = d.get("byMethod")
            res["un_playbook"]["dropped"] = d.get("dropped")
        _r(rpc, sid, "playbookUtilityTrace", {"action": "disarm"}, 60)

        # --- regime 3 : TOUS (pire cas, 163 ancres) ---
        armall = _r(rpc, sid, "playbookUtilityTrace", {"action": "arm", "all": True}, 300)
        res["arm_all"] = {"ok": armall.get("ok"), "anchors": armall.get("anchorCount")}
        if armall.get("ok"):
            _r(rpc, sid, "playbookUtilityTrace", {"action": "status", "clear": True}, 60)
            res["tous"] = _mesure(rpc, sid, rid, a.repet)
            st = _r(rpc, sid, "playbookUtilityTrace", {"action": "status"}, 60)
            d = st.get("diag") or {}
            res["tous"]["fires_total"] = d.get("fires")
            res["tous"]["fires_par_tour"] = round((d.get("fires") or 0) / max(1, a.repet), 1)
            res["tous"]["byMethod"] = d.get("byMethod")
            res["tous"]["dropped"] = d.get("dropped")
        _r(rpc, sid, "playbookUtilityTrace", {"action": "disarm"}, 60)
    finally:
        # On desarme TOUJOURS : un capteur laisse arme penaliserait les autres acteurs.
        try:
            _r(rpc, sid, "playbookUtilityTrace", {"action": "disarm"}, 60)
        except Exception:                                           # noqa: BLE001
            pass
        try:
            _r(rpc, sid, "disposeRunner", {"runnerId": rid}, 30)
        except Exception:                                           # noqa: BLE001
            pass

    base = res["desarme"]["median_s"]
    print("\n[988-r1] LATENCE d'un tour d'IA (median sur %d repetitions)" % a.repet)
    print("   desarme            : %6.3f s  [%.3f .. %.3f]"
          % (base, res["desarme"]["min_s"], res["desarme"]["max_s"]))
    for cle, libelle in (("un_playbook", "arme 1 playbook"), ("tous", "arme TOUS (163)")):
        m = res.get(cle)
        if not m:
            continue
        surcout = m["median_s"] - base
        pct = (surcout / base * 100.0) if base > 0 else float("nan")
        print("   %-18s : %6.3f s  [%.3f .. %.3f]   surcout %+.3f s (%+.1f %%)"
              % (libelle, m["median_s"], m["min_s"], m["max_s"], surcout, pct))
        print("        fires/tour = %-8s  dropped = %-6s  byMethod = %s"
              % (m.get("fires_par_tour"), m.get("dropped"), m.get("byMethod")))
        res[cle]["surcout_s"] = round(surcout, 3)
        res[cle]["surcout_pct"] = round(pct, 1)

    print("\n[988-r1] LECTURE : le regime de crash documente est une frame > 960 ms provoquee par")
    print("         ~27 000 appels/s sur un getter chaud. Les chiffres ci-dessus disent si l'un")
    print("         des deux axes (latence / volume) mord SUR CE POINT D'ANCRAGE. `dropped > 0`")
    print("         signale une perte d'information, jamais un risque pour le jeu.")

    if a.json:
        print(json.dumps(res, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
