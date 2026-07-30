#!/usr/bin/env python3
"""#275 -- INVENTAIRE de la derive des SIX tables de `scripts/python/enum_maps.py`.

LA QUESTION BINAIRE, PAR TABLE
------------------------------
Chaque bloc de `enum_maps.py` coincide-t-il EXACTEMENT -- memes valeurs, memes noms -- avec
l'enum natif correspondant de `data/symbols/<CURRENT>/frida/enums.tsv` ? Toute divergence est un
nom FAUX rendu en silence : `rl_collect_batch` remplit les colonnes `*_name` de `stream_event`
depuis `BY_COLUMN`, et les audits de couverture qualifient les passifs du parc contre
`EFFECT_TYPE` / `PASSIVE_ABILITY_TYPE`. `GROUP_TYPE`, lui, n'a plus AUCUN consommateur depuis
#254b-b (`stream_group.group_name` est resolu par NOM via `stream_events`) -- il reste garde ici
parce qu'une table qu'on garde est une table qu'on regenere, et parce que sa version perimee a
DEJA menti (elle a fixe le `59` de `_ATTACK`).

POURQUOI CETTE SONDE (et pas juste « on regenere »)
---------------------------------------------------
Le generateur historique `rl_gen_enum_columns.py` lit `data/dumps/<hash>/dump.cs` -- artefact
Il2CppDumper gitignore et SUPPRIME le 2026-07-25. La table n'avait donc plus de REPARATEUR, et
c'est la meme cause racine que #270. Le pendant de cette sonde est
`regen_enum_maps.py`, qui reecrit les blocs depuis `enums.tsv` (source VERSIONNEE).

LES TROIS SENS DE LA DERIVE N'ONT PAS LE MEME COUT
--------------------------------------------------
  * une valeur du depot ABSENTE du jeu est INERTE : le jeu ne l'emet jamais. Elle n'encombre
    qu'un lecteur humain -- SAUF si du CODE la cite (constante `_ATTACK = 59`...), auquel cas
    elle devient un bug muet ;
  * une valeur du jeu ABSENTE du depot degrade en silence : la colonne `*_name` reste NULL ;
  * une valeur RENUMEROTEE (meme id, autre nom) est le pire cas -- elle resout, pointe ailleurs,
    et rien ne proteste. C'est exactement ce qui a fait ecrire `59 = NormalAttack_AtomicDamage`
    alors que le jeu dit `ZingerAbility` (le vrai `NormalAttack_AtomicDamage` est 61).

CE QUE LA SONDE FAIT
--------------------
  Etape 1  diff natif <-> les 6 blocs (renumerotes / absents-du-jeu / manquants).
  Etape 2  COLLISIONS : parmi les ids renumerotes, ceux dont l'ANCIEN nom existe toujours dans
           l'enum sous une AUTRE valeur -- un `id` recycle vers un autre membre. C'est la classe
           d'erreur qu'une regeneration naive corrige sans le dire, et qu'un lecteur du depot ne
           peut pas voir.
  Etape 3  CITATIONS des noms que la regeneration SUPPRIMERAIT, classees. C'est le garde-fou du
           piege #270 : une regeneration naive retire un membre encore cite par le port. Trois
           classes, et elles ne se traitent pas pareil :
             GENERE   -- une ligne de table (enum_maps, les mirrors `engine/entities/*_type.py`,
                         les migrations SQL). Pas une citation de mecanique.
             HOMONYME -- le nom vit encore dans un AUTRE enum du dump, ou dans le gameconfig. La
                         citation peut viser l'enum vivant : elle doit etre QUALIFIEE, pas jugee
                         sur le nom seul (`Guard`, `Camouflage`, `Attack`... sont des traits).
             CODE/DOC -- le reste : a trancher un par un (code mort a retirer, ou citation
                         devenue fausse -- plus grave, elle a l'air juste).
  Etape 4  VOISINS : les mirrors `engine/entities/*_type.py` recopient les MEMES enums depuis le
           MEME generateur mort. Mesure informative (ils sont HORS du perimetre #275) : sans elle,
           corriger `enum_maps` seul laisserait le depot se contredire en silence.
  Etape 5  `--live` : confronte au RPC `dumpEnum` de la session Frida active (LECTURE SEULE,
           aucun inject, aucun runner).

Sortie 0 = les 6 blocs collent au build ; 1 = au moins un derive.
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

MAPS = REPO / "scripts" / "python" / "enum_maps.py"

# (bloc Python, cle enums.tsv, namespace live, classe live)
#
# ATTENTION -- ces appariements sont LUS, pas devines : le nom du bloc Python ne suit PAS celui de
# l'enum natif (`PASSIVE_ABILITY_TYPE` <- `TriggeredAbilityType`, `UNIT_SPAWN_SOURCE` <-
# `SpawnSource`), et `GroupType` vit dans un AUTRE namespace (`IdunBattle.Streams`) que les cinq
# autres. Un appariement au jugé produirait un diff massif et FAUX.
BLOCS = [
    ("EFFECT_TYPE",         "IdunBattle.Entities.Enum.EffectType",
     "IdunBattle.Entities.Enum", "EffectType"),
    ("ACTIVE_ABILITY_TYPE", "IdunBattle.Entities.Enum.ActiveAbilityType",
     "IdunBattle.Entities.Enum", "ActiveAbilityType"),
    ("PASSIVE_ABILITY_TYPE", "IdunBattle.Entities.Enum.TriggeredAbilityType",
     "IdunBattle.Entities.Enum", "TriggeredAbilityType"),
    ("DAMAGE_PROFILE_TYPE", "IdunBattle.Entities.Enum.DamageProfileType",
     "IdunBattle.Entities.Enum", "DamageProfileType"),
    ("UNIT_SPAWN_SOURCE",   "IdunBattle.Entities.Enum.SpawnSource",
     "IdunBattle.Entities.Enum", "SpawnSource"),
    ("GROUP_TYPE",          "IdunBattle.Streams.GroupType",
     "IdunBattle.Streams", "GroupType"),
]

ASM = "IdunSharedAssembly.dll"

# Artefacts GENERES : une occurrence d'un nom mort y est une ligne de table, pas une citation de
# mecanique. On les isole pour que le vrai signal (code + prose) reste lisible.
GENERES = {
    "scripts/python/enum_maps.py",
    "scripts/python/engine/entities/active_ability_type.py",
    "scripts/python/engine/entities/effect_type.py",
    "scripts/python/engine/entities/triggered_ability_type.py",
    "scripts/python/engine/entities/damage_profile_type.py",
    "scripts/sql/006_ref_tables.sql",
    "scripts/sql/013_enum_fk_and_names.sql",
    "scripts/sql/014_stream_group.sql",
}

# Les mirrors `IntEnum` : MEME source, MEME generateur mort, donc MEME derive. Hors perimetre #275
# (qui vise `enum_maps.py`), mais mesures -- etape 4.
MIRRORS = [
    ("engine/entities/effect_type.py", "EffectType",
     "IdunBattle.Entities.Enum.EffectType"),
    ("engine/entities/triggered_ability_type.py", "TriggeredAbilityType",
     "IdunBattle.Entities.Enum.TriggeredAbilityType"),
    ("engine/entities/damage_profile_type.py", "DamageProfileType",
     "IdunBattle.Entities.Enum.DamageProfileType"),
    ("engine/entities/active_ability_type.py", "ActiveAbilityType",
     "IdunBattle.Entities.Enum.ActiveAbilityType"),
]

# La sonde et son regenerateur nomment eux-memes des noms morts : ne pas s'auto-compter.
IGNORE_CITATIONS = {
    "scripts/python/probe_275_enum_maps_drift.py",
    "scripts/python/regen_enum_maps.py",
    "scripts/python/probe_270_active_ability_type_drift.py",
    "scripts/python/regen_active_ability_tables.py",
}

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

def enum_natif(build: str, cle: str) -> dict[int, set[str]]:
    """{valeur: {noms}} depuis `data/symbols/<build>/frida/enums.tsv`.

    Un ENSEMBLE de noms : plusieurs membres partagent parfois une valeur (mesure sur
    `ActiveAbilityType` : 9999 porte `STRIPPED` ET `testAssetBundles`)."""
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


# --------------------------------------------------------------------------- le depot

def blocs_enum_maps() -> dict[str, dict[int, str]]:
    """{nom du bloc: {valeur: nom}} -- decoupe par tete `NOM = {`, corps `<int>: '<nom>'`."""
    src = _lire(MAPS)
    tetes = [(m.start(), m.group(1))
             for m in re.finditer(r"^([A-Z_][A-Z0-9_]*)\s*(?::[^=]*)?=\s*\{", src, re.M)]
    out: dict[str, dict[int, str]] = {}
    for i, (deb, nom) in enumerate(tetes):
        fin = tetes[i + 1][0] if i + 1 < len(tetes) else len(src)
        out[nom] = {int(m.group(1)): m.group(2)
                    for m in re.finditer(r"^\s*(-?\d+):\s*'([^']*)'", src[deb:fin], re.M)}
    return out


def fichiers_suivis() -> list[str]:
    out = subprocess.run(["git", "-C", str(REPO), "ls-files"],
                         capture_output=True, text=True, encoding="utf-8").stdout
    return out.splitlines()


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


def noms_du_gameconfig(build: str) -> set[str]:
    """Abilities + passifs + traits que le JEU configure, par NOM. Source INDEPENDANTE du dump
    d'enums : un nom vu ici est vivant cote donnees, meme s'il est mort dans SON enum."""
    p = build_dir(build) / "gameconfig.json"
    d = json.loads(p.read_text(encoding="utf-8"))
    cg = (d.get("clientGameConfig") or {})
    units = cg.get("units") or {}
    out: set[str] = set()
    for cle in ("abilities", "passiveAbilities", "traits", "effects"):
        v = units.get(cle)
        if isinstance(v, dict):
            out |= set(v)
        elif isinstance(v, list):
            out |= {x for x in v if isinstance(x, str)}
    return out


def table_mirror(rel: str, cls: str) -> dict[int, str]:
    """{valeur: nom} d'un mirror `IntEnum`. `None_` -> `None` (echappement de mot-clef)."""
    src = (REPO / "scripts" / "python" / rel).read_text(encoding="utf-8")
    deb = src.find("class %s(IntEnum):" % cls)
    if deb < 0:
        return {}
    out = {}
    for m in re.finditer(r"^\s{4}([A-Za-z_]\w*)\s*=\s*(-?\d+)\s*$", src[deb:], re.M):
        nom = m.group(1)
        out[int(m.group(2))] = nom[:-1] if nom == "None_" else nom
    return out


# --------------------------------------------------------------------------- live

def confront_live(bloc: str, ns: str, cls: str, natif: dict[int, set[str]]) -> int:
    """RPC `dumpEnum` sur la session Frida active. LECTURE SEULE -- aucun inject, aucun runner."""
    from rl_collect_batch import _resolve_session, _rpc  # import tardif : le host peut etre eteint
    sid = _resolve_session()
    rep = _rpc(sid, "dumpEnum", [{"asm": ASM, "ns": ns, "cls": cls}], timeout=30)
    vals = (rep.get("result") or {}).get("values")
    if not vals:
        print("    %-22s live : RPC sans valeurs -- %s" % (bloc, json.dumps(rep)[:160]))
        return 1
    live: dict[int, set[str]] = {}
    for nom, v in vals.items():
        live.setdefault(int(v), set()).add(nom)
    manque = sorted(set(natif) - set(live))
    trop = sorted(set(live) - set(natif))
    faux = {v: (sorted(natif[v]), sorted(live[v]))
            for v in sorted(set(live) & set(natif)) if natif[v] != live[v]}
    etat = "OK    " if not (manque or trop or faux) else "DIVERGE"
    print("    %s %-22s live=%-4d tsv=%-4d  tsv-sans-live=%d live-sans-tsv=%d noms-divergents=%d"
          % (etat, bloc, len(live), len(natif), len(manque), len(trop), len(faux)))
    for v in list(faux)[:6]:
        print("             %6d : tsv %s  live %s" % (v, faux[v][0], faux[v][1]))
    if manque[:6]:
        print("             tsv sans live : %s" % manque[:6])
    if trop[:6]:
        print("             live sans tsv : %s" % trop[:6])
    return 0 if not (manque or trop or faux) else 1


# --------------------------------------------------------------------------- main

def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--build", default=None, help="defaut : data/symbols/CURRENT")
    ap.add_argument("--lister", type=int, default=10, help="nb d'ecarts detailles par bloc")
    ap.add_argument("--citations", action="store_true",
                    help="detaille l'inventaire des citations, fichier par fichier")
    ap.add_argument("--live", action="store_true",
                    help="confronte au RPC dumpEnum (lecture seule ; host requis)")
    ap.add_argument("--rev", default=None,
                    help="lit enum_maps.py a cette revision git au lieu du disque")
    args = ap.parse_args()

    global _REV
    _REV = args.rev
    build = args.build or current_build()
    if _REV:
        print("enum_maps.py lu a la revision : %s" % _REV)
    print("build : %s" % build)
    print("")

    depot = blocs_enum_maps()
    natifs = {bloc: enum_natif(build, cle) for bloc, cle, _, _ in BLOCS}

    # ---- Etape 1 : les 6 blocs contre le natif
    print("ETAPE 1 -- les 6 blocs de enum_maps.py contre l'enum du build")
    derive = False
    renum_par_bloc: dict[str, dict[int, tuple[str, list[str]]]] = {}
    absents_par_bloc: dict[str, dict[int, str]] = {}
    for bloc, cle, _, _ in BLOCS:
        t = depot.get(bloc, {})
        natif = natifs[bloc]
        faux = {v: (t[v], sorted(natif[v])) for v in sorted(set(t) & set(natif))
                if t[v] not in natif[v]}
        absents = {v: t[v] for v in sorted(set(t) - set(natif))}
        manquants = sorted(set(natif) - set(t))
        renum_par_bloc[bloc] = faux
        absents_par_bloc[bloc] = absents
        etat = "OK    " if not (faux or absents or manquants) else "DERIVE"
        if faux or absents or manquants:
            derive = True
        print("  %s %-22s depot=%-4d jeu=%-4d  RENUMEROTES=%-3d absents-du-jeu=%-3d manquants=%d"
              % (etat, bloc, len(t), len(natif), len(faux), len(absents), len(manquants)))
        for v in list(faux)[:args.lister]:
            print("           %6d : le depot dit '%s'  le jeu dit %s"
                  % (v, faux[v][0], faux[v][1]))
        if len(faux) > args.lister:
            print("           ... (%d renumerotes de plus)" % (len(faux) - args.lister))
        if absents:
            ap_ = ", ".join("%d=%s" % (v, absents[v]) for v in sorted(absents)[:args.lister])
            print("           absents du jeu : %s%s"
                  % (ap_, " ..." if len(absents) > args.lister else ""))
        if manquants:
            mq = ", ".join("%d=%s" % (v, "|".join(sorted(natif[v])))
                           for v in manquants[:args.lister])
            print("           manquants (le jeu les porte, le depot non) : %s%s"
                  % (mq, " ..." if len(manquants) > args.lister else ""))
    print("")

    # ---- Etape 2 : COLLISIONS de valeur (le piege de #270, transpose)
    print("ETAPE 2 -- collisions : un id RENUMEROTE dont l'ancien nom vit ailleurs dans l'enum")
    n_coll = 0
    for bloc, cle, _, _ in BLOCS:
        natif = natifs[bloc]
        # {nom natif -> valeurs}
        par_nom: dict[str, list[int]] = {}
        for v, noms in natif.items():
            for n in noms:
                par_nom.setdefault(n, []).append(v)
        coll = {v: (anc, par_nom[anc]) for v, (anc, _) in renum_par_bloc[bloc].items()
                if anc in par_nom}
        # Les absents-du-jeu ne peuvent pas collisionner (leur valeur n'existe plus).
        if coll:
            n_coll += len(coll)
            print("  %-22s %d collision(s)" % (bloc, len(coll)))
            for v in sorted(coll):
                anc, vraies = coll[v]
                print("      le depot dit %d='%s' ; le jeu place '%s' en %s  -> tout consommateur"
                      % (v, anc, anc, vraies))
                print("        de l'id %d recoit un nom FAUX, et qui cite le nom '%s' vise %s"
                      % (v, anc, vraies))
    if not n_coll:
        print("  aucune collision : aucun nom perime ne survit a une AUTRE valeur.")
    print("")

    # ---- Etape 3 : citations des noms que la regeneration SUPPRIMERAIT
    perimes: dict[str, set[str]] = {}
    for bloc, _, _, _ in BLOCS:
        s = {anc for anc, _ in renum_par_bloc[bloc].values()}
        s |= set(absents_par_bloc[bloc].values())
        # Un nom qui existe TOUJOURS dans l'enum (a une autre valeur) n'est pas « perime » : le
        # citer par NOM reste juste. Seul le citer par ID est faux -- l'etape 2 s'en charge.
        vivants = {n for noms in natifs[bloc].values() for n in noms}
        perimes[bloc] = {n for n in s if n not in vivants}
    tous_perimes = {n for s in perimes.values() for n in s if n}
    print("ETAPE 3 -- citations des %d noms que la regeneration SUPPRIMERAIT" % len(tous_perimes))

    tous = tous_les_enums(build)
    cles_visees = {cle for _, cle, _, _ in BLOCS}
    cfg = noms_du_gameconfig(build)
    homonymes: dict[str, list[str]] = {}
    for nom in tous_perimes:
        ail = [e for e, m in tous.items()
               if e not in cles_visees and any(nom in s for s in m.values())]
        if nom in cfg:
            ail.append("gameconfig")
        if ail:
            homonymes[nom] = ail
    print("  dont HOMONYMES (le nom vit ailleurs : autre enum ou gameconfig) : %d / %d"
          % (len(homonymes), len(tous_perimes)))

    motifs = {n: re.compile(r"\b" + re.escape(n) + r"\b") for n in tous_perimes}
    par_classe: dict[str, int] = {}
    a_trancher: list[tuple[str, str, int, str, str]] = []
    for rel in fichiers_suivis():
        # `data/` est ENTIEREMENT hors sujet : ce sont les ENTREES du depot (`symbols/`, `boards/`,
        # `seed-bc.json`, `i2_en.json`). Un nom d'effet y apparait comme DONNEE DU JEU, jamais
        # comme citation a trancher -- et `i2_en.json` a lui seul noyait le signal (des centaines
        # d'occurrences de `Guard`, `Camouflage`...).
        if rel.startswith("data/") or rel in IGNORE_CITATIONS:
            continue
        try:
            txt = (REPO / rel).read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        candidats = [n for n in motifs if n in txt]
        if not candidats:
            continue
        for k, ligne in enumerate(txt.splitlines(), 1):
            for n in candidats:
                if not motifs[n].search(ligne):
                    continue
                c = ("GENERE" if rel in GENERES
                     else "HOMONYME" if n in homonymes
                     else "DOC" if rel.endswith(".md")
                     else "CODE")
                par_classe[c] = par_classe.get(c, 0) + 1
                if c in ("CODE", "DOC"):
                    a_trancher.append((n, rel, k, ligne.strip()[:150], c))
    print("  ventilation des occurrences : %s" % dict(sorted(par_classe.items())))
    code = [x for x in a_trancher if x[4] == "CODE"]
    doc = [x for x in a_trancher if x[4] == "DOC"]
    # Le signal, c'est CODE : une table ou une constante qui resoudra FAUX. La prose (`DOC`) ne
    # casse rien -- et elle est dominee par des mots courants (`Guard`, `Attack`) dans les
    # journaux de partie, qui ne parlent pas de l'enum. Elle n'est detaillee que sur demande.
    print("  A TRANCHER dans du CODE : %d occurrence(s)" % len(code))
    for nom, rel, k, txt, _ in sorted(code, key=lambda x: (x[1], x[2])):
        print("    %-34s %s:%d" % (nom, rel, k))
        if args.citations:
            print("        %s" % txt)
    print("  en PROSE (docs/skills) : %d occurrence(s) sur %d noms%s"
          % (len(doc), len({x[0] for x in doc}), " :" if args.citations else " (--citations)"))
    if args.citations:
        for nom, rel, k, txt, _ in sorted(doc, key=lambda x: (x[1], x[2])):
            print("    %-34s %s:%d" % (nom, rel, k))
    print("")

    # ---- Etape 4 : les mirrors voisins (informatif -- hors perimetre #275)
    print("ETAPE 4 -- VOISINS : les mirrors `engine/entities/*_type.py` (informatif, hors #275)")
    for rel, cls, cle in MIRRORS:
        t = table_mirror(rel, cls)
        if not t:
            print("  %-42s classe %s introuvable" % (rel, cls))
            continue
        natif = enum_natif(build, cle)
        faux = {v: (t[v], sorted(natif[v])) for v in sorted(set(t) & set(natif))
                if t[v] not in natif[v]}
        absents = sorted(set(t) - set(natif))
        manquants = sorted(set(natif) - set(t))
        etat = "OK    " if not (faux or absents or manquants) else "DERIVE"
        print("  %s %-42s depot=%-4d jeu=%-4d RENUMEROTES=%-3d absents=%-4d manquants=%d"
              % (etat, rel, len(t), len(natif), len(faux), len(absents), len(manquants)))
        for v in list(faux)[:4]:
            print("           %6d : le depot dit '%s'  le jeu dit %s"
                  % (v, faux[v][0], faux[v][1]))
    print("")

    # ---- Etape 5 : live
    if args.live:
        print("ETAPE 5 -- confrontation LIVE (dumpEnum ; lecture seule)")
        for bloc, _, ns, cls in BLOCS:
            if confront_live(bloc, ns, cls, natifs[bloc]):
                derive = True
        print("")

    if derive:
        print("AU MOINS UN BLOC DERIVE.")
        print("Reparateur : python scripts/python/regen_enum_maps.py --ecrire")
        print("Le generateur historique rl_gen_enum_columns.py lit data/dumps/<hash>/dump.cs,")
        print("SUPPRIME le 2026-07-25 : il ne peut plus tourner.")
        return 1
    print("les 6 blocs de enum_maps.py collent au build %s" % build)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
