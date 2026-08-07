#!/usr/bin/env python
"""Probe #505 -- confront LIVE de `1129 BloodyFury` (`worldTerminator` « Wrask », WorldEaters),
face EXECUTION.

L'ability etait absente d'`ABILITY_CLASSES` : le cast tombait sur le no-op SILENCIEUX de
`AbilityHandler.visit_ActiveAbilityMessage` (`ported: False`, 0 degat, 0 effet, aucune erreur).

CE QUE CE PROBE MESURE, ET POURQUOI IL A DEUX REGIMES
-----------------------------------------------------
Le coeur de l'ability est un SNOWBALL de coups lu au decompile :

    GetNumTotalHits = Sum( Direct(nrOfHits),
                           Min( Multiply(Direct(extraHit), TotalTimesAttacked(Owner)),
                                Subtract(Direct(maxNrOfHits), Direct(nrOfHits)) ) )

et `IdunBattle.Entities.Formulas.TotalTimesAttackedFormula$$Calculate` rend
`*(uint *)(ActorStatisticsComponent + 0x34)`. La QUESTION que le decompile tranche et que ce probe
CONFRONTE est : ce compteur est-il le TOTAL DE LA BATAILLE (+0x34) ou le PER-TOUR (+0x38) ?
`$$RegisterAttackReceived` incremente les DEUX ; seul `$$ResetAttacksReceivedThisTurn` en efface UN
(`*(ulong*)(this+0x38) = 0`). Le port lit donc le TOTAL.

Le regime SNOWBALL etale ses attaques sur DEUX TOURS ENNEMIS : si le natif lisait le per-tour, il
rendrait `1 + <attaques du DERNIER tour>` ; s'il lit le total, `1 + <toutes>`. Les deux nombres sont
DIFFERENTS par construction (le montage refuse de continuer si le second tour porte autant
d'attaques que le total). C'est la seule facon de separer les deux offsets par un OBSERVABLE.

  * REGIME A -- `--attacks 0` : Wrask jamais attaque -> `hits = nrOfHits = 1`. TEMOIN DEGENERE :
    un seul coup, aucun report possible (`max(0, H-k-1) = 0` des que k >= H-1). Il ne prouve pas
    le snowball ; il prouve que le port ne SUR-tire pas.
  * REGIME B -- `--attacks N` (defaut 6, sur DEUX tours ennemis) : `hits = 1 + min(N, 7)`, la cible
    principale meurt tot (`--hp-target` bas) et les coups gaspilles sont REPORTES sur les autres
    ennemis adjacents au CASTER -- ce qui exerce `SortTargetsByDamagePredictionSelector` et
    `GetLeftOverHits`.

ETAGES CONFRONTES (jamais un scalaire agrege) :
  1. `ported is True`            -- la face EXECUTION n'est plus un no-op ;
  2. le NOMBRE DE COUPS live     -- `sum(len(per_hit))` sur toute la chaine == `1 + min(N, 7)`
                                    (c'est LE verdict qui separe +0x34 de +0x38) ;
  3. la CHAINE                   -- la LISTE ORDONNEE des cibles frappees (observable du selecteur
                                    de tri + du report) ;
  4. les degats PAR COUP         -- offline vs live, par cible, coup par coup ;
  5. le report                   -- `max(0, H - k - 1) + extraHits(=0)` de `GetLeftOverHits`.

⚠ CE QUE LE HARNAIS NE PEUT PAS FAIRE, ET C'EST DIT (pas contourne en silence) : aucun RPC
n'expose `ActorStatisticsComponent+0x34` (le hook `actorStats` de
`frida/hooks/features/ai-step/rpc-snapshot.ts` lit `+0x20 TotalAttacksMade`, `+0x30
TotalTurnsWithAttacksMade` et le trio tuiles `+0xec/+0xf0/+0xf4` -- PAS `+0x34`). L'etat OFFLINE
rebati par `load_state` part donc a 0 sur ce compteur, comme il le fait deja pour
`times_attacked_this_turn`. Le probe le SEEDE avec le nombre d'attaques qu'il a lui-meme DRIVEES
(donc une entree CONNUE, pas ajustee), et le verdict 2 porte sur le cote LIVE, qui lui n'est pas
seede. Le fait que le moteur OFFLINE tienne son propre compteur est garde separement, sans live,
par `tests/engine/runner/test_505_bloody_fury_offline.py`.

ASCII only (cp1252). Usage :
    python probe_505_bloody_fury.py [--seed 4242] [--board MC1_67] [--attacks 6] [--hp-target 3000]
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

PYDIR = Path(__file__).resolve().parent
sys.path.insert(0, str(PYDIR))

from probe_116_necrons import (_alive_units, _build, _capture, _cast_live, _dispose,   # noqa: E402
                               _from_here, _live_per_hit, _offline_cast, _r, _tid,
                               _unit_of)
from rl_collect_batch import _resolve_session                                          # noqa: E402
from engine.entities.active_ability_type import ActiveAbilityType                      # noqa: E402
from engine.runner.components import UnitComponent                                     # noqa: E402

ROOT = PYDIR.parents[1]
BLOODY_FURY = int(ActiveAbilityType.BloodyFury)          # 1129


# --------------------------------------------------------------------------- helpers de montage

def _pos_of(dec, uid):
    for u in _alive_units(dec):
        if int(u["id"]) == int(uid):
            p = u.get("pos") or {}
            return (p.get("col"), p.get("row"))
    return None


def _normal_attack_id(dec, uid):
    """`NormalAttackType` de l'unite = l'ability `kind == "normal"` de `decisionView` (l'attaque
    normale EST une ability, dont le type est PER-UNIT -- cf. le message de refus d'`applyAction`)."""
    for u in _alive_units(dec):
        if int(u["id"]) != int(uid):
            continue
        for ab in (u.get("abilities") or []):
            if ab.get("kind") == "normal" and ab.get("id") is not None:
                return int(ab["id"])
    return None


def _movable(sid, rid, uid):
    mov = _r(sid, "aiMovableTiles", {"runnerId": rid}, 60)
    for mu in (mov.get("units") or []):
        if int(mu.get("unitId") or -1) == int(uid):
            return [(t.get("col"), t.get("row")) for t in (mu.get("tiles") or [])
                    if t.get("col") is not None]
    return []


def _events_on(res, uid):
    """Events de DEGAT du retour d'`applyAction(captureEvents)` dont la CIBLE est `uid`.
    Sert d'AUDIT du montage : toute attaque encaissee par Wrask que le probe n'a pas DRIVEE
    (overwatch d'un ranged pendant une approche, reaction d'un passif...) incremente
    `ActorStatisticsComponent+0x34` et FAUSSE le compte de coups attendu."""
    out = []
    for act in (res.get("actions") or []):
        for e in (act.get("events") or []):
            td = e.get("tags")
            if not td:
                continue
            td = json.loads(td) if isinstance(td, str) else td
            if "Amount" in td and td.get("Target_Id") is not None \
                    and int(td["Target_Id"]) == int(uid):
                out.append((td.get("Active_Ability_Type"), td.get("Amount")))
    return out


def _move_next_to(sid, rid, uid, anchor, watch=None):
    """DRIVE la position (doctrine : on DEPLACE les unites pour realiser la condition testee, on ne
    subit pas la geometrie de spawn) : pose `uid` sur la tuile LEGALE la plus proche de `anchor`,
    en preferant une tuile ADJACENTE. `applyAction` ne verifie PAS la propriete du `unitId` -> on
    pilote les deux camps.

    `watch` = id dont on AUDITE les degats encaisses pendant ce deplacement (cf. `_events_on`)."""
    import hexgeo
    tiles = _movable(sid, rid, uid)
    if not tiles or anchor is None:
        return None, []
    best = min(tiles, key=lambda t: (hexgeo.distance(t, anchor), t))
    r = _r(sid, "applyAction", {"runnerId": rid, "captureEvents": True, "action": {
        "kind": "move", "unitId": int(uid), "to": {"col": best[0], "row": best[1]}}}, 60)
    hits = _events_on(r, watch) if watch is not None else []
    return (best if r.get("ok") is not False else None), hits


def _endturn(sid, rid):
    return _r(sid, "applyAction", {"runnerId": rid, "action": {"kind": "endturn"}}, 60)


def _dec(sid, rid):
    return _r(sid, "decisionView", {"runnerId": rid, "maxRank": 1, "allAbilities": True}, 90)


def _ctrl_of(dec, uid):
    for u in _alive_units(dec):
        if int(u["id"]) == int(uid):
            return bool(u.get("ctrl"))
    return None


def _turn_of(sid, rid, cid, mine: bool, tries=4):
    """Amene le runner sur le tour VOULU (celui de Wrask si `mine`, celui d'en face sinon), en
    VERIFIANT (`ctrl` de `decisionView`) au lieu de compter les `endturn`. Compter ne marche pas :
    un `endturn` peut ne pas basculer, et le probe se retrouve alors a caster pendant le tour
    adverse -- `abilityTargets.fromHere` rend une liste VIDE et l'echec se lit comme
    « aucune cible legale », c'est-a-dire comme une MESURE. Rend le nb de bascules effectuees."""
    n = 0
    for _ in range(tries):
        if _ctrl_of(_dec(sid, rid), cid) is bool(mine):
            return n
        _endturn(sid, rid)
        n += 1
    return n


def _adjacents(dec, cid, foes):
    """Ids des ennemis du caster ADJACENTS a lui (le pool de `GetOtherTargets`).

    ⚠ La liste des ENNEMIS est passee en argument, JAMAIS re-derivee de `ctrl` : ce drapeau designe
    « unite du camp qui joue EN CE MOMENT » et s'INVERSE a chaque `endturn`. Le derive ici rendait
    une liste VIDE une fois sur deux -- un « aucun ennemi adjacent » purement de harnais, alors que
    trois ennemis etaient au contact (mesure du premier jet de ce probe)."""
    import hexgeo
    c = _pos_of(dec, cid)
    out = []
    for u in _alive_units(dec):
        if int(u["id"]) not in set(int(f) for f in foes):
            continue
        p = u.get("pos") or {}
        if p.get("col") is None or c is None:
            continue
        if hexgeo.distance(c, (p["col"], p["row"])) == 1:
            out.append(int(u["id"]))
    return out


# --------------------------------------------------------------------------- le montage lui-meme

# GEOMETRIE FIGEE AU BUILD, pas conquise par des deplacements (cf. le commentaire de `phase`).
# `MC1_67` : la tuile `(3,4)` a SES SIX voisins jouables (verifie sur le dump du board -- aucune
# `ForceUnplayable`, aucun `Block`) ; c'est la seule facon d'exercer un pool `AdjacentEnemies`
# complet, un spawn de coin en sous-exercerait la moitie.
WRASK_TILE = (3, 4)
RING_TILES = ((3, 3), (3, 5), (2, 4), (4, 4))


def _hexd(a, b):
    import hexgeo
    if a is None or b is None or a[0] is None or b[0] is None:
        return 1 << 30
    return hexgeo.distance(a, b)


def _drive_attacks(sid, rid, cid, foes, total):
    """Fait encaisser `total` attaques NORMALES a Wrask, etalees sur PLUSIEURS tours ennemis (une
    unite n'agit qu'une fois par tour). Rend (n_delivree, [par tour]).

    UNE attaque = UN appel a `applyAction` qui produit AU MOINS un event de degat sur Wrask. C'est
    exactement la granularite de `IdunBattle.Operations.RegisterAttackOperation$$Execute` (appelee
    une fois par ATTAQUE, avec le `totalCrits` de la volee entiere), pas celle des COUPS -- une
    attaque normale a `nrOfHits` coups et n'incremente `+0x34` qu'UNE fois. Le cote port compte au
    meme grain (`record_attacked` est appele une fois par
    `AttackDamageOperation._apply_damage_pipeline`)."""
    done, per_turn, driven = 0, [], []
    guard = 8
    while done < total and guard > 0:
        guard -= 1
        this_turn = 0
        dec = _dec(sid, rid)
        for f in foes:
            if done >= total:
                break
            nat = _normal_attack_id(dec, f)
            if nat is None:
                continue
            res = _r(sid, "applyAction", {"runnerId": rid, "captureEvents": True, "action": {
                "kind": "ability", "casterId": int(f), "targetId": int(cid),
                "abilityType": int(nat)}}, 120)
            touche = _events_on(res, cid)
            print("[505]   attaque u%s -> u%s (nat=%s) ok=%s err=%s coups_sur_Wrask=%d"
                  % (f, cid, nat, res.get("ok"), res.get("error"), len(touche)))
            if touche:
                done += 1
                this_turn += 1
                driven.append((int(f), int(nat)))
        per_turn.append(this_turn)
        if done < total:
            _endturn(sid, rid)          # -> mon tour
            _endturn(sid, rid)          # -> tour ennemi suivant
    return done, per_turn, driven


def _fmt_chain(chain):
    return " | ".join("u%s: hits=%s applied=%s total=%s"
                      % (c.get("target"), c.get("hits"), c.get("applied_hits"), c.get("total"))
                      for c in (chain or []))


def _clamped(seq, hp):
    out = []
    for h in seq:
        d = max(0, min(int(h), hp))
        out.append(d)
        hp -= d
    return out


def phase(args, n_attacks: int, hp_target: int = None, label: str = None,
          main_hp: int = None) -> int:
    """UN regime complet : build -> montage -> capture -> cast offline -> cast live -> verdicts.

    LA GEOMETRIE EST FIGEE AU BUILD (`--place` / `--a-place`), PAS CONQUISE PAR DES DEPLACEMENTS.
    Deux raisons MESUREES, toutes deux fatales a la mesure du compteur :
      * un deplacement du CASTER attire l'OVERWATCH des ennemis ranged -> `+0x34` monte sans que le
        probe le sache (regime TEMOIN vu a `hits = 3` au lieu de 1) ;
      * dans ce runner, `applyAction move` CONSOMME l'activation de l'unite deplacee (`hasAction`
        passe a False, `toActivate` la retire) -> un ennemi qui vient d'avancer ne peut plus
        attaquer le meme tour, et le nombre d'attaques encaissees devient subi.
    Les positionner au build supprime les deux d'un coup, et donne en prime le PLEIN anneau de six
    voisins autour du caster."""
    hp_target = int(args.hp_target if hp_target is None else hp_target)
    tag = "[505/%s]" % (label or ("SNOWBALL" if n_attacks else "TEMOIN"))
    st_file = Path(args.state_file
                   or (ROOT / "logs" / "runners"
                       / ("_505_bf_%s.json" % (label or n_attacks))))
    st_file.parent.mkdir(parents=True, exist_ok=True)
    sid = _resolve_session()
    a_units = [x for x in args.a_units.split(",") if x]
    placement = ["--place", "worldTerminator:%d,%d" % WRASK_TILE]
    for uid, tile in zip(a_units, RING_TILES):
        placement += ["--a-place", "%s:%d,%d" % (uid, tile[0], tile[1])]
    if main_hp is not None:
        # UN SEUL ennemi FRAGILE, les autres immortels : la cible principale tombe (donc le report
        # EXISTE) et le MAILLON SUIVANT survit -- ses events sont alors EXACTEMENT ses coups, donc
        # `GetLeftOverHits` devient LISIBLE. Sans ca, un maillon qui meurt cesse d'emettre des
        # events (`UnitFlag.Overkilled`) et le nombre de coups reportes n'est plus observable.
        placement += ["--unit-stat", "%s:Health=%d,RemainingHealth=%d"
                      % (a_units[0], main_hp, main_hp)]
    rid = _build(st_file, ["--seed", str(args.seed), "--board", args.board, "--rank", "17",
                           "--p-units", "worldTerminator", "--a-units", args.a_units,
                           "--no-ai", "--hp-player", "900000",
                           "--hp-target", str(hp_target)] + placement)
    print("%s runner=%s session=%s board=%s seed=%s attaques_visees=%d"
          % (tag, rid, sid, args.board, args.seed, n_attacks))
    rc = 0
    try:
        dec = _dec(sid, rid)
        w = _unit_of(dec, "worldTerminator")
        if w is None:
            print("%s Wrask ABSENT du deploiement -- montage a revoir" % tag)
            return 2
        cid = int(w["id"])
        foes = [int(u["id"]) for u in _alive_units(dec) if not u.get("ctrl")]
        adj = _adjacents(dec, cid, foes)
        print("%s caster=u%s@%s ennemis=%s adjacents=%s"
              % (tag, cid, _pos_of(dec, cid), {f: _pos_of(dec, f) for f in foes}, adj))
        if len(adj) < 2:
            print("%s ECHEC DE MONTAGE : moins de 2 ennemis adjacents -- ni le report ni le pool "
                  "de `GetOtherTargets` ne peuvent s'exercer" % tag)
            return 2

        # --- MONTAGE : les attaques recues -------------------------------------------------------
        delivered, per_turn, driven = 0, [], []
        k_off = 0
        attaquants = foes if args.attackers is None else \
            [foes[i] for i in [int(x) for x in args.attackers.split(",") if x != ""] if i < len(foes)]
        if n_attacks:
            # ETAT AVANT LES ATTAQUES : c'est lui qui permet de MESURER le compteur au lieu de le
            # supposer (cf. le bloc COMPTEUR plus bas).
            mkstate0, _d0, _b0 = _capture(sid, rid)
            _turn_of(sid, rid, cid, mine=False)   # -> tour ennemi
            delivered, per_turn, driven = _drive_attacks(sid, rid, cid, attaquants, n_attacks)
            print("%s attaques encaissees par Wrask = %d, ventilees par tour ennemi : %s"
                  % (tag, delivered, per_turn))
            if delivered != n_attacks:
                print("%s ECHEC DE MONTAGE : %d attaques sur %d demandees"
                      % (tag, delivered, n_attacks))
                return 2
            # LE DISCRIMINANT : on traverse ENCORE un tour ennemi COMPLET sans une seule attaque.
            # `ResetAttacksReceivedThisTurn` a donc efface `+0x38` ; si le natif lisait ce champ-la,
            # le cast qui suit vaudrait `nrOfHits` tout court. Sans ce tour BLANC, les deux offsets
            # predisent le meme nombre et le verdict 2 ne mesurerait rien.
            _turn_of(sid, rid, cid, mine=True)    # -> mon tour
            _turn_of(sid, rid, cid, mine=False)   # -> tour ennemi BLANC (aucune attaque)
            print("%s tour ennemi BLANC traverse : `+0x38` (per-tour) est remis a 0, `+0x34` non"
                  % tag)
            # --- COMPTEUR : on MESURE `+0x34` cote port, on ne le suppose pas ------------------
            # Rejeu OFFLINE des MEMES attaques normales depuis l'etat d'AVANT, par le CHEMIN REEL
            # (`AbilityHandler.visit_ActiveAbilityMessage` avec le `NormalAttackType` per-unite --
            # l'attaque normale EST une active ability). On lit ensuite le champ que le port tient.
            # ⚠ CE N'EST PAS UN COMPTE D'APPELS `applyAction` : mesure du 2026-08-07, l'attaque
            # normale de `tauCrisis` incremente le compteur natif **3 fois** (9 events de degat,
            # plusieurs groupes d'arme), celle d'`eldarRanger`/`astraBullgryn`/`necroWarden` une
            # seule. Prendre « une commande = une incrementation » predisait 5 coups la ou le natif
            # en a fait 7 -- l'ecart n'etait PAS dans la formule, il etait dans l'entree.
            from engine.runner.messages import AttackUnitMessage
            from engine.runner.runner import Runner
            st0 = mkstate0()
            rr = Runner(st0).install_default_handlers(20)
            for f, _nat in driven:
                rr.apply(AttackUnitMessage(attacker_id=int(f), target_id=int(cid)))
            k_off = int(st0.get_entity(cid).get_component(UnitComponent).total_times_attacked)
            print("%s COMPTEUR : %d commandes d'attaque -> le PORT compte `+0x34` = %d "
                  "(rejeu offline des memes attaques depuis l'etat d'avant)"
                  % (tag, delivered, k_off))
        _turn_of(sid, rid, cid, mine=True)        # -> MON tour, pour caster

        dec = _dec(sid, rid)
        w = _unit_of(dec, "worldTerminator")
        cid = int(w["id"])
        print("%s avant cast : Wrask hp=%s alive=%s hasAction=%s ctrl=%s toActivate=%s"
              % (tag, w.get("hp"), w.get("alive"), w.get("hasAction"), w.get("ctrl"),
                 dec.get("toActivate")))
        fh, tg = _from_here(sid, rid, cid, BLOODY_FURY)
        legal = [t for t in (_tid(x) for x in fh) if t is not None]
        if not legal:
            print("%s AUCUNE cible legale `fromHere` (targets=%s) -- montage a revoir" % (tag, tg))
            return 2
        hp_of = {int(u["id"]): int(u.get("hp") or 0) for u in _alive_units(dec)}
        vis_of = {int(u["id"]): u.get("visualId") for u in _alive_units(dec)}
        tid = min(legal, key=lambda t: (hp_of.get(t, 1 << 30), t))
        print("%s cibles LEGALES fromHere (id: visualId/PV) : %s"
              % (tag, {t: "%s/%s" % (vis_of.get(t), hp_of.get(t)) for t in legal}))
        print("%s cible retenue = u%s (la moins vitale -> elle tombe TOT, donc le report existe)"
              % (tag, tid))

        # --- OFFLINE (chemin reel : le handler) -------------------------------------------------
        mkstate, dec, board = _capture(sid, rid)
        st = mkstate()
        # HARDCODE (harnais, cf. l'en-tete) : `load_state` ne peut pas lire
        # `ActorStatisticsComponent+0x34` (aucun RPC ne l'expose). On y injecte le nombre
        # d'attaques que CE probe a DRIVEES -- une entree connue, jamais un ajustement. La tenue
        # AUTONOME du compteur par le moteur offline est gardee par
        # `tests/engine/runner/test_505_bloody_fury_offline.py`, sans live.
        uc = st.get_entity(cid).get_component(UnitComponent)
        uc.total_times_attacked = k_off
        diag = _offline_cast(st, cid, tid, BLOODY_FURY)
        off_chain = diag.get("chain") or []
        print("%s OFFLINE ported=%s dsl=%s hits=%s" % (tag, diag.get("ported"), diag.get("dsl"),
                                                       diag.get("hits")))
        print("%s OFFLINE chaine : %s" % (tag, _fmt_chain(off_chain)))
        off_per_hit = {int(c["target"]): [int(x) for x in (c.get("per_hit_health") or [])]
                       for c in off_chain}
        off_hp0 = {int(c["target"]): int(c.get("hp_before") or 0) for c in off_chain}

        # --- LIVE --------------------------------------------------------------------------------
        res = _cast_live(sid, rid, cid, tid, BLOODY_FURY, capture_events=True)
        live_per_hit = _live_per_hit(res, BLOODY_FURY)
        print("%s LIVE ok=%s mutated=%s" % (tag, res.get("ok"), res.get("mutated")))
        print("%s LIVE per-coup par cible : %s"
              % (tag, json.dumps({str(k): v for k, v in sorted(live_per_hit.items())})))

        # --- VERDICTS -----------------------------------------------------------------------------
        if diag.get("ported") is not True:
            print("%s VERDICT-1 ECHEC : `ported` != True -- l'ability est ENCORE un no-op" % tag)
            rc = 1
        else:
            print("%s VERDICT-1 OK : ported=True" % tag)

        # 2 -- LE verdict du snowball. `nrOfHits + min(extraHit x recues, maxNrOfHits - nrOfHits)`.
        # Le dernier tour ennemi est BLANC par construction -> la lecture `+0x38` (per-tour)
        # predirait `nrOfHits` tout court. Les deux predictions sont donc separees des que
        # `delivered > 0`.
        attendu = 1 + min(1 * k_off, 8 - 1)
        per_turn_attendu = 1
        live_total = sum(len(v) for v in live_per_hit.values())
        # ⚠ Le compte d'EVENTS n'est le compte de COUPS que si la cible SURVIT : sur un cadavre,
        # `IdunBattle.Operations.ApplyDamageOperation$$Execute` sort des l'entree sur
        # `UnitFlag.Overkilled` et les coups gaspilles n'emettent plus rien. Le verdict n'est donc
        # rendu qu'en regime SURVIVANT ; en regime CHAINE c'est le VERDICT-3/4 qui porte.
        survivant = all(int(u.get("hp") or 0) > 0 for u in _alive_units(_dec(sid, rid))
                        if int(u["id"]) in set(int(x) for x in foes))
        ok2 = (live_total == attendu) if survivant else True
        print("%s VERDICT-2 coups : `+0x34` mesure=%d (pour %d commandes) -> attendu(total)=%d "
              "attendu(si per-tour +0x38)=%d ; live=%d offline=%s cible_survivante=%s -> %s"
              % (tag, k_off, delivered, attendu, per_turn_attendu,
                 live_total, diag.get("hits"), survivant,
                 "OK" if ok2 else "ECART" if survivant else "NON PORTANT (cible morte)"))
        if not ok2 or int(diag.get("hits") or 0) != attendu:
            rc = 1

        off_order = [int(c["target"]) for c in off_chain]
        live_order = list(live_per_hit.keys())
        same_chain = set(off_order) == set(live_order)
        # BLOQUANT : le PREMIER maillon (la cible du message + le degat que 1129 lui porte) --
        # c'est ce que ce port decide. Les maillons SUIVANTS dependent du nombre de coups
        # REPORTES, donc de la feuille partagee dont la loi est un residu ouvert (cf. VERDICT-5bis)
        # : leur ecart est RAPPORTE, pas impute a 1129.
        tete_ok = bool(off_order) and bool(live_order) and off_order[0] == live_order[0]
        print("%s VERDICT-3 chaine : offline=%s live=%s -> tete %s ; ensemble %s"
              % (tag, off_order, live_order, "OK" if tete_ok else "MISMATCH",
                 "OK" if same_chain else "ECART (residu du report, non bloquant)"))
        if not tete_ok:
            rc = 1

        # Le port APPLIQUE en un bloc la ou le natif cesse d'appliquer sur un cadavre : on compare
        # donc la sequence offline CLAMPEE par les PV (comportement documente de
        # `ChainLeftOverHitsAttackDamage.execute`).
        tete = off_order[0] if off_order else None
        for t in sorted(set(off_per_hit) | set(live_per_hit)):
            o, l = off_per_hit.get(t), live_per_hit.get(t)
            oc = _clamped(o, off_hp0.get(t, 0)) if o is not None else None
            # L'OBSERVABLE COMMUN s'arrete au COUP FATAL : au-dela, le natif ne publie plus rien
            # (`ApplyDamageOperation$$Execute` sort des l'entree sur `UnitFlag.Overkilled`) tandis
            # que le port continue d'emettre des 0. Comparer les LONGUEURS brutes rendrait donc
            # ROUGE un accord parfait des que la cible est ECRASEE -- ce qui est precisement le
            # regime de 1129. On exige : memes valeurs jusqu'au coup fatal INCLUS, et QUE des 0
            # apres, des deux cotes.
            n = min(len(oc or []), len(l or []))
            same = (oc is not None and l is not None and n > 0
                    and all(int(a) == int(b) for a, b in zip(oc[:n], l[:n]))
                    and all(int(x) == 0 for x in (oc[n:] + l[n:])))
            bloquant = (t == tete)          # cf. VERDICT-3 : seule la TETE est imputable a 1129
            print("%s VERDICT-4%s u%s per-coup offline(brut)=%s offline(clampe)=%s live=%s -> %s"
                  % (tag, "" if bloquant else "*", t, o, oc, l,
                     "OK" if same else ("ECART" if bloquant
                                        else "ECART (residu du report, non bloquant)")))
            if not same and bloquant:
                rc = 1

        # 5bis -- REPORT LU DIRECTEMENT (regime `report` : un seul ennemi fragile). Le 2e maillon
        # SURVIT, donc `#events(2e maillon) == coups reportes`. C'est l'ETAGE `GetLeftOverHits`
        # isole -- aucune inference depuis un compte d'events tronque par `Overkilled`.
        if main_hp is not None:
            ordre = list(live_per_hit.keys())
            l_live = len(live_per_hit[ordre[1]]) if len(ordre) > 1 else 0
            l_off = int(off_chain[1]["hits"]) if len(off_chain) > 1 else 0
            h1 = len(off_chain[0].get("per_hit_health") or []) if off_chain else 0
            # ⚠ NON BLOQUANT, ET C'EST DELIBERE : cet etage mesure la feuille PARTAGEE
            # `ChainLeftOverHitsAttackDamage._left_over_hits`, pas le port de 1129. Sa loi est un
            # RESIDU OUVERT, documente avec ses six points de mesure et la cause lue
            # (`DamagePrediction$$IsOverkill` est un SEUIL) dans la docstring de `_left_over_hits`.
            # Le rendre bloquant ferait rougir 1129 pour une dette de 1006/1048.
            print("%s VERDICT-5bis REPORT LU (feuille PARTAGEE, residu ouvert -- NON bloquant) : "
                  "maillon1 H=%d ; coups reportes live=%d port=%d -> %s"
                  % (tag, h1, l_live, l_off, "OK" if l_live == l_off else "ECART"))

        # 5 -- `GetLeftOverHits` sans `extraHits` : report = max(0, H - k - 1), 0 si la cible survit.
        if off_chain:
            first = off_chain[0]
            ph = [int(x) for x in (first.get("per_hit_health") or [])]
            hp0 = int(first.get("hp_before") or 0)
            k, acc = None, 0
            for i, h in enumerate(ph):
                acc += h
                if hp0 - acc <= 0:
                    k = i + 1
                    break
            att = max(0, len(ph) - k - 1) if k else 0
            porte = int(off_chain[1]["hits"]) if len(off_chain) > 1 else 0
            print("%s VERDICT-5 report : H=%s k=%s -> max(0,H-k-1)=%s ; 2e maillon hits=%s -> %s"
                  % (tag, len(ph), k, att, porte, "OK" if att == porte else "MISMATCH"))
            if att != porte:
                rc = 1
    finally:
        if not args.keep:
            _dispose(st_file)
    print("%s rc=%s" % (tag, rc))
    return rc


def main(argv):
    ap = argparse.ArgumentParser()
    ap.add_argument("--seed", type=int, default=4242)
    ap.add_argument("--board", default="MC1_67")
    ap.add_argument("--attacks", type=int, default=4,
                    help="attaques encaissees par Wrask dans les regimes non degeneres")
    ap.add_argument("--hp-target", type=int, default=3000,
                    help="PV des ennemis dans le regime CHAINE (bas = la cible tombe -> report)")
    ap.add_argument("--hp-survivant", type=int, default=400000,
                    help="PV des ennemis dans les regimes TEMOIN/SNOWBALL (la cible SURVIT, donc "
                         "chaque coup emet son event -> le compte d'events EST le compte de coups)")
    ap.add_argument("--a-units", default="eldarRanger,astraBullgryn,tauCrisis,necroWarden")
    ap.add_argument("--attackers", default=None,
                    help="INDICES (dans --a-units) des seuls ennemis autorises a attaquer Wrask -- "
                         "sert au regime CALIBRAGE, qui mesure la contribution de CHAQUE attaquant "
                         "au compteur `+0x34` au lieu de la supposer egale a 1")
    ap.add_argument("--state-file", default=None)
    ap.add_argument("--keep", action="store_true")
    ap.add_argument("--only", choices=("temoin", "snowball", "chaine", "calibrage", "report"),
                    default=None)
    ap.add_argument("--main-hp", default="3000",
                    help="regime REPORT : PV de la SEULE cible fragile (les autres sont "
                         "immortelles). LISTE separee par des virgules = BALAYAGE de `k`, le seul "
                         "moyen de LIRE la loi de report au lieu d'en ajuster une")
    args = ap.parse_args(argv)
    rc = 0
    if args.only == "report":
        for hp in [int(x) for x in str(args.main_hp).split(",")]:
            rc |= phase(args, args.attacks, hp_target=args.hp_survivant,
                        label="REPORT-hp%d" % hp, main_hp=hp)
        print("[505] rc=%s" % rc)
        return rc
    if args.only == "calibrage":
        # UN attaquant a la fois, UNE attaque : `hits - nrOfHits` donne sa contribution REELLE au
        # compteur. C'est la mesure qui remplace l'hypothese « une attaque = une incrementation ».
        base = args.attackers
        for i, uid in enumerate([x for x in args.a_units.split(",") if x]):
            args.attackers = base if base is not None else str(i)
            rc |= phase(args, 1, hp_target=args.hp_survivant, label="CAL-%d-%s" % (i, uid))
            if base is not None:
                break
        print("[505] rc=%s" % rc)
        return rc
    # TROIS regimes, et le decoupage est le point : le compte de COUPS ne se lit proprement que sur
    # une cible qui SURVIT (sur un cadavre, `ApplyDamageOperation$$Execute` sort des l'entree sur
    # `UnitFlag.Overkilled` et les coups gaspilles n'emettent plus rien -- le nb d'events cesse
    # alors d'etre le nb de coups). On mesure donc le SNOWBALL sans mort, et le REPORT a part.
    if args.only in (None, "temoin"):
        rc |= phase(args, 0, hp_target=args.hp_survivant, label="TEMOIN")
    if args.only in (None, "snowball"):
        rc |= phase(args, args.attacks, hp_target=args.hp_survivant, label="SNOWBALL")
    if args.only in (None, "chaine"):
        rc |= phase(args, args.attacks, hp_target=args.hp_target, label="CHAINE")
    print("[505] rc=%s" % rc)
    return rc


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
