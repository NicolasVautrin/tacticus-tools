"""CLIQUET #267-r1 -- les GATES DE TRAIT de la face PREDICTION lisent le substrat d'ENTITE.

SUITE de `test_predictor_traits_live.py` (#267), sur l'etage d'AU-DESSUS. #267 a fait entrer la
MESURE (`combatSnapshot.units[].traits`) dans `UnitContext.traits` des tables de prediction ; mais
12 sites de cette MEME face continuaient de relire `gameconfig.unit(visualId).traits` **BRUT** pour
leurs gates de trait. Une face qui lit la mesure sur une partie de ses gates et le kit sur l'autre,
c'est une incoherence INTERNE -- pire qu'un retard uniforme.

CE QUE LIT LE NATIF (decompile, build `rnca9r7q6c`). Il n'y a QU'UN substrat de traits, porte par
l'entite, et TOUS les gates y aboutissent :

  * `IdunBattle.Core.Services.DamagePrediction$$GetBaseDamageWithFixedPiercedArmor` ->
    `IdunBattle.Entities.UnitExtensions$$HasTrait(defender, 0x3f5)` (MkXGravis, `hit_multiplier` 2) ;
  * `IdunBattle.AI.Playbook.Loki.HellfireShellsPlaybook$$MakeDamagePredictions` ->
    `IdunBattle.Entities.UnitExtensions$$HasTrait(target, 0x3f9)` (BigTarget, `+extraHit`) EN DIRECT ;
  * les gates DSL (`IdunBattle.Entities.Effects.Loki.BeastSlayer_ExtraDmgEffect$$
    CreateDamageModifier`, `MartialKatahDamageEffect$$CreateEffectDamageBonusForAttack`, ...) passent
    par `IdunBattle.Entities.Triggers.HasTraitTrigger$$Evaluate`, qui resout l'entite du selecteur
    puis appelle **le meme** `UnitExtensions$$HasTrait`.

et `UnitExtensions$$HasTrait` delegue a `IdunBattle.Entities.Components.BaseUnitComponent$$HasTrait`
(`+0x50` veto, `+0x40` permanents, `+0x48` temporaires). AUCUNE lecture de gameconfig sur ce chemin.

CE QUE CES TESTS GARDENT :
  1. le substrat lu par les gates EGALE la mesure, ligne a ligne -- et la relecture du kit BRUT
     (l'AVANT) en DIVERGE (garde de NON-VACUITE : sans elle, l'egalite ne prouverait rien) ;
  2. la CONSEQUENCE CHIFFREE : `MartialKatah` (+100 % de degat vs `Summon`) suit le CANAL, et le
     port NEUTRALISE (gates re-branches sur le kit brut) y est SOURD ;
  3. l'ORACLE NATIF est inchange la ou kit et mesure concordent (aucune regression).

ASCII only (console cp1252).
"""
from __future__ import annotations

import pytest

import gameconfig as GC                                                        # noqa: E402
import hexgeo                                                                  # noqa: E402
from engine.entities.traits.unit_trait import (UnitTrait,                      # noqa: E402
                                               trait_names_from_ids)
from engine.playbook import scene as SC                                        # noqa: E402
from engine.playbook.prediction import _entity_traits                          # noqa: E402
from engine.playbook.scene import Scene                                        # noqa: E402

KATAH = "custoTrajann"          # porte le trait MartialKatah (+100 % vs Summon)
CIBLE = "orksWarboss"           # aucune occurrence de `Summon`, ni au kit ni au BC
SUMMON_ID = int(UnitTrait.Summon)                       # 2


# ── outillage de montage ───────────────────────────────────────────────────────────────────────
def _scene(rpc, rid, force=None) -> Scene:
    """La Scene de la face PREDICTION, montee comme le spine de decision (`engine.ai.context`).
    `force` substitue le `combatSnapshot` -- c'est LE levier de contre-epreuve de #267."""
    def _r(m, b=None, t=120):
        return force if (m == "combatSnapshot" and force is not None) else rpc(m, b, t)
    pred = SC.build_predictor(_r, rid)
    assert pred is not None, "build_predictor KO (combatSnapshot indispo)"
    vue = rpc("decisionView", {"runnerId": rid, "maxRank": 1}, 150)
    sctx = SC.step_context(pred, vue)
    obs = rpc("observeBattle", {"runnerId": rid}, 60) or {}
    hp = {u.get("squadId"): (u.get("hpMax") or 0) for u in (obs.get("units") or [])}
    hp.update(pred.get("hpmax_eff_by_id") or {})
    sctx["hpmax_by_id"] = hp
    return Scene.from_predictor_sctx(pred, sctx, None)


def _kit_brut(scene, uid) -> frozenset:
    """CE QUE LES 12 SITES LISAIENT avant #267-r1 : `gameconfig.unit(visualId).traits`, BRUT --
    donc sans les traits accordes en bataille, sans l'ecart `BC.Units[].Traits` vs kit, et sans le
    pseudo-trait de GRANDE ALLIANCE (qu'aucun `traits` gameconfig ne contient)."""
    return frozenset((GC.unit(scene.vis_by_id.get(uid)) or {}).get("traits") or ())


def _canal(snap, eid, avec_summon: bool) -> dict:
    """Le MEME snapshot, la ligne `traits` de `eid` forcee AVEC / SANS `UnitTrait.Summon`.
    Substitution de CANAL -- exactement le levier `_efface` de #267, avec une autre valeur que
    `null`."""
    out = []
    for u in (snap.get("units") or []):
        if u.get("entityId") != eid or not isinstance(u.get("traits"), list):
            out.append(u)
            continue
        t = [x for x in u["traits"] if int(x) != SUMMON_ID]
        out.append({**u, "traits": (t + [SUMMON_ID]) if avec_summon else t})
    return {**snap, "units": out}


def _pos_by_id(dv) -> dict:
    return {u.get("id"): ((u.get("pos") or {}).get("col"), (u.get("pos") or {}).get("row"))
            for u in ((dv or {}).get("units") or [])}


def _rapprocher(rpc, rid, a_id, b_id, tours=8):
    """Amene deux unites AU CONTACT en pilotant les DEUX camps (`applyAction` ne verifie pas la
    propriete du casterId, cf. runner.md §4) : chacune va sur la tuile de son movable set qui
    minimise la distance hex a l'autre, puis `endturn`. On DRIVE la geometrie, on ne la subit pas."""
    for _ in range(tours):
        pos = _pos_by_id(rpc("decisionView", {"runnerId": rid}, 150))
        pa, pb = pos.get(a_id), pos.get(b_id)
        if pa and pb and pa[0] is not None and pb[0] is not None and hexgeo.distance(pa, pb) <= 1:
            return pa, pb
        mv = rpc("aiMovableTiles", {"runnerId": rid}, 120) or {}
        for u in (mv.get("units") or []):
            uid = u.get("unitId")
            if uid not in (a_id, b_id):
                continue
            autre = pos.get(b_id if uid == a_id else a_id)
            tiles = [(t.get("col"), t.get("row")) for t in (u.get("tiles") or [])
                     if t.get("col") is not None]
            if not tiles or not autre or autre[0] is None:
                continue
            best = min(tiles, key=lambda t: hexgeo.distance(t, autre))
            rpc("applyAction", {"runnerId": rid, "action": {
                "kind": "move", "unitId": int(uid),
                "to": {"col": best[0], "row": best[1]}}}, 120)
        rpc("applyAction", {"runnerId": rid, "action": {"kind": "endturn"}}, 120)
    pos = _pos_by_id(rpc("decisionView", {"runnerId": rid}, 150))
    return pos.get(a_id), pos.get(b_id)


def _confronte_substrat(rpc, rid, snap):
    """(lignes, ecarts vs mesure, lignes ou le KIT BRUT divergeait). Le 3e terme est la garde de
    NON-VACUITE propre a #267-r1 : l'« avant » de CE residu est la relecture du kit brut."""
    sc = _scene(rpc, rid)
    lignes, ecarts, kit_faux = 0, [], []
    for su in (snap.get("units") or []):
        eid = su.get("entityId")
        if eid is None or not isinstance(su.get("traits"), list) or sc.ctx(eid) is None:
            continue
        lignes += 1
        mes = trait_names_from_ids(su["traits"])
        lu = frozenset(_entity_traits(sc, eid))
        brut = _kit_brut(sc, eid)
        if lu != mes:
            ecarts.append("u%s %s : MANQUE=%r EN_TROP=%r"
                          % (eid, sc.vis_by_id.get(eid), sorted(mes - lu), sorted(lu - mes)))
        if brut != mes:
            kit_faux.append("u%s %s : kit RATAIT %r, ACCORDAIT A TORT %r"
                            % (eid, sc.vis_by_id.get(eid), sorted(mes - brut), sorted(brut - mes)))
    return lignes, ecarts, kit_faux


# ── MONTAGE 1 : le substrat, sur deux couples (seed, board) ────────────────────────────────────
@pytest.fixture(scope="module")
def montage_substrat(rpc, build_runner):
    """Roster choisi pour couvrir les traits que le balayage exhaustif
    (`probe_267r1_gate_sweep.py`) designe comme CONSOMMES par les 12 sites : `Vehicle`
    (admecDestroyer), `BigTarget` (orksWarboss), `Psyker` (eldarFarseer), plus deux porteurs
    BeastSlayer/MartialKatah cote attaquant."""
    rid = build_runner("777", board="MC1_67",
                       extra=["--p-units", "ultraTitus,adeptCanoness,custoTrajann",
                              "--a-units", "admecDestroyer,orksWarboss,eldarFarseer"])["rid"]
    return rid, rpc("combatSnapshot", {"runnerId": rid}, 150)


def test_trait_gates_read_the_measured_substrate(rpc, montage_substrat):
    """Le substrat que lisent les gates EGALE la mesure, ligne a ligne."""
    rid, snap = montage_substrat
    lignes, ecarts, _ = _confronte_substrat(rpc, rid, snap)
    assert lignes >= 4, ("canal `traits` non renseigne : %d ligne(s) mesuree(s) -- montage "
                         "inexploitable" % lignes)
    assert not ecarts, ("les gates de la face PREDICTION DIVERGENT de la mesure :\n  "
                        + "\n  ".join(ecarts))


def test_raw_kit_read_was_wrong_on_every_line(rpc, montage_substrat):
    """NON-VACUITE. Le meme etat, lu comme AVANT (`gameconfig.unit(vis).traits` BRUT), doit
    DIVERGER -- sinon l'egalite ci-dessus serait triviale.

    Le pseudo-trait de GRANDE ALLIANCE suffit a lui seul : le BC l'ecrit dans
    `BaseUnitComponent+0x40` (la mesure le rend), et AUCUN `gameconfig.unit().traits` ne le
    contient -- mesure offline : 175/175 unites du seed BC. Ce n'est donc pas un artefact de
    capture, c'est structurel."""
    rid, snap = montage_substrat
    lignes, _, kit_faux = _confronte_substrat(rpc, rid, snap)
    assert len(kit_faux) == lignes and lignes >= 4, (
        "contre-epreuve INOPERANTE : le kit BRUT ne divergeait que sur %d/%d lignes -- %r"
        % (len(kit_faux), lignes, kit_faux))
    joint = " | ".join(kit_faux)
    assert any(t in joint for t in ("Imperial", "Xenos", "Chaos")), (
        "le pseudo-trait d'ALLIANCE devait manquer au kit BRUT sur ce roster -- %r" % (kit_faux,))


def test_trait_gates_read_the_measured_substrate_second_couple(rpc, build_runner):
    """GENERALISATION : second couple (seed, board), roster different. Une garde qui ne tient que
    d'un montage unique ne tient pas."""
    rid = build_runner("909", board="C4_09",
                       extra=["--p-units", "custoAtlacoya,astraDreir",
                              "--a-units", "necroWarden,orksNob"])["rid"]
    snap = rpc("combatSnapshot", {"runnerId": rid}, 150)
    lignes, ecarts, kit_faux = _confronte_substrat(rpc, rid, snap)
    assert lignes >= 4, "canal `traits` non renseigne : %d ligne(s)" % lignes
    assert not ecarts, "DIVERGENCE vs mesure :\n  " + "\n  ".join(ecarts)
    assert len(kit_faux) == lignes, ("contre-epreuve INOPERANTE sur ce couple : %d/%d"
                                     % (len(kit_faux), lignes))


# ── MONTAGE 2 : la CONSEQUENCE CHIFFREE (MartialKatah +100 % vs `Summon`) ──────────────────────
@pytest.fixture(scope="module")
def montage_katah(rpc, build_runner):
    """`custoTrajann` (MartialKatah) amene AU CONTACT d'`orksWarboss`. Rend
    `(rid, snap, att_id, tgt_id, att_pos, normal_attack_id)`."""
    rid = build_runner("4242", board="MC1_67",
                       extra=["--p-units", "%s,ultraApothecary" % KATAH,
                              "--a-units", "%s,necroWarden" % CIBLE])["rid"]
    dec = rpc("decisionView", {"runnerId": rid, "allAbilities": True}, 200) or {}
    by_vis = {u.get("visualId"): u for u in (dec.get("units") or [])}
    assert KATAH in by_vis and CIBLE in by_vis, "montage KO : %r" % sorted(by_vis)
    aid, tid = int(by_vis[KATAH]["id"]), int(by_vis[CIBLE]["id"])
    pa, _pb = _rapprocher(rpc, rid, aid, tid)
    na = next((int(ab.get("abilityType") or ab.get("id"))
               for ab in (by_vis[KATAH].get("abilities") or [])
               if "normalattack" in (ab.get("name") or "").lower()), None)
    return rid, rpc("combatSnapshot", {"runnerId": rid}, 150), aid, tid, pa, na


def _degat(scene, aid, tid, apos):
    from engine.playbook.prediction import make_normal_attack_predictions
    ev = make_normal_attack_predictions(scene, aid, tid, apos)
    assert ev is not None, "aucune prediction d'attaque normale"
    r = ev.prediction.raw_health_damage
    return (int(r.min), int(r.max))


def test_martial_katah_bonus_follows_the_measurement_channel(rpc, montage_katah):
    """CONSEQUENCE CHIFFREE. `MartialKatahDamageEffect$$CreateEffectDamageBonusForAttack` =
    `ForPercentIncrease(HasTrait(target, Summon = 2), Direct(martialKatahExtraDmgPct = 100))`.

    MEME etat, MEME pas, MEME tuile ; seule la ligne `traits` de la CIBLE change. Le gate doit
    suivre le CANAL : ~x2 entre les deux. Mesure de reference (seed 4242 / MC1_67, tuile (5,4)) :
    `(2118, 3180)` sans `Summon`, `(4239, 6360)` avec -- x2.0014 / x2.0000."""
    rid, snap, aid, tid, apos, _na = montage_katah
    assert any(e.name and "MartialKatah" in e.name
               for e in (_scene(rpc, rid).effects(aid) or [])), (
        "montage NON DISCRIMINANT : l'effet MartialKatah_DmgBonus n'est pas actif sur l'attaquant")
    sans = _degat(_scene(rpc, rid, force=_canal(snap, tid, False)), aid, tid, apos)
    avec = _degat(_scene(rpc, rid, force=_canal(snap, tid, True)), aid, tid, apos)
    assert sans[0] > 0, "degat nul : montage inexploitable (%r)" % (sans,)
    assert avec[1] == 2 * sans[1], (
        "le gate `HasTrait(target, Summon)` ne suit PAS le canal de mesure : %r -> %r "
        "(attendu le double sur la borne max)" % (sans, avec))


def test_neutralised_wiring_is_deaf_to_the_channel(rpc, montage_katah, monkeypatch):
    """CONTRE-EPREUVE / ROUGE PROVOQUE. Gates re-branches sur le kit BRUT = l'etat d'AVANT
    #267-r1 : les deux canaux doivent alors rendre la MEME valeur. Sans cette assertion, le test
    ci-dessus ne dirait pas d'ou vient le x2.

    ⚠ `normal_attack` / `abilities` importent le helper PAR NOM (`from ._shared import ...`) :
    patcher le seul `_shared` ne les atteindrait pas -- il faut les TROIS modules."""
    from engine.playbook.prediction import _shared, abilities as _abm, normal_attack as _na
    rid, snap, aid, tid, apos, _nid = montage_katah
    for m in (_shared, _na, _abm):
        monkeypatch.setattr(m, "_entity_traits", _kit_brut)
    sans = _degat(_scene(rpc, rid, force=_canal(snap, tid, False)), aid, tid, apos)
    avec = _degat(_scene(rpc, rid, force=_canal(snap, tid, True)), aid, tid, apos)
    assert sans == avec, (
        "CONTRE-EPREUVE INOPERANTE : sans le cablage, le gate reagit encore au canal (%r vs %r) -- "
        "le montage ne mesure donc pas ce qu'il pretend mesurer" % (sans, avec))


def test_native_oracle_unchanged_where_kit_and_measure_agree(rpc, montage_katah):
    """NON-REGRESSION. Sur l'etat NON MUTE (kit et mesure concordent sur `Summon` pour cette
    cible), le port cable doit rester EXACT vs `aiPlaybookPredict` -- l'oracle direct du playbook
    natif. Mesure de reference : oracle `(2118, 3180)` appliedHits=3, port `(2118, 3180)`,
    ecart (0, 0)."""
    rid, _snap, aid, tid, apos, na = montage_katah
    assert na is not None, "attaque normale de l'attaquant non resolue"
    orc = rpc("aiPlaybookPredict", {"runnerId": rid, "unitId": aid, "targetId": tid,
                                    "abilityType": na}, 150) or {}
    evs = [e for e in (orc.get("events") or []) if e.get("targetId") == tid]
    assert evs, "l'oracle natif n'a rendu aucun event pour la cible : %r" % (orc,)
    nat = (int(evs[0].get("healthDmgMin") or 0), int(evs[0].get("healthDmgMax") or 0))
    port = _degat(_scene(rpc, rid), aid, tid, apos)
    assert port == nat, ("le port cable DIVERGE de l'oracle natif : port=%r oracle=%r "
                         "(ecart %r)" % (port, nat, (port[0] - nat[0], port[1] - nat[1])))
