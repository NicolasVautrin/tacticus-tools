"""#570-r5 -- LE RAYON DE SOUFFLE du deplacement d'ORDRE dans `load_state`, MESURE.

QUESTION BINAIRE, POSEE AVANT LA METHODE :

    « Que touche EXACTEMENT le comblement de l'`AbilityState` par le canal `unitAbilityStates`,
      joue AVANT la materialisation des effets au lieu d'APRES ? »

C'est la seule chose que le residu #570-r5 declarait non mesuree (« c'est un changement d'ORDRE
dont le rayon de souffle n'est pas mesure »). On ne l'estime pas : on charge le MEME etat live
DEUX FOIS -- une fois avec le comblement, une fois avec `_ability_state_with_channel` DESARME
(la fonction rendue identite, c'est-a-dire l'etat d'AVANT la tranche) -- et on DIFFE tout.

DEUX AXES, ET ILS DOIVENT REPONDRE DIFFEREMMENT :

  * les `StatsComponent.ctx` -- attendu **IDENTIQUES**. Le seed d'aval (`_load_passive_abilities`)
    ecrivait deja ce couple ; le deplacement ne fait que l'avancer. Si un ctx bougeait, le
    deplacement aurait change ce que le port lit APRES `load_state`, ce qui n'est PAS l'intention.
  * les INSTANCES d'effet -- attendu **DIFFERENTES**, et uniquement sur des unites que
    `combatSnapshot.unitConfig` ne decrit pas (`{"error": "config null"}`, c'est-a-dire les
    INVOQUEES). C'est la fenetre exacte du changement.

ANTI-VACUITE. Le probe REFUSE de conclure si aucune instance ne bouge (le montage n'aurait rien
mesure) et si le canal `unitAbilityStates` est muet. Les DEUX charges partent des MEMES payloads,
captures UNE SEULE FOIS : sans cela, deux captures successives suffiraient a fabriquer un diff.

    python probe_570r5_rayon_de_souffle.py [--board MC1_67] [--seed 777] [--state-file <ABS>]

ASCII only (cp1252).
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import probe_503r1_overwhelming_wrath_phase2 as P
import probe_570r1_ramshackle as R1


def _payloads(sid: int, rid: int) -> dict:
    """Les SIX canaux, captures UNE SEULE FOIS. Les deux charges les partagent : un diff ne peut
    donc pas venir d'une seconde lecture du jeu."""
    from engine.entities.pathfinding.board import Board
    bg = P.rpc(sid, "boardGraph", {"runnerId": rid}, 60)
    return {"board": Board(bg["tiles"], adjacency="evenq"),
            "dec": P.rpc(sid, "decisionView",
                         {"runnerId": rid, "maxRank": 1, "allAbilities": True}, 90),
            "ob": P.rpc(sid, "observeBattle", {"runnerId": rid}, 40),
            "snap": P.rpc(sid, "combatSnapshot", {"runnerId": rid}, 60),
            "tiles": P.rpc(sid, "tileMeta", {"runnerId": rid}, 60),
            "abst": P.rpc(sid, "unitAbilityStates", {"runnerId": rid}, 60)}


def _charger(pl: dict, comble: bool):
    """`load_state` sur les payloads figes. `comble=False` DESARME
    `snapshot._ability_state_with_channel` (rendu identite) = l'etat d'AVANT #570-r5."""
    from engine.runner import snapshot as SNAP
    orig = SNAP._ability_state_with_channel
    try:
        if not comble:
            SNAP._ability_state_with_channel = lambda cfg, chan: cfg
        return SNAP.load_state(pl["dec"], pl["ob"], pl["snap"], board=pl["board"],
                               tiles=pl["tiles"], ability_states=pl["abst"])
    finally:
        SNAP._ability_state_with_channel = orig


def _ctx_par_unite(state) -> dict:
    from engine.runner.components import StatsComponent
    out = {}
    for eid, e in state.entities.items():
        sc = e.get_component(StatsComponent)
        if sc is None or getattr(sc, "ctx", None) is None:
            continue
        c = sc.ctx
        out[int(eid)] = (getattr(c, "passive_ability_level", None),
                         getattr(c, "ability_variables_multiplier", None),
                         getattr(c, "active_ability_level", None))
    return out


def _instances(state) -> dict:
    """`{(porteur, rang): (classe, effect_type, ability_level, mult)}` -- le RANG, pas le type :
    deux instances du meme `EffectType` sur la meme unite existent, et les confondre masquerait
    l'une des deux."""
    out = {}
    for uid, effs in (state.effects.by_unit if state.effects is not None else {}).items():
        for i, e in enumerate(effs):
            out[(int(uid), i)] = (type(e).__name__, e.effect_type,
                                  e.ability_level, e.ability_variables_multiplier)
    return out


def _sans_config(pl: dict) -> set:
    """Les entites dont `combatSnapshot` ne decrit PAS la configuration -- c'est-a-dire les
    INVOQUEES (`SpawnUnitOperation` fabrique leurs stats par
    `IdunBattle.Entities.Behaviours.SpawnUnitOptions$$WithStatsFromConfig`, sans passer par une
    `UnitConfiguration`). Le capteur y rend litteralement `{"error": ...}`."""
    out = set()
    for su in ((pl["snap"] or {}).get("units") or []):
        uc = su.get("unitConfig")
        if su.get("entityId") is None:
            continue
        if not isinstance(uc, dict) or uc.get("abilityVariablesMultiplier") is None:
            out.add(int(su["entityId"]))
    return out


def mesurer(sid: int, nom: str, board: str, seed: str) -> dict:
    """Monte le MEME scenario que `probe_570r1_ramshackle` (un summon NATIF sur le plateau), puis
    charge deux fois."""
    state_path = P.LOGS / ("%s.json" % nom)
    rid = P.build(state_path, [
        "--seed", seed, "--board", board,
        "--p-units", R1.CASTER,
        "--a-units", "%s,%s" % (R1.ATT_BAS, R1.ATT_HAUT),
        "--place", "%s:2,3" % R1.CASTER,
        "--a-place", "%s:1,3" % R1.ATT_BAS, "--a-place", "%s:1,2" % R1.ATT_HAUT])
    out: dict = {"rid": rid}
    try:
        P.bind_transport(sid)
        dec0 = P.decision(sid, rid)
        mek = P.find(dec0, R1.CASTER)
        if mek is None:
            raise AssertionError("SCENARIO NON MONTE : %s absent du decisionView" % R1.CASTER)
        at = P.rpc(sid, "abilityTargets",
                   {"runnerId": rid, "unitId": int(mek["id"]),
                    "abilityType": R1.GROT_TANK}, 90) or {}
        row = next((u for u in (at.get("units") or [])
                    if u.get("unitId") == int(mek["id"])), None)
        ab = next((a for a in ((row or {}).get("abilities") or [])
                   if int(a.get("abilityId", -1)) == R1.GROT_TANK), {})
        tuiles = [t.get("targetId") for t in (ab.get("fromHere") or [])]
        if not tuiles:
            raise AssertionError("SCENARIO NON MONTE : aucune tuile de spawn SUR PLACE pour 1057")
        P.rpc(sid, "applyAction", {"runnerId": rid, "action": {
            "kind": "ability", "casterId": int(mek["id"]),
            "abilityType": R1.GROT_TANK, "targetId": int(tuiles[0])}}, 90)

        pl = _payloads(sid, rid)
        out["canal_unites"] = len(((pl["abst"] or {}).get("units") or []))
        out["sans_config"] = sorted(_sans_config(pl))
        a, b = _charger(pl, comble=True), _charger(pl, comble=False)
        out["seed_source"] = (a.ability_states_seed or {}).get("source")
        ca, cb = _ctx_par_unite(a), _ctx_par_unite(b)
        ia, ib = _instances(a), _instances(b)
        out["n_unites_ctx"] = len(ca)
        out["n_instances"] = len(ia)
        out["ctx_diff"] = {k: {"comble": ca[k], "desarme": cb.get(k)}
                           for k in sorted(set(ca) | set(cb)) if ca.get(k) != cb.get(k)}
        out["inst_diff"] = {"%d#%d" % k: {"comble": ia[k], "desarme": ib.get(k)}
                            for k in sorted(set(ia) | set(ib)) if ia.get(k) != ib.get(k)}
        return out
    finally:
        try:
            P.rpc(sid, "disposeRunner", {"runnerId": rid}, 20)   # MES runners, jamais les autres
        except Exception as e:                                   # pragma: no cover
            print("[warn] disposeRunner a echoue : %s" % e)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--state-file", default=None)
    ap.add_argument("--board", default=R1.BOARD)
    ap.add_argument("--seed", default="777")
    a = ap.parse_args()
    sid = P._session()
    nom = Path(a.state_file).stem if a.state_file else "probe_570r5_rayon"
    m = mesurer(sid, nom, a.board, a.seed)
    rc = 0

    print("[570-r5] canal `unitAbilityStates` : %s unite(s), source du seed = %r"
          % (m["canal_unites"], m["seed_source"]))
    print("[570-r5] entites SANS `unitConfig` exploitable (les INVOQUEES) : %s" % (m["sans_config"],))
    print("[570-r5] perimetre compare : %d ctx, %d instances d'effet"
          % (m["n_unites_ctx"], m["n_instances"]))

    print("\n[A] AXE CTX -- attendu IDENTIQUE (le seed d'aval l'ecrivait deja)")
    if m["ctx_diff"]:
        print("    ECHEC : %d ctx different(s) -- le deplacement a change ce que le port lit "
              "APRES `load_state`" % len(m["ctx_diff"]))
        print("    %s" % json.dumps(m["ctx_diff"], ensure_ascii=True))
        rc = 1
    else:
        print("    OK : 0 ctx different sur %d" % m["n_unites_ctx"])

    print("\n[B] AXE INSTANCES -- attendu DIFFERENT, et SEULEMENT sur les unites sans config")
    if not m["inst_diff"]:
        print("    ECHEC : AUCUNE instance ne bouge -- le montage n'a rien mesure (pas de summon "
              "sur le plateau, ou canal muet)")
        rc = 1
    else:
        print("    %d instance(s) touchee(s) sur %d :" % (len(m["inst_diff"]), m["n_instances"]))
        for k, v in m["inst_diff"].items():
            print("      %-10s comble=%s  desarme=%s" % (k, v["comble"], v["desarme"]))
        hors = sorted({int(k.split("#")[0]) for k in m["inst_diff"]} - set(m["sans_config"]))
        if hors:
            print("    ECHEC : %s porte(nt) une instance touchee alors que `combatSnapshot` decrit "
                  "leur configuration -- le comblement deborde de sa fenetre" % (hors,))
            rc = 1
        else:
            print("    OK : toutes les unites touchees sont dans %s" % (m["sans_config"],))

    print("\n[C] CE QUE CETTE MESURE NE COUVRE PAS")
    print("    * UN montage, donc UNE unite sans config. La borne ANALYTIQUE du volet")
    print("      OWNER-EFFECT est lue du gameconfig : 2 summons seulement portent une ability")
    print("      inscrite a `ABILITY_INIT_OWNER_EFFECTS` (orksGrotTank/Ramshackle,")
    print("      ultraSmnEliminator/CamoCloak). Le volet CAPTURE, lui, n'a pas de borne :")
    print("      tout effet que le natif pose SUR une invoquee -- ou dont une invoquee est la")
    print("      SOURCE -- passe par la meme table `abstate_by_id`.")
    print("    * les MACHINES OF WAR sont hors fenetre par construction (la passe 1 les saute ;")
    print("      leur `AbilityState` vient de `_machine_ability_state`, canal distinct).")
    print("\nVERDICT : %s" % ("OK" if rc == 0 else "ECHEC"))
    return rc


if __name__ == "__main__":
    sys.exit(main())
