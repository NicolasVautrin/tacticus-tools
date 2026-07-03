"""BattleQuery — sélection d'arme de l'attaque normale (`IdunBattle.Core.Services.BattleQuery`).

`GetAttackWeaponForDefaultNormalAttack` choisit l'arme DISTANCE-AWARE :
  - variante simple `@18105e9b0` : `if !AreTilesAdjacent(att, tgt) -> FindRangedWeapon else FindMeleeWeapon`.
  - variante complète `@18105ea60` : `rangeType = GetAbilityAttackRangeType @181059fe0` (1=Melee, 2=Ranged,
    3=Both, 0=défaut) ; si 1 -> melée ; si 3 ET !HasFlag(att, 0x15) ET AreUnitsInMelee @1810584d0 -> melée ;
    sinon ranged. `FindMeleeWeapon @181059380` / `FindRangedWeapon @181059730` avec fallback vers l'autre type.
Le `DamageProfile` de l'arme choisie est lu à `weapon+0x10` (perçage : `GetAttackPiercingDamageRatio @181030a20`).

⚠ NE PAS confondre avec `ObjectivesBattleQuery.GetAmountOfHitsRangedFirstOrMelee @180467bb0` : ranged-first
INCONDITIONNEL, chemin OBJECTIFS de bataille, HORS prédiction de dégât. C'était le bug de l'ancien
`NormalAttackAbility` (sélection ranged-first au lieu de distance-aware).

Port : critère distance-aware (adjacent -> mêlée sinon ranged), VALIDÉ par l'ancien PV `_normal_weapon_pierce`.
Raffinements natifs `rangeType==3 (mixte) + flag 0x15` = documentés, à valider sur une unité à armes mixtes.
"""
from __future__ import annotations

import gameconfig as GC


def _find_by_hits(cands: list, prefer_hits) -> dict:
    """Parmi les armes candidates (même type), celle dont `hits == prefer_hits` (capté), sinon la 1re."""
    if prefer_hits is not None:
        return next((w for w in cands if int(w.get("hits") or 0) == prefer_hits), cands[0])
    return cands[0]


def get_attack_weapon_for_default_normal_attack(visual_id, is_adjacent: bool, prefer_hits=None):
    """`GetAttackWeaponForDefaultNormalAttack` (distance-aware). Renvoie `(weapon_dict|None, is_ranged)`.
    `is_adjacent` = cible en mêlée (`AreUnitsInMelee`/`AreTilesAdjacent`, ~dist<=1). Fallback : ranged si
    dispo à distance (ou position inconnue), sinon mêlée/1re arme."""
    gu = GC.unit(visual_id or "") or {}
    weapons = gu.get("weapons") or []
    if not weapons:
        return None, False
    melee = [w for w in weapons if not w.get("Range")]
    ranged = [w for w in weapons if w.get("Range")]
    if is_adjacent and melee:          # FindMeleeWeapon
        cand = melee
    elif ranged:                       # FindRangedWeapon (à distance, ou position inconnue)
        cand = ranged
    else:                              # fallback : mêlée si pas de ranged
        cand = melee or weapons
    w = _find_by_hits(cand, prefer_hits)
    return w, bool(w.get("Range"))
