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
  2. COMBAT, attaque d'ABILITY **famille ATTACK** (`IdunBattleLogic.Entities.DSLFactory$$AttackWithAttackDamage`
     -> `AttackDamageBehaviour` -> `AttackDamageOperation`) : MEME `Execute`, MEME `GetAttackHits` -> formule.
     La BASE change seulement : c'est le noeud `hits` du DSL (champ +0x80 du behaviour, evalue dans
     `IdunBattle.Entities.Behaviours.AttackDamageBehaviour$$ExecuteTarget` en `Nullable<int>` de l'AttackData),
     pas le nb de coups de l'arme. GROUND TRUTH live (case-61) : FlailSwing (`nrOfHits`=3) rend **2** coups
     contre une cible `Parry_ReduceHits` et **3** contre le temoin -> le canal EST traverse.
  3. COMBAT, attaque d'ABILITY **famille ABILITY** (`IdunBattleLogic.Entities.DSLFactory$$AttackWithAbilityDamage`
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
                                 aura_hits_malus_for_defense, aura_hits_bonus_for_attack)
from ..entities.traits import attacker_bonus_hits
from .damage_prediction import get_default_attack_hits


def attack_hits_with_modifiers(*, weapon_hits: int, extra_hits: int, extra_hits_melee: int,
                               attacker_effects, trait_objects, target_effects, aura_sources,
                               board: dict, is_melee: bool | None, damage_profile: str | None,
                               include_bonus_hit_behaviours: bool = False,
                               defender_on_cover: bool | None = None,
                               is_normal_attack: bool = True) -> int:
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
    # `is_normal_attack` = nature du VECTEUR (attaque normale vs attaque d'ABILITY), threade jusqu'aux
    # bonus dont le trigger natif porte le noeud `IsNormalAttack` (`IdunBattleLogic.Entities.DSLFactory$$IsNormalAttack`) —
    # aujourd'hui `IdunBattle.Entities.Effects.Loki.PowerTrip_FullHealthEffect$$CreateEffectHitsBonusForAttack`
    # (`IsNormalAttack & OwnerIsCaster`). Les autres bonus/malus du canal n'ont PAS ce gate
    # (FightingRetreat_HitReduction, Parry, LightCover, Camouflage, Diminutive, BigTarget, AstartesBanner) :
    # ils s'appliquent aux DEUX vecteurs. Defaut True = attaque normale (comportement historique inchange).
    eff_hits = hits_bonus_from_effects(attacker_effects, bool(is_normal_attack), att_ctx=att_hits_ctx)
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
    board = {**(board or {}), "base_hits": hits_pre}
    # (2) GetStuckIn = behaviour d'exec chance-gate (`AddBonusHitsToCurrentHitGroupBehaviour IdunBattle.Entities.Behaviours.AddBonusHitsToCurrentHitGroupBehaviour$$Execute`) :
    # DETERMINISTE en prediction (fold ICI), chance-roll a l'EXECUTION en combat (porte #62c dans
    # `_run_hits`, PAS dans cette formule -> gate False). Seul GetStuckInTrait override `as_attacker_bonus_
    # hits` -> gater `attacker_bonus_hits` ne perd que GetStuckIn cote formule (cf. entete BITE 2).
    bonus_hits = attacker_bonus_hits(trait_objects, board) if include_bonus_hit_behaviours else 0
    hits = hits_pre + bonus_hits
    # AURA COUPS côté ATTAQUANT (AstartesBanner IdunBattle.Entities.Effects.Loki.AstartesBanner_AdditionalHitsEffect$$CreateAdditionalHits : +extraHits mêlée si un allié porteur est dans
    # le rayon 2) — SYMÉTRIQUE de l'aura défenseur. ctx att-centrique dérivé de `board`.
    att_ctx = {"att_id": board.get("att_id"), "att_pos": board.get("attack_pos"),
               "att_team": (board.get("team_by_id") or {}).get(board.get("att_id")),
               "is_melee": is_melee}
    # (3) malus défenseur : LightCover -2 ranged / Parry -1 mêlée / MasterAnnihilator +1. Le gate
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
                                                  dist=_cam_dist)
               + aura_hits_malus_for_defense(aura_sources, board)
               + aura_hits_bonus_for_attack(aura_sources, att_ctx))
    return hits
