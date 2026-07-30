#!/usr/bin/env python3
"""#270 -- regenere les QUATRE recopies Python/SQL de `ActiveAbilityType` depuis le build courant.

Pendant exact de `regen_hook_name_tables.py` (#256), qui a fait le meme travail cote
`frida/hooks/data/*.ts`. Les tables visees ici sont celles que #256 n'a PAS touchees :

  1. `scripts/python/engine/entities/active_ability_type.py`  -- le mirror `IntEnum` ;
  2. `scripts/python/enum_maps.py` (`ACTIVE_ABILITY_TYPE`)    -- id<->nom, LU PAR LE MOTEUR
     (`engine.ai.state_bridge._abilities_of` / `_resolve_ability`) ;
  3. `scripts/sql/006_ref_tables.sql` (`ref_active_ability`)  -- cible de FK de `stream_event` ;
  4. `scripts/sql/013_enum_fk_and_names.sql`                  -- backfill `active_ability_type_name`.

POURQUOI UN REGENERATEUR DE PLUS
--------------------------------
Les deux generateurs historiques (`rl_gen_ref_tables.py`, `rl_gen_enum_columns.py`) lisent
`data/dumps/<hash>/dump.cs` -- artefact Il2CppDumper SUPPRIME le 2026-07-25. Ils ne peuvent donc
plus tourner : la derive n'avait plus de reparateur. Ce script prend la meme source de verite que
tout le reste du depot depuis #104, `data/symbols/<build>/frida/enums.tsv`.

Il ne traite QUE `ActiveAbilityType`. Les autres blocs de ces memes fichiers (`EFFECT_TYPE`,
`PASSIVE_ABILITY_TYPE`, `GROUP_TYPE`, `ref_triggered_ability`, `ref_effect`...) derivent aussi, mais
chacun demande sa propre lecture -- notamment `GROUP_TYPE`, dont 66 ids portent un nom FAUX (un
membre insere en 36 a decale toute la suite). Les reprendre en aveugle ici serait exactement la
faute qu'on corrige.

REGLES DE REGENERATION (identiques a #256)
------------------------------------------
1. Source de verite = `data/symbols/<build>/frida/enums.tsv`.
2. Une valeur peut porter PLUSIEURS noms (`9999` = `STRIPPED` ET `testAssetBundles`) : on GARDE le
   nom deja present s'il appartient toujours a l'ensemble -- ca minimise le diff et respecte les
   choix anterieurs -- sinon on prend le premier par ordre lexicographique (deterministe).
3. Les entrees dont la valeur n'existe plus sont SUPPRIMEES, et listees en sortie.
4. ON NE REECRIT QUE LE BLOC vise ; tete et queue du fichier sont recopiees VERBATIM.
5. Le mirror Python echappe les mots-clefs (`None` -> `None_`) : c'est une contrainte du LANGAGE,
   pas une divergence de nom, et la sonde le sait.

Garde : `python scripts/python/probe_270_active_ability_type_drift.py` doit rendre 0 apres passage.
Aucun rebuild ni reinject : ces fichiers vivent cote Python/SQL, pas dans `frida/hooks/`.

ASCII only (console Windows cp1252).
"""
from __future__ import annotations

import argparse
import keyword
import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "scripts" / "python"))

from symbols_layout import build_dir, current_build  # noqa: E402

CLE = "IdunBattle.Entities.Enum.ActiveAbilityType"

MIRROR = REPO / "scripts" / "python" / "engine" / "entities" / "active_ability_type.py"
MAPS = REPO / "scripts" / "python" / "enum_maps.py"
SQL_REF = REPO / "scripts" / "sql" / "006_ref_tables.sql"
SQL_ENUM = REPO / "scripts" / "sql" / "013_enum_fk_and_names.sql"


def enum_du_jeu(build: str) -> dict[int, set[str]]:
    """-> {valeur: {noms}}. Un ENSEMBLE : plusieurs membres peuvent partager une valeur."""
    p = build_dir(build) / "frida" / "enums.tsv"
    for ligne in p.open(encoding="utf-8"):
        if ligne.startswith(CLE + "\t"):
            out: dict[int, set[str]] = {}
            for paire in ligne.rstrip("\n").split("\t", 1)[1].split(","):
                v, _, n = paire.partition("=")
                if n:
                    try:
                        out.setdefault(int(v), set()).add(n)
                    except ValueError:
                        pass
            return out
    raise SystemExit("cle absente de enums.tsv : %s" % CLE)


def ident(nom: str) -> str:
    """Nom de membre Python. `None` est un mot-clef -> `None_` (echappement DEJA en place)."""
    return nom + "_" if keyword.iskeyword(nom) else nom


def desechappe(nom: str) -> str:
    return nom[:-1] if nom.endswith("_") and keyword.iskeyword(nom[:-1]) else nom


def sql_quote(s: str) -> str:
    return s.replace("'", "''")


def choisir(jeu: dict[int, set[str]], ancien: dict[int, str]) -> dict[int, str]:
    """Regle 2 : garder le nom existant s'il est TOUJOURS valide pour cette valeur."""
    return {v: (ancien[v] if ancien.get(v) in noms else sorted(noms)[0])
            for v, noms in jeu.items()}


def rapport(label: str, ancien: dict[int, str], choisi: dict[int, str]) -> None:
    supprimes = sorted(k for k in ancien if k not in choisi)
    ajoutes = sorted(k for k in choisi if k not in ancien)
    renommes = sorted(k for k in choisi if k in ancien and ancien[k] != choisi[k])
    print("  %-44s %d -> %d entrees" % (label, len(ancien), len(choisi)))
    print("      supprimees=%-4d ajoutees=%-4d renommees=%d"
          % (len(supprimes), len(ajoutes), len(renommes)))
    for v in renommes[:8]:
        print("        %6d : '%s' -> '%s'" % (v, ancien[v], choisi[v]))
    if ajoutes:
        print("      ids AJOUTES (le jeu les porte) : %s"
              % ", ".join("%d=%s" % (v, choisi[v]) for v in ajoutes))
    if supprimes:
        apercu = ", ".join("%d:%s" % (v, ancien[v]) for v in supprimes[:5])
        print("      ids disparus de l'enum (retires) : %s%s"
              % (apercu, " ..." if len(supprimes) > 5 else ""))


# --------------------------------------------------------------------------- 1. le mirror

def rends_mirror(jeu: dict[int, set[str]], build: str, ecrire: bool) -> None:
    brut = MIRROR.read_text(encoding="utf-8")
    deb = brut.find("class ActiveAbilityType(IntEnum):")
    if deb < 0:
        raise SystemExit("classe ActiveAbilityType introuvable dans le mirror")
    ancien = {int(m.group(2)): desechappe(m.group(1))
              for m in re.finditer(r"^\s{4}([A-Za-z_]\w*)\s*=\s*(-?\d+)\s*$", brut[deb:], re.M)}
    choisi = choisir(jeu, ancien)
    rapport("mirror  engine/entities/active_ability_type.py", ancien, choisi)

    tete = (
        '"""engine.entities.ActiveAbilityType -- enum natif `ActiveAbilityType` (mirror 1:1 complet).\n'
        "\n"
        "GENERE : `python scripts/python/regen_active_ability_tables.py --ecrire`.\n"
        "Source : `data/symbols/%s/frida/enums.tsv` -- `%s`.\n"
        "REGENERER A CHAQUE CHANGEMENT DE BUILD : le jeu AJOUTE et RETIRE des membres (mesure #270 sur\n"
        "`gqfc5mff6c` -> `rnca9r7q6c` : 75 ids historiques Idun retires, 4 ajoutes). Un membre garde ici\n"
        "alors que le jeu l'a retire est INERTE (le jeu ne l'emet jamais) ; un membre du jeu ABSENT ici\n"
        "DEGRADE EN SILENCE -- `engine.ai.state_bridge._abilities_of` ignore une active dont le nom\n"
        "n'est pas dans l'enum, et l'ability disparait de l'unite offline.\n"
        "\n"
        "Valeur == id natif. ATTENTION : le MEME id peut appartenir a des enums DIFFERENTS selon le\n"
        "contexte (ex. 1017 = `EffectType.ActOfFaith` ET `UnitTrait.BigTarget`) -> chaque site de\n"
        "conversion verifie l'enum correct. Le meme piege existe sur les NOMS : `DanceOfDaggers` est\n"
        "mort dans cet enum et VIVANT dans `IdunBattle.Configuration.UtilityType` (49).\n"
        "\n"
        "Garde : `python scripts/python/probe_270_active_ability_type_drift.py`.\n"
        '"""\n'
        "from __future__ import annotations\n"
        "\n"
        "from enum import IntEnum\n"
        "\n"
        "\n"
        % (build, CLE))
    corps = [
        "class ActiveAbilityType(IntEnum):",
        '    """Mirror 1:1 de `%s` (%d membres). Valeur == id natif."""' % (CLE, len(choisi)),
    ]
    corps += ["    %s = %d" % (ident(choisi[v]), v) for v in sorted(choisi)]
    texte = tete + "\n".join(corps) + "\n"
    if ecrire:
        MIRROR.write_text(texte, encoding="utf-8")


# --------------------------------------------------------------------------- 2. enum_maps

def rends_maps(jeu: dict[int, set[str]], build: str, ecrire: bool) -> None:
    brut = MAPS.read_text(encoding="utf-8")
    deb = brut.find("ACTIVE_ABILITY_TYPE = {")
    if deb < 0:
        raise SystemExit("bloc ACTIVE_ABILITY_TYPE introuvable dans enum_maps.py")
    # Le commentaire `# active_ability_type <- enum ...` qui precede fait partie du bloc.
    tete_deb = brut.rfind("\n# active_ability_type <- ", 0, deb)
    tete_deb = tete_deb + 1 if tete_deb >= 0 else deb
    fin = brut.find("\n}", deb)
    if fin < 0:
        raise SystemExit("bloc ACTIVE_ABILITY_TYPE non delimite")
    fin += len("\n}")
    ancien = {int(m.group(1)): m.group(2)
              for m in re.finditer(r"^\s*(-?\d+):\s*'([^']*)'", brut[deb:fin], re.M)}
    choisi = choisir(jeu, ancien)
    rapport("maps    enum_maps.ACTIVE_ABILITY_TYPE", ancien, choisi)

    bloc = ["# active_ability_type <- enum ActiveAbilityType (%d membres)" % len(choisi),
            "# GENERE par regen_active_ability_tables.py depuis data/symbols/%s/frida/enums.tsv."
            % build,
            "ACTIVE_ABILITY_TYPE = {"]
    bloc += ["    %d: %r," % (v, choisi[v]) for v in sorted(choisi)]
    bloc.append("}")
    texte = brut[:tete_deb] + "\n".join(bloc) + brut[fin:]
    if ecrire:
        MAPS.write_text(texte, encoding="utf-8")


# --------------------------------------------------------------------------- 3. SQL 006

def rends_sql_ref(jeu: dict[int, set[str]], build: str, ecrire: bool) -> None:
    brut = SQL_REF.read_text(encoding="utf-8")
    marque = "INSERT INTO tacticus.ref_active_ability (ability_id, name) VALUES\n"
    deb = brut.find(marque)
    if deb < 0:
        raise SystemExit("INSERT ref_active_ability introuvable dans 006")
    fin = brut.find(";", deb)
    if fin < 0:
        raise SystemExit("INSERT ref_active_ability non termine")
    fin += 1
    ancien = {int(m.group(1)): m.group(2).replace("''", "'")
              for m in re.finditer(r"\((-?\d+),\s*'((?:[^']|'')*)'\)", brut[deb:fin])}
    choisi = choisir(jeu, ancien)
    rapport("sql     006 ref_active_ability", ancien, choisi)

    ids = sorted(choisi)
    lignes = ["  (%d, '%s')" % (v, sql_quote(choisi[v])) for v in ids]
    bloc = (marque + ",\n".join(lignes)
            + " ON CONFLICT (ability_id) DO UPDATE SET name = EXCLUDED.name;")
    texte = brut[:deb] + bloc + brut[fin:]
    if ecrire:
        SQL_REF.write_text(texte, encoding="utf-8")


# --------------------------------------------------------------------------- 4. SQL 013

def rends_sql_backfill(jeu: dict[int, set[str]], build: str, ecrire: bool) -> None:
    brut = SQL_ENUM.read_text(encoding="utf-8")
    marque = "UPDATE tacticus.stream_event se SET active_ability_type_name = m.name\n"
    deb = brut.find(marque)
    if deb < 0:
        raise SystemExit("backfill active_ability_type_name introuvable dans 013")
    fin = brut.find("\n  ) AS m(id, name)", deb)
    if fin < 0:
        raise SystemExit("backfill active_ability_type_name non delimite")
    ancien = {int(m.group(1)): m.group(2).replace("''", "'")
              for m in re.finditer(r"\((-?\d+),\s*'((?:[^']|'')*)'\)", brut[deb:fin])}
    choisi = choisir(jeu, ancien)
    rapport("sql     013 backfill active_ability_type_name", ancien, choisi)

    vals = ",\n  ".join("(%d, '%s')" % (v, sql_quote(choisi[v])) for v in sorted(choisi))
    bloc = marque + "  FROM (VALUES\n  " + vals
    texte = brut[:deb] + bloc + brut[fin:]
    if ecrire:
        SQL_ENUM.write_text(texte, encoding="utf-8")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--build", default=None, help="defaut : data/symbols/CURRENT")
    ap.add_argument("--ecrire", action="store_true",
                    help="ecrit les fichiers ; sans ce drapeau, simule et n'ecrit RIEN")
    args = ap.parse_args()

    build = args.build or current_build()
    jeu = enum_du_jeu(build)
    print("build  : %s   (%d valeurs / %d noms)"
          % (build, len(jeu), sum(len(s) for s in jeu.values())))
    print("mode   : %s" % ("ECRITURE" if args.ecrire else "SIMULATION (rien n'est ecrit)"))
    print("")
    rends_mirror(jeu, build, args.ecrire)
    print("")
    rends_maps(jeu, build, args.ecrire)
    print("")
    rends_sql_ref(jeu, build, args.ecrire)
    print("")
    rends_sql_backfill(jeu, build, args.ecrire)
    print("")
    print("---")
    if args.ecrire:
        print("Verifier : python scripts/python/probe_270_active_ability_type_drift.py")
        print("Les migrations SQL sont IDEMPOTENTES (upsert / update) : retirer une ligne du fichier")
        print("ne SUPPRIME rien en base, ca cesse seulement de la reinserer.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
