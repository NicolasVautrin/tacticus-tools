"""#927-r3 -- `IdunBattle.Entities.Selectors.CacheSelector$$Select` a DEUX modes, et le port
n'implementait que le MINORITAIRE.

Le ctor `IdunBattleLogic.Entities.DSLSelectors$$Cache(entities, matchAbilityEntities)` pose
`+0x18 source`, `+0x20 matchAbilityEntities`, `+0x28 = 0` (slot) et alloue TOUJOURS le
`Dictionary` de `+0x30`. `Select` :

    result = (this+0x20 == 0) ? this+0x28 : this+0x30.TryGetValue(entities)
    if (result != 0) return result
    result    = <source>.Select(entities).ToList()
    this+0x28 = result            // TOUJOURS, quel que soit le mode
    this+0x30.Add(entities, result)   // TOUJOURS

Seule la LECTURE branche sur le flag. Census PE de TOUS les call-sites (build `t6dpr4k06g`) :
**119 call-sites, 112 en mode DICT, 7 en mode SLOT**. Le port n'avait que le SLOT.

Ce fichier garde la FORME (offline, aucun runner).
"""
from __future__ import annotations

#: Ce qui doit changer pour que ce FICHIER puisse changer de verdict (#486-r15).
DECLENCHEUR = {
    "chemins": (
        "scripts/python/conftest.py", "scripts/python/tests/conftest.py",
        "scripts/python/tests/engine/conftest.py",
        "scripts/python/green_skip_guard.py", "scripts/python/declencheur_guard.py",
        # LE FOYER : le noeud `Cache` et sa cle.
        "scripts/python/engine/entities/selectors/geometry.py",
        "scripts/python/engine/dsl/base.py",
        # LES DEUX call-sites portes dont le natif passe `matchAbilityEntities = 0`.
        "scripts/python/engine/runner/abilities/loki/stormcaller.py",
        "scripts/python/engine/runner/abilities/darkangels.py",
    ),
    "build": False,
    "toujours": False,
    "raison": "Garde OFFLINE des deux modes de `CacheSelector` et de la cle `AbilityEntities`. "
              "Aucun RPC, aucun runner.",
}

from dataclasses import replace                                                  # noqa: E402

from engine.dsl.base import DslContext                                           # noqa: E402
from engine.entities.selectors.geometry import (                                 # noqa: E402
    Cache, _ABILITY_ENTITIES_SLOTS, _ability_entities_key)


class _Compteur:
    """Source qui rend un resultat DIFFERENT a chaque evaluation : c'est le seul moyen de voir
    si le noeud a re-calcule ou rendu son cache."""

    def __init__(self):
        self.n = 0

    def evaluate(self, ctx):
        self.n += 1
        return [{"id": 100 + self.n}]


def _u(i):
    return {"id": i, "visualId": "u%d" % i}


# --------------------------------------------------------------------------------------------
# [1] LES DEUX MODES, ET CE QUI LES DISTINGUE
# --------------------------------------------------------------------------------------------

def test_mode_slot_rend_le_premier_cache_quel_que_soit_le_contexte():
    """`if (this+0x20 == 0) result = this+0x28` : le slot ignore l'`AbilityEntities`."""
    src = _Compteur()
    n = Cache(src, match_ability_entities=False)
    a = DslContext(caster=_u(1), target=_u(2))
    b = replace(a, target=_u(3))
    assert n.evaluate(a) == [{"id": 101}]
    assert n.evaluate(b) == [{"id": 101}], "le mode SLOT ne re-calcule JAMAIS"
    assert src.n == 1


def test_mode_dict_recalcule_quand_l_ability_entities_change():
    """`TryGetValue(entities)` : un `AbilityEntities` different est un MISS."""
    src = _Compteur()
    n = Cache(src, match_ability_entities=True)
    a = DslContext(caster=_u(1), target=_u(2))
    b = replace(a, target=_u(3))
    assert n.evaluate(a) == [{"id": 101}]
    assert n.evaluate(b) == [{"id": 102}], "le mode DICT doit re-calculer sur un autre contexte"
    assert n.evaluate(a) == [{"id": 101}], "et re-servir le cache du contexte deja vu"
    assert src.n == 2


def test_les_deux_modes_divergent_bien(monkeypatch):
    """NON-DEGENERESCENCE : sans ce cran, les deux tests ci-dessus pourraient passer sur un port
    qui ne distingue rien (par exemple si la cle etait constante)."""
    a = DslContext(caster=_u(1), target=_u(2))
    b = replace(a, target=_u(3))
    slot, dico = Cache(_Compteur(), False), Cache(_Compteur(), True)
    slot.evaluate(a), dico.evaluate(a)
    assert slot.evaluate(b) != dico.evaluate(b), (
        "les deux modes doivent produire des resultats DIFFERENTS sur ce montage, sinon le "
        "temoin est degenere et ne teste rien")


def test_le_defaut_est_le_mode_DICT():
    """112 call-sites sur 119. Un defaut SLOT redonnerait au port la sur-memoisation de #927-r3."""
    assert Cache(_Compteur()).match_ability_entities is True


def test_l_ecriture_alimente_les_DEUX_emplacements():
    """`this+0x28 = result` ET `this+0x30.Add(...)` sont INCONDITIONNELS -- c'est LU. Un port qui
    n'ecrirait que l'emplacement de son mode serait indistinguable... jusqu'au jour ou un
    lecteur croiserait les deux."""
    a = DslContext(caster=_u(1))
    slot = Cache(_Compteur(), match_ability_entities=False)
    slot.evaluate(a)
    assert slot._by_entities, "le mode SLOT alimente quand meme le dictionnaire"
    dico = Cache(_Compteur(), match_ability_entities=True)
    dico.evaluate(a)
    assert dico._cached is not None, "le mode DICT alimente quand meme le slot"


def test_un_resultat_VIDE_est_memoise():
    """`if (result != 0)` teste un POINTEUR : une `List<T>` vide n'est pas nulle. Un `if cached:`
    Python re-calculerait a chaque appel -- silencieusement, et seulement sur les cas vides."""

    class _Vide:
        def __init__(self):
            self.n = 0

        def evaluate(self, ctx):
            self.n += 1
            return []

    for flag in (False, True):
        src = _Vide()
        n = Cache(src, match_ability_entities=flag)
        a = DslContext(caster=_u(1))
        assert n.evaluate(a) == [] and n.evaluate(a) == []
        assert src.n == 1, "mode %s : le resultat VIDE doit etre memoise" % flag


# --------------------------------------------------------------------------------------------
# [2] LA CLE : les slots d'`AbilityEntities`, et RIEN d'autre
# --------------------------------------------------------------------------------------------

def test_la_cle_IGNORE_ce_qui_n_est_pas_un_slot_d_ability_entities():
    """C'EST LE CRAN QUI PROTEGE LA MEMOISATION LOAD-BEARING. GetEmRuntz partage un `Cache` entre
    `Spawn` (tuiles LIBRES pre-spawn) et `PerformAIAttackFromCurrentPosition` (memes tuiles
    post-spawn) ; entre les deux, `ctx.units`/`ctx.children` ont change. Si la cle prenait le
    contexte ENTIER, la 2e lecture raterait le cache et `CanAddUnit` re-calcule exclurait les
    tuiles desormais occupees -> zero grot. Le natif keye sur la STRUCTURE `AbilityEntities`, qui
    ne porte ni le pool d'unites ni l'accumulateur de summons."""
    a = DslContext(caster=_u(1), units=[_u(1)], children=[])
    b = replace(a, units=[_u(1), _u(2)], children=[_u(2)], times_attacked=3)
    assert _ability_entities_key(a) == _ability_entities_key(b)
    src = _Compteur()
    n = Cache(src, match_ability_entities=True)
    assert n.evaluate(a) == n.evaluate(b) and src.n == 1


def test_la_cle_DISTINGUE_l_element_courant_lie_par_un_foreach():
    """`AbilityEntities$$.ctor(entities, activeTarget)` -- la surcharge COPIE-avec-activeTarget est
    exactement ce que fait un `Foreach`/`Filter`. Deux iterations sont donc deux cles."""
    a = DslContext(caster=_u(1))
    for role in ("subject", "active_target", "target", "owner", "actor", "effect"):
        x = replace(a, **{role: _u(7)})
        y = replace(a, **{role: _u(8)})
        assert _ability_entities_key(x) != _ability_entities_key(y), (
            "le role %s doit entrer dans la cle" % role)


def test_la_cle_couvre_les_slots_declares_et_le_dit():
    """Le registre des slots est le CONTRAT : s'il maigrit, la cle se met a confondre des
    contextes que le natif distingue. On assertionne son non-vide ET son contenu."""
    assert set(_ABILITY_ENTITIES_SLOTS) == {
        "actor", "caster", "target", "owner", "caster_pos",
        "effect", "active_target", "subject", "is_first_hit"}


def test_la_cle_est_HACHABLE_sur_les_domaines_reels():
    """Le port fait circuler des dicts d'unite, des ids de tuile, des positions et des listes.
    Une cle non hachable ferait exploser le noeud a l'execution, pas au montage."""
    a = DslContext(caster=_u(1), target=3, active_target=[_u(2), 5], caster_pos=(2, 3),
                   subject=None, is_first_hit=True)
    k = _ability_entities_key(a)
    assert isinstance(hash(k), int)


def test_un_dict_sans_id_retombe_sur_l_identite_d_OBJET():
    """Le natif compare les champs ENTITE par REFERENCE. Sans `id`, la seule traduction fidele
    est l'identite d'objet -- surtout pas une egalite structurelle, qui confondrait deux entites
    distinctes de meme contenu."""
    x, y = {"visualId": "a"}, {"visualId": "a"}
    a = DslContext(caster=x)
    b = DslContext(caster=y)
    assert _ability_entities_key(a) != _ability_entities_key(b)
    assert _ability_entities_key(a) == _ability_entities_key(DslContext(caster=x))


# --------------------------------------------------------------------------------------------
# [3] LES DEUX CALL-SITES PORTES DE LA MINORITE ECRIVENT LEUR LITTERAL
# --------------------------------------------------------------------------------------------

def _caches_de(noeud, vus=None):
    """Walk d'arbre : tous les `Cache` atteignables depuis `noeud` (`vars` + `__slots__`)."""
    vus = vus if vus is not None else set()
    if id(noeud) in vus or noeud is None or isinstance(noeud, (str, bytes, int, float, bool)):
        return []
    vus.add(id(noeud))
    out = [noeud] if isinstance(noeud, Cache) else []
    enfants = list(vars(noeud).values()) if hasattr(noeud, "__dict__") else []
    for s in (getattr(type(noeud), "__slots__", ()) or ()):
        enfants.append(getattr(noeud, s, None))
    for e in enfants:
        if isinstance(e, (list, tuple, set)):
            for x in e:
                out += _caches_de(x, vus)
        else:
            out += _caches_de(e, vus)
    return out


def test_stormcaller_et_dark_talon_strike_ecrivent_le_mode_SLOT():
    """Ce sont DEUX des sept call-sites natifs en mode SLOT (`matchAbilityEntities = 0`), et les
    seuls de ces sept dont le port materialise le noeud. Le defaut etant DICT, un litteral non
    ecrit serait un mode faux -- silencieux, comme toujours ici."""
    from engine.entities.selectors.accessors import Target
    from engine.runner.abilities.darkangels import dark_talon_strike_tree
    from engine.runner.abilities.loki.stormcaller import stormcaller_tree

    caches = _caches_de(stormcaller_tree())
    assert caches, "TEMOIN VIDE : aucun `Cache` trouve dans l'arbre Stormcaller"
    assert all(c.match_ability_entities is False for c in caches), (
        "Stormcaller est en mode SLOT au call-site natif")

    c2 = _caches_de(dark_talon_strike_tree(Target()))
    assert c2, "TEMOIN VIDE : aucun `Cache` trouve dans l'arbre DarkTalonStrike"
    assert all(c.match_ability_entities is False for c in c2), (
        "DarkTalonStrike est en mode SLOT au call-site natif")
