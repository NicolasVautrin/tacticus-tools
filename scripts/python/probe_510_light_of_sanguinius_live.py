#!/usr/bin/env python
"""probe #510 -- CONFRONT LIVE de `1177 LightOfSanguinius` (Dante, `bloodDante`), les DEUX faces.

ARTEFACTS NATIFS CONFRONTES
---------------------------
  * `IdunBattleLogic.Entities.Abilities.Active.LightOfSanguiniusAbility$$ExecuteBehaviour`
        Execute( (AddEffect(0x416 Infiltrate_UnitEffect, Owner, Direct(1) TOUR) & FlyUnit(Caster, T))
                 & IfAlive(Owner, AttackWithAttackDamage(Caster, Target, MinMaxDamage,
                                                         Melta, nrOfHits)
                                  & AddEffect(0x560 LightOfSanguinius,
                                              Target + NonSteppableOrObjectUnits(Enemies(
                                                  SurroundingUnits(Target, range_2))),
                                              TurnsFromRounds(nrOfRounds))) )
    avec T = First(SortTilesByUtility(Filter(CanAddUnit(AdjacentTiles(Target)),
                   NOT(AmountIsGreater(MinDistance(It, CasterTiles), range))), Caster, 7 = Tile), 1)
  * `IdunBattle.Entities.Effects.Loki.LightOfSanguinius_DamageReductionEffect$$CreateDamageModifier`
        ForPercentDecrease( get_OwnerIsCaster,
                            If( NOT(HealthPctIsBelowOrEqual(Target, ConfigConst(0x4f = healthPct))),
                                ConfigVar(0x46 = dmgReductionPct), Multiply(<idem>, Direct(2)) ) )

CE QUE CHAQUE ETAGE MESURE
--------------------------
  E1 CAST      -- les coups LIVE tagges `Active_Ability_Type == 1177` contre le replay OFFLINE du
                  port depuis le MEME etat et le MEME Mersenne Twister (`dumpRng`). Sans le calage
                  MT, `execute_ability_attack` SKIPPE le degat et on lirait un faux `0`.
                  On compare la SEQUENCE, pas seulement le total.
  E2 VOL       -- la tuile d'arrivee LIVE de Dante contre le collapse
                  `First(SortTilesByUtility(...))` du port.
  E3 AURA      -- l'ENSEMBLE des unites qui portent l'effet 1376 apres le cast, live contre port.
                  C'est le seul etage qui exerce `Target + NonSteppableOrObjectUnits(Enemies(
                  SurroundingUnits(...)))`.
  E4 DEBUFF    -- ORACLE NATIF `aiPlaybookPredict(<attaque normale concrete>)` invoque sur un ennemi
                  AFFECTE, contre la prediction PORTEE (`make_normal_attack_predictions`). Deux
                  cibles ne differant QUE par leurs PV (100 % / 40 %) : le natif doit rendre DEUX
                  facteurs distincts (-dmgReductionPct % et son DOUBLE), et un ennemi NON AFFECTE
                  sert de TEMOIN DE CONTRASTE (facteur 1,00) -- sans lui, un port plat passerait.

MONTAGE (positions DRIVEES, jamais subies)
------------------------------------------
`rl_duel build --board MC1_67 --place/--a-place` :
  * `bloodDante` a l'ecart, et DEUX punching-bags allies de MEME `Health` dont l'un a 40 % de PV
    (`--unit-stat`) : c'est l'unique curseur de l'etage E4 ;
  * un ennemi HUB entoure de deux voisins (l'aura doit les prendre) et un ennemi ISOLE, loin, qui
    reste NON AFFECTE (le temoin de E4).
Le masque de 1177 porte `TargetIsNotAdjacent` (bit 32) et `CasterHasNotMoved` : Dante ne doit NI
etre au contact de sa cible, NI avoir bouge. Les positions sont donc explicites.

Usage (depuis scripts/python, session Frida chaude ; le probe DISPOSE son runner) :
    python probe_510_light_of_sanguinius_live.py
    python probe_510_light_of_sanguinius_live.py --board MC1_67 --seed 510510 --keep

ASCII only (cp1252). exit 0 = les quatre etages concordent.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

import probe_112_darkangels as PR                                          # noqa: E402
import probe_226_hammer_foehammer as P226                                  # noqa: E402
import probe_27_custom_utility_inventory as INV                            # noqa: E402

from engine.entities.active_ability_type import ActiveAbilityType          # noqa: E402
from engine.entities.effect_type import EffectType                         # noqa: E402
from engine.runner.abilities.bloodangels import LightOfSanguiniusAbility   # noqa: E402

LOGS = HERE.parents[1] / "logs"
LOS = int(ActiveAbilityType.LightOfSanguinius)          # 1177
LOS_EFFECT = int(EffectType.LightOfSanguinius)          # 0x560 = 1376
PORTEUR = "bloodDante"
BAG_FULL = "bloodSanguinary"        # punching-bag allie a 100 % PV
BAG_HURT = "bloodIntercessor"       # punching-bag allie a 40 % PV -- l'unique curseur de E4
HUB = "necroOverlord"               # la cible du cast
NEAR1 = "necroWarden"               # voisin du hub -> pris par l'aura
FAR = "necroDestroyer"              # ennemi ISOLE (hors ring) -> NON affecte, temoin de contraste
HEALTH = 20000                      # meme MAX pour les deux bags : un seul curseur, les PV RESTANTS


def _r(sid, m, b, t=90):
    """`probe_112_darkangels.rpc` -- timeout en SECONDES (celui d'`INV.rpc` est en MILLISECONDES,
    et un 150 y devient un timeout serveur, donc un HTTP 500)."""
    return PR.rpc(sid, m, b, t)


def _run(args) -> int:
    return subprocess.run([sys.executable, "rl_duel.py"] + args, cwd=str(HERE),
                          stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                          check=False).returncode


def _units_by_visual(dv):
    out = {}
    for u in (dv.get("units") or []):
        out.setdefault(u.get("visualId"), []).append(u)
    return out


def _carriers(dv, effect_type):
    """Ids des unites qui portent `effect_type` -- `decisionView.effects` est le GROUND TRUTH #100."""
    return sorted(u["id"] for u in (dv.get("units") or [])
                  if any(e.get("effectType") == effect_type for e in (u.get("effects") or [])))


def _pos(dv, uid):
    u = next((x for x in (dv.get("units") or []) if x.get("id") == uid), None)
    p = (u or {}).get("pos") or {}
    return (p.get("col"), p.get("row")) if p.get("col") is not None else None


def _normal_attack_id(dv, uid):
    """Id CONCRET de l'attaque normale (`kind == "normal"`), PER-UNITE (`NormalAttackType@0x28`)."""
    u = next((x for x in (dv.get("units") or []) if x.get("id") == uid), None)
    for a in ((u or {}).get("abilities") or []):
        if a.get("kind") == "normal":
            return a.get("id")
    return None


def _native_pred(sid, rid, cid, tid, ability):
    """ORACLE natif per-ability (`<X>Playbook$$MakeDamagePredictions` invoque en direct)."""
    r = _r(sid, "aiPlaybookPredict", {"runnerId": rid, "unitId": cid, "targetId": tid,
                                      "abilityType": int(ability)}, 150)
    evs = [e for e in (r.get("events") or []) if e.get("targetId") == tid]
    if not evs:
        return None
    return (int(evs[0].get("healthDmgMin") or 0), int(evs[0].get("healthDmgMax") or 0))


def _scene(sid, rid, cid):
    from engine import weights as W
    from engine.ai import context as AICTX
    from engine.playbook import scene as _sc
    rpc = (lambda m, b, t=90: _r(sid, m, b, t))                            # noqa: E731
    dv = _r(sid, "decisionView", {"runnerId": rid, "allAbilities": True}, 150)
    mov = _r(sid, "aiMovableTiles", {"runnerId": rid}, 60)
    mov_by_unit = {u.get("unitId"): u for u in (mov.get("units") or [])}
    pred = _sc.build_predictor(rpc, rid)
    if pred is None:
        raise RuntimeError("build_predictor KO (combatSnapshot indisponible)")
    ctx = AICTX.build(rpc, rid, dv, mov_by_unit, cid, W.load(), pred)
    mp = ctx.me.get("pos") or {}
    return ctx.scene, (mp.get("col"), mp.get("row"))


def _ported_normal_pred(scene, cid, tid, here):
    from engine.playbook.prediction.normal_attack import make_normal_attack_predictions
    ev = make_normal_attack_predictions(scene, cid, tid, here)
    if ev is None:
        return None
    r = ev.prediction.raw_health_damage
    return (int(r.min), int(r.max))


def _parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(description="#510 : confront live de 1177 LightOfSanguinius")
    ap.add_argument("--board", default="MC1_67")
    ap.add_argument("--seed", type=int, default=510510)
    ap.add_argument("--state-file", default="rs_510_los_live.json")
    ap.add_argument("--dante", default="0,0")
    ap.add_argument("--bag-full", default="2,2")
    ap.add_argument("--bag-hurt", default="2,5")
    ap.add_argument("--hub", default="3,3")
    ap.add_argument("--near1", default="3,4")
    ap.add_argument("--far", default="1,6")
    ap.add_argument("--keep", action="store_true")
    return ap


def mesure(a) -> "dict | None":
    """FOYER UNIQUE de la mesure : monte le runner, joue les six etages, rend le dict de verdicts
    (`{libelle: bool}`) ou `None` si le MONTAGE n'a pas abouti (build KO, porteur absent, cible non
    legale). Le test commite l'appelle -- il ne duplique NI le montage NI les criteres.
    `None` = PAS MESURE, ce qui n'est pas un verdict sur le port."""
    state_file = LOGS / a.state_file
    LOGS.mkdir(parents=True, exist_ok=True)
    rc = _run(["build", "--seed", str(a.seed), "--board", a.board, "--rank", "17",
               "--p-units", ",".join([PORTEUR, BAG_FULL, BAG_HURT]),
               "--a-units", ",".join([HUB, NEAR1, FAR]),
               "--place", "%s:%s" % (PORTEUR, a.dante),
               "--place", "%s:%s" % (BAG_FULL, a.bag_full),
               "--place", "%s:%s" % (BAG_HURT, a.bag_hurt),
               "--a-place", "%s:%s" % (HUB, a.hub),
               "--a-place", "%s:%s" % (NEAR1, a.near1),
               "--a-place", "%s:%s" % (FAR, a.far),
               "--unit-stat", "%s:Health=%d,RemainingHealth=%d" % (BAG_FULL, HEALTH, HEALTH),
               "--unit-stat", "%s:Health=%d,RemainingHealth=%d" % (BAG_HURT, HEALTH,
                                                                   int(HEALTH * 0.4)),
               "--state-file", str(state_file)])
    if not state_file.exists():
        print("[510] PAS MESURE : build KO (rc=%d, state-file absent)" % rc)
        return None
    rid = int(json.loads(state_file.read_text(encoding="utf-8"))["runnerId"])
    sid = INV._session_id()

    verdicts = {}
    try:
        dv = _r(sid, "decisionView", {"runnerId": rid, "allAbilities": True}, 150)
        bv = _units_by_visual(dv)
        for vid in (PORTEUR, BAG_FULL, BAG_HURT, HUB, FAR):
            if not bv.get(vid):
                print("[510] PAS MESURE : %s absent du montage" % vid)
                return None
        dante = bv[PORTEUR][0]["id"]
        hub = bv[HUB][0]["id"]
        far = bv[FAR][0]["id"]
        bag_full = bv[BAG_FULL][0]["id"]
        bag_hurt = bv[BAG_HURT][0]["id"]

        legal = PR.legal_from_here(sid, rid, dante, LOS)
        print("[510] runner=%d board=%s seed=%d | dante=u%d hub=u%d far=u%d "
              "bagFull=u%d bagHurt=u%d" % (rid, a.board, a.seed, dante, hub, far,
                                           bag_full, bag_hurt))
        print("      positions : dante=%s hub=%s far=%s | cibles LEGALES natives = %s"
              % (_pos(dv, dante), _pos(dv, hub), _pos(dv, far), sorted(legal)))
        if hub not in legal:
            print("[510] PAS MESURE : le HUB n'est pas une cible legale du natif depuis cette "
                  "position -- DEPLACER le montage (--dante/--hub), jamais conclure d'ici")
            return None

        # ---- BASELINE E4 : les predictions natives AVANT le cast (aucun ennemi n'est affecte).
        # Un couple n'est retenu que si le natif rend une prediction -- c'est ce qui rend le
        # montage auto-adaptatif au lieu de dependre d'une adjacence devinee.
        scene_pre, _ = _scene(sid, rid, dante)
        pre_pairs = {}
        for cid in (hub, far) + tuple(u["id"] for u in bv.get(NEAR1, [])):
            na = _normal_attack_id(dv, cid)
            cpos = _pos(dv, cid)
            if na is None or cpos is None:
                continue
            for tid in (bag_full, bag_hurt):
                nat = _native_pred(sid, rid, cid, tid, na)
                if nat is None or not nat[1]:
                    continue        # `(0, 0)` = cible HORS PORTEE du natif : pas un couple mesure
                pre_pairs.setdefault(cid, {})[tid] = (nat,
                                                      _ported_normal_pred(scene_pre, cid, tid, cpos))
        print("      couples (ennemi -> allie) a prediction native AVANT le cast : %s"
              % {c: sorted(v) for c, v in pre_pairs.items()})

        # ------------------------------------------------------------------ E1/E2/E3 : le CAST
        dec, ob, snap, bg, rngd = P226.capture(sid, rid)
        st = P226.offline_state(dec, ob, snap, bg, rngd)          # MT offline CALE sur le MT live
        hp_by_id = {u["squadId"]: u.get("hp") for u in (ob.get("units") or [])}
        before = _carriers(dv, LOS_EFFECT)
        r = PR.cast(sid, rid, dante, hub, LOS)
        live = {k: [int(h["amt"]) for h in v]
                for k, v in P226.live_hits(r.get("events"), LOS).items()}
        dv2 = _r(sid, "decisionView", {"runnerId": rid, "allAbilities": True}, 150)
        live_pos = _pos(dv2, dante)
        live_aura = _carriers(dv2, LOS_EFFECT)

        res = LightOfSanguiniusAbility().execute_behaviour(st, dante, hub)
        off = {hub: [int(x) for x in (((res or {}).get("main_attack") or {}).get("per_hit") or [])]}
        off_aura = sorted(d["target"] for d in ((res or {}).get("debuffed") or [])
                          if d.get("placed"))
        off_pos = (res or {}).get("flew_to") or (res or {}).get("dest")

        def clean_prefix(hits, hp):
            """Nb de coups NON CLAMPES par la mort : le tag `Amount` est le degat APPLIQUE."""
            run, n = 0, 0
            for x in hits:
                if hp is not None and run + x >= hp:
                    break
                run += x
                n += 1
            return n

        print("[510] E1 CAST -- coups tagges Active_Ability_Type=1177")
        for t in sorted(set(list(live) + list(off))):
            lh, oh = live.get(t, []), off.get(t, [])
            n = clean_prefix(lh, hp_by_id.get(t))
            print("      u%-4s live=%s" % (t, lh))
            print("            port=%s  (coups non clampes : %d)" % (oh, n))
        e1 = bool(live) and set(off) == set(live) and all(
            len(off[t]) == len(live[t])
            and off[t][:clean_prefix(live[t], hp_by_id.get(t))]
            == live[t][:clean_prefix(live[t], hp_by_id.get(t))]
            for t in live)
        verdicts["E1 cast bit-exact"] = e1

        print("[510] E2 VOL -- FlyUnit(Caster, First(SortTilesByUtility(...)))")
        print("      live=%s port=%s" % (live_pos, off_pos))
        verdicts["E2 tuile de vol"] = (live_pos is not None and tuple(live_pos) == tuple(off_pos))

        print("[510] E3 AURA -- porteurs de l'effet 1376 (avant=%s)" % before)
        print("      live=%s port=%s" % (live_aura, off_aura))
        verdicts["E3 porteurs de l'aura"] = (bool(live_aura) and live_aura == off_aura
                                             and far not in live_aura)
        scene_post, _ = _scene(sid, rid, dante)

        # ------------------------------------------------- E4-HORS-TOUR : LE PIEGE DE MESURE
        # `aiPlaybookPredict` est interroge ici sur un ennemi PENDANT LE TOUR DU JOUEUR. Cette
        # grille est imprimee parce qu'elle A INDUIT EN ERREUR : elle rend un facteur CONSTANT
        # (aucun doublement) quel que soit le regime de PV -- porteur sous le seuil COMME defenseur
        # sous le seuil. L'etage E4 ci-dessous, joue APRES `endturn` sur le MEME couple avec le MEME
        # effet actif, montre que c'est un artefact de CONTEXTE (l'unite interrogee n'est pas de
        # l'equipe ACTIVE), pas une propriete de l'ability. AUCUN verdict n'en est tire.
        # DECOMPOSITION PAR ETAGE de l'entree du gate `HealthPctIsBelowOrEqual` : les PV COURANTS et
        # MAX de CHAQUE unite, apres le cast. Sans eux, un facteur qui ne double pas est indiscernable
        # d'un montage ou aucun defenseur n'est reellement sous le seuil.
        ob2 = _r(sid, "observeBattle", {"runnerId": rid}, 60)
        hp2 = {u["squadId"]: (u.get("hp"), u.get("maxHp") or u.get("hpMax") or u.get("health"))
               for u in (ob2.get("units") or []) if u.get("squadId") is not None}
        print("      PV APRES le cast (gate `HealthPctIsBelowOrEqual`, seuil healthPct) : %s"
              % {("u%d" % k): v for k, v in sorted(hp2.items())})
        print("[510] E4-HORS-TOUR (piege) -- l'ennemi interroge n'est PAS de l'equipe active")
        print("      %-8s %-8s %-16s %-16s %s"
              % ("attaq.", "def.", "nat AVANT cast", "nat APRES cast", "facteur"))
        for cid in sorted(set(pre_pairs)):
            for tid in sorted(pre_pairs[cid]):
                na = _normal_attack_id(dv2, cid)
                if na is None:
                    continue
                nat_a = _native_pred(sid, rid, cid, tid, na)
                nat_b = pre_pairs[cid][tid][0]
                fac = (None if not (nat_b and nat_a and nat_b[1])
                       else round(nat_a[1] / float(nat_b[1]), 4))
                print("      u%-7d u%-7d %-16s %-16s %s"
                      % (cid, tid, str(nat_b), str(nat_a), fac))

        # ------------------------------------------ E4 / E5 : LE TOUR DE L'EQUIPE AFFECTEE
        # `endturn` -> `decisionView.ctrl` bascule sur l'adverse. C'est le SEUL regime ou le natif
        # rend une prediction a contexte COMPLET pour ces unites (cf. E4-HORS-TOUR ci-dessus).
        # E4 = oracle natif `aiPlaybookPredict` vs port, sur chaque couple.
        # E5 = attaque REELLE, rejouee OFFLINE depuis le MEME etat et le MEME MT, DEUX fois : une
        #      avec le doublement ARME, une avec le doublement DESARME. Une seule peut etre
        #      bit-exacte -- c'est ce qui tranche, jamais un scalaire ajuste.
        from engine.runner.components import HealthComponent as _HC
        from engine.runner.messages import AttackUnitMessage as _AUM
        from engine.runner.runner import Runner as _Runner
        import engine.entities.effects.loki.damage_reduction as _DR

        _vrai = _DR.LightOfSanguiniusDmgReductionEffect.create_effect_damage_bonus_for_attack

        def _sans_doublement(self, *a, **k):
            """Le MEME corps, prive du SEUL substrat du doublement (`tgt_hp`/`tgt_hp_max`) : la
            reduction de base reste, la branche `Multiply(pct, 2)` devient inatteignable."""
            k = dict(k)
            ctx = dict(k.get("att_ctx") or {})
            ctx.pop("tgt_hp", None)
            ctx.pop("tgt_hp_max", None)
            k["att_ctx"] = ctx
            return _vrai(self, *a, **k)

        def _rejoue(dec5, ob5, snap5, bg5, rng5, att, tid, hp_pre, patch):
            st = P226.offline_state(dec5, ob5, snap5, bg5, rng5)
            if patch:
                _DR.LightOfSanguiniusDmgReductionEffect \
                    .create_effect_damage_bonus_for_attack = _sans_doublement
            try:
                _Runner(st).install_default_handlers().apply(_AUM(att, tid))
            finally:
                _DR.LightOfSanguiniusDmgReductionEffect \
                    .create_effect_damage_bonus_for_attack = _vrai
            return int(hp_pre) - int(st.get_entity(tid).get_component(_HC).hp)

        PR.act(sid, rid, {"kind": "endturn"})
        dv3 = _r(sid, "decisionView", {"runnerId": rid, "allAbilities": True}, 150)
        ctrl = {u["id"] for u in (dv3.get("units") or []) if u.get("ctrl")}
        # Les porteurs sont RELUS ICI : la duree est `TurnsFromRounds(nrOfRounds)`, donc le passage
        # de tour peut en avoir retire. Reutiliser `live_aura` (capture AVANT `endturn`) ferait
        # compter comme AFFECTE une unite qui ne l'est plus -- et le port comme le natif seraient
        # d'accord dessus, ce qui rendrait le temoin FAUX au lieu de non-nul.
        aura_turn = _carriers(dv3, LOS_EFFECT)
        print("      porteurs de 1376 : avant endturn=%s | apres endturn=%s"
              % (live_aura, aura_turn))
        print("[510] E4 DEBUFF (equipe affectee ACTIVE) -- oracle natif vs port")
        print("      %-8s %-8s %-9s %-16s %-16s %s"
              % ("attaq.", "def.", "affecte", "natif", "port", "facteur / baseline"))
        scene_turn, _ = _scene(sid, rid, next(iter(sorted(ctrl))))
        lignes = []
        for cid in sorted(set(pre_pairs)):
            for tid in sorted(pre_pairs[cid]):
                na = _normal_attack_id(dv3, cid)
                cpos = _pos(dv3, cid)
                if na is None or cpos is None:
                    continue
                nat = _native_pred(sid, rid, cid, tid, na)
                port = _ported_normal_pred(scene_turn, cid, tid, cpos)
                base = pre_pairs[cid][tid][0]
                fac = (None if not (base and nat and base[1])
                       else round(nat[1] / float(base[1]), 4))
                lignes.append((cid, tid, nat, port, fac, cid in aura_turn))
                print("      u%-7d u%-7d %-9s %-16s %-16s %s"
                      % (cid, tid, "OUI" if cid in aura_turn else "non",
                         str(nat), str(port), fac))
        verdicts["E4 port == oracle natif"] = (bool(lignes)
                                               and all(l[2] == l[3] for l in lignes))
        aff = {(l[0], l[1]): l[4] for l in lignes if l[5]}
        tem = {(l[0], l[1]): l[4] for l in lignes if not l[5]}
        print("      facteurs (vs baseline pre-cast) -- AFFECTES %s | TEMOIN(S) %s" % (aff, tem))
        # TEMOIN NON NUL : le debuff doit MORDRE sur les affectes (facteur < 1) et laisser les
        # non-affectes INCHANGES -- sans quoi un accord en regime degenere ne prouverait rien.
        verdicts["E4 le debuff MORD (affectes)"] = (bool(aff)
                                                    and all(f is not None and f < 1.0
                                                            for f in aff.values()))
        if tem:
            verdicts["E4 temoin PLAT (non affecte)"] = all(f == 1.0 for f in tem.values())
        else:
            print("      ATTENTION : aucun TEMOIN non-affecte a portee -- E4 ne discrimine pas "
                  "'le debuff mord' de 'tout a baisse'")
        print("[510] E5 COMBAT -- ctrl apres endturn = %s ; affectes = %s"
              % (sorted(ctrl), aura_turn))
        agi = set()
        for tid, tag in ((bag_hurt, "defenseur 40pc PV"), (bag_full, "defenseur 100pc PV")):
            # L'attaquant est choisi PAR CIBLE : il doit etre AFFECTE **A CET INSTANT**, controlable,
            # ne pas avoir deja agi, et avoir une prediction native NON NULLE sur cette cible.
            att = next((u for u in aura_turn
                        if u in ctrl and u not in agi and (pre_pairs.get(u) or {}).get(tid)), None)
            if att is None:
                print("      %s : NON MESURE (aucun attaquant affecte, libre et a portee)" % tag)
                continue
            na = _normal_attack_id(dv3, att)
            # ANTI-CONFOND TEMPOREL : la prediction native est RE-MESUREE ICI, au MEME instant que
            # l'attaque de combat qui suit, sur le MEME couple et avec le MEME effet actif. Sans
            # elle, l'ecart prediction/combat pourrait n'etre qu'une expiration d'effet entre E4
            # et E5.
            nat_ici = _native_pred(sid, rid, att, tid, na)
            base_ici = (pre_pairs.get(att) or {}).get(tid, (None, None))[0]
            dec5, ob5, snap5, bg5, rng5 = P226.capture(sid, rid)
            hp_pre = P226.offline_state(dec5, ob5, snap5, bg5, rng5) \
                         .get_entity(tid).get_component(_HC).hp
            res5 = PR.act(sid, rid, {"kind": "ability", "casterId": att,
                                     "targetId": tid, "abilityType": na})
            if not res5.get("mutated"):
                print("      u%d -> u%d (%s) : action NON APPLIQUEE" % (att, tid, tag))
                continue
            agi.add(att)
            ob6 = _r(sid, "observeBattle", {"runnerId": rid}, 60)
            live_after = next((u.get("hp") for u in (ob6.get("units") or [])
                               if u.get("squadId") == tid), None)
            live_dmg = int(hp_pre) - int(live_after)
            # DECOMPOSITION : ce que le port fabrique comme modifiers ATTAQUANT, dans les deux bras.
            import engine.runner.damage_model as _DM
            st_dbg = P226.offline_state(dec5, ob5, snap5, bg5, rng5)
            m_on, act_on = _DM.attacker_modifiers(st_dbg, att, None, is_ranged=False,
                                                  target_id=tid)
            print("        modifiers ARME   : pct=%s details=%s effets_actifs=%s"
                  % (m_on.pct_list, [d.value for d in m_on.details],
                     sorted(getattr(e, "name", "?") for e in act_on)))
            off_on = _rejoue(dec5, ob5, snap5, bg5, rng5, att, tid, hp_pre, patch=False)
            off_ctl = _rejoue(dec5, ob5, snap5, bg5, rng5, att, tid, hp_pre, patch=False)
            off_no = _rejoue(dec5, ob5, snap5, bg5, rng5, att, tid, hp_pre, patch=True)
            fac_ici = (None if not (base_ici and nat_ici and base_ici[1])
                       else round(nat_ici[1] / float(base_ici[1]), 4))
            print("      u%d -> u%d (%s) : live=%d | port ARME=%d (controle re-joue=%d) | DESARME=%d"
                  % (att, tid, tag, live_dmg, off_on, off_ctl, off_no))
            print("        anti-confond : prediction native AU MEME INSTANT = %s (facteur %s)"
                  % (nat_ici, fac_ici))
            verdicts["E5 harnais deterministe (%s)" % tag] = (off_on == off_ctl)
            verdicts["E5 port == live (%s)" % tag] = (live_dmg == off_on)
            if tid == bag_hurt:
                double = (live_dmg == off_on and off_on != off_no)
                print("      -> le natif COMBAT est %s"
                      % ("DOUBLE (bras ARME)" if double
                         else "PLAT (bras DESARME)" if live_dmg == off_no
                         else "NI L'UN NI L'AUTRE -- autre etage en cause"))
                verdicts["E5 combat DOUBLE (bras arme bit-exact)"] = double
                # ANTI-CONFOND : au MEME instant, la PREDICTION native doit elle aussi porter le
                # doublement (facteur ~ 1 - 2*pct/100). C'est ce qui a REFUTE le « fork
                # prediction/combat » qu'on avait cru lire hors-tour.
                verdicts["E6 prediction ET combat doublent au MEME instant"] = (
                    double and fac_ici is not None and fac_ici < 0.5)
    finally:
        if not a.keep:
            _run(["dispose", "--state-file", str(state_file)])
    return verdicts


def main() -> int:
    a = _parser().parse_args()
    verdicts = mesure(a)
    if verdicts is None:
        return 2
    print("[510] VERDICTS")
    for k, v in verdicts.items():
        print("      %-44s : %s" % (k, "OK" if v else "FAUTE"))
    ok = bool(verdicts) and all(verdicts.values())
    print("[510] %s" % ("PROBE OK" if ok else "PROBE EN FAUTE"))
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
