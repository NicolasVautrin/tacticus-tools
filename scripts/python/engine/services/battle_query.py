"""BattleQuery — sélection d'arme de l'attaque normale (`IdunBattle.Core.Services.BattleQuery`).

`GetAttackWeaponForDefaultNormalAttack` choisit l'arme DISTANCE-AWARE :
  - variante simple `IdunBattle.Core.Services.BattleQuery$$GetAttackWeaponForDefaultNormalAttack` : `if !AreTilesAdjacent(att, tgt) -> FindRangedWeapon else FindMeleeWeapon`.
  - variante complète `IdunBattle.Core.Services.BattleQuery$$GetAttackWeaponForDefaultNormalAttack` : `rangeType = IdunBattle.Core.Services.BattleQuery$$GetAbilityAttackRangeType` (1=Melee, 2=Ranged,
    3=Both, 0=défaut) ; si 1 -> melée ; si 3 ET !HasFlag(att, 0x15) ET IdunBattle.Core.Services.BattleQuery$$AreUnitsInMelee -> melée ;
    sinon ranged. `IdunBattle.Core.Services.BattleQuery$$FindMeleeWeapon` / `IdunBattle.Core.Services.BattleQuery$$FindRangedWeapon` avec fallback vers l'autre type.
Le `DamageProfile` de l'arme choisie est lu à `weapon+0x10` (perçage : `IdunBattle.Core.Services.DamagePrediction$$GetAttackPiercingDamageRatio`).

⚠ NE PAS confondre avec `IdunBattle.ViewLogic.BattleSource.ObjectivesBattleQuery$$GetAmountOfHitsRangedFirstOrMelee` : ranged-first
INCONDITIONNEL, chemin OBJECTIFS de bataille, HORS prédiction de dégât. C'était le bug de l'ancien
`NormalAttackAbility` (sélection ranged-first au lieu de distance-aware).

Port : critère distance-aware (adjacent -> mêlée sinon ranged), VALIDÉ par l'ancien PV `_normal_weapon_pierce`.
Raffinements natifs `rangeType==3 (mixte) + flag 0x15` = documentés, à valider sur une unité à armes mixtes.
"""
from __future__ import annotations

import gameconfig as GC
import hexgeo

from .static_battle_rules import get_piercing_ratio


def are_tiles_adjacent(a_pos, t_pos, board=None):
    """`IdunBattle.Core.Services.MovementUtil$$AreTilesAdjacent` / `AreUnitsInMelee` — ADJACENCE HEX (PAS Chebyshev),
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
    à élévation. Renvoie `True`/`False`, ou `None` si une position est inconnue (→ ranged).

    ⚠ Le COURT-CIRCUIT D'IDENTITÉ (`A == B` → vrai sans consulter la connectivité) vaut dans les DEUX
    branches, et c'est la branche SANS board qui l'avait perdu : `hexgeo.distance(p, p)` vaut `0`,
    donc `== 1` rendait FAUX là où le natif rend VRAI. Le gate d'élévation ne le contredit jamais
    (`|Δelev| = 0 < 2` sur une tuile et elle-même), donc le natif rend VRAI **inconditionnellement**
    sur une paire identique — cf. `docs/rl/case-433-r1-identite-adjacence.md`."""
    if a_pos is None or t_pos is None:
        return None
    if (a_pos[0], a_pos[1]) == (t_pos[0], t_pos[1]):
        return True     # `tile1 == tile2` -> `b = 1`, et `|Delta elev| = 0 < 2` : VRAI des deux cotes
    if board is not None:
        a_tile = board.id_at(a_pos[0], a_pos[1])
        t_tile = board.id_at(t_pos[0], t_pos[1])
        if a_tile is not None and t_tile is not None:
            neighbour = (a_tile == t_tile) or (t_tile in board.neighbours(a_tile))  # A==B || IsNeighbour
            if not neighbour:
                return False
            # IdunBattle.Core.Services.MovementUtil$$AreTilesAdjacent : porte d'élévation |Δelev| < 2, foldée dans la primitive.
            ae = board.by_id.get(a_tile, {}).get("elevation")
            te = board.by_id.get(t_tile, {}).get("elevation")
            if ae is not None and te is not None:
                return abs(int(ae) - int(te)) < 2
            return True    # élévation non captée (board ancien) → dégradation sûre (adjacence hex pure)
    return hexgeo.distance(a_pos, t_pos) == 1


def are_entities_adjacent(feet_a, feet_b, board=None) -> bool:
    """`IdunBattle.Core.Services.BattleQuery$$AreEntitiesAdjacent(entity1, entity2)` -- la surcharge
    ENTITE/ENTITE, celle que le DSL invoque (slot 0x60 d'`IBattleQuery`) :

        tiles1 = EntityExtensions.GetTiles(entity1, state);
        tiles2 = EntityExtensions.GetTiles(entity2, state);
        return MovementUtil.AreTilesAdjacent(tiles1, tiles2);

    Elle compare donc les EMPREINTES COMPLETES, pas les main tiles. Et la surcharge LISTE de
    `IdunBattle.Core.Services.MovementUtil$$AreTilesAdjacent(IList, IList)` est un OU sur les paires
    (mirror du decompile) :

        foreach (t1 in tiles1) foreach (t2 in tiles2)
            if (AreTilesAdjacent(t1, t2)) return true;      // la surcharge SCALAIRE
        return false;                                       // enumeration epuisee

    Une liste VIDE rend donc FAUX (aucune paire evaluee) ; une liste NULLE fait LEVER cote natif --
    ici `None` est traite comme vide, le port n'ayant pas de domaine null distinct.

    UN SEUL LIEU boucle sur les empreintes dans tout le port, et c'est celui-ci :
      * `board` fourni -> DELEGUE a `engine.runner.abilities.targeting.are_entities_adjacent`, le
        foyer pose par #R30 (tuiles resolues par `board.id_at`, gate d'elevation et court-circuit
        d'identite par `targeting.are_tiles_adjacent`). Rien n'est reimplemente ici : le verdict
        de ciblage et le verdict DSL sortent litteralement de la meme fonction.
      * `board` ABSENT (contexte de FORMULE, scene de test) -> DEGRADATION NOMMEE : meme double
        boucle, primitive `are_tiles_adjacent(a, b, None)` ci-dessus = adjacence hex pure +
        court-circuit d'identite, SANS porte d'elevation (aucune elevation lisible). Sure sur un
        board plat, jamais un mirror.

    `feet_a`/`feet_b` = listes de `(col, row)` (mirror `EntityExtensions$$GetTiles`, cf.
    `dsl/base.py::_feet` cote DSL et `runner/components.get_unit_feet` cote ECS)."""
    fa = [f for f in (feet_a or ()) if f is not None]
    fb = [f for f in (feet_b or ()) if f is not None]
    if not fa or not fb:
        return False                       # `AreTilesAdjacent(IList, IList)` : boucle vide -> false
    if board is not None:
        from ..runner.abilities.targeting import are_entities_adjacent as _r30   # lazy : anti-cycle
        return bool(_r30(board, fa, fb))
    return any(are_tiles_adjacent(a, b, None) is True for a in fa for b in fb)


def _find_by_hits(cands: list, prefer_hits) -> dict:
    """Parmi les armes candidates (même type), celle dont `hits == prefer_hits` (capté), sinon la 1re."""
    if prefer_hits is not None:
        return next((w for w in cands if int(w.get("hits") or 0) == prefer_hits), cands[0])
    return cands[0]


def get_attack_weapon_for_default_normal_attack(visual_id, is_adjacent: bool, prefer_hits=None, dist=None):
    """`IdunBattle.Core.Services.BattleQuery$$GetAttackWeaponForDefaultNormalAttack` (distance-aware). Renvoie
    `(weapon_dict|None, is_ranged)`. `is_adjacent` = cible en mêlée (`AreUnitsInMelee`/`AreTilesAdjacent`
    = **adjacence HEX** élévation-gatée, PAS Chebyshev) -> branche mêlée. Sinon branche ranged
    (`IdunBattle.Core.Services.BattleQuery$$FindRangedWeapon`).

    PORTE DE PORTÉE ranged (#188) : `IdunBattle.Core.Services.BattleQuery$$FindRangedWeapon` n'inclut une arme ranged QUE si
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
    elif ranged:                       # IdunBattle.Core.Services.BattleQuery$$FindRangedWeapon
        if dist is not None:           # porte de portée : ranged en portée, sinon fallback mêlée
            in_range = [w for w in ranged if dist <= int(w.get("Range") or 0)]
            cand = in_range or melee or ranged   # hors portée + mêlée dispo -> mêlée (null natif)
        else:                          # dist inconnu -> legacy (ranged dès non-adjacent)
            cand = ranged
    else:                              # fallback : mêlée si pas de ranged
        cand = melee or weapons
    w = _find_by_hits(cand, prefer_hits)
    return w, bool(w.get("Range"))


def select_weapon_pierce(ctx, is_adjacent, dist=None, effect_bonus: int = 0):
    """SÉLECTION D'ARME + PERÇAGE — service PARTAGÉ prédiction↔runner (foyer natif `BattleQuery`).
    `GetAttackWeaponForDefaultNormalAttack` (arme mêlée/ranged par adjacence HEX + porte de portée
    ranged `dist`, cf. #188) + `IdunBattle.Core.Services.DamagePrediction$$GetAttackPiercingDamageRatio` (profil.PiercingRatio +
    ExtraPierce(26) + ExtraPierce{Melee21|Ranged22}). UN seul port : prédiction (`prediction._weapon_pierce`)
    ET combat (`damage_model.select_weapon_pierce`) l'appellent (un service natif appelé par N chemins =
    UNE fonction). `ctx` = UnitContext (les 2 en ont un). `dist` = distance HEX attaquant->cible (porte
    ranged ; `None` = legacy). Renvoie `(pierce, is_ranged, weapon_hits, profile_name)`.

    #71 : le BONUS LasCannon (+50) est appliqué ICI via `get_piercing_ratio` — mirror du natif
    `IdunBattle.Core.Services.DamagePrediction$$GetAttackPiercingDamageRatio` qui fait `base = GetPiercingRatio(profile, attackerTraits)`
    (bonus lascannon INCLUS) PUIS `+ ExtraPierce`. `GetAttackPiercingDamageRatio` n'a que des xrefs DATA
    (invoqué par delegate/slot) = service PARTAGÉ prédiction+combat -> le fix ici couvre LES DEUX faces.

    `effect_bonus` (case-117 phase 2) = Σ des `EffectBonus` de perçage des effets ACTIFS de l'attaquant
    (`IdunBattle.Entities.Effects.BaseEffect$$PiercingBonusForAttack`). C'est l'un des DEUX termes `Fix64`
    que le natif passe EN ARGUMENT à `GetAttackPiercingDamageRatio` (`param_6`/`param_7`, sommés DANS le
    `Max`/`Min` unique : `Min(100, Max(base>0, dirPierce + extraPierce + bonusB + bonusA + basePierce))`)
    -> il entre ici DANS la même somme, avant le clamp, jamais dans un second clamp. Défaut 0 =
    comportement historique. L'appelant COMBAT (attaque normale) le calcule après avoir résolu la nature
    du coup (`is_ranged`), que les gates d'effet consomment ; la PRÉDICTION ne le passe pas encore
    (résidu documenté : la face décision ignore ce canal, comme elle ignorait déjà GravitonRifle)."""
    w, is_ranged = get_attack_weapon_for_default_normal_attack(
        ctx.visual_id, is_adjacent, prefer_hits=ctx.normal_hits, dist=dist)
    if w is None:
        return 100, False, 1, None
    dp = GC.damage_profile(w.get("DamageProfile")) or {}
    prof_ratio = int(dp.get("PiercingRatio") or 0)
    # #71 : base pierce = GetPiercingRatio(profile, attackerTraits) = prof_ratio + 50 SI le profil porte
    # DamageTrait.LasCannon(3) ET l'attaquant UnitTrait.HeavyWeapon(1001)|Emplacement(1016). Les traits
    # gameconfig sont des NOMS de chaîne (DamageProfile.Traits / unit.traits) -> checks name-based.
    from ..entities.damage_trait import DamageTrait
    from ..entities.traits.unit_trait import UnitTrait
    profile_has_lascannon = DamageTrait.LasCannon.name in (dp.get("Traits") or ())
    att_traits = getattr(ctx, "traits", None) or ()
    attacker_hw_emp = (UnitTrait.HeavyWeapon.name in att_traits
                       or UnitTrait.Emplacement.name in att_traits)
    base_pierce = get_piercing_ratio(prof_ratio, profile_has_lascannon, attacker_hw_emp)
    dir_pierce = ctx.extra_pierce_ranged if is_ranged else ctx.extra_pierce_melee
    pierce = max(0, min(100, base_pierce + ctx.extra_pierce + dir_pierce + int(effect_bonus or 0)))
    return pierce, is_ranged, int(w.get("hits") or 1), w.get("DamageProfile")


def weapon_is_melee(weapon: dict | None) -> bool:
    """`IdunShared.Battle.WeaponProfile$$get_IsMelee` -- le predicat NATIF, et il n'est PAS
    « Range absent » :

        if (!this.Range.HasValue)  return true;      // champ `Nullable<int>` @ WeaponProfile+0x24
        return this.Range.Value < 2;                 // une portee de 1 est encore de la MELEE

    Le seuil `< 2` est LU (`local_res8[0] < 2` en sortie de `Nullable.get_Value`), pas deduit.
    Consequence : une arme a `Range == 1` est MELEE pour le natif, alors que le tri historique de
    `get_attack_weapon_for_default_normal_attack` (`bool(w.get("Range"))`) la range en DISTANCE.
    Les deux tris coexistent VOLONTAIREMENT ici : celui-la mirroir `FindMeleeWeapon`/`FindRangedWeapon`
    tels que la selection d'arme de l'attaque normale les appelle (residu nomme, non touche par cette
    tranche) ; celui-ci mirroir `get_IsMelee`, le seul que consultent `FindRangedWeapon` et
    `AttackWeaponRangeFormula$$Calculate`."""
    r = (weapon or {}).get("Range")
    if r is None:
        return True
    return int(r) < 2


def select_max_range_weapon(weapons: list) -> dict | None:
    """`IdunBattle.Core.Services.BattleQuery$$SelectMaxRangeWeapon(weapons)` -- mirror 1:1 :

        if (weapons.Count == 0) return null;
        if (weapons.Count == 1) return weapons[0];
        best = null; bestRange = 0;
        for (i = 0; i < weapons.Count; i++) {
            r = weapons[i].Range.GetValueOrDefault(0);   // `Nullable.GetValueOrDefault` @+0x24
            if (bestRange <= r) { best = weapons[i]; bestRange = r; }
        }
        return best;

    Deux details LUS qui ne se devinent pas : la comparaison est `<=` (a EGALITE de portee, c'est
    la DERNIERE arme de la liste qui gagne, pas la premiere), et `bestRange` part de `0` avec
    `GetValueOrDefault` -- une arme sans portee ne fait donc pas planter le balayage."""
    ws = list(weapons or [])
    if not ws:
        return None
    if len(ws) == 1:
        return ws[0]
    best, best_range = None, 0
    for w in ws:
        r = int((w or {}).get("Range") or 0)      # `Nullable<int>.GetValueOrDefault(0)`
        if best_range <= r:                        # `<=` : le DERNIER max gagne
            best, best_range = w, r
    return best


def find_ranged_weapon(visual_id) -> dict | None:
    """`IdunBattle.Core.Services.BattleQuery$$FindRangedWeapon(unit)` -- la surcharge a UN SEUL
    argument (celle que l'interface `IBattleQuery` expose au slot `0xb3`, identifie par son proxy
    `IdunBattle.Core.Services.RecordedSimulationRequestsBattleQuery.u003Cu003Ec__DisplayClass213_0$$u003CFindRangedWeaponu003Eb__0`,
    dont tout le corps est cet appel-la). Corps natif :

        if (!EntityExtensions.IsUnit(unit)) return null;
        set = new OrderedSet<WeaponProfile>();
        foreach (w in unit.WeaponsComponent.Weapons)
            if (!w.IsMelee) set.Add(w);
        return SelectMaxRangeWeapon(set);

    ⚠ A NE PAS confondre avec la surcharge a CINQ arguments
    `FindRangedWeapon(unit, unitPosition, target, distance)`, qui filtre en plus par
    `distance <= Range + rangeStatBonus` et peut basculer sur `SelectBestDamageWeapon`. Celle-ci
    n'a AUCUNE porte de distance et AUCUNE cible : elle rend l'arme de plus longue portee, point.

    SUBSTRAT : le natif itere le `WeaponsComponent` de l'ECS ; la face DECISION n'a que le kit
    gameconfig (`GC.unit(visualId).weapons`), exactement la source de
    `get_attack_weapon_for_default_normal_attack`. Unite inconnue / sans arme distance -> `None`,
    qui mirroir le `null` natif (set vide -> `SelectMaxRangeWeapon` rend `null`)."""
    weapons = (GC.unit(visual_id or "") or {}).get("weapons") or []
    return select_max_range_weapon([w for w in weapons if not weapon_is_melee(w)])
