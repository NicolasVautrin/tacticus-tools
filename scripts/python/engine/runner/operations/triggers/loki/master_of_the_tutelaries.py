"""MasterOfTheTutelaries_Summon (triggered 1173, Abraxas thousInfernalMaster) — #202 tranche C.

Mirror du kit natif `IdunBattleLogic.Entities.Abilities.Triggered.Loki.MasterOfTheTutelaries_SummonAbility`,
ARMEE par l'effet-marqueur 1197 (`MasterOfTheTutelariesEffect`, pose par l'active 1096 — cf.
`effects/loki/status.py` + `EFFECT_TRIGGERS[1197]` dans `../dispatch.py`). La collecte par-effet
PORTE est le vehicule ; le Add/RemoveTriggeredAbility natif d'`IdunBattle.Entities.Effects.Loki.MasterOfTheTutelariesEffect$$ApplyInternal` / `IdunBattle.Entities.Effects.Loki.MasterOfTheTutelariesEffect$$RevertInternal`
est mirrore par le gate d'ACTIVITE en tete de `matches` (#231, `_master_effect_is_carried_and_active`) :
`RevertInternal` s'execute des que l'effet est desactive, parce que
`IdunBattle.Operations.RefreshEffectsOperation$$DeactivateEffect` enchaine sur `UpdateEffectTargets`
avec une liste de cibles VIDE.

- `IdunBattleLogic.Entities.Abilities.Triggered.Loki.MasterOfTheTutelaries_SummonAbility$$CreateTrigger` :
    On(9=Attack, 1)
    & HasEffect(owner@0x148, 0x4ad=1197, onlyActive=0, relation=6=Both)   # PRESENCE seule (cf. #231)
    & AreEnemies(owner@0x148, target@0x178)            # la cible de l'attaque est un ENNEMI du porteur
    & Not(IsObjectOrSteppable(target@0x178))           # vraie unite (ni Steppable 27 ni Object 13)
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

⚠ `NOT IsObjectOrSteppable(target)` A ETE RECOPIE A LA MAIN, ET FAUX, jusqu'au 2026-08-05 : le
module gatait `{Steppable, Decoy}` la ou le natif dit `Steppable | Object`
(`IdunBattleLogic.Entities.DSLTriggers$$IsObjectOrSteppable` = `HasTrait(x, 0x1b=27 Steppable) |
HasTrait(x, 0xd=13 Object)`, decompile LU). `Decoy` = **1053**, `Object` = **13** : deux traits
DISTINCTS de `UnitTrait`. Mesure gameconfig (re-derivee par
`probe_462_..._r1_mot_object_or_steppable.py --step census`) : `Decoy` sans `Steppable` = **0**
porteur (le volet retire etait INERTE), `Object` sans `Steppable` = **28** porteurs, tous npc
`LootObj_*` (le TROU). Le conjoint passe desormais par le foyer partage
`entities/triggers.py::is_object_or_steppable`, comme `BattleFatigueAbility` — plus de recopie.
Detail : `docs/rl/case-462-r4b-r1-r1-r1-r1-b-r1-r1-r1-mot-object-or-steppable.md`.
"""
from __future__ import annotations

from typing import Optional

from .....entities.effect_type import EffectType
from .....entities.damage_profile_type import DamageProfileType
from .....entities.selectors.accessors import Target
from .....entities.triggers import is_object_or_steppable
from .....dsl.event_trigger_type import EventTriggerType
from ....abilities.behaviours.context import entities_from_state
from ....state import State
from ....components import UnitComponent, OwnerComponent
from ..base import EffectTrigger, TriggerEvent
from ....abilities.loki.summon import perform_ai_attack_from_current_position
from ...spawn import SpawnUnitOperation

MASTER_EFFECT = int(EffectType.MasterOfTheTutelaries)        # 1197 (0x4ad) — effet armeur
_PSYCHIC = DamageProfileType.Psychic.name                        # "Psychic" — profil du gate (0xd)
# 4e conjoint : `NOT IsObjectOrSteppable(target@0x178 = sel@+0x60)`. Foyer partage
# `entities/triggers.py` (mirror de `IdunBattleLogic.Entities.DSLTriggers$$IsObjectOrSteppable`,
# HUIT call-sites natifs) — surtout pas une n-ieme recopie du couple de traits.
_IS_OBJECT_OR_STEPPABLE = is_object_or_steppable(Target())


def _master_of_tutelaries_instances(state: State, owner_id: int) -> list:
    """Les instances d'effet 1197 NON consommees portees par `owner_id`. Liste (et non instance
    unique) parce que le natif raisonne PAR ENTITE-EFFET ; en pratique `AddEffectOperation` no-ope
    sur un meme-type deja present, donc il y en a 0 ou 1. [] si l'etat n'a pas d'`EffectsState`."""
    if state.effects is None:
        return []
    return [e for e in state.effects.by_unit.get(int(owner_id), [])
            if not e.consumed and e.effect_type == MASTER_EFFECT]


def _master_effect_is_carried_and_active(state: State, owner_id: int) -> bool:
    """Gate d'entree du trigger 1173 (#231). Il porte DEUX faits natifs DISTINCTS, qui se lisent sur
    la meme liste d'instances mais ne viennent PAS du meme artefact — les confondre serait une
    infidelite dans un sens comme dans l'autre :

    1. PRESENCE — le conjoint `HasEffect(owner@0x148, 0x4ad, onlyActive=0, relation=6)` de
       `IdunBattleLogic.Entities.Abilities.Triggered.Loki.MasterOfTheTutelaries_SummonAbility$$
       CreateTrigger`. Le 4e argument de `IdunBattleLogic.Entities.DSLTriggers$$HasEffect` est
       `onlyActive`, et il vaut **0** ici : le noeud de l'arbre ne teste QUE la presence. (Semantique
       lue, pas deduite : `IdunBattle.Entities.EntityExtensions$$IsOwnerOfEffect` ne saute une
       entite-effet — `continue` sur `IsActive@0x5c == 0` — que si ce bool est vrai.) Le `6` est un
       masque de relation decode par `IdunBattle.Entities.EntityExtensions$$HasOneOfEffects`
       (`&2` -> `IsOwnerOfOneOfEffects`, `&4` -> `IsTargetOfOneOfEffects`) = Both.
       => aucune instance : False.

    2. PORTAGE — la triggered 1173 n'est pas un effet-trigger du rail `CreateTargetTrigger` : c'est
       une triggered-ability portee par l'UNITE, ajoutee par
       `IdunBattle.Entities.Effects.Loki.MasterOfTheTutelariesEffect$$ApplyInternal`
       (`IdunBattleLogic.Entities.DSLBehaviors$$AddTriggeredAbility(Entity(target), 0x495)`) et RETIREE par
       `IdunBattle.Entities.Effects.Loki.MasterOfTheTutelariesEffect$$RevertInternal`
       (`IdunBattleLogic.Entities.DSLBehaviors$$RemoveTriggeredAbility(Entity(target), 0x495)`). Or desactiver l'effet REVERTE
       ses cibles : `IdunBattle.Operations.RefreshEffectsOperation$$DeactivateEffect` ecrit
       `EffectComponent.IsActive @+0x5c = 0` PUIS appelle
       `IdunBattle.Operations.RefreshEffectsOperation$$UpdateEffectTargets` avec une liste de
       nouvelles cibles **VIDE** -> `GetTargetsToRemove` rend toutes les cibles courantes ->
       `IdunBattle.Operations.RefreshEffectsOperation$$RemoveTargetsFromEffect` -> `Revert`.
       => effet 1197 INACTIF <=> triggered 1173 absente de l'unite <=> aucun Screamer.
       C'est ce couplage que mirroire `any(e.active ...)`, PAS un `onlyActive` (qui vaut 0).

    ⚠ #231-r1 -- << LE PORT PERSISTE 1173 TOUR APRES TOUR >> EST REFUTE, ET C'EST LE DECOMPILE QUI
    LE REFUTE. Le residu opposait le releve live de `case-546` Sec.6.2 (`initial=1 remaining=0
    removed=True`, annonce POST-CAST) au comportement du port. Or ce couple ne peut PAS venir du
    retrait : `IdunBattle.Operations.RemoveEffectOperation$$Execute` ecrit `<+0x5e> = 1`
    (beingRemoved), retire l'id des listes, puis `<+0x5c> = 0` et `<+0x5f> = 1` -- il **n'ecrit
    JAMAIS `Duration@+0x64`**. Le SEUL ecrivain decroissant est
    `IdunBattle.Entities.Components.EffectComponent$$RemoveOneTurn` (`if (0 < Duration) Duration -=
    1`), enfile par `IdunBattle.Operations.EndTurnOperation$$RefreshEffects`. Donc `remaining = 0`
    atteste qu'un END-TURN a eu lieu avant le releve -- et cote port le MEME end-turn consomme
    l'instance (`EffectsState.on_turn_end` : `1 -> 0` puis `consumed`), ce qui ferme ce gate.
    MESURE offline, avec son contre-bras et sa contre-epreuve :
    `tests/engine/runner/test_231r1_master_tutelaries_expiry_offline.py`.
    RESTE NON OBSERVE (et `case-546` Sec.8 le dit deja de son cote) : la fenetre INTRA-TOUR, entre
    la pose et le premier end-turn. Il faudrait un `effectsAll --effectType 1197` pris AVANT tout
    end-turn pour la trancher.

    ⚠ Ce gate est propre au rail APPLY_REVERT : il ne remonte PAS dans `collect_effect_triggers`,
    qui doit continuer a ne filtrer que `consumed`. Gater la COLLECTE eteindrait les `Triggered()`
    d'activation du rail ArraySet (evalues par
    `IdunBattle.Operations.EvaluateTriggerOperation$$EvaluateEffectTriggerEffectAbilities`, qui
    n'applique AUCUN gate `IsActive`) — ce sont eux qui RALLUMENT un effet eteint."""
    insts = _master_of_tutelaries_instances(state, owner_id)
    return bool(insts) and any(e.active for e in insts)


class MasterOfTheTutelariesSummonAbility(EffectTrigger):
    """`MasterOfTheTutelaries_SummonAbility` (triggered 1173) — cf. en-tete de module pour l'arbre
    natif. Enregistree dans `EFFECT_TRIGGERS[1197]`, qui sert de VEHICULE DE COLLECTE (« une instance
    1197 est portee »), et non de gate : la collecte ne filtre que `consumed`. Le gate d'activite
    — mirror de `AddTriggeredAbility`/`RemoveTriggeredAbility` pilotes par la (des)activation de
    l'effet — est porte EXPLICITEMENT en tete de `matches` (#231)."""
    event_id = int(EventTriggerType.Attack)                  # On(9, 1) — fin de CHAQUE attaque
    effect_type = MASTER_EFFECT                              # 1197

    def matches(self, state: State, ev: TriggerEvent) -> bool:
        # `HasEffect(owner@0x148, 0x4ad, onlyActive=0, Both)` + le portage Apply/Revert de la
        # triggered 1173 (#231 — cf. `_master_effect_is_carried_and_active`). Ce gate etait
        # AUPARAVANT suppose « implicite par la collecte EFFECT_TRIGGERS » : c'etait FAUX,
        # `collect_effect_triggers` ne filtre que `consumed`, jamais `e.active` (et c'est voulu —
        # le rail ArraySet doit pouvoir re-activer). Une instance 1197 INERTE (seedee par le canal
        # `includeInactive`, cf. `snapshot.decision_view_seed_body`) faisait donc spawner offline un
        # Screamer que le natif ne peut pas produire, l'ability ayant ete RemoveTriggeredAbility'ee.
        if not _master_effect_is_carried_and_active(state, self.owner_id):
            return False
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
        # GARDE DE PORT (pas un conjoint natif) : la cible doit etre une entite-UNITE de l'ECS.
        # INERTE en pratique — les six sites qui creent une entite (`snapshot.load_state` x2,
        # `operations/spawn.py` x4, `components.py`) posent TOUS un `UnitComponent`. Elle etait
        # AUPARAVANT presentee comme une part d'`IsObjectOrSteppable` (« objet = pas de
        # UnitComponent »), ce qui est faux : le natif ne teste que des TRAITS.
        if te.get_component(UnitComponent) is None:
            return False
        # `NOT IsObjectOrSteppable(target@0x178)` — 4e conjoint, par le FOYER (cf. en-tete). Le
        # `matches` est imperatif, donc on materialise ici l'`AbilityEntities` que le natif tient
        # pour tout l'arbre : `entities_from_state(state, owner, target)` pose `Target()` sur la
        # cible de l'attaque, exactement le `sel@+0x60` du decompile.
        entities = entities_from_state(state, self.owner_id, tgt)
        if _IS_OBJECT_OR_STEPPABLE.should_trigger(entities):
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
        spawned = SpawnUnitOperation.execute_master_of_tutelaries_screamer(state, self.owner_id)
        if not spawned:
            return None                                      # aucune tuile libre adjacente -> no-op
        out = {"type": "master_of_tutelaries_screamer", "owner": int(self.owner_id),
               "spawned": spawned}
        # on-appearance `PerformAIAttackFromCurrentPosition` (SpawnUnitOptions+0x18 du Spawn natif) :
        # melee Power 3 hits si ennemi adjacent — son propre vecteur after-attack est dispatche par
        # le helper : si le Screamer est ADJACENT a Abraxas, son attaque porte le bonus InfernalPacts
        # PSYCHIC -> re-qualifie -> Screamer suivant (chaine mesuree live, bornee par les positions).
        attacks = []
        for sid in spawned:
            att = perform_ai_attack_from_current_position(state, sid)
            if att is not None:
                attacks.append(att)
        out["attacks"] = attacks
        return out
