"""case-366-r1-camo-seed -- INVENTAIRE du gisement << effet condition-gated absent de la capture >>.

LA QUESTION, exactement. Un effet dont la `CreateActiveCondition` est FAUSSE au moment de la
capture est DROPPE par le canal `decisionView` PAR DEFAUT (`readEffectsByUnit` filtre
`EffectComponent.IsActive`). Un etat charge depuis ce canal n'a donc AUCUNE instance -- et si la
simulation fait ensuite entrer l'effet dans sa condition, le port n'a RIEN a rallumer, alors que le
natif, lui, n'a jamais cesse de porter l'entite-effet.

⚠ LA DISTINCTION QUI FONDE TOUT : **INERTE n'est pas ABSENT**. Le natif POSE l'instance et la laisse
inerte ; c'est le CAPTEUR qui la cache. Mesure directe (`probe_366_r1_camo_seed.py`) : hors couvert,
canal DEFAUT = pas de `1014`, canal `includeInactive` = `1014` avec `active: false`.

DEUX CONJOINTS decident si une classe est EXPOSEE, et il faut les DEUX :

  (A) POSE -- le natif materialise-t-il l'instance meme quand la condition est fausse ? C'est le
      `<X>Ability$$CreateBehaviour` qui tranche, PAS le comportement observe : un `AddEffect(...)`
      NU (sans `If(...)`) sur le trigger d'INIT pose inconditionnellement. Si la pose est un
      vecteur RUNTIME (attaque, cast), l'absence a la capture est FIDELE : le natif n'a pas
      d'instance non plus.
  (B) BASCULE -- la condition peut-elle passer de FAUSSE a VRAIE pendant la simulation ? Une
      condition sur un TRAIT ne bascule jamais ; une condition sur la position, les PV, le tour ou
      un effet voisin, si.

TROIS COMPENSATIONS existent cote port, et elles sont MECANIQUEMENT lisibles :
  * `factory.ABILITY_INIT_OWNER_EFFECTS` (+ `ABILITY_OWNER_EFFECTS`) -> `spawn._seed_ability_owner_
    effects`, appele par `runner/snapshot.py::load_state` : materialise l'instance quel que soit le
    canal ;
  * le canal `includeInactive` lui-meme (`snapshot.decision_view_seed_body`), quand le SITE DE
    CAPTURE le demande ;
  * `BaseEffect.active_condition_ported` + `seed_witness_effect` -> pendant DECISION
    (`playbook/scene.py::_seed_condition_gated_owner_effects`).

Ce probe RE-DERIVE la partie mecanique depuis le code (jamais un compte recopie) et la croise avec
le verdict de RE (table `POSE_VECTOR`, un symbole natif par entree). Il **ECHOUE** (rc 1) si une
classe surchargeant `is_active` n'a pas son verdict de pose : c'est le CLIQUET -- toute classe qui
entre au registre doit avoir ete lue au decompile sur cet axe.

Usage :
    python probe_366_camo_seed_inventory.py            # table + comptes + cliquet
    python probe_366_camo_seed_inventory.py --csv      # une ligne par classe

ASCII only (cp1252). Aucun RPC : 100 % offline.
"""
from __future__ import annotations

import argparse
import sys

#: Ce qui doit changer pour que ce cliquet puisse changer d'avis.
DECLENCHEUR = {
    "chemins": ("scripts/python/probe_366_camo_seed_inventory.py",
                "scripts/python/engine/*.py", "scripts/python/engine/**/*.py",
                "scripts/python/*.py"),
    "build": False,
    "toujours": False,
    "raison": (
        "Le verdict est `EFFECT_CLASSES` moins celles dont `is_active` est encore celui de "
        "`BaseEffect` : il depend donc du registre (`engine/entities/effects/factory.py`), de la "
        "BASE, de toute classe qui surcharge `is_active` OU QUI CESSE DE LE FAIRE, et des deux "
        "tables de seed (ABILITY_INIT_OWNER_EFFECTS / ABILITY_OWNER_EFFECTS) ; la table de RE "
        "(POSE_VECTOR) vit dans son propre source. Le glob n'est PAS borne a "
        "`engine/entities/effects/**` : une classe inscrite peut vivre ailleurs, et la fermeture "
        "d'imports MESUREE de `scan()` est de 99 modules engine/ plus `gameconfig.py` et "
        "`hexgeo.py` a la racine. Rien du build : le critere est une identite de fonction Python."),
}

# --------------------------------------------------------------------------------------------
# VERDICT DE RE, par classe d'effet qui surcharge `is_active`. Chaque entree est LUE au
# decompile du `<X>Ability$$CreateBehaviour` (build rnca9r7q6c) -- jamais deduite du nom ni du
# comportement observe.
#
#   pose  : "init"    = `AddEffect`/`AddStaticStatModifierEffectToOwner`/... NU sur le trigger
#                       d'init de l'ability -> l'instance existe TOUJOURS cote natif ;
#           "runtime" = pose par un vecteur d'execution (attaque, cast) -> l'absence a la
#                       capture est FIDELE.
#   flip  : "sim"     = la condition peut passer de FAUSSE a VRAIE pendant la simulation ;
#           "static"  = elle ne bascule pas (trait) ;
#           "one-way" = elle ne bascule que de VRAIE a FAUSSE dans les regimes atteignables.
# --------------------------------------------------------------------------------------------
POSE_VECTOR: dict[str, tuple[str, str, str, str]] = {
    # effet                                   pose       flip       symbole natif de la POSE / condition
    # #589-r1-r1-r2-r1 -- `AmuletOfTheVoidwyrmAbility` derive d'`AOwnerEffectTriggeredAbility`
    # (`classes.tsv`) et n'en surcharge QUE `GetEffectType` (-> 0x5b4). Le corps de BASE est
    # `If(<CreateCondition>, AddEffect(0x5b4, AbilityState(Owner, <cette ability>), source = Owner,
    # targets = Owner, turns = <zeroe>))` sur `CreateTrigger = OnOwnerSpecificAbilityInit` ; la
    # `CreateCondition` de base rend `<DSLTriggers+0x70>`, une instance de la MEME classe que
    # `<+0x40>` (dont `<+0x48>` est le `op_LogicalNot`), donc la pose est INCONDITIONNELLE.
    # MEME vecteur exact qu'`HammerOfWrath_ConditionalDamage` et `MartialSuperiority_Visual`.
    "AmuletOfTheVoidwyrm_CritDamageReduction": (
        "init", "sim",
        "IdunBattle.Entities.Abilities.AOwnerEffectTriggeredAbility$$CreateBehaviour"
        " (AmuletOfTheVoidwyrmAbility)",
        "AmountIsGreaterThanZero(summons/decoys allies ADJACENTS -- geometrique)"),
    "AnvilShield_BlockChanceBelowHealthCap": (
        "init", "sim",
        "IdunBattleLogic.Entities.Abilities.Triggered.Loki.AnvilShieldAbility_"
        "ApplyAdditionalBlockAndBlockChance$$CreateBehaviour",
        "HealthPct <= healthCap"),
    "CamoCloak_DmgReduction": (
        "init", "sim",
        "IdunBattleLogic.Entities.Abilities.Active.Loki.CamoCloakAbility$$CreateBehaviour",
        "HasEffect(Owner, 1013) | IsEffectTarget(Owner, 1026)"),
    "ContagionsOfNurgle_ArmorReduction1": (
        "init", "sim",
        "IdunBattleLogic.Entities.Abilities.Active.Loki."
        "ContagionsOfNurgle_AddEffectInitially_Ability$$CreateBehaviour",
        "ContagionsOfNurgleAmount dans [min, max] (aura, geometrique)"),
    "ContagionsOfNurgle_ArmorReduction2": (
        "init", "sim",
        "IdunBattleLogic.Entities.Abilities.Active.Loki."
        "ContagionsOfNurgle_AddEffectInitially_Ability$$CreateBehaviour",
        "ContagionsOfNurgleAmount dans [min, max] (aura, geometrique)"),
    "DestroyTheWitch_ExtraDamage": (
        "init", "sim",
        "IdunBattleLogic.Entities.Abilities.Triggered.Loki.DestroyTheWitchAbility$$CreateBehaviour",
        "un Psyker ENNEMI est vivant"),
    "DestroyTheWitch_ExtraMove": (
        "init", "sim",
        "IdunBattleLogic.Entities.Abilities.Triggered.Loki.DestroyTheWitchAbility$$CreateBehaviour",
        "un Psyker ENNEMI est vivant"),
    "HammerOfWrath_ConditionalDamage": (
        "init", "sim",
        "IdunBattle.Entities.Abilities.AOwnerEffectTriggeredAbility$$CreateBehaviour",
        "HealthPct <= healthPct"),
    "InescapableAccuracy_extraCritChance": (
        "init", "sim",
        "IdunBattleLogic.Entities.Abilities.Triggered.Loki."
        "InescapableAccuracyAbility$$CreateBehaviour",
        "NOT HasFlag(Owner, Moved)"),
    "InescapableAccuracy_extraCritDmg": (
        "init", "sim",
        "IdunBattleLogic.Entities.Abilities.Triggered.Loki."
        "InescapableAccuracyAbility$$CreateBehaviour",
        "NOT HasFlag(Owner, Moved)"),
    "InescapableAccuracy_overrideHits": (
        "init", "sim",
        "IdunBattleLogic.Entities.Abilities.Triggered.Loki."
        "InescapableAccuracyAbility$$CreateBehaviour",
        "NOT HasFlag(Owner, Moved)"),
    "MartialSuperiority_Visual": (
        "init", "sim",
        "IdunBattle.Entities.Abilities.AOwnerEffectTriggeredAbility$$CreateBehaviour"
        " (MartialSuperiorityAddEffectAbility)",
        "NOT IsTurnOf(Owner)"),
    "ModifiedExoarmour_ExtraDmg": (
        "init", "sim",
        "IdunBattleLogic.Entities.Abilities.Triggered.Loki.ModifiedExoarmourAbility$$CreateBehaviour",
        "AmountIsGreaterThanZero(TilesMovedThisTurn(Self))"),
    "Pinned": (
        "runtime", "static",
        "pose par le vecteur d'ATTAQUE (Suppression), pas par un init d'ability",
        "NOT HasTrait(Self, TerminatorArmour) -- un trait ne bascule pas"),
    "PowerTrip_FullHealth": (
        "init", "sim",
        "IdunBattleLogic.Entities.Abilities.Triggered.Loki.PowerTrip_InitAbility$$CreateBehaviour",
        "PV courants == PV max"),
    "PsychicStalk_VisualEffect": (
        "init", "one-way",
        "IdunBattleLogic.Entities.Abilities.Triggered.Loki."
        "PsychicStalk_ExtraAttackDamageAbility$$CreateBehaviour",
        "NOT IsDead(Owner) -- VRAIE pour tout porteur vivant, ne se rouvre pas"),
    "ReinforcedHiveNode_ExtraArmor": (
        "init", "sim",
        "IdunBattleLogic.Entities.Abilities.Triggered.Loki."
        "ReinforcedHiveNodeAbility$$CreateBehaviour",
        "AmountIsOdd(Sum(RoundsStarted(Owner), 1))"),
    # Le MEME `CreateBehaviour` pose les DEUX d'un bloc (`op_BitwiseAnd`) :
    # `AddStaticStatModifierEffectToOwner(0x454 = 1108, stat 0x10 FixedArmor, PercentageOf(...))`
    # ET `AddStatOverrideEffectToOwner(0x455 = 1109, stat 7 BlockChance, Direct(ConfigConst 0x2d))`
    # -- aucun `If`, donc pose INCONDITIONNELLE pour les deux. Condition FONDUE avec celle de 1108.
    "ReinforcedHiveNode_ExtraBlock": (
        "init", "sim",
        "IdunBattleLogic.Entities.Abilities.Triggered.Loki."
        "ReinforcedHiveNodeAbility$$CreateBehaviour",
        "AmountIsOdd(Sum(RoundsStarted(Owner), 1)) -- corps FONDU avec celui de 1108"),
    "StructuralAnalyser_Visual": (
        "init", "sim",
        "IdunBattleLogic.Entities.Abilities.Triggered.Loki."
        "StructuralAnalyser_AddDamageBuffAbility$$CreateBehaviour",
        "AmountIsGreaterThanZero(AdjacentFriends + SurroundingFriends(2) Tau)"),
    "VisionsOfHeresy_ExtraPierceMelee": (
        "init", "sim",
        "IdunBattleLogic.Entities.Abilities.Triggered.Loki."
        "VisionsOfHeresy_ExtraPierceAbility$$CreateBehaviour",
        "HealthPctIsBelowOrEqual(Owner, healthPct)"),
    "VisionsOfHeresy_ExtraPierceRanged": (
        "init", "sim",
        "IdunBattleLogic.Entities.Abilities.Triggered.Loki."
        "VisionsOfHeresy_ExtraPierceAbility$$CreateBehaviour",
        "HealthPctIsBelowOrEqual(Owner, healthPct)"),
}


def scan() -> dict:
    """RE-DERIVE tout ce qui est mecanique depuis le code (jamais un compte recopie)."""
    from engine.entities.effects.base import BaseEffect
    from engine.entities.effects.factory import (EFFECT_CLASSES, ABILITY_INIT_OWNER_EFFECTS,
                                                 ABILITY_OWNER_EFFECTS)
    seeded = {n for names in ABILITY_INIT_OWNER_EFFECTS.values() for n in names}
    seeded |= {n for names in ABILITY_OWNER_EFFECTS.values() for n in names}
    rows = []
    for name in sorted(EFFECT_CLASSES):
        klass = EFFECT_CLASSES[name]
        if klass.is_active is BaseEffect.is_active:
            continue
        pose, flip, symbol, cond = POSE_VECTOR.get(name, ("?", "?", "", ""))
        if pose == "?":
            verdict = "INCONNU"
        elif name in seeded:
            verdict = "COUVERT-SEED"
        elif pose != "init" or flip != "sim":
            verdict = "NON-EXPOSE"
        else:
            verdict = "EXPOSE"
        rows.append({"effect": name, "class": klass.__name__, "pose": pose, "flip": flip,
                     "seeded": name in seeded,
                     "acp": bool(getattr(klass, "active_condition_ported", False)),
                     "witness": getattr(klass, "seed_witness_effect", None),
                     "verdict": verdict, "symbol": symbol, "condition": cond})
    return {"n_effect_classes": len(EFFECT_CLASSES), "rows": rows,
            "unknown": [r["effect"] for r in rows if r["verdict"] == "INCONNU"]}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(
        description="case-366-r1-camo-seed : inventaire des effets condition-gated exposes au "
                    "trou de capture")
    ap.add_argument("--csv", action="store_true", help="une ligne CSV par classe")
    a = ap.parse_args(argv)

    r = scan()
    rows = r["rows"]
    if a.csv:
        print("effect,class,pose,flip,seeded,active_condition_ported,verdict")
        for x in rows:
            print("%s,%s,%s,%s,%s,%s,%s" % (x["effect"], x["class"], x["pose"], x["flip"],
                                            x["seeded"], x["acp"], x["verdict"]))
    else:
        print("EFFECT_CLASSES = %d ; surchargent `is_active` = %d"
              % (r["n_effect_classes"], len(rows)))
        print("")
        print("%-38s %-8s %-8s %-6s %s" % ("effet", "pose", "flip", "seed", "verdict"))
        for x in rows:
            print("%-38s %-8s %-8s %-6s %s"
                  % (x["effect"], x["pose"], x["flip"], "oui" if x["seeded"] else "-",
                     x["verdict"]))
        print("")
        for v in ("COUVERT-SEED", "NON-EXPOSE", "EXPOSE", "INCONNU"):
            n = sum(1 for x in rows if x["verdict"] == v)
            print("  %-14s %d" % (v, n))
        print("")
        print("EXPOSE = le natif porte l'instance (pose d'init INCONDITIONNELLE) ET la condition")
        print("  peut basculer en cours de sim, MAIS le port ne materialise l'instance que si le")
        print("  SITE DE CAPTURE demande `includeInactive` (`snapshot.decision_view_seed_body`).")

    if r["unknown"]:
        print("")
        print("[CLIQUET ROUGE] %d classe(s) surchargent `is_active` sans verdict de POSE dans "
              "POSE_VECTOR :" % len(r["unknown"]))
        for n in r["unknown"]:
            print("    %s" % n)
        print("  -> LIRE son `<X>Ability$$CreateBehaviour` au decompile (pose inconditionnelle ou")
        print("     vecteur runtime ?) et l'inscrire. Ne jamais deduire du comportement observe.")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
