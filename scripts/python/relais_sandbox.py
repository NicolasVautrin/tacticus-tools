"""LES RELAIS SANDBOX : qui ECRIT, qui OBSERVE, et comment lire leur etat.

Module FEUILLE -- il n'importe rien du depot. C'est ce qui lui permet d'etre la source
UNIQUE de la liste, lue a la fois par le desarmement manuel (`desarmer_relais.py`) et par
l'armement de la fermeture automatique (`sandbox_fenetre_armer`, ci-dessous), sans cycle.

(!)UNE SEULE COPIE DE LA LISTE, ET C'EST LE POINT. Le hook `sandbox-fenetre.ts` desarme a la
mort de la fenetre, mais il n'ECRIT PAS la liste : le pilote la lui PASSE a l'armement. En
tenir une seconde copie cote TypeScript, c'est garantir qu'une des deux se perime en silence
-- exactement ce qui est arrive aux deux RPC retires ci-dessous, qui ont fait rougir le garde
a chaque passage jusqu'a ce qu'on cesse de le lire.
"""

# Les relais qui ECRIVENT -- (rpc, corps de desarmement).
ECRIVENT = [
    ("deploymentPoolArmer", {"armer": False}),
    ("deploymentPhaseArmer", {"armer": False}),
    ("deploymentPlafondArmer", {"armer": False}),
    ("deploymentClearArmer", {"armer": False}),
    ("deploymentDeposeArmer", {"armer": False}),
    # (!)`deploymentPoseCommitArmer` et `deploymentPoseFsmArmer` ONT ETE RETIRES DE CETTE LISTE
    # le 2026-08-21 : les deux RPC n'existent plus (la voie commit a ete supprimee, la pose passe
    # toujours par l'etage FSM). Le host rendait donc `unable to find method`, que le desarmement
    # classait -- correctement -- en NON MESURE, et il sortait en rc 1 A CHAQUE PASSAGE. Un garde
    # qui rougit toujours est un garde qu'on cesse de lire : c'est exactement ce qui laisse
    # repasser le relais qu'il devait attraper. Retirer l'entree morte n'affaiblit rien -- il n'y
    # a plus de relais derriere elle.
    ("deploymentMemoire", {"armer": False}),
    ("deploymentPrefabArmer", {"armer": False}),
    ("deploymentDraftArmer", {"armer": False}),
    ("deploymentStartArmer", {"armer": False}),
    ("deploymentSyncArmer", {"armer": False}),
    ("deploymentBoutonArmer", {"armer": False}),
    ("deploymentJetArmer", {"armer": False}),
    ("deploymentVidangeArmer", {"armer": False}),
    ("deploymentCheminsArmer", {"armer": False}),
    ("deploymentRunnerStartArmer", {"armer": False}),
    ("deploymentPoolSansFiltre", {"armer": False}),
    ("sandboxModeGameViews", {"armer": False}),
    # Ces deux-la ne se desarment PAS par `armer` -- leur forme de retrait est propre.
    ("sandboxModeBcOverride", {"configJson": None}),
    ("sandboxModeSeed", {"seed": None}),
]

# Ce qu'on LAISSE, et pourquoi. Nomme, jamais implicite.
OBSERVENT = [
    ("deploymentHudArmer", "lit le HUD et le verdict de chaque clic -- n'ecrit rien"),
    ("deploymentPoseDiag", "diagnostic de pose"),
    ("vueExceptionArmer", "capte les exceptions de vue, celles qui tuent une bataille en silence"),
    ("replayFinAuto", "capture le replay en fin de bataille"),
]


def armer_relais_sandbox(jeu, armements, timeout=180000, fenetre=True):
    """LE POINT DE PASSAGE DES MONTAGES SANDBOX : armer les relais ET leur extinction, ENSEMBLE.

    ⛔ POURQUOI IL FALLAIT LE CREER. Cote sandbox il n'existait AUCUN point de passage : chaque
    pilote recopiait la meme boucle (`for nom, corps in armements: jeu.rpc(...)`), et la
    fermeture de fenetre etait un appel SEPARE, donc oubliable. Mesure du 2026-08-26 : sur les
    8 pilotes qui arment des relais d'ECRITURE, **6 n'armaient pas la fermeture** -- trois d'entre
    eux en armant ONZE relais chacun. Consequence sur une sandbox quittee : `sandboxModeBcOverride`
    encore actif, donc la BC de la premiere bataille REELLE venue substituee, et la composition
    precedente rejouee sur le plateau.
    (`deploiement_commun.armer_les_relais` n'etait PAS ce point de passage : seules les deux
    chaines de bataille REELLE l'empruntent, et elles ne doivent justement PAS eteindre leurs
    relais en fin de passe -- la boucle de farm en rejoue une autre derriere.)

    ⛔ `fenetre=False` QUAND L'APPELANT VA MONTER DERRIERE, ET C'EST MESURE. Il etait ecrit ici que
    l'armement de la fermeture AVANT le montage etait « une condition », parce que c'est la seule
    position qui couvre une fenetre morte tot (montage refuse, retraite immediate). La mesure du
    2026-08-26 dit l'inverse : dans cette position, le veilleur se met a surveiller PENDANT LE
    CHARGEMENT, et son critere -- « 4 s sans un seul appel de la pompe de bataille » -- est
    exactement la duree d'un chargement. Il conclut donc que la scene a DISPARU alors qu'elle
    APPARAIT, et eteint les 19 relais qu'on vient d'armer.

    Effet constate, sur `mirror4` noeud 29 : `deploymentPlafondArmer` retombe a `impose: None`, le
    HUD garde `maxUnitsPossible: 0` (il lit ses bornes UNE FOIS, a l'ouverture de l'ecran), et le
    joueur ne peut poser AUCUNE unite -- sans le moindre message. Deux bilans successifs du
    veilleur (`frameNo` 296575 puis 329803) montrent le second tir tombant apres le montage.

    ⚠ LA PARADE N'EST PAS UN DELAI. Attendre « un peu plus » avant d'armer ne fait que deplacer la
    course. On arme sur un SIGNAL : `sandbox_fenetre_armer_quand_vivante` ci-dessous attend que la
    bataille soit OBSERVEE en jeu, etat dans lequel `vuVivant` est legitimement vrai.

    ⚠ Ce que `fenetre=False` fait PERDRE, et il faut le savoir : un montage REFUSE laisse alors les
    relais armes. C'est deja le cas couvert par `desarmer_relais.py`, et que la fermeture
    n'a jamais promis (« elle ne couvre pas un pilote qui s'arrete AVANT d'avoir monte »).

    Rend la liste des noms armes.
    """
    poses = []
    for nom, corps in armements:
        r = jeu.rpc(nom, [dict(corps)], timeout) or {}
        ok = isinstance(r, dict) and r.get("ok")
        print("  %-28s %s" % (nom, "ok" if ok else ("REFUS %s" % str(r)[:120])))
        if ok:
            poses.append(nom)
    if fenetre:
        sandbox_fenetre_armer(jeu)
    return poses


def arme_selon(r):
    """Tri-etat : True / False / None = PAS MESURE. Un `arme` illisible n'est PAS un `False`."""
    if not isinstance(r, dict):
        return None
    if isinstance(r.get("arme"), bool):
        return r["arme"]
    # (!)LE NOM DU CHAMP N'EST PAS UNIFORME, et le supposer a fait rendre `NON MESURE` a cinq
    # relais pourtant bien desarmes (mesure du 2026-08-20). `actif` chez les relais de pose,
    # `ancres` (liste des methodes ancrees) chez `deploymentCheminsArmer`.
    if isinstance(r.get("actif"), bool):
        return r["actif"]
    if isinstance(r.get("ancres"), list):
        return len(r["ancres"]) > 0
    # `deploymentPoolArmer` et `deploymentPlafondArmer` rendent l'etat par sous-objets.
    for cle in ("delegations", "max", "min"):
        v = r.get(cle)
        if isinstance(v, list) and any(x.get("arme") for x in v if isinstance(x, dict)):
            return True
        if isinstance(v, dict) and v.get("arme"):
            return True
    if isinstance(r.get("delegations"), list):
        return False
    if isinstance(r.get("max"), dict) or isinstance(r.get("min"), dict):
        return False
    return None


def sandbox_fenetre_armer(jeu, timeout=60000):
    """ARMER la fermeture automatique, A L'OUVERTURE de la fenetre sandbox.

    A appeler par tout pilote qui MONTE une bataille sandbox, juste apres avoir arme ses
    relais. Les relais seront eteints a la mort de la fenetre -- `stage -> Finished`, ou
    `_runner -> null` (RETRAITE : on peut se retirer d'une sandbox, et c'est la voie la plus
    courante).

    Rend le retour du RPC, ou `None` si le RPC n'existe pas dans le bundle charge -- ce qui est
    le cas de tout bundle anterieur au 2026-08-24. `None` = PAS MESURE : l'appelant DIT que la
    fermeture n'est pas armee, il ne fait pas comme si elle l'etait.

    (!)CA N'EXEMPTE PAS DE `desarmer_relais.py`. La fermeture automatique couvre la mort de la
    fenetre ; elle ne couvre pas un pilote qui s'arrete AVANT d'avoir monte quoi que ce soit,
    ni une session ou quelqu'un a arme des relais a la main.
    """
    corps = {"armer": True,
             "relais": [{"rpc": nom, "corps": c} for nom, c in ECRIVENT]}
    try:
        r = jeu.rpc("sandboxFenetre", [corps], timeout)
    except Exception as e:  # noqa: BLE001
        print("  %-28s NON ARMEE (%s: %s)" % ("fermeture de fenetre", type(e).__name__,
                                              str(e)[:120]))
        return None
    if not isinstance(r, dict) or not r.get("ok"):
        print("  %-28s NON ARMEE : %s" % ("fermeture de fenetre", str(r)[:200]))
        return None
    print("  %-28s armee -- %d relais s'eteindront a la mort de la fenetre"
          % ("fermeture de fenetre", len(ECRIVENT)))
    return r


def sandbox_fenetre_armer_quand_vivante(jeu, essais=300, timeout=60000):
    """ARMER la fermeture UNE FOIS LE HUD DE DEPLOIEMENT PRESENT -- sur SIGNAL, jamais sur un delai.

    A appeler par tout pilote qui MONTE, juste apres le montage, en ayant passe `fenetre=False`
    a `armer_relais_sandbox`. Voir le pave d'`armer_relais_sandbox` pour la mesure qui l'impose.

    ⛔ LE SIGNAL EST LE HUD, PAS LE RUNNER. Ce qu'on protege est une FENETRE, c'est-a-dire une VUE
    -- et c'est le HUD qui lit `minUnitsPossible` / `maxUnitsPossible`, UNE SEULE FOIS, a son
    ouverture. `state.liveRunner` est la logique de bataille : il peut etre non nul sans qu'aucun
    HUD ne soit monte (et l'inverse au demontage). Prendre le runner pour signal, c'est armer sur
    une fenetre qui n'existe pas encore -- exactement la faute qu'on repare, deplacee d'un cran.

    ⛔ AUCUN `sleep` ICI. Le critere de sortie est l'ETAT observe (le HUD a une instance), pas une
    duree. Le rythme de la boucle est celui des allers-retours RPC eux-memes : un delai fixe
    encoderait une hypothese sur la vitesse de la machine, et c'est precisement l'hypothese fausse
    qui a produit la panne.

    ⚠ TRI-ETAT. Si le HUD n'apparait JAMAIS, on n'arme PAS et on le DIT : armer sur une fenetre
    qu'on n'a pas vue, c'est refaire l'erreur dans l'autre sens. Rend le retour du RPC, ou `None`
    = PAS ARMEE (et la raison est imprimee).
    """
    for _ in range(essais):
        try:
            h = jeu.rpc("deploymentHudArmer", [{}], timeout) or {}
        except Exception:  # noqa: BLE001
            continue
        etat = h.get("etat") if isinstance(h, dict) else None
        if isinstance(etat, dict) and etat.get("hud") not in (None, "0x0"):
            return sandbox_fenetre_armer(jeu, timeout)
    print("  %-28s NON ARMEE : HUD de deploiement jamais VU (%d tentatives). Les relais restent "
          "armes -- `desarmer_relais.py` pour les eteindre."
          % ("fermeture de fenetre", essais))
    return None
