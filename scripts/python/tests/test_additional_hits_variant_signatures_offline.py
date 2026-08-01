"""#393 -- les SUBSTITUTIONS d'`execute_additional_hits` suivent-elles le port, et TRANSMETTENT-elles
ce qu'elles ne font pas varier ?

POURQUOI CE FICHIER EXISTE. Plusieurs harnais remplacent `execute_additional_hits` par une
implementation de substitution a signature FIXE, pour n'isoler qu'un etage a la fois
(`additional_hits_variant` = ORDRE + MATERIALISATION ; `_extra_rolls_variant` = tirages
intercalaires). Le port livre, lui, gagne des parametres : #227 a ajoute `attack_profile`, #366-r1 a
ajoute `hit_interceptor`. Chaque ajout casse en silence toute substitution restee en arriere, et le
symptome est un `TypeError: ... got an unexpected keyword argument` a la PROCHAINE passe live -- pas
a la PR qui a introduit le parametre (mesure : `test_additional_hits_rounding_live` est parti rouge
sur `master`, 3 echecs, apres la PR `1227 HarlequinsPanoply`).

DEUX GARDES, et il faut LES DEUX :

  1. **SIGNATURE** -- le scan AST decouvre TOUTE fonction de `scripts/python/**` dont les six
     premiers parametres sont ceux du canal (`state, attacker_id, target_id, tgt, thc, groups`) :
     c'est la forme structurelle d'une substitution. Chacune doit declarer la MEME liste de
     parametres que le port. Aucune liste a tenir a jour -- une TROISIEME substitution ecrite demain
     est enrolee toute seule.
  2. **TRANSMISSION** -- une signature qui accepte un parametre puis l'AVALE rendrait cette garde
     verte tout en cessant d'exercer l'etage : c'est exactement le « vert qui ment » qu'un
     `**kwargs` fourre-tout produirait. On verifie donc que le parametre arrive REELLEMENT a
     `AttackDamageOperation._run_hits`, par un sentinelle.

OFFLINE et hermetique : aucune session Frida, aucun runner, et `gameconfig` est neutralise (ce
fichier ne mesure ni profil de degat ni valeur -- seulement le CABLAGE).
"""
from __future__ import annotations

import ast
import inspect
import io
import sys
from contextlib import contextmanager
from pathlib import Path

import pytest

PYDIR = Path(__file__).resolve().parents[1]          # scripts/python
sys.path.insert(0, str(PYDIR))

from engine.runner.operations.additional_hits import execute_additional_hits  # noqa: E402

# Les SIX premiers parametres du canal : signature structurelle d'une substitution.
_HEAD = ("state", "attacker_id", "target_id", "tgt", "thc", "groups")
# Sous-arbres sans interet pour ce scan (aucun code du port ni des harnais n'y vit).
_SKIP_DIRS = {"__pycache__", ".pytest_cache"}


def _reference_params():
    """Liste ORDONNEE des parametres du port livre -- la reference, re-derivee, jamais recopiee."""
    return tuple(inspect.signature(execute_additional_hits).parameters)


def _iter_py_files():
    for path in sorted(PYDIR.rglob("*.py")):
        if any(part in _SKIP_DIRS for part in path.parts):
            continue
        yield path


def _params_of(node):
    """(noms ordonnes, a_du_var_positional_ou_var_keyword) d'un noeud `def` AST."""
    a = node.args
    names = [p.arg for p in (list(a.posonlyargs) + list(a.args))]
    star = a.vararg is not None or a.kwarg is not None
    names += [p.arg for p in a.kwonlyargs]
    return tuple(names), star


def _substitution_impls():
    """Toute fonction dont les 6 premiers parametres sont ceux du canal -> [(rel, nom, ligne,
    params, star)]. Inclut le port lui-meme (qui matche trivialement sa propre reference)."""
    out = []
    for path in _iter_py_files():
        with io.open(path, encoding="utf-8") as fh:
            try:
                tree = ast.parse(fh.read(), filename=str(path))
            except SyntaxError as e:                  # un fichier illisible est un vrai probleme
                pytest.fail("%s : source non analysable (%s)" % (path, e))
        for node in ast.walk(tree):
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            names, star = _params_of(node)
            if names[:len(_HEAD)] == _HEAD:
                rel = path.relative_to(PYDIR).as_posix()
                out.append((rel, node.name, node.lineno, names, star))
    return out


def test_le_scan_TROUVE_bien_les_substitutions_connues():
    """Premisse de la garde : si le scan ne trouvait plus rien, les deux tests suivants
    passeraient A VIDE. On verifie donc qu'il voit le port ET les deux harnais mesures."""
    found = {(rel, name) for rel, name, _l, _p, _s in _substitution_impls()}
    assert ("engine/runner/operations/additional_hits.py",
            "execute_additional_hits") in found, found
    assert ("probe_r6_round_materialize.py", "_exec") in found, found
    assert ("probe_r6b_additional_hits_order.py", "_exec") in found, found


def test_toute_substitution_suit_la_signature_du_port():
    """CLIQUET. Un parametre ajoute au port et non repercute ici = `TypeError` a la prochaine
    passe live du harnais concerne."""
    ref = _reference_params()
    bad = []
    for rel, name, lineno, params, star in _substitution_impls():
        if star:
            bad.append("%s:%d %s : accepte *args/**kwargs -- un fourre-tout rendrait cette "
                       "garde verte en cessant d'exercer l'etage" % (rel, lineno, name))
        elif params != ref:
            manquants = [p for p in ref if p not in params]
            en_trop = [p for p in params if p not in ref]
            bad.append("%s:%d %s : manquants=%s en_trop=%s"
                       % (rel, lineno, name, manquants, en_trop))
    assert not bad, ("substitution(s) d'`execute_additional_hits` desynchronisees du port "
                     "(reference = %s) :\n  %s" % (list(ref), "\n  ".join(bad)))


# --- 2. TRANSMISSION : le parametre arrive-t-il jusqu'a `_run_hits` ? --------------------------

@contextmanager
def _patched(cls, **attrs):
    """Pose des attributs sur `cls` et les RETIRE exactement (un attribut absent du `__dict__` de
    la classe -- donc herite -- est supprime au lieu d'etre fige a sa valeur resolue)."""
    saved = {k: (k in cls.__dict__, cls.__dict__.get(k)) for k in attrs}
    for k, v in attrs.items():
        setattr(cls, k, v)
    try:
        yield
    finally:
        for k, (was_own, old) in saved.items():
            if was_own:
                setattr(cls, k, old)
            else:
                delattr(cls, k)


class _Rng:
    def next_internal(self, lo, hi):
        return lo


class _Thc:
    hp = 1000


def _run_one(impl, hit_interceptor, failed_block0=None):
    """Fait passer UN groupe a travers `impl`, tout etage voisin neutralise, et rend les kwargs
    vus par `AttackDamageOperation._run_hits`. Ce qu'on mesure ici est le CABLAGE, pas une valeur."""
    import gameconfig as GC
    from engine.runner.operations.damage import AttackDamageOperation as ADO

    seen: dict = {}

    def _rh(rng, hit_nc, hit_cr, *a, **kw):
        seen.update(kw)
        # Le stub rend le CONTRAT COMPLET de `_run_hits` : une cle manquante ferait echouer une
        # substitution qui THREADE correctement (`crit_allowed`, `failed_block`) -- un rouge qui
        # accuserait le harnais, pas le port.
        return {"total": 0, "per_hit": [], "per_hit_health": [], "rolls": [], "crits": [],
                "shield_dmg": 0, "armor_dmg": 0, "did_crit": False, "did_block": False,
                "did_evade": False, "next_hit_index": 0, "death": False,
                "crit_allowed": True, "failed_block": set(kw.get("failed_block0") or ())}

    orig_dp = GC.damage_profile
    GC.damage_profile = lambda _p: {}        # hermetique : aucun profil n'est mesure ici
    try:
        with _patched(ADO,
                      _run_hits=staticmethod(_rh),
                      _apply_max_out=staticmethod(lambda st, aid, nc, cr: (nc, cr)),
                      _target_limits=staticmethod(lambda *a, **k: None),
                      _deplete_shield=staticmethod(lambda *a, **k: None),
                      _apply_damage_pipeline=staticmethod(lambda *a, **k: False)):
            impl(_Rng.__new__(type("S", (), {"rng": _Rng()})), 1, 2, object(), _Thc(),
                 [{"profile": "Physical", "count": 1, "min": 10, "max": 10}],
                 None, None, 0, 100, None, None,
                 hit_interceptor=hit_interceptor, failed_block0=failed_block0)
    finally:
        GC.damage_profile = orig_dp
    return seen


@pytest.mark.parametrize("factory", ["additional_hits_variant", "_extra_rolls_variant"])
def test_la_substitution_TRANSMET_hit_interceptor(factory):
    """#366-r1. L'intercepteur per-coup (`should_discard` = l'etape que
    `IdunBattle.Operations.AttackDamageOperation$$ExecuteHit` execute juste apres `On(6)`, et
    `on_blocked` = `On(0x3c)` puis `ADamageOperation$$RegisterBlocks`) n'est PAS une variable de ces
    contrefactuels : une substitution qui l'avalerait desarmerait le discard et le compteur
    `ActorStatisticsComponent+0x8c` dans les rejeux offline, mais PAS dans le port livre -- et
    l'ecart se lirait comme une regression de l'etage effectivement mesure."""
    import probe_r6_round_materialize as P
    import probe_r6b_additional_hits_order as B

    impl = (P.additional_hits_variant("roll_then_reduce", None) if factory == "additional_hits_variant"
            else B._extra_rolls_variant(1))
    sentinel = object()
    seen = _run_one(impl, sentinel)
    assert "hit_interceptor" in seen, (
        "`%s` n'a pas repasse `hit_interceptor` a `_run_hits` (kwargs vus : %s)"
        % (factory, sorted(seen)))
    assert seen["hit_interceptor"] is sentinel, (
        "`%s` a repasse un AUTRE objet que celui recu -- la substitution doit THREADER, pas "
        "reconstruire" % factory)


@pytest.mark.parametrize("factory", ["additional_hits_variant", "_extra_rolls_variant"])
def test_la_substitution_TRANSMET_failed_block0(factory):
    """#407. `OngoingAttack+0x48` (`FailedBlockIds`) -- l'etat block de l'ATTAQUE, seme PAR
    REFERENCE dans `OngoingHitGroup+0x60` par `IdunBattle.Operations.ADamageOperation$$
    SetupHitGroup` et alimente par `RegisterBlocks`. Une substitution qui l'AVALERAIT ferait
    re-tirer, dans les rejeux offline, des sources de block deja exclues cote natif -- soit des
    tirages en TROP, exactement l'ecart que ces contrefactuels sont censes NE PAS introduire.
    On verifie le CONTENU (et non l'identite) : le port comme les substitutions recopient
    (`set(failed_block0 or ())`)."""
    import probe_r6_round_materialize as P
    import probe_r6b_additional_hits_order as B

    impl = (P.additional_hits_variant("roll_then_reduce", None) if factory == "additional_hits_variant"
            else B._extra_rolls_variant(1))
    seen = _run_one(impl, None, failed_block0={4242})
    assert "failed_block0" in seen, (
        "`%s` n'a pas repasse `failed_block0` a `_run_hits` (kwargs vus : %s)"
        % (factory, sorted(seen)))
    assert 4242 in (seen["failed_block0"] or ()), (
        "`%s` a repasse un failed_block0 qui NE CONTIENT PAS l'id recu (%s) -- la substitution "
        "doit THREADER l'etat block de l'attaque, pas le reconstruire vide"
        % (factory, seen["failed_block0"]))
