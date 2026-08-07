"""probe_507 -- MESURE de `1091 SlashingDive` (`thousNpc2Screamer` « Screamer », Thousand Sons).

QUESTION BINAIRE, posee AVANT la methode : **la classe native `SlashingDiveAbility`, dont IL2CPP a
FUSIONNE le ctor avec celui de sa soeur, se comporte-t-elle EXACTEMENT comme `1064 SwoopingHawk`
(meme `DiveAttackAbilityBase`) -- ou porte-t-elle une surcharge que l'absence de symbole cachait ?**

C'est la question que le paragraphe « NON-LU » de `abilities/targeting.py` avait laissee ouverte :
`SlashingDiveAbility$$.ctor` n'a AUCUN proprietaire nomme dans les tables (indexees par ADRESSE, et
le corps est identique a celui de `SwoopingHawkAbility$$.ctor`), donc « aucun ctor a lire ». La
reponse OFFLINE est prise au slot de methode de la CLASSE (RPC `resolveMethodPtr`) ; ce probe prend
la reponse COMPORTEMENTALE, qui est independante :

    M_partage  (decompile) : la vague de 3 tuiles, montants DECROISSANTS `dmg[0..2]`, profil `Power`
                             (la CONFIG differe de 1064 : `Piercing`), atterrissage DERRIERE la
                             derniere cible touchee.
    M_surcharge            : n'importe quel ecart -- topologie, montant, profil, atterrissage.

ETAGES MESURES (jamais un scalaire fitte -- chaque etage a son oracle natif) :
  [0] GATE DE CIBLAGE      : le masque `TargetIsEnemy` MORD (allie et self refuses), et l'oracle du
                             refus est le natif lui-meme (`abilityTargets` n'enumere que des
                             ennemis). C'est la donnee posee AVEC l'entree au registre : sans elle,
                             `get_invalid_target_reason` rend 0 immediatement.
  [1] EXECUTION portee     : `diag.ported is True` (sans quoi le cast est un NO-OP SILENCIEUX --
                             l'etat d'ou part cette tranche).
  [2] TOPOLOGIE            : l'ENSEMBLE ORDONNE des cibles frappees, port == natif, lu dans la
                             cascade du cast (`Active_Ability_Type == 1091`).
  [3] DEGAT, TUILE PAR TUILE : `state.rng` CALE sur le MT live (`dumpRng`) -> egalite BIT-EXACTE des
                             montants, RANG PAR RANG. C'est ce qui decompose le percage (profil
                             `Power` -> `PiercingRatio` -> armure) et `dmg_bonus` (les mods
                             ATTAQUANT) au lieu de les absorber dans un total.
  [4] ATTERRISSAGE         : la position FINALE du caster, port == natif. Elle discrimine l'ordre
                             `(source, target)` de `TileBehindTargetFromSourceDirection` ET
                             l'ancrage sur la DERNIERE tuile portant un ennemi.
  [5] REPLI                : meme montage, la tuile d'atterrissage OCCUPEE -> le natif prend « la
                             tuile libre la plus proche ». C'est la branche FAUSSE du
                             `ConditionalSelector`, celle qui porte le `Randomize`.
  [6] LES TROIS FACES SEPAREES : `crit`, `dmg_bonus` et `pierce` ne sont PAS confondus.
                             - `crit`  : la famille ABILITY n'a AUCUN slot `RollCritical`. La mesure
                               est donc « `Attack_DidCrit == 0` sur TOUS les coups », et c'est un
                               OBSERVABLE, pas une simplification.
                             - `pierce` : `DamageProfileType` natif de chaque coup == l'ordinal du
                               profil `Power` lu au gameconfig -- et il SEPARE 1091 de 1064, dont la
                               config dit `Piercing`. Un port qui aurait recopie la constante de la
                               soeur tombe ICI.
                             - `dmg_bonus` : le RATIO `montant_inflige / dmg[i]` doit etre le MEME
                               aux trois rangs (les mods attaquant sont multiplicatifs et communs) ;
                               un rang bloque (`Attack_DidBlock`) est EXCLU du test et signale.
  [7] ANCRE                : une SEULE tuile occupee -> le caster doit atterrir derriere la tuile
                             **1**, pas derriere la 3e. Un port qui prendrait « la derniere tuile de
                             la ligne » au lieu de « la derniere tuile OCCUPEE » passe [4] et tombe
                             ici. C'est le scenario qui a fait mordre #502.

TEMOIN DE NON-DEGENERESCENCE (l'accord en regime degenere ne prouve rien) : le probe exige que les
trois montants natifs soient NON NULS et DEUX A DEUX DIFFERENTS -- c'est ce qui rend une vague
« splash » (meme montant partout) refutable. Un montage ou personne ne prend de degat, ou ou les
trois rangs prennent la meme chose, est declare NON CONCLUANT plutot que vert.

GATE DE CONFRONTABILITE -- 1091 n'a AUCUN porteur lineup : `thousNpc2Screamer` (npc),
`thousSmnScreamer` / `thousSmnScreamerHSE` (summons). On prend le NPC par le CHEMIN DE STATS
EXPLICITE (`case-92` §5bis recours 4) : il porte une table `units.npc[].stats[]` de 45 paliers, donc
`--explicit-stats thousNpc2Screamer:45` l'amene en bataille avec SES stats, SES traits (`Daemon`,
`Flying`, `WeaverOfFate`) et SON arme -- c'est le MIRROR, pas un montage, et il est COMMANDABLE. La
voie SUMMON existe (l'active 1096 `MasterOfTheTutelaries` d'Abraxas `thousInfernalMaster`, DU POOL,
pose l'effet 1197 qui arme la triggered 1173 -> Screamer) mais elle n'OBSERVE que ce que l'IA
choisit : elle ne permet ni de choisir la cible ni d'aligner la ligne. Ni greffe ni injection npc
n'ont donc ete necessaires.

Le placement est FORCE (`--place`/`--a-place`), en COLONNE : sur une grille odd-q, deux tuiles de
meme colonne et de rangees consecutives ont un delta cube CONSTANT `(0,-1,+1)` -- c'est donc une
vraie ligne hex, celle que `TilesBehindInLine` prolonge. Les cibles sont des unites de MELEE
(`orksNob`) : les tireurs portent `Overwatch_AutoAttack`, qui tue le caster a l'atterrissage et rend
l'etage [4] inobservable. « Bloque par la geometrie » n'est pas un resultat : on DEPLACE.

Sortie ASCII stricte (console cp1252). Ecrit sous `logs/`, jamais `data/` (#349).

Usage:
    python probe_507_slashing_dive.py
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import requests

HOST = "http://127.0.0.1:8765"
PYDIR = Path(__file__).resolve().parent
sys.path.insert(0, str(PYDIR))

SLASHING_DIVE = 1091               # ActiveAbilityType.SlashingDive
BOARD = "MC1_67"
#: ⚠ SEED CHOISI PAR MESURE, et la raison est le TEMOIN, pas le confort. Le block est un TIRAGE par
#: coup ; sous `seed 777` le 2e coup de la vague BLOQUE (montant natif 0), et un rang a zero rend
#: irrefutable une vague << splash >> (meme montant partout) -- l'accord en regime degenere ne prouve
#: rien. `--block-target 0,0` ne suffit pas (il met la stat de BASE a zero, les traits/tuiles posent
#: leur bonus par-dessus) et deplacer la ligne non plus (mesure : meme resultat colonne 3 et
#: colonne 0, aux memes montants -- c'est bien le TIRAGE, pas la tuile). On change donc l'etat MT.
#: Sous `31337` les trois rangs passent : `1477 / 1164 / 873`, non nuls et deux a deux distincts.
SEED = "31337"
#: Le seed qui BLOQUE le 2e rang. Il n'est pas ecarte : il est promu en SCENARIO A PART (etage [9]),
#: parce qu'un rang bloque est un OBSERVABLE que le port doit suivre -- montant natif 0 ET aucun PV
#: perdu. Le retirer aurait cache une face au lieu de la mesurer.
SEED_BLOCK = "777"

#: LE PORTEUR. Suffixe `:45` = le palier de `units.npc[thousNpc2Screamer].stats[]` (45 lignes,
#: clamp HAUT) -- il fixe `AbilityLevel = 65`, donc la cellule `dmg` la plus haute, dont les trois
#: montants sont NON NULS et DEUX A DEUX DIFFERENTS (temoin de non-degenerescence).
CASTER_UNIT = "thousNpc2Screamer:45"
CASTER_VISUAL = "thousNpc2Screamer"

#: La LIGNE du montage : une colonne, quatre rangees consecutives. Le caster ouvre la colonne, les
#: trois cibles occupent les rangs 1, 2 et 3 de la vague.
#:
#: ⚠ COLONNE 0, PAS 3 -- et c'est une MESURE, pas un gout. Sur `MC1_67` la tuile `(3,2)` est un
#: `DryBush` (lu dans `data/boards/pvp/MC1_67.json`, `board.Tiles[col].Tile[row]`), qui pose
#: `LightCover` sur son occupant : le rang 2 BLOQUAIT le coup et son montant natif valait 0. Le
#: temoin de non-degenerescence exige TROIS montants non nuls et deux a deux distincts -- sans quoi
#: une vague << splash >> (meme montant partout) resterait irrefutable. `--block-target 0,0` ne
#: suffit PAS : il met la stat de BASE a zero, et `LightCover` est un modificateur POSE PAR LA TUILE
#: par-dessus. On DEPLACE la ligne, on ne rabat pas le regime.
#: La colonne 0 est en `Grass` sur les rangees 0..7, et les trois `DryBush` du plateau -- (3,2),
#: (3,6), (6,5) -- ne la touchent pas.
CASTER_TILE = (0, 0)
WAVE_TILES = ((0, 1), (0, 2), (0, 3))
#: La tuile d'ATTERRISSAGE attendue = un pas au-dela de la derniere cible, dans la meme direction.
LANDING_TILE = (0, 4)
#: Cibles de MELEE : pas d'`Overwatch_AutoAttack`, et ~10000 PV chacune -- personne ne meurt sous la
#: vague (max ~3600), donc les trois montants restent lisibles rang par rang.
WAVE_UNITS = ("orksNob", "orksNob", "orksNob")
#: Temoin du gate ALLIE, pose loin de la ligne pour ne rien perturber.
ALLY_UNIT = "eldarRanger"
ALLY_TILE = (5, 7)
#: Bouchon du scenario REPLI : une unite POSEE sur la tuile d'atterrissage.
PLUG_UNIT = "orksRuntherd"
#: TEMOIN DE SURVIE du scenario LETAL : un ennemi pose LOIN de la ligne, pour que la bataille ne
#: s'achete pas (3 morts sur 3 ennemis = victoire, et l'etat d'apres n'est plus observable).
FAR_UNIT = "orksRuntherd"
FAR_TILE = (6, 8)
#: PV forces des cibles du scenario LETAL. ⚠ `--hp-target` met AUSSI `Armor`/`FixedArmor` a 0 : ce
#: scenario ne mesure donc PAS l'etage armure -- il mesure la LETALITE et, surtout, que l'ancre du
#: deplacement reste la 3e tuile alors que son occupant est MORT (le natif fige `last` AU CAST, cf.
#: `dive_attack_tree`). Le scenario VAGUE, lui, garde l'armure intacte.
LETHAL_HP = 900

#: Ce qui doit changer pour que ce probe puisse changer d'avis (#486-r12). Declare LARGE : la
#: fermeture d'imports d'un cast d'ability traverse tout `engine/**`.
DECLENCHEUR = {
    "chemins": ("scripts/python/engine/**/*.py",
                "scripts/python/*.py",
                "scripts/python/tests/engine/conftest.py",
                "scripts/python/tests/conftest.py",
                "data/seed-bc.json", "data/boards/**"),
    "build": True,
    "toujours": False,
    "raison": "Il confronte le port de 1091 au NATIF via un runner live : il depend du code du "
              "port (la base `DiveAttackAbilityBase` partagee avec 1064 -- arbre DSL + selecteurs "
              "de ligne/tuile-derriere + la feuille d'attaque d'ability + le registre + le masque "
              "de ciblage + la geometrie hex de `battle_query`) ET du build charge (le natif est "
              "l'oracle de la topologie, du degat et de l'atterrissage). Il depend AUSSI du chemin "
              "de stats explicite npc (`catalog_inject`) qui amene son seul porteur en bataille.",
}


def _session() -> int:
    st = requests.get(f"{HOST}/api/admin/status", timeout=20).json()
    return int(st["session"]["id"])


def rpc(sid: int, method: str, body: dict, timeout: int = 90):
    r = requests.post(f"{HOST}/api/scripts/{sid}/rpc",
                      json={"method": method, "args": [body], "timeout": int(timeout * 1000)},
                      timeout=timeout + 5).json()
    return r.get("result", r)


def build(state_path: Path, args: list) -> int:
    state_path.parent.mkdir(parents=True, exist_ok=True)
    proc = subprocess.run([sys.executable, "rl_duel.py", "build", "--state-file", str(state_path)]
                          + args, cwd=str(PYDIR), capture_output=True, text=True,
                          encoding="utf-8", errors="replace")
    if not state_path.exists():
        print((proc.stderr or proc.stdout or "")[-1500:])
        raise SystemExit("build KO")
    return int(json.loads(state_path.read_text())["runnerId"])


def dispose(state_path: Path) -> None:
    subprocess.run([sys.executable, "rl_duel.py", "dispose", "--state-file", str(state_path)],
                   cwd=str(PYDIR), capture_output=True, text=True)


def load(sid, rid):
    from engine.entities.pathfinding.board import Board
    from engine.runner.snapshot import load_state
    bg = rpc(sid, "boardGraph", {"runnerId": rid}, 60)
    board = Board(bg["tiles"], adjacency="evenq")
    dec = rpc(sid, "decisionView", {"runnerId": rid, "maxRank": 1, "allAbilities": True}, 90)
    ob = rpc(sid, "observeBattle", {"runnerId": rid}, 40)
    snap = rpc(sid, "combatSnapshot", {"runnerId": rid}, 60)
    tiles = rpc(sid, "tileMeta", {"runnerId": rid}, 60)
    return load_state(dec, ob, snap, board=board, tiles=tiles), dec, bg


def seed_rng(s):
    """MT offline == MT live : `dumpRng` rend l'etat COMPLET (`mt[624]`, `mti`). Sans ce calage,
    `AttackDamageOperation.execute_ability_attack` SKIP le degat (rend None) -- degradation
    DEFENSIVE documentee, pas un bug : un replay de DEGAT doit caler le rng. Le lire comme un
    « port mort » est la faute que ce calage previent."""
    from engine.runner.prng import IntBasedMersenneTwister
    rng = IntBasedMersenneTwister()
    rng.mt = list(s["mt"])
    rng.mti = s["mti"]
    return rng


def hp_live(sid, rid) -> dict:
    ob = rpc(sid, "observeBattle", {"runnerId": rid}, 40) or {}
    return {int(u["squadId"]): int(u["hp"]) for u in (ob.get("units") or [])}


def pos_live(sid, rid) -> dict:
    """`observeBattle` publie `col`/`row` A PLAT sur chaque unite (PAS sous un objet `position`)."""
    ob = rpc(sid, "observeBattle", {"runnerId": rid}, 40) or {}
    return {int(u["squadId"]): (int(u["col"]), int(u["row"]))
            for u in (ob.get("units") or []) if u.get("col") is not None}


def hp_off(state) -> dict:
    from engine.runner.components import HealthComponent
    return {int(eid): int(e.get_component(HealthComponent).hp)
            for eid, e in state.entities.items()
            if e.get_component(HealthComponent) is not None}


def pos_off(state) -> dict:
    from engine.runner.components import PositionComponent
    return {int(eid): (int(e.get_component(PositionComponent).col),
                       int(e.get_component(PositionComponent).row))
            for eid, e in state.entities.items()
            if e.get_component(PositionComponent) is not None}


def find(dec, visual_id, skip=()):
    for u in (dec.get("units") or []):
        if u.get("visualId") == visual_id and int(u["id"]) not in skip:
            return u
    return None


def native_wave(act0) -> tuple:
    """La cascade du cast -> `([(target, amount, crit, block, profil)], [group_ids])`, dans l'ORDRE
    d'emission.

    FORME DE LA CASCADE, LUE et non supposee : `actions[0].events` est une liste **PLATE** de
    `{kind, group|step, entity, tags}` -- l'arborescence n'est portee que par la suite des
    `kind: "group"` / `kind: "finish"`, et **`tags` est une CHAINE JSON**, pas un objet.

    Le discriminant est `Active_Ability_Type == 1091` : c'est le champ que `AbilityDamageOperation`
    thread sur CHAQUE coup de la vague, et il exclut d'office tout degat d'une autre source
    (contre-attaque, overwatch, DoT) tombant dans la meme cascade."""
    coups, groupes = [], []
    for ev in (act0.get("events") or []):
        if not isinstance(ev, dict):
            continue
        if ev.get("kind") == "group" and ev.get("group") is not None:
            groupes.append(int(ev["group"]))
        raw = ev.get("tags")
        if not raw:
            continue
        try:
            f = json.loads(raw) if isinstance(raw, str) else dict(raw)
        except (TypeError, ValueError):
            continue
        if int(f.get("Active_Ability_Type", -1)) != SLASHING_DIVE or "Target_Id" not in f:
            continue
        coups.append((int(f["Target_Id"]), int(f.get("Amount", 0)),
                      int(f.get("Attack_DidCrit", 0)), int(f.get("Attack_DidBlock", 0)),
                      int(f.get("DamageProfileType", -1))))
    return coups, groupes


def profil_ordinal() -> int:
    """Ordinal `IdunBattle.Entities.Enum.DamageProfileType` du profil de 1091, DERIVE de la table
    de noms du port -- jamais une seconde transcription a la main. Il DOIT differer de celui de
    1064 : c'est le discriminant « la config a bien ete relue par ability »."""
    from engine.runner.abilities.thousandsons import slashing_dive_profile
    from engine.entities.damage_profile_type import PROFILE_NAME_BY_INDEX
    nom = slashing_dive_profile()
    for idx, n in PROFILE_NAME_BY_INDEX.items():
        if n == nom:
            return int(idx)
    return -1


def scenario(sid, state_path: Path, avec_bouchon: bool = False, n_cibles: int = 3,
             letal: bool = False, seed: str | None = None) -> dict:
    """Monte la ligne, joue le MEME cast des deux cotes depuis le MEME etat MT, et rend les deux
    observables cote a cote.

    `avec_bouchon` pose une unite SUR la tuile d'atterrissage -> etage [5].
    `n_cibles` borne le nombre de tuiles OCCUPEES de la ligne -> etage [7].
    `letal` force des PV bas (et un temoin lointain pour que la bataille survive) -> etage [8].

    ⚠ `--block-target 0,0` est pose sur TOUS les scenarios sauf mention : sans lui, le rang 2 tombait
    sur un BLOCK (mesure : `LightCover` + `BeastSlayer_ExtraBlock` sur `orksNob`) et son montant
    natif valait 0 -- le temoin de non-degenerescence exige TROIS montants non nuls et deux a deux
    distincts, sans quoi une vague << splash >> (meme montant partout) resterait irrefutable. Le
    block reste mesure comme observable a part (`live_block`), et le port doit le suivre."""
    from engine.runner.abilities.handler import ABILITY_CLASSES
    from engine.runner.abilities.targeting import get_invalid_target_reason
    from engine.runner.operations.summon_ai import _apply_active_ability

    tuiles = WAVE_TILES[:max(1, int(n_cibles))]
    a_units = list(WAVE_UNITS[:len(tuiles)]) + ([PLUG_UNIT] if avec_bouchon else [])
    if letal:
        a_units = a_units + [FAR_UNIT]
    args = ["--seed", str(seed or SEED), "--board", BOARD,
            "--explicit-stats", CASTER_UNIT,
            "--block-target", "0,0",
            "--p-units", "%s,%s" % (CASTER_UNIT, ALLY_UNIT),
            "--a-units", ",".join(a_units),
            "--place", "%s:%d,%d" % ((CASTER_UNIT,) + CASTER_TILE),
            "--place", "%s:%d,%d" % ((ALLY_UNIT,) + ALLY_TILE)]
    if letal:
        args += ["--hp-target", str(LETHAL_HP)]
    for unit, tile in zip(WAVE_UNITS, tuiles):
        args += ["--a-place", "%s:%d,%d" % ((unit,) + tile)]
    if avec_bouchon:
        args += ["--a-place", "%s:%d,%d" % ((PLUG_UNIT,) + LANDING_TILE)]
    if letal:
        args += ["--a-place", "%s:%d,%d" % ((FAR_UNIT,) + FAR_TILE)]
    rid = build(state_path, args)

    state, dec0, bg = load(sid, rid)
    caster = find(dec0, CASTER_VISUAL)
    ally = find(dec0, ALLY_UNIT)
    if caster is None:
        raise AssertionError("SCENARIO NON MONTE : %s absent du decisionView" % CASTER_VISUAL)
    caster_id = int(caster["id"])
    ally_id = int(ally["id"]) if ally is not None else None

    # Cible = une cible LEGALE DEPUIS LA POSITION COURANTE (`fromHere`), jamais `targets` (superset
    # move-inclus : un cast refuse rend `mutated:false`, observable identique a « rien ne se passe »).
    at = rpc(sid, "abilityTargets",
             {"runnerId": rid, "unitId": caster_id, "abilityType": SLASHING_DIVE}, 90) or {}
    row = next((u for u in (at.get("units") or []) if u.get("unitId") == caster_id), None)
    ab = next((a for a in ((row or {}).get("abilities") or [])
               if int(a.get("abilityId", -1)) == SLASHING_DIVE), {})

    def _ids(v):
        out = []
        for t in (v or []):
            if isinstance(t, dict):
                n = t.get("unitId", t.get("id", t.get("targetId")))
                if n is not None:
                    out.append(int(n))
            else:
                out.append(int(t))
        return out

    from_here = _ids(ab.get("fromHere") or ab.get("targetsFromHere"))
    superset = _ids(ab.get("targets"))
    p_live0 = pos_live(sid, rid)
    cible_ligne = [uid for uid, p in p_live0.items() if p == WAVE_TILES[0]]
    target_id = cible_ligne[0] if cible_ligne else (from_here[0] if from_here else None)
    if target_id is None:
        raise AssertionError("SCENARIO NON MONTE : aucune cible legale sur la 1re tuile de la ligne")

    # ---- [0] GATE DE CIBLAGE : le masque `TargetIsEnemy` MORD-il ? -------------------------------
    ability = ABILITY_CLASSES[SLASHING_DIVE]()
    gate = {
        "ennemi": get_invalid_target_reason(state, caster_id, target_id, ability),
        "allie": (get_invalid_target_reason(state, caster_id, ally_id, ability)
                  if ally_id is not None else None),
        "soi": get_invalid_target_reason(state, caster_id, caster_id, ability),
    }
    gate_natif = {"allie_dans_targets": (ally_id in superset) if ally_id is not None else None,
                  "soi_dans_targets": caster_id in superset}

    # ---- MT COMMUN : cale AVANT les deux casts ---------------------------------------------------
    rng0 = rpc(sid, "dumpRng", {"runnerId": rid}, 30)
    if not isinstance(rng0, dict) or "mt" not in rng0:
        raise AssertionError("dumpRng indisponible -> le degat n'est pas confrontable bit-exact")
    state.rng = seed_rng(rng0)

    # ---- OFFLINE : le cast, joue par le port -----------------------------------------------------
    off_hp0, off_pos0 = hp_off(state), pos_off(state)
    res = _apply_active_ability(state, caster_id, target_id, SLASHING_DIVE) or {}
    diag = res.get("diag") or {}
    off_hp1, off_pos1 = hp_off(state), pos_off(state)
    off_wave = [(int(w["target"]), int(w.get("total") or 0))
                for w in (diag.get("wave") or []) if w.get("target") is not None]

    # ---- LIVE : le MEME cast, joue par le natif, depuis le MEME etat MT --------------------------
    live_hp0, live_pos0 = hp_live(sid, rid), pos_live(sid, rid)
    act = rpc(sid, "applyAction", {"runnerId": rid, "action": {
        "kind": "ability", "casterId": caster_id, "abilityType": SLASHING_DIVE,
        "targetId": target_id}, "captureEvents": True}, 90) or {}
    act0 = (act.get("actions") or [{}])[0]
    live_hp1, live_pos1 = hp_live(sid, rid), pos_live(sid, rid)
    coups, groupes = native_wave(act0)
    # `changes` est le SECOND oracle natif du deplacement, independant de la cascade.
    chg = {int(c["squadId"]): c for c in (act0.get("changes") or []) if c.get("squadId") is not None}
    mv = chg.get(caster_id) or {}

    return {
        "rid": rid, "caster": caster_id, "target": target_id, "ally": ally_id,
        "avec_bouchon": avec_bouchon, "n_cibles": len(tuiles),
        "cast_error": act0.get("error"), "mutated": act0.get("mutated"),
        "routed": res.get("routed"), "ported": diag.get("ported"), "diag": diag,
        "gate": gate, "gate_natif": gate_natif,
        "from_here": from_here, "superset": superset,
        "off_wave": off_wave,
        "live_wave": [(t, a) for t, a, _c, _b, _p in coups],
        "live_crit": [c for _t, _a, c, _b, _p in coups],
        "live_block": [b for _t, _a, _c, b, _p in coups],
        "live_profile": sorted({p for _t, _a, _c, _b, p in coups}),
        "off_delta": {k: off_hp0[k] - off_hp1[k] for k in off_hp0 if off_hp0[k] != off_hp1.get(k)},
        "live_delta": {k: live_hp0[k] - live_hp1[k] for k in live_hp0
                       if live_hp0[k] != live_hp1.get(k)},
        "off_caster_pos": (off_pos0.get(caster_id), off_pos1.get(caster_id)),
        "live_caster_pos": (live_pos0.get(caster_id), live_pos1.get(caster_id)),
        "live_changes_move": ((mv.get("from") or {}).get("col"), (mv.get("from") or {}).get("row"),
                              (mv.get("to") or {}).get("col"), (mv.get("to") or {}).get("row"),
                              mv.get("moved")),
        "groupes": groupes,
        "damages_config": list(diag.get("damages") or []),
        "occupants": diag.get("occupants"),
        "pos_avant": {int(k): v for k, v in live_pos0.items()},
        # LETALITE, deux oracles independants : les PV natifs tombes a 0, et l'`isDead` publie par
        # `observeBattle` (le natif GARDE les morts dans la vue, cf. la note `decisionview keeps dead`).
        "live_morts": sorted(k for k, v in live_hp1.items() if v <= 0 and live_hp0.get(k, 0) > 0),
        "off_morts": sorted(k for k in off_hp0
                            if off_hp0[k] > 0 and off_hp1.get(k, 0) <= 0),
        "letal": bool(letal),
        "seed": str(seed or SEED),
    }


def rangs_de(s) -> list:
    """`[(montant_natif, bloque)]` INDEXE PAR RANG de la vague (0, 1, 2), pas par id d'unite : c'est
    l'appariement `tuile -> montant` qui rend l'etage `dmg_bonus` lisible. Une tuile vide rend
    `(0, False)`."""
    out = []
    for tile in WAVE_TILES:
        uid = next((u for u, p in s["pos_avant"].items() if p == tile), None)
        montant, bloque = 0, 0
        for j, (t, m) in enumerate(s["live_wave"]):
            if t == uid:
                montant, bloque = m, s["live_block"][j]
        out.append((montant, bool(bloque)))
    return out


def measure(sid: int, state_name: str = "probe_507_slashing_dive",
            avec_bouchon: bool = False, n_cibles: int = 3, letal: bool = False,
            seed: str | None = None):
    """Monte le scenario, joue le cast des DEUX cotes sur le MEME etat MT, rend `(mesures, dispose)`.

    C'est l'ENTREE que consomme `tests/engine/runner/test_slashing_dive_live.py` : le probe MESURE,
    le test GARDE, une SEULE implementation du montage. L'appelant est responsable de `dispose()`
    (le cast n'est pas rejouable : il consomme l'actif, donc un runner par scenario)."""
    state_path = PYDIR.parent.parent / "logs" / ("%s.json" % state_name)
    m = scenario(sid, state_path, avec_bouchon=avec_bouchon, n_cibles=n_cibles, letal=letal,
                 seed=seed)
    m["rangs"] = rangs_de(m)
    return m, (lambda: dispose(state_path))


def _ratios(coups_par_rang, damages):
    """`montant / dmg[rang]` rang par rang -- le canal `dmg_bonus`. Les mods ATTAQUANT sont
    multiplicatifs et communs aux trois rangs : un ratio identique partout est la signature d'un
    montant de base correctement INDEXE (dmg[0], dmg[1], dmg[2]) ; un ratio qui derive rang a rang
    signalerait que le port a fige un seul montant."""
    out = []
    for i, (montant, bloque) in enumerate(coups_par_rang):
        if i >= len(damages) or not damages[i] or bloque:
            out.append(None)
            continue
        out.append(round(montant / damages[i], 4))
    return out


def main() -> int:
    sid = _session()
    logs = PYDIR.parent.parent / "logs"
    # UN runner a la fois : on dispose AVANT de monter le suivant (budget partage, cf. runner.md).
    mesures = []
    for nom, kw in (("VAGUE", {}),
                    ("REPLI (tuile d'atterrissage occupee)", {"avec_bouchon": True}),
                    ("ANCRE (1 seule cible : la ligne est vide au-dela)", {"n_cibles": 1}),
                    ("LETAL (les trois cibles MEURENT)", {"letal": True}),
                    ("BLOCK (le 2e rang bloque)", {"seed": SEED_BLOCK})):
        sp = logs / ("probe_507_%s.json" % nom.split()[0].lower())
        try:
            mesures.append((nom, scenario(sid, sp, **kw)))
        finally:
            dispose(sp)

    prof = profil_ordinal()
    print("=== probe_507 -- 1091 SlashingDive (thousNpc2Screamer, chemin de stats explicite) ===")
    print("")
    for nom, s in mesures:
        rangs = rangs_de(s)
        print("--- SCENARIO %s (runner %s, seed %s) ---" % (nom, s["rid"], s["seed"]))
        print("  caster=%s target=%s allie=%s" % (s["caster"], s["target"], s["ally"]))
        print("  [1] porte   : routed=%s ported=%s cast_error=%s mutated=%s"
              % (s["routed"], s["ported"], s["cast_error"], s["mutated"]))
        print("  [0] gate    : port  ennemi=%s allie=%s soi=%s"
              % (s["gate"]["ennemi"], s["gate"]["allie"], s["gate"]["soi"]))
        print("              : natif allie_cible=%s soi_cible=%s"
              % (s["gate_natif"]["allie_dans_targets"], s["gate_natif"]["soi_dans_targets"]))
        print("  [2] topo    : port  %s" % (s["off_wave"],))
        print("              : natif %s" % (s["live_wave"],))
        print("  [3] degat   : port  delta=%s" % (sorted(s["off_delta"].items()),))
        print("              : natif delta=%s" % (sorted(s["live_delta"].items()),))
        print("  [6] faces   : crit=%s block=%s profils=%s (attendu %s)"
              % (s["live_crit"], s["live_block"], s["live_profile"], prof))
        print("              : dmg config=%s  rangs natifs=%s  ratios=%s"
              % (s["damages_config"], rangs, _ratios(rangs, s["damages_config"])))
        print("  [4] atterr. : port  %s -> %s" % s["off_caster_pos"])
        print("              : natif %s -> %s" % s["live_caster_pos"])
        print("              : changes %s" % (s["live_changes_move"],))
        print("  [8] morts   : port %s  natif %s" % (s["off_morts"], s["live_morts"]))
        print("  occupants   : %s" % (s["occupants"],))
        print("")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
