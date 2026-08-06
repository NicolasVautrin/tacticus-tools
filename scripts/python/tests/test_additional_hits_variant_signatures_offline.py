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
import sys
from contextlib import contextmanager
from pathlib import Path

import pytest

PYDIR = Path(__file__).resolve().parents[1]          # scripts/python
sys.path.insert(0, str(PYDIR))

import repo_read                                                            # noqa: E402
from engine.runner.operations.additional_hits import execute_additional_hits  # noqa: E402

# Les SIX premiers parametres du canal : signature structurelle d'une substitution.
_HEAD = ("state", "attacker_id", "target_id", "tgt", "thc", "groups")
# Sous-arbres sans interet pour ce scan (aucun code du port ni des harnais n'y vit).
_SKIP_DIRS = {"__pycache__", ".pytest_cache"}


def _reference_params():
    """Liste ORDONNEE des parametres du port livre -- la reference, re-derivee, jamais recopiee."""
    return tuple(inspect.signature(execute_additional_hits).parameters)


def _iter_py_files(racine: Path = PYDIR):
    """`racine` : PARAMETRE depuis #486-r5, pour que la garde du cache puisse exercer le
    balayage REEL sur un corpus synthetique minuscule. Le defaut est le corpus complet -- le
    perimetre des tests de ce fichier est INCHANGE."""
    for path in sorted(racine.rglob("*.py")):
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


#: RESULTAT du balayage, memoise pour la duree du PROCESS (#486-r5).
#:
#: POURQUOI. `_substitution_impls` lit et `ast.parse` TOUT `scripts/python/**` -- 2089 fichiers,
#: 37 Mo. Mesure du 2026-08-06 : 18 a 26 s par appel, et le 2e appel ne coute PAS moins que le
#: premier (rien n'etait mis en cache). Trois tests de ce fichier l'appelaient, soit ~66 s de
#: balayage pour UNE seule information.
#:
#: SUR A PARTAGER, et c'est ce qui autorise le cache : la valeur est un `tuple` de `tuple`s de
#: scalaires (`str`, `int`, `tuple[str]`, `bool`) -- IMMUABLE de bout en bout. Aucun test ne peut
#: la muter pour le suivant, donc aucun etat ne fuit. On ne garde PAS les ASTs : mesure du
#: 2026-08-06, les retenir couterait **1013 Mo** de tas Python pour ce seul corpus.
#:
#: Un `pytest.fail` du premier appel ne peuple pas le cache : les appels suivants re-balaient et
#: re-echouent, exactement comme avant.
_IMPLS_CACHE: tuple | None = None


def _substitution_impls():
    """Toute fonction dont les 6 premiers parametres sont ceux du canal -> ((rel, nom, ligne,
    params, star), ...). Inclut le port lui-meme (qui matche trivialement sa propre reference)."""
    global _IMPLS_CACHE
    if _IMPLS_CACHE is None:
        _IMPLS_CACHE = tuple(_balayer_substitutions())
    return _IMPLS_CACHE


def _balayer_substitutions(racine: Path = PYDIR):
    """LE balayage, sans cache -- meme perimetre et meme critere qu'avant #486-r5.

    Lecture PARALLELE (`repo_read`, 16 threads) : l'OUVERTURE d'un fichier sous `scripts/` pese
    ~7 ms (filtre systeme sur les extensions executables), soit ~3 s en serie contre ~0,9 s en
    parallele sur ce corpus. Le texte rendu est celui de `io.open(..., encoding='utf-8')` --
    meme decodage strict, meme traduction universelle des fins de ligne, donc memes `lineno`.
    Les deux echecs restent traites comme avant : `UnicodeDecodeError` remonte telle quelle
    (elle remontait de `fh.read()`), `OSError` aussi (elle remontait de `io.open`).
    """
    out = []
    fichiers = list(_iter_py_files(racine))
    for path, data in zip(fichiers, repo_read.read_bytes_many([str(p) for p in fichiers])):
        if data is None:
            raise OSError("illisible : %s" % path)
        try:
            tree = ast.parse(repo_read.to_text(data), filename=str(path))
        except SyntaxError as e:                      # un fichier illisible est un vrai probleme
            pytest.fail("%s : source non analysable (%s)" % (path, e))
        for node in ast.walk(tree):
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            names, star = _params_of(node)
            if names[:len(_HEAD)] == _HEAD:
                rel = path.relative_to(racine).as_posix()
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
    """`HealthComponent` minimal. `minimal_health` (le `Nullable<int>` @`FillUpStatComponent+0x1c`)
    en fait partie : `execute_additional_hits` le threade en `hp_floor` depuis #462-r4e-o ; et
    `over_reduce` (@+0x24, l'accumulateur de sur-reduction) depuis #462-r4e-o-r1."""
    hp = 1000
    minimal_health = None
    over_reduce = 0


class _Tgt:
    """Entite CIBLE minimale : `execute_additional_hits` l'interroge par `get_component`
    (`UnitFlagsComponent` pour `unit_is_overkilled`, `StatsComponent` pour `can_be_overkilled`)."""
    @staticmethod
    def get_component(_c):
        return None


def _cles_d_etat_attaque_lues():
    """Les cles que `damage_hits.attack_state_out` LIT sur le retour d'une substitution.

    DERIVEES a l'AST du foyer, jamais recopiees : c'est le contrat de SORTIE du canal, au meme
    titre que la signature est son contrat d'ENTREE. Si le port en ajoute une, cette garde la voit
    sans qu'on y touche."""
    src = (PYDIR / "engine" / "runner" / "operations" / "damage_hits.py").read_text(
        encoding="utf-8")
    tree = ast.parse(src)
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == "attack_state_out":
            cles = []
            for n in ast.walk(node):
                if (isinstance(n, ast.Subscript) and isinstance(n.value, ast.Name)
                        and n.value.id == "src" and isinstance(n.slice, ast.Constant)
                        and isinstance(n.slice.value, str)):
                    cles.append(n.slice.value)
            return tuple(sorted(set(cles)))
    pytest.fail("`attack_state_out` introuvable dans `damage_hits.py` -- la garde ne peut plus "
                "deriver le contrat de sortie, et un vert signifierait seulement qu'elle est "
                "aveugle.")


def test_le_contrat_de_SORTIE_est_bien_DERIVE_et_non_vide():
    """Premisse : sans cette assertion, un `attack_state_out` renomme rendrait la garde suivante
    VERTE A VIDE (ensemble de cles vide => aucune exigence)."""
    cles = _cles_d_etat_attaque_lues()
    assert cles, "aucune cle derivee -- la garde de sortie serait vacueuse"
    assert "next_hit_index" in cles, cles


def test_toute_substitution_expose_le_contrat_de_SORTIE():
    """CLIQUET #419-r6-r1. Une substitution qui n'expose pas les cles d'etat d'attaque fait lever
    `KeyError` a `attack_state_out`, appele par les DEUX vecteurs des qu'un groupe existe.

    Ce n'est pas theorique : `probe_r6_round_materialize.additional_hits_variant` ne les posait
    pas, et c'est la cause UNIQUE des **15** rouges des trois `test_additional_hits_*_live.py`
    (7 + 5 + 3), mesures pre-existants par #419-r6 et jusque-la non diagnostiques. Le garde
    voisin ne voyait rien : il verifie la signature d'ENTREE, pas le contrat de SORTIE."""
    from engine.runner.operations.additional_hits import execute_additional_hits as _port
    from engine.services.damage_modifiers import DamageModifiers
    from probe_r6_round_materialize import additional_hits_variant
    from probe_r6b_additional_hits_order import _extra_rolls_variant
    attendues = set(_cles_d_etat_attaque_lues())
    # Les substitutions EXERCABLES ici. Les autres sont NOMMEES plus bas plutot que tues : une
    # liste blanche silencieuse ne peut pas montrer celle qu'elle a oubliee.
    impls = [("engine/runner/operations/additional_hits.py", _port),
             ("probe_r6_round_materialize.py",
              additional_hits_variant("reduce_then_roll", None)),
             ("probe_r6b_additional_hits_order.py", _extra_rolls_variant(0))]
    bad = []
    for nom, impl in impls:
        out = _run_one(impl, None, retour=True,
                       mods=DamageModifiers(), def_mods=DamageModifiers())
        if out is None:
            bad.append("%s : aucun groupe execute -- le harnais ne mesure rien" % nom)
            continue
        manquantes = sorted(attendues - set(out))
        if manquantes:
            bad.append("%s : cles d'etat d'attaque ABSENTES du retour = %s (=> `KeyError` dans "
                       "`attack_state_out`)" % (nom, manquantes))
    # PORTEE : ce que le scan trouve et que cet etage n'exerce PAS (factory non triviale, closure
    # dont l'instanciation demande un contexte live...). Imprime, jamais tu.
    exercees = {n.split("/")[-1] for n, _ in impls}
    vues = {rel.split("/")[-1] for rel, _n, _l, _p, _s in _substitution_impls()}
    non_exercees = sorted(vues - exercees)
    if non_exercees:
        print("[419-r6-r1] substitutions VUES mais NON exercees par cet etage : %s"
              % non_exercees)
    assert not bad, "\n  ".join([""] + bad)


def _run_one(impl, hit_interceptor, failed_block0=None, retour=False,
             mods=None, def_mods=None):
    """Fait passer UN groupe a travers `impl`, tout etage voisin neutralise, et rend les kwargs
    vus par `AttackDamageOperation._run_hits` -- ou, si `retour`, le RETOUR de `impl` (le contrat
    de sortie). Ce qu'on mesure ici est le CABLAGE, pas une valeur.

    `mods`/`def_mods` : `None` suffit au volet CABLAGE (le stub de `_run_hits` court-circuite le
    calcul), mais PAS au volet SORTIE -- la variante, elle, traverse `reduce_group_damage`, qui
    deref `mods.pct_list`. On les rend donc fournissables plutot que de neutraliser un etage de
    plus (ce qui ferait diverger le contrefactuel du port sur une TROISIEME variable)."""
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
                "crit_allowed": True, "failed_block": set(kw.get("failed_block0") or ()),
                # #462-r4e-o-r1 : `hits_executed` (le compte de coups, DISTINCT de `len(per_hit)`
                # depuis le port du SITE (A)), `overkilled`, `overkill_at_hit`,
                # `overkill_suppressed`, `over_reduce`.
                "hits_executed": 0, "overkilled": None, "overkill_at_hit": None,
                "overkill_suppressed": 0, "over_reduce": 0}

    orig_dp = GC.damage_profile
    GC.damage_profile = lambda _p: {}        # hermetique : aucun profil n'est mesure ici
    try:
        with _patched(ADO,
                      _run_hits=staticmethod(_rh),
                      _apply_max_out=staticmethod(lambda st, aid, nc, cr: (nc, cr)),
                      _target_limits=staticmethod(lambda *a, **k: None),
                      _deplete_shield=staticmethod(lambda *a, **k: None),
                      _apply_damage_pipeline=staticmethod(lambda *a, **k: False)):
            # `get_entity` : le PORT LIVRE l'appelle (`unit_prevents_overkill`, #195) la ou la
            # variante ne le fait pas. Le stub d'etat doit donc porter les DEUX contrats, sinon la
            # garde ne peut pas exercer le port lui-meme -- et une garde qui n'exerce pas la
            # reference ne peut pas dire qu'une substitution s'en ecarte.
            _S = type("S", (), {"rng": _Rng(), "get_entity": staticmethod(lambda _i: None)})
            res = impl(_Rng.__new__(_S), 1, 2, _Tgt(), _Thc(),
                       [{"profile": "Physical", "count": 1, "min": 10, "max": 10}],
                       mods, def_mods, 0, 100, None, None,
                       hit_interceptor=hit_interceptor, failed_block0=failed_block0)
    finally:
        GC.damage_profile = orig_dp
    return res if retour else seen


@pytest.mark.parametrize("factory", ["additional_hits_variant", "_extra_rolls_variant"])
def test_la_substitution_TRANSMET_hit_interceptor(factory):
    """#366-r1. L'intercepteur per-coup (`should_discard` = l'etape que
    `IdunBattle.Operations.AttackDamageOperation$$ExecuteHit` execute juste apres `On(6)`, et
    `on_blocked` = `On(0x3c = UnitBlocked)` puis `ADamageOperation$$RegisterBlocks`) n'est PAS une variable de ces
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
