#!/usr/bin/env python
"""probe #366-r1 -- MESURE d'`InescapableAccuracy_extraCritDmg` (1116) sur `eldarMauganRa`.

CRITERION BINAIRE : « le port ajoute-t-il -- ET REFUSE-T-IL d'ajouter apres un mouvement -- la
contribution de 1116 comme le natif ? », mesure la ou l'effet MORD : le DEGAT PER-COUP d'un coup
CRITIQUE a distance, dont le montant passe par
`IdunBattle.Core.Services.DamagePrediction$$CalculateCriticalDamage` = `max(0, GetStat(10) +
GetCritDamageBonusFromEffects)`.

RE (detail : `docs/rl/case-366-r1-inescapable-accuracy-crit-damage.md`) --
`IdunBattleLogic.Entities.Abilities.Triggered.Loki.InescapableAccuracy_ExtraCritDamageEffect$$
CreateCritDamageBonus` :

    EffectBonus.ForAddition( get_OwnerIsCaster & IsRangedAttack,
                             ConfigVar(0x42 = extraCritDmg, GetAbilityState(effect), config@+0x60) )

et la `CreateActiveCondition` PARTAGEE par les trois classes du passif :

    op_LogicalNot( HasFlag( Owner, 0 = UnitFlag.Moved ) )

CE QUI DISTINGUE CE PROBE DE CELUI DE SON JUMEAU `1115` -- et pourquoi c'est un montage a part :
1115 decide SI le coup crite (`RollCritical`), 1116 decide de COMBIEN. Mesurer 1116 exige donc que
le coup CRITE **dans les deux bras**, sans quoi le bras MOVED ne mesurerait rien du tout (un coup
non critique ne traverse pas `CalculateCriticalDamage`). D'ou `--crit 100,700` par DEFAUT :

  NOMOVE -- MauganRa tire SANS avoir bouge. `clamp(100 + extraCritChance) = 100` -> CRIT certain,
            et `critDmg = GetStat(10) + extraCritDmg[50]`.
  MOVED  -- MauganRa fait UN pas (en restant a portee ET hors contact) puis tire. `UnitFlag.Moved`
            pose -> les DEUX volets sont inactifs : `clamp(100) = 100` -> CRIT toujours certain,
            mais `critDmg = GetStat(10)` seul. Le bras isole donc le GATE **sur le montant**.
  MELEE  -- MauganRa frappe AU CONTACT (d == 1) sans avoir bouge : l'`ActiveCondition` est VRAIE,
            et pourtant `IsRangedAttack` FERME le canal. Le bras isole le noeud d'ATTAQUE seul, la
            ou les deux precedents isolent le noeud de MOUVEMENT.

et par bras, une ou plusieurs MUTATIONS ADVERSARIALES du PORT, rejouees sur le MEME snapshot :

  NOCHANNEL   -- l'entree `InescapableAccuracy_extraCritDmg` est RETIREE d'`EFFECT_CLASSES` (l'effet
                 capte retombe sur `BaseEffect`, qui rend None). DOIT DIVERGER dans NOMOVE : c'est
                 la GARDE DE DISCRIMINATION du bras -- sans elle, un « live == offline » serait
                 vrai aussi d'un port qui n'applique rien du tout.
  NOSCALE     -- le multiplicateur de rarete force a 100. DOIT DIVERGER dans NOMOVE : `extraCritDmg`
                 EST dans `variablesAffectedByRarityBonus` (contrairement a `extraCritChance`), donc
                 la valeur juste est `round(554 * 180/100) = 997` et non `554`. Sans cette mutation,
                 un port qui aurait « oublie » le scaling passerait pour juste si le natif l'avait
                 oublie aussi -- ce que la mesure exclut.
  NOGATE      -- les DEUX mirrors de l'`ActiveCondition` de 1116 sont desarmes (`is_active` force a
                 True, cle `has_moved` retiree de l'`att_ctx`) -- CEUX DE 1116 SEULEMENT, la classe
                 de 1115 n'est pas touchee. DOIT DIVERGER dans MOVED : garde de CHARGE UTILE du gate.
  NORANGEGATE -- le noeud `IsRangedAttack` desarme (`is_ranged` force a True). DOIT DIVERGER dans
                 MELEE : sans lui, le port appliquerait le bonus a une frappe de contact.

MONTAGE PARTAGE avec le probe de 1115, IMPORTE et non re-transcrit (`stage`, `strike`,
`arrange_ranged`, `neutralized_seed_bc`) : deux transcriptions du meme montage finissent par
diverger. Les contraintes qu'il porte valent telles quelles ici --
  * salve RANGED (`2 <= d <= 3` avant ET apres le pas : au contact l'attaque bascule sur l'arme
    melee et `IsRangedAttack` se ferme) ;
  * `--block-target 0,0` (le canal BLOCK de la cible est celui du jumeau NON PORTE `1117`) ;
  * ennemis sans `Overwatch` ;
  * arme ranged a **1 coup** impose au seed BC -- CONTOURNEMENT du residu MESURE
    `#366-r1-crit-multihit` (l'etage CRIT diverge des le 3e coup d'une salve, independamment de
    toute ability, reproduit sur `necroDestroyer` et en melee ; tague `[fable]`, hors de ce cas).
    Un coup qui CRITE est exactement la cellule ou 1116 se manifeste.
  * `extraCritDmg` N'EST PAS neutralise (contrairement a ce que faisait le montage de 1115 quand
    1116 n'etait pas porte) : le patch vivrait dans le BC -- donc cote NATIF -- alors que le port
    lit `gameconfig` ; il ferait DIVERGER a coup sur.

Usage (depuis scripts/python, session warmee) :
    python probe_366_r1_inescapable_accuracy_crit_damage.py
    python probe_366_r1_inescapable_accuracy_crit_damage.py --board C1_25 --seed 31337
    python probe_366_r1_inescapable_accuracy_crit_damage.py --arms NOMOVE

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

from probe_366_r1_inescapable_accuracy_crit_chance import (   # noqa: E402
    MAUGAN, neutralized_seed_bc, stage, strike)

#: EffectType 0x45c (a NE PAS confondre avec `TriggeredAbilityType 1116 = Shrapnel` : l'homonymie
#: d'id entre les deux enums est reelle et sans rapport -- la config lue par le ctor est
#: `TriggeredAbilityType 1115 = InescapableAccuracy`).
EFFECT_NAME = "InescapableAccuracy_extraCritDmg"
EFFECT_TYPE = 1116


def _unwrap(r):
    return r.get("result") if isinstance(r, dict) and "result" in r else r


def build(a, arm):
    """Un runner par bras. Rend `(runnerId, state_file)` ou `(None, state_file)`."""
    fd, sf = tempfile.mkstemp(prefix="ia1116_%s_" % arm.lower(), suffix=".json")
    os.close(fd)
    Path(sf).unlink(missing_ok=True)
    argv = [sys.executable, "rl_duel.py", "build", "--seed", str(a.seed),
            "--state-file", sf, "--board", a.board,
            "--p-units", MAUGAN, "--a-units", "%s,%s" % (a.target_unit, a.other_unit),
            "--hp-target", "400000", "--hp-player", "400000", "--no-ai",
            "--crit", a.crit, "--block-target", "0,0"]
    seed_bc = a.seed_bc_melee if arm == "MELEE" else a.seed_bc
    if seed_bc:
        argv += ["--seed-bc", seed_bc]
    argv += list(a.extra or [])
    p = subprocess.run(argv, cwd=str(PYDIR), capture_output=True, text=True,
                       encoding="utf-8", errors="replace")
    if not Path(sf).exists():
        print("[%s] build KO : %s" % (arm, (p.stderr or p.stdout or "")[-500:]))
        return None, sf
    return json.loads(Path(sf).read_text())["runnerId"], sf


def replay(h, rec, mutate=None):
    """Rejeu OFFLINE du MEME snapshot, avec (option) une mutation ADVERSARIALE du PORT.

    QUATRE mutations, une par artefact porte -- chacune doit ROUGIR le bras qui l'exerce :

      NOCHANNEL    l'inscription `EFFECT_CLASSES[1116]` est retiree (l'effet capte retombe sur
                   `BaseEffect`, qui rend None)                                    -> bras NOMOVE
      NOGATE       les DEUX mirrors de l'`ActiveCondition` desarmes                 -> bras MOVED
      NORANGEGATE  le noeud `IsRangedAttack` desarme (cle `is_ranged` forcee a True) -> bras MELEE
      NOSCALE      le multiplicateur de rarete force a 100 (`extraCritDmg` EST dans
                   `variablesAffectedByRarityBonus`)                                -> bras NOMOVE

    Les trois premieres ne touchent QUE la classe de 1116 : `is_active` est HERITEE de
    `_InescapableAccuracyEffect` (le corps natif de `CreateActiveCondition` est partage), donc
    l'ecraser pose un attribut sur la SOUS-CLASSE et le `finally` le SUPPRIME -- 1115 n'est jamais
    affecte, et le bras reste une mesure de 1116 seul. `NOSCALE` patche le `ability_var` du MODULE,
    donc visible aussi de 1115 -- sans effet, `extraCritChance` n'etant PAS scalee (c'est
    exactement l'asymetrie que cette mutation verrouille)."""
    import engine.entities.effects.loki.inescapable_accuracy as M
    from engine.entities.effects.factory import EFFECT_CLASSES
    from engine.entities.effects.loki.inescapable_accuracy import (
        InescapableAccuracyExtraCritDamageEffect as K)
    saved_reg = EFFECT_CLASSES.get(EFFECT_NAME)
    had_own_is_active = "is_active" in K.__dict__
    saved_is_active = K.__dict__.get("is_active")
    saved_chan = K.__dict__["create_effect_crit_damage_bonus_for_attack"]
    saved_av = M.ability_var
    try:
        if mutate == "NOCHANNEL":
            EFFECT_CLASSES.pop(EFFECT_NAME, None)
        elif mutate == "NOGATE":
            orig = K.create_effect_crit_damage_bonus_for_attack
            K.is_active = lambda self, unit_state=None: True
            K.create_effect_crit_damage_bonus_for_attack = (
                lambda self, att_ctx=None: orig(
                    self, {k: v for k, v in (att_ctx or {}).items() if k != "has_moved"}))
        elif mutate == "NORANGEGATE":
            orig = K.create_effect_crit_damage_bonus_for_attack
            K.create_effect_crit_damage_bonus_for_attack = (
                lambda self, att_ctx=None: orig(self, {**(att_ctx or {}), "is_ranged": True}))
        elif mutate == "NOSCALE":
            M.ability_var = lambda *ar, **kw: saved_av(*ar, **{**kw, "multiplier_pct": 100})
        return h.replay_offline(rec)["per_hit"]
    finally:
        M.ability_var = saved_av
        if saved_reg is not None:
            EFFECT_CLASSES[EFFECT_NAME] = saved_reg
        if had_own_is_active:
            K.is_active = saved_is_active
        elif "is_active" in K.__dict__:
            del K.is_active
        K.create_effect_crit_damage_bonus_for_attack = saved_chan


def melee_seed_bc(hits: int = 1):
    """Seed BC du bras MELEE : **TOUTES** les armes de Maugan Ra a `hits` coup(s).

    Le bras MELEE frappe avec `weapons[0]` (5 coups au kit) : sans ce patch la salve retomberait
    dans le regime du residu `#366-r1-crit-multihit`, qui n'appartient pas a ce cas. On patche les
    deux armes pour que le montage soit le meme quelle que soit celle que le natif selectionne."""
    import catalog_inject
    fd, out = tempfile.mkstemp(prefix="ia1116_melee_seedbc_", suffix=".json")
    os.close(fd)
    p, _ = catalog_inject.write_variable_patched_seed_bc(out, [])
    bc = json.loads(Path(p).read_text(encoding="utf-8"))
    n = 0
    for u in (bc.get("Units") or []):
        if u.get("Id") != MAUGAN and u.get("VisualId") != MAUGAN:
            continue
        for w in (u.get("Weapons") or []):
            w["Hits"] = int(hits)
            n += 1
    if n < 2:
        raise RuntimeError("seed BC MELEE : %d arme(s) de %s patchee(s), >=2 attendues" % (n, MAUGAN))
    Path(p).write_text(json.dumps(bc), encoding="utf-8")
    return str(p), [{"weapon_hits": int(hits), "weapons": n, "unit": MAUGAN}]


def arrange_melee(h, caster_visual, enemy_index=0):
    """GEOMETRIE DU CONTACT (d == 1) -- on DEPLACE les unites pour l'obtenir.

    C'est le bras qui exerce le noeud `IsRangedAttack` du canal : au contact l'attaque normale
    bascule sur l'arme MELEE (`weapons[0]`), `IsRangedAttack` se FERME, et 1116 ne doit RIEN
    ajouter alors que son `ActiveCondition` est pourtant VRAIE (le porteur n'a pas bouge). Le gate
    d'attaque est donc mesure SEUL, sans le gate de mouvement.

    Meme ordre des poses que le montage RANGED : (1) ecarter les autres ennemis, (2) la cible sur
    l'ancre, (3) le caster en DERNIER."""
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
        adj = h.free_tiles(anchor, 1, exclude=(me["id"], tgt["id"]))
        if not adj:
            continue
        for other in ens:
            if other["id"] == tgt["id"]:
                continue
            far = h.free_tiles(anchor, 5, exclude=(other["id"],))
            if far:
                h.place(other["id"], far[0])
        if not h.place(tgt["id"], anchor):
            continue
        if not h.place(me["id"], adj[0]):
            continue
        return {"caster": me["id"], "target": tgt["id"], "start": adj[0],
                "step_to": None, "anchor": anchor}
    return None


def stage_melee(h):
    """Monte le bras MELEE et rend `(rec, reason)` -- `reason is None` = regime ATTEINT."""
    from probe_366_r1_inescapable_accuracy_crit_chance import _effect_names, _upos
    plan = arrange_melee(h, MAUGAN)
    if plan is None:
        return None, "geometrie MELEE (d=1) non realisable"
    if h.reach_my_turn(force_cycle=True) is None:
        return None, "mon tour non atteint"
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
    rec["rng_after_step"] = h.rpc("dumpRng", {"runnerId": h.rid}, 30)
    return rec, None


def carried(rec, off_state):
    """1116 MATERIALISE offline sur l'attaquant -- sinon on comparerait deux absences."""
    return [e for e in (off_state.effects.by_unit.get(rec["caster"]) or [])
            if getattr(e, "effect_type", None) == EFFECT_TYPE or getattr(e, "name", None) == EFFECT_NAME]


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
        rec, why = stage_melee(h) if arm == "MELEE" else stage(h, arm == "MOVED")
        if rec is None:
            print("[%s] REFUS : %s" % (arm, why))
            return 2

        # GARDES DE REGIME -- lues sur l'etat OFFLINE de reference, AVANT toute mesure.
        from engine.entities.stats import StatType
        from engine.runner.components import StatsComponent, unit_has_moved
        st0 = h.offline_state(rec)
        sc = st0.get_entity(rec["caster"]).get_component(StatsComponent)
        cc0 = int(sc.ctx.stat(StatType.CRIT_CHANCE) or 0)
        cd0 = int(sc.ctx.stat(StatType.CRIT_DAMAGE) or 0)
        moved = bool(unit_has_moved(st0, rec["caster"]))
        held = carried(rec, st0)
        print("[%s] attaquant u%s cc_base=%d cd_base=%d has_moved=%s | 1116 porte=%d | cible u%s"
              % (arm, rec["caster"], cc0, cd0, moved, len(held), rec["target"]))
        if not held:
            print("[%s] REFUS : %s ABSENT de l'etat offline -- rien a mesurer" % (arm, EFFECT_NAME))
            return 2
        if moved != (arm == "MOVED"):
            print("[%s] REFUS : has_moved=%s hors regime -- rien n'est mesure" % (arm, moved))
            return 2
        if arm == "MELEE":
            import hexgeo
            d = hexgeo.distance(rec["start"], rec["anchor"])
            print("[MELEE] distance caster-cible = %d (contact attendu : 1)" % d)
            if d != 1:
                print("[MELEE] REFUS : d=%d != 1 -- l'attaque ne serait pas MELEE" % d)
                return 2
        want_cc, want_cd = [int(x) for x in a.crit.split(",")[:2]]
        if cc0 != want_cc or cd0 != want_cd:
            print("[%s] REFUS : GetStat(9)=%d GetStat(10)=%d != %d,%d demande par --crit"
                  % (arm, cc0, cd0, want_cc, want_cd))
            return 2
        if cc0 < 100:
            print("[%s] REFUS : GetStat(9)=%d < 100 -- le CRIT n'est pas certain, ce bras ne "
                  "mesurerait pas le MONTANT de crit de facon deterministe" % (arm, cc0))
            return 2

        live, why = strike(h, rec)
        if live is None:
            print("[%s] REFUS : %s" % (arm, why))
            return 2
        off = replay(h, rec)
        n = len(live)
        print("[%s] LIVE    n=%d %s" % (arm, n, live))
        print("[%s] OFFLINE n=%d %s" % (arm, len(off), off))
        if n != int(a.hits):
            print("[%s] REFUS : le natif a joue %d coup(s), %d demande(s) par --hits -- la mesure "
                  "retomberait dans le regime du residu `#366-r1-crit-multihit`" % (arm, n, a.hits))
            return 2
        if len(off) >= n:
            print("[%s] DELTA   %s" % (arm, [l - o for l, o in zip(live, off[:n])]))
        same = off[:n] == live
        print("[%s] VERDICT per_hit %s" % (arm, "OK" if same else "DIVERGE"))
        rc = 0 if same else 1

        # GARDE DE DISCRIMINATION -- la mutation se compare au REJEU DE REFERENCE, jamais au live.
        if not a.no_mutations:
            for want in {"NOMOVE": ["NOCHANNEL", "NOSCALE"], "MOVED": ["NOGATE"],
                         "MELEE": ["NORANGEGATE"]}[arm]:
                mut = replay(h, rec, mutate=want)
                print("[%s] MUT-%s n=%d %s" % (arm, want, len(mut), mut))
                if mut[:n] == off[:n]:
                    print("[%s] REFUS : la mutation %s ne change RIEN au rejeu -- ce coup n'exerce "
                          "PAS le mecanisme (le coup n'a probablement pas crite) ; varier --crit / "
                          "--seed / --board" % (arm, want))
                    rc |= 2
                else:
                    print("[%s] MUT-%s change le rejeu : le coup EXERCE le mecanisme" % (arm, want))
        return rc
    finally:
        rpc("disposeRunner", {"runnerId": rid}, 20)
        Path(sf).unlink(missing_ok=True)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--seed", default="777")
    ap.add_argument("--board", default="MC1_67")
    ap.add_argument("--crit", default="100,700",
                    help="CritChance,CritDamage des p-units. CC=100 est REQUIS : 1116 ne modifie "
                         "que le MONTANT d'un crit, il faut donc que le coup crite dans les DEUX "
                         "bras pour que le gate soit lisible sur le montant seul.")
    ap.add_argument("--target-unit", default="necroWarden", help="cible SANS trait Overwatch")
    ap.add_argument("--other-unit", default="necroOverlord", help="2e ennemi, ecarte par le montage")
    ap.add_argument("--arms", default="NOMOVE,MOVED,MELEE")
    ap.add_argument("--no-mutations", action="store_true",
                    help="saute les gardes de discrimination (diagnostic seulement)")
    ap.add_argument("--hits", type=int, default=1,
                    help="coups de l'arme RANGED de Maugan Ra imposes au seed BC (defaut 1 -- "
                         "contourne le residu `#366-r1-crit-multihit`)")
    ap.add_argument("--extra", action="append", default=[],
                    help="arg supplementaire passe a `rl_duel build` (repetable)")
    a = ap.parse_args()
    arms = [x.strip() for x in a.arms.split(",") if x.strip()]
    a.seed_bc = a.seed_bc_melee = None
    if [x for x in arms if x != "MELEE"]:
        a.seed_bc, rep = neutralized_seed_bc(hits=a.hits)
        print("[probe] seed BC RANGED (ranged Hits = %d, extraCritDmg INTACT) : %s | %s"
              % (a.hits, a.seed_bc, rep))
    if "MELEE" in arms:
        a.seed_bc_melee, rep = melee_seed_bc(hits=a.hits)
        print("[probe] seed BC MELEE (toutes armes Hits = %d) : %s | %s"
              % (a.hits, a.seed_bc_melee, rep))

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
    for arm in arms:
        rc |= run_case(a, rpc, Board, ChargeRegimeHarness, arm)
    return rc


if __name__ == "__main__":
    raise SystemExit(main())
