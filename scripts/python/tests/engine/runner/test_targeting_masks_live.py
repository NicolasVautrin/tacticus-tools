"""#115 -- GARDE des `TARGETING_OPTIONS` des actives DarkAngels / Aeldari / WorldEaters.

`engine/runner/abilities/targeting.py` n'arme le gate de cible QUE si l'ability porte un
`TARGETING_OPTIONS` (`options = getattr(ability, "TARGETING_OPTIONS", None)` ; `None` -> retour 0
IMMEDIAT, aucun gate). Une ability entree au registre sans son masque fait donc accepter offline des
casts que `IdunBattle.Operations.ActiveAbilityOperation$$IsInvalidTarget` REFUSE -- degradation
PERMISSIVE, donc muette en self-play. Ce fichier GARDE les 10 masques poses sur les trois modules de
faction (`darkangels.py`, `aeldari.py`, `worldeaters.py`).

ORACLE = le LIVE : `abilityReason(casterId, abilityType, targetId)` rend le masque `TargetingRule`
NATIF (`targetReason.hex` + noms de flags) via
`IdunBattle.Core.Services.AttackQuery$$GetInvalidTargetReason`.

CONTRAT DE FIDELITE (identique a `test_ability_target_gate_live.py`) :

    natif == 0   =>  port == 0        STRICT (le port n'invente JAMAIS un refus)
    natif != 0   =>  port == natif    (regle PORTEE)
                 ou  port == 0        (regle NON PORTEE -> permissif, cf. targeting.py)
    jamais       :   port != 0 et port != natif

HORS PERIMETRE DU CONTRAT -- les raisons de DISPONIBILITE de l'ability. Le decompile de
`AttackQuery$$GetInvalidTargetReason` (celui qu'appelle le RPC) montre DEUX sorties EN AMONT de la
cascade `TargetingQuery` :

    ability = ActiveAbilityComponent.GetOrNull(caster, abilityType)
    if (ability == null || !ability.CanCurrentlyBeUsed || ability+0x44 == 0)  -> broken(0x1)
    if (IsDamagedMachine(caster) && !IsMachinePrimaryAbilityType(...))        -> broken(0x1)
    if (AttackQuery.IsAlreadyUsedThisTurn(...))                               -> broken(0x40000000000000)
    sinon -> ability.GetInvalidTargetReason(...) = LE filtre des TargetingOptions

`0x1` (`ValidRequest`) = cooldown / munitions epuisees / ability desactivee ; `0x40000000000000`
(`AlreadyUseThisTurn`) = deja utilisee ce tour. Ni l'un ni l'autre n'est un `TargetingRule` de
CIBLE : `is_invalid_target` porte le maillon SOUS cette porte (le port ne modelise ni cooldown ni
munitions). Ces raisons sont donc exclues du contrat, EXPLICITEMENT et par leur code.

PORTEURS (tous confrontables) : 5 HERO DarkAngels + la MACHINE OF WAR `darkaStormSpeeder` (absente
du catalogue du seed BC -> injectee par `catalog_inject.py`, cf. runner.md 1bis), 2 HERO Aeldari,
1 HERO WorldEaters.

ASCII only. Le harnais indisponible = ECHEC (conftest), jamais un skip vert.
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

import oracle_targeting as O
from engine.entities.pathfinding.board import Board
from engine.runner.abilities.handler import ABILITY_CLASSES
from engine.runner.abilities.targeting import is_invalid_target
from engine.runner.abilities.targeting_rule import TargetingRule as TR
from engine.runner.snapshot import load_state

PYDIR = Path(__file__).resolve().parents[3]            # scripts/python

BOARD = "MC1_67"                                       # arene pvp, MoW-capable (slot MachineOfWar)
FOES = "orksWarboss,orksNob,tyranWingedPrime,ultraInceptorSgt,eldarRanger"
DA_UNITS = "darkaTerminator,darkaHellblaster,darkaAzrael,darkaAsmodai,darkaCompanion"
EA_UNITS = "eldarFarseer,eldarMauganRa,worldJakhal,worldKharn,eldarAutarch"
STORM_SPEEDER = "darkaStormSpeeder"
TOURS_DE_CHAUFFE = 6                                    # purge les `initialCooldownTurns` du tour 1
MOW_AMMO = 5                                           # cf. masks_da : sans munitions, 1213 = 0x1

# Raisons de DISPONIBILITE rendues EN AMONT du filtre de cible (cf. l'en-tete) -> hors contrat.
REQUEST_LEVEL_REASONS = frozenset({int(TR.ValidRequest), int(TR.AlreadyUseThisTurn)})

# (abilityType, visualId du porteur, masque LU au `<X>Ability$$.ctor`, regle PORTEE attendue).
# La 4e colonne est le coeur du test : `None` = le masque n'arme AUCUNE regle portee (masque pose
# pour ce qu'il est, aucun refus offline) ; sinon c'est le `TargetingRule` que le port DOIT opposer
# a au moins une cible que le natif refuse pour EXACTEMENT cette raison.
DA_CASES = [
    (1150, "darkaTerminator", 0x4002, TR.TargetIsEnemy),        # PlasmaCannon
    (1103, "darkaHellblaster", 0x4002, TR.TargetIsEnemy),       # Supercharge
    (1140, "darkaAsmodai", 0x6004000, TR.TargetIsEnemy),        # ExemplarOfHate
    (1214, STORM_SPEEDER, 0x200240000400, TR.TargetIsFriendly), # Hailstrike (cible ALLIEE)
    # #249 -- ces deux-la ont CHANGE DE COLONNE : `TargetTileHasEnemyUnit` (bit 19) est desormais
    # PORTEE, donc leur masque arme un refus. Le refus attendu tombe sur toute cible qui n'est pas un
    # ENNEMI attaquable pose sur la tuile visee -- a commencer par un ALLIE du caster, et pour 1092
    # par le CASTER LUI-MEME (distance 0, donc jamais filtre par la portee en amont).
    (1092, "darkaAzrael", 0x80040, TR.TargetTileHasEnemyUnit),  # DarkTalonStrike (domaine TILE)
    (1213, STORM_SPEEDER, 0x40080042, TR.TargetTileHasEnemyUnit),  # DeathOnTheWind (TILE + dyn.)
    (1189, "darkaCompanion", 0x80, None),                       # CalibaniteGreatsword (AddCaster)
]
EA_CASES = [
    (1066, "eldarFarseer", 0x4002, TR.TargetIsEnemy),           # Executioner
    (1067, "eldarMauganRa", 0x4002, TR.TargetIsEnemy),          # HarvesterOfSouls
    (1131, "worldJakhal", 0x4000, TR.TargetIsEnemy),            # JakhalStimms
]
ALL_CASES = DA_CASES + EA_CASES


def _casters_by_visual(dec: dict) -> dict:
    """visualId -> id d'ACTEUR. Les MACHINES OF WAR ne sont PAS dans `decisionView.units` : elles
    vivent dans `decisionView.mows`, et la cle d'acteur est `casterId` (entite `Machine` Type=6,
    == `machineId`) -- c'est elle qu'attendent `abilityReason` et
    `applyAction{kind:"ability", casterId}` (cf. `snapshot._machine_rows`)."""
    out = {}
    for u in (dec.get("units") or []):
        out.setdefault(u.get("visualId"), u.get("id"))
    for m in (dec.get("mows") or []):
        if m.get("casterId") is not None:
            out.setdefault(m.get("visualId"), m.get("casterId"))
    return out


def _measure(rpc, rid: int, cases: list) -> dict:
    """Fige l'etat (dec/ob/snap/board), lit l'oracle natif pour chaque (ability, cible vivante) et
    rejoue le gate OFFLINE sur un `State` NEUF par ability. Rend {(at, target_id): row}."""
    dec = rpc("decisionView", {"runnerId": rid, "maxRank": 1, "allAbilities": True}, 90)
    ob = rpc("observeBattle", {"runnerId": rid}, 40)
    snap = rpc("combatSnapshot", {"runnerId": rid}, 60)
    bg = rpc("boardGraph", {"runnerId": rid}, 60)
    if not (isinstance(bg, dict) and bg.get("tiles")):
        pytest.fail("boardGraph indisponible -- rien n'a pu etre confronte", pytrace=False)
    board = Board(bg["tiles"], adjacency="evenq")
    casters = _casters_by_visual(dec)
    alive = [u for u in (dec.get("units") or []) if u.get("alive")]
    rows = {}
    for at, vis, _rules, _expect in cases:
        caster_id = casters.get(vis)
        if caster_id is None:
            pytest.fail(f"porteur {vis} (ability {at}) absent du runner {rid} -- le harnais n'a "
                        f"pas monte la bataille voulue, aucune validation n'a eu lieu "
                        f"(visualIds vus : {sorted(casters)})", pytrace=False)
        state = load_state(dec, ob, snap, board=board)
        klass = ABILITY_CLASSES[at]
        # LE CRAN D'ORACLE (#287-r9), lu UNE fois par ability : `casterReason` ne depend pas de la
        # cible, donc il couvre les N lignes qui suivent. `_advance` a compte des `endturn` sans
        # rien verifier -- et compter n'est pas mesurer : `1150 PlasmaCannon` porte
        # `initialCooldownTurns = 1`, `1143`/`1158` en portent DEUX, et une MACHINE OF WAR sans
        # munitions n'est JAMAIS debloquee par des tours (terme `ability+0x44`, mesure #287-r9 sur
        # `ultraDreadnought`). C'est ce que le compteur ne pouvait pas dire.
        cr = rpc("abilityReason", {"runnerId": rid, "casterId": caster_id,
                                   "abilityType": at}, 60) or {}
        if O.oracle_court_circuite(cr):
            pytest.fail(
                f"ability {at} ({vis}) : `AttackQuery$$GetInvalidTargetReason` refuse EN AMONT de "
                f"la cascade apres {TOURS_DE_CHAUFFE} fins de tour -- `casterReason` = "
                f"TargetingRule.ValidRequest. Tous les `targetReason` vaudraient `1` pour TOUTE "
                f"cible : le masque ne serait PAS confronte, et un vert ici ne mesurerait RIEN. "
                f"Cause lisible : {O.cause_du_court_circuit(cr)}", pytrace=False)
        for tgt in alive:
            r = rpc("abilityReason", {"runnerId": rid, "casterId": caster_id,
                                      "abilityType": at, "targetId": tgt["id"]}, 60) or {}
            tr = r.get("targetReason") or {}
            rows[(at, tgt["id"])] = {
                "ability": at, "caster": caster_id, "target": tgt["id"],
                "target_visual": tgt.get("visualId"),
                "native": int(tr.get("hex") or "0x0", 16),
                "names": list(tr.get("reasons") or []),
                "port": is_invalid_target(state, int(caster_id), int(tgt["id"]), klass()),
            }
    return {"rid": rid, "rows": rows, "alive": [u["id"] for u in alive]}


def _advance(rpc, rid: int, n: int = TOURS_DE_CHAUFFE) -> None:
    """Purge les cooldowns initiaux (`initialCooldownTurns`, ex. PlasmaCannon `cd1`) : tant qu'ils
    tiennent, le natif rend `ValidRequest` pour TOUTE cible et le filtre de cible n'est jamais
    atteint -- l'oracle ne dirait alors rien du masque. Le runner est bati `--no-ai` : un `endturn`
    ne bouge ni ne tue personne, la geometrie reste celle des spawns."""
    for _ in range(n):
        rpc("applyAction", {"runnerId": rid, "action": {"kind": "endturn"}}, 60)


@pytest.fixture(scope="module")
def masks_da(rpc, build_runner, tmp_path_factory):
    """Bataille DarkAngels : les 5 HERO + la MoW `darkaStormSpeeder`. Cette derniere est une des 17
    unites `lineup` absentes du catalogue du seed BC -> `catalog_inject.py` produit un seed BC
    augmente (Units + configs d'ability), cf. runner.md 1bis.

    MUNITIONS (#254) : `DeathOnTheWind` (1213) porte la constante `munitionsCost` = 1, et le seed BC
    capture pose `MachineOfWarAmmo = 0` sur les trois joueurs. Sans munitions l'ability n'est pas
    disponible, donc `AttackQuery$$GetInvalidTargetReason` sort EN AMONT du filtre de cible et rend
    `ValidRequest` (0x1) pour TOUTE cible : le masque n'est jamais confronte. MESURE
    (`probe_254_mow_ammo.py`, meme montage, 6 endturns) --
        ammo 0 -> 1213 : 0x1 sur les 10 cibles
        ammo 5 -> 1213 : 0x80000 `TargetTileHasEnemyUnit` sur les 5 ALLIES,
                                 0x2 `TargetMatchesDynamicRule` sur les 5 ENNEMIS
    Poser les munitions est une extension de HARNAIS (parametre de bataille, comme
    `probe_123_hailstrike_phase2.py`), pas une mecanique : elle rend la condition testee ATTEIGNABLE."""
    seed_bc = tmp_path_factory.mktemp("masks") / "seed-bc-storm.json"
    p = subprocess.run([sys.executable, "catalog_inject.py", "--units", STORM_SPEEDER,
                        "--out", str(seed_bc)], cwd=str(PYDIR), capture_output=True,
                       text=True, encoding="utf-8", errors="replace")
    if not seed_bc.exists():
        pytest.fail(f"catalog_inject KO pour {STORM_SPEEDER} : {(p.stderr or p.stdout)[-400:]}",
                    pytrace=False)
    bc = json.loads(seed_bc.read_text(encoding="utf-8"))
    for pl in ((bc.get("Player") or {}).get("Players") or {}).values():
        if isinstance(pl, dict):
            pl["MachineOfWarAmmo"] = MOW_AMMO
    seed_bc.write_text(json.dumps(bc), encoding="utf-8")
    rid = build_runner("777", extra=["--board", BOARD, "--seed-bc", str(seed_bc),
                                     "--p-units", DA_UNITS, "--p-mow", STORM_SPEEDER,
                                     "--a-units", FOES, "--no-ai"])["rid"]
    _advance(rpc, rid)
    return _measure(rpc, rid, DA_CASES)


@pytest.fixture(scope="module")
def masks_ea(rpc, build_runner):
    """Bataille Aeldari + WorldEaters : `eldarFarseer`, `eldarMauganRa`, `worldJakhal` (+ 2 unites
    de remplissage, qui servent de cibles ALLIEES au volet `TargetIsEnemy`)."""
    rid = build_runner("31337", extra=["--board", BOARD, "--p-units", EA_UNITS,
                                       "--a-units", FOES, "--no-ai"])["rid"]
    _advance(rpc, rid)
    return _measure(rpc, rid, EA_CASES)


@pytest.fixture(scope="module")
def masks_all(masks_da, masks_ea):
    """Les deux batailles vues comme UN jeu de mesures (les cles sont (abilityType, targetId), et
    les deux runners n'ont aucune ability en commun)."""
    rows = dict(masks_da["rows"])
    rows.update(masks_ea["rows"])
    return rows


# ================================================================================================ #
# 1. Le masque POSE est bien celui du ctor natif (offline, sans live)
# ================================================================================================ #

def test_every_mask_matches_the_literal_read_in_the_native_ctor():
    """Transcription du masque, ability par ability. Les valeurs de droite sont LUES au decompile de
    `<X>Ability$$.ctor` (build gqfc5mff6c) : soit le 5e argument de la surcharge 8 arguments de
    `IdunBattle.Core.Services.TargetingOptions$$.ctor` (qui pose `Rules <- param5` tel quel), soit,
    pour les ctors qui COPIENT un preset statique, la constante que
    `IdunBattle.Core.Services.TargetingOptions$$.cctor` ecrit a `<preset>+0x28`.

    C'est CE test qui rougit si un masque est retire ou altere -- il ne depend d'aucun live."""
    missing, wrong = [], []
    for at, _vis, rules, _expect in ALL_CASES:
        opts = getattr(ABILITY_CLASSES[at], "TARGETING_OPTIONS", None)
        if opts is None:
            missing.append(at)
        elif int(opts.rules) != rules:
            wrong.append((at, hex(int(opts.rules)), hex(rules)))
    assert not missing, (
        "TARGETING_OPTIONS ABSENT -- ces abilities entrent dans ABILITY_CLASSES sans masque, donc "
        f"AUCUN gate de cible (degradation permissive muette) : {sorted(missing)}")
    assert not wrong, f"masque different du litteral du ctor natif (at, port, natif) : {wrong}"


# ================================================================================================ #
# 2. Agrement avec l'oracle NATIF, cible par cible
# ================================================================================================ #

def test_port_never_refuses_what_the_native_accepts(masks_all):
    """LA propriete « zero regression » : une regle non portee est permissive, donc poser un masque
    ne peut JAMAIS faire refuser une cible que le natif accepte. C'est le sens dangereux (un refus
    invente casse des casts legaux en silence)."""
    bad = [(r["ability"], r["target"], r["target_visual"], hex(r["port"]))
           for r in masks_all.values() if r["native"] == 0 and r["port"] != 0]
    assert not bad, f"le port refuse des cibles que le natif ACCEPTE (at, uid, visual, port) : {bad}"


def test_port_reason_is_the_native_reason_or_permissive(masks_all):
    """Contrat de fidelite complet : le port rend soit EXACTEMENT la raison native (regle portee),
    soit 0 (regle non portee) -- jamais une AUTRE raison non nulle. Un refus pour la mauvaise raison
    passerait un test purement booleen accepte/refuse.

    Les raisons de DISPONIBILITE (`ValidRequest`, `AlreadyUseThisTurn`) sont exclues : elles sont
    rendues par `AttackQuery$$GetInvalidTargetReason` EN AMONT du filtre de cible (cf. en-tete)."""
    wrong = [(r["ability"], r["target"], r["target_visual"], hex(r["port"]), hex(r["native"]),
              r["names"])
             for r in masks_all.values()
             if r["native"] not in REQUEST_LEVEL_REASONS
             and r["port"] != 0 and r["port"] != r["native"]]
    assert not wrong, (
        "le port refuse pour une raison DIFFERENTE du natif "
        f"(at, uid, visual, port, natif, noms natifs) : {wrong}")


# ================================================================================================ #
# 3. Chaque masque qui ARME une regle portee produit un refus MESURE
# ================================================================================================ #

@pytest.mark.parametrize("at,vis,rules,expect", [c for c in ALL_CASES if c[3] is not None])
def test_armed_mask_reproduces_a_native_refusal(masks_all, at, vis, rules, expect):
    """Le coeur du travail : renseigner l'attribut ne suffit pas, il faut qu'un cast que le NATIF
    refuse soit desormais refuse OFFLINE, pour la MEME raison.

    `TargetIsEnemy` (0x4000) : le natif refuse soi-meme et les allies. `TargetIsFriendly` (0x400,
    Hailstrike) : c'est l'inverse -- le natif refuse les ENNEMIS, et le caster etant une MACHINE, il
    prend la branche `IsMachine(caster)` du bit 10 (`battleQuery.<slot 0x90>`), que le port rabat
    sur le meme predicat d'equipe.

    `TargetTileHasEnemyUnit` (0x80000, #249 -- 1092 DarkTalonStrike et 1213 DeathOnTheWind) : le natif
    refuse toute cible dont la MAIN TILE est vide/steppable OU dont l'occupant n'est pas attaquable
    par le caster, c'est-a-dire le caster lui-meme et ses allies. ⚠ Ce cas n'a PAS ete confronte au
    live lors de son ajout (MAJ de build gqfc5mff6c -> rnca9r7q6c en cours) : c'est CE test qui le
    fera, et son montage de reference est `probe_249_tile_has_enemy_targeting.py`."""
    hits = [r for r in masks_all.values()
            if r["ability"] == at and r["native"] == expect and r["port"] == expect]
    seen = sorted({(hex(r["native"]), tuple(r["names"])) for r in masks_all.values()
                   if r["ability"] == at})
    assert hits, (
        f"ability {at} ({vis}, masque {hex(rules)}) : AUCUN refus natif {hex(expect)} reproduit "
        f"a l'identique par le port -- le masque n'a rien arme. Raisons natives vues : {seen}")


# ================================================================================================ #
# 4. Les masques SANS bit porte : poses, et strictement sans effet
# ================================================================================================ #

@pytest.mark.parametrize("at,vis,rules", [(c[0], c[1], c[2]) for c in ALL_CASES if c[3] is None])
def test_mask_without_ported_bit_arms_no_refusal(masks_all, at, vis, rules):
    """Il ne reste QU'UN cas depuis #249 : CalibaniteGreatsword (`AddCaster` seul, 1189). Son masque ne
    pose AUCUN bit que la cascade offline consomme. Il est la parce que c'est la donnee RE-lue -- et
    il ne doit RIEN refuser PAR UN BIT : c'est la contrepartie honnete du « trou declare ».

    DarkTalonStrike (1092) et DeathOnTheWind (1213) etaient ici jusqu'a #249, au titre de
    `TargetTileHasEnemyUnit` non portee ; ce bit est desormais evalue, ils sont passes au test 3.
    Reste chez 1213 le TROU DECLARE du bit `TargetMatchesDynamicRule` (0x2) : le natif surcharge la
    regle (`DeathOnTheWindAbility$$GetDynamicInvalidTargetReason` = la cible doit avoir deja recu une
    attaque ce tour) et elle N'EST PAS portee (le compteur `UnitComponent.times_attacked_this_turn`
    n'est pas seede par `load_state`), donc le defaut 0 de la base doit tenir -- la porter refuserait
    des cibles que le natif ACCEPTE. C'est le test 2 qui le garde (permissif autorise, jamais un
    refus pour une autre raison).

    EXCEPTION AJOUTEE PAR #241 -- le volet PORTEE. Le titre « aucun bit consomme » ne vaut que pour
    les regles GATEES PAR UN BIT ; la portee, elle, n'en a pas : le natif la teste pour toute ability
    dont `options.Range.UseWholeBoard` est faux, avec la valeur de
    `IdunBattle.Core.Services.TargetingQuery$$GetRange`. CalibaniteGreatsword a un `TargetingRange`
    NON `UseWholeBoard` (`overrideRange` 0) et le natif LA REFUSE effectivement en `TargetIsInRange`
    (MESURE : 9 cibles). Un refus de portee est donc attendu -- mais il reste soumis au contrat de
    fidelite : il doit valoir EXACTEMENT le code natif."""
    range_rules = {int(TR.TargetIsInRange), int(TR.TargetIsAtRange)}
    assert getattr(ABILITY_CLASSES[at], "TARGETING_OPTIONS", None) is not None, (
        f"ability {at} ({vis}) : masque ABSENT alors qu'il a ete lu au ctor ({hex(rules)})")
    rows = [r for r in masks_all.values() if r["ability"] == at and r["port"] != 0]
    by_bit = [(r["target"], r["target_visual"], hex(r["port"]), hex(r["native"]), r["names"])
              for r in rows if r["port"] not in range_rules]
    assert not by_bit, (
        f"ability {at} ({vis}, masque {hex(rules)}) : le port oppose un refus alors qu'AUCUN bit du "
        f"masque n'est consomme par la cascade portee (uid, visual, port, natif, noms) : {by_bit}")
    divergent = [(r["target"], r["target_visual"], hex(r["port"]), hex(r["native"]), r["names"])
                 for r in rows if r["port"] in range_rules and r["port"] != r["native"]]
    assert not divergent, (
        f"ability {at} ({vis}) : refus de PORTEE non concordant avec le natif "
        f"(uid, visual, port, natif, noms) : {divergent}")
