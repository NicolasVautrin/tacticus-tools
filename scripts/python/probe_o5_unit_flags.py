#!/usr/bin/env python
"""Probe O5 -- `UnitFlagsComponent` expose live par `combatSnapshot.unitFlags`.

LE GAP QUE CA FERME. Aucun RPC n'exposait les flags d'unite. La face DECISION offline devait donc
les DERIVER de leurs effets poseurs -- c'est ecrit noir sur blanc dans `Scene.prevent_overkill_by_id`
(« VIDE cote `from_predictor_sctx` -- AUCUN RPC n'expose `UnitFlagsComponent` (gap d'outillage
nomme, tache O5) ») et dans `docs/rl/case-195-prevent-overkill-decision.md`. La derivation est le
MEME invariant, pas une approximation -- mais c'est une SECONDE expression d'un fait qui existe
deja tel quel dans l'ECS, donc un fork de port en puissance : le jour ou un poseur IMPERATIF du
flag apparait (le composant a un `Add` public, appele aussi hors des effets), la derivation par
l'effet devient FAUSSE en silence.

CE QUI EST LU. `IdunBattle.Entities.Components.UnitFlagsComponent` range ses flags dans un
`idun.shared.collections.OrderedSet<UnitFlag>` @+0x10 (cf. son `$$.ctor`), auquel son `$$Has`
n'accede que par un appel d'interface FULLY-SHARED generique -- disposition non lisible de facon
fiable depuis Frida. Le hook n'y touche pas : il invoque la fonction NOMMEE que le jeu appelle
lui-meme, `IdunBattle.Entities.UnitExtensions$$HasFlag(unit, flag)` (litteralement la ligne
`uVar1 = UnitExtensions.HasFlag(defender, 0x13)` d'`ApplyTraitDamageLimitsToDamage`), une fois par
valeur d'enum -- valeurs LUES AU RUNTIME (`dumpEnum`), jamais recopiees en dur.

DEUX MESURES, ET LA SECONDE EST CELLE QUI DISCRIMINE VRAIMENT :

  A. ACCORD A TROIS SOURCES (`--part accord`) -- sur le MEME runner, `PreventOverkill` (=19) doit
     etre rendu identiquement par TROIS canaux INDEPENDANTS :
       1. `combatSnapshot.unitFlags`        <- le nouveau, lu de l'ECS via `HasFlag`
       2. la derivation par l'effet actif    <- `effects_prevent_overkill` (effet 1354), la voie
                                                que le port utilisait FAUTE DE MIEUX
       3. `preventOverkill` de l'event natif <- `DamagePredictionResult@+0xb3` (expose #190)
     Porteur `ultraTitus` (VRAI partout) et temoin `genesPrimus` (FAUX partout). Un accord a trois
     sur DEUX valeurs distinctes : c'est ce qui autorise a substituer la source 1 a la source 2.

  B. LE CANAL SUIT L'ETAT (`--part moved`) -- `Moved` (=0) sur la MEME unite, AVANT puis APRES un
     `MoveUnitOperation`. C'est la garde qui distingue un canal VIVANT d'une table figee au build :
     la mesure A, a elle seule, resterait verte si `unitFlags` etait un CONSTAT FIGE par unite
     (le porteur porte son flag des le deploiement, il ne bouge jamais). Ici la MEME entite change
     de valeur sous l'effet d'une operation -- aucune lecture figee ne peut passer.

ASCII only (cp1252). Usage :
  python probe_o5_unit_flags.py --part accord
  python probe_o5_unit_flags.py --part moved
  python probe_o5_unit_flags.py --part all
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

PYDIR = Path(__file__).resolve().parent
sys.path.insert(0, str(PYDIR))

from rl_collect_batch import _resolve_session, _rpc                            # noqa: E402
from engine.entities import EffectsState                                       # noqa: E402
from engine.runner.components import (effects_prevent_overkill,                # noqa: E402
                                      PREVENT_OVERKILL_EFFECT)
from probe_r34_overkill_decision import (build, view, by_visual, place_ring,    # noqa: E402
                                         playbook_events, move)
from probe_195_prevent_overkill_decision import (CARRIER, CONTROL, ATTACKER,    # noqa: E402
                                                 FILLER_P)

# Ids d'enum `IdunBattle.Entities.Enum.UnitFlag` (`enums.tsv`, build gqfc5mff6c). Le PROBE les cite
# en dur pour pouvoir CONFRONTER la table que le hook rend au runtime : si les deux divergent, c'est
# que l'enum a bouge, et on veut le voir ROUGE plutot que suivre silencieusement la nouvelle
# numerotation. Le HOOK, lui, ne code rien en dur (cf. `unitFlagTypes()`).
FLAG_MOVED = 0
FLAG_PREVENT_OVERKILL = 19


def _r(sid, m, b, t=90):
    return (_rpc(sid, m, [b], timeout=t).get("result") or {})


def snapshot(sid, rid) -> dict:
    return _r(sid, "combatSnapshot", {"runnerId": rid}, 120)


def flags_by_id(snap) -> dict:
    """{entityId: [ids de flags poses]} -- `None` conserve TEL QUEL (non mesure), jamais rabattu
    sur `[]` : c'est toute la difference entre « lu, aucun flag » et « capteur mort »."""
    return {u["entityId"]: u.get("unitFlags") for u in (snap.get("units") or [])
            if u.get("entityId") is not None}


def derive_by_effect(dv, snap, uid) -> bool:
    """Source 2 : la DERIVATION par l'effet actif -- exactement le chemin que
    `Scene.prevents_overkill` empruntait faute de canal ECS (`effects_prevent_overkill`, foyer
    unique). On monte l'`EffectsState` comme `step_context` le fait par pas."""
    units = dv.get("units") or []
    mult, ablvl = {}, {}
    for u in (snap.get("units") or []):
        uc = u.get("unitConfig") or {}
        if isinstance(uc, dict) and uc.get("abilityVariablesMultiplier") is not None:
            mult[u["entityId"]] = int(uc["abilityVariablesMultiplier"])
            ablvl[u["entityId"]] = int(uc.get("passiveAbilityLevel") or 0)
    eff = EffectsState.seed({u["id"]: (u.get("effects") or []) for u in units}, mult, ablvl)
    hp = next((u.get("hp") for u in units if int(u["id"]) == int(uid)), None)
    return effects_prevent_overkill(eff.active_effects(uid, {"hp": hp}))


# --------------------------------------------------------------------------------------------
# A. ACCORD A TROIS SOURCES sur `PreventOverkill` (=19)
# --------------------------------------------------------------------------------------------

def run_accord(seed: int = 50101, state_file=None, verbose=True) -> dict:
    sid = _resolve_session()
    sf = Path(state_file) if state_file else (PYDIR.parent.parent / "logs" / "po5accord.json")
    sf.parent.mkdir(parents=True, exist_ok=True)
    out: dict = {"seed": seed}
    rid = None
    try:
        rid = build(sf, seed, (ATTACKER, FILLER_P), (CARRIER, CONTROL),
                    hp_target=400, crit_spec="0,0", no_ai=True, block_target="0,0")
        dv = view(sid, rid)
        ids = {}
        for v in (ATTACKER, FILLER_P, CARRIER, CONTROL):
            u = by_visual(dv, v)
            if u is None:
                return {"error": "unite absente du build : %s" % v}
            ids[v] = int(u["id"])
        place_ring(sid, rid, ids, ATTACKER, (3, 4))
        dv = view(sid, rid)
        snap = snapshot(sid, rid)
        if not snap.get("ok"):
            return {"error": "combatSnapshot KO : %s" % snap.get("error")}

        # La table d'enum RENDUE PAR LE HOOK (lue au runtime) vs ce que le probe cite en dur.
        types = snap.get("unitFlagTypes")
        out["flag_types_present"] = isinstance(types, dict) and len(types) > 0
        out["flag_types_count"] = len(types or {})
        out["enum_agrees"] = bool(types) and \
            types.get("PreventOverkill") == FLAG_PREVENT_OVERKILL and \
            types.get("Moved") == FLAG_MOVED

        fbi = flags_by_id(snap)
        for vis in (CARRIER, CONTROL):
            uid = ids[vis]
            flags = fbi.get(uid)
            evs = playbook_events(sid, rid, ids[ATTACKER], uid)
            main = next((e for e in evs if e.get("targetId") == uid), None)
            out[vis] = {
                "entityId": uid,
                "flags_measured": flags is not None,
                "flags": flags,
                "src1_snapshot": (None if flags is None
                                  else bool(FLAG_PREVENT_OVERKILL in flags)),
                "src2_effect": derive_by_effect(dv, snap, uid),
                "src3_event": (None if main is None else bool(main.get("preventOverkill"))),
                "effect_id": PREVENT_OVERKILL_EFFECT,
            }
        out["distinct_values"] = sorted({out[v]["src1_snapshot"] for v in (CARRIER, CONTROL)
                                         if out[v]["src1_snapshot"] is not None},
                                        key=lambda b: int(b))
    finally:
        if rid is not None:
            _r(sid, "disposeRunner", {"runnerId": rid}, 30)
    if verbose:
        print(json.dumps(out, indent=2, sort_keys=True))
    return out


# --------------------------------------------------------------------------------------------
# B. LE CANAL SUIT L'ETAT : `Moved` (=0) avant / apres un MoveUnitOperation, MEME unite
# --------------------------------------------------------------------------------------------

def run_moved(seed: int = 50201, state_file=None, verbose=True) -> dict:
    sid = _resolve_session()
    sf = Path(state_file) if state_file else (PYDIR.parent.parent / "logs" / "po5moved.json")
    sf.parent.mkdir(parents=True, exist_ok=True)
    out: dict = {"seed": seed}
    rid = None
    try:
        rid = build(sf, seed, (ATTACKER, FILLER_P), (CARRIER, CONTROL),
                    hp_target=400, crit_spec="0,0", no_ai=True, block_target="0,0")
        dv = view(sid, rid)
        u = by_visual(dv, ATTACKER)
        if u is None:
            return {"error": "attaquant absent du build"}
        uid = int(u["id"])
        pos = u.get("pos") or {}
        out["entityId"] = uid
        out["pos_before"] = [pos.get("col"), pos.get("row")]

        # AUCUN mouvement encore joue -> `Moved` doit etre ABSENT.
        before = flags_by_id(snapshot(sid, rid)).get(uid)
        out["flags_before"] = before
        out["moved_before"] = (None if before is None else bool(FLAG_MOVED in before))

        # Deplacement REEL (`applyAction` kind=move -> `MoveUnitMessage` -> `MoveUnitOperation`),
        # le SEUL vecteur qui pose `UnitFlag.Moved`. Une tuile adjacente suffit ; on essaie le ring
        # jusqu'a ce qu'une destination soit acceptee (les voisines peuvent etre occupees/bloquees).
        moved_ok, dest = False, None
        c0, r0 = int(pos.get("col")), int(pos.get("row"))
        for dc, dr in ((1, 0), (-1, 0), (0, 1), (0, -1), (1, 1), (-1, -1), (1, -1), (-1, 1)):
            res = move(sid, rid, uid, c0 + dc, r0 + dr)
            if res.get("ok"):
                moved_ok, dest = True, [c0 + dc, r0 + dr]
                break
        out["move_applied"] = moved_ok
        out["pos_after"] = dest
        if not moved_ok:
            out["error"] = "aucune destination adjacente acceptee -- montage sans variable"
            return out

        after = flags_by_id(snapshot(sid, rid)).get(uid)
        out["flags_after"] = after
        out["moved_after"] = (None if after is None else bool(FLAG_MOVED in after))
        out["flips"] = (out["moved_before"] is False and out["moved_after"] is True)
    finally:
        if rid is not None:
            _r(sid, "disposeRunner", {"runnerId": rid}, 30)
    if verbose:
        print(json.dumps(out, indent=2, sort_keys=True))
    return out


# --------------------------------------------------------------------------------------------

def _verdict_accord(m: dict) -> tuple:
    """(ok, motif) -- les trois sources doivent CONCORDER sur chaque cible, et le couple
    porteur/temoin doit produire DEUX valeurs distinctes."""
    if m.get("error"):
        return False, m["error"]
    if not m.get("enum_agrees"):
        return False, ("la table d'enum rendue par le hook ne correspond plus a `enums.tsv` "
                       "(PreventOverkill=%s, Moved=%s attendus %d/%d)"
                       % ((m.get("flag_types_count") or 0) and "?", "?",
                          FLAG_PREVENT_OVERKILL, FLAG_MOVED))
    for vis in (CARRIER, CONTROL):
        d = m.get(vis) or {}
        if not d.get("flags_measured"):
            return False, "`unitFlags` non mesure sur %s (capteur absent ou irresolu)" % vis
        s1, s2, s3 = d.get("src1_snapshot"), d.get("src2_effect"), d.get("src3_event")
        if s3 is None:
            return False, "aucun event natif pour %s -- montage sans observable" % vis
        if not (s1 == s2 == s3):
            return False, ("desaccord sur %s : snapshot=%s effet=%s event=%s"
                           % (vis, s1, s2, s3))
    if len(m.get("distinct_values") or []) < 2:
        return False, ("une seule valeur observee (%s) : le canal ne se distingue pas d'un "
                       "canal mort" % (m.get("distinct_values"),))
    return True, ""


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--part", choices=("accord", "moved", "all"), default="all")
    ap.add_argument("--seed", type=int, default=None)
    ap.add_argument("--state-file", default=None)
    a = ap.parse_args()
    rc = 0
    if a.part in ("accord", "all"):
        m = run_accord(seed=a.seed or 50101, state_file=a.state_file)
        ok, why = _verdict_accord(m)
        print("ACCORD : %s %s" % ("OK" if ok else "ECHEC", why))
        rc |= 0 if ok else 1
    if a.part in ("moved", "all"):
        m = run_moved(seed=a.seed or 50201, state_file=a.state_file)
        ok = bool(m.get("flips"))
        print("MOVED  : %s (avant=%s apres=%s)"
              % ("OK" if ok else "ECHEC", m.get("moved_before"), m.get("moved_after")))
        rc |= 0 if ok else 1
    return rc


if __name__ == "__main__":
    sys.exit(main())
