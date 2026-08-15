"""#433-r4-r2-r1-r2-r2-r1-r1-r1-r3 -- la branche ANNEAU `TargetIsAtRange` : de « 0 porteur sur les
masques LUS » a « 0 porteur dans le BINAIRE ».

LA QUESTION BINAIRE. `rules & TargetIsAtRange` (bit 9) fait brancher
`IdunBattle.Core.Services.TargetingQuery$$GetTilesInRange` sur `<IBattleQuery slot 0x64>`
`BattleQuery$$GetTilesAtDistance(casterTiles, (int)range, onlyEmptyOrSteppable: false)` -- une
distance EXACTE, pas un disque -- et `GetInvalidTargetReason` sur `d != (int)range`. Une ability
porte-t-elle ce bit ?

POURQUOI LE COMPTE PRECEDENT NE POUVAIT PAS REPONDRE. La fiche concluait « **0** porteur sur les
148 masques RE-lus ». C'est le vice « un recenseur ne peut pas rendre zero sur ce qu'il ne visite
pas » : le registre du port ne couvre pas le binaire, et une ability dont le masque n'est pas lu
aurait pu porter le bit sans que rien ne le montre. Le compte a d'ailleurs BOUGE depuis (148 ->
**182** masques lus, `TARGETING_OPTIONS_UNPORTED` desormais VIDE) sans que le zero change -- ce qui
ne prouve toujours rien sur les ctors non lus.

CE QUE CE PROBE VISITE, et c'est la POPULATION ENTIERE des ctors du binaire :

  * **etape `recensement`** -- `data/symbols/<build>/ghidra/functions.tsv` porte **tous** les
    `IdunBattleLogic.Entities.Abilities.Active.*$$.ctor`. Chacun doit tomber dans l'un des trois
    ensembles COUVERTS ci-dessous ; un ctor hors des trois fait ROUGIR l'etape, parce qu'il
    signifie « un masque du binaire que personne n'a lu ». C'est le cliquet : au prochain build,
    une ability neuve apparait ICI, pas dans un silence ;
  * **etape `bits`** -- aucun des masques connus (registre du port, profils d'attaque normale,
    presets du `cctor`, ctors relus a la main) ne porte le bit 9.

LES TROIS ENSEMBLES COUVERTS, et par quelle LECTURE :

  1. le REGISTRE du port (`ABILITY_CLASSES[...].TARGETING_OPTIONS`) + les 18 profils d'attaque
     normale -- masques deja RE-lus, chacun cite son ctor ;
  2. `CTORS_RELUS` -- les ctors que le registre ne couvrait pas, relus UN PAR UN au decompile de
     `t6dpr4k06g` pour cette tranche (valeur `rules` en clair ci-dessous) ;
  3. `PRESETS_CCTOR` -- les 16 `TargetingOptions` statiques ecrits par
     `IdunBattle.Core.Services.TargetingOptions$$.cctor`, que les ctors « static-copy » recopient
     sans OR (verifie sur les 32 relus de la categorie).

⚠ CE QUE CE PROBE NE COUVRE PAS, et il le DIT : les abilities `IdunBattleLogic.Entities.Abilities.
Triggered.*`, hors du prefixe recense. Une seule d'entre elles construit des `TargetingOptions`
(`MV71SniperDroneSquadAttackAbility$$.ctor`, via `TargetingOptions$$CustomLokiNormalAttackOptions`
avec `extraRules = 0x2`) ; elle figure dans `CTORS_RELUS` a ce titre.

CONSEQUENCE POUR LE PORT. La branche ANNEAU reste un mirror STRUCTUREL et NON CONFRONTE -- mais
plus « faute de porteur trouve » : parce qu'il n'en existe **aucun** dans ce build. Le montage qui
la confronterait exige une ability NATIVE portant le bit : ni la greffe (`catalog_inject`) ni
l'injection de catalogue ne peuvent l'armer, le masque etant cable dans le ctor natif.

ASCII only.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from engine.runner.abilities import targeting as TGT                      # noqa: E402
from engine.runner.abilities.handler import ABILITY_CLASSES               # noqa: E402
from engine.runner.abilities.targeting_rule import TargetingRule as TR    # noqa: E402

PYDIR = Path(__file__).resolve().parent
ROOT = PYDIR.parents[1]

PREFIXE = "IdunBattleLogic.Entities.Abilities.Active"
SUFFIXE = "$$.ctor"

#: Les 16 `TargetingOptions` STATIQUES, `rules` a `<preset>+0x28`, relus a l'octet sur
#: `IdunBattle.Core.Services.TargetingOptions$$.cctor` (build `t6dpr4k06g`). Cle = l'offset du
#: preset dans le bloc statique. Les ctors « static-copy » en recopient les 0x40 octets TELS QUELS.
PRESETS_CCTOR = {
    0x000: 0x4002, 0x040: 0x4000, 0x080: 0x4000, 0x0c0: 0x80040,
    0x100: 0x8500, 0x140: 0x4002, 0x180: 0x4002, 0x1c0: 0x6000040,
    0x200: 0x42, 0x240: 0x102004032, 0x280: 0x8004, 0x2c0: 0x4000,
    0x300: 0x4000, 0x340: 0x4000, 0x380: 0x400, 0x3c0: 0x200000000000004,
}

#: Les ctors que le registre du port ne couvre pas, RELUS un par un au decompile pour cette tranche.
#: Valeur = le litteral `rules` passe a `TargetingOptions$$.ctor`, ou l'offset du preset recopie
#: (prefixe `preset:`) pour un static-copy, ou `delegue:` quand le ctor delegue a une base qui n'a
#: pas de `TargetingOptions` propre.
CTORS_RELUS = {
    # --- flags directs, hors registre ---------------------------------------------------------
    "PoundThemToDustAbility": 0x4000,
    "PrecisionShot_AttackAbility": 0x4004,
    "RogalDorn_NormalAttackAbility": 0x4000,
    "SpawnPoxwalkersAbility": 0x8000000004,
    "TestDamageMachineAbility": 0x100040004000,
    "TheWailingDoomStrikesAbility": 0x2000000042,
    "TheWailingDoomSweepsAbility": 0x2000000042,
    "TreasonOfTzeentchAbility": 0x4800000004002,
    "TunnelingHorror_AppearAbility": 0x80008000000000,
    "TwistedScience_HealAbility": 0x8402,
    "NoneAbility": 0x8000000,
    "NeedsMoreDakkaAbility": 0x1000000042,
    "EreWeGoAbility": 0x1042,
    "DeathScreamAbility": 0x4000,
    "LivingBatteringRamAbility": 0x4002,
    "FloatingDeath_NormalAttackAbility": 0x4000,
    "GunnersKillOnSightAbility": 0x84,
    "ArmouredMight_MoveAbility": 0x80,
    "MachineTestAbility": 0x40004000,
    "BladeOfMagnusAbility": 0x4000,
    "TestTileAttack": 0x80040,
    "TestAttackTilesAbility": 0x80040,
    "MightOfHeroesAbility": 0x8400,
    "BurrowersAbility_Appear": 0x8040000004,
    "MassHealAbility": 0x8002,
    # --- static-copy d'un preset, hors registre -----------------------------------------------
    "ChainLightningAbility": "preset:0x80",
    "HolyBoltAbility": "preset:0x80",
    "AnnihilatorBeamAbility": "preset:0x280",
    "BreathOfSilenceAbility": "preset:0x280",
    "DaGreatWaaaghAbility": "preset:0x280",
    "DiveAttackAbilityBase": "preset:0x40",
    "MyWillBeDoneAbility": "preset:0x280",
    "ScytheOfDustAbility": "preset:0x340",
    "ShroudPsalmAbility": "preset:0x280",
    "SpawnTermagantsAbility": "preset:0x280",
    "StaffOfStarsAbility": "preset:0x0",
    "TargetingProtocolsAbility": "preset:0x280",
    "TheWrathOfKhaineUnleashedAbility": "preset:0x280",
    "TheWrathOfKhaineUnleashedReworkedAbility": "preset:0x280",
    "TzeentchsFirestormAbility": "preset:0x280",
    "UnparalleledFerocityAbility": "preset:0x40",
    "TauntAbility": "preset:0x340",
    # --- delegations : aucun `TargetingOptions` propre ------------------------------------------
    "CrushingStrikeTraitAbility": "delegue:AOwnerEffectSpecificTriggeredAbility",
    "BlessingsOfKhorneAbility": "delegue:AOwnerEffectSpecificTriggeredAbility",
    "CloseCombatWeakness_AddEffectAbility": "delegue:AOwnerEffectSpecificTriggeredAbility",
    "GenericAddEffectToOwnerAbility": "delegue:UnityThreadUtilsInternal",
    "InfiltrateAddEffectAbility": "delegue:AOwnerEffectSpecificTriggeredAbility",
    "InstinctiveBehaviour_InitAbility": "delegue:AOwnerEffectSpecificTriggeredAbility",
    "OverwatchAutoAttackAbility": "delegue:AOwnerEffectSpecificTriggeredAbility",
    "RammingSpeed_ExtraExplodeEffect": "delegue:BaseEffect",
    "ShadowInTheWarp_AddEffectAbility": "delegue:AOwnerEffectSpecificTriggeredAbility",
    "SwoopingHawkAbility": "delegue:DiveAttackAbilityBase",
    "Synapse_AddEffectAbility": "delegue:AOwnerEffectSpecificTriggeredAbility",
    "TerminatorArmour_AddVisualEffectAbility": "delegue:AOwnerEffectSpecificTriggeredAbility",
    "UnbreakableDuty_DamageReductionEffect": "delegue:BaseEffect",
    "TerrifyingAbilityAbility": "delegue:AOwnerEffectSpecificTriggeredAbility",
    # --- fabriques : preset OR `extraRules`, ce dernier lu a l'octet au call-site ---------------
    "NobleChargeAbility": 0x4000 | 0x10000000,          # CustomIdunNormalAttackOptions(0x10000000)
    "GauntletsOfUltramarAbility": 0x4000,               # SelfCastIfEnemyInCustomRangeOptions
    "MV71SniperDroneSquadAttackAbility": 0x4002 | 0x2,  # CustomLokiNormalAttackOptions(0x2)
    # --- les ctors `Test*` du binaire : du code de test du jeu, mais RELUS comme les autres ------
    # Aucune LISTE BLANCHE ici, et c'est deliberé : les exclure par leur PREFIXE aurait re-introduit
    # exactement le vice que ce probe corrige -- un recenseur qui rend zero sur ce qu'il ne visite
    # pas. Ils sont tous des static-copy PURS d'un preset.
    "TestAbility": "preset:0x80",
    "TestDecoyAbility": "preset:0x1c0",
    "TestDirectForceOverkillAbility": "preset:0x0",
    "TestDirectKillAbility": "preset:0x0",
    "TestDoubleMeleeAttackDamageAbility": "preset:0x40",
    "TestMeleeAbilityDamageAbility": "preset:0x40",
    "TestMeleeAttackDamageAbility": "preset:0x40",
    "TestMultiHitAttackAbility": "preset:0x0",
    "TestMultipleHitGroupsWithDifferentDamageProfileTypesAttackDamageAbility": "preset:0x40",
    "TestMultipleTargetsAttackDamageAbility": "preset:0x40",
    "TestRangedAbilityDamageAbility": "preset:0x180",
    "TestRangedAttackDamageAbility": "preset:0x140",
    "TestSummonAbility": "preset:0x1c0",
    "TestSummonOnBestUtilitytileAbility": "preset:0x1c0",
    "TestTargetAndAdjacentAttack": "preset:0x40",
    "TestTwoHitGroupsAttackDamageAbility": "preset:0x40",
}

#: Le build sur lequel `CTORS_RELUS` et `PRESETS_CCTOR` ont ete LUS. Le recensement doit porter sur
#: le MEME, sinon il apparie des noms a des valeurs d'un autre binaire -- la desynchronisation
#: silencieuse que le CLAUDE.md interdit.
BUILD_DE_LECTURE = "t6dpr4k06g"


def _build_avec_symboles() -> str:
    """Le build INSTALLE, via le foyer `build_pin.installed_build` -- jamais devine depuis le
    contenu de `data/symbols/`, qui peut porter plusieurs builds a la fois (mesure : 4 sur cette
    machine, chacun estampille de son propre nom, donc indiscernables par leur seul fichier
    `BUILD`)."""
    from build_pin import installed_build
    return installed_build()


def _ctors_du_binaire(build: str) -> list:
    src = ROOT / "data" / "symbols" / build / "ghidra" / "functions.tsv"
    out = []
    with src.open(encoding="utf-8", errors="replace") as f:
        for line in f:
            parts = line.rstrip("\n").split("\t")
            if len(parts) < 2:
                continue
            nom = parts[1]
            if nom.startswith(PREFIXE) and nom.endswith(SUFFIXE):
                out.append(nom.rsplit(".", 1)[0].rsplit(".", 1)[-1].replace("$", ""))
    return sorted(set(out))


def _noms_du_registre() -> set:
    """Les noms de classe que le REGISTRE du port couvre, apparies par le nom d'`ActiveAbilityType`
    suffixe `Ability` (la convention du binaire)."""
    from engine.entities.active_ability_type import ActiveAbilityType as AAT
    noms = set()
    for a in ABILITY_CLASSES:
        o = TGT.targeting_options_for(a)
        if o is None or getattr(o, "rules", None) is None:
            continue
        try:
            noms.add(AAT(int(a)).name)
        except Exception:
            pass
    for t in TGT.NORMAL_ATTACK_TARGETING_OPTIONS_BY_TYPE:
        try:
            noms.add(AAT(int(t)).name)
        except Exception:
            pass
    return noms


def recensement() -> dict:
    """Chaque ctor du binaire tombe-t-il dans l'un des trois ensembles COUVERTS ?"""
    build = _build_avec_symboles()
    ctors = _ctors_du_binaire(build)
    reg = _noms_du_registre()

    def _couvert(n):
        base = n[:-7] if n.endswith("Ability") else n
        return base in reg or n in CTORS_RELUS

    decouverts = [n for n in ctors if not _couvert(n)]
    return {"build_installe": build, "build_de_lecture": BUILD_DE_LECTURE,
            "lecture_sur_le_build_installe": build == BUILD_DE_LECTURE,
            "table_de_symboles_presente":
                (ROOT / "data" / "symbols" / build / "ghidra" / "functions.tsv").exists(),
            "ctors_recenses": len(ctors),
            "couverts_par_le_registre": sum(1 for n in ctors
                                            if (n[:-7] if n.endswith("Ability") else n) in reg),
            "couverts_par_CTORS_RELUS": sum(1 for n in ctors if n in CTORS_RELUS),
            "DECOUVERTS": decouverts,
            "couverture_totale": not decouverts}


def bits() -> dict:
    """Aucun masque connu ne porte le bit 9 -- registre, profils d'attaque normale, presets, ctors
    relus."""
    from engine.entities.active_ability_type import ActiveAbilityType as AAT
    bit = int(TR.TargetIsAtRange)
    porteurs = []
    n_reg = 0
    for a in ABILITY_CLASSES:
        o = TGT.targeting_options_for(a)
        if o is None or getattr(o, "rules", None) is None:
            continue
        n_reg += 1
        if int(o.rules) & bit:
            porteurs.append({"source": "registre", "id": int(a)})
    n_na = 0
    for t, o in TGT.NORMAL_ATTACK_TARGETING_OPTIONS_BY_TYPE.items():
        n_na += 1
        if int(o.rules) & bit:
            porteurs.append({"source": "attaque_normale", "id": int(t)})
    for off, r in PRESETS_CCTOR.items():
        if int(r) & bit:
            porteurs.append({"source": "preset_cctor", "offset": hex(off)})
    n_relus = 0
    for nom, v in CTORS_RELUS.items():
        if isinstance(v, int):
            n_relus += 1
            if v & bit:
                porteurs.append({"source": "ctor_relu", "classe": nom})
        elif isinstance(v, str) and v.startswith("preset:"):
            n_relus += 1
            r = PRESETS_CCTOR[int(v.split(":")[1], 16)]
            if r & bit:
                porteurs.append({"source": "static_copy", "classe": nom})
    return {"bit": bit, "nom": TR.TargetIsAtRange.name,
            "masques_registre": n_reg, "profils_attaque_normale": n_na,
            "presets_cctor": len(PRESETS_CCTOR), "ctors_relus_a_masque": n_relus,
            "PORTEURS": porteurs, "gisement_vide": not porteurs}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--step", default="offline", choices=["offline", "recensement", "bits"])
    a = ap.parse_args()
    if a.step in ("offline", "recensement"):
        print("recensement :", json.dumps(recensement())[:1200])
    if a.step in ("offline", "bits"):
        print("bits        :", json.dumps(bits())[:1200])
    return 0


if __name__ == "__main__":
    sys.exit(main())
