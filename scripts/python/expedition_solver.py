"""Solveur d'affectation pour les OPERATIONS (Expeditions) -- 100 % hors ligne.

CE QUE LE JEU DEMANDE, MOT POUR MOT (infobulles lues en jeu le 2026-08-10) :

    "Completing an Operation always grants its base rewards. In order to receive
     the Bonus Rewards, all Bonus Objectives must be fulfilled."

    "Each Bonus Objective must be fulfilled by ONE of the dispatched characters.
     A dispatched character can fulfil MULTIPLE Bonus Objectives."

=> ce n'est pas un choix de puissance, c'est une COUVERTURE D'ENSEMBLE : il faut
choisir au plus `participants` personnages dont l'union des proprietes couvre TOUS
les objectifs bonus. Un personnage qui coche trois objectifs libere deux places.
C'est exactement un set cover, et il se resout exactement a cette echelle.

POURQUOI HORS LIGNE. Tout ce qu'il faut est deja dans le gameconfig, via
`unit_map.kit()` : `faction`, `alliance`, `traits`, `ranged_hits`. Aucun runner,
aucune session Frida, aucun appel serveur. Le solveur ne joue rien et n'envoie
rien -- il repond a << qui envoyer >>, l'envoi reste un geste humain.

LES TROIS FORMES D'OBJECTIF MESUREES (operation "Stand Against All Odds",
plateau Mythic I, 10 h, Imperial) :

    Melee                    "a character WITHOUT a normal ranged attack"
    Adeptus Custodes Faction "a character of the <faction> faction"
    Healer Trait             "a character with the Trait <trait>"
    Mk X Gravis Trait        idem

Le vocabulaire est donc : profil d'attaque normale, faction, trait. Toute forme
non reconnue est REFUSEE avec la liste des identifiants connus -- jamais devinee.

ATTENTION AUX IDENTIFIANTS. L'UI affiche des LIBELLES ("Adeptus Custodes",
"Mk X Gravis") la ou le gameconfig porte des IDS (`Custodes`, `MkXGravis`). La
resolution est faite par normalisation puis appariement, et une correspondance
AMBIGUE est refusee en listant les candidats. Un id force au hasard serait pire
qu'une erreur : il rendrait une reponse fausse d'apparence juste.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass
from itertools import combinations

import unit_map

# ---------------------------------------------------------------------------
# Vocabulaire des objectifs
# ---------------------------------------------------------------------------

#: Formes acceptees. `melee` mirroir de "without a normal ranged attack".
FORMES_SIMPLES = ("melee", "ranged")
PREFIXES = ("faction", "trait", "alliance")

#: Plafond du nombre de solutions minimales enumerees pour UNE operation. Il est
#: publie dans la sortie des qu'il mord : un plafond silencieux se lirait comme
#: << il n'y en a pas d'autres >>.
PLAFOND_SOLUTIONS = 200

#: Plafond du nombre d'ensembles candidats retenus par operation en mode plateau.
PLAFOND_ENSEMBLES_PAR_OP = 120


def _norm(s: str) -> str:
    """Normalise pour appariement : minuscules, sans rien d'autre qu'alphanumerique."""
    return re.sub(r"[^a-z0-9]", "", (s or "").lower())


@dataclass(frozen=True)
class Objectif:
    brut: str
    kind: str            # "melee" | "ranged" | "faction" | "trait" | "alliance"
    valeur: str | None   # identifiant gameconfig RESOLU, ou None pour melee/ranged
    libelle: str


class ObjectifIrresoluble(ValueError):
    """Leve -- jamais rendu comme un resultat. Un objectif qu'on ne sait pas lire
    doit ARRETER le calcul : le laisser passer produirait une couverture qui
    ignore silencieusement une contrainte, donc un plan FAUX."""


def _apparier(brut: str, connus: set[str], quoi: str) -> str:
    """Apparie un libelle a un identifiant connu. Exact d'abord, puis suffixe/inclusion.
    Refuse l'ambiguite plutot que de choisir."""
    n = _norm(brut)
    exact = [c for c in connus if _norm(c) == n]
    if len(exact) == 1:
        return exact[0]
    approx = [c for c in connus if n.endswith(_norm(c)) or _norm(c).endswith(n) or _norm(c) == n]
    approx = sorted(set(approx))
    if len(approx) == 1:
        return approx[0]
    if len(approx) > 1:
        raise ObjectifIrresoluble(
            "%s AMBIGU : '%s' correspond a %d identifiants -- %s. "
            "Donne l'identifiant exact." % (quoi, brut, len(approx), ", ".join(approx)))
    raise ObjectifIrresoluble(
        "%s INCONNU : '%s'. Identifiants connus : %s"
        % (quoi, brut, ", ".join(sorted(connus))))


def resoudre_objectif(txt: str, factions: set[str], traits: set[str],
                      alliances: set[str]) -> Objectif:
    t = (txt or "").strip()
    if not t:
        raise ObjectifIrresoluble("objectif VIDE")
    bas = t.lower()
    if bas in FORMES_SIMPLES:
        libelle = ("Melee (sans attaque a distance normale)" if bas == "melee"
                   else "Ranged (avec attaque a distance normale)")
        return Objectif(brut=t, kind=bas, valeur=None, libelle=libelle)
    if ":" not in t:
        raise ObjectifIrresoluble(
            "objectif NON RECONNU : '%s'. Formes acceptees : %s, ou %s"
            % (t, "/".join(FORMES_SIMPLES), "/".join(p + ":<id>" for p in PREFIXES)))
    pref, _, reste = t.partition(":")
    pref = pref.strip().lower()
    reste = reste.strip()
    if pref == "faction":
        vid = _apparier(reste, factions, "FACTION")
        return Objectif(t, "faction", vid, "Faction %s" % vid)
    if pref == "trait":
        vid = _apparier(reste, traits, "TRAIT")
        return Objectif(t, "trait", vid, "Trait %s" % vid)
    if pref == "alliance":
        vid = _apparier(reste, alliances, "ALLIANCE")
        return Objectif(t, "alliance", vid, "Alliance %s" % vid)
    raise ObjectifIrresoluble(
        "prefixe INCONNU : '%s'. Attendu : %s" % (pref, "/".join(PREFIXES)))


def satisfait(k: dict, o: Objectif) -> bool:
    """Le kit `k` remplit-il l'objectif `o` ?

    `melee` mirroir de la formulation native "without a normal ranged attack" :
    on lit `ranged_hits`, derive des armes de portee > 0 par `unit_map._weapons`.
    """
    if o.kind == "melee":
        return not k.get("ranged_hits")
    if o.kind == "ranged":
        return bool(k.get("ranged_hits"))
    if o.kind == "faction":
        return k.get("faction") == o.valeur
    if o.kind == "alliance":
        return k.get("alliance") == o.valeur
    if o.kind == "trait":
        return o.valeur in (k.get("traits") or [])
    raise ObjectifIrresoluble("kind non gere : %s" % o.kind)


# ---------------------------------------------------------------------------
# Couverture exacte
# ---------------------------------------------------------------------------

def masque(k: dict, objs: list[Objectif]) -> int:
    m = 0
    for i, o in enumerate(objs):
        if satisfait(k, o):
            m |= 1 << i
    return m


def _enumerer(masques: list[int], plein: int, limite: int,
              plafond: int) -> tuple[list[tuple[int, ...]], bool]:
    """Enumere les combinaisons de masques de taille <= `limite` couvrant `plein`.

    Technique d'exact cover : a chaque etage on prend le PLUS BAS objectif encore
    non couvert et on n'essaie que les masques qui le couvrent. Ca elimine d'office
    les permutations et borne la profondeur a `limite`.

    Rend (solutions, plafond_atteint).
    """
    sols: list[tuple[int, ...]] = []
    vues: set[tuple[int, ...]] = set()
    deborde = [False]

    def rec(restant: int, courant: list[int]) -> None:
        if deborde[0]:
            return
        if restant == plein:
            cle = tuple(sorted(courant))
            if cle not in vues:
                vues.add(cle)
                sols.append(cle)
                if len(sols) >= plafond:
                    deborde[0] = True
            return
        if len(courant) >= limite:
            return
        libres = (~restant) & plein
        bit = libres & (-libres)
        for mk in masques:
            if mk & bit:
                courant.append(mk)
                rec(restant | mk, courant)
                courant.pop()
                if deborde[0]:
                    return

    rec(0, [])
    return sols, deborde[0]


def resoudre_operation(candidats: list[dict], objs: list[Objectif],
                       participants: int,
                       plafond: int = PLAFOND_SOLUTIONS) -> dict:
    """Resout UNE operation. Rend un dict AUDITABLE : par objectif, combien de
    candidats le remplissent (un 0 est ainsi VISIBLE et nomme), la taille minimale
    trouvee, et les solutions en identifiants d'unites."""
    plein = (1 << len(objs)) - 1
    par_masque: dict[int, list[dict]] = {}
    for k in candidats:
        m = masque(k, objs)
        if m:
            par_masque.setdefault(m, []).append(k)

    couverture = [
        {"objectif": o.libelle,
         "candidats": sum(1 for k in candidats if satisfait(k, o))}
        for o in objs
    ]
    impossibles = [c["objectif"] for c in couverture if c["candidats"] == 0]

    base = {
        "objectifs": [o.libelle for o in objs],
        "participants": participants,
        "candidats": len(candidats),
        "couverture": couverture,
        "impossibles": impossibles,
        "plafond_atteint": False,
    }
    if impossibles:
        base.update({"ok": False, "raison": "objectif(s) sans AUCUN candidat",
                     "taille": None, "solutions": []})
        return base
    if not objs:
        base.update({"ok": True, "taille": 0, "solutions": [], "raison": None})
        return base

    masques = sorted(par_masque)
    borne = min(participants, len(objs))
    for taille in range(1, borne + 1):
        sols, deborde = _enumerer(masques, plein, taille, plafond)
        sols = [s for s in sols if len(s) == taille]
        if sols:
            rendu = []
            for combo in sols:
                rendu.append([
                    {"masque": mk,
                     "objectifs": [objs[i].libelle for i in range(len(objs))
                                   if mk & (1 << i)],
                     "unites": [{"id": u["id"], "name": u.get("name"),
                                 "faction": u.get("faction")}
                                for u in par_masque[mk]]}
                    for mk in combo
                ])
            base.update({"ok": True, "taille": taille, "solutions": rendu,
                         "raison": None, "plafond_atteint": deborde})
            return base

    base.update({"ok": False, "taille": None, "solutions": [],
                 "raison": "couverture IMPOSSIBLE avec %d participant(s) "
                           "(il en faudrait davantage)" % participants})
    return base


# ---------------------------------------------------------------------------
# Plateau : plusieurs operations, unites DISJOINTES
# ---------------------------------------------------------------------------

def _ensembles_par_op(candidats: list[dict], objs: list[Objectif], participants: int,
                      plafond: int) -> list[frozenset[str]]:
    """Ensembles d'unites (ids) realisant une couverture MINIMALE de l'operation."""
    r = resoudre_operation(candidats, objs, participants, plafond=plafond)
    if not r["ok"]:
        return []
    out: list[frozenset[str]] = []
    vus: set[frozenset[str]] = set()
    for combo in r["solutions"]:
        # produit cartesien borne : un representant par groupe de masque
        listes = [[u["id"] for u in grp["unites"]] for grp in combo]
        for choix in _produit_borne(listes, plafond):
            fs = frozenset(choix)
            if len(fs) == len(choix) and fs not in vus:
                vus.add(fs)
                out.append(fs)
                if len(out) >= plafond:
                    return out
    return out


def _produit_borne(listes: list[list[str]], plafond: int):
    """Produit cartesien tronque a `plafond` -- la troncature est assumee et le
    plateau le signale ; on ne pretend pas enumerer tout l'espace."""
    n = 0
    idx = [0] * len(listes)
    if not listes:
        return
    while True:
        yield [listes[i][idx[i]] for i in range(len(listes))]
        n += 1
        if n >= plafond:
            return
        p = len(listes) - 1
        while p >= 0:
            idx[p] += 1
            if idx[p] < len(listes[p]):
                break
            idx[p] = 0
            p -= 1
        if p < 0:
            return


def resoudre_plateau(ops: list[dict], kits: dict[str, dict], roster: list[str],
                     plafond_ens: int = PLAFOND_ENSEMBLES_PAR_OP) -> dict:
    """Affecte des unites DISJOINTES a un plateau d'operations.

    Pourquoi la disjonction est le vrai probleme : une unite envoyee est
    IMMOBILISEE pour la duree (`ExpeditionDispatchUnitWidget.State.Dispatched`).
    Optimiser chaque operation isolement propose donc des plans infaisables --
    la meme unite pivot apparait dans trois operations a la fois.

    Objectif : MAXIMISER le nombre d'operations dont le bonus est debloque ;
    a egalite, MINIMISER le nombre d'unites mobilisees.
    """
    prepares = []
    for op in ops:
        pool = [kits[u] for u in roster if u in kits]
        alli = op.get("grandAlliance")
        if alli:
            pool = [k for k in pool if k.get("alliance") == alli]
        ens = _ensembles_par_op(pool, op["_objs"], int(op.get("participants") or 0),
                                plafond_ens)
        prepares.append({"op": op, "ensembles": ens, "pool": len(pool)})

    meilleur = {"couvertes": -1, "unites": None, "plan": None}

    def rec(i: int, utilisees: frozenset[str], plan: list[dict]) -> None:
        restantes = len(prepares) - i
        # elagage : meme en couvrant tout le reste, peut-on battre le meilleur ?
        couvertes = sum(1 for p in plan if p["ensemble"] is not None)
        if couvertes + restantes < meilleur["couvertes"]:
            return
        if i == len(prepares):
            if (couvertes > meilleur["couvertes"]
                    or (couvertes == meilleur["couvertes"]
                        and len(utilisees) < (meilleur["unites"] or 10 ** 9))):
                meilleur["couvertes"] = couvertes
                meilleur["unites"] = len(utilisees)
                meilleur["plan"] = [dict(p) for p in plan]
            return
        p = prepares[i]
        for ens in p["ensembles"]:
            if utilisees & ens:
                continue
            plan.append({"op": p["op"], "ensemble": sorted(ens)})
            rec(i + 1, utilisees | ens, plan)
            plan.pop()
        # branche << on renonce a cette operation >>
        plan.append({"op": p["op"], "ensemble": None})
        rec(i + 1, utilisees, plan)
        plan.pop()

    rec(0, frozenset(), [])
    return {
        "operations": len(prepares),
        "couvertes": max(meilleur["couvertes"], 0),
        "unites_mobilisees": meilleur["unites"] or 0,
        "plan": meilleur["plan"] or [],
        "ensembles_par_op": [len(p["ensembles"]) for p in prepares],
        "plafond_ensembles": plafond_ens,
    }


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def _charger_kits() -> dict[str, dict]:
    return {k["id"]: k for k in unit_map.all_kits() if k.get("kind") == "lineup"}


def _vocabulaire(kits: dict[str, dict]):
    factions = {k["faction"] for k in kits.values() if k.get("faction")}
    alliances = {k["alliance"] for k in kits.values() if k.get("alliance")}
    traits = {t for k in kits.values() for t in (k.get("traits") or [])}
    return factions, traits, alliances


def _roster(arg: str | None, kits: dict[str, dict]) -> tuple[list[str], bool]:
    """Rend (ids, complet_suppose). `complet_suppose` = on n'a PAS de roster reel."""
    if not arg:
        return sorted(kits), True
    ids: list[str] = []
    try:
        with open(arg, "r", encoding="utf-8") as fh:
            brut = fh.read()
    except OSError:
        brut = arg
    # Les commentaires se coupent PAR LIGNE, pas par jeton. Un filtre par jeton
    # (`not tok.startswith("#")`) ne retire que le `#` lui-meme et laisse entrer tous
    # les MOTS du commentaire : mesure faite, un en-tete de deux lignes injectait
    # 18 faux ids. Benin tant qu'ils sont inconnus et signales -- mais un commentaire
    # contenant un vrai identifiant l'ajouterait au roster SANS que rien ne le dise.
    for ligne in brut.splitlines():
        ligne = ligne.split("#", 1)[0]
        for tok in re.split(r"[\s,;]+", ligne):
            tok = tok.strip()
            if tok:
                ids.append(tok)
    inconnus = [i for i in ids if i not in kits]
    if inconnus:
        print("ATTENTION -- %d id(s) de roster inconnus, IGNORES : %s"
              % (len(inconnus), ", ".join(inconnus[:10])))
    return [i for i in ids if i in kits], False


def _afficher_operation(r: dict) -> None:
    print("Objectifs        : %s" % " | ".join(r["objectifs"]))
    print("Participants max : %d" % r["participants"])
    print("Candidats        : %d" % r["candidats"])
    print("")
    print("Couverture par objectif :")
    for c in r["couverture"]:
        marque = "  ZERO CANDIDAT" if c["candidats"] == 0 else ""
        print("   %-46s %4d%s" % (c["objectif"], c["candidats"], marque))
    print("")
    if not r["ok"]:
        print("RESULTAT : IMPOSSIBLE -- %s" % r["raison"])
        for o in r["impossibles"]:
            print("   objectif sans candidat : %s" % o)
        return
    print("RESULTAT : couverture complete avec %d unite(s)" % r["taille"])
    if r.get("plafond_atteint"):
        print("   (plafond de %d solutions atteint -- d'autres existent, NON listees)"
              % PLAFOND_SOLUTIONS)
    print("")
    for n, combo in enumerate(r["solutions"][:10], 1):
        print("  Solution %d :" % n)
        for grp in combo:
            noms = ", ".join("%s" % u["id"] for u in grp["unites"][:6])
            reste = len(grp["unites"]) - 6
            if reste > 0:
                noms += " (+%d autres)" % reste
            print("     couvre [%s]" % " + ".join(grp["objectifs"]))
            print("        -> %s" % noms)
    if len(r["solutions"]) > 10:
        print("  ... %d autres solutions de meme taille" % (len(r["solutions"]) - 10))


def cmd_solve(a) -> int:
    kits = _charger_kits()
    factions, traits, alliances = _vocabulaire(kits)
    try:
        objs = [resoudre_objectif(t, factions, traits, alliances) for t in a.objectif]
    except ObjectifIrresoluble as e:
        print("REFUS : %s" % e)
        return 2
    roster, suppose = _roster(a.roster, kits)
    pool = [kits[u] for u in roster]
    if a.alliance:
        try:
            alli = _apparier(a.alliance, alliances, "ALLIANCE")
        except ObjectifIrresoluble as e:
            print("REFUS : %s" % e)
            return 2
        pool = [k for k in pool if k.get("alliance") == alli]
        print("Alliance imposee : %s" % alli)
    if suppose:
        print("ATTENTION -- aucun roster fourni : on suppose que TOUS les %d "
              "personnages du gameconfig sont possedes." % len(kits))
        print("             Utilise --roster pour un plan REELLEMENT jouable.")
    print("")
    r = resoudre_operation(pool, objs, a.participants)
    _afficher_operation(r)
    if a.json:
        print("")
        print(json.dumps(r, ensure_ascii=True, indent=2))
    return 0 if r["ok"] else 1


def cmd_board(a) -> int:
    kits = _charger_kits()
    factions, traits, alliances = _vocabulaire(kits)
    with open(a.fichier, "r", encoding="utf-8") as fh:
        ops = json.load(fh)
    if isinstance(ops, dict):
        ops = ops.get("board") or ops.get("operations") or []
    try:
        for op in ops:
            op["_objs"] = [resoudre_objectif(t, factions, traits, alliances)
                           for t in (op.get("bonusObjectives") or [])]
    except ObjectifIrresoluble as e:
        print("REFUS : %s" % e)
        return 2
    roster, suppose = _roster(a.roster, kits)
    if suppose:
        print("ATTENTION -- aucun roster fourni : on suppose TOUT possede (%d)." % len(kits))
        print("")
    r = resoudre_plateau(ops, kits, roster)
    print("Operations   : %d" % r["operations"])
    print("Bonus obtenu : %d / %d" % (r["couvertes"], r["operations"]))
    print("Unites mobilisees : %d" % r["unites_mobilisees"])
    print("Ensembles candidats retenus par operation : %s (plafond %d)"
          % (r["ensembles_par_op"], r["plafond_ensembles"]))
    print("")
    for p in r["plan"]:
        op = p["op"]
        nom = op.get("expeditionId") or op.get("id") or "?"
        if p["ensemble"] is None:
            print("  [BONUS NON OBTENU] %s" % nom)
        else:
            print("  [BONUS] %-32s <- %s" % (nom, ", ".join(p["ensemble"])))
    return 0


def cmd_vocabulaire(a) -> int:
    kits = _charger_kits()
    factions, traits, alliances = _vocabulaire(kits)
    print("ALLIANCES (%d) : %s" % (len(alliances), ", ".join(sorted(alliances))))
    print("")
    print("FACTIONS (%d) :" % len(factions))
    for f in sorted(factions):
        print("   %-24s %d personnage(s)"
              % (f, sum(1 for k in kits.values() if k.get("faction") == f)))
    print("")
    print("TRAITS (%d) :" % len(traits))
    for t in sorted(traits):
        print("   %-24s %d porteur(s)"
              % (t, sum(1 for k in kits.values() if t in (k.get("traits") or []))))
    return 0


def main(argv: list[str]) -> int:
    p = argparse.ArgumentParser(
        prog="expedition_solver",
        description="Couverture des objectifs bonus d'une Operation (Expedition). "
                    "100%% hors ligne : lit le gameconfig, ne joue rien, n'envoie rien.")
    sp = p.add_subparsers(dest="cmd", required=True)

    s = sp.add_parser("solve", help="une seule operation")
    s.add_argument("--objectif", action="append", required=True,
                   help="repeter. Formes : melee | ranged | faction:<id> | "
                        "trait:<id> | alliance:<id>. Les libelles UI sont acceptes "
                        "(ex. 'Adeptus Custodes') et resolus, ou REFUSES si ambigus.")
    s.add_argument("--participants", type=int, required=True)
    s.add_argument("--alliance", help="restriction grandAlliance de l'operation")
    s.add_argument("--roster", help="fichier ou liste d'ids possedes")
    s.add_argument("--json", action="store_true")
    s.set_defaults(f=cmd_solve)

    b = sp.add_parser("board", help="plateau entier, unites disjointes")
    b.add_argument("--fichier", required=True, help="JSON du plateau")
    b.add_argument("--roster")
    b.set_defaults(f=cmd_board)

    v = sp.add_parser("vocabulaire", help="lister les ids connus")
    v.set_defaults(f=cmd_vocabulaire)

    a = p.parse_args(argv)
    return a.f(a)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
