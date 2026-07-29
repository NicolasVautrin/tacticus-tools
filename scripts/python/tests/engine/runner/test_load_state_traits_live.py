"""CLIQUET #264 -- `load_state` CONSOMME `combatSnapshot.units[].traits`.

Le capteur `readUnitTraits` (`frida/hooks/features/ai-step/rpc-snapshot.ts`, `0231573`/#233) invoque
`IdunBattle.Entities.UnitExtensions$$HasTrait(unit, trait)` une fois par valeur d'enum `UnitTrait` et
rend la liste des ids VRAIS -- donc la resultante de
`IdunBattle.Entities.Components.BaseUnitComponent$$HasTrait` (`+0x40` permanents | `+0x48`
temporaires, moins le VETO `+0x50`). `snapshot._load_unit_traits` la pose sur `UnitContext.traits`.

CRITERE GARDE ICI : apres `load_state`, l'ensemble de traits que rend le port est EGAL a celui que
publie le capteur -- pour CHAQUE ligne du snapshot, et par les TROIS lecteurs qui l'exposent
(`entity_trait_names`, `targeting._unit_traits`, `behaviours.context._unit_dict`). Deux montages de
rosters differents, chacun avec sa garde de NON-VACUITE (sans elle, le test passerait a vide le jour
ou le canal cesserait de porter quoi que ce soit).

Les deux regimes discriminants, mesures le 2026-07-30 :
  * `necroOverlord` porte `Resilient` au GAMECONFIG et PAS en bataille (son `BC.Units[].Traits`,
    resolu par PROGRESSION, ne le contient pas) -> la reconstruction en ajoutait un EN TROP. Le
    consommateur mordant est `ApplyResilientTraitDamageLimit` (cape le degat a `HP-1`) : l'unite
    etait donc IMPOSSIBLE A TUER offline, la ou le natif la tue -- degradation PERMISSIVE.
  * le dreadnought invoque par `DutyEternalAbility` (1158) porte `Stationary`, accorde EN BATAILLE
    par `AddTrait(ActiveTarget, 0x418)` -> la reconstruction le RATAIT (degradation RESTRICTIVE).

ASCII only (console cp1252).
"""
from __future__ import annotations

import pytest

from engine.entities.traits.unit_trait import (UnitTrait, entity_trait_names,      # noqa: E402
                                               trait_names_from_ids, unit_trait_names)
from engine.runner.abilities.behaviours.context import _unit_dict                  # noqa: E402
from engine.runner.abilities.targeting import _unit_traits                         # noqa: E402
from engine.runner.components import StatsComponent, UnitComponent                 # noqa: E402
from engine.runner.snapshot import load_state                                      # noqa: E402

DREADNOUGHT = "ultraDreadnought"
SUMMON = "ultraSmnDreadnought"
DUTY_ETERNAL = 1158


def _hexes_cibles(at) -> list:
    """Hexes legaux d'un retour `abilityTargets` : `units[].abilities[].{fromHere,targets}[]`, dont
    chaque entree est `{kind:"tile", tile:{col,row}}` (les cibles ENTITE n'ont pas de `tile`)."""
    out = []
    for u in ((at or {}).get("units") or []):
        for ab in (u.get("abilities") or []):
            for cle in ("fromHere", "targets"):
                for t in (ab.get(cle) or []):
                    tile = t.get("tile") if isinstance(t, dict) else None
                    if isinstance(tile, dict) and tile.get("col") is not None:
                        out.append((int(tile["col"]), int(tile["row"])))
    return out


def _capture(rpc, rid):
    return (rpc("decisionView", {"runnerId": rid, "allAbilities": True, "includeInactive": True}, 150),
            rpc("observeBattle", {"runnerId": rid}, 60),
            rpc("combatSnapshot", {"runnerId": rid}, 120))


def _lecteurs(state, eid, vis):
    """Les TROIS lecteurs du substrat de traits, tels que les consomment les gates du port."""
    ent = state.get_entity(eid)
    sc = ent.get_component(StatsComponent) if ent is not None else None
    return {
        "entity_trait_names": frozenset(entity_trait_names(sc.ctx if sc is not None else None, vis)),
        "targeting._unit_traits": frozenset(_unit_traits(state, eid)),
        "behaviours._unit_dict": frozenset((_unit_dict(state, eid) or {}).get("_traits") or ()),
    }


def _confronte(dec, obs, snap):
    """Rend `(lignes, ecarts, rates_par_la_reconstruction)` pour l'etat charge.

    `ecarts` = divergences du port SEEDE contre la mesure (doit etre vide).
    `rates` = unites que l'etat d'AVANT #264 (canal EFFACE, `traits: null`) manquait -- la
    non-vacuite du montage."""
    st = load_state(dec, obs, snap)
    st_avant = load_state(dec, obs, {**snap, "units": [{**u, "traits": None}
                                                       for u in (snap.get("units") or [])]})
    lignes, ecarts, rates = 0, [], []
    for su in (snap.get("units") or []):
        eid = su.get("entityId")
        if eid is None or not isinstance(su.get("traits"), list):
            continue
        lignes += 1
        mes = trait_names_from_ids(su["traits"])
        ent = st.get_entity(eid)
        uc = ent.get_component(UnitComponent) if ent is not None else None
        vis = uc.visual_id if uc is not None else None
        for nom, val in _lecteurs(st, eid, vis).items():
            if val != mes:
                ecarts.append("u%s %s via %s : MANQUE=%r EN_TROP=%r"
                              % (eid, vis, nom, sorted(mes - val), sorted(val - mes)))
        ent0 = st_avant.get_entity(eid)
        sc0 = ent0.get_component(StatsComponent) if ent0 is not None else None
        avant = frozenset(entity_trait_names(sc0.ctx if sc0 is not None else None, vis))
        if avant != mes:
            rates.append("u%s %s : reconstruction %r vs mesure %r"
                         % (eid, vis, sorted(avant - mes), sorted(mes - avant)))
    return lignes, ecarts, rates


# ---------------------------------------------------------------------------------------------
# MONTAGE 1 -- roster ALEATOIRE seede : le canal repond et le port l'egale sur TOUTES les lignes.
# ---------------------------------------------------------------------------------------------

@pytest.fixture(scope="module")
def montage_aleatoire(rpc, build_runner):
    rid = build_runner("777", board="MC1_67")["rid"]
    return _capture(rpc, rid)


def test_random_roster_port_traits_equal_measured(montage_aleatoire):
    """Roster aleatoire (seed 777 / MC1_67) : egalite stricte, ligne a ligne, par les 3 lecteurs."""
    dec, obs, snap = montage_aleatoire
    lignes, ecarts, _ = _confronte(dec, obs, snap)
    assert lignes >= 4, ("canal `traits` non renseigne (capteur anterieur a 0231573 ?) : %d ligne(s) "
                         "mesuree(s)" % lignes)
    assert not ecarts, "le port DIVERGE de la mesure :\n  " + "\n  ".join(ecarts)


def test_tri_state_null_is_not_empty(montage_aleatoire):
    """`null` = NON MESURE -> la RECONSTRUCTION du port reste intacte ; `[]` = mesure d'un ensemble
    VIDE -> le port ecrit vide. Les confondre ferait passer un capteur MORT pour une unite sans
    trait -- et, ici, ECRASERAIT le kit gameconfig de toutes les unites."""
    dec, obs, snap = montage_aleatoire
    cible = next((u.get("entityId") for u in (snap.get("units") or [])
                  if isinstance(u.get("traits"), list) and u.get("traits")), None)
    assert cible is not None, "aucune ligne mesuree non vide : montage inexploitable"

    def _lire(mut):
        s = {**snap, "units": [({**u, **mut} if u.get("entityId") == cible else u)
                               for u in (snap.get("units") or [])]}
        st = load_state(dec, obs, s)
        e = st.get_entity(cible)
        sc, uc = e.get_component(StatsComponent), e.get_component(UnitComponent)
        return (frozenset(entity_trait_names(sc.ctx if sc is not None else None,
                                             uc.visual_id if uc is not None else None)),
                bool(getattr(sc.ctx, "traits_measured", False)) if sc is not None else False,
                uc.visual_id if uc is not None else None)

    par_null, mesure_null, vis = _lire({"traits": None})
    par_vide, mesure_vide, _ = _lire({"traits": []})
    assert not mesure_null and par_null == frozenset(unit_trait_names(vis)), (
        "canal `null` : le port doit garder sa RECONSTRUCTION (kit gameconfig + grande-alliance), "
        "obtenu %r (attendu %r)" % (sorted(par_null), sorted(unit_trait_names(vis))))
    assert mesure_vide and par_vide == frozenset(), (
        "canal `[]` : mesure d'un ensemble VIDE, le port doit rendre vide -- obtenu %r"
        % (sorted(par_vide),))


# ---------------------------------------------------------------------------------------------
# MONTAGE 2 -- roster EXPLICITE + MoW, puis un trait ACCORDE EN BATAILLE. Les DEUX polarites.
# ---------------------------------------------------------------------------------------------

@pytest.fixture(scope="module")
def montage_explicite(rpc, build_runner):
    """`necroOverlord` (trait gameconfig NON porte en bataille) + `ultraDreadnought` (MoW, ligne
    `EntityType.Machine`) ; on caste `DutyEternal` pour faire apparaitre un summon qui prend
    `Stationary` a l'apparition."""
    rid = build_runner("31337", board="MC1_67",
                       extra=["--p-units", "ultraTitus,ultraApothecary",
                              "--a-units", "necroOverlord,orksWarboss",
                              "--p-mow", DREADNOUGHT])["rid"]
    dec, _obs, _snap = _capture(rpc, rid)
    mow = next((m for m in (dec.get("mows") or []) if m.get("visualId") == DREADNOUGHT), None)
    if mow is not None:
        hexes = _hexes_cibles(rpc("abilityTargets", {"runnerId": rid,
                                                     "unitId": int(mow["casterId"]),
                                                     "abilityType": DUTY_ETERNAL}, 90))
        for col, row in hexes[:6]:
            rpc("applyAction", {"runnerId": rid, "action": {
                "kind": "ability", "casterId": int(mow["casterId"]),
                "abilityType": DUTY_ETERNAL, "to": {"col": col, "row": row}}}, 90)
            dv = rpc("decisionView", {"runnerId": rid}, 90) or {}
            if any(u.get("visualId") == SUMMON for u in (dv.get("units") or [])):
                break
    return _capture(rpc, rid)


def test_explicit_roster_port_traits_equal_measured(montage_explicite):
    """Egalite stricte sur un roster explicite -- lignes `EntityType.Unit` ET `Machine`."""
    dec, obs, snap = montage_explicite
    lignes, ecarts, _ = _confronte(dec, obs, snap)
    assert lignes >= 4, "canal `traits` non renseigne : %d ligne(s) mesuree(s)" % lignes
    assert any(u.get("entityType") == 6 for u in (snap.get("units") or [])), (
        "aucune ligne EntityType.Machine : le montage ne couvre pas la MoW")
    assert not ecarts, "le port DIVERGE de la mesure :\n  " + "\n  ".join(ecarts)


def test_seed_is_not_vacuous_reconstruction_misses_both_polarities(montage_explicite):
    """GARDE DE NON-VACUITE, et elle porte sur les DEUX SENS de l'erreur.

    Le meme etat recharge canal EFFACE (l'etat d'AVANT #264) doit rater `necroOverlord`
    (`Resilient` reconstruit EN TROP) ET le summon (`Stationary` MANQUANT). Un montage ou la
    reconstruction tomberait juste ne prouverait rien du seed."""
    dec, obs, snap = montage_explicite
    _lignes, _ecarts, rates = _confronte(dec, obs, snap)
    assert len(rates) >= 2, (
        "montage NON DISCRIMINANT : la reconstruction ne rate que %d unite(s) -- %r"
        % (len(rates), rates))
    joint = " | ".join(rates)
    assert "necroOverlord" in joint and UnitTrait.Resilient.name in joint, (
        "regime PERMISSIF absent : la reconstruction devait ajouter `Resilient` a necroOverlord -- %r"
        % (rates,))
    assert SUMMON in joint and UnitTrait.Stationary.name in joint, (
        "regime RESTRICTIF absent : le summon de DutyEternal devait porter `Stationary` accorde en "
        "bataille (cast non passe ?) -- %r" % (rates,))


def test_resilient_cap_follows_the_measure_not_the_kit(montage_explicite):
    """CONSEQUENCE CHIFFREE du seed : un coup LETAL sur `necroOverlord` n'est plus rogne a `HP-1`.

    `IdunBattle.Core.Services.DamagePrediction$$ApplyResilientTraitDamageLimit` cape le degat a
    `curHP - 1` quand la cible porte `Resilient` et que le coup n'est pas un overkill. Le lecteur
    COMBAT (`operations/damage.py::_target_limits`) relisait le kit gameconfig, ou `necroOverlord`
    porte le trait : le port RENDAIT LA CIBLE INTUABLE, la ou le natif ne lui donne pas le trait.

    On mesure l'etage LIMITES lui-meme sur un coup juste letal (`curHP + 1`, sous le seuil
    d'overkill), etat SEEDE contre etat canal-EFFACE (l'avant-#264). La contre-epreuve est la garde
    de non-vacuite : si les deux rendaient la meme chose, l'assertion positive ne dirait rien."""
    dec, obs, snap = montage_explicite
    from engine.runner.components import HealthComponent
    from engine.runner.operations.damage import AttackDamageOperation
    from engine.services.trait_damage_limits import apply_trait_damage_limits_to_damage
    cible = next((u.get("id") for u in (dec.get("units") or [])
                  if u.get("visualId") == "necroOverlord"), None)
    assert cible is not None, "necroOverlord absent du montage"

    def _etage(etat):
        ent = etat.get_entity(cible)
        hc = ent.get_component(HealthComponent)
        lim = AttackDamageOperation._target_limits(ent, hc)
        letal = int(hc.hp) + 1
        if lim is None:                       # fast-path : mono-membre sans Resilient -> no-op
            return lim, letal, letal
        garde = dict(lim)
        garde.pop("is_special", None)
        return lim, letal, apply_trait_damage_limits_to_damage(
            letal, is_special=1, current_health=int(hc.hp),
            **{k: v for k, v in garde.items() if k != "current_health"})

    lim_seed, letal, apres = _etage(load_state(dec, obs, snap))
    lim_avant, _letal0, avant = _etage(load_state(
        dec, obs, {**snap, "units": [{**u, "traits": None} for u in (snap.get("units") or [])]}))

    assert lim_avant is not None and lim_avant["target_has_resilient"] and avant < letal, (
        "contre-epreuve INOPERANTE : sans le seed, le kit gameconfig devait faire mordre le cap "
        "Resilient (limites=%r, %d -> %d)" % (lim_avant, letal, avant))
    assert lim_seed is None or not lim_seed["target_has_resilient"], (
        "le cap Resilient mord encore : le lecteur COMBAT relit le kit gameconfig au lieu du "
        "substrat mesure -- %r" % (lim_seed,))
    assert apres == letal, (
        "coup letal rogne malgre la mesure : %d -> %d (sans le seed : %d)" % (letal, apres, avant))


# ---------------------------------------------------------------------------------------------
# MONTAGE 3 -- la POLARITE INVERSE au montage 2 sur les traits de DEPART : le `BC.Units[].Traits`
# en porte que le kit gameconfig n'a PAS (48 unites sur les 175 du seed BC, mesure 2026-07-30).
# ---------------------------------------------------------------------------------------------

def test_bc_only_starting_traits_are_seeded(rpc, build_runner):
    """`custoAtlacoya` porte `SistersSilence` et `astraDreir` `DeathKorpsKrieg` dans le BC, ni l'un
    ni l'autre au gameconfig -- la reconstruction les RATAIT (degradation RESTRICTIVE, cette fois
    sur un trait de DEPART, sans aucun `AddTrait` en jeu). Egalite + non-vacuite sur ce regime."""
    rid = build_runner("909", board="MC1_67",
                       extra=["--p-units", "custoAtlacoya,astraDreir",
                              "--a-units", "necroWarden,orksNob"])["rid"]
    dec, obs, snap = _capture(rpc, rid)
    lignes, ecarts, rates = _confronte(dec, obs, snap)
    assert lignes >= 4, "canal `traits` non renseigne : %d ligne(s) mesuree(s)" % lignes
    assert not ecarts, "le port DIVERGE de la mesure :\n  " + "\n  ".join(ecarts)
    joint = " | ".join(rates)
    assert UnitTrait.SistersSilence.name in joint and UnitTrait.DeathKorpsKrieg.name in joint, (
        "regime NON DISCRIMINANT : la reconstruction devait rater les traits de depart portes par "
        "le seul BC (`SistersSilence` / `DeathKorpsKrieg`) -- %r" % (rates,))
