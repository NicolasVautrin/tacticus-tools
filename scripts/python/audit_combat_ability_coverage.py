"""Audit de la COUVERTURE COMBAT des abilities actives (#95).

Croise les `activeAbilities` (gameconfig, par unite) avec le registry d'execution combat
`engine.runner.abilities.handler.ABILITY_CLASSES`. Toute ability active castable dont l'`ActiveAbilityType`
est ABSENT du registry fait un NO-OP SILENCIEUX en combat (`AbilityHandler.visit_ActiveAbilityMessage` :
`ported:False`, 0 degat/effet, aucune erreur) -> divergence d'etat invisible en replay/self-play. Cf.
doctrine CLAUDE.md "DECIDER != EXECUTER".

Genere `docs/rl/combat-ability-coverage.md` (inventaire priorise). A RELANCER au changement de build du jeu
ou apres tout port d'ability (nouvelle entree dans ABILITY_CLASSES). Aucune session live requise (offline).

Usage : depuis `scripts/python/`  ->  `python audit_combat_ability_coverage.py`
"""
from __future__ import annotations

import os
import sys
from collections import Counter

_PYROOT = os.path.dirname(os.path.abspath(__file__))   # scripts/python
_REPO = os.path.dirname(os.path.dirname(_PYROOT))      # racine repo
if _PYROOT not in sys.path:
    sys.path.insert(0, _PYROOT)

import enum_maps as EM
import gameconfig as GC
import unit_map as UM
from engine.runner.abilities.handler import ABILITY_CLASSES

OUT = os.path.join(_REPO, "docs", "rl", "combat-ability-coverage.md")


#: #491-r2 -- LES CAS OU LA CATEGORIE DERIVEE DU KIT A ETE **MESUREE FAUSSE**, id -> (etiquette, ref).
#:
#: `_classify` ne peut lire que le GAMECONFIG (le `damageProfile` du kit). Pour une ability NON
#: PORTEE, son `ExecuteBehaviour` n'est connu de personne, donc la categorie ne peut PAS etre
#: derivee -- c'est une limite structurelle, pas un manque de soin. Or c'est exactement cette
#: colonne qu'on lit pour DISPATCHER : le 2026-08-07, elle a fait briefer QUATRE tranches comme
#: des ports d'attaque alors que leur cast ne frappe pas. Un solveur envoye porter « une attaque »
#: qui n'en est pas perd son temps, ou pire, **invente le degat au cast**.
#:
#: Ce registre est donc l'inverse d'une derivation : il consigne ce qui a ete **MESURE**, ability
#: par ability, et l'ecrase sur la colonne. Il ne grandit que par des tranches qui ont lu le
#: decompile ET confronte live. Un id qu'il ne contient pas n'est PAS « verifie DAMAGE » -- il est
#: **non verifie**, et le tableau le dit maintenant en toutes lettres.
CATEGORIE_MESUREE: dict[int, tuple[str, str]] = {
    # Le cast ne frappe PAS : il pose des effets, et le degat appartient a une TRIGGERED (phase 2).
    # Mesure live : HP inchanges au cast, alors que la prediction native annoncait [8818-12049].
    1069: ("2-PHASES (cast sans degat)", "case-491-seeker-missile-frequency-lock.md"),
    # Trois poses d'effet ; le `2x Eviscerate` du kit vit dans la triggered 1237.
    1141: ("2-PHASES (cast sans degat)", "case-503-overwhelming-wrath.md"),
}


def _classify(name: str) -> str:
    a = GC.ability(name) or {}
    c = a.get("constants") or {}
    v = a.get("variables") or {}
    if c.get("damageProfile"):
        return "DAMAGE(%s)" % c.get("damageProfile")
    if c.get("unitId"):
        return "SUMMON"
    if any(k.startswith("hpToHeal") for k in v):
        return "HEAL"
    if any(k.startswith("hpToRepair") for k in v):
        return "REPAIR"
    return "EFFECT/BUFF"


def _bucket(cl: str) -> str:
    return "DAMAGE" if cl.startswith("DAMAGE") else cl


def collect():
    name2id = {v: k for k, v in EM.ACTIVE_ABILITY_TYPE.items()}
    registered = set(ABILITY_CLASSES.keys())
    active_by_name: dict[str, dict] = {}
    for k in UM.all_kits():
        u = GC.unit(k["id"]) or {}
        for nm in (u.get("activeAbilities") or []):
            rec = active_by_name.setdefault(nm, {"units": set(), "kinds": set()})
            rec["units"].add(k["id"])
            rec["kinds"].add(k.get("kind"))
    rows = []
    for nm, rec in active_by_name.items():
        aid = name2id.get(nm)
        ported = aid in registered
        cl = _classify(nm)
        mes = CATEGORIE_MESUREE.get(aid)
        if mes:
            # La MESURE ecrase la derivation du kit, et garde la valeur du kit entre parentheses :
            # le `damageProfile` reste vrai (c'est bien le profil de l'ARME), il ne dit simplement
            # rien de la phase ou le degat tombe.
            cl = "%s [kit: %s]" % (mes[0], cl)
        rows.append((aid, nm, "PORTED" if ported else "NO-OP", cl,
                     len(rec["units"]), rec["kinds"]))
    return rows


def _table(lines, title, lst):
    lines.append("\n## %s (%d)\n\n" % (title, len(lst)))
    lines.append("| id | ability | categorie | #units | kinds |\n|---|---|---|---|---|\n")
    for aid, nm, st, cl, nu, kinds in sorted(lst, key=lambda r: (_bucket(r[3]), -r[4], str(r[1]))):
        kmark = "".join(sorted(x[0].upper() for x in kinds if x))
        idstr = str(aid) if aid is not None else "?"       # nom sans ActiveAbilityType enum
        lines.append("| %s | %s | %s | %d | %s |\n" % (idstr, nm, cl, nu, kmark))


def main():
    rows = collect()
    unported = [r for r in rows if r[2] == "NO-OP"]
    ported = [r for r in rows if r[2] == "PORTED"]
    cat = Counter(_bucket(r[3]) for r in unported)

    lines = []
    lines.append("# Couverture combat des abilities actives (audit #95)\n\n")
    lines.append("> Genere par `scripts/python/audit_combat_ability_coverage.py` (source de verite : "
                 "`gameconfig.activeAbilities` par unite x `AbilityHandler.ABILITY_CLASSES`). A regenerer au "
                 "changement de build ou apres un port d'ability.\n\n")
    lines.append("## Contexte : DECIDER != EXECUTER\n\n")
    lines.append("Le runner combat route chaque ability choisie via `ActiveAbilityMessage` -> "
                 "`AbilityHandler.visit_ActiveAbilityMessage` : tout `ActiveAbilityType` **absent** de "
                 "`ABILITY_CLASSES` fait un **NO-OP SILENCIEUX** (`ported:False`, 0 degat, 0 effet, AUCUNE "
                 "erreur). La DECISION (prediction/scoring) peut CHOISIR l'ability alors que l'EXECUTION "
                 "l'ignore -> divergence d'etat INVISIBLE en replay/self-play. Cf. doctrine CLAUDE.md "
                 "\"DECIDER != EXECUTER\". Durcissement : `AbilityHandler.unported` accumule les casts tombes "
                 "sur no-op ; les tests d'execution assert `last['ported'] is True`.\n\n")
    lines.append("## Bilan\n\n")
    lines.append("- ActiveAbilityType castables par les unites : **%d** distinct\n" % len(rows))
    lines.append("- **PORTED** (dans `ABILITY_CLASSES`) : **%d**\n" % len(ported))
    lines.append("- **NO-OP silencieux** (a porter) : **%d**\n" % len(unported))
    lines.append("- Ventilation NO-OP : " + ", ".join("**%s**=%d" % (k, n)
                                                       for k, n in cat.most_common()) + "\n\n")
    lines.append("## Priorisation & templates de port\n\n")
    lines.append("1. **DAMAGE** (impact combat direct : degat non inflige = divergence PV) -> template "
                 "`SpiritLeechAbility`/`CrushingClawsAbility` (`ability_attack_params` + `execute_ability_attack`, "
                 "config minDmg/maxDmg + profil + nrOfHits ; splash/effets composes selon `ExecuteBehaviour`). "
                 "Prioriser par #units. ATTENTION : quelques \"DAMAGE\" sont en fait des BUFF a `damageProfile` "
                 "(NovaBoost/NovaCharge/NovaShield 1192-1194 = NonComparable buff/tile) -> verifier "
                 "`ExecuteBehaviour` avant de porter comme attaque.\n")
    lines.append("\n> ⚠ **LA COLONNE `categorie` DERIVE DU KIT, PAS DU BEHAVIOUR -- elle N'EST PAS "
                 "VERIFIEE.** Elle lit le `damageProfile` du gameconfig, c'est-a-dire le profil de "
                 "l'ARME du porteur. Pour une ability NON PORTEE, son `ExecuteBehaviour` n'est "
                 "connu de personne : la categorie ne peut donc PAS etre derivee, c'est une limite "
                 "structurelle. **Mesure du 2026-08-07 : quatre tranches ont ete briefees comme des "
                 "ports d'ATTAQUE alors que leur cast ne frappe pas** -- patron 2-PHASES (le cast "
                 "pose des effets, le degat appartient a une TRIGGERED), ou `AddEffect` suivi d'une "
                 "attaque normale libre, ou boucle imperative. Un solveur envoye porter « une "
                 "attaque » qui n'en est pas perd son temps, ou pire **invente le degat au cast**.\n>\n"
                 "> **Avant tout dispatch : LIRE `<X>Ability$$ExecuteBehaviour` au decompile.** Les "
                 "cas ou la derivation a ete mesuree FAUSSE sont ecrases dans le tableau et "
                 "s'affichent `2-PHASES (cast sans degat) [kit: DAMAGE(...)]` ; le registre qui les "
                 "porte est `CATEGORIE_MESUREE` dans le generateur. Une ability qui n'y figure pas "
                 "n'est PAS « verifiee DAMAGE » : elle est **non verifiee** (residu `#491-r2`).\n\n")
    lines.append("2. **SUMMON** -> template `ScarabHiveAbility`/`GetEmRuntzAbility` (`SpawnUnitOperation` + "
                 "summon on-appearance).\n")
    lines.append("3. **HEAL** / lifesteal / **REPAIR** -> **DEBLOQUE** (#520). Les deux Operations sont "
                 "portees et COMPLETES : `IdunBattle.Operations.RepairUnitOperation$$Execute` "
                 "(`runner/operations/repair.py`, #299) et "
                 "`IdunBattle.Operations.HealUnitOperation$$Execute` (`runner/operations/heal.py`, #520). "
                 "Chacune porte son gate (`AttackQuery$$EntityCanBeRepaired` / `$$EntityCanBeHealed`), "
                 "sa prediction (`DamagePrediction$$PredictRepair` / `$$PredictHeal`) et ses deux "
                 "fabriques d'options (`ForRepair`/`ForRegenerate`, `ForHeal`/`ForRegenerate`). "
                 "Un port de cette categorie construit une feuille `Repair`/`Heal` "
                 "(`runner/abilities/behaviours/stats.py`) et DECLARE sa fabrique lue au decompile.\n")
    lines.append("\n> ⚠ **CETTE LIGNE A ANNONCE « BLOQUE sur un `HealOperation`/`RepairOperation` "
                 "combat absent du runner (tache #94) » BIEN APRES QUE LES DEUX EURENT ETE PORTEES**, "
                 "et c'est la forme de degat la plus couteuse d'une citation perimee : elle a fait "
                 "RENONCER a dispatcher une categorie entiere. Pire, elle designait le mauvais "
                 "bloqueur -- le vrai etait qu'`HealUnitOperation` n'appelait NI son gate NI "
                 "`PredictHeal`, donc les QUATRE abilities HEAL deja au registre soignaient des "
                 "cibles que le natif refuse, en rendant `ported: True`. Mesure #520 sur le seed 777 : "
                 "**3 unites blessees sur 10** etaient refusees par le gate et soignees par le port. "
                 "Un no-op silencieux DANS une ability declaree portee ne se voit par AUCUN compteur "
                 "de cet audit -- il ne compte que les absentes du registre.\n\n")
    lines.append("4. **EFFECT/BUFF** -> `AddEffectOperation` (+ stat-mods) ; certains deja modelises cote "
                 "prediction (NonComparable) mais pas executes.\n\n")
    lines.append("Legende `kinds` : **L**=lineup (jouable), **N**=npc, **S**=summons.\n")
    _table(lines, "NO-OP SILENCIEUX en combat (a porter, tries categorie puis frequence)", unported)
    _table(lines, "PORTED (registry)", ported)

    with open(OUT, "w", encoding="utf-8") as f:
        f.writelines(lines)
    print("ecrit -> %s" % OUT)
    print("actives=%d ported=%d no-op=%d | %s"
          % (len(rows), len(ported), len(unported),
             ", ".join("%s=%d" % (k, n) for k, n in cat.most_common())))


if __name__ == "__main__":
    main()
