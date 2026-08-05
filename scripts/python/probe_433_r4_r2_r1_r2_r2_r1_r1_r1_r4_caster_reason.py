"""#433-r4-r2-r1-r2-r2-r1-r1-r1-r4 -- le QUATRIEME gate CASTER, et ce qu'il debloque.

LA QUESTION BINAIRE. `IdunBattle.Core.Services.AttackQuery$$GetAllTilesInAbilityRange` (surcharge
4 arguments) evalue QUATRE gates avant de verser la zone d'une ability. Les trois premiers sont
portes depuis `#433-r4-r2-r1-r1-c` ; le quatrieme -- la marche (g), un appel a
`IdunBattle.Core.Services.TargetingQuery$$GetInvalidCasterReason` -- ne l'etait pas. Est-ce lui qui
annulait `1045 GetEmRuntz` sur `orksRuntherd`, et le porter rend-il la branche INCLUSION de la zone
(`#...-r1-r1-r1-r1`) enfin CONFRONTABLE ?

CE QUE LE DECOMPILE DIT. La cascade CASTER, onze regles, est transcrite verbatim dans
`engine/services/ability_caster_gates.py` (section GATE 4). Sur les 148 masques RE-lus, un seul
porteur du POOL arme une de ces regles d'une facon derivable : `1045`, masque `0x8004`
(`CasterMatchesDynamicRule | CasterIsPossibleTarget`), dont la regle-delegue
`IdunBattleLogic.Entities.Abilities.Active.Loki.GetEmRuntzAbility$$GetDynamicInvalidCasterReason`
rend **2** quand `GetSpawnTileSelector` est VIDE -- « aucune tuile libre adjacente au Runtherd ET
adjacente a un ennemi ».

⚠ ETAT COURANT, PAS ETAT INTERROGE. `GetAllTilesInAbilityRange(unit, possiblePositions, true)`
balaie des positions CANDIDATES et passe chacune en `casterTiles`, mais le selecteur de spawn part
de `AdjacentTiles(Caster())` et `IdunBattle.Entities.Selectors.CasterSelector$$Select` rend
l'ENTITE caster (`entities+0x08`), dont `SelectTiles` prend le `GetMainTile`. Le verdict du gate est
donc CONSTANT sur tout le balayage. D'ou `caster_pos` cote port.

CE QUE CE PROBE MESURE, en DEUX regimes du MEME montage -- c'est le couple qui prouve, pas l'un des
deux :
  * regime MORD  : `casterReason != 0` -> le natif ne verse RIEN pour `1045`, la zone se reduit a
    l'attaque normale. Le port SANS le 4e gate y ajoute la tuile source (1 FP) ;
  * regime PASSE : `casterReason == 0` -> le natif VERSE la tuile source (branche INCLUSION), et le
    port doit la verser AUSSI. C'est la mesure que `#...-r1-r1-r1-r1` attendait : sans le gate, on
    ne pouvait pas distinguer « le port a tort » de « le port a raison mais le gate l'annule ».

Le regime PASSE s'obtient en laissant l'IA adverse APPROCHER (des `endturn` successifs) : des qu'un
ennemi est adjacent a la tuile libre voisine du Runtherd, le selecteur de spawn devient non vide.

Le TEST qui garde le port est `tests/engine/test_433_r4_r2_r1_r2_r2_r1_r1_r1_r4_caster_reason_*.py`.
ASCII only.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import uuid
from pathlib import Path

import gameconfig as GC                                                  # noqa: E402
import hexgeo                                                            # noqa: E402
from engine.runner.abilities.handler import ABILITY_CLASSES              # noqa: E402
from engine.runner.abilities.targeting import (TARGETING_OPTIONS_UNPORTED,  # noqa: E402
                                               targeting_options_for)
from engine.runner.abilities.targeting_rule import TargetingRule as TR   # noqa: E402
from engine.services import ability_caster_gates as acg                  # noqa: E402
from engine.services import ability_range as AR                          # noqa: E402
from rl_collect_batch import _resolve_session, _rpc                      # noqa: E402

PYDIR = Path(__file__).resolve().parent
ROOT = PYDIR.parents[1]
SEED = "777"

#: Le porteur confrontable du gate : `orksRuntherd` / `1045 GetEmRuntz`, masque `0x8004`.
CASTER_VISUAL = "orksRuntherd"
GETEMRUNTZ = 1045

#: Meme montage que `#...-r1-r1-r1` : les fillers OCCUPENT les tuiles de spawn voisines, ce qui rend
#: le movable set SINGLETON -- le seul regime ou la tuile source n'est pas couverte depuis une autre.
BOARD = "MC1_67"
FILLER = "necroWarden"
MEASURE_RANGE = 1

#: Les onze regles de la cascade CASTER, dans l'ORDRE NATIF de
#: `TargetingQuery$$GetInvalidCasterReason` -- l'inventaire les compte par ce nom.
CASTER_RULES = ("CasterHasNotMoved", "CasterCanMove", "CasterHasCompletedOneTurn",
                "AllowNullCasterTile", "CasterHasNoTile", "CasterMatchesDynamicRule",
                "CasterHas1Tiles", "CasterHas3Tiles", "CasterHas7Tiles",
                "CasterHas2TurnsLeft", "CasterIsMachine")


def ability_ids() -> list:
    """Les ids dont les `TargetingOptions` sont RE-lues, par les DEUX sources du foyer."""
    ids = {int(a) for a in ABILITY_CLASSES
           if getattr(ABILITY_CLASSES[a], "TARGETING_OPTIONS", None) is not None}
    ids |= {int(a) for a in TARGETING_OPTIONS_UNPORTED}
    return sorted(ids)


def inventaire() -> dict:
    """Le GISEMENT de chaque regle CASTER sur les masques RE-lus, et le regime de chaque
    regle-delegue. Une regle a ZERO porteur est un mirror STRUCTUREL -- c'est un resultat."""
    aids = ability_ids()
    par_regle = {}
    for n in CASTER_RULES:
        bit = int(getattr(TR, n))
        par_regle[n] = [a for a in aids
                        if int(getattr(targeting_options_for(a), "rules", 0) or 0) & bit]
    dyn = sorted(a for a in aids
                 if int(getattr(targeting_options_for(a), "rules", 0) or 0)
                 & int(TR.CasterMatchesDynamicRule))
    regimes = {}
    for a in dyn:
        regimes.setdefault(acg.dynamic_caster_gate_of(a), []).append(a)
    return {"abilities": len(aids),
            "par_regle": {k: len(v) for k, v in par_regle.items()},
            "porteurs": {k: v for k, v in par_regle.items() if v},
            "dyn_porteurs": dyn,
            "dyn_regimes": {k: sorted(v) for k, v in sorted(regimes.items())},
            "table_couvre_les_porteurs": sorted(acg.DYNAMIC_CASTER_GATE_BY_ABILITY) == dyn}


# ------------------------------------------------------------------------------------------------
# LE VOLET LIVE
# ------------------------------------------------------------------------------------------------

def _r(sid, m, b, t=90):
    return (_rpc(sid, m, [b], timeout=t).get("result") or {})


def _build(board, p_units, a_units):
    state = ROOT / "logs" / "runners" / ("p433r4-%s.json" % uuid.uuid4().hex[:8])
    state.parent.mkdir(parents=True, exist_ok=True)
    argv = [sys.executable, "rl_duel.py", "build", "--seed", SEED, "--board", board,
            "--state-file", str(state), "--p-units", p_units, "--a-units", a_units,
            "--hp-target", "90000", "--hp-player", "90000"]
    p = subprocess.run(argv, cwd=str(PYDIR), capture_output=True, text=True,
                       encoding="utf-8", errors="replace")
    if not state.exists():
        return None, (p.stderr or p.stdout or "")[-1500:]
    return json.loads(state.read_text())["runnerId"], None


def _dispose(sid, rid):
    if rid is None:
        return
    try:
        _r(sid, "disposeRunner", {"runnerId": rid}, 60)
    except Exception:                                                    # pragma: no cover
        pass


def _obs(sid, rid):
    o = _r(sid, "observeBattle", {"runnerId": rid}, 120)
    return [u for u in (o.get("units") or [])
            if not u.get("isDead") and u.get("col") is not None]


def _threat(sid, rid):
    mov = _r(sid, "aiMovableTiles",
             {"runnerId": rid, "threat": True, "side": "all",
              "overrideRange": MEASURE_RANGE}, 150)
    return {u.get("unitId"): ([(t["col"], t["row"]) for t in (u.get("tiles") or [])],
                              {(t["col"], t["row"]) for t in (u.get("threatTiles") or [])})
            for u in (mov.get("units") or [])}


def _board_maps(sid, rid):
    bg = _r(sid, "boardGraph", {"runnerId": rid}, 90)
    tiles = bg.get("tiles") or []
    pos = {t["id"]: (t["col"], t["row"]) for t in tiles}
    return ({pos[t["id"]]: t.get("elevation") for t in tiles},
            {pos[t["id"]]: bool(t.get("walkable")) for t in tiles},
            {pos[t["id"]]: bool(t.get("isWall")) for t in tiles},
            {pos[t["id"]]: bool(t.get("isInFog")) for t in tiles})


def _dv_state(sid, rid, visual):
    """L'etat par ability (`decisionView`, `allAbilities: true`) -- le canal des TROIS PREMIERS
    gates. Les alimenter est ce qui rend le 4e ISOLABLE : si l'ecart persiste alors qu'ils sont
    nourris, il ne vient pas d'eux."""
    dv = _r(sid, "decisionView", {"runnerId": rid, "allAbilities": True, "maxRank": 1}, 180)
    row = next((u for u in (dv.get("units") or []) if u.get("visualId") == visual), None)
    if row is None:
        return None, None
    return acg.ability_state_map(row), acg.normal_attack_id(row)


class _SansGate4:
    """Le contre-factuel : le port SANS la marche (g). C'est EXACTEMENT ce qu'il faisait avant cette
    tranche -- `invalid_caster_reason` rendait toujours « valide ».

    ⚠ La substitution porte sur `acg.invalid_caster_reason`, que `caster_gate_reason` appelle par
    son nom de module : la muter est donc EFFECTIF. `_mordu` le VERIFIE, parce que sur une
    contre-epreuve le vert est le resultat suspect."""

    def __enter__(self):
        self._f = acg.invalid_caster_reason
        acg.invalid_caster_reason = lambda ability_id, caster=None: 0
        AR._REACH_CACHE.clear()
        return self

    def __exit__(self, *_exc):
        acg.invalid_caster_reason = self._f
        AR._REACH_CACHE.clear()
        return False


def _mordu(caster_sub) -> bool:
    """La mutation de `_SansGate4` CHANGE-t-elle la reponse du gate sur `1045` ? Sans ce controle,
    un `EXACT` des deux cotes se lirait comme « le gate ne sert a rien » alors qu'il pourrait ne
    pas s'appliquer du tout."""
    avec = acg.invalid_caster_reason(GETEMRUNTZ, caster_sub)
    with _SansGate4():
        sans = acg.invalid_caster_reason(GETEMRUNTZ, caster_sub)
    return avec != sans


def _port_zone(move_tiles, all_tiles, visual, elev, walk, wall, fog, caster_pos,
               caster_team=None, team_by_pos=None, ability_ids=None,
               ability_state=None, normal_attack_id=None):
    """Le port, evalue en UNION sur le MOVABLE SET -- le meme `possiblePositions` que le natif.

    `caster_pos` est passe EXPLICITEMENT : dans ce regime la position balayee n'est pas la tuile
    courante, et le 4e gate lit la COURANTE (cf. l'en-tete)."""
    AR._REACH_CACHE.clear()
    out = set()
    for T in all_tiles:
        for X in move_tiles:
            if AR.is_tile_in_range_of_any_ability(X, T, visual, ability_ids=ability_ids,
                                                  elev_by_pos=elev, ability_state=ability_state,
                                                  normal_attack_id=normal_attack_id,
                                                  is_wall_by_pos=wall, walkable_by_pos=walk,
                                                  is_in_fog_by_pos=fog, caster_pos=caster_pos,
                                                  caster_team=caster_team,
                                                  team_by_pos=team_by_pos):
                out.add(T)
                break
    return out


def _caster_reason(sid, rid, uid):
    """`casterReason` de l'oracle `abilityReason` -- la raison CASTER structuree du natif, en NOMS
    de `TargetingRule`. C'est le seul canal qui dise QUELLE regle mord ; l'ensemble de tuiles, lui,
    ne dit que « rien versé »."""
    rep = _r(sid, "abilityReason",
             {"runnerId": rid, "casterId": uid, "abilityType": GETEMRUNTZ, "targetId": uid}, 90)
    return (rep or {}).get("casterReason")


def live(sid, board=None, fillers=3, tours=8) -> dict:
    rid, err = _build(board or BOARD,
                      ",".join([CASTER_VISUAL] + [FILLER] * int(fillers)),
                      "%s,%s" % (FILLER, FILLER))
    if rid is None:
        return {"error": "build KO -- %s" % err}
    try:
        out = {"board": board or BOARD, "runner": rid, "tours": []}
        elev, walk, wall, fog = _board_maps(sid, rid)
        allp = sorted(elev)
        for it in range(int(tours)):
            units = _obs(sid, rid)
            me = next((u for u in units if u.get("visualId") == CASTER_VISUAL), None)
            if me is None:
                out["tours"].append({"iter": it, "error": "caster absent"})
                break
            uid, pos = me["id"], (me["col"], me["row"])
            team_by_pos = {(u["col"], u["row"]): u.get("owner") for u in units}
            my_team = me.get("owner")
            th = _threat(sid, rid)
            move, natif = th.get(uid) or ([], set())
            natif &= set(allp)
            st, na_id = _dv_state(sid, rid, CASTER_VISUAL)
            sub = acg.CasterSubstrate(pos=pos, has_tile=True, team=my_team,
                                      team_by_pos=team_by_pos, walkable_by_pos=walk,
                                      elev_by_pos=elev, neigh_by_pos=None)
            ligne = {
                "iter": it, "pos": list(pos), "n_move": len(move), "move": sorted(move),
                "casterReason_natif": _caster_reason(sid, rid, uid),
                "gate_port": acg.invalid_caster_reason(GETEMRUNTZ, sub),
                "gate_port_nom": acg.caster_gate_reason(GETEMRUNTZ, (st or {}).get(GETEMRUNTZ),
                                                        sub),
                "mutation_mord": _mordu(sub),
                "n_natif": len(natif),
            }
            if move:
                apres = _port_zone(move, allp, CASTER_VISUAL, elev, walk, wall, fog, pos,
                                   caster_team=my_team, team_by_pos=team_by_pos,
                                   ability_state=st, normal_attack_id=na_id)
                with _SansGate4():
                    avant = _port_zone(move, allp, CASTER_VISUAL, elev, walk, wall, fog, pos,
                                       caster_team=my_team, team_by_pos=team_by_pos,
                                       ability_state=st, normal_attack_id=na_id)
                normale = _port_zone(move, allp, CASTER_VISUAL, elev, walk, wall, fog, pos,
                                     caster_team=my_team, team_by_pos=team_by_pos,
                                     ability_ids=[], ability_state=st, normal_attack_id=na_id)
                ligne.update({
                    "n_normale_seule": len(normale),
                    "n_avant": len(avant), "n_apres": len(apres),
                    "fp_avant": sorted(avant - natif), "fn_avant": sorted(natif - avant),
                    "fp_apres": sorted(apres - natif), "fn_apres": sorted(natif - apres),
                    "source_dans_natif": sorted(t for t in move if t in natif),
                })
            out["tours"].append(ligne)
            _r(sid, "applyAction", {"runnerId": rid, "action": {"kind": "endturn"}}, 60)
        return out
    finally:
        _dispose(sid, rid)


def _verdict(res) -> int:
    """DEUX regimes exiges, et le port EXACT dans les deux. Un seul regime ne prouverait rien :
    « mord » seul ne dit pas que la branche INCLUSION est juste, « passe » seul ne dit pas que le
    gate existe."""
    mord = passe = 0
    faux = []
    for d in (res.get("tours") or []):
        if d.get("error") or d.get("n_move") != 1 or "n_apres" not in d:
            continue
        hexnat = ((d.get("casterReason_natif") or {}).get("hex"))
        nat_invalide = bool(hexnat) and str(hexnat) not in ("0", "0x0")
        port_invalide = bool(d.get("gate_port"))
        if nat_invalide != port_invalide:
            faux.append(("etage", d["iter"], hexnat, d.get("gate_port")))
        if d["fp_apres"] or d["fn_apres"]:
            faux.append(("zone", d["iter"], d["fp_apres"], d["fn_apres"]))
        if nat_invalide:
            mord += 1
        else:
            passe += 1
            if not d["source_dans_natif"]:
                faux.append(("inclusion", d["iter"], "gate PASSE mais le natif "
                             "ne verse pas la tuile source"))
    print("regimes en singleton : MORD=%d  PASSE=%d" % (mord, passe))
    for f in faux:
        print("  DESACCORD %s" % (f,))
    if not mord or not passe:
        print("VERDICT: INCOMPLET -- il faut les DEUX regimes (augmenter --tours)")
        return 1
    if faux:
        print("VERDICT: ECART")
        return 1
    print("VERDICT: EXACT dans les deux regimes")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--step", default="all", choices=("all", "inventaire", "live"))
    ap.add_argument("--board", default=None)
    ap.add_argument("--fillers", type=int, default=3)
    ap.add_argument("--tours", type=int, default=8)
    args = ap.parse_args()
    if args.step in ("all", "inventaire"):
        inv = inventaire()
        print("abilities aux masques RE-lus : %d" % inv["abilities"])
        for k, n in sorted(inv["par_regle"].items(), key=lambda kv: -kv[1]):
            print("  %-28s %3d porteur(s)%s" % (k, n, "" if n else "   [mirror STRUCTUREL]"))
        print("regle-delegue CASTER -- regimes :")
        for k, v in inv["dyn_regimes"].items():
            print("  %-16s %s" % (k, v))
        print("la table couvre exactement les porteurs : %s"
              % inv["table_couvre_les_porteurs"])
        if not inv["table_couvre_les_porteurs"]:
            return 1
    if args.step in ("all", "live"):
        sid = _resolve_session()
        res = live(sid, args.board, args.fillers, args.tours)
        print(json.dumps(res, indent=2, sort_keys=True, default=str))
        if res.get("error"):
            return 1
        for d in (res.get("tours") or []):
            if d.get("error"):
                print("iter %d ERREUR %s" % (d["iter"], d["error"]))
                continue
            print("iter %d pos=%s n_move=%d casterReason=%s gate_port=%s (mutation mord: %s) "
                  "natif=%s avant=%s apres=%s"
                  % (d["iter"], d["pos"], d["n_move"],
                     (d.get("casterReason_natif") or {}).get("hex"),
                     d.get("gate_port"), d.get("mutation_mord"), d.get("n_natif"),
                     d.get("n_avant"), d.get("n_apres")))
        return _verdict(res)
    return 0


if __name__ == "__main__":
    sys.exit(main())
