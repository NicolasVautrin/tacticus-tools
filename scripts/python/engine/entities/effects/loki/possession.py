"""Effets de `1101 AttemptedPossession` (`thousSorcerer` << Thaumachus >>, Thousand Sons) -- #590.

DEUX effets natifs, tous deux poses par
`IdunBattleLogic.Entities.Abilities.Active.Loki.AttemptedPossessionAbility$$ExecuteBehaviour` :

  * **1209 `AttemptedPossession_Possessed`** (`0x4b9`) -- l'OWNER-SWAP, pose par `AddBondEffect`
    avec `bondedEntity = Caster` et `turns = <DSLFormulas+0x20 = ConstantAmount(1)>`.
  * **1210 `AttemptedPossession_DmgOverride`** (`0x4ba`) -- l'override de la stat `ATTACK`, pose par
    `AddStatOverrideEffect(..., statType = 0 = ATTACK, amount = <formule>, turns = null,
    isHidden = true)`. Il n'a **AUCUNE classe d'effet propre** dans le binaire (aucun symbole
    `AttemptedPossession_DmgOverride*` -- verifie sur `rnca9r7q6c`) : c'est le `StatOverrideEffect`
    GENERIQUE, dont l'`ApplyInternal`/`RevertInternal` est deja porte par le canal
    `AddStatOverrideEffect` de `runner/abilities/behaviours/stats.py`. Rien a declarer ici.

⚠ **CETTE ABILITY EST UN VRAI OWNER-SWAP, ET C'EST LU -- PAS DEDUIT DU NOM.**
`AttemptedPossession_PossessedEffect$$ApplyInternal` appelle
`IOperationProcessor slot 127 = ChangeUnitOwner(target, casterEntity)` et son `RevertInternal`
`slot 128 = ResetUnitOwner(target)` (slots resolus dans
`data/symbols/<build>/metadata/ioperationprocessor_slots.tsv`). C'est le CONTRE-EXEMPLE de
`1164 MindControl` (meme registre semantique, owner-swap **REFUTE** : son arbre ne contient
ni `OwnerComponent`, ni `ChangeTeam`, ni `PerformAIAction` -- le << controle >> y est un taunt).
Ici les deux appels sont litteralement le corps ENTIER des deux fonctions.

⚠ **LA POSSESSION NE DURE PAS UN TOUR, ELLE DURE UN CAST.** Le `turns = ConstantAmount(1)` du
`AddBondEffect` est un plafond, pas la duree effective : le meme arbre RETIRE l'effet a la fin du
meme `Execute` (`... & RemoveEffect(possedes, 1209)`), apres que le `PerformAIAbility` a fait agir
les unites. La fenetre pendant laquelle une unite ennemie appartient au caster ne contient donc
qu'UNE action IA. Le `turns` natif n'est atteint que si l'effet survit au cast -- ce que le
`RemoveEffect` de queue exclut sur les cibles du cast, mais PAS sur celles que le trigger
`UnitAdded` ci-dessous ajoute apres coup.

RECON i2 (`GC.ability_description("AttemptedPossession")`, verbatim) :
  << Target an enemy within 2 hexes. The target and any Summons it has summoned become possessed
  and immediately perform a normal attack against the closest enemy unit, preferring unpossessed
  targets. Possessed units deal 100% of their own Damage to a maximum of 4001 Damage per hit.
  Possessed Summons will move before attacking. >>
"""
from __future__ import annotations

from ....dsl.event_trigger_type import EventTriggerType
from ...effect_type import EffectType
from ...kill_unit_step import KillUnitStep   # feuille pure (#1088)
from ..base import BaseEffect

#: La cle gameconfig de l'ability 1101.
ATTEMPTED_POSSESSION_ID = "AttemptedPossession"


class AttemptedPossessionPossessedEffect(BaseEffect):
    """`IdunBattle.Entities.Effects.Loki.AttemptedPossession_PossessedEffect` (EffectType
    **0x4b9 = 1209**), un `ABondEffect` pose sur CHAQUE unite possedee, `bondedEntity = le CASTER`.

    MIRROR 1:1 des trois corps natifs :

        $$.ctor              -> ABondEffect..ctor(this, AbilityOrEffect(...), 0)   -- rien de propre
        $$ApplyInternal      -> ChangeUnitOwner( target, state.Get(BondedEntityId(effet)) )
        $$RevertInternal     -> ResetUnitOwner( target )

    donc `overrides_unit_owner() -> True` et RIEN d'autre : cet effet ne modifie AUCUNE stat, ne
    pose AUCUN sous-effet, n'ecrit AUCUNE cible forcee, ne contribue a AUCUN calcul de degat (il
    ne declare ni `CreateEffectDamageBonusForAttack` ni aucun des slots de bonus -- `methods.tsv`
    ne lui connait que `.ctor`, `ApplyInternal`, `RevertInternal` et
    `CreateHandleTriggerAbilitiesInternal`). Toute la puissance de l'ability passe par le SWAP et
    par l'override de degat, qui est un effet SEPARE (1210).

    ⚠ Il n'arme PAS `get_CanBeImmuneTo` (`data/symbols/<build>/metadata/can_be_immune_to.tsv` ne le
    liste pas) : une cible `Immune` peut porter cet effet. Le gate `Immune` de l'ability vit dans
    l'ARBRE (`If(HasTrait(Target, Immune), ...)`) et n'exclut que la CIBLE elle-meme, pas ses
    summons -- lire `attempted_possession_targets()`.

    ⚠ Il SURCHARGE en revanche `IEffect` slot 4 `get_RemoveOnDeathStep` -> `33 c0 c3` =
    `PreUnitRemove` (#1088), et c'est la SEULE classe du build (sur 465) a le faire. La valeur
    coincide avec l'ancien defaut FAUX du port, donc l'ecrire explicitement n'est pas cosmetique :
    sans cette ligne, la correction du defaut (`PreUnitRemove` -> `AfterUnitRemove`) aurait
    silencieusement decale CET effet d'un step. Le sens est net -- la possession se defait AVANT
    tout le reste de la sequence de mort, donc `ResetUnitOwner` rend l'unite a son camp d'origine
    avant que `On(UnitDeath)` ne parte.

    ⚠ **`CreateHandleTriggerAbilitiesInternal` -- la PROPAGATION, portee a part.** Le natif greffe
    sur cet effet un trigger declaratif supplementaire (lu terme a terme) :

        base + [ Triggered(
                   On(0x32 = UnitAdded)
                   & AmountIsZero( Count( Parent(Owner@sel+0x30) ) )     // le porteur n'a pas de parent
                   & AreEqual( Parent(Actor@sel+0x40), Owner@sel+0x30 ), // l'arrivant est SON enfant
                   AddBondEffect( 0x4b9,
                                  abilityState = AbilityStateFromEffect(Effect@sel+0x38),
                                  source       = BondedEntityFromEffect(Effect@sel+0x38),
                                  targets      = Actor@sel+0x40,
                                  bondedEntity = BondedEntityFromEffect(Effect@sel+0x38),
                                  turns        = <DSLFormulas+0x20 = ConstantAmount(1)> ) ) ]

    -- c'est-a-dire : **un summon invoque PENDANT la possession devient possede a son tour**, avec
    le meme caster pour bondedEntity, a condition que son invocateur soit lui-meme un possede de
    premier rang (`Parent(Owner)` vide). Le trigger vit sur l'EFFET, pas sur l'ability : il survit
    donc au `RemoveEffect` de queue pour les enfants poses apres.
    C'est le seul chemin par lequel un `AttemptedPossession_Possessed` dure vraiment `1` tour.
    NON PORTE : residu `#590-r3`. ⚠ **SON `BLOCAGE: etage` ETAIT PERIME, et c'est cette phrase-ci
    qui le portait** -- re-mesure #984 sur le commit courant : les trois etages qu'elle declarait
    manquants EXISTENT tous les trois.
      * le canal EST porte : `EFFECT_TRIGGERS` (`runner/operations/triggers/dispatch/registry.py`),
        consomme par `collect_effect_triggers` (`.../dispatch/core.py`), et il porte DEJA des
        entrees issues d'un `CreateHandleTriggerAbilitiesInternal` (1009 `RangedAutoAttackEffect`,
        `PhoenixGem_CanReviveEffect`) ;
      * la BASE `ABondEffect` est DEJA mirroree -- `runner/operations/triggers/bond_removal.py`
        porte ses trois triggers de retrait ;
      * le vecteur `On(UnitAdded)` n'est pas seulement present, il est VIVANT : `on_unit_added`
        (`runner/operations/spawn.py`) a deja des abonnes portes (`GhostRemoveOnUnitAdded`,
        `ContagionsOfNurgle_AddEffectToNewUnit`, ...).
    Le travail restant est donc **deux entrees de registre**, pas un etage a ouvrir.
    ⚠ **SECOND ECART, que le residu ne nommait pas** : `1209` est absent de `EFFECT_TRIGGERS` **ET**
    de `bond_removal.py` -- il manque donc AUSSI les trois triggers de retrait de bond herites de
    la base, pas seulement la propagation.
    ⚠ **CE QUI RESTE NON PROUVE, et qui interdit de porter a l'aveugle** : `<DSLSelectors+0x40>`
    est une HYPOTHESE ETAYEE (`Actor`), pas une lecture -- `DSLSelectors` expose ses selecteurs
    partages en CHAMPS, et aucun dump de champs n'existe sous `data/symbols/<build>/`. Et les
    VALEURS des trois getters de `ABondEffect` (`+0x748`/`+0x728`/`+0x738`) POUR CET EFFET sont
    inconnues (corps dedupliques, absents de `methods.tsv`), donc lesquels des trois retraits
    s'arment reellement sur 1209 reste a etablir avant de l'inscrire.
    Portee de l'ecart : nulle sur `thousSorcerer`
    tant qu'aucune unite possedee n'invoque pendant sa propre action IA -- regime etroit (il
    faudrait que le moteur d'utilite elise une ability de summon, alors que le `customUtility` de
    l'ability CONTRAINT le choix a une attaque normale sur la cible preferee, cf.
    `runner/abilities/loki/attempted_possession.py`)."""
    # (`effect_type` est un CHAMP d'instance de `BaseEffect`, ecrit a la pose par
    # `AddEffectOperation` -- la classe ne le redeclare pas : meme regime que
    # `MindControlTaunterEffect`. La valeur attendue est `0x4b9 = 1209`.)

    # #1088 -- `IEffect` slot 4 `get_RemoveOnDeathStep` -> `33 c0 c3` = `PreUnitRemove`. SEULE
    # classe du build a surcharger vers cette valeur ; ECRITE explicitement parce qu'elle ne
    # coincide plus avec le defaut de `BaseEffect` (`AfterUnitRemove`).
    remove_on_kill_step = KillUnitStep.PreUnitRemove

    def overrides_unit_owner(self) -> bool:
        """`ApplyInternal` = `ChangeUnitOwner(target, bonded)` / `RevertInternal` =
        `ResetUnitOwner(target)`. Cf. `BaseEffect.overrides_unit_owner`."""
        return True


#: `BaseEffect.On(0x32)` du trigger de propagation -- CITE ici pour que le residu `#590-r3` porte
#: l'evenement exact a brancher, et pour que le nom soit grep-able depuis le vecteur qui l'emet.
POSSESSION_PROPAGATION_EVENT = int(EventTriggerType.UnitAdded)       # 0x32 = 50
