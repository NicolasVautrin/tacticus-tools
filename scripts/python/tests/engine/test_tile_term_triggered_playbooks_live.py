"""GARDE N13 -- le TERME DE TUILE Tile(7) et les playbooks de la feuille TriggeredAbilities(2).

CE QUE CES GARDES PROTEGENT. Le composite `Tile(7)` (29 feuilles, enumerees live par
`scorerComposedDump`) contient la feuille DISPATCHER `TriggeredAbilities(2)` :
`IdunBattle.AI.Utilities.TriggeredAbilitiesUtility.u003CEvaluateMovementInStepsu003Ed__2$$MoveNext`
itere les abilities DECLENCHEES de l'unite qui bouge, charge le playbook singleton par type
(`IdunBattle.AI.PlaybookDatabase$$LoadPlaybook`) et somme leurs
`CalculateMovementUtilityInSteps`. Un playbook ABSENT du registre du port = un terme qui MANQUE
au Tile(7), donc des tuiles que le port EGALISE alors que le natif les SEPARE -- des ties
ARTEFACTS, et un depart de decision arbitraire (cf. `docs/rl/case-n13-tile-term-triggered-playbooks.md`).

TROIS montages INDEPENDANTS, chacun exercant un porteur different :
  * `C4_09`/999 pas 14 -- u98 templAncient, passif `AstartesBanner` (1106) : natif Tile(7)
    (4,4)=45 vs (6,4)=40 ; le port EGALISAIT les deux a 30 -> tie artefact, tuile choisie
    arbitraire ;
  * `C4_09`/31337 pas 22 -- u84 admecMarshall, RELIQUE `KardiocoreGalvanus` (1457) + la feuille
    `UnitEffectsRanged(13)` (`PathOfCommand_ExtraDmg` porte par l'Autarch a 2 hex) : natif
    (2,4)=45 / (3,6)=40 / (2,5)=35 ; le port EGALISAIT les TROIS a 30 ;
  * `C3_01`/777 pas 14 -- montage CRAFTE sur un AUTRE BOARD (`--p-units`), templAncient : natif
    (3,5)=45 / (4,5)=40 / (5,5)=25 -> generalisation geometrique du meme terme.

L'assertion est un AGREEMENT LIVE : la tuile retenue par `_best_attack` doit etre celle que le
natif joue au meme pas (`aiStepDryRun` du meme run). Aucune valeur native n'est gelee dans le
test -- les chiffres ci-dessus ne sont que la trace de la mesure qui a fonde le port.

ASCII only.
"""
from __future__ import annotations

import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(__file__))      # tests/engine -> import du helper sibling

from _move_tile_sweep_order import build_sweep_order_case  # noqa: E402

# (board, seed, pas, porteur attendu, ability declenchee attendue). Le porteur ET son ability sont
# verifies : un montage ou l'unite activee aurait change (drift de trajectoire), ou dont le kit
# declenche ne remonterait plus l'ability, n'a plus rien a prouver.
#   1106 AstartesBanner      = passif gameconfig de templAncient
#   1457 KardiocoreGalvanus  = RELIQUE d'admecMarshall -> ABSENTE du gameconfig, elle ne peut venir
#                              que de la lecture live du TriggeredAbilityComponent
#
# Le 3e montage est CRAFTE (`--p-units`) et sur un AUTRE BOARD : il sort le terme du seul `C4_09`
# et prouve la GENERALISATION geometrique (autre plateau, autres allies, autres distances).
#
# ⚠ #506-r1 -- LE PAS N'EST PLUS EPINGLE, IL EST CHERCHE. Les trois montages marchent une
# trajectoire 100 % NATIVE : toute tranche qui change une stat globale la deplace. La bascule
# « equiper » de #419-r6 (`c4be3896`) l'a fait -- au pas 14 de `C4_09`/999 c'est desormais
# `astraCreed` qui est activee, et le pas 22 de `C4_09`/31337 n'existe plus (la bataille finit au
# pas 21). Les assertions ci-dessous n'ont PAS bouge : ce qui avait peri, c'est la PREMISSE que le
# montage installait. Le pas de depart reste celui de la mesure d'origine, `search` ouvre la
# fenetre, et le couple (porteur, ability declenchee) est le critere -- exactement ce que les deux
# premieres assertions du fichier verifiaient deja.
_TEMPL = ["--p-units", "templAncient,ultraApothecary,astraCreed,templChampion,tauDarkstrider"]
# (board, seed, pas de DEPART, largeur de recherche, porteur attendu, ability declenchee, extra)
CASES = [("C4_09", "999", 14, 24, "templAncient", 1106, []),
         ("C4_09", "31337", 8, 20, "admecMarshall", 1457, []),
         ("C3_01", "777", 14, 24, "templAncient", 1106, _TEMPL)]


@pytest.fixture(scope="module", params=CASES, ids=lambda c: "%s-%s-s%d" % c[:3])
def tile_term_case(request, rpc, build_runner):
    board, seed, step, search, _vid, _ab, extra = request.param

    def _porte_l_ability(c):
        """Le pas ne convient que s'il installe les DEUX premisses que les assertions supposent :

          * le KIT DECLENCHE du porteur remonte bien l'ability visee -- MEME lecture que
            `test_kit_source_carries_the_triggered_ability`, decisive pour 1457
            `KardiocoreGalvanus` (une RELIQUE : seul le `TriggeredAbilityComponent` lu live la
            remonte, jamais `gameconfig.passiveAbilities`) ;
          * le pas porte une action d'ATTAQUE (`_best_attack` rend quelque chose). Les trois
            assertions de tie/agreement ouvrent toutes sur `assert c.best is not None` : un pas de
            MOUVEMENT PUR n'a aucune paire (ability, cible) a departager. Mesure : sur
            `C4_09`/31337 le premier pas d'`admecMarshall` trouve (18) est un mouvement pur, et
            les deux gardes y tombaient sur leur propre premisse.

        Le montage n'anticipe donc AUCUNE assertion -- il installe ce qu'elles exigent."""
        from engine.utilities.tile import tile_leaf_ctx
        if c.best is None:
            return False
        return _ab in (tile_leaf_ctx(c.ctx).get("unit_triggered_abilities") or [])

    c = build_sweep_order_case(rpc, build_runner, seed=seed, board=board, step=step, extra=extra,
                               carrier=_vid, accept=_porte_l_ability, search=search)
    c.expected_visual_id = _vid
    c.expected_ability = _ab
    print("\n[N13] %s/%s : pas RETENU %d (%s), %d pas ecarte(s) %r"
          % (board, seed, c.step, c.visual_id, len(c.searched or []), (c.searched or [])[:6]))
    return c


def test_kit_source_carries_the_triggered_ability(tile_term_case):
    """Le KIT DECLENCHE que le dispatcher va iterer contient bien l'ability du porteur.

    C'est la garde de SOURCE, distincte de la garde de formule : sans elle, un playbook peut etre
    enregistre et n'etre JAMAIS appele (port speculatif). Elle est decisive pour 1457
    `KardiocoreGalvanus`, une RELIQUE : `gameconfig.passiveAbilities` ne la contient pas, seul le
    `TriggeredAbilityComponent` lu live (`unitAbilityStates`) la remonte."""
    from engine.utilities.tile import tile_leaf_ctx
    c = tile_term_case
    kit = tile_leaf_ctx(c.ctx).get("unit_triggered_abilities") or []
    assert c.expected_ability in kit, (
        "pas %d (%s) : ability %d absente du kit declenche %r -- le playbook porte ne sera JAMAIS "
        "appele par le dispatcher TriggeredAbilities(2)"
        % (c.step, c.visual_id, c.expected_ability, kit))


def test_case_still_activates_the_expected_carrier(tile_term_case):
    """Le montage n'a de sens que si le pas active bien le PORTEUR vise (AstartesBanner /
    KardiocoreGalvanus) : sinon la trajectoire a derive et les gardes suivantes ne testent rien."""
    c = tile_term_case
    assert c.visual_id == c.expected_visual_id, (
        "pas %d : porteur attendu %s, active %s -- trajectoire derivee, montage a re-etalonner"
        % (c.step, c.expected_visual_id, c.visual_id))


def test_no_artefact_tie_at_the_top(tile_term_case):
    """AUCUN TIE au sommet : sur ces trois pas, le natif SEPARE strictement ses meilleures tuiles
    (Delta Tile(7) de 5 sur chacun des montages, mesure aux hooks). Un tie cote port y est donc
    forcement un ARTEFACT -- la signature exacte du terme de tuile manquant : sans lui les tuiles
    de meme elevation s'egalisent et le keep-first tranche au hasard de l'ordre de sweep."""
    c = tile_term_case
    assert c.best is not None, "aucune action d'attaque retenue au pas %d" % c.step
    assert len(c.tie_tiles) <= 1, (
        "pas %d (%s) : TIE ARTEFACT sur %r a u=%.4f -- le natif separe ces tuiles, le port les "
        "egalise : un terme de Tile(7) manque. Tile(7) du port = %r"
        % (c.step, c.visual_id, c.tie_tiles, c.best[1],
           {k: round(v, 4) for k, v in c.tile_terms.items()}))


def test_best_attack_tile_agrees_with_native(tile_term_case):
    """AGREEMENT LIVE : la tuile retenue par le sweep du port == la tuile jouee par le natif.

    C'est la garde qui tombe ROUGE sans le terme de tuile manquant : a Tile(7) plat, le keep-first
    de `Bucket$$AddAction` retient la premiere tuile d'`action_tiles` a l'utilite (fausse) maximale,
    qui n'est pas celle du natif."""
    c = tile_term_case
    assert c.best is not None, "aucune action d'attaque retenue au pas %d" % c.step
    assert c.best[4] == c.native_tile, (
        "pas %d (%s) : le port retient la tuile %r, le natif joue %r. "
        "Tile(7) du port = %r ; action_tiles=%r"
        % (c.step, c.visual_id, c.best[4], c.native_tile,
           {k: round(v, 4) for k, v in c.tile_terms.items()}, c.action_tiles))
