#!/usr/bin/env python
"""#487-r2 -- la face DECISION de `1088 HellfyreMissileRack`, CONFRONTEE au natif.

CE QUE CE PROBE DISCRIMINE, et pourquoi il n'etait pas jouable avant le 2026-08-15.

`IdunBattle.AI.Playbook.Loki.HellfyreMissileRackPlaybook` est un **NonComparable** dont l'utilite
est un COMPTAGE -- `Fix64(Sum(Select(GetAllEnemiesOf(owner), u => HasTakenDamageOfDamageProfile
ThisTurn(u, 0xd = Psychic) ? 1 : 0)))` -- et dont le `.cctor` ecrit `Fix64(1)` dans le premier champ
du `Bucket`, donc **`MIN_UTILITY = 1`** (et non `null`, cf. la correction de #487-r1). Le gate MORD :
aucun ennemi n'ayant encaisse de Psychic ce tour, l'utilite vaut `0 < 1`, le bucket reste VIDE, et
l'ability **n'est pas proposee**.

Le substrat de cette utilite est `ActorStatisticsComponent + 0x80`. Il n'etait publie par AUCUN
canal de seed, donc la face LIVE du port rendait `None` = **non mesure** et s'abstenait en le
DISANT. Le capteur est desormais ARME (#10008) : ce n'est PAS un scalaire `receivedDamageThisTurn`
mais un `Dictionary<DamageProfileType, int>` nomme **`ReceiveDamageTypeThisTurn`** -- un compte
d'instances PAR PROFIL. Il est publie sous `actorStats.units[].receiveDamageTypeThisTurn`, consomme
par `snapshot._seed_received_damage_types`, et arrive au playbook par
`UnitComponent.received_damage_this_turn` -> `Scene.has_taken_damage_of_profile_this_turn`.

DEUX REGIMES, et c'est le contraste qui fait la mesure -- pas un bras isole :

  * **NON ARME** : personne n'a pris de Psychic ce tour -> utilite `0 < 1` -> bucket VIDE cote
    natif, aucun candidat cote port. C'est le regime ou le gate REFUSE.
  * **ARME** : Ahriman caste `1102 Doombolt` (multi-cible Psychic) AVANT que Toth ne decide, dans le
    MEME tour d'equipe -> N ennemis armes -> utilite `N >= 1` -> bucket NON VIDE, candidat rendu.

Un probe qui ne jouerait que le second ne prouverait rien : il ne separerait pas « le gate passe »
de « le gate n'existe pas ». Et un probe qui ne jouerait que le premier ne separerait pas « le gate
refuse » de « le canal est muet » -- c'est exactement l'etat d'AVANT le capteur, et c'est pourquoi
le probe imprime `canal_mesure` a chaque bras.

DEUX ORACLES NATIFS, et ils ne voient pas la meme chose (meme raison qu'au #1066) :
  * `ncPlaybookPredict(via="evaluate")` invoque `Evaluate/3` -- il rend le BUCKET (vide ou non) et
    ne traverse PAS `ShouldEvaluate` ;
  * `aiDryRunAllUnits` passe par `CalculateNextActionForUnit`, donc par le GENERATEUR complet.
Les deux sont lus ; un `ok:false` LEVE (un capteur muet se lirait sinon comme un refus du gate).

GEOMETRIE, heritee de `probe_487_hellfyre_missile_rack.py` et choisie la-bas pour une raison qui
vaut ici aussi : EXACTEMENT 3 ennemis a `d(Ahriman) <= 2` (`Doombolt` repartit `nrOfHits = 3`
« evenly », `3 % 3 == 0` -> 1 coup chacun, donc l'ensemble arme ne depend pas de l'ordre de tri),
plus un 4e ennemi HORS de portee -- le TEMOIN NEGATIF, vivant et a portee de Hellfyre, mais sans
Psychic : l'utilite doit valoir 3, pas 4.

Usage : python probe_487r2_hellfyre_decision_live.py [--seed 777] [--board MC1_67]
ASCII only.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

import rl_collect_batch as R

PYDIR = Path(__file__).resolve().parent
sys.path.insert(0, str(PYDIR))

HELLFYRE = 1088
DOOMBOLT = 1102
TOTH = "thousTerminator"
AHRIMAN = "thousAhriman"
DOOMBOLT_RANGE = 2          # `GetNumberConstant(0x16 = range)` de la config 1102
PSYCHIC = 13                # `DamageProfileType.Psychic` -- le profil TESTE par le predicat

#: Ce qui doit changer pour que ce probe puisse changer d'avis (#486-r12).
DECLENCHEUR = {
    "chemins": ("scripts/python/engine/playbook/noncomparable/hellfyre_missile_rack.py",
                "scripts/python/engine/playbook/scene.py",
                "scripts/python/engine/runner/snapshot.py",
                "frida/hooks/game/receive-damage-types.ts",
                "frida/hooks/features/ai-step/rpc-snapshot.ts",
                "data/seed-bc.json", "data/boards/**"),
    "build": True,
    "toujours": False,
    "raison": "Il confronte au NATIF le gate `MIN_UTILITY = 1` de la face DECISION de 1088, dans "
              "les DEUX regimes (arme / non arme), et il est le SEUL consommateur de bout en bout "
              "du canal `receiveDamageTypeThisTurn` (capteur -> seeder -> Scene -> playbook).",
}


def _rpc(sid, m, b=None, t=90):
    r = R._rpc(sid, m, [b] if b is not None else [], timeout=t)
    return r.get("result") if isinstance(r, dict) and "result" in r else r


def _build(state_file, seed, board):
    argv = [sys.executable, "rl_duel.py", "build", "--seed", str(seed), "--board", board,
            "--state-file", state_file,
            "--p-units", f"{TOTH},{AHRIMAN}",
            "--a-units", "orksNob,orksWarboss,orksBigMek,orksRuntherd",
            "--place", f"{AHRIMAN}:3,3", "--place", f"{TOTH}:1,3",
            "--a-place", "orksNob:3,4", "--a-place", "orksWarboss:4,4",
            "--a-place", "orksBigMek:2,4", "--a-place", "orksRuntherd:1,6",
            "--hp-target", "400000", "--hp-player", "400000", "--no-ai"]
    p = subprocess.run(argv, cwd=str(PYDIR), capture_output=True, text=True,
                       encoding="utf-8", errors="replace")
    sf = Path(state_file)
    if not sf.exists():
        return None, (p.stderr or p.stdout or "")[-1500:]
    return json.loads(sf.read_text())["runnerId"], None


def _oracle_bucket(sid, rid: int, caster_id: int) -> dict:
    """`ncPlaybookPredict(via="evaluate")` -- le BUCKET natif du playbook.

    ⚠ UN ECHEC RENDU N'EST PAS UNE MESURE : `ok: false` LEVE. Sans cela un capteur muet se lirait
    comme « bucket vide », c'est-a-dire comme le refus meme qu'on cherche a mesurer -- les deux
    bras rendraient alors le meme verdict pour des raisons opposees."""
    r = _rpc(sid, "ncPlaybookPredict",
             {"runnerId": rid, "unitId": caster_id, "abilityType": HELLFYRE, "via": "evaluate"}, 300)
    if not isinstance(r, dict) or not r.get("ok"):
        raise RuntimeError("ncPlaybookPredict a ECHOUE (capteur muet, PAS un refus) : %s"
                           % json.dumps(r, default=str)[:400])
    return {"classe": r.get("playbookClass"),
            "vide": r.get("bucket") == "empty",
            "util": (None if r.get("bucket") == "empty" else r.get("bucketUtil")),
            "actions": r.get("bucketActionCount")}


def _oracle_generateur(sid, rid: int, caster_id: int) -> dict:
    """`aiDryRunAllUnits` -- l'action PROPOSEE par `CalculateNextActionForUnit`, donc en passant par
    le GENERATEUR (et par `ShouldEvaluate`, que `Evaluate/3` ne traverse pas).

    La reponse porte `units[].proposed[]`, une LISTE de messages -- forme LUE (#1066), pas
    supposee : lire un champ `action` y rend `None` partout et fait passer un temoin vivant pour
    nul."""
    r = _rpc(sid, "aiDryRunAllUnits", {"runnerId": rid}, 300)
    if not isinstance(r, dict) or not r.get("ok"):
        raise RuntimeError("aiDryRunAllUnits a ECHOUE (capteur muet, PAS un refus) : %s"
                           % json.dumps(r, default=str)[:400])
    for u in (r.get("units") or []):
        if u.get("unitId") != caster_id:
            continue
        prop = u.get("proposed") or []
        act = next((m for m in prop if m.get("cls") == "ActiveAbilityMessage"), None)
        return {"ability": (act or {}).get("abilityType"), "target": (act or {}).get("targetId"),
                "proposed": [m.get("cls") for m in prop]}
    return {"ability": None, "target": None, "proposed": None,
            "absent": "le caster n'est pas dans les units du dry-run"}


def _nc_context(sid, rid: int, caster_id: int):
    from engine.ai import context as _ai_ctx
    from engine.playbook import noncomparable as PB
    from engine.playbook import scene as _scene
    from engine import weights
    dv = _rpc(sid, "decisionView", {"runnerId": rid, "allAbilities": True, "maxRank": 32})
    mov = _rpc(sid, "aiMovableTiles", {"runnerId": rid}, 60)
    mov_by_unit = {u.get("unitId"): u for u in (mov.get("units") or [])}
    predictor = _scene.build_predictor(lambda m, b, t: _rpc(sid, m, b, t), rid)
    c = _ai_ctx.build(lambda m, b, t: _rpc(sid, m, b, t), rid, dv, mov_by_unit, caster_id,
                      weights.load(), predictor)
    return PB.NCContext(
        uid=c.uid, origin=c.origin, reach_nc=c.reach_nc, epos=c.epos, fpos=c.fpos,
        enemies=c.enemies, neigh_by_pos=c.neigh_by_pos, walkable_by_pos=c.walkable_by_pos,
        plan=c.plans.get(c.uid) or {}, plans=c.plans, hp_cur_by_id=c.hp_cur_by_id,
        elev_by_pos=c.elev_by_pos, ability_targets=c.ability_targets, wt=c.wt,
        is_temporary_by_pos=c.is_temporary_by_pos, effects_by_pos=c.effects_by_pos,
        is_wall_by_pos=getattr(c, "is_wall_by_pos", None) or {},
        is_in_fog_by_pos=getattr(c, "is_in_fog_by_pos", None) or {},
        obs_units=c.obs_units, tile_id_by_pos=c.tile_id_by_pos,
        active_levels=c.active_ability_levels, ability_config=c.heal_config,
        current_player=getattr(c, "cur", None),
        machine_of_war_position=c.machine_of_war_position,
        triggered_kits=getattr(c, "live_triggered_kits", None),
        units=c.units, cast_from_tiles=c.cast_from_tiles, scene=c.scene)


def _canal(nc, ennemis: list) -> dict:
    """L'ETAT DU CANAL, mesure par unite -- le TRI-ETAT rendu VISIBLE.

    C'est ce releve qui separe les trois regimes que le seul verdict du playbook confond :
    `None` = non mesure (le canal ne publie rien pour cette unite), `False` = mesure et negatif,
    `True` = mesure et positif. Sans lui, un bras « aucun candidat » ne dirait pas si le gate a
    REFUSE ou si le port s'est ABSTENU."""
    sc = getattr(nc, "scene", None)
    if sc is None:
        return {"scene": None}
    par_unite = {}
    for uid in ennemis:
        par_unite[int(uid)] = sc.has_taken_damage_of_profile_this_turn(int(uid), PSYCHIC)
    mesurees = [u for u, v in par_unite.items() if v is not None]
    return {"par_unite": par_unite, "mesurees": sorted(mesurees),
            "canal_mesure": bool(mesurees),
            "armees": sorted(u for u, v in par_unite.items() if v)}


def _canal_brut(sid, rid: int, ennemis: list) -> dict:
    """LE CAPTEUR LUI-MEME, lu SANS passer par le port -- ce qui NOMME le maillon defaillant.

    Trois maillons separent le composant natif du playbook : le CAPTEUR
    (`frida/hooks/game/receive-damage-types.ts` -> `actorStats.units[].receiveDamageTypeThisTurn`),
    le SEEDER (`snapshot._seed_received_damage_types` -> `UnitComponent.received_damage_this_turn`)
    et la SCENE (`Scene.received_damage_profiles_by_id`). Un `util = None` cote playbook les
    confond tous les trois. On lit donc le canal BRUT : s'il porte la donnee, le capteur est hors
    de cause et l'accusation porte sur l'aval."""
    r = _rpc(sid, "actorStats", {"runnerId": rid}, 90)
    if not isinstance(r, dict) or not r.get("ok"):
        return {"ok": False, "error": (r or {}).get("error") if isinstance(r, dict) else str(r)}
    par_unite = {}
    for u in (r.get("units") or []):
        uid = u.get("unitId", u.get("entityId"))
        if uid is None or int(uid) not in [int(e) for e in ennemis]:
            continue
        par_unite[int(uid)] = u.get("receiveDamageTypeThisTurn")
    return {"ok": True, "layout": r.get("receiveDamageLayout"),
            "enum": r.get("receiveDamageEnum"), "par_unite": par_unite,
            "champs_d_une_ligne": sorted((r.get("units") or [{}])[0].keys())[:24]}


def _mesurer(sid, rid, caster_id, ennemis, libelle, attendu_arme: bool) -> dict:
    from engine.playbook import noncomparable as PB
    nat_bucket = _oracle_bucket(sid, rid, caster_id)
    nat_gen = _oracle_generateur(sid, rid, caster_id)
    nc = _nc_context(sid, rid, caster_id)
    canal = _canal(nc, ennemis)
    pb = PB.PLAYBOOKS[HELLFYRE]
    util = pb._utility(nc)
    cands = pb.generate_candidates(nc)
    return {"libelle": libelle, "attendu_arme": attendu_arme,
            "natif_bucket_vide": nat_bucket["vide"], "natif_bucket_util": nat_bucket["util"],
            "natif_bucket_actions": nat_bucket["actions"], "natif_classe": nat_bucket["classe"],
            "natif_gen_ability": nat_gen.get("ability"), "natif_gen_target": nat_gen.get("target"),
            "natif_gen_proposed": nat_gen.get("proposed"),
            "port_util": util, "port_candidats": len(cands),
            "port_cible": (cands[0].get("target") if cands else None),
            "canal": canal}


def _pp(m: dict) -> None:
    print("  --- %s (attendu : %s) ---" % (m["libelle"],
                                           "ARME" if m["attendu_arme"] else "NON ARME"))
    print("      NATIF  bucket vide=%s util=%s actions=%s classe=%s"
          % (m["natif_bucket_vide"], m["natif_bucket_util"], m["natif_bucket_actions"],
             m["natif_classe"]))
    print("      NATIF  generateur -> ability=%s target=%s (%s)"
          % (m["natif_gen_ability"], m["natif_gen_target"], m["natif_gen_proposed"]))
    print("      PORT   util=%s candidats=%s cible=%s"
          % (m["port_util"], m["port_candidats"], m["port_cible"]))
    c = m["canal"]
    print("      CANAL  mesure=%s armees=%s par_unite=%s"
          % (c.get("canal_mesure"), c.get("armees"),
             json.dumps(c.get("par_unite"), default=str, sort_keys=True)))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--seed", default="777")
    ap.add_argument("--board", default="MC1_67")
    a = ap.parse_args()
    sid = R._resolve_session()
    sf = str(PYDIR.parents[1] / "logs" / "runners" / "probe-487r2-decision.json")
    Path(sf).parent.mkdir(parents=True, exist_ok=True)
    rid, err = _build(sf, a.seed, a.board)
    if rid is None:
        print("[487-r2] BUILD KO : %s" % err)
        return 2
    rc = 0
    try:
        dv = _rpc(sid, "decisionView", {"runnerId": rid, "maxRank": 1, "allAbilities": True})
        units = [u for u in (dv.get("units") or []) if u.get("alive")]
        toth = next((u for u in units if u.get("visualId") == TOTH), None)
        ahri = next((u for u in units if u.get("visualId") == AHRIMAN), None)
        if toth is None or ahri is None:
            print("[487-r2] SCENARIO NON MONTE : Toth/Ahriman absents")
            return 2
        ennemis = [u["id"] for u in units if u.get("owner") != toth.get("owner")]
        if len(ennemis) < 4:
            print("[487-r2] SCENARIO NON MONTE : moins de 4 ennemis vivants")
            return 2
        print("[487-r2] runner=%s caster(Toth)=%s Ahriman=%s ennemis=%s"
              % (rid, toth["id"], ahri["id"], ennemis))

        # --- BRAS 1 : NON ARME. Personne n'a pris de Psychic ce tour -----------------------
        m0 = _mesurer(sid, rid, toth["id"], ennemis, "NON ARME (aucun Psychic ce tour)", False)
        _pp(m0)

        # --- ARMEMENT : Ahriman caste Doombolt, MEME tour d'equipe -------------------------
        cibles = _rpc(sid, "abilityTargets",
                      {"runnerId": rid, "unitId": ahri["id"], "abilityType": DOOMBOLT}, 90) or {}
        row = next((u for u in (cibles.get("units") or []) if u.get("unitId") == ahri["id"]), None)
        ab = next((x for x in ((row or {}).get("abilities") or [])
                   if int(x.get("abilityId", -1)) == DOOMBOLT), {})
        fh = [t.get("targetId") for t in (ab.get("fromHere") or [])]
        if not fh:
            print("[487-r2] SCENARIO NON MONTE : aucune cible SUR PLACE pour Doombolt")
            return 2
        res = _rpc(sid, "applyAction", {"runnerId": rid, "action": {
            "kind": "ability", "casterId": ahri["id"], "abilityType": DOOMBOLT,
            "targetId": int(fh[0])}}, 120) or {}
        err0 = (res.get("actions") or [{}])[0].get("error")
        if err0:
            print("[487-r2] SCENARIO NON MONTE : Doombolt refuse (%s)" % err0)
            return 2

        # --- BRAS 2 : ARME -----------------------------------------------------------------
        m1 = _mesurer(sid, rid, toth["id"], ennemis, "ARME (Doombolt joue, Psychic pose)", True)
        _pp(m1)
        brut = _canal_brut(sid, rid, ennemis)
        print("      CAPTEUR brut actorStats -> ok=%s par_unite=%s"
              % (brut.get("ok"), json.dumps(brut.get("par_unite"), default=str, sort_keys=True)))
        print("              layout=%s enum=%s"
              % (json.dumps(brut.get("layout"), default=str),
                 json.dumps(brut.get("enum"), default=str)))
        print("              champs d'une ligne = %s"
              % json.dumps(brut.get("champs_d_une_ligne"), default=str))

        # --- VERDICTS ----------------------------------------------------------------------
        print("[487-r2] VERDICTS")
        # (0) NON-DEGENERESCENCE : sans canal mesure, les deux bras seraient « aucun candidat »
        #     pour la meme raison, et le contraste ne prouverait RIEN.
        if not m1["canal"].get("canal_mesure"):
            print("  !! CANAL MUET dans le bras ARME -- la mesure est DEGENEREE, aucun verdict "
                  "de gate n'est prononcable (c'est l'etat d'AVANT le capteur #10008).")
            return 2
        if not m1["canal"].get("armees"):
            print("  !! le bras ARME n'a arme AUCUN ennemi -- montage degenere")
            return 2
        # (1) le NATIF doit REFUSER a vide et ACCEPTER arme -- le gate `MIN_UTILITY = 1`.
        if not m0["natif_bucket_vide"]:
            print("  !! NATIF : bucket NON vide sans Psychic -- le gate MIN_UTILITY=1 ne mord pas")
            rc |= 1
        if m1["natif_bucket_vide"]:
            print("  !! NATIF : bucket VIDE alors que %s ennemis sont armes"
                  % len(m1["canal"]["armees"]))
            rc |= 1
        # (2) le PORT doit rendre le MEME verdict, dans les deux bras.
        for m in (m0, m1):
            refus_natif = bool(m["natif_bucket_vide"])
            refus_port = (m["port_candidats"] == 0)
            if refus_natif != refus_port:
                print("  !! [%s] DESACCORD natif/port : natif vide=%s, port candidats=%s (util=%s)"
                      % (m["libelle"], refus_natif, m["port_candidats"], m["port_util"]))
                rc |= 1
        # (3) l'UTILITE portee doit valoir le nombre d'ennemis armes -- et le TEMOIN NEGATIF
        #     (le 4e ork, hors portee du Doombolt) doit en etre EXCLU.
        attendu = float(len(m1["canal"]["armees"]))
        if m1["port_util"] != attendu:
            print("  !! PORT : util=%s, attendu %s (= nb d'ennemis armes mesures)"
                  % (m1["port_util"], attendu))
            rc |= 1
        if attendu >= len(ennemis):
            print("  !! TEMOIN NEGATIF ABSENT : tous les ennemis sont armes, le montage "
                  "n'exerce pas l'exclusion du non-arme")
            rc |= 2
        if rc == 0:
            print("  OK  gate `MIN_UTILITY = 1` CONFRONTE : le natif refuse a vide et accepte "
                  "arme, le port rend le meme verdict aux DEUX bras, et l'utilite portee vaut "
                  "exactement le nombre d'ennemis armes (%s sur %s ennemis)."
                  % (int(attendu), len(ennemis)))
    finally:
        _rpc(sid, "disposeRunner", {"runnerId": rid}, 20)
    return rc


if __name__ == "__main__":
    raise SystemExit(main())
