"""CLIQUET #585-r1 -- le RELEVE des littéraux `selectionType`, call-site par call-site.

Ce que la tranche a fait : lire, au decompile du build `rnca9r7q6c`, le littéral que chaque
`IdunBattleLogic.Entities.DSLSelectors$$*` recoit, et le CABLER au mirror correspondant. Ce que ce
fichier garde, c'est que ces littéraux **restent cables** et **restent CEUX-LA**.

POURQUOI UN CLIQUET, ET PAS SEULEMENT UN TEST DE COMPORTEMENT
-------------------------------------------------------------
La degradation est PERMISSIVE et SILENCIEUSE : un `selection_type` retire rend `None`, donc aucun
filtre, donc le port retient une unite `Untargetable` (deep strike, `AmbushEffect`) que le natif
ecarte. Ni erreur, ni crash. C'est exactement le regime que #585 a mesure sur `spaceRockfist`.

LE PIEGE QUE CE FICHIER MATERIALISE -- et il n'est pas theorique
----------------------------------------------------------------
Sur le corpus releve, la valeur est **3** (`OnlyAliveAndTargetable`) partout SAUF une, et cette
exception est structurante :

    IdunBattleLogic.Entities.Abilities.Active.Loki.ResurrectionOrbAbility$$GetPossibleResurrectTargets
        -> Friends(gs, gs@0x48, AllDeadUnits(gs), 0)          # UnitSelectionType.Any

Ses cibles sont MORTES. Un `3` recopie par symetrie y aurait vide l'ensemble -- un masque FAUX qui
a l'air renseigne, donc pire que l'absence. L'etage 2 le rend EXECUTABLE : il montre que le `3`
serait discriminant sur ce montage-la.

⚠ TROISIEME PIEGE, tranche par les XREFS ENTRANTES et pas par le pseudo-C :
`DSLSelectors$$AdjacentFriends` et `$$AdjacentEnemies` ont DEUX surcharges d'arite 4, au meme nom
affiche. `(this, unit, unique, selectionType)` porte le littéral ; `(this, unit, unitTile, unique)`
**code le selectionType EN DUR a 3** (dans son `Units` interne ET dans son `Friends`/`Enemies`
final). `...RitesOfRestorationAbility$$GetHealTargets` emprunte la SECONDE -- son 3 n'est ecrit
nulle part dans son propre corps.

ASCII only (cp1252).
"""
from __future__ import annotations

#: Perimetre ETROIT et DERIVE : les fichiers dont une edition peut RENDRE FAUX ce qui est fige ici.
#: Pas de glob `scripts/python/**` (ce serait un `toujours: True` deguise). Les chemins sont
#: COMPLETS -- un basename se confondrait avec un homonyme d'un autre paquet.
DECLENCHEUR = {
    "chemins": (
        "scripts/python/engine/runner/abilities/darkangels.py",
        "scripts/python/engine/runner/abilities/deathguard.py",
        "scripts/python/engine/runner/abilities/blacklegion.py",
        "scripts/python/engine/runner/abilities/necrons.py",
        "scripts/python/engine/runner/abilities/orks.py",
        "scripts/python/engine/runner/abilities/sisterhood.py",
        "scripts/python/engine/entities/selectors/units.py",
        "scripts/python/engine/entities/selectors/composites.py",
        "scripts/python/engine/entities/unit_selection_type.py",
        "scripts/python/engine/entities/unit_flag.py",
        "scripts/python/engine/entities/effects/aura_selectors.py",
        "scripts/python/engine/dsl/base.py",
    ),
    "build": False,
    "toujours": False,
    "raison": "Ce cliquet fige des valeurs du PORT (les litteraux `selectionType` RECOPIES depuis "
              "le decompile) et le fait qu'ils MORDENT. Il ne lit ni le binaire ni les tables du "
              "build, donc `build: False` : le seul axe qui peut le perimer est une edition des "
              "fichiers ci-dessus -- les six modules d'ability releves, les mirrors de selecteur "
              "qui portent le parametre, le foyer du predicat et ses deux canaux de donnee.",
}

import ast
from pathlib import Path

import pytest

ENGINE = Path(__file__).resolve().parents[3] / "engine"

from engine.entities.selectors.accessors import Target
from engine.entities.unit_flag import UnitFlag
from engine.entities.unit_selection_type import UnitSelectionType

_ANY = int(UnitSelectionType.Any)
_AAT = int(UnitSelectionType.OnlyAliveAndTargetable)


# ─────────────────────────── ETAGE 1 : les littéraux RELEVES, figes un par un

def _plagueburst_adjacent():
    from engine.runner.abilities.deathguard import plagueburst_adjacent_enemies
    return plagueburst_adjacent_enemies(Target())


def _plagueburst_main():
    from engine.runner.abilities.deathguard import plagueburst_main_damage_target
    return plagueburst_main_damage_target(Target())


def _daemonic_ordnance():
    from engine.runner.abilities.blacklegion import daemonic_ordnance_all_damageable_targets
    return daemonic_ordnance_all_damageable_targets(Target())


def _resurrection_orb():
    from engine.runner.abilities.necrons import resurrection_orb_possible_resurrect_targets
    return resurrection_orb_possible_resurrect_targets()


def _rites_heal():
    from engine.runner.abilities.sisterhood import rites_of_restoration_heal_targets
    return rites_of_restoration_heal_targets()


#: (libelle, fabricant, chemin d'attributs depuis la racine, littéral MESURE au decompile).
#: Le chemin est explicite : c'est ce qui rend le test lisible sans deplier l'arbre a la main.
RELEVE = (
    ("PlagueburstMortarAbility$$GetAdjacentEnemies / Enemies",
     _plagueburst_adjacent, ("selection_type",), _AAT),
    ("PlagueburstMortarAbility$$GetAdjacentEnemies / Units",
     _plagueburst_adjacent, ("inner", "selection_type"), _AAT),
    ("PlagueburstMortarAbility$$GetMainDamageTarget / Enemies",
     _plagueburst_main, ("source", "selection_type"), _AAT),
    ("DaemonicOrdnanceAbility$$GetAllDamageableTargets / Enemies",
     _daemonic_ordnance, ("selection_type",), _AAT),
    ("DaemonicOrdnanceAbility$$GetAllDamageableTargets / Units",
     _daemonic_ordnance, ("inner", "selection_type"), _AAT),
    # LE CONTRE-EXEMPLE.
    ("ResurrectionOrbAbility$$GetPossibleResurrectTargets / Friends",
     _resurrection_orb, ("source", "selection_type"), _ANY),
    # LE LITTERAL IMPLICITE (surcharge `(this, unit, unitTile, unique)`, selectionType EN DUR).
    ("RitesOfRestorationAbility$$GetHealTargets / Friends",
     _rites_heal, ("source", "b", "selection_type"), _AAT),
)


def _resoudre(racine, chemin):
    n = racine
    for p in chemin:
        n = getattr(n, p)
    return n


def test_etage1_chaque_litteral_releve_est_toujours_cable():
    """Chaque littéral LU au decompile est encore celui que porte le noeud du port.

    Un `selection_type` retire (ou remis a `None`) fait tomber ce test -- c'est le seul canal ou
    la degradation, PERMISSIVE et silencieuse, devient visible."""
    ecarts = []
    for libelle, fabricant, chemin, attendu in RELEVE:
        try:
            v = _resoudre(fabricant(), chemin)
        except AttributeError as exc:
            ecarts.append("%s : CHEMIN CASSE (%s) -- l'arbre du port a change de forme, "
                          "re-lire le decompile avant de rafistoler le chemin" % (libelle, exc))
            continue
        if v is None:
            ecarts.append("%s : `selection_type` est revenu a None -- le filtre `Untargetable` "
                          "n'est plus arme, le port sur-selectionne EN SILENCE" % libelle)
        elif int(v) != attendu:
            ecarts.append("%s : %d cable, %d LU au decompile" % (libelle, int(v), attendu))
    assert not ecarts, "RELEVE #585-r1 rompu :\n  " + "\n  ".join(ecarts)


def test_etage1b_le_releve_n_est_pas_degenere():
    """Anti-degenerescence : une table a valeur UNIQUE ne prouverait rien.

    Si le releve ne portait que des `3`, l'etage 1 serait satisfait par la faute meme qu'il doit
    interdire (« recopier 3 partout »). On exige donc que le corpus fige contienne AU MOINS deux
    valeurs distinctes, et que `Any` en fasse partie."""
    valeurs = {attendu for _l, _f, _c, attendu in RELEVE}
    assert len(RELEVE) >= 5, "table trop maigre pour etre un temoin (%d entrees)" % len(RELEVE)
    assert len(valeurs) >= 2, (
        "toutes les entrees du releve portent la MEME valeur : ce cliquet ne discrimine plus "
        "« littéral lu » de « 3 recopie ». Y remettre un contre-exemple.")
    assert _ANY in valeurs, (
        "le contre-exemple `Any` (ResurrectionOrb, cibles MORTES) a disparu de la table -- c'est "
        "lui qui etablit que le releve n'a pas ete fait par symetrie")


# ─────────────────────────── ETAGE 2 : le contre-exemple SERAIT discriminant (il n'est pas gratuit)

COLS, ROWS = 6, 6


def _tid(col, row):
    return col * ROWS + row


def _board():
    """Board PLAT au format `boardGraph` : adjacence purement geometrique, porte d'elevation
    inerte -- donc tout verdict ci-dessous vient du FILTRE, pas du terrain."""
    import hexgeo
    from engine.entities.pathfinding.board import Board
    tuiles = []
    for col in range(COLS):
        for row in range(ROWS):
            voisins = [_tid(c, r) for (c, r) in hexgeo.neighbors(col, row)
                       if 0 <= c < COLS and 0 <= r < ROWS]
            tuiles.append({"id": _tid(col, row), "col": col, "row": row, "elevation": 0,
                           "walkable": True, "isWall": False, "neighbours": voisins})
    return Board(tuiles)


def _ctx(units, caster, target, *, flags=None):
    """`flags = {unit_id: {flag, ...}}` -> `ctx.has_unit_flag`. `None` = canal ABSENT (tri-etat :
    `matches_unit_selection_type` degrade alors la clause en VRAI, jamais en FAUX)."""
    from engine.dsl.base import DslContext
    hf = None
    if flags is not None:
        def hf(u, flag, _f=flags):
            return int(flag) in _f.get(u.get("id"), set())
    return DslContext(units=list(units), caster=caster, target=target, board=_board(),
                      has_unit_flag=hf)


@pytest.fixture
def morts():
    """Un caster vivant et DEUX allies MORTS -- le substrat exact de `ResurrectionOrb`."""
    caster = {"id": 1, "team": "A", "col": 1, "row": 1, "alive": True, "hp": 10}
    m1 = {"id": 2, "team": "A", "col": 1, "row": 2, "alive": False, "hp": 0}
    m2 = {"id": 3, "team": "A", "col": 2, "row": 1, "alive": False, "hp": 0}
    return caster, [caster, m1, m2]


def test_etage2_un_3_recopie_aurait_VIDE_les_cibles_de_ResurrectionOrb(morts):
    """La faute EVITEE, rendue executable -- sinon « le littéral est 0 » n'est qu'une affirmation.

    On evalue le MEME selecteur (`Friends(AllDeadUnits(), Caster())`) sous les deux littéraux et
    on exige qu'ils DIFFERENT : `Any` retient les morts, `OnlyAliveAndTargetable` les ecarte tous
    (`MatchesUnitSelectionType` teste `IsAlive` pour 1 comme pour 3).

    ⚠ Ce test ASSERTIONNE SON PROPRE NON-VIDE : sur un montage sans mort, les deux branches
    rendraient `[]` et l'egalite passerait pour une preuve."""
    from engine.entities.selectors.tiles import Caster
    from engine.entities.selectors.units import AllDeadUnits, Friends

    caster, units = morts
    ctx = _ctx(units, caster, None)

    avec_any = Friends(AllDeadUnits(), Caster(), selection_type=_ANY).evaluate(ctx)
    avec_3 = Friends(AllDeadUnits(), Caster(), selection_type=_AAT).evaluate(ctx)

    assert len(avec_any) == 2, (
        "le montage ne rend PAS de mort avec `Any` (%d) : le temoin est degenere, le test ne "
        "mesure rien" % len(avec_any))
    assert avec_3 == [], (
        "`OnlyAliveAndTargetable` ne vide PAS l'ensemble des morts -- la mesure qui justifie le "
        "littéral `0` de `ResurrectionOrbAbility$$GetPossibleResurrectTargets` a change, relire "
        "le decompile")


# ─────────────────────────── ETAGE 3 : le littéral MORD (contre-epreuve du cablage)

#: Trois ennemis que SEULS les deux predicats de `MatchesUnitSelectionType` distinguent :
#: 2 = vivant et ciblable, 3 = vivant mais `Untargetable`, 4 = MORT et ciblable.
_CASTER = {"id": 1, "team": "A", "col": 1, "row": 1, "alive": True, "hp": 10}
_VIVANT = {"id": 2, "team": "B", "col": 1, "row": 2, "alive": True, "hp": 10}
_CACHE = {"id": 3, "team": "B", "col": 2, "row": 1, "alive": True, "hp": 10}
_MORT = {"id": 4, "team": "B", "col": 2, "row": 2, "alive": False, "hp": 0}

#: Ce que CHAQUE littéral doit retenir sur ce substrat -- transcription directe de
#: `IdunBattle.Entities.UnitExtensions$$MatchesUnitSelectionType`.
_ATTENDU_PAR_LITTERAL = {
    int(UnitSelectionType.Any): {2, 3, 4},
    int(UnitSelectionType.OnlyAlive): {2, 3},
    int(UnitSelectionType.OnlyTargetable): {2, 4},
    int(UnitSelectionType.OnlyAliveAndTargetable): {2},
}


def test_etage3_chaque_litteral_cable_MORD_et_les_deux_valeurs_DIVERGENT():
    """CONTRE-EPREUVE : un littéral cable qui ne changerait aucun resultat serait decoratif.

    Pour chaque entree du releve on prend la valeur REELLEMENT portee par le noeud du port, on la
    remet dans un noeud `Enemies` dont l'entree est un `UnitSet` explicite -- la GEOMETRIE est
    ainsi neutralisee, ce qui est le but : on veut mesurer le FILTRE, pas le terrain -- et on exige
    la partition que `MatchesUnitSelectionType` prescrit.

    Le cran qui compte est le DERNIER : `Any` et `OnlyAliveAndTargetable` doivent rendre des
    ensembles DIFFERENTS sur ce meme substrat. Sans lui, un releve entierement recopie a `3`
    passerait cet etage."""
    from engine.entities.selectors.units import Enemies, UnitSet

    units = [_CASTER, _VIVANT, _CACHE, _MORT]
    ctx = _ctx(units, _CASTER, None, flags={3: {int(UnitFlag.Untargetable)}})

    vus = {}
    ecarts = []
    for libelle, fabricant, chemin, _attendu in RELEVE:
        v = int(_resoudre(fabricant(), chemin))
        rendu = {u["id"] for u in
                 Enemies(UnitSet([_VIVANT, _CACHE, _MORT]), selection_type=v).evaluate(ctx)}
        vus[v] = rendu
        if rendu != _ATTENDU_PAR_LITTERAL[v]:
            ecarts.append("%s (littéral %d) : rend %r, `MatchesUnitSelectionType` prescrit %r"
                          % (libelle, v, sorted(rendu), sorted(_ATTENDU_PAR_LITTERAL[v])))
    assert not ecarts, "\n  ".join(ecarts)

    assert len(vus) >= 2, (
        "toutes les valeurs relevees se comportent pareil : cet etage ne discrimine plus rien")
    assert vus[_ANY] != vus[_AAT], (
        "`Any` et `OnlyAliveAndTargetable` rendent le MEME ensemble (%r) -- le substrat du test "
        "est degenere (il lui faut un mort ET un `Untargetable`), donc rien ne prouve que le "
        "contre-exemple `ResurrectionOrb` etait necessaire" % sorted(vus[_ANY]))


# ─────────────────────────── ETAGE 4 : le COMPTE par fichier (une regression de masse se voit)

#: `fichier -> nombre de call-sites RENSEIGNES`, mesure a la livraison de la tranche. Un compte qui
#: BAISSE = des littéraux retires. Un compte qui MONTE est licite (la tranche suivante en releve
#: d'autres) -- c'est pourquoi la comparaison est `>=` et non `==`.
COMPTES = {
    "runner/abilities/darkangels.py": 8,
    "runner/abilities/deathguard.py": 7,
    "runner/abilities/blacklegion.py": 5,
    "runner/abilities/necrons.py": 2,
    "runner/abilities/orks.py": 1,
    "runner/abilities/sisterhood.py": 2,
}


def _renseignes(rel: str) -> int:
    """Compte les `selection_type=<...>` passes en MOT-CLE dans les appels du fichier -- AST, pas
    grep : les docstrings de ce port citent les signatures natives a longueur de ligne."""
    arbre = ast.parse((ENGINE / rel).read_text(encoding="utf-8"))
    n = 0
    for noeud in ast.walk(arbre):
        if isinstance(noeud, ast.Call):
            n += sum(1 for k in noeud.keywords if k.arg == "selection_type")
    return n


def test_etage4_aucun_fichier_n_a_perdu_de_litteral():
    """Cliquet de MASSE : l'etage 1 ne tient que sept sites nommes, celui-ci tient les 25.

    Il ne dit PAS lesquels sont justes -- c'est le role des etages 1 a 3. Il dit qu'aucun n'a
    disparu, ce qu'aucune inspection d'objet ne peut voir a cette echelle."""
    manques = []
    for rel, attendu in sorted(COMPTES.items()):
        vu = _renseignes(rel)
        if vu < attendu:
            manques.append("%s : %d call-sites renseignes, la tranche en avait cable %d"
                           % (rel, vu, attendu))
    assert not manques, ("DES LITTERAUX `selectionType` ONT DISPARU (degradation PERMISSIVE et "
                         "silencieuse) :\n  " + "\n  ".join(manques))
