"""case-366-r1 -- GARDES des deux `EffectType` de percage de `VisionsOfHeresy`
(`1345 ExtraPierceMelee` / `1346 ExtraPierceRanged`, `bloodDeathCompany` <<Lucien>>).

i2 : << If Lucien is at or below {healthPct}% Health, all of his attacks have +{extraPierceRatio}%
pierce ratio. >>

ARTEFACTS NATIFS (build rnca9r7q6c) :
  - `IdunBattleLogic.Entities.Abilities.Triggered.Loki.VisionsOfHeresy_ExtraPierceAbility$$CreateBehaviour`
      `AddStaticStatModifierEffect(Owner, 0x541, statType 0x15 = 21 EXTRA_PIERCE_MELEE,
       ConfigVar(0x3f = extraPierceRatio), turns = NULL)`
    & `AddStaticStatModifierEffect(Owner, 0x542, statType 0x16 = 22 EXTRA_PIERCE_RANGED, <le MEME>,
       turns = NULL)`
    -> UNE seule classe d'effet native pour les DEUX ids (meme slot `Il2CppClass*`), le
       discriminant melee/ranged est le `statType` de la POSE.
  - `Idun.Source.IdunBattle.Logic.Entities.Effects.Loki.VisionsOfHeresy_ExtraPierceEffect$$CreateActiveCondition`
      `HealthPctIsBelowOrEqual(Owner, ConfigConst(0x4f = healthPct))` ->
      `IdunBattle.Entities.Conditions.StatPercentageIsBelowOrEqualAbilityTrigger$$ShouldTrigger` =
      `GetStat(5, CURRENT) / GetStat(5, MAXIMUM) <= pct/100` (Fix64, INCLUSIF).
  - CANAL consommateur : `IdunBattle.Core.Services.DamagePrediction$$GetAttackPiercingDamageRatio`
      = `Min(100, Max(base>0, GetStat(isMelee ? 0x15 : 0x16) + GetStat(0x1a) + mods + base))`.

CE QUE CES GARDES TIENNENT, et qui n'est tenu nulle part ailleurs :
  * E1 -- la POSE a l'init : a pleins PV les effets sont ABSENTS du canal `decisionView` ACTIF et
    PRESENTS sous `includeInactive` avec `active: false`. Sans le seed
    `ABILITY_INIT_OWNER_EFFECTS["VisionsOfHeresy"]`, le port n'aurait AUCUN effet a activer quand
    Lucien descend en cours de bataille -- silencieusement.
  * E2 -- le CANAL : la contribution passe par les STATS 21/22, que `ctx.extra_pierce_{melee,ranged}`
    LIT (proprietes adossees a `get_stat`). Le test DISCRIMINANT part de la capture PLEINS PV --
    ou le canal live ne livre RIEN -- descend les PV OFFLINE, et exige la valeur NATIVE mesuree
    au regime bas. Un port qui garderait des champs plats seedes a la capture rend 0 ici.
  * E3 -- le DEGAT, dans le regime PERCAGE-DOMINANT (`--armor-target 6000`), avec sa
    CONTRE-EPREUVE : le meme coup rejoue sans les deux effets donne des per-coup DIFFERENTS. Sans
    elle, << port == live >> ne prouverait pas que le percage y change quoi que ce soit.

Montage complet (build, drive des deux camps, pilonnage sous le seuil, captures, rejeux) :
`scripts/python/probe_366_visions_of_heresy.py`. ASCII only (cp1252).
"""
from __future__ import annotations

import pytest

import probe_366_visions_of_heresy as VOH

# Deux couples (board, seed) par axe -- discipline de generalisation (runner.md S3) : un resultat
# obtenu sur UN seul board peut etre un artefact de ce board (geometrie de spawn, distance).
COUPLES = (("MC1_67", "31337"), ("C4_09", "4242"))


@pytest.fixture(scope="module")
def voh_case(live_session, rpc):
    """Fabrique : `voh_case("melee", board, seed)` -> le dict de mesure du probe.

    [!] Un montage qui ne s'installe pas ECHOUE, il ne skippe pas (#268) : un `pytest.skip` sur un
    regime non atteint est un VERT qui ment -- aucune mesure n'a eu lieu."""
    cache: dict = {}

    def _case(axis: str, board: str = "MC1_67", seed: str = "31337") -> dict:
        k = (axis, board, seed)
        if k not in cache:
            r = VOH.run(rpc, axis=axis, seed=seed, board_id=board)
            if r.get("error"):
                pytest.fail("montage VisionsOfHeresy NON INSTALLE (%s/%s/%s): %s"
                            % (axis, board, seed, r["error"]))
            cache[k] = r
        return cache[k]
    return _case


def _key(axis):
    return "melee" if axis == "melee" else "ranged"


def _assert_axis(axis, r):
    k = _key(axis)
    ratio = r["extra_pierce_ratio_config"]
    assert ratio, ("extraPierceRatio irresoluble au niveau %s -- la config d'ability a bouge ?"
                   % r["passive_level"])

    # --- E1 : POSE a l'init + ActiveCondition (canal ACTIF-ONLY vs includeInactive) -----------
    assert r["high_effect_in_active_channel"] is False, (
        "l'effet %s est PUBLIE a %.1f%% PV alors que le seuil est %s%% -> la `CreateActiveCondition` "
        "native ne filtre pas ce qu'on croit" % (r["effect_type"], r["high_hp_pct"],
                                                 r["threshold_pct"]))
    assert r["high_effect_in_inactive_channel"] is True, (
        "l'effet %s est ABSENT MEME sous `includeInactive` a pleins PV : il n'est donc PAS pose a "
        "l'init de l'ability, et l'entree `ABILITY_INIT_OWNER_EFFECTS['VisionsOfHeresy']` du port "
        "n'a plus de fondement natif" % r["effect_type"])
    assert r["high_effect_active_flag"] is False, (
        "`EffectComponent.IsActive` vaut %s a pleins PV" % r["high_effect_active_flag"])
    posed = {n for n, _a, _c in r["high_offline"]["effects"]}
    assert posed == {"VisionsOfHeresy_ExtraPierceMelee", "VisionsOfHeresy_ExtraPierceRanged"}, (
        "le port ne pose pas les DEUX owner-effects a l'init (pose: %s)" % sorted(posed))
    assert all(not a for _n, a, _c in r["high_offline"]["effects"]), (
        "le port rend un effet ACTIF a %.1f%% PV (seuil %s%%)" % (r["high_hp_pct"],
                                                                  r["threshold_pct"]))

    # --- E2 : le CANAL STAT, confronte au natif ------------------------------------------------
    assert r["high_stat_live"] == 0, (
        "natif : %s = %s a pleins PV, attendu 0" % (r["stat_key"], r["high_stat_live"]))
    assert r["low_stat_live"] == ratio, (
        "natif : %s = %s a %.1f%% PV, attendu extraPierceRatio[L%s] = %s (magnitude re-derivee de "
        "gameconfig, NON scalee par la rarete -- `extraPierceRatio` hors "
        "`variablesAffectedByRarityBonus`)"
        % (r["stat_key"], r["low_stat_live"], r["low_hp_pct"], r["passive_level"], ratio))
    assert r["high_offline"][k] == 0, (
        "port : %s = %s a pleins PV (le gate PV fuit)" % (k, r["high_offline"][k]))
    assert r["low_offline"][k] == r["low_stat_live"], (
        "port %s = %s != natif %s sous le seuil" % (k, r["low_offline"][k], r["low_stat_live"]))

    # LE test DISCRIMINANT : la capture PLEINS PV ne porte AUCUN de ces effets cote live ; le port
    # doit quand meme produire le percage natif une fois les PV descendus OFFLINE.
    assert r["high_capture_dropped_offline"][k] == r["low_stat_live"], (
        "DISCRIMINANT : depuis une capture a pleins PV (ou `decisionView.effects` ne livre RIEN), "
        "PV descendus a %s offline -> le port rend %s = %s, le natif mesure %s. C'est le canal qui "
        "est mort : soit les owner-effects ne sont pas seedes, soit `refresh_stat_modifier_effects` "
        "ne pose pas la stat 21/22, soit `ctx.extra_pierce_%s` ne LIT pas `get_stat` (champ plat "
        "fige a la capture)."
        % (r["low_hp"], k, r["high_capture_dropped_offline"][k], r["low_stat_live"], k))

    # BASCULE INVERSE (mirror `DeactivateEffect` -> `RevertModification`).
    assert r["low_capture_healed_offline"][k] == 0, (
        "port : le << soin >> au-dessus du seuil ne RETIRE pas la contribution (%s = %s) -- mirror "
        "`RefreshEffectsOperation.DeactivateEffect`" % (k, r["low_capture_healed_offline"][k]))

    # --- E3 : le DEGAT, regime percage-dominant + contre-epreuve de discriminance --------------
    assert not r["high_dirty"] and not r["low_dirty"], (
        "coup non propre (crit/block/evade) -- l'etage percage n'est pas isole")
    assert r["high_live_weapon"] == r["high_port_hits"], (
        "regime HAUT : port %s != live %s (queue live non portee : %s)"
        % (r["high_port_hits"], r["high_live_weapon"], r["high_live_tail"]))
    assert r["low_live_weapon"] == r["low_port_hits"], (
        "regime BAS : port %s != live %s -- le +%s de percage n'entre pas dans le degat du port "
        "(queue live non portee : %s)"
        % (r["low_port_hits"], r["low_live_weapon"], ratio, r["low_live_tail"]))
    assert r["low_port_hits_without_effect"] != r["low_port_hits"], (
        "regime NON DISCRIMINANT : retirer les deux effets ne change RIEN au degat (%s) -- l'armure "
        "de la cible (%s) ne fait pas gagner la branche PERCAGE du plancher, la mesure ne prouve "
        "rien. Monter `--armor-target`." % (r["low_port_hits"], r["armor"]))
    assert (r["low_port_pierce_ratio"]["pierce"]
            == r["high_port_pierce_ratio"]["pierce"] + ratio), (
        "ratio de percage du port : HAUT=%s BAS=%s, ecart attendu +%s"
        % (r["high_port_pierce_ratio"]["pierce"], r["low_port_pierce_ratio"]["pierce"], ratio))
    assert r["low_port_pierce_ratio"]["is_ranged"] is (axis == "ranged"), (
        "l'arme resolue par le port n'est pas celle de l'axe %s (is_ranged=%s) -- la distance du "
        "montage ne selectionne pas l'arme voulue, donc c'est l'AUTRE stat qui serait lue"
        % (axis, r["low_port_pierce_ratio"]["is_ranged"]))


@pytest.mark.parametrize("board,seed", COUPLES)
def test_visions_of_heresy_extra_pierce_melee_live(voh_case, board, seed):
    """`1345 VisionsOfHeresy_ExtraPierceMelee` -- statType 21, arme MELEE (distance hex 1)."""
    r = voh_case("melee", board, seed)
    print("\n[366-r1/melee %s/%s] %s" % (board, seed, {
        "stat_live": (r["high_stat_live"], r["low_stat_live"]),
        "port": (r["high_offline"]["melee"], r["low_offline"]["melee"]),
        "discriminant": r["high_capture_dropped_offline"]["melee"],
        "pierce": (r["high_port_pierce_ratio"]["pierce"], r["low_port_pierce_ratio"]["pierce"]),
        "hits_live": (r["high_live_weapon"], r["low_live_weapon"]),
        "hits_port": (r["high_port_hits"], r["low_port_hits"]),
        "sans_effet": r["low_port_hits_without_effect"]}))
    _assert_axis("melee", r)


@pytest.mark.parametrize("board,seed", COUPLES)
def test_visions_of_heresy_extra_pierce_ranged_live(voh_case, board, seed):
    """`1346 VisionsOfHeresy_ExtraPierceRanged` -- statType 22, arme RANGED (distance hex 2).

    Axe CONFRONTE SEPAREMENT du melee : un montage melee ne dit rien du ranged (le natif lit
    `GetStat(0x15)` ou `GetStat(0x16)` selon `isMelee`, jamais les deux)."""
    r = voh_case("ranged", board, seed)
    print("\n[366-r1/ranged %s/%s] %s" % (board, seed, {
        "stat_live": (r["high_stat_live"], r["low_stat_live"]),
        "port": (r["high_offline"]["ranged"], r["low_offline"]["ranged"]),
        "discriminant": r["high_capture_dropped_offline"]["ranged"],
        "pierce": (r["high_port_pierce_ratio"]["pierce"], r["low_port_pierce_ratio"]["pierce"]),
        "hits_live": (r["high_live_weapon"], r["low_live_weapon"]),
        "hits_port": (r["high_port_hits"], r["low_port_hits"]),
        "sans_effet": r["low_port_hits_without_effect"]}))
    _assert_axis("ranged", r)
