"""`#419-r1-tr14-r5-r2-r1-r1-r1-r3` -- crans du dernier lot de `ShouldExecute` a corps propre, du
foyer d'adjacence PARTAGE (`#419-r1-tr10-r2`) et du rang du lifesteal (`#419-r1-tr14-r5-r2-r1-r1-r3`).

Ce fichier est OFFLINE et il l'assume : les quatre gates portes ici lisent le caster, sa tuile de
cast, ses allies ou son compteur de tours -- jamais une prediction. Leur confrontation LIVE demande
une GREFFE (leurs porteurs sont npc, sauf `1147` qui est une MoW), montage non joue par cette
tranche et NOMME dans la case-doc. Ce que ces crans gardent, c'est :

  * l'appariement id <-> corps natif, LU dans le `.ctor` de chaque classe -- le seul canal ou une
    confusion serait visible (cf. la regle projet << un entier qui DESIGNE passe par un ENUM >>) ;
  * le COMPORTEMENT de chaque gate sur les deux cotes de sa bascule ;
  * la ventilation << ce module l'enregistre / son gate vit ailleurs >>, qui est ce qui empeche un
    lecteur de croire un id oublie ;
  * le RANG du terme lifesteal (il doit etre folde DANS `calculate_utility_from_predictions`) ;
  * la table de verite de `MatchesUnitSelectionType`, defaut `Any = true` compris.

ASCII only (console cp1252).
"""
from __future__ import annotations

import pytest

from engine.entities.active_ability_type import ActiveAbilityType
from engine.entities.traits.unit_trait import UnitTrait
from engine.entities.unit_selection_type import (UnitSelectionType,
                                                 matches_unit_selection_type)
from engine.playbook import adjacency as adj
from engine.playbook import get_playbook_or_default
from engine.playbook.base import ComparablePlaybook
from engine.playbook.common import (HEAL_PLAYBOOK, HEAL_PLAYBOOKS, HealPlaybook,
                                    TWISTED_SCIENCE_HEAL_PLAYBOOK, TwistedScience_HealPlaybook)
from engine.playbook.normal_attack_kill_gate import SpiritLeechPlaybook
from engine.playbook.should_execute_gates import (HadesAutocannonsPlaybook,
                                                  LITERAL_ZERO_ELSEWHERE,
                                                  LITERAL_ZERO_THRESHOLD_IDS,
                                                  LiteralZeroThresholdPlaybook,
                                                  ReapingScythePlaybook,
                                                  StormOfFlensingBladesPlaybook)
from engine.playbook.spirit_leech import SpiritLeechLifestealPlaybook

#: Ce qui doit changer pour que cette garde puisse changer de verdict (#486-r15).
DECLENCHEUR = {
    "chemins": (
        # SOCLE COMMUN a tout fichier de test : la cascade des deux `conftest.py` et sa fermeture.
        "scripts/python/conftest.py", "scripts/python/tests/conftest.py",
        # LES QUATRE GATES et leur registre -- l'objet meme du fichier.
        "scripts/python/engine/playbook/should_execute_gates.py",
        # LE RANG du lifesteal : la classe 1104 et le crochet `make_heal_predictions` + son fold.
        "scripts/python/engine/playbook/spirit_leech.py",
        "scripts/python/engine/playbook/base.py",
        # LE FOYER d'adjacence PARTAGE (multi-tuiles + `UnitSelectionType`) et son mirror d'enum.
        "scripts/python/engine/playbook/adjacency.py",
        "scripts/python/engine/entities/unit_selection_type.py",
        # LA CLAUSE BOSS du soin generique, et la classe 1167 qui ne la porte PAS.
        "scripts/python/engine/playbook/common.py",
        # LE GATE DE KILL dont 1104 DERIVE (la ventilation `REGISTERED_ELSEWHERE` est gardee ici).
        "scripts/python/engine/playbook/normal_attack_kill_gate.py",
        # LE SITE d'ou le terme lifesteal a ete RETIRE : un cran lit sa source (`inspect.getsource`),
        # donc une reintroduction du terme apres le gate doit rejouer ce fichier.
        "scripts/python/engine/ai/action_generators.py",
        # LES DEUX ENUMS dont ce fichier FIGE des ordinaux mesures a la conversion : `probe_313`
        # compare le mirror au BUILD et redevient vert des qu'on le regenere apres un renumerotage
        # -- c'est le cran du dessous que ce fichier pose, il doit donc rejouer quand ils bougent.
        "scripts/python/engine/entities/active_ability_type.py",
        "scripts/python/engine/entities/traits/unit_trait.py",
        # LE REGISTRE lui-meme : `get_playbook_or_default` et l'ordre d'enregistrement des modules.
        "scripts/python/engine/playbook/__init__.py",
    ),
    "build": False,
    "toujours": False,
    "raison": (
        "CES chemins parce que chacun porte une assertion NOMMEE de ce fichier, et le premier jet "
        "-- une liste VIDE, que `--proposer` declarait pourtant 'juste' au motif que la cascade "
        "derivee du foyer couvre les 452 modules de fermeture -- a ete REFUSE par le cliquet, avec "
        "raison : `toujours: False` + perimetre vide = un fichier que RIEN ne rejouerait jamais. "
        "La derivee dit ce que le fichier LIT ; la declaration doit dire ce qui le fait CHANGER "
        "D'AVIS, et les deux ne coincident pas. Pas d'autres chemins : ce fichier n'ouvre aucune "
        "donnee, ne monte aucun runner et n'assertionne rien sur les autres playbooks. "
        "`build: False` est LU au contenu -- aucune assertion ne lit `data/symbols/**` ni le "
        "binaire ; les ordinaux (0x420, 0x447, 0x3f2, 0x47b, 0x48f, 0x45f, 0x4bc, 0x12, 0x1c, "
        "`UnitSelectionType` 0..3, `UnitTrait.Summon` = 2) sont figes EN DUR ici EXPRES, et les "
        "deux mirrors d'enum sont declares pour cette raison-la. `toujours: False` : ce fichier ne "
        "garde ni le harnais ni la banque, il garde HUIT foyers nommes."
    ),
}


# ------------------------------------------------------------------ substrats synthetiques minimaux

class _Scene:
    """Le SOUS-ENSEMBLE de `playbook.scene.Scene` que ces quatre gates lisent, et rien de plus.
    Tri-etat conserve : `turns_started` peut rendre `None` (canal muet)."""

    def __init__(self, units, pos_by_id, team_by_id, turns=None, effects=None):
        self.units = units
        self._pos = pos_by_id
        self._team = team_by_id
        self._turns = turns or {}
        self.eff_state = effects

    def pos(self, uid):
        return self._pos.get(uid)

    def team(self, uid):
        return self._team.get(uid)

    def turns_started(self, uid):
        return self._turns.get(uid)


class _Ctx:
    def __init__(self, scene, uid):
        self.scene = scene
        self.uid = uid


def _scene_one(uid=1, pos=(3, 4), team=1, turns=None):
    units = [{"id": uid, "alive": True, "team": team}]
    return _Scene(units, {uid: pos}, {uid: team}, {uid: turns})


# ------------------------------------------------------- cran 1 : appariement id <-> corps natif

def test_les_quatre_ids_sont_ceux_lus_au_ctor():
    """Chaque id vient de `ComparablePlaybook<T>..ctor(this, <id>, klass)` du decompile, jamais du
    nom de la classe -- et le nom PEUT mentir : le playbook `TwistedScience_HealPlaybook` porte
    l'ability `Heal_TwistedScience`."""
    assert int(ActiveAbilityType.StranglethornCannon) == 0x420      # 1056
    assert int(ActiveAbilityType.ReapingScythe) == 0x447            # 1095
    assert int(ActiveAbilityType.StormOfFlensingBlades) == 0x3f2    # 1010
    assert int(ActiveAbilityType.HadesAutocannons) == 0x47b         # 1147
    assert int(ActiveAbilityType.Heal_TwistedScience) == 0x48f      # 1167
    assert int(ActiveAbilityType.Repair_GalvanicField) == 0x45f     # 1119
    assert int(ActiveAbilityType.HealingBalms_Heal) == 0x4bc        # 1212
    assert int(ActiveAbilityType.Heal) == 0x12                      # 18
    assert int(ActiveAbilityType.Repair) == 0x1c                    # 28


def test_les_quatre_gates_sont_au_registre():
    assert isinstance(get_playbook_or_default(1056), LiteralZeroThresholdPlaybook)
    assert isinstance(get_playbook_or_default(1095), ReapingScythePlaybook)
    assert isinstance(get_playbook_or_default(1010), StormOfFlensingBladesPlaybook)
    assert isinstance(get_playbook_or_default(1147), HadesAutocannonsPlaybook)
    for aid in LITERAL_ZERO_THRESHOLD_IDS:
        assert get_playbook_or_default(aid).ability_id == aid


def test_les_ids_dont_le_gate_vit_ailleurs_ne_sont_PAS_enregistres_ici():
    """Leur corps natif EST `utility > Fix64(0)`, mais leur route n'est pas `_best_attack` : les
    inscrire au registre Comparable serait un port MORT (leur `calculate_action_utility` n'est
    jamais appele) et masquerait ou le gate vit vraiment."""
    for aid in LITERAL_ZERO_ELSEWHERE:
        assert aid not in LITERAL_ZERO_THRESHOLD_IDS, aid
        pb = get_playbook_or_default(aid)
        assert not isinstance(pb, LiteralZeroThresholdPlaybook), (aid, type(pb).__name__)
    # les deux routes de SOIN portent bien un playbook DEDIE (leurs gates different)
    assert set(HEAL_PLAYBOOKS) == {int(ActiveAbilityType.HealingBalms_Heal),
                                   int(ActiveAbilityType.Heal_TwistedScience)}


# --------------------------------------------------------------- cran 2 : comportement des gates

def test_seuil_litteral_zero_est_STRICT():
    """`Fix64$$op_GreaterThan` : une utilite EGALE a 0 est REFUSEE."""
    pb = LiteralZeroThresholdPlaybook(1056)
    assert pb.should_execute(None, None, None, 1056, 0.001) is True
    assert pb.should_execute(None, None, None, 1056, 0.0) is False
    assert pb.should_execute(None, None, None, 1056, -1.0) is False


def test_reaping_scythe_exige_plus_de_deux_tours_demarres():
    """`if (!(u > 0)) return false; return GetStat(caster, TurnsStarted) > 2;` -- STRICT."""
    pb = ReapingScythePlaybook()
    for turns, attendu in ((0, False), (2, False), (3, True), (10, True)):
        ctx = _Ctx(_scene_one(turns=turns), 1)
        assert pb.should_execute(ctx, (3, 4), 2, 1095, 50.0) is attendu, turns
    # le seuil d'utilite court-circuite AVANT la stat (ordre natif)
    ctx = _Ctx(_scene_one(turns=99), 1)
    assert pb.should_execute(ctx, (3, 4), 2, 1095, 0.0) is False


def test_reaping_scythe_canal_muet_degrade_en_VRAI():
    """Tri-etat : `turns_started` a `None` = PAS MESURE. Un `0` invente ferait REFUSER l'ability,
    c.-a-d. prononcer un refus que le natif n'a pas prononce."""
    ctx = _Ctx(_scene_one(turns=None), 1)
    assert ReapingScythePlaybook().should_execute(ctx, (3, 4), 2, 1095, 50.0) is True


def test_storm_of_flensing_blades_refuse_toute_tuile_de_deplacement():
    """`return casterTile == GetMainTile(caster)` : l'ability n'est proposee QUE depuis l'origine."""
    pb = StormOfFlensingBladesPlaybook()
    ctx = _Ctx(_scene_one(pos=(3, 4)), 1)
    assert pb.should_execute(ctx, (3, 4), 2, 1010, 5.0) is True     # tuile courante
    assert pb.should_execute(ctx, (4, 4), 2, 1010, 5.0) is False    # tuile de move
    assert pb.should_execute(ctx, (3, 5), 2, 1010, 999.0) is False  # l'utilite n'entre PAS au gate


def test_hades_autocannons_exige_un_ENNEMI_SUMMON():
    """`foreach (u in battleQuery.<slot 0x8e = GetAllEnemiesOf>(owner(caster)))
        if (HasTrait(u, UnitTrait.Summon)) return true;`

    ⚠ **CE CRAN ASSERTIONNAIT L'INVERSE, ET IL AVAIT TORT** (`#419-r1-tr14-r5-r2-r1-r1-r1-r3-r1`).
    Il gardait un port qui lisait les ALLIES du caster, en s'appuyant sur une transcription du
    decompile qui ecrivait << slot 0x8e >> sans le RESOUDRE. Le slot est nomme dans
    `data/symbols/<build>/metadata/interface_slots.tsv` : `IBattleQuery 142 GetAllEnemiesOf 1`,
    `GetAllFriendsOf` etant le slot VOISIN (141). Les deux corps de `IdunBattle.Core.Services.
    BattleQuery` ne different QUE par le sens de la comparaison d'owner (`!=` contre `==`), donc
    l'erreur etait invisible a la lecture du seul pseudo-C. C'est un cran qui FIGEAIT un bug : il
    est ici retourne, avec sa contre-epreuve."""
    pb = HadesAutocannonsPlaybook()
    assert pb.REQUIRED_ENEMY_TRAIT is UnitTrait.Summon and int(UnitTrait.Summon) == 2

    class _S(_Scene):
        def __init__(self, units, traits):
            super().__init__(units, {u["id"]: (0, 0) for u in units},
                             {u["id"]: u["team"] for u in units})
            self.traits = traits

    units = [{"id": 1, "alive": True, "team": 1},      # le caster
             {"id": 2, "alive": True, "team": 1},      # un ALLIE
             {"id": 3, "alive": True, "team": 2}]      # un ENNEMI
    sc = _S(units, {1: frozenset(), 2: frozenset(), 3: frozenset()})
    import engine.playbook.should_execute_gates as SEG
    orig = SEG._entity_traits
    try:
        SEG._entity_traits = lambda scene, uid: scene.traits.get(uid, frozenset())
        # personne ne porte `Summon` -> refus
        assert pb.should_execute(_Ctx(sc, 1), None, 9, 1147, 5.0) is False
        # un ALLIE porteur ne suffit PAS : `GetAllEnemiesOf` ne l'enumere pas
        sc.traits[2] = frozenset({"Summon"})
        assert pb.should_execute(_Ctx(sc, 1), None, 9, 1147, 5.0) is False
        # un ENNEMI porteur valide le gate
        sc.traits[3] = frozenset({"Summon"})
        assert pb.should_execute(_Ctx(sc, 1), None, 9, 1147, 5.0) is True
        # le CASTER porteur ne se valide PAS lui-meme (`GetAllEnemiesOf` exclut son propre owner)
        sc.traits[2] = frozenset()
        sc.traits[3] = frozenset()
        sc.traits[1] = frozenset({"Summon"})
        assert pb.should_execute(_Ctx(sc, 1), None, 9, 1147, 5.0) is False
    finally:
        SEG._entity_traits = orig


# ------------------------------------------------------- cran 3 : la clause BOSS du soin generique

def test_heal_generique_porte_la_clause_boss_et_1167_ne_la_porte_PAS():
    """`Common.HealPlaybook$$ShouldExecute` = `u > 0 && (!IsBoss(caster) || caster != target)` ;
    `TwistedScience_HealPlaybook$$ShouldExecute` = `u > 0` SEUL. Confondre les deux interdirait a un
    boss porteur de TwistedScience de se soigner."""
    assert isinstance(TWISTED_SCIENCE_HEAL_PLAYBOOK, TwistedScience_HealPlaybook)
    assert isinstance(TWISTED_SCIENCE_HEAL_PLAYBOOK, HealPlaybook)      # meme CustomUtility

    sc = _scene_one(uid=7)
    ctx = _Ctx(sc, 7)
    bosses = {7}
    orig = HealPlaybook._is_boss
    try:
        HealPlaybook._is_boss = staticmethod(lambda scene, uid: uid in bosses)
        # caster BOSS : self-heal refuse, soin d'un tiers accepte
        assert HEAL_PLAYBOOK.should_execute(ctx, None, 7, 18, 30.0) is False
        assert HEAL_PLAYBOOK.should_execute(ctx, None, 8, 18, 30.0) is True
        # caster NON boss : self-heal accepte
        bosses.clear()
        assert HEAL_PLAYBOOK.should_execute(ctx, None, 7, 18, 30.0) is True
        # 1167 n'a PAS la clause, meme sur un boster boss
        bosses.add(7)
        assert TWISTED_SCIENCE_HEAL_PLAYBOOK.should_execute(ctx, None, 7, 1167, 30.0) is True
        # la 1re clause reste STRICTE des deux cotes
        assert HEAL_PLAYBOOK.should_execute(ctx, None, 8, 18, 0.0) is False
        assert TWISTED_SCIENCE_HEAL_PLAYBOOK.should_execute(ctx, None, 8, 1167, 0.0) is False
    finally:
        HealPlaybook._is_boss = orig


# --------------------------------------------- cran 4 : le RANG du lifesteal (fold DANS l'etage u)

def test_1104_est_enregistree_par_spirit_leech_et_derive_du_gate_de_kill():
    pb = get_playbook_or_default(1104)
    assert isinstance(pb, SpiritLeechLifestealPlaybook)
    assert isinstance(pb, SpiritLeechPlaybook)      # le gate `!WillNormalAttackKill` est CONSERVE
    assert pb.ability_id == int(ActiveAbilityType.SpiritLeech) == 0x450


def test_le_fold_heal_est_DANS_calculate_utility_from_predictions():
    """Le natif somme `CalculateUtilityFromHealEvent` (slot +0x368) DANS
    `CalculateUtilityFromPredictions`, donc AVANT `ShouldExecute`. Le cran mesure le RANG, pas la
    valeur : un playbook temoin dont `make_heal_predictions` rend un evenement doit deplacer `u`."""
    class _PB(ComparablePlaybook):
        ability_id = -999

        def make_damage_predictions(self, ctx, caster_tile, target, ability_id):
            return []

        def make_heal_predictions(self, ctx, caster_tile, target, ability_id, events):
            return [(10, 99, True, False)]

    class _Wt:
        pass

    class _C:
        wt = _Wt()
        hpmax_by_id = {}

    u_avec, _ = _PB().calculate_utility_from_predictions(_C(), (0, 0), 1, -999, [])
    assert u_avec > 0.0, "le fold heal ne mord pas : le terme n'est PAS au rang natif"
    u_base, _ = ComparablePlaybook().calculate_utility_from_predictions(_C(), (0, 0), 1, -999, [])
    assert u_base == 0.0, "la BASE doit rendre une liste de soins VIDE"


def test_le_generateur_ne_somme_plus_le_lifesteal_apres_le_gate():
    """Le terme ne doit plus etre ajoute au RETOUR de `calculate_action_utility` : c'est
    precisement le rang faux que cette tranche corrige."""
    import inspect
    import engine.ai.action_generators as AG
    src = inspect.getsource(AG.ComparableAbilityGenerator._action_utility)
    assert "_spiritleech_lifesteal_util" not in src, src


# ------------------------------------------------ cran 5 : `UnitSelectionType`, table de verite

def test_matches_unit_selection_type_mirror_du_decompile():
    """`UnitExtensions$$MatchesUnitSelectionType`, verbatim -- y compris le DEFAUT `true`, qui n'est
    pas un `false` prudent : le chemin qui ne satisfait aucune des trois comparaisons saute au
    `return true`."""
    S = UnitSelectionType
    assert (int(S.Any), int(S.OnlyAlive), int(S.OnlyTargetable),
            int(S.OnlyAliveAndTargetable)) == (0, 1, 2, 3)
    for alive in (True, False):
        for tgt in (True, False):
            assert matches_unit_selection_type(S.Any, alive=alive, targetable=tgt) is True
            assert matches_unit_selection_type(S.OnlyAlive, alive=alive, targetable=tgt) is alive
            assert matches_unit_selection_type(S.OnlyTargetable, alive=alive, targetable=tgt) is tgt
            assert matches_unit_selection_type(S.OnlyAliveAndTargetable, alive=alive,
                                               targetable=tgt) is (alive and tgt)
    # une valeur HORS enum passe le filtre (branche par defaut du natif)
    assert matches_unit_selection_type(42, alive=False, targetable=False) is True
    # `is_unit == False` -> refus, avant meme le switch
    assert matches_unit_selection_type(S.Any, is_unit=False, alive=True, targetable=True) is False


def test_le_tri_etat_degrade_la_clause_en_VRAI():
    """`None` = PAS MESURE. Un `False` invente ecarterait une unite que le natif compte."""
    S = UnitSelectionType
    assert matches_unit_selection_type(S.OnlyAliveAndTargetable, alive=True,
                                       targetable=None) is True
    assert matches_unit_selection_type(S.OnlyTargetable, alive=None, targetable=None) is True
    assert matches_unit_selection_type(S.OnlyAliveAndTargetable, alive=False,
                                       targetable=None) is False


# ------------------------------------------------- cran 6 : le foyer d'adjacence est MULTI-TUILES

def test_iterate_tiles_lit_les_pieds_quand_le_canal_les_porte():
    """`EntityExtensions$$IterateTiles` -- TOUTES les tuiles, `feet[0]` etant la MainTile. Sans la
    cle `feet`, le port retombe sur la MainTile SEULE : c'est la degradation d'avant, et le residu
    est alors un trou de SEEDING (`#419-r1-tr10-r2`)."""
    sc = _Scene([{"id": 1, "alive": True, "team": 1, "feet": [(3, 4), (3, 5), (4, 4)]}],
                {1: (3, 4)}, {1: 1})
    assert adj.iterate_tiles(sc, 1) == [(3, 4), (3, 5), (4, 4)]
    sc2 = _Scene([{"id": 1, "alive": True, "team": 1}], {1: (3, 4)}, {1: 1})
    assert adj.iterate_tiles(sc2, 1) == [(3, 4)]
    sc3 = _Scene([{"id": 1, "alive": True, "team": 1}], {}, {1: 1})
    assert adj.iterate_tiles(sc3, 1) == []      # entite sans tuile -> [] (comme le natif)


def test_unit_in_adjacent_tiles_voit_les_pieds_des_DEUX_cotes():
    """`Units(AdjacentTiles(subject)).Contains(other)` : `other` y figure des qu'UN de ses pieds
    tombe dans l'union des ring-1 des pieds de `subject`. Le cran monte une adjacence qui n'existe
    QUE de pied a pied -- les deux MainTiles, elles, sont a distance 2."""
    neigh = {(0, 0): [(1, 0)], (1, 0): [(0, 0), (2, 0)], (2, 0): [(1, 0), (3, 0)],
             (3, 0): [(2, 0)]}
    sc = _Scene([{"id": 1, "alive": True, "team": 1, "feet": [(0, 0), (1, 0)]},
                 {"id": 2, "alive": True, "team": 2, "feet": [(2, 0), (3, 0)]}],
                {1: (0, 0), 2: (2, 0)}, {1: 1, 2: 2})
    assert adj.unit_in_adjacent_tiles(sc, 1, 2, elev={}, neigh=neigh) is True
    # sans les pieds, les deux MainTiles sont a distance 2 : le port ne voit RIEN
    sc_mono = _Scene([{"id": 1, "alive": True, "team": 1}, {"id": 2, "alive": True, "team": 2}],
                     {1: (0, 0), 2: (2, 0)}, {1: 1, 2: 2})
    assert adj.unit_in_adjacent_tiles(sc_mono, 1, 2, elev={}, neigh=neigh) is False


def test_adjacent_tiles_retire_l_empreinte_du_sujet():
    """`if (!inner.Contains(n)) result.Add(n)` : une tuile de l'empreinte n'est jamais sa propre
    voisine, meme quand le graphe la relie a un autre pied."""
    neigh = {(0, 0): [(1, 0)], (1, 0): [(0, 0), (2, 0)], (2, 0): [(1, 0)]}
    sc = _Scene([{"id": 1, "alive": True, "team": 1, "feet": [(0, 0), (1, 0)]}],
                {1: (0, 0)}, {1: 1})
    assert adj.adjacent_positions(sc, 1, neigh=neigh) == {(2, 0)}
    assert adj.is_adjacent_to_entity(sc, 1, (1, 0), elev={}, neigh=neigh) is False
