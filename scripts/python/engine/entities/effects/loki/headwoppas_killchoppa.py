"""`HeadwoppasKillchoppa` -- la relique `R_Crit_HeadwoppasKillchoppa` d'`orksWarboss` << Gulgortz >>
(Orks, HERO, AU POOL rank 17) et son owner-effect d'AURA a NIVEAU. Tache #1012-r1.

**AUCUN texte i2 n'existe pour cette ability** (ni `_CurrentLevelDescription`, ni
`_NextLevelDescription`) : seul `Items/R_Crit_HeadwoppasKillchoppa_name` est traduit. Tout ce qui
suit est LU au decompile du build `rnca9r7q6c`, sans aucun appui sur un tooltip.

gameconfig : `variables.extraDmg` = 10 paliers de RELIQUE (195 -> 290),
`constants.unitId = "orksNpc2OrkBoy"`.

================================================================================================
IDENTITE -- deux enums, deux ordinaux
================================================================================================

    TriggeredAbilityType  0x60d = 1549 = HeadwoppasKillchoppa            <- l'ABILITY (la relique)
    EffectType            0x620 = 1568 = HeadwoppasKillchoppa_ExtraDmg   <- l'EFFET pose sur elle

L'appariement ability -> config est LU AUX OCTETS, parce que le pseudo-C le perd (le littéral part
par `edx`). `IdunBattle.Entities.Effects.Loki.HeadwoppasKillchoppaEffect$$.ctor` :

    ba 0d 06 00 00      mov  edx, 0x60d = 1549      <- AbilityOrEffect(HeadwoppasKillchoppa)
    e8 <rel32>          call IdunBattle.Core.AbilityOrEffect$$op_Implicit
    41 b0 01            mov  r8b, 1                 <- hasAutomaticActivation
    e8 <rel32>          call IdunBattle.Entities.Effects.BaseEffect$$.ctor

=> la config lue par TOUS les `ConfigVar` de l'effet est celle de la RELIQUE (10 paliers), jamais
une config d'active.

================================================================================================
1. LA POSE -- owner-effect a l'init, **AU NIVEAU 0**
================================================================================================

`IdunBattleLogic.Entities.Abilities.Triggered.Loki.HeadwoppasKillchoppaAbility$$CreateTrigger` --
ABSENT des deux tables, corps DEDUPLIQUE ; appartenance etablie slot a slot dans le bloc
`methodPointers` (meme methode que #916 / #910), corps GENERIQUE
`OnOwnerSpecificAbilityInit( this.<AbilityType> )`.

`...HeadwoppasKillchoppaAbility$$CreateBehaviour` ::

    AddEffect( 0x620 = 1568 HeadwoppasKillchoppa_ExtraDmg,
               abilityState = BaseTriggeredAbility$$get_AbilityStateReference,
               source  = Owner@DSLSelectors+0x30,
               targets = Owner@DSLSelectors+0x30,
               options = Nullable<AddEffectBehaviourOptions>{ +0x00 = null,
                                                              +0x08 = null,
                                                              +0x10 = <DSLFormulas+0x18> } )

⚠ **LA FOURCHE DE #1012-r1 EST TRANCHEE AU DECOMPILE, PAS AU LIVE** -- le 3e champ des `options`
est le **NIVEAU INITIAL**, pas la duree, et les deux etages qui le disent sont NOMMES :

  a) `IdunBattle.Entities.Behaviours.AddEffectBehaviour$$.ctor` recopie les trois champs du
     `Nullable` a `this+0x70 / +0x78 / +0x80` ; `...AddEffectBehaviour$$Execute` evalue `+0x78` en
     `AddEffectOptions+0x00` et `+0x80` en `AddEffectOptions+0x10` -- **et pose `1` par defaut**
     quand `+0x80` est nul (`uVar6 = 1` avant le test) ;
  b) `IdunBattle.Operations.AddEffectOperation$$Execute` consomme cette struct champ par champ :
     `+0x00` est la DUREE (repli sur
     `idun.Idun.Source.Shared.Battle.StaticBattleRules.StaticBattleRules.Effect$$DefaultAmountOfRounds`
     quand il est nul), `+0x08` est l'effet BONDE, et `+0x10` -- redefaute a `1` -- est ecrit dans
     `EffectComponent+0x68`, **le NIVEAU** (`+0x58` recevant l'`effectType` juste avant).

Et `IdunBattleLogic.Entities.DSLFormulas$$.ctor` donne le scalaire : `+0x18` = `Direct(0)`,
`+0x20` = `Direct(1)`, `+0x28` = `Direct(2)`, `+0x30` = `Direct(100)`, `+0x38` = `Direct(-1)`.

=> **l'effet naît au NIVEAU 0, sans duree (donc permanent)**. Sa `CreateActiveCondition`
`AmountIsGreaterThanZero(EffectLevel)` n'est donc PAS mort-nee : elle tient l'effet INACTIF tant
que Gulgortz n'a rien abattu. (La mesure live `decisionView.effects` + `includeInactive` que la
case-doc proposait reste un CONTROLE, elle n'est plus l'arbitre.)

================================================================================================
2. QUI EN BENEFICIE -- `HeadwoppasKillchoppaEffect$$CreateTargetSelector`
================================================================================================

    Owner@DSLSelectors+0x30
  + Friends( Owner@+0x30,
             Friends( Owner@+0x30,
                      UnitsWithVisualId( ConfigConstString( TriggeredAbilityConfigId(0x60d), 0 ),
                                         1 = UnitSelectionType.OnlyAlive ),
                      3 = UnitSelectionType.OnlyAliveAndTargetable ),
             3 = UnitSelectionType.OnlyAliveAndTargetable )

⚠ **DEUX corrections a la RE ecrite dans `docs/rl/case-1012-reliques-tau-et-orks.md` SS 2.2**,
toutes deux relues aux OCTETS de `...HeadwoppasKillchoppaEffect$$CreateTargetSelector` :

  1. le `Friends` est appele **DEUX FOIS**, imbrique (deux `call` distincts vers la meme cible
     `IdunBattleLogic.Entities.DSLSelectors$$Friends`, aucun `je` ne saute par-dessus l'un des
     deux). Le filtre est IDEMPOTENT -- filtrer deux fois << ami de Owner >> rend le meme
     ensemble -- donc l'observable est identique ; c'est ecrit ici parce que le decompile
     l'ecrit, pas parce que ca change un resultat ;
  2. le 3e argument de `Friends` n'est **PAS** un `UnitTeamSelectionType` (#963-r1, qui n'a que
     `0 = ByCurrentTeam` et `1 = ByOriginalTeam`, donc pour qui `3` n'existe pas) : le TYPE
     DECLARE, LU dans `data/symbols/<build>/frida/methods.tsv`, est
     `DSLSelectors.Friends(of, entities, selectionType:IdunBattle.Entities.Enum.UnitSelectionType)`
     -- et `UnitSelectionType 3 = OnlyAliveAndTargetable`. Meme lecture pour le `1` de
     `UnitsWithVisualId(unitId, selectionType:UnitSelectionType)` = `OnlyAlive`.

⚠ **IL N'Y A QU'UNE INSTANCE D'EFFET, ET C'EST CE QUI DECIDE DU COMPTEUR.** `AddEffect` pose
l'effet sur `targets = Owner` -- une seule cible, Gulgortz. `CreateTargetSelector` n'est PAS un
selecteur de POSE : c'est celui des unites AFFECTEES, evalue par
`IdunBattle.Entities.Effects.BaseEffect$$GetTargets` (qui met en cache
`CreateTargetSelectorAndCache` en `this+0xa0`, puis retranche `UnitsWithTrait(.., 0x1b, 3)` quand
le slot de vtable `+0x4d8` est faux). Le patron est exactement celui de `NornCrownEffect` (#1011),
dont la face AURA est CONFRONTEE live.

=> **la case-doc se trompe** en ecrivant << chaque recipiendaire a SA propre instance, dont
l'`Owner` est LUI ; un Ork Boy qui tue monte SON niveau >>. Il n'existe qu'une instance, portee
par Gulgortz ; `IncreaseEffectLevel(Owner@+0x30, ...)` descend a
`DSLSelectors$$EffectFromOwner(owner, effectType)`, donc **seuls les kills du PORTEUR montent le
niveau**, et ce niveau unique sert Gulgortz ET ses Ork Boyz.

================================================================================================
3. CE QU'ILS GAGNENT -- `$$CreateEffectDamageBonusForAttack`
================================================================================================

    EffectBonus.ForAddition( IsMeleeAttack & get_OwnerIsCaster, GetCurrentDamageBonus() )

    ...$$GetCurrentDamageBonus =
        Multiply( ConfigVar( 0x8 = extraDmg, GetAbilityState(this), <config@this+0x60> ),
                  EffectLevel( Effect@DSLSelectors+0x38 ) )

    ...$$GetCurrentDamageBonusMultiplier = EffectLevel( Effect@+0x38 )   # sans ConfigVar

    ...$$CreateActiveCondition = AmountIsGreaterThanZero( EffectLevel( Effect@+0x38 ) )

Canal : additif ATTAQUANT (`IdunBattle.Core.Services.DamageModifiers$$Add`), meme famille que
`FuelledByFury_ExtraDamage`, `BeaconOfRage_FriendlyExtraDamage` et `ModifiedExoarmour_ExtraDmg`.
AUCUN `IsNormalAttack` -> le bonus vaut aussi pour les attaques d'ABILITY, tant qu'elles sont
melee.

⚠ **LE NIVEAU EST CELUI DE LA RELIQUE, PAS DU PASSIF** (#357) -- `GetAbilityState(this)` rend
l'`AbilityState` BAKE a la pose, donc l'etat **TERTIAIRE**. Lire `self.ability_level` rendrait le
niveau PASSIF (50 sur tout runner normalise), donc `extraDmg[10] = 290` au lieu du palier equipe :
la meme faute de +49 % que #357 et #1011 ont fermee. Foyer UNIQUE :
`runner/operations/triggers/base.py::triggered_ability_state`, expose sous
`tertiary_ability_state_of`.

================================================================================================
4. LE COMPTEUR -- `$$CreateHandleTriggerAbilitiesInternal`
================================================================================================

    ArraySet{ DSLFactory.Triggered(
        trigger   = BaseEffect$$On( 0x36 = 54 EventTriggerType.UnitDefeated )
                  & NOT IsSteppableUnit( Targets@DSLSelectors+0x60 )
                  & AreEqual( DSLSelectors$$Attacker(), Owner@+0x30 ),
        behaviour = IncreaseEffectLevel( Owner@+0x30, <this.effectType @+0x10>,
                                         amount = null, max = null ),
        null ) }

`amount = null` retombe sur `<DSLFormulas+0x20>` = `Direct(1)` (lu dans
`IdunBattleLogic.Entities.DSLBehaviors$$IncreaseEffectLevel`, qui substitue le champ quand
l'argument est nul) ; `max = null` desactive le clamp d'
`IdunBattle.Operations.IncreaseEffectLevelOperation$$Execute` -- **aucun cap**, contrairement a
`Neuroparasite` (`$$GetMaximumLevel`). Le port de ce trigger vit dans
`runner/operations/triggers/loki/headwoppas_killchoppa.py`.
"""
from __future__ import annotations

from collections.abc import Mapping

from ....services.effect_bonus import EffectBonus, for_addition
from ..base import BaseEffect, is_melee_attack
from ..magnitude import ability_const_str, ability_var
import engine.entities.effects.ctx_keys as _ctx_keys      # #1042-r5 : foyer UNIQUE des chaines de cle de ctx

#: `TriggeredAbilityType` 0x60d = 1549 -- la config lue par `ConfigVar` (celle de la RELIQUE),
#: etablie par le `mov edx, 0x60d` du `.ctor` (cf. en-tete).
HEADWOPPAS_KILLCHOPPA_ABILITY = "HeadwoppasKillchoppa"
#: `AbilityVariableType` 0x8 -- la variable multipliee par le niveau de l'effet.
_VAR_EXTRA_DMG = "extraDmg"
#: `ConfigConstString( TriggeredAbilityConfigId(0x60d), 0 )` = `constants.unitId` de la relique.
#: ⚠ C'est un **visualId**, pas un `unitId` : le natif le passe DIRECTEMENT a `UnitsWithVisualId`,
#: sans le `VisualUnitIdFromUnitId` que `PhasalSubjugator_SummonAbility$$CreateTrigger` interpose.
_CONST_UNIT_ID = "unitId"
#: callable `(owner_id, ability_name) -> (level, multiplier)` -- mirror de `GetAbilityState(this)`
#: (#357). Meme cle et meme semantique que `NornCrownEffect` / `RelicBoltPistol*Effect` : le foyer
#: UNIQUE `runner/operations/triggers/base.py::triggered_ability_state`.
CTX_ABILITY_STATE_OF = _ctx_keys.CTX_TERTIARY_ABILITY_STATE_OF
#: `visualId` de l'unite qui ATTAQUE -- substrat d'`UnitsWithVisualId` pour la patte AURA.
#: Tri-etat : `None` = canal NON MESURE (le gate se tait), jamais << mauvais visualId >>.
CTX_ATT_VISUAL_ID = "att_visual_id"


def _beneficiary_visual_id() -> "str | None":
    """`ConfigConstString( TriggeredAbilityConfigId(0x60d), 0 )` -- lu au gameconfig par le foyer
    partage `magnitude.ability_const_str`, jamais ecrit en dur ici (la constante est une donnee de
    build : la coder en dur en ferait une fausse verite au prochain build)."""
    v = ability_const_str(HEADWOPPAS_KILLCHOPPA_ABILITY, _CONST_UNIT_ID)
    return str(v) if v else None


class HeadwoppasKillchoppaExtraDmgEffect(BaseEffect):
    """`HeadwoppasKillchoppa_ExtraDmg` (`EffectType` 0x620 = 1568) -- owner-effect PERMANENT de la
    relique `HeadwoppasKillchoppa` (`TriggeredAbilityType` 0x60d = 1549), pose sur `orksWarboss`
    << Gulgortz >> a l'init **au niveau 0**, et projete sur ses Ork Boyz allies (`visualId` =
    `constants.unitId`) : leurs attaques de MELEE gagnent `extraDmg x <niveau de l'effet>` en
    additif ATTAQUANT. Le niveau monte de +1 a chaque unite non-`Steppable` abattue par le
    PORTEUR (cf. en-tete SS 4), sans cap.

    DEUX pattes DISJOINTES, parce que le selecteur natif porte `Owner` comme PREMIER terme :
      * `create_effect_damage_bonus_for_attack`    -- le PORTEUR attaque (aucun gate de visualId :
        le terme `Owner` du selecteur est inconditionnel) ;
      * `create_aura_attack_damage_bonus_for_ally` -- un Ork Boy allie attaque.
    Les agregateurs d'aura excluent deja `uid == att_id` : ni trou, ni double-compte."""

    # `CreateActiveCondition` = `AmountIsGreaterThanZero(EffectLevel)`. Le flag `IsActive` capte
    # decrit l'etat REEL ; la magnitude etant `V x level`, un niveau 0 rend l'effet inerte tout
    # seul -- mais le natif ECRIT la condition, donc on la mirroire.
    active_condition_ported = True

    def is_active(self, unit_state=None) -> bool:
        """`HeadwoppasKillchoppaEffect$$CreateActiveCondition` =
        `AmountIsGreaterThanZero( EffectLevel(Effect@+0x38) )`.

        ⚠ Consequence de la fourche tranchee en SS 1 : l'effet naît au niveau **0**, donc INACTIF.
        Le canal `decisionView` par defaut ne publie pas les effets inactifs -- un montage qui
        veut l'observer AVANT le premier kill doit demander `includeInactive`.

        ⚠ **`level` ABSENT vaut 0 ICI, et c'est l'inverse du tri-etat habituel.** Le seed offline
        (`runner/operations/spawn.py::_materialize_owner_effect`) cree l'instance sans niveau ; pour
        CET effet la seule valeur qu'une POSE puisse produire est `Direct(0)`, lue au decompile --
        donc << non publie >> y designe le niveau initial, pas une ignorance. Se taire (rendre
        `True`) ferait au contraire naître l'effet ACTIF, ce que le natif ne fait jamais. La
        degradation est RESTRICTIVE et nommee ; le compteur, lui, n'est pas gele : le dispatch des
        `EFFECT_TRIGGERS` (`triggers/dispatch/core.py::collect_effect_triggers`) ne filtre que
        `consumed`, jamais `is_active` -- exactement comme le rail natif
        `EvaluateTriggerOperation$$EvaluateEffectTriggerEffectAbilities`, qui n'accede pas a
        `EffectComponent+0x5c`."""
        return int(self.level or 0) > 0

    def _amount(self, ctx: "Mapping | None", owner_id) -> "int | None":
        """`GetCurrentDamageBonus` = `Multiply( ConfigVar(0x8 = extraDmg, GetAbilityState(this)),
        EffectLevel(Effect@+0x38) )`.

        `MultiplyAmount$$Calculate` est un produit d'ENTIERS (cf. `ModifiedExoarmour`, case-322) :
        `ability_var` rend deja l'entier arrondi par
        `AbilityConfiguration$$TryGetVariableArrayForLevel`, on ne re-arrondit rien.

        Le niveau d'ABILITY est le TERTIAIRE (#357). Canal absent (contexte offline, probe) ->
        repli NOMME sur les niveaux que l'instance porte deja, exactement celui de
        `NornCrownEffect._amount` et de `RelicBoltPistol*Effect._ability_state` : il clampe au
        dernier palier, ce n'est pas un choix mais une degradation declaree."""
        lvl_eff = self.level                       # EffectLevel -- le compteur de kills
        if not lvl_eff or int(lvl_eff) <= 0:
            return None
        c = ctx or {}
        fn = c.get(CTX_ABILITY_STATE_OF)
        lvl = mult = None
        if fn is not None and owner_id is not None:
            lvl, mult = fn(owner_id, HEADWOPPAS_KILLCHOPPA_ABILITY)
        if lvl is None:
            lvl = self.ability_level if self.ability_level is not None else self.level
            mult = self.ability_variables_multiplier
        per = ability_var(HEADWOPPAS_KILLCHOPPA_ABILITY, _VAR_EXTRA_DMG, lvl,
                          multiplier_pct=int(mult if mult is not None else 100))
        if not per:
            return None
        return int(per) * int(lvl_eff)

    def create_effect_damage_bonus_for_attack(self, is_ranged: "bool | None" = None,
                                              has_moved: "bool | None" = None,
                                              target_traits=None,
                                              is_prediction: bool = False,
                                              is_normal_attack: "bool | None" = True,
                                              target_armor_reduced: "bool | None" = None,
                                              att_ctx=None) -> "EffectBonus | None":
        """PATTE SELF -- le PORTEUR attaque. Le premier terme du `CreateTargetSelector` est
        `Owner@+0x30` NU : le porteur est beneficiaire sans condition de `visualId`.

        Gates natifs, et RIEN d'autre (les callees du decompile sont exactement
        {`IsMeleeAttack`, `get_OwnerIsCaster`, `op_BitwiseAnd`, `GetCurrentDamageBonus`,
        `ForAddition`, `Nullable..ctor`}) :
          * `IsMeleeAttack` -- gate PARTAGE `is_melee_attack(is_ranged)` : nature non prouvee
            melee => aucune contribution ;
          * `get_OwnerIsCaster` -- VRAI par construction sur ce canal
            (`entities/effects/__init__.py::_attacker_effect_bonuses` n'itere que les effets de
            l'ATTAQUANT).
        AUCUN `IsNormalAttack`, AUCUN gate sur la cible."""
        if not is_melee_attack(is_ranged):                       # IsMeleeAttack
            return None
        c = att_ctx or {}
        amt = self._amount(c, c.get("att_id"))                   # sur ce canal, l'attaquant EST le porteur
        return for_addition(True, int(amt)) if amt else None

    def create_aura_attack_damage_bonus_for_ally(self, ctx: "Mapping | None" = None) -> "EffectBonus | None":
        """PATTE AURA -- un Ork Boy allie attaque. Mirror du second terme du
        `CreateTargetSelector` (`Friends(Owner, UnitsWithVisualId(<constants.unitId>, OnlyAlive),
        OnlyAliveAndTargetable)`), puis du trigger de `$$CreateEffectDamageBonusForAttack`.

        Tri-etat sur `att_visual_id` : canal NON MESURE -> aucune contribution, jamais un gate
        permissif."""
        c = ctx or {}
        if c.get("att_id") == c.get("owner_id"):                 # patte SELF ci-dessus
            return None
        if c.get("is_melee") is not True:                        # IsMeleeAttack -- tri-etat
            return None
        # `Friends(Owner@+0x30, ..., OnlyAliveAndTargetable)` -- l'agregateur ne retient deja que
        # les VIVANTS de l'equipe du porteur ; on re-joue l'egalite d'equipe explicitement.
        if c.get("owner_team") is None or c.get("owner_team") != c.get("att_team"):
            return None
        vid = c.get(CTX_ATT_VISUAL_ID)
        if vid is None:                                          # canal non mesure -> le gate se tait
            return None
        want = _beneficiary_visual_id()
        if not want or str(vid) != want:                         # UnitsWithVisualId(<constants.unitId>)
            return None
        amt = self._amount(c, c.get("owner_id"))
        return for_addition(True, int(amt)) if amt else None
