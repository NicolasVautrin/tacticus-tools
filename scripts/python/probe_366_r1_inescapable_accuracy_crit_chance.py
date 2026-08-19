#!/usr/bin/env python
"""probe #366-r1 -- MESURE d'`InescapableAccuracy_extraCritChance` (1115) sur `eldarMauganRa`.

CRITERION BINAIRE : « le port ajoute-t-il -- ET REFUSE-T-IL d'ajouter apres un mouvement -- la
contribution de 1115 comme le natif ? », mesure la ou l'effet MORD : le DEGAT PER-COUP d'une salve
A DISTANCE, dont chaque coup passe par `RollCritical(clamp(GetStat(9) + somme, 0, 100))`.

RE (detail : `docs/rl/case-366-r1-inescapable-accuracy-crit-chance.md`) --
`IdunBattleLogic.Entities.Abilities.Triggered.Loki.InescapableAccuracy_ExtraCritChanceEffect$$
CreateCritChanceBonus` :

    EffectBonus.ForAddition( get_OwnerIsCaster & IsRangedAttack,
                             ConfigVar(0x41 = extraCritChance, GetAbilityState(effect), config@+0x60) )

et la `CreateActiveCondition` PARTAGEE par les trois classes du passif :

    op_LogicalNot( HasFlag( Owner, 0 = UnitFlag.Moved ) )

DEUX BRAS :

  NOMOVE -- MauganRa tire SANS avoir bouge (`arrange_ranged` le pose deja a portee).
            ActiveCondition VRAIE -> cc = GetStat(9) + extraCritChance[50] = GetStat(9) + 15.
  MOVED  -- MauganRa fait UN pas (en restant a portee ET hors contact) puis tire.
            `UnitFlag.Moved` pose -> l'effet est INACTIF -> cc = GetStat(9), inchange.

et par bras, DEUX MUTATIONS ADVERSARIALES du PORT, rejouees sur le MEME snapshot :

  NOCHANNEL -- l'entree `InescapableAccuracy_extraCritChance` est RETIREE d'`EFFECT_CLASSES` (l'effet
               capte retombe sur `BaseEffect`, qui rend None). DOIT DIVERGER dans NOMOVE : c'est la
               GARDE DE DISCRIMINATION du bras -- sans elle, un « live == offline » ne prouverait
               rien (il serait vrai aussi d'un port qui n'applique rien du tout).
  NOGATE    -- les DEUX mirrors de l'`ActiveCondition` sont desarmes (`is_active` force a True, cle
               `has_moved` retiree de l'`att_ctx`). DOIT DIVERGER dans MOVED : c'est la garde de
               CHARGE UTILE du gate -- sans elle, « le port n'applique rien apres un pas » serait
               indistinguable d'un port qui n'applique jamais rien.

REGIME DE CRIT -- `--crit CC,CD` (defaut `50,700`). `CC > 0` est OBLIGATOIRE pour le bras de
reference : `IdunBattle.Core.Services.DamageCalculations$$CouldCrit(attacker)` lit `GetStat(9)`
BRUTE (le bonus d'effet n'y entre PAS), donc a `CC == 0` le natif ne tire aucun crit alors que le
port, qui passe `GetStat(9) + somme` a `could_crit`, en tirerait -- residu STRUCTUREL du port,
mesurable par `--crit 0,700 --expect-diverge` (bras `NOMOVE`, mutation NONE).

Le probe REFUSE de mesurer si le regime n'est pas atteint (geometrie, tour, effet absent/present a
contretemps, crit hors regime, attaque melee au lieu de rangee, cible morte) : un « vert » degrade
vaudrait moins que rien.

Usage (depuis scripts/python, session warmee) :
    python probe_366_r1_inescapable_accuracy_crit_chance.py
    python probe_366_r1_inescapable_accuracy_crit_chance.py --board C1_25 --seed 31337
    python probe_366_r1_inescapable_accuracy_crit_chance.py --arms NOMOVE --crit 0,700 --expect-diverge

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

#: Le SEUL porteur du passif `InescapableAccuracy` (`unit_map find --ability InescapableAccuracy` :
#: 6 entrees, dont UNE seule `lineup` -- les cinq autres sont des variantes de BOSS npc).
MAUGAN = "eldarMauganRa"
#: Le nom d'ABILITY (TriggeredAbilityType 1115) -- distinct du nom d'EffectType ci-dessous.
_ABILITY_CFG = "InescapableAccuracy"
EFFECT_NAME = "InescapableAccuracy_extraCritChance"
EFFECT_TYPE = 1115                   # EffectType 0x45b (homonyme de TriggeredAbilityType 1115)
#: Portee de l'arme a distance de MauganRa (`weapons[1].Range`) : le tir exige `2 <= d <= 3`
#: (d == 1 ferait basculer l'attaque normale sur l'arme MELEE, qui ferme `IsRangedAttack`).
RANGE_MAX = 3
RANGE_MIN = 2


def _unwrap(r):
    return r.get("result") if isinstance(r, dict) and "result" in r else r


def _effect_names(u):
    return [e.get("name") for e in ((u or {}).get("effects") or []) if isinstance(e, dict)]


def _upos(u):
    p = (u or {}).get("pos") or {}
    return (p.get("col"), p.get("row")) if p.get("col") is not None else None


def _hits_of(res, caster, target):
    """Degats per-coup lus dans les events de l'attaque live (tag `Amount`, paire attaquant/cible)."""
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


def neutralized_seed_bc(level: int = 50, hits: "int | None" = 1, zero_crit_dmg: bool = False):
    """Ecrit le seed BC du montage (+ son sidecar d'epinglage) : arme A DISTANCE de Maugan Ra a
    `hits` coup(s), et -- SI et seulement si `zero_crit_dmg` -- `InescapableAccuracy.extraCritDmg`
    force a **0**.

    ⚠ `zero_crit_dmg` VAUT MAINTENANT `False` PAR DEFAUT, ET C'EST UN RENVERSEMENT ASSUME (tranche
    #366-r1/1116). Tant que `1116 InescapableAccuracy_extraCritDmg` n'etait pas porte, le mettre a
    0 le rendait inerte DES DEUX COTES et c'etait la seule facon de lire l'ecart de 1115 sans le
    noyer dans les `extraCritDmg[50]` que le natif ajoutait a chaque crit. Depuis que 1116 EST
    porte, le meme geste INVERSE son effet et deviendrait un FAUX ROUGE : le patch vit dans le BC
    (donc le NATIF le voit), alors que le port lit `gameconfig.ability(...)` par
    `magnitude.ability_var` (donc il NE le voit PAS) -- le port ajouterait `extraCritDmg` la ou le
    natif n'ajouterait rien. Le laisser a `False` fait porter la mesure sur les DEUX volets du
    passif, chacun garde par son propre cliquet.

    Le sidecar `<seed>.pins.json` est INDISPENSABLE des qu'on patche (#375) : sans lui
    `refresh_ability_configs` ecrase le patch depuis le gameconfig vivant, **en silence**. Il est
    ecrit dans les deux cas (liste d'epingles vide quand il n'y a rien a epingler).

    `hits = 1` -- POURQUOI, et pourquoi ce n'est pas un confort : le port porte une divergence
    PRE-EXISTANTE de l'etage CRIT, INDEPENDANTE de ce cas, qui se declenche a partir du 3e coup
    d'une salve des qu'un coup a crite. Elle est REPRODUITE sur `necroDestroyer` (aucun rapport
    avec `InescapableAccuracy`) et en MELEE, ou 1115 est ferme -- residu nomme dans la fiche. Une
    salve d'UN coup mesure donc CE port, et rien d'autre ; la salve de 6 le noierait dans un ecart
    qui ne lui appartient pas. L'arme ranged (`Weapons[1]`, `Range` 3) est la seule touchee :
    l'arme melee reste a 5 coups."""
    import catalog_inject
    fd, out = tempfile.mkstemp(prefix="ia1115_seedbc_", suffix=".json")
    os.close(fd)
    patches = [(_ABILITY_CFG, level, {"extraCritDmg": 0})] if zero_crit_dmg else []
    p, reports = catalog_inject.write_variable_patched_seed_bc(out, patches)
    if hits is not None:
        bc = json.loads(Path(p).read_text(encoding="utf-8"))
        n = 0
        for u in (bc.get("Units") or []):
            if u.get("Id") != MAUGAN and u.get("VisualId") != MAUGAN:
                continue
            for w in (u.get("Weapons") or []):
                if w.get("IsRanged"):
                    w["Hits"] = int(hits)
                    n += 1
        if n != 1:
            raise RuntimeError("seed BC : %d arme(s) RANGED de %s patchee(s), attendu 1 -- le "
                               "montage 1-coup n'a pas pris" % (n, MAUGAN))
        Path(p).write_text(json.dumps(bc), encoding="utf-8")
        reports = list(reports) + [{"weapon_hits": int(hits), "unit": MAUGAN}]
    return str(p), reports


def build(a, arm):
    """Un runner par bras. Rend `(runnerId, state_file)` ou `(None, state_file)`.

    `--block-target 0,0` met `BlockChance/BlockDamage` de la cible a zero, c'est-a-dire le BLOCAGE
    DE DEGAT (`GetStat(7/8)` -> `IdunBattle.Core.Services.DamageCalculations$$CalculateBlockChances`)
    : un tirage de moins dans le flux, donc une salve comparable coup a coup.

    ⚠ RECTIFICATION (case-366-r1/1117) : ce n'est **PAS** le canal
    `IdunBattle.Entities.Effects.BaseEffect$$BlockHitsReduction` de `1117
    InescapableAccuracy_overrideHits`, contrairement a ce que disait cette docstring. Les deux
    « block » n'ont rien en commun : l'un est une stat de DEGAT de la cible, l'autre un
    interrupteur de l'axe COUPS. `1117` n'a jamais ete neutralise par cette option -- il etait
    simplement INERTE ici, faute de la moindre reduction de coups sur `necroWarden`/`necroOverlord`
    (aucun des deux ne porte Parry, Camouflage, LightCover, Diminutive ni BigTarget). Depuis qu'il
    est PORTE, il reste inerte pour la meme raison, des deux cotes. `1116`, LUI, n'a plus besoin
    d'etre neutralise : il est PORTE (cf. `neutralized_seed_bc`)."""
    fd, sf = tempfile.mkstemp(prefix="ia1115_%s_" % arm.lower(), suffix=".json")
    os.close(fd)
    Path(sf).unlink(missing_ok=True)
    argv = [sys.executable, "rl_duel.py", "build", "--seed", str(a.seed),
            "--state-file", sf, "--board", a.board,
            "--p-units", MAUGAN, "--a-units", "%s,%s" % (a.target_unit, a.other_unit),
            "--hp-target", "400000", "--hp-player", "400000", "--no-ai",
            "--crit", a.crit, "--block-target", "0,0"]
    if getattr(a, "seed_bc", None):
        argv += ["--seed-bc", a.seed_bc]
    argv += list(a.extra or [])
    p = subprocess.run(argv, cwd=str(PYDIR), capture_output=True, text=True,
                       encoding="utf-8", errors="replace")
    if not Path(sf).exists():
        print("[%s] build KO : %s" % (arm, (p.stderr or p.stdout or "")[-500:]))
        return None, sf
    return json.loads(Path(sf).read_text())["runnerId"], sf


def arrange_ranged(h, caster_visual, enemy_index=0):
    """GEOMETRIE DU TIR -- on DEPLACE les unites pour l'obtenir, jamais « bloque par les spawns ».

    Rend `{caster, target, start, step_to, anchor}` ou None. `start` est a `RANGE_MAX` hexes de
    l'ancre (dans la portee, hors contact) et `step_to` est ADJACENT a `start` tout en restant dans
    `[RANGE_MIN, RANGE_MAX]` de l'ancre : le bras MOVED change donc le FLAG `Moved`, et RIEN
    d'autre de ce que lit le canal (l'attaque reste rangee, la cible reste la meme, la distance
    reste dans la portee).

    ORDRE DES POSES : (1) ecarter les AUTRES ennemis, (2) poser la CIBLE sur l'ancre, (3) poser le
    CASTER. Le caster bouge en DERNIER pour que le montage ne fasse pas tirer en OVERWATCH une
    unite adverse sur lui (MauganRa porte lui-meme `Overwatch`, d'ou le choix d'ennemis qui ne le
    portent PAS -- `necroWarden` / `necroOverlord`)."""
    import hexgeo
    dv = h.dview()
    me = h.by_visual(caster_visual, dv)
    if me is None:
        return None
    h.my_player = me.get("owner")
    ens = h.enemies_of(h.my_player, dv)
    if len(ens) <= enemy_index:
        return None
    tgt = ens[enemy_index]
    for anchor in [h.board.coord(t) for t in sorted(h.board.by_id) if h.board.walkable(t)]:
        starts = h.free_tiles(anchor, RANGE_MAX, exclude=(me["id"], tgt["id"]))
        if not starts:
            continue
        near = [c for c in h.free_tiles(anchor, RANGE_MIN, exclude=(me["id"], tgt["id"]))]
        pairs = []
        for start in starts:
            for step_to in list(starts) + list(near):
                if step_to != start and hexgeo.distance(start, step_to) == 1:
                    pairs.append((start, step_to))
                    break
            if pairs:
                break
        if not pairs:
            continue
        # (1) les AUTRES ennemis a l'ecart (ni encaisseurs de splash, ni cibles alternatives).
        for other in ens:
            if other["id"] == tgt["id"]:
                continue
            far = h.free_tiles(anchor, 5, exclude=(other["id"],))
            if far:
                h.place(other["id"], far[0])
        # (2) la CIBLE sur l'ancre, (3) le CASTER a distance de tir.
        if not h.place(tgt["id"], anchor):
            continue
        start, step_to = pairs[0]
        if not h.place(me["id"], start):
            continue
        return {"caster": me["id"], "target": tgt["id"], "start": start,
                "step_to": step_to, "anchor": anchor}
    return None


def stage(h, do_step):
    """FOYER UNIQUE du montage (importe par le cliquet, jamais re-transcrit).

    Monte le bras et rend `(rec, reason)` : `reason is None` = regime ATTEINT."""
    import hexgeo
    plan = arrange_ranged(h, MAUGAN)
    if plan is None:
        return None, "geometrie RANGED (d=%d, pas d'un hex) non realisable" % RANGE_MAX
    if h.reach_my_turn(force_cycle=True) is None:
        return None, "mon tour non atteint"
    # Le cycle force purge `UnitFlag.Moved` (`StartTurnOperation$$ResetUnit`) : le bras NOMOVE part
    # donc bien d'un « n'a pas bouge », et le bras MOVED mesure SON pas et pas ceux du montage.
    dv = h.dview()
    pos = {u["id"]: _upos(u) for u in h.alive(dv)}
    if pos.get(plan["caster"]) != plan["start"] or pos.get(plan["target"]) != plan["anchor"]:
        return None, "geometrie perdue apres les endturns"
    names = _effect_names(h.by_visual(MAUGAN, dv))
    if EFFECT_NAME not in names:
        return None, "%s ABSENT du seed live (effets=%s)" % (EFFECT_NAME, names)
    atk = h.normal_attack_type(plan["caster"], dv)
    if atk is None:
        return None, "pas d'attaque normale sur u%s" % plan["caster"]
    rec = dict(plan)
    rec["ability_type"] = int(atk)
    rec["snapshot"] = h.snapshot()
    if not do_step:
        rec["step_to"] = None
    else:
        if not h.place(plan["caster"], plan["step_to"]):
            return None, "pas refuse (tuile occupee / hors portee de mouvement)"
        d = hexgeo.distance(plan["step_to"], plan["anchor"])
        if not (RANGE_MIN <= d <= RANGE_MAX):
            return None, "apres le pas d=%d hors [%d,%d] : le tir changerait de NATURE" % (
                d, RANGE_MIN, RANGE_MAX)
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
    materialise l'effet capte) ; `NOGATE` desarme les DEUX mirrors de l'`ActiveCondition`."""
    from engine.entities.effects.factory import EFFECT_CLASSES
    from engine.entities.effects.loki.inescapable_accuracy import (
        InescapableAccuracyExtraCritChanceEffect as K)
    saved_reg = EFFECT_CLASSES.get(EFFECT_NAME)
    saved_gate = (K.is_active, K.create_effect_crit_chance_bonus_for_attack)
    try:
        if mutate == "NOCHANNEL":
            EFFECT_CLASSES.pop(EFFECT_NAME, None)
        elif mutate == "NOGATE":
            orig = saved_gate[1]
            K.is_active = lambda self, unit_state=None: True
            K.create_effect_crit_chance_bonus_for_attack = (
                lambda self, att_ctx=None: orig(
                    self, {k: v for k, v in (att_ctx or {}).items() if k != "has_moved"}))
        return h.replay_offline(rec)["per_hit"]
    finally:
        if saved_reg is not None:
            EFFECT_CLASSES[EFFECT_NAME] = saved_reg
        K.is_active, K.create_effect_crit_chance_bonus_for_attack = saved_gate


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
        rec, why = stage(h, arm == "MOVED")
        if rec is None:
            print("[%s] REFUS : %s" % (arm, why))
            return 2

        # GARDES DE REGIME -- lues sur l'etat OFFLINE de reference, AVANT toute mesure.
        from engine.entities.stats import StatType
        from engine.runner.components import StatsComponent, unit_has_moved
        st0 = h.offline_state(rec)
        sc = st0.get_entity(rec["caster"]).get_component(StatsComponent)
        cc0 = int(sc.ctx.stat(StatType.CRIT_CHANCE) or 0)
        moved = bool(unit_has_moved(st0, rec["caster"]))
        print("[%s] attaquant u%s cc_base=%d has_moved=%s | cible u%s d=%s"
              % (arm, rec["caster"], cc0, moved, rec["target"],
                 "start" if rec["step_to"] is None else "step"))
        if moved != (arm == "MOVED"):
            print("[%s] REFUS : has_moved=%s hors regime -- rien n'est mesure" % (arm, moved))
            return 2
        want_cc = int((a.crit.split(",") or ["0"])[0])
        if cc0 != want_cc:
            print("[%s] REFUS : GetStat(9)=%d != %d demande par --crit" % (arm, cc0, want_cc))
            return 2

        live, why = strike(h, rec)
        if live is None:
            print("[%s] REFUS : %s" % (arm, why))
            return 2
        off = replay(h, rec)
        print("[%s] LIVE    n=%d %s" % (arm, len(live), live))
        print("[%s] OFFLINE n=%d %s" % (arm, len(off), off))
        # PORTEE DE LA COMPARAISON. Le montage `--hits` s'applique au NATIF seul : le port derive
        # le nombre de coups du GAMECONFIG par visualId (`battle_query.select_weapon_pierce` ->
        # `get_attack_weapon_for_default_normal_attack(ctx.visual_id, ...)`), pas du BC ni du
        # snapshot -- residu de SOURCE nomme dans la fiche. On confronte donc les `len(live)`
        # premieres cellules, les SEULES ou les deux modeles sont sur la MEME case du flux PRNG
        # (meme dump `rng_after_step` en entree). Le harnais REFUSE si le natif n'a pas rendu
        # exactement les `--hits` coups demandes : sans cette garde, une salve tronquee (cible
        # morte, coup avale) passerait pour un accord.
        n = len(live)
        if not a.keep_crit_dmg and n != int(a.hits):
            print("[%s] REFUS : le natif a joue %d coup(s), %d demande(s) par --hits"
                  % (arm, n, a.hits))
            return 2
        if len(off) >= n:
            print("[%s] DELTA   %s" % (arm, [l - o for l, o in zip(live, off[:n])]))
        expect_div = bool(a.expect_diverge)
        same = off[:n] == live
        print("[%s] VERDICT per_hit %s (attendu : %s)"
              % (arm, "OK" if same else "DIVERGE", "DIVERGE" if expect_div else "OK"))
        rc = 0 if (same != expect_div) else 1

        # GARDE DE DISCRIMINATION -- la mutation se compare au REJEU DE REFERENCE, jamais au live :
        # `mut == off` veut dire que desarmer le mecanisme ne change RIEN au modele, donc que la
        # salve ne l'exerce pas (aucun tirage de crit ne tombe dans la fenetre ouverte par les 15
        # points). Comparer a `live` serait vide de sens des que live et off different deja.
        if not a.no_mutations:
            want = {"NOMOVE": "NOCHANNEL", "MOVED": "NOGATE"}[arm]
            mut = replay(h, rec, mutate=want)
            print("[%s] MUT-%s n=%d %s" % (arm, want, len(mut), mut))
            if mut[:n] == off[:n]:
                print("[%s] REFUS : la mutation %s ne change RIEN au rejeu -- la salve n'exerce "
                      "PAS le mecanisme (aucun tirage dans la fenetre des 15 points) ; varier "
                      "--crit / --seed / --board" % (arm, want))
                rc |= 2
            else:
                print("[%s] MUT-%s change le rejeu : la salve EXERCE le mecanisme" % (arm, want))
        return rc
    finally:
        rpc("disposeRunner", {"runnerId": rid}, 20)
        Path(sf).unlink(missing_ok=True)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--seed", default="777")
    ap.add_argument("--board", default="MC1_67")
    ap.add_argument("--crit", default="50,700",
                    help="CritChance,CritDamage des p-units. CC>0 requis hors mesure du residu "
                         "`could_crit` (cf. l'en-tete).")
    ap.add_argument("--target-unit", default="necroWarden", help="cible SANS trait Overwatch")
    ap.add_argument("--other-unit", default="necroOverlord", help="2e ennemi, ecarte par le montage")
    ap.add_argument("--arms", default="NOMOVE,MOVED")
    ap.add_argument("--expect-diverge", action="store_true",
                    help="le bras doit DIVERGER (mesure du residu `could_crit` a --crit 0,...)")
    ap.add_argument("--no-mutations", action="store_true",
                    help="saute les gardes de discrimination (diagnostic seulement)")
    ap.add_argument("--keep-crit-dmg", action="store_true",
                    help="AUCUN seed BC custom : salve PLEINE et config d'origine (diagnostic : "
                         "montre le residu CRIT pre-existant a partir du 3e coup)")
    ap.add_argument("--zero-crit-dmg", action="store_true",
                    help="force `InescapableAccuracy.extraCritDmg = 0` dans le seed BC. Depuis que "
                         "1116 est PORTE ce n'est plus une neutralisation mais une DESYNCHRO "
                         "voulue (le patch vit dans le BC, le port lit le gameconfig) : reserve au "
                         "diagnostic, il DOIT faire diverger tout coup critique")
    ap.add_argument("--hits", type=int, default=1,
                    help="coups de l'arme RANGED de Maugan Ra imposes au seed BC (defaut 1)")
    ap.add_argument("--extra", action="append", default=[],
                    help="arg supplementaire passe a `rl_duel build` (repetable)")
    a = ap.parse_args()
    a.seed_bc = None
    if not a.keep_crit_dmg:
        a.seed_bc, rep = neutralized_seed_bc(hits=a.hits, zero_crit_dmg=a.zero_crit_dmg)
        print("[probe] seed BC (ranged Hits = %d, extraCritDmg zero = %s) : %s | %s"
              % (a.hits, a.zero_crit_dmg, a.seed_bc, rep))

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
