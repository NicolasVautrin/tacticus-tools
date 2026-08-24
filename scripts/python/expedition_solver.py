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
PREFIXES = ("faction", "trait", "alliance", "damagetype")

#: Noms NATIFS d'`objectiveType`, releves sur le plateau reel (capteur `expedition-board`,
#: 2026-08-10). On les accepte VERBATIM pour que le JSON capte se rejoue sans traduction.
#: `HasNoRangedAttack` porte `objectiveTarget: "None"` -- la cible est ignoree.
#: `HasRangedAttack` (releve le 2026-08-11) est son PENDANT et porte `objectiveTarget: null` :
#: meme forme, cible bidon a jeter. Il apparaissait sur 4 des 7 operations du plateau et
#: faisait REFUSER tout le calcul -- refus correct (le solveur ne devine pas), mais la
#: mecanique `ranged` etait deja la, seul l'alias manquait.
ALIAS_NATIFS = {
    "faction": "faction",
    "trait": "trait",
    "damagetype": "damagetype",
    "hasnorangedattack": "melee",
    "hasrangedattack": "ranged",
}

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
                      alliances: set[str], degats: set[str] | None = None) -> Objectif:
    t = (txt or "").strip()
    if not t:
        raise ObjectifIrresoluble("objectif VIDE")
    bas = t.lower()
    # Les DEUX formes `Has[No]RangedAttack` portent une cible bidon ("None" / null) : on la
    # jette AVANT de chercher un separateur, sinon on partirait resoudre une faction "None".
    tete = bas.split(":", 1)[0].strip()
    if tete == "hasnorangedattack":
        return Objectif(brut=t, kind="melee", valeur=None,
                        libelle="HasNoRangedAttack (sans attaque a distance normale)")
    if tete == "hasrangedattack":
        return Objectif(brut=t, kind="ranged", valeur=None,
                        libelle="HasRangedAttack (avec attaque a distance normale)")
    if bas in FORMES_SIMPLES:
        libelle = ("Melee (sans attaque a distance normale)" if bas == "melee"
                   else "Ranged (avec attaque a distance normale)")
        return Objectif(brut=t, kind=bas, valeur=None, libelle=libelle)
    if ":" not in t:
        raise ObjectifIrresoluble(
            "objectif NON RECONNU : '%s'. Formes acceptees : %s, ou %s"
            % (t, "/".join(FORMES_SIMPLES), "/".join(p + ":<id>" for p in PREFIXES)))
    pref, _, reste = t.partition(":")
    pref = ALIAS_NATIFS.get(pref.strip().lower(), pref.strip().lower())
    reste = reste.strip()
    if pref == "damagetype":
        vid = _apparier(reste, degats or set(), "TYPE DE DEGAT")
        return Objectif(t, "damagetype", vid, "DamageType %s" % vid)
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
    if o.kind == "damagetype":
        # Les cibles `DamageType` du plateau sont des noms de `DamageProfile` EXACTS -- verifie
        # le 2026-08-10 : les 7 rencontrees (Power, Physical, Energy, Psychic, Piercing, Blast,
        # Flame) apparient toutes a l'identique. On ne normalise donc pas, on compare.
        return any(w.get("profile") == o.valeur for w in (k.get("weapons") or []))
    raise ObjectifIrresoluble("kind non gere : %s" % o.kind)


# ---------------------------------------------------------------------------
# ELIGIBILITE -- mirror 1:1 de
#   Idun.Source.IdunMeta.Logic.Features.Expedition.Progression.UnitEligibility.
#       ExpeditionUnitEligibility$$IsEligibleFor(unit, entry)
#
# Ce que le decompile fait, dans l'ordre, et ce qu'on reproduit :
#
#   1. rarete de l'unite ABSENTE                  -> non eligible (unite non debloquee)
#   2. rarete de l'unite < entry.rarity           -> non eligible (`Expedition.UnitLowRarity`)
#   3. rang < level.GetRequiredRankFor(rarity)    -> non eligible (`Expedition.UnitLowRank`)
#   4. entry.grandAlliance non nul et different   -> non eligible
#
# Le seuil du point 3 est pris sur `entry.rarity` -- la rarete EXIGEE PAR L'OPERATION, pas
# celle de l'unite. C'est ce qui fait qu'une operation Legendary demande a la fois une unite
# Legendary ET un rang eleve.
#
# POURQUOI CE PORT EXISTE. Le solveur raisonnait sur la seule POSSESSION : il pouvait donc
# proposer une unite que l'operation refuse, et le plan avait l'air valide. La possession est
# lisible du gameconfig ; le rang et la rarete, NON -- c'est de la progression de compte, il
# faut la capter (`rosterOwned {details:true}`).
# ---------------------------------------------------------------------------

#: `IdunMetaLogic.UserProgress.Model.UnitRarity` (data/symbols/<build>/frida/enums.tsv).
RARETES = ("Common", "Uncommon", "Rare", "Epic", "Legendary", "Mythic")


def rarete_en_ordinal(v) -> int | None:
    """Accepte l'ordinal ET le nom : le serialiseur peut emettre l'un ou l'autre selon
    qu'un `StringEnumConverter` est pose sur le DTO. Rendre `None` plutot que 0 -- un 0
    signifie `Common`, donc << aucune exigence >>, l'inverse d'une valeur non lue."""
    if isinstance(v, bool):
        return None
    if isinstance(v, int):
        return v if 0 <= v < len(RARETES) else None
    if isinstance(v, str):
        s = v.strip()
        if s.isdigit():
            n = int(s)
            return n if 0 <= n < len(RARETES) else None
        for i, nom in enumerate(RARETES):
            if nom.lower() == s.lower():
                return i
    return None


def est_eligible(unite: str, kits: dict, progression: dict, entry: dict,
                 seuils: dict) -> tuple[bool, str | None]:
    """Rend (eligible, motif_de_refus). `motif` est None quand c'est eligible.

    `progression` = {id: {"rank": int|None, "rarity": int|None}} (RPC `rosterOwned
    {details:true}`). `seuils` = {nom_de_rarete: rang_minimum} (RPC
    `expeditionRankRequirements`).

    Toute donnee NON MESUREE rend un refus NOMME (`... NON MESURE`), jamais un faux
    << eligible >> ni un faux << refuse >> silencieux : on veut voir le trou."""
    p = progression.get(unite)
    if p is None:
        return False, "non possedee"

    # UNE MACHINE OF WAR N'EST JAMAIS DISPATCHABLE, ET SON `rank` NE LE DIT PAS.
    #
    # Mesure du 2026-08-24, plateau `imp_judgement_c_01_10` (Common, Imperial) : le natif
    # `ExpeditionUnitEligibility$$CountEligibleUnits` rend 33, ce miroir en rendait 49.
    # L'ecart se decompose EXACTEMENT -- 13 impériales deja parties + 3 MoW -- donc le seul
    # filtre qui manquait ici est celui-la.
    #
    # POURQUOI CA NE S'ETAIT JAMAIS VU : `rosterOwned` rend `rank: 0` pour une MoW (elle n'a
    # pas de rang -- son niveau est le `StarLevel`, cf. la doctrine MoW). Le test `rang <
    # seuil` la refuse donc partout ou le seuil est > 0, c'est-a-dire des Rare (6). Sur une
    # operation COMMON, le seuil vaut 0 et `0 >= 0` la laisse passer. C'est le symetrique du
    # piege deja connu : un garde sur `Rank` rend un FAUX verdict sur une MoW, dans les deux
    # sens.
    #
    # CE QUE COUTAIT LE TROU : l'envoi est accepte LOCALEMENT (`ok: true`, statut 0 -> 1)
    # puis REVOQUE par la reponse serveur quelques secondes plus tard -- le plateau retombe a
    # `status: 0`, `units: null`, sans le moindre message. Deux envois de suite ont ete
    # perdus ainsi avant que la relecture du plateau ne le montre.
    if "MachineOfWar" in ((kits.get(unite) or {}).get("traits") or []):
        return False, "MachineOfWar -- non dispatchable en Operation"

    rar_u = p.get("rarity")
    if rar_u is None:
        return False, "rarete NON MESUREE"

    rar_op = rarete_en_ordinal(entry.get("rarity"))
    if rar_op is None:
        return False, "rarete de l'operation NON LUE"
    if rar_u < rar_op:
        return False, "rarete insuffisante (%s < %s)" % (RARETES[rar_u], RARETES[rar_op])

    seuil = seuils.get(RARETES[rar_op])
    if seuil is None:
        return False, "seuil de rang NON MESURE pour %s" % RARETES[rar_op]
    rang = p.get("rank")
    if rang is None:
        return False, "rang NON MESURE"
    if rang < seuil:
        return False, "rang insuffisant (%d < %d)" % (rang, seuil)

    alli = entry.get("grandAlliance")
    if alli and (kits.get(unite) or {}).get("alliance") != alli:
        return False, "alliance (%s != %s)" % (
            (kits.get(unite) or {}).get("alliance"), alli)
    return True, None


def pool_eligible(entry: dict, kits: dict, roster: list[str], progression: dict | None,
                  seuils: dict | None) -> tuple[list[str], dict[str, str]]:
    """Le pool reellement dispatchable sur `entry`, et le motif de chaque ecarte.

    `progression`/`seuils` a None = NON MESURES : on retombe sur le seul filtre derivable
    hors ligne (l'alliance), et l'appelant DOIT le dire. Ne jamais faire passer ce repli
    pour une eligibilite complete."""
    if progression is None or seuils is None:
        alli = entry.get("grandAlliance")
        pool = [u for u in roster
                if not alli or (kits.get(u) or {}).get("alliance") == alli]
        return pool, {u: "alliance" for u in roster if u not in set(pool)}
    ok, refuses = [], {}
    for u in roster:
        e, motif = est_eligible(u, kits, progression, entry, seuils)
        if e:
            ok.append(u)
        else:
            refuses[u] = motif or "?"
    return ok, refuses


# ---------------------------------------------------------------------------
# Couverture exacte
# ---------------------------------------------------------------------------

def masque(k: dict, objs: list[Objectif]) -> int:
    m = 0
    for i, o in enumerate(objs):
        if satisfait(k, o):
            m |= 1 << i
    return m


def _enumerer(dispo: dict[int, int], besoins: tuple[int, ...], limite: int,
              plafond: int) -> tuple[list[tuple[tuple[int, int], ...]], bool]:
    """Enumere les selections de <= `limite` personnages satisfaisant les MULTIPLICITES.

    LE MODELE, ET IL A ETE MESURE, PAS SUPPOSE. Les objectifs d'une operation forment un
    MULTI-ENSEMBLE : le plateau reel porte `DamageType:Physical` deux fois, `Trait:Healer`
    deux fois, `Faction:AdeptusMechanicus` deux fois. Deux lectures etaient possibles :

      (a) un doublon n'exige qu'un porteur (un personnage couvre les deux entrees)
          -> le doublon serait SANS EFFET, ce qui n'a pas de sens ;
      (b) chaque instance exige un personnage DISTINCT, et un personnage ne compte que
          pour une instance -> il faudrait au moins autant de places que d'objectifs.

    (b) est REFUTEE par la mesure : 6 operations sur 7 ont PLUS d'objectifs que de places
    (op 3 : 6 objectifs pour 4 places). Le bonus serait inatteignable. Le modele retenu est
    donc le seul qui survive aux deux faits : pour chaque objectif DISTINCT de multiplicite
    m, il faut au moins m personnages distincts qui le remplissent, et un personnage compte
    simultanement pour tous les objectifs DIFFERENTS qu'il remplit.

    `dispo` : masque de couverture -> nombre de candidats portant ce masque.
    `besoins` : multiplicite requise par objectif distinct.
    Rend (solutions, plafond_atteint) ; une solution = tuple trie de (masque, quantite).
    """
    sols: list[tuple[tuple[int, int], ...]] = []
    vues: set[tuple[tuple[int, int], ...]] = set()
    deborde = [False]
    masques = sorted(dispo)

    def rec(restants: tuple[int, ...], pris: dict[int, int], profondeur: int) -> None:
        if deborde[0]:
            return
        if not any(restants):
            cle = tuple(sorted(pris.items()))
            if cle not in vues:
                vues.add(cle)
                sols.append(cle)
                if len(sols) >= plafond:
                    deborde[0] = True
            return
        places = limite - profondeur
        # Un personnage ajoute AU PLUS 1 au compte d'un objectif donne : si un deficit
        # depasse le nombre de places restantes, la branche est morte.
        if max(restants) > places:
            return
        # On vise le PREMIER objectif encore deficitaire : ca elimine les permutations.
        j = next(i for i, r in enumerate(restants) if r > 0)
        bit_j = 1 << j
        for mk in masques:
            if not (mk & bit_j):
                continue
            if pris.get(mk, 0) >= dispo[mk]:
                continue          # plus de candidat portant ce masque
            suivants = tuple(max(0, r - (1 if mk & (1 << i) else 0))
                             for i, r in enumerate(restants))
            pris[mk] = pris.get(mk, 0) + 1
            rec(suivants, pris, profondeur + 1)
            pris[mk] -= 1
            if pris[mk] == 0:
                del pris[mk]
            if deborde[0]:
                return

    rec(tuple(besoins), {}, 0)
    return sols, deborde[0]


def resoudre_operation(candidats: list[dict], objs: list[Objectif],
                       participants: int,
                       plafond: int = PLAFOND_SOLUTIONS) -> dict:
    """Resout UNE operation. Rend un dict AUDITABLE : par objectif, combien de
    candidats le remplissent (un 0 est ainsi VISIBLE et nomme), la taille minimale
    trouvee, et les solutions en identifiants d'unites."""
    # Les objectifs arrivent en MULTI-ENSEMBLE : on les replie sur leurs valeurs DISTINCTES
    # en gardant la multiplicite, qui devient le nombre de porteurs exiges.
    distincts: list[Objectif] = []
    besoins: list[int] = []
    for o in objs:
        cle = (o.kind, o.valeur)
        trouve = next((i for i, d in enumerate(distincts)
                       if (d.kind, d.valeur) == cle), None)
        if trouve is None:
            distincts.append(o)
            besoins.append(1)
        else:
            besoins[trouve] += 1

    par_masque: dict[int, list[dict]] = {}
    for k in candidats:
        m = masque(k, distincts)
        if m:
            par_masque.setdefault(m, []).append(k)

    couverture = [
        {"objectif": d.libelle, "requis": besoins[i],
         "candidats": sum(1 for k in candidats if satisfait(k, d))}
        for i, d in enumerate(distincts)
    ]
    # Un objectif est infaisable des que le vivier est plus petit que la MULTIPLICITE : avec
    # un seul Healer possede, `Trait:Healer` demande deux fois ne peut pas tomber. Comparer a
    # zero seulement aurait laisse passer ce cas et rendu un << impossible >> sans cause.
    impossibles = [
        "%s (requis %d, disponibles %d)" % (c["objectif"], c["requis"], c["candidats"])
        for c in couverture if c["candidats"] < c["requis"]
    ]

    base = {
        "objectifs": [o.libelle for o in objs],
        "distincts": [d.libelle for d in distincts],
        "besoins": besoins,
        "participants": participants,
        "candidats": len(candidats),
        "couverture": couverture,
        "impossibles": impossibles,
        "plafond_atteint": False,
    }
    if impossibles:
        base.update({"ok": False, "raison": "objectif(s) sans assez de porteurs",
                     "taille": None, "solutions": []})
        return base
    if not distincts:
        base.update({"ok": True, "taille": 0, "solutions": [], "raison": None})
        return base

    dispo = {mk: len(us) for mk, us in par_masque.items()}
    # Borne haute : jamais plus que les places, et jamais plus que la somme des besoins.
    borne = min(participants, sum(besoins))
    for taille in range(1, borne + 1):
        sols, deborde = _enumerer(dispo, tuple(besoins), taille, plafond)
        sols = [s for s in sols if sum(q for _, q in s) == taille]
        if sols:
            rendu = []
            for combo in sols:
                rendu.append([
                    {"masque": mk, "quantite": q,
                     "objectifs": [distincts[i].libelle for i in range(len(distincts))
                                   if mk & (1 << i)],
                     "unites": [{"id": u["id"], "name": u.get("name"),
                                 "faction": u.get("faction")}
                                for u in par_masque[mk]]}
                    for mk, q in combo
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
        # Produit cartesien borne. Un groupe de masque peut exiger PLUSIEURS porteurs
        # (multiplicite) : on lui ouvre alors autant d'emplacements, et le controle
        # `len(fs) == len(choix)` plus bas rejette les tirages qui reprendraient deux fois
        # le meme personnage -- ce qui est exactement la contrainte << porteurs distincts >>.
        listes: list[list[str]] = []
        for grp in combo:
            ids = [u["id"] for u in grp["unites"]]
            for _ in range(grp.get("quantite", 1)):
                listes.append(ids)
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


def deja_parties(ops: list[dict]) -> tuple[list[dict], list[str]]:
    """Separe les operations DISPONIBLES de celles deja lancees, et rend les unites
    immobilisees.

    `status` != 0 = deja dispatchee (mesure : 0 avant envoi, 1 apres). Ses `units` sont
    IMMOBILISEES pour la duree -- les laisser dans le roster ferait proposer des unites
    qui ne peuvent pas partir, exactement le defaut que l'eligibilite vient de corriger
    sur un autre axe."""
    libres, prises = [], []
    for op in ops:
        if op.get("status"):
            prises.extend(op.get("units") or [])
        else:
            libres.append(op)
    return libres, sorted(set(prises))


def presse_par_unite(prepares: list[dict]) -> dict[str, int]:
    """unite -> taille du POOL LE PLUS ETROIT ou elle figure. Petit = PRECIEUSE.

    POURQUOI, et c'est une operation PERDUE le 2026-08-11 : le remplissage piochait dans le
    pool le plus large sans regarder ce qu'il coutait ailleurs. Il a depense `adeptCanoness`
    et `admecRuststalker` -- deux des CINQ seules unites de rang 17 du roster -- en bourrage
    sur une Legendary a 32 eligibles. L'operation Mythic, qui n'avait que ces 5 candidats
    pour 4 places, s'est retrouvee a 2 unites libres : elle n'est jamais partie, alors que
    sa recompense de BASE etait a portee.

    On consomme donc les unites par presse DECROISSANTE : les abondantes d'abord, celles qui
    sont le dernier recours d'une operation etroite en dernier.
    """
    presse: dict[str, int] = {}
    for p in prepares:
        n = len(p["ids"])
        for u in p["ids"]:
            if u not in presse or n < presse[u]:
                presse[u] = n
    return presse


def completer(ensemble: set[str], besoin: int, pool: list[str],
              indisponibles: set[str], presse: dict[str, int] | None = None
              ) -> tuple[set[str], int] | None:
    """Complete `ensemble` jusqu'a `besoin` unites, avec des eligibles libres.

    POURQUOI C'EST OBLIGATOIRE, et mesure au decompile :
    `ExpeditionDispatchScreen$$HandleOnDispatchTapped` compare `SelectedCount()` a
    `ParticipantsRequired` et RETOURNE SANS RIEN ENVOYER si c'est inferieur ;
    `UpdateDispatchButton` garde le bouton grise dans le meme cas. Une place vide ne
    reste donc pas vide : elle EMPECHE le depart.

    Consequence sur le plan : une operation consomme `participants` unites, pas la taille
    de son ensemble couvrant. Rend `None` si le pool libre n'y suffit pas."""
    manque = besoin - len(ensemble)
    if manque <= 0:
        return set(ensemble), 0
    libres = [u for u in pool if u not in ensemble and u not in indisponibles]
    if len(libres) < manque:
        return None
    if presse:
        # presse DECROISSANTE : on brule les unites abondantes avant les rares. `-presse` en
        # cle primaire, le nom en secondaire pour rester DETERMINISTE (deux unites de meme
        # presse doivent toujours sortir dans le meme ordre, sinon le plan bouge d'un run a
        # l'autre sans qu'aucune donnee n'ait change).
        libres.sort(key=lambda u: (-presse.get(u, 10 ** 9), u))
    return set(ensemble) | set(libres[:manque]), manque


def resoudre_plateau(ops: list[dict], kits: dict[str, dict], roster: list[str],
                     plafond_ens: int = PLAFOND_ENSEMBLES_PAR_OP,
                     progression: dict | None = None,
                     seuils: dict | None = None) -> dict:
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
        dispo = [u for u in roster if u in kits]
        ids, _ = pool_eligible(op, kits, dispo, progression, seuils)
        pool = [kits[u] for u in ids]
        ens = _ensembles_par_op(pool, op["_objs"], int(op.get("participants") or 0),
                                plafond_ens)
        prepares.append({"op": op, "ensembles": ens, "pool": len(pool), "ids": ids})

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

    # REMPLISSAGE OBLIGATOIRE. La recherche ci-dessus raisonne sur les ensembles COUVRANTS
    # (minimaux) ; le jeu, lui, exige `participants` unites (cf. `completer`). On complete
    # donc apres coup, en traitant les operations du POOL LE PLUS ETROIT au plus large --
    # une operation a 15 eligibles doit servir avant une a 76, sinon la seconde lui prend
    # ses rares candidats.
    #
    # Ce n'est PAS optimal : le remplissage n'est pas re-injecte dans la recherche, donc un
    # plan peut perdre une operation ici alors qu'un autre choix d'ensembles l'aurait
    # gardee. Une operation qu'on ne peut pas completer est RETIREE du plan et NOMMEE --
    # jamais laissee incomplete, ce qui la ferait paraitre partante.
    par_id = {id(p["op"]): p for p in prepares}
    plan = meilleur["plan"] or []
    ordre = sorted([p for p in plan if p["ensemble"] is not None],
                   key=lambda p: len(par_id[id(p["op"])]["ids"]))
    # ⛔ TOUS LES ENSEMBLES COUVRANTS SONT RESERVES D'EMBLEE, pas au fil du parcours.
    # `rec` garantit que les couvrants sont disjoints ENTRE EUX, mais le remplissage se
    # sert dans le pool libre : parti d'un `utilisees` VIDE, il pouvait prendre une unite
    # deja couvrante d'une operation PAS ENCORE TRAITEE, qui la gardait ensuite (son
    # ensemble est fige). Le plan sortait avec la meme unite sur DEUX operations -- donc
    # injouable, une unite partie etant immobilisee pour la duree.
    # MESURE (plateau du 2026-08-11, 7 operations) : 3 doublons sur 28 places --
    # `astraPrimarisPsy`, `adeptHospitaller`, `adeptRetributor`, chacun couvrant ici et
    # remplissage la. Les trois relevaient exactement de ce patron.
    reserves = {u for p in ordre for u in p["ensemble"]}
    presse = presse_par_unite(prepares)
    utilisees: set[str] = set()
    incompletes: list[dict] = []
    for p in ordre:
        prep = par_id[id(p["op"])]
        besoin = int(p["op"].get("participants") or 0)
        # `reserves - ensemble` : les couvrants des AUTRES operations sont interdits au
        # remplissage ; le sien propre ne l'est pas, il EST la base a completer.
        r = completer(set(p["ensemble"]), besoin, prep["ids"],
                      utilisees | (reserves - set(p["ensemble"])), presse)
        if r is None:
            incompletes.append({"op": p["op"].get("expeditionId") or p["op"].get("id"),
                                "besoin": besoin, "couvrant": len(p["ensemble"]),
                                "pool_libre": len([u for u in prep["ids"]
                                                   if u not in utilisees])})
            p["ensemble"] = None
            p["equipe"] = None
            continue
        equipe, ajoutes = r
        p["equipe"] = sorted(equipe)
        p["remplissage"] = ajoutes
        utilisees |= equipe

    couvertes = sum(1 for p in plan if p["ensemble"] is not None)

    # SANS BONUS N'EST PAS SANS INTERET. Une operation dont aucun ensemble ne couvre les
    # objectifs rapporte quand meme sa recompense de BASE -- la renoncer, c'est laisser un
    # slot vide. MESURE du 2026-08-11 : la Mythic `imp_guns_m_01_10` (bonus hors d'atteinte,
    # 5 eligibles pour 4 places) a ete abandonnee, et 6 operations sont parties la ou 7
    # pouvaient l'etre.
    # On les traite APRES les operations a bonus -- jamais au detriment d'un bonus -- et de
    # la plus etroite a la plus large, meme raison qu'au-dessus.
    sans_bonus = sorted([p for p in plan if p["ensemble"] is None],
                        key=lambda p: len(par_id[id(p["op"])]["ids"]))
    base_seule: list[str] = []
    for p in sans_bonus:
        prep = par_id[id(p["op"])]
        besoin = int(p["op"].get("participants") or 0)
        r = completer(set(), besoin, prep["ids"], utilisees, presse)
        if r is None:
            continue
        equipe, ajoutes = r
        p["equipe"] = sorted(equipe)
        p["remplissage"] = ajoutes
        p["base_seule"] = True
        utilisees |= equipe
        base_seule.append(p["op"].get("expeditionId") or p["op"].get("id"))

    return {
        "operations": len(prepares),
        "couvertes": couvertes,
        # Operations parties SANS bonus : elles occupent un slot et rapportent la base.
        "base_seule": base_seule,
        "partantes": couvertes + len(base_seule),
        # Ce que le plan consomme REELLEMENT : la somme des `participants`, pas la taille
        # des ensembles couvrants.
        "unites_mobilisees": len(utilisees),
        "unites_utiles": meilleur["unites"] or 0,
        "incompletes": incompletes,
        "plan": plan,
        "ensembles_par_op": [len(p["ensembles"]) for p in prepares],
        "pool_par_op": [p["pool"] for p in prepares],
        "plafond_ensembles": plafond_ens,
        # Ce que le plan a REELLEMENT filtre. `alliance` = repli : rang et rarete NON
        # MESURES, donc le plan peut proposer une unite que l'operation refuse.
        "eligibilite": "complete" if (progression is not None and seuils is not None)
                       else "alliance seule",
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
    degats = {w.get("profile") for k in kits.values()
              for w in (k.get("weapons") or []) if w.get("profile")}
    return factions, traits, alliances, degats


def normaliser_objectif_brut(x) -> str:
    """Accepte les DEUX formes : la chaine ecrite a la main (`trait:Healer`) et la forme
    NATIVE captee par `expedition-board`
    (`{"objectiveType": "Trait", "objectiveTarget": "Healer"}`).

    Le serialiseur emet la cle dans les deux casses (`objectiveType` ET `ObjectiveType`) --
    champ ET propriete sont serialises ; on lit l'une ou l'autre."""
    if isinstance(x, str):
        return x
    if isinstance(x, dict):
        t = x.get("objectiveType") or x.get("ObjectiveType")
        v = x.get("objectiveTarget") or x.get("ObjectiveTarget")
        if t:
            return "%s:%s" % (t, v)
    raise ObjectifIrresoluble("objectif de forme inconnue : %r" % (x,))


def _extraire_board(donnees) -> list[dict]:
    """Deroule les enveloppes connues. Le capteur `expedition-board` rend
    `{"expeditionState": {"board": [...]}}` ; un fichier ecrit a la main peut etre une liste
    nue ou `{"board": [...]}`. On accepte les trois plutot que d'imposer un reformatage --
    le JSON capte doit se rejouer TEL QUEL."""
    if isinstance(donnees, list):
        return donnees
    if isinstance(donnees, dict):
        if isinstance(donnees.get("expeditionState"), dict):
            donnees = donnees["expeditionState"]
        for cle in ("board", "operations"):
            if isinstance(donnees.get(cle), list):
                return donnees[cle]
    raise ValueError("plateau introuvable : attendu une liste, `board`, `operations` "
                     "ou `expeditionState.board`")


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


def _lire_json(chemin: str):
    with open(chemin, "r", encoding="utf-8-sig") as fh:
        return json.load(fh)


def _charger_eligibilite(a) -> tuple[dict | None, dict | None]:
    """Charge la progression (rang/rarete) et les seuils de rang.

    On accepte la REPONSE RPC telle quelle (`{"ok":true,"details":{...}}`,
    `{"ok":true,"seuils":{...}}`) autant que le dict nu : le JSON capte doit se rejouer
    sans reformatage prealable.

    Les deux vont ENSEMBLE. N'en fournir qu'un rend `(None, None)` avec un refus explicite
    -- un filtre a moitie applique produirait un pool faux sans que rien ne le dise."""
    prog = getattr(a, "progression", None)
    seui = getattr(a, "seuils", None)
    if not prog and not seui:
        return None, None
    if not prog or not seui:
        print("REFUS d'eligibilite partielle : --progression et --seuils vont ensemble.")
        print("   Le filtre retombe sur l'ALLIANCE SEULE.")
        return None, None
    p = _lire_json(prog)
    if isinstance(p, dict) and isinstance(p.get("details"), dict):
        p = p["details"]
    s = _lire_json(seui)
    if isinstance(s, dict) and isinstance(s.get("seuils"), dict):
        s = s["seuils"]
    if not isinstance(p, dict) or not isinstance(s, dict):
        print("REFUS : --progression attend {id: {rank, rarity}}, --seuils {rarete: rang}.")
        return None, None
    manquants = [k for k in RARETES if s.get(k) is None]
    if manquants:
        print("ATTENTION -- seuil NON MESURE pour : %s. Les operations de ces raretes"
              % ", ".join(manquants))
        print("             rendront un pool VIDE, avec le motif ecrit.")
    return p, s


def _afficher_operation(r: dict) -> None:
    print("Objectifs        : %s" % " | ".join(r["objectifs"]))
    print("Participants max : %d" % r["participants"])
    print("Candidats        : %d" % r["candidats"])
    print("")
    print("Couverture par objectif DISTINCT (requis = multiplicite sur le plateau) :")
    for c in r["couverture"]:
        marque = "  PAS ASSEZ DE PORTEURS" if c["candidats"] < c["requis"] else ""
        print("   %-42s requis %d   porteurs %4d%s"
              % (c["objectif"], c["requis"], c["candidats"], marque))
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
            q = grp.get("quantite", 1)
            print("     %dx couvre [%s]" % (q, " + ".join(grp["objectifs"])))
            print("        -> choisir %d parmi : %s" % (q, noms))
    if len(r["solutions"]) > 10:
        print("  ... %d autres solutions de meme taille" % (len(r["solutions"]) - 10))


def cmd_solve(a) -> int:
    kits = _charger_kits()
    factions, traits, alliances, degats = _vocabulaire(kits)
    try:
        objs = [resoudre_objectif(normaliser_objectif_brut(t), factions, traits,
                                  alliances, degats) for t in a.objectif]
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
    factions, traits, alliances, degats = _vocabulaire(kits)
    with open(a.fichier, "r", encoding="utf-8-sig") as fh:
        ops = _extraire_board(json.load(fh))
    try:
        for op in ops:
            op["_objs"] = [
                resoudre_objectif(normaliser_objectif_brut(t), factions, traits,
                                  alliances, degats)
                for t in (op.get("bonusObjectives") or [])]
    except ObjectifIrresoluble as e:
        print("REFUS : %s" % e)
        return 2
    roster, suppose = _roster(a.roster, kits)
    if suppose:
        print("ATTENTION -- aucun roster fourni : on suppose TOUT possede (%d)." % len(kits))
        print("")
    progression, seuils = _charger_eligibilite(a)
    ops, immobilisees = deja_parties(ops)
    if immobilisees:
        print("DEJA PARTIES : %d unite(s) immobilisee(s), retirees du roster : %s"
              % (len(immobilisees), ", ".join(immobilisees)))
        roster = [u for u in roster if u not in set(immobilisees)]
        print("")
    r = resoudre_plateau(ops, kits, roster, progression=progression, seuils=seuils)
    print("Operations disponibles : %d" % r["operations"])
    print("PARTANTES : %d / %d   (dont %d avec bonus, %d pour la BASE seule)"
          % (r["partantes"], r["operations"], r["couvertes"], len(r["base_seule"])))
    print("Unites mobilisees : %d (dont %d utiles au bonus, le reste = remplissage "
          "OBLIGATOIRE)" % (r["unites_mobilisees"], r["unites_utiles"]))
    for i in r.get("incompletes") or []:
        print("   ECARTEE faute de remplissage : %s -- besoin %d, couvrant %d, "
              "pool libre %d" % (i["op"], i["besoin"], i["couvrant"], i["pool_libre"]))
    print("Eligibilite appliquee : %s" % r["eligibilite"])
    if r["eligibilite"] != "complete":
        print("   ATTENTION -- rang et rarete NON MESURES : un plan peut proposer une unite")
        print("   que l'operation refuse. Fournis --progression et --seuils.")
    print("Pool par operation : %s" % r["pool_par_op"])
    print("Ensembles candidats retenus par operation : %s (plafond %d)"
          % (r["ensembles_par_op"], r["plafond_ensembles"]))
    print("")
    for p in r["plan"]:
        op = p["op"]
        nom = op.get("expeditionId") or op.get("id") or "?"
        if p["ensemble"] is None and not p.get("equipe"):
            print("  [NON PARTANTE] %s -- bonus hors d'atteinte ET pas assez d'unites "
                  "libres eligibles" % nom)
        elif p["ensemble"] is None:
            # Bonus hors d'atteinte, mais l'operation PART : elle occupe un slot et rapporte
            # sa recompense de base. Toutes ses unites sont du remplissage par construction.
            eq = p["equipe"]
            print("  [BASE SEULE] %-33s %d place(s)  -- aucun bonus atteignable" % (nom, len(eq)))
            for u in eq:
                print("             %-24s (remplissage)" % u)
        else:
            eq = p.get("equipe") or p["ensemble"]
            utiles = set(p["ensemble"])
            # Le remplissage est marque : ces unites ne servent AUCUN objectif, elles
            # occupent une place que le jeu exige de remplir.
            print("  [BONUS] %-38s %d place(s)" % (nom, len(eq)))
            for u in eq:
                print("             %-24s %s" % (u, "" if u in utiles else "(remplissage)"))
    return 0


def cmd_confronter(a) -> int:
    """NOTRE compte d'eligibles CONTRE celui du jeu, operation par operation.

    C'est le temoin du port : `ExpeditionUnitEligibility$$CountEligibleUnits(entry)` est
    calcule par le jeu lui-meme au rendu du plateau, et `expedition-board` en lit le RETOUR.
    Si notre mirror de `IsEligibleFor` est fidele, les deux comptes coincident sur les SEPT
    operations -- des nombres non triviaux et distincts, donc une concordance qui ne peut
    pas etre un hasard.

    Un ecart n'est pas rattrape : il est affiche avec l'operation et les deux comptes."""
    kits = _charger_kits()
    ops = _extraire_board(_lire_json(a.fichier))
    roster, _ = _roster(a.roster, kits)
    progression, seuils = _charger_eligibilite(a)
    if progression is None or seuils is None:
        print("REFUS : la confrontation exige --progression ET --seuils.")
        return 2

    natif = _lire_json(a.natif)
    entrees = natif.get("entries") if isinstance(natif, dict) else natif
    if not isinstance(entrees, list):
        print("REFUS : --natif attend la reponse de `expeditionEligibility` "
              "({\"entries\": [...]}).")
        return 2
    # Le compte natif est indexe par `expeditionId` -- la seule cle que les deux sources
    # partagent (le capteur ne lit pas `id`).
    par_id = {e.get("expeditionId"): e.get("eligibles") for e in entrees
              if isinstance(e, dict)}

    print("Roster interroge : %d unites" % len(roster))
    print("Seuils de rang   : %s" % seuils)
    print("")
    print("%-34s %8s %8s   %s" % ("OPERATION", "PORTE", "NATIF", "VERDICT"))
    accords = ecarts = nonmesures = 0
    for op in ops:
        nom = op.get("expeditionId") or op.get("id") or "?"
        pool, _refuses = pool_eligible(op, kits, roster, progression, seuils)
        attendu = par_id.get(nom)
        if attendu is None:
            verdict = "NON MESURE par le jeu"
            nonmesures += 1
        elif attendu == len(pool):
            verdict = "OK"
            accords += 1
        else:
            verdict = "ECART de %+d" % (len(pool) - attendu)
            ecarts += 1
        print("%-34s %8d %8s   %s"
              % (nom[:34], len(pool),
                 "?" if attendu is None else str(attendu), verdict))
    print("")
    print("accords %d | ecarts %d | non mesurees %d" % (accords, ecarts, nonmesures))
    if accords == 0:
        # Un accord VIDE se lirait comme un succes. Il ne prouve rien.
        print("AUCUN accord mesure -- ce resultat ne valide RIEN du port.")
        return 1
    return 0 if ecarts == 0 else 1


def cmd_vocabulaire(a) -> int:
    kits = _charger_kits()
    factions, traits, alliances, degats = _vocabulaire(kits)
    print("ALLIANCES (%d) : %s" % (len(alliances), ", ".join(sorted(alliances))))
    print("")
    print("TYPES DE DEGAT (%d) -- cibles de `DamageType:` :" % len(degats))
    for d in sorted(degats):
        print("   %-24s %d arme(s)"
              % (d, sum(1 for k in kits.values()
                        for w in (k.get("weapons") or []) if w.get("profile") == d)))
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
    b.add_argument("--progression",
                   help="JSON du RPC `rosterOwned {details:true}` (rang + rarete par unite)")
    b.add_argument("--seuils",
                   help="JSON du RPC `expeditionRankRequirements` (rarete -> rang minimum)")
    b.set_defaults(f=cmd_board)

    c = sp.add_parser("confronter",
                      help="notre eligibilite portee CONTRE le compte du jeu, par operation")
    c.add_argument("--fichier", required=True, help="JSON du plateau")
    c.add_argument("--roster", required=True)
    c.add_argument("--progression", required=True)
    c.add_argument("--seuils", required=True)
    c.add_argument("--natif", required=True,
                   help="JSON du RPC `expeditionEligibility` (comptes CountEligibleUnits)")
    c.set_defaults(f=cmd_confronter)

    v = sp.add_parser("vocabulaire", help="lister les ids connus")
    v.set_defaults(f=cmd_vocabulaire)

    a = p.parse_args(argv)
    return a.f(a)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
