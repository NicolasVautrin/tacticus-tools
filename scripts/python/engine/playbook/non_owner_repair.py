"""Face **REPAIR** de la famille `TriggeredAbilityNonOwnerPlaybook<T>` (#271-r7).

Le dispatcher `IdunBattle.AI.Utilities.TriggeredAbilitiesNonOwnerUtility` a TROIS entrees, une par
face de `ITriggeredAbilityNonOwnerPlaybook` : `$$EvaluateMovementInSteps` (slot 0),
`$$EvaluateAttackInSteps` (slot 1) et `$$EvaluateRepairInSteps` (slot 2). La face MOVE vit dans
`non_owner.py`, la face ATTACK dans `non_owner_attack.py` ; CE module porte la TROISIEME, la
DERNIERE des 28 concrets a n'etre pas montee.

LE `BLOCAGE: etage` DE CE RESIDU EST REFUTE, ET VOICI PAR QUOI
--------------------------------------------------------------
La fiche disait : << `VoltagheistFieldPlaybook` rend
`<utilitiesDatabase>.GetUtility(0x30, 0).<slot 6>(case)`, et le `<slot 6>` d'`IUtility` n'est pas
dans `data/symbols/<build>/metadata/interface_slots.tsv` (l'interface n'y figure pas) : le canal
n'est pas etabli. >> C'est le TSV qui manquait, pas le slot -- et un slot d'interface se LIT dans
le `global-metadata.dat`, exactement comme les huit autres interfaces de ce fichier.

MESURE (`probe_271r7_iutility_slots.py`, build `t6dpr4k06g`, meme machinerie
`il2cpp_metadata.locate_types` que `probe_477r25`) :

    slot 0 Init                      slot 5 EvaluateAttack
    slot 1 EvaluateAttackInSteps     slot 6 EvaluateRepair          <-- LE SLOT CHERCHE
    slot 2 EvaluateRepairInSteps     slot 7 CalculateAttackModifier
    slot 3 EvaluateMovementInSteps   slot 8 EvaluateMovement
    slot 4 EvaluateUnitInSteps       slot 9 CalculateMovementModifier

Les slots 0..8 concordent avec la DECLARATION Il2CppDumper ; le 9 est un AJOUT de ce build (ecart
de build, pas de lecture). `IUtility.<slot 6>` = `EvaluateRepair(UtilityAttackCase) -> Fix64`.

`IdunBattle.AI.Utilities.BaseUtility$$EvaluateRepair` (relu) est le pont entre la forme `InSteps`
et la forme scalaire :

    IEnumerator<Fix64> en = this.<vslot 0x268 = EvaluateRepairInSteps>(case);
    while (en.MoveNext()) ;
    return en.get_Current();          // le DERNIER yield -- ici l'unique

LE CORPS CONCRET, LU
--------------------
```c
// IdunBattle.AI.Playbook.Loki.VoltagheistFieldPlaybook.<CalculateRepairUtilityInSteps>d__1$$MoveNext
// (champs de la SM : case @+0x20, owner @+0x28, playbook @+0x30)
if (case.Target /* +0x20 */ != owner) yield break;
yield return <playbook.utilitiesDatabase @+0xe0>
                 .<IUtilitiesDatabase slot 0 = GetUtility>(0x30 /* UtilityType.RepairedAmount */, 0)
                 .<IUtility slot 6 = EvaluateRepair>(case);
```

⚠ **CE TERME EST UN DOUBLEMENT, PAS UN POIDS.** Il ne lit AUCUNE cle `BC.Utilities` : il re-emet
la feuille `RepairedAmount(48)`, qui est **deja** membre du composite `Repair(47)` (les trois
membres, lus par `probe_271r4_composition_map.py` : `RepairedAmount`, `TriggeredAbilities`,
`TriggeredAbilitiesNonOwner`). Reparer une cible qui porte `VoltagheistField` vaut donc
`2 x fill/(maxHP+1) x 100` au lieu de `1 x`. Chercher une cle BC ici serait en inventer une.

⚠ Et ca se LIT avec l'autre face du meme passif : `VoltagheistField_RepairReductionEffect$$
CreateEffectRepairBonus` DIVISE la reparation predite (le `mod_mul = 0.5` que
`calculate_repair_modifier_for_prediction` applique deja dans `_repair_candidates`). Le doublement
de l'utilite COMPENSE exactement le halving de la magnitude : sans lui, l'IA fuirait une cible
debuffee. Porter l'un sans l'autre biaise le choix de cible dans un sens ou dans l'autre.

⚠ `<slot 4>` = **false** (entree versionnee `metadata/non_owner_slot4.tsv` :
`VoltagheistFieldPlaybook  TriggeredAbilityNonOwnerPlaybook`1  REPAIR  0  0`) : le pre-gate
d'`IterateAbilities` se reduit donc a `IsFriend(caster, owner)` -- on ne repare que ses propres
machines, et le corps ne re-teste PAS l'amitie.

ASCII only dans les sorties ; les accents restent dans les docstrings non imprimees.
"""
from __future__ import annotations

from ..entities.triggered_ability_type import TriggeredAbilityType
from ..utilities.repair import REPAIR_UTILITY
from .non_owner import TriggeredAbilityNonOwnerPlaybook


class TriggeredAbilityNonOwnerRepairPlaybook(TriggeredAbilityNonOwnerPlaybook):
    """Base de la face REPAIR :
    `IdunBattle.AI.Playbook.TriggeredAbilityNonOwnerPlaybooku003C__Il2CppFullySharedGenericTypeu003E$$CalculateRepairUtilityInSteps`
    yield 0 (la base ne pese rien ; seuls les concrets qui overrident comptent).

    Signature du port -- eclatement du `UtilityAttackCase` que le natif passe entier. Le
    `repairCase` de la face REPAIR est du MEME type que celui de la face ATTACK (`frida/methods.tsv`
    le declare `IdunBattle.AI.Utilities.UtilityAttackCase` des deux cotes ; seul le NOM du parametre
    change) :
      * `caster`      = `case+0x10`, le SUJET d'`IterateAbilities` (l'unite qui REPARE) ;
      * `target`      = `case+0x20`, la cible reparee ;
      * `owner`       = le porteur de la `TriggeredAbility`, 2e element du tuple yielde ;
      * `is_friend`   = `UnitExtensions.IsFriend(caster, owner, State)`, deja calcule par le
                        dispatcher pour son pre-gate ;
      * `fill_hp` / `target_max_hp` / `caster_is_boss` = ce que la feuille `RepairedAmount(48)` lit
                        du case (`+0xdc` = le `fillUp` de la `RepairPredictionResult`, puis
                        `GetStat(Target, Health, Maximum)` et `IsBoss(Caster)`)."""

    FACE = "REPAIR"

    def calculate_repair_utility_in_steps(self, ctx, caster: int, target: int, owner: int,
                                          is_friend: bool, fill_hp, target_max_hp,
                                          caster_is_boss: bool, wt) -> float:
        return 0.0


class VoltagheistFieldNonOwnerPlaybook(TriggeredAbilityNonOwnerRepairPlaybook):
    """`VoltagheistFieldPlaybook` -- l'UNIQUE corps de face REPAIR des 28 concrets
    (`IdunBattle.AI.Playbook.Loki.VoltagheistFieldPlaybook$$.ctor`).

    Corps : cf. l'en-tete du module. `case.Target != owner` -> rien ; sinon, la valeur de la
    feuille `RepairedAmount(48)` est RE-EMISE (doublement du terme du composite `Repair(47)`).

    ⚠ Le port DELEGUE a `engine.utilities.repair.REPAIR_UTILITY` -- le meme objet que celui que le
    generateur d'actions somme deja par `engine.predict.repair_utility`. C'est le mirror du
    `GetUtility(0x30, 0)` natif, qui rend le SINGLETON enregistre a
    `UtilityType.RepairedAmount` : deux implementations divergeraient, et l'une des deux
    porterait alors une formule de reparation fausse.

    PORTEURS (voie PASSIF d'unite, `unit_map.py find --ability VoltagheistField`) :
    `admecSmnElectropriest` (**SUMMON**) et deux npc `admecNpc3Electropriest*`. Le summon compte
    (on l'amene en spawnant son invocateur) ; et le corps ne lisant du PORTEUR que son IDENTITE
    (`case.Target != owner`), la GREFFE sur une unite MECHANICAL du pool est licite (recours 3 de
    `case-92` Sec.5bis) -- c'est le montage a jouer pour la confrontation live."""

    ABILITY_ID = int(TriggeredAbilityType.VoltagheistField)
    #: `<slot 4>` LU dans `metadata/non_owner_slot4.tsv` : la classe ne declare pas le getter.
    SLOT_4 = False

    def calculate_repair_utility_in_steps(self, ctx, caster: int, target: int, owner: int,
                                          is_friend: bool, fill_hp, target_max_hp,
                                          caster_is_boss: bool, wt) -> float:
        if target is None or owner is None or int(target) != int(owner):
            return 0.0                                    # `case.Target != owner` -> yield break
        if fill_hp is None or target_max_hp is None:
            return 0.0                                    # pas de prediction -> rien a re-emettre
        return float(REPAIR_UTILITY.evaluate(fill_hp, target_max_hp, bool(caster_is_boss)))


# `IdunBattle.AI.PlaybookDatabase$$LoadPlaybookNonOwner` rend LE MEME singleton pour les trois
# faces -- c'est le DISPATCHER qui choisit le slot (0 / 1 / 2). Le port a TROIS registres parce que
# les trois dispatchers portes sont distincts ; une classe ne doit figurer que dans celui de SA
# face, LUE dans l'entree versionnee `metadata/non_owner_slot4.tsv` (24 MOVE / 3 ATTACK / 1 REPAIR).
NON_OWNER_REPAIR_PLAYBOOKS: dict = {
    int(TriggeredAbilityType.VoltagheistField): VoltagheistFieldNonOwnerPlaybook(),
}


def load_playbook_non_owner_repair(ability_id: int):
    """Mirror `PlaybookDatabase.LoadPlaybookNonOwner`, restreint aux corps de face REPAIR.
    None -> le dispatcher skip la paire (meme chemin que le `if (playbook == null) continue`)."""
    return NON_OWNER_REPAIR_PLAYBOOKS.get(int(ability_id))
