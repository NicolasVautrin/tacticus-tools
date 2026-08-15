#!/usr/bin/env python3
"""#256 -- regenere les tables de noms FIGEES de `frida/hooks/data/` depuis l'enum du build courant.

POURQUOI
--------
Quatre fichiers `frida/hooks/data/*.ts` recopient un enum natif sous forme `{ id: "Nom" }`.
Contrairement a `introspect.ts` -- qui lit l'enum A L'EXECUTION via `dumpEnum` et se met donc a
jour tout seul -- ces tables sont GELEES au build ou elles ont ete generees. Leur en-tete disait
« Regenerate when GameAssembly.dll is updated », et personne ne le faisait : mesure du 2026-07-29,
trois d'entre elles derivaient DEPUIS AVANT la mise a jour (75, 73 et 107 entrees hors enum), deux
citant meme une source disparue (`sources_win`).

Le mode de defaillance est le pire qui soit : une table figee nomme correctement les ids inferieurs
au premier decalage et ment SILENCIEUSEMENT sur tous les suivants -- la sortie reste plausible.

REGLE DE REGENERATION
---------------------
1. La source de verite est `data/symbols/<build>/frida/enums.tsv` (produit par la chaine Frida,
   qui fait autorite sur les METADONNEES).
2. Une valeur peut porter PLUSIEURS noms (mesure : `9999 = STRIPPED` ET `9999 = testAssetBundles`
   dans `ActiveAbilityType` et `TriggeredAbilityType`). On garde le nom DEJA PRESENT dans la table
   s'il appartient toujours a l'ensemble -- ca minimise le diff et respecte les choix anterieurs --
   sinon on prend le premier par ordre lexicographique, pour rester DETERMINISTE.
3. Les entrees dont la valeur n'existe plus dans l'enum sont SUPPRIMEES, et listees en sortie.
   Rien n'est « volontairement hors enum » : `9999 STRIPPED`, longtemps cite comme tel, EST un
   membre a part entiere des trois enums -- verifie le 2026-07-29.

⚠ ON NE REECRIT QUE LE BLOC DE TABLE, pas le fichier. Deux de ces fichiers portent une FONCTION
EXPORTEE sous la table (`abilityName`, `triggeredAbilityName`, qui rendent `"id:N"` sur un id
inconnu). Un regenerateur qui recrache le fichier entier les SUPPRIME -- et comme elles sont
importees ailleurs, la casse ne se voit qu'a la compilation, apres coup. On remplace donc
exactement de `export const <CONST> ... = {` jusqu'a son `};`, et on recopie la queue VERBATIM.

NE REGENERE PAS `targeting-rule-names.ts` : cette table indexe des INDEX DE BIT, pas des valeurs,
et la projection enum -> bits est lossy (les composites a plusieurs bits n'ont pas d'index). Elle
est par ailleurs SAINE. La toucher demanderait une regle propre, pas ce moule-ci.

Garde : `python scripts/python/probe_252_hook_name_tables.py` doit rendre 0 apres passage.
Ces fichiers vivent dans `frida/hooks/*` -> leur correction exige un REBUILD + un REINJECT.

ASCII only (console Windows cp1252).
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "scripts" / "python"))

from symbols_layout import current_build  # noqa: E402

DATA = REPO / "frida" / "hooks" / "data"

# fichier -> (cle dans enums.tsv, nom de la const TS exportee, table INDEXEE PAR BIT ?)
TABLES = {
    "ability-names.ts":            ("IdunBattle.Entities.Enum.ActiveAbilityType",    "ACTIVE_ABILITY_NAMES", False),
    "effect-type-names.ts":        ("IdunBattle.Entities.Enum.EffectType",           "EFFECT_TYPE_NAMES", False),
    "event-trigger-type-names.ts": ("IdunBattle.DSL.EventTriggerType",               "EVENT_TRIGGER_TYPE_NAMES", False),
    "triggered-ability-names.ts":  ("IdunBattle.Entities.Enum.TriggeredAbilityType", "TRIGGERED_ABILITY_NAMES", False),
    # #283 : entree en 2026-07-30. Cette table vivait INLINE dans
    # `frida/hooks/features/ai-utility-trace.ts`, donc hors de la garde #252 -- et elle etait
    # figee sur `gqfc5mff6c` (82 entrees, 37 fausses). Elle n'est PAS decorative : elle pilote
    # `prePopulateKnownConfigs`, qui appelle `UtilitiesDatabase$$GetUtilityConfig(type, coll)`
    # AVEC ces ordinaux et etiquette le resultat avec le nom associe.
    "utility-type-names.ts":       ("IdunBattle.Configuration.UtilityType",          "UTILITY_TYPE_NAMES", False),
    # #330-r4 : entree en 2026-08-15. Elle etait le SEUL artefact genere du depot SANS
    # generateur -- son en-tete declarait `data/dumps/kqkbjqfb6c/dump.cs`, source SUPPRIMEE, deux
    # builds en arriere. L'ancien refus (<< la projection enum -> bits est lossy, ca demanderait
    # une regle propre >>) etait juste sur le fond et perime sur la forme : la regle propre
    # EXISTAIT DEJA -- `probe_252` la joue pour VERIFIER cette table depuis #252, et c'est celle
    # de `_par_bit` ci-dessous. Un artefact qu'un cliquet sait verifier, un generateur sait
    # l'ecrire ; les separer, c'etait garder un orphelin dont seule l'ESTAMPILLE mentait.
    "targeting-rule-names.ts":     ("IdunBattle.Core.Services.TargetingRule",        "TARGETING_RULE_BITS", True),
}

ENTREE = re.compile(r'^\s*(-?\d+)\s*:\s*"([^"]*)"', re.M)

# Ce que chaque table SERT -- recopie dans l'en-tete generee, pour qu'un lecteur sache a quoi elle
# sert sans avoir a remonter au consommateur.
ROLE = {
    "ability-names.ts": "id -> nom d'ActiveAbilityType (l'ability concrete d'une action).",
    "effect-type-names.ts": "id -> nom d'EffectType (EffectComponent.EffectType) : ce que l'UI rend en icones.",
    "event-trigger-type-names.ts": "id -> nom d'EventTriggerType (le declencheur d'un trigger DSL).",
    "triggered-ability-names.ts": "id -> nom de TriggeredAbilityType (l'ability passive/declenchee).",
    "utility-type-names.ts": "id -> nom d'UtilityType (la cle d'une UtilityConfig d'IA).",
    "targeting-rule-names.ts": "index de BIT -> nom de TargetingRule (composites a plusieurs bits exclus).",
}


def enum_du_jeu(build: str, cle: str) -> dict[int, set[str]]:
    """-> {valeur: {noms}}. Un ENSEMBLE : plusieurs membres peuvent partager une valeur."""
    p = REPO / "data" / "symbols" / build / "frida" / "enums.tsv"
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


def _par_bit(jeu: dict[int, set[str]]) -> dict[int, set[str]]:
    """{valeur: noms} -> {index de BIT: noms}, composites EXCLUS.

    Regle REPRISE MOT POUR MOT de `probe_252_hook_name_tables` (`if par_bit:`), et c'est le
    point : le cliquet et le generateur doivent projeter A L'IDENTIQUE, sinon le second ecrit ce
    que le premier refusera. `v & (v - 1) == 0` = une seule puissance de deux ; un composite
    (`TargetIsEnemy | TargetIsAlive`) n'a pas d'index de bit et n'entre donc pas dans la table.
    C'est une projection LOSSY, ASSUMEE : la table sert a NOMMER un bit d'un masque decompose.
    """
    return {v.bit_length() - 1: n for v, n in jeu.items() if v > 0 and (v & (v - 1)) == 0}


def decoupe(texte: str, const: str) -> tuple[str, str]:
    """-> (corps de la table, QUEUE a preserver verbatim).

    La queue n'est PAS decorative : `ability-names.ts` et `triggered-ability-names.ts` exportent
    une fonction sous leur table. Ecraser le fichier entier la supprimerait, et l'import casse ne
    se verrait qu'a la compilation."""
    debut = texte.find("export const %s" % const)
    if debut < 0:
        raise SystemExit("bloc `export const %s` introuvable" % const)
    ouvre = texte.find("{", debut)
    ferme = texte.find("\n};", ouvre)
    if ouvre < 0 or ferme < 0:
        raise SystemExit("bloc `%s` non delimite (pas de `};` en debut de ligne)" % const)
    return texte[ouvre:ferme], texte[ferme + len("\n};"):]


def rends(fichier: str, cle: str, const: str, build: str, ecrire: bool,
          par_bit: bool = False) -> tuple[int, int, int]:
    f = DATA / fichier
    brut = f.read_text(encoding="utf-8") if f.is_file() else ""
    corps, queue = decoupe(brut, const) if brut else ("", "")
    ancien = {int(m.group(1)): m.group(2) for m in ENTREE.finditer(corps)}
    jeu = enum_du_jeu(build, cle)
    if par_bit:
        jeu = _par_bit(jeu)

    # Regle 2 : garder le nom existant s'il est TOUJOURS valide pour cette valeur.
    choisi: dict[int, str] = {}
    for v, noms in jeu.items():
        vu = ancien.get(v)
        choisi[v] = vu if (vu in noms) else sorted(noms)[0]

    supprimes = sorted(k for k in ancien if k not in jeu)
    ajoutes = sorted(k for k in jeu if k not in ancien)
    renommes = sorted(k for k in jeu if k in ancien and ancien[k] != choisi[k])

    lignes = [
        "// Auto-genere : python scripts/python/regen_hook_name_tables.py",
        "// Source : data/symbols/%s/frida/enums.tsv -- %s" % (build, cle),
        "// %s" % ROLE[fichier],
        "// REGENERER A CHAQUE CHANGEMENT DE BUILD. Ces valeurs sont IMPLICITES : un membre insere",
        "// ou retire au MILIEU decale tout ce qui suit, et une table figee ment alors SILENCIEUSEMENT",
        "// sur tous les ids au-dela du decalage (les precedents restent justes -- d'ou l'invisibilite).",
        "// Garde : python scripts/python/probe_252_hook_name_tables.py",
        "// %d %s (%d..%d)." % (len(choisi), "bits simples" if par_bit else "entrees",
                                min(choisi), max(choisi)),
        "export const %s: Record<number, string> = {" % const,
    ]
    if par_bit:
        # La projection est LOSSY et la table doit le DIRE : un lecteur qui y cherche un
        # composite (`TargetIsEnemy | TargetIsAlive`) ne le trouvera pas, et sans cette ligne
        # il conclurait que le membre n'existe pas dans le jeu.
        lignes.insert(3, "// Table indexee par INDEX DE BIT, pas par valeur : l'enum natif est un"
                         " [Flags] 64 bits ;")
        lignes.insert(4, "// les membres COMPOSITES (plusieurs bits allumes) n'ont pas d'index et"
                         " sont donc ABSENTS.")
    lignes += ['    %d: "%s",' % (v, choisi[v]) for v in sorted(choisi)]
    lignes.append("};")
    texte = "\n".join(lignes) + queue

    print("  %-30s %d -> %d entrees%s" % (fichier, len(ancien), len(choisi),
                                          "   (+ queue preservee : %d lignes)" % queue.count("\n")
                                          if queue.strip() else ""))
    print("      supprimees=%-4d ajoutees=%-4d renommees=%d" % (len(supprimes), len(ajoutes), len(renommes)))
    for v in renommes[:8]:
        print("        %6d : %-38s -> %s" % (v, '"%s"' % ancien[v], '"%s"' % choisi[v]))
    if len(renommes) > 8:
        print("        ... et %d autres renommages" % (len(renommes) - 8))
    if supprimes:
        apercu = ", ".join("%d:%s" % (v, ancien[v]) for v in supprimes[:5])
        print("      ids disparus de l'enum (retires) : %s%s"
              % (apercu, " ..." if len(supprimes) > 5 else ""))

    if ecrire:
        f.write_text(texte, encoding="utf-8")
    return len(supprimes), len(ajoutes), len(renommes)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--build", default=None, help="defaut : data/symbols/CURRENT")
    ap.add_argument("--ecrire", action="store_true",
                    help="ecrit les fichiers ; sans ce drapeau, simule et n'ecrit RIEN")
    args = ap.parse_args()

    build = args.build or current_build()
    print("build  : %s" % build)
    print("mode   : %s" % ("ECRITURE" if args.ecrire else "SIMULATION (rien n'est ecrit)"))
    print("")
    tot = [0, 0, 0]
    for fichier, (cle, const, par_bit) in sorted(TABLES.items()):
        s, a, r = rends(fichier, cle, const, build, args.ecrire, par_bit)
        tot[0] += s; tot[1] += a; tot[2] += r
        print("")
    print("---")
    print("total : supprimees=%d ajoutees=%d renommees=%d" % tuple(tot))
    if args.ecrire:
        print("")
        print("Ces fichiers vivent dans frida/hooks/* : REBUILD (npm run build:hooks) + REINJECT requis.")
        print("Puis verifier : python scripts/python/probe_252_hook_name_tables.py")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
