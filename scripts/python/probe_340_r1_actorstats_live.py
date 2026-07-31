"""probe #340-r1 -- le capteur `actorStats` publie-t-il `ActorStatisticsComponent+0xf0`, et les
DEUX voies LIVE du port lisent-elles enfin le compteur REEL de tuiles ?

LE CRITERE, pose AVANT toute methode
------------------------------------
Question binaire, en trois volets qui se lisent chacun tout seul :

  V1 -- LE CAPTEUR. `actorStats.tilesMoved{ThisBattle,ThisTurn,LastTurn}` sont-ils bien
      `ActorStatisticsComponent +0xec / +0xf0 / +0xf4` ? Les OFFSETS sont attestes par trois
      lectures du decompile, mais les NOMS passes a `getFieldOffset` ne sont PAS verifiables
      offline (aucun `fields.tsv` dans `data/symbols/`) : si `getFieldOffset` resolvait un autre
      champ, le hook lirait du garbage SANS erreur. Seule la mesure tranche, et le discriminant
      est le PATRON A TROIS CHAMPS, pas une valeur isolee :

          apres un pas de k tuiles     -> battle += k, turn = k,        last inchange
          apres `EndTurnOperation`     -> battle inchange, turn = 0,    last = k

      C'est `IdunBattle.Entities.Components.ActorStatisticsComponent$$ResetThisTurn`
      (`if (wasOwnTurn) comp[0xf4] = comp[0xf0]; comp[0xf0] = 0;`) lu par sa CONSEQUENCE. Trois
      champs qui roulent ensemble selon deux transitions differentes ne peuvent pas etre un
      alignement heureux sur de mauvais offsets.

  V2 -- LA VOIE `load_state`. Un `State` reconstruit d'une capture live prise APRES le pas
      repartait a `tiles_moved_this_turn = 0` : aucun canal ne portait `+0xf0`. Le rejeu offline
      d'un `MoveUnitMessage` (voie `probe_335.offline_state`, celle que #340 a validee) MASQUAIT
      le trou -- c'est le moteur qui reposait le compteur. Ici on charge SANS rejouer : le
      compteur ne peut venir que du capteur.

  V3 -- LA VOIE LIVE-CAPTURE de la PREDICTION (`build_predictor` -> `from_predictor_sctx`), celle
      dont #340 disait "le cablage est pose et inerte tant que le hook n'est pas deploye".
      `Scene.tiles_moved_this_turn` doit rendre k, et la prediction doit etre bit-exacte contre
      `aiPlaybookPredict`.

Chaque volet porte son CONTREFACTUEL, sinon un vert ne prouverait rien : le canal est retire
(`actor_stats=None` pour V2, table videe pour V3) et la mesure doit RE-DIVERGER. Une tuile ou le
port rend la meme chose avec et sans le compteur ne MESURE RIEN, et le probe la denonce.

CE QUE LE DECOMPILE DIT (relu sur `rnca9r7q6c`)
----------------------------------------------
    IdunBattle.Entities.Formulas.TilesMovedThisTurnFormula$$Calculate:
        return *(uint *)(GetComponent<ActorStatisticsComponent>(sel) + 0xf0);

    IdunBattle.Entities.UnitExtensions$$RecordTilesMoved(unit, tiles, state):
        if ((int)tiles < 1) return;  comp[0xec] += tiles;  comp[0xf0] += tiles;

    IdunBattle.Entities.Components.ActorStatisticsComponent$$ResetThisTurn(comp, wasOwnTurn):
        if (wasOwnTurn) comp[0xf4] = comp[0xf0];   comp[0xf0] = 0;

MONTAGE (harnais #335/#340 reutilise TEL QUEL)
---------------------------------------------
  * `votanChampion` (Kimm) est HORS du seed BC -> injection catalogue ;
  * geometrie DRIVEE, puis `reach_my_turn(force_cycle=True)` OBLIGATOIRE : les `place()` du
    montage sont de vrais `MoveUnitOperation` et ENREGISTRENT des tuiles ; sans le cycle complet
    le compteur du MONTAGE entrerait dans la mesure ;
  * on N'ATTAQUE JAMAIS : une attaque poserait `UnitFlag.ActiveAbilityUsed` et changerait ce que
    le natif accepte de predire.

Usage :
    python probe_340_r1_actorstats_live.py                      # MC1_67 / 909, pas de 1 et 2
    python probe_340_r1_actorstats_live.py --board C1_25 --seed 31337 --steps 1,3
ASCII only.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import hexgeo
import probe_335_tiles_moved_combat as P335
import probe_340_tiles_moved_prediction as P340
from engine.runner.components import unit_tiles_moved_this_turn
from engine.runner.snapshot import load_state

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
LOGS = ROOT / "logs"
# State-file PROPRE a ce probe (discipline runner : un state-file par probe, jamais partage).
STATE = LOGS / "rs_340r1_actorstats.json"


# ---------------------------------------------------------------- le capteur
def actor_stats(rid: int) -> dict | None:
    """`{entityId: {battle, turn, last, attacks}}` depuis le RPC `actorStats`.

    Rend **None** si le RPC echoue -- jamais `{}` : un dict vide se lirait comme "mesure faite,
    rien a signaler" alors que c'est "pas mesure". Meme discipline tri-etat que
    `scene._tiles_moved_from_actor_stats`, pour la meme raison (un echec RENDU ne doit pas pouvoir
    se lire comme une mesure)."""
    r = P335._rpc("actorStats", {"runnerId": int(rid)}, 40000)
    if not (isinstance(r, dict) and r.get("ok")):
        return None
    out = {}
    for u in (r.get("units") or []):
        eid = u.get("entityId")
        if eid is None:
            continue
        out[int(eid)] = {"battle": u.get("tilesMovedThisBattle"),
                         "turn": u.get("tilesMovedThisTurn"),
                         "last": u.get("tilesMovedLastTurn"),
                         "attacks": u.get("totalAttacksMade")}
    return out


def sensor_publishes_tiles(ast: dict | None) -> bool:
    """Le hook DEPLOYE publie-t-il les trois compteurs ? Sur un bundle anterieur les cles sont
    absentes du JSON -> `None`, et tout le reste du probe serait vert pour la mauvaise raison
    (le port garderait son comportement d'avant, qui est correct... mais ne mesure rien)."""
    return bool(ast) and any(v.get("turn") is not None for v in ast.values())


def raw_payload(rid: int) -> dict:
    """Payload BRUT du RPC, tel que `load_state(actor_stats=...)` l'attend."""
    r = P335._rpc("actorStats", {"runnerId": int(rid)}, 40000)
    return r if isinstance(r, dict) else {}


# ---------------------------------------------------------------- voie live-capture (PREDICTION)
def _live_capture_scene(rid: int, caster: int):
    """La `Scene` de la voie LIVE-CAPTURE : `build_predictor` (qui interroge `actorStats`) puis
    `from_predictor_sctx`. C'est le chemin que la chaine de decision emprunte quand elle part d'un
    runner VIVANT, par opposition a `Scene.from_state` (ECS offline) que #340 a deja ferme."""
    import engine_validate as EV
    import probe_27_custom_utility_inventory as INV
    from engine import weights as W
    from engine.ai import context as AICTX
    from engine.playbook import scene as _scene
    sid = INV._session_id()

    def rpc(m, b, t):
        return EV._r(sid, m, b, t)

    dv = rpc("decisionView", {"runnerId": rid, "allAbilities": True, "maxRank": 32}, 180)
    mov = rpc("aiMovableTiles", {"runnerId": rid}, 60)
    mov_by_unit = {u.get("unitId"): u for u in (mov.get("units") or [])}
    predictor = _scene.build_predictor(rpc, rid)
    # `refresh_shields` est le point de RE-CAPTURE par pas : c'est LUI que la boucle de decision
    # appelle, et c'est donc lui qui doit tenir le compteur a jour au fil des deplacements.
    _scene.refresh_shields(predictor, rpc, rid)
    ctx = AICTX.build(rpc, rid, dv, mov_by_unit, caster, W.load(), predictor)
    return ctx, predictor


# ---------------------------------------------------------------- un bras
def arm(h, steps: int, with_rival: bool = False) -> dict:
    """Monte le regime `steps`, mesure le capteur AVANT/APRES le pas, confronte les deux voies
    LIVE, puis fait ROULER le tour pour lire le reset.

    `with_rival` RAMENE le second ennemi au contact de la tuile d'arrivee (repris de #340) : il
    BLOQUE le passage (`WalkPathfinder$$UnitIsBlockedByEnemyUnit`), donc un pas de 2 hex coute 6
    tuiles de CHEMIN. C'est le discriminant CHEMIN-vs-HEX du capteur : un `+0xf0` qui compterait en
    distance hexagonale rendrait 2 la ou le natif en met 6."""
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
            raise RuntimeError("RIVAL non installe (steps=%d) -- le discriminant chemin-vs-hex ne "
                               "serait pas mesure" % steps)
    if h.reach_my_turn(force_cycle=True) is None:
        raise RuntimeError("mon tour non atteint pour un pas de %d tuile(s)" % steps)
    dv = h.dview()
    pos = {u["id"]: P335._upos(u) for u in h.alive(dv)}
    if pos.get(plan["caster"]) != plan["start"] or pos.get(plan["target"]) != plan["anchor"]:
        raise RuntimeError("la geometrie a bouge avant le pas (steps=%d)" % steps)
    if hexgeo.distance(plan["start"], plan["step_to"]) != steps:
        raise RuntimeError("pas demande != distance hex (steps=%d)" % steps)
    ab_nat = h.normal_attack_type(plan["caster"], dv)
    if ab_nat is None:
        raise RuntimeError("attaque normale introuvable (steps=%d)" % steps)
    plan["ability_type"] = ab_nat
    caster, tgt = plan["caster"], plan["target"]
    step_to = tuple(plan["step_to"])

    # ---- V1a : le capteur AVANT le pas. Le cycle complet vient de remettre `+0xf0` a zero.
    ast_before = actor_stats(h.rid)
    plan["snapshot"] = h.snapshot()

    # ---- le PAS, en live
    if not h.place(caster, step_to):
        raise RuntimeError("le PAS live n'a pas eu lieu (steps=%d)" % steps)
    plan["rng_after_step"] = P335._rpc("dumpRng", {"runnerId": h.rid}, 30000)

    # ---- V1b : le capteur APRES le pas
    ast_after = actor_stats(h.rid)
    raw_after = raw_payload(h.rid)

    # `n` de REFERENCE : ce que le port compte par le PATHFINDER en rejouant le pas offline. C'est
    # la voie que #340 a validee bit-exacte contre le natif -- elle sert ici d'ETALON au capteur.
    st_replay = h.offline_state(plan)
    n_ref = unit_tiles_moved_this_turn(st_replay, caster)

    # ---- V2 : la voie `load_state` -- capture CHARGEE, PAS rejouee.
    s = plan["snapshot"]
    dv_after = h.dview()
    ob_after = P335._rpc("observeBattle", {"runnerId": h.rid}, 40000)
    snap_after = P335._rpc("combatSnapshot", {"runnerId": h.rid}, 60000)
    st_seeded = load_state(dv_after, ob_after, snap_after, board=h.board, actor_stats=raw_after)
    st_bare = load_state(dv_after, ob_after, snap_after, board=h.board)   # CONTREFACTUEL
    n_seeded = unit_tiles_moved_this_turn(st_seeded, caster)
    n_bare = unit_tiles_moved_this_turn(st_bare, caster)

    # ---- V4 : le GARDE `< 0` du seeder. Tant que le correctif du hook n'est pas reinjecte, deux
    # des trois champs publient du garbage NEGATIF ; un seeder naif l'ecrirait dans l'ECS, ou il
    # deviendrait indistinguable d'un etat de jeu. On verifie ce que le seeder a REELLEMENT pose.
    from engine.runner.components import UnitComponent as _UC
    _uc = st_seeded.get_entity(caster).get_component(_UC)
    guard = {"battle": _uc.tiles_moved_this_battle, "last": _uc.tiles_moved_last_turn,
             "published_battle": (ast_after or {}).get(caster, {}).get("battle"),
             "published_last": (ast_after or {}).get(caster, {}).get("last")}

    # ---- V3 : la voie live-capture de la PREDICTION
    ctx_live, predictor = _live_capture_scene(h.rid, caster)
    n_scene = ctx_live.scene.tiles_moved_this_turn(caster)

    # Tuiles de MELEE : le bonus est melee-only, seules celles-la exercent l'effet.
    tiles = [step_to] + [tuple(t) for t
                         in h.free_tiles(plan["anchor"], 1, exclude=(caster, tgt))
                         if tuple(t) != step_to]
    ab_port_state = P340.port_ability_id(P340._port_ctx(st_seeded, caster))
    rows = []
    for t in tiles:
        nat = P340.predict_native(h.rid, caster, tgt, ab_nat, t)
        # voie live-capture : le ctx porte l'id CONCRET per-unit (`NormalAttackType@0x28`)
        off_live = P340.predict_port(ctx_live, tgt, ab_nat, t)
        # voie load_state : le port synthetise `state_bridge.NORMAL_ATTACK_ID`
        off_seeded = P340.predict_port(P340._port_ctx(st_seeded, caster), tgt, ab_port_state, t)
        off_bare = P340.predict_port(P340._port_ctx(st_bare, caster), tgt, ab_port_state, t)
        rows.append({"tile": t, "same_tile": t == step_to, "nat": nat,
                     "live": off_live, "seeded": off_seeded, "bare": off_bare})

    # ---- V1c : le RESET de fin de tour, lu par sa CONSEQUENCE sur les TROIS champs
    P335._rpc("applyAction", {"runnerId": h.rid, "action": {"kind": "endturn"}}, 40000)
    ast_reset = actor_stats(h.rid)

    return {"steps": int(steps), "plan": plan, "step_to": step_to, "caster": caster,
            "n_ref": n_ref, "n_seeded": n_seeded, "n_bare": n_bare, "n_scene": n_scene,
            "ast_before": ast_before, "ast_after": ast_after, "ast_reset": ast_reset,
            "rows": rows, "ab_nat": ab_nat, "guard": guard, "with_rival": with_rival,
            "tiles_moved_by_id": dict(predictor.get("tiles_moved_by_id") or {})}


# ---------------------------------------------------------------- verdicts
def sensor_transitions(a: dict) -> dict:
    """Le PATRON A TROIS CHAMPS, VENTILE PAR CHAMP -- le discriminant de V1.

    Ventile, parce que les trois champs ne sont PAS solidaires dans le capteur : mesure du
    2026-07-31, `tilesMovedThisTurn` (+0xf0) est exact alors que `tilesMovedThisBattle` (+0xec) et
    `tilesMovedLastTurn` (+0xf4) rendent la MEME valeur constante -- signature d'une lecture a la
    MEME adresse (`getFieldOffset` rend **-1** sur un nom absent, et `-1 || 0x...` vaut -1 en JS,
    donc le hook lisait `comp - 1` pour les deux). Un verdict global aurait noye le seul champ qui
    porte ce cas sous l'echec des deux autres.

    Rend `{champ: [(quoi, attendu, obtenu), ...]}` ; listes vides = champ conforme."""
    c = a["caster"]
    if not (a["ast_before"] and a["ast_after"] and a["ast_reset"]):
        return {"turn": [("capteur MUET (RPC en echec)", None, None)]}
    if not all(c in a[k] for k in ("ast_before", "ast_after", "ast_reset")):
        return {"turn": [("capteur MUET sur le caster", None, None)]}
    b, af, rs = a["ast_before"][c], a["ast_after"][c], a["ast_reset"][c]
    k = a["n_ref"]
    out = {"turn": [], "battle": [], "last": []}
    # +0xf0 -- LE champ de ce cas (`TilesMovedThisTurnFormula$$Calculate` rend exactement lui).
    if b["turn"] != 0:
        out["turn"].append(("avant le pas (le cycle complet doit l'avoir remis a 0)", 0, b["turn"]))
    if af["turn"] != k:
        out["turn"].append(("apres le pas", k, af["turn"]))
    if rs["turn"] != 0:
        out["turn"].append(("remis a 0 par ResetThisTurn", 0, rs["turn"]))
    # +0xec -- cumul BATAILLE : `RecordTilesMoved` l'incremente du MEME pas, `ResetThisTurn` n'y
    # touche jamais.
    if af["battle"] != (b["battle"] or 0) + k:
        out["battle"].append(("cumule le pas", (b["battle"] or 0) + k, af["battle"]))
    if rs["battle"] != af["battle"]:
        out["battle"].append(("insensible au reset", af["battle"], rs["battle"]))
    # +0xf4 -- tour PRECEDENT : inchange par un pas, prend `+0xf0` au reset (`wasOwnTurn`).
    if af["last"] != b["last"]:
        out["last"].append(("inchange par un pas", b["last"], af["last"]))
    if rs["last"] != k:
        out["last"].append(("= +0xf0 au reset (wasOwnTurn)", k, rs["last"]))
    return out


def mismatches(rows: list, key: str) -> list:
    return [r for r in rows if r["nat"] is not None and r[key] != r["nat"]]


def vacuous(rows: list, key: str) -> list:
    """Tuiles ou le CONTREFACTUEL rend la meme chose : elles ne mesurent RIEN."""
    return [r for r in rows
            if r["nat"] is not None and r[key] is not None and r["bare"] == r[key]]


def report(res: dict) -> bool:
    ok = True
    print("\n  #340-r1 -- capteur `actorStats` et les deux voies LIVE (board %s / seed %d, "
          "runner %d)" % (res["board"], res["seed"], res["rid"]))
    for s in sorted(res["arms"]):
        a = res["arms"][s]
        c = a["caster"]
        print("\n  BRAS %s -- pas de %d hex vers %s%s ; n de reference (pathfinder, rejeu offline)"
              " = %d" % (s, a["steps"], a["step_to"],
                         (" ; RIVAL bloquant en %s" % (a["plan"].get("rival_pos"),))
                         if a.get("with_rival") else "", a["n_ref"]))
        if a.get("with_rival") and a["n_ref"] <= a["steps"]:
            ok = False
            print("    [X] le rival ne BLOQUE pas (n=%d <= pas de %d hex) -- ce bras ne separe donc "
                  "pas CHEMIN de DISTANCE HEX" % (a["n_ref"], a["steps"]))
        elif a.get("with_rival"):
            print("    [OK] discriminant CHEMIN-vs-HEX : %d hex de pas coutent %d tuiles de chemin "
                  "-- un capteur qui compterait en distance hex rendrait %d"
                  % (a["steps"], a["n_ref"], a["steps"]))

        # ---- V1
        if not sensor_publishes_tiles(a["ast_after"]):
            ok = False
            print("    [X] V1 CAPTEUR : `actorStats` ne publie PAS `tilesMovedThisTurn` -- le hook "
                  "deploye est ANTERIEUR au capteur. Tout le reste de ce probe serait vert pour la "
                  "mauvaise raison (le port garderait son comportement d'avant).")
            continue
        b, af, rs = a["ast_before"][c], a["ast_after"][c], a["ast_reset"][c]
        print("    V1 CAPTEUR (+0xec battle / +0xf0 turn / +0xf4 last ; attacks = +0x20)")
        for lbl, row in (("avant le pas", b), ("apres le pas", af),
                         ("apres EndTurnOperation", rs)):
            print("      %-22s battle=%-13s turn=%-6s last=%-13s attacks=%-6s"
                  % (lbl, row["battle"], row["turn"], row["last"], row["attacks"]))
        bad = sensor_transitions(a)
        if bad.get("turn"):
            ok = False
            print("      [X] +0xf0 (`TilesMovedThisTurnFormula$$Calculate`) : %s"
                  % [(w, "attendu %s" % e, "obtenu %s" % g) for w, e, g in bad["turn"]])
        else:
            print("      [OK] +0xf0 : les deux transitions (pas -> %d, EndTurnOperation -> 0) "
                  "suivent RecordTilesMoved et ResetThisTurn -- c'est LE champ de ce cas" % a["n_ref"])
        for f, sym in (("battle", "+0xec (cumul BATAILLE)"), ("last", "+0xf4 (tour PRECEDENT)")):
            if bad.get(f):
                print("      [X] %s : %s" % (sym, [(w, "attendu %s" % e, "obtenu %s" % g)
                                                   for w, e, g in bad[f]]))
            else:
                print("      [OK] %s" % sym)
        if bad.get("battle") and bad.get("last") and b["battle"] == b["last"]:
            print("      -> les DEUX champs faux rendent la MEME valeur (%s) : signature d'une "
                  "lecture a la MEME adresse. `getFieldOffset` rend -1 sur un nom ABSENT, et "
                  "`-1 || 0x...` vaut -1 en JS -> le hook lit `comp - 1`. CORRECTIF LIVRE "
                  "(rpc-snapshot.ts), EXIGE UNE REINJECTION." % b["battle"])

        # ---- V2 / V3
        print("    V2 `load_state`  : compteur seede=%s   contrefactuel (sans le canal)=%s"
              % (a["n_seeded"], a["n_bare"]))
        print("    V3 live-capture  : Scene.tiles_moved_this_turn=%s   table=%s"
              % (a["n_scene"], a["tiles_moved_by_id"] or "{} (VIDE)"))
        if a["n_seeded"] != a["n_ref"]:
            ok = False
            print("      [X] V2 : `load_state` seede %s au lieu de %d" % (a["n_seeded"], a["n_ref"]))
        if a["n_bare"] != 0:
            ok = False
            print("      [X] V2 : le CONTREFACTUEL devrait valoir 0 (canal retire), il vaut %s -- "
                  "le bras ne separe donc rien" % a["n_bare"])
        if a["n_scene"] != a["n_ref"]:
            ok = False
            print("      [X] V3 : la voie live-capture rend %s au lieu de %d"
                  % (a["n_scene"], a["n_ref"]))
        g = a["guard"]
        pub = [v for v in (g["published_battle"], g["published_last"]) if v is not None]
        if pub and min(pub) < 0:
            if g["battle"] or g["last"]:
                ok = False
                print("      [X] V4 GARDE : du garbage NEGATIF publie (%s) a ete INGERE dans l'ECS "
                      "(battle=%s last=%s)" % (pub, g["battle"], g["last"]))
            else:
                print("      [OK] V4 GARDE : le garbage negatif publie (%s) n'entre PAS dans l'ECS "
                      "(battle=%s last=%s restent a leur 0 de construction)"
                      % (pub, g["battle"], g["last"]))
        else:
            print("      V4 GARDE : non exerce (aucune valeur negative publiee) -- battle=%s last=%s"
                  % (g["battle"], g["last"]))

        print("    PREDICTION depuis les tuiles de MELEE")
        print("      %-10s %-6s %-16s %-16s %-16s %-16s"
              % ("tuile", "meme?", "NATIF", "PORT live", "PORT load_state", "PORT sans canal"))
        for r in a["rows"]:
            print("      %-10s %-6s %-16s %-16s %-16s %-16s"
                  % (r["tile"], "oui" if r["same_tile"] else "non", r["nat"], r["live"],
                     r["seeded"], r["bare"]))
        answered = [r for r in a["rows"] if r["nat"] is not None]
        if not answered:
            ok = False
            print("      [X] le natif n'a repondu sur AUCUNE tuile -- rien n'est mesure")
        for key, label in (("live", "V3 live-capture"), ("seeded", "V2 load_state")):
            bad_k = mismatches(a["rows"], key)
            if bad_k:
                ok = False
                print("      [X] %s : PORT != NATIF sur %d/%d tuile(s) : %s"
                      % (label, len(bad_k), len(answered),
                         [(r["tile"], r["nat"], r[key]) for r in bad_k][:4]))
            else:
                print("      [OK] %s : port == natif sur les %d tuile(s) repondues"
                      % (label, len(answered)))
            vac = vacuous(a["rows"], key)
            if vac:
                ok = False
                print("      [X] %s : %d tuile(s) INERTES (le contrefactuel rend la meme valeur) "
                      ": %s" % (label, len(vac), [r["tile"] for r in vac][:6]))
            else:
                print("      [OK] %s : les tuiles mesurantes re-divergent bien sans le canal "
                      "(ecart/borne %s)"
                      % (label, [(r[key][0] - r["bare"][0]) for r in answered
                                 if r[key] is not None and r["bare"] is not None][:4]))
    return ok


def scenario(steps=(1, 2), board: str = P335.BOARD, seed: int = P335.SEED,
             rival_step: int | None = None) -> dict:
    P335.STATE = STATE                       # state-file PROPRE (les modules #335/#340 ont le leur)
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
                    help="pas du bras CHEMIN-vs-HEX (rival bloquant) ; 0 = pas de bras rival")
    ap.add_argument("--keep", action="store_true", help="ne pas disposer le runner")
    a = ap.parse_args()
    steps = tuple(int(x) for x in a.steps.split(",") if x.strip())
    res = scenario(steps=steps, board=a.board, seed=a.seed, rival_step=(a.rival_step or None))
    try:
        ok = report(res)
    finally:
        if not a.keep:
            res["harness"].dispose()
    print("\n  VERDICT : %s" % ("capteur conforme et les DEUX voies LIVE lisent le compteur"
                                if ok else "ECART"))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
