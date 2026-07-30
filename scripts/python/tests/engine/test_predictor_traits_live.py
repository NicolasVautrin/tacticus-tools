"""CLIQUET #267 -- la face PREDICTION consomme `combatSnapshot.units[].traits`.

PENDANT EXACT de `tests/engine/runner/test_load_state_traits_live.py` (#264), sur l'AUTRE seam.
`engine/playbook/scene.py` a son propre chemin live (`build_predictor` / `refresh_shields` /
`Scene.from_predictor_sctx`) : il RECONSTRUISAIT les traits depuis `gameconfig.unit(vis).traits`
(via `UnitContext.from_snapshot`) alors que la face combat lisait deja la mesure. Une face qui lit
et l'autre qui reconstruit, c'est le fork « ce que le moteur fait != ce que la prediction annonce ».

CE QUE LIT LE NATIF. La prediction n'a PAS de substrat de traits separe :
`IdunBattle.Core.Services.DamagePrediction$$ApplyTraitDamageLimitsToDamage` appelle deux fois
`IdunBattle.Core.Services.DamagePrediction$$ApplyResilientTraitDamageLimit` (une par borne), dont le
corps teste `IdunBattle.Entities.UnitExtensions$$HasTrait(defender, 0x3f1)` -- LA MEME fonction que
la face combat, qui delegue a `IdunBattle.Entities.Components.BaseUnitComponent$$HasTrait`
(`+0x40` permanents | `+0x48` temporaires, moins le veto `+0x50`). Le canal
`combatSnapshot.units[].traits` (#233, `0231573`) est l'invocation de cette fonction par valeur
d'enum : il rend l'ensemble EFFECTIF.

CRITERE GARDE ICI : apres `build_predictor`, l'ensemble de traits que rend la face PREDICTION est
EGAL a celui que publie le capteur, pour CHAQUE ligne -- plus la CONSEQUENCE CHIFFREE sur l'etage
limites, plus la propagation PAR PAS (`refresh_shields`) d'un trait accorde en bataille.

Les deux regimes discriminants (mesures le 2026-07-30) :
  * `necroOverlord` porte `Resilient` au GAMECONFIG et PAS en bataille -> la reconstruction en
    ajoutait un EN TROP, donc `_target_damage_limits` rendait `target_has_resilient=True` et la
    prediction annoncait un degat CAPE a `HP-1` la ou le natif tue (degradation PERMISSIVE, mesuree
    live par `probe_267_predictor_traits.py` montage C : oracle `(6267,6267) killSure=True`,
    port reconstruit `(6266,6267) killSure=False`) ;
  * le dreadnought invoque par `DutyEternalAbility` (1158) prend `Stationary` a l'apparition ->
    la reconstruction le RATAIT (degradation RESTRICTIVE), et le seed COLD du build ne peut pas le
    connaitre : il faut la re-capture par pas.

ASCII only (console cp1252).
"""
from __future__ import annotations

import pytest

from engine.entities.traits.unit_trait import (UnitTrait, entity_trait_names,      # noqa: E402
                                               trait_names_from_ids, unit_trait_names)
from engine.playbook import scene as SC                                            # noqa: E402
from engine.playbook.scene import Scene                                            # noqa: E402

DREADNOUGHT = "ultraDreadnought"
SUMMON = "ultraSmnDreadnought"
DUTY_ETERNAL = 1158
OVERLORD = "necroOverlord"


def _hexes_cibles(at) -> list:
    """Hexes legaux d'un retour `abilityTargets` : `units[].abilities[].{fromHere,targets}[]`."""
    out = []
    for u in ((at or {}).get("units") or []):
        for ab in (u.get("abilities") or []):
            for cle in ("fromHere", "targets"):
                for t in (ab.get(cle) or []):
                    tile = t.get("tile") if isinstance(t, dict) else None
                    if isinstance(tile, dict) and tile.get("col") is not None:
                        out.append((int(tile["col"]), int(tile["row"])))
    return out


def _scene(rpc, rid, snap_force=None, dv=None):
    """Monte la Scene de la face PREDICTION comme le spine de decision (`engine.ai.context`) :
    `build_predictor` + `step_context` + `from_predictor_sctx`, `hpmax_by_id` seede depuis
    `observeBattle` (sans lui `_target_damage_limits.max_health` vaut 0 et le cap Resilient est
    INERTE -- `ApplyResilientTraitDamageLimit` exige `initialHealth > 1`).

    `snap_force` substitue le `combatSnapshot` : passe avec `traits: null` partout, il rejoue
    EXACTEMENT l'etat d'AVANT ce cablage (canal non mesure -> reconstruction du kit)."""
    def _rpc(m, b=None, t=120):
        if m == "combatSnapshot" and snap_force is not None:
            return snap_force
        return rpc(m, b, t)

    predictor = SC.build_predictor(_rpc, rid)
    assert predictor is not None, "build_predictor KO (combatSnapshot indispo)"
    vue = dv if dv is not None else rpc("decisionView", {"runnerId": rid, "maxRank": 1}, 120)
    sctx = SC.step_context(predictor, vue)
    obs = rpc("observeBattle", {"runnerId": rid}, 60) or {}
    hpmax = {u.get("squadId"): (u.get("hpMax") or 0) for u in (obs.get("units") or [])}
    hpmax.update(predictor.get("hpmax_eff_by_id") or {})
    sctx["hpmax_by_id"] = hpmax
    return Scene.from_predictor_sctx(predictor, sctx, None), predictor


def _efface(snap):
    """Le MEME snapshot, canal `traits` a `null` = l'etat d'AVANT (non mesure)."""
    return {**snap, "units": [{**u, "traits": None} for u in (snap.get("units") or [])]}


def _confronte(rpc, rid, snap):
    """Rend `(lignes, ecarts, rates_par_la_reconstruction)` pour la face PREDICTION.

    `ecarts` = divergences de la Scene SEEDEE contre la mesure (doit etre vide) ; `rates` = unites
    que l'etat canal-EFFACE manquait -- la non-vacuite du montage. Deux lecteurs sont confrontes :
    `entity_trait_names` (celui de `_target_damage_limits`) et `Scene.unit_state()["traits"]`
    (le contexte des `CreateActiveCondition`, cf. `BaseEffect.is_active`)."""
    sc, _p = _scene(rpc, rid)
    sc0, _p0 = _scene(rpc, rid, snap_force=_efface(snap))
    lignes, ecarts, rates = 0, [], []
    for su in (snap.get("units") or []):
        eid = su.get("entityId")
        if eid is None or not isinstance(su.get("traits"), list) or sc.ctx(eid) is None:
            continue
        lignes += 1
        mes = trait_names_from_ids(su["traits"])
        vis = sc.vis_by_id.get(eid)
        lus = {
            "entity_trait_names": frozenset(entity_trait_names(sc.ctx(eid), vis)),
            "Scene.unit_state.traits": frozenset(sc.unit_state(eid).get("traits") or ()),
        }
        for nom, val in lus.items():
            if val != mes:
                ecarts.append("u%s %s via %s : MANQUE=%r EN_TROP=%r"
                              % (eid, vis, nom, sorted(mes - val), sorted(val - mes)))
        avant = frozenset(entity_trait_names(sc0.ctx(eid), vis))
        if avant != mes:
            rates.append("u%s %s : reconstruction %r vs mesure %r"
                         % (eid, vis, sorted(avant - mes), sorted(mes - avant)))
    return lignes, ecarts, rates


# ---------------------------------------------------------------------------------------------
# MONTAGE 1 -- roster ALEATOIRE seede : le canal repond et la face prediction l'egale partout.
# ---------------------------------------------------------------------------------------------

@pytest.fixture(scope="module")
def montage_aleatoire(rpc, build_runner):
    rid = build_runner("777", board="MC1_67")["rid"]
    return rid, rpc("combatSnapshot", {"runnerId": rid}, 120)


def test_random_roster_predictor_traits_equal_measured(rpc, montage_aleatoire):
    """Roster aleatoire (seed 777 / MC1_67) : egalite stricte, ligne a ligne."""
    rid, snap = montage_aleatoire
    lignes, ecarts, _ = _confronte(rpc, rid, snap)
    assert lignes >= 4, ("canal `traits` non renseigne (capteur anterieur a 0231573 ?) : %d ligne(s) "
                         "mesuree(s)" % lignes)
    assert not ecarts, "la face PREDICTION DIVERGE de la mesure :\n  " + "\n  ".join(ecarts)


def test_tri_state_null_is_not_empty(rpc, montage_aleatoire):
    """`null` = NON MESURE -> la RECONSTRUCTION de la face prediction reste intacte ; `[]` = mesure
    d'un ensemble VIDE -> elle ecrit vide. Les confondre ferait passer un capteur MORT pour une
    unite sans trait -- et ECRASERAIT le kit gameconfig de toutes les unites."""
    rid, snap = montage_aleatoire
    cible = next((u.get("entityId") for u in (snap.get("units") or [])
                  if isinstance(u.get("traits"), list) and u.get("traits")), None)
    assert cible is not None, "aucune ligne mesuree non vide : montage inexploitable"

    def _lire(mut):
        s = {**snap, "units": [({**u, **mut} if u.get("entityId") == cible else u)
                               for u in (snap.get("units") or [])]}
        sc, _p = _scene(rpc, rid, snap_force=s)
        vis = sc.vis_by_id.get(cible)
        return (frozenset(entity_trait_names(sc.ctx(cible), vis)),
                bool(getattr(sc.ctx(cible), "traits_measured", False)), vis)

    par_null, mesure_null, vis = _lire({"traits": None})
    par_vide, mesure_vide, _ = _lire({"traits": []})
    assert not mesure_null and par_null == frozenset(unit_trait_names(vis)), (
        "canal `null` : la face prediction doit garder sa RECONSTRUCTION (kit gameconfig + "
        "grande-alliance), obtenu %r (attendu %r)"
        % (sorted(par_null), sorted(unit_trait_names(vis))))
    assert mesure_vide and par_vide == frozenset(), (
        "canal `[]` : mesure d'un ensemble VIDE, la face prediction doit rendre vide -- obtenu %r"
        % (sorted(par_vide),))


# ---------------------------------------------------------------------------------------------
# MONTAGE 2 -- roster EXPLICITE + MoW, puis un trait ACCORDE EN BATAILLE. Les DEUX polarites.
# ---------------------------------------------------------------------------------------------

@pytest.fixture(scope="module")
def montage_explicite(rpc, build_runner):
    """`necroOverlord` (trait gameconfig NON porte en bataille) + `ultraDreadnought` (MoW, ligne
    `EntityType.Machine`). Le `predictor` est construit COLD **avant** le cast, puis
    `refresh_shields` le rafraichit APRES -- c'est le regime que la boucle de decision applique
    reellement (build 1x/runner, refresh 1x/pas)."""
    rid = build_runner("31337", board="MC1_67",
                       extra=["--p-units", "ultraTitus,ultraApothecary",
                              "--a-units", "necroOverlord,orksWarboss",
                              "--p-mow", DREADNOUGHT])["rid"]
    predictor = SC.build_predictor(lambda m, b=None, t=120: rpc(m, b, t), rid)
    assert predictor is not None, "build_predictor KO"
    dec = rpc("decisionView", {"runnerId": rid, "allAbilities": True}, 150)
    mow = next((m for m in (dec.get("mows") or []) if m.get("visualId") == DREADNOUGHT), None)
    spawned = None
    if mow is not None:
        hexes = _hexes_cibles(rpc("abilityTargets", {"runnerId": rid,
                                                     "unitId": int(mow["casterId"]),
                                                     "abilityType": DUTY_ETERNAL}, 90))
        for col, row in hexes[:6]:
            rpc("applyAction", {"runnerId": rid, "action": {
                "kind": "ability", "casterId": int(mow["casterId"]),
                "abilityType": DUTY_ETERNAL, "to": {"col": col, "row": row}}}, 90)
            dv = rpc("decisionView", {"runnerId": rid}, 90) or {}
            spawned = next((u.get("id") for u in (dv.get("units") or [])
                            if u.get("visualId") == SUMMON), None)
            if spawned is not None:
                break
    SC.refresh_shields(predictor, lambda m, b=None, t=120: rpc(m, b, t), rid)
    return rid, rpc("combatSnapshot", {"runnerId": rid}, 120), predictor, spawned


def test_explicit_roster_predictor_traits_equal_measured(rpc, montage_explicite):
    """Egalite stricte sur un roster explicite -- lignes `EntityType.Unit` ET `Machine`.

    La MoW compte : `build_predictor` hydrate TOUTES les lignes du snapshot, et une ligne `Machine`
    n'a pas de `visualId` -> la reconstruction par kit y rendait un ensemble VIDE alors que
    `HasTrait` repond bien sur elle (`MachineOfWar`+`Imperial` mesures)."""
    rid, snap, _pred, _sp = montage_explicite
    lignes, ecarts, _ = _confronte(rpc, rid, snap)
    assert lignes >= 4, "canal `traits` non renseigne : %d ligne(s) mesuree(s)" % lignes
    assert any(u.get("entityType") == 6 for u in (snap.get("units") or [])), (
        "aucune ligne EntityType.Machine : le montage ne couvre pas la MoW")
    assert not ecarts, "la face PREDICTION DIVERGE de la mesure :\n  " + "\n  ".join(ecarts)


def test_seed_is_not_vacuous_reconstruction_misses_the_permissive_case(rpc, montage_explicite):
    """GARDE DE NON-VACUITE : le meme etat, canal EFFACE, doit rater `necroOverlord` (`Resilient`
    reconstruit EN TROP). Un montage ou la reconstruction tomberait juste ne prouverait rien."""
    rid, snap, _pred, _sp = montage_explicite
    _lignes, _ecarts, rates = _confronte(rpc, rid, snap)
    joint = " | ".join(rates)
    assert OVERLORD in joint and UnitTrait.Resilient.name in joint, (
        "regime PERMISSIF absent : la reconstruction devait ajouter `Resilient` a necroOverlord "
        "-- %r" % (rates,))


def test_refresh_shields_propagates_a_battle_granted_trait(rpc, montage_explicite):
    """PROPAGATION PAR PAS. `build_predictor` est COLD (pas 0) : un trait accorde ENSUITE
    (`IdunBattle.Operations.AddTraitOperation$$Execute`, ici `Stationary` pose a l'apparition du
    dreadnought invoque par `DutyEternal`) resterait invisible a la prediction pour TOUTE la
    bataille sans la re-capture de `refresh_shields`. Le predictor de la fixture a ete bati AVANT
    le cast et rafraichi APRES : c'est exactement le regime de la boucle de decision."""
    rid, snap, predictor, spawned = montage_explicite
    assert spawned is not None, "le cast DutyEternal n'a fait apparaitre aucun summon"
    ctx = (predictor.get("ctx_by_id") or {}).get(spawned)
    assert ctx is not None, ("le summon u%s n'a pas ete hydrate par refresh_shields (#53)" % spawned)
    mes = trait_names_from_ids(next(u["traits"] for u in (snap.get("units") or [])
                                    if u.get("entityId") == spawned))
    lu = frozenset(entity_trait_names(ctx, predictor["vis_by_id"].get(spawned)))
    assert UnitTrait.Stationary.name in mes, (
        "montage NON DISCRIMINANT : le summon devait porter `Stationary` accorde en bataille -- %r"
        % (sorted(mes),))
    assert lu == mes, ("la prediction ne voit pas le trait accorde en bataille : MANQUE=%r EN_TROP=%r"
                       % (sorted(mes - lu), sorted(lu - mes)))


def test_resilient_cap_follows_the_measure_not_the_kit(rpc, montage_explicite):
    """CONSEQUENCE CHIFFREE cote PREDICTION : un coup letal sur `necroOverlord` n'est plus rogne.

    Pendant exact de `test_load_state_traits_live::test_resilient_cap_follows_the_measure_not_the_kit`
    (face combat), sur l'etage limites de la PREDICTION : `_target_damage_limits(scene, tgt)` ->
    `apply_trait_damage_limits_to_damage` (mirror d'
    `IdunBattle.Core.Services.DamagePrediction$$ApplyTraitDamageLimitsToDamage`). On soumet un coup
    JUSTE letal (`curHP + 1`, donc sous le seuil d'overkill) dans les deux regimes : canal EFFACE
    (l'avant) doit CAPER a `curHP - 1`, canal MESURE doit laisser passer. La contre-epreuve est
    l'assertion sur le regime efface : sans elle, l'assertion positive ne dirait rien."""
    from engine.playbook.prediction._shared import _target_damage_limits
    from engine.services.trait_damage_limits import apply_trait_damage_limits_to_damage

    rid, snap, _pred, _sp = montage_explicite
    sc, _p = _scene(rpc, rid)
    sc0, _p0 = _scene(rpc, rid, snap_force=_efface(snap))
    cible = next((u for u in sc.vis_by_id if sc.vis_by_id[u] == OVERLORD), None)
    assert cible is not None, "necroOverlord absent du montage"
    hp = int(sc.hp(cible) or 0)
    assert hp > 1, "PV de la cible non lus (%r)" % (hp,)
    letal = hp + 1

    def _cape(scene):
        lim = _target_damage_limits(scene, cible)
        return lim, apply_trait_damage_limits_to_damage(letal, current_health=hp, **lim)

    lim_avant, avant = _cape(sc0)
    lim_seed, apres = _cape(sc)
    assert lim_avant["target_has_resilient"] and avant == hp - 1, (
        "contre-epreuve INOPERANTE : sans la mesure, le kit gameconfig devait faire mordre le cap "
        "Resilient (%d -> %d, limites=%r)" % (letal, avant, lim_avant))
    assert not lim_seed["target_has_resilient"], (
        "le cap Resilient mord encore : la face PREDICTION relit le kit gameconfig au lieu du "
        "substrat mesure -- %r" % (lim_seed,))
    assert apres == letal, (
        "coup letal rogne malgre la mesure : %d -> %d (sans la mesure : %d)" % (letal, apres, avant))


# ---------------------------------------------------------------------------------------------
# MONTAGE 3 -- la POLARITE INVERSE sur les traits de DEPART : le `BC.Units[].Traits` en porte que
# le kit gameconfig n'a PAS (48 unites sur les 175 du seed BC, mesure 2026-07-30).
# ---------------------------------------------------------------------------------------------

def test_bc_only_starting_traits_are_seeded(rpc, build_runner):
    """`custoAtlacoya` porte `SistersSilence` et `astraDreir` `DeathKorpsKrieg` dans le BC, ni l'un
    ni l'autre au gameconfig -- la reconstruction les RATAIT (degradation RESTRICTIVE, sur un trait
    de DEPART, sans aucun `AddTrait` en jeu). Egalite + non-vacuite sur ce regime, cote PREDICTION.
    Second couple (seed, board) : la garde ne tient pas d'un montage unique."""
    rid = build_runner("909", board="C4_09",
                       extra=["--p-units", "custoAtlacoya,astraDreir",
                              "--a-units", "necroWarden,orksNob"])["rid"]
    snap = rpc("combatSnapshot", {"runnerId": rid}, 120)
    lignes, ecarts, rates = _confronte(rpc, rid, snap)
    assert lignes >= 4, "canal `traits` non renseigne : %d ligne(s) mesuree(s)" % lignes
    assert not ecarts, "la face PREDICTION DIVERGE de la mesure :\n  " + "\n  ".join(ecarts)
    joint = " | ".join(rates)
    assert UnitTrait.SistersSilence.name in joint and UnitTrait.DeathKorpsKrieg.name in joint, (
        "regime NON DISCRIMINANT : la reconstruction devait rater les traits de depart portes par "
        "le seul BC (`SistersSilence` / `DeathKorpsKrieg`) -- %r" % (rates,))
