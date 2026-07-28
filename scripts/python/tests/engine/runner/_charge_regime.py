"""Helper REUTILISABLE du REGIME DE CHARGE -- confronte `BattleQuery$$IsCharging` live vs offline.

Pendant d'`_ability_cast_replay.py` (cast d'ability) et d'`_pierce_floor_regime.py` (regime de
percage) : ici on monte les DEUX regimes que le predicat natif
`IdunBattle.Core.Services.BattleQuery$$IsCharging(caster, target)` SEPARE, et que le proxy
« l'unite a-t-elle bouge » (`UnitFlag.Moved`) CONFOND :

  * `CHARGE`        -- le caster part d'une tuile NON adjacente a la cible et arrive AU CONTACT.
                       `MoveUnitOperation$$UpdateCharging` ajoute la cible aux `ChargedUnitIds`
                       -> `IsCharging` VRAI.
  * `STEP_ADJACENT` -- le caster part d'une tuile DEJA adjacente a la cible et se deplace vers une
                       AUTRE tuile encore adjacente. `UpdateCharging` n'ajoute QUE les unites
                       NOUVELLEMENT adjacentes : la cible ne l'est pas -> `IsCharging` FAUX, alors
                       que le flag `Moved` est VRAI. C'est LE cas discriminant (case-231 §6 sc. 3).

Le harnais ne fait AUCUN assert : il rend les degats per-coup live et le rejeu offline, le test
appelant tranche.

PROTOCOLE (chaque marche a deja coute une mesure fausse, cf. les fiches citees) :

  1. PLACER d'abord, `reach_my_turn()` ENSUITE -- un `applyAction move` consomme une activation et
     peut FAIRE BASCULER le joueur courant ; le cast suivant est alors refuse EN SILENCE (`ok=True`,
     aucun `mutated`, 2 evenements, zero degat -- signature #111). Repasser par `reach_my_turn()`
     donne au caster un tour NEUF, flags purges (`StartTurnOperation$$ResetUnit`) : il n'a donc PAS
     bouge, et sa liste `ChargedUnitIds` a ete videe par `FinishUnitTurnOperation$$Execute`.
  2. SNAPSHOT **avant** le pas -- c'est le pas lui-meme qui remplit `ChargedUnitIds`, donc l'offline
     doit le REJOUER (`MoveUnitMessage`), jamais declarer la liste a la main : declarer
     court-circuiterait justement le morceau de port qu'on confronte.
  3. `Runner(...).install_default_handlers()` est INDISPENSABLE avant `apply` -- un `Runner` nu n'a
     aucun visiteur, `apply` ne fait rien et `charged_unit_ids` reste vide (le port paraitrait faux
     alors que le move n'a pas eu lieu).
  4. RE-SEED du MT **apres** le pas live : le flux a pu bouger (cascade after-move) ; les deux cotes
     doivent partir du MEME etat de PRNG pour que seule l'ATTAQUE soit comparee.
  5. `applyAction {kind:"move"}` rend `ok=True` MEME quand le pas est refuse (tuile occupee /
     non marchable) -> on RELIT la position apres chaque pose (`place`/`step` rendent un booleen).

Usage (fixture nommee `charge_regime`, factory de portee session) :

    from _charge_regime import charge_regime          # noqa: F401  (fixture)

    def test_x(charge_regime):
        h = charge_regime(p_units="astraBullgryn", a_units="necroOverlord,necroWarden")
        rec = h.run(regime="STEP_ADJACENT", caster_visual="astraBullgryn")
        off = h.replay_offline(rec)

ASCII only (console cp1252).
"""
from __future__ import annotations

import json

import pytest

import hexgeo
from engine.entities.pathfinding.board import Board
from engine.runner.messages import AttackUnitMessage, MoveUnitMessage
from engine.runner.prng import IntBasedMersenneTwister
from engine.runner.runner import Runner
from engine.runner.snapshot import load_state

CHARGE = "CHARGE"                    # part de loin, arrive au contact -> IsCharging VRAI
STEP_ADJACENT = "STEP_ADJACENT"      # part deja au contact, se decale -> IsCharging FAUX
NO_STEP = "NO_STEP"                  # n'a pas bouge du tour -> IsCharging FAUX (controle)


def _ok(r):
    return isinstance(r, dict) and r.get("ok")


def _upos(u):
    p = u.get("pos") or {}
    return (p.get("col"), p.get("row")) if p.get("col") is not None else None


def _seed_rng(dump):
    rng = IntBasedMersenneTwister()
    rng.mt = list(dump["mt"])
    rng.mti = dump["mti"]
    return rng


class ChargeRegimeHarness:
    """Une bataille isolee ou l'on impose le regime de charge du caster, action par action.

    Attributs : `rid` (runnerId), `board` (`Board`, adjacence `native_sym`), `my_player`."""

    def __init__(self, rpc, rid, board):
        self.rpc, self.rid, self.board = rpc, rid, board
        self.my_player = None

    # ------------------------------------------------------------------ lecture d'etat live

    def dview(self):
        return self.rpc("decisionView",
                        {"runnerId": self.rid, "maxRank": 1, "allAbilities": True}, 90)

    def alive(self, dv=None):
        """Unites VIVANTES (le `decisionView` GARDE les cadavres)."""
        dv = dv if dv is not None else self.dview()
        return [u for u in (dv.get("units") or []) if u.get("alive")]

    def by_visual(self, visual_id, dv=None):
        return next((u for u in self.alive(dv) if u.get("visualId") == visual_id), None)

    def enemies_of(self, player, dv=None):
        return [u for u in self.alive(dv) if u.get("owner") != player]

    def normal_attack_type(self, unit_id, dv=None):
        """L'attaque normale est un `ActiveAbilityType` PAR UNITE (`kind == 'normal'` du
        `decisionView`), jamais l'id generique 17 -- cf. `NormalAttackType@0x28`."""
        dv = dv if dv is not None else self.dview()
        for u in (dv.get("units") or []):
            if u.get("id") == unit_id:
                for a in (u.get("abilities") or []):
                    if a.get("kind") == "normal":
                        return a.get("id")
        return None

    # ------------------------------------------------------------------ pilotage

    def reach_my_turn(self, max_end_turns=12):
        """Enchaine des `endturn` jusqu'a mon tour. Purge au passage les flags de tour du caster
        (`StartTurnOperation$$ResetUnit`) ET ses `ChargedUnitIds` (vides par
        `FinishUnitTurnOperation$$Execute`) : l'etat de depart est donc « n'a pas bouge, n'a rien
        charge », ce qu'exige tout montage de charge."""
        dv = self.dview()
        if self.my_player is None:
            mine = self.alive(dv)
            self.my_player = mine[0].get("owner") if mine else None
        for _ in range(max_end_turns):
            if dv.get("currentPlayer") == self.my_player:
                return dv
            self.rpc("applyAction", {"runnerId": self.rid, "action": {"kind": "endturn"}}, 40)
            dv = self.dview()
        return dv if dv.get("currentPlayer") == self.my_player else None

    def place(self, unit_id, coord):
        """Pose `unit_id` sur `coord` (`applyAction` ne verifie NI propriete NI portee : les DEUX
        camps sont pilotables). RELIT la position -> True SSI le pas a reellement eu lieu."""
        self.rpc("applyAction", {"runnerId": self.rid, "action": {
            "kind": "move", "unitId": unit_id,
            "to": {"col": int(coord[0]), "row": int(coord[1])}}}, 40)
        u = next((x for x in self.alive() if x.get("id") == unit_id), None)
        return u is not None and _upos(u) == (int(coord[0]), int(coord[1]))

    def free_tiles(self, center, radius, exclude=()):
        """Tuiles MARCHABLES a distance hex EXACTEMENT `radius` de `center`, libres de toute unite
        vivante (hors `exclude`). Ordre deterministe (id de tuile croissant)."""
        occupied = {_upos(u) for u in self.alive() if u.get("id") not in set(exclude)}
        out = []
        for t in sorted(self.board.by_id):
            c = self.board.coord(t)
            if (self.board.walkable(t) and hexgeo.distance(tuple(center), c) == radius
                    and c not in occupied and c != tuple(center)):
                out.append(c)
        return out

    def snapshot(self):
        """Fige l'etat courant : `decisionView` + `observeBattle` + `combatSnapshot` + `dumpRng`."""
        return {
            "dv": self.dview(),
            "ob": self.rpc("observeBattle", {"runnerId": self.rid}, 40),
            "snap": self.rpc("combatSnapshot", {"runnerId": self.rid}, 60),
            "rng": self.rpc("dumpRng", {"runnerId": self.rid}, 30),
        }

    # ------------------------------------------------------------------ montage des regimes

    def arrange(self, caster_visual, regime, enemy_index=0):
        """Impose la GEOMETRIE du regime demande et rend
        `{caster, target, start, step_to, regime}` (coordonnees (col,row)), ou None si la
        geometrie n'est pas realisable sur ce board.

        On DEPLACE les unites pour obtenir la configuration voulue -- jamais « bloque par la
        geometrie de spawn ». Les placements se font AVANT `reach_my_turn` (cf. protocole en tete).

          * `CHARGE`        : caster pose a distance 2 de la cible, pas vers une tuile adjacente.
          * `STEP_ADJACENT` : caster pose ADJACENT a la cible, pas vers une AUTRE tuile adjacente
                              a la MEME cible (la cible n'est donc jamais « nouvellement adjacente »).
          * `NO_STEP`       : caster pose adjacent, aucun pas (controle negatif).
        """
        dv = self.dview()
        me = self.by_visual(caster_visual, dv)
        if me is None:
            return None
        self.my_player = me.get("owner")
        ens = self.enemies_of(self.my_player, dv)
        if len(ens) <= enemy_index:
            return None
        tgt = ens[enemy_index]

        # Ancre la cible sur une tuile a 6 voisins marchables -> les deux regimes y tiennent.
        anchors = [self.board.coord(t) for t in sorted(self.board.by_id)
                   if self.board.walkable(t)
                   and len([c for c in self.free_tiles(self.board.coord(t), 1,
                                                       exclude=(tgt["id"], me["id"]))]) >= 3]
        for anchor in anchors:
            if not self.place(tgt["id"], anchor):
                continue
            # Les AUTRES ennemis sont ecartes a >= 3 : ils ne doivent ni etre charges par le pas,
            # ni encaisser de splash, ni polluer `ChargedUnitIds`.
            for other in ens:
                if other["id"] == tgt["id"]:
                    continue
                far = self.free_tiles(anchor, 4, exclude=(other["id"],))
                if far:
                    self.place(other["id"], far[0])
            ring1 = self.free_tiles(anchor, 1, exclude=(me["id"],))
            if regime == CHARGE:
                ring2 = self.free_tiles(anchor, 2, exclude=(me["id"],))
                for start in ring2:
                    for step_to in ring1:
                        if hexgeo.distance(start, step_to) != 1:
                            continue          # pas d'UN hex (portee de mouvement minimale)
                        if self.place(me["id"], start):
                            return {"caster": me["id"], "target": tgt["id"], "start": start,
                                    "step_to": step_to, "regime": regime, "anchor": anchor}
            elif regime == STEP_ADJACENT:
                for start in ring1:
                    for step_to in ring1:
                        if step_to == start or hexgeo.distance(start, step_to) != 1:
                            continue
                        if self.place(me["id"], start):
                            return {"caster": me["id"], "target": tgt["id"], "start": start,
                                    "step_to": step_to, "regime": regime, "anchor": anchor}
            else:   # NO_STEP
                for start in ring1:
                    if self.place(me["id"], start):
                        return {"caster": me["id"], "target": tgt["id"], "start": start,
                                "step_to": None, "regime": regime, "anchor": anchor}
        return None

    def run(self, caster_visual, regime, enemy_index=0):
        """Monte le regime, atteint mon tour, SNAPSHOTe, joue le pas puis l'ATTAQUE NORMALE en LIVE.

        Rend `{...arrange, snapshot, rng_after_step, live_per_hit, ability_type, moved}` ou None si
        la geometrie ou le tour n'ont pas pu etre obtenus. Le snapshot est pris AVANT le pas : c'est
        la seule facon d'avoir un offline qui rejoue LUI-MEME `UpdateCharging`."""
        plan = self.arrange(caster_visual, regime, enemy_index=enemy_index)
        if plan is None:
            return None
        if self.reach_my_turn() is None:
            return None
        # Re-verifie la geometrie APRES les endturns (une cascade a pu deplacer/tuer quelqu'un).
        dv = self.dview()
        pos = {u["id"]: _upos(u) for u in self.alive(dv)}
        if pos.get(plan["caster"]) != plan["start"] or pos.get(plan["target"]) is None:
            return None
        plan["ability_type"] = self.normal_attack_type(plan["caster"], dv)
        if plan["ability_type"] is None:
            return None
        plan["snapshot"] = self.snapshot()
        plan["moved"] = True
        if plan["step_to"] is not None:
            plan["moved"] = self.place(plan["caster"], plan["step_to"])
            if not plan["moved"]:
                return None
        plan["rng_after_step"] = self.rpc("dumpRng", {"runnerId": self.rid}, 30)
        res = self.rpc("applyAction", {"runnerId": self.rid, "action": {
            "kind": "ability", "casterId": plan["caster"], "targetId": plan["target"],
            "abilityType": int(plan["ability_type"])}}, 60)
        a0 = (res.get("actions") or [{}])[0] if isinstance(res, dict) else {}
        hits = []
        for e in (a0.get("events") or []):
            td = e.get("tags")
            if not td:
                continue
            td = json.loads(td) if isinstance(td, str) else td
            if ("Amount" in td and td.get("Attacker_Id") == plan["caster"]
                    and td.get("Target_Id") == plan["target"]):
                hits.append(int(td["Amount"]))
        plan["live_ok"] = bool(_ok(res) and a0.get("ok"))
        plan["live_per_hit"] = hits
        plan["live_raw"] = res
        return plan

    # ------------------------------------------------------------------ rejeu offline

    def offline_state(self, rec):
        """Reconstruit un `State` OFFLINE depuis le snapshot PRE-pas, REJOUE le pas (donc
        `update_charging` + `set_moved_flag` sont poses PAR LE MOTEUR, pas declares), puis cale le MT
        sur le dump pris APRES le pas live. Rejouable : chaque appel rend un etat neuf."""
        s = rec["snapshot"]
        st = load_state(s["dv"], s["ob"], s["snap"], board=self.board)
        if rec.get("step_to") is not None:
            Runner(st).install_default_handlers().apply(
                MoveUnitMessage(rec["caster"], tuple(rec["step_to"])))
        dump = rec.get("rng_after_step") or s["rng"]
        if isinstance(dump, dict) and dump.get("mt"):
            st.rng = _seed_rng(dump)
        return st

    def replay_offline(self, rec):
        """Rejoue l'ATTAQUE NORMALE offline et rend `{per_hit, state, charged}`.
        `charged` = la liste `UnitComponent.ChargedUnitIds` du caster APRES le pas (le 2e terme de
        `BattleQuery$$IsCharging`)."""
        from engine.runner.components import UnitComponent
        st = self.offline_state(rec)
        e = st.get_entity(rec["caster"])
        uc = e.get_component(UnitComponent) if e is not None else None
        charged = sorted(int(i) for i in (uc.charged_unit_ids or ())) if uc is not None else []
        runner = Runner(st).install_default_handlers(20)
        runner.apply(AttackUnitMessage(attacker_id=rec["caster"], target_id=rec["target"]))
        per_hit = list((runner.damage_handler.last or {}).get("per_hit") or [])
        return {"per_hit": per_hit, "state": st, "charged": charged}

    def dispose(self):
        self.rpc("disposeRunner", {"runnerId": self.rid}, 20)


@pytest.fixture(scope="session")
def charge_regime(rpc, build_runner):
    """FABRIQUE de `ChargeRegimeHarness` -- fixture NOMMEE, reutilisable par tout test de charge.

    `make(p_units=..., a_units=..., seed=..., board=..., extra=[...])`. Le `--board` est OBLIGATOIRE
    au build ; defaut `MC1_67` (arene). Les PV sont gonfles par defaut pour qu'aucune cible ne meure
    en cours de montage (un cadavre change la geometrie ET le flux d'evenements)."""
    def make(p_units, a_units, seed="777", board="MC1_67", extra=None):
        args = ["--p-units", p_units, "--a-units", a_units,
                "--hp-target", "120000", "--hp-player", "120000", "--no-ai", *(extra or [])]
        rid = build_runner(seed, extra=args, board=board)["rid"]
        bg = rpc("boardGraph", {"runnerId": rid}, 60)
        if not (isinstance(bg, dict) and bg.get("tiles")):
            pytest.skip("boardGraph indispo")
        h = ChargeRegimeHarness(rpc, rid, Board(bg["tiles"], adjacency="native_sym"))
        if not _ok(h.dview()):
            pytest.skip("decisionView KO")
        return h
    return make
