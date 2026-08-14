"""Générateurs d'action ordonnés — namespace `IdunBattle.AI` (cf. playbook/architecture.md §2.3).

Le tactic natif (`DefaultAiUnitTactic`) itère une LISTE ORDONNÉE de générateurs et prend la PREMIÈRE
action NON-NULLE (`IdunBattle.AI.Tactics.DefaultAiUnitTactic.u003CCalculateNextActionForUnitu003Ed__5$$MoveNext`). Un `ActiveAbilityActionGenerator`
balaie (tuiles de move × abilities de SON ensemble), fait `LoadPlaybook(ability) -> playbook.Evaluate`
(le playbook énumère ses cibles et les score), merge dans un `Bucket`, `ChooseAction`
(`<GenerateActions>d__7 IdunBattle.AI.ActionGenerators.ActiveAbilityActionGenerator.u003CGenerateActionsu003Ed__7$$MoveNext` + `IdunBattle.AI.BucketSystem.Bucketu003C__Il2CppFullySharedGenericTypeu003E$$ChooseAction`).

MÉCANISME CONFIRMÉ (RE ghidra, décompilé = vérité — cf. architecture.md §2.3) : `IdunBattle.AI.Tactics.ABaseAiActorTactic$$InitAbilityTypeLists` range chaque ability par le flag `slot1` de son playbook = **Comparable vs NonComparable** :
  - NonComparable (slot1=FALSE) -> `dict[get_Priority]` : UN générateur par tier de priorité,
    dans l'ordre `[1000, 100, 0, -100, -1000]` (générateurs #1..#5) ;
  - Comparable (slot1=TRUE, **attaque normale INCLUSE** + spéciales d'attaque + soins) -> l'OrderedSet
    `special` = UN générateur fallback (#6), évalué APRÈS tous les tiers NonComparable ;
  - `MovementActionGenerator` (approche pure) EN DERNIER (#7).
`IdunBattle.AI.Tactics.ABaseAiActorTactic$$GetDefaultActiveAbilityActionGenerators` crée cette liste dans cet ordre exact ; le tactic
prend la 1re action non-nulle. => **toute NonComparable précède toute Comparable** : une NC bat une
attaque de plus forte utilité PAR L'ORDRE DES GÉNÉRATEURS, pas par l'utilité (preuves live seed777 :
step7 FightingRetreat u=2 vs attaque u=102 ; step10 BloodyFury ; step14 summon). Le gate par-playbook
(seuil `Fix64` du cctor : FightingRetreat>=2, AberrantHypermorph>=1, …) décide si la NC « sort » de son
générateur ; sinon on descend au tier suivant, puis au fallback Comparable.

Le SCORING Comparable est dispatché par playbook (`engine.playbook` : NormalAttack/Default/Heal),
chacun déléguant sa prédiction à `engine.playbook.prediction` (modèle objet). Intra-générateur :
argmax d'utilité faisable (`Bucket` `default`), seuil par-playbook comme gate.

NB : sur seed777, les 4 NonComparable présentes (BloodyFury/Vexilla/FightingRetreat/AberrantHypermorph)
sont priorité 0 -> seul le générateur #3 (dict[0]) tire côté NC. Mais l'ordre inter-tier EST exercé en
général : **22 des 257 ActiveAbilityType surchargent `get_Priority`** (slot-0 de l'interface, dispatch
`FUN_180002560(0, interface, playbook)`), toutes NonComparable — table
`engine.playbook.noncomparable.NATIVE_PRIORITY`, sweep exhaustif #170. Trois sont portées : NovaBoost
1192 = 1000, ThriceBlessedConflagration 1187 = 100, NovaShield 1194 = -1000. Dans un MÊME tier, deux
NonComparable d'une même unité se départagent par UTILITÉ (argmax intra-tier `choose_action`).

⚠ L'affirmation antérieure « AUCUN playbook n'override `get_Priority` » (#115) était un FAUX NÉGATIF de
méthode : les corps `mov eax,imm32 ; ret` sont dédupliqués par IL2CPP, donc ni Ghidra ni `methods.tsv`
(indexé par RVA, sans doublon) ne les exposent tous. Détail en tête de
`engine/playbook/noncomparable/_base.py`.
"""
from __future__ import annotations

import sys
from fractions import Fraction

import hexgeo
import gameconfig as gc
from engine import move
from engine import battle_query as bq          # is_adjacent (élévation-gaté) — cibles heal SpiritLeech (#84)
from engine.entities.active_ability_type import ActiveAbilityType   # #270-r1-r1
from engine.playbook import noncomparable as playbooks
from engine.playbook import get_playbook_or_default, tile_utility
from engine.playbook.base import NO_ACTION   # sentinelle `BaseUtility` -> Nullable VIDE (#27-4g)
from engine.playbook.common import (HEAL_PLAYBOOK, HEAL_PLAYBOOKS, TWISTED_SCIENCE_HEAL_PLAYBOOK,
                                    normal_attack_playbook)
from engine.playbook.bespoke import BESPOKE_SELFCAST   # #82 : BloodChalice/MomentShackle self-cast
from engine.playbook.nonattack import nonattack_candidates  # #27-4b : route Comparable SANS prédiction
from engine.playbook.excruciating_frequencies import excruciating_frequencies_candidates  # #56-t3b : 1197 ligne-AoE tuile
from engine.predict import (repair_utility, repair_amount_weapon,  # RepairedAmountUtility + magnitude ARME (#45d)
                            predict_heal_effective, heal_amount_config,   # magnitude soin OFFLINE (#79)
                            heal_amount_weapon,        # #45c : branche ARME REELLE de HealAmount
                            heal_amount_for_ability,   # #27-1212 : dispatch NATIF de HealAmount par classe
                            predict_repair_effective, repair_amount_config,  # magnitude repair OFFLINE (#83)
                            repair_amount, calculate_repair_modifier_for_prediction,  # RepairModifier cible (#45d)
                            heal_utility)             # HealUtility — terme lifesteal SpiritLeech (#84)
from engine.entities.stats import StatType, StatPart   # Attack INITIALE de la cible (magnitude #85)
from engine.entities.effect_type import EffectType     # #158 : ids d'effet -> enum natif
from engine.entities.effects.magnitude import ability_var   # maxDmg/dmgPct GalvanicField (#85)
from engine.services.min_max_damage import min_max_avg  # `MinMaxDamage$$Avg` (#333) — lifesteal SpiritLeech (#339)
from engine.dsl.base import _round_fix64   # `AAmountFormula$$RoundFix64Result` — PercentageOf(roundUp=1)
from engine.ai.bucket import Action, Bucket
from engine.ai import cast_positions          # #350-r3a-r4 : FOYER des positions non tronquees
                                              # (forme B -- liaison de MODULE, substituable)
from engine.services.trait_damage_limits import get_group_unit_heal_limit


# RepairPlaybook GENERIQUE IdunBattle.AI.Playbook.Common.RepairPlaybook$$.ctor — identifiee par ID (PAS `"Repair" in name` : R2 ce substring
# captait aussi NanoscarabRepairProtocols(1224), NonComparablePlaybook IdunBattle.AI.Playbook.Loki.NanoscarabRepairProtocolsPlaybook$$.ctor -> mauvais routage).
# Repair(28) SEUL = repair Comparable generique (magnitude hpToRepair, RepairedAmountUtility seule ;
# necroReanimator/ReanimationBeam...). Repair_GalvanicField(1119) = playbook BESPOKE distinct
# (`Repair_GalvanicFieldPlaybook IdunBattle.AI.Playbook.Loki.Repair_GalvanicFieldPlaybook$$.ctor` : magnitude % Attack-CIBLE + terme CustomUtility) ->
# route dediee `_repair_galvanic_candidates` (#85), PAS ce set generique. (1224 = NonComparable-repair,
# exclu ; 82/84 = IDs inexistants dans l'enum, retires -- validateur.)
# #270-r1-r1 : membre nomme (`Repair(28)` est deja ecrit dans la prose ci-dessus).
_COMPARABLE_REPAIR_IDS: "frozenset[int]" = frozenset({ActiveAbilityType.Repair})   # 28
_GALVANIC_REPAIR_ID = ActiveAbilityType.Repair_GalvanicField   # Repair_GalvanicField (bespoke Comparable, admecManipulus/Loki) — #85
_SPIRITLEECH_ID = ActiveAbilityType.SpiritLeech       # SpiritLeech (tyranNeurothrope/Loki) — attaque psychique per-ennemi + lifesteal (#84)
_SPIRITLEECH_HEAL_FACTION = "Tyranids"   # IdunBattleLogic.Entities.Abilities.Active.Loki.SpiritLeechAbility$$GetHealTargets : faction 0xc (self + amis Tyranids adjacents)


_FACTION_CACHE: dict = {}


def _faction(visual_id) -> str | None:
    """FactionId gameconfig d'une unité par visualId (cache). Pour le bonus heal
    `HasFaction(15)` = Genestealers (cf. dump.cs UnitFaction.Genestealers=15)."""
    if not visual_id:
        return None
    if visual_id in _FACTION_CACHE:
        return _FACTION_CACHE[visual_id]
    f = None
    try:
        uid = gc.resolve_unit_id(visual_id)
        u = gc.unit(uid) if uid else None
        f = (u or {}).get("FactionId")
    except Exception:
        f = None
    _FACTION_CACHE[visual_id] = f
    return f


# #60 : cap groupe des prédictions soin/repair (`IdunBattle.Core.Services.DamagePrediction$$GetGroupUnitHealLimit`). Dans le natif il
# est GATE par un flag d'APPEL de `IdunBattle.Core.Services.DamagePrediction$$PredictHeal` (param_6==1) / `IdunBattle.Core.Services.DamagePrediction$$PredictRepair`
# (param_7==1) — non lisible statiquement (façades virtuelles), DISCRIMINÉ live (probe_60_swarm,
# runner 25 seed 60004) : scarab 2218 hpMax à hp=888 = PILE la frontière de membre (at_limit=True,
# group_limit=0) → `aiPlaybookPredict.repairs.hpFill = 1330` (= missing ENTIER, NON capé) et
# `pairUtility = 59.9369 = 1330/2219×100` EXACT, pour Repair 28 ET Repair_GalvanicField 1119 ;
# éligibilité (`EntityCanBeRepaired`, abilityTargets) : cible at-limit LÉGALE → gate flag 0 aussi.
# Cohérent i2 Swarm : « Healing this unit can revive dead members ». ⇒ flags OFF sur les chemins IA ;
# la plomberie (helpers + group_limit) reste en place pour un futur chemin natif à flag 1.
_HEAL_GROUP_CAP = False
_REPAIR_GROUP_CAP = False


def _group_heal_limit(visual_id, hp_max: int, hp_cur: int) -> int | None:
    """`IdunBattle.Core.Services.DamagePrediction$$GetGroupUnitHealLimit` pour une cible identifiée par son visualId : None pour un
    héros (nrOfMembers<2 -> int.MaxValue natif = pas de cap ; on omet le min). nrOfMembers de BASE =
    gameconfig (NumberOfMembersComponent+0x10), hpMax = HealthComponent max (observeBattle.hpMax)."""
    if not visual_id:
        return None
    try:
        uid = gc.resolve_unit_id(visual_id)
        u = gc.unit(uid) if uid else None
        n = int((u or {}).get("nrOfMembers") or 1)
    except Exception:
        return None
    if n < 2:
        return None
    return get_group_unit_heal_limit(int(hp_max), n, int(hp_cur))


class ActionGenerator:
    """Base d'un générateur : `generate(ctx) -> action|None`. None = ce générateur n'a produit
    aucune action légale (le tactic passe au suivant)."""

    def generate(self, ctx) -> dict | None:
        raise NotImplementedError


class ActiveAbilityActionGenerator(ActionGenerator):
    """Base commune aux générateurs qui MIRRORENT
    `IdunBattle.AI.ActionGenerators.ActiveAbilityActionGenerator` — les 5 tiers NonComparable ET le
    tier Comparable. `IdunBattle.AI.Tactics.ABaseAiActorTactic$$GetDefaultActiveAbilityActionGenerators`
    en instancie SIX de cette MÊME classe ; le `MovementActionGenerator` en est une AUTRE, et c'est
    exactement ce qui rend le gate ci-dessous asymétrique (les abilities sont coupées, le mouvement
    reste)."""

    def unit_action_gate(self, ctx) -> bool:
        """PREMIÈRE instruction de l'état 0 de
        `IdunBattle.AI.ActionGenerators.ActiveAbilityActionGenerator.u003CGenerateActionsu003Ed__7$$MoveNext` :

            if (IdunBattle.Entities.UnitExtensions$$HasFlag(<unit @+0x20>, 2)) return 0;

        `UnitFlag.ActiveAbilityUsed = 2` (cf. `UnitFlagsComponent.ACTIVE_ABILITY_USED`). Le générateur
        rend alors ZÉRO action — AVANT `GetUnitAbilitiesInOrder`, donc l'attaque NORMALE tombe avec
        les actives (elles vivent dans la même liste, cf. #64). Le tactic passe au générateur suivant
        et finit sur `MovementActionGenerator`, qui n'est PAS de cette classe : une unité qui a déjà
        consommé son action peut encore SE DÉPLACER, et rien d'autre.

        Poseur natif du flag : `UseActiveAbilityBehaviour`/`ActiveAbilityOperation` via
        `AActiveAbility.SetsActiveAbilityUsedFlag` (cf. `runner/abilities/base.py`) ; purge à l'entrée
        de tour par `IdunBattle.Entities.Components.UnitFlagsComponent$$RemoveTurnFlags`.

        TRI-ÉTAT (`Scene.has_used_active_ability`) : `None` = capteur `unitFlags` non mesuré -> on NE
        COUPE PAS (comportement strictement antérieur). Couper sur une non-mesure supprimerait des
        attaques légitimes, ce qui est la dégradation dangereuse ; laisser passer ne fait que
        conserver le défaut connu."""
        scene = getattr(ctx, "scene", None)
        if scene is None:
            return True
        return not bool(scene.has_used_active_ability(ctx.uid))


class NonComparableGenerator(ActiveAbilityActionGenerator):
    """UN générateur NonComparable de tier `priority` (= `dict[get_Priority]`, `IdunBattle.AI.Tactics.ABaseAiActorTactic$$InitAbilityTypeLists`). Évalue les abilities NonComparable de l'unité DE CE TIER ; chaque
    `<Playbook>.EvaluateNonComparable` score une heuristique ENTIÈRE (pas de terme Tile7), gate par
    `MIN_UTILITY` (seuil du cctor). `choose_action(priority=…)` = `Bucket.ChooseAction` (argmax STRICT).
    Le tactic instancie 5 de ces générateurs [1000,100,0,-100,-1000], tous AVANT le fallback Comparable
    -> une NC qui « sort » prime sur toute attaque (preuves seed777 : step7 FightingRetreat u=2 vs
    attaque u=102 ; step10 BloodyFury ; step14 summon)."""

    def __init__(self, priority: int = 0):
        self.priority = priority

    def generate(self, ctx) -> dict | None:
        if not self.unit_action_gate(ctx):
            return None                    # HasFlag(unit, ActiveAbilityUsed=2) -> generateur MUET
        nc_ctx = playbooks.NCContext(
            uid=ctx.uid, origin=ctx.origin, reach_nc=ctx.reach_nc, epos=ctx.epos, fpos=ctx.fpos,
            enemies=ctx.enemies,   # id+pos (meme ordre que epos) -> cible Gauntlets (#117)
            neigh_by_pos=ctx.neigh_by_pos,   # voisins ordre natif -> cible EXACTE Gauntlets (#117)
            walkable_by_pos=ctx.walkable_by_pos,   # gate statique placement CanAddUnit (HammerOfWrath #116)
            plan=ctx.plans.get(ctx.uid) or {}, plans=ctx.plans, hp_cur_by_id=ctx.hp_cur_by_id,
            elev_by_pos=ctx.elev_by_pos, ability_targets=ctx.ability_targets,
            is_wall_by_pos=getattr(ctx, "is_wall_by_pos", None) or {},   # volet MURS de la ligne de vue (#433-r4-r2-r1-r2)
            is_in_fog_by_pos=getattr(ctx, "is_in_fog_by_pos", None) or {},   # 2e volet d'IsWalkable -> GetTilesInRange (#433-r4-r2-r1-r2-r2-r1)
            wt=ctx.wt, is_temporary_by_pos=ctx.is_temporary_by_pos,
            effects_by_pos=ctx.effects_by_pos, obs_units=ctx.obs_units,
            current_player=getattr(ctx, "cur", None),   # TurnComponent._currentPlayerId ->
            #      `BattleQuery$$IsTurnOfUnit` (prefixe de `CasterHasNotMoved`, #447-r1-r1-r3)
            tile_id_by_pos=ctx.tile_id_by_pos, active_levels=ctx.active_ability_levels,
            ability_config=ctx.heal_config,   # {"active","passive","multiplier"} (ReachedSummonCap #38)
            units=ctx.units, cast_from_tiles=ctx.cast_from_tiles, scene=ctx.scene,
            # #979 : le MEME callable que porte `AiDecisionContext` (cascade 4 etages, tri-etat) --
            # `IsPositionMachineForCurrentPlayer(2)` de `DevastatingRefrainAbility$$GetShape`.
            machine_of_war_position=ctx.machine_of_war_position,
            # #945-r2 -- le kit DECLENCHE RUNTIME (`unitAbilityStates`), MEME canal que celui que
            # `utilities/tile.py::_adjacent_units` consomme deja. `getattr` : un contexte de test qui
            # ne porte pas la methode laisse le champ a `None`, donc le repli kit gameconfig.
            triggered_kits=getattr(ctx, "live_triggered_kits", None),
            # #1027-r5 -- les DEUX entrees de `BattleQuery$$HasMinimumRemainingTurns` (slot 0x1b),
            # gate AMONT de 1174/1094. Elles ne sont MESUREES que sur le chemin offline (le `State`
            # porte la BC et le compteur) ; en LIVE elles restent `None` et le foyer applique sa
            # cascade -- statu quo EXACT, jamais un plafond devine.
            victory_conditions=getattr(ctx, "victory_conditions", None),
            turns_ended_by_first_player=getattr(ctx, "turns_ended_by_first_player", None),
            debug=ctx.debug)
        bc = playbooks.choose_action((ctx.me or {}).get("abilities") or [], nc_ctx,
                                     priority=self.priority)
        if bc is None:
            return None
        return {"kind": "ability", "target": bc["target"], "ability": bc["ability"],
                "to": bc["to"], "util": bc["pred"]}


class ComparableAbilityGenerator(ActiveAbilityActionGenerator):
    """Tier Comparable (attaque normale INCLUSE + spéciales d'attaque + soins). DISPATCHE par playbook :
    `LoadPlaybook(ability)` (NormalAttack pour l'attaque normale, Default/spéciale sinon) puis
    `playbook.calculate_action_utility(ctx, tuile, cible)` (= `IdunBattle.AI.Playbook.ComparablePlaybooku003C__Il2CppFullySharedGenericTypeu003E$$EvaluateInternal` :
    prédiction déléguée à PV + Σ + Tile(7) + gate ShouldExecute). Sweep de position par paire
    (ability,cible) [argmax tile STRICT] -> argmax inter-ability -> pool attaque+soin -> `Bucket.ChooseAction`.

    `ability_ids` = mirror du 1er argument d'`IdunBattle.AI.ActionGenerators.ActiveAbilityActionGenerator$$.ctor`
    (`OrderedSet<int>`, rangé à `generator+0x28`), que
    `...ActiveAbilityActionGenerator.u003CGenerateActionsu003Ed__7$$MoveNext` teste sur CHAQUE ability de
    `GetUnitAbilitiesInOrder` : `if (!abilityIds.Contains(abilityType)) continue`. `None` = le set du tier
    Comparable construit par `IdunBattle.AI.Tactics.ABaseAiActorTactic$$GetDefaultActiveAbilityActionGenerators`
    (`special`), que le port n'énumère pas -> aucun filtre, comportement historique du tactic complet.
    Un set EXPLICITE est ce qu'alloue `IdunBattle.AI.Tactics.DefaultAiUnitTactic.u003CCalculateAbilityActionForUnitu003Ed__6$$MoveNext`
    (`new OrderedSet<int>(); Add(abilityId)` -> UNE seule ability) — cf. `tactic.calculate_ability_action_for_unit`."""

    def __init__(self, ability_ids=None):
        self.ability_ids = None if ability_ids is None else frozenset(int(a) for a in ability_ids)

    def _in_ability_set(self, ability_id) -> bool:
        """`abilityIds.Contains(abilityType)` (`generator+0x28`). Set absent -> pas de filtre."""
        return self.ability_ids is None or int(ability_id) in self.ability_ids

    def _action_utility(self, ctx, pb, ab, tgt, tile):
        """Utilité d'ACTION d'un candidat (ability, cible, tuile) — un tour de la boucle CIBLE de
        `IdunBattle.AI.Playbook.ComparablePlaybooku003C__Il2CppFullySharedGenericTypeu003E$$EvaluateInternal`.

        Renvoie `(u_action, u_full, u, pred, aoe, bk)` ou None (le natif ne pousse rien dans son
        `Bucket` quand `CalculateActionUtility` rend un `Nullable` vide).

        `u_action` = `BucketAction.Utility` = `u_full + CalculateCustomUtility` (#64 : base 0
        `…ComparablePlaybook…$$CalculateCustomUtility`, NormalAttack +1
        `IdunBattle.AI.Playbook.Loki.ALoki_NormalAttackPlaybooku003C__Il2CppFullySharedGenericTypeu003E$$CalculateCustomUtility`).
        Le custom est SOMMÉ DANS `…$$CalculateActionUtility` (avant le terme Tile), donc AVANT tout
        argmax -> il doit entrer dans CE comparatif, pas être ajouté après (sinon un custom
        POSITION-dépendant — Drachnyen `IdunBattle.AI.Playbook.Loki.DrachnyenPlaybook$$CalculateCustomUtility` — ne peut jamais changer la tuile choisie).

        ORDRE : le natif calcule le custom EN PREMIER et teste ses trois valeurs SENTINELLES avant
        d'appeler `CalculateUtilityFromPredictions`. Deux d'entre elles rendent un `Nullable` VIDE,
        c.-à-d. AUCUNE action pour ce (tuile, cible) — cf. `playbook.base.NO_ACTION`, que le port
        laisse rendre à `calculate_custom_utility`. Ce chemin est INERTE pour tous les playbooks dont
        le custom est numérique (la quasi-totalité) ; seul `PlasmaGrenadePlaybook` (1098) l'emprunte."""
        custom = pb.calculate_custom_utility(ctx, tile, tgt, ab)
        if custom is NO_ACTION:
            return None                # `CalculateActionUtility` rend un Nullable VIDE -> pas d'action
        cand = pb.calculate_action_utility(ctx, tile, tgt, ab)
        if cand is None:
            return None
        u_full = cand["u_full"]
        u_val = cand["u"]
        # #84 : le terme LIFESTEAL de `1104 SpiritLeech` était sommé ICI, au RETOUR de
        # `calculate_action_utility` — donc APRÈS le gate `ShouldExecute`, alors que le natif le
        # folde DEDANS (`SpiritLeechPlaybook$$MakeHealPredictions` -> 2ᵉ boucle de
        # `CalculateUtilityFromPredictions`, slot +0x368). Il vit désormais à son RANG, dans
        # `playbook.spirit_leech.SpiritLeechLifestealPlaybook.make_heal_predictions`
        # (#419-r1-tr14-r5-r2-r1-r1-r3). L'utilité finale est inchangée (l'addition commute) ;
        # ce qui change, c'est l'étage `u` (que `pairUtility` confronte) et l'argument du gate.
        u_action = u_full + custom
        return (u_action, u_full, u_val, cand["pred"], cand["aoe"], cand["bk"])

    def _sweep_tiles(self, ctx, rk_tiles_union) -> list:
        """Positions candidates DANS L'ORDRE NATIF (R1-b). Mirror de la liste `tiles` que
        `IdunBattle.AI.Tactics.DefaultAiUnitTactic.u003CCalculateNextActionForUnitu003Ed__5$$MoveNext`
        passe à chaque générateur, c.-à-d. `ctx.action_tiles` (cf. `engine.ai.context.action_tiles_for`).

        Chaîne d'ORDRE, lue au décompilé (gqfc5mff6c) et CONFIRMÉE live :

        - `IdunBattle.Core.Services.BattleQuery$$GetCurrentAndMovablePositionsFor` seede un
          `OrderedSet<UnitPosition>` avec `GetUnitPosition(unit)` puis `UnionWith(GetMovablePositionsFor(…))`
          -> ORIGINE EN TÊTE ;
        - `IdunBattle.Core.Services.MovementQuery$$GetMovablePositionsFor` = `GetMovableTilesFor` puis
          `UnionWith(EntityExtensions.IterateTiles(unit))` (⚠ **UnionWith**, pas `ExceptWith` : c'est le
          MÊME method-info que le `param_8.UnionWith(accumulé)` final d'`…$$AnyOrFillMoveableTiles`, dont
          la cible est un `OrderedSet` VIDE — un `ExceptWith` y rendrait toujours l'ensemble vide) puis
          `GetMovablePositionsFromTiles(tiles, feetCount)` ;
        - `IdunBattle.Core.Services.MovementQuery$$GetMovablePositionsFromTiles` à `feetCount == 1` =
          `IdunBattle.Core.UnitPositionExtensions$$ToUnitPositionList` = boucle `for i in 0..Count-1` sur
          la LISTE de l'`OrderedSet` -> ORDRE PRÉSERVÉ ;
        - `idun.shared.collections.OrderedSetu003C__Il2CppFullySharedGenericTypeu003E` EST une `List<T>`
          (+ `HashSet<T>` @+0x28) : `$$Add` = `hashSet.Add` puis `List.Add` (ordre d'INSERTION),
          `$$UnionWith` -> `$$SyncListWithSet` APPEND les manquants dans l'ordre de la source, et
          `$$RemoveExtraEntriesFromList` supprime À REBOURS par `List.RemoveAt` (ordre des survivants
          préservé).
        ⇒ ordre natif = `[origine] + ordre d'insertion de GetMovableTilesFor` = EXACTEMENT ce que le RPC
        `aiMovableTiles` expose (il appelle le MÊME `GetMovableTilesFor` et lit la MÊME `List<T>`).

        CONFIRMÉ LIVE (`probe_r1b_native_sweep_order.py`, C4_09/999 pas 14, `templAncient`) : la séquence
        des tuiles caster vues par `IdunBattle.AI.Playbook.ComparablePlaybooku003C__Il2CppFullySharedGenericTypeu003E$$CalculateActionUtility`
        est `[(5,5),(5,6),(6,4),(4,4),(4,3),(3,5),(3,6),(5,3),(3,3),(2,4),(2,6)]` = `action_tiles`
        À L'IDENTIQUE, et ce N'EST PAS l'ordre `ranked` (`GetBestTileToAttackFrom`, qui classe par une
        utilité de MOUVEMENT et ne sert nulle part dans le générateur d'action).

        `rk_tiles_union` = les tuiles LÉGALES vues dans les `ranked` du plan ; celles qui manqueraient à
        `action_tiles` sont mises en queue (ne doit pas arriver : `ranked` est construit sur
        `GetMovableTilesFor` + `mainTile`, cf. `projection.ts::computeAttackPlans`)."""
        at = [t for t in (ctx.action_tiles or []) if t and t[0] is not None]
        seen = set(at)
        return at + [t for t in rk_tiles_union if t and t[0] is not None and t not in seen]

    def _best_attack(self, ctx):
        """Sweep attaque : renvoie `best = (u, u_action, target, ability, tile)` ou None.

        MIRROR 1:1 des TROIS boucles imbriquées natives, keep-first (`>` STRICT) à chaque étage :

            `IdunBattle.AI.ActionGenerators.ActiveAbilityActionGenerator.u003CGenerateActionsu003Ed__7$$MoveNext`
                foreach ability in `…ActiveAbilityActionGenerator$$GetUnitAbilitiesInOrder`   <- MAJEURE
                    foreach position in `tiles`                                               <- MÉDIANE
                        `Bucket.Merge`(bucket, playbook.Evaluate(unit, position, ctx))
            `IdunBattle.AI.Playbook.ComparablePlaybooku003C__Il2CppFullySharedGenericTypeu003E$$EvaluateInternal`
                    foreach target in `IdunBattle.AI.Playbook.BasePlaybook$$GetEligibleTargetsEntities` <- MINEURE
                        if (utility > best) best = action
            `IdunBattle.AI.BucketSystem.Bucketu003C__Il2CppFullySharedGenericTypeu003E$$AddAction`
                seede le 1er ajouté, ne remplace que sur `>` STRICT.

        C'est la POSITION qui domine la CIBLE, pas l'inverse : à utilité d'action égale entre deux
        (cible, tuile) d'une même ability, c'est la TUILE énumérée la première qui gagne. L'ordre des
        tuiles vient de `_sweep_tiles` (origine en tête puis l'ordre de `GetMovableTilesFor`).

        L'utilité comparée est celle d'ACTION `u_full + CalculateCustomUtility` (#64 : la normale porte
        +1 -> elle bat tout actif Comparable à Δ(pair+tile) < 1 ; couvre l'ancien tie exact step-9
        seed777 (69 vs 1067 même u_full) ET 2468 s18 (69 vs 1191, Δpair=0.75))."""
        plan = ctx.plans.get(ctx.uid) or {}
        best = None       # (u, u_action, tgt, ab, tile)
        best_key = None
        # #57g : ordre d'énumération des CIBLES (boucle MINEURE). `EvaluateInternal` compare en STRICT
        # `op_GreaterThan` dans l'ordre de `IterateSurroundingTiles` (lex cube (x,y) croissant, cf.
        # bq.iterate_surrounding_tiles_order_key) -> à utilité égale DEPUIS LA MÊME tuile d'attaque, la
        # cible au plus petit rang cube gagne (12345 s15 : t83(2,-7) bat t81(2,-6) à 167.8599 exact).
        # Ici le tri des `evals` par ce rang REND cette règle structurelle (keep-first suffit).
        tgt_pos_by_id = {e.get("id"): (e["pos"]["col"], e["pos"]["row"])
                         for e in (ctx.enemies or [])
                         if isinstance(e, dict) and (e.get("pos") or {}).get("col") is not None}
        # Regroupement ABILITY-MAJEUR : `plan["evals"]` est déjà produit ability-major puis cible
        # (`projection.ts::computeAttackPlans` boucle `abilities` x `enemies`) — mirror de l'ordre de
        # `GetUnitAbilitiesInOrder`. On préserve l'ordre de PREMIÈRE apparition de chaque ability.
        by_ab: dict = {}
        ab_order: list = []
        for ev in (plan.get("evals") or []):
            if not ev.get("rankCount") or not (ev.get("ranked") or []):
                continue
            ab = ev.get("abilityId")
            # `if (!abilityIds.Contains(abilityType)) continue` — le filtre `generator+0x28` du natif,
            # inerte quand le set est absent (tier Comparable complet).
            if not self._in_ability_set(ab):
                continue
            # #15 : une ability NonComparable (ex. HeroicFusillade 1180) est rangée par
            # `IdunBattle.AI.Tactics.ABaseAiActorTactic$$InitAbilityTypeLists` dans le tier NonComparable SEUL (flag IsComparable) ->
            # JAMAIS évaluée par le tier Comparable, même si elle figure dans les attackPlans (dégât).
            # Sans ce skip, le fallback générique la repêcherait ici alors que son playbook NC a gaté (=[]).
            if playbooks.is_noncomp(ab):
                continue
            if ab not in by_ab:
                by_ab[ab] = []
                ab_order.append(ab)
            by_ab[ab].append(ev)
        dbg = []
        for ab in ab_order:
            # LoadPlaybook : attaque normale -> le playbook de SON identité (générique ou boss, cf.
            # `common.normal_attack_playbook` — les deux ne diffèrent que par `ShouldExecute`) ;
            # sinon fallback/spéciale.
            pb = normal_attack_playbook(ab) if ab in ctx.normal_ids else get_playbook_or_default(ab)
            evs = sorted(
                by_ab[ab],
                key=lambda ev: (0, bq.iterate_surrounding_tiles_order_key(tgt_pos_by_id[ev["targetId"]]))
                if ev.get("targetId") in tgt_pos_by_id else (1, ()))
            # #350-r3a-r4 -- LE GATE DE POSITION PASSE PAR LE FOYER, plus par `ranked` brut.
            # `computeAttackPlans` TRONQUE (`for (let r = 0; r < maxRank; r++)`), plafond absent
            # du natif : a `maxRank=6` (defaut du RPC `decisionView`) 21 positions sur 33
            # disparaissent, et `tile not in legal[tgt]` REFUSE alors une attaque que le natif
            # autorise -- le tier COMPARABLE couvre TOUTES les attaques, attaque normale comprise,
            # donc c'est le site le plus expose des six. Le foyer est TRI-ETAT : `rankComplete`
            # vrai (face COMBAT, `state_bridge`) -> `ranked` tel quel, zero RPC.
            legal = {ev.get("targetId"): cast_positions.positions_castables(
                         ev, getattr(ctx, "cast_from_tiles", None), ctx.uid,
                         ev.get("targetId"), ab, ctx.origin)
                     for ev in evs}
            # union des tuiles LEGALES, dans l'ordre `ranked` de premiere apparition (deterministe :
            # `legal` est un set, il ne peut pas porter d'ordre) -- ne sert qu'au filet de queue.
            union, seen_u = [], set()
            for ev in evs:
                for rk in (ev.get("ranked") or []):
                    t = (rk.get("col"), rk.get("row"))
                    if t not in seen_u:
                        seen_u.add(t)
                        union.append(t)
            for tile in self._sweep_tiles(ctx, union):
                # `EvaluateInternal` à POSITION FIXE : argmax sur les cibles, keep-first STRICT.
                tile_best = None   # (u_action, u_full, u, pred, aoe, tgt, bk)
                for ev in evs:
                    tgt = ev.get("targetId")
                    if tile not in legal[tgt]:
                        continue          # attaque illégale depuis cette tuile -> pas d'action générée
                    cand = self._action_utility(ctx, pb, ab, tgt, tile)
                    if cand is None:
                        continue
                    u_action, u_full, u_val, cpred, caoe, cbk = cand
                    if tile_best is None or u_action > tile_best[0]:
                        tile_best = (u_action, u_full, u_val, cpred, caoe, tgt, cbk)
                if tile_best is None:
                    continue
                u_action, u_full, u, pred, aoe, tgt, bk = tile_best
                if ctx.debug:
                    p = pred or {}
                    dbg.append((ab, tgt, round(u, 1), round(u_full, 1), p.get("killSure"),
                                p.get("kill"), p.get("healthDmgMax"), p.get("hpBefore"),
                                f"aoe{len(aoe)}", tile,
                                ("sh", p.get("shieldDmgMin"), p.get("shieldDmgMax")), ("bk", bk)))
                # `Bucket.Merge` -> `AddAction` : keep-first, remplacement sur `>` STRICT.
                if best_key is None or u_action > best_key:
                    best = (u, u_action, tgt, ab, tile)
                    best_key = u_action
        if ctx.debug:
            ab_ids = [a.get("id") for a in ((ctx.me or {}).get("abilities") or [])]
            print(f"    [dbg u{ctx.uid}] abilities={ab_ids} attack_cands(ab,tgt,util,kS,k,dmax,hp)={dbg}",
                  file=sys.stderr)
            nat_dbg = [(ev.get("abilityId"), ev.get("targetId"),
                        (ev.get("ranked") or [{}])[0].get("dmgMin"),
                        (ev.get("ranked") or [{}])[0].get("dmgMax"),
                        "OPT" if (ev.get("ranked") or [{}])[0].get("predOptimistic") else "")
                       for ev in (plan.get("evals") or []) if ev.get("rankCount")]
            print(f"    [dbg u{ctx.uid}] NATIVE ranked(ab,tgt,dMin,dMax,opt)={nat_dbg}", file=sys.stderr)
        return best

    def _spiritleech_lifesteal_util(self, ctx, tile_T, cand_pred) -> float:
        """Terme LIFESTEAL de `IdunBattle.AI.Playbook.Loki.SpiritLeechPlaybook$$MakeHealPredictions` (Comparable id 1104,
        tyranNeurothrope/Loki) → `GenerateHealPredictions` → Σ `CalculateUtilityFromHealEvent`, SOMMÉ au
        dégât (+ effet Pinned=0, inerte ce build) par `IdunBattle.AI.Playbook.ComparablePlaybooku003C__Il2CppFullySharedGenericTypeu003E$$CalculateActionUtility`.

        - lifesteal = `IdunBattleLogic.Entities.Abilities.Active.Loki.SpiritLeechAbility$$GetHealAmountForPrediction`
          = `PercentageOf(DamagePredictionFormula(…), ConfigVar 0x4b, roundUp=1)` — le `roundUp=1` est le
          mode `Ceiling` de `IdunBattle.DSL.AAmountFormula$$RoundFix64Result`.
          `hpToHealPct` ∈ [40..60] au niveau ACTIF du caster (PAS rarity-scaled).
          **#339 — le montant moyenné est `AccurateHealthDamage`, une seule fois, arrondi
          demi-vers-le-pair.** `IdunBattle.Entities.Formulas.DamagePredictionFormula$$Calculate` finit par
          `MinMaxDamage$$Avg(prediction + 0x40)` quand `prioritizeKills@+0x54` est FAUX — et
          `GetHealAmountForPrediction` passe bien `false` (10ᵉ arg de
          `IdunBattle.Entities.Formulas.DamagePredictionFormula$$.ctor`). Donc : bornes CAPÉES aux PV
          (`healthDmgMin/Max`), PAS les bornes BRUTES (`DefaultScenario` @+0x14 = `rawHealthDmg*`), et
          AUCUN terme de BOUCLIER. Le port lisait les trois de travers ; mesuré live (probe_339,
          bornes brutes `[2758,4139]` capées à `[2758,2765]`) : **4.83 points d'utilité** d'écart.
        - cibles = `IdunBattleLogic.Entities.Abilities.Active.Loki.SpiritLeechAbility$$GetHealTargets` = SELF ∪ (amis ADJACENTS à `tile_T`, faction Tyranids(0xc)).
        - Σ par cible : eff = `PredictHeal` = min(lifesteal, PV manquants) ; `HealUtility` = eff/(maxHP+1)×100
          (is_friend=True). Position-dépendant (adjacence des alliés à la tuile de cast `tile_T`)."""
        me = ctx.me
        if me is None or not cand_pred:
            return 0.0
        # `DamagePredictionFormula.Calculate` -> `MinMaxDamage$$Avg(AccurateHealthDamage@+0x40)`
        # (#339) : bornes CAPÉES, un SEUL arrondi demi-vers-le-pair, aucun bouclier.
        # ⚠ Pas de court-circuit `LimitedByMinHp` ici — `DamagePredictionFormula$$Calculate` lit
        # `+0x40` en direct (contrairement à `IdunBattle.AI.Utilities.DamageUtility$$GetHealthDamage`).
        dmg = min_max_avg(cand_pred.get("healthDmgMin") or 0, cand_pred.get("healthDmgMax") or 0)
        if dmg <= 0:
            return 0.0
        hc = ctx.heal_config(ctx.uid)
        pct = ability_var("SpiritLeech", "hpToHealPct", hc["active"], multiplier_pct=hc["multiplier"]) or 0
        # `PercentageOf(dmg, pct, roundUp=1)` -> `RoundFix64Result(mode 1 = Ceiling)`.
        lifesteal = _round_fix64(Fraction(int(dmg) * int(pct), 100), 1)
        if lifesteal <= 0:
            return 0.0
        # cibles de soin : SELF + amis Tyranids ADJACENTS à la tuile de cast (GetHealTargets)
        team = me.get("team")
        heal_ids = {ctx.uid}
        for u in ctx.units:
            if u.get("id") == ctx.uid or u.get("team") != team or not u.get("alive"):
                continue
            if _faction(u.get("visualId")) != _SPIRITLEECH_HEAL_FACTION:
                continue
            p = u.get("pos")
            if p and p.get("col") is not None and bq.is_adjacent(tile_T, (p["col"], p["row"]), ctx.elev_by_pos, bq.neigh_map(ctx)):
                heal_ids.add(u.get("id"))
        obs_by_sq = {u.get("squadId"): u for u in ctx.obs_units}
        total = 0.0
        for hid in heal_ids:
            ob = obs_by_sq.get(hid) or {}
            hp_max = int(ob.get("hpMax") or 0)
            hp_cur = int(ob.get("hp") or 0)
            if hp_max <= 0:
                continue
            eff = min(lifesteal, max(0, hp_max - hp_cur))   # PredictHeal = min(healAmount, manquant)
            total += heal_utility(eff, hp_max, is_friend=True, is_boss=False)
        if ctx.debug:
            print(f"    [dbg spiritleech u{ctx.uid}@{tile_T}] dmg={dmg:.0f} pct={pct} lifesteal={lifesteal} "
                  f"healTargets={sorted(heal_ids)} lifestealU={total:.3f}", file=sys.stderr)
        return total

    def _heal_candidates(self, ctx) -> list:
        """Sweep soin (tile-swept) via `HealPlaybook` -> liste {target, ability, to, pred, full}.
        Énumération cibles = `abilityTargets` ; gate d'énumération « cible déjà buffée TwistedScience »
        (inconditionnel) ; utilité par cible = `HealPlaybook.score` (CustomUtility + heal_term ; gate
        pred > 0). reach = origine + tuiles de move (self depuis toute tuile, allié depuis adjacent)."""
        me = ctx.me
        heal_abis = [ab for ab in ((me or {}).get("abilities") or [])
                     if "Heal" in (ab.get("name") or "") and ab.get("usable") is not False]
        if not heal_abis:
            return []
        unit_by_id = {u.get("id"): u for u in ctx.units}
        pos_by_id = {u.get("id"): (u["pos"]["col"], u["pos"]["row"])
                     for u in ctx.units if u.get("pos") and u["pos"].get("col") is not None}
        hpmax_by_sq = {u.get("squadId"): u for u in ctx.obs_units}
        reach = ([ctx.origin] if ctx.origin is not None else []) \
            + [(t["col"], t["row"]) for t in ctx.move_tiles]
        HEAL_RANGE = 1  # gameconfig : aucun heal ciblé n'a de `range` -> adjacent
        out = []
        for ab in heal_abis:
            aid = ab.get("id")
            at = ctx.ability_targets(ctx.uid, aid)
            vts = set()
            for u in (at.get("units") or []):
                for a in (u.get("abilities") or []):
                    if a.get("abilityId") == aid:
                        for t in (a.get("targets") or []):
                            if t.get("kind") == "unit" and t.get("targetId") is not None:
                                vts.add(t["targetId"])
            is_twisted = "TwistedScience" in (ab.get("name") or "")
            pb = HEAL_PLAYBOOKS.get(int(aid)) if aid is not None else None   # 1212 -> playbook bespoke
            # Magnitude OFFLINE du soin : le natif DISPATCHE par classe d'ability (deux implementations
            # de `HealAmount` seulement, cf. `engine.predict.heal_amount_for_ability`) —
            #   MassHeal(8) -> `MassHealAbility$$HealAmount` = la variable de config `hpToHeal` ;
            #   18 / 1167 / 1212 -> `HealAbility$$HealAmount` = `StatAmount(weapon) x Max(WeaponHighestHits,1)`
            #   (= stat Damage RESOLUE du caster x hits d'arme ; #55 : le x hits est reel, Hospitaller
            #   Heal(18) 3-hit = 2008x3 = 6024).
            # Depend de l'ability + du caster, PAS de la cible -> resolu 1x. None -> saturation `missing`
            # (dernier filet : Scene absente, ou branche config sans `hpToHeal`).
            _hc = ctx.heal_config(ctx.uid)
            _actx = (ctx.scene.ctx(ctx.uid) if getattr(ctx, "scene", None) is not None else None)
            heal_amt = heal_amount_for_ability(
                aid, ab.get("name"), _hc["active"], _hc["passive"], _hc["multiplier"],
                (None if _actx is None else _actx.attack),
                (1 if _actx is None else _actx.normal_weapon_hits))
            for tg in vts:
                tu = unit_by_id.get(tg) or {}
                # gate natif `HasEffect(target, EffectType.TwistedScience_ExtraHp=1355)` sur l'état d'effets
                # STRUCTURÉ (`EffectsState`) — on colle au JEU (HasEffect sur les EffectComponent), PAS à la
                # liste sérialisée `unit["effects"]` de decisionView. Les deux chemins (live/offline) portent
                # cet état via `ctx.scene.eff_state`. Scene absente -> pas d'exclusion (no-op fidèle).
                _eff = getattr(getattr(ctx, "scene", None), "eff_state", None)
                if _eff is not None and _eff.has_effect(tg, effect_type=int(EffectType.TwistedScience_ExtraHp)):
                    continue  # cible déjà buffée (TwistedScience_ExtraHp) -> ignorée (inconditionnel)
                ob = hpmax_by_sq.get(tg) or {}
                hp_max = int(ob.get("hpMax") or 0)
                hp_cur = int(ob.get("hp") or 0)
                missing = max(0, hp_max - hp_cur)   # PV manquants = BORNE du soin effectif
                # Soin EFFECTIF = `IdunBattle.Core.Services.DamagePrediction$$PredictHeal` (IdunBattle.Entities.Components.FillUpStatComponent$$MaxFillUp) = min(healAmount, missing).
                # heal_amt None (soin non-hpToHeal) -> saturation `missing` (approximation documentee #79,
                # sans regression). Le -50/+50 friendSign + bossMod restent dans HealUtility (score).
                # #60 : cap groupe `IdunBattle.Core.Services.DamagePrediction$$GetGroupUnitHealLimit` — dans PredictHeal il est GATE
                # par le flag d'appel (`param_6 == 1`), mesuré OFF sur les chemins IA (probe_60 :
                # PredictRepair natif NON capé a la frontiere de membre ; i2 Swarm « Healing this
                # unit can revive dead members »). Plomberie en place, inerte tant que le flag est OFF.
                group_limit = _group_heal_limit(tu.get("visualId"), hp_max, hp_cur) if _HEAL_GROUP_CAP else None
                effective = (missing if heal_amt is None
                             else predict_heal_effective(heal_amt, hp_cur, hp_max, group_limit=group_limit))
                is_friend = (me is not None and tu.get("team") == me.get("team"))
                faction = _faction(tu.get("visualId"))
                if pb is None or pb is TWISTED_SCIENCE_HEAL_PLAYBOOK:
                    # 18 generique ET 1167 `Heal_TwistedScience` : MEME CustomUtility (`HealPlaybook.
                    # score`), gates `ShouldExecute` DIFFERENTS -- d'ou l'instance distincte, lue
                    # plus bas pour le gate. Cf. `playbook.common.TwistedScience_HealPlaybook`.
                    pred = HEAL_PLAYBOOK.score(effective, hp_max, is_friend, is_twisted, faction)
                    balms = None
                else:
                    # 1212 : `...HealingBalms_HealPlaybook$$CalculateCustomUtility` est GATE par
                    # `HasEffect(target, EffectType.HealingBalms_ExtraCritDamage = 0x5df)` — meme
                    # canal `EffectsState` que le gate TwistedScience ci-dessus. Ici le gate n'exclut
                    # PAS la cible (le natif calcule bien l'action, custom = 0) : il annule le terme.
                    balms = bool(_eff is not None and _eff.has_effect(
                        tg, effect_type=int(EffectType.HealingBalms_ExtraCritDamage)))
                    pred = pb.score(effective, hp_max, is_friend, balms)
                if ctx.debug:
                    print(f"    [dbg heal u{ctx.uid}->{tg}] vis={tu.get('visualId')} fac={faction} "
                          f"hp={hp_cur}/{hp_max} miss={missing} healAmt={heal_amt} eff={effective} "
                          f"twisted={is_twisted} balms={balms} pred={pred}", file=sys.stderr)
                if pred is None:
                    continue  # ShouldExecute, 1re clause : émet le soin SSI pred > 0
                # ShouldExecute, SECONDE clause -- `Common.HealPlaybook$$ShouldExecute` porte en plus
                # `!IsBoss(caster) || caster != target` (#419-r1-tr14-r5-r2-r1-r1-r1). Le dispatch
                # PAR PLAYBOOK est ce qui la rend juste : `1167`/`1212` ne l'ont PAS a leur corps
                # natif, et leurs classes la neutralisent. `pred` EST l'argument que
                # `CalculateActionUtility` passe au gate (custom + predictions).
                gate_pb = pb if pb is not None else HEAL_PLAYBOOK
                if not gate_pb.should_execute(ctx, ctx.origin, tg, aid, pred):
                    continue
                tpos = pos_by_id.get(tg)
                for T in reach:
                    if tg != ctx.uid and (tpos is None or hexgeo.distance(T, tpos) > HEAL_RANGE):
                        continue  # cible hors portée de soin depuis T (self = depuis toute tuile)
                    out.append({"target": tg, "ability": aid,
                                "to": (T if T != ctx.origin else None),
                                "pred": pred, "full": pred + tile_utility(ctx, T)})
        return out

    def _repair_candidates(self, ctx) -> list:
        """Sweep RÉPARATION GÉNÉRIQUE (tile-swept) via `RepairPlaybook` (Comparable, IdunBattle.AI.Playbook.Common.RepairPlaybook$$.ctor) -> liste
        {target, ability, to, pred, full}. MIROIR de `_heal_candidates` : identification par ID Comparable-
        repair (`_COMPARABLE_REPAIR_IDS` = {28} = Repair générique SEUL ; PAS `"Repair" in name` qui
        captait le NonComparable NanoscarabRepairProtocols(1224). Repair_GalvanicField(1119) = playbook
        BESPOKE -> `_repair_galvanic_candidates`, PAS ici) ; énumération cibles =
        `abilityTargets` ; utilité par cible =
        `repair_utility` (RepairedAmountUtility : `fill_hp/(maxHP+1)×100`, UN SEUL terme,
        PAS de friendSign — répare ses propres machines) ; gate `ShouldExecute` : pred > 0.

        MAGNITUDE — `IdunBattleLogic.Entities.Abilities.Active.RepairAbility$$RepairAmount`, DEUX branches,
        exactement comme le soin (`_heal_candidates`) :
          1. config (#83) : `hpToRepair[activeLevel]` de la clé CONCRÈTE de l'unité
             (`repair_amount_config`) — sert aux réparations Comparable à variable de config ;
          2. ARME RÉELLE (#45d, LA branche des porteurs du trait `Mechanic`) : l'arbre DSL natif est
             `Multiply(StatAmount(weapon), Max(WeaponHighestHits(weapon), Get(1)))` = attack RÉSOLUE
             du caster × max(hits d'arme, 1) — `repair_amount_weapon(ctx.attack, normal_weapon_hits)`.
             AUCUN des 5 porteurs du trait n'a de `hpToRepair` Comparable ⇒ la branche 1 rend None
             pour tous, et c'est la branche 2 qui alimente la prédiction. Avant #45d le générateur
             tombait sur la saturation `fill = missing` : mesuré FAUX live (admecDominus 5022×1 vers
             une cible à 5724 PV manquants — `pairUtility` natif 25.108745 = min(5022,5724)/20001×100,
             la saturation donnait 28.618569).
        `IdunBattle.Core.Services.DamagePrediction$$PredictRepair` remplit UNE stat via `MaxFillUp` :
        Health(5) → `fill_hp = min(repairAmount, manquant)` (`predict_repair_effective`). Le volet
        Armor n'existe pas (poids W[1] sans lecteur, un seul `MaxFillUp` natif — cf. PARTIE 4 de
        `engine/predict.py`). Saturation `fill = missing` = dernier filet, seulement si la Scene
        manque (attack indisponible)."""
        me = ctx.me
        repair_abis = [ab for ab in ((me or {}).get("abilities") or [])
                       if ab.get("id") in _COMPARABLE_REPAIR_IDS and ab.get("usable") is not False]
        if not repair_abis:
            return []
        pos_by_id = {u.get("id"): (u["pos"]["col"], u["pos"]["row"])
                     for u in ctx.units if u.get("pos") and u["pos"].get("col") is not None}
        obs_by_sq = {u.get("squadId"): u for u in ctx.obs_units}
        reach = ([ctx.origin] if ctx.origin is not None else []) \
            + [(t["col"], t["row"]) for t in ctx.move_tiles]
        REPAIR_RANGE = 1  # gameconfig : repair ciblé adjacent (pas de `range` propre observé)
        eff_by_id = {u.get("id"): (u.get("effects") or []) for u in ctx.units}  # RepairModifier cible (#45d)
        # Magnitude REPAIR OFFLINE = hpToRepair[activeLevel] × rareté (résolu 1x : dépend du caster, pas de
        # la cible). Niveau = ACTIF (réparation native, +0xB8) via heal_config (même source unitConfig).
        _rc = ctx.heal_config(ctx.uid)
        _caster_vid = (obs_by_sq.get(ctx.uid) or {}).get("visualId")
        repair_amt = repair_amount_config(_caster_vid, _rc["active"], _rc["multiplier"])
        # #45d : pas de `hpToRepair` Comparable -> branche ARME REELLE de `RepairAbility$$RepairAmount`
        # (`Multiply(StatAmount(weapon), Max(WeaponHighestHits, 1))`), le cas de TOUS les porteurs du
        # trait `Mechanic`. La saturation `missing` ne reste que si la Scene manque (dernier filet).
        if repair_amt is None and getattr(ctx, "scene", None) is not None:
            _actx = ctx.scene.ctx(ctx.uid)
            if _actx is not None:
                repair_amt = repair_amount_weapon(_actx.attack, _actx.normal_weapon_hits)
        out = []
        for ab in repair_abis:
            aid = ab.get("id")
            at = ctx.ability_targets(ctx.uid, aid)
            vts = set()
            for u in (at.get("units") or []):
                for a in (u.get("abilities") or []):
                    if a.get("abilityId") == aid:
                        for t in (a.get("targets") or []):
                            if t.get("kind") == "unit" and t.get("targetId") is not None:
                                vts.add(t["targetId"])
            for tg in vts:
                ob = obs_by_sq.get(tg) or {}
                hp_max = int(ob.get("hpMax") or 0)
                hp_cur = int(ob.get("hp") or 0)
                if repair_amt is None:   # Scene absente -> saturation (dernier filet, approx documentée)
                    fill_hp = max(0, hp_max - hp_cur)
                else:                    # PredictRepair : fill = min(repairAmount, manquant) sur Health
                    # RepairModifier (#45d) : bonus/malus des effets ACTIFS portés par la CIBLE
                    # (Nanoscarab +hpToRepair, Voltagheist ×0.5), appliqué à la base AVANT MaxFillUp
                    # (ordre natif IdunBattle.Core.Services.DamagePrediction$$PredictRepair : modifier -> caps -> min(amount, manquant)).
                    mod_add, mod_mul = calculate_repair_modifier_for_prediction(
                        eff_by_id.get(tg), ctx.heal_config)
                    # #60 : cap groupe `GetGroupUnitHealLimit` (IdunBattle.Core.Services.DamagePrediction$$PredictRepair, gate param_7)
                    # — cible multi-membres (ex. necroSmnSwarm 5 membres) -> repair « sans réveiller ».
                    _glim = (_group_heal_limit(ob.get("visualId"), hp_max, hp_cur)
                             if _REPAIR_GROUP_CAP else None)
                    rp = predict_repair_effective(repair_amount(repair_amt, mod_add, mod_mul),
                                                  hp_cur, hp_max, group_limit=_glim)
                    fill_hp = rp.fill_hp
                pred = repair_utility(fill_hp, hp_max, is_boss=False)
                if ctx.debug:
                    print(f"    [dbg repair u{ctx.uid}->{tg}] vis={ob.get('visualId')} "
                          f"hp={hp_cur}/{hp_max} repairAmt={repair_amt} "
                          f"fillHp={fill_hp} pred={pred}", file=sys.stderr)
                if pred <= 0:
                    continue   # ShouldExecute : émet la réparation SSI pred > 0
                tpos = pos_by_id.get(tg)
                for T in reach:
                    if tg != ctx.uid and (tpos is None or hexgeo.distance(T, tpos) > REPAIR_RANGE):
                        continue   # cible hors portée depuis T (self = depuis toute tuile)
                    out.append({"target": tg, "ability": aid,
                                "to": (T if T != ctx.origin else None),
                                "pred": pred, "full": pred + tile_utility(ctx, T)})
        return out

    def _repair_galvanic_candidates(self, ctx) -> list:
        """`Repair_GalvanicFieldPlaybook IdunBattle.AI.Playbook.Loki.Repair_GalvanicFieldPlaybook$$.ctor` (ComparablePlaybook<0x45f=1119>, admecManipulus/Loki)
        — réparation Comparable BESPOKE GRANTED par le passif GalvanicField. DISTINCTE du RepairPlaybook
        générique (`_repair_candidates`, id 28, magnitude hpToRepair) : magnitude ET utilité PROPRES (RE
        ghidra gqfc5mff6c). Tile-swept sur les cibles de `abilityTargets` (self + amis Mechanical, vérité
        live — le natif cible target!=caster, mais le self-repair est OBSERVÉ live seed909 step14).

        MAGNITUDE `IdunBattleLogic.Entities.Abilities.Active.Loki.Repair_GalvanicFieldAbility$$GetOverrideAttackDamageAmount` = `IdunBattleLogic.Entities.DSLFactory$$PercentageOfAttackCappedAtMax`
        = `M = min(round(cible.Attack_INITIALE × dmgPct/100), maxDmg)` — % de l'Attack INITIALE de la
        CIBLE réparée (`StatType=Attack`, `StatPart=Initial` ; le « 100% of *its own* Damage » du tooltip),
        plafonnée à `maxDmg`. `dmgPct`/`maxDmg` = vars du passif GalvanicField au niveau PASSIF du CASTER
        (`maxDmg` seule rarity-scaled). PAS `hpToRepair`.

        UTILITÉ `IdunBattle.AI.Playbook.ComparablePlaybooku003C__Il2CppFullySharedGenericTypeu003E$$CalculateActionUtility` (chemin repair) = SOMME de deux termes (lu dans le
        décompilé, ADDITIFS) : (1) `RepairedAmountUtility` générique = `repair_utility(fill_hp, maxHP)`
        avec `fill = min(M, manquant)` sur Health (`PredictRepair`/`MaxFillUp` — UNE stat, #45d) ;
        (2) `IdunBattle.AI.Playbook.Loki.Repair_GalvanicFieldPlaybook$$CalculateCustomUtility` bespoke = `M/(cible.maxHP+1) × 50`, GATÉ par
        `HasValidTargets(cible)` (la cible réparée peut attaquer depuis SA position = combat-readiness, même
        prédicat que #77 → 0 sinon). `ShouldExecute` : util totale > 0."""
        me = ctx.me
        gal = next((ab for ab in ((me or {}).get("abilities") or [])
                    if ab.get("id") == _GALVANIC_REPAIR_ID and ab.get("usable") is not False), None)
        if gal is None:
            return []
        scene = ctx.scene
        if scene is None:
            return []   # pas de prédicteur (combatSnapshot KO) -> Attack cible indisponible -> pas de candidat
        pos_by_id = {u.get("id"): (u["pos"]["col"], u["pos"]["row"])
                     for u in ctx.units if u.get("pos") and u["pos"].get("col") is not None}
        obs_by_sq = {u.get("squadId"): u for u in ctx.obs_units}
        reach = ([ctx.origin] if ctx.origin is not None else []) \
            + [(t["col"], t["row"]) for t in ctx.move_tiles]
        REPAIR_RANGE = 1  # réparation ciblée adjacente (pas de `range` propre observé)
        eff_by_id = {u.get("id"): (u.get("effects") or []) for u in ctx.units}  # RepairModifier cible (#45d)
        # dmgPct/maxDmg du passif GalvanicField au niveau PASSIF du caster (maxDmg rarity-scaled par mult).
        cfg = ctx.heal_config(ctx.uid)
        maxdmg = ability_var("GalvanicField", "maxDmg", cfg["passive"], multiplier_pct=cfg["multiplier"])
        dmgpct = ability_var("GalvanicField", "dmgPct", cfg["passive"], multiplier_pct=cfg["multiplier"])
        at = ctx.ability_targets(ctx.uid, _GALVANIC_REPAIR_ID)
        vts = set()
        for u in (at.get("units") or []):
            for a in (u.get("abilities") or []):
                if a.get("abilityId") == _GALVANIC_REPAIR_ID:
                    for t in (a.get("targets") or []):
                        if t.get("kind") == "unit" and t.get("targetId") is not None:
                            vts.add(t["targetId"])
        out = []
        for tg in vts:
            tctx = scene.ctx_by_id.get(tg)
            if tctx is None:
                continue   # cible hors combatSnapshot (Attack indisponible) -> pas de candidat bespoke
            ob = obs_by_sq.get(tg) or {}
            hp_max = int(ob.get("hpMax") or 0)
            hp_cur = int(ob.get("hp") or 0)
            # M = min(round(Attack_INITIALE cible × dmgPct/100), maxDmg)
            att = tctx.get_stat(StatType.ATTACK, StatPart.INITIAL)
            raw = int(round(att * (dmgpct or 0) / 100.0))
            M = raw if maxdmg is None else min(raw, maxdmg)
            # RepairModifier (#45d) appliqué au FILL seulement (il vit DANS IdunBattle.Core.Services.DamagePrediction$$PredictRepair) ;
            # le terme custom IdunBattle.AI.Playbook.Loki.Repair_GalvanicFieldPlaybook$$CalculateCustomUtility consomme le M brut de GetOverrideAttackDamageAmount (hors PredictRepair).
            mod_add, mod_mul = calculate_repair_modifier_for_prediction(eff_by_id.get(tg), ctx.heal_config)
            _glim = (_group_heal_limit(ob.get("visualId"), hp_max, hp_cur)
                     if _REPAIR_GROUP_CAP else None)   # #60 : cap groupe (PredictRepair, gate param_7)
            rp = predict_repair_effective(repair_amount(M, mod_add, mod_mul),
                                          hp_cur, hp_max, group_limit=_glim)  # fill = min(M', manquant)
            repaired = repair_utility(rp.fill_hp, hp_max, is_boss=False)
            custom = (M / (hp_max + 1) * 50.0) if playbooks._has_valid_targets(ctx, tg) else 0.0
            pred = repaired + custom
            if ctx.debug:
                print(f"    [dbg galv u{ctx.uid}->{tg}] vis={ob.get('visualId')} hp={hp_cur}/{hp_max} "
                      f"attInit={att} dmgPct={dmgpct} maxDmg={maxdmg} M={M} fillHp={rp.fill_hp} "
                      f"repaired={repaired:.3f} custom={custom:.3f} pred={pred:.3f}", file=sys.stderr)
            if pred <= 0:
                continue   # ShouldExecute : util totale > 0
            tpos = pos_by_id.get(tg)
            for T in reach:
                if tg != ctx.uid and (tpos is None or hexgeo.distance(T, tpos) > REPAIR_RANGE):
                    continue   # cible hors portée depuis T (self = depuis toute tuile)
                out.append({"target": tg, "ability": _GALVANIC_REPAIR_ID,
                            "to": (T if T != ctx.origin else None),
                            "pred": pred, "full": pred + tile_utility(ctx, T)})
        return out

    def _bespoke_candidates(self, ctx) -> list:
        """Playbooks Comparable BESPOKE self-cast (#82 : BloodChalice/MomentShackle) — chacun a son
        scoring PROPRE (override `EvaluateInternal`, PAS `HEAL_PLAYBOOK.score`). Dispatch par ID d'ability
        présente + `usable` (identification par id, PAS `"Heal" in name` : leur nom n'a pas "Heal")."""
        me_abis = {ab.get("id"): ab for ab in ((ctx.me or {}).get("abilities") or [])}
        out = []
        for aid, pb in BESPOKE_SELFCAST.items():
            ab = me_abis.get(aid)
            if ab is None or ab.get("usable") is False:
                continue
            out += pb.generate_candidates(ctx)
        return out

    def generate(self, ctx) -> dict | None:
        if not self.unit_action_gate(ctx):
            return None                    # HasFlag(unit, ActiveAbilityUsed=2) -> generateur MUET
        cands: list = []  # {target, ability, to:(c,r)|None, pred, full}
        best = self._best_attack(ctx)
        if best and best[0] > 0:   # best[0] = u (dégât) > 0 -> ShouldExecute
            cands.append({"target": best[2], "ability": best[3], "to": best[4],
                          "pred": best[0], "full": best[1]})   # full = u_action (dégât + Tile7 + custom #64)
        cands += self._heal_candidates(ctx)
        cands += self._repair_candidates(ctx)             # RepairPlaybook générique (id 28)
        cands += self._repair_galvanic_candidates(ctx)    # #85 : Repair_GalvanicField bespoke (id 1119)
        cands += self._bespoke_candidates(ctx)   # #82 : BloodChalice/MomentShackle
        cands += nonattack_candidates(ctx)       # #27-4b : Comparable SANS prediction (verrou 2)
        #                                       (ability sans `damageProfile` -> jamais dans `plans`,
        #                                        donc invisible de `_best_attack` ; le natif, lui, ne
        #                                        gate PAS sur la prediction — `ShouldExecute` = true)
        cands += excruciating_frequencies_candidates(ctx)   # #56-t3b : 1197 ExcruciatingFrequencies
        #                                       (ligne-AoE ciblant une TUILE, non plan-driven rankCount=0)
        # (Les NonComparable sont traitées par le générateur précédent — cf. InitAbilityTypeLists.)
        # `abilityIds.Contains` (generator+0x28) : le natif filtre CHAQUE ability de l'unité, pas
        # seulement celles du sweep d'attaque -> les pools heal/repair/bespoke/nonattack tombent
        # aussi quand le set est explicite. Inerte quand `ability_ids is None`.
        if self.ability_ids is not None:
            cands = [c for c in cands if self._in_ability_set(c.get("ability"))]
        if ctx.debug and cands:
            for c in sorted(cands, key=lambda c: -c["full"])[:8]:
                print(f"    [dbg cand u{ctx.uid}] tgt={c.get('target')} ab={c.get('ability')} "
                      f"to={c.get('to')} pred={round(c.get('pred') or 0,3)} "
                      f"tile_term={round((c.get('full') or 0)-(c.get('pred') or 0),3)} "
                      f"full={round(c.get('full') or 0,3)}", file=sys.stderr)
        if not cands:
            return None
        # `Bucket.ChooseAction` : argmax `full` (tie-break id de cible croissant = -target).
        bucket = Bucket()
        for c in cands:
            bucket.add_action(Action(key=(c["full"], -(c.get("target") or 0)),
                                     payload={"kind": "ability", "target": c["target"],
                                              "ability": c["ability"], "to": c["to"],
                                              "util": c["pred"]}))
        return bucket.choose_action()


def movement_candidate_positions(ctx) -> list:
    """`positions` — le 3ᵉ argument que le tactic passe à
    `IdunBattle.AI.ActionGenerators.MovementActionGenerator$$GenerateActions(unit, startPosition,
    positions, overrideUtility)` (rangé à `<GenerateActions>d__6+0x40`, d'où
    `...u003CGenerateActionsu003Ed__6$$MoveNext` construit **un** `UtilityMovementCase` par position).

    Sa source est `IdunBattle.AI.Tactics.ABaseAiUnitTactic$$GenerateActionTiles`, qui appelle le slot
    `+0xe` de l'`IBattleQuery` = `IdunBattle.Core.Services.BattleQuery$$GetCurrentAndMovablePositionsFor` :

        var set = new OrderedSet<UnitPosition>(EntityExtensions.GetUnitPosition(unit, this._state));
        set.UnionWith(this._movementQuery.GetMovablePositionsFor(unit, ignoreUnitFlags, options));
        return set;

    ⇒ la position **COURANTE** est la GRAINE de l'`OrderedSet` : elle est dans l'ensemble, et elle y
    est **PREMIÈRE** ; les tuiles de `GetMovableTilesFor` (qui, elles, l'excluent — d'où l'union)
    suivent. C'est exactement ce que `engine.ai.context.action_tiles_for` construit déjà, et ce que
    `ctx.action_tiles` porte.

    **Pourquoi l'ordre est LOAD-BEARING** : l'argmax natif vit dans
    `IdunBattleLogic.AI.Utilities.UtilityDecider.u003CCalculateUtilitiesForCasesEnumeratedu003Ed__7u003Cobjectu003E$$MoveNext`
    et remplace le meilleur case sur `FixMath.NET.Fix64$$op_GreaterThan` — **STRICT**, donc
    **keep-first à égalité**. Position courante énumérée en tête + remplacement strict ⇒ **à utilité
    ÉGALE le natif RESTE SUR PLACE**, et il ne bouge que sur un gain STRICT.

    Ce que le port faisait (#320) : il passait `ctx.move_tiles` (= RPC `aiMovableTiles` =
    `GetMovableTilesFor`) — candidate-set AMPUTÉ de la seule tuile que le natif évalue en PREMIER.
    « Rester sur place » n'était pas représentable, donc le générateur proposait TOUJOURS un
    déplacement réel. Dégradation permissive : `InputBuilder` n'aurait émis aucun `MoveUnitMessage`,
    le natif finissait le tour — cf. `engine.ai.tactic.input_messages_from_unit_action`.

    Fonction de MODULE (et non méthode) pour la même raison que le mirror de #309 : c'est ce qui la
    rend NEUTRALISABLE depuis un probe, donc la garde falsifiable
    (`probe_320_movement_scoring_origin.py`).

    Format : liste de `{"col", "row"}` — celui d'`aiMovableTiles`, que `move.best_move_faithful`
    consomme déjà. L'ORDRE de la liste est conservé jusqu'à l'argmax."""
    return [{"col": c, "row": r} for (c, r) in (ctx.action_tiles or [])]


class MovementActionGenerator(ActionGenerator):
    """Générateur d'approche pure (`MovementActionGenerator`, EN DERNIER dans la liste). Ne fire que
    si aucun tier d'ability n'a produit d'action légale. Scoring `MovementSuggestion` porté
    (`move.best_move_faithful` = MinDist chemin + MaxDist + situationnels). Renvoie TOUJOURS une
    action (fallback terminal du tactic)."""

    def generate(self, ctx) -> dict | None:
        # `positions` = `GenerateActionTiles` : position COURANTE en TÊTE, puis les movables
        # (cf. `movement_candidate_positions`). Résolu par le MODULE -> neutralisable par un probe.
        positions = movement_candidate_positions(ctx)
        if not positions or not ctx.enemies:
            return {"kind": "move", "to": None}
        # #26 : le seed du fallback HEX de MinDist(16) = les ennemis CIBLABLES (tgt_epos, post-filtres
        # `FindClosestEnemy` IdunBattle.AI.ActionGenerators.MovementActionGenerator.u003CFindClosestEnemyu003Ed__8$$MoveNext), PAS epos complet — un ennemi Environment/deep-strike/irrelevant
        # ne participe jamais au ClosestEnemy natif. epos (complet) reste le fallback si tgt_epos vide.
        move_to, move_util = move.best_move_faithful(
            positions, ctx.elev_by_pos, ctx.tgt_epos or ctx.epos, ctx.wt,
            pathdist_by_pos=ctx.pathdist_by_pos,
            is_temporary_by_pos=ctx.is_temporary_by_pos, effects_by_pos=ctx.effects_by_pos,
            terrain_by_pos=ctx.terrain_by_pos, leaf_ctx=tile_leaf_ctx(ctx),
            # #236 : les 4 gates d'entree de la feuille MinDist(16) (`case.Unit`/`ClosestEnemy`).
            mindist_case=ctx.mindist_case)
        return {"kind": "move", "to": move_to, "util": move_util}


def movement_action_with_override(ctx, utility_types) -> dict:
    """`IdunBattle.AI.ActionGenerators.MovementActionGenerator$$GenerateActions(unit, startPosition,
    positions, overrideUtility)` -- la branche ou le 4e argument est NON NUL.

    Le generateur ci-dessus (`MovementActionGenerator.generate`) porte la branche `overrideUtility ==
    null` : le scoring y est celui du playbook de mouvement PAR DEFAUT (`move.best_move_faithful`).
    Quand un appelant fournit un `UtilityDefinition`, c'est LUI qui score, et lui SEUL -- il ne
    s'ajoute pas au defaut, il le REMPLACE (le natif construit son `UtilityMovementCase` avec
    l'utilite passee). Unique producteur porte : le behaviour DSL `PerformAIMovement`, dont le
    troisieme argument est le `UtilityDefinition` que l'ability construit dans son `.ctor` --
    p.ex. `BioMinefieldAbility$$.ctor`, qui alloue un tableau d'UN `UtilityBucket` de type
    `UtilityType.BioMinefield_MoveTowardsTarget`.

    `utility_types` = les `UtilityType` des buckets de ce `UtilityDefinition`. Le score d'une
    position est leur SOMME, evaluee par `engine.ai.utilities.get_movement_utility` = le mirror de
    `Playbook<T>$$GetMovementUtility` (`ComposedUtility.EvaluateMovement(UtilitiesDatabase.
    GetUtility(type), caster@pos)`) -- on ne re-implemente aucune feuille ici.

    ⚠ **ARGMAX STRICT, DONC KEEP-FIRST -- et c'est ce qui rend << rester sur place >> representable.**
    L'argmax natif vit dans `IdunBattleLogic.AI.Utilities.UtilityDecider.<CalculateUtilitiesForCases
    Enumerated>d__7<object>$$MoveNext` et remplace le meilleur case sur `FixMath.NET.Fix64$$
    op_GreaterThan`. Comme `movement_candidate_positions` enumere la position COURANTE EN TETE (cf.
    sa docstring), une egalite laisse l'unite ou elle est. C'est la MEME loi que le chemin par
    defaut, et elle est load-bearing ici : si toutes les positions scorent identiquement, le natif
    n'emet AUCUN `MoveUnitMessage`.

    ⚠ **ETAGE MANQUANT NOMME (residu #175-r), et il rend ce chemin INERTE pour BioMinefield.**
    `BioMinefield_MoveTowardsTargetUtility` derive de `MoveTowardsUnitUtility`, dont le port lit
    `meta["movetowards_hexdist"][<ability/effet>]`. **AUCUN producteur de `meta` du depot ne remplit
    cette cle** (mesure : 0 site d'ecriture) -- la feuille rend donc `0.0` sur TOUTE position, la
    somme est plate, et le keep-first garde la position courante. Le port ne se degrade pas
    silencieusement pour autant : `to` reste la position COURANTE et `apply_action` n'emet aucun
    move (`to == origin`), ce qui est EXACTEMENT le comportement natif a utilite plate. Ce qui
    manque au natif, ce sont les deux etages qu'`IdunBattle.AI.Utilities.MoveTowardsUnitUtility$$
    GetMinDistanceToTarget` ajoute (resolution de la cible par balayage `GetAllAliveUnits` +
    distance de CHEMIN par tuile de la cible), et ils appartiennent au foyer de #175-r. (#939)"""
    positions = movement_candidate_positions(ctx)
    if not positions:
        return {"kind": "move", "to": None}
    types = [int(t) for t in (utility_types or ())]
    best, best_u = None, None
    for p in positions:
        pos = (p["col"], p["row"])
        u = 0.0
        for t in types:
            u += float(_ai_utilities.get_movement_utility(ctx, pos, t) or 0.0)
        if best_u is None or u > best_u:          # `Fix64$$op_GreaterThan` STRICT -> keep-first
            best, best_u = pos, u
    return {"kind": "move", "to": best, "util": best_u}


# tile_leaf_ctx : DÉPLACÉ dans engine/utilities/tile.py (case-49 : consommé par les DEUX chemins
# de la Composed Tile(7) — move ET attaque). Ré-exporté ici pour les importeurs existants
# (engine_agreement_stages).
from engine.utilities.tile import tile_leaf_ctx  # noqa: E402,F401
# Forme B (module, pas symbole) : un binding de module n'est jamais gele, donc un probe qui
# substitue `engine.ai.utilities.get_movement_utility` MORD ici. `engine.ai.utilities` n'importe pas
# ce module -- mesure : ses imports ne citent que `engine.utilities.*`, donc AUCUN cycle a fermer.
import engine.ai.utilities as _ai_utilities  # noqa: E402
