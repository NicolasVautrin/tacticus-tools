"""#927-r5 -- la CLE du `Dictionary` de `CacheSelector+0x30` : ce qu'elle couvre, et le binding
que `FilterContinuous` ne posait qu'a moitie.

CE QUE LA RE-MESURE A ETABLI, ET OU L'ENONCE DU RESIDU ETAIT FAUX
-----------------------------------------------------------------
L'enonce disait « la cle ne couvre que 9 des 33 champs -- tous les champs de DEGAT manquent ».
Les deux nombres sont faux, et le « tous les champs de degat » sous-compte le trou :

  * **32 champs, pas 33.** C'est le nombre de parametres du `.ctor` NOMME d'`AbilityEntities`
    (lu dans `frida/methods.tsv` du build courant) : il porte `blockedHits` mais PAS
    `armorDamage`. Le dump Il2CppDumper en donne DEUX versions, et AUCUNE ne decrit ce
    layout -- elles sont d'autres builds. Controles concordants : `classes.tsv` = 312 boxee,
    donc 0x128 nue = exactement ce que copie `IdunBattle.Entities.Selectors.CacheSelector$$Select` ;
    `AbilityEntities$$get_IsFirstHit` lit `+0x108`, `$$get_IsFirstHitGroup` lit `+0x110`.
  * **6 champs couverts, pas 9.** La cle a 9 SLOTS, mais `caster_pos` et `is_first_hit` sont des
    PROPRIETES derivees (de `casterTile`/`casterTiles` et de `hitIndex`), et `subject` /
    `active_target` sont DEUX noeuds portes pour UN SEUL selecteur natif (`DSLFactory+0x180`).
  * **9 des 26 champs manquants sont HORS DEGAT** : `previousActiveTarget`, `targetTile`,
    `targetTiles`, `casterTile`, `casterTiles`, `activePlayer`, et les trois `abilityOrEffect`.

CE QUE LA RE-MESURE A TROUVE EN PLUS, ET QUI ETAIT UN VRAI BUG
--------------------------------------------------------------
`FilterContinuous` posait `replace(ctx, subject=item)` SEUL. Le natif -- `IdunBattle.Entities.
Selectors.FromTriggerSelector$$Select`, corps commun a `Filter` et `FilterContinuous` --
rebinde `<AbilityEntities+0x20> ActiveTarget`, et RIEN d'autre. `Filter` (`selectors/units.py`)
posait bien les deux ; celui-ci laissait `active_target` sur la valeur du contexte PARENT.

Le sens de la faute reste toujours le meme : la cle SOUS-DISTINGUE. Le port sert un HIT la ou le
natif RE-CALCULE ; il ne peut pas faire l'inverse.

Aucun runner, aucun RPC.
"""
from __future__ import annotations

#: Ce qui doit changer pour que ce FICHIER puisse changer de verdict (#486-r15).
DECLENCHEUR = {
    "chemins": (
        "scripts/python/conftest.py", "scripts/python/tests/conftest.py",
        "scripts/python/tests/engine/conftest.py",
        "scripts/python/green_skip_guard.py", "scripts/python/declencheur_guard.py",
        # LES DEUX FOYERS du residu : le noeud + sa cle, et le contexte qui la peuple.
        "scripts/python/engine/entities/selectors/geometry.py",
        "scripts/python/engine/dsl/base.py",
        # `Filter`, le JUMEAU natif de `FilterContinuous` (meme `FromTriggerSelector$$Select`).
        "scripts/python/engine/entities/selectors/units.py",
    ),
    "build": True,
    "toujours": False,
    "raison": "Il garde la COMPOSITION de la cle du `Cache` (quels slots, et lesquels apparient "
              "un champ natif) et le binding `ActiveTarget` des deux noeuds `Filter*`. Un "
              "changement de build peut redisposer `AbilityEntities`.",
}

from dataclasses import fields, replace                                         # noqa: E402

import pytest                                                                   # noqa: E402

from engine.dsl.base import DslContext                                          # noqa: E402
from engine.entities.selectors.geometry import (                                # noqa: E402
    Cache, FilterContinuous, _ABILITY_ENTITIES_SLOTS, _ability_entities_key)

#: Les 32 parametres du `.ctor` NOMME d'`AbilityEntities` sur le build `t6dpr4k06g`, dans
#: l'ordre de la signature (`frida/methods.tsv`). C'est la liste des CHAMPS de la structure.
CHAMPS_NATIFS = (
    "caster", "actor", "target", "owner", "casterTile", "activePlayer", "casterTiles", "effect",
    "targetTile", "targetTiles", "activeTarget", "previousActiveTarget", "currentAbilityOrEffect",
    "parentAbilityOrEffect", "triggerAbilityOrEffect", "damageReason", "damageProfile",
    "usedDamageProfiles", "appliedDamageProfiles", "healthDamage", "initialDamage", "totalDamage",
    "wasCrit", "wasBlock", "blockedHits", "wasOverkilled", "hitIndex", "hitGroupIndex",
    "isFirstDamagingHit", "movementSteps", "individualHitDamage", "hasUsedAttackDamage")

#: Les slots de la cle qui apparient EXACTEMENT un champ natif (les trois autres sont deux
#: proprietes derivees et un doublon de `active_target`).
SLOTS_APPARIES = {"actor": "actor", "caster": "caster", "target": "target", "owner": "owner",
                  "effect": "effect", "active_target": "activeTarget"}


def _u(i):
    return {"id": i, "visualId": "u%d" % i}


class _Compteur:
    def __init__(self):
        self.n = 0

    def evaluate(self, ctx):
        self.n += 1
        return [{"id": 100 + self.n}]


# --------------------------------------------------------------------------------------------
# [1] LE COMPTE -- 32 champs, et ce que la cle en couvre
# --------------------------------------------------------------------------------------------

def test_la_structure_native_porte_32_champs_pas_33():
    """L'enonce du residu disait 33 et citait `blockedHits` : il lisait une version du dump
    Il2CppDumper qui n'est pas celle du build. Le `.ctor` nomme fait foi."""
    assert len(CHAMPS_NATIFS) == 32
    assert "blockedHits" in CHAMPS_NATIFS, "le build courant PORTE `blockedHits`"
    assert "armorDamage" not in CHAMPS_NATIFS, (
        "le build courant ne porte PAS `armorDamage` -- c'est ce qui distingue son layout des "
        "deux versions du dump")


def test_la_cle_apparie_6_champs_natifs_sur_32():
    """Le chiffre qui compte n'est pas le nombre de SLOTS (9) mais le nombre de CHAMPS natifs
    reellement discrimines."""
    assert set(SLOTS_APPARIES) <= set(_ABILITY_ENTITIES_SLOTS)
    assert len(SLOTS_APPARIES) == 6
    assert set(SLOTS_APPARIES.values()) <= set(CHAMPS_NATIFS)
    non_couverts = set(CHAMPS_NATIFS) - set(SLOTS_APPARIES.values())
    assert len(non_couverts) == 26


def test_neuf_des_champs_manquants_ne_sont_PAS_du_degat():
    """« tous les champs de DEGAT manquent » etait vrai mais sous-comptait : le trou porte aussi
    sur des champs d'ENTITE et de TUILE, que le blocage `seeding` couvre pareillement."""
    hors_degat = {"previousActiveTarget", "targetTile", "targetTiles", "casterTile",
                  "casterTiles", "activePlayer", "currentAbilityOrEffect",
                  "parentAbilityOrEffect", "triggerAbilityOrEffect"}
    assert hors_degat <= (set(CHAMPS_NATIFS) - set(SLOTS_APPARIES.values()))
    assert len(hors_degat) == 9


def test_aucun_champ_manquant_n_est_seede_par_le_DslContext():
    """LE CRAN QUI JUSTIFIE `BLOCAGE: seeding`. Si l'un d'eux apparaissait au contexte, la cle
    pourrait le prendre -- et ce test le dirait au lieu de laisser dormir le residu."""
    noms = {f.name for f in fields(DslContext)}
    candidats = {"previous_active_target", "target_tile", "target_tiles", "caster_tile",
                 "caster_tiles", "active_player", "hit_index", "hit_group_index",
                 "damage_reason", "damage_profile", "was_crit", "was_block", "health_damage",
                 "total_damage", "blocked_hits", "is_first_damaging_hit", "movement_steps"}
    presents = candidats & noms
    assert not presents, (
        "le `DslContext` porte desormais %s : la cle du `Cache` peut (et doit) les prendre"
        % sorted(presents))


def test_le_slot_is_first_hit_ne_discrimine_RIEN_aujourd_hui():
    """Il est dans la cle, mais AUCUN vecteur du port ne le pose -- il vaut toujours `None`.
    Le documenter par un test evite qu'on le compte comme une couverture qu'il n'assure pas."""
    assert "is_first_hit" in _ABILITY_ENTITIES_SLOTS
    assert DslContext().is_first_hit is None
    a = DslContext(caster=_u(1))
    assert _ability_entities_key(a) == _ability_entities_key(replace(a, is_first_hit=None))


# --------------------------------------------------------------------------------------------
# [2] LE SENS DE LA FAUTE -- la cle SOUS-DISTINGUE, jamais l'inverse
# --------------------------------------------------------------------------------------------

def test_deux_contextes_qui_ne_different_que_par_un_champ_NON_COUVERT_font_un_HIT():
    """La divergence NOMMEE, rendue EXECUTABLE : le natif re-calculerait (sa cle porte le champ),
    le port sert son cache. On la garde visible plutot que de la laisser en prose."""
    src = _Compteur()
    n = Cache(src, match_ability_entities=True)
    a = DslContext(caster=_u(1), target=_u(2), times_attacked=0)
    b = replace(a, times_attacked=7)          # un champ hors des 9 slots
    assert n.evaluate(a) == n.evaluate(b)
    assert src.n == 1, "la cle portee ne distingue pas ce que le natif distinguerait"


def test_un_champ_COUVERT_fait_bien_un_MISS():
    """NON-DEGENERESCENCE du test precedent : sans ce cran, une cle constante le ferait passer."""
    src = _Compteur()
    n = Cache(src, match_ability_entities=True)
    a = DslContext(caster=_u(1), target=_u(2))
    assert n.evaluate(a) != n.evaluate(replace(a, target=_u(3)))
    assert src.n == 2


# --------------------------------------------------------------------------------------------
# [3] `FilterContinuous` -- le binding `ActiveTarget`, qui n'etait pose qu'a moitie
# --------------------------------------------------------------------------------------------

class _VoitActiveTarget:
    """Predicat qui lit `ActiveTarget()` : c'est le nom que le natif rebinde."""

    def __init__(self):
        self.vus = []

    def evaluate(self, ctx):
        self.vus.append(None if ctx.active_target is None else ctx.active_target.get("id"))
        return True


class _Source:
    def __init__(self, items):
        self.items = items

    def evaluate(self, ctx):
        return list(self.items)


def test_filter_continuous_rebinde_ACTIVE_TARGET_a_chaque_element():
    """`FromTriggerSelector$$Select` : `sub.<+0x20 ActiveTarget> = item`. Le port ne posait que
    `subject`, donc un predicat lisant `ActiveTarget()` voyait la valeur du contexte PARENT --
    ici, l'unite 99 pour les trois elements."""
    p = _VoitActiveTarget()
    items = [_u(1), _u(2), _u(3)]
    FilterContinuous(_Source(items), p).select(DslContext(caster=_u(0), active_target=_u(99)))
    assert p.vus == [1, 2, 3], "chaque element doit etre lie au slot `ActiveTarget`"


def test_filter_continuous_lie_AUSSI_le_slot_subject():
    """`Subject` et `ActiveTarget` sont deux noeuds portes du MEME selecteur natif : les deux
    call-sites portes lisent `Subject()`, donc ce cran garde la non-regression du correctif."""

    class _VoitSubject:
        def __init__(self):
            self.vus = []

        def evaluate(self, ctx):
            self.vus.append(None if ctx.subject is None else ctx.subject.get("id"))
            return True

    p = _VoitSubject()
    FilterContinuous(_Source([_u(4), _u(5)]), p).select(DslContext(caster=_u(0)))
    assert p.vus == [4, 5]


def test_filter_continuous_court_circuite_toujours_au_premier_echec():
    """Le flag `+0x28` distingue `FilterContinuous` de `Filter` -- le correctif de binding ne
    doit pas l'avoir touche."""

    class _RefuseApres:
        def __init__(self, seuil):
            self.seuil = seuil

        def evaluate(self, ctx):
            return int(ctx.subject["id"]) < self.seuil

    out = FilterContinuous(_Source([_u(1), _u(2), _u(9), _u(3)]),
                           _RefuseApres(5)).select(DslContext(caster=_u(0)))
    assert [u["id"] for u in out] == [1, 2], "prefixe CONTIGU, arret au premier echec"


def test_un_Cache_sous_un_FilterContinuous_re_calcule_par_element():
    """LA JONCTION DES DEUX VOLETS. Avec le binding a moitie pose, la cle du `Cache` ne bougeait
    que par `subject` ; elle bouge maintenant par les deux, comme sous un `Filter`."""
    src = _Compteur()
    cache = Cache(src, match_ability_entities=True)

    class _Predicat:
        def evaluate(self, ctx):
            cache.evaluate(ctx)
            return True

    FilterContinuous(_Source([_u(1), _u(2), _u(3)]), _Predicat()).select(DslContext(caster=_u(0)))
    assert src.n == 3, "un element = un contexte = un MISS"
