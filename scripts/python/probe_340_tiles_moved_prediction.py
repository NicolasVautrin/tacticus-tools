"""probe #340 (residu #322-r2) -- FACE PREDICTION de `TilesMovedThisTurn` : ce que l'IA PREVOIT pour
une unite qui a DEJA bouge.

LE CRITERE, pose AVANT toute methode
------------------------------------
Question binaire : **la prediction du port suit-elle le natif sur les DEUX termes de
`TilesMovedThisTurn`, et pas seulement sur celui que la simulation fabrique ?**

Un seul et meme bras les separe, parce qu'il mesure la MEME tuile d'attaque de part et d'autre du
MEME deplacement :

  PHASE A -- AVANT le pas. L'unite est sur `start`, on predit l'attaque DEPUIS `step_to`. Le natif
      voit `0 (reel) + k (pas simule)`. Un port qui ne lit que le pas simule tombe JUSTE ici : c'est
      le regime des 85 paires de #322, et c'est pour cela qu'il n'avait rien revele.
  PHASE B -- APRES le pas. L'unite EST sur `step_to`, on predit la MEME attaque DEPUIS `step_to`.
      Le natif voit `k (reel) + 0 (pas simule)` -- la MEME valeur, par l'autre terme. Un port qui ne
      lit pas le compteur reel rend le bonus a ZERO et l'ecart est ENTIER.

L'invariant qui rend le bras probant : **NATIF(A) == NATIF(B)**, tuile pour tuile. Les deux termes
sont les deux moities d'une meme somme ; le port doit reproduire les deux.

CE QUE LE DECOMPILE DIT (relu sur `rnca9r7q6c`)
----------------------------------------------
    IdunBattle.Entities.Formulas.TilesMovedThisTurnFormula$$Calculate:
        comp = GetComponent<ActorStatisticsComponent>(entite selectionnee);
        return *(uint *)(comp + 0xf0);

    IdunBattle.Entities.UnitExtensions$$RecordTilesMoved(unit, tiles, state):
        if ((int)tiles < 1) return;
        comp[0xec] += tiles;   comp[0xf0] += tiles;

    IdunBattle.Operations.SimulateEffectsOperation$$DoActionInSimulatedTile:
        local_108 = comp[0xec];  local_104 = comp[0xf0];    // SAUVEGARDE avant l'action simulee
        ... SetMovedFlag -> l'action (dont MoveUnitOperation branche SIMULATION) ...
        comp[0xec] = local_108;  comp[0xf0] = local_104;    // RESTAURE apres

    IdunBattle.Operations.SimulateEffectsOperation$$DoActionInSimulatedOnSameTile:
        ne touche PAS l'ActorStatisticsComponent -- aucune sauvegarde, aucune ecriture.

C'est CETTE sauvegarde/restauration qui autorise le modele a deux termes : le compteur reel n'est
JAMAIS pollue par les tuiles candidates deja evaluees, donc `n_predit = reel + pas simule` -- et une
prediction depuis la tuile courante rend le compteur reel TOUT NU.

MONTAGE (herite de #335, dont le harnais est reutilise TEL QUEL)
---------------------------------------------------------------
  * `votanChampion` (Kimm) est HORS du seed BC -> injection catalogue.
  * geometrie DRIVEE (`arrange`), puis `reach_my_turn(force_cycle=True)` OBLIGATOIRE : les `place()`
    du montage sont de vrais `MoveUnitOperation` et ENREGISTRENT des tuiles ; sans le cycle complet
    (`EndTurnOperation` -> `ResetThisTurn` -> `+0xf0 = 0`) le compteur du MONTAGE entrerait dans la
    mesure et l'ecart se lirait comme un bug de port.
  * SNAPSHOT **avant** le pas, pas REJOUE offline (`MoveUnitMessage`) : le compteur est pose PAR LE
    MOTEUR, jamais declare.
  * le port est interroge par `engine.ai.state_bridge.build_from_state` -- la voie `Scene.from_state`,
    celle que la chaine de decision offline emprunte reellement.
  * l'attaque normale a DEUX ids : concret cote live (`NormalAttackType@0x28`, per-unit) et
    synthetique cote offline (`state_bridge.NORMAL_ATTACK_ID` = 17). On passe le bon a chaque face.

CE QUE CE PROBE NE COUVRE PAS, ET POURQUOI C'EST STRUCTUREL
-----------------------------------------------------------
Le regime `reel > 0` ET `pas simule > 0` n'est PAS atteignable : une unite qui a joue son
deplacement ne peut plus bouger, donc `aiPlaybookPredict` ne rend plus rien depuis une autre tuile
(mesure : `None` sur toutes les tuiles non courantes en phase B). La somme des deux termes n'est
donc confrontee que terme par terme -- ce que le mirror `real + (Count - 1)` couvre par
construction.

Usage :
    python probe_340_tiles_moved_prediction.py                       # MC1_67 / 909, pas de 1 et 2
    python probe_340_tiles_moved_prediction.py --board C1_25 --seed 31337 --steps 1,3
ASCII only.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import hexgeo
import probe_335_tiles_moved_combat as P335
from engine.runner.components import unit_tiles_moved_this_turn

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
LOGS = ROOT / "logs"
# State-file PROPRE a ce probe (discipline runner : un state-file par probe, jamais partage).
STATE = LOGS / "rs_340_tiles_moved_pred.json"
# Nombre MINIMAL de tuiles auxquelles le natif doit repondre en phase A pour que le bras compte.
MIN_TILES_A = 2


def _rpc(method, body=None, timeout_ms=90000):
    return P335._rpc(method, body, timeout_ms)


# ---------------------------------------------------------------- cote NATIF
def predict_native(rid: int, caster: int, target: int, ab: int, tile) -> tuple | None:
    """Prediction NATIVE de la paire DEPUIS `tile` -- `aiPlaybookPredict`, le meme oracle que
    `engine_agreement_stages.StageProbe._native_events`. Passer `col`/`row` fait evaluer le natif A
    LA TUILE CANDIDATE (`GetUnitPositionAtTile`), donc par
    `SimulateEffectsOperation$$DoActionInSimulatedTile` quand elle differe de la courante et par
    `$$DoActionInSimulatedOnSameTile` quand elle l'est.
    Rend `(healthDmgMin, healthDmgMax)` de l'event porte par `target`, ou None (le natif ne prevoit
    RIEN depuis cette tuile -- typiquement hors de son movable set, ou deplacement deja consomme)."""
    resp = _rpc("aiPlaybookPredict",
                {"runnerId": rid, "unitId": caster, "targetId": target, "abilityType": int(ab),
                 "col": int(tile[0]), "row": int(tile[1])}, 60000)
    if not (isinstance(resp, dict) and resp.get("ok")):
        return None
    evs = resp.get("events") or []
    if not evs:
        return None
    main = next((e for e in evs if e.get("targetId") == target), evs[0])
    lo, hi = main.get("healthDmgMin"), main.get("healthDmgMax")
    return None if lo is None else (int(lo), int(hi))


# ---------------------------------------------------------------- cote PORT
def _port_ctx(state, caster: int):
    from engine.ai.state_bridge import build_from_state
    return build_from_state(state, caster)


def _playbook_for(ctx, ab: int):
    from engine.playbook import get_playbook_or_default
    from engine.playbook.common import NORMAL_ATTACK_PLAYBOOK
    return NORMAL_ATTACK_PLAYBOOK if ab in ctx.normal_ids else get_playbook_or_default(ab)


def port_ability_id(ctx) -> int:
    """L'id que le PORT emploie pour l'attaque normale. `build_from_state` synthetise
    `state_bridge.NORMAL_ATTACK_ID` (17) la ou le live rend l'id CONCRET per-unit
    (`NormalAttackType@0x28`) : deux expressions de la MEME attaque, a ne pas confondre."""
    from engine.ai.state_bridge import NORMAL_ATTACK_ID
    return NORMAL_ATTACK_ID if NORMAL_ATTACK_ID in ctx.normal_ids else next(iter(ctx.normal_ids))


def predict_port(ctx, target: int, ab: int, tile) -> tuple | None:
    """Prediction du PORT pour la meme paire depuis la meme tuile. `(min, max)` ou None."""
    pb = _playbook_for(ctx, ab)
    evs = pb.make_damage_predictions(ctx, (int(tile[0]), int(tile[1])), target, int(ab)) or []
    main = next((e for e in evs if e.target == target), evs[0] if evs else None)
    if main is None:
        return None
    f = main.composite_fields()
    lo, hi = f.get("healthDmgMin"), f.get("healthDmgMax")
    return None if lo is None else (int(lo), int(hi))


def port_utility(ctx, target: int, ab: int, tile):
    """Utilite du port pour l'action (ability, cible, tuile) -- ce que l'argmax de decision compare."""
    pb = _playbook_for(ctx, ab)
    act = pb.calculate_action_utility(ctx, (int(tile[0]), int(tile[1])), target, int(ab))
    return None if act is None else float(act["u_full"])


def _pred_tiles_moved(ctx, caster: int, tile) -> int:
    from engine.playbook.prediction._shared import prediction_tiles_moved_this_turn
    return prediction_tiles_moved_this_turn(ctx.scene, caster, (int(tile[0]), int(tile[1])))


def _decision(state, caster: int):
    """L'ACTION que le spine de decision retient -- `DefaultAiUnitTactic.calculate_next_action`,
    donc l'argmax COMPLET (toutes abilities, toutes cibles, toutes tuiles, mouvements compris), pas
    seulement le meilleur couple d'attaque. C'est ce qu'un entrainement consommerait."""
    from engine.ai.tactic import DefaultAiUnitTactic
    d = DefaultAiUnitTactic().calculate_next_action(_port_ctx(state, caster))
    if not isinstance(d, dict):
        return None
    # L'ACTION retenue, cles decouvertes du dict -- mais SANS `util` : l'utilite change par
    # construction des que le bonus s'applique, donc l'inclure ferait passer 100 % des points pour
    # « renverses » alors que l'action est la MEME (faute commise, puis vue). A l'inverse, comparer
    # une poignee de cles DEVINEES rendrait deux `None` egaux et un « aucun renversement » qui ne
    # mesure rien (autre faute, aussi commise). D'ou : toutes les cles sauf le scalaire d'utilite.
    return tuple(sorted((str(k), repr(v)) for k, v in d.items() if k != "util"))


def rank_actions(state, caster: int) -> list:
    """Classement COMPLET des actions d'attaque du caster -- toutes les paires (ability, cible) que
    `ctx.plans` enumere, sur toutes leurs tuiles rankees, chacune scoree par son playbook. C'est le
    materiau de l'argmax : un renversement s'y lit comme un changement de TETE."""
    ctx = _port_ctx(state, caster)
    plan = ctx.plans.get(ctx.uid) or {}
    out = []
    for ev in (plan.get("evals") or []):
        ab, tgt = ev.get("abilityId"), ev.get("targetId")
        if ab is None or tgt is None:
            continue
        for rk in (ev.get("ranked") or []):
            t = (rk.get("col"), rk.get("row"))
            if t[0] is None:
                continue
            u = port_utility(ctx, tgt, ab, t)
            if u is not None:
                out.append((u, int(ab), int(tgt), t))
    out.sort(key=lambda x: -x[0])
    return out


def rank_flip(state_n, state_0, caster: int) -> dict:
    """Tete du classement avec le compteur LU vs FORCE a 0, et la MARGE que le bonus doit franchir
    pour renverser (`u(top1) - u(top2)` a compteur nul). Une marge INFERIEURE au gain du bonus dit
    que le terme est capable de renverser, meme si CE point-ci ne renverse pas."""
    rn, r0 = rank_actions(state_n, caster), rank_actions(state_0, caster)
    if not rn or not r0:
        return {"skipped": "aucune action scoree"}
    gap0 = (r0[0][0] - r0[1][0]) if len(r0) > 1 else None
    return {"top_n": rn[0], "top_zero": r0[0], "flip": rn[0][1:] != r0[0][1:],
            "gain": rn[0][0] - next((u for u, ab, tg, t in r0
                                     if (ab, tg, t) == rn[0][1:]), r0[0][0]),
            "gap_zero": gap0, "n_actions": len(rn)}


def argmax_sensitivity(h, a: dict, points: int = 7, rival_points: int = 5) -> dict:
    """**Le terme reel renverse-t-il une DECISION, ou seulement un scalaire ?**

    Sur le montage nominal l'ennemi a 300000 PV : aucune borne ne peut le tuer, donc l'ecart de
    `V x n` ne fait que deplacer une utilite sans jamais changer l'action retenue. Et avec une SEULE
    cible atteignable il n'existe aucune alternative a departager -- un « 0 renversement » y serait
    une propriete du MONTAGE, pas du terme. La question est donc : « existe-t-il un etat, atteignable,
    ou il renverse ? », et il faut un RIVAL pour y repondre.

    On balaie donc DEUX axes sur le `State` OFFLINE deja confronte bit-exact au natif en phase B :
      * les PV de la cible ancree, dans la fenetre `[min(port n=0), max(port n reel)]` -- l'intervalle
        exact ou le bonus fait basculer un KILL ;
      * les PV du RIVAL (le second ennemi, ramene au contact par le montage), qui fournit l'action
        concurrente.
    Analyse de sensibilite d'un port VALIDE, pas une simulation libre. Sans rival au contact, on
    balaie quand meme la cible et on DIT que l'axe rival manque."""
    from engine.runner.components import HealthComponent
    row = next((r for r in a["rows_b"] if r["same_tile"]), None)
    if row is None or row["off"] is None or row["off_zero"] is None:
        return {"skipped": "phase B sans prediction sur la tuile courante"}
    lo, hi = int(row["off_zero"][0]), int(row["off"][1])
    if hi <= lo:
        return {"skipped": "fenetre de PV vide (%d..%d)" % (lo, hi)}
    tgt, caster = a["plan"]["target"], a["plan"]["caster"]
    rival = a["plan"].get("rival")
    grid = [lo + int(round((hi - lo) * i / float(points - 1))) for i in range(points)]
    rivals = ([lo + int(round((hi - lo) * j / float(rival_points - 1))) for j in range(rival_points)]
              if rival is not None else [None])

    def _set_hp(st, uid, hp):
        e = st.get_entity(uid)
        hc = e.get_component(HealthComponent) if e is not None else None
        if hc is not None and hp is not None:
            hc.hp = int(hp)

    out = []
    for hp in grid:
        for rhp in rivals:
            st_n = h.offline_state(a["plan"])
            st_0 = h.offline_state(a["plan"], force_tiles=0)
            for st in (st_n, st_0):
                _set_hp(st, tgt, hp)
                _set_hp(st, rival, rhp)
            d_n, d_0 = _decision(st_n, caster), _decision(st_0, caster)
            rk = rank_flip(st_n, st_0, caster)
            out.append({"hp": hp, "rhp": rhp, "dec_n": d_n, "dec_zero": d_0,
                        "flip": d_n != d_0 or bool(rk.get("flip")), "rank": rk})
    return {"lo": lo, "hi": hi, "rival": rival, "points": out,
            "flips": [p for p in out if p["flip"]]}


# ---------------------------------------------------------------- un bras
def arm(h, steps: int, with_rival: bool = False) -> dict:
    """Monte le regime `steps`, mesure la PHASE A, joue le PAS en live, mesure la PHASE B.

    N'ATTAQUE JAMAIS : une attaque jouee poserait `UnitFlag.ActiveAbilityUsed` et changerait ce que
    le natif accepte de predire. Le pas seul suffit -- c'est lui qui remplit `+0xf0`.

    `with_rival` RAMENE le second ennemi au contact de la tuile d'arrivee, pour que l'argmax ait une
    action CONCURRENTE a departager (`arrange` l'ecarte a 4+steps). C'est un bras SEPARE : le rival
    BLOQUE le passage (`WalkPathfinder$$UnitIsBlockedByEnemyUnit`), donc le chemin s'allonge et sort
    la tuile d'arrivee du movable set -- la phase A n'y est plus mesurable. En echange il offre le
    discriminant le plus fort du lot : un pas de 2 hex qui coute 6 tuiles de CHEMIN."""
    plan = h.arrange(int(steps))
    if plan is None:
        raise RuntimeError("geometrie NON INSTALLEE pour un pas de %d tuile(s)" % steps)
    plan["rival"] = None
    if with_rival:
        # On DEPLACE les unites pour obtenir le regime voulu ; on ne subit pas la geometrie de spawn.
        others = [u for u in h.enemies_of(h.my_player) if u.get("id") != plan["target"]]
        if others:
            for cand in h.free_tiles(plan["step_to"], 1,
                                     exclude=(others[0]["id"], plan["caster"], plan["target"])):
                if tuple(cand) == tuple(plan["start"]) or tuple(cand) == tuple(plan["anchor"]):
                    continue
                if h.place(others[0]["id"], cand):
                    plan["rival"] = others[0]["id"]
                    plan["rival_pos"] = tuple(cand)
                    break
        if plan["rival"] is None:
            raise RuntimeError("RIVAL non installe (steps=%d) -- l'axe argmax ne serait pas mesure"
                               % steps)
    if h.reach_my_turn(force_cycle=True) is None:
        raise RuntimeError("mon tour non atteint pour un pas de %d tuile(s)" % steps)
    dv = h.dview()
    pos = {u["id"]: P335._upos(u) for u in h.alive(dv)}
    if pos.get(plan["caster"]) != plan["start"] or pos.get(plan["target"]) != plan["anchor"]:
        raise RuntimeError("la geometrie a bouge avant le pas (steps=%d)" % steps)
    if hexgeo.distance(plan["start"], plan["anchor"]) <= 1:
        raise RuntimeError("depart DEJA au contact (steps=%d)" % steps)
    if hexgeo.distance(plan["start"], plan["step_to"]) != steps:
        raise RuntimeError("pas demande != distance hex (steps=%d)" % steps)
    ab_nat = h.normal_attack_type(plan["caster"], dv)
    if ab_nat is None:
        raise RuntimeError("attaque normale introuvable (steps=%d)" % steps)
    plan["ability_type"] = ab_nat
    plan["snapshot"] = h.snapshot()

    tgt = plan["target"]
    step_to = tuple(plan["step_to"])
    # Tuiles de melee : `step_to` D'ABORD, puis les autres tuiles LIBRES adjacentes a la cible (le
    # bonus est melee-only -- seules celles-la exercent l'effet).
    tiles = [step_to] + [tuple(t) for t
                         in h.free_tiles(plan["anchor"], 1,
                                         exclude=(plan["caster"], plan["target"]))
                         if tuple(t) != step_to]

    # ---------------- PHASE A : AVANT le pas (reel = 0, pas simule = k)
    st_a = P335.load_state(plan["snapshot"]["dv"], plan["snapshot"]["ob"],
                           plan["snapshot"]["snap"], board=h.board)
    ctx_a = _port_ctx(st_a, plan["caster"])
    ab_port = port_ability_id(ctx_a)
    rows_a = []
    for t in tiles:
        rows_a.append({"tile": t,
                       "hex": hexgeo.distance(tuple(plan["start"]), t),
                       "n_pred": _pred_tiles_moved(ctx_a, plan["caster"], t),
                       "nat": predict_native(h.rid, plan["caster"], tgt, ab_nat, t),
                       "off": predict_port(ctx_a, tgt, ab_port, t)})

    # ---------------- le PAS, en live
    if not h.place(plan["caster"], step_to):
        raise RuntimeError("le PAS live n'a pas eu lieu (steps=%d)" % steps)
    plan["rng_after_step"] = _rpc("dumpRng", {"runnerId": h.rid}, 30000)

    # ---------------- PHASE B : APRES le pas (reel = k, pas simule = 0)
    st_b = h.offline_state(plan)                       # pas REJOUE -> compteur pose par le moteur
    n = unit_tiles_moved_this_turn(st_b, plan["caster"])
    ctx_b = _port_ctx(st_b, plan["caster"])
    st_0 = h.offline_state(plan, force_tiles=0)        # contrefactuel = l'etat d'AVANT #340
    ctx_0 = _port_ctx(st_0, plan["caster"])
    rows_b = []
    for t in tiles:
        rows_b.append({"tile": t, "same_tile": t == step_to,
                       "n_pred": _pred_tiles_moved(ctx_b, plan["caster"], t),
                       "n_pred_zero": _pred_tiles_moved(ctx_0, plan["caster"], t),
                       "nat": predict_native(h.rid, plan["caster"], tgt, ab_nat, t),
                       "off": predict_port(ctx_b, tgt, ab_port, t),
                       "off_zero": predict_port(ctx_0, tgt, ab_port, t),
                       "u": port_utility(ctx_b, tgt, ab_port, t),
                       "u_zero": port_utility(ctx_0, tgt, ab_port, t)})
    out = {"steps": int(steps), "n": n, "plan": plan, "step_to": step_to, "with_rival": with_rival,
           "ab_nat": ab_nat, "ab_port": ab_port, "rows_a": rows_a, "rows_b": rows_b,
           "ctx_b": ctx_b, "ctx_zero": ctx_0}
    out["argmax"] = argmax_sensitivity(h, out) if with_rival else {"skipped": "bras sans rival"}
    return out


# ---------------------------------------------------------------- verdicts
def mismatches(rows: list) -> list:
    """Tuiles ou le NATIF a repondu et ou le PORT s'en ecarte (ou ne repond pas)."""
    return [r for r in rows if r["nat"] is not None and r["off"] != r["nat"]]


def answered(rows: list) -> list:
    return [r for r in rows if r["nat"] is not None]


def vacuous(rows_b: list) -> list:
    """Tuiles de la phase B ou le contrefactuel `n=0` rend la MEME chose que le port : elles ne
    mesurent RIEN, et un vert obtenu dessus ne prouverait rien."""
    return [r for r in rows_b
            if r["nat"] is not None and r["off"] is not None and r["off_zero"] == r["off"]]


def phase_invariant_breaks(a: dict) -> list:
    """Tuiles ou NATIF(A) != NATIF(B) : les deux moities de la somme devraient rendre la MEME
    valeur. Une rupture ici accuse le MONTAGE (geometrie/compteur pollue), pas le port."""
    byb = {r["tile"]: r["nat"] for r in a["rows_b"]}
    out = []
    for r in a["rows_a"]:
        nb = byb.get(r["tile"])
        if r["nat"] is not None and nb is not None and r["nat"] != nb:
            out.append((r["tile"], r["nat"], nb))
    return out


def report(res: dict) -> bool:
    ok = True
    print("\n  PREDICTION apres deplacement -- board %s / seed %d (runner %d)"
          % (res["board"], res["seed"], res["rid"]))
    for s, a in sorted(res["arms"].items()):
        print("\n  BRAS %s -- pas demande = %d hex, arrivee %s%s ; compteur du port apres rejeu : "
              "n = %d" % (s, a["steps"], a["step_to"],
                          (" ; RIVAL en %s" % (a["plan"].get("rival_pos"),)) if a["with_rival"]
                          else "", a["n"]))
        print("    PHASE A (avant le pas : reel=0, pas simule=k)")
        print("      %-10s %-5s %-7s %-16s %-16s" % ("tuile", "hex", "n_pred", "NATIF", "PORT"))
        for r in a["rows_a"]:
            print("      %-10s %-5s %-7s %-16s %-16s"
                  % (r["tile"], r["hex"], r["n_pred"], r["nat"], r["off"]))
        na = answered(a["rows_a"])
        bad_a = mismatches(a["rows_a"])
        if len(na) < MIN_TILES_A and not a["with_rival"]:
            ok = False
            print("      [X] le natif n'a repondu que sur %d tuile(s) (< %d) -- le bras ne mesure "
                  "pas le terme « pas simule »" % (len(na), MIN_TILES_A))
        if bad_a:
            ok = False
            print("      [X] PORT != NATIF sur %d/%d tuile(s) : %s"
                  % (len(bad_a), len(na), [(r["tile"], r["nat"], r["off"]) for r in bad_a][:4]))
        else:
            print("      [OK] port == natif sur les %d tuile(s) auxquelles le natif repond" % len(na))

        print("    PHASE B (apres le pas : reel=%d, pas simule=0)" % a["n"])
        print("      %-10s %-6s %-7s %-11s %-16s %-16s %-16s"
              % ("tuile", "meme?", "n_pred", "n_pred(0)", "NATIF", "PORT", "PORT(n=0)"))
        for r in a["rows_b"]:
            print("      %-10s %-6s %-7s %-11s %-16s %-16s %-16s"
                  % (r["tile"], "oui" if r["same_tile"] else "non", r["n_pred"], r["n_pred_zero"],
                     r["nat"], r["off"], r["off_zero"]))
        nb = answered(a["rows_b"])
        bad_b = mismatches(a["rows_b"])
        vac = vacuous(a["rows_b"])
        if not nb:
            ok = False
            print("      [X] le natif n'a repondu sur AUCUNE tuile -- rien n'est mesure")
        if bad_b:
            ok = False
            print("      [X] PORT != NATIF sur %d/%d tuile(s) : %s"
                  % (len(bad_b), len(nb), [(r["tile"], r["nat"], r["off"]) for r in bad_b][:4]))
        else:
            print("      [OK] port == natif sur les %d tuile(s) auxquelles le natif repond" % len(nb))
        if vac:
            ok = False
            print("      [X] %d tuile(s) INERTES (le contrefactuel n=0 rend la meme valeur) : %s"
                  % (len(vac), [r["tile"] for r in vac][:6]))
        else:
            print("      [OK] les %d tuile(s) mesurantes re-divergent bien a n=0 (ecart/borne %s)"
                  % (len(nb), [(r["off"][0] - r["off_zero"][0]) for r in nb
                               if r["off"] is not None and r["off_zero"] is not None][:4]))

        brk = phase_invariant_breaks(a)
        if brk:
            ok = False
            print("      [X] NATIF(A) != NATIF(B) sur %s -- le MONTAGE ne tient pas (les deux "
                  "termes devraient rendre la meme somme)" % (brk[:3],))
        else:
            print("      [OK] NATIF(A) == NATIF(B) : les deux termes rendent la meme somme")

        best = max((r for r in a["rows_b"] if r["u"] is not None), key=lambda r: r["u"],
                   default=None)
        best0 = max((r for r in a["rows_b"] if r["u_zero"] is not None),
                    key=lambda r: r["u_zero"], default=None)
        if best is not None and best0 is not None:
            print("      utilite (tuile courante) : n reel u=%.4f ; n=0 u=%.4f"
                  % (next(r["u"] for r in a["rows_b"] if r["same_tile"]),
                     next(r["u_zero"] for r in a["rows_b"] if r["same_tile"])))
        am = a.get("argmax") or {}
        if am.get("skipped"):
            print("      argmax : NON MESURE (%s)" % am["skipped"])
        else:
            fl = am.get("flips") or []
            print("      argmax (DefaultAiUnitTactic ; PV cible%s balayes sur [%d, %d]) : "
                  "%d/%d point(s) RENVERSES"
                  % (" ET rival" if am.get("rival") is not None else " -- SANS rival au contact",
                     am["lo"], am["hi"], len(fl), len(am["points"])))
            for p in fl[:3]:
                print("        [FLIP] hp=%-7s rival=%-7s top1 n reel -> %s ; n=0 -> %s"
                      % (p["hp"], p["rhp"], p["rank"].get("top_n"), p["rank"].get("top_zero")))
            # Un « 0 renversement » ne vaut que si les decisions sont REELLES : deux `None` seraient
            # egaux sans rien decider. On imprime donc un echantillon, toujours, et la MARGE.
            for p in (am["points"][:1] + am["points"][len(am["points"]) // 2:][:1]
                      + am["points"][-1:]):
                rk = p["rank"]
                print("        [echantillon] hp=%-7s rival=%-7s action=%s | %d actions scorees, "
                      "gain du bonus=%.3f, marge top1-top2 (n=0)=%s"
                      % (p["hp"], p["rhp"], p["dec_n"], rk.get("n_actions", 0),
                         rk.get("gain") or 0.0, rk.get("gap_zero")))
            if all(p["dec_n"] is None for p in am["points"]):
                ok = False
                print("        [X] AUCUNE decision rendue -- le « 0 renversement » ne mesure RIEN")
            gains = [p["rank"].get("gain") or 0.0 for p in am["points"]]
            gaps = [p["rank"].get("gap_zero") for p in am["points"]
                    if p["rank"].get("gap_zero") is not None]
            if gaps:
                print("        pouvoir de renversement : gain du bonus max=%.3f vs marge top1-top2 "
                      "min=%.3f -> %s" % (max(gains), min(gaps),
                                          "PEUT renverser" if max(gains) > min(gaps)
                                          else "ne peut PAS renverser sur ce montage"))
    return ok


def scenario(steps=(1, 2), board: str = P335.BOARD, seed: int = P335.SEED,
             rival_step: int | None = None) -> dict:
    """Bras NOMINAUX (`steps`, sans rival : phases A et B toutes deux mesurables), puis UN bras
    ARGMAX (`rival_step`, avec rival au contact : seule la phase B y est mesurable, mais c'est le
    seul qui offre une action concurrente a departager)."""
    P335.STATE = STATE                       # state-file PROPRE (le module #335 a le sien)
    h = P335.build(board=board, seed=seed)
    out = {"board": board, "seed": seed, "rid": h.rid, "arms": {}, "harness": h}
    for s in steps:
        out["arms"]["%d" % int(s)] = arm(h, int(s))
    if rival_step is not None:
        out["arms"]["%d+rival" % int(rival_step)] = arm(h, int(rival_step), with_rival=True)
    return out


def dispose(res: dict) -> None:
    h = (res or {}).get("harness")
    if h is not None:
        try:
            h.dispose()
        except Exception:                                # noqa: BLE001 -- best effort de cleanup
            pass


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--board", default=P335.BOARD)
    ap.add_argument("--seed", type=int, default=P335.SEED)
    ap.add_argument("--steps", default="1,2")
    ap.add_argument("--rival-step", type=int, default=2,
                    help="pas du bras ARGMAX (rival au contact) ; 0 = pas de bras argmax")
    ap.add_argument("--keep", action="store_true", help="ne pas disposer le runner")
    a = ap.parse_args()
    steps = tuple(int(x) for x in a.steps.split(",") if x.strip())
    res = scenario(steps=steps, board=a.board, seed=a.seed,
                   rival_step=(a.rival_step or None))
    try:
        ok = report(res)
    finally:
        if not a.keep:
            res["harness"].dispose()
    print("\n  VERDICT : %s" % ("port == natif sur tous les bras" if ok else "ECART"))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
