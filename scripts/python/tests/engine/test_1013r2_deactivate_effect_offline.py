"""#1013-r2 -- la feuille DSL `DeactivateEffect`, l'etage qui BLOQUAIT le port de `TheArdentBlade`
(relique 1468 d'`adeptCelestine`). Purement OFFLINE.

LU (build `rnca9r7q6c`) :

  * `IdunBattleLogic.Entities.DSLBehaviors$$DeactivateEffect(selector, effectType)` instancie
    `IdunBattle.Entities.Behaviours.DeactivateEffectBehaviour` (`+0x50 = selector`,
    `+0x60 = (int)effectType`) ;
  * `DeactivateEffectBehaviour$$Execute` est le JUMEAU EXACT d'`ActivateEffectBehaviour$$Execute`
    -- corps identique instruction pour instruction, seul l'index de slot du processeur differe
    (`0x2d` = 45 contre `0x2c` = 44) ;
  * le slot 45 mene a `IdunBattle.Operations.DeactivateEffectOperation$$Execute`, qui pousse une
    demande TYPEE au slot 47 (`RefreshEffects`) ; l'ecriture reelle est
    `IdunBattle.Operations.RefreshEffectsOperation$$DeactivateEffect` :
    no-op si `+0x5c == 0`, sinon `+0x5c = 0` puis `UpdateEffectTargets(<liste VIDE>)`.

⚠ **Il DESACTIVE, il ne RETIRE PAS** : `RemoveEffect` est un slot DISTINCT (17) de
`IdunBattle.Core.Services.IOperationProcessor`, jamais emprunte ici. C'est ce que gardent les
etages 2 et 3 -- un port qui supprimerait l'instance passerait les etages 1 et 4, et casserait
silencieusement le cycle `HasEffect(onlyActive = true)` du `CreateTrigger` de la relique.
"""
import pytest

from engine.entities.effect_type import EffectType
from engine.runner.abilities.behaviours.effects import ActivateEffect, DeactivateEffect

#: Meme contrat que les cliquets de la banque (`declencheur_cliquet.py`).
DECLENCHEUR = {
    # VIDE, et c'est un RESULTAT : les deux seuls modules que ce fichier exerce
    # (`abilities/behaviours/effects.py` pour les deux feuilles jumelles, `entities/effect_type.py`
    # pour le type discriminant) sont dans sa fermeture d'imports, donc dans la cascade DERIVEE
    # par le foyer -- et #531 interdit de recopier ce que le foyer derive.
    "chemins": (),
    "build": False,          # aucune lecture du binaire ni de `data/symbols/**`
    "toujours": False,
    "raison": (
        "Ce fichier garde le comportement de la feuille `DSLBehaviors$$DeactivateEffect` et son "
        "ASYMETRIE avec sa jumelle `ActivateEffect` -- les deux vivent dans "
        "`abilities/behaviours/effects.py`, que l'import en tete tire, donc tout changement de "
        "l'une ou de l'autre le rejoue. Il n'exerce AUCUN etat de bataille reel : le montage est "
        "une paire de doubles locaux (`_Eff`, `_Effects`), volontairement, pour que l'etage 2 "
        "(l'instance SURVIT) ne depende pas du cycle de vie des effets. `entities/effect_type.py` "
        "entre par le meme chemin -- l'etage 1 discrimine par le TYPE. Aucune entree `data/**`."),
}

_TYPE = int(EffectType.TheArdentBlade)          # 0x5b6 = 1462
_AUTRE = int(EffectType.GeminaeSuperia_JustSummonedEffect)   # temoin : un type VOISIN a ne pas toucher


class _Sel:
    """Sélecteur mono-unité, la forme que rend `DSLSelectors+0x30` (`Owner`)."""

    def __init__(self, *uids):
        self.uids = uids

    def evaluate(self, ctx):
        return [{"id": u} for u in self.uids]


class _Eff:
    """Le strict minimum que la feuille LIT d'une instance d'effet : son type, son flag `active`
    (mirror d'`EffectComponent.IsActive @+0x5c`) et `consumed`."""

    def __init__(self, effect_type, active=True, consumed=False):
        self.effect_type, self.active, self.consumed = int(effect_type), active, consumed


class _Effects:
    def __init__(self, by_unit):
        self.by_unit = by_unit

    def has_effect(self, uid, effect_type=None):
        return any(int(e.effect_type) == int(effect_type)
                   for e in self.by_unit.get(int(uid), []) if not e.consumed)


class _State:
    def __init__(self, effects):
        self.effects = effects

    def get_entity(self, uid):
        return None


class _Ctx:
    def __init__(self, state):
        self.state, self.events = state, []

    def emit(self, nom, **kw):
        self.events.append((nom, kw))


def _monte(*effs, uids=(7,)):
    st = _State(_Effects({u: list(effs) for u in uids}))
    return st, _Ctx(st)


# ------------------------------------------------ etage 1 : le flag TOMBE, et seulement pour CE type

def test_le_flag_tombe_sur_le_type_vise():
    e, autre = _Eff(_TYPE), _Eff(_AUTRE)
    st, ctx = _monte(e, autre)
    DeactivateEffect(_Sel(7), _TYPE).execute(None, ctx)
    assert e.active is False, "`+0x5c` n'est pas tombe sur l'instance visee"
    assert autre.active is True, (
        "un effet d'un AUTRE type a ete eteint -- le natif filtre par "
        "`unit.EffectComponent.Type@+0x58 == this+0x60`")
    assert ctx.events and ctx.events[0][0] == "DeactivateEffect"
    assert ctx.events[0][1]["deactivated"] is True


def test_un_flag_deja_tombe_est_un_NO_OP_declare():
    """`RefreshEffectsOperation$$DeactivateEffect` sort AVANT toute ecriture quand `+0x5c == 0`.
    Le port doit le refleter dans son rapport, sinon un appelant croirait avoir agi."""
    st, ctx = _monte(_Eff(_TYPE, active=False))
    DeactivateEffect(_Sel(7), _TYPE).execute(None, ctx)
    assert ctx.events[0][1]["deactivated"] is False


# ------------------------------------------------ etage 2 : DESACTIVE, ne RETIRE PAS

def test_l_instance_SURVIT():
    """LE cran. `RemoveEffect` est un slot DISTINCT (17) de `IOperationProcessor` : l'entite-effet
    survit a la desactivation. Un port qui la supprimerait romprait le cycle
    `AddEffect` -> `ActivateEffect` -> `HasEffect(onlyActive)` -> `DeactivateEffect` -> re-pose,
    qui est exactement ce que fait la relique 1468."""
    e = _Eff(_TYPE)
    st, ctx = _monte(e)
    DeactivateEffect(_Sel(7), _TYPE).execute(None, ctx)
    assert st.effects.by_unit[7] == [e], "l'instance a ete RETIREE de l'unite"
    assert st.effects.has_effect(7, effect_type=_TYPE), \
        "l'effet n'est plus PRESENT : la feuille a fait un `RemoveEffect`"


def test_la_desactivation_est_REVERSIBLE_par_sa_jumelle():
    """Consequence directe de l'etage 2, et c'est ce dont la relique a besoin : le meme jeton se
    re-arme. On rejoue `ActivateEffect` sur l'instance eteinte (la branche « presente -> flag »)."""
    e = _Eff(_TYPE)
    st, ctx = _monte(e)
    DeactivateEffect(_Sel(7), _TYPE).execute(None, ctx)
    assert e.active is False
    ActivateEffect(_Sel(7), _TYPE, "TheArdentBlade").execute(None, ctx)
    assert e.active is True, "l'effet eteint n'a pas pu etre re-arme : le cycle de la relique casse"


# ------------------------------------------------ etage 3 : ce qu'il ne fait PAS

def test_il_ne_MATERIALISE_rien():
    """Asymetrie LUE avec sa jumelle. `ActivateEffect` materialise une instance absente (le canal
    de seed `decisionView` DROPPE les effets `IsActive == 0`, donc « absente » y signifie
    « desactivee »). Le sens inverse n'a pas cette ambiguite, et le natif sort en no-op quand le
    flag est deja a 0 : materialiser pour eteindre serait INVENTER une entite."""
    st, ctx = _monte()                      # aucune instance sur l'unite
    DeactivateEffect(_Sel(7), _TYPE).execute(None, ctx)
    assert st.effects.by_unit[7] == [], "une instance a ete creee pour etre eteinte"
    assert ctx.events[0][1]["deactivated"] is False


def test_un_effet_CONSOMME_est_ignore():
    e = _Eff(_TYPE, consumed=True)
    st, ctx = _monte(e)
    DeactivateEffect(_Sel(7), _TYPE).execute(None, ctx)
    assert e.active is True, "un effet deja retire par le cycle de vie a ete touche"


# ------------------------------------------------ etage 4 : la population

def test_chaque_unite_du_selecteur_est_traitee():
    """Le natif itere `(this+0x50).SelectEffects(entities)` : le selecteur peut rendre N unites."""
    a, b = _Eff(_TYPE), _Eff(_TYPE)
    st = _State(_Effects({7: [a], 9: [b]}))
    ctx = _Ctx(st)
    DeactivateEffect(_Sel(7, 9), _TYPE).execute(None, ctx)
    assert (a.active, b.active) == (False, False)
    assert [ev[1]["owner"] for ev in ctx.events] == [7, 9], "un evenement par proprietaire attendu"


def test_sans_state_c_est_un_no_op_sans_erreur():
    ctx = _Ctx(None)
    assert DeactivateEffect(_Sel(7), _TYPE).execute(None, ctx) is not None
    assert ctx.events == []


# ------------------------------------------------ etage 5 : la SIGNATURE, contre la confusion d'enum

def test_le_type_d_effet_est_stocke_en_ENTIER_et_relu_tel_quel():
    """`this+0x60 = (int)effectType`. Le membre d'enum doit survivre au stockage : `EffectType` est
    un `IntEnum`, donc `int(...)` preserve la VALEUR -- c'est ce que le site ecrit."""
    b = DeactivateEffect(_Sel(7), EffectType.TheArdentBlade)
    assert b.effect_type == 1462 == int(EffectType.TheArdentBlade)


@pytest.mark.parametrize("cls", (ActivateEffect, DeactivateEffect))
def test_les_deux_jumelles_ont_la_MEME_forme_de_selection(cls):
    """Corps identique instruction pour instruction cote natif : les deux feuilles doivent selectionner
    la MEME population (selecteur d'unites + filtre par type), sans quoi elles ne seraient pas
    inverses l'une de l'autre."""
    e, autre = _Eff(_TYPE, active=(cls is DeactivateEffect)), _Eff(_AUTRE, active=True)
    st, ctx = _monte(e, autre)
    args = (_Sel(7), _TYPE, "TheArdentBlade") if cls is ActivateEffect else (_Sel(7), _TYPE)
    cls(*args).execute(None, ctx)
    assert autre.active is True, "%s a touche un effet d'un autre type" % cls.__name__
    assert e.active is (cls is ActivateEffect)
