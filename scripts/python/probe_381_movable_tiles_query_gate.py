"""probe #381 (residu `#361-r3`) -- QUELLE branche de la garde d'entree vide le pool de tuiles.

OU EN EST LA QUESTION, ET CE QUE LA MESURE PRECEDENTE A REELLEMENT DIT
----------------------------------------------------------------------
Le capteur #370/#374 est CHARGE (session 4). Il repond deux choses DIFFERENTES selon le montage,
et c'est leur ecart qui est l'objet de ce probe :

  * `probe_361_ramming_speed_explosion_batches` -- le SEUL regime DEFICITAIRE connu (2 events pour
    5 attendus, gate OUVERTE, cast reel qui PASSE) : `tile_kind = query-vide`, **4 appels**,
    `returnedCount = 0` sur les quatre, `returnedClass = OrderedSet`1` sur les quatre.
  * `probe_361_movable_tiles_selector` -- ses DEUX bras sont EXACTS (4 == 4 et 5 == 5), donc ils
    n'ont AUCUNE perte a expliquer ; leur `pool-non-vide` (28 et 51 tuiles) ne mesure que le
    regime ou tout marche.

⚠ Un `pool-non-vide` lu sur un bras SANS deficit n'etablit donc PAS que « la perte est en aval » :
il n'y a pas de perte dans ce bras. La phrase inverse -- « la perte est en AVAL (`op_BitwiseAnd
CanAddUnit` / `SortTilesByUtility` / `First`) » -- est exactement ce que la mesure du regime
deficitaire REFUTE : le pool y vaut `0`, donc les trois maillons aval operent sur un pool DEJA
VIDE et sont hors de cause.

CE QUE LA CLASSE DU RETOUR ETABLIT (et qui ferme la moitie de la question)
--------------------------------------------------------------------------
`IdunBattle.Entities.Selectors.MovableTilesInRangeSelector$$Select`, lu au decompile, porte trois
issues et elles ne rendent PAS le meme type :

    entity   = _unitSelector.<slot 7>(ctx)         ; if (entity == 0)   -> `List`1` VIDE
    fromTile = _unitTileSelector.<slot 0xc>(ctx)   ; if (fromTile == 0) -> la MEME `List`1` VIDE
    return     _battleQuery.<slot 0xc>(entity, fromTile, _ignoreFlags, options)  -> `OrderedSet`1`

Le regime deficitaire rend `OrderedSet`1` : les deux early-returns sont ECARTES, la requete a
bel et bien REPONDU, et elle a repondu VIDE.

LE FOYER, LU AU DECOMPILE
-------------------------
`IdunBattle.Core.Services.BattleQuery$$GetMovableTilesFor` delegue a
`IdunBattle.Core.Services.MovementQuery$$GetMovableTilesFor`, qui ALLOUE l'`OrderedSet` puis
appelle `IdunBattle.Core.Services.MovementQuery$$FindAnyOrAllMoveableTiles`. La premiere
instruction utile de celle-ci est une garde a DEUX branches qui rend SANS RIEN REMPLIR --
l'`OrderedSet` deja alloue repart donc VIDE, sans erreur, sans exception :

    if ( (UnitFlagsComponent$$Has(unitFlags, 1) && ignoreUnitFlags == 0)
       || !UnitExtensions$$CanMove(unit) )   return;      // <- l'OrderedSet reste VIDE

et `MovableTilesInRangeSelector` passe `_ignoreFlags = 0` -- champ MESURE par le capteur #370, pas
suppose (`_ignoreFlags off=0x38 u8=0` sur les deux regimes). La premiere branche est donc ARMEE.

COMMENT LES DEUX BRANCHES SE SEPARENT -- SANS AUCUN NOUVEAU HOOK
-----------------------------------------------------------------
1. Le RPC `aiMovableTiles` appelle la MEME
   `MovementQuery$$GetMovableTilesFor(unit, ignoreUnitFlags: false, options)` -- meme surcharge,
   meme `ignoreUnitFlags` a `false`, donc la MEME garde. Avec `side="all"` il couvre AUSSI les
   unites que le joueur courant ne controle pas, et avec `overrideRange` il pose le meme range
   que `DSLFormulas$$Direct(GetNumberConstant(config, 0x16))`. C'est le capteur, deja charge.
2. Les deux branches n'ont pas la meme DUREE DE VIE :
     * `UnitFlagsComponent$$Has(unitFlags, 1)` depend de l'ETAT DE TOUR -- un flag qui se pose et
       se leve ;
     * `UnitExtensions$$CanMove` teste `BaseUnitComponent$$HasTrait(0x418)` et le dictionnaire de
       blocages `MovementComponent+0x50` (`MovementComponent$$IsAllowedToMove` = `Count == 0`) --
       deux etats PERSISTANTS qu'un `endturn` ne change pas.

Le probe BALAIE donc les tours SANS toucher a la geometrie, et lit a chaque etape le pool
(capteur #370), la requete nue (`aiMovableTiles`) et le compte d'events. Si le pool suit le tour,
c'est la branche FLAG ; s'il reste vide meme quand le caster a la main, c'est la branche
PERSISTANTE. S'il ne varie pas du tout, le probe REFUSE de conclure.

Le verdict est DERIVE des champs (`_branch_verdict`, teste 100 % offline par
`tests/engine/test_381_query_gate_offline.py`) -- jamais un texte ecrit d'avance.

ASCII only (cp1252). Usage (depuis scripts/python, host up, session deja warmee) :
    python probe_381_movable_tiles_query_gate.py
    python probe_381_movable_tiles_query_gate.py --steps 4 --json
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
    ENEMY2, FILLER_P, GRAFT, VICTIM, _pos, _view, controlled_by_current_player)
from probe_361_ramming_speed_explosion_batches import _gate_verdict          # noqa: E402
from probe_361_movable_tiles_selector import (                               # noqa: E402
    GEO_386, HP_PLAYER, _expected_events, _port_tile, _redrive, _tile_verdict,
    probe_predates_374)
from montage_361_attack_predictions_selector import (                        # noqa: E402
    ARMS, RAMMING_MOVE_RANGE, build_montage, dispose_montage)


def _r(sid, m, b, t=90):
    return (_rpc(sid, m, [b], timeout=t).get("result") or {})


# --------------------------------------------------------------------------------------------
# LE DECODEUR -- pur, derive des champs, teste offline
# --------------------------------------------------------------------------------------------

def _branch_verdict(steps: list) -> tuple:
    """Traduit le balayage de tours en (etiquette, phrase). TRI-ETAT a chaque niveau :

      * une etape dont le capteur n'est pas exploitable ne COMPTE PAS comme une mesure --
        elle bascule tout le run en `non-confronte`, jamais en « pool vide » ;
      * il faut avoir OBSERVE les deux regimes de tour pour trancher : un balayage qui ne voit
        le caster que d'un cote rend `regime-unique`, pas une conclusion ;
      * la correlation doit etre PARFAITE dans les deux sens. Un pool non vide alors que le
        caster n'a pas la main REFUTE la branche flag et se dit, il ne se lisse pas.
    """
    if not steps:
        return ("aucune-etape", "aucune etape mesuree -- rien n'est confronte")
    bad = [s for s in steps if s.get("tile_kind") in
           ("absent", "non-arme", "retour-illisible", "structure-inattendue",
            "sous-maillon-non-arme", "fenetre-vide") or s.get("probe_predates_374")]
    if bad:
        return ("non-confronte",
                "capteur non exploitable sur %d/%d etape(s) : %s. Rien n'est conclu du natif"
                % (len(bad), len(steps),
                   [(s["k"], s.get("tile_kind"), s.get("tile_phrase")) for s in bad][:2]))
    unusable = [s for s in steps if s.get("pool") is None or s.get("caster_has_turn") is None]
    if unusable:
        return ("non-confronte",
                "%d/%d etape(s) sans pool ou sans tour lisible : %s"
                % (len(unusable), len(steps), [s["k"] for s in unusable]))
    # `zero-appel` = l'arbre n'est pas evalue du tout : ce n'est PAS un pool vide, et melanger
    # les deux inverserait la conclusion (le decodeur #370 le dit deja, on ne le defait pas ici).
    amont = [s for s in steps if s.get("tile_kind") == "zero-appel"]
    if amont:
        return ("amont",
                "l'arbre `GetTileToMoveTo` n'est PAS EVALUE sur %d/%d etape(s) (k=%s) : la cause "
                "y est en AMONT du pool, pas dans la requete de mouvement"
                % (len(amont), len(steps), [s["k"] for s in amont]))
    with_turn = [s for s in steps if s["caster_has_turn"]]
    without = [s for s in steps if not s["caster_has_turn"]]
    if not with_turn or not without:
        return ("regime-unique",
                "le balayage n'a observe qu'UN regime de tour (avec la main : %d etape(s), sans : "
                "%d) -- les deux branches de la garde restent indiscernables. Augmenter --steps"
                % (len(with_turn), len(without)))
    full_with = [s for s in with_turn if s["pool"] > 0]
    empty_with = [s for s in with_turn if s["pool"] == 0]
    full_without = [s for s in without if s["pool"] > 0]
    empty_without = [s for s in without if s["pool"] == 0]
    if not empty_with and not full_without and full_with and empty_without:
        return ("branche-flag",
                "le pool suit EXACTEMENT le tour : non vide sur les %d etape(s) ou le caster a la "
                "main (k=%s, %s tuiles) et VIDE sur les %d ou il ne l'a pas (k=%s). La geometrie "
                "n'a pas bouge. => c'est la branche `UnitFlagsComponent$$Has(unitFlags, 1) && "
                "ignoreUnitFlags == 0` de `MovementQuery$$FindAnyOrAllMoveableTiles` qui rend, en "
                "laissant l'`OrderedSet` alloue VIDE"
                % (len(full_with), [s["k"] for s in full_with],
                   [s["pool"] for s in full_with], len(empty_without),
                   [s["k"] for s in empty_without]))
    if empty_with and not full_with:
        return ("branche-persistante",
                "le pool reste VIDE meme sur les %d etape(s) ou le caster a la main (k=%s) : le "
                "flag de tour n'explique pas ce vide. La cause est un etat PERSISTANT lu par "
                "`UnitExtensions$$CanMove` (`BaseUnitComponent$$HasTrait(0x418)` ou le "
                "dictionnaire de blocages `MovementComponent+0x50`)"
                % (len(empty_with), [s["k"] for s in empty_with]))
    return ("correlation-imparfaite",
            "le pool ne suit pas le tour de facon univoque : avec la main -> %d non vide / %d "
            "vide (k=%s) ; sans la main -> %d non vide / %d vide (k=%s). Une troisieme variable "
            "gouverne -- le probe REFUSE de trancher"
            % (len(full_with), len(empty_with), [s["k"] for s in empty_with],
               len(full_without), len(empty_without), [s["k"] for s in full_without]))


def _query_agreement(steps: list) -> tuple:
    """Le pool du capteur (DSL) et la requete NUE (`aiMovableTiles`, meme surcharge, meme
    `ignoreUnitFlags = false`) doivent s'accorder sur le VIDE. Un desaccord dirait que le vide
    vient du contexte DSL et non de la requete -- c'est la seule facon de le savoir sans hook.

    ⚠ STRICT : une etape sans requete lisible ne se laisse PAS ecarter du calcul. C'est le piege
    exact de `side="friendly"` -- ce filtre fait DISPARAITRE le caster des qu'il n'a pas la main,
    c'est-a-dire precisement dans le regime a mesurer, et il ne resterait alors que les etapes
    ou tout marche : un accord parfait, sur la moitie de la question. On rend `None`."""
    if not steps:
        return (None, "aucune etape ne porte a la fois le pool et la requete nue")
    muettes = [s for s in steps if s.get("pool") is None or s.get("query_tiles") is None]
    if muettes:
        return (None,
                "%d/%d etape(s) sans pool ou sans requete nue lisible (k=%s : %s) -- l'accord ne "
                "se calcule PAS sur le sous-ensemble qui repond, ce serait mesurer la moitie qui "
                "marche"
                % (len(muettes), len(steps), [s["k"] for s in muettes],
                   [(s.get("query") or {}).get("error") for s in muettes][:2]))
    rows = steps
    dis = [s for s in rows if (s["pool"] == 0) != (s["query_tiles"] == 0)]
    if dis:
        return (False,
                "DESACCORD sur %d/%d etape(s) entre le pool DSL et `aiMovableTiles` (meme "
                "surcharge, meme ignoreUnitFlags) : %s. Le vide ne viendrait donc PAS de la "
                "requete mais du contexte DSL"
                % (len(dis), len(rows),
                   [(s["k"], s["pool"], s["query_tiles"]) for s in dis]))
    return (True,
            "le pool DSL et `aiMovableTiles` s'accordent sur le vide/non-vide aux %d etape(s) "
            "(%s) => le vide est bien celui de `MovementQuery$$GetMovableTilesFor`, pas un effet "
            "du contexte DSL"
            % (len(rows), [(s["k"], s["pool"], s["query_tiles"]) for s in rows]))


# --------------------------------------------------------------------------------------------
# LA MESURE
# --------------------------------------------------------------------------------------------

def _movable_for(sid, rid, unit_id: int, override_range: int) -> dict:
    """La requete NUE, telle que le RPC l'emet : `MovementQuery$$GetMovableTilesFor(unit,
    ignoreUnitFlags: false, options{OverrideRange})`. `side="all"` est indispensable : le defaut
    (`friendly`) filtre sur `IsControlledByCurrentPlayer`, donc il ferait DISPARAITRE le caster
    exactement dans le regime qu'on veut mesurer, et son absence se lirait « 0 tuile »."""
    res = _r(sid, "aiMovableTiles",
             {"runnerId": rid, "side": "all", "overrideRange": int(override_range)}, 90)
    if not res or res.get("ok") is False:
        return {"listed": None, "tiles": None, "error": res.get("error") if res else "pas de retour"}
    for u in (res.get("units") or []):
        if int(u.get("unitId") or -1) == int(unit_id):
            return {"listed": True, "tiles": int(u.get("tileCount") or 0),
                    "error": u.get("err")}
    return {"listed": False, "tiles": None,
            "error": "unite %s absente du retour `aiMovableTiles` (side=all)" % unit_id}


def _step(sid, m, k: int) -> dict:
    """UNE etape du balayage : l'etat courant, sans rien deplacer."""
    caster, target = m.ids[GRAFT], m.ids[VICTIM]
    tile, dv, board = _port_tile(sid, m.runner, m.ids)
    o: dict = {"k": k, "port_tile": tile,
               "caster_pos": _pos(dv, caster), "target_pos": _pos(dv, target),
               "current_player": dv.get("currentPlayer"),
               "positions": {v: _pos(dv, m.ids[v]) for v in (GRAFT, FILLER_P, VICTIM, ENEMY2)}}
    ctrl = controlled_by_current_player(sid, m.runner)
    o["caster_has_turn"] = (caster in ctrl) if ctrl else None
    o["controlled"] = sorted(ctrl)
    o["query"] = _movable_for(sid, m.runner, caster, RAMMING_MOVE_RANGE)
    o["query_tiles"] = o["query"].get("tiles")
    o["expected"] = _expected_events(board, dv, tile, caster) if tile else None
    nat = _r(sid, "aiPlaybookPredict",
             {"runnerId": m.runner, "unitId": caster, "targetId": target,
              "abilityType": ARMS["ramming"].ability, "gateProbe": True, "tileProbe": True}, 150)
    o["native_error"] = nat.get("error")
    evs = nat.get("events") or []
    o["n_events"] = len(evs)
    self_ev = next((e for e in evs if e.get("targetId") == caster), None)
    o["self_will_be_kill"] = (self_ev or {}).get("willBeKill")
    o["gate_kind"], o["gate_phrase"] = _gate_verdict(nat.get("gateProbe"))
    tp = nat.get("tileProbe")
    o["tile_kind"], o["tile_phrase"] = _tile_verdict(tp)
    o["probe_predates_374"] = probe_predates_374(tp)
    nodes = (tp or {}).get("nodes") or []
    counts = [int(n.get("returnedCount", -1)) for n in nodes]
    o["pool_counts"] = counts
    # Le POOL de l'etape = le max des appels : un seul appel non vide suffit a etablir que la
    # requete a repondu. Un `-1` (refus de lire) ne doit PAS se moyenner avec un `0` mesure --
    # il est deja intercepte plus haut par `tile_kind`.
    o["pool"] = (max(counts) if counts and all(c >= 0 for c in counts) else None)
    return o


def run(seed: int = 37000, level: int = 8, steps: int = 4, verbose: bool = True,
        geometry: str = "386") -> dict:
    """`geometry` : `"386"` = la geometrie de `#386` sec.1 reproduite LITTERALEMENT (caster (1,4),
    tuile d'arrivee a distance 5 -- le bord de la portee de charge) ; `"montage"` = celle que
    `montage_361.scan_geometry` derive (caster plus proche, tuile a distance 4). Les deux existent
    pour que la conclusion ne tienne pas a UNE disposition : si le pool suivait le tour ici et pas
    la, la garde d'entree ne serait pas la seule variable."""
    sid = _resolve_session()
    arm = ARMS["ramming"]
    if geometry not in ("386", "montage"):
        raise ValueError("geometrie inconnue : %r (attendu 386 | montage)" % geometry)
    out: dict = {"seed": seed, "level": level, "steps": steps, "ability": arm.ability,
                 "hp_player": HP_PLAYER, "move_range": RAMMING_MOVE_RANGE,
                 "geometry_kind": geometry,
                 "geometry_386": {k: list(v) for k, v in GEO_386.items()}}
    m = None
    rows: list = []
    try:
        m = build_montage(sid, arm, seed=seed, level=level, hp_player=HP_PLAYER,
                          caster_max_dist=RAMMING_MOVE_RANGE)
        out["runner"] = m.runner
        if m.errors:
            out["error"] = "; ".join(m.errors)
            return out
        if geometry == "montage":
            out["geometry"] = {k: list(v) for k, v in (m.geometry or {}).items()}
        else:
            # La geometrie de reference (`#386` sec.1), reproduite LITTERALEMENT : c'est celle sur
            # laquelle les deux regimes ont ete lus, donc la seule ou l'ecart est attribuable.
            rd = _redrive(sid, m, GEO_386)
            if rd.get("error"):
                out["error"] = rd["error"]
                return out
            out["geometry"] = rd.get("geometry")
        from probe_353r1_ramming_speed_charge_tile import _endturn
        for k in range(max(1, int(steps))):
            rows.append(_step(sid, m, k))
            if k + 1 < max(1, int(steps)):
                _endturn(sid, m.runner)
    finally:
        if m is not None:
            dispose_montage(sid, m)
    out["steps_measured"] = rows

    # --- GARDES DE MONTAGE, avant tout verdict sur le natif
    moved = [r["k"] for r in rows if r.get("positions") != (rows[0].get("positions") if rows
                                                            else None)]
    out["geometry_stable"] = not moved
    closed = [r["k"] for r in rows if r.get("self_will_be_kill") is not True]
    exp_n = {r["k"]: (r.get("expected") or {}).get("n") for r in rows}
    out["expected_by_step"] = exp_n
    if out.get("error"):
        out["ok"] = False
        out["verdict"] = "MONTAGE KO : %s" % out["error"]
    elif moved:
        out["ok"] = False
        out["verdict"] = ("MONTAGE KO : la geometrie a bouge pendant le balayage (etapes %s) -- "
                          "l'ecart ne serait plus attribuable au seul tour" % moved)
    elif closed:
        out["ok"] = False
        out["verdict"] = ("BALAYAGE NON DISCRIMINANT : la gate `Any(selfPreds, p => p.WillBeKill)` "
                          "est FERMEE aux etapes %s (willBeKill=%s) -- l'arbre `GetTileToMoveTo` "
                          "n'y est meme pas construit. Baisser --hp-player"
                          % (closed, [rows[k].get("self_will_be_kill") for k in closed]))
    elif any((n or 0) <= 2 for n in exp_n.values()):
        out["ok"] = False
        out["verdict"] = ("BALAYAGE NON DISCRIMINANT : le voisinage de la tuile d'arrivee est vide "
                          "a une etape au moins (attendus par etape = %s) -- les batchs 3/4 "
                          "n'auraient rien a emettre" % exp_n)
    else:
        kind, phrase = _branch_verdict(rows)
        out["branch_kind"], out["branch_phrase"] = kind, phrase
        agree, agree_phrase = _query_agreement(rows)
        out["query_agreement"], out["query_agreement_phrase"] = agree, agree_phrase
        if kind in ("branche-flag", "branche-persistante") and agree is True:
            out["ok"] = True
            out["verdict"] = "BRANCHE TRANCHEE [%s] : %s. %s" % (kind, phrase, agree_phrase)
        elif kind in ("branche-flag", "branche-persistante"):
            out["ok"] = False
            out["verdict"] = ("BRANCHE [%s] MAIS LA REQUETE NUE NE CONFIRME PAS : %s"
                              % (kind, agree_phrase))
        else:
            out["ok"] = False
            out["verdict"] = "NON TRANCHE [%s] : %s" % (kind, phrase)

    if verbose:
        print("[381] runner=%s ability=%s niveau=%s geometrie=%s"
              % (out.get("runner"), arm.ability, level, json.dumps(out.get("geometry"))))
        for r in rows:
            exp = (r.get("expected") or {}).get("n")
            print("[381] k=%d joueur=%s caster_a_la_main=%s pool=%s (appels=%s) "
                  "requete_nue=%s events=%s attendu=%s"
                  % (r["k"], r.get("current_player"), r.get("caster_has_turn"), r.get("pool"),
                     r.get("pool_counts"), r.get("query_tiles"), r.get("n_events"), exp))
            print("        tuile_port=%s caster=%s gate[%s] tuile[%s]"
                  % (r.get("port_tile"), r.get("caster_pos"), r.get("gate_kind"),
                     r.get("tile_kind")))
            if (r.get("query") or {}).get("error"):
                print("        requete nue : %s" % r["query"]["error"])
        print("[381] %s" % out.get("verdict"))
        print("[381] -> %s" % ("OK" if out.get("ok") else "ECHEC"))
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--seed", type=int, default=37000)
    ap.add_argument("--level", type=int, default=8)
    ap.add_argument("--steps", type=int, default=4,
                    help="nombre d'etats de tour balayes (un `endturn` entre chacun)")
    ap.add_argument("--geometry", choices=("386", "montage"), default="386",
                    help="386 = geometrie de #386 sec.1 (tuile a distance 5) ; "
                         "montage = celle que scan_geometry derive (tuile a distance 4)")
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args()
    out = run(seed=a.seed, level=a.level, steps=a.steps, verbose=not a.json,
              geometry=a.geometry)
    if a.json:
        print(json.dumps(out, indent=1, default=str))
    return 0 if out.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
