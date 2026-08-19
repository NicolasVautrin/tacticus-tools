"""probe #419-r1-tr14-r5-r2-r1-r2-r1 -- la REGLE DYNAMIQUE de l'attaque normale.

QUESTION BINAIRE
    Le port refuse-t-il EXACTEMENT ce que la regle dynamique de l'attaque normale refuse -- ni plus
    (il casserait du ciblage legitime), ni moins (l'ecart PERMISSIF qu'une politique entrainee
    exploiterait) ?

CHAINE NATIVE (decompile = verite, relue sur le build courant)

  `IdunBattleLogic.Entities.Abilities.Active.Loki.ALoki_NormalAttackAbility$$GetDynamicInvalidTargetReason`
  (5 parametres : `caster, casterTile, target, targetTiles`) :

      w = <IBattleQuery slot 0xb0>(caster, casterTile, targetTiles)
      return (w != null) ? 0 : 2 /* TargetMatchesDynamicRule */

  Le slot `0xb0` est `IdunBattle.Core.Services.BattleQuery$$GetAttackWeaponForDefaultNormalAttack`
  -- mais LAQUELLE de ses TROIS surcharges, et ce n'est pas indifferent :

      0xae  (attacker, attackerTiles)              chaine de repli melee<->ranged
      0xaf  (attacker, attackerTiles, target)      `GetAbilityAttackRangeType`, `HasFlag(0x15)`
      0xb0  (attacker, attackerTiles, targetTiles) `AreTilesAdjacent` -> melee OU ranged   <= CELLE-CI

  Appariement LU, pas suppose : `IdunBattle.View.FSM.VisualBattleQuery$$GetAttackWeaponForDefaultNormalAttack`
  (2 arguments) delegue au slot `0xae`, ce qui FIXE l'arite ; et les deux surcharges de
  `IdunBattleLogic.Entities.Abilities.Active.Loki.ALoki_NormalAttackAbility$$FindAttackWeapon`
  appellent respectivement `0xaf` (parametre `target`) et `0xb0` (parametre `targetTiles`).

      GetAttackWeaponForDefaultNormalAttack(attacker, attackerTiles, targetTiles):
          if (MovementUtil.AreTilesAdjacent(attackerTiles, targetTiles))   # surcharge LISTE
               return FindMeleeWeapon(attacker, null, null)
          else return FindRangedWeapon(attacker)

  `FindMeleeWeapon` / `FindRangedWeapon` filtrent les `WeaponProfile` par
  `IdunShared.Battle.WeaponProfile$$get_IsMelee` (`!Range.HasValue || Range.Value < 2`) puis
  `IdunBattle.Core.Services.BattleQuery$$SelectMaxRangeWeapon`, qui rend **null sur un ensemble
  VIDE**. C'est la SEULE porte de sortie `null`, donc le seul regime de refus.

LE DISCRIMINANT, ENONCE AVANT LA MESURE

  Ventilation du catalogue (683 unites, re-derivee -- pas heritee) :
    * caster sans arme A DISTANCE, cible NON adjacente (271 unites) -> le natif refuse ici aussi,
      mais le volet PORTEE a deja refuse EN AMONT (`onlyAdjacent = IfNotRangedCaster` vrai pour un
      caster non-ranged). Meme verdict, autre raison : PAS un discriminant.
    * caster sans arme de MELEE, cible ADJACENTE -> **0 unite** au catalogue. Regime VIDE.
    * caster sans AUCUNE ARME -> les deux branches rendent null : le natif refuse TOUTE cible.
      **C'est le seul regime ou ce port deplace un verdict.** 81 unites, dont 79 portent le bit.

  Donc le discriminant est : **caster SANS AUCUNE ARME, cible ADJACENTE**.
      natif        REFUSE  (0x2 TargetMatchesDynamicRule)
      port AVANT   ACCEPTE (0x0)   <- l'ecart PERMISSIF
      port APRES   REFUSE  (0x2)

  Et le TEMOIN, qui garde le sens inverse (aucune cible legitime perdue) :
      **caster ARME, meme cible adjacente** -> les TROIS acceptent.

MONTAGE -- DEUX SUMMONS DE LA MEME EQUIPE, UNE SEULE VARIABLE

  `genesPrimus` (HERO, au pool) porte l'ability ACTIVE `CultDemagogue` (1179), qui invoque
  d'un coup des `genesSmnDecoy` **et** des `genesSmnNeophyte`. Les deux sont des SUMMONS de la meme
  equipe, portent la meme attaque normale `69`, et ne different que par UN champ :

      genesSmnDecoy     weapons = []                              <- le CASTER du discriminant
      genesSmnNeophyte  weapons = [melee Physical, Projectile R2] <- le CASTER du TEMOIN

  C'est ce qui rend le temoin probant : il ne change ni l'equipe, ni la classe d'entite, ni le type
  d'attaque normale, ni la geometrie -- seulement la presence d'armes.

  ⚠ SUBSTRATS CONCORDANTS, et c'est indispensable : `genesSmnDecoy` a `weapons = []` AU KIT **et**
  `Weapons = []` dans `BC.Units`. Le port lit le kit gameconfig la ou le natif lit le
  `WeaponsComponent` ; un montage qui ne viderait QUE le BC mesurerait la divergence des SUBSTRATS
  au lieu de la REGLE (residu nomme dans la case-doc).

  Geometrie PILOTEE (jamais subie), en DEUX etages -- et le second a ete ajoute parce que le
  premier NE SUFFIT PAS :

    1. on amene `genesPrimus` au contact d'un ennemi, PUIS on caste. Necessaire, pas suffisant :
       les summons n'apparaissent PAS tous autour du caster. Mesure (`MC1_67`/`4192`, ancre en
       `(5, 7)`, ennemis en `(6, 7)` / `(6, 8)` / `(5, 8)`) : les trois `genesSmnDecoy` tombent en
       `(4, 6)`, `(3, 6)` et `(1, 1)`, soit `d = 2`, `3` et `9`. **AUCUN decoy adjacent** -- le
       montage rendait `MontageError` et les trois fichiers de la famille ERROR-aient, sans qu'aucun
       port soit en cause. Les `genesSmnNeophyte`, eux, en avaient un : le TEMOIN etait monte et le
       DISCRIMINANT non, la pire des deux moities ;
    2. `forcer_contact` (ci-dessous) amene un ENNEMI a `d = 1`. Sa doc porte les trois faits mesures
       qui en fixent la forme -- summons non activables, ennemis activables seulement quand leur
       camp a la main, et geometrie detruite si on rend la main a notre camp.

  ⚠ Un summon ne se COMMANDE pas (#291) -- mais on ne le commande pas : `abilityReason` est une
  REQUETE d'oracle, et le summon est une entite de `decisionView.units` comme une autre.

VERDICT
  rc 0 si (a) le montage a MORDU (decoy vivant, `normal == 69`, au moins un ennemi adjacent),
  (b) le port APRES est en accord TOTAL avec le natif, (c) la BASELINE diverge sur au moins une
  ligne -- sinon le regime est DEGENERE et le probe le DIT au lieu de se declarer vert --, et
  (d) AUCUNE ligne perdue (aucune cible que le natif accepte et que le port APRES refuse).
"""
from __future__ import annotations

import argparse
import itertools
import json
import os
import subprocess
import sys
import time
from pathlib import Path

PYDIR = Path(__file__).resolve().parent
ROOT = PYDIR.parent.parent
sys.path.insert(0, str(PYDIR))

import hexgeo                                                        # noqa: E402
from rl_collect_batch import _resolve_session                        # noqa: E402

import probe_247_splash_targeting as P247                            # noqa: E402
import probe_436_taunt_targeting as P436                             # noqa: E402

from engine.runner.abilities.targeting import (                      # noqa: E402
    NORMAL_ATTACK_TARGETING_OPTIONS_BY_TYPE as OPTS,
    _NormalAttackTargeting, get_invalid_target_reason)
from engine.runner.abilities.targeting_rule import TargetingRule as TR   # noqa: E402

_seq = itertools.count(1)

#: `genesPrimus` (HERO, au pool) -> `CultDemagogue` invoque les DEUX summons en un seul cast.
ANCHOR_VIS = "genesPrimus"
CULT_DEMAGOGUE = 1179               # `ActiveAbilityType.CultDemagogue`
NOWEAPON_VIS = "genesSmnDecoy"      # `weapons = []` au kit ET dans `BC.Units`  -> DISCRIMINANT
ARMED_VIS = "genesSmnNeophyte"      # meme equipe, meme type d'attaque normale, ARME -> TEMOIN
GENERIC_TYPE = 69                   # `ActiveAbilityType.Loki_NormalAttack`, masque `0x4002`
P_UNITS = "genesPrimus,genesMagus"
A_UNITS = "tauCrisis,tauMarksman,necroSpyder"


class _NoDynamicRule(_NormalAttackTargeting):
    """La BASELINE -- le corps EXACT d'avant #419-r1-tr14-r5-r2-r1-r2-r1 (`return 0`, la regle
    dynamique n'etait pas portee). Elle sert a DEUX choses, et c'est la meme mesure : chiffrer
    l'ecart ferme, et prouver que le regime n'est pas DEGENERE (si baseline == port, la mesure ne
    prouve rien, quel que soit l'accord avec le natif)."""

    def get_dynamic_invalid_target_reason(self, state, caster_id, target_id) -> int:
        return 0


class MontageError(RuntimeError):
    """Le montage n'a pas MORDU (pas de decoy vivant, type non generique, aucun ennemi adjacent).
    ECHEC DE MONTAGE, pas un verdict sur le port -- il doit ROUGIR, jamais partir en skip vert."""


def _build(sid, seed, board):
    """`rl_duel build` avec state-file PROPRE sous `logs/`. ATTEND si `MAX_RUNNERS` est sature (le
    cap est PARTAGE entre agents)."""
    state = ROOT / "logs" / ("_probe419r5r2r1r2r1-%d-%d.json" % (os.getpid(), next(_seq)))
    state.parent.mkdir(parents=True, exist_ok=True)
    argv = [sys.executable, "rl_duel.py", "build", "--seed", str(seed),
            "--state-file", str(state), "--board", board, "--no-ai",
            "--p-units", P_UNITS, "--a-units", A_UNITS]
    deadline = time.time() + 300
    while True:
        state.unlink(missing_ok=True)
        p = subprocess.run(argv, cwd=str(PYDIR), capture_output=True, text=True,
                           encoding="utf-8", errors="replace")
        if state.exists():
            return int(json.loads(state.read_text())["runnerId"]), state
        out = (p.stderr or p.stdout or "")
        if "runner cap reached" not in out or time.time() >= deadline:
            raise RuntimeError("build KO : " + out[-600:])
        time.sleep(10)


def _normal_attack_id(u):
    """L'id CONCRET publie par `decisionView` pour l'attaque normale de `u` (=
    `ActiveAbilityComponent.NormalAttackType@0x28`). `None` = non publie."""
    for ab in (u.get("abilities") or []):
        if ab.get("kind") == "normal" and ab.get("id") is not None:
            return int(ab["id"])
    return None


def _live(dv, vis):
    return [u for u in (dv.get("units") or []) if u.get("visualId") == vis and u.get("alive")]


def _foes_of(dv, u):
    return [f for f in (dv.get("units") or [])
            if f.get("alive") and f.get("owner") != u.get("owner")]


def _drive_and_summon(sid, rid, rounds=16):
    """Amene `genesPrimus` AU CONTACT d'un ennemi, PUIS caste `CultDemagogue` : les summons
    apparaissent autour du caster, donc au contact. C'est l'ordre qui compte -- cf. la note de
    montage en tete de module."""
    for it in range(rounds):
        dv = P247._dv(sid, rid)
        me = P247._by_vis(dv, ANCHOR_VIS)
        if me is None:
            raise MontageError("ancre `%s` absente ou morte au tour %d" % (ANCHOR_VIS, it))
        foes = _foes_of(dv, me)
        if not foes:
            raise MontageError("aucun ennemi vivant")
        near = min(foes, key=lambda f: hexgeo.distance(P247._pos(me), P247._pos(f)))
        d = hexgeo.distance(P247._pos(me), P247._pos(near))
        print("  [drive %d] ancre@%s d_min=%d (vers u%s@%s)"
              % (it, P247._pos(me), d, near["id"], P247._pos(near)))
        if d <= 1:
            break
        if not P247._step_toward(sid, rid, int(me["id"]), P247._pos(near), 1):
            P247._act(sid, rid, {"kind": "endturn"}, 60)
    else:
        raise MontageError("l'ancre n'a pas atteint le contact en %d tours" % rounds)

    dv = P247._dv(sid, rid)
    me = P247._by_vis(dv, ANCHOR_VIS)
    tg = P247._r(sid, "abilityTargets",
                 {"runnerId": rid, "casterId": int(me["id"]), "abilityType": CULT_DEMAGOGUE}, 60)
    # `fromHere` = LEGALITE EXACTE du cast immediat (`targets` est un superset « move inclus »).
    choice = None
    for u in (tg.get("units") or []):
        for a in (u.get("abilities") or []):
            if a.get("abilityId") == CULT_DEMAGOGUE and a.get("fromHere"):
                choice = a["fromHere"][0]
    if choice is None:
        raise MontageError("`CultDemagogue` non castable depuis la position atteinte")
    print("  cast %s -> cible u%s %s" % (CULT_DEMAGOGUE, choice.get("targetId"),
                                         choice.get("visualId")))
    P247._act(sid, rid, {"kind": "ability", "casterId": int(me["id"]),
                         "targetId": int(choice["targetId"]),
                         "abilityType": CULT_DEMAGOGUE}, 120)
    return P247._dv(sid, rid)


def _pick_adjacent(dv, vis):
    """Le premier summon VIVANT de `vis` ayant au moins UN ennemi a d=1. `None` = non monte."""
    for u in _live(dv, vis):
        if any(hexgeo.distance(P247._pos(u), P247._pos(f)) == 1 for f in _foes_of(dv, u)):
            return u
    return None


def _current_player(sid, rid):
    return P247._r(sid, "battleStatus", {"runnerId": rid}, 40).get("currentPlayer")


def _hand_to(sid, rid, player: int, maxit: int = 6) -> bool:
    """Passe la main au camp `player` a coups d'`endturn`. Le runner est `--no-ai` : rendre la main
    a l'adversaire ne le fait PAS jouer, il rend seulement ses unites ACTIVABLES."""
    for _ in range(maxit):
        if _current_player(sid, rid) == player:
            return True
        P247._act(sid, rid, {"kind": "endturn"}, 90)
    return _current_player(sid, rid) == player


def _paires(dv, vis):
    """`(distance, id summon, id ennemi, pos summon)` triees, pour tous les summons vivants."""
    out = []
    for s in _live(dv, vis):
        for f in _foes_of(dv, s):
            out.append((hexgeo.distance(P247._pos(s), P247._pos(f)), int(s["id"]), int(f["id"]),
                        P247._pos(s)))
    return sorted(out)


def forcer_contact(sid, rid, vis_list=(NOWEAPON_VIS, ARMED_VIS), rounds: int = 8) -> dict:
    """PILOTE la geometrie du contact : amene un ENNEMI a `d = 1` d'au moins un summon de CHAQUE
    `vis` demande. Rend `{vis: distance minimale atteinte}`.

    DEUX FAITS MESURES gouvernent cette fonction, et ils vont dans des sens opposes :

      1. **Les summons ne sont PAS activables** -- `aiMovableTiles` les publie avec `tiles = []`
         (mesure : les trois `genesSmnDecoy` du montage, zero tuile), conformement a #291 : le natif
         termine le tour de toute unite qui apparait pendant le tour de son proprietaire. On ne peut
         donc PAS rapprocher le summon ; il faut rapprocher l'ENNEMI.
      2. **Un ennemi n'est activable que quand son camp a la main.** Pendant notre tour,
         `aiMovableTiles` ne publie QUE nos unites (mesure : `[83, 85, 109, ...]`, aucun id adverse),
         donc un `move` sur un ennemi n'a aucune tuile legale ou aller. C'est precisement le cran qui
         manquait a la version anterieure de cette approche, qui concluait « u%d n'est pas activable
         sans consommer un tour -- arret ». Il faut RENDRE LA MAIN a l'adversaire d'abord.

    ET ON N'EN REVIENT PAS : au retour de la main a notre camp, `PlayAutomaticUnits` joue les
    summons au turn-start (trait `Summon`) -- mesure : les huit `genesSmnNeophyte` se deplacent, un
    `genesSmnDecoy` est remplace, et l'ennemi qu'on venait d'amener au contact MEURT. La geometrie
    installee ici ne survit donc pas a un `endturn` de plus, et la mesure se fait **pendant le tour
    adverse**. `abilityReason` y repond normalement (mesure : `0x2` sur le decoy adjacent, `0x0` sur
    le neophyte adjacent, `0x8000000` sur les cibles lointaines) -- c'est une REQUETE d'oracle, pas
    une action, et elle ne demande pas que le caster soit activable."""
    besoin = [v for v in vis_list]
    rep = {}
    for _ in range(rounds):
        dv = P247._dv(sid, rid)
        reste = []
        for vis in besoin:
            paires = _paires(dv, vis)
            if not paires:
                rep[vis] = None
                continue
            rep[vis] = paires[0][0]
            if paires[0][0] > 1:
                reste.append((vis, paires))
        if not reste:
            return rep
        if not _hand_to(sid, rid, 4):
            print("  [contact] la main ne passe pas a l'adversaire -- arret")
            return rep
        avance = False
        for vis, paires in reste:
            for d, suid, fid, spos in paires:
                tiles = P247._movable(sid, rid, fid)
                if not tiles:
                    continue
                t = min(tiles, key=lambda x: (hexgeo.distance(x, spos), x))
                if hexgeo.distance(t, spos) >= d:
                    continue
                print("  [contact] %-18s summon u%-4d@%s <- ennemi u%-4d -> %s (d %d -> %d)"
                      % (vis, suid, spos, fid, t, d, hexgeo.distance(t, spos)))
                P247._act(sid, rid, {"kind": "move", "unitId": fid,
                                     "to": {"col": t[0], "row": t[1]}}, 90)
                avance = True
                break
        if not avance:
            print("  [contact] aucun ennemi ne peut se rapprocher davantage -- arret")
            return rep
    return rep


def _rows(sid, rid, st, dv, caster_u):
    """Une ligne par cible ENNEMIE vivante : natif, port APRES, port BASELINE."""
    cid = int(caster_u["id"])
    after = _NormalAttackTargeting(OPTS[GENERIC_TYPE])
    before = _NoDynamicRule(OPTS[GENERIC_TYPE])
    out = []
    for u in (dv.get("units") or []):
        if not u.get("alive") or int(u["id"]) == cid or u.get("owner") == caster_u.get("owner"):
            continue
        tid = int(u["id"])
        tr = (P247._nat(sid, rid, cid, GENERIC_TYPE, tid) or {}).get("targetReason") or {}
        out.append({
            "tid": tid, "vis": u.get("visualId"),
            "d": hexgeo.distance(P247._pos(caster_u), P247._pos(u)),
            "nat": P247._hexval(tr),
            "after": int(get_invalid_target_reason(st, cid, tid, after)),
            "before": int(get_invalid_target_reason(st, cid, tid, before))})
    return out


def _print_rows(label, rows):
    print("\n  --- CASTER %s" % label)
    print("      %-5s %-16s %-3s %-12s %-12s %-12s" % ("id", "cible", "d", "natif", "portApres",
                                                       "portAvant"))
    for r in rows:
        mark = ""
        if r["after"] != r["before"]:
            mark = "   <- DISCRIMINANT"
        print("      %-5d %-16s %-3d %-12s %-12s %-12s%s"
              % (r["tid"], r["vis"], r["d"],
                 "?" if r["nat"] is None else hex(r["nat"]), hex(r["after"]), hex(r["before"]),
                 mark))


def run(sid, seed: str = "4192", board: str = "MC1_67") -> dict:
    """La MESURE, sans verdict. Leve `MontageError` si le montage n'a pas mordu."""
    rid, state = _build(sid, seed, board)
    print("=== montage : %s -> `CultDemagogue` -> %s (SANS ARME) + %s (ARME)  (runner %d)"
          % (ANCHOR_VIS, NOWEAPON_VIS, ARMED_VIS, rid))
    try:
        for _ in range(P247.TOURS_DE_CHAUFFE):
            P247._act(sid, rid, {"kind": "endturn"}, 60)
        _drive_and_summon(sid, rid)
        print("  contact force : %s" % forcer_contact(sid, rid))
        dv, payloads = P436._capture(sid, rid)
        st = P436._mk_state(payloads)
        nw = _pick_adjacent(dv, NOWEAPON_VIS)
        ar = _pick_adjacent(dv, ARMED_VIS)
        if nw is None:
            raise MontageError("aucun `%s` vivant ADJACENT a un ennemi -> discriminant NON monte"
                               % NOWEAPON_VIS)
        if ar is None:
            raise MontageError("aucun `%s` vivant ADJACENT a un ennemi -> temoin NON monte"
                               % ARMED_VIS)
        for tag, u in (("SANS ARME", nw), ("ARME", ar)):
            got = _normal_attack_id(u)
            print("  montage %-9s u%-4s %-18s attaque normale NATIVE = %s (attendu %d) -> %s"
                  % (tag, u["id"], u.get("visualId"), got, GENERIC_TYPE,
                     "MORD" if got == GENERIC_TYPE else "N'A PAS MORDU"))
            if got != GENERIC_TYPE:
                raise MontageError("%s ne porte pas l'attaque normale generique" % u.get("visualId"))
        d_rows = _rows(sid, rid, st, dv, nw)
        a_rows = _rows(sid, rid, st, dv, ar)
        _print_rows("SANS ARME  u%s %s" % (nw["id"], NOWEAPON_VIS), d_rows)
        _print_rows("ARME       u%s %s" % (ar["id"], ARMED_VIS), a_rows)
        return {"decoy": d_rows, "anchor": a_rows}
    finally:
        subprocess.run([sys.executable, "rl_duel.py", "dispose", "--state-file", str(state)],
                       cwd=str(PYDIR), capture_output=True, text=True)


def tally(res: dict) -> dict:
    """Le BILAN chiffre, sur DEUX axes qu'il ne faut PAS confondre :

      * **VERDICT** (refuse / accepte) -- l'axe qui gouverne le comportement : `is_invalid_target`
        et `valid_normal_attack_targets` ne lisent qu'un booleen « non nul = refus ». C'est le
        critere de cette tranche : le port doit refuser EXACTEMENT ce que le natif refuse.
      * **CODE** exact du `TargetingRule` rendu -- plus exigeant, et il expose un ecart AMONT qui
        n'appartient PAS a cette tranche : quand la portee d'arme n'est pas observable
        (`unit_weapon_range` rend `None` pour les 81 unites sans arme), `get_range` abandonne TOUT
        le volet portee, **y compris la branche `only_adjacent`, qui n'utilise pourtant jamais la
        valeur** (`get_range_broken_rule` : `if rr.only_adjacent: ... are_entities_adjacent`).
        Le natif, lui, rend `TargetIsInRange` sur ces lignes. Resultat : sur une cible NON adjacente
        d'un caster sans arme, natif et port REFUSENT tous deux, mais le port impute le refus a
        `TargetMatchesDynamicRule` au lieu de `TargetIsInRange`.
        Residu nomme `#419-r1-tr14-r5-r2-r1-r2-r1-r1`, cause racine LOCALISEE, hors mandat ici --
        et PREEXISTANT : avant cette tranche ces memes lignes rendaient `0x0`, c.-a-d. ACCEPTE."""
    out = {"tot": 0, "after": 0, "before": 0, "gain": 0, "perte": 0,
           "v_after": 0, "v_before": 0, "v_gain": 0, "v_perte": 0}
    for key in ("decoy", "anchor"):
        rows = [r for r in res[key] if r["nat"] is not None]
        out["tot"] += len(rows)
        out["after"] += sum(1 for r in rows if r["after"] == r["nat"])
        out["before"] += sum(1 for r in rows if r["before"] == r["nat"])
        out["gain"] += sum(1 for r in rows if r["after"] == r["nat"] and r["before"] != r["nat"])
        out["perte"] += sum(1 for r in rows if r["after"] != r["nat"] and r["before"] == r["nat"])
        for r in rows:
            nat, af, bf = bool(r["nat"]), bool(r["after"]), bool(r["before"])
            out["v_after"] += int(af == nat)
            out["v_before"] += int(bf == nat)
            out["v_gain"] += int(af == nat and bf != nat)
            # PERTE = le natif ACCEPTE et le port REFUSE : un refus trop large, l'echec symetrique
            # de l'ecart permissif qu'on ferme ici.
            out["v_perte"] += int(af != nat and bf == nat)
    return out


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--seed", default="4192")
    ap.add_argument("--board", default="MC1_67")
    a = ap.parse_args(argv)
    sid = _resolve_session()
    try:
        res = run(sid, a.seed, a.board)
    except MontageError as e:
        print("\n[FAIL] MONTAGE : %s" % e)
        return 2
    t = tally(res)
    print("\n=== BILAN sur %d lignes" % t["tot"])
    print("  VERDICT (refuse/accepte) : accord APRES %d | accord AVANT %d | gagnees %d | PERDUES %d"
          % (t["v_after"], t["v_before"], t["v_gain"], t["v_perte"]))
    print("  CODE    (regle exacte)   : accord APRES %d | accord AVANT %d | gagnees %d | PERDUES %d"
          % (t["after"], t["before"], t["gain"], t["perte"]))
    rc = 0
    if t["v_after"] != t["tot"]:
        print("[FAIL] le port APRES n'est pas en accord total avec le natif SUR LE VERDICT")
        rc = 1
    if t["v_gain"] == 0:
        print("[FAIL] REGIME DEGENERE : la baseline ne diverge sur AUCUN verdict -- la mesure ne "
              "prouve rien, meme si l'accord est parfait")
        rc = 1
    if t["v_perte"]:
        print("[FAIL] %d cible(s) LEGITIME(S) PERDUE(S) : le refus porte est trop large"
              % t["v_perte"])
        rc = 1
    if t["after"] != t["tot"]:
        print("  [note] %d ligne(s) en desaccord sur le CODE seul -- residu "
              "`#419-r1-tr14-r5-r2-r1-r2-r1-r1` (`get_range` desarme `only_adjacent` quand la "
              "portee d'arme n'est pas observable). NON bloquant ici : hors mandat, et PREEXISTANT."
              % (t["tot"] - t["after"]))
    print("VERDICT: %s" % ("PASS" if rc == 0 else "FAIL"))
    return rc


if __name__ == "__main__":
    raise SystemExit(main())
