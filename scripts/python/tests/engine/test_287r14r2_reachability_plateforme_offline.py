"""#287-r14-r2 -- la branche `MachinePlatform` de `UnitExtensions$$GetMachine` n'est PORTEE par
AUCUN vecteur, et ce cliquet garde ce verdict au lieu de le laisser se peri­mer en prose.

CE QUE LE DECOMPILE DIT (relu le 2026-08-15 sur le build COURANT `t6dpr4k06g` -- la fiche notait
« Ghidra sert encore l'ANCIEN build », ce qui n'est plus vrai) :

    IdunBattle.Entities.UnitExtensions$$GetMachine(entity, state):
        if (entity == null)          return null;
        if (EntityType(entity) == 6) return entity;                       # Machine
        if (EntityType(entity) == 7) return TileExtensions
                                            .GetMachinePlatformContent(entity, state);
        return null;

    IdunBattle.Entities.TileExtensions$$GetMachinePlatformContent(platform, state):
        comp = platform.GetComponent(MachinePlatformComponent);
        if (comp == null)            return null;                # via le tail-call d'echec
        machineId = comp.MachineId;                              # Nullable, @+0x14 / @+0x18
        if (!machineId.HasValue)     return null;                # `if (*pcVar4 == 0) return 0`
        return state.GetEntity(machineId.Value);

DEUX PREMISSES DE LA FICHE SONT TOMBEES, ET CE FICHIER LES REMPLACE PAR DES MESURES.

(1) « le substrat est publie A MOITIE, ce qui est pire qu'absent » -- PERIME. Le canal
    `decisionView.mows[].platformIds` est ARME, et `frida/hooks/game/match-state.ts::
    readMachinePlatformLink` ne retient QUE les plateformes dont `MachineId.HasValue` est vrai.
    C'est LA MEME condition que celle du natif ci-dessus : une plateforme absente du canal est une
    plateforme sur laquelle `GetMachinePlatformContent` rendrait `null`. Le mapping publie est donc
    COMPLET pour tout ce qui est LIABLE, et la crainte d'« une resolution qui reussit sur une
    plateforme et echoue sur l'autre, en silence » n'a plus d'objet. MESURE (runner MoW sur
    `MC1_67`, `dumpEntityComponents`) : la MoW porte bien DEUX entites de type 7, et `platformIds`
    n'en publie qu'UNE -- parce que l'autre ne porte pas de `MachineId`.

(2) « aucun canal mesure ne remet un id de PLATEFORME comme cible » -- CONFIRME, et desormais
    MESURE au lieu d'etre suppose. C'est CE point, et lui seul, qui interdit le port : ecrire la
    branche ajouterait du code qu'aucun vecteur n'exerce, et le premier test a l'exercer devrait
    FABRIQUER une cible que le natif ne produit jamais. Doctrine « pas de porteur = speculatif ».

MESURE LIVE DU 2026-08-15 (runner `--p-mow tauBroadside --a-mow orksRukkatrukk`, board `MC1_67`,
seed 777). `1160 HeavyRailRifle` est la SEULE ability du registre a porter `TargetIsActor`, donc
le seul chemin qui atteigne `machine_id()` sur autre chose qu'une Machine :

    decisionView.mows -> id=75 machineId=80 (tauBroadside)   platformIds=[75]
                         id=76 machineId=79 (orksRukkatrukk) platformIds=[76]
    abilityTargets(caster=80, ability=1160).fromHere -> [77, 79]
        INTERSECTION avec les PLATEFORMES {75, 76} = {}          <- VIDE
        INTERSECTION avec les MACHINES    {79, 80} = {79}        <- la MACHINE, pas sa plateforme

    et cote port, sur le MEME etat charge :
        machine_id(79) = 79      machine_id(80) = 80             <- ACCORD avec le natif
        machine_id(75) = None    machine_id(76) = None           <- jamais interroge

CE QUI FERAIT ROUGIR CE FICHIER, et c'est le but : une ability qui entre au registre avec
`TargetIsMachine`, ou `1160` qui change de masque. La branche `MachinePlatform` deviendrait alors
exigible, AVEC son vecteur de confrontation -- ce que ce residu demandait depuis le debut.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

#: Ce qui doit changer pour que ce fichier puisse changer de verdict (#486-r15).
#: Le REGISTRE d'abilities est le declencheur PRINCIPAL -- une entree neuve y suffit a rouvrir la
#: reachability. `handler.py` porte la table, mais les masques vivent dans les modules d'ability :
#: le perimetre est donc pris LARGE (tout `runner/abilities/**`), ce qui est le regime sain.
DECLENCHEUR = {
    "chemins": ("scripts/python/engine/runner/abilities/handler.py",
                "scripts/python/engine/runner/abilities/*.py",
                "scripts/python/engine/runner/abilities/targeting_rule.py",
                "scripts/python/engine/runner/abilities/behaviours/context.py",
                "scripts/python/engine/runner/snapshot.py",
                "scripts/python/engine/runner/components.py",
                "frida/hooks/game/match-state.ts",
                "frida/hooks/features/ai-step/projection.ts"),
    "build": True,
    "toujours": False,
    "raison": "Il garde le verdict 'la branche MachinePlatform d'`UnitExtensions$$GetMachine` "
              "n'est atteinte par AUCUN vecteur' : 0 ability `TargetIsMachine`, une seule "
              "`TargetIsActor` (1160), et le natif lui remet la MACHINE. Un changement de build "
              "peut renumeroter les bits du masque, d'ou `build: True`.",
}

from engine.runner.abilities.handler import ABILITY_CLASSES            # noqa: E402
from engine.runner.abilities.targeting_rule import TargetingRule as TR  # noqa: E402
from engine.runner.abilities.behaviours import context as CTX           # noqa: E402
from engine.runner.components import MachineComponent, UnitComponent    # noqa: E402
from engine.runner.state import State                                   # noqa: E402


def _porteurs(bit: int) -> list:
    """Les entrees du registre dont le masque de ciblage porte `bit`, par ORDINAL d'ability."""
    out = []
    for aid, cls in sorted(ABILITY_CLASSES.items()):
        opts = getattr(cls, "TARGETING_OPTIONS", None)
        if opts is None:
            continue
        if int(getattr(opts, "rules", 0) or 0) & int(bit):
            out.append(int(aid))
    return out


def test_le_registre_est_non_vide_et_porte_des_masques():
    """TEMOIN DE NON-DEGENERESCENCE, et il n'est pas decoratif.

    Les deux assertions qui suivent sont des comptes ATTENDUS BAS (0 et 1). Sur un registre vide,
    sur un `TargetingRule` renomme, ou sur un `TARGETING_OPTIONS` devenu introuvable, elles
    passeraient toutes les deux au vert en n'ayant RIEN regarde. On exige donc d'abord que le
    gisement existe -- meme discipline que le « assertionner son propre non-vide » du CLAUDE.md."""
    assert len(ABILITY_CLASSES) > 100, (
        "registre d'abilities anormalement petit (%d) -- les comptes ci-dessous seraient vacants"
        % len(ABILITY_CLASSES))
    avec_masque = [aid for aid, cls in ABILITY_CLASSES.items()
                   if getattr(cls, "TARGETING_OPTIONS", None) is not None]
    assert len(avec_masque) > 100, (
        "seules %d entrees portent un TARGETING_OPTIONS -- un balayage de masques ne mesurerait "
        "rien" % len(avec_masque))
    # Les DEUX bits doivent exister sous ces noms-la, sinon `_porteurs` rendrait 0 par erreur de
    # nom et non par absence de porteur.
    assert int(TR.TargetIsMachine) == 1 << 44
    assert int(TR.TargetIsActor) == 1 << 46


def test_aucune_ability_ne_cible_une_machine_donc_la_branche_plateforme_reste_non_portee():
    """LE CLIQUET. `TargetIsMachine` est la SEULE voie qui envoie une cible directement a
    `machine_id()` sans passer par `unit_id()` d'abord (cf. `actual_target` : la branche MACHINE
    n'essaie PAS `GetUnit`, seule la branche ACTOR enchaine les deux).

    Tant que ce compte vaut 0, aucun vecteur ne peut remettre une entite `MachinePlatform` a
    `machine_id()` par cette porte."""
    porteurs = _porteurs(TR.TargetIsMachine)
    assert porteurs == [], (
        "REACHABILITE OUVERTE : les abilities %s portent desormais `TargetIsMachine`. La branche "
        "`EntityType == 7` d'`IdunBattle.Entities.UnitExtensions$$GetMachine` "
        "(-> `TileExtensions$$GetMachinePlatformContent`) devient EXIGIBLE, et le substrat est "
        "deja publie (`decisionView.mows[].platformIds`, tri-etat). Porter #287-r14-r2, avec le "
        "vecteur de confrontation que ces abilities fournissent." % porteurs)


def test_la_seule_ability_ACTOR_est_1160_et_le_natif_lui_remet_la_MACHINE_pas_sa_plateforme():
    """La seconde porte, et la mesure live qui la ferme.

    `TargetIsActor` fait `unit_id(target) ?? machine_id(target)`. Elle POURRAIT donc atteindre la
    branche plateforme -- si un canal remettait un id de plateforme. MESURE (cf. l'en-tete) :
    `abilityTargets` rend `[77, 79]`, ou `79` est l'entite **Machine**, et l'intersection avec les
    plateformes publiees est VIDE.

    Ce test fige l'IDENTITE du porteur : si une seconde ability entre avec ce bit, la mesure live
    de l'en-tete ne la couvre plus et doit etre rejouee."""
    assert _porteurs(TR.TargetIsActor) == [1160], (
        "la population `TargetIsActor` a change -- la mesure live de l'en-tete (abilityTargets sur "
        "1160 rend la MACHINE, jamais une plateforme) ne couvre plus le registre. La rejouer avant "
        "de conclure quoi que ce soit sur #287-r14-r2.")


def test_machine_id_rend_l_entite_ELLE_MEME_sur_une_Machine_ce_que_le_natif_fait_aussi():
    """La branche REELLEMENT exercee (`EntityType == 6` -> `return entity`), portee et confrontee.

    C'est la contre-epreuve du cliquet ci-dessus : le port n'est pas « aveugle aux MoW », il est
    aveugle a un cas que le natif ne produit pas. MESURE LIVE, meme runner : `machine_id(79) = 79`
    et `machine_id(80) = 80`, `79` etant exactement l'id que `abilityTargets` propose."""
    st = State()
    mow = st.add_entity(79)
    mow.add_component(UnitComponent(visual_id="orksRukkatrukk", alive=True))
    mow.add_component(MachineComponent(slot=1))
    assert CTX.machine_id(st, 79) == 79

    # Une entite SANS `MachineComponent` -- l'autre moitie du mirror : le natif rend `null` sur
    # tout ce qui n'est ni Machine (6) ni MachinePlatform (7), et sur une plateforme dont le
    # `MachineId` n'a pas de valeur. Le port rend `None` dans les deux cas.
    unite = st.add_entity(77)
    unite.add_component(UnitComponent(visual_id="custoVexilusPraetor", alive=True))
    assert CTX.machine_id(st, 77) is None
    # Un id ABSENT du state : c'est le cas d'une plateforme non publiee (`MachineId.HasValue`
    # faux cote natif -> pas dans `platformIds` -> aucune entite cote port). Le natif y rend
    # `null` par `if (!machineId.HasValue) return null`, le port par « entite inconnue ».
    assert CTX.machine_id(st, 75) is None
    # Et les entrees degenerees, qui ne doivent pas lever.
    assert CTX.machine_id(st, None) is None
    assert CTX.machine_id(st, "pas-un-id") is None


if __name__ == "__main__":                                  # pragma: no cover
    raise SystemExit(pytest.main([__file__, "-q"]))
