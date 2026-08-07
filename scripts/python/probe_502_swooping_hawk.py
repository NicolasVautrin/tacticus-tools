"""probe_502 -- MESURE de `1064 Loki_SwoopingHawk` (`eldarAutarch` Aethana, Aeldari, HERO).

QUESTION BINAIRE, posee AVANT la methode : **la vague frappe-t-elle une LIGNE de 3 tuiles ancree
sur la cible, et le caster atterrit-il DERRIERE la derniere cible touchee -- ou DEVANT elle ?**

Le premier volet separe deux modeles que le kit ne distingue pas (l'audit classe 1064
`DAMAGE(Piercing)`, le kit annonce `3hmp80` / `dmg_bonus` / `crit` / `pierce`, et rien de tout cela
ne dit la topologie) :

    M_ligne  (decompile) : Aethana -> A, puis les 2 tuiles ALIGNEES derriere A, degats DECROISSANTS
                           `dmg[0] > dmg[1] > dmg[2]` -- un montant PAR RANG
    M_splash (le voisin) : Aethana -> A + les ennemis ADJACENTS a A, meme montant partout

Le second volet est celui que le nom de la factory native ne tranche pas :
`DiveAttackAbilityBase$$GetMovementBehavior` appelle
`TileBehindTargetFromSourceDirection(target, source)` alors que le SELECTEUR construit lit
`(Select(+0x18), Select(+0x20))` = `(source, target)` -- les deux ordres sont inverses, et s'en
remettre au nom ferait atterrir le caster ENTRE lui et sa cible au lieu de derriere elle.

Le montage ci-dessous aligne TROIS ennemis en colonne derriere la cible : `M_splash` ne peut pas
produire trois montants DIFFERENTS, et l'atterrissage separe les deux ordres d'arguments (les deux
tuiles candidates sont de part et d'autre de la derniere cible).

ETAGES MESURES (jamais un scalaire fitte -- chaque etage a son oracle natif) :
  [0] GATE DE CIBLAGE      : le masque `TargetIsEnemy` MORD (allie et self refuses), et l'oracle du
                             refus est le natif lui-meme (`abilityTargets` n'enumere que des
                             ennemis). C'est la donnee posee AVEC l'entree au registre : sans elle,
                             `get_invalid_target_reason` rend 0 immediatement.
  [1] EXECUTION portee     : `diag.ported is True` (sans quoi le cast est un NO-OP SILENCIEUX --
                             l'etat d'ou part cette tranche).
  [2] TOPOLOGIE            : l'ENSEMBLE ORDONNE des cibles frappees, port == natif, lu dans la
                             cascade du cast (`Active_Ability_Type == 1064`).
  [3] DEGAT, TUILE PAR TUILE : `state.rng` CALE sur le MT live (`dumpRng`) -> egalite BIT-EXACTE des
                             montants, RANG PAR RANG. C'est ce qui decompose `pierce` (profil
                             `Piercing` -> `PiercingRatio` -> armure) et `dmg_bonus` (les mods
                             ATTAQUANT) au lieu de les absorber dans un total.
  [4] ATTERRISSAGE         : la position FINALE du caster, port == natif. Elle discrimine l'ordre
                             `(source, target)` (cf. ci-dessus) ET l'ancrage sur la DERNIERE tuile
                             portant un ennemi.
  [5] REPLI                : meme montage, la tuile d'atterrissage OCCUPEE -> le natif prend « la
                             tuile libre la plus proche ». C'est la branche FAUSSE du
                             `ConditionalSelector`, celle qui porte le `Randomize`.
  [6] LES TROIS FACES SEPAREES : `crit`, `dmg_bonus` et `pierce` ne sont PAS confondus.
                             - `crit`  : la famille ABILITY n'a AUCUN slot `RollCritical`. La mesure
                               est donc « `Attack_DidCrit == 0` sur TOUS les coups », et c'est un
                               OBSERVABLE, pas une simplification -- un port qui router
                               `AttackDamageOperation` (famille ATTACK) le ferait crit.
                             - `pierce` : `DamageProfileType` natif de chaque coup == l'ordinal du
                               profil `Piercing` lu au gameconfig.
                             - `dmg_bonus` : le RATIO `montant_inflige / dmg[i]` doit etre le MEME
                               aux trois rangs (les mods attaquant sont multiplicatifs et communs) ;
                               un rang bloque (`Attack_DidBlock`) est EXCLU du test et signale.

TEMOIN DE NON-DEGENERESCENCE (l'accord en regime degenere ne prouve rien) : le probe exige que les
trois montants natifs soient NON NULS et DEUX A DEUX DIFFERENTS -- c'est ce qui rend
`M_splash` refutable. Un montage ou personne ne prend de degat, ou ou les trois rangs prennent la
meme chose, est declare NON CONCLUANT plutot que vert.

Le placement est FORCE (`--place`/`--a-place`), en COLONNE : sur une grille odd-q, deux tuiles de
meme colonne et de rangees consecutives ont un delta cube CONSTANT `(0,-1,+1)` -- c'est donc une
vraie ligne hex, celle que `TilesBehindInLine` prolonge. Les cibles sont des unites de MELEE
(`orksNob`) et non les `eldarRanger` du premier montage : ceux-la portent `Overwatch_AutoAttack`,
qui TUE le caster a l'atterrissage et rend l'etage [4] inobservable. « Bloque par la geometrie »
n'est pas un resultat : on DEPLACE, et on change d'unite quand l'unite elle-meme est le bruit.

Sortie ASCII stricte (console cp1252). Ecrit sous `logs/`, jamais `data/` (#349).

Usage:
    python probe_502_swooping_hawk.py
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

SWOOPING_HAWK = 1064               # ActiveAbilityType.Loki_SwoopingHawk
BOARD = "MC1_67"

#: La LIGNE du montage : une colonne, quatre rangees consecutives. Le caster ouvre la colonne, les
#: trois cibles occupent les rangs 1, 2 et 3 de la vague.
CASTER_TILE = (3, 0)
WAVE_TILES = ((3, 1), (3, 2), (3, 3))
#: La tuile d'ATTERRISSAGE attendue = un pas au-dela de la derniere cible, dans la meme direction.
LANDING_TILE = (3, 4)
#: Cibles de MELEE : pas d'`Overwatch_AutoAttack` (cf. le bandeau -- les `eldarRanger` tuaient le
#: caster a l'atterrissage et rendaient l'etage [4] inobservable).
WAVE_UNITS = ("orksNob", "orksNob", "orksNob")
#: Temoin du gate ALLIE, pose loin de la ligne pour ne rien perturber.
ALLY_UNIT = "eldarRanger"
ALLY_TILE = (0, 6)
#: Bouchon du scenario REPLI : une unite POSEE sur la tuile d'atterrissage.
PLUG_UNIT = "orksRuntherd"

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
    "raison": "Il confronte le port de 1064 au NATIF via un runner live : il depend du code du "
              "port (arbre DSL + selecteurs de ligne/tuile-derriere + la feuille d'attaque "
              "d'ability + le registre + le masque de ciblage + la geometrie hex de "
              "`battle_query`) ET du build charge (le natif est l'oracle de la topologie, du "
              "degat et de l'atterrissage).",
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
    « port mort » est la faute que ce calage previent (mesure #497)."""
    from engine.runner.prng import IntBasedMersenneTwister
    rng = IntBasedMersenneTwister()
    rng.mt = list(s["mt"])
    rng.mti = s["mti"]
    return rng


def hp_live(sid, rid) -> dict:
    ob = rpc(sid, "observeBattle", {"runnerId": rid}, 40) or {}
    return {int(u["squadId"]): int(u["hp"]) for u in (ob.get("units") or [])}


def pos_live(sid, rid) -> dict:
    """`observeBattle` publie `col`/`row` A PLAT sur chaque unite (PAS sous un objet `position` --
    lire le mauvais champ rendait un dict VIDE, donc un « le caster n'a pas bouge » qui n'etait
    qu'un capteur muet)."""
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
    `kind: "group"` / `kind: "finish"`, et **`tags` est une CHAINE JSON**, pas un objet. Un
    parcours recursif qui cherche un noeud `UnitDamaged` rend donc ZERO, ce qui se lit exactement
    comme « le natif n'a rien frappe » -- premier capteur muet de ce probe, repare ici.

    Le discriminant est `Active_Ability_Type == 1064` : c'est le champ que `AbilityDamageOperation`
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
        if int(f.get("Active_Ability_Type", -1)) != SWOOPING_HAWK or "Target_Id" not in f:
            continue
        coups.append((int(f["Target_Id"]), int(f.get("Amount", 0)),
                      int(f.get("Attack_DidCrit", 0)), int(f.get("Attack_DidBlock", 0)),
                      int(f.get("DamageProfileType", -1))))
    return coups, groupes


def profil_ordinal() -> int:
    """Ordinal `IdunBattle.Entities.Enum.DamageProfileType` du profil de 1064, DERIVE de la table
    de noms du port -- jamais une seconde transcription a la main."""
    from engine.runner.abilities.aeldari import swooping_hawk_profile
    from engine.entities.damage_profile_type import PROFILE_NAME_BY_INDEX
    nom = swooping_hawk_profile()
    for idx, n in PROFILE_NAME_BY_INDEX.items():
        if n == nom:
            return int(idx)
    return -1


def scenario(sid, state_path: Path, avec_bouchon: bool = False, n_cibles: int = 3) -> dict:
    """Monte la ligne, joue le MEME cast des deux cotes depuis le MEME etat MT, et rend les deux
    observables cote a cote.

    `avec_bouchon` pose une unite SUR la tuile d'atterrissage -> etage [5] (branche FAUSSE du
    `ConditionalSelector`, celle qui porte le `Randomize`).

    `n_cibles` borne le nombre de tuiles OCCUPEES de la ligne -> etage [7]. C'est le discriminant
    de l'ANCRE : avec `n_cibles = 1`, seules les tuiles 2 et 3 sont vides, et le caster doit
    atterrir derriere la tuile **1** (la derniere PORTANT un ennemi), pas derriere la tuile 3. Un
    port qui prendrait « la derniere tuile de la ligne » au lieu de « la derniere tuile OCCUPEE »
    passe les scenarios a 3 cibles et tombe ici -- d'ou son existence."""
    from engine.runner.abilities.handler import ABILITY_CLASSES
    from engine.runner.abilities.targeting import get_invalid_target_reason
    from engine.runner.operations.summon_ai import _apply_active_ability

    tuiles = WAVE_TILES[:max(1, int(n_cibles))]
    a_units = list(WAVE_UNITS[:len(tuiles)]) + ([PLUG_UNIT] if avec_bouchon else [])
    args = ["--seed", "777", "--board", BOARD,
            "--p-units", "eldarAutarch,%s" % ALLY_UNIT,
            "--a-units", ",".join(a_units),
            "--place", "eldarAutarch:%d,%d" % CASTER_TILE,
            "--place", "%s:%d,%d" % ((ALLY_UNIT,) + ALLY_TILE)]
    for unit, tile in zip(WAVE_UNITS, tuiles):
        args += ["--a-place", "%s:%d,%d" % ((unit,) + tile)]
    if avec_bouchon:
        args += ["--a-place", "%s:%d,%d" % ((PLUG_UNIT,) + LANDING_TILE)]
    rid = build(state_path, args)

    state, dec0, bg = load(sid, rid)
    caster = find(dec0, "eldarAutarch")
    ally = find(dec0, ALLY_UNIT)
    if caster is None:
        raise AssertionError("SCENARIO NON MONTE : eldarAutarch absent du decisionView")
    caster_id = int(caster["id"])
    ally_id = int(ally["id"]) if ally is not None else None

    # Cible = une cible LEGALE DEPUIS LA POSITION COURANTE (`fromHere`), jamais `targets` (superset
    # move-inclus : un cast refuse rend `mutated:false`, observable identique a « rien ne se passe »).
    at = rpc(sid, "abilityTargets",
             {"runnerId": rid, "unitId": caster_id, "abilityType": SWOOPING_HAWK}, 90) or {}
    row = next((u for u in (at.get("units") or []) if u.get("unitId") == caster_id), None)
    ab = next((a for a in ((row or {}).get("abilities") or [])
               if int(a.get("abilityId", -1)) == SWOOPING_HAWK), {})
    # `abilityTargets` publie ses cibles tantot en ids nus, tantot en objets `{unitId|id: N}` selon
    # le champ -- on normalise plutot que de supposer une forme (un `int(dict)` leve, et le lire
    # comme « aucune cible » aurait fabrique un faux « porteur non confrontable »).
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
    ability = ABILITY_CLASSES[SWOOPING_HAWK]()
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
    res = _apply_active_ability(state, caster_id, target_id, SWOOPING_HAWK) or {}
    diag = res.get("diag") or {}
    off_hp1, off_pos1 = hp_off(state), pos_off(state)
    off_wave = [(int(w["target"]), int(w.get("total") or 0))
                for w in (diag.get("wave") or []) if w.get("target") is not None]

    # ---- LIVE : le MEME cast, joue par le natif, depuis le MEME etat MT --------------------------
    live_hp0, live_pos0 = hp_live(sid, rid), pos_live(sid, rid)
    act = rpc(sid, "applyAction", {"runnerId": rid, "action": {
        "kind": "ability", "casterId": caster_id, "abilityType": SWOOPING_HAWK,
        "targetId": target_id}, "captureEvents": True}, 90) or {}
    act0 = (act.get("actions") or [{}])[0]
    live_hp1, live_pos1 = hp_live(sid, rid), pos_live(sid, rid)
    coups, groupes = native_wave(act0)
    # `changes` est le SECOND oracle natif du deplacement, independant de la cascade : le host y
    # publie `from`/`to`/`moved` par unite. On le garde parce qu'un capteur unique qui se tait ne
    # se distingue pas d'un « rien ne s'est passe ».
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
    }


def measure(sid: int, state_name: str = "probe_502_swooping_hawk",
            avec_bouchon: bool = False, n_cibles: int = 3):
    """Monte le scenario, joue le cast des DEUX cotes sur le MEME etat MT, rend `(mesures, dispose)`.

    C'est l'ENTREE que consomme `tests/engine/runner/test_swooping_hawk_live.py` : le probe MESURE,
    le test GARDE, une SEULE implementation du montage -- aucune divergence possible entre les deux.
    L'appelant est responsable de `dispose()` (le cast n'est pas rejouable : il consomme l'actif,
    donc un runner par scenario)."""
    state_path = PYDIR.parent.parent / "logs" / ("%s.json" % state_name)
    m = scenario(sid, state_path, avec_bouchon=avec_bouchon, n_cibles=n_cibles)
    m["rangs"] = rangs_de(m)
    return m, (lambda: dispose(state_path))


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
    sp_a = logs / "probe_502_wave.json"
    sp_b = logs / "probe_502_repli.json"
    sp_c = logs / "probe_502_ancre.json"
    rc = 0
    try:
        a = scenario(sid, sp_a, avec_bouchon=False)
        b = scenario(sid, sp_b, avec_bouchon=True)
        c = scenario(sid, sp_c, n_cibles=1)
    finally:
        dispose(sp_a)
        dispose(sp_b)
        dispose(sp_c)

    prof = profil_ordinal()
    print("=== probe_502 -- 1064 Loki_SwoopingHawk (eldarAutarch) ===")
    print("")
    for nom, s in (("VAGUE", a), ("REPLI (tuile d'atterrissage occupee)", b),
                   ("ANCRE (1 seule cible : la ligne est vide au-dela)", c)):
        print("--- SCENARIO %s (runner %s) ---" % (nom, s["rid"]))
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
        print("              : dmg config (indexe par rang) = %s" % (s["damages_config"],))
        print("  [4] pos     : port  %s -> %s" % s["off_caster_pos"])
        print("              : natif %s -> %s" % s["live_caster_pos"])
        print("              : natif changes (%s,%s) -> (%s,%s) moved=%s" % s["live_changes_move"])
        print("              : groupes natifs = %s (0x2a=42 = ExecuteAtomic du decompile)"
              % (sorted(set(s["groupes"])),))
        print("  [6] faces   : crit=%s (attendu 0 partout : famille ABILITY, pas de RollCritical)"
              % (s["live_crit"],))
        print("              : block=%s" % (s["live_block"],))
        print("              : profil natif=%s attendu=%s" % (s["live_profile"], prof))
        rangs = rangs_de(s)
        print("              : ratio montant/dmg par rang = %s"
              % (_ratios(rangs, s["damages_config"]),))
        # TEMOIN DE NON-DEGENERESCENCE : sans lui, un accord se lirait sur un montage ou rien ne
        # bouge, ou les trois rangs prennent la meme chose (M_splash indistinguable).
        montants = [m for m, bl in rangs[:s["n_cibles"]] if not bl]
        mini = 2 if s["n_cibles"] >= 3 else 1
        temoin_non_nul = all(m > 0 for m in montants) and len(montants) >= mini
        temoin_distincts = len(set(montants)) == len(montants)
        print("  TEMOIN      : montants non-bloques=%s non_nuls=%s deux_a_deux_distincts=%s"
              % (montants, temoin_non_nul, temoin_distincts))
        if not temoin_non_nul:
            print("  ** NON CONCLUANT : regime degenere (aucun montant non-bloque exploitable) **")
            rc = 2
        print("")

    print("--- VERDICTS ---")
    # ETAGE [7] -- L'ANCRE. Avec une seule cible (tuile 1), le natif doit atterrir DERRIERE ELLE
    # (3,2) et non derriere la 3e tuile de la ligne (3,4). Les deux tuiles sont distinctes, donc
    # le scenario SEPARE reellement les deux modeles.
    ancre_natif = c["live_caster_pos"][1]
    ancre_port = c["off_caster_pos"][1]
    print("  ANCRE  1 cible -> natif %s | port %s | (attendu : derriere la tuile 1 = %s, "
          "PAS derriere la tuile 3 = %s)"
          % (ancre_natif, ancre_port, (WAVE_TILES[0][0], WAVE_TILES[0][1] + 1), LANDING_TILE))
    if ancre_natif == LANDING_TILE:
        print("  ** ANCRE NON CONCLUANTE : le natif atterrit au meme endroit qu'a 3 cibles, "
              "le scenario ne separe rien **")
        rc = 2
    for nom, s in (("VAGUE", a), ("REPLI", b), ("ANCRE", c)):
        ok_topo = sorted(s["off_wave"]) == sorted(s["live_wave"])
        ok_deg = (sorted(s["off_delta"].items()) == sorted(s["live_delta"].items()))
        ok_pos = s["off_caster_pos"][1] == s["live_caster_pos"][1]
        ok_crit = all(c == 0 for c in s["live_crit"])
        ok_prof = s["live_profile"] in ([prof], [])
        print("  %-6s topo=%s degat=%s position=%s crit0=%s profil=%s"
              % (nom, ok_topo, ok_deg, ok_pos, ok_crit, ok_prof))
        if not (ok_topo and ok_deg and ok_pos and ok_crit and ok_prof):
            rc = 1
    print("")
    print("rc=%d" % rc)
    return rc


if __name__ == "__main__":
    raise SystemExit(main())
