#!/usr/bin/env python
"""Probe #1015-r1 -- le trait `BeastSnagga` CONFRONTE LIVE, avec TEMOIN NON-NUL des DEUX cotes.

CE QU'IL MESURE, et contre quoi :

  1. KIT    -- l'ability `TriggeredAbilityType.BeastSnagga` (0x43c = 1084) est-elle MONTEE sur le
               porteur quand on force le trait ? Canal `unitAbilityStates` (l'`AbilitiesComponent`
               REEL), jamais le gameconfig. C'est la confrontation LIVE de la paire `cle 0x406 ->
               valeur 0x43c` du dict `idun.Idun.Source.Shared.Battle.StaticBattleRules.
               StaticBattleRules.Trait$$.cctor` (+0x0), LUE au decompile.

  2. POSE   -- les DEUX effets que pose `IdunBattleLogic.Entities.Abilities.Triggered.Loki.
               BeastSnaggaAbility$$CreateBehaviour` sont-ils sur le porteur ? `BeastSnagga_ExtraDmg`
               (0x438 = 1080) par `AddEffect`, `BeastSnagga_ExtraBlock` (0x439 = 1081) par
               `AddExtraBlockEffectToOwner`. Canal `decisionView.effects` (l'ECS, pas le port).

  3. NATIF  -- le natif applique-t-il le bonus, et de combien ? DEUX runners, MEME seed, MEME board,
               MEMES unites, MEMES stats : le seul ECART est le trait du porteur. On compare la
               PREDICTION NATIVE (`decisionView.attackPlans`, `ranked[].dmgMin/dmgMax`) de la MEME
               attaque normale depuis la MEME tuile candidate. Le runner SANS trait EST le temoin
               non-nul : sans lui, un accord ne prouverait rien (regime degenere).

  4. PORT   -- le port rend-il la MEME chose que le natif, DANS LES DEUX REGIMES ?

LE SECOND TEMOIN, qui est le vrai discriminant de CE trait. Le gate natif n'est pas
« le porteur a le trait » mais `HasTrait(CIBLE, Vehicle) | HasTrait(CIBLE, BigTarget)`. Un probe qui
n'aurait qu'une cible `BigTarget` mesurerait « le trait fait quelque chose », pas « il fait CE
quelque chose-la ». Les deux cibles sont donc montees dans le MEME runner :

  * `astraCreed`    -> `Traits=["Hero","BigTarget"]`  : le `op_BitwiseOr` est VRAI  -> +20 % attendu
  * `adeptCanoness` -> `Traits=["Hero"]`              : il est FAUX                 -> +0 % attendu

et le probe exige les DEUX : un +20 % sur la premiere ET une EGALITE STRICTE sur la seconde. Un port
qui aurait oublie le gate de trait passerait le premier cran et echouerait au second.

MONTAGE. Le seul porteur du kit est `tauNpcFarsight` (`units.npc`), donc hors pool. Le trait se
GREFFE par `rl_duel build --unit-stat "<vis>:Traits=[...]"` -- greffe LEGITIME au sens de
`case-92` §5bis : `BeastSnagga_ExtraDmgEffect$$CreateDamageModifier` ne lit NI les stats NI les
traits du CASTER (ses trois noeuds sont `get_OwnerIsCaster`, `IsMeleeAttack` et deux `HasTrait` sur
la CIBLE), et son amount est une CONSTANTE de config. Le porteur greffe est `astraBullgryn` : HERO
du pool, arme MELEE unique (Physical, 4 coups) -- `IsMeleeAttack` est donc vrai par construction,
sans dependre de la geometrie.

`Movement=12` est pose sur les DEUX runners : il ne touche aucun canal de degat et met les tuiles
d'attaque a portee du premier tour.

⚠ CE QUE CE PROBE NE COUVRE PAS, et il le DIT : l'axe BLOCK (`BeastSnagga_ExtraBlock`, +10 % de
chance de bloquer 20 % des PV MAX) n'est confronte QU'EN POSE (cran 2). Sa VALEUR n'entre ni dans
`dmgMin/dmgMax` (le block est un scenario separe, `DamagePredictionResult` list[0]@0x50) ni dans le
scalaire `GetStat(7/8)` -- par construction, puisque c'est une entree de `GetMultiValueStat(7)`.

Usage (depuis scripts/python, session Frida chaude) :
    python probe_1015r1_beast_snagga.py
    python probe_1015r1_beast_snagga.py --keep      # ne pas disposer les runners

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
from engine.playbook import scene as SC                                # noqa: E402
from engine.playbook import prediction                                 # noqa: E402
from engine.playbook.scene import Scene                                # noqa: E402
from engine.runner import snapshot as _snapshot                        # noqa: E402
from engine.entities.effect_type import EffectType                     # noqa: E402
from engine.entities.traits.unit_trait import UnitTrait                # noqa: E402
from engine.entities.triggered_ability_type import TriggeredAbilityType  # noqa: E402

BOARD = "MC1_67"
SEED = 777
TRAIT = UnitTrait.BeastSnagga.name
PORTEUR = "astraBullgryn"
#: Traits du porteur SANS le trait mesure. `BigTarget` fait partie de son kit reel -- on le garde
#: pour que le seul ECART entre les deux runners soit `BeastSnagga` (il monte l'ability 1030, qui
#: apparait donc dans les DEUX kits et sert de temoin interne au cran 1).
TRAITS_PORTEUR = [UnitTrait.Hero.name, UnitTrait.BigTarget.name]

#: {unitId de la cible: (traits forces, bonus attendu en %)}. Les DEUX branches du gate natif.
CIBLES = {
    "astraCreed":    ([UnitTrait.Hero.name, UnitTrait.BigTarget.name], 20),
    "adeptCanoness": ([UnitTrait.Hero.name], 0),
}

ABILITY_ID = int(TriggeredAbilityType.BeastSnagga)              # 0x43c = 1084
EFFET_DMG = int(EffectType.BeastSnagga_ExtraDmg)                # 0x438 = 1080
EFFET_BLOCK = int(EffectType.BeastSnagga_ExtraBlock)            # 0x439 = 1081


def _res(r):
    return r.get("result") if isinstance(r, dict) and "result" in r else r


def _sf(nom: str) -> str:
    """State-file ABSOLU, unique par PID, HORS `data/` (que `rl_duel --state-file` refuse, #349)."""
    return os.path.join(tempfile.gettempdir(), "bsnag_%d_%s.json" % (os.getpid(), nom))


def _build(state_file: str, with_trait: bool) -> int:
    traits = list(TRAITS_PORTEUR) + ([TRAIT] if with_trait else [])
    args = ["build", "--seed", str(SEED), "--board", BOARD,
            "--p-units", PORTEUR, "--a-units", ",".join(CIBLES),
            "--state-file", state_file,
            "--unit-stat", "%s:Traits=%s" % (PORTEUR, str(traits).replace("'", '"')),
            "--unit-stat", "%s:Movement=12" % PORTEUR]
    for cible, (tr, _pct) in CIBLES.items():
        args += ["--unit-stat", "%s:Traits=%s" % (cible, str(tr).replace("'", '"'))]
    R.main(args)
    return int(R._read_state(Path(state_file))["runnerId"])


def _effets_du_porteur(dec, porteur_ids) -> set:
    """Les `effectType` portes par le porteur, LUS dans `decisionView.effects` (l'ECS).

    La forme du noeud varie selon le hook (`effects` a la racine, ou par unite) : on accepte les
    deux et on rend l'UNION, plutot que de supposer une seule."""
    out = set()
    for e in (dec.get("effects") or ()):
        if not isinstance(e, dict):
            continue
        tgt = e.get("targetId", e.get("unitId"))
        if tgt in porteur_ids:
            t = e.get("effectType", e.get("type"))
            if t is not None:
                out.add(int(t))
    for u in (dec.get("units") or ()):
        if u.get("id") in porteur_ids:
            for e in (u.get("effects") or ()):
                t = e.get("effectType", e.get("type")) if isinstance(e, dict) else None
                if t is not None:
                    out.add(int(t))
    return out


def _mesure(sid, rid: int) -> dict:
    """{`kit`, `effets`, `plans`} : le kit DECLENCHE du porteur, ses effets ECS, et par plan
    d'attaque NORMALE le couple (oracle natif, prediction du port) a la MEME tuile candidate."""
    def rpc(m, body=None, t=90):
        return _res(R._rpc(sid, m, [body] if body is not None else [], timeout=t))

    st = rpc("unitAbilityStates", {"runnerId": rid})
    kit = {}
    for u in (st.get("units") or ()):
        if u.get("configId") == PORTEUR:
            kit[int(u["entityId"])] = sorted(int(t["raw"][0]) for t in (u.get("triggered") or ()))

    predictor = SC.build_predictor(lambda m, b, t: rpc(m, b, t), rid)
    dec = rpc("decisionView", _snapshot.decision_view_seed_body(rid, maxRank=12, allAbilities=True))
    sctx = SC.step_context(predictor, dec)
    scene = Scene.from_predictor_sctx(predictor, sctx, None)
    pos_by_id = sctx["pos_by_id"]
    cible_de = {u["id"]: u.get("configId") or u.get("visualId")
                for u in (dec.get("units") or ())}
    #: PV COURANTS par entite -- ils bornent `accurate_health_damage` (le natif clampe la borne
    #: haute a ce que la cible peut ENCORE perdre). Un ratio pris sur une borne CLAMPEE ne mesure
    #: plus le bonus : cf. `_ratio_decidable`.
    hp_de = {u["id"]: u.get("hp") for u in (dec.get("units") or ())}
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
                if att_pos is None:
                    continue
                pred = prediction.make_normal_attack_predictions(scene, a_id, t_id, att_pos)
                res = pred.prediction.accurate_health_damage
                plans.append({"att": a_id, "tgt": t_id, "cible": cible_de.get(t_id),
                              "att_pos": tuple(att_pos), "hp_tgt": hp_de.get(t_id),
                              "oracle": (r0.get("dmgMin"), r0.get("dmgMax")),
                              "port": (res.min, res.max)})
    return {"kit": kit, "effets": _effets_du_porteur(dec, set(kit)), "plans": plans}


def _joue(keep: bool) -> int:
    sid = R._resolve_session()
    sf_w, sf_o = _sf("with"), _sf("without")
    rid_w = _build(sf_w, True)
    rid_o = _build(sf_o, False)
    print("\n===== BeastSnagga -- porteur=%s cibles=%s | runners AVEC=%s SANS=%s"
          % (PORTEUR, list(CIBLES), rid_w, rid_o))
    try:
        m_w, m_o = _mesure(sid, rid_w), _mesure(sid, rid_o)
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
              "`Trait$$GetTriggeredAbility` ne mappe pas ce trait, ou la greffe n'a pas mordu."
              % ABILITY_ID)
        rc = 1
    elif ABILITY_ID in kit_o:
        print("   ECHEC : l'ability %d est montee SANS le trait -- le temoin est DEGENERE."
              % ABILITY_ID)
        rc = 1
    else:
        print("   OK : %d monte SSI le trait est pose (dict `Trait +0x0` confronte LIVE)."
              % ABILITY_ID)

    print("2. EFFETS ECS du porteur (`decisionView.effects`) : AVEC=%s SANS=%s"
          % (sorted(m_w["effets"]), sorted(m_o["effets"])))
    for eid, nom in ((EFFET_DMG, "BeastSnagga_ExtraDmg"), (EFFET_BLOCK, "BeastSnagga_ExtraBlock")):
        if eid in m_w["effets"] and eid not in m_o["effets"]:
            print("   OK : %d (%s) pose SSI le trait est pose." % (eid, nom))
        elif eid in m_w["effets"]:
            print("   ECHEC : %d (%s) present DANS LES DEUX -- temoin degenere." % (eid, nom))
            rc = 1
        else:
            print("   NON CONFRONTE : %d (%s) absent de `decisionView.effects` du porteur. Le "
                  "capteur ne publie pas cet effet a ce niveau -- ce n'est PAS une preuve d'absence."
                  % (eid, nom))

    par_cle_w = {(p["att_pos"], p["tgt"]): p for p in m_w["plans"]}
    par_cle_o = {(p["att_pos"], p["tgt"]): p for p in m_o["plans"]}
    communs = sorted(set(par_cle_w) & set(par_cle_o), key=lambda k: (str(k[0]), k[1]))
    print("3-4. PREDICTION d'attaque NORMALE : %d couple(s) (tuile, cible) commun(s)" % len(communs))
    if not communs:
        print("   NON CONFRONTE : aucun couple (tuile candidate, cible) commun aux deux runners.")
        return 2
    vus = {}
    for cle in communs:
        w, o = par_cle_w[cle], par_cle_o[cle]
        cible = w["cible"]
        attendu = CIBLES.get(cible, (None, None))[1]
        if attendu is None:
            continue
        vus.setdefault(cible, 0)
        print("   @%s vs %s (attendu %+d %%)  natif SANS=%s AVEC=%s | port SANS=%s AVEC=%s"
              % (cle[0], cible, attendu, o["oracle"], w["oracle"], o["port"], w["port"]))
        # a. NATIF -- le trait mord (ou pas) DANS LE SENS ATTENDU.
        if attendu == 0:
            if o["oracle"] != w["oracle"]:
                print("      ECHEC : le natif CHANGE alors que la cible n'est ni BigTarget ni "
                      "Vehicle -- le gate `HasTrait(cible, ...)` ne serait pas celui qu'on a lu.")
                rc = 1
                continue
        else:
            if o["oracle"] == w["oracle"]:
                print("      ECHEC : le natif rend LA MEME CHOSE avec et sans le trait -- soit la "
                      "greffe n'a pas mordu, soit la mecanique ne tire pas dans ce regime. Un "
                      "accord port/natif y serait un accord en regime DEGENERE.")
                rc = 1
                continue
            n_dec = 0
            for i, quoi in ((0, "min"), (1, "max")):
                base, avec = o["oracle"][i], w["oracle"][i]
                if not base:
                    continue
                # ⚠ LE CLAMP AUX PV REND LE RATIO INDECIDABLE, et le taire fabriquerait un ECHEC.
                # `accurate_health_damage` est borne par ce que la cible peut ENCORE perdre :
                # MESURE du premier run, `astraCreed` a 9037 PV -> la borne MAX passe de 8420 a
                # 9037 (et non a 10104 = 8420 x 1,2), soit un ratio apparent de 1,0733 alors que le
                # bonus est bien de +20 % (la borne MIN, elle, rend 3604 -> 4324 = 1,1998). On
                # ECARTE la borne clampee EN LE DISANT, jamais en la lissant.
                if w["hp_tgt"] is not None and avec >= int(w["hp_tgt"]):
                    print("      (borne %s ECARTEE : natif AVEC=%d atteint les PV de la cible (%s) "
                          "-> clampee, ratio indecidable)" % (quoi, avec, w["hp_tgt"]))
                    continue
                n_dec += 1
                ratio = avec / base
                cible_ratio = 1.0 + attendu / 100.0
                if abs(ratio - cible_ratio) > 0.02:
                    print("      ECHEC : ratio natif %s = %.4f, attendu %.2f (%+d %%)."
                          % (quoi, ratio, cible_ratio, attendu))
                    rc = 1
            if n_dec == 0:
                print("      NON CONFRONTE : les DEUX bornes sont clampees aux PV -- ce couple ne "
                      "mesure aucun ratio. Il reste utile pour l'accord port/natif ci-dessous.")
                rc = max(rc, 2)
        # b. PORT -- il rend la meme chose que le natif, DANS LES DEUX REGIMES.
        for nom, m in (("SANS", o), ("AVEC", w)):
            if tuple(m["oracle"]) != tuple(m["port"]):
                print("      ECHEC (port, regime %s) : natif=%s port=%s"
                      % (nom, m["oracle"], m["port"]))
                rc = 1
        vus[cible] += 1

    manquantes = [c for c in CIBLES if not vus.get(c)]
    if manquantes:
        print("   NON CONFRONTE : aucune tuile commune contre %s -- le second temoin manque, donc "
              "le gate de trait n'est PAS mesure." % manquantes)
        rc = max(rc, 2)
    print("\nVERDICT : %s" % ("OK" if rc == 0 else ("NON CONFRONTE" if rc == 2 else "ECHEC")))
    return rc


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Confrontation live du trait BeastSnagga (#1015-r1)")
    ap.add_argument("--keep", action="store_true", help="ne pas disposer les runners")
    a = ap.parse_args(argv)
    return _joue(a.keep)


if __name__ == "__main__":
    raise SystemExit(main())
