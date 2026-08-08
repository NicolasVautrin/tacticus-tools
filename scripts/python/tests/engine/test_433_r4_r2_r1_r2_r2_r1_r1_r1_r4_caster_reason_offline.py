"""OFFLINE #433-r4-r2-r1-r2-r2-r1-r1-r1-r4 -- la cascade CASTER : son ORDRE, son PREFIXE, son
tri-etat.

CE QUE CE FICHIER GARDE, et pourquoi il ne peut pas etre live. `IdunBattle.Core.Services.
TargetingQuery$$GetInvalidCasterReason` rend la PREMIERE regle rompue. Sur les 148 masques RE-lus,
AUCUNE ability n'arme deux de ces regles a la fois : l'ORDRE n'est donc observable dans AUCUN
montage live, et c'est pourtant la seule chose qu'un port de onze clauses puisse encore rater. On le
garde donc sur des masques CRAFTES -- l'ordre est une propriete du CODE, pas du catalogue.

Le PREFIXE, lui, est mesure live (`..._live.py`) : `BattleQuery$$IsTurnOfUnit`. Il est re-garde ici
en tri-etat, parce que la faute originelle etait de le porter comme TOUJOURS VRAI.

ASCII only. Detail : `docs/rl/case-433-r4-r2-r1-r2-portees.md`.
"""
from __future__ import annotations

import dataclasses

import pytest

from engine.runner.abilities import targeting as TGT
from engine.runner.abilities.targeting import TargetingOptions, targeting_options_for
from engine.runner.abilities.targeting_rule import TargetingRule as TR
from engine.services import ability_caster_gates as acg

#: Un id qui n'existe dans AUCUN registre -- le masque lui est donne par `_masque`.
FAUX_ID = 999999

#: `1045 GetEmRuntz`, le seul porteur du bit `CasterMatchesDynamicRule` dont la regle-delegue soit
#: derivable du substrat DECISION.
GETEMRUNTZ = 1045


@pytest.fixture
def masque(monkeypatch):
    """Pose un masque CRAFTE sur `FAUX_ID`.

    ⚠ LE SITE D'INJECTION SUIT LA FORME DE L'IMPORT, ET CELLE-CI A DEJA BASCULE DEUX FOIS. Le
    foyer `targeting_options_for` est UNIQUE, mais la facon dont `ability_caster_gates` l'atteint
    ne l'est pas -- et chaque bascule a casse ce fixture, dans un sens puis dans l'autre :

      * FORME C (import dans le CORPS de la fonction) -- le nom etait re-resolu a chaque appel,
        patcher `TGT` mordait ;
      * FORME A (`from ...targeting import targeting_options_for` au niveau module, `492c722f`
        « hisser 624 imports differes d'engine/ ») -- le nom est COPIE dans le namespace d'`acg`
        a l'import, patcher `TGT` ne mordait PLUS : les 21 tests de ce fichier ne mesuraient plus
        rien, `invalid_caster_reason` rendant `None` partout (#484) ;
      * FORME B (`import engine.runner.abilities.targeting as TGT` puis `TGT.targeting_options_for
        (...)`, PR #827) -- l'etat COURANT, et celui que le CLAUDE.md prescrit. Patcher `TGT` mord
        de nouveau, et `setattr(acg, "targeting_options_for", ...)` LEVE `AttributeError` : la
        liaison n'existe plus. C'est cela qui a rendu `master` ROUGE sur ces 21 tests.

    On patche donc `TGT.targeting_options_for` -- LE FOYER -- et on verifie que le masque atteint
    `acg` par une mesure de COMPORTEMENT, jamais par la forme de son import : `invalid_caster_reason`
    rend `None` quand le masque n'a PAS ete lu, un ENTIER quand il l'a ete
    (`test_un_masque_NON_RE_LU_rend_None_pas_zero` garde ce discriminant, sans ce fixture). La
    garde survit donc a la PROCHAINE bascule de forme, quel qu'en soit le sens -- ce qu'une garde
    ecrite sur un binding nomme ne pouvait pas faire.
    """
    orig = TGT.targeting_options_for

    def poser(rules):
        def _f(aid):
            if int(aid) == FAUX_ID:
                return TargetingOptions(rules=int(rules))
            return orig(aid)
        monkeypatch.setattr(TGT, "targeting_options_for", _f)
        # GARDE D'INERTIE, en COMPORTEMENT : sans masque lu, `invalid_caster_reason` rend `None`
        # (cf. `test_un_masque_NON_RE_LU_rend_None_pas_zero`). Un entier prouve donc que le masque
        # crafte a traverse jusqu'a `acg`. Sans elle, un deplacement de l'import rendrait ces
        # tests silencieusement vacueux -- c'est deja arrive.
        assert acg.invalid_caster_reason(FAUX_ID, None) is not None, (
            "le masque crafte n'atteint pas `ability_caster_gates` : le site d'injection est "
            "perime (cf. #484, puis la bascule en forme B de la PR #827)")
    return poser


def _sub(**kw):
    return acg.CasterSubstrate(**kw)


# ------------------------------------------------------------------------------------------------
# LE PREFIXE -- `BattleQuery$$IsTurnOfUnit`
# ------------------------------------------------------------------------------------------------

@pytest.mark.parametrize("tour,bouge,attendu", [
    (True,  True,  int(TR.CasterHasNotMoved)),   # les deux mesurees vraies -> REFUS
    (False, True,  0),                           # a bouge, mais ce n'est PAS son tour -> le natif
                                                 # saute la regle entiere (11 cas mesures live)
    (True,  False, 0),
    (None,  True,  0),                           # prefixe NON mesure -> permissif
    (True,  None,  0),                           # flag NON mesure   -> permissif
])
def test_casterhasnotmoved_exige_le_prefixe_ET_le_flag(masque, tour, bouge, attendu):
    """LE LIVRABLE DE LA CORRECTION. Le decompile garde la clause derriere
    `battleQuery.IsTurnOfUnit(caster) && (rules & CasterHasNotMoved)`. Porter le prefixe comme
    toujours vrai faisait refuser 11 paires sur 42 que le natif ACCEPTE -- un ecart RESTRICTIF,
    et le pire possible ici : le consommateur cote DECISION evalue la menace des unites ENNEMIES,
    donc exactement celles dont ce n'est pas le tour."""
    masque(TR.CasterHasNotMoved)
    got = acg.invalid_caster_reason(FAUX_ID, _sub(has_tile=True, is_turn_of_unit=tour,
                                                  has_moved=bouge))
    assert got == attendu


def test_le_prefixe_ne_desarme_QUE_cette_regle(masque):
    """ANTI-SUR-CORRECTION. `IsTurnOfUnit` prefixe la clause 1 et ELLE SEULE : une autre regle
    rompue doit continuer de mordre quand ce n'est pas le tour du caster."""
    masque(TR.CasterHasNotMoved | TR.CasterHas1Tiles)
    got = acg.invalid_caster_reason(FAUX_ID, _sub(has_tile=True, is_turn_of_unit=False,
                                                  has_moved=True, feet_count=3))
    assert got == int(TR.CasterHas1Tiles)


# ------------------------------------------------------------------------------------------------
# L'ORDRE -- la seule chose qu'un port de onze clauses puisse encore rater
# ------------------------------------------------------------------------------------------------

#: (masque, substrat, regle attendue). Chaque ligne rompt DEUX regles a la fois et exige celle qui
#: vient EN PREMIER dans `TargetingQuery$$GetInvalidCasterReason`.
ORDRE = [
    (TR.CasterHasNotMoved | TR.CasterMatchesDynamicRule,
     dict(has_tile=True, is_turn_of_unit=True, has_moved=True), TR.CasterHasNotMoved),
    (TR.CasterHasNotMoved | TR.CasterIsMachine,
     dict(has_tile=True, is_turn_of_unit=True, has_moved=True, is_machine=False),
     TR.CasterHasNotMoved),
    (TR.CasterHasNoTile | TR.CasterHas1Tiles,
     dict(has_tile=True, feet_count=3), TR.CasterHasNoTile),
    (TR.CasterHas1Tiles | TR.CasterIsMachine,
     dict(has_tile=True, feet_count=3, is_machine=False), TR.CasterHas1Tiles),
    (TR.CasterHas3Tiles | TR.CasterHas7Tiles,
     dict(has_tile=True, feet_count=1), TR.CasterHas3Tiles),
    (TR.CasterHas7Tiles | TR.CasterIsMachine,
     dict(has_tile=True, feet_count=1, is_machine=False), TR.CasterHas7Tiles),
]


@pytest.mark.parametrize("rules,sub,attendu", ORDRE,
                         ids=[str(TR(int(r)).name if int(r).bit_count() == 1 else hex(int(r)))
                              for r, _s, _a in ORDRE])
def test_la_premiere_regle_rompue_gagne(masque, rules, sub, attendu):
    """`GetInvalidCasterReason` RETOURNE a la premiere regle qui mord : l'ordre est SEMANTIQUE.
    Un port qui poserait les memes onze clauses dans un autre ordre serait juste sur chaque cas
    ISOLE et faux des que deux conditions coexistent -- exactement le mode de panne qu'une relecture
    a l'oeil ne voit pas."""
    masque(rules)
    assert acg.invalid_caster_reason(FAUX_ID, _sub(**sub)) == int(attendu)


def test_la_clause_tuile_nulle_rend_AllowNullCasterTile_pas_une_regle_homonyme(masque):
    """Le litteral rendu par le natif est `0x40000000` = `AllowNullCasterTile`, c'est-a-dire la
    PERMISSION dont l'ABSENCE declenche le refus. Le lire comme « une regle CasterHasNoTile » serait
    une transcription fausse d'un bit juste."""
    masque(TR.CasterIsMachine)          # une regle quelconque, SANS aucune des deux permissions
    assert acg.invalid_caster_reason(FAUX_ID, _sub(has_tile=False)) == int(TR.AllowNullCasterTile)
    masque(TR.AllowNullCasterTile)      # la permission est posee -> plus de refus
    assert acg.invalid_caster_reason(FAUX_ID, _sub(has_tile=False)) == 0
    masque(TR.CasterHasNoTile)          # bit 55 pose ET tuile PRESENTE -> refus sur bit 55
    assert acg.invalid_caster_reason(FAUX_ID, _sub(has_tile=True)) == int(TR.CasterHasNoTile)


# ------------------------------------------------------------------------------------------------
# LE TRI-ETAT -- « non mesure » n'est jamais « faux »
# ------------------------------------------------------------------------------------------------

@pytest.mark.parametrize("rules,champ", [
    (TR.CasterHasNotMoved, "has_moved"),
    (TR.CasterHas1Tiles, "feet_count"),
    (TR.CasterHas3Tiles, "feet_count"),
    (TR.CasterHas7Tiles, "feet_count"),
    (TR.CasterIsMachine, "is_machine"),
    (TR.CasterHasNoTile, "has_tile"),
])
def test_un_champ_non_mesure_ne_refuse_JAMAIS(masque, rules, champ):
    """La convention du module : `None` = pas mesure -> aucune regle qui le lit ne peut refuser.
    Un port qui rabattrait `None` sur `False` inventerait un refus, et la degradation serait
    RESTRICTIVE -- invisible en self-play et exploitable a l'entrainement."""
    masque(rules)
    sub = _sub(has_tile=None if champ == "has_tile" else True)
    assert getattr(sub, champ) is None
    assert acg.invalid_caster_reason(FAUX_ID, sub) == 0


def test_un_substrat_absent_est_le_statu_quo(masque):
    """`caster=None` = le comportement d'AVANT cette tranche : aucune des onze regles ne mord."""
    masque(TR.CasterHasNotMoved | TR.CasterHasNoTile | TR.CasterIsMachine | TR.CasterHas1Tiles)
    assert acg.invalid_caster_reason(FAUX_ID, None) == 0


def test_un_masque_NON_RE_LU_rend_None_pas_zero():
    """`None` (masque jamais lu) et `0` (cascade parcourue, caster valide) sont deux reponses
    DIFFERENTES : la premiere dit « je ne sais pas », la seconde « j'ai regarde »."""
    assert targeting_options_for(FAUX_ID) is None
    assert acg.invalid_caster_reason(FAUX_ID, _sub(has_tile=True)) is None
    assert acg.caster_gate_reason(FAUX_ID, None, _sub(has_tile=True)) is None


# ------------------------------------------------------------------------------------------------
# LA COMPOSITION DES QUATRE GATES -- l'ordre y est semantique AUSSI
# ------------------------------------------------------------------------------------------------

def _st(usable=True, disabled=False, cooldown=None, ammo=None, has_ammo=True):
    return {"usable": usable, "disabled": disabled, "cooldown": cooldown,
            "ammoCost": ammo, "hasAmmo": has_ammo}


def test_la_composition_rend_le_PREMIER_des_quatre_gates(masque):
    """`AttackQuery$$GetAllTilesInAbilityRange` evalue slot 0x14, puis slot 0x13, puis
    `GetInvalidCasterReason` (dont la marche d est `CanCurrentlyBeUsed`). Quand plusieurs mordent,
    c'est le PREMIER qui est rapporte."""
    masque(TR.CasterHasNotMoved)
    sub = _sub(has_tile=True, is_turn_of_unit=True, has_moved=True)
    # les deux derniers gates mordent ensemble -> c'est le 3e (marche d) qui sort
    assert acg.caster_gate_reason(FAUX_ID, _st(cooldown=2), sub) \
        == acg.REASON_CAN_CURRENTLY_BE_USED
    # le 1er mord aussi -> il gagne
    assert acg.caster_gate_reason(FAUX_ID, _st(usable=False, cooldown=2), sub) \
        == acg.REASON_CAN_STILL_BE_USED
    # seul le 4e mord -> il est rendu par le NOM NATIF de la regle, pas par une etiquette de gate
    assert acg.caster_gate_reason(FAUX_ID, _st(), sub) == "CasterHasNotMoved"
    assert acg.gates_allow(FAUX_ID, _st(), sub) is False
    assert acg.gates_allow(FAUX_ID, _st(), _sub(has_tile=True)) is True


# ------------------------------------------------------------------------------------------------
# LA REGLE-DELEGUE -- table de regime et selecteur de spawn
# ------------------------------------------------------------------------------------------------

def test_la_table_de_regime_couvre_EXACTEMENT_les_porteurs_du_bit():
    """La table ne doit contenir QUE les abilities qui posent `CasterMatchesDynamicRule` : pour les
    autres le natif n'invoque jamais le delegue, et une entree serait du bruit. Inversement, un
    porteur ABSENT de la table serait silencieusement traite comme « pas de regle »."""
    from engine.runner.abilities.handler import ABILITY_CLASSES
    from engine.runner.abilities.targeting import TARGETING_OPTIONS_UNPORTED
    ids = {int(a) for a in ABILITY_CLASSES
           if getattr(ABILITY_CLASSES[a], "TARGETING_OPTIONS", None) is not None}
    ids |= {int(a) for a in TARGETING_OPTIONS_UNPORTED}
    porteurs = sorted(a for a in ids
                      if int(getattr(targeting_options_for(a), "rules", 0) or 0)
                      & int(TR.CasterMatchesDynamicRule))
    assert sorted(acg.DYNAMIC_CASTER_GATE_BY_ABILITY) == porteurs
    assert acg.dynamic_caster_gate_of(GETEMRUNTZ) == acg.CASTER_GATE_SPAWN_TILE


def test_1045_le_masque_effectif_est_bien_0x8004():
    """Le ctor de `GetEmRuntzAbility` n'appelle AUCUN `TargetingOptions$$.ctor` : il recopie un
    PRESET STATIQUE. Ce test garde le masque EFFECTIF (celui de `<preset>+0x28`), pas un litteral
    visible -- et il garde surtout que la seule regle CASTER armee est la delegue."""
    o = targeting_options_for(GETEMRUNTZ)
    assert int(o.rules) == 0x8004
    assert int(o.rules) & int(TR.CasterMatchesDynamicRule)
    assert not (int(o.rules) & int(TR.CasterHasNotMoved))


#: Plateau SYNTHETIQUE 6x6 plat : le selecteur de spawn n'a besoin que de l'adjacence et des cartes.
_PLAT = {(c, r): 0 for c in range(6) for r in range(6)}
_WALK = {p: True for p in _PLAT}


@pytest.mark.parametrize("ennemi,attendu", [
    ((2, 0), 0),                       # ennemi a d=2 : (1,0) est libre, adjacent aux deux -> PASSE
    ((5, 5), int(TR.TargetMatchesDynamicRule)),   # aucun ennemi a portee -> le delegue rend 2
])
def test_le_selecteur_de_spawn_decide_le_delegue(ennemi, attendu):
    """`GetEmRuntzAbility$$GetSpawnTileSelector` =
    `CanAddUnit(AdjacentTiles(Caster())) & Unique(AdjacentTiles(UnitsWithoutTrait(Enemies, 0x1b)))`.
    Le litteral rendu quand la liste est VIDE est **2**, que l'enum genere nomme
    `TargetMatchesDynamicRule` : le natif reutilise ce code pour le volet CASTER."""
    sub = acg.CasterSubstrate(pos=(0, 0), has_tile=True, team=1,
                              team_by_pos={(0, 0): 1, ennemi: 2},
                              walkable_by_pos=_WALK, elev_by_pos=_PLAT)
    assert acg.invalid_caster_reason(GETEMRUNTZ, sub) == attendu


@pytest.mark.parametrize("manquant", ["pos", "team", "team_by_pos", "walkable_by_pos"])
def test_le_selecteur_rend_None_quand_son_substrat_manque(manquant):
    """Inventer « aucune tuile de spawn » RETIRERAIT une zone : c'est l'ecart RESTRICTIF que tout ce
    module refuse. Substrat incomplet -> `dynamic_caster_reason` rend `None`, donc aucun refus."""
    champs = dict(pos=(0, 0), has_tile=True, team=1,
                  team_by_pos={(0, 0): 1, (5, 5): 2},
                  walkable_by_pos=_WALK, elev_by_pos=_PLAT)
    champs[manquant] = None
    sub = acg.CasterSubstrate(**champs)
    assert acg.dynamic_caster_reason(GETEMRUNTZ, sub) is None
    assert acg.invalid_caster_reason(GETEMRUNTZ, sub) == 0


def test_le_substrat_est_immuable_et_par_defaut_entierement_non_mesure():
    """`CasterSubstrate()` vide = le statu quo d'avant la tranche, et il est FROZEN : personne ne
    peut le muter en cours de sweep (le verdict du gate est CONSTANT sur tout le balayage)."""
    sub = acg.CasterSubstrate()
    assert all(getattr(sub, f.name) is None for f in dataclasses.fields(sub))
    with pytest.raises(dataclasses.FrozenInstanceError):
        sub.has_moved = True                                          # type: ignore[misc]
