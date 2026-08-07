#!/usr/bin/env python
"""#271-r4 -- les TROIS faces de la feuille `TriggeredAbilitiesNonOwner(4)`, et LAQUELLE est portee.

POURQUOI CE PROBE EXISTE. Le residu #271-r4 disait « les 24 autres playbooks
`*NonOwnerPlaybook` du binaire restent non portes », sur la base de « un seul est au registre ».
Les deux chiffres sont PERIMES : le registre en porte 19, et le compte de concrets est 28, pas 25
(compte par PARENT, pas par NOM -- trois concrets ne portent pas le suffixe). Ce qui RESTE ouvert
n'est donc pas une liste de classes, c'est **une FACE entiere du dispatcher**.

`IdunBattle.AI.Utilities.TriggeredAbilitiesNonOwnerUtility` en a TROIS, chacune avec sa propre
machine a etats et son propre `IterateAbilities` :

    $$EvaluateMovementInSteps  -> `...u003CEvaluateMovementInStepsu003Ed__0$$MoveNext`  (+ `IterateAbilities` d__3)
    $$EvaluateAttackInSteps    -> `...u003CEvaluateAttackInStepsu003Ed__1$$MoveNext`    (+ `IterateAbilities` d__4)
    $$EvaluateRepairInSteps    -> `...u003CEvaluateRepairInStepsu003Ed__2$$MoveNext`

et l'interface `IdunBattle.AI.Playbook.ITriggeredAbilityNonOwnerPlaybook` leur repond par ses
slots 0 / 1 / 2 (`CalculateMovementUtilityInSteps` / `CalculateAttackUtilityInSteps` /
`CalculateRepairUtilityInSteps`). Le port ne monte QUE la face MOVE
(`engine/utilities/tile.py::TriggeredAbilitiesNonOwnerUtility.evaluate`).

REACHABILITY AVANT PORT (la regle du CLAUDE.md) -- ce que ce probe MESURE.
Une face n'est atteignable que si la feuille 4 est MEMBRE du composite qui la porte.
`IdunBattle.Core.Services.UtilitiesDatabase$$GetUtility` resout un `utilityType` par une CARTE DE
COMPOSITION (`db+0x58`, `Dictionary<UtilityType, UtilityType[]>`) que
`IdunBattle.Core.Services.UtilitiesDatabase$$InitializeUtilities` remplit ; chaque tableau est
rempli par `System.Runtime.CompilerServices.RuntimeHelpers$$InitializeArray` depuis un blob de
`<PrivateImplementationDetails>` -- et ces blobs vivent dans le **`global-metadata.dat`**, pas dans
le PE (cherches dans `GameAssembly.dll`, ils n'y sont pas : mesure, 0 occurrence).

CE QUI EST LU AU DECOMPILE (cite, pas mesure ici) : les COUPLES `(cle, taille)` de la carte --
`InitializeUtilities` appelle `il2cpp_array_new(<UtilityType>, N)` puis `InitializeArray` puis
`Dictionary.Add(map, cle, tableau)` :

    Tile(7) -> 29 | Damage(35) -> 13 | Repair(47) -> 3 | AttackTile(8) -> 4
    Spawn(0) -> 2 | MovementSuggestion(33) -> 2 | UnitMovement(6) -> 2 | UnitMovementFromTemporary(5) -> 2

CE QUE CE PROBE MESURE : le CONTENU de ces blobs. Il s'ancre sur le blob `Tile(7)`, qui est le SEUL
identifiable sans rien supposer -- ses 29 elements sont deja portes et confrontes
(`engine/utilities/tile.py::TILE_LEAF_IDS`), et sa suite d'octets est UNIQUE dans le fichier. Les
blobs voisins sont delimites par un `0`, ce qui permet de les segmenter.

⚠ ANTI-CIRCULARITE. On ne cherche pas « un blob qui contient la feuille 4 » -- ce serait supposer
la reponse. Chaque blob est identifie par sa TAILLE (lue au decompile) **et** par un temoin
INDEPENDANT de la question posee, deja porte dans le depot :
  * Damage(35) : doit contenir `DamageDealt(36)`, `KillUnit(37)`, `OverkillUnit(38)` -- les trois
    dominants portes par `engine/utilities/damage.py` ;
  * Repair(47) : doit contenir `RepairedAmount(48)` -- la feuille portee par
    `engine/utilities/repair.py`.
Si un temoin manque, le probe LEVE : une identification ratee ne doit pas se lire comme une mesure.

Usage :
    python probe_271r4_composition_map.py            # carte + ventilation des 28 concrets
    python probe_271r4_composition_map.py --blobs    # + segmentation brute autour de l'ancre

ASCII only (console cp1252).
"""
from __future__ import annotations

import argparse
import struct
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from engine.utilities.tile import TILE_LEAF_IDS                      # noqa: E402
from engine.utilities.utility_type import UtilityType as U           # noqa: E402
import build_pin                                                     # noqa: E402


#: `(cle, taille)` de la carte de composition -- LUS dans
#: `IdunBattle.Core.Services.UtilitiesDatabase$$InitializeUtilities` (build rnca9r7q6c).
#: Les deux composites qui portent une face NON PORTEE sont `Damage` et `Repair`.
TAILLES_LUES = {
    int(U.Spawn): 2, int(U.UnitMovementFromTemporary): 2, int(U.UnitMovement): 2,
    int(U.Tile): 29, int(U.AttackTile): 4, int(U.MovementSuggestion): 2,
    int(U.Damage): 13, int(U.Repair): 3,
}

#: Temoin INDEPENDANT par composite : des feuilles deja portees, dont la presence identifie le blob
#: sans rien presupposer de la feuille 4. `None` = blob non identifie par ce probe.
TEMOINS = {
    int(U.Damage): (int(U.DamageDealt), int(U.KillUnit), int(U.OverkillUnit)),
    int(U.Repair): (int(U.RepairedAmount),),
}

NOMS = {int(m): m.name for m in U}


def _nom(v: int) -> str:
    return NOMS.get(v, "<hors mirror>")


def _metadata() -> Path:
    """`global-metadata.dat`, par le foyer `build_pin.global_metadata()`.

    ⚠ NE PAS refaire le chemin a la main : ce foyer confronte le build INSTALLE au build
    VERSIONNE et REFUSE quand ils divergent. Sans ce controle, ce probe lirait les blobs d'un
    build et la table des faces (`data/symbols/<build>/metadata/non_owner_slot4.tsv`) d'un autre
    -- la desynchronisation silencieuse que le CLAUDE.md nomme. `BuildPinRefused` remonte telle
    quelle : une entree hors depot absente est une mesure IMPOSSIBLE, jamais un zero."""
    return build_pin.global_metadata()


def ancre(data: bytes) -> int:
    """Offset du blob `Tile(7)`. C'est la SEULE ancre qui ne suppose rien : ses 29 elements sont
    portes ET confrontes ailleurs. LEVE si absente ou ambigue."""
    pat = b"".join(struct.pack("<i", int(x)) for x in TILE_LEAF_IDS)
    n = data.count(pat)
    if n != 1:
        raise SystemExit(
            "le blob Tile(7) apparait %d fois dans le metadata (attendu 1) : l'ancre n'est pas "
            "fiable, et une segmentation ancree sur elle ne mesurerait rien" % n)
    return data.find(pat)


def _runs(data: bytes, centre: int, rayon: int = 8192) -> list:
    """Segmente en runs 0-delimites la fenetre autour de l'ancre. Rend `[(offset, [valeurs])]`.

    Les blobs de `<PrivateImplementationDetails>` sont contigus et separes par des `0` ; on ne
    retient que les runs entierement composes de valeurs plausibles pour un `UtilityType`."""
    lo = max(0, (centre - rayon) & ~3)
    hi = min(len(data), centre + rayon)
    vals = struct.unpack("<%di" % ((hi - lo) // 4), data[lo:lo + ((hi - lo) // 4) * 4])
    out, cur, deb = [], [], None
    for k, v in enumerate(vals):
        if 0 < v <= 80:
            if not cur:
                deb = lo + 4 * k
            cur.append(v)
        else:
            if cur:
                out.append((deb, cur))
            cur, deb = [], None
    if cur:
        out.append((deb, cur))
    return out


def carte(verbeux: bool = True, blobs: bool = False) -> dict:
    """Rend `{cle_composite: [feuilles]}` pour les composites identifiables. LEVE sur temoin absent."""
    data = _metadata().read_bytes()
    a = ancre(data)
    runs = _runs(data, a)
    res = {int(U.Tile): [int(x) for x in TILE_LEAF_IDS]}
    if blobs:
        print("[blobs] segmentation 0-delimitee autour de l'ancre (0x%x) :" % a)
        for off, r in runs:
            print("[blobs]   0x%-8x n=%-3d %s" % (off, len(r), r))
    for cle, temoins in TEMOINS.items():
        taille = TAILLES_LUES[cle]
        cands = [(off, r) for off, r in runs
                 if len(r) == taille and set(temoins) <= set(r) and len(set(r)) == len(r)]
        if len(cands) != 1:
            raise SystemExit(
                "composite %s(%d) : %d blob(s) de taille %d portant les temoins %s -- "
                "identification IMPOSSIBLE, on ne rend pas une carte devinee"
                % (_nom(cle), cle, len(cands), taille, [_nom(t) for t in temoins]))
        res[cle] = cands[0][1]
    if verbeux:
        print("=== CARTE DE COMPOSITION (blobs LUS dans global-metadata.dat, tailles LUES au "
              "decompile d'`UtilitiesDatabase$$InitializeUtilities`) ===")
        for cle in (int(U.Tile), int(U.Damage), int(U.Repair)):
            f = res[cle]
            print("[carte] %-10s(%2d) n=%-3d %s" % (_nom(cle), cle, len(f),
                                                    [_nom(v) for v in f]))
            if len(f) != TAILLES_LUES[cle]:
                raise SystemExit("taille mesuree %d != taille lue %d pour %s"
                                 % (len(f), TAILLES_LUES[cle], _nom(cle)))
    return res


def ventilation(verbeux: bool = True) -> dict:
    """Les 28 concrets par FACE, croises avec ce que le port monte. Source de la face : l'entree
    VERSIONNEE `data/symbols/<build>/metadata/non_owner_slot4.tsv` (#477-r37)."""
    import probe_477r37_slot4_et_faces_restantes as R
    table = R.lire_tsv()
    import engine.playbook.non_owner as NO
    au_registre = {type(pb).__name__ for pb in NO.NON_OWNER_MOVE_PLAYBOOKS.values()}
    portees = {n for n, v in vars(NO).items()
               if isinstance(v, type) and issubclass(v, NO.TriggeredAbilityNonOwnerPlaybook)
               and hasattr(v, "ABILITY_ID")}
    par_face = {}
    for nom, r in table.items():
        par_face.setdefault(r["face"], []).append(nom)
    if verbeux:
        print()
        print("=== LES %d CONCRETS, PAR FACE ===" % len(table))
        for face in sorted(par_face):
            noms = sorted(par_face[face])
            reg = [n for n in noms if n in au_registre]
            hors = [n for n in noms if n in portees and n not in au_registre]
            manque = [n for n in noms if n not in portees]
            print("[face] %-7s %2d classe(s) : %2d au registre MOVE, %d portee(s) hors registre, "
                  "%2d NON portee(s)" % (face, len(noms), len(reg), len(hors), len(manque)))
            if hors:
                print("[face]     portee(s) hors registre : %s" % ", ".join(hors))
            if manque:
                print("[face]     NON portee(s)           : %s" % ", ".join(manque))
    return par_face


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--blobs", action="store_true", help="imprime la segmentation brute")
    a = ap.parse_args()
    c = carte(blobs=a.blobs)
    par_face = ventilation()
    leaf = int(U.TriggeredAbilitiesNonOwner)
    print()
    print("=== REACHABILITY DES TROIS FACES DE LA FEUILLE %d ===" % leaf)
    for cle, face, porte in ((int(U.Tile), "MOVE", "OUI -- TriggeredAbilitiesNonOwnerUtility.evaluate"),
                             (int(U.Damage), "ATTACK", "NON"),
                             (int(U.Repair), "REPAIR", "NON")):
        dedans = leaf in c[cle]
        print("[reach] composite %-10s(%2d) : feuille %d MEMBRE = %-5s | face %-6s | portee : %s"
              % (_nom(cle), cle, leaf, dedans, face, porte))
    print()
    print("[reach] => les faces ATTACK et REPAIR sont ATTEIGNABLES (ce n'est pas du dead code) et")
    print("[reach]    NON portees : %d classe(s) ATTACK + %d REPAIR."
          % (len(par_face.get("ATTACK", ())), len(par_face.get("REPAIR", ()))))
    print("[reach]    `NoHidingFromTheWatchersNonOwnerPlaybook` (ATTACK) porte `<slot 4> = true` :")
    print("[reach]    l'inscrire sans cette valeur rendrait sa branche ENNEMI inatteignable.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
