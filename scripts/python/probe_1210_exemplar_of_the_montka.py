"""PROBE 1210 `ExemplarOfTheMontka` -- confrontation LIVE du port (`tauFarsight`).

`tauFarsight` est ABSENT de `rl_duel build --list-pool` : ce probe l'INJECTE
(`catalog_inject --units tauFarsight --out <abs>.json` puis `build --seed-bc`), recette
`docs/rl/case-92-catalog-injection.md` §6. Absent du pool != non confrontable.

MONTAGE, choisi pour que le DISCRIMINANT existe -- le selecteur natif est
`UnitsWithRangedWeapons(UnitsWithTrait(Friends(Caster, AllAliveUnits, 3), Hero, 3))`, donc il faut
au moins un ami qui echoue a CHACUN des deux filtres, sinon le bras ne prouve rien :

    p-units  tauFarsight      Hero + arme `Plasma Range 2` + BigTarget -> BUFFE (par le FILTRE,
                              pas par une exception : 1210 n'a NI `op_Subtraction` NI
                              `op_Addition`, contrairement au jumeau de forme WarHowl 1106)
             tauDarkstrider   Hero + arme `Pulse Range 2`             -> BUFFE
             tauAunShi        Hero + arme `Power` SANS Range          -> **NON BUFFE** (temoin du
                              filtre `UnitsWithRangedWeapons`, celui que 1106 a en NEGATIF)
    a-units  tauCrisis        BigTarget (cible de l'axe `If(HasTrait(Target, BigTarget))`)
             ultraTitus       PAS BigTarget (l'autre branche)

QUATRE bras, et chacun peut rougir seul :
  1. SELECTEUR   : les unites que le NATIF buffe == celles que le PORT selectionne ;
  2. TRAIT natif : qui GAGNE `UnitTrait.Unstoppable` (0x412) au cast (temoin d'ajout exige) ;
  3. TRAIT port  : le port POSE-t-il puis RETIRE-t-il le meme trait sur le MEME etat ? -- sans ce
     bras, les deux premiers resteraient VERTS si `applied_traits()` rendait `[]` ;
  4. DEGAT       : la magnitude `create_effect_damage_bonus_for_attack` du port confrontee au kit
     gameconfig, dans les DEUX branches du `If` (BigTarget / non), au niveau REEL du caster.

ASCII only (cp1252).
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

PYDIR = Path(__file__).resolve().parent
sys.path.insert(0, str(PYDIR))

BOARD = "MC1_67"
CASTER_VIS = "tauFarsight"
RANGED_ALLY = "tauDarkstrider"       # Hero + Range 2  -> buffe
MELEE_ALLY = "tauAunShi"             # Hero, arme `Power` SANS Range -> NON buffe
SUMMONER = "tauMarksman"             # `MV71SniperDroneSquad` -> `tauSmnDroneSniper`
SUMMON_WITNESS = "tauSmnDroneSniper"  # NON-Hero + arme `Piercing Range 4` -> NON buffe
FOES = "tauCrisis,ultraTitus"        # BigTarget / non-BigTarget

#: Le TEMOIN du filtre `Hero`, et pourquoi il faut un SUMMON pour l'avoir. Balayage du pool
#: (97 unites regulieres au rank courant) : **0** unite `lineup` n'est non-Hero, et les 8 MoW
#: spawnables n'ont AUCUNE arme au gameconfig (donc elles echouent au filtre RANGED, pas au filtre
#: HERO -- elles ne discriminent rien). Sans ce summon, retirer `UnitsWithTrait(Hero)` du port
#: serait un mutant INERTE : le montage ne pourrait pas le voir.
_HERO_WITNESS_NOTE = "tauSmnDroneSniper : Summon/Flying/Mechanical/RangedSpecialist, Piercing R4"

MONTKA = 1210                        # ActiveAbilityType.ExemplarOfTheMontka (0x4ba)
BUFF = 1498                          # EffectType.ExemplarOfTheMontka (0x5da)
BUFF_NAME = "ExemplarOfTheMontka"    # `decisionView` ne publie que le NOM de l'effet
UNSTOPPABLE = 1042                   # UnitTrait.Unstoppable (0x412)
BIG_TARGET = 1017                    # UnitTrait.BigTarget (0x3f9)


def _unwrap(r):
    if isinstance(r, dict) and "result" in r and set(r) <= {"ok", "result", "error"}:
        return r["result"]
    return r


def _by_unit(snap, dv):
    """DEUX canaux : `combatSnapshot.units[].traits` (l'invoke de `UnitExtensions$$HasTrait` par
    valeur d'enum) et `decisionView.units[].effects[].name` (canal ACTIF-ONLY)."""
    names = {}
    for u in (dv or {}).get("units") or []:
        uid = u.get("id")
        if uid is None:
            continue
        names[int(uid)] = sorted(e.get("name") for e in (u.get("effects") or []) if e.get("name"))
    out = {}
    for u in (snap or {}).get("units") or []:
        uid = u.get("entityId")
        if uid is None:
            continue
        out[int(uid)] = {"vis": ((u.get("unitConfig") or {}).get("visualId")),
                         "traits": sorted(int(t) for t in (u.get("traits") or [])),
                         "effects": names.get(int(uid), [])}
    return out


def _line(tag, uid, rec):
    print("[1210/%s] u%-4s %-16s buff1498=%-5s unstoppable=%-5s effets=%s"
          % (tag, uid, rec["vis"], BUFF_NAME in rec["effects"],
             UNSTOPPABLE in rec["traits"], rec["effects"]))


def _inject(out_path):
    argv = [sys.executable, "catalog_inject.py", "--units", CASTER_VIS, "--out", out_path]
    p = subprocess.run(argv, cwd=str(PYDIR), capture_output=True, text=True,
                       encoding="utf-8", errors="replace")
    if not Path(out_path).exists():
        print("[1210] injection KO : %s" % (p.stderr or p.stdout or "")[-600:])
        return False
    return True


def _build(state_file, seed, seed_bc, with_summoner):
    p_units = [CASTER_VIS, RANGED_ALLY, MELEE_ALLY] + ([SUMMONER] if with_summoner else [])
    argv = [sys.executable, "rl_duel.py", "build", "--seed", str(seed), "--board", BOARD,
            "--seed-bc", seed_bc,
            "--p-units", ",".join(p_units),
            "--a-units", FOES, "--state-file", state_file, "--no-ai"]
    p = subprocess.run(argv, cwd=str(PYDIR), capture_output=True, text=True,
                       encoding="utf-8", errors="replace")
    if not Path(state_file).exists():
        print("[1210] build KO : %s" % (p.stderr or p.stdout or "")[-800:])
        return None
    return json.loads(Path(state_file).read_text())["runnerId"]


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--state-file", required=True, help="chemin ABSOLU, hors data/")
    ap.add_argument("--seed-bc", required=True, help="chemin ABSOLU du seed BC augmente a ecrire")
    ap.add_argument("--seed", type=int, default=777)
    ap.add_argument("--keep", action="store_true", help="ne pas disposer le runner en sortie")
    ap.add_argument("--hero-witness", action="store_true",
                    help="ajoute `tauMarksman` et fait spawner `tauSmnDroneSniper` AVANT le cast : "
                         "le TEMOIN du filtre `UnitsWithTrait(Hero)` (non-Hero mais RANGED). Sans "
                         "lui, retirer ce filtre du port est un mutant INERTE sur ce montage.")
    a = ap.parse_args(argv)

    import rl_collect_batch as R
    sid = R._resolve_session()
    w = _unwrap(R._rpc(sid, "autoBootExtraire", [{}], timeout=180))
    if not (isinstance(w, dict) and w.get("ok")):
        print("[1210] amorce KO : %s" % str(w)[:200])
        return 2

    def rpc(method, body=None, timeout=60):
        return _unwrap(R._rpc(sid, method, [body] if body is not None else [], timeout=timeout))

    if not _inject(a.seed_bc):
        return 2
    rid = _build(a.state_file, a.seed, a.seed_bc, a.hero_witness)
    if rid is None:
        return 2
    print("[1210] runner %s (board %s seed %s)" % (rid, BOARD, a.seed))
    rc = 0
    try:
        if a.hero_witness:
            # PHASE DE SPAWN -- elle EXISTE pour rendre le mutant `Hero` MORDANT (cf. la note en
            # tete). Le summoner caste `MV71SniperDroneSquad` par la voie NATIVE ; la cible est
            # tiree d'`abilityTargets(...).fromHere`, donc du selecteur natif, jamais devinee.
            d = rpc("decisionView", {"runnerId": rid})
            s0 = rpc("combatSnapshot", {"runnerId": rid})
            smn = None
            for u in (s0 or {}).get("units") or []:
                if ((u.get("unitConfig") or {}).get("visualId")) == SUMMONER:
                    smn = int(u.get("entityId"))
            ab_id = None
            for u in (d or {}).get("units") or []:
                if smn is not None and int(u.get("id") or -1) == smn:
                    for ab in (u.get("abilities") or []):
                        if ab.get("kind") == "active" and ab.get("id") is not None:
                            ab_id = int(ab["id"])
            if ab_id is None:
                # `decisionView` ne publie les `abilities[]` que pour l'unite dont c'est le TOUR ;
                # le summoner n'est pas forcement celle-la. Constante de MONTAGE (pas de port) :
                # l'ability active de `tauMarksman` est `ActiveAbilityType.MV71SniperDroneSquadAttack`
                # (1076) -- le NOM du kit gameconfig est `MV71SniperDroneSquad`, l'enum du build
                # n'en porte que la forme `...Attack`, mesure sur
                # `data/symbols/rnca9r7q6c/frida/enums.tsv`.
                from engine.entities.active_ability_type import ActiveAbilityType
                ab_id = int(ActiveAbilityType.MV71SniperDroneSquadAttack)
                print("[1210] ability non publiee en dv -> repli sur l'enum : %s" % ab_id)
            print("[1210] summoner u%s ability=%s" % (smn, ab_id))
            if smn is None:
                print("[1210] KO -- summoner introuvable : le TEMOIN Hero manque")
                rc |= 1
            else:
                at = rpc("abilityTargets", {"runnerId": rid, "unitId": smn,
                                            "abilityId": ab_id}) or {}
                tgt = None
                for u in (at.get("units") or []):
                    for ab in (u.get("abilities") or []):
                        if int(ab.get("abilityId") or -1) != ab_id:
                            continue
                        for t in (ab.get("fromHere") or []):
                            if tgt is None:
                                tgt = t.get("targetId")
                if tgt is None:
                    # 1076 est `SummonAndAttackTarget` : sa cible est un ENNEMI. `fromHere` peut
                    # etre vide au tour 1 (portee), on retombe alors sur le 1er ennemi du board --
                    # c'est un choix de MONTAGE, et s'il est refuse le probe le DIT (il ne
                    # fabrique pas un temoin).
                    tgt = next((int(u.get("entityId")) for u in (s0 or {}).get("units") or []
                                if ((u.get("unitConfig") or {}).get("visualId"))
                                in FOES.split(",")), None)
                res = rpc("applyAction", {"runnerId": rid, "action": {
                    "kind": "ability", "casterId": smn, "targetId": tgt,
                    "abilityType": ab_id}}, 60)
                print("[1210] spawn cible=%s -> %s" % (tgt, str(res)[:220]))

        snap0 = rpc("combatSnapshot", {"runnerId": rid})
        dv0 = rpc("decisionView", {"runnerId": rid})
        ob = rpc("observeBattle", {"runnerId": rid})
        bg = rpc("boardGraph", {"runnerId": rid})
        before = _by_unit(snap0, dv0)
        ids = {r["vis"]: uid for uid, r in before.items()}
        caster = ids.get(CASTER_VIS)
        if caster is None:
            print("[1210] KO -- %s absent du snapshot (%s)" % (CASTER_VIS, sorted(ids)))
            return 2
        print("== AVANT CAST ==")
        for uid in sorted(before):
            _line("avant", uid, before[uid])

        # `isSelfCasting = 1` -> `TargetingQuery$$GetActualTarget` rend le CASTER quelle que soit
        # la cible passee ; on la passe explicitement pour ne rien deviner.
        res = rpc("applyAction", {"runnerId": rid, "action": {
            "kind": "ability", "casterId": caster, "targetId": caster,
            "abilityType": MONTKA}}, 60)
        a0 = (res.get("actions") or [{}])[0] if isinstance(res, dict) else {}
        if not (isinstance(res, dict) and res.get("ok") and a0.get("ok")):
            print("[1210] cast REFUSE : %s" % str(res)[:400])
            return 2

        snap = rpc("combatSnapshot", {"runnerId": rid})
        dv = rpc("decisionView", {"runnerId": rid})
        after = _by_unit(snap, dv)
        print("== APRES CAST ==")
        for uid in sorted(after):
            _line("apres", uid, after[uid])

        # --- BRAS 1 : SELECTEUR --------------------------------------------------------------
        buffed = sorted(uid for uid, r in after.items() if BUFF_NAME in r["effects"])
        print("[1210] LIVE  buffes = %s (%s)" % (buffed, [after[u]["vis"] for u in buffed]))
        if not buffed:
            print("[1210] ATTENTION -- AUCUN buffe : le bras selecteur ne prouve rien")
            rc |= 1
        melee_uid = ids.get(MELEE_ALLY)
        if melee_uid is None:
            print("[1210] ATTENTION -- %s absent : le TEMOIN du filtre ranged manque" % MELEE_ALLY)
            rc |= 1
        elif melee_uid in buffed:
            print("[1210] KO -- %s (Hero SANS arme distante) est BUFFE : le filtre "
                  "UnitsWithRangedWeapons ne mord pas cote NATIF ?" % MELEE_ALLY)
            rc |= 1
        else:
            print("[1210] TEMOIN OK -- %s (Hero, arme melee seule) n'est PAS buffe" % MELEE_ALLY)
        # TEMOIN DU FILTRE `Hero` : le drone est RANGED (Piercing R4) et NON-Hero.
        drone = ids.get(SUMMON_WITNESS)
        if a.hero_witness:
            if drone is None:
                print("[1210] KO -- %s absent apres le spawn : le TEMOIN Hero manque"
                      % SUMMON_WITNESS)
                rc |= 1
            elif drone in buffed:
                print("[1210] KO -- %s (RANGED mais NON-Hero) est BUFFE cote NATIF" % SUMMON_WITNESS)
                rc |= 1
            else:
                print("[1210] TEMOIN OK -- %s (RANGED, NON-Hero) n'est PAS buffe (%s)"
                      % (SUMMON_WITNESS, _HERO_WITNESS_NOTE))

        from engine.runner.snapshot import load_state
        from engine.runner.abilities.tau import (ExemplarOfTheMontkaAbility,
                                                 exemplar_of_the_montka_buff_targets)
        from engine.runner.abilities.behaviours.context import entities_from_state
        from engine.entities.pathfinding.board import Board
        state = load_state(dv, ob, snap, board=Board(bg["tiles"], adjacency="native_sym"))
        sel = exemplar_of_the_montka_buff_targets().evaluate(entities_from_state(state, int(caster)))
        port = sorted(int(u["id"]) for u in sel
                      if isinstance(u, dict) and u.get("id") is not None)
        print("[1210] PORT  cibles = %s" % port)
        same = (port == buffed)
        print("[1210] VERDICT selecteur : %s" % ("OK" if same else "DIVERGE"))
        rc |= 0 if same else 1

        # --- BRAS 2 : TRAIT natif ------------------------------------------------------------
        gained = sorted(uid for uid in before
                        if UNSTOPPABLE not in before[uid]["traits"]
                        and UNSTOPPABLE in after.get(uid, before[uid])["traits"])
        print("[1210] TRAIT 1042 gagne au cast (LIVE) : %s (%s)"
              % (gained, [after[u]["vis"] for u in gained]))
        if not gained:
            print("[1210] ATTENTION -- aucun temoin d'AJOUT : le bras trait ne prouve rien")
            rc |= 1

        # --- BRAS 3 : TRAIT cote PORT --------------------------------------------------------
        state0 = load_state(dv0, ob, snap0, board=Board(bg["tiles"], adjacency="native_sym"))
        from engine.runner.components import StatsComponent
        from engine.runner.operations.turnflow import EndTurnOperation
        from engine.entities.traits.unit_trait import entity_trait_names

        def _port_traits(st, uid):
            e = st.get_entity(int(uid))
            sc = e.get_component(StatsComponent) if e is not None else None
            return set(entity_trait_names(getattr(sc, "ctx", None), None))

        pre = {uid: _port_traits(state0, uid) for uid in sorted(before)}
        ExemplarOfTheMontkaAbility().execute_behaviour(state0, int(caster), int(caster))
        mid = {uid: _port_traits(state0, uid) for uid in sorted(before)}
        gained_port = sorted(uid for uid in pre if "Unstoppable" not in pre[uid]
                             and "Unstoppable" in mid[uid])
        print("[1210] PORT  trait Unstoppable gagne au cast : %s" % gained_port)
        ok_add = (gained_port == gained)
        print("[1210] VERDICT face PORT (ajout du trait) : %s"
              % ("OK" if ok_add else "DIVERGE (natif %s)" % gained))
        rc |= 0 if ok_add else 1
        # `turns = <DSLFormulas+0x20>` = 1 -> UN tick suffit.
        EndTurnOperation.execute(state0, advance=False)
        post = {uid: _port_traits(state0, uid) for uid in sorted(before)}
        ok_rev = all(pre[uid] == post[uid] for uid in pre)
        for uid in sorted(pre):
            if pre[uid] != post[uid]:
                print("[1210] PORT  trait NON RESTITUE u%s : %s -> %s"
                      % (uid, sorted(pre[uid] - post[uid]), sorted(post[uid] - pre[uid])))
        print("[1210] VERDICT face PORT (retrait du trait) : %s" % ("OK" if ok_rev else "KO"))
        rc |= 0 if ok_rev else 1

        # --- BRAS 4 : DEGAT, les DEUX branches du `If(HasTrait(Target, BigTarget))` -----------
        from engine.entities.effects.factory import EFFECT_CLASSES
        from engine.entities.effects.magnitude import ability_var
        eff_inst = None
        for u in (dv or {}).get("units") or []:
            if int(u.get("id") or -1) != int(caster):
                continue
            for e in (u.get("effects") or []):
                if e.get("name") == BUFF_NAME:
                    eff_inst = e
        lvl = None
        for u in (snap or {}).get("units") or []:
            if int(u.get("entityId") or -1) == int(caster):
                cfg = u.get("unitConfig") or {}
                lvl = cfg.get("activeAbilityLevel") or cfg.get("abilityLevel")
        print("[1210] effet live sur le caster = %s ; niveau actif du caster = %s"
              % (eff_inst, lvl))
        klass = EFFECT_CLASSES.get(BUFF_NAME)
        eff = klass(effect_type=BUFF, name=BUFF_NAME)
        eff.active_ability_level = lvl
        small = eff.create_effect_damage_bonus_for_attack(target_traits=frozenset())
        big = eff.create_effect_damage_bonus_for_attack(
            target_traits=frozenset({"BigTarget"}))
        kit_small = ability_var("ExemplarOfTheMontka", "extraDmg", lvl)
        kit_big = ability_var("ExemplarOfTheMontka", "extraDmg_2", lvl)
        print("[1210] PORT  bonus non-BigTarget = %s (kit extraDmg   = %s)"
              % (None if small is None else small.value, kit_small))
        print("[1210] PORT  bonus BigTarget     = %s (kit extraDmg_2 = %s)"
              % (None if big is None else big.value, kit_big))
        ok_dmg = (small is not None and big is not None and big.value > small.value)
        print("[1210] VERDICT branches du If : %s" % ("OK" if ok_dmg else "KO"))
        rc |= 0 if ok_dmg else 1
        # Le natif NE porte AUCUN gate de nature de coup : melee et distance doivent donner LE MEME
        # bonus. C'est l'ecart de fond avec 1222 (`IsMeleeAttack`).
        m = eff.create_effect_damage_bonus_for_attack(is_ranged=False, target_traits=frozenset())
        r_ = eff.create_effect_damage_bonus_for_attack(is_ranged=True, target_traits=frozenset())
        ok_nat = (m is not None and r_ is not None and m.value == r_.value)
        print("[1210] VERDICT absence de gate melee/distance : %s (melee=%s distance=%s)"
              % ("OK" if ok_nat else "KO",
                 None if m is None else m.value, None if r_ is None else r_.value))
        rc |= 0 if ok_nat else 1
    finally:
        if not a.keep:
            rpc("disposeRunner", {"runnerId": rid}, 30)
    print("[1210] rc=%d" % rc)
    return rc


if __name__ == "__main__":
    raise SystemExit(main())
