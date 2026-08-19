#!/usr/bin/env python
"""probe #366-r1-blockhits-purgeresponse -- MESURE de `PurgeResponse` (1538), SECOND et DERNIER
implementeur natif de `IdunBattle.Entities.Effects.BaseEffect$$BlockHitsReduction`.

CRITERION BINAIRE : « le port ETEINT-il -- et REFUSE-T-IL d'eteindre hors overwatch -- les
REDUCTIONS de coups comme le natif, alors que le porteur du flag n'est NI l'attaquant NI la
cible ? », mesure sur le NOMBRE DE COUPS de la salve d'overwatch.

Le nombre et pas la valeur : le trigger natif est NU (pas d'`EffectBonus`), donc `PurgeResponse` n'a
AUCUNE magnitude -- son seul observable est la cardinalite de la salve. C'est aussi le seul criterion
immunise au residu `#366-r1-crit-multihit` (qui decale les VALEURS, jamais le COMPTE).

RE (detail : `docs/rl/case-366-r1-blockhits-purgeresponse.md`) --
`IdunBattle.Entities.Effects.Loki.PurgeResponseEffect$$CreateBlockHitReductionTrigger`, LU A
L'ASSEMBLEUR (un seul `call` vers `DSLTriggers`, aucun `AbilityTrigger$$op_BitwiseAnd`) :

    TriggeringAbilityIs( AbilityOrEffect( EffectType 0x3f1 = 1009 Overwatch_AutoAttack ) )

-- a comparer au SEUL autre implementeur, `...InescapableAccuracy_OverridHitsEffect$$
CreateBlockHitReductionTrigger` = `get_OwnerIsCaster & IsRangedAttack`. **`PurgeResponse` n'a PAS de
`get_OwnerIsCaster`** : son trigger ne lit RIEN du porteur. C'est ce fait, et lui seul, qui exige
d'elargir le balayage de `block_hits_reduction_from_effects` a TOUT le board -- mirror de
`IdunBattle.Core.Services.EffectsQuery$$GetActiveEffectsWithBonuses`, qui ne prend aucun argument
de portee.

DEUX BRAS, et c'est le montage lui-meme qui prouve l'absence du noeud `get_OwnerIsCaster` :

  ON  -- `votanMemnyr` (INJECTE au catalogue : aucun Votann n'est dans le pool) caste
         `IronkinSteeljack` (1219) -> le summon `votanSmnSteeljack` apparait DANS MON CAMP, porteur
         de l'effet `PurgeResponse` (1538) ACTIF (piege #427 : il se projette sous le visualId
         **`votanNpc2Steeljack`**). Puis MON `tauMarksman` (trait `Camouflage`) entre a d=2 de
         l'ennemi `necroDestroyer` (trait `Overwatch`, 6 coups a distance, portee 2) : l'overwatch
         tire. L'attaquant est DANS L'AUTRE CAMP, la cible est un TIERS du porteur -- un flag gate
         `get_OwnerIsCaster` ne pourrait PAS s'armer. Attendu : **6** coups pleins.
  OFF -- MEME montage, summon NON caste : plus aucun porteur de 1538 sur le board, la reduction de
         `Camouflage_HitReduction` (`OwnerIsTarget & IsRangedAttack`, -1 a d<=2) s'applique.
         Attendu : **5** coups.

et TROIS MUTATIONS ADVERSARIALES du PORT, rejouees sur le MEME snapshot du bras ON :

  NOCHANNEL -- l'entree `PurgeResponse` est RETIREE d'`EFFECT_CLASSES` (l'effet capte retombe sur
               `BaseEffect`, dont `block_hits_reduction` rend False). DOIT retomber a 5.
  NOWIDEN   -- le balayage est RESTREINT aux effets de l'ATTAQUANT, c'est-a-dire l'etat du port
               AVANT cette tranche. DOIT retomber a 5 : c'est la garde de l'ELARGISSEMENT, celle
               qui rougit si le balayage se re-retrecit.
  NOTRIGGER -- la cle `trigger_ability_type` est FORCEE a None dans l'`att_ctx` (le noeud
               `TriggeringAbilityIs` devient FAUX). DOIT retomber a 5.

Le probe REFUSE de mesurer si le regime n'est pas atteint (geometrie, effet absent, overwatch
desarme, salve hors attendu, porteur d'aura trop proche) : un « vert » degrade vaudrait moins que
rien.

Usage (depuis scripts/python, session warmee) :
    python probe_366_r1_blockhits_purgeresponse.py
    python probe_366_r1_blockhits_purgeresponse.py --board C1_25 --seed 31337
    python probe_366_r1_blockhits_purgeresponse.py --arms ON

ASCII only (console cp1252).
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import tempfile
import uuid
from pathlib import Path

PYDIR = Path(__file__).resolve().parent
ROOT = PYDIR.parents[1]
sys.path.insert(0, str(PYDIR))
sys.path.insert(0, str(PYDIR / "tests" / "engine" / "runner"))

#: Invocateur du porteur. HORS POOL (aucune unite `LeaguesOfVotann` n'y est) -> injecte au catalogue
#: par `catalog_inject`, recette `docs/rl/case-92-catalog-injection.md` §6.
SUMMONER = "votanMemnyr"
#: Ability ACTIVE de l'invocateur : `IronkinSteeljack` (`ActiveAbilityType` 0x4c3 = 1219), summon sur
#: une tuile LIBRE **ADJACENTE** au caster (case-92 §5 : une tuile non adjacente rend
#: `ok:true / mutated:false / spawned:0`, faux negatif parfait).
SUMMON_ABILITY = 1219
#: ⚠ Le summon se projette sous le `visualId` du NPC jumeau, PAS sous son `unitId` (piege #427 /
#: case-92 §5). Un filtre sur `votanSmnSteeljack` rend zero unite.
SUMMON_VISUAL = "votanNpc2Steeljack"
EFFECT_NAME = "PurgeResponse"
EFFECT_TYPE = 1538                   # EffectType 0x602

#: OVERWATCHER (l'ATTAQUANT de la salve) : trait `Overwatch` + arme a distance a **6 coups**,
#: portee 2. `eldarMauganRa` est ECARTE alors qu'il coche les memes cases : il porte `1117
#: InescapableAccuracy_overrideHits`, dont le canal EST le meme -- il bloquerait les reductions tout
#: seul et le bras ON serait vide de sens.
OVERWATCHER = "necroDestroyer"
#: MOVER (la CIBLE de la salve) : trait `Camouflage` -> `Camouflage_HitReduction`
#: (`OwnerIsTarget & IsRangedAttack`, -1 a d<=2). Les autres porteurs `lineup` de `Camouflage` sont
#: ecartes : `tyranDeathleaper`, `astarCyrus` et `thousSekhetar` portent `Infiltrate`, qui est
#: precisement l'IMMUNITE du mover a l'overwatch (`Overwatch_AutoAttackEffect$$AdditionalTriggers`
#: = `NOT HasEffect(mover, 0x418 = 1048 Infiltrate)`) -> aucune salve.
MOVER = "tauMarksman"

MUTATIONS = ("NOCHANNEL", "NOWIDEN", "NOTRIGGER")


def shot_regime(overwatcher: str):
    """`(portee du tir, coups d'arme, reduction Camouflage)` LUS du gameconfig -- aucun chiffre en
    dur. La distance du tir est la PORTEE de l'arme a distance de l'overwatcher (l'overwatch ne peut
    tirer que dedans), et c'est elle qui choisit la branche de `Camouflage_HitReduction` :
    `AmountIsGreater(AverageDistance(Caster, Target), Direct(2))` -> `-2` au-dela de 2 hexes,
    `-1` sinon. Les coups d'arme viennent du BC cote natif et du gameconfig cote port : les deux
    COINCIDENT tant qu'on ne patche pas `Weapons[].Hits` (residu de SOURCE #366-r1 §7.2), et ce
    montage ne les patche PAS -- c'est justement l'etage qu'il mesure."""
    import gameconfig as GC
    ws = [w for w in ((GC.unit(overwatcher) or {}).get("weapons") or [])
          if int(w.get("Range") or 0) > 0]      # une arme SANS `Range` est l'arme de melee
    if not ws:
        raise AssertionError("%s n'a aucune arme a distance dans le gameconfig" % overwatcher)
    w = max(ws, key=lambda x: int(x.get("Range") or 0))
    dist = int(w["Range"])
    hits = int(w.get("hits") or 1)
    return dist, hits, (2 if dist > 2 else 1)


def _unwrap(r):
    return r.get("result") if isinstance(r, dict) and "result" in r else r


def _upos(u):
    p = (u or {}).get("pos") or {}
    return (p.get("col"), p.get("row")) if p.get("col") is not None else None


def _effect_rows(u):
    return [(e.get("effectType"), e.get("name"), e.get("active"))
            for e in ((u or {}).get("effects") or []) if isinstance(e, dict)]


def _amounts(res, attacker, target):
    """Degats per-coup lus dans les events de l'action live (tag `Amount`, paire attaquant/cible).
    C'est la LISTE des coups de l'overwatch : sa LONGUEUR est le criterion de ce probe."""
    a0 = (res.get("actions") or [{}])[0] if isinstance(res, dict) else {}
    out = []
    for e in (a0.get("events") or []):
        td = e.get("tags")
        if not td:
            continue
        td = json.loads(td) if isinstance(td, str) else td
        if ("Amount" in td and td.get("Attacker_Id") == attacker
                and td.get("Target_Id") == target):
            out.append(int(td["Amount"]))
    return bool(a0.get("ok")), out


def build(a, arm):
    """Un runner par bras. Rend `(runnerId, state_file, seed_bc)` ou `(None, ...)`.

    Le seed BC est AUGMENTE de `votanMemnyr` : aucune unite `LeaguesOfVotann` n'est dans le pool
    (`rl_duel build --list-pool`), et le porteur est un SUMMON -- il n'entre donc en bataille que par
    son invocateur, lui-meme injecte. `catalog_inject` re-synthetise AUSSI `BC.Abilities` depuis le
    gameconfig courant, ce qui fournit la config d'`IronkinSteeljack` absente du seed capture
    (sans elle : « system error » au cast, case-92 §5)."""
    tag = uuid.uuid4().hex[:8]
    bc = ROOT / "logs" / "runners" / ("bc-purge-%s-%s.json" % (arm.lower(), tag))
    bc.parent.mkdir(parents=True, exist_ok=True)
    p = subprocess.run([sys.executable, "catalog_inject.py", "--units", SUMMONER,
                        "--out", str(bc)],
                       cwd=str(PYDIR), capture_output=True, text=True, encoding="utf-8",
                       errors="replace")
    if not bc.exists():
        print("[%s] catalog_inject KO : %s" % (arm, (p.stderr or p.stdout or "")[-400:]))
        return None, None, None
    fd, sf = tempfile.mkstemp(prefix="purge_%s_" % arm.lower(), suffix=".json")
    os.close(fd)
    Path(sf).unlink(missing_ok=True)
    argv = [sys.executable, "rl_duel.py", "build", "--seed", str(a.seed), "--seed-bc", str(bc),
            "--state-file", sf, "--board", a.board,
            "--p-units", "%s,%s" % (SUMMONER, MOVER),
            "--a-units", a.overwatcher,
            "--hp-target", "400000", "--hp-player", "400000", "--no-ai"]
    argv += list(a.extra or [])
    p = subprocess.run(argv, cwd=str(PYDIR), capture_output=True, text=True, encoding="utf-8",
                       errors="replace")
    if not Path(sf).exists():
        print("[%s] build KO : %s" % (arm, (p.stderr or p.stdout or "")[-500:]))
        return None, sf, bc
    return json.loads(Path(sf).read_text())["runnerId"], sf, bc


def summon(h):
    """Caste `IronkinSteeljack` sur une tuile LIBRE **ADJACENTE** au caster et rend
    `(summon_id, reason)`. L'adjacence est la marche de case-92 §5 : `abilityTargets` rend TOUT
    l'ensemble castable, alors que le behaviour de summon exige un hex adjacent."""
    import hexgeo
    dv = h.dview()
    me = h.by_visual(SUMMONER, dv)
    if me is None:
        return None, "%s absent du board (injection catalogue KO ?)" % SUMMONER
    at = h.rpc("abilityTargets",
               {"runnerId": h.rid, "unitId": me["id"], "abilityType": SUMMON_ABILITY}, 120)
    row = next((u for u in (at.get("units") or []) if u.get("unitId") == me["id"]), None)
    tgts = ((row.get("abilities") or [{}])[0].get("targets") or []) if row else []
    mp = _upos(me)
    adj = [t for t in tgts if t.get("kind") != "unit" and t.get("tile")
           and hexgeo.distance(mp, (t["tile"]["col"], t["tile"]["row"])) == 1]
    if not adj:
        return None, ("aucune tuile castable ADJACENTE a u%s (%d cibles rendues) -- un hex non "
                      "adjacent rendrait spawned:0 en silence" % (me["id"], len(tgts)))
    t = adj[0]["tile"]
    res = h.rpc("applyAction", {"runnerId": h.rid, "action": {
        "kind": "ability", "casterId": me["id"], "abilityType": SUMMON_ABILITY,
        "to": {"col": int(t["col"]), "row": int(t["row"])}}}, 150)
    a0 = (res.get("actions") or [{}])[0] if isinstance(res, dict) else {}
    if not a0.get("ok"):
        return None, "cast %d refuse : %s" % (SUMMON_ABILITY, str(res)[:200])
    sm = h.by_visual(SUMMON_VISUAL, h.dview())
    if sm is None:
        return None, ("summon absent apres le cast (mutated=%s) -- chercher le visualId `%s`, PAS "
                      "l'unitId `votanSmnSteeljack`" % (a0.get("mutated"), SUMMON_VISUAL))
    rows = _effect_rows(sm)
    if not any(r[0] == EFFECT_TYPE and r[2] for r in rows):
        return None, "u%s n'a pas %s (%d) ACTIF : %s" % (sm["id"], EFFECT_NAME, EFFECT_TYPE, rows)
    return sm["id"], None


def park(h, unit_id, anchor, keep_away=None, min_gap=3):
    """GARE `unit_id` LOIN de l'overwatcher (rayons 6 puis 5/7 : hors de toute portee d'arme, donc
    aucun overwatch premature) ET a `min_gap` hexes au moins de la tuile d'arrivee du mover.

    On DEPLACE les unites pour obtenir la configuration voulue -- jamais « bloque par la geometrie
    de spawn ». Deux porteurs a ecarter, chacun pour un canal de l'axe COUPS qui n'a rien a voir
    avec la tranche : l'invocateur (`PredictiveGuidance`, +1 coup aux amis Votann contre un ennemi
    marque a 2 hexes) et le SUMMON lui-meme (`BigTarget_AdjacentEffect`, -1 coup RANGED sur ses
    allies RING-1). Rend True si la pose a mordu."""
    import hexgeo
    for radius in (6, 5, 7, 4, 8):
        cands = [c for c in h.free_tiles(anchor, radius, exclude=(unit_id,))
                 if keep_away is None or hexgeo.distance(c, tuple(keep_away)) >= min_gap]
        for c in cands:
            if h.place(unit_id, c):
                return True
    return False


def stage(h, arm, overwatcher: str = OVERWATCHER):
    """FOYER UNIQUE du montage (importe par le cliquet, jamais re-transcrit).

    Rend `(rec, reason)` : `reason is None` = regime ATTEINT. `rec` porte `caster` (l'OVERWATCHER,
    donc l'attaquant de la salve), `target` (le MOVER), `step_to` (la tuile a la portee du tir) et
    le `snapshot` pris JUSTE AVANT le pas."""
    import hexgeo
    shot_dist, _wh, _red = shot_regime(overwatcher)
    dv = h.dview()
    ow = h.by_visual(overwatcher, dv)
    mv = h.by_visual(MOVER, dv)
    me = h.by_visual(SUMMONER, dv)
    if ow is None or mv is None or me is None:
        return None, "unite absente (ow=%s mover=%s summoner=%s)" % (ow is not None, mv is not None,
                                                                     me is not None)
    h.my_player = mv.get("owner")
    smn_id = None
    if arm == "ON":
        smn_id, why = summon(h)
        if smn_id is None:
            return None, "summon : %s" % why
    anchor = _upos(ow)
    # (1) ECARTER l'invocateur (son passif `PredictiveGuidance` porte a 2 hexes et donne un coup
    # SUPPLEMENTAIRE aux attaques des amis Votann contre les ennemis marques -- hors sujet ici, mais
    # on ne laisse pas un canal de l'axe COUPS trainer dans le montage) et le SUMMON (son
    # `BigTarget_AdjacentEffect` projette -1 coup RANGED sur ses allies RING-1, ce qui changerait la
    # reduction subie par le mover).
    for uid in [me["id"]] + ([smn_id] if smn_id is not None else []):
        park(h, uid, anchor)
    # (2) GEOMETRIE du tir : le mover part a `SHOT_DIST + 1` de l'overwatcher (donc HORS de sa
    # portee -- aucun overwatch premature) et le PAS le fait entrer a `SHOT_DIST` EXACT.
    starts = h.free_tiles(anchor, shot_dist + 1, exclude=(mv["id"],))
    stops = h.free_tiles(anchor, shot_dist, exclude=(mv["id"],))
    pair = None
    for s in starts:
        nxt = next((c for c in stops if hexgeo.distance(s, c) == 1), None)
        if nxt is not None:
            pair = (s, nxt)
            break
    if pair is None:
        return None, "geometrie d=%d -> d=%d (pas d'un hex) non realisable" % (shot_dist + 1,
                                                                              shot_dist)
    if not h.place(mv["id"], pair[0]):
        return None, "pose du mover sur %s refusee" % (pair[0],)
    if h.reach_my_turn(force_cycle=True) is None:
        return None, "mon tour non atteint"
    # (3) RE-PARKING APRES les endturns. Le summon porte le trait `Summon` : le natif le fait JOUER
    # TOUT SEUL au debut de chaque tour de son equipe (`PlayAutomaticUnits`, case-291) -- il se
    # deplace donc entre la pose et le pas, et peut atterrir RING-1 de la tuile d'arrivee du mover,
    # ou son `BigTarget_AdjacentEffect` ajouterait une SECONDE reduction. On le re-gare (MESURE
    # C1_25/31337 : sans ce re-parking le bras ON est REFUSE, d=1).
    for uid in [me["id"]] + ([smn_id] if smn_id is not None else []):
        park(h, uid, anchor, keep_away=pair[1])
    dv = h.dview()
    pos = {u["id"]: _upos(u) for u in h.alive(dv)}
    if pos.get(mv["id"]) != pair[0] or pos.get(ow["id"]) != anchor:
        return None, "geometrie perdue apres les endturns"
    owl = next((u for u in h.alive(dv) if u["id"] == ow["id"]), None)
    if not any(r[0] == 1009 and r[2] for r in _effect_rows(owl)):
        return None, ("l'overwatch de u%s n'est pas ACTIF (%s) -- il a pu etre CONSOMME par une "
                      "unite qui est entree dans sa portee avant le pas"
                      % (ow["id"], _effect_rows(owl)))
    mvl = next((u for u in h.alive(dv) if u["id"] == mv["id"]), None)
    if not any(r[0] == 1134 and r[2] for r in _effect_rows(mvl)):
        return None, ("le mover u%s n'a pas `Camouflage_HitReduction` (1134) ACTIF (%s) -- sans "
                      "reduction, les deux bras rendraient le meme compte" % (mv["id"],
                                                                              _effect_rows(mvl)))
    if smn_id is not None:
        sp = pos.get(smn_id)
        if sp is None:
            return None, "le summon u%s a disparu du board" % smn_id
        d_sm = hexgeo.distance(sp, pair[1])
        if d_sm <= 1:
            return None, ("le summon u%s est RING-1 de la tuile d'arrivee (d=%d) : son "
                          "`BigTarget_AdjacentEffect` ajouterait -1 coup et brouillerait le bras"
                          % (smn_id, d_sm))
        smr = next((u for u in h.alive(dv) if u["id"] == smn_id), None)
        if not any(r[0] == EFFECT_TYPE and r[2] for r in _effect_rows(smr)):
            return None, "u%s a perdu %s ACTIF : %s" % (smn_id, EFFECT_NAME, _effect_rows(smr))
    rec = {"caster": ow["id"], "target": mv["id"], "start": pair[0], "step_to": pair[1],
           "anchor": anchor, "summon_id": smn_id, "arm": arm, "shot_dist": shot_dist}
    rec["snapshot"] = h.snapshot()
    return rec, None


def strike(h, rec):
    """Joue le PAS live -- c'est LUI qui declenche l'overwatch -- et rend `(live_hits, reason)`."""
    res = h.rpc("applyAction", {"runnerId": h.rid, "action": {
        "kind": "move", "unitId": rec["target"],
        "to": {"col": int(rec["step_to"][0]), "row": int(rec["step_to"][1])}},
        "captureEvents": True}, 90)
    ok, hits = _amounts(res, rec["caster"], rec["target"])
    if not ok:
        return None, "pas live refuse (%s)" % str(res)[:200]
    if not hits:
        return None, ("aucun coup d'overwatch dans les events -- le pas n'a pas declenche la salve "
                      "(portee ? immunite du mover ? overwatch deja consomme ?)")
    dv = h.dview()
    if _upos(next((u for u in h.alive(dv) if u["id"] == rec["target"]), None)) != rec["step_to"]:
        return None, "le mover n'a pas atteint %s (pas refuse en silence)" % (rec["step_to"],)
    return hits, None


def offline_state(h, rec):
    """`State` OFFLINE reconstruit depuis le snapshot PRE-pas, MT cale sur le meme dump."""
    from engine.runner.prng import IntBasedMersenneTwister
    from engine.runner.snapshot import load_state
    s = rec["snapshot"]
    st = load_state(s["dv"], s["ob"], s["snap"], board=h.board)
    dump = s.get("rng")
    if isinstance(dump, dict) and dump.get("mt"):
        r = IntBasedMersenneTwister()
        r.mt = list(dump["mt"])
        r.mti = dump["mti"]
        st.rng = r
    return st


def replay(h, rec, mutate=None):
    """Rejeu OFFLINE du MEME snapshot : on REJOUE LE PAS (`MoveUnitMessage`), et c'est le vecteur
    after-move du moteur qui doit declencher l'overwatch. Rend la liste des coups.

    Les mutations sont posees sur le PORT, et restaurees dans le `finally` :
      * `NOCHANNEL` retire l'inscription du registre AVANT `load_state` (c'est la factory qui
        materialise l'effet capte) ;
      * `NOWIDEN` restreint le balayage aux effets de l'ATTAQUANT -- l'etat d'AVANT cette tranche ;
      * `NOTRIGGER` force `trigger_ability_type = None` dans l'`att_ctx` de la classe (le noeud
        `TriggeringAbilityIs` devient FAUX). ⚠ Ici FORCER la valeur et la RETIRER coincident, parce
        que ce gate est BINAIRE (`ta is None -> False`) et non tri-etat : le desarmement va bien
        dans le sens qui EFFACE le blocage. La garde de discrimination le verifie quand meme."""
    from engine.runner.messages import MoveUnitMessage
    from engine.runner.runner import Runner
    from engine.entities.effects import factory as F
    from engine.entities.effects.loki.votann import PurgeResponseEffect as K
    import engine.services.attack_hits_formula as AHF

    saved_reg = F.EFFECT_CLASSES.get(EFFECT_NAME)
    saved_cls = K.block_hits_reduction
    saved_carriers = AHF.board_effect_carriers
    try:
        if mutate == "NOCHANNEL":
            F.EFFECT_CLASSES.pop(EFFECT_NAME, None)
        elif mutate == "NOWIDEN":
            AHF.board_effect_carriers = (
                lambda att_id, att_eff, tgt_id, tgt_eff, auras: [(att_id, att_eff)])
        elif mutate == "NOTRIGGER":
            orig = saved_cls
            K.block_hits_reduction = (
                lambda self, att_ctx=None: orig(
                    self, {**(att_ctx or {}), "trigger_ability_type": None}))
        elif mutate is not None:
            raise AssertionError("mutation inconnue : %r" % (mutate,))
        st = offline_state(h, rec)
        runner = Runner(st).install_default_handlers(20)
        runner.apply(MoveUnitMessage(rec["target"], tuple(rec["step_to"])))
        rows = [x for x in (runner.movement_handler.after_move or [])
                if x.get("effect") == "Overwatch_AutoAttack"]
        per_hit = []
        for x in rows:
            per_hit += list(((x.get("result") or {}).get("per_hit")) or [])
        return per_hit, st
    finally:
        if saved_reg is not None:
            F.EFFECT_CLASSES[EFFECT_NAME] = saved_reg
        K.block_hits_reduction = saved_cls
        AHF.board_effect_carriers = saved_carriers


def carried(rec, off_state):
    """`PurgeResponse` MATERIALISE offline sur le SUMMON -- sinon on comparerait deux absences."""
    if rec.get("summon_id") is None:
        return True
    return bool([e for e in (off_state.effects.by_unit.get(rec["summon_id"]) or [])
                 if getattr(e, "effect_type", None) == EFFECT_TYPE
                 or getattr(e, "name", None) == EFFECT_NAME])


def run_case(a, rpc, Board, ChargeRegimeHarness, arm) -> int:
    rid, sf, bc = build(a, arm)
    if rid is None:
        for p in (sf, bc):
            if p:
                Path(p).unlink(missing_ok=True)
        return 2
    shot_dist, weapon_hits, reduction = shot_regime(a.overwatcher)
    expected = {"ON": weapon_hits, "OFF": weapon_hits - reduction}
    print("\n===== %s -- runner %s (board %s seed %s, ow %s : %d coups a d=%d, Camouflage -%d) ====="
          % (arm, rid, a.board, a.seed, a.overwatcher, weapon_hits, shot_dist, reduction))
    try:
        bg = rpc("boardGraph", {"runnerId": rid}, 60)
        h = ChargeRegimeHarness(rpc, rid, Board(bg["tiles"], adjacency="native_sym"))
        rec, why = stage(h, arm, overwatcher=a.overwatcher)
        if rec is None:
            print("[%s] REFUS : %s" % (arm, why))
            return 2
        print("[%s] overwatcher u%s @%s | mover u%s -> %s (d=%d) | summon %s"
              % (arm, rec["caster"], rec["anchor"], rec["target"], rec["step_to"], shot_dist,
                 "u%s" % rec["summon_id"] if rec["summon_id"] is not None else "AUCUN"))
        live, why = strike(h, rec)
        if live is None:
            print("[%s] REFUS : %s" % (arm, why))
            return 2
        off, st = replay(h, rec)
        print("[%s] LIVE    n=%d %s" % (arm, len(live), live))
        print("[%s] OFFLINE n=%d %s" % (arm, len(off), off))
        if not carried(rec, st):
            print("[%s] REFUS : %s n'est pas materialise offline sur le summon" % (arm, EFFECT_NAME))
            return 2

        want = expected[arm]
        if len(live) != want:
            print("[%s] REFUS : le natif a joue %d coup(s), %d attendus (arme %d, %s) -- le regime "
                  "n'est PAS celui que le bras promet" % (arm, len(live), want, weapon_hits,
                                                          "block" if want == weapon_hits
                                                          else "reduction appliquee"))
            return 2
        same_n = len(off) == len(live)
        print("[%s] VERDICT n_hits live=%d offline=%d -> %s"
              % (arm, len(live), len(off), "OK" if same_n else "DIVERGE"))
        rc = 0 if same_n else 1

        if arm == "ON" and not a.no_mutations:
            for m in MUTATIONS:
                mut, _ = replay(h, rec, mutate=m)
                print("[%s] MUT-%-9s n=%d %s" % (arm, m, len(mut), mut))
                if len(mut) == len(off):
                    print("[%s] REFUS : la mutation %s ne change PAS le nombre de coups -- la salve "
                          "n'exerce PAS le mecanisme" % (arm, m))
                    rc |= 2
                else:
                    print("[%s] MUT-%s : %d -> %d coups, la salve EXERCE le mecanisme"
                          % (arm, m, len(off), len(mut)))
        return rc
    finally:
        rpc("disposeRunner", {"runnerId": rid}, 20)
        for p in (sf, bc):
            if p:
                Path(p).unlink(missing_ok=True)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--seed", default="777")
    ap.add_argument("--board", default="MC1_67")
    ap.add_argument("--arms", default="ON,OFF")
    ap.add_argument("--overwatcher", default=OVERWATCHER,
                    help="porteur du trait Overwatch (l'ATTAQUANT de la salve). Sa portee choisit "
                         "la branche de Camouflage : d>2 -> -2, sinon -1. JAMAIS eldarMauganRa "
                         "(il porte 1117, meme canal).")
    ap.add_argument("--no-mutations", action="store_true",
                    help="saute les gardes de discrimination (diagnostic seulement)")
    ap.add_argument("--extra", action="append", default=[],
                    help="arg supplementaire passe a `rl_duel build` (repetable)")
    a = ap.parse_args()

    import rl_collect_batch as R
    from engine.entities.pathfinding.board import Board
    from _charge_regime import ChargeRegimeHarness

    sid = R._resolve_session()
    w = _unwrap(R._rpc(sid, "autoBootExtraire", [{}], timeout=180))
    if not (isinstance(w, dict) and w.get("ok")):
        print("[probe] amorce KO : %s" % str(w)[:200])
        return 2

    def rpc(method, body=None, timeout=60):
        return _unwrap(R._rpc(sid, method, [body] if body is not None else [], timeout=timeout))

    rc = 0
    for arm in [x.strip() for x in a.arms.split(",") if x.strip()]:
        rc |= run_case(a, rpc, Board, ChargeRegimeHarness, arm)
    return rc


if __name__ == "__main__":
    raise SystemExit(main())
