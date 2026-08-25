"""INVENTORIER l'inbox, et REFUSER de reclamer ce qui contient de la STAMINA.

    python scripts/python/inbox_reclamer.py                    # inventaire, ne reclame RIEN
    python scripts/python/inbox_reclamer.py --reclamer FOXRAIDS

⛔ REFUS N.1 -- LA STAMINA. Toute entree dont les recompenses contiennent `stamina` est
REFUSEE. La stamina se regenere et se PLAFONNE : la reclamer trop tot en jette une partie, et
c'est une decision de JOUEUR, pas d'outil. La consigne existait en prose le 2026-08-25 ; la
prose n'arrete pas un comportement, donc elle est ici EXECUTABLE.
Echappatoire nommee : `--stamina-je-sais`, qui doit etre tapee a la main.

⛔ REFUS N.2 -- LE MARSHALLING. `ViewCommandExecutor$$ClaimInboxItem` prend un
`thor.UserProgress.Data.InboxItemGUID`, qui est un TYPE VALEUR a un seul champ :

    thor.UserProgress.Data.InboxItemGUID
        +0x10  _value   String          (offset dans la forme BOXEE)

`il2cpp_runtime_invoke` attend, pour un type valeur, un pointeur vers la VALEUR BRUTE -- donc
un pointeur vers les 8 octets qui portent eux-memes le pointeur de chaine. Or `argIl2cpp`
(fsm-input.ts), sur une chaine, rend le pointeur de l'OBJET chaine : une indirection de MOINS.
Passer la chaine telle quelle ferait lire au natif l'en-tete de l'objet comme si c'etait le
champ `_value`.

⚠ ET SE TROMPER DE CONVENTION SUR UN TYPE VALEUR NE LEVE PAS -- CA CRASHE LE JEU. C'est deja
arrive le 2026-08-21 sur `AbilitiesConfigurations`, dont la cle est aussi un type valeur.
Tant que la forme `{brut, octets}` n'a pas ete ETABLIE pour ce type (et non devinee), ce
script REFUSE d'invoquer. Reclamer dans l'UI coute deux clics et ne risque rien.

ASCII only en sortie (console Windows cp1252).
"""
import argparse
import json
import pathlib
import sys

PROG = pathlib.Path(r"C:\Users\nicolasv\AppData\LocalLow\Snowprint"
                    r"\Warhammer 40,000_ Tacticus\user_progression.json")
INTERDIT = "stamina"


def entrees():
    """Les entrees d'inbox. Rend `None` si la source n'est pas LUE -- jamais une liste vide,
    qui se lirait comme << inbox vide >>."""
    try:
        d = json.loads(PROG.read_text(encoding="utf-8"))
    except Exception as e:
        print("NON MESURE : progression illisible -- %s" % e)
        return None
    return (d.get("inbox") or {}).get("inboxItems") or []


def stamina_de(it):
    return sum(r.get("amount", 0) for r in (it.get("rewards") or [])
               if r.get("id") == INTERDIT)


def libelle(it):
    return it.get("code") or it.get("titleKey") or it.get("type") or it.get("id")


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--reclamer", metavar="CODE_OU_ID",
                    help="l'entree a reclamer (son `code`, ou son `id` GUID)")
    ap.add_argument("--stamina-je-sais", dest="stamina_ok", action="store_true",
                    help="echappatoire NOMMEE au refus n.1 -- ne leve PAS le refus n.2")
    a = ap.parse_args()

    inb = entrees()
    if inb is None:
        return 2

    non_reclamees = [it for it in inb if not it.get("claimed")]
    print("inbox : %d entree(s), %d NON reclamee(s)" % (len(inb), len(non_reclamees)))
    print()
    print("%-30s %-9s %s" % ("entree", "stamina", "le reste"))
    print("-" * 78)
    total = {}
    for it in non_reclamees:
        st = stamina_de(it)
        autres = [(r.get("id"), r.get("amount")) for r in (it.get("rewards") or [])
                  if r.get("id") != INTERDIT]
        for cle, n in autres:
            total[cle] = total.get(cle, 0) + n
        total[INTERDIT] = total.get(INTERDIT, 0) + st
        print("%-30s %-9s %s" % (str(libelle(it))[:30], st or "-", autres or "RIEN D AUTRE"))
    print()
    print("TOTAL non reclame : %s" % ", ".join("%s %d" % (k, v)
                                               for k, v in sorted(total.items())))

    if not a.reclamer:
        print()
        print("(inventaire seul -- rien n'a ete reclame)")
        return 0

    vise = [it for it in non_reclamees
            if a.reclamer in (it.get("code"), it.get("id"))]
    if not vise:
        print()
        print("REFUS : aucune entree NON RECLAMEE ne porte le code/id %r." % a.reclamer)
        return 2
    it = vise[0]
    st = stamina_de(it)

    print()
    if st > 0 and not a.stamina_ok:
        print("REFUS -- %r porte %d STAMINA." % (libelle(it), st))
        print("        La stamina PLAFONNE : la reclamer trop tot en jette une part, et")
        print("        c'est une decision de joueur. Echappatoire : --stamina-je-sais.")
        return 2

    print("REFUS -- l'invocation de `ClaimInboxItem` n'est PAS ETABLIE sur ce build.")
    print("        Son argument est un TYPE VALEUR (`InboxItemGUID`, champ `_value:String`),")
    print("        et `argIl2cpp` rendrait le pointeur de la CHAINE la ou le natif attend un")
    print("        pointeur vers la STRUCT -- une indirection d'ecart. Se tromper de")
    print("        convention sur un type valeur NE LEVE PAS : ca CRASHE le jeu.")
    print("        Reclamer dans l'UI ne risque rien. Entree visee : %s" % it.get("id"))
    return 3


if __name__ == "__main__":
    sys.exit(main())
