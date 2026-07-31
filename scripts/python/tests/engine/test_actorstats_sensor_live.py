"""GARDES #340-r1 -- le capteur `actorStats` publie `ActorStatisticsComponent+0xf0`, et les DEUX
voies LIVE du port le lisent.

CE QUI ETAIT BLOQUE, ET PAR QUOI
--------------------------------
#340 a ferme le terme REEL de `TilesMovedThisTurn` cote OFFLINE (`Scene.from_state` lit l'ECS que
la face COMBAT tient depuis #335). Restait `#340-r1` : les voies qui partent d'une CAPTURE LIVE --
`load_state` (etat recharge) et `build_predictor`/`from_predictor_sctx` (prediction) -- n'avaient
aucun canal pour `+0xf0`. Le cablage Python etait pose et INERTE, en attente du capteur.

Le capteur est desormais deploye, et ces gardes le confrontent AU LIEU de lui faire confiance.

POURQUOI LE PATRON A TROIS CHAMPS EST LE BON DISCRIMINANT
---------------------------------------------------------
Les OFFSETS sont attestes par trois lectures du decompile, mais les NOMS passes a `getFieldOffset`
ne sont PAS verifiables offline (aucun `fields.tsv` dans `data/symbols/`). Un capteur qui lit au
mauvais endroit ne leve RIEN -- il rend un entier plausible. Ce qu'on exige donc du champ, ce n'est
pas une valeur, ce sont les DEUX TRANSITIONS du composant natif :

    un pas de n tuiles          -> `RecordTilesMoved`     : `+0xec += n`, `+0xf0 += n`
    `EndTurnOperation`          -> `ResetThisTurn`        : `+0xf4 = +0xf0`, puis `+0xf0 = 0`

et le fait que `n` soit le compte du CHEMIN (`BattleQuery$$GetNumTilesMoved` = `Count - 1` du
WalkPathfinder), pas la distance hexagonale -- ce que le bras RIVAL separe (un ennemi au contact
BLOQUE le passage, donc 2 hex y coutent 6 tuiles).

CE QUE CES GARDES ONT DEJA ATTRAPE
----------------------------------
Au premier passage, `tilesMovedThisBattle` (+0xec) et `tilesMovedLastTurn` (+0xf4) rendaient tous
deux **-1201836032** -- la MEME valeur, signature d'une lecture a la MEME adresse -- pendant que
`tilesMovedThisTurn` (+0xf0) etait exact. Cause : `getFieldOffset` rend **-1** sur un nom absent, et
l'idiome `getFieldOffset(...) || 0xec` ne teste que `0` (or -1 est truthy en JS), donc le repli
decompile n'etait jamais pris et le hook lisait `comp - 1`. Correctif livre (`fieldOffsetOr`), il
EXIGE UNE REINJECTION -- d'ou la garde `test_the_two_other_counters_are_measured_either_way`, qui
mesure dans les DEUX regimes et constatera le reinject au lieu de virer au vert a vide.

ASCII only.
"""
from __future__ import annotations

import pytest

import probe_340_r1_actorstats_live as R1


@pytest.fixture(scope="module")
def sensor_case(live_session):
    """Fabrique : monte UN runner isole et le DISPOSE en sortie.

    Un montage qui ne s'installe pas ECHOUE, il ne skippe pas (#268) : un skip sur un regime non
    atteint est un VERT qui ment."""
    cache: dict = {}

    def _case(steps=(1, 2), board: str = R1.P335.BOARD, seed: int = R1.P335.SEED,
              rival_step: int | None = 2) -> dict:
        key = (tuple(steps), board, seed, rival_step)
        if key not in cache:
            res = None
            try:
                res = R1.scenario(steps=tuple(steps), board=board, seed=seed,
                                  rival_step=rival_step)
            except RuntimeError as exc:
                pytest.fail(f"montage actorStats NON INSTALLE (board={board}, seed={seed}, "
                            f"pas={tuple(steps)}) : {exc}", pytrace=False)
            finally:
                if res is not None:
                    R1.dispose(res)
            cache[key] = res
        return cache[key]
    return _case


@pytest.fixture(scope="module")
def nominal(sensor_case):
    """MC1_67 / 909 : un pas d'UNE tuile, un pas de DEUX, plus le bras RIVAL (chemin-vs-hex)."""
    return sensor_case()


def _arms(res, with_rival=None):
    out = [a for a in res["arms"].values()
           if with_rival is None or a.get("with_rival") == with_rival]
    return sorted(out, key=lambda a: (bool(a.get("with_rival")), a["steps"]))


def _same_tile_row(arm):
    return next(r for r in arm["rows"] if r["same_tile"])


# --------------------------------------------------------------------- V1 : le capteur
def test_sensor_publishes_the_tiles_counter(nominal):
    """PREALABLE A TOUT LE RESTE -- le hook DEPLOYE publie-t-il `tilesMovedThisTurn` ?

    Sans ce champ, chaque autre garde de ce fichier virerait au vert pour la mauvaise raison : le
    port garderait son comportement d'AVANT (tri-etat `None` -> seul le pas simule compte), qui est
    correct mais ne mesure rien. On refuse ce vert-la."""
    for arm in _arms(nominal):
        assert R1.sensor_publishes_tiles(arm["ast_after"]), (
            "`actorStats` ne publie PAS `tilesMovedThisTurn` -- le bundle injecte est ANTERIEUR au "
            "capteur (`frida/hooks/features/ai-step/rpc-snapshot.ts`). Une REINJECTION est requise ; "
            "sans elle ce fichier ne mesure rien.")


def test_sensor_counter_matches_the_pathfinder_count(nominal):
    """LE CONTROLE D'OFFSET -- `+0xf0` apres le pas vaut exactement le compte du CHEMIN.

    L'etalon est la voie deja validee bit-exacte par #340 : le rejeu offline du `MoveUnitMessage`,
    ou c'est le moteur qui pose le compteur (`components.record_tiles_moved`). Un capteur lisant au
    mauvais offset rendrait un entier plausible mais decorrele du pas."""
    for arm in _arms(nominal):
        assert arm["n_ref"] > 0, (
            "bras pas=%d : le rejeu offline n'enregistre AUCUNE tuile -- l'etalon est vide"
            % arm["steps"])
        got = arm["ast_after"][arm["caster"]]["turn"]
        assert got == arm["n_ref"], (
            "bras pas=%d : le capteur rend +0xf0 = %s la ou le pathfinder compte %d tuile(s) "
            "(`BattleQuery$$GetNumTilesMoved` = Count - 1)" % (arm["steps"], got, arm["n_ref"]))


def test_sensor_counter_is_zero_before_the_step(nominal):
    """Le compteur part de ZERO -- le cycle complet du montage (`reach_my_turn(force_cycle=True)`)
    a bien fait passer `EndTurnOperation`, donc les `place()` du montage ne polluent pas la mesure.

    Sans cette garde, un compteur deja non nul rendrait la garde d'offset ci-dessus trompeuse."""
    for arm in _arms(nominal):
        got = arm["ast_before"][arm["caster"]]["turn"]
        assert got == 0, (
            "bras pas=%d : +0xf0 vaut %s AVANT le pas -- le compteur du MONTAGE entre dans la "
            "mesure" % (arm["steps"], got))


def test_sensor_counter_resets_at_end_of_turn(nominal):
    """La SECONDE transition -- `ActorStatisticsComponent$$ResetThisTurn` remet `+0xf0` a 0, de
    facon INCONDITIONNELLE.

    Deux transitions differentes sur le meme champ ne peuvent pas etre un alignement heureux sur un
    mauvais offset : c'est ce qui fait de ce couple un controle, et pas une observation."""
    for arm in _arms(nominal):
        got = arm["ast_reset"][arm["caster"]]["turn"]
        assert got == 0, (
            "bras pas=%d : apres `EndTurnOperation`, +0xf0 vaut %s au lieu de 0"
            % (arm["steps"], got))


def test_sensor_counts_path_not_hex_distance(nominal):
    """DISCRIMINANT -- le capteur rend le compte du CHEMIN, pas la distance hexagonale.

    Le bras RIVAL le fournit : l'ennemi ramene au contact BLOQUE le passage
    (`WalkPathfinder$$UnitIsBlockedByEnemyUnit`), donc un pas de 2 hex coute 6 tuiles. Un capteur
    qui lirait un champ de distance rendrait 2."""
    rival = _arms(nominal, with_rival=True)
    assert rival, "le bras RIVAL n'a pas ete monte -- ce discriminant n'est pas exerce"
    for arm in rival:
        assert arm["n_ref"] > arm["steps"], (
            "bras rival : n=%d pour un pas de %d hex -- le detour n'a pas eu lieu, chemin et hex "
            "ne sont pas separes" % (arm["n_ref"], arm["steps"]))
        got = arm["ast_after"][arm["caster"]]["turn"]
        assert got == arm["n_ref"], (
            "bras rival : le capteur rend %s la ou le CHEMIN coute %d tuile(s) ; la distance HEX "
            "vaudrait %d" % (got, arm["n_ref"], arm["steps"]))


# --------------------------------------------------------------------- V2 : la voie load_state
def test_load_state_seeds_the_counter(nominal):
    """FOYER 1 -- un `State` recharge d'une capture live porte le compteur.

    C'est le residu nomme « `load_state` ne seede pas le compteur » de #340 SS6. Le rejeu offline
    d'un `MoveUnitMessage` le MASQUAIT (c'est le moteur qui reposait le compteur) : ici l'etat est
    CHARGE, jamais rejoue, donc la valeur ne peut venir que du capteur."""
    for arm in _arms(nominal):
        assert arm["n_seeded"] == arm["n_ref"], (
            "bras pas=%d : `load_state(actor_stats=...)` seede %s au lieu de %d"
            % (arm["steps"], arm["n_seeded"], arm["n_ref"]))


def test_load_state_without_the_channel_keeps_the_prior_behaviour(nominal):
    """TRI-ETAT -- sans le canal, le compteur reste a son 0 de construction : le comportement
    STRICTEMENT anterieur.

    C'est aussi le CONTREFACTUEL des gardes de prediction : si l'etat sans canal portait deja le
    bon compteur, elles compareraient a vide."""
    for arm in _arms(nominal):
        assert arm["n_bare"] == 0, (
            "bras pas=%d : sans `actor_stats`, le compteur vaut %s au lieu de 0 -- le contrefactuel "
            "ne separe rien" % (arm["steps"], arm["n_bare"]))


# --------------------------------------------------------------------- V3 : la voie live-capture
def test_live_capture_scene_reads_the_counter(nominal):
    """FOYER 2 -- la voie `build_predictor` -> `from_predictor_sctx`, celle que #340 declarait
    « posee et inerte tant que le hook n'est pas deploye ».

    `refresh_shields` est inclus dans le montage : c'est LUI que la boucle de decision appelle par
    pas, donc lui qui doit tenir le compteur a jour au fil des deplacements."""
    for arm in _arms(nominal):
        assert arm["tiles_moved_by_id"], (
            "bras pas=%d : la table `tiles_moved_by_id` de la voie live est VIDE -- l'accesseur "
            "rendrait `None` et la prediction garderait le seul terme « pas simule »" % arm["steps"])
        assert arm["n_scene"] == arm["n_ref"], (
            "bras pas=%d : `Scene.tiles_moved_this_turn` rend %s au lieu de %d"
            % (arm["steps"], arm["n_scene"], arm["n_ref"]))


# --------------------------------------------------------------------- la consequence observable
def test_prediction_matches_live_on_both_live_paths(nominal):
    """CONTROLE PRINCIPAL -- apres un deplacement JOUE, les DEUX voies live rendent la prediction
    du natif, bit a bit.

    Le pas simule est NUL depuis la tuile courante, donc TOUT le bonus vient du compteur reel :
    c'est exactement le regime que le port ratait."""
    for arm in _arms(nominal):
        row = _same_tile_row(arm)
        assert row["nat"] is not None, (
            "bras pas=%d : le natif ne predit RIEN depuis la tuile courante -- rien n'est mesure"
            % arm["steps"])
        for key, label in (("live", "voie live-capture"), ("seeded", "voie load_state")):
            assert row[key] == row["nat"], (
                "bras pas=%d (n=%d), %s : la prediction diverge -- natif=%s port=%s (delta/borne=%s)"
                % (arm["steps"], arm["n_ref"], label, row["nat"], row[key],
                   None if row[key] is None
                   else [o - x for x, o in zip(row["nat"], row[key])]))


def test_neither_path_is_vacuous(nominal):
    """NON-VACUITE -- sans le canal, les deux voies doivent RE-DIVERGER, et vers le BAS (l'additif
    `V x n` est positif). Sinon la garde principale comparerait a vide."""
    for arm in _arms(nominal):
        row = _same_tile_row(arm)
        assert row["bare"] is not None, "le contrefactuel ne predit rien -- il ne separe rien"
        for key, label in (("live", "voie live-capture"), ("seeded", "voie load_state")):
            assert row["bare"] != row[key], (
                "bras pas=%d (n=%d), %s : retirer le canal rend EXACTEMENT la meme prediction (%s) "
                "-- le montage n'active pas `ModifiedExoarmour_ExtraDmg`"
                % (arm["steps"], arm["n_ref"], label, row[key]))
            assert row["bare"][0] < row[key][0], (
                "bras pas=%d, %s : sans le canal la prediction est PLUS HAUTE (%s > %s) -- "
                "l'additif devrait etre positif"
                % (arm["steps"], label, row["bare"], row[key]))


def test_the_counter_is_threaded_not_a_constant(nominal):
    """Le compteur est THREADE : des pas de longueurs differentes doivent donner des `n` et des
    predictions DIFFERENTS. Un port qui facturerait `V x 1` quel que soit le pas passerait toutes
    les gardes ci-dessus prises une a une."""
    arms = _arms(nominal)
    assert len(arms) >= 2, "il faut au moins deux bras pour separer threade de constante"
    ns = {a["n_ref"] for a in arms}
    assert len(ns) == len(arms), (
        "les bras rendent le meme compteur %s" % sorted(ns))
    preds = {tuple(_same_tile_row(a)["live"]) for a in arms}
    assert len(preds) == len(arms), (
        "les bras rendent la meme prediction %s malgre des pas differents" % sorted(preds))


# --------------------------------------------------------------------- V4 : le garde anti-garbage
def test_negative_readings_never_enter_the_ecs():
    """FOYER, SANS LIVE -- `_load_actor_statistics` REFUSE une valeur negative.

    Ce n'est pas de la defense de principe : les trois champs sont des compteurs a increments
    `>= 1` (`RecordTilesMoved` sort sur `if ((int)tiles < 1) return;`), remis a `0` ou copies l'un
    dans l'autre par `ResetThisTurn`. AUCUNE ecriture native ne peut les rendre negatifs, donc un
    negatif denonce une LECTURE invalide -- et il ne doit pas devenir indistinguable d'un etat de
    jeu une fois dans l'ECS.

    Garde OFFLINE a dessein : elle reste mordante quel que soit l'etat du hook deploye."""
    from engine.runner.components import UnitComponent
    from engine.runner.snapshot import _load_actor_statistics
    from engine.runner.state import State

    st = State()
    ent = st.add_entity(42)
    uc = UnitComponent(visual_id="votanChampion", alive=True)
    ent.add_component(uc)
    _load_actor_statistics(st, {"units": [{"entityId": 42,
                                           "tilesMovedThisBattle": -1201836032,
                                           "tilesMovedThisTurn": 3,
                                           "tilesMovedLastTurn": -1201836032}]})
    assert uc.tiles_moved_this_turn == 3, (
        "le champ VALIDE doit passer -- obtenu %s" % uc.tiles_moved_this_turn)
    assert uc.tiles_moved_this_battle == 0 and uc.tiles_moved_last_turn == 0, (
        "du garbage NEGATIF est entre dans l'ECS : battle=%s last=%s"
        % (uc.tiles_moved_this_battle, uc.tiles_moved_last_turn))


def test_the_two_other_counters_are_measured_either_way(nominal):
    """CLIQUET DU REINJECT -- `+0xec` et `+0xf4` sont mesures dans les DEUX regimes.

    Tant que le correctif `fieldOffsetOr` n'est pas reinjecte, ces deux champs rendent la MEME
    valeur negative (lecture a `comp - 1`) : on l'exige explicitement, pour que la garde ne vire pas
    au vert a vide. Une fois le reinject fait, on exige a la place le patron natif complet
    (`+0xec` cumule le pas et ignore le reset ; `+0xf4` prend `+0xf0` au reset). Dans les deux cas
    la garde MESURE -- c'est elle qui constatera le passage d'un regime a l'autre."""
    for arm in _arms(nominal):
        c = arm["caster"]
        b, af, rs = (arm["ast_before"][c], arm["ast_after"][c], arm["ast_reset"][c])
        k = arm["n_ref"]
        if af["battle"] is not None and af["battle"] < 0:
            assert af["battle"] == af["last"], (
                "regime PRE-reinject attendu : les deux champs faux devraient rendre la MEME valeur "
                "(lecture a `comp - 1`), obtenu battle=%s last=%s" % (af["battle"], af["last"]))
            pytest.xfail("hook PRE-correctif : +0xec/+0xf4 lisent `comp - 1` (%s). Le correctif "
                         "`fieldOffsetOr` est livre et EXIGE UNE REINJECTION." % af["battle"])
        assert af["battle"] == (b["battle"] or 0) + k, (
            "+0xec doit cumuler le pas : attendu %s, obtenu %s"
            % ((b["battle"] or 0) + k, af["battle"]))
        assert rs["battle"] == af["battle"], (
            "+0xec est insensible a `ResetThisTurn` : attendu %s, obtenu %s"
            % (af["battle"], rs["battle"]))
        assert rs["last"] == k, (
            "`ResetThisTurn` doit poser +0xf4 = +0xf0 (wasOwnTurn) : attendu %d, obtenu %s"
            % (k, rs["last"]))
