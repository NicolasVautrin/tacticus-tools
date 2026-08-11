#!/usr/bin/env python
"""Probe #908 volet CRIT -- `NetherRealmCasket_CritDamageReduction` (EffectType 0x5af = 1455).

LE NATIF
========
`IdunBattle.Entities.Effects.Loki.NetherRealmCasket_CritDamageReductionEffect$$CreateCritDamageBonus`
    = ForSubtraction( get_OwnerIsTarget,                       <- trigger NU
                      Multiply( ConfigVar(0x97 = critDmgReduction),
                                AdjacentMechanicalUnits() ) )  <- slot virtuel `+0x5f8`
`...$$CreateActiveCondition` = `AmountIsGreaterThanZero(<le MEME compteur>)`, et le compteur est
    Count( MechanicalUnits( NormalUnits( AdjacentFriends(Owner, unique: 1, selectionType: 3),
                                         3 ), 3 ) )

CE QUE CE PROBE CHERCHE A CASSER
================================
Le CANAL (`GetCritDamageBonusFromEffects` -> `CalculateCriticalDamage`) est deja confronte par
`AmuletOfTheVoidwyrm` (#589-r1-r1-r2-r1) et `SupaCyborkBody` (#503-r4). CE QUI EST NEUF ICI est le
COMPTEUR, et il a DEUX pieges que ce probe arme explicitement :

  1. **`MechanicalUnits` n'est PAS `HasTrait(Mechanical)`.**
     `IdunBattle.Entities.Selectors.MechanicalUnitsSelector$$Select` delegue a
     `IdunBattle.Entities.UnitExtensions$$IsMechanical` = `HasTrait(Mechanical 5) ||
     HasTrait(LivingMetal 1000) || HasTrait(Vehicle 0x405)`. Le bras `--trait LivingMetal` donne
     aux compagnons `LivingMetal` **SANS** `Mechanical` : un port par trait unique compterait 0.
     C'est le regime le plus probable en jeu reel -- la relique est NECRON, et tout le roster
     necron est `LivingMetal`, plusieurs SANS `Mechanical` (mesure #220).
  2. **`NormalUnits` est un etage REEL.** `UnitExtensions$$IsNormalUnit` =
     `!HasTrait(Object 0xd) && !HasTrait(Steppable 0x1b)`. Le bras `--trait LivingMetal,Steppable`
     donne un compagnon MECANIQUE mais PIETINABLE : le natif ne le compte PAS. Un port qui
     oublierait cet etage compterait 1 de trop.

MONTAGE
=======
  P (moi)  = ATTAQUANT, traits reduits a `["Hero"]`, `--crit 100,<critDamage>` -> crit GARANTI.
  A (eux)  = PORTEUR (relique niveau L, traits `["Hero"]`) + 2 COMPAGNONS, traits pilotes.
  Tous a `--hp-*` enormes : personne ne meurt, la salve est lue coup par coup.

  Le porteur est ancre, `n` compagnons sont poses ADJACENTS, le reste est POUSSE a hex >= 4, et
  l'attaquant est pose adjacent au porteur (regime NO_STEP : aucun pas, donc aucune charge).

  ⚠ INVENTAIRE NATIF OBLIGATOIRE (lecon #589-r1-r1-r2-r1-r8/r9) : `n` n'est jamais DECLARE, il est
  DERIVE de `combatSnapshot.units[].traits` -- les traits REELLEMENT portes en bataille. Un bras qui
  ne fige que les unites qu'il a posees peut mesurer autre chose que ce qu'il annonce, et rendre un
  accord par COMPENSATION.

TROIS BRAS OFFLINE, sur le MEME etat capture et le MEME dump de PRNG
====================================================================
  PORT      : doit egaler le LIVE, coup par coup.
  NOCHANNEL : l'effet retire d'`EFFECT_CLASSES` -> la factory le fait retomber sur `BaseEffect`,
              dont le hook rend `None`. C'est la vue « d'AVANT ce port ». Doit mordre SSI `n > 0`.
  PASSIF    : `tertiary_ability_state_of` retire du contexte du canal -> le port lit
              `ability_level` (50 en runner normalise) et `ability_var` CLAMPE au dernier palier.
              Doit mordre des que `L != 10`.

ASCII only (cp1252).
Usage:
  python probe_908_nether_realm_casket_crit_live.py --n 0,1,2 --level 3 --trait LivingMetal
  python probe_908_nether_realm_casket_crit_live.py --n 1 --trait LivingMetal,Steppable   # NormalUnits
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

PYDIR = Path(__file__).resolve().parent
sys.path.insert(0, str(PYDIR))
sys.path.insert(0, str(PYDIR / "tests" / "engine" / "runner"))

CARRIER = "necroDestroyer"           # porteur autorise de NetherRealmCasket, AU POOL
COMPANIONS = ("necroWarden", "necroOverlord")
ATTACKER = "blackHaarken"            # melee, plusieurs coups -- salve lisible coup par coup
EFFECT_NAME = "NetherRealmCasket_CritDamageReduction"
ABILITY_ID = "NetherRealmCasket"     # TriggeredAbilityType 0x5b6 = 1462 (la CONFIG)
VAR_KEY = "critDmgReduction"         # AbilityVariableType 0x97 = 151

#: `IdunBattle.Entities.UnitExtensions$$IsMechanical` -- les TROIS traits, par NOM gameconfig.
TRAITS_MECANIQUES = ("Mechanical", "LivingMetal", "Vehicle")
#: `UnitExtensions$$IsNormalUnit` ecarte ces deux-la (`NormalUnits`).
TRAITS_NON_NORMAUX = ("Object", "Steppable")


def _unwrap(r):
    return r.get("result") if isinstance(r, dict) and "result" in r else r


def paliers_du_gameconfig() -> list:
    """`critDmgReduction` RELU du gameconfig, jamais code en dur -- meme lecture que le port."""
    import gameconfig as GC
    arr = ((GC.ability(ABILITY_ID) or {}).get("variables") or {}).get(VAR_KEY)
    if not arr:
        raise SystemExit("%s.variables.%s absent du gameconfig" % (ABILITY_ID, VAR_KEY))
    return [int(x) for x in arr]


def _garde_regime(level, paliers, n_max, crit_dmg, traits) -> None:
    """GARDES DE REGIME, jouees AVANT tout montage -- chacune ferme une porte de vert-qui-ne-mesure-rien."""
    if not (1 <= level <= len(paliers)):
        raise SystemExit("niveau %d hors des %d paliers : le clamp haut de "
                         "`AbilityConfiguration$$TryGetVariableArrayForLevel` rendrait le bras "
                         "NIVEAU non discriminant" % (level, len(paliers)))
    v = paliers[level - 1]
    if n_max and crit_dmg - v * n_max <= 0:
        raise SystemExit("SATURATION : critDamage=%d - %d x %d <= 0, le `Math.Max(0, .)` de "
                         "`CalculateCriticalDamage` confondrait les modeles (regime DEGENERE). "
                         "Augmenter --crit-damage." % (crit_dmg, v, n_max))
    mech = [t for t in traits if t in TRAITS_MECANIQUES]
    if not mech:
        print("   [note] AUCUN trait mecanique demande (%r) : le compteur natif attendu est 0 "
              "quel que soit `n` -- c'est un bras TEMOIN, pas un bras de magnitude." % (traits,))
    print("   %s.%s[%d] = %d  (paliers %s..%s) | traits compagnons = %r"
          % (ABILITY_ID, VAR_KEY, level, v, paliers[0], paliers[-1], traits))
    if level == len(paliers):
        print("   [note] niveau == dernier palier : le bras PASSIF ne peut pas mordre. SAUTE.")


def _traits_json(spec: str) -> str:
    return ",".join('"%s"' % t.strip() for t in spec.split(",") if t.strip())


def build(a, tag, level):
    fd, sf = tempfile.mkstemp(prefix="probe_908_crit_%s_" % tag, suffix=".json")
    os.close(fd)
    Path(sf).unlink(missing_ok=True)
    argv = [sys.executable, "rl_duel.py", "build",
            "--seed", str(a.seed), "--state-file", sf, "--board", a.board,
            "--p-units", ATTACKER,
            "--a-units", "%s,%s,%s" % (CARRIER, COMPANIONS[0], COMPANIONS[1]),
            "--equip-relic", "%s:%s:%d" % (CARRIER, ABILITY_ID, level),
            # Les compagnons portent EXACTEMENT les traits demandes : c'est le seul moyen de piloter
            # `IsMechanical` / `IsNormalUnit` sans dependre du kit gameconfig (tout le roster necron
            # est LivingMetal, donc mecanique -- le compteur serait pollue par construction).
            "--unit-stat", '%s:Traits=[%s]' % (COMPANIONS[0], _traits_json(a.trait)),
            "--unit-stat", '%s:Traits=[%s]' % (COMPANIONS[1], _traits_json(a.trait)),
            # PORTEUR reduit a `Hero` : ses propres traits ne comptent pas (le compteur porte sur
            # ses VOISINS), et `Overwatch` tirerait pendant le montage.
            "--unit-stat", '%s:Traits=["Hero"]' % CARRIER,
            # ATTAQUANT reduit a `Hero` pour la LISIBILITE de la salve (cf. probe amulette).
            "--unit-stat", '%s:Traits=["Hero"]' % ATTACKER,
            "--hp-target", "900000", "--hp-player", "900000",
            "--no-ai", "--crit", "100,%d" % a.crit_damage, "--block-target", "0,0"]
    p = subprocess.run(argv, cwd=str(PYDIR), capture_output=True, text=True,
                       encoding="utf-8", errors="replace")
    if not Path(sf).exists():
        print("[%s] build KO : %s" % (tag, (p.stderr or p.stdout or "")[-800:]))
        return None, sf
    return json.loads(Path(sf).read_text())["runnerId"], sf


class MontageError(RuntimeError):
    """On REFUSE de rendre un verdict plutot que d'en fabriquer un depuis un montage muet."""


def _pos_de(u) -> tuple:
    p = (u or {}).get("pos") or {}
    return (p.get("col"), p.get("row"))


def _tid_de(board, coord):
    """`(col, row)` -> `TileId`. L'adjacence NATIVE est indexee par TileId, pas par coordonnee."""
    for tid in board.by_id:
        if board.coord(tid) == tuple(coord):
            return tid
    return None


def inventaire_mecaniques(h, dv=None) -> tuple:
    """Inventaire NATIF des unites que `IsMechanical` retiendrait, lu sur
    `combatSnapshot.units[].traits` (#233 : les traits REELLEMENT portes en bataille, veto compris)
    -- jamais le kit gameconfig, jamais ce que le montage croit avoir pose.

    La cle d'unite de `combatSnapshot` est `entityId`, PAS `id`. TRI-ETAT : `traits == None` =
    capteur MUET -> l'unite sort dans `muets`, jamais dans une liste vide qui se lirait
    « personne n'est mecanique »."""
    from engine.entities.traits.unit_trait import UnitTrait
    codes_mech = {int(getattr(UnitTrait, t)) for t in TRAITS_MECANIQUES}
    codes_pasnorm = {int(getattr(UnitTrait, t)) for t in TRAITS_NON_NORMAUX}
    snap = h.rpc("combatSnapshot", {"runnerId": h.rid}, 60)
    units = (snap.get("units") if isinstance(snap, dict) else None) or []
    dv = dv if dv is not None else h.dview()
    par_id = {u.get("id"): u for u in (dv.get("units") or [])}
    mecas, muets = [], []
    for u in units:
        eid, tr = u.get("entityId"), u.get("traits")
        if tr is None:
            muets.append(eid)
            continue
        codes = set(int(t) for t in tr)
        if codes & codes_mech:
            d = par_id.get(eid) or {}
            mecas.append({"id": eid, "visualId": d.get("visualId") or u.get("visualId"),
                          "team": d.get("team"), "pos": _pos_de(d), "alive": d.get("alive"),
                          "normal": not (codes & codes_pasnorm)})
    return mecas, muets


def pousser_loin(h, ids, loins, quoi):
    """DEPLACE des unites vers des tuiles a hex >= 4 de l'ancre -- on FORCE la configuration, on ne
    subit pas la geometrie de spawn. Leve `MontageError` si une unite ne peut pas etre eloignee."""
    for uid in ids:
        occ = {_pos_de(u) for u in h.alive()}
        if next((c for c in loins if c not in occ and h.place(uid, c)), None) is None:
            raise MontageError("impossible d'eloigner u%s (%s)" % (uid, quoi))


def _activite(h, carrier_id):
    """TRI-ETAT de la `CreateActiveCondition` NATIVE, lue sur `decisionView` (`includeInactive`).
    `None` = l'effet est ABSENT du canal, donc NON MESURE -- jamais rabattu sur `False`."""
    dvi = h.rpc("decisionView", {"runnerId": h.rid, "maxRank": 1, "allAbilities": True,
                                 "includeInactive": True}, 90)
    cu = next((u for u in (dvi.get("units") or []) if u.get("id") == carrier_id), None)
    for e in ((cu or {}).get("effects") or []):
        if e.get("name") == EFFECT_NAME:
            return bool(e.get("active"))
    return None


def stage(h, board, n, verbose=False):
    """Ancre le porteur, pose `n` compagnons ADJACENTS, ECARTE tout le reste, place l'attaquant.

    Rend `(rec, None)` ou `(None, raison)`. `rec["n_natif"]` est DERIVE de l'inventaire natif, pas
    du `n` demande : c'est ce qui empeche l'accord par compensation."""
    dv = h.dview()
    att = h.by_visual(ATTACKER, dv)
    car = h.by_visual(CARRIER, dv)
    if att is None or car is None:
        return None, "roster incomplet (att=%s car=%s)" % (att is not None, car is not None)
    h.my_player = att.get("owner")
    comps = [u for u in h.alive(dv)
             if u.get("visualId") in COMPANIONS and u.get("id") != car["id"]]
    if len(comps) < n:
        return None, "pas assez de compagnons (%d < %d)" % (len(comps), n)

    marchables = [board.coord(t) for t in sorted(board.by_id) if board.walkable(t)]
    for anchor in marchables:
        ring1 = h.free_tiles(anchor, 1, exclude=tuple(u["id"] for u in h.alive()))
        if len(ring1) < n + 1:                      # n compagnons + l'attaquant
            continue
        import hexgeo
        loins = [c for c in marchables if hexgeo.distance(c, anchor) >= 4]
        if len(loins) < len(comps):
            continue
        try:
            if not h.place(car["id"], anchor):
                continue
            # (1) TOUT le monde loin d'abord -- y compris les compagnons non retenus.
            pousser_loin(h, [u["id"] for u in comps], loins, "compagnon hors bras")
            # (2) puis on RAMENE exactement `n` compagnons sur des voisins de l'ancre.
            ring1 = h.free_tiles(anchor, 1, exclude=(car["id"],))
            poses = []
            for u in comps[:n]:
                cible = next((c for c in ring1 if h.place(u["id"], c)), None)
                if cible is None:
                    raise MontageError("impossible de poser u%s adjacent" % u["id"])
                poses.append(u["id"])
                ring1 = h.free_tiles(anchor, 1, exclude=(car["id"],))
            # (3) l'ATTAQUANT, adjacent au porteur, pose EN DERNIER (regime NO_STEP : aucun pas).
            ring1 = h.free_tiles(anchor, 1, exclude=(car["id"],))
            if not ring1 or not h.place(att["id"], ring1[0]):
                raise MontageError("impossible de poser l'attaquant adjacent")
        except MontageError as e:
            if verbose:
                print("    ancre %s refusee : %s" % (anchor, e))
            continue

        mecas, muets = inventaire_mecaniques(h)
        if muets:
            return None, "capteur de traits MUET pour %r -- inventaire non fiable" % (muets,)
        # ⚠ ADJACENCE = LA LISTE STOCKEE, PAS `hexgeo.distance == 1`. Cette ligne a d'abord ete
        # ecrite en distance hex, et elle a produit un FAUX ROUGE sur `C1_74` : `n_natif = 2` alors
        # que le natif ET le port comptaient 1 -- les degats LIVE et PORT etant IDENTIQUES, c'est
        # l'INVENTAIRE qui mentait, pas le port. `AdjacentFriends` -> `AdjacentTiles` ->
        # `AdjacentTilesSelector$$Select` -> `IBattleQuery` slot 80 = `IterateAdjacentTiles`, dont
        # `IdunBattle.Core.Services.TileQuery.u003CIterateAdjacentTilesu003Ed__8$$MoveNext` enumere
        # une LISTE STOCKEE par la tuile (`tile.<+0x30>.<+0x10>`) -- AUCUNE geometrie. Deux tuiles a
        # hex 1 peuvent donc ne PAS etre voisines. C'est exactement la mesure de
        # #589-r1-r1-r2-r1-r8, ici re-observee sur un canal independant.
        voisins = set(board.neighbours(_tid_de(board, anchor)))
        amis = [m for m in mecas
                if m["team"] == car.get("team") and m["id"] != car["id"] and m["alive"]
                and m["pos"] and _tid_de(board, m["pos"]) in voisins and m["normal"]]
        n_natif = len(amis)
        actif = _activite(h, car["id"])
        rec = {"caster": att["id"], "target": car["id"], "anchor": anchor, "step_to": None,
               "regime": "NO_STEP", "n_demande": n, "n_natif": n_natif,
               "actif_natif": actif, "poses": poses,
               "mecas_adjacents": [(m["visualId"], m["pos"], m["normal"]) for m in amis]}
        if n_natif != n:
            # On ne CORRIGE pas le montage, on le DIT : `n_natif` fait foi (il est derive de
            # l'adjacence STOCKEE), et le verdict porte sur lui. Une tuile a hex 1 peut ne pas
            # etre voisine -- le montage a donc pose un compagnon que le natif ne compte pas.
            print("[n=%d] ANCRE %s : %d compagnon(s) pose(s), %d compte(s) par l'adjacence "
                  "STOCKEE -- le verdict porte sur n_natif=%d, pas sur le n demande."
                  % (n, anchor, n, n_natif, n_natif))
        if verbose:
            print("    ancre=%s | n demande=%d | n NATIF derive=%d | effet actif natif=%s"
                  % (anchor, n, n_natif, actif))
        return rec, None
    return None, "aucune ancre ne porte la geometrie demandee (n=%d)" % n


def replay(h, rec, mutate=None):
    """Rejeu OFFLINE de la MEME attaque, RNG neutralise par le dump pris apres le montage."""
    from engine.entities.effects.factory import EFFECT_CLASSES
    from engine.runner.operations import damage as D
    saved = EFFECT_CLASSES.get(EFFECT_NAME)
    orig = D.AttackDamageOperation._crit_board
    try:
        if mutate == "NOCHANNEL":
            EFFECT_CLASSES.pop(EFFECT_NAME, None)
        if mutate == "PASSIF":
            def _sans_tertiaire(state, att_id, tgt_id):
                d = dict(orig(state, att_id, tgt_id))
                d.pop("tertiary_ability_state_of", None)
                return d
            D.AttackDamageOperation._crit_board = staticmethod(_sans_tertiaire)
        return h.replay_offline(rec)["per_hit"]
    finally:
        if saved is not None:
            EFFECT_CLASSES[EFFECT_NAME] = saved
        D.AttackDamageOperation._crit_board = orig


def etages(h, rec) -> dict:
    """DECOMPOSITION PAR ETAGE du port, sur l'etat OFFLINE reconstruit -- jamais un scalaire fitte.

    Rend, dans l'ordre du natif : le COMPTEUR (`AdjacentMechanicalUnits`), le couple `(level, mult)`
    de `GetAbilityState(effect)`, l'activite portee, et le scalaire SIGNE que le canal verse."""
    from engine.runner.components import (adjacent_friendly_mechanical_units_count,
                                          unit_state_for_effects)
    from engine.runner.operations.damage import AttackDamageOperation
    from engine.runner.operations.triggers.base import triggered_ability_state
    st = h.offline_state(rec)
    oid, aid = int(rec["target"]), int(rec["caster"])
    out = {"compteur": adjacent_friendly_mechanical_units_count(st, oid),
           "ability_state": triggered_ability_state(st, oid, ABILITY_ID)}
    effs = st.effects.active_effects(oid, unit_state_for_effects(st, oid)) if st.effects else []
    cible = next((e for e in effs if getattr(e, "name", None) == EFFECT_NAME), None)
    out["effet_actif_port"] = cible is not None
    ctx = dict(AttackDamageOperation._crit_board(st, aid, oid))
    ctx.update({"att_id": aid, "tgt_id": oid, "owner_id": oid})
    out["bonus_signe"] = (cible.create_effect_crit_damage_bonus_for_attack(ctx)
                          if cible is not None else None)
    return out


def run_case(a, rpc, Board, Harness, n, level, paliers) -> int:
    rid, sf = build(a, "n%d_l%d" % (n, level), level)
    if rid is None:
        Path(sf).unlink(missing_ok=True)
        return 2
    try:
        bg = rpc("boardGraph", {"runnerId": rid}, 90)
        h = Harness(rpc, rid, Board(bg["tiles"], adjacency="native_sym"))
        rec, why = stage(h, h.board, n, a.verbose)
        if rec is None:
            print("[n=%d lvl=%d] REFUS : %s" % (n, level, why))
            return 2
        if h.reach_my_turn(force_cycle=True) is None:
            print("[n=%d lvl=%d] REFUS : mon tour inatteignable" % (n, level))
            return 2
        rec["ability_type"] = h.normal_attack_type(rec["caster"])
        if rec["ability_type"] is None:
            print("[n=%d lvl=%d] REFUS : pas d'attaque normale" % (n, level))
            return 2
        rec["snapshot"] = h.snapshot()
        rec["rng_after_step"] = rec["snapshot"]["rng"]
        live = rpc("applyAction", {"runnerId": rid, "action": {
            "kind": "ability", "casterId": rec["caster"], "targetId": rec["target"],
            "abilityType": int(rec["ability_type"])}}, 60)
        a0 = (live.get("actions") or [{}])[0] if isinstance(live, dict) else {}
        hits = []
        for e in (a0.get("events") or []):
            td = e.get("tags")
            if not td:
                continue
            td = json.loads(td) if isinstance(td, str) else td
            if ("Amount" in td and td.get("Attacker_Id") == rec["caster"]
                    and td.get("Target_Id") == rec["target"]):
                hits.append(int(td["Amount"]))
        if not hits:
            print("[n=%d lvl=%d] REFUS : salve live VIDE (%s)" % (n, level, str(live)[:200]))
            return 2

        et = etages(h, rec)
        port = replay(h, rec)
        noch = replay(h, rec, "NOCHANNEL")
        pas_ = replay(h, rec, "PASSIF")
        v = paliers[level - 1]
        attendu = -v * rec["n_natif"] if rec["n_natif"] else None

        print("[n=%d lvl=%d] n_natif=%d actif_natif=%s | ETAGES port: compteur=%s "
              "ability_state=%s actif=%s bonus_signe=%s (attendu %s)"
              % (n, level, rec["n_natif"], rec["actif_natif"], et["compteur"],
                 et["ability_state"], et["effet_actif_port"], et["bonus_signe"], attendu))
        print("[n=%d lvl=%d] LIVE      %s" % (n, level, hits))
        print("[n=%d lvl=%d] PORT      %s" % (n, level, port))
        print("[n=%d lvl=%d] NOCHANNEL %s" % (n, level, noch))
        print("[n=%d lvl=%d] PASSIF    %s" % (n, level, pas_))

        rc = 0
        if et["compteur"] != rec["n_natif"]:
            print("   ** FAIL compteur ** port=%s != natif=%d" % (et["compteur"], rec["n_natif"]))
            rc |= 1
        if rec["actif_natif"] is not None and et["effet_actif_port"] != rec["actif_natif"]:
            print("   ** FAIL activite ** port=%s != natif=%s"
                  % (et["effet_actif_port"], rec["actif_natif"]))
            rc |= 1
        if et["bonus_signe"] != attendu:
            print("   ** FAIL magnitude ** bonus=%s != -%d x %d = %s"
                  % (et["bonus_signe"], v, rec["n_natif"], attendu))
            rc |= 1
        if port != hits:
            print("   ** FAIL degat ** port != live")
            rc |= 1
        if rec["n_natif"] > 0:
            if noch == hits:
                print("   ** MUTANT VERT (NOCHANNEL) ** : retirer l'effet ne change RIEN alors que "
                      "n=%d -- le temoin est AVEUGLE sur ce bras" % rec["n_natif"])
                rc |= 1
            if level != len(paliers) and pas_ == hits:
                print("   ** MUTANT VERT (PASSIF) ** : le niveau TERTIAIRE n'est pas ce qui est lu")
                rc |= 1
        else:
            if noch != hits:
                print("   ** FAIL ** : a n=0 le canal ne doit RIEN verser, or NOCHANNEL diverge")
                rc |= 1
        print("[n=%d lvl=%d] %s" % (n, level, "OK" if rc == 0 else "** FAIL **"))
        return rc
    finally:
        try:
            rpc("disposeRunner", {"runnerId": rid}, 15)
        except Exception:
            pass
        Path(sf).unlink(missing_ok=True)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", default="0,1,2", help="nombre de compagnons MECANIQUES adjacents")
    ap.add_argument("--level", type=int, default=3)
    ap.add_argument("--trait", default="LivingMetal",
                    help="traits POSES sur les compagnons (liste separee par des virgules)")
    ap.add_argument("--seed", type=int, default=777)
    ap.add_argument("--board", default="MC1_67")
    ap.add_argument("--crit-damage", type=int, default=4000)
    ap.add_argument("--verbose", action="store_true")
    a = ap.parse_args()

    paliers = paliers_du_gameconfig()
    ns = [int(x) for x in a.n.split(",") if x.strip()]
    print("== #908 NetherRealmCasket_CritDamageReduction -- traits compagnons = %s" % a.trait)
    _garde_regime(a.level, paliers, max(ns) if ns else 1, a.crit_damage,
                  [t.strip() for t in a.trait.split(",") if t.strip()])

    import rl_collect_batch as R
    from engine.entities.pathfinding.board import Board
    from _charge_regime import ChargeRegimeHarness
    from engine.runner import snapshot as SNAP

    sid = R._resolve_session()

    def rpc(method, body=None, timeout=60):
        return _unwrap(R._rpc(sid, method, [body] if body is not None else [], timeout=timeout))

    # CANAL RELIQUE (#357/#363) : sans transport ambiant lie, le port lit le couple PASSIF.
    SNAP.bind_live_rpc(rpc)
    rc = 0
    for n in ns:
        rc |= run_case(a, rpc, Board, ChargeRegimeHarness, n, a.level, paliers)
    print("VERDICT: %s" % ("PASS" if rc == 0 else "FAIL(%d)" % rc))
    return 0 if rc == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
