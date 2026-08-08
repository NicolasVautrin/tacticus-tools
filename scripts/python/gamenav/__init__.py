"""gamenav -- naviguer dans Tacticus : voir, agir, et PROUVER que l'action a porte.

CE PAQUET EST UN BARIL VIDE, ET C'EST VOULU.

Il n'importe RIEN. Le `CLAUDE.md` mesure ce que coute l'inverse : un `__init__` qui tire ses
sous-modules fait passer `import engine.entities` de 2 a 94 modules charges, et c'est la cause
racine des cycles qu'on repare ensuite a coups d'imports differes. Chaque appelant entre par
le module dont il a besoin :

    from gamenav import vue          # L1 -- observer
    from gamenav import agir         # L2 -- agir et prouver

LES QUATRE COUCHES, ET LA MESURE QUI JUSTIFIE CHACUNE
-----------------------------------------------------
L0  `transport`  Deux voies pour la meme intention : le clic UI et l'invoke IL2CPP direct.
                 Le warmup utilise deja la seconde (`IdunNavigation.ToCampaign`) pour
                 remplacer trois clics fragiles -- certaines transitions n'ont pas de bouton.
                 Les deux TENTENT ; aucune ne rapporte la verite.

L1  `vue`        L'ecran s'identifie par ses PREFABS, jamais par un compte de boutons.
                 Mesure du 2026-08-08 : `HomeScreen` passe de 38 a 57 boutons SANS changer
                 d'ecran, quand des widgets finissent de charger.

L2  `agir`       << Agir >> n'existe pas comme operation primitive, parce que le retour d'un
                 clic est faux DANS LES DEUX SENS (mesure : `ok:true` sur un clic avale,
                 `ok:false` sur trois clics qui ont porte). Seul << agir ET PROUVER >>
                 existe : empreinte avant, action, attente d'un changement d'empreinte.

L3  `carte`      Le graphe des ecrans est une DONNEE, pas du code. La chaine du warmup
                 (`PLAY_BUTTON_KEY`, "campaign1", pause -> retraite -> confirm) est un
                 chemin parmi d'autres, pas une fonction figee.

Transverses :
    `journal`    Toutes les pannes rencontrees ici sont de la forme << ca a dit X, la realite
                 etait Y >>. Sans trace on les redecouvre a chaque fois.
    `secours`    `maison()` n'est JAMAIS gate et ne vit PAS dans le graphe. Mesure :
                 l'onglet Home remonte l'accueil quand tout le reste echoue.

⚠ LA SESSION EST PARTAGEE. Toute action qui DEPLACE le jeu passe par le garde de calme de
`transport` : un runner vivant, ou un capteur en panne, valent REFUS.

ASCII strict dans toute sortie console (cp1252).
"""

__all__ = ["transport", "vue", "agir", "carte", "journal", "secours"]
