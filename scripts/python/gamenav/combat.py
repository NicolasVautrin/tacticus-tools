"""L2bis -- CONDUIRE UN TOUR DE COMBAT par l'interface, et PROUVER chaque cran.

Pendant du `deploiement` : celui-ci compose avant la bataille, celui-ci la joue. Aucun message
vers le runner -- on joue ce que le joueur joue, et on juge sur l'EFFET.

LA CHAINE, CONFRONTEE LE 2026-08-09 (`Campaign1_06`, build `rnca9r7q6c`)
------------------------------------------------------------------------
    reset        `back` jusqu'a NormalState
    selection    `down(TUILE)` puis `up(UNITE)`      -> UnitNormallySelected
    armement     `uiClick` sur la barre d'abilities  -> Ability_Info_Bar_HUD
    designation  `up(CIBLE)`                          -> le cast part

Un seul geste a rendu 3 ennemis a 0 pv, le caster sorti de `toActivate`, et `battleEvents.pile`
vide (aucun `Apply` n'a leve).

⚠ LE RANG DU BOUTON NE DESIGNE PAS UNE ABILITY. La barre monte DEUX boutons de chemin
IDENTIQUE (`Ability_Selection_HUD/.../Button` -- meme parent, meme nom). Mesure : le rang
portant l'actif etait 1 a un essai et 0 au suivant, MEME unite, MEME bataille. Le rang sert a
ATTEINDRE les deux exemplaires, il ne dit pas lequel est lequel. D'ou `armer_actif` qui ESSAIE
et garde celui dont l'effet se voit -- la barre d'info bascule de `Unit_Info_Bar_HUD` vers
`Ability_Info_Bar_HUD`.

⚠ ARMER NE CHANGE PAS L'ETAT DU FSM : il reste `UnitNormallySelected` avant comme apres. La
selection d'ability est un fait de HUD, et c'est le `up(cible)` qui declenche. Chercher un
`AbilitySelectedState` est une impasse -- il n'existe pas.

⚠ HORS DE PORTEE, LE `up` PART EN DEPLACEMENT, ET IL REND `ok: true`. Au tour 1 les ennemis
etaient a distance 5 pour un mouvement de 3 : `up(ennemi)` faisait
`UnitNormallySelected -> MovementSuggestionState`, ce qui se lit << le cast a rate >> alors que
c'est << la cible n'est pas atteignable >>. `designer` distingue les deux et le DIT.

⚠ LA DESTINATION D'APPROCHE NE SE DEVINE PAS : `decisionView.attackPlans[].evals[].ranked`
publie les positions DEPUIS LESQUELLES une cible est attaquable. `positions_de_tir` les lit.

⚠ L'ID DE TUILE NE SE CALCULE PAS. La formule `12 + col*9 + row` vaut pour un plateau 7x9 ;
`C1_01` fait 5x7. Seul `boardGraph` donne le couple `(col,row) -> tileEntityId`.

⚠ LE `down` PREND LA TUILE, LE `up` PREND L'UNITE (case-596, lu aux deux decompiles).

⚠ UN ETAT HERITE FAIT RATER LA SELECTION EN SILENCE. Mesure : depuis
`MovementSuggestionState`, la sequence `down`/`up` laisse le FSM a `NormalState` et la barre
d'abilities a ZERO bouton -- et rien ne le signale. D'ou le `reset` en tete de chaque verbe.

ASCII strict dans toute sortie console (cp1252).
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field

from gamenav import vue as _vue

#: Fragment de chemin des boutons de la barre d'abilities.
BARRE = "Ability_Selection_HUD"

#: Temoin d'un actif ARME : la barre d'info montre l'ability et non l'unite.
TEMOIN_ARME = "Ability_Info_Bar_HUD"

#: L'etat de repos du FSM, celui d'ou toute chaine repart.
REPOS = "NormalState"

#: L'etat ou une unite est selectionnee et pilotable.
SELECTIONNEE = "UnitNormallySelected"

#: L'etat ou le FSM a lu le tap comme un DEPLACEMENT (cible hors de portee).
SUGGESTION = "MovementSuggestionState"

#: Le tap a ete lu comme une INSPECTION -- il a donc porte, mais pas comme un cast.
INSPECTION = ("InspectEnemyState", "InspectTileState")

#: Le tap a RE-SELECTIONNE l'unite visee au lieu de la cibler (mesure : `up` sur un ALLIE).
RESELECTION = "FingerDownOnUnitForFirstTime"


@dataclass
class Cran:
    """Un cran de la chaine et sa PREUVE. `porte is None` = PAS MESURE."""
    quoi: str
    porte: bool | None = None
    avant: str | None = None
    apres: str | None = None
    refus: str | None = None
    detail: dict = field(default_factory=dict)

    def __bool__(self) -> bool:                                       # pragma: no cover
        return bool(self.porte)


# ------------------------------------------------------------------ lectures

def etat(hote) -> str | None:
    """L'etat courant du FSM, ou None = PAS MESURE."""
    try:
        return (hote.rpc("fsmStatus", [], 20000) or {}).get("etatCourant")
    except Exception:                                                 # noqa: BLE001
        return None


def pile(hote) -> list | None:
    """Les frames d'`Apply` en vol. Une frame ORPHELINE = un `Apply` qui a leve.

    `Interceptor.attach` n'appelle pas `onLeave` quand la fonction jette : c'est le seul
    detecteur d'exception qu'on ait cote bataille (#596-r1). None = PAS MESURE.
    """
    try:
        return (hote.rpc("battleEvents", [{}], 20000) or {}).get("pile")
    except Exception:                                                 # noqa: BLE001
        return None


def tuiles(hote) -> dict | None:
    """{(col,row): tileEntityId} depuis `boardGraph`. None = PAS MESURE.

    Le board est STATIQUE pour une bataille donnee ; l'appelant peut cacher le resultat.
    """
    try:
        r = hote.rpc("boardGraph", [{}], 30000) or {}
    except Exception:                                                 # noqa: BLE001
        return None
    ts = r.get("tiles")
    if not ts:
        return None
    return {(t.get("col"), t.get("row")): t.get("id") for t in ts}


def unites(hote, vivantes: bool = True) -> list | None:
    """Les unites du plateau. None = PAS MESURE.

    ⚠ `observeBattle` GARDE LES MORTS. Le defaut filtre donc sur `isDead` -- sans quoi une
    tuile occupee par un cadavre passe pour libre, et une cible deja tuee entre dans un
    balayage. Ce module l'a fait : sa premiere version annoncait << les unites vivantes >>
    et ne filtrait rien. `vivantes=False` rend le releve BRUT quand on veut compter les morts.

    ⚠ `visualId` LAISSE TOMBER le suffixe des mannequins de tutoriel : la BC dit
    `necroNpc1TutWarriorFTUEtest`, `observeBattle` rend `necroNpc1Warrior`. Pour savoir a QUOI
    on se confronte, lire `inspectBattleConfig`, pas ceci.
    """
    try:
        r = hote.rpc("observeBattle", [{}], 30000) or {}
    except Exception:                                                 # noqa: BLE001
        return None
    us = r.get("units")
    if us is None or not vivantes:
        return us
    return [u for u in us if not u.get("isDead")]


def unite(hote, visual_id: str) -> dict | None:
    """L'unite portant ce `visualId`, ou None (absente OU pas mesuree -- l'appelant tranche
    en interrogeant `unites` lui-meme s'il a besoin de distinguer)."""
    us = unites(hote)
    if us is None:
        return None
    for u in us:
        if str(u.get("visualId")) == visual_id:
            return u
    return None


def positions_de_tir(hote, u: dict) -> list:
    """[(col, row, targetId)] -- les positions DEPUIS LESQUELLES `u` peut attaquer.

    Lues dans `decisionView.attackPlans`, apparie par la position COURANTE de l'unite. Liste
    vide = le jeu n'en propose aucune (rien a portee, meme apres deplacement).
    """
    try:
        d = hote.rpc("decisionView", [{}], 30000) or {}
    except Exception:                                                 # noqa: BLE001
        return []
    ici = (u.get("col"), u.get("row"))
    out = []
    for p in (d.get("attackPlans") or []):
        ct = p.get("currentTile") or {}
        if (ct.get("col"), ct.get("row")) != ici:
            continue
        for ev in (p.get("evals") or []):
            for rk in (ev.get("ranked") or []):
                out.append((rk.get("col"), rk.get("row"), ev.get("targetId")))
    return out


def _photo(hote) -> dict:
    """L'etat de jeu qui sert de PREUVE : pv, effets, file d'activation."""
    try:
        d = hote.rpc("decisionView", [{}], 25000) or {}
    except Exception:                                                 # noqa: BLE001
        d = {}
    us = unites(hote) or []
    return {
        "toActivate": d.get("toActivate"),
        "hp": {u.get("squadId"): u.get("hp") for u in us},
        "eff": {u.get("id"): sorted(e.get("name") for e in (u.get("effects") or []))
                for u in (d.get("units") or [])},
    }


def _diff(a: dict, b: dict) -> list:
    out = []
    if a["toActivate"] != b["toActivate"]:
        out.append("toActivate %s -> %s" % (a["toActivate"], b["toActivate"]))
    for k in sorted(set(a["hp"]) | set(b["hp"]), key=lambda x: (x is None, x)):
        if a["hp"].get(k) != b["hp"].get(k):
            out.append("hp[%s] %s -> %s" % (k, a["hp"].get(k), b["hp"].get(k)))
    for k in sorted(set(a["eff"]) | set(b["eff"]), key=lambda x: (x is None, x)):
        av, ap = set(a["eff"].get(k) or []), set(b["eff"].get(k) or [])
        if ap - av:
            out.append("effets[%s] + %s" % (k, sorted(ap - av)))
        if av - ap:
            out.append("effets[%s] - %s" % (k, sorted(av - ap)))
    return out


# ------------------------------------------------------------------ garde

def pret(hote) -> str | None:
    """Motif de REFUS si le combat n'est pas pilotable, sinon None."""
    calme = hote.calme()
    if calme:
        return calme
    try:
        st = hote.rpc("fsmStatus", [], 20000) or {}
    except Exception as ex:                                           # noqa: BLE001
        return "fsmStatus NON MESURE (%s)" % str(ex)[:80]
    if not st.get("pret"):
        return st.get("cause") or "FSM non utilisable, sans cause nommee"
    return None


# ------------------------------------------------------------------ les crans

def tuile_libre(hote, carte: dict | None = None) -> int | None:
    """L'id d'une tuile SANS unite dessus, ou None = PAS MESURE / plateau plein.

    Sert au tap sur le sol, qui est la vraie echappatoire du FSM (cf. `reset`).
    """
    carte = carte if carte is not None else tuiles(hote)
    us = unites(hote)
    if carte is None or us is None:
        return None
    prises = {(u.get("col"), u.get("row")) for u in us}
    for pos in sorted(carte):
        if pos not in prises:
            return carte[pos]
    return None


def reset(hote, essais: int = 4, attente: float = 1.0,
          carte: dict | None = None) -> Cran:
    """Ramene le FSM a `NormalState`. A JOUER AVANT CHAQUE CHAINE -- cf. l'en-tete.

    ⚠ `back` NE SUFFIT PAS, ET IL ECHOUE EN SILENCE. Mesure du 2026-08-09 : depuis
    `InspectEnemyState`, quatre `back` d'affilee laissent l'etat INCHANGE. Ce qui sort, c'est
    le tap sur le SOL -- `up` sur une tuile sans unite :

        InspectEnemyState  --back-->        InspectEnemyState   (rien)
        UnitNormallySelected --up(libre)--> NormalState         (1/1)

    On alterne donc les deux voies plutot que de repeter celle qui ne mord pas.
    """
    c = Cran(quoi="reset", avant=etat(hote))
    libre = None
    for i in range(essais):
        e = etat(hote)
        if e == REPOS:
            c.porte, c.apres = True, e
            return c
        if e is None:
            c.refus = "etat du FSM NON MESURE -- on ne pilote pas a l'aveugle"
            return c
        if i % 2 == 0:
            hote.rpc("fsmInput", [{"kind": "back"}], 20000)
        else:
            if libre is None:
                libre = tuile_libre(hote, carte)
            if libre is None:
                c.refus = ("aucune tuile libre mesuree -- la seule echappatoire connue "
                           "(tap sur le sol) est indisponible")
                c.apres = etat(hote)
                return c
            hote.rpc("fsmInput", [{"kind": "up", "entityId": libre}], 20000)
        time.sleep(attente)
    c.apres = etat(hote)
    c.porte = c.apres == REPOS
    if not c.porte:
        c.refus = ("le FSM reste a %r apres %d tentatives (back ET tap sur le sol)"
                   % (c.apres, essais))
    return c


def selectionner(hote, u: dict, carte: dict | None = None,
                 attente: float = 1.5) -> Cran:
    """Selectionne l'unite : `down(TUILE)` puis `up(UNITE)`.

    `carte` = le dict rendu par `tuiles`, a passer si l'appelant le cache.
    """
    c = Cran(quoi="selectionner", avant=etat(hote))
    carte = carte if carte is not None else tuiles(hote)
    if carte is None:
        c.refus = "plateau NON MESURE (`boardGraph`) -- l'id de tuile ne se calcule pas"
        return c
    pos = (u.get("col"), u.get("row"))
    tid = carte.get(pos)
    if tid is None:
        c.refus = "aucune tuile a %r dans le plateau" % (pos,)
        return c

    hote.rpc("fsmInput", [{"kind": "down", "entityId": tid}], 20000)
    time.sleep(0.5)
    hote.rpc("fsmInput", [{"kind": "up", "entityId": u.get("squadId")}], 20000)
    time.sleep(attente)

    c.apres = etat(hote)
    c.porte = c.apres == SELECTIONNEE
    c.detail = {"tuile": tid, "unite": u.get("squadId"), "pos": pos}
    if not c.porte:
        c.refus = ("le FSM est a %r et non %r -- un etat HERITE fait rater la selection "
                   "en silence, jouer `reset` d'abord" % (c.apres, SELECTIONNEE))
    return c


def deplacer(hote, u: dict, dest: tuple, carte: dict | None = None,
             attente: float = 1.0) -> Cran:
    """Deplace l'unite : `down(tuileUnite)` `held(tuileDest)` `up(tuileDest)`.

    Preuve par la POSITION relue, jamais par le retour des trois appels.
    """
    c = Cran(quoi="deplacer", avant=etat(hote))
    carte = carte if carte is not None else tuiles(hote)
    if carte is None:
        c.refus = "plateau NON MESURE (`boardGraph`)"
        return c
    depart = (u.get("col"), u.get("row"))
    t_dep, t_dest = carte.get(depart), carte.get(tuple(dest))
    if t_dep is None or t_dest is None:
        c.refus = "tuile absente du plateau (depart=%r dest=%r)" % (depart, tuple(dest))
        return c

    for kind, eid in (("down", t_dep), ("held", t_dest), ("up", t_dest)):
        hote.rpc("fsmInput", [{"kind": kind, "entityId": eid}], 20000)
        time.sleep(attente)
    time.sleep(attente)

    apres_u = unite(hote, str(u.get("visualId")))
    arrivee = (apres_u.get("col"), apres_u.get("row")) if apres_u else None
    c.apres = etat(hote)
    c.detail = {"depart": depart, "demande": tuple(dest), "arrivee": arrivee}
    if arrivee is None:
        c.refus = "position d'arrivee NON MESUREE -- deplacement NON PROUVE"
        return c
    c.porte = arrivee == tuple(dest)
    if not c.porte:
        c.refus = ("l'unite est a %r et non %r -- destination hors de portee, "
                   "occupee, ou bloquee" % (arrivee, tuple(dest)))
    return c


def _barre_montre_ability(hote):
    """(True/False/None, vue) -- un actif est-il ARME ? None = ecran non mesure."""
    v = _vue.regarder(hote, tout=True)
    if v is None:
        return None, None
    return any(TEMOIN_ARME in b.get("path", "") for b in v.boutons), v


def armer_actif(hote, attente: float = 1.5) -> Cran:
    """Arme l'actif en ESSAYANT chaque bouton de la barre et en jugeant par l'EFFET.

    ⚠ On n'appelle PAS le rang par son numero : il ne designe pas une ability (cf. l'en-tete).
    On s'arrete au premier rang qui fait basculer la barre d'info.
    """
    c = Cran(quoi="armer_actif", avant=etat(hote))
    deja, v = _barre_montre_ability(hote)
    if deja is None:
        c.refus = "ecran NON MESURE"
        return c
    if deja:
        c.porte, c.apres = True, etat(hote)
        c.detail = {"rang": None, "note": "un actif etait DEJA arme"}
        return c

    cands = [b for b in v.boutons if BARRE in b.get("path", "")]
    c.detail["boutons"] = len(cands)
    if not cands:
        c.refus = ("aucun bouton d'ability a l'ecran -- l'unite n'est pas selectionnee, "
                   "ou `uiList` ne les voit pas (il n'enumere que des `Button` ACTIFS)")
        return c

    for rang in range(len(cands)):
        hote.rpc("uiClick", [{"path": cands[rang].get("path"), "index": rang}], 20000)
        time.sleep(attente)
        arme, v = _barre_montre_ability(hote)
        if arme:
            c.porte, c.apres = True, etat(hote)
            c.detail.update({"rang": rang, "ptr": cands[rang].get("ptr")})
            return c
    c.apres = etat(hote)
    c.porte = False
    c.refus = ("aucun des %d boutons n'arme d'actif -- l'unite n'en a pas de disponible "
               "a ce cran (charge, deja joue, ou masque par le noeud)" % len(cands))
    return c


def designer(hote, cible_id: int, attente: float = 3.0) -> Cran:
    """Designe la cible : `up(CIBLE)`. Le verdict se prend sur ce qui a CHANGE.

    Quatre issues, et elles se DISTINGUENT -- c'est tout l'interet :
      - un effet de jeu (pv, effets, `toActivate`)          -> le cast est parti ;
      - `MovementSuggestionState`                           -> cible HORS DE PORTEE ;
      - `InspectEnemyState` / `InspectTileState`            -> le tap A PORTE, mais lu comme
        une INSPECTION : la cible n'est pas valide pour l'ability armee ;
      - rien du tout                                        -> le tap n'a pas ete lu.

    ⚠ La troisieme etait rangee dans la quatrieme, et c'est faux : ecrire << le tap n'a pas
    ete lu >> sur une inspection envoie chercher un probleme d'entree la ou il y a un probleme
    de CIBLE. Trouve par la contre-epreuve du module lui-meme, sur une cible lointaine.
    """
    c = Cran(quoi="designer", avant=etat(hote))
    av = _photo(hote)
    hote.rpc("fsmInput", [{"kind": "up", "entityId": int(cible_id)}], 20000)
    time.sleep(attente)
    c.apres = etat(hote)
    d = _diff(av, _photo(hote))
    c.detail = {"cible": int(cible_id), "changements": d, "pile": pile(hote)}
    if d:
        c.porte = True
        return c
    c.porte = False
    if c.apres == SUGGESTION:
        c.refus = ("cible HORS DE PORTEE -- le FSM a lu le tap comme un deplacement "
                   "(%r). Approcher d'abord : `positions_de_tir` dit d'ou tirer." % SUGGESTION)
    elif c.apres in INSPECTION:
        c.refus = ("le tap A PORTE mais a ete lu comme une INSPECTION (%r) -- la cible n'est "
                   "pas valide pour l'ability armee (hors portee, mauvais camp, ou masque "
                   "de ciblage). Ce n'est PAS un probleme d'entree." % c.apres)
    elif c.apres == RESELECTION:
        c.refus = ("le tap a RE-SELECTIONNE la cible (%r) au lieu de la viser -- mesure sur "
                   "un ALLIE. L'ability armee ne se designe pas par ce geste ; a instruire "
                   "(self-cast, cible TUILE, ou confirmation en deux temps)." % c.apres)
    else:
        c.refus = "aucun effet de jeu et etat %r -- le tap n'a pas ete lu" % c.apres
    return c


def caster(hote, visual_id: str, cible_id: int, carte: dict | None = None) -> list:
    """La chaine complete : reset -> selection -> armement -> designation.

    Rend la liste des `Cran` joues, ARRETEE au premier qui ne porte pas. Ne masque rien :
    l'appelant lit le `refus` du dernier.
    """
    motif = pret(hote)
    if motif:
        return [Cran(quoi="pret", refus=motif)]
    carte = carte if carte is not None else tuiles(hote)
    out = [reset(hote)]
    if not out[-1]:
        return out
    u = unite(hote, visual_id)
    if u is None:
        out.append(Cran(quoi="selectionner", refus="unite %r absente du plateau" % visual_id))
        return out
    for cran in (selectionner(hote, u, carte), armer_actif(hote),
                 designer(hote, cible_id)):
        out.append(cran)
        if not cran:
            break
    return out
