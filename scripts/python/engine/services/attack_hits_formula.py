"""Port de `IdunBattle.Entities.Formulas.AttackHitsWithModifiersFormula` (`IdunBattle.Entities.Formulas.AttackHitsWithModifiersFormula$$Calculate`) — la
FORMULE (noeud DSL) qui calcule le NB DE COUPS d'une attaque AVEC ses modificateurs, PARTAGEE par tous les
contextes. Nativement, les facades `GetAttackHits` (slot d'interface 0xb5) delegent a cette formule :
  - `IdunBattle.Operations.AttackDamageOperation$$GetAttackHits`  = COMBAT (runner) ;
  - `IdunBattle.Core.Services.DamagePrediction$$GetAttackHits`  = PREDICTION (playbook) ;
  - `IdunBattle.Core.Services.BattleQuery$$GetAttackHits`  (+ variantes Cached/Recorded/Query).

Les call-sites du port SONT ces facades : le combat (`AttackDamageOperation.execute` pour l'attaque
NORMALE, `execute_ability_attack` pour l'attaque d'ABILITY de la famille ATTACK) et la prediction
(`make_normal_attack_predictions`) rassemblent leurs entrees (ECS vs Scene) puis appellent cette formule.
C'est FIDELE : le natif PARTAGE la formule (il ne la duplique pas entre combat et prediction), donc le
port la partage aussi (un seul point de calcul, plusieurs facades).

PERIMETRE EXACT DU CANAL (case-61, RE + mesure live) — trois vecteurs, TROIS verdicts DISTINCTS :
  1. COMBAT, attaque NORMALE : `IdunBattle.Operations.AttackDamageOperation$$Execute` appelle
     `IdunBattle.Operations.AttackDamageOperation$$GetAttackHits` -> formule. Base = nb de coups de l'arme.
  2. COMBAT, attaque d'ABILITY **famille ATTACK** (`IdunBattleLogic.Entities.DSLBehaviors$$AttackWithAttackDamage`
     -> `AttackDamageBehaviour` -> `AttackDamageOperation`) : MEME `Execute`, MEME `GetAttackHits` -> formule.
     La BASE change seulement : c'est le noeud `hits` du DSL (champ +0x80 du behaviour, evalue dans
     `IdunBattle.Entities.Behaviours.AttackDamageBehaviour$$ExecuteTarget` en `Nullable<int>` de l'AttackData),
     pas le nb de coups de l'arme. GROUND TRUTH live (case-61) : FlailSwing (`nrOfHits`=3) rend **2** coups
     contre une cible `Parry_ReduceHits` et **3** contre le temoin -> le canal EST traverse.
  3. COMBAT, attaque d'ABILITY **famille ABILITY** (`IdunBattleLogic.Entities.DSLBehaviors$$AttackWithAbilityDamage`
     -> `AbilityDamageOperation`) : `IdunBattle.Operations.AbilityDamageOperation$$Execute` N'APPELLE PAS
     `GetAttackHits` — il lit le `Nullable<int>` de l'AttackData et l'utilise BRUT (defaut 1 si absent).
     AUCUN ExtraHits, AUCUN effet. -> le port ne traverse PAS la formule pour cette famille.
  4. PREDICTION d'une attaque d'ABILITY (`IdunBattle.AI.Playbook.ComparablePlaybooku003C__Il2CppFullySharedGenericTypeu003E$$GenerateMultiHitAttackPredictions`)
     : le playbook EVALUE le noeud `hits` de l'ability et le passe tel quel a `PredictAttack` (slot 0x27) —
     la formule n'est PAS interposee. GROUND TRUTH live (case-61) : la MEME FlailSwing predit **3** coups
     contre la cible Parry (vs 2 reellement appliques), et FrenziedFiring predit le meme nb de coups contre
     une cible `Camouflage_HitReduction` que contre le temoin. -> `generate_multi_hit_attack_prediction`
     reste sur la BASE seule (`get_special_hits`), c'est FIDELE. Ne pas "corriger" cette asymetrie : elle
     est NATIVE (l'IA sur-estime ses propres attaques speciales contre les porteurs de Parry/Camouflage).

Composition (chaque piece deleguee a SON port de classe natif) :
  1. base = `IdunBattle.Core.Services.DamagePrediction$$GetDefaultAttackHits` (`weapon + ExtraHits(0x11) + (melee ? ExtraHitsMelee(0x17))`)
     + `Sigma effets` (EffectAdditionalHits, clamps Min/Max type LightCover), plancher Max(.,0)
     -> `services.damage_prediction.get_default_attack_hits` + `entities.effects.hits_bonus_from_effects`.
  2. + GetStuckIn : behaviour `IdunBattle.Entities.Behaviours.AddBonusHitsToCurrentHitGroupBehaviour$$Execute` (ajoute au hit-group PENDANT l'exec, gate `Maybe(IdunBattleLogic.Entities.Abilities.Triggered.Loki.GetStuckInAbility$$GetBonusHitChance)` = 30%/100%)
     -> `entities.traits.attacker_bonus_hits`. **Gate par `include_bonus_hit_behaviours`** (cf. ci-dessous).
  3. + malus de coups de la CIBLE : `IdunBattle.Operations.AdditionalHitsFromEffects.GetAdditionalHits
     FromEffects IdunBattle.Operations.AdditionalHitsFromEffects$$GetAdditionalHitsFromEffects` (LightCover -2 ranged / Parry -1 melee) + aura BigTarget  -> `entities.effects`
     (`hits_malus_from_defender_effects` / `aura_hits_malus_for_defense`).
  4. INTERRUPTEUR des REDUCTIONS : `IdunBattle.Entities.Effects.BaseEffect$$BlockHitsReduction`
     (case-366-r1) -> `entities.effects.block_hits_reduction_from_effects`. Ce n'est PAS un terme
     de la somme. `DamagePrediction$$GetAttackHits` range les `HitsBonusForAttack` en DEUX listes
     selon le SIGNE de leur `addition` (`< 0` = reduction), somme la liste des additions
     INCONDITIONNELLEMENT, et ne somme celle des REDUCTIONS que si aucun effet actif n'a rendu
     `BlockHitsReduction == true`. Le tri est au SIGNE, pas a la provenance : un `Parry` de la
     cible, un `BigTarget` d'aura et un `FightingRetreat_HitReduction` de l'ATTAQUANT tombent dans
     la MEME liste, donc s'eteignent ensemble. Le balayage est BOARD-WIDE (mirror de
     `EffectsQuery$$GetActiveEffectsWithBonuses`, qui n'a aucun argument de portee) ; les DEUX
     implementeurs natifs sont portes :
       - `1117 InescapableAccuracy_overrideHits` (`get_OwnerIsCaster & IsRangedAttack`, eldarMauganRa) ;
       - `1538 PurgeResponse` (`TriggeringAbilityIs(EffectType 1009 Overwatch_AutoAttack)`, SANS
         `get_OwnerIsCaster` -> n'importe quel porteur du board, n'importe quel camp ; votanSmnSteeljack).

NATURE DU COUP (`is_melee`) -- #122. Le natif l'obtient par
`IdunBattle.Core.Services.BattleQuery$$IsMeleeAttack` (que `DamagePrediction$$GetAttackHits` appelle sur
l'`AbilityOrEffect` de l'AttackData) : elle est **DECLAREE** par l'ability
(`GetAbilityAttackRangeType` : 0 absent -> melee ET ranged FAUX · 1 Melee · 2 Ranged · 3 Normal ->
positionnel `AreUnitsInMelee`). Le MEME resultat alimente le terme `ExtraHitsMelee` de la base ET les
gates des effets -- un seul point de calcul. TRI-ETAT : `None` = nature non declaree, les DEUX familles
de gates se taisent (les gates `IsRangedAttack` testent donc `is_melee is False`, pas la truthiness ;
`LightCover`, dont le trigger est `!IsMeleeAttack` et NON `IsRangedAttack`, s'applique sur `None`).

Fidelite GetStuckIn (2) -- divergence PREDICTION vs COMBAT (verdict validateur cluster, BITE 2) : le natif
applique GetStuckIn comme un behaviour SEPARE chance-gate PENDANT l'execution (pas dans la formule). Les
DEUX faces sont portees, avec deux emplacements DISTINCTS (fidele : la formule native != l'execution) :
  - PREDICTION (`DamagePrediction.GetAttackHits`) l'inclut de facon DETERMINISTE dans la formule (la chance ne
    pilote que le roll d'exec, pas la prediction de degat de l'IA) -> `include_bonus_hit_behaviours=True`
    (fold correct, confirme live seed777 + validateur).
  - COMBAT (`AttackDamageOperation.GetAttackHits`) NE le fold PAS dans la formule -> `include_bonus_hit_
    behaviours=False` (la formule native ne l'inclut pas : folder en dur sur-comptait, orksNob 1v1 chance=30
    -> natif 3 coups, folder 4). Le coup bonus est ajoute a l'EXECUTION par le behaviour chance-gate PORTE
    (#62c, commit 3997793) : `runner.damage_model.getstuckin_combat_chance` (mirror `IdunBattleLogic.Entities.Abilities.Triggered.Loki.GetStuckInAbility$$GetBonusHitChance` + gate trigger `On(8) & IsOdd(CurrentHitIndex) & OwnerIsCaster & !(MinDistance>2)`
    IdunBattleLogic.Entities.Abilities.Triggered.Loki.GetStuckInAbility$$CreateTrigger) alimente `bonus_hit_chance` de `runner.operations.damage_hits._run_hits`, qui roll
    `Maybe(GetBonusHitChance)` (1 tirage `NextBool`, `IdunBattle.Entities.Behaviours.MaybeBehaviour$$Execute`) APRES le block de
    chaque coup d'INDEX IMPAIR (0-based ; `CurrentHitIndex` = compteur persistant `attack+0x30`, lu dans
    `IdunBattle.Operations.ADamageOperation$$EvaluateAfterHitTriggers`), puis execute les coups bonus DEFERES (FIFO, mirror
    `Execute@180e60c70` : boucle base peuple `hitGroup+0x58`, re-`ExecuteHits` par entree). VALIDE bit-exact
    LIVE (case-67) : orksNob base-3 (0/1 coup bonus) + orksBigMek base-4 (0/1/2 coups bonus), off_ph==live_ph.
Le combat manquait aussi (3) LightCover/Parry/BigTarget (verdict #62a, toujours valide -- non chance-gate,
donc partage sans reserve avec la prediction).
"""
from __future__ import annotations

import hexgeo

from ..entities.effects import (hits_bonus_from_effects, hits_malus_from_defender_effects,
                                 aura_hits_malus_for_defense, aura_hits_bonus_for_attack,
                                 block_hits_reduction_from_effects, board_effect_carriers)
from ..entities.traits import attacker_bonus_hits
from .damage_prediction import get_default_attack_hits


def attack_hits_with_modifiers(*, weapon_hits: int, extra_hits: int, extra_hits_melee: int,
                               attacker_effects, trait_objects, target_effects, aura_sources,
                               board: dict, is_melee: bool | None, damage_profile: str | None,
                               include_bonus_hit_behaviours: bool = False,
                               defender_on_cover: bool | None = None,
                               is_normal_attack: bool = True,
                               hit_group_index: int = 0,
                               is_prediction: bool = False) -> int:
    """`IdunBattle.Entities.Formulas.AttackHitsWithModifiersFormula$$Calculate` : nb de coups d'une attaque normale. `board` =
    {att_id, tgt_id, attack_pos, t_pos, tgt_team, is_melee, pos_by_id, team_by_id} (base_hits pose ici) ;
    `aura_sources` = [(owner_id, pos, team, effets)] des unites != cible. Ordre = base (APRES PowerTrip) ->
    +GetStuckIn/traits (SSI `include_bonus_hit_behaviours` : prediction=True [fold formule] ; combat=False
    [le coup bonus est ajoute a l'EXECUTION par `_run_hits`, PAS ici], cf. entete BITE 2)
    -> +malus defenseur/aura, plancher 1.

    #227 — `LetTheGalaxyBurn` N'EST PLUS un terme de cette formule. Son artefact natif est un
    descripteur `IdunBattle.Entities.Effects.EffectAdditionalHits` (canal #179), PAS un
    `EffectHitsBonusForAttack` : il est desormais porte par `additional_hit_groups` /
    `runner/operations/additional_hits.py`, qui recoit lui-meme `tile_effects_by_pos` /
    `persistent_data` (le gate) et le `HitDamage` de l'attaque (le degat). Les deux parametres
    correspondants ont donc quitte cette signature — ils n'avaient AUCUN autre consommateur."""
    # Contexte de l'attaque passe aux effets du canal (1) : le `board` de la formule. Un seul dict =
    # un seul point d'enrichissement pour les futurs gates cible.
    att_hits_ctx = {**(board or {})}
    # (0) INTERRUPTEUR `BaseEffect$$BlockHitsReduction` (case-366-r1). Le natif l'evalue dans une
    # boucle DEDIEE, sur la MEME collection d'effets actifs que les bonus de coups et AVANT toute
    # somme, puis s'en sert pour SAUTER la liste des bonus a `addition < 0`
    # (`DamagePrediction$$GetAttackHits`). Il est donc calcule ici, une seule fois, et threade a
    # chacun des quatre agregateurs de l'axe -- le tri se fait bonus par bonus au SIGNE (foyer
    # `entities.effects._hits_contribution`), jamais sur un agregat ni par provenance.
    # BALAYAGE BOARD-WIDE (`#366-r1-blockhits-purgeresponse`) : `EffectsQuery$$GetActiveEffects
    # WithBonuses` ne prend AUCUN argument de portee, et le SECOND implementeur du canal
    # (`PurgeResponseEffect` = `TriggeringAbilityIs(Overwatch_AutoAttack)`) n'a pas de noeud
    # `get_OwnerIsCaster` -> son porteur peut etre n'importe qui, y compris dans l'autre camp. Les
    # trois collections que cette formule tient deja RECOUVRENT l'univers natif : attaquant + cible
    # + `aura_sources` (= toutes les unites vivantes != cible). `False` tant qu'aucun effet ACTIF ne
    # l'arme => no-op strict hors porteur.
    block_reduction = block_hits_reduction_from_effects(
        board_effect_carriers((board or {}).get("att_id"), attacker_effects,
                              (board or {}).get("tgt_id"), target_effects, aura_sources),
        att_hits_ctx)
    # `is_normal_attack` = nature du VECTEUR (attaque normale vs attaque d'ABILITY), threade jusqu'aux
    # bonus dont le trigger natif porte le noeud `IdunBattleLogic.Entities.DSLTriggers$$IsNormalAttack`
    # (la surcharge SANS argument delegue a celle qui en prend un ; toutes deux finissent sur
    # `idun.Idun.Source.Shared.Battle.StaticBattleRules.StaticBattleRules.ActiveAbility$$IsRegularAttack`,
    # evalue par `IdunBattle.Entities.Triggers.AbilityIsNormalAttackTrigger$$ShouldTrigger` sur
    # l'`ActiveAbilityType` de l'`AbilityEntities` du coup).
    # RE-BALAYE le 2026-08-02 (#419-r1-tr9-r4-r1, xrefs des DEUX surcharges) -- ce canal en a **SIX**
    # consommateurs, pas un ; le commentaire d'avant n'en citait qu'un et affirmait a tort que « les
    # autres bonus/malus du canal n'ont PAS ce gate » :
    #   * `IdunBattle.Entities.Effects.Loki.PowerTrip_FullHealthEffect$$CreateEffectHitsBonusForAttack`
    #     (`IsNormalAttack & get_OwnerIsCaster`)                                        -- PORTE ici ;
    #   * `IdunBattle.Entities.Effects.Loki.Waaagh_ExtraHitsEffect$$CreateEffectHitsBonusForAttack`
    #     (`IsNormalAttack & IsMeleeAttack & get_OwnerIsCaster`)                        -- PORTE ici ;
    #   * `IdunBattle.Entities.Effects.Loki.ShroudPsalmEffect$$CreateEffectHitsBonusForAttack`
    #     (1366, `get_OwnerIsTarget & IsNormalAttack` -- un MALUS defenseur, `ForAdditionWithMinimum`)
    #     -- PORTE (#419-r1-tr9-r4-r1-r2), cote DEFENSE : c'est pourquoi `is_normal_attack` est
    #     desormais threade jusqu'a `hits_malus_from_defender_effects` ;
    #   * `IdunBattle.Entities.Effects.Loki.VoltagheistField_ExtraHitEffect$$CreateEffectHitsBonusForAttack`
    #     (1381, `get_OwnerIsCaster & IsNormalAttack`)     -- PORTE (#419-r1-tr9-r4-r1-r2) ;
    #   * `IdunBattle.Entities.Effects.Loki.Dakka_ExtraHitsEffect$$CreateEffectHitsBonusForAttack`
    #     (1105, `AmountIsEqual(MinDistance(Caster,Target), 2) & AmountIsEqualOrGreater(
    #     AttackWeaponRange, 3) & get_OwnerIsActor & IsNormalAttack & IsRangedAttack`)
    #     -- NON PORTE, **registered-but-DEAD** : son unique voie d'attribution est le TRAIT `Dakka`
    #     (`DakkaAbility` = `AOwnerEffectSpecificTriggeredAbility`, seul appelant de son ctor =
    #     `AbilitiesDatabase.<InitializeTriggeredAbilities>b__28_107`), et AUCUNE unite du gameconfig
    #     `rnca9r7q6c` ne porte ce trait ;
    #   * `IdunBattle.Entities.Effects.Loki.LegendaryCommander_ExtraHitsEffect$$IsValidAttack`
    #     (1395, en NEGATION : `get_OwnerIsTarget & AreFriends(Caster, EffectSource) & !IsNormalAttack
    #     & !(TriggeringAbilityIsNormalAttack & IsPartialAttackAbility)`, plus `!IsInPersistentDataList
    #     & IsFirstHitGroupInAttack`) -- PORTE (#419-r1-tr9-r4-r1-r2-r1), sur le canal **AURA**
    #     (`aura_hits_bonus_for_attack`) : l'effet vit sur `custoTrajann` et ce sont ses `Targets`
    #     (le `CreateTargetSelector`) qui designent les ennemis, pas le porteur. C'est le SEUL
    #     consommateur du canal gate en NEGATION, et l'unique lecteur de `hit_group_index`.
    # Les bonus/malus du canal qui n'ont VRAIMENT pas ce gate restent ceux d'avant
    # (FightingRetreat_HitReduction, Parry, LightCover, Camouflage, Diminutive, BigTarget,
    # DefenderOfTheGreaterGood).
    # Defaut True = attaque normale (comportement historique inchange).
    eff_hits = hits_bonus_from_effects(attacker_effects, bool(is_normal_attack), att_ctx=att_hits_ctx,
                                       block_reduction=block_reduction)
    # base = `IdunBattle.Core.Services.DamagePrediction$$GetDefaultAttackHits` : weapon + ExtraHits(0x11) + (melee ? ExtraHitsMelee(0x17)).
    # is_melee=None (contexte inconnu) -> False -> pas d'ExtraHitsMelee (conservateur, mêlée seule).
    base_default = get_default_attack_hits(int(weapon_hits), int(extra_hits), int(extra_hits_melee),
                                           bool(is_melee))
    # PLANCHER — mirror BORNE du natif. `IdunBattle.Core.Services.DamagePrediction$$GetAttackHits`
    # ne plancher JAMAIS a 1 : il termine par `System.Math.Max(hits, 0)` (et sa base est elle-meme
    # `Math.Max(weapon + ExtraHits + ExtraHitsMelee, 0)`). Le « minimum 1 coup » observe sur
    # LightCover/Parry vient du CLAMP PAR-EFFET `hits = Math.Max(hits, Math.Min(base, cap))`, que ce
    # port approxime historiquement par un `max(1, ...)` global.
    # Cette approximation est CORRECTE tant que la base est >= 1, et FAUSSE quand elle vaut 0 : le
    # clamp natif est borne par la BASE (`Math.Min(base, cap)` = 0 si base = 0), donc rien ne peut
    # remonter au-dessus de 0. MESURE LIVE (probe_psychic_aoe --case db-4, Doombolt 1102 : 3 coups
    # repartis sur 4 cibles -> la 4e recoit une base de 0) : le natif ne lui porte AUCUN coup, le port
    # lui en portait 1 (1603 de degat fantome). D'ou `min(1, base_default)` : identique partout ou la
    # base est >= 1 (aucune regression), et 0 quand la base est 0 (le seul regime ou les deux
    # divergent). Le port INTEGRAL des caps par-effet reste un chantier separe (composant PARTAGE).
    _floor = min(1, base_default)
    hits_pre = max(_floor, base_default + eff_hits)   # base APRES PowerTrip, AVANT GetStuckIn
    # `hit_group_index` = le 3e argument de `IdunBattle.Core.Services.DamagePrediction$$GetAttackHits`,
    # que le natif pose en `Nullable<int>` dans l'`AbilityEntities` qu'il synthetise et qui n'atteint
    # le DSL que par `IdunBattle.Entities.Abilities.AbilityEntities$$get_IsFirstHitGroup`
    # (`HasValue && Value == 0`), lu par le seul
    # `IdunBattleLogic.Entities.DSLTriggers$$IsFirstHitGroupInAttack` -> `LegendaryCommander_ExtraHits`.
    # LES QUATRE FACADES PORTEES SONT LE GROUPE D'ARME, INDEX 0, et c'est LU, pas suppose :
    #   * COMBAT -- `IdunBattle.Operations.AttackDamageOperation$$Execute` passe
    #     `*(int*)(currentAttack + 0x34)` au slot 0xb6 (`$$GetAttackHits`), et
    #     `IdunBattle.Core.OngoingAttack$$.ctor` initialise ce bloc (`+0x30`, 8 octets) a ZERO.
    #     Les groupes de coups ADDITIONNELS a profil re-entrent `Execute` avec un index INCREMENTE --
    #     le port ne leur fait PAS traverser cette formule (`execute_additional_hits` consomme le
    #     `count` du descripteur #179), donc aucune sur-application de ce cote.
    #   * PREDICTION -- `make_normal_attack_predictions` et le fold `GetAdditionalDamagePrediction`
    #     passent tous deux le litteral `0` (tranche #419-r1-tr9-r4-r2).
    # Parametre (et non constante) pour qu'un test puisse le faire MORDRE.
    board = {**(board or {}), "base_hits": hits_pre,
             "hit_group_index": (None if hit_group_index is None else int(hit_group_index)),
             # nature du VECTEUR, deja threadee aux canaux ATTAQUANT et DEFENSEUR : le canal AURA en
             # a besoin lui aussi depuis `LegendaryCommander_ExtraHits` (`!IsNormalAttack`).
             "is_normal_attack": bool(is_normal_attack),
             # `is_prediction` -- la FACE, et c'est un axe DISTINCT de tous les autres du board.
             #
             # Pourquoi il faut le porter : le canal #179 (`EffectAdditionalHits`) n'a PAS le meme
             # rendu sur les deux faces, et les deux rendus sont MESURES, pas deduits :
             #   * COMBAT (#204) -- l'evenement supplementaire de `MasterAnnihilator` vaut la
             #     CONSTANTE `reduce(base)` (stat ATTACK a l'unite, 4617 sur 5/5) quand les coups
             #     d'ARME de la meme campagne prennent 8 valeurs distinctes sur 8. C'est un GROUPE,
             #     et la formule de coups ne doit RIEN ajouter ;
             #   * PREDICTION (#10019) -- le natif rend UN COUP DE PLUS au degat EXACT d'un coup
             #     d'arme : trois paires vers la meme cible, six nombres, tous en rapports ENTIERS
             #     `(h+1)/h` sur les DEUX bornes (4->5, 2->3, 6->7). Un groupe a degat CONSTANT ne
             #     peut pas produire ce profil (il ajouterait le meme entier aux deux bornes).
             #
             # C'est la MEME forme que `include_bonus_hit_behaviours` (GetStuckIn : deterministe
             # dans la formule cote prediction, chance-gate a l'execution cote combat), et c'est un
             # parametre SEPARE a dessein -- les deux axes ne commandent pas les memes termes, et
             # les confondre rendrait vacant le cliquet qui garde le verdict #204
             # (`test_ah_master_annihilator_astartes_banner_live.py`, monte en regime COMBAT mais
             # avec `include_bonus_hit_behaviours=True`).
             #
             # Defaut `False` = COMBAT : tout appelant qui ne le passe pas garde EXACTEMENT le
             # comportement d'avant, y compris les quatre facades de combat et les probes.
             "is_prediction": bool(is_prediction)}
    # (2) GetStuckIn = behaviour d'exec chance-gate (`AddBonusHitsToCurrentHitGroupBehaviour IdunBattle.Entities.Behaviours.AddBonusHitsToCurrentHitGroupBehaviour$$Execute`) :
    # DETERMINISTE en prediction (fold ICI), chance-roll a l'EXECUTION en combat (porte #62c dans
    # `_run_hits`, PAS dans cette formule -> gate False). Seul GetStuckInTrait override `as_attacker_bonus_
    # hits` -> gater `attacker_bonus_hits` ne perd que GetStuckIn cote formule (cf. entete BITE 2).
    bonus_hits = attacker_bonus_hits(trait_objects, board) if include_bonus_hit_behaviours else 0
    hits = hits_pre + bonus_hits
    # #204 — l'aura COUPS d'`AstartesBanner` a QUITTÉ cette formule : son artefact natif est
    # `IdunBattle.Entities.Effects.Loki.AstartesBanner_AdditionalHitsEffect$$CreateAdditionalHits`
    # (canal #179), donc `additional_hit_groups` / `runner/operations/additional_hits.py`.
    # #372 — le canal `aura_hits_bonus_for_attack` REVIENT ici, avec l'alimenteur natif qui manquait :
    # `IdunBattle.Entities.Effects.Loki.DefenderOfTheGreaterGood_ExtraHitsEffect$$CreateEffectHitsBonus
    # ForAttack` (1183 `tauShadowsun` / 1307 son Command-Link Drone) est bien un `EffectBonus.
    # ForAddition`, donc un TERME de cette formule -- un coup d'ARME de plus, pas un groupe a dégât
    # propre. Il est placé APRÈS `GetStuckIn` et AVANT les malus défenseur : le natif ne sépare pas
    # ces termes (une seule somme dans `DamagePrediction$$GetAttackHits`), seul le plancher final
    # `Math.Max(., 0)` les borne — c'est lui qui suit.
    # Les porteurs sont les MÊMES `aura_sources` que le canal malus (BigTarget) : le natif énumère
    # TOUS les effets actifs du board (`EffectsQuery$$GetActiveEffectsWithBonuses`), attaquant exclu
    # par le sélecteur de l'effet, pas par la boucle.
    # Le ctx du canal AURA part du `board` COMPLET -- mirror : le natif passe LE MEME
    # `AbilityEntities` a tous les effets de la boucle, il n'en construit pas un sous-ensemble par
    # canal. Les clés `att_*` ci-dessous restent les ALIAS historiques que lisent les porteurs
    # existants (`DefenderOfTheGreaterGood`), et `LegendaryCommander_ExtraHits` lit les clés CIBLE
    # (`tgt_id`/`t_pos`/`team_by_id`/`pos_by_id`) + `is_normal_attack`/`hit_group_index`/
    # `trigger_ability_type`/`used_active_by_id`/`persistent_data_list` que le board porte deja.
    hits += aura_hits_bonus_for_attack(aura_sources, {
        **board,
        "att_id": board.get("att_id"), "att_pos": board.get("attack_pos"),
        "att_team": (board.get("team_by_id") or {}).get(board.get("att_id")),
        # `UnitsFromFaction(SurroundingFriends(owner, 2), 9 = Tau)` du sélecteur DotGG.
        "att_faction": board.get("att_faction"),
        "is_melee": is_melee, "damage_profile": damage_profile,
        # `UnitTurnsStarted(If(AmountIsGreaterThanZero(Parent(src)), Parent(src), src))` = `GetStat(.,
        # 0xc)` du PORTEUR (ou de son summoner) -> substrat d'ENTITÉ, pas du coup.
        "turns_started_by_id": board.get("turns_started_by_id"),
        "parent_by_id": board.get("parent_by_id"),
        # `Maybe(chance)` : PRNG en COMBAT (le tirage CONSOMME un genrand), None en PRÉDICTION —
        # c'est exactement `ANonDeterministicAbilityTrigger$$CanUseRandom == false`, où le natif
        # substitue `99 < chance` au tirage (cf. `entities.triggers.MaybeTrigger`).
        "rng": board.get("rng")},
        # inerte pour l'alimenteur actuel (POSITIF) -- threade parce que le tri natif porte sur le
        # SIGNE de chaque bonus, pas sur le canal qui le produit.
        block_reduction=block_reduction)
    # (3) malus défenseur : LightCover -2 ranged / Parry -1 mêlée / Camouflage. Le gate
    # compute-time `defender_on_cover` (A3, #113) empêche LightCover de sur-appliquer un effet périmé en
    # runner-sim (cible ayant quitté sa tuile de cover) ; None (prédiction) = applique-sur-présence.
    # Distance AVERAGE(Caster,Target) hex (branches Camouflage dist>2 -> -2 / dist<=2 -> -1),
    # calculee ICI depuis le board (attack_pos = tuile candidate du caster, t_pos = cible) : les DEUX
    # facades (prediction + combat) peuplent ces cles -> pas d'edit de call-site pour la distance.
    _cam_ap, _cam_tp = board.get("attack_pos"), board.get("t_pos")
    _cam_dist = (hexgeo.distance(tuple(_cam_ap), tuple(_cam_tp))
                 if (_cam_ap is not None and _cam_tp is not None) else None)
    hits = max(_floor, hits            # `Math.Max(·, 0)` natif, borne par la BASE (cf. `_floor`)
               + hits_malus_from_defender_effects(target_effects, is_melee, damage_profile,
                                                  defender_on_cover=defender_on_cover,
                                                  dist=_cam_dist,
                                                  block_reduction=block_reduction,
                                                  # #419-r1-tr9-r4-r1-r2 : `ShroudPsalmEffect` porte
                                                  # `get_OwnerIsTarget & IsNormalAttack` -- le canal
                                                  # DEFENSE a lui aussi ce noeud.
                                                  is_normal_attack=bool(is_normal_attack),
                                                  # Le `board` COMPLET, le MEME que celui deja passe
                                                  # aux canaux ATTAQUANT et AURA : le natif n'a QU'UN
                                                  # canal et passe le MEME `AbilityEntities` a tous
                                                  # les effets de sa boucle. Consommateur :
                                                  # `TerrorsLament_HitReduction`, dont le trigger
                                                  # porte sur l'ATTAQUANT.
                                                  att_ctx=board)
               + aura_hits_malus_for_defense(aura_sources, board,
                                             block_reduction=block_reduction))
    return hits
