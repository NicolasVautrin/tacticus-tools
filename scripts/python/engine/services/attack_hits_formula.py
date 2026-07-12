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
  1. base = `GetDefaultAttackHits @181032520` (`weapon + ExtraHits(0x11) + (melee ? ExtraHitsMelee(0x17))`)
     + `Sigma effets` (EffectAdditionalHits, clamps Min/Max type LightCover), plancher Max(.,0)
     -> `services.damage_prediction.get_default_attack_hits` + `entities.effects.hits_bonus_from_effects`.
  2. + GetStuckIn : behaviour `IdunBattle.Entities.Behaviours.AddBonusHitsToCurrentHitGroupBehaviour.Execute
     @180f93410` (ajoute au hit-group PENDANT l'exec, gate `Maybe(GetBonusHitChance @180f83460)` = 30%/100%)
     -> `entities.traits.attacker_bonus_hits`. **Gate par `include_bonus_hit_behaviours`** (cf. ci-dessous).
  3. + malus de coups de la CIBLE : `IdunBattle.Operations.AdditionalHitsFromEffects.GetAdditionalHits
     FromEffects @180e59e50` (LightCover -2 ranged / Parry -1 melee) + aura BigTarget  -> `entities.effects`
     (`hits_malus_from_defender_effects` / `aura_hits_malus_for_defense`).

Fidelite GetStuckIn (2) -- divergence PREDICTION vs COMBAT (verdict validateur cluster, BITE 2) : le natif
applique GetStuckIn comme un behaviour SEPARE chance-gate PENDANT l'execution (pas dans la formule) :
  - PREDICTION (`DamagePrediction.GetAttackHits`) l'inclut de facon DETERMINISTE (la chance ne pilote que le
    roll d'exec, pas la prediction de degat de l'IA) -> `include_bonus_hit_behaviours=True` (fold correct,
    confirme live seed777 + validateur).
  - COMBAT (`AttackDamageOperation.GetAttackHits`) NE le fold PAS : le natif roll `Maybe(GetBonusHitChance)`
    (30%/100%) et insere le coup bonus par index de coup IMPAIR a l'EXECUTION -> `include_bonus_hit_behaviours
    =False`. Folder en dur sur-comptait (prouve live par le validateur : orksNob 1v1 chance=30 -> natif 3
    coups, port 4). Le port fidele du behaviour combat (roll RNG a la bonne position) est un TODO (#62c) ->
    tant qu'il n'existe pas, le combat OMET GetStuckIn (structurellement fidele : la formule native ne
    l'inclut pas), au lieu de sur-compter.
Le combat manquait aussi (3) LightCover/Parry/BigTarget (verdict #62a, toujours valide -- non chance-gate,
donc partage sans reserve avec la prediction).
"""
from __future__ import annotations

from ..entities.effects import (hits_bonus_from_effects, hits_malus_from_defender_effects,
                                 aura_hits_malus_for_defense, aura_hits_bonus_for_attack)
from ..entities.traits import attacker_bonus_hits
from .damage_prediction import get_default_attack_hits


def attack_hits_with_modifiers(*, weapon_hits: int, extra_hits: int, extra_hits_melee: int,
                               attacker_effects, trait_objects, target_effects, aura_sources,
                               board: dict, is_melee: bool | None, damage_profile: str | None,
                               include_bonus_hit_behaviours: bool = False,
                               defender_on_cover: bool | None = None) -> int:
    """`AttackHitsWithModifiersFormula.Calculate @180f0bf50` : nb de coups d'une attaque normale. `board` =
    {att_id, tgt_id, attack_pos, t_pos, tgt_team, is_melee, pos_by_id, team_by_id} (base_hits pose ici) ;
    `aura_sources` = [(owner_id, pos, team, effets)] des unites != cible. Ordre = base (APRES PowerTrip) ->
    +GetStuckIn/traits (SSI `include_bonus_hit_behaviours` : prediction=True, combat=False, cf. entete BITE 2)
    -> +malus defenseur/aura, plancher 1."""
    eff_hits = hits_bonus_from_effects(attacker_effects)
    # base = `GetDefaultAttackHits @181032520` : weapon + ExtraHits(0x11) + (melee ? ExtraHitsMelee(0x17)).
    # is_melee=None (contexte inconnu) -> False -> pas d'ExtraHitsMelee (conservateur, mêlée seule).
    base_default = get_default_attack_hits(int(weapon_hits), int(extra_hits), int(extra_hits_melee),
                                           bool(is_melee))
    hits_pre = max(1, base_default + eff_hits)   # base APRES PowerTrip, AVANT GetStuckIn
    board = {**(board or {}), "base_hits": hits_pre}
    # (2) GetStuckIn = behaviour d'exec chance-gate (`AddBonusHitsToCurrentHitGroupBehaviour @180f93410`) :
    # DETERMINISTE en prediction (fold), chance-roll en combat (non porte -> OMIS). Seul GetStuckInTrait
    # override `as_attacker_bonus_hits` -> gater `attacker_bonus_hits` ne perd que GetStuckIn (cf. entete BITE 2).
    bonus_hits = attacker_bonus_hits(trait_objects, board) if include_bonus_hit_behaviours else 0
    hits = hits_pre + bonus_hits
    # AURA COUPS côté ATTAQUANT (AstartesBanner @180f323b0 : +extraHits mêlée si un allié porteur est dans
    # le rayon 2) — SYMÉTRIQUE de l'aura défenseur. ctx att-centrique dérivé de `board`.
    att_ctx = {"att_id": board.get("att_id"), "att_pos": board.get("attack_pos"),
               "att_team": (board.get("team_by_id") or {}).get(board.get("att_id")),
               "is_melee": is_melee}
    # (3) malus défenseur : LightCover -2 ranged / Parry -1 mêlée / MasterAnnihilator +1. Le gate
    # compute-time `defender_on_cover` (A3, #113) empêche LightCover de sur-appliquer un effet périmé en
    # runner-sim (cible ayant quitté sa tuile de cover) ; None (prédiction) = applique-sur-présence.
    hits = max(1, hits
               + hits_malus_from_defender_effects(target_effects, is_melee, damage_profile,
                                                  defender_on_cover=defender_on_cover)
               + aura_hits_malus_for_defense(aura_sources, board)
               + aura_hits_bonus_for_attack(aura_sources, att_ctx))
    return hits
