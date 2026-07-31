#!/usr/bin/env python3
"""#270 -- CONFRONTATION LIVE : les 4 abilities que `enum_maps` ne connaissait pas.

CE QUE CETTE SONDE TRANCHE
--------------------------
`engine.ai.state_bridge._abilities_of` reconstruit la liste d'abilities d'une unite depuis le
gameconfig, en resolvant chaque NOM par le reverse de `enum_maps.ACTIVE_ABILITY_TYPE` -- et son
docstring dit : « une active dont le nom n'est pas dans l'enum est IGNOREE ». Quatre membres du
build `rnca9r7q6c` manquaient a cette table (1222 `MassDriverAccelerator`, 1227 `HeavyWarpFlamer`,
1231 `TitanhammerSquad`, 1232 `EmpyricAmbush`). L'affirmation « l'ability disparaissait de l'unite
offline » doit etre MESUREE, pas deduite du docstring.

Les 4 porteurs sont des HEROS (`kind=lineup`) ABSENTS du seed BC partage -> `catalog_inject`
(doctrine : « absent du pool != non confrontable »).

TROIS MESURES, dont une CONTRE-EPREUVE
--------------------------------------
  A. NATIF   -- `decisionView(allAbilities=true)` porte-t-il l'id sur le porteur ? (si non, la
                question ne se pose meme pas : rien a porter)
  B. OFFLINE -- `_abilities_of(visualId)` le porte-t-il, avec la table CORRIGEE ?
  C. CONTRE-EPREUVE -- on RETIRE l'id de `ACTIVE_ABILITY_TYPE` en memoire et on re-mesure B.
                S'il disparait, le correctif est PORTANT ; s'il reste, le test etait tautologique
                (l'ability arrivait par un autre chemin) et la conclusion serait a revoir.

Sortie 0 = les 3 mesures concordent sur les 4 porteurs. ASCII only.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import uuid
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
PYDIR = REPO / "scripts" / "python"
sys.path.insert(0, str(PYDIR))

import catalog_inject  # noqa: E402
from rl_collect_batch import _resolve_session, _rpc  # noqa: E402

# id -> (nom, porteur lineup). Les 4 membres AJOUTES par le build, cf. case-270 §4.
CIBLES = {
    1222: ("MassDriverAccelerator", "votanChampion"),
    1227: ("HeavyWarpFlamer", "thousSekhetar"),
    1231: ("TitanhammerSquad", "astarLysander"),
    1232: ("EmpyricAmbush", "eldarLhykhis"),
}

# Porteurs qui NE SE DEPLOIENT PAS. Vide depuis #270-d (2026-07-31) : `astarLysander` y figurait
# avec pour motif suppose la famille #254 (« `IconOfObstinacy` a `constants: null`, un
# `GetStringConstant` LEVE a la construction du trigger »). CETTE PISTE EST REFUTEE au decompile --
# aucune des classes du kit n'appelle `GetStringConstant`/`GetNumberConstant` a la construction, et
# la seule constante lue (`TitanhammerSquadAbility$$GetCurrentlyAffectedFriends` ->
# `GetNumberConstant(0x16 = AbilityConstantType.range)`) est PRESENTE au gameconfig.
#
# La vraie cause : `catalog_inject._traits` posait `Subfaction: ImperialFists` dans
# `UnitConfiguration.Traits`, qui est TYPE `List<IdunBattle.Entities.Enum.UnitTrait>` -- nom hors
# enum => `StringEnumConverter$$ReadJson` -> `EnumUtils$$ParseEnum` LEVE au step=deserialize BC
# d'`initAndStart`, ce qui emporte le BC ENTIER. Detail + montage A/B :
# `probe_270d_lysander_deploy.py`, `docs/rl/case-270d-trait-hors-enum.md`.
BLOQUES: dict = {}
FOES = "orksWarboss,orksNob,necroWarden,eldarRanger"
BOARD = "MC1_67"


def offline_abilities(vid: str) -> set[int]:
    """Ce que le port croit savoir des abilities de l'unite, depuis le SEUL gameconfig."""
    import engine.ai.state_bridge as SB
    SB._abilities_of.cache_clear()
    return {int(a[0]) for a in SB._abilities_of(vid)}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--seed", type=int, default=777)
    ap.add_argument("--board", default=BOARD)
    args = ap.parse_args()

    sid = _resolve_session()
    print("session Frida : %d" % sid)

    tmp = REPO / "logs" / "probe270"
    tmp.mkdir(parents=True, exist_ok=True)
    tag = uuid.uuid4().hex[:8]
    bc = tmp / ("seedbc-%s.json" % tag)
    state = tmp / ("state-%s.json" % tag)

    porteurs = [v for _, v in CIBLES.values() if v not in BLOQUES]
    for vid, motif in sorted(BLOQUES.items()):
        print("NON COUVERT  %-18s %s" % (vid, motif))
    catalog_inject.write_augmented_seed_bc(str(bc), porteurs)
    print("seed BC augmente : %s (%s)" % (bc.name, ", ".join(porteurs)))

    cmd = [sys.executable, "rl_duel.py", "build", "--seed", str(args.seed),
           "--board", args.board, "--seed-bc", str(bc), "--state-file", str(state),
           "--p-units", ",".join(porteurs), "--a-units", FOES]
    proc = subprocess.run(cmd, cwd=str(PYDIR), capture_output=True, text=True,
                          encoding="utf-8", errors="replace")
    if not state.exists():
        print("BUILD KO\n%s\n%s" % ((proc.stdout or "")[-1500:], (proc.stderr or "")[-1500:]))
        bc.unlink(missing_ok=True)
        return 1
    rid = json.loads(state.read_text(encoding="utf-8"))["runnerId"]
    print("runner %s   board %s   seed %d" % (rid, args.board, args.seed))

    rc = 0
    try:
        dec = (_rpc(sid, "decisionView", [{"runnerId": rid, "allAbilities": True}],
                    timeout=150).get("result") or {})
        par_vis = {}
        for u in (dec.get("units") or []):
            par_vis.setdefault(u.get("visualId"), set()).update(
                int(a.get("id")) for a in (u.get("abilities") or []) if a.get("id") is not None)

        import enum_maps as EM
        print("")
        print("%-6s %-24s %-18s %-8s %-8s %-14s" %
              ("id", "ability", "porteur", "A natif", "B port", "C sans l'entree"))
        for aid, (nom, vid) in sorted(CIBLES.items()):
            if vid in BLOQUES:
                print("%-6d %-24s %-18s %s" % (aid, nom, vid, "NON COUVERT (montage)"))
                continue
            natif = aid in par_vis.get(vid, set())
            porte = aid in offline_abilities(vid)
            sauve = EM.ACTIVE_ABILITY_TYPE.pop(aid, None)
            try:
                sans = aid in offline_abilities(vid)
            finally:
                if sauve is not None:
                    EM.ACTIVE_ABILITY_TYPE[aid] = sauve
                offline_abilities(vid)   # purge le cache lru avec la table restauree
            ok = natif and porte and not sans
            rc |= 0 if ok else 1
            print("%-6d %-24s %-18s %-8s %-8s %-14s %s"
                  % (aid, nom, vid, natif, porte, sans, "OK" if ok else "<-- ECART"))

        print("")
        print("A natif=True  : le jeu porte bien l'ability sur ce porteur (la question se pose).")
        print("B port=True   : le port la voit, table CORRIGEE.")
        print("C sans=False  : elle DISPARAIT si on retire l'entree -> le correctif est PORTANT")
        print("                (si C etait True, la mesure serait tautologique).")
    finally:
        _rpc(sid, "disposeRunner", [{"runnerId": rid}], timeout=30)
        state.unlink(missing_ok=True)
        bc.unlink(missing_ok=True)
    return rc


if __name__ == "__main__":
    raise SystemExit(main())
