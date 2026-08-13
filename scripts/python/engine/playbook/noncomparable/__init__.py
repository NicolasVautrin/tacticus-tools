"""Playbooks NonComparable — une classe Python HOMONYME par playbook natif.

Remplace l'ancien switch `if kind in ("summon","adjacent_count","target_hp")` d'engine_decide
par un mecanisme generique (registre de classes + driver commun). Structure FIDELE au decompile
(confirme sur IdunBattle.AI.Playbook.Loki.AberrantHypermorphPlaybook$$EvaluateNonComparable) :

  - `IdunBattle.AI.Tactics.ABaseAiActorTactic$$InitAbilityTypeLists` range chaque ability NonComparable par
    son playbook dans `dict[get_Priority]` ; `IdunBattle.AI.Tactics.ABaseAiActorTactic$$GetDefaultActiveAbilityActionGenerators`
    cree UN generator par tier [1000,100,0,-100,-1000] ; le tactic prend le PREMIER generator
    non-vide -> une NC qui passe son MIN_UTILITY prime sur toute Comparable, ET une NC de tier
    superieur prime sur une NC de tier inferieur PAR L'ORDRE (pas l'utilite). get_Priority = slot-0
    de l'interface DAT_1831d4f88 (dispatch runtime FUN_180002560(0, interface, playbook)).

    **22 playbooks SURCHARGENT `get_Priority`** (#170) ; les 235 autres ActiveAbilityType heritent
    du defaut 0 = `AbilityPriority.Normal`. La table est `NATIVE_PRIORITY` (_base.py) ; les 22 sont
    TOUTES NonComparable (`get_IsComparable` = False mesure), donc leur tier est REELLEMENT exerce.
    Trois d'entre elles sont portees : NovaBoost 1192 = **1000**, ThriceBlessedConflagration 1187 =
    **100**, NovaShield 1194 = **-1000**.

    L'affirmation inverse de #115 (« AUCUN playbook n'override ce getter ») etait un FAUX NEGATIF
    DE METHODE, pas une lecture : les corps `mov eax,imm32 ; ret` sont dedupliques par IL2CPP, donc
    (a) Ghidra n'en NOMME aucun -- `search_symbols get_Priority` rend 0 hit Playbook meme quand 22
    existent -- et (b) `data/symbols/<build>/frida/methods.tsv`, indexe par RVA et sans doublon
    (121502 lignes, 0 RVA repetee), n'expose qu'UN proprietaire par corps partage : 3 lignes pour
    22 surcharges. La mesure #170 invoque le slot 0 de la vtable d'interface, ability par ability,
    sur les 257 valeurs de l'enum (`probe_170_playbook_priority.py`, RPC `pbGate`), recoupee par
    `abilityPreferences` (0 divergence) et par les OCTETS de trois corps natifs.

    Consequence pour le driver : l'ordre inter-tier NC EST exerce des qu'une unite porte l'une des
    22 ; a l'interieur d'un tier, deux NC d'une meme unite se departagent par UTILITE
    (choose_action argmax).
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

#: `NATIVE_PRIORITY`, `native_priority` et `_has_valid_targets` sont lus par ACCES ATTRIBUTAIRE
#: (`from engine.playbook import noncomparable as NC` puis `NC.NATIVE_PRIORITY`) : `ai/
#: action_generators.py` pour le troisieme, `test_nc_priority_tiers_offline` et
#: `probe_170_playbook_priority` pour les deux premiers. Voie invisible d'un recensement
#: d'`ImportFrom` -- #485-r1-r1 les a retires, cliquet `probe_485r1r1_acces_attributaires.py`.
from ._base import NCContext, NonComparablePlaybook, NATIVE_PRIORITY, native_priority, \
    _has_valid_targets
from .bloody_fury import BloodyFuryPlaybook
from .vexilla_magnifica import VexillaMagnificaPlaybook
from .fighting_retreat import FightingRetreatPlaybook
from .fire_and_reposition import FireAndRepositionPlaybook
from .aberrant_hypermorph import AberrantHypermorphPlaybook
from .nova_boost import NovaBoostPlaybook
from .nova_shield import NovaShieldPlaybook
from .invocation_of_machine_vengeance import InvocationOfMachineVengeancePlaybook   # 1172 (#1027)
from .solar_atomizer import SolarAtomizerPlaybook                                    # 1174 (#1027)
from .heals import (
    RitesOfRestorationPlaybook, CombatRestorativesPlaybook, DefendTheDivineWorkPlaybook,
    RevitalizingMalignancyPlaybook, InspiredToGreatnessPlaybook
)
from .scarab_summon import ScarabSummonPlaybook
from .get_em_runtz import GetEmRuntzPlaybook
from .grot_tank import GrotTankPlaybook
from .gauntlets_of_ultramar import GauntletsOfUltramarPlaybook
from .hammer_of_wrath import HammerOfWrathPlaybook
from .heroic_fusillade import HeroicFusilladePlaybook
from .doctrina_imperatives import DoctrinaImperativesPlaybook
from .stormcaller import StormcallerPlaybook
from .it_itches import ItItchesPlaybook
from .the_quickening import TheQuickeningPlaybook
from .black_rage import BlackRagePlaybook
from .vigilance_eternal import VigilanceEternalPlaybook
from .kill_maim_burn import KillMaimBurnPlaybook
from .euphoric_strikes import EuphoricStrikesPlaybook   # #974 -- 1198, `emperExultant`
from .scarab_hive import ScarabHivePlaybook
from .cord_claw import CordClawPlaybook
from .poxwalkers import SpawnPoxwalkersPlaybook
from .foul_infusion import FoulInfusionPlaybook
from .holy_duel import HolyDuelPlaybook
from .grapnel_launcher import GrapnelLauncherPlaybook
from .early_warning_override import EarlyWarningOverridePlaybook
from .dark_talon_strike import DarkTalonStrikePlaybook
from .thrice_blessed_conflagration import ThriceBlessedConflagrationPlaybook
from .send_in_the_next_wave import SendInTheNextWavePlaybook
from .incursion import IncursionPlaybook
from .master_of_the_tutelaries import MasterOfTheTutelariesPlaybook
from .supreme_commander import SupremeCommanderPlaybook
from .hellfyre_missile_rack import HellfyreMissileRackPlaybook
from .unstoppable_momentum import UnstoppableMomentumReworkedPlaybook
from .mind_control import MindControlPlaybook
from .unbreakable_duty import UnbreakableDutyPlaybook
from .exemplar_of_the_montka import ExemplarOfTheMontkaPlaybook
from .attempted_possession import AttemptedPossessionPlaybook
from .bio_minefield import BioMinefieldPlaybook
from .adaptive_strategy import AdaptiveStrategyPlaybook
from .storm_of_wrath import StormOfWrathPlaybook
from .alpha_warrior import AlphaWarriorPlaybook
from .calibanite_greatsword import CalibaniteGreatswordPlaybook
from .exemplar_of_hate import ExemplarOfHatePlaybook
from .fear_of_the_unseen import FearOfTheUnseenPlaybook
from .foehammer import FoehammerPlaybook
from .storm_speeder import DeathOnTheWindPlaybook, HailstrikePlaybook
from .ordnance_battery import ForwardSpotterPlaybook, MalleusRocketLauncherPlaybook
from .necro_reanimator import NanoscarabRepairProtocolsPlaybook, ReanimationBeamPlaybook
from .twin_smart_missile_system import TwinSmartMissileSystemPlaybook
from .squig_mine import SquigMinePlaybook
from .crusade_of_wrath import CrusadeOfWrathPlaybook
from .daemonic_patrons import DaemonicPatronsPlaybook
from .death_from_above import DeathFromAbovePlaybook
from .sternguard_focus import SternguardFocusPlaybook
from .war_howl import WarHowlPlaybook
from .waaagh import WaaaghPlaybook
from .spore_mine_launcher import SporeMineLauncherPlaybook
from .ironkin_steeljack import IronkinSteeljackPlaybook
from .titanhammer_squad import TitanhammerSquadPlaybook
from .daemon_prince import AetherStridePlaybook, InfernalCannonPlaybook
from .doombolt import DoomboltPlaybook
from .swooping_hawk import SwoopingHawkPlaybook
from .empyric_ambush import EmpyricAmbushPlaybook
# #975 -- les CINQ faces DECISION du lot AdeptusMechanicus / LeaguesOfVotann / T'au.
from .sentinel_directives import SentinelDirectivesPlaybook
from .rad_bombardment import RadBombardmentPlaybook
from .graviton_rifle import GravitonRiflePlaybook
from .augmented_assault import AugmentedAssaultPlaybook
from .exemplar_of_the_kauyon import ExemplarOfTheKauyonPlaybook
# #977 -- forme B ABSOLUE (jamais `from . import X`, qui passe A TRAVERS le paquet et a deja
# referme un SCC module-level de 5) : une seule arete par module, et la liaison reste patchable.
import engine.playbook.noncomparable.worldeaters as _we
import engine.playbook.noncomparable.thunderous_assault as _ta
from .devastating_refrain import DevastatingRefrainPlaybook
from .duty_eternal import DutyEternalPlaybook
# #985 -- les dernieres faces DECISION d'active.
from .silent_death import SilentDeathPlaybook
from .heavy_rail_rifle import HeavyRailRiflePlaybook


# Registre abilityType -> instance de playbook (remplace le switch `kind`).
PLAYBOOKS: dict[int, NonComparablePlaybook] = {
    pb.ABILITY_ID: pb for pb in (
        BloodyFuryPlaybook(),
        VexillaMagnificaPlaybook(),
        FightingRetreatPlaybook(),
        FireAndRepositionPlaybook(),    # 1063 (#567-r1) — util = 1.5 + 20*(distance MOYENNE aux
        #                                 ennemis, division ENTIERE) + Tile(7). Terme
        #                                 position-dependant SEUL : la cible n'y entre pas.
        AberrantHypermorphPlaybook(),
        NovaBoostPlaybook(),
        NovaShieldPlaybook(),
        InvocationOfMachineVengeancePlaybook(),   # 1172 admecBossBelisarius -- util = 1 + (position != origine) ; tier -1000
        SolarAtomizerPlaybook(),                  # 1174 admecBossBelisarius -- util = 1 + |bande| + 20*|ennemis de la bande| ; tier 100
        RitesOfRestorationPlaybook(),
        CombatRestorativesPlaybook(),
        DefendTheDivineWorkPlaybook(),
        RevitalizingMalignancyPlaybook(),
        InspiredToGreatnessPlaybook(),
        ScarabSummonPlaybook(),
        GetEmRuntzPlaybook(),
        BioMinefieldPlaybook(),         # 1144 (#939) — util = 100 * |GetFreeAdjacentTiles(cible)|
        #                                 (IBattleQuery slot 82) + 100 * PV%(cible), gate count > 0,
        #                                 MIN_UTILITY = 1 (cctor). Position-INDEPENDANTE -> to=None.
        GrotTankPlaybook(),             # 1057 — util = #ennemis dans le DISQUE r=3 autour de la
        #                                 tuile de spawn (= la portee Blast du tank), gate u > 0
        #                                 (IdunBattle.AI.Playbook.Loki.GrotTankPlaybook$$GetUtility)
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
        # #362 (residu #356-r1) — DEBLOQUE par l'oracle NC (#350-r3) : meme forme que 1202 (utilite
        # de DEGAT interne) PLUS le gate `WillNormalAttackKill` de Stormcaller. L'oracle repondait
        # deja pour 1132, mais sans playbook porte `probe_344 --oracle auto` refusait (rc 2) : la
        # comparaison aurait oppose le chemin GENERIQUE a une capture qui contenait, elle, l'event
        # d'attaque NORMALE construit par ce meme gate.
        KillMaimBurnPlaybook(),         # 1132 — degat de l'ability ; `continue` si la normale sure-kill
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
        # #129 -- MEME famille `GetTilesInBestLine` que 1092, face DECISION ABSENTE jusqu'ici (la face
        # COMBAT etait portee et fidele) : l'ability ne pouvait donc JAMAIS etre proposee par le moteur.
        ThriceBlessedConflagrationPlaybook(),  # 1187 (adeptExorcist, MoW) -- cible=UNITE ALLIEE
        #                                 (buff 1401/1436), util=#ennemis continus alignes depuis SA
        #                                 tuile, ring=SurroundingTiles r=1 SANS porte d'elevation,
        #                                 UN SEUL tri (count DESC), MIN_UTILITY=1 (IdunBattle.AI.Playbook.Loki.ThriceBlessedConflagrationPlaybook$$EvaluateNonComparable)
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
        # #487-r1 -- face DECISION de 1088, dont la face COMBAT etait portee et confrontee (#487).
        # Utilite CONSTANTE = #ennemis ayant pris du `DamageProfileType.Psychic` ce tour ; MIN_UTILITY
        # = 1 (le `.cctor`), donc l'ability n'est PAS proposee tant que personne n'a ete arme.
        # ⚠ Sa hierarchie a ete relue dans `frida/classes.tsv` : `NonComparablePlaybook`1` -- le
        # `.ctor` du decompile NOMME `ComparablePlaybook..ctor` (corps gshared FONDU), et la fiche
        # `case-487` §7 avait recopie ce nom.
        HellfyreMissileRackPlaybook(),  # 1088 (IdunBattle.AI.Playbook.Loki.HellfyreMissileRackPlaybook$$EvaluateNonComparable)
        # #498-r1 -- face DECISION de 1152, dont la face COMBAT etait portee et confrontee (#498).
        # Utilite = #ennemis TRAVERSES par la charge (PREFIXE : `break` a la 1re tuile ou
        # `CanContinue` refuse) ; MIN_UTILITY **DYNAMIQUE** 2/1 selon
        # `BasePlaybook$$EnemyCouldBeDamagedWithNormalAttack(caster)` -- deux statiques au `.cctor`.
        UnstoppableMomentumReworkedPlaybook(),  # 1152 (IdunBattle.AI.Playbook.Loki.UnstoppableMomentumReworkedPlaybook$$EvaluateNonComparable)
        # #552 -- face DECISION de `1164 MindControl`, ABSENTE jusqu'ici (la face COMBAT l'etait
        # aussi : l'ability etait un NO-OP silencieux des DEUX cotes). Patron IDENTIQUE a
        # `VexillaMagnificaPlaybook` : `IdunBattle.AI.Playbook.Loki.MindControlPlaybook$$
        # EvaluateNonComparable` = `Fix64(GetStat(cible, 5 = HEALTH))`, `MIN_UTILITY = 1` (cctor).
        # La base est `NonComparablePlaybook` -- LUE dans `classes.tsv`, le ctor gshared etant
        # mislabele `ComparablePlaybook<...>` par ghidra.
        MindControlPlaybook(),          # 1164 -- util = PV COURANTS de la cible ENNEMIE
        # #590 -- face DECISION de `1101 AttemptedPossession`, ABSENTE jusqu'ici (comme la face
        # COMBAT : l'ability etait un NO-OP silencieux des DEUX cotes). `IdunBattle.AI.Playbook.
        # Loki.AttemptedPossessionPlaybook$$EvaluateNonComparable` = un COMPTEUR 1/2/3 (plancher
        # Fix64(1), +1 si la cible a des summons, +1 si elle a une cible d'attaque normale),
        # `MIN_UTILITY = 1` (cctor). Le port rend le PLANCHER : les deux increments exigent des
        # substrats absents de `NCContext` (`parentId` d'une unite ennemie, cibles d'attaque par
        # unite) -- residu `#590-r7`. Base `NonComparablePlaybook` LUE dans `classes.tsv`.
        AttemptedPossessionPlaybook(),  # 1101 -- util = PLANCHER Fix64(1) (increments non portes)
        # #572-r2 -- face DECISION de `1061 UnbreakableDuty`, dont la face COMBAT etait portee et
        # confrontee (#572). Utilite CONSTANTE = `Fix64(1)` = `MIN_UTILITY` (le MEME statique) :
        # tout le discriminant est dans `GetUseProbability`, dont le ZERO (aucun allie a portee ET
        # moins de deux heros imperiaux morts) fait S'ABSTENIR le natif. Base
        # `NonComparablePlaybook` LUE dans `classes.tsv` ; slots `0x75`/`0x7d` resolus dans
        # `metadata/interface_slots.tsv` (l'`etage manquant` que la fiche annoncait).
        UnbreakableDutyPlaybook(),      # 1061
        # Face DECISION de `1210 ExemplarOfTheMontka` (`tauFarsight`), portee avec sa face COMBAT.
        # Reachability LUE dans `metadata/active_playbook_builders.tsv` (`active 1210 ->
        # ...ExemplarOfTheMontkaPlaybook`, une seule entree, dict `active` seul). Meme forme
        # d'`EvaluateNonComparable` que 1061 -- utilite CONSTANTE `Fix64(1)` = `MIN_UTILITY` --
        # mais le gate est une surcharge DIRECTE du slot 4 (`ShouldEvaluate = HasNormalAttackTarget`),
        # pas un `GetUseProbability` : aucun tirage aleatoire, donc le port peut etre EXACT.
        ExemplarOfTheMontkaPlaybook(),  # 1210
        # #945 -- les QUATRE faces DECISION `NonComparable` du lot `IdunBattle.AI.Playbook.Loki.*`
        # (base LUE dans `frida/classes.tsv` pour les quatre ; le `.ctor` NOMME
        # `ComparablePlaybook<...>` pour toutes, corps trivial DEDUPLIQUE -- piege de #487-r1).
        # Aucune ne surcharge `get_Priority` (absentes du sweep exhaustif #170) -> tier 0.
        AdaptiveStrategyPlaybook(),     # 1005 -- util = #allies du caster NON-HEROS adjacents a la
        #                                 CIBLE ; gate `if (1 < n)` INLINE (pas de `.cctor`).
        #                                 ⚠ le playbook ancre sur `Target@+0x60` la ou
        #                                 `...AdaptiveStrategyAbility$$ExecuteBehaviour` ancre sur
        #                                 `Caster@+0x48` : ecart NATIF, transcrit tel quel.
        StormOfWrathPlaybook(),         # 1019 -- util = |GetChainedUnits(cible, onlyFriends: true)|
        #                                 (slot IBattleQuery 16), CIBLE COMPRISE ; MIN_UTILITY = 2
        #                                 construit INLINE dans la methode, pas dans un `.cctor`.
        AlphaWarriorPlaybook(),         # 1112 -- util BOOLEENNE `HasSummonTargetInAttackRangeAtTile`
        #                                 (slot 195) sur la TUILE de spawn ; MIN_UTILITY = 1
        #                                 (`.cctor`) en fait un VETO. Gate slot 4 = le corps folde
        #                                 `AlphaWarriorPlaybook$$ShouldEvaluate` (turnsStarted > 1).
        CalibaniteGreatswordPlaybook(),  # 1189 -- TOGGLE self-cast : `Fix64(int.MaxValue)` emis ssi
        #                                 `cond XOR HasEffect(CalibaniteGreatswordSweep)`, et
        #                                 SEULEMENT depuis l'origine (`casterPosition != current`
        #                                 -> bucket vide).
        # #957 -- les TROIS faces DECISION `NonComparable` du lot (base LUE dans `frida/classes.tsv`
        # pour les trois ; le `.ctor` NOMME `ComparablePlaybook<...>` pour toutes, corps trivial
        # DEDUPLIQUE -- piege de #487-r1 / #945). Recensement des methodes fait AU BLOC d'adresses
        # (`ghidra/functions.tsv`), pas par grep : les trois classes ont exactement trois corps
        # CONTIGUS, rien n'y est fondu. Aucune ne surcharge `get_Priority` (absentes du sweep
        # exhaustif #170) -> tier 0.
        ExemplarOfHatePlaybook(),       # 1140 -- util = 1 + PV%(cible)/100 + 2*(NON Infiltrate)
        #                                 + 1*(Chaos) ; cible `Object` ECARTEE (`continue`).
        #                                 `statPart = 1 = CurrentPct` (contraste 1164, qui lit
        #                                 `Current`) ; `0x7ea` est le PSEUDO-trait de GRANDE-ALLIANCE
        #                                 Chaos, derive du `GrandAllianceId` -- un `HasTrait` sur les
        #                                 `traits` gameconfig rendrait la branche MORTE.
        FearOfTheUnseenPlaybook(),      # 1115 -- VETO : utilite CONSTANTE 10 sur SOI, emise ssi
        #                                 l'UNION des cibles d'attaque normale (`IBattleQuery` slot
        #                                 0x45, sur TOUTES les tuiles de move) est VIDE. Aucun appel
        #                                 a `GetEligibleTargetsSelectable` dans le corps natif.
        FoehammerPlaybook(),            # 1097 -- util = |unites MORTES du plateau, DEUX camps|
        #                                 (`IBattleQuery` slot 0x8b, `playerEntityId` NUL),
        #                                 CONSTANTE. ⚠ QUIRK : `...FoehammerAbility$$ExecuteBehaviour`
        #                                 compte, lui, `UnitsWithTrait(AllDeadOrResurrectedUnits(),
        #                                 Hero)` -- le playbook n'a ni le filtre `Hero` ni la branche
        #                                 « ressuscite ». Ecart NATIF, transcrit tel quel.
        # #967 -- les SIX faces DECISION des TROIS MACHINES OF WAR dont la face COMBAT etait deja
        # portee ET confrontee (case-90 / case-117 / #902). Base `NonComparablePlaybook`1` LUE dans
        # `frida/classes.tsv` pour les six ; reachability LUE dans
        # `metadata/active_playbook_builders.tsv` (six entrees du dict `active`, une par ability) ;
        # recensement AU BLOC d'adresses (`probe_967_playbook_blocks.py`) : six blocs CONTIGUS,
        # rien de fondu dedans. Deux surchargent `get_Priority` (sweep #170) : 1213 = 1000,
        # 1223 = -1000 ; les quatre autres sont hors table -> tier 0.
        DeathOnTheWindPlaybook(),       # 1213 (`darkaStormSpeeder`) -- util = #ennemis que le
        #                                 barrage frapperait ({tuile visee} UNION la ligne de
        #                                 `nrOfTiles-1` hexes la plus peuplee du ring-1), MIN = **2**
        #                                 (la seule des six a ne pas valoir 1). ⚠ L'arbre DSL est
        #                                 bati hors boucle mais EVALUE par `ITargetsSelector.Count`
        #                                 slot 2 sur le contexte de CHAQUE cible -> le terme n'est
        #                                 PAS constant sur les cibles. Gate `ShouldEvaluate` PROPRE
        #                                 (`HasPossibleTarget`), pas le corps folde d'AlphaWarrior.
        HailstrikePlaybook(),           # 1214 (`darkaStormSpeeder`) -- util = (100 - PiercingRatio
        #                                 de l'arme de l'allie vise) + `rng.Next(0,10)` + 500 si
        #                                 (Overwatch ou (arme/ability a distance ET peut attaquer)).
        #                                 Le terme ALEATOIRE n'est pas portable (#967-r3).
        MalleusRocketLauncherPlaybook(),  # 1142 (`astraOrdnanceBattery`) -- util = +3/-3 pour
        #                                 l'occupant de la tuile visee, +1/-1 par unite ADJACENTE
        #                                 (ennemi/ami) ; gate INLINE `util > 0` en plus du MIN = 1.
        #                                 `GetAdjacentDamageTargets` ancre sur `Target@+0x60`.
        ForwardSpotterPlaybook(),       # 1143 (`astraOrdnanceBattery`) -- util = **1** + #tuiles
        #                                 libres adjacentes a l'allie vise d'ou le Cadian invoque
        #                                 aurait une cible (slot 195). Le plancher `Fix64(1)` POSE
        #                                 AVANT la boucle est ce qui separe 1143 d'`AlphaWarrior`
        #                                 (1112), qui partage le slot mais emet le booleen NU et
        #                                 devient donc un VETO. Porteur MoW -> branche
        #                                 `...WithMachineParent` (tous les ennemis), qui ferme #945-r1.
        NanoscarabRepairProtocolsPlaybook(),  # 1224 (`necroReanimator`) -- util = `GetStat(cible,
        #                                 0 = ATTACK)`. ⚠ MEME squelette que `MindControlPlaybook`,
        #                                 qui lit `5 = HEALTH` au MEME emplacement : seul l'ordinal
        #                                 differe. Ne lit PAS `hpToRepair` (c'est l'EFFET 1545 qui
        #                                 le lit, #902).
        ReanimationBeamPlaybook(),      # 1223 (`necroReanimator`) -- util CONSTANTE `Fix64(1)` =
        #                                 MIN_UTILITY : keep-first sur l'ordre du selecteur.
        #                                 PRIORITY = **-1000** (octets `mov eax,0xFFFFFC18 ; ret`)
        #                                 -> 1224 (tier 0) prime TOUJOURS sur elle, par l'ORDRE des
        #                                 generateurs et non par comparaison d'utilites.
        # #970 -- faces DECISION `NonComparable` de MACHINES OF WAR (base LUE dans
        # `frida/classes.tsv` : `NonComparablePlaybook`1` pour les deux ; leur `.ctor` NOMME
        # `ComparablePlaybook<...>`, corps trivial DEDUPLIQUE -- piege de #487-r1 / #945 / #957).
        # Le refus « porteur MoW => hors face DECISION » (`nonattack.py`) est PERIME :
        # `DefaultMachineTactic$$.ctor` pose `GetDefaultActiveAbilityActionGenerators`, donc les
        # MEMES generateurs NC par tier -- et 1187 (`adeptExorcist`, MoW) est deja portee par
        # cette voie. Corollaire : `ctx.reach_nc == []`, donc AUCUN des deux ne peut heriter
        # `_PlanTargetPlaybook` (son sweep serait vide) -> `NonComparablePlaybook` + `fromHere`.
        TwinSmartMissileSystemPlaybook(),  # 1161 (`tauBroadside`) -- utilite CONSTANTE `Fix64(1)`,
        #                                 cible TIREE AU SORT (`IPseudoRNG` slot 6 `NextElement`),
        #                                 selecteur `GetEligibleTargetsEntities` (domaine UNITE),
        #                                 et le SEUL `Bucket` du lot construit SANS borne.
        SquigMinePlaybook(),            # 1201 (`orksRukkatrukk`) -- util = 1 + |GetAdjacentEnemies
        #                                 (tuile, caster)| (`IBattleQuery` slot 0x7f, arite 3),
        #                                 gate `IsFreeTile` DANS le playbook, domaine TUILE.
        #                                 `PRIORITY = -100` : octets `mov eax,0xFFFFFF9C` cites
        #                                 dans `NATIVE_PRIORITY`.
        # #969 -- les CINQ faces DECISION de categorie EFFECT/BUFF dont la face COMBAT etait deja
        # portee. Base `NonComparablePlaybook`1` LUE dans `frida/classes.tsv` pour les cinq -- et le
        # `.ctor` NOMME `ComparablePlaybook<...>` pour les CINQ (corps gshared DEDUPLIQUE, piege de
        # #487-r1 / #945 / #967). La fiche `#893-r1` du backlog avait recopie ce faux nom pour 1049.
        # Reachability LUE dans `metadata/active_playbook_builders.tsv` : cinq entrees du dict
        # `active`, une par ability -> aucune n'est du code registered-but-dead. Aucune ne surcharge
        # `get_Priority` (absentes du sweep exhaustif #170) -> tier 0 pour les cinq.
        CrusadeOfWrathPlaybook(),       # 1049 (`templHelbrecht`) -- util = #allies que le buff
        #                                 toucherait DEPUIS la position candidate (le sous-arbre
        #                                 `crusade_of_wrath_buff_targets` de la face COMBAT, evalue
        #                                 par tuile) ; cible = le CASTER (self-cast). Le `.cctor`
        #                                 pose DEUX statiques : `1` (min + facteur) et `0.1`
        #                                 (facteur de `GetUseProbability`). Gate DETERMINISTE
        #                                 `maxBuffed > 0`. POSITION-DEPENDANTE -> il se deplace.
        DaemonicPatronsPlaybook(),      # 1203 (`emperFlawlessBlade`) -- util = PV COURANTS de la
        #                                 cible ; gate `continue` si `WillNormalAttackKill`. Meme
        #                                 squelette que `MindControlPlaybook` + le gate de
        #                                 `KillMaimBurnPlaybook`.
        DeathFromAbovePlaybook(),       # 1003 (`ultraInceptorSgt`) -- util = #tuiles ou un Inceptor
        #                                 peut atterrir autour de la cible. ⚠ Le corps appele est
        #                                 nomme `SpawnTermagantsAbility$$<ExecuteBehaviour>b__1_0`
        #                                 par ghidra (fusion ICF) : c'est l'arbre de 1003. Surcharge
        #                                 DIRECTE du slot 4 (`GetBestTarget` + `GetNumSummons`).
        SternguardFocusPlaybook(),      # 1228 (`darkaSternguard`) -- util = 1 + 10 si un AUTRE Dark
        #                                 Angel ami est adjacent a la POSITION DU CASTER. ⚠ Terme
        #                                 calcule DANS la boucle des cibles mais argumente par
        #                                 `e.CasterPosition` : il departage les POSITIONS, jamais les
        #                                 cibles -- l'inverse exact du piege de #957.
        WarHowlPlaybook(),              # 1106 (`spaceBlackmane`) -- util PLATE `Fix64(1)`, cible =
        #                                 le CASTER (self-cast, RANGE_SELF). Tout le discriminant
        #                                 est dans `GetUseProbability`, dont le ZERO (le caster n'a
        #                                 AUCUNE cible d'attaque normale sur toute son aire de move)
        #                                 fait S'ABSTENIR le natif -- c'est ce zero qui est porte.
        # #971 -- les trois faces DECISION de categorie SUMMON du lot. Base
        # `NonComparablePlaybook`1` LUE dans `frida/classes.tsv` pour les trois (le `.ctor` est le
        # corps gshared NOMME `ComparablePlaybook<...>` -- meme piege que #487-r1 / #945), et les
        # trois sont ENREGISTREES (`metadata/active_playbook_builders.tsv`).
        WaaaghPlaybook(),               # 1058 -- util = |unites deja buffees| (CONSTANTE, ancree
        #                                 sur l'ORIGINE : l'`AbilityEntities` de
        #                                 `GetNumExistingUnitsBuffed` ne pose AUCUN casterTile)
        #                                 + min(nrOfSummons, |tuiles libres adjacentes a la POSITION
        #                                 CANDIDATE|). Aucun terme ne lit la cible -> la cible EST
        #                                 le 1er element du selecteur. `GetUseProbability` surcharge
        #                                 (0.05*turnsStarted*nBuffed) : porte ALEATOIRE, residu #971-r2.
        SporeMineLauncherPlaybook(),    # 1145 -- cible TUILE (portee PLATEAU ENTIER) ; util =
        #                                 1 + |ennemis a distance EXACTEMENT 2| (`IBattleQuery` slot
        #                                 0x73 `GetUnitsAtDistance` = RING, pas disque),
        #                                 MIN_UTILITY = 1. Position-INDEPENDANTE -> to=None.
        #                                 ⚠ 1145 = `ActiveAbilityType.SporeMineLauncher` ici, PAS le
        #                                 `TriggeredAbilityType.SereneUnifier` de meme ordinal.
        IronkinSteeljackPlaybook(),     # 1219 -- cible TUILE ring-1 libre ; util = -distance de la
        #                                 tuile de spawn a l'ennemi le plus proche (slots 0x4a
        #                                 `GetNearestEnemy` / 0x6c `GetDistance`). ⚠ SEUL playbook du
        #                                 registre SANS borne : ctor de Bucket a DEUX arguments +
        #                                 aucune `.cctor` -> `minUtility.HasValue == false` ->
        #                                 `MIN_UTILITY = -inf` (le 0.0 par defaut aurait tout rejete,
        #                                 l'utilite etant negative par construction).
        # #974 -- face DECISION d'`EuphoricStrikes`. Base `NonComparablePlaybook`1` LUE dans
        # `frida/classes.tsv` (son `.ctor` NOMME `ComparablePlaybook<...>`, corps DEDUPLIQUE --
        # meme piege que #487-r1 / #945 / #957 / #970). Porteur `emperExultant` = HEROS, donc
        # `ctx.reach_nc` n'est PAS vide et `_PlanTargetPlaybook` est atteint (contraste avec les
        # deux MoW de #970 juste au-dessus, pour qui ce sweep aurait ete inerte).
        EuphoricStrikesPlaybook(),      # 1198 (`emperExultant`) -- util = `GetStat(cible,
        #                                 5 = Health)` NUE, avec VETO `WillNormalAttackKill` EN
        #                                 TETE de boucle. Meme utilite que `VexillaMagnifica`
        #                                 (1183), mais l'autre conjoint : la, `HasEffect(Stunned)`
        #                                 SOUS le calcul ; ici le gate AU-DESSUS -- et ce gate
        #                                 CONSTRUIT un `ProbableDamageEvent` que l'oracle capte.
        #                                 A la difference de `KillMaimBurn` (1132), qui porte le
        #                                 MEME gate, le playbook ne construit AUCUNE prediction
        #                                 d'ability : sa trace vaut au plus UN event.
        #                                 ⚠ CONVERGENCE INDEPENDANTE : `DaemonicPatronsPlaybook`
        #                                 (1203, #969, quelques lignes plus haut) a EXACTEMENT ce
        #                                 patron -- PV courants + gate `WillNormalAttackKill`. Deux
        #                                 lectures separees du meme squelette natif.
        TitanhammerSquadPlaybook(),     # 1231 (`astarLysander`) -- util = |ennemis DISTINCTS du
        #                                 caster adjacents a une tuile de la couronne de la TUILE
        #                                 visee| (`GetAdjacentTiles` slot 0x4f o `GetAdjacentEnemies`
        #                                 slot 0x7f, dedoublonne par `PooledHashSet`) ; MIN = 1
        #                                 (`.cctor` = `Fix64(1)`). Domaine TUILE, jumeau de 1201.
        # #978 -- les CINQ faces DECISION `NonComparable` Thousand Sons / Eldar. Base LUE dans
        # `frida/classes.tsv` pour les cinq (`NonComparablePlaybook`1`) ; leur `.ctor` NOMME
        # `ComparablePlaybook<...>`, corps trivial DEDUPLIQUE -- piege #487-r1 / #945 / #957 / #967.
        # Reachability LUE dans `metadata/active_playbook_builders.tsv` : cinq entrees du dict
        # `active`, une par ability. Slots resolus dans `metadata/interface_slots.tsv` (131, 170,
        # 195) et, pour les deux appels de vtable de CLASSE, dans le `global-metadata.dat` via
        # `il2cpp_metadata.type_methods` (`TargetsSelector` slot 23 = `Select`, slot 24 = `Count`)
        # -- recoupes par `ITargetsSelector` (slots 0 et 2), deux sources concordantes.
        DoomboltPlaybook(),             # 1102 (`thousAhriman`) -- util = #ennemis du rayon
        #                                 `SurroundingEnemies(casterTile, ConfigConst(range))`,
        #                                 INDEPENDANTE de la cible (l'arbre est ancre sur le
        #                                 CASTER) mais DEPENDANTE de la position -> Ahriman se
        #                                 deplace pour maximiser sa nappe. ⚠ Quirk transcrit : le
        #                                 disque part de la tuile CANDIDATE, l'`Unobscured` de la
        #                                 tuile REELLE.
        SwoopingHawkPlaybook(),         # 1064 (`eldarAutarch`) -- util = (#ennemis traverses par
        #                                 la vague de 3 tuiles alignees derriere la cible) - 1.
        #                                 SEUL playbook du lot dont le `Fix64(1)` du Bucket est
        #                                 construit INLINE (aucun `.cctor`) -- la borne vaut 1
        #                                 quand meme. Ferme le residu nomme de `dive_attack.py`
        #                                 (`GetTargetUnitsSelector` non porte).
        AetherStridePlaybook(),         # 1208 (`thousDaemonPrince`, MoW) -- VETO booleen : util 1
        #                                 ssi l'empreinte `ThreeTileUnitSpawnShape(cible)` a
        #                                 (a) un allie PSYKER adjacent a l'une de ses tuiles ET
        #                                 (b) une tuile d'ou le summon aurait une cible (slot 195,
        #                                 branche `...WithMachineParent`). Les deux predicats ne
        #                                 partagent PAS leur tuile.
        InfernalCannonPlaybook(),       # 1209 (`thousDaemonPrince`, MoW) -- util = 1 + PV
        #                                 **MAXIMUM** de la cible ennemie. ⚠ `statPart = 2 =
        #                                 Maximum`, la ou 1164 lit `Current` et 1140 `CurrentPct`
        #                                 au MEME emplacement. `PRIORITY = -100` (table mesuree
        #                                 #170) -> le tier 0 d'`AetherStride`, porte par la MEME
        #                                 unite, est evalue AVANT : seul couple de la tranche ou
        #                                 l'ordre des generateurs est reellement exerce.
        EmpyricAmbushPlaybook(),        # 1232 (`eldarLhykhis`) -- util = Max(hi - PV COURANTS de
        #                                 la cible, 1), `hi` = slot 170
        #                                 `GetHighestMaxHealthFromNoneBossConfig` (hisse hors
        #                                 boucle par le natif). Score de FINISSEUR : l'inverse
        #                                 exact de 1209, et le `statPart` est tout le
        #                                 discriminant. `GetUseProbability` = **0.5** -> tirage RNG
        #                                 natif NON porte (residu `#978-r1`).
        # #975 -- les CINQ faces DECISION du lot AdeptusMechanicus / LeaguesOfVotann / T'au, dont la
        # face COMBAT etait deja portee. Base `NonComparablePlaybook`1` LUE dans `frida/classes.tsv`
        # pour les cinq -- et leur `.ctor` est NOMME `ComparablePlaybook<...>` pour les CINQ (corps
        # gshared DEDUPLIQUE, piege de #487-r1 / #945 / #957 / #967 / #969). Reachability LUE dans
        # `metadata/active_playbook_builders.tsv` : cinq entrees du dict `active`, une par ability.
        # AUCUNE ne surcharge `get_Priority` (absentes du sweep exhaustif #170) -> tier 0.
        SentinelDirectivesPlaybook(),   # 1139 (`admecDestroyer`) -- util = **1 +** utilite de degat,
        #                                 avec `minDmg` (var 0xc) SEUL en base -- pas la moyenne
        #                                 `Half(Sum(minDmg, maxDmg))` du chemin generique. Namespace
        #                                 natif SANS `.Loki`, seul du lot.
        RadBombardmentPlaybook(),       # 1116 (`admecDominus`) -- util = |ennemis sur la ligne de
        #                                 tir| (compte NU) ; `MIN_UTILITY = **2**`, seul du lot.
        #                                 ⚠ Le « x 2 » qu'annoncait `_NONCOMPARABLE_ABILITIES` est
        #                                 REFUTE : aucun `op_Multiply` dans le corps.
        GravitonRiflePlaybook(),        # 1206 (`votanIronmaster`) -- util = PV COURANTS de la cible ;
        #                                 double gate `ShouldEvaluate` = `!EnemyWillBeKilledWith
        #                                 NormalAttack && !HasAnyRepairTarget` (Vynn est `Mechanic` :
        #                                 il REPARE plutot que de tirer).
        AugmentedAssaultPlaybook(),     # 1221 (`votanBeserk`) -- MEME corps de boucle que 1206, PLUS
        #                                 un gate PAR POSITION `if (1 < targets.Count)` : au moins
        #                                 DEUX cibles legales depuis la position evaluee.
        ExemplarOfTheKauyonPlaybook(),  # 1087 (`tauShadowsun`) -- util CONSTANTE 1 = MIN_UTILITY sur
        #                                 toute tuile de teleport qui passe `HasEnemyInRange`
        #                                 (= `GetValidTargets(caster, <la tuile visee>, naType)`).
        #                                 Gate porte en BORNE SUP (capteur absent, residu #975-r1).
        # #977 -- les trois NonComparable du lot (base LUE dans `frida/classes.tsv`, jamais dans le
        # nom du corps de `.ctor`, que ghidra etiquette `ComparablePlaybook<T>$$.ctor` pour LES TROIS) :
        _we.JakhalStimmsPlaybook(),     # 1131 (`worldJakhal`) -- util = `1 + Count(AdjacentUnits(P)
        #                                 & AdjacentFriends(cible))`, le MEME set d'AoE que la face
        #                                 COMBAT. Gate `IsDisallowedTarget` a TROIS clauses
        #                                 CONJOINTES (sure-kill normale ET aucun splash ET <= 1 cible
        #                                 d'attaque normale depuis la tuile) -- n'en porter qu'une
        #                                 aurait supprime l'ability en fin de combat.
        _we.OverwhelmingWrathPlaybook(),  # 1141 (`worldEightbound`) -- util = `Count(cibles
        #                                 eligibles de la position)`, cible = la PREMIERE
        #                                 (`Enumerable.First`). Le corps ne BOUCLE PAS sur les cibles.
        _ta.ThunderousAssaultPlaybook(),  # 1043 (`templSwordBrother`) -- DEUX strategies
        #                                 (`GenerateBucketWithMultipleStrategies`), la 1re non nulle
        #                                 gagne. ⚠ `Bucket<T>..ctor` a UN argument + AUCUN `.cctor`
        #                                 -> `MIN_UTILITY = -inf` : le defaut `0.0` l'aurait TUE en
        #                                 silence (son utilite vaut 0 sur tout plateau plat).
        DevastatingRefrainPlaybook(),   # 1188 (`adeptExorcist`, MoW) -- util = **1** + #ennemis du
        #                                 caster OCCUPANT une tuile de la forme (tuile visee + ses
        #                                 voisines dans 3 directions hex). La forme est l'artefact
        #                                 de la face COMBAT (#90-B), appele et non recable ; son
        #                                 `If(IsPositionMachineForCurrentPlayer(2), ...)` exigeait
        #                                 un canal que `NCContext` ne portait pas (#979).
        DutyEternalPlaybook(),          # 1158 (`ultraDreadnought`, MoW) -- util = **1** + Somme sur
        #                                 les 3 tuiles de `ThreeTileUnitSpawnShape(cible)`, sur les
        #                                 unites DES DEUX CAMPS a <= 2 tuiles (`friendsOf = null`),
        #                                 de 10 si adjacente sinon 1. `includeCenter = false` EXCLUT
        #                                 l'occupant de la tuile, donc le `10` ne vaut que pour
        #                                 `distance == 1`. Ferme `#970-r5` (son `BLOCAGE: etage`
        #                                 etait `CtxBoard`, arrive avec #978).
        # #985 -- les dernieres faces DECISION d'active.
        SilentDeathPlaybook(),          # 1068 (`eldarJainZar`) -- utilite PLATE `Fix64(1)` : ce
        #                                 playbook FILTRE les cibles au lieu de les classer. Gate
        #                                 discriminant = `Enemies(of: caster,
        #                                 AdjacentUnits(cible) - cible)` non vide, c.-a-d. la cible
        #                                 a >= 1 allie A ELLE colle a elle. Le `- origin` est LU
        #                                 dans `DSLSelectors$$AdjacentUnits` : sans lui le gate
        #                                 serait TOUJOURS vrai (la cible est ennemie du caster).
        HeavyRailRiflePlaybook(),       # 1160 (`tauBroadside`, MoW) -- utilite de DEGAT du
        #                                 TRIGGERED `1260`, lue au slot 4 (`CalculateAverage`,
        #                                 TRONCATURE) ; branche `IsMachine(cible)` a tirage 50 %,
        #                                 dont le port prend la face DETERMINISTE (util 1).
        #                                 Ferme `#970-r2` : sa premisse (<< config du triggered
        #                                 illisible >>) est REFUTEE -- le triggered partage
        #                                 l'`AbilityConfiguration` de l'active.
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
    "NCContext", "NonComparablePlaybook", "NATIVE_PRIORITY", "native_priority",
    "_has_valid_targets",
    "PLAYBOOKS", "playbook_for", "is_noncomp", "is_summon",
    "choose_action", "BloodyFuryPlaybook", "VexillaMagnificaPlaybook", "FightingRetreatPlaybook",
    "FireAndRepositionPlaybook", "UnbreakableDutyPlaybook", "ExemplarOfTheMontkaPlaybook",
    "AberrantHypermorphPlaybook", "NovaBoostPlaybook", "NovaShieldPlaybook",
    "InvocationOfMachineVengeancePlaybook", "SolarAtomizerPlaybook",
    "RitesOfRestorationPlaybook", "CombatRestorativesPlaybook", "DefendTheDivineWorkPlaybook",
    "RevitalizingMalignancyPlaybook", "InspiredToGreatnessPlaybook", "ScarabSummonPlaybook",
    "GetEmRuntzPlaybook", "GrotTankPlaybook", "GauntletsOfUltramarPlaybook",
    "HammerOfWrathPlaybook",
    "HeroicFusilladePlaybook", "DoctrinaImperativesPlaybook", "StormcallerPlaybook",
    "ItItchesPlaybook", "TheQuickeningPlaybook", "BlackRagePlaybook", "VigilanceEternalPlaybook",
    "KillMaimBurnPlaybook", "ScarabHivePlaybook", "CordClawPlaybook", "SpawnPoxwalkersPlaybook",
    "FoulInfusionPlaybook", "HolyDuelPlaybook", "GrapnelLauncherPlaybook",
    "EarlyWarningOverridePlaybook", "DarkTalonStrikePlaybook",
    "ThriceBlessedConflagrationPlaybook", "SendInTheNextWavePlaybook", "IncursionPlaybook",
    "MasterOfTheTutelariesPlaybook", "SupremeCommanderPlaybook",
    "HellfyreMissileRackPlaybook", "UnstoppableMomentumReworkedPlaybook",
    "MindControlPlaybook", "AttemptedPossessionPlaybook",
    "AdaptiveStrategyPlaybook", "StormOfWrathPlaybook", "AlphaWarriorPlaybook",
    "CalibaniteGreatswordPlaybook",
    "ExemplarOfHatePlaybook", "FearOfTheUnseenPlaybook", "FoehammerPlaybook",
    "DeathOnTheWindPlaybook", "HailstrikePlaybook",
    "ForwardSpotterPlaybook", "MalleusRocketLauncherPlaybook",
    "NanoscarabRepairProtocolsPlaybook", "ReanimationBeamPlaybook",
    "TwinSmartMissileSystemPlaybook", "SquigMinePlaybook",
    "CrusadeOfWrathPlaybook", "DaemonicPatronsPlaybook", "DeathFromAbovePlaybook",
    "SternguardFocusPlaybook", "WarHowlPlaybook",
    "WaaaghPlaybook", "SporeMineLauncherPlaybook", "IronkinSteeljackPlaybook",   # #971
    "TitanhammerSquadPlaybook",
    "DoomboltPlaybook", "SwoopingHawkPlaybook",
    "AetherStridePlaybook", "InfernalCannonPlaybook", "EmpyricAmbushPlaybook",
    "DevastatingRefrainPlaybook", "DutyEternalPlaybook",   # #979
]
