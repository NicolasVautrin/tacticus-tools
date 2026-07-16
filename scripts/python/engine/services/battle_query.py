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
import hexgeo


def are_tiles_adjacent(a_pos, t_pos, board=None):
    """`MovementUtil.AreTilesAdjacent @18109d740` / `AreUnitsInMelee` — ADJACENCE HEX (PAS Chebyshev),
    service PARTAGÉ prédiction↔runner. Le natif folde DEUX conditions dans la primitive :
    `return (|Δelev| < 2) & (A==B || ConnectivityComponent.IsNeighbour(A, B))` — l'adjacence hex ET une
    PORTE d'élévation (deux tuiles voisines séparées de ≥2 crans d'élévation ne sont PAS adjacentes ;
    élévation = `tileMeta.elevation`, lue via `FUN_180007ae0(...)→[+0x18]`). Le port réplique les deux.

    `board` fourni (runner `state.board`, ou `Scene.board`) → voisins NATIFS (`board.neighbours`,
    ground-truth capturé) + élévation par tuile (`by_id[tid]["elevation"]`, capteur boardGraph) ; sinon
    géométrie **evenq** (= le mode d'adjacence combat du runner, cf. `damage.py`), via `hexgeo.distance==1`
    (parité evenq validée vs boardGraph) SANS porte d'élévation (aucune info dispo → dégradation sûre =
    adjacence hex pure, comme le playbook `is_adjacent` sans `elev_by_pos`). Sur un board PLAT
    (Δelev=0<2 partout) la porte ne mord jamais → aucune régression ; elle ne discrimine que les boards
    à élévation. Renvoie `True`/`False`, ou `None` si une position est inconnue (→ ranged)."""
    if a_pos is None or t_pos is None:
        return None
    if board is not None:
        a_tile = board.id_at(a_pos[0], a_pos[1])
        t_tile = board.id_at(t_pos[0], t_pos[1])
        if a_tile is not None and t_tile is not None:
            neighbour = (a_tile == t_tile) or (t_tile in board.neighbours(a_tile))  # A==B || IsNeighbour
            if not neighbour:
                return False
            # AreTilesAdjacent @18109d740 : porte d'élévation |Δelev| < 2, foldée dans la primitive.
            ae = board.by_id.get(a_tile, {}).get("elevation")
            te = board.by_id.get(t_tile, {}).get("elevation")
            if ae is not None and te is not None:
                return abs(int(ae) - int(te)) < 2
            return True    # élévation non captée (board ancien) → dégradation sûre (adjacence hex pure)
    return hexgeo.distance(a_pos, t_pos) == 1


def _find_by_hits(cands: list, prefer_hits) -> dict:
    """Parmi les armes candidates (même type), celle dont `hits == prefer_hits` (capté), sinon la 1re."""
    if prefer_hits is not None:
        return next((w for w in cands if int(w.get("hits") or 0) == prefer_hits), cands[0])
    return cands[0]


def get_attack_weapon_for_default_normal_attack(visual_id, is_adjacent: bool, prefer_hits=None, dist=None):
    """`GetAttackWeaponForDefaultNormalAttack @18105ea60` (distance-aware). Renvoie
    `(weapon_dict|None, is_ranged)`. `is_adjacent` = cible en mêlée (`AreUnitsInMelee`/`AreTilesAdjacent`
    = **adjacence HEX** élévation-gatée, PAS Chebyshev) -> branche mêlée. Sinon branche ranged
    (`FindRangedWeapon @181059ae0`).

    PORTE DE PORTÉE ranged (#188) : `FindRangedWeapon @181059ae0` n'inclut une arme ranged QUE si
    `dist <= weapon.Range + rangeStatBonus` (`param_5 <= local_88[0] + iVar6`, iVar6 =
    `StatComponent.get_CurrentValue` du stat de portée `DAT_1831b8008` = **0 sur tous les units connus**,
    cf. sweep case-184 §gaps#2 : boundary exactement à Range). Si AUCUNE ranged en portée, le natif
    renvoie null -> le jeu retombe sur l'arme MÊLÉE (mesuré : mêlée à `dist > Range`). `dist` = distance
    HEX attaquant->cible (int) ; fourni -> porte appliquée, `None` -> comportement legacy (pas de porte).
    IMPACT NUL sur les tuiles d'attaque LÉGALES (cible toujours en portée de l'arme choisie) : la porte
    ne mord que les prédictions HORS-PORTÉE (que l'IA n'émet jamais) -> zéro régression. rangeStatBonus
    omis (=0) : à réintroduire si un unit à stat de portée positif apparaît (`DAT_1831b8008`)."""
    gu = GC.unit(visual_id or "") or {}
    weapons = gu.get("weapons") or []
    if not weapons:
        return None, False
    melee = [w for w in weapons if not w.get("Range")]
    ranged = [w for w in weapons if w.get("Range")]
    if is_adjacent and melee:          # AreUnitsInMelee -> FindMeleeWeapon
        cand = melee
    elif ranged:                       # FindRangedWeapon @181059ae0
        if dist is not None:           # porte de portée : ranged en portée, sinon fallback mêlée
            in_range = [w for w in ranged if dist <= int(w.get("Range") or 0)]
            cand = in_range or melee or ranged   # hors portée + mêlée dispo -> mêlée (null natif)
        else:                          # dist inconnu -> legacy (ranged dès non-adjacent)
            cand = ranged
    else:                              # fallback : mêlée si pas de ranged
        cand = melee or weapons
    w = _find_by_hits(cand, prefer_hits)
    return w, bool(w.get("Range"))


def select_weapon_pierce(ctx, is_adjacent, dist=None):
    """SÉLECTION D'ARME + PERÇAGE — service PARTAGÉ prédiction↔runner (foyer natif `BattleQuery`).
    `GetAttackWeaponForDefaultNormalAttack` (arme mêlée/ranged par adjacence HEX + porte de portée
    ranged `dist`, cf. #188) + `GetAttackPiercingDamageRatio @181030a20` (profil.PiercingRatio +
    ExtraPierce(26) + ExtraPierce{Melee21|Ranged22}). UN seul port : prédiction (`prediction._weapon_pierce`)
    ET combat (`damage_model.select_weapon_pierce`) l'appellent (un service natif appelé par N chemins =
    UNE fonction). `ctx` = UnitContext (les 2 en ont un). `dist` = distance HEX attaquant->cible (porte
    ranged ; `None` = legacy). Renvoie `(pierce, is_ranged, weapon_hits, profile_name)`."""
    w, is_ranged = get_attack_weapon_for_default_normal_attack(
        ctx.visual_id, is_adjacent, prefer_hits=ctx.normal_hits, dist=dist)
    if w is None:
        return 100, False, 1, None
    dp = GC.damage_profile(w.get("DamageProfile")) or {}
    prof_ratio = int(dp.get("PiercingRatio") or 0)
    dir_pierce = ctx.extra_pierce_ranged if is_ranged else ctx.extra_pierce_melee
    pierce = max(0, min(100, prof_ratio + ctx.extra_pierce + dir_pierce))
    return pierce, is_ranged, int(w.get("hits") or 1), w.get("DamageProfile")
