"""#889-r6 -- les quatre litteraux de `1215 InstrumentsOfVengeance` qu'un port peut inverser EN
SILENCE, et les deux noeuds neufs qui les portent.

CE QUE CE FICHIER GARDE, et pourquoi chaque cran existe
=======================================================

`IdunBattleLogic.Entities.Abilities.Active.Loki.InstrumentsOfVengeanceAbility$$ExecuteBehaviour`
n'ecrit AUCUN degat : il choisit deux lignes de tir, les MARQUE, et arme une phase 2. Rien de ce
qu'il fait ne se lit dans un total de degat -- donc rien ne le confronte par un scalaire. Ce qui
peut casser en silence, c'est la STRUCTURE :

  * **le SENS des trois tris chaines** (`ascending` = `0, 1, 0` au call-site). Ils sont STABLES et
    chaines, donc le DERNIER est la cle PRIMAIRE ; inverser celui des AMIS (le seul a `1`) choisit
    la ligne qui couvre le PLUS d'allies au lieu du MOINS, et l'ensemble des tuiles marquees reste
    de MEME TAILLE -- une garde qui compterait les marques ne verrait rien.
    ⚠ `docs/rl/case-1022` §7 ecrivait `desc` sur ce tri-la. C'est la faute que ce cran attrape.
  * **l'INDICE des cles persistantes** : la 1re passe ecrit `0`, la 2e RELIT `0` puis ecrit `1`.
    Ecrire `idx` a la lecture (au lieu du litteral `0`) ferait relire une cle vide, et les deux
    lignes pourraient se SUPERPOSER -- sans erreur, sans marque manquante.
  * **`EdgeExtensions$$Rotate(direction, 3)`** : trois crans = l'arete OPPOSEE. Confondre avec
    `EdgeExtensions$$Next` (un cran, sens porte par un bool) fait partir la ligne le long du bord
    au lieu de traverser le plateau.
  * **le masque `0x8004`** : `1215` recopie le MEME preset que `1216` mais SANS le
    `additionalRules = 0x10`, donc SANS `CasterHasNotMoved`. Recopier le masque de 1216 rendrait
    1215 INCASTABLE apres deplacement -- et sa face DECISION est POSITION-DEPENDANTE (#27-r6).

Et un cran de NON-REGRESSION en sens inverse : `1519` ne doit PAS entrer dans
`PENDING_ATTACK_EFFECTS` tant que la phase 2 n'est pas portee (residu `#889-r6-r1`). L'y mettre
ferait firer `TriggerAbility(1519)` sur une ability triggered absente, et son `RemoveEffect`
consommerait la marque -- un no-op silencieux de plus.

ASCII only.
"""
from __future__ import annotations

DECLENCHEUR = {
    "chemins": (
        "scripts/python/engine/hex_edge.py",
        "scripts/python/engine/entities/selectors/geometry.py",
        "scripts/python/engine/entities/selectors/tiles.py",
        "scripts/python/engine/entities/formulas.py",
        "scripts/python/engine/runner/abilities/loki/instruments_of_vengeance.py",
        "scripts/python/engine/runner/abilities/handler.py",
        "scripts/python/engine/runner/abilities/attack_type.py",
        "scripts/python/engine/runner/abilities/targeting.py",
        "scripts/python/engine/runner/operations/triggers/pending_attack.py",
    ),
    "build": False,
    "toujours": False,
    "raison": "Fichier OFFLINE et court (aucun runner, aucun RPC). Le perimetre est la CASCADE du "
              "port de 1215 : le module d'ability, les deux noeuds neufs qu'il consomme "
              "(`EdgeTilesByDirection`, `hex_edge.rotate`), les deux normalisations de domaine "
              "mixte qu'il a exigees (`EntityId`, `TileUnion`), les trois registres ou il entre, "
              "et le foyer `pending_attack.py` -- parce qu'un cran garde precisement l'ABSENCE de "
              "1519 dans sa table. `build: False` : rien n'est fige depuis le binaire, ce sont "
              "les litteraux du decompile cites au site qui tiennent, pas une table generee.",
}

import pytest

from engine.dsl import nodes as dsl
from engine.entities.active_ability_type import ActiveAbilityType
from engine.entities.effect_type import EffectType
from engine.entities.pathfinding.board import Board
from engine.entities.selectors.geometry import EdgeTilesByDirection
from engine.entities.selectors.tiles import TileUnion
from engine.entities.selectors.units import SortByFormula
from engine.hex_edge import Edge, rotate
from engine.runner.abilities.attack_type import ABILITY_ATTACK_TYPE, AbilityAttackType
from engine.runner.abilities.behaviours.persistent_data import SetPersistentData
from engine.runner.abilities.handler import ABILITY_CLASSES
from engine.runner.abilities.loki.instruments_of_vengeance import (
    IOV_ABILITY, IOV_KEY_DIRECTION_TILE, IOV_KEY_TARGET_TILE, IOV_LOCATION_TARGET,
    IOV_PENDING_ATTACK, InstrumentsOfVengeanceAbility, instruments_of_vengeance_effect_behavior)
from engine.runner.abilities.targeting import TARGETING_OPTIONS_UNPORTED
from engine.runner.abilities.targeting_rule import TargetingRule as TR
from engine.runner.operations.triggers.pending_attack import PENDING_ATTACK_EFFECTS

#: Un plateau RECTANGULAIRE 4 colonnes x 3 lignes, ids CROISSANTS colonne par colonne.
_COLS, _ROWS = 4, 3


def _board():
    tiles = [{"id": 100 + c * _ROWS + r, "col": c, "row": r, "neighbours": []}
             for c in range(_COLS) for r in range(_ROWS)]
    return Board(tiles)


def _ctx(**kw):
    return dsl.DslContext(units=[], board=_board(), **kw)


# ------------------------------------------------------------------------------------------------
# 1. `IdunBattle.Utils.Hex.EdgeExtensions$$Rotate`
# ------------------------------------------------------------------------------------------------

def test_rotate_de_trois_crans_donne_l_arete_opposee():
    """`Rotate(edge, 3)` = `(edge + 3) % 6` -- l'arete DIAMETRALEMENT opposee, pour les SIX.

    Les quatre premieres lignes sont les call-sites REELS de
    `...InstrumentsOfVengeanceAbility$$GetEffectBehavior` : `1 -> 4`, `5 -> 2`, `2 -> 5`, `4 -> 1`.
    Les deux autres ferment l'enum. Un `Next` (un seul cran) rendrait `2, 0, 3, 5` -- aucun ne
    coincide, donc ce cran separe bien les deux fonctions natives."""
    assert rotate(Edge.North_East, 3) == int(Edge.South_West)     # 1 -> 4
    assert rotate(Edge.North_West, 3) == int(Edge.South_East)     # 5 -> 2
    assert rotate(Edge.South_East, 3) == int(Edge.North_West)     # 2 -> 5
    assert rotate(Edge.South_West, 3) == int(Edge.North_East)     # 4 -> 1
    assert rotate(Edge.North, 3) == int(Edge.South)               # 0 -> 3
    assert rotate(Edge.South, 3) == int(Edge.North)               # 3 -> 0
    # L'involution : deux fois trois crans ramenent au point de depart, pour les six.
    assert [rotate(rotate(e, 3), 3) for e in Edge] == [int(e) for e in Edge]


def test_rotate_tronque_vers_zero_comme_le_remainder_c_sharp():
    """Le corps natif est un `%` sur `int` SIGNE -- quotient TRONQUE VERS ZERO. Sur une somme
    negative, `%` de Python (plancher) donnerait un AUTRE resultat, et le mirror serait faux hors du
    domaine de ses appelants du jour.

    Ce cran n'a pas de call-site porte : il garde la PROPRIETE, pas un usage. Il ne serait plus vrai
    si quelqu'un << simplifiait >> en `% 6`."""
    assert rotate(-1, 0) == -1        # C# : -1 % 6 == -1 ; Python : -1 % 6 == 5
    assert rotate(-7, 0) == -1
    assert rotate(-4, 3) == -1
    # et le domaine REEL (0..5 + 0..5) est inchange par la troncature
    assert all(rotate(a, b) == (a + b) % 6 for a in range(6) for b in range(6))


# ------------------------------------------------------------------------------------------------
# 2. `IdunBattle.Entities.Selectors.EdgeTilesByDirectionSelector$$Select`
# ------------------------------------------------------------------------------------------------

def test_edge_tiles_par_direction_rend_la_bordure_du_switch_natif():
    """Les quatre `case` du `switch` natif, sur un plateau rectangulaire dont on connait les ids.

    `GetTileAt(column, row)` : `South` = la ligne `0` sur toutes les colonnes ; `North` = la ligne
    `ROWS - 1` ; `North_East`/`South_East` = la colonne `COLS - 1` sur toutes les lignes ;
    `South_West`/`North_West` = la colonne `0`."""
    ctx = _ctx()
    b = _board()

    def ids(cells):
        return [b.id_at(c, r) for c, r in cells]

    assert EdgeTilesByDirection(int(Edge.South)).evaluate(ctx) == ids(
        [(c, 0) for c in range(_COLS)])
    assert EdgeTilesByDirection(int(Edge.North)).evaluate(ctx) == ids(
        [(c, _ROWS - 1) for c in range(_COLS)])
    assert EdgeTilesByDirection(int(Edge.North_East)).evaluate(ctx) == ids(
        [(_COLS - 1, r) for r in range(_ROWS)])
    assert EdgeTilesByDirection(int(Edge.South_West)).evaluate(ctx) == ids(
        [(0, r) for r in range(_ROWS)])


def test_deux_aretes_par_cote_partagent_la_meme_bordure():
    """`North_East`/`South_East` partagent LITTERALEMENT le meme bloc dans le decompile, et de meme
    `South_West`/`North_West`. C'est ce qui fait que les deux branches du `Maybe` de 1215 visent le
    MEME couple de bordures et ne different que par l'INCLINAISON des lignes.

    Ce cran assertionne son propre NON-VIDE : deux bordures vides seraient egales entre elles et le
    test passerait pour vert sans rien mesurer."""
    ctx = _ctx()
    est = EdgeTilesByDirection(int(Edge.North_East)).evaluate(ctx)
    sud_est = EdgeTilesByDirection(int(Edge.South_East)).evaluate(ctx)
    ouest = EdgeTilesByDirection(int(Edge.South_West)).evaluate(ctx)
    nord_ouest = EdgeTilesByDirection(int(Edge.North_West)).evaluate(ctx)
    assert est and ouest, "bordures VIDES : le test ne mesurerait rien"
    assert est == sud_est
    assert ouest == nord_ouest
    assert est != ouest, "les deux cotes doivent differer, sinon le switch est degenere"


def test_edge_tiles_refuse_une_direction_absente_ou_hors_enum():
    """`!v.HasValue` -> liste VIDE, et le `default:` du switch -> liste VIDE. Aucun repli sur une
    bordure par defaut : un `None` (le `Nullable` vide du natif) ne doit JAMAIS designer un bord."""
    ctx = _ctx()
    assert EdgeTilesByDirection(None).evaluate(ctx) == []
    assert EdgeTilesByDirection(6).evaluate(ctx) == []
    assert EdgeTilesByDirection(-1).evaluate(ctx) == []
    assert EdgeTilesByDirection(int(Edge.South)).evaluate(dsl.DslContext(units=[])) == []


def test_edge_tiles_saute_les_trous_du_plateau():
    """`GetTileAt` rend `null` sur une case absente et le natif ne l'ajoute PAS. Le port doit sauter,
    pas rendre `None` dans la liste -- sinon toute la chaine en aval (`Randomize`, `Count`,
    `AddEffect`) traiterait un trou comme une tuile."""
    tiles = [{"id": 100 + c * _ROWS + r, "col": c, "row": r, "neighbours": []}
             for c in range(_COLS) for r in range(_ROWS)
             if not (c == 0 and r == 1)]                  # un trou dans la bordure OUEST
    ctx = dsl.DslContext(units=[], board=Board(tiles))
    ouest = EdgeTilesByDirection(int(Edge.South_West)).evaluate(ctx)
    assert None not in ouest
    assert len(ouest) == _ROWS - 1


# ------------------------------------------------------------------------------------------------
# 3. `TileUnion` en domaine mixte -- l'operande MONO-ENTITE
# ------------------------------------------------------------------------------------------------

def test_tile_union_accepte_un_operande_mono_entite():
    """`TilesBehindInLine(...) op_Addition ActiveTarget@+0x68` : le second operande est l'element
    COURANT du tri, donc un id de tuile NU. `list(<int>)` levait `TypeError` -- ce qui aurait fait
    tomber tout l'arbre de 1215 des la premiere evaluation de formule."""
    from engine.entities.selectors.accessors import ActiveTarget
    from engine.entities.selectors.accessors import FixedTileIds
    ctx = dsl.DslContext(units=[], board=_board(), active_target=107)
    assert TileUnion(FixedTileIds([100, 101]), ActiveTarget()).evaluate(ctx) == [100, 101, 107]
    # dedup preserve, et un `ActiveTarget` absent ne fabrique pas d'entite
    ctx_vide = dsl.DslContext(units=[], board=_board())
    assert TileUnion(FixedTileIds([100]), ActiveTarget()).evaluate(ctx_vide) == [100]


# ------------------------------------------------------------------------------------------------
# 4. La STRUCTURE de `GetEffectBehavior` -- les litteraux qui s'inversent en silence
# ------------------------------------------------------------------------------------------------

def _walk(node):
    """Parcours de l'arbre porte, par attributs -- aucun registre a tenir a jour."""
    vus, pile, out = set(), [node], []
    while pile:
        n = pile.pop()
        if id(n) in vus:
            continue
        vus.add(id(n))
        out.append(n)
        for v in vars(n).values() if hasattr(n, "__dict__") else ():
            if hasattr(v, "evaluate") or hasattr(v, "execute"):
                pile.append(v)
            elif isinstance(v, (list, tuple)):
                pile.extend(x for x in v if hasattr(x, "evaluate") or hasattr(x, "execute"))
        for s in getattr(type(n), "__slots__", ()) or ():
            v = getattr(n, s, None)
            if hasattr(v, "evaluate") or hasattr(v, "execute"):
                pile.append(v)
            elif isinstance(v, (list, tuple)):
                pile.extend(x for x in v if hasattr(x, "evaluate") or hasattr(x, "execute"))
    return out


@pytest.mark.parametrize("first,idx", [(True, "0"), (False, "1")])
def test_les_deux_cles_persistantes_portent_l_indice_de_leur_passe(first, idx):
    """`String.Concat(<litteral>, i.ToString())` avec `i = ((byte)first & 0xff) ^ 1`.

    Les DEUX litteraux sont resolus au `global-metadata.dat` du build (slots `0x3364300` /
    `0x3364070`), pas inventes -- et ils sont DISTINCTS : les confondre ferait relire la tuile de
    depart comme direction, donc une ligne de longueur nulle."""
    ecrits = sorted(n.data_key for n in _walk(
        instruments_of_vengeance_effect_behavior(int(Edge.North_East), first))
        if isinstance(n, SetPersistentData))
    assert ecrits == sorted([IOV_KEY_DIRECTION_TILE + idx, IOV_KEY_TARGET_TILE + idx])
    assert IOV_KEY_TARGET_TILE != IOV_KEY_DIRECTION_TILE
    # l'ecriture porte sur le CASTER, jamais sur l'Owner (les deux slots sont distincts au natif)
    from engine.entities.selectors.tiles import Caster
    assert all(isinstance(n.unit_sel, Caster)
               for n in _walk(instruments_of_vengeance_effect_behavior(int(Edge.North_East), first))
               if isinstance(n, SetPersistentData))


def test_la_seconde_passe_relit_l_indice_zero_pas_le_sien():
    """`local_res18[0] = 0` : la 2e passe RELIT l'indice **0** -- celui que la 1re vient d'ecrire --
    puis ecrit l'indice 1. Relire `idx` (= 1) rendrait une cle VIDE, `Entity(None)` -> `[]`, donc
    AUCUNE soustraction : les deux lignes pourraient se superposer, en silence."""
    from engine.entities.formulas import GetPersistentData
    lus = sorted(n.data_key for n in _walk(
        instruments_of_vengeance_effect_behavior(int(Edge.North_West), False))
        if isinstance(n, GetPersistentData))
    assert lus == sorted([IOV_KEY_DIRECTION_TILE + "0", IOV_KEY_TARGET_TILE + "0"])
    assert all(n.ability_or_effect == IOV_ABILITY for n in _walk(
        instruments_of_vengeance_effect_behavior(int(Edge.North_West), False))
        if isinstance(n, GetPersistentData))


def test_la_premiere_passe_ne_lit_aucune_donnee_persistante():
    """Le terme de SOUSTRACTION n'existe QUE sur la 2e passe (`if ((char)first == '\\0')` du
    decompile). Une 1re passe qui lirait retrancherait la ligne d'un cast PRECEDENT -- le sac de
    donnees persistantes survit au tour."""
    from engine.entities.formulas import GetPersistentData
    assert not [n for n in _walk(
        instruments_of_vengeance_effect_behavior(int(Edge.North_East), True))
        if isinstance(n, GetPersistentData)]


def test_les_trois_tris_portent_le_sens_lu_au_call_site():
    """`ascending` = `0, 1, 0` dans l'ORDRE d'application. Les tris sont chaines et STABLES, donc le
    dernier applique est la cle PRIMAIRE ; le port les imbrique, donc le PLUS EXTERIEUR est le
    dernier applique.

    ⚠ Le SEUL a `1` est celui des AMIS. L'inverser choisit la ligne qui couvre le PLUS d'allies --
    meme nombre de tuiles marquees, resultat oppose."""
    n = instruments_of_vengeance_effect_behavior(int(Edge.North_East), True)
    # on remonte la chaine `SortByFormula` par imbrication : externe -> interne
    tris = []
    cur = None
    for x in _walk(n):
        if isinstance(x, SortByFormula) and not any(
                isinstance(y, SortByFormula) for y in _walk(x) if y is not x):
            cur = x                                       # le plus INTERNE
    assert cur is not None, "aucun SortByFormula trouve : le walk ne voit plus l'arbre"
    # reconstruit l'ordre d'application en descendant depuis l'externe
    externe = [x for x in _walk(n) if isinstance(x, SortByFormula)]
    assert len(externe) == 3, "trois tris chaines attendus, vu %d" % len(externe)
    chaine, x = [], None
    for cand in externe:
        if all(cand is not getattr(o, "source", None) for o in externe):
            x = cand                                      # personne ne le consomme -> le PLUS externe
    while x is not None:
        chaine.append(x)
        x = x.source if isinstance(x.source, SortByFormula) else None
    tris = [t.ascending for t in reversed(chaine)]        # ordre d'APPLICATION
    assert tris == [False, True, False], "sens des tris (asc) attendu [0, 1, 0], vu %s" % (tris,)


# ------------------------------------------------------------------------------------------------
# 5. Les REGISTRES -- la regle de non-regression du meme commit
# ------------------------------------------------------------------------------------------------

def test_1215_entre_au_registre_avec_son_masque_et_son_attack_type():
    """`ABILITY_CLASSES` + `TARGETING_OPTIONS` + `ABILITY_ATTACK_TYPE`, dans le meme commit.

    Le masque est assertionne PAR SA VALEUR ENTIERE (`0x8004`), pas seulement par ses membres : ce
    qui separe 1215 de 1216 est un bit ABSENT, et un test qui verifierait la seule presence des deux
    bits attendus passerait aussi sur `0x8014`."""
    assert ABILITY_CLASSES.get(1215) is InstrumentsOfVengeanceAbility
    opts = InstrumentsOfVengeanceAbility.TARGETING_OPTIONS
    assert int(opts.rules) == 0x8004
    assert int(opts.rules) & int(TR.CasterHasNotMoved) == 0, (
        "1215 NE porte PAS CasterHasNotMoved : c'est le seul bit qui la separe de 1216, et le "
        "recopier la rendrait incastable apres deplacement")
    assert opts.self_cast is True
    assert ABILITY_ATTACK_TYPE.get(ActiveAbilityType.InstrumentsOfVengeance) == \
        AbilityAttackType.Others


def test_le_masque_a_quitte_la_table_des_non_portees():
    """CONTRAT DE DISJONCTION d'`abilities/targeting.py` : une ability a UNE source de masque."""
    assert int(ActiveAbilityType.InstrumentsOfVengeance) not in TARGETING_OPTIONS_UNPORTED
    assert ActiveAbilityType.InstrumentsOfVengeance not in TARGETING_OPTIONS_UNPORTED


def test_les_trois_ordinaux_sont_qualifies_par_leur_enum():
    """`0x5ee`/`0x5ef` sont des `EffectType`, `0x3f1` aussi -- et cet ordinal-la est PARTAGE
    (`ActiveAbilityType(1009)` = `ResurrectionOrb`, `TriggeredAbilityType(1009)` = `WhipcoilBody`).
    C'est l'`ActivateEffect` (dont l'argument est un `EffectType`) qui fixe l'enum."""
    assert IOV_LOCATION_TARGET == int(EffectType.InstrumentsOfVengeance_LocationTarget) == 0x5EE
    assert IOV_PENDING_ATTACK == int(EffectType.InstrumentsOfVengeance_PendingAttack) == 0x5EF
    assert int(EffectType.Overwatch_AutoAttack) == 0x3F1
    assert int(ActiveAbilityType.ResurrectionOrb) == 0x3F1, (
        "l'ordinal 1009 est bien PARTAGE entre deux enums -- si ce n'etait plus vrai, la "
        "qualification ci-dessus n'aurait plus d'objet et il faudrait la re-mesurer")


def test_1519_est_dans_la_table_ET_sa_phase_2_est_ATTEIGNABLE():
    """LE CRAN A BASCULE (`#889-r7`, 2026-08-17), et c'etait son signal. Il gardait en NEGATIF
    l'ABSENCE de `1519` dans `PENDING_ATTACK_EFFECTS`, parce que la PHASE 2
    (`...InstrumentsOfVengeance_AttackAbility$$CreateBehaviour`) n'etait pas portee : l'inscrire
    seule aurait fait consommer la marque `1518` par le `RemoveEffect` du meme arbre sans que rien
    ne frappe -- un no-op SILENCIEUX.

    Il garde desormais le MEME invariant dans l'autre sens, et c'est le seul qui compte : l'entree
    n'est legitime QUE si son ability triggered est atteignable. Le couple est donc verifie
    ENSEMBLE -- retirer le module de phase 2 en laissant l'entree rougit ici, et l'inverse aussi.

    ⚠ L'`attacker` est `ATTACKER_EFFECT_SOURCE` et NON `ATTACKER_BONDED`, bien que l'effet soit pose
    par `AddBondEffect` : `...InstrumentsOfVengeance_PendingAttackEffect$$GetAttackingUnitSelector`
    est SURCHARGEE en `DSLSelectors$$EffectSource(Effect@DSLSelectors+0x38)`. Sur ce porteur les deux
    lectures COINCIDENT (`source == targets == bondedEntity == Owner@+0x30`), donc aucune mesure live
    ne peut les separer -- l'assertion vient du decompile, et c'est ce qui la rend utile."""
    from engine.entities.triggered_ability_type import TriggeredAbilityType
    from engine.runner.abilities.behaviours.lifecycle import TRIGGERED_ABILITY_BEHAVIOURS
    from engine.runner.operations.triggers.dispatch import registry as _reg     # noqa: F401
    from engine.runner.operations.triggers.pending_attack import ATTACKER_EFFECT_SOURCE

    spec = PENDING_ATTACK_EFFECTS.get(IOV_PENDING_ATTACK)
    assert spec is not None, (
        "1519 a QUITTE PENDING_ATTACK_EFFECTS : sans elle le `Triggered()` d'APendingAttackEffect "
        "ne fire jamais et la phase 2 portee devient du code mort.")
    assert spec.triggered_ability == int(TriggeredAbilityType.InstrumentsOfVengeance_PendingAttack)
    assert spec.attacker == ATTACKER_EFFECT_SOURCE, (
        "GetAttackingUnitSelector est SURCHARGEE en EffectSource -- ATTACKER_BONDED accorderait sur "
        "ce porteur (source == bonde) et serait faux partout ailleurs.")
    assert spec.triggered_ability in TRIGGERED_ABILITY_BEHAVIOURS, (
        "l'entree 1519 est dans la table mais son ability triggered n'est PAS au registre : le "
        "RemoveEffect de l'arbre consommerait la marque sans que rien ne frappe.")
