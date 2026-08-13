"""#931-r2 -- la face DECISION derivait les abilities ACCORDEES du KIT gameconfig, pas de l'ENTITE.

MESURE, pas test. 100 % OFFLINE : aucun RPC, aucun runner.

## Le vice

`engine.ai.state_bridge._granted_abilities(vid)` bouclait sur `GC.unit(vid)["passiveAbilities"]`
-- le KIT -- et resolvait `Heal_<passif>` dans `ActiveAbilityType`. Le natif, lui, monte l'ability
accordee depuis `UnitConfiguration.PassiveAbilities`, c.-a-d. `BC.Units[].PassiveAbilities` : un
fait d'**ENTITE** (`...TwistedScienceAbility$$CreateBehaviour`, `On(AbilityInit) & OwnerIsActor`).

Les deux coincident tant que personne ne touche a la liste, et divergent SILENCIEUSEMENT des qu'un
montage la modifie -- ce que fait tout bras `catalog_inject.write_grafted_seed_bc(..., replace=True)`,
qui REMPLACE la liste. Meme vice de substrat que #264 (traits) / #366-r1 (passifs, face COMBAT) /
#419-r1-tr14-r5 (attaque normale).

## Ce que ce probe mesure

  0. POPULATION : quelles unites du catalogue recoivent une ability accordee PAR LE KIT, et par
     quel passif. Assertionne son propre non-vide.
  1. LES DEUX SENS de la divergence, sur le meme foyer :
     * GREFFE  -- une unite dont le kit N'A PAS le passif, mais dont l'ENTITE le porte : le natif
       lui donne l'ability, le port (kit) ne la lui donnait pas -> ability MANQUANTE ;
     * RETRAIT -- une unite dont le kit A le passif, mais dont l'ENTITE ne le porte pas (une greffe
       `replace=True` VIDE la liste) : le port la lui donnait -> ability FANTOME.
  2. LE TRI-ETAT : `None` (canal muet) doit rendre EXACTEMENT le comportement kit d'avant, et un
     tuple VIDE doit se lire « mesure : aucun passif », pas « pas de mesure ».

Sortie ASCII stricte (console cp1252).
"""
from __future__ import annotations

import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import unit_map as UM                                                          # noqa: E402
from engine.ai import state_bridge as SB                                       # noqa: E402
from engine.entities.active_ability_type import ActiveAbilityType              # noqa: E402

#: Le passif ACCORDEUR du build courant, et l'ability qu'il monte. Les deux sont LUS
#: (`ActiveAbilityType` porte un seul membre `Heal_*`), pas choisis.
PASSIF = "TwistedScience"
ACCORDEE = int(ActiveAbilityType.Heal_TwistedScience)      # 1167
#: Unite TEMOIN dont le kit ne porte PAS le passif (voie `active`, `lineup`).
TEMOIN_SANS = "admecRuststalker"


def etape0() -> list:
    print("== ETAGE 0 : POPULATION -- a qui le KIT accorde-t-il une active via un passif ? ==")
    ids = sorted(k["id"] for k in UM.all_kits() if k.get("id"))
    porteurs = [(v, SB._granted_abilities(v)) for v in ids if SB._granted_abilities(v)]
    assert porteurs, "ETAGE 0 VIDE : aucune unite ne recoit d'ability accordee -- rien n'est mesure"
    print("kits du catalogue        : %d" % len(ids))
    print("porteurs d'un grant KIT  : %d" % len(porteurs))
    for v, g in porteurs:
        print("  %-24s %r" % (v, g))
    print("temoin SANS le passif    : %-12s -> %r" % (TEMOIN_SANS,
                                                      SB._granted_abilities(TEMOIN_SANS)))
    return porteurs


def etape1(porteurs: list) -> None:
    print()
    print("== ETAGE 1 : les DEUX sens de la divergence KIT vs ENTITE ==")
    kit_porteur = porteurs[0][0]

    # (a) GREFFE : l'entite porte le passif, le kit non.
    kit = SB._granted_abilities(TEMOIN_SANS)                  # repli KIT (canal muet)
    ent = SB._granted_abilities(TEMOIN_SANS, (PASSIF,))       # MESURE d'entite
    print("GREFFE  %-22s kit=%r  entite=%r" % (TEMOIN_SANS, kit, ent))
    print("        -> ability %d %s (le natif la monte, le port la manquait)"
          % (ACCORDEE, "RETROUVEE" if any(a == ACCORDEE for a, _ in ent) else "TOUJOURS ABSENTE"))

    # (b) RETRAIT : le kit porte le passif, l'entite non (une greffe `replace=True` VIDE la liste).
    kit2 = SB._granted_abilities(kit_porteur)
    ent2 = SB._granted_abilities(kit_porteur, ())             # MESURE : aucun passif monte
    print("RETRAIT %-22s kit=%r  entite=%r" % (kit_porteur, kit2, ent2))
    print("        -> ability %d %s (le port la donnait a tort)"
          % (ACCORDEE, "ECARTEE" if not ent2 else "TOUJOURS FANTOME"))


def etape2(porteurs: list) -> None:
    print()
    print("== ETAGE 2 : TRI-ETAT -- `None` (muet) != `()` (mesure vide) ==")
    kit_porteur = porteurs[0][0]
    muet = SB._granted_abilities(kit_porteur, None)
    vide = SB._granted_abilities(kit_porteur, ())
    print("None (muet, repli kit) : %r" % (muet,))
    print("()   (mesure vide)     : %r" % (vide,))
    print("les deux different     : %s" % (muet != vide))
    print("le muet EGALE le kit   : %s" % (muet == SB._granted_abilities(kit_porteur),))


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.parse_args(argv)
    porteurs = etape0()
    etape1(porteurs)
    etape2(porteurs)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
