"""Coeur du dispatch : collecte des triggers portes et evaluation d'un `TriggerEvent`,
extraits de `triggers/dispatch.py` (scission du module >1000 lignes, tache #169 --
deplacement VERBATIM, zero changement de comportement).

  - `collect_triggered_abilities` / `collect_effect_triggers` : mirror du registre
    `AbilityAndEffectCache` (volets ability-trigger et effet-trigger) ;
  - `evaluate_trigger_operation` : le point de passage de TOUS les vecteurs d'event ;
  - `_trigger_phase_component` : le composant de phase du porteur."""
from __future__ import annotations

from typing import Optional

from .....dsl.event_trigger_type import EventTriggerType
from ....state import State
from ....components import StatsComponent, UnitComponent, TriggeredAbilityComponent
from ..base import TriggerEvent, TriggeredAbility, EffectTrigger, PHASE_TRIGGER_CAP
from .registry import (TRAIT_TRIGGERS, ABILITY_TRIGGERS, ACTIVE_ABILITY_TRIGGERS,
                       RELIC_ABILITY_TRIGGERS, EFFECT_TRIGGERS)


def collect_triggered_abilities(state: State) -> list[TriggeredAbility]:
    """Mirror du registre `AbilityAndEffectCache` (volet ability-trigger) : itère TOUTES les entités et,
    pour chaque trait à trigger porté, instancie l'ability correspondante (owner = l'entité). (Le volet
    effet-trigger — Overwatch, on-hit — n'est pas encore collecté ici.)

    CINQ chemins de registration, tous mirrors de `IdunBattle.Entities.Factories.UnitFactory$$Add*
    Abilities` : trait, passiveAbility, activeAbility (dérivée), relicAbility EN DUR (gameconfig) et
    -- depuis #357 -- l'item RELIQUE ÉQUIPÉ (`UnitConfiguration.TertiaryAbility`, cf. plus bas)."""
    import gameconfig as GC
    from ...behaviour import BEHAVIOUR_TRAIT_TRIGGERS            # lazy : evite circular import behaviour<->triggers
    out: list[TriggeredAbility] = []
    for eid, e in state.entities.items():
        sc = e.get_component(StatsComponent)
        if sc is None:
            continue
        for trait in (sc.ctx.traits or []):
            for cls in TRAIT_TRIGGERS.get(trait, ()):            # un trait peut accorder >1 trigger
                out.append(cls(eid))
            for cls in BEHAVIOUR_TRAIT_TRIGGERS.get(trait, ()):  # mecaniques de comportement (Battle Fatigue)
                out.append(cls(eid))
        # passiveAbilities (TheBetrayer…) — résolues via gameconfig par visualId.
        vid = getattr(sc.ctx, "visual_id", None)
        relics: list[str] = []
        if vid:
            gu = GC.unit(vid) or {}
            for pa in (gu.get("passiveAbilities") or []):
                for cls in ABILITY_TRIGGERS.get(pa, ()):
                    out.append(cls(eid))
            # activeAbilities -> triggered-abilities DERIVEES (`StaticBattleRules.ActiveAbility$$
            # GetDerivedTriggeredAbilities`) : porté dès l'init de l'unité, sans cast préalable.
            for aa in (gu.get("activeAbilities") or []):
                for cls in ACTIVE_ABILITY_TRIGGERS.get(aa, ()):
                    out.append(cls(eid))
            # relicAbilities -> triggered-ability(s) accordee(s) par une RELIQUE cablee EN DUR sur
            # l'unite (#317). QUATRIEME chemin de registration ; les 25 abilities dans ce cas sont
            # TOUTES sur des npc.
            relics = list(gu.get("relicAbilities") or [])
        # CINQUIEME chemin (#357) : l'item RELIQUE **EQUIPE**, `UnitConfiguration.TertiaryAbility`
        # (+0xb0). C'est la branche TERTIAIRE d'`IdunBattle.Entities.Factories.UnitFactory$$
        # AddConfiguredAbilities` : `if (config.TertiaryAbility.HasValue) TriggeredAbilityComponent
        # $$TryAdd(id, tertiaryAbilityState, 3)`. Etat JOUEUR, invisible du gameconfig -- d'ou un
        # canal PROPRE (`snapshot._load_tertiary_abilities`, RPC `unitAbilityStates`) et non une
        # derivation -- ON PAR DEFAUT depuis #363 (transport ambiant lie par le harnais). Sans ce
        # canal (State nu, capture rejouee hors harnais live, ou `ability_states=False`),
        # `tertiary_ability` vaut None et cette branche est un no-op : le comportement d'avant.
        # DEDUPLICATION -- le natif TryAdd sur une `KeyedCollection` indexee par l'ability-type :
        # monter DEUX FOIS la meme ability n'ajoute qu'UNE entree. Un npc qui porte la relique en dur
        # ET se la voit equipee (montage synthetique) ne doit donc etre inscrit qu'une fois.
        tertiary = getattr(sc.ctx, "tertiary_ability", None)
        if tertiary and tertiary not in relics:
            relics.append(tertiary)
        for ra in relics:
            for cls in RELIC_ABILITY_TRIGGERS.get(ra, ()):
                out.append(cls(eid))
    return out


def collect_global_triggers() -> list[TriggeredAbility]:
    """Volet GLOBAL du registre : les abilities `IdunBattleLogic.Entities.Abilities.Damage.Loki.*`,
    inscrites UNE SEULE FOIS pour la bataille et non par entité.

    Leur `CreateTrigger` ne porte AUCUN prédicat d'owner -- il ne teste que le PROFIL du coup :
        IdunBattleLogic.Entities.Abilities.Damage.Loki.OnFireDamageAbility$$CreateTrigger
            On(0x10, 1) & DamageProfileHasTrait(1 = OnFire)  & !TriggeringEffectIs(5)
        IdunBattleLogic.Entities.Abilities.Damage.Loki.OnToxicDamageAbility$$CreateTrigger
            On(0x10, 1) & DamageProfileHasTrait(4 = OnToxic) & !TriggeringEffectIs(0x4dc)
    Elles se déclenchent donc pour N'IMPORTE QUEL attaquant dont le coup porte le trait, ce qui est
    exactement ce qu'un registre par-entité ne sait pas exprimer.

    CARDINALITE -- l'inscription est UNIQUE, et c'est une MESURE, pas une hypothèse : le canal 1203
    consomme EXACTEMENT un `NextBool` par série de coups en live (`test_on_toxic_damage_live.py`,
    oracle = l'état MT). Une inscription par unité en consommerait un PAR unité du plateau.
    RESIDU DOCUMENTE : le SITE natif de cette inscription unique n'est pas RE'd
    (`IdunBattleLogic.Core.Services.Caches.AbilityAndEffectCache$$AddEntity` n'ajoute que les
    abilities PORTEES par l'entité) ; c'est la cardinalité observée qui fonde ce registre."""
    from .registry import GLOBAL_TRIGGERS
    return [cls(None) for cls in GLOBAL_TRIGGERS]


def collect_effect_triggers(state: State) -> list[EffectTrigger]:
    """Mirror du registre `AbilityAndEffectCache` (volet effet-trigger) : itère les effets ACTIFS portés
    par chaque unité (via `state.effects`) et, pour chaque effet d'un type enregistré, instancie son
    effet-trigger (owner = le porteur). No-op si `state.effects` absent."""
    out: list[EffectTrigger] = []
    eff = getattr(state, "effects", None)
    if eff is None:
        return out
    for uid, effs in eff.by_unit.items():
        for e in effs:
            if e.consumed:
                continue
            for cls in EFFECT_TRIGGERS.get(e.effect_type, ()):   # ArraySet natif : N triggers par effet
                out.append(cls(int(uid)))
    return out


def evaluate_trigger_operation(state: State, ev: TriggerEvent) -> list[dict]:
    """Mirror COLLAPSÉ du PUMP FIFO natif (#201) — `IdunBattle.Operations.EvaluateTriggerOperation$$ExecuteInternal`
    (dispatch) + `IdunBattle.Messages.InputMessageProcessor$$ProcessPendingTriggeredAbilities` (drain) + `IdunBattle.Messages.InputMessageProcessor$$RunPhase(0xf)`
    (item) + `IdunBattle.Messages.InputMessageProcessor$$VerifyDeaths` (retrait-des-morts entre items), fondus en UNE boucle.

    Structure native (RE) :
      1. `ExecuteInternal` : itère le registre GLOBAL `AbilityAndEffectCache` (composant #3 = triggers de
         CET event) → `EvaluateAbilityOrEffectTrigger` par entrée → **ENFILE** un pending triggered-ability
         (file #5) — il n'EXÉCUTE PAS inline.
      2. `ProcessPendingTriggeredAbilities` : **SNAPSHOT** la file #5 dans une List + **`Queue.Clear`**, puis
         `foreach` item → `RunPhase(0xf, item)`. Chaque `RunPhase` = callback (le behaviour de l'item) PUIS
         `VerifyDeaths` PUIS `ProcessDamageEvents` PUIS `ProcessPendingTriggeredAbilities` (cascade imbriquée).
         => les morts causées par l'item N sont RETIRÉES avant l'item N+1.

    Collapse du port (équivalent observable, sans machinerie de file) :
      - `registry` = liste MATÉRIALISÉE une fois = le SNAPSHOT (mirror du snapshot+Clear : les effets/traits
        ajoutés PENDANT le drain n'entrent pas dans CE registre).
      - la boucle draine le snapshot en ordre FIFO ; le **re-appel de `matches` par item** (contre l'état
        COURANT) = la re-validation de cible du `RunPhase(0xf)` (un item tué par un item antérieur ne matche
        plus — cf. la leg target-validity `OverwatchAutoAttack.matches`, alive du mover).
      - les morts sont appliquées **INLINE** par `_fire_death_if_killed` (alive=False + `after_death_triggers`
        LIFO) DANS `execute_behaviour` = le `VerifyDeaths`-entre-items (la victime est morte avant l'entrée
        suivante). Équivalent au pump pour la cascade prouvée #201 (overwatch kill-cancel) ; une vraie file
        pending explicite (ordre snapshot-clear multi-rounds) n'ajoute AUCUN effet observable ici → non portée
        (blast-radius/ordre RNG) tant qu'aucune divergence ne l'exige.

    Gates par entrée : `event_id` écouté → `CanGet*Trigger` (owner VIVANT sauf fire-on-death ;
    triggers-disabled non porté) → cap-phase (`<0x33`, ability-triggers) → `matches` → behaviour.
    Renvoie la liste des résultats (diagnostic)."""
    out: list[dict] = []
    registry = (collect_triggered_abilities(state) + collect_global_triggers()
                + collect_effect_triggers(state))
    for entry in registry:
        # Un tile-effect écoute souvent PLUSIEURS events (`event_ids`) ; sinon `event_id` unique.
        if entry.event_id != ev.event_id and ev.event_id not in getattr(entry, "event_ids", ()):
            continue
        if getattr(entry, "owner_is_tile", False) or getattr(entry, "owner_is_global", False):
            pass                                           # owner = TUILE ou AUCUN : pas de gate alive
        else:
            owner = state.get_entity(entry.owner_id)
            if owner is None:
                continue
            uc = owner.get_component(UnitComponent)        # CanGet*Trigger : owner unit vivant
            if uc is not None and not uc.alive and not getattr(entry, "fire_on_death", False):
                continue                                   # sauf ability fire-on-death (ex. FinalJustice)
        if not entry.matches(state, ev):
            continue
        # #140 : CAP phase-triggers (mirror IdunBattle.Operations.EvaluateTriggerOperation$$EvaluateAbilityTrigger : GetTimesTriggeredThisPhase
        # < 0x33). S'applique aux ability-triggers (TriggeredAbility) — les effet-triggers passent par
        # EvaluateEffectTrigger (sans ce cap). Borne l'auto-récursion (splash Psyker qui re-déclenche le
        # splash Psyker via le vecteur after-hit). Clé = type d'ability-trigger (1 par trait-trigger).
        # `mark_as_triggered` AVANT le behaviour → la récursion voit le compteur incrémenté.
        # Le cap est PAR OWNER (`TriggeredAbilityComponent` de l'unité porteuse) -> il ne s'applique
        # ni aux tile-effects ni aux abilities GLOBALES (`owner_id is None`, aucun composant à porter).
        if (isinstance(entry, TriggeredAbility) and not getattr(entry, "owner_is_tile", False)
                and not getattr(entry, "owner_is_global", False)):
            tac = _trigger_phase_component(state, entry.owner_id)
            if tac is not None:
                pkey = type(entry).__name__
                tac.try_add(pkey)                                       # peuplement paresseux (idempotent)
                if tac.get_times_triggered_this_phase(pkey) >= PHASE_TRIGGER_CAP:
                    continue                                           # cap atteint cette phase → skip
                tac.mark_as_triggered(pkey)
        # `IdunBattle.Entities.Abilities.BaseTriggeredAbility$$Execute` ecrit
        # `Nullable<AbilityOrEffect>(ability.Id)` dans le champ **`CurrentAbility`**
        # (`AbilityEntities+0x60`) **AVANT** d'executer le behaviour -> tout ce que le behaviour engendre
        # (attaque, degat, mort) porte cet id, et c'est lui que lit
        # `IdunBattleLogic.Entities.DSLTriggers$$CurrentAbilityIs`. C'est CE moment-la qui est mirrore
        # ici -- foyer UNIQUE du port. La sauvegarde/restauration reproduit l'imbrication native (une
        # triggered-ability declenchee DANS le behaviour d'une autre ecrase le champ pour SA duree, puis
        # rend la main) ; le natif ne fuit pas non plus d'une evaluation a la suivante, chaque
        # `EvaluateTriggerOperation` batissant son propre `AbilityEntities`.
        # ⚠ Le champ natif HOMONYME `TriggeringAbility` (`AbilityEntities+0x98`) est ecrit par la MEME
        # fonction mais **APRES** le behaviour, pour le seul `On(0xd = UnitTriggeredAbility)`. Le nom
        # du champ Python ci-dessous est historique ; sa semantique est celle de `CurrentAbility`
        # (case-292, `docs/rl/case-292-current-vs-triggering-ability.md`). Le SECOND canal (+0x98)
        # est `state.trigger_ability_type`, ecrit juste apres ce bloc (#294).
        prev_trig = getattr(state, "triggering_ability", None)
        if entry.TRIGGERED_ABILITY_ID is not None:
            state.triggering_ability = int(entry.TRIGGERED_ABILITY_ID)
        try:
            r = entry.execute_behaviour(state, ev)
        finally:
            state.triggering_ability = prev_trig
        if r is not None:
            out.append(r)
        _publish_unit_triggered_ability(state, ev, entry)
    return out


def _publish_unit_triggered_ability(state: State, ev: TriggerEvent, entry) -> None:
    """Queue de `IdunBattle.Entities.Abilities.BaseTriggeredAbility$$Execute` — les DEUX gestes que
    le natif pose APRES le retour du behaviour, dans cet ordre (#294) :

        4. `AbilityOrEffect.op_Implicit(this)` -> `Nullable<>..ctor` -> ecrit `entities+0x98`
           (`TriggeringAbility`)
        5. copie de `entities` -> local
        6. `<processor>.Publish(<slot>, ..., 0xd, <la copie>)`
           = `On(0xd = EventTriggerType.UnitTriggeredAbility)`

    C'est le MOMENT D'ECRITURE qui separe `+0x98` de `+0x60`, pas la valeur : la MEME
    `AbilityOrEffect(this.Id)` part dans les deux. `+0x60` est pose AVANT le behaviour (donc herite
    par tout ce qu'il engendre) ; `+0x98` est pose APRES, donc il ne couvre QUE cet `On(0xd)`.

    Consequence, et c'est le regime discriminant : une triggered `B` declenchee PAR cet `On(0xd)`
    ecrit `+0x60 = B` avant SON behaviour, tandis que `+0x98` vaut toujours `A` -- le natif ne le
    reecrit qu'a la fin de `B`. `IdunBattle.Operations.EvaluateTriggerOperation$$PopulateAbilityEntities`
    ne touche ni `+0x60` ni `+0x98` (relu : il n'ecrit que `+0x40`, `+0x48`, `+0x50`), donc les deux
    champs TRAVERSENT l'evaluation imbriquee -> pendant le behaviour de `B`, les deux canaux portent
    DEUX VALEURS NON NULLES DIFFERENTES.

    RESTAURATION : le natif ecrit dans l'`AbilityEntities` de l'appelant (passe par reference) et le
    jette avec l'evaluation ; le port n'a qu'UN canal global, donc il restaure -- meme raisonnement
    et meme geste que pour `+0x60`. Le supprimer FAIT FUIR l'id d'une evaluation a la suivante
    (contre-epreuve `--mutate persist` de `probe_294_trigger_ability_channels.py`).

    EMISSION INCONDITIONNELLE : le natif publie `On(0xd)` a chaque execution de triggered-ability,
    sans gate. Le `TriggerEvent` reprend les champs de `ev` : le natif republie le MEME
    `AbilityEntities` (mute par le behaviour), pas un contexte neuf.

    ⚠ CET EVENEMENT N'A AUCUN CONSOMMATEUR CONNU -- ni porte, ni NATIF. Mesure #294, re-derivable :
    cote port, 86 classes-triggers enregistrees couvrent 37 `event_id` distincts et AUCUNE n'ecoute
    13 ; cote natif, le balayage des voies de construction d'un noeud d'evenement
    (`IdunBattleLogic.Entities.DSLTriggers$$On` et ses deux overloads, `$$OnDeathEvent`,
    `$$OnOwnerSpecificAbilityInit`, `$$OnNormalAttackOrSmite`, `$$OnAttackFromAbility`,
    `IdunBattle.Entities.Effects.BaseEffect$$On`) ne rend AUCUN `CreateTrigger` sur `0xd` -- a
    l'exception declaree de 4 `Env*Ability$$CreateTrigger` dont la liste d'events arrive par
    `RuntimeHelpers.InitializeArray` (blob non lisible depuis Ghidra ; abilities d'environnement,
    hors perimetre confrontable).
    L'emission reste portee malgre ca, pour deux raisons : (a) c'est le mirror -- le natif publie ;
    (b) sans elle le canal `+0x98` est INOBSERVABLE, donc invalidable, donc sans valeur.
    COUT MESURE : sur les 86 classes-triggers du registre, **7** declarent un `TRIGGERED_ABILITY_ID`
    -- les 79 autres sortent d'ici par le `return` ci-dessous. Bout-en-bout,
    `test_death_queue_ordering_live.py` (22 tests) rend 148,43 s AVANT et 147,07 s APRES : le
    surcout est dans le bruit."""
    if entry.TRIGGERED_ABILITY_ID is None:
        return                                          # aucun id a poser -> rien a publier
    # Acces DIRECT, pas `getattr(..., None)` : le slot est declare dans `State.__slots__` et
    # initialise par `State.__init__`. Un objet qui ne l'a pas n'est pas un `State` -> ca doit
    # LEVER, pas dégrader en `None` (un canal absent lu comme « vide » est exactement le mode de
    # panne silencieuse que ce cas documente).
    prev = state.trigger_ability_type
    state.trigger_ability_type = int(entry.TRIGGERED_ABILITY_ID)
    try:
        evaluate_trigger_operation(state, TriggerEvent(
            EventTriggerType.UnitTriggeredAbility, ev.actor_id, ev.target_id,
            ranged=ev.ranged, profile=ev.profile, is_crit=ev.is_crit,
            killer_id=ev.killer_id, dying_id=ev.dying_id, player_id=ev.player_id,
            overkill=ev.overkill, ability_type=ev.ability_type, profiles=ev.profiles,
            triggering_effect=ev.triggering_effect, is_first_hit=ev.is_first_hit,
            triggering_ability=ev.triggering_ability))
    finally:
        state.trigger_ability_type = prev


def _trigger_phase_component(state: State, owner_id: int) -> Optional[TriggeredAbilityComponent]:
    """Get-or-create le `TriggeredAbilityComponent` de l'unité `owner_id` (mirror du composant natif ;
    absent d'une unité spawnée avant #140 → créé paresseusement). None si l'entité n'existe pas."""
    e = state.get_entity(owner_id)
    if e is None:
        return None
    c = e.get_component(TriggeredAbilityComponent)
    if c is None:
        c = TriggeredAbilityComponent()
        e.add_component(c)
    return c
