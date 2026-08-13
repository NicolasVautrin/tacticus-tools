"""#890-r2 -- `Effect_SourceId` d'un `AddStaticStatModifierEffect` : le natif pose LA CIBLE.

Le foyer `runner/abilities/behaviours/effects.py::AddStaticStatModifierEffect` passait
`source = entities.caster`. Le natif ne le fait dans AUCUN cas, et le decompile le dit en deux
temps -- ce fichier garde les deux, plus la non-regression du jumeau DYNAMIQUE :

  1. `IdunBattle.Entities.Behaviours.AddStatModifierEffectBehaviour$$Execute` :
         src = <sel@+0x58>.SelectSingle(entities)
         foreach (cible in <sel@+0x60>.Select(entities))
             source = (src != null) ? src : cible          <- LE DEFAUT EST LA CIBLE
  2. `IdunBattleLogic.Entities.DSLBehaviors$$AddStaticStatModifierEffect(targets, effectType,
     statType, amount, turns, isHidden)` construit ce behaviour par
     `.ctor(logger, isDynamic = 0, source = NULL, targets, ...)` -- le 3e argument du ctor est un
     **litteral nul**. Donc `+0x58 == null` pour TOUT call-site de cette factory, et la branche
     prise est toujours << la cible >>. Le variant `...ToOwner` passe `source = targets =
     DSLSelectors+0x30`, meme entite des deux cotes : meme resultat.

⚠ **LE JUMEAU DYNAMIQUE N'A PAS CE VICE, et il ne faut PAS l'aligner.**
`DSLBehaviors$$AddDynamicStatModifierEffect(targets, source, ...)` a, LUI, un vrai selecteur de
source, et le port le lit deja (`AddDynamicStatModifierEffect.source_sel`). Un correctif qui
uniformiserait les deux feuilles casserait la voie dynamique.

⚠ **CE QUE L'ECART COUTE.** Il est INOBSERVABLE sur les call-sites dont la magnitude est figee par
un noeud `IdunBattleLogic.Entities.DSLFormulas$$Direct` -- c'est le cas des trois effets de `1032
Catalyst`, ou l'ecart a ete mesure live. Mais le champ est LU par
`IdunBattle.Entities.Effects.BaseEffect$$GetAbilityState` : un effet a magnitude `ConfigVar`
resolue contre la SOURCE lirait le mauvais `AbilityState`.

ASCII only.
"""
from __future__ import annotations

DECLENCHEUR = {
    # PERIMETRE LARGE et MESURE : ce fichier monte un `State` runner complet, la factory d'effets,
    # les selecteurs et les Operations de pose -- sa fermeture d'import couvre l'essentiel de
    # `engine/**`. Declarer etroit produirait un FAUX VERT.
    # ⚠ Les DEUX formes sont necessaires : `**/` exige un SEGMENT, donc `scripts/python/**/*.py`
    # ne voit PAS `scripts/python/board.py`.
    "chemins": ("scripts/python/*.py", "scripts/python/**/*.py"),
    # `build: False` -- aucune valeur n'est figee depuis le binaire ; ce qui est fige, c'est la
    # STRUCTURE lue au decompile (qui porte la source de l'entite-effet).
    "build": False,
    # `toujours: True` : offline, aucun runner, ~2 s. Le foyer est PARTAGE par au moins six
    # abilities deja validees -- le cout de le rejouer a chaque passe est negligeable.
    "toujours": True,
    "raison": "La SOURCE de l'entite-effet posee par la feuille PARTAGEE "
              "`AddStaticStatModifierEffect` est la CIBLE, jamais le caster (selecteur `+0x58` "
              "nul sur cette voie). Garde aussi la non-regression du jumeau DYNAMIQUE, qui a, "
              "lui, un vrai selecteur de source.",
}

import pytest

from engine.dsl.effects import ExecutionContext
from engine.entities.effect_type import EffectType
from engine.entities.selectors.accessors import Target
from engine.entities.stats import StatType

#: Un effet PORTEUR de stat-mod quelconque : ce fichier ne teste pas la magnitude, il teste QUI est
#: inscrit comme source de l'entite-effet.
TYPE_EFFET = int(EffectType.RedRampage_ExtraMovement)
CASTER, CIBLE = 11, 22


@pytest.fixture(name="etat_caster_et_cible")
def _etat_caster_et_cible():
    """Un `State` minimal avec un caster et une CIBLE DISTINCTE, de camps opposes.

    TEMOIN NON NUL : `CASTER != CIBLE`. Sans deux entites distinctes, << source = caster >> et
    << source = cible >> rendraient le MEME id et le fichier ne conclurait rien."""
    from engine.entities.effects_state import EffectsState
    from engine.entities.stats import UnitStats
    from engine.runner.components import OwnerComponent, StatsComponent
    from engine.runner.state import State

    assert CASTER != CIBLE, "regime DEGENERE : caster et cible doivent etre deux entites distinctes"
    st = State()
    st.effects = EffectsState()
    for uid, team in ((CASTER, 1), (CIBLE, 2)):
        ent = st.add_entity(uid)
        us = UnitStats()

        class _Ctx:
            traits = []

            def __init__(self, u):
                self.stats = u

            def get_stat(self, *_a, **_k):
                return 0

        ent.add_component(StatsComponent(ctx=_Ctx(us)))
        ent.add_component(OwnerComponent(team, 2 + team))
    return st


def _poser(state, feuille):
    from engine.runner.abilities.behaviours.context import entities_from_state
    entities = entities_from_state(state, CASTER, CIBLE)
    ectx = ExecutionContext(state=state, rng=state.rng)
    feuille.execute(entities, ectx)
    poses = [(uid, e) for uid, lst in state.effects.by_unit.items() for e in lst]
    return poses, ectx


# ---------------------------------------------------------------------------------------------
# ETAGE 1 -- LA SOURCE EST LA CIBLE
# ---------------------------------------------------------------------------------------------
def test_la_source_de_l_entite_effet_est_LA_CIBLE_pas_le_caster(etat_caster_et_cible):
    """`source = (src != null) ? src : cible`, et `src` est NUL sur cette voie."""
    from engine.runner.abilities.behaviours.effects import AddStaticStatModifierEffect

    poses, _ectx = _poser(etat_caster_et_cible,
                          AddStaticStatModifierEffect(Target(), TYPE_EFFET,
                                                      int(StatType.MOVEMENT), 1,
                                                      name=EffectType(TYPE_EFFET).name,
                                                      duration_turns=3))
    assert len(poses) == 1, "une seule entite-effet posee : %s" % poses
    uid, eff = poses[0]
    assert uid == CIBLE, "l'effet est PORTE par la cible"
    assert eff.source == CIBLE, (
        "AVANT #890-r2 le port inscrivait le CASTER (%d) : `BaseEffect$$GetAbilityState` "
        "aurait lu le mauvais `AbilityState` pour une magnitude `ConfigVar`" % CASTER)
    assert eff.source != CASTER


def test_le_jumeau_OrUpdate_herite_du_meme_choix(etat_caster_et_cible):
    """`AddOrUpdateStaticStatModifierEffect` se COMPOSE sur la meme feuille (remove-puis-add) : il
    ne doit pas y avoir deux reponses a la meme question dans le meme fichier."""
    from engine.runner.abilities.behaviours.effects import AddOrUpdateStaticStatModifierEffect

    poses, _ectx = _poser(etat_caster_et_cible,
                          AddOrUpdateStaticStatModifierEffect(Target(), TYPE_EFFET,
                                                              int(StatType.MOVEMENT), 1,
                                                              name=EffectType(TYPE_EFFET).name,
                                                              duration_turns=3))
    assert poses, "temoin : la branche `then` du `If` d'idempotence doit AVOIR pose quelque chose"
    for uid, eff in poses:
        assert eff.source == uid, "meme regle que la feuille sous-jacente : source == cible"


# ---------------------------------------------------------------------------------------------
# ETAGE 2 -- NON-REGRESSION du jumeau DYNAMIQUE, qui a un VRAI selecteur de source
# ---------------------------------------------------------------------------------------------
def test_la_voie_DYNAMIQUE_garde_son_selecteur_de_source(etat_caster_et_cible):
    """`DSLBehaviors$$AddDynamicStatModifierEffect(targets, source, ...)` porte, LUI, un selecteur
    `+0x58` REEL. Aligner les deux feuilles << pour la coherence >> casserait cette voie : la
    source y est celle que le call-site DESIGNE, pas la cible."""
    from engine.entities.selectors.tiles import Caster
    from engine.runner.abilities.behaviours.effects import AddDynamicStatModifierEffect

    poses, _ectx = _poser(etat_caster_et_cible,
                          AddDynamicStatModifierEffect(Target(), Caster(), TYPE_EFFET,
                                                       int(StatType.MOVEMENT),
                                                       name=EffectType(TYPE_EFFET).name,
                                                       duration_turns=3))
    assert len(poses) == 1, "une seule entite-effet posee : %s" % poses
    uid, eff = poses[0]
    assert uid == CIBLE
    assert eff.source == CASTER, (
        "la voie DYNAMIQUE resout sa source par son selecteur `+0x58` -- ici `Caster()`. "
        "Si elle rend la CIBLE, c'est que les deux feuilles ont ete uniformisees a tort")


def test_la_signature_des_deux_feuilles_reste_DISTINCTE():
    """Cran STRUCTUREL : la feuille statique n'a PAS de `source_sel` (le natif y passe un litteral
    nul), la dynamique en a un OBLIGATOIRE. Un port qui ajouterait un `source_sel` optionnel a la
    statique inventerait un cablage qu'aucun call-site natif n'emprunte."""
    import inspect

    from engine.runner.abilities.behaviours.effects import (AddDynamicStatModifierEffect,
                                                            AddStaticStatModifierEffect)
    stat = inspect.signature(AddStaticStatModifierEffect.__init__).parameters
    dyn = inspect.signature(AddDynamicStatModifierEffect.__init__).parameters
    assert "source_sel" not in stat, \
        "le ctor natif de la voie STATIQUE passe `source = NULL` : rien a cabler"
    assert "source_sel" in dyn and dyn["source_sel"].default is inspect.Parameter.empty, \
        "la voie DYNAMIQUE prend sa source en argument OBLIGATOIRE"
