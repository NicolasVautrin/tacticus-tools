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

    ###### RESIDU MAJEUR = BONUS CRIT-SUR-GLACE +50% (CANDIDAT FABLE-SOLVER, PAS PORTE) ######
    i2 : « The Crit Damage bonus of the Ice is already applied for this attack ». MESURE LIVE (spaceWulfen
    vs necroWarden, cc=0, DidCrit=0 sur tous les coups) : le degat LIVE par coup = EXACTEMENT 1.5x le degat
    OFFLINE (ratio 2425/1616=1.5006, 2508/1672=1.5000, 2456/1637=1.5003 -- coup 4 clampe par la mort). Ce
    +50% est SPECIFIQUE a GreatFrostAxe : une attaque NORMALE du MEME spaceWulfen sur la MEME necroWarden ne
    diverge PAS (offline ~1670 == live ~1700). C'est donc le bonus crit-sur-glace de l'effet Ice
    (`IceEffect.CreateEffectDamageBonusForAttack @180f44940`), applique a l'attaque de GreatFrostAxe parce
    qu'elle glace la tuile de la cible AVANT de frapper (la cible est « on-Ice » au moment du coup).

    IMPORTANT -- ce n'est PAS « crit-only » (l'hypothese initiale du doc case-220 space-wolves.md, REFUTEE
    par le live) : le bonus s'applique a CHAQUE coup meme NON-critique (DidCrit=0). Contradiction NON RESOLUE
    dans le decompile : `CreateEffectDamageBonusForAttack` = `PercentageOf(StatAmount(caster, CRIT_DAMAGE=10),
    EffectConfig(5))` gate par `AttackDamageIsCritical & AreEqual(occupant-tuile-glacee, target) & NOT
    HasTrait(target,0x19)` -- MAIS le caster a CRIT_DAMAGE=0 (mesure), donc `PercentageOf(0, config5)=0`, ce
    qui contredit le +50% observe ; ET le gate `AttackDamageIsCritical` devrait etre faux sur un coup non-crit.
    -> le mecanisme exact (comment l'attaque devient « critical » pour le bonus + d'ou vient le 50% sans
    CRIT_DAMAGE) reste SOUS-DETERMINE. C'est un SOUS-SYSTEME PARTAGE jamais modelise offline : la famille
    `Effect.CreateEffectDamageBonusForAttack` (~40+ effets) collectee par `BaseEffect.DamageBonusForAttack
    @180f0f5e0` dans `AttackDamageOperation.ExecuteHit @180e5eff0` (== residu #131/#133 flague -- a tort
    « crit-only » -- dans Stormcaller `loki/stormcaller.py`, qui diverge IDENTIQUEMENT mais n'a jamais eu de
    test bit-exact live). Le porter FIDELEMENT (pas fitter un x1.5) exige de RE ce subsystem + resoudre la
    contradiction CRIT_DAMAGE=0 -> **CANDIDAT FABLE-SOLVER / tranche dediee effect-damage-bonus**. En
    attendant, ce port ship la STRUCTURE fidele (glace + attaque + native_factory), degat ~33% bas (÷1.5),
    COHERENT avec Stormcaller (meme residu). La face DECISION/prediction (playbook @18113fbd0) est validee a
    part (case-220 s18) et n'est PAS impactee (la prediction a son propre canal crit-Ice).

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
    TERMINE le tour + pose ActiveAbilityUsed, == Stormcaller). La glace, l'attaque et ses ROLLS per-coup sont
    reels et bit-exacts vs live (native_factory correct). RESIDU MAJEUR NON PORTE (cf. `great_frost_axe_tree`) :
    le bonus crit-sur-glace +50% (`IceEffect.CreateEffectDamageBonusForAttack`) applique a CHAQUE coup (mesure
    live x1.5, PAS crit-only) -> degat ~33% bas. Sous-systeme `effect-damage-bonus` PARTAGE jamais modelise
    offline -> CANDIDAT FABLE-SOLVER (contradiction CRIT_DAMAGE=0 vs +50% non resolue)."""
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
