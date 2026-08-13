"""PROBE #996 -- confrontation LIVE des trois no-op silencieuses portees par la tranche.

    python probe_996_no_op_silencieuses.py --ability 1185 --state-file <ABSOLU>.json

Trois abilities, TROIS BRAS chacune :

  A. **NATIF** -- `applyAction {kind: "ability"}` accepte, puis l'etat lu par `decisionView` /
     `combatSnapshot`. C'est l'oracle.
  B. **PORT, face CIBLAGE** -- `is_invalid_target(state, caster, target, ability)` doit rendre 0 la
     ou le natif a accepte. Une ability entree au registre SANS masque rendrait 0 elle aussi, donc
     ce bras seul ne prouve rien -- il est la pour attraper le cas INVERSE (un masque TROP strict
     qui refuserait ce que le natif accepte, regression que le port precedent, permissif, ne
     pouvait pas produire).
  C. **PORT, face EXECUTION** -- `execute_behaviour` rejoue sur l'etat d'AVANT le cast, et les
     effets poses (ou les attaques emises) sont confrontes a ceux du natif.

**LE POINT DE LA TRANCHE EST LE BRAS C**, et il faut le dire : avant ce port, les trois abilities
etaient ABSENTES d'`ABILITY_CLASSES`, donc le bras C n'existait pas -- le moteur repondait
`ported: False`, 0 degat, 0 effet, aucune erreur. Le bras A, lui, a toujours ete vert : le natif,
lui, fait son travail. C'est exactement ce qui rend ce mode de panne INVISIBLE en self-play.

MONTAGE -- LE VRAI PORTEUR, PAS UNE GREFFE. Les trois porteurs sont npc, et `--explicit-stats`
(#419-r1-tr12-r2) les rend spawnables AVEC leurs stats, leurs traits et leurs armes :
`IdunMetaLogic.UserProgress.UnitProgression$$GetNpcStats`. La greffe de `case-92` §5bis (remplacer
les `ActiveAbilities` d'un heros du pool) reste le recours de secours ; elle ne couvre PAS les
stats/traits/armes du vrai porteur, donc elle n'est pas utilisee ici.

GEOMETRIE -- ON DEPLACE, ON NE SE PLAINT PAS DU SPAWN. 1185 a `range = 3` (RANGE_FROM_CONFIG) : le
caster avance vers l'ennemi le plus proche avant de caster. 1010 exige `CasterHasNotMoved` ET une
cible ADJACENTE : le caster ne peut donc PAS avancer -- on passe des tours pour que l'IA adverse
vienne au contact. 1133 est un self-cast : rien a approcher.

ASCII only (cp1252).
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

PYDIR = Path(__file__).resolve().parent
BOARD = "MC1_67"

#: id -> (porteur npc + palier, allie du pool, ennemis, nom lisible)
SCENARIOS = {
    1185: {"nom": "ForwardObservers", "porteur": "tauNpc5StealthSuit:50", "allie": "tauCrisis",
           "ennemis": "necroWarden,necroDestroyer", "self_cast": False, "approche": "attendre"},
    1133: {"nom": "WarConstruct", "porteur": "eldarNpc4Wraithguard:50", "allie": "eldarFarseer",
           "ennemis": "necroWarden,necroDestroyer", "self_cast": True, "approche": "aucune"},
    1010: {"nom": "StormOfFlensingBlades", "porteur": "necroNpc2FlayedOne:50",
           "allie": "necroWarden", "ennemis": "tauCrisis,tauMarksman", "self_cast": False,
           "approche": "attendre"},
}

#: Effets attendus par le DECOMPILE (ce sont des NOMS : `decisionView` ne publie que le nom).
EFFETS_ATTENDUS = {
    1185: ("Markerlight", "ForwardObservers_DamageReduction"),
    1133: ("WarConstruct_CounterAttack", "IgnoreUsedAbilityInOverwatch"),
    1010: (),                      # 1010 ne pose RIEN : c'est une double attaque normale
}


def _unwrap(r):
    if isinstance(r, dict) and "result" in r and set(r) <= {"ok", "result", "error"}:
        return r["result"]
    return r


def _by_unit(dv):
    """TOUT vient de `decisionView.units[]`, et c'est une MESURE, pas une preference : les cles
    `position` / `teamId` que ce probe cherchait d'abord dans `combatSnapshot.units[]` n'y existent
    PAS (ses cles sont `entityId`, `unitConfig`, `stats`, `traits`, `unitFlags`, ...). Elles
    rendaient `None`, donc l'ensemble des positions ennemies etait VIDE et l'approche par
    deplacement ne bougeait jamais -- un montage muet qui se lisait « aucune cible legale ».
    `decisionView` publie `pos`, `team`, `hp`, `visualId` et `effects[].name`."""
    out = {}
    for u in (dv or {}).get("units") or []:
        uid = u.get("id")
        if uid is None:
            continue
        p = u.get("pos") or {}
        out[int(uid)] = {
            "vis": u.get("visualId"),
            "effects": sorted(e.get("name") for e in (u.get("effects") or []) if e.get("name")),
            "hp": u.get("hp"),
            "team": u.get("team"),
            "pos": (int(p["col"]), int(p["row"])) if p.get("col") is not None else None,
            "alive": bool(u.get("alive")),
        }
    return out


def _build(state_file, seed, sc):
    argv = [sys.executable, "rl_duel.py", "build", "--seed", str(seed), "--board", BOARD,
            "--explicit-stats", sc["porteur"],
            "--p-units", "%s,%s" % (sc["porteur"], sc["allie"]),
            "--a-units", sc["ennemis"], "--state-file", state_file, "--no-ai"]
    p = subprocess.run(argv, cwd=str(PYDIR), capture_output=True, text=True,
                       encoding="utf-8", errors="replace")
    if not Path(state_file).exists():
        print("[996] build KO : %s" % (p.stderr or p.stdout or "")[-800:])
        return None
    return json.loads(Path(state_file).read_text())["runnerId"]


def _cibles_legales(rep, unit_id, aid, immediat=True):
    """Deplie la reponse d'`abilityTargets` : `units[].abilities[].{targets, fromHere}`.

    Le RPC publie DEUX ensembles, et il dit lui-meme la difference dans `semantics` :
    `targets` = superset « ce tour, MOVE inclus » ; `fromHere` = legalite EXACTE du cast immediat.
    On prend `fromHere` (`immediat=True`) parce que le probe caste SANS bouger -- lire `targets`
    ferait passer pour confrontable un cast que le natif refuserait a la position courante."""
    cle = "fromHere" if immediat else "targets"
    for u in ((rep or {}).get("units") or []):
        if int(u.get("unitId", -1)) != int(unit_id):
            continue
        for ab in (u.get("abilities") or []):
            if int(ab.get("abilityId", -1)) != int(aid):
                continue
            out = []
            for t in (ab.get(cle) or []):
                if isinstance(t, dict):
                    v = t.get("entityId", t.get("id", t.get("unitId")))
                else:
                    v = t
                if v is not None:
                    out.append(int(v))
            return out
    return []


def _nom_regle(mask):
    """Un refus se RAPPORTE par son NOM de regle, jamais par son ordinal : `0x8000000` ne dit rien,
    `TargetIsInRange` dit ou chercher."""
    from engine.runner.abilities.targeting_rule import TargetingRule as TR
    noms = [r.name for r in TR if int(r) and bin(int(r)).count("1") == 1 and (int(mask) & int(r))]
    return "|".join(noms) or ("0x%x" % int(mask))


def _hexdist(a, b):
    """Distance hex du JEU -- `hexgeo.distance`, deja mirror de `CubeCoordinate$$Distance` et
    consomme par `engine.services.movement_query.get_distance`.

    ⚠ NE PAS LA REECRIRE : ce probe portait d'abord sa propre conversion cube en offset **odd-R**,
    alors que le jeu est en **odd-Q** (`hexgeo.to_cube` : `z = row - (col + (col & 1)) // 2`). La
    difference n'est pas academique -- elle rendait `dist((5,7),(6,8)) = 1` la ou le jeu lit `2`.
    L'approche s'arretait donc a une case NON adjacente, le cast etait refuse pour PORTEE, et le
    probe rapportait « aucune cible legale » : un montage muet qui se lit comme un verdict."""
    from hexgeo import distance as _d
    return _d(a, b)


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--ability", type=int, required=True, choices=sorted(SCENARIOS))
    ap.add_argument("--state-file", required=True, help="chemin ABSOLU, hors data/")
    ap.add_argument("--seed", type=int, default=777)
    ap.add_argument("--keep", action="store_true")
    ap.add_argument("--max-tours", type=int, default=6,
                    help="tours d'attente max quand l'approche est 'attendre' (1010)")
    a = ap.parse_args(argv)
    aid = a.ability
    sc = SCENARIOS[aid]

    import rl_collect_batch as R
    sid = R._resolve_session()
    w = _unwrap(R._rpc(sid, "warmupGameSingletons", [{}], timeout=180))
    if not (isinstance(w, dict) and w.get("ok")):
        print("[996] warmup KO : %s" % str(w)[:200])
        return 2

    def rpc(method, body=None, timeout=60):
        return _unwrap(R._rpc(sid, method, [body] if body is not None else [], timeout=timeout))

    rid = _build(a.state_file, a.seed, sc)
    if rid is None:
        return 2
    print("[996] %s (%d) -- runner %s, board %s, seed %s, porteur %s"
          % (sc["nom"], aid, rid, BOARD, a.seed, sc["porteur"]))
    rc = 0
    try:
        # --- localiser le caster ---------------------------------------------------------------
        snap0 = rpc("combatSnapshot", {"runnerId": rid})
        dv0 = rpc("decisionView", {"runnerId": rid})
        etat = _by_unit(dv0)
        vis = sc["porteur"].split(":")[0]
        caster = next((uid for uid, r in etat.items() if r["vis"] == vis), None)
        if caster is None:
            print("[996] KO -- porteur %s absent du snapshot (%s)"
                  % (vis, sorted({r['vis'] for r in etat.values()})))
            return 2

        # --- approche : ON DEPLACE, on ne se plaint jamais de la geometrie de spawn -------------
        # Le critere d'arret n'est pas une distance devinee : c'est le natif lui-meme
        # (`abilityTargets` -> `fromHere`, la legalite EXACTE du cast SANS bouger). Tant qu'il rend
        # vide, on avance le caster vers l'ennemi le plus proche PUIS on passe le tour.
        #
        # ⚠ AVANCER PUIS FINIR LE TOUR EST CE QUI REND 1010 CONFRONTABLE. Son masque porte
        # `CasterHasNotMoved` : caster APRES un deplacement serait refuse. Mais le flag `Moved` est
        # remis a zero au debut du tour suivant de l'unite, donc « j'avance ce tour, je caste au
        # suivant » satisfait les deux contraintes a la fois (adjacence ET caster immobile).
        if sc["approche"] == "attendre":
            for i in range(max(0, a.max_tours)):
                t = rpc("abilityTargets", {"runnerId": rid, "unitId": caster, "abilityType": aid})
                if _cibles_legales(t, caster, aid):
                    print("[996] approche : cible LEGALE (sans bouger) apres %d tour(s)" % i)
                    break
                etatI = _by_unit(rpc("decisionView", {"runnerId": rid}))
                mv = rpc("aiMovableTiles", {"runnerId": rid})
                tiles = []
                for u in ((mv or {}).get("units") or []):
                    if int(u.get("unitId", -1)) == int(caster):
                        tiles = [(int(x["col"]), int(x["row"])) for x in (u.get("tiles") or [])
                                 if x.get("col") is not None]
                pos_enn = [r["pos"] for r in etatI.values()
                           if r["team"] != etat[caster]["team"] and r["pos"] and r["alive"]]
                if tiles and pos_enn:
                    best = min(tiles, key=lambda t2: min(_hexdist(t2, e) for e in pos_enn))
                    rpc("applyAction", {"runnerId": rid, "action": {
                        "kind": "move", "unitId": caster,
                        "to": {"col": best[0], "row": best[1]}}}, 60)
                    print("[996] approche t%d : caster -> (%s,%s), dist min ennemi = %d"
                          % (i, best[0], best[1], min(_hexdist(best, e) for e in pos_enn)))
                elif not tiles:
                    print("[996] approche t%d : aucune tuile jouable pour u%s" % (i, caster))
                rpc("applyAction", {"runnerId": rid, "action": {"kind": "endturn"}}, 90)

        # --- l'etat d'AVANT le cast : c'est celui que le PORT rejouera -------------------------
        snapA = rpc("combatSnapshot", {"runnerId": rid})
        dvA = rpc("decisionView", {"runnerId": rid})
        obA = rpc("observeBattle", {"runnerId": rid})
        bg = rpc("boardGraph", {"runnerId": rid})
        avant = _by_unit(dvA)

        if sc["self_cast"]:
            target = caster
        else:
            t = rpc("abilityTargets", {"runnerId": rid, "unitId": caster, "abilityType": aid})
            cibles = _cibles_legales(t, caster, aid)
            if not cibles:
                # ⚠ `abilityTargets` N'EST PAS L'ORACLE, ET LE CONFONDRE FAIT RENONCER A TORT.
                # C'est un PREFILTRE de preview : mesure du 2026-08-13, il rend `fromHere = []`
                # pour 1185 comme pour 1010 alors que le caster est ADJACENT a un ennemi vivant --
                # et le cast, lui, passe (le natif ouvre son groupe `source: <ability>`). L'oracle
                # est ce que le natif FAIT quand on lui envoie le cast, pas ce que ce RPC annonce.
                # On continue donc sur l'ennemi VIVANT le plus proche, en le DISANT.
                mien = avant[caster]
                enn = [(uid, r) for uid, r in avant.items()
                       if r["team"] != mien["team"] and r["alive"] and r["pos"]]
                if not enn or not mien["pos"]:
                    print("[996] NON CONFRONTE -- plus d'ennemi vivant positionne apres l'approche")
                    return 3
                uid, r = min(enn, key=lambda kv: _hexdist(mien["pos"], kv[1]["pos"]))
                print("[996] `fromHere` VIDE (prefiltre de preview) -- cast quand meme sur u%s (%s)"
                      " a distance hex %d" % (uid, r["vis"], _hexdist(mien["pos"], r["pos"])))
                target = uid
            else:
                target = cibles[0]
        print("[996] cast : caster=u%s target=u%s" % (caster, target))

        # --- BRAS B : la face CIBLAGE du port, AVANT de laisser le natif trancher ---------------
        from engine.runner.snapshot import load_state
        from engine.entities.pathfinding.board import Board
        from engine.runner.abilities.handler import ABILITY_CLASSES
        from engine.runner.abilities.targeting import is_invalid_target
        state = load_state(dvA, obA, snapA, board=Board(bg["tiles"], adjacency="native_sym"))
        klass = ABILITY_CLASSES.get(aid)
        if klass is None:
            print("[996] KO -- %d ABSENTE d'ABILITY_CLASSES : l'execution serait un NO-OP" % aid)
            return 2
        ability = klass()
        final = klass.get_actual_target(state, caster, target)
        reason = is_invalid_target(state, int(caster), final, ability)

        # --- BRAS A : le NATIF ------------------------------------------------------------------
        res = rpc("applyAction", {"runnerId": rid, "action": {
            "kind": "ability", "casterId": caster, "targetId": target, "abilityType": aid}}, 60)
        a0 = (res.get("actions") or [{}])[0] if isinstance(res, dict) else {}
        if not (isinstance(res, dict) and res.get("ok") and a0.get("ok")):
            print("[996] RPC en erreur : %s" % str(res)[:300])
            return 2
        # ⚠ `ok: True` NE VEUT PAS DIRE « cast execute ». Mesure du 2026-08-13 : un cast REFUSE par
        # `IdunBattle.Operations.ActiveAbilityOperation$$ExecuteInternal` rend `ok: True`,
        # `mutated: False`, `changes: []`, `actionConsumed: False` -- et ouvre quand meme un
        # evenement `group` portant le nom de l'ability. Lire `ok` comme un accord ferait rougir le
        # port pour un refus que le natif partage. Le discriminant est `actionConsumed`, qui est
        # exactement ce que le decompile decrit (« un cast REFUSE ne mute rien et ne consomme PAS
        # l'activation »).
        natif_a_caste = bool(a0.get("actionConsumed") or a0.get("mutated"))
        snapB = rpc("combatSnapshot", {"runnerId": rid})
        dvB = rpc("decisionView", {"runnerId": rid})
        apres = _by_unit(dvB)

        if not natif_a_caste:
            # Le natif a REFUSE. Le seul verdict disponible est alors l'ACCORD SUR LE REFUS -- et
            # c'est un vrai verdict : un port permissif (masque absent) rendrait 0 ici.
            if reason:
                print("[996] ACCORD SUR LE REFUS -- natif REFUSE (actionConsumed=False, "
                      "changes=[]) et port REFUSE (reason=0x%x = %s). Face EXECUTION NON "
                      "CONFRONTEE : ce montage ne produit pas de cast accepte."
                      % (int(reason), _nom_regle(int(reason))))
                return 4
            print("[996] ROUGE bras B -- le natif REFUSE le cast, le port l'ACCEPTE : gate "
                  "PERMISSIF (c'est exactement le trou qu'un entrainement irait exploiter)")
            return 1
        if reason:
            print("[996] ROUGE bras B -- le natif EXECUTE le cast, le port le REFUSE "
                  "(reason=0x%x = %s). Masque TROP STRICT."
                  % (int(reason), _nom_regle(int(reason))))
            rc |= 1
        else:
            print("[996] bras B OK -- ciblage : natif EXECUTE, port ACCEPTE")

        # --- BRAS C : le PORT rejoue sur l'etat d'AVANT ------------------------------------------
        port_state = load_state(dvA, obA, snapA, board=Board(bg["tiles"], adjacency="native_sym"))
        out = klass().execute_behaviour(port_state, int(caster), int(final))
        print("[996] port execute_behaviour -> %s" % json.dumps(out, default=str)[:400])

        attendus = EFFETS_ATTENDUS[aid]
        if attendus:
            # NATIF : quels effets attendus sont APPARUS, et sur qui.
            natif_poses = set()
            for uid, r in apres.items():
                for nom in attendus:
                    if nom in r["effects"] and nom not in avant.get(uid, {}).get("effects", []):
                        natif_poses.add((uid, nom))
            # PORT : les memes, lus dans l'etat que `execute_behaviour` vient de muter.
            from engine.runner.components import has_effect_of_type
            from engine.entities.effect_type import EffectType
            port_poses = set()
            for uid in avant:
                for nom in attendus:
                    et = int(getattr(EffectType, nom))
                    if (has_effect_of_type(port_state, int(uid), et)
                            and nom not in avant.get(uid, {}).get("effects", [])):
                        port_poses.add((uid, nom))
            print("[996] NATIF poses = %s" % sorted(natif_poses))
            print("[996] PORT  poses = %s" % sorted(port_poses))
            if not natif_poses:
                print("[996] ROUGE -- le NATIF n'a pose AUCUN des effets attendus %s : le montage "
                      "ne mesure pas ce qu'il annonce (temoin NUL)" % (attendus,))
                rc |= 1
            elif natif_poses != port_poses:
                print("[996] ROUGE bras C -- desaccord natif/port : natif seul %s ; port seul %s"
                      % (sorted(natif_poses - port_poses), sorted(port_poses - natif_poses)))
                rc |= 1
            else:
                print("[996] bras C OK -- %d pose(s) d'effet, natif == port" % len(natif_poses))
        else:
            # 1010 : pas d'effet -- le discriminant est le NOMBRE d'attaques et la CIBLE frappee.
            hp_avant = avant.get(int(target), {}).get("hp")
            hp_apres = apres.get(int(target), {}).get("hp")
            atks = (out or {}).get("attacks") or []
            print("[996] NATIF hp cible %s -> %s ; PORT attaques emises = %d"
                  % (hp_avant, hp_apres, len(atks)))
            if hp_avant is None or hp_apres is None:
                print("[996] ROUGE -- PV de la cible NON MESURES (ni avant ni apres) : on ne rend "
                      "pas un zero pour une non-mesure")
                rc |= 1
            elif not (hp_apres < hp_avant):
                print("[996] ROUGE -- le NATIF n'a inflige AUCUN degat : temoin NUL, le montage ne "
                      "mesure pas la double attaque")
                rc |= 1
            elif len(atks) != 2:
                print("[996] ROUGE bras C -- le port a emis %d attaque(s) au lieu de 2" % len(atks))
                rc |= 1
            else:
                print("[996] bras C OK -- natif inflige des degats, port emet DEUX attaques")
        print("[996] rc=%d" % rc)
        return rc
    finally:
        if not a.keep:
            try:
                rpc("disposeRunner", {"runnerId": rid}, 30)
            except Exception as exc:                                   # noqa: BLE001
                print("[996] disposeRunner KO : %s" % str(exc)[:150])


if __name__ == "__main__":
    raise SystemExit(main())
