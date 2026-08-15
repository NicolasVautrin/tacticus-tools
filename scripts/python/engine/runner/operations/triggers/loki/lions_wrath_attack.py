"""PHASE 2 de `TheLionsWrath` -- la TRIGGERED `1520`, declenchee par le `Triggered()` d'
`IdunBattle.Entities.Effects.APendingAttackEffect` (`triggers/pending_attack.py`). #889.

Meme emplacement et meme cause que `loki/overwhelming_wrath_attack.py` et
`loki/seeker_missile_attack.py` : une ability TRIGGERED vit avec les triggers, pour que
`TRIGGERED_ABILITY_BEHAVIOURS[1520]` soit peuple des que `dispatch/registry.py` est charge, sans
dependre d'`abilities/handler.py` (cliquet `test_503r3_registre_trigger_peuple_offline.py`, dont le
PERIMETRE est DERIVE de `PENDING_ATTACK_EFFECTS`).

================================================================================================
`...Triggered.Loki.TheLionsWrath_PendingAttackAbility$$CreateBehaviour(abilityState, triggerType)`
================================================================================================
MIRROR 1:1 du decompile, build `rnca9r7q6c` :

  rm1 = DSLBehaviors$$RemoveEffect( targets = Owner@DSLSelectors+0x30,
                                    effectType = Nullable(0x5f1 = 1521 TheLionsWrath_PendingAttack),
                                    <4e arg> = 0 )
  atk = DSLBehaviors$$AttackWithAttackDamage(
            caster        = Caster@DSLSelectors+0x48,
            target        = Target@DSLSelectors+0x60,
            amount        = BaseTriggeredAbility$$MinMaxDamage2(this, abilityState),
            damageProfile = AbilityConfiguration$$GetDamageProfile2(config@+0x20),
            hits          = DSLFormulas$$ConfigConst(0x32 = nrOfHits_2, config@+0x20),
            abilityOrEffect = AbilityOrEffect(this),
            options       = Nullable{ +0x00..0x07 = 0 ; +0x08 = List<int>{1} ; +0x10..0x1f = 0 },
            selectionType = 2 )
  rm2 = DSLBehaviors$$RemoveEffect( targets = Owner@+0x30,
                                    effectType = Nullable(0x5f2 = 1522 TheLionsWrath_ExtraCritChance),
                                    <4e arg> = 0 )
  cond = DSLTriggers$$IsAlive( Target@+0x60 )
         op_BitwiseAnd DSLTriggers$$IsAdjacent( Caster@+0x48, Target@+0x60, selectionType = 3 )
  return DSLBehaviors$$If( cond, rm1 op_Addition atk, <else> = null )  op_Addition  rm2

LA STRUCTURE EST LE POINT : `rm2` est **HORS** du `If`. Le buff de crit 1522 est donc retire dans
TOUS les cas -- meme si la cible est morte entre-temps, meme si elle s'est eloignee -- alors que le
coup differe (`rm1 + atk`) ne part que si la cible est **VIVANTE ET ADJACENTE** au moment ou le
tour du caster commence. Coller `rm2` dans le `If` laisserait un +100 % de crit permanent sur le
boss des qu'il rate son coup differe : regression PERMISSIVE, invisible sans ce test-la.

`2` litteral en `selectionType` : c'est `UnitSelectionType.OnlyAlive`, PAS `3`
(`OnlyAliveAndTargetable`) -- transcrit, pas harmonise sur les selecteurs voisins.

QUATRE POINTS DE FIDELITE, tous LUS :

1. LE SECOND JEU DE DEGAT. `MinMaxDamage2` / `GetDamageProfile2` / `ConfigConst(0x32)` sont le jeu
   `minDmg_2` / `maxDmg_2` / `damageProfile_2` / `nrOfHits_2` -- la PHASE 1 lit le PREMIER
   (`MinMaxDamage`, `GetDamageProfile`, `ConfigConst(0x2f = nrOfHits)`). Le gameconfig de 1217
   porte bien les deux : `{damageProfile: Power, nrOfHits: 2, nrOfRounds: 1,
   damageProfile_2: Piercing, nrOfHits_2: 2}`. Ecrire le premier jeu ici changerait le PROFIL
   (Power -> Piercing, donc le `PiercingRatio` et les gates de profil de la cible) sans changer le
   nombre de coups : divergence de degat sans divergence de forme, exactement le genre qu'un
   scalaire fitte.

2. LA CONFIG EST CELLE DE L'ACTIVE 1217. `GC.ability("TheLionsWrath_PendingAttack")` rend **None**
   (mesure) -- la triggered n'a aucune entree gameconfig. Meme forme, meme mesure et meme
   conclusion que `OverwhelmingWrath_Attack` et `SeekerMissileFrequencyLock_Attack` (residu
   #513-r3 pour le site natif de l'attribution, partage).

3. `is_melee=True` : `attackRangeType` de 1217 = `"Melee"` au gameconfig. C'est la CONFIG qui
   decide, pas le noeud -- les cinq surcharges de `AttackWithAttackDamage` ne portent AUCUN bit
   melee/ranged (releve #503-r5), et `IdunBattle.Core.Services.BattleQuery$$IsMeleeAttack` part de
   `GetAbilityAttackRangeType(<l'ability du coup>)`.

4. `multi=False` : le natif passe `Target@+0x60`, un selecteur MONO-cible (le slot de cible du
   contexte), pas un selecteur d'ensemble -- contraste LU avec la phase 2 de 1141, qui passe
   `AdjacentEnemies(...)` et exige donc `multi=True` pour que l'`OrderBy` d'`AttackBehaviour`
   s'applique.

✅ **RESOLU (#889-r2, 2026-08-15) -- le champ `+0x08` des `AttackDamageBehaviourOptions`.** Le
call-site construit une `List<int>` a laquelle il `Add(1)`, la range a l'offset `+0x08` de la struct
d'options et emballe le tout dans un `Nullable`. Chaine d'offsets (deja lue par #986) :
`AttackDamageBehaviour$$.ctor` recopie `Nullable.GetValueOrDefault(options)` en `this+0x98..0xb7`
(donc `options+0x08` -> `this+0xa0`), et `AttackDamageBehaviour$$ExecuteTarget` transmet `this+0xa0`
dans l'`AttackDamageOptions` du message, a **`+0x40`**.

CE QUI MANQUAIT ETAIT LE **LECTEUR**, et la fiche le cherchait au mauvais etage : il n'est pas dans
`IdunBattle.Operations.AttackDamageOperation$$ExecuteHit` (ou le champ n'est en effet que recopie)
mais dans `IdunBattle.Operations.AttackDamageOperation$$ExecuteHits`, la boucle AU-DESSUS, en fin de
chaque coup NON CRITIQUE :

    hitGroup.<+0x3c isCriticalDamageAllowed> =
        options[+0x40] != null && options[+0x40].Any(hitIndex => hitIndex == i + 1)

`i` etant le compteur de la boucle, remis a **0** en tete de chaque `ExecuteHits`. Le predicat est le
corps ENTIER de `IdunBattle.Operations.AttackDamageOperation.u003Cu003Ec__DisplayClass4_0$$
u003CExecuteHitsu003Eb__0` :

    return hitIndex == this.<+0x10 = i> + 1;

et `IdunBattle.Operations.AttackDamageOperation$$Execute` propage le resultat a l'attaque par
`attack[+0x40] &= hitGroup[+0x3c]`.

=> **`options+0x08` est la liste des numeros de coup (1-BASED) apres lesquels le crit reste
AUTORISE.** Avec `{1}` et `nrOfHits_2 = 2`, les DEUX coups de cette phase peuvent criter ; sans
elle (`Any(null)` = faux, le cas des douze autres call-sites du depot et de l'attaque normale),
seul le premier le pourrait. C'est exactement ce que dit l'effet compagnon `1522
TheLionsWrath_ExtraCritChance`, dont le gate est `AmountIsEqual(CurrentHitIndex(), 1)` -- et
l'hypothese « indices de coups », que #889-r2 refusait de coder faute de lecture, se trouve
CONFIRMEE par le predicat ci-dessus. Port : `crit_allowed_hits=[1]` sur les DEUX phases.

NI `TARGETING_OPTIONS` NI `ABILITY_ATTACK_TYPE` : `BaseTriggeredAbility`, hors `ABILITY_CLASSES`.
ASCII only.
"""
from __future__ import annotations

from typing import TYPE_CHECKING

from ....abilities.behaviours.combat import AttackWithAttackDamage
from ....abilities.behaviours.context import entities_from_state
from ....abilities.behaviours.effects import RemoveEffect
from ....abilities.behaviours.lifecycle import TRIGGERED_ABILITY_BEHAVIOURS, TriggerAbility
from .....dsl.effects import ExecutionContext
from .....dsl.event_trigger_type import EventTriggerType
from .....entities.active_ability_type import ActiveAbilityType
from .....entities.behaviours import If, op_add
from .....entities.effect_type import EffectType
from .....entities.selectors.accessors import Owner, Target
from .....entities.selectors.tiles import Caster
from .....entities.triggers import IsAdjacent, IsAlive, TriggerAnd
from .....entities.triggered_ability_type import TriggeredAbilityType
from .....entities.unit_selection_type import UnitSelectionType
from ..base import EffectTrigger

if TYPE_CHECKING:                                  # pragma: no cover
    from ....state import State

#: Le NOM gameconfig de l'ACTIVE 1217 -- la config que lisent LES DEUX PHASES (cf. point 2).
#: DERIVE de l'enum et defini ICI plutot qu'importe d'`abilities/darkangels.py` : ce module doit
#: rester chargeable SEUL par `dispatch/registry.py` (meme discipline qu'`OW_ACTIVE_ID`).
LW_ACTIVE_ID = ActiveAbilityType.TheLionsWrath.name                    # "TheLionsWrath"
LW_ATTACK = int(TriggeredAbilityType.TheLionsWrath_PendingAttack)      # 0x5f0 = 1520
LW_PENDING_ATTACK = int(EffectType.TheLionsWrath_PendingAttack)        # 0x5f1 = 1521
LW_EXTRA_CRIT = int(EffectType.TheLionsWrath_ExtraCritChance)          # 0x5f2 = 1522
#: 3e argument LU de `DSLTriggers$$IsAdjacent(unitA, unitB, selectionType)`.
_ADJ_SELECTION = int(UnitSelectionType.OnlyAliveAndTargetable)         # 3


def lions_wrath_attack_tree():
    """Arbre de `...Triggered.Loki.TheLionsWrath_PendingAttackAbility$$CreateBehaviour` -- cf.
    l'en-tete du module. `rm2` est HORS du `If`, c'est la seule chose que la forme doit preserver.

    `Owner()` transcrit `Owner@DSLSelectors+0x30`. ⚠ Dans le port, `Owner()` retombe sur le CASTER
    (convention case-224) ; en phase 2 le caster est l'unite BONDEE, c'est-a-dire le Lion --
    l'unite qui porte le 1522. Le retrait du 1522 est donc bien adresse. Pour le 1521, pose sur la
    CIBLE (`AddBondEffect(0x5f1, source = Owner, targets = Target@+0x60, bondedEntity = Owner)` en
    phase 1), ce meme slot ne le vise PAS : c'est le `RemoveEffect(Effect@DSLSelectors+0x38)` du
    `Triggered()` d'`APendingAttackEffect` (`pending_attack_tree`) qui le retire, et il le fait
    dans le MEME arbre de declenchement. Le `rm1` d'ici est donc REDONDANT sur ce chemin -- on le
    porte quand meme, verbatim, parce que c'est ce que le natif ecrit et parce qu'il est le SEUL
    retrait sur le SECOND chemin de declenchement (`On(0x25 = UnitRemoved) & get_OwnerIsTarget`,
    qui ne porte aucun `RemoveEffect`)."""
    # DIFFERE et GRATUIT : `gameconfig` n'est pas un module `engine.*`, il n'entre dans aucun cycle
    # du paquet, et le hisser ferait payer le chargement du gameconfig a tout importeur -- donc a
    # `dispatch/registry.py`, qui importe ce module pour effet de bord. (Meme raison, meme forme
    # que `overwhelming_wrath_attack_tree`.)
    import gameconfig as GC
    consts = (GC.ability(LW_ACTIVE_ID) or {}).get("constants") or {}
    rm1 = RemoveEffect(LW_PENDING_ATTACK, Owner())
    atk = AttackWithAttackDamage(
        Target(),                                             # `Target@DSLSelectors+0x60`
        LW_ACTIVE_ID,                                         # cf. point 2 : la config de l'ACTIVE
        str(consts.get("damageProfile_2") or ""),             # `GetDamageProfile2`
        is_melee=True,                                        # cf. point 3 : `attackRangeType`
        # LE SECOND JEU (point 1) : `MinMaxDamage2` + `ConfigConst(0x32 = nrOfHits_2)`.
        min_key="minDmg_2", max_key="maxDmg_2", hits_key="nrOfHits_2",
        level_slot="active",
        multi=False,                                          # cf. point 4 : MONO-cible
        ability_type=LW_ATTACK,
        # `options` : premier qword a ZERO -> ni `alwaysOverkilled` (+4) ni `alwaysCrit` (+5) ni
        # `isNormalAttackDamage` (+6). Le champ `+0x08` (une `List<int>{1}`) est RESOLU depuis
        # #889-r2 : ce sont les numeros de coup 1-based apres lesquels `isCriticalDamageAllowed`
        # reste VRAI (cf. l'en-tete). `nrOfHits_2 = 2` -> les DEUX coups peuvent criter.
        force_overkill=False, force_crit=False, crit_allowed_hits=[1])
    rm2 = RemoveEffect(LW_EXTRA_CRIT, Owner())
    cond = TriggerAnd(IsAlive(Target()),
                      IsAdjacent(Caster(), Target(), _ADJ_SELECTION))
    return op_add(If(cond, op_add(rm1, atk)), rm2)


def _lions_wrath_attack_behaviour(state: "State", unit_id: int, entities, ectx):
    """Entree de `TRIGGERED_ABILITY_BEHAVIOURS[1520]` -- la phase 2, declenchee par le noeud
    `TriggerAbility` du `Triggered()` d'`APendingAttackEffect` (`triggers/pending_attack.py`).

    `unit_id` = l'unite declenchee (l'ATTAQUANT = le BONDE = le Lion) ; `entities` est
    l'`AbilityEntities` reconstitue par ce noeud, ou `Caster()` est l'attaquant et `Target()` le
    PORTEUR de l'effet (la cible du cast). ⚠ Contrairement a 1141, les deux slots designent ici
    DEUX unites de DEUX joueurs differents -- meme configuration que 1069.

    Le tirage du `RandomAmount` et les coups se font DANS `ectx`, donc sur le MEME `state.rng` que
    le reste du tour."""
    lions_wrath_attack_tree().execute(entities, ectx)
    # LES ETAGES du coup, pas seulement son total (meme diag que les deux autres phases 2).
    dmg = [{"target": p.get("target"), "total": (p.get("attack") or {}).get("total"),
            "etages": {k: (p.get("attack") or {}).get(k) for k in
                       ("base_min", "base_max", "pierce", "armor", "did_block", "did_crit",
                        "crits", "rolls", "per_hit", "per_hit_health",
                        "clean_min", "clean_max", "hp_before", "hp_after")}}
           for n, p in ectx.emitted if n == "AttackWithAttackDamage"]
    removed = [{"effect": p.get("effect_type"), "target": p.get("target"),
                "removed": p.get("removed")}
               for n, p in ectx.emitted if n == "RemoveEffect"]
    return {"ability": "TheLionsWrath_PendingAttack", "phase": 2, "attacker": int(unit_id),
            "damage": dmg, "removed": removed}


TRIGGERED_ABILITY_BEHAVIOURS[LW_ATTACK] = _lions_wrath_attack_behaviour


# =================================================================================================
# LE SECOND CHEMIN DE DECLENCHEMENT -- `Triggered()` de la DERIVEE, pas de la base
# =================================================================================================
# `IdunBattle.Entities.Effects.Loki.TheLionsWrath_PendingAttackEffect$$
# CreateHandleTriggerAbilitiesInternal`, mirror de l'ordre du decompile :
#
#     set = APendingAttackEffect$$CreateHandleTriggerAbilitiesInternal()   # le Triggered de la BASE
#     set.Add( DSLFactory$$Triggered(
#                  DSLTriggers$$On(0x25 = UnitRemoved, ownerNeedsToBeAlive: 0)
#                    op_BitwiseAnd DSLTriggers$$get_OwnerIsTarget,
#                  APendingAttackEffect$$GetAttackBehaviour(effect),
#                  <3e arg> = 0) )
#     return set
#
# `GetAttackBehaviour` rend le `TriggerAbility(...)` **SEUL** -- SANS le
# `RemoveEffect(Effect@DSLSelectors+0x38)` que porte le `Triggered()` de la base (lecture ecrite
# dans `triggers/pending_attack.py` Sec.1, ou les trois lectures concordent). C'est la seule
# difference de forme entre les deux chemins, et elle est LOAD-BEARING : sur ce chemin-ci le
# marqueur 1521 n'est retire que par le `rm1` de la phase 2 elle-meme.
#
# `get_OwnerIsTarget` sous l'event `On(0x25)` : `RemoveUnitOperation$$Execute` publie
# `AbilityEntities.ctor(entity, entity, entity)` -- actor = caster = target = l'unite RETIREE
# (`runner/operations/remove_unit.py`, etape 13). La condition dit donc « le PORTEUR de cet effet
# est l'unite qui quitte le plateau », c'est-a-dire la cible marquee.
#
# ⚠ ATTEIGNABILITE, mesuree comme pour `GhostRemoveOnSourceRemoved` : `On(0x25)` n'est publie que
# par `RemoveUnitOperation`, dont les appelants de production sont les feuilles `RemoveUnit` du DSL
# (MV71, `AggressiveOnslaught_Unsummon`, `HunterOfSouls`, ...) -- une MORT ordinaire passe par
# `KillUnitOperation` et ne publie PAS cet event. Ce chemin reste donc INERTE face a un roster de
# duel ordinaire ; il est ecrit parce que le natif l'ecrit, et parce que son absence ferait perdre
# le coup differe dans le seul regime ou il existe.

class LionsWrathPendingAttackOnUnitRemoved(EffectTrigger):
    """`Triggered( On(0x25 = UnitRemoved) & get_OwnerIsTarget, GetAttackBehaviour(effect) )` --
    le SECOND chemin de declenchement de `TheLionsWrath_PendingAttackEffect` (cf. le bloc ci-dessus).

    Reutilise le MEME behaviour que le chemin de la base (`pending_attack_tree` MOINS son
    `RemoveEffect`), donc le MEME couple de slots : `Caster()` = l'unite BONDEE (le Lion, l'ATTAQUANT
    -- `<klass+0x758> GetAttackingUnitSelector` = `BondedEntityFromEffect(Effect@0x38)`) et
    `Target()` = le PORTEUR de l'effet. On ne collapse pas sur le porteur : la mesure de 1069 refute
    ce collapse, et ici les deux appartiennent a deux JOUEURS differents."""
    effect_type = LW_PENDING_ATTACK
    event_ids = (int(EventTriggerType.UnitRemoved),)
    event_id = int(EventTriggerType.UnitRemoved)
    # Meme raison que `PendingAttackOnAttackersTurn` : l'ability declenchee est resolue par le
    # `TriggerAbility` du dispatch, pas par une constante de classe.
    TRIGGERED_ABILITY_ID = None

    def _instance(self, state: "State"):
        eff = getattr(state, "effects", None)
        if eff is None:
            return None
        for e in eff.by_unit.get(int(self.owner_id), []):
            if not e.consumed and int(e.effect_type) == LW_PENDING_ATTACK:
                return e
        return None

    def matches(self, state: "State", ev) -> bool:
        """`get_OwnerIsTarget` = « le porteur de cet effet est l'unite RETIREE ». Identite non
        prouvee (cle absente) => FAUX, jamais permissif."""
        if self._instance(state) is None:
            return False
        return ev.target_id is not None and int(ev.target_id) == int(self.owner_id)

    def execute_behaviour(self, state: "State", ev):
        """`GetAttackBehaviour(effect)` = le `TriggerAbility(...)` SEUL -- pas de `RemoveEffect`."""
        inst = self._instance(state)
        if inst is None:
            return None
        bonded = getattr(inst, "bonded", None)
        if bonded is None:
            # `BondedEntityFromEffect` rend une liste VIDE sans id de bond -> rien a declencher.
            return None
        entities = entities_from_state(state, int(bonded), int(self.owner_id),
                                       actor_id=int(bonded))
        ectx = ExecutionContext(state=state, rng=state.rng)
        TriggerAbility(Caster(), LW_ATTACK).execute(entities, ectx)
        fired = [p for n, p in ectx.emitted if n == "TriggerAbility"]
        return {"effect": LW_PENDING_ATTACK, "owner": int(self.owner_id),
                "attacker": int(bonded), "triggered": LW_ATTACK, "fired": fired,
                "native": "IdunBattle.Entities.Effects.Loki.TheLionsWrath_PendingAttackEffect"}
