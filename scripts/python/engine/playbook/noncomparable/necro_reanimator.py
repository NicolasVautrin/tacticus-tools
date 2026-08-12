"""Les DEUX faces DECISION de `necroReanimator` (MACHINE OF WAR Necrons) -- #967.

`ReanimationBeam` (1223) et `NanoscarabRepairProtocols` (1224) partagent leur porteur, leur base
et leur `.cctor` ; elles ne different que par UNE ligne d'utilite. D'ou un module commun.

BASE, LUE dans `data/symbols/<build>/frida/classes.tsv` : les deux classes derivent de
`IdunBattle.AI.Playbook.NonComparablePlaybook`1`. Le `.ctor` decompile NOMME
`ComparablePlaybook<...>..ctor` pour les deux -- corps trivial DEDUPLIQUE par IL2CPP, le piege
de #487-r1 / #945 / #957. Ne jamais lire la hierarchie dans le `.ctor`.

REACHABILITY, LUE dans `data/symbols/<build>/metadata/active_playbook_builders.tsv`
(`IdunBattle.AI.PlaybookDatabase$$InitializePlaybookBuilders`) :

    active  1223  IdunBattle.AI.Playbook.Loki.ReanimationBeamPlaybook
    active  1224  IdunBattle.AI.Playbook.Loki.NanoscarabRepairProtocolsPlaybook

-- une entree chacune dans le dict `active` : ce n'est pas du code registered-but-dead.

RECENSEMENT AU BLOC D'ADRESSES (`ghidra/functions.tsv`, `probe_967_playbook_blocks.py`) : chaque
classe occupe un bloc CONTIGU de trois corps (`EvaluateNonComparable`, `.cctor`, `.ctor`), le
voisin suivant appartenant a une autre classe. RIEN n'y est fondu. S'y ajoute, pour 1223 seule,
`IdunBattle.AI.Playbook.Loki.ReanimationBeamPlaybook$$get_Priority` -- corps `mov eax,0xFFFFFC18 ;
ret` DEDUPLIQUE, siegeant tres loin du bloc, et c'est le SEUL `get_Priority` de playbook que
Ghidra nomme dans tout le binaire (cf. l'encadre de `_base.NATIVE_PRIORITY`).
"""
from __future__ import annotations

from engine.entities.active_ability_type import ActiveAbilityType
from engine.entities.stats import StatType

import engine.playbook.noncomparable._targets as TGT   # FORME B, en ABSOLU (cf. #962)
from ._base import NCContext, NonComparablePlaybook, native_priority


class ReanimationBeamPlaybook(NonComparablePlaybook):
    """`IdunBattle.AI.Playbook.Loki.ReanimationBeamPlaybook$$EvaluateNonComparable` (0x4c7 = 1223).

    LE CORPS, TERME A TERME -- c'est le playbook le plus court des six :

        bucket = new Bucket<UnitAction>(0, Nullable(<statics+0x00>))     # `.cctor` : Fix64(1)
        foreach entities in BasePlaybook.GetEligibleTargetsSelectable(caster, casterPosition):
            bucket.AddAction(BasePlaybook.GenerateAction(casterPosition, entities@+0x10,
                                                         Fix64.op_Implicit(1)))

    L'utilite est la CONSTANTE `Fix64(1)`, litteral INLINE (aucun `GetStat`, aucun appel de
    requete). `IdunBattle.AI.Playbook.Loki.ReanimationBeamPlaybook$$.cctor` pose
    `Fix64.op_Implicit(1)` -> `MIN_UTILITY = 1` = l'utilite elle-meme : toute cible eligible est
    admise, aucune n'est departagee. `AddAction` ne remplacant que sur `>` STRICT, c'est donc la
    PREMIERE cible enumeree qui gagne, toujours.

    PRIORITY = **-1000** (`AbilityPriority.Last`). Ce n'est pas une deduction : les OCTETS du corps
    natif sont `b8 18 fc ff ff c3` = `mov eax,0xFFFFFC18 ; ret`, cites depuis #170 dans l'encadre
    de `_base.NATIVE_PRIORITY`, et confirmes par le sweep exhaustif des 258 `ActiveAbilityType`.
    Consequence EXERCEE sur ce porteur : `necroReanimator` porte AUSSI `NanoscarabRepairProtocols`
    (1224), de tier **0**. Les tiers etant evalues dans l'ordre [1000, 100, 0, -100, -1000] et le
    tactic prenant le PREMIER generateur non vide, 1224 PRIME donc TOUJOURS sur 1223 des qu'elle a
    une cible -- quelle que soit son utilite. C'est un ordonnancement PAR L'ORDRE DES GENERATEURS,
    que `choose_action(priority=...)` mirrore.

    CIBLES : des allies MECANIQUES deja marques par l'effet `NanoscarabRepairProtocols` (1545) --
    cf. `IdunBattleLogic.Entities.Abilities.Active.Loki.ReanimationBeamAbility$$GetDynamicInvalidTargetReason`,
    deja lu et documente par la face COMBAT (`engine/runner/abilities/necrons.py`, #902). Le port
    ne re-implemente pas ce gate : `abilityTargets` le rend deja applique."""
    ABILITY_ID = int(ActiveAbilityType.ReanimationBeam)   # 0x4c7 = 1223
    MIN_UTILITY = 1.0     # `ReanimationBeamPlaybook$$.cctor` : `Fix64.op_Implicit(1)` -> statics+0x00
    PRIORITY = native_priority(int(ActiveAbilityType.ReanimationBeam))   # -1000 (octets du corps)

    def generate_candidates(self, ctx: NCContext) -> list[dict]:
        elig = TGT.eligible_units(ctx, self.ABILITY_ID)
        if not elig:
            return []
        tid = elig[0][0]                    # utilite CONSTANTE -> keep-first (remplacement STRICT)
        if ctx.debug:
            import sys
            print("    [dbg NC u%s] ReanimationBeam target=%s (util constante 1, %d eligibles)"
                  % (ctx.uid, tid, len(elig)), file=sys.stderr)
        # cast EN PLACE : le porteur est une MoW SANS position, `casterPosition` est la position
        # nulle et l'utilite n'en depend pas.
        return [{"target": tid, "ability": self.ABILITY_ID, "to": None, "pred": 1.0}]


class NanoscarabRepairProtocolsPlaybook(NonComparablePlaybook):
    """`IdunBattle.AI.Playbook.Loki.NanoscarabRepairProtocolsPlaybook$$EvaluateNonComparable`
    (0x4c8 = 1224).

    LE CORPS, TERME A TERME -- meme squelette que 1223, une seule ligne differe :

        bucket = new Bucket<UnitAction>(0, Nullable(<statics+0x00>))     # `.cctor` : Fix64(1)
        foreach entities in BasePlaybook.GetEligibleTargetsSelectable(caster, casterPosition):
            u = UnitExtensions.GetStat(entities@+0x10, 0, 0, 0)
            bucket.AddAction(BasePlaybook.GenerateAction(casterPosition, entities@+0x10,
                                                         Fix64.op_Implicit(u)))

    `GetStat(target, 0, 0, 0)` : le premier argument est un `StatType`, et **0 = ATTACK** (le
    mirror `engine.entities.stats.StatType` ; contraste `MindControlPlaybook`, qui lit `5 = HEALTH`
    au MEME emplacement -- deux playbooks au squelette identique dont seul l'ORDINAL differe,
    exactement la confusion que la regle « un entier qui DESIGNE passe par un ENUM » evite). Les
    2e/3e arguments a `0` sont `StatPart.Current` et le drapeau de partie -- la MEME lecture que
    `SendInTheNextWavePlaybook` (`GetStat(cible, Attack=0, Current)`), dont `scene.attack_current`
    est deja le foyer offline.

    ⚠ L'utilite ne lit **PAS** `hpToRepair`, et ce n'est pas une simplification. La magnitude de
    reparation de 1224 est lue par l'EFFET 1545
    (`IdunBattle.Entities.Effects.Loki.NanoscarabRepairProtocolsEffect$$CreateEffectRepairBonus`),
    pas par le cast -- le meme constat que la face COMBAT a etabli (#902,
    `engine/runner/abilities/necrons.py`). Le playbook, lui, classe ses cibles par leur ATTAQUE :
    il repare la machine alliee qui FRAPPE le plus fort.

    MIN_UTILITY = 1 (le `.cctor`) : une cible d'Attaque nulle serait ecartee. PRIORITY = 0 --
    1224 est ABSENTE de `NATIVE_PRIORITY` (sweep exhaustif #170), donc `AbilityPriority.Normal`.

    ⚠ ROUTAGE : `engine/ai/action_generators.py` EXCLUT deja 1224 du set Comparable-repair
    (`_COMPARABLE_REPAIR_IDS = {Repair(28)}`, et son commentaire nomme `NanoscarabRepairProtocols`
    comme « NonComparable-repair, exclu »), et `engine/predict.py` la range dans `_REPAIR_NC_KEYS`.
    Les deux etaient donc CORRECTS -- mais sans playbook NC enregistre, l'exclusion faisait de 1224
    une ability que le moteur ne proposait JAMAIS. C'est ce trou-la que ce port ferme."""
    ABILITY_ID = int(ActiveAbilityType.NanoscarabRepairProtocols)   # 0x4c8 = 1224
    MIN_UTILITY = 1.0     # `NanoscarabRepairProtocolsPlaybook$$.cctor` : `Fix64.op_Implicit(1)`
    PRIORITY = 0          # hors `NATIVE_PRIORITY` (defaut `AbilityPriority.Normal`, sweep #170)

    #: `GetStat(target, <ici>, 0, 0)` -- l'ordinal ECRIT AU SITE natif, nomme.
    STAT = StatType.ATTACK        # 0

    def generate_candidates(self, ctx: NCContext) -> list[dict]:
        if ctx.scene is None:
            return []             # `GetStat` non mesurable -> aucun candidat (jamais une utilite
            #                       inventee : un 0 ferait tomber le gate MIN_UTILITY a tort)
        elig = TGT.eligible_units(ctx, self.ABILITY_ID)
        if not elig:
            return []
        best = None               # (targetId, attack)
        for tid, _pos in elig:
            atk = float(ctx.scene.attack_current(tid))
            if best is None or atk > best[1]:      # argmax STRICT -> keep-first au tie
                best = (tid, atk)
        if best is None or best[1] < self.MIN_UTILITY:
            return []
        if ctx.debug:
            import sys
            print("    [dbg NC u%s] NanoscarabRepairProtocols target=%s attack=%s"
                  % (ctx.uid, best[0], best[1]), file=sys.stderr)
        return [{"target": best[0], "ability": self.ABILITY_ID, "to": None, "pred": best[1]}]
