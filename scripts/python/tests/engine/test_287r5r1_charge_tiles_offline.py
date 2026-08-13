"""#287-r5-r1 -- la garde OFFLINE des trois regles « tuiles de mouvement du caster ».

Le probe live (`probe_287r5r1_charge_tiles_live.py`) confronte au natif ; ce fichier GARDE ce que la
confrontation a etabli, et couvre le SEUL bras que le live ne peut pas exercer.

CINQ ETAGES :

 1. RECENSEMENT BI-CANAL -- les trois ids sont EVALUABLES, chacun par son canal. Le recensement
    reste bi-canal (etage NON-REGRESSION en fin de fichier), mais LE CANAL DE 1204 A CHANGE : #508
    a porte sa face COMBAT, donc son masque et sa regle ont MIGRE de `TARGETING_OPTIONS_UNPORTED` /
    `DYNAMIC_TARGET_RULE_UNPORTED` vers `LeadingTheChargeAbility`. Ce fichier gardait
    « 1204 n'a AUCUNE classe portee » -- un fait de CADENCE, pas une loi native. Ce qu'il garde
    desormais est la loi : les trois restent EVALUABLES, et la regle de 1204 n'a toujours qu'UN
    SEUL mirror (la surcharge DELEGUE au foyer, elle ne recopie pas son corps).
 2. BASCULE -- chaque regle DISCRIMINE : un substrat qui refuse, un substrat qui passe. Les deux ne
    different que par la grandeur que le corps natif LIT (la distance, l'adjacence, l'empreinte).
 3. MUTANTS, en DELTA -- la regle DESARMEE doit LACHER le refus qu'elle produisait
    (`avant == refus` ET `apres == 0`). Le seul `apres == 0` serait vert sur un port qui n'evalue
    rien.
 4. LA CLAUSE D'EMPREINTE DE 1151, que le LIVE N'EXERCE PAS -- cause MESUREE, pas supposee : le seul
    occupant multi-hex atteignable serait une MoW, et une MoW arrive au runner NON DEPLOYEE
    (`decisionView.mows[].pos is None`, mesure du 2026-08-06 sur `MC1_67` / `ultraDreadnought`),
    donc elle n'occupe aucune tuile. Le bras « empreintes EGALES -> 0 » est, lui, confronte live
    (deux allies a 1 pied, `natif = 0x0` et port `0x0`). Ici on tient les DEUX bras.
 5. LA TUILE DE DEPART, hors du pool sous `ignoreUnitsOnTiles` -- le cran trouve PAR le live :
    `BasePathfinder.u003CIterateReachableTilesu003Ed__12$$MoveNext` n'emet pas le depart (sa branche
    `depth == 1` rend `GetValidNeighbours` et rien d'autre), la ou le `visited` du port l'incluait.
    L'ecart etait INOBSERVABLE tant qu'aucun call-site ne posait ce booleen.

ASCII only.
"""
from __future__ import annotations

import sys
import textwrap
from pathlib import Path

HERE = Path(__file__).resolve()
PY = HERE.parents[2]
if str(PY) not in sys.path:
    sys.path.insert(0, str(PY))

import probe_287r4r1_dynamic_target_rules as P                             # noqa: E402
from engine.entities.active_ability_type import ActiveAbilityType          # noqa: E402
from engine.entities.pathfinding.board import Board                        # noqa: E402
from engine.runner.abilities.targeting import (DYNAMIC_TARGET_RULE_UNPORTED,  # noqa: E402
                                               is_invalid_target)
from engine.runner.abilities.targeting_rule import TargetingRule as TR     # noqa: E402
from engine.runner.abilities.handler import ABILITY_CLASSES                # noqa: E402
from engine.runner.snapshot import load_state                              # noqa: E402
import hexgeo                                                              # noqa: E402

QUICKENING = int(ActiveAbilityType.TheQuickening)          # 1151
VIGILANCE = int(ActiveAbilityType.VigilanceEternal)        # 1202
LEADING = int(ActiveAbilityType.LeadingTheCharge)          # 1204
TRIO = (QUICKENING, VIGILANCE, LEADING)


COLS, ROWS = 9, 9


def _tid(col: int, row: int) -> int:
    return col * ROWS + row + 1


def _board(cols=COLS, rows=ROWS) -> Board:
    """Un plateau PLAT et entierement marchable -- aucun terrain ne doit departager : ce que ces
    etages mesurent est la DISTANCE, l'ADJACENCE et l'EMPREINTE, pas le pathfinding (deja garde
    ailleurs)."""
    out = []
    for col in range(cols):
        for row in range(rows):
            nb = [_tid(c, r) for (c, r) in hexgeo.neighbors(col, row)
                  if 0 <= c < cols and 0 <= r < rows]
            out.append({"id": _tid(col, row), "col": col, "row": row, "elevation": 0,
                        "walkable": True, "isWall": False, "neighbours": nb})
    return Board(out, adjacency="evenq")


def _state(board, unites):
    """`unites` = [(id, (col,row), team, feet|None)] -> `State` runner, monte par le MEME chemin que
    le live (`snapshot.load_state`), donc avec les memes composants et les memes conventions.

    `feet` non nul = unite MULTI-HEX : les pieds passent par le canal `observeBattle` (UNE LIGNE PAR
    PIED, cf. `snapshot._load_feet`), le seul que le port lit -- pas par une ecriture directe du
    composant, qui court-circuiterait le recalage de la `PositionComponent` sur `feet[0]`."""
    dv = {"currentPlayer": 1, "units": [
        {"id": uid, "visualId": "u%d" % uid, "alive": True, "team": team, "owner": team,
         "pos": {"col": pos[0], "row": pos[1]}, "effects": []}
        for (uid, pos, team, _feet) in unites]}
    ob_units = []
    for uid, pos, _team, feet in unites:
        if feet:
            for i, (c, r) in enumerate(feet):
                ob_units.append({"squadId": uid, "entityId": uid * 100 + i,
                                 "col": c, "row": r, "hp": 100, "hpMax": 100})
        else:
            ob_units.append({"squadId": uid, "entityId": uid * 100,
                             "col": pos[0], "row": pos[1], "hp": 100, "hpMax": 100})
    snap = {"units": [{"entityId": uid, "traits": []} for (uid, _p, _t, _f) in unites]}
    return load_state(dv, {"units": ob_units}, snap, board=board)


def _reason(st, caster, cible, aid) -> int:
    return int(is_invalid_target(st, caster, cible, P._porteur(aid)) or 0)


# ================================================================================================
# 1. RECENSEMENT BI-CANAL
# ================================================================================================

def test_les_trois_ids_sont_evaluables_chacun_par_son_canal():
    """L'INVARIANT -- les trois ids sont EVALUABLES ; le CANAL, lui, suit la cadence de portage.

    1204 a bascule `table` -> `surcharge` avec #508 (`8dd377ef`). Cette version-ci ne CONSTATE pas
    le nouveau canal en remplacant un litteral par un autre : le seul canal interdit est `aucune`,
    et c'est ce que l'assertion exprime. Le contrat de DISJONCTION qui rend la bascule propre
    (1204 sortie des deux tables « non portee ») est garde par
    `tests/engine/runner/test_508_leading_the_charge_offline.py::test_1204_est_au_registre_et_a_UNE
    _seule_source_de_masque` -- on ne le duplique pas ici."""
    for aid in TRIO:
        # `in ETATS_EVALUABLES`, et non `!= "aucune"` (#1015) : depuis que la partition nomme ses
        # DEFAUTS, `perdue` designe justement une regle mirroree que plus rien n'appelle. Un critere
        # « different de aucune » la laisserait passer pour evaluable -- alors que c'est exactement
        # la degradation permissive que cette assertion a pour but d'interdire.
        assert P.evaluabilite(aid) in P.ETATS_EVALUABLES, (
            "%d n'est plus EVALUABLE (%s) : sa regle dynamique a disparu des DEUX canaux (ni "
            "surcharge de classe, ni entree de `DYNAMIC_TARGET_RULE_UNPORTED`), ou bien elle y est "
            "ecrite sans etre appelee. Le bit `TargetMatchesDynamicRule` de son masque est alors un "
            "gate DESARME, et la degradation est PERMISSIVE -- le moteur accepterait des cibles que "
            "le natif refuse." % (aid, P.evaluabilite(aid)))
    assert LEADING in P.ids_portant_le_bit(), (
        "1204 ne porte plus `TargetMatchesDynamicRule` dans son masque effectif : ce fichier ne "
        "mesure alors plus rien sur elle.")


def test_la_regle_de_1204_n_a_toujours_qu_UN_SEUL_mirror():
    """LE CRAN QUE LA MIGRATION DE #508 A RENDU NECESSAIRE, et que rien d'autre ne tient.

    `LeadingTheChargeAbility.get_dynamic_invalid_target_reason` DELEGUE a
    `_dynamic_rule_leading_the_charge` (`runner/abilities/targeting.py`), qui reste l'UNIQUE mirror
    de `...LeadingTheChargeAbility$$GetDynamicInvalidTargetReason` -- sa propre docstring le
    prescrit : « Dupliquer le corps ici en ferait deux, qui divergeraient. »

    `test_508...::test_la_classe_surcharge_bien_la_regle_dynamique` verifie qu'elle SURCHARGE, pas
    qu'elle DELEGUE : une recopie locale du corps y passerait au vert, serait indistinguable
    AUJOURD'HUI, et divergerait au premier correctif applique d'un seul cote (c'est la contre-epreuve
    deja mesuree en #643/#646 sur un autre foyer). D'ou une assertion sur le SOURCE.

    Par AST et pas par grep : la docstring de la methode CITE le nom du foyer, donc un critere par
    chaine resterait vert sur une methode qui ne l'appelle plus."""
    import ast
    import inspect
    klass = ABILITY_CLASSES[LEADING]
    src = inspect.getsource(klass.get_dynamic_invalid_target_reason)
    tree = ast.parse(textwrap.dedent(src))
    appels = {n.func.id for n in ast.walk(tree)
              if isinstance(n, ast.Call) and isinstance(n.func, ast.Name)}
    assert "_dynamic_rule_leading_the_charge" in appels, (
        "`%s.get_dynamic_invalid_target_reason` n'APPELLE plus `_dynamic_rule_leading_the_charge` : "
        "le mirror de `...LeadingTheChargeAbility$$GetDynamicInvalidTargetReason` est recopie "
        "localement. Meme a l'identique, c'est la SECONDE source que la migration de #508 avait "
        "pour but d'eviter. Appels vus : %r" % (klass.__name__, sorted(appels)))


# ================================================================================================
# 2. BASCULE + 3. MUTANTS (en DELTA)
# ================================================================================================

def _bascule_portee(aid: int, d_proche: int, d_loin: int):
    """Deux substrats a UNE grandeur d'ecart : la DISTANCE caster -> cible. Le caster est en (0,0)."""
    b = _board()
    proche = _state(b, [(1, (0, 0), 1, None), (2, (d_proche, 0), 2, None)])
    loin = _state(b, [(1, (0, 0), 1, None), (2, (d_loin, 0), 2, None)])
    return _reason(proche, 1, 2, aid), _reason(loin, 1, 2, aid)


def test_bascule_vigilance_1202_par_la_distance():
    # `range` = 2 : une cible a 2 est chargeable (tuile libre adjacente atteignable), une cible a 8
    # ne l'est pas -> `TargetIsInRange`.
    ok, ko = _bascule_portee(VIGILANCE, 2, 8)
    assert ok == 0, "cible chargeable : la regle doit laisser passer, rendu %s" % hex(ok)
    assert ko & int(TR.TargetIsInRange), "cible hors d'atteinte : %s" % hex(ko)


def test_bascule_leading_1204_par_la_distance():
    # `range` = 4 : meme forme, seuil plus large -- et AUCUN court-circuit d'adjacence.
    ok, ko = _bascule_portee(LEADING, 4, 8)
    assert ok == 0, "cible chargeable : %s" % hex(ok)
    assert ko & int(TR.TargetIsInRange), "cible hors d'atteinte : %s" % hex(ko)


def test_le_court_circuit_d_adjacence_est_PROPRE_a_1202():
    """La difference STRUCTURELLE entre les deux regles qui partagent l'etage, mesuree sur le MEME
    substrat : une cible ADJACENTE mais dont AUCUNE tuile adjacente n'est libre.

    1202 rend `0` par son court-circuit `AreEntitiesAdjacent(casterTiles, targetTiles)` -- le natif
    retourne AVANT d'appeler le selecteur. 1204, lui, n'a pas ce court-circuit ; son verdict passe
    donc par l'etage TUILES, et le masque `TargetIsNotAdjacent` l'ecarte de toute facon en amont.
    Si un jour les deux regles etaient fusionnees « puisqu'elles partagent l'etage », ce test
    rougirait."""
    b = _board(3, 3)
    # caster (1,1), cible (1,0) ADJACENTE, et TOUTES les autres tuiles du 3x3 occupees par des
    # bloqueurs -> aucune tuile de charge libre.
    unites = [(1, (1, 1), 1, None), (2, (1, 0), 2, None)]
    uid = 10
    for c in range(3):
        for r in range(3):
            if (c, r) in {(1, 1), (1, 0)}:
                continue
            unites.append((uid, (c, r), 2, None))
            uid += 1
    st = _state(b, unites)
    assert _reason(st, 1, 2, VIGILANCE) == 0, "1202 doit court-circuiter sur une cible adjacente"
    assert _reason(st, 1, 2, LEADING) != 0, "1204 n'a PAS de court-circuit d'adjacence"


def test_mutants_en_delta_les_trois_regles_mordent():
    """`avant == refus` ET `apres == 0` -- le seul `apres == 0` serait vert sur un port inerte.

    ⚠ LE COUPLE DOIT ETRE CELUI OU **SEULE** LA REGLE DECIDE, et c'est ce que la premiere ecriture de
    ce test avait rate : pour 1151 une tuile a d=8 est deja refusee par le volet PORTEE STATIQUE
    (`RANGE_FROM_CONFIG` -> `overrideRange = constants.range = 2`), donc desarmer la regle ne
    retirait RIEN et le mutant accusait le protocole au lieu du port. On vise donc la tuile du
    CASTER : elle est DANS la portee statique (d = 0), et seule la regle la refuse -- exactement le
    couple que le live a mesure (`natif = 0x8000000` sur `tgt d=0 occupee:bloodMephiston`)."""
    b = _board()
    cas = [(VIGILANCE, _state(b, [(1, (0, 0), 1, None), (2, (8, 0), 2, None)]), 2),
           (LEADING, _state(b, [(1, (0, 0), 1, None), (2, (8, 0), 2, None)]), 2),
           (QUICKENING, _state(b, [(1, (2, 2), 1, None)]), b.id_at(2, 2))]
    for aid, st, cible in cas:
        avant = _reason(st, 1, cible, aid)
        assert avant & int(TR.TargetIsInRange), "%d : pas de refus AVANT (%s)" % (aid, hex(avant))
        with P.desarme(aid):
            apres = _reason(st, 1, cible, aid)
        assert apres == 0, "%d : la mutation n'a RIEN retire (apres=%s)" % (aid, hex(apres))


# ================================================================================================
# 4. LA CLAUSE D'EMPREINTE DE 1151 -- le bras que le live n'exerce pas
# ================================================================================================

def test_quickening_1151_empreinte_egale_accepte_differente_refuse():
    """`GetFeetCount(GetUnit(target)) != GetFeetCount(caster) -> TargetMatchesDynamicRule`.

    Deux substrats a UNE grandeur d'ecart : le NOMBRE DE PIEDS de l'occupant ALLIE de la tuile visee
    (le pathfinding traverse les allies, pas les ennemis -- c'est pour cela que l'occupant doit etre
    ami). Meme position, meme distance, meme camp : seule l'empreinte change.

    Le bras EGAL est aussi confronte LIVE (`natif = 0x0` sur deux allies a 1 pied, `MC1_67`) ; le
    bras DIFFERENT ne l'est pas, faute d'occupant multi-hex atteignable au runner."""
    b = _board()
    # caster (0,0) 1 pied ; allie sur (1,0), a portee de mouvement (`range` = 2).
    egal = _state(b, [(1, (0, 0), 1, None), (2, (1, 0), 1, None)])
    diff = _state(b, [(1, (0, 0), 1, None), (2, (1, 0), 1, [(1, 0), (1, 1), (2, 0)])])
    cible = b.id_at(1, 0)
    r_egal = _reason(egal, 1, cible, QUICKENING)
    r_diff = _reason(diff, 1, cible, QUICKENING)
    assert r_egal == 0, "empreintes EGALES : l'echange doit passer, rendu %s" % hex(r_egal)
    assert r_diff & int(TR.TargetMatchesDynamicRule), \
        "empreintes DIFFERENTES : %s" % hex(r_diff)
    # ... et c'est bien LA REGLE qui le produit, pas un autre etage du masque.
    with P.desarme(QUICKENING):
        assert _reason(diff, 1, cible, QUICKENING) == 0


def test_quickening_1151_une_tuile_LIBRE_a_portee_passe():
    """Contre-epreuve de non-vacuite du test precedent : sans occupant, la meme tuile passe. Sans
    lui, un port qui refuserait TOUTE tuile rendrait le bras `diff` vert par accident."""
    b = _board()
    st = _state(b, [(1, (0, 0), 1, None)])
    assert _reason(st, 1, b.id_at(1, 0), QUICKENING) == 0


# ================================================================================================
# 5. LA TUILE DE DEPART, HORS DU POOL SOUS `ignoreUnitsOnTiles`
# ================================================================================================

def test_la_tuile_du_caster_est_refusee_par_1151():
    """Le cran trouve PAR la confrontation live : le natif refuse la tuile du caster par
    `TargetIsInRange` (mesure `MC1_67`, `tgt d=0 occupee:bloodMephiston`), parce que
    `BasePathfinder.u003CIterateReachableTilesu003Ed__12$$MoveNext` n'emet pas le depart. Le
    `visited` du port l'incluait -- il ne l'inclut plus SOUS `ignore_units_on_tiles`."""
    b = _board()
    st = _state(b, [(1, (2, 2), 1, None)])
    r = _reason(st, 1, b.id_at(2, 2), QUICKENING)
    assert r & int(TR.TargetIsInRange), "la tuile du caster doit etre refusee, rendu %s" % hex(r)


def test_le_noeud_movable_tiles_in_range_n_emet_pas_le_depart():
    """Le meme cran, UN ETAGE PLUS BAS -- sur le noeud lui-meme, pour que la garde survive a une
    refonte du call-site. Sous `ignore_units_on_tiles`, le pool s'ELARGIT (les tuiles occupees y
    entrent) mais le DEPART reste dehors."""
    from engine.entities.selectors.accessors import CasterTile, SelectTile
    from engine.entities.selectors.tiles import Caster, MovableTilesInRange
    from engine.dsl.base import Const
    from engine.runner.abilities.behaviours.context import entities_from_state
    b = _board()
    st = _state(b, [(1, (2, 2), 1, None), (2, (3, 2), 1, None)])
    ents = entities_from_state(st, 1, None)
    depart = b.id_at(2, 2)
    voisin_occupe = b.id_at(3, 2)
    large = MovableTilesInRange(Caster(), SelectTile(CasterTile()), Const(2),
                                ignore_flags=True, ignore_units_on_tiles=True).evaluate(ents)
    etroit = MovableTilesInRange(Caster(), SelectTile(CasterTile()), Const(2),
                                 ignore_flags=True, ignore_units_on_tiles=False).evaluate(ents)
    assert depart not in large, "le DEPART ne doit pas entrer dans le pool"
    assert depart not in etroit
    # non-vacuite : le booleen elargit REELLEMENT quelque chose (sinon le test ci-dessus serait vrai
    # pour une mauvaise raison).
    assert voisin_occupe in large and voisin_occupe not in etroit, \
        "ignore_units_on_tiles doit faire entrer les tuiles OCCUPEES"


# ================================================================================================
# NON-REGRESSION : les entrees deja portees n'ont pas bouge
# ================================================================================================

def test_le_recensement_partitionne_et_chaque_canal_PEUPLE_est_EXERCE():
    """CE QUE CETTE GARDE A REMPLACE, ET POURQUOI (#1015).

    Elle exigeait `any(evaluabilite(a) == "table")` -- un recensement BI-CANAL. Ce critere a expire
    PARCE QUE LE TRAVAIL A ETE FAIT : #996 (`b061a916`) a porte la face COMBAT de `1185
    ForwardObservers`, dernier occupant de `DYNAMIC_TARGET_RULE_UNPORTED`, et le canal `table` est
    tombe a zero. `master` en est reste rouge. Remonter le seuil, ou nommer un autre id, n'aurait
    fait que reporter la meme peremption : le peuplement d'un canal SUIT la cadence de portage, il
    ne peut pas etre un invariant.

    L'INVARIANT QU'ELLE APPROXIMAIT tient en trois points, tous independants de la cadence :

      (a) le recensement est une PARTITION -- tout id posant le bit sort dans exactement un `ETATS`,
          et la somme des etats redonne le tout. Un etat inconnu sort sous son nom, jamais
          silencieusement en « non couvert » ;
      (b) les canaux sont DISJOINTS -- aucun id n'est declare dans les deux a la fois (`ambigu`), et
          aucune regle mirroree n'est rendue inatteignable par une classe qui ne surcharge pas
          (`perdue`). C'est le defaut REEL que le seuil masquait : 1185 etait dans les deux canaux,
          et `evaluabilite` l'absorbait par priorite silencieuse ;
      (c) tout canal PEUPLE est EXERCE par au moins un bras de mesure, et reciproquement. C'est ce
          que « bi-canal » voulait dire : que la mesure ne cesse pas de voir un canal vivant. A table
          vide, `canaux_peuples` et `canaux_exerces` perdent `table` ENSEMBLE et l'egalite tient ;
          si la table se REPEUPLAIT sans qu'aucun bras ne l'exerce, elle rougirait.

    ⚠ ET LE TEST ASSERTIONNE SON PROPRE NON-VIDE. Une egalite entre deux ensembles VIDES serait verte
    pour rien -- c'est la faute exacte deja mesuree ailleurs dans ce depot (un test « les ordinaux
    communs nomment autre chose » rendu vert par un ensemble vide). On exige donc que les deux
    ensembles soient non vides AVANT de les comparer."""
    ids = P.ids_portant_le_bit()
    assert ids, "recensement VIDE : un recenseur qui ne visite rien ne peut rien rendre"
    etats = {a: P.evaluabilite(a) for a in ids}

    # (a) PARTITION -- exhaustive, et sans etat hors nomenclature.
    inconnus = sorted({e for e in etats.values()} - set(P.ETATS))
    assert inconnus == [], (
        "etats hors de la partition `P.ETATS` : %r -- un canal inconnu doit sortir sous son nom, "
        "jamais etre absorbe dans un etat voisin" % inconnus)
    par_etat = {e: [a for a, v in etats.items() if v == e] for e in P.ETATS}
    assert sum(len(v) for v in par_etat.values()) == len(ids)

    # (b) DISJONCTION -- les deux etats de DEFAUT sont vides.
    assert par_etat["ambigu"] == [], (
        "ids declares dans les DEUX canaux : %r. L'entree de `DYNAMIC_TARGET_RULE_UNPORTED` y est "
        "INATTEIGNABLE (le porteur est la classe), donc c'est un second mirror du meme corps natif, "
        "que rien ne consulte et qui divergera au premier correctif applique d'un seul cote."
        % par_etat["ambigu"])
    assert par_etat["perdue"] == [], (
        "ids dont la regle mirroree est PERDUE : %r. Une entree de table existe, mais la classe "
        "portee capture le porteur SANS surcharger -> le mirror n'est jamais appele et l'id devient "
        "PERMISSIF en silence." % par_etat["perdue"])

    # Les trois ids de ce fichier restent evaluables (le canal, lui, peut migrer).
    for aid in TRIO:
        assert etats[aid] in P.ETATS_EVALUABLES, (
            "%d n'est plus EVALUABLE (%s)" % (aid, etats[aid]))

    # (c) canaux PEUPLES == canaux EXERCES, les deux non vides.
    peuples = {e for e in ("surcharge", "table") if par_etat[e]}
    exerces = P.canaux_exerces() & {"surcharge", "table"}
    assert peuples, "aucun canal de portage peuple : plus AUCUNE regle n'est evaluable"
    assert exerces, "aucun bras de `P.CAS` n'exerce un canal de portage : la mesure est vide"
    assert peuples == exerces, (
        "canaux PEUPLES %r != canaux EXERCES par les bras de mesure %r. Un canal peuple mais non "
        "exerce peut se vider sans qu'aucune bascule ne tombe ; un canal exerce mais non peuple "
        "signale un bras qui porte sur un id ayant migre." % (sorted(peuples), sorted(exerces)))
