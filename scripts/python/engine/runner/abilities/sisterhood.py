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
from ...entities.behaviours import AtomicGroup, op_and
from ...entities.selectors import Target, TargetTile, Caster, AdjacentUnits, Sub, Unobscured
from ...entities.active_ability_type import ActiveAbilityType
from .base import ActiveAbility
from .behaviours import AttackWithAttackDamage, entities_from_state

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
