"""#922-r5 + #1020-r6 -- les DEUX canaux que cette tranche a recables, gardes OFFLINE.

POURQUOI CE FICHIER EXISTE. Les deux correctifs sont des CABLAGES : ils ne changent aucune formule,
seulement la FRAICHEUR d'une entree (#922-r5) et la PRESENCE d'un argument (#1020-r6). Une
degradation y est donc silencieuse -- ni erreur, ni crash -- et les deux confrontations qui les
etablissent sont LIVE, donc absentes de toute passe offline. Ce fichier est ce qui reste quand la
session Frida est eteinte.

CHAQUE ETAGE PORTE SA CONTRE-EPREUVE, dans le meme test : on rejoue le MEME critere contre la
version d'AVANT le correctif (reconstruite ici, pas devinee) et on exige qu'elle ECHOUE. Une garde
qui n'a jamais ete vue rougir ne prouve rien.

OFFLINE et hermetique : aucune session Frida, aucun runner, aucun `gameconfig`.
"""
from __future__ import annotations

import ast
import inspect
import sys
from pathlib import Path

import pytest

PYDIR = Path(__file__).resolve().parents[3]          # scripts/python
sys.path.insert(0, str(PYDIR))

#: Ce qui doit changer pour que ce fichier puisse changer de verdict (#486-r15). Pris LARGE : un
#: declencheur trop ETROIT est un faux vert -- le fichier ne se rejoue pas sous `--since` quand ce
#: qu'il garde a bouge.
DECLENCHEUR = {
    "chemins": (
        # SOCLE d'un fichier de test OFFLINE : la cascade des `conftest.py` et les gardes de passe.
        # Aucun harnais live n'est traverse -- ce fichier ne monte AUCUN runner.
        "scripts/python/conftest.py", "scripts/python/tests/conftest.py",
        "scripts/python/tests/engine/conftest.py",
        "scripts/python/tests/engine/runner/conftest.py",
        "scripts/python/green_skip_guard.py", "scripts/python/declencheur_guard.py",
        # PROPRE A CE FICHIER.
        # #922-r5 : le foyer du canal CRIT (`_crit_carriers`, `_crit_params`) et l'univers de
        # balayage qu'il compose.
        "scripts/python/engine/runner/operations/damage.py",
        "scripts/python/engine/entities/effects/__init__.py",
        # La source de la liste que le port CAPTURAIT trop tot -- si elle cesse d'etre
        # `active_effects`, la fraicheur ne se mesure plus au meme endroit.
        "scripts/python/engine/runner/damage_model.py",
        "scripts/python/engine/runner/components.py",
        # #1020-r6 : le canal `source_ability` des groupes, et ses DEUX vecteurs appelants.
        "scripts/python/engine/runner/operations/additional_hits.py",
        "scripts/python/engine/runner/operations/damage_ops/normal.py",
        "scripts/python/engine/runner/operations/damage_ops/ability.py",
    ),
    "build": False,      # aucun octet du binaire ni de `data/symbols/**` n'est lu ici
    "toujours": False,
    "raison": "les deux CABLAGES gardes ici -- fraicheur des porteurs du canal CRIT (#922-r5) et "
              "descente de `source_ability` vers les groupes additionnels (#1020-r6) -- se "
              "degradent SANS erreur ni crash, donc ce fichier doit se rejouer des que l'un de "
              "leurs foyers bouge. Les chemins sont pris LARGE volontairement : `probe_486r15 "
              "--proposer` rend << RIEN A DECLARER hors de la cascade >> (la fermeture d'imports "
              "de ce fichier, 746 modules, y tient entierement), donc une liste VIDE serait juste "
              "au sens du garde -- mais elle ne DIRAIT rien. Les foyers cites sont ceux dont une "
              "edition change le verdict : le canal CRIT (`damage.py`, `effects/__init__.py`), la "
              "SOURCE de la liste que le port capturait trop tot (`damage_model.py`, "
              "`components.py`), et le canal des groupes avec ses DEUX vecteurs appelants.",
}

from engine.runner.operations.damage import AttackDamageOperation   # noqa: E402
from engine.runner.operations import additional_hits as AH          # noqa: E402


# --------------------------------------------------------------------------- substrat minimal

class _Effects:
    """`EffectsState` minimal. `active_effects` rend une liste RECONNAISSABLE et DIFFERENTE de
    celle qu'un appelant aurait pu capturer plus tot -- c'est ce qui rend la fraicheur MESURABLE."""

    def __init__(self):
        self.appels = []

    def active_effects(self, uid, _unit_state):
        self.appels.append(int(uid))
        return ["RELU-%d" % int(uid)]


class _State:
    """`State` minimal : `_crit_carriers` n'en lit que `entities` et `effects`. `entities` VIDE fait
    que la boucle sur les autres unites ne tourne pas -- on isole ainsi l'attaquant, qui est le seul
    sujet de cet etage."""
    entities: dict = {}

    def __init__(self):
        self.effects = _Effects()
        self.entities = {}


@pytest.fixture()
def state_sans_unites(monkeypatch):
    """`unit_state_for_effects` est neutralise : cet etage mesure la PROVENANCE de la liste, pas la
    construction du `unit_state`. Le binding patche est celui de `operations.damage` (forme A --
    patcher `runner.components` NE MORDRAIT PAS, cf. CLAUDE.md)."""
    monkeypatch.setattr("engine.runner.operations.damage.unit_state_for_effects",
                        lambda _st, _uid: {})
    return _State()


# --------------------------------------------------------------------------- #922-r5

def test_les_effets_de_l_attaquant_sont_RELUS_de_l_etat_et_non_repris_du_parametre(
        state_sans_unites):
    """#922-r5. `IdunBattle.Core.Services.EffectsQuery$$GetActiveEffectsWithBonuses` ne prend AUCUN
    argument : elle enumere la collection globale des entites-effet, rafraichit chacune (slot
    `0x29`) puis filtre sur `EffectComponent+0x5c`. Aucune place native ne donne a l'attaquant une
    liste plus vieille que celle des autres.

    Le port passait `attacker_effects` -- la liste que `damage_model.attacker_modifiers` calcule en
    TETE d'operation, donc AVANT `On(PreAttackHit = 6)`. Un effet du porteur devenu ACTIF pendant
    l'event etait alors invisible du canal CRIT, et la relecture post-event de `_crit_params` ne
    pouvait rien y changer."""
    st = state_sans_unites
    perimee = ["PERIMEE"]                 # ce qu'un vecteur aurait capture avant l'event
    carriers = AttackDamageOperation._crit_carriers(st, 7, perimee, None)
    par_owner = dict((oid, effs) for oid, effs in carriers if oid is not None)
    assert 7 in par_owner, "l'attaquant doit figurer parmi les porteurs : %s" % (carriers,)
    assert par_owner[7] == ["RELU-7"], (
        "les effets de l'attaquant viennent du PARAMETRE (%s) au lieu d'etre RELUS de `state` -- "
        "c'est exactement le regime de #922-r5, ou le correctif #919 devenait un NO-OP"
        % (par_owner[7],))
    assert 7 in st.effects.appels, "`active_effects` n'a meme pas ete appele pour l'attaquant"


def test_CONTRE_EPREUVE_la_version_d_AVANT_echoue_ce_meme_critere(state_sans_unites):
    """La version d'AVANT #922-r5, reconstruite : elle repasse `attacker_effects` tel quel. Le
    critere ci-dessus doit la REFUSER -- sinon il ne mesure pas ce qu'il pretend."""
    from engine.entities.effects import board_effect_carriers

    def _avant(state, att_id, attacker_effects, tgt_id):
        return board_effect_carriers(att_id, attacker_effects, tgt_id, [], [])

    carriers = _avant(state_sans_unites, 7, ["PERIMEE"], None)
    par_owner = dict((oid, effs) for oid, effs in carriers if oid is not None)
    assert par_owner[7] == ["PERIMEE"], (
        "la version d'AVANT ne reproduit plus le defaut -- la contre-epreuve est vide")


def test_SANS_EffectsState_le_parametre_reste_le_repli(state_sans_unites):
    """RETRO-COMPAT : un appelant sans `EffectsState` (probe, contexte hors runner) garde le
    comportement d'avant. Le correctif ne DEGRADE aucun chemin, il en RAFRAICHIT un."""
    st = state_sans_unites
    st.effects = None
    carriers = AttackDamageOperation._crit_carriers(st, 7, ["FOURNIE"], None)
    par_owner = dict((oid, effs) for oid, effs in carriers if oid is not None)
    assert par_owner[7] == ["FOURNIE"], par_owner


# --------------------------------------------------------------------------- #1020-r6

def test_execute_additional_hits_ACCEPTE_source_ability():
    """Contrat d'ENTREE. Le cliquet #393 exige que les substitutions suivent la signature du port ;
    celui-ci exige que le port PORTE le parametre -- sans quoi #393 serait vert sur une signature
    amputee."""
    assert "source_ability" in inspect.signature(AH.execute_additional_hits).parameters


def _appels_de(fichier: str, nom_fn: str):
    """Les `Call` a `nom_fn` dans `fichier`, par l'AST -- jamais un `in` sur le texte, qui verrait
    aussi bien un commentaire qu'un appel."""
    src = (PYDIR / fichier).read_text(encoding="utf-8")
    arbre = ast.parse(src, filename=fichier)
    return [n for n in ast.walk(arbre)
            if isinstance(n, ast.Call) and isinstance(n.func, ast.Name) and n.func.id == nom_fn]


@pytest.mark.parametrize("vecteur", [
    "engine/runner/operations/damage_ops/normal.py",
    "engine/runner/operations/damage_ops/ability.py",
])
def test_les_DEUX_vecteurs_font_DESCENDRE_source_ability(vecteur):
    """#1020-r6. La valeur ne se devine pas au site : elle DESCEND de l'appelant, comme le natif la
    fait descendre (`AttackDamageOperation$$ExecuteAdditionalHitsWithoutDamageProfileType` pose le
    MEME `abilityOrEffect` en `AbilityEntities+0x60` ET `+0x98`). On verifie donc que chaque appel
    a `execute_additional_hits` porte le mot-cle -- et que sa valeur n'est pas un LITTERAL, ce qui
    serait precisement la valeur devinee que la fiche interdit."""
    appels = _appels_de(vecteur, "execute_additional_hits")
    assert appels, "%s : aucun appel a `execute_additional_hits`" % vecteur
    for appel in appels:
        kw = {k.arg: k.value for k in appel.keywords}
        assert "source_ability" in kw, (
            "%s:%d : appel sans `source_ability` -- le sink `On(0x39)` et le chokepoint le "
            "recevraient `None`, et le gate `HasValue` de `TransferDamageBehaviour$$Execute` "
            "refuserait tout transfert declenche par un groupe additionnel"
            % (vecteur, appel.lineno))
        assert not isinstance(kw["source_ability"], ast.Constant), (
            "%s:%d : `source_ability` est un LITTERAL -- il doit DESCENDRE de l'appelant"
            % (vecteur, appel.lineno))


def test_source_ability_arrive_au_SINK_et_au_CHOKEPOINT(monkeypatch):
    """Contrat de TRANSMISSION. Une signature qui accepte le parametre puis l'AVALE rendrait la
    garde precedente verte en cessant d'exercer le canal -- c'est le << vert qui ment >> que le
    cliquet #393 nomme deja pour ses propres parametres.

    Les DEUX destinations comptent, et pour des raisons distinctes : le SINK porte l'emission
    `On(0x39)` a sa position dans le flux PRNG (#1020-r4), le CHOKEPOINT porte le reste du
    pipeline. En alimenter un seul rendrait les deux moities du meme fait divergentes."""
    from engine.runner.operations.damage import AttackDamageOperation as ADO

    sentinelle = 4242
    vus = {}

    def _sink(state, aid, tid, thc, profil, *, is_first_damaging_hit, source_ability=None):
        vus["sink"] = source_ability
        return None

    def _pipeline(state, target_id, attacker_id, tgt, thc, total, profile, *a, **kw):
        vus["chokepoint"] = kw.get("source_ability")
        return False

    monkeypatch.setattr(ADO, "make_pre_damage_taken_sink", staticmethod(_sink))
    monkeypatch.setattr(ADO, "_apply_damage_pipeline", staticmethod(_pipeline))
    monkeypatch.setattr(ADO, "pre_damage_taken_of", staticmethod(lambda _s: None))
    monkeypatch.setattr(ADO, "_apply_max_out", staticmethod(lambda st, aid, nc, cr: (nc, cr)))
    monkeypatch.setattr(ADO, "_target_limits", staticmethod(lambda *a, **k: None))
    monkeypatch.setattr(ADO, "_run_hits", staticmethod(lambda *a, **k: {
        "total": 1, "per_hit": [1], "per_hit_health": [1], "rolls": [1], "crits": [False],
        "shield_dmg": 0, "armor_dmg": 0, "did_crit": False, "did_block": False,
        "did_evade": False, "next_hit_index": 1, "death": False, "crit_allowed": True,
        "failed_block": set(), "hits_executed": 1, "overkilled": None, "overkill_at_hit": None,
        "overkill_suppressed": 0, "over_reduce": 0}))
    import gameconfig as GC
    monkeypatch.setattr(GC, "damage_profile", lambda _p: {})

    class _Thc:
        hp = 1000
        minimal_health = None
        over_reduce = 0

    class _Tgt:
        @staticmethod
        def get_component(_c):
            return None

    class _S:
        rng = None
        entities: dict = {}

        @staticmethod
        def get_entity(_i):
            return None

    out = AH.execute_additional_hits(
        _S(), 1, 2, _Tgt(), _Thc(),
        [{"profile": "Physical", "count": 1, "min": 10, "max": 10}],
        None, None, 0, 100, None, None, source_ability=sentinelle)
    assert out is not None, "aucun groupe execute -- le harnais ne mesure rien"
    assert vus.get("sink") == sentinelle, (
        "`source_ability` n'arrive pas au SINK `On(0x39)` (vu : %r)" % (vus.get("sink"),))
    assert vus.get("chokepoint") == sentinelle, (
        "`source_ability` n'arrive pas au CHOKEPOINT `_apply_damage_pipeline` (vu : %r)"
        % (vus.get("chokepoint"),))
