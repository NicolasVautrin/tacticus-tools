"""FRAMEWORK de trigger du port + sélecteurs DSL nommés (leaf : aucun import de sibling).

Porte les types de base côté port de la couche trigger (`AbilityTrigger`/`EffectTrigger` natifs +
l'abstraction TUILE) et les **sélecteurs DSL** partagés par toutes les classes concrètes (mirror
`DSLFactory.*` : `IsInAttackRange`, `IsRangedAttack`, `PickRandomAmountSelector`, adjacence/faction).
Le DISPATCH (`IdunBattle.Operations.EvaluateTriggerOperation`) vit dans `dispatch.py` ; les classes
concrètes dans `loki.py` (`Abilities.{Active,Triggered,Damage}.Loki.*`), `tiles.py` (`Abilities.Tiles.*`)
et `effect_triggers.py` (`Entities.Effects.*`)."""
from __future__ import annotations

from typing import Optional

from ...state import State
from ...components import StatsComponent, OwnerComponent, PositionComponent, UnitComponent
from ...abilities.loki.splash import _pick_randomly_n
from ...abilities.targeting import unit_weapon_range
# FORME B (`import <module>` puis `<module>.<nom>`) et non `from ... import attack_range_type` : un
# binding de module n'est jamais gele, donc un `monkeypatch.setattr("engine.services.battle_query.
# attack_range_type", ...)` mord (cf. CLAUDE.md, les 28 fichiers rouges de #484). Differe -> hisse :
# classe GRATUIT (charger `engine.services.battle_query` seul en process frais ne tire PAS ce
# module-ci), donc aucun cycle a fermer.
from ....services import battle_query as _svc_bq

# --- Cap phase-triggers (#140) --------------------------------------------------------------------
PHASE_TRIGGER_CAP = 0x33         # 51 — `IdunBattle.Operations.EvaluateTriggerOperation$$EvaluateAbilityTrigger : GetTimesTriggeredThisPhase < 0x33.
                                 # Borne native (par PHASE = une activation ; ResetPhase à EndPhaseOperation) de
                                 # la ré-entrance d'un ability-trigger générateur d'attaque. GARDE-FOU générique :
                                 # depuis le fix #147, Psyker ne s'auto-déclenche plus (splash = after-hit `On(8)`,
                                 # PAS NormalAttack `On(0x26)`) → le cap n'est plus atteint par Psyker, mais reste
                                 # porté fidèlement (borne toute future ability-trigger récursive).


class TriggerEvent:
    """Contexte d'événement de trigger (sous-ensemble de l'`AbilityEntities` natif). `actor_id` = acteur de
    l'action (attaquant) ; `target_id` = cible primaire. Pour un événement MORT (`On(1)`), `killer_id` (slot
    0x158) = l'auteur du coup fatal, `dying_id` (slot 0x178) = l'unité qui meurt (actor/target les reflètent
    aussi pour rester compatibles avec le dispatch générique)."""
    __slots__ = ("event_id", "actor_id", "target_id", "ranged", "profile", "is_crit",
                 "killer_id", "dying_id", "player_id", "overkill", "ability_type", "profiles",
                 "triggering_effect", "is_first_hit", "triggering_ability", "dest_tile",
                 "health_damage", "was_block", "is_normal_attack", "movement_steps",
                 "attack_used_attack_damage", "is_first_damaging_hit")

    def __init__(self, event_id: int, actor_id: int, target_id: int, *,
                 ranged: bool, profile: Optional[str], is_crit: bool = False,
                 killer_id: Optional[int] = None, dying_id: Optional[int] = None,
                 player_id: Optional[int] = None, overkill: bool = False,
                 ability_type: Optional[int] = None, profiles=None,
                 triggering_effect: Optional[int] = None,
                 is_first_hit: Optional[bool] = None,
                 triggering_ability: Optional[int] = None,
                 dest_tile=None,
                 health_damage: Optional[int] = None, was_block: Optional[bool] = None,
                 is_normal_attack: Optional[bool] = None,
                 movement_steps: Optional[int] = None,
                 attack_used_attack_damage: Optional[bool] = None,
                 is_first_damaging_hit: Optional[bool] = None):
        self.event_id = event_id
        self.actor_id = actor_id
        self.target_id = target_id
        self.ranged = ranged
        self.profile = profile
        self.is_crit = is_crit
        # `IsNormalAttack(CurrentAbility@DSLSelectors+0x88)` -- la nature du VECTEUR d'attaque, telle
        # que la facade la resout deja pour `attack_hits_with_modifiers` (attaque normale vs attaque
        # d'ABILITY). TRI-ETAT : `None` = non threadee sur cet event, et le consommateur doit alors
        # se TAIRE plutot que supposer. Consommateur : le target-trigger de
        # `LegendaryCommander_ExtraHits`, dont le predicat porte `!IsNormalAttack`.
        self.is_normal_attack = is_normal_attack
        # `AbilityEntities+0x11c` = **`movementSteps`** (nom LU verbatim dans la signature du ctor a
        # 33 parametres d'`IdunBattle.Entities.Abilities.AbilityEntities$$.ctor`, 30e parametre
        # nomme). C'est le canal UNIQUE de la formule `IdunBattleLogic.Entities.DSLFormulas$$
        # MovementSteps()`, dont le `Calculate` a pour corps ENTIER :
        #     `IdunBattle.DSL.MovementStepFormula$$Calculate` = Nullable<int>.GetValueOrDefault(
        #                                                            entities+0x11c)
        # `None` cote port = le `Nullable` VIDE du natif -> les lecteurs doivent rendre **0**, pas se
        # taire : `GetValueOrDefault()` n'a pas de tri-etat, et 0 fait echouer tout gate
        # `AmountIsEqualOrGreater(MovementSteps(), N>0)`. C'est FIDELE, pas une degradation.
        # SEUL emetteur qui le renseigne : `IdunBattle.Operations.MoveUnitOperation$$
        # EvaluateAfterMoveTriggers` (donc `On(0x24)`/`On(4)`/`On(0x1d)` d'un MOUVEMENT). Le
        # pre-move `On(0x1f)`, `IdunBattle.Operations.DisplaceUnitOperation$$
        # EventAndAbilitiesAndEffects` (push) et `IdunBattle.Operations.ReviveUnitOperation$$
        # SetRevivePosition` le laissent NUL -- lu au decompile, argument 30 = 0 aux trois sites.
        self.movement_steps = movement_steps
        self.killer_id = killer_id
        self.dying_id = dying_id
        self.player_id = player_id          # tour DÉBUTÉ (event turn-start On(0x16)) — owner doit appartenir
        self.overkill = overkill            # mort par OVERKILL (dmg >= 2*PV) — gate de FinalJustice
        self.ability_type = ability_type    # AbilityOrEffect du coup (mirror du payload d'event natif lu par
                                            # DirectAbilitySelector, ex. 0x3f5=1013 kind « attaque-normale »
                                            # du smite Psyker — gate branche 2 LordOfTempests AddIce #35).
                                            # None = kind inconnu/non threadé (aucun gate kind ne fire).
        # `CurrentAttackDamageProfilesContain` (#202-C) : le SET des profils de TOUTE l'attaque —
        # profil d'arme + profils des sous-operations bonus (#179 InfernalPacts : MESURE live, une
        # attaque melee Physical/Power + bonus Psychic QUALIFIE le trigger 1173). None = non threadé
        # (les consommateurs retombent sur {profile}).
        self.profiles = set(profiles) if profiles else None
        # `TriggeringEffectIs(effectType)` : le canal `AbilityEntities+0x98` (`TriggeringAbility`).
        # `IdunBattleLogic.Entities.DSLTriggers$$TriggeringEffectIs` prend le slot `DSLSelectors+0x90`
        # -- LE MEME que `$$TriggeringAbilityIs` et `$$TriggeringAbilityIsNone` -- et ce slot porte
        # `AbilityTypeSelector.TriggeringAbilitySelector`, dont le `Select` est une copie plate de
        # `+0x98/+0xa0/+0xa8/+0xb0`. `CurrentAbilityIs`, lui, prend `DSLSelectors+0x88` ->
        # `CurrentAbilitySelector` -> `+0x60/+0x68/+0x70/+0x78` (= `self.triggering_ability`).
        # None = ce canal est VIDE sur l'evenement.
        # Consommateur : branche 2 de
        # `IdunBattleLogic.Entities.Abilities.Triggered.Loki.TerrifyingCrescendoAbility$$CreateTrigger`
        # (`On(0x3d = 61 PreEffectAdded) & OwnerIsActor & TriggeringEffectIs(0x429 = Pinned)`).
        #
        # SUR LES VECTEURS D'EFFET, LES DEUX CANAUX SONT ASYMETRIQUES (#306, RE re-derivee sur
        # `rnca9r7q6c`) : `IdunBattle.Operations.AddEffectOperation$$Execute` passe DEUX
        # `Nullable<AbilityOrEffect>` bâtis sur le MEME `effectType` au ctor nomme
        # (`currentAbilityOrEffect` -> `+0x60` ET `triggerAbilityOrEffect` -> `+0x98`), alors que
        # `IdunBattle.Operations.RemoveEffectOperation$$Execute` n'appelle AUCUN ctor : apres son
        # `memset(0, 0x128)` il n'ecrit que `+0x10`/`+0x18` (le porteur) et `+0x60..+0x7c`
        # (l'effet retire) -- `+0x98` reste a ZERO (controle negatif fait a l'assembleur).
        # DONC sur `On(63 = PreEffectRemoved)` / `On(64 = EffectRemoved)` / `On(59 =
        # UnitBecameTargetable)` : `TriggeringEffectIs` et `TriggeringAbilityIs` sont TOUJOURS FAUX,
        # `TriggeringAbilityIsNone` est VRAI, et c'est **`CurrentAbilityIs` qui porte l'effet
        # retire**. Foyer porte des deux sens : `dispatch/move_death.py::_effect_vector_triggers`.
        self.triggering_effect = triggering_effect
        # `IsFirstHitInSeries` (`IdunBattle.Entities.Triggers.IsFirstHitInSeriesTrigger$$ShouldTrigger`) =
        # `AbilityEntities.get_IsFirstHit` = `Nullable<bool>(hitIndex.HasValue && hitIndex == 0)` — le champ
        # `AbilityEntities@+0x110` est le Nullable<int> d'INDEX DE COUP, renseigne par
        # `IdunBattle.Operations.AttackDamageOperation$$ExecuteHit` (son param_3) qui emet
        # `On(PreAttackHit=6)` PAR COUP. Le trigger renvoie **false** si le Nullable est vide -> `None`
        # ici = « pas d'index de coup dans cet evenement » = `IsFirstHitInSeries` FAUX. Consommateur :
        # ThrillSeekers (branche 1).
        self.is_first_hit = is_first_hit
        # `AbilityEntities+0x118` = **`isFirstDamagingHit`** (nom LU verbatim, 29e parametre nomme du
        # ctor a 32 parametres d'`IdunBattle.Entities.Abilities.AbilityEntities$$.ctor`, juste avant
        # `movementSteps` @+0x11c). TROISIEME champ de la famille, DISTINCT des deux autres -- et
        # c'est mesure, pas suppose : `get_IsFirstHit` lit **+0x108**, `get_IsFirstHitGroup` lit
        # **+0x110**, et `IdunBattle.Entities.Triggers.IsFirstDamagingHitInSeriesTrigger$$
        # ShouldTrigger` lit **+0x118 DIRECTEMENT**, sans passer par aucun getter.
        # Canal UNIQUE du noeud `IdunBattleLogic.Entities.DSLTriggers$$IsFirstDamagingHitInSeries`.
        # TRI-ETAT : `None` = non threade sur cet event (le `Nullable` vide du natif -> le trigger
        # rend `false`, cf. `IsFirstDamagingHitInSeriesTrigger$$ShouldTrigger`).
        # SEUL emetteur qui le renseigne : `IdunBattle.Operations.ApplyDamageOperation$$Execute`
        # (vecteur `pre_damage_taken_triggers`, `On(0x39 = PreDamageTaken)`).
        self.is_first_damaging_hit = is_first_damaging_hit
        # L'`AbilityOrEffect` de la TRIGGERED-ABILITY dont l'execution a engendre cet evenement.
        #
        # ATTENTION AU NOM (case-292, RE relue sur le build `rnca9r7q6c`) : ce canal mirror en
        # realite le champ natif **`CurrentAbility`**, pas `TriggeringAbility`. Ce sont DEUX champs
        # DISTINCTS de l'`AbilityEntities`, et `IdunBattle.Entities.Abilities.BaseTriggeredAbility$$Execute`
        # les ecrit a des MOMENTS differents :
        #   * `CurrentAbility`    (`AbilityEntities+0x60`, lu par `AbilityTypeSelector.CurrentAbilitySelector$$Select`)
        #     = `Nullable<AbilityOrEffect>(this.Id)` pose **AVANT** l'appel du behaviour -> herite par
        #     TOUT ce que le behaviour engendre (attaque, degat, mort). C'est CE moment-la que le port
        #     reproduit (`dispatch/core.py`), donc CE champ que le canal porte.
        #   * `TriggeringAbility` (`AbilityEntities+0x98`, lu par `AbilityTypeSelector.TriggeringAbilitySelector$$Select`
        #     et rendu par `IdunBattle.Entities.Abilities.AbilityEntities$$get_TriggerAbilityType`)
        #     = le MEME id, mais pose **APRES** le behaviour, juste avant l'emission de
        #     `On(0xd = EventTriggerType.UnitTriggeredAbility)`. Aucun consommateur porte n'ecoute cet
        #     evenement -> cette face n'est PAS modelisee.
        # Cote DSL les deux predicats prennent des slots distincts de `DSLSelectors` :
        # `IdunBattleLogic.Entities.DSLTriggers$$CurrentAbilityIs` -> `+0x88` ;
        # `$$TriggeringAbilityIs` / `$$TriggeringEffectIs` / `$$TriggeringAbilityIsNone` -> `+0x90`
        # (un SEUL slot pour les trois, d'ou l'unique canal cote port).
        #
        # Consommateurs portes de CE canal :
        #   * `...CursedPlagueBellAttackAbility$$CreateTrigger` : `!CurrentAbilityIs(this)` -- le canal
        #     est EXACT (meme champ, meme moment d'ecriture) ;
        #   * `...FuelledByFury_ReviveAbility$$CreateTrigger` : `TriggeringAbilityIs(0x400 = 1024
        #     FinalJustice)` sur `On(3)` -- APPROXIMATION assumee. Le natif y lit le `killTrigger`
        #     recopie par `IdunBattle.Operations.RecordKillOperation$$Execute` depuis le
        #     `KillUnitContext` (le champ `+0x20` s'il a une valeur, sinon `+0x00`) et passe au
        #     publieur de `On(3)`. Les deux valeurs COINCIDENT dans les regimes portes (le coup fatal
        #     est porte par la triggered en cours), jamais separees par un montage. Sur `On(3)` le
        #     natif ecrit d'ailleurs `+0x60` ET `+0x98` avec la MEME ability (voie universelle
        #     `Core.Services.OperationProcessor$$EvaluateAbilities`) -> lire l'un ou l'autre y est
        #     equivalent, contrairement aux CINQ evenements de `KillUnitOperation` (#301).
        # None = evenement hors triggered-ability. ⚠ Sur le vecteur MORT (`On(0)/On(1)/On(2)/On(53 = PostUnitKill)/
        # On(54 = UnitDefeated)`) ce canal est INCONDITIONNELLEMENT vide cote natif comme cote port (#301) : un gate
        # `Triggering*Is` de ce vecteur doit lire `state.trigger_ability_type`, jamais celui-ci.
        # ⚠ Sur les vecteurs d'EFFET, a l'inverse, c'est CE canal-ci qui est renseigne dans LES DEUX
        # sens -- il porte l'`AbilityOrEffect` de l'EFFET (pas d'une triggered) : `+0x60 = +0x98 =
        # effectType` a la pose, `+0x60 = effectType` avec `+0x98` VIDE au retrait (#306). Un gate de
        # RETRAIT doit donc lire `CurrentAbilityIs`, jamais `TriggeringEffectIs`.
        self.triggering_ability = triggering_ability
        # La DESTINATION `(col, row)` d'un evenement de MOUVEMENT -- mirror des champs `casterTiles`
        # (7e arg) et `targetTiles` (10e) que `IdunBattle.Operations.MoveUnitOperation$$
        # EvaluatePreMoveTriggers` remplit avec la MEME liste `position` au ctor nomme
        # `IdunBattle.Entities.Abilities.AbilityEntities$$.ctor`. Sans ce canal, un `CreateTrigger`
        # qui compare la tuile COURANTE de l'acteur a sa tuile d'ARRIVEE n'a rien a comparer.
        # Consommateur : `HatefulAssaultAbility$$CreateTrigger` (`NOT AreEqual(Tiles(Actor),
        # <tuiles @DSLSelectors+0x78>)` = « la destination differe de la tuile courante », donc un
        # VRAI deplacement). Renseigne par `MoveUnitOperation.execute` -- seul emetteur du vecteur
        # `On(PreUnitMove)` cote port. None = non threade (les autres vecteurs) : un consommateur qui
        # le lit doit DIRE ce qu'il fait de l'absence, jamais la confondre avec « les tuiles sont
        # egales ».
        self.dest_tile = dest_tile
        # `IdunBattleLogic.Entities.DSLFormulas$$HealthDamageFromEvent` — la part SANTE du degat de
        # l'evenement (ce que les PV ont REELLEMENT perdu, bouclier deduit). Le port la threade sur le
        # vecteur de CLOTURE `On(9 = Attack)` uniquement, ou elle vaut `AttackDamageOperation.execute`
        # -> `r["total"]` (les operations de degat du port defalquent deja le bouclier : cf. le
        # commentaire « total = part SANTE seule » de `damage_ops/normal.py`). None = ce vecteur ne
        # porte pas de degat -> un gate `AmountIsGreaterThanZero(HealthDamageFromEvent())` est FAUX,
        # jamais « inconnu = vrai ».
        self.health_damage = health_damage
        # `IdunBattleLogic.Entities.DSLTriggers$$WasBlock` — l'attaque a-t-elle ete BLOQUEE ? Meme
        # canal que le `did_block` deja passe a `unit_blocked_triggers` (`On(0x3c)`), threade ici sur
        # le vecteur de cloture parce que la disjonction native
        # `AmountIsGreaterThanZero(HealthDamageFromEvent()) | WasBlock()` de
        # `TerminatorArmour_ReduceDmg_Effect$$CreateTargetTrigger` en a besoin : un coup ENTIEREMENT
        # bloque (0 PV perdu) consomme quand meme l'armure. None = non threade -> FAUX.
        self.was_block = was_block
        # `IdunBattleLogic.Entities.DSLTriggers$$AttackUsedAttackDamage` — corps ENTIER de son trigger :
        #     `IdunBattle.Entities.Triggers.AttackUsedAttackDamageTrigger$$ShouldTrigger`
        #         = `return *(byte *)(entities + 0xf9);`
        # C'est le MEME fait que le gate de `On(10)` (`currentAttack@+0x2c`, pose par
        # `IdunBattle.Operations.AttackDamageOperation$$Execute`) : « cette attaque a comporte une
        # ATTAQUE-A-DEGATS » (famille ATTACK), par opposition a une attaque resolue par
        # `IdunBattle.Operations.AbilityDamageOperation`. Cote port, ce fait EST `is_attack_damage_op`,
        # threade par les emetteurs d'`On(9)`.
        # ⚠ PAS DE TRI-ETAT ICI, et c'est LU : le natif lit un `byte` BRUT d'un `AbilityEntities`
        # `memset` a 0 -> un evenement qui ne le renseigne pas vaut FAUX cote natif aussi. `None` se
        # lit donc `False`, ce n'est pas une degradation. Consommateur : le volet DespoiledGround de
        # `IdunBattleLogic.Entities.Abilities.Triggered.Loki.LetTheGalaxyBurn_ResetAbility$$CreateBehaviour`.
        self.attack_used_attack_damage = attack_used_attack_damage


class TriggeredAbility:
    """Mirror d'une entrée ability-trigger du registre `AbilityAndEffectCache`. `event_id` = l'événement
    écouté (`On(event_id)`) ; `owner_id` = entité porteuse. `matches` = condition `CreateTrigger` ;
    `execute_behaviour` = PossibleTargets + CreateBehaviour. Sous-classes = un trigger concret."""
    event_id: int = -1
    # `AbilityOrEffect(this.Id)` de CETTE triggered-ability (`TriggeredAbilityType`), tel que
    # `IdunBattle.Entities.Abilities.BaseTriggeredAbility$$Execute` l'ecrit dans le champ
    # **`CurrentAbility`** (`AbilityEntities+0x60`) AVANT d'executer le behaviour -> c'est ce que lit
    # `IdunBattleLogic.Entities.DSLTriggers$$CurrentAbilityIs` sur tout evenement engendre par ce
    # behaviour (cf. le bloc `triggering_ability` de `TriggerEvent` pour la distinction avec le champ
    # `TriggeringAbility` @+0x98, ecrit APRES). None = id non renseigne (le port ne threade alors AUCUN
    # id pour cette ability : gate positif faux, gate negatif vrai). Cf. `dispatch/core.py`.
    TRIGGERED_ABILITY_ID: Optional[int] = None
    fire_on_death: bool = False     # ability « fire-on-death » : owner = l'unité MOURANTE (alive=False) —
                                    # bypass du gate « owner vivant » (CanGetAbilityTrigger). Ex. FinalJustice.
    owner_is_global: bool = False   # ability de la famille `Abilities.Damage.Loki` : son `CreateTrigger` ne
                                    # porte AUCUN prédicat d'owner (`get_OwnerIs*`), et le canal se déclenche
                                    # sur le PROFIL du coup, jamais sur une unité. Elle est donc inscrite UNE
                                    # SEULE FOIS pour la bataille (`GLOBAL_TRIGGERS`), et non par entité :
                                    # une inscription par unité la ferait firer N fois par événement, ce que
                                    # la mesure live REFUTE (exactement UN `NextBool` par série de coups,
                                    # `test_on_toxic_damage_live.py`). `owner_id` vaut None -> les gates
                                    # unit-entity/alive et le cap PAR PHASE (compteur porté par le
                                    # `TriggeredAbilityComponent` de l'owner) ne s'appliquent pas.

    def __init__(self, owner_id: int):
        self.owner_id = owner_id

    def matches(self, state: State, ev: TriggerEvent) -> bool:
        raise NotImplementedError

    def execute_behaviour(self, state: State, ev: TriggerEvent) -> Optional[dict]:
        raise NotImplementedError


class EffectTrigger:
    """Mirror d'une entrée EFFET-trigger du registre `AbilityAndEffectCache` (`IdunBattle.Operations.EvaluateTriggerOperation$$EvaluateEffectTrigger
    → `IdunBattle.Operations.EvaluateTriggerOperation$$EvaluateEffectTriggerTargets). `effect_type` = l'effet porteur ; `owner_id` = l'unité qui
    porte l'effet. `matches` = condition du trigger de l'effet (def `EffectsDatabase` slot 0x26) ;
    `execute_behaviour` = le behaviour (`HandleTriggerAbilities`). Sous-classe = un effet-trigger concret."""
    event_id: int = -1
    effect_type: int = -1
    # cf. `TriggeredAbility.TRIGGERED_ABILITY_ID` : un effet-trigger est lui aussi execute par
    # `IdunBattle.Entities.Abilities.BaseTriggeredAbility$$Execute` cote natif.
    TRIGGERED_ABILITY_ID: Optional[int] = None

    def __init__(self, owner_id: int):
        self.owner_id = owner_id

    def matches(self, state: State, ev: "TriggerEvent") -> bool:
        raise NotImplementedError

    def execute_behaviour(self, state: State, ev: "TriggerEvent") -> Optional[dict]:
        raise NotImplementedError


class TileEffectTrigger(EffectTrigger):
    """Effet-trigger porté par une TUILE (`owner_id` = id d'entité-tile ; boardGraph `t.id` = entity id,
    disjoint des ids d'unité → clé `EffectsState.by_unit` valide). Mirror natif : une tuile = entité à
    `EffectsOwnedComponent` portant l'effet + ses triggers (ex.
    `IdunBattle.Entities.Effects.Loki.ContaminatedEffect$$CreateHandleTriggerAbilitiesInternal). `owner_is_tile` fait bypasser les
    gates unit-entity/alive de `evaluate_trigger_operation` (une tuile n'est PAS dans `state.entities`).
    `event_ids` (au lieu d'un `event_id` unique) : un tile-effect écoute souvent PLUSIEURS events (enter
    `On(4)` + tick `On(0x12)`/`On(0x14)`)."""
    owner_is_tile = True
    event_ids: tuple = ()

    def _tile_coord(self, state: State):
        b = getattr(state, "board", None)
        if b is None:
            return None
        try:
            return b.coord(self.owner_id)
        except Exception:
            return None

    def _unit_on_tile(self, state: State) -> Optional[int]:
        """id de l'unité VIVANTE occupant ma tuile (positions exclusives → <=1). None si vide."""
        co = self._tile_coord(state)
        if co is None:
            return None
        for uid, e in state.entities.items():
            pc = e.get_component(PositionComponent)
            if pc is None or (pc.col, pc.row) != co:
                continue
            uc = e.get_component(UnitComponent)
            if uc is not None and not uc.alive:
                continue
            return int(uid)
        return None


def triggered_ability_state(state: State, unit_id: int, ability_name: str):
    """`(level, multiplier)` de l'`AbilityState` sous lequel `ability_name` est MONTEE sur `unit_id`.

    MIRROR de `IdunBattle.Entities.Factories.UnitFactory$$Build`, qui fabrique TROIS `AbilityState`
    depuis la `UnitConfiguration` et les distribue par `AddConfiguredAbilities` :

        activeAbilityState   = (config+0xb8 ActiveAbilityLevel,   config+0x74)  -> les actives
        passiveAbilityState  = (config+0xbc PassiveAbilityLevel,  config+0x74)  -> les passives (hier. 2)
        tertiaryAbilityState = (config+0xc0 TertiaryAbilityLevel, config+0x78)  -> la RELIQUE (hier. 3)

    C'est CE couple que `IdunBattle.Configuration.AbilityConfiguration$$GetVariableForLevel` consomme
    (index `Idun.Shared.Level$$ToZeroBasedIndex(level)` clampe au dernier palier, puis
    `x mult/100` SSI la variable est dans `variablesAffectedByRarityBonus`).

    La MEME ability peut arriver par les deux voies, et le couple n'est PAS le meme :
      * relique EQUIPEE (`UnitContext.tertiary_ability`) -> etat TERTIAIRE ;
      * relique cablee EN DUR (`gameconfig.units.<id>.relicAbilities`, npc) ou passif de kit ->
        etat PASSIF, qui est aussi le repli quand le canal tertiaire n'est pas fourni.
    Sans ce discriminant, une relique montee au niveau 8 lirait le niveau des PASSIFS du porteur
    (50 dans tout runner normalise), donc le dernier palier -- un ecart SILENCIEUX de magnitude.

    Rend `(None, 100)` si l'unite / son contexte manquent : l'appelant retombe alors sur une
    variable a 0, et la feuille DSL qui la consomme est un no-op (sa garde `amount > 0`)."""
    e = state.get_entity(unit_id)
    sc = e.get_component(StatsComponent) if e is not None else None
    ctx = sc.ctx if sc is not None else None
    if ctx is None:
        return (None, 100)
    if getattr(ctx, "tertiary_ability", None) == ability_name:
        return (int(getattr(ctx, "tertiary_ability_level", 0) or 0),
                int(getattr(ctx, "tertiary_ability_variables_multiplier", 100) or 100))
    return (getattr(ctx, "passive_ability_level", None),
            int(getattr(ctx, "ability_variables_multiplier", 100) or 100))


#: `AreEqual(<DSLSelectors+0x98>, DirectAbilitySelector(0x434))` -- le littéral LU à l'assembleur
#: (`IdunBattleLogic.Entities.DSLSelectors$$Attacker+0x38` : `mov edx,0x434`). Cf. `attacker_of`.
ATTACKER_PARENT_ABILITY = 1076        # ActiveAbilityType.MV71SniperDroneSquadAttack


def attacker_of(state: State, ev: "TriggerEvent") -> Optional[int]:
    """`IdunBattleLogic.Entities.DSLSelectors$$Attacker` -- FOYER UNIQUE du sélecteur (#523-r4).

    CE N'EST PAS le slot `Actor@DSLSelectors+0x40`, et ce n'est pas non plus `Caster@+0x48` nu :
    c'est un sélecteur CONDITIONNEL, lu en entier ::

        If( AreEqual(<DSLSelectors+0x98>,
                     DirectAbilitySelector(AbilityOrEffect(0x434 = MV71SniperDroneSquadAttack))),
            ParentSelector(Caster@+0x48),
            Caster@+0x48 )

    CE QUI EST LU, ET COMMENT :
      * le littéral `0x434` est à l'assembleur (`...$$Attacker+0x38` : `mov edx,0x434`), pas dans
        le décompilé -- ghidra perd le registre dans `AbilityOrEffect$$op_Implicit` ;
      * la nature CONDITIONNELLE du nœud rendu vient des XREFS de son `.ctor` (corps DÉDUPLIQUÉ que
        `DSLSelectors$$If` et `DSLSelectors$$ConditionalSelector` partagent) : le nom ghidra
        `IdunBattle.Entities.Selectors.UnobscuredEntitiesSelector$$.ctor` est celui d'un
        propriétaire ARBITRAIRE et ne dit RIEN -- l'ordre des arguments
        `(services, condition, then, else)` est celui du site d'appel ;
      * la surcharge d'`AreEqual` retenue est celle appelée par `Attacker`, et son SECOND opérande
        est un `AbilityTypeSelector` : la comparaison porte donc sur des ABILITY-TYPES, jamais sur
        des entités ;
      * `ParentSelector$$Select` remonte par `IdunBattle.Entities.UnitExtensions$$GetParent`, dont
        le port a le pendant (`UnitComponent.parent_id`, mirror de `ChildComponent.ParentId` que
        `SpawnUnitOperation` pose au spawn).

    LE SEUL POINT NON ÉPINGLÉ, et il est nommé : `<DSLSelectors+0x98>` est l'un des TROIS
    sélecteurs sans argument que `IdunBattleLogic.Entities.DSLSelectors$$.ctor` met en cache en
    `+0x88/+0x90/+0x98` (leur ctor commun est un corps dédupliqué, donc leurs classes ne sont pas
    nommables hors ligne). Deux seuls candidats sont des `AbilityTypeSelector` parameterless :
    `CurrentAbilitySelector` (dont le `$$Select` lit `AbilityEntities+0x60`) et
    `TriggeringAbilitySelector` (`+0x98` de l'`AbilityEntities`). Le second est écrit APRÈS le
    behaviour d'une triggered et ne couvre que `On(0xd)` (case-292) : il serait NUL sur le vecteur
    `On(9 = Attack)` où `Attacker` est consommé. Le port lit donc `ev.ability_type`, le canal du
    port pour `+0x60`.

    SÉMANTIQUE : une attaque portée par le drone `MV71SniperDroneSquad` (T'au) est créditée à son
    PARENT ; toute autre attaque est créditée à son caster, que ce vecteur expose en `ev.actor_id`.

    ⚠ NON CONFRONTÉ, et c'est MESURÉ, pas supposé. Le seul consommateur PORTÉ de ce sélecteur est
    `HeavyWarpFlamer_AttackTrackingAbility$$CreateTrigger`, où `Attacker` n'entre que dans
    `NOT AreEqual(Attacker, Owner)` et `AreFriends(Attacker, Owner)`. Un drone et son parent sont
    dans la MÊME équipe, donc `AreFriends` rend le même verdict des deux côtés ; et `AreEqual` ne
    diffèrerait que si l'owner de `1546` ÉTAIT le parent du drone -- il faudrait greffer le passif
    `MV71SniperDroneSquad` sur `thousSekhetar`, ET que l'attaque du drone porte un profil
    `Psychic`, que le conjoint `CurrentAttackDamageProfilesContain(0xd)` exige. La branche est donc
    INERTE sur ce porteur. Ce foyer existe pour que le PROCHAIN consommateur (`ShieldOfFaith`,
    `LifeStealEffect`, `HeadwoppasKillchoppaEffect` -- les trois autres XREFS, aucune portée)
    hérite du sélecteur au lieu de re-collapser sur l'acteur.

    Rend `None` quand le vecteur ne porte pas d'acteur (le natif rendrait un ensemble vide, et tout
    conjoint qui le consomme est alors faux)."""
    caster = getattr(ev, "actor_id", None)
    if caster is None:
        return None
    caster = int(caster)
    if getattr(ev, "ability_type", None) is None:
        return caster
    if int(ev.ability_type) != ATTACKER_PARENT_ABILITY:
        return caster
    e = state.get_entity(caster)
    uc = e.get_component(UnitComponent) if e is not None else None
    parent = getattr(uc, "parent_id", None) if uc is not None else None
    # `ParentSelector$$Select` n'ajoute à son `OrderedSet` que les parents NON NULS : un enfant sans
    # parent rend un ensemble VIDE, pas l'enfant lui-meme.
    return int(parent) if parent is not None else None


# --- Sélecteurs DSL partagés (mirror `DSLFactory.*`) : géométrie / adjacence / faction ------------
def _unit_trait_names(state: State, unit_id: int) -> list:
    """Noms de traits gameconfig de l'unité (`StatsComponent.ctx.traits` = NOMS, cf. unit_context.py:191).
    [] si l'entité / le ctx / les traits sont absents."""
    e = state.get_entity(unit_id)
    sc = e.get_component(StatsComponent) if e is not None else None
    return (sc.ctx.traits if (sc is not None and getattr(sc, "ctx", None) is not None) else None) or []


def _adjacent_damageable_enemies(state: State, attacker_id: int, target_id: int) -> list[int]:
    """`Damageable(Enemies(AdjacentUnits(cible)))` — ids des ennemis (de l'attaquant) VIVANTS adjacents
    (hex) à la cible primaire. Requiert `state.board` (adjacence hex) ; sans board → [] (no-op fidèle).
    ⚠ Le board DOIT être construit en mode **evenq** : le JEU utilise l'adjacence géométrique hex (preuve
    live : splash sur un ennemi evenq-adjacent que la capture `native`/`native_sym` de `boardGraph.neighbours`
    NE liste PAS — la capture est partielle/asymétrique, ~13 arêtes one-way + tuiles coin vides)."""
    board = state.board
    tgt = state.get_entity(target_id)
    att = state.get_entity(attacker_id)
    if board is None or tgt is None or att is None:
        return []
    tp = tgt.get_component(PositionComponent)
    a_owner = att.get_component(OwnerComponent)
    if tp is None or a_owner is None:
        return []
    ttile = board.id_at(tp.col, tp.row)
    neigh = set(board.neighbours(ttile))
    out: list[int] = []
    for eid, e in state.entities.items():
        if eid == target_id or eid == attacker_id:
            continue
        oc = e.get_component(OwnerComponent)
        uc = e.get_component(UnitComponent)
        pc = e.get_component(PositionComponent)
        if oc is None or pc is None or oc.team == a_owner.team:   # ennemis de l'attaquant uniquement
            continue
        if uc is not None and not uc.alive:
            continue
        if board.id_at(pc.col, pc.row) in neigh:                  # adjacent (hex) à la cible
            out.append(eid)
    return out


from ....entities.effect_type import EffectType

FORCED_IN_MELEE = int(EffectType.ForcedInMelee)   # 1321 = 0x529 — clamp de portée (cf. `_forced_in_melee`)


def _max_attack_range(ctx) -> int:
    """Portée d'attaque MAX de l'unité pour `DSLFactory.IsInAttackRange` — DÉLÈGUE à
    `engine.runner.abilities.targeting.unit_weapon_range`, le port UNIQUE des trois branches d'arme
    de `IdunBattle.Core.Services.TargetingQuery$$GetRange` (partagé avec le gate de cible #241 ;
    surtout pas un 2e port de la même fonction native).

    SEULE différence, assumée ici : la branche `!HasAnyWeapon` (unité SANS aucune arme — les Machines
    of War et les objets de décor) rend `None` côté port, parce que `GetStat(u, StatType.Range = 2)`
    n'est **pas observable** (StatType 2 est hors du catalogue de `combatSnapshot`). Ce chemin-ci lui
    substitue **1**, le comportement historique de `IsInAttackRange` — le gate de cible, lui, préfère
    ne poser AUCUN refus. Les deux traductions sont volontairement différentes : ici un 0 fermerait
    l'overwatch d'une MoW, là un 0 refuserait toutes ses cibles.

    Le clamp `ForcedInMelee` (`Math.Min(1, range)`) et le cap final restent chez l'appelant
    (`_in_attack_range`)."""
    r = unit_weapon_range(getattr(ctx, "visual_id", None), getattr(ctx, "stats", None))
    return 1 if r is None else r


def _forced_in_melee(state: State, unit_id: int) -> bool:
    """`IdunBattle.Core.Services.TargetingQuery$$GetRange` : juste avant le `Math.Min` final, le natif
    fait `if (EntityExtensions.HasEffect(unit, ..., 0x529, 0, 0)) { range = Math.Min(1, range); }` —
    le porteur de l'effet `ForcedInMelee` ne peut plus atteindre QUE la mêlée, quelle que soit son arme
    (le drapeau `isMelee` de retour bascule aussi). C'est le SEUL paramètre natif qui restreint le
    domaine de cible d'une attaque « depuis la position courante » à l'adjacence.

    Poseur porté : `IdunBattleLogic.Entities.Abilities.Active.Loki.TheQuickeningAbility$$GetTriggerAttackBehaviour`
    (pose transitoire autour de sa free-attack, retirée dans le même cast) → inerte partout ailleurs."""
    eff = getattr(state, "effects", None)
    if eff is None or unit_id is None:
        return False
    return any((not e.consumed) and e.effect_type == FORCED_IN_MELEE
               for e in eff.by_unit.get(int(unit_id), []))


def _hex_dist(board, src: int, dst: int, cap: int) -> Optional[int]:
    """Distance hex (BFS non pondéré sur les voisins du board, murs ignorés = portée/range, pas
    déplacement) ; renvoie la distance si <= cap, sinon None. ⚠ board en mode **evenq** (cf.
    `_adjacent_damageable_enemies`)."""
    from collections import deque
    seen = {src: 0}
    q = deque([src])
    while q:
        x = q.popleft()
        if x == dst:
            return seen[x]
        if seen[x] >= cap:
            continue
        for n in board.neighbours(x):
            if n not in seen:
                seen[n] = seen[x] + 1
                q.append(n)
    return None


def _in_attack_range(state: State, attacker_id: int, target_id: int, from_pos=None) -> bool:
    """`DSLFactory.IsInAttackRange(attacker, target, 3)` — la cible est-elle dans la portée d'attaque
    de l'attaquant (distance hex <= portée arme max) ? Requiert `state.board` (evenq). Sans board → False.

    La portée est celle de `IdunBattle.Core.Services.TargetingQuery$$GetRange`, clamp `ForcedInMelee`
    INCLUS (`_forced_in_melee`) : un porteur de l'effet 0x529 ne porte qu'à 1.

    `from_pos=(col,row)` évalue depuis une tuile CANDIDATE au lieu de la position courante. Ce n'est
    pas une commodité de test : `IdunBattle.AI.Playbook.BasePlaybook$$GetEligibleTargetsForNormalAttack`
    est appelée par `ComparablePlaybook.EvaluateInternal(unit, position, ctx)` **une fois par position
    candidate** — la PORTÉE, elle, ne dépend que de l'unité (`GetRange(unit)`), mais la DISTANCE se
    mesure depuis la position évaluée. Tant que le domaine d'action se réduisait à la tuile courante
    (`GenerateActionTiles(…, 0)`) les deux lectures coïncidaient ; dès que l'acteur peut s'approcher
    (`…, null`), gater sur la seule position courante annulerait l'approche (#348)."""
    board = state.board
    if board is None:
        return False
    a = state.get_entity(attacker_id)
    t = state.get_entity(target_id)
    if a is None or t is None:
        return False
    ap = a.get_component(PositionComponent)
    tp = t.get_component(PositionComponent)
    sc = a.get_component(StatsComponent)
    if (ap is None and from_pos is None) or tp is None or sc is None:
        return False
    a_tile = board.id_at(from_pos[0], from_pos[1]) if from_pos is not None \
        else board.id_at(ap.col, ap.row)
    t_tile = board.id_at(tp.col, tp.row)
    if a_tile is None or t_tile is None:
        return False
    rng = _max_attack_range(sc.ctx)
    if _forced_in_melee(state, attacker_id):     # `GetRange` : `range = Math.Min(1, range)`
        rng = min(1, rng)
    return _hex_dist(board, a_tile, t_tile, rng) is not None


def _is_ranged_position(state: State, attacker_id: int, target_id: int) -> bool:
    """Mirror `IdunBattleLogic.Entities.DSLFactory$$IsRangedAttack` (= `IsRangedAttackAbilityTrigger` IdunBattle.Entities.Triggers.IsRangedAttackAbilityTrigger$$ShouldTrigger, qui
    calcule les POSITIONS caster/cible via `IdunBattleLogic.Entities.DSLTriggers$$IsRangedPosition`) : une attaque est RANGED ssi le
    caster N'EST PAS adjacent (mêlée) à la cible — **POSITION-based, PAS le type d'arme/profil**. Donc un
    splash psychique porté sur un ennemi ADJACENT au caster est MÊLÉE → ne re-déclenche PAS Smite (pas de
    chain). Non-adjacent (dist > 1) = ranged. Fallback False (mêlée = conservateur, pas de re-trigger) si
    board/positions absents. Adjacence = `board.neighbours` (evenq, l'adjacence fidèle du port)."""
    if state.board is None:
        return False
    a = state.get_entity(attacker_id)
    t = state.get_entity(target_id)
    ap = a.get_component(PositionComponent) if a is not None else None
    tp = t.get_component(PositionComponent) if t is not None else None
    if ap is None or tp is None:
        return False
    atile = state.board.id_at(ap.col, ap.row)
    ttile = state.board.id_at(tp.col, tp.row)
    if atile is None or ttile is None:
        return False
    return ttile not in set(state.board.neighbours(atile))     # non-adjacent = RANGED


def _is_ranged_attack(state: State, ability_type, attacker_id: int, target_id: int) -> bool:
    """`IdunBattle.Core.Services.BattleQuery$$IsRangedAttack(ability, caster, casterPosition,
    target)` -- le slot **3** d'`IBattleQuery`, COMPLET, dans le domaine du runner.

        switch (GetAbilityAttackRangeType(ability)) {   // 0 None, 1 Melee, 2 Ranged, 3 Normal
          case 0: case 1: return false;
          case 2: return true;                          // INCONDITIONNEL -- aucune position lue
          case 3: return HasFlag(caster, ForceRangedAttack) || !AreEntitiesAdjacent(...);
        }

    ⚠ `_is_ranged_position` ci-dessus n'implemente QUE la branche `Normal(3)` -- c'est le mirror du
    seul repli positionnel, et l'appliquer a une ability declaree `Ranged(2)` DESARME le predicat
    des que la cible est au contact. Mesure (#512-r1) : `1197 ExcruciatingFrequencies` est
    `attackRangeType = Ranged` (gameconfig ET `BC.Abilities.ActiveAbilities[...].AttackRangeType = 2`),
    sa 1re cible est ADJACENTE au caster, et le natif la suppresse quand meme.

    L'ETAGE `GetAbilityAttackRangeType` est delegue au FOYER `services/battle_query.attack_range_type`
    (le natif l'a aussi en fonction separee, consultee par les slots 2 ET 3) ; la branche `Normal(3)`
    reste sur `_is_ranged_position`, c.-a-d. `state.board.neighbours` -- l'adjacence du RUNNER, deja
    confrontee live (`test_suppressive_fire_live.py` : Pinned a d==2, absent a d==1).

    `ability_type` = l'`AbilityOrEffect` du coup, tel que l'event le porte (`TriggerEvent.
    ability_type`). `None` -> pas de nom -> branche `Normal(3)`, MEME convention que
    `services/battle_query.is_melee_attack` et MEME justification : les attaques normales CONCRETES
    n'ont pas d'entree nommee au gameconfig. `ForceRangedAttack` (`UnitFlag` 21) n'est publie par
    aucun capteur (residu `#419-r1-tr5-r1`) -> non lu ici, degradation RESTRICTIVE nommee."""
    import gameconfig as GC     # differe comme chez son voisin `_faction_id` (module TOP-LEVEL,
                                # hors du critere `engine.*` du CLAUDE.md ; charge le gameconfig)
    rt = _svc_bq.attack_range_type(GC.ability_name(int(ability_type))
                                   if ability_type is not None else None)
    if rt == "Ranged":                 # `AttackRangeType.Ranged` (2)
        return True
    if rt in ("Melee", "None"):        # `AttackRangeType.Melee` (1) / `.None` (0)
        return False
    return _is_ranged_position(state, attacker_id, target_id)   # branche `Normal(3)`


def _attack_range_type(state: State, ability_type, attacker_id, target_id) -> str:
    """`IdunBattle.Core.Services.BattleQuery$$GetAttackRangeType(ability, caster, casterPosition,
    target)` -- le slot **4** d'`IBattleQuery`, dans le domaine du RUNNER. FRERE de
    `_is_ranged_attack` ci-dessus (slot 3) : meme etage `GetAbilityAttackRangeType`, meme repli
    positionnel sur la branche `Normal(3)`, mais il rend le MEMBRE et non un booleen -- et cette
    troisieme valeur (`"None"`) est exactement ce que ses consommateurs distinguent.

    Il y en a DEUX cote natif, et les deux ecrivent une donnee que le port ne tenait pas :

      * `IdunBattle.Operations.FinishAttackOperation$$Execute` -> `IOperationProcessor` slot 74
        (`RegisterAttack`) -> `ActorStatisticsComponent$$RegisterAttackMade`, qui incremente
        `@+0x2c` sur `Melee` et `@+0x28` sur `Ranged` (`#508-r2`) ;
      * `IdunBattle.Operations.ApplyDamageOperation$$Execute` -> `KillUnitContext@+0x38` ->
        `IdunBattle.Core.MatchState$$AddDeath(..., AttackRangeType)` -> `KillUnitOptions+0x3c` ->
        `IdunBattle.Operations.KillUnitOperation$$Execute`, qui en derive
        `inMelee = HasValue && value == Melee(1)` (`#951-r1`).

    L'ETAGE `GetAbilityAttackRangeType` est delegue au FOYER
    `services/battle_query.get_attack_range_type` (le natif l'a aussi en fonction separee) ; la
    branche `Normal(3)` reste sur `_is_ranged_position`, c.-a-d. `state.board.neighbours` --
    l'adjacence du RUNNER, deja confrontee live, exactement comme `_is_ranged_attack`.

    `ability_type` = l'`AbilityOrEffect` du coup. `None` -> pas de nom -> branche `Normal(3)`,
    MEME convention que `_is_ranged_attack`. `ForceRangedAttack` (`UnitFlag` 21) n'est publie par
    aucun capteur (residu `#419-r1-tr5-r1`) -> non lu ici, degradation nommee et identique."""
    import gameconfig as GC     # differe pour la meme raison que dans `_is_ranged_attack`
    rt = _svc_bq.attack_range_type(GC.ability_name(int(ability_type))
                                   if ability_type is not None else None)
    if rt in ("Melee", "Ranged", "None"):      # `case 1` / `case 2` / `case 0`
        return rt
    # branche `Normal(3)` : `Melee` ssi adjacent (et pas de `ForceRangedAttack`), sinon `Ranged`.
    if attacker_id is None or target_id is None:
        return "Ranged"                        # `AreEntitiesAdjacent` sans entite = FAUX
    return "Ranged" if _is_ranged_position(state, int(attacker_id), int(target_id)) else "Melee"


def _faction_id(state: State, unit_id: int) -> Optional[str]:
    """`FactionId` gameconfig de l'unité (résolu par `visual_id`) — sert au test Imperial (`HasTrait(26)`).
    None si l'unité ou son visual_id est introuvable."""
    import gameconfig as GC
    e = state.get_entity(unit_id)
    if e is None:
        return None
    vid = None
    sc = e.get_component(StatsComponent)
    if sc is not None:
        vid = getattr(sc.ctx, "visual_id", None)
    if vid is None:
        uc = e.get_component(UnitComponent)
        vid = uc.visual_id if uc is not None else None
    if vid is None:
        return None
    return (GC.unit(vid) or {}).get("FactionId")


def _pick_randomly(state: State, candidates: list[int]) -> Optional[int]:
    """`IdunBattleLogic.Entities.DSLSelectors$$PickRandomly(source, 1)` ->
    `IdunBattle.Entities.Selectors.PickRandomAmountSelector$$Select` avec `amount = 1` — choisit UN
    candidat et **consomme UN tirage dès que le pool est non vide**, y compris quand il ne contient
    qu'un seul élément (case-130 SS4 ; loi établie et mesurée par #130).

    Le décompilé de `PickRandomAmountSelector$$Select` n'a AUCUN court-circuit « le pool tient dans
    amount » : sa seule sortie anticipée est `candidates.Count < 1` (pool VIDE). Pour `amount = 1` et
    un pool de `k >= 1`, la boucle tourne donc exactement une fois et appelle
    `rng.NextInternal(0, k)` — et à `k == 1`,
    `IdunBattle.Utils.PRNG.IntBasedMersenneTwister$$NextInternal` prend la branche puissance-de-deux
    (`(-1 & 1) == 1`), qui CONSOMME un `genrand_int32` avant de retourner 0. Un tirage « sans choix »
    reste un tirage : court-circuiter décale tout le flux RNG en aval (crit/block/dégât suivants).

    Les DEUX appelants construisent bien ce nœud (décompilé lu, pas déduit) :
      * `IdunBattleLogic.Entities.Abilities.Active.Loki.PsykerExtraAttackAbility$$CreateBehaviour` :
        `PickRandomly(Damageable(Enemies(caster, AdjacentUnits(target@0x178, 1, 3))), 1, 0,
        0x7fffffff, false)` ;
      * `IdunBattleLogic.Entities.Abilities.Triggered.Loki.EnvAmbushResurrectAbility$$CreateBehaviour` :
        `PickRandomly(GetValidDecoys(), 1, 0, 0x7fffffff, false)`, sous un `Foreach` -> un tirage PAR
        ressuscité.

    Foyer unique de la loi = `abilities/loki/splash.py::_pick_randomly_n` (mirror 1:1 de la boucle
    native) : on délègue au lieu de la ré-écrire. Ordre du pool = ids triés (⚠ résidu #215 restant :
    le natif énumère dans l'ordre du sélecteur source, ce qui ne change QUI est pris que lorsque le
    pool déborde `amount` — jamais le NOMBRE de tirages)."""
    picked = _pick_randomly_n(state, sorted(candidates), 1)    # PickRandomly(., 1)
    return picked[0] if picked else None


def _unit_tile(state: State, board, uid: int) -> Optional[int]:
    e = state.get_entity(uid)
    pc = e.get_component(PositionComponent) if e is not None else None
    return board.id_at(pc.col, pc.row) if pc is not None else None


def _is_adjacent_units(state: State, a_id: int, b_id: int) -> bool:
    """Adjacence hex (dist == 1) entre deux unites. ORACLE DE TEST uniquement depuis la Voie A
    (S-chantier) : le runner ne l'appelle PLUS -- le noeud DSL `IsAdjacent` (entities/triggers.py,
    relu LIVE via LiveUnit) a repris ce role en production. Conserve comme oracle d'adjacence
    INDEPENDANT du test de migration TheBetrayer (ne pas s'auto-tester avec le noeud sous test).
    Cf. docs/rl/dsl-live-context-substrate.md."""
    board = state.board
    if board is None:
        return False
    at = _unit_tile(state, board, a_id)
    bt = _unit_tile(state, board, b_id)
    return at is not None and bt is not None and bt in set(board.neighbours(at))


def _adjacent_enemies(state: State, owner_id: int) -> list[int]:
    """Ennemis VIVANTS adjacents (hex) à `owner` = cibles normal-attaquables d'une unité MÊLÉE (Kharn
    ne se déplace pas en mourant). Requiert `state.board` (evenq). Sans board → []."""
    board = state.board
    owner = state.get_entity(owner_id)
    if board is None or owner is None:
        return []
    ot = _unit_tile(state, board, owner_id)
    oc = owner.get_component(OwnerComponent)
    if ot is None or oc is None:
        return []
    neigh = set(board.neighbours(ot))
    out: list[int] = []
    for eid, e in state.entities.items():
        if eid == owner_id:
            continue
        c = e.get_component(OwnerComponent)
        u = e.get_component(UnitComponent)
        if c is None or c.team == oc.team:                 # ennemis de l'owner uniquement
            continue
        if u is not None and not u.alive:
            continue
        t = _unit_tile(state, board, eid)
        if t is not None and t in neigh:
            out.append(eid)
    return out
