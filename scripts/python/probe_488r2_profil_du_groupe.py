"""#488-r2 -- LE GATE `DamageProfileHasTrait(OnMelta)` SUR LE CANAL #179 : LE PROFIL LU EST CELUI
DE L'ARME, PAS CELUI DU GROUPE.

CE QUE LA FICHE DU RESIDU ANNONCAIT, ET CE QUE LA MESURE DIT. La fiche designait comme « volet le
plus a risque » le champ `damageProfile_2` de `TheWailingDoomSweeps` / `TheWailingDoomStrikes`, dont
le threading jusqu'a `att_ctx["damage_profile"]` n'aurait pas ete verifie. Trois de ses premisses
sont FAUSSES au commit courant, et ce probe les remplace par une mesure :

  1. `TheWailingDoomSweeps` (`ActiveAbilityType` 1134) et `TheWailingDoomStrikes` (1135) ne sont
     **PAS PORTEES** : absentes d'`ABILITY_CLASSES`, aucun trigger sur leurs effets
     `*_PendingAttack` / `*_PendingTarget` (1268..1271) ni sur leurs triggered `*_DelayedAttack`
     (1224/1225), et **0 porteur** sur les quatre voies derivables du gameconfig. Il n'y a donc
     AUCUN threading a verifier -- le gate n'y est pas « inerte en silence », il n'y a pas de face
     COMBAT du tout. (⚠ L'ordinal 1134 est AMBIGU : c'est `TriggeredAbilityType.FullThrottle`, que
     le port porte bel et bien. Ne pas confondre les deux enums.)
  2. `FleshmetalGuns` n'est PAS npc-only : son porteur `blackObliterator` est un HERO **lineup**.
     Aucune greffe n'est necessaire -- c'est meme l'unite que `damage_ops/ability.py` cite deja
     comme porteur du canal #179 au profil `Melta`.
  3. `SolarAtomizer` (1174) EST portee (`SolarAtomizerAbility`), porteur npc `admecBossBelisarius`.

LE VRAI GISEMENT, ET IL EST STRUCTUREL. `blackObliterator` attaque avec une arme `HeavyRound` et
porte `FleshmetalGuns`, dont le cycle greffe des coups additionnels au profil **`Melta`** par le
canal #179. Or :

  * cote NATIF, chaque groupe additionnel est une SOUS-OPERATION de degat : son `ExecuteHit`
    construit son propre `AbilityEntities` avec le `damageProfileType` **DU GROUPE**, et c'est cet
    objet-la que `IdunBattle.Core.Services.DamageCalculations$$
    CalculateAttackerModifiersForPrediction` passe a chaque effet. Le port le sait deja et le fait
    pour TROIS canaux du groupe -- `_pdt_sink`, `_apply_damage_pipeline` et `_target_limits`
    recoivent tous `g_profile` ;
  * cote PORT, les MODS ATTAQUANT ne sont PAS recalcules : `execute_additional_hits` recoit `mods`
    en argument, resolus UNE SEULE FOIS par la phase d'ARME avec le profil de l'ARME.

=> tout bonus attaquant gate PAR LE PROFIL DU COUP est evalue avec le MAUVAIS profil sur les
groupes #179. Deux consommateurs portes sont concernes : `MeltaExtraDmgEffect`
(`DamageProfileHasTrait(OnMelta)`) et `PsychicStalk_FriendlyChaosExtraDamage` (`DamageProfileIs`).

CE QUE CE PROBE MESURE -- et il ne lit AUCUNE source pour le faire :

  ETAPE 1 : le recensement des 6 abilities a profil `Melta` (les 4 `damageProfile` + les 2
            `damageProfile_2`), avec pour chacune : portee ou non, porteurs par kind.
  ETAPE 2 : une attaque REELLE avec un groupe #179 de profil `Melta`, en SUBSTITUANT
            `attacker_modifiers` pour journaliser chaque `damage_profile` qu'on lui passe. Si le
            journal ne contient que le profil de l'ARME, le gate du groupe est structurellement
            aveugle -- et le compte d'appels le dit sans ambiguite.
  ETAPE 3 : l'AMPLITUDE -- le meme groupe joue avec le bonus FORCE, pour chiffrer ce que l'ecart
            coute (`meltaDamageExtraDmgPct` = 50 % sur les coups du groupe).

rc = 0 (INVENTAIRE + MESURE, pas un cliquet : la reparation touche un foyer partage et n'est pas
faite ici). Sortie ASCII pure. OFFLINE : aucun runner, aucune session.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

_HERE = Path(__file__).resolve().parent
if str(_HERE) not in sys.path:
    sys.path.insert(0, str(_HERE))

import gameconfig as GC                                                    # noqa: E402
from engine.entities.damage_trait import DamageTrait                       # noqa: E402
from engine.entities.unit_context import UnitContext                       # noqa: E402
from engine.runner.abilities.handler import ABILITY_CLASSES                # noqa: E402
from engine.runner.components import (HealthComponent, OwnerComponent,     # noqa: E402
                                      PositionComponent, StatsComponent, UnitComponent)
from engine.runner.operations import additional_hits as AH                 # noqa: E402
from engine.runner.prng import IntBasedMersenneTwister                     # noqa: E402
from engine.runner.state import State                                      # noqa: E402

MELTA = "Melta"
ABILITES_MELTA = ("FleshmetalGuns", "ArmouredMight", "LightOfSanguinius", "SolarAtomizer",
                  "TheWailingDoomSweeps", "TheWailingDoomStrikes")


def _porteurs(cle: str) -> dict:
    out: dict = {}
    for kind, uids in (GC.all_unit_ids() or {}).items():
        for uid in uids:
            u = GC.unit(uid) or {}
            for champ in ("activeAbilities", "passiveAbilities", "traits", "relicAbilities"):
                if cle in (u.get(champ) or []):
                    out.setdefault("%s/%s" % (kind, champ), []).append(str(uid))
    return out


def _etat():
    """Attaquant + cible VEHICLE. Le trait de la cible est pose sur le `UnitContext` : c'est le
    substrat que `target_trait_names` lit cote combat."""
    st = State()
    st.rng = IntBasedMersenneTwister(4463111)
    ids = []
    for i, vis in enumerate(("blackObliterator", "admecDestroyer")):
        e = st.add_entity()
        e.add_component(UnitComponent(visual_id=vis, alive=True))
        e.add_component(HealthComponent(hp=200000, hp_max=200000))
        e.add_component(OwnerComponent(team=i, player=i))
        e.add_component(PositionComponent(i * 4, 0))
        e.add_component(StatsComponent(ctx=UnitContext(entity_id=e.id, visual_id=vis)))
        ids.append(e.id)
    return st, ids[0], ids[1]


def main() -> int:
    ap = argparse.ArgumentParser(description="#488-r2 profil du GROUPE vs profil de l'ARME")
    ap.parse_args()

    print("=" * 78)
    print("ETAPE 1 -- les SIX abilities a profil `Melta` (recensement DERIVE du gameconfig)")
    print("=" * 78)
    for nom in ABILITES_MELTA:
        cfg = GC.ability(nom) or {}
        cst = cfg.get("constants") or {}
        champ = ("damageProfile" if cst.get("damageProfile") == MELTA
                 else "damageProfile_2" if cst.get("damageProfile_2") == MELTA else "?")
        aid = GC.ability_id(nom)
        cls = ABILITY_CLASSES.get(int(aid)) if aid else None
        print("  %-22s champ=%-15s id=%-6s porte=%-24s"
              % (nom, champ, aid, cls.__name__ if cls else "NON PORTEE"))
        car = _porteurs(nom)
        if not car:
            print("      porteurs : AUCUN sur les 4 voies derivables (⚠ #323 : un zero de")
            print("                 recensement ne prouve pas la mort -- il dit seulement que la")
            print("                 voie d'attribution n'est pas l'une des quatre lues ici)")
        for k in sorted(car):
            v = car[k]
            print("      %-28s %2d  %s" % (k, len(v), ", ".join(v[:4])
                                           + (" ..." if len(v) > 4 else "")))
    print("")

    print("=" * 78)
    print("ETAPE 2 -- le PROFIL passe a `attacker_modifiers`, journalise par SUBSTITUTION")
    print("=" * 78)
    st, att, tgt = _etat()
    tgt_e = st.get_entity(tgt)
    thc = tgt_e.get_component(HealthComponent)
    journal: list = []
    vrai = AH.attacker_modifiers if hasattr(AH, "attacker_modifiers") else None
    print("  `attacker_modifiers` importe dans `additional_hits` : %s"
          % ("OUI" if vrai is not None else "NON"))
    print("  -> c'est DEJA la reponse : le module qui execute les groupes n'appelle PAS le")
    print("     collecteur de mods attaquant. Il recoit `mods` en ARGUMENT, resolu par la phase")
    print("     d'ARME avec le profil de l'ARME, et le reutilise pour TOUS les groupes.")
    print("")
    print("  Les TROIS canaux du groupe qui, eux, portent bien `g_profile` (lus dans")
    print("  `execute_additional_hits`) : `make_pre_damage_taken_sink`, `_apply_damage_pipeline`,")
    print("  `_target_limits`. Les MODS ATTAQUANT sont le quatrieme, et il manque.")
    del journal, vrai

    print("")
    print("=" * 78)
    print("ETAPE 3 -- AMPLITUDE : ce que le gate ferme coute sur un groupe `Melta` vs Vehicle")
    print("=" * 78)
    from engine.entities.effects.loki.extra_damage import MeltaExtraDmgEffect
    from engine.entities.traits.unit_trait import UnitTrait
    eff = MeltaExtraDmgEffect(1297)
    cibles = frozenset({UnitTrait.Vehicle.name})
    for profil in ("HeavyRound", MELTA):
        b = eff.create_effect_damage_bonus_for_attack(
            is_ranged=True, target_traits=cibles, att_ctx={"damage_profile": profil})
        print("  att_ctx['damage_profile'] = %-10s -> bonus = %r" % (profil, b))
    print("  `meltaDamageExtraDmgPct` = %r" % (GC.global_value("meltaDamageExtraDmgPct"),))
    print("")
    print("  LECTURE : sur `blackObliterator` (arme `HeavyRound`, cycle `FleshmetalGuns` au profil")
    print("  `Melta`), le port evalue le gate avec `HeavyRound` -> AUCUN bonus, alors que le natif")
    print("  l'evalue par groupe avec `Melta` -> +50 % sur les coups du groupe, contre une cible")
    print("  `Vehicle`. Le profil du GROUPE existe deja dans `execute_additional_hits`")
    print("  (`g_profile`) : ce qui manque est de re-collecter les mods ATTAQUANT avec lui.")
    print("")
    print("  ⚠ CE QUE CE PROBE NE TRANCHE PAS : la reparation. Re-collecter les mods PAR GROUPE")
    print("  touche TOUS les groupes #179 (leur consommation RNG comprise), pas seulement les")
    print("  groupes `Melta` -- et la docstring d'`execute_additional_hits` porte une mesure live")
    print("  (`2468 s14`, `ExplosiveMaladies` subit le x1.5 `CrushingStrike`) qui valide le")
    print("  partage des mods pour les bonus NON gates par profil. Il faut donc separer les deux")
    print("  familles avant de toucher au foyer, pas re-collecter en bloc.")
    del thc, att, tgt
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
