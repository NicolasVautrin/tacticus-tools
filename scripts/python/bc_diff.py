"""Confronter une BC FABRIQUEE a une BC CAPTUREE, VALEUR par VALEUR -- pas cle par cle.

    python scripts/python/bc_diff.py <fabriquee.json> <capturee.json>

POURQUOI CE PROBE EXISTE
------------------------
Le controle precedent comparait le JEU DE CLES RACINE (34 contre 34) et rendait
<< ecart nul >>. Une egalite de FORME, muette sur les VALEURS : c'est ainsi qu'un
`SpawnPointTag` a `"0"` la ou le jeu ecrit `"defaultGroup"` a survecu trois niveaux plus bas
(mesure du 2026-08-16). Un controle qui compare des cles ne peut pas accuser un contenu.

CE QU'IL NE FAUT PAS FAIRE, ET POURQUOI
---------------------------------------
Un diff BRUT est inutilisable ici : les deux BC sont deux batailles DIFFERENTES (autre board,
autres unites, autres vagues), donc des milliers d'ecarts LEGITIMES noieraient le seul qui
compte. On ne compare donc pas les CONTENUS -- on compare la FORME QU'ILS PRENNENT :

  * un chemin present chez le jeu et ABSENT chez nous            -> le jeu attend, on ne donne pas
  * un chemin NON NUL chez le jeu et NUL chez nous               -> idem, en plus discret
  * une liste/dict NON VIDE chez le jeu et VIDE chez nous        -> idem
  * un TYPE qui diverge (str vs int, list vs dict)               -> le natif lira de travers

C'est la classe << le jeu attend quelque chose qu'on ne fournit pas >>, seule capable de faire
lever le natif. L'inverse (present chez nous, absent chez lui) est rendu a part : moins
dangereux, mais un champ qu'on invente est un champ qu'on n'a pas mesure.

(!) Les listes sont comparees par leur PREMIER element quand elles en ont un des deux cotes :
comparer element par element sur des listes de longueurs differentes n'apprend rien, et le
gabarit d'un element est ce qui porte la forme. On DIT combien d'elements sont ignores.

ASCII only en sortie (console Windows cp1252).
"""
import json
import sys
from pathlib import Path

RACINE = Path(__file__).resolve().parents[2]

# Les sous-arbres dont le CONTENU est massif et propre a la bataille : on garde la
# comparaison de forme mais on n'y descend pas element par element.
VOLUMINEUX = ("/Board/Tiles", "/Units", "/Abilities")


def genre(v):
    if v is None:
        return "nul"
    if isinstance(v, bool):
        return "bool"
    if isinstance(v, (int, float)):
        return "nombre"
    if isinstance(v, str):
        return "texte"
    if isinstance(v, list):
        return "liste"
    if isinstance(v, dict):
        return "dict"
    return type(v).__name__


def vide(v):
    return v is None or (isinstance(v, (list, dict, str)) and len(v) == 0)


def parcourir(a, b, chemin="", ecarts=None, ignores=None, prof=0):
    """`a` = capturee (la VERITE), `b` = fabriquee. Remplit `ecarts`."""
    if ecarts is None:
        ecarts, ignores = [], []
    if prof > 12:
        return ecarts, ignores

    ga, gb = genre(a), genre(b)
    if ga != gb:
        ecarts.append(("TYPE", chemin, ga, gb))
        return ecarts, ignores

    if ga == "dict":
        for k in sorted(a):
            sous = chemin + "/" + str(k)
            if k not in b:
                ecarts.append(("ABSENT", sous, "%s" % genre(a[k]), "-"))
                continue
            parcourir(a[k], b[k], sous, ecarts, ignores, prof + 1)
        for k in sorted(b):
            if k not in a:
                ecarts.append(("EN TROP", chemin + "/" + str(k), "-", genre(b[k])))
        return ecarts, ignores

    if ga == "liste":
        if a and not b:
            ecarts.append(("VIDE CHEZ NOUS", chemin, "%d element(s)" % len(a), "0"))
            return ecarts, ignores
        if chemin.startswith(VOLUMINEUX):
            ignores.append((chemin, len(a), len(b)))
            # on compare quand meme le GABARIT du premier element
            if a and b:
                parcourir(a[0], b[0], chemin + "[0]", ecarts, ignores, prof + 1)
            return ecarts, ignores
        if a and b:
            parcourir(a[0], b[0], chemin + "[0]", ecarts, ignores, prof + 1)
        if len(a) != len(b):
            ignores.append((chemin, len(a), len(b)))
        return ecarts, ignores

    # feuille : on n'accuse QUE le vide-chez-nous, jamais une valeur differente
    if not vide(a) and vide(b):
        ecarts.append(("VIDE CHEZ NOUS", chemin, json.dumps(a)[:60], json.dumps(b)[:30]))
    return ecarts, ignores


def charger_enum(build, nom_plein):
    """`data/symbols/<build>/frida/enums.tsv` -> {ordinal: nom}. Rend None si absent.

    (!) C'est la table du BUILD, pas un mirror Python : un mirror perime nommerait faux, et
    ici un nom faux se lit comme une ability MANQUANTE -- exactement le defaut qu'on cherche."""
    p = RACINE / "data" / "symbols" / build / "frida" / "enums.tsv"
    if not p.exists():
        return None
    for ligne in p.read_text(encoding="utf-8", errors="replace").split("\n"):
        c = ligne.split("\t")
        if len(c) < 2 or c[0] != nom_plein:
            continue
        out = {}
        for couple in c[1].split(","):
            if "=" not in couple:
                continue
            k, v = couple.split("=", 1)
            try:
                out[int(k)] = v
            except ValueError:
                pass
        return out
    return None


def unites_qui_entrent(bc):
    """Les `UnitId` qui ARRIVENT VRAIMENT sur le plateau -- pas les 80 gabarits.

    Deux sources, et il faut les DEUX : `PredefinedUnits` (l'equipe posee au depart) et les
    `ToSpawn` des vagues.

    (!) ON NE DEPOUILLE PAS LE SUFFIXE DE RANG. Un `UnitId` de vague s'ecrit
    `tyranNpc4Warrior:29`, et le gabarit correspondant de `Units` porte le MEME `Id`, suffixe
    compris -- ce sont deux gabarits distincts (`:1` et `:29` coexistent). Retirer le `:29`
    avant de comparer a fait accuser 4 gabarits MANQUANTS le 2026-08-16, alors qu'ils etaient
    la, et que la BC CAPTUREE -- celle qui marche -- les nomme exactement pareil. Un probe qui
    normalise une cle avant de la chercher fabrique ses propres absences."""
    ids = set()
    for bloc in (bc.get("PredefinedUnits") or []):
        for u in (bloc.get("Units") or []):
            if u.get("UnitId"):
                ids.add(str(u["UnitId"]))
    tiers = (bc.get("UnitSpawningOverTime") or {}).get("Tiers") or {}
    for niveau in tiers.values():
        for entree in niveau.values():
            for u in (entree.get("ToSpawn") or []):
                if u.get("UnitId"):
                    ids.add(str(u["UnitId"]))
    return ids


def coherence(chemin_bc, build):
    """Chaque ability REFERENCEE par une unite qui entre a-t-elle sa CONFIG dans la BC ?

    C'est le verrou #237 : une ability sans config leve << system error >> AU CAST -- donc
    tard, et seulement si l'unite s'en sert. Un montage peut tourner plusieurs vagues avant
    de le rencontrer. Ce controle est OFFLINE et ne coute rien ; il n'y a aucune raison de
    decouvrir ca en jeu."""
    bc = json.loads(Path(chemin_bc).read_text(encoding="utf-8"))
    actifs = charger_enum(build, "IdunBattle.Entities.Enum.ActiveAbilityType")
    passifs = charger_enum(build, "IdunBattle.Entities.Enum.TriggeredAbilityType")
    if actifs is None or passifs is None:
        print("REFUS : table d'enums du build `%s` INTROUVABLE -- on ne devine pas un nom "
              "d'ability, un nom faux se lirait comme une config manquante." % build)
        return 2
    print("enums du build %s : ActiveAbilityType=%d, TriggeredAbilityType=%d"
          % (build, len(actifs), len(passifs)))

    entrent = unites_qui_entrent(bc)
    gabarits = {u.get("Id"): u for u in (bc.get("Units") or [])}
    print("%d unite(s) entrent vraiment (sur %d gabarits)" % (len(entrent), len(gabarits)))
    sans_gabarit = sorted(x for x in entrent if x not in gabarits)
    if sans_gabarit:
        print("  (!) %d unite(s) a poser SANS gabarit dans `Units` : %s"
              % (len(sans_gabarit), ", ".join(sans_gabarit[:8])))
    print()

    cfg = bc.get("Abilities") or {}
    manques, total = [], 0
    for uid in sorted(entrent):
        u = gabarits.get(uid)
        if not u:
            continue
        lots = [("ActiveAbilities", u.get("ActiveAbilities") or [], actifs, "ActiveAbilities"),
                ("PassiveAbilities", u.get("PassiveAbilities") or [], passifs, "PassiveAbilities")]
        if u.get("TertiaryAbility"):
            lots.append(("TertiaryAbility", [u["TertiaryAbility"]], passifs, "PassiveAbilities"))
        for champ, ids, table, categorie in lots:
            for i in ids:
                total += 1
                if not isinstance(i, int):
                    continue
                nom = table.get(i)
                if nom is None:
                    manques.append((uid, champ, i, "ORDINAL INCONNU DE L'ENUM", ""))
                    continue
                if nom not in (cfg.get(categorie) or {}):
                    manques.append((uid, champ, i, nom, "config ABSENTE de Abilities.%s" % categorie))

    print("=== %d reference(s) d'ability verifiee(s) ===" % total)
    if not manques:
        print("  aucune manquante -- la BC est AUTO-COHERENTE sur cet axe.")
        print("  (!) ca ne dit rien des VALEURS a l'interieur d'une config, seulement de sa presence.")
        return 0
    print("=== %d MANQUANTE(S) -- chacune leverait << system error >> au cast ===" % len(manques))
    for uid, champ, i, nom, quoi in manques:
        print("   %-26s %-18s %-6s %-32s %s" % (uid, champ, i, nom, quoi))
    return 1


def main(argv):
    if argv and argv[0] == "--coherence":
        if len(argv) < 2:
            print("usage : bc_diff.py --coherence <bc.json> [build]")
            return 2
        build = argv[2] if len(argv) > 2 else (
            RACINE / "data" / "symbols" / "CURRENT").read_text(encoding="utf-8").strip()
        return coherence(argv[1], build)
    if len(argv) < 2:
        print(__doc__)
        return 2
    mien = json.loads(Path(argv[0]).read_text(encoding="utf-8"))
    vrai = json.loads(Path(argv[1]).read_text(encoding="utf-8"))
    print("fabriquee : %s (%d cles racine)" % (Path(argv[0]).name, len(mien)))
    print("capturee  : %s (%d cles racine)" % (Path(argv[1]).name, len(vrai)))
    print("  (!) ce sont DEUX batailles differentes -- on compare la FORME, pas le contenu")
    print()

    ecarts, ignores = parcourir(vrai, mien)

    par_classe = {}
    for c, ch, x, y in ecarts:
        par_classe.setdefault(c, []).append((ch, x, y))

    ordre = ["ABSENT", "VIDE CHEZ NOUS", "TYPE", "EN TROP"]
    for c in ordre:
        lot = par_classe.get(c) or []
        titre = {
            "ABSENT": "le jeu le porte, NOUS PAS -- classe la plus dangereuse",
            "VIDE CHEZ NOUS": "non nul chez le jeu, VIDE ou NUL chez nous",
            "TYPE": "le TYPE diverge -- le natif lira de travers",
            "EN TROP": "present chez nous seulement (moins grave, mais non mesure)",
        }[c]
        print("=== %s : %d -- %s ===" % (c, len(lot), titre))
        for ch, x, y in lot[:40]:
            print("   %-58s jeu=%-22s nous=%s" % (ch[:58], str(x)[:22], y))
        if len(lot) > 40:
            print("   ... %d de plus" % (len(lot) - 40))
        print()

    print("=== longueurs de listes NON comparees element par element (%d) ===" % len(ignores))
    for ch, na, nb in ignores[:25]:
        marque = "  <<< on en a MOINS" if nb < na else ""
        print("   %-58s jeu=%-6d nous=%-6d%s" % (ch[:58], na, nb, marque))
    if len(ignores) > 25:
        print("   ... %d de plus" % (len(ignores) - 25))

    dangereux = len(par_classe.get("ABSENT") or []) + len(par_classe.get("VIDE CHEZ NOUS") or []) \
        + len(par_classe.get("TYPE") or [])
    print()
    print("BILAN : %d ecart(s) de la classe << le jeu attend, on ne fournit pas >>" % dangereux)
    return 1 if dangereux else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
