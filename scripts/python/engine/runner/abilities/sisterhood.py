"""Abilities de la faction Sisterhood / Adepta Sororitas (prefixe `adept*`). RE ghidra gqfc5mff6c
(VA citees). Case-220 / docs/rl/case-220/sisterhood.md.

Org native = les abilities Sisterhood vivent dans le namespace partage `Abilities.Active.Loki.*`
(codename interne, cf. DarkAngels/darkangels.py) ; l'arbre SPECIFIQUE vit avec son ability. Module DEDIE
et ISOLE (rien de porte pour Sisterhood cote abilities avant ceci).

SanctorumMissile (`SanctorumMissileAbility$$ExecuteBehaviour @1812041d0`, id 1062, unite adeptMorvenn =
Morvenn Vahl) : missile RANGED (range 3, profil Blast) 2x sur la CIBLE + 1x sur les ADJACENTS de la cible
(hex de Morvenn EXCLU) + tuiles vides/steppables. Template splash 2-bandes (== Gauntlets/PlasmaCannon/
Fragstorm), meme plage `MinMaxDamage` partagee, seul le nb de coups differe par bande. FACTORY NATIVE =
`AttackWithAttackDamage @180de9fb0` (native_factory="attack", classe PAR XREFS, cf. ci-dessous).
"""
from __future__ import annotations

from typing import Optional, TYPE_CHECKING

from ...dsl.effects import ExecutionContext
from ...entities.behaviours import AtomicGroup, op_and, If
from ...entities.selectors import Target, TargetTile, Caster, AdjacentUnits, Sub, Unobscured, FixedTiles
from ...entities.triggers import Not, IsAlive, IsAdjacent, TriggerAnd
from ...entities.active_ability_type import ActiveAbilityType
from ...entities.stats import StatType
from ...entities.effects.magnitude import ability_var
from ..components import PositionComponent, UnitComponent, StatsComponent
from ..damage_model import select_weapon, select_weapon_pierce
from .base import ActiveAbility
from .behaviours import AttackWithAttackDamage, MoveUnit, entities_from_state

import hexgeo

if TYPE_CHECKING:
    from ..state import State


def sanctorum_missile_tree():
    """Arbre de `SanctorumMissileAbility.ExecuteBehaviour @1812041d0` (id 1062, adeptMorvenn — MIRROR du
    DECOMPILE) :
        ExecuteAtomic( op_BitwiseAnd(
            AttackWithAttackDamage(caster@0x160, target@0x178, MinMaxDamage(var0xc,var0xd), GetDamageProfile(0),
                                   hits=GetNumberConstant(0x2f)=nrOfHits),                         # [MAIN]
            AttackWithAttackDamage(caster@0x160, GetAdjacentDamageTargetsAll(),
                                   MinMaxDamage(MEME), GetDamageProfile(0)(MEME),
                                   hits=GetNumberConstant(0x32)=nrOfHits_2) ),                     # [SPLASH]
          0x56 )

    - **MAIN** = attaque sur la cible du message (`Target()`), `nrOfHits` coups (0x2f=2), plage `MinMaxDamage`
      (minDmg/maxDmg), profil `GetDamageProfile(config,0)`=Blast, RANGED (range 3 -> `is_melee=False`).
    - **SPLASH** = attaque MULTI-cible sur `GetAdjacentDamageTargetsAll()` (cf. sous), `nrOfHits_2` coups
      (0x32=1), MEME plage `MinMaxDamage` (cles par defaut, PARTAGEES main/splash), MEME profil Blast.
    - Config 1062 (gameconfig, LU) : nrOfHits=2, nrOfHits_2=1, damageProfile=Blast, range=3, attackRangeType=
      Ranged, plage minDmg/maxDmg unique.

    **SELECTEUR SPLASH `GetAdjacentDamageTargetsAll @1812044a0` (MIRROR du decompile)** :
        Unobscured( self@0x168,
            ( Units(AdjacentTiles(target@0x178), 1, 3) - caster@0x160 )    # [band UNIT]
            + EmptyOrHasSteppableUnit(AdjacentTiles(target@0x178)) )        # [band TILE]
    - band UNIT = `Units(AdjacentTiles(target))` (occupants DEBOUT des tuiles adjacentes a la cible, AUCUN
      filtre d'equipe = FRIENDLY-FIRE, == Stikkbomb `AdjacentUnits` brut) MOINS `caster` (l'hex de Morvenn) ->
      porte `Sub(AdjacentUnits(TargetTile()), Caster())`. `AdjacentUnits(TargetTile())` = `_within(units,
      target_pos, 1)` (exclut deja la cible dist 0) ; `Sub(., Caster())` retire Morvenn par id (BigTarget OK).
      Les flags `(1,3)` de `Units` = mode d'occupation main/steppable (raffinement inerte offline, cf. `Units`
      selectors.py). Le natif soustrait CASTER (0x160), PAS target (0x178) -> la cible n'est de toute facon pas
      adjacente a elle-meme.
    - band TILE = `EmptyOrHasSteppableUnitTilesSelector.Select @180ee83e0` (`TileExtensions.IsEmptyOrSteppable`)
      = tuiles adjacentes a la cible qui sont VIDES ou portent une unite STEPPABLE (scenery `Object`). NON
      PORTE (GAP flagge) : le leaf `AttackWithAttackDamage(multi=True)` resout un selecteur UNIT-domain
      (il filtre `u.get("id")`) ; ce band est TILE-domain et INERTE pour le degat-UNITE en duel (une tuile
      VIDE frappee = 0 degat unite ; aucune scenery Steppable dans un runner 1v1). CONFIRME par le FRERE
      `GetAdjacentDamageTargetsUnits @181204580 = Units(GetAdjacentDamageTargetsAll())` (variante units-only
      cote prediction @1811582c0) : `Units(All)` re-resout aux occupants DEBOUT -> les tuiles vides du band
      TILE disparaissent, il ne reste que les UNITES = exactement ce que mon port emet.
    - **Unobscured, observer `self@0x168`** : 0x168 est un slot d'entite DISTINCT de caster (0x160, utilise
      pour la soustraction) ET de target (0x178, utilise comme centre d'AdjacentTiles DANS LA MEME fonction)
      -> c'est le 3e role (self/owner), qui en cast ACTIF top-level == Morvenn == `Caster()`. Porte
      `Unobscured(sel, Caster())` (== precedent Gauntlets `GetSurroundingTargetsSelector @1811e20d0` qui
      observe depuis le caster). Geometrie Unobscured DEJA validee live cote PREDICTION (case-49/#50) : dist 1
      jamais obscurcie, dist 2 = elevation ; board plat -> passe-tout.

    **FACTORY NATIVE = `AttackWithAttackDamage @180de9fb0` -> `native_factory="attack"`** : CLASSIFIE PAR LES
    XREFS de l'ExecuteBehaviour natif (tip #2 / piege rngcrit-1202 -- attaque MULTI-COUPS), PAS au nom du
    template. Les DEUX call-sites `@18120432f` (main) et `@1812043cf` (splash) referencent `@180de9fb0`
    (verifie via `list_xrefs` ; SanctorumMissile ABSENT des xrefs de `@180de9c90`/`@180de9dd0` = la famille
    "ability"). `native_factory="attack"` => `AttackDamageOperation.ExecuteHit` = valeur brute + resolve
    slot-8 GASPILLE = **2 tirages/coup a cc=0** (defaut `wasted_resolve=True`). Un port copie a l'aveugle
    ("ability", 1 tirage/coup) desyncherait le RNG des le coup 2 -- confronte LIVE par le test.

    `op_BitwiseAnd` = `CombinedBehaviour` (effets PURS -> les deux volets s'executent) ; `ExecuteAtomic` ->
    `AtomicGroup` (inline #201 ; tag 0x56 = id du groupe atomique, aucun `EvaluateAbilities` implicite, cf.
    #209). Ordre = main PUIS splash (cibles splash triees par id = OrderBy natif) -> meme `state.rng` ->
    bit-exact BY CONSTRUCTION vs une sequence directe (memes bornes/hits/profil/factory)."""
    tgt = Target()
    # [MAIN] cible du message, 2 coups (nrOfHits 0x2f), plage MinMaxDamage, profil Blast, ranged.
    main = AttackWithAttackDamage(tgt, "SanctorumMissile", "Blast", is_melee=False,
                                  native_factory="attack")                       # @180de9fb0 (XREFS)
    # [SPLASH] unites adjacentes a la cible MOINS le caster (Morvenn), Unobscured depuis le caster ; MEME
    # plage, 1 coup (nrOfHits_2 0x32). Band TILE EmptyOrHasSteppable non porte (inerte, cf. docstring).
    splash_sel = Unobscured(Sub(AdjacentUnits(TargetTile()), Caster()), Caster())
    splash = AttackWithAttackDamage(splash_sel, "SanctorumMissile", "Blast", is_melee=False,
                                    hits_key="nrOfHits_2", multi=True, native_factory="attack")
    return AtomicGroup(op_and(main, splash))


class SanctorumMissileAbility(ActiveAbility):
    """`SanctorumMissileAbility$$ExecuteBehaviour @1812041d0` (id 1062, adeptMorvenn = Morvenn Vahl ; faction
    Sisterhood / Adepta Sororitas).

    Sequence native (`ExecuteAtomic`, `op_BitwiseAnd`, tag 0x56) :
        AttackWithAttackDamage(actor, target, MinMaxDamage, Blast, nrOfHits=GetNumberConstant(0x2f)=2)   # principale
      & AttackWithAttackDamage(actor, GetAdjacentDamageTargetsAll(), MEME MinMaxDamage, Blast,
                               nrOfHits_2=GetNumberConstant(0x32)=1)                                       # splash
    Splash = unites ADJACENTES a la cible (hex de Morvenn EXCLU) + tuiles vides/steppables, Unobscured depuis
    le caster ; MEME plage de degat que la principale, seul le nb de coups change (2 vs 1). RANGED (range 3,
    profil Blast, missile).

    `execute_behaviour` DELEGUE a `sanctorum_missile_tree()` (mirror 1:1 du decompile @1812041d0 +
    `GetAdjacentDamageTargetsAll @1812044a0`). Le SPLASH est un SEUL `AttackWithAttackDamage(selecteur-multi)`
    (== le natif, PAS un `Foreach`) : `AttackBehaviour.Execute` resout la liste + `OrderBy` par id. FACTORY
    `native_factory="attack"` (@180de9fb0, PROUVE par XREFS des call-sites @18120432f/@1812043cf -- CONTRASTE
    la famille "ability" @180de9c90/@180de9dd0, piege rngcrit-1202/tip #2) => 2 tirages/coup a cc=0.

    GAP flagge : band TILE `EmptyOrHasSteppableUnit @180ee83e0` du selecteur natif (tuiles vides/steppables)
    NON porte -- INERTE pour le degat-unite en duel (0 degat sur tuile vide ; aucune scenery Steppable), et le
    frere natif `GetAdjacentDamageTargetsUnits = Units(All)` (cote prediction) l'elimine deja en re-resolvant
    aux occupants. Passif porteur `RighteousRepugnance` (double-count ActOfFaith porte a part, act_of_faith.py)
    hors path SanctorumMissile."""
    __slots__ = ()
    ABILITY_TYPE = int(ActiveAbilityType.SanctorumMissile)  # 1062
    ABILITY_ID = "SanctorumMissile"

    def execute_behaviour(self, state: "State", caster_id: int,
                          target_id: Optional[int]) -> Optional[dict]:
        if target_id is None:
            return None
        ectx = ExecutionContext(state=state, rng=state.rng)
        sanctorum_missile_tree().execute(entities_from_state(state, caster_id, target_id), ectx)
        atks = [p for n, p in ectx.emitted if n == "AttackWithAttackDamage"]
        main = next((p["attack"] for p in atks if p.get("target") == target_id), None)
        splash = [{"target": p["target"], "attack": p["attack"]}
                  for p in atks if p.get("target") != target_id]      # cibles splash != cible principale
        return {"ability": "SanctorumMissile", "caster": caster_id, "target": target_id,
                "main_attack": main, "splash": splash, "dsl": True}


# ============================ SkyStrike (adeptCelestine Celestine, actif 1025) ============================
#
# `SkyStrikeAbility$$ExecuteBehaviour @181207d30` (namespace natif `Abilities.Active.Loki`) = template
# VigilanceEternal/HeroicFusillade EXACT (charge move-si-pas-adjacent + attaque), MAIS l'attaque n'est PAS
# `MinMaxDamage` config : c'est l'ATTAQUE MELEE NORMALE du caster + un flat `extraDmg`. Correction registre :
# le tag `SkyStrike [--] NO-OP EFFECT/BUFF` etait FAUX -- c'est un CHARGE + ATTAQUE MELEE. Arbre au decompile :
#     op_BitwiseAnd(
#       If( Not(IsAdjacent(caster@0x160, target@0x178, 3)),                                       # MOVE gate
#           MoveUnit(caster, First(SortTilesByUtility(CanAddUnit(AdjacentTiles(target)),          #   charge-tile
#                                  caster@0x160, UtilityDefinition(7)), 1)) ),
#       If( <factory+0x98 = gate alive, InitializeShared @180df2670>,                             # ATTACK gate
#           AttackWithAttackDamage(caster@0x160, target@0x178,
#               Sum(NormalAttackDamage(caster), Direct(GetVariableForLevel(8=extraDmg))),         #   base+extraDmg
#               NormalMeleeAttackDamageProfile(caster), MeleeWeaponHits(caster)) ) )              #   profil/coups MELEE
#
# Differences avec VigilanceEternal (@18122a580), lues au decompile :
#  - dest = `First(SortTilesByUtility(CanAddUnit(AdjacentTiles(target)), caster, UtilityDefinition(7)), 1)`
#    SANS l'intersection `MovableTilesInRange` (VigilanceEternal passe `GetPossibleMovementTiles` = CanAddUnit(
#    AdjacentTiles) op_And MovableTilesInRange(range=2, reachOnly)). SkyStrike alimente SortTilesByUtility avec
#    `CanAddUnit(AdjacentTiles(target))` SEUL -> AUCUNE contrainte de portee (Celestine vole / "Sky Strike").
#    Collapse (doctrine slice-18/19) = la tuile LIBRE ring-1 de la cible la PLUS PROCHE du caster (dist hex,
#    tie-break tile id) -- meme proxy que HeroicFusillade (utilDef 7).
#  - MOVE gate = `Not(IsAdjacent(caster, target, 3))` (== VigilanceEternal : bouge sauf si deja adjacent dist==1 ;
#    le `3` inerte pour le predicat par-paire, cf. VigilanceEternal RE).
#  - ATTACK = `AttackWithAttackDamage` overload @180dea6b0 (VERIFIE list_xrefs : SkyStrike call-site @1812080b2
#    -> @180dea6b0, ABSENT de @180de9fb0 ; @180dea6b0 == @180de9fb0 SAUF que `nrOfHits` est un NODE
#    `MeleeWeaponHits(caster)` passe direct a `AttackDamageBehaviour.ctor` au lieu d'une const int wrappee ->
#    MEME `AttackDamageBehaviour`, famille "attack"). Node de degat = `Sum(NormalAttackDamage(caster)=StatAmount(
#    Attack), Direct(GetVariableForLevel(8=extraDmg)))`. `StatAmountFormula.Calculate @180f22d40` = SOMME de
#    GetStat(Attack) sur le selecteur = UNE valeur (PAS de min/max) -> `AttackDamageBehaviour.GetDamage @180fbb250`
#    construit `HitDamage(V, V)` DEGENERE (V = Attack + extraDmg) : AUCUN spread +/-20% (le +/-20% de l'attaque
#    normale vient du weapon-path `GetBaseDamageFix64`, ABSENT du path ability). Chaque coup = reduce(V) FIXE.
#    Profil = `NormalMeleeAttackDamageProfile(caster)` = profil arme melee (Celestine = Power) ; coups =
#    `MeleeWeaponHits(caster)` = nrOfHits arme melee (WeaponHitsFormula.Calculate @180f2f510 = somme des parts,
#    SANS ExtraHits ; Celestine = 3). Modelise via le mode BORNES du leaf + `damage_override` -> (V,V) degenere +
#    `hits_override=MeleeWeaponHits` -> `execute_ability_attack(wasted_resolve=True)` (roll-then-reduce, resolve
#    slot-8 GASPILLE, 1 tirage/coup pour un node degenere : GetDamage court-circuite min==max + 1 resolve, cf.
#    #202 WeaverOfFate). RNG-exact vs le natif. `Sum(base, extraDmg)` == pattern MurderousSwing/SavageEchoes.
#  - ATTACK gate = `factory+0x98` = trigger cache du DslContext (`InitializeShared @180df2670`, construit depuis
#    +0x28) = gate "alive". Porte comme `IsAlive(caster) & IsAlive(target)` (== gate VigilanceEternal, template
#    EXACT ; post-charge non-reactive les deux sont vivants -> l'attaque tire). +0x98 exact non byte-resolu
#    (variante IsAlive) -- INERTE en runner (aucune mort reactive intra-arbre sur board plat 1v1).
# native_factory = "attack" (@180dea6b0 -> AttackDamageBehaviour -> ExecuteHit resolve slot-8). Config 1025
# (gameconfig LU) : attackRangeType=Melee, extraDmg[level] rarity-scaled (variablesAffectedByRarityBonus),
# initialCooldownTurns=1. Porteuse = Celestine (SkyStrike = sa SEULE active).


def _sk_pos_of(state: "State", uid: int):
    e = state.get_entity(uid)
    pc = e.get_component(PositionComponent) if e is not None else None
    return (pc.col, pc.row) if pc is not None else None


def _sk_occupied_positions(state: "State") -> set:
    occ: set = set()
    for e in state.entities.values():
        pc = e.get_component(PositionComponent)
        uc = e.get_component(UnitComponent)
        if pc is None or (uc is not None and not uc.alive):
            continue
        occ.add((pc.col, pc.row))
    return occ


def _sky_strike_dest_tile(state: "State", caster_id: int, target_id: int):
    """Collapse du selecteur de destination @181207d30 : `First(SortTilesByUtility(CanAddUnit(AdjacentTiles(
    target)), caster@0x160, UtilityDefinition(7)), 1)` -> la tuile LIBRE+marchable ring-1 (adjacente) de la
    cible la PLUS PROCHE du caster (dist hex, tie-break tile id). AUCUN filtre de reach/portee (contraste
    VigilanceEternal `GetPossibleMovementTiles`). Pre-move (aucune mutation avant le MoveUnit). Renvoie
    (col,row) ou None."""
    board = state.board
    cpos = _sk_pos_of(state, caster_id)
    tpos = _sk_pos_of(state, target_id)
    if board is None or cpos is None or tpos is None:
        return None
    occ = _sk_occupied_positions(state)
    cands = []
    for (c, r) in hexgeo.disk(tpos[0], tpos[1], 1):     # AdjacentTiles(target) = ring-1 (centre occupe -> exclu)
        if (c, r) in occ:
            continue
        t = board.id_at(c, r)
        if t is None or not board.walkable(t):          # CanAddUnit
            continue
        cands.append(t)
    if not cands:
        return None
    cands.sort(key=lambda t: (hexgeo.distance(cpos, board.coord(t)), t))   # SortTilesByUtility(7) collapse
    return board.coord(cands[0])


def _sky_strike_damage_override(extra_dmg: int):
    """`Sum(NormalAttackDamage(caster)=StatAmount(caster, Attack), Direct(GetVariableForLevel(8=extraDmg)))`
    porte en `GetAttackDamage` (mirror SavageEchoes/SpiritLeech damage_override) : base DEGENEREE V = stat
    Attack (LIVE, re-lue post-move) + extraDmg. `StatAmountFormula.Calculate @180f22d40` = 1 valeur (pas de
    min/max) -> HitDamage(V,V), AUCUN spread. bmin/bmax config (0/0, pas de minDmg/maxDmg 1025) IGNORES."""
    def _override(state, caster_id, target_id, bmin, bmax):
        e = state.get_entity(caster_id)
        sc = e.get_component(StatsComponent) if e is not None else None
        atk = int(sc.ctx.stats.get_stat(int(StatType.ATTACK), 0)) \
            if (sc is not None and sc.ctx is not None and sc.ctx.stats is not None) else 0
        v = atk + int(extra_dmg)
        return v, v
    return _override


def sky_strike_tree(dest, extra_dmg: int, profile: str, hits: int):
    """Mirror 1:1 de `SkyStrikeAbility$$ExecuteBehaviour @181207d30` (template VigilanceEternal EXACT, attaque
    = attaque melee NORMALE du caster + extraDmg au lieu de MinMaxDamage config). `dest`/`extra_dmg`/`profile`/
    `hits` resolus imperativement (collapse du selecteur S + config, comme VigilanceEternal `dest`) :
        op_BitwiseAnd(
          If(Not(IsAdjacent(caster,target)), MoveUnit(caster, dest)),                    # MOVE (charge)
          If(IsAlive(caster) & IsAlive(target),                                          # ATTACK gate (factory+0x98)
             AttackWithAttackDamage(caster->target,
                 Sum(StatAmount(caster, Attack), Direct(extraDmg)),                      #   NormalAttackDamage + var8
                 NormalMeleeAttackDamageProfile(caster), MeleeWeaponHits(caster))) )     #   attaque melee normale
    Mono-cible (pas de Union/splash). Le node de degat = valeur mono (Attack + extraDmg) DEGENEREE -> mode BORNES
    + `damage_override` -> (V,V) + `hits_override` -> `execute_ability_attack(wasted_resolve=True)` : chaque coup
    = reduce(V) FIXE, 1 tirage/coup (resolve slot-8 gaspille). AUCUN spread +/-20% (path ability, pas
    weapon-path)."""
    move = If(Not(IsAdjacent(Caster(), Target())),
              MoveUnit(Caster(), FixedTiles([dest] if dest is not None else [])))
    attack = AttackWithAttackDamage(Target(), "SkyStrike", profile, is_melee=True,
                                    damage_override=_sky_strike_damage_override(int(extra_dmg)),
                                    hits_override=int(hits), native_factory="attack")
    attack_branch = If(TriggerAnd(IsAlive(Caster()), IsAlive(Target())), attack)
    return op_and(move, attack_branch)


class SkyStrikeAbility(ActiveAbility):
    """`SkyStrikeAbility$$ExecuteBehaviour @181207d30` (id 1025, adeptCelestine = Celestine ; faction
    Sisterhood / Adepta Sororitas). CHARGE + ATTAQUE MELEE (correction registre : le tag `NO-OP EFFECT/BUFF`
    etait FAUX). Arbre DSL `sky_strike_tree()` = VigilanceEternal EXACT MOINS la contrainte de reach du move,
    PLUS une attaque = attaque melee NORMALE du caster + extraDmg (au lieu de MinMaxDamage config, qui donnerait
    0 : SkyStrike n'a PAS de minDmg/maxDmg) :
    (1) Celestine CHARGE sur la tuile LIBRE ring-1 de la cible la plus proche (SANS limite de portee -- elle
        vole), gate `Not(IsAdjacent)` (skip si deja adjacente) ; (2) attaque MELEE mono-cible = base
        `NormalAttackDamage(caster)`=stat Attack + `extraDmg`[level] (rarity-scaled), profil/coups de l'arme
        MELEE (Celestine = Power / 3 coups), gatee par les deux vivants. Selecteur S (dest) collapse ; structure
        DSL. Renvoie {move, attack, dsl}.

    `GetDynamicInvalidTargetReason @1812082a0` (face DECISION/eligibilite, HORS ExecuteBehaviour) : gate
    `DidMove(caster)` -> si Celestine a DEJA bouge ce tour ET n'est pas adjacente a la cible, l'ability est
    INVALIDE (reason 0x10) ; sinon valide ssi une tuile libre adjacente existe (reason 0x20 sinon). Enforce cote
    ciblage (l'ability n'est offerte que si castable) ; le runner l'invoque une fois castable.

    native_factory `attack` (@180dea6b0, PROUVE par XREFS du call-site @1812080b2 -- overload de @180de9fb0
    dont seul l'arg hits differe [NODE vs const], MEME AttackDamageBehaviour). Node de degat DEGENERE (Sum(
    StatAmount(Attack), Direct(extraDmg)) = 1 valeur, StatAmountFormula.Calculate @180f22d40) -> HitDamage(V,V) :
    chaque coup = reduce(V) FIXE, 1 tirage/coup (GetDamage court-circuite min==max + resolve slot-8 gaspille,
    cf. #202). Modelise en mode BORNES + damage_override(V,V) + hits_override -> execute_ability_attack(wasted).

    PORTEUR HORS POOL (comme SavageEchoes) : adeptCelestine absente du seed BC capture -> injectee via seed-BC
    custom. Le cast LIVE de 1025 leve `system error` (`AbilityConfiguration.GetVariableForLevel(8=extraDmg)`
    THROW pour une unite injectee dont l'array n'est pas materialise) -> RESIDU documente (idem SavageEchoes).
    Validation = A/B (arbre == execute_ability_attack direct sous meme rng) + charge (deterministe-sur-etat) ;
    la machinerie per-coup melee est live-validee ailleurs (VigilanceEternal 3-hit, CordClaw 4-hit)."""
    __slots__ = ()
    ABILITY_TYPE = int(ActiveAbilityType.SkyStrike)  # 1025
    ABILITY_ID = "SkyStrike"

    def execute_behaviour(self, state: "State", caster_id: int,
                          target_id: Optional[int]) -> Optional[dict]:
        if target_id is None:
            return None
        e = state.get_entity(caster_id)
        sc = e.get_component(StatsComponent) if e is not None else None
        ctx = sc.ctx if sc is not None else None
        # NormalMeleeAttackDamageProfile(caster) + MeleeWeaponHits(caster) : profil/coups de l'ARME MELEE du
        # caster (dist=1 force la selection melee). extraDmg = GetVariableForLevel(8), rarity-scaled par niveau.
        if ctx is not None:
            _p, _ranged, melee_hits = select_weapon_pierce(ctx, 1)
            w = select_weapon(ctx, 1)
            profile = (w or {}).get("DamageProfile") or "Power"
            level = ctx.active_ability_level
            mult = ctx.ability_variables_multiplier
        else:
            melee_hits, profile, level, mult = 1, "Power", 0, 100
        extra = ability_var(self.ABILITY_ID, "extraDmg", level, multiplier_pct=mult) or 0
        dest = _sky_strike_dest_tile(state, caster_id, target_id)
        ectx = ExecutionContext(state=state, rng=state.rng)
        sky_strike_tree(dest, int(extra), profile, int(melee_hits)).execute(
            entities_from_state(state, caster_id, target_id), ectx)
        moved = next((p for n, p in ectx.emitted if n == "MoveUnit"), None)
        atk = next((p for n, p in ectx.emitted if n == "AttackWithAttackDamage"), None)
        return {"ability": "SkyStrike", "caster": caster_id, "target": target_id,
                "move": moved, "attack": atk, "dsl": True}
