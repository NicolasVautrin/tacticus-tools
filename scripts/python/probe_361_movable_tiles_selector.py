"""probe #370 (residu `#361-r2`) -- QUEL maillon de `GetTileToMoveTo` rend vide dans le playbook.

LA QUESTION, BINAIRE
--------------------
`#386` a referme la localisation : les batchs 3/4 de `RammingSpeedPlaybook$$MakeDamagePredictions`
sont absents parce que les deux `ComparablePlaybook<T>$$GenerateAttackPredictions` rendent VIDE,
gate OUVERTE, composition `AdjacentUnits` mesuree VIVANTE 3/3. Reste l'`origin` : l'arbre
`RammingSpeedAbility$$GetTileToMoveTo`, qui rend la bonne tuile dans le contexte de
`RammingSpeedAbility$$GetDynamicInvalidTargetReason` (cast reel, MATCH 2/2) et VIDE dans celui du
playbook. **Lequel de ses maillons ?**

CE QUE LE CAPTEUR OBSERVE (`frida/hooks/features/ai-step/movable-tiles-probe.ts`, flag `tileProbe`)
---------------------------------------------------------------------------------------------------
`IdunBattle.Entities.Selectors.MovableTilesInRangeSelector$$Select` est le SEUL noeud de la chaine
haute dont un retour vide est SILENCIEUX -- partout ailleurs un maillon absent tombe dans le
thrower. Son corps porte trois issues, lues au decompile :

    entity   = unitSelector.<slot 7>(ctx)          ; if (entity == null)   -> List VIDE
    fromTile = unitTileSelector.<slot 0xc>(ctx)    ; if (fromTile == null) -> List VIDE
    return     IBattleQuery.GetMovableTilesInRange(entity, fromTile, ignoreFlags, options)

`entity` et `fromTile` sont des LOCALES : un attach sur `Select` seul ne les voit pas. Le capteur
arme donc AUSSI les deux sous-selecteurs, NOMMES et a corps court, qui les PRODUISENT :

  * `CasterSelector$$Select`     -> `if (ctx+0x08 == 0) return new List(); l.Add(ctx+0x08); return l`
  * `CasterTileSelector$$Select` -> `tiles = ctx+0x48 ?? ToList(ctx+0x40) ?? GetTiles(ctx+0x08)`
    (le SEUL noeud de l'arbre qui CHANGE de branche entre les deux contextes : le gate laisse
    `+0x48` nul, le playbook le renseigne)

DEUX GARDE-FOUS, sans lesquels ce probe mesurerait un artefact de MONTAGE
------------------------------------------------------------------------
  1. **La gate doit etre OUVERTE.** `MakeDamagePredictions` ne construit `GetTileToMoveTo()`
     qu'APRES `Any(selfPreds, p => p.WillBeKill)`. Gate fermee => 0 appel du capteur, et ce zero se
     lirait « l'arbre n'est pas evalue ». Le probe arme donc AUSSI `gateProbe` et REFUSE de
     conclure tant que `willBeKill` n'est pas vrai sur l'event du caster (d'ou `--hp-player`).
  2. **Le caster doit etre A PORTEE.** Le pool est `MovableTilesInRange(..., Direct(0x16))`
     intersecte `CanAddUnit(AdjacentTiles(Target))` : un caster au-dela de la portee rend ce pool
     vide LEGITIMEMENT. Le montage borne la distance (`caster_max_dist`) et le probe la RE-VERIFIE
     sur l'etat drive.

ASCII only (cp1252). Usage (depuis scripts/python, host up, session deja warmee) :
    python probe_361_movable_tiles_selector.py
    python probe_361_movable_tiles_selector.py --json
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import hexgeo

PYDIR = Path(__file__).resolve().parent
sys.path.insert(0, str(PYDIR))

from rl_collect_batch import _resolve_session, _rpc                          # noqa: E402
from probe_353r1_ramming_speed_charge_tile import (                          # noqa: E402
    ENEMY2, FILLER_P, GRAFT, VICTIM, _pos, _view)
from probe_361_ramming_speed_explosion_batches import _gate_verdict          # noqa: E402
from montage_361_attack_predictions_selector import (                        # noqa: E402
    ARMS, RAMMING_MOVE_RANGE, build_montage, dispose_montage)

# PV du camp JOUEUR : le 2e batch est un RECUL qui frappe le caster, il faut
# `hpBefore(caster) <= willKillDmg` pour que la gate ouvre. Le probe ne le SUPPOSE pas -- il relit
# le capteur de gate et refuse le bras si elle est restee fermee.
HP_PLAYER = 60

# Les deux sous-selecteurs que `GetTileToMoveTo` passe a `DSLSelectors$$MovableTilesInRange`
# (`factory+0x48` et `factory+0x50`). Le capteur publie les classes EFFECTIVES : le decodeur les
# CONFRONTE a celles-ci et refuse de conclure si la structure differe.
WANT_UNIT_SEL = "CasterSelector"
WANT_TILE_SEL = "CasterTileSelector"


def _r(sid, m, b, t=90):
    return (_rpc(sid, m, [b], timeout=t).get("result") or {})


# --------------------------------------------------------------------------------------------
# LE DECODEUR -- tout le verdict est DERIVE des champs du capteur, jamais d'un texte ecrit
# d'avance. Teste 100 % offline par `tests/engine/test_370_tile_probe_tristate_offline.py`.
# --------------------------------------------------------------------------------------------

def _sub_classes(node: dict) -> dict:
    """Retrouve, parmi les champs d'instance publies par le capteur, les classes des deux
    sous-selecteurs -- par leur NOM DE CLASSE, jamais par un offset ni un nom de champ suppose."""
    out = {"unit": None, "tile": None, "unitField": None, "tileField": None}
    for f in (node.get("fields") or []):
        cls = f.get("cls")
        if cls == WANT_UNIT_SEL and out["unit"] is None:
            out["unit"], out["unitField"] = cls, f.get("name")
        elif cls == WANT_TILE_SEL and out["tile"] is None:
            out["tile"], out["tileField"] = cls, f.get("name")
    return out


def _in_window(calls, node: dict) -> list:
    """Les appels d'un sous-selecteur survenus PENDANT cet appel du noeud principal."""
    lo, hi = node.get("seqEnter", -1), node.get("seqLeave", 1 << 30)
    return [c for c in (calls or []) if lo <= c.get("seq", -1) <= hi]


def _tile_verdict(tp) -> tuple:
    """Traduit le capteur #370 en (etiquette, phrase). TRI-ETAT strict a chaque maillon :
      `None`           -> capteur ABSENT du bundle injecte (reinject en attente) ;
      `nodes is None`  -> capteur DEMANDE mais NON ARME (un maillon n'a pas resolu) ;
      `nodes == []`    -> arme, et le natif n'appelle JAMAIS `MovableTilesInRangeSelector$$Select` ;
      un appel         -> la taille du pool rendu, puis, si elle est nulle, LEQUEL des deux
                          sous-selecteurs est vide -- donc laquelle des trois issues du corps."""
    if tp is None:
        return ("absent", "capteur #370 absent du bundle injecte (reinject en attente)")
    nodes = tp.get("nodes")
    if nodes is None:
        return ("non-arme", "capteur #370 NON ARME : %s" % tp.get("nodesError"))
    if not nodes:
        return ("zero-appel",
                "capteur #370 ARME : `MovableTilesInRangeSelector$$Select` n'est JAMAIS appele "
                "pendant `MakeDamagePredictions` => l'arbre `GetTileToMoveTo` n'est PAS EVALUE, et "
                "la cause est en AMONT du pool (`DSLSelectors$$First` / `$$SortTilesByUtility` / "
                "`TargetsSelector$$op_BitwiseAnd` / `$$AdjacentTiles`)")
    counts = [int(n.get("returnedCount", -1)) for n in nodes]
    if any(c < 0 for c in counts):
        return ("retour-illisible",
                "capteur #370 ARME (%d appel(s)) mais le retour de "
                "`MovableTilesInRangeSelector$$Select` n'est pas decodable (classes=%s) -- c'est "
                "une ERREUR de lecture, pas un pool vide"
                % (len(nodes), [n.get("returnedClass") for n in nodes]))
    if any(c > 0 for c in counts):
        return ("pool-non-vide",
                "capteur #370 ARME : `MovableTilesInRangeSelector$$Select` rend %s tuile(s) => le "
                "POOL n'est PAS vide, et la perte est en AVAL (`op_BitwiseAnd CanAddUnit` / "
                "`SortTilesByUtility` / `First`). Tuiles : %s"
                % (counts, [n.get("returnedTiles") for n in nodes]))

    # --- tous les appels rendent un pool VIDE : departager les trois issues du corps
    node = nodes[0]
    subs = _sub_classes(node)
    if subs["unit"] is None or subs["tile"] is None:
        return ("structure-inattendue",
                "capteur #370 ARME, pool VIDE (%d appel(s)), mais les sous-selecteurs ne sont pas "
                "ceux qu'attend `GetTileToMoveTo` (`%s` / `%s`) : champs vus = %s. Le decodeur "
                "REFUSE de conclure -- l'arbre a change, la RE est a refaire"
                % (len(nodes), WANT_UNIT_SEL, WANT_TILE_SEL,
                   [(f.get("name"), f.get("cls")) for f in (node.get("fields") or [])]))
    caster_calls, tile_calls = tp.get("casterCalls"), tp.get("casterTileCalls")
    if caster_calls is None or tile_calls is None:
        return ("sous-maillon-non-arme",
                "capteur #370 ARME sur le noeud (pool VIDE) mais PAS sur les sous-selecteurs : "
                "`%s` / `%s`. Les trois issues du corps restent indiscernables"
                % (tp.get("casterError"), tp.get("casterTileError")))
    unit_win = _in_window(caster_calls, node)
    tile_win = _in_window(tile_calls, node)
    ctx = node.get("ctx") or {}
    if unit_win and all(int(c.get("returnedCount", -1)) == 0 for c in unit_win):
        return ("unit-null",
                "capteur #370 : pool VIDE et `CasterSelector$$Select` rend 0 element (%d appel(s) "
                "dans la fenetre) => `entity == null` dans `MovableTilesInRangeSelector$$Select`, "
                "donc `ctx+0x08` (le caster) est NUL dans le contexte du playbook. Slot lu : %s"
                % (len(unit_win), (ctx.get("caster@0x08") or {}).get("ptr")))
    if tile_win and all(int(c.get("returnedCount", -1)) == 0 for c in tile_win):
        return ("from-tile-null",
                "capteur #370 : pool VIDE, le caster est PRESENT, et `CasterTileSelector$$Select` "
                "rend 0 tuile (%d appel(s) dans la fenetre) => `TargetsSelector$$SelectTile` rend "
                "null, donc `fromTile == null`. Branche : casterPosition@0x48=%s "
                "casterMainTile@0x40=%s caster@0x08=%s"
                % (len(tile_win), (ctx.get("casterPosition@0x48") or {}).get("ptr"),
                   (ctx.get("casterMainTile@0x40") or {}).get("ptr"),
                   (ctx.get("caster@0x08") or {}).get("ptr")))
    if not unit_win or not tile_win:
        return ("fenetre-vide",
                "capteur #370 : pool VIDE, mais AUCUN appel de sous-selecteur n'a ete observe dans "
                "la fenetre du noeud (caster=%d tuile=%d). Les trois issues restent "
                "indiscernables -- la correlation par sequence est a revoir"
                % (len(unit_win), len(tile_win)))
    return ("query-vide",
            "capteur #370 : pool VIDE alors que `CasterSelector$$Select` rend %s element(s) ET "
            "`CasterTileSelector$$Select` rend %s tuile(s) => les deux entrees sont PRESENTES, et "
            "c'est `IBattleQuery.GetMovableTilesInRange(entity, fromTile, ignoreFlags, options)` "
            "qui rend un ensemble VIDE"
            % ([c.get("returnedCount") for c in unit_win],
               [c.get("returnedCount") for c in tile_win]))


# --------------------------------------------------------------------------------------------
# LA MESURE
# --------------------------------------------------------------------------------------------

def _predict(sid, rid, cid, tid):
    """Une invocation avec les DEUX capteurs armes. `gateProbe` n'est pas decoratif : sans lui, un
    « 0 appel » du capteur de tuile serait indiscernable d'une gate restee fermee."""
    return _r(sid, "aiPlaybookPredict",
              {"runnerId": rid, "unitId": cid, "targetId": tid, "abilityType": ARMS["ramming"].ability,
               "gateProbe": True, "tileProbe": True}, 150)


def _port_tile(sid, rid, ids):
    """La tuile que rend le PORT (`ramming_speed_tile_to_move_to`, confronte 2/2 en #353-r1) --
    point de comparaison quand le pool n'est PAS vide. Jamais une source de verdict."""
    from engine.entities.pathfinding.board import Board
    from engine.runner.snapshot import load_state
    from engine.runner.abilities.orks import ramming_speed_tile_to_move_to
    bg = _r(sid, "boardGraph", {"runnerId": rid}, 60)
    board = Board(bg["tiles"], adjacency="evenq")
    dv = _view(sid, rid)
    ob = _r(sid, "observeBattle", {"runnerId": rid}, 40)
    snap = _r(sid, "combatSnapshot", {"runnerId": rid}, 60)
    state = load_state(dv, ob, snap, board=board)
    t = ramming_speed_tile_to_move_to(state, ids[GRAFT], ids[VICTIM], RAMMING_MOVE_RANGE)
    return (list(t) if t else None), dv


def run(seed: int = 37000, level: int = 8, verbose: bool = True) -> dict:
    sid = _resolve_session()
    arm = ARMS["ramming"]
    out: dict = {"seed": seed, "level": level, "ability": arm.ability,
                 "selector": arm.selector, "hp_player": HP_PLAYER,
                 "move_range": RAMMING_MOVE_RANGE}
    m = None
    try:
        m = build_montage(sid, arm, seed=seed, level=level, hp_player=HP_PLAYER,
                          caster_max_dist=RAMMING_MOVE_RANGE)
        out["runner"] = m.runner
        out["geometry"] = {k: list(v) for k, v in (m.geometry or {}).items()}
        out["montage_errors"] = list(m.errors)
        if m.errors:
            out["error"] = "; ".join(m.errors)
            return out
        caster, target = m.ids[GRAFT], m.ids[VICTIM]
        tile, dv = _port_tile(sid, m.runner, m.ids)
        out["port_tile"] = tile
        cp, tp_ = _pos(dv, caster), _pos(dv, target)
        out["caster_pos"], out["target_pos"] = cp, tp_
        out["caster_target_dist"] = (hexgeo.distance(tuple(cp), tuple(tp_))
                                     if cp and tp_ else None)
        nat = _predict(sid, m.runner, caster, target)
        out["playbook"] = nat.get("playbookClass")
        out["native_error"] = nat.get("error")
        out["n_events"] = len(nat.get("events") or [])
        self_ev = next((e for e in (nat.get("events") or [])
                        if e.get("targetId") == caster), None)
        out["self_will_be_kill"] = (self_ev or {}).get("willBeKill")
        out["gate_kind"], out["gate_phrase"] = _gate_verdict(nat.get("gateProbe"))
        out["tile_probe"] = nat.get("tileProbe")
        out["tile_kind"], out["tile_phrase"] = _tile_verdict(nat.get("tileProbe"))
    finally:
        if m is not None:
            dispose_montage(sid, m)

    # --- VERDICT DERIVE DES CHAMPS (jamais un recit ecrit d'avance)
    d = out.get("caster_target_dist")
    if out.get("error"):
        out["ok"] = False
        out["verdict"] = "MONTAGE KO : %s" % out["error"]
    elif d is None or d < 2 or d > RAMMING_MOVE_RANGE:
        out["ok"] = False
        out["verdict"] = ("BRAS NON DISCRIMINANT : distance caster->cible = %s, hors de "
                          "[2, %d]. Un caster hors portee vide le pool POUR UNE RAISON DE MONTAGE."
                          % (d, RAMMING_MOVE_RANGE))
    elif out.get("self_will_be_kill") is not True:
        out["ok"] = False
        out["verdict"] = ("BRAS NON DISCRIMINANT : la gate n'est pas ouverte (willBeKill=%s sur "
                          "l'event du caster) -- `GetTileToMoveTo` n'est meme pas construite. "
                          "Baisser --hp-player. Capteur gate : %s"
                          % (out.get("self_will_be_kill"), out.get("gate_phrase")))
    elif out["tile_kind"] in ("absent", "non-arme"):
        out["ok"] = False
        out["verdict"] = ("NON CONFRONTE : %s. Le montage est PRET et DISCRIMINANT (gate ouverte, "
                          "caster a distance %s) -- il ne manque que la fenetre de reinject."
                          % (out["tile_phrase"], d))
    elif out["tile_kind"] in ("retour-illisible", "structure-inattendue",
                              "sous-maillon-non-arme", "fenetre-vide"):
        out["ok"] = False
        out["verdict"] = "CAPTEUR NON CONCLUANT : %s" % out["tile_phrase"]
    else:
        out["ok"] = True
        out["verdict"] = ("MAILLON TRANCHE [%s] : %s" % (out["tile_kind"], out["tile_phrase"]))

    if verbose:
        print("[370] runner=%s ability=%s niveau=%s | geo=%s"
              % (out.get("runner"), arm.ability, level, json.dumps(out.get("geometry"))))
        print("[370] caster=%s cible=%s dist=%s tuile_port=%s"
              % (out.get("caster_pos"), out.get("target_pos"),
                 out.get("caster_target_dist"), out.get("port_tile")))
        print("[370] playbook=%s events=%s erreur=%s willBeKill(self)=%s"
              % (out.get("playbook"), out.get("n_events"), out.get("native_error"),
                 out.get("self_will_be_kill")))
        print("[370] capteur gate [%s] : %s" % (out.get("gate_kind"), out.get("gate_phrase")))
        print("[370] capteur tuile [%s] : %s" % (out.get("tile_kind"), out.get("tile_phrase")))
        print("[370] %s" % out.get("verdict"))
        print("[370] -> %s" % ("OK" if out.get("ok") else "ECHEC"))
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--seed", type=int, default=37000)
    ap.add_argument("--level", type=int, default=8)
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args()
    out = run(seed=a.seed, level=a.level, verbose=not a.json)
    if a.json:
        print(json.dumps(out, indent=1, default=str))
    return 0 if out.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
