"""#936 -- `WrathfulDevotion` (passif `worldTerminator`, triggered 1214) confronte au JEU, ses DEUX
faces, sur le meme etat de depart et le meme flux PRNG.

RE + residus : `engine/runner/operations/triggers/loki/wrathful_devotion.py`.
Montage, temoins et mesure du 2026-08-11 : `scripts/python/probe_936_wrathful_devotion.py`.

CE QUE CE FICHIER GARDE, ET QUE L'OFFLINE NE PEUT PAS :
  * le MONTANT du bouclier au PV pres (`shieldHp[niveau] x multiplicateur de rarete`), qui n'existe
    qu'en regime normalise -- 3989 au rank 17 ;
  * la DUREE telle que le jeu la compte (`TurnsFromRounds(1)` = 2 tours a deux joueurs) ;
  * le fait que `combatSnapshot.units[].traits` porte REELLEMENT le pseudo-trait d'alliance
    `Chaos` (0x7ea) -- sans quoi le bras `UnitsWithTrait` du selecteur serait inerte en live et
    vivant offline, l'exact contraire d'une garde ;
  * la CHAINE d'emission de la face B : `finish` -> T3 d'`ATeleportingEffect` retire `1035` ->
    `RemoveEffectOperation$$Execute` publie `On(0x3b)`. Le canal a ete AJOUTE par cette tranche ;
    sans confrontation live, un port qui l'emettrait au mauvais rang serait indiscernable ;
  * et le VERDICT DEAD, vu du jeu : sur la face A (kill en melee), le NATIF lui-meme ne pose
    AUCUN marqueur visuel -- ni `Teleported`, ni surtout `Killed`.

ASCII only.
"""
from __future__ import annotations

import pytest

import probe_936_wrathful_devotion as P

DECLENCHEUR = {
    "chemins": (
        # le port et son inscription
        "scripts/python/engine/runner/operations/triggers/loki/wrathful_devotion.py",
        "scripts/python/engine/runner/operations/triggers/dispatch/registry.py",
        # le montage LIVE (c'est LUI qui produit toutes les mesures de ce fichier)
        "scripts/python/probe_936_wrathful_devotion.py",
        # les DEUX emetteurs dont depend chaque face -- dont celui AJOUTE par la tranche
        "scripts/python/engine/runner/operations/remove_effects.py",
        "scripts/python/engine/runner/operations/triggers/dispatch/move_death.py",
        "scripts/python/engine/runner/operations/triggers/dispatch/core.py",
        # le gate de TYPE de l'emetteur, et la famille d'effets qui le declenche
        "scripts/python/engine/entities/effects/aura_selectors.py",
        "scripts/python/engine/runner/operations/triggers/loki/teleporting_in.py",
        # les feuilles et le contexte que le behaviour lit
        "scripts/python/engine/runner/abilities/behaviours/effects.py",
        "scripts/python/engine/runner/abilities/behaviours/context.py",
        "scripts/python/engine/entities/selectors/units.py",
        "scripts/python/engine/entities/selectors/accessors.py",
        "scripts/python/engine/runner/abilities/base.py",
        # la base des triggers et le seed d'etat
        "scripts/python/engine/runner/operations/triggers/base.py",
        "scripts/python/engine/runner/snapshot.py",
        # le harnais live
        "scripts/python/tests/conftest.py", "scripts/python/tests/engine/conftest.py",
        "scripts/python/tests/engine/runner/conftest.py",
    ),
    # Le montage joue une bataille REELLE et compare des boucliers au PV pres : un changement de
    # build (stats normalisees, multiplicateur de rarete, table `shieldHp`) peut le faire basculer
    # sans qu'un fichier du depot bouge.
    "build": True,
    "toujours": False,
    "raison": "Il confronte les DEUX faces de `WrathfulDevotion` au jeu : le montant exact du "
              "bouclier en regime normalise, sa duree telle que le natif la compte, la presence "
              "REELLE du pseudo-trait d'alliance dans le canal de traits, la chaine d'emission du "
              "vecteur `On(UnitBecameTargetable)` AJOUTE par cette tranche, et le verdict DEAD vu "
              "du jeu (aucun marqueur sur la face kill).",
}

#: `shieldHp[49] x 180 %` au rank 17 (mesure du 2026-08-11). Le montant EXACT, pas un seuil : un
#: port qui lirait le mauvais palier, oublierait le multiplicateur ou prendrait `hp` a la place de
#: `shieldHp` rendrait un autre nombre, et l'egalite live/port ne suffirait pas a le voir si les
#: deux cotes lisaient la meme mauvaise cle.
BOUCLIER_ATTENDU = 3989


@pytest.fixture(scope="module")
def face_b(live_session):
    """Regime B monte UNE fois pour le fichier (un build + une bataille pilotee)."""
    return P.run_face_b()


@pytest.fixture(scope="module")
def face_a(live_session):
    """Regime A monte UNE fois pour le fichier (un build + une approche pilotee)."""
    return P.run_face_a()


# ------------------------------------------------------------------ le montage lui-meme
def test_le_porteur_arrive_bien_sous_TeleportStrike_TeleportingIn(face_b):
    """Sans `1035` sur le porteur au depart, le regime B ne mesure RIEN : `finish` ne retirerait
    aucun effet untargetable, donc `On(0x3b)` ne serait pas publie et les DEUX cotes rendraient
    zero -- un ACCORD EN REGIME DEGENERE. C'est la premisse du fichier, elle est assertionnee."""
    assert "TeleportStrike_TeleportingIn" in face_b["effets_porteur_avant"], (
        f"le porteur n'arrive plus en Deep Strike : {face_b['effets_porteur_avant']}")
    assert all(v == 0 for v in face_b["avant"]["live"].values()), (
        f"des boucliers PREEXISTENT au depart : {face_b['avant']['live']}")
    assert face_b["avant"]["live"] == face_b["avant"]["port"], (
        "les etats de depart divergent DEJA -- toute comparaison d'apres serait ininterpretable")


# --------------------------------------------------------------------------- FACE B
def test_face_B_le_bouclier_va_au_porteur_et_a_l_allie_CHAOS_adjacent(face_b):
    """`CreateShield(Owner + UnitsWithTrait(AdjacentFriends(Owner, 1, 3), Chaos, 3), ...)`.

    Le temoin qui porte tout le poids est `orksNob` : ADJACENT et ALLIE, mais **Xenos**. Un port
    qui aurait oublie `UnitsWithTrait(Chaos)` le servirait, et rien d'autre ne le montrerait."""
    u, live, port = face_b["uids"], face_b["live"], face_b["port"]
    assert live["shields"].get(u[P.PORTEUR]) == BOUCLIER_ATTENDU, (
        f"bouclier NATIF du porteur = {live['shields'].get(u[P.PORTEUR])} "
        f"(attendu {BOUCLIER_ATTENDU} = shieldHp[49] x 180 %)")
    assert live["shields"].get(u[P.ALLIE_CHAOS]) == BOUCLIER_ATTENDU, (
        "l'allie Chaos adjacent n'a pas recu le bouclier COTE NATIF -- le montage a bouge "
        "(adjacence ?), pas le port")
    assert live["shields"].get(u[P.ALLIE_XENOS]) == 0, (
        "l'allie XENOS adjacent a recu un bouclier COTE NATIF : le gate `UnitsWithTrait(Chaos)` "
        "n'existe plus, re-lire `$$CreateBehaviour`")
    for nom in (P.PORTEUR, P.ALLIE_CHAOS, P.ALLIE_XENOS, P.VICTIME):
        assert port["shields"].get(u[nom], 0) == live["shields"].get(u[nom], 0), (
            f"ECART live/port sur {nom} : live={live['shields'].get(u[nom])} "
            f"port={port['shields'].get(u[nom])}")


def test_face_B_le_marqueur_TELEPORTED_est_pose_sur_exactement_les_cibles_du_bouclier(face_b):
    """`Foreach(targets, t => If(NOT HasEffect(t, 0x518, 0, Both), AddEffect(0x518, ..., targets,
    Direct(1))))` -- le lambda `b__1`, celui de la branche VIVANTE du `switch (triggerType)`."""
    u, live, port = face_b["uids"], face_b["live"], face_b["port"]
    attendu = sorted([u[P.PORTEUR], u[P.ALLIE_CHAOS]])
    assert live["teleported"] == attendu, (
        f"porteurs NATIFS du marqueur = {live['teleported']} (attendu {attendu} = les cibles "
        "du bouclier, et elles seules)")
    assert port["teleported"] == live["teleported"], (
        f"ECART live/port sur le marqueur : live={live['teleported']} port={port['teleported']}")


# --------------------------------------------------------------------------- FACE A
def test_face_A_un_kill_en_melee_donne_le_bouclier_au_porteur(face_a):
    """`On(UnitDefeated) & OwnerIsActor & IsDefeatedByMeleeAttack(Target, 0, 1)`.

    L'allie Chaos est reste LOIN dans ce regime : il est ici le temoin NEGATIF du bras
    `AdjacentFriends`, dont la face B a montre le bras POSITIF."""
    u, live, port = face_a["uids"], face_a["live"], face_a["port"]
    assert face_a["victime_morte"], (
        f"la victime n'est pas morte ({face_a['hp_apres']}) -- le trigger `On(UnitDefeated)` n'a "
        "pas pu etre publie, la mesure est vide")
    assert live["shields"].get(u[P.PORTEUR]) == BOUCLIER_ATTENDU, (
        f"bouclier NATIF du porteur apres son kill = {live['shields'].get(u[P.PORTEUR])} "
        f"(attendu {BOUCLIER_ATTENDU})")
    assert live["shields"].get(u[P.ALLIE_CHAOS], 0) == 0, (
        "l'allie Chaos LOIN a recu un bouclier COTE NATIF : le bras `AdjacentFriends` a disparu")
    for nom in (P.PORTEUR, P.ALLIE_CHAOS, P.ALLIE_XENOS):
        assert port["shields"].get(u[nom], 0) == live["shields"].get(u[nom], 0), (
            f"ECART live/port sur {nom} : live={live['shields'].get(u[nom])} "
            f"port={port['shields'].get(u[nom])}")


def test_face_A_le_NATIF_ne_pose_AUCUN_marqueur_visuel(face_a):
    """LE VERDICT DEAD, VU DU JEU.

    Le `switch (triggerType)` natif n'a de branche visuelle que pour `UnitDeath` (MORTE) et
    `UnitBecameTargetable` ; la face A arrive avec `UnitDefeated` et tombe donc en `default`. Si un
    build futur CORRIGEAIT le `switch` (en y mettant `UnitDefeated`), c'est CE test qui rougirait
    le premier -- et il accuserait le bon etage, puisqu'il regarde le NATIF, pas le port."""
    live, port = face_a["live"], face_a["port"]
    assert live["killed"] == [], (
        f"le NATIF pose desormais `WrathfulDevotionKilled_Visual` ({live['killed']}) : la branche "
        "`triggerType == UnitDeath` n'est PLUS morte -- re-lire `$$CreateTrigger` et porter `b__0`")
    assert live["teleported"] == [], (
        f"le NATIF pose `WrathfulDevotionTeleported_Visual` sur la face KILL ({live['teleported']}) "
        "-- le `switch` a change de branche")
    assert port["killed"] == [] and port["teleported"] == [], (
        f"le PORT pose un marqueur sur la face A : killed={port['killed']} "
        f"teleported={port['teleported']}")
