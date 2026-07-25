"""Abilities de la faction DarkAngels (faction native id 10, codename « Loki »). RE ghidra gqfc5mff6c
(VA citees). Case-220 / docs/rl/case-220/dark-angels.md.

Org native = 1 classe par ability (`Abilities.Active.Loki.*`) ; les arbres SPECIFIQUES vivent avec leur
ability. Module DEDIE (les modules `loki/` et `behaviours/` sont deja au seuil de split ~1000 lignes).

PlasmaCannon (`PlasmaCannonAbility$$IdunBattleLogic.Entities.Abilities.Active.Loki.PlasmaCannonAbility$$ExecuteBehaviour`, id 1150, unite darkaTerminator) :
attaque RANGED (range 3, profil Plasma) 3x sur la cible + 3x sur JUSQU'A 2 unites tirees au hasard
DIRECTEMENT DERRIERE la cible. Meme plage de degat ET meme nb de coups pour les deux volets. Template
`plasma_grenade_tree` (loki/splash.py) MOINS le selecteur splash (adjacent-cible -> directly-behind) ET
avec une FACTORY NATIVE DIFFERENTE (cf. ci-dessous, piege rngcrit-1202).
"""
from __future__ import annotations

from typing import Optional, TYPE_CHECKING

from ...dsl.effects import ExecutionContext
from ...entities.behaviours import AtomicGroup, op_and
from ...entities.selectors import Target, UnitsDirectlyBehind
from ...entities.active_ability_type import ActiveAbilityType
from .base import ActiveAbility
from .behaviours import AttackWithAttackDamage, entities_from_state

if TYPE_CHECKING:
    from ..state import State


def plasma_cannon_tree():
    """Arbre de `IdunBattleLogic.Entities.Abilities.Active.Loki.PlasmaCannonAbility$$ExecuteBehaviour` (id 1150, darkaTerminator — MIRROR du
    DECOMPILE) :
        ExecuteAtomic( op_BitwiseAnd(
            AttackWithAttackDamage(caster@0x160, target@0x178, MinMaxDamage(var0xc,var0xd), Plasma,
                                   GetHits(0)=GetNumberConstant(0x2f)=nrOfHits),                       # [MAIN]
            AttackWithAttackDamage(caster@0x160,
                PickRandomly( UnitsDirectlyBehind(caster, target), 2 ),
                MinMaxDamage(MEME), Plasma, GetHits(0)=nrOfHits(MEME)) ),                              # [SPLASH]
          0x2a )

    DIFFERENCES vs `plasma_grenade_tree` (le template cite par la roadmap) — 3 divergences LUES au decompile,
    JAMAIS copiees du commentaire du template :

    1. **SELECTEUR splash = `PickRandomly(UnitsDirectlyBehind(target), 2)`** (PlasmaGrenade = `Enemies(caster,
       AdjacentUnits(target,1))`). `IdunBattleLogic.Entities.DSLFactory$$UnitsDirectlyBehind` (DEJA porte, selectors.py:157, cite
       PlasmaCannon) = ennemis-du-caster VIVANTS sur l'anneau R1 de la cible, du COTE OPPOSE au caster
       (`MinDistance(caster,cand) > MinDistance(caster,target)`, STRICT = AmountIsGreater, case #48 : la
       laterale a distance EGALE est EXCLUE), meme elevation (tolerance +-1). Le `IdunBattleLogic.Entities.DSLFactory$$PickRandomly(.,2)` (2 = nrOfTargets, lu au decompile) est FOLDE dans la feuille via `pick_n=2` (comme Fragstorm
       IdunBattleLogic.Entities.Abilities.Active.Loki.FragstormAbility$$ExecuteBehaviour : tire 2 cibles DANS la resolution du selecteur d'attaque via `state.rng`). len<=2 -> les deux
       (le natif ne roll pas quand le set tient).

    2. **HITS main == HITS splash == `nrOfHits` (0x2f)** : les DEUX volets appellent `GetHits(param_1,0)`
       (`ArmoriumCherubAbility$$IdunBattleLogic.Entities.Abilities.Active.Loki.ArmoriumCherubAbility$$GetHits` = `GetNumberConstant(config, 0x2f, 0)` = nrOfHits). PlasmaGrenade
       differenciait main (0x2f) / splash (0x32=nrOfHits_2) ; ICI le splash utilise la MEME cle `nrOfHits` (defaut
       `hits_key`). Plage `MinMaxDamage(minDmg/maxDmg)` PARTAGEE main/splash (memes cles par defaut). Config 1150 :
       nrOfHits=3, range=3, damageProfile=Plasma.

    3. **FACTORY NATIVE = `IdunBattleLogic.Entities.DSLFactory$$AttackWithAttackDamage` -> `native_factory="attack"`** (PlasmaGrenade =
       `IdunBattleLogic.Entities.DSLFactory$$AttackWithAbilityDamage` -> "ability"). CLASSIFIE PAR XREFS de l'ExecuteBehaviour natif (piege
       rngcrit-1202 / tip #2), PAS au nom du template : les deux call-sites `IdunBattleLogic.Entities.Abilities.Active.Loki.PlasmaCannonAbility$$ExecuteBehaviour+0x1eb`/`IdunBattleLogic.Entities.Abilities.Active.Loki.PlasmaCannonAbility$$ExecuteBehaviour+0x2a6` referencent
       IdunBattleLogic.Entities.DSLFactory$$AttackWithAttackDamage (verifie via `list_xrefs` -- PlasmaCannon ABSENT des xrefs de IdunBattleLogic.Entities.DSLFactory$$AttackWithAbilityDamage). `native_factory=
       "attack"` => `AttackDamageOperation.ExecuteHit` = valeur brute + resolve slot-8 GASPILLE = **2 tirages/
       coup a cc=0** (le DEFAUT `is_attack_damage_op=True`). Un port copie a l'aveugle du template (native_factory=
       "ability", 1 tirage/coup) desyncherait le RNG des le coup 2 -- confronte LIVE par le test.

    `op_BitwiseAnd` = `CombinedBehaviour` (effets PURS -> les deux volets s'executent) ; `ExecuteAtomic` ->
    `AtomicGroup` (inline #201 ; tag 0x2a = id du groupe atomique, aucun `EvaluateAbilities` implicite, cf. #209).
    Ordre = main PUIS splash (cibles triees par id = OrderBy natif) -> meme `state.rng`. RANGED (range 3) ->
    `is_melee=False`.

    GAP (flagge) : (a) `UnitsDirectlyBehind` runner degrade le GATE d'ELEVATION en no-op (`entities_from_state`
    ne peuple pas `ctx.elev_by_pos`) -> sur board plat = exact (meme elevation partout) ; board a relief =
    raffinement. (b) RNG-exact du `PickRandomly` >2 candidats : `_pick_randomly_n` tire via `state.rng` mais
    l'ORDRE/cout exact de `PickRandomlySelector.Select` n'est pas cale (== Fragstorm #215) -> le set/la conso rng
    peuvent diverger quand >2 unites derriere la cible. Structure fidele ; bit-exactness garantie a <=2 derriere."""
    tgt = Target()
    # [MAIN] cible du message, 3 coups (nrOfHits), plage MinMaxDamage, profil Plasma, ranged.
    main = AttackWithAttackDamage(tgt, "PlasmaCannon", "Plasma", is_melee=False,
                                  native_factory="attack")                       # IdunBattleLogic.Entities.DSLFactory$$AttackWithAttackDamage (XREFS)
    # [SPLASH] jusqu'a 2 unites tirees derriere la cible ; MEME plage, MEME nb de coups (nrOfHits, defaut).
    splash = AttackWithAttackDamage(UnitsDirectlyBehind(), "PlasmaCannon", "Plasma", is_melee=False,
                                    multi=True, pick_n=2, native_factory="attack")  # PickRandomly(UnitsDirectlyBehind,2)
    return AtomicGroup(op_and(main, splash))


class PlasmaCannonAbility(ActiveAbility):
    """`PlasmaCannonAbility$$IdunBattleLogic.Entities.Abilities.Active.Loki.PlasmaCannonAbility$$ExecuteBehaviour` (id 1150, darkaTerminator ; faction DarkAngels).

    Sequence native (`ExecuteAtomic`, `op_BitwiseAnd`) :
        AttackWithAttackDamage(actor, target, MinMaxDamage, Plasma, nrOfHits=GetHits(0)=0x2f)             # principale
      & AttackWithAttackDamage(actor, PickRandomly(UnitsDirectlyBehind(actor,target), 2), MEME MinMaxDamage,
                               Plasma, nrOfHits=GetHits(0)=0x2f)                                            # splash <=2
    Splash = jusqu'a 2 unites ennemies tirees au hasard DIRECTEMENT DERRIERE la cible (anneau R1, cote oppose au
    caster), MEME plage de degat ET MEME nb de coups que la principale. RANGED (range 3, profil Plasma).

    `execute_behaviour` DELEGUE a `plasma_cannon_tree()` (mirror 1:1 du decompile). Le SPLASH est un SEUL
    `AttackWithAttackDamage(selecteur-multi, pick_n=2)` (== le natif, PAS un `Foreach`) : `AttackBehaviour.Execute`
    resout la liste + `OrderBy` par id + `PickRandomly(2)`. FACTORY `native_factory="attack"` (IdunBattleLogic.Entities.DSLFactory$$AttackWithAttackDamage, prouve
    par XREFS -- CONTRASTE le template PlasmaGrenade "ability" IdunBattleLogic.Entities.DSLFactory$$AttackWithAbilityDamage, piege rngcrit-1202/tip #2) => 2 tirages/
    coup a cc=0. Passif porteur `Deathwing` [fable] non porte (no-op ; se declenche on-block, hors path degat)."""
    __slots__ = ()
    ABILITY_TYPE = int(ActiveAbilityType.PlasmaCannon)  # 1150
    ABILITY_ID = "PlasmaCannon"

    def execute_behaviour(self, state: "State", caster_id: int,
                          target_id: Optional[int]) -> Optional[dict]:
        if target_id is None:
            return None
        ectx = ExecutionContext(state=state, rng=state.rng)
        plasma_cannon_tree().execute(entities_from_state(state, caster_id, target_id), ectx)
        atks = [p for n, p in ectx.emitted if n == "AttackWithAttackDamage"]
        main = next((p["attack"] for p in atks if p.get("target") == target_id), None)
        splash = [{"target": p["target"], "attack": p["attack"]}
                  for p in atks if p.get("target") != target_id]      # cibles splash != cible principale
        return {"ability": "PlasmaCannon", "caster": caster_id, "target": target_id,
                "main_attack": main, "splash": splash, "dsl": True}
