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

MONTAGES (deux boards, deux seeds) -- `genesMagus` fabrique elle-meme les decoys que ce terme compte
(sa face COMBAT pose un `genesSmnDecoy` a la fin de chaque activation), donc il faut la laisser jouer
plusieurs tours : d'ou `--hp-*` eleve, sans quoi la bataille se termine avant qu'un seul decoy soit
adjacent a plus d'une tuile candidate (mesure : 1re activation, `#decoys = [0]` sur TOUTES les
candidates -- un montage qui ne peut rien contredire).
  * `MC1_67`/777   pas 47 -- candidates a 0, 1, 2 ET 3 decoys adjacents ;
  * `C4_09`/31337  pas 21 -- autre board, candidates a 0, 1 ET 2.

Mesure fondatrice (`probe_212_spiritual_leader_tile_term.py`, decomposition
`X = Tile(7) - Elevation - TileEffects` aux hooks EXISTANTS de `scorer-damage-trace`) :
`X_nat` = 30 pour n = 1, 2 ET 3, et `X_nat - X_port` = 0 sur les 18 tuiles dont l'occupant n'est pas
un decoy ami (22 tuiles mesurees, 2 boards). Les 4 tuiles restantes portent un residu CONSTANT de
+25 -- deux feuilles de tuile INERTES faute de metadonnee (`case-212` §7), etranger a 1275.
AUCUNE de ces valeurs n'est gelee ici : les assertions re-derivent tout du contexte du pas.

ASCII only.
"""
from __future__ import annotations

import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(__file__))      # tests/engine -> import du helper sibling

from _move_tile_sweep_order import build_sweep_order_case  # noqa: E402

ABILITY = 1275                                     # TriggeredAbilityType.SpiritualLeader
CARRIER = "genesMagus"
BC_KEY = "SPIRITUALLDEADER_AdjacentDecoy"          # la cle REELLE (faute de frappe du jeu)
BC_KEY_MISSPELL_FIXED = "SPIRITUALLEADER_AdjacentDecoy"   # ce qu'une « correction » produirait
DECOY_TRAIT = "Decoy"                              # UnitTrait.Decoy = 0x41d = 1053

# Bataille LONGUE : Xybia doit pouvoir jouer plusieurs activations pour semer ses decoys.
_LONG = ["--hp-target", "100000", "--hp-player", "100000"]
_GENES = _LONG + [
    "--p-units", "genesMagus,genesPrimus,genesKelermorph,orksNob,spaceWulfen",
    "--a-units", "darkaHellblaster,eldarRanger,worldKharn,templChampion,tauMarksman"]

CASES = [("MC1_67", "777", 47, _GENES),
         ("C4_09", "31337", 21, _GENES)]


@pytest.fixture(scope="module", params=CASES, ids=lambda c: "%s-%s-s%d" % (c[0], c[1], c[2]))
def sl_case(request, rpc, build_runner):
    board, seed, step, extra = request.param
    return build_sweep_order_case(rpc, build_runner, seed=seed, board=board, step=step, extra=extra)


def _terms_by_tile(case):
    """{tuile: (terme du playbook 1275, nombre de DECOYS allies a distance 1)} sur les candidates."""
    import hexgeo
    from engine.utilities.tile import tile_leaf_ctx
    from engine.playbook.adjacent_unit_preference import load_playbook
    pb = load_playbook(ABILITY)
    assert pb is not None, "ability %d absente de TRIGGERED_MOVE_PLAYBOOKS" % ABILITY
    lc = tile_leaf_ctx(case.ctx)
    out = {}
    for t in (case.action_tiles or []):
        n = sum(1 for u in (lc.get("friend_units") or ())
                if hexgeo.distance(t, u["pos"]) == 1 and DECOY_TRAIT in (u.get("traits") or ()))
        out[t] = (pb.calculate_movement_utility_in_steps(t, lc, case.ctx.wt), n)
    return out


def test_case_still_activates_the_carrier(sl_case):
    """Le montage n'a de sens que si le pas active bien Xybia ; sinon la trajectoire a derive."""
    assert sl_case.visual_id == CARRIER, (
        "pas %d : porteur attendu %s, active %s -- trajectoire derivee, montage a re-etalonner"
        % (sl_case.step, CARRIER, sl_case.visual_id))


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
    chose."""
    counts = sorted({n for (_, n) in _terms_by_tile(sl_case).values()})
    assert 0 in counts and max(counts) >= 2, (
        "pas %d (%s) : #decoys adjacents par candidate = %r -- il faut au moins une tuile a 0 et une "
        "a >=2 pour exercer le cap" % (sl_case.step, sl_case.visual_id, counts))


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
        "methodPointers) : le terme NE SOMME PAS les decoys. (terme, n) par tuile = %r"
        % (sl_case.step, sl_case.visual_id, w, sorted(bad),
           {t: (round(v, 4), n) for t, (v, n) in tv.items()}))
