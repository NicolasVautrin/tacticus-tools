"""`total_attack_hits` — nombre de coups d'une attaque NORMALE, service PARTAGE prediction+combat.

Mirror natif : le nb de coups exécuté = `BattleQuery.GetAttackHits @18105d8d0` (slot 0xb5, MEME noyau que
`AttackHitsWithModifiersFormula.Calculate @180f0bf50` / `DamagePrediction.GetAttackHits @18102f240`) =
`weapon_hits + ExtraHits(0x11) + Sigma effets (EffectAdditionalHits, avec clamps Min/Max type LightCover)`,
plancher `Max(.,0)` — PLUS le behaviour DECLENCHE `AddBonusHitsToCurrentHitGroup` (GetStuckIn @180f93410,
ajoute les coups bonus au hit-group pendant l'attaque) et les malus de coups de la CIBLE
(`hits_malus_from_defender_effects` : LightCover -2 ranged / Parry -1 melee) + auras
(`aura_hits_malus_for_defense` : BigTarget -1 ranged aux allies ring-1 du porteur).

UNE fonction pour les DEUX chemins (prediction `make_normal_attack_predictions` ET combat
`AttackDamageOperation.execute`) : un service natif = un port (structure offline == native, pas de fork).
Le combat le manquait (verdict RE cluster #62a) : il ne sommait que weapon+ExtraHits+effets, sans GetStuckIn
ni malus defenseur/aura -> nb de coups (donc degat) divergent de la prediction sur GetStuckIn/LightCover/BigTarget.
"""
from __future__ import annotations

from ..entities.effects import (hits_bonus_from_effects, hits_malus_from_defender_effects,
                                 aura_hits_malus_for_defense)
from ..entities.traits import attacker_bonus_hits


def total_attack_hits(*, weapon_hits: int, extra_hits: int, attacker_effects, trait_objects,
                      target_effects, aura_sources, board: dict,
                      is_melee: bool | None, damage_profile: str | None) -> int:
    """`hits` d'une attaque normale. `board` = {att_id, tgt_id, attack_pos, t_pos, tgt_team, is_melee,
    pos_by_id, team_by_id, faction_of} (base_hits posé ici). `aura_sources` = [(owner_id, pos, team,
    effets)] des unites != cible. Ordre = celui de la prediction validee : hits_pre (APRES PowerTrip) ->
    +GetStuckIn/traits -> +malus defenseur/aura, plancher 1."""
    eff_hits = hits_bonus_from_effects(attacker_effects)
    hits_pre = max(1, int(weapon_hits) + int(extra_hits) + eff_hits)   # base APRES PowerTrip, AVANT GetStuckIn
    board = {**(board or {}), "base_hits": hits_pre}
    hits = hits_pre + attacker_bonus_hits(trait_objects, board)
    hits = max(1, hits
               + hits_malus_from_defender_effects(target_effects, is_melee, damage_profile)
               + aura_hits_malus_for_defense(aura_sources, board))
    return hits
