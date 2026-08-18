"""#494-r2 -- D'OU vient `isMelee` dans la prediction d'attaque, et le port lit-il la meme source ?

Le natif `IdunBattle.Core.Services.DamagePrediction$$PredictAttackRaw` fait, LU au decompile :

    isMelee  = DamagePrediction.IsMeleeAttack(ability, attacker, attackerPos, defender);
    extraMax = isMelee ? 0 : UnitExtensions.GetStat(attacker, 0x19);   // StatType.ExtraMaxDamage
    ...      = GetBaseDamageFix64(damage, isMaxOut, ..., extraMax)

et `IdunBattle.Core.Services.DamagePrediction$$IsMeleeAttack` delegue au slot 2 d'`IBattleQuery` =
`IdunBattle.Core.Services.BattleQuery$$IsMeleeAttack`, qui branche sur
`IdunBattle.Core.Services.BattleQuery$$GetAbilityAttackRangeType(ability)` :
`None(0)`/`Ranged(2)` -> false SANS condition de distance, `Melee(1)` -> true SANS condition,
`Normal(3)` -> `!HasFlag(caster, UnitFlag.ForceRangedAttack) && AreEntitiesAdjacent(...)`.

Le port, lui, decide `isMelee` par l'ARME choisie
(`engine/runner/operations/damage_utility.py::normal_attack_is_melee` ->
`services/battle_query.select_weapon_pierce` -> `not is_ranged`), et son homologue COMBAT
(`runner/operations/damage_ops/normal.py`) fait pareil (`_ranged`).

Ce probe repond par LECTURE (gameconfig + mirror des tables natives) :

  1. distribution d'`attackRangeType` sur toutes les abilities du gameconfig ;
  2. les ids d'ATTAQUE NORMALE (generiques + les 16 concretes des tables de substitution
     `custom_normal_attack.py`) ont-ils une entree gameconfig, et quel `attackRangeType` ?
     -> c'est ce qui decide QUELLE branche du switch le natif prend pour une attaque normale ;
  3. combien d'unites sont MELEE-ONLY / RANGED-ONLY -- le regime ou le repli du port
     (aucune arme eligible -> `select_weapon_pierce` rend `is_ranged=False`, donc `isMelee=True`)
     s'ecarte du natif, qui rend `false` sur `Normal(3)` non adjacent.

ASCII only (cp1252).
"""
from __future__ import annotations

import pathlib
import sys
from collections import Counter

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

import gameconfig as GC  # noqa: E402
from engine.services.custom_normal_attack import (  # noqa: E402
    CUSTOM_NORMAL_ATTACK_BY_ACTIVE, CUSTOM_NORMAL_ATTACK_BY_PASSIVE, NORMAL_BOSS_ATTACK)

#: Les deux generiques (`ActiveAbilityType` 17 `NormalAttack`, 69 `Loki_NormalAttack`) + la boss.
GENERIQUES = ["NormalAttack", "Loki_NormalAttack", NORMAL_BOSS_ATTACK]


def main() -> int:
    abilities = GC._index()["abilities"]
    print("ETAGE 1 -- distribution attackRangeType sur %d abilities du gameconfig" % len(abilities))
    dist = Counter((a or {}).get("attackRangeType") for a in abilities.values())
    total = 0
    for k, n in sorted(dist.items(), key=lambda kv: (-kv[1], str(kv[0]))):
        print("  %-10s : %d" % (k if k is not None else "(absent)", n))
        total += n
    print("  TOTAL      : %d" % total)

    print()
    print("ETAGE 2 -- les ATTAQUES NORMALES ont-elles une entree, et quel attackRangeType ?")
    noms = list(GENERIQUES)
    noms += sorted(CUSTOM_NORMAL_ATTACK_BY_PASSIVE.values())
    noms += sorted(CUSTOM_NORMAL_ATTACK_BY_ACTIVE.values())
    vus, art = set(), Counter()
    for nom in noms:
        if nom in vus:
            continue
        vus.add(nom)
        a = GC.ability(nom)
        rt = (a or {}).get("attackRangeType")
        art[rt if a is not None else "(PAS D'ENTREE)"] += 1
        print("  %-34s entree=%-5s attackRangeType=%s"
              % (nom, a is not None, rt if rt is not None else "(absent)"))
    print("  --- resume : %s" % dict(art))

    print()
    print("ETAGE 3 -- unites MELEE-ONLY / RANGED-ONLY (regime de repli du port)")

    def _is_melee(w):
        r = (w or {}).get("Range")
        return r is None or int(r) < 2

    ids = GC.all_unit_ids()
    melee_only = ranged_only = mixte = sans_arme = 0
    ex_ro, ex_mo = [], []
    for kind in ("lineup", "npc", "summons"):
        for uid in ids[kind]:
            gu = GC.unit(uid) or {}
            ws = gu.get("weapons") or []
            if not ws:
                sans_arme += 1
                continue
            m = any(_is_melee(w) for w in ws)
            r = any(not _is_melee(w) for w in ws)
            if m and r:
                mixte += 1
            elif m:
                melee_only += 1
                if len(ex_mo) < 6 and kind == "lineup":
                    ex_mo.append(uid)
            else:
                ranged_only += 1
                if len(ex_ro) < 6 and kind == "lineup":
                    ex_ro.append(uid)
    print("  melee-only : %d  (ex. lineup %s)" % (melee_only, ", ".join(ex_mo)))
    print("  ranged-only: %d  (ex. lineup %s)" % (ranged_only, ", ".join(ex_ro)))
    print("  mixte      : %d" % mixte)
    print("  sans arme  : %d" % sans_arme)

    print()
    print("ETAGE 4 -- porteurs de StatType.ExtraMaxDamage (25) : qui rend l'ecart OBSERVABLE ?")
    porteurs = []
    for name, a in sorted(abilities.items()):
        blob = repr(a)
        if "ExtraMaxDamage" in blob:
            porteurs.append(name)
    print("  abilities citant ExtraMaxDamage : %d -> %s" % (len(porteurs), ", ".join(porteurs[:12])))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
