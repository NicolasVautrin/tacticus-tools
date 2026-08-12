"""#983 -- gardes OFFLINE de trois reparations qui n'ont AUCUN autre cliquet.

Ce que ce fichier FIGE, et pourquoi chacun :

1. **`SanguinaryPriestPlaybook` (1296), face MOVE** -- le corps natif est PROPRE (il n'herite pas
   d'`AdjacentUnitPreferenceTriggeredAbilityPlaybook`) et il porte trois particularites qu'un port
   « par ressemblance » aurait toutes ratees : le second `+=` est IMBRIQUE dans le premier `if`
   (donc un ami Mechanical ne rapporte RIEN, meme blesse), il n'y a AUCUN
   `RemoveAll(u.Id == case.Unit.Id)` (donc le mover se compte LUI-MEME), et le court-circuit
   `AffectedByHealAndRepair` PRECEDE le test mecanique (donc une unite Mechanical qui le porte est
   quand meme comptee).
2. **Les DEUX cles de PV publiees par les TROIS producteurs de contexte des feuilles `Tile(7)`**.
   Sans elles, `IsDamagedUnit` se tait PARTOUT et le terme vaut 5N au lieu de 5N + 6D -- une
   sous-estimation SILENCIEUSE, exactement le mode de defaillance que #921-r1 nommait.
3. **La DIRECTION de l'adjacence des deux sites cables (#943-r7)** : `AdjacentUnits(origin)`
   enumere le voisinage des tuiles de l'ORIGINE, donc la source de l'enumeration est le PORTEUR
   (`RitesOfBattle`) ou l'ami Dark Angel (`FearedInterrogator`), jamais la cible. Une couronne hex
   est SYMETRIQUE et ne pouvait pas porter cet axe : il ne devient observable qu'apres le cablage.
4. **La duree d'un `AddEffect`/`AddDynamicStatModifierEffect` s'evalue PAR CIBLE (#448-r6)** --
   `AddEffectBehaviour$$Execute` ecrit `processor[+0x20] = unit` AVANT d'evaluer son champ `+0x78`.
   Le port l'evaluait UNE fois sur le SET, ce qui est le `Max` de
   `TurnsUntilUnitOwnerTurnFormula$$Calculate` : identique tant que le set est HOMOGENE, divergent
   des qu'il ne l'est pas. Le regime discriminant n'est pas constructible par le runner (il exige
   des allies de DEUX joueurs), mais il l'est ici, en montant le `DslContext` a la main.

Tests OFFLINE (aucun runner).
"""
from __future__ import annotations

DECLENCHEUR = {
    "chemins": (
        # Le playbook neuf et son registre.
        "scripts/python/engine/playbook/sanguinary_priest.py",
        "scripts/python/engine/playbook/adjacent_unit_preference.py",
        # Le foyer des TROIS producteurs de contexte des feuilles `Tile(7)` (cles `hp`/`hp_max`).
        "scripts/python/engine/utilities/tile.py",
        # Les deux sites d'adjacence cables par cette tranche, et le foyer qu'ils consomment.
        "scripts/python/engine/entities/effects/loki/dark_angels_passives.py",
        "scripts/python/engine/entities/effects/loki/extra_damage_aura.py",
        "scripts/python/engine/battle_query.py",
        "scripts/python/engine/entities/pathfinding/board.py",
        # Les mirrors d'enum dont les ordinaux sont assertionnes ici.
        "scripts/python/engine/entities/traits/unit_trait.py",
        "scripts/python/engine/entities/triggered_ability_type.py",
        # Le cliquet du canal d'adjacence, dont cette tranche deplace trois registres.
        "scripts/python/probe_433r4r1r4r2_neigh_channel_wired.py",
        # #448-r6 -- le foyer de la duree PAR CIBLE et son unique call-site a noeud.
        "scripts/python/engine/runner/abilities/behaviours/effects.py",
        "scripts/python/engine/runner/abilities/behaviours/__init__.py",
        "scripts/python/engine/runner/abilities/astartes.py",
        "scripts/python/engine/entities/formulas.py",
        # #945-r2 -- le canal runtime des triggered abilities et son unique alimenteur.
        "scripts/python/engine/playbook/noncomparable/_base.py",
        "scripts/python/engine/playbook/noncomparable/calibanite_greatsword.py",
        "scripts/python/engine/ai/action_generators.py",
    ),
    "build": True,
    "toujours": False,
    "raison": (
        "Ces gardes figent des STRUCTURES lues au decompile qu'aucun autre test ne tient : "
        "l'imbrication des deux `+=` de `SanguinaryPriestPlaybook`, l'absence de `RemoveAll` "
        "(le mover se compte lui-meme), l'ordre du court-circuit d'`IsAffectedByHealType`, et la "
        "DIRECTION de l'enumeration d'`AdjacentUnits` -- que la couronne hex, symetrique, ne "
        "pouvait pas exprimer. `build: True` : les quatre ordinaux de trait assertionnes "
        "(1057/5/1000/1029) et l'id 1296 sont LUS dans les tables du hash courant ; un "
        "renumerotage les rend faux, et c'est ce que ce fichier doit voir."
    ),
}

import pytest        # noqa: E402  (le DECLENCHEUR doit rester en tete, cf. `probe_486r15`)

from engine import battle_query as bq
from engine.entities.traits.unit_trait import UnitTrait
from engine.entities.triggered_ability_type import TriggeredAbilityType
from engine.playbook import sanguinary_priest as SP
from engine.playbook.adjacent_unit_preference import TRIGGERED_MOVE_PLAYBOOKS, load_playbook

W_ADJ = 5      # `SanguinaryPriest_AdjacentNonMechanicalFriend`, lu dans `BC.Utilities.Default`
W_DMG = 6      # `SanguinaryPriest_AdjacentDamagedNonMechanicalFriend`


class _Wt:
    """Le minimum de `engine.weights.Weights` que consomme la face MOVE."""

    def __init__(self, table):
        self._t = dict(table)

    def sub(self, category, subkey, default=0):
        return self._t.get((category, subkey), default)


def _wt(adj=W_ADJ, dmg=W_DMG):
    return _Wt({("TriggeredAbilities", SP.WEIGHT_KEY_ADJACENT): adj,
                ("TriggeredAbilities", SP.WEIGHT_KEY_ADJACENT_DAMAGED): dmg})


def _ami(pos, traits=(), hp=None, hp_max=None, uid=None):
    return {"id": uid, "pos": pos, "traits": tuple(traits), "hp": hp, "hp_max": hp_max}


def _ctx(friends, *, self_pos=None, unit_traits=(), self_hp=None, self_hp_max=None,
         neigh_by_pos=None, elev_by_pos=None):
    c = {"friend_units": list(friends), "unit_traits": tuple(unit_traits)}
    if self_pos is not None:
        c["self_pos"] = self_pos
    c["self_hp"], c["self_hp_max"] = self_hp, self_hp_max
    if neigh_by_pos is not None:
        c["neigh_by_pos"] = neigh_by_pos
    if elev_by_pos is not None:
        c["elev_by_pos"] = elev_by_pos
    return c


# --------------------------------------------------------------------- montage / registre

def test_premisse_le_playbook_est_enregistre_sous_son_id_natif():
    """`SanguinaryPriestPlaybook$$.ctor` passe `0x510` = 1296 a la base."""
    assert int(TriggeredAbilityType.SanguinaryPriest) == 1296
    p = load_playbook(1296)
    assert isinstance(p, SP.SanguinaryPriestPlaybook)
    assert int(p.ability_id) == 1296
    assert TRIGGERED_MOVE_PLAYBOOKS[1296] is p


def test_premisse_les_quatre_ordinaux_de_trait_sont_ceux_du_build():
    """Les traits LUS dans `IsAffectedByHealType` / `IsMechanical`, par leur NOM."""
    assert int(SP.TRAIT_AFFECTED_BY_HEAL_AND_REPAIR) == 0x421
    assert tuple(int(t) for t in SP.TRAITS_MECHANICAL) == (0x5, 0x3e8, 0x405)
    assert SP.TRAIT_AFFECTED_BY_HEAL_AND_REPAIR is UnitTrait.AffectedByHealAndRepair


def test_premisse_les_deux_cles_de_poids_sont_distinctes():
    assert SP.WEIGHT_KEY_ADJACENT != SP.WEIGHT_KEY_ADJACENT_DAMAGED
    assert SP.WEIGHT_KEY_ADJACENT.startswith("SanguinaryPriest_")


# --------------------------------------------------------------------- le corps, terme a terme

def test_terme_de_base_un_poids_par_ami_adjacent_non_mecanique():
    """`util += GetUtilityValue(<AdjacentNonMechanicalFriend>)` par ami retenu."""
    p = SP.SanguinaryPriestPlaybook()
    ctx = _ctx([_ami((1, 0)), _ami((0, 1))])
    assert p.calculate_movement_utility_in_steps((0, 0), ctx, _wt()) == float(2 * W_ADJ)


def test_le_terme_DAMAGED_se_CUMULE_avec_le_terme_de_base():
    """Le second `+=` est IMBRIQUE : un ami blesse rapporte 5 + 6, pas 6."""
    p = SP.SanguinaryPriestPlaybook()
    ctx = _ctx([_ami((1, 0), hp=7, hp_max=10)])
    assert p.calculate_movement_utility_in_steps((0, 0), ctx, _wt()) == float(W_ADJ + W_DMG)


def test_un_ami_MECANIQUE_ne_rapporte_RIEN_meme_blesse():
    """L'imbrication du second `if` : le gate `IsAffectedByHealType` porte sur les DEUX termes.

    CONTRE-EPREUVE de la faute naturelle -- appliquer le gate au seul terme de base laisserait
    6 ici, et le test de base ci-dessus resterait VERT."""
    p = SP.SanguinaryPriestPlaybook()
    for trait in SP.TRAITS_MECHANICAL:
        ctx = _ctx([_ami((1, 0), traits=(trait.name,), hp=1, hp_max=10)])
        assert p.calculate_movement_utility_in_steps((0, 0), ctx, _wt()) == 0.0, trait.name


def test_AffectedByHealAndRepair_COURT_CIRCUITE_le_test_mecanique():
    """L'ORDRE est LU : le `HasTrait(0x421)` PRECEDE le test mecanique et le rend inoperant."""
    p = SP.SanguinaryPriestPlaybook()
    ctx = _ctx([_ami((1, 0), traits=(UnitTrait.Mechanical.name,
                                     UnitTrait.AffectedByHealAndRepair.name), hp=1, hp_max=10)])
    assert p.calculate_movement_utility_in_steps((0, 0), ctx, _wt()) == float(W_ADJ + W_DMG)


def test_le_MOVER_se_compte_LUI_MEME_faute_de_RemoveAll():
    """AUCUN `RemoveAll(u.Id == case.Unit.Id)`, et `IsFriend` n'ecarte pas l'egalite.

    C'est l'INVERSE de `SereneUnifierPlaybook` (#456-r1), qui, lui, porte le `RemoveAll`."""
    p = SP.SanguinaryPriestPlaybook()
    ctx = _ctx([], self_pos=(1, 0))
    assert p.calculate_movement_utility_in_steps((0, 0), ctx, _wt()) == float(W_ADJ)
    # ... et son terme DAMAGED aussi, ce qui EXIGE `self_hp`/`self_hp_max` (#983).
    ctx2 = _ctx([], self_pos=(1, 0), self_hp=3, self_hp_max=10)
    assert p.calculate_movement_utility_in_steps((0, 0), ctx2, _wt()) == float(W_ADJ + W_DMG)


def test_le_MOVER_MECANIQUE_ne_se_compte_pas():
    """Le gate porte AUSSI sur le mover -- ses traits arrivent en IDS, pas en noms."""
    p = SP.SanguinaryPriestPlaybook()
    ctx = _ctx([], self_pos=(1, 0), unit_traits=(int(UnitTrait.Vehicle),), self_hp=1, self_hp_max=9)
    assert p.calculate_movement_utility_in_steps((0, 0), ctx, _wt()) == 0.0


def test_hors_ring1_ne_compte_pas():
    p = SP.SanguinaryPriestPlaybook()
    ctx = _ctx([_ami((4, 4), hp=1, hp_max=10)], self_pos=(5, 5))
    assert p.calculate_movement_utility_in_steps((0, 0), ctx, _wt()) == 0.0


# --------------------------------------------------------------------- tri-etat des PV

def test_PV_non_mesures_TAISENT_le_terme_damaged_sans_toucher_au_terme_de_base():
    """TRI-ETAT : `hp`/`hp_max` absents -> degradation RESTRICTIVE et bornee au seul terme DAMAGED.

    C'est le cran qui distingue « non mesure » d'un `0` invente : un `hp_max = 0` ferait passer
    l'unite pour intacte -- meme resultat ici, mais presente comme une MESURE."""
    p = SP.SanguinaryPriestPlaybook()
    for hp, hpm in ((None, 10), (7, None), (None, None)):
        ctx = _ctx([_ami((1, 0), hp=hp, hp_max=hpm)])
        assert p.calculate_movement_utility_in_steps((0, 0), ctx, _wt()) == float(W_ADJ)


def test_hp_egal_hp_max_nest_PAS_damaged():
    p = SP.SanguinaryPriestPlaybook()
    ctx = _ctx([_ami((1, 0), hp=10, hp_max=10)])
    assert p.calculate_movement_utility_in_steps((0, 0), ctx, _wt()) == float(W_ADJ)


def test_poids_absents_des_deux_cotes_rendent_zero():
    """`wt` muet -> 0.0 : le natif ajouterait 0, pas un defaut invente."""
    p = SP.SanguinaryPriestPlaybook()
    ctx = _ctx([_ami((1, 0), hp=1, hp_max=10)])
    assert p.calculate_movement_utility_in_steps((0, 0), ctx, _Wt({})) == 0.0


# --------------------------------------------------------------------- adjacence : liste STOCKEE

def test_l_adjacence_suit_la_liste_STOCKEE_et_pas_la_couronne_hex():
    """Deux tuiles a distance hex 1 qui ne sont PAS voisines dans la liste stockee.

    Regime REEL (mesure #943-r4 : 22 aretes sur `MC2_60`, 8 sur `C4_69`), et c'est ce que
    `battle_query.is_adjacent` doit trancher -- pas `hexgeo.distance == 1`."""
    p = SP.SanguinaryPriestPlaybook()
    voisin = (1, 0)
    assert bq.is_adjacent((0, 0), voisin) is True          # couronne hex : VOISINE
    neigh = {(0, 0): [(0, 1)], (1, 0): [(2, 0)]}           # liste stockee : arete COUPEE
    ctx = _ctx([_ami(voisin, hp=1, hp_max=10)], neigh_by_pos=neigh)
    assert p.calculate_movement_utility_in_steps((0, 0), ctx, _wt()) == 0.0
    # Temoin NON NUL : la meme carte, arete PORTEE -> le terme revient.
    neigh2 = {(0, 0): [voisin], (1, 0): [(0, 0)]}
    ctx2 = _ctx([_ami(voisin, hp=1, hp_max=10)], neigh_by_pos=neigh2)
    assert p.calculate_movement_utility_in_steps((0, 0), ctx2, _wt()) == float(W_ADJ + W_DMG)


def test_la_porte_d_elevation_coupe_aussi():
    p = SP.SanguinaryPriestPlaybook()
    elev = {(0, 0): 0, (1, 0): 2}
    ctx = _ctx([_ami((1, 0), hp=1, hp_max=10)], elev_by_pos=elev)
    assert p.calculate_movement_utility_in_steps((0, 0), ctx, _wt()) == 0.0


# --------------------------------------------------------------------- les TROIS producteurs

def _sources_tile():
    from pathlib import Path
    return Path(__import__("engine.utilities.tile", fromlist=["x"]).__file__).read_text(
        encoding="utf-8")


def test_les_trois_producteurs_publient_hp_et_hp_max():
    """Le cran qui empeche un producteur d'etre oublie -- une feuille lisant une cle absente d'UN
    SEUL des trois rendrait 0 sans erreur (c'est ce que dit le FOYER UNIQUE de `_unit_record`)."""
    src = _sources_tile()
    # `_unit_record` (runner), le record de `scene_tile_leaf_ctx`, celui de `_adjacent_units`.
    assert src.count('"hp": ') >= 2 and src.count('"hp_max": ') >= 2
    assert '"hp": scene.hp(uid), "hp_max": scene.hpmax(uid)' in src
    # ... et les PV du MOVER, dans les TROIS aussi.
    assert src.count('"self_hp"') == 3 and src.count('"self_hp_max"') == 3


def test_les_producteurs_gardent_le_TRI_ETAT():
    """Aucun des trois ne doit rabattre un PV non mesure sur `0` (cf. `_is_damaged`)."""
    src = _sources_tile()
    for interdit in ('"hp": 0', '"hp_max": 0', '"self_hp": 0', '"self_hp_max": 0',
                     '"hp_max": (hc.hp_max if hc is not None else 0)'):
        assert interdit not in src, interdit


def test_is_damaged_est_le_mirror_de_GetStat_Health_Missing():
    """`GetStat(u, Health, Missing) > 0` -- strictement, et sur des entiers."""
    assert SP._is_damaged(9, 10) is True
    assert SP._is_damaged(10, 10) is False
    assert SP._is_damaged(11, 10) is False      # `Missing` negatif : le natif teste `> 0`
    assert SP._is_damaged(None, 10) is False
    assert SP._is_damaged(9, None) is False


# --------------------------------------------------------------------- #943-r7 : la DIRECTION

def test_direction_de_l_enumeration_AdjacentUnits_RitesOfBattle():
    """`AdjacentUnits(Owner)` enumere le voisinage des tuiles de l'ORIGINE = le PORTEUR.

    Carte ASYMETRIQUE : `owner -> att` existe, `att -> owner` non. La couronne hex, symetrique,
    ne pouvait pas distinguer les deux sens -- l'axe n'est observable qu'apres le cablage."""
    from engine.entities.effects.loki.extra_damage_aura import RitesOfBattleExtraDmgEffect

    class _B:                       # board DUCK-TYPE minimal (`by_id` suffit au foyer)
        by_id = {1: {"col": 0, "row": 0, "elevation": 0, "neighbours": [2]},
                 2: {"col": 1, "row": 0, "elevation": 0, "neighbours": []}}

    e = RitesOfBattleExtraDmgEffect("RitesOfBattle_ExtraDmgBasic")
    base = {"owner_id": 1, "att_id": 2, "owner_team": 0, "att_team": 0,
            "att_grand_alliance": "Xenos", "owner_level": 50, "owner_mult": 100,
            "board": _B()}
    # owner en (0,0), attaquant en (1,0) : l'arete SORT de l'origine -> retenu (magnitude non nulle
    # ou None selon le gameconfig ; ce qui est fige ici, c'est le NON-REJET par l'adjacence).
    assert e.create_aura_attack_bonus({**base, "owner_pos": (0, 0), "att_pos": (1, 0)}) is not None
    # sens INVERSE : l'origine est (1,0), dont la liste stockee est VIDE -> rejete.
    assert e.create_aura_attack_bonus({**base, "owner_pos": (1, 0), "att_pos": (0, 0)}) is None


def test_le_canal_absent_retombe_sur_la_couronne_hex_et_pas_sur_un_vide():
    """Board absent -> `(None, None)` -> repli GEOMETRIQUE nomme, jamais un voisinage vide."""
    from engine.entities.effects.loki.extra_damage_aura import RitesOfBattleExtraDmgEffect

    e = RitesOfBattleExtraDmgEffect("RitesOfBattle_ExtraDmgBasic")
    ctx = {"owner_id": 1, "att_id": 2, "owner_team": 0, "att_team": 0,
           "att_grand_alliance": "Xenos", "owner_level": 50, "owner_mult": 100,
           "owner_pos": (0, 0), "att_pos": (1, 0)}          # AUCUN `board`
    assert e.create_aura_attack_bonus(ctx) is not None


# --------------------------------------------------------------------- #448-r6 : duree PAR CIBLE

def _ctx_deux_joueurs():
    """Le regime DISCRIMINANT : des cibles appartenant a DEUX joueurs distincts.

    Le runner ne le construit pas (duel a deux joueurs, cibles = allies du joueur COURANT), et
    c'est POUR CETTE RAISON que l'ecart etait invisible. Un `DslContext` monte a la main l'exprime."""
    from engine.dsl.base import DslContext

    a = {"id": 11, "player": 1}          # le joueur COURANT -> `GetTurnsUntilUnitOwnerTurn` = 0
    b = {"id": 12, "player": 2}          # un AUTRE joueur   -> 1
    return DslContext(units=[a, b], current_player_id=1), a, b


def test_le_noeud_de_duree_evalue_PAR_CIBLE_diverge_du_MAX_sur_un_set_HETEROGENE():
    """Le coeur de #448-r6, dans les DEUX sens.

    * evalue PAR CIBLE (`active_target` lie a chacune) : 0 + 1 = 1 pour l'allie du joueur courant,
      1 + 1 = 2 pour l'autre ;
    * evalue UNE fois sur le SET : `TurnsUntilUnitOwnerTurnFormula$$Calculate` fait un `Max`, donc
      **2 pour les deux** -- l'ancien comportement, et l'ecart exact."""
    from dataclasses import replace as _rep

    from engine.dsl.base import Const
    from engine.entities.formulas import Sum, TurnsUntilUnitOwnerTurn
    from engine.entities.selectors.accessors import ActiveTarget

    ctx, a, b = _ctx_deux_joueurs()
    noeud = Sum(TurnsUntilUnitOwnerTurn(ActiveTarget()), Const(1))
    par_cible = [int(noeud.evaluate(_rep(ctx, active_target=u))) for u in (a, b)]
    assert par_cible == [1, 2], par_cible
    # Le MAX du set -- ce que le port faisait, et ce qu'il ne doit PLUS faire ici. Le SET entier
    # est lie a `active_target` d'un coup, exactement comme l'ancien `TurnsUntilUnitOwnerTurn(group)`.
    sur_le_set = int(noeud.evaluate(_rep(ctx, active_target=[a, b])))
    assert sur_le_set == 2
    assert par_cible[0] != sur_le_set, "temoin NON NUL : sans divergence ce test ne garde rien"


def test_resolve_duration_distingue_NOEUD_scalaire_et_absence():
    """Les trois regimes du foyer, dont le refus de DEVINER une duree sans contexte."""
    from dataclasses import replace as _rep

    from engine.dsl.base import Const
    from engine.entities.formulas import Sum, TurnsUntilUnitOwnerTurn
    from engine.entities.selectors.accessors import ActiveTarget
    from engine.runner.abilities.behaviours import effects as FX

    ctx, a, b = _ctx_deux_joueurs()
    noeud = Sum(TurnsUntilUnitOwnerTurn(ActiveTarget()), Const(1))
    assert FX._duration_is_node(noeud) is True
    assert FX._duration_is_node(3) is False
    assert FX._resolve_duration(None, None, noeud, _rep(ctx, active_target=b)) == 2
    # noeud SANS contexte par-cible -> `None`, jamais une valeur inventee.
    assert FX._resolve_duration(None, None, noeud) is None
    # scalaire : inchange, et prioritaire sur `duration_rounds`.
    assert FX._resolve_duration(None, 5, 3) == 3


def test_les_deux_call_sites_de_titanhammer_passent_des_NOEUDS():
    """Le cran qui empeche la regression : un retour au scalaire re-figerait le `Max`.

    On lit la SOURCE parce que le montage complet de `b3`/`b4` exige un `State` de runner --
    ce que le regime discriminant, lui, ne sait de toute facon pas produire (cf. `_ctx_deux_joueurs`)."""
    from pathlib import Path

    import engine.runner.abilities.astartes as A

    src = Path(A.__file__).read_text(encoding="utf-8")
    assert "dur_b = Sum(TurnsUntilUnitOwnerTurn(ActiveTarget())" in src
    assert "dur_c = Sum(TurnsUntilUnitOwnerTurn(ActiveTarget())" in src
    # ... et le foyer evalue bien DANS la boucle (apres la liaison de la cible courante).
    fx = Path(__import__("engine.runner.abilities.behaviours.effects",
                         fromlist=["x"]).__file__).read_text(encoding="utf-8")
    assert fx.count("replace(entities, active_target=elem)") == 2


# --------------------------------------------------------- #945-r2 : kit DECLENCHE runtime

def _nc(**kw):
    from engine.playbook.noncomparable._base import NCContext

    base = dict(uid=7, origin=(0, 0), units=[{"id": 7, "visualId": "darkaAzrael"}],
                reach_nc=[], epos=[], fpos=[], plan={}, hp_cur_by_id={})
    base.update(kw)
    return NCContext(**base)


def test_le_gate_de_calibanite_lit_le_kit_DECLENCHE_runtime_en_UNION():
    """`UnitExtensions$$HasTriggeredAbility(caster, 0x5f2)` interroge l'ECS, pas le gameconfig.

    Les QUATRE regimes, dont les deux qui ne doivent JAMAIS affirmer : canal absent et RPC muet."""
    from engine.playbook.noncomparable.calibanite_greatsword import (
        CalibaniteGreatswordPlaybook, _EXCLUDING_TRIGGERED)

    p = CalibaniteGreatswordPlaybook()
    assert int(_EXCLUDING_TRIGGERED) == 1522
    # canal ABSENT -> kit gameconfig SEUL (la degradation d'avant, nommee).
    assert p._has_excluding_triggered_ability(_nc()) is False
    # canal PRESENT et porteur -> le gate FERME, ce que le kit gameconfig ne voyait pas.
    assert p._has_excluding_triggered_ability(
        _nc(triggered_kits=lambda: {7: [int(_EXCLUDING_TRIGGERED)]})) is True
    # canal PRESENT, autre id -> pas de faux positif.
    assert p._has_excluding_triggered_ability(_nc(triggered_kits=lambda: {7: [1234]})) is False
    # RPC MUET -> jamais une AFFIRMATION.
    def _boum():
        raise RuntimeError("rpc")
    assert p._has_excluding_triggered_ability(_nc(triggered_kits=_boum)) is False


def test_le_canal_runtime_est_bien_BRANCHE_au_seul_call_site_de_NCContext():
    """Un champ de dataclass sans alimenteur serait un mort-ne -- exactement le vice de #943-r8."""
    from pathlib import Path

    import engine.ai.action_generators as AG
    from engine.playbook.noncomparable._base import NCContext

    assert "triggered_kits" in NCContext.__dataclass_fields__
    src = Path(AG.__file__).read_text(encoding="utf-8")
    assert 'triggered_kits=getattr(ctx, "live_triggered_kits", None)' in src
