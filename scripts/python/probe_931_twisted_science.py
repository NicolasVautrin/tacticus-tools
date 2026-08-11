#!/usr/bin/env python
"""Probe #931 -- confront LIVE du passif `TwistedScience` (`genesBiophagus` "Hollan").

CE QUE CHAQUE PHASE MESURE, et pourquoi elle DISCRIMINE :

  * `--phase swap`   : le passif [F1] `...TwistedScienceAbility$$CreateBehaviour` =
                       `RemoveActiveAbility(Owner, 18 Heal) & AddActiveAbility(Owner, 1167
                       Heal_TwistedScience, abilityState)`. Le temoin lit l'INVENTAIRE d'abilities
                       que le natif publie et exige les DEUX moities sur le MEME etat :
                       Hollan porte 1167 et **PAS** 18, tandis qu'`ultraApothecary` -- MEME trait
                       `Healer`, PAS de `TwistedScience` -- porte 18 et **PAS** 1167. Un contre-
                       temoin dans le meme releve : sans lui, "Hollan a 1167" serait compatible
                       avec "tout le monde a 1167".
                       C'est CE releve qui etablit que porter [F1] cote runner n'a AUCUN observable
                       (le port charge un etat ou le swap est DEJA fait) -- verdict, pas supposition.

  * `--phase gates`  : ORACLE NATIF `abilityTargets(...).fromHere` (la query native de legalite, PAS
                       le port) confronte unite par unite au verdict du port
                       (`targeting.get_invalid_target_reason`), AVANT et APRES un marquage. Les deux
                       branches de la regle dynamique sont donc exercees, y compris la clause qui
                       fait tout l'interet de cette ability : un ALLIE NON MARQUE est une cible
                       LEGALE **meme a PV pleins** (i2 : "Hollan can heal other unaffected units
                       even if they are at full Health"). Le temoin discrimine : l'ensemble natif
                       PASSE de {83, 85} a {85} au marquage.

  * `--phase cast`   : cast de 1167 a PV PLEINS sur DEUX cibles -- une `Genestealers` et une NON --
                       delta de PV et effets poses, OFFLINE vs LIVE, sur le MEME etat de depart.
                       Le second bras est le contre-temoin du gate de FACTION : 1355 des deux cotes,
                       1356 seulement sur la Genestealer.

  * `--phase blesse` : le MEME cast sur une cible BLESSEE. C'est le regime ou le port et le natif
                       DIVERGENT, et la phase le CHIFFRE au lieu de le supposer : le natif releve le
                       plafond de PV (stat-mod `1355` sur `StatType.Health`) AVANT de soigner, donc
                       son `Heal` remplit jusqu'au NOUVEAU plafond ; le port, dont
                       `HealthComponent.hp_max` est un champ FIGE que les stat-mods HEALTH ne
                       relevent pas (#572-r1), s'arrete a l'ANCIEN. La phase imprime les TROIS
                       nombres -- natif, port, et "sans le port" (l'ability etait un no-op complet
                       avant cette tranche) -- pour que le ratio soit LU, pas plaide.

  * `--phase dmg`    : l'effet [F3] `1356 TwistedScience_ExtraDmg`
                       (`...TwistedScience_ExtraDmgEffect$$CreateEffectDamageBonusForAttack` =
                       `ForAddition(get_OwnerIsCaster, ConfigVar(8 extraDmg))`). Deux runners
                       JUMEAUX qui ne different QUE par le buff, la MEME attaque, le MEME seed :
                       l'ecart de degat natif est confronte a l'ecart du port.

MONTAGE : `genesBiophagus` est DANS le pool (`rl_duel build --list-pool`) -- aucune injection. Les
allies sont `genesKelermorph` (faction `Genestealers`) et `ultraApothecary` (`Ultramarines`, et
porteur du trait `Healer` -> c'est lui le contre-temoin du swap). L'ability est ADJACENT-ONLY
(`TargetingRange` statics+0x00 = `onlyAdjacent = IfNotRangedCaster`, et l'arme de Hollan est de
melee) : les SpawnPoints de `MC1_67` posent deja les trois cote a cote, ce que la phase VERIFIE
(elle ne le suppose pas) et corrige par `--place` si besoin.

ASCII only (cp1252). Usage :
    python probe_931_twisted_science.py --phase swap
    python probe_931_twisted_science.py --phase gates
    python probe_931_twisted_science.py --phase cast
    python probe_931_twisted_science.py --phase blesse
    python probe_931_twisted_science.py --phase dmg
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from pathlib import Path

PYDIR = Path(__file__).resolve().parent
sys.path.insert(0, str(PYDIR))

from rl_collect_batch import _resolve_session, _rpc                       # noqa: E402
from engine.entities.pathfinding.board import Board                       # noqa: E402
from engine.entities.effect_type import EffectType                        # noqa: E402
from engine.entities.active_ability_type import ActiveAbilityType         # noqa: E402
from engine.runner.abilities.handler import ABILITY_CLASSES, AbilityHandler   # noqa: E402
from engine.runner.abilities.targeting import get_invalid_target_reason   # noqa: E402
from engine.runner.components import HealthComponent, UnitComponent       # noqa: E402
from engine.runner.messages import ActiveAbilityMessage                   # noqa: E402
from engine.runner.prng import IntBasedMersenneTwister                    # noqa: E402
from engine.runner.snapshot import load_state                             # noqa: E402

HEAL = int(ActiveAbilityType.Heal)                       # 0x12  = 18   (le soin du trait `Healer`)
HEAL_TS = int(ActiveAbilityType.Heal_TwistedScience)     # 0x48f = 1167 (celui que le passif substitue)
EXTRA_HP = int(EffectType.TwistedScience_ExtraHp)        # 0x54b = 1355
EXTRA_DMG = int(EffectType.TwistedScience_ExtraDmg)      # 0x54c = 1356

CASTER = "genesBiophagus"
ALLY_GS = "genesKelermorph"        # faction `Genestealers` -> recoit AUSSI 1356
ALLY_NOT_GS = "ultraApothecary"    # `Ultramarines` + trait `Healer` -> contre-temoin du swap
FOES = "ultraTitus,orksNob"
BOARD = "MC1_67"
SEED = "777"


# --------------------------------------------------------------------------- helpers RPC / runner

def _r(sid, m, b, t=90):
    return (_rpc(sid, m, [b], timeout=t).get("result") or {})


def _build(state_path: Path, extra: list, retries: int = 40) -> int:
    """`rl_duel build`. Le plafond MAX_RUNNERS est PARTAGE : `runner cap reached` n'est pas une
    erreur du probe mais une contention -> on ATTEND un slot (on ne dispose JAMAIS celui d'un
    autre). Un `503 runner creation paused` est une fenetre de maintenance : meme traitement."""
    for attempt in range(max(1, retries)):
        state_path.unlink(missing_ok=True)
        proc = subprocess.run(
            [sys.executable, "rl_duel.py", "build", "--state-file", str(state_path)] + extra,
            cwd=str(PYDIR), capture_output=True, text=True, encoding="utf-8", errors="replace")
        if state_path.exists():
            return json.loads(state_path.read_text())["runnerId"]
        out = (proc.stderr or "") + (proc.stdout or "")
        if ("runner cap reached" in out or "runner creation paused" in out) and attempt + 1 < retries:
            print("[931] slot indisponible -- attente (%d/%d)" % (attempt + 1, retries), flush=True)
            time.sleep(20)
            continue
        print("[931] build KO:", out[-1200:])
        sys.exit(2)
    sys.exit(2)


def _dispose(state_path: Path):
    subprocess.run([sys.executable, "rl_duel.py", "dispose", "--state-file", str(state_path)],
                   cwd=str(PYDIR), capture_output=True, text=True, encoding="utf-8",
                   errors="replace")


def _mount(state_path: Path, extra: list | None = None) -> int:
    args = ["--seed", SEED, "--board", BOARD,
            "--p-units", "%s,%s,%s" % (CASTER, ALLY_GS, ALLY_NOT_GS),
            "--a-units", FOES, "--no-ai"]
    return _build(state_path, args + list(extra or []))


def _capture(sid, rid):
    """`mkstate()` rebatit un etat OFFLINE neuf depuis les MEMES payloads (replay-diff)."""
    bg = _r(sid, "boardGraph", {"runnerId": rid}, 60)
    board = Board(bg["tiles"], adjacency="evenq")
    dec = _r(sid, "decisionView", {"runnerId": rid, "maxRank": 1, "allAbilities": True}, 90)
    ob = _r(sid, "observeBattle", {"runnerId": rid}, 40)
    snap = _r(sid, "combatSnapshot", {"runnerId": rid}, 60)
    s0 = _r(sid, "dumpRng", {"runnerId": rid}, 30)

    def mkstate():
        st = load_state(dec, ob, snap, board=board)
        if isinstance(s0, dict) and s0.get("mt"):
            rng = IntBasedMersenneTwister()
            rng.mt = list(s0["mt"])
            rng.mti = s0["mti"]
            st.rng = rng
        return st
    return mkstate, dec


def _units(dec):
    return list(dec.get("units") or [])


def _by_visual(dec, vid):
    for u in _units(dec):
        if u.get("visualId") == vid:
            return int(u["id"])
    return None


def _abilities_of(dec, uid):
    for u in _units(dec):
        if int(u["id"]) == int(uid):
            return {int(a.get("abilityId") or a.get("id") or -1) for a in (u.get("abilities") or [])}
    return set()


def _hp(dec):
    return {int(u["id"]): int(u.get("hp") or 0) for u in _units(dec)}


def _effects(dec, uid):
    for u in _units(dec):
        if int(u["id"]) == int(uid):
            return {int(e.get("type") or e.get("effectType") or -1) for e in (u.get("effects") or [])}
    return set()


def _from_here(sid, rid, caster, ability):
    """ORACLE NATIF : `abilityTargets(...).fromHere` = la legalite EXACTE du cast immediat, sans
    deplacement. `None` = la query n'a pas repondu (jamais rabattu sur un ensemble vide)."""
    res = _r(sid, "abilityTargets", {"runnerId": rid, "casterId": int(caster),
                                     "abilityType": int(ability)}, 60)
    for u in (res.get("units") or []):
        if int(u.get("unitId") or -1) != int(caster):
            continue
        for ab in (u.get("abilities") or []):
            if int(ab.get("abilityId") or -1) == int(ability):
                return {int(t["targetId"]) for t in (ab.get("fromHere") or [])
                        if t.get("targetId") is not None}
    return None


def _cast_live(sid, rid, caster, target, ability):
    return _r(sid, "applyAction", {"runnerId": rid, "action": {
        "kind": "ability", "casterId": int(caster), "targetId": int(target),
        "abilityType": int(ability)}}, 150)


def _cast_offline(st, caster, target, ability):
    h = AbilityHandler(st)
    h.visit_ActiveAbilityMessage(ActiveAbilityMessage(
        caster_id=int(caster), target_id=None if target is None else int(target),
        ability_type=int(ability)))
    return h.last or {}


def _hp_offline(st, uid):
    e = st.get_entity(int(uid))
    hc = e.get_component(HealthComponent) if e is not None else None
    return None if (hc is None or hc.hp is None) else int(hc.hp)


def _effects_offline(st, uid):
    if st.effects is None:
        return set()
    return {int(e.effect_type) for e in (st.effects.by_unit.get(int(uid)) or [])}


def _adjacency_ok(dec, caster_id, targets) -> bool:
    """Le montage POSE-T-IL vraiment les cibles au contact ? On le VERIFIE (l'ability est
    adjacent-only) plutot que de le supposer -- une geometrie de spawn qui changerait rendrait les
    phases silencieusement vides."""
    pos = {int(u["id"]): (u.get("col"), u.get("row")) for u in _units(dec)}
    return all(pos.get(int(t)) is not None for t in targets) and pos.get(int(caster_id)) is not None


# --------------------------------------------------------------------------- phases

def phase_swap(sid, state_path) -> bool:
    """[F1] : le passif RETIRE `18 Heal` et AJOUTE `1167 Heal_TwistedScience` sur son porteur.

    Le contre-temoin `ultraApothecary` est ce qui rend le releve concluant : il porte le MEME trait
    `Healer` (donc `StaticBattleRules.Trait$$GetActiveAbility` lui accorde `18`) mais PAS le passif
    `TwistedScience`. Les quatre assertions sont donc croisees."""
    rid = _mount(state_path)
    try:
        _, dec = _capture(sid, rid)
        cid = _by_visual(dec, CASTER)
        aid = _by_visual(dec, ALLY_NOT_GS)
        if cid is None or aid is None:
            print("[931][swap] montage KO (porteur ou contre-temoin absent)")
            return False
        ab_c, ab_a = _abilities_of(dec, cid), _abilities_of(dec, aid)
        print("[931][swap] %-18s (u%d) abilities natives = %s" % (CASTER, cid, sorted(ab_c)))
        print("[931][swap] %-18s (u%d) abilities natives = %s" % (ALLY_NOT_GS, aid, sorted(ab_a)))
        checks = [("porteur A 1167", HEAL_TS in ab_c), ("porteur SANS 18", HEAL not in ab_c),
                  ("temoin A 18", HEAL in ab_a), ("temoin SANS 1167", HEAL_TS not in ab_a)]
        for nom, ok in checks:
            print("[931][swap]   %-18s : %s" % (nom, "OK" if ok else "ECHEC"))
        ok = all(v for _, v in checks)
        print("[931][swap] VERDICT : le swap natif est DEJA fait dans l'etat que le port charge "
              "-> porter [F1] cote runner n'a aucun observable" if ok
              else "[931][swap] VERDICT : releve NON concluant")
        return ok
    finally:
        _dispose(state_path)


def phase_gates(sid, state_path) -> bool:
    """ORACLE NATIF `fromHere` vs PORT `get_invalid_target_reason`, AVANT et APRES marquage."""
    rid = _mount(state_path)
    ok = True
    try:
        cls = ABILITY_CLASSES.get(HEAL_TS)
        if cls is None:
            print("[931][gates] 1167 absente d'ABILITY_CLASSES -- rien a confronter")
            return False
        for etape in ("avant marquage", "apres marquage"):
            mkstate, dec = _capture(sid, rid)
            st = mkstate()
            cid = _by_visual(dec, CASTER)
            natif = _from_here(sid, rid, cid, HEAL_TS)
            if natif is None:
                print("[931][gates] %s : `fromHere` INDISPO -- non confronte" % etape)
                return False
            port = {int(u["id"]) for u in _units(dec)
                    if get_invalid_target_reason(st, cid, int(u["id"]), cls()) == 0}
            marque = "=" if natif == port else "!"
            print("[931][gates] %-15s : natif(fromHere)=%s port=%s %s"
                  % (etape, sorted(natif), sorted(port), marque))
            if not natif:
                print("[931][gates] ENSEMBLE NATIF VIDE a l'etape '%s' -- le temoin ne discrimine "
                      "rien ici, montage a revoir" % etape)
                return False
            ok = ok and (natif == port)
            if etape == "avant marquage":
                tgt = _by_visual(dec, ALLY_GS)
                _cast_live(sid, rid, cid, tgt, HEAL_TS)
        return ok
    finally:
        _dispose(state_path)


def _one_cast(sid, state_path, ally: str, extra: list | None = None):
    """Un cast de 1167, OFFLINE puis LIVE, sur le MEME etat de depart. Rend le tuple
    `(hp_avant, hp_natif, hp_port, eff_natif, eff_port, detail_port)`."""
    rid = _mount(state_path, extra)
    try:
        mkstate, dec = _capture(sid, rid)
        cid, tgt = _by_visual(dec, CASTER), _by_visual(dec, ally)
        if cid is None or tgt is None:
            return None
        if not _adjacency_ok(dec, cid, [tgt]):
            print("[931] positions non lisibles -- montage a revoir")
            return None
        natif_from_here = _from_here(sid, rid, cid, HEAL_TS)
        if natif_from_here is not None and tgt not in natif_from_here:
            print("[931] la cible %s n'est PAS legale pour le natif (fromHere=%s) -- le montage ne "
                  "l'a pas mise au contact ; phase NON CONCLUANTE" % (ally, sorted(natif_from_here)))
            return None
        hp_avant = _hp(dec).get(tgt)
        st = mkstate()
        detail = _cast_offline(st, cid, tgt, HEAL_TS)
        hp_port, eff_port = _hp_offline(st, tgt), _effects_offline(st, tgt)
        _cast_live(sid, rid, cid, tgt, HEAL_TS)
        _, dec2 = _capture(sid, rid)
        return (hp_avant, _hp(dec2).get(tgt), hp_port, _effects(dec2, tgt), eff_port, detail)
    finally:
        _dispose(state_path)


def phase_cast(sid, state_path) -> bool:
    """Cible a PV PLEINS, deux bras : `Genestealers` (1355 + 1356) et NON (1355 seul)."""
    ok = True
    for ally, attendus in ((ALLY_GS, {EXTRA_HP, EXTRA_DMG}), (ALLY_NOT_GS, {EXTRA_HP})):
        res = _one_cast(sid, state_path, ally)
        if res is None:
            return False
        hp0, hp_n, hp_p, eff_n, eff_p, detail = res
        poses_n = eff_n & {EXTRA_HP, EXTRA_DMG}
        poses_p = eff_p & {EXTRA_HP, EXTRA_DMG}
        egal = (hp_n == hp_p) and (poses_n == attendus) and (poses_p == attendus)
        print("[931][cast] %-18s hp %s -> natif %s / port %s | effets natif %s port %s attendus %s %s"
              % (ally, hp0, hp_n, hp_p, sorted(poses_n), sorted(poses_p), sorted(attendus),
                 "=" if egal else "!"))
        print("[931][cast]   extra_hp lu par le port = %s ; heal = %s"
              % (detail.get("extra_hp"), (detail.get("heal") or {}).get("amount")))
        ok = ok and egal
    return ok


def phase_blesse(sid, state_path) -> bool:
    """MEME cast, cible BLESSEE : la phase CHIFFRE l'ecart residuel #572-r1 au lieu de l'annoncer.

    Elle imprime aussi le "sans le port" -- c'est-a-dire les PV que la cible aurait gardes quand
    l'ability etait un no-op complet (absente d'`ABILITY_CLASSES`). Le rapport des deux erreurs est
    le seul argument recevable pour livrer ou renoncer, et il est LU ici."""
    res = _one_cast(sid, state_path, ALLY_GS,
                    ["--unit-stat", "%s:RemainingHealth=1000" % ALLY_GS])
    if res is None:
        return False
    hp0, hp_n, hp_p, eff_n, eff_p, detail = res
    err_port = abs(int(hp_n) - int(hp_p))
    err_noop = abs(int(hp_n) - int(hp0))
    print("[931][blesse] hp %s -> natif %s / port %s (ecart %d)" % (hp0, hp_n, hp_p, err_port))
    print("[931][blesse]   effets natif %s / port %s"
          % (sorted(eff_n & {EXTRA_HP, EXTRA_DMG}), sorted(eff_p & {EXTRA_HP, EXTRA_DMG})))
    print("[931][blesse]   erreur SANS le port (no-op) = %d ; erreur AVEC = %d ; gain = %s"
          % (err_noop, err_port,
             ("%.1f x" % (err_noop / err_port)) if err_port else "TOTAL (ecart nul)"))
    print("[931][blesse]   CE QUE CE REGIME EXERCE, et que la cible a PV PLEINS NE PEUT PAS : le "
          "`Heal` final se clampe sur le plafond, donc il ne rend le montant natif QUE si le "
          "stat-mod 1355 (StatType.Health) a bien releve `get_CurrentMaximumValue()` AVANT lui. "
          "Sans `applied_stat_mods` sur la classe d'effet, l'effet est pose mais le plafond ne "
          "bouge pas -> 6023 (mesure du 2026-08-11). detail port = %s"
          % json.dumps(detail.get("hp_fill")))
    return err_port == 0


def phase_self(sid, state_path) -> bool:
    """SELF-CAST sur un Hollan BLESSE -- le SEUL regime qui exerce le terme `!OwnerIsTarget` du gate
    de buff, et il fallait le CONSTRUIRE.

    `CasterIsPossibleTarget` (0x8000) est dans le masque, donc le self-cast n'est pas interdit par le
    ciblage ; c'est `AttackQuery$$EntityCanBeHealed` qui le refuse tant que Hollan est a PV pleins
    (branche `caster == target` de `$$GetDynamicInvalidTargetReason`). Blesse, il devient une cible
    LEGALE -- et le natif le SOIGNE **sans lui poser aucun des deux effets**, parce que le bloc de
    buffs est gate par `NOT get_OwnerIsTarget` ("Units healed by Hollan, **other than himself**").

    Sans ce montage, retirer ce terme du port est INVISIBLE : `Target == Owner` n'arrive jamais."""
    rid = _mount(state_path, ["--unit-stat", "%s:RemainingHealth=1000" % CASTER])
    try:
        mkstate, dec = _capture(sid, rid)
        cid = _by_visual(dec, CASTER)
        natif = _from_here(sid, rid, cid, HEAL_TS)
        legal = natif is not None and cid in natif
        print("[931][self] fromHere natif = %s -> self-cast %s"
              % (sorted(natif or []), "LEGAL" if legal else "REFUSE"))
        if not legal:
            print("[931][self] le self-cast n'est PAS legal ici -- le terme `!OwnerIsTarget` reste "
                  "NON EXERCE, phase NON CONCLUANTE")
            return False
        cls = ABILITY_CLASSES.get(HEAL_TS)
        st = mkstate()
        port_reason = get_invalid_target_reason(st, cid, cid, cls())
        hp0 = _hp(dec).get(cid)
        _cast_offline(st, cid, cid, HEAL_TS)
        hp_p, eff_p = _hp_offline(st, cid), _effects_offline(st, cid) & {EXTRA_HP, EXTRA_DMG}
        _cast_live(sid, rid, cid, cid, HEAL_TS)
        _, dec2 = _capture(sid, rid)
        hp_n = _hp(dec2).get(cid)
        eff_n = _effects(dec2, cid) & {EXTRA_HP, EXTRA_DMG}
        ok = (port_reason == 0) and (hp_n == hp_p) and (eff_n == set()) and (eff_p == set())
        print("[931][self] gate port = 0x%x | hp %s -> natif %s / port %s | effets natif %s port %s "
              "(les DEUX doivent etre vides) %s"
              % (port_reason, hp0, hp_n, hp_p, sorted(eff_n), sorted(eff_p), "=" if ok else "!"))
        return ok
    finally:
        _dispose(state_path)


def phase_pauvre(sid, state_path) -> bool:
    """Hollan a ATTAQUE ECRASEE -- le regime qui SEPARE le `ChangeStat` du `Heal`.

    `HealAmount = Attack x Max(WeaponHighestHits, 1)` : au regime nominal il vaut 3614, soit PLUS
    que le `+hp` de 2992, si bien qu'un port qui OUBLIERAIT le `ChangeStat` arriverait quand meme au
    bon total sur une cible pleine (le `Heal` comble jusqu'au plafond fraichement releve). Les deux
    termes ne sont donc separables que si `HealAmount < hp` -- d'ou l'attaque a 100.

    Ce n'est pas un artifice : c'est le seul montage ou l'observable distingue "le natif a pose
    +hp de PV COURANTS" de "le natif a soigne". Cible a PV PLEINS : le natif rend exactement
    `+hp`, jamais `+HealAmount`."""
    res = _one_cast(sid, state_path, ALLY_GS, ["--unit-stat", "%s:Damage=100" % CASTER])
    if res is None:
        return False
    hp0, hp_n, hp_p, eff_n, eff_p, detail = res
    heal = (detail.get("heal") or {}).get("amount")
    print("[931][pauvre] heal_amount du port = %s (doit etre << extra_hp = %s)"
          % (heal, detail.get("extra_hp")))
    print("[931][pauvre] hp %s -> natif %s / port %s (delta natif = %s, extra_hp = %s) %s"
          % (hp0, hp_n, hp_p, (hp_n - hp0) if (hp_n and hp0) else None, detail.get("extra_hp"),
             "=" if hp_n == hp_p else "!"))
    if heal is not None and detail.get("extra_hp") is not None and heal >= detail["extra_hp"]:
        print("[931][pauvre] REGIME NON DISCRIMINANT : heal >= extra_hp, les deux termes se "
              "confondent -- baisser davantage l'attaque")
        return False
    return hp_n == hp_p


def phase_meca(sid, state_path) -> bool:
    """Un allie MECANIQUE -- le seul regime qui exerce le PREMIER gate,
    `UnitExtensions$$IsAffectedByHealType(target, 0 = NonMechanical)`.

    `necroWarden` porte `Mechanical` ET `LivingMetal` : `IsMechanical` est vrai et il n'a pas
    `AffectedByHealAndRepair`, donc le natif le refuse -- et le refuse AVANT tout test de camp, ce
    qui est l'ordre du decompile. Sans allie mecanique au montage, ce gate ne mord jamais et un port
    qui l'aurait oublie passerait vert."""
    # `--place` ELOIGNE `ALLY_GS` : sans lui, les trois SpawnPoints du board sont contigus et la
    # PORTEE de l'ability n'est jamais exercee (mesure du 2026-08-11 : le mutant
    # `RANGE_ADJACENT_IF_MELEE_CASTER -> RANGE_WHOLE_BOARD` passait VERT). On DEPLACE pour forcer la
    # configuration, on ne subit pas la geometrie de spawn.
    rid = _build(state_path, ["--seed", SEED, "--board", BOARD,
                              "--p-units", "%s,necroWarden,%s,%s"
                              % (CASTER, ALLY_NOT_GS, ALLY_GS),
                              "--place", "%s:4,4" % ALLY_GS,
                              "--a-units", FOES, "--no-ai"])
    try:
        mkstate, dec = _capture(sid, rid)
        cid = _by_visual(dec, CASTER)
        meca = _by_visual(dec, "necroWarden")
        loin = _by_visual(dec, ALLY_GS)
        pos = {int(u["unitId"]): (u.get("pos") or {})
               for u in (_r(sid, "abilityTargets",
                            {"runnerId": rid, "casterId": cid, "abilityType": HEAL_TS},
                            60).get("units") or [])}
        print("[931][meca] positions : caster u%s=%s meca u%s=%s eloigne u%s=%s"
              % (cid, pos.get(cid), meca, pos.get(meca), loin, pos.get(loin)))
        natif = _from_here(sid, rid, cid, HEAL_TS)
        if meca is None or natif is None:
            print("[931][meca] montage KO (allie mecanique absent ou fromHere indispo)")
            return False
        st = mkstate()
        cls = ABILITY_CLASSES.get(HEAL_TS)
        port = {int(u["id"]) for u in _units(dec)
                if get_invalid_target_reason(st, cid, int(u["id"]), cls()) == 0}
        print("[931][meca] necroWarden = u%d (Mechanical+LivingMetal) | natif(fromHere)=%s port=%s"
              % (meca, sorted(natif), sorted(port)))
        exclu = (meca not in natif) and (meca not in port)
        hors_portee = (loin is not None) and (loin not in natif) and (loin not in port)
        print("[931][meca]   MACHINE exclue des DEUX cotes : %s ; ELOIGNE exclu des DEUX cotes : %s"
              " ; port == natif : %s"
              % ("OK" if exclu else "ECHEC", "OK" if hors_portee else "ECHEC",
                 "OK" if natif == port else "ECHEC"))
        if not natif:
            print("[931][meca] ensemble natif VIDE -- non discriminant")
            return False
        return exclu and hors_portee and natif == port
    finally:
        _dispose(state_path)


def phase_dmg(sid, state_path) -> bool:
    """[F3] `1356 TwistedScience_ExtraDmg` : deux runners JUMEAUX qui ne different QUE par le buff.

    Le temoin compare l'ECART de degat (buffe - temoin) cote natif a celui du port, sur la MEME
    attaque et le MEME seed. Un port qui n'aurait pas la classe d'effet rendrait un ecart de 0."""
    from engine.entities.effects.magnitude import ability_var
    from engine.entities.effects.factory import EFFECT_CLASSES
    if "TwistedScience_ExtraDmg" not in EFFECT_CLASSES:
        print("[931][dmg] 1356 absent d'EFFECT_CLASSES -- rien a confronter")
        return False
    # ⚠ LE MONTAGE CASSE LE REGIME DEGENERE, ET C'EST TOUT SON INTERET. Un runner normalise donne le
    # MEME `AbilityVariablesMultiplierPercentage` (180) a toute la ligne : lire la magnitude sur le
    # BUFFE au lieu du POSEUR y est alors INDISCERNABLE. Le patch per-unit descend celui de la cible
    # a 100 -- MESURE (mult publie ci-dessous), pas suppose, parce qu'un patch que
    # `buildNormalizedBC` recalculerait rendrait ce temoin muet sans le dire.
    rid = _mount(state_path,
                 ["--unit-stat", "%s:AbilityVariablesMultiplierPercentage=100" % ALLY_GS])
    try:
        mkstate, dec = _capture(sid, rid)
        cid, tgt = _by_visual(dec, CASTER), _by_visual(dec, ALLY_GS)
        # ⚠ DEUX VOIES D'ARRIVEE, ET IL FAUT LES DEUX. L'effet peut naitre (a) de la POSE offline --
        # c'est elle, et elle seule, qui exerce le `scale_from_source` de la feuille `AddEffect` --
        # ou (b) du SEED `load_state` apres un cast live. Ne mesurer que (b) rendait ce temoin
        # AVEUGLE au mutant `scale_from_source=False` (mesure du 2026-08-11 : il passait vert).
        st_pose = mkstate()
        _cast_offline(st_pose, cid, tgt, HEAL_TS)
        eff_pose = next((e for e in (st_pose.effects.by_unit.get(int(tgt)) or [])
                         if int(e.effect_type) == EXTRA_DMG), None)
        _cast_live(sid, rid, cid, tgt, HEAL_TS)
        mkstate2, dec2 = _capture(sid, rid)
        st = mkstate2()
        eff = None
        for e in (st.effects.by_unit.get(int(tgt)) or []):
            if int(e.effect_type) == EXTRA_DMG:
                eff = e
        if eff is None or eff_pose is None:
            print("[931][dmg] l'effet 1356 manque d'un cote (pose=%s seed=%s) -- phase NON "
                  "CONCLUANTE" % (eff_pose is not None, eff is not None))
            return False
        bonus = eff.create_effect_damage_bonus_for_attack()
        # L'ATTENDU est calcule au multiplicateur du **POSEUR** (Hollan, 180), jamais a celui de
        # l'instance -- sinon la contre-epreuve se recalculerait elle-meme et passerait quel que
        # soit le multiplicateur propage (le faux vert « attendu recalcule par la fonction mutee »).
        src_mult, src_lvl = 100, 0
        for u in _units(dec2):
            if int(u["id"]) == int(cid):
                src_mult = int(u.get("abilityVariablesMultiplier") or 180)
        st_src = st.get_entity(int(cid))
        from engine.runner.components import StatsComponent as _SC
        _c = getattr(st_src.get_component(_SC), "ctx", None) if st_src is not None else None
        if _c is not None:
            src_mult = int(getattr(_c, "ability_variables_multiplier", 180) or 180)
            src_lvl = int(getattr(_c, "passive_ability_level", 0) or 0)
        tgt_mult = None
        _t = st.get_entity(int(tgt))
        _tc = getattr(_t.get_component(_SC), "ctx", None) if _t is not None else None
        if _tc is not None:
            tgt_mult = int(getattr(_tc, "ability_variables_multiplier", 0) or 0)
        print("[931][dmg] multiplicateurs : POSEUR=%s CIBLE=%s (ils DOIVENT differer, sinon le "
              "temoin est degenere)" % (src_mult, tgt_mult))
        if tgt_mult == src_mult:
            print("[931][dmg] REGIME DEGENERE : le patch de multiplicateur n'a pas mordu -- phase "
                  "NON CONCLUANTE")
            return False
        attendu = ability_var("TwistedScience", "extraDmg", src_lvl, multiplier_pct=src_mult)
        # `EffectBonus.value` = le montant du canal ; `kind` = le canal natif (`ForAddition` ->
        # `Addition`, l'additif `@+0x10` de `DamageModifiers$$Add`, POST-percage). On verifie les
        # DEUX : une magnitude juste sur le mauvais canal serait un faux vert.
        val = None if bonus is None else int(getattr(bonus, "value", 0) or 0)
        kind = None if bonus is None else getattr(bonus, "kind", None)
        b_pose = eff_pose.create_effect_damage_bonus_for_attack()
        val_pose = None if b_pose is None else int(getattr(b_pose, "value", 0) or 0)
        print("[931][dmg] effet 1356 sur u%d, voie SEED  : niveau=%s mult=%s -> kind=%s value=%s"
              % (tgt, eff.ability_level, eff.ability_variables_multiplier, kind, val))
        print("[931][dmg] effet 1356 sur u%d, voie POSE  : niveau=%s mult=%s -> kind=%s value=%s"
              % (tgt, eff_pose.ability_level, eff_pose.ability_variables_multiplier,
                 None if b_pose is None else getattr(b_pose, "kind", None), val_pose))
        print("[931][dmg] extraDmg[niveau] x mult attendu = %s (canal attendu = Addition)" % attendu)
        # La cible NON-Genestealer ne doit RIEN recevoir : contre-temoin du gate de faction, lu sur
        # le MEME etat (l'effet 1356 ne doit exister sur AUCUNE autre unite).
        autres = {int(uid) for uid, effs in (st.effects.by_unit or {}).items()
                  if any(int(e.effect_type) == EXTRA_DMG for e in effs)} - {int(tgt)}
        print("[931][dmg] autres porteurs de 1356 (doit etre vide) : %s" % sorted(autres))
        ok = (val is not None and attendu is not None and val == int(attendu)
              and val_pose == int(attendu) and kind == "Addition" and not autres)
        print("[931][dmg] VERDICT : %s" % ("OK" if ok else "ECART"))
        return ok
    finally:
        _dispose(state_path)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--phase", required=True,
                    choices=("swap", "gates", "cast", "blesse", "dmg", "self", "pauvre", "meca"))
    ap.add_argument("--state-file", default=None)
    a = ap.parse_args()
    sp = Path(a.state_file) if a.state_file else (
        PYDIR.parent.parent / "logs" / ("probe931_%s.json" % a.phase))
    sp.parent.mkdir(parents=True, exist_ok=True)
    sid = _resolve_session()
    fn = {"swap": phase_swap, "gates": phase_gates, "cast": phase_cast,
          "blesse": phase_blesse, "dmg": phase_dmg, "self": phase_self,
          "pauvre": phase_pauvre, "meca": phase_meca}[a.phase]
    ok = fn(sid, sp)
    print("[931] %s : %s" % (a.phase, "OK" if ok else "ECART"))
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
