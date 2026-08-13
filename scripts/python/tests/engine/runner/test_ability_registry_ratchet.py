"""#167 -- CLIQUET de non-regression du registre d'abilities (offline pur, aucune session).

CE QUE CE FICHIER GARDE
-----------------------
Entrer dans `ABILITY_CLASSES` engage DEUX donnees, et leur absence se degrade de la MEME facon :
en silence, dans le sens PERMISSIF.

  * `TARGETING_OPTIONS` -- `engine/runner/abilities/targeting.py`, `get_invalid_target_reason` /
    `get_invalid_caster_reason` commencent par `options = getattr(ability, "TARGETING_OPTIONS", None)`
    et rendent **0 immediatement** si c'est `None`. Aucun gate. Le moteur accepte alors des casts que
    `IdunBattle.Operations.ActiveAbilityOperation$$IsInvalidTarget` REFUSE (ami/ennemi, cible ==
    caster, caster ayant deja bouge). Ni erreur ni crash -- donc invisible en self-play, et c'est
    exactement l'espace d'action qu'un entrainement irait exploiter.
  * `ABILITY_ATTACK_TYPE` -- `engine/runner/abilities/attack_type.py`, `ability_has_attack_type`
    rend `False` sur une cle absente : l'ability se degrade en `Others` et le gate
    `AbilityHasAttackType(0|1)` de SwornProtector reste MUET pour elle.

POURQUOI UN CLIQUET, ET PAS UN SIMPLE ASSERT DE COUVERTURE
----------------------------------------------------------
C'est le SEUL gisement que notre propre cadence de portage AGGRAVE : chaque nouveau port l'alimente.
Le compte de masques manquants est passe de 60 a 75 pendant la campagne, sans qu'aucun test ne
rougisse. Et l'absence de `ABILITY_ATTACK_TYPE` a ete creusee TROIS fois (1036 FrenziedFiring en
`d2be96e`, puis 1041 BrazierOfHolyFire et 1116 RadBombardment en `825f69f`) -- les deux dernieres
n'ont ete vues qu'au RE-JEU apres rebase d'un autre agent : le trou ne s'etait montre dans aucune
des deux PR qui l'avaient creuse.

Un assert de couverture pleine serait ROUGE des le premier jour sur `TARGETING_OPTIONS` (28/81 a la
creation de ce fichier, 51/91 au 2026-07-28) et donc desarme dans la semaine. La forme qui tient est
le CLIQUET : une liste d'exemption figee, qui ne peut que RETRECIR.

  * une ability du registre SANS masque et ABSENTE de la liste -> ECHEC (regression neuve) ;
  * une ability de la liste qui a MAINTENANT son masque -> ECHEC, il faut la retirer de la liste
    (c'est ce sens-la qui fait le cliquet : sans lui, la liste se fossilise et ne redescend jamais) ;
  * une ability de la liste ABSENTE du registre -> ECHEC (entree perimee).

`ABILITY_ATTACK_TYPE`, lui, est deja PLEIN (81/81 a la creation, 91/91 au 2026-07-28) : sa garde est
donc SANS exemption. Elle existait, mais
enterree a l'etape 0 de `probe_120_pre_unit_ability_fork.py` -- un probe qui monte un etat de
bataille complet et casse pour dix raisons sans rapport, auquel cas la couverture n'est jamais
vue. Ici elle tient seule, en un import.

ASCII only (console Windows cp1252).
"""
from __future__ import annotations

import ast
from pathlib import Path

import repo_read
from engine.runner.abilities.handler import ABILITY_CLASSES
from engine.runner.abilities.attack_type import ABILITY_ATTACK_TYPE
from engine.runner.abilities.targeting_rule import TargetingRule

# --- LISTE D'EXEMPTION -- NE PEUT QUE RETRECIR ----------------------------------------------------
# Etat au 2026-07-29 (#247 -> #254) : 94 abilities au registre, 94 avec masque, ZERO sans.
# La liste d'exemption est VIDE : la campagne a resorbe l'integralite du gisement. Elle reste ici
# comme cliquet -- toute nouvelle ability entrant au registre sans masque fera ECHOUER
# `test_targeting_options_ne_regresse_pas`, et l'y rajouter demande de justifier le doute.
# (Historique du cliquet : 81/28/53 au 2026-07-27 `6110d37` -> 13 resorbees par #181, lot
#  ultramarines / sisterhood / tyranids / spacewolves / admec / bloodangels ; puis 1014
#  ArmoriumCherub par #222, 1018 ValkyrieStrike par #245, 1043 ThunderousAssault par #246,
#  1104 SpiritLeech + 1122 CordClaw par #247 -- qui SOLDENT le module `strike` --, les SIX du
#  module `splash` par #248 : 1000/1051/1065/1078/1098/1105, qui relevent a elles seules de TROIS
#  formes de ctor et de TROIS presets differents, les CINQ du module `deathguard` par #249 :
#  1037/1040/1042/1168/1169, les CINQ du module `blacklegion` par #250 : 1021/1022/1036/1147/1148
#  -- dont les DEUX abilities de MACHINE OF WAR du MEME porteur `blackForgefiend`, qui ont des
#  masques SANS RAPPORT --, les CINQ du module `summon` par #251 : 1007/1045/1047/1096/1166, dont
#  1007 et 1047 partagent fichier ET forme de ctor sans partager ni litteral ni portee, les CINQ
#  du module `tau` par #252 : 1077/1081/1082/1160/1161, dont 1160 et 1161 sont portees par la MEME
#  MoW `tauBroadside` avec la MEME forme et la MEME portee -- et des masques differents, et les
#  QUATRE du module `astramilitarum` par #253 : 1016/1028/1142/1143, toutes de forme 1 mais avec
#  QUATRE presets de PORTEE differents -- statics+0x00, +0x60, +0x48, +0x48 -- et 1028 seule a
#  poser `isSelfCasting = 1`. TROISIEME paire d'actives d'une MEME MoW aux masques sans rapport
#  (1142/1143, `astraOrdnanceBattery`), apres `blackForgefiend` et `tauBroadside` : le porteur ne
#  predit RIEN du masque, trois fois mesure. Enfin les QUATRE abilities a MODULE UNIQUE par #254 :
#  1076 MV71 / 1113 Stormcaller / 1118 DoctrinaImperatives / 1151 TheQuickening -- QUATRE FORMES DE
#  CTOR sur quatre abilities, le seul lot de la campagne a les exhiber toutes.)
# ⚠ Les comptes ci-dessus se PERIMENT : les re-deriver (`probe_181_targeting_gaps.py`), pas les citer.
# Ne JAMAIS y ajouter une ligne pour faire passer un port neuf : le masque se lit au decompile, dans
# le litteral passe par `<X>Ability$$.ctor` a `IdunBattle.Core.Services.TargetingOptions$$.ctor`.
#
# QUATRE FORMES DE CTOR, et TROIS d'entre elles ont deja produit un masque FAUX :
#   1. FLAGS DIRECTS -- `TargetingOptions..ctor(&opts, self, &range, melee, <flags>, 0,0,0)` : le
#      litteral EST le masque (seule forme ou la lecture naive marche).
#   2. PRESET + FLAGS -- `TargetingOptions..ctor(&opts, &preset, <flags>, 0)` : cette surcharge
#      recopie le preset SAUF `Rules`, qu'elle COMBINE (`dst+0x28 = flags | preset+0x28`). Le
#      litteral visible n'est PAS le masque effectif.
#   3. PRESET STATIQUE COPIE, AUCUN ctor -- recopie integrale des 0x40 octets d'un champ STATIQUE :
#      le masque effectif est la constante ecrite par `TargetingOptions$$.cctor` a `<preset>+0x28`.
#   4. FACTORY NOMMEE (decouverte par #248) -- le ctor n'ecrit rien et ne copie rien, il appelle un
#      helper qui remplit la structure : `TargetingOptions$$SelfCastIfEnemyInCustomRangeOptions`
#      (1000 GauntletsOfUltramar). Chercher le seul `TargetingOptions$$<Xxx>Options` appele.
#      ⚠ Cette forme est INVISIBLE aux trois autres recettes, et IL2CPP l'INLINE ailleurs
#      (1009/1207/1226 la portent inlinee) : ne pas conclure « aucun ctor, aucune copie => pas de
#      masque ».
#
# Les presets ne sont PAS interchangeables, et le piege a DEUX faces, toutes deux MESUREES :
#   * MEME preset, masques differents -- 1043 ThunderousAssault et 1122 CordClaw recopient tous deux
#     `statics+0x40`, mais 1043 enchaine sur la surcharge 2 qui COMBINE : 0x10004000 contre 0x4000 nu.
#   * MEME masque, presets differents -- 1104 SpiritLeech (`+0x180`) et 1014 ArmoriumCherub (`+0x140`)
#     valent tous deux 0x4002 avec RANGE_FROM_CONFIG, mais leurs presets ne different QUE par
#     `forceMeleeTarget`, et ce champ change le regime de portee au contact. Meme couple entre 1078
#     Fragstorm (`+0x180`) et 1051/1098 (`+0x140`). Recopier la voisine y donne le BON `rules` et le
#     MAUVAIS volet portee -- l'erreur la plus difficile a voir, puisque le masque a l'air juste.
# Recopier un litteral sans verifier la forme produit un masque FAUX -- PIRE que l'absence, qui au
# moins ne ment pas. Laisser l'entree dans cette liste est le bon choix tant que le doute existe.
SANS_TARGETING_OPTIONS: dict[int, str] = {
    # 1000 GauntletsOfUltramarAbility RESORBEE (#247) -- une QUATRIEME forme : **FACTORY NOMMEE**.
    # `...GauntletsOfUltramarAbility$$.ctor` n'ecrit aucun champ et ne copie aucun preset : il appelle
    # `IdunBattle.Core.Services.TargetingOptions$$SelfCastIfEnemyInCustomRangeOptions(&opts, 2)`, qui
    # ecrit `isSelfCasting = 1`, `range = CustomRange(2)`, `forceMeleeTarget = RangedBool.False` et
    # `rules = 0x4000` (TargetIsEnemy seul). C'est le SEUL appelant natif de cette factory ; les 3
    # autres porteurs du profil (1009/1207/1226) l'ont recue INLINEE.
    # 1007 ScarabHiveAbility RESORBEE (#250) -- forme « FLAGS DIRECTS » :
    # `...ScarabHiveAbility$$.ctor` recopie le `TargetingRange` STATIQUE +0x30 (= RANGE_ADJACENT) puis
    # `TargetingOptions..ctor(&opts, 0, &range, 1, 0x4020, 0,0,0)`. Le litteral EST le masque (aucun
    # preset a OR-er) : 0x4020 = `TargetHasFreeAdjacentTile` (0x20) | `TargetIsEnemy` (0x4000).
    # `AActiveAbility..ctor(..., 1, 0)` = `SummonAndAttackTarget` (le SEUL des cinq du module qui ne
    # vaut pas `Others`).
    # 1014 ArmoriumCherubAbility RESORBEE (#222) -- forme « PRESET STATIQUE COPIE » :
    # `...ArmoriumCherubAbility$$.ctor` recopie `TargetingOptions statics+0x140` et le masque
    # effectif est `*(statics+0x168)` = 0x4002, lu dans `TargetingOptions$$.cctor`.
    # 1016 SendInTheNextWaveAbility RESORBEE (#253) -- forme 1 « FLAGS DIRECTS » :
    # `...SendInTheNextWaveAbility$$.ctor` recopie `TargetingRange statics+0x00` puis appelle la
    # surcharge 8 arguments `TargetingOptions..ctor(&opts, 0, &preset, 1, 0x4002, 0,0,0)`, celle qui
    # ecrit `+0x28 <- param_5` SANS OR -> masque = 0x4002 = TargetIsEnemy (1<<14) |
    # TargetMatchesDynamicRule (1<<1). Portee = statics+0x00 = RANGE_ADJACENT_IF_MELEE_CASTER
    # (`onlyAdjacent = IfNotRangedCaster`) ; `forceMeleeTarget = 1 = RangedBool.False`.
    # Yarrick etant RANGED (arme Range=2), `onlyAdjacent` retombe a faux et la portee vaut 2 -- l'i2
    # « Select a target within 2 hexes ». Confrontee live (oracle `abilityReason`, 2 boards).
    # 1018 ValkyrieStrikeAbility RESORBEE (#245) -- MEME forme « PRESET STATIQUE COPIE » que 1014,
    # mais un AUTRE preset : `...ValkyrieStrikeAbility$$.ctor` recopie `TargetingOptions statics+0x1c0`
    # et le masque effectif est `*(statics+0x1e8)` = 0x6000040 (TargetIsTile | AllowObscuredTarget
    # ByElevation | AllowObscuredTargetByWalls), lu dans `TargetingOptions$$.cctor`. Preuve vivante que
    # les presets ne sont pas interchangeables : 0x140 -> 0x4002, 0x1c0 -> 0x6000040.
    # 1021 IncursionAbility RESORBEE (#249) -- forme « FLAGS DIRECTS », la 1re des trois :
    # `...IncursionAbility$$.ctor` appelle `TargetingOptions..ctor(&opts, 0, &<TargetingRange
    # statics+0x18>, 2, 0x4020, 0, 0, 0)` -> le litteral EST le masque : 0x20
    # TargetHasFreeAdjacentTile | 0x4000 TargetIsEnemy. Portee = RANGE_FROM_CONFIG
    # (constants.range = 2) ; `forceMeleeTarget` = 2 = RangedBool.IfRangedCaster -- ARME, car
    # `blackPossession` porte une arme a Range 2 : au contact d'un ennemi la portee clampe a 1.
    # 1022 BringerOfDespairAbility RESORBEE (#249) -- forme « PRESET STATIQUE COPIE » :
    # `...BringerOfDespairAbility$$.ctor` recopie `TargetingOptions statics+0x40` INTEGRALEMENT
    # (aucun ctor appele) -> masque = `*(statics+0x68)` = 0x4000 (TargetIsEnemy seul). Portee =
    # `TargetingRange statics+0x30` = RANGE_ADJACENT ; `forceMeleeTarget` = `*(statics+0x60)` = 1 =
    # RangedBool.False. MEME preset que 1020 HeraldOfTheApocalypse, 1122 CordClaw ET 1029 Drachnyen
    # -- quatre porteurs, MEME masque 0x4000. (Ce commentaire prêtait a 1029 un `0x200004000` via la
    # surcharge PRESET + flags : REFUTE par les xrefs entrantes des trois surcharges de
    # `TargetingOptions..ctor` -- cf. docs/rl/case-302-4-population-cible-tuile.md §5.3.)
    # 1028 SupremeCommanderAbility RESORBEE (#253) -- forme 1 « FLAGS DIRECTS », mais le SEUL des
    # quatre a poser `isSelfCasting = 1` : `TargetingOptions..ctor(&opts, 1, &preset, 1, 0x208000,
    # 0,0,0)` -> masque = CasterHasFreeAdjacentTile (1<<21) | CasterIsPossibleTarget (1<<15).
    # Portee = `TargetingRange statics+0x60` = RANGE_SELF (`overrideRange = Nullable(0)`), donc
    # PORTEE NULLE ; `forceMeleeTarget = 1 = RangedBool.False`. Le byte `options+0x00` aiguille vers
    # `TargetingQuery$$GetCasterNotAddedReason` des que la cible EST le caster : la cascade CIBLE
    # n'est alors jamais evaluee, et `CasterHasFreeAdjacentTile` reste INERTE pour ce porteur (le
    # seul chemin qui l'atteindrait est deja refuse par la portee 0). Elle n'est donc pas portee.
    # 1036 FrenziedFiringAbilityCombat RESORBEE (#250) -- forme PRESET STATIQUE COPIE :
    # `...FrenziedFiringAbility$$.ctor` recopie `TargetingOptions statics+0x140` -> masque =
    # `*(statics+0x168)` = 0x4002 (TargetMatchesDynamicRule | TargetIsEnemy). Portee =
    # `TargetingRange statics+0x18` = RANGE_FROM_CONFIG (constants.range = 3) ; `forceMeleeTarget` =
    # `*(statics+0x160)` = 0 = RangedBool.True -> clamp a l'adjacence des qu'un ennemi est au contact
    # du caster. MEME preset que 1014 ArmoriumCherub, PAS celui de 1104 SpiritLeech (+0x180), qui
    # n'en differe QUE par ce champ (`*(statics+0x1a0)` = 1 = RangedBool.False) -- le couple
    # « meme masque, presets differents » deja signale en tete, MESURE ici : voir case-250 §4.
    # 1037 RevitalizingMalignancyAbility RESORBEE (#249) -- forme FLAGS DIRECTS :
    # `...RevitalizingMalignancyAbility$$.ctor` appelle `TargetingOptions..ctor(&opts, 1, &range, 1,
    # 0x8500, 0,0,0)`, le litteral EST le masque. 0x8500 = 0x100 TargetIsHealable | 0x400
    # TargetIsFriendly | 0x8000 CasterIsPossibleTarget. Portee = `TargetingRange statics+0x30` =
    # RANGE_ADJACENT ; `isSelfCasting = 1`.
    # 1040 SpawnPoxwalkersAbility RESORBEE (#249) -- FLAGS DIRECTS, masque 0x8000000004 =
    # 0x4 CasterMatchesDynamicRule | 0x8000000000 TargetIsCaster. Son `TargetingRange` est le SEUL
    # du registre construit par `TargetingRange$$CustomRange(GetRange)` (surcharge DELEGUE) : la
    # portee est ECRASEE par un delegue non resolu -> `override_range_func` pose, aucun gate de
    # portee (cf. `custom_range_func` dans targeting.py).
    # 1042 FlailSwingAbility RESORBEE (#249) -- forme PRESET STATIQUE COPIE, aucun ctor :
    # `...FlailSwingAbility$$.ctor` recopie `TargetingOptions statics+0x40`, masque effectif
    # `*(statics+0x68)` = 0x4000 TargetIsEnemy, portee = RANGE_ADJACENT. MEME preset que 1043, qui
    # lui passe par la surcharge PRESET + FLAGS et vaut donc 0x10004000 : le preset ne suffit
    # jamais, il faut lire QUELLE forme l'ability emploie.
    # 1043 ThunderousAssaultAbility RESORBEE (#246) -- forme « PRESET + FLAGS », la 2e des trois :
    # `...ThunderousAssaultAbility$$.ctor` recopie `TargetingOptions statics+0x40` PUIS appelle
    # `TargetingOptions..ctor(&opts, &preset, 0x10000000, 0)`. Cette surcharge COMBINE
    # (`dst+0x28 = flags | preset+0x28`) -> masque effectif `0x10000000 | *(statics+0x68)` =
    # `0x10000000 | 0x4000` = 0x10004000 (CasterCanMove | TargetIsEnemy). Le litteral visible
    # (0x10000000) n'est donc PAS le masque, et le preset n'est pas non plus le masque : c'est le
    # OU des deux. Portee = `TargetingRange statics+0x30` = RANGE_ADJACENT.
    # 1045 GetEmRuntzAbility RESORBEE (#250) -- forme « PRESET STATIQUE COPIE » :
    # `...GetEmRuntzAbility$$.ctor` n'appelle AUCUN `TargetingOptions$$.ctor` et recopie les 0x40
    # octets de `TargetingOptions statics+0x280`. Masque effectif = `*(statics+0x2a8)` = 0x8004 =
    # `CasterMatchesDynamicRule` (0x4) | `CasterIsPossibleTarget` (0x8000) ; portee =
    # `<preset>+0x08` <- `TargetingRange statics+0x60` = RANGE_SELF (portee 0) ; `isSelfCasting` =
    # `*(statics+0x280)` = 1. Preuve de plus que les presets ne sont pas interchangeables : +0x280
    # -> 0x8004, la ou +0x140 -> 0x4002 et +0x1c0 -> 0x6000040. Le bit 2 est PORTE (#250) : nouveau
    # patron `ActiveAbility.get_dynamic_invalid_caster_reason` (slot vtable +0x470).
    # 1047 ScarabSummonAbility RESORBEE (#250) -- forme « FLAGS DIRECTS » comme 1007, mais un AUTRE
    # `TargetingRange` statique (+0x60 = RANGE_SELF, pas +0x30) et un autre litteral :
    # `TargetingOptions..ctor(&opts, 1, &range, 1, 0x208000, 0,0,0)` -> `CasterIsPossibleTarget`
    # (0x8000) | `CasterHasFreeAdjacentTile` (0x200000), `isSelfCasting = 1`. Deux abilities du MEME
    # fichier, meme forme de ctor, rien de commun : lire chacune.
    # 1051 StikkbombAbility RESORBEE (#247) -- forme « PRESET + FLAGS » : preset `statics+0x140`
    # + flags `0x2000000` -> masque effectif `0x2000000 | *(statics+0x168)` = `0x2000000 | 0x4002`
    # = 0x2004002 (AllowObscuredTargetByElevation | TargetIsEnemy | TargetMatchesDynamicRule).
    # Portee = `TargetingRange statics+0x18` = RANGE_FROM_CONFIG (`constants.range` = 2) ;
    # `forceMeleeTarget = 0 = RangedBool.True` (clamp de melee ARME).
    # CONFRONTEE LIVE (#243) : 14/14 lignes d'accord natif/port sur DEUX montages, seuil encadre des
    # deux cotes (d=2 accepte / d=3 refuse `TargetIsInRange`) ET le clamp de melee EXERCE -- avec un
    # ennemi au contact, la cible a d=2 bascule en refus. Porteur amene par catalogue injecte + trait
    # `Summon` retire (recette case-245), cf. `probe_243_splash_range_clamp.py` et
    # `test_splash_range_clamp_live.py`. Meme statut pour 1078 et 1098.
    # 1065 ScythingTalonsAbility RESORBEE (#247) -- forme « PRESET STATIQUE COPIE », preset
    # `statics+0x40` : masque = `*(statics+0x68)` = 0x4000 (TargetIsEnemy seul), portee =
    # `TargetingRange statics+0x30` = RANGE_ADJACENT, `forceMeleeTarget = RangedBool.False`.
    # CONFRONTEE LIVE (#250) sur son PORTEUR REEL `tyranSmnWarrior` -- elle etait jusque-la validee
    # par IDENTITE DE PRESET avec 1105, ce qui n'est pas une mesure. 6/6 d'accord natif/port, seuil
    # encadre des deux cotes (ENNEMI d=1 `0x0` / d=2 `TargetIsInRange`), ALLIE et CASTER refuses sur
    # `TargetIsEnemy` ; contrefactuels : masque absent 5 lignes, `rules=0` 2, `range=None` 3.
    # `fmtFlip` 0 -- `force_melee_target` est INERTE ici, et c'est LU (RANGE_ADJACENT pose deja
    # `overrideRange = 1`, le clamp `Math.Min(1, v)` est idempotent), pas suppose.
    # cf. `probe_250_summon_automatic.py`, garde `test_summon_automatic_live.py`.
    # 1076 MV71SniperDroneSquadAttackAbility RESORBEE (#254) -- forme FACTORY NOMMEE (la 4e) :
    # `...Triggered.Loki.MV71SniperDroneSquadAttackAbility$$.ctor` n'ecrit rien et ne copie rien, il
    # appelle `IdunBattle.Core.Services.TargetingOptions$$CustomLokiNormalAttackOptions(&opts, 2)`.
    # Cette factory recopie le preset `<TargetingOptions statics>+0x00` et COMBINE `Rules` comme la
    # surcharge 2 : `*(dst+0x28) = *(preset+0x28) | extra` = `0x4002 | 2` = 0x4002
    # (TargetMatchesDynamicRule | TargetIsEnemy) -- l'argument etait DEJA dans le preset. Portee =
    # `TargetingRange statics+0x00` = RANGE_ADJACENT_IF_MELEE_CASTER, `forceMeleeTarget = 2 =
    # RangedBool.IfRangedCaster` : le profil exact du tir normal (meme preset que 1004 MortisRound,
    # a `Rules` pres). ⚠ SON PORTEUR NE SE LIT PAS DANS LE GAMECONFIG (zero kit sur l'ID 1076 ;
    # `tauMarksman` n'y porte que le PASSIF `MV71SniperDroneSquad`) -- c'est le LIVE qui a tranche :
    # `decisionView(allAbilities=true)` l'expose sur `tauMarksman`, et `abilityReason` traverse la
    # cascade malgre un `abilityState` null. CONFRONTEE LIVE, 4/4 sur deux couples.
    # 1077 EarlyWarningOverrideAbility RESORBEE (#252) -- forme « PRESET STATIQUE COPIE » (la 3e) :
    # `...EarlyWarningOverrideAbility$$.ctor` recopie `TargetingOptions statics+0x280` et n'appelle
    # AUCUN ctor. Le masque effectif est `*(statics+0x2a8)` = 0x8004 (CasterMatchesDynamicRule |
    # CasterIsPossibleTarget), lu dans `TargetingOptions$$.cctor` ; le meme preset porte
    # `isSelfCasting = 1` et `TargetingRange statics+0x60` = RANGE_SELF.
    # 1078 FragstormAbility RESORBEE (#247) -- forme « PRESET + FLAGS », mais preset `statics+0x180`
    # et NON `+0x140` comme ses deux voisines de module (1051/1098). Meme `rules` effectif
    # (0x2004002) et une portee qui DIFFERE : `*(statics+0x1a0)` = 1 = `RangedBool.False` ->
    # `forceMeleeTarget` DESARME, donc pas de clamp a 1 au contact. Illustration directe du piege
    # « la voisine ment » : le masque se serait recopie juste, le volet portee faux.
    # CONFRONTEE LIVE (#243) -- cf. la note de 1051 : 14/14, et c'est la SEULE des trois dont la
    # cible a d=2 reste ACCEPTEE avec un ennemi au contact. Le contrefactuel `fmtFlip` (basculer
    # `forceMeleeTarget`) faux-REFUSE exactement cette ligne : le champ est mesure, pas suppose.
    # Piege de recon a ne pas repeter : `templAggressor` (au pool) porte `FragstormGrenadeLauncher`
    # (1048), PAS `Fragstorm` (1078). Le recensement par sous-chaine ment ; c'est l'oracle live qui
    # a tranche.
    # 1081 FightingRetreatAbility RESORBEE (#252) -- forme « FLAGS DIRECTS » (la 1re) :
    # `TargetingOptions..ctor(&opts, 1, <TargetingRange statics+0x30>, 1, 0x802, 0,0,0)` ->
    # 0x802 = TargetMatchesDynamicRule | AddCasterIfAtLeastOneTarget, portee RANGE_ADJACENT.
    # 1082 InspiredToGreatnessAbility RESORBEE (#252) -- MEME forme, MEME TargetingRange, masque
    # DIFFERENT : `TargetingOptions..ctor(&opts, 0, <statics+0x30>, 1, 0x402, 0,0,0)` ->
    # 0x402 = TargetMatchesDynamicRule | TargetIsFriendly (ability ALLIE, self-cast = 0).
    # 1096 MasterOfTheTutelariesAbility RESORBEE (#253) -- forme « FLAGS DIRECTS » :
    # `TargetingOptions..ctor(&opts, 0, &<TargetingRange statics+0x30 = RANGE_ADJACENT>, 1, 0x1040,
    # 0,0,0)` -> 0x1040 = `TargetIsTile` (0x40) | `TargetTileIsFree` (0x1000). Cast TILE-TARGET sur un
    # hex LIBRE ADJACENT au caster.
    # 1098 PlasmaGrenadeAbility RESORBEE (#248) -- forme « PRESET + FLAGS », preset `statics+0x140`
    # + flags `0x2000000` -> 0x2004002 ; portee RANGE_FROM_CONFIG (2) ; `forceMeleeTarget =
    # RangedBool.True`. STRICTEMENT le meme couple que 1051, verifie ctor par ctor.
    # CONFRONTEE LIVE (#243, cf. la note de 1051) : 14/14, clamp de melee exerce comme 1051.
    # 1104 SpiritLeechAbility RESORBEE (#247) -- forme « PRESET STATIQUE COPIE » :
    # `...SpiritLeechAbility$$.ctor` recopie `TargetingOptions statics+0x180` (copie INTEGRALE,
    # aucun ctor appele) et le masque effectif est `*(statics+0x1a8)` = 0x4002
    # (TargetMatchesDynamicRule | TargetIsEnemy). Portee = `TargetingRange statics+0x18` =
    # RANGE_FROM_CONFIG (constants.range = 3) ; `forceMeleeTarget` = `*(statics+0x1a0)` = 1 =
    # RangedBool.False. Piege ecarte : 1014 ArmoriumCherub a le MEME masque et le MEME
    # RANGE_FROM_CONFIG, mais son preset (+0x140) pose `forceMeleeTarget = 0 = RangedBool.True` --
    # deux presets qui ne different QUE par ce champ, et il change le regime de portee au contact.
    # 1105 CrushingClawsAbility RESORBEE (#248) -- forme « PRESET STATIQUE COPIE », preset
    # `statics+0x40` (le meme que 1065) : masque 0x4000, portee RANGE_ADJACENT, `forceMeleeTarget =
    # RangedBool.False`. CONFRONTEE LIVE (6/6 sur deux couples, 5 casts illegaux fermes).
    # 1113 StormcallerAbility RESORBEE (#250) -- forme « PRESET + FLAGS » : preset `statics+0x180`
    # + flags `0x200000000` -> masque effectif `0x200000000 | *(statics+0x1a8)` = `0x200000000 |
    # 0x4002` = 0x200004002 (TargetMatchesDynamicRule | TargetIsEnemy | TargetIsNotAnObject).
    # Portee = `TargetingRange statics+0x18` = RANGE_FROM_CONFIG (`constants.range` = 3) ;
    # `forceMeleeTarget` = `*(statics+0x1a0)` = 1 = RangedBool.False. Piege ecarte : le preset
    # +0x140 (1014 ArmoriumCherub) porte le MEME `rules` 0x4002 et le MEME RANGE_FROM_CONFIG, et ne
    # differe QUE par `forceMeleeTarget` -- la voisine aurait donne le bon masque et le mauvais
    # regime de portee au contact.
    # 1118 DoctrinaImperativesAbility RESORBEE (#250) -- forme FLAGS DIRECTS :
    # `...DoctrinaImperativesAbility$$.ctor` appelle `TargetingOptions..ctor(&opts, 1, &range, 1,
    # 0x80, 0,0,0)`. 0x80 = `AddCaster` SEUL -- aucune regle de refus : c'est le court-circuit
    # `if ((char)rules < 0) return valide;` de `TargetingQuery$$GetCasterNotAddedReason` (test du
    # bit 7). Tout le gate vient du `TargetingRange statics+0x60` = RANGE_SELF (`overrideRange =
    # 0`) : une cible autre que le caster tombe sur `range.Value(0) < d` -> TargetIsInRange.
    # `isSelfCasting = 1` ; `forceMeleeTarget = 1 = RangedBool.False`.
    # 1122 CordClawAbility RESORBEE (#247) -- forme « PRESET STATIQUE COPIE » :
    # `...CordClawAbility$$.ctor` recopie `TargetingOptions statics+0x40` INTEGRALEMENT (aucun ctor
    # appele) -> masque = `*(statics+0x68)` = 0x4000 (TargetIsEnemy seul). Portee =
    # `TargetingRange statics+0x30` = RANGE_ADJACENT ; `forceMeleeTarget` = `*(statics+0x60)` = 1 =
    # RangedBool.False. Piege ecarte : 1043 ThunderousAssault recopie LE MEME preset +0x40, mais
    # enchaine sur la surcharge « preset + flags » qui COMBINE (0x10000000 | 0x4000 = 0x10004000).
    # Meme source statique, deux masques -- c'est la FORME du ctor qui tranche.
    # 1142 MalleusRocketLauncherAbility et 1143 ForwardSpotterAbility RESORBEES (#253) -- les DEUX
    # abilities de la MoW `astraOrdnanceBattery`, forme 1 « FLAGS DIRECTS », MEME preset de portee
    # `TargetingRange statics+0x48` = RANGE_WHOLE_BOARD, MEME `forceMeleeTarget = 1 = RangedBool.False`
    # -- et pourtant deux masques SANS AUCUN bit CIBLE commun :
    #   1142 : 0x10000040000040 = CasterHas2TurnsLeft (1<<52) | AllowNullCasterTile (1<<30)
    #                           | TargetIsTile (1<<6)                    -- cast TILE-target
    #   1143 : 0x40000422       = AllowNullCasterTile (1<<30) | TargetIsFriendly (1<<10)
    #                           | TargetHasFreeAdjacentTile (1<<5) | TargetMatchesDynamicRule (1<<1)
    # `AllowNullCasterTile` est le seul bit partage, et c'est une PERMISSION : sans lui,
    # `TargetingQuery$$GetInvalidCasterReason` refuserait TOUT cast d'une MoW (aucune position).
    # C'est la TROISIEME paire d'actives d'un MEME porteur MoW aux masques sans rapport, apres
    # 1147/1148 (`blackForgefiend`) et 1168/1169 (`deathCrawler`) : la lecture se fait ability par
    # ability, le porteur ne predit RIEN.
    # ⚠ PIEGE ECARTE sur 1142 : sa config porte `constants.range = 2`, mais le preset ne pose pas
    # `useRangeFromConfig` -> ce range est celui du barrage de phase 2, PAS du ciblage.
    # 1147 HadesAutocannonsAbility RESORBEE (#249) -- forme « FLAGS DIRECTS » :
    # `...HadesAutocannonsAbility$$.ctor` appelle `TargetingOptions..ctor(&opts, 0, &<TargetingRange
    # statics+0x48>, 1, 0x46006000, 0, 0, 0)` -> masque = 0x2000 TargetIsSummon | 0x4000
    # TargetIsEnemy | 0x6000000 AllowObscuredTarget | 0x40000000 AllowNullCasterTile. Portee =
    # RANGE_WHOLE_BOARD (aucun test) ; `forceMeleeTarget` = 1 = RangedBool.False.
    # 1148 DaemonicOrdnanceAbility RESORBEE (#249) -- MEME forme, MEME `TargetingRange` que 1147,
    # masque DIFFERENT : `TargetingOptions..ctor(..., 0x46000040, ...)` = 0x40 TargetIsTile |
    # 0x6000000 AllowObscuredTarget | 0x40000000 AllowNullCasterTile. Deux abilities du MEME porteur
    # (`blackForgefiend`), l'une cible une UNITE-summon ennemie, l'autre une TUILE : la lecture se
    # fait ability par ability, jamais par porteur.
    # 1151 TheQuickeningAbility RESORBEE (#254) -- forme « PRESET + FLAGS », le cas d'ecole cite en
    # tete de ce fichier, VERIFIE au decompile : preset `statics+0x200` + flags `0x806000000` ->
    # masque effectif `0x806000000 | *(statics+0x228)` = `0x806000000 | 0x42` = 0x806000042
    # (TargetMatchesDynamicRule | TargetIsTile | AllowObscuredTargetByElevation |
    # AllowObscuredTargetByWalls | CasterHas1Tiles). Portee = `TargetingRange statics+0x18` =
    # RANGE_FROM_CONFIG (`constants.range` = 2) ; `forceMeleeTarget` = `*(statics+0x220)` = 1 =
    # RangedBool.False. Recopier le litteral visible aurait perdu `TargetIsTile`, c'est-a-dire le
    # domaine meme du cast.
    # 1160 HeavyRailRifleAbility et 1161 TwinSmartMissileSystemAbility RESORBEES (#252) -- forme
    # « FLAGS DIRECTS », MEME porteur (`tauBroadside`), MEME TargetingRange (`statics+0x48` =
    # RANGE_WHOLE_BOARD), et pourtant DEUX masques distincts :
    #   1160 -> 0x10400040004000 = TargetIsEnemy | AllowNullCasterTile | TargetIsActor |
    #           CasterHas2TurnsLeft   (l'ability 2-phases peut viser une MACHINE et exige 2 tours)
    #   1161 -> 0x40004000         = TargetIsEnemy | AllowNullCasterTile
    # Contre-exemple intra-porteur : generaliser de l'une a l'autre aurait produit un masque FAUX.
    # 1166 AberrantHypermorphAbility RESORBEE (#253) -- ctor BIT-IDENTIQUE a 1096 (meme
    # `TargetingRange` statique +0x30, meme litteral 0x1040, meme `AbilityAttackType` = 2). LU
    # ability par ability, pas deduit de la voisine : dans ce meme lot, 1007 vaut 0x4020 et 1047
    # 0x208000.
    # 1168 EntropyCannonsAbility RESORBEE (#249) -- FLAGS DIRECTS, masque 0x40004002 =
    # 0x2 TargetMatchesDynamicRule | 0x4000 TargetIsEnemy | 0x40000000 AllowNullCasterTile.
    # 1169 PlagueburstMortarAbility RESORBEE (#249) -- FLAGS DIRECTS, masque 0x40000042 =
    # 0x2 TargetMatchesDynamicRule | 0x40 TargetIsTile | 0x40000000 AllowNullCasterTile.
    # Les deux sont des actives du MEME porteur MoW `deathCrawler`, avec le MEME `TargetingRange`
    # (`statics+0x48` = RANGE_WHOLE_BOARD) et pourtant des masques DIFFERENTS : 1168 cible une
    # UNITE ennemie, 1169 une TUILE. `AllowNullCasterTile` est la signature MoW (caster hors
    # plateau) -- un ALLOW du volet CASTER, jamais une regle de refus du filtre cible.
}


def _nom(aid: int) -> str:
    cls = ABILITY_CLASSES.get(aid)
    return cls.__name__ if cls is not None else "<hors registre>"


def test_attack_type_couvre_tout_le_registre():
    """`ABILITY_ATTACK_TYPE` couvre TOUT le registre : sa garde n'a PAS d'exemption, et ne doit
    jamais en avoir.

    Le litteral est le 3e argument de `AActiveAbility$$.ctor` -- une ligne a relire au decompile,
    pas un chantier. Rien ne justifie d'entrer au registre sans lui."""
    manquants = sorted(a for a in ABILITY_CLASSES if a not in ABILITY_ATTACK_TYPE)
    assert not manquants, (
        "abilities entrees au registre SANS leur litteral `AbilityAttackType` -> elles se degradent "
        "en Others et le gate SwornProtector reste muet pour elles. Relire le 3e argument de "
        "`<X>Ability$$.ctor` -> `AActiveAbility..ctor(this, &opts, <ICI>)` : %s"
        % [(a, _nom(a)) for a in manquants])


def test_targeting_options_ne_regresse_pas():
    """Une ability qui entre au registre pose son masque DANS LE MEME COMMIT.

    Sans masque, la cascade rend 0 sans rien gater -- le cast illegal passe, en silence."""
    nouveaux = sorted(a for a, cls in ABILITY_CLASSES.items()
                      if getattr(cls, "TARGETING_OPTIONS", None) is None
                      and a not in SANS_TARGETING_OPTIONS)
    assert not nouveaux, (
        "abilities entrees au registre SANS `TARGETING_OPTIONS` -> aucun gate de ciblage, le moteur "
        "accepte des casts que le natif REFUSE. Lire le masque dans "
        "`<X>Ability$$.ctor` -> `TargetingOptions$$.ctor` (attention a l'overload PRESET, cf. l'en-tete "
        "de ce fichier) : %s" % [(a, _nom(a)) for a in nouveaux])


def test_liste_d_exemption_ne_peut_que_retrecir():
    """LE cliquet. Sans ce sens-la, la liste se fossilise : on n'ajoute plus de dette, mais on ne
    rembourse jamais celle qui reste, et les entrees survivent a la campagne. Il a mordu pour de vrai
    le 2026-07-28 (#181) : les 13 masques du lot ont fait ECHOUER ce test tant qu'ils n'avaient pas
    ete retires de la liste."""
    resorbees = sorted(a for a in SANS_TARGETING_OPTIONS
                       if a in ABILITY_CLASSES
                       and getattr(ABILITY_CLASSES[a], "TARGETING_OPTIONS", None) is not None)
    assert not resorbees, (
        "ces abilities ont MAINTENANT leur masque : les retirer de SANS_TARGETING_OPTIONS (la liste "
        "ne peut que retrecir) -> %s" % [(a, _nom(a)) for a in resorbees])

    perimees = sorted(a for a in SANS_TARGETING_OPTIONS if a not in ABILITY_CLASSES)
    assert not perimees, (
        "entrees perimees dans SANS_TARGETING_OPTIONS -- ces abilities ne sont plus au registre : %s"
        % [(a, SANS_TARGETING_OPTIONS[a]) for a in perimees])


def test_targeting_range_accompagne_toujours_le_masque():
    """#241 -- pendant EXACT de la regle ci-dessus, sur l'axe PORTEE.

    `rules` et `range` sortent du MEME appel de ctor -- `TargetingOptions..ctor(isSelfCasting,
    range, forceMeleeTarget, rules, ...)`, ou de la MEME copie de preset statique. N'en poser qu'un
    n'est pas un choix, c'est un oubli : `TargetingOptions.range is None` = « `TargetingRange` non
    RE-lu » -> `get_range` rend None -> AUCUN gate de portee. Meme degradation permissive, meme
    invisibilite en self-play.

    Pas d'exemption ici, et il n'en faut pas : TOUS les masques poses portent leur `TargetingRange`,
    et il se lit dans la MEME ligne de decompile que le masque."""
    manquants = sorted(a for a, cls in ABILITY_CLASSES.items()
                       if getattr(cls, "TARGETING_OPTIONS", None) is not None
                       and cls.TARGETING_OPTIONS.range is None)
    assert not manquants, (
        "abilities avec `TARGETING_OPTIONS` mais SANS `TargetingRange` -> le volet portee du filtre "
        "n'est pas arme, le moteur accepte des casts hors portee que le natif REFUSE. Lire le 2e "
        "argument de `<X>Ability$$.ctor` -> `TargetingOptions$$.ctor` (ou le `<preset>+0x08..0x1f` "
        "du preset statique recopie) : %s" % [(a, _nom(a)) for a in manquants])


def test_les_quatre_porteurs_du_preset_0x40_ont_le_meme_masque():
    """#336 / `case-302-4` §5.3 -- garde de NON-REGRESSION d'un masque corrige.

    `TargetingOptions statics+0x40` est recopie INTEGRALEMENT par quatre ctors : 1020
    `HeraldOfTheApocalypse`, 1022 `BringerOfDespair`, 1029 `Drachnyen` et 1122 `CordClaw`. La copie
    passe par la surcharge **2 arguments** de `TargetingOptions..ctor` (copie PURE) ou par aucune
    surcharge du tout -- dans les deux cas AUCUN flag n'est ajoute, donc les quatre masques valent
    `*(statics+0x68)` = `TargetIsEnemy` seul.

    Le registre a porte pendant un temps `TargetIsEnemy | TargetIsNotAnObject` sur 1029, sur la foi
    d'un `..ctor(&out, &preset, 0x200000000, 0)` qui N'EST PAS la surcharge appelee : les xrefs
    entrantes des trois surcharges tranchent (1029 appelle la 2-args, et n'appelle pas la 3-args).
    Ce test verrouille la lecture corrigee -- et, plus utile, il verrouille l'INVARIANT : quatre
    porteurs d'un meme preset copie ne peuvent pas diverger sans qu'un flag soit LU quelque part."""
    porteurs = (1020, 1022, 1029, 1122)
    masques = {}
    for aid in porteurs:
        cls = ABILITY_CLASSES.get(aid)
        assert cls is not None, "%d absente du registre COMBAT -- test a re-ancrer" % aid
        opts = getattr(cls, "TARGETING_OPTIONS", None)
        assert opts is not None, "%d sans TARGETING_OPTIONS" % aid
        masques[aid] = int(opts.rules)
    attendu = int(TargetingRule.TargetIsEnemy)
    faux = {a: hex(m) for a, m in masques.items() if m != attendu}
    assert not faux, (
        "les porteurs du preset `TargetingOptions statics+0x40` doivent tous valoir "
        "`TargetIsEnemy` (%s) -- la copie de preset n'ajoute aucun flag : %s" % (hex(attendu), faux))


def test_masques_poses_ne_portent_aucun_bit_inconnu():
    """Tout bit d'un masque pose doit se nommer dans `TargetingRule` (le mirror GENERE de
    `IdunBattle.Core.Services.TargetingRule` depuis `data/symbols/<build>/frida/enums.tsv`).

    Un bit hors enum = une transcription fautive du decompile, ou un enum qui a bouge au dernier
    build. Les deux se lisent ici, et nulle part ailleurs : la cascade, elle, ignore silencieusement
    ce qu'elle ne sait pas lire."""
    connus = 0
    for membre in TargetingRule:
        v = int(membre)
        if v > 0:
            connus |= v

    fautifs = []
    for aid, cls in sorted(ABILITY_CLASSES.items()):
        opts = getattr(cls, "TARGETING_OPTIONS", None)
        if opts is None:
            continue
        reste = int(opts.rules) & ~connus
        if reste:
            fautifs.append((aid, cls.__name__, hex(reste)))
    assert not fautifs, (
        "masques portant un bit ABSENT de l'enum TargetingRule (transcription fautive, ou enum "
        "deplace au dernier build -- rejouer probe_targeting_rule_bits.py) : %s" % fautifs)


# --- SOURCE UNIQUE des regles de ciblage (#164) ---------------------------------------------------
# Le port a longtemps lu ses regles depuis DEUX endroits : le module GENERE `targeting_rule.py`
# (mirror 1:1 du dump) et ~31 constantes `RULE_*` ECRITES A LA MAIN dans `targeting.py`. Deux
# sources pour la meme information, c'est une divergence SILENCIEUSE en attente : rien n'obligeait
# la copie manuelle a suivre le dump, et trois de ses constantes portaient un nom INVENTE
# (`RULE_BIT39_...`, `RULE_BIT41_...`, `RULE_BIT57_...`) faute d'avoir le nom natif sous la main.
# Les deux tests qui suivent interdisent la re-apparition d'une seconde source.
PY_ROOT = Path(__file__).resolve().parents[3]           # scripts/python
MODULE_GENERE = PY_ROOT / "engine" / "runner" / "abilities" / "targeting_rule.py"


def _nom_normalise(ident: str) -> str:
    """`RULE_TARGET_IS_IN_RANGE` -> `TARGETISINRANGE`, pour confronter un identifiant Python
    UPPER_SNAKE au nom PascalCase d'un membre de l'enum."""
    for prefixe in ("TARGETING_RULE_", "RULE_"):
        if ident.startswith(prefixe):
            ident = ident[len(prefixe):]
            break
    return ident.replace("_", "")


def _sources_python(racine: Path = PY_ROOT) -> list:
    """`racine` : PARAMETRE depuis #486-r5, pour que la garde du cache puisse exercer le balayage
    REEL sur un corpus synthetique minuscule. Le defaut est le corpus complet -- le perimetre des
    tests de ce fichier est INCHANGE."""
    return [p for p in racine.rglob("*.py") if p != MODULE_GENERE]


#: LES DEUX RELEVES, produits par UNE SEULE passe de lecture + `ast.parse` (#486-r5).
#:
#: POURQUOI. Les deux tests ci-dessous balaient le MEME corpus (`scripts/python/**`, 2089
#: fichiers, 37 Mo) et n'en tirent que deux listes de fautifs. Mesure du 2026-08-06 : une passe
#: de lecture SERIE + `ast.parse` coute 18 a 20 s -- elle etait payee DEUX fois.
#:
#: SUR A PARTAGER : la valeur memoisee est un couple de `tuple`s de `str`. Immuable de bout en
#: bout, donc aucun etat ne fuit d'un test a l'autre. Les ASTs, eux, ne sont PAS gardes (mesure :
#: les retenir couterait 1013 Mo de tas Python pour ce corpus) -- ils sont liberes au fil de la
#: passe.
#:
#: LES CRITERES SONT INCHANGES : chaque test garde son propre releve, sa propre assertion et son
#: propre message. Seule la LECTURE est mutualisee.
_RELEVES_CACHE: tuple | None = None


def _releves_de_ciblage() -> tuple:
    """`(constantes_redeclarees, bits_en_valeur_brute)` -- deux tuples de lignes fautives."""
    global _RELEVES_CACHE
    if _RELEVES_CACHE is None:
        _RELEVES_CACHE = _balayer_ciblage()
    return _RELEVES_CACHE


def _balayer_ciblage(racine: Path = PY_ROOT) -> tuple:
    """LE balayage, sans cache. Lecture PARALLELE (`repo_read`, 16 threads) : l'ouverture d'un
    fichier sous `scripts/` pese ~7 ms (filtre systeme sur les extensions executables), soit
    3,2 s en serie contre 0,8 s en parallele sur ce corpus. Le texte rendu est celui de
    `read_text(encoding='utf-8')`, donc memes `lineno` ; un fichier illisible ou non-UTF-8 reste
    ECARTE en silence, exactement comme le faisait le `except (SyntaxError, UnicodeDecodeError)`
    de chacun des deux tests.

    `racine` : PARAMETRE, pour que la garde du cache exerce ce balayage sur un corpus synthetique
    minuscule. Le defaut est le corpus complet -- critere INCHANGE."""
    par_nom = {m.name.upper(): int(m) for m in TargetingRule}
    par_nom["ALLOWOBSCUREDTARGET"] = int(TargetingRule.AllowObscuredTarget)   # composite, non itere

    constantes, bits = [], []
    chemins = _sources_python(racine)
    for chemin, data in zip(chemins, repo_read.read_bytes_many([str(p) for p in chemins])):
        if data is None:
            continue
        try:
            arbre = ast.parse(repo_read.to_text(data))
        except (SyntaxError, UnicodeDecodeError):
            continue
        for noeud in ast.walk(arbre):
            if isinstance(noeud, (ast.Assign, ast.AnnAssign)):
                valeur = noeud.value
                if not (isinstance(valeur, ast.Constant) and isinstance(valeur.value, int)
                        and not isinstance(valeur.value, bool)):
                    continue
                cibles = noeud.targets if isinstance(noeud, ast.Assign) else [noeud.target]
                for cible in cibles:
                    if not isinstance(cible, ast.Name):
                        continue
                    ident = cible.id
                    prefixe = ident.startswith("RULE_") or ident.startswith("TARGETING_RULE_")
                    homonyme = par_nom.get(_nom_normalise(ident)) == valeur.value
                    if prefixe or homonyme:
                        constantes.append("%s:%d  %s = %#x"
                                          % (chemin.relative_to(racine).as_posix(),
                                             cible.lineno, ident, valeur.value))
            elif (isinstance(noeud, ast.Call) and isinstance(noeud.func, ast.Attribute)
                    and noeud.func.attr == "has"):
                receveur = noeud.func.value
                if not (isinstance(receveur, ast.Name) and receveur.id in ("options", "opts")):
                    continue
                for arg in noeud.args:
                    if (isinstance(arg, ast.Constant) and isinstance(arg.value, int)
                            and not isinstance(arg.value, bool)):
                        bits.append("%s:%d  options.has(%#x)"
                                    % (chemin.relative_to(racine).as_posix(),
                                       noeud.lineno, arg.value))
    return tuple(constantes), tuple(bits)


def test_le_corpus_REEL_du_balayage_est_NON_VIDE_et_porte_ses_temoins():
    """#941-r3 -- LE CRAN SANS LEQUEL LES DEUX TESTS SUIVANTS SONT DES VERTS QUI MENTENT.

    Les deux tests ci-dessous ne savent dire qu'une chose : « la liste des fautifs est vide ». Ils
    la tirent de `_balayer_ciblage()`, qui balaie `_sources_python()` = `PY_ROOT.rglob("*.py")`.
    **Si cette racine cessait de designer quoi que ce soit** -- un `parents[3]` de trop apres un
    deplacement du fichier, un renommage de `scripts/python`, un `rglob` qui ne descend plus --
    la liste des fautifs serait vide et les deux tests VERTS. Rien, dans le fichier, ne l'aurait
    dit : c'est le patron « un recenseur ne peut pas rendre zero sur ce qu'il ne visite pas »,
    applique au CORPUS au lieu du critere.

    #486-r5 etage 1 exerce bien `_balayer_ciblage(tmp_path)` sur un corpus SYNTHETIQUE (le
    detecteur voit encore) -- mais un detecteur qui voit, braque sur le vide, rend zero.

    TROIS crans, et le troisieme est celui qui distingue « non vide » de « le BON corpus » :
      1. le corpus reel est NON VIDE, et d'un ordre de grandeur qui ne peut pas etre un accident ;
      2. la racine EST `scripts/python` -- verifie par son NOM, pas par un compte ;
      3. des TEMOINS NOMMES y sont, dont le module que les deux tests confrontent
         (`engine/runner/abilities/targeting.py`, ou vivaient les 31 constantes supprimees) et le
         fichier de test COURANT. Une racine juste-mais-decalee (un cran trop haut : la racine du
         depot ; un cran trop bas : `tests/`) rend un corpus non vide et RATE ces temoins.

    COUT MESURE : un `rglob` de plus, soit ~0,9 s -- et il est paye UNE fois, le cache
    `_RELEVES_CACHE` n'etant pas concerne (ce test ne lit aucun fichier)."""
    chemins = _sources_python()
    assert PY_ROOT.name == "python" and PY_ROOT.parent.name == "scripts", (
        "la racine du balayage ne designe plus `scripts/python` mais `%s` -- les deux tests qui "
        "suivent balaieraient autre chose, et leur `assert not fautifs` serait un VERT VACUEUX "
        "(mesure #941-r3 : sur une racine effondree, un fautif PLANTE reste invisible et les deux "
        "tests rendent VERT)" % PY_ROOT)
    assert len(chemins) > 1000, (
        "le corpus REEL du balayage est tombe a %d fichiers -- les deux tests qui suivent "
        "rendraient VERT sans avoir rien visite. Racine : %s" % (len(chemins), PY_ROOT))
    noms = {p.relative_to(PY_ROOT).as_posix() for p in chemins}
    temoins = {"engine/runner/abilities/targeting.py",
               "tests/engine/runner/test_ability_registry_ratchet.py"}
    assert temoins <= noms, (
        "le corpus reel ne porte pas ses temoins -- la racine designe autre chose que "
        "`scripts/python` : manquants %s" % sorted(temoins - noms))
    assert MODULE_GENERE.relative_to(PY_ROOT).as_posix() not in noms, (
        "le module GENERE doit rester EXCLU du corpus -- sinon ses propres declarations "
        "`TargetingRule.<Nom> = <ordinal>` seraient comptees comme des fautifs")


def test_aucune_constante_de_ciblage_declaree_hors_du_module_genere():
    """UNE seule source de noms de bits : `engine/runner/abilities/targeting_rule.py`, GENERE par
    `scripts/python/gen_targeting_rule.py` depuis `data/symbols/<build>/frida/enums.tsv`.

    Rougit sur toute RE-DECLARATION d'une constante de ciblage ailleurs, sous deux formes :

      * un identifiant prefixe `RULE_` / `TARGETING_RULE_` affecte a un entier -- la forme exacte
        des 31 constantes supprimees, et de la copie locale qui vivait dans
        `probe_range_gate_melee_clamp.py` ;
      * un identifiant NON prefixe dont le nom ET la valeur retombent sur un membre de l'enum
        (ex. `TARGET_IS_ENEMY = 0x4000`) -- le contournement evident de la regle ci-dessus.

    Le mode de defaillance garde ici n'est pas l'erreur : c'est la copie qui reste JUSTE aujourd'hui
    et devient FAUSSE au prochain re-dump, sans que rien ne le dise."""
    fautifs = list(_releves_de_ciblage()[0])
    assert not fautifs, (
        "constantes de ciblage declarees HORS du module genere -- il y a de nouveau DEUX sources "
        "pour la meme information, et rien n'oblige la copie a suivre le dump. Importer "
        "`from engine.runner.abilities.targeting_rule import TargetingRule as TR` et citer "
        "`TR.<NomNatif>` : %s" % fautifs)


def test_aucun_bit_de_ciblage_cite_par_sa_valeur_brute():
    """Pendant du test precedent, sur l'autre facon de contourner la source unique : ne pas
    declarer de constante du tout et ecrire le litteral au point d'usage (`options.has(0x4000)`).

    Le symptome que ca produit se lit dans nos propres traces : la tache #166 decrivait le refus
    d'une cible deja adjacente comme « le bit `0x100000000` », faute de pouvoir le nommer. Le
    module genere le nomme : `TargetIsNotAdjacent`."""
    fautifs = list(_releves_de_ciblage()[1])
    assert not fautifs, (
        "bits de ciblage cites par leur VALEUR BRUTE au point d'usage -- un lecteur ne peut pas "
        "verifier un masque qu'il doit decoder de tete. Citer `TR.<NomNatif>` : %s" % fautifs)


def test_module_genere_concorde_avec_le_dump_du_build_courant():
    """L'autre moitie de la source unique : la source EST unique, encore faut-il qu'elle soit a
    jour. Le module est GENERE, donc il peut dater d'un build anterieur sans que rien ne le dise --
    et tous les masques `TARGETING_OPTIONS` du registre deviennent faux d'un coup, en silence.

    Meme confrontation que `scripts/python/probe_targeting_rule_bits.py` (dont ce test reutilise les
    lecteurs), mais DANS la suite : un probe qu'on oublie de lancer ne garde rien."""
    import probe_targeting_rule_bits as P

    build = P.build_hash()
    dump, genere = P.from_dump(build), P.from_python()
    ecarts = [(bit, dump.get(bit), genere.get(bit))
              for bit in sorted(set(dump) | set(genere))
              if dump.get(bit) != genere.get(bit)]
    assert not ecarts, (
        "le module GENERE `targeting_rule.py` a derive du dump du build %s -- regenerer "
        "(`python scripts/python/gen_targeting_rule.py`) et RELIRE les masques du registre, "
        "qui sont tous suspects : %s" % (build, ecarts))
