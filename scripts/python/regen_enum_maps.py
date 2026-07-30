#!/usr/bin/env python3
"""#275 -- regenere les SIX tables de `scripts/python/enum_maps.py` depuis le build courant.

Pendant exact de `regen_active_ability_tables.py` (#270/#276), qui a fait le meme travail pour le
SEUL bloc `ACTIVE_ABILITY_TYPE` (et ses recopies SQL). Ce script prend les six blocs du fichier :

  | bloc Python            | enum natif                                    | consommateur           |
  |------------------------|-----------------------------------------------|------------------------|
  | `EFFECT_TYPE`          | `IdunBattle.Entities.Enum.EffectType`         | `BY_COLUMN` (ingest),  |
  |                        |                                               | `audit_passive_*`      |
  | `ACTIVE_ABILITY_TYPE`  | `...Enum.ActiveAbilityType`                   | `state_bridge`, audits |
  | `PASSIVE_ABILITY_TYPE` | `...Enum.TriggeredAbilityType`                | `BY_COLUMN`, audits    |
  | `DAMAGE_PROFILE_TYPE`  | `...Enum.DamageProfileType`                   | `BY_COLUMN`            |
  | `UNIT_SPAWN_SOURCE`    | `...Enum.SpawnSource`                         | `BY_COLUMN`            |
  | `GROUP_TYPE`           | `IdunBattle.Streams.GroupType`                | plus AUCUN (cf. infra) |

Le nom du bloc NE SUIT PAS celui de l'enum (`PASSIVE_ABILITY_TYPE` <- `TriggeredAbilityType`,
`UNIT_SPAWN_SOURCE` <- `SpawnSource`) et `GroupType` vit dans un AUTRE namespace. Les appariements
ci-dessus sont LUS dans `enums.tsv`, pas deduits du nom -- un appariement au juge produirait un
diff massif et FAUX.

POURQUOI UN REGENERATEUR DE PLUS
--------------------------------
Le generateur historique `rl_gen_enum_columns.py` lit `data/dumps/<hash>/dump.cs` -- artefact
Il2CppDumper gitignore et SUPPRIME le 2026-07-25. Il ne peut donc plus tourner : la derive
n'avait plus de reparateur, exactement la cause racine de #270. Ce script lit
`data/symbols/<build>/frida/enums.tsv`, VERSIONNEE, donc presente dans TOUT checkout.

`GROUP_TYPE` N'A PLUS DE CONSOMMATEUR, ET ON LE REGENERE QUAND MEME
-------------------------------------------------------------------
`rl_collect_batch._group_name` resout desormais par NOM contre `stream_events` (#254b-b) ; plus
aucun code ne lit `enum_maps.GROUP_TYPE`. Le laisser faux serait pourtant le pire des deux mondes :
une table que rien ne garde, qu'un humain lit comme une reference, et qui a DEJA menti en base
(2 099 lignes de `stream_group.group_name`, cf. `docs/rl/case-275-enum-maps-drift.md`). Une table
qu'on garde est une table qu'on regenere.

REGLES DE REGENERATION (identiques a #256/#270)
-----------------------------------------------
1. Source de verite = `data/symbols/<build>/frida/enums.tsv`.
2. Une valeur peut porter PLUSIEURS noms : on GARDE le nom deja present s'il appartient toujours
   a l'ensemble (diff minimal, choix anterieurs respectes), sinon le premier par ordre
   lexicographique (deterministe).
3. Les entrees dont la valeur n'existe plus sont SUPPRIMEES, et listees en sortie.
4. ON NE REECRIT QUE LES BLOCS vises + l'en-tete du fichier ; `BY_COLUMN` et tout le reste sont
   recopies VERBATIM.
5. Les commentaires de fin de ligne sont PERDUS -- c'est voulu. Le seul present
   (`1551: 'RedRampage',  # fix live dumpEnum (absent du tsv)`) est FAUX : `RedRampage` est bien
   dans `enums.tsv`, a 1551, sur les DEUX builds versionnes.

Garde : `python scripts/python/probe_275_enum_maps_drift.py` doit rendre 0 apres passage.
Aucun rebuild ni reinject : ce fichier vit cote Python, pas dans `frida/hooks/`.

ASCII only (console Windows cp1252).
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "scripts" / "python"))

from symbols_layout import build_dir, current_build  # noqa: E402

MAPS = REPO / "scripts" / "python" / "enum_maps.py"

# (bloc, cle enums.tsv, colonne `stream_event` alimentee ou None)
BLOCS = [
    ("EFFECT_TYPE",          "IdunBattle.Entities.Enum.EffectType",           "effect_type"),
    ("ACTIVE_ABILITY_TYPE",  "IdunBattle.Entities.Enum.ActiveAbilityType",    "active_ability_type"),
    ("PASSIVE_ABILITY_TYPE", "IdunBattle.Entities.Enum.TriggeredAbilityType", "passive_ability_type"),
    ("DAMAGE_PROFILE_TYPE",  "IdunBattle.Entities.Enum.DamageProfileType",    "damage_profile_type"),
    ("UNIT_SPAWN_SOURCE",    "IdunBattle.Entities.Enum.SpawnSource",          "unit_spawn_source"),
    ("GROUP_TYPE",           "IdunBattle.Streams.GroupType",                  None),
]

TETE = """\
# enum_maps.py -- id <-> nom des enums natifs, LU PAR L'INGEST ET LES AUDITS.
#
# GENERE : `python scripts/python/regen_enum_maps.py --ecrire`.
# Source : `data/symbols/%s/frida/enums.tsv` (VERSIONNEE, donc presente dans tout checkout).
# Garde  : `python scripts/python/probe_275_enum_maps_drift.py`.
#
# REGENERER A CHAQUE CHANGEMENT DE BUILD. Le jeu AJOUTE, RETIRE et REATTRIBUE des membres ; une
# valeur reattribuee est le pire cas -- elle resout, pointe ailleurs, et rien ne proteste. Mesure
# #275 : `GROUP_TYPE` portait 66 ids au nom FAUX (un membre insere en 36 decalait toute la suite),
# et `EFFECT_TYPE` donnait `1563 = DA_Hero6_Passive_1` la ou le jeu dit
# `SpecialIssueCombiMelta_AdditionalHits`.
#
# ATTENTION -- le nom du bloc ne suit PAS celui de l'enum : `PASSIVE_ABILITY_TYPE` vient de
# `TriggeredAbilityType`, `UNIT_SPAWN_SOURCE` de `SpawnSource`, et `GROUP_TYPE` d'un AUTRE
# namespace (`IdunBattle.Streams`). L'appariement fait foi dans `regen_enum_maps.BLOCS`.
#
# Ce fichier etait genere par `rl_gen_enum_columns.py` depuis `data/dumps/<hash>/dump.cs`,
# artefact Il2CppDumper SUPPRIME le 2026-07-25 : la table n'avait plus de reparateur.
""" % ("%s",)


def enum_du_jeu(build: str, cle: str) -> dict[int, set[str]]:
    """-> {valeur: {noms}}. Un ENSEMBLE : plusieurs membres peuvent partager une valeur."""
    p = build_dir(build) / "frida" / "enums.tsv"
    for ligne in p.open(encoding="utf-8"):
        if ligne.startswith(cle + "\t"):
            out: dict[int, set[str]] = {}
            for paire in ligne.rstrip("\n").split("\t", 1)[1].split(","):
                v, _, n = paire.partition("=")
                if n:
                    try:
                        out.setdefault(int(v), set()).add(n)
                    except ValueError:
                        pass
            return out
    raise SystemExit("cle absente de enums.tsv : %s" % cle)


def choisir(jeu: dict[int, set[str]], ancien: dict[int, str]) -> dict[int, str]:
    """Regle 2 : garder le nom existant s'il est TOUJOURS valide pour cette valeur."""
    return {v: (ancien[v] if ancien.get(v) in noms else sorted(noms)[0])
            for v, noms in jeu.items()}


def rapport(bloc: str, ancien: dict[int, str], choisi: dict[int, str], lister: int) -> None:
    supprimes = sorted(k for k in ancien if k not in choisi)
    ajoutes = sorted(k for k in choisi if k not in ancien)
    renommes = sorted(k for k in choisi if k in ancien and ancien[k] != choisi[k])
    print("  %-22s %d -> %d entrees   supprimees=%-4d ajoutees=%-4d RENOMMEES=%d"
          % (bloc, len(ancien), len(choisi), len(supprimes), len(ajoutes), len(renommes)))
    for v in renommes[:lister]:
        print("      RENOMME %6d : '%s' -> '%s'" % (v, ancien[v], choisi[v]))
    if len(renommes) > lister:
        print("      ... (%d renommages de plus)" % (len(renommes) - lister))
    if ajoutes:
        apercu = ", ".join("%d=%s" % (v, choisi[v]) for v in ajoutes[:lister])
        print("      AJOUTES (le jeu les porte, le depot non) : %s%s"
              % (apercu, " ..." if len(ajoutes) > lister else ""))
    if supprimes:
        apercu = ", ".join("%d:%s" % (v, ancien[v]) for v in supprimes[:lister])
        print("      SUPPRIMES (la valeur n'existe plus) : %s%s"
              % (apercu, " ..." if len(supprimes) > lister else ""))


def bornes_bloc(src: str, bloc: str) -> tuple[int, int, dict[int, str]]:
    """(debut du commentaire d'en-tete, fin du bloc, table actuelle).

    Le commentaire qui PRECEDE immediatement `<BLOC> = {` fait partie du bloc : il porte le
    compte de membres et le nom de l'enum source, donc il perime avec la table."""
    m = re.search(r"^%s\s*=\s*\{" % re.escape(bloc), src, re.M)
    if not m:
        raise SystemExit("bloc %s introuvable dans enum_maps.py" % bloc)
    deb = m.start()
    fin = src.find("\n}", deb)
    if fin < 0:
        raise SystemExit("bloc %s non delimite" % bloc)
    fin += len("\n}")
    # remonte les lignes de commentaire contigues
    tete = deb
    while True:
        prec = src.rfind("\n", 0, tete - 1)
        ligne_deb = prec + 1
        if ligne_deb >= tete or not src[ligne_deb:tete].lstrip().startswith("#"):
            break
        tete = ligne_deb
    table = {int(x.group(1)): x.group(2)
             for x in re.finditer(r"^\s*(-?\d+):\s*'([^']*)'", src[deb:fin], re.M)}
    return tete, fin, table


def rends_bloc(src: str, bloc: str, cle: str, colonne: str | None, build: str,
               lister: int) -> str:
    jeu = enum_du_jeu(build, cle)
    tete, fin, ancien = bornes_bloc(src, bloc)
    choisi = choisir(jeu, ancien)
    rapport(bloc, ancien, choisi, lister)

    court = cle.rsplit(".", 1)[1]
    if colonne:
        entete = "# %s <- enum %s (%d membres) -- %s" % (colonne, court, len(choisi), cle)
    else:
        # `GROUP_TYPE` n'alimente plus aucune colonne : le dire ICI, pas seulement en doc.
        entete = ("# %s (%d membres) -- %s\n"
                  "# PLUS AUCUN CONSOMMATEUR depuis #254b-b : `stream_group.group_name` est resolu\n"
                  "# par NOM via `stream_events.group_name` (meme source `enums.tsv`). Table de\n"
                  "# reference pour lecture humaine uniquement." % (court, len(choisi), cle))
    lignes = [entete, "%s = {" % bloc]
    lignes += ["    %d: %r," % (v, choisi[v]) for v in sorted(choisi)]
    lignes.append("}")
    return src[:tete] + "\n".join(lignes) + src[fin:]


def rends_tete(src: str, build: str) -> str:
    """Remplace l'en-tete du FICHIER (il nommait `rl_gen_enum_columns.py` / `dump.cs`)."""
    m = re.search(r"^\s*$", src, re.M)      # 1re ligne vide = fin de l'en-tete
    fin = m.start() if m else 0
    return (TETE % build) + src[fin:]


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--build", default=None, help="defaut : data/symbols/CURRENT")
    ap.add_argument("--lister", type=int, default=10, help="nb d'ecarts detailles par bloc")
    ap.add_argument("--ecrire", action="store_true",
                    help="ecrit le fichier ; sans ce drapeau, simule et n'ecrit RIEN")
    args = ap.parse_args()

    build = args.build or current_build()
    print("build  : %s" % build)
    print("mode   : %s" % ("ECRITURE" if args.ecrire else "SIMULATION (rien n'est ecrit)"))
    print("")
    src = MAPS.read_text(encoding="utf-8")
    for bloc, cle, colonne in BLOCS:
        src = rends_bloc(src, bloc, cle, colonne, build, args.lister)
    src = rends_tete(src, build)
    if args.ecrire:
        MAPS.write_text(src, encoding="utf-8")
    print("")
    print("---")
    if args.ecrire:
        print("Verifier : python scripts/python/probe_275_enum_maps_drift.py")
    else:
        print("Rien ecrit. Relancer avec --ecrire pour appliquer.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
