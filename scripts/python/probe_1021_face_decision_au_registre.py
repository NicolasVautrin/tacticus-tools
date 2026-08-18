"""#1021 -- CLIQUET : une active qui entre dans `ABILITY_CLASSES` porte son VERDICT de face DECISION.

LA QUESTION BINAIRE
--------------------
    « Une active qui entre dans `ABILITY_CLASSES` peut-elle etre livree SANS verdict de face
      DECISION ? »

Avant ce module : OUI, en silence. `probe_909_decision_actives_kit.py` COMPTAIT les actives sans
face decision portee et rendait `rc=0` -- un inventaire deguise en garde-fou, exactement ce que
`probe_181_targeting_gaps.py` etait avant #430 (il rendait `0` inconditionnellement pendant que le
CLAUDE.md le citait comme cliquet). Le gisement est le meme que `TARGETING_OPTIONS` et
`ABILITY_ATTACK_TYPE` : **notre propre cadence de portage l'alimente**. Chaque ability qu'on porte
en COMBAT sans rien dire de sa face DECISION rouvre le trou, et la degradation est muette -- l'unite
s'execute fidelement mais est CHOISIE par le chemin generique, ce qui est invisible en replay.

LE VERDICT, C'EST L'ETAT TERNAIRE -- PAS << PORTEE >>
------------------------------------------------------
« Porter » n'est PAS l'unique reponse, et le rabattre a deux etats est un axe FAUX (`#979`,
`decision_face_voies`) : une active dont le playbook natif EST le chemin generique n'a RIEN a
porter, et la compter comme du travail est aussi faux que de rater un port. Un verdict est donc
l'un des trois :

    PORTEE      une VOIE de `decision_face_voies.VOIES` la designe (14 voies PARTITIONNEES) ;
    CONSTANTE   le ledger `coverage_attestations` l'atteste `RIEN_A_PORTER` (categorie
                `active-decision`), verdict LU au corps natif et ancre par un cliquet ;
    (PORTEE)    ledger `PORTE_HORS_REGISTRE` -- porte par une voie sans registre, porteur resolvable.

Une attestation PERIMEE ne vaut rien : `attestations_valides` la retire, l'item redevient du
travail, et ce cran le voit ROUGE s'il n'est pas en dette. Aucun chemin ne fait disparaitre du
travail.

LA DETTE EST FIGEE, ET C'EST CE QUI REND LE CRAN LIVRABLE
-----------------------------------------------------------
Poser l'obligation seche rendrait `master` rouge sur 16 abilities le jour de la livraison -- donc la
ferait desarmer dans l'heure. Meme arbitrage que `declencheur_guard` (#486-r15) et
`probe_287r9_consommateurs_oracle` (#287-r9), dont ce module copie la FORME : un registre `DETTE`
VERSIONNE, donc tout elargissement apparait dans un diff.

⚠ LE COMPTE N'EST PAS UN SEUIL, ET C'EST DELIBERE. Le 2026-08-13, CINQ cliquets ont rougi parce
qu'une ability avait ete PORTEE : leurs planchers de population (`>= 20`, `>= 1`,
`any(canal peuple)`) prenaient le PROGRES pour une panne. Aucun cran d'ici ne compare un compte a
un nombre :

    CRAN A  un id sans verdict et ABSENT de `DETTE`               -> ROUGE   (regression)
    CRAN B  un id declare `TRANCHE` qui a PERDU son verdict       -> ROUGE   (regression)
    CRAN C  population vide / mirror vide / ledger illisible      -> ROUGE   (mesure creuse)
    ---     un id `SANS_VERDICT` qui a ACQUIS son verdict         -> IMPRIME, jamais rouge

La dette ne peut donc que DESCENDRE : chaque item tranche se retire (ou passe a `TRANCHE`), et le
CRAN A le protege ensuite pour toujours. L'inverse -- un id qui reviendrait sans verdict -- est un
elargissement de `DETTE`, donc une ligne ajoutee dans un diff que quelqu'un relit.

CE QUE CE CRAN NE VOIT PAS (portee imprimee a chaque execution)
----------------------------------------------------------------
  * les actives HORS `ABILITY_CLASSES` : le registre porte la face COMBAT, donc une active dont
    aucune des deux faces n'est portee n'y est pas et reste invisible ici. Le compte est imprime,
    derive de l'enum COMPLET -- jamais suppose ;
  * les faces TRIGGERED / NON-OWNER / SPECIFIC (dicts `+0x88`, `+0x98`, `+0xa8` de
    `IdunBattle.AI.PlaybookDatabase`) : autre population, autres inventaires (case-419,
    case-433-r4-r3, case-477r33/r35/r37) ;
  * la FIDELITE d'un verdict `PORTEE` : ce cran dit qu'une voie DESIGNE l'ability, jamais que
    l'utilite portee est juste ;
  * la SUBSTANCE d'un item en dette : la raison inscrite cite le playbook natif et ses methodes
    propres (derivees de `ghidra/functions.tsv`), qui est une BORNE INFERIEURE -- IL2CPP
    deduplique les corps triviaux.

Usage (100 % offline, aucun runner) :
    python scripts/python/probe_1021_face_decision_au_registre.py
    python scripts/python/probe_1021_face_decision_au_registre.py --tout   # y compris les PORTEES
ASCII only ; exit 0 = les trois crans passent.
"""
from __future__ import annotations

import argparse
import collections
import os
import sys

_PYROOT = os.path.dirname(os.path.abspath(__file__))
if _PYROOT not in sys.path:
    sys.path.insert(0, _PYROOT)

import decision_face_voies as DFV                                          # noqa: E402
import enum_maps as EM                                                     # noqa: E402
from engine.runner.abilities.handler import ABILITY_CLASSES                # noqa: E402

#: Ce qui doit changer pour que ce cliquet puisse changer d'avis (#486-r12).
DECLENCHEUR = {
    "chemins": ("scripts/python/**/*.py", "data/seed-bc.json",
                "scripts/ratchets-951r2-couverture-attestee.json"),
    "build": True,
    "toujours": False,
    "raison": "Il croise DEUX registres en memoire : `ABILITY_CLASSES` (face COMBAT) et les voies "
              "de `decision_face_voies` (face DECISION), plus le ledger d'attestations. Son "
              "declencheur est donc la FERMETURE D'IMPORT de `engine.runner.abilities.handler` et "
              "de `engine.playbook.**` -- prise a tout `scripts/python/**` parce qu'un import "
              "indirect peut atteindre n'importe quel module (mesure de `probe_181`, meme "
              "fermeture : 366 fichiers, dont `data/seed-bc.json` qu'aucune relecture du source "
              "ne donne). `build: True` : la validite d'une attestation PERIME au changement de "
              "build (`coverage_attestations.validite` compare a `data/symbols/CURRENT`), donc un "
              "nouveau build peut a lui seul remettre un item au compte des sans-verdict.",
}

#: Les etats declarables dans `DETTE`. Deux, et ils n'ont PAS le meme cran :
#:   `SANS_VERDICT` -- dette connue, TOLEREE par le CRAN A. Acquerir un verdict est un PROGRES :
#:                     imprime, jamais rouge, et la ligne se retire (ou passe a `TRANCHE`).
#:   `TRANCHE`      -- le verdict a ete pose ; le CRAN B exige qu'il le RESTE. C'est ce qui empeche
#:                     un item deja solde de retomber en silence sous couvert de sa vieille ligne.
ETATS = ("SANS_VERDICT", "TRANCHE")

# ------------------------------------------------------------------------------------------------
# LE REGISTRE DE DETTE -- mesure du 2026-08-13 sur le build `rnca9r7q6c`, commit `f51b2447`.
# Il ne peut que DECROITRE : un sans-verdict absent d'ici fait rougir le CRAN A.
#
# Chaque raison porte ce qui a ete DERIVE, pas ce qui est suppose : la classe de playbook natif lue
# dans `data/symbols/<build>/metadata/active_playbook_builders.tsv` (dict `+0x68` de
# `IdunBattle.AI.PlaybookDatabase`, extrait par `probe_909 --regenerer`), ses methodes propres lues
# dans `ghidra/functions.tsv` (BORNE INFERIEURE : IL2CPP deduplique les corps triviaux), la classe
# qui porte la face COMBAT, et la ventilation des porteurs par `kind` de kit.
#
# Le nom de la methode propre DIT le registre vise (derivation de `probe_909` etape 4) :
#   `EvaluateNonComparable`  -> `playbook.noncomparable.PLAYBOOKS`
#   `MakeDamagePredictions`  -> `entities.abilities.active_ability._SPECIAL_ABILITY_CLASSES`
#   aucune methode listee    -> INDETERMINE : trancher au slot de vtable, pas a l'absence.
# ------------------------------------------------------------------------------------------------
DETTE: dict[int, tuple[str, str]] = {
    1011: ("SANS_VERDICT",
           "TunnelingHorrorPlaybook -- EvaluateNonComparable, ShouldEvaluate. COMBAT : "
           "TunnelingHorrorAbility (necrons). 4 porteurs (npc, summons)."),
    1018: ("SANS_VERDICT",
           "ValkyrieStrikePlaybook -- EvaluateNonComparable, GetNumberOfEnemies, "
           "GetNumberOfFriends, GetPossiblyTargetedUnits. COMBAT : ValkyrieStrikeAbility "
           "(strike). 2 porteurs (npc, summons)."),
    # 1023 Burrowers -- LIGNE RETIREE par #1021-r2 : la face DECISION est PORTEE
    # (`engine/playbook/noncomparable/burrowers.py`, registre `PLAYBOOKS`). Le CRAN A prend le
    # relais. La dette descend de 15 a 14.
    1026: ("SANS_VERDICT",
           "BasiliskBarragePlaybook -- GenerateAttackPredictionsForShells, MakeDamagePredictions. "
           "COMBAT : BasiliskBarrageAbility (astramilitarum). 5 porteurs (lineup, npc). Sa CLASSE "
           "est deja citee dans `docs/rl/backlog.md`."),
    1032: ("SANS_VERDICT",
           "CatalystPlaybook -- EvaluateNonComparable, GetUseProbability. COMBAT : CatalystAbility "
           "(tyranids). 1 porteur (npc)."),
    1052: ("SANS_VERDICT",
           "CallRipperSwarmsPlaybook -- EvaluateNonComparable, GetMaxSummons. COMBAT : "
           "CallRipperSwarmsAbility (tyranids, #1032). 1 porteur (npc, "
           "tyranBossHiveTyrantLeviathan). L'utilite du corps natif est CONSTANTE (le statique du "
           "`.cctor`), la seule variable etant l'enumeration de `GetEligibleTargetsSelectable` -- "
           "residu #1032-r1."),
    # 1076 `MV71SniperDroneSquadAttack` -- TRANCHE par #1021, ligne RETIREE (et non passee a
    # `TRANCHE`) : le retrait est ce qui la fait tomber sous le CRAN A, donc ce qui la protege
    # DESORMAIS. Attestation `RIEN_A_PORTER` au ledger (c'est une attaque NORMALE concrete, dont le
    # playbook ne surcharge rien) -- si elle perime, l'item rougit au lieu d'etre couvert par une
    # vieille ligne de dette. C'est la trajectoire attendue de chacune des lignes ci-dessous.
    1012: ("SANS_VERDICT",
           "PrecisionShot_AimPlaybook -- EvaluateNonComparable, ShouldEvaluate (+ .ctor, .cctor). "
           "COMBAT : PrecisionShot_AimAbility (necrons), entree au registre par #996-r1-r3. "
           "2 porteurs (npc `necroNpc3Deathmark`, summon `necroSmnDeathmark`). RE AMORCEE : le "
           "`.ctor` est `ComparablePlaybook<T>..ctor(this, 0x3f4)`, `EvaluateNonComparable` batit "
           "UN bucket (`Bucket(0, <statics[0]>)`) et pousse une action par cible eligible avec "
           "l'utilite CONSTANTE `Fix64.FromIntFraction(3, 2)` = 1,5 -- le seul terme variable est "
           "l'enumeration de `BasePlaybook$$GetEligibleTargetsSelectable`. `ShouldEvaluate`, lui, "
           "est SUBSTANTIEL (gate `WillBeKill` sur une prediction, seuil de HP > 0x3c, valeurs "
           "0x50 / 0x14) -- c'est LUI qui porte la decision de viser, et il n'est pas porte. "
           "⚠ Sa soeur `1015 PrecisionShot` est ATTESTEE `RIEN_A_PORTER` au ledger, et ce n'est "
           "PAS transposable : 1015 est la SEULE des 233 actives du dict `+0x68` a retomber sur "
           "`DefaultActiveAbilityPlaybook`, 1012 a bien une classe PROPRE. Residu `#996-r1-r3-r5`."),
    1091: ("SANS_VERDICT",
           "SlashingDivePlaybook -- EvaluateNonComparable. COMBAT : SlashingDiveAbility "
           "(thousandsons). 3 porteurs (npc, summons)."),
    1107: ("SANS_VERDICT",
           "RevealPlaybook -- EvaluateNonComparable (+ .ctor, .cctor). COMBAT : RevealAbility "
           "(loki/reveal.py), entree au registre par #1033. 1 porteur (npc `eldarNpc2Warlock`). "
           "RE DEJA FAITE, residu `#1033-r2` : le corps est COURT et son utilite est CONSTANTE -- "
           "`bucket = Bucket(0, <statics[0]>)` ; `foreach t in BasePlaybook$$"
           "GetEligibleTargetsSelectable(caster, casterPosition.MainTile)` ; "
           "`if (BasePlaybook$$WillNormalAttackKill(caster, t, casterPosition.MainTile)) continue;` "
           "-- on ECARTE les cibles qu'une attaque normale tuerait -- ; "
           "`bucket.AddAction(BasePlaybook$$GenerateAction(casterPosition, t, Fix64(1)))`. "
           "Le `.ctor` passe `0x453` (= 1107) a `ComparablePlaybook<T>..ctor`, mais la methode "
           "propre est `EvaluateNonComparable` -> registre vise "
           "`playbook.noncomparable.PLAYBOOKS` (derivation de `probe_909` etape 4)."),
    # 1108 RETIRE le 2026-08-14 (#940-r2) : la face DECISION est PORTEE
    # (`engine/playbook/noncomparable/kiss_of_death.py`, au registre `PLAYBOOKS`), donc le CRAN A
    # prend le relais -- la laisser en `DETTE` ferait taire le cran sur une ability desormais
    # couverte. Garde : `tests/engine/test_940r2_kiss_of_death_decision_offline.py`.
    1133: ("SANS_VERDICT",
           "WarConstructPlaybook -- EvaluateNonComparable, ShouldEvaluate. COMBAT : "
           "WarConstructAbility (aeldari). 2 porteurs (npc)."),
    # 1159 `MacroPlasmaIncinerator` -- TRANCHE par #1066 (residu #970-r4), ligne RETIREE : sa face
    # DECISION est PORTEE (`engine/playbook/noncomparable/macro_plasma_incinerator.py`, registre
    # `PLAYBOOKS`). Le retrait est ce qui la fait tomber sous le CRAN A -- si le port disparaissait,
    # l'item rougirait au lieu d'etre couvert par une vieille ligne de dette.
    # 1168 `EntropyCannons` -- TRANCHE par #970-r3, ligne RETIREE : attestation `RIEN_A_PORTER` au
    # ledger (son `MakeDamagePredictions` est la forme CANONIQUE -- `h_body` IDENTIQUE a celui de
    # `LashOfTorment`, deja attestee, et de `MightFromBelow`). Le retrait est ce qui la fait tomber
    # sous le CRAN A : si l'attestation perime, l'item rougit au lieu d'etre couvert par une
    # vieille ligne de dette.
    # 1170 `ExplosivePresents` -- TRANCHE par #909-r7, ligne RETIREE : sa face DECISION est PORTEE
    # (`ExplosivePresentsAbility.get_aoe_targets` + `_explosive_presents_inputs`, registres
    # `_SPECIAL_ABILITY_CLASSES` / `_MAKE_DMG_INPUT_OVERRIDES` / `_MAKE_DMG_SELECTOR_ONLY`) et
    # CONFRONTEE au natif sur le porteur REEL `orksRedGobbo` monte par `--explicit-stats` (natif 5
    # evenements, port 1 AVANT le port ; 5 == 5 apres, magnitude comprise). Le retrait est ce qui la
    # fait tomber sous le CRAN A -- si le port disparaissait, l'item rougirait au lieu d'etre
    # couvert par une vieille ligne de dette.
    1173: ("SANS_VERDICT",
           "ArcScourgePlaybook -- EvaluateNonComparable. COMBAT : ArcScourgeAbility (admec). "
           "1 porteur (npc)."),
    1186: ("SANS_VERDICT",
           "WallOfMirrorsPlaybook -- EvaluateNonComparable, GetUseProbability. COMBAT : "
           "WallOfMirrorsAbility (wall_of_mirrors). 2 porteurs (npc, summons)."),
    1193: ("SANS_VERDICT",
           "NovaChargePlaybook -- EvaluateNonComparable, GetUseProbability, ResetCaches, "
           "ShouldEvaluate. COMBAT : NovaChargeAbility (tau, #1032). 1 porteur (npc, "
           "tauBossRiptide). L'utilite du corps natif est `100 * CountEnemiesOnTiles(GetLineTiles) "
           "+ Count(GetLineTiles)` -- elle REUTILISE `NovaChargeAbility$$GetLineTiles`, que la "
           "face COMBAT vient de porter (`tau.nova_charge_line_tiles`) ; residu #1032-r1."),
    # 1200 `SquigLaunchas` -- TRANCHE par #970-r3, ligne RETIREE : sa face DECISION est PORTEE
    # (`engine/playbook/noncomparable/squig_launchas.py`, registre `PLAYBOOKS`). Le retrait est ce
    # qui la fait tomber sous le CRAN A -- si le port disparaissait, l'item rougirait au lieu
    # d'etre couvert par une vieille ligne de dette.
    # 1211 `RitesOfMorkai` -- TRANCHE par #1066 (residus #906-r1 / #985-r1), ligne RETIREE : sa
    # face DECISION est PORTEE (`engine/playbook/noncomparable/rites_of_morkai.py`, registre
    # `PLAYBOOKS`), gate `ShouldEvaluate` compris. Le retrait est ce qui la fait tomber sous le
    # CRAN A -- si le port disparaissait, l'item rougirait au lieu d'etre couvert par une vieille
    # ligne de dette.
}


# ============================================================================================
#  La mesure
# ============================================================================================

class MesureRefusee(RuntimeError):
    """Impossible de MESURER. Jamais rabattu sur un resultat vide (meme discipline que
    `coverage_attestations.build_courant` et `host_inputs` : un capteur muet ne vaut pas zero)."""


def mesurer() -> dict:
    """`{id: {"nom", "etat", "detail", "classe", "module"}}` pour tout `ABILITY_CLASSES`.

    L'etat vient de `decision_face_voies.etat` -- le FOYER UNIQUE, celui que lisent deja
    `probe_909`, `audit_kit_coverage` et `audit_npc_registry`. Un cran dont le predicat divergerait
    de celui de l'audit ne garderait rien : c'est exactement le vice que #979 a ferme (3 registres
    ici, 4 la-bas, 22 % de sur-comptage)."""
    noms = EM.ACTIVE_ABILITY_TYPE
    tables, att = DFV.voies_par_ability(), DFV.attestations()
    out = {}
    for aid, cls in ABILITY_CLASSES.items():
        aid = int(aid)
        nom = noms.get(aid)
        if nom is None:
            out[aid] = {"nom": None, "etat": "HORS MIRROR", "detail": "",
                        "classe": cls.__name__, "module": cls.__module__.rsplit(".", 1)[-1]}
            continue
        etat, detail = DFV.etat(aid, nom, tables, att)
        out[aid] = {"nom": nom, "etat": etat, "detail": detail,
                    "classe": cls.__name__, "module": cls.__module__.rsplit(".", 1)[-1]}
    return out


def sans_verdict(mes: dict) -> list:
    """Les ids du registre COMBAT dont la face DECISION n'a AUCUN verdict. Tries."""
    return sorted(a for a, v in mes.items() if v["etat"] == "NON PORTEE")


def hors_registre_sans_verdict() -> list:
    """Les actives de l'enum COMPLET sans verdict et ABSENTES d'`ABILITY_CLASSES`.

    C'est la PORTEE du cran, derivee et non supposee : un recenseur ne peut pas rendre zero sur ce
    qu'il ne visite pas. Ces ids-la ne sont gardes par RIEN ici -- leur face COMBAT n'etant pas
    portee, ils n'entrent pas dans la population."""
    noms = EM.ACTIVE_ABILITY_TYPE
    tables, att = DFV.voies_par_ability(), DFV.attestations()
    dedans = {int(a) for a in ABILITY_CLASSES}
    out = []
    for aid, nom in noms.items():
        if int(aid) in dedans:
            continue
        etat, _d = DFV.etat(int(aid), nom, tables, att)
        if etat == "NON PORTEE":
            out.append((int(aid), nom))
    return sorted(out)


# ============================================================================================
#  Les trois crans
# ============================================================================================

def crans(mes: dict) -> dict:
    """Les trois crans + le canal de PROGRES. Aucun d'eux ne compare un compte a un nombre."""
    manque = sans_verdict(mes)
    porte_un_verdict = {a for a, v in mes.items() if v["etat"] in ("PORTEE", "CONSTANTE")}

    # CRAN A -- anti-cadence. Un id sans verdict qui n'est pas dans la dette est une REGRESSION :
    # il a ete livre au registre COMBAT sans que personne ne dise ce qu'il en est de la DECISION.
    a = [i for i in manque if i not in DETTE]

    # CRAN B -- anti-regression sur les acquis. Un id declare TRANCHE doit AVOIR son verdict ; sans
    # ce cran, un item solde puis re-casse resterait couvert par sa vieille ligne de dette.
    b = [i for i, (etat, _r) in sorted(DETTE.items())
         if etat == "TRANCHE" and i not in porte_un_verdict]

    # CRAN C -- la mesure doit MESURER. Un cliquet qui ne visite rien rend vert pour rien : on
    # assertionne le non-vide de chaque entree AVANT de conclure quoi que ce soit.
    hors_mirror = sorted(a2 for a2, v in mes.items() if v["etat"] == "HORS MIRROR")
    etats_inconnus = sorted({etat for etat, _r in DETTE.values()} - set(ETATS))
    c = []
    if not mes:
        c.append("`ABILITY_CLASSES` est VIDE -- rien n'a ete visite")
    if not EM.ACTIVE_ABILITY_TYPE:
        c.append("le mirror `ACTIVE_ABILITY_TYPE` est VIDE -- aucun nom n'aurait resolu")
    if not DFV.VOIES:
        c.append("`decision_face_voies.VOIES` est VIDE -- tout serait rendu NON PORTEE")
    if not porte_un_verdict:
        c.append("AUCUN id du registre ne porte de verdict -- le predicat est casse, pas la dette")
    if hors_mirror:
        c.append("%d id(s) d'`ABILITY_CLASSES` hors du mirror `ACTIVE_ABILITY_TYPE` : %s -- on ne "
                 "visite pas ce qu'on croit visiter" % (len(hors_mirror), hors_mirror))
    if etats_inconnus:
        c.append("etat(s) de dette inconnu(s) : %s -- admis : %s"
                 % (etats_inconnus, ", ".join(ETATS)))

    # PROGRES -- jamais rouge. Une dette qui descend est un succes : on l'IMPRIME.
    progres = [i for i, (etat, _r) in sorted(DETTE.items())
               if etat == "SANS_VERDICT" and i in porte_un_verdict]
    # Une ligne de dette pour un id qui n'est PLUS au registre COMBAT est de la scorie, pas une
    # faute : elle ne couvre plus rien. Imprimee, jamais rouge.
    orphelines = [i for i in sorted(DETTE) if i not in mes]
    return {"A": a, "B": b, "C": c, "progres": progres, "orphelines": orphelines,
            "manque": manque, "verdicts": porte_un_verdict}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--tout", action="store_true", help="imprimer aussi les ids qui ont un verdict")
    args = ap.parse_args()

    mes = mesurer()
    k = crans(mes)
    noms = EM.ACTIVE_ABILITY_TYPE

    print("[1021] POPULATION -- le registre de la face COMBAT")
    print("   ABILITY_CLASSES                       : %d" % len(mes))
    par_etat = collections.Counter(v["etat"] for v in mes.values())
    for etat in ("PORTEE", "CONSTANTE", "NON PORTEE", "HORS MIRROR"):
        if par_etat.get(etat):
            print("   face DECISION %-24s: %d" % (etat, par_etat[etat]))
    print("   dette DECLAREE                        : %d (%s)"
          % (len(DETTE), ", ".join("%s=%d" % (e, n) for e, n in
                                   sorted(collections.Counter(x for x, _ in DETTE.values()).items()))))

    print("\n[1021] LES SANS-VERDICT (%d)" % len(k["manque"]))
    for aid in k["manque"]:
        v = mes[aid]
        etat_d = DETTE.get(aid, ("HORS DETTE", ""))[0]
        print("   %-6d %-30s %-38s %-16s %s"
              % (aid, v["nom"], v["classe"], v["module"], etat_d))

    if args.tout:
        print("\n[1021] LES IDS QUI PORTENT UN VERDICT (%d)" % len(k["verdicts"]))
        for aid in sorted(k["verdicts"]):
            v = mes[aid]
            print("   %-6d %-30s %-10s %s" % (aid, v["nom"], v["etat"], v["detail"]))

    print("\n[1021] PORTEE DE LA MESURE -- ce que ce cran NE VOIT PAS")
    hors = hors_registre_sans_verdict()
    print("   actives SANS VERDICT et hors `ABILITY_CLASSES` : %d sur %d membres du mirror"
          % (len(hors), len(noms)))
    print("      (leur face COMBAT n'est pas portee, donc elles n'entrent pas dans la population "
          "de ce cran -- il ne les garde PAS)")
    for aid, nom in hors[:8]:
        print("      %-6d %s" % (aid, nom))
    if len(hors) > 8:
        print("      ... %d de plus" % (len(hors) - 8))
    print("   faces TRIGGERED / NON-OWNER / SPECIFIC : hors axe (dicts +0x88, +0x98, +0xa8 de")
    print("      `IdunBattle.AI.PlaybookDatabase` -- inventaires case-419, case-433-r4-r3,")
    print("      case-477r33/r35/r37)")
    print("   la FIDELITE d'un verdict PORTEE n'est pas evaluee, seulement son EXISTENCE.")

    if k["progres"]:
        print("\n[1021] DETTE REDUCTIBLE -- %d id(s) declare(s) SANS_VERDICT ont ACQUIS leur verdict"
              % len(k["progres"]))
        for aid in k["progres"]:
            print("   %-6d %-30s %s -- retirer la ligne de `DETTE` (ou la passer a `TRANCHE`)"
                  % (aid, mes[aid]["nom"], mes[aid]["etat"]))
        print("   Ce n'est PAS une faute : une dette qui descend est un succes. Le CRAN A prend le")
        print("   relais des que la ligne est retiree.")
    if k["orphelines"]:
        print("\n[1021] LIGNES DE DETTE ORPHELINES -- %d id(s) ne sont plus dans `ABILITY_CLASSES`"
              % len(k["orphelines"]))
        for aid in k["orphelines"]:
            print("   %-6d %s -- ne couvre plus rien, a retirer" % (aid, noms.get(aid, "?")))

    print("\n[1021] CRAN A (aucun sans-verdict hors du registre de dette) : %s"
          % ("OK" if not k["A"] else "FAUTE (%d)" % len(k["A"])))
    for aid in k["A"]:
        v = mes[aid]
        print("   MANQUANT %-6d %-30s %-38s %s"
              % (aid, v["nom"], v["classe"], v["module"]))
    if k["A"]:
        print("   => Cette active est entree dans `ABILITY_CLASSES` (face COMBAT portee) sans")
        print("      qu'aucun verdict ne dise ce qu'il en est de sa face DECISION. Trois issues,")
        print("      et << je verrai plus tard >> n'en est pas une :")
        print("        1. PORTER l'utilite -- l'ability entre dans une voie de")
        print("           `decision_face_voies.VOIES` (le nom de la methode propre du `<X>Playbook`")
        print("           natif dit laquelle : `EvaluateNonComparable` -> `noncomparable.PLAYBOOKS`,")
        print("           `MakeDamagePredictions` -> `_SPECIAL_ABILITY_CLASSES`) ;")
        print("        2. ATTESTER `RIEN_A_PORTER` au ledger `coverage_attestations` (categorie")
        print("           `active-decision`) -- verdict LU au corps natif, avec sa source, son")
        print("           build et son ancrage. C'est un RESULTAT, pas un aveu ;")
        print("        3. ATTESTER `PORTE_HORS_REGISTRE` si le mecanisme vit sans registre --")
        print("           `porteur` = `module:symbole`, verifie resolvable.")
        print("      Sans verdict, l'unite s'execute fidelement mais est CHOISIE par le chemin")
        print("      generique : degradation MUETTE, invisible en replay.")

    print("[1021] CRAN B (les ids declares TRANCHE portent toujours leur verdict) : %s"
          % ("OK" if not k["B"] else "FAUTE (%d)" % len(k["B"])))
    for aid in k["B"]:
        print("   REGRESSION %-6d %-30s declare TRANCHE, etat mesure = %s"
              % (aid, noms.get(aid, "?"), mes.get(aid, {}).get("etat", "ABSENT DU REGISTRE")))

    print("[1021] CRAN C (la mesure mesure : population, mirror, voies, verdicts non vides) : %s"
          % ("OK" if not k["C"] else "FAUTE (%d)" % len(k["C"])))
    for m in k["C"]:
        print("   %s" % m)

    ok = not k["A"] and not k["B"] and not k["C"]
    print("[1021] VERDICT : %s" % ("OK" if ok else "FAUTES"))
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
