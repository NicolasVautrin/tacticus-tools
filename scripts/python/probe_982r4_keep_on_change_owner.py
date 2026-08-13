"""`#982-r4` -- QUELLES classes d'effet ne SURVIVENT PAS au changement de proprietaire.

    python probe_982r4_keep_on_change_owner.py            # derivation OFFLINE complete
    python probe_982r4_keep_on_change_owner.py --runtime   # + 2e source, la vtable LIVE

## La question

`IdunBattle.Operations.ChangeUnitOwnerOperation$$RemoveEffects` met un effet dans la liste de
SUPPRESSION quand `IEffect` **slot 3** rend **FAUX** (noter le sens du test). Le nom du slot est
VERSIONNE (`data/symbols/<build>/metadata/interface_slots.tsv` -> `IEffect 3
get_KeepOnChangeOwner`) ; restait la VALEUR, classe par classe.

## Pourquoi PAS la vtable runtime

`probe_916r1_effect_slots.py` la lit, et c'est une source VALABLE -- mais **partielle par
construction** : IL2CPP ne remplit la vtable d'une classe qu'a son INITIALISATION. Mesure du
2026-08-13 sur une session ou aucun taunt n'avait ete pose : **53 classes mesurees sur 465**, et le
verdict rendu est << AUCUN override >>. C'est un **faux zero** -- exactement le mode de panne que
le probe lui-meme documente, et il aurait fait conclure << rien a purger >>.

## La derivation retenue -- offline, complete, sans session

Elle reutilise TELLE QUELLE la machinerie de `probe_175r2_can_be_immune_to.py`, qui repond a la
MEME forme de question pour `get_CanBeImmuneTo` (slot d'`IEffect`, getter constant, corps
DEDUPLIQUE par IL2CPP) :

  * **QUI DECLARE** : la table des methodes du type dans le `global-metadata.dat`. C'est la seule
    source qui distingue << la classe surcharge >> de << le corps est partage >>. `methods.tsv`,
    indexee par ADRESSE, n'en garde qu'UN proprietaire et ne peut donc rien prouver par l'absence.
  * **QUELLE VALEUR** : les OCTETS du corps, retrouves par calage du bloc `methodPointers` --
    `b0 01 c3` (`mov al,1 ; ret`) = VRAI, `32 c0 c3` (`xor al,al ; ret`) = FAUX. Le NOM que ghidra
    donne a ces corps designe un proprietaire ARBITRAIRE (mesure : le `true` s'appelle
    `UnityEngine.U2D.IK.Solver2D$$DoValidate`) -- seuls les octets comptent.

Le seul parametre qui change entre les deux probes est le NOM DU GETTER : ce module se contente
donc de le poser et d'appeler `deriver()`. Il n'ECRIT AUCUNE entree versionnee (le domaine tient en
deux classes, et il est fige par `tests/engine/test_982r4_keep_on_change_owner_offline.py`).

ASCII only (console cp1252).
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

import probe_175r2_can_be_immune_to as P175                              # noqa: E402

#: Le getter en cause, LU dans `data/symbols/<build>/metadata/interface_slots.tsv` (`IEffect 3`),
#: jamais ecrit de memoire.
GETTER = "get_KeepOnChangeOwner"
#: Les DEUX corps constants possibles, par leurs OCTETS.
CORPS = {"b0 01 c3": True, "32 c0 c3": False}


def deriver() -> dict | None:
    """`{classe: {declare, valeur_propre, valeur_effective, corps, ...}}` sur la fermeture
    transitive de `BaseEffect`, ou `None` si une etape a REFUSE de conclure.

    ⚠ On REPOSITIONNE le getter du module reutilise, et on le REMET ensuite : `probe_175r2` est un
    module partage, le laisser dans un etat modifie ferait mesurer le mauvais slot au prochain
    appelant du meme process."""
    ancien = P175.GETTER
    try:
        P175.GETTER = GETTER
        return P175.deriver()
    finally:
        P175.GETTER = ancien


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--runtime", action="store_true",
                    help="croise avec la VTABLE live (PARTIELLE : classes deja initialisees)")
    a = ap.parse_args()

    print("== #982-r4 -- `IEffect` slot 3 `%s`, par classe d'effet" % GETTER)
    table = deriver()
    if table is None:
        print("REFUS : la derivation offline n'a pas pu conclure (rien n'est devine).")
        return 2

    faux = sorted(k for k, v in table.items() if v.get("valeur_effective") is False)
    vrai = [k for k, v in table.items() if v.get("valeur_effective") is True]
    inconnu = sorted(k for k, v in table.items() if v.get("valeur_effective") is None)
    declarants = sorted(k for k, v in table.items() if v.get("declare"))

    print("")
    print("   classes couvertes : %d   (FAUX %d | VRAI %d | INCONNU %d)"
          % (len(table), len(faux), len(vrai), len(inconnu)))
    print("   DECLARANTS (la seule source qui distingue surcharge et corps partage) : %d"
          % len(declarants))
    for k in declarants:
        v = table[k]
        print("      %-64s propre=%-5s corps=%s" % (k, v.get("valeur_propre"), v.get("corps")))
    print("")
    print("   NE SURVIVENT PAS au changement de proprietaire (le natif les PURGE) :")
    for k in faux:
        print("      %s" % k)
    if inconnu:
        print("")
        print("   %d classe(s) INCONNUE(S) -- aucune valeur n'est devinee pour elles :" % len(inconnu))
        for k in inconnu[:20]:
            print("      %s" % k)

    if a.runtime:
        print("")
        print("=== 2e source : la VTABLE LIVE (PARTIELLE par construction) ===")
        vals, refus = P175.runtime(sorted(table))
        print("   mesurees : %d ; NON mesurees (classe non initialisee) : %d"
              % (len(vals), len(refus)))
        divergent = [(k, vals[k], table[k].get("valeur_effective"))
                     for k in vals if vals[k] != table[k].get("valeur_effective")]
        if divergent:
            print("   DIVERGENCES offline/runtime (a trancher, rien n'est rabattu) :")
            for k, r, o in divergent:
                print("      %-64s runtime=%s offline=%s" % (k, r, o))
            return 1
        print("   les deux sources CONCORDENT sur les %d classes mesurees." % len(vals))

    return 0 if not inconnu else 1


if __name__ == "__main__":
    sys.exit(main())
