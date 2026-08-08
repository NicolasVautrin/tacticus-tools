"""CLIQUET #487-r1 -- face DECISION de `1088 HellfyreMissileRack` : les DEUX corrections de fiche.

`IdunBattle.AI.Playbook.Loki.HellfyreMissileRackPlaybook$$EvaluateNonComparable` pose une utilite
CONSTANTE = le nombre d'ennemis ayant encaisse du `DamageProfileType.Psychic` ce tour, identique
pour toutes les cibles rendues par `IdunBattle.AI.Playbook.BasePlaybook$$GetEligibleTargetsSelectable`.

Ce fichier garde les DEUX lectures que la fiche `case-487` §7 portait FAUSSES, parce qu'aucune des
deux n'est visible d'un test de valeur :

  1. **`MIN_UTILITY = 1`, pas `null`.** Le `.cctor` ecrit `Fix64(1)` dans le premier champ statique
     de la classe et la leaf relit CE champ pour le `Nullable<Fix64>` du `Bucket`. Le gate MORD :
     tant qu'aucun ennemi n'a pris de Psychic, le bucket reste VIDE. Un `MIN_UTILITY = 0` aurait
     rendu le playbook inoffensif -- et VERT sur tout test qui ne regarde que l'utilite.
  2. **La hierarchie est `NonComparablePlaybook`1`**, LUE dans
     `data/symbols/<build>/frida/classes.tsv`, alors que le decompile du `.ctor` NOMME
     `ComparablePlaybooku003C...u003E$$.ctor` (corps gshared FONDU, un seul proprietaire nomme).
     Elle decide de la ROUTE : `IdunBattle.AI.Tactics.ABaseAiActorTactic$$InitAbilityTypeLists`
     range les NonComparable dans `dict[get_Priority]`, evalues AVANT le fallback Comparable.

S'y ajoute le TRI-ETAT du canal : `receivedDamageThisTurn` (`ActorStatisticsComponent + 0x80`)
n'est publie par AUCUN hook -- `Scene.has_taken_damage_of_profile_this_turn` rend `None` = NON
MESURE, et le playbook rend alors AUCUN candidat au lieu de compter `0`. Les deux sorties se
ressemblent (liste vide) et n'ont PAS la meme cause : l'etage 5 les separe explicitement.

Ce que le cliquet mord (mutations verifiees ROUGE avant vert) :
  * `MIN_UTILITY = 0.0`                              -> test_gate_min_utility
  * compter les ALLIES armes                         -> test_utilite_compte_les_ennemis_seuls
  * rabattre le canal muet sur `0`/`False`           -> test_canal_muet_nest_pas_zero
  * `TESTED_PROFILE = HeavyRound` (le profil INFLIGE) -> test_profil_teste_est_psychic
  * loger le playbook hors du registre NonComparable  -> test_inscrit_au_registre_noncomparable

100 % OFFLINE : aucun runner, aucun RPC, aucune session Frida. ASCII only (cp1252).
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

PYDIR = Path(__file__).resolve().parents[2]          # scripts/python
ROOT = Path(__file__).resolve().parents[4]           # racine du checkout
if str(PYDIR) not in sys.path:
    sys.path.insert(0, str(PYDIR))

from engine.playbook import noncomparable as NC                      # noqa: E402
from engine.playbook.scene import Scene                              # noqa: E402
from engine.entities.active_ability_type import ActiveAbilityType    # noqa: E402
from engine.entities.damage_profile_type import DamageProfileType    # noqa: E402

#: DECLENCHEUR -- ce qui doit changer pour que ce fichier puisse changer de verdict.
#: `engine/**` en glob parce que l'import de `engine.playbook.noncomparable` traine tout le
#: registre (une liste de modules nommes serait un faux vert des la prochaine feuille ajoutee) ;
#: `classes.tsv` parce que l'etage 2 confronte la HIERARCHIE au dump du build -- c'est la seule
#: source qui distingue `NonComparablePlaybook`1` de `ComparablePlaybook`1`, et un changement de
#: binaire peut la faire bouger.
DECLENCHEUR = {
    "chemins": (
        "scripts/python/engine/**/*.py",
        "scripts/python/tests/conftest.py",
        "scripts/python/tests/engine/conftest.py",
        "data/symbols/*/frida/classes.tsv",
    ),
    "build": True,
    "toujours": False,
    "raison": "`build: True` parce que l'etage 2 lit la table de classes du build pour etablir la "
              "hierarchie du playbook (c'est CE fait qui decide de la route). Les autres etages "
              "sont purement offline : ils construisent une `Scene` et un `NCContext` a la main, "
              "sans runner ni RPC.",
}

ABILITY = int(ActiveAbilityType.HellfyreMissileRack)     # 0x440 = 1088
PSYCHIC = int(DamageProfileType.Psychic)                 # 0xd = 13


# ------------------------------------------------------------------------------------------------
# Substrat minimal : une `Scene` et un `NCContext` construits a la main (aucun runner).
# ------------------------------------------------------------------------------------------------
def _scene(received: dict | None) -> Scene:
    """`Scene` reduite au seul canal que ce playbook lit. `received=None` = canal MUET."""
    return Scene(ctx_by_id={}, armor_by_id={}, shield_by_id={}, mult_by_id={}, ablvl_by_id={},
                 vis_by_id={}, units=[], hp_by_id={}, pos_by_id={}, team_by_id={}, eff_state=None,
                 received_damage_profiles_by_id=received)


def _ctx(units: list, received: dict | None, targets: list, uid: int = 1) -> NC.NCContext:
    """`NCContext` minimal. `targets` = les cibles que `abilityTargets` rend en `fromHere`."""
    def _ability_targets(u, aid):
        if u != uid or aid != ABILITY:
            return {"units": []}
        return {"units": [{"unitId": uid, "abilities": [{
            "abilityId": ABILITY,
            "fromHere": [{"kind": "unit", "targetId": t} for t in targets],
            "targets": [{"kind": "unit", "targetId": t} for t in targets]}]}]}

    return NC.NCContext(uid=uid, origin=(0, 0), reach_nc=[(0, 0)], epos=[], fpos=[], plan={},
                        hp_cur_by_id={}, ability_targets=_ability_targets, units=units,
                        scene=_scene(received))


def _units(*rows) -> list:
    """`decisionView.units` reduites : `(id, ctrl)` -- `ctrl` vrai = camp de l'unite qui decide."""
    return [{"id": i, "ctrl": c} for (i, c) in rows]


# ------------------------------------------------------------------------------------------------
# ETAGE 1 -- le mirror est INSCRIT, et ses ordinaux sont FIGES A LA VALEUR MESUREE.
# ------------------------------------------------------------------------------------------------
def test_inscrit_au_registre_noncomparable():
    """Le playbook est dans le registre NonComparable -- la route que sa hierarchie impose."""
    pb = NC.PLAYBOOKS.get(ABILITY)
    assert pb is not None, "1088 absent de `noncomparable.PLAYBOOKS` : face DECISION non routee"
    assert type(pb).__name__ == "HellfyreMissileRackPlaybook"
    assert isinstance(pb, NC.NonComparablePlaybook)
    # `get_Priority` : 1088 est ABSENTE de `NATIVE_PRIORITY` (sweep exhaustif #170) -> tier 0.
    assert ABILITY not in NC.NATIVE_PRIORITY
    assert pb.PRIORITY == 0


def test_gate_min_utility_est_un():
    """`.cctor` = `Fix64(1)` -> le gate `Bucket.AddAction` est `>= 1`, pas `>= 0`."""
    assert NC.PLAYBOOKS[ABILITY].MIN_UTILITY == 1.0


def test_profil_teste_est_psychic():
    """`0xd` = `DamageProfileType.Psychic` (profil TESTE), PAS `HeavyRound` (profil INFLIGE).

    Les deux vivent dans le meme arbre d'ability et le meme litteral `0xd` y designe encore un
    TROISIEME enum (`UnitTrait.Object`) -- cf. `case-487` §4. L'ordinal nu ne leve aucune erreur."""
    pb = NC.PLAYBOOKS[ABILITY]
    assert pb.TESTED_PROFILE == PSYCHIC == 13
    assert pb.TESTED_PROFILE != int(DamageProfileType.HeavyRound)


# ------------------------------------------------------------------------------------------------
# ETAGE 2 -- la HIERARCHIE, lue dans le dump du build (c'est elle qui decide de la route).
# ------------------------------------------------------------------------------------------------
def _classes_tsv() -> Path | None:
    cands = sorted((ROOT / "data" / "symbols").glob("*/frida/classes.tsv"))
    return cands[-1] if cands else None


def test_hierarchie_est_noncomparable_dans_le_dump():
    """`HellfyreMissileRackPlaybook` derive de `NonComparablePlaybook`1` -- LU, pas deduit.

    Le decompile du `.ctor` nomme `ComparablePlaybook..ctor` : corps gshared FONDU. La table de
    classes est la source qui tranche, et le test porte son TEMOIN DE CONTROLE (`ChronometronPlaybook`,
    qui est bien un `ComparablePlaybook`1` et n'a, elle, AUCUN `EvaluateNonComparable`) : sans lui,
    un fichier ou toutes les lignes diraient `NonComparablePlaybook` passerait pour vert."""
    tsv = _classes_tsv()
    if tsv is None:
        pytest.skip("data/symbols/*/frida/classes.tsv absent de ce checkout")
    parents = {}
    for line in tsv.read_text(encoding="utf-8", errors="replace").splitlines():
        if line.startswith("#!") or "\t" not in line:
            continue
        cols = line.split("\t")
        parents[cols[0]] = cols[2] if len(cols) > 2 else ""
    mine = parents.get("IdunBattle.AI.Playbook.Loki.HellfyreMissileRackPlaybook")
    ctrl = parents.get("IdunBattle.AI.Playbook.Loki.ChronometronPlaybook")
    assert mine is not None and ctrl is not None, "classes introuvables dans le dump du build"
    assert mine.endswith("NonComparablePlaybook`1"), mine
    # TEMOIN NON NUL : la table sait dire `ComparablePlaybook` quand c'est le cas.
    assert ctrl.endswith("ComparablePlaybook`1"), ctrl


# ------------------------------------------------------------------------------------------------
# ETAGE 3 -- l'UTILITE : `Sum(Select(GetAllEnemiesOf(owner), ... ? 1 : 0))`.
# ------------------------------------------------------------------------------------------------
def test_utilite_compte_les_ennemis_seuls():
    """`GetAllEnemiesOf(ownerId)` = les unites dont le proprietaire n'est PAS celui du caster.

    Un ALLIE arme au Psychic (le cas NOMINAL : c'est un Doombolt ami qui arme) ne doit RIEN
    ajouter -- sinon le caster s'auto-alimente et l'ability sort toujours."""
    pb = NC.PLAYBOOKS[ABILITY]
    units = _units((1, True), (2, True), (10, False), (11, False), (12, False))
    # allie 2 arme + ennemi 10 arme -> l'utilite doit valoir 1, pas 2.
    ctx = _ctx(units, {1: set(), 2: {PSYCHIC}, 10: {PSYCHIC}, 11: set(), 12: set()}, [10])
    assert pb._utility(ctx) == 1.0
    ctx2 = _ctx(units, {1: set(), 2: set(), 10: {PSYCHIC}, 11: {PSYCHIC}, 12: set()}, [10])
    assert pb._utility(ctx2) == 2.0


def test_utilite_ne_confond_pas_les_profils():
    """Un ennemi qui a pris du `HeavyRound` (le profil que l'ability INFLIGE) ne compte pas."""
    pb = NC.PLAYBOOKS[ABILITY]
    units = _units((1, True), (10, False))
    hr = int(DamageProfileType.HeavyRound)
    assert pb._utility(_ctx(units, {1: set(), 10: {hr}}, [10])) == 0.0
    assert pb._utility(_ctx(units, {1: set(), 10: {hr, PSYCHIC}}, [10])) == 1.0


# ------------------------------------------------------------------------------------------------
# ETAGE 4 -- le GATE : c'est lui que la fiche `Bucket(0, null)` aurait desarme.
# ------------------------------------------------------------------------------------------------
def test_gate_min_utility():
    """0 ennemi arme -> AUCUN candidat ; 1 ennemi arme -> un candidat, utilite 1, cast en place.

    Le bras positif est ce qui interdit de faire passer le test en rendant toujours `[]`."""
    pb = NC.PLAYBOOKS[ABILITY]
    units = _units((1, True), (10, False), (11, False))
    vide = pb.generate_candidates(_ctx(units, {1: set(), 10: set(), 11: set()}, [10, 11]))
    assert vide == [], vide
    plein = pb.generate_candidates(_ctx(units, {1: set(), 10: {PSYCHIC}, 11: set()}, [10, 11]))
    assert len(plein) == 1, plein
    assert plein[0]["ability"] == ABILITY
    assert plein[0]["pred"] == 1.0
    # Utilite PLATE + sweep origine-first + remplacement STRICT `>` -> 1re cible `fromHere`,
    # cast EN PLACE (`to is None`).
    assert plein[0]["target"] == 10
    assert plein[0]["to"] is None


def test_utilite_plate_ne_depend_pas_de_la_cible():
    """La MEME valeur est passee a chaque `GenerateAction` : l'ordre des cibles ne la change pas."""
    pb = NC.PLAYBOOKS[ABILITY]
    units = _units((1, True), (10, False), (11, False))
    recu = {1: set(), 10: {PSYCHIC}, 11: {PSYCHIC}}
    a = pb.generate_candidates(_ctx(units, recu, [10, 11]))
    b = pb.generate_candidates(_ctx(units, recu, [11, 10]))
    assert a[0]["pred"] == b[0]["pred"] == 2.0
    assert (a[0]["target"], b[0]["target"]) == (10, 11)   # seule la 1re cible enumeree change


# ------------------------------------------------------------------------------------------------
# ETAGE 5 -- TRI-ETAT : « canal muet » et « personne n'a pris de Psychic » rendent la MEME liste
# vide et n'ont PAS la meme cause. C'est le seul etage qui les separe.
# ------------------------------------------------------------------------------------------------
def test_canal_muet_nest_pas_zero():
    """`received_damage_profiles_by_id is None` (regime LIVE) -> `None`, jamais `0`/`False`."""
    sc_muet = _scene(None)
    sc_mesure = _scene({10: set()})
    assert sc_muet.has_taken_damage_of_profile_this_turn(10, PSYCHIC) is None
    assert sc_mesure.has_taken_damage_of_profile_this_turn(10, PSYCHIC) is False
    assert sc_mesure.has_taken_damage_of_profile_this_turn(10, PSYCHIC) is not None
    # Une unite ABSENTE de la table mesuree reste non mesuree, elle aussi.
    assert sc_mesure.has_taken_damage_of_profile_this_turn(99, PSYCHIC) is None
    pb = NC.PLAYBOOKS[ABILITY]
    units = _units((1, True), (10, False))
    assert pb._utility(_ctx(units, None, [10])) is None            # muet -> `None`
    assert pb._utility(_ctx(units, {1: set(), 10: set()}, [10])) == 0.0   # mesure -> `0.0`
    assert pb.generate_candidates(_ctx(units, None, [10])) == []


def test_scene_from_state_transporte_le_canal(tmp_path):
    """`Scene.from_state` renseigne le canal : le rejeu OFFLINE est le regime confrontable.

    On n'y monte PAS de runner -- on verifie que le transport lit bien
    `UnitComponent.received_damage_this_turn`, avec un `state` reduit a un seul faux composant."""
    from engine.runner.components import UnitComponent

    class _E:
        def __init__(self, uc):
            self._uc = uc

        def get_component(self, cls):
            return self._uc if cls is UnitComponent else None

    class _S:
        board = None
        effects = None
        current_player_id = None

        def __init__(self, ents):
            self.entities = ents

        def get_entity(self, eid):
            return self.entities.get(eid)

    uc = UnitComponent(visual_id="x", alive=True)
    uc.received_damage_this_turn = {PSYCHIC: 2}
    sc = Scene.from_state(_S({7: _E(uc)}))
    assert sc.received_damage_profiles_by_id is not None
    assert sc.has_taken_damage_of_profile_this_turn(7, PSYCHIC) is True
    assert sc.has_taken_damage_of_profile_this_turn(7, int(DamageProfileType.HeavyRound)) is False
