"""#989 -- `CampaignGameModeSource` est-il resolvable AVANT toute bataille ?

Reponse etablie le 2026-08-12 sur le build `rnca9r7q6c` : NON. C'est un TRANSIENT
cree par bataille, pas une liaison de conteneur DI. Voir
`docs/rl/case-989-campaign-game-mode-source-transient.md`.

CE PROBE NE REFAIT PAS LA PREUVE -- il en re-derive les faisceaux qui sont
lisibles HORS LIGNE, pour qu'un futur build qui changerait l'architecture le dise
au lieu de laisser la case-doc se perimer en silence.

CE QU'IL MESURE (depuis les entrees VERSIONNEES de `data/symbols/<build>/`)
  1. la signature du ctor porte des parametres PER-BATAILLE -- un conteneur ne
     peut pas les fournir avant de savoir quelle bataille est lancee ;
  2. aucune des classes `*GameModeSource` n'expose d'accesseur STATIQUE
     (`get_Instance`, `get_Current`, `Resolve`, ...) ;
  3. aucun type de conteneur DI (Zenject, VContainer, Reflex, MS.DI, Autofac,
     Ninject) n'existe dans le binaire.

CE QU'IL NE MESURE PAS, ET C'EST L'ESSENTIEL DE LA PREUVE
  Le SITE DE CREATION. Le discriminant qui a tranche la question est la xref
  entrante du ctor -- `ViewCommandExecutor$$StartCampaignMatch` fait
  `il2cpp::vm::Object::New` puis appelle le ctor inline -- et une xref ne se lit
  que dans Ghidra, pas dans un TSV. Les trois faisceaux ci-dessus sont
  CONVERGENTS, pas concluants : c'est exactement le regime ou l'on se trompe.
  Un rouge ici dit << l'architecture a bouge, refais la RE >>, jamais << c'est
  devenu resolvable >>.

Usage :
    python probe_989_cgms_sans_liaison_di.py [--build <hash>]

rc 0 = les trois faisceaux tiennent ; rc 1 = au moins un a bouge ; rc 2 = entree
absente (rien n'est mesure -- jamais rabattu sur un vert).
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

RACINE = Path(__file__).resolve().parents[2]
SYMBOLES = RACINE / "data" / "symbols"

# La classe en cause, et la famille a laquelle elle appartient.
CLASSE = "IdunBattle.ViewLogic.BattleSource.CampaignGameModeSource"
SUFFIXE_FAMILLE = "GameModeSource"

# Les trois parametres du ctor qui decrivent LA BATAILLE LANCEE, pas une
# dependance. Lus dans `IdunBattle.ViewLogic.BattleSource.CampaignGameModeSource$$.ctor`
# (17 parametres, dont 14 interfaces). Leur presence est ce qui rend une liaison
# singleton structurellement impossible.
PARAMS_PER_BATAILLE = (
    "campaignId:System.String",
    "initialLocationIndex:System.Int32",
    "enemyIsAiControlled:System.Boolean",
)

# Un accesseur statique serait la forme qu'aurait un point de resolution.
# On cherche le NOM, sur toute methode statique d'une classe `*GameModeSource`.
NOMS_ACCESSEUR = (
    "get_Instance", "get_Current", "get_Default", "get_Active",
    "Resolve", "GetInstance", "Create", "CreateInstance", "Get",
)

# Les conteneurs DI qu'un projet Unity peut embarquer. Prefixes de NAMESPACE :
# `Zenject.DiContainer`, `VContainer.IObjectResolver`, ... On evite les
# sous-chaines nues (`Reflex` matcherait `ReflexionUtils`).
PREFIXES_CONTENEUR_DI = (
    "Zenject.",
    "VContainer.",
    "Reflex.",
    "Microsoft.Extensions.DependencyInjection.",
    "Autofac.",
    "Ninject.",
    "StrangeIoC.",
    "Extenject.",
)


def _build_courant(demande: str | None) -> str:
    if demande:
        return demande
    courant = SYMBOLES / "CURRENT"
    if not courant.exists():
        raise FileNotFoundError(f"absent : {courant}")
    return courant.read_text(encoding="utf-8").strip()


def _lignes(chemin: Path):
    """Rend les lignes utiles d'un TSV de dump, en sautant l'en-tete de provenance."""
    with chemin.open("r", encoding="utf-8", errors="replace") as fh:
        for ligne in fh:
            if ligne.startswith("#!"):
                continue
            ligne = ligne.rstrip("\n")
            if ligne:
                yield ligne


def etape_1_signature_ctor(methodes: Path) -> tuple[bool, list[str]]:
    """Le ctor porte-t-il encore ses parametres PER-BATAILLE ?"""
    journal: list[str] = []
    cible = f"{CLASSE}..ctor"
    trouve = None
    for ligne in _lignes(methodes):
        col = ligne.split("\t")
        if len(col) > 1 and col[1] == cible:
            trouve = col
            break
    if trouve is None:
        journal.append(f"  INTROUVABLE : {cible}")
        return False, journal

    params = trouve[5] if len(trouve) > 5 else ""
    nb = len([p for p in params.split(",") if p.strip()])
    journal.append(f"  ctor trouve, {nb} parametre(s)")
    ok = True
    for attendu in PARAMS_PER_BATAILLE:
        present = attendu in params
        journal.append(f"    {'OK  ' if present else 'PERDU'} {attendu}")
        ok = ok and present
    if ok:
        journal.append("  -> un conteneur ne peut pas fournir ces trois-la : "
                       "pas de singleton possible")
    return ok, journal


def etape_2_accesseurs_statiques(methodes: Path) -> tuple[bool, list[str]]:
    """Une classe `*GameModeSource` expose-t-elle un point de resolution statique ?"""
    journal: list[str] = []
    classes = set()
    suspects: list[str] = []
    for ligne in _lignes(methodes):
        col = ligne.split("\t")
        if len(col) < 4:
            continue
        classe, statique = col[2], col[3]
        if not classe.endswith(SUFFIXE_FAMILLE):
            continue
        classes.add(classe)
        if statique != "1":
            continue
        nom_court = col[1].rsplit(".", 1)[-1]
        if nom_court in NOMS_ACCESSEUR:
            suspects.append(f"{col[1]} (statique)")

    journal.append(f"  {len(classes)} classe(s) *{SUFFIXE_FAMILLE} dans le dump")
    if suspects:
        journal.append("  ACCESSEUR STATIQUE TROUVE -- une voie de resolution existe "
                       "peut-etre desormais :")
        for s in sorted(suspects):
            journal.append(f"    {s}")
        return False, journal
    journal.append("  aucun accesseur statique (get_Instance/Resolve/...) sur la famille")
    return True, journal


def etape_3_absence_de_conteneur(classes_tsv: Path) -> tuple[bool, list[str]]:
    """Un framework DI est-il embarque dans le binaire ?"""
    journal: list[str] = []
    trouves: list[str] = []
    total = 0
    for ligne in _lignes(classes_tsv):
        total += 1
        nom = ligne.split("\t")[0]
        for prefixe in PREFIXES_CONTENEUR_DI:
            if nom.startswith(prefixe):
                trouves.append(nom)
                break

    journal.append(f"  {total} type(s) balaye(s)")
    if trouves:
        journal.append("  CONTENEUR DI TROUVE -- l'architecture a change :")
        for t in sorted(trouves)[:20]:
            journal.append(f"    {t}")
        if len(trouves) > 20:
            journal.append(f"    ... et {len(trouves) - 20} de plus")
        return False, journal
    journal.append("  aucun type de conteneur DI (Zenject/VContainer/Reflex/"
                   "MS.DI/Autofac/Ninject)")
    return True, journal


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--build", default=None,
                    help="hash de build (defaut : data/symbols/CURRENT)")
    args = ap.parse_args()

    try:
        build = _build_courant(args.build)
    except FileNotFoundError as e:
        print(f"[989] PAS MESURE : {e}")
        return 2

    base = SYMBOLES / build / "frida"
    methodes, classes_tsv = base / "methods.tsv", base / "classes.tsv"
    for chemin in (methodes, classes_tsv):
        if not chemin.exists():
            print(f"[989] PAS MESURE : entree absente -> {chemin}")
            return 2

    print(f"[989] build = {build}")
    print(f"[989] question : `{CLASSE}` est-il resolvable AVANT toute bataille ?")
    print("[989] verdict etabli (2026-08-12, rnca9r7q6c) : NON -- TRANSIENT par bataille.")
    print("")

    etapes = (
        ("1. le ctor porte des parametres PER-BATAILLE",
         lambda: etape_1_signature_ctor(methodes)),
        ("2. aucun accesseur statique sur la famille *GameModeSource",
         lambda: etape_2_accesseurs_statiques(methodes)),
        ("3. aucun conteneur DI dans le binaire",
         lambda: etape_3_absence_de_conteneur(classes_tsv)),
    )

    tout_ok = True
    for titre, fn in etapes:
        ok, journal = fn()
        print(f"[989] {'PASS' if ok else 'FAIL'} -- {titre}")
        for ligne in journal:
            print(ligne)
        print("")
        tout_ok = tout_ok and ok

    print("[989] PORTEE DE LA MESURE -- ce que ce probe ne couvre PAS")
    print("  Le SITE DE CREATION, qui est le vrai discriminant. Il se lit par la xref")
    print("  entrante du ctor dans Ghidra -- `ViewCommandExecutor$$StartCampaignMatch`,")
    print("  qui alloue par `il2cpp::vm::Object::New` et appelle le ctor inline, puis")
    print("  enchaine `StartMatch` -> `thor.Loader$$LoadBattle` SANS point de sortie.")
    print("  Les trois etapes ci-dessus sont des faisceaux CONVERGENTS, pas la preuve.")
    print("  Un rouge dit << refais la RE >>, jamais << c'est devenu resolvable >>.")
    print("")
    print(f"[989] {'tous les faisceaux tiennent' if tout_ok else 'AU MOINS UN A BOUGE'}")
    return 0 if tout_ok else 1


if __name__ == "__main__":
    sys.exit(main())
