"""#549-r1 -- le `tgt_id` threade cote PREDICTION, confronte a `aiPlaybookPredict`.

CE QUE #549 A LAISSE OUVERT
---------------------------
`#549` a threade `tgt_id` dans l'`att_ctx` des DEUX faces -- combat (`damage_model.attacker_modifiers`)
ET prediction (`playbook/prediction/normal_attack.py`, `playbook/prediction/abilities.py`) -- parce
que le gate `AreEqual(Target@DSLSelectors+0x60, BondedEntityFromEffect(Effect@0x38))` de
`IdunBattle.Entities.Effects.Loki.HolyDuel_ExtraDmgEffect$$CreateEffectDamageBonusForAttack` compare
deux ENTITES. La face COMBAT est confrontee (degat du cast bit-exact, 6140). La face PREDICTION ne
l'etait PAS : avant le threading, elle ignorait SILENCIEUSEMENT le `+extraDmg` (1092) -- degradation
RESTRICTIVE, mais fork prediction/combat, et c'est exactement le regime ou une prediction
SOUS-ESTIME une ability que la DECISION vient de choisir.

LE CRITERE, ENONCE AVANT LE MONTAGE
------------------------------------
Oracle = `aiPlaybookPredict` (= `<Ability>Playbook$$MakeDamagePredictions`, ce que le scorer de
DECISION consomme reellement -- PAS le preview `aiPredict`). Port =
`engine.playbook.prediction.make_normal_attack_predictions` sur la MEME Scene, la MEME tuile.

  * `avant` -- prediction de l'attaque NORMALE du champion sur sa future victime, AVANT le cast.
               Aucun duel : le gate est ferme des deux cotes. `port == natif`, et la
               CONTRE-EPREUVE `sans tgt_id` ne change RIEN. C'est le CONTROLE.
  * `duel`  -- MEME paire, APRES le cast de `1050 HolyDuel`. Le champion porte 1092, bonde a la
               victime : le gate se ferme, le `+extraDmg` entre. `port == natif`, et la
               CONTRE-EPREUVE `sans tgt_id` doit DIVERGER (elle rejoue le port d'AVANT #549).

Sans le bras `avant`, une morsure sur `duel` ne dirait pas si elle vient du duel ou d'un effet de
bord du threading. Sans le bras `duel`, le `tgt_id` reste non confronte -- c'est-a-dire #549-r1.

ASCII only (cp1252). Usage (depuis scripts/python, session Frida chaude) :
    python probe_549r1_holy_duel_prediction.py [--garder]
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

PYDIR = Path(__file__).resolve().parent
sys.path.insert(0, str(PYDIR))

import probe_112_darkangels as PR                                    # noqa: E402
import probe_462_r4b_r1_r1_r1_r1_b_bond_range as B                   # noqa: E402
from probe_267_predictor_traits import _scene_de                     # noqa: E402
from predict_sweep import live_main_event as oracle                  # noqa: E402
from rl_collect_batch import _resolve_session                        # noqa: E402

HOLY_DUEL = 1050
HOLY_DUEL_EXTRA_DMG = 1092


def _normal_ability_id(dv, uid):
    """`UnitExtensions$$GetNormalAttackType(unit)` -- l'attaque normale CONCRETE, per-unit (jamais
    l'abstrait 17, cf. `project_ability_normal_attack_concrete`)."""
    u = next((x for x in (dv.get("units") or []) if x.get("id") == uid), None)
    for a in ((u or {}).get("abilities") or []):
        if a.get("kind") == "normal":
            return a.get("id")
    return None


def _port_pred(sid, rid, att, tgt, sans_tgt_id=False):
    """La prediction du PORT pour (att -> tgt) depuis la tuile COURANTE de `att`.

    `sans_tgt_id` rejoue le port d'AVANT #549 : la cle `tgt_id` est RETIREE de l'`att_ctx` juste
    avant que les modificateurs ATTAQUANT ne soient calcules. C'est le seul cran retire -- tout le
    reste du chemin est identique, donc une divergence lui est ATTRIBUABLE."""
    from engine.playbook import prediction
    # ⚠ On substitue le binding LOCAL du module consommateur, PAS celui du module qui DEFINIT la
    # fonction : `normal_attack.py` fait `from ._shared import *` (forme A), donc patcher
    # `engine.entities.effects` NE MORDRAIT PAS -- c'est la faute mesuree de #484/#429-r1.
    import engine.playbook.prediction.normal_attack as NA
    scene, _sctx, _dv = _scene_de(sid, rid)
    if scene is None:
        return None
    pos = scene.pos(att)
    if not sans_tgt_id:
        pe = prediction.make_normal_attack_predictions(scene, att, tgt, pos)
    else:
        vrai = NA.calculate_attacker_modifiers_for_prediction

        def _ampute(*a, **kw):
            ctx = dict(kw.get("att_ctx") or {})
            ctx.pop("tgt_id", None)
            kw["att_ctx"] = ctx
            return vrai(*a, **kw)

        NA.calculate_attacker_modifiers_for_prediction = _ampute
        try:
            pe = prediction.make_normal_attack_predictions(scene, att, tgt, pos)
        finally:
            NA.calculate_attacker_modifiers_for_prediction = vrai
    if pe is None:
        return None
    r = pe.prediction.accurate_health_damage
    return {"min": int(r.min), "max": int(r.max)}


def _mesure(tag, sid, rid, att, tgt, ab):
    nat = oracle(sid, rid, att, tgt, ab)
    port = _port_pred(sid, rid, att, tgt)
    sans = _port_pred(sid, rid, att, tgt, sans_tgt_id=True)
    ok = (nat and "min" in nat and port is not None
          and (nat["min"], nat["max"]) == (port["min"], port["max"]))
    print("[%s] u%s -> u%s (ab=%s)  NATIF=%s  PORT=%s  PORT_SANS_tgt_id=%s  -> %s"
          % (tag, att, tgt, ab, nat, port, sans, "OK" if ok else "DESACCORD"))
    return {"tag": tag, "natif": nat, "port": port, "sans_tgt_id": sans, "ok": bool(ok)}


def campagne(sid, garder=False):
    """FOYER UNIQUE du montage et des criteres : `main` et la garde
    `tests/engine/runner/test_549_holy_duel_live.py` passent tous deux par ici."""
    ctx = B.build_montage(sid, mode="proche", taunter=B.HOLY_DUELIST)
    champ, victim = ctx["taunter"], ctx["victim"]
    recs = []
    try:
        dv0 = PR.rpc(sid, "decisionView", {"runnerId": ctx["rid"], "maxRank": 1,
                                           "allAbilities": True}, 90)
        ab = _normal_ability_id(dv0, champ)
        if ab is None:
            raise SystemExit("[549r1] pas d'attaque NORMALE sur le champion -- rien a predire")
        print("[549r1] runner=%s  champion=u%s  victime=u%s  attaque normale=%s"
              % (ctx["rid"], champ, victim, ab))
        recs.append(_mesure("avant", sid, ctx["rid"], champ, victim, ab))

        B.cast_taunt(ctx, ability=HOLY_DUEL)
        dv1 = PR.rpc(sid, "decisionView", {"runnerId": ctx["rid"], "maxRank": 1,
                                           "allAbilities": True}, 90)
        fam = B.effects_of(dv1, champ)
        if not any(t[0] == HOLY_DUEL_EXTRA_DMG for t in fam):
            raise SystemExit("[549r1] le champion ne porte PAS 1092 apres le cast (%r) -- "
                             "montage sterile" % (fam,))
        recs.append(_mesure("duel", sid, ctx["rid"], champ, victim, ab))
    finally:
        if not garder:
            PR.dispose(sid, ctx["rid"])
    return recs


def verdict(recs) -> bool:
    """`True` ssi les DEUX bras concordent, que la contre-epreuve MORD sur `duel`, et qu'elle est
    INERTE sur `avant` (sinon la morsure ne serait pas attribuable au duel)."""
    if len(recs) < 2:
        print("[549r1] montage sterile : %d bras sur 2" % len(recs))
        return False
    ok = all(rec["ok"] for rec in recs)
    av = next(r for r in recs if r["tag"] == "avant")
    du = next(r for r in recs if r["tag"] == "duel")
    inerte = av["sans_tgt_id"] == av["port"]
    mord = du["sans_tgt_id"] != du["port"]
    print("[549r1] contre-epreuve `sans tgt_id` : sur `avant` %s ; sur `duel` %s"
          % ("INERTE (attendu)" if inerte else "MORD -- elle change quelque chose HORS duel",
             "MORD (%s au lieu de %s)" % (du["sans_tgt_id"], du["port"]) if mord
             else "NON DISCRIMINANTE -- le `+extraDmg` n'entre pas par cette cle"))
    return ok and inerte and mord


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="#549-r1 -- prediction du duel confrontee")
    ap.add_argument("--garder", action="store_true")
    a = ap.parse_args(argv)
    sid = _resolve_session()
    recs = campagne(sid, garder=a.garder)
    ok = verdict(recs)
    print("[549r1] VERDICT : %s" % ("OK" if ok else "DESACCORD"))
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
