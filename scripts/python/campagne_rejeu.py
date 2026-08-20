"""REJOUER UN REPLAY DE CAMPAGNE SUR UNE BATAILLE VIVANTE -- la chaine ENTIERE, sous crans.

    python scripts/python/campagne_rejeu.py --replay logs/replay-she31-decode.json --confirmer

Le replay SUFFIT : le noeud s'en DERIVE. Rien d'autre a fournir.

(!)POURQUOI CE SCRIPT EXISTE, ET CE N'EST PAS DU CONFORT. La sequence a ete jouee a la main le
2026-08-20, en neuf gestes. Un seul a ete fait dans le mauvais ORDRE -- le seed arme APRES le
montage -- et le resultat a ete une bataille montee, demarree, INUTILISABLE, decouverte
seulement parce qu'on a pense a relire le journal du seed. Rien ne l'aurait signale.
`bataille_reference.py` porte deja cette lecon dans son en-tete : un jeton de boss de guilde a
ete perdu parce qu'un armement manuel avait ete oublie.

L'ORDRE DES MAILLONS *EST* LA PROPRIETE DE SURETE. Tant qu'il vit dans la tete de celui qui
conduit la seance et pas dans un script, il se reperdra.

## LES CRANS

    0. charger le replay          -- JSON brut OU base64+gzip, SNIFFE (jamais l'extension)
    1. router sur `GameMode`      -- Campaign ici ; GuildBoss = `bataille_reference.py`
    2. resoudre le noeud          -- par FORGE ET COMPARAISON, jamais par convention de nom
    3. sortir d'une bataille      -- si une tourne, le montage refuse
    4. ARMER LE SEED              -- AVANT le montage, conditionne a l'`Id`
    5. monter                     -- `sandbox_campagne.py`
    6. le seed A-T-IL MORDU ?     -- le cran qui manquait, celui qui a coute la soiree
    7. la phase                   -- `battleStatus.stageName`, PAS `ordreConversion`
    8. poser le deploiement       -- et le CONFRONTER avant tout cout d'entree
    9. START                      -- puis verifier qu'il a porte
   10. rejouer les coups          -- delegue a `replay_rejouer.py`

(!)LES COUPS SONT DELEGUES, PAS RECOPIES. `replay_rejouer.py` porte deja le cran d'appariement,
l'arret au premier ecart et l'affichage du delta par `Apply`. Le dupliquer ici ferait deux
verites a maintenir.

⛔ SANS `--confirmer` : LECTURE SEULE. Les crans 0 a 2 sont joues et affiches, rien n'est monte.
"""
import argparse
import json
import subprocess
import sys
import time
from pathlib import Path

RACINE = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(Path(__file__).resolve().parent))

from replay_format import charger as charger_replay        # noqa: E402
from replay_rejouer import (                               # noqa: E402
    Jeu, session_vivante, poses_du_replay, controler_avant_start,
)

# Les types de campagne, tels que `campaignSourceForger` les prend.
TYPES = [0, 1, 2, 3, 4]
NOM_TYPE = {0: "Standard", 1: "Elite", 2: "Mirror", 3: "EliteMirror", 4: "Event"}


def stop(msg, code=2):
    print()
    print("ARRET -- " + msg)
    sys.exit(code)


def cran(n, titre):
    print()
    print("CRAN %-2s -- %s" % (n, titre))


# ─────────────────────────────────────────────────────────────────────────────────────────────
# CRAN 2 : RESOUDRE LE NOEUD
#
# (!)ON NE DECODE PAS L'`Id`. `Campaign4_31` donne le noeud par son suffixe, mais son prefixe ne
# porte PAS le type : `elite4` et un eventuel `standard4` produiraient le meme texte. Deduire
# << Campaign4 => elite4 >> serait une convention SUPPOSEE, exactement le genre de raccourci que
# ce depot paie en silence.
#
# On FORGE donc chaque candidat et on compare la BC obtenue a celle du replay. La comparaison
# porte sur l'`Id` d'abord (rapide), puis sur la BC ENTIERE -- mesure du 2026-08-20 : 0 ecart
# entre la BC forgee et celle du replay, `SpawnPointSetIndex` compris.
#
# ⚠ ZERO CORRESPONDANCE OU PLUSIEURS => REFUS. On ne prend jamais << la premiere qui marche >>
# quand il y en a deux : ce serait choisir a la place de l'operateur, sans le dire.
# ─────────────────────────────────────────────────────────────────────────────────────────────

def noeud_du_id(bc_id):
    """Le numero de noeud, lu au SUFFIXE de l'`Id`. `None` s'il n'y en a pas."""
    if not isinstance(bc_id, str) or "_" not in bc_id:
        return None
    queue = bc_id.rsplit("_", 1)[1]
    return int(queue) if queue.isdigit() else None


def _gameconfig():
    """Le gameconfig VERSIONNE du build courant. LEVE en le nommant s'il manque.

    ⚠ IL SE PERIME SUR SON PROPRE AXE : le jeu telecharge sa config sans que la version du jeu
    bouge. Pour la STRUCTURE des campagnes le risque est faible, mais si une resolution parait
    fausse, c'est la premiere chose a re-verifier (cf. `gameconfig.PROVENANCE.txt`).
    """
    courant = RACINE / "data" / "symbols" / "CURRENT"
    if not courant.exists():
        stop("`data/symbols/CURRENT` absent -- on ne devine pas le build.")
    build = courant.read_text(encoding="utf-8").strip()
    f = RACINE / "data" / "symbols" / build / "gameconfig.json"
    if not f.exists():
        stop("gameconfig absent pour le build %s (%s)" % (build, f))
    return json.loads(f.read_text(encoding="utf-8")), build


def entrees_de_campagne():
    """Toutes les `(type, campagne, bataille)` du gameconfig.

    Structure : `clientGameConfig.battles.campaigns.<Type>[] -> {id, battles: [...]}`.
    """
    g, build = _gameconfig()
    try:
        camp = g["clientGameConfig"]["battles"]["campaigns"]
    except (KeyError, TypeError):
        stop("`clientGameConfig.battles.campaigns` absent du gameconfig %s" % build)
    ordinal = {nom: t for t, nom in NOM_TYPE.items()}
    out = []
    for nom_type, liste in camp.items():
        t = ordinal.get(nom_type)
        if t is None or not isinstance(liste, list):
            continue
        for c in liste:
            for b in (c.get("battles") or []):
                out.append((t, c.get("id"), b))
    return out, build


def candidats_du_catalogue(jeu):
    """Les couples `(campagne, type)` du gameconfig. `None` = PAS MESURE (jamais une liste vide,
    qui se lirait << aucune campagne >>).

    (!)LE CATALOGUE A DEUX NIVEAUX, et le premier n'est PAS ce qu'on croit. Mesure du
    2026-08-20 : ses cles de tete sont les TYPES (`Standard`, `Elite`, `Mirror`, `EliteMirror`,
    `Event`) -- les identifiants de campagne (`elite4`...) sont un cran en dessous. La premiere
    version les lisait au niveau 0 et essayait `Elite` comme s'il s'agissait d'une campagne :
    25 forges, 0 correspondance, alors qu'`elite4` matche du premier coup.

    Bon effet de bord : le type se LIT ici, il ne se cherche plus. On passe d'un produit
    cartesien (campagnes x 5 types) a un couple exact par campagne.
    """
    r = jeu.rpc("dumpCampaignCatalog", [{}], timeout=180000)
    if not isinstance(r, dict) or not r.get("json"):
        return None, "catalogue NON LU : %s" % json.dumps(r, ensure_ascii=False)[:200]
    try:
        cat = json.loads(r["json"])
    except Exception as e:  # noqa: BLE001
        return None, "catalogue ILLISIBLE (%s)" % e
    if not isinstance(cat, dict):
        return None, ("forme de catalogue non reconnue (%s) : %s"
                      % (type(cat).__name__, json.dumps(cat, ensure_ascii=False)[:200]))
    ordinal = {nom: t for t, nom in NOM_TYPE.items()}
    couples = []
    for cle, sous in cat.items():
        t = ordinal.get(cle)
        if t is None:
            # Un type inconnu n'est pas une erreur : on l'essaie sur TOUS les ordinaux plutot
            # que de le jeter -- mais on le DIT, pour que l'angle mort se voie.
            print("   (!) type de campagne inconnu au catalogue : `%s` -- essaye sur les %d "
                  "ordinaux" % (cle, len(TYPES)))
            noms = ([k for k in sous] if isinstance(sous, dict) else [])
            couples += [(n, tt) for n in noms for tt in TYPES]
            continue
        if isinstance(sous, dict):
            couples += [(n, t) for n in sous.keys() if isinstance(n, str)]
        elif isinstance(sous, list):
            for e in sous:
                if isinstance(e, dict):
                    v = e.get("id") or e.get("Id") or e.get("campaignId")
                    if isinstance(v, str):
                        couples.append((v, t))
    if not couples:
        return None, ("aucun identifiant sous les %d cle(s) de tete (%s)"
                      % (len(cat), ", ".join(list(cat)[:8])))
    return sorted(set(couples)), None


def forger_bc(jeu, campagne, type_, index):
    """Forger la BC d'un candidat. Rend `(bc, None)` ou `(None, motif)`."""
    r = jeu.rpc("campaignSourceForger",
                [{"campaignType": type_, "campaignId": campagne,
                  "locationIndex": index, "confirmer": True}], timeout=180000)
    if not isinstance(r, dict) or r.get("ok") is False:
        return None, json.dumps(r, ensure_ascii=False)[:160]
    b = jeu.rpc("campaignSourceBc", [{"confirmer": True}], timeout=180000)
    if not isinstance(b, dict) or b.get("ok") is False:
        return None, json.dumps(b, ensure_ascii=False)[:160]
    bc = b.get("bc") if isinstance(b.get("bc"), dict) else None
    if bc is None and isinstance(b.get("json"), str):
        try:
            bc = json.loads(b["json"])
        except Exception:  # noqa: BLE001
            bc = None
    if bc is None:
        return None, "BC absente de la reponse (%s)" % json.dumps(b, ensure_ascii=False)[:160]
    return bc, None


def ordonner_candidats(couples, bc_id):
    """Les candidats les plus PLAUSIBLES d'abord -- pour que le MATCH s'affiche tot, jamais
    pour trancher. Tous sont essayes de toute facon : c'est la comparaison qui decide, et il
    faut le balayage COMPLET pour pouvoir detecter une ambiguite."""
    chiffres = "".join(c for c in (bc_id or "") if c.isdigit())
    def score(cple):
        c, t = cple
        return (0 if chiffres and chiffres[0] in c else 1, c, t)
    return sorted(couples, key=score)


def resoudre_hors_ligne(d, bc_id):
    """(campagne, type, noeud) -- LU dans le gameconfig versionne. Aucun RPC, aucune forge.

    (!)COMMENT UNE BC ACQUIERT SON `Id`, LU DANS LE NATIF.
    `Idun.Source.IdunBattle.View.BattleConfigBuilder$$GetCampaignLevelConfig` le construit ainsi :

        Id = String.Format(<format>, CampaignConfigDto.campaignId,   // Int32, +0x10
                                     CampaignConfigDto.battleId)     // String, +0x18

    `campaignId` est un NUMERO, et le TYPE de campagne n'entre pas dans la formule. L'`Id` est
    donc LOSSY PAR CONSTRUCTION : mesure du 2026-08-20, `Campaign4_31` designe QUATRE batailles
    (`campaign4`/Standard, `mirror4`/Mirror, `elite4`/Elite, `eliteMirror4`/EliteMirror). Aucune
    astuce ne recupere la campagne depuis l'`Id` seul -- il faut une autre cle.

    (!)ET LE TYPE N'EST NULLE PART AILLEURS DANS LE REPLAY -- CHERCHE, PAS SUPPOSE. Trois
    controles independants, le 2026-08-20 :
      1. `campaignId` vaut **4 pour les quatre types** (mesure sur le gameconfig) : l'entier de
         l'`Id` est un numero de campagne, il n'encode pas la difficulte ;
      2. aucun champ SCALAIRE de la `BattleConfiguration` ni de la racine du replay ne porte de
         type de campagne (15 + 10 champs passes en revue) ;
      3. `MetaData.Data`, le seul emplacement libre, vaut `''` sur les CINQ replays disponibles
         -- y compris les TROIS captures reelles de boss de guilde, pas seulement les sandbox.
    Le type est donc perdu a l'ecriture, et il faut le rechercher ailleurs que dans le replay.

    (!)ET CETTE CLE EST DANS LE MEME DTO, DONC HORS LIGNE. `BoardId` suffit : sur ces quatre,
    il vaut `C4_01`, `C4_54`, `MC4_01`, `C4_59`. Une lecture de fichier remplace donc les 28
    forges et les 4 BC chargees de la premiere version -- qui prenaient 10 s et sollicitaient un
    jeu vivant pour une question entierement statique.
    """
    # (!)UN REPLAY EXISTE SOUS DEUX FORMES, ET LE PLATEAU CHANGE DE PLACE ENTRE LES DEUX.
    #
    # `ReplaySerializer$$SerializeReplay(replay, alleger)` fait, quand `alleger` est vrai :
    #     Replay.BoardId             = Replay.BC.Board.Id   (+0x68 -> +0x10, remonte a +0x30)
    #     Replay.BC.Board  (+0x68)   = null                 (le plateau ENTIER est jete)
    #     Replay.BC.Tiles  (+0x88)   = null                 (et le catalogue de tuiles)
    # puis `Json.SerializeObject` -> `ZipUtil.GzipCompress` -> `Convert.ToBase64String`.
    #
    # C'est la forme qui part au SERVEUR : il connait le plateau par son identifiant et en
    # re-derive la geometrie. Nos captures locales, elles, sont NON allegees -- `BoardId` y est
    # nul et le `Board` complet. Lire un seul des deux emplacements fait donc REFUSER la moitie
    # des replays, selon leur provenance.
    bc_ = d.get("BattleConfiguration") or {}
    board = d.get("BoardId") or (bc_.get("Board") or {}).get("Id")
    sps = bc_.get("SpawnPointSetIndex")
    entrees, build = entrees_de_campagne()
    print("   gameconfig %s : %d bataille(s) de campagne" % (build, len(entrees)))
    if board is None:
        stop("le replay ne porte pas de `BattleConfiguration.Board.Id` -- rien a apparier.")

    # (!)LA CASSE DES CLES DU GAMECONFIG N'EST PAS CELLE DES CHAMPS C#. Le DTO declare `boardId`
    # et `spawnPointsSet` ; le JSON porte `BoardId` et `SpawnPointsSet`. Chercher avec les noms
    # C# rend ZERO candidat -- faute commise, et elle se lit comme << ce noeud n'existe pas >>.
    def cle(b, *noms):
        for n in noms:
            if n in b:
                return b[n]
        return None

    par_id = [(t, c, b) for (t, c, b) in entrees
              if "Campaign%s_%s" % (cle(b, "campaignId"), cle(b, "battleId")) == bc_id]
    if not par_id:
        stop("aucune bataille du gameconfig ne porte l'`Id` `%s`. Le replay vient peut-etre "
             "d'un autre build, ou le gameconfig versionne est perime." % bc_id)
    print("   %d bataille(s) portent `%s`" % (len(par_id), bc_id))

    exacts = [(t, c, b) for (t, c, b) in par_id if cle(b, "BoardId", "boardId") == board]
    for t, c, b in par_id:
        print("      %-12s %-14s Board=%-8s SPS=%-3s %s"
              % (NOM_TYPE.get(t, "?"), c, cle(b, "BoardId", "boardId"),
                 cle(b, "SpawnPointsSet", "spawnPointsSet"),
                 "<<< le replay" if (t, c, b) in exacts else ""))
    if len(exacts) > 1:
        exacts = [x for x in exacts
                  if cle(x[2], "SpawnPointsSet", "spawnPointsSet") == sps] or exacts
    if not exacts:
        stop("aucune des %d batailles d'`Id` `%s` n'a le plateau `%s` du replay."
             % (len(par_id), bc_id, board))
    if len(exacts) > 1:
        stop("%d batailles restent indiscernables (meme `Id`, meme plateau, meme "
             "`SpawnPointsSet`) : %s. Donner `--campagne` et `--type`."
             % (len(exacts), [(c, t) for t, c, _ in exacts]))
    t, campagne, b = exacts[0]
    noeud = int(cle(b, "battleId"))
    return campagne, t, noeud


def resoudre_noeud(jeu, d, bc_id, campagne_forcee, type_force):
    """(campagne, type, noeud) -- DERIVE et CONFIRME, jamais suppose."""
    noeud = noeud_du_id(bc_id)
    if noeud is None:
        stop("l'`Id` du replay (%s) ne porte pas de numero de noeud en suffixe -- on ne devine "
             "pas le noeud." % bc_id)
    index = noeud - 1
    print("   noeud = %d (index %d), lu au suffixe de `%s`" % (noeud, index, bc_id))

    if campagne_forcee is not None:
        couples = [(campagne_forcee, type_force if type_force is not None else 1)]
        print("   candidat IMPOSE : %s type=%s -- il sera confirme quand meme"
              % (campagne_forcee, couples[0][1]))
    else:
        couples, motif = candidats_du_catalogue(jeu)
        if couples is None:
            stop("catalogue de campagnes NON MESURE, donc aucun candidat : %s\n"
                 "         Donner `--campagne` (et `--type`) pour court-circuiter la "
                 "resolution." % motif)
        print("   %d couple(s) (campagne, type) au catalogue" % len(couples))
        couples = ordonner_candidats(couples, bc_id)

    # ⚠ L'`Id` NE SUFFIT PAS A DESIGNER UNE BATAILLE, ET C'EST MESURE. Le 2026-08-20,
    # `Campaign4_31` est rendu par QUATRE couples : `campaign4`/Standard, `elite4`/Elite,
    # `mirror4`/Mirror, `eliteMirror4`/EliteMirror. Le type n'entre pas dans l'`Id`. Une
    # convention << Campaign4 => elite4 >> aurait donc tire a pile ou face entre quatre
    # batailles dont trois portent d'autres ennemis.
    #
    # Ce qui les SEPARE, c'est la BC entiere -- qu'on forge de toute facon. On s'en sert donc
    # comme DISCRIMINANT, pas comme simple controle de fin.
    ref = d.get("BattleConfiguration") or {}
    trouves, essais = [], 0
    for campagne, type_ in couples:
        essais += 1
        bc, motif = forger_bc(jeu, campagne, type_, index)
        if bc is None:
            continue
        if bc.get("Id") != bc_id:
            continue
        ecarts = [k for k in sorted(set(ref) | set(bc))
                  if json.dumps(ref.get(k), sort_keys=True) != json.dumps(bc.get(k),
                                                                         sort_keys=True)]
        trouves.append((campagne, type_, ecarts))
        print("   Id match  %-14s type=%d (%-11s) -> %d ecart(s) de BC   [forge %d]"
              % (campagne, type_, NOM_TYPE.get(type_, "?"), len(ecarts), essais))
    print("   %d forge(s) tentee(s), %d correspondance(s) d'Id" % (essais, len(trouves)))
    if not trouves:
        # (!)UN REFUS DIT CE QU'IL A REGARDE. Sans la liste, << aucune correspondance >> se lit
        # comme << ce noeud n'existe pas >>, alors que la cause mesuree le 2026-08-20 etait tout
        # autre : les identifiants du CATALOGUE ne sont pas ceux qu'attend `campaignSourceForger`
        # (`elite4` matche, et n'est dans aucune des 5 entrees du catalogue).
        stop("AUCUN des %d candidat(s) essaye(s) ne produit `%s` au noeud %d.\n"
             "         candidats : %s\n"
             "         Si l'identifiant attendu (ex. `elite4`) n'est pas dans cette liste, "
             "c'est le CATALOGUE qui parle un autre langage que `campaignSourceForger` --\n"
             "         donner `--campagne` et `--type`, qui restent confirmes par forge."
             % (len(couples), bc_id, noeud,
                ", ".join(sorted({c for c, _ in couples})) or "aucun"))
    # LE DISCRIMINANT : le MOINS d'ecarts de BC. Une egalite au sommet est une ambiguite REELLE
    # -- deux batailles indiscernables par leur configuration -- et elle REFUSE.
    mini = min(len(e) for _, _, e in trouves)
    meilleurs = [t for t in trouves if len(t[2]) == mini]
    if len(meilleurs) > 1:
        stop("%d couples produisent `%s` avec le MEME nombre d'ecarts de BC (%d) : %s.\n"
             "         Ils sont indiscernables par la BC -- on ne choisit pas a ta place. "
             "Donner `--campagne` et `--type`."
             % (len(meilleurs), bc_id, mini, [(c, t) for c, t, _ in meilleurs]))
    campagne, type_, ecarts = meilleurs[0]
    if ecarts:
        # (!)UN ECART NON NUL NE DESIGNE PAS UNE ERREUR, mais il PRECEDE toute divergence de
        # rejeu : si les coups divergent ensuite, c'est ICI qu'il faut regarder d'abord.
        print("   (!) meilleur candidat %s type=%d, mais %d ecart(s) de BC : %s"
              % (campagne, type_, len(ecarts), ", ".join(ecarts[:12])))
        print("       Toute divergence de rejeu devra d'abord etre imputee A CA.")
    else:
        print("   %s type=%d (%s) : BC IDENTIQUE a celle du replay, cle a cle."
              % (campagne, type_, NOM_TYPE.get(type_, "?")))
    return campagne, type_, noeud


def nom_canonique(mode, bc_id, campagne=None, noeud=None, seed=None):
    """LE NOM PORTE L'IDENTIFICATION -- lire le fichier ne doit pas etre necessaire.

        campagne    <campagne>_<noeud>-<seed>     elite4_31-1968318669.json
        boss        <BC.Id>-<seed>                GuildBoss10Boss1AdmecBelisarius-42.json

    (!)POUR LA CAMPAGNE, CE N'EST PAS L'`Id`. Mesure du 2026-08-20 : `Campaign4_31` est produit
    par QUATRE couples (`campaign4`/Standard, `elite4`/Elite, `mirror4`/Mirror,
    `eliteMirror4`/EliteMirror) -- le type n'entre pas dans la formule de l'`Id`
    (`BattleConfigBuilder$$GetCampaignLevelConfig` : `String.Format(fmt, campaignId, battleId)`).
    Un fichier nomme `Campaign4_31` collerait donc la meme etiquette sur quatre batailles
    differentes, et rendrait le repertoire inutilisable au moment precis ou il grossit.

    (!)ET LE SEED N'EST PAS DECORATIF. Sans lui, deux passages sur le MEME noeud produisent le
    meme nom : comme on refuse d'ecraser une reference, le second ne serait jamais range -- en
    disant << DEJA LA >>, ce qui se lit comme un succes. Le seed est intrinseque au replay et
    distingue les instances sans rien inventer.
    """
    queue = "" if seed is None else "-%s" % seed
    if mode == "Campaign":
        if not campagne or noeud is None:
            return None      # NON RESOLU -- on ne fabrique pas un nom ambigu
        return "%s_%d%s" % (campagne, noeud, queue)
    return "%s%s" % (bc_id, queue)


COLONNES = ["fichier", "campagne", "type", "noeud", "bcId", "board", "spawn",
            "seed", "provenance", "build", "role"]


def ranger_le_replay(d, mode, nom, source, infos, brut=None):
    """Ranger le replay sous son nom canonique, avec sa ligne de registre. N'ECRASE JAMAIS.

    (!)CE QU'ON ECRIT MAINTENANT PARCE QU'UNE RELECTURE NE LE RETROUVERA PLUS. La campagne se
    RE-DERIVE aujourd'hui (`BoardId` -> gameconfig), mais elle depend du gameconfig DU JOUR : si
    un noeud est rebalance ou un plateau reaffecte, la meme lecture rendra autre chose, ou rien.
    Les colonnes `campagne`/`type`/`noeud` figent donc la resolution, et `build` dit QUELLE
    version l'a etablie. C'est l'exact pendant de la colonne `rank` du registre boss, que le
    README nomme comme la seule qu'on ne peut pas retrouver apres coup.

    (!)ET LE BRUT SE GARDE AUSSI. Un `.replay.txt` est `base64(gzip(JSON))` ; le decode est
    commode mais c'est une TRANSFORMATION. Le jeu fait tourner son repertoire : le brut n'est
    recuperable que le jour meme.
    """
    if nom is None:
        stop("nom canonique NON RESOLU -- on ne range pas sous un nom ambigu.")
    dossier = RACINE / "data" / "replays" / ("campaign" if mode == "Campaign" else "guild-boss")
    dossier.mkdir(parents=True, exist_ok=True)

    ecrits = []
    cible = dossier / (nom + ".json")
    # ⛔ JAMAIS D'ECRASEMENT. Un replay est une REFERENCE : le reecrire, meme par une capture
    # qu'on croit identique, detruit le seul temoin dont on dispose.
    if cible.exists():
        print("   DEJA LA : %s (inchange)" % cible.relative_to(RACINE))
    else:
        cible.write_text(json.dumps(d, ensure_ascii=False), encoding="utf-8")
        ecrits.append(cible)
        print("   ecrit  : %s   (depuis %s)" % (cible.relative_to(RACINE), Path(source).name))

    if brut is not None:
        b = Path(brut)
        if not b.is_absolute():
            b = (RACINE / b).resolve()
        cible_brute = dossier / (nom + ".replay.txt")
        if cible_brute.exists():
            print("   DEJA LA : %s (inchange)" % cible_brute.relative_to(RACINE))
        elif not b.exists():
            print("   (!) brut INTROUVABLE : %s -- rien copie" % b)
        else:
            cible_brute.write_text(b.read_text(encoding="utf-8"), encoding="utf-8")
            ecrits.append(cible_brute)
            print("   ecrit  : %s   (brut, depuis %s)"
                  % (cible_brute.relative_to(RACINE), b.name))

    # LE REGISTRE. Une ligne par fichier ; on n'en reecrit jamais une existante.
    reg = dossier / "registre.tsv"
    lignes = reg.read_text(encoding="utf-8").splitlines() if reg.exists() else []
    if not lignes:
        lignes = ["\t".join(COLONNES)]
    deja = {l.split("\t", 1)[0] for l in lignes[1:] if l.strip()}
    for f in ([cible] + ([dossier / (nom + ".replay.txt")] if brut is not None else [])):
        if not f.exists() or f.name in deja:
            continue
        role = "reference" if f.suffix == ".json" else "meme replay, base64+gzip brut"
        lignes.append("\t".join([
            f.name, str(infos.get("campagne")), NOM_TYPE.get(infos.get("type"), "?"),
            str(infos.get("noeud")), str(infos.get("bcId")), str(infos.get("board")),
            str(infos.get("spawn")), str(infos.get("seed")), str(infos.get("provenance")),
            str(infos.get("build")), role]))
        deja.add(f.name)
    reg.write_text("\n".join(lignes) + "\n", encoding="utf-8")
    print("   registre : %s (%d ligne(s))" % (reg.relative_to(RACINE), len(lignes) - 1))

    if ecrits:
        print("   ⚠ INDEXER MAINTENANT -- un fichier non suivi sous `data/` n'est protege par "
              "RIEN (git clean l'efface sans trace) :")
        print("     git add " + " ".join(str(f.relative_to(RACINE)).replace("\\", "/")
                                         for f in ecrits + [reg]))
    return cible


# ─────────────────────────────────────────────────────────────────────────────────────────────

def sortir_de_bataille(jeu, confirmer):
    p = jeu.rpc("sandboxProbe", [], timeout=120000)
    if not isinstance(p, dict):
        stop("`sandboxProbe` NON MESURE : %s" % json.dumps(p, ensure_ascii=False)[:200])
    if not p.get("instance"):
        print("   hors bataille.")
        return
    print("   une bataille TOURNE (instance=%s)." % p.get("instance"))
    if not confirmer:
        stop("il faut en sortir, et c'est une ECRITURE : relancer avec `--confirmer`.", 3)
    r = jeu.rpc("retreatInvoke",
                [{"methode": "OnBattleSurrender", "confirmer": True}], timeout=180000)
    if not isinstance(r, dict) or not r.get("ok"):
        stop("la retraite a ECHOUE : %s" % json.dumps(r, ensure_ascii=False)[:240])
    # (!)UN `ok` D'APPEL N'EST PAS UN EFFET. On relit, et on exige AUSSI le repos du loader :
    # injecter ou monter pendant une transition est ce qui a fige le jeu deux fois le 19.
    for _ in range(20):
        time.sleep(1.5)
        p = jeu.rpc("sandboxProbe", [], timeout=120000)
        l = jeu.rpc("loaderStatus", [], timeout=120000)
        if (isinstance(p, dict) and not p.get("instance")
                and isinstance(l, dict) and l.get("etape") == 0
                and l.get("chargementEnCours") is False):
            print("   SORTIE confirmee, loader au repos.")
            return
    stop("sortie NON CONFIRMEE apres 30 s (ou loader encore en chargement).")


def armer_le_seed(jeu, graine, bc_id):
    """(!)AVANT LE MONTAGE, ET CONDITIONNE. Sans `siConfigId`, le seed partirait sur la
    PROCHAINE bataille quelle qu'elle soit. Avec, entrer ailleurs est SANS CONSEQUENCE."""
    if graine is None:
        stop("le replay ne porte pas de `RngSeed` -- on ne rejoue pas sans.")
    av = jeu.rpc("sandboxModeSeed", [{}], timeout=120000)
    n_av = len((av or {}).get("journal") or []) if isinstance(av, dict) else None
    if n_av is None:
        stop("journal du seed NON MESURE -- on ne saurait pas dire s'il a mordu.")
    r = jeu.rpc("sandboxModeSeed",
                [{"seed": int(graine), "unCoup": True, "siConfigId": bc_id}], timeout=120000)
    if not isinstance(r, dict) or r.get("arme") is not True:
        stop("le seed n'a PAS ete arme : %s" % json.dumps(r, ensure_ascii=False)[:240])
    print("   seed %s arme (un coup), CONDITIONNE a Id=%s -- journal a %d entree(s) avant"
          % (graine, bc_id, n_av))
    return n_av


def verifier_morsure(jeu, n_av, graine):
    """LE CRAN QUI MANQUAIT. Un seed arme APRES le montage laisse une bataille montee, demarree
    et inutilisable -- sans le moindre signal. Ici, l'absence d'entree ARRETE."""
    j = jeu.rpc("sandboxModeSeed", [{}], timeout=120000)
    entrees = (j or {}).get("journal") if isinstance(j, dict) else None
    if entrees is None:
        stop("journal du seed NON MESURE apres montage -- ce n'est PAS << il a mordu >>.")
    neuves = entrees[n_av:]
    if not neuves:
        stop("le seed n'a PAS ete impose : `IdunRunner$$Initialize` n'a rien journalise.\n"
             "         La bataille montee tourne donc sur un AUTRE tirage que le replay ; "
             "la rejouer ne mesurerait rien.")
    imposee = [e for e in neuves if e.get("par") == int(graine)]
    if not imposee:
        stop("le journal porte %d entree(s) neuve(s), mais aucune n'impose %s : %s"
             % (len(neuves), graine, json.dumps(neuves, ensure_ascii=False)[:240]))
    print("   seed IMPOSE : %s" % json.dumps(imposee[0], ensure_ascii=False))


def verifier_phase_avant_start(jeu):
    """(!)LE TEMOIN EST `battleStatus.stageName`, PAS `ordreConversion`.

    `deploymentEtat.ordreConversion` lit `IdunGameViews$$GetPlaceholderUnitViews()`, qui N'EST
    PAS VIDEE apres conversion : une bataille DEJA demarree rend donc une liste de cinq vues,
    identique a celle d'une phase de deploiement. Mesure du 2026-08-20 -- c'est exactement ce
    qui a fait prendre une bataille en cours pour un deploiement en attente.
    """
    b = jeu.rpc("battleStatus", [{}], timeout=120000)
    if not isinstance(b, dict) or not b.get("ok"):
        stop("`battleStatus` NON MESURE : %s" % json.dumps(b, ensure_ascii=False)[:200])
    stage = b.get("stageName")
    if stage == "Running":
        stop("la bataille est DEJA `Running` (%s unites) : le deploiement est passe, il est "
             "trop tard pour le poser. Remonter." % b.get("unitsAlive"))
    print("   phase = %s (pas `Running`) -- le deploiement est encore ouvert." % stage)


def poser_le_deploiement(jeu, d):
    """Poser, puis CONFRONTER. Les deux ordres sont essayes, et on DIT lequel a porte.

    (!)<< POSER A L'ENVERS >> N'EST PAS UNE REGLE, et n'est pas ecrit comme telle. Ca ne vaut
    que si le clear vient de liberer autant de paires qu'on repose. Ce qui est fiable, c'est de
    VERIFIER -- donc on essaie, on relit `ordreConversion`, et on recommence dans l'autre sens
    si besoin.
    """
    voulu = poses_du_replay(d)
    if voulu is None:
        stop("poses du replay NON LISIBLES -- on ne pose rien a l'aveugle.")
    for etiquette, suite in (("INVERSE de l'ordre du replay", list(reversed(voulu))),
                             ("ordre du replay", list(voulu))):
        poses = [{"unitId": u, "playerId": 11, "col": c, "row": r} for (u, c, r) in suite]
        jeu.rpc("deploymentMemoire", [{"poser": {"poses": poses, "mow": None}}], timeout=120000)
        r = jeu.rpc("deploymentMemoire",
                    [{"rejouer": True, "confirmer": True}], timeout=180000)
        if not isinstance(r, dict) or not r.get("ok"):
            stop("le rejeu de memoire a ECHOUE : %s" % json.dumps(r, ensure_ascii=False)[:240])
        time.sleep(2.0)
        ok, motif = controler_avant_start(jeu, d)
        print("   pose en %-28s -> %s" % (etiquette, motif.split("\n")[0]))
        if ok:
            return etiquette
    stop("aucun des deux ordres de pose ne rend l'ordre de conversion du replay. NE PAS "
         "demarrer : les squads seraient attribues autrement et chaque coup frapperait une "
         "autre unite.")


def demarrer(jeu, attendus):
    r = jeu.rpc("deploymentStartInvoquer", [{"confirmer": True}], timeout=180000)
    if not isinstance(r, dict) or not r.get("ok"):
        stop("le START a ECHOUE : %s" % json.dumps(r, ensure_ascii=False)[:240])
    time.sleep(3.0)
    # (!)L'APPEL PASSE NE DIT RIEN DU DEMARRAGE -- son propre retour le dit. On verifie par
    # l'etat ET par le compte de pas de mise en place.
    b = jeu.rpc("battleStatus", [{}], timeout=120000)
    if not isinstance(b, dict) or b.get("stageName") != "Running":
        stop("apres START, la bataille n'est pas `Running` : %s"
             % json.dumps(b, ensure_ascii=False)[:240])
    s = jeu.rpc("replaySteps", [{"maxSteps": 200}], timeout=180000)
    pas = (s or {}).get("steps") if isinstance(s, dict) else None
    if pas is None:
        stop("`replaySteps` NON MESURE apres START.")
    if len(pas) != attendus:
        stop("%d pas de mise en place enregistres, %d attendus par le replay -- la BC ou le "
             "deploiement differe." % (len(pas), attendus))
    print("   `Running`, %d pas de mise en place (conforme au replay)." % len(pas))


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--replay", required=True,
                    help="le replay -- JSON brut ou base64+gzip, le format est SNIFFE")
    ap.add_argument("--hote", default="http://127.0.0.1:8765")
    ap.add_argument("--session", type=int, default=None)
    ap.add_argument("--campagne", default=None,
                    help="court-circuite la resolution (confirmee quand meme)")
    ap.add_argument("--type", type=int, default=None, help="0=Standard 1=Elite 2=Mirror ...")
    ap.add_argument("--par-forge", dest="par_forge", action="store_true",
                    help="resoudre en FORGEANT chaque candidat et en comparant la BC entiere "
                         "(exige le jeu, ~10 s). Le defaut lit le gameconfig versionne.")
    ap.add_argument("--ranger", action="store_true",
                    help="ecrire le replay sous son nom canonique dans `data/replays/`, avec sa "
                         "ligne de registre (n'ecrase JAMAIS un fichier existant)")
    ap.add_argument("--brut", default=None,
                    help="le meme replay en base64+gzip, range a cote sous `.replay.txt`. Le "
                         "jeu fait tourner son repertoire : le brut n'est recuperable que le "
                         "jour meme.")
    ap.add_argument("--confirmer", action="store_true",
                    help="sans lui : lecture seule, rien n'est monte ni demarre")
    args = ap.parse_args(argv)

    cran(0, "charger le replay -- le format est SNIFFE, jamais deduit de l'extension")
    chemin = Path(args.replay)
    if not chemin.is_absolute():
        chemin = (RACINE / chemin).resolve()
    d, forme = charger_replay(chemin)
    bc = d.get("BattleConfiguration") or {}
    bc_id, mode, graine = bc.get("Id"), bc.get("GameMode"), d.get("RngSeed")
    n_pose = len(poses_du_replay(d) or [])
    print("   %s (%s)" % (chemin.name, forme))
    print("   Id=%s  GameMode=%s  seed=%s  poses=%d  pas=%d"
          % (bc_id, mode, graine, n_pose, len(d.get("Messages") or [])))

    cran(1, "router sur `GameMode` -- c'est LUI le discriminant, pas la forme de l'`Id`")
    if mode != "Campaign":
        stop("`GameMode=%s` : ce script ne monte que la CAMPAGNE. Pour un boss de guilde, la "
             "voie est `bataille_reference.py` (il attend que tu entres dans la bataille)."
             % mode)
    print("   Campaign -- montage par `sandbox_campagne.py`.")

    sid = args.session or session_vivante(args.hote)
    if sid is None:
        stop("aucune session Frida vivante.")
    jeu = Jeu(args.hote, sid)
    print("   session %d" % sid)

    # (!)HORS LIGNE PAR DEFAUT. La premiere version forgeait 28 BC et en comparait 4 en entier
    # -- 10 s, sur un jeu vivant, pour une question entierement STATIQUE. Le gameconfig
    # versionne repond seul. La forge reste disponible en confirmation explicite.
    cran(2, "resoudre le noeud -- HORS LIGNE, dans le gameconfig versionne")
    if args.campagne is not None:
        campagne = args.campagne
        type_ = args.type if args.type is not None else 1
        noeud = noeud_du_id(bc_id)
        print("   IMPOSE : --campagne %s --type %d --noeud %s" % (campagne, type_, noeud))
    elif args.par_forge:
        campagne, type_, noeud = resoudre_noeud(jeu, d, bc_id, None, None)
    else:
        campagne, type_, noeud = resoudre_hors_ligne(d, bc_id)
    print("   RESOLU : --campagne %s --type %d --noeud %d" % (campagne, type_, noeud))
    nom = nom_canonique(mode, bc_id, campagne, noeud, graine)
    print("   nom canonique : %s.json" % nom)
    print("     (l'`Id` %s ne suffit pas : il designe 4 batailles ; le seed distingue les "
          "passages)" % bc_id)
    if args.ranger:
        ranger_le_replay(d, mode, nom, chemin,
                         {"campagne": campagne, "type": type_, "noeud": noeud, "bcId": bc_id,
                          "board": (d.get("BoardId")
                                    or ((d.get("BattleConfiguration") or {}).get("Board")
                                        or {}).get("Id")),
                          "spawn": (d.get("BattleConfiguration") or {}).get("SpawnPointSetIndex"),
                          "seed": graine, "provenance": (d.get("MetaData") or {}).get("Mode"),
                          "build": (RACINE / "data" / "symbols" / "CURRENT").read_text(
                              encoding="utf-8").strip()},
                         brut=args.brut)

    if not args.confirmer:
        print()
        print("LECTURE SEULE -- rien n'a ete monte. Relancer avec `--confirmer` pour la suite.")
        return 0

    cran(3, "sortir d'une bataille en cours -- sinon le montage refuse")
    sortir_de_bataille(jeu, args.confirmer)

    cran(4, "ARMER LE SEED, *AVANT* le montage")
    n_av = armer_le_seed(jeu, graine, bc_id)

    cran(5, "monter le noeud en sandbox")
    cmd = [sys.executable, str(RACINE / "scripts" / "python" / "sandbox_campagne.py"),
           "--campagne", campagne, "--type", str(type_), "--noeud", str(noeud), "--confirmer"]
    p = subprocess.run(cmd, cwd=str(RACINE), capture_output=True, text=True)
    for ligne in (p.stdout or "").splitlines()[-6:]:
        print("   | " + ligne)
    if p.returncode != 0:
        stop("`sandbox_campagne.py` a rendu %d :\n%s"
             % (p.returncode, (p.stdout or "") + (p.stderr or ""))[:600])

    cran(6, "LE SEED A-T-IL MORDU ? -- le cran qui manquait")
    verifier_morsure(jeu, n_av, graine)

    cran(7, "la phase, par le BON temoin")
    verifier_phase_avant_start(jeu)

    cran(8, "poser le deploiement, et le CONFRONTER avant tout cout d'entree")
    sens = poser_le_deploiement(jeu, d)
    print("   CONFORME (pose %s), cases comprises." % sens)

    cran(9, "START")
    demarrer(jeu, n_pose + 1)     # les poses + le `StartBattleMessage`

    cran(10, "rejouer les coups -- delegue a `replay_rejouer.py`")
    cmd = [sys.executable, str(RACINE / "scripts" / "python" / "replay_rejouer.py"),
           "--replay", str(chemin), "--vivant", "--depuis", str(n_pose + 1),
           "--arret-au-premier-ecart", "--hote", args.hote, "--session", str(sid)]
    p = subprocess.run(cmd, cwd=str(RACINE), text=True)
    print()
    print("bilan : `replay_rejouer.py` a rendu %d" % p.returncode)
    return p.returncode


if __name__ == "__main__":
    sys.exit(main())
