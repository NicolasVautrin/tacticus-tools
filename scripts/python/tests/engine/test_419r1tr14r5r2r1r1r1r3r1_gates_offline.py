"""`#419-r1-tr14-r5-r2-r1-r1-r1-r3-r1` -- les crans OFFLINE de la tranche : le gate de
`1014 ArmoriumCherub`, l'inversion de `1147 HadesAutocannons`, le code MORT de `1175 BloodChalice`,
le substrat REFUTE de la clause BOSS, et le volet `Untargetable` qui n'avait jamais eu de bras.

CE QUE CE FICHIER GARDE -- six choses, chacune adossee a une MESURE de la tranche :

 1. **LE FOYER DE COMPTE EST UNIQUE ET VALUE-PRESERVING.** `count_eligible_normal_attack_targets`
    est le corps ; `has_eligible_normal_attack_target` en derive (`> 0`). Le refactor ne devait
    RIEN changer a la forme booleenne, tri-etat compris (`None` -> `False`).
 2. **LE GATE DE `1014`, SUR SES DEUX BRANCHES.** `n >= 2` -> vrai sans rien lire d'autre ;
    `n < 2` -> `!CanKillTarget`, avec `MightBeKill` (cle `kill`) et NON `WillBeKill` (`killSure`).
 3. **`1147` LIT LES ENNEMIS.** Le slot d'interface est `GetAllEnemiesOf` (142) et non son VOISIN
    `GetAllFriendsOf` (141) ; le cran garde le SENS du predicat et la coherence avec le foyer
    `battle_query.all_enemies_of`, qui porte le meme natif sur l'autre substrat.
 4. **`1175` EST DU CODE MORT.** `BloodChalicePlaybook` override `EvaluateInternal`, donc son
    `ShouldExecute` n'est jamais atteint -- et la route BESPOKE du port ne consulte aucun gate.
 5. **LE SUBSTRAT DE `IsBoss` EST TRI-ETAT.** Mesure live : le trait `Boss` n'est PAS ce que
    `UnitExtensions$$IsBoss` lit (le natif se soigne lui-meme alors que le trait a bascule son
    attaque normale sur `1030`). Un `True` reintroduirait un refus infonde.
 6. **LE VOLET `Untargetable` MORD.** `#419-r1-tr10-r4` l'avait porte sans bras ; il en a un ici,
    OFFLINE : sur une scene ou l'unique voisin porte un effet du domaine `UNTARGETABLE_EFFECT_TYPES`,
    le compte d'adjacence PASSE DE 1 A 0. Le bras LIVE reste NON JOUE (il exige une unite en
    deep-strike adjacente au caster ET a la cible au meme pas) -- cf. la case-doc.

ASCII only (console cp1252). Probe jumeau (etapes 1..7, dont 5 LIVE) :
`scripts/python/probe_419r1tr14r5r2r1r1r1r3r1_gates.py`.
"""
from __future__ import annotations

import inspect

from engine import battle_query as bq
from engine.entities.active_ability_type import ActiveAbilityType
from engine.entities.traits.unit_trait import UnitTrait
from engine.playbook import adjacency as adj
from engine.playbook import get_playbook_or_default
from engine.playbook.bespoke import BESPOKE_SELFCAST, BloodChalicePlaybook
from engine.playbook.common import HEAL_PLAYBOOK, HealPlaybook
from engine.playbook.loki_custom import ArmoriumCherubPlaybook
from engine.playbook.noncomparable import _base as NCB
from engine.playbook.should_execute_gates import HadesAutocannonsPlaybook

#: Ce qui doit changer pour que cette garde puisse changer de verdict (#486-r15).
DECLENCHEUR = {
    "chemins": (
        # SOCLE COMMUN a tout fichier de test : la cascade des deux `conftest.py`.
        "scripts/python/conftest.py", "scripts/python/tests/conftest.py",
        # LE GATE DE 1014 et le foyer de COMPTE dont il derive.
        "scripts/python/engine/playbook/loki_custom.py",
        "scripts/python/engine/playbook/noncomparable/_base.py",
        # LE GATE DE 1147 (le sens du predicat) et le foyer qui porte le MEME natif.
        "scripts/python/engine/playbook/should_execute_gates.py",
        "scripts/python/engine/battle_query.py",
        # LA ROUTE BESPOKE de 1175 -- le cran de code MORT lit sa source.
        "scripts/python/engine/playbook/bespoke.py",
        # LA CLAUSE BOSS et son substrat TRI-ETAT.
        "scripts/python/engine/playbook/common.py",
        # LE VOLET `Untargetable` : le foyer d'adjacence et le domaine offline du flag.
        "scripts/python/engine/playbook/adjacency.py",
        "scripts/python/engine/entities/unit_selection_type.py",
        "scripts/python/engine/entities/effects/aura_selectors.py",
        # LA LECTURE d'un `DamagePredictionResult` : `kill` (MightBeKill) vs `killSure`.
        "scripts/python/engine/utilities/damage.py",
        # LES ENUMS dont ce fichier FIGE des ordinaux mesures.
        "scripts/python/engine/entities/active_ability_type.py",
        "scripts/python/engine/entities/traits/unit_trait.py",
        # LE REGISTRE : `get_playbook_or_default` et l'ordre d'enregistrement.
        "scripts/python/engine/playbook/__init__.py",
        "scripts/python/engine/playbook/base.py",
    ),
    "build": False,
    "toujours": False,
    "raison": (
        "CES chemins parce que chacun porte une assertion NOMMEE de ce fichier. `build: False` est "
        "LU au contenu : aucune assertion n'ouvre `data/symbols/**` ni le binaire -- les ordinaux "
        "(0x3f6, 0x47b, 0x497, 0x12, `UnitTrait.Summon` = 2) sont figes EN DUR ici EXPRES, et les "
        "deux mirrors d'enum sont declares pour cette raison. `toujours: False` : ce fichier ne "
        "garde ni le harnais ni la banque, il garde SIX foyers nommes. Les confrontations LIVE de "
        "la tranche vivent dans le probe jumeau, pas ici -- ce fichier reste jouable sans session."
    ),
}


# ------------------------------------------------------------- substrats synthetiques minimaux

class _Eff:
    """`EffectsState` reduit a ce que `adjacency.is_targetable` lui demande."""

    def __init__(self, by_uid=None):
        self._t = by_uid or {}

    def has_effect(self, uid, effect_type) -> bool:
        return int(effect_type) in self._t.get(int(uid), set())


class _Scene:
    def __init__(self, units, pos, team, eff=None, elev=None):
        self.units = units
        self._pos, self._team = pos, team
        self.eff_state = eff
        self.elev_by_pos = elev or {}

    def pos(self, uid):
        return self._pos.get(uid)

    def team(self, uid):
        return self._team.get(uid)


class _Ctx:
    def __init__(self, scene=None, uid=1, obs=(), epos=(), elev=None, origin=None):
        self.scene = scene
        self.uid = uid
        self.obs_units = list(obs)
        self.epos = list(epos)
        self.elev_by_pos = elev or {}
        self.origin = origin


# ================================================== cran 1 : le foyer de COMPTE, value-preserving

def test_le_predicat_derive_du_compte_et_rien_d_autre():
    """`has_eligible_normal_attack_target` DOIT etre `count(...) > 0` -- deux transcriptions du
    meme `GetValidTargets` se desynchroniseraient (c'est ce que la docstring du foyer promet)."""
    src = inspect.getsource(NCB.has_eligible_normal_attack_target)
    assert "count_eligible_normal_attack_targets(ctx, unit_id, tile, foes)" in src, src
    assert "hexgeo.distance" not in src, "le predicat a re-ecrit sa propre boucle : c'est un fork"


def test_le_compte_est_TRI_ETAT_et_le_predicat_rabat_None_sur_False():
    """Les deux gardes de tete de l'ancien predicat rendaient `False` ; le compte, lui, doit dire
    « PAS MESURE ». Le rabattage ne se fait QUE dans la forme booleenne -- sinon `ArmoriumCherub`
    lirait un `0` invente et basculerait sur sa branche restrictive."""
    ctx = _Ctx(obs=[{"squadId": 1, "visualId": "darkaTerminator"}])
    assert NCB.count_eligible_normal_attack_targets(ctx, 1, None, [(0, 0)]) is None
    assert NCB.has_eligible_normal_attack_target(ctx, 1, None, [(0, 0)]) is False
    # `visualId` introuvable -> portee non derivable -> PAS MESURE (jamais un zero)
    vide = _Ctx(obs=[])
    assert NCB.count_eligible_normal_attack_targets(vide, 1, (0, 0), [(1, 0)]) is None
    assert NCB.has_eligible_normal_attack_target(vide, 1, (0, 0), [(1, 0)]) is False


def test_le_compte_compte_vraiment_et_le_predicat_reste_coherent():
    """Meme entree, deux formes : `count > 0` et le booleen doivent coincider en TOUT point."""
    ctx = _Ctx(obs=[{"squadId": 1, "visualId": "darkaTerminator"}])   # arme MELEE (portee 1)
    for foes, attendu_non_nul in (([], False), ([(9, 9)], False), ([(1, 0)], True)):
        n = NCB.count_eligible_normal_attack_targets(ctx, 1, (0, 0), foes)
        assert n is not None
        assert (n > 0) is attendu_non_nul, (foes, n)
        assert NCB.has_eligible_normal_attack_target(ctx, 1, (0, 0), foes) is (n > 0)


# ============================================================ cran 2 : le gate de 1014, deux branches

class _PB1014(ArmoriumCherubPlaybook):
    """Le playbook REEL, avec ses deux entrees substituees -- on garde le CORPS du gate."""

    def __init__(self, n, can_kill):
        self._n, self._ck = n, can_kill

    def _can_kill_target(self, ctx, caster_tile, target, ability_id) -> bool:
        return self._ck


def _gate_1014(n, can_kill, monkeypatch) -> bool:
    pb = _PB1014(n, can_kill)
    monkeypatch.setattr(NCB, "count_eligible_normal_attack_targets",
                        lambda ctx, uid, tile, foes: n)
    return pb.should_execute(_Ctx(origin=(0, 0)), (0, 0), 7, 1014, 123.0)


def test_1014_deux_ou_plus_de_cibles_accepte_sans_rien_lire_d_autre(monkeypatch):
    """`if (n < 2) ... ; return true;` -- au-dessus du seuil le `CanKillTarget` n'est meme PAS
    evalue (court-circuit du corps natif)."""
    assert _gate_1014(2, True, monkeypatch) is True
    assert _gate_1014(5, True, monkeypatch) is True
    assert ArmoriumCherubPlaybook.MIN_NORMAL_ATTACK_TARGETS == 2


def test_1014_moins_de_deux_cibles_delegue_a_CanKillTarget(monkeypatch):
    """`return !CanKillTarget(...)` : le gate REFUSE quand l'ability peut tuer -- c'est un gate
    d'ECONOMIE DE SURTUAGE, l'inverse de la famille `!WillNormalAttackKill`."""
    assert _gate_1014(0, True, monkeypatch) is False
    assert _gate_1014(1, True, monkeypatch) is False
    assert _gate_1014(0, False, monkeypatch) is True
    assert _gate_1014(1, False, monkeypatch) is True


def test_1014_canal_muet_degrade_en_VRAI(monkeypatch):
    """Compte NON MESURABLE -> aucun refus invente (convention des cinq autres gates)."""
    assert _gate_1014(None, True, monkeypatch) is True


def test_1014_lit_MightBeKill_et_NON_WillBeKill():
    """`get_MightBeKill` = la cle `kill` du composite ; `get_WillBeKill` = `killSure`. Les deux
    different des qu'un block est possible, et prendre `killSure` rendrait le refus PLUS RARE que
    le natif -- degradation permissive silencieuse."""
    src = inspect.getsource(ArmoriumCherubPlaybook._can_kill_target)
    assert '.get("kill")' in src, src
    # La docstring NOMME `killSure` pour dire de ne pas le confondre : c'est la LECTURE qu'on garde,
    # donc l'assertion porte sur l'ACCES, pas sur la presence du mot.
    assert '.get("killSure")' not in src, src

    class _Ev:
        def __init__(self, fields):
            self._f = fields

        def composite_fields(self):
            return self._f

    class _PB(ArmoriumCherubPlaybook):
        def __init__(self, evs):
            self._evs = evs

        def make_damage_predictions(self, ctx, caster_tile, target, ability_id):
            return self._evs

    assert _PB([_Ev({"kill": True, "killSure": False})])._can_kill_target(None, None, 1, 1014)
    assert not _PB([_Ev({"kill": False, "killSure": False})])._can_kill_target(None, None, 1, 1014)
    assert not _PB([])._can_kill_target(None, None, 1, 1014)      # `foreach` vide -> false


def test_1014_est_au_registre_et_garde_son_custom():
    """Le gate vit dans `loki_custom` PARCE QUE le registre est indexe par `ability_id` : deux
    entrees pour 1014 se seraient ECRASEES."""
    pb = get_playbook_or_default(1014)
    assert isinstance(pb, ArmoriumCherubPlaybook)
    assert pb.ability_id == int(ActiveAbilityType.ArmoriumCherub) == 0x3f6
    assert pb.calculate_custom_utility(None, None, None, 1014) == 1.0


# ============================================================== cran 3 : 1147 lit les ENNEMIS

def _scene_1147(traits_by_uid, teams):
    units = [{"id": u, "alive": True, "team": t} for u, t in teams.items()]
    sc = _Scene(units, {u: (0, 0) for u in teams}, dict(teams))
    sc.traits = traits_by_uid
    return sc


def test_1147_le_gate_lit_GetAllEnemiesOf(monkeypatch):
    """Le slot 0x8e est `GetAllEnemiesOf` (142) ; `GetAllFriendsOf` est le VOISIN (141), et les
    deux corps natifs ne different que par le sens de la comparaison d'owner."""
    import engine.playbook.should_execute_gates as SEG
    pb = HadesAutocannonsPlaybook()
    assert pb.REQUIRED_ENEMY_TRAIT is UnitTrait.Summon and int(UnitTrait.Summon) == 2
    assert not hasattr(pb, "REQUIRED_ALLY_TRAIT"), "le nom ALLY reintroduirait la lecture fausse"
    monkeypatch.setattr(SEG, "_entity_traits",
                        lambda scene, uid: scene.traits.get(uid, frozenset()))
    sc = _scene_1147({1: frozenset(), 2: frozenset(), 3: frozenset()}, {1: 1, 2: 1, 3: 2})
    ctx = _Ctx(sc, 1)
    assert pb.should_execute(ctx, None, 9, 1147, 5.0) is False       # personne
    sc.traits[2] = frozenset({"Summon"})                             # un ALLIE
    assert pb.should_execute(ctx, None, 9, 1147, 5.0) is False
    sc.traits[3] = frozenset({"Summon"})                             # un ENNEMI
    assert pb.should_execute(ctx, None, 9, 1147, 5.0) is True


def test_1147_ne_filtre_NI_la_mort_NI_la_position(monkeypatch):
    """`GetAllEnemiesOf` enumere le POOL : aucun filtre de vie ni de position (meme lecture que
    `battle_query.all_enemies_of`, qui porte le meme natif sur l'autre substrat)."""
    import engine.playbook.should_execute_gates as SEG
    monkeypatch.setattr(SEG, "_entity_traits",
                        lambda scene, uid: scene.traits.get(uid, frozenset()))
    sc = _scene_1147({1: frozenset(), 3: frozenset({"Summon"})}, {1: 1, 3: 2})
    for u in sc.units:
        if u["id"] == 3:
            u["alive"] = False                                       # summon ennemi MORT
    assert HadesAutocannonsPlaybook().should_execute(_Ctx(sc, 1), None, 9, 1147, 5.0) is True


def test_le_foyer_all_enemies_of_porte_le_MEME_predicat():
    """L'autre substrat du meme natif : `ctrl` faux = ennemi. Un jour ou l'un des deux changerait
    de sens, ce cran le dirait."""
    units = [{"id": 1, "ctrl": True}, {"id": 2, "ctrl": False}, {"id": 3, "ctrl": False}]
    assert [u["id"] for u in bq.all_enemies_of(units)] == [2, 3]


# ==================================================== cran 4 : 1175 BloodChalice est du code MORT

def test_1175_la_route_bespoke_ne_consulte_AUCUN_gate():
    """`BloodChalicePlaybook` override `EvaluateInternal` cote natif, donc son `ShouldExecute`
    (slot +0x328) est inatteignable -- `CalculateActionUtility` n'est appelee QUE depuis
    `ComparablePlaybook<T>$$EvaluateInternal`. Cote port, la route bespoke est
    `generate_candidates` : elle ne doit consulter aucun `should_execute`, sinon le port porterait
    un gate que le natif ne joue pas."""
    pb = BESPOKE_SELFCAST[int(ActiveAbilityType.BloodChalice)]
    assert isinstance(pb, BloodChalicePlaybook)
    src = inspect.getsource(BloodChalicePlaybook.generate_candidates)
    assert "should_execute" not in src, src
    assert not hasattr(BloodChalicePlaybook, "should_execute"), \
        "un `should_execute` ici serait un port MORT du gate natif"


# ============================================= cran 5 : le substrat de `IsBoss` est TRI-ETAT

def test_is_boss_rend_None_PAS_MESURE():
    """Mesure live de la tranche : le natif se soigne LUI-MEME alors que le trait `Boss` greffe a
    bien bascule son attaque normale sur `1030` -- `UnitExtensions$$IsBoss` ne lit donc PAS ce
    trait. Un `True` ici prononcerait un refus que le natif ne prononce pas."""
    assert HealPlaybook._is_boss(None, 1) is None
    src = inspect.getsource(HealPlaybook._is_boss)
    assert "_entity_traits" not in src, "le trait `Boss` a ete REINTRODUIT comme substrat"


def test_la_clause_boss_se_degrade_en_VRAI_quand_le_substrat_se_tait():
    """`_is_boss` muet -> le self-heal reste ACCEPTE (le gate se reduit a `utility > 0`)."""
    sc = _Scene([{"id": 7, "alive": True, "team": 1}], {7: (0, 0)}, {7: 1})
    ctx = _Ctx(sc, 7)
    assert HEAL_PLAYBOOK.should_execute(ctx, None, 7, 18, 30.0) is True     # self
    assert HEAL_PLAYBOOK.should_execute(ctx, None, 8, 18, 30.0) is True     # tiers
    assert HEAL_PLAYBOOK.should_execute(ctx, None, 7, 18, 0.0) is False     # 1re clause STRICTE


def test_le_CORPS_de_la_clause_est_conserve(monkeypatch):
    """Le gate n'est pas SUPPRIME, il est prive de son substrat : quand `_is_boss` repond, la
    clause mord exactement comme le corps natif le dit."""
    sc = _Scene([{"id": 7, "alive": True, "team": 1}], {7: (0, 0)}, {7: 1})
    ctx = _Ctx(sc, 7)
    monkeypatch.setattr(HealPlaybook, "_is_boss", staticmethod(lambda scene, uid: True))
    assert HEAL_PLAYBOOK.should_execute(ctx, None, 7, 18, 30.0) is False    # boss : PAS de self
    assert HEAL_PLAYBOOK.should_execute(ctx, None, 8, 18, 30.0) is True     # boss : tiers OK


# ============================== cran 6 : le volet `Untargetable` MORD (le bras qui manquait)

def test_untargetable_retire_une_unite_du_compte_d_adjacence():
    """`#419-r1-tr10-r4` avait porte la seconde clause de `UnitSelectionType.OnlyAliveAndTargetable`
    sans jamais lui donner de bras. En voici un, OFFLINE : le MEME voisin, VIVANT et adjacent,
    compte 1 quand il est ciblable et **0** des qu'il porte un effet du domaine
    `UNTARGETABLE_EFFECT_TYPES` (le flag `0x11` est pose par `UntargetableEffect$$ApplyInternal`,
    donc il se lit par ses effets).

    Le bras LIVE reste NON JOUE : il exige une unite en deep-strike (`1035`/`1140`) adjacente au
    caster ET a la cible AU MEME PAS -- cf. la case-doc."""
    from engine.entities.effects.aura_selectors import UNTARGETABLE_EFFECT_TYPES
    assert UNTARGETABLE_EFFECT_TYPES, "domaine VIDE : ce cran ne mesurerait rien"
    et = int(sorted(int(x) for x in UNTARGETABLE_EFFECT_TYPES)[0])

    voisin = {"id": 2, "alive": True, "team": 2}
    sc = _Scene([{"id": 1, "alive": True, "team": 1}, voisin],
                {1: (0, 0), 2: (1, 0)}, {1: 1, 2: 2}, eff=_Eff({}))
    assert adj.is_targetable(sc, 2) is True
    assert adj.unit_matches(sc, voisin) is True

    sc.eff_state = _Eff({2: {et}})
    assert adj.is_targetable(sc, 2) is False
    assert adj.unit_matches(sc, voisin) is False, \
        "le volet `Untargetable` ne mord pas : le port compte une unite que le natif ecarte"

    # TRI-ETAT : sans etat d'effets, la clause se DEGRADE en vrai (jamais un refus invente).
    sc.eff_state = None
    assert adj.is_targetable(sc, 2) is None
    assert adj.unit_matches(sc, voisin) is True
