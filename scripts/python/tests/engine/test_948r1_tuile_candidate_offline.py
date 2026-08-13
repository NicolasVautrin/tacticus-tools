"""#948-r1 -- les DEUX compteurs d'`EnmityForTheUnworthy` suivent la TUILE CANDIDATE.

CE QUE LA LECTURE A TRANCHE
----------------------------
Le residu supposait que le natif << re-evalue par tuile simulee >>, en citant
`SimulateEffectsOperation$$RefreshSimulatedEffects`. Ce corps-la ne fait que re-poser les effets ;
ce n'est pas lui qui repositionne. Le DEPLACEMENT est dans son appelant, lu VERBATIM sur
`rnca9r7q6c` -- `IdunBattle.Operations.SimulateEffectsOperation$$DoActionInSimulatedTile` :

    if (!UnitExtensions.IsDead(unit, state)) {
        originalTiles = EntityExtensions.GetTiles(unit, state)      # sauvegarde
        flags.Add(1) ; SetMovedFlag(unit, state)
        processor->slot(+0x65)(processor, unit, tile, &out)         # <- L'UNITE EST POSEE SUR `tile`
        added = SimulateMoveUnitTriggers(this, unit, node, tile)
        RefreshSimulatedEffects(this)                               # <- les effets sont re-poses
        action.Invoke(...)                                          # <- LA PREDICTION S'EXECUTE ICI
        ResetAddedEffects(this, added) ; <restauration complete>
    }

L'entite est donc PHYSIQUEMENT sur la tuile candidate pendant l'action. `AdjacentUnits(Owner)`
descend sur `EntityExtensions$$IterateTiles(owner)` : il lit la tuile CANDIDATE, pas la reelle.
L'enonce du residu etait donc JUSTE, mais pour une raison qu'il ne nommait pas.

CE QUE LA GARDE TIENT
----------------------
1. le compteur CHANGE quand on threade une tuile candidate (temoin NON NUL exige des deux cotes) ;
2. la DEUXIEME geometrie -- une amplitude ne s'estime pas depuis une seule configuration ;
3. l'absence de `at_pos` rend EXACTEMENT la position courante (non-regression) ;
4. les DEUX vecteurs de prediction (attaque normale ET ability) threadent la tuile, sinon le fork
   se deplace au lieu de disparaitre ;
5. un porteur MULTI-TUILES retombe sur ses pieds REELS -- degradation NOMMEE, jamais une empreinte
   inventee.
"""
from __future__ import annotations

import sys
from pathlib import Path

PYDIR = Path(__file__).resolve().parents[2]
if str(PYDIR) not in sys.path:
    sys.path.insert(0, str(PYDIR))

from engine.playbook import adjacency as _adj                # noqa: E402
from engine.playbook.scene import Scene                      # noqa: E402


# --- FIXTURES NOMMEES ---------------------------------------------------------------------------
#
# Deux geometries. Dans les deux, Forcas (`uid=1`) est le porteur ; les voisins sont poses de sorte
# que la position COURANTE et la TUILE CANDIDATE donnent des comptes DIFFERENTS -- c'est la seule
# condition qui rend la mesure concluante.

_DARK_ANGELS = 10          # `UnitFaction.DarkAngels` (0xa), la meme constante que `scene.py`


class _CtxUnite:
    def __init__(self, traits=()):
        self.traits = tuple(traits)
        self.stats = None


def _scene(unites, feet_by_id=None) -> Scene:
    """Scene MINIMALE : `Scene` est un agregat de tables, on ne monte que celles que les compteurs
    lisent. Aucun runner, aucun RPC -- le residu porte sur une recomposition PUREMENT positionnelle."""
    sc = Scene.__new__(Scene)
    sc.units = [dict(u) for u in unites]
    sc.pos_by_id = {u["id"]: u["pos"] for u in unites}
    sc.team_by_id = {u["id"]: u["team"] for u in unites}
    sc.vis_by_id = {u["id"]: u.get("visualId") for u in unites}
    sc.ctx_by_id = {u["id"]: _CtxUnite(u.get("traits", ())) for u in unites}
    sc.feet_by_id = dict(feet_by_id or {})
    # `neigh_by_pos` est une @property DERIVEE du board (memoisee) : on ne l'assigne pas, on pose
    # `board = None` -> la property rend `None` (tri-etat), et `battle_query.is_adjacent` retombe
    # sur son repli geometrique hex NOMME. C'est exactement le substrat voulu ici : le residu porte
    # sur la POSITION, pas sur la liste d'adjacence stockee.
    sc.board = None
    sc.elev_by_pos = {}
    sc.eff_state = None
    return sc


def _u(uid, col, row, team, faction_da=False, traits=(), visual=None):
    return {"id": uid, "pos": (col, row), "team": team, "alive": True,
            "visualId": visual or ("darkaCompanion" if uid == 1 else "u%d" % uid),
            "traits": traits, "_da": faction_da}


# Geometrie A -- Forcas en (5,5). Deux ennemis colles en (5,6) et (6,5) ; la tuile candidate (2,2)
# est HORS de tout contact. Compte courant 2, compte candidat 0.
GEOM_A = {
    "nom": "A -- contact rompu par le deplacement",
    "unites": [_u(1, 5, 5, team=0), _u(2, 5, 6, team=1), _u(3, 6, 5, team=1)],
    "porteur": 1, "candidate": (2, 2),
}

# Geometrie B -- l'INVERSE : Forcas isole en (0,0), et la tuile candidate (5,5) le met au contact
# de DEUX unites. Compte courant 0, compte candidat 2. Une garde qui ne jouerait que le sens
# << on s'eloigne >> laisserait passer un port qui rend 0 en toutes circonstances.
GEOM_B = {
    "nom": "B -- contact CREE par le deplacement",
    "unites": [_u(1, 0, 0, team=0), _u(2, 5, 6, team=1), _u(3, 6, 5, team=1)],
    "porteur": 1, "candidate": (5, 5),
}

GEOMETRIES = (GEOM_A, GEOM_B)


def _compte(geom, at_pos):
    sc = _scene(geom["unites"])
    return sc.enmity_adjacent_units(geom["porteur"], at_pos)


def test_etage1_et_2_le_compteur_suit_la_tuile_sur_DEUX_geometries():
    """Le compteur DOIT differer entre position courante et tuile candidate, et dans les DEUX sens.
    Chaque geometrie exige un temoin NON NUL : un couple (0, 0) ne prouverait rien."""
    vus = []
    for geom in GEOMETRIES:
        courant = _compte(geom, None)
        candidat = _compte(geom, geom["candidate"])
        vus.append((geom["nom"], courant, candidat))
        assert courant is not None and candidat is not None, geom["nom"]
        assert courant != candidat, (
            "%s : le compteur ne bouge PAS (courant=%s candidat=%s) -- la tuile candidate n'est "
            "pas threadee, ou la geometrie ne discrimine pas" % (geom["nom"], courant, candidat))
        assert max(courant, candidat) > 0, (
            "%s : TEMOIN DEGENERE, les deux comptes sont nuls" % geom["nom"])
    # Les deux SENS sont couverts : une geometrie ou le compte baisse, une ou il monte.
    baisse = [v for v in vus if v[2] < v[1]]
    monte = [v for v in vus if v[2] > v[1]]
    assert baisse and monte, "les deux SENS doivent etre couverts, vu : %s" % (vus,)


def test_etage3_sans_tuile_candidate_le_comportement_est_INCHANGE():
    """`at_pos=None` doit rendre EXACTEMENT ce que rendait le port d'avant : le compte a la
    position courante. C'est ce qui garantit que les appelants non cables n'ont pas bouge."""
    for geom in GEOMETRIES:
        sc = _scene(geom["unites"])
        attendu = sum(
            1 for u in geom["unites"]
            if u["id"] != geom["porteur"]
            and _adj.unit_in_adjacent_tiles(sc, geom["porteur"], u["id"], {}, {}))
        assert sc.enmity_adjacent_units(geom["porteur"]) == attendu, geom["nom"]


def test_etage4_les_deux_vecteurs_de_prediction_threadent_la_tuile():
    """LE fork que le fix doit eviter : si un seul des deux vecteurs (attaque NORMALE / ABILITY)
    threade `attack_pos`, la prediction se contredit elle-meme selon le type de coup.

    On lit la SOURCE des deux sites plutot que de les executer : monter les deux vecteurs complets
    demanderait un runner, et ce que la garde doit tenir ici est un CABLAGE, pas un dommage."""
    import inspect
    from engine.playbook.prediction import normal_attack, abilities
    for mod in (normal_attack, abilities):
        src = inspect.getsource(mod)
        for nom in ("enmity_adjacent_units", "enmity_adjacent_dark_angels_friends"):
            i = src.find(nom + "(")
            assert i > 0, "%s : appel a %s introuvable" % (mod.__name__, nom)
            # L'appel doit porter un SECOND argument -- la tuile candidate.
            fin = src.find(")", i)
            args = src[i + len(nom) + 1:fin]
            assert "," in args or "attack_pos" in args, (
                "%s : `%s(%s)` ne threade pas la tuile candidate" % (mod.__name__, nom, args))


def test_etage5_un_porteur_multi_tuiles_garde_ses_pieds_reels():
    """Degradation NOMMEE : aucune empreinte n'est inventee pour une entite multi-tuiles. Le
    substrat offline ne publie ni l'orientation ni la forme a la position d'arrivee, donc
    `subject_tiles_at` rend `None` et l'appelant garde les pieds REELS."""
    geom = GEOM_A
    sc = _scene(geom["unites"], feet_by_id={1: [(5, 5), (5, 4)]})
    assert _adj.subject_tiles_at(sc, 1, (2, 2)) is None, (
        "un porteur MULTI-TUILES ne doit PAS voir son empreinte reconstruite")
    # ... et le compte reste donc celui de la position reelle, threadee ou non.
    assert sc.enmity_adjacent_units(1, (2, 2)) == sc.enmity_adjacent_units(1)


def test_etage5bis_un_porteur_mono_tuile_est_bien_repositionne():
    """Le pendant NON NUL de l'etage 5 : sur un porteur a UN pied, `subject_tiles_at` rend bien la
    tuile candidate. Sans cette assertion, l'etage 5 passerait aussi si le mecanisme etait mort."""
    sc = _scene(GEOM_A["unites"])
    assert _adj.subject_tiles_at(sc, 1, (2, 2)) == [(2, 2)]
