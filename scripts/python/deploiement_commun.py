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
import subprocess
import sys
import time
from pathlib import Path

RACINE = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(Path(__file__).resolve().parent))

from replay_rejouer import poses_du_replay, controler_avant_start      # noqa: E402


def stop(msg, code=2):
    print()
    print("ARRET -- " + msg)
    sys.exit(code)


def cran(n, titre):
    print()
    print("CRAN %-2s -- %s" % (n, titre))


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

    for etiquette, suite in (("INVERSE de l'ordre du replay", list(reversed(voulu))),
                             ("ordre du replay", list(voulu))):
        poses = [{"unitId": u, "playerId": 11, "col": c, "row": r} for (u, c, r) in suite]
        jeu.rpc("deploymentMemoire", [{"poser": {"poses": poses, "mow": mow}}], timeout=120000)
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

    stop("aucun des deux ordres de pose ne rend l'ordre de conversion du replay. NE PAS "
         "demarrer : les squads seraient attribues autrement et chaque coup frapperait une "
         "autre unite.")


def controler_le_lineup(jeu, d):
    """⛔ << PAS QUESTION DE LUI ENVOYER UN TRUC OU ON EST 10 >>.

    (!)ON COMPTE `ordreConversion`, PAS `deploymentPlacees`. La premiere est la liste que le
    START PARCOURT ; la seconde rend des entrees MEMOIRE brutes, sans nom, dont la taille est
    celle du tampon et pas celle du deploiement. Compter la mauvaise ferait lire << 5 >> sur un
    tampon de 5 quel qu'en soit le contenu.
    """
    voulu = sorted(u for (u, _c, _r) in (poses_du_replay(d) or []))
    e = jeu.rpc("deploymentEtat", [{}], timeout=180000)
    vues = e.get("ordreConversion") if isinstance(e, dict) else None
    if not isinstance(vues, list):
        print("   lineup NON MESURE (`ordreConversion` illisible) -- ce n'est PAS << conforme >>.")
        return
    noms = sorted(v.get("unitId") for v in vues if isinstance(v, dict))
    if noms != voulu:
        stop("le lineup pose (%d : %s) n'est pas celui du replay (%d : %s)."
             % (len(noms), ", ".join(map(str, noms)), len(voulu), ", ".join(voulu)))
    print("   lineup conforme : %d unites, %s" % (len(noms), ", ".join(noms)))


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
    """
    n_pose = len(poses_du_replay(d) or [])

    cran(premier_cran, "le deploiement -- CONFRONTER, ne poser que s'il diverge")
    sens = poser_le_deploiement(jeu, d, sur_reelle=sur_reelle)
    controler_le_lineup(jeu, d)
    print("   CONFORME (%s), cases comprises." % sens)

    cran(premier_cran + 1, "START")
    demarrer(jeu, n_pose + 1)          # les poses + le `StartBattleMessage`

    cran(premier_cran + 2, "rejouer les coups -- delegue a `replay_rejouer.py`")
    return rejouer_les_coups(chemin, n_pose + 1, hote, sid)
