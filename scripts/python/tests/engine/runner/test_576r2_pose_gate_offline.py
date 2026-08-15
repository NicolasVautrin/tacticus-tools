"""#576-r2 -- LA POSE MATERIALISE, SEUL LE REFRESH APPLIQUE.

La feuille `AddStaticStatModifierEffect` (`runner/abilities/behaviours/effects.py`) appelait
`apply_change_stat` INCONDITIONNELLEMENT juste apres `AddEffectOperation.execute`. Le natif ne le
fait pas. Chaine LUE de bout en bout sur le build courant `t6dpr4k06g` :

  1. `IdunBattle.Operations.AddEffectOperation$$Execute` materialise l'entite-effet (ecrit
     `EffectComponent.Type @+0x58`, `Level @+0x68`) puis appelle `...$$AddNewEffect` ;
  2. le PREMIER geste d'`...$$AddNewEffect` est le slot **46** (`RefreshEffects`) de
     `IdunBattle.Core.Services.IOperationProcessor` -- table VERSIONNEE
     `data/symbols/<build>/metadata/ioperationprocessor_slots.tsv` ;
  3. `Core.Services.OperationProcessor$$RefreshEffects` appelle DIRECTEMENT
     `IdunBattle.Operations.RefreshEffectsOperation$$Execute` : **aucune file d'attente**. Le
     refresh est SYNCHRONE dans la chaine de pose ;
  4. `IdunBattle.Operations.RefreshEffectsOperation$$RefreshEffect`, lu VERBATIM :

         active = ShouldBeActive(trigger, type, effect, comp, owner, activePlayer, effectEntity)
         if (!active)  DeactivateEffect(this, comp, effect, effectEntity, owner)
         else       {  comp->+0x5c = 1
                       if (effect.<slot 0xc>(trigger))              // ShouldRefreshForTrigger
                           UpdateEffectTargets(GetDesiredEffectTargets(...), ...) }

     et `...$$ApplyEffectsForTargets` -- SEUL appelant du slot `IEffect+0xe` (`ApplyModification`,
     etabli par #576-r1) -- n'est atteint QUE par la branche `else` ;
  5. `IdunBattle.Operations.RefreshEffectsOperation$$ShouldBeActive`, branche `refreshType == 0`
     (`Automatically`, celle de la pose) :

         if (comp->+0x5e)                        return false
         if (!effect.<slot 0xc>(refreshTrigger)) return comp->+0x5c      // le flag COURANT
         return effect.<slot 0xb>(entities)                              // CreateActiveCondition

Un composant NEUF porte `+0x5c == 0`. Donc, quand la `CreateActiveCondition` est fausse a la pose,
la modification **n'est JAMAIS appliquee** -- ce n'est pas << appliquee puis retiree au refresh
suivant >>.

⚠ CE FICHIER CORRIGE L'ENONCE DU RESIDU. #576-r2 parlait d'une << fenetre >> entre le cast et le
premier declencheur du driver. Il n'y a AUCUNE fenetre cote natif : le refresh est synchrone.
L'ecart etait un GATE MANQUANT, pas un delai. Le correctif est le meme ; la raison de le poser,
non -- et c'est elle qui dit ou chercher le prochain.

⚠ POURQUOI CE FICHIER EXISTE ALORS QUE #576-r1 EST DEJA GARDE. `test_576r1_blood_chalice_inactive_
offline.py` monte son `UnitStats` A LA MAIN (`us.change_stat(PIERCE, KEY, 15)`) : il n'exerce
JAMAIS la feuille de pose. Il est donc structurellement aveugle au gate -- il reste vert que la
feuille applique ou non. Ce fichier-ci passe par la FEUILLE, et c'est la seule facon de voir le
cran.

ASCII only.
"""
from __future__ import annotations

DECLENCHEUR = {
    # PERIMETRE LARGE et MESURE, meme motif que `test_890r2_statmod_source_offline.py` : ce fichier
    # monte un `State` runner complet, la factory d'effets, les selecteurs et les Operations de
    # pose. Sa fermeture d'import couvre l'essentiel d'`engine/**` -- declarer etroit produirait un
    # FAUX VERT. L'etage 4 lit EN PLUS tout `engine/**` par AST (via le probe).
    # ⚠ Les DEUX formes sont necessaires : `**/` exige un SEGMENT, donc `scripts/python/**/*.py`
    # ne voit PAS `scripts/python/board.py`.
    "chemins": ("scripts/python/*.py", "scripts/python/**/*.py"),
    # `build: False` -- rien n'est fige depuis le binaire ; ce qui est fige, c'est la STRUCTURE lue
    # au decompile (la pose materialise, le refresh applique).
    "build": False,
    # Offline, aucun runner, ~20 s dont l'essentiel est l'AST de l'etage 4. Le foyer est PARTAGE
    # par une trentaine de call-sites : le cout de le rejouer est negligeable devant le risque.
    "toujours": True,
    "raison": "La feuille PARTAGEE `AddStaticStatModifierEffect` ne doit appliquer la "
              "`ValueModification` que sous le meme predicat que la branche `ShouldBeActive` du "
              "refresh natif. Garde AUSSI l'invariant qui borne le rayon du gate : toute classe "
              "qu'il peut fermer a une condition CONSTANTE (le driver ne re-applique jamais).",
}

import pytest

from engine.dsl.effects import ExecutionContext
from engine.entities.effect_type import EffectType
from engine.entities.selectors.accessors import Target
from engine.entities.stats import StatType

#: `1369 BloodChalice_ExtraPiercing` -- le SEUL effet, aujourd'hui, que le gate peut fermer
#: (cf. etage 4, qui le RE-DERIVE au lieu de le figer). Sa `CreateActiveCondition` lit
#: `Target@DSLSelectors+0x60`, un slot que le contexte de `ShouldBeActive` laisse a ZERO (#576-r1).
TYPE_GATE = int(EffectType.BloodChalice_ExtraPiercing)
STAT_GATE = int(StatType.EXTRA_PIERCE_MELEE)

#: TEMOIN : un effet SANS `CreateActiveCondition` portee -- `BaseEffect.is_active` rend `True` par
#: defaut, donc le gate doit LAISSER PASSER. Sans cet etage, l'etage 2 serait vert par VACUITE
#: (une feuille qui n'appliquerait plus JAMAIS rien le satisferait aussi).
TYPE_PASSANT = int(EffectType.RedRampage_ExtraMovement)
STAT_PASSANT = int(StatType.MOVEMENT)

MONTANT = 15
CASTER, CIBLE = 11, 22


@pytest.fixture(name="etat")
def _etat():
    """Un `State` minimal avec un caster et une CIBLE DISTINCTE, de camps opposes."""
    from engine.entities.effects_state import EffectsState
    from engine.entities.stats import UnitStats
    from engine.runner.components import OwnerComponent, StatsComponent
    from engine.runner.state import State

    assert CASTER != CIBLE, "regime DEGENERE : caster et cible doivent etre distincts"
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


def _stats_de(state, uid):
    """Le `UnitStats` de `uid` -- `State` porte des `__slots__`, on passe donc par le composant,
    qui est de toute facon la voie que la feuille elle-meme emprunte (`apply_change_stat`)."""
    from engine.runner.components import StatsComponent

    ent = state.get_entity(int(uid))
    return ent.get_component(StatsComponent).ctx.stats


def _poser(state, type_effet, stat):
    """Joue la FEUILLE (pas un `UnitStats` monte a la main) et rend (effets_poses, ectx)."""
    from engine.runner.abilities.behaviours.context import entities_from_state
    from engine.runner.abilities.behaviours.effects import AddStaticStatModifierEffect

    feuille = AddStaticStatModifierEffect(Target(), type_effet, stat, MONTANT,
                                          name=EffectType(type_effet).name, duration_turns=3)
    entities = entities_from_state(state, CASTER, CIBLE)
    ectx = ExecutionContext(state=state, rng=state.rng)
    feuille.execute(entities, ectx)
    poses = [(uid, e) for uid, lst in state.effects.by_unit.items() for e in lst]
    return poses, ectx


# ---------------------------------------------------------------------------------------------
# ETAGE 0 -- la classe posee est bien celle du port
# ---------------------------------------------------------------------------------------------
def test_la_feuille_pose_bien_la_classe_a_condition_portee(etat):
    """Sans lui, tout le reste porterait sur un `BaseEffect` anonyme (le defaut quand un nom n'est
    pas au registre), dont `is_active` rend `True` : l'etage 2 serait rouge sans rapport avec la
    RE, ou vert pour la mauvaise raison."""
    from engine.entities.effects.loki.blood_chalice import BloodChaliceExtraPiercingEffect

    poses, _ = _poser(etat, TYPE_GATE, STAT_GATE)
    assert len(poses) == 1, "une seule entite-effet posee : %s" % poses
    assert isinstance(poses[0][1], BloodChaliceExtraPiercingEffect)


# ---------------------------------------------------------------------------------------------
# ETAGE 1 -- TEMOIN NON NUL : le gate LAISSE PASSER ce qui n'a pas de condition portee
# ---------------------------------------------------------------------------------------------
def test_temoin_une_pose_SANS_condition_portee_applique_toujours(etat):
    """`BaseEffect.is_active` rend `True` par DEFAUT -- une valeur par defaut, pas une lecture du
    natif. Le gate doit donc etre INERTE sur les 38 autres effect_type que la feuille pose.

    C'est l'etage qui interdit la degradation la plus tentante : << ne plus rien appliquer >>
    satisferait l'etage 2 et casserait une trentaine de call-sites en silence."""
    poses, ectx = _poser(etat, TYPE_PASSANT, STAT_PASSANT)
    assert len(poses) == 1
    uid, _eff = poses[0]
    assert _stats_de(etat, uid).get_stat(STAT_PASSANT) == MONTANT, (
        "un effet sans `CreateActiveCondition` portee doit voir sa `ValueModification` APPLIQUEE "
        "a la pose -- le refresh natif y rend `ShouldBeActive == true`")
    emis = [p for n, p in ectx.emitted if n == "AddStaticStatModifierEffect"]
    assert emis and emis[0].get("active") is True


# ---------------------------------------------------------------------------------------------
# ETAGE 2 -- LE CRAN : la pose GATEE n'applique RIEN, et sans aucun refresh
# ---------------------------------------------------------------------------------------------
def test_la_pose_dont_la_condition_est_FAUSSE_n_applique_rien(etat):
    """LE cran de #576-r2. Mirror de la branche `if (!ShouldBeActive(...)) DeactivateEffect(...)`
    de `IdunBattle.Operations.RefreshEffectsOperation$$RefreshEffect` : `ApplyEffectsForTargets`
    n'est jamais atteint, donc le slot `IEffect+0xe` (`ApplyModification`) ne joue pas.

    AUCUN refresh n'est declenche ici -- c'est le point. AVANT #576-r2 la stat valait `MONTANT`
    jusqu'au premier declencheur du driver (`TurnChanged`, `UnitPositionChanged`, degat)."""
    poses, ectx = _poser(etat, TYPE_GATE, STAT_GATE)
    uid, eff = poses[0]
    assert eff.is_active(None) is False, "temoin : c'est bien la condition qui ferme"
    assert _stats_de(etat, uid).get_stat(STAT_GATE) == 0, (
        "AVANT #576-r2 le port appliquait +%d a la pose et ne le retirait qu'au premier refresh ; "
        "le natif ne l'applique JAMAIS (`ShouldBeActive` faux des la pose, refresh SYNCHRONE)"
        % MONTANT)
    emis = [p for n, p in ectx.emitted if n == "AddStaticStatModifierEffect"]
    assert emis and emis[0].get("active") is False


# ---------------------------------------------------------------------------------------------
# ETAGE 3 -- le gate ne degenere PAS en << pas de pose >> : la MATERIALISATION a lieu
# ---------------------------------------------------------------------------------------------
def test_l_entite_effet_est_MATERIALISEE_meme_quand_le_gate_ferme(etat):
    """Le natif ECRIT bien le `StatModifierComponent` de l'entite-effet : seule l'APPLICATION est
    gatee, jamais la creation. Un gate qui sauterait la pose entiere ferait disparaitre l'effet de
    `decisionView`, casserait `RemoveEffect` (plus rien a retirer) et priverait le driver de quoi
    APPLIQUER l'instance si sa condition devenait vraie."""
    poses, _ = _poser(etat, TYPE_GATE, STAT_GATE)
    assert len(poses) == 1, "l'entite-effet doit EXISTER"
    uid, eff = poses[0]
    assert eff.stat_mod_source is not None, (
        "`stat_mod_source` reste pose : c'est la cle par laquelle `RemoveEffect` et le driver "
        "savent QUELLE contribution cette instance porte")
    assert list(eff.reverted_stats() or []) == [STAT_GATE], (
        "`reverted_stats` reste installe sur l'instance -- l'etage 4 de "
        "`test_576r1_blood_chalice_inactive_offline.py` en depend")
    assert eff.remaining_turns == 3, "la duree posee ne doit pas dependre du gate"


# ---------------------------------------------------------------------------------------------
# ETAGE 4 -- L'INVARIANT QUI BORNE LE RAYON (re-derive, JAMAIS fige)
# ---------------------------------------------------------------------------------------------
def test_toute_classe_que_le_gate_peut_fermer_a_une_condition_CONSTANTE():
    """LE cran de non-regression, et il garde une chose que l'oeil ne verifie pas.

    Le driver `refresh_stat_modifier_effects` **NE RE-APPLIQUE JAMAIS** une instance portant un
    `stat_mod_source` -- il ne fait que la RETIRER (le bloc `if e.stat_mod_source is not None:`
    sort par `continue` des que la condition est vraie). Consequence : si le gate ferme sur une
    classe dont la condition est DYNAMIQUE, la contribution est perdue A VIE au lieu d'etre
    appliquee quand la condition devient vraie. Ce serait une REGRESSION, pas une fidelite.

    L'invariant est donc : toute classe de l'INTERSECTION
    `{effect_type poses par la feuille}` INTER `{classes surchargeant is_active}` doit avoir une
    condition CONSTANTE -- meme verdict quel que soit l'etat du porteur.

    ⚠ RIEN N'EST FIGE ICI, ni un compte ni une liste de noms : les deux se PERIMENT a chaque port
    qui entre une classe surchargeant `is_active`, et sont la cause mecanique d'un conflit de
    rebase entre PR paralleles (meme raison que le bloc equivalent de
    `runner/operations/refresh_effects.py`). L'intersection est RE-DERIVEE par
    `probe_576r2_rayon_du_gate.mesurer()`.

    QUAND CE TEST ROUGIT, ce n'est pas lui qu'il faut relacher : une classe a condition DYNAMIQUE
    vient d'entrer dans le rayon du gate. Il faut alors cabler la RE-APPLICATION dans le driver
    (le natif re-evalue `ShouldBeActive` a CHAQUE refresh), pas retirer le gate."""
    from probe_576r2_rayon_du_gate import mesurer

    res = mesurer()
    assert not res["non_resolus"], (
        "des call-sites de la feuille ne sont pas resolus : le rayon n'est pas mesure, donc "
        "l'invariant ci-dessous ne porte sur rien -- %s" % res["non_resolus"])
    # ASSERTION DE NON-VACUITE : sans elle, une intersection VIDE (par regression du recenseur,
    # ou par un import casse) rendrait ce test vert en n'ayant RIEN verifie.
    assert res["mordus"], (
        "l'intersection est VIDE : soit le recenseur est casse, soit `BloodChalice_ExtraPiercing` "
        "a quitte le rayon. Dans les deux cas ce test ne garde plus rien -- ne pas l'ignorer")

    etats = [None, {},
             {"hp": 100, "max_hp": 100, "traits": ["Chaos"], "owner_id": CIBLE, "has_moved": False},
             {"hp": 1, "max_hp": 100, "traits": [], "owner_id": CASTER, "has_moved": True}]
    dynamiques = []
    for ordinal in res["mordus"]:
        klass = res["surchargent"][res["par_ordinal"][ordinal]]
        inst = klass.__new__(klass)          # pas de ctor : on n'exerce que la condition
        verdicts = set()
        for st in etats:
            try:
                verdicts.add(bool(klass.is_active(inst, st)))
            except Exception:                # noqa: BLE001 -- une condition qui exige un etat
                verdicts.add("exception")    #   monte n'est PAS constante : on le compte comme tel
        if len(verdicts) != 1:
            dynamiques.append((ordinal, res["par_ordinal"][ordinal], sorted(map(str, verdicts))))
    assert not dynamiques, (
        "condition(s) DYNAMIQUE(S) dans le rayon du gate de pose : %s. Le driver ne RE-APPLIQUE "
        "jamais une instance a `stat_mod_source` -- le gate leur ferait perdre leur contribution "
        "A VIE. Cabler la re-application dans `refresh_stat_modifier_effects` AVANT d'elargir le "
        "rayon." % dynamiques)
