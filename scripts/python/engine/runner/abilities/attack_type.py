"""`IdunBattle.Entities.Abilities.AbilityAttackType` + les deux predicats DSL qui le lisent
(`AbilityHasAttackType`, `IsNormalAttack`) -- la DONNEE manquante quand le vecteur
`On(PreUnitAbility=0x2a)` cesse d'etre emis par la SEULE voie d'attaque normale (#120).

POURQUOI CE MODULE EXISTE
-------------------------
`IdunBattle.Operations.ActiveAbilityOperation$$ExecuteInternal` emet `On(0x2a = PreUnitAbility)` depuis UN SEUL
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
  `IdunBattleLogic.Entities.DSLTriggers$$OnNormalAttackOrSmite`, deja porte par LordOfTempests
  (`triggers/loki/lord_of_tempests.py`, `SMITE_KIND = 0x3f5`) : « l'ability courante porte le KIND
  attaque-normale ». C'est le marqueur que la voie normale du port thread deja
  (`damage_ops.execute` -> `pre_unit_ability_triggers(..., ability_type=1013)`).
"""
from __future__ import annotations

from typing import Optional

from ...entities.active_ability_type import ActiveAbilityType
# Feuille pure (`enum` seul) : `import engine.entities.triggered_ability_type` charge 2 modules
# `engine.*` (le paquet + lui-meme). L'ajouter ici n'allonge la cascade d'AUCUN module.
from ...entities.triggered_ability_type import TriggeredAbilityType


class AbilityAttackType:
    """`IdunBattle.Entities.Abilities.AbilityAttackType` (dump il2cpp, enum verbatim) -- la valeur
    stockee a `AActiveAbility+0x68` et comparee par `AActiveAbility$$HasAttackType`."""
    DirectTargetAttack = 0
    SummonAndAttackTarget = 1
    Others = 2


# `idun.Idun.Source.Shared.Battle.StaticBattleRules.StaticBattleRules.ActiveAbility$$.cctor` --
# l'`OrderedSet<ActiveAbilityType>` range dans le champ statique +0x18, le SEUL lu par
# `...ActiveAbility$$IsRegularAttack` (`Contains`). Transcription VERBATIM de l'ordre du cctor.
# #270-r1-r1 : membres nommes. L'ORDRE du cctor est conserve (il est transcrit VERBATIM ci-dessus)
# et l'ordinal reste en commentaire de fin de ligne -- il documente, il ne designe plus.
REGULAR_ATTACK_ABILITY_TYPES = frozenset({
    ActiveAbilityType.NormalAttack,                       # 0x011 = 17
    ActiveAbilityType.Loki_NormalAttack,                  # 0x045 = 69
    ActiveAbilityType.Loki_NormalBossAttack,              # 0x406 = 1030
    ActiveAbilityType.TemplarInitiateNormalAttack,        # 0x416 = 1046
    ActiveAbilityType.MV71SniperDroneSquadAttack,         # 0x434 = 1076
    ActiveAbilityType.ProperKilly_NormalAttack,           # 0x43e = 1086
    ActiveAbilityType.BlisteringAssault_NormalAttack,     # 0x45a = 1114
    ActiveAbilityType.FeederTendrils_NormalAttack,        # 0x460 = 1120
    ActiveAbilityType.Boltstorm_NormalAttack,             # 0x468 = 1128
    ActiveAbilityType.OptimizedGait_NormalAttack,         # 0x463 = 1123
    ActiveAbilityType.RogalDorn_NormalAttack,             # 0x466 = 1126
    ActiveAbilityType.FloatingDeath_NormalAttack,         # 0x47a = 1146
    ActiveAbilityType.AncientFury_NormalAttack,           # 0x48a = 1162
    ActiveAbilityType.Wraithcannon_NormalAttack,          # 0x472 = 1138
    ActiveAbilityType.ElectroShock_NormalAttack,          # 0x49a = 1178
    ActiveAbilityType.RighteousRepugnance_NormalAttack,   # 0x49e = 1182
    ActiveAbilityType.TalonOfHorus_NormalAttack,          # 0x4b5 = 1205
    ActiveAbilityType.Fealty_NormalAttack,                # 0x4c4 = 1220
})

# `AbilityOrEffect(0x3f5)` du `DirectAbilitySelector` de la 2e branche d'`IsNormalAttack` -- le
# marqueur de KIND que la voie normale du port thread deja (damage_ops.execute, psyker.py,
# lord_of_tempests.py). MEME constante que `lord_of_tempests.SMITE_KIND`.
#
# ⚠ L'ENUM EST TRANCHE, ET CE N'EST PAS `ActiveAbilityType` (#270-r1-r1-r3-r1, build `rnca9r7q6c`).
# `1013` est un membre valide de QUATRE enums (`ActiveAbilityType.PrecisionShot_Attack`,
# `TriggeredAbilityType.PsykerExtraAttack`, `EffectType.LightCover`, `UnitTrait.MkXGravis`), donc
# l'ordinal ne discrimine RIEN. Le discriminant est la SURCHARGE d'`IdunBattle.Core.AbilityOrEffect$$op_Implicit`
# empruntee par le call-site natif -- lue par le rel32 du `call` qui suit `mov edx, 0x3f5`, jamais
# par le pseudo-C (les trois surcharges portent le meme nom affiche) :
#
#     IdunBattleLogic.Entities.DSLTriggers$$IsNormalAttack+0x6f     -> op_Implicit(triggeredAbility)
#     IdunBattleLogic.Entities.DSLTriggers$$OnNormalAttackOrSmite+0x4d -> op_Implicit(triggeredAbility)
#
# La surcharge ainsi designee est celle dont le parametre se nomme `triggeredAbility` et qui appelle
# `IdunBattle.Core.AbilityOrEffect$$set_TriggeredAbility` (les deux autres appellent
# `$$set_ActiveAbility` / `$$set_Effect`). => `TriggeredAbilityType.PsykerExtraAttack`.
# Le NOM NATIF corrobore : la branche 1 d'`OnNormalAttackOrSmite` est l'attaque normale, la
# branche 2 -- celle qui porte ce litteral -- est le SMITE (splash du trait `Psyker`), et
# `entities/triggered_ability_type.py` inscrit deja `"Psyker": (PsykerExtraAttack,)`.
NORMAL_ATTACK_KIND = int(TriggeredAbilityType.PsykerExtraAttack)      # 0x3f5 = 1013

# --- 3e argument d'`AActiveAbility$$.ctor` (= `AActiveAbility+0x68`), ability par ability. ---------
# Cle = `ActiveAbilityType` (celle du registre `ABILITY_CLASSES`) ; valeur = `AbilityAttackType`.
# Source = `IdunBattleLogic.Entities.Abilities.Active.Loki.<X>Ability$$.ctor` (litteral du dernier
# argument du `AActiveAbility..ctor(this, &targetingOptions, <ici>)`). Couvre TOUT le registre
# d'abilities porte au moment de #120 ; une ability absente = litteral non lu (cf. l'en-tete).
ABILITY_ATTACK_TYPE: dict[int, int] = {
    # --- 0 : DirectTargetAttack ---------------------------------------------------------------
    # `PrecisionShot_AttackAbility$$.ctor` -- 1013 est aussi le KIND attaque-normale threade par la
    # voie normale (cf. `NORMAL_ATTACK_KIND` ci-dessus).
    ActiveAbilityType.PrecisionShot_Attack: AbilityAttackType.DirectTargetAttack,  # 1013
    ActiveAbilityType.MortisRound: AbilityAttackType.DirectTargetAttack,  # 1004
    ActiveAbilityType.MultiThreatEliminator: AbilityAttackType.DirectTargetAttack,  # 1006
    ActiveAbilityType.HarbingerOfDestruction: AbilityAttackType.DirectTargetAttack,  # 1008
    ActiveAbilityType.ArmoriumCherub: AbilityAttackType.DirectTargetAttack,  # 1014
    # StormOfFlensingBlades (1010, lot #996) : `...StormOfFlensingBladesAbility$$.ctor` ->
    # `AActiveAbility..ctor(this, &opts, 0)` -- le 3e argument est le litteral `0`. TRANSCRIT, et il
    # tombe juste ici : le cast rejoue DEUX FOIS l'attaque NORMALE du porteur sur la cible. C'est
    # l'audit qui se trompait en l'annoncant EFFECT/BUFF (colonne derivee du `damageProfile` de
    # l'ARME, cf. residu #491-r2).
    ActiveAbilityType.StormOfFlensingBlades: AbilityAttackType.DirectTargetAttack,  # 1010
    # StormOfWrath (1019) : `...Active.Loki.StormOfWrathAbility$$.ctor` ->
    # `AActiveAbility..ctor(this, &opts, 0)` -- le 3e argument est le litteral `0`. TRANSCRIT, pas
    # deduit : le behaviour n'attaque PAS « en direct » (c'est une CHAINE `ChainAbilityDamage` de
    # famille ABILITY, aucune Operation `AttackDamage`), et le litteral vaut quand meme
    # `DirectTargetAttack`. (#499)
    ActiveAbilityType.StormOfWrath: AbilityAttackType.DirectTargetAttack,  # 1019
    ActiveAbilityType.HeraldOfTheApocalypse: AbilityAttackType.DirectTargetAttack,  # 1020 (case-bl-1029-1020)
    # BloodyFury (1129) : `...Active.Loki.BloodyFuryAbility$$.ctor` recopie le preset statique
    # `<TargetingOptions statics>+0x40`, appelle la surcharge COPIE PURE a 2 arguments, puis
    # `AActiveAbility..ctor(this, &opts, 0)` -- le 3e argument est le litteral `0`. TRANSCRIT, pas
    # deduit du comportement (le lot du jour porte les deux contre-exemples : `Others` sur une
    # ability qui attaque, `DirectTargetAttack` sur une qui ne frappe pas). (#505)
    ActiveAbilityType.BloodyFury: AbilityAttackType.DirectTargetAttack,  # 1129
    # MindControl (1164) : `...Active.Loki.MindControlAbility$$.ctor` recopie les 3 qwords du champ
    # statique `<TargetingRange statics>+0x18`, appelle `TargetingOptions..ctor(&opts, 0, &range, 1,
    # 0x4002, 0, 0)`, puis `AActiveAbility..ctor(this, &opts, 0)` -- le 3e argument est le litteral
    # `0`. TRANSCRIT, jamais deduit : l'arbre de 1164 NE FRAPPE PAS (quatre `AddEffect`/
    # `AddBondEffect`, un `Inform`, deux `If` -- aucune Operation d'attaque), et le litteral vaut
    # quand meme `DirectTargetAttack`. Meme contre-exemple que StormOfWrath (1019) et BloodyFury
    # (1129) ci-dessus. (#552)
    ActiveAbilityType.MindControl: AbilityAttackType.DirectTargetAttack,  # 1164
    # AttemptedPossession (1101) : `...Active.Loki.AttemptedPossessionAbility$$.ctor` recopie les
    # 0x40 octets du champ statique `<TargetingOptions statics>+0x180` (preset), appelle
    # `TargetingOptions..ctor(&opts, &preset, 0x200000002)`, puis
    # `AActiveAbility..ctor(this, &opts, 0)` -- le 3e argument est le litteral `AbilityAttackType`,
    # et il vaut **0**. On le TRANSCRIT. Nouveau contre-exemple de la meme famille que StormOfWrath
    # (1019), BloodyFury (1129) et MindControl (1164) : l'arbre ne contient AUCUN
    # `AttackWithAttackDamage` ni `UseActiveAbility` -- il fait FRAPPER la cible via
    # `PerformAIAbility`, ce qui n'est pas un coup du CASTER -- et le litteral vaut quand meme
    # `DirectTargetAttack`. (#590)
    ActiveAbilityType.AttemptedPossession: AbilityAttackType.DirectTargetAttack,  # 1101
    ActiveAbilityType.BringerOfDespair: AbilityAttackType.DirectTargetAttack,  # 1022
    ActiveAbilityType.SkyStrike: AbilityAttackType.DirectTargetAttack,  # 1025
    # PsychicMaelstrom (1027) : `PsychicMaelstromAbility$$.ctor` recopie le preset statique
    # `<TargetingOptions statics>+0x180` puis appelle `AActiveAbility..ctor(this, &opts, 0)` --
    # le 3e argument est le litteral `0`. (#490)
    ActiveAbilityType.PsychicMaelstrom: AbilityAttackType.DirectTargetAttack,  # 1027
    # Drachnyen (1029) : `DrachnyenAbility$$.ctor` -> `AActiveAbility..ctor(this, &opts, 0, 0)`.
    # Le litteral est `0` MEME si le behaviour n'attaque pas en direct (il dispatche l'attaque
    # NORMALE via `UseActiveAbility`) : on transcrit le 3e argument du ctor, jamais le profil de
    # degat de l'arbre. (case-bl-1029-1020)
    ActiveAbilityType.Drachnyen: AbilityAttackType.DirectTargetAttack,  # 1029
    # HolyDuel (1050) : `...Active.Loki.HolyDuelAbility$$.ctor` recopie le preset statique
    # `<TargetingOptions statics>+0x40`, appelle la surcharge PRESET+FLAGS (`0x200000000`) puis
    # `AActiveAbility..ctor(this, &opts, 0)` -- le 3e argument est le litteral `0`. MEME
    # configuration que Drachnyen ci-dessus : TRANSCRIT bien que l'arbre n'attaque pas « en
    # direct » (il dispatche l'attaque NORMALE via `UseActiveAbility`).
    ActiveAbilityType.HolyDuel: AbilityAttackType.DirectTargetAttack,  # 1050
    # DevoutPush (1053) : `...Active.Loki.DevoutPushAbility$$.ctor` est de forme STATIC-COPY (aucun
    # `TargetingOptions$$.ctor` appele) -- il recopie les 0x40 octets du preset statique
    # `<TargetingOptions statics>+0x40` puis `AActiveAbility..ctor(this, &opts, 0)`, ou le 3e
    # argument est le litteral `0` (`xor r8d, r8d`). MEME configuration que Drachnyen et HolyDuel
    # ci-dessus : TRANSCRIT bien que l'arbre n'attaque pas « en direct » (il dispatche l'attaque
    # NORMALE via `UseActiveAbility`, puis DEPLACE via `PerformAIMovement`). (#996-r1)
    ActiveAbilityType.DevoutPush: AbilityAttackType.DirectTargetAttack,  # 1053
    ActiveAbilityType.FlailSwing: AbilityAttackType.DirectTargetAttack,  # 1042
    # StrikeFromTheShadows (1225) : `...Active.Loki.StrikeFromTheShadowsAbility$$.ctor` recopie les
    # 0x40 octets du preset statique `<TargetingOptions statics>+0x140` puis appelle
    # `AActiveAbility..ctor(this, &opts, 0)` -- le 3e argument est le litteral `0`. TRANSCRIT, jamais
    # deduit du profil de degat de l'arbre. (#511)
    ActiveAbilityType.StrikeFromTheShadows: AbilityAttackType.DirectTargetAttack,  # 1225
    # TitanhammerSquad (1231) : `...Active.Loki.TitanhammerSquadAbility$$.ctor` appelle le ctor PLEIN
    # de `TargetingOptions` (surcharge tranchee par ses XREFS ENTRANTES) puis
    # `AActiveAbility..ctor(this, &opts, 2)` -- le 3e argument est le litteral `2` = `Others`.
    # TRANSCRIT, jamais deduit : l'arbre ne porte AUCUNE attaque (marquage de tuile + soin + buff +
    # marqueur de teleportation), donc `Others` est aussi ce qu'on attendrait -- mais c'est le
    # litteral qui tranche, pas l'arbre. (#448-r2d-r2)
    ActiveAbilityType.TitanhammerSquad: AbilityAttackType.Others,  # 1231
    # LashOfTorment (1196) : `...Active.Loki.LashOfTormentAbility$$.ctor` recopie les 0x40 octets du
    # MEME preset statique `<TargetingOptions statics>+0x140` que 1225 puis appelle
    # `AActiveAbility..ctor(this, &opts, 0)` -- le 3e argument est le litteral `0`. TRANSCRIT au
    # decompile, jamais deduit (l'arbre attaque bien en direct, mais c'est une coincidence : le lot
    # #499/#505 porte les deux contre-exemples). (#524)
    ActiveAbilityType.LashOfTorment: AbilityAttackType.DirectTargetAttack,  # 1196
    # InfernalCannon (1209) : `...Active.Loki.InfernalCannonAbility$$.ctor` appelle la surcharge a
    # SEPT arguments de `TargetingOptions$$.ctor` puis `AActiveAbility..ctor(this, &opts, 2)` -- le
    # 3e argument est le litteral `2`. TRANSCRIT, jamais deduit : l'arbre attaque bel et bien en
    # direct (une volee `AttackWithAbilityDamage` multi-cible), et le litteral vaut quand meme
    # `Others`. C'est le contre-exemple SYMETRIQUE de 1019 `StormOfWrath` (chaine qui n'attaque pas
    # en direct et porte `DirectTargetAttack`). (#605)
    ActiveAbilityType.InfernalCannon: AbilityAttackType.Others,  # 1209
    # DaemonicPatrons (1203) : `...Active.Loki.DaemonicPatronsAbility$$.ctor` recopie les 0x40 octets
    # du preset statique `<TargetingOptions statics>+0x40`, appelle la surcharge PRESET+FLAGS
    # (`0x200000000`, surcharge tranchee par ses XREFS ENTRANTES -- la MEME que 1183/1050) puis
    # `AActiveAbility..ctor(this, &opts, 0)` -- le 3e argument est le litteral `0`. TRANSCRIT, jamais
    # deduit : l'arbre de 1203 NE FRAPPE PAS (un `AddBondEffect` + deux `AddEffect`, rien d'autre),
    # et le litteral vaut quand meme `DirectTargetAttack`. Meme contre-exemple que StormOfWrath
    # (1019), BloodyFury (1129), MindControl (1164) et AttemptedPossession (1101). (#911)
    ActiveAbilityType.DaemonicPatrons: AbilityAttackType.DirectTargetAttack,  # 1203
    # HellfireShells (1080) : `...Active.Loki.HellfireShellsAbility$$.ctor` recopie les 0x40 octets
    # du MEME preset statique `<TargetingOptions statics>+0x140` que 1225/1196 puis appelle
    # `AActiveAbility..ctor(this, &opts, 0)` -- le 3e argument est le litteral `0`. TRANSCRIT au
    # decompile ; le preset ne dit RIEN de l'attack-type (le 3e argument en est independant, et le
    # lot #499/#511 en porte les contre-exemples dans les deux sens). (#605)
    ActiveAbilityType.HellfireShells: AbilityAttackType.DirectTargetAttack,  # 1080
    ActiveAbilityType.ThunderousAssault: AbilityAttackType.DirectTargetAttack,  # 1043
    # IncendiaryShells (1044) : `...Active.Loki.IncendiaryShellsAbility$$.ctor` recopie les 0x40
    # octets du preset statique `<TargetingOptions statics>+0x140` -- le MEME que 1080 ci-dessus --
    # puis `AActiveAbility..ctor(this, &opts, 0)`. Le `0` est LU AU DESASSEMBLAGE (`xor r8d, r8d`
    # juste avant le `call`), pas au pseudo-C : c'est le seul canal ou un immediat perdu se verrait.
    # Le preset partage avec 1080 ne dit RIEN de l'attack-type -- 1191/1195 partagent le preset
    # `+0x40` avec des litteraux `0` et `2`. (#907)
    ActiveAbilityType.IncendiaryShells: AbilityAttackType.DirectTargetAttack,  # 1044
    # FragstormGrenadeLauncher (1048) : `FragstormGrenadeLauncherAbility$$.ctor` copie le preset
    # `TargetingOptions` statics `+0x180`, appelle la surcharge PRESET+FLAGS puis
    # `AActiveAbility..ctor(this, &opts, 0)` -> litteral `0`. (#489)
    ActiveAbilityType.FragstormGrenadeLauncher: AbilityAttackType.DirectTargetAttack,  # 1048
    ActiveAbilityType.FragBomb: AbilityAttackType.DirectTargetAttack,  # 1017
    ActiveAbilityType.BasiliskBarrage: AbilityAttackType.DirectTargetAttack,  # 1026
    ActiveAbilityType.Stikkbomb: AbilityAttackType.DirectTargetAttack,  # 1051
    ActiveAbilityType.SanctorumMissile: AbilityAttackType.DirectTargetAttack,  # 1062
    ActiveAbilityType.ScythingTalons: AbilityAttackType.DirectTargetAttack,  # 1065
    ActiveAbilityType.Executioner: AbilityAttackType.DirectTargetAttack,  # 1066
    ActiveAbilityType.HarvesterOfSouls: AbilityAttackType.DirectTargetAttack,  # 1067
    # `SilentDeathAbility$$.ctor` -> `AActiveAbility..ctor(this, &opts, 0)`. Le litteral est `0`, et
    # il est TRANSCRIT : ni deduit de la forme de l'arbre (une CHAINE de 4 attaques), ni du profil de
    # degat (`Piercing`). (#497)
    # Loki_SwoopingHawk (1064) : `SwoopingHawkAbility$$.ctor` n'a AUCUN corps propre
    # (`return DiveAttackAbilityBase$$.ctor(this);`) -- le litteral est donc lu sur la BASE, dont le
    # ctor recopie le preset statique `+0x40` puis appelle `AActiveAbility..ctor(this, &opts, 0)`.
    # 3e argument = `0`. Il vaut pour les DEUX heritieres de la base (1064 et 1091 SlashingDive).
    ActiveAbilityType.Loki_SwoopingHawk: AbilityAttackType.DirectTargetAttack,  # 1064 (#502)
    # SlashingDive (1091) : MEME lecture, et le partage n'est plus une deduction -- le slot de methode
    # de `SlashingDiveAbility` rend, au runtime, la MEME adresse d'entree de `.ctor` que
    # `SwoopingHawkAbility` (corps fusionne par IL2CPP), et AUCUNE surcharge a depth=0. Le litteral est
    # donc celui de `DiveAttackAbilityBase$$.ctor` -> `AActiveAbility..ctor(this, &opts, 0)` = `0`.
    # Transcrit tel quel : ni deduit du profil de degat (`Power`, different de 1064), ni de la forme
    # de l'arbre (une VAGUE de 3 tuiles, pas une cible unique). (#507)
    ActiveAbilityType.SlashingDive: AbilityAttackType.DirectTargetAttack,  # 1091 (#507)
    ActiveAbilityType.SilentDeath: AbilityAttackType.DirectTargetAttack,  # 1068
    # SeekerMissileFrequencyLock (1069, #491) : `...SeekerMissileFrequencyLockAbility$$.ctor` recopie
    # le preset statique `TargetingOptions statics+0x180` puis `AActiveAbility..ctor(this, &opts, 0)`.
    # MEME configuration que Drachnyen ci-dessus : le litteral est `0` bien que le behaviour
    # n'attaque PAS en direct (son `ExecuteBehaviour` ne pose que 3 effets, le degat appartient a la
    # triggered 1127). On transcrit le 3e argument du ctor, jamais le profil de degat de l'arbre.
    ActiveAbilityType.SeekerMissileFrequencyLock: AbilityAttackType.DirectTargetAttack,  # 1069
    # EmpyricAmbush (1232) : `EmpyricAmbushAbility$$.ctor` -> `AActiveAbility..ctor(this, &opts, 0)`.
    # Le litteral est `0` bien que le behaviour commence par un `FlyUnit` : on transcrit le 3e argument
    # du ctor, jamais la forme de l'arbre. (#589-r1-r1-r1)
    ActiveAbilityType.EmpyricAmbush: AbilityAttackType.DirectTargetAttack,  # 1232
    # KissOfDeath (1108) : `...Active.Loki.KissOfDeathAbility$$.ctor` ne construit AUCUN
    # `TargetingOptions` -- il RECOPIE les 0x40 octets du preset statique
    # `<TargetingOptions statics>+0x40` puis appelle `AActiveAbility..ctor(this, &opts, 0)`. Le 3e
    # argument est le litteral `0`. TRANSCRIT, jamais deduit de l'arbre : celui-ci commence par un
    # `AddEffect` et finit par un `RemoveEffect`, et son degat passe par une CHAINE
    # (`ChainAttackDamage`), pas par une attaque directe -- la forme ne dit rien du litteral. (#940)
    ActiveAbilityType.KissOfDeath: AbilityAttackType.DirectTargetAttack,  # 1108
    # MortarionsPlagueWind (1093) et ReapingScythe (1095), les deux actives de degat de
    # `deathBossMortarion` (#888). Leurs ctors sont tous deux des STATIC-COPY (aucun appel a
    # `TargetingOptions$$.ctor`) et finissent par `AActiveAbility$$.ctor(this, &opts, 0)` -- 3e
    # argument = litteral `0`. TRANSCRIT, jamais deduit : ni de la forme de l'arbre (1093 est une AoE
    # a trois bandes, pas une frappe mono-cible), ni du profil (`Psychic` / `Chain`). Les DEUX ctors
    # copient des presets DIFFERENTS (`statics+0x180` pour 1093, `statics+0x40` pour 1095) et
    # portent pourtant le MEME 3e argument : le preset ne predit pas ce litteral, on l'a relu.
    # Le troisieme actif du boss, `1094 TheLantern`, porte `2` (`Others`) -- cf. plus bas.
    ActiveAbilityType.MortarionsPlagueWind: AbilityAttackType.DirectTargetAttack,  # 1093
    ActiveAbilityType.ReapingScythe: AbilityAttackType.DirectTargetAttack,  # 1095
    # TheLantern (1094, `deathBossMortarion`) -- le TROISIEME actif du boss, et le SEUL des trois a
    # ne pas valoir `0`. `IdunBattleLogic.Entities.Abilities.Active.Loki.TheLanternAbility$$.ctor`
    # construit ses options par la surcharge FLAGS DIRECTS a 6 parametres puis appelle
    # `AActiveAbility..ctor(this, &opts, 2)` -- 3e argument = litteral `2` = `Others`. TRANSCRIT,
    # RELU au decompile de ce build (#1030), jamais deduit : ni du profil (`Energy`), ni de la forme
    # de l'arbre (le cast ne frappe PAS -- il pose trois effets, et le degat appartient a la
    # triggered 1167 du tour suivant).
    ActiveAbilityType.TheLantern: AbilityAttackType.Others,  # 1094
    ActiveAbilityType.Fragstorm: AbilityAttackType.DirectTargetAttack,  # 1078
    # HellfyreMissileRack (1088, thousTerminator « Toth ») : `IdunBattleLogic.Entities.Abilities.
    # Active.Loki.HellfyreMissileRackAbility$$.ctor` -> `AActiveAbility..ctor(this, &opts, 0)`.
    # 3e argument = `0` = DirectTargetAttack. Litteral RELU au decompile (#487) ; il vaut `0` bien
    # que l'arbre frappe AUSSI des unites board-wide via `SortedAttackSeries` -- on transcrit le 3e
    # argument du ctor, jamais la forme du ciblage (meme regle que MurderousSwing ci-dessous).
    ActiveAbilityType.HellfyreMissileRack: AbilityAttackType.DirectTargetAttack,  # 1088
    # HeavyWarpFlamer (1227, thousSekhetar « Sekhetar Robot ») : `IdunBattleLogic.Entities.Abilities.
    # Active.Loki.HeavyWarpFlamerAbility$$.ctor` recopie les 0x40 octets du preset statique
    # `<TargetingOptions statics>+0x140` (AUCUN appel a `TargetingOptions$$.ctor`, donc aucun flag
    # ajoute) puis `AActiveAbility..ctor(this, &opts, 0)` -> 3e argument = litteral `0`. TRANSCRIT,
    # jamais deduit du profil de degat (`Flame`) ni de la chaine de report. (#523)
    ActiveAbilityType.HeavyWarpFlamer: AbilityAttackType.DirectTargetAttack,  # 1227
    ActiveAbilityType.GreatFrostAxe: AbilityAttackType.DirectTargetAttack,  # 1089
    ActiveAbilityType.DarkTalonStrike: AbilityAttackType.DirectTargetAttack,  # 1092
    ActiveAbilityType.PlasmaGrenade: AbilityAttackType.DirectTargetAttack,  # 1098
    ActiveAbilityType.SpiritLeech: AbilityAttackType.DirectTargetAttack,  # 1104
    ActiveAbilityType.CrushingClaws: AbilityAttackType.DirectTargetAttack,  # 1105
    ActiveAbilityType.Stormcaller: AbilityAttackType.DirectTargetAttack,  # 1113
    ActiveAbilityType.CordClaw: AbilityAttackType.DirectTargetAttack,  # 1122
    ActiveAbilityType.JakhalStimms: AbilityAttackType.DirectTargetAttack,  # 1131
    # KillMaimBurn (1132, worldKharn) : `IdunBattleLogic.Entities.Abilities.Active.Loki.
    # KillMaimBurnAbility$$.ctor` recopie le preset statique `<TargetingOptions statics>+0x40` puis
    # `AActiveAbility..ctor(this, &opts, 0)` -- le 3e argument est le litteral `0`. RELU au
    # decompile (#504) ; il vaut `0` bien que l'arbre porte TROIS attaques a cibles distinctes.
    ActiveAbilityType.KillMaimBurn: AbilityAttackType.DirectTargetAttack,  # 1132
    # MurderousSwing (1137) : `IdunBattleLogic.Entities.Abilities.Active.MurderousSwingAbility$$.ctor`
    # -> `AActiveAbility..ctor(this, &opts, 0, 0)`. Litteral RELU au decompile ; il vaut `0` bien que
    # l'arbre soit un splash MULTI-cible self-centre (on transcrit le 3e argument du ctor, jamais la
    # forme du ciblage).
    ActiveAbilityType.MurderousSwing: AbilityAttackType.DirectTargetAttack,  # 1137
    ActiveAbilityType.SentinelDirectives: AbilityAttackType.DirectTargetAttack,  # 1139
    ActiveAbilityType.HadesAutocannons: AbilityAttackType.DirectTargetAttack,  # 1147
    ActiveAbilityType.DaemonicOrdnance: AbilityAttackType.DirectTargetAttack,  # 1148
    ActiveAbilityType.PlasmaCannon: AbilityAttackType.DirectTargetAttack,  # 1150
    # #997 -- litteral TRANSCRIT du 3e argument d'`AActiveAbility..ctor(this, &opts, 0)`, jamais
    # deduit du nom ni du profil de degat.
    # `IdunBattleLogic.Entities.Abilities.Active.Loki.ExplosivePresentsAbility$$.ctor` -> `0`.
    ActiveAbilityType.ExplosivePresents: AbilityAttackType.DirectTargetAttack,  # 1170
    # `IdunBattleLogic.Entities.Abilities.Active.BlightGrenadesAbility$$.ctor` (namespace SANS `Loki`)
    # -> `0`, apres les DEUX ctors de `TargetingOptions` (preset inline puis PRESET+FLAGS).
    ActiveAbilityType.BlightGrenades: AbilityAttackType.DirectTargetAttack,  # 1176
    ActiveAbilityType.HeavyRailRifle: AbilityAttackType.DirectTargetAttack,  # 1160
    ActiveAbilityType.TwinSmartMissileSystem: AbilityAttackType.DirectTargetAttack,  # 1161
    # MightFromBelow (1165) : `MightFromBelowAbility$$.ctor` recopie le preset statique
    # `<TargetingOptions statics>+0x40` puis appelle `AActiveAbility..ctor(this, &opts, 0)` -- le
    # 3e argument est le litteral `0`. Il vaut `DirectTargetAttack` MEME si l'arbre summone en
    # troisieme phase : on transcrit le litteral du ctor, jamais ce que fait le behaviour
    # (`1 = SummonAndAttackTarget` est ce que porte `IncursionAbility`, pas celle-ci). (#501)
    # BioMinefield (1144) : `BioMinefieldAbility$$.ctor` -> `AActiveAbility$$.ctor(this, &opts, 2)`.
    # Le 3e argument du ctor de base EST l'`AbilityAttackType`, et il vaut 2 = `Others` -- LU au
    # ctor, pas deduit : l'ability n'inflige AUCUN degat direct (elle marque, deplace, tue ses
    # propres mines, ou en pose). #939
    ActiveAbilityType.BioMinefield: AbilityAttackType.Others,  # 1144
    ActiveAbilityType.MightFromBelow: AbilityAttackType.DirectTargetAttack,  # 1165
    ActiveAbilityType.EntropyCannons: AbilityAttackType.DirectTargetAttack,  # 1168
    ActiveAbilityType.PlagueburstMortar: AbilityAttackType.DirectTargetAttack,  # 1169
    ActiveAbilityType.HeroicFusillade: AbilityAttackType.DirectTargetAttack,  # 1180
    # `IdunBattleLogic.Entities.Abilities.Active.Loki.ExcruciatingFrequenciesAbility$$.ctor` ->
    # `AActiveAbility..ctor(this, &opts, 2)` : 3e argument = **2 = Others** (#512). TRANSCRIT TEL
    # QUEL, surtout pas deduit du comportement : 1197 EST une attaque (nrOfHits coups Blast) et
    # porterait donc `DirectTargetAttack` a l'oeil -- le litteral dit `Others`, et c'est lui qui
    # decide de `AbilityHasAttackType(0|1)` (gate SwornProtector).
    ActiveAbilityType.ExcruciatingFrequencies: AbilityAttackType.Others,  # 1197
    # `IdunBattleLogic.Entities.Abilities.Active.Loki.TalonsOfTheEmperorAbility$$.ctor` ->
    # `AActiveAbility..ctor(this, &opts, 2)` : 3e argument = **2 = Others** (#521). TRANSCRIT TEL
    # QUEL, surtout pas deduit du comportement : 1195 est une attaque DIRECTE mono-cible sur la
    # cible du message (`If(cond, 1x DirectDamage, 1x Power)`) et porterait `DirectTargetAttack` a
    # l'oeil -- le litteral dit `Others`. Contraste `1191 MartialInspiration`, du MEME module et du
    # MEME preset de `TargetingOptions`, dont le litteral vaut `0`.
    ActiveAbilityType.TalonsOfTheEmperor: AbilityAttackType.Others,  # 1195
    # `IdunBattleLogic.Entities.Abilities.Active.Loki.UnbreakableDutyAbility$$.ctor` recopie les
    # 3 qwords du champ statique `<TargetingRange statics>+0x18`, appelle la surcharge FLAGS DIRECTS
    # `TargetingOptions..ctor(&opts, 1, &range, 1, 0x8400, 0, 0)` puis
    # `AActiveAbility..ctor(this, &opts, 2)` : 3e argument = **2 = Others** (#572). TRANSCRIT TEL
    # QUEL, surtout pas deduit de l'arbre : 1061 FRAPPE (attaque NORMALE gratuite dispatchee par
    # `UseActiveAbility(Loki_NormalAttack)`), exactement comme `HolyDuel` 1050 et `Drachnyen` 1029 --
    # qui, eux, portent `0`. Meme forme d'arbre, litteral OPPOSE : c'est le contre-exemple de plus.
    ActiveAbilityType.UnbreakableDuty: AbilityAttackType.Others,  # 1061
    # `IdunBattleLogic.Entities.Abilities.Active.Loki.CrusadeOfWrathAbility$$.ctor` recopie les
    # 3 qwords du champ statique `<TargetingRange statics>+0x18` (le MEME que 1061), appelle la
    # surcharge FLAGS DIRECTS `TargetingOptions..ctor(&opts, 1, &range, 1, 0x400, 0, 0)` puis
    # `AActiveAbility..ctor(this, &opts, 2)` : 3e argument = **2 = Others** (#893). TRANSCRIT TEL
    # QUEL : 1049 FRAPPE (attaque NORMALE gratuite dispatchee par `UseActiveAbility(
    # UnitNormalAttackType(Owner))`), exactement comme `HolyDuel` 1050 -- qui, lui, porte `0`.
    ActiveAbilityType.CrusadeOfWrath: AbilityAttackType.Others,  # 1049
    # `IdunBattleLogic.Entities.Abilities.Active.Loki.EuphoricStrikesAbility$$.ctor` ->
    # `AActiveAbility..ctor(this, &preset, 0)` : 3e argument = **0 = DirectTargetAttack** (#522).
    # Le ctor est de la forme PRESET STATIQUE COPIE (il recopie les 0x40 octets de
    # `TargetingOptions statics+0x40` et les passe TELS QUELS, sans surcharge preset+flags --
    # contraste avec `ThunderousAssaultAbility$$.ctor`, qui lit le MEME preset puis y OR-e
    # `0x10000000`). Le litteral est donc lu sur l'appel, pas deduit du profil de degat.
    # ⚠ Voisin IMMEDIAT et litteral OPPOSE : `1195` juste au-dessus vaut `Others`. Les deux sont LUS
    # sur leur propre appel, jamais deduits du fait que ce sont deux attaques directes mono-cible.
    ActiveAbilityType.EuphoricStrikes: AbilityAttackType.DirectTargetAttack,  # 1198
    # `IdunBattleLogic.Entities.Abilities.Active.Loki.TheLionsWrathAbility$$.ctor` ->
    # `AActiveAbility..ctor(this, &opts, 0)` : 3e argument = **0 = DirectTargetAttack** (#889).
    # Meme forme de ctor que `1198` ci-dessus -- PRESET STATIQUE COPIE (les 0x40 octets de
    # `TargetingOptions statics+0x40`, passes TELS QUELS, aucune surcharge preset+flags) -- et donc
    # meme lecture : le litteral est pris sur l'appel, pas deduit du fait que le cast frappe.
    # ⚠ Le cast arme AUSSI une attaque DIFFEREE (la triggered 1520, profil `Piercing`), et
    # l'`AbilityAttackType` ne le dit pas : il qualifie le CAST, pas la mecanique.
    ActiveAbilityType.TheLionsWrath: AbilityAttackType.DirectTargetAttack,  # 1217
    # `IdunBattleLogic.Entities.Abilities.Active.Loki.MartialExemplarAbility$$.ctor` ->
    # `AActiveAbility..ctor(this, &opts, 2)` : 3e argument = **2 = Others** (#889-r5).
    # ⚠ **LITTERAL OPPOSE A CELUI DE SA JUMELLE**, ligne du dessus : 1216 et 1217 sont les DEUX
    # actives du MEME boss (`darkaBossLion`), toutes deux frappent, et pourtant l'une vaut `0` et
    # l'autre `2`. Le deduire du profil de degat ou de la parente aurait ecrit `0`. Ce qui les
    # separe est la FORME du ctor, lue octet a octet : 1217 recopie le preset `statics+0x40` TEL
    # QUEL (STATIC-COPY), 1216 recopie `statics+0x280` puis appelle la surcharge PRESET+FLAGS avec
    # `additionalRules = 0x10` -- et son 3e argument a `AActiveAbility..ctor` est `2`.
    # ⚠ Le cast enchaine AUSSI une ATTAQUE NORMALE (`UseNormalAttack`/`UseNormalAttackIfAble`), et
    # l'`AbilityAttackType` ne le dit pas : il qualifie le CAST, pas la mecanique.
    ActiveAbilityType.MartialExemplar: AbilityAttackType.Others,  # 1216
    # `IdunBattleLogic.Entities.Abilities.Active.Loki.SternguardFocusAbility$$.ctor` ->
    # `AActiveAbility..ctor(this, &opts, 2, 0)` : 3e argument = **2 = Others** (#905). Le litteral
    # est lu au DESASSEMBLAGE (`mov r8d, 2` juste avant le `call`) parce que le decompile ghidra
    # avait perdu l'immediat -- pas deduit du fait que le cast FRAPPE. ⚠ Il frappe pourtant, et par
    # une ATTAQUE NORMALE (`UseNormalAttack`) : l'`AbilityAttackType` qualifie le CAST, pas la
    # mecanique -- meme lecture que 1216/1049, et litteral OPPOSE a celui de `1198`/`1217`, qui
    # frappent aussi et valent `0`. Son ctor est de la forme PRESET STATIQUE COPIE (les 0x40 octets
    # de `TargetingOptions statics+0x00`, passes TELS QUELS) -- ses `TARGETING_OPTIONS` SONT donc
    # posees (le masque `0x4002` est lu dans `TargetingOptions$$.cctor` a `<preset>+0x28`).
    ActiveAbilityType.SternguardFocus: AbilityAttackType.Others,  # 1228
    # `IdunBattleLogic.Entities.Abilities.Active.Loki.DoomSirenAbility$$.ctor` ->
    # `AActiveAbility..ctor(this, &opts, 0, 0)` : 3e argument = 0 = DirectTargetAttack.
    ActiveAbilityType.DoomSiren: AbilityAttackType.DirectTargetAttack,  # 1199
    ActiveAbilityType.SquigLaunchas: AbilityAttackType.DirectTargetAttack,  # 1200
    ActiveAbilityType.SquigMine: AbilityAttackType.DirectTargetAttack,  # 1201
    ActiveAbilityType.VigilanceEternal: AbilityAttackType.DirectTargetAttack,  # 1202
    # `IdunBattleLogic.Entities.Abilities.Active.Loki.LeadingTheChargeAbility$$.ctor` ->
    # `AActiveAbility..ctor(this, &opts, 0)` : 3e argument = 0 = DirectTargetAttack (LU, #508 --
    # le ctor ne fait qu'y recopier le preset `TargetingOptions statics+0x240` avant l'appel).
    ActiveAbilityType.LeadingTheCharge: AbilityAttackType.DirectTargetAttack,  # 1204
    ActiveAbilityType.DeathOnTheWind: AbilityAttackType.DirectTargetAttack,  # 1213
    ActiveAbilityType.AugmentedAssault: AbilityAttackType.DirectTargetAttack,  # 1221
    # `IdunBattleLogic.Entities.Abilities.Active.Loki.MassDriverAcceleratorAbility$$.ctor` ->
    # `AActiveAbility..ctor(this, &opts, 0)` : 3e argument = 0 = DirectTargetAttack (LU, #525 -- le
    # ctor est BYTE-IDENTIQUE a celui de 1204 : meme preset `TargetingOptions statics+0x240` recopie,
    # meme litteral). TRANSCRIT, pas deduit du comportement : 1222 est une CHARGE qui pose d'abord un
    # stat-mod et se DEPLACE, et son 2e volet de degat est un SPLASH multi-cible.
    ActiveAbilityType.MassDriverAccelerator: AbilityAttackType.DirectTargetAttack,  # 1222
    ActiveAbilityType.SavageEchoes: AbilityAttackType.DirectTargetAttack,  # 1230
    ActiveAbilityType.Supercharge: AbilityAttackType.DirectTargetAttack,  # 1103 (lot #112, litteral 0 relu)
    # DakkaDakkaDakka (1171, Snappawrecka orksKillaKan), case-decision-noop. Litteral RELU :
    # `IdunBattleLogic.Entities.Abilities.Active.Loki.DakkaDakkaDakkaAbility$$.ctor` =
    # `AActiveAbility..ctor(this, &opts, 0, 0)` -> 3e argument = 0 = DirectTargetAttack.
    # (`&opts` = le PRESET statique `TargetingOptions` `+0x140` -- le MEME que 1006/1206, dont le
    #  masque a ete lu dans `IdunBattle.Core.Services.TargetingOptions$$.cctor` : les
    #  `TARGETING_OPTIONS` de 1171 SONT donc posees, cf. la classe.)
    ActiveAbilityType.DakkaDakkaDakka: AbilityAttackType.DirectTargetAttack,  # 1171
    # RammingSpeed (1059), #389. Litteral RELU :
    # `IdunBattleLogic.Entities.Abilities.Active.Loki.RammingSpeedAbility$$.ctor` =
    # `AActiveAbility..ctor(this, &opts, 0)` -> 3e argument = 0 = DirectTargetAttack. (`&opts` = la
    # forme FLAGS DIRECTS, `rules = 0x4002` litteral -> les `TARGETING_OPTIONS` sont posees aussi.)
    ActiveAbilityType.RammingSpeed: AbilityAttackType.DirectTargetAttack,  # 1059
    # FrenziedFiring (1036, Volk blackObliterator) : entree dans `ABILITY_CLASSES` par le lot #61
    # (face COMBAT du volet AoE) SANS son litteral -> l'etape 0 du garde-fou
    # `probe_120_pre_unit_ability_fork` echouait (« ability portee sans AbilityAttackType lu »).
    # Litteral RELU : `IdunBattleLogic.Entities.Abilities.Active.Loki.FrenziedFiringAbility$$.ctor`
    # = `AActiveAbility..ctor(this, &opts, 0, 0)` -> 3e argument = 0 = DirectTargetAttack.
    # (⚠ le `&opts` y est un PRESET lu d'un champ STATIQUE de la classe, PAS un litteral inline :
    #  ses `TARGETING_OPTIONS` restent donc NON renseignes -- les deviner serait pire que l'absence.)
    ActiveAbilityType.FrenziedFiring: AbilityAttackType.DirectTargetAttack,  # 1036
    # TacticalPrecision (1154, Titus ultraTitus), case-231. Litteral RELU :
    # `IdunBattleLogic.Entities.Abilities.Active.Loki.TacticalPrecisionAbility$$.ctor` =
    # `AActiveAbility..ctor(this, &opts, 0, 0)` -> 3e argument = 0 = DirectTargetAttack.
    # (Contrairement a 1036/1041, ses `TARGETING_OPTIONS` SONT posees : le preset statique recopie
    #  a ete lu dans `IdunBattle.Core.Services.TargetingOptions$$.cctor`, cf. la classe.)
    ActiveAbilityType.TacticalPrecision: AbilityAttackType.DirectTargetAttack,  # 1154
    # BrazierOfHolyFire (1041) : MEME cas que 1036, entree au registre par le lot #128 sans son
    # litteral. `IdunBattleLogic.Entities.Abilities.Active.Loki.BrazierOfHolyFireAbility$$.ctor`
    # = `AActiveAbility..ctor(this, &opts, 0, 0)` -> 0 = DirectTargetAttack (opts = PRESET statique).
    ActiveAbilityType.BrazierOfHolyFire: AbilityAttackType.DirectTargetAttack,  # 1041
    # Foehammer (1097, Arjac spaceRockfist) et HammerOfWrath (1153, Mataneo bloodIntercessor), lot
    # #226. Litteraux RELUS : `...FoehammerAbility$$.ctor` et `...HammerOfWrathAbility$$.ctor` font
    # tous deux `AActiveAbility..ctor(this, &opts, 0, 0)` -> 3e argument = 0 = DirectTargetAttack.
    # (`&opts` = un PRESET statique de `TargetingOptions` dans les DEUX cas -- mais ici le masque
    #  EFFECTIF a bien ete lu dans `IdunBattle.Core.Services.TargetingOptions$$.cctor`
    #  (`statics+0x168` = 0x4002 pour 1097, `statics+0x268` = 0x102004032 pour 1153), donc leurs
    #  `TARGETING_OPTIONS` sont renseignes -- contraste 1036/1041 ci-dessus.)
    # GrapnelLauncher (1090, Tjark spaceHound) -- #366-r1 tranche 2. Litteral RELU :
    # `IdunBattleLogic.Entities.Abilities.Active.Loki.GrapnelLauncherAbility$$.ctor` =
    # `AActiveAbility..ctor(this, &opts, 0)` -> 3e argument = 0 = DirectTargetAttack. (`&opts` est la
    # forme FLAGS DIRECTS a 6 arguments, `rules = 0x8004000` litteral -> `TARGETING_OPTIONS` posees.)
    ActiveAbilityType.GrapnelLauncher: AbilityAttackType.DirectTargetAttack,  # 1090
    ActiveAbilityType.Foehammer: AbilityAttackType.DirectTargetAttack,  # 1097
    ActiveAbilityType.HammerOfWrath: AbilityAttackType.DirectTargetAttack,  # 1153
    # LightOfSanguinius (1177, Dante bloodDante), #510. Litteral RELU :
    # `IdunBattleLogic.Entities.Abilities.Active.LightOfSanguiniusAbility$$.ctor` =
    # `AActiveAbility..ctor(this, &opts, 0)` -> 3e argument = `0` = DirectTargetAttack, transcrit tel
    # quel. (`&opts` = le MEME PRESET statique `<TargetingOptions statics>+0x240` que 1153 ci-dessus,
    #  donc le meme masque EFFECTIF `statics+0x268` = 0x102004032 -- ses `TARGETING_OPTIONS` vivent
    #  sur la classe du registre depuis #510.)
    ActiveAbilityType.LightOfSanguinius: AbilityAttackType.DirectTargetAttack,  # 1177
    # UnstoppableMomentumReworked (1152, Tanksmasha orksNob), #498. Litteral RELU :
    # `IdunBattleLogic.Entities.Abilities.Active.Loki.UnstoppableMomentumReworkedAbility$$.ctor` =
    # `AActiveAbility..ctor(this, &opts, 0)` -> 3e argument = `0` = DirectTargetAttack. Transcrit tel
    # quel : la cible du MESSAGE est pourtant une TUILE (`TargetIsTile`) et l'attaque ne frappe pas
    # cette cible mais les occupants de la ligne de charge -- on transcrit le 3e argument du ctor,
    # jamais la forme de l'arbre (meme regle que Drachnyen 1029 / SeekerMissile 1069 ci-dessus).
    # (`&opts` est la forme FLAGS DIRECTS a 7 arguments, `rules = 0x10120040` litteral -> ses
    #  `TARGETING_OPTIONS` vivent sur la classe du registre.)
    ActiveAbilityType.UnstoppableMomentumReworked: AbilityAttackType.DirectTargetAttack,  # 1152
    # PlagueWind (1035, Typhus deathTyphus), case-psychic-aoe. Litteral RELU :
    # `IdunBattleLogic.Entities.Abilities.Active.Loki.PlagueWindAbility$$.ctor` =
    # `AActiveAbility..ctor(this, &opts, 0, 0)` -> 3e argument = 0 = DirectTargetAttack.
    # (`&opts` = PRESET statique `TargetingOptions statics+0x180` ; son masque EFFECTIF a bien ete lu
    #  dans le `cctor` (`statics+0x1a8` = 0x4002) -> ses `TARGETING_OPTIONS` sont renseignes.)
    ActiveAbilityType.PlagueWind: AbilityAttackType.DirectTargetAttack,  # 1035
    # StranglethornCannon (1056, `tyranBossHiveTyrantLeviathan` « Hive Tyrant »). Litteral LU :
    # `IdunBattleLogic.Entities.Abilities.Active.Loki.StranglethornCannonAbility$$.ctor` finit par
    # `AActiveAbility..ctor(this, &opts, 0)` -> 3e argument = 0 = DirectTargetAttack. TRANSCRIT.
    # (`&opts` = PRESET `TargetingOptions statics+0x140` PLUS le flag `0x100000000` via la surcharge
    #  PRESET+FLAGS -- masque EFFECTIF `0x100004002` ; ses `TARGETING_OPTIONS` vivent sur la classe du
    #  registre `abilities/tyranids.py::StranglethornCannonAbility`.) (#890)
    ActiveAbilityType.StranglethornCannon: AbilityAttackType.DirectTargetAttack,  # 1056
    # --- 1 : SummonAndAttackTarget (le summon pose attaque la cible du cast) --------------------
    ActiveAbilityType.DeathFromAbove: AbilityAttackType.SummonAndAttackTarget,  # 1003
    ActiveAbilityType.ScarabHive: AbilityAttackType.SummonAndAttackTarget,  # 1007
    ActiveAbilityType.SendInTheNextWave: AbilityAttackType.SummonAndAttackTarget,  # 1016
    ActiveAbilityType.Incursion: AbilityAttackType.SummonAndAttackTarget,  # 1021
    ActiveAbilityType.Poxwalkers: AbilityAttackType.SummonAndAttackTarget,  # 1040 SpawnPoxwalkersAbility
    # 1076 : sa classe native est un TRIGGERED
    # (`...Triggered.Loki.MV71SniperDroneSquadAttackAbility$$.ctor`) mais elle derive de
    # `ALoki_NormalAttackAbility`, dont le ctor FORWARDE son 3e argument a `AActiveAbility$$.ctor` :
    # `ALoki_NormalAttackAbility..ctor(this, &opts, 1)` -> 1.
    ActiveAbilityType.MV71SniperDroneSquadAttack: AbilityAttackType.SummonAndAttackTarget,  # 1076
    # --- 2 : Others (y compris des abilities qui font pourtant des degats -- le natif les CLASSE
    #         hors « attaque directe sur la cible » : AoE de zone, charge-puis-frappe, tile-target) -
    # Reparation REGULIERE (#299). `IdunBattleLogic.Entities.Abilities.Active.RepairAbility$$.ctor`
    # finit par `ADeprecatedActiveAbility..ctor(this, &opts, 2)`, et
    # `IdunBattle.Entities.Abilities.ADeprecatedActiveAbility$$.ctor` FORWARDE ce 3e argument tel quel
    # a `AActiveAbility$$.ctor` (il ne fait que recopier les 0x40 octets des `TargetingOptions`) -> 2.
    # `IdunBattleLogic.Entities.Abilities.Active.Loki.Repair_GalvanicFieldAbility$$.ctor` = `return
    # RepairAbility..ctor(this)` -> MEME litteral, herite et non recopie a l'aveugle.
    # Catalyst (1032, `tyranBossHiveTyrantLeviathan` « Hive Tyrant »). Litteral LU :
    # `IdunBattleLogic.Entities.Abilities.Active.Loki.CatalystAbility$$.ctor` finit par
    # `AActiveAbility..ctor(this, &opts, 2)` -> 3e argument = 2 = Others. TRANSCRIT.
    # (`&opts` = recopie des 0x40 octets du PRESET `TargetingOptions statics+0x280`, forme
    #  STATIC-COPY, masque `0x8004` ; `TARGETING_OPTIONS` sur la classe du registre.) (#890)
    ActiveAbilityType.Catalyst: AbilityAttackType.Others,  # 1032
    # ExemplarOfTheMontka (1210, `tauFarsight` « Commander Farsight »). Litteral LU aux OCTETS du
    # ctor, jamais deduit du fait que le cast ne frappe personne :
    # `IdunBattleLogic.Entities.Abilities.Active.Loki.ExemplarOfTheMontkaAbility$$.ctor` recopie les
    # 0x40 octets du PRESET `<TargetingOptions statics>+0x280` (forme STATIC-COPY, masque `0x8004`,
    # `TARGETING_OPTIONS` sur la classe du registre) puis finit par
    # `AActiveAbility..ctor(this, &opts, 2)` -> 3e argument = 2 = Others. TRANSCRIT.
    ActiveAbilityType.ExemplarOfTheMontka: AbilityAttackType.Others,  # 1210
    # Reveal (1107, `eldarNpc2Warlock`). Litteral LU aux OCTETS du ctor, jamais deduit du fait que
    # le cast ne frappe personne : `IdunBattleLogic.Entities.Abilities.Active.Loki.RevealAbility$$
    # .ctor` recopie le PRESET `<TargetingOptions statics>+0x180` puis appelle la surcharge
    # PRESET+FLAGS `TargetingOptions..ctor(&opts, &preset, 0x6000002)` (masque EFFECTIF `0x6004002`,
    # `TARGETING_OPTIONS` sur la classe du registre) et finit par
    # `AActiveAbility..ctor(this, &opts, 2)` -> 3e argument = 2 = Others. TRANSCRIT. (#1033)
    ActiveAbilityType.Reveal: AbilityAttackType.Others,  # 1107
    ActiveAbilityType.Repair: AbilityAttackType.Others,  # 28 RepairAbility (derivee du trait Mechanic)
    # Heal (18, derivee du trait `Healer`) -- #931-r1. Litteral RELU sur son ctor, jamais deduit du
    # voisin `28 Repair` ni du fait que le cast ne frappe personne :
    # `IdunBattleLogic.Entities.Abilities.Active.Common.HealAbility$$.ctor` recopie les 0x40 octets
    # du preset `<TargetingOptions statics>+0x100` (forme STATIC-COPY, masque `0x8500`) puis finit
    # par `ADeprecatedActiveAbility..ctor(this, &opts, 2)` -> 3e argument = 2 = Others. Coherent :
    # l'arbre de son `$$CreateBehaviour` est la feuille `Heal` NUE (aucun noeud d'attaque), et 18
    # n'a AUCUNE entree gameconfig, donc aucun `damageProfile`.
    ActiveAbilityType.Heal: AbilityAttackType.Others,  # 18 Common.HealAbility (derivee du trait Healer)
    ActiveAbilityType.Repair_GalvanicField: AbilityAttackType.Others,  # 1119 (passif GalvanicField)
    # `DefendTheDivineWorkAbility$$.ctor` -> `AActiveAbility..ctor(this, &opts, 2)` : le litteral EST
    # `2`, relu au decompile (et NON deduit du fait que l'ability ne fait pas de degat direct -- le
    # coup gratuit de GalvanicField, lui, en fait).
    ActiveAbilityType.DefendTheDivineWork: AbilityAttackType.Others,  # 1117 (admecManipulus)
    # WallOfMirrorsAbility$$.ctor -> `AActiveAbility..ctor(this, &opts, 2)` (#433-r4-r1-r1). Le
    # litteral est `2` MEME si l'arbre attaque : il dispatche l'attaque NORMALE par `UseNormalAttack`
    # (meme lecture que Drachnyen, transcrite en sens inverse) -- on transcrit le 3e argument du ctor.
    ActiveAbilityType.WallOfMirrors: AbilityAttackType.Others,  # 1186
    ActiveAbilityType.GauntletsOfUltramar: AbilityAttackType.Others,  # 1000
    ActiveAbilityType.CombatRestoratives: AbilityAttackType.Others,  # 1002
    ActiveAbilityType.ResurrectionOrb: AbilityAttackType.Others,  # 1009
    # AdaptiveStrategy (1005, necroWarden) -- #577. Litteral TRANSCRIT, jamais deduit :
    # `IdunBattleLogic.Entities.Abilities.Active.Loki.AdaptiveStrategyAbility$$.ctor` finit par
    # `AActiveAbility..ctor(this, &opts, 2)` -> 3e argument = 2 = Others. La lecture est facile a
    # se donner a POSTERIORI (le cast ne frappe personne : il override l'Attack d'allies, les fait
    # AGIR, puis retire l'override) -- mais c'est le litteral qui tranche, pas ce raisonnement :
    # sur ce meme axe, `WallOfMirrors` et `StormOfWrath` ci-dessus le contredisent chacun dans un
    # sens (l'une ATTAQUE et vaut 2, l'autre n'attaque pas en direct et vaut 0).
    ActiveAbilityType.AdaptiveStrategy: AbilityAttackType.Others,  # 1005
    # TunnelingHorror (1011, necroSmnDestroyer) -- #366-r1. Litteral RELU :
    # `IdunBattleLogic.Entities.Abilities.Active.Loki.TunnelingHorrorAbility$$.ctor` =
    # `AActiveAbility..ctor(this, &opts, 2)` -> 3e argument = 2 = Others (le behaviour n'attaque pas :
    # il retire le caster de ses tuiles et pose un bond sur la tuile visee).
    ActiveAbilityType.TunnelingHorror: AbilityAttackType.Others,  # 1011
    # Burrowers (1023, tyranSmnRipperSwarm) -- tranche 1 de `#366-r1-tunnel-family`. Litteral RELU :
    # `IdunBattleLogic.Entities.Abilities.Active.Loki.BurrowersAbility$$.ctor` =
    # `AActiveAbility..ctor(this, &opts, 2)` -> 3e argument = 2 = Others. RELU au decompile, pas
    # deduit du fait que le behaviour n'attaque pas (il retire le caster de ses tuiles et se pose un
    # effet).
    ActiveAbilityType.Burrowers: AbilityAttackType.Others,  # 1023
    # 1121 ItItches (`tyranParasiteOfMortrex`) -- LITTERAL RELU au decompile, et il CONTREDIT tout
    # ce qu'on croirait : `IdunBattleLogic.Entities.Abilities.Active.Loki.ItItchesAbility$$.ctor` =
    # `AActiveAbility..ctor(this, &opts, 0)` -> 3e argument = **0 = DirectTargetAttack**, alors que
    # l'ability est classee SUMMON par l'audit, qu'elle INVOQUE bel et bien (`tyranSmnRipperSwarm`)
    # et qu'elle n'inflige AUCUN degat direct (son seul degat possible est le knockback d'une poussee
    # BLOQUEE). `SummonAndAttackTarget` (1) et `Others` (2) auraient tous deux paru plus naturels --
    # c'est exactement pourquoi la regle est de LIRE le litteral, jamais de le deduire du nom, du
    # profil de degat ni de la colonne d'audit.
    ActiveAbilityType.ItItches: AbilityAttackType.DirectTargetAttack,  # 1121
    # 1106 WarHowl (`spaceBlackmane` « Ragnar ») -- LITTERAL RELU au decompile :
    # `IdunBattleLogic.Entities.Abilities.Active.Loki.WarHowlAbility$$.ctor` se termine par
    # `AActiveAbility..ctor(this, &opts, 2)` -> 3e argument = **2 = Others**. TRANSCRIT, pas deduit
    # du fait que le behaviour n'attaque pas : le lot voisin porte les deux contre-exemples
    # (`1121 ItItches` = `DirectTargetAttack` sans degat direct, `1038 FoulInfusion` = `Others` avec
    # une attaque). (`&opts` = la forme PRESET + FLAGS, dont le masque EFFECTIF `0x8014` vit sur
    # `spacewolves.WarHowlAbility.TARGETING_OPTIONS`.)
    ActiveAbilityType.WarHowl: AbilityAttackType.Others,  # 1106
    # 1211 RitesOfMorkai (`spaceWolfPriest` « Baldr »), #906 -- LITTERAL RELU AU DESASSEMBLAGE :
    # `IdunBattleLogic.Entities.Abilities.Active.Loki.RitesOfMorkaiAbility$$.ctor` se termine par
    # `mov r8d, 2 ; call <AActiveAbility..ctor>` -> 3e argument = **2 = Others**. TRANSCRIT, et le
    # contre-sens etait ici particulierement facile : l'arbre ENCHAINE UNE ATTAQUE NORMALE, donc
    # « une ability qui frappe » aurait fait ecrire `DirectTargetAttack`. C'est le meme piege que
    # `1121 ItItches` pris a l'envers, et c'est pourquoi on lit le litteral. (`&opts` = la forme
    # FLAGS DIRECTS, dont le masque `0x2008402` vit sur `spacewolves.RitesOfMorkaiAbility`.)
    ActiveAbilityType.RitesOfMorkai: AbilityAttackType.Others,  # 1211
    ActiveAbilityType.ValkyrieStrike: AbilityAttackType.Others,  # 1018
    ActiveAbilityType.SupremeCommander: AbilityAttackType.Others,  # 1028
    ActiveAbilityType.RevitalizingMalignancy: AbilityAttackType.Others,  # 1037
    # RitesOfRestoration (1039, adeptHospitaller « Isabella »), #564. Litteral RELU :
    # `IdunBattleLogic.Entities.Abilities.Active.Loki.RitesOfRestorationAbility$$.ctor` =
    # `AActiveAbility..ctor(this, &opts, 2)` -> 3e argument = 2 = Others. TRANSCRIT du ctor : l'arbre
    # ne fait AUCUN degat (soin + resurrection), mais c'est le litteral qui decide, pas le profil --
    # le lot #499/#505 porte les deux contre-exemples dans l'autre sens.
    ActiveAbilityType.RitesOfRestoration: AbilityAttackType.Others,  # 1039
    # BloodChalice (1175, bloodSanguinary « Sanguinary Priest »), #576. Litteral RELU :
    # `IdunBattleLogic.Entities.Abilities.Active.BloodChaliceAbility$$.ctor` =
    # `AActiveAbility..ctor(this, &opts, 2)` -> 3e argument = 2 = Others. TRANSCRIT du ctor : l'arbre
    # ne frappe pas (SetAbsolute de PV + deux poses d'effet), mais c'est le litteral qui decide.
    ActiveAbilityType.BloodChalice: AbilityAttackType.Others,  # 1175
    # 1038 -- `...Active.Loki.FoulInfusionAbility$$.ctor` : `AActiveAbility..ctor(this, &opts, 2)`.
    # LITTERAL RELU au decompile, jamais deduit : l'ability EMET pourtant une attaque
    # (`UseNormalAttack` en 2e volet de son `op_Addition`), et sa categorie d'audit est
    # `DAMAGE(Toxic)` -- deux raisons de croire a `DirectTargetAttack`. Le natif ecrit `2`.
    ActiveAbilityType.FoulInfusion: AbilityAttackType.Others,  # 1038
    ActiveAbilityType.GetEmRuntz: AbilityAttackType.Others,  # 1045
    # 1057 GrotTank (`orksBigMek`) -- #570. LITTERAL RELU au decompile :
    # `...Active.Loki.GrotTankAbility$$.ctor` finit par `AActiveAbility..ctor(this, &opts, 2)`
    # -> 3e argument = **2 = Others**. Le voisinage ne le donnait PAS : les autres SUMMON qui font
    # attaquer leur invocation dans la foulee (`ScarabHive` 1007, `SendInTheNextWave` 1016,
    # `Incursion` 1021, `Poxwalkers` 1040) valent tous `1 = SummonAndAttackTarget`, et GrotTank
    # porte pourtant lui aussi un sous-behaviour d'attaque on-appearance
    # (`PerformAIAttackFromCurrentPosition`). La difference LUE : ces quatre-la font frapper LA
    # CIBLE DU CAST, alors que GrotTank cible une TUILE et laisse l'IA choisir. On transcrit le 3e
    # argument, jamais la forme de l'arbre.
    ActiveAbilityType.GrotTank: AbilityAttackType.Others,  # 1057
    ActiveAbilityType.ScarabSummon: AbilityAttackType.Others,  # 1047
    ActiveAbilityType.Waaagh: AbilityAttackType.Others,  # 1058
    ActiveAbilityType.MasterOfTheTutelaries: AbilityAttackType.Others,  # 1096
    ActiveAbilityType.AlphaWarrior: AbilityAttackType.Others,  # 1112
    ActiveAbilityType.DoctrinaImperatives: AbilityAttackType.Others,  # 1118
    ActiveAbilityType.MalleusRocketLauncher: AbilityAttackType.Others,  # 1142
    ActiveAbilityType.ForwardSpotter: AbilityAttackType.Others,  # 1143
    ActiveAbilityType.SporeMineLauncher: AbilityAttackType.Others,  # 1145
    ActiveAbilityType.TheQuickening: AbilityAttackType.Others,  # 1151
    ActiveAbilityType.MacroPlasmaIncinerator: AbilityAttackType.Others,  # 1159
    # DutyEternal (1158, Galatian ultraDreadnought MoW), case-91. Litteral RELU :
    # `IdunBattleLogic.Entities.Abilities.Active.Loki.DutyEternalAbility$$.ctor` =
    # `AActiveAbility..ctor(this, &opts, 2, 0)` -> 3e argument = 2 = Others (l'ability ne fait AUCUN
    # degat : elle retire la MoW et pose un summon a 3 pieds). Le `&opts` y est un litteral INLINE
    # (forme « flags directs », masque 0x20000040000042) -> ses `TARGETING_OPTIONS` sont posees.
    ActiveAbilityType.DutyEternal: AbilityAttackType.Others,  # 1158
    # AetherStride (1208, `thousNpcMowDaemonPrince` ThousandSons MoW npc), #1022. Litteral RELU au
    # decompile de `IdunBattleLogic.Entities.Abilities.Active.Loki.AetherStrideAbility$$.ctor` =
    # `AActiveAbility..ctor(this, &opts, 2)` -> 3e argument = 2 = Others. Ce ctor est OCTET POUR
    # OCTET celui de 1158 ci-dessus (meme classe statique, meme `+0x48`, meme masque
    # 0x20000040000042, meme `2`) -- les deux decompiles ont ete COMPARES, le litteral n'est pas
    # deduit de la parente des deux arbres. Forme « flags directs » -> `TARGETING_OPTIONS` posees
    # sur la classe.
    ActiveAbilityType.AetherStride: AbilityAttackType.Others,  # 1208
    ActiveAbilityType.BlackRage: AbilityAttackType.Others,  # 1163
    ActiveAbilityType.AberrantHypermorph: AbilityAttackType.Others,  # 1166
    ActiveAbilityType.CultDemagogue: AbilityAttackType.Others,  # 1179
    # `IdunBattleLogic.Entities.Abilities.Active.Loki.FearOfTheUnseenAbility$$.ctor` ->
    # `AActiveAbility..ctor(this, &opts, 2, 0)` : 3e argument = 2 = Others (poseur d'effets, le
    # DirectDamage vit dans l'effet 1239, pas dans l'attaque du cast).
    ActiveAbilityType.FearOfTheUnseen: AbilityAttackType.Others,  # 1115
    ActiveAbilityType.ThriceBlessedConflagration: AbilityAttackType.Others,  # 1187
    ActiveAbilityType.DevastatingRefrain: AbilityAttackType.Others,  # 1188
    ActiveAbilityType.GravitonRifle: AbilityAttackType.Others,  # 1206
    ActiveAbilityType.AncestralFortune: AbilityAttackType.Others,  # 1207
    ActiveAbilityType.Hailstrike: AbilityAttackType.Others,  # 1214
    ActiveAbilityType.IronkinSteeljack: AbilityAttackType.Others,  # 1219
    ActiveAbilityType.Chronometron: AbilityAttackType.Others,  # 1226
    # ReanimationBeam (1223) et NanoscarabRepairProtocols (1224), `necroReanimator` MoW -- #902.
    # Litteral RELU sur CHACUN des deux ctors (jamais deduit de l'autre, ni du profil de degat) :
    # `...ReanimationBeamAbility$$.ctor` et `...NanoscarabRepairProtocolsAbility$$.ctor` finissent
    # tous deux par `AActiveAbility..ctor(this, &opts, 2)` -> 3e argument = 2 = Others. Coherent :
    # aucune des deux ne porte de coup (la seule attaque de 1223 est celle des SUMMONS, jouee par
    # `PerformAIAction`, donc par LEUR propre ability), et aucune n'a de `damageProfile` au gameconfig.
    ActiveAbilityType.ReanimationBeam: AbilityAttackType.Others,  # 1223
    ActiveAbilityType.NanoscarabRepairProtocols: AbilityAttackType.Others,  # 1224
    # Heal_TwistedScience (1167, `genesBiophagus` "Hollan") -- l'active que le passif
    # `TwistedScience` SUBSTITUE au `18 Heal` du trait `Healer` (#931). Litteral RELU sur son ctor :
    # `IdunBattleLogic.Entities.Abilities.Active.Loki.TwistedScience_HealAbility$$.ctor` finit par
    # `AActiveAbility..ctor(this, &opts, 2)` -> 3e argument = 2 = Others. Coherent : l'arbre de son
    # `$$ExecuteBehaviour` ne contient AUCUN noeud d'attaque (`Heal` + `AddDynamicStatModifierEffect`
    # + `ChangeStat` + `AddEffect`), et 1167 n'a AUCUNE entree gameconfig, donc aucun `damageProfile`.
    ActiveAbilityType.Heal_TwistedScience: AbilityAttackType.Others,  # 1167
    # HealingBalms_Heal (1212, `spaceWolfPriest` "Baldr") -- l'active que le passif `HealingBalms`
    # (1502) SUBSTITUE au `18 Heal` du trait `Healer` (#966). Litteral RELU sur son ctor :
    # `IdunBattleLogic.Entities.Abilities.Active.Loki.HealingBalms_HealAbility$$.ctor` finit par
    # `AActiveAbility..ctor(this, &opts, 2)` -> 3e argument = 2 = Others. Coherent : l'arbre de son
    # `$$ExecuteBehaviour` ne contient AUCUN noeud d'attaque (`RemoveEffect` x2 +
    # `AddDynamicStatModifierEffect` x2 + `AddEffect` + `Heal`), et 1212 n'a AUCUNE entree
    # gameconfig, donc aucun `damageProfile`.
    ActiveAbilityType.HealingBalms_Heal: AbilityAttackType.Others,  # 1212
    # Doombolt (1102, Ahriman thousAhriman), case-psychic-aoe. Litteral RELU :
    # `IdunBattleLogic.Entities.Abilities.Active.Loki.DoomboltAbility$$.ctor` =
    # `AActiveAbility..ctor(this, &opts, 2, 0)` -> 3e argument = 2 = Others. Coherent avec la nature
    # de l'ability (AoE de zone : les coups sont REPARTIS sur tous les ennemis a portee, la « cible »
    # du message n'etant qu'une priorite d'ordre), et avec son masque, qui n'a PAS `TargetIsEnemy`.
    ActiveAbilityType.Doombolt: AbilityAttackType.Others,  # 1102
    # MomentShackle (1184, Trajann custoTrajann), case-231. Litteral RELU :
    # `IdunBattleLogic.Entities.Abilities.Active.Loki.MomentShackleAbility$$.ctor` =
    # `AActiveAbility..ctor(this, &opts, 2, 0)` -> 2 = Others (l'ACTIVE ne fait aucun degat ; le
    # 2x Bolter de l'i2 vient de la TRIGGERED `MomentShackle_AttackAbility`, hors registre).
    ActiveAbilityType.MomentShackle: AbilityAttackType.Others,  # 1184
    # MartialInspiration (1191, Kariyan custoBladeChampion), #509. Litteral RELU :
    # `IdunBattleLogic.Entities.Abilities.Active.Loki.MartialInspirationAbility$$.ctor` =
    # `AActiveAbility..ctor(this, &opts, 0)` -> 3e argument = **0** = DirectTargetAttack. TRANSCRIT
    # du ctor, jamais deduit -- meme si l'ability POSE un effet avant de frapper, ce qui aurait pu
    # faire croire a un `Others` (cf. 1184 juste au-dessus, qui, lui, ne frappe pas).
    ActiveAbilityType.MartialInspiration: AbilityAttackType.DirectTargetAttack,  # 1191
    # VexillaMagnifica (1183, Aesoth custoVexilusPraetor), #566. Litteral RELU :
    # `IdunBattleLogic.Entities.Abilities.Active.Loki.VexillaMagnificaAbility$$.ctor` =
    # `AActiveAbility..ctor(this, &opts, 0)` -> 3e argument = **0** = DirectTargetAttack. TRANSCRIT
    # du ctor : le cast frappe DEUX cibles (celle du message + le meilleur autre adjacent) et pose
    # deux effets, ce qui aurait pu faire pencher pour `Others` (cf. 1195 TalonsOfTheEmperor, du
    # MEME module et du MEME preset de `TargetingOptions`, qui est mono-cible et vaut pourtant `2`).
    ActiveAbilityType.VexillaMagnifica: AbilityAttackType.DirectTargetAttack,  # 1183
    # SorcerousFacade (1100, Yazaghor thousTzaangor), #287. Litteral RELU :
    # `IdunBattleLogic.Entities.Abilities.Active.Loki.SorcerousFacadeAbility$$.ctor` =
    # `AActiveAbility..ctor(this, &opts, 2)` -> 3e argument = 2 = Others. Coherent avec la nature du
    # cast (la cible du MESSAGE est un ALLIE ; le degat part sur un AUTRE rail, `sel`, via
    # `UseActiveAbility(attaque NORMALE)`) -- mais c'est bien le LITTERAL du ctor qui est transcrit,
    # pas cette lecture. (`&opts` = un litteral INLINE « flags directs », rules = 0x402 -> ses
    # `TARGETING_OPTIONS` sont posees sur la classe.)
    ActiveAbilityType.SorcerousFacade: AbilityAttackType.Others,  # 1100
    # FireAndReposition (1063, Calandis eldarRanger), #567. Litteral RELU :
    # `IdunBattleLogic.Entities.Abilities.Active.Loki.FireAndRepositionAbility$$.ctor` recopie les
    # 0x40 octets du preset statique `<TargetingOptions statics>+0x00` puis
    # `AActiveAbility..ctor(this, &opts, 2)` -> 3e argument = **2 = Others**. TRANSCRIT, surtout pas
    # deduit : le cast FRAPPE (il dispatche l'attaque NORMALE de Calandis via `UseActiveAbility`),
    # ce qui ferait ecrire `DirectTargetAttack` a l'oeil -- et c'est la lecture INVERSE qui a ete
    # faite pour `HolyDuel` (1050) et `Drachnyen` (1029), MEME forme d'arbre, litteral `0`. Le
    # litteral se lit ability par ability : ni le nom, ni le profil de degat, ni la forme de l'arbre
    # ne le predisent. Meme valeur que `FoulInfusion` (1038) et `WallOfMirrors` (1186).
    ActiveAbilityType.FireAndReposition: AbilityAttackType.Others,  # 1063
    # Lot Tau #114 (merge d67b6ac), arrive APRES la redaction de #120 : les trois ctors passent
    # litteralement `AActiveAbility..ctor(this, &opts, 2, 0)` (relu au decompile).
    ActiveAbilityType.EarlyWarningOverride: AbilityAttackType.Others,  # 1077
    ActiveAbilityType.FightingRetreat: AbilityAttackType.Others,  # 1081
    # 1087 -- `...ExemplarOfTheKauyonAbility$$.ctor` : `AActiveAbility..ctor(this, &opts, 2)`
    ActiveAbilityType.ExemplarOfTheKauyon: AbilityAttackType.Others,  # 1087
    ActiveAbilityType.InspiredToGreatness: AbilityAttackType.Others,  # 1082
    # Lot DarkAngels #112, arrive lui aussi apres #120 (litteraux relus au decompile) :
    # Supercharge est le seul des trois a `DirectTargetAttack` (0) -- il entre donc dans le gate
    # `AbilityHasAttackType(0|1)` de SwornProtector, contrairement aux deux autres.
    ActiveAbilityType.ExemplarOfHate: AbilityAttackType.Others,  # 1140
    ActiveAbilityType.CalibaniteGreatsword: AbilityAttackType.Others,  # 1189
    # ArcScourge (1173, `admecBossBelisarius`), #894 : `IdunBattleLogic.Entities.Abilities.Active.
    # ArcScourgeAbility$$.ctor` = `AActiveAbility..ctor(this, &opts, 2)` -- le 3e argument est le
    # litteral `2`. TRANSCRIT, jamais deduit : l'arbre de 1173 FRAPPE bel et bien (une
    # `AttackWithAttackDamage` par maillon ennemi), ce qui aurait pu faire pencher pour
    # `DirectTargetAttack` -- et le litteral vaut quand meme `Others`.
    ActiveAbilityType.ArcScourge: AbilityAttackType.Others,  # 1173
# InvocationOfMachineVengeance (1172) et SolarAtomizer (1174), `admecBossBelisarius`, #1027 :
# `IdunBattleLogic.Entities.Abilities.Active.InvocationOfMachineVengeanceAbility$$.ctor` et
# `...SolarAtomizerAbility$$.ctor` finissent tous DEUX par `AActiveAbility..ctor(this, &opts, 2)`
# -- le 3e argument est le litteral `AbilityAttackType`, LU au decompile (jamais deduit du nom :
# `SolarAtomizer` sonne comme une attaque mais son arbre ne porte AUCUNE feuille `AttackWith*`,
# le degat est differe d'un tour par la triggered 1297).
ActiveAbilityType.InvocationOfMachineVengeance: AbilityAttackType.Others,  # 1172
ActiveAbilityType.SolarAtomizer: AbilityAttackType.Others,  # 1174
    # RadBombardment (1116), lot #128 : `IdunBattleLogic.Entities.Abilities.Active.Loki.
    # RadBombardmentAbility$$.ctor` = `AActiveAbility..ctor(this, &opts, 2, 0)` -> 2 = Others.
    # (Ici le `&opts` EST un litteral inline : `TargetingOptions..ctor(&opts, 0, CustomRange(1), 1,
    #  0xa0000000042, 0, 0, 0)` -- mais le masque est deja pose par le lot #128, on ne le double pas.)
    ActiveAbilityType.RadBombardment: AbilityAttackType.Others,  # 1116
    # OverwhelmingWrath (1141, Azkor worldEightbound), #503. Litteral RELU :
    # `IdunBattleLogic.Entities.Abilities.Active.Loki.OverwhelmingWrathAbility$$.ctor` =
    # `AActiveAbility..ctor(this, &opts, 2)` -> 3e argument = 2 = Others. On transcrit le LITTERAL,
    # jamais la categorie du kit : l'audit classe 1141 `DAMAGE(Eviscerate)` (elle a bien un
    # minDmg/maxDmg/damageProfile au gameconfig), et le ctor dit quand meme `2` -- parce que le degat
    # appartient a la TRIGGERED 1237 `OverwhelmingWrath_Attack`, pas au cast. Meme configuration que
    # 1069 SeekerMissileFrequencyLock et 1184 MomentShackle (2-phases).
    ActiveAbilityType.OverwhelmingWrath: AbilityAttackType.Others,  # 1141
    # Lot BOSS RIPTIDE (#895) -- les DEUX ctors du boss `tauBossRiptide` finissent litteralement par
    # `AActiveAbility..ctor(this, &opts, 2)` (relu au decompile, 3e argument = le litteral
    # `AbilityAttackType`). MEME configuration que 1069/1141 ci-dessus : l'audit les classe
    # `DAMAGE(Particle)` d'apres le `damageProfile` du KIT, et le ctor dit quand meme `2` -- parce
    # que le degat appartient aux TRIGGERED de phase 2 (`NovaShield_Attack`, `NovaBoost_Attack`),
    # pas au cast. On transcrit le 3e argument du ctor, jamais le profil de degat du kit.
    ActiveAbilityType.NovaBoost: AbilityAttackType.Others,  # 1192
    ActiveAbilityType.NovaShield: AbilityAttackType.Others,  # 1194
    # Lot #996 (« six no-op silencieuses ») -- les DEUX poseuses d'effets du lot. Litteraux RELUS au
    # decompile, jamais deduits du kit :
    #   `...ForwardObserversAbility$$.ctor` -> `AActiveAbility..ctor(this, &opts, 2)`
    #   `...WarConstructAbility$$.ctor`     -> `AActiveAbility..ctor(this, &opts, 2)`
    ActiveAbilityType.ForwardObservers: AbilityAttackType.Others,  # 1185
    ActiveAbilityType.WarConstruct: AbilityAttackType.Others,  # 1133
    # #1032 -- les deux no-op silencieuses 2-PHASES du lot boss. Litteraux RELUS au decompile :
    #   `...CallRipperSwarmsAbility$$.ctor` -> `AActiveAbility..ctor(this, &opts, 2)`
    #   `...NovaChargeAbility$$.ctor`       -> `AActiveAbility..ctor(this, &opts, 2)`
    # 1193 est le TROISIEME `Nova*` du Riptide : meme regime que 1192/1194 ci-dessus (le kit dit
    # `DAMAGE(Particle)`, le ctor dit `2`, et le degat vit dans `NovaCharge_Attack` 1324).
    ActiveAbilityType.CallRipperSwarms: AbilityAttackType.Others,  # 1052
    ActiveAbilityType.NovaCharge: AbilityAttackType.Others,  # 1193
}
# COUVERTURE : la table couvre l'INTEGRALITE du registre `ABILITY_CLASSES` (garde-fou :
# `probe_120_pre_unit_ability_fork.py` etape 0). Une ability AJOUTEE au registre sans son litteral de
# ctor n'est PAS gatee -- elle se degrade en `Others` (aucun trigger invente), ce que le probe
# SIGNALE au lieu de le taire.


def ability_has_attack_type(ability_type: Optional[int], attack_type: int) -> bool:
    """`IdunBattleLogic.Entities.DSLTriggers$$AbilityHasAttackType(df, sel, attackType)` ->
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


def ability_is_direct_target_attack(ability_type: Optional[int]) -> bool:
    """`IdunBattleLogic.Entities.DSLTriggers$$IsDirectTargetAttack(df, sel)` -- MIRROR du decompile :

        AbilityHasAttackTypeTrigger(sel, 0 = DirectTargetAttack, df@0x50, df@0x40)
        | IsNormalAttack(df, sel)

    (DISJONCTION `AbilityTrigger.op_BitwiseOr`, lue verbatim). A NE PAS confondre avec
    `ability_is_attack` ci-dessus, qui est la disjonction *DirectTargetAttack | SummonAndAttackTarget*
    de SwornProtector -- `IsDirectTargetAttack` prend l'autre branche (attaque NORMALE) et EXCLUT
    `SummonAndAttackTarget`.

    Consommateurs natifs (les 2 seuls call-sites, `list_xrefs`) :
      * `IdunBattleLogic.Entities.Abilities.Triggered.Loki.MartialSuperiorityAbility$$CreateTrigger`
      * `IdunBattle.Entities.Effects.CounterAttackEffect$$GetDirectTargetAbilityTrigger`
    -- les deux batissent le MEME idiome `IsDirectTargetAttack(@0x130) & !IsDirectTargetAttack(@0x140)`."""
    return (ability_has_attack_type(ability_type, AbilityAttackType.DirectTargetAttack)
            or is_normal_attack(ability_type))


def is_regular_attack(ability_type: Optional[int]) -> bool:
    """`idun.Idun.Source.Shared.Battle.StaticBattleRules.StaticBattleRules.ActiveAbility$$IsRegularAttack`
    = `Contains` sur l'`OrderedSet` statique @+0x18 = `REGULAR_ATTACK_ABILITY_TYPES`."""
    return ability_type is not None and int(ability_type) in REGULAR_ATTACK_ABILITY_TYPES


# `IsActiveAbility` exclut, EN PLUS des attaques regulieres, cinq `ActiveAbilityType` litteraux lus au
# decompile (`... != 0x12 && ... != 0x48f && ... != 0x4bc && ... != 0x1c && ... != 0x45f`) : ce sont les
# abilities-OUTILS de soin/reparation que le moteur declenche pour le compte d'une AUTRE ability.
NOT_ACTIVE_ABILITY_TYPES = frozenset({
    ActiveAbilityType.Heal,                   # 0x012 = 18
    ActiveAbilityType.Repair,                 # 0x01c = 28
    ActiveAbilityType.Repair_GalvanicField,   # 0x45f = 1119
    ActiveAbilityType.Heal_TwistedScience,    # 0x48f = 1167
    ActiveAbilityType.HealingBalms_Heal,      # 0x4bc = 1212
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
