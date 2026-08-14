"""#1038 -- `MastersOfManoeuvre` (mythique de la MoW `darkaStormSpeeder`, `TriggeredAbilityType`
0x5e4 = 1508 / `EffectType` 0x5e6 = 1510), CONFRONTE LIVE.

CE QUE CE FICHIER MESURE, ET POURQUOI LE MONTAGE EST CE QU'IL EST
------------------------------------------------------------------
La face portee est celle de l'EFFET :
`IdunBattle.Entities.Effects.Loki.MastersOfManoeuvreEffect$$CreateEffectDamageMalusForDefense` =
`EffectBonus.ForPercentDecrease( get_OwnerIsTarget & IsRangedAttack(),
ConfigVar(AbilityVariableType.dmgReductionPct = 0x46) )`.

La POSE (`...MastersOfManoeuvreAbility$$CreateTrigger`) n'est PAS portee -- son gate COMMUN porte
`HasRarity(Actor@<DSLSelectors+0x40>, idun.meta.Rarity.Mythic = 5)`, et aucun canal du port ne
publie `GetBaseUnitComponent(e)+0x74` (meme verrou que `#1025-r1`). C'est donc le NATIF qui pose,
et le port qui CONSOMME l'instance captee : ce fichier verifie exactement cette jointure.

TROIS BRAS, et ils sont SEPARANTS (mesure, pas hypothese) :

    bras            tuiles traversees   niveau mythique   aiPredict (min/max)   rapport
    B contre-bras   1  (< tilesTraversed = 2)      1      2890 / 4334           1.0000
    A               3                             1      2600 / 3900           0.8997
    C               3                             4      2312 / 3468           0.8000

Les trois finissent sur la MEME tuile (3,3), avec le MEME tireur en (3,6) : seuls changent le
NOMBRE de tuiles traversees et le NIVEAU. Le contre-bras B isole donc le gate
`AmountIsEqualOrGreater(TilesMovedThisTurn(Actor), Get(GetNumberConstant(tilesTraversed)))` -- pas
la presence de la MoW, qui est montee dans les TROIS (l'injection catalogue de `darkaStormSpeeder`,
hors seed, passe par `--equip-mythic`).

L'ECART A/C EST CE QUI REND LE NIVEAU OBSERVABLE : le port lisait le couple des PASSIFS (50 -> le
palier 4 apres clamp, x mult 160 = **32 %**) au lieu du couple TERTIAIRE (1 -> **10 %**). Un
montage au seul niveau 4 aurait rendu VERT ce port FAUX.

`--hp-player 200000` sort du regime SATURE ou `aiPredict` clampe ses bornes aux PV restants (et met
l'armure a 0, donc le rapport se lit directement) ; `--crit-target 0,0` / `--block-player 0,0`
eteignent l'aleatoire de la preview ; `--no-ai` fige la geometrie entre les mesures.
ASCII only.
"""
from __future__ import annotations

import pytest

from engine.entities.effect_type import EffectType
from engine.entities.effects.loki.masters_of_manoeuvre import (ABILITY_ID,
                                                               MastersOfManoeuvreEffect,
                                                               VAR_DMG_REDUCTION_PCT)
from engine.entities.effects.magnitude import ability_var
from engine.entities.pathfinding.board import Board
from engine.runner.snapshot import load_state

DECLENCHEUR = {
    "chemins": (
        "scripts/python/engine/runner/snapshot.py",
        "scripts/python/engine/entities/effects/factory.py",
        "scripts/python/engine/entities/effects/loki/masters_of_manoeuvre.py",
        "scripts/python/engine/entities/effects/effects_state.py",
        "scripts/python/rl_duel.py",
        "scripts/python/catalog_inject.py",
    ),
    "build": True,
    "toujours": False,
    "raison": ("Confronte le port au NATIF sur un runner monte par `rl_duel build "
               "--equip-mythic` : il depend du montage (rl_duel/catalog_inject), du seed de "
               "l'`AbilityState` (snapshot/effects_state), du registre (factory) et de la classe "
               "d'effet. `build: True` parce que les magnitudes viennent du gameconfig du build "
               "courant et que les bornes natives citees en en-tete sont per-build."),
}

MOW = "darkaStormSpeeder"
#: L'unite qui PORTERA l'effet : elle doit etre MYTHIQUE (`HasRarity(Actor, 5)`) et amie de la MoW.
#: `worldKharn` est `Rarity == 5` au seed BC, et son `move 3` lui permet de franchir le seuil.
PORTEUR = "worldKharn"
FIGURANT = "admecMarshall"
TIREUR = "necroWarden"          # arme RANGED portee 3 -> tir NON adjacent depuis (3,6) vers (3,3)
BOARD, SEED = "MC1_67", "777"
TUILE_FINALE = (3, 3)


def _montage(depart: str, niveau: int) -> list:
    """LE MONTAGE, NOMME ET REUTILISABLE. `depart` fixe le NOMBRE de tuiles a traverser pour
    rejoindre `TUILE_FINALE` -- c'est la SEULE variable du contre-bras."""
    return ["--p-units", "%s,%s" % (PORTEUR, FIGURANT), "--a-units", TIREUR,
            "--p-mow", MOW, "--rank", "17", "--board", BOARD,
            "--place", "%s:%s" % (PORTEUR, depart), "--place", "%s:0,0" % FIGURANT,
            "--a-place", "%s:3,6" % TIREUR,
            "--crit-target", "0,0", "--block-player", "0,0", "--hp-player", "200000", "--no-ai",
            "--equip-mythic", "%s:%s:%d" % (MOW, ABILITY_ID, niveau)]


def _ok(r):
    return isinstance(r, dict) and r.get("ok")


def _ids(dv):
    return {u.get("visualId"): int(u["id"]) for u in (dv.get("units") or [])}


def _bras(rpc, build_runner, depart: str, niveau: int) -> dict:
    rid = build_runner(SEED, extra=_montage(depart, niveau))["rid"]
    dv0 = rpc("decisionView", {"runnerId": rid, "allAbilities": True}, 120)
    if not _ok(dv0):
        pytest.fail("capture live KO au build (depart=%s niveau=%d)" % (depart, niveau),
                    pytrace=False)
    ids = _ids(dv0)
    porteur, tireur = ids.get(PORTEUR), ids.get(TIREUR)
    if porteur is None or tireur is None:
        pytest.fail("montage incomplet : %s / %s absents de la vue" % (PORTEUR, TIREUR),
                    pytrace=False)
    res = rpc("applyAction", {"runnerId": rid, "action": {
        "kind": "move", "unitId": porteur,
        "to": {"col": TUILE_FINALE[0], "row": TUILE_FINALE[1]}}}, 60)
    if not _ok(res):
        pytest.fail("deplacement refuse (depart=%s) : %r" % (depart, res), pytrace=False)
    dv = rpc("decisionView", {"runnerId": rid, "allAbilities": True}, 120)
    ob = rpc("observeBattle", {"runnerId": rid}, 60)
    snap = rpc("combatSnapshot", {"runnerId": rid}, 60)
    bg = rpc("boardGraph", {"runnerId": rid}, 60)
    if not (_ok(dv) and _ok(ob) and _ok(snap) and isinstance(bg, dict) and bg.get("tiles")):
        pytest.fail("capture live KO apres deplacement", pytrace=False)
    pred = rpc("aiPredict", {"runnerId": rid, "unitId": tireur, "targetId": porteur,
                             "fresh": True}, 90)
    return {"rid": rid, "porteur": porteur, "tireur": tireur, "dv": dv, "ob": ob, "snap": snap,
            "board": Board(bg["tiles"], adjacency="evenq"), "pred": pred, "niveau": niveau}


@pytest.fixture(scope="module")
def bras(live_session, rpc, build_runner):
    """Les TROIS bras, montes une fois. Chaque `build_runner` est libere au teardown du module."""
    return {"B": _bras(rpc, build_runner, "3,2", 1),      # 1 tuile  -> sous le seuil
            "A": _bras(rpc, build_runner, "3,0", 1),      # 3 tuiles -> au-dessus, niveau 1
            "C": _bras(rpc, build_runner, "3,0", 4)}      # 3 tuiles -> au-dessus, niveau 4


def _dmg(b) -> tuple:
    p = ((b.get("pred") or {}).get("pred") or {})
    lo, hi = p.get("healthDmgMin"), p.get("healthDmgMax")
    if not lo or not hi:
        pytest.fail("aiPredict muet (pred=%r)" % (b.get("pred"),), pytrace=False)
    return int(lo), int(hi)


def _instance(b):
    st = load_state(b["dv"], b["ob"], b["snap"], board=b["board"])
    return st, [e for e in (st.effects.by_unit.get(b["porteur"]) or [])
                if int(getattr(e, "effect_type", -1) or -1) == int(EffectType.MastersOfManoeuvre)
                and not e.consumed]


# ══ 1. LA POSE -- vecteur A, et son contre-bras sous le seuil ═══════════════════════════════════

def test_le_natif_pose_leffet_quand_le_seuil_de_tuiles_est_franchi(bras):
    """`On(EventTriggerType.UnitAfterMove) & AreFriends & HasRarity(Actor, Mythic) &
    !HasEffect(...) & AmountIsEqualOrGreater(TilesMovedThisTurn(Actor), tilesTraversed)`.
    C'est le bras qui MORD : sans lui, le contre-bras ci-dessous ne prouverait rien."""
    _st, insts = _instance(bras["A"])
    assert insts, "l'effet 1510 n'est pas pose apres 3 tuiles traversees"
    assert isinstance(insts[0], MastersOfManoeuvreEffect), (
        "1510 retombe sur %s : l'entree EFFECT_CLASSES manque, et la degradation est SILENCIEUSE"
        % type(insts[0]).__name__)


def test_contre_bras_sous_le_seuil_aucun_effet(bras):
    """1 tuile traversee < `tilesTraversed` = 2 : le natif ne pose RIEN. Meme tuile finale, meme
    MoW montee, meme tireur -- seul le nombre de tuiles change."""
    _st, insts = _instance(bras["B"])
    assert not insts, ("l'effet 1510 est pose alors que le seuil `tilesTraversed` n'est pas "
                       "franchi -- le contre-bras ne separe plus rien")


# ══ 2. L'ABILITY STATE BAKEE -- le niveau TERTIAIRE, pas celui des passifs ══════════════════════

def test_linstance_porte_le_niveau_tertiaire_et_non_celui_des_passifs(bras):
    """`AddEffectBehaviour$$DefaultEffectBuilder` BAKE l'`AbilityStateReference` de l'ability QUI
    POSE. Pour une TERTIAIRE : `level 1..4 / mult 100`. Le port lisait le couple des PASSIFS
    (50 / 160) et la classe rendait `None` faute d'`AbilityState` : effet MATERIALISE et INERTE."""
    for cle, attendu in (("A", 1), ("C", 4)):
        _st, insts = _instance(bras[cle])
        assert insts, "bras %s : aucune instance a mesurer" % cle
        e = insts[0]
        assert e.ability_level == attendu, (
            "bras %s : ability_level=%r (attendu %d, le TertiaryAbilityLevel de la MoW)"
            % (cle, e.ability_level, attendu))
        assert e.ability_variables_multiplier == 100, (
            "bras %s : multiplicateur %r au lieu du 100 de la voie tertiaire"
            % (cle, e.ability_variables_multiplier))
        mows = [int(m["casterId"]) for m in (bras[cle]["dv"].get("mows") or [])
                if m.get("casterId") is not None and m.get("visualId") == MOW]
        assert mows and int(e.source) in mows, (
            "bras %s : SOURCE %r, attendue la MoW %s %r -- le natif pose `source = "
            "Owner@<DSLSelectors+0x30>` et `targets = Actor@<+0x40>`, et c'est PRECISEMENT parce "
            "que les deux different que la passe clee par PORTEUR ne voyait pas l'instance"
            % (cle, e.source, MOW, mows))


# ══ 3. LA MAGNITUDE -- port confronte au NATIF, trois bras ══════════════════════════════════════

def test_le_natif_reduit_du_pourcentage_du_palier_tertiaire(bras):
    """MESURE NATIVE, `aiPredict` (preview DETERMINISTE, sans RNG). Le rapport bras/contre-bras
    doit valoir `1 - dmgReductionPct[niveau]/100`, lu au gameconfig -- jamais une constante ecrite
    a la main ici."""
    ref_lo, ref_hi = _dmg(bras["B"])
    assert ref_lo > 0 and ref_hi > ref_lo, (
        "le contre-bras rend une preview degeneree (%s/%s) : aucun rapport n'y serait lisible"
        % (ref_lo, ref_hi))
    for cle in ("A", "C"):
        pct = int(ability_var(ABILITY_ID, VAR_DMG_REDUCTION_PCT, bras[cle]["niveau"],
                              multiplier_pct=100))
        assert pct, "gameconfig muet sur %s.%s[%d]" % (ABILITY_ID, VAR_DMG_REDUCTION_PCT,
                                                       bras[cle]["niveau"])
        lo, hi = _dmg(bras[cle])
        for mesure, ref, quoi in ((lo, ref_lo, "min"), (hi, ref_hi, "max")):
            attendu = ref * (100 - pct) / 100.0
            assert abs(mesure - attendu) <= 1.0, (
                "bras %s (%s) : natif %d, attendu ~%.1f = %d x (1 - %d/100)"
                % (cle, quoi, mesure, attendu, ref, pct))


def test_les_trois_bras_sont_distincts_le_regime_nest_pas_degenere(bras):
    """ANTI-CONFOND. Un accord en regime degenere ne prouve rien : les trois previews doivent
    DIFFERER, sinon le fichier entier passerait vert pour un port qui lit le mauvais niveau."""
    vus = {cle: _dmg(bras[cle]) for cle in ("B", "A", "C")}
    assert len(set(vus.values())) == 3, "previews non separantes : %r" % (vus,)


def test_le_port_rend_le_meme_pourcentage_que_le_natif(bras):
    """La jointure : ce que le PORT verse dans le %-list defenseur, sur l'instance CAPTEE."""
    for cle in ("A", "C"):
        _st, insts = _instance(bras[cle])
        assert insts, "bras %s : aucune instance a mesurer" % cle
        eb = insts[0].create_effect_damage_malus_for_defense(is_melee=False)
        pct = int(ability_var(ABILITY_ID, VAR_DMG_REDUCTION_PCT, bras[cle]["niveau"],
                              multiplier_pct=100))
        assert eb is not None and eb.kind == "PercentDecrease" and eb.value == pct, (
            "bras %s : le port rend %r au lieu d'un PercentDecrease(%d)" % (cle, eb, pct))
        assert eb.owner_is_caster is False


def test_le_port_est_muet_en_melee(bras):
    """`IsRangedAttack()` est un conjoint du trigger de l'`EffectBonus` -- pas du trigger de POSE.
    Le contraste avec `ContemptuousDisregard_DamageReduction` (aucun gate de nature) est ENTIER."""
    _st, insts = _instance(bras["A"])
    assert insts and insts[0].create_effect_damage_malus_for_defense(is_melee=True) is None
    assert insts[0].create_effect_damage_malus_for_defense(is_melee=None) is None
