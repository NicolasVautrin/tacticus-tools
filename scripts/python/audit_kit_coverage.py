"""Audit de la couverture moteur PAR KIT (unites lineup) — vue "kits restants a porter".

Complement KIT-centrique de `audit_combat_ability_coverage.py` (#95, vue par-ability) : pour
chaque unite LINEUP (jouable en walk), croise son kit gameconfig complet avec les registres
moteur des deux faces :

  FACE COMBAT (execution) :
    - actives  -> `engine.runner.abilities.handler.ABILITY_CLASSES` (id ActiveAbilityType)
    - passives -> `triggers.dispatch.ABILITY_TRIGGERS` (nom d'ability) et
                  `effects.factory.ABILITY_INIT_OWNER_EFFECTS` (effet owner pose au spawn)
    - traits   -> `triggers.dispatch.TRAIT_TRIGGERS` + `effects.factory.TRAIT_DERIVED_ABILITIES`
                  + `effects.factory.TRAIT_OWNER_EFFECTS` (owner-effect pose au spawn : c'est un
                  TROISIEME chemin de port, ni trigger ni ability derivee). L'oublier faisait compter
                  MartialKatah manquant sur ses 4 porteurs Custodes alors que ses DEUX effets sont
                  portes (MartialKatahDmgBonusEffect / MartialKatahDmgReductionEffect).
  FACE DECISION (scoring) : TROIS registres, pas un —
    - `engine.playbook.noncomparable.PLAYBOOKS` (id) : les abilities NON-COMPARABLES, qui ont
      leur propre voie de scoring ;
    - `engine.playbook.base.REGISTRY` (id) : les abilities COMPARABLES dotees d'un override
      `CalculateCustomUtility` (#27) — leur voie generique est commune, seul le terme custom est
      par-ability. Lire le 1er SEUL faisait ressortir `[--]` (= rien de porte) sur des abilities
      dont la face DECISION est portee, ex. DoomSiren(1199) alors que `DoomSirenPlaybook` existe.
    - `entities.abilities.active_ability._SPECIAL_ABILITY_CLASSES` (NOM) : les sous-classes
      `AActiveAbility` mirrorees PAR ability (formule de coups propre, AoE, degat conditionnel).
      Consommees uniquement sous `engine/playbook/prediction/` -> face DECISION. Rater ce 3e
      registre affichait 14 `[-D]` pour 20 reels, et des `[--]` faux (ex. 1191 MartialInspiration).
    Le reste de la voie comparable est generique et n'est pas audite ici.

    ⚠ `_NONCOMPARABLE_ABILITIES` n'est PAS un 4e registre de couverture : y figurer dit seulement
    que le port CLASSE l'ability NonComparable (donc s'interdit de fabriquer un degat depuis
    minDmg/maxDmg) ; son UTILITE de decision vit dans `PLAYBOOKS`. L'audit le signale a part
    (« NC classee, utilite NC non portee ») au lieu de le compter comme `D` -- sinon on commet
    l'erreur SYMETRIQUE du sous-comptage, en declarant porte ce qui ne l'est pas.

APPROXIMATIONS assumees (l'audit RANGE les kits par volume de travail, il ne PROUVE pas une
couverture) : un passif peut etre implemente ailleurs (mod attaquant, effet, legalite) sans
figurer dans ces registres -> faux "MISSING" possibles, a trancher au recon du kit. Les traits
FREQUENTS (>TRAIT_COMMON_MAX unites : Hero, Psyker, Flying, ...) sont presumes couverts par les
couches globales (mouvement/legalite/smite) et exclus du comptage.

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

import enum_maps as EM
import gameconfig as GC
import unit_map as UM
from audit_combat_ability_coverage import _classify
from engine.entities.effects.factory import (
    ABILITY_INIT_OWNER_EFFECTS, EFFECT_CLASSES, TRAIT_DERIVED_ABILITIES, TRAIT_OWNER_EFFECTS,
)
from engine.entities.abilities.active_ability import (   # 3e registre de decision, keye par NOM
    _NONCOMPARABLE_ABILITIES, _SPECIAL_ABILITY_CLASSES,
)
from engine.playbook import REGISTRY as CUSTOM_PLAYBOOKS   # comparables a override CalculateCustomUtility
from engine.playbook.noncomparable import PLAYBOOKS
from engine.runner.abilities.handler import ABILITY_CLASSES
from engine.runner.operations.triggers.dispatch import ABILITY_TRIGGERS, TRAIT_TRIGGERS

OUT = os.path.join(_REPO, "docs", "rl", "kit-coverage.md")

# Au-dela de ce nombre de porteurs, un trait est presume couvert par les couches globales
# (stats/mouvement/legalite) et n'est pas compte comme travail de kit.
TRAIT_COMMON_MAX = 12

# Voies d'attribution qui touchent une unite `lineup` sans figurer sur `activeAbilities` /
# `passiveAbilities` (#323). Elles sont CONDITIONNELLES (a debloquer / a equiper) -> comptees a
# part, jamais fondues dans le total, mais jamais tues non plus.
VOIES_CONDITIONNELLES = ("mythic", "item")


def _has_effect_named_after(name: str) -> bool:
    """Un trait/passif peut etre porte UNIQUEMENT par sa/ses classe(s) d'effet, sans passer par un
    registre trait->X : l'effet est seede depuis le live (`decisionView.effects`) et c'est sa classe
    qui porte toute la mecanique. Deux formes observees, les deux comptent :
      - effet HOMONYME du trait/passif (ex. trait `BlessingsOfKhorne` -> `BlessingsOfKhorne`) ;
      - effets PREFIXES `<nom>_...` (ex. trait `MartialKatah` -> `MartialKatah_DmgBonus` +
        `MartialKatah_DmgReduction` ; passif `BeaconOfRage` -> `BeaconOfRage_ExtraDamage` + ...).
    APPROXIMATION assumee, comme le reste de cet audit : c'est la convention de nommage du port,
    pas une preuve de cablage. Elle sous-estime beaucoup moins que de l'ignorer (l'ignorer faisait
    ressortir MartialKatah et BlessingsOfKhorne comme du travail a faire alors qu'ils sont portes
    et valides live)."""
    pfx = name + "_"
    return any(k == name or k.startswith(pfx) for k in EFFECT_CLASSES)


def _passive_covered(nm: str) -> bool:
    """Le predicat de couverture d'un item NON-actif (passif, mythique, relique) : un trigger
    d'ability, un owner-effect pose au spawn, ou une classe d'effet nommee d'apres lui."""
    return (nm in ABILITY_TRIGGERS or nm in ABILITY_INIT_OWNER_EFFECTS
            or _has_effect_named_after(nm))


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
    out = []
    for (nm, voie), units in carriers.items():
        aid = name2id.get(nm)
        out.append({
            "name": nm, "voie": voie, "id": aid, "carriers": sorted(units),
            "covered": _passive_covered(nm) or (aid is not None and aid in ABILITY_CLASSES),
        })
    return sorted(out, key=lambda r: (r["covered"], r["voie"], r["name"]))


def collect():
    name2id = {v: k for k, v in EM.ACTIVE_ABILITY_TYPE.items()}
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
            actives.append({
                "name": nm, "id": aid, "cat": _classify(nm),
                "combat": aid in ABILITY_CLASSES,
                # 3e registre, keye par NOM et non par id : `_SPECIAL_ABILITY_CLASSES` mirror une
                # sous-classe `AActiveAbility` PAR ability (formule de coups propre, AoE, degat
                # conditionnel), consommee uniquement sous `engine/playbook/prediction/` — c'est
                # donc bien de la face DECISION, et l'ignorer produisait des `[--]` faux (mesure :
                # 14 `[-D]` affiches pour 20 reels).
                "decision": (aid in PLAYBOOKS or aid in CUSTOM_PLAYBOOKS
                             or nm in _SPECIAL_ABILITY_CLASSES),
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
            passives.append({"name": nm, "covered": _passive_covered(nm)})
        kit_traits = []
        for t in (u.get("traits") or []):
            if trait_units[t] > TRAIT_COMMON_MAX:
                continue                       # trait commun -> couche globale, pas du travail de kit
            kit_traits.append({
                "name": t, "carriers": trait_units[t],
                "covered": (t in TRAIT_TRIGGERS or t in TRAIT_DERIVED_ABILITIES
                            or t in TRAIT_OWNER_EFFECTS or _has_effect_named_after(t)),
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
                 "> section, chiffree, en fin de document. Les voies `trait`/`liveevent`/`summon`/`tile`\n"
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
                 "(%d mythiques, %d reliques equipables)\n\n"
                 % (len(cond_open),
                    sum(1 for c in cond_open if c["voie"] == "mythic"),
                    sum(1 for c in cond_open if c["voie"] == "item")))

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
    lines.append("\n## Kits lineup COMPLETS (%d)\n\n" % len(done))
    lines.append(", ".join(sorted(r["id"] for r in done)) + "\n")

    lines.append("\n## HORS total — voies conditionnelles (%d abilities non portees)\n\n" % len(cond_open))
    lines.append("> Une unite `lineup` porte aussi des abilities par deux voies que le kit n'expose\n"
                 "> pas : `mythic` (`units.<kind>.<id>.mythicAbilities`, a DEBLOQUER) et `item`\n"
                 "> (`items[*].abilityId` + `allowedUnits`, la relique a EQUIPER). Elles sont hors du\n"
                 "> total parce que leur nature differe — mais les taire reproduirait la cecite de #323,\n"
                 "> qui a fait rendre un faux « 0 unite, DEAD ». Une relique se ventile en TROIS etats\n"
                 "> (equipee au seed / porteur au pool relique non equipee / porteur hors pool) :\n"
                 "> `case-323-unit-map-attribution-voies.md` §5. La voie `relicAbilities` ne touche\n"
                 "> AUCUNE unite `lineup` (0 mesure) — elle n'apparait donc pas ici.\n\n")
    lines.append("| ability | voie | porteurs lineup | ex. |\n|---|---|---:|---|\n")
    for c in sorted(cond_open, key=lambda c: (c["voie"], c["name"])):
        lines.append("| %s | %s | %d | %s |\n"
                     % (c["name"], c["voie"], len(c["carriers"]), ", ".join(c["carriers"][:4])))
    cond_ok = [c for c in cond if c["covered"]]
    lines.append("\nPortees (au moins un registre) : **%d**%s\n"
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


if __name__ == "__main__":
    main()
