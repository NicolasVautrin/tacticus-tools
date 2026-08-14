"""Audit de la couverture moteur PAR KIT (unites lineup) — vue "kits restants a porter".

Complement KIT-centrique de `audit_combat_ability_coverage.py` (#95, vue par-ability) : pour
chaque unite LINEUP (jouable en walk), croise son kit gameconfig complet avec les registres
moteur des deux faces :

  FACE COMBAT (execution) :
    - actives  -> `engine.runner.abilities.handler.ABILITY_CLASSES` (id ActiveAbilityType)
    - passives, traits, voies conditionnelles -> `kit_item_voies.etat` -- le FOYER UNIQUE (#1041),
      qui PARTITIONNE le perimetre `engine/runner` + `effects/factory.py` + `engine/services` au
      lieu d'ENUMERER des registres. Cet audit y est venu apres avoir tenu sa PROPRE liste blanche
      de cinq registres, qui avait rate `EFFECT_TRIGGERS` -- et donc rendu `PhoenixGem`
      (`eldarAutarch`) << non portee >> alors que ses trois classes y vivent sous
      `EffectType.PhoenixGem_CanRevive`. Le foyer ne les ENUMERE plus : un conteneur neuf y sort
      MUET au lieu d'etre tu, et le cliquet rougit.
      ⚠ Ce foyer rend un TRI-ETAT, pas un booleen : cf. la section suivante.
  FACE DECISION (scoring) : `decision_face_voies.face_portee` — le FOYER UNIQUE (#979), partage
    avec `probe_909_decision_actives_kit.py`. Cet audit y est venu apres avoir tenu sa PROPRE liste
    blanche de registres, qui divergeait de celle du probe (4 ici, 3 la-bas) et qui a rate deux
    voies MESUREES : `BESPOKE_SELFCAST` (#971 -- 3 faux GAP, dont `1179 CultDemagogue` sur lequel
    un agent a ete redispatche) puis `_MAKE_DMG_INPUT_OVERRIDES` (#974). Le foyer ne les ENUMERE
    plus : il PARTITIONNE le perimetre `engine/playbook/**` + `active_ability.py`, de sorte qu'un
    conteneur neuf y sorte MUET au lieu d'etre tu.
    Le reste de la voie comparable est generique et n'est pas audite ici.

    ⚠ `_NONCOMPARABLE_ABILITIES` n'est PAS un 4e registre de couverture : y figurer dit seulement
    que le port CLASSE l'ability NonComparable (donc s'interdit de fabriquer un degat depuis
    minDmg/maxDmg) ; son UTILITE de decision vit dans `PLAYBOOKS`. L'audit le signale a part
    (« NC classee, utilite NC non portee ») au lieu de le compter comme `D` -- sinon on commet
    l'erreur SYMETRIQUE du sous-comptage, en declarant porte ce qui ne l'est pas.

LE TRI-ETAT `PORTE` / `PARTIEL` / `ABSENT` (#1041), et pourquoi le booleen d'avant etait FAUX DES
DEUX COTES. Deux vices tiraient en sens OPPOSES, et ne corriger que l'un DEGRADAIT le chiffre :
  * SOUS-comptage -- la liste blanche ne visitait pas `EFFECT_TRIGGERS` : `PhoenixGem`, portee en
    entier (3 classes, 17 tests live), etait comptee du travail a faire ;
  * SUR-comptage -- une entree d'`ABILITY_INIT_OWNER_EFFECTS` creditait l'item MEME QUAND l'effet
    pose n'a AUCUNE CLASSE dans `EFFECT_CLASSES`. Le montage est alors DECLARE et il ne s'execute
    RIEN. Mesure : 4 mythiques (`BlightedLand`, `CabalOfSorcerers`, `GuardianConstruct`,
    `MoreGitzOverEre`) etaient dans ce cas -- ce sont EXACTEMENT les 4 entrees du registre dont
    aucune cible n'a de classe. `audit_passive_ability_coverage` appliquait DEJA ce gate a son
    canal `[O]` ; les deux audits divergeaient sur la meme question.
`PARTIEL` est donc rendu TEL QUEL, jamais arrondi : le rabattre sur PORTE fait RENONCER a du
travail reel, le rabattre sur ABSENT fait RE-DISPATCHER un port a moitie fait.
⚠ `missing` COMPTE LES PARTIELS comme du travail restant (c'en est), et la section conditionnelle
les liste a part -- un chiffre qui change de sens doit etre ANNONCE, pas glisse.

APPROXIMATIONS assumees (l'audit RANGE les kits par volume de travail, il ne PROUVE pas une
couverture) : un passif peut etre implemente ailleurs (mod attaquant, effet, legalite) sans
figurer dans ces registres -> faux "MISSING" possibles, a trancher au recon du kit. Le tri-etat
mesure la PRESENCE d'un cablage et la vivacite de sa cible, JAMAIS sa fidelite : un item `PORTE`
peut l'etre faussement.

VOIES D'ATTRIBUTION (#341, apres le precedent #323). Le kit d'une unite s'atteint par CINQ voies
derivables du gameconfig (`unit_map.VOIE_KEYS`). Le corps de cet audit n'en lit que DEUX
(`activeAbilities`, `passiveAbilities`) + les traits. Les deux autres qui touchent une unite
`lineup` -- `mythicAbilities` et la relique EQUIPABLE `items[*].abilityId` + `allowedUnits` --
sont desormais LUES et rendues dans une section a part, **hors du total** :
  * hors total parce que leur nature differe -- une mythique se DEBLOQUE, une relique s'EQUIPE ;
    les fondre dans le compte ferait remonter en tete du classement un heros riche en reliques
    equipables dont le KIT, lui, est porte ;
  * mais IMPRIMEES, jamais tues : mesure #341 = **43 abilities**, **0 couverte** par un registre.
    Les taire reproduisait exactement la cecite qui a fait rendre un faux « 0 unite, DEAD » a
    `unit_map find --ability` (`docs/rl/case-323-unit-map-attribution-voies.md`).
La voie `relicAbilities` ne touche AUCUNE unite `lineup` (0 mesure) ; les voies `trait`,
`liveevent`, `summon`, `tile` ne sont derivables d'aucune source offline (cf. `case-323` §2).

ORDRE DE SORTIE : les sections detaillees sont ordonnees par NOM de faction, pas par volume. Le
classement par volume vit dans la table de bilan en tete. Motif (#341) : trie par volume, le doc
REORDONNE des sections entieres des qu'un seul compte bouge -- le dernier delta valait 58 lignes
pour 3 changements de fond, et c'est ce bruit qui a fait renoncer trois agents d'affilee a le
regenerer.

Genere `docs/rl/kit-coverage.md`. A relancer apres tout port / changement de build.
Usage : depuis `scripts/python/`  ->  `python audit_kit_coverage.py`
"""
from __future__ import annotations

import os
import sys
from collections import Counter, defaultdict

_PYROOT = os.path.dirname(os.path.abspath(__file__))
_REPO = os.path.dirname(os.path.dirname(_PYROOT))
if _PYROOT not in sys.path:
    sys.path.insert(0, _PYROOT)

import coverage_attestations as CA
import decision_face_voies as DFV     # #979 : foyer UNIQUE des voies de face DECISION
import enum_maps as EM
import gameconfig as GC
import unit_map as UM
import kit_item_voies as KIV        # #1041 : foyer UNIQUE des voies de montage COMBAT d'un item
from audit_combat_ability_coverage import _classify
from engine.entities.abilities.active_ability import (   # 3e registre de decision, keye par NOM
    _NONCOMPARABLE_ABILITIES, _SPECIAL_ABILITY_CLASSES,
)
from engine.playbook import REGISTRY as CUSTOM_PLAYBOOKS   # comparables a override CalculateCustomUtility
from engine.playbook.bespoke import BESPOKE_SELFCAST       # 4e registre : override TOTAL d'EvaluateInternal
from engine.playbook.noncomparable import PLAYBOOKS
from engine.runner.abilities.handler import ABILITY_CLASSES
# ⚠ LES SIX REGISTRES DE COUVERTURE D'ITEM NE SONT PLUS IMPORTES ICI, ET C'EST LE FOND DE #1041.
# Les lire d'ici, c'etait tenir une LISTE BLANCHE -- elle en avait deja rate cinq, chacun paye par
# un faux MANQUANT mesure, et le sixieme (`EFFECT_TRIGGERS`) a fait sortir `PhoenixGem` en
# << non portee >> alors qu'elle est portee en entier. Le foyer PARTITIONNE le perimetre a la
# place ; y ajouter un import ici RE-OUVRIRAIT le gisement.

OUT = os.path.join(_REPO, "docs", "rl", "kit-coverage.md")

# ⚠ `TRAIT_COMMON_MAX` A DISPARU (#1015). C'etait un SEUIL DE FREQUENCE (12 porteurs) qui ECARTAIT
# 22 traits du compte en les declarant « presumes couverts par les couches globales ». Un trait
# frequent n'est pas un trait couvert : la mesure a rendu **3 des 22 presumes** LUS NULLE PART dans
# `engine/**` -- `InstinctiveBehaviour` (23 porteurs), `Healer` (18), `CloseCombatWeakness` (16) --
# alors que les trois portent une mecanique de combat explicite. Le seuil ne mesurait rien, il
# supposait ; et comme tout seuil, il se degradait en silence a mesure que le travail avancait.
#
# Ce qui l'a remplace : `trait_channels.canaux()`, un foyer qui PARTITIONNE. Tout trait porte y sort
# dans exactement un etat, avec le CANAL qui l'y met et les SITES qui l'etablissent ; un canal
# inconnu sortirait sous son nom au lieu d'etre absorbe en « non couvert ». Le compte n'ecarte plus
# personne -- il repond, trait par trait, a « le port sait-il l'evaluer, et par quel canal ? ».
import trait_channels as TC

# Voies d'attribution qui touchent une unite `lineup` sans figurer sur `activeAbilities` /
# `passiveAbilities` (#323). Elles sont CONDITIONNELLES (a debloquer / a equiper) -> comptees a
# part, jamais fondues dans le total, mais jamais tues non plus.
VOIES_CONDITIONNELLES = ("mythic", "item")

#: Les VERDICTS attestes (#951-r2), charges UNE fois. Cle = `(categorie, nom)`. Seules les
#: attestations VALIDES y figurent : `coverage_attestations.validite` est le foyer UNIQUE, et une
#: attestation perimee n'arrive simplement jamais jusqu'ici -- l'item reste donc compte manquant.
_ATTESTEES = CA.attestations_valides()

#: Les VOIES de face DECISION, resolues UNE fois (#979). Le foyer PARTITIONNE le perimetre au lieu
#: d'enumerer des registres : un conteneur neuf y sort MUET, et `probe_909` etape 6 rougit.
_VOIES = DFV.voies_par_ability()

#: ⚠ PAS D'INSTANTANE A L'IMPORT pour les voies d'ITEM, contrairement a `_VOIES` ci-dessus -- et
#: c'est une correction MESUREE, pas une precaution. Un instantane fige rend le predicat
#: INSENSIBLE a une mutation de registre : trois etages de
#: `test_951r2_voies_de_couverture_offline` (qui RETIRENT une entree et exigent que la couverture
#: TOMBE) sont passes au ROUGE. Un recenseur qu'on ne peut plus faire mentir ne prouve plus rien.
#: Les BOUCLES calculent donc la table une fois, localement (`collect`, `collect_conditionnelles`),
#: et le predicat public relit -- `kit_item_voies.items_de_kit` porte le seul cache, sur le
#: GAMECONFIG, qui lui ne mute pas.


def _atteste(categorie: str, nm: str) -> dict | None:
    """L'attestation VALIDE de cet item, s'il en a une (#951-r2).

    ⚠ Ce n'est PAS une liste blanche : le foyer `coverage_attestations.validite` exige une raison
    ECRITE, une source qui EXISTE, le build COURANT, et un ancrage VERIFIABLE (le cliquet qui garde
    le verdict, et/ou le symbole qui porte le mecanisme). Toute clause qui tombe rend l'attestation
    PERIMEE, donc REMET l'item au compte -- la peremption ne sait que RAJOUTER du travail."""
    return _ATTESTEES.get((categorie, nm))


def _etat_item(nm: str, table=None) -> tuple[str, str]:
    """L'etat TERNAIRE de couverture d'un item NON-actif (passif, trait, mythique, relique) :
    `("PORTE"|"PARTIEL"|"ABSENT", detail)`. Delegue au FOYER `kit_item_voies` (#1041).

    `table` = l'instantane des voies, que les BOUCLES calculent une fois. Sans elle, le foyer
    RELIT les registres -- c'est ce qui garde le predicat sensible a leur mutation (cf. le
    commentaire de `_VOIES` plus haut : un instantane a l'import desarmait trois etages de garde).

    ⚠ CE PREDICAT ETAIT UNE LISTE BLANCHE DE CINQ REGISTRES, et il en avait rate un : une liste
    blanche ne peut pas montrer le registre qu'elle a oublie. Chacune de ses extensions passees
    avait ete payee par un faux MANQUANT MESURE -- `DawnBlade` (`RELIC_ABILITY_TRIGGERS`, #951-r2),
    `FireOfAbsolution` (`IMPERATIVE_ABILITY_VECTORS`, #951-r2), `Boltstorm` et ses voisins
    (`CUSTOM_NORMAL_ATTACK_BY_PASSIVE`, #925), `MartialKatah` (`TRAIT_OWNER_EFFECTS`). Le sixieme
    trou etait `EFFECT_TRIGGERS` (`PhoenixGem`, #1041) -- et le suivant serait arrive pareil.
    Le foyer PARTITIONNE : un registre qui naitrait demain y sort MUET, et le cliquet rougit.

    L'ATTESTATION (`_atteste`) n'est PAS testee ici : elle est deliberement tenue HORS de ce
    predicat, parce qu'elle ne dit pas la meme chose. Ce predicat repond a « un registre le
    porte-t-il ? » ; l'attestation repond a « ce verdict a-t-il ete ETABLI ? ». Les fondre rendrait
    les deux indiscernables dans le doc, et c'est precisement ce qu'on veut pouvoir lire."""
    return KIV.etat(nm, table)


def _passive_covered(nm: str) -> bool:
    """Compatibilite : `True` seulement si l'item est PLEINEMENT porte. Un `PARTIEL` rend `False`
    -- c'est du travail restant, et le rabattre sur `True` fait RENONCER. Les appelants qui
    veulent DISTINGUER les deux lisent `_etat_item`."""
    return _etat_item(nm)[0] == KIV.PORTE


def collect_conditionnelles(name2id: dict) -> list[dict]:
    """Les abilities qui atteignent une unite `lineup` par une voie CONDITIONNELLE (#341).

    Rend une ligne PAR ABILITY (et non par unite) : 43 abilities pour 76 couples unite-ability,
    la vue par ability est celle qui dit « ce mecanisme est-il branche », qui est la question.
    `couverte` applique les DEUX predicats -- une relique peut etre une active (`Maugetar` est
    portee en `activeAbilities` par un npc) autant qu'un passif."""
    carriers: dict[tuple[str, str], set] = defaultdict(set)
    for k in UM.all_kits():
        if k.get("kind") != "lineup":
            continue
        for voie in VOIES_CONDITIONNELLES:
            for nm in (k.get("voies") or {}).get(voie, []):
                carriers[(nm, voie)].add(k["id"])
    voies_item = KIV.voies_par_item()      # UNE fois par appel, jamais fige a l'import
    out = []
    for (nm, voie), units in carriers.items():
        aid = name2id.get(nm)
        att = _atteste("conditionnelle-" + voie, nm)
        et, detail = _etat_item(nm, voies_item)
        # Une active portee et une attestation valide valent PORTE : les trois signaux disent la
        # meme chose (« il n'y a plus rien a faire ici »). Le `PARTIEL`, lui, n'est ABSORBE par
        # aucun des deux -- s'il l'etait, la face manquante redeviendrait invisible.
        if aid is not None and aid in ABILITY_CLASSES:
            et, detail = KIV.PORTE, "ABILITY_CLASSES"
        elif att is not None and et != KIV.PARTIEL:
            et, detail = KIV.PORTE, "atteste"
        out.append({
            "name": nm, "voie": voie, "id": aid, "carriers": sorted(units), "atteste": att,
            "etat": et, "detail": detail, "covered": et == KIV.PORTE,
        })
    return sorted(out, key=lambda r: (r["covered"], r["voie"], r["name"]))


def collect():
    name2id = {v: k for k, v in EM.ACTIVE_ABILITY_TYPE.items()}
    voies_item = KIV.voies_par_item()      # UNE fois par appel, jamais fige a l'import
    trait_units: Counter = Counter()
    for k in UM.all_kits():
        u = GC.unit(k["id"]) or {}
        for t in (u.get("traits") or []):
            trait_units[t] += 1

    rows = []
    for k in UM.all_kits():
        if k.get("kind") != "lineup":
            continue
        u = GC.unit(k["id"]) or {}
        actives = []
        for nm in (u.get("activeAbilities") or []):
            aid = name2id.get(nm)
            att_c, att_d = _atteste("active-combat", nm), _atteste("active-decision", nm)
            actives.append({
                "name": nm, "id": aid, "cat": _classify(nm),
                "combat": aid in ABILITY_CLASSES or att_c is not None,
                "atteste_combat": att_c, "atteste_decision": att_d,
                # 3e registre, keye par NOM et non par id : `_SPECIAL_ABILITY_CLASSES` mirror une
                # sous-classe `AActiveAbility` PAR ability (formule de coups propre, AoE, degat
                # conditionnel), consommee uniquement sous `engine/playbook/prediction/` — c'est
                # donc bien de la face DECISION, et l'ignorer produisait des `[--]` faux (mesure :
                # 14 `[-D]` affiches pour 20 reels).
                # #951-r2 : une ability dont le playbook natif n'a AUCUN contenu propre est portee
                # par le chemin GENERIQUE -- il n'y a rien a ecrire, et la compter manquante fait
                # RE-DISPATCHER un agent (mesure : `1204 LeadingTheCharge`, verdict verrouille par
                # #945). Ce n'est PAS une exception codee en dur : c'est une attestation VALIDE
                # (raison + source + build + ancrage), qui PERIME des que le sujet bouge.
                # 4e registre : `BESPOKE_SELFCAST` (`engine/playbook/bespoke.py`). Une COMPARABLE
                # qui override `EvaluateInternal` EN ENTIER n'entre NI dans `REGISTRY` (elle n'a pas
                # d'override `CalculateCustomUtility`) NI dans `PLAYBOOKS` (elle n'est pas
                # NonComparable) : elle est dispatchee par `_bespoke_candidates`. Les 3 ids qu'il
                # porte sortaient donc en GAP alors qu'ils sont portes -- et `1179 CultDemagogue`
                # a ete redispatchee sur cette foi (#971).
                # #979 : CETTE LISTE A DISPARU. Elle en etait a QUATRE registres quand le probe
                # frere en lisait TROIS -- deux listes blanches divergentes pour la meme question,
                # et il en manquait encore. L'appartenance vient desormais de
                # `decision_face_voies.face_portee` (14 voies PARTITIONNEES, pas enumerees), foyer
                # UNIQUE partage avec `probe_909`. L'attestation reste sommee ici : une ability
                # portee HORS registre (generateur bespoke appele en dur) n'a aucun conteneur ou
                # figurer.
                "decision": bool(DFV.face_portee(aid, nm, _VOIES)) or att_d is not None,
                # `_NONCOMPARABLE_ABILITIES` NE COMPTE PAS comme decision portee, et c'est
                # deliberé : y figurer signifie seulement que le port CLASSE l'ability
                # NonComparable — ce qui l'empeche de fabriquer un degat depuis minDmg/maxDmg. Son
                # UTILITE, elle, vit dans `playbook.noncomparable.PLAYBOOKS`. Compter les deux
                # ensemble ferait l'erreur SYMETRIQUE du sous-comptage : `HammerOfWrath` passerait
                # pour porte alors que son propre commentaire dit l'utilite NC « reste a porter ».
                "nc_unported": nm in _NONCOMPARABLE_ABILITIES and aid not in PLAYBOOKS,
            })
        passives = []
        for nm in (u.get("passiveAbilities") or []):
            att = _atteste("passif", nm)
            et, detail = _etat_item(nm, voies_item)
            # Meme regle que pour les conditionnelles : une attestation VALIDE vaut PORTE, mais elle
            # n'absorbe PAS un `PARTIEL` -- une face manquante ne s'atteste pas par un verdict pose
            # sur une AUTRE face.
            if att is not None and et != KIV.PARTIEL:
                et, detail = KIV.PORTE, "atteste"
            passives.append({"name": nm, "covered": et == KIV.PORTE, "atteste": att,
                             "etat": et, "detail": detail})
        kit_traits = []
        for t in (u.get("traits") or []):
            # AUCUN ECART (#1015) : le seuil de frequence est retire, tout trait porte est compte et
            # rend son CANAL. Un trait tres repandu qui n'est evalue nulle part est desormais VISIBLE
            # au lieu d'etre presume couvert -- c'etait le cas de 3 des 22 qu'ecartait le seuil.
            att = _atteste("trait", t)
            cx = TC.canaux(t)
            kit_traits.append({
                "name": t, "carriers": trait_units[t], "atteste": att,
                "canaux": cx, "sites": len(TC.sites(t)),
                "covered": bool(cx) or att is not None,
            })
        missing = (sum(1 for a in actives if not a["combat"])
                   + sum(1 for p in passives if not p["covered"])
                   + sum(1 for t in kit_traits if not t["covered"]))
        rows.append({
            "id": k["id"], "faction": u.get("FactionId") or "?",
            "actives": actives, "passives": passives, "traits": kit_traits,
            "missing": missing,
        })
    return rows


def _fmt_active(a: dict) -> str:
    face = ("C" if a["combat"] else "-") + ("D" if a["decision"] else "-")
    tag = "OK" if a["combat"] else "NO-OP %s" % a["cat"]
    if a["nc_unported"]:
        tag += " ; NC classee, utilite NC non portee"
    return "%s(%s) [%s] %s" % (a["name"], a["id"] if a["id"] is not None else "?", face, tag)


def main():
    rows = collect()
    cond = collect_conditionnelles({v: k for k, v in EM.ACTIVE_ABILITY_TYPE.items()})
    done = [r for r in rows if r["missing"] == 0]
    # Tri par ID, pas par volume : une unite qui passe de 2 items a 1 ne doit pas CHANGER DE PLACE
    # dans sa table -- sinon un port isole produit deux hunks de diff distants au lieu d'un seul.
    # Le volume reste lisible en colonne `manque`, et la priorisation vit dans la table de bilan.
    todo = sorted((r for r in rows if r["missing"] > 0),
                  key=lambda r: (r["faction"], r["id"]))
    by_faction: dict[str, list] = defaultdict(list)
    for r in todo:
        by_faction[r["faction"]].append(r)
    total = sum(r["missing"] for r in todo)
    cond_open = [c for c in cond if not c["covered"]]
    # Le TRI-ETAT (#1041). `PARTIEL` est un sous-ensemble de `cond_open` -- il RESTE compte comme
    # du travail (c'en est), mais il est NOMME : c'est ce que le booleen d'avant ne pouvait pas
    # dire, et c'est ce qui distingue « personne n'a rien ecrit » de « le montage est ecrit et il
    # ne s'execute rien ».
    cond_partiels = [c for c in cond_open if c["etat"] == KIV.PARTIEL]
    passifs_partiels = sorted({p["name"] for r in rows for p in r["passives"]
                               if p["etat"] == KIV.PARTIEL})

    # LA FACE DECISION EST CALCULEE MAIS NE COMPTE PAS DANS `missing` (cf. `collect`,
    # qui ne somme que `not a["combat"]`). Ce n'est pas un bug a corriger en douce :
    # redefinir `missing` changerait le sens du chiffre que tout le monde cite. Mais
    # taire le trou l'a rendu INVISIBLE -- le marqueur `[C-]` n'est rendu que dans la
    # section << kits avec du travail >>, donc une ability sans face DECISION vivant
    # dans un kit declare COMPLET n'etait imprimee NULLE PART.
    # Mesure du 2026-08-11 : 59 actives sur 138 sans face DECISION, dont 42 dans 36
    # des 91 kits << complets >>. On les compte a part, et on les LISTE.
    n_actives = sum(len(r["actives"]) for r in rows)
    deci_open = [(r, a) for r in rows for a in r["actives"] if not a["decision"]]
    deci_masquees = [(r, a) for (r, a) in deci_open if r["missing"] == 0]
    kits_masques = sorted({r["id"] for (r, _a) in deci_masquees})

    lines = []
    lines.append("# Couverture moteur par KIT (unites lineup)\n\n")
    lines.append("> Genere par `scripts/python/audit_kit_coverage.py` (kit gameconfig x registres moteur\n"
                 "> des deux faces). Vue KIT-centrique complementaire de `combat-ability-coverage.md`\n"
                 "> (par-ability). **Ne jamais fusionner un conflit sur ce fichier : le REGENERER.**\n"
                 ">\n"
                 "> Faces : `[CD]` = combat/decision portees, `[--]` = aucune ; `D` couvre les TROIS\n"
                 "> registres de scoring (non-comparables + overrides custom des comparables +\n"
                 "> sous-classes `AActiveAbility` par ability). La mention « NC classee, utilite NC non\n"
                 "> portee » marque une ability reconnue NonComparable dont l'utilite reste a porter :\n"
                 "> c'est un travail restant, pas une face couverte. Les MISSING passifs/traits sont des\n"
                 "> CANDIDATS (approximation registres, cf. docstring du script) : trancher au recon du kit.\n"
                 ">\n"
                 "> **Ce que le total compte** : les items du kit INTRINSEQUE (`activeAbilities`,\n"
                 "> `passiveAbilities`, traits de kit). **Ce qu'il ne compte pas** : les voies\n"
                 "> CONDITIONNELLES (mythique a debloquer, relique a equiper) — elles ont leur propre\n"
                 "> section, chiffree, en fin de document. ⚠ CONDITIONNEL vaut pour le JEU, pas pour le\n"
                 "> HARNAIS : les deux voies se MONTENT en runner (`--equip-relic` #237,\n"
                 "> `--equip-mythic` #999) et 2 des 11 mythiques sont confrontees en live (#1024).\n"
                 "> Les voies `trait`/`liveevent`/`summon`/`tile`\n"
                 "> ne sont derivables d'aucune source offline (`case-323-unit-map-attribution-voies.md`).\n"
                 ">\n"
                 "> Sections detaillees ordonnees par NOM de faction (ordre stable, pour qu'une\n"
                 "> regeneration ne produise un diff que la ou le contenu bouge) ; la priorisation par\n"
                 "> volume est la table de bilan ci-dessous.\n\n")
    lines.append("## Bilan\n\n")
    lines.append("- Unites lineup : **%d** ; kits COMPLETS (aucun manque detecte) : **%d** ; "
                 "kits avec du travail : **%d**\n" % (len(rows), len(done), len(todo)))
    lines.append("- Volume total : **%d** items manquants (actives no-op + passifs/traits non registres)\n"
                 % total)
    lines.append("- HORS total — voies conditionnelles : **%d** abilities non portees "
                 "(%d mythiques, %d reliques equipables), dont **%d PARTIELLES**\n"
                 % (len(cond_open),
                    sum(1 for c in cond_open if c["voie"] == "mythic"),
                    sum(1 for c in cond_open if c["voie"] == "item"),
                    len(cond_partiels)))
    lines.append("- PARTIELS (#1041) — montage DECLARE, rien ne s'execute : **%d** conditionnelle(s)"
                 "%s ; **%d** passif(s)%s\n"
                 % (len(cond_partiels),
                    (" (" + ", ".join(sorted(c["name"] for c in cond_partiels)) + ")")
                    if cond_partiels else "",
                    len(passifs_partiels),
                    (" (" + ", ".join(passifs_partiels) + ")") if passifs_partiels else ""))
    lines.append("- HORS total — faces DECISION non portees : **%d** actives sur %d, "
                 "dont **%d** dans des kits declares COMPLETS (%d kits concernes)\n"
                 % (len(deci_open), n_actives, len(deci_masquees), len(kits_masques)))
    n_val, n_per = (len(x) for x in CA.ventiler())
    lines.append("- DECOMPTES par un verdict ATTESTE : **%d** (et **%d** attestation(s) PERIMEE(S), "
                 "dont l'item est REDEVENU manquant) — section dediee plus bas, jamais tue\n\n"
                 % (n_val, n_per))

    lines.append("### Priorite par faction (volume decroissant)\n\n")
    lines.append("| faction | kits | items |\n|---|---:|---:|\n")
    for fac in sorted(by_faction, key=lambda f: (-sum(r["missing"] for r in by_faction[f]), f)):
        lines.append("| %s | %d | %d |\n"
                     % (fac, len(by_faction[fac]), sum(r["missing"] for r in by_faction[fac])))

    lines.append("\n## Par faction (kits avec du travail)\n")
    for fac in sorted(by_faction):
        frows = by_faction[fac]
        lines.append("\n### %s — %d kits, %d items\n\n" % (fac, len(frows), sum(r["missing"] for r in frows)))
        lines.append("| unite | manque | actives | passifs manquants | traits de kit manquants |\n")
        lines.append("|---|---|---|---|---|\n")
        for r in frows:
            acts = "<br>".join(_fmt_active(a) for a in r["actives"]) or "-"
            pmiss = ", ".join(p["name"] for p in r["passives"] if not p["covered"]) or "-"
            tmiss = ", ".join("%s(x%d)" % (t["name"], t["carriers"])
                              for t in r["traits"] if not t["covered"]) or "-"
            lines.append("| %s | %d | %s | %s | %s |\n" % (r["id"], r["missing"], acts, pmiss, tmiss))
    lines.append("\n## HORS total — faces DECISION non portees dans des kits COMPLETS (%d)\n\n"
                 % len(deci_masquees))
    lines.append("> ⚠ **`missing` NE COMPTE QUE LA FACE COMBAT.** Une ability dont l'execution est\n"
                 "> portee mais dont l'UTILITE de decision ne l'est pas rend `missing = 0` : le kit\n"
                 "> sort << COMPLET >>, et son marqueur `[C-]` n'etait imprime nulle part, la section\n"
                 "> par faction ne rendant que les kits AVEC du travail. C'est le meme angle mort que\n"
                 "> #323 (un recensement qui rend zero sur ce qu'il ne visite pas), sur l'axe DECIDER.\n"
                 ">\n"
                 "> Consequence : l'IA CHOISIT ces abilities avec un scoring qui n'est pas celui du\n"
                 "> natif — divergence de POLITIQUE, invisible en replay puisque l'execution, elle,\n"
                 "> est fidele. Cf. doctrine « DECIDER != EXECUTER », face DECISION.\n"
                 ">\n"
                 "> Ces entrees restent **hors du total** : elles ne sont pas des items de kit\n"
                 "> manquants, ce sont des faces manquantes d'items presents. Les fondre dans\n"
                 "> `missing` changerait le sens du chiffre cite partout.\n\n")
    lines.append("| unite | ability | id | categorie |\n|---|---|---:|---|\n")
    for r, a in sorted(deci_masquees, key=lambda ra: (ra[0]["faction"], ra[0]["id"], ra[1]["name"])):
        lines.append("| %s | %s | %s | %s |\n"
                     % (r["id"], a["name"], a["id"], a["cat"]))

    val, per = CA.ventiler()
    lines.append("\n## Verdicts ATTESTES — decomptes du total, et JAMAIS tus (%d valides, %d perimees)\n\n"
                 % (len(val), len(per)))
    lines.append("> Un item peut manquer aux registres pour une raison parfaitement legitime : **le\n"
                 "> natif n'a rien de propre a porter**, ou le mecanisme est porte par une voie SANS\n"
                 "> registre. Ecrit uniquement dans une case-doc, ce verdict ne survit a aucun outil —\n"
                 "> `1204 LeadingTheCharge` (prouvee SANS CONTENU PROPRE par #945) et `GalvanicField`\n"
                 "> (verdict MESURE par #952) etaient recomptes manquants a chaque regeneration, et un\n"
                 "> agent a failli etre redispatche dessus.\n"
                 ">\n"
                 "> Ce ne sont PAS des exceptions codees en dur. Chaque entree de\n"
                 "> `scripts/ratchets-951r2-couverture-attestee.json` porte sa RAISON, sa SOURCE, son\n"
                 "> BUILD et un ANCRAGE VERIFIABLE (le cliquet qui garde le verdict, et/ou le symbole\n"
                 "> qui porte le mecanisme). Foyer UNIQUE de validite :\n"
                 "> `scripts/python/coverage_attestations.py::validite`.\n"
                 ">\n"
                 "> ⚠ **L'asymetrie est INVERSE de celle du ledger #462/#465, et c'est structurel** :\n"
                 "> ici l'attestation EST le geste permissif (elle RETIRE du travail du compte). Une\n"
                 "> attestation PERIMEE — build change, cliquet disparu, porteur non resolvable —\n"
                 "> **REMET son item au compte des manquants**. Aucun chemin ne peut faire disparaitre\n"
                 "> du travail : la peremption ne sait que EN RAJOUTER. Un audit qui sous-compte fait\n"
                 "> RENONCER, ce qui est pire qu'un audit qui sur-compte et fait perdre du temps.\n\n")
    lines.append("| item | verdict | ancrage | source | raison |\n|---|---|---|---|---|\n")
    for cle, e, _r in val:
        ancre = e.get("cliquet") or e.get("porteur") or "-"
        lines.append("| %s | %s | `%s` | %s | %s |\n"
                     % (cle, e["verdict"], os.path.basename(ancre), e["source"], e["raison"]))
    if per:
        lines.append("\n**PERIMEES — ces items sont REDEVENUS des manquants** (%d) :\n\n" % len(per))
        for cle, _e, r in per:
            lines.append("* `%s` — %s\n" % (cle, r))

    lines.append("\n## Kits lineup COMPLETS (%d)\n\n" % len(done))
    lines.append("> ⚠ **COMPLET = face COMBAT complete.** %d de ces kits portent au moins une active\n"
                 "> sans face DECISION (section precedente) — ils sont marques `*` ci-dessous.\n\n"
                 % len(kits_masques))
    lines.append(", ".join(
        (r["id"] + ("*" if r["id"] in kits_masques else "")) for r in sorted(done, key=lambda r: r["id"]))
        + "\n")

    lines.append("\n## HORS total — voies conditionnelles (%d abilities non portees)\n\n" % len(cond_open))
    lines.append("> Une unite `lineup` porte aussi des abilities par deux voies que le kit n'expose\n"
                 "> pas : `mythic` (`units.<kind>.<id>.mythicAbilities`, a DEBLOQUER) et `item`\n"
                 "> (`items[*].abilityId` + `allowedUnits`, la relique a EQUIPER). Elles sont hors du\n"
                 "> total parce que leur nature differe — mais les taire reproduirait la cecite de #323,\n"
                 "> qui a fait rendre un faux « 0 unite, DEAD ». Une relique se ventile en TROIS etats\n"
                 "> (equipee au seed / porteur au pool relique non equipee / porteur hors pool) :\n"
                 "> `case-323-unit-map-attribution-voies.md` §5. La voie `relicAbilities` ne touche\n"
                 "> AUCUNE unite `lineup` (0 mesure) — elle n'apparait donc pas ici.\n"
                 ">\n"
                 "> ⚠ **LA COLONNE `etat` EST UN TRI-ETAT DEPUIS #1041, PLUS UN BOOLEEN**, parce que\n"
                 "> le booleen etait faux DES DEUX COTES et que ne corriger qu'un sens DEGRADAIT le\n"
                 "> chiffre. `ABSENT` = aucune voie ne la designe. **`PARTIEL` = une voie la designe\n"
                 "> et son GATE tombe** : typiquement une pose d'owner-effect dont la cible n'a\n"
                 "> AUCUNE classe dans `EFFECT_CLASSES` — le montage est ECRIT et il ne s'execute\n"
                 "> RIEN. Les deux comptent comme du travail, mais ils n'appellent pas le meme :\n"
                 "> `ABSENT` demande un port entier, `PARTIEL` demande la face qui manque.\n"
                 "> Foyer : `scripts/python/kit_item_voies.py`.\n\n")
    lines.append("| ability | voie | etat | porteurs lineup | ex. | detail |\n"
                 "|---|---|---|---:|---|---|\n")
    for c in sorted(cond_open, key=lambda c: (c["voie"], c["name"])):
        lines.append("| %s | %s | %s | %d | %s | %s |\n"
                     % (c["name"], c["voie"], c["etat"], len(c["carriers"]),
                        ", ".join(c["carriers"][:4]), c["detail"] or "-"))
    cond_ok = [c for c in cond if c["covered"]]
    lines.append("\nPortees (au moins une voie dont le gate passe) : **%d**%s\n"
                 % (len(cond_ok),
                    (" — " + ", ".join(sorted(c["name"] for c in cond_ok))) if cond_ok else ""))

    with open(OUT, "w", encoding="utf-8") as f:
        f.writelines(lines)
    print("ecrit -> %s" % OUT)
    print("lineup=%d complets=%d avec-travail=%d items=%d"
          % (len(rows), len(done), len(todo), total))
    print("hors-total voies conditionnelles: %d non portees (%d mythic, %d item), %d portees"
          % (len(cond_open),
             sum(1 for c in cond_open if c["voie"] == "mythic"),
             sum(1 for c in cond_open if c["voie"] == "item"), len(cond_ok)))
    print("tri-etat #1041: PARTIELS = %d conditionnelle(s) [%s], %d passif(s) [%s]"
          % (len(cond_partiels), ", ".join(sorted(c["name"] for c in cond_partiels)) or "-",
             len(passifs_partiels), ", ".join(passifs_partiels) or "-"))


if __name__ == "__main__":
    main()
