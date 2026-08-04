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

from ..entities.pathfinding.board import connectivity_neighbours
from .static_battle_rules import get_piercing_ratio


def are_tiles_adjacent(a_pos, t_pos, board=None):
    """`IdunBattle.Core.Services.MovementUtil$$AreTilesAdjacent` / `AreUnitsInMelee` — ADJACENCE HEX (PAS Chebyshev),
    service PARTAGÉ prédiction↔runner. Le natif folde DEUX conditions dans la primitive :
    `return (|Δelev| < 2) & (A==B || ConnectivityComponent.IsNeighbour(A, B))` — l'adjacence hex ET une
    PORTE d'élévation (deux tuiles voisines séparées de ≥2 crans d'élévation ne sont PAS adjacentes ;
    élévation = `tileMeta.elevation`, lue via `FUN_180007ae0(...)→[+0x18]`). Le port réplique les deux.

    `board` fourni (runner `state.board`, ou `Scene.board`) → le `ConnectivityComponent` BRUT
    (`connectivity_neighbours`, ce que lit littéralement `IsNeighbour`) + élévation par tuile
    (`by_id[tid]["elevation"]`, capteur boardGraph) ; sinon
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
            # `IsNeighbour` lit le `ConnectivityComponent` (`return this[+0x10].Contains(id)`),
            # canal BRUT -- et surtout PAS `board.neighbours()`, qui depend du `adjacency=` de
            # l'instance donc du MONTAGE de l'appelant (#448-r1-r1-r1-r1-r2-r1 ; c'est le meme
            # vice que `#381-r3` a ferme pour les pathfinders). Repli sur `board.neighbours()`
            # quand le canal n'est pas capte : le comportement anterieur, jamais un graphe vide.
            # MESURE (3 boards, 11718 paires) : en `native_sym` -- le mode de la PRODUCTION
            # (`playbook/scene.py`, le runner) -- le rebranchement change **0** verdict ; en
            # `evenq` il en corrige **4**, les aretes des deux `Bridge` de `C1_74` que
            # `TileComponent$$HasEdge` refuse et que la couronne hex inventait.
            conn = connectivity_neighbours(board, a_tile)
            ring = board.neighbours(a_tile) if conn is None else conn
            neighbour = (a_tile == t_tile) or (t_tile in ring)   # A==B || IsNeighbour
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


def is_melee_attack(ability_name, caster_position, target_position, elev_by_pos=None,
                    force_ranged_attack: bool = False, neigh_by_pos=None) -> bool:
    """`IdunBattle.Core.Services.BattleQuery$$IsMeleeAttack(ability, caster, casterPosition,
    target)` -- le slot **2** d'`IBattleQuery`, mirror 1:1 du decompile :

        if (!ability.HasValue) return false;
        switch (GetAbilityAttackRangeType(ability)) {   // 0 None, 1 Melee, 2 Ranged, 3 Normal
          case 0: return false;
          case 1: return true;
          case 2: return false;
          case 3: return !UnitExtensions.HasFlag(caster, 0x15)      // UnitFlag.ForceRangedAttack
                         && AreEntitiesAdjacent(casterPosition, target);
          default: throw new NotImplementedException();
        }

    FOYER UNIQUE de ce predicat : il est consomme par DEUX chemins natifs distincts, et les deux
    passent ici -- la gate `TriggeredAbilityPlaybook<T>$$IsMeleeAttack(case)` (cote DECISION, ex.
    `playbook/light_im_up.py`) et le predicat des effets d'attaquant
    (`IdunBattle.Entities.Triggers.IsMeleeAttackAbilityTrigger$$ShouldTrigger`, qui appelle le MEME
    slot 2 sur `AbilityEntities.Ability`). Un service natif appele par N chemins = UNE fonction.

    `ability_name` = le NOM gameconfig de l'ability EVALUEE (`case.AbilityType` cote playbook) ;
    `None` / nom inconnu -> `attackRangeType` absent -> branche `Normal(3)`, qui est CELLE QUE LE
    NATIF PREND pour les attaques normales concretes (leur id per-unite n'a pas d'entree nommee au
    gameconfig, cf. `light_im_up` residu `#419-r1-tr5-r3`).

    `caster_position` = la tuile d'ATTAQUE (`case.CasterPosition.MainTile`), pas la tuile reelle :
    c'est litteralement le 3e argument du natif. L'adjacence passe par le foyer
    `battle_query.are_entities_adjacent` (`AreEntitiesAdjacent`, court-circuit d'identite #433-r1),
    pas par `is_adjacent` (`IterateAdjacentTiles`, qui ne rend jamais la tuile source).

    `force_ranged_attack` = `UnitFlag.ForceRangedAttack` (21) ; le capteur
    `combatSnapshot.unitFlags` ne le publie pas (residu `#419-r1-tr5-r1`), donc l'appelant le laisse
    a `False` -- degradation PERMISSIVE-EN-PLUS, nommee.

    ⚠ HOMONYME A NE PAS CONFONDRE : `engine.entities.effects.base.is_melee_attack(is_ranged)` est un
    AUTRE artefact -- le gate TRI-ETAT (`is_ranged is False`) que les effets d'attaquant consomment
    une fois la nature du coup DEJA resolue. Celui-ci la RESOUT."""
    if caster_position is None or target_position is None:
        return False
    rt = ((GC.ability(ability_name) or {}) if ability_name else {}).get("attackRangeType")
    if rt == "Melee":                       # `AttackRangeType.Melee` (1)
        return True
    if rt == "Ranged":                      # `AttackRangeType.Ranged` (2)
        return False
    if rt == "None":                        # `AttackRangeType.None` (0)
        return False
    if force_ranged_attack:                 # `HasFlag(caster, 0x15)` -> pas de melee
        return False
    from .. import battle_query as _bq      # lazy : anti-cycle (le module playbook importe celui-ci)
    # `neigh_by_pos` = la liste STOCKEE (#433-r4-r1-r4-r2). Le substrat de `MovementUtil$$AreTilesAdjacent`
    # est le `ConnectivityComponent` BRUT (`IsNeighbour`) et non le champ `neighbours` gate ; lire
    # le second est NEANMOINS exact ici, parce que la porte est un terme SEPARE du meme predicat :
    # `(|dElev| < 2) & IsNeighbour` == `(|dElev| < 2) & (arete de C ^ gate)` == `C ^ gate`.
    return bool(_bq.are_entities_adjacent(tuple(caster_position), tuple(target_position),
                                          elev_by_pos, neigh_by_pos))


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


def find_melee_weapon(visual_id) -> dict | None:
    """`IdunBattle.Core.Services.BattleQuery$$FindMeleeWeapon(unit)` -- la surcharge a UN SEUL
    argument (celle que l'interface `IBattleQuery` expose au slot `0xb2`, identifie par son proxy
    `IdunBattle.Core.Services.RecordedSimulationRequestsBattleQuery.u003Cu003Ec__DisplayClass212_0$$u003CFindMeleeWeaponu003Eb__0`).
    Son corps est UN SEUL appel : `FindMeleeWeapon(unit, unitPosition: null, target: null)`, la
    surcharge a QUATRE arguments, dont le corps est le SYMETRIQUE EXACT de `find_ranged_weapon` :

        if (!EntityExtensions.IsUnit(unit)) return null;
        set = new OrderedSet<WeaponProfile>();
        foreach (w in unit.WeaponsComponent.Weapons)
            if (w.IsMelee) set.Add(w);                   // le filtre est INVERSE de FindRangedWeapon
        if (target != null) return SelectBestDamageWeapon(unit, unitPosition, target, set);
        return SelectMaxRangeWeapon(set);

    `target` etant NUL sur cette surcharge, la branche `SelectBestDamageWeapon` est MORTE ici : c'est
    toujours `SelectMaxRangeWeapon` qui tranche -- donc, parmi les armes de MELEE, celle de plus
    longue portee (`Range.GetValueOrDefault(0)`, `<=` -> la DERNIERE a egalite). Une unite dont
    toutes les armes de melee sont sans `Range` rend donc la DERNIERE de la liste.

    CONSOMMATEUR PORTE : `...TheLionsWrathPlaybook$$CalculateCustomUtility` (#27-r4), qui lit le
    `Hits` (`WeaponProfile+0x20`) de l'arme rendue pour la CIBLE -- jamais pour le caster.

    SUBSTRAT : identique a `find_ranged_weapon` (kit gameconfig par `visualId`) ; unite inconnue ou
    sans arme de melee -> `None`, qui mirroir le `null` natif (set vide -> `SelectMaxRangeWeapon`
    rend `null`)."""
    weapons = (GC.unit(visual_id or "") or {}).get("weapons") or []
    return select_max_range_weapon([w for w in weapons if weapon_is_melee(w)])


def get_attack_weapon_for_default_normal_attack_from_tiles(visual_id, is_adjacent: bool) -> dict | None:
    """`IdunBattle.Core.Services.BattleQuery$$GetAttackWeaponForDefaultNormalAttack(attacker,
    attackerTiles, **targetTiles**)` -- la surcharge que l'interface `IBattleQuery` expose au slot
    `0xb0`, et la SEULE que la regle dynamique de l'attaque normale consulte. Corps natif :

        t1 = attackerTiles[0]; t2 = targetTiles[0];              // deux `First()`
        if (MovementUtil.AreTilesAdjacent(t1, t2))
             return FindMeleeWeapon(attacker, unitPosition: null, target: null);
        else return FindRangedWeapon(attacker);

    `AreTilesAdjacent` y est la surcharge **LISTE** (`MovementUtil$$AreTilesAdjacent(IList, IList)`,
    xref LUE depuis ce corps) : un produit cartesien vrai des qu'UNE paire de tuiles est adjacente --
    donc l'EMPREINTE complete, exactement le predicat de `BattleQuery$$AreEntitiesAdjacent`, et non
    la seule tuile principale. C'est pourquoi l'adjacence est calculee par l'appelant et arrive ici
    en booleen : ce module n'a pas de board.

    ⚠ TROIS SURCHARGES, ET ELLES NE FONT PAS LA MEME CHOSE -- ne pas les confondre, le slot les
    separe :
      * `0xae` `(attacker, attackerTiles)` -- chaine de repli melee<->ranged ; c'est celle que
        `IdunBattle.View.FSM.VisualBattleQuery$$GetAttackWeaponForDefaultNormalAttack` delegue
        (lecture qui FIXE l'appariement slot<->arite) ;
      * `0xaf` `(attacker, attackerTiles, **target**)` -- resout `GetNormalAttackType` puis
        `BattleQuery$$GetAbilityAttackRangeType`, teste `UnitExtensions$$HasFlag(attacker, 0x15)`
        et `AreEntitiesAdjacent` ; NON PORTEE, aucun consommateur porte ne l'emprunte ;
      * `0xb0` `(attacker, attackerTiles, **targetTiles**)` -- CELLE-CI.
    L'appariement `0xaf`/`0xb0` est LU sur les deux surcharges de
    `IdunBattleLogic.Entities.Abilities.Active.Loki.ALoki_NormalAttackAbility$$FindAttackWeapon`,
    qui appellent respectivement le slot `0xaf` (parametre `target`) et le slot `0xb0` (parametre
    `targetTiles`) -- et c'est le slot `0xb0` que
    `ALoki_NormalAttackAbility$$GetDynamicInvalidTargetReason` invoque.

    SUBSTRAT : le kit gameconfig, via `find_melee_weapon` / `find_ranged_weapon` (meme borne, meme
    citation). `None` = le natif rendrait `null` -- ce que la regle dynamique traduit en REFUS."""
    return find_melee_weapon(visual_id) if is_adjacent else find_ranged_weapon(visual_id)


def weapon_hits(weapon: dict | None) -> int:
    """`WeaponProfile+0x20` = `Hits`, le nombre de coups du profil -- et `null -> 0`, la valeur que
    le natif garde quand `FindMeleeWeapon` ne rend rien (`iVar8` initialise a 0 et laisse tel quel
    dans `...TheLionsWrathPlaybook$$CalculateCustomUtility`).

    L'offset est etabli par DEUX lectures concordantes, jamais par le nom :
    `IdunBattle.Core.Services.BattleQuery$$u003CGetBestWeaponu003Eb__316_0` calcule
    `GetDamageProfile(w.<+0x10>).<+0x14> * w.<+0x20>` (degat par coup x nombre de coups), et
    `...$$SelectMaxRangeWeapon` / `IdunShared.Battle.WeaponProfile$$get_IsMelee` lisent tous deux
    `+0x24` comme le `Nullable<int> Range` -- donc `+0x20` n'est pas la portee.

    ⚠ Le defaut est `0`, PAS `1` : `get_attack_weapon_for_default_normal_attack` retombe sur `1`
    parce qu'une attaque porte au moins un coup, mais ici l'absence d'arme doit rendre un TERME NUL,
    et un `1` implicite vaudrait 30 points d'utilite offerts."""
    return int((weapon or {}).get("hits") or 0)


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
