"""PROBE #957-r3 -- `1197 ExcruciatingFrequencies` : le `hits` du playbook natif, CONFRONTE.

QUESTION BINAIRE : `IdunBattle.AI.Playbook.Loki.ExcruciatingFrequenciesPlaybook$$MakeDamagePredictions`
predit-il `nrOfHits` LITTERAL, ou `GetDefaultAttackHits(nrOfHits, ExtraHits)` ?

Le cran offline (`tests/engine/test_957r3_excruciating_hits_offline.py`) garde la FORME de
l'override. Ce probe-ci va chercher l'ACCORD avec le natif, sur le porteur reel `emperNoiseMarine`,
par `aiPlaybookPredict` -- l'ORACLE DIRECT du playbook per-ability (il invoque
`<Ability>Playbook.MakeDamagePredictions` natif et rend `appliedHits` par evenement).

⚠ LE REGIME DISCRIMINANT N'EST PAS MONTABLE PAR LE LEVIER QUE LE RESIDU PROPOSAIT, et c'est le
premier resultat de ce probe. << `--unit-stat` sur la stat 17 >> suppose que l'entree BC d'une unite
porte un champ `ExtraHits` : elle n'en porte AUCUN (38 champs, tous listes par `--montrer-bc`).
`ExtraHits` est une stat de BATAILLE, a 0 par defaut, et le build `rnca9r7q6c` n'a que DEUX
producteurs, aucun des deux atteignable sur le caster de 1197 :

  * `IdunBattle.Entities.Effects.Loki.Swarm_HitReductionEffect` (1021, EXTRA_HITS **negatif** =
    `-min(nrOfMembers - 1, membres morts)`), pose par
    `IdunBattleLogic.Entities.Abilities.Active.Loki.SwarmAbility$$CreateBehaviour`. Voie
    d'attribution = le trait `Swarm`, porte par **3** unites du seed
    (`necroSmnSwarm`, `deathNpc3Nurglings`, `tyranNpc2RipperSwarm`) -- toutes SUMMON/NPC, et aucune
    ne porte 1197 ;
  * `DoomSiren_ExtraHit` (1431, `AddStaticStatModifierEffect(EXTRA_HITS, +1, PERMANENT)`), pose par
    la branche OVERKILL de `1199 DoomSiren` -- porteur `emperKakophonist`, qui porte 1199 et **pas**
    1197.

⇒ LE REGIME DISCRIMINANT S'ARME QUAND MEME, par le PREMIER producteur et par le SIGNE NEGATIF, et
c'est le second resultat de ce probe. `Swarm` n'est pas une propriete que le porteur aurait ou
n'aurait pas : c'est un TRAIT plus un compte de membres, et les DEUX sont des champs de l'entree BC
(`Traits`, `NumberOfMembers`) -- donc `--unit-stat`. Il ne manque que des membres MORTS, c'est-a-dire
`RemainingHealth < Health`, un troisieme champ BC. Montage complet, MESURE :

    --unit-stat emperNoiseMarine:NumberOfMembers=5
    --unit-stat emperNoiseMarine:Traits=[...,"Swarm"]
    --unit-stat emperNoiseMarine:RemainingHealth=800        (Health = 8533 -> 4 membres morts)
      => statModSources : extraHits = -4

⚠ `--hp-player` NE MARCHE PAS ici et c'est le piege du montage : il force `Health` **et**
`RemainingHealth` a la meme valeur, donc AUCUN membre mort, donc `extraHits = 0`. Il faut le champ
PER-UNIT `RemainingHealth`, seul a creuser l'ecart.

⇒ deux bras, et le probe DIT lequel il a joue :

  A. NOMINAL (`--bras nominal`, defaut) -- `emperNoiseMarine` tel quel. Accord natif/port sur le
     porteur reel, mais **DEGENERE par rapport a l'override** (`ExtraHits = 0` fait coincider les
     deux candidats) : c'est un accord, pas un discriminant, et le probe l'ecrit.
  B. SWARM (`--bras swarm`) -- le montage ci-dessus. `ExtraHits = -4` : le litteral vaut `nrOfHits`
     = 1 et le chemin generique `GetDefaultAttackHits(1, -4, 0, false)` = `max(1 - 4, 0)` = **0**.
     Les deux candidats sont donc SEPARES, et de la facon la plus visible qui soit (1 contre 0).
     Le probe MESURE `extraHits` avant de conclure : stat non armee -> `REGIME NON ARME`, et il ne
     confronte rien plutot que de fabriquer un discriminant qu'il n'a pas.

Usage (depuis scripts/python) :

    python probe_957r3_excruciating_hits.py                 # bras NOMINAL (accord, degenere)
    python probe_957r3_excruciating_hits.py --bras swarm    # bras DISCRIMINANT
    python probe_957r3_excruciating_hits.py --montrer-bc    # champs BC d'une unite (offline)

ASCII only. Dispose SES runners, jamais ceux des autres.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import uuid
from pathlib import Path

PYDIR = Path(__file__).resolve().parent
ROOT = PYDIR.parents[1]
if str(PYDIR) not in sys.path:
    sys.path.insert(0, str(PYDIR))

import probe_130_placement_sort_rng as P130  # noqa: E402

#: Ce qui doit changer pour que cette confrontation puisse changer d'avis.
DECLENCHEUR = {
    "chemins": ("scripts/python/engine/playbook/prediction/abilities.py",
                "scripts/python/engine/playbook/excruciating_frequencies.py",
                "scripts/python/engine/entities/abilities/active_ability.py",
                "scripts/python/engine/services/damage_prediction.py",
                "scripts/python/probe_957r3_excruciating_hits.py"),
    "build": True,
    "toujours": False,
    "raison": "Il confronte le `hits` predit par le playbook NATIF de 1197 a celui du port, et "
              "mesure si le regime discriminant (`ExtraHits != 0`) est seulement ARMABLE.",
}

PORTEUR = "emperNoiseMarine"          # seul porteur de 1197 dans le seed BC
ENNEMIS = "necroWarden,necroDestroyer"
ABILITY_1197 = 1197
BOARD = "MC1_67"
SEED = "777"
#: Traits du porteur au seed, PLUS `Swarm`. Recopies depuis `data/seed-bc.json` -- le patch
#: `--unit-stat` REMPLACE la liste, donc en omettre un retirerait un trait au passage.
TRAITS_SWARM = '["Chaos","Hero","ThrillSeekers","HeavyWeapon","SuppressiveFire","Swarm"]'
MEMBRES_SWARM = 5
#: `Health` du porteur normalise au rank courant = 8533 ; 800 PV laissent 4 membres sur 5 MORTS.
#: On ne code pas le `-4` attendu : il est MESURE par `statModSources`, et le verdict s'en sert.
PV_RESTANTS = 800


def _build(state_file, p_units, extra=()):
    cmd = [sys.executable, "rl_duel.py", "build", "--seed", SEED,
           "--state-file", str(state_file), "--board", BOARD,
           "--p-units", p_units, "--a-units", ENNEMIS] + list(extra)
    proc = subprocess.run(cmd, cwd=str(PYDIR), capture_output=True, text=True,
                          encoding="utf-8", errors="replace")
    if not Path(state_file).exists():
        print("BUILD KO:", (proc.stderr or proc.stdout or "")[-900:])
        return None
    return json.loads(Path(state_file).read_text())["runnerId"]


def _nr_of_hits():
    """`GetNumberConstant(0x2f = nrOfHits)` sur la config de `ExcruciatingFrequencies`."""
    import gameconfig as GC
    from engine.entities.abilities.ability_configuration import AbilityConfiguration
    cfg = AbilityConfiguration.from_gameconfig("ExcruciatingFrequencies",
                                               GC.ability("ExcruciatingFrequencies"))
    return int((cfg.constants or {}).get("nrOfHits") or 0), cfg


def _find_unit(ob, visual):
    for u in (ob or {}).get("units") or []:
        if u.get("visualId") == visual and not u.get("isDead"):
            return u
    return None


def _extra_hits_arme(rpc, rid, uid):
    """MESURE de la stat `ExtraHits` sur l'unite, par les sources de stat-mod NATIVES.

    `statModSources` publie `statTypes.extraHits = 17` (le nom EST derive du build, on ne code pas
    l'ordinal) et, par unite, un dict `mods` clef par ce meme nom. Un `mods` SANS entree `extraHits`
    signifie << aucune source ne modifie cette stat >> = 0 ; une reponse absente ou malformee rend
    `None` = **NON MESURE**, jamais rabattu sur 0."""
    r = rpc("statModSources", {"runnerId": rid, "unitId": int(uid)}, 40)
    if not isinstance(r, dict) or not r.get("ok"):
        return None
    nom = None
    for k, v in (r.get("statTypes") or {}).items():
        if int(v) == 17:
            nom = k
            break
    if nom is None:
        return None
    for u in (r.get("units") or []):
        if int(u.get("entityId", -1)) != int(uid):
            continue
        mods = u.get("mods") or {}
        entree = mods.get(nom)
        return 0 if entree is None else int(entree.get("total") or 0)
    return None


def _confronte(rpc, rid, ob, visual, nr_hits):
    caster = _find_unit(ob, visual)
    if caster is None:
        return {"ok": False, "raison": "caster %s absent du runner" % visual}
    ennemis = [u for u in (ob.get("units") or [])
               if u.get("teamId") != caster.get("teamId") and not u.get("isDead")]
    if not ennemis:
        return {"ok": False, "raison": "aucun ennemi vivant"}
    # ⚠ `aiPlaybookPredict` (comme `statModSources`) veut le **`squadId`** d'`observeBattle`, pas son
    # `entityId` : passer l'`entityId` rend `unit 82 not found (unit/machine)`. Meme piege que celui
    # deja nomme sur `combatSnapshot.units[].entityId` (#982-r5).
    cid = int(caster["squadId"])
    extra = _extra_hits_arme(rpc, rid, cid)
    out = {"ok": True, "caster": visual, "casterId": cid, "extraHits": extra,
           "nrOfHits": nr_hits, "events": []}
    for e in ennemis:
        r = rpc("aiPlaybookPredict", {"runnerId": rid, "unitId": cid,
                                      "targetId": int(e["squadId"]),
                                      "abilityType": ABILITY_1197}, 60)
        if not isinstance(r, dict) or not r.get("ok"):
            continue
        for ev in (r.get("events") or []):
            out["events"].append({"target": ev.get("targetId"),
                                  "appliedHits": ev.get("appliedHits")})
    return out


def _verdict(res):
    if not res.get("ok"):
        print("NON MESURE :", res.get("raison"))
        return 2
    hits = sorted({e["appliedHits"] for e in res["events"] if e["appliedHits"] is not None})
    print("caster=%s id=%s  ExtraHits(stat 17)=%s  nrOfHits(config)=%s"
          % (res["caster"], res["casterId"], res["extraHits"], res["nrOfHits"]))
    print("appliedHits NATIFS distincts :", hits, "  (%d evenements)" % len(res["events"]))
    if not hits:
        print("REGIME NON ARME : `aiPlaybookPredict` n'a rendu AUCUN evenement -- rien a confronter")
        return 2
    from engine.services.damage_prediction import get_default_attack_hits
    litteral = res["nrOfHits"]
    # Le candidat GENERIQUE, calcule par le FOYER du port (`AActiveAbility.get_special_hits` y
    # delegue) et non par une addition ecrite ici -- le natif termine par `Math.Max(..., 0)`, que
    # seule cette fonction porte.
    generique = get_default_attack_hits(litteral, int(res["extraHits"] or 0), 0, False)
    if res["extraHits"] in (None, 0):
        print("ACCORD, mais en regime DEGENERE : `ExtraHits` = %s, donc le litteral (%d) et le "
              "chemin generique (%d) COINCIDENT. L'accord ne discrimine PAS l'override."
              % (res["extraHits"], litteral, generique))
        ok = hits == [litteral]
        print("VERDICT :", "appliedHits == nrOfHits" if ok else "ECART : %s != %d" % (hits, litteral))
        return 0 if ok else 1
    print("REGIME DISCRIMINANT : litteral=%d  generique=%d" % (litteral, generique))
    if hits == [litteral]:
        print("VERDICT : le natif predit le LITTERAL -- l'override du port est CONFIRME live")
        return 0
    if hits == [generique]:
        print("VERDICT : le natif predit le GENERIQUE -- l'override du port est REFUTE")
        return 1
    print("VERDICT : appliedHits %s ne vaut NI le litteral NI le generique -- etage inconnu" % hits)
    return 1


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--bras", choices=("nominal", "swarm"), default="nominal")
    ap.add_argument("--state-file", default=None)
    ap.add_argument("--montrer-bc", action="store_true",
                    help="OFFLINE : imprime les champs de l'entree BC du porteur (le levier du "
                         "residu supposait un champ `ExtraHits` -- il n'existe pas)")
    a = ap.parse_args()

    if a.montrer_bc:
        bc = json.loads((ROOT / "data" / "seed-bc.json").read_text(encoding="utf-8"))
        for u in bc["Units"]:
            if u.get("VisualId") == PORTEUR:
                print("champs BC de %s (%d) :" % (PORTEUR, len(u)))
                print(sorted(u))
                print("champ `ExtraHits` present :", "ExtraHits" in u)
                return 0
        print("porteur absent du seed BC")
        return 2

    nr_hits, _cfg = _nr_of_hits()
    rpc = P130.Rpc()
    sf = Path(a.state_file) if a.state_file else (
        ROOT / "logs" / "runners" / ("p957r3-%s.json" % uuid.uuid4().hex[:8]))
    sf.parent.mkdir(parents=True, exist_ok=True)
    # `--place` : 1197 est une ability de LIGNE (`GetAffectedTiles` = `TilesBehindInLine(CasterTile,
    # Direction, ...)`). Au placement de spawn les deux camps sont face a face mais le caster n'est
    # PAS aligne avec eux -- le playbook rend alors zero evenement, et un probe qui s'arreterait la
    # conclurait << pas de prediction >> pour une raison de GEOMETRIE. On aligne donc explicitement.
    place = ["--place", "%s:6,6" % PORTEUR]
    if a.bras == "nominal":
        extra = list(place)
    else:
        # SWARM : les TROIS champs BC qui arment `Swarm_HitReduction`, et rien d'autre. `--hp-player`
        # est INUTILISABLE ici (il aligne `Health` sur `RemainingHealth` -> 0 membre mort).
        extra = place + [
            "--unit-stat", "%s:NumberOfMembers=%d" % (PORTEUR, MEMBRES_SWARM),
            "--unit-stat", "%s:Traits=%s" % (PORTEUR, TRAITS_SWARM),
            "--unit-stat", "%s:RemainingHealth=%d" % (PORTEUR, PV_RESTANTS)]
    rid = _build(sf, PORTEUR, extra)
    if rid is None:
        print("NON CONFRONTE : le build a echoue (ce n'est pas un verdict sur le port)")
        return 2
    try:
        ob = rpc("observeBattle", {"runnerId": rid}, 40)
        res = _confronte(rpc, rid, ob, PORTEUR, nr_hits)
        return _verdict(res)
    finally:
        rpc("disposeRunner", {"runnerId": rid}, 30)
        Path(sf).unlink(missing_ok=True)


if __name__ == "__main__":
    sys.exit(main())
