"""Abilities Space Wolves (namespace natif `Abilities.Active.Loki.*`) — face COMBAT (case-220 SW).

Module DEDIE (org native = 1 classe par ability `Abilities.Active.*` ; `loki/` et les autres modules
d'abilities sont deja > 1000 lignes = seuil de split). RE ghidra build gqfc5mff6c (VA citees).

[1089 GreatFrostAxe | spaceWulfen] — attaque melee 4x Piercing + pose de glace (zone cible+ring-1).
Patron « Stormcaller inverse » : Stormcaller (`loki/stormcaller.py`) POSE la glace PUIS attaque les
ennemis DEBOUT sur la glace (multi-cible, ability-family) ; GreatFrostAxe pose la glace PUIS attaque la
CIBLE DIRECTE (mono-cible, ATTACK-family). Doc : docs/rl/case-220/space-wolves.md §6.15.
"""
from __future__ import annotations

from typing import Optional, TYPE_CHECKING

from ...entities.behaviours import op_and, If
from ...entities.selectors import Target, Tiles, AdjacentTiles, Union
from ...entities.triggers import IsAlive
from ...entities.active_ability_type import ActiveAbilityType
from ...entities.effect_type import EffectType
from ...dsl.effects import ExecutionContext
from .base import ActiveAbility
from .behaviours import AttackWithAttackDamage, AddEffect, entities_from_state

if TYPE_CHECKING:
    from ..state import State

ICE_TILE = int(EffectType.Ice)          # 17 (0x11) — effet de TUILE Ice, duree defaut 2 rounds (@181559ff0)


def great_frost_axe_ice_tiles() -> Union:
    """Zone de glace de GreatFrostAxe — construction INLINE dans `ExecuteBehaviour @1811e3500` (MIRROR
    du DECOMPILE, pas d'accesseur `GetAddIceTiles` separe cote natif contrairement a Stormcaller) :
        AdjacentTiles(TargetTiles@0x190)  op_Addition  TargetTiles@0x190
    = le ring-1 de la tuile de la cible + la tuile elle-meme (== `StormcallerAbility.GetAddIceTiles
    @18120cf70`, MEME construction byte-pour-byte). Port : `Union(AdjacentTiles(Target()), Tiles(Target()))`
    (IDENTIQUE a `stormcaller_get_add_ice_tiles`). `@0x190` = le selecteur TargetTiles de la cible ->
    `Tiles(Target())` (POSITION MainTile) ; `AdjacentTiles(@0x190)` -> `AdjacentTiles(Target())` (ids de
    tuile du ring, l'elevation gate le voisinage via `board.neighbours`). Domaines mixtes normalises par
    `_add_effect_target_id` (int = tile-id, (col,row) = position). i2 : « covers the hex the enemy stands
    on and all hexes adjacent to it in Ice »."""
    return Union(AdjacentTiles(Target()), Tiles(Target()))


def great_frost_axe_tree():
    """Arbre de `GreatFrostAxeAbility.ExecuteBehaviour @1811e3500` (id 1089, spaceWulfen — MIRROR 1:1 du
    DECOMPILE) :
        op_BitwiseAnd(
            AddEffect( 0x11=Ice, AbilityStateReference, source=Owner@0x148,
                       cible = op_Addition(AdjacentTiles(TargetTiles@0x190), TargetTiles@0x190),
                       <Nullable ZEROE> ),                                                        # [1] glace
            If( IsAlive(target@0x178),
                AttackWithAttackDamage( caster@0x160, target@0x178,
                    RandomAmount(GetVariableForLevel(0xc=minDmg), GetVariableForLevel(0xd=maxDmg)),
                    GetDamageProfile(config)=Piercing, GetNumberConstant(0x2f)=nrOfHits=4,
                    AbilityOrEffect(this@+0x10=1089) ) ) )                                        # [2] attaque

    Port : `op_and( AddEffect(Ice, zone, defaut), If(IsAlive(Target()), AttackWithAttackDamage(...)) )`.

    ORDRE = `op_BitwiseAnd(AddEffect(Ice), If(...))` = GLACE D'ABORD, PUIS attaque (left->right, `Seq`
    court-circuit ; les deux volets sont PURS -> les deux s'executent). C'est le natif `op_BitwiseAnd(uVar13=
    AddEffect(Ice), uVar12=If(IsAlive,attack))` @1811e3500. La glace est DETERMINISTE (aucun tirage RNG) ->
    l'ordre glace-avant-attaque n'altere PAS l'ordre RNG de l'attaque : les ROLLS per-coup sont bit-exacts
    (le port et le live tirent la MEME sequence -- valide live : native_factory correct, cf. plus bas).

    ###### RESIDU x1.5 RESOLU (#45f fable, 2026-07-24) — c'etait l'ELEVATION, pas la glace ######
    L'ex-« bonus crit-sur-glace +50% » etait un ARTEFACT DE CONFUSION : la mesure historique (live =
    1.5x offline par coup, DidCrit=0) venait du bonus d'ELEVATION (`Damage.ElevationBonus`=50, feuille
    positionnelle du builder PARTAGE `CalculateAttackerModifiersForPrediction @181000590`, gate
    `elev(att) > elev(cible)` + effet 0x423, AUCUN gate normale/ability) que le vecteur offline
    `execute_ability_attack` n'appliquait pas (fork de port : seul le chemin attaque NORMALE appelait
    `apply_elevation_bonus`). Le scenario de test move sur `aiAttackRank ranked[0]` qui PREFERE le
    surplomb sur MC1_67 -> 1.5x systematique ; l'attaque normale du meme caster passait, elle, par le
    chemin qui applique l'elevation -> « pas de divergence » (confond parfait). PROUVE par sonde
    discriminante (`probe_45f_gfa_elevation`, une variable = la relation d'elevation) : pre-fix
    high=1.5000x/coup, flat=bit-exact, low=bit-exact (gate strict `>`) ; post-fix 16/16 coups
    bit-exact (4 cas x 4 coups). FIX : `execute_ability_attack`/`execute_normal_like` appliquent
    desormais `apply_elevation_bonus` + `apply_trench_reduction` comme le chemin normal (#45f).

    La CONTRADICTION historique (« CRIT_DAMAGE=0 mais +50% ») est levee : la formule
    `IceEffect.CreateEffectDamageBonusForAttack @180f44940` n'a JAMAIS ete la source du 1.5x. C'est un
    `EffectBonus` (struct il2cpp : trigger/multiplicator/ADDITION/subtraction/minimum/override) du canal
    ADDITION : `PercentageOf(StatAmount(attacker, CRIT_DAMAGE=10), EffectConfig(5)=IceCritDmgBonusPct=25)`
    gate `AttackDamageIsCritical & AreEqual(occupant-tuile-Ice, target) & !HasTrait(target, 0x19=Immune)`
    = +25% du CRIT_DAMAGE de l'attaquant, PAR COUP CRITIQUE, contre une cible sur tuile glacee -> 0 pour
    Wulfen (cd=0). PORTE (`damage_model.ice_crit_damage_addition`) et VALIDE live par crit force
    (probe --case crit, --crit 100,700 : delta natif +175 = floor(700 x 25 / 100) par coup crit, 4/4
    bit-exact post-port). i2 « The Crit Damage bonus of the Ice is already applied for this attack » =
    note d'AFFICHAGE (les nombres montres incluent le bonus), pas une regle d'execution speciale.

    - [1] `AddEffect(Ice)` : glace la tuile de la cible + son ring-1 (`great_frost_axe_ice_tiles()`). Duree =
      arg Nullable ZEROE -> `duration_rounds=None` -> `DefaultAmountOfRounds(0x11)=2` (== case-35/Stormcaller).
      Feuille `AddEffect` tile-domain (le selecteur rend des tuiles ; `AddEffectOperation` pose l'effet Ice).
    - [2] `If(IsAlive(target), attack)` : garde LAZY `DSLFactory.IsAlive(target@0x178) @180df2fa0` (vivant &
      hp>0) devant l'attaque -- la glace ne tue pas, donc la garde est vraie pour un cast normal (mirror
      fidele, meme idiome que VigilanceEternal/HeroicFusillade/genestealer `If(IsAlive(Target()), ...)`).
      Attaque MONO-cible melee 4 coups Piercing (pierce 80), bornes `MinMaxDamage(minDmg/maxDmg[level])`
      rarity-affected via `ability_attack_params`.

    `native_factory="attack"` (defaut) = famille `DSLFactory.AttackWithAttackDamage @180de9fb0`
    (AttackDamageBehaviour -> `AttackDamageOperation.ExecuteHit`) = 2 tirages/coup a cc=0 (valeur brute +
    resolve slot-8 GASPILLE, cf. cas fable rngcrit-1202 / tip #2). CLASSE PAR LES XREFS : `GreatFrostAxe
    Ability$$ExecuteBehaviour` appelle @180de9fb0 (from_address 1811e367f, UNCONDITIONAL_CALL) -- l'ATTACK
    family, PAS l'ability family (@180de9dd0->@180de9e50) qu'utilise Stormcaller. Multi-coups (4 hits) ->
    per-hit desync des le coup 2 si mal classe : ici c'est bien "attack" (verifie XREF).

    `ability_type=1089` = l'arg natif `AbilityOrEffect(this+0x10)` (= ActiveAbilityType.GreatFrostAxe),
    threade au payload des events after-hit (== Stormcaller threade 1113) : != 1013 -> la branche smite
    LordOfTempests AddIce reste muette (fidele) ; n'affecte AUCUN nombre de degat (le roll/reduce/crit/block
    ne depend pas de `ability_type`)."""
    ice = AddEffect(ICE_TILE, "Ice", great_frost_axe_ice_tiles(), duration_rounds=None)  # duree DEFAUT (Nullable zeroe)
    attack = AttackWithAttackDamage(Target(), "GreatFrostAxe", "Piercing", is_melee=True,   # 4x Piercing melee mono-cible
                                    native_factory="attack",   # XREF @1811e367f -> @180de9fb0 (attack family, 2 tirages/coup)
                                    ability_type=int(ActiveAbilityType.GreatFrostAxe))
    return op_and(ice, If(IsAlive(Target()), attack))


class GreatFrostAxeAbility(ActiveAbility):
    """`GreatFrostAxeAbility.ExecuteBehaviour @1811e3500` (id 1089, spaceWulfen «Wulfen», namespace natif
    `Abilities.Active.Loki`) — cf. docstring `great_frost_axe_tree()`. Behaviour = `great_frost_axe_tree()`
    (mirror 1:1). Patron « Stormcaller inverse » : glace la zone (tuile cible + ring-1) PUIS attaque la CIBLE
    DIRECTE 4x Piercing (mono-cible, ATTACK-family, gate `If(IsAlive(target))`). Diag : tuiles glacees +
    attaque (id + total).

    Turn-flags = defauts base (1089 ABSENT des overrides `NO_END_TURN`/`NO_ABILITY_USED_FLAG` -> le cast
    TERMINE le tour + pose ActiveAbilityUsed, == Stormcaller). La glace, l'attaque et le DEGAT per-coup
    sont BIT-EXACTS vs live (native_factory correct + elevation appliquee au vecteur ability, residu
    x1.5 RESOLU #45f — c'etait `Damage.ElevationBonus`, pas la glace ; le vrai bonus crit-sur-Ice
    (+25% du CRIT_DAMAGE par coup crit vs cible gelee, `ice_crit_damage_addition`) est porte et vaut 0
    ici (cd=0). Cf. `great_frost_axe_tree`."""
    __slots__ = ()
    ABILITY_TYPE = int(ActiveAbilityType.GreatFrostAxe)  # 1089
    ABILITY_ID = "GreatFrostAxe"

    def execute_behaviour(self, state: "State", caster_id: int,
                          target_id: Optional[int]) -> Optional[dict]:
        if target_id is None:
            return None
        ectx = ExecutionContext(state=state, rng=state.rng)
        great_frost_axe_tree().execute(entities_from_state(state, caster_id, target_id), ectx)
        iced: list = []
        main_attack = None
        for name, p in ectx.emitted:
            if name == "AddEffect" and p.get("effect_type") == ICE_TILE and p.get("placed"):
                iced.append(p.get("target"))               # ids de tuile glaces (nouvelles poses)
            elif name == "AttackWithAttackDamage":
                main_attack = p.get("attack")              # attaque MONO-cible (per_hit/crits/total)
        return {"ability": "GreatFrostAxe", "caster": caster_id, "target": target_id,
                "iced_tiles": iced, "main_attack": main_attack, "dsl": True}
