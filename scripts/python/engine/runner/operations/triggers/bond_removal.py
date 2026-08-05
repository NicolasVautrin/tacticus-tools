"""Le RETRAIT herite d'`IdunBattle.Entities.Effects.ABondEffect` (#462-r4b-r1-r1-r1-r1).

`IdunBattle.Entities.Effects.ABondEffect$$CreateHandleTriggerAbilitiesInternal` construit JUSQU'A
TROIS `Triggered()` de `RemoveEffect`, communs a TOUTES les classes d'effet BOND. Chacun est sous un
appel VIRTUEL de la classe d'effet -- c'est le virtuel, et lui seul, qui decide si le trigger entre
dans l'`ArraySet` :

    (a) <klass+0x748>() : bool  ->
          Triggered( NOT AmountIsZero(BondedEntityFromEffect(Effect@DSLSelectors+0x38))
                     & ( On(2 = PreUnitDeath_2) | On(0x25 = UnitRemoved) )
                     & IsEntityWithIdTarget(BondedEntityFromEffect(...)),
                     RemoveEffect(Effect@0x38) )

    (b) <klass+0x728>() : Nullable<int> ; si HasValue ->
          Triggered( NOT IsInRange(Owner@DSLSelectors+0x30, BondedEntity, Direct(value))
                     & NOT AmountIsZero(BondedEntity) & On(0x1d = UnitPositionChanged_2),
                     RemoveEffect(Effect@0x38) )

    (c) <klass+0x738>() : bool  ->
          Triggered( NOT IsAdjacent(Owner@0x30, BondedEntity, 3)
                     & NOT AmountIsZero(BondedEntity) & On(0x1d),
                     RemoveEffect(Effect@0x38) )

================================================================================================
1. LES TROIS VIRTUELS SONT NOMMES -- au RUNTIME, parce que les tables ne pouvaient pas le dire
================================================================================================
`probe_462_r4b_r1_r1_r1_r1_bond_removal.py --step vtable` lit les slots sur l'instance et rend le
`il2cpp_method_get_name` de chacun :

    +0x728 = `get_Range`                        (`System.Nullable<System.Int32>`)
    +0x738 = `get_Adjacent`                     (`System.Boolean`)
    +0x748 = `get_RemoveOnBondedEntityDeath`    (`System.Boolean`)

⚠ Ce pas ne CONCLUT pas seul : une vtable IL2CPP n'est materialisee qu'apres
`il2cpp_runtime_class_init`, et la BASE `ABondEffect` -- abstraite, jamais instanciee -- rend le
stub de remplissage paresseux (`Unity.Burst.Unsafe$$AsRef`, qui ne retourne pas) pour les trois
slots. Comparer a elle serait comparer a du bruit. C'est `--step declared` qui conclut : il enumere
`class_get_methods` NIVEAU PAR NIVEAU de la chaine de parents, et une classe qui SURCHARGE declare
son propre `MethodInfo` meme quand IL2CPP a DEDUPLIQUE le corps (le `methodPointer` est partage,
l'entree de la classe ne l'est pas). C'est exactement ce que `frida/methods.tsv` -- indexee par
ADRESSE -- ne peut pas montrer.

Les trois corps triviaux, resolus par leur ADRESSE au decompile (les noms ghidra qui y sont
attaches, `UnityEngine.U2D.IK.Solver2D$$DoValidate` et consorts, sont ceux du proprietaire
ARBITRAIRE du corps partage -- ils ne disent RIEN de l'appelant) :

    `0x1802b4590` = `return 1`   -> bool TRUE
    `0x1802b45a0` = `return 0`   -> bool FALSE
    `0x1802b45b0` = `return 0`   -> `Nullable<int>` VIDE (pas de portee)

================================================================================================
2. LE GATE `NOT AmountIsZero(BondedEntity)` MORD -- et la lecture LITTERALE dit le contraire
================================================================================================
`IdunBattleLogic.Entities.DSLTriggers$$AmountIsZero(selector)` construit
`NOT AmountIsGreaterAbilityTrigger(selector, <DSLFormulas+0x20>)`, et
`IdunBattle.Entities.Conditions.AmountIsGreaterAbilityTrigger$$ShouldTrigger` rend
`minAmount < amount`. Or `<DSLFormulas+0x20>` vaut **1**, pas 0 :

  * `IdunBattleLogic.Entities.DSLFormulas$$.ctor` ecrit `+0x18 <- Direct(0)`, `+0x20 <- Direct(1)`,
    `+0x28 <- Direct(2)`, `+0x30 <- Direct(100)`, `+0x38 <- Direct(-1)` ;
  * `IdunBattleLogic.Entities.DSLTriggers$$AmountIsGreaterThanZero`, lui, lit `+0x18` -- son nom
    colle donc a `minAmount = 0`, et `AmountIsZero` lit bien un AUTRE slot ;
  * `IdunBattle.Entities.Effects.Loki.NeuroparasiteEffect$$GetIncreaseLevelBehaviour` passe
    exactement `+0x20` en 2e argument d'`IdunBattleLogic.Entities.DSLBehaviors$$IncreaseEffectLevel`
    (`effect, amount, max`), et #556 a MESURE live niveau 1 -> 2. `+0x20` vaut 1.

Et `IdunBattle.Entities.Selectors.SelectBondedEntityFromEffectSelector$$Select` rend AU PLUS UN
element : il prend `Enumerable.First` du selecteur d'effet, lit le `BondedEntityId` du composant de
bond, resout l'entite, et passe par `IdunBattleLogic.Extensions.TExtensions$$ToList<T>` -- dont le
corps fait UN SEUL `List<T>.Add`, sans boucle. Sinon il rend une liste VIDE.

Litteralement, `AmountIsZero(x) == (count(x) <= 1)` serait donc TOUJOURS vrai sur ce selecteur, et
`NOT AmountIsZero` TOUJOURS faux : les trois triggers seraient structurellement morts.

**LA MESURE REFUTE CETTE LECTURE.** `--step killlive`, runner `MC1_67`, Neurothrope patche a 1000
PV, victime a 400000 de degat :

    mort d'une unite TIERCE (`ultraCalgar`, notre camp) -> parasite 1218 PRESENT (level 1)
    mort du BONDE (le Neurothrope)                      -> parasite 1218 ABSENT

Et le retrait n'est attribuable a AUCUN autre chemin : `IdunBattle.Operations.RemoveEffectsOperation$$Execute`
-- la voie qu'empruntent `IdunBattle.Operations.KillUnitOperation$$RemoveEffects` et l'etape 14 de
`IdunBattle.Operations.RemoveUnitOperation$$Execute` -- lit la liste des effets sur le composant
d'effets de l'unite QUI MEURT (champ `+0x10`), c'est-a-dire les effets qu'elle PORTE. Le parasite,
lui, est porte par la VICTIME, qui ne meurt pas. Il n'existe aucun nettoyage natif << par SOURCE >>.

⇒ Le port mirrore la semantique MESUREE : `NOT AmountIsZero(BondedEntity)` = << l'entite bondee est
encore resoluble dans l'etat >>. La reconciliation exacte avec le litteral `<DSLFormulas+0x20>` = 1
n'est PAS tranchee -- residu nomme `#462-r4b-r1-r1-r1-r1-r1`. Elle ne change rien au comportement
porte : sur les deux vecteurs `On(2)` et `On(0x25)` le bonde est encore dans l'etat (l'event part
AVANT la consommation des effets, cf. `remove_unit.py` etape 13), donc les deux lectures possibles
du gate coincident sur tout ce qui est confrontable ici.

================================================================================================
3. LA TABLE -- ce qu'elle contient, et pourquoi PAS PLUS
================================================================================================
La cle est l'`EffectType` du PORT ; la valeur est la mesure `--step declared` de la classe NATIVE
correspondante. N'y entrent que les effets de bond que le port POSE (call-sites `AddBondEffect`) ET
dont la classe native est ETABLIE par une preuve directe -- jamais par ressemblance de nom, qui
serait fausse (`EffectType.Taunted_OnlySpecificTargets` est servi par `TauntedEffect`,
`EffectType.ValkyrieStrike_Effect` par `ValkyrieStrikeEffect`).

RESIDUS NOMMES, explicitement HORS table (aucun trigger pose pour eux -- statu quo) :

  * **Les 20 derivees d'`IdunBattle.Entities.Effects.APendingAttackEffect`** : RESOLUES
    (#462-r4b-r1-r1-r1-r1-c). Elles heritent toutes de
    `IdunBattle.Entities.Effects.APendingAttackEffect$$get_RemoveOnBondedEntityDeath`, dont le corps
    est `NOT <klass+0x778>()`. Ce QUATRIEME virtuel est NOMME `IsExecutedIfOwnerDies`, mesure par
    `--step pending` (voie `class_get_methods`, qui n'exige aucune initialisation) et recoupe sur
    vtable materialisee, controle d'alignement passe. Les 20 le DECLARENT en propre : **17 a `false`**
    (donc `get_RemoveOnBondedEntityDeath` VRAI) et **3 a `true`** -- `AnnihilatorBeam`,
    `TargetingProtocols` et `ValkyrieStrike`, donc gate (a) FAUX.
    La sous-famille herite par ailleurs `get_Range` = `Nullable` VIDE et `get_Adjacent` = `false`
    d'`APendingAttackEffect`, qui les surcharge : **ni (b) ni (c) sur aucune des 20**.
    Des trois que le port POSE, seul `ValkyrieStrike_Effect` (1022) entre dans la table ci-dessous.
    Les deux autres restent HORS table, et pas par prudence -- par mesure :
      - `MalleusRocketLauncher` (1308) et `DevastatingRefrain_Target` (1402) ont pour `bondedEntity`
        l'owner du cast, c'est-a-dire une MACHINE OF WAR. `--step pendingporteurs` mesure que cette
        entite est de type `Machine`, `pos=None`, absente de `decisionView.units` et cible legale
        d'AUCUNE attaque : sa mort n'est pas atteignable. Le trigger (a) est CONSTRUIT cote natif et
        INATTEIGNABLE -- l'inscrire serait du code que rien ne peut invalider.
      - S'y ajoute une raison structurelle, suffisante a elle seule : leurs call-sites ne passent
        pas `bonded_ref`, donc `BaseEffect.bonded` reste `None` et `matches` rendrait `False`.
        ⚠ Une TROISIEME raison etait invoquee ici -- << ces effets vivent sur des TUILES alors que
        `collect_effect_triggers` itere `effects.by_unit` >> -- et elle est LEVEE
        (#462-r4b-r1-r1-r1-r1-c-r1) : `by_unit` est clee par id d'ENTITE, donc le collecteur voyait
        deja les tuiles ; c'etait le gate d'owner du dispatch, corrige depuis. Le verdict NON
        CONFRONTABLE tenait deja sur chacune des deux autres raisons.
    ⚠ Ces effets ne sont pas pour autant sans retrait : `APendingAttackEffect$$CreateHandleTriggerAbilitiesInternal`
    ajoute son PROPRE `Triggered( On(0x15) & IsTurnOf(<0x758>()), TriggerAbility(...) &
    RemoveEffect(Effect) )` -- le retrait au declenchement de l'attaque differee, qui est un AUTRE
    foyer que celui-ci. Ce foyer-la est le RETRAIT EFFECTIF de ces trois effets, et il MORD :
    mesure du 2026-08-05, un seul `endturn` apres le cast fait disparaitre 1022 de sa tuile SANS
    qu'aucun bonde ne soit mort. C'est ce qui rend le gate (a) doublement sans consequence ici.
  * **`Taunted_BlockMovement` (25) et `Taunted_CantUseAbility` (26)**, enfants du composite 27 : la
    classe native qui les sert n'est pas etablie (le ctor `IdunBattle.Entities.Effects.TauntedEffect$$.ctor`
    ne porte pas d'`EffectType` -- il vient de la lambda d'`IdunBattle.Core.Services.EffectsDatabase$$InitializeEffects`,
    non lue). Les inscrire par ressemblance serait une hypothese, pas une lecture.

================================================================================================
4. LES TRIGGERS (b) ET (c) NE SONT PAS PORTES -- NON CONFRONTES, et voici la raison
================================================================================================
Ils exigent `get_Range.HasValue` (b) ou `get_Adjacent == true` (c). Mesure `--step declared` sur les
37 classes de la famille :

  * (b) arme sur `TauntedEffect`, `Taunted_RefreshUnitTurnFinishedEffect`,
    `BlockUnitMovementBondEffect` et `Idun.Source.IdunBattle.Logic.Entities.Effects.Loki.MindControl_TaunterEffect`
    -- les quatre rendent `Nullable<int>(1)` (corps LUS : `System.Nullable..ctor(&ret, 1)`).
  * (c) arme sur `IdunBattle.Entities.Effects.Loki.HolyDuel_TauntEffect` et sur elle seule.
  * `IdunBattle.Entities.Effects.Loki.HazeOfCorruption_DamageTransferEffect` porte les DEUX en
    CHAMPS (`get_Range` = `this+0x480`, `get_Adjacent` = `this+0x488`) -- et son ctor n'ecrit NI
    l'un NI l'autre, donc `Nullable` vide et `false` : ni (b) ni (c).

Aucun de ces porteurs n'est confrontable sur ce cycle. Le seul que le port POSE est la famille
`Taunted` -- et la mesure `--step gatelive` etablit qu'elle est INOBSERVABLE ici : le taunt de
`CrushingClaws` (1105) est pose avec `TurnsFromRounds(1)` et TOMBE au deuxieme `endturn` SANS QUE
PERSONNE NE BOUGE (sa duree epuise le montage avant que le terme de PORTEE soit exercable ; le
premier jet, qui deplacait le taunte, mesurait en realite la fin de son propre tour). Porter (b) ou
(c) serait donc du code que rien ne peut invalider -- exactement ce que la doctrine proscrit.
NON CONFRONTES : `<klass+0x728> get_Range` et `<klass+0x738> get_Adjacent`.
"""
from __future__ import annotations

from typing import NamedTuple, Optional

from ...state import State
from ...components import UnitComponent
from ...abilities.behaviours import RemoveEffect, entities_from_state
from ....dsl.effects import ExecutionContext
from ....dsl.event_trigger_type import EventTriggerType
from ....entities.effect_type import EffectType
from ....entities.selectors import Caster
from .base import EffectTrigger, TriggerEvent


class BondRemovalGates(NamedTuple):
    """Les virtuels de la classe d'effet NATIVE, tels que
    `probe_462_r4b_r1_r1_r1_r1_bond_removal.py` les a rendus (`--step declared` pour les trois
    premiers, `--step pending` pour le quatrieme).

    `native` = le nom de la classe native, VERBATIM : c'est lui qui rend la ligne re-verifiable
    d'un rejeu du probe, et c'est la seule chose qui relie une valeur a sa mesure."""
    native: str
    remove_on_bonded_entity_death: bool     # `<klass+0x748> get_RemoveOnBondedEntityDeath`
    range: Optional[int]                    # `<klass+0x728> get_Range` -- None = `Nullable` VIDE
    adjacent: bool                          # `<klass+0x738> get_Adjacent`
    # `<klass+0x778> IsExecutedIfOwnerDies` -- N'EXISTE QUE sous
    # `IdunBattle.Entities.Effects.APendingAttackEffect`, qui redefinit
    # `get_RemoveOnBondedEntityDeath` en `NOT <klass+0x778>()` au lieu de rendre une constante.
    # `None` = la classe n'est PAS de cette sous-famille (le gate (a) y est une constante directe).
    # Quand il est renseigne, `remove_on_bonded_entity_death` DOIT en etre la negation --
    # `assert_pending_gate_consistency()` le verifie, pour qu'une des deux valeurs ne puisse pas
    # deriver sans l'autre.
    is_executed_if_owner_dies: Optional[bool] = None


BOND_REMOVAL_GATES: dict[int, BondRemovalGates] = {
    # Pose par `NeuroparasiteAbility$$CreateBehaviour` (#556). Classe native ETABLIE : c'est
    # `NeuroparasiteEffect$$GetIncreaseLevelBehaviour` / `$$GetMaximumLevel` qui portent la montee
    # en niveau de l'effet 1218, mesuree live sur CET effect_type par #556.
    int(EffectType.Neuroparasite): BondRemovalGates(
        "IdunBattle.Entities.Effects.Loki.NeuroparasiteEffect", True, None, False),
    # Pose par `TunnelingHorrorAbility$$ExecuteBehaviour` (#366-r1) sur la TUILE visee,
    # `bondedEntity` = le caster -- qui QUITTE le plateau dans le meme cast
    # (`RemoveUnitFromItsTiles(Caster, true)`, donc `On(0x25 = UnitRemoved)` sur le bonde).
    # `false` n'est donc PAS une valeur inerte : c'est ce qui laisse le marqueur survivre a
    # l'enfouissement du Destroyer. S'il valait `true`, le kit s'auto-detruirait au cast.
    int(EffectType.TunnelingHorror_PendingSummon): BondRemovalGates(
        "IdunBattle.Entities.Effects.Loki.TunnelingHorror_PendingSummonEffect", False, None, False),
    # Pose par `HazeOfCorruptionAbility` (chaine de bonds, #207/#220/#231). `get_Range` et
    # `get_Adjacent` sont ici des CHAMPS (`this+0x480` / `this+0x488`) que
    # `HazeOfCorruption_DamageTransferEffect$$.ctor` n'ecrit PAS -> `Nullable` vide et `false`.
    int(EffectType.HazeOfCorruption_DamageTransfer): BondRemovalGates(
        "IdunBattle.Entities.Effects.Loki.HazeOfCorruption_DamageTransferEffect", True, None, False),
    # Pose par `ValkyrieStrikeAbility$$ExecuteBehaviour` (`caster@0x160` en 4e ET 6e position, donc
    # `bondedEntity` = le caster). SOUS-FAMILLE `APendingAttackEffect` : le gate (a) n'y est pas une
    # constante, c'est `NOT <klass+0x778> IsExecutedIfOwnerDies` -- et ce virtuel vaut VRAI ici, donc
    # `get_RemoveOnBondedEntityDeath` est FAUX et le natif ne construit AUCUN trigger (a). L'entree
    # est dans la table pour DOCUMENTER ce non-retrait ; `bond_removal_registry_entries` n'en tire
    # aucun trigger, exactement comme pour `TunnelingHorror_PendingSummon`.
    # ⚠ C'est la SEULE ligne du fichier confrontee dans le sens << l'effet SURVIT >>
    # (`--step valkyrielive` : bonde mort, 1022 encore present). Elle vaut donc aussi contre-epreuve
    # de la table `TRIVIAL` du probe, par laquelle toutes les autres valeurs sont lues.
    # `get_Range`/`get_Adjacent` sont HERITES d'`APendingAttackEffect`, qui les surcharge en
    # `Nullable` vide et `false` pour ses 20 derivees : ni (b) ni (c) sur toute la sous-famille.
    int(EffectType.ValkyrieStrike_Effect): BondRemovalGates(
        "IdunBattle.Entities.Effects.Loki.ValkyrieStrikeEffect", False, None, False,
        is_executed_if_owner_dies=True),
}


def assert_pending_gate_consistency() -> None:
    """`remove_on_bonded_entity_death == NOT is_executed_if_owner_dies` sur la sous-famille.

    Mirror executable de `APendingAttackEffect$$get_RemoveOnBondedEntityDeath`, dont le corps EST
    cette negation. Sans ce garde, les deux champs pourraient deriver l'un de l'autre au fil des
    editions et la table mentirait sans que rien ne rougisse -- ils sont redondants EXPRES, et
    c'est la redondance qui les garde."""
    for et, g in BOND_REMOVAL_GATES.items():
        if g.is_executed_if_owner_dies is None:
            continue
        attendu = not g.is_executed_if_owner_dies
        if g.remove_on_bonded_entity_death != attendu:
            raise AssertionError(
                "effect_type %d (%s) : get_RemoveOnBondedEntityDeath=%s mais "
                "NOT IsExecutedIfOwnerDies=%s"
                % (et, g.native, g.remove_on_bonded_entity_death, attendu))

_ON_PRE_UNIT_DEATH_2 = int(EventTriggerType.PreUnitDeath_2)      # `On(2)`
_ON_UNIT_REMOVED = int(EventTriggerType.UnitRemoved)             # `On(0x25)`


def bond_removal_tree(effect_type: int) -> RemoveEffect:
    """Arbre du behaviour `IdunBattleLogic.Entities.DSLBehaviors$$RemoveEffect(Effect@0x38)`.

    Frontiere #149 : feuille DECLARATIVE ici, le mutateur
    `IdunBattle.Operations.RemoveEffectOperation` (port : `remove_effect_instance`) EN DESSOUS.
    Le selecteur natif est `Effect@DSLSelectors+0x38` = l'entite-effet COURANTE ; le port n'a que le
    couple (porteur, effect_type), et `Caster()` designe ici le PORTEUR -- meme collapse assume que
    `ChronometronExtraDamageRemove`, legitime par le gate << deja present >> d'`AddEffectOperation`
    qui garantit au plus UNE instance non consommee d'un effect_type par unite.

    Rendu par une USINE et non construit inline : c'est ce qui rend l'arbre INSPECTABLE par un garde
    offline (lecon de #556 §3 -- un garde qui lit le TEXTE d'`execute_behaviour` matche ses propres
    commentaires et ne peut pas rougir)."""
    return RemoveEffect(int(effect_type), Caster())


class BondRemoveOnBondedEntityDeath(EffectTrigger):
    """Trigger (a) d'`ABondEffect$$CreateHandleTriggerAbilitiesInternal`, gate
    `<klass+0x748> get_RemoveOnBondedEntityDeath`.

        Triggered( NOT AmountIsZero(BondedEntityFromEffect(Effect))
                   & ( On(2 = PreUnitDeath_2) | On(0x25 = UnitRemoved) )
                   & IsEntityWithIdTarget(BondedEntityFromEffect(Effect)),
                   RemoveEffect(Effect) )

    Le `CreateTrigger` COLLAPSE imperativement dans `matches` (doctrine #149, comme
    `ChronometronExtraDamageRemove`) ; le behaviour est un ARBRE DSL rendu par
    `bond_removal_tree`.

    UNE SEULE classe pour tous les effect_type, comme le natif : c'est `ABondEffect` -- la BASE --
    qui construit ce `Triggered()` pour toutes ses derivees. L'attribut declaratif `effect_type`
    reste donc a `-1` ; le dispatch (`dispatch/core.py`) fait son lookup sur le `effect_type` de
    l'INSTANCE d'effet, jamais sur celui de la classe de trigger.

    ⚠ L'owner est le PORTEUR de l'effet (vivant), et c'est le BONDE qui est `target` de l'event.
    C'est ce qui fait passer ce trigger a travers le gate << owner vivant >> de `dispatch/core.py`,
    lequel n'a pas d'echappatoire `fire_on_death` sur un `EffectTrigger`."""
    event_id = _ON_PRE_UNIT_DEATH_2
    # `On(2) | On(0x25)` : le dispatch accepte l'entree si `ev.event_id` est `event_id` OU dans
    # `event_ids` -- c'est le seul moyen de mirrorer un `op_BitwiseOr` de deux `On()`.
    event_ids = (_ON_PRE_UNIT_DEATH_2, _ON_UNIT_REMOVED)

    def matches(self, state: State, ev: TriggerEvent) -> bool:
        inst = _bonded_instance(state, int(self.owner_id))
        if inst is None:
            return False
        gates = BOND_REMOVAL_GATES.get(int(inst.effect_type))
        if gates is None or not gates.remove_on_bonded_entity_death:
            return False                        # `<klass+0x748>()` faux -> trigger NON CONSTRUIT
        bonded = getattr(inst, "bonded", None)
        if bonded is None:
            return False
        # `NOT AmountIsZero(BondedEntityFromEffect(Effect))` -- semantique MESUREE : l'entite bondee
        # est encore resoluble dans l'etat (cf. §2 de l'en-tete). Sur les deux vecteurs, l'event
        # part AVANT la consommation des effets, donc le bonde y est encore.
        if state.get_entity(int(bonded)) is None:
            return False
        # `IsEntityWithIdTarget(BondedEntityFromEffect(Effect))` --
        # `IdunBattle.Entities.Triggers.IsEntityWithIdAbilityTrigger$$ShouldTrigger` avec
        # `isOwner = 0` : l'id de l'entite selectionnee doit EGALER celui de la CIBLE de l'event.
        # Les deux vecteurs renseignent bien `target_id` = l'unite qui meurt / est retiree.
        return ev.target_id is not None and int(ev.target_id) == int(bonded)

    def execute_behaviour(self, state: State, ev: TriggerEvent) -> Optional[dict]:
        inst = _bonded_instance(state, int(self.owner_id))
        if inst is None:
            return None
        et = int(inst.effect_type)
        ectx = ExecutionContext(state=state, rng=state.rng)
        bond_removal_tree(et).execute(
            entities_from_state(state, int(self.owner_id), int(self.owner_id)), ectx)
        removed = sum(int(p.get("removed") or 0) for n, p in ectx.emitted if n == "RemoveEffect")
        if not removed:
            return None
        return {"effect": et, "owner": int(self.owner_id), "removed": removed,
                "bonded": int(getattr(inst, "bonded", -1)), "reason": "BondedEntityDeath"}


def _bonded_instance(state: State, owner_id: int):
    """L'instance NON CONSOMMEE, portee par `owner_id`, dont l'`effect_type` est dans la table ET
    dont le gate (a) est arme. `None` sinon.

    Mirror du couple (`Effect@DSLSelectors+0x38`, `ABondEffect$$BondedEntityId`) : le natif tient
    l'entite-effet COURANTE, le port la retrouve par son type sur le porteur."""
    eff = getattr(state, "effects", None)
    if eff is None:
        return None
    for e in eff.by_unit.get(int(owner_id), []):
        if e.consumed:
            continue
        g = BOND_REMOVAL_GATES.get(int(e.effect_type))
        if g is not None and g.remove_on_bonded_entity_death:
            return e
    return None


def bond_removal_registry_entries() -> list[tuple[int, type[EffectTrigger]]]:
    """`(effect_type, classe)` a inscrire dans `EFFECT_TRIGGERS` -- UNIQUEMENT pour les effets dont
    `<klass+0x748>` est VRAI. Une entree a `False` (`TunnelingHorror_PendingSummon`) reste dans la
    table -- elle y DOCUMENTE le non-retrait, et un garde offline peut l'assertionner -- mais
    n'inscrit aucun trigger : cote natif, le `Triggered()` n'entre pas dans l'`ArraySet`."""
    return [(et, BondRemoveOnBondedEntityDeath)
            for et, g in sorted(BOND_REMOVAL_GATES.items())
            if g.remove_on_bonded_entity_death]
