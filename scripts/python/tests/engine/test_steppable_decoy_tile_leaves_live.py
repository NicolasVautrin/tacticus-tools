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

MONTAGE -- ON PILOTE LES POSITIONS (2026-08-03). `genesMagus`/Xybia fabrique elle-meme les decoys
que ces feuilles lisent (d'ou `--hp-*` eleve pour la laisser jouer plusieurs activations), et
`genesPrimus`/Isaak est dans l'equipe -- c'est LUI le porteur de `DecoysAndMisdirection` (1304) que
le compte de la feuille 64 retient. Mais ATTENDRE que la geometrie de spawn amene un decoy sur une
candidate est un echantillon SUBI : il tenait a un numero de pas en dur (47 / 21) sur une
trajectoire native que rien ne fige. On marche donc la trajectoire en DEPLACANT le carrier vers les
decoys (`walk_driven` de `probe_212_spiritual_leader_tile_term.py`, `goals_241` de
`probe_241_decoy_tile_leaves.py`), et on s'arrete au premier pas ou le regime est REALISE.

Aucune valeur n'est gelee : les assertions re-derivent tout de la BC et du contexte du pas. Le
confront LIVE par tuile contre le natif (`X_nat - X_port == 0`, hooks `scorer-damage-trace`) vit dans
`probe_241_decoy_tile_leaves.py` -- ces gardes-ci sont son cliquet sans hook.

ASCII only.
"""
from __future__ import annotations

import os
import sys
from types import SimpleNamespace

import pytest

sys.path.insert(0, os.path.dirname(__file__))      # tests/engine -> import du helper sibling

from counterproof import assert_sample_confrontable  # noqa: E402

CARRIER = "genesMagus"                             # HERO du pool, faction Genestealers
MAX_STEPS = 140
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

CASES = [("MC1_67", "777", _GENES),
         ("C4_09", "31337", _GENES)]


def _wants(ctx, lc) -> bool:
    """Le regime de CE fichier : au moins une candidate a occupant steppable AMI (sans elle les deux
    feuilles ne tirent nulle part) ET au moins une SANS occupant (sans elle, une pose TROP LARGE
    rendrait exactement la meme chose -- c'est la contre-epreuve de `case-241` §4.4)."""
    from probe_241_decoy_tile_leaves import _steppable_tiles
    occ = _steppable_tiles(lc)
    tiles = ctx.action_tiles or []
    return (any(t in occ and not occ[t][1] for t in tiles) and any(t not in occ for t in tiles))


@pytest.fixture(scope="module", params=CASES, ids=lambda c: "%s-%s" % (c[0], c[1]))
def decoy_case(request, rpc, build_runner):
    """Etat de decision d'une activation de Xybia ou les DEUX natures de tuile sont presentes.

    On ne SUBIT pas la geometrie : tant qu'aucune candidate ne porte de decoy, on DEPLACE le carrier
    vers eux et on termine le tour des allies (`walk_driven`)."""
    from probe_212_spiritual_leader_tile_term import walk_driven, carrier_id_of
    from probe_241_decoy_tile_leaves import goals_241
    board, seed, extra = request.param

    def r(m, b, t=90):
        return rpc(m, b, t)

    rid = build_runner(seed, extra=list(extra), board=board)["rid"]
    cid = carrier_id_of(r, rid, CARRIER)
    assert cid is not None, "%s absent du runner (roster/pool a re-etalonner)" % CARRIER
    for st in walk_driven(r, rid, cid, _wants, goals_241, MAX_STEPS):
        me = next((u for u in (st["dv"].get("units") or []) if u.get("id") == st["uid"]), None)
        return SimpleNamespace(rid=rid, step=st["step"], uid=st["uid"],
                               visual_id=(me or {}).get("visualId"), ctx=st["ctx"],
                               action_tiles=list(st["ctx"].action_tiles or []),
                               decoys=st["decoys"], driven=st["driven"])
    assert_sample_confrontable(
        False,
        mutation="montage %s/%s : trajectoire native marchee en PILOTANT les positions de %s vers "
                 "les decoys poses par sa face COMBAT (walk_driven / goals_241)" % (board, seed,
                                                                                    CARRIER),
        doit_casser="une activation du carrier ou ses candidates portent A LA FOIS un occupant "
                    "steppable ami et aucun occupant -- les deux natures que ces gardes opposent",
        observe="aucune en %d pas : trajectoire epuisee, ou aucun decoy n'est jamais arrive sur une "
                "candidate" % MAX_STEPS,
        remede="rejouer `probe_241_decoy_tile_leaves.py --carrier genesMagus` (il imprime chaque "
               "DRIVE et les candidates a occupant steppable) ; si aucun decoy n'est POSE, c'est la "
               "face COMBAT de SpiritualLeader qu'il faut relire, pas ce montage")


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
    """Le montage n'a de sens que si le pas active bien Xybia ; sinon rien n'a ete confronte.

    ROUGE DE SCENARIO (#462-r6) : ce n'est ni un verdict sur le port ni sur le harnais."""
    assert_sample_confrontable(
        decoy_case.visual_id == CARRIER,
        mutation="marche pilotee jusqu'a une activation du carrier %s" % CARRIER,
        doit_casser="le pas retenu active bien %s (les gardes suivantes lisent SA faction et SON "
                    "voisinage)" % CARRIER,
        observe="pas %d : l'unite activee est %s" % (decoy_case.step, decoy_case.visual_id),
        remede="`walk_driven` ne yield que sur `uid == carrier_id` : si ce message apparait, c'est "
               "que `carrier_id_of` a resolu un autre `visualId` -- re-etalonner le roster")


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
    suivantes passeraient a vide (l'une ne verrait jamais la pose, l'autre jamais son absence).

    Premiere assertion = ECHANTILLON (rouge de SCENARIO, #462-r6) ; seconde = FOND (la pose ne doit
    retenir QUE le decoy)."""
    metas, _ = _metas(decoy_case)
    with_occ = [t for t, m in metas.items() if m.get("steppable")]
    without = [t for t, m in metas.items() if not m.get("steppable")]
    assert_sample_confrontable(
        bool(with_occ) and bool(without),
        mutation="drive de %s vers les decoys de sa face COMBAT (%d drive(s), %d decoy(s) allie(s) "
                 "vus au pas retenu)" % (CARRIER, decoy_case.driven, len(decoy_case.decoys)),
        doit_casser="au moins une candidate a occupant steppable ET au moins une sans -- sans les "
                    "deux, ni la pose ni son absence ne sont exercees",
        observe="pas %d (%s) : %d candidate(s) a occupant steppable, %d sans"
                % (decoy_case.step, decoy_case.visual_id, len(with_occ), len(without)),
        remede="augmenter MAX_STEPS, ou rejouer `probe_241_decoy_tile_leaves.py --carrier %s`, qui "
               "imprime chaque DRIVE et les candidates a occupant steppable" % CARRIER)
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
    # ECHANTILLON (rouge de SCENARIO, #462-r6) : sans porteur de 1304 la feuille 64 vaut 0 par
    # CONSTRUCTION -- l'assertion de fond qui suit passerait alors sans rien confronter.
    assert_sample_confrontable(
        n >= 1,
        mutation="roster avec genesPrimus (LE porteur de %d du montage) vivant" % ATTRACT_ABILITY,
        doit_casser="au moins un ami porteur de %d, sinon `n x GSC` vaut 0 quoi que fasse le port"
                    % ATTRACT_ABILITY,
        observe="pas %d : n(amis porteurs de %d, self inclus) = %d"
                % (decoy_case.step, ATTRACT_ABILITY, n),
        remede="genesPrimus est-il encore vivant a ce pas ? relever `--hp-player`, ou arreter le "
               "drive plus tot (MAX_STEPS)")
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
    que la feuille 19 fait ensuite sur l'occupant.

    ⚠ #477-r37 : le foyer a DEMENAGE dans `engine.battle_query.get_steppable_unit` (un second
    consommateur est apparu, `HaywireMineNonOwnerPlaybook`, qui ne peut pas importer `tile`) et rend
    desormais une cle de PLUS -- `vis`, l'id d'unite de l'occupant, l'argument d'
    `IdunBattle.Entities.UnitExtensions$$HasUnitId`. L'ajout est ADDITIF : les quatre lectures de la
    feuille 19 sont inchangees, et ce test compare par EGALITE STRICTE, donc il a rougi -- c'est
    exactement ce qu'on lui demande. Les attendus sont etendus, pas relaches : `vis` est ASSERTIONNE
    sur chaque branche, y compris celle du mover-sur-son-origine, ou il vient d'une autre cle du
    `ctx` (`self_vis`) et ou une regression le rendrait `None` en silence."""
    from engine.utilities.tile import _steppable_occupant
    T = (2, 3)
    # occupant NON steppable -> pas d'occupant steppable (le natif rend false), meme s'il est Decoy
    assert _steppable_occupant(T, _lc(friend_units=[_u(T, ("Decoy",))])) is None
    # tuile vide
    assert _steppable_occupant(T, _lc(friend_units=[_u((9, 9), ("Steppable",))])) is None
    # ami steppable non decoy / ami steppable decoy
    assert _steppable_occupant(T, _lc(friend_units=[_u(T, ("Steppable",))])) == {
        "is_friend": True, "is_enemy": False, "is_decoy": False, "triggered": (), "vis": "x"}
    assert _steppable_occupant(T, _lc(friend_units=[_u(T, ("Steppable", "Decoy"), (77,))])) == {
        "is_friend": True, "is_enemy": False, "is_decoy": True, "triggered": (77,), "vis": "x"}
    # ennemi steppable decoy
    assert _steppable_occupant(T, _lc(enemy_units=[_u(T, ("Steppable", "Decoy"))])) == {
        "is_friend": False, "is_enemy": True, "is_decoy": True, "triggered": (), "vis": "x"}
    # le MOVER sur son ORIGINE : self-exclu de `friend_units`, donc branche dediee. `unit_traits`
    # est une liste d'IDS (27 = Steppable, 1053 = Decoy), pas de noms.
    assert _steppable_occupant(T, _lc(self_pos=T, unit_traits=(16,))) is None      # hero -> rien
    assert _steppable_occupant(T, _lc(self_pos=T, unit_traits=(27, 1053),
                                      unit_triggered_abilities=(1304,),
                                      self_vis="moi")) == {
        "is_friend": True, "is_enemy": False, "is_decoy": True, "triggered": (1304,), "vis": "moi"}


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
