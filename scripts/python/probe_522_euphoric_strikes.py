#!/usr/bin/env python
"""probe #522 -- `EuphoricStrikes` (1198, `emperExultant` « Laviscus ») vs le natif.

CE QUI EST MESURE
-----------------
Avant #522 l'ability etait un **NO-OP SILENCIEUX** : absente d'`ABILITY_CLASSES`, donc le cast
partait, l'`AbilityHandler` rendait `ported=False` et RIEN ne se passait -- 0 degat, 0 effet,
AUCUNE erreur. Le probe monte UN regime deterministe (positions FORCEES par `--place`), prend une
capture complete (`decisionView`/`observeBattle`/`combatSnapshot`/`boardGraph` + `dumpRng`), rejoue
le cast HORS LIGNE par le CHEMIN COMPLET du moteur (`Runner.apply`), lance le cast NATIF sur le MEME
runner, et confronte CINQ etages -- jamais un scalaire :

  E0  `ported`      -- l'observable qui distingue le port du no-op ;
  E1  LE DEGAT du cast, coup par coup (`UnitDamaged` natifs `Active_Ability_Type=1198` vs
      `per_hit_health` du port) ET le nombre de tirages `genrand_int32` consommes de part et
      d'autre (`dumpRng` avant/apres) : meme compte + montants differents = arithmetique ;
      comptes differents = STRUCTURE ;
  E2  LA POSE de la marque `EuphoricStrikes_ExtraCrit` (0x595 = 1429) sur la CIBLE, cote natif
      (`decisionView.effects` de la cible) et cote port (`EffectsState`) ;
  E3  LE CANAL crit-chance, et c'est le coeur du cas. L'ALLIE frappe ensuite la cible marquee.
      `--crit 70,700` met sa crit chance de BASE a 70 ; `extraCritChance[L50] = 30` -> la marque la
      porte a **100**, donc TOUS les coups doivent criter. Le regime est rendu DISCRIMINANT par une
      contre-epreuve HORS LIGNE sur la MEME capture : la meme attaque rejouee avec la marque
      CONSOMMEE doit rendre un resultat DIFFERENT. Si les deux coincidaient, le vert de l'accord ne
      prouverait rien (accord en regime degenere) ;
  E4  LE RETRAIT -- `CreateRemoveEffectTrigger` = `On(9 = Attack) & OwnerIsTarget | On(0 = UnitDeath)
      & Target == EffectSource`. Apres l'attaque de l'allie, 1429 doit avoir DISPARU de la cible,
      cote natif comme cote port. Sans ce cran le +crit bufferait TOUTES les attaques du tour.

MONTAGE (board `MC1_67`) -- les positions sont FORCEES, jamais subies
---------------------------------------------------------------------
    emperExultant  (4,5)  le caster. HERO `lineup` HORS seed BC -> `catalog_inject`
                          (`docs/rl/case-92-catalog-injection.md` §6). `--list-pool` ne le rend PAS,
                          et ce n'est PAS un refus : aucun `data/unspawnable_rank*.json` n'existe.
    necroWarden    (4,6)  la CIBLE -- adjacente au caster (le masque est `RANGE_ADJACENT`)
    ultraTitus     (4,7)  l'ALLIE  -- adjacent a la CIBLE, c'est lui qui exerce le canal crit
    orksNob        (0,3)  temoin LOIN : il porte la meme crit chance et n'a AUCUNE marque

REGIMES
-------
    `nominal` (`--crit 70,700`) -- kit COMPLET, RIEN n'est retire. C'est le regime ou le degat du
       cast doit etre BIT-EXACT et ou le canal crit est DISCRIMINANT (70 + 30 = 100).
    `gate0`   (`--crit 0,700`)  -- la crit chance de BASE est nulle : le gate
       `AmountIsGreaterThanZero(StatAmount(Caster, CritChance))` doit FERMER le canal. Le trait
       `ThrillSeekers` du caster y est RETIRE (`--unit-stat emperExultant:Traits=["Hero"]`),
       exactement comme le R0 de `probe_512` retire un passif -- et pour la meme raison, mesuree
       ci-dessous. (`--unit-stat` splitte ses CHAMPS sur la virgule, donc un tableau JSON
       multi-elements est impossible a passer : `CrushingStrike` part avec, et c'est sans effet ici
       -- il modifie le DEGAT, or les deux cotes rendent 6353 dans les deux variantes.)

RESIDU MESURE `#522-r1` -- POURQUOI LE REGIME `gate0` ISOLE LE TRAIT, ET CE QUE CA N'ACCUSE PAS
-----------------------------------------------------------------------------------------------
Avec le kit COMPLET a `--crit 0,700`, le port consomme **UN tirage `genrand_int32` DE PLUS** que le
natif sur le cast (3 contre 2) -- a DEGAT ET SEQUENCE IDENTIQUES (6353 des deux cotes, `crits=
[False]`). L'ecart est ENTIEREMENT attribue, et il n'est PAS dans le mirror d'`ExecuteBehaviour` :

    kit complet, --crit 0,700   : natif 2  /  port 3
    trait ThrillSeekers RETIRE  : natif 2  /  port 2      <- l'ecart DISPARAIT
    temoin `ThunderousAssault` (1043, `templSwordBrother`, meme board, meme `--crit 0,700`,
    meme famille ATTACK, melee adjacent -- porteur SANS le trait) : natif 5 / port 5

Cause : `ThrillSeekers` (trait `UnitTrait` 1056 des cinq kits Emperor's Children) pose « Thrilled »
(`EffectType` 0x59a = 1434), un `StaticStatModifierEffect` de +15 CRIT_CHANCE, sur
`On(PreAttackHit = 6) & IsFirstHitInSeries & OwnerIsCaster & NOT IsWounded(target)`. Le NATIF le
pose bien (`decisionView` du caster porte 1434 apres le cast) mais **n'en tient PAS compte pour le
crit du coup DECLENCHANT** : sa crit chance reste 0, donc `DamageCalculations$$CouldCrit(0, 700)`
est faux et `RollCritical` n'est jamais appele. Le PORT, lui, applique le +15 au coup courant :
`could_crit(15, 700)` est vrai -> un crit-roll de plus. `runner/operations/triggers/loki/
thrill_seekers.py` l'ecrit d'ailleurs explicitement (« le buff s'applique bien a l'attaque
declenchante ») -- c'est CETTE lecture que la mesure contredit.

Observable ici : RIEN sur le degat (le crit-roll a cc = 15 echoue), mais le RNG est DESYNCHRONISE
pour la suite, et dans un regime ou ce tirage REUSSIRAIT le port critterait la ou le natif ne le
peut pas. Corriger le timing touche les CINQ porteurs du trait et exige la RE du point ou le natif
lit `GetStat(9)` dans `ExecuteHit` : hors perimetre de cette tranche, d'ou le residu.

RESIDU `#522-r2` -- le PASSIF de Laviscus n'est pas porte
---------------------------------------------------------
Meme mesure, autre lecture : apres le cast, le CASTER porte cote natif `[1226, 1430, 1434, 1511]`
et cote port `[1226, 1434]`. `RefusalToBeOutdone_ExtraDamage` (1430) et
`RefusalToBeOutdone_ExtraCritDamage` (1511) viennent du passif `RefusalToBeOutdone`
(`TriggeredAbilityType` 1441), NON PORTE. Aucun effet observable sur les degats de ce montage (les
deux cotes rendent 7403 en `nominal` et 6353 en `gate0`), mais l'ecart d'ETAT est reel.

Usage (depuis `scripts/python`, ASCII only) :
    python probe_522_euphoric_strikes.py
    python probe_522_euphoric_strikes.py --regime gate0
    python probe_522_euphoric_strikes.py --keep      # ne dispose PAS le runner
"""
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import tempfile
import urllib.request

HOST = "http://127.0.0.1:8765"
PYDIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, PYDIR)

EUPHORIC_STRIKES = 1198                    # `ActiveAbilityType.EuphoricStrikes`
EUPHORIC_EXTRA_CRIT = 0x595                # `EffectType.EuphoricStrikes_ExtraCrit` = 1429

CASTER = "emperExultant"                   # « Laviscus », seul porteur LINEUP de 1198
ALLY = "ultraTitus"                        # l'attaquant qui exerce le canal crit
FOE = "necroWarden"                        # la CIBLE marquee
FOE_B = "orksNob"                          # temoin LOIN

BOARD = "MC1_67"
SEED = 522
PLACES = ((CASTER, "4,5"), (ALLY, "4,7"))
A_PLACES = ((FOE, "4,6"), (FOE_B, "0,3"))
#: `--crit C,D` sur les p-units. 70 + `extraCritChance[L50]` (= 30) = **100** : la marque doit faire
#: criter TOUS les coups de l'allie, la ou 70 seul ne le garantit pas. C'est ce couple qui rend
#: l'etage E3 discriminant.
CRIT = "70,700"
#: PV eleves : la cible doit SURVIVRE au cast pour que l'attaque de l'allie ait lieu. (⚠ `--hp-target`
#: met AUSSI Armor/FixedArmor a 0 -- l'etage armure disparait, ce qui est neutre ici puisque les deux
#: cotes voient le MEME etat, mais serait un piege si le sujet etait le percage.)
HP_TARGET = 400000

RE_DMG = re.compile(
    r"UnitDamaged e=(\d+).*?Attack_DidCrit=(\d).*?Attacker_Id=(\d+) Target_Id=(\d+) "
    r"Amount=(-?\d+) DamageProfileType=(\d+) Active_Ability_Type=(\d+)")


# ------------------------------------------------------------------ transport

def _sid():
    with urllib.request.urlopen(HOST + "/api/admin/status", timeout=20) as r:
        return json.loads(r.read().decode("utf-8"))["session"]["id"]


def _rpc(sid, method, body=None, timeout=120):
    payload = json.dumps({"method": method,
                          "args": [body] if body is not None else []}).encode("utf-8")
    req = urllib.request.Request("%s/api/scripts/%s/rpc" % (HOST, sid), data=payload,
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        out = json.loads(r.read().decode("utf-8"))
    return out.get("result") if isinstance(out, dict) and "result" in out else out


def _duel(args, timeout=500):
    return subprocess.run([sys.executable, "rl_duel.py"] + args, cwd=PYDIR,
                          capture_output=True, text=True, timeout=timeout)


# ------------------------------------------------------------------ montage

def build(state_file: str, seed_bc: str, crit: str, unit_stat=()):
    argv = ["build", "--seed", str(SEED), "--board", BOARD, "--seed-bc", seed_bc,
            "--crit", crit, "--hp-target", str(HP_TARGET),
            "--p-units", ",".join(v for v, _t in PLACES),
            "--a-units", ",".join(v for v, _t in A_PLACES),
            "--state-file", state_file]
    for vid, tile in PLACES:
        argv += ["--place", "%s:%s" % (vid, tile)]
    for vid, tile in A_PLACES:
        argv += ["--a-place", "%s:%s" % (vid, tile)]
    for spec in unit_stat:
        argv += ["--unit-stat", spec]
    p = _duel(argv)
    if p.returncode != 0:
        print("[build] rc=%s\n%s\n%s" % (p.returncode, p.stdout[-2000:], p.stderr[-1200:]))
        return None
    with open(state_file, "r", encoding="utf-8") as f:
        return int(json.load(f)["runnerId"])


def unites(sid, rid):
    dv = _rpc(sid, "decisionView", {"runnerId": rid, "allAbilities": True}, 150)
    out = {}
    for u in (dv.get("units") or []):
        p = u.get("pos") or {}
        out[u.get("visualId")] = {"id": u.get("id"), "pos": (p.get("col"), p.get("row")),
                                  "hp": u.get("hp"), "alive": not u.get("isDead"),
                                  "abilities": u.get("abilities") or [],
                                  "effects": [e.get("effectType") for e in (u.get("effects") or [])
                                              if isinstance(e, dict)]}
    return out


def capture(sid, rid):
    return {
        "dv": _rpc(sid, "decisionView", {"runnerId": rid, "allAbilities": True}, 150),
        "ob": _rpc(sid, "observeBattle", {"runnerId": rid}, 90),
        "snap": _rpc(sid, "combatSnapshot", {"runnerId": rid}, 120),
        "ab": _rpc(sid, "unitAbilityStates", {"runnerId": rid}, 90),
        "tiles": _rpc(sid, "boardGraph", {"runnerId": rid}, 90)["tiles"],
        "rng": _rpc(sid, "dumpRng", {"runnerId": rid}, 60),
    }


def etat_offline(cap):
    """Le substrat du rejeu porte, MT cale sur `dumpRng` -- sans lui le degat offline est un faux 0."""
    from engine.entities.pathfinding.board import Board
    from engine.runner.prng import IntBasedMersenneTwister
    from engine.runner.snapshot import load_state
    st = load_state(cap["dv"], cap["ob"], cap["snap"], board=Board(cap["tiles"], adjacency="evenq"),
                    ability_states=cap["ab"])
    rng = IntBasedMersenneTwister()
    rng.mt = list(cap["rng"]["mt"])
    rng.mti = cap["rng"]["mti"]
    st.rng = rng
    return st


def montants_natifs(sortie, ability_type=None):
    """SEQUENCE coup par coup du NATIF : (attaquant, cible, montant, crit).

    Elle se lit dans le STDOUT de `rl_duel act` (les events formates), PAS dans la reponse RPC
    brute d'`applyAction` : cette derniere ne porte pas le texte des tags. Mesure du 2026-08-07 --
    ce probe lisait d'abord la reponse RPC et rendait une liste VIDE en silence, ce qui aurait
    laisse passer une divergence de sequence sous un total juste."""
    out = []
    for m in RE_DMG.finditer(sortie or ""):
        _e, crit, att, tgt, amount, _prof, at = m.groups()
        if ability_type is not None and int(at) != int(ability_type):
            continue
        out.append({"att": int(att), "tgt": int(tgt), "amount": int(amount), "crit": crit == "1"})
    return out


def tirages(rng_initial, mt_cible, mti_cible, cap=4000):
    """Nombre de `genrand_int32` consommes pour aller de l'etat INITIAL a l'etat CIBLE.

    C'est l'etage qui LOCALISE une divergence : deux moteurs qui rendent des montants differents
    mais consomment le MEME nombre de tirages ont un bug d'ARITHMETIQUE ; s'ils n'en consomment
    pas le meme nombre, c'est la STRUCTURE. Rend `None` si l'etat cible n'est pas atteint.
    ⚠ Une soustraction de `mti` est FAUSSE : le compteur MT19937 se recharge tous les 624 tirages
    et rend alors un delta NEGATIF (mesure : `-621` ici avant correction)."""
    from engine.runner.prng import IntBasedMersenneTwister
    r = IntBasedMersenneTwister()
    r.mt, r.mti = list(rng_initial["mt"]), rng_initial["mti"]
    for n in range(cap + 1):
        if r.mti == mti_cible and r.mt == list(mt_cible):
            return n
        r.genrand_int32()
    return None


def hp_de(ob, uid):
    """`observeBattle` indexe par `squadId`, PAS par `id`."""
    for u in ((ob or {}).get("units") or []):
        if u.get("squadId") == uid and not u.get("isDead"):
            return u.get("hp")
    return None


def effets_de(sid, rid, uid):
    dv = _rpc(sid, "decisionView", {"runnerId": rid, "allAbilities": True}, 150)
    for u in (dv.get("units") or []):
        if u.get("id") == uid:
            return sorted(e.get("effectType") for e in (u.get("effects") or [])
                          if isinstance(e, dict) and e.get("effectType") is not None)
    return None


def effets_port(st, uid):
    eff = getattr(st, "effects", None)
    if eff is None:
        return []
    return sorted(e.effect_type for e in eff.by_unit.get(int(uid), []) if not e.consumed)


def hp_port(st, uid):
    from engine.runner.components import HealthComponent
    e = st.get_entity(uid)
    hc = e.get_component(HealthComponent) if e is not None else None
    return hc.hp if hc is not None else None


def normale_de(u):
    """L'attaque normale est une ABILITY d'id CONCRET par unite (jamais un `kind: attack`)."""
    return next((a["id"] for a in (u.get("abilities") or [])
                 if a.get("kind") == "normal" and a.get("id") is not None), None)


def crit_effectif(st, att_id, tgt_id):
    """La crit chance EFFECTIVE du coup `att_id -> tgt_id`, par le FOYER UNIQUE du canal
    (`AttackDamageOperation._crit_params`) -- l'ETAGE isole, pas un scalaire de sortie.

    C'est ce qui permet d'attribuer : un ecart de degat total peut naitre de dix endroits, une
    crit chance de 100 au lieu de 70 n'en a qu'un. Rend `(crit_chance, crit_damage, could_crit)`."""
    from engine.runner.components import StatsComponent, unit_state_for_effects
    from engine.runner.operations.damage import AttackDamageOperation
    e = st.get_entity(att_id)
    sc = e.get_component(StatsComponent) if e is not None else None
    if sc is None:
        return (None, None, None)
    eff = ([] if st.effects is None
           else list(st.effects.active_effects(int(att_id), unit_state_for_effects(st, int(att_id)))))
    return AttackDamageOperation._crit_params(sc.ctx, eff, state=st, att_id=int(att_id),
                                              tgt_id=int(tgt_id), is_ranged=False,
                                              is_normal_attack=True)


# ------------------------------------------------------------------ le probe

#: `gate0` SEUL retire le trait `ThrillSeekers` du caster -- c'est ce qui isole l'`ExecuteBehaviour`
#: du residu `#522-r1` (cf. l'en-tete : l'ecart de tirages DISPARAIT sans lui, 2/2 au lieu de 3/2).
#: Le regime `nominal` garde le kit COMPLET : c'est lui qui atteste que le port est bit-exact avec
#: tout le kit en place.
UNIT_STAT = {"gate0": ('%s:Traits=["Hero"]' % CASTER,)}


def mesurer(regime: str, crit: str, keep: bool, state_file_arg) -> int:
    """Rend 0 si le regime est vert, 1 si une mesure echoue, 2 si le MONTAGE n'est pas installe.

    Un montage qui ne s'installe pas ECHOUE (rc 2) -- jamais un skip vert : un echec de montage
    parti en skip est un VERT QUI MENT."""
    import catalog_inject
    from engine.runner.messages import ActiveAbilityMessage, AttackUnitMessage
    from engine.runner.runner import Runner

    tmp = tempfile.mkdtemp(prefix="p522_")
    seed_bc = os.path.join(tmp, "seedbc_522.json")
    catalog_inject.write_augmented_seed_bc(seed_bc, [CASTER])
    state_file = state_file_arg or os.path.join(tmp, "state_522_%s.json" % regime)

    sid = _sid()
    rid = build(state_file, seed_bc, crit, UNIT_STAT.get(regime, ()))
    if rid is None:
        print("[522/%s] BUILD KO -- aucune mesure" % regime)
        return 2
    print("\n================ REGIME %s (--crit %s) ================" % (regime, crit))
    print("[522] runner=%s board=%s seed=%s" % (rid, BOARD, SEED))
    ok = True
    try:
        u = unites(sid, rid)
        voulu = dict(PLACES) | dict(A_PLACES)
        manque = [v for v in voulu if v not in u]
        if manque:
            print("[522] MONTAGE INVALIDE -- absents %r" % (manque,))
            return 2
        mauvais = [(v, u[v]["pos"], voulu[v]) for v in voulu
                   if u[v]["pos"] != tuple(int(x) for x in voulu[v].split(","))]
        if mauvais:
            print("[522] PLACEMENT REFUSE -- %r" % (mauvais,))
            return 2
        cid, tid, aid = u[CASTER]["id"], u[FOE]["id"], u[ALLY]["id"]
        print("[522] caster=%s(%s) cible=%s(%s) allie=%s(%s)"
              % (CASTER, cid, FOE, tid, ALLY, aid))

        # ---------------------------------------------------------------- E0/E1/E2 : le CAST
        cap = capture(sid, rid)
        st = etat_offline(cap)
        #: Etat JUMEAU, non mute : il sert a lire la crit chance du CASTER AVANT le cast (`st` est
        #: mute par `Runner.apply`, et lire apres rendrait l'etat d'apres en croyant lire celui du
        #: cast). C'est l'attribution de l'ecart de TIRAGES : un crit-roll ne se tire que si
        #: `CouldCrit(cc, cd)`, donc un port qui verrait `cc > 0` la ou le natif voit 0 tirerait un
        #: coup de plus, a degat pourtant identique.
        st_diag = etat_offline(cap)
        runner = Runner(st).install_default_handlers(20)
        hp0_nat = hp_de(cap["ob"], tid)
        hp0_off = hp_port(st, tid)
        p = _duel(["act", "ability", "--caster", str(cid), "--ability", str(EUPHORIC_STRIKES),
                   "--target", str(tid), "--state-file", state_file, "--runner", str(rid)])
        sortie = (p.stdout or "") + (p.stderr or "")
        if p.returncode != 0 or "mutated" not in sortie.lower():
            print("[522] le natif REFUSE le cast (rc=%s) :\n%s" % (p.returncode, sortie[-1500:]))
            return 2
        rng_apres_nat = _rpc(sid, "dumpRng", {"runnerId": rid}, 60)
        ob2 = _rpc(sid, "observeBattle", {"runnerId": rid}, 90)
        delta_nat = (hp0_nat or 0) - (hp_de(ob2, tid) or 0)

        runner.apply(ActiveAbilityMessage(cid, tid, EUPHORIC_STRIKES))
        diag = runner.ability_handler.last or {}
        delta_off = (hp0_off or 0) - (hp_port(st, tid) or 0)

        print("\n-- E0 ported ------------------------------------------------")
        print("    ported=%r  emitted=%r" % (diag.get("ported"), diag.get("emitted")))
        if diag.get("ported") is not True:
            print("    ECHEC : 1198 NON PORTEE (no-op silencieux)")
            ok = False

        print("\n-- E1 degat du cast -----------------------------------------")
        seq_nat = montants_natifs(sortie, EUPHORIC_STRIKES)
        atk = diag.get("attack") or {}
        seq_off = list(atk.get("per_hit_health") or [])
        n_nat = tirages(cap["rng"], rng_apres_nat.get("mt"), rng_apres_nat.get("mti"))
        n_off = tirages(cap["rng"], st.rng.mt, st.rng.mti)
        print("    natif  delta=%s  sequence=%r  crits=%r"
              % (delta_nat, [d["amount"] for d in seq_nat], [d["crit"] for d in seq_nat]))
        print("    port   delta=%s  sequence=%r" % (delta_off, seq_off))
        print("    tirages genrand_int32 : natif=%r  port=%r" % (n_nat, n_off))
        cc_caster = crit_effectif(st_diag, cid, tid)
        print("    port  crits=%r rolls=%r | crit chance du CASTER (port) = %r cd=%r could_crit=%r"
              % (atk.get("crits"), atk.get("rolls"), cc_caster[0], cc_caster[1], cc_caster[2]))
        if delta_nat != delta_off:
            print("    ECHEC : degat du cast DIVERGENT")
            ok = False
        if delta_nat <= 0:
            print("    ECHEC : temoin NUL -- un accord en regime DEGENERE ne prouve rien")
            ok = False
        if not seq_nat:
            print("    ECHEC : AUCUN `UnitDamaged` natif lu -- la mesure de SEQUENCE est MUETTE,")
            print("            donc l'accord des totaux ne prouve rien sur les coups.")
            ok = False
        elif [d["amount"] for d in seq_nat] != seq_off:
            print("    ECHEC : SEQUENCE coup par coup divergente (le total peut masquer)")
            ok = False
        if n_nat is None or n_off is None or n_nat != n_off:
            print("    ECHEC : nombre de tirages DIVERGENT (natif=%r port=%r) -> STRUCTURE"
                  % (n_nat, n_off))
            ok = False

        print("\n-- E2 pose de la marque 1429 --------------------------------")
        eff_nat = effets_de(sid, rid, tid)
        eff_off = effets_port(st, tid)
        print("    natif effets(cible)=%r" % (eff_nat,))
        print("    port  effets(cible)=%r" % (eff_off,))
        if EUPHORIC_EXTRA_CRIT not in (eff_nat or []):
            print("    ECHEC : le NATIF ne pose pas 1429 -- la RE est fausse")
            ok = False
        if EUPHORIC_EXTRA_CRIT not in eff_off:
            print("    ECHEC : le PORT ne pose pas 1429")
            ok = False

        # ---------------------------------------------------------------- E3/E4 : le CANAL
        cap2 = capture(sid, rid)
        st_avec = etat_offline(cap2)
        st_sans = etat_offline(cap2)
        # CONTRE-EPREUVE : la MEME capture, marque CONSOMMEE. Si les deux rejeux coincidaient, le
        # regime ne mesurerait PAS le canal et le vert de l'accord ne prouverait rien.
        for e in (st_sans.effects.by_unit.get(int(tid)) or []):
            if e.effect_type == EUPHORIC_EXTRA_CRIT:
                e.consumed = True
        u2 = unites(sid, rid)
        na = normale_de(u2[ALLY])
        if na is None:
            print("[522] attaque normale de l'allie introuvable -- montage non conforme")
            return 2
        # E3a se mesure AVANT tout rejeu : `EFFECT_TRIGGERS[1429]` CONSOMME la marque pendant
        # l'attaque, donc lire la crit chance APRES rendrait la valeur NUE des deux cotes -- un
        # faux « bonus 0 » qui accuserait le canal a tort (faute commise puis corrigee ici).
        cc_marque = crit_effectif(st_avec, aid, tid)          # marque presente, cible = le porteur
        cc_sans = crit_effectif(st_sans, aid, tid)            # marque consommee
        bid = u2[FOE_B]["id"]
        cc_autre = crit_effectif(st_avec, aid, bid)           # get_OwnerIsTarget : AUTRE defenseur

        hp1_nat = hp_de(cap2["ob"], tid)
        p2 = _duel(["act", "ability", "--caster", str(aid), "--ability", str(int(na)),
                    "--target", str(tid), "--state-file", state_file, "--runner", str(rid)])
        sortie2 = (p2.stdout or "") + (p2.stderr or "")
        if p2.returncode != 0 or "mutated" not in sortie2.lower():
            print("[522] l'attaque de l'allie est REFUSEE (rc=%s) :\n%s"
                  % (p2.returncode, sortie2[-1500:]))
            return 2
        ob3 = _rpc(sid, "observeBattle", {"runnerId": rid}, 90)
        rng_apres_na = _rpc(sid, "dumpRng", {"runnerId": rid}, 60)
        d2_nat = (hp1_nat or 0) - (hp_de(ob3, tid) or 0)
        seq2_nat = montants_natifs(sortie2, int(na))

        h_avec = hp_port(st_avec, tid)
        Runner(st_avec).install_default_handlers(20).apply(AttackUnitMessage(aid, tid))
        d2_avec = (h_avec or 0) - (hp_port(st_avec, tid) or 0)
        h_sans = hp_port(st_sans, tid)
        Runner(st_sans).install_default_handlers(20).apply(AttackUnitMessage(aid, tid))
        d2_sans = (h_sans or 0) - (hp_port(st_sans, tid) or 0)
        # Les tirages de l'attaque NORMALE : chemin 100 % GENERIQUE, hors #522. Il sert de TEMOIN
        # d'attribution pour l'ecart de tirages mesure sur le cast (E1).
        n2_nat = tirages(cap2["rng"], rng_apres_na.get("mt"), rng_apres_na.get("mti"))
        n2_off = tirages(cap2["rng"], st_avec.rng.mt, st_avec.rng.mti)
        base = int(crit.split(",")[0])
        #: GATE `AmountIsGreaterThanZero(StatAmount(Caster, CritChance, Current))`. Le SUJET est
        #: l'ATTAQUANT, pas le porteur : une unite a crit chance de BASE nulle ne doit RIEN gagner.
        #: C'est ce que le regime `gate0` (`--crit 0,...`) exerce, et lui seul.
        gate_ouvert = base > 0
        var_extra = None
        try:
            from engine.entities.effects.magnitude import ability_var
            var_extra = int(ability_var("EuphoricStrikes", "extraCritChance", 50,
                                        multiplier_pct=100) or 0)
        except Exception as exc:                              # pragma: no cover - diagnostic
            print("    (lecture gameconfig KO : %r)" % (exc,))
        attendu = var_extra if gate_ouvert else 0
        print("\n-- E3a crit chance EFFECTIVE (etage isole) ------------------")
        print("    base(--crit)=%s  extraCritChance[L50] du gameconfig=%r  gate=%s"
              % (base, var_extra, "OUVERT" if gate_ouvert else "FERME"))
        print("    cc(allie -> CIBLE MARQUEE)  = %r" % (cc_marque[0],))
        print("    cc(allie -> cible, SANS)    = %r   (contre-epreuve)" % (cc_sans[0],))
        print("    cc(allie -> AUTRE unite)    = %r   (get_OwnerIsTarget)" % (cc_autre[0],))
        if var_extra is None or cc_marque[0] is None or cc_sans[0] is None:
            print("    ECHEC : mesure MUETTE")
            ok = False
        else:
            if not var_extra:
                print("    ECHEC : `extraCritChance` lu a 0 -- contre-epreuve VACUE")
                ok = False
            if int(cc_marque[0]) != int(cc_sans[0]) + attendu:
                print("    ECHEC : bonus applique %r, attendu %r (base %r + %r)"
                      % (int(cc_marque[0]) - int(cc_sans[0]), attendu, cc_sans[0], attendu))
                ok = False
            # `get_OwnerIsTarget` : la marque vit sur `necroWarden` ; un coup porte sur une AUTRE
            # unite ne doit RIEN recevoir. Sans ce noeud, tout porteur du board bufferait tout le
            # monde (c'est le vice que l'elargissement `board_effect_carriers` rendait possible).
            if int(cc_autre[0]) != int(cc_sans[0]):
                print("    ECHEC : la marque buffe un coup porte sur une AUTRE unite")
                ok = False

        print("\n-- E3 canal crit-chance (attaque de l'allie) ----------------")
        print("    natif delta=%s  crits=%r" % (d2_nat, [d["crit"] for d in seq2_nat]))
        print("    port  AVEC la marque delta=%s" % (d2_avec,))
        print("    port  SANS la marque delta=%s  (contre-epreuve)" % (d2_sans,))
        print("    tirages attaque NORMALE (chemin generique, TEMOIN) : natif=%r port=%r"
              % (n2_nat, n2_off))
        if gate_ouvert and d2_avec == d2_sans:
            print("    ECHEC : regime NON DISCRIMINANT -- avec et sans la marque donnent le meme")
            print("            resultat, donc ce bras ne mesure PAS le canal crit.")
            ok = False
        if (not gate_ouvert) and d2_avec != d2_sans:
            print("    ECHEC : gate FERME et pourtant la marque change le degat -- le noeud")
            print("            `AmountIsGreaterThanZero(StatAmount(Caster, CritChance))` ne mord pas.")
            ok = False
        if d2_nat != d2_avec:
            print("    ECHEC : le natif ne suit PAS le port marque (%s vs %s)" % (d2_nat, d2_avec))
            ok = False
        if not seq2_nat:
            print("    ECHEC : AUCUN `UnitDamaged` natif lu sur l'attaque de l'allie -- la mesure")
            print("            des CRITS est muette, le seul total ne dit pas OU l'ecart naitrait.")
            ok = False
        elif gate_ouvert and not all(d["crit"] for d in seq2_nat):
            print("    ECHEC : tous les coups natifs ne critent PAS alors que la marque porte la")
            print("            crit chance a %s + %r = %r." % (base, var_extra, base + (var_extra or 0)))
            ok = False
        elif (not gate_ouvert) and any(d["crit"] for d in seq2_nat):
            print("    ECHEC : un coup natif CRITE alors que la crit chance de base est 0 -- le")
            print("            natif applique donc un bonus que le gate devrait fermer.")
            ok = False

        print("\n-- E4 retrait On(9) -----------------------------------------")
        eff2_nat = effets_de(sid, rid, tid)
        eff2_off = effets_port(st_avec, tid)
        print("    natif effets(cible) apres l'attaque=%r" % (eff2_nat,))
        print("    port  effets(cible) apres l'attaque=%r" % (eff2_off,))
        if EUPHORIC_EXTRA_CRIT in (eff2_nat or []):
            print("    ECHEC : le NATIF garde 1429 -- la lecture du RemoveEffectTrigger est fausse")
            ok = False
        if EUPHORIC_EXTRA_CRIT in eff2_off:
            print("    ECHEC : le PORT garde 1429 -- EFFECT_TRIGGERS[1429] muet")
            ok = False
    finally:
        if not keep:
            _duel(["dispose", "--state-file", state_file])

    print("\n[522/%s] %s" % (regime, "OK" if ok else "KO"))
    return 0 if ok else 1


#: Les DEUX regimes. Ils ne different QUE par la crit chance de BASE de l'attaquant, et c'est ce
#: couple qui rend le gate `AmountIsGreaterThanZero(StatAmount(Caster, CritChance))` mesurable :
#: un port qui l'oublierait rendrait `+extraCritChance` dans les DEUX, le natif rend 30 puis 0.
REGIMES = {"nominal": CRIT, "gate0": "0,700"}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--keep", action="store_true")
    ap.add_argument("--regime", choices=sorted(REGIMES), default=None)
    ap.add_argument("--state-file", default=None)
    args = ap.parse_args()
    noms = [args.regime] if args.regime else ["nominal", "gate0"]
    rcs = {}
    for nom in noms:
        rcs[nom] = mesurer(nom, REGIMES[nom], args.keep, args.state_file)
    print("\n[522] %s -- %r" % ("PROBE OK" if set(rcs.values()) == {0} else "PROBE KO", rcs))
    return 0 if set(rcs.values()) == {0} else max(rcs.values())


if __name__ == "__main__":
    raise SystemExit(main())
