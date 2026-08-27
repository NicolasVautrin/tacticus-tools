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

# Les relais qui ECRIVENT mais qu'on NE DESARME PAS, et POURQUOI.
#
# ⛔ CETTE LISTE EXISTE PARCE QUE L'OMISSION N'EST PAS UNE DECISION LISIBLE. `lineupRetraiteCommit`
# ecrit dans le jeu -- il n'avait donc rien a faire dans `OBSERVENT` -- mais il ne devait pas
# entrer dans `ECRIVENT` non plus. Il etait donc epargne par ABSENCE, c'est-a-dire de facon
# invisible : rien dans la sortie du desarmement ne disait qu'il existait, ni qu'il fallait le
# laisser. Mesure du 2026-08-28 : je l'ai desarme A LA MAIN dans un << menage avant le live >>,
# et la composition du joueur a perdu son heros (Kariyan retire de `eliteMirror3_5`) -- deux fois
# dans la soiree, la premiere ayant coute une lineup entiere (Haarken remplace par Volk).
#
# ⚠ Une liste d'epargnes n'est pas une liste d'exceptions : c'est la partie de la decision qu'on
# doit POUVOIR LIRE. Le script les imprime a chaque passage, avec leur etat et leur raison.
EPARGNES = [
    ("lineupRetraiteCommit",
     "il TIENT la composition posee en sandbox : l'eteindre la defait, SANS le moindre message. "
     "Capter la lineup a CHAQUE retraite EST sa fonction."),
]


def armer_relais_sandbox(jeu, armements, timeout=180000, fenetre=True, lineup=None):
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
    course -- et la premiere version de la parade EN ETAIT UN, sous un autre nom : une boucle
    bornee a 300 sondages du HUD, qui a fini par expirer pour de bon le 2026-08-27. Cf. le pave de
    `sandbox_fenetre_armer_quand_vivante`.

    ⚠ CE QUI REND L'ARMEMENT POST-MONTAGE SUR, ET CE N'EST PAS UN DELAI NON PLUS : le garde
    `vuVivant` du HOOK. La veille << pompe arretee >> est explicitement court-circuitee tant
    qu'aucune fenetre n'a vecu (`if (!vuVivant) { ...; return; }`, commente << une pompe a l'arret
    est alors l'etat NORMAL >>). Le scenario decrit ci-dessus -- conclure a la mort PENDANT un
    chargement -- ne peut donc plus se produire avant l'ouverture. C'est ce garde, cote hook, qui
    remplace le sondage cote Python, pas une temporisation mieux reglee.

    ⚠ ET LES DEUX PANNES SONT TOUTES DEUX SILENCIEUSES -- ne pas se rassurer en croyant que l'une
    << se verrait >>. Desarmer trop tot ne dit RIEN (le joueur ne peut poser aucune unite, sans
    message : c'est la mesure du 2026-08-26 juste au-dessus) ; ne pas armer ne dit rien non plus
    jusqu'a la bataille REELLE suivante. Le seul controle qui tranche reste la LECTURE des relais
    (`sandboxModeBcOverride {}`, `deploymentMemoire {}` -> `arme`).

    ⚠ Ce que `fenetre=False` fait PERDRE, et il faut le savoir : un montage REFUSE laisse alors les
    relais armes. C'est deja le cas couvert par `desarmer_relais.py`, et que la fermeture
    n'a jamais promis (« elle ne couvre pas un pilote qui s'arrete AVANT d'avoir monte »).

    ⛔ `lineup` EST OBLIGATOIRE POUR CONSERVER LA COMPOSITION, ET SON ABSENCE SE DIT. Le jeu
    n'ecrit la lineup d'un noeud que par `UnitProgression$$SetBattleLineupLocally`, normalement a
    la VICTOIRE ; en sandbox on sort par la RETRAITE, donc rien n'est ecrit. `lineupRetraiteCommit`
    est le seul chemin -- il lit, a la retraite, la composition REELLEMENT en jeu et la pose sur la
    cible. Sans lui, poser sa lineup en sandbox ne la conserve pas, SANS LE MOINDRE MESSAGE.

    (!)POURQUOI ICI ET PLUS DANS LES PILOTES. Deux pilotes sur huit (`sandbox_gw`,
    `sandbox_onslaught`) recopiaient la meme paire desarmement/armement ; les six autres ne
    l'armaient pas. Mesure du 2026-08-27 sur `elite2` noeud 11 : composition posee a la main,
    sortie par la retraite, remontage -- le jeu reproposait l'ANCIENNE (`lineupRetraiteCommit`
    rendait `arme: false, fires: 0`). C'est exactement le gisement que ce point de passage existe
    pour tuer, et il l'avait laisse passer.

    ⚠ LA CIBLE NE SE DEVINE PAS : ELLE EST PROPRE A LA SOURCE. Chaque `AGameModeSource` fabrique
    sa clef, et elles n'ont pas la meme forme -- `CampaignGameModeSource$$GetBattleLineup` fait
    `Concat(<campagneId>, "_", lineupIndex)` ou `lineupIndex` est le nombre de PLACES (mesure :
    `elite2_5` -> 5 unites, `elite2_3` -> 3, `elite2_10` -> VIDE), tandis que
    `OnslaughtLineupParser$$GetLineupKey` fait `Concat("onslaught", "_", <alliance>)`. Une clef
    fausse ne leve RIEN : elle range a cote, en silence. L'appelant la passe donc explicitement --
    `{"cle": "elite2_5"}` (magasin) ou `{"mode": "guildWar"}` (registre, pour les modes SANS
    magasin). On ne rend jamais une clef devinee.

    ⚠ ON DESARME AVANT D'ARMER, SANS CONDITION. Re-armer sur une autre cible alors qu'il l'est
    deja rend << deja arme -- desarmer pour changer de cible >> et GARDE l'ancienne : la
    composition partirait sous la cible du mode PRECEDENT. Et ce relais n'est PAS dans `ECRIVENT`
    (donc la fermeture de fenetre ne l'eteint pas) precisement parce qu'il doit tirer AU MOMENT de
    la retraite -- il survit donc a la sandbox, et c'est ce desarmement-ci qui le rattrape.

    Rend la liste des noms armes.
    """
    if lineup is None:
        print("  %-28s ABSENT -- la composition posee ne sera PAS conservee (le jeu n'ecrit"
              % "lineupRetraiteCommit")
        print("  %-28s qu'a la victoire ; on sort par la retraite). Passer"
              % "")
        print("  %-28s `lineup={\"cle\": ...}` ou `{\"mode\": ...}` pour l'armer."
              % "")
    else:
        if not isinstance(lineup, dict) or (("cle" in lineup) == ("mode" in lineup)):
            raise ValueError(
                "`lineup` attend EXACTEMENT une cible : {'cle': <magasin>} OU {'mode': <registre>}"
                " -- recu %r. Les deux, ou aucune, ne designe rien." % (lineup,))
        armements = ([("lineupRetraiteCommit", {"armer": False})]
                     + list(armements)
                     + [("lineupRetraiteCommit", dict(lineup, armer=True, confirmer=True))])

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


def banc_lire(jeu, timeout=60000):
    """DIRE si le banc est arme AVANT la forge -- une LECTURE, elle n'ecrit rien.

    Le patch de BC (`env_ability_patch.py` : buffs, debuffs, calendrier de vagues, abilities
    d'environnement) s'applique au `LoadBattle.onLeave`. Le lire avant la forge est ce qui
    distingue << la BC va en sortir patchee >> de << personne n'a arme le banc >>, dont l'oubli
    est autrement SILENCIEUX : la sandbox monte normalement, seul le compte de modificateurs
    tombe a 0.

    ⛔ IL N'Y A RIEN A << RESTAURER >>, ET `banc_restaurer` A ETE RETIRE (2026-08-26). Il partait
    de la these que `consumeOnce` etait obligatoire pour eviter la double application ; c'est FAUX
    dans les deux sens. D'abord parce que le banc n'est PAS specifique a un montage : son reglage
    vaut pour TOUTES les batailles, donc `env_ability_patch.py` pose `consumeOnce: False` par
    defaut et le patch DOIT rester arme -- il n'est jamais consomme, il n'y a donc rien a
    remettre. Ensuite parce que la double application n'est plus nuisible : la pose est devenue
    IDEMPOTENTE (`environment-abilities.ts`, `empreinteEnhancement`), et c'est la vraie reparation
    -- un patch permanent se rejoue a chaque `LoadBattle`, plusieurs fois par montage, donc seule
    l'idempotence tient. Re-armer restait alors nuisible dans le SEUL cas ou il agissait : sur un
    `--une-fois` DEMANDE explicitement, il defaisait l'intention de l'appelant.

    ⚠ TRI-ETAT : rend `None` quand l'etat n'est PAS MESURE **et** quand il n'y a rien d'arme --
    l'appelant les distingue a l'ecran par le message imprime ici.
    """
    r = jeu.rpc("getBattleConfigPatchStatus", [{}], timeout) or {}
    if not (isinstance(r, dict) and r.get("ok")):
        print("  %-28s NON MESURE : %s" % ("banc", str(r)[:150]))
        return None
    p = r.get("pending")
    if p:
        cles = ", ".join(sorted(p.keys())) if isinstance(p, dict) else "?"
        print("  %-28s ARME (%s) -- la BC produite en sortira DEJA PATCHEE" % ("banc", cles))
    else:
        print("  %-28s aucun -- `env_ability_patch.py --poser ...` AVANT, pour l'armer"
              % "banc")
    return p or None


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


def sandbox_fenetre_armer_quand_vivante(jeu, essais=None, timeout=60000):
    """ARMER la fermeture TOUT DE SUITE -- c'est le HOOK qui attend l'ouverture, pas nous.

    A appeler par tout pilote qui MONTE, juste apres le montage, en ayant passe `fenetre=False`
    a `armer_relais_sandbox`. Voir le pave d'`armer_relais_sandbox` pour la mesure qui l'impose.

    ⛔ ELLE A SONDE, ET C'ETAIT UN TIMER DEGUISE. Elle appelait `deploymentHudArmer` jusqu'a 300
    fois en attendant de VOIR le HUD, et sa propre docstring affirmait << sur SIGNAL, jamais sur un
    delai >> puis << AUCUN `sleep` ICI >>. Les deux etaient faux dans les faits : une boucle BORNEE
    est un delai, simplement libelle en allers-retours RPC au lieu de secondes -- et sa borne
    encodait exactement l'hypothese qu'elle pretendait bannir, celle du temps que met un humain a
    rejoindre l'ecran de deploiement. Mesure du 2026-08-27 (`elite2` 25) : les 300 essais se sont
    ecoules AVANT l'arrivee sur l'ecran, la fermeture n'a pas ete armee, et `sandboxModeBcOverride`
    comme `deploymentMemoire` etaient encore `arme=True` apres la bataille -- la panne meme que ce
    module existe pour empecher. La prose a fait passer le timer pour un signal ; c'est ce qui l'a
    rendu invisible a la relecture.

    ⛔ LE GARDE D'OUVERTURE EXISTE DEJA, ET IL EST DANS LE HOOK. `sandbox-fenetre.ts` porte
    `vuVivant`, pose par la POMPE (`if (state.liveRunner) vuVivant = true;` dans
    `surveillerFinDeFenetre`, appele a chaque frame) et exige par les QUATRE declencheurs de
    fermeture. A l'armement il vaut `state.liveRunner !== null` -- donc `false` quand on arme avant
    la bataille, puis il bascule SEUL a l'ouverture. Armer hors bataille est le cas PREVU, pas un
    cas limite : le hook ne peut rien fermer tant qu'il n'a rien vu vivre. Sonder cote Python
    refaisait ce travail, en moins bien, et ajoutait la seule course qui pouvait etre perdue.

    ⚠ L'ANCIEN ARGUMENT -- << le signal est le HUD, pas le runner ; le runner peut etre non nul
    sans qu'aucun HUD soit monte >> -- reste vrai, mais il ne porte pas. Ce que `vuVivant` empeche,
    c'est de se consommer sur un detachement ANTERIEUR a la fenetre ; laquelle des deux vies on
    observe est alors indifferent.

    ⛔ ET ON NE SE RASSURE PAS EN SE DISANT QUE L'AUTRE PANNE << SE VERRAIT >>. J'ai d'abord ecrit
    ici qu'armer trop tot echouait FERME, donc visiblement -- c'est FAUX, et le fichier le mesurait
    deja quinze lignes plus haut : des relais eteints trop tot laissent un HUD a
    `maxUnitsPossible: 0` et un joueur qui ne peut poser AUCUNE unite, SANS le moindre message.
    Les deux pannes sont muettes. Ce qui autorise l'armement immediat n'est donc pas un arbitrage
    entre elles, c'est le garde `vuVivant` du hook, qui rend la premiere IMPOSSIBLE avant
    l'ouverture.

    `essais` est conserve pour ne casser aucun appelant ; il est IGNORE, et le dit.
    """
    # ⛔ L'ARMEMENT IMMEDIAT A ETE ESSAYE LE 2026-08-27, ET IL CASSE -- garder le sondage jusqu'a
    # ce que le hook sache attendre une TRANSITION. Mesure, sur `elite2` 25 : la fermeture a tire
    # dans la seconde, `raison = "pompe de bataille ARRETEE (4 s sans un seul appel)"`, 19 relais
    # eteints sur un montage qui venait de les armer. Le garde `vuVivant` n'a pas protege parce
    # qu'il vaut `state.liveRunner !== null` A L'INSTANT DE L'ARMEMENT : un runner de la bataille
    # PRECEDENTE le met a `true` tout de suite, apres quoi la pompe se tait pendant la transition
    # de scene et la veille conclut a la mort. C'est la panne du 2026-08-26, retrouvee a
    # l'identique.
    for _ in range(essais if essais is not None else 300):
        try:
            h = jeu.rpc("deploymentHudArmer", [{}], timeout) or {}
        except Exception:  # noqa: BLE001
            continue
        etat = h.get("etat") if isinstance(h, dict) else None
        if isinstance(etat, dict) and etat.get("hud") not in (None, "0x0"):
            return sandbox_fenetre_armer(jeu, timeout)
    print("  %-28s NON ARMEE : HUD de deploiement jamais VU (%d tentatives). Les relais restent "
          "armes -- `desarmer_relais.py` pour les eteindre."
          % ("fermeture de fenetre", essais if essais is not None else 300))
    return None
