"""R6-b' -- le `Maybe` after-hit est-il evalue sur les coups d'un GROUPE de coups additionnels ?

QUESTION (binaire) : `IdunBattle.Operations.ADamageOperation$$EvaluateAfterHitTriggers` est la
DERNIERE instruction de CHAQUE `IdunBattle.Operations.AttackDamageOperation$$ExecuteHit` (appel
INCONDITIONNEL). Les coups d'un groupe passent-ils par ce meme `ExecuteHit` avec un index de coup
CONTINU -- donc en roulant le `Maybe(GetBonusHitChance)` de `GetStuckIn` quand cet index est
IMPAIR -- ou l'index repart-il de 0 par sous-operation (auquel cas le `Maybe` ne serait roule que
sur les coups d'arme, ce que faisait le port) ?

RE (decompile = verite, gqfc5mff6c) -- chaine LUE de l'index au tirage :

  * `IdunBattle.Core.OngoingAttack$$.ctor` met `+0x30` (index de coup) et `+0x34` (compteur de
    series) a 0. L'objet est POUSSE UNE FOIS PAR ATTAQUE sur la pile `MatchState+0x60`
    (`IdunBattle.Core.MatchState$$StartAttack` <- `IdunBattle.Operations.StartAttackOperation$$
    Execute`) et depile par `IdunBattle.Core.MatchState$$FinishAttack` ;
  * toute sous-operation le RECUPERE par `Peek` : `IdunBattle.Operations.ADamageOperation$$
    GetCurrentAttackOrDefault` -> `IdunBattle.Core.Services.BattleQuery$$GetCurrentAttackOrDefault`
    -> `IdunBattle.Core.MatchState$$GetCurrentAttack` ;
  * `IdunBattle.Operations.AttackDamageOperation$$ExecuteHits` relit `currentAttack+0x30` FRAIS a
    chaque tour de boucle ; `IdunBattle.Operations.ADamageOperation$$UpdateCurrentAttackAfterHit`
    fait `+0x30 += 1` apres CHAQUE coup (`+0x34 += 1` seulement en fin de serie) ;
  * `EvaluateAfterHitTriggers` construit `IdunBattle.Entities.Abilities.AbilityEntities$$.ctor`
    avec cet index en `Nullable<int>` au champ **+0x110**, puis dispatche **`On(8)`** ;
    `IdunBattle.Entities.Formulas.CurrentHitIndexFormula$$Calculate` lit exactement `+0x110` ;
  * `IdunBattleLogic.Entities.Abilities.Triggered.Loki.GetStuckInAbility$$CreateTrigger` =
    `On(8) & AmountIsOdd(CurrentHitIndex()) & OwnerIsCaster & !(MinDistance > Direct(2))` ;
    `...$$CreateBehaviour` = `Maybe(AddBonusHitsToCurrentHitGroup(...), GetBonusHitChance())`
    -> 1 `NextBool(chance)` (`IdunBattle.Entities.Behaviours.MaybeBehaviour$$Execute`) ;
  * la voie GROUPES (`ExecuteAdditionalHitsWithDamageProfileTypeOperation$$Execute` -> slot 0x3c
    -> `AttackDamageOperation$$Execute` -> `ExecuteHits`) partage donc le MEME `OngoingAttack`.

=> REPONSE : OUI, l'index CONTINUE et le `Maybe` est roule sur les coups d'un groupe.

CE QUE CE PROBE MESURE (per-coup live vs deux modeles offline sur le MEME flux RNG) :
  * `shipped`     = le port TEL QU'IL EST LIVRE ;
  * `no_maybe_grp`= le CONTREFACTUEL (le `Maybe` n'est PAS roule dans les groupes) =
    `additional_hits_variant("roll_then_reduce", None)` de `probe_r6_round_materialize`.

DEUX REGIMES apparaissent SEULS, et c'est ce qui refute un « +1 tirage » fitte : le `Maybe` de la
phase d'ARME (coup d'index 1) SPAWNE un coup bonus quand il REUSSIT, ce qui DECALE la parite de
l'index a l'entree du groupe. Avec `orksRuntherd` (3 coups d'arme) :
  * echec  -> groupe aux index 3,4 : 3 est IMPAIR -> 1 tirage ENTRE les deux coups du groupe ;
  * succes -> 1 coup bonus (index 3), groupe aux index 4,5 : 4 est PAIR -> AUCUN tirage entre eux.
Le contrefactuel « toujours +1 » echouerait donc sur le second regime.

TROIS MONTAGES :
  * `--case squig`  : `orksRuntherd` (GetStuckIn + passif SquigHound, 3 coups d'arme) vs
    `ultraApothecary` (ni BigTarget ni Vehicle -> BeastSlayer inerte) ;
  * `--case parry`  : MEME porteur vs `templSwordBrother` (trait `Parry` = -1 coup en melee ->
    2 coups d'arme). La PARITE est INVERSEE : echec -> groupe aux index 2,3 (AUCUN tirage entre
    les deux coups) ; succes -> groupe aux index 3,4 (1 tirage). Un modele qui « ajoute toujours
    un tirage » (ou qui n'en ajoute jamais) tombe sur l'un des deux montages ;
  * `--case temoin` : `admecRuststalker` (CordClaw -> effet 1250) -- porteur SANS trigger
    after-hit -> les deux modeles DOIVENT coincider et reproduire le live (garde de non-regression
    : prouve qu'on n'a pas ajoute un tirage partout).

Discipline runner : state-file UNIQUE en chemin ABSOLU sous logs/, `--board` explicite, dispose en
fin. ASCII only (cp1252).
"""
from __future__ import annotations

import argparse
import json
import sys

from probe_r6_round_materialize import (_build, _drive_normal, _live_amounts,   # noqa: F401
                                        _mkrpc, additional_hits_variant)
from probe_r6b_additional_hits_order import _cast_cord_claw

# Marqueurs de SOURCE portes par les events de degat (tags live, mesures 2026-07-28) :
AH_EFFECT_SRC = "Additional_Hit_Effect_Source"              # 1292 = SquigHound_AdditionalHits
AH_TRIGGERED_SRC = "Additional_Hit_TriggeredAbility_Source"  # 1234 = 0x4d2, le litteral que
#   `GetStuckInAbility$$CreateBehaviour` passe a `AddBonusHitsToCurrentHitGroup` -> un coup marque
#   AINSI **EST** un coup bonus GetStuckIn, et le voir APRES les coups du groupe (meme `Attacker_Id`)
#   est la preuve LIVE, cote jeu, que le `Maybe` a ete evalue PENDANT le groupe.


def live_hits_of_attacker(res, target_id, attacker_id):
    """Per-coup LIVE emis par `attacker_id` sur `target_id`, dans l'ordre, + flags de salete + le
    marqueur de source de chaque coup.

    Filtrer par `Attacker_Id` ECARTE l'attaque du grot spawne par `SquigHound`, qui SUIT le groupe
    dans le MEME flux d'events : le NOMBRE de coups de l'attaque devient alors observable, ce qui
    permet une garde EXACTE EN NOMBRE (un `Maybe` qui reussit PENDANT le groupe y ajoute un coup).
    Rend `(amounts, dirty, sources)` ou `sources[i]` vaut `None` (coup d'arme), `"eff:<id>"`
    (coup de groupe) ou `"trig:<id>"` (coup bonus d'un trigger after-hit)."""
    amounts, sources, dirty = [], [], False
    for act in (res.get("actions") or []):
        for e in (act.get("events") or []):
            td = e.get("tags")
            td = json.loads(td) if isinstance(td, str) else (td or {})
            if td.get("Target_Id") != target_id or "Amount" not in td:
                continue
            if attacker_id is not None and td.get("Attacker_Id") != attacker_id:
                continue
            amounts.append(int(td["Amount"]))
            if AH_EFFECT_SRC in td:
                sources.append("eff:%s" % td[AH_EFFECT_SRC])
            elif AH_TRIGGERED_SRC in td:
                sources.append("trig:%s" % td[AH_TRIGGERED_SRC])
            else:
                sources.append(None)
            dirty = dirty or bool(td.get("Attack_DidCrit")) or bool(td.get("Attack_DidBlock")) \
                or bool(td.get("Attack_DidEvade"))
    return amounts, dirty, sources

SQUIG_CARRIER = "orksRuntherd"        # GetStuckIn + SquigHound (2 coups Physical p1, PREDEFINED)
SQUIG_TARGET = "ultraApothecary"      # ni BigTarget ni Vehicle
PARRY_TARGET = "templSwordBrother"    # trait Parry -> -1 coup d'arme en melee (parite INVERSEE)
CC_CARRIER = "admecRuststalker"       # temoin : AUCUN trigger after-hit
CC_TARGET = "necroWarden"
CC_A_UNITS = "necroWarden,necroWarden"


def _replay(dv, ob, snap, board, rng0, caster_id, target_id, moved):
    """Rejoue le MEME coup offline (meme etat, meme flux RNG) sous le port LIVRE et sous le
    CONTREFACTUEL sans `Maybe` dans les groupes. Rend, pour chacun, les per-coup du GROUPE ; plus
    les coups d'ARME et le nombre de coups d'arme de BASE (le delta = coups bonus GetStuckIn, donc
    le REGIME de parite)."""
    from engine.runner.snapshot import load_state
    from engine.runner.runner import Runner
    from engine.runner.messages import AttackUnitMessage
    from engine.runner.prng import IntBasedMersenneTwister
    from engine.runner.components import set_moved_flag
    from engine.runner.operations import additional_hits as _ah_mod
    from engine.runner.operations.damage_ops import normal as _dnormal
    from engine.runner.operations.damage_ops import ability as _dability

    def _one(impl):
        st = load_state(dv, ob, snap, board=board)
        if moved:
            set_moved_flag(st, caster_id)
        rng = IntBasedMersenneTwister()
        rng.mt = list(rng0["mt"])
        rng.mti = rng0["mti"]
        st.rng = rng
        per_hit: list = []
        o_ah = _ah_mod.execute_additional_hits
        o_n, o_a = _dnormal.execute_additional_hits, _dability.execute_additional_hits

        def _rec(*a, **kw):
            out = (impl or o_ah)(*a, **kw)
            if out:
                per_hit.extend(out.get("per_hit") or [])
            return out

        _ah_mod.execute_additional_hits = _rec
        _dnormal.execute_additional_hits = _rec
        _dability.execute_additional_hits = _rec
        try:
            runner = Runner(st).install_default_handlers(20)
            runner.apply(AttackUnitMessage(caster_id, target_id))
            last = getattr(getattr(runner, "damage_handler", None), "last", None)
            last = last if isinstance(last, dict) else {}
            return per_hit, list(last.get("per_hit") or []), int(last.get("hits") or 0)
        finally:
            _ah_mod.execute_additional_hits = o_ah
            _dnormal.execute_additional_hits = o_n
            _dability.execute_additional_hits = o_a

    grp_ship, arme, base_hits = _one(None)
    grp_no, _, _ = _one(additional_hits_variant("roll_then_reduce", None))
    return {"shipped": grp_ship, "no_maybe_grp": grp_no, "arme": arme, "base_hits": base_hits}


def _confront(label, seed, live, srcs, off):
    """Imprime la confrontation et rend (n_ship_ok, n_nomaybe_ok, discriminant, regime).

    `live` est deja FILTRE sur l'`Attacker_Id` du porteur -> la comparaison du groupe est EXACTE
    EN NOMBRE (pas un prefixe)."""
    arme, base = off["arme"], off["base_hits"]
    n = len(arme)
    grp_live = live[n:]
    bonus = n - base
    regime = "bonus=%d (arme %d base + %d GetStuckIn)" % (bonus, base, bonus)
    print("[%s] seed %-7s live=%s" % (label, seed, live))
    print("        sources     =%s" % (srcs,))
    print("        arme_offline=%s  %s  -> groupe live=%s" % (arme, regime, grp_live))
    print("        shipped      =%s" % (off["shipped"],))
    print("        no_maybe_grp =%s" % (off["no_maybe_grp"],))
    if live[:n] != arme:
        print("        [!] coups d'ARME desalignes -> mesure NON portante")
        return (0, 0, 0, bonus)
    ship, nom = off["shipped"], off["no_maybe_grp"]
    ship_ok = int(bool(ship) and ship == grp_live)
    nom_ok = int(bool(nom) and nom == grp_live)
    disc = int(ship != nom)
    note = ""
    if len(ship) != len(nom):
        note = "  [COMPTE: shipped %d coups vs contrefactuel %d, live %d]" % (
            len(ship), len(nom), len(grp_live))
    print("        -> shipped %s  no_maybe_grp %s  (discriminant: %s)%s"
          % ("OK" if ship_ok else "MISMATCH", "OK" if nom_ok else "MISMATCH",
             "oui" if disc else "NON", note))
    return (ship_ok, nom_ok, disc, bonus)


def _run_one(rpc, seed, carrier, target, a_units, armor, rank, verbose, cast_first=False,
             effect_required=None, label="squig"):
    from engine.entities.pathfinding.board import Board
    rid, sf = _build(seed, carrier, a_units,
                     extra=["--crit", "0,0", "--block-target", "0,0",
                            "--armor-target", str(armor)], rank=rank)
    if rid is None:
        return None
    try:
        bg = rpc("boardGraph", {"runnerId": rid}, 60)
        board = Board(bg["tiles"], adjacency="native_sym")
        if cast_first and not _cast_cord_claw(rpc, rid, board):
            print("[%s] seed %s: cast KO" % (label, seed))
            return None
        cid, tid, moved = _drive_normal(rpc, rid, board, carrier, target)
        if cid is None:
            print("[%s] seed %s: drive KO" % (label, seed))
            return None
        dv = rpc("decisionView", {"runnerId": rid, "allAbilities": True}, 120)
        cu = next((u for u in (dv.get("units") or []) if u.get("id") == cid), {})
        if effect_required is not None:
            effs = {e.get("effectType") for e in (cu.get("effects") or [])}
            if effect_required not in effs:
                print("[%s] seed %s: effet %s absent" % (label, seed, effect_required))
                return None
        ob = rpc("observeBattle", {"runnerId": rid}, 60)
        snap = rpc("combatSnapshot", {"runnerId": rid}, 90)
        rng0 = rpc("dumpRng", {"runnerId": rid}, 30)
        nrm = next((a for a in (cu.get("abilities") or []) if a.get("kind") == "normal"), None)
        if nrm is None:
            print("[%s] seed %s: pas d'attaque normale" % (label, seed))
            return None
        res = rpc("applyAction", {"runnerId": rid, "action": {
            "kind": "ability", "casterId": cid, "targetId": tid,
            "abilityType": nrm["id"]}, "captureEvents": True}, 120)
        if verbose:
            _live_amounts(res, tid, verbose=True)
        live, dirty, srcs = live_hits_of_attacker(res, tid, cid)
        if dirty:
            print("[%s] seed %s: coup SALE (crit/block/evade) -- ignore" % (label, seed))
            return None
        off = _replay(dv, ob, snap, board, rng0, cid, tid, moved)
        return _confront(label, seed, live, srcs, off)
    finally:
        try:
            rpc("disposeRunner", {"runnerId": rid}, 20)
        except Exception:
            pass
        try:
            sf.unlink()
        except Exception:
            pass


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--case", default="squig", choices=("squig", "parry", "temoin"))
    ap.add_argument("--seeds", default="777,31337,12345,314159,88")
    ap.add_argument("--rank", type=int, default=None)
    ap.add_argument("--armor", type=int, default=6000)
    ap.add_argument("--verbose", action="store_true")
    args = ap.parse_args()
    rpc = _mkrpc()

    if args.case == "squig":
        carrier, target, a_units = SQUIG_CARRIER, SQUIG_TARGET, SQUIG_TARGET
        cast_first, eff = False, None
    elif args.case == "parry":
        carrier, target, a_units = SQUIG_CARRIER, PARRY_TARGET, PARRY_TARGET
        cast_first, eff = False, None
    else:
        carrier, target, a_units = CC_CARRIER, CC_TARGET, CC_A_UNITS
        cast_first, eff = True, 1250

    tot = [0, 0, 0]
    rows = 0
    regimes = {}
    for seed in [s for s in args.seeds.split(",") if s]:
        r = _run_one(rpc, seed, carrier, target, a_units, args.armor, args.rank, args.verbose,
                     cast_first=cast_first, effect_required=eff, label=args.case)
        if r is None:
            continue
        tot = [a + b for a, b in zip(tot, r[:3])]
        regimes[r[3]] = regimes.get(r[3], 0) + 1
        rows += 1
    print()
    print("[%s] BILAN %d montages : shipped %d/%d, contrefactuel-sans-Maybe %d/%d, "
          "montages discriminants %d/%d"
          % (args.case, rows, tot[0], rows, tot[1], rows, tot[2], rows))
    print("[%s] regimes (coups bonus GetStuckIn en phase d'arme) : %s"
          % (args.case, dict(sorted(regimes.items()))))
    return 0


if __name__ == "__main__":
    sys.exit(main())
