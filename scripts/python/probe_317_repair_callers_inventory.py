#!/usr/bin/env python
"""Probe #317 -- INVENTAIRE ventile des 13 appelants natifs de `IdunBattleLogic.Entities.DSLBehaviors$$Repair`.

POURQUOI. #310 a rebranche `LivingMetalRepair` du soin vers la reparation et rendu le compte
« 13 appelants, 4 portes ». Le compte seul ne dit pas QUOI porter : il faut, pour chacun,
(a) l'ARTEFACT reellement construit -- surtout pas le NOM (`DawnBlade_HealAbility` construit un
`Repair`, c'est exactement le piege qui a fait survivre le bug #310), (b) les OPTIONS
(`RepairBehaviourOptions`, dont le champ `scope` arme le cap de GROUPE de `PredictRepair`), et
(c) la CONFRONTABILITE de ses porteurs (hero/MoW/summon = confrontable ; tous-npc = NON PERTINENT).

Ce probe fait les deux moities :

  * la table `CALLSITES` est la RE, transcrite du decompile (build `rnca9r7q6c`). Elle n'est pas
    derivable du checkout : les xrefs et les corps vivent dans ghidra. Commande de re-derivation
    en pied de docstring ;
  * la ventilation des PORTEURS, elle, est DERIVEE du gameconfig a chaque execution -- y compris
    la voie RELIQUE (`items[*].abilityId` + `allowedUnits`), que `unit_map.py find --ability`
    ne voit pas (il ne lit que `activeAbilities` + `passiveAbilities`, d'ou son « 0 unite » sur
    `DawnBlade`, qui est une `relicAbilities`).

CORRECTIONS que ce probe apporte a la fiche #310 (mesurees, pas heritees) :

  * `LivingMetal` n'est PAS le seul call-site `ForRegenerate` du build :
    `IdunBattle.Entities.Effects.Loki.LifeStealEffect$$CreateTargetTriggerBehaviour` en est un
    second ;
  * il existe une TROISIEME forme d'options -- deux appelants n'appellent AUCUNE fabrique et
    ecrivent les champs a la main apres `RepairBehaviourOptions$$.ctor`
    (`EnhancementRegenerationAbility` -> `scope = 1`, `PowerUp_HealingAbility` -> `scope = 0`).
    Donc **3** call-sites arment `scope == 1` (le cap de GROUPE), pas 1.

RE-DERIVATION (ghidra-mcp) :

    mcp__ghidra__list_xrefs("GameAssembly.dll", "IdunBattleLogic.Entities.DSLBehaviors$$Repair")
    mcp__ghidra__decompile_function("GameAssembly.dll", "<chaque symbole de CALLSITES>")
    mcp__ghidra__decompile_function("GameAssembly.dll",
        ["IdunBattle.Entities.Behaviours.RepairBehaviourOptions$$ForRepair",
         "IdunBattle.Entities.Behaviours.RepairBehaviourOptions$$ForRegenerate"])

ASCII only (cp1252). Usage: python probe_317_repair_callers_inventory.py
"""
from __future__ import annotations

import json
import sys

import gameconfig as GC

# ---------------------------------------------------------------------------------------------
# Les DEUX fabriques statiques d'options, relues verbatim sur `rnca9r7q6c` :
#   `$$ForRepair`     ecrit `+0x14 = 1` (removeEffects), `+0x18 = 3`, puis `+0x10 = 0` (scope),
#                     puis re-ecrit `+0x14 = 1`   -> (scope 0, removeEffects 1)
#   `$$ForRegenerate` idem jusqu'a `+0x18 = 3`, puis `+0x10 = 1`, puis `+0x14 = 0`
#                                                 -> (scope 1, removeEffects 0)
# `scope == 1` est CE QUI ARME l'etage cap-de-GROUPE de `DamagePrediction$$PredictRepair`.
# ---------------------------------------------------------------------------------------------
FOR_REPAIR = "ForRepair (scope 0, removeEffects 1)"
FOR_REGEN = "ForRegenerate (scope 1, removeEffects 0)"

REPAIR = "REPAIR"          # l'artefact construit est un `DSLBehaviors$$Repair`
FORK = "REPAIR+HEAL"       # l'arbre porte les DEUX feuilles sous un `If(...)`

# (symbole, artefact, options, id enum QUALIFIE, ability gameconfig, porte cote COMBAT, note)
CALLSITES: list[tuple[str, str, str, str, str | None, bool, str]] = [
    ("IdunBattleLogic.Entities.Abilities.Active.RepairAbility$$CreateBehaviour",
     REPAIR, FOR_REPAIR, "ActiveAbilityType 28 Repair / 1119 Repair_GalvanicField", None, True,
     "Repair(Caster@0x48, sel@0x60, <vtable +0x4b8 amount>, AbilityOrEffect, ForRepair) -- porte #299 ; "
     "28 est accordee par le TRAIT `Mechanic` (aucune entree `units.abilities`), 1119 par le passif "
     "`GalvanicField`"),
    ("IdunBattleLogic.Entities.Abilities.Active.Loki.FabricatorClawArrayAbility$$CreateBehaviour",
     REPAIR, FOR_REPAIR, "ActiveAbilityType 1006 FabricatorClawArray", "FabricatorClawArray", True,
     "Repair(Owner@0x30, GetTargetSelector(), Direct(GetVariableForLevel(0x24)), .., ForRepair) -- porte #303"),
    ("IdunBattleLogic.Entities.Abilities.Active.Loki.InspiredToGreatnessAbility$$RepairOrHeal",
     FORK, FOR_REPAIR, "ActiveAbilityType 1082 InspiredToGreatness", "InspiredToGreatness", True,
     "If(IsRepairable(sel), Repair(Caster@0x48, sel, Direct(toHeal), .., ForRepair), "
     "Heal(.., ForHeal)) -- les DEUX branches portees"),
    ("IdunBattleLogic.Entities.Abilities.Active.Loki.LivingMetalRepairAbility$$CreateBehaviour",
     REPAIR, FOR_REGEN, "TriggeredAbilityType 1010 LivingMetalRepair", None, True,
     "Repair(Owner@0x30, Owner@0x30, PercentageOf(StatAmount(Owner, Health, Maximum), "
     "Direct(GetNumberConstant(0x12))), .., ForRegenerate) -- REBRANCHE par #310 ; accorde par le "
     "trait LivingMetal, pas par une entree d'ability"),
    ("IdunBattleLogic.Entities.Abilities.Active.Loki.ReanimationBeamAbility$$ExecuteBehaviour",
     REPAIR, FOR_REPAIR, "ActiveAbilityType 1223 ReanimationBeam", "ReanimationBeam", False,
     "Repair(Caster@0x48, Repairable(EntitiesWithAnyEffect(MechanicalUnits(Friends(Owner)), 0x609)), "
     "ConfigVar(0x24), .., ForRepair) + GetSummonsTakeActionBehaviour + AddEffect(0x60b) -- "
     "seul le volet REVIVE est porte (triggers/loki/reanimation_beam.py)"),
    ("IdunBattleLogic.Entities.Abilities.Active.Loki.ReanimationBeamAbility$$GetRepairBehaviour",
     REPAIR, FOR_REPAIR, "ActiveAbilityType 1223 ReanimationBeam", "ReanimationBeam", False,
     "meme feuille, extraite : Repair(Caster@0x48, Repairable(allFriendlyUnitsWithNrp), "
     "ConfigVar(0x24), .., ForRepair)"),
    ("IdunBattleLogic.Entities.Abilities.Active.Loki.RelentlessMarchAbility$$CreateBehaviour",
     REPAIR, FOR_REPAIR, "TriggeredAbilityType 1004 RelentlessMarch "
     "(HOMONYME d'id avec ActiveAbilityType 1004 MortisRound)", "RelentlessMarch", False,
     "AddEffect(0x3f3) + Repair(Owner@0x30, UnitsWithoutTrait(Friends(AdjacentUnits(Owner)), 0x418) "
     "[- HeroUnits si triggerType == 0x20], Direct(GetVariableForLevel(0x24)), .., ForRepair)"),
    ("IdunBattleLogic.Entities.Abilities.Active.Loki.DefendTheDivineWorkAbility$$ExecuteBehaviour",
     REPAIR, FOR_REPAIR, "ActiveAbilityType 1117 DefendTheDivineWork", "DefendTheDivineWork", False,
     "Repair(Caster@0x48, Friends(Caster, AdjacentUnits(@0x50)) + Caster, "
     "Get(GetVariableForLevel(0x24)), .., ForRepair) puis ExecuteAtomic(0x2a) + "
     "Repair_GalvanicFieldAbility$$CreateAttackBehavior -- face DECISION portee (playbook), COMBAT non"),
    ("IdunBattleLogic.Entities.Abilities.Triggered.Loki.DawnBlade_HealAbility$$CreateBehaviour",
     REPAIR, FOR_REPAIR, "TriggeredAbilityType 1501 DawnBlade "
     "(l'EffectType 1501 est DawnBlade_ExtraDmg -- homonyme d'id, autre enum)", "DawnBlade", True,
     "LE NOM DIT HEAL, L'ARTEFACT EST UN REPAIR : Repair(Owner@0x30, Owner@0x30, "
     "Get(GetVariableForLevel(0x20 hpToHeal)), AbilityOrEffect, ForRepair) ; trigger = "
     "On(UnitDeath=0) & OwnerIsActor & IsDefeatedByMeleeAttack(sel@0x60) -- PORTE par #317 "
     "(triggers/loki/dawn_blade.py, registre RELIC_ABILITY_TRIGGERS)"),
    ("IdunBattleLogic.Entities.Abilities.Triggered.Loki.EnhancementRegenerationAbility$$CreateBehaviour",
     FORK, "ctor ad-hoc : +0x10 = 1 (scope), +0x14 = 0 (removeEffects), +0x15 = 1, +0x18 = 1",
     "TriggeredAbilityType 1433 EnhancementRegeneration", "EnhancementRegeneration", False,
     "Foreach(UnitsWithTrait(UnitsFromTeam(..), 0x10), If(Repairable(sel@0x68), Repair(Player(1), "
     "sel@0x68, .., <options ad-hoc>), Heal(Player(1), sel@0x68, .., <HealBehaviourOptions ad-hoc>))) "
     "-- 2e call-site scope == 1"),
    ("IdunBattleLogic.Entities.Abilities.Triggered.Loki.PowerUp_HealingAbility$$AdditionalBehavior",
     FORK, "ctor ad-hoc : +0x10 = 0 (scope), +0x14 = 1 (removeEffects), +0x16 = 1",
     "TriggeredAbilityType 1273 PowerUp_Healing", "PowerUp_Healing", False,
     "If(IsMechanical(target), Repair(Owner@0x30, target, PercentageOf(StatAmount(target, Health, "
     "Maximum), Get(GetNumberConstant(0x13))), .., <options ad-hoc>), Heal(...))"),
    ("IdunBattleLogic.Entities.Abilities.Triggered.Loki.SelfRepairMechanismAbility$$CreateBehaviour",
     REPAIR, FOR_REPAIR, "TriggeredAbilityType 1291 SelfRepairMechanism "
     "(1474 SelfRepairMechanismReworked est une AUTRE entree)", "SelfRepairMechanism", False,
     "Repair(Owner@0x30, Owner@0x30, Multiply(EffectLevel(EffectFromOwner(Owner, 0x555)), "
     "Direct(GetVariableForLevel(0x24))), .., ForRepair)"),
    ("IdunBattle.Entities.Effects.Loki.LifeStealEffect$$CreateTargetTriggerBehaviour",
     FORK, FOR_REGEN, "EffectType (pose par TriggeredAbilityType 1309 EnhancementLifeSteal)",
     "EnhancementLifeSteal", False,
     "If(AmountIsGreaterThanZero(dmg), If(IsRepairable(Owner@0x30), Repair(Owner, Owner, "
     "Multiply(PercentageOf(@0x50, Get(GetNumberConstant(0x12))), EffectLevel), .., ForRegenerate), "
     "Heal(.., HealBehaviourOptions$$ForRegenerate)) & Inform(0xb3)) -- 3e call-site scope == 1 ; "
     "le lifesteal PORTE est SpiritLeech, une ability DISTINCTE qui construit bien un $$Heal"),
]


def _units_by_ability() -> dict:
    """Index `abilityId -> [(kind, unitId, voie)]`, DERIVE du gameconfig.

    Trois voies, et la troisieme est celle qui manquait : `activeAbilities`, `passiveAbilities`,
    `relicAbilities` -- plus les ITEMS reliques (`items[*].abilityId` + `allowedUnits`), qui
    accordent une ability a un HERO sans qu'elle apparaisse dans sa fiche d'unite."""
    doc = json.loads(GC._find_gameconfig().read_text(encoding="utf-8"))
    cg = doc["clientGameConfig"]
    idx: dict[str, list[tuple[str, str, str]]] = {}
    for kind in ("lineup", "npc", "summons"):
        coll = cg["units"].get(kind) or {}
        items = coll.items() if isinstance(coll, dict) else [(u.get("id"), u) for u in coll]
        for uid, u in items:
            for field in ("activeAbilities", "passiveAbilities", "relicAbilities"):
                for aid in (u.get(field) or []):
                    idx.setdefault(aid, []).append((kind, uid, field))
    for iid, it in (cg.get("items") or {}).items():
        aid = it.get("abilityId")
        if not aid:
            continue
        for uid in (it.get("allowedUnits") or []):
            u = GC.unit(uid) or {}
            idx.setdefault(aid, []).append((u.get("kind") or "?", uid, "item:" + iid))
    return idx


def _pool() -> set | None:
    """Le pool spawnable (hero + MoW) du seed BC courant = `rl_duel.py build --list-pool`.

    TRI-ETAT, deliberement (meme discipline que `host_inputs.py`) : `None` = PAS MESURE (la
    session live n'a pas repondu -- `_normalize_and_extract_pool` passe par un RPC
    `buildNormalizedBC`), `set()` = mesure et vide. Rendre un ensemble vide sur echec ferait lire
    « aucun porteur confrontable » la ou on n'a simplement rien mesure.

    Rappel de doctrine : ABSENT DU POOL != NON CONFRONTABLE (un hero hors pool s'injecte, cf.
    `docs/rl/case-92-catalog-injection.md` par. 6) ; un SUMMON compte meme hors pool (on l'amene
    en spawnant son summoner)."""
    import re
    import subprocess
    from pathlib import Path
    try:
        r = subprocess.run([sys.executable, str(Path(__file__).with_name("rl_duel.py")),
                            "build", "--list-pool"], capture_output=True, text=True, timeout=180)
    except Exception:
        return None
    if r.returncode != 0:
        return None
    out: set = set()
    for line in (r.stdout or "").splitlines():
        s = line.strip()
        if s and " " not in s and s[0].islower():
            out.add(s)
        m = re.search(r"MoW spawnables : \[(.*)\]", s)
        if m:
            out |= {x.strip().strip("'\"") for x in m.group(1).split(",") if x.strip()}
    return out or None


def main() -> int:
    idx = _units_by_ability()
    pool = _pool()
    n_ported = sum(1 for c in CALLSITES if c[5])
    print("[317] %d appelants natifs de DSLBehaviors$$Repair, %d portes cote COMBAT"
          % (len(CALLSITES), n_ported))
    scope1 = [c[0] for c in CALLSITES if "scope 1" in c[2] or "+0x10 = 1" in c[2]]
    print("[317] call-sites armant scope == 1 (cap de GROUPE de PredictRepair) : %d" % len(scope1))
    for s in scope1:
        print("        %s" % s)
    print("")
    for sym, art, opts, enum_id, aid, ported, note in CALLSITES:
        print("[%s] %s" % ("PORTE " if ported else "ouvert", sym))
        print("        artefact=%s  options=%s" % (art, opts))
        print("        enum=%s" % enum_id)
        carriers = idx.get(aid or "", [])
        kinds: dict[str, list[str]] = {}
        for kind, uid, voie in carriers:
            kinds.setdefault(kind, []).append("%s(%s)" % (uid, voie))
        if aid is None:
            print("        porteurs: <accorde par un TRAIT, pas par une entree d'ability>")
        elif not carriers:
            print("        porteurs: AUCUN (ability %s absente de toute unite du gameconfig)" % aid)
        else:
            for kind in sorted(kinds):
                print("        porteurs[%s]: %s" % (kind, ", ".join(sorted(kinds[kind]))))
            non_npc = sorted({uid for kind, uid, _ in carriers if kind != "npc"})
            if pool is None:
                pool_txt = "<non mesure : la session live n'a pas rendu --list-pool>"
            else:
                pool_txt = str(sorted({uid for kind, uid, _ in carriers if uid in pool}) or "-")
            print("        confrontable: pool=%s | non-npc=%s"
                  % (pool_txt, non_npc or "AUCUN -> NON PERTINENT"))
        print("        %s" % note)

    # --- volet RELIQUES : la voie que `unit_map.py find --ability` ne voit pas ------------------
    # `unit_map` ne lit que `activeAbilities` + `passiveAbilities` -> il rend « 0 unite » pour toute
    # ability de RELIQUE. C'est ce faux negatif qui a fait classer `NetherRealmCasket` en DEAD dans
    # la fiche #310. Le seed BC, lui, porte la relique EQUIPEE dans `Units[].TertiaryAbility`.
    from pathlib import Path
    seed_p = Path(__file__).resolve().parents[2] / "data" / "seed-bc.json"
    print("\n[317] volet RELIQUES -- `Units[].TertiaryAbility` du seed BC (l'ability de la relique "
          "EQUIPEE) :")
    if not seed_p.exists():
        print("        <data/seed-bc.json absent : non mesure>")
    else:
        seed = json.loads(seed_p.read_text(encoding="utf-8"))
        rows = [(u.get("Id"), u.get("TertiaryAbility")) for u in (seed.get("Units") or [])
                if u.get("TertiaryAbility")]
        print("        %d unite(s) sur %d : %s"
              % (len(rows), len(seed.get("Units") or []), rows))
    doc = json.loads(GC._find_gameconfig().read_text(encoding="utf-8"))
    relics = {iid: it for iid, it in (doc["clientGameConfig"].get("items") or {}).items()
              if it.get("isRelic") and it.get("abilityId")}
    print("        items reliques du gameconfig : %d" % len(relics))
    for iid, it in sorted(relics.items()):
        print("          %-36s -> %-24s allowedUnits=%s"
              % (iid, it.get("abilityId"), it.get("allowedUnits")))
    return 0


if __name__ == "__main__":
    sys.exit(main())
