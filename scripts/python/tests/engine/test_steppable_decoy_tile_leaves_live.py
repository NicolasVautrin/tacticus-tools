"""GARDE #241 -- les deux feuilles de tuile a OCCUPANT STEPPABLE : `SteppableUnitUtility` (19) et
`AttractToDecoysUtility` (64), et le CONTEXTE sans lequel elles restaient muettes.

CE QUE CES GARDES PROTEGENT.

Les deux classes existaient et etaient fideles, mais AUCUN appelant ne posait leur metadonnee :
`apply_tile_attributes` ne derivait ni `meta.steppable`, ni `meta.decoy_gate`, ni
`meta.decoy_friend_count`, et `tile_leaf_ctx` ne posait pas `ctx.unit_faction`. Elles rendaient donc
0 en toute circonstance -- une degradation SILENCIEUSE (ni erreur ni crash), exactement le profil que
le self-play irait exploiter. Le chiffre : sur toute tuile candidate occupee par un decoy allie,
`X_natif - X_port` valait **+25** = `SteppableUnit.FriendlyDecoy(-50)` +
`DecoysAndMisdirection_AttractToDecoys.DecoysAndMisdirection_FriendlyGSCLikeDecoys(+75)` -- constant,
sur les DEUX montages (case-212 §7.1). Le port EGALISAIT des tuiles que le natif separe de 25, sur
toute bataille Genestealers.

Les faits LUS au decompile (`IdunBattle.AI.Utilities.SteppableUnitUtility.u003CEvaluateMovementIn
Stepsu003Ed__10$$MoveNext` et `IdunBattle.AI.Utilities.AttractToDecoysUtility.u003CEvaluateMovement
InStepsu003Ed__1$$MoveNext`), que ces gardes verrouillent un par un :

  * l'occupant qui compte est celui qui porte `UnitTrait.Steppable` (0x1b=27) -- PAS `Decoy`. Le trait
    `Decoy` (0x41d=1053) ne choisit qu'entre DEUX cles de la feuille 19 ;
  * le gate de la feuille 64 est `occupant steppable present ET !IsEnemy(occupant, mover)` -- donc
    une tuile SANS occupant steppable ne doit RIEN rendre (garde anti-pose-trop-large) ;
  * son compte boucle sur `GetAllAliveUnits` (slot 0x88 de l'interface de query, cf.
    `IdunBattle.Entities.Selectors.AllAliveUnitsSelector$$Select`), SANS filtre de position et SANS
    exclusion de self : c'est un compte de BATAILLE, pas de voisinage ;
  * `HasFaction(case.unit, 0xf)` = `UnitFaction.Genestealers` -- une autre faction ferme la feuille.

MONTAGES : les memes deux que case-212 (`genesMagus`/Xybia fabrique elle-meme les decoys que ces
feuilles lisent ; d'ou `--hp-*` eleve pour la laisser jouer plusieurs activations), plus
`genesPrimus`/Isaak dans l'equipe -- c'est LUI le porteur de `DecoysAndMisdirection` (1304) que le
compte de la feuille 64 retient.
  * `MC1_67`/777   pas 47 -- 4 candidates a occupant decoy sur 16 ;
  * `C4_09`/31337  pas 21 -- autre board, 2 candidates a occupant decoy sur 6.

Aucune valeur n'est gelee : les assertions re-derivent tout de la BC et du contexte du pas. Le
confront LIVE par tuile contre le natif (`X_nat - X_port == 0`, hooks `scorer-damage-trace`) vit dans
`probe_212_spiritual_leader_tile_term.py` -- ces gardes-ci sont son cliquet sans hook.

ASCII only.
"""
from __future__ import annotations

import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(__file__))      # tests/engine -> import du helper sibling

from _move_tile_sweep_order import build_sweep_order_case  # noqa: E402

CARRIER = "genesMagus"                             # HERO du pool, faction Genestealers
DECOY_UNIT = "genesSmnDecoy"                       # summon Steppable+Decoy pose par SpiritualLeader
ATTRACT_ABILITY = 1304                             # TriggeredAbilityType.DecoysAndMisdirection
CAT_19 = "SteppableUnit"
CAT_64 = "DecoysAndMisdirection_AttractToDecoys"
KEY_FRIENDLY_DECOY = "FriendlyDecoy"
KEY_GSC = "DecoysAndMisdirection_FriendlyGSCLikeDecoys"
# Les DEUX cles court-circuit de la feuille 19, LUES au decompile mais ABSENTES de cette BC : le
# natif les lit AVANT tout le reste, donc si elles apparaissaient un jour en BC, un steppable porteur
# de SpikySting(77)/LandMine(114) cesserait de valoir -50 et il faudrait relire le port.
KEYS_SHORTCIRCUIT = ("SpikyStingOnMovementTile", "Landmine")

_LONG = ["--hp-target", "100000", "--hp-player", "100000"]
_GENES = _LONG + [
    "--p-units", "genesMagus,genesPrimus,genesKelermorph,orksNob,spaceWulfen",
    "--a-units", "darkaHellblaster,eldarRanger,worldKharn,templChampion,tauMarksman"]

CASES = [("MC1_67", "777", 47, _GENES),
         ("C4_09", "31337", 21, _GENES)]


@pytest.fixture(scope="module", params=CASES, ids=lambda c: "%s-%s-s%d" % (c[0], c[1], c[2]))
def decoy_case(request, rpc, build_runner):
    board, seed, step, extra = request.param
    return build_sweep_order_case(rpc, build_runner, seed=seed, board=board, step=step, extra=extra)


def _leaf(name: str):
    """Feuille du composite Tile, designee par son MEMBRE `UtilityType` -- jamais par un litteral.

    #254 : la MAJ de build a renumerote `UtilityType` (`AttackTile` insere en 8, 59 membres decales
    de +1), donc `SteppableUnit` vaut 20 et non plus 19, `DecoysAndMisdirection_AttractToDecoys` 65
    et non plus 64. Un `_leaf(19)` litteral ne trouve alors plus rien (StopIteration) -- ou, pire,
    trouve la feuille du VOISIN."""
    from engine.utilities.tile import TILE_UTILITY
    from engine.utilities.utility_type import UtilityType
    want = int(getattr(UtilityType, name))
    return next(c for c in TILE_UTILITY.children if int(c.UTILITY_TYPE) == want)


def _metas(case):
    """{tuile candidate: (meta apres `apply_tile_attributes`, leaf_ctx)} -- MEME chaine que
    `engine.playbook.base.tile_utility` / `engine.move.best_move_faithful`, donc ce que les feuilles
    voient reellement en production (pas une variante de test)."""
    from engine.utilities.tile import tile_leaf_ctx, apply_tile_attributes
    lc = tile_leaf_ctx(case.ctx)
    return {t: apply_tile_attributes({}, t, lc) for t in (case.action_tiles or [])}, lc


def _occupant_visual(case, tile):
    """visualId de l'occupant VIVANT de `tile` d'apres `decisionView` (source independante du
    `leaf_ctx` : c'est ce qui rend la garde capable de contredire la pose)."""
    for u in (case.ctx.units or []):
        p = u.get("pos") or {}
        if u.get("alive") and (p.get("col"), p.get("row")) == tile:
            return u.get("visualId")
    return None


def test_case_still_activates_the_carrier(decoy_case):
    """Le montage n'a de sens que si le pas active bien Xybia ; sinon la trajectoire a derive."""
    assert decoy_case.visual_id == CARRIER, (
        "pas %d : porteur attendu %s, active %s -- trajectoire derivee, montage a re-etalonner"
        % (decoy_case.step, CARRIER, decoy_case.visual_id))


def test_bc_keys_are_present_and_shortcircuit_keys_are_absent(decoy_case):
    """Les 2 cles utilisees existent en BC ; les 2 cles court-circuit n'y sont PAS.

    Le natif teste `HasTriggeredAbility(occupant, 0x4d)` puis `0x72` AVANT le trait `Decoy`. Sur
    cette BC les deux cles correspondantes sont absentes -> `GetUtilityValue` rend 0. Si elles
    apparaissaient, le port continuerait a rendre 0 pour elles (`Weights.sub` d'une cle absente),
    ce qui deviendrait FAUX : d'ou cette assertion, qui force la relecture."""
    wt = decoy_case.ctx.wt
    assert wt.sub(CAT_19, KEY_FRIENDLY_DECOY) != 0, (
        "`Utilities.Default.%s.%s` rend 0 -- le litteral lu par "
        "`IdunBattle.AI.Utilities.SteppableUnitUtility.u003CEvaluateMovementInStepsu003Ed__10$$MoveNext` "
        "a disparu de la BC (BC re-dumpee ? build change ?)" % (CAT_19, KEY_FRIENDLY_DECOY))
    assert wt.sub(CAT_64, KEY_GSC) != 0, (
        "`Utilities.Default.%s.%s` rend 0 -- litteral disparu de la BC" % (CAT_64, KEY_GSC))
    now_present = [k for k in KEYS_SHORTCIRCUIT if wt.sub(CAT_19, k) != 0]
    assert not now_present, (
        "les cles court-circuit %r sont DESORMAIS en BC : la feuille 19 doit les rendre pour un "
        "steppable porteur de SpikySting(77)/LandMine(114), or le port ne connait leur valeur que "
        "par `Weights.sub` -- relire le decompile avant de conclure" % now_present)


def test_mover_faction_is_resolved_from_gameconfig(decoy_case):
    """`ctx.unit_faction` doit valoir `UnitFaction.Genestealers` -- sinon la feuille 64 est morte.

    C'est LA cle qui n'etait posee par aucun constructeur de `leaf_ctx` avant #241."""
    from engine.entities.unit_faction import UnitFaction
    _, lc = _metas(decoy_case)
    assert lc.get("unit_faction") == int(UnitFaction.Genestealers), (
        "pas %d (%s) : ctx.unit_faction = %r, attendu %d (%s). Sans cette cle "
        "`AttractToDecoysUtility` rend 0 quoi qu'il arrive."
        % (decoy_case.step, decoy_case.visual_id, lc.get("unit_faction"),
           int(UnitFaction.Genestealers), UnitFaction.Genestealers.name))


def test_montage_exercises_both_kinds_of_tile(decoy_case):
    """Sans candidate a occupant decoy ET candidate sans occupant steppable, les deux gardes
    suivantes passeraient a vide (l'une ne verrait jamais la pose, l'autre jamais son absence)."""
    metas, _ = _metas(decoy_case)
    with_occ = [t for t, m in metas.items() if m.get("steppable")]
    without = [t for t, m in metas.items() if not m.get("steppable")]
    assert with_occ and without, (
        "pas %d (%s) : %d candidate(s) a occupant steppable, %d sans -- il faut des DEUX"
        % (decoy_case.step, decoy_case.visual_id, len(with_occ), len(without)))
    # L'occupant steppable attendu sur ce montage est bien le decoy de Xybia, pas autre chose.
    vis = {_occupant_visual(decoy_case, t) for t in with_occ}
    assert vis == {DECOY_UNIT}, (
        "occupants steppables vus = %r, attendu {%r} -- la pose retient une unite qu'elle ne devrait "
        "pas (ou le montage a change)" % (sorted(v or "-" for v in vis), DECOY_UNIT))


def test_leaves_fire_exactly_on_tiles_with_a_friendly_steppable_occupant(decoy_case):
    """LE COEUR DE #241, dans les DEUX sens.

    Sur une candidate occupee par un decoy ALLIE : feuille 19 = `FriendlyDecoy`, feuille 64 =
    `n x FriendlyGSCLikeDecoys` avec `n` RE-DERIVE (amis vivants porteurs de 1304, self inclus).
    Sur une candidate sans occupant steppable : les DEUX feuilles rendent 0 -- c'est la contre-epreuve
    d'une pose trop large, qui se verrait ici et nulle part ailleurs."""
    wt = decoy_case.ctx.wt
    l19, l64 = _leaf(CAT_19), _leaf(CAT_64)
    metas, lc = _metas(decoy_case)
    n = 1 if ATTRACT_ABILITY in (lc.get("unit_triggered_abilities") or ()) else 0
    n += sum(1 for u in (lc.get("friend_units") or ())
             if ATTRACT_ABILITY in (u.get("triggered") or ()))
    assert n >= 1, (
        "pas %d : aucun ami porteur de %d (DecoysAndMisdirection) -- le terme de la feuille 64 vaut "
        "0 par construction, le montage ne peut rien contredire (genesPrimus est-il encore vivant ?)"
        % (decoy_case.step, ATTRACT_ABILITY))
    exp19, exp64 = wt.sub(CAT_19, KEY_FRIENDLY_DECOY), n * wt.sub(CAT_64, KEY_GSC)
    bad = {}
    for t, m in metas.items():
        v19 = l19.evaluate(t, m, lc, wt)
        v64 = l64.evaluate(t, m, lc, wt)
        occ = m.get("steppable")
        want = (exp19, exp64) if (occ and not occ["is_enemy"]) else (0.0, 0.0)
        if occ and occ["is_enemy"]:                     # pas exerce par ces montages, mais explicite
            want = (wt.sub(CAT_19, "EnemyDecoy" if occ["is_decoy"] else "EnemySteppableUnit"), 0.0)
        if abs(v19 - want[0]) > 1e-6 or abs(v64 - want[1]) > 1e-6:
            bad[t] = {"occupant": _occupant_visual(decoy_case, t), "steppable": occ,
                      "got": (v19, v64), "want": want}
    assert not bad, (
        "pas %d (%s) : feuilles 19/64 hors contrat sur %d tuile(s). n(amis 1304) = %d, "
        "FriendlyDecoy = %g, GSC = %g. Detail : %r"
        % (decoy_case.step, decoy_case.visual_id, len(bad), n, exp19, wt.sub(CAT_64, KEY_GSC), bad))


def test_residual_on_decoy_tiles_is_the_measured_plus_25(decoy_case):
    """Le residu que #241 ferme, re-derive : sur une tuile a decoy allie, les deux feuilles somment
    `FriendlyDecoy + n x GSC`. Avec `n == 1` (le seul porteur de 1304 de ce roster est `genesPrimus`)
    cela vaut exactement **+25**, le chiffre mesure par case-212 §7.1 contre le natif.

    La garde n'assert pas « 25 » en dur : elle assert que la somme des deux feuilles est bien celle
    de la BC. Un port qui n'armerait qu'UNE des deux feuilles rendrait -50 ou +75 et tomberait ici,
    en nommant laquelle."""
    wt = decoy_case.ctx.wt
    l19, l64 = _leaf(CAT_19), _leaf(CAT_64)
    metas, lc = _metas(decoy_case)
    n = 1 if ATTRACT_ABILITY in (lc.get("unit_triggered_abilities") or ()) else 0
    n += sum(1 for u in (lc.get("friend_units") or ())
             if ATTRACT_ABILITY in (u.get("triggered") or ()))
    exp = wt.sub(CAT_19, KEY_FRIENDLY_DECOY) + n * wt.sub(CAT_64, KEY_GSC)
    got = {t: round(l19.evaluate(t, m, lc, wt) + l64.evaluate(t, m, lc, wt), 4)
           for t, m in metas.items() if m.get("steppable") and not m["steppable"]["is_enemy"]}
    assert got and all(abs(v - exp) < 1e-6 for v in got.values()), (
        "pas %d (%s) : somme des feuilles 19+64 sur les tuiles a occupant steppable allie = %r, "
        "attendu %g partout (= FriendlyDecoy %g + %d x GSC %g)"
        % (decoy_case.step, decoy_case.visual_id, got, exp,
           wt.sub(CAT_19, KEY_FRIENDLY_DECOY), n, wt.sub(CAT_64, KEY_GSC)))


# --------------------------------------------------------------------------- table de BRANCHEMENT
# Les quatre cas ci-dessous ne sont PAS atteignables par un montage live, et c'est structurel :
# les tuiles candidates d'une decision sont `[origine] + aiMovableTiles`, or `aiMovableTiles`
# n'expose que des tuiles LIBRES ou occupees par un `Steppable` (c'est precisement ce que le trait
# autorise). Une candidate a occupant NON steppable autre que l'origine n'existe donc pas -- MESURE :
# la mutation « ne plus tester `Steppable` dans `_steppable_occupant` » laisse les 12 gardes live
# ci-dessus VERTES. Un occupant steppable ENNEMI n'apparait pas davantage sur ces deux montages
# (les decoys sont ceux de Xybia, du cote du mover).
#
# Ces assertions ne gelent aucune MESURE : elles gelent la table de branchement LUE au decompile
# (`GetSteppableUnit` filtre sur `0x1b`, `IsFriend` cote Decoy / `IsEnemy` cote non-Decoy, et les
# deux court-circuits `SpikySting`/`LandMine` AVANT tout le reste). Sans elles, ces branches ne sont
# couvertes par rien.

def _lc(**over):
    """leaf_ctx synthetique MINIMAL -- seules les cles que `_steppable_occupant` lit."""
    base = {"self_pos": None, "unit_traits": (), "unit_triggered_abilities": (),
            "friend_units": (), "enemy_units": ()}
    base.update(over)
    return base


def _u(pos, traits, triggered=()):
    return {"pos": pos, "traits": tuple(traits), "triggered": tuple(triggered), "vis": "x", "id": 1}


def test_branch_table_of_the_steppable_occupant():
    """`_steppable_occupant` = `IdunBattle.Entities.TileExtensions$$GetSteppableUnit` + les lectures
    que la feuille 19 fait ensuite sur l'occupant."""
    from engine.utilities.tile import _steppable_occupant
    T = (2, 3)
    # occupant NON steppable -> pas d'occupant steppable (le natif rend false), meme s'il est Decoy
    assert _steppable_occupant(T, _lc(friend_units=[_u(T, ("Decoy",))])) is None
    # tuile vide
    assert _steppable_occupant(T, _lc(friend_units=[_u((9, 9), ("Steppable",))])) is None
    # ami steppable non decoy / ami steppable decoy
    assert _steppable_occupant(T, _lc(friend_units=[_u(T, ("Steppable",))])) == {
        "is_friend": True, "is_enemy": False, "is_decoy": False, "triggered": ()}
    assert _steppable_occupant(T, _lc(friend_units=[_u(T, ("Steppable", "Decoy"), (77,))])) == {
        "is_friend": True, "is_enemy": False, "is_decoy": True, "triggered": (77,)}
    # ennemi steppable decoy
    assert _steppable_occupant(T, _lc(enemy_units=[_u(T, ("Steppable", "Decoy"))])) == {
        "is_friend": False, "is_enemy": True, "is_decoy": True, "triggered": ()}
    # le MOVER sur son ORIGINE : self-exclu de `friend_units`, donc branche dediee. `unit_traits`
    # est une liste d'IDS (27 = Steppable, 1053 = Decoy), pas de noms.
    assert _steppable_occupant(T, _lc(self_pos=T, unit_traits=(16,))) is None      # hero -> rien
    assert _steppable_occupant(T, _lc(self_pos=T, unit_traits=(27, 1053),
                                      unit_triggered_abilities=(1304,))) == {
        "is_friend": True, "is_enemy": False, "is_decoy": True, "triggered": (1304,)}


def test_leaf_19_branch_order_shortcircuits_before_the_decoy_trait():
    """Les deux `HasTriggeredAbility` passent AVANT `HasTrait(0x41d)` dans le natif : un decoy ALLIE
    porteur de `SpikySting`(77) ou `LandMine`(114) ne vaut PAS `FriendlyDecoy`, il vaut la cle
    court-circuit -- 0 sur cette BC, ou elle est absente. Inverser l'ordre rendrait -50."""
    from engine import weights as W
    wt = W.load()
    l19 = _leaf(CAT_19)
    friendly_decoy = {"is_friend": True, "is_enemy": False, "is_decoy": True}
    assert l19.evaluate((0, 0), {"steppable": dict(friendly_decoy, triggered=())}, {}, wt) \
        == wt.sub(CAT_19, KEY_FRIENDLY_DECOY)
    for ab in (77, 114):
        assert l19.evaluate((0, 0), {"steppable": dict(friendly_decoy, triggered=(ab,))}, {}, wt) \
            == 0.0, "la branche court-circuit %d ne prime plus sur le trait Decoy" % ab
