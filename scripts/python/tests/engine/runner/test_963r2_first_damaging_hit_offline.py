"""#963-r2 -- `isFirstDamagingHit` est un ETAT DE PORTEE ATTAQUE, pas un index de coup.

`IdunBattle.Entities.Triggers.IsFirstDamagingHitInSeriesTrigger$$ShouldTrigger` lit
`AbilityEntities+0x118` -- un `Nullable<bool>` SANS getter (`HasValue` puis `get_Value` ; un
Nullable vide vaut FAUX). C'est le 29e parametre nomme du ctor `AbilityEntities$$.ctor`, distinct
de ses deux voisins `+0x108` (`IsFirstHit`, = `hitIndex == 0`) et `+0x110` (`IsFirstHitGroup`).

CE QUE LA RE-MESURE A CHANGE DANS L'ENONCE DU RESIDU
----------------------------------------------------
#963-r2 affirmait : « si le coup d'index 0 inflige 0 (bloque entierement), le port ne marque AUCUN
groupe ». **C'est inexact.** Le port emet `On(PreDamageTaken = 0x39)` sous le gate `total > 0` du
GROUPE : un groupe dont le coup 0 est bloque mais dont un coup suivant damage emettait DEJA avec le
flag vrai. Le trou reel est plus etroit d'un cran -- il faut que le groupe portant l'index 0 soit
ENTIEREMENT a zero (donc n'emette rien du tout), et qu'un groupe SUIVANT damage : ce second groupe
ne contient pas l'index 0, donc `is_first_hit` y est FAUX, la ou le natif marque le premier coup
damageant.

D'ou la reparation : un etat threade de portee ATTAQUE (`damaging_done`), jumeau de `crit_allowed`
(`OngoingAttack+0x40`) et de `failed_block` (`OngoingAttack+0x48`) -- et NON une derivation de
l'index de coup.

CE QUI N'EST PAS COUVERT ICI
----------------------------
La confrontation LIVE du regime (phase d'arme entierement bloquee + groupe additionnel damageant +
un porteur de `On(PreDamageTaken)`, c'est-a-dire `GeminaeSuperia`) n'est pas montee : elle exige un
`--block-target` total sur la salve d'arme ET un descripteur #179 actif sur le meme attaquant. Ce
fichier garde la FORME du threading, pas sa valeur observee.
"""
from __future__ import annotations

DECLENCHEUR = {
    "chemins": (
        # Le chokepoint qui EMET, et qui porte le repli `is_first_hit` quand rien n'est threade.
        "scripts/python/engine/runner/operations/damage.py",
        # Le porteur du threading (etat d'attaque + sortie `damaging_done`).
        "scripts/python/engine/runner/operations/additional_hits.py",
        # Les deux vecteurs qui MESURENT l'etat d'entree sur leur propre total d'arme.
        "scripts/python/engine/runner/operations/damage_ops/normal.py",
        "scripts/python/engine/runner/operations/damage_ops/ability.py",
    ),
    "build": False,
    "toujours": False,
    "raison": "CES chemins parce que ce fichier est un cliquet de FORME : il n'execute aucune "
              "bataille et ne fige aucune valeur -- il `ast.parse` les quatre modules qui portent "
              "le threading de `isFirstDamagingHit`, et sa verite depend EXACTEMENT de leur "
              "source. `build: False` : aucune adresse, aucun symbole, aucune valeur de config "
              "n'est lue ; les references natives sont CITEES en prose.",
}

import ast
import inspect
import pathlib

from engine.runner.operations.additional_hits import execute_additional_hits
from engine.runner.operations.damage import AttackDamageOperation

_OPS = pathlib.Path(__file__).resolve().parents[3] / "engine" / "runner" / "operations"


def _arbre(rel):
    return ast.parse((_OPS / rel).read_text(encoding="utf-8"))


# ------------------------------------------------- etage 1 : le canal existe et il est DISTINCT

def test_le_chokepoint_expose_un_flag_PROPRE_distinct_de_l_index():
    """`is_first_damaging_hit` ne doit pas etre un alias de `is_first_hit` : ce sont deux champs
    natifs differents (`+0x118` contre `+0x108`)."""
    p = inspect.signature(AttackDamageOperation._apply_damage_pipeline).parameters
    assert "is_first_damaging_hit" in p, "le chokepoint n'expose pas le flag `+0x118`"
    assert "is_first_hit" in p
    assert p["is_first_damaging_hit"].default is None, \
        "le defaut doit etre None (= non threade), pour que le repli soit explicite"


def test_le_threading_expose_son_etat_d_entree_et_de_sortie():
    """Jumeau de `crit_allowed0`/`crit_allowed` et de `failed_block0`/`failed_block`."""
    assert "damaging_done0" in inspect.signature(execute_additional_hits).parameters
    src = (_OPS / "additional_hits.py").read_text(encoding="utf-8")
    assert 'out["damaging_done"]' in src, \
        "l'etat de sortie n'est pas publie -- un appelant ne peut pas le chainer"


# ------------------------------------------- etage 2 : le REPLI preserve l'ancien comportement

class _Espion:
    """Substitut du module `triggers.dispatch.attack` : `_pre_damage_taken_per_hit` le recoit en
    ARGUMENT, donc rien (forme d'import, refactoring) ne peut desarmer l'observation."""

    def __init__(self, thc=None):
        self.flags = []
        self.hp_vus = []
        self.thc = thc

    def pre_damage_taken_triggers(self, state, source_id, target_id, profile=None,
                                  is_first_damaging_hit=None, source_ability=None):
        # `source_ability` (#1020-r3) = le canal `AbilityEntities+0x98`, ignore par CETTE garde
        # (elle mesure `isFirstDamagingHit`) mais present au contrat du vecteur.
        self.flags.append(is_first_damaging_hit)
        if self.thc is not None:
            self.hp_vus.append(self.thc.hp)
        return []


def _emet(pend, total, first_hit=None, first_damaging=None, thc=None):
    """Joue le chokepoint tel qu'il est CABLE (l'appelant passe `is_first_hit` et, s'il le thread,
    `is_first_damaging_hit`) et rend l'espion."""
    from engine.runner.components import HealthComponent
    thc = thc if thc is not None else HealthComponent(hp=1000, hp_max=1000)
    esp = _Espion(thc)
    AttackDamageOperation._pre_damage_taken_per_hit(
        None, 1, 2, thc, total, 0, "Physical", {"per_hit_pending": pend}, esp,
        is_first_damaging_hit=(first_hit if first_damaging is None else first_damaging))
    return esp


def test_le_repli_sur_is_first_hit_est_EXPLICITE_dans_l_emission():
    """Un appelant qui ne thread pas le flag doit retomber EXACTEMENT sur l'ancien comportement
    (`is_first_hit`), sinon la reparation serait une regression pour les vecteurs sans
    sous-operations.

    ⚠ CE TEST A ETE REECRIT (#1020). Il confrontait l'AST de l'appel et exigeait un `ast.IfExp`
    LITTERALEMENT a l'argument `is_first_damaging_hit=` de `pre_damage_taken_triggers`. C'etait une
    approximation SYNTAXIQUE de l'invariant, et elle a rougi des que l'emission est passee PAR COUP
    (le repli existe toujours, un cran plus haut, a l'appel de `_pre_damage_taken_per_hit`). Une
    garde qui rougit sur un refactoring FIDELE et se tairait sur un repli SUPPRIME ne garde pas le
    bon fait : on confronte donc le COMPORTEMENT -- `is_first_damaging_hit=None` doit rendre
    exactement ce que rendait `is_first_hit`.

    Les deux valeurs de `is_first_hit` sont exercees, sinon un port qui renverrait toujours `True`
    (ou toujours `False`) passerait."""
    for first_hit in (True, False):
        esp = _emet([(300, 0)], 300, first_hit=first_hit, first_damaging=None)
        assert esp.flags == [first_hit], (
            "repli ROMPU : appelant qui ne thread PAS `is_first_damaging_hit` avec "
            "`is_first_hit=%r` -> flag emis %r, attendu [%r]" % (first_hit, esp.flags, first_hit))
    # et quand l'appelant le thread, c'est LUI qui gagne (jamais `is_first_hit`)
    esp = _emet([(300, 0)], 300, first_hit=True, first_damaging=False)
    assert esp.flags == [False], (
        "l'etat THREADE doit primer sur le repli : flags %r" % (esp.flags,))


def test_le_vecteur_part_avant_toute_mutation_de_PV():
    """L'INVARIANT que gardait la comparaison de numeros de ligne de #963 (`pre_damage_taken_triggers`
    AVANT `applied = thc.reduce(total)`), reformule en COMPORTEMENT -- donc insensible au
    refactoring et sensible au vrai defaut.

    Lu aux octets dans `IdunBattle.Operations.ApplyDamageOperation$$Execute` : la publication de
    `On(0x39 = EventTriggerType.PreDamageTaken)` precede `FillUpStatComponent$$Reduce`. C'est ce qui
    permet a `GeminaeSuperia` d'apparaitre alors que Celestine est **encore a pleine vie**, et a
    `SaviorProtocols` de detourner un degat qui n'a pas encore ete encaisse."""
    from engine.runner.components import HealthComponent
    thc = HealthComponent(hp=1000, hp_max=1000)
    esp = _emet([(300, 0), (250, 0)], 550, first_hit=True, thc=thc)
    assert esp.hp_vus == [1000, 1000], (
        "la victime avait deja perdu des PV quand `On(0x39)` est parti (PV vus : %r) -- "
        "l'event doit PRECEDER `FillUpStatComponent$$Reduce`" % (esp.hp_vus,))
    assert thc.hp == 1000, (
        "l'etage d'emission ne doit muter AUCUN PV : c'est l'appelant qui reduit, avec ce que le "
        "pending RELU porte")


# ------------------------------------ etage 3 : le flag n'est PAS derive de l'index dans la boucle

def test_le_groupe_ne_derive_PLUS_le_flag_de_l_index_de_coup():
    """LE cran. Dans `additional_hits.py`, `is_first_damaging_hit` doit venir de l'etat threade, PAS
    de `g_first_hit` (qui, lui, ne parle que de l'index 0). Les rebrancher l'un sur l'autre
    rouvrirait le residu en silence."""
    arbre = _arbre("additional_hits.py")
    appels = [n for n in ast.walk(arbre)
              if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)
              and n.func.attr == "_apply_damage_pipeline"]
    assert appels, "aucun appel au chokepoint"
    for appel in appels:
        kw = {k.arg: k.value for k in appel.keywords if k.arg}
        assert "is_first_damaging_hit" in kw, "le groupe n'envoie pas le flag `+0x118`"
        noms = {n.id for n in ast.walk(kw["is_first_damaging_hit"]) if isinstance(n, ast.Name)}
        assert "g_first_hit" not in noms, \
            "le flag est REDERIVE de l'index de coup -- c'est le defaut de #963-r2"
        assert "_damaging_done" in noms, "le flag ne vient pas de l'etat threade"


def test_l_etat_ne_bascule_QUE_sur_un_groupe_qui_damage():
    """`_damaging_done` doit passer a True sous un gate `total > 0`, et APRES l'emission du groupe
    courant -- sinon le groupe qui damage le premier se marquerait lui-meme comme « pas le
    premier »."""
    src = (_OPS / "additional_hits.py").read_text(encoding="utf-8").splitlines()
    i_emission = next(i for i, l in enumerate(src) if "is_first_damaging_hit=(not _damaging_done)" in l)
    i_bascule = next(i for i, l in enumerate(src) if "_damaging_done = True" in l)
    assert i_bascule > i_emission, \
        "l'etat bascule AVANT l'emission : le premier groupe damageant se verrait FAUX"
    assert 'if int(r["total"] or 0) > 0:' in src[i_bascule - 1], \
        "la bascule n'est pas gatee par « ce groupe a inflige du degat »"


# ---------------------------------------------- etage 4 : les deux vecteurs MESURENT l'entree

def test_les_deux_vecteurs_alimentent_l_etat_d_entree():
    """Un vecteur qui ne passe pas `damaging_done0` laisserait l'etat a False : le premier groupe
    additionnel se croirait le premier a damager alors que la phase d'arme a deja frappe --
    degradation PERMISSIVE, celle qui ne se voit pas."""
    for vecteur in ("normal.py", "ability.py"):
        arbre = _arbre(pathlib.Path("damage_ops") / vecteur)
        appels = [n for n in ast.walk(arbre)
                  if isinstance(n, ast.Call) and isinstance(n.func, ast.Name)
                  and n.func.id == "execute_additional_hits"]
        assert appels, "%s : aucun appel a `execute_additional_hits`" % vecteur
        for appel in appels:
            kw = {k.arg: k.value for k in appel.keywords if k.arg}
            assert "damaging_done0" in kw, \
                "%s : `damaging_done0` non passe -- #963-r2 rouvert (sens PERMISSIF)" % vecteur
            assert isinstance(kw["damaging_done0"], ast.Compare), \
                "%s : `damaging_done0` n'est pas une comparaison sur le total" % vecteur
