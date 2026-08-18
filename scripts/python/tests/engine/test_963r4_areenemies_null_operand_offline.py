"""#963-r4 -- la RESOLUTION DES OPERANDES d'`AreFriends` / `AreEnemies` : UNE entite, pas un produit.

Ce que le residu demandait de fermer, et ce que la relecture du binaire a CORRIGE en chemin :

  * `IdunBattle.Entities.Triggers.AreFriendsAbilityTrigger$$ShouldTrigger` resout CHAQUE operande
    par **UN SEUL** appel de selecteur et rend FAUX des que l'un rend `null` ; le port faisait un
    `any` sur le PRODUIT des deux listes, donc plus permissif des qu'un operande en rend plusieurs.
  * Le nom << SelectSingle >> ecrit par #963-r1 **n'existe dans aucun symbole du build** : le slot
    d'interface appele est le **8** d'`ITargetsSelector`, c'est-a-dire
    `IdunBattle.DSL.TargetsSelector$$SelectActor(entities, selectionType)`.
  * Le 2e argument de ce `SelectActor` est **INVISIBLE au pseudo-C** (Ghidra n'affiche que 4
    arguments du trampoline d'invocation d'interface). Il est ecrit par `mov [rsp+0x20], edi` juste
    apres la boucle de copie de l'`AbilityEntities`, dont `edi` est le compteur -- et la boucle
    finit par `sub rdi,1 ; jne`, donc `edi == 0` = `UnitSelectionType.Any`. LU A L'ASSEMBLEUR.
  * Le 4e argument natif `anyEntity` choisit la CLASSE : `false` ->
    `AreFriendsAbilityTrigger` (slot 8), `true` -> `IdunBattle.Entities.Triggers.
    AreEntityFriendsAbilityTrigger`, MEME corps au slot **1** = `SelectFirst`. Les deux passent par
    le MEME `$$.ctor` -- corps trivial DEDUPLIQUE par IL2CPP, a ne jamais lire comme une identite
    de classe.
  * `IdunBattleLogic.Entities.DSLTriggers$$AreEnemies` enveloppe TOUJOURS la variante `anyEntity =
    false` dans `IdunBattle.DSL.NegatedAbilityTrigger`, dont le `ShouldTrigger` est une negation
    NUE (`return inner.ShouldTrigger(entities) ^ 1`). Donc un operande vide rend **VRAI** a
    `AreEnemies`, la ou le port rendait FAUX des deux cotes.

Ce que ce fichier garde, et pourquoi chaque etage existe :

  1. Le SLOT d'interface, lu dans l'entree VERSIONNEE `metadata/interface_slots.tsv` : c'est la
     seule affirmation de RE que ce fichier peut confronter sans le jeu, et elle rougira au
     changement de build si la table bouge.
  2. Le regime DISCRIMINANT de la resolution : un operande qui rend PLUSIEURS unites. L'ancien
     `any` sur le produit y rendait VRAI, le mirror rend FAUX.
  3. La bascule d'`AreEnemies` sur un operande NUL (l'ecart que le residu nommait).
  4. La degradation << equipe NON MESUREE >> reste FERMEE **des deux cotes** -- c'est le piege de
     la bascule : nier un verdict qu'on n'a pas mesure fabriquerait un VRAI a partir d'un trou.
  5. La NON-REGRESSION des call-sites portes, sur l'arbre REEL (`DarkTalonStrikeAbility$$
     GetTilesInLine`) et un board NON DEGENERE (une tuile occupee ET une tuile vide) : le
     `HasUnit(subject)` de tete rend la bascule inerte, et c'est MESURE, pas suppose.

ASCII only (console Windows cp1252).
"""
from __future__ import annotations

DECLENCHEUR = {
    # Le foyer edite, ses deux consommateurs tile-domain, et le foyer d'equipe qu'il appelle.
    "chemins": ("scripts/python/engine/entities/triggers.py",
                "scripts/python/engine/entities/unit_team_selection_type.py",
                "scripts/python/engine/runner/abilities/darkangels.py",
                "scripts/python/engine/runner/abilities/sisterhood.py",
                "scripts/python/engine/entities/abilities/active_ability.py",
                "scripts/python/tests/engine/test_963r4_areenemies_null_operand_offline.py"),
    # `build: True` -- l'etage 1 lit `data/symbols/<build>/metadata/interface_slots.tsv`, entree
    # VERSIONNEE et donc specifique au build. Un changement de build doit le rejouer.
    "build": True,
    # `toujours: False` : perimetre etroit ET mesure -- les 5 etages sont purement offline et
    # instantanes, mais ils ne peuvent rougir que si l'un des chemins ci-dessus bouge.
    "toujours": False,
    "raison": "Resolution des operandes d'`AreFriends`/`AreEnemies` (slot 8 `SelectActor`, un seul "
              "couple compare, operande nul -> FAUX / negation NUE cote `AreEnemies`), et "
              "non-regression des call-sites tile-domain qui la consomment.",
}

from pathlib import Path

import pytest

# FORME B (module + acces attributaire) : le foyer UNIQUE des chemins d'artefact par build.
import build_pin
from engine.entities.selectors.accessors import Target
from engine.entities.selectors.tiles import Caster
from engine.entities.triggers import AreEnemies, AreFriends
from engine.entities.unit_team_selection_type import UnitTeamSelectionType

RACINE = Path(__file__).resolve().parents[4]      # <racine depot>/scripts/python/tests/engine/<ici>

#: Les DEUX slots d'`ITargetsSelector` que la relecture #963-r4 met en jeu, avec la classe de
#: trigger que chacun sert. Ecrits par leur SYMBOLE, jamais par une VA.
SLOTS_ATTENDUS = {
    # `anyEntity == false` -> `IdunBattle.Entities.Triggers.AreFriendsAbilityTrigger`
    8: "SelectActor",
    # `anyEntity == true`  -> `IdunBattle.Entities.Triggers.AreEntityFriendsAbilityTrigger`
    1: "SelectFirst",
}


# ---------------------------------------------------------------------------------------------
# FIXTURES NOMMEES
# ---------------------------------------------------------------------------------------------
class _Ctx:
    """Contexte DSL minimal. `Caster()` lit `ctx.caster`, `Target()` lit `ctx.target`."""

    def __init__(self, **kw):
        for k, v in kw.items():
            setattr(self, k, v)

    def __getattr__(self, _n):
        return None


class _Liste:
    """Selecteur-STUB qui rend telle quelle la liste qu'on lui donne.

    Il ne remplace AUCUN selecteur porte : il sert a produire le regime << un operande rend
    PLUSIEURS unites >>, que les selecteurs mono-unite du port (`Caster`, `Target`, `Owner`,
    `Actor`) ne peuvent pas produire. C'est l'entree du noeud qu'on fabrique, pas sa logique."""

    def __init__(self, items):
        self.items = items

    def evaluate(self, _ctx):
        return list(self.items)


@pytest.fixture(name="deux_equipes")
def _deux_equipes():
    """Trois unites : `a1`/`a2` en equipe 1, `e1` en equipe 2. Rend le triplet."""
    a1 = {"id": 1, "team": 1}
    a2 = {"id": 2, "team": 1}
    e1 = {"id": 3, "team": 2}
    assert a1["team"] == a2["team"] != e1["team"], \
        "regime DEGENERE : il faut DEUX equipes distinctes pour que les deux noeuds discriminent"
    return a1, a2, e1


@pytest.fixture(name="ligne_occupee")
def _ligne_occupee():
    """Un board LIGNE de 4 tuiles, l'ennemi sur la tuile `2`, les tuiles `3`/`4` VIDES.

    Regime NON DEGENERE exige par l'etage 5 : sans une tuile occupee, le predicat complet rendrait
    FAUX partout et l'accord avant/apres ne prouverait rien.

    Rend `(ctx, tuile_occupee, tuile_vide)`."""
    from engine.entities.pathfinding.board import Board

    tiles = [{"id": i, "col": i - 1, "row": 0, "walkable": True, "elevation": 0} for i in range(1, 5)]
    board = Board(tiles)
    # `hp > 0` est ce que `dsl.base._is_alive` exige pour qu'une unite OCCUPE sa tuile.
    caster = {"id": 10, "team": 1, "pos": {"col": 0, "row": 0}, "alive": True, "hp": 100, "hpMax": 100}
    ennemi = {"id": 11, "team": 2, "pos": {"col": 1, "row": 0}, "alive": True, "hp": 100, "hpMax": 100}
    ctx = _Ctx(board=board, units=[caster, ennemi], caster=caster, target=ennemi)
    return ctx, 2, 4


# ---------------------------------------------------------------------------------------------
# ETAGE 1 -- LE SLOT, lu dans l'entree VERSIONNEE
# ---------------------------------------------------------------------------------------------
def test_les_deux_slots_d_itargetsselector_sont_ceux_qu_on_a_lus():
    """La table `metadata/interface_slots.tsv` est DERIVEE de `global-metadata.dat` du build.

    Sans cet etage, l'affirmation << le slot 8 est `SelectActor` >> ne serait qu'une phrase de
    docstring ; avec lui, elle rougit si le build renumerote l'interface."""
    # #10027 -- le build se DEMANDE, il ne s'ecrit pas. La ligne d'avant lisait le marqueur `BUILD`
    # DANS `data/symbols/rnca9r7q6c/` : un chemin en dur qui court-circuite `data/symbols/CURRENT`.
    # Elle a survecu a deux mises a jour du jeu, si bien que ce test confrontait les slots ATTENDUS
    # a la table d'un binaire qui n'est plus charge -- son vert ne disait plus rien du build courant,
    # ce qui est exactement l'inverse de ce que sa docstring promet.
    build = build_pin.versioned_build()
    tsv = build_pin.build_dir(build) / "metadata" / "interface_slots.tsv"
    assert tsv.exists(), "table de slots ABSENTE pour le build %s -- NON MESURE" % build
    lus = {}
    for ligne in tsv.read_text(encoding="utf-8").splitlines():
        if ligne.startswith("#"):
            continue
        cols = ligne.split("\t")
        if len(cols) >= 3 and cols[0] == "ITargetsSelector":
            lus[int(cols[1])] = cols[2]
    assert lus, "aucun slot `ITargetsSelector` lu -- le test s'auto-invalide (perimetre VIDE)"
    for slot, nom in SLOTS_ATTENDUS.items():
        assert lus.get(slot) == nom, \
            "ITargetsSelector slot %d = %r, attendu %r" % (slot, lus.get(slot), nom)


# ---------------------------------------------------------------------------------------------
# ETAGE 2 -- LE REGIME DISCRIMINANT : un operande qui rend PLUSIEURS unites
# ---------------------------------------------------------------------------------------------
def test_arefriends_ne_compare_QUE_le_premier_de_chaque_operande(deux_equipes):
    """L'ancien port faisait `any(x == y for x in A for y in B)` : le couple `(a2, a2)` suffisait a
    rendre VRAI. Le natif ne compare QUE `(SelectActor(A), SelectActor(B))` = `(e1, a2)`."""
    a1, a2, e1 = deux_equipes
    ctx = _Ctx()
    noeud = AreFriends(_Liste([e1, a2]), _Liste([a2, e1]))
    assert noeud.evaluate(ctx) is False, (
        "le noeud doit comparer le PREMIER de chaque operande (e1 team 2 vs a2 team 1) ; "
        "un `any` sur le produit rendrait VRAI par le couple (a2, a2)")
    # TEMOIN NON NUL, meme entree a l'ordre pres : si les deux tetes concordent, c'est VRAI.
    assert AreFriends(_Liste([a1, e1]), _Liste([a2, e1])).evaluate(ctx) is True, \
        "temoin NUL : le noeud doit savoir rendre VRAI sur ce meme montage"


def test_areenemies_ne_compare_QUE_le_premier_de_chaque_operande(deux_equipes):
    """Miroir exact -- l'ancien `any` y rendait VRAI par le couple `(a2, e1)`."""
    a1, a2, e1 = deux_equipes
    ctx = _Ctx()
    assert AreEnemies(_Liste([a1, e1]), _Liste([a2, e1])).evaluate(ctx) is False, (
        "les deux tetes sont de la MEME equipe : `AreEnemies` doit rendre FAUX ; un `any` sur le "
        "produit rendrait VRAI par le couple (a1, e1)")
    assert AreEnemies(_Liste([e1, a2]), _Liste([a2, e1])).evaluate(ctx) is True, \
        "temoin NUL : le noeud doit savoir rendre VRAI sur ce meme montage"


# ---------------------------------------------------------------------------------------------
# ETAGE 3 -- L'OPERANDE NUL : `AreFriends` FAUX, donc `AreEnemies` VRAI
# ---------------------------------------------------------------------------------------------
@pytest.mark.parametrize("vide,plein", [("a", "b"), ("b", "a")])
def test_un_operande_vide_rend_FAUX_a_arefriends_et_VRAI_a_areenemies(deux_equipes, vide, plein):
    """`if (a == null) return false;` puis `NegatedAbilityTrigger` = negation NUE.

    Les DEUX positions sont couvertes : le natif teste `+0x10` AVANT `+0x18`, mais les deux
    retours sont le meme `return false`."""
    a1, _a2, _e1 = deux_equipes
    ctx = _Ctx()
    ops = {vide: _Liste([]), plein: _Liste([a1])}
    assert AreFriends(ops["a"], ops["b"]).evaluate(ctx) is False
    assert AreEnemies(ops["a"], ops["b"]).evaluate(ctx) is True, (
        "AVANT #963-r4 le port rendait FAUX des deux cotes ; le natif nie un FAUX **mesure**")


def test_un_operande_qui_ne_rend_aucune_UNITE_compte_comme_nul(deux_equipes):
    """`SelectActor` ne rend que des entites qui RESOLVENT en unite (ou une machine) ; une liste
    d'ids de tuile ne resout rien dans le domaine du port -> operande nul."""
    a1, _a2, _e1 = deux_equipes
    ctx = _Ctx()
    assert AreFriends(_Liste([3, 4]), _Liste([a1])).evaluate(ctx) is False
    assert AreEnemies(_Liste([3, 4]), _Liste([a1])).evaluate(ctx) is True


# ---------------------------------------------------------------------------------------------
# ETAGE 4 -- L'EQUIPE NON MESUREE reste FERMEE DES DEUX COTES
# ---------------------------------------------------------------------------------------------
def test_une_equipe_NON_MESUREE_ne_bascule_pas_areenemies():
    """LE PIEGE de la bascule. `team_for_selection` rend `None` quand le substrat ne publie pas
    l'equipe -- ce n'est PAS le `return false` natif, c'est un TROU du port. Le nier fabriquerait
    un VRAI a partir d'une absence de mesure ; les deux noeuds restent donc FERMES.

    L'ecart natif correspondant (un joueur absent est rabattu sur `teamId = 0`, donc deux unites
    sans joueur y sont AMIES) est nomme dans `entities/unit_team_selection_type.py`, pas devine."""
    ctx = _Ctx()
    sans = {"id": 20}                    # aucune cle `team`
    avec = {"id": 21, "team": 1}
    assert AreFriends(_Liste([sans]), _Liste([avec])).evaluate(ctx) is False
    assert AreEnemies(_Liste([sans]), _Liste([avec])).evaluate(ctx) is False, \
        "equipe NON MESUREE : FERME des deux cotes -- surtout pas un VRAI fabrique"
    # TEMOIN NON NUL : le meme montage, equipe publiee, discrimine bien.
    avec2 = {"id": 22, "team": 2}
    assert AreEnemies(_Liste([avec2]), _Liste([avec])).evaluate(ctx) is True


def test_un_selectionType_HORS_enum_reste_FERME_des_deux_cotes():
    """`IsFriend` a une 3e branche `return false`, qu'aucun call-site natif n'emprunte (#963-r1).
    Le port la rabat sur `None` (non mesure) ; on FIGE le fait qu'elle ne bascule pas `AreEnemies`,
    sinon un litteral aberrant ouvrirait un predicat au lieu de le fermer."""
    ctx = _Ctx()
    u1, u2 = {"id": 30, "team": 1}, {"id": 31, "team": 2}
    assert AreFriends(_Liste([u1]), _Liste([u2]), 7).evaluate(ctx) is False
    assert AreEnemies(_Liste([u1]), _Liste([u2]), 7).evaluate(ctx) is False


# ---------------------------------------------------------------------------------------------
# ETAGE 5 -- NON-REGRESSION des call-sites portes, sur l'arbre REEL
# ---------------------------------------------------------------------------------------------
def test_l_arbre_DarkTalonStrike_est_inchange_par_la_bascule(ligne_occupee):
    """`DarkTalonStrikeAbility$$GetTilesInLine` = `HasUnit(subject) & AreEnemies(Caster,
    Units(subject))`. Le `HasUnit` de tete est ce qui rend la bascule inerte -- on le MESURE sur
    l'arbre REEL, avec un board qui porte une tuile OCCUPEE **et** une tuile VIDE.

    Sans la tuile occupee, les deux regimes rendraient FAUX partout : accord en regime DEGENERE,
    donc zero preuve."""
    from engine.runner.abilities.darkangels import dark_talon_get_tiles_in_line

    ctx, occupee, vide = ligne_occupee
    pred = dark_talon_get_tiles_in_line(Target(), Caster()).predicate
    noeuds = [n for n in vars(pred).values() if isinstance(n, AreEnemies)]
    assert len(noeuds) == 1, "l'arbre doit porter exactement un `AreEnemies` (perimetre auto-verifie)"

    ctx.subject = occupee
    assert pred.evaluate(ctx) is True, \
        "TEMOIN NON NUL : sur la tuile OCCUPEE par un ennemi, le predicat complet doit rendre VRAI"
    # Le terme `AreEnemies` SEUL, sur la tuile VIDE, a bien BASCULE -- c'est ce qui rend le test
    # non trivial : l'inertie vient du `HasUnit`, pas d'une absence de changement.
    ctx.subject = vide
    assert noeuds[0].evaluate(ctx) is True, \
        "sur une tuile VIDE, `AreEnemies` seul rend desormais VRAI (operande nul, negation NUE)"
    assert pred.evaluate(ctx) is False, \
        "le predicat COMPLET reste FAUX : `HasUnit(subject)` garde le call-site"
