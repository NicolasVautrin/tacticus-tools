"""#433-r4-r2-r1-r2-r2-r1-r1-r1-r4 -- le QUATRIEME gate CASTER, et ce qu'il debloque.

LA QUESTION BINAIRE. `IdunBattle.Core.Services.AttackQuery$$GetAllTilesInAbilityRange` (surcharge
4 arguments) evalue QUATRE gates avant de verser la zone d'une ability. Les trois premiers sont
portes depuis `#433-r4-r2-r1-r1-c` ; le quatrieme -- la marche (g), un appel a
`IdunBattle.Core.Services.TargetingQuery$$GetInvalidCasterReason` -- ne l'etait pas. Est-ce lui qui
annulait `1045 GetEmRuntz` sur `orksRuntherd`, et le porter rend-il la branche INCLUSION de la zone
(`#...-r1-r1-r1-r1`) enfin CONFRONTABLE ?

CE QUE LE DECOMPILE DIT. La cascade CASTER, onze regles, est transcrite verbatim dans
`engine/services/ability_caster_gates.py` (section GATE 4). Sur les 148 masques RE-lus, un seul
porteur du POOL arme une de ces regles d'une facon derivable SANS canal supplementaire : `1045`,
masque `0x8004` (`CasterMatchesDynamicRule | CasterIsPossibleTarget`), dont la regle-delegue
`IdunBattleLogic.Entities.Abilities.Active.Loki.GetEmRuntzAbility$$GetDynamicInvalidCasterReason`
rend **2** quand `GetSpawnTileSelector` est VIDE -- « aucune tuile libre adjacente au Runtherd ET
adjacente a un ennemi ».

⚠ ETAT COURANT, PAS ETAT INTERROGE. `GetAllTilesInAbilityRange(unit, possiblePositions, true)`
balaie des positions CANDIDATES et passe chacune en `casterTiles`, mais le selecteur de spawn part
de `AdjacentTiles(Caster())` et `IdunBattle.Entities.Selectors.CasterSelector$$Select` rend
l'ENTITE caster (`entities+0x08`) -- LU : son corps ne touche QUE ce slot -- dont `SelectTiles`
prend le `GetMainTile`. Le verdict du gate est donc CONSTANT sur tout le balayage. D'ou `caster_pos`
cote port, et d'ou le fait que l'oracle `abilityReason` (qui pose `casterTile =
getUnitMainTile(caster)`) soit exactement le bon juge.

TROIS VOLETS DE MESURE, et ils ne se remplacent pas :

  * `--step live` -- **la ZONE**, sur `1045`/`orksRuntherd`, en DEUX regimes du MEME montage :
      - regime MORD  : `casterReason != 0` -> le natif ne verse RIEN pour `1045`, la zone se reduit
        a l'attaque normale. Le port SANS le 4e gate y ajoute la tuile source (faux positif) ;
      - regime PASSE : `casterReason == 0` -> le natif VERSE la tuile source (branche INCLUSION), et
        le port doit la verser AUSSI. C'est la mesure que `#...-r1-r1-r1-r1` attendait : sans le
        gate, on ne pouvait pas distinguer « le port a tort » de « le port a raison mais le gate
        l'annule ».
      Le regime PASSE s'obtient en laissant l'IA adverse APPROCHER (des `endturn` successifs) : des
      qu'un ennemi est adjacent a une tuile libre voisine du Runtherd, le selecteur devient non vide.

  * `--step cascade` -- **L'ETAGE**, en LARGEUR. Pour CHAQUE unite vivante et CHAQUE ability de son
    kit dont le masque est RE-lu, on confronte le port a l'oracle `abilityReason.casterReason`
    (= `AttackQuery$$GetInvalidCasterReason`, marches a..g). Contrat de fidelite, celui de
    `probe_115` :
        natif == 0  =>  port == 0            STRICT (le port n'invente JAMAIS un refus)
        natif != 0  =>  port == natif, ou 0  (ecart PERMISSIF, compte et nomme)
    C'est le seul volet qui exerce les regles a gisement non nul AUTRES que la delegue.

  * `--step moved` -- **LA 2e REGLE, avec sa CONTRE-EPREUVE**. `CasterHasNotMoved` (bit 4, 13
    porteurs) ne mord que sur un `has_moved` MESURE, et le module le declarait non publie cote
    DECISION. Il l'est : `combatSnapshot.units[].unitFlags` contient `UnitFlag.Moved` (= **0**, lu a
    `enums.tsv`), et c'est exactement ce que `IdunBattle.Entities.UnitExtensions$$DidMove` teste
    (`GetComponent<UnitFlagsComponent>(unit).Has(0)` apres un `Type == Unit`). Le volet DEPLACE le
    porteur, montre que le natif REFUSE la ou le port refuse, puis RETIRE le bit du masque du port
    et montre qu'il ACCEPTE -- sans quoi un gate vert ne prouverait rien.

Le TEST qui garde le port est `tests/engine/test_433_r4_r2_r1_r2_r2_r1_r1_r1_r4_caster_reason_*.py`.
ASCII only.
"""
from __future__ import annotations

import argparse
import dataclasses
import json
import subprocess
import sys
import uuid
from pathlib import Path

import gameconfig as GC                                                  # noqa: E402
import hexgeo                                                            # noqa: E402
from engine.entities.active_ability_type import ActiveAbilityType        # noqa: E402
from engine.runner.abilities import targeting as TGT                     # noqa: E402
from engine.runner.abilities.handler import ABILITY_CLASSES              # noqa: E402
from engine.runner.abilities.targeting import (TARGETING_OPTIONS_UNPORTED,  # noqa: E402
                                               targeting_options_for)
from engine.runner.abilities.targeting_rule import TargetingRule as TR   # noqa: E402
from engine.services import ability_caster_gates as acg                  # noqa: E402
from engine.services import ability_range as AR                          # noqa: E402
from rl_collect_batch import _resolve_session, _rpc                      # noqa: E402

PYDIR = Path(__file__).resolve().parent
ROOT = PYDIR.parents[1]
SEED = "777"

#: Le porteur confrontable de la regle-delegue : `orksRuntherd` / `1045 GetEmRuntz`, masque `0x8004`.
CASTER_VISUAL = "orksRuntherd"
GETEMRUNTZ = 1045

#: Meme montage que `#...-r1-r1-r1` : les fillers OCCUPENT les tuiles de spawn voisines, ce qui rend
#: le movable set SINGLETON -- le seul regime ou la tuile source n'est pas couverte depuis une autre.
BOARD = "MC1_67"
FILLER = "necroWarden"
MEASURE_RANGE = 1

#: Le porteur de `CasterHasNotMoved` du volet `moved` : `bloodDante` / `1177 LightOfSanguinius`,
#: masque `0x102004032` (bit 4 pose). Choisi parce qu'il est au POOL et que son ability n'est pas
#: consommee par le simple fait de bouger.
MOVED_VISUAL = "bloodDante"
MOVED_ABILITY = 1177

#: `UnitFlag.Moved`, LU dans `data/symbols/<build>/frida/enums.tsv` -- et re-confronte au runtime par
#: `combatSnapshot.unitFlagTypes["Moved"]`, qui est la source AUTORITAIRE (le probe REFUSE si les
#: deux divergent : une renumerotation au prochain build ne doit pas passer en silence).
UNIT_FLAG_MOVED = 0

#: Les onze regles de la cascade CASTER, dans l'ORDRE NATIF de
#: `TargetingQuery$$GetInvalidCasterReason` -- l'inventaire les compte par ce nom.
CASTER_RULES = ("CasterHasNotMoved", "CasterCanMove", "CasterHasCompletedOneTurn",
                "AllowNullCasterTile", "CasterHasNoTile", "CasterMatchesDynamicRule",
                "CasterHas1Tiles", "CasterHas3Tiles", "CasterHas7Tiles",
                "CasterHas2TurnsLeft", "CasterIsMachine")


def ability_ids() -> list:
    """Les ids dont les `TargetingOptions` sont RE-lues, par les DEUX sources du foyer."""
    ids = {int(a) for a in ABILITY_CLASSES
           if getattr(ABILITY_CLASSES[a], "TARGETING_OPTIONS", None) is not None}
    ids |= {int(a) for a in TARGETING_OPTIONS_UNPORTED}
    return sorted(ids)


def inventaire() -> dict:
    """Le GISEMENT de chaque regle CASTER sur les masques RE-lus, et le regime de chaque
    regle-delegue. Une regle a ZERO porteur est un mirror STRUCTUREL -- c'est un resultat."""
    aids = ability_ids()
    par_regle = {}
    for n in CASTER_RULES:
        bit = int(getattr(TR, n))
        par_regle[n] = [a for a in aids
                        if int(getattr(targeting_options_for(a), "rules", 0) or 0) & bit]
    dyn = sorted(a for a in aids
                 if int(getattr(targeting_options_for(a), "rules", 0) or 0)
                 & int(TR.CasterMatchesDynamicRule))
    regimes = {}
    for a in dyn:
        regimes.setdefault(acg.dynamic_caster_gate_of(a), []).append(a)
    return {"abilities": len(aids),
            "par_regle": {k: len(v) for k, v in par_regle.items()},
            "porteurs": {k: v for k, v in par_regle.items() if v},
            "dyn_porteurs": dyn,
            "dyn_regimes": {k: sorted(v) for k, v in sorted(regimes.items())},
            "table_couvre_les_porteurs": sorted(acg.DYNAMIC_CASTER_GATE_BY_ABILITY) == dyn}


# ------------------------------------------------------------------------------------------------
# LE VOLET LIVE -- plomberie
# ------------------------------------------------------------------------------------------------

def _r(sid, m, b, t=120):
    return (_rpc(sid, m, [b], timeout=t).get("result") or {})


def _build(board, p_units, a_units):
    state = ROOT / "logs" / "runners" / ("p433r4-%s.json" % uuid.uuid4().hex[:8])
    state.parent.mkdir(parents=True, exist_ok=True)
    argv = [sys.executable, "rl_duel.py", "build", "--seed", SEED, "--board", board,
            "--state-file", str(state), "--p-units", p_units, "--a-units", a_units,
            "--hp-target", "90000", "--hp-player", "90000"]
    p = subprocess.run(argv, cwd=str(PYDIR), capture_output=True, text=True,
                       encoding="utf-8", errors="replace")
    if not state.exists():
        return None, (p.stderr or p.stdout or "")[-1500:]
    return json.loads(state.read_text())["runnerId"], None


def _dispose(sid, rid):
    if rid is None:
        return
    try:
        _r(sid, "disposeRunner", {"runnerId": rid}, 60)
    except Exception:                                                    # pragma: no cover
        pass


def _obs(sid, rid):
    """Les unites VIVANTES et POSEES. La cle d'acteur est `squadId` -- c'est elle que
    `decisionView.units[].id`, `aiMovableTiles.units[].unitId`, `combatSnapshot.units[].entityId`
    et `abilityReason.casterId` partagent (MESURE : `entityId` d'`observeBattle` en differe de 1 et
    `abilityReason` rend `casterReason: null` si on le lui passe)."""
    o = _r(sid, "observeBattle", {"runnerId": rid}, 120)
    return [u for u in (o.get("units") or [])
            if not u.get("isDead") and u.get("col") is not None]


def _threat(sid, rid):
    mov = _r(sid, "aiMovableTiles",
             {"runnerId": rid, "threat": True, "side": "all",
              "overrideRange": MEASURE_RANGE}, 150)
    return {u.get("unitId"): ([(t["col"], t["row"]) for t in (u.get("tiles") or [])],
                              {(t["col"], t["row"]) for t in (u.get("threatTiles") or [])})
            for u in (mov.get("units") or [])}


def _board_maps(sid, rid):
    bg = _r(sid, "boardGraph", {"runnerId": rid}, 90)
    tiles = bg.get("tiles") or []
    pos = {t["id"]: (t["col"], t["row"]) for t in tiles}
    return ({pos[t["id"]]: t.get("elevation") for t in tiles},
            {pos[t["id"]]: bool(t.get("walkable")) for t in tiles},
            {pos[t["id"]]: bool(t.get("isWall")) for t in tiles},
            {pos[t["id"]]: bool(t.get("isInFog")) for t in tiles})


def _dv_rows(sid, rid):
    """`{squadId: ligne decisionView}` (`allAbilities: true`) -- le canal des TROIS PREMIERS gates.
    Les alimenter est ce qui rend le 4e ISOLABLE : si l'ecart persiste alors qu'ils sont nourris, il
    ne vient pas d'eux."""
    dv = _r(sid, "decisionView", {"runnerId": rid, "allAbilities": True, "maxRank": 1}, 180)
    return {u.get("id"): u for u in (dv.get("units") or []) if u.get("id") is not None}


def _moved_map(sid, rid):
    """`{squadId: has_moved}` depuis `combatSnapshot.units[].unitFlags` -- le mirror EXACT de
    `IdunBattle.Entities.UnitExtensions$$DidMove` (`UnitFlagsComponent.Has(UnitFlag.Moved)`).

    `None` en valeur = flags NON mesures pour cette unite (tri-etat). Rend aussi l'id de l'enum tel
    que le jeu le publie, pour REFUSER une renumerotation silencieuse."""
    cs = _r(sid, "combatSnapshot", {"runnerId": rid, "debugOnly": ["unitFlags"]}, 180)
    mid = (cs.get("unitFlagTypes") or {}).get("Moved")
    out = {}
    for u in (cs.get("units") or []):
        f = u.get("unitFlags")
        out[u.get("entityId")] = None if f is None else (mid in f)
    return out, mid


def _substrate(row, units, walk, elev, moved=None):
    """Le `CasterSubstrate` d'une unite d'`observeBattle`, alimente par tout ce qui EST publie."""
    return acg.CasterSubstrate(
        pos=(row["col"], row["row"]), has_tile=True, team=row.get("teamId"),
        has_moved=None if moved is None else moved.get(row.get("squadId")),
        team_by_pos={(u["col"], u["row"]): u.get("teamId") for u in units},
        walkable_by_pos=walk, elev_by_pos=elev, neigh_by_pos=None)


def _hex_to_int(h):
    """`casterReason.hex` -> entier. `None` = l'oracle n'a pas resolu la methode (pas « valide »)."""
    if not h:
        return None
    try:
        return int(str(h), 16)
    except ValueError:
        return None


def _caster_reason(sid, rid, uid, aid):
    """`casterReason` de l'oracle `abilityReason` = `AttackQuery$$GetInvalidCasterReason(caster,
    getUnitMainTile(caster), ability)` -- la cascade COMPLETE (marches a..g), en NOMS de
    `TargetingRule`. C'est le seul canal qui dise QUELLE regle mord."""
    rep = _r(sid, "abilityReason",
             {"runnerId": rid, "casterId": uid, "abilityType": int(aid)}, 90)
    cr = (rep or {}).get("casterReason")
    return (None if cr is None else _hex_to_int(cr.get("hex")),
            None if cr is None else (cr.get("reasons") or []))


def _port_caster_reason(aid, ability_state, sub):
    """La restriction PORTEE de `AttackQuery$$GetInvalidCasterReason`, sur le substrat DECISION.

    DEUX marches sur sept sont derivables : (d) `ActiveAbility.CanCurrentlyBeUsed` -> le litteral
    **1** que le natif rend par `GenericBrokenTargetingRule(1)`, et (g) la cascade des onze regles,
    portee par `invalid_caster_reason`. Les cinq autres (unite nulle, multi-tuiles sans le trait
    0x418, composant/entree absents, `AbilityName == 0`, `IsAlreadyUsedThisTurn`) ne sont pas
    derivables ici -> le port ne refuse pas, ecart PERMISSIF."""
    if acg.can_currently_be_used(ability_state) is False:
        return 1
    return int(acg.invalid_caster_reason(aid, sub) or 0)


class _SansGate4:
    """Le contre-factuel : le port SANS la marche (g). C'est EXACTEMENT ce qu'il faisait avant cette
    tranche -- `invalid_caster_reason` rendait toujours « valide ».

    ⚠ La substitution porte sur `acg.invalid_caster_reason`, que `caster_gate_reason` appelle par
    son nom de module : la muter est donc EFFECTIF. `_mordu` le VERIFIE, parce que sur une
    contre-epreuve le vert est le resultat suspect."""

    def __enter__(self):
        self._f = acg.invalid_caster_reason
        acg.invalid_caster_reason = lambda ability_id, caster=None: 0
        AR._REACH_CACHE.clear()
        return self

    def __exit__(self, *_exc):
        acg.invalid_caster_reason = self._f
        AR._REACH_CACHE.clear()
        return False


class _SansRegle:
    """Le contre-factuel de la CONTRE-EPREUVE : la meme cascade, moins UN bit du masque.

    Retirer le bit est plus fidele que court-circuiter la fonction : on demande « et si le natif ne
    l'armait pas ? », donc le reste de la cascade continue de s'appliquer. La substitution porte sur
    `engine.runner.abilities.targeting.targeting_options_for`, que `invalid_caster_reason` importe
    a CHAQUE appel (import tardif) -- muter le module est donc effectif."""

    def __init__(self, bit):
        self.bit = int(bit)

    def __enter__(self):
        self._f = TGT.targeting_options_for
        bit, orig = self.bit, self._f

        def sans(aid):
            o = orig(aid)
            return None if o is None else dataclasses.replace(o, rules=int(o.rules) & ~bit)
        TGT.targeting_options_for = sans
        AR._REACH_CACHE.clear()
        return self

    def __exit__(self, *_exc):
        TGT.targeting_options_for = self._f
        AR._REACH_CACHE.clear()
        return False


def _mordu(caster_sub) -> bool:
    """La mutation de `_SansGate4` CHANGE-t-elle la reponse du gate sur `1045` ? Sans ce controle,
    un `EXACT` des deux cotes se lirait comme « le gate ne sert a rien » alors qu'il pourrait ne
    pas s'appliquer du tout."""
    avec = acg.invalid_caster_reason(GETEMRUNTZ, caster_sub)
    with _SansGate4():
        sans = acg.invalid_caster_reason(GETEMRUNTZ, caster_sub)
    return avec != sans


def _port_zone(move_tiles, all_tiles, visual, elev, walk, wall, fog, caster_pos,
               caster_team=None, team_by_pos=None, ability_ids=None,
               ability_state=None, normal_attack_id=None):
    """Le port, evalue en UNION sur le MOVABLE SET -- le meme `possiblePositions` que le natif.

    `caster_pos` est passe EXPLICITEMENT : dans ce regime la position balayee n'est pas la tuile
    courante, et le 4e gate lit la COURANTE (cf. l'en-tete)."""
    AR._REACH_CACHE.clear()
    out = set()
    for T in all_tiles:
        for X in move_tiles:
            if AR.is_tile_in_range_of_any_ability(X, T, visual, ability_ids=ability_ids,
                                                  elev_by_pos=elev, ability_state=ability_state,
                                                  normal_attack_id=normal_attack_id,
                                                  is_wall_by_pos=wall, walkable_by_pos=walk,
                                                  is_in_fog_by_pos=fog, caster_pos=caster_pos,
                                                  caster_team=caster_team,
                                                  team_by_pos=team_by_pos):
                out.add(T)
                break
    return out


# ------------------------------------------------------------------------------------------------
# VOLET 1 -- LA ZONE (1045, deux regimes)
# ------------------------------------------------------------------------------------------------

def _pas_vers_ennemi(sid, rid, uid, pos, ennemis, move):
    """UN pas du caster vers l'ennemi le plus proche. Rend la destination, ou `None`."""
    cand = [t for t in move if tuple(t) != tuple(pos)]
    if not cand or not ennemis:
        return None
    dest = min(cand, key=lambda t: (min(hexgeo.distance(tuple(t), e) for e in ennemis), tuple(t)))
    rep = _r(sid, "applyAction", {"runnerId": rid, "action": {
        "kind": "move", "unitId": uid, "to": {"col": dest[0], "row": dest[1]}}}, 60)
    return {"to": list(dest), "ok": rep.get("ok"), "err": rep.get("error")}


def _rapproche(sid, rid, cible_d, budget) -> dict:
    """APPROCHE SILENCIEUSE -- rapproche le caster sans rien mesurer, jusqu'a `cible_d`.

    MESURE qui l'impose : sur `MC1_67`, `endturn` seul ne fait PAS avancer l'adversaire (les deux
    `necroWarden` restent a (6,7)/(6,8) sur 10 tours) et le caster part a **d = 10**. Le gate ne
    s'ouvre qu'a `d <= 2` (il faut une tuile LIBRE adjacente au caster ET adjacente a un ennemi),
    donc sans cette phase le regime PASSE n'est jamais atteint -- pas parce qu'il n'existe pas, mais
    parce que la GEOMETRIE DE SPAWN l'eloigne. On DEPLACE, on n'accuse pas la geometrie."""
    trace = []
    for _ in range(int(budget)):
        units = _obs(sid, rid)
        me = next((u for u in units if u.get("visualId") == CASTER_VISUAL), None)
        if me is None:
            return {"pas": trace, "arret": "caster absent"}
        pos = (me["col"], me["row"])
        ennemis = [(u["col"], u["row"]) for u in units if u.get("teamId") != me.get("teamId")]
        d = min([hexgeo.distance(pos, e) for e in ennemis] or [-1])
        if d >= 0 and d <= int(cible_d):
            return {"pas": trace, "arret": "d=%d" % d, "pos": list(pos)}
        move = (_threat(sid, rid).get(me["squadId"]) or ([], set()))[0]
        step = _pas_vers_ennemi(sid, rid, me["squadId"], pos, ennemis, move)
        trace.append({"d": d, "pos": list(pos), "step": step})
        _r(sid, "applyAction", {"runnerId": rid, "action": {"kind": "endturn"}}, 60)
    return {"pas": trace, "arret": "budget epuise"}


def live(sid, board=None, fillers=3, tours=8, approche=True, approche_d=4,
         approche_budget=40) -> dict:
    """`approche` -- le caster AVANCE d'une tuile vers l'ennemi le plus proche a chaque tour.

    C'est ce qui produit le regime PASSE : le gate ne s'ouvre que lorsqu'une tuile LIBRE adjacente
    au Runtherd est AUSSI adjacente a un ennemi, et attendre que l'IA adverse vienne ne le donne pas
    (MESURE : 8 tours d'`endturn` seul sur `MC1_67`, les deux `necroWarden` adverses restent hors de
    portee, MORD=4 PASSE=0). Bouger le caster est licite ici : le masque de `1045` est `0x8004`, il
    ne porte PAS `CasterHasNotMoved` -- le deplacement n'arme donc aucune autre regle de la
    cascade."""
    rid, err = _build(board or BOARD,
                      ",".join([CASTER_VISUAL] + [FILLER] * int(fillers)),
                      "%s,%s" % (FILLER, FILLER))
    if rid is None:
        return {"error": "build KO -- %s" % err}
    try:
        out = {"board": board or BOARD, "runner": rid, "tours": []}
        elev, walk, wall, fog = _board_maps(sid, rid)
        allp = sorted(elev)
        if approche:
            out["approche_silencieuse"] = _rapproche(sid, rid, approche_d, approche_budget)
        for it in range(int(tours)):
            units = _obs(sid, rid)
            me = next((u for u in units if u.get("visualId") == CASTER_VISUAL), None)
            if me is None:
                out["tours"].append({"iter": it, "error": "caster absent"})
                break
            uid, pos = me["squadId"], (me["col"], me["row"])
            ennemis = [(u["col"], u["row"]) for u in units
                       if u.get("teamId") != me.get("teamId")]
            moved, _ = _moved_map(sid, rid)
            sub = _substrate(me, units, walk, elev, moved)
            th = _threat(sid, rid)
            move, natif = th.get(uid) or ([], set())
            natif &= set(allp)
            rows = _dv_rows(sid, rid)
            st = acg.ability_state_map(rows.get(uid))
            na_id = acg.normal_attack_id(rows.get(uid))
            nat, noms = _caster_reason(sid, rid, uid, GETEMRUNTZ)
            ligne = {
                "iter": it, "pos": list(pos), "n_move": len(move), "move": sorted(move),
                "natif_reason": nat, "natif_noms": noms,
                "port_reason": _port_caster_reason(GETEMRUNTZ, st.get(GETEMRUNTZ), sub),
                "gate_port": acg.invalid_caster_reason(GETEMRUNTZ, sub),
                "gate_port_nom": acg.caster_gate_reason(GETEMRUNTZ, st.get(GETEMRUNTZ), sub),
                "mutation_mord": _mordu(sub),
                "n_natif": len(natif),
                "ennemis": sorted(ennemis),
                "d_min_ennemi": min([hexgeo.distance(pos, e) for e in ennemis] or [-1]),
            }
            if move:
                apres = _port_zone(move, allp, CASTER_VISUAL, elev, walk, wall, fog, pos,
                                   caster_team=me.get("teamId"),
                                   team_by_pos=sub.team_by_pos,
                                   ability_state=st, normal_attack_id=na_id)
                with _SansGate4():
                    avant = _port_zone(move, allp, CASTER_VISUAL, elev, walk, wall, fog, pos,
                                       caster_team=me.get("teamId"),
                                       team_by_pos=sub.team_by_pos,
                                       ability_state=st, normal_attack_id=na_id)
                normale = _port_zone(move, allp, CASTER_VISUAL, elev, walk, wall, fog, pos,
                                     caster_team=me.get("teamId"),
                                     team_by_pos=sub.team_by_pos,
                                     ability_ids=[], ability_state=st, normal_attack_id=na_id)
                ligne.update({
                    "n_normale_seule": len(normale),
                    "n_avant": len(avant), "n_apres": len(apres),
                    "fp_avant": sorted(avant - natif), "fn_avant": sorted(natif - avant),
                    "fp_apres": sorted(apres - natif), "fn_apres": sorted(natif - apres),
                    # ATTRIBUTION -- l'ecart residuel du terme d'ATTAQUE NORMALE, MESURE et non
                    # suppose : il preexiste a cette tranche (LoS/elevation/walkability du modele
                    # de zone) et n'est pas imputable au 4e gate. Le verdict le compte a part.
                    "fp_normale": sorted(normale - natif), "fn_normale": sorted(natif - normale),
                    "retire_par_le_gate": sorted(avant - apres),
                    "source_dans_natif": sorted(t for t in move if t in natif),
                })
            out["tours"].append(ligne)
            if approche and move:
                ligne["approche"] = _pas_vers_ennemi(sid, rid, uid, pos, ennemis, move)
            _r(sid, "applyAction", {"runnerId": rid, "action": {"kind": "endturn"}}, 60)
        return out
    finally:
        _dispose(sid, rid)


def _verdict_live(res) -> int:
    """DEUX regimes exiges, et le port EXACT dans les deux. Un seul regime ne prouverait rien :
    « mord » seul ne dit pas que la branche INCLUSION est juste, « passe » seul ne dit pas que le
    gate existe.

    L'ecart de ZONE est VENTILE, pas agrege : `fp_normale` est le residu du terme d'ATTAQUE NORMALE
    (LoS/elevation/walkability), PREEXISTANT et hors de cette tranche ; ce qui est imputable au 4e
    gate est `fp_apres \\ fp_normale` (faux positif que le gate aurait du retirer et n'a pas retire)
    et tout `fn_apres` (tuile du natif que le gate a retiree A TORT). Confondre les deux ferait
    accuser cette tranche d'un ecart qu'elle n'a pas cree -- ou l'absoudre d'un qu'elle a cree."""
    mord = passe = efficace = 0
    faux, residu = [], 0
    for d in (res.get("tours") or []):
        # `n_move == 0` = aucune position candidate : le natif ne verse rien de comparable.
        if d.get("error") or not d.get("n_move") or "n_apres" not in d:
            continue
        nat = d.get("natif_reason")
        if nat is None:
            faux.append(("oracle", d["iter"], "casterReason non resolu"))
            continue
        if int(nat) != int(d.get("port_reason") or 0):
            faux.append(("etage", d["iter"], hex(int(nat)), d.get("port_reason")))
        fp_impute = [t for t in d["fp_apres"] if t not in (d.get("fp_normale") or [])]
        residu += len(d["fp_apres"]) - len(fp_impute)
        if fp_impute or d["fn_apres"]:
            faux.append(("zone", d["iter"], fp_impute, d["fn_apres"]))
        # Le gate a-t-il CHANGE la zone, et n'a-t-il retire QUE des faux positifs ? Sans au moins
        # une occurrence, il serait decoratif SUR LA ZONE dans la fenetre mesuree.
        retire = d.get("retire_par_le_gate") or []
        if retire:
            efficace += 1
            garde = [t for t in retire if t in (d.get("fp_avant") or [])]
            if len(garde) != len(retire):
                faux.append(("gate-retire-du-vrai", d["iter"],
                             [t for t in retire if t not in garde]))
        if int(nat):
            mord += 1
        else:
            passe += 1
            if not d["source_dans_natif"]:
                faux.append(("inclusion", d["iter"], "gate PASSE mais le natif "
                             "ne verse pas la tuile source"))
    print("regimes mesures : MORD=%d  PASSE=%d   tours ou le gate CHANGE la zone : %d"
          "   (residu ZONE preexistant, non impute : %d tuiles)"
          % (mord, passe, efficace, residu))
    for f in faux:
        print("  DESACCORD %s" % (f,))
    if not mord or not passe:
        print("VERDICT live: INCOMPLET -- il faut les DEUX regimes (augmenter --tours)")
        return 1
    if not efficace:
        print("VERDICT live: INCOMPLET -- le gate n'a change AUCUNE zone dans la fenetre "
              "(partir du spawn : --approche-d 10)")
        return 1
    if faux:
        print("VERDICT live: ECART")
        return 1
    print("VERDICT live: EXACT dans les deux regimes")
    return 0


# ------------------------------------------------------------------------------------------------
# VOLET 2 -- L'ETAGE, EN LARGEUR (toutes les unites x toutes leurs abilities)
# ------------------------------------------------------------------------------------------------

def _kit_ability_ids(visual):
    lus = set(ability_ids())
    out = []
    for a in (GC.unit_abilities(visual or "").get("active") or []):
        if a.get("id") is not None and int(a["id"]) in lus:
            out.append(int(a["id"]))
    return sorted(set(out))


def cascade(sid, board, rosters, tours=3) -> dict:
    """Confronte `_port_caster_reason` a `abilityReason.casterReason` sur TOUTES les paires
    (unite, ability a masque RE-lu) d'un runner, a chaque tour."""
    out = {"board": board, "rosters": rosters, "paires": [], "runner": None}
    p_units, a_units = rosters
    rid, err = _build(board, p_units, a_units)
    if rid is None:
        out["error"] = "build KO -- %s" % err
        return out
    out["runner"] = rid
    try:
        elev, walk, _wall, _fog = _board_maps(sid, rid)
        for it in range(int(tours)):
            units = _obs(sid, rid)
            moved, mid = _moved_map(sid, rid)
            if mid is not None and int(mid) != UNIT_FLAG_MOVED:
                out["error"] = ("UnitFlag.Moved renumerote : enums.tsv=%d live=%s"
                                % (UNIT_FLAG_MOVED, mid))
                return out
            rows = _dv_rows(sid, rid)
            for u in units:
                uid, vis = u.get("squadId"), u.get("visualId")
                sub = _substrate(u, units, walk, elev, moved)
                st = acg.ability_state_map(rows.get(uid))
                for aid in _kit_ability_ids(vis):
                    nat, noms = _caster_reason(sid, rid, uid, aid)
                    out["paires"].append({
                        "iter": it, "unit": vis, "uid": uid, "ability": aid,
                        "rules": "0x%x" % int(getattr(targeting_options_for(aid), "rules", 0) or 0),
                        "natif": nat, "natif_noms": noms,
                        "port": _port_caster_reason(aid, st.get(aid), sub),
                        "moved": sub.has_moved,
                    })
            _r(sid, "applyAction", {"runnerId": rid, "action": {"kind": "endturn"}}, 60)
        return out
    finally:
        _dispose(sid, rid)


def _verdict_cascade(res) -> int:
    """Contrat de `probe_115` : le port n'invente JAMAIS un refus ; quand il en pose un, il pose le
    MEME que le natif ; sinon c'est un ecart PERMISSIF, compte et nomme."""
    if res.get("error"):
        print("VERDICT cascade: %s" % res["error"])
        return 1
    inv, exact, permissif = [], 0, {}
    n = 0
    for d in (res.get("paires") or []):
        nat, port = d.get("natif"), int(d.get("port") or 0)
        if nat is None:
            continue
        n += 1
        nat = int(nat)
        if nat == 0:
            if port != 0:
                inv.append(d)
            else:
                exact += 1
        elif port == nat:
            exact += 1
        elif port == 0:
            k = ",".join(d.get("natif_noms") or []) or hex(nat)
            permissif[k] = permissif.get(k, 0) + 1
        else:
            inv.append(d)
    print("paires confrontees : %d   accord EXACT : %d   ecart PERMISSIF : %d"
          % (n, exact, sum(permissif.values())))
    for k, v in sorted(permissif.items(), key=lambda kv: -kv[1]):
        print("   permissif %-40s x%d" % (k, v))
    for d in inv[:20]:
        print("   REFUS INVENTE/FAUX %s" % ({k: d[k] for k in
                                             ("unit", "ability", "natif", "natif_noms", "port")},))
    if inv:
        print("VERDICT cascade: ECART -- %d refus inventes ou faux" % len(inv))
        return 1
    if not n:
        print("VERDICT cascade: INCOMPLET -- aucune paire confrontee")
        return 1
    print("VERDICT cascade: aucun refus invente, aucun refus FAUX")
    return 0


# ------------------------------------------------------------------------------------------------
# VOLET 3 -- LA 2e REGLE : `CasterHasNotMoved`, avec sa CONTRE-EPREUVE
# ------------------------------------------------------------------------------------------------

def moved(sid, board=None) -> dict:
    board = board or BOARD
    rid, err = _build(board, "%s,%s" % (MOVED_VISUAL, FILLER), "%s,%s" % (FILLER, FILLER))
    if rid is None:
        return {"error": "build KO -- %s" % err}
    try:
        out = {"board": board, "runner": rid, "ability": MOVED_ABILITY,
               "rules": "0x%x" % int(getattr(targeting_options_for(MOVED_ABILITY),
                                             "rules", 0) or 0), "phases": []}
        elev, walk, _w, _f = _board_maps(sid, rid)

        def mesure(tag):
            units = _obs(sid, rid)
            me = next((u for u in units if u.get("visualId") == MOVED_VISUAL), None)
            if me is None:
                return {"phase": tag, "error": "caster absent"}, None, None
            uid = me["squadId"]
            mv, mid = _moved_map(sid, rid)
            sub = _substrate(me, units, walk, elev, mv)
            st = acg.ability_state_map(_dv_rows(sid, rid).get(uid))
            nat, noms = _caster_reason(sid, rid, uid, MOVED_ABILITY)
            with _SansRegle(TR.CasterHasNotMoved):
                sans = int(acg.invalid_caster_reason(MOVED_ABILITY, sub) or 0)
            return ({"phase": tag, "pos": [me["col"], me["row"]], "uid": uid,
                     "flag_moved_id": mid, "has_moved": sub.has_moved,
                     "natif": nat, "natif_noms": noms,
                     "port": _port_caster_reason(MOVED_ABILITY, st.get(MOVED_ABILITY), sub),
                     "port_sans_la_regle": sans}, me, uid)

        ligne, me, uid = mesure("avant")
        out["phases"].append(ligne)
        if me is None:
            return out
        # DEPLACER -- c'est le geste qui arme la regle. `aiMovableTiles` sans `threat` rend les
        # tuiles LEGALES ; on en prend une DIFFERENTE de la courante.
        for _ in range(4):
            th = _threat(sid, rid)
            tiles = [t for t in (th.get(uid) or ([], set()))[0]
                     if tuple(t) != (me["col"], me["row"])]
            if tiles:
                dest = sorted(tiles)[0]
                rep = _r(sid, "applyAction", {"runnerId": rid, "action": {
                    "kind": "move", "unitId": uid, "to": {"col": dest[0], "row": dest[1]}}}, 60)
                out["move"] = {"to": list(dest), "ok": rep.get("ok"), "err": rep.get("error")}
                break
            _r(sid, "applyAction", {"runnerId": rid, "action": {"kind": "endturn"}}, 60)
        ligne, _me2, _u2 = mesure("apres")
        out["phases"].append(ligne)
        return out
    finally:
        _dispose(sid, rid)


def _verdict_moved(res) -> int:
    if res.get("error"):
        print("VERDICT moved: %s" % res["error"])
        return 1
    ph = {d.get("phase"): d for d in (res.get("phases") or [])}
    av, ap = ph.get("avant"), ph.get("apres")
    if not av or not ap or av.get("error") or ap.get("error"):
        print("VERDICT moved: INCOMPLET -- phases manquantes")
        return 1
    for d in (av, ap):
        print("  %-6s pos=%s has_moved=%s natif=%s %s port=%s port_sans_la_regle=%s"
              % (d["phase"], d["pos"], d["has_moved"],
                 None if d["natif"] is None else hex(int(d["natif"])),
                 d["natif_noms"], d["port"], d["port_sans_la_regle"]))
    bit = int(TR.CasterHasNotMoved)
    ok = True
    if ap.get("has_moved") is not True:
        print("  MONTAGE KO : le caster n'a pas bouge (has_moved=%s)" % ap.get("has_moved"))
        ok = False
    if ap.get("natif") is None or int(ap["natif"]) != bit:
        print("  le NATIF ne refuse pas sur CasterHasNotMoved apres le move (natif=%s)"
              % ap.get("natif"))
        ok = False
    if int(ap.get("port") or 0) != bit:
        print("  le PORT ne refuse pas la ou le natif refuse (port=%s)" % ap.get("port"))
        ok = False
    if int(ap.get("port_sans_la_regle") or 0) != 0:
        print("  CONTRE-EPREUVE MUETTE : le port refuse encore sans la regle (%s)"
              % ap.get("port_sans_la_regle"))
        ok = False
    if int(av.get("natif") or 0) != int(av.get("port") or 0):
        print("  desaccord AVANT le move : natif=%s port=%s"
              % (av.get("natif"), av.get("port")))
        ok = False
    print("VERDICT moved: %s" % ("le natif REFUSE, le port REFUSE, et sans la regle il ACCEPTE"
                                 if ok else "ECART"))
    return 0 if ok else 1


# ------------------------------------------------------------------------------------------------

def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--step", default="all",
                    choices=("all", "inventaire", "live", "cascade", "moved"))
    ap.add_argument("--board", default=None)
    ap.add_argument("--fillers", type=int, default=3)
    ap.add_argument("--tours", type=int, default=8)
    ap.add_argument("--sans-approche", action="store_true",
                    help="ne fait PAS avancer le caster (regime MORD seul -- cf. `live`)")
    ap.add_argument("--approche-d", type=int, default=4,
                    help="distance a laquelle l'approche SILENCIEUSE s'arrete")
    ap.add_argument("--approche-budget", type=int, default=40)
    ap.add_argument("--p-units", default="orksWarboss,bloodDante,astraOrdnance,bloodIntercessor")
    ap.add_argument("--a-units", default="orksNob,templSwordBrother,bloodMephiston")
    args = ap.parse_args()
    rc = 0
    if args.step in ("all", "inventaire"):
        inv = inventaire()
        print("abilities aux masques RE-lus : %d" % inv["abilities"])
        for k, n in sorted(inv["par_regle"].items(), key=lambda kv: -kv[1]):
            print("  %-28s %3d porteur(s)%s" % (k, n, "" if n else "   [mirror STRUCTUREL]"))
        print("regle-delegue CASTER -- regimes :")
        for k, v in inv["dyn_regimes"].items():
            print("  %-16s %s" % (k, v))
        print("la table couvre exactement les porteurs : %s"
              % inv["table_couvre_les_porteurs"])
        if not inv["table_couvre_les_porteurs"]:
            rc = 1
    sid = None
    if args.step in ("all", "live", "cascade", "moved"):
        sid = _resolve_session()
    if args.step in ("all", "live"):
        res = live(sid, args.board, args.fillers, args.tours,
                   approche=not args.sans_approche, approche_d=args.approche_d,
                   approche_budget=args.approche_budget)
        print(json.dumps(res, indent=2, sort_keys=True, default=str))
        rc = max(rc, 1 if res.get("error") else _verdict_live(res))
    if args.step in ("all", "cascade"):
        res = cascade(sid, args.board or BOARD, (args.p_units, args.a_units))
        print(json.dumps(res, indent=2, sort_keys=True, default=str))
        rc = max(rc, _verdict_cascade(res))
    if args.step in ("all", "moved"):
        res = moved(sid, args.board)
        print(json.dumps(res, indent=2, sort_keys=True, default=str))
        rc = max(rc, _verdict_moved(res))
    return rc


if __name__ == "__main__":
    sys.exit(main())
