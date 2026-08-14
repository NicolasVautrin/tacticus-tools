"""#1042-r1 -- CONFRONTATION du port de `WisdomOfTheAncients_DamageReduction` (1445).

`probe_1042_wisdom_of_the_ancients_live.py` etablit le GROUND TRUTH natif (qui est vise, et de
combien). Ce probe-ci confronte le PORT a ce ground truth, en DEUX etages separes :

  A. le SELECTEUR -- `wisdom_of_the_ancients_target_ids(scene, <la MoW>)` contre les `targetIds`
     que `decisionView` publie sur l'entite-effet ;
  B. la MAGNITUDE -- la prediction de degat du port contre `attackPlans[].evals[].ranked[]`, par
     le foyer PARTAGE `prediction_confrontation` (tolerance 3, cf. sa docstring).

⚠ LE PIEGE QUE CE PROBE EVITE. `rl_duel build` impose `targetRarity = 5` a toute unite normalisee :
dans le regime par defaut, les TROIS etages `UnitsWithRarity(Mythic)` du selecteur sont
uniformement VRAIS et un port SANS gate y serait faussement d'accord. L'etage A exige donc que le
set natif SEPARE (au moins une unite PRISE **et** au moins une ECARTEE), et rc 3 sinon.

⚠ IDENTITE DU PORTEUR. `decisionView.mows[]` porte `id` **et** `casterId`, et ce ne sont PAS le
meme entier (mesure : `id = 76`, `casterId = 77`). `scene.step_context` cle TOUTES ses tables par
`casterId` ; interroger le resolveur avec `id` rend `None` et se lirait comme une divergence. C'est
`casterId` qu'on prend, et c'est ecrit ici parce que ca a coute une fausse divergence.

TEMOIN NON NUL, mesure le 2026-08-14 (bras `mow`, niveau 4, board MC1_67, seed 777) :

    origin/master  ->  7 divergences / 25 lignes   port=(2444, 3664)  oracle=(1956, 2932)
    ce port        ->  0 divergence  / 25 lignes   port=(1956, 2932)  oracle=(1956, 2932)

soit exactement `1 - dmgReductionPct[4]/100 = 0.80` sur les trois cibles de l'aura, et `1.0`
ailleurs. Le meme couple en bras separant (`--rarity adeptRetributor=4`) : natif `{P2, P3}`,
master 5 divergences, ce port 0.

Usage :
  python probe_1042r1_wisdom_confrontation_live.py                       # monte, confronte, dispose
  python probe_1042r1_wisdom_confrontation_live.py --rarity adeptRetributor=4
  python probe_1042r1_wisdom_confrontation_live.py --runner 231          # runner DEJA monte

rc : 0 accord | 1 DIVERGENCE | 2 montage muet | 3 regime DEGENERE (rien n'est separe).
Sortie ASCII only.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import prediction_confrontation as PC        # noqa: E402
import probe_1042_wisdom_of_the_ancients_live as G   # noqa: E402  (montage + constantes)
import rl_collect_batch as B                 # noqa: E402
import rl_duel as R                          # noqa: E402
from engine.playbook.prediction import _shared as SH        # noqa: E402
from engine.runner import snapshot as SNAP                  # noqa: E402

EFFECT_TYPE = G.EFFECT_TYPE                  # 1445


def _rpc_de(sid):
    def rpc(method, body=None, timeout=90):
        r = B._rpc(sid, method, [body] if body is not None else [], timeout=timeout)
        return (r.get("result") or {}) if isinstance(r, dict) else {}
    return rpc


def cibles_natives(dec: dict):
    """`(porteur, {ids vises})` -- l'entite-effet est publiee UNE FOIS, portee par sa SOURCE, et
    c'est son `targetIds` qui enumere les affectes (#1024). Le porteur rendu est la cle des tables
    de `Scene` : `casterId` pour une MoW (cf. l'en-tete), `id` pour une unite."""
    porteur, vises = None, set()
    for u in (dec.get("units") or []):
        for e in (u.get("effects") or []):
            if e.get("effectType") == EFFECT_TYPE:
                porteur, _ = u.get("id"), vises.update(e.get("targetIds") or [])
    for m in (dec.get("mows") or []):
        for e in (m.get("effects") or []):
            if e.get("effectType") == EFFECT_TYPE:
                porteur, _ = m.get("casterId"), vises.update(e.get("targetIds") or [])
    return porteur, vises


def confronter(rpc, rid: int) -> dict:
    """Les DEUX etages, sur un runner DEJA monte. Rend un dict de mesure (jamais un verdict)."""
    dec = rpc("decisionView", SNAP.decision_view_seed_body(rid, maxRank=99, allAbilities=True), 180)
    scene, sctx, dec = PC.construire_scene(rpc, rid, dec)
    porteur, vises = cibles_natives(dec)
    # L'UNIVERS sur lequel le regime doit separer : les unites du dv (une MoW n'y est pas).
    univers = {u.get("id") for u in (dec.get("units") or []) if u.get("id") is not None}
    porte = SH.wisdom_of_the_ancients_target_ids(scene, porteur) if porteur is not None else None
    namap = R._normal_ability_map(dec)
    na = sorted({v for v in namap.values() if v is not None})
    lignes, ecartes = PC.lignes_de_confrontation(scene, sctx, dec,
                                                 ability_id=(na[0] if na else None))
    return {"runner": rid, "porteur": porteur, "natif": sorted(vises),
            "port": (sorted(porte) if porte is not None else None),
            "univers": sorted(univers), "abilityNormale": (na[0] if na else None),
            "lignes": lignes, "ecartes": ecartes, "divergences": PC.divergences(lignes)}


def _verdict(m: dict) -> int:
    print("=== ETAGE A : le SELECTEUR ===")
    print("  porteur (cle des tables de Scene) : %s" % m["porteur"])
    print("  natif (decisionView.targetIds)    : %s" % m["natif"])
    print("  port  (resolveur PREDICTION)      : %s" % m["port"])
    if m["porteur"] is None or m["port"] is None:
        print("  MONTAGE MUET : aucun porteur de %d, ou resolveur non mesure -- rien n'est conclu."
              % EFFECT_TYPE)
        return 2
    pris, ecartes = set(m["natif"]), set(m["univers"]) - set(m["natif"])
    print("  temoin PRIS = %s ; temoin ECARTE = %s" % (sorted(pris), sorted(ecartes)))
    if not pris or not ecartes:
        print("  REGIME DEGENERE : le natif ne SEPARE pas (tout pris, ou rien pris). Un accord ici"
              " ne prouverait RIEN -- monter `--rarity <vis>=N` ou `--traits`.")
        return 3
    if set(m["port"]) != pris:
        print("  DIVERGENCE DE SELECTEUR : port\\natif=%s  natif\\port=%s"
              % (sorted(set(m["port"]) - pris), sorted(pris - set(m["port"]))))
        return 1
    print("  ACCORD.")

    print()
    print("=== ETAGE B : la MAGNITUDE (ability normale %s) ===" % m["abilityNormale"])
    print("  " + PC.resume(m["lignes"], m["ecartes"]).replace("\n", "\n  "))
    if not m["lignes"]:
        print("  AUCUNE LIGNE CONFRONTEE : rien n'est conclu (accord vide = zero preuve).")
        return 2
    if m["divergences"]:
        for d in m["divergences"][:12]:
            print("  DIV %s" % json.dumps(d))
        return 1
    print("  ACCORD sur les %d lignes." % len(m["lignes"]))
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description="#1042-r1 -- confrontation du port de 1445")
    ap.add_argument("--runner", type=int, default=None, help="runner DEJA monte (sinon on monte)")
    ap.add_argument("--level", type=int, default=4)
    ap.add_argument("--seed", type=int, default=777)
    ap.add_argument("--board", default=G.BOARD)
    ap.add_argument("--rarity", action="append", default=[],
                    help="'<visualId>=<n>', repetable -- cf. `probe_1042_...` (regime SEPARANT)")
    ap.add_argument("--state-file", default=None)
    ap.add_argument("--keep", action="store_true")
    a = ap.parse_args()

    sid = B._resolve_session()
    rpc = _rpc_de(sid)
    rid, monte_ici = a.runner, False
    if rid is None:
        rar = dict(x.split("=", 1) for x in a.rarity)
        rar.setdefault(G.H_VIS, str(G.RARITE_H))          # invariant du montage (cf. `probe_1042`)
        sf = a.state_file or str(Path(__file__).resolve().parents[2] / "logs"
                                 / ("probe1042r1_l%d%s.json"
                                    % (a.level, "".join("_%s%s" % (k[:6], v)
                                                        for k, v in sorted(rar.items())))))
        argv = ["build", "--seed", str(a.seed), "--board", a.board,
                "--p-units", ",".join(v for v, _ in G.MES_UNITS),
                "--a-units", ",".join(v for v, _ in G.AURA_UNITS),
                "--a-mow", G.PORTEUR_MOW,
                "--unit-stat", ";".join("%s:Rarity=%s" % (k, v) for k, v in sorted(rar.items())),
                "--equip-mythic", "%s:%s:%d" % (G.PORTEUR_MOW, G.ABILITY, a.level)]
        for vis, pos in G.MES_UNITS:
            argv += ["--place", "%s:%d,%d" % (vis, pos[0], pos[1])]
        for vis, pos in G.AURA_UNITS:
            argv += ["--a-place", "%s:%d,%d" % (vis, pos[0], pos[1])]
        argv += ["--state-file", sf]
        if R.main(argv) != 0:
            print("BUILD ECHOUE -- rien n'est conclu")
            return 2
        rid = json.loads(Path(sf).read_text(encoding="utf-8")).get("runnerId")
        monte_ici = True
        print("runnerId=%s  rarites=%s" % (rid, rar))
    try:
        return _verdict(confronter(rpc, int(rid)))
    finally:
        if monte_ici and not a.keep and rid is not None:
            try:
                rpc("disposeRunner", {"runnerId": rid}, 40)
                print("[runner %s dispose]" % rid)
            except Exception as exc:  # noqa: BLE001
                print("[dispose echoue : %s]" % type(exc).__name__)


if __name__ == "__main__":
    raise SystemExit(main())
