"""Abilities actives AdeptusMechanicus (faction `admec*`, namespace natif
`IdunBattleLogic.Entities.Abilities.Active.<X>Ability`).

Module DEDIE (convention 1 fichier/faction : necrons.py/sisterhood.py/votann.py/tyranids.py).
NB : d'autres AdMec (CordClaw 1122, DoctrinaImperatives 1118) vivent dans loki.py (namespace natif
`Abilities.Active.Loki.*`) — ce fichier porte les AdMec du namespace propre. RE ghidra gqfc5mff6c.

SentinelDirectives (id 1139, admecDestroyer « Sy-Gex ») — case-220 §6.17 [opus] direct.
"""
from __future__ import annotations

from typing import Optional, TYPE_CHECKING

from ...dsl.effects import ExecutionContext
from ...entities.behaviours import Foreach, op_add
from ...entities.formulas import (Const as _AmountConst, RoundsStarted, Sum,
                                  TotalRepairActionsAmount)
from ...entities.selectors import (AllUnits, Blocking, Caster, CasterTile, FixedTileIds, Friends,
                                   SortReverse, Sub, Subject, Target, TilesBehindInLine, Units,
                                   UnitsWithTrait)
from ...entities.active_ability_type import ActiveAbilityType
from ...entities.effect_type import EffectType
from ...entities.traits.unit_trait import UnitTrait
from ...entities.effects.magnitude import ability_var
from .base import ActiveAbility
from .targeting import RANGED_BOOL_FALSE, TargetingOptions, custom_range
from .targeting_rule import TargetingRule as TR
from .behaviours import (entities_from_state, AttackWithAttackDamage, AddEffect, InformWeapon)

if TYPE_CHECKING:
    from ..state import State

PINNED = int(EffectType.Pinned)   # 1065 (0x429) — UI « Suppressed » — stat-mod Movement (PinnedEffect porte)


def sentinel_directives_tree() -> "op_add":
    """Arbre de `SentinelDirectivesAbility$$IdunBattleLogic.Entities.Abilities.Active.SentinelDirectivesAbility$$ExecuteBehaviour` (id 1139, admecDestroyer
    « Sy-Gex » — MIRROR du DECOMPILE) :
        Execute( op_Addition( op_Addition(
            InformWeapon(GetDamageProfile=Physical),                                          # metadata arme
            AttackWithAttackDamage(caster@0x160, target@0x178, MinMaxDamage(minDmg 0xc/maxDmg 0xd),
                                   GetDamageProfile=Physical, nrOfHits=ConfigConst(0x2f)=1) ),  # attaque 1x
            AddEffect(0x429=Pinned, source=AbilityStateReference, target@0x178, dureeNode=0) ) )  # Pin cible

    Port : `op_add( op_add( InformWeapon("Physical"), AttackWithAttackDamage(Target(),"SentinelDirectives",
    "Physical",ranged) ), AddEffect(PINNED,"Pinned",Target(),None) )` — plain `Execute` (le decompile passe
    l'`op_Addition` DIRECTEMENT a `AActiveAbility.Execute`, aucun `AtomicGroup` autour ; == SpiritLeech/
    CordClaw, contraste ArmoriumCherub/BringerOfDespair `ExecuteAtomic`). Details RE :

    - `MinMaxDamage(param_1, &entities, 0, 0)` = bornes `minDmg`(0xc)/`maxDmg`(0xd)[active_ability_level]
      brutes de la config (AUCUN `GetAttackDamage` surcharge -> pas de `damage_override`, contraste
      SpiritLeech). minDmg/maxDmg sont dans `variablesAffectedByRarityBonus` -> scales par
      `AbilityVariablesMultiplier` (via `ability_var` dans `ability_attack_params`).
    - Profil `GetDamageProfile(config, 0)` = `Physical` (`constants.damageProfile`="Physical", PiercingRatio 1).
      `attackRangeType`=Ranged (range 3) -> `is_melee=False`.
    - `nrOfHits` = `ConfigConst(config, 0x2f)` = `GetNumberConstant(0x2f)` = 1 (`constants.nrOfHits`="1",
      verifie gameconfig). La feuille lit `nrOfHits` (hits_key defaut) via `ability_attack_params`.
    - **native_factory = "attack"** (defaut) : le decompile appelle `DSLFactory.AttackWithAttackDamage`
      (famille attack, VERIFIE par la CALLEE de IdunBattleLogic.Entities.Abilities.Active.SentinelDirectivesAbility$$ExecuteBehaviour = symbole `DSLFactory$$AttackWithAttackDamage`,
      JAMAIS `AttackWithAbilityDamage`, contraste SpiritLeech "ability" ; tip #2). Attaque MONO-COUP (1x) ->
      non concernee par le desync per-hit de toute facon (le flag est correct par XREF ET no-op ici).
    - `InformWeapon` = `op_Addition` volet GAUCHE (execute EN PREMIER) : canal weapon-inform
      (`ActivateEffectBehaviour`, metadata) COMBAT-INERTE (0 RNG, 0 mutation PV/stat) -> n'altere PAS l'ordre
      `state.rng` de l'attaque : bit-exact BY CONSTRUCTION. (== FlailSwing, mais FlailSwing utilisait
      `op_BitwiseAnd` ; ici le natif utilise `op_Addition` — memes observables pour des noeuds PURS,
      l'operateur porte mirror le natif.)
    - `AddEffect(0x429=1065 Pinned, source=AbilityStateReference(=caster), target@0x178, dureeNode=0)` :
      pose Pinned/« Suppressed » sur la cible, source=caster (la feuille assigne implicitement
      `entities.caster`), duree DEFAUT (`DefaultAmountOfRounds`, mirror de l'arg natif `0` SANS
      `TurnsFromRounds` — == Pinned de CrushingClaws/SpiritLeech). Effet PORTE+valide live
      (`PinnedEffect`, status.py). Le Pin s'applique APRES l'attaque (ordre `op_add` gauche->droite) ->
      il n'affecte pas le degat DEJA inflige.

    Deterministe hors le tirage per-coup de l'attaque -> memes Operations/args/`state.rng` qu'un imperatif
    attaque->pin : bit-exact BY CONSTRUCTION. « Ne finit pas le tour, peut entrer en Overwatch »
    (`SetsEndTurnFlags`=False / `SetsActiveAbilityUsedFlag`=False) = deja porte GENERIQUEMENT (1139 dans
    `NO_END_TURN_ABILITY_TYPES` + `NO_ABILITY_USED_FLAG_ABILITY_TYPES`, base.py ; queue `_add_flags_after_
    execution` du handler)."""
    tgt = Target()
    attack = AttackWithAttackDamage(tgt, "SentinelDirectives", "Physical", is_melee=False)  # 1x Physical ranged
    pin = AddEffect(PINNED, "Pinned", tgt, None)                                            # AddEffect(0x429), duree DEFAUT
    return op_add(op_add(InformWeapon("Physical"), attack), pin)                            # ((Inform + Attack) + Pin)


class SentinelDirectivesAbility(ActiveAbility):
    """`SentinelDirectivesAbility$$IdunBattleLogic.Entities.Abilities.Active.SentinelDirectivesAbility$$ExecuteBehaviour` (id 1139, admecDestroyer « Sy-Gex »,
    AdeptusMechanicus) — MIRROR du DECOMPILE, arbre DSL (`sentinel_directives_tree`) :
        Execute( op_Addition( op_Addition(
            InformWeapon(Physical),                                                            # metadata arme
            AttackWithAttackDamage(caster, target, MinMaxDamage, Physical, nrOfHits=1) ),      # attaque 1x
            AddEffect(0x429=1065 Pinned, source=caster, target, dureeNode=0) ) )               # Pin « Suppressed »

    Attaque RANGED MONO-CIBLE : 1 coup Physical (range 3, PiercingRatio 1) sur la cible du message, PUIS
    pose Pinned/« Suppressed » sur cette cible. Quasi-clone de SpiritLeech (1104) MOINS le degat conditionnel
    (`GetAttackDamage`) et le lifesteal (`Heal`) : ici degat generique `MinMaxDamage` sans surcharge, PAS de
    heal. La feuille `AttackWithAttackDamage` (native_factory="attack", VERIFIE par XREF de IdunBattleLogic.Entities.Abilities.Active.SentinelDirectivesAbility$$ExecuteBehaviour) emet
    la MEME Operation que l'attaque generique -> bit-exact BY CONSTRUCTION (memes bornes/hits/profil/state.rng).

    « Using Sentinel Directives does not end Sy-Gex's turn » (i2) = turn-flow : `SetsEndTurnFlags`=False +
    `SetsActiveAbilityUsedFlag`=False -> deja porte GENERIQUEMENT (1139 dans les frozensets de base.py, queue
    `AbilityHandler._add_flags_after_execution`). Aucun override bespoke necessaire ici."""
    __slots__ = ()
    ABILITY_TYPE = int(ActiveAbilityType.SentinelDirectives)  # 1139
    ABILITY_ID = "SentinelDirectives"

    def execute_behaviour(self, state: "State", caster_id: int,
                          target_id: Optional[int]) -> Optional[dict]:
        if target_id is None:
            return None
        ectx = ExecutionContext(state=state, rng=state.rng)
        sentinel_directives_tree().execute(entities_from_state(state, caster_id, target_id), ectx)
        atk = next((p["attack"] for n, p in ectx.emitted if n == "AttackWithAttackDamage"), None)
        pinned = next((p.get("placed") for n, p in ectx.emitted if n == "AddEffect"), None)
        informed = next((p.get("profile") for n, p in ectx.emitted if n == "InformWeapon"), None)
        return {"ability": "SentinelDirectives", "caster": caster_id, "target": target_id,
                "attack": atk, "pinned_placed": pinned, "informed_weapon": informed, "dsl": True}


# ============ RadBombardment (1116, `admecDominus` -- Dominus, HERO AdeptusMechanicus) =============
#
# `IdunBattleLogic.Entities.Abilities.Active.Loki.RadBombardmentAbility$$ExecuteBehaviour`
# (MIRROR du DECOMPILE ; `AActiveAbility.Execute` PLAIN) :
#
#   tiles  = GetAffectedTiles()                                              # cf. ci-dessous
#   units  = Units(tiles, 0, 3)                                              # occupants des tuiles
#   dmg    = MinMaxDamage(this, entities)                                    # minDmg(0xc)/maxDmg(0xd)
#   prof   = DamageProfileFromConfig(config@0x60)                            # constants.damageProfile
#   hits   = Get( ArmoriumCherubAbility$$GetHits() = ConfigConst(0x2f) )     # nrOfHits (corps FOLDE)
#   attack = AttackWithAbilityDamage( caster@0x160, units, dmg, prof, hits,
#                                     AbilityOrEffect(this+0x10 = 0x45c = 1116) )
#   pin    = AddEffect( 0x429 = 1065 Pinned, stateRef, source = caster@0x160, units, <opts ZERO> )
#   contam = AddEffect( 0x4dc = 1244 Contaminated, stateRef, tiles )         # surcharge 4-ARGS
#   AActiveAbility.Execute( (attack op_Addition pin) op_Addition contam, entities )
#
# `IdunBattleLogic.Entities.Abilities.Active.Loki.RadBombardmentAbility$$GetAffectedTiles` (MIRROR) :
#   settings = new TilesBehindInLineSettings { +0x10 = 0, +0x11 = 1 }        # `*(short*)+0x10 = 0x100`
#   line = TilesBehindInLine( from = CasterTile@0x168, to = TargetTiles@0x190, settings,
#                             AffectedTileAmount() )
#   rev  = SortReverse(line)
#   return rev op_Subtraction Blocking(rev)
#
# `IdunBattleLogic.Entities.Abilities.Active.Loki.RadBombardmentAbility$$AffectedTileAmount` (MIRROR) :
#   Sum( Get(1),
#        RoundsStarted(caster@0x160),
#        TotalRepairActionsAmount( UnitsWithTrait( Friends(caster@0x160, AllUnits@0x80, 3),
#                                                  0xc = 12 Mechanic, 3 ) ) )
#
# L'i2 CONFIRME les trois termes : « The length of the line starts at 2 hexes and increases by 1 hex for
# each round that has passed and by 1 hex each time a friendly Mechanic restores Health of a unit. »
# (au round 1 : `Get(1) + RoundsStarted = 1 + 1 = 2`.)
#
# CAST TILE-TARGET : `.ctor` passe `TargetingRange.CustomRange(1)` -> la cible du message est une TUILE
# ADJACENTE au caster = l'AIM (la direction du tir). CONFIRME live (`abilityTargets` 1116 : `kind="tile"`,
# `fromHere` = les voisines libres du caster).
#
# FAMILLE **ABILITY** : `...RadBombardmentAbility$$ExecuteBehaviour+0x132` appelle
# `IdunBattleLogic.Entities.DSLFactory$$AttackWithAbilityDamage` (VERIFIE par `list_xrefs` ; ABSENT des
# xrefs des surcharges `AttackWithAttackDamage`) -> `native_factory="ability"` = 1 tirage/coup, pas de
# crit/block.
#
# ORDRE DES CIBLES -- pourquoi un `Foreach` et pas `multi=True`. `IdunBattle.Entities.Behaviours.
# AbilityDamageBehaviour$$Execute` (famille ABILITY) ENUMERE son selecteur TEL QUEL : aucun `OrderBy`,
# contrairement a `IdunBattle.Entities.Behaviours.AttackBehaviour$$Execute` (famille ATTACK) qui pose
# `targets.OrderBy(b__5_0)` des que `Count > 1`. Or la feuille portee `AttackWithAttackDamage(multi=True)`
# folde l'`OrderBy` de la famille ATTACK -- l'appliquer ici TRIERAIT par id une liste que le natif laisse
# dans l'ordre du selecteur (apres `SortReverse` : de la tuile la PLUS LOINTAINE vers l'aim), donc
# desyncherait le RNG des qu'au moins DEUX unites sont alignees. On preserve donc l'ordre avec
# `Foreach(units, AttackWithAttackDamage(Subject(), ..., multi=False))` : une attaque par element, dans
# l'ordre du selecteur = exactement ce que fait `AbilityDamageBehaviour$$Execute`. (Meme forme que
# `ThriceBlessedConflagrationAbility`, dont le natif a lui aussi un `Foreach`.)
#
# RESIDU NOMME : `AbilityDamageBehaviour$$Execute` tient un `OrderedSet` et passe a `ExecuteTarget` un
# flag « 1re occurrence de cette unite » (`Contains` AVANT `Add`) ; il ecarte aussi les cibles
# `!IsTargetable` et celles portant le trait `0x40e`. Inerte ici : `Units(tiles)` ne peut rendre deux
# fois la meme unite (une unite par tuile) sauf BigTarget (unite sur plusieurs tuiles) -- non modelise.

RAD_BOMBARDMENT_ID = "RadBombardment"
CONTAMINATED = int(EffectType.Contaminated)      # 0x4dc = 1244
TRAIT_MECHANIC = int(UnitTrait.Mechanic)         # 0xc = 12


def rad_bombardment_affected_tile_amount():
    """`IdunBattleLogic.Entities.Abilities.Active.Loki.RadBombardmentAbility$$AffectedTileAmount`
    (MIRROR 1:1) = `Sum( Get(1), RoundsStarted(caster@0x160),
    TotalRepairActionsAmount(UnitsWithTrait(Friends(caster@0x160, AllUnits@0x80, 3), Mechanic, 3)) )`.

    REDUCTION NOTEE : la factory native `IdunBattleLogic.Entities.DSLFactory$$Sum` a UNE seule classe
    de noeud a 5 termes (les surcharges ne different que par le nombre de termes passes, les autres a 0) ;
    le port n'a qu'un `Sum` BINAIRE -> `Sum(Sum(a, b), c)`. Somme d'entiers, associative : identique.

    `@0x80` est la source board-wide `AllUnits` (cf. `entities/selectors/geometry.py`, meme ancrage que
    `WaaaghAbility$$GetBuffBehaviour`). `TotalRepairActionsAmount` rend 0 offline (compteur non capte,
    RESIDU documente sur le noeud) -> la longueur vaut `1 + turnsStarted(caster)`, exactement l'i2 tant
    qu'aucun Mechanic ami n'a soigne."""
    mechanic_friends = UnitsWithTrait(Friends(AllUnits(), Caster()), TRAIT_MECHANIC)
    return Sum(Sum(_AmountConst(1), RoundsStarted(Caster())),
               TotalRepairActionsAmount(mechanic_friends))


def rad_bombardment_affected_tiles(aim_tile_id: int, n_tiles: int):
    """`IdunBattleLogic.Entities.Abilities.Active.Loki.RadBombardmentAbility$$GetAffectedTiles`
    (MIRROR 1:1) :

        line = TilesBehindInLine( from = CasterTile@0x168, to = TargetTiles@0x190,
                                  settings{+0x10 = 0, +0x11 = 1}, AffectedTileAmount() )
        rev  = SortReverse(line)
        return rev op_Subtraction Blocking(rev)

    - `settings` : le ctor natif ecrit `*(short*)(settings + 0x10) = 0x100` = **+0x10 (checkWalkable)
      a 0**, **+0x11 (updateReference) a 1** (little-endian) -> `check_walkable=False,
      update_reference=True`, MEME couple que
      `IdunBattleLogic.Entities.Abilities.Active.Loki.DeathOnTheWindAbility$$GetTilesInLine`
      (inventaire des call-sites : cf. la docstring de `TilesBehindInLine`). `check_walkable=False`
      DESARME aussi le gate d'ELEVATION (il vit dans la branche walkable d'
      `IdunBattle.Core.Services.TileUtil$$IsTileValidForList`) : la ligne traverse les denivelees.
    - `to` = la TUILE CIBLEE (l'aim) -> `FixedTileIds([aim])` (vehicule de collapse tile-domain : le
      cast est tile-target, l'`AbilityEntities` du runner n'a pas d'entite `Target()` pour une tuile).
    - `n_tiles` = `AffectedTileAmount()` deja evalue par la classe (le noeud VALEUR ne peut pas etre
      passe tel quel a `max_count`, qui l'evalue mais sur un `ctx` sans `get_stat` cote tuile) --
      l'arbre reste lisible via `rad_bombardment_affected_tile_amount()`.
    - `Blocking(rev)` retire les tuiles NON walkable de la ligne (murs) ; `op_Subtraction` en domaine
      TUILE (cf. `Sub._key`)."""
    line = TilesBehindInLine(CasterTile(), FixedTileIds([int(aim_tile_id)]), max_count=int(n_tiles),
                             check_walkable=False, update_reference=True)
    rev = SortReverse(line)
    return Sub(rev, Blocking(rev))


def rad_bombardment_tree(tiles_sel, profile: str):
    """Arbre de `IdunBattleLogic.Entities.Abilities.Active.Loki.RadBombardmentAbility$$ExecuteBehaviour`
    (MIRROR 1:1) :

        op_Addition( op_Addition( Foreach(Units(tiles), AttackWithAbilityDamage(...)),
                                  AddEffect(Pinned -> Units(tiles), source = caster) ),
                     AddEffect(Contaminated -> tiles) )

    - `Units(tiles)` = les occupants DEBOUT des tuiles de la ligne, dans l'ORDRE DES TUILES (le natif
      itere le selecteur de tuiles et resout l'occupant de chacune) -- AUCUN filtre d'equipe : la ligne
      touche aussi les ALLIES (friendly-fire), le natif ne wrappe pas dans `Enemies`.
    - l'ATTAQUE route `IdunBattleLogic.Entities.DSLFactory$$AttackWithAbilityDamage` (famille ABILITY,
      1 tirage/coup, pas de crit) -> `native_factory="ability"` ; `Foreach` preserve l'ordre du
      selecteur (cf. le bloc de commentaire).
    - `Pinned` : options natives ZERO -> duree `DefaultAmountOfRounds(0x429)` convertie DANS
      `AddEffectOperation` (`duration_rounds=None`) ; source = `caster@0x160` (defaut du port).
    - `Contaminated` : surcharge `AddEffect` **4-args** -> selecteur SOURCE natif NULL -> chaque TUILE
      est sa PROPRE source (`source_from_target=True`), duree DEFAUT (`DefaultAmountOfRounds(0x4dc)=2`).
    - ORDRE (`op_Addition`, gauche->droite) : attaques, PUIS Pinned, PUIS Contaminated."""
    units = Units(tiles_sel)
    attack = Foreach(units,
                     AttackWithAttackDamage(Subject(), RAD_BOMBARDMENT_ID, profile, is_melee=False,
                                            native_factory="ability",
                                            ability_type=int(ActiveAbilityType.RadBombardment)))
    pin = AddEffect(PINNED, EffectType.Pinned.name, units, duration_rounds=None)
    contam = AddEffect(CONTAMINATED, EffectType.Contaminated.name, tiles_sel,
                       duration_rounds=None, source_from_target=True)
    return op_add(op_add(attack, pin), contam)


class RadBombardmentAbility(ActiveAbility):
    """`IdunBattleLogic.Entities.Abilities.Active.Loki.RadBombardmentAbility$$ExecuteBehaviour`
    (id 1116, `admecDominus` -- Dominus, HERO AdeptusMechanicus) -- cf. le bloc de commentaire ci-dessus.

    Kit gameconfig 1116 : `damageProfile=Toxic`, `nrOfHits=1`, `minDmg`/`maxDmg`[level]
    (rarity-affected), `attackRangeType=Ranged`. PAS de `range` (la portee vient du `.ctor` :
    `TargetingRange.CustomRange(1)` = tuile ADJACENTE) ni de `nrOfTiles` (la longueur est CALCULEE par
    `AffectedTileAmount`).

    OBSERVABLE DU CAST (cible = une TUILE voisine du caster = l'AIM) : (1) une ligne droite de
    `1 + RoundsStarted(caster) + TotalRepairActions(amis Mechanic)` tuiles part de l'aim en s'eloignant
    du caster, tronquee a ses tuiles bloquantes ; (2) chaque unite (TOUTE equipe) sur ces tuiles prend
    `nrOfHits` coups Toxic, famille ABILITY ; (3) et `Pinned`/« Suppressed » (1065) ; (4) chaque tuile
    de la ligne prend `Contaminated` (1244).

    `target_id` = id de TUILE (l'aim). Turn-flags = defauts base (1116 absent des overrides).
    Retour : {attacks, tiles, n_tiles, pinned, contaminated, dsl}."""
    __slots__ = ()
    ABILITY_TYPE = int(ActiveAbilityType.RadBombardment)   # 1116
    ABILITY_ID = RAD_BOMBARDMENT_ID

    # GATE DE CIBLE (#115). `IdunBattleLogic.Entities.Abilities.Active.Loki.RadBombardmentAbility$$.ctor` :
    #     range = TargetingRange.CustomRange(1)
    #     TargetingOptions..ctor(&opts, 0, &range, 1, 0xa0000000042, 0, 0, 0)
    #     AActiveAbility..ctor(this, &opts, 2, 0)
    # La surcharge appelee est celle a 7 arguments (VERIFIEE par `list_xrefs` : le call-site pointe sur
    # l'overload « FLAGS DIRECTS », dont le decompile pose `*(options + 0x28) = param_5`) -- PAS
    # l'overload PRESET+flags (qui ferait `+0x28 = flags | preset.+0x28`). Le litteral EST donc le
    # masque effectif : **0xa0000000042**. Decomposition (`IdunBattle.Core.Services.TargetingRule`) :
    #     0x2            TargetMatchesDynamicRule -> consulte `GetDynamicInvalidTargetReason`, PORTE
    #                    ci-dessous (mirror du virtuel natif).
    #     0x40           TargetIsTile             -> cast TILE-TARGET (confirme live : `abilityTargets`
    #                    1116 rend `kind="tile"`). Regle NON portee par le filtre statique (domaine
    #                    TILE, cf. l'inventaire de `targeting.py`) -> inerte, et c'est deliberе.
    #     0x20000000000  AllowUntargetableTarget  -> INVERSE la regle `TargetIsTargetable` : ce n'est
    #                    pas un refus, c'est une permission (cf. la cascade de `targeting.py`).
    #     0x80000000000  AllowUnwalkableTargetTile -> permissif aussi (tuile non marchable acceptee) ;
    #                    aucune regle du domaine TILE n'est portee, donc inerte.
    # PORTEE (#241) : `range = TargetingRange.CustomRange(1)` (le ctor construit le
    # `TargetingRange` INLINE : `onlyAdjacent = False`, `overrideRange = 1`) et
    # `forceMeleeTarget = False`. La cible etant une TUILE, le port ne sait pas resoudre sa
    # position -> le gate de portee ne mord pas offline ; l'annotation reste exacte et
    # s'activera le jour ou les tuiles seront des entites du `State`.
    TARGETING_OPTIONS = TargetingOptions(rules=(
          TR.TargetMatchesDynamicRule
        | TR.TargetIsTile
        | TR.AllowUntargetableTarget
        | TR.AllowUnwalkableTargetTile
    ), range=custom_range(1), force_melee_target=RANGED_BOOL_FALSE)

    def get_dynamic_invalid_target_reason(self, state: "State", caster_id: int,
                                          target_id: Optional[int]) -> int:
        """`IdunBattleLogic.Entities.Abilities.Active.Loki.RadBombardmentAbility$$GetDynamicInvalidTargetReason`
        -- MIRROR du decompile :

            if (target == ListExtensions.FirstOrDefault(casterTiles))  return 1;
            <AbilityEntities{caster, casterTiles, target}>
            tiles = GetAffectedTiles().Select(entities);
            return Count(tiles) == 0 ? 2 : 0;

        = (1) on ne peut pas viser SA PROPRE tuile (l'aim doit designer une direction, pas le caster) ;
        (2) sinon le cast n'est legal que si la ligne calculee depuis CET aim n'est pas VIDE -- une
        ligne peut etre vide quand la 1re tuile est bloquante (`- Blocking`) ou hors plateau.
        `casterTiles.FirstOrDefault()` = la MainTile du caster (une unite mono-tuile n'en a qu'une ;
        pour un BigTarget le natif prend la PREMIERE -- reduction NOTEE, le port lit la MainTile).

        N'est consulte que sous le bit `TargetMatchesDynamicRule` (0x2), qui EST pose (cf.
        `TARGETING_OPTIONS`). Les codes rendus sont des `TargetingRule` bruts, comme dans le natif."""
        from ..components import PositionComponent
        board = state.board
        if board is None or target_id is None:
            return 0                       # pas de plateau -> aucun refus INVENTE (degradation permissive)
        ce = state.get_entity(caster_id)
        cpc = ce.get_component(PositionComponent) if ce is not None else None
        if cpc is None:
            return 0
        caster_tile = board.id_at(cpc.col, cpc.row)
        aim = int(target_id) if int(target_id) in board.by_id else None
        if aim is None:
            te = state.get_entity(target_id)
            tpc = te.get_component(PositionComponent) if te is not None else None
            aim = board.id_at(tpc.col, tpc.row) if tpc is not None else None
        if aim is None:
            return 0
        if aim == caster_tile:             # target == casterTiles.FirstOrDefault()
            return 1
        entities = entities_from_state(state, caster_id)
        n_tiles = int(rad_bombardment_affected_tile_amount().evaluate(entities))
        tiles = rad_bombardment_affected_tiles(aim, n_tiles).evaluate(entities)
        return 0 if tiles else 2

    def execute_behaviour(self, state: "State", caster_id: int,
                          target_id: Optional[int]) -> Optional[dict]:
        board = state.board
        if board is None or target_id is None:
            return None
        # `TargetTiles@0x190` : la cible du message est une TUILE (cast tile-target). On accepte aussi un
        # id d'UNITE (on prend alors sa MainTile) -- `target@0x190` designe une entite dont le natif lit
        # la MainTile partout ou il l'utilise en domaine tuile (meme convention que PlagueburstMortar).
        aim = int(target_id) if int(target_id) in board.by_id else None
        if aim is None:
            from ..components import PositionComponent
            te = state.get_entity(target_id)
            tpc = te.get_component(PositionComponent) if te is not None else None
            aim = board.id_at(tpc.col, tpc.row) if tpc is not None else None
        if aim is None:
            return None
        import gameconfig as GC
        profile = ((GC.ability(RAD_BOMBARDMENT_ID) or {}).get("constants") or {}).get(
            "damageProfile") or "Toxic"
        entities = entities_from_state(state, caster_id)
        # `AffectedTileAmount()` : noeud VALEUR evalue ICI (la feuille `TilesBehindInLine` prend un
        # `max_count` scalaire ; meme collapse que le `hits` d'Executioner).
        n_tiles = int(rad_bombardment_affected_tile_amount().evaluate(entities))
        tiles_sel = rad_bombardment_affected_tiles(aim, n_tiles)
        tiles = list(tiles_sel.evaluate(entities))          # diagnostic (le tree les re-resout)
        ectx = ExecutionContext(state=state, rng=state.rng)
        rad_bombardment_tree(tiles_sel, profile).execute(entities, ectx)
        attacks = [{"target": p.get("target"), "total": p.get("total"), "attack": p.get("attack")}
                   for n, p in ectx.emitted if n == "AttackWithAttackDamage"]
        posed = [{"target": p.get("target"), "effect": p.get("effect_type"),
                  "source": p.get("source"), "placed": p.get("placed")}
                 for n, p in ectx.emitted if n == "AddEffect"]
        return {"ability": RAD_BOMBARDMENT_ID, "caster": caster_id, "target": target_id,
                "aim": aim, "n_tiles": n_tiles, "tiles": tiles, "profile": profile,
                "attacks": attacks,
                "pinned": [p for p in posed if p["effect"] == PINNED],
                "contaminated": [p for p in posed if p["effect"] == CONTAMINATED], "dsl": True}
