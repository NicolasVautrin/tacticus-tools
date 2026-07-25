"""MasterOfTheTutelaries_Summon (triggered 1173, Abraxas thousInfernalMaster) — #202 tranche C.

Mirror du kit natif `IdunBattleLogic.Entities.Abilities.Triggered.Loki.MasterOfTheTutelaries_SummonAbility`,
ARMEE par l'effet-marqueur 1197 (`MasterOfTheTutelariesEffect`, pose par l'active 1096 — cf.
`effects/loki/status.py` + `EFFECT_TRIGGERS[1197]` dans `../dispatch.py` : la collecte par-effet-actif
EST le Add/RemoveTriggeredAbility natif d'`IdunBattle.Entities.Effects.Loki.MasterOfTheTutelariesEffect$$ApplyInternal` / `IdunBattle.Entities.Effects.Loki.MasterOfTheTutelariesEffect$$RevertInternal`).

- `IdunBattleLogic.Entities.Abilities.Triggered.Loki.MasterOfTheTutelaries_SummonAbility$$CreateTrigger` :
    On(9=Attack, 1)
    & HasEffect(owner@0x148, 0x4ad=1197)               # re-gate natif (double du Add/Remove dynamique)
    & AreEnemies(owner@0x148, target@0x178)            # la cible de l'attaque est un ENNEMI du porteur
    & Not(IsObjectOrSteppable(target@0x178))           # vraie unite (pas decor/decoy steppable)
    & CurrentAttackDamageProfilesContain(0xd=13)       # les profils de l'ATTAQUE contiennent Psychic
  `On(9)` = event generique de FIN d'attaque (`FinishAttackOperation IdunBattle.Operations.FinishAttackOperation$$Execute`, normale ET ability) —
  UN fire max par attaque qualifiante (MESURE live diag 202c runner 183 : 1 Screamer par ATTAQUE, pas
  par coup — l'attaque melee du Horror avec 2 degats n'a donne qu'UN Screamer). AUCUN gate
  « degat > 0 » : une attaque Psychic entierement bloquee declenche quand meme (decompile = verite ;
  l'i2 « dealt Psychic Damage » est approximatif). ⚠ `CurrentAttackDamageProfilesContain` inclut les
  profils des BONUS-HITS #179 (mesure : melee Physical/Power + bonus InfernalPacts Psychic QUALIFIE)
  -> la chaine Horror -> Screamer -> Screamer... n'est PAS bornee par le profil d'arme, seulement par
  les positions (un summon sans cible a portee n'attaque pas) et les tuiles libres.

- `IdunBattleLogic.Entities.Abilities.Triggered.Loki.MasterOfTheTutelaries_SummonAbility$$CreateBehaviour` (BODY GSHARED, param_3 = token de type — precedent ActOfFaith #151) :
    branche `!=0x20` = `TriggerAbilityDelayed(owner@0x148, 0x495=1173, kind=3)` — le fire INITIAL
      planifie un re-declenchement DIFFERE de LA MEME ability (via `TriggerAbilityDelayedBehaviour.
      IdunBattle.Entities.Behaviours.TriggerAbilityDelayedBehaviour$$Execute`, service de triggers differes) ;
    branche `==0x20` = `IdunBattleLogic.Entities.Abilities.Triggered.Loki.MasterOfTheTutelaries_SummonAbility$$CreateSummonBehaviour` — le REVEIL differe (ctx 0x20 octets)
      execute le spawn reel du Screamer.
  Les DEUX branches sont vivantes ici (self-delayed : initial -> differe -> spawn), contrairement a
  ActOfFaith ou la branche delayed etait ecartee. Port : le differe kind-3 est COLLAPSE — le spawn
  s'execute inline a la fin du vecteur On(9) (apres l'attaque resolue, meme point d'ordre observable) ;
  l'ordre exact vs d'AUTRES triggers On(9) de la meme attaque = RESIDU (a confronter au stream live).

- Spawn (mirror détaillé : `SpawnUnitOperation.execute_master_of_tutelaries_screamer`, spawn.py) :
  possible = CanAddUnit(AdjacentTiles(owner)) (`IdunBattleLogic.Entities.Abilities.Triggered.Loki.MasterOfTheTutelaries_SummonAbility$$GetPossibleSummonTiles`) ; preferred =
  `TilesUnitCanAttackFrom(possible, owner, "thousSmnScreamer").Otherwise(possible)`
  (`IdunBattleLogic.Entities.Abilities.Triggered.Loki.MasterOfTheTutelaries_SummonAbility$$GetPreferredSummonTiles` — Screamer melee => tuiles a ennemi adjacent) ; PickRandomly(1) ;
  RemoveEffect(0x425=1061 GeminaeSuperia_JustSummonedEffect) prealable (no-op offline) ; stats
  `WithStatsFromConfig2(config 1096)` = summonHp_2/summonDmg_2 (mesure live : 4487 = 2493 x 180%) ;
  on-appearance `PerformAIAttackFromCurrentPosition` (melee Power 3 hits — QUI RE-DECLENCHE 1173 si le
  Screamer est adjacent a Abraxas, via son bonus InfernalPacts Psychic ; cf. en-tete).
"""
from __future__ import annotations

from typing import Optional

from .....entities.effect_type import EffectType
from .....entities.damage_profile_type import DamageProfileType
from .....dsl.event_trigger_type import EventTriggerType
from ....state import State
from ....components import UnitComponent, OwnerComponent, StatsComponent
from ..base import EffectTrigger, TriggerEvent

MASTER_EFFECT = int(EffectType.MasterOfTheTutelaries)        # 1197 (0x4ad) — effet armeur
_PSYCHIC = DamageProfileType(13).name                        # "Psychic" — profil du gate (0xd)
_STEPPABLE_TRAITS = {"Steppable", "Decoy"}                   # IsObjectOrSteppable (unites-token)


class MasterOfTheTutelariesSummonAbility(EffectTrigger):
    """`MasterOfTheTutelaries_SummonAbility` (triggered 1173) — cf. en-tete de module pour l'arbre
    natif. Enregistre dans `EFFECT_TRIGGERS[1197]` : instancie UNIQUEMENT tant que l'effet 1197 est
    ACTIF sur le porteur (mirror AddTriggeredAbility/RemoveTriggeredAbility + HasEffect du trigger)."""
    event_id = int(EventTriggerType.Attack)                  # On(9, 1) — fin de CHAQUE attaque
    effect_type = MASTER_EFFECT                              # 1197

    def matches(self, state: State, ev: TriggerEvent) -> bool:
        # HasEffect(owner, 1197) : implicite par la collecte EFFECT_TRIGGERS (l'effet est actif).
        tgt = ev.target_id
        if tgt is None or tgt == self.owner_id:
            return False
        # AreEnemies(owner@0x148, target@0x178) — la cible de l'attaque est un ennemi du porteur.
        owner = state.get_entity(self.owner_id)
        te = state.get_entity(tgt)
        ooc = owner.get_component(OwnerComponent) if owner is not None else None
        toc = te.get_component(OwnerComponent) if te is not None else None
        if ooc is None or toc is None or ooc.team == toc.team:
            return False
        # Not(IsObjectOrSteppable(target)) : vraie unite — pas d'entite sans UnitComponent (objet)
        # ni token steppable/decoy (traits gameconfig Steppable/Decoy).
        tuc = te.get_component(UnitComponent)
        if tuc is None:
            return False
        tsc = te.get_component(StatsComponent)
        t_traits = set(getattr(tsc.ctx, "traits", None) or ()) if tsc is not None else set()
        if t_traits & _STEPPABLE_TRAITS:
            return False
        # CurrentAttackDamageProfilesContain(Psychic=13) : le SET des profils de TOUTE l'attaque —
        # arme + bonus-hits #179. TRANCHE live (diag 202c, runner 183) : l'attaque MELEE Physical du
        # Horror / Power du Screamer + bonus InfernalPacts Psychic QUALIFIE (le bonus est DANS le set)
        # -> chaine Horror -> Screamer -> Screamer tant que les positions le permettent. `ev.profiles`
        # (threade par les vecteurs) ; fallback {ev.profile} si non threade.
        profs = ev.profiles if ev.profiles else ({ev.profile} if ev.profile else set())
        return _PSYCHIC in profs

    def execute_behaviour(self, state: State, ev: TriggerEvent) -> Optional[dict]:
        # `TriggerAbilityDelayed(owner, 1173, kind=3)` -> reveil differe -> `CreateSummonBehaviour` :
        # collapse inline (cf. en-tete — le spawn s'execute apres la resolution de l'attaque, ce
        # vecteur etant dispatche a FinishAttack ; ordre intra-On(9) = residu).
        from ...spawn import SpawnUnitOperation
        spawned = SpawnUnitOperation.execute_master_of_tutelaries_screamer(state, self.owner_id)
        if not spawned:
            return None                                      # aucune tuile libre adjacente -> no-op
        out = {"type": "master_of_tutelaries_screamer", "owner": int(self.owner_id),
               "spawned": spawned}
        # on-appearance `PerformAIAttackFromCurrentPosition` (SpawnUnitOptions+0x18 du Spawn natif) :
        # melee Power 3 hits si ennemi adjacent — son propre vecteur after-attack est dispatche par
        # le helper : si le Screamer est ADJACENT a Abraxas, son attaque porte le bonus InfernalPacts
        # PSYCHIC -> re-qualifie -> Screamer suivant (chaine mesuree live, bornee par les positions).
        from ....abilities.loki.summon import perform_ai_attack_from_current_position
        attacks = []
        for sid in spawned:
            att = perform_ai_attack_from_current_position(state, sid)
            if att is not None:
                attacks.append(att)
        out["attacks"] = attacks
        return out
