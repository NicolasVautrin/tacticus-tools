"""Playbooks NonComparable — une classe Python HOMONYME par playbook natif.

Remplace l'ancien switch `if kind in ("summon","adjacent_count","target_hp")` d'engine_decide
par un mecanisme generique (registre de classes + driver commun). Structure FIDELE au decompile
(confirme sur IdunBattle.AI.Playbook.Loki.AberrantHypermorphPlaybook$$EvaluateNonComparable) :

  - `IdunBattle.AI.Tactics.ABaseAiActorTactic$$InitAbilityTypeLists` range chaque ability NonComparable par
    son playbook dans `dict[get_Priority]` ; `IdunBattle.AI.Tactics.ABaseAiActorTactic$$GetDefaultActiveAbilityActionGenerators`
    cree UN generator par tier [1000,100,0,-100,-1000] ; le tactic prend le PREMIER generator
    non-vide -> une NC qui passe son MIN_UTILITY prime sur toute Comparable, ET une NC de tier
    superieur prime sur une NC de tier inferieur PAR L'ORDRE (pas l'utilite). get_Priority = slot-0
    de l'interface DAT_1831d4f88 (dispatch runtime FUN_180002560(0, interface, playbook)). #115 (RE
    gqfc5mff6c) : AUCUN playbook n'override ce getter (search_symbols get_Priority / Playbook.*Priority
    / Playbook$$get_ / IsComparable = 0 hit Playbook ; ni BasePlaybook, ni NonComparablePlaybook<T>,
    ni ComparablePlaybook<T> ne le nomment -> il vit UNE fois sur le parent partage, jamais surcharge
    par-leaf). => TOUTES les NonComparable partagent le MEME get_Priority de base = 0 (les 15 portees
    inclus NovaBoost/NovaShield). L'ancien NovaBoost=1000/NovaShield=-1000 venait d'un idun.tests.TestLegendaryEventProgression$$GetLiveEventState+0x40
    (`mov eax,0x3E8`) stale/mal-attribue qui NE RESOUT PLUS dans ce build -> supprime. Consequence :
    l'ordre inter-tier NC n'est PAS exerce (un seul tier 0 peuple) ; a l'interieur du tier 0, deux NC
    d'une meme unite se departagent par UTILITE (choose_action argmax), pas par un tier fabrique.
  - Le generator `ActiveAbilityActionGenerator.<GenerateActions>IdunBattle.AI.ActionGenerators.ActiveAbilityActionGenerator.u003CGenerateActionsu003Ed__7$$MoveNext` BALAIE
    les positions candidates du caster (tuiles de move) et appelle par position
    `<Playbook>.EvaluateNonComparable(this, ctx, position)` : celui-ci cree un Bucket (MIN_UTILITY
    du cctor), enumere les cibles eligibles via `IdunBattle.AI.Playbook.BasePlaybook$$GetEligibleTargetsSelectable`, score chacune (`<Playbook>.GetUtility`), et gate `IdunBattle.AI.BucketSystem.Bucketu003C__Il2CppFullySharedGenericTypeu003E$$AddAction`
    (util >= min, remplacement STRICT `>`).
  - `Bucket.ChooseAction` = argmax STRICT (tie -> premier enumere).

Mapping : une CLASSE = un playbook natif ; `evaluate_non_comparable` = la methode homonyme
(formule EvaluateNonComparable INLINE, VA citee) ; `generate_candidates` = le balayage
generator+selector propre a l'ability (positions/cibles specifiques). Les requetes spatiales
(GetAdjacentEnemies/Friends) deleguent a `engine/battle_query.py` (primitive IBattleQuery).
Le driver generique `choose_action` (mirror ChooseAction) collecte les candidats de toutes les
abilities NC usable de l'unite et rend l'argmax -> remplace le switch. Utilite = heuristique BRUTE
(pas de terme Tile7 : CalculateActionUtility/Tile7 est un chemin Comparable-only).

cf. engine/battle_query.py (primitives), docs/rl/playbook/architecture.md §2.3 + playbooks.md.
Vit dans le namespace unifie `engine.playbook` (= `IdunBattle.AI.Playbook`), aux cotes de
`comparable.py`/`common.py` (les playbooks Comparable).

DECOUPAGE (Option 1) : une CLASSE = un MODULE (bloody_fury.py, heals.py, hammer_of_wrath.py, ...),
fondations partagees dans `_base.py`. Ce `__init__.py` est la FACADE : il importe les feuilles,
construit le registre `PLAYBOOKS` et expose le driver `choose_action` + les predicats. L'API
publique (`noncomparable.NCContext`, `.is_noncomp`, `.choose_action`, `.is_summon`,
`._has_valid_targets`, classes) reste identique a l'ancien module monolithique.
"""
from __future__ import annotations

from ._base import (
    NCContext, NonComparablePlaybook, _PlanTargetPlaybook,
    _unit_cfg, _traits, _has_valid_targets, _sweep_origin_first,
)
from .bloody_fury import BloodyFuryPlaybook
from .vexilla_magnifica import VexillaMagnificaPlaybook
from .fighting_retreat import FightingRetreatPlaybook
from .aberrant_hypermorph import AberrantHypermorphPlaybook
from .nova_boost import NovaBoostPlaybook
from .nova_shield import NovaShieldPlaybook
from .heals import (
    RitesOfRestorationPlaybook, CombatRestorativesPlaybook,
    DefendTheDivineWorkPlaybook, RevitalizingMalignancyPlaybook,
    InspiredToGreatnessPlaybook, _active_ability_levels,
)
from .scarab_summon import ScarabSummonPlaybook
from .get_em_runtz import GetEmRuntzPlaybook
from .gauntlets_of_ultramar import GauntletsOfUltramarPlaybook
from .hammer_of_wrath import HammerOfWrathPlaybook, _enemy_killed_by_normal_attack
from .heroic_fusillade import HeroicFusilladePlaybook
from .doctrina_imperatives import DoctrinaImperativesPlaybook
from .stormcaller import StormcallerPlaybook
from .it_itches import ItItchesPlaybook
from .the_quickening import TheQuickeningPlaybook
from .black_rage import BlackRagePlaybook
from .vigilance_eternal import VigilanceEternalPlaybook
from .scarab_hive import ScarabHivePlaybook
from .cord_claw import CordClawPlaybook
from .poxwalkers import SpawnPoxwalkersPlaybook
from .foul_infusion import FoulInfusionPlaybook
from .holy_duel import HolyDuelPlaybook
from .grapnel_launcher import GrapnelLauncherPlaybook
from .early_warning_override import EarlyWarningOverridePlaybook
from .dark_talon_strike import DarkTalonStrikePlaybook
from .send_in_the_next_wave import SendInTheNextWavePlaybook
from .incursion import IncursionPlaybook
from .master_of_the_tutelaries import MasterOfTheTutelariesPlaybook
from .supreme_commander import SupremeCommanderPlaybook


# Registre abilityType -> instance de playbook (remplace le switch `kind`).
PLAYBOOKS: dict[int, NonComparablePlaybook] = {
    pb.ABILITY_ID: pb for pb in (
        BloodyFuryPlaybook(),
        VexillaMagnificaPlaybook(),
        FightingRetreatPlaybook(),
        AberrantHypermorphPlaybook(),
        NovaBoostPlaybook(),
        NovaShieldPlaybook(),
        RitesOfRestorationPlaybook(),
        CombatRestorativesPlaybook(),
        DefendTheDivineWorkPlaybook(),
        RevitalizingMalignancyPlaybook(),
        InspiredToGreatnessPlaybook(),
        ScarabSummonPlaybook(),
        GetEmRuntzPlaybook(),
        GauntletsOfUltramarPlaybook(),
        HammerOfWrathPlaybook(),
        HeroicFusilladePlaybook(),   # #15 (G5, Judh) — util plate=1, gates Hero+ennemi-voisin
        DoctrinaImperativesPlaybook(),  # S4a (Tan Gi'da) — self-cast toggle, util 100, once-per-turn
        # #95-RESTE2 — DEBLOQUE par le port de `SwornProtector` : son gate `IsFriendlyKell` exige un
        # ENFANT du caster, ce qui etait impossible offline tant que Kell ne pouvait pas apparaitre
        # (le playbook aurait rendu False EN PERMANENCE = code enregistre-mais-mort).
        SupremeCommanderPlaybook(),     # 1028 (Creed) — util PLATE 3/2, MIN_UTILITY 1 (.cctor)
        # #44 (reframe #34) — les 5 playbooks NC du « lead 8 » : le stage agreement les classait
        # « non-attack-oracle » alors qu'ils sont NonComparable NATIFS (EvaluateNonComparable, AUCUN
        # Make*Predictions). Deux familles : utilite ENTIERE (comptage/paliers) pour 1113/1121/1151,
        # utilite de DEGAT interne (CalculateUtilityFromDamageEvent) pour 1163/1202 — cf. HammerOfWrath.
        StormcallerPlaybook(),          # 1113 — #unites dans la zone de glace ; gate WillNormalAttackKill
        ItItchesPlaybook(),             # 1121 — #ennemis pousses ; gates IsDisplaceable + CanBePushed
        BlackRagePlaybook(),            # 1163 — degat de l'attaque NORMALE depuis la tuile de charge
        VigilanceEternalPlaybook(),     # 1202 — degat de l'ability depuis l'hex libre adjacent
        TheQuickeningPlaybook(),        # 1151 — teleport-echange ; porte #46 RESOLUE : slot 4
        #                                 `ShouldEvaluate(unit)` = corps folde IdunBattle.AI.Playbook.Loki.AlphaWarriorPlaybook$$ShouldEvaluate
        #                                 (`turnsStarted > 1`, jamais au 1er tour de l'unite)
        #                                 -> `should_evaluate` (gate AMONT dans choose_action)
        # #56 (tranche 1) — 2 NC natifs (EvaluateNonComparable) jamais confrontes, reveles par le
        # batch de generalisation MC1_67 (misses "non-attack-oracle") :
        ScarabHivePlaybook(),           # 1007 — summon 2 scarabs adj. cible ; util plate 1, gate
        #                                 adjacent_addable_count(cible) >= 2 (IdunBattle.AI.Playbook.Loki.ScarabHivePlaybook$$EvaluateNonComparable)
        CordClawPlaybook(),             # 1122 — attaque melee ; util = #ennemis adj. tuile d'attaque
        #                                 (GetAdjacentEnemies casterPos), MIN_UTILITY=1 (IdunBattle.AI.Playbook.Loki.CordClawPlaybook$$EvaluateNonComparable)
        # #56 (tranche 2) — 3 NC natifs self/enemy-cast reveles par le batch MC1_67 (non-attack-oracle) :
        SpawnPoxwalkersPlaybook(),      # 1040 — summon self-cast ; util plate 1.5, cible=SOI (IdunBattle.AI.Playbook.Loki.SpawnPoxwalkersPlaybook$$EvaluateNonComparable)
        FoulInfusionPlaybook(),         # 1038 — buff self-cast ; util=#amis-eligibles adj +bonus ennemi,
        #                                 MIN_UTILITY=2, cible=SOI (IdunBattle.AI.Playbook.Loki.FoulInfusionPlaybook$$EvaluateNonComparable)
        HolyDuelPlaybook(),             # 1050 — defi ; util=Attack(cible), cible=max-Attack ennemi,
        #                                 gate !MightBeKill (IdunBattle.AI.Playbook.Loki.HolyDuelPlaybook$$EvaluateNonComparable)
        # #56 (tranche 3a) -- 3 NC natifs Loki reveles par le batch MC1_67 seed 54321 (misses
        # non-attack-oracle). Les 3 sont des NC natifs (EvaluateNonComparable).
        GrapnelLauncherPlaybook(),      # 1090 -- reposition ; util plate 1, cible=1er ennemi
        #                                 eligible a l'origine, cast en place (IdunBattle.AI.Playbook.Loki.GrapnelLauncherPlaybook$$EvaluateNonComparable)
        EarlyWarningOverridePlaybook(),  # 1077 -- summon overwatch self-cast ; util POSITIONNELLE
        #                                 50*(#ennemis hors-portee) - 10*Sum(dist), cible=SOI,
        #                                 position=argmax, gate nearest<9 (IdunBattle.AI.Playbook.Loki.EarlyWarningOverridePlaybook$$EvaluateNonComparable)
        DarkTalonStrikePlaybook(),      # 1092 -- beam en ligne ; cible=TILE (aim), util=#ennemis
        #                                 continus sur le rayon caster->aim, MIN_UTILITY=2 (IdunBattle.AI.Playbook.Loki.DarkTalonStrikePlaybook$$EvaluateNonComparable)
        # #56 (tranche 3b) -- 2 NC natifs summon reveles par le batch MC1_67 seed 1357 (misses
        # non-attack-oracle). MIN_UTILITY DYNAMIQUE = max stat sur TOUS les ennemis (ne fire que si le
        # meilleur ennemi est ciblable) ; util(cible) = stat de la cible.
        SendInTheNextWavePlaybook(),    # 1016 -- summon Cadians ; util=Attack(cible), cible=ennemi de
        #                                 plus haute Attack, MIN=max Attack ennemis (IdunBattle.AI.Playbook.Loki.SendInTheNextWavePlaybook$$EvaluateNonComparable)
        IncursionPlaybook(),            # 1021 -- summon Bloodletters ; util=PV(cible), cible=ennemi de
        #                                 plus haut PV avec >=2 tuiles libres adj., MIN=max PV (IdunBattle.AI.Playbook.Loki.IncursionPlaybook$$EvaluateNonComparable)
        # #202-C (Abraxas) — summon Pink Horror tile-target ; gates nFree(ST)>2 & nE2(ring exact
        # dist==2 du REEL)>0 ; util = 1 + (nE2-1)*10 + (nFree-3)*10 + 100 si dist(nearest, ST)==2.
        MasterOfTheTutelariesPlaybook(),  # 1096 (IdunBattle.AI.Playbook.Loki.MasterOfTheTutelariesPlaybook$$EvaluateNonComparable, slots 0x49/0x52/0x6b/0x72 resolus)
    )
}


def playbook_for(ability_id: int) -> NonComparablePlaybook | None:
    return PLAYBOOKS.get(ability_id)


def is_noncomp(ability_id: int) -> bool:
    """L'ability a-t-elle un playbook NonComparable porté ?"""
    return ability_id in PLAYBOOKS


def is_summon(ability_id: int) -> bool:
    """L'ability est-elle le summon composé (AberrantHypermorph) ? Son targetId natif = l'unité
    SPAWNÉE (post-exec) — la comparaison d'agreement se fait sur l'ability seule, pas la cible."""
    return isinstance(PLAYBOOKS.get(ability_id), AberrantHypermorphPlaybook)


def choose_action(abilities: list, ctx: NCContext, priority: int | None = None) -> dict | None:
    """Driver d'UN generateur NonComparable (mirror `ActiveAbilityActionGenerator.GenerateActions`
    IdunBattle.AI.ActionGenerators.ActiveAbilityActionGenerator.u003CGenerateActionsu003Ed__7$$MoveNext + `Bucket.ChooseAction`) : pour chaque ability NC usable de l'unite DU TIER `priority`
    (get_Priority ; None = tous tiers confondus), collecte les candidats de son playbook (generator +
    gate MIN_UTILITY), rend l'argmax STRICT (tie -> 1er) ou None si le generateur est vide.

    Le natif range les NonComparable dans `dict[get_Priority]` (IdunBattle.AI.Tactics.ABaseAiActorTactic$$InitAbilityTypeLists) : un generateur PAR tier,
    evalues dans l'ordre 1000..-1000 AVANT le fallback Comparable. `priority` selectionne ce tier."""
    nc_cands: list[dict] = []
    for ab in (abilities or []):
        pb = playbook_for(ab.get("id"))
        if pb is None or ab.get("usable") is False:
            continue
        if priority is not None and pb.PRIORITY != priority:
            continue   # ability d'un autre tier NonComparable -> pas dans CE generateur
        # Gate AMONT slot-4 `ShouldEvaluate(unit)` (#46) : le générateur natif le teste AVANT tout
        # sweep (`FUN_180003bd0(4, …)` dans <GenerateActions>d__7 IdunBattle.AI.ActionGenerators.ActiveAbilityActionGenerator.u003CGenerateActionsu003Ed__7$$MoveNext) — False = ability
        # sautée entièrement (jamais évaluée), le fallback Comparable prend la main.
        if not pb.should_evaluate(ctx):
            continue
        nc_cands += pb.generate_candidates(ctx)
    if not nc_cands:
        return None
    if ctx.debug:
        import sys
        print(f"    [dbg NC u{ctx.uid}] tier{priority}="
              f"{[(c['ability'], c.get('target'), c.get('to'), c['pred']) for c in nc_cands]}",
              file=sys.stderr)
    return max(nc_cands, key=lambda c: c["pred"])   # strict : max() garde le 1er a egalite


# Facade publique (identique a l'ancien module monolithique). Les `_`-prefixes re-exportes sont
# consommes hors package : `_has_valid_targets` (action_generators.galvanic), et les helpers/bases
# accessibles via `noncomparable.X` pour compat. Marque-les "used" (pyflakes).
__all__ = [
    "NCContext", "NonComparablePlaybook", "_PlanTargetPlaybook",
    "PLAYBOOKS", "playbook_for", "is_noncomp", "is_summon", "choose_action",
    "_unit_cfg", "_traits", "_has_valid_targets", "_sweep_origin_first",
    "_active_ability_levels", "_enemy_killed_by_normal_attack",
    "BloodyFuryPlaybook", "VexillaMagnificaPlaybook", "FightingRetreatPlaybook",
    "AberrantHypermorphPlaybook", "NovaBoostPlaybook", "NovaShieldPlaybook",
    "RitesOfRestorationPlaybook", "CombatRestorativesPlaybook", "DefendTheDivineWorkPlaybook",
    "RevitalizingMalignancyPlaybook", "InspiredToGreatnessPlaybook", "ScarabSummonPlaybook",
    "GetEmRuntzPlaybook", "GauntletsOfUltramarPlaybook", "HammerOfWrathPlaybook",
    "HeroicFusilladePlaybook", "DoctrinaImperativesPlaybook",
    "StormcallerPlaybook", "ItItchesPlaybook", "TheQuickeningPlaybook",
    "BlackRagePlaybook", "VigilanceEternalPlaybook",
    "ScarabHivePlaybook", "CordClawPlaybook",
    "SpawnPoxwalkersPlaybook", "FoulInfusionPlaybook", "HolyDuelPlaybook",
    "GrapnelLauncherPlaybook", "EarlyWarningOverridePlaybook", "DarkTalonStrikePlaybook",
    "SendInTheNextWavePlaybook", "IncursionPlaybook", "MasterOfTheTutelariesPlaybook",
    "SupremeCommanderPlaybook",
]
