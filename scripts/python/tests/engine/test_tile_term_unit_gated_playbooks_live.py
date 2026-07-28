"""GARDE #193c -- les playbooks de MOUVEMENT dont le poids DEPEND DU VOISIN.

CE QUE CES GARDES PROTEGENT. La feuille dispatcher `TriggeredAbilities(2)` du composite `Tile(7)`
somme les `CalculateMovementUtilityInSteps` des playbooks de l'unite qui bouge. Pour la famille
`AdjacentUnitPreferenceTriggeredAbilityPlaybook`, le corps commun appelle son accesseur de poids
UNE FOIS PAR VOISIN RETENU (`GetAdjacent{Friend,Enemy}Utility(unit, ctx)`) -- l'unite voisine est un
ARGUMENT, pas un decor. Deux concrets le LISENT :

  * `IdunBattle.AI.Playbook.Loki.HatefulAssaultPlaybook$$GetAdjacentEnemyUtility` (1038,
    `blackTerminator`) : `HasRangedWeapon(u) ? _AdjacentEnemyRanged (20) : _AdjacentEnemyDefault (10)` ;
  * `IdunBattle.AI.Playbook.Loki.FearedInterrogatorPlaybook$$GetAdjacentFriendUtility` (1235,
    `darkaAsmodai`) : `HasFaction(u, 10 DarkAngels) ? _AdjacentDAFriend (30) : 0`.

Tant que le port hissait le poids HORS de la boucle (legitime pour les 4 concrets a lookup PLAT
portes avant), ces deux termes etaient INEXPRIMABLES : aucune valeur unique ne separe deux tuiles
qui ont le MEME NOMBRE de voisins mais pas les MEMES voisins. C'est cette separation que les gardes
verifient -- pas seulement « le port trouve la bonne tuile ».

QUATRE montages, deux boards, deux porteurs (`--hp-*` eleve : la bataille dure assez pour que les
unites se melangent, sinon le terme reste constant et la mesure ne peut RIEN contredire) :
  * `MC1_67`/777 pas 34  -- u87 blackTerminator : natif X=(5,6)20 (6,5)20 (4,4)10 (5,7)40 (3,4)10 ;
    (5,6) et (4,4) ont TOUTES DEUX un seul ennemi adjacent, et valent 20 vs 10 (arme de portee vs melee) ;
  * `C4_09`/31337 pas 31 -- meme porteur, autre board, autres voisins ;
  * `MC1_67`/777 pas 28  -- u87 darkaAsmodai : (3,3) et (3,4) ont TOUTES DEUX un seul ami adjacent,
    et valent 30 vs 0 (DarkAngels vs SpaceWolves) ;
  * `C4_09`/999 pas 26   -- meme porteur, autre board.

Les valeurs ci-dessus sont la trace de la mesure fondatrice (`probe_193c_move_playbook_terms.py`,
decomposition `X = Tile(7) - Elevation - TileEffects` aux hooks `scorer-damage-trace`) : AUCUNE
n'est gelee dans une assertion. Les assertions sont un AGREEMENT LIVE + une propriete STRUCTURELLE
re-derivee du contexte du pas.

ASCII only.
"""
from __future__ import annotations

import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(__file__))      # tests/engine -> import du helper sibling

from _move_tile_sweep_order import build_sweep_order_case  # noqa: E402

# Batailles LONGUES : sans `--hp-*` eleve les rosters s'effondrent avant de se melanger et le terme
# reste constant sur toutes les tuiles candidates (mesure : MC1_67/777 sans, bataille finie au pas 17,
# terme = 20 partout). Ce n'est PAS un reglage cosmetique : c'est ce qui rend le montage discriminant.
_LONG = ["--hp-target", "100000", "--hp-player", "100000"]
_HATEFUL = _LONG + [
    "--p-units", "blackTerminator,spaceWulfen,orksNob,templSwordBrother,bloodIntercessor",
    "--a-units", "darkaHellblaster,eldarRanger,worldKharn,templChampion,tauMarksman"]
# Cote AMIS : 2 DarkAngels + 2 non-DA dans MON roster -> le gate de faction separe des tuiles a
# nombre d'amis adjacents EGAL.
_FEARED = _LONG + [
    "--p-units", "darkaAsmodai,darkaTerminator,darkaCompanion,orksNob,spaceWulfen",
    "--a-units", "worldKharn,templChampion,eldarJainZar,tyranDeathleaper,custoTrajann"]

# --- #211 CursedPlagueBell (1071, `deathBlightbringer`) : le seul concret qui gate les DEUX faces.
# Ses deux montages sont VOLONTAIREMENT sans `--hp-*` : le porteur est active tot et la geometrie
# discriminante apparait avant le pas 30 (mesure `probe_211_cursed_plague_bell.py`) ; gonfler les PV
# reecrit la trajectoire et deplace le pas.
#   `_CPB_FRIEND` : 2 amis de grande alliance Chaos (deathBlightlord, thousSorcerer) + 2 hors Chaos
#     -> le gate `HasTrait(u, 0x7ea)` separe des tuiles a nombre d'amis adjacents EGAL.
#   `_CPB_ENEMY`  : AUCUN ami Chaos (la face amie est muette, le terme ne vient que des ennemis) et
#     un melange melee-Psychic (bloodMephiston, astraPrimarisPsy -> 10) / Psychic de PORTEE
#     (thousAhriman -> 0, c'est le gate `WeaponProfile$$get_IsMelee`) / non-Psychic (-> 0).
_CPB_FRIEND = [
    "--p-units", "deathBlightbringer,deathBlightlord,thousSorcerer,astraBullgryn,necroWarden",
    "--a-units", "bloodMephiston,astraPrimarisPsy,thousAhriman,tauMarksman,orksNob"]
_CPB_ENEMY = [
    "--p-units", "deathBlightbringer,astraBullgryn,necroWarden,orksNob,eldarRanger",
    "--a-units", "bloodMephiston,astraPrimarisPsy,thousAhriman,tauMarksman,templChampion"]

CASES = [("MC1_67", "777", 34, "blackTerminator", 1038, "enemy_units", _HATEFUL),
         ("C4_09", "31337", 31, "blackTerminator", 1038, "enemy_units", _HATEFUL),
         ("MC1_67", "777", 28, "darkaAsmodai", 1235, "friend_units", _FEARED),
         ("C4_09", "999", 26, "darkaAsmodai", 1235, "friend_units", _FEARED),
         ("MC1_67", "777", 25, "deathBlightbringer", 1071, "friend_units", _CPB_FRIEND),
         ("MC1_67", "2468", 19, "deathBlightbringer", 1071, "enemy_units", _CPB_ENEMY)]


@pytest.fixture(scope="module", params=CASES, ids=lambda c: "%s-%s-s%d-%s" % (c[0], c[1], c[2], c[3]))
def gated_case(request, rpc, build_runner):
    board, seed, step, vid, ab, side, extra = request.param
    c = build_sweep_order_case(rpc, build_runner, seed=seed, board=board, step=step, extra=extra)
    c.expected_visual_id = vid
    c.expected_ability = ab
    c.neighbour_side = side
    return c


def _terms_by_tile(case):
    """Terme du playbook teste, tuile candidate par tuile candidate, + le nombre de voisins R1 du
    COTE que ce playbook lit (amis pour 1235, ennemis pour 1038)."""
    import hexgeo
    from engine.utilities.tile import tile_leaf_ctx
    from engine.playbook.adjacent_unit_preference import load_playbook
    pb = load_playbook(case.expected_ability)
    lc = tile_leaf_ctx(case.ctx)
    out = {}
    for t in (case.action_tiles or []):
        n = sum(1 for u in (lc.get(case.neighbour_side) or ())
                if hexgeo.distance(t, u["pos"]) == 1)
        out[t] = (pb.calculate_movement_utility_in_steps(t, lc, case.ctx.wt), n)
    return out


def test_kit_source_carries_the_triggered_ability(gated_case):
    """GARDE DE SOURCE : sans elle un playbook peut etre au registre et n'etre JAMAIS appele
    (port speculatif, vert par coincidence -- la lecon de N13)."""
    from engine.utilities.tile import tile_leaf_ctx
    c = gated_case
    kit = tile_leaf_ctx(c.ctx).get("unit_triggered_abilities") or []
    assert c.expected_ability in kit, (
        "pas %d (%s) : ability %d absente du kit declenche %r -- le playbook ne sera JAMAIS appele"
        % (c.step, c.visual_id, c.expected_ability, kit))


def test_case_still_activates_the_expected_carrier(gated_case):
    """Le montage n'a de sens que si le pas active bien le PORTEUR vise ; sinon la trajectoire a
    derive et tout ce qui suit ne teste rien."""
    c = gated_case
    assert c.visual_id == c.expected_visual_id, (
        "pas %d : porteur attendu %s, active %s -- trajectoire derivee, montage a re-etalonner"
        % (c.step, c.expected_visual_id, c.visual_id))


def test_weight_really_depends_on_WHICH_neighbour(gated_case):
    """LE COEUR DE #193c : AUCUN poids unique par voisin ne reproduit le terme sur ce pas.

    Formellement : le rapport `terme / (nombre de voisins R1 du cote lu)` prend au moins DEUX
    valeurs distinctes sur les tuiles candidates. Un accesseur a lookup PLAT rendrait `w x n`, donc
    un rapport CONSTANT -- c'est exactement ce que le port faisait avant #193c en hissant le poids
    hors de la boucle. Le test couvre les deux formes observees : deux tuiles a MEME `n` et termes
    differents (20 vs 10 pour un unique ennemi melee vs a portee), et un `n` plus grand dont le
    terme n'est PAS proportionnel (2 ennemis -> 30 = 20+10, ni 20 ni 40).

    Cette propriete certifie que le montage EXERCE le gate `HasRangedWeapon` / `HasFaction`. Si la
    trajectoire derive vers une geometrie ou tous les voisins se valent, ce test tombe -- plutot
    que de laisser les gardes suivantes passer a vide."""
    c = gated_case
    tv = _terms_by_tile(c)
    ratios = {round(val / n, 6) for (val, n) in tv.values() if n}
    assert len(ratios) > 1, (
        "pas %d (%s, ability %d) : terme/voisins CONSTANT (%r) -- un poids unique suffirait, "
        "le montage ne teste PAS la dependance au voisin. (terme, n) par tuile = %r"
        % (c.step, c.visual_id, c.expected_ability, sorted(ratios),
           {t: (round(v, 4), n) for t, (v, n) in tv.items()}))


def test_no_artefact_tie_at_the_top(gated_case):
    """Aucun TIE au sommet : le natif SEPARE ces tuiles (mesure aux hooks). Un tie cote port y est
    la signature exacte du terme de tuile manquant."""
    c = gated_case
    assert c.best is not None, "aucune action d'attaque retenue au pas %d" % c.step
    assert len(c.tie_tiles) <= 1, (
        "pas %d (%s) : TIE ARTEFACT sur %r a u=%.4f -- Tile(7) du port = %r"
        % (c.step, c.visual_id, c.tie_tiles, c.best[1],
           {k: round(v, 4) for k, v in c.tile_terms.items()}))


def test_best_attack_tile_agrees_with_native(gated_case):
    """AGREEMENT LIVE : la tuile retenue par le sweep du port == celle que le natif joue au meme pas."""
    c = gated_case
    assert c.best is not None, "aucune action d'attaque retenue au pas %d" % c.step
    assert c.best[4] == c.native_tile, (
        "pas %d (%s) : le port retient %r, le natif joue %r. Tile(7) du port = %r ; action_tiles=%r"
        % (c.step, c.visual_id, c.best[4], c.native_tile,
           {k: round(v, 4) for k, v in c.tile_terms.items()}, c.action_tiles))
