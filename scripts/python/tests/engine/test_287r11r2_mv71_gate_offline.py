"""#287-r11-r2 -- GARDE de la regle dynamique de ciblage de `1076 MV71SniperDroneSquadAttack`.

Le probe LIVE (`probe_287r11r2_mv71_gate_live.py`) prouve que la regle repond COMME LE NATIF sur un
plateau reel (`MC1_01`, disque r=4 sature -> natif `0x1 ValidRequest`, reproduit par les DEUX
porteurs ; une seule unite deplacee -> `0x0`). Ce fichier-ci garde ce que le live ne peut pas
atteindre, et les lectures NON TRIVIALES de la RE :

  1. RECENSEMENT   -- 1076 est evaluable par SURCHARGE, pose le bit dans SES DEUX masques (celui du
                      registre ET celui de la table par type d'attaque normale), et il est le SEUL
                      type d'attaque normale a declarer le corps -- c'est cette mesure qui rend
                      l'aiguillage de `_NormalAttackTargeting` sur, plutot que suppose.
  2. CODE RENDU    -- le refus est le litteral `1 = TargetingRule.ValidRequest`, PAS
                      `2 TargetMatchesDynamicRule`. Recopier `2` par analogie avec les autres
                      regles dynamiques aurait ecrit un code FAUX que la cascade propage tel quel.
  3. BASCULE       -- disque r=4 SATURE -> refus ; UNE tuile liberee -> accepte. Le decideur est le
                      COMPTE, pas la distance (elle ne change pas entre les deux bras).
  4. BRAS MELEE    -- cible ADJACENTE au caster : `IsMeleeAttack` court-circuite AVANT `PickTile`,
                      donc `0` MEME sur un disque sature. Aucun montage live ne le produit (il
                      faudrait saturer le disque d'une cible au contact du caster).
  5. AIGUILLAGE    -- `_NormalAttackTargeting` rend le corps de 1076 pour `tauMarksman` et celui de
                      la BASE pour un caster generique. C'est LA cause du trou : le porteur de
                      l'attaque normale appliquait la regle de la base a tout le monde.
  6. RAYON         -- `GetUnitMaxRange(tauSmnDroneSniper)` = 4, DERIVE du catalogue (mutant sur
                      `GC.unit`), jamais une constante ecrite au site.
  7. MUTANTS       -- desarmee, la bascule doit S'EFFONDRER. Sans cet etage, les precedents
                      seraient verts sur un port qui ne consulte plus rien.

ASCII only (cp1252). Aucun runner : tout est offline.
"""
from __future__ import annotations

import sys
from pathlib import Path

# `DECLENCHEUR` (#486-r15) -- ce qui doit changer pour que ce fichier puisse changer de verdict.
DECLENCHEUR = {
    "chemins": (
        # SOCLE COMMUN a tout fichier de test : la cascade des deux `conftest.py` et sa fermeture.
        "scripts/python/conftest.py", "scripts/python/tests/conftest.py",
        "scripts/python/green_skip_guard.py", "scripts/python/declencheur_guard.py",
        # LE CORPS PORTE et son foyer de melee -- c'est l'objet meme de ce fichier.
        "scripts/python/engine/runner/abilities/loki/mv71.py",
        # L'AIGUILLAGE : `_NormalAttackTargeting`, la table par type, et la cascade qui les lit.
        "scripts/python/engine/runner/abilities/targeting.py",
        "scripts/python/engine/runner/abilities/targeting_rule.py",
        # LE REGISTRE : l'aiguillage est DERIVE de `ABILITY_CLASSES`, donc toute entree neuve
        # d'attaque normale portant une surcharge fait changer l'etage 1.
        "scripts/python/engine/runner/abilities/handler.py",
        # LA CASCADE DE L'ATTAQUE NORMALE : quel type est celui de ce caster.
        "scripts/python/engine/services/custom_normal_attack.py",
        # LE SUBSTRAT que les montages offline construisent.
        "scripts/python/engine/runner/snapshot.py",
        "scripts/python/engine/entities/pathfinding/board.py",
        # LE RECENSEMENT et le desarmement dont ce fichier se sert comme mutant.
        "scripts/python/probe_287r4r1_dynamic_target_rules.py",
        # ⚠ LARGE ET ASSUME : importer `handler` tire tout le paquet `abilities` (registre de
        # triggers, vocabulaire DSL, pathfinding). Une liste feuille-a-feuille ne peut pas montrer
        # le module qu'elle a oublie -- les chemins nommes ci-dessus disent OU regarder, les deux
        # globs disent ce qui FAIT changer d'avis. Les DEUX formes sont necessaires : `**/` exige
        # un SEGMENT, donc `scripts/python/**/*.py` ne voit PAS `scripts/python/gameconfig.py`.
        "scripts/python/*.py", "scripts/python/**/*.py",
    ),
    # Le rayon du drone et `maxSummons` sont LUS dans le gameconfig du build : un re-dump peut les
    # faire bouger, et l'etage 6 doit alors rougir plutot que de figer une valeur perimee.
    "build": True,
    "toujours": False,
    "raison": (
        "La regle dynamique de 1076 est un mirror d'un corps natif ; elle ne peut changer de "
        "verdict que si le corps porte, son aiguillage, le registre, le substrat de montage ou "
        "le gameconfig du build changent."),
}

HERE = Path(__file__).resolve()
PY = HERE.parents[2]
if str(PY) not in sys.path:
    sys.path.insert(0, str(PY))

import gameconfig as GC                                                    # noqa: E402
import hexgeo                                                              # noqa: E402
import probe_287r4r1_dynamic_target_rules as P                             # noqa: E402
from engine.entities.active_ability_type import ActiveAbilityType          # noqa: E402
from engine.entities.pathfinding.board import Board                        # noqa: E402
from engine.runner.abilities.handler import ABILITY_CLASSES                # noqa: E402
from engine.runner.abilities.targeting import (                            # noqa: E402
    NORMAL_ATTACK_TARGETING_OPTIONS_BY_TYPE, _NormalAttackTargeting,
    normal_attack_targeting_options, normal_attack_type_for)
from engine.runner.abilities.targeting_rule import TargetingRule as TR     # noqa: E402
from engine.runner.snapshot import load_state                              # noqa: E402

# ⚠ LES SYMBOLES NEUFS DE LA TRANCHE SONT IMPORTES *DANS* LEURS TESTS, PAS EN TETE, et c'est la
# seule raison : sur l'arbre TEMOIN (avant #287-r11-r2) ils n'existent pas, et un import de tete
# ferait echouer la COLLECTE -- donc un rouge d'UNE ligne au lieu d'une ventilation.

MV71 = int(ActiveAbilityType.MV71SniperDroneSquadAttack)   # 1076
GENERIQUE = int(ActiveAbilityType.Loki_NormalAttack)       # 69
PORTEUR = "tauMarksman"

# MESURES du build `rnca9r7q6c`, FIGEES ici. Le cliquet `probe_313` compare des MIRRORS d'enum,
# jamais une valeur derivee au site : sans ce cran, une derivation qui glisse reste verte.
DRONE = "tauSmnDroneSniper"
RAYON_DRONE_MESURE = 4          # = max(Range des armes du drone), arme sans portee -> 1
MAX_SUMMONS_MESURE = 3
REFUS = int(TR.ValidRequest)    # le litteral `1` du decompile


# ================================================================================================
# substrat -- board LIGNE, saturable avec trois unites
# ================================================================================================
#
# Le disque r=4 d'une tuile de coin sur un board PLEIN compte 60 tuiles : injouable offline comme
# live. Une LIGNE de 4 tuiles le ramene a 3, saturables par trois unites, et sa geometrie est
# mesurable (`hexgeo.distance((0,0),(k,0)) == k`, verifie ci-dessous).

def _tid(col: int, row: int) -> int:
    return col * 100 + row + 1                 # ids de TUILE, disjoints des ids d'unite


def _board_ligne(n: int) -> Board:
    """Board de `n` tuiles alignees sur `row = 0`. Plat, marchable, sans mur."""
    tuiles = []
    for col in range(n):
        nb = [_tid(c, r) for (c, r) in hexgeo.neighbors(col, 0) if r == 0 and 0 <= c < n]
        tuiles.append({"id": _tid(col, 0), "col": col, "row": 0, "elevation": 0,
                       "walkable": True, "isWall": False, "neighbours": nb})
    return Board(tuiles, adjacency="evenq")


def _substrat(unites: list, n: int):
    """`State` runner sur un board LIGNE de `n` tuiles. `unites` = (id, visualId, team, col)."""
    dv = {"currentPlayer": 1, "units": [
        {"id": uid, "visualId": vid, "alive": True, "team": team, "owner": team,
         "pos": {"col": col, "row": 0}, "effects": []}
        for (uid, vid, team, col) in unites]}
    ob = {"units": [{"squadId": u["id"], "hp": 100, "hpMax": 100} for u in dv["units"]]}
    snap = {"units": [{"entityId": uid, "traits": []} for (uid, _v, _t, _c) in unites]}
    return load_state(dv, ob, snap, board=_board_ligne(n))


U_CASTER, U_CIBLE, U_A, U_B = 9001, 9002, 9003, 9004

# Les trois substrats de la bascule. La CIBLE est toujours en (0,0) et le disque r=4 de la ligne de
# 4 tuiles est donc {(1,0), (2,0), (3,0)}.
#   SATURE   : caster en 2 (d = 2, NON adjacent) + bloqueurs en 1 et 3 -> zero tuile libre.
#   UNE_LIBRE: le bloqueur de 3 retire -> exactement UNE tuile libre.
#   MELEE    : caster en 1 (d = 1) + bloqueurs en 2 et 3 -> disque sature, mais `IsMeleeAttack`
#              court-circuite. C'est le bras que le live n'atteint pas.
SATURE = [(U_CASTER, PORTEUR, 1, 2), (U_CIBLE, "necroWarden", 2, 0),
          (U_A, "ultraTitus", 1, 1), (U_B, "ultraTitus", 1, 3)]
UNE_LIBRE = [(U_CASTER, PORTEUR, 1, 2), (U_CIBLE, "necroWarden", 2, 0),
             (U_A, "ultraTitus", 1, 1)]
MELEE = [(U_CASTER, PORTEUR, 1, 1), (U_CIBLE, "necroWarden", 2, 0),
         (U_A, "ultraTitus", 1, 2), (U_B, "ultraTitus", 1, 3)]


def _regle(unites, caster_id=U_CASTER, target_id=U_CIBLE) -> int:
    """La regle telle que la cascade la consulte par la VOIE DU REGISTRE (`turnflow`)."""
    st = _substrat(unites, 4)
    return int(P._porteur(MV71).get_dynamic_invalid_target_reason(
        st, caster_id, target_id) or 0)


def _regle_attaque_normale(unites, caster_id=U_CASTER, target_id=U_CIBLE) -> int:
    """La MEME regle par la voie de l'ATTAQUE NORMALE (`valid_normal_attack_targets`)."""
    st = _substrat(unites, 4)
    porteur = _NormalAttackTargeting(normal_attack_targeting_options(st, caster_id))
    return int(porteur.get_dynamic_invalid_target_reason(st, caster_id, target_id) or 0)


def test_la_ligne_du_substrat_a_la_geometrie_voulue():
    """Un substrat dont la geometrie n'est pas celle qu'on croit rend les bras VRAIS PAR VACUITE."""
    for k in range(1, 5):
        assert hexgeo.distance((0, 0), (k, 0)) == k, "la ligne n'est pas isometrique en col"
    b = _board_ligne(4)
    assert sorted(b.coord(t) for t in b.by_id) == [(0, 0), (1, 0), (2, 0), (3, 0)]
    # Les trois tuiles hors cible sont TOUTES dans le disque r=4 : sinon « sature » ne saturerait
    # rien et le refus viendrait d'ailleurs.
    assert all(1 <= hexgeo.distance((0, 0), (k, 0)) <= RAYON_DRONE_MESURE for k in (1, 2, 3))


# ================================================================================================
# 1. RECENSEMENT
# ================================================================================================

def test_1076_est_evaluable_par_surcharge():
    assert P.evaluabilite(MV71) == "surcharge", (
        "1076 n'est plus evaluable par surcharge (%s) : le port redevient permissif"
        % P.evaluabilite(MV71))


def test_1076_pose_le_bit_dans_SES_DEUX_masques():
    """Le bit vit a DEUX endroits pour 1076, et les deux comptent : le masque du REGISTRE (voie
    `turnflow`) et celui de `NORMAL_ATTACK_TARGETING_OPTIONS_BY_TYPE` (voie attaque normale). Sans
    le bit, la cascade n'appelle JAMAIS la regle -- permissif en silence."""
    opts = P.targeting_options_for(MV71)
    assert opts is not None and opts.has(TR.TargetMatchesDynamicRule)
    par_type = NORMAL_ATTACK_TARGETING_OPTIONS_BY_TYPE.get(MV71)
    assert par_type is not None and par_type.has(TR.TargetMatchesDynamicRule)


def test_1076_est_le_SEUL_type_d_attaque_normale_a_declarer_le_corps():
    """L'aiguillage de `_NormalAttackTargeting` est DERIVE (`'...' in klass.__dict__`), donc il
    s'applique a tout type qui declarerait le corps. Cette mesure dit lesquels : aujourd'hui 1076
    et lui seul. Le jour ou un autre type entre au registre AVEC sa surcharge, ce test rougit et
    demande qu'on CONFRONTE ce nouveau corps -- il ne doit pas etre wire en silence."""
    declarants = sorted(
        aid for aid in NORMAL_ATTACK_TARGETING_OPTIONS_BY_TYPE
        if (ABILITY_CLASSES.get(int(aid)) is not None
            and "get_dynamic_invalid_target_reason" in ABILITY_CLASSES[int(aid)].__dict__))
    assert declarants == [MV71], (
        "la liste des types d'attaque normale a surcharge a change : %s" % declarants)


# ================================================================================================
# 2. LE CODE RENDU
# ================================================================================================

def test_le_refus_est_ValidRequest_et_PAS_TargetMatchesDynamicRule():
    """`MV71SniperDroneSquadAttackAbility$$GetDynamicInvalidTargetReason` rend le litteral `1`.
    C'est CONTRE-INTUITIF (les autres regles dynamiques rendent `2`) et c'est mesure live :
    l'oracle a rendu `0x1 [ValidRequest]`. Un port qui aurait recopie `2` propagerait un code faux."""
    assert REFUS == 1 and int(TR.ValidRequest) == 1
    assert _regle(SATURE) == REFUS
    assert _regle(SATURE) != int(TR.TargetMatchesDynamicRule)


# ================================================================================================
# 3. LA BASCULE -- le COMPTE du disque, pas la distance
# ================================================================================================

def test_bascule_disque_sature_vs_une_tuile_libre():
    """MEME caster, MEME cible, MEME distance (2) : seule l'occupation change."""
    assert _regle(SATURE) == REFUS, "disque sature : le natif refuse, le port doit refuser"
    assert _regle(UNE_LIBRE) == 0, "une tuile libre suffit : le natif accepte"
    st_a, st_b = _substrat(SATURE, 4), _substrat(UNE_LIBRE, 4)
    from engine.runner.components import PositionComponent                 # noqa: PLC0415
    for st in (st_a, st_b):
        cp = st.get_entity(U_CASTER).get_component(PositionComponent)
        tp = st.get_entity(U_CIBLE).get_component(PositionComponent)
        assert hexgeo.distance((cp.col, cp.row), (tp.col, tp.row)) == 2, (
            "la DISTANCE doit etre invariante entre les deux bras, sinon elle est le decideur")


def test_la_cible_nulle_ne_refuse_pas():
    """`target != null` est une CONJONCTION du corps natif : sans cible, il rend `0`."""
    assert _regle(SATURE, target_id=None) == 0


# ================================================================================================
# 4. LE BRAS MELEE -- que le live n'atteint pas
# ================================================================================================

def test_bras_melee_court_circuite_le_disque_sature():
    """Cible ADJACENTE : `IsMeleeAttack(entities)` est evalue AVANT `PickTile` et rend `0` MEME
    quand aucune tuile de spawn n'existe. Aucun montage live ne produit ce regime (il faudrait
    saturer le disque d'une cible au contact du caster, sur un board qui l'autorise)."""
    from engine.runner.abilities.loki.mv71 import _is_melee_attack         # noqa: PLC0415
    st = _substrat(MELEE, 4)
    assert _is_melee_attack(st, U_CASTER, U_CIBLE) is True
    assert _regle(MELEE) == 0
    # ... et le disque EST bien sature dans ce substrat : sinon le `0` viendrait de `PickTile`.
    from engine.runner.abilities.loki.mv71 import _pick_tile               # noqa: PLC0415
    assert _pick_tile(st, U_CASTER, U_CIBLE, DRONE, MAX_SUMMONS_MESURE, first_only=True) is None


def test_le_predicat_melee_est_le_MEME_foyer_que_le_dispatch_d_execution():
    """Le natif appelle la MEME methode `IsMeleeAttack` dans son gate et dans `ExecuteBehaviour`.
    Le port ne doit pas pouvoir les faire diverger : `execute_behaviour` doit consommer le foyer."""
    src = (PY / "engine" / "runner" / "abilities" / "loki" / "mv71.py").read_text(encoding="utf-8")
    corps = src.split("def execute_behaviour", 1)[1]
    assert "_is_melee_attack(state, caster_id, target_id)" in corps, (
        "`execute_behaviour` n'appelle plus le foyer `_is_melee_attack` : le dispatch d'execution "
        "et le gate de ciblage peuvent diverger")


# ================================================================================================
# 5. L'AIGUILLAGE DE `_NormalAttackTargeting` -- la cause du trou
# ================================================================================================

def test_le_porteur_d_attaque_normale_aiguille_vers_la_surcharge_de_1076():
    st = _substrat(SATURE, 4)
    assert normal_attack_type_for(st, U_CASTER) == MV71, (
        "l'attaque normale de `%s` n'est plus 1076 : l'aiguillage ne se mesure plus" % PORTEUR)
    assert _regle_attaque_normale(SATURE) == REFUS, (
        "la voie ATTAQUE NORMALE rend encore la regle de la BASE : c'est le trou de #287-r11-r2")
    assert _regle_attaque_normale(UNE_LIBRE) == 0


def test_un_caster_generique_garde_la_regle_de_la_BASE():
    """L'aiguillage ne doit rien changer pour les 17 autres types : leur regle reste celle
    d'`ALoki_NormalAttackAbility` (test d'ARME), au CODE PRES.

    `ultraTitus` est mele-seul : a d=2 la base ne trouve aucune arme et refuse `2
    TargetMatchesDynamicRule` ; AU CONTACT elle accepte. Les deux bras sont mesures, et le code
    rendu est confronte au FOYER de la base -- ce qui rend le test insensible a l'evolution du
    catalogue tout en disant que ce n'est PAS le corps de 1076 (`1 ValidRequest`) qui repond."""
    from engine.runner.abilities.targeting import (                        # noqa: PLC0415
        normal_attack_dynamic_invalid_target_reason as base)
    loin = [(U_CASTER, "ultraTitus", 1, 2), (U_CIBLE, "necroWarden", 2, 0),
            (U_A, "ultraTitus", 1, 1), (U_B, "ultraTitus", 1, 3)]
    contact = [(U_CASTER, "ultraTitus", 1, 1), (U_CIBLE, "necroWarden", 2, 0),
               (U_A, "ultraTitus", 1, 2), (U_B, "ultraTitus", 1, 3)]
    for unites in (loin, contact):
        st = _substrat(unites, 4)
        assert normal_attack_type_for(st, U_CASTER) == GENERIQUE
        attendu = int(base(st, U_CASTER, U_CIBLE) or 0)
        assert _regle_attaque_normale(unites) == attendu, (
            "un caster generique ne recoit plus la regle de la BASE")
        assert _regle_attaque_normale(unites) != REFUS, (
            "un caster generique recoit le code de 1076 : l'aiguillage deborde")
    # NON-DEGENERESCENCE : les deux bras de la base doivent DIFFERER, sinon l'egalite ci-dessus
    # serait obtenue par un `0` partout et ne dirait rien.
    assert _regle_attaque_normale(loin) != _regle_attaque_normale(contact)


# ================================================================================================
# 6. LE RAYON -- derive du CATALOGUE
# ================================================================================================

def test_le_rayon_du_drone_est_derive_du_catalogue(monkeypatch):
    from engine.runner.abilities.loki import mv71                          # noqa: PLC0415
    assert mv71._drone_attack_range(DRONE) == RAYON_DRONE_MESURE
    consts = (GC.ability(mv71.CONFIG) or {}).get("constants") or {}
    assert consts.get("unitId") == DRONE
    assert int(consts.get("maxSummons")) == MAX_SUMMONS_MESURE
    # MUTANT DE SOURCE : si le rayon etait une constante ecrite au site, ce patch ne mordrait pas.
    monkeypatch.setattr(GC, "unit", lambda uid: {"weapons": [{"Range": 1}]})
    assert mv71._drone_attack_range(DRONE) == 1, "le rayon ne vient PAS du catalogue"


def test_une_arme_sans_portee_vaut_UN_pas_zero(monkeypatch):
    """`HasValue ? Value : 1` -- LU dans `IsTargetInAttackRangeForSummon`. Un `0` ferait rendre un
    disque VIDE et refuserait tout. Le catalogue courant n'exerce pas ce bras seul (le drone a une
    arme portee 4), donc le substrat est FABRIQUE -- et on assertionne d'abord qu'il l'est."""
    reel = [w.get("Range") for w in (GC.unit(DRONE) or {}).get("weapons") or []]
    assert any(r for r in reel), "le catalogue exerce deja ce bras : le mutant ne dit plus rien"
    from engine.runner.abilities.loki import mv71                          # noqa: PLC0415
    monkeypatch.setattr(GC, "unit", lambda uid: {"weapons": [{"Range": None}, {}]})
    assert mv71._drone_attack_range(DRONE) == 1


# ================================================================================================
# 7. MUTANTS EN DELTA -- desarmee, la bascule doit s'effondrer
# ================================================================================================

def test_desarmee_la_bascule_s_effondre_sur_LES_DEUX_voies():
    """`P.desarme(1076)` retire la surcharge de la classe -- ce qui desarme AUSSI l'aiguillage de
    `_NormalAttackTargeting` (il lit `klass.__dict__`). Le port revient a ce qu'il faisait avant
    cette tranche : `0` partout, y compris sur le disque sature. C'est la VUE ROUGE, et le live la
    mesure aussi (`probe_287r11r2` : 2 SOUS-refus sous temoin)."""
    with P.desarme(MV71):
        assert _regle(SATURE) == 0, "le desarmement ne mord pas : la mesure ne prouve rien"
        assert _regle_attaque_normale(SATURE) == 0
    assert _regle(SATURE) == REFUS, "le desarmement n'a pas ete restaure"
    assert _regle_attaque_normale(SATURE) == REFUS
