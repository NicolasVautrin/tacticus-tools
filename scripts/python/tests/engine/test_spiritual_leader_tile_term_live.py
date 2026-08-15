"""GARDE #212 -- `SpiritualLeaderPlaybook` (1275, `genesMagus`/Xybia) : la CLE BC et le CAP.

CE QUE CES GARDES PROTEGENT, et pourquoi elles existent en DEUX exemplaires.

1. LA CLE. Le terme de mouvement de 1275 est un LOOKUP PLAT
   `Utilities.Default.TriggeredAbilities[<cle>]` lu par
   `IdunBattle.AI.Playbook.Loki.SpiritualLeaderPlaybook$$GetAdjacentFriendUtility`. La cle porte une
   FAUTE DE FRAPPE du jeu : `SPIRITUALLDEADER_AdjacentDecoy` (L-D-E-A-D-E-R). `case-193c` l'avait
   cherchee par prefixe correct, ne l'avait pas trouvee, et avait laisse le terme non resolu -- le
   playbook n'etait PAS au registre, donc le terme valait 0. La garde `test_bc_key_...` echoue si
   quelqu'un « corrige » l'orthographe : la cle corrigee n'existe pas en BC, `Weights.sub` rend 0, et
   le terme meurt SILENCIEUSEMENT (ni erreur ni crash -- exactement la degradation permissive que le
   self-play irait exploiter).

2. LE CAP. Le corps commun
   `IdunBattle.AI.Playbook.AdjacentUnitPreferenceTriggeredAbilityPlaybook.u003CCalculateMovementUtilityInStepsInternalu003Ed__1u003C__Il2CppFullySharedGenericTypeu003E$$MoveNext`
   fait `n = Min(count(<amis filtres>), vtbl+0x228)` puis ne somme que les `n` premiers.
   `SpiritualLeaderPlaybook` override ce slot a **1** (corps trivial `mov eax,1 ; ret` fondu par
   l'ICF, donc SANS symbole -- lu par le bloc `methodPointers` du PE,
   `probe_8889_methodptr_vtable.py`). Le terme vaut donc 30 des qu'il y a UN decoy adjacent, et
   **pas** 30 x n. La garde `test_term_is_capped_...` echoue si le cap disparait (2 decoys -> 60).

3. L'ORACLE DU COMPTAGE. « Decoy ADJACENT » se lit par `engine.battle_query.is_adjacent`, mirror
   d'`IdunBattle.Core.Services.TileQuery.u003CIterateAdjacentTilesu003Ed__8$$MoveNext` (liste
   STOCKEE du `ConnectivityComponent`, puis porte INCONDITIONNELLE `|elev(t) - elev(v)| < 2`), et
   PAS par la couronne hex `hexgeo.distance == 1`. Les deux ne coincident pas : la couronne est un
   SUR-ENSEMBLE strict, donc elle SUR-COMPTE. Ce fichier a rendu 1 F / 9 P pendant plusieurs jours
   pour cette seule raison -- l'oracle voyait 2 decoys la ou le natif et le port en voyaient 0, et
   le desaccord etait impute au PORT. `test_les_deux_adjacences_ne_sont_PAS_interchangeables_sur_
   ce_board` garde le cran : si les deux lectures coincidaient partout sur le board, ce fichier ne
   distinguerait plus l'oracle juste du faux, et il le DIT au lieu de rester vert.

MONTAGE -- ON PILOTE LES POSITIONS (2026-08-03). `genesMagus` fabrique elle-meme les decoys que ce
terme compte (sa face COMBAT pose un `genesSmnDecoy` a la fin de chaque activation), mais ATTENDRE
que la geometrie de spawn produise une candidate a >= 2 decoys adjacents est un echantillon SUBI :
il tenait a un numero de pas en dur (47 / 21) sur une trajectoire native que rien ne fige. On
marche donc la trajectoire en DEPLACANT le carrier vers les tuiles RICHES (`walk_driven` /
`_drive_carrier_toward` de `probe_212_spiritual_leader_tile_term.py`, patron de `_drive_cluster`
#242), et on s'arrete au premier pas ou le regime est REALISE -- quel que soit son numero.

Mesure fondatrice (`probe_212_spiritual_leader_tile_term.py`, decomposition
`X = Tile(7) - Elevation - TileEffects` aux hooks EXISTANTS de `scorer-damage-trace`) :
`X_nat` = 30 pour n = 1, 2 ET 3, et `X_nat - X_port` = 0 tuile par tuile.
AUCUNE de ces valeurs n'est gelee ici : les assertions re-derivent tout du contexte du pas.

ASCII only.
"""
from __future__ import annotations

import os
import sys
from types import SimpleNamespace

import pytest

sys.path.insert(0, os.path.dirname(__file__))      # tests/engine -> import du helper sibling

from counterproof import assert_sample_confrontable  # noqa: E402

ABILITY = 1275                                     # TriggeredAbilityType.SpiritualLeader
CARRIER = "genesMagus"
BC_KEY = "SPIRITUALLDEADER_AdjacentDecoy"          # la cle REELLE (faute de frappe du jeu)
BC_KEY_MISSPELL_FIXED = "SPIRITUALLEADER_AdjacentDecoy"   # ce qu'une « correction » produirait
DECOY_TRAIT = "Decoy"                              # UnitTrait.Decoy = 0x41d = 1053
MAX_STEPS = 140

# Bataille LONGUE : Xybia doit pouvoir jouer plusieurs activations pour semer ses decoys.
_LONG = ["--hp-target", "100000", "--hp-player", "100000"]
_GENES = _LONG + [
    "--p-units", "genesMagus,genesPrimus,genesKelermorph,orksNob,spaceWulfen",
    "--a-units", "darkaHellblaster,eldarRanger,worldKharn,templChampion,tauMarksman"]

CASES = [("MC1_67", "777", _GENES),
         ("C4_09", "31337", _GENES)]


@pytest.fixture(scope="module", params=CASES, ids=lambda c: "%s-%s" % (c[0], c[1]))
def sl_case(request, rpc, build_runner):
    """Etat de decision d'une activation de Xybia ou le regime du CAP est REALISE.

    On ne SUBIT pas la geometrie : tant qu'aucune candidate ne porte `>= 2` decoys adjacents, on
    DEPLACE le carrier vers une tuile riche et on termine le tour des allies (`walk_driven`). Le
    `move` du carrier declenche lui-meme `On(0x1c=ArrivedAtFinalTile)`, donc un decoy de plus : le
    drive enrichit le plateau en meme temps qu'il en rapproche Xybia."""
    from probe_212_spiritual_leader_tile_term import (walk_driven, carrier_id_of, wants_212,
                                                      goals_212)
    board, seed, extra = request.param

    def r(m, b, t=90):
        return rpc(m, b, t)

    rid = build_runner(seed, extra=list(extra), board=board)["rid"]
    cid = carrier_id_of(r, rid, CARRIER)
    assert cid is not None, "%s absent du runner (roster/pool a re-etalonner)" % CARRIER
    for st in walk_driven(r, rid, cid, wants_212, goals_212, MAX_STEPS):
        me = next((u for u in (st["dv"].get("units") or []) if u.get("id") == st["uid"]), None)
        return SimpleNamespace(rid=rid, step=st["step"], uid=st["uid"], board=board, seed=seed,
                               visual_id=(me or {}).get("visualId"), ctx=st["ctx"],
                               action_tiles=list(st["ctx"].action_tiles or []),
                               decoys=st["decoys"], driven=st["driven"])
    assert_sample_confrontable(
        False,
        mutation="montage %s/%s : trajectoire native marchee en PILOTANT les positions de %s vers "
                 "les tuiles a >= 2 decoys allies adjacents (walk_driven / _drive_carrier_toward)"
                 % (board, seed, CARRIER),
        doit_casser="une activation du carrier ou ses candidates portent a la fois 0 et >= 2 decoys "
                    "adjacents -- le seul regime ou un port qui SOMME differe d'un port qui BORNE",
        observe="aucune en %d pas : trajectoire epuisee, ou le drive n'a jamais atteint de tuile "
                "riche" % MAX_STEPS,
        remede="rejouer `probe_212_spiritual_leader_tile_term.py` sur ce couple board/seed pour voir "
               "ou le drive bute (il imprime chaque DRIVE et le nombre de decoys allies vus) ; si "
               "les decoys ne sont plus poses, c'est la face COMBAT de SpiritualLeader qu'il faut "
               "relire, pas ce montage")


def _terms_by_tile(case):
    """{tuile: (terme du playbook 1275, nombre de DECOYS allies ADJACENTS)} sur les candidates.

    ⚠ « ADJACENTS » EST L'ADJACENCE NATIVE, ET C'EST LE CORRECTIF DE CETTE GARDE. L'oracle
    comptait `hexgeo.distance(t, u["pos"]) == 1` -- la COURONNE HEX -- pendant que le port, comme
    le natif, passe par `engine.battle_query.is_adjacent` (mirror de
    `IdunBattle.Core.Services.TileQuery.u003CIterateAdjacentTilesu003Ed__8$$MoveNext` : liste
    STOCKEE du `ConnectivityComponent`, puis porte INCONDITIONNELLE `|elev(t) - elev(v)| < 2`).
    La couronne est un SUR-ENSEMBLE strict du voisinage natif, donc l'oracle SUR-COMPTAIT, et
    l'ecart s'imputait au PORT.

    MESURE QUI TRANCHE (2026-08-15, `MC1_67`/777, pas 23, `genesMagus`) : sur 24 candidates,
    23 concordaient et `(1,3)` rendait `(terme 0.0, n 2)`. `(1,3)` est a l'ELEVATION 4 et deux de
    ses six voisins hex, `(1,2)` et `(2,2)`, sont a l'ELEVATION 2 (`data/boards/global/MC1_67.json`)
    : `|dElev| = 2` les exclut du voisinage natif. Les deux decoys que l'oracle comptait ne sont
    adjacents NI pour le natif NI pour le port -- le terme 0.0 etait JUSTE. C'est l'oracle qui
    etait faux, pas le moteur.

    Le comptage vit dans le FOYER `probe_212_spiritual_leader_tile_term.decoys_adjacent`, partage
    avec le probe : deux comptages ecrits separement redivergeraient, et c'est exactement ce qui
    s'est produit ici."""
    from probe_212_spiritual_leader_tile_term import decoys_adjacent
    from engine.utilities.tile import tile_leaf_ctx
    from engine.playbook.adjacent_unit_preference import load_playbook
    pb = load_playbook(ABILITY)
    assert pb is not None, "ability %d absente de TRIGGERED_MOVE_PLAYBOOKS" % ABILITY
    lc = tile_leaf_ctx(case.ctx)
    out = {}
    for t in (case.action_tiles or []):
        out[t] = (pb.calculate_movement_utility_in_steps(t, lc, case.ctx.wt),
                  len(decoys_adjacent(lc, t)))
    return out


def test_les_deux_adjacences_ne_sont_PAS_interchangeables_sur_ce_board(sl_case):
    """LE TEMOIN DU CORRECTIF : sur CE board, la couronne hex et le voisinage NATIF DIFFERENT.

    Sans lui, `_terms_by_tile` pourrait revenir a `hexgeo.distance == 1` sans qu'aucune assertion
    ne bouge -- le fichier serait vert sur les deux oracles, donc il n'en garderait AUCUN. Le
    compte est RE-DERIVE des cartes du pas (`neigh_by_pos` = `boardGraph.neighbours`, capte par
    `IdunBattle.Core.Services.BattleQuery$$GetAdjacentTiles(t, 0, 0, 1)` ; `elev_by_pos` =
    `tileMeta.elevation`), jamais cite.

    L'ecart attendu est STRICTEMENT PERMISSIF -- la couronne SUR-ATTEINT, elle ne rate jamais un
    voisin natif. Les deux sens sont assertionnes : un ecart RESTRICTIF signifierait que le port
    a une porte que le natif n'a pas, ce qui est un tout autre defaut."""
    from engine import battle_query as bq
    from engine.utilities.tile import tile_leaf_ctx
    import hexgeo
    lc = tile_leaf_ctx(sl_case.ctx)
    elev, neigh = lc.get("elev_by_pos"), bq.neigh_map(lc)
    permissif = restrictif = paires = 0
    for t in sorted(neigh or {}):
        for v in hexgeo.neighbors(t[0], t[1]):
            if v not in (neigh or {}):
                continue                         # hors plateau : aucun des deux ne la voit
            paires += 1
            nat = bq.is_adjacent(t, v, elev, neigh)
            if not nat:
                permissif += 1                   # la couronne la voit, le natif NON
    for t in sorted(neigh or {}):
        for v in (neigh or {}).get(t) or ():
            v = (v[0], v[1])
            if hexgeo.distance(t, v) != 1 and bq.is_adjacent(t, v, elev, neigh):
                restrictif += 1                  # le natif la voit, la couronne NON
    assert not restrictif, (
        "%d arete(s) que le voisinage NATIF accorde et que la couronne hex refuse : l'ecart n'est "
        "plus strictement permissif, la lecture d'`IterateAdjacentTiles` est a refaire" % restrictif)
    assert_sample_confrontable(
        permissif > 0,
        mutation="comparaison arete par arete de la couronne hex et du voisinage NATIF sur les "
                 "%d paires du board %s" % (paires, sl_case.board),
        doit_casser="au moins une arete que la couronne hex accorde et que le natif REFUSE (marche "
                    "d'elevation >= 2, ou tuile absente de la liste stockee)",
        observe="0 ecart sur %d paires : les deux oracles coincident partout ici" % paires,
        remede="choisir un board qui porte une marche d'elevation >= 2 ou des tuiles `Bridge` "
               "(mesure #271 : MC1_67 9 ecarts, C4_09 22, C1_25 2) -- sinon cette garde ne "
               "distingue pas l'oracle CORRIGE de l'oracle FAUX qu'elle remplace")


def test_case_still_activates_the_carrier(sl_case):
    """Le montage n'a de sens que si le pas active bien Xybia ; sinon rien n'a ete confronte.

    ROUGE DE SCENARIO (#462-r6) : ce n'est ni un verdict sur le port ni sur le harnais."""
    assert_sample_confrontable(
        sl_case.visual_id == CARRIER,
        mutation="marche pilotee jusqu'a une activation du carrier %s" % CARRIER,
        doit_casser="le pas retenu active bien %s (les gardes suivantes lisent SON kit)" % CARRIER,
        observe="pas %d : l'unite activee est %s" % (sl_case.step, sl_case.visual_id),
        remede="`walk_driven` ne yield que sur `uid == carrier_id` : si ce message apparait, c'est "
               "que `carrier_id_of` a resolu un autre `visualId` -- re-etalonner le roster")


def test_kit_source_carries_the_triggered_ability(sl_case):
    """GARDE DE SOURCE : sans elle le playbook peut etre au registre et n'etre JAMAIS appele."""
    from engine.utilities.tile import tile_leaf_ctx
    kit = tile_leaf_ctx(sl_case.ctx).get("unit_triggered_abilities") or []
    assert ABILITY in kit, (
        "pas %d (%s) : ability %d absente du kit declenche %r -- le playbook ne sera JAMAIS appele"
        % (sl_case.step, sl_case.visual_id, ABILITY, kit))


def test_bc_key_is_the_misspelled_one_and_is_non_zero(sl_case):
    """La cle EFFECTIVE porte la faute de frappe du jeu, et c'est la SEULE qui existe en BC.

    Deux assertions symetriques : le litteral natif rend un poids non nul, et son orthographe
    « corrigee » n'existe pas. Corriger la faute rendrait donc 0 sans le moindre signal."""
    wt = sl_case.ctx.wt
    w = wt.sub("TriggeredAbilities", BC_KEY)
    assert w > 0, (
        "la cle BC %r rend %r -- le litteral lu par "
        "`IdunBattle.AI.Playbook.Loki.SpiritualLeaderPlaybook$$GetAdjacentFriendUtility` a disparu "
        "de `Utilities.Default.TriggeredAbilities` (BC re-dumpee ? build change ?)" % (BC_KEY, w))
    assert wt.sub("TriggeredAbilities", BC_KEY_MISSPELL_FIXED) == 0, (
        "la cle %r existe desormais en BC : la faute de frappe du jeu a ete corrigee cote jeu, "
        "il faut RELIRE le litteral natif (probe_212_bc_key_literals.py) avant de changer le port"
        % BC_KEY_MISSPELL_FIXED)


def test_montage_exercises_more_than_one_adjacent_decoy(sl_case):
    """Sans une candidate a >=2 decoys adjacents, le cap ne peut pas etre mis en defaut : la garde
    suivante passerait a vide. On le dit ici plutot que de laisser croire qu'elle mesure quelque
    chose.

    ROUGE DE SCENARIO (#462-r6) : c'est l'ECHANTILLON qui est en cause, pas le port."""
    counts = sorted({n for (_, n) in _terms_by_tile(sl_case).values()})
    assert_sample_confrontable(
        bool(counts) and 0 in counts and max(counts) >= 2,
        mutation="drive de %s vers une tuile a >= 2 decoys allies adjacents (%d drive(s) joue(s), "
                 "%d decoy(s) allie(s) vus au pas retenu)" % (CARRIER, sl_case.driven,
                                                              len(sl_case.decoys)),
        doit_casser="au moins une candidate a 0 decoy adjacent ET une a >= 2 -- sur un echantillon "
                    "a n <= 1 le cap est TRANSPARENT et un port qui somme rend la meme chose",
        observe="pas %d (%s) : #decoys adjacents par candidate = %r"
                % (sl_case.step, sl_case.visual_id, counts),
        remede="augmenter MAX_STEPS, ou rejouer `probe_212_spiritual_leader_tile_term.py` qui "
               "imprime chaque DRIVE et le profil (n, occupant) des candidates")


def test_term_is_capped_at_one_adjacent_decoy(sl_case):
    """LE COEUR DE #212 : le terme vaut le poids BC des qu'il y a UN decoy adjacent, et PAS PLUS.

    `vtbl+0x228 = 1` (`Min(count, 1)`) : deux candidates a 1 et a 3 decoys portent le MEME terme.
    Un port qui somme (comportement d'avant ce commit une fois l'ability au registre) rendrait
    30 / 60 / 90 -- cette assertion tombe. Un port sans l'entree au registre rendrait 0 partout --
    elle tombe aussi (`w > 0` et `terme == w`)."""
    w = sl_case.ctx.wt.sub("TriggeredAbilities", BC_KEY)
    tv = _terms_by_tile(sl_case)
    bad = {t: (round(v, 4), n) for t, (v, n) in tv.items()
           if abs(v - (w if n >= 1 else 0.0)) > 1e-6}
    assert not bad, (
        "pas %d (%s) : terme != %g x [au moins 1 decoy adjacent] sur %r. Le cap `vtbl+0x228` de "
        "`SpiritualLeaderPlaybook` vaut 1 (corps trivial `mov eax,1 ; ret`, lu au bloc "
        "methodPointers) : le terme NE SOMME PAS les decoys. ATTENTION -- AVANT d'accuser le port, verifier "
        "l'ORACLE : `n` est ici le comptage NATIF (`decoys_adjacent`, `is_adjacent`), pas la "
        "couronne hex -- une tuile a `n >= 1` pour la couronne et `n = 0` pour le natif rend 0.0 A "
        "BON DROIT, et c'est cette confusion qui a fait rougir ce test (cf. l'en-tete du fichier). "
        "(terme, n) par tuile = %r"
        % (sl_case.step, sl_case.visual_id, w, sorted(bad),
           {t: (round(v, 4), n) for t, (v, n) in tv.items()}))
