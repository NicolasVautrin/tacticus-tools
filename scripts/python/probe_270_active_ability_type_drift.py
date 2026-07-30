#!/usr/bin/env python3
"""#270 -- INVENTAIRE de la derive `ActiveAbilityType` : qui, dans le depot, cite un id que le
build courant ne porte plus, et cette citation designe-t-elle encore une mecanique du jeu ?

POURQUOI CETTE SONDE
--------------------
Quatre artefacts du depot recopient l'enum natif `IdunBattle.Entities.Enum.ActiveAbilityType` :

  1. `scripts/python/engine/entities/active_ability_type.py`  -- le mirror IntEnum ;
  2. `scripts/python/enum_maps.py` (`ACTIVE_ABILITY_TYPE`)    -- id<->nom, LU PAR LE MOTEUR
     (`engine.ai.state_bridge._abilities_of` / `_resolve_ability`) ;
  3. `scripts/sql/006_ref_tables.sql` (`ref_active_ability`)  -- cible de FK de `stream_event` ;
  4. `scripts/sql/013_enum_fk_and_names.sql`                  -- backfill `active_ability_type_name`.

Aucun des quatre n'est re-derive au changement de build, et leurs DEUX generateurs
(`rl_gen_ref_tables.py`, `rl_gen_enum_columns.py`) lisent `data/dumps/<hash>/dump.cs`, artefact
Il2CppDumper SUPPRIME le 2026-07-25 -- ils ne peuvent donc plus tourner. La derive est doublement
silencieuse : elle ne casse rien ET son reparateur est en panne.

LES DEUX SENS DE LA DERIVE N'ONT PAS LE MEME COUT
-------------------------------------------------
  * un id du port ABSENT du jeu est INERTE : le jeu ne l'emet jamais, aucun nom du gameconfig ne
    lui correspond. Il encombre, il ne ment que si un humain le lit ;
  * un id du jeu ABSENT du port DEGRADE EN SILENCE : `_abilities_of` dit noir sur blanc « une
    active dont le nom n'est pas dans l'enum est ignoree » -> l'ability disparait de l'unite
    offline ; et cote base, la FK `se_active_ability_id_fkey` REFUSE la ligne.
  * un id RENUMEROTE (meme valeur, autre nom) serait le pire -- il resout, pointe ailleurs, et
    rien ne proteste. La sonde le cherche explicitement, dans les DEUX sens.

CE QUE LA SONDE FAIT
--------------------
  Etape 1  diff natif <-> les 4 artefacts (manquants / en trop / RENUMEROTES).
  Etape 2  corroboration de CHAQUE id absent par des sources INDEPENDANTES du dump d'enums :
           `classes.tsv` (`<Nom>Ability` existe-t-il ?), `gameconfig.json` (le jeu configure-t-il
           une ability de ce nom ?), et le dump d'enums COMPLET (le nom vit-il dans un AUTRE
           enum ? -- c'est le piege d'homonymie : `DanceOfDaggers` est mort en ActiveAbilityType
           et VIVANT en `IdunBattle.Configuration.UtilityType`).
  Etape 3  inventaire des CITATIONS dans les fichiers suivis, classees
           GENERE / CODE / DOC / DONNEE / HOMONYME.
  Etape 4  `--live` : confronte au RPC `dumpEnum` de la session Frida active (lecture seule,
           aucun inject).

`--rev <git-rev>` lit les 4 artefacts A UNE REVISION au lieu du disque. C'est ce qui garde la
sonde utile APRES la correction : `--rev <sha d'avant #270>` rejoue l'inventaire complet des 75
ids morts et de leurs citations, au lieu de rendre une page vide. Au PROCHAIN build, la forme par
defaut (artefacts du disque vs enum du jeu) se rallume toute seule.
   ATTENTION : `--rev` ne rembobine QUE les 4 artefacts. L'etape 3 balaye toujours l'ARBRE DE
   TRAVAIL -- c'est voulu (on veut savoir qui cite AUJOURD'HUI un id mort HIER), mais ca fausse le
   seul compte `GENERE`, qui retombe a ce que l'arbre courant porte encore.

Sortie 0 = les 4 artefacts collent au build ; 1 = au moins un derive.
ASCII only (console Windows cp1252).
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "scripts" / "python"))

from symbols_layout import build_dir, current_build  # noqa: E402

ENUM = "IdunBattle.Entities.Enum.ActiveAbilityType"

MIRROR = REPO / "scripts" / "python" / "engine" / "entities" / "active_ability_type.py"
MAPS = REPO / "scripts" / "python" / "enum_maps.py"
SQL_REF = REPO / "scripts" / "sql" / "006_ref_tables.sql"
SQL_ENUM = REPO / "scripts" / "sql" / "013_enum_fk_and_names.sql"

# Les quatre artefacts GENERES : toute occurrence d'un nom mort y est une ligne de table, pas une
# citation de mecanique. On les isole pour que le vrai signal (code + prose) reste lisible.
GENERES = {
    "scripts/python/engine/entities/active_ability_type.py",
    "scripts/python/enum_maps.py",
    "scripts/sql/006_ref_tables.sql",
    "scripts/sql/013_enum_fk_and_names.sql",
}

# Le mirror echappe `None` (mot-clef Python). Ce n'est pas une divergence de nom.
ALIAS_MIRROR = {"None_": "None"}

# La sonde nomme elle-meme des ids morts dans sa propre docstring : ne pas s'auto-compter.
IGNORE_CITATIONS = {"scripts/python/probe_270_active_ability_type_drift.py",
                    "scripts/python/regen_active_ability_tables.py"}

# Lu par `--rev` : quand on lit les artefacts a une revision git, cette variable porte le rev.
_REV: str | None = None


def _lire(rel: Path) -> str:
    """Contenu d'un artefact : le disque, ou la revision `--rev` si elle est posee."""
    chemin = rel.relative_to(REPO).as_posix()
    if _REV is None:
        return rel.read_text(encoding="utf-8")
    r = subprocess.run(["git", "-C", str(REPO), "show", "%s:%s" % (_REV, chemin)],
                       capture_output=True, text=True, encoding="utf-8")
    if r.returncode:
        raise SystemExit("git show %s:%s -> %s" % (_REV, chemin, r.stderr.strip()[:200]))
    return r.stdout


# --------------------------------------------------------------------------- sources natives

def enum_natif(build: str, cle: str = ENUM) -> dict[int, set[str]]:
    """{valeur: {noms}} depuis `data/symbols/<build>/frida/enums.tsv`.

    Un ENSEMBLE de noms : plusieurs membres partagent parfois une valeur (mesure : 9999 porte
    `STRIPPED` ET `testAssetBundles`)."""
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


def tous_les_enums(build: str) -> dict[str, dict[int, set[str]]]:
    """Le dump d'enums ENTIER -- sert a detecter les HOMONYMES inter-enums."""
    p = build_dir(build) / "frida" / "enums.tsv"
    out: dict[str, dict[int, set[str]]] = {}
    for ligne in p.open(encoding="utf-8"):
        if ligne.startswith("#!"):
            continue
        tete, _, corps = ligne.rstrip("\n").partition("\t")
        if not corps:
            continue
        m: dict[int, set[str]] = {}
        for paire in corps.split(","):
            v, _, n = paire.partition("=")
            if n:
                try:
                    m.setdefault(int(v), set()).add(n)
                except ValueError:
                    pass
        out[tete] = m
    return out


def noms_de_classes(build: str) -> str:
    return (build_dir(build) / "frida" / "classes.tsv").read_text(encoding="utf-8", errors="replace")


def abilities_du_gameconfig(build: str) -> set[str]:
    """Les abilities que le JEU configure, keyees par NOM. Source independante du binaire."""
    p = build_dir(build) / "gameconfig.json"
    d = json.loads(p.read_text(encoding="utf-8"))
    return set(((d.get("clientGameConfig") or {}).get("units") or {}).get("abilities") or {})


# --------------------------------------------------------------------------- les 4 artefacts

def table_mirror() -> dict[int, str]:
    src = _lire(MIRROR)
    out = {}
    for m in re.finditer(r"^\s{4}([A-Za-z_]\w*)\s*=\s*(-?\d+)\s*$", src, re.M):
        out[int(m.group(2))] = ALIAS_MIRROR.get(m.group(1), m.group(1))
    return out


def _blocs_enum_maps() -> dict[str, dict[int, str]]:
    src = _lire(MAPS)
    tetes = [(m.start(), m.group(1))
             for m in re.finditer(r"^([A-Z_][A-Z0-9_]*)\s*(?::[^=]*)?=\s*\{", src, re.M)]
    out: dict[str, dict[int, str]] = {}
    for i, (deb, nom) in enumerate(tetes):
        fin = tetes[i + 1][0] if i + 1 < len(tetes) else len(src)
        out[nom] = {int(m.group(1)): m.group(2)
                    for m in re.finditer(r"^\s*(-?\d+):\s*'([^']*)'", src[deb:fin], re.M)}
    return out


def table_enum_maps() -> dict[int, str]:
    return _blocs_enum_maps().get("ACTIVE_ABILITY_TYPE", {})


def table_sql_ref() -> dict[int, str]:
    """Le bloc `INSERT INTO tacticus.ref_active_ability` de 006 -- borne au PROCHAIN `INSERT`."""
    src = _lire(SQL_REF)
    deb = src.find("INSERT INTO tacticus.ref_active_ability")
    if deb < 0:
        return {}
    fin = src.find("INSERT INTO", deb + 10)
    bloc = src[deb:fin if fin > 0 else len(src)]
    return {int(m.group(1)): m.group(2)
            for m in re.finditer(r"\((-?\d+),\s*'((?:[^']|'')*)'\)", bloc)}


def table_sql_backfill() -> dict[int, str]:
    """Le VALUES du backfill `active_ability_type_name` de 013."""
    src = _lire(SQL_ENUM)
    deb = src.find("SET active_ability_type_name")
    if deb < 0:
        return {}
    fin = src.find("WHERE se.active_ability_type", deb)
    bloc = src[deb:fin if fin > 0 else len(src)]
    return {int(m.group(1)): m.group(2)
            for m in re.finditer(r"\((-?\d+),\s*'((?:[^']|'')*)'\)", bloc)}


ARTEFACTS = (
    ("mirror  engine/entities/active_ability_type.py", table_mirror),
    ("maps    enum_maps.ACTIVE_ABILITY_TYPE", table_enum_maps),
    ("sql     006 ref_active_ability", table_sql_ref),
    ("sql     013 backfill *_name", table_sql_backfill),
)


# --------------------------------------------------------------------------- citations

def fichiers_suivis() -> list[str]:
    out = subprocess.run(["git", "-C", str(REPO), "ls-files"],
                         capture_output=True, text=True, encoding="utf-8").stdout
    return out.splitlines()


def inventaire_citations(morts: dict[int, str], homonymes: dict[str, dict[str, list[int]]]
                         ) -> dict[str, list[tuple[str, int, str]]]:
    """{nom mort: [(fichier, ligne, texte)]} sur tout le depot suivi, hors data/symbols/."""
    motifs = {n: re.compile(r"\b" + re.escape(n) + r"\b") for n in morts.values()}
    cites: dict[str, list[tuple[str, int, str]]] = {}
    for rel in fichiers_suivis():
        if rel.startswith("data/symbols/") or rel in IGNORE_CITATIONS:
            continue
        try:
            txt = (REPO / rel).read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        # Coupe-circuit : ne balaye ligne par ligne que si le fichier contient au moins un nom.
        candidats = [n for n in motifs if n in txt]
        if not candidats:
            continue
        for k, ligne in enumerate(txt.splitlines(), 1):
            for n in candidats:
                if motifs[n].search(ligne):
                    cites.setdefault(n, []).append((rel, k, ligne.strip()[:150]))
    return cites


def classe_citation(rel: str, nom: str, homonymes: dict[str, dict[str, list[int]]]) -> str:
    """HOMONYME ne veut PAS dire « faux positif » : le nom vit dans un AUTRE enum, donc la
    citation doit etre QUALIFIEE avant d'etre jugee. Elle peut viser l'enum vivant (ex.
    `utility_type.py:89 DanceOfDaggers = 49` est JUSTE) comme l'enum mort (ex. le commentaire
    `MechRepair` de `state_bridge.py:283` accompagne bien l'id 82, mort)."""
    if rel in GENERES:
        return "GENERE"
    if nom in homonymes:
        return "HOMONYME"
    if rel.startswith("docs/") or rel.endswith(".md"):
        return "DOC"
    if rel.startswith("data/"):
        return "DONNEE"
    return "CODE"


# --------------------------------------------------------------------------- live

def confront_live(natif: dict[int, set[str]]) -> int:
    """RPC `dumpEnum` sur la session Frida active. LECTURE SEULE -- aucun inject, aucun runner."""
    from rl_collect_batch import _resolve_session, _rpc  # import tardif : le host peut etre eteint
    sid = _resolve_session()
    rep = _rpc(sid, "dumpEnum", [{"asm": "IdunSharedAssembly.dll",
                                  "ns": "IdunBattle.Entities.Enum",
                                  "cls": "ActiveAbilityType"}], timeout=30)
    vals = (rep.get("result") or {}).get("values")
    if not vals:
        print("  live : RPC sans valeurs -- %s" % json.dumps(rep)[:200])
        return 1
    live: dict[int, set[str]] = {}
    for nom, v in vals.items():
        live.setdefault(int(v), set()).add(nom)
    manque = sorted(set(natif) - set(live))
    trop = sorted(set(live) - set(natif))
    faux = {v: (sorted(natif[v]), sorted(live[v]))
            for v in sorted(set(live) & set(natif)) if natif[v] != live[v]}
    print("  live (session %d) : %d valeurs ; tsv : %d valeurs" % (sid, len(live), len(natif)))
    print("  tsv sans live=%s  live sans tsv=%s  noms divergents=%d" % (manque, trop, len(faux)))
    for v, (a, b) in list(faux.items())[:10]:
        print("    %6d : tsv %s  live %s" % (v, a, b))
    return 0 if not (manque or trop or faux) else 1


# --------------------------------------------------------------------------- main

def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--build", default=None, help="defaut : data/symbols/CURRENT")
    ap.add_argument("--lister", type=int, default=8, help="nb d'ecarts detailles par artefact")
    ap.add_argument("--citations", action="store_true",
                    help="detaille l'inventaire des citations, fichier par fichier")
    ap.add_argument("--live", action="store_true",
                    help="confronte au RPC dumpEnum (lecture seule ; host requis)")
    ap.add_argument("--rev", default=None,
                    help="lit les 4 artefacts a cette revision git au lieu du disque "
                         "(rejoue un inventaire historique)")
    args = ap.parse_args()

    global _REV
    _REV = args.rev
    build = args.build or current_build()
    if _REV:
        print("artefacts lus a la revision : %s" % _REV)
    natif = enum_natif(build)
    nat_noms = {n for s in natif.values() for n in s}
    print("build : %s   %s : %d valeurs / %d noms"
          % (build, ENUM, len(natif), len(nat_noms)))
    print("")

    # ---- Etape 1 : les 4 artefacts contre le natif
    print("ETAPE 1 -- les artefacts du depot contre l'enum du build")
    derive = False
    absents_union: dict[int, str] = {}
    for label, lire in ARTEFACTS:
        t = lire()
        faux = {v: (t[v], sorted(natif[v])) for v in sorted(set(t) & set(natif))
                if t[v] not in natif[v]}
        absents = {v: t[v] for v in sorted(set(t) - set(natif))}
        manquants = sorted(set(natif) - set(t))
        absents_union.update(absents)
        etat = "OK    " if not (faux or absents or manquants) else "DERIVE"
        if faux or absents or manquants:
            derive = True
        print("  %s %-44s porte=%-4d  RENUMEROTES=%-3d  absents-du-jeu=%-3d  manquants=%d"
              % (etat, label, len(t), len(faux), len(absents), len(manquants)))
        for v in list(faux)[:args.lister]:
            print("           %6d : le depot dit '%s'  le jeu dit %s"
                  % (v, faux[v][0], faux[v][1]))
        if manquants:
            print("           manquants (le jeu les porte, le depot non) : %s"
                  % ", ".join("%d=%s" % (v, "|".join(sorted(natif[v]))) for v in manquants))
    print("")

    # ---- Etape 2 : corroborer chaque id absent par des sources independantes
    print("ETAPE 2 -- les %d ids absents du jeu, corrobores hors dump d'enums" % len(absents_union))
    classes = noms_de_classes(build)
    cfg = abilities_du_gameconfig(build)
    tous = tous_les_enums(build)
    homonymes: dict[str, dict[str, list[int]]] = {}
    survivants: list[str] = []
    n_classe = n_cfg = 0
    for v, nom in sorted(absents_union.items()):
        ail = {e: sorted(k for k, s in m.items() if nom in s)
               for e, m in tous.items() if any(nom in s for s in m.values())}
        if ail:
            homonymes[nom] = ail
        # `<Nom>Ability` doit etre un SEGMENT de symbole, pas un suffixe (`RadBombardmentAbility`
        # ne prouve RIEN sur `Bombardment`) -> bornage a gauche par un non-mot.
        classe_vue = re.search(r"(?<![A-Za-z0-9_])" + re.escape(nom) + r"Ability\b",
                               classes) is not None
        n_classe += int(classe_vue)
        n_cfg += int(nom in cfg)
        if classe_vue or nom in cfg:
            survivants.append("%d=%s (classe=%s cfg=%s)" % (v, nom, classe_vue, nom in cfg))
    print("  classe `<Nom>Ability` presente dans classes.tsv : %d / %d"
          % (n_classe, len(absents_union)))
    print("  nom present dans gameconfig.units.abilities     : %d / %d"
          % (n_cfg, len(absents_union)))
    print("  nom porte par un AUTRE enum du dump (homonyme)  : %d"
          % len(homonymes))
    for nom, d in sorted(homonymes.items()):
        print("      %-24s -> %s" % (nom, ", ".join("%s%s" % (e, v) for e, v in d.items())))
    if survivants:
        print("  !! A TRANCHER (une source independante les voit encore vivants) :")
        for s in survivants:
            print("       %s" % s)
    elif absents_union:
        print("  AUCUN id absent n'est vu vivant par une source independante -> code mort.")
    print("")

    # ---- Etape 3 : citations
    print("ETAPE 3 -- citations des %d noms morts dans les fichiers suivis" % len(absents_union))
    cites = inventaire_citations(absents_union, homonymes)
    par_classe: dict[str, int] = {}
    hors_generes: list[tuple[str, str, int, str]] = []
    for nom, locs in cites.items():
        for rel, k, txt in locs:
            c = classe_citation(rel, nom, homonymes)
            par_classe[c] = par_classe.get(c, 0) + 1
            if c != "GENERE":
                hors_generes.append((nom, rel, k, txt))
    print("  noms cites : %d / %d   occurrences : %d"
          % (len(cites), len(absents_union), sum(len(v) for v in cites.values())))
    print("  ventilation : %s" % dict(sorted(par_classe.items())))
    print("  HORS artefacts generes (%d occurrences) :" % len(hors_generes))
    for nom, rel, k, txt in sorted(hors_generes, key=lambda x: (x[1], x[2])):
        print("    [%-8s] %-24s %s:%d" % (classe_citation(rel, nom, homonymes), nom, rel, k))
        if args.citations:
            print("               %s" % txt)
    print("")

    # ---- Etape 4 : live
    if args.live:
        print("ETAPE 4 -- confrontation LIVE (dumpEnum)")
        if confront_live(natif):
            derive = True
        print("")

    if derive:
        print("AU MOINS UN ARTEFACT DERIVE.")
        print("Les deux generateurs (rl_gen_ref_tables.py / rl_gen_enum_columns.py) lisent")
        print("data/dumps/<hash>/dump.cs, SUPPRIME le 2026-07-25 : ils ne peuvent plus tourner.")
        print("Voir docs/rl/case-270-active-ability-type-drift.md.")
        return 1
    print("les 4 artefacts collent au build %s" % build)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
