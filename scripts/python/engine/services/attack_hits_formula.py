"""Port de `IdunBattle.Entities.Formulas.AttackHitsWithModifiersFormula` (`Calculate @180f0bf50`) — la
FORMULE (noeud DSL) qui calcule le NB DE COUPS d'une attaque AVEC ses modificateurs, PARTAGEE par tous les
contextes. Nativement, les facades `GetAttackHits` (slot d'interface 0xb5) delegent a cette formule :
  - `IdunBattle.Operations.AttackDamageOperation.GetAttackHits @180e613d0`  = COMBAT (runner) ;
  - `IdunBattle.Core.Services.DamagePrediction.GetAttackHits   @18102f240`  = PREDICTION (playbook) ;
  - `IdunBattle.Core.Services.BattleQuery.GetAttackHits        @18105d8d0`  (+ variantes Cached/Recorded/Query).

Les DEUX call-sites du port SONT ces facades : le combat (`AttackDamageOperation.execute`) et la prediction
(`make_normal_attack_predictions`) rassemblent leurs entrees (ECS vs Scene) puis appellent cette formule =>
MEME nb de coups des deux cotes. C'est FIDELE : le natif PARTAGE la formule (il ne la duplique pas entre
combat et prediction), donc le port la partage aussi (un seul point de calcul, deux facades).

Composition (chaque piece deleguee a SON port de classe natif) :
  1. base = `weapon_hits + ExtraHits(0x11) + Sigma effets` (EffectAdditionalHits, clamps Min/Max type
     LightCover), plancher Max(.,0)  -> `entities.effects.hits_bonus_from_effects`.
  2. + GetStuckIn : behaviour `IdunBattle.Entities.Behaviours.AddBonusHitsToCurrentHitGroupBehaviour.Execute
     @180f93410` (ajoute au hit-group PENDANT l'exec)  -> `entities.traits.attacker_bonus_hits`.
  3. + malus de coups de la CIBLE : `IdunBattle.Operations.AdditionalHitsFromEffects.GetAdditionalHits
     FromEffects @180e59e50` (LightCover -2 ranged / Parry -1 melee) + aura BigTarget  -> `entities.effects`
     (`hits_malus_from_defender_effects` / `aura_hits_malus_for_defense`).

Note fidelite : le natif applique GetStuckIn (2) comme un behaviour SEPARE pendant l'execution (pas dans la
formule elle-meme) ; le port le FOLD ici pour rendre le compte TOTAL en un point (simplification documentee,
pas une invention de structure). Verdict RE cluster #62a : le combat manquait (2)+(3) -> divergeait de la
prediction sur GetStuckIn / LightCover / BigTarget.
"""
from __future__ import annotations

from ..entities.effects import (hits_bonus_from_effects, hits_malus_from_defender_effects,
                                 aura_hits_malus_for_defense)
from ..entities.traits import attacker_bonus_hits


def attack_hits_with_modifiers(*, weapon_hits: int, extra_hits: int, attacker_effects, trait_objects,
                               target_effects, aura_sources, board: dict,
                               is_melee: bool | None, damage_profile: str | None) -> int:
    """`AttackHitsWithModifiersFormula.Calculate @180f0bf50` : nb de coups d'une attaque normale. `board` =
    {att_id, tgt_id, attack_pos, t_pos, tgt_team, is_melee, pos_by_id, team_by_id, faction_of} (base_hits
    pose ici) ; `aura_sources` = [(owner_id, pos, team, effets)] des unites != cible. Ordre = base (APRES
    PowerTrip) -> +GetStuckIn/traits -> +malus defenseur/aura, plancher 1."""
    eff_hits = hits_bonus_from_effects(attacker_effects)
    hits_pre = max(1, int(weapon_hits) + int(extra_hits) + eff_hits)   # base APRES PowerTrip, AVANT GetStuckIn
    board = {**(board or {}), "base_hits": hits_pre}
    hits = hits_pre + attacker_bonus_hits(trait_objects, board)
    hits = max(1, hits
               + hits_malus_from_defender_effects(target_effects, is_melee, damage_profile)
               + aura_hits_malus_for_defense(aura_sources, board))
    return hits
