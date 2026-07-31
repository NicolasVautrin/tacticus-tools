"""GARDES #340 (residu #322-r2) -- la face PREDICTION lit le compteur REEL de `TilesMovedThisTurn`.

CE QUI ETAIT FAUX, ET POURQUOI AUCUN TEST NE LE VOYAIT
------------------------------------------------------
`playbook/prediction/_shared.py::prediction_tiles_moved_this_turn` ouvrait sur `real = 0` en dur :
seul le PAS SIMULE etait compte. Or `IdunBattle.Entities.Formulas.TilesMovedThisTurnFormula$$
Calculate` rend `ActorStatisticsComponent+0xf0`, et
`IdunBattle.Operations.SimulateEffectsOperation$$DoActionInSimulatedTile` SAUVEGARDE ce champ avant
l'action simulee puis le RESTAURE -- donc ce que la prediction native voit vaut
`compteur REEL + tuiles du pas simule`, et une prediction depuis la tuile COURANTE
(`$$DoActionInSimulatedOnSameTile`, qui ne touche pas le composant) rend le compteur reel TOUT NU.

Les 85 paires de #322 n'ont rien vu parce qu'elles predisaient toutes AVANT tout deplacement : le
terme reel y valait zero de part et d'autre. C'est exactement pour cela que ces gardes mesurent la
MEME tuile d'attaque de part et d'autre du MEME deplacement (phases A et B du probe #340), avec
l'invariant NATIF(A) == NATIF(B) comme controle de montage.

Foyer du fix : `Scene.tiles_moved_by_id` / `Scene.tiles_moved_this_turn` (tri-etat), alimente par
`Scene.from_state` depuis l'ECS que la face COMBAT tient deja (#322-r1). MEME forme que #267
(traits) et #266 (flag `Moved`) : une face qui LIT ce que l'autre TIENT.

ASCII only.
"""
from __future__ import annotations

import pytest

import probe_340_tiles_moved_prediction as TMP


@pytest.fixture(scope="module")
def pred_case(live_session):
    """Fabrique : monte UN runner isole (bras nominaux + bras argmax) et le DISPOSE en sortie.

    Un montage qui ne s'installe pas ECHOUE, il ne skippe pas (#268) : un skip sur un regime non
    atteint est un VERT qui ment."""
    cache: dict = {}

    def _case(steps=(1, 2), board: str = TMP.P335.BOARD, seed: int = TMP.P335.SEED,
              rival_step: int | None = 2) -> dict:
        key = (tuple(steps), board, seed, rival_step)
        if key not in cache:
            res = None
            try:
                res = TMP.scenario(steps=tuple(steps), board=board, seed=seed,
                                   rival_step=rival_step)
            except RuntimeError as exc:
                pytest.fail(f"montage tiles-moved PREDICTION NON INSTALLE (board={board}, "
                            f"seed={seed}, pas={tuple(steps)}) : {exc}", pytrace=False)
            finally:
                if res is not None:
                    TMP.dispose(res)
            cache[key] = res
        return cache[key]
    return _case


@pytest.fixture(scope="module")
def nominal(pred_case):
    """MC1_67 / 909 : un pas d'UNE tuile, un pas de DEUX, plus le bras RIVAL (argmax)."""
    return pred_case()


def _arms(res, with_rival=None):
    out = [a for a in res["arms"].values()
           if with_rival is None or a["with_rival"] == with_rival]
    return sorted(out, key=lambda a: (a["with_rival"], a["steps"]))


def _same_tile_row(arm):
    return next(r for r in arm["rows_b"] if r["same_tile"])


# --------------------------------------------------------------------- controle principal
def test_prediction_after_move_matches_live(nominal):
    """CONTROLE PRINCIPAL -- apres un deplacement JOUE, la prediction du port depuis la tuile
    COURANTE est bit-exacte avec `aiPlaybookPredict`.

    C'est le regime que `real = 0` ratait : le pas simule y est NUL, donc TOUT le bonus vient du
    compteur reel."""
    for arm in _arms(nominal):
        row = _same_tile_row(arm)
        assert row["nat"] is not None, (
            "bras pas=%d : le natif ne predit RIEN depuis la tuile courante -- rien n'est mesure"
            % arm["steps"])
        assert arm["n"] > 0, (
            "bras pas=%d : le port n'a enregistre AUCUNE tuile au rejeu (n=%s)"
            % (arm["steps"], arm["n"]))
        assert row["off"] == row["nat"], (
            "bras pas=%d (n=%d) : la PREDICTION depuis la tuile courante diverge -- natif=%s "
            "port=%s (delta/borne=%s)"
            % (arm["steps"], arm["n"], row["nat"], row["off"],
               None if row["off"] is None
               else [o - x for x, o in zip(row["nat"], row["off"])]))


def test_prediction_before_move_still_matches_live(nominal):
    """NON-REGRESSION du terme deja porte -- AVANT le pas, la prediction depuis les tuiles
    candidates reste bit-exacte (le regime des 85 paires de #322). Cabler le terme reel ne doit
    RIEN changer la ou le compteur vaut zero."""
    for arm in _arms(nominal, with_rival=False):
        answered = [r for r in arm["rows_a"] if r["nat"] is not None]
        assert len(answered) >= TMP.MIN_TILES_A, (
            "bras pas=%d : le natif n'a repondu que sur %d tuile(s) en phase A -- le terme "
            "« pas simule » n'est pas exerce" % (arm["steps"], len(answered)))
        bad = [r for r in answered if r["off"] != r["nat"]]
        assert not bad, (
            "bras pas=%d : la prediction AVANT le pas diverge sur %s"
            % (arm["steps"], [(r["tile"], r["nat"], r["off"]) for r in bad][:4]))


def test_both_terms_are_the_same_sum(nominal):
    """CONTROLE DE MONTAGE -- `reel + 0` et `0 + pas simule` sont les deux moities d'une MEME somme :
    le natif doit rendre la MEME valeur en phase A et en phase B pour la meme tuile.

    Une rupture ici accuse le montage (compteur pollue par les `place()`, geometrie deplacee), pas
    le port -- et invaliderait les deux autres gardes."""
    for arm in _arms(nominal, with_rival=False):
        brk = TMP.phase_invariant_breaks(arm)
        assert not brk, (
            "bras pas=%d : NATIF(A) != NATIF(B) sur %s -- le montage ne tient pas"
            % (arm["steps"], brk[:3]))


def test_counter_is_not_vacuous(nominal):
    """GARDE DE NON-VACUITE -- avec le compteur FORCE a 0 (l'etat du port AVANT #340), la prediction
    doit DIVERGER, et vers le BAS (l'additif est positif). Sinon le controle principal comparerait
    a vide."""
    for arm in _arms(nominal):
        row = _same_tile_row(arm)
        assert row["off_zero"] is not None and row["off_zero"] != row["off"], (
            "bras pas=%d (n=%d) : forcer le compteur a ZERO rend EXACTEMENT la meme prediction (%s) "
            "-- le montage n'active pas `ModifiedExoarmour_ExtraDmg`, la garde principale ne mesure "
            "rien" % (arm["steps"], arm["n"], row["off"]))
        assert row["off_zero"][0] < row["off"][0], (
            "bras pas=%d : le compteur a ZERO rend une prediction PLUS HAUTE (%s > %s) -- "
            "l'additif `V x n` devrait etre positif" % (arm["steps"], row["off_zero"], row["off"]))


def test_count_scales_with_the_step(nominal):
    """Le compteur est THREADE, pas une constante heureuse : deux longueurs de pas doivent donner
    deux valeurs de `n` DIFFERENTES et deux predictions DIFFERENTES depuis la tuile courante."""
    arms = _arms(nominal, with_rival=False)
    assert len(arms) >= 2, "il faut au moins deux longueurs de pas pour separer threade de constante"
    ns = {a["n"] for a in arms}
    assert len(ns) == len(arms), (
        "les bras rendent le meme compteur %s -- un port qui facturerait `V x 1` quel que soit le "
        "pas passerait cette suite" % sorted(ns))
    preds = {tuple(_same_tile_row(a)["off"]) for a in arms}
    assert len(preds) == len(arms), (
        "les bras rendent la meme prediction %s malgre des pas differents" % sorted(preds))


def test_count_comes_from_the_pathfinder_not_hex_distance(nominal):
    """DISCRIMINANT -- le compte est celui du CHEMIN (`BattleQuery$$GetNumTilesMoved` = `Count - 1`
    du `WalkPathfinder`), pas la distance hexagonale.

    Le bras RIVAL le fournit gratuitement : l'ennemi ramene au contact BLOQUE le passage
    (`WalkPathfinder$$UnitIsBlockedByEnemyUnit`), donc un pas de 2 hex coute 6 tuiles de chemin. Un
    port qui compterait en hexes rendrait la prediction du bras a 2 tuiles."""
    rival = _arms(nominal, with_rival=True)
    assert rival, "le bras RIVAL n'a pas ete monte -- ce discriminant n'est pas exerce"
    for arm in rival:
        assert arm["n"] > arm["steps"], (
            "bras rival : n=%d pour un pas de %d hex -- le detour n'a pas eu lieu, le discriminant "
            "chemin/hex n'est pas exerce" % (arm["n"], arm["steps"]))
        row = _same_tile_row(arm)
        assert row["nat"] is not None and row["off"] == row["nat"], (
            "bras rival (n=%d, pas=%d hex) : la prediction diverge -- natif=%s port=%s. Un compte "
            "en distance HEX rendrait la valeur du bras a %d tuile(s)."
            % (arm["n"], arm["steps"], row["nat"], row["off"], arm["steps"]))


def test_the_term_can_flip_the_argmax(nominal):
    """LA PORTEE -- ce terme change des DECISIONS, pas seulement un scalaire.

    Balayage des PV de la cible ET du rival sur la fenetre `[min(port n=0), max(port n reel)]` :
    il doit exister des points ou la TETE du classement (ability, cible, tuile) change entre le
    compteur lu et le compteur force a 0. Sans cette garde, on ne saurait pas si le residu valait
    la peine d'etre ferme."""
    rival = _arms(nominal, with_rival=True)
    assert rival, "le bras RIVAL n'a pas ete monte -- l'argmax n'a aucune action concurrente"
    for arm in rival:
        am = arm["argmax"]
        assert not am.get("skipped"), "argmax non mesure : %s" % am.get("skipped")
        assert any(p["dec_n"] is not None for p in am["points"]), (
            "AUCUNE decision rendue sur le balayage -- un « 0 renversement » ne mesurerait rien")
        flips = am["flips"]
        assert flips, (
            "aucun des %d points ne renverse la tete du classement : sur ce montage le terme ne "
            "changerait aucune decision" % len(am["points"]))
        # Le renversement doit porter sur l'ACTION (ability, cible, tuile), pas sur l'utilite seule.
        real = [p for p in flips if p["rank"].get("flip")]
        assert real, (
            "les %d « renversements » ne changent que l'utilite, jamais l'action retenue" % len(flips))


# --------------------------------------------------------------------- foyer, sans live
def test_scene_from_state_reads_the_counter(nominal):
    """FOYER -- `Scene.from_state` publie le compteur de l'ECS, et le tri-etat est respecte.

    C'est le cablage que #340 pose : la face DECISION lit ce que la face COMBAT tient deja
    (`runner/components.py::unit_tiles_moved_this_turn`), au lieu de le reconstruire a zero."""
    from engine.playbook.scene import Scene
    for arm in _arms(nominal):
        sc = arm["ctx_b"].scene
        caster = arm["plan"]["caster"]
        assert sc.tiles_moved_this_turn(caster) == arm["n"], (
            "`Scene.tiles_moved_this_turn` rend %s alors que l'ECS porte %s"
            % (sc.tiles_moved_this_turn(caster), arm["n"]))
        assert arm["ctx_zero"].scene.tiles_moved_this_turn(caster) == 0, (
            "le contrefactuel n=0 devrait publier un compteur nul")
    # TRI-ETAT : une Scene sans la table rend `None` (non mesure), jamais `0` (mesure et nul).
    bare = Scene(ctx_by_id={}, armor_by_id={}, shield_by_id={}, mult_by_id={}, ablvl_by_id={},
                 vis_by_id={}, units=[], hp_by_id={}, pos_by_id={}, team_by_id={}, eff_state=None)
    assert bare.tiles_moved_this_turn(1) is None, (
        "table vide : `tiles_moved_this_turn` doit rendre None (non mesure), pas 0 -- confondre les "
        "deux ferait passer un capteur ABSENT pour « n'a pas bouge »")
