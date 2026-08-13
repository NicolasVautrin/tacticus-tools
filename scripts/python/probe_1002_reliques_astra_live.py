"""#1002 -- MESURE LIVE des deux reliques ASTRA MILITARUM, sur le NATIF.

  * `SabreOfSacrifice` (0x5c6 = 1478, `astraDreir`) -- `On(9 = Attack) & IsCharging(Caster, Target)
    & (OwnerIsCaster | <les trois termes du Death Rider>)` -> `AddEffect(1065 Pinned, Target)` +
    `AddStaticStatModifierEffect(Caster, 1473 SabreOfSacrifice_ExtraArmor, 16 FixedArmor,
    Multiply(Count(<allies normaux vaincus>), Get(extraArmor)), TurnsFromRounds(1))`.
  * `RelicOfLostCadia` (0x5b3 = 1459, `astraBullgryn` / `astraOrdnance` / `astraPrimarisPsy`) --
    `RelicOfLostCadiaAbility_SummonUnit` = `On(0 = UnitDeath, alive: 0) & OwnerIsTarget` ->
    `Spawn(astraSmnGuardsman)` dans l'hex du porteur mort.

CE QUE CE PROBE MESURE, et pourquoi ces bras-la :

  SABRE_CHARGE      Dreir se DEPLACE au contact d'une cible qui ne l'etait pas, puis l'attaque.
                    C'est le seul regime ou `BattleQuery$$IsCharging` rend vrai (le 2e terme,
                    `ChargedUnitIds.Contains(target)`, n'est ecrit que par `MoveUnitOperation$$
                    UpdateCharging` sur une adjacence NOUVELLE). Attendus : `Pinned` sur la cible
                    ET `SabreOfSacrifice_ExtraArmor` sur Dreir.
  SABRE_SANS_CHARGE CONTRE-EPREUVE du gate : meme attaque, mais la cible est DEJA adjacente et
                    Dreir ne bouge pas. Aucun des deux effets ne doit apparaitre. Sans ce bras, un
                    port qui aurait OUBLIE `IsCharging` serait vert sur le premier.
  CADIA_MORT        Le porteur de `RelicOfLostCadia` est ABATTU -> un `astraSmnGuardsman` doit
                    apparaitre. Mesure aussi ses TROIS stats de config (`summonHp`/`summonDmg`/
                    `summonArmor` au niveau TERTIAIRE) : c'est ce qui distingue un
                    `WithStatsFromConfig(config, abilityState)` d'un spawn au niveau du porteur.

⚠ Le montage relique est celui de #237, NON REECRIT : `--equip-relic` pose les TROIS ecritures, dont
DEUX echouent en silence. Le probe VERIFIE la hierarchie 3 avant toute mesure (tri-etat : canal muet
-> `MontageError`, jamais un verdict).
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


def _unwrap(r):
    return r.get("result") if isinstance(r, dict) and "result" in r else r


ABILITY_SABRE = "SabreOfSacrifice"
ABILITY_CADIA = "RelicOfLostCadia"
TRIGGERED_SABRE = 1478                                                 # 0x5c6
TRIGGERED_CADIA = 1459                                                 # 0x5b3
HIERARCHY_TERTIARY = 3                                                 # `AddConfiguredAbilities`

SABRE_CARRIER = "astraDreir"
#: `RelicOfLostCadia` a TROIS porteurs `lineup`, tous au pool rank 17 : `astraBullgryn`,
#: `astraOrdnance`, `astraPrimarisPsy`. On CONFRONTE sur `astraOrdnance`.
#: ⚠ PAS `astraBullgryn` : MESURE du 2026-08-13 -- il SURVIT a 30 attaques au contact
#: (`applyAction` rend `ok:true, changes:[]`, PV inchanges), donc le bras ne convergeait jamais.
#: Trait `BigTarget` non elucide ici ; le bras n'a pas besoin de ce porteur-la pour mesurer le
#: `Spawn` a la mort, et changer de porteur est moins couteux que d'elucider le refus.
CADIA_CARRIER = "astraOrdnance"
#: L'allie que l'on fait ABATTRE pour rendre le compte de `GetCurrentExtraArmor` NON NUL. Il doit
#: passer `IsNormalUnit` (ni `Object` 0xd ni `Steppable` 0x1b) et etre ami du porteur -- un heros
#: `lineup` du meme camp coche les deux.
SACRIFICE = "astraOrdnance"
#: Le FIGURANT allie du bras CADIA (il ne fait rien : il occupe une place et rend le camp non vide).
CADIA_FIGURANT = "astraPrimarisPsy"
GUARDSMAN_VISUAL = "astraNpc1Guardsman"                                # visualId d'astraSmnGuardsman
GUARDSMAN_CONFIG = "astraSmnGuardsman"
TARGET = "ultraTitus"
FILLER = "ultraApothecary"

EFFECT_PINNED = 1065                                                   # 0x429
EFFECT_EXTRA_ARMOR = 1473                                              # 0x5c1
EFFECT_FINAL_VENGEANCE = 1454                                          # 0x5ae
#: Le canal `decisionView.units[].effects` publie des NOMS, pas des ordinaux.
NOM_PINNED = "Pinned"
NOM_EXTRA_ARMOR = "SabreOfSacrifice_ExtraArmor"
NOM_FINAL_VENGEANCE = "FinalVengeance_UnitEffect"


def paliers(ability: str, var_key: str) -> list:
    """Paliers RELUS du gameconfig -- jamais codes en dur, meme lecture que le port."""
    import gameconfig as GC
    arr = ((GC.ability(ability) or {}).get("variables") or {}).get(var_key)
    if not arr:
        raise SystemExit("%s.variables.%s absent du gameconfig" % (ability, var_key))
    return [int(x) for x in arr]


class MontageError(RuntimeError):
    """Le montage n'a pas tenu -- ce n'est PAS un verdict sur le port."""


def _pos(u):
    p = (u or {}).get("pos") or {}
    return (p.get("col"), p.get("row"))


class Live:
    """Pilotage minimal d'un runner. Les DEUX camps sont pilotables (`applyAction` ne verifie ni
    propriete ni portee) -- c'est ce qui permet de faire ABATTRE le porteur par l'adversaire."""

    def __init__(self, rpc, rid):
        self.rpc, self.rid = rpc, rid
        self.mine = None

    def dview(self):
        return self.rpc("decisionView", {"runnerId": self.rid, "maxRank": 1,
                                         "allAbilities": True}, 90)

    def alive(self, dv=None):
        dv = dv if dv is not None else self.dview()
        return [u for u in (dv.get("units") or []) if u.get("alive")]

    def by_visual(self, v, dv=None):
        return next((u for u in self.alive(dv) if u.get("visualId") == v), None)

    def any_by_visual(self, v, dv=None):
        dv = dv if dv is not None else self.dview()
        return next((u for u in (dv.get("units") or []) if u.get("visualId") == v), None)

    def stats(self, eid):
        snap = self.rpc("combatSnapshot", {"runnerId": self.rid}, 60)
        for u in (snap.get("units") or []):
            if u.get("entityId") == eid:
                return u.get("stats") or {}
        return {}

    def effects_of(self, eid, dv=None):
        """Les NOMS d'effets ACTIFS portes par `eid`.

        ⚠ Le canal est `decisionView.units[].effects`, PAS une clef `effects` a la RACINE : le
        decisionView n'en publie aucune (mesure du 2026-08-13 -- `dv.get('effects')` rend `None`,
        et `observeBattle.units[].effects` / `combatSnapshot.units[].effects` aussi). Lire la
        racine rendait une liste VIDE pour toute unite, donc un << aucun effet >> qui ne mesurait
        rien -- exactement le vert-qui-ment que ce probe doit interdire."""
        dv = dv if dv is not None else self.dview()
        for u in (dv.get("units") or []):
            if u.get("id") != eid and u.get("casterId") != eid:
                continue
            return sorted((e.get("name") or "") for e in (u.get("effects") or []))
        return []

    def tertiary_raw(self, eid, ability_id: int):
        """`(abilityId, level, hierarchie)` de l'entree TERTIAIRE. TRI-ETAT : `None` = canal MUET."""
        uas = self.rpc("unitAbilityStates", {"runnerId": self.rid}, 40)
        for u in (uas.get("units") or []):
            if u.get("entityId") != eid:
                continue
            trig = u.get("triggered")
            if trig is None:
                return None
            for e in trig:
                raw = e.get("raw") or []
                if len(raw) >= 11 and int(raw[0]) == ability_id:
                    return (int(raw[0]), int(e.get("level") or 0), int(raw[10]))
            return ()
        return None

    def my_turn(self, max_end_turns=12):
        for _ in range(max_end_turns):
            dv = self.dview()
            if dv.get("currentPlayer") == self.mine:
                return dv
            self.rpc("applyAction", {"runnerId": self.rid,
                                     "action": {"kind": "endturn"}}, 40)
        return None

    def turn_of(self, player, max_end_turns=12):
        for _ in range(max_end_turns):
            dv = self.dview()
            if dv.get("currentPlayer") == player:
                return dv
            self.rpc("applyAction", {"runnerId": self.rid,
                                     "action": {"kind": "endturn"}}, 40)
        return None

    def place(self, uid, coord):
        self.rpc("applyAction", {"runnerId": self.rid, "action": {
            "kind": "move", "unitId": uid,
            "to": {"col": int(coord[0]), "row": int(coord[1])}}}, 40)
        u = next((x for x in self.alive() if x.get("id") == uid), None)
        return u is not None and _pos(u) == (int(coord[0]), int(coord[1]))

    def normal_attack_type(self, uid, dv=None):
        """`ActiveAbilityType` de l'attaque NORMALE de l'unite -- elle est PER-UNIT (le port ne
        peut pas la coder en dur, cf. `project_ability_normal_attack_concrete`)."""
        dv = dv if dv is not None else self.dview()
        for u in (dv.get("units") or []):
            if u.get("id") == uid:
                for x in (u.get("abilities") or []):
                    if x.get("kind") == "normal":
                        return x.get("id")
        return None

    def attack(self, attacker, target):
        """⚠ Il n'existe PAS de `kind: "attack"` : l'attaque normale EST une `ability`, dont
        l'`abilityType` est le `NormalAttackType` de l'unite (le host le dit explicitement quand on
        se trompe, et REFUSE l'action -- aucune mesure n'aurait ete produite)."""
        na = self.normal_attack_type(attacker)
        if na is None:
            raise MontageError("aucune attaque normale publiee pour l'unite %s" % attacker)
        r = self.rpc("applyAction", {"runnerId": self.rid, "action": {
            "kind": "ability", "casterId": attacker, "targetId": target,
            "abilityType": na}}, 60)
        a0 = (r.get("actions") or [{}])[0] or {}
        if not a0.get("ok"):
            raise MontageError("attaque REFUSEE (%s) -- aucune mesure" % a0.get("error"))
        return r

    def endturn(self):
        self.rpc("applyAction", {"runnerId": self.rid, "action": {"kind": "endturn"}}, 40)

    def dispose(self):
        try:
            self.rpc("disposeRunner", {"runnerId": self.rid}, 40)
        except Exception:                                              # pragma: no cover
            pass


# GEOMETRIE FORCEE (`--place` / `--a-place`) -- on DEPLACE les unites, on ne subit jamais la
# geometrie de spawn. Sur `MC1_67`, `(2,2)` `(2,3)` `(2,4)` sont trois tuiles `grass` alignees et
# deux a deux adjacentes (`hexgeo.neighbors`), `(2,2)` et `(2,4)` ne l'etant PAS entre elles : c'est
# exactement ce qu'il faut pour opposer une attaque APRES DEPLACEMENT (charge) a une attaque au
# contact SANS deplacement.
TUILE_LOIN = (2, 2)
TUILE_CONTACT = (2, 3)
TUILE_CIBLE = (2, 4)
#: L'allie SACRIFIABLE et son BOURREAU, adjacents (`hexgeo.neighbors`) et LOIN du trio ci-dessus :
#: la mise a mort ne doit RIEN changer a la geometrie de la charge.
TUILE_SACRIFICE = (5, 1)
TUILE_BOURREAU = (5, 0)
TUILE_FIGURANT = TUILE_SACRIFICE
TUILE_FIGURANT_ADV = TUILE_BOURREAU


def _place(flag: str, unit: str, coord) -> list:
    return [flag, "%s:%d,%d" % (unit, int(coord[0]), int(coord[1]))]


def flags_de_build(bras: str, level: int) -> list:
    """FOYER UNIQUE des flags de montage, partage par le probe et par son cliquet.

    `--hp-player`/`--hp-target` mettent AUSSI `Armor`/`FixedArmor` a 0 des DEUX cotes : la base
    d'armure du porteur est donc NULLE, et `fixedArmor` mesure EXACTEMENT la contribution de la
    relique -- pas un delta a soustraire d'un socle qu'on n'aurait pas mesure. `--crit 0,0` /
    `--block-target 0,0` : un tirage ne doit pas pouvoir tuer la cible-sac et interrompre la serie.
    Le bras CADIA_MORT, lui, doit pouvoir TUER le porteur : ses PV sont rabaisses par `--unit-stat`
    (pendant PER-UNIT de `--hp-player`, qui forcerait la meme valeur sur tout le camp).
    """
    if bras.startswith("SABRE"):
        depart = TUILE_CONTACT if bras == "SABRE_SANS_CHARGE" else TUILE_LOIN
        # ⚠ TEMOIN NON NUL. `GetCurrentExtraArmor` = `Multiply(Count(<allies normaux vaincus>),
        # Get(extraArmor))` : sans AUCUN allie vaincu le montant vaut 0, l'effet est pose mais ne
        # CONTRIBUE a rien, et `fixedArmor` ne bouge pas. Un bras joue dans ce regime rendrait
        # << rien ne se passe >> qu'il y ait un port ou non -- accord en regime DEGENERE, zero
        # preuve. On amene donc un allie SACRIFIABLE (`SACRIFICE`) et on le fait ABATTRE avant la
        # charge : le compte passe a 1, et l'attendu devient `extraArmor[level]` EXACTEMENT.
        return (["--equip-relic", "%s:%s:%d" % (SABRE_CARRIER, ABILITY_SABRE, level),
                 "--hp-target", "900000", "--hp-player", "900000", "--no-ai",
                 "--crit", "0,0", "--block-target", "0,0",
                 # ⚠ LES DEUX CHAMPS : `--hp-player` ecrit `Health` ET `RemainingHealth` ; ne
                 # patcher que `Health` laisse l'unite a 900000 PV COURANTS et le sacrifice ne
                 # converge jamais (mesure : 30 coups sans tuer).
                 "--unit-stat", "%s:Health=900,RemainingHealth=900" % SACRIFICE]
                + _place("--place", SABRE_CARRIER, depart)
                + _place("--place", SACRIFICE, TUILE_SACRIFICE)
                + _place("--a-place", TARGET, TUILE_CIBLE)
                + _place("--a-place", FILLER, TUILE_BOURREAU))
    return (["--equip-relic", "%s:%s:%d" % (CADIA_CARRIER, ABILITY_CADIA, level),
             "--hp-player", "900000", "--no-ai", "--crit", "0,0", "--crit-target", "0,0",
             "--unit-stat", "%s:Health=1200,RemainingHealth=1200" % CADIA_CARRIER]
            # GEOMETRIE REPRISE TELLE QUELLE du bras SABRE, ou elle a fait converger la mise a mort
            # en UN coup : porteur sur `TUILE_SACRIFICE`, bourreau `FILLER` sur `TUILE_BOURREAU`.
            # ⚠ MESURE du 2026-08-13 : sur le couple `(2,2)`/`(2,3)`, l'attaque revient
            # `ok:true, changes:[]` et les PV ne bougent pas -- action ACCEPTEE mais NO-OP, donc
            # zero convergence en 30 coups. La cause exacte n'est pas elucidee (elle n'a pas
            # d'incidence sur ce que ce bras mesure) ; ce qui compte est de NE PAS rendre un
            # verdict depuis un montage qui ne mord pas.
            + _place("--place", CADIA_CARRIER, TUILE_SACRIFICE)
            + _place("--place", CADIA_FIGURANT, TUILE_LOIN)
            + _place("--a-place", FILLER, TUILE_BOURREAU)
            + _place("--a-place", TARGET, TUILE_CIBLE))


def p_units_de(bras: str) -> str:
    if bras.startswith("SABRE"):
        return "%s,%s" % (SABRE_CARRIER, SACRIFICE)
    return "%s,%s" % (CADIA_CARRIER, CADIA_FIGURANT)


def build(a, bras: str, level: int):
    fd, sf = tempfile.mkstemp(prefix="probe_1002_%s_l%d_" % (bras, level), suffix=".json")
    os.close(fd)
    Path(sf).unlink(missing_ok=True)
    argv = ([sys.executable, "rl_duel.py", "build",
             "--seed", str(a.seed), "--state-file", sf, "--board", a.board,
             "--p-units", p_units_de(bras), "--a-units", "%s,%s" % (TARGET, FILLER)]
            + flags_de_build(bras, level))
    p = subprocess.run(argv, cwd=str(PYDIR), capture_output=True, text=True,
                       encoding="utf-8", errors="replace")
    if not Path(sf).exists():
        print("[%s] build KO : %s" % (bras, (p.stderr or p.stdout or "")[-900:]))
        return None, sf
    return json.loads(Path(sf).read_text())["runnerId"], sf


def _verifie_montage(h, visual, ability_id, level, bras):
    dv = h.dview()
    porteur = h.by_visual(visual, dv)
    if porteur is None:
        raise MontageError("[%s] porteur %s absent du decisionView" % (bras, visual))
    raw = h.tertiary_raw(porteur["id"], ability_id)
    if raw is None:
        raise MontageError("[%s] canal `unitAbilityStates.triggered` MUET -- aucune mesure "
                           "possible (tri-etat)" % bras)
    if raw == () or raw[0] != ability_id or raw[2] != HIERARCHY_TERTIARY or raw[1] != level:
        raise MontageError("[%s] relique NON montee : lu %r, attendu (%d, %d, %d) -- les trois "
                           "ecritures de #237 echouent DEUX FOIS EN SILENCE"
                           % (bras, raw, ability_id, level, HIERARCHY_TERTIARY))
    return porteur


def _voisines(board, coord):
    import hexgeo
    return list(hexgeo.neighbors(int(coord[0]), int(coord[1])))


def _abattre(h, bourreau_vis: str, victime_vis: str, bras: str, max_coups=30) -> int:
    """Fait ABATTRE `victime_vis` par `bourreau_vis` (les deux camps sont pilotables). Rend le
    nombre de coups. Leve si la victime survit -- un temoin NUL ne doit jamais passer pour une
    mesure."""
    victime = h.any_by_visual(victime_vis)
    if victime is None:
        raise MontageError("[%s] victime %s absente" % (bras, victime_vis))
    camp_bourreau = h.by_visual(bourreau_vis).get("owner")
    coups = 0
    for _ in range(max_coups):
        v = h.by_visual(victime_vis)
        if v is None:
            return coups
        if h.turn_of(camp_bourreau) is None:
            raise MontageError("[%s] tour du bourreau inatteignable" % bras)
        b = h.by_visual(bourreau_vis)
        if b is None:
            raise MontageError("[%s] bourreau %s mort en route" % (bras, bourreau_vis))
        h.attack(b["id"], v["id"])
        coups += 1
    raise MontageError("[%s] %s a survecu a %d coups -- temoin NUL, aucune mesure"
                       % (bras, victime_vis, max_coups))


def bras_sabre(a, h, bras: str, level: int, extra_armor_attendu: int) -> dict:
    """SABRE_CHARGE / SABRE_SANS_CHARGE -- la SEULE difference est la geometrie de depart."""
    dv = h.dview()
    dreir = h.by_visual(SABRE_CARRIER, dv)
    if dreir is None:
        raise MontageError("[%s] porteur absent" % bras)
    h.mine = dreir.get("owner")
    dv = h.my_turn()
    if dv is None:
        raise MontageError("[%s] le tour du porteur est inatteignable" % bras)
    _verifie_montage(h, SABRE_CARRIER, TRIGGERED_SABRE, level, bras)

    # TEMOIN NON NUL : on abat l'allie sacrifiable AVANT la charge, sinon le `Count` vaut 0 et
    # `Multiply(0, extraArmor)` rend 0 -- l'effet serait pose sans contribution mesurable.
    coups_sacrifice = _abattre(h, FILLER, SACRIFICE, bras)
    if h.my_turn() is None:
        raise MontageError("[%s] tour du porteur inatteignable apres le sacrifice" % bras)

    dreir = h.by_visual(SABRE_CARRIER)
    cible = h.by_visual(TARGET)
    if dreir is None or cible is None:
        raise MontageError("[%s] porteur ou cible absent apres le sacrifice" % bras)

    if bras == "SABRE_SANS_CHARGE":
        # Le porteur EST DEJA au contact (pose la par `--place`) et ne bouge PAS : `UpdateCharging`
        # n'est ecrit que par `MoveUnitOperation`, donc `ChargedUnitIds` reste VIDE et
        # `BattleQuery$$IsCharging` rend faux malgre l'adjacence. C'est la contre-epreuve du gate.
        if _pos(dreir) != TUILE_CONTACT or _pos(cible) != TUILE_CIBLE:
            raise MontageError("[%s] geometrie de depart inattendue : porteur %s, cible %s"
                               % (bras, _pos(dreir), _pos(cible)))
    else:
        # CHARGE : le porteur part de `TUILE_LOIN` (NON adjacente) et se deplace au contact DANS LE
        # MEME TOUR -> la cible devient NOUVELLEMENT adjacente, donc entre dans `ChargedUnitIds`.
        if _pos(dreir) != TUILE_LOIN:
            raise MontageError("[%s] le porteur n'est pas sur sa tuile de depart (%s)"
                               % (bras, _pos(dreir)))
        if not h.place(dreir["id"], TUILE_CONTACT):
            raise MontageError("[%s] impossible d'amener le porteur au contact %s"
                               % (bras, TUILE_CONTACT))
        dreir = h.by_visual(SABRE_CARRIER)

    snap_av = h.rpc("combatSnapshot", {"runnerId": h.rid}, 60)
    charges_av = next((u.get("chargedUnitIds") for u in (snap_av.get("units") or [])
                       if u.get("entityId") == dreir["id"]), None)
    avant = {"armure_porteur": h.stats(dreir["id"]).get("fixedArmor"),
             "effets_porteur": h.effects_of(dreir["id"]),
             "effets_cible": h.effects_of(cible["id"]),
             "charged_unit_ids": charges_av}
    h.attack(dreir["id"], cible["id"])
    apres = {"armure_porteur": h.stats(dreir["id"]).get("fixedArmor"),
             "effets_porteur": h.effects_of(dreir["id"]),
             "effets_cible": h.effects_of(cible["id"])}
    return {"bras": bras, "porteur": dreir["id"], "cible": cible["id"],
            "coups_sacrifice": coups_sacrifice,
            "extra_armor_attendu": extra_armor_attendu,
            "avant": avant, "apres": apres,
            "pinned_pose": (NOM_PINNED in apres["effets_cible"]
                            and NOM_PINNED not in avant["effets_cible"]),
            "armure_posee": (NOM_EXTRA_ARMOR in apres["effets_porteur"]
                             and NOM_EXTRA_ARMOR not in avant["effets_porteur"]),
            "delta_armure": ((apres["armure_porteur"] or 0) - (avant["armure_porteur"] or 0))}


def bras_cadia_mort(a, h, level: int) -> dict:
    """CADIA_MORT -- on ABAT le porteur avec l'adversaire, puis on cherche le Cadian Guardsman."""
    bras = "CADIA_MORT"
    dv = h.dview()
    porteur = h.by_visual(CADIA_CARRIER, dv)
    if porteur is None:
        raise MontageError("[%s] porteur absent" % bras)
    h.mine = porteur.get("owner")
    dv = h.my_turn()
    _verifie_montage(h, CADIA_CARRIER, TRIGGERED_CADIA, level, bras)

    tueur = h.by_visual(FILLER)
    porteur = h.by_visual(CADIA_CARRIER)
    if tueur is None or porteur is None:
        raise MontageError("[%s] porteur ou bourreau absent" % bras)
    hex_porteur = _pos(porteur)
    # Le bourreau est DEJA au contact (`TUILE_BOURREAU` est adjacente a `TUILE_SACRIFICE`).
    if hex_porteur != TUILE_SACRIFICE or _pos(tueur) != TUILE_BOURREAU:
        raise MontageError("[%s] geometrie de depart inattendue : porteur %s, bourreau %s"
                           % (bras, hex_porteur, _pos(tueur)))

    coups = _abattre(h, FILLER, CADIA_CARRIER, bras)
    porteur_vivant = h.by_visual(CADIA_CARRIER)
    dv = h.dview()
    guard = next((u for u in (dv.get("units") or [])
                  if u.get("visualId") in (GUARDSMAN_VISUAL, GUARDSMAN_CONFIG)), None)
    return {"bras": bras, "coups": coups, "porteur_mort": porteur_vivant is None,
            "hex_porteur": list(hex_porteur),
            "guardsman": None if guard is None else {
                "id": guard.get("id"), "visualId": guard.get("visualId"),
                "pos": list(_pos(guard)), "owner": guard.get("owner"),
                "stats": h.stats(guard.get("id"))}}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="#1002 -- reliques Astra, mesure LIVE")
    ap.add_argument("--board", default="MC1_67")
    ap.add_argument("--seed", type=int, default=777)
    ap.add_argument("--level", type=int, default=10)
    ap.add_argument("--bras", default="SABRE_CHARGE,SABRE_SANS_CHARGE,CADIA_MORT")
    a = ap.parse_args(argv)

    import rl_collect_batch as R
    sid = R._resolve_session()

    def rpc(method, body=None, timeout=60):
        return _unwrap(R._rpc(sid, method, [body] if body is not None else [], timeout=timeout))

    # CANAL RELIQUE : sans transport ambiant, `UnitContext.tertiary_ability` reste None et
    # `triggered_ability_state` retomberait sur le couple PASSIF (niveau 50 sur tout runner
    # normalise) -- la magnitude serait FAUSSE en silence.
    from engine.runner import snapshot as SNAP
    SNAP.bind_live_rpc(rpc)

    p_armor = paliers(ABILITY_SABRE, "extraArmor")
    if not (1 <= a.level <= len(p_armor)):
        raise SystemExit("niveau %d hors des %d paliers d'extraArmor : "
                         "`TryGetVariableArrayForLevel` CLAMPE et l'attendu serait faux"
                         % (a.level, len(p_armor)))
    if p_armor[a.level - 1] <= 0:
        raise SystemExit("extraArmor[%d] = %d : aucun observable sur `fixedArmor`"
                         % (a.level, p_armor[a.level - 1]))
    extra_armor_attendu = p_armor[a.level - 1]                # x 1 allie vaincu
    print("== #1002 -- extraArmor paliers %s ; attendu au niveau %d (1 allie vaincu) = %d"
          % (p_armor, a.level, extra_armor_attendu))

    resultats, rc = [], 0
    for bras in [b.strip() for b in a.bras.split(",") if b.strip()]:
        rid, sf = build(a, bras, a.level)
        if rid is None:
            print("[%s] MONTAGE KO -- pas de runner" % bras)
            rc = 1
            continue
        h = Live(rpc, rid)
        try:
            if bras.startswith("SABRE"):
                r = bras_sabre(a, h, bras, a.level, extra_armor_attendu)
            else:
                r = bras_cadia_mort(a, h, a.level)
            resultats.append(r)
            print(json.dumps(r, indent=1, ensure_ascii=True))
        except MontageError as e:
            print("MONTAGE : %s" % e)
            rc = 1
        finally:
            h.dispose()
            Path(sf).unlink(missing_ok=True)

    print("\n=== VERDICTS ===")
    for r in resultats:
        if r["bras"] == "SABRE_CHARGE":
            ok = (r["pinned_pose"] and r["armure_posee"]
                  and r["delta_armure"] == r["extra_armor_attendu"])
            print("SABRE_CHARGE      : Pinned=%s ExtraArmor=%s armure %s -> %s (delta %s, "
                  "attendu %s)  %s"
                  % (r["pinned_pose"], r["armure_posee"], r["avant"]["armure_porteur"],
                     r["apres"]["armure_porteur"], r["delta_armure"], r["extra_armor_attendu"],
                     "OK" if ok else "ROUGE"))
            rc = rc or (0 if ok else 1)
        elif r["bras"] == "SABRE_SANS_CHARGE":
            ok = not r["pinned_pose"] and not r["armure_posee"]
            print("SABRE_SANS_CHARGE : Pinned=%s ExtraArmor=%s  %s (contre-epreuve `IsCharging`)"
                  % (r["pinned_pose"], r["armure_posee"], "OK" if ok else "ROUGE"))
            rc = rc or (0 if ok else 1)
        elif r["bras"] == "CADIA_MORT":
            ok = r["porteur_mort"] and r["guardsman"] is not None
            print("CADIA_MORT        : porteur_mort=%s guardsman=%s  %s"
                  % (r["porteur_mort"],
                     None if r["guardsman"] is None else r["guardsman"]["pos"],
                     "OK" if ok else "ROUGE"))
            rc = rc or (0 if ok else 1)
    return rc


if __name__ == "__main__":
    raise SystemExit(main())
