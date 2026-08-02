"""#443-r2 -- la MESURE qui DISCRIMINE `onlyActive`, sur l'overwatch (1009).

LE CRITERE, AVANT LA METHODE
----------------------------
`IdunBattle.Entities.EntityExtensions$$HasEffect(e, state, T, onlyActive)` ne peut differer entre
`onlyActive = 0` et `onlyActive = 1` que si `e` PORTE un effet de type `T` dont
`EffectComponent.IsActive @+0x5c` est FAUX (`IdunBattle.Entities.EntityExtensions$$IsOwnerOfEffect`
n'a QUE cette lecture conditionnelle ; `IdunBattle.Entities.EntityExtensions$$IsTargetOfEffect`, lui,
exige `+0x5c` INCONDITIONNELLEMENT). Il faut donc un effet PRESENT-mais-INACTIF, et un call-site qui
l'interroge.

`probe_443r2_only_active_callsites.py` DERIVE ce couple du code : sur les call-sites `onlyActive`
portes, DEUX seulement interrogent un effectType dont un vecteur PORTE ecrit le flag -- et les deux
portent le MEME, `Overwatch_AutoAttack` (1009), avec des litteraux OPPOSES :

    playbook/suppressive_fire.py::_target_has_overwatch      onlyActive: null -> PRESENCE
    triggers/loki/reactivate_overwatch.py::matches           onlyActive: true -> ACTIVITE

Ce probe mesure le PREMIER, qui est confrontable a un oracle natif (`pairUtility`).

LE REGIME PRESENT-mais-INACTIF, ET COMMENT ON L'ATTEINT
-------------------------------------------------------
`IdunBattle.Entities.Effects.RangedAutoAttackEffect$$CreateHandleTriggerAbilitiesInternal` rend
TROIS `Triggered()` qui pilotent le flag de l'instance 1009. Le deuxieme est
`On(TurnStart_EffectActivation = 0x12) & IsTurnOf(owner@0x148) -> DeactivateEffect` : **pendant le
tour de son porteur, l'overwatch est DESACTIVE** -- il est present, et inerte.

C'est donc un `endturn`, rien de plus. MESURE (board MC1_67, seed 41504) :

    tour du CASTER   `decisionView` defaut [True]   `includeInactive` [True]     -> 1009 ACTIF
    tour du PORTEUR  `decisionView` defaut []       `includeInactive` [False]    -> 1009 INACTIF

Les DEUX canaux sont lus a chaque regime : l'etat est MESURE, jamais suppose. Et c'est le canal par
defaut qui rend le regime B interessant -- il DROPPE l'instance inerte, donc un port seede par lui
n'a rien a voir la ou le natif a quelque chose.

CE QUE LE PROBE ETABLIT
-----------------------
1. NATIF : `pairUtility` verse-t-il `SUPPRESSIVEFIRE_TargetWithOverwatch` dans le regime B ?
   OUI => `onlyActive` faux est CONFIRME PAR MESURE (le natif voit un overwatch inerte).
   NON => le litteral lu au decompile serait contredit -- ce serait le resultat le plus important.
2. PORT : rend-il la meme chose ? L'ecart eventuel se lit sur le CANAL DE SEED, pas sur le mirror.
3. CONTRE-EPREUVE : le substrat `has_effect` mute en `active_effects` (= ce que le port ferait si
   `onlyActive` valait 1). Critere = DEPLACEMENT par rapport au port NON MUTE :
      regime A (actif)   -> la mutation ne doit RIEN deplacer (les deux substrats coincident) ;
      regime B (inactif) -> la mutation DOIT faire tomber le terme.
   C'est exactement la contre-epreuve `CE3` de #443, qui NE MORDAIT PAS faute de ce regime.

Usage :
    python probe_443r2_only_active_overwatch.py --state-file <chemin ABSOLU> [--board B] [--seed S]

ASCII only. Garde jumelle : `scripts/python/tests/engine/test_443r2_only_active_overwatch_live.py`.
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

import hexgeo                                                    # noqa: E402
import probe_124_line_elevation_decision as P124                 # noqa: E402
from engine import battle_query as bq                            # noqa: E402
from engine import weights as W                                  # noqa: E402
from engine.ai import context as _ai_ctx                         # noqa: E402
from engine.entities.effect_type import EffectType               # noqa: E402
from engine.playbook import scene as _scene                      # noqa: E402
from engine.playbook.common import NORMAL_ATTACK_PLAYBOOK        # noqa: E402

BOARD = "MC1_67"
SEED = "41504"
CASTER = "emperNoiseMarine"      # trait `SuppressiveFire` (UnitTrait 1010) -> triggered 1044
TARGET = "eldarRanger"           # trait `Overwatch` -> effet 1009 sur elle-meme
OVERWATCH = int(EffectType.Overwatch_AutoAttack)             # 0x3f1 = 1009
KEY = "SUPPRESSIVEFIRE_TargetWithOverwatch"
EPS = 1e-4                       # Fix64 natif contre float du port
#: Distance de mesure : le predicat natif est NIE (`if (!AreEntitiesAdjacent(tile, target))`), donc
#: le terme n'entre QU'A DISTANCE. 3 = hors contact, dans la portee du bolter.
DIST = 3


class MontageError(RuntimeError):
    """Le montage ne s'installe pas -- la mesure n'a PAS eu lieu (jamais un vert silencieux)."""


# --------------------------------------------------------------------------- etat mesure

def overwatch_state(rpc, rid: int, uid: int) -> dict:
    """L'etat de l'instance 1009 du porteur, LU AUX DEUX CANAUX de `readEffectsByUnit`.

    `defaut` = ce que voit un port seede par `decisionView` nu (les `!active` sont DROPPES) ;
    `inactif_publie` = ce que voit `decision_view_seed_body` (canal `includeInactive`, qui publie
    l'instance avec son flag). La difference entre les deux EST la mesure du regime."""
    d0 = rpc("decisionView", {"runnerId": rid, "allAbilities": True, "maxRank": 32}, 180)
    d1 = rpc("decisionView", {"runnerId": rid, "allAbilities": True, "maxRank": 32,
                              "includeInactive": True}, 180)

    def flags(d):
        u = next((x for x in (d.get("units") or []) if x.get("id") == uid), None)
        return [bool(e.get("active")) for e in ((u or {}).get("effects") or [])
                if int(e.get("effectType") or -1) == OVERWATCH]

    f0, f1 = flags(d0), flags(d1)
    return {"defaut": f0, "include_inactive": f1,
            "present": bool(f1), "actif": bool(f1) and all(f1),
            "current_player": d0.get("currentPlayer"), "dv": d0}


# --------------------------------------------------------------------------- oracles

def pair_native(rpc, rid, cid, tgt, ab, tile) -> float:
    r = rpc("pairUtility", {"runnerId": rid, "unitId": cid, "targetId": tgt,
                            "abilityType": ab, "col": tile[0], "row": tile[1]}, 90)
    v = (r or {}).get("utility")
    if not isinstance(v, (int, float)):
        raise MontageError(f"pairUtility natif indisponible pour {tile} / cible {tgt}: {r}")
    return float(v)


def pair_port(ctx, ab, tgt, tile) -> float:
    cand = NORMAL_ATTACK_PLAYBOOK.calculate_action_utility(ctx, tile, tgt, ab)
    if cand is None:
        raise MontageError(f"le port ne produit AUCUNE action depuis {tile} sur {tgt}")
    return float(cand["u"])


def leaf_term(ctx, cid, ab, tgt, tile) -> float:
    """La face ATTACK ISOLEE (`engine.utilities.tile.triggered_abilities_attack_utility`) -- le
    terme SEUL, sans la composante de degat qui bruite l'utilite de paire."""
    from engine.utilities.tile import triggered_abilities_attack_utility
    return float(triggered_abilities_attack_utility(ctx, cid, ab, tgt, tile))


# --------------------------------------------------------------------------- mutation

class _SubstratMute:
    """CONTRE-EPREUVE : `battle_query.scene_has_effect` bascule de `EffectsState.has_effect`
    (mirror d'`onlyActive = 0`) a `EffectsState.active_effects` (mirror d'`onlyActive = 1`).

    C'est la MEME mutation que `CE3` de #443, appliquee au call-site OPPOSE. Elle porte sur le
    FOYER PARTAGE : depuis #441 les deux playbooks ATTACK qui posent ce predicat
    (`SuppressiveFire` 1044 et `Neuroparasite` 1183) passent par la, donc le rayon de souffle de la
    mutation est MESURE, pas herite -- il vaut exactement ces deux-la."""

    def __init__(self):
        self._saved = None

    def __enter__(self):
        self._saved = bq.scene_has_effect

        def mute(scene, uid, effect_type):
            eff = getattr(scene, "eff_state", None)
            if eff is not None:
                st = scene.unit_state(int(uid)) if hasattr(scene, "unit_state") else None
                for e in eff.active_effects(int(uid), st):
                    if int(e.effect_type or -1) == int(effect_type):
                        return True
            return getattr(scene, "is_effect_target", lambda *_a: None)(
                int(uid), int(effect_type)) is True

        bq.scene_has_effect = mute
        # `suppressive_fire` importe le MODULE (`from engine import battle_query as bq`), donc la
        # substitution d'attribut suffit -- verifiee par l'appelant, jamais supposee.
        return self

    def __exit__(self, *a):
        bq.scene_has_effect = self._saved
        return False


# --------------------------------------------------------------------------- montage

def _stage(sid, rpc, rid: int) -> dict:
    """Place le caster et la cible a `DIST` tuiles (regime NON adjacent, le seul ou le terme entre),
    puis rend les identites. Le drive est indispensable : au spawn les deux camps sont trop loin
    pour que la tuile de mesure soit acceptee par l'oracle."""
    elev, walk, _tid = P124._board(sid, rid)
    dv = rpc("decisionView", {"runnerId": rid, "allAbilities": True, "maxRank": 32}, 180)
    units = dv.get("units") or []
    me = next((u for u in units if u.get("ctrl") and u.get("visualId") == CASTER
               and u.get("alive")), None)
    if me is None:
        raise MontageError(f"montage NON INSTALLE : {CASTER} absent du roster controle")
    myplayer = me.get("owner")
    foe = next((u for u in units if u.get("owner") != myplayer and u.get("alive")
                and u.get("visualId") == TARGET), None)
    if foe is None:
        raise MontageError(f"montage NON INSTALLE : {TARGET} absent du roster adverse")

    cells = sorted(p for p, w in walk.items() if w and elev.get(p) is not None)
    if not cells:
        raise MontageError("montage NON INSTALLE : boardGraph sans tuile walkable")
    ctr = (sum(c for c, _ in cells) / len(cells), sum(r for _, r in cells) / len(cells))
    cpos = min(cells, key=lambda q: (q[0] - ctr[0]) ** 2 + (q[1] - ctr[1]) ** 2)
    ring = [p for p in cells if hexgeo.distance(cpos, p) == DIST
            and abs((elev.get(p) or 0) - (elev.get(cpos) or 0)) < 2]
    if not ring:
        raise MontageError(f"montage NON INSTALLE : {cpos} n'a aucune tuile a distance {DIST}")
    tpos = ring[0]
    if not P124._drive_to(sid, rid, walk, elev, {me["id"]: cpos, foe["id"]: tpos}):
        _dv, pos = P124._positions(sid, rid)
        raise MontageError(f"montage NON INSTALLE : placement incomplet -- voulu "
                           f"{ {me['id']: cpos, foe['id']: tpos} }, obtenu "
                           f"{ {u: pos.get(u) for u in (me['id'], foe['id'])} }")
    P124._give_turn_back(sid, rid, myplayer)
    dv = rpc("decisionView", {"runnerId": rid, "allAbilities": True, "maxRank": 32}, 180)
    ab = next((a["id"] for u in (dv.get("units") or []) if u.get("id") == me["id"]
               for a in (u.get("abilities") or []) if a.get("kind") == "normal"), None)
    if ab is None:
        raise MontageError(f"montage NON INSTALLE : aucune attaque normale sur {CASTER}")
    return {"rid": rid, "cid": me["id"], "tgt": foe["id"], "player": myplayer,
            "tile": cpos, "tpos": tpos, "ab": ab}


def _ctx_for(rpc, rid: int, cid: int, seed_inactive: bool):
    """Contexte de decision du port. `seed_inactive` choisit le CANAL DE CAPTURE -- c'est la seule
    difference entre les deux, et elle decide de ce que `EffectsState` contient.

    `decision_view_seed_body` (canal `includeInactive`) est la porte NOMMEE du seed cote COMBAT ;
    la face DECISION, elle, seede son `EffectsState` depuis le `dv` que son appelant lui donne
    (`playbook/scene.py::step_context`). Passer les deux, c'est mesurer ce que le canal decide."""
    body = {"runnerId": rid, "allAbilities": True, "maxRank": 32}
    if seed_inactive:
        body["includeInactive"] = True
    dv = rpc("decisionView", body, 180)
    mov = rpc("aiMovableTiles", {"runnerId": rid}, 60)
    mbu = {u.get("unitId"): u for u in (mov.get("units") or [])}
    return _ai_ctx.build(rpc, rid, dv, mbu, cid, W.load(), _scene.build_predictor(rpc, rid))


def measure(rpc, case: dict, regime: str) -> dict:
    """Une ligne de mesure : etat 1009 atteste, natif, port (2 canaux), port mute (2 canaux)."""
    st = overwatch_state(rpc, case["rid"], case["tgt"])
    nat = pair_native(rpc, case["rid"], case["cid"], case["tgt"], case["ab"], case["tile"])
    row = {"regime": regime, "ow": st, "native": nat}
    for canal, seed_inactive in (("defaut", False), ("includeInactive", True)):
        ctx = _ctx_for(rpc, case["rid"], case["cid"], seed_inactive)
        port = pair_port(ctx, case["ab"], case["tgt"], case["tile"])
        leaf = leaf_term(ctx, case["cid"], case["ab"], case["tgt"], case["tile"])
        with _SubstratMute():
            muted = pair_port(ctx, case["ab"], case["tgt"], case["tile"])
            muted_leaf = leaf_term(ctx, case["cid"], case["ab"], case["tgt"], case["tile"])
        row[canal] = {"port": port, "leaf": leaf, "muted": muted, "muted_leaf": muted_leaf,
                      "poids": float(ctx.wt.triggered(KEY))}
    return row


# --------------------------------------------------------------------------- rayon de souffle

def blast_radius(rpc, rid: int) -> dict:
    """Ce que la bascule du canal AJOUTERAIT au substrat de la face DECISION, sur CET etat.

    Mesure, pas deduction : on lit les deux canaux et on DIFFERENCE, par unite et par effectType.
    Un effet ajoute n'entre dans AUCUN nombre passant par `EffectsState.active_effects` (il y est
    filtre par le flag) ; il n'est vu que des lecteurs `has_effect` -- c'est-a-dire exactement les
    mirrors d'un `onlyActive` FAUX, qui DOIVENT le voir."""
    d0 = rpc("decisionView", {"runnerId": rid, "allAbilities": True, "maxRank": 32}, 180)
    d1 = rpc("decisionView", {"runnerId": rid, "allAbilities": True, "maxRank": 32,
                              "includeInactive": True}, 180)

    def index(d):
        out = {}
        for u in (d.get("units") or []) + (d.get("mows") or []):
            uid = u.get("id") if u.get("id") is not None else u.get("casterId")
            out[uid] = [(int(e.get("effectType") or -1), bool(e.get("active")), e.get("name"))
                        for e in (u.get("effects") or [])]
        return out

    i0, i1 = index(d0), index(d1)
    ajouts = {}
    for uid, effs in i1.items():
        base = i0.get(uid) or []
        for t, act, nom in effs:
            if (t, act, nom) not in base:
                ajouts.setdefault(uid, []).append((t, act, nom))
    par_type = {}
    for uid, lst in ajouts.items():
        for t, act, nom in lst:
            par_type.setdefault((t, nom), 0)
            par_type[(t, nom)] += 1
    return {"entrees_defaut": sum(len(v) for v in i0.values()),
            "entrees_include": sum(len(v) for v in i1.values()),
            "unites_touchees": len(ajouts), "par_type": par_type}


# --------------------------------------------------------------------------- CLI

def _build(state_file: str, board: str, seed: str, roster: str = None) -> int:
    p_units, a_units = (roster.split("|", 1) if roster else (CASTER, TARGET))
    argv = [sys.executable, "rl_duel.py", "build", "--seed", seed, "--state-file", state_file,
            "--board", board, "--p-units", p_units, "--a-units", a_units,
            "--hp-target", "90000", "--hp-player", "90000"]
    p = subprocess.run(argv, cwd=_HERE, capture_output=True, text=True,
                       encoding="utf-8", errors="replace")
    if p.returncode != 0:
        raise MontageError(f"rl_duel build a echoue (rc={p.returncode}) : "
                           f"{(p.stderr or p.stdout or '')[-800:]}")
    return int(json.load(open(state_file, encoding="utf-8"))["runnerId"])


def _print(row: dict) -> None:
    st = row["ow"]
    print("  regime %-8s | 1009 defaut=%-7s includeInactive=%-7s -> present=%s actif=%s "
          "| joueur courant=%s" % (row["regime"], st["defaut"], st["include_inactive"],
                                   st["present"], st["actif"], st["current_player"]))
    print("      natif  pairUtility = %.6f" % row["native"])
    for canal in ("defaut", "includeInactive"):
        c = row[canal]
        print("      port[%-15s] pair=%.6f (d=%+.6f)  terme=%.6f | MUTE pair=%.6f terme=%.6f "
              "-> deplacement=%+.6f" % (canal, c["port"], c["port"] - row["native"], c["leaf"],
                                        c["muted"], c["muted_leaf"], c["muted_leaf"] - c["leaf"]))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--state-file", required=True, help="chemin ABSOLU du state-file")
    ap.add_argument("--board", default=BOARD)
    ap.add_argument("--seed", default=SEED)
    ap.add_argument("--keep", action="store_true")
    ap.add_argument("--blast", action="store_true",
                    help="mesure ce que la bascule du canal AJOUTERAIT au substrat de la decision")
    ap.add_argument("--roster", default=None,
                    help="rosters explicites `p-units|a-units` (rayon de souffle sur 5v5)")
    args = ap.parse_args()

    from rl_collect_batch import _resolve_session, _rpc
    sid = _resolve_session()

    def rpc(method, body=None, timeout=90):
        r = _rpc(sid, method, [body] if body is not None else [], timeout=timeout)
        return r["result"] if isinstance(r, dict) and "result" in r else r

    rid = _build(args.state_file, args.board, args.seed, args.roster)
    try:
        case = _stage(sid, rpc, rid)
        print("runner %d | board %s seed %s | %s u%d @%s vs %s u%d @%s (dist %d) | ability %d"
              % (rid, args.board, args.seed, CASTER, case["cid"], case["tile"], TARGET,
                 case["tgt"], case["tpos"], hexgeo.distance(case["tile"], case["tpos"]),
                 case["ab"]))

        rows = []
        # REGIME A -- tour du CASTER : l'overwatch de la cible est ARME (`On(0x12)` l'a active).
        a = measure(rpc, case, "A-actif")
        rows.append(a)
        _print(a)
        if not a["ow"]["actif"]:
            raise MontageError("montage DEGENERE : le regime A n'a pas d'overwatch ACTIF "
                               f"-- {a['ow']['defaut']} / {a['ow']['include_inactive']}")

        # REGIME B -- tour du PORTEUR : `On(0x12) & IsTurnOf(owner) -> DeactivateEffect`.
        r = rpc("applyAction", {"runnerId": rid, "action": {"kind": "endturn"}}, 120) or {}
        if not r.get("ok"):
            raise MontageError(f"montage NON INSTALLE : endturn refuse -- {r}")
        b = measure(rpc, case, "B-inactif")
        rows.append(b)
        _print(b)
        if not (b["ow"]["present"] and not b["ow"]["actif"]):
            raise MontageError("montage DEGENERE : le regime B n'est pas PRESENT-mais-INACTIF "
                               f"-- {b['ow']['defaut']} / {b['ow']['include_inactive']}")

        poids = a["defaut"]["poids"]
        print("\n  poids BC `%s` = %s" % (KEY, poids))
        if not poids:
            raise MontageError(f"le BC servi porte {KEY}={poids} -- un poids nul ne discrimine rien")
        print("  VERDICT natif : le terme est verse en regime A=%s, en regime B=%s"
              % (abs(a["native"]) > EPS, abs(b["native"]) > EPS))
        print("  => `onlyActive` faux %s par la mesure (le natif %s un overwatch INERTE)"
              % ("CONFIRME" if abs(b["native"]) > EPS else "CONTREDIT",
                 "VOIT" if abs(b["native"]) > EPS else "IGNORE"))
        for canal in ("defaut", "includeInactive"):
            dep_a = a[canal]["muted_leaf"] - a[canal]["leaf"]
            dep_b = b[canal]["muted_leaf"] - b[canal]["leaf"]
            print("  contre-epreuve [seed %-15s] deplacement du terme : A=%+.6f  B=%+.6f  %s"
                  % (canal, dep_a, dep_b,
                     "MORD" if abs(dep_b) > EPS else "NE MORD PAS"))

        if args.blast:
            br = blast_radius(rpc, rid)
            print("\n  RAYON DE SOUFFLE de la bascule de canal (etat courant, regime B) :")
            print("    entrees d'effet : defaut=%d  includeInactive=%d  (+%d)"
                  % (br["entrees_defaut"], br["entrees_include"],
                     br["entrees_include"] - br["entrees_defaut"]))
            print("    unites touchees : %d" % br["unites_touchees"])
            for (t, nom), n in sorted(br["par_type"].items(), key=lambda kv: -kv[1]):
                print("      %-6s %-38s x%d" % (t, nom, n))
    finally:
        if not args.keep:
            rpc("disposeRunner", {"runnerId": rid}, 30)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
