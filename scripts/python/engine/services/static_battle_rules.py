"""Port FIDÈLE de `idun.Idun.Source.Shared.Battle.StaticBattleRules.StaticBattleRules.Damage`
(+ un membre de `StaticBattleRules.Effect`, cf. `is_tile_status_effect`).

Règles de combat STATIQUES (perçage/armure). 1:1 avec le natif (gqfc5mff6c), VA citées.

Constantes statiques du jeu (LUES au cctor natif, VA citées) :
  • W_LASCANNON_PIERCE_BONUS = 50 : bonus de perçage si le profil a `DamageTrait.LasCannon` (3, cf.
    entities/damage_trait.py) ET l'attaquant a `UnitTrait.HeavyWeapon` (1001) ou `UnitTrait.Emplacement`
    (1016) (cf. entities/traits/unit_trait.py). Valeur RÉSOLUE (#71) : `StaticBattleRules.DamageTrait$$.idun.Idun.Source.Shared.Battle.StaticBattleRules.StaticBattleRules.DamageTrait$$.cctor fait `**(int **)(DAT_183218fd8 + 0xb8) = 0x32` (= 50), écriture du static_field[0] de la classe
    `StaticBattleRules.DamageTrait` ; `idun.Idun.Source.Shared.Battle.StaticBattleRules.StaticBattleRules.Damage$$GetPiercingRatio` lit `iVar3 += **(int **)(cls + 0xb8)`
    (offset 0xb8 = Il2CppClass.static_fields). C'est un static field INTRINSÈQUE au natif (pas un paramètre)
    → `get_piercing_ratio` l'applique par défaut.
"""
from __future__ import annotations

import engine.services.fix64 as _fx   # module FRERE, pas `from . import` (#270-r4-r2)
from ..entities.effect_type import EffectType
from ..entities.traits.unit_trait import UnitTrait
# Feuille pure (`enum` seul) : `import engine.entities.triggered_ability_type` charge 3 modules
# `engine.*` (le paquet, son parent et lui-meme) -- MESURE, pas suppose. Ce module en charge
# deja 8 : l'ajouter n'allonge la cascade d'AUCUN module.
from ..entities.triggered_ability_type import TriggeredAbilityType

# ─── #485-r1-r1 : LA CONTRAINTE DE PLACEMENT A DISPARU -- MESUREE, PAS SUPPOSEE
#
# Ces deux imports vivaient plus bas, sous `TILE_STATUS_EFFECT_NAMES`, et c'etait FONCTIONNEL :
# `from ..entities.effect_type import EffectType` EN TETE initialisait le paquet `engine.entities`,
# qui tirait `effects/loki/hits.py`, qui re-importait CE module partiellement initialise ->
# `ImportError` reel. #270-r4-r2 avait trouve le placement qui l'evitait (la boucle ne lit qu'UN
# symbole, defini au-dessus des imports), et l'etage 4 de
# `tests/engine/test_270r1r1_container_enum_offline.py` gardait cette place.
#
# La vidange des barils de #485-r1-r1 a SUPPRIME la boucle, et la mesure le dit :
#     `import engine.entities`  ->  94 modules `engine.*` sur `origin/master`,  2 apres la vidange
#     `engine.entities.effects.loki.hits` charge : VRAI avant, FAUX apres
# L'`__init__` du paquet ne tire plus l'arbre des effets : il n'y a plus de boucle a eviter, donc
# plus de place a garder. L'etage 4 mesure DESORMAIS l'inverse (les imports sont en tete ET le
# module s'importe), et il se re-retournera si la cascade revenait.
#
# Ce qui garde ces valeurs contre un renumerotage du build est inchange : les membres sont ECRITS
# ici, sous cliquet `probe_313`.

# Bonus de perçage LasCannon — static_field[0] de `StaticBattleRules.DamageTrait` écrit à 0x32 par sa cctor
# idun.Idun.Source.Shared.Battle.StaticBattleRules.StaticBattleRules.DamageTrait$$.cctor (`**(int **)(cls + 0xb8) = 0x32`), lu par `idun.Idun.Source.Shared.Battle.StaticBattleRules.StaticBattleRules.Damage$$GetPiercingRatio`. VALEUR NATIVE = 50.
W_LASCANNON_PIERCE_BONUS = 50


# --- `StaticBattleRules.Effect` : le discriminant << STATUS de tuile >> ---------------------------
# `idun.Idun.Source.Shared.Battle.StaticBattleRules.StaticBattleRules.Effect$$IsTileStatusEffect
# = `OrderedSet.Contains(<set statique>, effectType)`, le set etant bati par
# `idun.Idun.Source.Shared.Battle.StaticBattleRules.StaticBattleRules.Effect$$.cctor (champ statique
# +0x28) avec EXACTEMENT ces 5 membres, lus 1:1 dans l'ordre des `OrderedSet.Add` du decompile.
#
# POURQUOI ICI et pas a cote de `default_amount_of_rounds` (l'autre membre porte de
# `StaticBattleRules.Effect`, dans `runner/operations/effects.py`) : ce predicat est consomme par
# `engine/entities/**` (le gate `TargetHasTileEffect` de LetTheGalaxyBurn) ET par `engine/runner/**`
# (`damage_model.tile_status_effects_by_pos`). Or `entities/` n'importe JAMAIS `runner/` (aucune
# inversion de couche dans l'arbre) ; `engine/services/` est la couche que les deux importent deja.
#
# ENJEU (#102) : une tuile porte des effets qui ne sont PAS des status (mesure live `C1_02` :
# `BlockEnteringUnits`=0 et `Thorns_DefenseReduction`=0xb sur les Swamp, `Melta_ExtraDmg`=0x511).
# `IdunBattle.Entities.TileExtensions$$HasTileStatusEffect` les EXCLUT via ce set. Tant que
# `load_state` ne seedait pas les effets de tuile, la liste offline ne contenait que ce que le runner
# avait pose lui-meme (Fire/Ice, tous des status) et l'absence de filtre etait INVISIBLE ; depuis le
# seed elle porte la VRAIE liste native, donc le filtre est OBLIGATOIRE.
# MEMES membres, par NOM : le canal PREDICTION (`tileMeta.tiles[].effects[].name` ->
# `Scene.tile_effects_by_pos`) ne transporte que des noms, pas des EffectType.
# `TILE_STATUS_EFFECT_NAMES` etait le SEUL symbole que l'ancienne boucle d'import lisait
# (`entities/effects/loki/hits.py`), ce qui imposait de le definir AVANT les deux imports d'enum.
# Cette boucle n'existe plus (encadre en tete de module) : sa place n'est plus contrainte.
TILE_STATUS_EFFECT_NAMES: frozenset = frozenset(
    {"Darkness", "Fire", "Ice", "Contaminated", "DespoiledGround"})

TILE_STATUS_EFFECT_TYPES: frozenset = frozenset({
    EffectType.Darkness, EffectType.Fire, EffectType.Ice,
    EffectType.Contaminated, EffectType.DespoiledGround})


def is_tile_status_effect(effect_type) -> bool:
    """`idun.Idun.Source.Shared.Battle.StaticBattleRules.StaticBattleRules.Effect$$IsTileStatusEffect
    -- cet EffectType compte-t-il comme un STATUS de tuile ? (cf. `TILE_STATUS_EFFECT_TYPES`)"""
    return effect_type is not None and int(effect_type) in TILE_STATUS_EFFECT_TYPES


# --- `StaticBattleRules` : les DEUX sets de l'ATTAQUE PARTIELLE ----------------------------------
# LUS PAR LES OCTETS DU PE (`probe_419r1tr9r4r1r2r1a_partial_attack_sets.py`), pas au decompile :
# le `.cctor` de `StaticBattleRules.Effect` fait 0xd120 octets et DEPASSE le budget de
# `mcp__ghidra__decompile_function` -- deux tranches (#1103, #1107) ont bute dessus. La voie qui
# marche lit l'ACCESSEUR (petit) pour obtenir le couple `(Il2CppClass*, offset du champ statique)`,
# puis delimite dans le `.cctor` le segment entre les DEUX stores au bloc de statiques qui
# l'encadrent : les immediats `mov dword ptr [rbp+N], IMM` poses juste avant chaque `Add` SONT les
# membres. Le probe re-derive ces deux ensembles a chaque run et rougit sur ecart.
#
#   `StaticBattleRules.TriggeredAbility$$IsPartialAttackAbility` -- statics +0x80, `HashSet.Contains`
#   `StaticBattleRules.Effect$$IsPartialAttack`                  -- statics +0x38, `HashSet.Contains`
#
# ⚠ LES DEUX SETS SONT DANS DEUX ENUMS DIFFERENTS, ET L'ORDINAL NE LES DISTINGUE PAS -- c'est
# exactement la confusion SILENCIEUSE que le nom rend visible : `1032` vaut
# `TriggeredAbilityType.DeathToTheFalseEmperor` ici et `EffectType.UnstoppableFerocity_OwnerEffect`
# ailleurs ; `1076` vaut `TriggeredAbilityType.HazeOfCorruption` ici et
# `EffectType.CondemnorStake_ExtraDmg` ailleurs ; `1077` vaut
# `EffectType.HazeOfCorruption_DamageTransfer` ici et `TriggeredAbilityType.Volatile` ailleurs.
PARTIAL_ATTACK_TRIGGERED_ABILITY_TYPES: frozenset = frozenset({
    TriggeredAbilityType.DeathToTheFalseEmperor,        # 0x408 = 1032
    TriggeredAbilityType.HazeOfCorruption,              # 0x434 = 1076
})

PARTIAL_ATTACK_EFFECT_TYPES: frozenset = frozenset({
    EffectType.HazeOfCorruption_DamageTransfer,         # 0x435 = 1077
})


def is_partial_attack_ability(triggered_ability_type) -> bool:
    """`idun.Idun.Source.Shared.Battle.StaticBattleRules.StaticBattleRules.TriggeredAbility$$IsPartialAttackAbility(abilityType)`
    = `HashSet.Contains(<set statique +0x80>, abilityType)`. Le parametre est un
    **`TriggeredAbilityType`** (signature LUE dans `frida/methods.tsv`)."""
    return (triggered_ability_type is not None
            and int(triggered_ability_type) in PARTIAL_ATTACK_TRIGGERED_ABILITY_TYPES)


def is_partial_attack(effect_type) -> bool:
    """`idun.Idun.Source.Shared.Battle.StaticBattleRules.StaticBattleRules.Effect$$IsPartialAttack(effectType)`
    = `HashSet.Contains(<set statique +0x38>, effectType)`. Le parametre est un **`EffectType`**
    (signature LUE dans `frida/methods.tsv`)."""
    return effect_type is not None and int(effect_type) in PARTIAL_ATTACK_EFFECT_TYPES


def ability_is_partial_attack(ability_or_effect) -> bool:
    """`Idun.Source.IdunBattle.Logic.Entities.Triggers.AbilityIsPartialAttackAbilityTrigger$$IsPartialAttack(abilityType)`
    -- le noeud DSL `IdunBattleLogic.Entities.DSLTriggers$$IsPartialAttackAbility`, mirror du corps
    natif LU par les octets (`Nullable<AbilityOrEffect>` en entree) :

        if (!a.HasValue)                 return false                          # `Nullable.get_HasValue`
        v = a.Value                                                            # `AbilityOrEffect`, 40 octets
        if (v.TriggeredAbility.HasValue) return TriggeredAbility.IsPartialAttackAbility(v.TriggeredAbility.Value)
        if (v.Effect.HasValue)           return Effect.IsPartialAttack(v.Effect.Value)
        return false                                                           # -> une ACTIVE rend TOUJOURS faux

    Les trois `Nullable` sont lus a `AbilityOrEffect+0x00` (`ActiveAbility`, JAMAIS consulte ici),
    `+0x08` (`TriggeredAbility`) et `+0x10` (`Effect`) -- ordre du corps natif, la branche
    `TriggeredAbility` PRIME sur `Effect`.

    ⚠ LE DISCRIMINANT DE TYPE N'EXISTE PAS DANS LE CANAL DU PORT (residu nomme). Le port thread
    l'`AbilityOrEffect` comme un ENTIER NU partout (`state.trigger_ability_type`,
    `state.triggering_ability`, `att_ctx["ability_type"]`, `NORMAL_ATTACK_KIND` -- qui melange deja
    un `TriggeredAbilityType` a des `ActiveAbilityType` dans le meme espace d'entiers). On ne peut
    donc pas savoir LEQUEL des trois `Nullable` est arme, et on teste l'UNION des deux ensembles.
    C'est une SUR-approximation, et son SENS est mesure : l'unique consommateur porte
    (`LegendaryCommander_ExtraHitsEffect$$IsValidAttack`) l'utilise sous un
    `!(TriggeringAbilityIsNormalAttack & IsPartialAttackAbility)`, donc rendre VRAI plus souvent
    RESTREINT -- jamais n'elargit. Les six noms concernes sont ecrits ci-dessus ; les trois qui
    seraient a tort classes `partial` sont `EffectType.UnstoppableFerocity_OwnerEffect` (1032),
    `EffectType.CondemnorStake_ExtraDmg` (1076) et `TriggeredAbilityType.Volatile` (1077).
    `ActiveAbilityType.MV71SniperDroneSquadAttack` (1076) ne compte pas : il est dans
    `REGULAR_ATTACK_ABILITY_TYPES`, donc le gate `!IsNormalAttack` en amont l'a deja ferme."""
    if ability_or_effect is None:                          # `Nullable.HasValue == false`
        return False
    t = int(ability_or_effect)
    return (t in PARTIAL_ATTACK_TRIGGERED_ABILITY_TYPES) or (t in PARTIAL_ATTACK_EFFECT_TYPES)


# --- `StaticBattleRules.Effect` : traits EXEMPTS d'un effet de tuile qui bloque le mouvement ------
# `idun.Idun.Source.Shared.Battle.StaticBattleRules.StaticBattleRules.Effect$$NotBlockingMovementOfTraits
# (lu VERBATIM au decompile) :
#     effectType in {0, 5, 0x11}  -> List{ 0, 0x405, 0x412 }     (Mounted, Vehicle, Unstoppable)
#     effectType == 0x3a          -> List{ 0x1d }                (NightVision, face Darkness)
#     sinon                       -> null
# Consommee par `IdunBattle.Entities.Pathfinding.WalkPathfinder$$GetTileBlockingReasons` : un effet de
# tuile ne compte comme raison de blocage que si l'unite qui se deplace n'a AUCUN de ces traits
# (predicat `Enumerable.Any(exemptTraits, t => HasTrait(unit, t))`).
BLOCK_ENTERING_UNITS_EFFECT_TYPE = EffectType.BlockEnteringUnits   # Swamp, BrokenIce...
# ⚠ Les elements sont des `EffectType` (le set) et des `UnitTrait` (les deux tuples) -- DEUX enums
# differents a deux lignes d'ecart, et l'ordinal ne les distinguait PAS : `0` vaut
# `EffectType.BlockEnteringUnits` d'un cote et `UnitTrait.Mounted` de l'autre. C'est exactement la
# confusion que le nom rend visible ; elle etait SILENCIEUSE en ordinal.
_MOVEMENT_BLOCKING_EFFECT_TYPES: frozenset = frozenset({
    EffectType.BlockEnteringUnits, EffectType.Fire, EffectType.Ice})
_MOVEMENT_EXEMPT_TRAIT_IDS: tuple = (UnitTrait.Mounted, UnitTrait.Vehicle, UnitTrait.Unstoppable)
_DARKNESS_EXEMPT_TRAIT_IDS: tuple = (UnitTrait.NightVision,)


def not_blocking_movement_of_traits(effect_type) -> tuple:
    """`StaticBattleRules.Effect$$NotBlockingMovementOfTraits(effectType)` — ids de trait pour
    lesquels CET effet de tuile ne bloque PAS le mouvement. Tuple VIDE = aucun porteur exempte
    (le natif rend `null` ; `Enumerable.Any` sur null leverait, donc le natif ne l'appelle que
    pour les types qu'il connait -- cote port un tuple vide = « personne n'est exempte »)."""
    if effect_type is None:
        return ()
    et = int(effect_type)
    if et in _MOVEMENT_BLOCKING_EFFECT_TYPES:
        return _MOVEMENT_EXEMPT_TRAIT_IDS
    # #484 : ce site portait le litteral `0x3a` parce que ce module NE POUVAIT PAS importer
    # `EffectType` (cycle mesure). `980173f9` (#270-r4-r2) a ferme ce cycle et pose l'import en
    # tete de ce fichier -- mais a laisse le litteral derriere, et la garde qui devait s'en
    # apercevoir (`test_270r4::etage5`) rougissait depuis, sans lecteur.
    if et == int(EffectType.Darkness):
        return _DARKNESS_EXEMPT_TRAIT_IDS
    return ()


def get_piercing_ratio(profile_piercing_ratio: int, profile_has_lascannon: bool,
                       attacker_has_heavy_weapon_or_emplacement: bool,
                       lascannon_bonus: int = W_LASCANNON_PIERCE_BONUS) -> int:
    """StaticBattleRules.Damage.GetPiercingRatio (idun.Idun.Source.Shared.Battle.StaticBattleRules.StaticBattleRules.Damage$$GetPiercingRatio).

        p = profile.PiercingDamageRatio                 # WeaponProfile/DamageProfile @+0x14
        if profile.HasTrait(DamageTrait.LasCannon) and attacker.HasTrait(HeavyWeapon|Emplacement): p += 50 (idun.Idun.Source.Shared.Battle.StaticBattleRules.StaticBattleRules.DamageTrait$$.cctor)
        return clamp(0, 100, p)
    `profile_has_lascannon` = `DamageProfile.HasTrait(DamageTrait.LasCannon)` (précalc appelant) ;
    `attacker_has_heavy_weapon_or_emplacement` = `HasTrait(attacker, UnitTrait.HeavyWeapon|Emplacement)` (précalc appelant).
    `lascannon_bonus` = W_LASCANNON_PIERCE_BONUS (50) par défaut — le natif le lit du static field, pas d'un param.
    """
    p = profile_piercing_ratio
    if profile_has_lascannon and attacker_has_heavy_weapon_or_emplacement:
        p += lascannon_bonus
    return max(0, min(100, p))


def get_damage_with_piercing(damage, pierce_pct: int, armor: int) -> "_fx.Fix64":
    """StaticBattleRules.Damage.GetDamageWithPiercing (idun.Idun.Source.Shared.Battle.StaticBattleRules.StaticBattleRules.Damage$$GetDamageWithPiercing) — LE cœur armure/perçage.
    ARITHMÉTIQUE Fix64 EXACTE (#30a) — l'ordre des ops natif est LOAD-BEARING :

        pierceFrac  = Fix64Div(FromInt(pierce), FromInt(100))   # div ARRONDI → ex. 0.15 devient
                                                                # 0.1499999999767… (raw 644245094)
        pierced     = Fix64Mul(damage, pierceFrac)              # mul TRONQUANT
        after_armor = damage − FromInt(armor)
        return max(Zero, after_armor, pierced)                  # le perçage est un PLANCHER

    ⚠ Le port float faisait `damage × pierce / 100.0` — ordre différent (mul avant div) ET float64 :
    sur 777s6, natif 1850×fix(0.15)=277.4999…→floor 277 vs float 277.5→round 278 (±1/coup, ×hits).
    ⚠ RENVOIE UN Fix64 (FRACTIONNAIRE, `.raw` exact) — le natif NE tronque PAS ici (aucun
    `op_Explicit`/`Round` en sortie) ; la matérialisation int UNIQUE se fait EN AVAL (prédiction ET
    combat : op_Explicit = floor, IdunBattle.Core.Services.DamagePrediction$$PredictAttackRaw+0x1ed7+/`IdunBattle.Core.Services.DamagePrediction$$CalculateAbilityDamage`). `damage` peut être
    fractionnaire (Fix64 des coups chaînés hit_mult>1) — passthrough exact via `.raw`."""
    d_raw = _fx.from_number(damage)
    pierce_frac = _fx.div(_fx.from_int(pierce_pct), _fx.from_int(100))
    pierced = _fx.mul(d_raw, pierce_frac)
    after_armor = d_raw - _fx.from_int(armor)
    # mirror natif : part de Zero (static +0x28), max avec after_armor puis avec pierced
    best = after_armor if after_armor > 0 else 0
    if pierced > best:
        best = pierced
    return _fx.Fix64(best)
