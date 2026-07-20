"""Playbooks NonComparable — une classe Python HOMONYME par playbook natif.

Remplace l'ancien switch `if kind in ("summon","adjacent_count","target_hp")` d'engine_decide
par un mecanisme generique (registre de classes + driver commun). Structure FIDELE au decompile
(confirme sur AberrantHypermorphPlaybook.EvaluateNonComparable @1811197d0) :

  - `ABaseAiActorTactic.InitAbilityTypeLists @1810ed540` range chaque ability NonComparable par
    son playbook dans `dict[get_Priority]` ; `GetDefaultActiveAbilityActionGenerators @1810ed0c0`
    cree UN generator par tier [1000,100,0,-100,-1000] ; le tactic prend le PREMIER generator
    non-vide -> une NC qui passe son MIN_UTILITY prime sur toute Comparable, ET une NC de tier
    superieur prime sur une NC de tier inferieur PAR L'ORDRE (pas l'utilite). get_Priority = slot-0
    de l'interface DAT_1831d4f88 (dispatch runtime FUN_180002560(0, interface, playbook)). #115 (RE
    gqfc5mff6c) : AUCUN playbook n'override ce getter (search_symbols get_Priority / Playbook.*Priority
    / Playbook$$get_ / IsComparable = 0 hit Playbook ; ni BasePlaybook, ni NonComparablePlaybook<T>,
    ni ComparablePlaybook<T> ne le nomment -> il vit UNE fois sur le parent partage, jamais surcharge
    par-leaf). => TOUTES les NonComparable partagent le MEME get_Priority de base = 0 (les 15 portees
    inclus NovaBoost/NovaShield). L'ancien NovaBoost=1000/NovaShield=-1000 venait d'un @1807D66A0
    (`mov eax,0x3E8`) stale/mal-attribue qui NE RESOUT PLUS dans ce build -> supprime. Consequence :
    l'ordre inter-tier NC n'est PAS exerce (un seul tier 0 peuple) ; a l'interieur du tier 0, deux NC
    d'une meme unite se departagent par UTILITE (choose_action argmax), pas par un tier fabrique.
  - Le generator `ActiveAbilityActionGenerator.<GenerateActions>d__7.MoveNext @18119a3f0` BALAIE
    les positions candidates du caster (tuiles de move) et appelle par position
    `<Playbook>.EvaluateNonComparable(this, ctx, position)` : celui-ci cree un Bucket (MIN_UTILITY
    du cctor), enumere les cibles eligibles via `BasePlaybook.GetEligibleTargetsSelectable
    @18111f0d0`, score chacune (`<Playbook>.GetUtility`), et gate `Bucket.AddAction @1813fbcc0`
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
        # #44 (reframe #34) — les 5 playbooks NC du « lead 8 » : le stage agreement les classait
        # « non-attack-oracle » alors qu'ils sont NonComparable NATIFS (EvaluateNonComparable, AUCUN
        # Make*Predictions). Deux familles : utilite ENTIERE (comptage/paliers) pour 1113/1121/1151,
        # utilite de DEGAT interne (CalculateUtilityFromDamageEvent) pour 1163/1202 — cf. HammerOfWrath.
        StormcallerPlaybook(),          # 1113 — #unites dans la zone de glace ; gate WillNormalAttackKill
        ItItchesPlaybook(),             # 1121 — #ennemis pousses ; gates IsDisplaceable + CanBePushed
        BlackRagePlaybook(),            # 1163 — degat de l'attaque NORMALE depuis la tuile de charge
        VigilanceEternalPlaybook(),     # 1202 — degat de l'ability depuis l'hex libre adjacent
        # 1151 TheQuickening : PORTE mais DELIBEREMENT PAS ENREGISTRE — porte de decision native
        # NON RESOLUE (mesure 31337 : le natif DECLINE 1151 au pas 5 alors que l'unique gate du
        # decompile `GetNumAttackTargetsInPosition > 0` passe, et le cast au pas 15 ; l'enregistrer
        # produit un OVERFIRE mesure au s5 + un miss d'ordre au s15 sur utilite PLATE). Voir
        # the_quickening.py et la tache dediee. L'enregistrer sans la porte = anti-pattern #31.
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
    @18119a3f0 + `Bucket.ChooseAction`) : pour chaque ability NC usable de l'unite DU TIER `priority`
    (get_Priority ; None = tous tiers confondus), collecte les candidats de son playbook (generator +
    gate MIN_UTILITY), rend l'argmax STRICT (tie -> 1er) ou None si le generateur est vide.

    Le natif range les NonComparable dans `dict[get_Priority]` (@1810ed540) : un generateur PAR tier,
    evalues dans l'ordre 1000..-1000 AVANT le fallback Comparable. `priority` selectionne ce tier."""
    nc_cands: list[dict] = []
    for ab in (abilities or []):
        pb = playbook_for(ab.get("id"))
        if pb is None or ab.get("usable") is False:
            continue
        if priority is not None and pb.PRIORITY != priority:
            continue   # ability d'un autre tier NonComparable -> pas dans CE generateur
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
]
