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


def nom_canonique(mode, bc_id, campagne=None, noeud=None):
    """LE NOM D'UN REPLAY = L'IDENTITE DE SA BATAILLE, pas le hasard de sa capture.

    (!)ET POUR LA CAMPAGNE, CE N'EST PAS L'`Id`. Mesure du 2026-08-20 : `Campaign4_31` est
    produit par QUATRE couples (`campaign4`/Standard, `elite4`/Elite, `mirror4`/Mirror,
    `eliteMirror4`/EliteMirror) -- le type n'y figure pas. Nommer un fichier `Campaign4_31`
    reviendrait donc a coller la meme etiquette sur quatre batailles differentes, et a rendre
    le repertoire de replays inutilisable exactement quand il grossit.

    Le nom porte donc la campagne RESOLUE : `elite4_31`. Pour un boss de guilde, l'`Id` est
    deja discriminant (`GuildBoss10Boss1AdmecBelisarius`) et sert tel quel.
    """
    if mode == "Campaign":
        if not campagne or noeud is None:
            return None      # NON RESOLU -- on ne fabrique pas un nom ambigu
        return "%s_%d" % (campagne, noeud)
    return bc_id


def ranger_le_replay(d, mode, nom, source):
    """Ecrire le replay DECODE sous son nom canonique. REFUSE d'ecraser."""
    if nom is None:
        stop("nom canonique NON RESOLU -- on ne range pas sous un nom ambigu.")
    dossier = RACINE / "data" / "replays" / ("campaign" if mode == "Campaign" else "guild-boss")
    dossier.mkdir(parents=True, exist_ok=True)
    cible = dossier / (nom + ".json")
    # ⛔ JAMAIS D'ECRASEMENT. Un replay est une REFERENCE : le reecrire, meme par une capture
    # qu'on croit identique, detruit le seul temoin dont on dispose.
    if cible.exists():
        print("   DEJA RANGE : %s (inchange -- on n'ecrase jamais une reference)"
              % cible.relative_to(RACINE))
        return cible
    cible.write_text(json.dumps(d, ensure_ascii=False), encoding="utf-8")
    print("   range : %s   (depuis %s)" % (cible.relative_to(RACINE), Path(source).name))
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
    ap.add_argument("--ranger", action="store_true",
                    help="ecrire le replay DECODE sous son nom canonique dans "
                         "`data/replays/` (n'ecrase JAMAIS un fichier existant)")
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

    cran(2, "resoudre le noeud -- par FORGE ET COMPARAISON")
    campagne, type_, noeud = resoudre_noeud(jeu, d, bc_id, args.campagne, args.type)
    print("   RESOLU : --campagne %s --type %d --noeud %d" % (campagne, type_, noeud))
    nom = nom_canonique(mode, bc_id, campagne, noeud)
    print("   nom canonique : %s   (l'`Id` %s designe %s)"
          % (nom, bc_id, "4 batailles, il ne suffit pas" if mode == "Campaign" else "seul"))
    if args.ranger:
        ranger_le_replay(d, mode, nom, chemin)

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
