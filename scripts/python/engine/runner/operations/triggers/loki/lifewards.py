"""`Lifewards` (`TriggeredAbilityType.Lifewards` = 0x419 = **1049**) -- passif du summon
`adeptSmnGeminaeSuperia`, **second maillon du kit de `adeptCelestine`**. #963-r3.

i2 (`GeminaeSuperia`) : « When attacked, summons a Geminae Superia in a free adjacent hex, and
immediately triggers its passive ability Lifewards. »

Le premier maillon (`GeminaeSuperiaAbility`, 1048) est porte depuis #963
(`triggers/loki/geminae_superia.py`) et se termine par
`TriggerAbility(<la Geminae posee>, 0x419 = Lifewards)`. Cette feuille rendait `dispatched: False`
faute d'entree au registre : c'est ce module qui la ferme. Sans lui, la Geminae apparait et
n'absorbe RIEN -- Celestine encaisse alors que le natif la laisse a pleine vie.

===================================================================================================
DEUX CLASSES NATIVES, UN SEUL ID -- et la seconde est une voie de SEEDING
===================================================================================================

`TriggeredAbilityType.Lifewards` (1049) est servi par DEUX classes, patron `Vitarus` :

  * `IdunBattleLogic.Entities.Abilities.Triggered.LifewardsAbility` -- le vecteur de COMBAT, porte
    ici ;
  * `IdunBattleLogic.Entities.Abilities.Triggered.LifewardsAddEffectAbility` -- la pose d'INIT.

⚠ **CORRECTION DE NAMESPACE, deja signalee par la fiche et RE-VERIFIEE dans `frida/classes.tsv`** :
les deux vivent sous `...Abilities.Triggered.` **SANS `.Loki`**. Chercher sous `Triggered.Loki`
rend un ensemble VIDE et ferait conclure a tort a une classe introuvable.

⚠ **LE `CreateTrigger` DE LA SECONDE EST ICF-DEDUPLIQUE, ET IL A FALLU LE RESOUDRE SLOT A SLOT.**
Son bloc `methodPointers` du PE porte `[<CreateTrigger>, CreateBehaviour, ...]`, et le premier
pointeur EST le corps nomme `IdunBattleLogic.Entities.Abilities.Active.Loki.
SummaryExecutionAddBaseEffectAbility$$CreateTrigger`, dont le corps ENTIER est
`return <DSLFactory+0x88 = DSLTriggers>+0x30`. Et `IdunBattleLogic.Entities.DSLTriggers$$
InitializeShared` ecrit ce slot verbatim (LU) :

    <DSLTriggers+0x30> = On(0x21 = AbilityInit) & <+0x70 = YesTrigger> & get_OwnerIsActor

C'est donc la branche d'INIT **INCONDITIONNELLE**, que le port materialise par **SEEDING**
(`ABILITY_INIT_OWNER_EFFECTS["Lifewards"]`), exactement comme `AllIsDust` (#1052),
`SynapticInsight` (#1073) et `LegendaryCommander` (#419-...), qui partagent LE MEME corps de
trigger. L'inscrire au vecteur `ability_init_triggers` ferait un DOUBLE FIRE avec ce seed.

    LifewardsAddEffectAbility$$CreateBehaviour =
        If( NOT HasEffect(Owner@<DSLSelectors+0x30>, 0x424, onlyActive: 0, effectTarget: 6),
            AddBondEffect(0x424, get_AbilityStateReference(this),
                          source = Owner@+0x30, targets = Owner@+0x30,
                          bondedEntity = Parent(Owner@+0x30), options = <ZEROEES>) )

-- c'est EXACTEMENT le premier `If` de `LifewardsAbility$$CreateBehaviour` ci-dessous. La pose
d'init n'est donc qu'une pose ANTICIPEE du meme bond ; les deux sont idempotentes par leur propre
gate `NOT HasEffect`.

===================================================================================================
`LifewardsAbility` -- LE DECOMPILE, LU VERBATIM (build `t6dpr4k06g`)
===================================================================================================

    $$CreateTrigger =
        On(0x39 = EventTriggerType.PreDamageTaken)
          & <DSLTriggers+0x70 = YesTrigger>                       <- conjoint NEUTRE
          & ( IsAlive(Owner@<DSLSelectors+0x30>)
              | HasEffect(Owner@+0x30, 0x4d8 = 1240, onlyActive: 0, effectTarget: 6) )
          & AreEqual(Target@<DSLSelectors+0x60>, Parent(Owner@+0x30))
          & IsAdjacent(Owner@+0x30, Target@+0x60, UnitSelectionType.Any = 0)

    $$CreateBehaviour =
        If( NOT HasEffect(Owner@+0x30, 0x424 = 1060, onlyActive: 0, 6),
            AddBondEffect(0x424, get_AbilityStateReference(this), Owner@+0x30, Owner@+0x30,
                          bondedEntity = Parent(Owner@+0x30), <ZEROEES>) )
      & If( NOT HasEffect(Owner@+0x30, 0x4d8 = 1240, onlyActive: 0, 6) & IsAlive(Owner@+0x30),
            AddBondEffect(0x4d8, get_AbilityStateReference(this), Owner@+0x30, Owner@+0x30,
                          bondedEntity = Parent(Owner@+0x30), <ZEROEES>) )
      & TransferDamage( <DSLSelectors+0x48> = Caster,  <+0x60> = Target,  <+0x30> = Owner,
                        <+0x88>, <+0x90> )

LA DISJONCTION DU 2e CONJOINT EST LA MECANIQUE, pas un detail : `IsAlive(Owner) | HasEffect(Owner,
1240)` laisse une Geminae **MORTE** absorber encore un coup, tant qu'elle porte le marqueur 1240 --
lequel est retire au premier `On(0x9 = Attack)` (cf. `LifewardsProtectingEffect`). Rabattre ce
conjoint sur `IsAlive` seul serait RESTRICTIF et silencieux.

⚠ **LE `TransferDamage` N'EST PLUS A PORTER** (MAJ #1020) : la feuille DSL
(`abilities/behaviours/transfer.py`), l'Operation (`operations/transfer_damage.py`, mirror
`IdunBattle.Operations.TransferDamageOperation`) et le canal PENDANT qu'elle consomme
(`HealthComponent.pending_damage` = `FillUpStatComponent+0x64`) sont livres et confrontes live par
`SaviorProtocols`. **La signature est LA MEME, aux cinq selecteurs pres** -- `<+0x48>, <+0x60>,
<+0x30>, <+0x88>, <+0x90>` chez les deux. Ce n'est donc pas une recopie de voisin de forme : c'est
le meme appel natif, argument pour argument.

⚠ **CE N'EST PAS UN BONUS, C'EST UN DEPLACEMENT.** `TransferDamageOperation$$GetDamage` CONSOMME le
`Nullable<DamageAppliedResult>` pose par `ApplyDamageOperation$$Execute` et ECRIT `0` a la place :
le `FillUpStatComponent$$Reduce` qui suit n'enleve plus rien a la victime. Un port qui ajouterait
le degat a la Geminae sans le retirer a Celestine DOUBLERAIT le degat total.

===================================================================================================
CE QUI N'EST PAS PORTE, ET C'EST NOMME
===================================================================================================

  * Les DEUX `AddBondEffect` posent avec `options = <struct ZEROEE>` -> duree par DEFAUT de l'effet
    (`DefaultAmountOfRounds`), mirror de `duration_rounds=None`.
  * `ownerNeedsToBeAlive` du `On(0x39)` : le 2e argument natif n'est pas lisible au pseudo-C ici (le
    ctor est ICF-fondu). Le gate << owner vivant >> du dispatch reste celui du port
    (`CanGetAbilityTrigger`) -- residu PARTAGE avec `GeminaeSuperia` et `SaviorProtocols`, tous deux
    dans le meme cas et tous deux annotes ainsi. Sans consequence observable ici : le vecteur precede
    la mutation des PV, donc la victime est vivante par construction, et le porteur (la Geminae) est
    justement celui dont la mort est ABSORBEE par le 2e conjoint.
  * Les quatre selecteurs que le noeud `TriggerAbility` de `GeminaeSuperia` reconstruit
    (`actor@+0x40`, `caster@+0x48`, `target = Owner@+0x30`, `unitFeetTiles = null`) ne sont pas
    exposes par la feuille portee -- residu PARTAGE par tous ses call-sites, deja nomme dans
    `geminae_superia.py`. Le callable ci-dessous LIT donc l'`AbilityEntities` que la feuille lui
    passe, au lieu de le rebatir a l'aveugle : c'est ce qui rend le chainage fidele malgre ce residu.

  * ⚠ **LA BRANCHE D'INIT DE `LifewardsAddEffectAbility` N'EST PAS SEEDEE, ET C'EST UN ARBITRAGE
    MESURE, PAS UN OUBLI.** Elle poserait 1060 des l'apparition de la Geminae, et le canal de seed
    existe (`ABILITY_INIT_OWNER_EFFECTS`) -- mais `spawn.py::_materialize_owner_effect` construit
    l'instance par `EffectFactory.create({...})` **sans ecrire `bonded`**. Une instance 1060 seedee
    n'aurait donc AUCUN lien vers Celestine, et deux consequences suivraient, toutes deux pires que
    l'abstention :
      1. le gate `NOT HasEffect(Owner, 0x424, onlyActive: 0)` du behaviour verrait cette instance
         SANS LIEN et **bloquerait la pose correcte** au premier coup -- le bond ne serait alors
         JAMAIS lie, offline ;
      2. `BOND_REMOVAL_GATES[1060]` (gate (a), `RemoveOnBondedEntityDeath = true`) lit
         `BaseEffect.bonded` : sur une instance sans lien, `matches` rend `False` et le retrait ne
         mordrait pas -- meme regime que `MalleusRocketLauncher` / `DevastatingRefrain_Target`, deja
         nomme dans `bond_removal.py`.
    CE QUE L'ABSTENTION COUTE, ET POURQUOI C'EST BORNE : la pose survient de toute facon des
    l'apparition de la Geminae, parce que `GeminaeSuperiaAbility$$CreateBehaviour` enchaine
    `Spawn(...) & TriggerAbility(<la Geminae>, Lifewards)` -- donc ce module-ci s'execute dans le
    MEME cast, et pose les deux bonds AVEC leur `bondedEntity`. La branche d'init native est
    redondante avec ce chainage dans le seul scenario ou la Geminae existe. RESIDU : une Geminae
    qui arriverait par une AUTRE voie que son summoner n'aurait pas 1060 avant son premier coup
    encaisse. Fermer ce residu demande d'abord que le seed sache ecrire `bonded`.
"""
from __future__ import annotations

from typing import Optional

from ....state import State
from ....abilities.behaviours.context import entities_from_state
from ....abilities.behaviours.effects import AddBondEffect, RemoveEffect
from ....abilities.behaviours.lifecycle import TRIGGERED_ABILITY_BEHAVIOURS
from ....abilities.behaviours.transfer import TransferDamage
from .....dsl.effects import ExecutionContext
from .....dsl.event_trigger_type import EventTriggerType
from .....entities.behaviours import If, Seq
from .....entities.effect_type import EffectType
from .....entities.selectors.accessors import Actor, Target
from .....entities.selectors.tiles import Caster, Parent
from .....entities.triggered_ability_type import TriggeredAbilityType
from .....entities.triggers import (AreEqual, HasEffect, IsAdjacent, IsAlive, Not, TriggerAnd,
                                    TriggerOr)
from .....entities.unit_selection_type import UnitSelectionType
from ..base import EffectTrigger, TriggeredAbility, TriggerEvent

ABILITY_ID = "Lifewards"
#: `0x419` = 1049 -- l'id que porte `passiveAbilities` d'`adeptSmnGeminaeSuperia`, et l'argument du
#: `TriggerAbility` de `GeminaeSuperiaAbility$$CreateBehaviour`.
LIFEWARDS = TriggeredAbilityType.Lifewards
#: `0x424` = 1060 -- le BOND Geminae <-> Celestine.
BOND_EFFECT = int(EffectType.Lifewards_BondEffect)
#: `0x4d8` = 1240 -- le marqueur qui laisse une Geminae MORTE absorber encore un coup.
PROTECTING_EFFECT = int(EffectType.Lifewards_Protecting)
#: `HasEffect(..., effectTarget = 6)` = `2|4` (owned | targeted) -- cote port les deux branches
#: coincident, l'`EffectsState` etant indexee par ENTITE PORTEUSE.
_EFFECT_TARGET_OWNED_OR_TARGETED = 6
#: `IsAdjacent(Owner@+0x30, Target@+0x60, 0)` du TRIGGER -- `UnitSelectionType.Any`.
#: ⚠ DIFFERE du `3` de `LifewardsBondEffect$$CreateActiveCondition` : les deux sont LUS.
TRIGGER_ADJACENCY_SELECTION = int(UnitSelectionType.Any)

_ON_PRE_DAMAGE_TAKEN = int(EventTriggerType.PreDamageTaken)           # 0x39 = 57
_ON_ATTACK = int(EventTriggerType.Attack)                             # 0x09 = 9


def lifewards_trigger_tree():
    """`LifewardsAbility$$CreateTrigger`, moins le volet `On(0x39)` que porte le DISPATCH et moins
    le conjoint NEUTRE `<DSLTriggers+0x70>` :

        ( IsAlive(Owner@<+0x30>) | HasEffect(Owner@+0x30, 0x4d8, onlyActive: 0, 6) )
          & AreEqual(Target@<+0x60>, Parent(Owner@+0x30))
          & IsAdjacent(Owner@+0x30, Target@+0x60, 0)

    `<DSLTriggers+0x70>` est le **YesTrigger** -- la constante VRAIE que `DSLTriggers` construit une
    fois et re-cite partout (`AOwnerEffectTriggeredAbility$$CreateCondition` la rend TELLE QUELLE, et
    `InitializeShared` l'utilise comme conjoint neutre dans `<+0x30>` et `<+0x38>`). L'omettre est
    value-preserving ; l'ecrire serait du bruit.

    `Owner@<DSLSelectors+0x30>` est rendu par `Caster()` cote port : pour une `BaseTriggeredAbility`,
    `Owner == Caster` (meme convention que `geminae_superia.py` et `savior_protocols.py`).

    ZERO tirage PRNG -- contrairement a `SaviorProtocols`, il n'y a AUCUN `Maybe` ici, ni dans le
    trigger ni dans le behaviour : Lifewards absorbe a coup SUR."""
    alive_or_protecting = TriggerOr(
        IsAlive(Caster()),
        HasEffect(Caster(), PROTECTING_EFFECT, active_only=False))
    t = TriggerAnd(alive_or_protecting, AreEqual(Target(), Parent(Caster())))
    return TriggerAnd(t, IsAdjacent(Caster(), Target(), TRIGGER_ADJACENCY_SELECTION))


def _add_bond(effect_type: int, name: str) -> AddBondEffect:
    """Une des deux feuilles `AddBondEffect` du behaviour -- MIRROR 1:1 :

        AddBondEffect(<effectType>, get_AbilityStateReference(this),
                      source = Owner@<+0x30>, targets = Owner@+0x30,
                      bondedEntity = Parent(Owner@+0x30), options = <ZEROEES>)

    `source` ET `targets` valent tous deux `Owner` (le natif passe DEUX FOIS le meme selecteur) ;
    seul `bondedEntity` differe -- c'est `Parent(Owner)`, donc CELESTINE. C'est ce lien que
    `ABondEffect$$BondedEntityId` relit, et que `BOND_REMOVAL_GATES[1060]` consomme pour son
    gate (a) (`RemoveOnBondedEntityDeath = true`, MESURE : cf. `entities/effects/loki/lifewards.py`).

    `options = <struct ZEROEE>` -> `duration_rounds=None` = duree par DEFAUT de l'effet
    (`DefaultAmountOfRounds`), et NON une duree d'un round."""
    return AddBondEffect(effect_type, name, Caster(), Caster(),
                         duration_rounds=None, bonded_ref=Parent(Caster()))


def lifewards_behaviour_tree(*, transfer_ability=None, attack_ability=None):
    """`LifewardsAbility$$CreateBehaviour` -- MIRROR 1:1, les trois termes composes par
    `op_BitwiseAnd` (donc `Seq`, qui execute GAUCHE puis DROITE) :

        If(NOT HasEffect(Owner, 0x424, onlyActive: 0, 6), AddBondEffect(0x424, ...))
      & If(NOT HasEffect(Owner, 0x4d8, onlyActive: 0, 6) & IsAlive(Owner), AddBondEffect(0x4d8, ...))
      & TransferDamage(<+0x48>, <+0x60>, <+0x30>, <+0x88>, <+0x90>)

    ⚠ L'ORDRE EST LOAD-BEARING, et il est celui du natif : les deux poses PRECEDENT le transfert.
    Le second `If` exige `IsAlive(Owner)` alors que le premier ne l'exige pas -- lu, pas harmonise :
    une Geminae morte garde son BOND mais ne re-obtient pas son marqueur de protection.

    ⚠ `onlyActive = 0` sur les deux `HasEffect` : une instance INERTE (bond dont la condition
    d'adjacence est fausse) compte comme << deja presente >> et bloque la re-pose. C'est le 4e
    argument du noeud porte (`active_only=False`), pas son 3e (`min_level`, filtre propre au port).

    Les selecteurs du `TransferDamage`, identiques a ceux de `SaviorProtocols` :
    `Caster@<+0x48>` = la SOURCE du degat = `Actor()` cote port ; `Target@<+0x60>` = la VICTIME
    (Celestine) ; `Owner@<+0x30>` = le PROTECTEUR (la Geminae) = `Caster()` cote port."""
    pose_bond = If(Not(HasEffect(Caster(), BOND_EFFECT, active_only=False)),
                   _add_bond(BOND_EFFECT, EffectType.Lifewards_BondEffect.name), None)
    pose_protecting = If(
        TriggerAnd(Not(HasEffect(Caster(), PROTECTING_EFFECT, active_only=False)),
                   IsAlive(Caster())),
        _add_bond(PROTECTING_EFFECT, EffectType.Lifewards_Protecting.name), None)
    transfer = TransferDamage(caster_sel=Actor(),
                              original_target_sel=Target(),
                              transfer_targets_sel=Caster(),
                              transfer_ability=transfer_ability,
                              attack_ability=attack_ability)
    return Seq(Seq(pose_bond, pose_protecting), transfer)


def _execute_lifewards(state: State, owner_id: int, entities, ectx) -> Optional[dict]:
    """Le corps du behaviour, PARTAGE par les deux voies d'entree -- le vecteur `On(0x39)` et le
    declenchement DIRECT par le noeud `TriggerAbility` de `GeminaeSuperiaAbility`.

    Rend le payload de diagnostic ; `None` seulement si l'etat ne permet aucune pose."""
    if state is None or owner_id is None:
        return None
    lifewards_behaviour_tree(
        transfer_ability=getattr(state, "triggering_ability", None),
        attack_ability=getattr(entities, "attack_ability_type", None)).execute(entities, ectx)
    posed = [p for (n, p) in ectx.emitted if n == "AddBondEffect"]
    transfers = [p for (n, p) in ectx.emitted if n == "TransferDamage"]
    return {"passive": ABILITY_ID, "owner": int(owner_id),
            "bonds": posed,
            "transfers": transfers,
            "transferred": bool(transfers and any(t.get("result") for t in transfers)),
            "dsl": True}


class LifewardsAbility(TriggeredAbility):
    """`LifewardsAbility` (`TriggeredAbilityType` 0x419 = 1049) -- cf. l'en-tete du module.

    `On(0x39 = PreDamageTaken) & (IsAlive(Owner) | HasEffect(Owner, 1240))
     & AreEqual(Target, Parent(Owner)) & IsAdjacent(Owner, Target)`
    -> `If(...) AddBondEffect(1060) & If(...) AddBondEffect(1240) & TransferDamage(source, Celestine,
       la Geminae)`.

    OBSERVABLE : un coup destine a Celestine est DEPLACE sur la Geminae adjacente."""
    event_id = _ON_PRE_DAMAGE_TAKEN
    TRIGGERED_ABILITY_ID = int(TriggeredAbilityType.Lifewards)        # 0x419 = 1049

    def matches(self, state: State, ev: TriggerEvent) -> bool:
        """`CreateTrigger` moins le volet `On(0x39)` du dispatch.

        `self.owner_id` est la GEMINAE (`Owner@+0x30`) ; `ev.target_id` la VICTIME du coup, que le
        3e conjoint contraint a etre `Parent(Owner)`, c.-a-d. Celestine ; `ev.actor_id` la source du
        degat, lue seulement par le behaviour."""
        if ev.target_id is None:
            return False
        entities = entities_from_state(state, self.owner_id, ev.target_id, actor_id=ev.actor_id)
        return bool(lifewards_trigger_tree().evaluate(entities))

    def execute_behaviour(self, state: State, ev: TriggerEvent) -> Optional[dict]:
        ectx = ExecutionContext(state=state, rng=state.rng)
        from dataclasses import replace                              # noqa: PLC0415
        entities = entities_from_state(state, self.owner_id, ev.target_id, actor_id=ev.actor_id)
        # `<DSLSelectors+0x90>` = `TriggeringAbilitySelector` = `AbilityEntities+0x98`, que le
        # publieur d'`On(0x39)` a rempli depuis la `DamageSource` du coup. MEME canal que
        # `savior_protocols.py`, dont ce `TransferDamage` partage la signature.
        entities = replace(entities, attack_ability_type=ev.triggering_effect)
        return _execute_lifewards(state, self.owner_id, entities, ectx)


def _lifewards_triggered_directly(state: State, owner_id: int,
                                  entities=None, ectx_appelant=None) -> Optional[dict]:
    """Entree de `TRIGGERED_ABILITY_BEHAVIOURS[1049]` -- le callable que le noeud DSL
    `TriggerAbility` de `GeminaeSuperiaAbility$$CreateBehaviour` invoque, unite par unite.

    ⚠ **CE CALL-SITE CONSOMME `entities`, contrairement a `FullThrottle`, et c'est LU** : le noeud
    natif reconstruit son `AbilityEntities` depuis ses quatre selecteurs, et `GeminaeSuperia` y
    passe `actor = Actor@<+0x40>, caster = Caster@<+0x48>, target = **Owner@<+0x30>**` -- donc
    CELESTINE en cible. Rebatir a l'aveugle un contexte `Caster == Target == la Geminae` ferait
    echouer le `TransferDamage` (il n'y aurait aucune victime distincte) et rendrait le chainage
    INERTE, sans erreur.

    Le seul slot a REECRIRE est l'`Owner`/`Caster` : `BaseTriggeredAbility$$Execute` l'ecrit avec
    l'unite DECLENCHEE (la Geminae), la ou l'`entities` du noeud porte encore le caster de
    `GeminaeSuperia`. Le port le fait en rebatissant depuis `state` avec les slots LUS du contexte
    recu -- jamais en devinant.

    `ectx_appelant` est REUTILISE quand il existe : le natif execute dans le MEME processeur
    d'operations, donc les evenements du transfert appartiennent au cast en cours."""
    if state is None or owner_id is None:
        return None
    tgt = (getattr(entities, "target", None) or {}).get("id") if entities is not None else None
    act = (getattr(entities, "actor", None) or {}).get("id") if entities is not None else None
    ents = entities_from_state(state, int(owner_id), tgt, actor_id=act)
    if entities is not None:
        from dataclasses import replace                              # noqa: PLC0415
        ents = replace(ents, attack_ability_type=getattr(entities, "attack_ability_type", None))
    ectx = ectx_appelant if ectx_appelant is not None else ExecutionContext(state=state,
                                                                           rng=state.rng)
    return _execute_lifewards(state, int(owner_id), ents, ectx)


TRIGGERED_ABILITY_BEHAVIOURS[int(LIFEWARDS)] = _lifewards_triggered_directly


class LifewardsProtectingRemove(EffectTrigger):
    """`LifewardsProtectingEffect$$CreateRemoveEffectTrigger` = `On(0x9 = Attack,
    ownerNeedsToBeAlive: 0)` -> `BaseEffect$$GetRemoveEffectBehaviour` = `RemoveEffect(<cette
    instance>)`.

    Corps ENTIER du natif : UN seul noeud, AUCUN conjoint -- pas de `get_OwnerIsCaster`, pas de
    `get_OwnerIsTarget`. **N'IMPORTE QUELLE attaque** retire le marqueur de n'importe quel porteur.
    C'est ce qui borne la protection posthume d'une Geminae morte a UN seul coup.

    ⚠ Ne pas recopier le gate `get_OwnerIsCaster` de son voisin de forme `ShockAssaultBuffRemove` :
    il n'est PAS dans ce corps-ci, et l'ajouter rendrait le marqueur quasi-permanent (une Geminae
    morte n'attaque plus jamais).

    COLLAPSE ASSUME, identique a celui de `ShockAssaultBuffRemove` : le natif retire **l'instance**,
    le port retire tous les 1240 non consommes du porteur (`RemoveEffect(effectType, Caster())`, la
    seule forme portee). Le gate << deja present >> d'`AddEffectOperation` garantit au plus UNE
    instance de 1240 par unite -> les deux formes coincident."""
    event_id = _ON_ATTACK
    effect_type = PROTECTING_EFFECT

    def execute_behaviour(self, state: State, ev: TriggerEvent) -> Optional[dict]:
        ectx = ExecutionContext(state=state, rng=state.rng)
        entities = entities_from_state(state, self.owner_id, ev.target_id, actor_id=ev.actor_id)
        RemoveEffect(PROTECTING_EFFECT, Caster()).execute(entities, ectx)
        return {"effect": EffectType.Lifewards_Protecting.name, "owner": int(self.owner_id),
                "removed": any(n == "RemoveEffect" for n, _ in ectx.emitted), "dsl": True}
