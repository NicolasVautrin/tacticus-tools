#!/usr/bin/env python
"""probe #366-r1 -- MESURE d'`InescapableAccuracy_overrideHits` (1117) sur `eldarMauganRa`.

CRITERION BINAIRE : « le port IGNORE-t-il -- ET REFUSE-T-IL d'ignorer apres un mouvement, et au
CONTACT -- les REDUCTIONS de coups comme le natif ? », mesure sur l'ETAGE QUI PORTE LE MECANISME :
le NOMBRE DE COUPS de la salve, pas leur valeur.

Pourquoi le NOMBRE et pas la valeur : 1117 n'a AUCUNE magnitude (son canal natif est un booleen,
cf. ci-dessous), donc son seul effet observable est la cardinalite de la salve. Ce criterion est
aussi le seul IMMUNISE au residu `#366-r1-crit-multihit` (l'etage CRIT diverge des le 3e coup d'une
salve, independamment de toute ability) : ce residu decale les VALEURS, jamais le COMPTE. C'est ce
qui permet ici une salve PLEINE (6 coups ranged / 5 melee) la ou #411 et #414 devaient se rabattre
sur une salve d'UN coup.

RE (detail : `docs/rl/case-366-r1-inescapable-accuracy-override-hits.md`) --
`IdunBattleLogic.Entities.Abilities.Triggered.Loki.InescapableAccuracy_OverridHitsEffect$$
CreateBlockHitReductionTrigger` :

    get_OwnerIsCaster & IsRangedAttack          (trigger NU -- PAS un `EffectBonus`)

lu par `IdunBattle.Entities.Effects.BaseEffect$$BlockHitsReduction` (cache a `<effect>+0x460`), dont
l'unique consommateur `IdunBattle.Core.Services.DamagePrediction$$GetAttackHits` trie les
`HitsBonusForAttack` de tous les effets ACTIFS en DEUX listes selon le SIGNE de leur `addition` et
**saute la liste des reductions** quand le flag est arme. Plus la `CreateActiveCondition` PARTAGEE
par les trois volets du passif :

    op_LogicalNot( HasFlag( Owner, 0 = UnitFlag.Moved ) )

QUATRE BRAS -- chacun choisit sa cible pour que la REDUCTION mesuree soit celle du bon vecteur, et
le quatrieme change d'AGREGATEUR cote port :

  NOMOVE -- tir a d=3 sur `tyranDeathleaper` (trait `Camouflage` -> `Camouflage_HitReduction`,
            RANGED-only, -2 coups au-dela de 2 hexes). MauganRa n'a pas bouge -> le block MORD :
            6 coups pleins (la reduction est ignoree).
  MOVED  -- MEME tir, MEME distance d=3, apres UN pas. `UnitFlag.Moved` pose -> l'effet est INACTIF
            -> la reduction s'applique : 6 - 2 = 4 coups.
  MELEE  -- frappe au CONTACT sur `custoAtlacoya` (trait `Parry` -> `Parry_ReduceHits`, MELEE-only,
            -1 coup), MauganRa n'ayant PAS bouge. `IsRangedAttack` est FAUX -> le block ne s'arme
            pas : 5 - 1 = 4 coups.
  AURA   -- tir a d=3 sur `necroWarden` (AUCUNE reduction propre) avec `astraBullgryn` (trait
            `BigTarget`) pose RING-1 de la cible : la reduction (-1 ranged) vient d'un TIERS et
            passe par un TROISIEME agregateur cote port (`aura_hits_malus_for_defense`). Le block
            l'eteint aussi -- le natif trie par SIGNE, pas par provenance : 6 coups pleins.

et par bras UNE MUTATION ADVERSARIALE du PORT, rejouee sur le MEME snapshot :

  NOCHANNEL    -- l'entree `InescapableAccuracy_overrideHits` est RETIREE d'`EFFECT_CLASSES`
                  (l'effet capte retombe sur `BaseEffect`, dont `block_hits_reduction` rend False).
                  DOIT DIVERGER dans NOMOVE (6 -> 4) : garde de DISCRIMINATION.
  NOGATE       -- les DEUX mirrors de l'`ActiveCondition` sont desarmes (`is_active` force a True,
                  cle `has_moved` retiree de l'`att_ctx`). DOIT DIVERGER dans MOVED (4 -> 6) :
                  garde de CHARGE UTILE du gate de mouvement.
  NORANGEGATE  -- le noeud `IsRangedAttack` est desarme (cle `is_melee` FORCEE a `False` dans
                  l'`att_ctx`, cf. le commentaire de `replay` : la RETIRER fermerait le gate au lieu
                  de l'ouvrir, mutation inerte). DOIT DIVERGER dans MELEE (4 -> 5) : garde de
                  CHARGE UTILE du gate de nature.

AUCUN seed BC custom : le nombre de coups vient du BC cote natif et du gameconfig cote port
(residu de SOURCE #366-r1 §7.2) -- les deux COINCIDENT tant qu'on ne patche rien (`eldarMauganRa`
= 5 coups melee / 6 coups ranged des deux cotes, verifie). Patcher `Weapons[].Hits` DESYNCHRONISERAIT
les deux modeles sur l'etage meme qu'on mesure : c'est le seul montage ou ce patch est interdit.

Le probe REFUSE de mesurer si le regime n'est pas atteint (geometrie, distance apres le pas, tour,
effet absent, cible morte, nombre de coups natif hors attendu) : un « vert » degrade vaudrait moins
que rien.

Usage (depuis scripts/python, session warmee) :
    python probe_366_r1_inescapable_accuracy_override_hits.py
    python probe_366_r1_inescapable_accuracy_override_hits.py --board C1_25 --seed 31337
    python probe_366_r1_inescapable_accuracy_override_hits.py --arms NOMOVE

ASCII only (console cp1252).
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

PYDIR = Path(__file__).resolve().parent
sys.path.insert(0, str(PYDIR))
sys.path.insert(0, str(PYDIR / "tests" / "engine" / "runner"))

#: Le SEUL porteur `lineup` du passif `InescapableAccuracy` (les cinq autres entrees d'
#: `unit_map find --ability InescapableAccuracy` sont des variantes de BOSS npc). HERO, dans le pool.
MAUGAN = "eldarMauganRa"
EFFECT_NAME = "InescapableAccuracy_overrideHits"
EFFECT_TYPE = 1117                   # EffectType 0x45d

#: Cible du vecteur RANGED : trait `Camouflage` -> effet `Camouflage_HitReduction`
#: (`OwnerIsTarget & IsRangedAttack`, -1 a d<=2 / -2 a d>2). Choisie parmi les 6 porteurs `lineup`
#: du trait pour trois raisons cumulees : PAS d'`Overwatch` (le montage deplace les deux camps),
#: PAS de `TertiaryAbility` au seed BC (contrairement a `admecRuststalker`, qui en porte une), et
#: aucun autre effet touchant l'axe COUPS.
TARGET_RANGED = "tyranDeathleaper"
#: Cible du vecteur MELEE : trait `Parry` -> effet `Parry_ReduceHits` (`OwnerIsTarget &
#: IsMeleeAttack`, -1). Memes trois criteres.
TARGET_MELEE = "custoAtlacoya"
#: Bras AURA : la reduction ne vient NI de la cible NI de l'attaquant mais d'un TIERS. Le trait
#: `BigTarget` d'`astraBullgryn` pose `BigTargetAdjacentEffect` sur SON porteur, qui projette
#: `ForAdditionWithMinimum(OwnerIsTarget & IsRangedAttack, Direct(-1), min=1)` sur ses ALLIES
#: ring-1. Cote port c'est un TROISIEME agregateur (`aura_hits_malus_for_defense`), et le bras
#: prouve LIVE que le block l'eteint aussi -- le natif ne trie pas par provenance mais par SIGNE.
#: `astraBullgryn` : traits `[Hero, BigTarget]` seuls (pas d'Overwatch), aucune `TertiaryAbility`
#: au seed, dans le pool. La cible du bras est `necroWarden`, qui ne porte AUCUNE reduction propre
#: (verifie par les montages de 1115/1116) : la seule reduction en jeu est donc l'aura.
TARGET_AURA = "necroWarden"
AURA_CARRIER = "astraBullgryn"

#: Portee de l'arme a distance de MauganRa (`weapons[1].Range` = 3). Le tir est monte a d=3 EXACT,
#: avant ET apres le pas : c'est la branche `dist > 2` de Camouflage (-2), et la garder identique
#: dans les deux bras isole le SEUL facteur qui change (le flag `Moved`).
RANGE_SHOT = 3
#: Coups d'arme attendus (BC == gameconfig, cf. l'en-tete) et reduction attendue par bras.
WEAPON_HITS = {"NOMOVE": 6, "MOVED": 6, "MELEE": 5, "AURA": 6}
EXPECTED_HITS = {"NOMOVE": 6, "MOVED": 4, "MELEE": 4, "AURA": 6}
MUTATION = {"NOMOVE": "NOCHANNEL", "MOVED": "NOGATE", "MELEE": "NORANGEGATE",
            "AURA": "NOCHANNEL"}


def _unwrap(r):
    return r.get("result") if isinstance(r, dict) and "result" in r else r


def _effect_names(u):
    return [e.get("name") for e in ((u or {}).get("effects") or []) if isinstance(e, dict)]


def _upos(u):
    p = (u or {}).get("pos") or {}
    return (p.get("col"), p.get("row")) if p.get("col") is not None else None


def _hits_of(res, caster, target):
    """Degats per-coup lus dans les events de l'attaque live (tag `Amount`, paire attaquant/cible).
    C'est la LISTE des coups : sa LONGUEUR est le criterion de ce probe."""
    a0 = (res.get("actions") or [{}])[0] if isinstance(res, dict) else {}
    out = []
    for e in (a0.get("events") or []):
        td = e.get("tags")
        if not td:
            continue
        td = json.loads(td) if isinstance(td, str) else td
        if ("Amount" in td and td.get("Attacker_Id") == caster
                and td.get("Target_Id") == target):
            out.append(int(td["Amount"]))
    return bool(a0.get("ok")), out


def build(a, arm):
    """Un runner par bras. Rend `(runnerId, state_file)` ou `(None, state_file)`.

    Les DEUX cibles sont dans l'equipe adverse pour les trois bras : le bras choisit la sienne, le
    montage ecarte l'autre. `--crit 0,700` = `GetStat(9) = 0` : dans MOVED et MELEE le volet `1115`
    est ferme (mouvement / melee), donc la salve ne crite pas du tout et les VALEURS y sont
    confrontables en plus du compte. Dans NOMOVE `1115` ouvre `clamp(0+15) = 15` et des crits
    tombent -- c'est justement le regime ou le residu `#366-r1-crit-multihit` decale les valeurs
    sans toucher au compte."""
    fd, sf = tempfile.mkstemp(prefix="ia1117_%s_" % arm.lower(), suffix=".json")
    os.close(fd)
    Path(sf).unlink(missing_ok=True)
    argv = [sys.executable, "rl_duel.py", "build", "--seed", str(a.seed),
            "--state-file", sf, "--board", a.board,
            "--p-units", MAUGAN,
            "--a-units", "%s,%s,%s,%s" % (a.target_ranged, a.target_melee, TARGET_AURA,
                                          AURA_CARRIER),
            "--hp-target", "400000", "--hp-player", "400000", "--no-ai",
            "--crit", a.crit]
    argv += list(a.extra or [])
    p = subprocess.run(argv, cwd=str(PYDIR), capture_output=True, text=True,
                       encoding="utf-8", errors="replace")
    if not Path(sf).exists():
        print("[%s] build KO : %s" % (arm, (p.stderr or p.stdout or "")[-500:]))
        return None, sf
    return json.loads(Path(sf).read_text())["runnerId"], sf


def arrange(h, target_visual, dist, need_step, aura_visual=None):
    """GEOMETRIE -- on DEPLACE les unites pour l'obtenir, jamais « bloque par les spawns ».

    Rend `{caster, target, start, step_to, anchor}` ou None. `start` est a `dist` hexes de l'ancre ;
    quand `need_step`, `step_to` est ADJACENT a `start` et EXACTEMENT a `dist` de l'ancre aussi --
    le pas change donc le flag `Moved` et RIEN d'autre de ce que lit le canal (meme nature d'attaque,
    meme cible, meme branche de Camouflage).

    ORDRE DES POSES : (1) ecarter les AUTRES ennemis, (2) poser la CIBLE sur l'ancre, (3) poser le
    CASTER -- en dernier, pour que le montage ne fasse pas tirer une unite adverse en OVERWATCH sur
    lui (MauganRa porte lui-meme `Overwatch`, d'ou le choix de cibles qui ne le portent PAS)."""
    import hexgeo
    dv = h.dview()
    me = h.by_visual(MAUGAN, dv)
    tgt = h.by_visual(target_visual, dv)
    if me is None or tgt is None:
        return None
    h.my_player = me.get("owner")
    others = [u for u in h.enemies_of(h.my_player, dv) if u["id"] != tgt["id"]]
    for anchor in [h.board.coord(t) for t in sorted(h.board.by_id) if h.board.walkable(t)]:
        starts = h.free_tiles(anchor, dist, exclude=(me["id"], tgt["id"]))
        if not starts:
            continue
        pair = None
        if not need_step:
            pair = (starts[0], None)
        else:
            for start in starts:
                nxt = next((c for c in starts
                            if c != start and hexgeo.distance(start, c) == 1), None)
                if nxt is not None:
                    pair = (start, nxt)
                    break
        if pair is None:
            continue
        for other in others:                      # (1)
            if aura_visual is not None and other.get("visualId") == aura_visual:
                continue                          # celui-la se pose EN RING-1, pas a l'ecart
            far = h.free_tiles(anchor, 5, exclude=(other["id"],))
            if far:
                h.place(other["id"], far[0])
        if not h.place(tgt["id"], anchor):        # (2)
            continue
        aura_id = None
        if aura_visual is not None:               # (2bis) porteur d'aura ADJACENT a la cible
            av = next((u for u in others if u.get("visualId") == aura_visual), None)
            if av is None:
                return None
            ring1 = h.free_tiles(anchor, 1, exclude=(av["id"],))
            if not ring1 or not h.place(av["id"], ring1[0]):
                continue
            aura_id = av["id"]
        if not h.place(me["id"], pair[0]):        # (3)
            continue
        return {"caster": me["id"], "target": tgt["id"], "start": pair[0],
                "step_to": pair[1], "anchor": anchor, "aura_id": aura_id}
    return None


def stage(h, arm):
    """FOYER UNIQUE du montage (importe par le cliquet, jamais re-transcrit).

    Monte le bras et rend `(rec, reason)` : `reason is None` = regime ATTEINT."""
    import hexgeo
    dist = 1 if arm == "MELEE" else RANGE_SHOT
    tvis = {"MELEE": TARGET_MELEE, "AURA": TARGET_AURA}.get(arm, TARGET_RANGED)
    plan = arrange(h, tvis, dist, need_step=(arm == "MOVED"),
                   aura_visual=(AURA_CARRIER if arm == "AURA" else None))
    if plan is None:
        return None, "geometrie d=%d (%s, pas d'un hex = %s) non realisable" % (
            dist, tvis, arm == "MOVED")
    if h.reach_my_turn(force_cycle=True) is None:
        return None, "mon tour non atteint"
    # Le cycle force purge `UnitFlag.Moved` (`StartTurnOperation$$ResetUnit`) : NOMOVE et MELEE
    # partent bien d'un « n'a pas bouge », et MOVED mesure SON pas et pas ceux du montage.
    dv = h.dview()
    pos = {u["id"]: _upos(u) for u in h.alive(dv)}
    if pos.get(plan["caster"]) != plan["start"] or pos.get(plan["target"]) != plan["anchor"]:
        return None, "geometrie perdue apres les endturns"
    if plan.get("aura_id") is not None:
        ap, tp = pos.get(plan["aura_id"]), pos.get(plan["target"])
        if ap is None or tp is None or hexgeo.distance(ap, tp) != 1:
            return None, ("le porteur d'aura u%s n'est plus RING-1 de la cible (d=%s) -- l'aura ne "
                          "serait pas projetee" % (plan["aura_id"],
                                                   None if (ap is None or tp is None)
                                                   else hexgeo.distance(ap, tp)))
    names = _effect_names(h.by_visual(MAUGAN, dv))
    if EFFECT_NAME not in names:
        return None, "%s ABSENT du seed live (effets=%s)" % (EFFECT_NAME, names)
    atk = h.normal_attack_type(plan["caster"], dv)
    if atk is None:
        return None, "pas d'attaque normale sur u%s" % plan["caster"]
    rec = dict(plan)
    rec["ability_type"] = int(atk)
    rec["snapshot"] = h.snapshot()
    if arm != "MOVED":
        rec["step_to"] = None
    else:
        if not h.place(plan["caster"], plan["step_to"]):
            return None, "pas refuse (tuile occupee / hors portee de mouvement)"
        d = hexgeo.distance(plan["step_to"], plan["anchor"])
        if d != RANGE_SHOT:
            return None, ("apres le pas d=%d != %d : la branche de Camouflage changerait, le bras "
                          "ne serait plus comparable" % (d, RANGE_SHOT))
    rec["rng_after_step"] = h.rpc("dumpRng", {"runnerId": h.rid}, 30)
    return rec, None


def strike(h, rec):
    """Joue l'ATTAQUE NORMALE live et rend `(live_hits, reason)`."""
    live = h.rpc("applyAction", {"runnerId": h.rid, "action": {
        "kind": "ability", "casterId": rec["caster"], "targetId": rec["target"],
        "abilityType": int(rec["ability_type"])}}, 60)
    ok, hits = _hits_of(live, rec["caster"], rec["target"])
    if not ok or not hits:
        return None, "attaque live refusee/vide (%s)" % str(live)[:200]
    if not any(u.get("id") == rec["target"] for u in h.alive()):
        return None, "la cible u%s est MORTE pendant la salve -- flux live tronque" % rec["target"]
    return hits, None


def replay(h, rec, mutate=None):
    """Rejeu OFFLINE du MEME snapshot, avec (option) une mutation ADVERSARIALE du PORT.

    `NOCHANNEL` retire l'inscription du registre AVANT `load_state` (c'est la factory qui
    materialise l'effet capte) ; `NOGATE` desarme les DEUX mirrors de l'`ActiveCondition` ;
    `NORANGEGATE` desarme le noeud `IsRangedAttack`. Chaque mutation est posee sur la CLASSE, et
    restauree dans le `finally` -- un rejeu de reference qui suivrait verrait le port intact."""
    from engine.entities.effects.factory import EFFECT_CLASSES
    from engine.entities.effects.loki.inescapable_accuracy import (
        InescapableAccuracyOverrideHitsEffect as K)
    saved_reg = EFFECT_CLASSES.get(EFFECT_NAME)
    saved = (K.is_active, K.block_hits_reduction)
    try:
        if mutate == "NOCHANNEL":
            EFFECT_CLASSES.pop(EFFECT_NAME, None)
        elif mutate == "NOGATE":
            orig = saved[1]
            K.is_active = lambda self, unit_state=None: True
            K.block_hits_reduction = (
                lambda self, att_ctx=None: orig(
                    self, {k: v for k, v in (att_ctx or {}).items() if k != "has_moved"}))
        elif mutate == "NORANGEGATE":
            # DESARMER un gate TRI-ETAT, ce n'est PAS retirer sa cle : `is_melee` absent rend
            # `is_ranged` NON PROUVE, donc FERME le gate -- la mutation serait INERTE (mesure du
            # 2026-08-01 : NORANGEGATE rendait 4 coups comme la reference, verte et vide de sens).
            # On force donc la cle a `False` = « nature PROUVEE distance », ce qui est exactement
            # « le noeud `IsRangedAttack` ne filtre plus rien ».
            orig = saved[1]
            K.block_hits_reduction = (
                lambda self, att_ctx=None: orig(self, {**(att_ctx or {}), "is_melee": False}))
        elif mutate is not None:
            raise AssertionError("mutation inconnue : %r" % (mutate,))
        return h.replay_offline(rec)["per_hit"]
    finally:
        if saved_reg is not None:
            EFFECT_CLASSES[EFFECT_NAME] = saved_reg
        K.is_active, K.block_hits_reduction = saved


def carried(rec, off_state):
    """1117 MATERIALISE offline sur l'attaquant -- sinon on comparerait deux absences. L'effet est
    PERMANENT (`turns = NULL`), donc il reste porte MEME quand son gate ferme : c'est la CONDITION
    qui l'eteint, pas un retrait."""
    return [e for e in (off_state.effects.by_unit.get(rec["caster"]) or [])
            if getattr(e, "effect_type", None) == EFFECT_TYPE
            or getattr(e, "name", None) == EFFECT_NAME]


def run_case(a, rpc, Board, ChargeRegimeHarness, arm) -> int:
    rid, sf = build(a, arm)
    if rid is None:
        Path(sf).unlink(missing_ok=True)
        return 2
    print("\n===== %s -- runner %s (board %s seed %s crit %s) =====" % (arm, rid, a.board, a.seed,
                                                                       a.crit))
    try:
        bg = rpc("boardGraph", {"runnerId": rid}, 60)
        h = ChargeRegimeHarness(rpc, rid, Board(bg["tiles"], adjacency="native_sym"))
        rec, why = stage(h, arm)
        if rec is None:
            print("[%s] REFUS : %s" % (arm, why))
            return 2

        # GARDES DE REGIME -- lues sur l'etat OFFLINE de reference, AVANT toute mesure.
        from engine.runner.components import unit_has_moved
        st0 = h.offline_state(rec)
        moved = bool(unit_has_moved(st0, rec["caster"]))
        print("[%s] attaquant u%s has_moved=%s | cible u%s (%s)%s"
              % (arm, rec["caster"], moved, rec["target"],
                 {"MELEE": TARGET_MELEE, "AURA": TARGET_AURA}.get(arm, TARGET_RANGED),
                 "" if rec.get("aura_id") is None
                 else " | aura u%s (%s) ring-1" % (rec["aura_id"], AURA_CARRIER)))
        if moved != (arm == "MOVED"):
            print("[%s] REFUS : has_moved=%s hors regime -- rien n'est mesure" % (arm, moved))
            return 2

        live, why = strike(h, rec)
        if live is None:
            print("[%s] REFUS : %s" % (arm, why))
            return 2
        off = replay(h, rec)
        print("[%s] LIVE    n=%d %s" % (arm, len(live), live))
        print("[%s] OFFLINE n=%d %s" % (arm, len(off), off))

        # CRITERION -- le NOMBRE de coups. Le natif DOIT rendre exactement l'attendu du bras
        # (`WEAPON_HITS - reduction`, ou `WEAPON_HITS` quand le block mord) : sans cette garde, un
        # accord live==offline sur un compte INATTENDU (cible morte, effet absent, arme mal
        # choisie) passerait pour une reussite.
        want = EXPECTED_HITS[arm]
        if len(live) != want:
            print("[%s] REFUS : le natif a joue %d coup(s), %d attendus (arme %d, %s) -- le regime "
                  "n'est PAS celui que le bras promet" % (arm, len(live), want, WEAPON_HITS[arm],
                                                          "block" if want == WEAPON_HITS[arm]
                                                          else "reduction appliquee"))
            return 2
        same_n = len(off) == len(live)
        print("[%s] VERDICT n_hits live=%d offline=%d -> %s"
              % (arm, len(live), len(off), "OK" if same_n else "DIVERGE"))
        rc = 0 if same_n else 1
        # GARDE SECONDAIRE -- les VALEURS. Elle n'est exigee que dans les bras ou la salve ne crite
        # pas du tout (`1115` ferme par le mouvement ou par la melee, et `GetStat(9) = 0`) : c'est
        # le seul regime hors d'atteinte du residu `#366-r1-crit-multihit`. Dans NOMOVE les crits
        # tombent et les valeurs peuvent legitimement diverger a partir du 3e coup.
        if arm in ("MOVED", "MELEE") and same_n:
            if off != live:
                print("[%s] VALEURS DIVERGENTES (regime SANS crit) : delta %s"
                      % (arm, [l - o for l, o in zip(live, off)]))
                rc |= 1
            else:
                print("[%s] valeurs bit-exactes (regime SANS crit)" % arm)

        # GARDE DE DISCRIMINATION -- la mutation se compare au REJEU DE REFERENCE, jamais au live.
        if not a.no_mutations:
            m = MUTATION[arm]
            mut = replay(h, rec, mutate=m)
            print("[%s] MUT-%s n=%d %s" % (arm, m, len(mut), mut))
            if len(mut) == len(off):
                print("[%s] REFUS : la mutation %s ne change PAS le nombre de coups -- la salve "
                      "n'exerce PAS le mecanisme ; varier --board / --seed / la cible"
                      % (arm, m))
                rc |= 2
            else:
                print("[%s] MUT-%s : %d -> %d coups, la salve EXERCE le mecanisme"
                      % (arm, m, len(off), len(mut)))
        return rc
    finally:
        rpc("disposeRunner", {"runnerId": rid}, 20)
        Path(sf).unlink(missing_ok=True)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--seed", default="777")
    ap.add_argument("--board", default="MC1_67")
    ap.add_argument("--crit", default="0,700",
                    help="CritChance,CritDamage des p-units. `0` garde MOVED et MELEE hors de tout "
                         "crit, donc confrontables sur les VALEURS en plus du compte.")
    ap.add_argument("--target-ranged", default=TARGET_RANGED,
                    help="cible du vecteur RANGED : porteur du trait Camouflage, SANS Overwatch")
    ap.add_argument("--target-melee", default=TARGET_MELEE,
                    help="cible du vecteur MELEE : porteur du trait Parry, SANS Overwatch")
    ap.add_argument("--arms", default="NOMOVE,MOVED,MELEE,AURA")
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
