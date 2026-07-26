"""`IdunBattle.Entities.Abilities.AbilityAttackType` + les deux predicats DSL qui le lisent
(`AbilityHasAttackType`, `IsNormalAttack`) -- la DONNEE manquante quand le vecteur
`On(PreUnitAbility=0x2b)` cesse d'etre emis par la SEULE voie d'attaque normale (#120).

POURQUOI CE MODULE EXISTE
-------------------------
`IdunBattle.Operations.ActiveAbilityOperation$$ExecuteInternal` emet `On(0x2b)` depuis UN SEUL
site, en amont de l'execution -- et l'attaque NORMALE emprunte cette meme operation (elle EST une
active ability : `IdunBattleLogic.Entities.Abilities.Active.Loki.ALoki_NormalAttackAbility`). Le
port, lui, a DEUX portes d'operation (`DamageHandler.visit_AttackUnitMessage` et
`AbilityHandler.visit_ActiveAbilityMessage`) : tant que seule la voie normale emettait, les deux
consommateurs de `0x2b` pouvaient s'appuyer sur un gate *structurel* (« ce vecteur ne vient que de
l'attaque normale »). Des que les DEUX voies emettent (#120), ce gate structurel disparait et il
faut porter les predicats REELS de leurs `CreateTrigger` -- sinon on transforme un no-op silencieux
en faux-positif silencieux (AnvilShield qui donnerait +20 % block sur un soin adverse, SwornProtector
qui ferait apparaitre Kell sur un buff).

`AActiveAbility$$HasAttackType`
------------------------------
    df = this+0x30
    if (attackType == this+0x68)  return df+0xf8;   // trigger constant VRAI
    else                          return df+0x100;  // trigger constant FAUX

=> le predicat est une simple EGALITE avec un champ d'instance. Et `IdunBattle.Entities.Abilities.
AActiveAbility$$.ctor` (`*(undefined4 *)(param_1 + 0xd) = param_3;`, soit l'octet +0x68) montre que
ce champ est le **3e argument du ctor de base**, donc un LITTERAL du ctor de chaque sous-classe :

    IdunBattleLogic.Entities.Abilities.Active.Loki.ThunderousAssaultAbility$$.ctor
        -> AActiveAbility..ctor(this, &opts, 0)   = DirectTargetAttack
    IdunBattleLogic.Entities.Abilities.Active.Loki.IncursionAbility$$.ctor
        -> AActiveAbility..ctor(this, &opts, 1)   = SummonAndAttackTarget
    IdunBattleLogic.Entities.Abilities.Active.Loki.CombatRestorativesAbility$$.ctor
        -> AActiveAbility..ctor(this, &opts, 2)   = Others

La table `ABILITY_ATTACK_TYPE` ci-dessous est donc la TRANSCRIPTION de ce litteral, ability par
ability, exactement comme `TARGETING_OPTIONS` transcrit le masque de `TargetingOptions..ctor`
(cf. `abilities/targeting.py`). Meme convention de degradation : une ability dont le litteral n'a
PAS ete lu est ABSENTE de la table -> `ability_has_attack_type` rend False, donc AUCUN trigger
invente (le sens sur dans lequel se degrader : un trigger qui ne part pas laisse l'etat inchange,
un trigger qui part a tort MUTE la bataille).

`DSLFactory$$IsNormalAttack`
---------------------------
`IdunBattleLogic.Entities.DSLFactory$$IsNormalAttack(df)` = `IsNormalAttack(df, df@0x130)` (l'ability
DECLENCHANTE), et l'overload a 2 arguments batit une DISJONCTION :

    AbilityIsNormalAttackTrigger(sel)                       # branche 1
    | <trigger DAT_18322f680>(sel, DirectAbilitySelector(AbilityOrEffect 0x3f5 = 1013))   # branche 2

* branche 1 -- `IdunBattle.Entities.Triggers.AbilityIsNormalAttackTrigger$$ShouldTrigger` resout le
  selecteur en `Nullable<AbilityOrEffect>` puis rend
  `idun.Idun.Source.Shared.Battle.StaticBattleRules.StaticBattleRules.ActiveAbility$$IsRegularAttack`
  de son `ActiveAbilityType`. `IsRegularAttack(t)` = `Contains(t)` sur l'`OrderedSet` statique
  `StaticBattleRules.ActiveAbility` @+0x18, rempli par son `$$.cctor` -> c'est exactement
  `REGULAR_ATTACK_ABILITY_TYPES` ci-dessous (les attaques normales PER-UNIT, cf. la memoire
  « normal attack = concrete ability id »).
* branche 2 -- MEME noeud (meme classe, meme selecteur 1013) que la 2e branche de
  `IdunBattleLogic.Entities.DSLFactory$$OnNormalAttackOrSmite`, deja porte par LordOfTempests
  (`triggers/loki/lord_of_tempests.py`, `SMITE_KIND = 0x3f5`) : « l'ability courante porte le KIND
  attaque-normale ». C'est le marqueur que la voie normale du port thread deja
  (`damage_ops.execute` -> `pre_unit_ability_triggers(..., ability_type=1013)`).
"""
from __future__ import annotations

from typing import Optional


class AbilityAttackType:
    """`IdunBattle.Entities.Abilities.AbilityAttackType` (dump il2cpp, enum verbatim) -- la valeur
    stockee a `AActiveAbility+0x68` et comparee par `AActiveAbility$$HasAttackType`."""
    DirectTargetAttack = 0
    SummonAndAttackTarget = 1
    Others = 2


# `idun.Idun.Source.Shared.Battle.StaticBattleRules.StaticBattleRules.ActiveAbility$$.cctor` --
# l'`OrderedSet<ActiveAbilityType>` range dans le champ statique +0x18, le SEUL lu par
# `...ActiveAbility$$IsRegularAttack` (`Contains`). Transcription VERBATIM de l'ordre du cctor.
REGULAR_ATTACK_ABILITY_TYPES = frozenset({
    0x011,   # 17   NormalAttack
    0x045,   # 69   Loki_NormalAttack
    0x406,   # 1030 Loki_NormalBossAttack
    0x416,   # 1046 TemplarInitiateNormalAttack
    0x434,   # 1076 MV71SniperDroneSquadAttack
    0x43e,   # 1086 ProperKilly_NormalAttack
    0x45a,   # 1114 BlisteringAssault_NormalAttack
    0x460,   # 1120 FeederTendrils_NormalAttack
    0x468,   # 1128 Boltstorm_NormalAttack
    0x463,   # 1123 OptimizedGait_NormalAttack
    0x466,   # 1126 RogalDorn_NormalAttack
    0x47a,   # 1146 FloatingDeath_NormalAttack
    0x48a,   # 1162 AncientFury_NormalAttack
    0x472,   # 1138 Wraithcannon_NormalAttack
    0x49a,   # 1178 ElectroShock_NormalAttack
    0x49e,   # 1182 RighteousRepugnance_NormalAttack
    0x4b5,   # 1205 TalonOfHorus_NormalAttack
    0x4c4,   # 1220 Fealty_NormalAttack
})

# `AbilityOrEffect(0x3f5)` du `DirectAbilitySelector` de la 2e branche d'`IsNormalAttack` -- le
# marqueur « kind attaque-normale » que la voie normale du port thread deja (damage_ops.execute,
# psyker.py, lord_of_tempests.py). MEME constante que `lord_of_tempests.SMITE_KIND`.
NORMAL_ATTACK_KIND = 0x3f5      # 1013

# --- 3e argument d'`AActiveAbility$$.ctor` (= `AActiveAbility+0x68`), ability par ability. ---------
# Cle = `ActiveAbilityType` (celle du registre `ABILITY_CLASSES`) ; valeur = `AbilityAttackType`.
# Source = `IdunBattleLogic.Entities.Abilities.Active.Loki.<X>Ability$$.ctor` (litteral du dernier
# argument du `AActiveAbility..ctor(this, &targetingOptions, <ici>)`). Couvre TOUT le registre
# d'abilities porte au moment de #120 ; une ability absente = litteral non lu (cf. l'en-tete).
ABILITY_ATTACK_TYPE: dict[int, int] = {
    # --- 0 : DirectTargetAttack ---------------------------------------------------------------
    1013: AbilityAttackType.DirectTargetAttack,   # PrecisionShot_AttackAbility$$.ctor -- le KIND
                                                  # attaque-normale threade par la voie normale
    1004: AbilityAttackType.DirectTargetAttack,   # MortisRoundAbility
    1006: AbilityAttackType.DirectTargetAttack,   # MultiThreatEliminatorAbility
    1008: AbilityAttackType.DirectTargetAttack,   # HarbingerOfDestructionAbility
    1014: AbilityAttackType.DirectTargetAttack,   # ArmoriumCherubAbility
    1022: AbilityAttackType.DirectTargetAttack,   # BringerOfDespairAbility
    1025: AbilityAttackType.DirectTargetAttack,   # SkyStrikeAbility
    1042: AbilityAttackType.DirectTargetAttack,   # FlailSwingAbility
    1043: AbilityAttackType.DirectTargetAttack,   # ThunderousAssaultAbility
    1051: AbilityAttackType.DirectTargetAttack,   # StikkbombAbility
    1062: AbilityAttackType.DirectTargetAttack,   # SanctorumMissileAbility
    1065: AbilityAttackType.DirectTargetAttack,   # ScythingTalonsAbility
    1066: AbilityAttackType.DirectTargetAttack,   # ExecutionerAbility
    1067: AbilityAttackType.DirectTargetAttack,   # HarvesterOfSoulsAbility
    1078: AbilityAttackType.DirectTargetAttack,   # FragstormAbility
    1089: AbilityAttackType.DirectTargetAttack,   # GreatFrostAxeAbility
    1092: AbilityAttackType.DirectTargetAttack,   # DarkTalonStrikeAbility
    1098: AbilityAttackType.DirectTargetAttack,   # PlasmaGrenadeAbility
    1104: AbilityAttackType.DirectTargetAttack,   # SpiritLeechAbility
    1105: AbilityAttackType.DirectTargetAttack,   # CrushingClawsAbility
    1113: AbilityAttackType.DirectTargetAttack,   # StormcallerAbility
    1122: AbilityAttackType.DirectTargetAttack,   # CordClawAbility
    1131: AbilityAttackType.DirectTargetAttack,   # JakhalStimmsAbility
    1139: AbilityAttackType.DirectTargetAttack,   # SentinelDirectivesAbility
    1147: AbilityAttackType.DirectTargetAttack,   # HadesAutocannonsAbility
    1148: AbilityAttackType.DirectTargetAttack,   # DaemonicOrdnanceAbility
    1150: AbilityAttackType.DirectTargetAttack,   # PlasmaCannonAbility
    1160: AbilityAttackType.DirectTargetAttack,   # HeavyRailRifleAbility
    1161: AbilityAttackType.DirectTargetAttack,   # TwinSmartMissileSystemAbility
    1168: AbilityAttackType.DirectTargetAttack,   # EntropyCannonsAbility
    1169: AbilityAttackType.DirectTargetAttack,   # PlagueburstMortarAbility
    1180: AbilityAttackType.DirectTargetAttack,   # HeroicFusilladeAbility
    1200: AbilityAttackType.DirectTargetAttack,   # SquigLaunchasAbility
    1201: AbilityAttackType.DirectTargetAttack,   # SquigMineAbility
    1202: AbilityAttackType.DirectTargetAttack,   # VigilanceEternalAbility
    1213: AbilityAttackType.DirectTargetAttack,   # DeathOnTheWindAbility
    1221: AbilityAttackType.DirectTargetAttack,   # AugmentedAssaultAbility
    1230: AbilityAttackType.DirectTargetAttack,   # SavageEchoesAbility
    1103: AbilityAttackType.DirectTargetAttack,   # SuperchargeAbility (lot #112, litteral 0 relu)
    # --- 1 : SummonAndAttackTarget (le summon pose attaque la cible du cast) --------------------
    1003: AbilityAttackType.SummonAndAttackTarget,   # DeathFromAboveAbility
    1007: AbilityAttackType.SummonAndAttackTarget,   # ScarabHiveAbility
    1016: AbilityAttackType.SummonAndAttackTarget,   # SendInTheNextWaveAbility
    1021: AbilityAttackType.SummonAndAttackTarget,   # IncursionAbility
    1040: AbilityAttackType.SummonAndAttackTarget,   # SpawnPoxwalkersAbility
    1076: AbilityAttackType.SummonAndAttackTarget,   # MV71SniperDroneSquadAttackAbility -- sa classe
        # native est un TRIGGERED (`...Triggered.Loki.MV71SniperDroneSquadAttackAbility$$.ctor`) mais
        # elle derive de `ALoki_NormalAttackAbility`, dont le ctor FORWARDE son 3e argument a
        # `AActiveAbility$$.ctor` : `ALoki_NormalAttackAbility..ctor(this, &opts, 1)` -> 1.
    # --- 2 : Others (y compris des abilities qui font pourtant des degats -- le natif les CLASSE
    #         hors « attaque directe sur la cible » : AoE de zone, charge-puis-frappe, tile-target) -
    1000: AbilityAttackType.Others,   # GauntletsOfUltramarAbility
    1002: AbilityAttackType.Others,   # CombatRestorativesAbility
    1009: AbilityAttackType.Others,   # ResurrectionOrbAbility
    1018: AbilityAttackType.Others,   # ValkyrieStrikeAbility
    1028: AbilityAttackType.Others,   # SupremeCommanderAbility
    1037: AbilityAttackType.Others,   # RevitalizingMalignancyAbility
    1045: AbilityAttackType.Others,   # GetEmRuntzAbility
    1047: AbilityAttackType.Others,   # ScarabSummonAbility
    1058: AbilityAttackType.Others,   # WaaaghAbility
    1096: AbilityAttackType.Others,   # MasterOfTheTutelariesAbility
    1112: AbilityAttackType.Others,   # AlphaWarriorAbility
    1118: AbilityAttackType.Others,   # DoctrinaImperativesAbility
    1142: AbilityAttackType.Others,   # MalleusRocketLauncherAbility
    1143: AbilityAttackType.Others,   # ForwardSpotterAbility
    1145: AbilityAttackType.Others,   # SporeMineLauncherAbility
    1151: AbilityAttackType.Others,   # TheQuickeningAbility
    1159: AbilityAttackType.Others,   # MacroPlasmaIncineratorAbility
    1163: AbilityAttackType.Others,   # BlackRageAbility
    1166: AbilityAttackType.Others,   # AberrantHypermorphAbility
    1179: AbilityAttackType.Others,   # CultDemagogueAbility
    1187: AbilityAttackType.Others,   # ThriceBlessedConflagrationAbility
    1188: AbilityAttackType.Others,   # DevastatingRefrainAbility
    1206: AbilityAttackType.Others,   # GravitonRifleAbility
    1207: AbilityAttackType.Others,   # AncestralFortuneAbility
    1214: AbilityAttackType.Others,   # HailstrikeAbility
    1219: AbilityAttackType.Others,   # IronkinSteeljackAbility
    1226: AbilityAttackType.Others,   # ChronometronAbility
    # Lot Tau #114 (merge d67b6ac), arrive APRES la redaction de #120 : les trois ctors passent
    # litteralement `AActiveAbility..ctor(this, &opts, 2, 0)` (relu au decompile).
    1077: AbilityAttackType.Others,   # EarlyWarningOverrideAbility
    1081: AbilityAttackType.Others,   # FightingRetreatAbility
    1082: AbilityAttackType.Others,   # InspiredToGreatnessAbility
    # Lot DarkAngels #112, arrive lui aussi apres #120 (litteraux relus au decompile) :
    # Supercharge est le seul des trois a `DirectTargetAttack` (0) -- il entre donc dans le gate
    # `AbilityHasAttackType(0|1)` de SwornProtector, contrairement aux deux autres.
    1140: AbilityAttackType.Others,   # ExemplarOfHateAbility
    1189: AbilityAttackType.Others,   # CalibaniteGreatswordAbility
}
# COUVERTURE : la table couvre l'INTEGRALITE du registre `ABILITY_CLASSES` (garde-fou :
# `probe_120_pre_unit_ability_fork.py` etape 0). Une ability AJOUTEE au registre sans son litteral de
# ctor n'est PAS gatee -- elle se degrade en `Others` (aucun trigger invente), ce que le probe
# SIGNALE au lieu de le taire.


def ability_has_attack_type(ability_type: Optional[int], attack_type: int) -> bool:
    """`IdunBattleLogic.Entities.DSLFactory$$AbilityHasAttackType(df, sel, attackType)` ->
    `IdunBattle.Entities.Triggers.AbilityHasAttackTypeTrigger$$ShouldTrigger`, qui resout le
    selecteur d'ability puis delegue a `IdunBattle.Entities.Abilities.AActiveAbility$$HasAttackType`
    = `attackType == this+0x68` (trigger constant VRAI/FAUX).

    `ability_type` = l'ability DECLENCHANTE de l'evenement (`df@0x130`, porte par
    `TriggerEvent.ability_type`). Inconnue de la table (ou None) -> False : le litteral du ctor n'a
    pas ete lu, on n'invente pas un trigger (cf. l'en-tete de module)."""
    if ability_type is None:
        return False
    return ABILITY_ATTACK_TYPE.get(int(ability_type)) == int(attack_type)


def ability_is_attack(ability_type: Optional[int]) -> bool:
    """`AbilityHasAttackType(@0x130, 0) | AbilityHasAttackType(@0x130, 1)` -- la disjonction
    litterale de `IdunBattleLogic.Entities.Abilities.Active.Loki.SwornProtectorAbility$$CreateTrigger`
    (sous-fonction `GetIsValidAttackForSwornProtectorTrigger`) et de
    `...SwornProtector_ProtectAbility$$CreateTrigger`."""
    return (ability_has_attack_type(ability_type, AbilityAttackType.DirectTargetAttack)
            or ability_has_attack_type(ability_type, AbilityAttackType.SummonAndAttackTarget))


def is_regular_attack(ability_type: Optional[int]) -> bool:
    """`idun.Idun.Source.Shared.Battle.StaticBattleRules.StaticBattleRules.ActiveAbility$$IsRegularAttack`
    = `Contains` sur l'`OrderedSet` statique @+0x18 = `REGULAR_ATTACK_ABILITY_TYPES`."""
    return ability_type is not None and int(ability_type) in REGULAR_ATTACK_ABILITY_TYPES


# `IsActiveAbility` exclut, EN PLUS des attaques regulieres, cinq `ActiveAbilityType` litteraux lus au
# decompile (`... != 0x12 && ... != 0x48f && ... != 0x4bc && ... != 0x1c && ... != 0x45f`) : ce sont les
# abilities-OUTILS de soin/reparation que le moteur declenche pour le compte d'une AUTRE ability.
NOT_ACTIVE_ABILITY_TYPES = frozenset({
    0x012,   # 18   Heal
    0x01c,   # 28   Repair
    0x45f,   # 1119 Repair_GalvanicField
    0x48f,   # 1167 Heal_TwistedScience
    0x4bc,   # 1212 HealingBalms_Heal
})


def is_active_ability(ability_type: Optional[int]) -> bool:
    """`idun.Idun.Source.Shared.Battle.StaticBattleRules.StaticBattleRules.ActiveAbility$$IsActiveAbility`
    (MIRROR du decompile) = `!IsRegularAttack(t) && t not in NOT_ACTIVE_ABILITY_TYPES`.

    C'est le GATE de l'evenement `On(UnitActiveAbility = 0xc)` d'
    `IdunBattle.Operations.ActiveAbilityOperation$$ExecuteInternal` : le natif emet `On(0xb)`
    inconditionnellement puis `On(0xc)` **seulement si** ce predicat est vrai. Consequence directe :
    une ATTAQUE NORMALE (qui emprunte pourtant la meme operation) n'emet PAS `On(0xc)` -- c'est ce qui
    rend le retrait de `InspiredToGreatness_OverrideLevel` (`On(0xc) & OwnerIsCaster`) borne au
    PROCHAIN CAST D'ACTIF de la cible, et non a sa prochaine attaque."""
    if ability_type is None:
        return False
    t = int(ability_type)
    return not is_regular_attack(t) and t not in NOT_ACTIVE_ABILITY_TYPES


def is_normal_attack(ability_type: Optional[int]) -> bool:
    """`IdunBattleLogic.Entities.DSLFactory$$IsNormalAttack(df)` -- la DISJONCTION des deux branches
    detaillees en tete de module :

        AbilityIsNormalAttackTrigger(@0x130)          -> `IsRegularAttack(ActiveAbilityType)`
        | <noeud kind>(@0x130, DirectAbilitySelector(AbilityOrEffect 0x3f5))

    Cote port, l'attaque normale thread le marqueur `0x3f5` (branche 2) ; une ability CASTEE thread
    son propre `ActiveAbilityType`, qui n'est dans `REGULAR_ATTACK_ABILITY_TYPES` que si c'est
    justement l'attaque normale per-unit d'une unite (ex. 1076 MV71) -- fidele."""
    return is_regular_attack(ability_type) or (
        ability_type is not None and int(ability_type) == NORMAL_ATTACK_KIND)
