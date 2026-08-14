#!/usr/bin/env python
"""Probe #1015-r1 -- le trait `CloseCombatWeakness` CONFRONTE LIVE, avec TEMOIN NON-NUL.

CE QU'IL MESURE, et contre quoi :

  1. KIT       -- l'ability `TriggeredAbilityType.CloseCombatWeakness` (1130) est-elle MONTEE sur le
                  porteur quand on force le trait ? Canal `unitAbilityStates` (l'`AbilitiesComponent`
                  REEL), jamais le gameconfig. C'est la confrontation LIVE du dict
                  `idun.Idun.Source.Shared.Battle.StaticBattleRules.StaticBattleRules.Trait$$.cctor`
                  (+0x0), lu au decompile : cle `0x40b` (UnitTrait 1035) -> valeur `0x46a` (1130).

  2. NATIF     -- le natif applique-t-il vraiment le malus, et de combien ? DEUX runners, MEME seed,
                  MEME board, MEMES unites, MEME `Movement` : le seul ECART est le trait. On compare
                  la PREDICTION NATIVE (`decisionView.attackPlans`, `ranked[0].dmgMin/dmgMax`) de la
                  MEME attaque normale depuis la MEME tuile candidate. Le runner SANS trait EST le
                  temoin non-nul : sans lui, un accord ne prouverait rien (regime degenere).

  3. PORT      -- le port rend-il la MEME chose que le natif, DANS LES DEUX REGIMES ? La prediction
                  offline passe par `engine.playbook.prediction.make_normal_attack_predictions` sur
                  la `Scene`, exactement comme `predict_samples`. Un accord dans le seul regime SANS
                  trait ne prouverait rien non plus : c'est le couple qui fait la mesure.

MONTAGE. Les 16 porteurs du trait sont TOUS `units.npc`, donc hors pool. Le trait se GREFFE par
`rl_duel build --unit-stat "<vis>:Traits=[...]"`, levier qui mord sur 104 des 105 membres de
`UnitTrait`. Le porteur greffe est `astraBullgryn` : HERO du pool, arme MELEE unique, deux traits
seulement -- et rien dans `CloseCombatWeakness_ReduceDmg_Effect` ni dans son playbook ne lit les
stats ou les traits du caster, donc la greffe est LEGITIME (meme critere que `1194 NovaShield`).

`Movement=12` est pose SUR LES DEUX runners : il ne touche aucun canal de degat, et il met la tuile
d'attaque a portee du premier tour -- sans lui la mesure demanderait plusieurs tours de nav, donc
deux etats divergents.

⚠ MESURE INATTENDUE, ET ELLE EST DANS LE RESULTAT : `BC.Abilities.Traits` ne contient QUE
`{HeavyWeapon, MartialKatah, RangedSpecialist}` -- **pas** `CloseCombatWeakness` -- et le natif
applique quand meme le malus. La config de cette ability de trait n'est donc PAS lue depuis la
`BattleConfiguration` ; aucune injection de config n'est requise pour ce montage, contrairement au
verrou d'une ability de RELIQUE (#237). Le port lit la source AMONT (`globalValues.traitVariables`,
`closeCombatWeaknessMeleeDmgPctReduction` = -50 / `...Range...` = -25), et les deux concordent.

Usage (depuis scripts/python, session Frida chaude) :
    python probe_1015r1_close_combat_weakness.py
    python probe_1015r1_close_combat_weakness.py --keep      # ne pas disposer les runners

ASCII only (cp1252).
"""
from __future__ import annotations

import argparse
import os
import sys
import tempfile
from pathlib import Path

PYDIR = Path(__file__).resolve().parent
if str(PYDIR) not in sys.path:
    sys.path.insert(0, str(PYDIR))

import rl_duel as R                                                    # noqa: E402
from engine import battle_query as _bq                                 # noqa: E402
from engine.playbook import adjacency as _adj                          # noqa: E402
from engine.playbook import scene as SC                                # noqa: E402
from engine.playbook import prediction                                 # noqa: E402
from engine.playbook.scene import Scene                                # noqa: E402
from engine.runner import snapshot as _snapshot                        # noqa: E402

#: LES DEUX VOLETS, un par branche du `If(IsMeleeAttack, ...)` de
#: `CloseCombatWeakness_ReduceDmg_Effect$$CreateEffectDamageBonusForAttack`.
#:
#: `melee`  -- porteur GREFFE `astraBullgryn` : HERO du pool, arme MELEE unique (Physical, 4 coups),
#:             deux traits seulement. Une seule cible : au contact, `GetAbilityAttackRangeType` rend
#:             MELEE et la branche `ConfigConst(0x4c)` tire.
#: `ranged` -- porteur `necroWarden` : DEUX armes (Physical melee + Gauss PORTEE 3), donc
#:             `AttackRangeType = Both` -> la nature du coup est POSITIONNELLE
#:             (`AreUnitsInMelee(attPos, tgtPos)`, cf. `effects/base.py`). DEUX ennemis : le porteur
#:             se place au CONTACT de l'un (ce qui ARME `HasAdjacentEnemies`) et TIRE sur l'autre a
#:             distance 2-3 (ce qui prend la branche `ConfigConst(0x53)`). Le pool ne contient
#:             AUCUNE unite ranged-only (mesure : 0 sur 97), donc ce montage a DEUX cibles est le
#:             seul qui separe les deux branches -- et il exige la PORTEE 3 (mesure : avec la
#:             portee 2 de `tauDarkstrider`, la seule tuile au contact met l'autre ennemi hors
#:             portee, donc AUCUN plan et un « NON CONFRONTE » pour une mauvaise raison).
VOLETS = {
    "melee": {"porteur": "astraBullgryn",
              "traits": ["Hero", "BigTarget"],
              "cibles": ["astraCreed"],
              "pct": -50,
              "nature": "melee"},
    "ranged": {"porteur": "necroWarden",
               "traits": ["Hero", "LivingMetal", "Mechanical"],
               # CINQ cibles, et c'est une MESURE, pas une precaution : avec DEUX ennemis, le seed
               # les pose COLINEAIRES ((6,8) et (6,7)), donc toute tuile au contact de l'un a
               # l'autre a d = 2 DERRIERE lui -- le natif n'emet alors aucun plan (l'ennemi adjacent
               # bloque la ligne), et le regime sort NON CONFRONTE pour une raison de LOS, pas de
               # mecanique. A cinq, la tuile (5,6) met le 5e ennemi au CONTACT et laisse deux cibles
               # a d = 2 EN CLAIR, et le natif la classe lui-meme dans ses `ranked`.
               # ⚠ Le 5e est `astraYarrick` (`Hero`, `Resilient`) et surtout PAS `bloodDante` : ce
               # dernier porte `TeleportStrike`, donc il arrive en DEEP-STRIKE et n'est pas
               # CIBLABLE au tour 1. Il est alors ecarte par le `UnitSelectionType 3
               # (OnlyAliveAndTargetable)` que `HasAdjacentEnemies` propage a tous ses etages --
               # des DEUX cotes. Mesure : avec lui, `n_adj` valait 1 en geometrie nue mais 0 au
               # `selectionType`, natif et port rendaient tous deux AUCUN malus, et le probe
               # criait `ECHEC` sur un regime qui n'existait pas.
               "cibles": ["astraCreed", "astraBullgryn", "adeptCanoness", "astraDreir", "astraYarrick"],
               "pct": -25,
               "nature": "ranged"},
}
BOARD = "MC1_67"
SEED = 777
TRAIT = "CloseCombatWeakness"
#: `TriggeredAbilityType.CloseCombatWeakness`, la valeur du dict `Trait$$GetTriggeredAbility`.
ABILITY_ID = 1130


def _res(r):
    return r.get("result") if isinstance(r, dict) and "result" in r else r


def _sf(nom: str) -> str:
    """State-file ABSOLU, unique par PID, HORS `data/` (que `rl_duel --state-file` refuse, #349)."""
    return os.path.join(tempfile.gettempdir(), "ccw_%d_%s.json" % (os.getpid(), nom))




def _build(state_file: str, volet: dict, with_trait: bool) -> int:
    traits = list(volet["traits"]) + ([TRAIT] if with_trait else [])
    porteur = volet["porteur"]
    R.main(["build", "--seed", str(SEED), "--board", BOARD,
            "--p-units", porteur, "--a-units", ",".join(volet["cibles"]),
            "--state-file", state_file,
            "--unit-stat", "%s:Traits=%s" % (porteur, str(traits).replace("'", '"')),
            "--unit-stat", "%s:Movement=12" % porteur])
    return int(R._read_state(Path(state_file))["runnerId"])


def _hexdist(a, b) -> int:
    import hexgeo
    return hexgeo.distance(tuple(a), tuple(b))


def _n_adj(tile, adv, scene, units_by_id) -> int:
    """Ennemis a l'ADJACENCE NATIVE de `tile` -- `engine.battle_query.is_adjacent`, JAMAIS
    `hexgeo.distance == 1`.

    ⚠ CE N'EST PAS UN DETAIL, et le probe l'a appris a ses depens : avec `hexgeo` nu, le volet
    RANGED rendait `ECHEC -- le natif rend LA MEME CHOSE avec et sans le trait` sur SEPT couples,
    alors que port et natif etaient d'ACCORD PARFAIT sur les quatorze valeurs. La cause est la porte
    d'ELEVATION `abs(dElev) < 2` de `IdunBattle.Core.Services.TileQuery.
    u003CIterateAdjacentTilesu003Ed__8$$MoveNext` : deux tuiles cote a cote mais separees de deux
    niveaux ne sont PAS voisines pour le natif. C'est la mesure #271 (hexgeo se trompe 9 / 22 / 2
    fois sur trois boards, TOUJOURS dans le sens PERMISSIF) -- ici elle a fabrique un faux ECHEC en
    declarant << au contact >> un porteur qui ne l'etait pas.

    ⚠ ET LE `UnitSelectionType 3` COMPTE AUTANT. `HasAdjacentEnemies` propage `3
    (OnlyAliveAndTargetable)` a TOUS ses etages, donc une unite VIVANTE mais NON CIBLABLE (arrivee
    en deep-strike `TeleportStrike`) n'est PAS un ennemi adjacent. Mesure : `bloodDante` etait
    hex-adjacent ET natif-adjacent, mais non ciblable -- natif comme port rendaient AUCUN malus, et
    un critere qui l'ignore fabrique un `ECHEC` sur un regime qui n'existe pas."""
    return sum(1 for eid, p in adv.items()
               if _bq.is_adjacent(tuple(tile), tuple(p),
                                  getattr(scene, "elev_by_pos", None), _bq.neigh_map(scene))
               and _adj.unit_matches(scene, units_by_id.get(eid) or {}))


def _mesure(sid, rid: int, volet: dict) -> dict:
    """Rend {`kit`, `plans`} : le kit DECLENCHE du porteur (canal `unitAbilityStates`) et, par plan
    d'attaque NORMALE du porteur, le couple (oracle natif, prediction du port) a la MEME tuile
    candidate -- avec la GEOMETRIE qui decide la branche du `If(IsMeleeAttack, ...)` :
    `d_cible` (distance a la cible depuis la tuile candidate) et `n_adj` (ennemis a son ring-1)."""
    def rpc(m, body=None, t=90):
        return _res(R._rpc(sid, m, [body] if body is not None else [], timeout=t))

    st = rpc("unitAbilityStates", {"runnerId": rid})
    kit = {}
    for u in (st.get("units") or ()):
        if u.get("configId") == volet["porteur"]:
            kit[int(u["entityId"])] = sorted(int(t["raw"][0]) for t in (u.get("triggered") or ()))

    predictor = SC.build_predictor(lambda m, b, t: rpc(m, b, t), rid)
    # `maxRank=12` et non 3 : le regime RANGED discriminant (tuile au CONTACT d'un ennemi, cible a
    # distance >= 2) est par construction une MAUVAISE tuile pour le natif -- elle sort donc hors du
    # top-3 des `ranked`, et un `maxRank` trop court rend « NON CONFRONTE » un regime qui EXISTE.
    _dv = lambda: rpc("decisionView",                                   # noqa: E731
                      _snapshot.decision_view_seed_body(rid, maxRank=12, allAbilities=True))
    dec = _dv()
    sctx = SC.step_context(predictor, dec)
    scene = Scene.from_predictor_sctx(predictor, sctx, None)
    pos_by_id = sctx["pos_by_id"]
    units_by_id = {u["id"]: u for u in (dec.get("units") or ())}
    ennemis = {u["id"]: (u["pos"]["col"], u["pos"]["row"])
               for u in (dec.get("units") or ()) if u.get("alive") and u.get("pos")
               and u.get("team") != 1}
    plans = []
    for ap in (dec.get("attackPlans") or ()):
        a_id = ap.get("unitId")
        if a_id not in kit:                       # on ne mesure QUE le porteur greffe
            continue
        norm = {ab.get("id") for u in (dec.get("units") or ()) if u.get("id") == a_id
                for ab in (u.get("abilities") or ()) if ab.get("kind") == "normal"}
        for ev in (ap.get("evals") or ()):
            if norm and ev.get("abilityId") not in norm:
                continue
            for r0 in (ev.get("ranked") or ()):
                if r0.get("dmgMax") is None:
                    continue
                t_id = ev.get("targetId")
                att_pos = ((r0.get("col"), r0.get("row")) if r0.get("col") is not None
                           else pos_by_id.get(a_id))
                if att_pos is None or t_id not in ennemis:
                    continue
                pred = prediction.make_normal_attack_predictions(scene, a_id, t_id, att_pos)
                res = pred.prediction.accurate_health_damage
                plans.append({
                    "att": a_id, "tgt": t_id, "att_pos": tuple(att_pos),
                    "d_cible": _hexdist(att_pos, ennemis[t_id]),
                    "n_adj": _n_adj(att_pos, ennemis, scene, units_by_id),
                    "oracle": (r0.get("dmgMin"), r0.get("dmgMax")),
                    "port": (res.min, res.max),
                    "pred_opt": bool(r0.get("predOptimistic"))})
    return {"kit": kit, "plans": plans}


def _joue(volet_nom: str, keep: bool) -> int:
    volet = VOLETS[volet_nom]
    sid = R._resolve_session()
    sf_w, sf_o = _sf(volet_nom + "_with"), _sf(volet_nom + "_without")
    rid_w = _build(sf_w, volet, True)
    rid_o = _build(sf_o, volet, False)
    print("\n===== VOLET %s -- porteur=%s cibles=%s | runners AVEC=%s SANS=%s"
          % (volet_nom.upper(), volet["porteur"], volet["cibles"], rid_w, rid_o))
    try:
        m_w, m_o = _mesure(sid, rid_w, volet), _mesure(sid, rid_o, volet)
    finally:
        if not keep:
            for f in (sf_w, sf_o):
                try:
                    R.main(["dispose", "--state-file", f])
                except SystemExit:
                    pass
                except Exception as e:                      # noqa: BLE001
                    print("[dispose] %s : %s" % (f, e))

    rc = 0
    kit_w = sorted(set().union(*m_w["kit"].values())) if m_w["kit"] else []
    kit_o = sorted(set().union(*m_o["kit"].values())) if m_o["kit"] else []
    print("1. KIT DECLENCHE du porteur (`unitAbilityStates`) : AVEC=%s SANS=%s" % (kit_w, kit_o))
    if ABILITY_ID not in kit_w:
        print("   ECHEC : l'ability %d n'est PAS montee alors que le trait est pose -- le dict "
              "`Trait$$GetTriggeredAbility` ne mappe pas ce trait, ou le patch n'a pas mordu."
              % ABILITY_ID)
        return 1
    if ABILITY_ID in kit_o:
        print("   ECHEC : l'ability %d est montee SANS le trait -- le temoin est DEGENERE." % ABILITY_ID)
        return 1
    print("   OK : %d monte SSI le trait est pose (dict Trait +0x0 confronte LIVE)." % ABILITY_ID)

    # La GEOMETRIE decide la branche : melee = cible ADJACENTE ; ranged = >= 1 ennemi adjacent
    # (ce qui ARME `HasAdjacentEnemies`) ET cible a distance >= 2 (ce qui rend le coup NON-melee).
    def eligible(p):
        return (p["n_adj"] >= 1 and p["d_cible"] == 1) if volet["nature"] == "melee" \
            else (p["n_adj"] >= 1 and p["d_cible"] >= 2)

    par_cle_w = {(p["att_pos"], p["tgt"]): p for p in m_w["plans"] if eligible(p)}
    par_cle_o = {(p["att_pos"], p["tgt"]): p for p in m_o["plans"] if eligible(p)}
    communs = sorted(set(par_cle_w) & set(par_cle_o))
    print("2-3. PREDICTION d'attaque NORMALE %s : %d couple(s) (tuile, cible) ELIGIBLE(S) et commun(s)"
          % (volet["nature"], len(communs)))
    if not communs:
        print("   NON CONFRONTE : aucun couple (tuile candidate, cible) ne realise le regime %s "
              "(n_adj>=1 et d_cible%s). Plans AVEC=%r" 
              % (volet["nature"], "==1" if volet["nature"] == "melee" else ">=2",
                 [(p["att_pos"], p["tgt"], p["d_cible"], p["n_adj"]) for p in m_w["plans"]][:8]))
        return 2
    attendu = 1.0 + volet["pct"] / 100.0
    for cle in communs:
        w, o = par_cle_w[cle], par_cle_o[cle]
        print("   @%s vs u%s (d=%d, ennemis ring-1=%d)  natif SANS=%s AVEC=%s | port SANS=%s AVEC=%s"
              % (cle[0], cle[1], w["d_cible"], w["n_adj"], o["oracle"], w["oracle"],
                 o["port"], w["port"]))
        if o["oracle"] == w["oracle"]:
            print("      ECHEC : le natif rend LA MEME CHOSE avec et sans le trait -- soit la greffe "
                  "n'a pas mordu, soit la mecanique ne tire pas dans ce regime. Un accord "
                  "port/natif y serait un accord en regime DEGENERE.")
            rc = 1
            continue
        for i, quoi in ((0, "min"), (1, "max")):
            base, avec = o["oracle"][i], w["oracle"][i]
            if not base:
                continue
            ratio = avec / base
            ok = abs(ratio - attendu) <= 0.01
            print("      natif dmg%s : %s -> %s   ratio=%.4f  attendu=%.2f  %s"
                  % (quoi, base, avec, ratio, attendu, "OK" if ok else "ECART"))
            if not ok:
                rc = 1
        for etiq, s in (("SANS", o), ("AVEC", w)):
            if s["pred_opt"]:
                print("      %s : oracle `predOptimistic` -> non exploitable, pas de verdict." % etiq)
                continue
            ecart = max(abs(s["oracle"][0] - s["port"][0]), abs(s["oracle"][1] - s["port"][1]))
            print("      port %s : oracle=%s port=%s ecart=%d %s"
                  % (etiq, s["oracle"], s["port"], ecart, "OK" if ecart <= 3 else "DIVERGENCE"))
            if ecart > 3:
                rc = 1
    return rc


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--volet", choices=tuple(VOLETS) + ("tous",), default="tous")
    ap.add_argument("--keep", action="store_true")
    a = ap.parse_args(argv)
    volets = tuple(VOLETS) if a.volet == "tous" else (a.volet,)
    codes = {v: _joue(v, a.keep) for v in volets}
    print("\nVERDICT par volet : %s" % codes)
    if any(c == 1 for c in codes.values()):
        return 1
    return 2 if any(c == 2 for c in codes.values()) else 0


if __name__ == "__main__":
    raise SystemExit(main())


