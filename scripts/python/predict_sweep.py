"""#1 - Balayage d'agrement PREDICTION moteur <-> oracle live PER-ABILITY.

But : produire une CARTE d'ecarts priorisee entre la prediction offline du moteur et
l'oracle natif DIRECT du playbook (`<Ability>Playbook.MakeDamagePredictions`), qui est la
verite terrain per-ability depuis #102 (aiPlaybookPredict) -- pas `aiPredict`/GetAllPredictions
(preview Attack-based, faux pour les specials config-based).

Pour un runner (build --seed / roster --p-units,--a-units, ou --runner existant), on drive au
contact puis, pour chaque triple (attaquant, ability de DEGAT, cible) que le NATIF a score
(decisionView attackPlans.evals ranked), on compare -- A POSITION COURANTE des deux cotes :
  - MOTEUR : engine.playbook.prediction.make_normal_attack_predictions (kind==normal)
             / make_damage_predictions (actives/granted) -> event cible principale
  - ORACLE : RPC aiPlaybookPredict(unitId, targetId, abilityType) -> event cible principale
On classe l'ecart de degat sante (min/max) : OK / MINOR / MAJOR / ENG_NONE / ENG_ZERO /
ORACLE_FAIL / ENG_ERR, on bucketise par (ability, kind, retClass) et on trie par priorite.

READ-ONLY : ne corrige RIEN, ne mute pas le jeu (aiPlaybookPredict est read-only ; le drive
mute un runner ISOLE, jamais celui de l'utilisateur). ASCII only (console cp1252).

CLI : python predict_sweep.py [--seed 777 | --runner <id>] [--p-units ..] [--a-units ..]
        [--board ..|--board-pool ..] [--max-turns 6] [--topk 3] [--json out.json]
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

import rl_collect_batch as R
import gameconfig as GC
from engine.playbook import scene as SC
from engine.playbook.scene import Scene
from engine.playbook import prediction
from engine.runner import snapshot as _snapshot   # porte du canal de seed `includeInactive` (#443-r2-b1)
import predict_samples as PS   # reutilise _drive_into_range (meme drive que l'agrement normal)
from sibling_script import sibling_script

ROOT = Path(__file__).resolve().parents[2]
STATE_REL = "data/_predict_sweep.json"          # state-file DEDIE (coexistence : proprietaire = ce fichier)
STATE = ROOT / STATE_REL
TOL = 3                                          # arrondi //100 vs Fix64


def _res(r):
    return r.get("result") if isinstance(r, dict) and "result" in r else r


def rpc(sid, method, body=None, timeout=90):
    return _res(R._rpc(sid, method, [body] if body is not None else [], timeout=timeout))


# ── Extraction de l'event cible principale de chaque cote ────────────────────────────────────────
def engine_main_event(scene, att, tgt, ability_id, ability_name, kind, cur_tile):
    """(min, max, hits, crit) de l'event cible PRINCIPALE cote MOTEUR, ou dict {err}."""
    try:
        if kind == "normal":
            ev = prediction.make_normal_attack_predictions(scene, att, tgt, cur_tile)
            events = [ev] if ev is not None else []
        else:
            events = prediction.make_damage_predictions(
                scene, att, tgt, ability_id, ability_name, attack_pos=cur_tile)
    except Exception as e:                                       # noqa: BLE001 - on veut classer, pas crasher
        return {"err": "%s: %s" % (type(e).__name__, e)}
    main = next((e for e in (events or []) if e.target == tgt), None)
    if main is None:
        return {"err": "no main event (n=%d)" % len(events or [])}
    r = main.prediction.accurate_health_damage
    return {"min": int(r.min), "max": int(r.max),
            "hits": int(main.prediction.applied_hits), "crit": bool(main.prediction.might_crit)}


def live_main_event(sid, rid, att, tgt, ability_id):
    """(min, max, hits, crit) de l'event cible PRINCIPALE cote ORACLE (aiPlaybookPredict), ou dict {err}.

    Distingue l'ECHEC RPC (ok:false) du playbook VIDE (#110) : quand `ok:true` mais `count==-1`
    (listNull), le `<Ability>Playbook.MakeDamagePredictions` NATIF a rendu null -- ces specials
    (Doombolt/JakhalStimms/GauntletsOfUltramar) n'ont PAS de playbook de degat bespoke, donc
    l'oracle DIRECT ne peut pas les mesurer. Ce N'EST PAS un echec RPC ni un trou de port moteur :
    on le flag `empty` -> classe ORACLE_EMPTY (attendu), pas ORACLE_FAIL (bruit). On ne fallback
    PAS sur GetAllPredictions (preview Attack-based = ARTEFACT, cf. case-99) : contaminerait
    l'oracle playbook pur ; l'ability reste inmesurable par le playbook direct, tag honnete."""
    r = rpc(sid, "aiPlaybookPredict",
            {"runnerId": rid, "unitId": att, "targetId": tgt, "abilityType": ability_id}, 60)
    if not r or not r.get("ok"):
        return {"err": (r or {}).get("error", "rpc null"), "retClass": (r or {}).get("retClass")}
    evs = r.get("events") or []
    main = next((e for e in evs if e.get("targetId") == tgt), None)
    if main is None:
        # ok:true sans event cible. count==-1 (listNull) = playbook rend null = pas de prediction
        # de degat directe (#110, playbook-none) ; count>=0 = playbook a des events mais aucun pour
        # CETTE cible (artefact positionnel/cible, distinct du playbook-none).
        empty = (r.get("count") == -1) or bool(r.get("listNull"))
        return {"err": "no main event (count=%s)" % r.get("count"),
                "empty": empty, "count": r.get("count"), "listNull": r.get("listNull"),
                "retClass": r.get("retClass"), "playbook": r.get("playbookClass")}
    return {"min": int(main.get("healthDmgMin") or 0), "max": int(main.get("healthDmgMax") or 0),
            "hits": int(main.get("appliedHits") or 0), "crit": bool(main.get("mightCrit")),
            "retClass": r.get("retClass"), "playbook": r.get("playbookClass")}


def classify(eng, live):
    """Statut de l'ecart de degat sante entre MOTEUR (eng) et ORACLE (live).

    OUT_OF_RANGE : l'oracle predit [0,0] depuis la tuile COURANTE (ability non applicable a cette
      cible depuis ici -- artefact positionnel, PAS un ecart de formule) -> exclu des buckets de gap.
    NON_DAMAGE   : les DEUX cotes ne produisent aucun event de degat pour cette cible (buff/self/
      ally-targeted mal ranke par decisionView) -> hors scope degat.
    ENG_NONE     : le NATIF predit du degat mais le moteur n'en produit AUCUN (vrai trou de port).
    ORACLE_EMPTY : le playbook NATIF rend null (count=-1) -- ability sans <Ability>Playbook de degat
      bespoke (Doombolt/JakhalStimms/Gauntlets #110) : oracle DIRECT inmesurable. Ni un echec RPC,
      ni un trou de port moteur -> categorie ATTENDUE (pas du bruit ORACLE_FAIL).
    ORACLE_FAIL  : le RPC oracle a VRAIMENT echoue (ok:false / throw) la ou le moteur produit une valeur.
    ENG_ZERO     : moteur predit 0 la ou le natif predit du degat. OK/MINOR/MAJOR = ecart chiffre."""
    live_ok = "err" not in live
    eng_ok = "err" not in eng
    if live_ok and live["min"] == 0 and live["max"] == 0:
        return "OUT_OF_RANGE"
    if not live_ok:
        if live.get("empty"):                      # playbook natif null -> inmesurable (#110), pas un echec
            return "ORACLE_EMPTY"
        return "NON_DAMAGE" if not eng_ok else "ORACLE_FAIL"
    if not eng_ok:
        return "ENG_NONE"                          # natif predit du degat, moteur rien -> trou de port
    lm, lM = live["min"], live["max"]
    em, eM = eng["min"], eng["max"]
    if abs(em - lm) <= TOL and abs(eM - lM) <= TOL:
        return "OK"
    if em == 0 and eM == 0:
        return "ENG_ZERO"                          # moteur predit 0 la ou le natif predit du degat
    rmin = em / lm if lm > 0 else (1.0 if em == 0 else 9.99)
    rmax = eM / lM if lM > 0 else (1.0 if eM == 0 else 9.99)
    if 0.90 <= rmin <= 1.10 and 0.90 <= rmax <= 1.10:
        return "MINOR"
    return "MAJOR"


def hit_aura_hint(units, att_id, att_pos, att_team):
    """INDICE DE CAUSE pour un ecart de COUPS (liveHits != engHits) : liste les ALLIES a portee
    (hex<=2) porteurs d'une ability a variable `extraHits` -> aura de coups PROBABLE non portee
    (ex. AstartesBanner range2 extraHits1 sur templAncient). Ces auras sont INVISIBLES dans
    decisionView.effects (posees source-side, pas comme EffectComponent sur le beneficiaire) et
    absentes du stat ExtraHits capte -> le harnais ne peut pas les seeder, mais il peut POINTER le
    porteur probable. Indice heuristique (pas une preuve) : oriente la RE. `att_pos`=(col,row)."""
    import hexgeo
    hints = []
    for u in units:
        p = u.get("pos")
        if not p or u.get("team") != att_team or u.get("id") == att_id:
            continue
        d = hexgeo.distance(att_pos, (p["col"], p["row"])) if att_pos else None
        if d is None or d > 2:
            continue
        vis = u.get("visualId")
        try:
            abils = GC.unit_abilities(vis)
        except Exception:
            continue
        for kind in ("passive", "active"):
            for ent in (abils.get(kind) or []):
                a = GC.ability(ent.get("name")) or {}
                v = {**(a.get("constants") or {}), **(a.get("variables") or {})}
                eh = v.get("extraHits")
                if eh and str(eh) not in ("0", "0.0"):
                    hints.append("u%s(%s)@hex%s %s:%s extraHits=%s range=%s"
                                 % (u.get("id"), vis, d, kind, ent.get("name"), eh, v.get("range")))
    return hints


def build_rows(sid, rid, my_team, max_turns, topk):
    """Drive au contact puis balaye les triples (att, ability degat, cible ranked) -> rows classees."""
    rpc_b = lambda m, b, t: rpc(sid, m, b, t)
    dec = PS._drive_into_range(sid, rid, my_team, max_turns)
    if dec.get("stageName") != "Running":
        return None, "bataille non-Running (stage=%s)" % dec.get("stageName")
    # COMMIT-BEST-MOVE : mettre chaque attaquant sur sa MEILLEURE tuile d'attaque (max dmgMax parmi ses
    # evals), pour que `aiPlaybookPredict` (tuile COURANTE) predise du degat reel -- sinon les melee non
    # encore adjacentes rendent [0,0] (artefact positionnel). 1 seul move/unite (pas de re-move gate).
    for ap in (dec.get("attackPlans") or []):
        att = ap.get("unitId")
        best = None
        for ev in (ap.get("evals") or []):
            for r0 in (ev.get("ranked") or []):
                if r0.get("dmgMax") is None or r0.get("col") is None:
                    continue
                if best is None or r0["dmgMax"] > best[0]:
                    best = (r0["dmgMax"], r0["col"], r0["row"])
        if best is not None:
            rpc(sid, "applyAction", {"runnerId": rid, "action": {
                "kind": "move", "unitId": att, "to": {"col": best[1], "row": best[2]}}}, 30)
    # CYCLE-TOUR : le commit-move a laisse mes unites en MILIEU d'activation (deplacement consomme).
    # On cycle le tour (endturn -> ennemi -> endturn -> moi) pour retrouver un etat NEUF -- « debut de
    # tour, unite en portee, attaque SANS bouger » -- ou toutes les activations sont disponibles et ou
    # `RemoveTurnFlags` a purge les flags de tour. Le flag `UnitFlag.Moved` lui-meme n'impose plus ce
    # cycle depuis #266 : la face PREDICTION le LIT (`Scene.moved_by_id` <- `combatSnapshot.unitFlags`
    # -> `prediction_has_moved`), donc un caster ayant deja bouge est vu comme tel des deux cotes.
    amine = 3 if my_team == 1 else 4
    rpc(sid, "applyAction", {"runnerId": rid, "action": {"kind": "endturn"}}, 30)
    for _ in range(4):
        cp = (rpc(sid, "decisionView", {"runnerId": rid, "maxRank": 1}, 60) or {}).get("currentPlayer")
        if cp == amine:
            break
        rpc(sid, "applyAction", {"runnerId": rid, "action": {"kind": "endturn"}}, 30)
    # Canal de SEED (#443-r2-b1) : `decision_view_seed_body` = la porte NOMMEE d'`includeInactive`,
    # le seul canal qui publie les effets POSES mais INERTES -- ceux que les mirrors d'un
    # `HasEffect(..., onlyActive = 0)` doivent voir. `SC.step_context` ci-dessous en seede son
    # `EffectsState` ; la liste BRUTE (`Scene.units[].effects`) reste projetee ACTIF-ONLY.
    dec = rpc(sid, "decisionView",
              _snapshot.decision_view_seed_body(rid, maxRank=3, allAbilities=True), 90)
    _aps = dec.get("attackPlans") or []
    _dmg_evals = sum(1 for ap in _aps for ev in (ap.get("evals") or [])
                     if (ev.get("ranked") or []) and (ev["ranked"][0].get("dmgMax") is not None))
    print("[sweep] post-move dec: currentPlayer=%s attackPlans=%d dmg-evals=%d"
          % (dec.get("currentPlayer"), len(_aps), _dmg_evals))
    # #166 : build_predictor APRES le drive+cycle (PAS avant) -> les stats DYNAMIQUES seedees dans le ctx
    # (turnsStarted stat 12 ; actorStats totalAttacksMade) sont COURANTES au moment de la comparaison. Un
    # predicteur construit a t=0 fige turnsStarted~0 -> ExecutionerAbility.get_special_hits (=RoundsStarted)
    # rendait 1 coup vs l'oracle live (round courant) : faux ecart de MESURE, pas un gap de port (un fresh
    # build_predictor capture turnsStarted correctement, prouve probe166 : eldarFarseer stat 12 = 8).
    predictor = SC.build_predictor(rpc_b, rid)
    if predictor is None:
        return None, "combatSnapshot KO (build_predictor None)"
    sctx = SC.step_context(predictor, dec)
    scene = Scene.from_predictor_sctx(predictor, sctx, None)
    pos_by_id = sctx["pos_by_id"]
    units = dec.get("units") or []
    kind_by = {}                                   # (att, ability_id) -> kind
    vis_by = {u.get("id"): u.get("visualId") for u in units}
    team_by = {u.get("id"): u.get("team") for u in units}
    for u in units:
        for ab in (u.get("abilities") or []):
            kind_by[(u.get("id"), ab.get("id"))] = ab.get("kind")
    rows = []
    seen = set()                                   # dedup (att, aid, tgt)
    for ap in (dec.get("attackPlans") or []):
        att = ap.get("unitId")
        if att not in predictor["ctx_by_id"] or att not in pos_by_id:
            continue
        cur_tile = pos_by_id.get(att)
        for ev in (ap.get("evals") or []):
            aid = ev.get("abilityId")
            rk = ev.get("ranked") or []
            if not rk or rk[0].get("dmgMax") is None:   # non-degat (heal/buff) -> hors scope
                continue
            aname = GC.ability_name(aid) or ("id%s" % aid)
            kind = kind_by.get((att, aid)) or "?"
            # UNE cible par eval (ev.targetId) ; `ranked` = tuiles d'attaque (col/row/dmg). On compare
            # a POSITION COURANTE (cur_tile) des deux cotes -> la tuile ranked ne sert qu'au display.
            tgt = ev.get("targetId")
            if tgt is None or (att, aid, tgt) in seen:
                continue
            seen.add((att, aid, tgt))
            r0 = rk[0]
            live = live_main_event(sid, rid, att, tgt, aid)
            eng = engine_main_event(scene, att, tgt, aid, aname, kind, cur_tile)
            st = classify(eng, live)
            # INDICE aura de coups : ecart liveHits vs engHits -> pointe un porteur extraHits a portee.
            hint = None
            if (live.get("hits") is not None and eng.get("hits") is not None
                    and live["hits"] != eng["hits"]):
                hint = hit_aura_hint(units, att, cur_tile, team_by.get(att)) or None
            rows.append({
                "att": att, "attVis": vis_by.get(att), "tgt": tgt, "tgtVis": vis_by.get(tgt),
                "ability": aname, "abilityId": aid, "kind": kind,
                "retClass": live.get("retClass") or eng.get("retClass"),
                "playbook": live.get("playbook"),
                "live": None if "err" in live else (live["min"], live["max"]),
                "eng": None if "err" in eng else (eng["min"], eng["max"]),
                "liveHits": live.get("hits"), "engHits": eng.get("hits"),
                "liveErr": live.get("err"), "engErr": eng.get("err"),
                "displayDmg": (r0.get("dmgMin"), r0.get("dmgMax")),   # decisionView best-tile (routage #103)
                "status": st, "hitAuraHint": hint,
            })
    return rows, None


# ── Reporting (buckets prioritaires) ─────────────────────────────────────────────────────────────
_ORDER = ["MAJOR", "ENG_ZERO", "ENG_NONE", "MINOR", "ORACLE_FAIL", "OK",
          "ORACLE_EMPTY", "OUT_OF_RANGE", "NON_DAMAGE"]


def _fmt_row(r):
    def pr(v):
        return "[%s,%s]" % (v[0], v[1]) if v else "-"
    tail = ""
    if r["liveErr"]:
        tail = " liveErr=%s" % r["liveErr"]
    elif r["engErr"]:
        tail = " engErr=%s" % r["engErr"]
    if r.get("hitAuraHint"):
        tail += " | AURA-COUPS? " + "; ".join(r["hitAuraHint"])
    return ("[%s] u%s(%s)->u%s(%s) live=%s eng=%s disp=%s hits(l/e)=%s/%s%s"
            % (r.get("seed"), r["att"], r["attVis"], r["tgt"], r["tgtVis"], pr(r["live"]), pr(r["eng"]),
               pr(r["displayDmg"]), r["liveHits"], r["engHits"], tail))


def report(rows):
    from collections import Counter, defaultdict
    tot = Counter(r["status"] for r in rows)
    print("\n=== %d TRIPLES (att x ability-degat x cible) ===" % len(rows))
    print("  " + " ".join("%s=%d" % (k, tot.get(k, 0)) for k in _ORDER if tot.get(k)))

    buckets = defaultdict(list)
    for r in rows:
        buckets[(r["ability"], r["kind"], r["retClass"])].append(r)

    def bscore(items):
        c = Counter(x["status"] for x in items)
        return (c["MAJOR"] + c["ENG_ZERO"] + c["ENG_NONE"], c["MINOR"], c["ORACLE_FAIL"])

    print("\n=== BUCKETS (tries : #MAJOR/ZERO/ERR desc, puis MINOR) ===")
    for key in sorted(buckets, key=lambda k: bscore(buckets[k]), reverse=True):
        items = buckets[key]
        c = Counter(x["status"] for x in items)
        cnt = " ".join("%s=%d" % (k, c[k]) for k in _ORDER if c.get(k))
        aname, kind, retc = key
        print("\n[%s / %s%s]  n=%d  %s"
              % (aname, kind, ("" if not retc else " / " + str(retc)), len(items), cnt))
        # exemples : 1 pire par statut de GAP (MAJOR d'abord ; OK/OUT_OF_RANGE/NON_DAMAGE muets)
        for stt in _ORDER:
            if stt in ("OK", "OUT_OF_RANGE", "NON_DAMAGE"):
                continue
            ex = [x for x in items if x["status"] == stt]
            if not ex:
                continue
            # pire = plus grand ecart relatif si live present, sinon 1er
            def gap(x):
                if not x["live"] or not x["eng"]:
                    return 9e9
                lm, lM = x["live"]
                em, eM = x["eng"]
                return max(abs(em - lm), abs(eM - lM))
            ex.sort(key=gap, reverse=True)
            print("    %-11s %s" % (stt, _fmt_row(ex[0])))


def sweep_build(sid, seed, a):
    """Build un runner ISOLE (seede + roster), balaye, dispose. Renvoie les rows taggees seed."""
    cmd = [sys.executable, sibling_script("rl_duel.py"), "build", "--seed", str(seed), "--state-file", STATE_REL]
    for flag, val in (("--p-units", a.p_units), ("--a-units", a.a_units),
                      ("--board", a.board), ("--board-pool", a.board_pool)):
        if val:
            cmd += [flag, str(val)]
    print("[sweep] seed %s build: %s" % (seed, " ".join(cmd[4:])))
    bp = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace")
    if not STATE.exists():
        print("[sweep] seed %s build KO:\n%s\n%s" % (seed, bp.stdout[-1500:], bp.stderr[-1500:]))
        return []
    try:
        st = json.loads(STATE.read_text())
        rid = st["runnerId"]; my_team = st.get("myTeam", 1)
        rows, err = build_rows(sid, rid, my_team, a.max_turns, a.topk)
        if err:
            print("[sweep] seed %s: %s" % (seed, err)); return []
        for r in (rows or []):
            r["seed"] = seed
        print("[sweep] seed %s -> %d rows" % (seed, len(rows or [])))
        return rows or []
    finally:
        subprocess.run([sys.executable, sibling_script("rl_duel.py"), "dispose", "--state-file", STATE_REL],
                       capture_output=True, text=True, encoding="utf-8", errors="replace")


def main(argv):
    ap = argparse.ArgumentParser()
    ap.add_argument("--seed", type=int, default=777)
    ap.add_argument("--seeds", default=None,
                    help="liste de seeds separees par virgule -> balaye chacune (build/dispose isole) "
                         "et AGREGE les buckets (carte d'ecarts multi-roster). Prime sur --seed.")
    ap.add_argument("--runner", type=int, default=None,
                    help="reutilise un runner EXISTANT (ne build/dispose rien) ; sinon build seede")
    ap.add_argument("--p-units", default=None)
    ap.add_argument("--a-units", default=None)
    ap.add_argument("--board", default=None)
    ap.add_argument("--board-pool", default=None)
    ap.add_argument("--max-turns", type=int, default=6)
    ap.add_argument("--topk", type=int, default=3, help="(reserve) borne les RPC par ability")
    ap.add_argument("--json", dest="json_out", default=None, help="dump JSON des rows")
    a = ap.parse_args(argv)

    sid = R._resolve_session()
    print("[sweep] session %s" % sid)

    if a.runner is not None:
        rows, err = build_rows(sid, a.runner, 1, a.max_turns, a.topk)
        if err:
            print("[sweep] %s" % err); return 1
        for r in (rows or []):
            r["seed"] = "runner%s" % a.runner
    else:
        seeds = ([int(s) for s in a.seeds.split(",") if s.strip()] if a.seeds else [a.seed])
        rows = []
        for sd in seeds:
            rows += sweep_build(sid, sd, a)

    if not rows:
        print("[sweep] aucun triple de degat capture."); return 1
    report(rows)
    if a.json_out:
        Path(a.json_out).write_text(json.dumps(rows, indent=2), encoding="utf-8")
        print("\n[sweep] %d rows -> %s" % (len(rows), a.json_out))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
