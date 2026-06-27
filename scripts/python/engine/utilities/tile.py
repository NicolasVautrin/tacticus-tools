"""Tile(7) composite — les 29 leaf-utilities de tuile (membership LUE runtime, doc §13.8).

`Tile(7)` (composite scoré par `Weight[Tile=7]` dans `CalculateUtilityFromTilePrediction`) = SOMME de
29 feuilles. La plupart sont SITUATIONNELLES (terrain spécial / trait de l'unité / effet présent) → =0
sur une bataille basique plate. Chaque feuille = `f(tile, meta, ctx, wt) -> float`, portée depuis son
`*Utility.<EvaluateMovementInSteps>d__N.MoveNext` (ghidra gqfc5mff6c) + poids BC `Utilities.Default`.

⚠ DÉPENDANCE DONNÉE : beaucoup de feuilles consomment une METADATA PAR TUILE / PAR UNITÉ que
`aiMovableTiles` n'expose pas (col/row seulement). Chaque feuille lit deux dicts optionnels et rend 0
quand la donnée manque — c'est EXACTEMENT la dégradation native (la condition de gate ne tient pas) :

`meta` (PAR TUILE candidate) — clés consommées :
  elevation, elevation_max, elevation_min : int            (Elevation 8 — via tileMeta) [ACTIF]
  steppable : {is_enemy, is_decoy} | None                  (SteppableUnit 19)
  effects : [effect_name]                                  (TileEffects 9 — noms d'effets SUR la tuile)
  is_temporary : bool                                      (TemporaryTile 13 — via tileMeta) [ACTIF]
  is_territory : bool                                      (CapturePoint 24 — via tileMeta.isTerritory)
  occupant_is_powerup : bool                               (PowerUp 26)
  tile_effect_type_ids : [int]                             (Contaminated 1244 / MoltenForm 5,10 / DespoiledGround 1476)
  effect_target_ids : [int]                                (EnvEndBombardment 1359/1360)
  pending_summons : [{type_id:int, owner_is_enemy:bool}]   (TilePendingBlockableSummon 1094)
  door : {linked:bool, closed:bool}                        (SummonDislikeDoorOpening 29 / HeroLikeDoorOpening 30)
  hero_door_nearest_cost : int                             (HeroLikeDoorOpening 30 branche B)
  phantasm_friendly_adjacent / ghost_friendly_adjacent : bool      (Phantasm 60 / Echoes 58)
  attract_mechanicals_neighbor : bool                      (DoctrinaImperatives 57)
  decoy_gate : bool, decoy_friend_count : int              (DecoysAndMisdirection 64)
  ability_friend_counts : {ability_id:int -> count}        (KustomForceField 1102 / Defender 1155 / Savior 1120)
  movetowards_hexdist : {ability_id:int -> hexdist}        (BioMinefield 1315 / MasterOfTheTutelaries 1096)
  neighbor_effect_names : {adjacent|surrounding1|ranged2 -> [effect_name]}   (UnitEffects 10/11/12)

`ctx` (PAR UNITÉ/DÉCISION, constant sur toutes les tuiles d'une décision) — clés consommées :
  unit_traits : [int]                 (2 summon, 5, 13, 16 hero, 26, 1006, 1019, 2026 …)
  unit_triggered_abilities : [int]    (1120 SaviorProtocols, 1221 MoltenForm …)
  unit_faction : int                  (9 T'au-style, 15 GSC-style …)
  unit_has_ranged_weapon : bool ; unit_is_ai : bool ; player_door_mode : int ; contaminated_excluded : bool

Statut de portage (cf. docs/rl/playbook-engine.md §13.8/§13.14) :
- ACTIVES (metadata dispo) : Elevation(8), SteppableUnit(19), TileEffects(9, partiel), TemporaryTile(13).
- PORTÉES FIDÈLE mais DORMANTES (gate sur metadata non encore plombée → 0) : les 22 autres `*Utility`.
- NON portées comme simples leaves : RangedAdjacentEnemy(15)=0 dans Default ; TriggeredAbilities(2)/
  NonOwner(4)/UnitSpecificBehaviours(3) = dispatchers vers le moteur Playbook par-ability (séparé).
"""
from __future__ import annotations

from ..weights import Weights

# UtilityType des 29 feuilles de Tile(7) (ordre runtime). name = catégorie BC `Default.<name>`.
TILE_LEAF_IDS = [8, 13, 9, 10, 11, 12, 15, 19, 24, 2, 4, 3, 20, 21, 22, 14, 26, 57, 60, 58, 25, 23,
                 61, 62, 64, 28, 29, 30, 31]


def elevation(tile, meta: dict, ctx: dict, wt: Weights) -> float:
    """Elevation(8) FIDÈLE (`ElevationUtility.<d__8>.MoveNext` @1811019a0) :
        u = Multiplier × elev  (+ HighestElevation si elev == max parmi tuiles pertinentes)
                               (+ LowestElevation  si elev == min)
    BC : Multiplier=10, HighestElevation=10, LowestElevation=-5. `meta` requis (élévation tuile + max/min)."""
    if not meta or "elevation" not in meta:
        return 0.0
    elev = meta["elevation"]
    u = wt.sub("Elevation", "Multiplier") * elev
    if meta.get("elevation_max") is not None and elev == meta["elevation_max"]:
        u += wt.sub("Elevation", "HighestElevation")
    if meta.get("elevation_min") is not None and elev == meta["elevation_min"]:
        u += wt.sub("Elevation", "LowestElevation")
    return u


def steppable_unit(tile, meta: dict, ctx: dict, wt: Weights) -> float:
    """SteppableUnit(19) FIDÈLE (`SteppableUnitUtility.<d__10>.MoveNext` @1810f9850) : si une unité
    STEPPABLE (summon/decoy) est sur la tuile → poids selon ami/ennemi × summon/decoy.
    BC : EnemySteppableUnit=50, FriendlySteppableUnit=-50, FriendlyDecoy=-50, EnemyDecoy=1.
    (Les 2 abilities triggered 0x4d/0x72 = cas spéciaux non portés ; rares.) `meta.steppable` requis."""
    st = (meta or {}).get("steppable")
    if not st:
        return 0.0
    is_enemy = st.get("is_enemy")
    if st.get("is_decoy"):
        return wt.sub("SteppableUnit", "EnemyDecoy" if is_enemy else "FriendlyDecoy")
    return wt.sub("SteppableUnit", "EnemySteppableUnit" if is_enemy else "FriendlySteppableUnit")


def tile_effects(tile, meta: dict, ctx: dict, wt: Weights) -> float:
    """TileEffects(9) PARTIEL (`TileEffectsUtility.<d__1>.MoveNext` @1810fbe50) : somme des poids BC
    `Default.TileEffects.<EffectName>` pour chaque effet de statut présent SUR la tuile (le natif
    multiplie les status-effects par un facteur de durée ; non porté → poids brut). `meta.effects` requis.
    BC TileEffects : Shrub_BonusDefense 25, FirstAidHeal 20, Thorns_DefenseReduction -25, SpiderWeb -25,
    Fire -25, Ice -25, … (cf. wt.category('TileEffects'))."""
    effs = (meta or {}).get("effects") or []
    if not effs:
        return 0.0
    cat = wt.category("TileEffects")
    return float(sum(cat.get(e, 0) for e in effs if isinstance(cat.get(e), (int, float))))


# Pénalité constante (Fix64) appliquée aux tuiles temporaires — RE'd, PAS un poids BC.
TEMPORARY_TILE_PENALTY = -10000.0


def temporary_tile(tile, meta: dict, ctx: dict, wt: Weights) -> float:
    """TemporaryTile(13) FIDÈLE (`TemporaryTileUtility.<d__1>.MoveNext` @1810faed0) :
        u = 0 ; si la tuile candidate est TEMPORAIRE → u -= Fix64(10000)
    Le natif lit `tileData+0x2c` (flag IsTemporary) de la MainTile de l'unité (= tuile candidate) et
    soustrait la CONSTANTE 10000 (pas un poids BC). ⇒ l'IA évite fortement de finir sur une tuile
    temporaire (terrain créé par capacité : glace, blocage de summon…). `meta.is_temporary` requis
    (exposé par le RPC `tileMeta`, champ `isTemporary`)."""
    if (meta or {}).get("is_temporary"):
        return TEMPORARY_TILE_PENALTY
    return 0.0


# ---------------------------------------------------------------------------
# Leaves SITUATIONNELLES portées (RE fidèle ghidra gqfc5mff6c + poids BC réels du
# profil `Utilities.Default`). TOUTES DORMANTES tant que la metadata par-tuile/unité
# n'est pas plombée : chaque fonction lit le contrat `meta`/`ctx` (cf. docstring module)
# et rend 0 quand la donnée manque — c'est EXACTEMENT la dégradation native (la condition
# de gate ne tient pas). Chaque docstring cite l'adresse MoveNext + les ids de gate
# (effet/trait/ability, hex+déc) + la/les clé(s) de poids BC réelle(s). cf. §13.14.
# ---------------------------------------------------------------------------

def _has(ctx: dict, key: str, val: int) -> bool:
    """True si `ctx[key]` (itérable d'ids) contient `val`."""
    s = (ctx or {}).get(key)
    return bool(s) and val in set(s)


def _eff_ids(meta: dict, key: str) -> set:
    return set((meta or {}).get(key) or ())


def _unit_effects(meta: dict, wt: Weights, cat: str, zone: str) -> float:
    """AUnitEffectsUtility.MoveNext @1810fb260 : Σ sur les amis du voisinage `zone`, Σ sur leurs
    effets, poids[EffectType.ToString()] si la clé existe dans la catégorie BC `cat`. Voisinages :
    Adjacent=ring R1, Surrounding=R1, Ranged=R2 (minus self, amis seulement). meta.neighbor_effect_names."""
    names = ((meta or {}).get("neighbor_effect_names") or {}).get(zone) or []
    if not names:
        return 0.0
    c = wt.category(cat)
    return float(sum(c.get(n, 0) for n in names if isinstance(c.get(n), (int, float))))


def unit_effects_adjacent(tile, meta: dict, ctx: dict, wt: Weights) -> float:
    return _unit_effects(meta, wt, "UnitEffectsAdjacent", "adjacent")


def unit_effects_surrounding(tile, meta: dict, ctx: dict, wt: Weights) -> float:
    return _unit_effects(meta, wt, "UnitEffectsSurrounding", "surrounding1")


def unit_effects_ranged(tile, meta: dict, ctx: dict, wt: Weights) -> float:
    return _unit_effects(meta, wt, "UnitEffectsRanged", "ranged2")


def capture_point(tile, meta: dict, ctx: dict, wt: Weights) -> float:
    """CapturePoint(24) @1811000a0 : sur tuile TERRITOIRE (flag tile+0x2e) → poids selon flag unité.
    RE : flag = HasTrait(2 summon) || HasTrait(13). Mapping branch→clé déduit de la sémantique des
    2 seules clés BC : flag(summon) → summons_dislike_capture_points(-300) ; sinon
    heroes_on_capture_points(+300). (trait 13 non confirmé ; mapping DAT→clé non résolu côté binaire.)
    meta.is_territory + ctx.unit_traits."""
    if not (meta or {}).get("is_territory"):
        return 0.0
    flag = _has(ctx, "unit_traits", 2) or _has(ctx, "unit_traits", 13)
    key = "summons_dislike_capture_points" if flag else "heroes_on_capture_points"
    return wt.sub("CapturePoint", key)


def power_up(tile, meta: dict, ctx: dict, wt: Weights) -> float:
    """PowerUp(26) @1810fd130 : -300 si l'occupant de la tuile EstPowerUp ET flag(trait 2||13).
    meta.occupant_is_powerup + ctx.unit_traits."""
    if not (meta or {}).get("occupant_is_powerup"):
        return 0.0
    if not (_has(ctx, "unit_traits", 2) or _has(ctx, "unit_traits", 13)):
        return 0.0
    return wt.sub("PowerUp", "summons_dislike_tiles_with_powerups")


def contaminated(tile, meta: dict, ctx: dict, wt: Weights) -> float:
    """Contaminated(25) @181100670 : -25 si la tuile porte un effet type 1244 (0x4dc) ET l'unité
    n'est pas exclue (= n'est pas la source de la contamination). meta.tile_effect_type_ids +
    ctx.contaminated_excluded."""
    if 1244 not in _eff_ids(meta, "tile_effect_type_ids"):
        return 0.0
    if (ctx or {}).get("contaminated_excluded"):
        return 0.0
    return wt.sub("Contaminated", "AffectedUnit")


def molten_form(tile, meta: dict, ctx: dict, wt: Weights) -> float:
    """MoltenForm(23) @1810fd300 : si l'unité a la triggered ability 1221 (0x4c5) →
    +25 si la tuile a l'effet type 5 (ResistFireTiles) ; -25 si effet type 10 (AvoidHealingTiles).
    ctx.unit_triggered_abilities + meta.tile_effect_type_ids."""
    if not _has(ctx, "unit_triggered_abilities", 1221):
        return 0.0
    ids = _eff_ids(meta, "tile_effect_type_ids")
    u = 0.0
    if 5 in ids:
        u += wt.sub("MoltenForm", "MoltenForm_ResistFireTiles")
    if 10 in ids:
        u += wt.sub("MoltenForm", "MoltenForm_AvoidHealingTiles")
    return u


def tile_pending_blockable_summon(tile, meta: dict, ctx: dict, wt: Weights) -> float:
    """TilePendingBlockableSummon(14) @181100250 : Σ sur les summons en attente de type 1094 (0x446)
    sur la tuile : +25 si owner ENNEMI, -25 si AMI. meta.pending_summons=[{type_id,owner_is_enemy}]."""
    ps = (meta or {}).get("pending_summons") or []
    we = wt.sub("TilePendingBlockableSummon", "EnemySummon")
    wf = wt.sub("TilePendingBlockableSummon", "FriendlySummon")
    return float(sum((we if e.get("owner_is_enemy") else wf)
                     for e in ps if e.get("type_id") == 1094))


def env_end_bombardment(tile, meta: dict, ctx: dict, wt: Weights) -> float:
    """EnvEndBombardment(31) @1810fe4c0 : tuile ciblée par l'effet 1359 (0x54f) → -30 ; sinon par
    l'effet 1360 (0x550) → -60 (×2). meta.effect_target_ids."""
    ids = _eff_ids(meta, "effect_target_ids")
    w = wt.sub("EnvEndBombardment", "EnvEndBombardment_TileToAvoid")
    if 1359 in ids:
        return w
    if 1360 in ids:
        return w * 2
    return 0.0


def despoiled_ground(tile, meta: dict, ctx: dict, wt: Weights) -> float:
    """DespoiledGround(28) @181100ac0 : si la tuile porte un tile-effect type 1476 (0x5c4) →
    trait 2026 (0x7ea, Chaos) → ChaosAffectedUnit(-5) ; trait 26 (0x1a) ou 1006 (0x3ee)
    (Imperial/Xenos) → ImperialAndXenosAffectedUnit(-25). meta.tile_effect_type_ids + ctx.unit_traits.
    (mapping trait→clé déduit de la sémantique ; DAT→clé non résolu côté binaire.)"""
    if 1476 not in _eff_ids(meta, "tile_effect_type_ids"):
        return 0.0
    if _has(ctx, "unit_traits", 2026):
        return wt.sub("DespoiledGround", "ChaosAffectedUnit")
    if _has(ctx, "unit_traits", 26) or _has(ctx, "unit_traits", 1006):
        return wt.sub("DespoiledGround", "ImperialAndXenosAffectedUnit")
    return 0.0


def summon_dislike_door(tile, meta: dict, ctx: dict, wt: Weights) -> float:
    """SummonDislikeDoorOpening(29) @1810fce30 : -50 si l'unité est "affected" (AI-controlled OU
    human + trait 2 summon) ET la tuile candidate est une PORTE FERMÉE (tile→door link + door open-flag=0).
    meta.door={linked,closed} + ctx.unit_is_ai/unit_traits."""
    door = (meta or {}).get("door") or {}
    if not (door.get("linked") and door.get("closed")):
        return 0.0
    affected = bool((ctx or {}).get("unit_is_ai")) or _has(ctx, "unit_traits", 2)
    if not affected:
        return 0.0
    return wt.sub("SummonDislikeDoorOpening", "Dislike")


def hero_door(tile, meta: dict, ctx: dict, wt: Weights) -> float:
    """HeroLikeDoorOpening(30) @1810fe100 : UNIQUEMENT unité hero (trait 16 / 0x10). PAS de poids BC
    (constantes hardcodées). branche A (player flag==0) : -50 si la tuile candidate est une porte
    fermée (activation), sinon 0. branche B (player flag!=0) : (10 - cost)*10 où cost = min coût de
    CHEMIN depuis la tuile candidate vers la porte fermée la plus proche. ctx.player_door_mode +
    meta.door + meta.hero_door_nearest_cost."""
    if not _has(ctx, "unit_traits", 16):
        return 0.0
    if (ctx or {}).get("player_door_mode", 0) == 0:
        door = (meta or {}).get("door") or {}
        return -50.0 if (door.get("linked") and door.get("closed")) else 0.0
    cost = (meta or {}).get("hero_door_nearest_cost")
    if cost is None:
        return 0.0
    return (10 - cost) * 10.0


def phantasm_avoid_friendly(tile, meta: dict, ctx: dict, wt: Weights) -> float:
    """Phantasm_AvoidFriendlyPhantasm(60) @1810fb020 : -40 si la tuile candidate porte l'effet
    Phantasm 1279 (0x4ff) ET un phantasme AMI est adjacent. meta.phantasm_friendly_adjacent."""
    if not (meta or {}).get("phantasm_friendly_adjacent"):
        return 0.0
    return wt.sub("Phantasm_AvoidFriendlyPhantasm", "Phantasm_AvoidFriendlyPhantasm")


def echoes_avoid_ghost(tile, meta: dict, ctx: dict, wt: Weights) -> float:
    """EchoesFromTheWarp_FriendliesAvoidGhost(58) @1810e3750 : +10 si la tuile POSSÈDE (owner) l'effet
    ghost 1284 (0x504) ET le ghost ami est adjacent. meta.ghost_friendly_adjacent."""
    if not (meta or {}).get("ghost_friendly_adjacent"):
        return 0.0
    return wt.sub("EchoesFromTheWarp_FriendliesAvoidGhost", "GhostTile")


def attract_mechanicals(tile, meta: dict, ctx: dict, wt: Weights) -> float:
    """DoctrinaImperatives_AttractMechanicals(57) @1810e3af0 : +10 si l'unité a le trait 5 ET au moins
    un voisin (autour de la tuile) a l'active ability 1118 (0x45e) et n'est pas l'unité elle-même.
    ctx.unit_traits + meta.attract_mechanicals_neighbor."""
    if not _has(ctx, "unit_traits", 5):
        return 0.0
    if not (meta or {}).get("attract_mechanicals_neighbor"):
        return 0.0
    return wt.sub("DoctrinaImperatives_AttractMechanicals", "Marshal_AttractMechanicals")


def attract_to_decoys(tile, meta: dict, ctx: dict, wt: Weights) -> float:
    """DecoysAndMisdirection_AttractToDecoys(64) @1810e2ef0 : +75 PAR ami avec triggered ability 1304
    (0x518), gate : unité faction 15 (0xf) ET la tuile a une unité steppable (trait 27 / 0x1b) NON
    ennemie. ctx.unit_faction + meta.decoy_gate + meta.decoy_friend_count (PER-unit, sommé)."""
    if (ctx or {}).get("unit_faction") != 15:
        return 0.0
    if not (meta or {}).get("decoy_gate"):
        return 0.0
    n = (meta or {}).get("decoy_friend_count") or 0
    return n * wt.sub("DecoysAndMisdirection_AttractToDecoys",
                      "DecoysAndMisdirection_FriendlyGSCLikeDecoys")


def _ability_count(meta: dict, ability_id: int) -> int:
    """count d'amis (dans le rayon propre à la leaf) ayant l'ability `ability_id`."""
    counts = (meta or {}).get("ability_friend_counts") or {}
    return int(counts.get(ability_id) or counts.get(str(ability_id)) or 0)


def kustom_force_field(tile, meta: dict, ctx: dict, wt: Weights) -> float:
    """KustomForceField(20) base ATriggeredAbilityUtility.d__3 @1810e4160 : +20 × count(amis ADJACENTS
    (R1) avec triggered ability 1102 (0x44e)). meta.ability_friend_counts[1102]."""
    return _ability_count(meta, 1102) * wt.sub("KustomForceField", "AdjacentFriendly")


def defender_greater_good(tile, meta: dict, ctx: dict, wt: Weights) -> float:
    """DefenderOfTheGreaterGood(21) @1810e4160 : +25 × count(amis R1, ou R2 si l'unité faction 9,
    avec ability 1155 (0x483)). Gate : l'unité a une arme à distance. ctx.unit_has_ranged_weapon +
    meta.ability_friend_counts[1155]."""
    if not (ctx or {}).get("unit_has_ranged_weapon"):
        return 0.0
    return _ability_count(meta, 1155) * wt.sub("DefenderOfTheGreaterGood", "PerUnitWithAbilityInRange")


def savior_protocols(tile, meta: dict, ctx: dict, wt: Weights) -> float:
    """SaviorProtocols(22) @1810e4160 : +20 × count(amis ADJACENTS R1 avec ability 1120 (0x460)).
    Gate : l'unité est faction 9 ET n'a pas elle-même l'ability 1120. ctx.unit_faction/
    unit_triggered_abilities + meta.ability_friend_counts[1120]."""
    if (ctx or {}).get("unit_faction") != 9 or _has(ctx, "unit_triggered_abilities", 1120):
        return 0.0
    return _ability_count(meta, 1120) * wt.sub("SaviorProtocols", "PerUnitWithAbilityInRange")


def _movetowards(meta: dict, wt: Weights, cat: str, ability_id: int,
                 trait_gate: set | None, ctx: dict) -> float:
    """MoveTowardsUnitUtility.MoveNext @1810f9b40 : score = poids("PerTileDistance") × hexdist(candidate,
    cible). cible = unité ayant l'ability/effet `ability_id` (ou le parent). distance = HEX (cube).
    meta.movetowards_hexdist[ability_id]."""
    if trait_gate is not None:
        if not (set((ctx or {}).get("unit_traits") or ()) & trait_gate):
            return 0.0
    dd = (meta or {}).get("movetowards_hexdist") or {}
    d = dd.get(ability_id)
    if d is None:
        d = dd.get(str(ability_id))
    if d is None:
        return 0.0
    return d * wt.sub(cat, "PerTileDistance")


def bio_minefield_movetowards(tile, meta: dict, ctx: dict, wt: Weights) -> float:
    """BioMinefield_MoveTowardsTarget(61) : -100 × hexdist(candidate, cible ability/effet 1315 (0x523)).
    Pas de gate trait."""
    return _movetowards(meta, wt, "BioMinefield_MoveTowardsTarget", 1315, None, ctx)


def master_tutelaries_movetowards(tile, meta: dict, ctx: dict, wt: Weights) -> float:
    """MasterOfTheTutelaries_MoveTowardsTarget(62) : -20 × hexdist(candidate, cible 1096 (0x448)).
    Gate trait : l'unité a 2026 (0x7ea) ou 1019 (0x3fb)."""
    return _movetowards(meta, wt, "MasterOfTheTutelaries_MoveTowardsTarget", 1096, {2026, 1019}, ctx)


# Registry : UtilityType -> (name, fn|None). fn=None => délégué/non-portable comme simple leaf.
TILE_LEAVES: dict[int, tuple] = {
    # --- ACTIVES (metadata dispo aujourd'hui) ---
    8:  ("Elevation", elevation),
    19: ("SteppableUnit", steppable_unit),
    9:  ("TileEffects", tile_effects),
    13: ("TemporaryTile", temporary_tile),   # RÉELLE (meta.is_temporary via tileMeta)
    # --- PORTÉES FIDÈLE, DORMANTES (gate sur metadata par-tuile/unité non encore plombée → 0) ---
    10: ("UnitEffectsAdjacent", unit_effects_adjacent),
    11: ("UnitEffectsSurrounding", unit_effects_surrounding),
    12: ("UnitEffectsRanged", unit_effects_ranged),
    24: ("CapturePoint", capture_point),
    26: ("PowerUp", power_up),
    25: ("Contaminated", contaminated),
    23: ("MoltenForm", molten_form),
    14: ("TilePendingBlockableSummon", tile_pending_blockable_summon),
    31: ("EnvEndBombardment", env_end_bombardment),
    28: ("DespoiledGround", despoiled_ground),
    29: ("SummonDislikeDoorOpening", summon_dislike_door),
    30: ("HeroLikeDoorOpening", hero_door),
    60: ("Phantasm_AvoidFriendlyPhantasm", phantasm_avoid_friendly),
    58: ("EchoesFromTheWarp_FriendliesAvoidGhost", echoes_avoid_ghost),
    57: ("DoctrinaImperatives_AttractMechanicals", attract_mechanicals),
    64: ("DecoysAndMisdirection_AttractToDecoys", attract_to_decoys),
    20: ("KustomForceField", kustom_force_field),
    21: ("DefenderOfTheGreaterGood", defender_greater_good),
    22: ("SaviorProtocols", savior_protocols),
    61: ("BioMinefield_MoveTowardsTarget", bio_minefield_movetowards),
    62: ("MasterOfTheTutelaries_MoveTowardsTarget", master_tutelaries_movetowards),
    # --- NON portées comme simples leaves ---
    15: ("RangedAdjacentEnemy", None),       # =0 dans le profil Default (BC HasAdjacentEnemy absent)
    # 2/3/4 = dispatchers vers le moteur Playbook PAR-ABILITY (LoadPlaybook/LoadPlaybookNonOwner ;
    # somme des playbooks par unit/ability/behaviour) — workstream Playbook séparé, pas un simple
    # terme de tuile. Restent 0 ici (cf. §13.14 + project_playbook_engine).
    2:  ("TriggeredAbilities", None),
    4:  ("TriggeredAbilitiesNonOwner", None),
    3:  ("UnitSpecificBehaviours", None),
}


def tile_composite(tile, meta: dict | None, ctx: dict, wt: Weights) -> float:
    """Composite Tile(7) = somme des 29 feuilles portées (les stubs rendent 0). `meta` = metadata
    par tuile (élévation/effets/steppable) ; absent ⇒ seules les feuilles sans donnée contribuent (≈0)."""
    m = meta or {}
    total = 0.0
    for uid in TILE_LEAF_IDS:
        fn = TILE_LEAVES.get(uid, (None, None))[1]
        if fn is not None:
            total += fn(tile, m, ctx, wt)
    return total
