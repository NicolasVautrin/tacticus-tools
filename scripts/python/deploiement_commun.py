"""LE FOYER COMMUN DES DEUX CHAINES DE REJEU -- sandbox et campagne REELLE.

(!)POURQUOI CE MODULE EXISTE. `campagne_rejeu.py` (sandbox) avait deja resolu la pose du
deploiement : les DEUX ordres essayes, la confrontation relue jusqu'a conformite, le START
attendu sur le FAIT, le rejeu delegue a `replay_rejouer.py`. La chaine REELLE
(`campagne_rejeu_reel.py`) a commence par en REECRIRE une copie -- donc deux verites a
maintenir, et la copie neuve n'avait deja plus l'armement des relais que la sandbox arme depuis
le 2026-08-20 (`deploymentPoseFsmArmer` en tete). Le remede n'est pas de recopier la liste : il
est de n'en avoir qu'UNE.

Les deux chaines ne different que par DEUX choses, et ce module les prend en parametre :

  * COMMENT la bataille est arrivee -- montage sandbox, ou entree reelle par
    `idun.shared.commands.ViewCommandExecutor$$StartCampaignMatch` ;
  * `sur_reelle` -- l'echappatoire `surBatailleReelle: true` que `refusHorsSandbox`
    (`frida/hooks/features/deployment-draft.ts`) exige des que la source de mode active n'est pas
    `SandboxGameModeSource`.

⛔ ET `sur_reelle` N'EST PAS UN MODE. Le garde le dit et il est ne d'un incident : le
2026-08-20, un relais laisse arme a ECRIT sur un essai reel et un jeton de boss de guilde a ete
perdu. On le passe donc coup par coup, a l'appel, jamais dans une variable retenue.

(!)IL N'Y A PLUS DE VOIE A CHOISIR, ET C'EST CE QUI A REPARE LA CHAINE REELLE. `rejouerMemoire`
posait selon un drapeau `poseParFsm` : arme, par l'etage FSM -- le meme que le clic humain, donc
un PLACEHOLDER que `HandleStartMatch` convertit ; desarme, par un `AddUnitMessage` applique au
runner. La voie commit est SUPPRIMEE (2026-08-21), donc le drapeau aussi.

Ce qui l'a condamnee n'est pas son cout connu (deux comptabilites pour un seul plafond, **10
unites pour 5**, un jeton de boss perdu le 2026-08-20) mais son EFFET DE BORD : le clear du
plateau etait conditionne au MEME drapeau. Sur la campagne reelle du 2026-08-21 il n'etait pas
arme -- l'ecran arrive pre-rempli par le lineup sauvegarde du jeu, les cinq reposes sont tombees
sur un plateau plein, et QUATRE rejeux ont laisse l'arrangement du jeu strictement inchange,
sans une seule erreur. Le journal disait meme << plateau VIDE avant rejeu >>.
"""
import json
import atexit
import subprocess
import sys
import time
from pathlib import Path

RACINE = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(Path(__file__).resolve().parent))

from replay_rejouer import (poses_du_replay, controler_avant_start,   # noqa: E402
                            mise_en_place_du_replay)
from board import Board  # noqa: E402


def stop(msg, code=2):
    print()
    print("ARRET -- " + msg)
    sys.exit(code)


# ⚠ LE TEMPS D'UNE PASSE ETAIT MESURE EN UN SEUL BLOC, DONC INATTRIBUABLE.
# `campagne_rejeu_boucle.py` chronometre le sous-processus ENTIER (crans 0 a 17) : quand une
# passe est lente, rien ne dit si c'est l'entree, le chargement de scene, le deploiement, le
# START ou le rejeu des coups. Mesure du 2026-08-23 : les etapes AUTOUR de la passe sont
# petites -- crans 0-6 en 2,5 s, `netCaptureDump` 0,34 s, `battleStatus` 0,17 s,
# `ecranGeneration` 0,14 s -- et l'ecran de fin vaut 5,4 a 10+ s. Tout le reste tombait dans un
# seul nombre.
#
# Le chronometre vit ICI parce que `cran()` est le foyer PARTAGE des trois chaines (reelle,
# sandbox, deploiement) : une horloge par chaine divergerait, et deux d'entre elles n'en
# auraient jamais eu.
#
# Il n'ARBITRE rien et ne peut donc rien casser : il imprime. Le total est rendu par
# `bilan_des_crans()`, que l'appelant affiche s'il le veut.
_CHRONO = {"debut": None, "precedent": None, "n": None, "titre": None, "durees": []}


def cran(n, titre):
    t = time.time()
    p = _CHRONO["precedent"]
    if p is not None:
        _CHRONO["durees"].append((_CHRONO["n"], _CHRONO["titre"], t - p))
    else:
        _CHRONO["debut"] = t
    _CHRONO["precedent"], _CHRONO["n"], _CHRONO["titre"] = t, n, titre
    print()
    ecoule = "" if _CHRONO["debut"] is None else "   [+%.1f s]" % (t - _CHRONO["debut"])
    print("CRAN %-2s -- %s%s" % (n, titre, ecoule))


def bilan_des_crans(seuil_s=1.0):
    """Les crans TRIES par duree, le plus lent d'abord. `[]` = aucun cran chronometre.

    Le dernier cran n'a pas de duree (rien ne le suit) : on le DIT au lieu de lui en inventer
    une -- un cran final compte comme 0 s se lirait comme instantane."""
    if _CHRONO["precedent"] is None:
        return []
    fin = time.time()
    lignes = list(_CHRONO["durees"])
    lignes.append((_CHRONO["n"], _CHRONO["titre"] + " (dernier -- jusqu'a la sortie)",
                   fin - _CHRONO["precedent"]))
    return [(n, t, d) for n, t, d in sorted(lignes, key=lambda x: -x[2]) if d >= seuil_s]


def imprimer_bilan_des_crans(seuil_s=1.0):
    lignes = bilan_des_crans(seuil_s)
    if not lignes:
        return
    total = time.time() - (_CHRONO["debut"] or time.time())
    print()
    print("--- OU EST PASSE LE TEMPS (%.1f s au total ; crans >= %.1f s) ---" % (total, seuil_s))
    for n, titre, d in lignes:
        print("   %5.1f s  cran %-2s  %s" % (d, n, titre[:78]))


# ⚠ SUR `atexit`, ET PAS AU POINT DE SORTIE NOMINAL. `stop()` fait `sys.exit`, et une passe qui
# REFUSE est justement celle dont on veut savoir ce qui a ete lent -- un bilan branche sur la
# seule fin heureuse ne serait jamais la quand il sert. `bilan_des_crans` rend `[]` tant qu'aucun
# cran n'a tourne, donc les modules qui importent ce foyer sans jouer de cran n'impriment rien.
atexit.register(imprimer_bilan_des_crans)


# ─────────────────────────────────────────────────────────────────────────────────────────────
# LES RELAIS, ARMES *AVANT* QUE LA BATAILLE EXISTE
#
# (!)L'ORDRE EST LE SUJET, ET IL A COUTE UNE SOIREE. Les capteurs de vue et de HUD ne tirent qu'a
# la CREATION de la bataille / a l'AFFICHAGE de l'ecran. Armes apres, ils ne tirent JAMAIS pour
# cette bataille-la, et tout devient aveugle -- mesure du 2026-08-21 sur la chaine reelle :
# `deploymentEtat` publiait `placeholders: 5` et un `ordreHud` JUSTE tout en rendant
# `ordreConversion: {erreur}`, parce que `IdunGameViews$$Enable` n'etait pas ancre. Le refus
# accusait alors la POSE alors que seule la LECTURE manquait.
# ─────────────────────────────────────────────────────────────────────────────────────────────
ARMEMENTS_CAPTEURS = [
    ("deploymentPrefabArmer", {"armer": True}),
    # ⚠ `armer` SEUL -- pas de `forcer`. Le montage sandbox y ajoute `forcer: true` parce qu'il
    # doit FABRIQUER une phase de deploiement ; une bataille reelle a deja la sienne, et forcer
    # y ecrirait sur une partie du joueur pour rien.
    ("deploymentPhaseArmer", {"armer": True}),
    ("deploymentHudArmer", {"armer": True}),
    ("deploymentPoseDiag", {"armer": True}),
    ("deploymentMemoire", {"armer": True}),
    ("vueExceptionArmer", {"armer": True}),
]

# CE QUI N'EST VRAI QUE POUR LA SANDBOX, et qu'on ne monte donc PAS sur une bataille reelle :
#   ("deploymentPhaseArmer", {..., "forcer": True, "confirmer": True})
#       la sandbox n'a pas de phase de deploiement, il faut la fabriquer.
#   ("deploymentPoolArmer", {..., "source": "campagne", "only": [...]})
#       `SandboxGameModeSource` ne fournit pas de roster -- l'ecran sort VIDE sans delegation a
#       la source du MODE. La campagne, elle, fournit le sien : deleguer y serait un detour.
#   ("sandboxModeGameViews", {"armer": True, "confirmer": True})
#       le hook le dit lui-meme : << n'agit que sur une SandboxGameModeSource dont `_gameViews`
#       est encore nul >>. Inerte ailleurs.


def armer_les_relais(jeu, liste=None, etiquette="capteurs"):
    """Arme la liste et REFUSE au premier echec. Un relais qu'on croit arme et qui ne l'est pas
    rend la phase illisible SANS le dire -- c'est exactement le mode de panne du 2026-08-21."""
    liste = ARMEMENTS_CAPTEURS if liste is None else liste
    poses = []
    for nom, corps in liste:
        r = jeu.rpc(nom, [dict(corps)], timeout=120000)
        if not isinstance(r, dict) or r.get("ok") is False:
            stop("relais `%s` NON ARME : %s" % (nom, json.dumps(r, ensure_ascii=False)[:220]))
        poses.append(nom)
    print("   %d relais %s armes : %s" % (len(poses), etiquette, ", ".join(poses)))
    return poses


# ─────────────────────────────────────────────────────────────────────────────────────────────
# LA POSE, LE START, LE REJEU -- la SUITE, identique aux deux chaines
# ─────────────────────────────────────────────────────────────────────────────────────────────
def mow_du_replay(d):
    """La Machine of War du replay, PLATEFORME COMPRISE -- ou `None` s'il n'y en a pas.

    ⚠ CETTE FONCTION EXISTE PARCE QUE `poser_le_deploiement` PASSAIT `mow: None` EN DUR. Elle a
    ete ecrite pour la CAMPAGNE, ou il n'y a pas de Machine of War -- et sur une bataille qui en
    porte une, elle ne la posait pas ET ecrasait l'entree MoW de la memoire a chaque pose. Mesure
    du 2026-08-21 : trois crashs du jeu sur la chaine de guerre de guilde, dont le dernier
    (`Tacticus.exe.22660.dmp`, 15:58) PENDANT la pose. La seule difference de fond avec nos
    rejeux de campagne, qui passent, est la MoW.

    ⚠ ON RESTE EN REGIME PLACEHOLDER -- c'est le seul. La pose passe donc par l'etage FSM
    (`deploymentMoWPoser` -> `UnitDeployment_PlaceMachineOfWarUnitOnBoard`), et c'est le START du
    jeu qui convertit. PAS `AddMachineMessage`, qui CRASHE ; pas `PredefinedMachines`, qui DECALE
    les ids.

    ⚠ LA PLATEFORME N'EST PAS DANS LE REPLAY et se DERIVE : chaque `SpawnPointGroup` du jeu de
    spawns que la BC designe porte un `MachineOfWarPosition`, et on reconnait NOTRE groupe au
    fait que NOS positions enregistrees sont dedans. On l'apparie PAR LES POSITIONS, jamais par
    le `TeamWithPlayerIndex` : mesure sur maradak, nos 5 poses tombent 5/5 dans le groupe
    d'index 0 alors que notre `TeamId` vaut 1 -- l'apparier par l'equipe aurait pris l'AUTRE
    groupe et pose la machine sur la mauvaise plateforme.

    Rend `None` quand la plateforme ne se derive pas : on ne la devine pas.
    """
    mow = None
    for m in d.get("Messages") or []:
        jm = json.loads((m.get("Message") or {}).get("MessageJson") or "{}")
        if jm.get("Name") == "StartBattleMessage":
            break
        if jm.get("Name") == "AddMachineMessage":
            mow = {"unitId": jm.get("UnitId"), "playerId": jm.get("PlayerId")}
    if mow is None:
        return None

    bc = d.get("BattleConfiguration") or {}
    idx = bc.get("SpawnPointSetIndex")
    jeux = ((bc.get("Board") or {}).get("SpawnPointSets") or [])
    if not isinstance(idx, int) or idx >= len(jeux):
        print("   (!) MoW %s : `SpawnPointSetIndex`=%r hors des %d jeux -- plateforme "
              "INDERIVABLE, on ne la pose pas." % (mow["unitId"], idx, len(jeux)))
        return None
    nos = [(c, r) for (_u, c, r) in (poses_du_replay(d) or [])]
    candidats = []
    for g in jeux[idx].get("SpawnPointGroups") or []:
        pts = set((s.get("Column"), s.get("Row")) for s in (g.get("SpawnPoints") or []))
        if nos and all(p in pts for p in nos):
            candidats.append(g)
    if len(candidats) != 1:
        print("   (!) MoW %s : %d groupe(s) de spawns contiennent nos positions -- appariement "
              "NON UNIVOQUE, on ne pose pas." % (mow["unitId"], len(candidats)))
        return None
    mow["position"] = candidats[0].get("MachineOfWarPosition")
    return mow


def cases_de_spawn_du_joueur(bc):
    """(playerId, [(col,row), ...], diagnostic) -- MES cases de spawn, DERIVEES du plateau.

    Sert quand il n'y a PAS de replay d'ou tirer les positions : un banc qu'on monte de zero
    (`sandbox_incursion.py`) doit bien poser sa lineup QUELQUE PART, et une case en dur serait
    fausse au premier changement de board ou de jeu de spawns.

    Le joueur humain est celui a `PlayerType 0` de `Player.Players` ; ses cases sont celles que
    `Board.spawns` lui attribue -- le depliage de `TeamWithPlayerIndex` vit dans `board.py`
    (`TeamPlayerIdExtensions.Unfold`, aligne sur `board.js`), on le REPREND plutot que d'en tenir
    une seconde copie. L'ordre rendu est celui du plateau, donc stable d'un montage a l'autre.

    (!)LE COMPTE DES CASES ADVERSES EST LA CORROBORATION, et c'est pour ca qu'il est rendu.
    Deplier un `TeamWithPlayerIndex` est une CONVENTION : se tromper de groupe ferait atterrir
    mes unites sur les cases de l'ennemi, et rien ne le dirait. Le controle qui ne coute rien --
    les cases qu'on n'a PAS prises doivent etre aussi nombreuses que les ennemis de la BC (8
    pour 8, mesure du 2026-08-24 sur `MC1_74` set 5). Un ecart ne bloque pas : il se DIT.

    ⚠ CE N'EST PAS L'APPARIEMENT DE `mow_du_replay`, ET LES DEUX SONT JUSTES. Celui-la refuse
    explicitement le `TeamWithPlayerIndex` et apparie PAR LES POSITIONS -- il le peut, il a un
    replay. Ici il n'y a rien a apparier : ce sont les positions qu'on cherche.

    Rend `(None, [], motif)` quand la derivation n'est pas univoque : on ne devine pas une case.
    """
    joueurs = (bc.get("Player") or {}).get("Players") or {}
    moi = [pid for pid, p in joueurs.items() if (p or {}).get("PlayerType") == 0]
    if len(moi) != 1:
        return None, [], ("%d joueur(s) `PlayerType 0` -- on ne devine pas le mien" % len(moi))
    mon_id = int(moi[0])

    spawns = Board(bc).spawns
    miennes = [cr for cr, v in spawns.items() if v.get("player") == mon_id]
    if not miennes:
        return None, [], ("aucune case de spawn pour le joueur %d parmi %d case(s) -- "
                          "`SpawnPointSetIndex`=%r" % (mon_id, len(spawns),
                                                       bc.get("SpawnPointSetIndex")))

    ennemis = sum(len(g.get("Units") or []) for g in (bc.get("PredefinedUnits") or [])
                  if str(g.get("Id")) != str(mon_id))
    adverses = len(spawns) - len(miennes)
    return mon_id, miennes, (
        "playerId=%d  %d case(s) : %s | %d case(s) adverse(s) pour %d ennemi(s) dans la BC%s"
        % (mon_id, len(miennes), " ".join("(%s,%s)" % c for c in miennes), adverses, ennemis,
           "" if adverses == ennemis else "  (!) ECART -- verifier le depliage"))


def plateforme_du_joueur(bc, mes_cases):
    """Le `MachineOfWarPosition` de MON groupe de spawns, ou `(None, motif)`.

    Une Machine of War ne se pose PAS par case : elle n'a ni colonne ni ligne, elle va sur une
    PLATEFORME, designee par un entier que porte le `SpawnPointGroup`.

    (!)L'APPARIEMENT SE FAIT PAR LES POSITIONS, JAMAIS PAR LE `TeamWithPlayerIndex` -- c'est la
    regle que `mow_du_replay` a payee : mesure sur maradak, les 5 poses tombent 5/5 dans le groupe
    d'index 0 alors que le `TeamId` vaut 1. Apparier par l'equipe aurait pris l'AUTRE groupe et
    pose la machine sur la plateforme adverse.

    Rend `(None, motif)` quand l'appariement n'est pas univoque : on ne devine pas une plateforme.
    """
    idx = (bc or {}).get("SpawnPointSetIndex")
    jeux = ((bc.get("Board") or {}).get("SpawnPointSets") or [])
    if not isinstance(idx, int) or not (0 <= idx < len(jeux)):
        return None, ("`SpawnPointSetIndex`=%r hors des %d jeux de spawns" % (idx, len(jeux)))
    voulues = set(tuple(c) for c in mes_cases)
    if not voulues:
        return None, "aucune case connue -- rien a quoi apparier le groupe"
    candidats = []
    for g in (jeux[idx] or {}).get("SpawnPointGroups") or []:
        pts = set((s.get("Column"), s.get("Row")) for s in (g.get("SpawnPoints") or []))
        if voulues <= pts:
            candidats.append(g)
    if len(candidats) != 1:
        return None, ("%d groupe(s) contiennent mes %d case(s) -- appariement NON UNIVOQUE"
                      % (len(candidats), len(voulues)))
    pos = candidats[0].get("MachineOfWarPosition")
    if not isinstance(pos, int):
        return None, ("mon groupe ne porte pas de `MachineOfWarPosition` (%r)" % pos)
    return pos, "plateforme %d (groupe apparie par mes %d case(s))" % (pos, len(voulues))


def ids_de_la_lineup(lineup, override=None, etiquette="lineup de la source"):
    """Les ids a poser : l'`override` s'il est donne, sinon ce que LA SOURCE annonce.

    Rend `(ids, ligne_de_diagnostic)`. `ids` vide n'est PAS une erreur -- c'est un etat qu'il
    faut DIRE, avec le motif que la source rend.

    (!)LA COMPOSITION SE DEMANDE A LA SOURCE, PAS A LA BC. `GetBattleLineup` est le contrat
    commun a TOUTES les sources de mode (Campaign, CampaignEvent, GuildBoss, GuildWars,
    MachinesOfWarEvent, Pvp, SyncPvp, Sandbox...). La BC, elle, ne porte que l'adversaire : le
    camp du joueur y est VIDE, ses unites n'entrant qu'au DEPLOIEMENT.

    ⚠ ET `deploymentMemoire` N'EST PAS UN REPLI. Il ne lit pas la sauvegarde du compte : il
    PHOTOGRAPHIE le plateau a l'appui sur START. Il est donc vide tant qu'aucune bataille n'a
    demarre RELAIS ARME dans la session courante -- ce qui se lit a tort comme << le jeu n'a pas
    de lineup >>. Mesure du 2026-08-24 : une sandbox boss montee apres reinjection arrivait
    plateau vide pour cette seule raison.
    """
    lu = lineup or {}
    if override:
        ids = [u.strip() for u in override.split(",") if u.strip()] \
            if isinstance(override, str) else list(override)
        return ids, "%d unite(s) IMPOSEE(S)" % len(ids)
    ids = list(lu.get("unites") or [])
    if not ids:
        return [], ("la source n'annonce AUCUNE unite (%s) -- l'ecran restera VIDE"
                    % (lu.get("refus") or lu.get("voie")))
    return ids, ("%d unite(s) de la SOURCE (classe=%s, voie=%s)%s"
                 % (len(ids), lu.get("classe"), lu.get("voie"),
                    "  + MoW %s" % lu.get("mow") if lu.get("mow") else "  (aucune MoW)"))


def poses_sur_cases_de_spawn(bc, ids):
    """Apparier `ids` aux cases de spawn du joueur. Rend `(poses, moi, diagnostic)`.

    `poses` a `None` = REFUS (le diagnostic le dit) ; `[]` = rien a poser.

    ⛔ LES POSITIONS SONT ARBITRAIRES, ET LE DIAGNOSTIC LE DIT. `GetBattleLineup` rend un
    `String[]` : la source porte QUI le joueur amene, JAMAIS OU il le pose. L'appariement
    ci-dessous zippe les ids avec les cases de spawn dans l'ordre du plateau -- c'est une
    convention de CE code, pas une donnee du jeu.

    Mesure du 2026-08-24 : sur le boss de guilde, les 5 unites rendues etaient EXACTEMENT
    celles du dernier combat, et les 5 positions TOUTES fausses -- chaque unite sur la case
    d'une autre. Le compte (5/5) et les noms (5/5) etaient justes, ce qui rendait le tout
    parfaitement credible. C'est le mode de panne le plus couteux : une moitie mesuree, une
    moitie inventee, et rien qui les distingue a l'ecran.

    ⇒ Pour un placement FIDELE, la position doit venir d'une source qui la porte : un replay
    (`poses_du_replay` / `--depuis-replay`), ou une saisie explicite. Pas d'ici.

    ⚠ QUESTION OUVERTE, ET MA CONCLUSION A ETE CONTREDITE. J'ai ecrit << le jeu sauvegarde
    l'equipe, pas le placement >> apres avoir constate que TOUT le contrat de source est
    `String[]`/`String` et que `UnitProgressionData.SetLineup(key, unitIds)` ne stocke que des
    ids. L'utilisateur a corrige : << le jeu arrive tres bien a retrouver le placement >>. Le
    mecanisme n'est donc PAS celui que j'ai balaye, et il reste a trouver -- une absence dans
    une famille de symboles ne prouve rien. Ne pas re-citer ma conclusion : la RE-MESURER.

    (!)PLUS D'UNITES QUE DE CASES EST UN REFUS, PAS UNE TRONCATURE. Poser << ce qui tient >>
    laisserait une composition AMPUTEE que personne n'a demandee, et le compte affiche ne
    dirait plus ce qui est en jeu. On refuse, et on nomme les deux nombres.
    """
    if not ids:
        return [], None, "rien a poser"
    moi, tuiles, diag = cases_de_spawn_du_joueur(bc)
    if moi is None:
        return None, None, diag
    if len(ids) > len(tuiles):
        return None, moi, ("REFUS : %d unite(s) pour %d case(s) de spawn -- %s"
                           % (len(ids), len(tuiles), diag))
    return ([{"unitId": u, "playerId": moi, "col": c, "row": r}
             for u, (c, r) in zip(ids, tuiles)], moi,
            diag + " | (!) POSITIONS ARBITRAIRES : la source donne les UNITES, pas leur "
                   "placement -- `--depuis-replay` pour un placement fidele")


def poser_la_mow_du_joueur(jeu, bc, mow_id, poses):
    """La MoW du joueur, APRES ses heros et par la voie PLATEFORME. Rend le motif imprime.

    (!)L'ORDRE N'EST PAS UN CONFORT. Les entites sont allouees dans l'ordre de pose : une
    machine posee AVANT les heros decale TOUS les squads d'un cran, et un replay adresse ses
    coups PAR ENTITE. Sur un plateau VIERGE, `unites + [MoW]` est le seul ordre qui reproduise
    ce que les replays du depot enregistrent.
    """
    if not mow_id or not poses:
        return None
    pos, motif = plateforme_du_joueur(bc, [(q["col"], q["row"]) for q in poses])
    if pos is not None:
        poser_la_mow(jeu, mow_id, poses[0]["playerId"], pos)
    return motif


def poser_la_mow(jeu, unit_id, player_id, position, plafond_s=20.0):
    """Poser MA Machine of War sur sa plateforme -- etage FSM, donc PLACEHOLDER.

    ⛔ NI `AddMachineMessage`, NI `BC.PredefinedMachines`. Le premier CRASHE ; le second est le
    canal de la machine ADVERSE (que le mode impose) et decalerait les ids d'entites. On passe par
    `deploymentMoWPoser` -> `StateMachineActions$$UnitDeployment_PlaceMachineOfWarUnitOnBoard`,
    le chemin du clic humain, et c'est le START natif qui convertit.

    ⚠ LE RETOUR NE PROUVE RIEN : `AddPlaceholderMachine` ne pose qu'un placeholder de VUE, et un
    appel peut rendre `ok` sans que la machine existe. On relit `deploymentEtat.machines`.
    """
    r = jeu.rpc("deploymentMoWPoser", [{"unitId": unit_id, "playerId": player_id,
                                        "position": position, "confirmer": True}], timeout=180000)
    if not isinstance(r, dict) or not r.get("ok"):
        print("   REFUS `deploymentMoWPoser` : %s" % json.dumps(r, ensure_ascii=False)[:280])
        return None
    debut, e = time.time(), None
    while time.time() - debut < plafond_s:
        e = jeu.rpc("deploymentEtat", [{}], timeout=120000)
        if isinstance(e, dict) and e.get("machines") is True:
            break
        time.sleep(0.3)
    machines = e.get("machines") if isinstance(e, dict) else None
    print("   MoW %-22s -> plateforme %s   machines=%s   [%.1f s]"
          % (unit_id, position, machines, time.time() - debut))
    if machines is not True:
        print("   (!) le HUD ne declare AUCUNE machine -- la pose n'a pas abouti.")
    return e


def poser_en_placeholders(jeu, poses, mow=None, mow_index=None, sur_reelle=False,
                          plafond_s=20.0):
    """Poser une composition DONNEE en PLACEHOLDERS, et attendre qu'elle ait atterri.

    L'etage bas, partage : `poser_le_deploiement` s'en distingue en ce qu'il tire ses poses d'un
    REPLAY et confronte le resultat a lui (deux ordres essayes). Ici la composition est donnee,
    il n'y a rien a confronter -- seulement a verifier que la pose a PRIS.

    (!)REGIME PLACEHOLDER, ET C'EST LE SEUL. `deploymentMemoire {rejouer}` vide le plateau puis
    repose par l'etage FSM -- le meme chemin que le clic humain -- donc des `PlaceholderUnitView`
    que `idun.IdunMainView$$AddUnitsFromPlaceholdersAndRunnerStartMatch` convertit au START. Rien
    n'est ecrit dans `BattleConfiguration.PredefinedUnits` : ce canal-la porte les unites que le
    MODE impose, pas la lineup du joueur.

    (!)LE REJEU EST << ENFILE >>, PAS FAIT : le RPC rend la main aussitot (`rejouerMemoire` est
    une chaine `queueOnMainThread(...).then(...)` qui rend `void`). On attend donc LE FAIT --
    les placeholders comptes par le HUD -- jamais une duree.

    Rend l'etat final (`deploymentEtat`) ou `None` si la pose n'a pas abouti.
    """
    corps = {"poses": poses, "mow": mow}
    if mow is not None and mow_index is not None:
        corps["mowIndex"] = mow_index
    r = jeu.rpc("deploymentMemoire", [{"poser": corps}], timeout=120000)
    if not isinstance(r, dict) or not r.get("ok"):
        print("   REFUS `deploymentMemoire {poser}` : %s"
              % json.dumps(r, ensure_ascii=False)[:280])
        return None
    rejeu = {"rejouer": True, "confirmer": True}
    # ⛔ COUP PAR COUP, jamais retenu -- cf. l'en-tete du module.
    if sur_reelle:
        rejeu["surBatailleReelle"] = True
    r = jeu.rpc("deploymentMemoire", [rejeu], timeout=180000)
    if not isinstance(r, dict) or not r.get("ok"):
        print("   REFUS `deploymentMemoire {rejouer}` : %s"
              % json.dumps(r, ensure_ascii=False)[:280])
        return None

    debut, e = time.time(), None
    while time.time() - debut < plafond_s:
        e = jeu.rpc("deploymentEtat", [{}], timeout=120000)
        if isinstance(e, dict) and isinstance(e.get("placeholders"), int) \
                and e["placeholders"] >= len(poses):
            break
        time.sleep(0.3)
    if not isinstance(e, dict) or not isinstance(e.get("placeholders"), int):
        print("   pose NON MESURABLE apres %.1f s : %s"
              % (time.time() - debut, json.dumps(e, ensure_ascii=False)[:280]))
        return None
    print("   placeholders=%s reelles=%s max=%s   [%.1f s]"
          % (e.get("placeholders"), e.get("reelles"), e.get("max"), time.time() - debut))
    if e["placeholders"] < len(poses):
        print("   (!) %d pose(s) demandee(s), %d placeholder(s) -- il en manque."
              % (len(poses), e["placeholders"]))
        return None
    # ⚠ `reelles` DOIT valoir 0 avant le START : une unite REELLE ici signale la DOUBLE
    # COMPTABILITE que le regime placeholder existe justement pour eviter -- c'est elle qui a
    # produit les 10 unites pour 5 du 2026-08-20.
    if (e.get("reelles") or 0) != 0:
        print("   (!) %s unite(s) REELLE(S) avant le START -- ce n'est PAS le regime placeholder."
              % e.get("reelles"))
    return e


def poser_le_deploiement(jeu, d, sur_reelle=False, plafond_s=15.0):
    """CONFRONTER d'abord, poser seulement si ca diverge, et RE-CONFRONTER.

    (!)<< POSER A L'ENVERS >> N'EST PAS UNE REGLE. Ca ne vaut que si le clear vient de liberer
    autant de paires qu'on repose. Ce qui est fiable, c'est de VERIFIER -- donc on essaie, on
    relit `ordreConversion`, et on recommence dans l'autre sens si besoin.

    (!)LA CONFRONTATION PREALABLE N'EST PAS UNE OPTIMISATION. Sur la voie reelle c'est la
    consigne meme -- << tu ne remplaces pas la BC, tu t'assures juste que le deploiement est
    celui prevu dans le replay >>. Et sur la voie sandbox elle ne coute rien : le plateau y est
    vierge, donc elle diverge toujours et on pose comme avant.

    (!)LE REJEU DE POSE EST << ENFILE >>, PAS FAIT. `deploymentMemoire {rejouer}` rend la main
    aussitot : `rejouerMemoire` est une chaine `queueOnMainThread(...).then(...)` qui rend
    `void`, donc le RPC ne peut pas l'attendre. Mesure du 2026-08-21 : confronter immediatement
    fait tomber les DEUX ordres -- le plateau n'est pas encore pose, et le refus accuse l'ordre
    au lieu du delai. A defaut de signal on attend LE FAIT, jamais une duree.

    ⚠ CE N'EST PAS LE BON REGIME, ET C'EST DIT : la vraie reparation est de faire REMONTER la
    chaine de promesses de `rejouerMemoire` jusqu'au RPC, pour que l'appel HTTP attende son
    propre travail -- comme `attendreRunner` le fait pour le montage.
    """
    voulu = poses_du_replay(d)
    if voulu is None:
        stop("poses du replay NON LISIBLES -- on ne pose rien a l'aveugle.")

    ok, motif = controler_avant_start(jeu, d)
    if ok:
        print("   DEJA CONFORME au replay -- rien a poser. %s" % motif.split("\n")[0])
        return "tel quel"
    print("   diverge : %s" % motif.split("\n")[0])
    print("   -> on pose les %d unites du replay%s"
          % (len(voulu), " (SUR BATAILLE REELLE)" if sur_reelle else ""))

    # ⚠ LA MoW EST LUE, PLUS FORCEE A `None`. Ce `None` en dur venait de la campagne, qui n'en a
    # pas -- et sur une bataille qui en porte une il ne se contentait pas de l'ignorer : il
    # ECRASAIT l'entree MoW de la memoire a chaque pose. Pour un replay de campagne
    # `mow_du_replay` rend `None` et le comportement est identique au precedent.
    mow = mow_du_replay(d)
    if mow is not None:
        print("   MoW du replay : %s -> plateforme %s (DERIVEE des spawns)"
              % (mow["unitId"], mow.get("position")))

    # (!)L'ORDRE DU REPLAY D'ABORD -- PARCE QUE POUR UNE MoW, C'EST LE SEUL ESSAI QUI PUISSE
    # GAGNER.
    #
    # Les deux regimes, MESURES sur maradak le 2026-08-21. Soit `U` les unites dans l'ordre donne
    # et `M` la Machine of War -- qui est TOUJOURS posee APRES elles, quel que soit leur ordre :
    #   * plateau VIERGE (montage frais, aucun clear) -- conversion = `U + [M]`.
    #   * plateau PLEIN (un clear precede la repose) -- la liste libre des paires d'entites se
    #     comporte en PILE, donc conversion = `reverse(U + [M])` = `[M] + reverse(U)`.
    #
    # ⛔ SUR UN PLATEAU PLEIN, LA MoW EST DONC TOUJOURS EN TETE, et aucune permutation des unites
    # ne l'en deloge -- elle n'est pas dans la partie permutee. Les six replays du depot
    # l'enregistrent EN DERNIER : ils ne sont reproductibles QUE sur un plateau VIERGE, pose dans
    # l'ordre du replay. Verifie deux fois, les deux essais rendant `[M] + ...`.
    #
    # ⚠ J'AI CRU L'INVERSE, ET LE CODE A PORTE MON ERREUR : << essayer `R` puis son inverse
    # converge dans les deux regimes >>. Faux -- ca ne vaut que pour les UNITES. Le second essai
    # rend `[M] + U`, donc les unites justes et la machine a la mauvaise place, ce qui decale
    # TOUS les squads d'un cran (mesure : replay 95/97/99/101/103, live 96/98/100/102/104).
    #
    # ⚠ ET AUCUNE DETECTION DE REGIME ICI, C'EST DELIBERE. Une version lisait
    # `deploymentEtat.placeholders` pour choisir : sur un plateau REELLEMENT vierge ce RPC ne
    # resout aucune vue (<< aucune `IdunGameViews` joignable >>) et rend `None` -- lu comme
    # << pas vierge >>, il faisait prendre le mauvais essai, donc perdre l'unique occasion.
    #
    # Le second essai reste : il rattrape le cas SANS MoW, ou la permutation des unites suffit.
    # (!)L'ORDRE DE POSE SE DERIVE DE LA MISE EN PLACE COMPLETE, MoW COMPRISE.
    #
    # Ce site n'essayait que deux ordres des UNITES, la machine etant posee apres elles dans les
    # deux cas. Ca ne peut donc produire qu'une conversion ou la MoW est a une EXTREMITE --
    # derniere sur plateau vierge, premiere sur plateau plein. Mesure du 2026-08-21 sur
    # `maradak-f1z2p0s1` : le replay porte la machine en 5e position sur 6, avec une unite APRES
    # elle, et les deux essais tombent -- non parce que l'ordre des unites est faux, mais parce
    # que cette position-la etait INATTEIGNABLE.
    #
    # Le gisement vient de NOUS : les six replays historiques enregistrent la MoW en dernier
    # parce qu'ils sortent tous de cette fonction. La capture automatique de fin de bataille en
    # produit desormais d'autres -- quand le joueur pose a la main, la machine atterrit ou il la
    # met.
    #
    # On derive donc la sequence de la mise en place ENTIERE (`mise_en_place_du_replay`, qui
    # porte la MoW a sa vraie place), et on passe son index au hook. Les deux essais restent :
    # ils couvrent les deux regimes de conversion, `U + [M]` et son inverse.
    mep, _n, _r = mise_en_place_du_replay(d)
    if mep is None:
        stop(_r)
    par_id = {u: (c, r) for (u, c, r) in voulu}

    def sequence(entrees):
        """(poses, mowIndex) -- l'index dit combien d'unites PRECEDENT la machine."""
        poses, idx = [], None
        for e in entrees:
            if e["genre"] == "mow":
                idx = len(poses)
                continue
            cr = par_id.get(e["unitId"])
            if cr is None:
                stop("l'unite %s de la mise en place n'a pas de case dans les poses du replay"
                     % e["unitId"])
            poses.append({"unitId": e["unitId"], "playerId": 11, "col": cr[0], "row": cr[1]})
        return poses, idx

    for etiquette, entrees in (("ordre du replay", list(mep)),
                               ("INVERSE de l'ordre du replay", list(reversed(mep)))):
        poses, mow_idx = sequence(entrees)
        corps_poser = {"poses": poses, "mow": mow}
        if mow is not None and mow_idx is not None:
            corps_poser["mowIndex"] = mow_idx
        jeu.rpc("deploymentMemoire", [{"poser": corps_poser}], timeout=120000)
        corps = {"rejouer": True, "confirmer": True}
        # ⛔ COUP PAR COUP, jamais retenu -- cf. l'en-tete du module.
        if sur_reelle:
            corps["surBatailleReelle"] = True
        r = jeu.rpc("deploymentMemoire", [corps], timeout=180000)
        if not isinstance(r, dict) or not r.get("ok"):
            stop("le rejeu de memoire a ECHOUE : %s" % json.dumps(r, ensure_ascii=False)[:280])
        debut, ok, motif = time.time(), False, ""
        while time.time() - debut < plafond_s:
            ok, motif = controler_avant_start(jeu, d)
            if ok:
                break
            time.sleep(0.2)
        print("   pose en %-28s -> %s   [%.1f s]"
              % (etiquette, motif.split("\n")[0], time.time() - debut))
        if ok:
            return etiquette
        # ⚠ LE DETAIL EST IMPRIME, PLUS AVALE. `motif.split("\n")[0]` ne rendait que la premiere
        # ligne, et le tableau ligne a ligne -- celui qui montre << replay 5 entrees, live 6 >>
        # d'un coup d'oeil -- restait dans la chaine sans jamais atteindre l'ecran. Mesure du
        # 2026-08-21 : c'est ce qui a fait accuser l'ORDRE DE POSE pendant que la vraie cause
        # etait une comparaison AVEUGLE A LA MoW, lisible sur la premiere ligne du tableau.
        for ligne in motif.split("\n")[1:]:
            print(ligne)

    # ⚠ QUAND LES DEUX ESSAIS TOMBENT AVEC LA MoW EN TETE DES DEUX COTES LIVE, LA CAUSE N'EST PAS
    # L'ORDRE : c'est que le plateau n'etait pas vierge. On le NOMME, parce que le motif
    # << aucun des deux ordres >> a deja fait accuser l'ordre deux fois pour d'autres causes.
    # ⛔ AVANT D'ACCUSER L'ORDRE : Y A-T-IL SEULEMENT QUELQUE CHOSE DE POSE ?
    #
    # Mesure du 2026-08-21. Ce refus a dit << aucun des deux ordres de pose ne rend l'ordre de
    # conversion >> sur un plateau ou le live portait ZERO unite -- il n'y avait donc AUCUN ordre
    # a rendre. La cause etait que les six unites du replay etaient EPUISEES (elles venaient de
    # combattre), donc impossibles a deployer. Un refus qui nomme la mauvaise cause fait chercher
    # au mauvais endroit : il a failli faire conclure que l'intercalage de la MoW ne marchait pas,
    # alors que la memoire du hook rendait bien `mowIndex`.
    etat = jeu.rpc("deploymentEtat", [{}], timeout=120000)
    poses_live = etat.get("ordreConversion") if isinstance(etat, dict) else None
    if isinstance(poses_live, list) and len(poses_live) == 0:
        epuisees = []
        b = jeu.rpc("guildWarBoardRead", [{}], timeout=240000)
        if isinstance(b, dict) and b.get("ok"):
            ep = set(b.get("exhaustedUnits") or [])
            epuisees = [u for (u, _c, _r) in voulu if u in ep]
            if mow is not None and mow.get("unitId") in ep:
                epuisees.append(mow["unitId"] + " (MoW)")
        stop("le plateau est reste VIDE -- AUCUNE unite posee, donc aucun ordre de conversion a "
             "confronter. Ce n'est PAS un probleme d'ordre.\n"
             "         %s"
             % ("unites EPUISEES, donc non deployables : " + ", ".join(epuisees)
                if epuisees else
                "les unites du replay ne sont pas epuisees -- la cause est ailleurs "
                "(pool, cap de rarete, capteurs de pose non armes). NE PAS conclure a l'ordre."))

    mep, _n, _r = mise_en_place_du_replay(d)
    detail = ""
    if mep and mep[-1]["genre"] == "mow":
        detail = (" LE REPLAY PORTE UNE MoW, ENREGISTREE EN DERNIER : il n'est reproductible que "
                  "sur un plateau VIERGE. Sur un plateau deja peuple, le clear fait de la liste "
                  "libre une PILE et la machine -- posee apres les unites -- se retrouve en TETE "
                  "quel que soit leur ordre. REMONTER la bataille, puis reposer SANS avoir rien "
                  "pose avant.")
    stop("aucun des deux ordres de pose ne rend l'ordre de conversion du replay. NE PAS "
         "demarrer : les squads seraient attribues autrement et chaque coup frapperait une "
         "autre unite." + detail)


def controler_le_lineup(jeu, d):
    """⛔ << PAS QUESTION DE LUI ENVOYER UN TRUC OU ON EST 10 >>.

    (!)ON COMPTE `ordreConversion`, PAS `deploymentPlacees`. La premiere est la liste que le
    START PARCOURT ; la seconde rend des entrees MEMOIRE brutes, sans nom, dont la taille est
    celle du tampon et pas celle du deploiement. Compter la mauvaise ferait lire << 5 >> sur un
    tampon de 5 quel qu'en soit le contenu.

    ⚠ ET LA MACHINE OF WAR EN FAIT PARTIE. Comparer aux seules `poses_du_replay` faisait lire 5
    noms attendus contre 6 vus sur une bataille qui en porte une -- donc un ARRET sur un lineup
    JUSTE. Elle compte : c'est une unite de plus a l'ecran, et l'interdit qui commande ce cran
    (<< pas question de lui envoyer un truc ou on est 10 >>) porte sur ce qui entre en bataille,
    machine comprise.
    """
    attendu, _n, refus = mise_en_place_du_replay(d)
    if attendu is None:
        stop(refus)
    voulu = sorted("%s%s" % (x["unitId"], " (MoW)" if x["genre"] == "mow" else "")
                   for x in attendu)
    e = jeu.rpc("deploymentEtat", [{}], timeout=180000)
    vues = e.get("ordreConversion") if isinstance(e, dict) else None
    if not isinstance(vues, list):
        print("   lineup NON MESURE (`ordreConversion` illisible) -- ce n'est PAS << conforme >>.")
        return
    noms = sorted("%s%s" % (v.get("unitId"), " (MoW)" if v.get("mow") else "")
                  for v in vues if isinstance(v, dict))
    if noms != voulu:
        stop("le lineup pose (%d : %s) n'est pas celui du replay (%d : %s)."
             % (len(noms), ", ".join(map(str, noms)), len(voulu), ", ".join(voulu)))
    print("   lineup conforme : %d entree(s), %s" % (len(noms), ", ".join(noms)))


def demarrer(jeu, attendus, sur_reelle=False, plafond_s=20.0):
    """(!)L'APPEL PASSE NE DIT RIEN DU DEMARRAGE, et son propre retour le dit : mesure du
    2026-08-21, `battleStatus` lu a l'instant du retour rend `stageName: Setup` avec 4 unites.
    `HandleOnStartBattleTapped` ENCLENCHE la conversion des placeholders ; elle se deroule sur
    les frames suivantes. On attend donc LE FAIT (`Running`), pas une duree.

    Il n'y a pas de signal push ici : le runner ne CHANGE pas au START, il existe deja depuis le
    montage -- `attendreRunner` ne mordrait jamais.
    """
    r = jeu.rpc("deploymentStartInvoquer", [{"confirmer": True}], timeout=180000)
    if not isinstance(r, dict) or not r.get("ok"):
        stop("le START a ECHOUE : %s" % json.dumps(r, ensure_ascii=False)[:280])
    debut, b = time.time(), None
    while time.time() - debut < plafond_s:
        b = jeu.rpc("battleStatus", [{}], timeout=120000)
        if isinstance(b, dict) and b.get("stageName") == "Running":
            break
        time.sleep(0.2)
    if not isinstance(b, dict) or b.get("stageName") != "Running":
        stop("apres START, la bataille n'est toujours pas `Running` apres %.0f s : %s"
             % (time.time() - debut, json.dumps(b, ensure_ascii=False)[:280]))
    print("   `Running` apres %.1f s." % (time.time() - debut))
    s = jeu.rpc("replaySteps", [{"maxSteps": 200}], timeout=180000)
    pas = (s or {}).get("steps") if isinstance(s, dict) else None
    if pas is None:
        stop("`replaySteps` NON MESURE apres START.")
    if len(pas) != attendus:
        stop("%d pas de mise en place enregistres, %d attendus par le replay -- la BC ou le "
             "deploiement differe." % (len(pas), attendus))
    print("   `Running`, %d pas de mise en place (conforme au replay)." % len(pas))


def rejouer_les_coups(chemin, depuis, hote, sid):
    """(!)DELEGUE, PAS RECOPIE. `replay_rejouer.py` porte deja le cran d'appariement, l'arret au
    premier ecart et l'affichage du delta par `Apply`. Le dupliquer ferait deux verites."""
    cmd = [sys.executable, str(RACINE / "scripts" / "python" / "replay_rejouer.py"),
           "--replay", str(chemin), "--vivant", "--depuis", str(depuis),
           "--arret-au-premier-ecart", "--hote", hote, "--session", str(sid)]
    return subprocess.run(cmd, cwd=str(RACINE), text=True).returncode


def jouer_la_suite(jeu, d, chemin, hote, sid, premier_cran=8, sur_reelle=False):
    """LA SUITE ENTIERE -- pose, lineup, START, rejeu. Identique aux deux chaines.

    `premier_cran` decale seulement la NUMEROTATION affichee : les deux chaines n'ont pas le
    meme nombre de crans avant celui-ci, et un journal dont les numeros sautent se lit mal.

    ⚠ LE NOMBRE DE PAS DE MISE EN PLACE SE DERIVE DU REPLAY, il ne se calcule plus. Il valait
    `len(poses_du_replay) + 1` -- les unites, plus le `StartBattleMessage`. Sur une bataille qui
    porte une Machine of War il en manque UN : le START produit AUSSI un `AddMachineMessage`, et
    le replay de maradak porte bien 7 messages de mise en place pour 5 unites (mesure du
    2026-08-21). Le calcul aurait fait echouer le cran du START sur un demarrage JUSTE, et
    demarre le rejeu des coups un cran trop tot -- donc chaque coup sur la mauvaise unite.
    """
    attendu, n_mise_en_place, refus = mise_en_place_du_replay(d)
    if attendu is None:
        stop(refus)

    cran(premier_cran, "le deploiement -- CONFRONTER, ne poser que s'il diverge")
    sens = poser_le_deploiement(jeu, d, sur_reelle=sur_reelle)
    controler_le_lineup(jeu, d)
    print("   CONFORME (%s), cases comprises." % sens)

    cran(premier_cran + 1, "START")
    demarrer(jeu, n_mise_en_place)

    cran(premier_cran + 2, "rejouer les coups -- delegue a `replay_rejouer.py`")
    return rejouer_les_coups(chemin, n_mise_en_place, hote, sid)
