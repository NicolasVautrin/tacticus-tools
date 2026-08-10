"""#605 -- MESURE D'ETAGE de `...HellfireShellsAbility$$ExecuteBehaviour` : les deux constantes
lues en entree (`IdunBattle.Configuration.AbilityConfiguration$$GetNumberConstant`) vs le NOMBRE DE
COUPS que le natif emet.

Le decompile dit :

    uVar6 = GetNumberConstant( config@0x60, 0x2f = nrOfHits )
    uVar7 = GetNumberConstant( config@0x60, 0x2b = extraHit )
    base  = AttackWithAttackDamage( ..., hits = uVar6, ... )
    big   = AttackWithAttackDamage( ..., hits = uVar6 + uVar7, ... )
    If( HasTrait(Target@0x60, 0x3f9 BigTarget), big, base )

Une premiere mesure live a rendu **1** coup hors `BigTarget` (le decompile en annonce
`nrOfHits` = 2) et **4** avec (`nrOfHits + extraHit` = 4). Plutot que de fitter un scalaire, ce
probe fait VARIER l'entree et lit la sortie : il patche
`BC.Abilities.ActiveAbilities.HellfireShells.Constants` dans une COPIE du seed BC, EPINGLE cette
config (sidecar `.pins.json` -- sans quoi `refresh_ability_configs` la reecrit depuis le gameconfig
au rechargement, et la fixture est INERTE, cf. #375), monte un runner par point de mesure et compte
les events `UnitDamaged` d'un cast.

⚠ Le porteur est amene par le CHEMIN DE STATS EXPLICITE (`--explicit-stats`, #419-r1-tr12-r2) :
`ultraNpc4HeavyIntercessor` est le VRAI porteur npc de 1080, avec SES stats, SES traits et SES
armes -- pas une greffe.

Usage (depuis `scripts/python`) :

    python probe_605_hellfire_hits.py --state-file <ABSOLU>.json
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import uuid
from pathlib import Path

import catalog_inject as CI
import hexgeo
import rl_duel as R
import stream_events as SE

PORTEUR = "ultraNpc4HeavyIntercessor:33"
PORTEUR_VIS = "ultraNpc4HeavyIntercessor"
CIBLE_SANS = "ultraTitus"          # aucun trait `BigTarget`
CIBLE_AVEC = "astraBullgryn"       # traits: Hero, BigTarget
BOARD = "MC1_67"
ABILITY = 1080
PORTEE = 3                         # `constants.range`
CLE_CONFIG = "ActiveAbilities/HellfireShells"


def _seed_bc_patche(sortie: Path, nr_of_hits: int, extra_hit: int) -> str:
    """COPIE du seed BC dont la config d'ability 1080 porte les deux constantes demandees, PLUS son
    sidecar d'epinglage.

    On ecrit dans `Constants`, c'est-a-dire exactement ce que `GetNumberConstant` lit -- pas dans le
    gameconfig, qui n'est PAS ce que le runner charge. `_load_seed_bc` etant appele DE NOUVEAU au
    build, l'epingle est ce qui empeche `refresh_ability_configs` d'ecraser le patch."""
    bc = R._load_seed_bc(None)
    cfg = ((bc.get("Abilities") or {}).get("ActiveAbilities") or {}).get("HellfireShells")
    if cfg is None:
        raise SystemExit("[605] HellfireShells absente de BC.Abilities.ActiveAbilities")
    consts = cfg.setdefault("Constants", {})
    consts["nrOfHits"] = str(int(nr_of_hits))
    consts["extraHit"] = str(int(extra_hit))
    sortie.write_text(json.dumps(bc), encoding="utf-8")
    CI.write_pins(sortie, [CLE_CONFIG])
    return str(sortie)


def _coups(res, cible_id: int) -> list:
    """La SEQUENCE des montants du natif (tags `Amount` des pas `UnitDamaged` de l'ability 1080),
    resolue PAR NOM de pas -- un ordinal fige designerait le pas voisin au prochain build."""
    out = []
    for a in ((res or {}).get("actions") or []):
        for e in (a.get("events") or []):
            if e.get("step") != SE.step_id("UnitDamaged"):
                continue
            try:
                t = json.loads(e.get("tags") or "{}")
            except Exception:
                continue
            if t.get("Active_Ability_Type") == ABILITY and int(t.get("Target_Id", -1)) == cible_id:
                out.append(int(t.get("Amount", 0)))
    return out


def _pos(u):
    p = u.get("pos") or {}
    return (p.get("col"), p.get("row"))


def _vue(rpc, rid):
    return rpc("decisionView", {"runnerId": rid, "allAbilities": True}, 150)


def _rapproche(rpc, rid, porteur_id: int, cible_id: int, tours: int = 8) -> bool:
    """DEPLACE le porteur jusqu'a ce que la cible soit a portee -- on ne se plaint jamais de la
    geometrie de spawn."""
    for _ in range(tours):
        dv = _vue(rpc, rid)
        units = {u["id"]: u for u in (dv.get("units") or []) if u.get("alive")}
        me, tgt = units.get(porteur_id), units.get(cible_id)
        if me is None or tgt is None:
            return False
        if 1 <= hexgeo.distance(_pos(me), _pos(tgt)) <= PORTEE:
            return True
        if dv.get("currentPlayer") != me.get("owner"):
            rpc("applyAction", {"runnerId": rid, "action": {"kind": "endturn"}}, 60)
            continue
        mov = rpc("aiMovableTiles", {"runnerId": rid, "side": "friendly"}, 60) or {}
        tiles = set()
        for mu in (mov.get("units") or []):
            if mu.get("unitId") == porteur_id:
                tiles = {(t.get("col"), t.get("row")) for t in (mu.get("tiles") or [])
                         if t.get("col") is not None}
        if not tiles:
            rpc("applyAction", {"runnerId": rid, "action": {"kind": "endturn"}}, 60)
            continue
        tp = _pos(tgt)
        best = min(tiles, key=lambda p: hexgeo.distance(p, tp))
        rpc("applyAction", {"runnerId": rid,
                            "action": {"kind": "move", "unitId": porteur_id,
                                       "to": {"col": best[0], "row": best[1]}}}, 60)
    return False


def _passe_le_tour(rpc, rid, porteur_id: int, tours: int = 4) -> bool:
    """Termine le tour courant jusqu'a ce que le porteur REDEVIENNE actif SANS avoir bouge.

    C'est le seul moyen d'isoler la variable << a bouge ce tour >> : `_rapproche` a deja consomme
    le deplacement, donc on rend la main et on revient. Le porteur retrouve alors la cible a portee
    et un `Moved` a FAUX -- exactement le regime que `RapidFire` distingue
    (i2 : << attacks twice if he did not move this turn >>)."""
    for _ in range(tours):
        rpc("applyAction", {"runnerId": rid, "action": {"kind": "endturn"}}, 120)
        dv = _vue(rpc, rid)
        units = {u["id"]: u for u in (dv.get("units") or []) if u.get("alive")}
        me = units.get(porteur_id)
        if me is not None and dv.get("currentPlayer") == me.get("owner"):
            return True
    return False


def _mesure(rpc, state_file: str, nr_of_hits: int, extra_hit: int, cible: str, tmp: Path,
            sans_mouvement: bool = False) -> dict:
    """UN point de mesure : un runner, un porteur, une cible, un cast.

    `sans_mouvement` : apres avoir amene la cible a portee, on rend la main et on revient, pour que
    le cast parte d'un porteur qui N'A PAS bouge ce tour-ci."""
    bc = _seed_bc_patche(tmp / ("hfs-%s.json" % uuid.uuid4().hex[:8]), nr_of_hits, extra_hit)
    R.main(["build", "--board", BOARD, "--seed", "777", "--no-ai", "--seed-bc", bc,
            "--explicit-stats", PORTEUR, "--p-units", PORTEUR, "--a-units", cible,
            "--armor-target", "0", "--block-target", "0,0", "--hp-target", "400000",
            "--state-file", state_file])
    rid = json.loads(Path(state_file).read_text(encoding="utf-8"))["runnerId"]
    try:
        dv = _vue(rpc, rid)
        units = [u for u in (dv.get("units") or []) if u.get("alive")]
        me = next((u["id"] for u in units if (u.get("visualId") or "") == PORTEUR_VIS), None)
        tg = next((u["id"] for u in units if (u.get("visualId") or "") == cible), None)
        if me is None or tg is None:
            raise SystemExit("[605] montage non installe : porteur=%r cible=%r" % (me, tg))
        # Le patch a-t-il MORDU ? On relit la config que le runner a REELLEMENT chargee -- sans ce
        # controle, une fixture inerte rendrait un accord qui ne prouve rien (#375).
        vu = json.loads(Path(state_file).read_text(encoding="utf-8"))
        lu = (((vu.get("bc") or {}).get("Abilities") or {}).get("ActiveAbilities")
              or {}).get("HellfireShells") or {}
        lus = (lu.get("Constants") or {})
        mordu = (lus.get("nrOfHits") == str(nr_of_hits) and lus.get("extraHit") == str(extra_hit))
        if not _rapproche(rpc, rid, me, tg):
            raise SystemExit("[605] cible jamais amenee a portee")
        if sans_mouvement and not _passe_le_tour(rpc, rid, me):
            raise SystemExit("[605] le porteur n'a jamais retrouve la main sans avoir bouge")
        # `Moved` LU sur l'etat live juste avant le cast -- jamais suppose de la sequence d'actions.
        dv2 = _vue(rpc, rid)
        me_u = next((u for u in (dv2.get("units") or []) if u.get("id") == me), {})
        a_bouge = bool(me_u.get("hasMoved") if me_u.get("hasMoved") is not None
                       else me_u.get("moved"))
        res = rpc("applyAction", {"runnerId": rid,
                                  "action": {"kind": "ability", "casterId": me, "targetId": tg,
                                             "abilityType": ABILITY}}, 240)
        a0 = ((res or {}).get("actions") or [{}])[0]
        if not a0.get("ok"):
            raise SystemExit("[605] le natif REFUSE le cast : %r" % (a0,))
        return {"nrOfHits": nr_of_hits, "extraHit": extra_hit, "cible": cible,
                "coups": _coups(res, tg), "patch_mordu": mordu, "a_bouge": a_bouge,
                "runner": rid}
    finally:
        rpc("disposeRunner", {"runnerId": rid}, 60)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--state-file", required=True)
    a = ap.parse_args(argv)
    tmp = Path(os.environ.get("TEMP") or ".") / ("probe605-%s" % uuid.uuid4().hex[:6])
    tmp.mkdir(parents=True, exist_ok=True)
    sid = R._resolve_session()

    def rpc(m, p, t=60):
        return R._rpc(sid, m, [p], timeout=t)["result"]

    print("[605] MESURE D'ETAGE -- entree = les deux constantes du BC, sortie = nb d'events "
          "`UnitDamaged` du cast")
    points = [(2, 2, CIBLE_SANS, False), (2, 2, CIBLE_AVEC, False),
              (7, 0, CIBLE_SANS, False), (7, 0, CIBLE_AVEC, False),
              (1, 5, CIBLE_SANS, False), (1, 5, CIBLE_AVEC, False),
              # Le MEME point que le premier, mais caste par un porteur qui N'A PAS bouge : c'est
              # ce que `RapidFire` distingue, et le seul ecart entre les deux montages qui avaient
              # rendu 1 coup et 2 coups pour la MEME config.
              (2, 2, CIBLE_SANS, True), (2, 2, CIBLE_AVEC, True)]
    for nh, eh, cible, immobile in points:
        m = _mesure(rpc, a.state_file, nh, eh, cible, tmp, sans_mouvement=immobile)
        print("  nrOfHits=%-2d extraHit=%-2d cible=%-16s immobile=%-5s a_bouge=%-5s "
              "patch_mordu=%-5s -> %d coup(s) %r"
              % (nh, eh, cible, immobile, m["a_bouge"], m["patch_mordu"], len(m["coups"]),
                 m["coups"]))
    print("[605] LECTURE : hors BigTarget le compte doit suivre `nrOfHits` ; avec BigTarget il doit "
          "suivre `nrOfHits + extraHit`. Tout ecart localise l'ETAGE fautif entre "
          "`GetNumberConstant` et `AttackDamageBehaviour`.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
