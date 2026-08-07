"""#513 -- RECENSEMENT de la famille `IdunBattle.Entities.Effects.APendingAttackEffect`.

Le patron 2-PHASES : une ability ACTIVE pose un effet de bond derive d'`APendingAttackEffect`
(phase 1), et le DEGAT appartient a une ability TRIGGERED que cet effet declenche au debut du
tour suivant de l'unite attaquante (phase 2). Le foyer est
`IdunBattle.Entities.Effects.APendingAttackEffect$$CreateHandleTriggerAbilitiesInternal`, commun a
TOUTE la famille.

CE QUE CE PROBE DERIVE (il ne devine rien) :

  [1] la FERMETURE TRANSITIVE des classes dont un ancetre est `APendingAttackEffect`, lue dans la
      colonne PARENT de `data/symbols/<build>/frida/classes.tsv` ;
  [2] les methodes que chaque classe DECLARE, dans les DEUX tables (frida ET ghidra) -- l'ABSENCE
      n'y prouve rien : elles sont indexees par ADRESSE et IL2CPP DEDUPLIQUE les corps triviaux ;
  [3] le `TriggeredAbilityType` rendu par chaque `GetTriggeredAbilityType`, resolu PAR NOM dans
      `frida/enums.tsv` (jamais par ordinal : 0x467 est `SeekerMissileFrequencyLock_Attack` en
      `TriggeredAbilityType` et `AnnihilatorBeam_PendingAttack` en `EffectType`) ;
  [4] l'`ActiveAbilityType` de meme radical = la PHASE 1 presumee, et son etat dans
      `ABILITY_CLASSES` (le registre COMBAT du port).

DEUX MESURES SONT DES ENTREES ECRITES, pas des derivations -- chacune cite son symbole :

  * `GTAT_LU` : la valeur rendue par `<classe>$$GetTriggeredAbilityType`, LUE au decompile
    (ghidra-mcp, build `rnca9r7q6c`). Elle n'est pas derivable des TSV, qui ne portent pas de
    corps de fonction. Le probe verifie qu'elle couvre EXACTEMENT la fermeture [1] -- une classe
    neuve fait donc rougir, elle ne disparait pas en silence.
  * `PHASE1_LU` : l'`ActiveAbilityType` reellement ETABLI (cast-site lu, ou case-doc). Le radical
    partage ne PROUVE rien -- il oriente. Le probe imprime les deux colonnes cote a cote et DIT
    quand elles divergent.

DEUX CLASSES NE RENDENT PAS DE CONSTANTE : `IdunBattle.Entities.Effects.OwnerPendingAttackEffect`
et `IdunBattle.Entities.Effects.Loki.TheWrathOfKhaineUnleashed_PendingAttackEffect`. Les deux
pesent **1160** octets la ou les 18 autres en pesent 1152, et le corps unique que ghidra publie
(`return *(uint*)(this+0x480)`) lit exactement ce champ de 8 octets supplementaire : les deux
declarent la meme surcharge, ghidra n'en nomme qu'UN proprietaire. C'est le piege « l'absence dans
les tables ne prouve rien », dans sa forme la plus nette de ce dossier.

Usage :  python probe_513_pending_attack_family.py [--json]
rc 0 = recensement coherent ; rc 1 = la fermeture et les tables ecrites ont diverge.
"""
from __future__ import annotations

import io
import json
import os
import sys
from collections import defaultdict

_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

BASE = "IdunBattle.Entities.Effects.APendingAttackEffect"

#: `<classe native>$$GetTriggeredAbilityType` -> valeur LUE au decompile (build `rnca9r7q6c`).
#: `None` = le corps ne rend PAS de constante : il lit le champ `this+0x480` (classes de 1160 o).
GTAT_LU: dict[str, int | None] = {
    "Idun.Source.IdunBattle.Logic.Entities.Effects.Loki.DevastatingRefrainEffect": 0x523,
    "Idun.Source.IdunBattle.Logic.Entities.Effects.Loki.InstrumentsOfVengeance_PendingAttackEffect": 0x5ef,
    "IdunBattle.Entities.Effects.Loki.AnnihilatorBeam_PendingAttackEffect": 0x469,
    "IdunBattle.Entities.Effects.Loki.EreWeGo_PendingAttackEffect": 0x480,
    "IdunBattle.Entities.Effects.Loki.GazeOfMagnusEffect": 0x4e7,
    "IdunBattle.Entities.Effects.Loki.HeavyRailRifle_PendingAttackEffect": 0x4ec,
    "IdunBattle.Entities.Effects.Loki.MalleusRocketLauncherEffect": 0x4d7,
    "IdunBattle.Entities.Effects.Loki.NeedsMoreDakka_PendingAttackEffect": 0x47f,
    "IdunBattle.Entities.Effects.Loki.OverwhelmingWrath_PendingAttackEffect": 0x4d5,
    "IdunBattle.Entities.Effects.Loki.PoundThemToDust_PendingAttackEffect": 0x4b9,
    "IdunBattle.Entities.Effects.Loki.SeekerMissileFrequencyLockTargetEffect": 0x467,
    "IdunBattle.Entities.Effects.Loki.SolarAtomizer_PendingAttackEffect": 0x511,
    "IdunBattle.Entities.Effects.Loki.TargetingProtocols_PendingAttackEffect": 0x466,
    "IdunBattle.Entities.Effects.Loki.TheLantern_PendingAttackEffect": 0x48f,
    "IdunBattle.Entities.Effects.Loki.TheLionsWrath_PendingAttackEffect": 0x5f0,
    "IdunBattle.Entities.Effects.Loki.TheWailingDoomStrikes_PendingAttackEffect": 0x4c9,
    "IdunBattle.Entities.Effects.Loki.TheWailingDoomSweeps_PendingAttackEffect": 0x4c8,
    "IdunBattle.Entities.Effects.Loki.ValkyrieStrikeEffect": 0x402,
    "IdunBattle.Entities.Effects.Loki.TheWrathOfKhaineUnleashed_PendingAttackEffect": None,
    "IdunBattle.Entities.Effects.OwnerPendingAttackEffect": None,
}

#: `<classe native>` -> `ActiveAbilityType` de la PHASE 1, ETABLI (pas devine). Les six lignes
#: renseignees sont celles dont la phase 1 est PORTEE, et chacune a son cast-site lu :
#:   1069 `...Active.Loki.SeekerMissileFrequencyLockAbility$$ExecuteBehaviour` (case-491)
#:   1141 `...Active.Loki.OverwhelmingWrathAbility$$ExecuteBehaviour`          (case-503)
#:   1160 `...Active.Loki.HeavyRailRifleAbility$$ExecuteBehaviour`
#:   1142 `...Active.Loki.MalleusRocketLauncherAbility$$ExecuteBehaviour`
#:   1188 `...Active.Loki.DevastatingRefrainAbility$$ExecuteBehaviour`
#:   1018 `...Active.Loki.ValkyrieStrikeAbility$$ExecuteBehaviour`             (bond_removal.py)
#: Les autres restent `None` : leur phase 1 n'est pas portee, donc le lien n'a pas ete etabli --
#: et ecrire un radical a la place d'une lecture serait une hypothese deguisee en mesure.
PHASE1_LU: dict[str, int | None] = {
    "IdunBattle.Entities.Effects.Loki.SeekerMissileFrequencyLockTargetEffect": 1069,
    "IdunBattle.Entities.Effects.Loki.OverwhelmingWrath_PendingAttackEffect": 1141,
    "IdunBattle.Entities.Effects.Loki.HeavyRailRifle_PendingAttackEffect": 1160,
    "IdunBattle.Entities.Effects.Loki.MalleusRocketLauncherEffect": 1142,
    "Idun.Source.IdunBattle.Logic.Entities.Effects.Loki.DevastatingRefrainEffect": 1188,
    "IdunBattle.Entities.Effects.Loki.ValkyrieStrikeEffect": 1018,
}


def _build() -> str:
    p = os.path.join(_HERE, "..", "..", "data", "symbols", "CURRENT")
    return io.open(p, encoding="ascii").read().strip()


def _sym_dir() -> str:
    return os.path.join(_HERE, "..", "..", "data", "symbols", _build())


def _read_tsv(path: str) -> list[list[str]]:
    rows = []
    for line in io.open(path, "r", encoding="utf-8"):
        if line.startswith("#!") or line.startswith("# "):
            continue
        rows.append(line.rstrip("\n").split("\t"))
    return rows


def _enum(name: str) -> dict[int, str]:
    for line in io.open(os.path.join(_sym_dir(), "frida", "enums.tsv"), "r", encoding="utf-8"):
        if line.startswith(name + "\t"):
            _, vals = line.rstrip("\n").split("\t", 1)
            out = {}
            for kv in vals.split(","):
                k, v = kv.split("=", 1)
                out[int(k)] = v
            return out
    return {}


def family() -> tuple[set[str], dict[str, str], dict[str, str]]:
    """[1] Fermeture TRANSITIVE des derivees d'`APendingAttackEffect`, + parent + taille."""
    rows = _read_tsv(os.path.join(_sym_dir(), "frida", "classes.tsv"))
    parent = {r[0]: r[2] for r in rows if len(r) >= 3}
    size = {r[0]: r[1] for r in rows if len(r) >= 3}
    fam: set[str] = set()
    changed = True
    while changed:
        changed = False
        for cls, par in parent.items():
            if cls not in fam and (par == BASE or par in fam):
                fam.add(cls)
                changed = True
    return fam, parent, size


def declared_methods() -> tuple[dict[str, list[str]], dict[str, set[str]]]:
    """[2] Ce que chaque table PUBLIE par classe. Les deux, parce qu'aucune n'est complete."""
    fm = _read_tsv(os.path.join(_sym_dir(), "frida", "methods.tsv"))
    by_frida: dict[str, list[str]] = defaultdict(list)
    for r in fm:
        if len(r) >= 3:
            by_frida[r[2]].append(r[1].rsplit(".", 1)[-1])
    gh = _read_tsv(os.path.join(_sym_dir(), "ghidra", "functions.tsv"))
    by_ghidra: dict[str, set[str]] = defaultdict(set)
    for r in gh:
        if len(r) >= 2 and "$$" in r[1]:
            c, m = r[1].split("$$", 1)
            by_ghidra[c].add(m)
    return by_frida, by_ghidra


def recense() -> dict:
    fam, parent, size = family()
    by_frida, by_ghidra = declared_methods()
    trig = _enum("IdunBattle.Entities.Enum.TriggeredAbilityType")
    act = _enum("IdunBattle.Entities.Enum.ActiveAbilityType")
    act_by_name = {v: k for k, v in act.items()}
    from engine.runner.abilities.handler import ABILITY_CLASSES

    items = []
    for cls in sorted(fam, key=lambda c: c.split(".")[-1]):
        v = GTAT_LU.get(cls, "MANQUANTE")
        tname = None
        radical = None
        if isinstance(v, int):
            tname = trig.get(v)
            radical = tname.rsplit("_", 1)[0] if tname else None
        p1_radical = act_by_name.get(radical) if radical else None
        p1_lu = PHASE1_LU.get(cls)
        p1 = p1_lu if p1_lu is not None else p1_radical
        items.append({
            "classe": cls,
            "court": cls.split(".")[-1],
            "taille": size.get(cls),
            "gtat": v,
            "triggered_nom": tname,
            "phase1_radical": p1_radical,
            "phase1_lu": p1_lu,
            "phase1": p1,
            "phase1_portee": (p1 in ABILITY_CLASSES) if p1 is not None else None,
            "frida": sorted(by_frida.get(cls, [])),
            "ghidra": sorted(by_ghidra.get(cls, ())),
        })
    return {"build": _build(), "base": BASE,
            "chaine": [BASE, parent.get(BASE), parent.get(parent.get(BASE, ""), None)],
            "items": items}


def main(argv: list[str]) -> int:
    r = recense()
    if "--json" in argv:
        print(json.dumps(r, indent=1, sort_keys=True))
        return 0
    items = r["items"]
    print("=" * 104)
    print("RECENSEMENT #513 -- famille APendingAttackEffect (patron 2-PHASES), build %s" % r["build"])
    print("=" * 104)
    print("chaine : %s <- %s <- %s" % tuple(r["chaine"]))
    print("derivees (fermeture transitive de classes.tsv) : %d" % len(items))
    print("")
    fmt = "%-46s %5s %6s %-36s %6s %-7s"
    print(fmt % ("classe native (nom court)", "size", "gtat", "TriggeredAbilityType (NOM)",
                 "phase1", "portee"))
    print("-" * 112)
    for it in items:
        g = it["gtat"]
        gtxt = "champ" if g is None else ("MANQ." if g == "MANQUANTE" else str(g))
        p1 = it["phase1"]
        porte = "-" if it["phase1_portee"] is None else ("OUI" if it["phase1_portee"] else "non")
        print(fmt % (it["court"], it["taille"] or "?", gtxt,
                     it["triggered_nom"] or "<champ / absent de l'enum>",
                     "-" if p1 is None else str(p1), porte))
    print("")
    print("METHODES DECLAREES -- frida | ghidra (l'ABSENCE ne prouve rien : dedup par ADRESSE)")
    for it in items:
        print("  %-46s frida=%-44s ghidra=%s"
              % (it["court"], ",".join(it["frida"]) or "(0)", ",".join(it["ghidra"]) or "(0)"))
    print("")
    a_porter = [it for it in items if it["phase1_portee"]]
    non_portee = [it for it in items if it["phase1_portee"] is False]
    inconnu = [it for it in items if it["phase1_portee"] is None]
    print("BILAN")
    print("  phase 1 PORTEE, phase 2 A PORTER : %d" % len(a_porter))
    for it in a_porter:
        print("     * active %-5s -> triggered %-5s %-36s (effet %s)"
              % (it["phase1"], it["gtat"], it["triggered_nom"], it["court"]))
    print("  phase 1 NON portee (rien a brancher tant qu'elle manque) : %d" % len(non_portee))
    for it in non_portee:
        print("     * active %-5s -> triggered %-5s %-36s (effet %s)"
              % (it["phase1"], it["gtat"], it["triggered_nom"], it["court"]))
    print("  phase 1 NON ETABLIE : %d" % len(inconnu))
    for it in inconnu:
        print("     * %-36s (effet %s, taille %s)"
              % (it["triggered_nom"] or "<champ>", it["court"], it["taille"]))
    print("")

    # ---- COHERENCE : la table ecrite doit couvrir EXACTEMENT la fermeture derivee -------------
    ecrites = set(GTAT_LU)
    derivees = {it["classe"] for it in items}
    rc = 0
    if ecrites != derivees:
        rc = 1
        print("ECHEC -- GTAT_LU ne couvre pas la fermeture :")
        print("   dans la fermeture, PAS dans GTAT_LU : %s" % sorted(derivees - ecrites))
        print("   dans GTAT_LU, PLUS dans la fermeture : %s" % sorted(ecrites - derivees))
    inconnus_enum = [it["court"] for it in items
                     if isinstance(it["gtat"], int) and it["triggered_nom"] is None]
    if inconnus_enum:
        rc = 1
        print("ECHEC -- gtat absent de TriggeredAbilityType : %s" % inconnus_enum)
    divergents = [(it["court"], it["phase1_lu"], it["phase1_radical"]) for it in items
                  if it["phase1_lu"] is not None and it["phase1_radical"] is not None
                  and it["phase1_lu"] != it["phase1_radical"]]
    if divergents:
        print("ATTENTION -- phase1 LUE != phase1 par RADICAL (le radical n'est qu'un indice) : %s"
              % divergents)
    print("PROBE %s" % ("OK" if rc == 0 else "ECHEC"))
    return rc


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
