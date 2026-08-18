"""#1027-r4 -- CLIQUETS OFFLINE du repositionnement du caster sur la voie TILE-TARGET.

LE FAIT NATIF, relu sur `t6dpr4k06g`. `IdunBattle.AI.Playbook.BasePlaybook$$GetEligibleTargetsSelectable(caster,
possibleCasterPosition)` memset son `AbilityEntities` (0x128 octets) puis ecrit, entre autres :

    ae@+0x08 = caster                                             // Caster (l'ENTITE)
    ae@+0x40 = UnitPosition.get_MainTile(possibleCasterPosition)  // CasterTile
    ae@+0x48 = possibleCasterPosition                             // CasterPosition

et `IdunBattle.Entities.Selectors.CasterTileSelector$$Select` -- corps des DEUX slots
`<DSLSelectors+0x50> = CasterTile` et `<DSLSelectors+0x58> = CasterTiles` -- lit dans CET ordre :

    tiles = entities.CasterPosition.Tiles   (+0x48)
         ?? entities.CasterTile.ToList()    (+0x40)
         ?? EntityExtensions.GetTiles(entities.Caster, state)   (+0x08)

Donc, sur cette voie, `CasterTiles` designe l'empreinte A LA POSITION CANDIDATE. Le port evaluait
la bande de `SolarAtomizerAbility$$GetTargetTiles` -- dont la DIRECTION vient de
`DirectionTo(AdjacentTiles(Target) & Tiles(CasterTiles), Target)` -- depuis l'empreinte COURANTE,
pour TOUTES les positions balayees.

⚠ ET L'AUTRE VOIE FAIT L'INVERSE, ce qui est precisement pourquoi le parametre est OPTIONNEL :
`IdunBattle.AI.Playbook.PlagueburstMortarPlaybook$$CalculateCustomUtility(this, caster,
casterPosition, target, abilityState, possibleTargets)` construit son `AbilityEntities` par
`AbilityEntities$$.ctor(&ae, caster, caster, target, 0, 0, ...)` et **ne passe pas** son parametre
`casterPosition` -- `CasterTiles` y retombe donc sur `GetTiles(Caster)`. Recopier l'une sur l'autre
serait faux dans les deux sens.

ASCII only.
"""
from __future__ import annotations

import ast
import inspect
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from engine.entities.selectors.accessors import CasterTile     # noqa: E402
from engine.playbook import tile_targets as TT                 # noqa: E402
from engine.playbook.noncomparable import solar_atomizer as SA  # noqa: E402

#: #486-r15 -- ce qui doit changer pour que ce fichier puisse changer de verdict.
DECLENCHEUR = {
    "chemins": (
        "scripts/python/engine/playbook/tile_targets.py",
        "scripts/python/engine/playbook/noncomparable/solar_atomizer.py",
        "scripts/python/engine/entities/selectors/accessors.py",
    ),
    "build": False,
    "toujours": False,
    "raison": ("le fait garde est LOCAL : le parametre `caster_position` du socle tile-target, sa "
               "transmission par le seul appelant qui mirrore `GetEligibleTargetsSelectable`, et "
               "la cascade de `CasterTile.select`. Les trois foyers sont cites ; rien d'autre ne "
               "peut changer ce verdict sans passer par eux."),
}


class _SceneStub:
    """Le minimum que `dsl_context_for_tile_target` lit -- on ne monte pas une bataille pour
    verifier qu'un parametre traverse."""
    board = object()
    elev_by_pos = {}
    tile_effects_by_pos = None          # carte d'effets NON MESUREE -> `HasEffect` rend False

    def __init__(self, units):
        self.units = units

    def ctx(self, _uid):
        return None

    def turns_started(self, _uid):
        return None


class _CtxStub:
    def __init__(self, uid, scene):
        self.uid, self.scene = uid, scene


def _dctx(caster_position=None):
    sc = _SceneStub([{"id": 7, "visualId": "x", "pos": {"col": 1, "row": 1},
                      "feet": [{"col": 1, "row": 1}, {"col": 2, "row": 1}]}])
    return TT.dsl_context_for_tile_target(_CtxStub(7, sc), caster_position=caster_position)


def test_le_socle_transmet_la_position_candidate_au_contexte():
    """`caster_position` -> `DslContext.caster_pos`, c'est-a-dire le slot que
    `CasterTileSelector$$Select` consulte EN PREMIER."""
    assert _dctx().caster_pos is None
    assert _dctx((4, 9)).caster_pos == (4, 9)


def test_la_cascade_de_CasterTile_prend_la_position_candidate():
    """Le fait NATIF, joue de bout en bout : posee, la position candidate GAGNE sur l'empreinte
    courante ; absente, on retombe sur `GetTiles(Caster)` -- et cette 3e branche rend l'empreinte
    MESUREE (`decisionView.units[].feet`), pas la seule main tile."""
    sans = CasterTile().select(_dctx())
    avec = CasterTile().select(_dctx((4, 9)))
    assert sans == [(1, 1), (2, 1)], "3e branche : l'empreinte COURANTE, entiere -- got %r" % (sans,)
    assert avec == [(4, 9)], "1re branche : la position CANDIDATE -- got %r" % (avec,)
    assert sans != avec, "les deux branches doivent DIVERGER, sinon le test est vide"


def test_le_caster_lui_meme_n_est_PAS_repositionne():
    """ASYMETRIE NATIVE, et elle est LOAD-BEARING : `ae@+0x08` porte l'ENTITE, que
    `TargetsSelector$$SelectTiles` deplie par `GetTiles(caster, state)` = l'empreinte COURANTE. Un
    arbre ancre sur `Caster()` lit donc la position d'ORIGINE meme quand la candidate est posee.
    Le port ne doit toucher QUE `caster_pos`, jamais `caster['pos']`."""
    d = _dctx((4, 9))
    assert d.caster["pos"] == {"col": 1, "row": 1}
    assert d.caster.get("feet") == [{"col": 1, "row": 1}, {"col": 2, "row": 1}]


def test_solar_atomizer_pose_la_position_PAR_TUILE_BALAYEE_et_RIEN_a_l_origine():
    """Le CALL-SITE. `...SolarAtomizerPlaybook$$EvaluateNonComparable` itere
    `GetEligibleTargetsSelectable(this, caster, casterPosition)` puis evalue `GetTargetTiles()` sur
    une COPIE de l'`AbilityEntities` de chaque cible : la bande lit donc la position candidate.

    ⚠ A L'ORIGINE le port pose `None` -- et c'est PLUS fidele que d'y poser la position : natif,
    `CasterPosition.Tiles` a l'origine EST l'empreinte d'origine, que le repli rend MESUREE la ou
    `caster_pos` la reduirait a sa main tile (residu `#459-r1`, INCHANGE par cette tranche).

    Lecture STATIQUE de l'AST -- un test qui monterait un runner pour cela paierait une bataille
    pour verifier qu'une variable est passee."""
    src = inspect.getsource(SA.SolarAtomizerPlaybook.generate_candidates)
    arbre = ast.parse(src.lstrip())
    # `cp = None if caster_pos == ctx.origin else caster_pos`
    ternaires = [n for n in ast.walk(arbre) if isinstance(n, ast.IfExp)]
    assert any(isinstance(t.body, ast.Constant) and t.body.value is None
               and isinstance(t.orelse, ast.Name) and t.orelse.id == "caster_pos"
               for t in ternaires), (
        "le call-site ne pose plus `None` a l'origine et la position candidate ailleurs")
    # ... et il le passe bien au contexte de l'evaluation.
    kws = [k.arg for n in ast.walk(arbre) if isinstance(n, ast.Call) for k in n.keywords]
    assert "caster_pos" in kws, (
        "`caster_pos` n'est plus transmis au `replace(...)` du contexte d'evaluation -- la bande "
        "redeviendrait celle de l'empreinte COURANTE, SILENCIEUSEMENT")


def test_le_defaut_reste_None_pour_la_voie_CalculateCustomUtility():
    """Les autres appelants du socle mirrorent `CalculateCustomUtility`, qui NE PASSE PAS son
    `casterPosition`. Le defaut du parametre doit donc rester `None` : le rendre obligatoire, ou
    poser la position d'office, ferait mentir ces quatre voies-la."""
    sig = inspect.signature(TT.dsl_context_for_tile_target)
    assert sig.parameters["caster_position"].default is None
