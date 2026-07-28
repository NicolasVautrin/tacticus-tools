"""MONTAGE REUTILISABLE du porteur SUMMON `blackSmnBloodletter` -- et POSTURE D'OBSERVATION.

Le gate de confrontabilite compte les SUMMONS, a condition de les amener par leur SUMMONER. Ici :
`blackPossession` <<Archimatos>> (HERO du pool) caste son ACTIVE `Incursion` (1021), qui fait
apparaitre jusqu'a `maxSummons`=6 Bloodletters sur les hex LIBRES adjacents a sa cible
(`IdunBattleLogic.Entities.Abilities.Active.Loki.IncursionAbility$$ExecuteBehaviour` -- une
`ChainBehaviour` bornee, 1 spawn par iteration).

═══ POURQUOI ON OBSERVE AU LIEU DE PILOTER (le point qui a coute le plus cher) ═══

**Un summon ne se pilote pas.** Mesures live, verbatim :

  * il est AUTO-ACTIVE par l'IA au debut de chaque tour de son camp, et cette activation est
    CONSOMMEE par son deplacement -- apres quoi `hasAction=False`, `applyAction {kind:"ability"}`
    rend `mutated=False` (signature #111) et meme `aiPlayByUnit` ne le fait plus attaquer :
        [endturn] mutated=True currentPlayer=3
        [caster] hasAction=False
        [manuel] mutated=False eventCount=2 hits=[]
        [ia]     activations=1 demos=1 hits=[]
  * il REBOUGE tout seul au tour suivant, et il EXPIRE apres ~2 tours :
        [apres-place(0,0)] cp=4  summon pos=(0,0)
        [endturn#1]        cp=3  summon pos=(0,3)     <- 3 hex vers l'ennemi (Movement=3)
        [endturn#3]        cp=3  summon pos=(2,5)
        [endturn#5]        cp=3  summon ABSENT

Le harnais `_charge_regime` veut PILOTER le caster (poser la geometrie, puis jouer le pas ET
l'attaque). Ses `place()` marchent -- ce sont de vrais `MoveUnitOperation` -- mais l'ATTAQUE finale
est refusee. On renverse donc la posture : **on POSE la geometrie, on laisse l'IA jouer, et on LIT
le resultat** dans les `changes` de l'`applyAction endturn`, qui portent tout ce qu'il faut :

    {"squadId": 77, "from": (0,1), "to": (0,1), "moved": false,
     "hpBefore": 118279, "hpAfter": 114994, "hpDelta": -3285}     <- la CIBLE encaisse
    {"squadId": 99, "from": (0,3), "to": (0,2), "moved": true,
     "hpBefore": 3888,   "hpAfter": 3888,   "hpDelta": 0}         <- le SUMMON a CHARGE

⚠ `eventCount` vaut 0 sur cette action et `events` est vide : les coups ne sont PAS publies event
par event. Le `hpDelta` des `changes` est la SEULE observable du degat -- d'ou la strategie de
BORNES (`replay_attack_offline(..., force_no_charge=...)` : on encadre le delta live par les deux
rejeux offline, avec et sans le bonus ; un MATCH n'est probant que si les deux bornes DIFFERENT).

═══ DEUX PIEGES DE ROSTER, MESURES ═══

1. **Un Bloodletter n'a pas de PV gonfles** (`--hp-player` ne s'applique qu'aux unites du BUILD, pas
   a un summon apparu en cours de bataille : 3888 PV). Il meurt au moindre degat, et le montage se
   lit alors comme « geometrie non realisable ». Avec `necroWarden,necroDestroyer` la trace des
   poses le dit sans ambiguite -- la 1re pose du caster echoue, puis TOUTES les suivantes ont une
   position de depart `None` (l'unite n'est plus dans `alive()`) :
        (77, (6,8), (0,4), True), (79, (6,7), (1,4), True),
        (98, (3,6), (0,2), False), (98, None, (1,2), False), (98, None, (2,0), False), ...
   `necroDestroyer` porte **Overwatch** (il tire sur toute unite ennemie qui bouge dans sa zone --
   et les `place()` SONT des deplacements) et `necroWarden` porte `RelentlessMarch_DangerZone`
   (1068). => cibles SANS Overwatch ni zone de danger : condition de REALISABILITE, pas de confort.

2. **Cible NON PSYKER obligatoire** : le meme kit porte un SECOND effet,
   `UnstoppableFerocity_ExtraHit` (0x4a8=1192) = `ForAddition(HasTrait(target, 0x3ea = Psyker) &
   get_OwnerIsCaster, Direct(1))`, SANS aucun noeud `IsCharging`. Sur une cible Psyker les deux +1
   se confondraient et le regime discriminant ne discriminerait plus rien.

`orksNob` (Hero/GetStuckIn/BeastSlayer/Unstoppable) et `tyranTyrantGuard` (Hero/BigTarget/
CrushingStrike) satisfont les deux conditions.

ASCII only.
"""
from __future__ import annotations

import hexgeo

from _charge_regime import ChargeRegimeHarness

SUMMONER = "blackPossession"          # <<Archimatos>>, HERO du pool
SUMMON_VIS = "blackSmnBloodletter"    # porteur du passif UnstoppableFerocity (effet 1032)
INCURSION = 1021                      # ActiveAbilityType.Incursion
INCURSION_RANGE = 2                   # `constants.range` -- garde d'EXECUTION, pas de targeting
EFFECT_NAME = "UnstoppableFerocity_OwnerEffect"   # nom CAPTE (effect-type-names.ts:157)
EFFECT_ID = 1032

# Roster ennemi par defaut : ni Psyker, ni Overwatch, ni zone de danger (cf. en-tete).
SAFE_ENEMIES = "orksNob,tyranTyrantGuard"
SAFE_TARGET = "orksNob"

CHARGE = "CHARGE"          # caster pose a distance 2 -> c'est l'IA qui l'amene AU CONTACT
ADJACENT = "ADJACENT"      # caster pose DEJA au contact, cible amenee en DERNIER -> liste caster VIDE


def _upos(u):
    p = u.get("pos") or {}
    return (p.get("col"), p.get("row"))


def summon_bloodletters(rpc, rid, enemy_visual):
    """Rapproche Archimatos de `enemy_visual` tour par tour jusqu'a ce que le NATIF publie une cible
    legale pour `Incursion` ET que la distance hex soit <= `INCURSION_RANGE`, puis CASTE.

    DEUX portes DISTINCTES, et c'est le piege du montage (deja documente par `_summon_montage`) : la
    porte de TARGETING (`abilityTargets`) accepte une cible bien au-dela de la garde d'EXECUTION
    `IdunBattleLogic.Entities.Abilities.Active.Loki.IncursionAbility$$GetNextSpawnTile`, qui exige
    `IsInRange(caster, target, range=2)` -- un cast « legal » a distance 5 rend ZERO summon.

    Rend `({new, cast, target_id, summoner_id}, None)` ou `(None, "raison")`. `new` vient du
    `decisionView` POST-cast : ces unites portent deja leurs `effects`, ce qui permet de verifier
    que le passif du summon est materialise (donc lisible par `load_state` cote offline)."""

    def dview():
        return rpc("decisionView", {"runnerId": rid, "maxRank": 1, "allAbilities": True}, 90)

    def legal(uid):
        at = rpc("abilityTargets", {"runnerId": rid}, 90)
        out = []
        for u in (at.get("units") or []):
            if u.get("unitId") != uid:
                continue
            for a in (u.get("abilities") or []):
                if a.get("abilityId") != INCURSION:
                    continue
                out += [t["targetId"] for t in (a.get("targets") or [])
                        if t.get("targetId") is not None]
        return out

    for _ in range(16):
        dv = dview()
        c = next((u for u in (dv.get("units") or []) if u.get("visualId") == SUMMONER), None)
        e = next((u for u in (dv.get("units") or []) if u.get("visualId") == enemy_visual), None)
        if c is None or e is None:
            return None, "summoner/ennemi absent du build"
        if dv.get("currentPlayer") != c.get("owner"):
            rpc("applyAction", {"runnerId": rid, "action": {"kind": "endturn"}}, 60)
            continue
        cp, ep = _upos(c), _upos(e)
        if cp[0] is None or ep[0] is None:
            return None, "positions absentes"
        d = hexgeo.distance(cp, ep)
        tg = legal(c["id"])
        if tg and d <= INCURSION_RANGE:
            ids_before = {u["id"] for u in dv["units"]}
            tid = e["id"] if e["id"] in tg else tg[0]
            act = rpc("applyAction", {"runnerId": rid, "action": {
                "kind": "ability", "casterId": c["id"], "targetId": tid,
                "abilityType": INCURSION}}, 120)
            a0 = ((act or {}).get("actions") or [{}])[0]
            if not a0.get("mutated"):
                return None, "cast Incursion non mute : %s" % a0.get("error")
            new = [u for u in (dview().get("units") or []) if u["id"] not in ids_before]
            if not [u for u in new if u.get("visualId") == SUMMON_VIS]:
                return None, "cast mute mais aucun %s apparu" % SUMMON_VIS
            return {"new": new, "cast": a0, "target_id": tid, "summoner_id": c["id"]}, None
        mov = rpc("aiMovableTiles", {"runnerId": rid}, 60)
        mu = next((m for m in (mov.get("units") or []) if m.get("unitId") == c["id"]), None)
        best = None
        for t in (mu or {}).get("tiles") or []:
            if t.get("col") is None:
                continue
            dd = hexgeo.distance((t["col"], t["row"]), ep)
            if best is None or dd < best[0]:
                best = (dd, (t["col"], t["row"]))
        if best is None or best[0] >= d:
            rpc("applyAction", {"runnerId": rid, "action": {"kind": "endturn"}}, 60)
            continue
        rpc("applyAction", {"runnerId": rid, "action": {
            "kind": "move", "unitId": c["id"], "to": {"col": best[1][0], "row": best[1][1]}}}, 60)
    return None, "aucune cible legale a portee %d pour Incursion" % INCURSION_RANGE


def on_appearance_hits(cast_action, summon_ids, target_id):
    """Coups PAR COUP de l'attaque on-appearance (`UseNormalAttackIfAble`) de chaque Bloodletter,
    lus dans les events du cast. Contrairement a l'`endturn`, CETTE action publie bien ses events.

    C'est le TEMOIN « adjacent SANS pas » : le summon apparait AU CONTACT de la cible et frappe
    immediatement, sans aucun `MoveUnitOperation` -- donc `ChargedUnitIds` vide, `IsCharging` FAUX.
    Rend `{attacker_id: [amount, ...]}`."""
    import json as _json
    out = {}
    ids = set(summon_ids)
    for e in (cast_action.get("events") or []):
        td = e.get("tags")
        if not td:
            continue
        t = _json.loads(td) if isinstance(td, str) else td
        if isinstance(t, dict) and "Amount" in t and t.get("Attacker_Id") in ids \
                and t.get("Target_Id") == target_id:
            out.setdefault(t["Attacker_Id"], []).append(int(t["Amount"]))
    return out


class BloodletterHarness(ChargeRegimeHarness):
    """`ChargeRegimeHarness` reutilise pour tout ce qui est LECTURE D'ETAT et POSE (`dview`,
    `alive`, `by_visual`, `enemies_of`, `free_tiles`, `place` + sa TRACE, `snapshot`) -- seule la
    boucle « pas + attaque pilotes » est remplacee par l'observation (cf. l'en-tete du module).

    ⚠ UN RUNNER PAR REGIME. Aucun `FinishUnitTurnOperation$$Execute` ne survient entre deux poses,
    et `UpdateCharging` **AJOUTE sans jamais vider** (mirror lu : `if (!before.Contains(u))
    if (!ChargedUnitIds.Contains(u.Id)) Add(u.Id)`). Enchainer deux regimes sur le MEME caster
    laisserait la charge du premier polluer le second."""

    def park_others(self, anchor, keep_ids):
        """Ecarte tous les ennemis SAUF `keep_ids` a distance 5 de l'ancre : ni charges par le pas
        de l'IA, ni encaisseurs de splash, ni cibles alternatives pour l'IA."""
        for u in list(self.alive()):
            if u.get("id") in keep_ids or u.get("owner") == self.my_player:
                continue
            far = self.free_tiles(anchor, 5, exclude=(u["id"],))
            if far:
                self.place(u["id"], far[0])

    def pick_anchor(self, caster_id, target_id, min_free=4):
        """Premiere tuile marchable ayant >= `min_free` voisins libres (l'IA doit avoir de la place
        pour approcher)."""
        for t in sorted(self.board.by_id):
            c = self.board.coord(t)
            if self.board.walkable(t) \
                    and len(self.free_tiles(c, 1, exclude=(target_id, caster_id))) >= min_free:
                return c
        return None

    def arrange_regime(self, caster_id, target_id, regime):
        """Pose la geometrie de depart. Rend `{anchor, caster_pos, target_pos, dist}` ou None.

        ORDRE DES POSES -- NE PAS L'INVERSER. Un `place()` est un `MoveUnitOperation` COMPLET : il
        appelle `UpdateCharging`, qui ecrit dans la liste **DE L'UNITE QUI BOUGE**.
          * `CHARGE`   : la CIBLE est posee d'abord sur l'ancre, le caster ENSUITE a distance 2 (il
                         ne devient pas adjacent -> sa liste reste VIDE). C'est le pas de l'IA, au
                         debut de mon tour, qui produira la charge -- pas le montage.
          * `ADJACENT` : le CASTER est pose d'abord (cible GAREE loin), la CIBLE est AMENEE en
                         dernier sur l'ancre -> c'est SA liste qui s'ecrit, jamais celle du caster.
                         Geometrie finale identique a une charge, `ChargedUnitIds` du caster VIDE.
                         C'est le regime DISCRIMINANT : le caster a BOUGE (flag `Moved` VRAI) mais
                         n'a PAS charge -- un port gate par `has_moved` y accorderait le bonus."""
        anchor = self.pick_anchor(caster_id, target_id)
        if anchor is None:
            return None
        self.park_others(anchor, {target_id})
        if regime == CHARGE:
            if not self.place(target_id, anchor):
                return None
            ring2 = self.free_tiles(anchor, 2, exclude=(caster_id, target_id))
            if not ring2 or not self.place(caster_id, ring2[0]):
                return None
        else:
            park = self.free_tiles(anchor, 5, exclude=(target_id, caster_id))
            if not park or not self.place(target_id, park[0]):
                return None
            ring1 = self.free_tiles(anchor, 1, exclude=(caster_id, target_id))
            if not ring1 or not self.place(caster_id, ring1[0]):
                return None
            if not self.place(target_id, anchor):
                return None
        pos = {u["id"]: _upos(u) for u in self.alive()}
        cp, tp = pos.get(caster_id), pos.get(target_id)
        if cp is None or tp is None or cp[0] is None or tp[0] is None:
            return None
        return {"anchor": anchor, "caster_pos": cp, "target_pos": tp,
                "dist": hexgeo.distance(cp, tp)}

    def observe_endturn(self, caster_id, target_id):
        """`applyAction endturn` -> le summon est AUTO-ACTIVE par l'IA. Rend les `changes` decodes :
        `{caster_from, caster_to, caster_moved, target_hp_before, target_hp_after, target_delta}`.

        C'est LA source : `events` est vide et `eventCount` vaut 0 sur cette action (mesure), donc
        le `hpDelta` des `changes` est la seule observable du degat inflige."""
        res = self.rpc("applyAction", {"runnerId": self.rid,
                                       "action": {"kind": "endturn"}}, 120)
        a0 = ((res or {}).get("actions") or [{}])[0]
        out = {"caster_from": None, "caster_to": None, "caster_moved": None,
               "target_hp_before": None, "target_hp_after": None, "target_delta": None,
               "mutated": a0.get("mutated"), "changes": a0.get("changes")}
        for ch in (a0.get("changes") or []):
            f, t = ch.get("from") or {}, ch.get("to") or {}
            if ch.get("squadId") == caster_id:
                out["caster_from"] = (f.get("col"), f.get("row"))
                out["caster_to"] = (t.get("col"), t.get("row"))
                out["caster_moved"] = bool(ch.get("moved"))
            elif ch.get("squadId") == target_id:
                out["target_hp_before"] = ch.get("hpBefore")
                out["target_hp_after"] = ch.get("hpAfter")
                out["target_delta"] = -(ch.get("hpDelta") or 0)
        return out


def replay_attack_offline(snapshot, board, caster_id, target_id, move_to=None,
                          force_no_charge=False):
    """Rejoue OFFLINE, depuis le snapshot PRE-`endturn`, le pas OBSERVE puis l'attaque normale.

    `move_to` = la tuile ou l'IA a effectivement amene le caster (lue dans les `changes`) : le pas
    est REJOUE par le moteur (`MoveUnitMessage`), donc `update_charging` est pose PAR LE MOTEUR,
    jamais declare a la main -- c'est exactement le morceau de port qu'on confronte.

    `force_no_charge=True` = BORNE DIAGNOSTIQUE : l'effet 1032 est retire du caster avant l'attaque.
    L'ecart entre les deux bornes est ce qui rend un MATCH probant (sans lui, un accord pourrait
    etre le MATCH trivial « aucun bonus des deux cotes »).

    Rend `{per_hit, hits, total, clean_min, clean_max, charged, effect_present}`."""
    from engine.runner.components import UnitComponent
    from engine.runner.messages import AttackUnitMessage, MoveUnitMessage
    from engine.runner.prng import IntBasedMersenneTwister
    from engine.runner.runner import Runner
    from engine.runner.snapshot import load_state

    st = load_state(snapshot["dv"], snapshot["ob"], snapshot["snap"], board=board)
    if move_to is not None:
        Runner(st).install_default_handlers().apply(MoveUnitMessage(caster_id, tuple(move_to)))
    dump = snapshot.get("rng")
    if isinstance(dump, dict) and dump.get("mt"):
        rng = IntBasedMersenneTwister()
        rng.mt = list(dump["mt"])
        rng.mti = dump["mti"]
        st.rng = rng
    e = st.get_entity(caster_id)
    uc = e.get_component(UnitComponent) if e is not None else None
    charged = sorted(int(i) for i in (uc.charged_unit_ids or ())) if uc is not None else []
    present = [x for x in ((st.effects.by_unit.get(caster_id) or []) if st.effects else [])
               if x.effect_type == EFFECT_ID or x.name == EFFECT_NAME]
    if force_no_charge and st.effects is not None:
        st.effects.by_unit[caster_id] = [
            x for x in (st.effects.by_unit.get(caster_id) or [])
            if not (x.effect_type == EFFECT_ID or x.name == EFFECT_NAME)]
    runner = Runner(st).install_default_handlers(20)
    runner.apply(AttackUnitMessage(attacker_id=caster_id, target_id=target_id))
    last = runner.damage_handler.last or {}
    return {"per_hit": list(last.get("per_hit") or []), "hits": last.get("hits"),
            "total": last.get("total"), "clean_min": last.get("clean_min"),
            "clean_max": last.get("clean_max"), "charged": charged,
            "effect_present": bool(present), "state": st}
