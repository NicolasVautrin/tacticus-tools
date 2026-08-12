"""#977 -- confrontation LIVE des cinq faces DECISION du lot (WorldEaters / Genestealer / Death
Guard / Black Templars), sur UN SEUL montage co-injecte.

    python probe_977_faces_decision_kit.py [--state-file <absolu>] [--seed 777] [--board MC1_67]

QUATRE etages, et ils ne mesurent pas la meme chose :

  0. REGISTRES (offline) -- chacune des cinq est-elle portee, et par LEQUEL des quatre registres ?
     C'est la seule etape qui repond a « le port existe » ; les trois suivantes repondent a « il
     est JUSTE ».
  1. MONTAGE -- `rl_duel build` avec les CINQ porteurs dans la MEME equipe (dont une MoW), positions
     FORCEES par `--place` / `--a-place`. Publie la preuve de co-injection.
  2. ORACLE NC (`ncEvaluate`) -- pour `1131` / `1141` / `1043` le natif invoque
     `EvaluateNonComparable(caster, UnitPosition(P))` POSITION PAR POSITION et rend le `best` de
     son `Bucket` local. Le port expose la meme unite (`playbook.evaluate_at(ctx, P)`), donc la
     confrontation est position-a-position, pas seulement sur l'argmax final.
  3. ORACLE COMPARABLE -- `1165` / `1168` : `aiPlaybookPredict` (les `ProbableDamageEvent` que
     `<Ability>Playbook$$MakeDamagePredictions` construit) confronte au chemin generique du port,
     et le terme `CalculateCasterPositionUtility` de `1165` mesure a part.

CE QUE CE PROBE NE PROUVE PAS. `ncEvaluate` invoque le wrapper `Evaluate/3` du playbook natif :
il donne l'UTILITE et la CIBLE, pas la decision finale de l'IA (qui passe encore par les tiers de
priorite et le `Bucket` du tactic). Un accord ici est necessaire, pas suffisant.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

PYDIR = Path(__file__).resolve().parent
sys.path.insert(0, str(PYDIR))

#: Les cinq du lot -> (nom, visualId du porteur, registre VISE).
CASES = [
    (1131, "JakhalStimms", "worldJakhal", "noncomparable.PLAYBOOKS"),
    (1141, "OverwhelmingWrath", "worldEightbound", "noncomparable.PLAYBOOKS"),
    (1043, "ThunderousAssault", "templSwordBrother", "noncomparable.PLAYBOOKS"),
    (1165, "MightFromBelow", "genesPatriarch", "playbook.REGISTRY"),
    (1168, "EntropyCannons", "deathCrawler", "chemin GENERIQUE (rien a porter)"),
]
_NC_IDS = (1131, 1141, 1043)


# --- etape 0 : les quatre registres, offline ------------------------------------------------------

def step0_registres(verbose: bool = True) -> dict:
    from engine.playbook.noncomparable import PLAYBOOKS
    from engine.playbook.base import REGISTRY
    from engine.entities.abilities.active_ability import _SPECIAL_ABILITY_CLASSES
    from engine.playbook.bespoke import BESPOKE_SELFCAST
    out = {}
    for aid, name, carrier, vise in CASES:
        where = []
        if aid in PLAYBOOKS:
            where.append("noncomparable.PLAYBOOKS/%s" % type(PLAYBOOKS[aid]).__name__)
        if aid in REGISTRY:
            where.append("playbook.REGISTRY/%s" % type(REGISTRY[aid]).__name__)
        if name in _SPECIAL_ABILITY_CLASSES:
            where.append("_SPECIAL_ABILITY_CLASSES")
        if aid in BESPOKE_SELFCAST:
            where.append("BESPOKE_SELFCAST")
        out[aid] = {"name": name, "carrier": carrier, "vise": vise, "registres": where}
    if verbose:
        print("\n[977/0] LES QUATRE REGISTRES DE DECISION")
        for aid, name, _c, vise in CASES:
            print("   %d %-20s vise=%-34s -> %s"
                  % (aid, name, vise, out[aid]["registres"] or ["AUCUN"]))
    return out


# --- harnais RPC ---------------------------------------------------------------------------------

def _rpc_mod():
    from rl_collect_batch import _resolve_session, _rpc          # noqa: E402
    return _resolve_session, _rpc


def _r(rpc, sid, m, b, t=120):
    return (rpc(sid, m, [b], timeout=t).get("result") or {})


# --- etape 1 : le montage ------------------------------------------------------------------------

#: Le noeud de la mesure. Positions FORCEES pour que les trois NC soient DISCRIMINANTES :
#: * `worldJakhal` en (3,4) touche TROIS ennemis (3,5)/(4,4)/(2,4) ; l'intersection d'AoE vaut 2
#:   pour la cible (3,5) et 1 pour les deux autres -> utilite 3 / 2 / 2, un argmax NON degenere ;
#: * `worldEightbound` en (2,5) touche (3,5) et (2,4) -> compte 2 depuis l'origine ;
#: * `templSwordBrother` en (4,3) touche (4,4) -- une cible poussable, arc arriere non vide.
_PLACE = ["worldJakhal:3,4", "worldEightbound:2,5", "genesPatriarch:1,4",
          "templSwordBrother:4,3"]
_A_PLACE = ["necroWarden:3,5", "necroDestroyer:4,4", "tauCrisis:2,4", "ultraTitus:5,4"]


def step1_montage(state_file: Path, seed: int, board: str, verbose: bool = True) -> dict:
    state_file.parent.mkdir(parents=True, exist_ok=True)
    state_file.unlink(missing_ok=True)
    cmd = [sys.executable, "rl_duel.py", "build", "--seed", str(seed), "--board", board,
           "--state-file", str(state_file), "--no-ai",
           "--p-units", "worldJakhal,worldEightbound,genesPatriarch,templSwordBrother",
           "--p-mow", "deathCrawler",
           "--a-units", "necroWarden,necroDestroyer,tauCrisis,ultraTitus"]
    for p in _PLACE:
        cmd += ["--place", p]
    for p in _A_PLACE:
        cmd += ["--a-place", p]
    proc = subprocess.run(cmd, cwd=str(PYDIR), capture_output=True, text=True,
                          encoding="utf-8", errors="replace")
    if not state_file.exists():
        raise RuntimeError("build KO : %s" % ((proc.stderr or proc.stdout or "")[-1500:]))
    rid = int(json.loads(state_file.read_text())["runnerId"])
    if verbose:
        print("\n[977/1] MONTAGE : runner %d, board %s, seed %d" % (rid, board, seed))
    return {"runnerId": rid, "board": board, "seed": seed}


def _co_injection(rpc, sid, rid: int, verbose: bool = True) -> dict:
    """La preuve que les CINQ porteurs sont dans la MEME bataille et la MEME equipe.

    ⚠ DEUX canaux, pas un : `observeBattle.units` ne porte PAS les MACHINES OF WAR (canal
    `decisionView.mows`, cf. `loki_custom.MortisRoundPlaybook._is_displaceable`). Chercher
    `deathCrawler` dans le seul premier canal aurait rendu un « porteur absent » FAUX.
    L'identite d'unite est `squadId` (= `dv.id`), pas `entityId` -- cf. `rpc-snapshot.ts`."""
    o = _r(rpc, sid, "observeBattle", {"runnerId": rid})
    rows = [u for u in (o.get("units") or []) if not u.get("isDead")]
    by_vis = {}
    for u in rows:
        by_vis.setdefault(u.get("visualId"), []).append(u)
    dv = _r(rpc, sid, "decisionView", {"runnerId": rid, "allAbilities": True}, 180)
    for m in (dv.get("mows") or []):
        # ⚠ TROIS ids sur une MoW (`id` / `machineId` / `casterId`) et ce n'est PAS `id` que les
        # RPC d'oracle acceptent : `aiPlaybookPredict` rend « unit 75 not found » sur `id`, et
        # repond sur `casterId`. Mesure #977.
        by_vis.setdefault(m.get("visualId"), []).append(
            {"squadId": m.get("casterId"), "teamId": m.get("team"), "isMow": True,
             "col": (m.get("pos") or {}).get("col") if m.get("pos") else None,
             "row": (m.get("pos") or {}).get("row") if m.get("pos") else None})
    out = {}
    for aid, name, carrier, _v in CASES:
        us = by_vis.get(carrier) or []
        out[carrier] = None if not us else {
            "id": int(us[0].get("squadId")), "teamId": us[0].get("teamId"),
            "isMow": bool(us[0].get("isMow")),
            "pos": (us[0].get("col"), us[0].get("row"))}
    teams = {v["teamId"] for v in out.values() if v and v["teamId"] is not None}
    ok = (len([v for v in out.values() if v]) == len(CASES)) and len(teams) == 1
    if verbose:
        print("[977/1] CO-INJECTION : %d/%d porteurs presents, equipes distinctes = %d -> %s"
              % (len([v for v in out.values() if v]), len(CASES), len(teams),
                 "OK" if ok else "ECHEC"))
        for c, v in out.items():
            print("   %-22s %s" % (c, v))
    return {"ok": ok, "carriers": out}


# --- le CONTEXTE du port, construit des MEMES RPC ------------------------------------------------

def _nc_ctx(rpc, sid, rid: int, uid: int):
    from engine.ai import context as _ai_ctx
    from engine.playbook import noncomparable as PB
    from engine import weights
    from engine.playbook import scene as _scene
    dv = _r(rpc, sid, "decisionView", {"runnerId": rid, "allAbilities": True, "maxRank": 32}, 180)
    mov = _r(rpc, sid, "aiMovableTiles", {"runnerId": rid}, 60)
    mov_by_unit = {u.get("unitId"): u for u in (mov.get("units") or [])}
    predictor = _scene.build_predictor(lambda m, b, t: _r(rpc, sid, m, b, t), rid)
    c = _ai_ctx.build(lambda m, b, t: _r(rpc, sid, m, b, t), rid, dv, mov_by_unit, uid,
                      weights.load(), predictor)
    return c, PB.NCContext(
        uid=c.uid, origin=c.origin, reach_nc=c.reach_nc, epos=c.epos, fpos=c.fpos,
        enemies=c.enemies, neigh_by_pos=c.neigh_by_pos, walkable_by_pos=c.walkable_by_pos,
        plan=c.plans.get(c.uid) or {}, plans=c.plans, hp_cur_by_id=c.hp_cur_by_id,
        elev_by_pos=c.elev_by_pos, ability_targets=c.ability_targets, wt=c.wt,
        is_temporary_by_pos=c.is_temporary_by_pos, effects_by_pos=c.effects_by_pos,
        obs_units=c.obs_units, tile_id_by_pos=c.tile_id_by_pos,
        active_levels=c.active_ability_levels, ability_config=c.heal_config,
        units=c.units, cast_from_tiles=c.cast_from_tiles, scene=c.scene)


# --- etape 2 : ORACLE NC, position par position ---------------------------------------------------

def step2_oracle_nc(rpc, sid, rid: int, carriers: dict, verbose: bool = True) -> dict:
    from engine.playbook import noncomparable as PB
    out = {}
    for aid, name, carrier, _v in CASES:
        if aid not in _NC_IDS:
            continue
        row = carriers.get(carrier)
        if not row:
            out[aid] = {"ok": None, "skipped": "porteur absent"}
            continue
        uid = row["id"]
        nat = _r(rpc, sid, "ncEvaluate",
                 {"runnerId": rid, "unitId": uid, "abilityType": aid, "sweep": True}, 300)
        positions = nat.get("positions") or []
        _c, nc = _nc_ctx(rpc, sid, rid, uid)
        pb = PB.playbook_for(aid)
        # ⚠ `ncEvaluate` rend, pour la cible, les 32 bits BAS du `BEntityId` (`action.targetLow`) --
        # c'est-a-dire un POINTEUR d'objet, PAS le `squadId` que `decisionView` (et le port)
        # manipulent. Les quatre valeurs mesurees sont espacees de 0x130 exactement : c'est
        # l'allocation heap, aucune table publiee ne la traduit. On NE FABRIQUE PAS de mapping :
        # cet etage confronte l'UTILITE (sans id) et la CONSISTANCE de la cible (meme pointeur natif
        # <=> meme id porte, sur toutes les positions). L'accord au niveau des IDS est etabli par les
        # deux etages SUIVANTS, qui parlent tous deux en `squadId` : l'ordre `fromHere` (2bis) et la
        # decision native `aiDryRunAllUnits` (2ter).
        rows = []
        for p in positions:
            P = tuple(p.get("pos") or (None, None))
            _act = p.get("action") or {}
            n_tgt = _act.get("targetLow")
            if P[0] is None:
                # `UnitPosition` nulle : le natif la publie quand la tuile n'a pas de position. Le
                # port n'a rien a evaluer -- on l'ecarte en le DISANT, jamais en accord.
                rows.append({"pos": None, "nat_util": p.get("util"), "port_util": None,
                             "nat_tgt": n_tgt, "port_tgt": None,
                             "util_ok": None, "tgt_ok": None})
                continue
            n_util = p.get("util")
            r = pb.evaluate_at(nc, P) if hasattr(pb, "evaluate_at") else None
            p_util = None if r is None else round(float(r[1]), 4)
            p_tgt = None if r is None else r[0]
            n_util_r = None if not isinstance(n_util, (int, float)) else round(float(n_util), 4)
            rows.append({"pos": P, "nat_util": n_util_r, "port_util": p_util,
                         "nat_tgt": n_tgt, "port_tgt": p_tgt,
                         "util_ok": n_util_r == p_util})
        cmp_rows = [x for x in rows if x["util_ok"] is not None]   # hors position nulle
        scored = [x for x in cmp_rows if x["nat_util"] is not None]
        util_ok = sum(1 for x in cmp_rows if x["util_ok"])
        n_cmp = len(cmp_rows)
        # CONSISTANCE de la cible : le pointeur natif et l'id du port doivent former une BIJECTION
        # sur les positions scorees des DEUX cotes. Un renommage constant passe, une PERMUTATION
        # (le natif change de cible la ou le port n'en change pas) est vue.
        pairs = [(x["nat_tgt"], x["port_tgt"]) for x in cmp_rows
                 if x["nat_tgt"] is not None and x["port_tgt"] is not None]
        bij = (len(set(a for a, _ in pairs)) == len(set(dict(pairs).items()))
               and len(set(b for _, b in pairs)) == len(set(dict(pairs).items())))
        # ⚠ CECITE STRUCTURELLE DU CAPTEUR, et elle s'ETABLIT ici -- elle ne se suppose pas.
        # `ncEvaluate` decode `Bucket+0x20` (le champ que `Bucket$$AddAction` ecrit). Or
        # `NonComparablePlaybook<T>$$GenerateBucketWithMultipleStrategies` -- la voie de `1043` --
        # n'appelle JAMAIS `AddAction` sur le bucket externe : il passe par
        # `Bucket$$AddActionToBucket`, qui range l'action dans un SOUS-bucket de la `SortedList`
        # a `+0x28`. Le champ `+0x20` reste donc nul MEME quand une action existe.
        # Les DEUX faits qui le prouvent, tous deux mesures ici : (a) le natif rend `bucket: empty`
        # sur TOUTES les positions ; (b) `aiDryRunAllUnits` (etage 2ter) propose quand meme
        # l'ability. Tant que (a) tient, l'etage rend NON CONFRONTE -- jamais un vert.
        all_empty = all(p.get("bucket") == "empty" for p in positions) and bool(positions)
        blind = all_empty and any(x["port_util"] is not None for x in cmp_rows)
        out[aid] = {"ok": None if blind else (bool(cmp_rows) and util_ok == n_cmp and bij),
                    "capteurAveugle": blind, "toutesBucketsVides": all_empty,
                    "nComparees": n_cmp, "bijectionCible": bij, "paires": sorted(set(pairs)),
                    "playbookClass": nat.get("playbookClass"), "evalName": nat.get("evalName"),
                    "error": nat.get("error"), "uid": uid,
                    "nPositions": len(rows), "nScoredNatif": len(scored),
                    "utilOk": util_ok, "rows": rows}
        if verbose:
            print("\n[977/2] %d %s (u%d, %s) -- eval=%s"
                  % (aid, name, uid, nat.get("playbookClass"), nat.get("evalName")))
            if nat.get("error"):
                print("   ERREUR RPC : %s" % nat["error"])
            print("   positions=%d (comparables %d), scorees NATIF=%d | utilite %d/%d | "
                  "bijection cible=%s" % (len(rows), n_cmp, len(scored), util_ok, n_cmp, bij))
            if blind:
                print("   CAPTEUR AVEUGLE (ETABLI) : toutes les buckets NATIVES sont vides alors "
                      "que le port score -- `GenerateBucketWithMultipleStrategies` n'ecrit jamais "
                      "`Bucket+0x20`. Verdict reporte sur l'etage 2ter.")
            for x in rows[:14]:
                flag = "  " if x["util_ok"] in (True, None) else "XX"
                print("     %s %-8s nat=(u=%s,ptr=%s)  port=(u=%s,t=%s)"
                      % (flag, x["pos"], x["nat_util"], x["nat_tgt"],
                         x["port_util"], x["port_tgt"]))
            if len(rows) > 14:
                print("     ... %d de plus" % (len(rows) - 14))
            print("     paires (ptr natif -> id port) : %s" % sorted(set(pairs)))
    return out


def step2bis_ordre_selecteur(rpc, sid, rid: int, carriers: dict, verbose: bool = True) -> dict:
    """L'ORDRE du selecteur, en `squadId` -- le seul etage qui confronte les CIBLES par leur id.

    `abilityTargets.fromHere` EST `GetValidTargets(unit, position COURANTE, ability)`, publie dans
    l'ordre du selecteur natif. Le port reconstruit cette liste depuis le VOISINAGE NATIF de la
    tuile (`_targets.eligible_units_at_position`) : l'egalite ELEMENT PAR ELEMENT, ordre compris,
    est ce qui autorise a appliquer la meme regle aux positions de MOVE, ou aucune vue RPC
    n'existe."""
    from engine.playbook.noncomparable._targets import eligible_units_at_position
    out = {}
    for aid, name, carrier, _v in CASES:
        if aid not in _NC_IDS:
            continue
        row = carriers.get(carrier)
        if not row:
            out[aid] = {"ok": None, "skipped": "porteur absent"}
            continue
        uid = row["id"]
        at = _r(rpc, sid, "abilityTargets", {"runnerId": rid, "unitId": uid, "abilityType": aid})
        fh = []
        for u in (at.get("units") or []):
            for a in (u.get("abilities") or []):
                if a.get("abilityId") == aid:
                    fh = [t.get("targetId") for t in (a.get("fromHere") or [])
                          if t.get("kind") == "unit"]
        _c, nc = _nc_ctx(rpc, sid, rid, uid)
        self_cast = (aid == 1141)
        port = [t for t, _p in eligible_units_at_position(nc, aid, nc.origin,
                                                          self_cast=self_cast)]
        out[aid] = {"ok": fh == port, "origin": nc.origin, "fromHere": fh, "port": port,
                    "voisins": (nc.neigh_by_pos or {}).get(nc.origin)}
        if verbose:
            print("\n[977/2bis] %d %s -- ordre du selecteur a l'origine %s"
                  % (aid, name, nc.origin))
            print("   fromHere NATIF : %s" % fh)
            print("   port           : %s   -> %s" % (port, "OK" if fh == port else "ECART"))
    return out


def step2ter_decision(rpc, sid, rid: int, carriers: dict, verbose: bool = True) -> dict:
    """La DECISION native de chaque porteur (`aiDryRunAllUnits`) vs celle du port
    (`noncomparable.choose_action`), en `squadId`.

    C'est le seul etage qui traverse le generateur ENTIER (tiers de priorite, gates amont, Bucket du
    tactic). Il est aussi le SEUL a pouvoir juger `1043` : `ncEvaluate` decode `Bucket+0x20`, or
    `NonComparablePlaybook<T>$$GenerateBucketWithMultipleStrategies` n'ecrit JAMAIS ce champ -- il
    passe par `Bucket$$AddActionToBucket`, qui range l'action dans un SOUS-bucket de la `SortedList`
    a `+0x28`. Le capteur rend donc `bucket: "empty"` pour 1043 MEME quand une action existe."""
    from engine.playbook import noncomparable as PB
    nat_all = _r(rpc, sid, "aiDryRunAllUnits", {"runnerId": rid}, 300)
    by_unit = {int(u["unitId"]): u for u in (nat_all.get("units") or [])
               if u.get("unitId") is not None}
    out = {}
    for aid, name, carrier, _v in CASES:
        if aid not in _NC_IDS:
            continue
        row = carriers.get(carrier)
        if not row:
            out[aid] = {"ok": None, "skipped": "porteur absent"}
            continue
        uid = row["id"]
        prop = (by_unit.get(uid) or {}).get("proposed") or []
        nat_ab = next((m for m in prop if m.get("cls") == "ActiveAbilityMessage"), None)
        nat_mv = next((m for m in prop if m.get("cls") == "MoveUnitMessage"), None)
        nat = {"ability": (nat_ab or {}).get("abilityType"),
               "target": (nat_ab or {}).get("targetId"),
               "to": ((nat_mv or {}).get("to") or {}).get("col") is not None
               and ((nat_mv["to"]["col"], nat_mv["to"]["row"])) or None}
        _c, nc = _nc_ctx(rpc, sid, rid, uid)
        cands = PB.playbook_for(aid).generate_candidates(nc)
        port = cands[0] if cands else None
        ok = (port is not None and nat["ability"] == aid
              and port["target"] == nat["target"] and port["to"] == nat["to"])
        out[aid] = {"ok": bool(ok), "natif": nat, "port": port, "uid": uid}
        if verbose:
            print("\n[977/2ter] %d %s (u%d) -- DECISION" % (aid, name, uid))
            print("   natif : ability=%s target=%s to=%s"
                  % (nat["ability"], nat["target"], nat["to"]))
            print("   port  : %s   -> %s" % (port, "OK" if ok else "ECART"))
    return out


# --- etape 3 : les deux COMPARABLE ----------------------------------------------------------------

def step3_comparable(rpc, sid, rid: int, carriers: dict, verbose: bool = True) -> dict:
    """`1165` / `1168` : la PREDICTION generique, puis le terme de POSITION propre a `1165`."""
    from engine.playbook import prediction as PRED
    from engine.playbook import get_playbook_or_default
    out = {}
    for aid, name, carrier, _v in CASES:
        if aid in _NC_IDS:
            continue
        row = carriers.get(carrier)
        if not row:
            out[aid] = {"ok": None, "skipped": "porteur absent"}
            continue
        uid = row["id"]
        # La `Scene` du port est GLOBALE : on la construit depuis une unite ORDINAIRE, jamais
        # depuis la MoW (qui n'a ni `PositionComponent` ni entree `decisionView.units`).
        anchor = next((carriers[c2]["id"] for _a, _n, c2, _vv in CASES
                       if carriers.get(c2) and not carriers[c2].get("isMow")), uid)
        c, nc = _nc_ctx(rpc, sid, rid, anchor)
        o = _r(rpc, sid, "observeBattle", {"runnerId": rid})
        my_team = row["teamId"]
        foes = [u for u in (o.get("units") or [])
                if not u.get("isDead") and u.get("teamId") != my_team]
        rec = {"uid": uid, "events": []}
        for f in foes:
            tid = int(f["squadId"])
            nat = _r(rpc, sid, "aiPlaybookPredict",
                     {"runnerId": rid, "unitId": uid, "targetId": tid, "abilityType": aid}, 180)
            evs = nat.get("events") or []
            if not evs:
                continue
            # `attack_pos` : la tuile du caster. Une MoW n'en a pas (`posSrc = machine:NullPosition`
            # cote natif) -> `None`, jamais l'origine d'une AUTRE unite.
            pos = None if row.get("isMow") else _nc_ctx(rpc, sid, rid, uid)[0].origin
            port = PRED.make_damage_predictions(c.scene, uid, tid, aid, name, attack_pos=pos)
            rec["events"].append({
                "target": tid,
                "nat": [(e.get("healthDmgMin"), e.get("healthDmgMax"), e.get("appliedHits"))
                        for e in evs],
                "port": [(p.prediction.accurate_health_damage.min,
                          p.prediction.accurate_health_damage.max,
                          p.prediction.applied_hits) for p in (port or [])],
            })
        for e in rec["events"]:
            e["ok"] = e["nat"] == e["port"]
        rec["ok"] = bool(rec["events"]) and all(e["ok"] for e in rec["events"])
        if aid == 1165:
            cc = _nc_ctx(rpc, sid, rid, uid)[0]
            pb = get_playbook_or_default(aid)
            rec["caster_position_utility"] = {
                str(P): round(pb.calculate_caster_position_utility(cc, P, aid), 4)
                for P in (cc.reach_nc or [])[:8]}
            rec["W"] = cc.wt.sub("ActiveAbilities", "MIGHTFROMBELOW_ExistingAdjacentDecoy")
        out[aid] = rec
        if verbose:
            print("\n[977/3] %d %s (u%d) -- prediction generique vs `MakeDamagePredictions` natif"
                  % (aid, name, uid))
            for e in rec["events"]:
                print("     %s cible %s : nat=%s port=%s"
                      % ("  " if e["ok"] else "XX", e["target"], e["nat"], e["port"]))
            if not rec["events"]:
                print("     AUCUN event natif -- NON CONFRONTE (ability sans cible legale ici)")
            if aid == 1165:
                print("     CalculateCasterPositionUtility (W=%s) : %s"
                      % (rec.get("W"), rec.get("caster_position_utility")))
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--state-file", default=str(PYDIR.parent.parent / "logs" / "probe977.json"))
    ap.add_argument("--seed", type=int, default=777)
    ap.add_argument("--board", default="MC1_67")
    ap.add_argument("--keep", action="store_true", help="ne pas disposer le runner a la fin")
    ap.add_argument("--offline", action="store_true", help="etape 0 seule")
    a = ap.parse_args()

    verdict = {"step0": step0_registres()}
    if a.offline:
        print("\n[977] OFFLINE : etape 0 seule.")
        return 0

    resolve, rpc = _rpc_mod()
    sid = resolve()
    sf = Path(a.state_file).resolve()
    rid = None
    try:
        m = step1_montage(sf, a.seed, a.board)
        rid = m["runnerId"]
        verdict["step1"] = m
        co = _co_injection(rpc, sid, rid)
        verdict["co_injection"] = co
        verdict["step2"] = step2_oracle_nc(rpc, sid, rid, co["carriers"])
        verdict["step2bis"] = step2bis_ordre_selecteur(rpc, sid, rid, co["carriers"])
        verdict["step2ter"] = step2ter_decision(rpc, sid, rid, co["carriers"])
        verdict["step3"] = step3_comparable(rpc, sid, rid, co["carriers"])
    finally:
        if rid is not None and not a.keep:
            try:
                _r(rpc, sid, "disposeRunner", {"runnerId": rid}, 60)
            except Exception:
                pass

    print("\n[977] BILAN -- un `ECART` a un seul etage suffit a rougir l'ability")
    bad = 0
    for aid, name, _c, _v in CASES:
        etages = []
        for k in ("step2", "step2bis", "step2ter", "step3"):
            rec = (verdict.get(k) or {}).get(aid)
            if rec is None:
                continue
            st = rec.get("ok")
            etages.append("%s=%s" % (k, "OK" if st is True
                                     else ("NC" if st is None else "ECART")))
            if st is False:
                bad += 1
        print("   %d %-20s -> %s" % (aid, name, " ".join(etages) or "AUCUN ETAGE"))
    out = PYDIR.parent.parent / "logs" / "probe977_verdict.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(verdict, indent=1, default=str), encoding="utf-8")
    print("   verdict complet : %s" % out)
    return 1 if bad else 0


if __name__ == "__main__":
    raise SystemExit(main())
