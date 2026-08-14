"""#1071 OFFLINE -- le VERDICT sur `RepairEnthusiast` (`TriggeredAbilityType` 0x5ea = 1514), grave.

Ce passif est `GAP-ABSENT` dans `docs/rl/passive-ability-coverage.md`, et cette tranche conclut
**NON PORTE -- ETAGE MANQUANT**, pas << non confrontable >>. Les deux affirmations qui fondent ce
verdict sont RE-DERIVEES ici des tables du build, jamais citees : un verdict de non-portage qui
repose sur une phrase de case-doc se perime en silence, et c'est exactement ce que ce fichier
empeche.

LES TROIS FAITS GRAVES
======================

1. **Il n'a AUCUNE face COMBAT** -- il n'existe pas de `RepairEnthusiastAbility` dans le build.
   ⚠ << le symbole n'apparait pas dans la table >> ne prouve normalement RIEN (IL2CPP DEDUPLIQUE
   les corps de METHODE, et les bases generiques sont absentes du dump Frida). Le controle ci-
   dessous evite ce piege sur deux points : il interroge `frida/classes.tsv`, qui est indexee par
   CLASSE et non par ADRESSE -- la dedup ICF n'y opere donc pas --, et il exige DEUX TEMOINS
   POSITIFS du meme patron (`VengeanceForTheOmnissiah`, `OmnissiahsBlessing`, les deux autres
   passifs de la meme tranche), sans quoi un critere structurellement aveugle passerait pour vert.

2. **Sa face MOVE est un corps TRIVIAL**, donc son absence du registre EST le comportement natif.
   La taille est re-derivee du delta d'adresses de `ghidra/functions.tsv`, et calibree sur un
   corps trivial CONNU (`VengeanceForTheOmnissiahPlaybook.<CalculateAttackUtilityInStepsInternal>`,
   lu au decompile : `yield return Fix64.op_Implicit(0)`) plutot que sur un seuil invente.

3. **Sa face REPAIR est un corps REEL, et l'ETAGE qui la consommerait n'existe pas cote port** :
   aucune methode `calculate_repair_utility_in_steps`, aucun registre REPAIR, aucun
   `evaluate_repair_in_steps` sur le dispatcher `TriggeredAbilitiesUtility(2)`. Monter un
   dispatcher dont le registre serait vide est le patron #419 que ce depot REFUSE -- le refus est
   deja ecrit et argumente dans `engine/playbook/non_owner_attack.py` (residu #271-r7).

LE CRAN QUI FAIT SA VALEUR
==========================
L'etage 3 est un cliquet INVERSE : il rougit le jour ou quelqu'un MONTE l'etage REPAIR. A ce
moment-la, `RepairEnthusiast` doit etre inscrit -- et sans ce test, personne ne le saurait, puisque
le portage de l'etage et celui de la feuille sont deux tranches differentes. C'est la seule facon
de rendre un residu << bloque par un etage >> auto-rappelant.

CE QUE CE FICHIER NE FAIT PAS : porter quoi que ce soit. Le corps REPAIR est LU (cf. la case-doc
`docs/rl/case-1071-passifs-admec-votann.md`), il n'est pas mirroire -- un port sans consommateur
serait du code que rien n'itere.
"""
from __future__ import annotations

#: Ce qui doit changer pour que ce FICHIER puisse changer de verdict (#486-r15).
DECLENCHEUR = {
    "chemins": (
        # Les tables du build sont lues DIRECTEMENT (elles ne sont dans aucune fermeture d'imports).
        "data/symbols/*/frida/classes.tsv",
        "data/symbols/*/ghidra/functions.tsv",
        # Les foyers ou l'etage REPAIR apparaitrait : c'est eux qui doivent faire rougir l'etage 3.
        "scripts/python/engine/playbook/adjacent_unit_preference.py",
        "scripts/python/engine/playbook/psyker.py",
        "scripts/python/engine/playbook/non_owner.py",
        "scripts/python/engine/playbook/non_owner_attack.py",
        "scripts/python/engine/utilities/tile.py",
    ),
    "build": True,
    "toujours": False,
    "raison": (
        "Offline : grave le verdict NON PORTE / ETAGE MANQUANT de `RepairEnthusiast` (1514) en le "
        "RE-DERIVANT des tables du build -- absence de classe d'ability (avec DEUX temoins "
        "positifs), face MOVE triviale (taille calibree sur un corps trivial connu), face REPAIR "
        "reelle. Son etage 3 est un cliquet INVERSE : il rougit quand l'etage REPAIR est monte "
        "cote port, pour qu'on pense a inscrire la feuille a ce moment-la."
    ),
}

from pathlib import Path        # noqa: E402  (le DECLENCHEUR doit rester en tete)

import pytest

from engine.entities.triggered_ability_type import TriggeredAbilityType     # noqa: E402

REPAIR_ENTHUSIAST = "RepairEnthusiast"
REPAIR_ENTHUSIAST_ID = int(TriggeredAbilityType.RepairEnthusiast)           # 0x5ea = 1514
#: Les DEUX porteurs, tous deux hors pool : le SUMMON d'`EcogSupport` (passif de `votanIronmaster`
#: << Vynn >>, HERO) et son jumeau npc, apparies par `visualId`.
PORTEUR_SUMMON = "votanSmnEcog"
PORTEUR_NPC = "votanNpc1Ecog"
#: TEMOINS POSITIFS -- deux passifs qui, eux, ONT une classe d'ability. Sans eux, un critere
#: structurellement aveugle (mauvais separateur, mauvaise colonne, table vide) rendrait le meme
#: << absent >> et passerait pour vert.
TEMOINS = ("VengeanceForTheOmnissiah", "OmnissiahsBlessing")

_RACINE = Path(__file__).resolve().parents[4]


def _table(rel: str) -> Path:
    """La table du build COURANT. On ne code pas le hash en dur : `data/symbols/` n'en contient
    qu'un jeu par build, et le fichier le plus recent est celui du build charge."""
    base = _RACINE / "data" / "symbols"
    cands = sorted(base.glob("*/" + rel))
    if not cands:
        pytest.skip("table absente du checkout : data/symbols/*/%s" % rel)
    return max(cands, key=lambda p: p.stat().st_mtime)


def _classes() -> list[str]:
    p = _table("frida/classes.tsv")
    return [ln.split("\t", 1)[0] for ln in p.read_text(encoding="utf-8", errors="replace").splitlines()
            if ln.strip()]


def _tailles() -> dict:
    """Taille de chaque fonction = delta d'adresses sur `ghidra/functions.tsv` TRIEE. C'est la seule
    mesure de corps disponible offline ; elle sur-estime la derniere fonction d'une section, ce qui
    est sans effet ici (on ne compare que des corps courts a un corps trivial CONNU)."""
    p = _table("ghidra/functions.tsv")
    rows = []
    for ln in p.read_text(encoding="utf-8", errors="replace").splitlines():
        parts = ln.split("\t")
        if len(parts) >= 2:
            try:
                rows.append((int(parts[0], 16), parts[1]))
            except ValueError:
                continue
    rows.sort()
    return {n: (rows[i + 1][0] - a) for i, (a, n) in enumerate(rows) if i + 1 < len(rows)}


# ------------------------------------------------------------------- 1. le PORTEUR et sa VOIE
def test_l_ability_et_ses_deux_porteurs():
    """Le passif existe, son ordinal est fige AU SITE, et ses deux porteurs le portent par la voie
    `passiveAbilities` -- donc `TriggeredAbilityType`, jamais `ActiveAbilityType` (l'ordinal 1514
    n'est d'ailleurs pas un membre de ce dernier)."""
    import gameconfig as GC
    from engine.entities.active_ability_type import ActiveAbilityType
    assert REPAIR_ENTHUSIAST_ID == 1514 == 0x5ea
    assert getattr(ActiveAbilityType, REPAIR_ENTHUSIAST, None) is None, \
        "1514 nommerait aussi une ACTIVE : l'appariement par la voie ne suffirait plus"
    for uid in (PORTEUR_SUMMON, PORTEUR_NPC):
        u = GC.unit(uid) or {}
        assert REPAIR_ENTHUSIAST in (u.get("passiveAbilities") or []), uid
        assert not (u.get("activeAbilities") or []), uid
    # Le jumeau npc est apparie par `visualId` -- c'est la voie d'arrivee en bataille (MIRROR).
    assert (GC.unit(PORTEUR_SUMMON) or {}).get("visualId") == PORTEUR_NPC
    # Et le SUMMON a bien un invocateur, contrairement au cas #1052 : `EcogSupport`, portee par
    # `votanIronmaster` << Vynn >> (HERO). Ce n'est donc PAS un summon orphelin.
    assert ((GC.ability("EcogSupport") or {}).get("constants") or {}).get("unitId") == PORTEUR_SUMMON


def test_le_porteur_REPARE_donc_la_face_repair_est_ATTEIGNABLE_in_game():
    """Le trait `Mechanic` accorde l'action de REPARATION (<< Can repair a friendly Mechanical unit
    as its action >>). Sans lui, la face REPAIR du playbook serait de toute facon morte, et le
    verdict << etage manquant >> serait le mauvais diagnostic."""
    import gameconfig as GC
    for uid in (PORTEUR_SUMMON, PORTEUR_NPC):
        assert "Mechanic" in ((GC.unit(uid) or {}).get("traits") or []), uid


# --------------------------------------------------- 2. AUCUNE face COMBAT (avec DEUX temoins)
def test_il_n_existe_AUCUNE_classe_d_ability_pour_ce_passif():
    """Cf. l'en-tete, point 1 : `classes.tsv` est indexee par CLASSE (pas par adresse), donc la
    dedup ICF ne s'y applique pas -- et les DEUX temoins positifs etablissent que le critere VOIT
    ce qu'il cherche."""
    classes = _classes()
    for t in TEMOINS:                       # LES TEMOINS D'ABORD : un critere aveugle rendrait 0
        assert any(c.endswith("." + t + "Ability") for c in classes), \
            ("TEMOIN %s : aucune classe d'ability trouvee -- le critere est aveugle, "
             "le verdict sur RepairEnthusiast ne vaut RIEN" % t)
    assert not [c for c in classes if c.endswith("." + REPAIR_ENTHUSIAST + "Ability")], \
        ("une `RepairEnthusiastAbility` est apparue : le passif a desormais une face COMBAT, "
         "ce verdict est PERIME -- la porter et mettre a jour la case-doc")
    # Corollaire lisible : pas d'instanciation FERMEE du playbook generique non plus (elle nomme
    # l'ability), la ou les deux temoins en ont une.
    ferme = "IdunBattle.AI.Playbook.TriggeredAbilityPlaybook<"
    assert not [c for c in classes if c.startswith(ferme) and REPAIR_ENTHUSIAST in c]
    for t in TEMOINS:
        assert [c for c in classes if c.startswith(ferme) and t in c], t


def test_le_playbook_lui_EXISTE():
    """Contre-epreuve du precedent : ce qui manque est l'ABILITY, pas le passif. Si cette assertion
    tombait aussi, le verdict serait << le passif a disparu du build >>, pas << il est purement
    AI >> -- deux causes que le test ne doit pas confondre."""
    classes = _classes()
    assert "IdunBattle.AI.Playbook.Loki.RepairEnthusiastPlaybook" in classes


# ------------------------------------------- 3. face MOVE TRIVIALE / face REPAIR REELLE
def test_la_face_MOVE_est_TRIVIALE_donc_son_absence_du_registre_est_JUSTE():
    """Corps lu au decompile : `yield return Fix64.op_Implicit(0)`, un seul step, aucune lecture
    d'etat. L'inscrire ferait rougir `test_419_playbook_wiring_ratchet_offline` (entree sur un
    corps trivial) -- et n'ajouterait rien, un step a 0 ne se distinguant pas d'un playbook absent.

    Le SEUIL n'est pas invente : il est CALIBRE sur un corps trivial CONNU du meme build, la face
    ATTAQUE de `VengeanceForTheOmnissiahPlaybook`, elle aussi lue au decompile."""
    t = _tailles()
    pfx = "IdunBattle.AI.Playbook.Loki."
    trivial_connu = t.get(pfx + "VengeanceForTheOmnissiahPlaybook."
                          "u003CCalculateAttackUtilityInStepsInternalu003Ed__3$$MoveNext")
    move = t.get(pfx + "RepairEnthusiastPlaybook."
                 "u003CCalculateMovementUtilityInStepsInternalu003Ed__2$$MoveNext")
    reel_connu = t.get(pfx + "VengeanceForTheOmnissiahPlaybook."
                       "u003CCalculateMovementUtilityInStepsInternalu003Ed__2$$MoveNext")
    for nom, v in (("trivial_connu", trivial_connu), ("move", move), ("reel_connu", reel_connu)):
        assert v, "taille NON MESUREE pour %s -- aucune conclusion possible" % nom
    assert move <= trivial_connu, \
        "la face MOVE (0x%x) depasse le corps trivial de reference (0x%x) : la RE-LIRE" % (
            move, trivial_connu)
    # Le calibrage SEPARE bien : un corps reel du meme build est nettement plus gros.
    assert reel_connu > 2 * trivial_connu, \
        "le calibre ne discrimine pas trivial/reel -- le seuil ne prouve rien"


def test_la_face_REPAIR_est_un_corps_REEL():
    """C'est ce qui rend le residu #1071-r1 non vide : il y a bien quelque chose a porter, et la
    seule raison de ne pas le faire est l'absence d'etage consommateur (etage 4)."""
    t = _tailles()
    pfx = "IdunBattle.AI.Playbook.Loki."
    repair = t.get(pfx + "RepairEnthusiastPlaybook."
                   "u003CCalculateRepairUtilityInStepsInternalu003Ed__3$$MoveNext")
    base = t.get("IdunBattle.AI.Playbook.TriggeredAbilityPlaybooku003C"
                 "__Il2CppFullySharedGenericTypeu003E$$CalculateRepairUtilityInStepsInternal")
    assert repair and base, "tailles NON MESUREES -- aucune conclusion possible"
    assert repair > base, \
        ("la face REPAIR ne depasse plus le corps de la BASE (qui yield 0) : elle serait "
         "triviale, et le residu #1071-r1 deviendrait vide -- la RE-LIRE")


def test_le_poids_BC_de_la_face_REPAIR_existe():
    """`RepairEnthusiast_LikesRepair` est present dans la capture, ce qui atteste que la face
    REPAIR est bien alimentee cote natif -- un poids absent signerait une face morte."""
    import json
    bc = json.loads((_RACINE / "data" / "seed-bc.json").read_text(encoding="utf-8"))
    poids = ((bc.get("Utilities") or {}).get("Default") or {}).get("TriggeredAbilities") or {}
    assert "RepairEnthusiast_LikesRepair" in poids
    assert int(poids["RepairEnthusiast_LikesRepair"]) > 0


# --------------------------------- 4. LE CLIQUET INVERSE : l'etage REPAIR n'existe pas (encore)
def test_le_passif_n_est_inscrit_NULLE_PART_et_c_est_JUSTE_pour_l_instant():
    """Tant que l'etage REPAIR n'existe pas, l'inscrire serait du code que rien n'itere."""
    from engine.playbook.adjacent_unit_preference import TRIGGERED_MOVE_PLAYBOOKS
    from engine.playbook.psyker import TRIGGERED_ATTACK_PLAYBOOKS
    from engine.runner.operations.triggers.dispatch import registry as REG
    assert REPAIR_ENTHUSIAST_ID not in TRIGGERED_MOVE_PLAYBOOKS
    assert REPAIR_ENTHUSIAST_ID not in TRIGGERED_ATTACK_PLAYBOOKS
    for d in (REG.ABILITY_TRIGGERS, REG.TRAIT_TRIGGERS, REG.ACTIVE_ABILITY_TRIGGERS,
              REG.RELIC_ABILITY_TRIGGERS, REG.PASSIVE_HELPER_ABILITY_TRIGGERS):
        assert REPAIR_ENTHUSIAST not in d


def test_CLIQUET_INVERSE_l_etage_REPAIR_du_port_n_existe_toujours_pas():
    """⚠ CE TEST EST FAIT POUR ROUGIR UN JOUR, et c'est sa raison d'etre.

    Le jour ou l'etage REPAIR est monte cote port -- une methode
    `calculate_repair_utility_in_steps` sur un playbook, un registre REPAIR, ou un
    `evaluate_repair_in_steps` sur le dispatcher `TriggeredAbilitiesUtility(2)` --, ce test tombe
    et rappelle qu'il faut alors INSCRIRE `RepairEnthusiast` (et re-lire son corps `0xe0`).

    Sans ce cran, le portage de l'etage et celui de la feuille sont deux tranches differentes, et
    la seconde serait simplement oubliee : c'est ce qui transforme un residu << bloque par un
    etage >> en quelque chose qui se rappelle tout seul. Residu #1071-r1 ; le refus d'origine est
    ecrit dans `engine/playbook/non_owner_attack.py` (#271-r7).

    ⚠ ON NE SE FIE PAS AU SEUL NOM DE METHODE : le balayage porte sur les DEUX registres existants
    ET sur le dispatcher, parce qu'un etage peut apparaitre par l'un sans l'autre."""
    from engine.playbook.adjacent_unit_preference import TRIGGERED_MOVE_PLAYBOOKS
    from engine.playbook.psyker import TRIGGERED_ATTACK_PLAYBOOKS
    from engine.utilities import tile as TILE

    porteurs = list(TRIGGERED_MOVE_PLAYBOOKS.values()) + list(TRIGGERED_ATTACK_PLAYBOOKS.values())
    assert porteurs, "les deux registres sont VIDES -- le balayage ne prouverait rien"
    avec_repair = sorted({type(p).__name__ for p in porteurs
                          if hasattr(p, "calculate_repair_utility_in_steps")})
    assert not avec_repair, (
        "l'etage REPAIR est APPARU (%s) : inscrire `RepairEnthusiast` (1514) -- corps 0xe0, "
        "gate `actor != target && NOT HasTriggeredAbility(target, 1514)`, poids "
        "`RepairEnthusiast_LikesRepair`. Cf. docs/rl/case-1071-passifs-admec-votann.md" % avec_repair)

    dispatcher = getattr(TILE, "TriggeredAbilitiesUtility", None)
    assert dispatcher is not None, "le dispatcher a change de nom -- re-lire avant de conclure"
    assert hasattr(dispatcher, "evaluate"), "le dispatcher n'a plus sa face MOVE -- re-lire"
    assert not hasattr(dispatcher, "evaluate_repair_in_steps"), (
        "le dispatcher REPAIR est APPARU : inscrire `RepairEnthusiast` (1514). "
        "Cf. docs/rl/case-1071-passifs-admec-votann.md")
