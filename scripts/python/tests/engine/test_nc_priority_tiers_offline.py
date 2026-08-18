"""#170 -- le POINT D'EXTENSION `PRIORITY` est-il CABLE, ou seulement declaratif ?

Jusqu'a #170 les 35 playbooks NonComparable portes avaient TOUS `PRIORITY = 0` (conclusion
erronee de #115). Les 5 generateurs `NC(1000) NC(100) NC(0) NC(-100) NC(-1000)` du tactic
etaient donc structurellement presents mais JAMAIS exerces : un seul tier peuple. Un filtrage
par tier casse (ou absent) serait passe totalement inapercu.

Ce fichier EXERCE le mecanisme, avec des playbooks STUB (le stub ne vit que dans le test --
aucune invention dans `engine/`) :

  * `choose_action(..., priority=P)` ne retient QUE les abilities du tier P
    (mirror `InitAbilityTypeLists` : `dict[playbook.get_Priority()]`) ;
  * `DefaultAiUnitTactic` prend la PREMIERE action non-nulle de
    `[NC(1000), NC(100), NC(0), NC(-100), NC(-1000), Comparable, Movement]`
    -> un tier SUPERIEUR bat un tier inferieur PAR L'ORDRE, meme a utilite tres inferieure
    (mirror `<CalculateNextActionForUnit>d__5$$MoveNext` : `if (action != 0) break`) ;
  * la table `NATIVE_PRIORITY` et les 3 playbooks portes qui en dependent (NovaBoost 1192 =
    1000, ThriceBlessedConflagration 1187 = 100, NovaShield 1194 = -1000).

La CONFORMITE des valeurs au natif est mesuree live par
`scripts/python/probe_170_playbook_priority.py` (invocation du slot 0 de la vtable
d'interface, sweep exhaustif des 257 ActiveAbilityType). Ici on garde le CABLAGE. ASCII only.
"""
from __future__ import annotations

from types import SimpleNamespace

import pytest

from engine.ai.tactic import DefaultAiUnitTactic, NC_PRIORITY_TIERS
from engine.playbook import noncomparable as NC


class _StubPlaybook(NC.NonComparablePlaybook):
    """Playbook NonComparable minimal : un candidat unique d'utilite fixe."""

    def __init__(self, ability_id: int, priority: int, util: float):
        self.ABILITY_ID = ability_id
        self.PRIORITY = priority
        self.MIN_UTILITY = 0.0
        self._util = util

    def generate_candidates(self, ctx) -> list[dict]:
        return [{"target": 900 + self.ABILITY_ID, "ability": self.ABILITY_ID,
                 "to": None, "pred": self._util}]


class _Ctx(SimpleNamespace):
    """Contexte de decision STUB, avec repli a `None` sur ce qu'il ne porte pas explicitement.

    ⚠ POURQUOI CE REPLI (#10027). Ce fichier garde le CABLAGE DES TIERS -- il n'a aucune opinion
    sur la forme du contexte de decision. Il etait pourtant ROUGE sur `master`, et pas pour une
    raison de tiers : `NonComparableGenerator.generate` a gagne un champ
    (`machine_of_war_position=ctx.machine_of_war_position`, #979 -- le predicat
    `IsPositionMachineForCurrentPlayer(2)` de `DevastatingRefrainAbility$$GetShape`), lu en acces
    DIRECT la ou ses voisins immediats passent par `getattr(ctx, ..., None)`. Le champ EST porte
    par `AiDecisionContext`, donc la production ne casse jamais : c'est le `SimpleNamespace` ecrit
    a la main ici qui a peri -- << un changement de harnais perime les premisses d'un test >>.

    Le repli reproduit le contrat que `NCContext` declare deja pour ce champ
    (`machine_of_war_position: object = None`, tri-etat « non mesure ») et l'etend a tout champ
    futur. Ce n'est PAS un affaiblissement du test : ce qu'il garde reste assert e explicitement --
    un generateur devenu muet ferait rougir `action["ability"] == ...`, pas passer."""

    def __getattr__(self, nom):        # appele UNIQUEMENT quand l'attribut n'est pas porte
        if nom.startswith("__"):
            raise AttributeError(nom)
        return None


def _ctx(ability_ids):
    """Contexte de decision minimal : seul `me.abilities` porte l'information utile ici (les
    stubs n'interrogent ni la geometrie ni la prediction). Les autres champs sont poses pour leur
    TYPE (un `{}`/`[]` la ou le generateur fait `.get`/itere) ; tout le reste replie a `None`."""
    return _Ctx(
        uid=1, origin=(0, 0), reach_nc=[(0, 0)], epos=[], fpos=[], enemies=[],
        neigh_by_pos={}, walkable_by_pos={}, plans={}, hp_cur_by_id={}, elev_by_pos={},
        ability_targets=None, wt=None, is_temporary_by_pos={}, effects_by_pos={},
        obs_units=[], tile_id_by_pos={}, active_ability_levels=None, heal_config=None,
        units=[], cast_from_tiles=None, scene=None, debug=False,
        me={"id": 1, "abilities": [{"id": a, "usable": True} for a in ability_ids]},
    )


@pytest.fixture
def registry():
    """Registre NC temporaire (restaure a la sortie) : deux stubs de tiers DIFFERENTS, le tier
    SUPERIEUR portant l'utilite la PLUS FAIBLE -- c'est ce couple qui rend le tier observable."""
    saved = dict(NC.PLAYBOOKS)
    NC.PLAYBOOKS[9101] = _StubPlaybook(9101, priority=100, util=1.0)     # tier haut, util basse
    NC.PLAYBOOKS[9102] = _StubPlaybook(9102, priority=0, util=999.0)     # tier bas, util haute
    NC.PLAYBOOKS[9103] = _StubPlaybook(9103, priority=-1000, util=500.0)
    try:
        yield
    finally:
        NC.PLAYBOOKS.clear()
        NC.PLAYBOOKS.update(saved)


def test_choose_action_ne_voit_que_son_tier(registry):
    """`choose_action(priority=P)` = UN generateur = le seul bucket `dict[P]`."""
    ctx = _ctx([9101, 9102, 9103])
    assert NC.choose_action(ctx.me["abilities"], ctx, priority=100)["ability"] == 9101
    assert NC.choose_action(ctx.me["abilities"], ctx, priority=0)["ability"] == 9102
    assert NC.choose_action(ctx.me["abilities"], ctx, priority=-1000)["ability"] == 9103
    # tier VIDE -> generateur nul (le tactic descend au suivant), PAS un repli sur un autre tier
    assert NC.choose_action(ctx.me["abilities"], ctx, priority=1000) is None
    assert NC.choose_action(ctx.me["abilities"], ctx, priority=-100) is None
    # priority=None -> tous tiers confondus (argmax pur) : c'est l'ANCIEN comportement, conserve
    # pour les appelants hors-tactic, et il choisit bien l'utilite max
    assert NC.choose_action(ctx.me["abilities"], ctx, priority=None)["ability"] == 9102


def test_le_tier_superieur_bat_l_utilite(registry):
    """Le tactic renvoie la 1re action non-nulle -> 9101 (util 1) bat 9102 (util 999)."""
    action = DefaultAiUnitTactic().calculate_next_action(_ctx([9101, 9102, 9103]))
    assert action["kind"] == "ability"
    assert action["ability"] == 9101 and action["util"] == 1.0


def test_sans_le_tier_haut_le_tier_bas_reprend(registry):
    """Contre-epreuve : retire l'ability de tier 100 -> c'est le tier 0 qui sort (999), et si on
    retire aussi le tier 0 c'est le tier -1000. Le filtrage n'est donc pas un accident d'ordre."""
    assert DefaultAiUnitTactic().calculate_next_action(_ctx([9102, 9103]))["ability"] == 9102
    assert DefaultAiUnitTactic().calculate_next_action(_ctx([9103]))["ability"] == 9103


def test_le_stub_de_contexte_replie_a_None_sans_masquer_ce_qu_il_porte():
    """Contrat du repli (#10027) : ce qui est POSE est rendu tel quel, ce qui est ABSENT rend
    `None` -- jamais un `AttributeError`, jamais une valeur inventee. Le dunder, lui, doit
    continuer a lever, sans quoi `copy`/`pickle`/`inspect` se croiraient servis."""
    c = _ctx([9101])
    assert c.uid == 1 and c.plans == {} and c.me["abilities"][0]["id"] == 9101
    assert c.machine_of_war_position is None          # le champ #979 qui a peri ce fichier
    assert c.un_champ_qui_n_existe_pas_encore is None
    with pytest.raises(AttributeError):
        c.__un_dunder_quelconque__


def test_ordre_des_tiers_du_tactic():
    """`GetDefaultActiveAbilityActionGenerators` : [1000, 100, 0, -100, -1000] puis Comparable."""
    assert NC_PRIORITY_TIERS == (1000, 100, 0, -100, -1000)
    gens = DefaultAiUnitTactic().generators
    assert [g.priority for g in gens[:5]] == list(NC_PRIORITY_TIERS)
    assert len(gens) == 7        # 5 tiers NC + Comparable + Movement


def test_table_native_priority_et_playbooks_portes():
    """La table #170 (22 entrees, toutes des ActiveAbilityType reels) et les 3 portes qui en
    dependent. Les valeurs sont celles de l'enum `AbilityPriority`."""
    assert len(NC.NATIVE_PRIORITY) == 22
    assert set(NC.NATIVE_PRIORITY.values()) <= {1000, 100, -100, -1000}
    assert NC.native_priority(1192) == 1000     # NovaBoost
    assert NC.native_priority(1187) == 100      # ThriceBlessedConflagration
    assert NC.native_priority(1194) == -1000    # NovaShield
    assert NC.native_priority(69) == 0          # attaque normale : hors table -> Normal
    for ability_id, tier in NC.NATIVE_PRIORITY.items():
        pb = NC.PLAYBOOKS.get(ability_id)
        if pb is not None:
            assert pb.PRIORITY == tier, f"ability {ability_id} portee avec un tier faux"
    # tout playbook porte HORS table doit valoir 0 (defaut AbilityPriority.Normal)
    for ability_id, pb in NC.PLAYBOOKS.items():
        if ability_id not in NC.NATIVE_PRIORITY:
            assert pb.PRIORITY == 0, f"ability {ability_id} : tier {pb.PRIORITY} sans source"
