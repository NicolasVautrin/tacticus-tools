#!/usr/bin/env python
"""#1081 -- les DIX residus du foyer `engine/entities/effects/factory.py` : leurs premisses,
RE-MESUREES contre le code, et le CLIQUET qui empeche le champ `BLOCAGE:` de se perimer en silence.

POURQUOI CE FOYER, ET POURQUOI UN PROBE
=======================================

`docs/rl/index-foyers.md` (genere) designait `scripts/python/engine/entities/effects/factory.py`
comme le foyer le plus charge du depot : **10** residus y convergent. Une tranche de BLOCAGE y a
re-mesure les dix enonces (2026-08-14, `master` a `49bec900`).

Resultat brut : **cinq des dix premisses etaient PERIMEES**, et deux d'entre elles annoncaient
comme << a porter >> du code DEJA LIVRE par des tranches ulterieures. Le mode de panne est
toujours le meme -- une fiche est un INSTANTANE, le code avance, et rien ne confronte les deux.
C'est exactement ce que ce probe fait, mecaniquement.

CE QUE LE PROBE MESURE -- trois etages
======================================

* **etage 1 (INVENTAIRE)** : ce que le code PORTE aujourd'hui, lu dans les registres executables
  (`EFFECT_CLASSES`, `ABILITY_INIT_OWNER_EFFECTS`, `ABILITY_INIT_OWNER_FLAGS`,
  `RELIC_ABILITY_TRIGGERS`) et dans les signatures qui portent les etages nommes. Aucun compte
  n'est herite : tout est re-derive a chaque execution.

* **etage 2 (VERDICT)** : pour chacun des dix, la premisse TIENT-elle ? Le verdict est DERIVE de
  l'etage 1, jamais ecrit en dur. Une premisse REFUTEE est un RESULTAT : elle ferme le residu.

* **etage 3 (CLIQUET)** : le champ `BLOCAGE:` REELLEMENT ECRIT dans `docs/rl/backlog.md`
  concorde-t-il avec ce que l'etage 1 mesure ? Un champ perime rend le residu **indispatchable en
  silence** (un `capteur` / `porteur` / `etage` est ECARTE au dispatch), ce qui est pire que son
  absence -- personne ne relit un champ qui a l'air rempli.

  &#9888; Le champ se lit par le parseur AUTORITAIRE (`backlog_entries.lire`), jamais par un
  `grep` maison : l'etiquette `BLOCAGE: capteur` est citee des CENTAINES de fois entre backticks
  dans de la PROSE, et un critere par presence la prend pour le champ. Trois parseurs maison se
  sont deja fait prendre.

  &#9888; **ET LE PARSEUR AUTORITAIRE S'EST FAIT PRENDRE AUSSI (#1084).** Son marqueur acceptait
  un deux-points OPTIONNEL, donc il mordait sur le MOT en prose : `**BLOCAGE RE-MESURE ET
  CONFIRME**` rendait `RE`. MESURE sur les 1024 entrees : **4** champs hors vocabulaire et **34**
  entrees dont le `FOYER` capturait de la prose (**63 chemins fantomes**). Corrige dans
  `backlog_entries` -- le `:` est desormais obligatoire.

  &#9888; **LE TEMOIN N'EST PLUS UN COUPLE FIGE, ET C'EST LA LECON DE CETTE TRANCHE.** Il valait
  `("943-r7", "seeding")` ; la fiche a ete RESOLUE trois jours plus tard et son champ est passe a
  `aucun`, donc le cliquet rougissait sur un MOUVEMENT LEGITIME du backlog. Le temoin est
  desormais **DERIVE** (`temoins_de_parseur`) : toutes les entrees qui citent l'etiquette sans
  deux-points, avec exigence que le champ rendu reste du VOCABULAIRE, plus un cran de
  NON-DEGENERESCENCE (au moins une entree ou la lecture naive differe du champ rendu).

CE QUE LE PROBE NE FAIT PAS
===========================

Il ne juge PAS si un port est FIDELE -- seulement s'il EXISTE. << Present au registre >> et
<< confronte live >> sont deux axes distincts, et confondre les deux ferait fermer un residu sur
une inscription vide. Les verdicts de fidelite vivent dans les tests cibles de chaque tranche.

Usage :
    python scripts/python/probe_1081_premisses_foyer_factory.py            # les trois etages
    python scripts/python/probe_1081_premisses_foyer_factory.py --inventaire   # etage 1 seul
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

RACINE = Path(__file__).resolve().parents[2]
BACKLOG = RACINE / "docs" / "rl" / "backlog.md"

EX_OK = 0
EX_ROUGE = 1
EX_NON_MESURE = 99

#: Les dix residus du foyer, dans l'ordre de l'index genere.
LES_DIX = ("1023-r1", "922-r1", "924-r1", "927-r2", "952-r2",
           "961-r3", "965-r2", "966-r4", "999-r1", "999-r2")

#: ⚠ **LE TEMOIN DE PARSEUR ETAIT UN COUPLE FIGE, ET IL S'EST PERIME EN TROIS JOURS.**
#: Il valait `("943-r7", "seeding")` : la fiche a ete RESOLUE le 2026-08-15 et son champ est passe
#: a `aucun`, donc le cliquet rougissait sur un MOUVEMENT LEGITIME du backlog -- pas sur le vice
#: qu'il garde. Une contre-epreuve qui NOMME son temoin se perime avec lui (meme lecon que
#: l'etage [5] de `test_1041`, qui citait deux couples en dur).
#:
#: La propriete VRAIE, elle, ne se perime pas : **le parseur rend le CHAMP, jamais une occurrence
#: de l'etiquette en PROSE**. On la DERIVE du backlog -- les temoins sont toutes les entrees dont
#: la ligne porte le mot `BLOCAGE` SANS deux-points (donc en prose), et le cran exige que le champ
#: rendu reste du VOCABULAIRE. Mesure du 2026-08-18 : ce gisement valait **4 champs hors
#: vocabulaire** (`RE` x2, `RETIRES`, `sont`) tant que `backlog_entries` acceptait `:?`.
_MOT_APRES = re.compile(r"`?([A-Za-z?]+)`?")
_ETIQUETTE_EN_PROSE = re.compile(r"BLOCAGE(?!\*{0,2}\s*:)")


def temoins_de_parseur(entrees) -> list:
    """Les entrees ou l'etiquette `BLOCAGE` est CITEE en prose (sans deux-points).

    Ce sont exactement celles ou un parseur par PRESENCE lit la citation a la place du champ."""
    return [e for e in entrees if _ETIQUETTE_EN_PROSE.search(e.brut)]


def _lecture_naive(brut: str) -> "str | None":
    """Ce que rendrait un parseur PAR PRESENCE : le premier mot apres la premiere occurrence de
    l'etiquette, deux-points ou non. Sert de CONTRE-MODELE -- il n'est jamais utilise comme
    mesure, seulement pour etablir que le temoin DISCRIMINE."""
    i = brut.find("BLOCAGE")
    if i < 0:
        return None
    m = _MOT_APRES.search(brut[i + len("BLOCAGE"):])
    return m.group(1) if m else None


# --------------------------------------------------------------------------- etage 1

def _registres():
    """Les registres EXECUTABLES du foyer, importes -- pas relus au texte.

    Passer par l'import (et non par un balayage de source) est ce qui rend la mesure fidele a ce
    que le moteur LIT : une entree commentee, ou ecrite dans un dict mort, ne compte pas."""
    from engine.entities.effects import factory as F
    try:
        from engine.runner.operations.triggers.dispatch import registry as REG
        relic = dict(getattr(REG, "RELIC_ABILITY_TRIGGERS", {}) or {})
    except Exception:                                        # pragma: no cover - defense
        relic = {}
    return {
        "EFFECT_CLASSES": dict(F.EFFECT_CLASSES),
        "ABILITY_INIT_OWNER_EFFECTS": dict(F.ABILITY_INIT_OWNER_EFFECTS),
        "ABILITY_INIT_OWNER_FLAGS": dict(F.ABILITY_INIT_OWNER_FLAGS),
        "TERTIARY_ABILITY_POSED_EFFECTS": dict(F.TERTIARY_ABILITY_POSED_EFFECTS),
        "RELIC_ABILITY_TRIGGERS": relic,
    }


def _porte(regs: dict, nom: str) -> dict:
    """Ou le NOM `nom` apparait-il ? (les registres sont keyes par NOM, jamais par ordinal --
    l'ordinal ne discrimine pas : `TriggeredAbilityType 1469` = `MawClawsOfThyrax` quand
    `EffectType 1469` = `MischiefMakers`.)"""
    return {
        "effect_classes": sorted(k for k in regs["EFFECT_CLASSES"] if k.startswith(nom)),
        "init_owner_effects": regs["ABILITY_INIT_OWNER_EFFECTS"].get(nom),
        "init_owner_flags": regs["ABILITY_INIT_OWNER_FLAGS"].get(nom),
        "tertiary_posed": regs["TERTIARY_ABILITY_POSED_EFFECTS"].get(nom),
        "relic_trigger": nom in regs["RELIC_ABILITY_TRIGGERS"],
    }


def _cle_posee(cle: str) -> list[str]:
    """Les fichiers d'`engine/**` qui POSENT la cle de contexte `cle` (`"<cle>":` dans un dict).

    Sert a distinguer un gate PORTE d'un gate INERTE : un effet dont le gate lit une cle que
    PERSONNE ne pose est materialise et muet -- le vice ferme par #462-r4b-r1-r1."""
    out = []
    for p in sorted((RACINE / "scripts" / "python" / "engine").rglob("*.py")):
        try:
            txt = p.read_text(encoding="utf-8")
        except OSError:                                      # pragma: no cover - defense
            continue
        if f'"{cle}":' in txt:
            out.append(str(p.relative_to(RACINE)).replace("\\", "/"))
    return out


def _signature_a(module: str, fonction: str, mot: str) -> bool | None:
    """Le parametre `mot` figure-t-il dans la SIGNATURE de `fonction` ? `None` = non mesure."""
    p = RACINE / "scripts" / "python" / module
    if not p.exists():
        return None
    lignes = p.read_text(encoding="utf-8").splitlines()
    for i, l in enumerate(lignes):
        if l.startswith(f"def {fonction}("):
            bloc = "\n".join(lignes[i:i + 8]).split('"""')[0]
            return mot in bloc
    return None


def inventaire() -> dict:
    """L'etat MESURE du code, re-derive. Toutes les cles sont consommees par l'etage 2."""
    regs = _registres()
    return {
        "registres": {k: len(v) for k, v in regs.items()},
        # #1023-r1 -- le canal DEGAT de 1365 MachineVengeance
        "MachineVengeance": _porte(regs, "MachineVengeance"),
        # #922-r1 -- owner-effects de RELIQUE a condition geometrique
        "IntoxicatingElixir": _porte(regs, "IntoxicatingElixir"),
        "AmuletOfTheVoidwyrm": _porte(regs, "AmuletOfTheVoidwyrm"),
        "NetherRealmCasket": _porte(regs, "NetherRealmCasket"),
        "spawn_lit_tertiaire": "tertiary_ability" in (
            RACINE / "scripts" / "python" / "engine" / "runner" / "operations" / "spawn.py"
        ).read_text(encoding="utf-8"),
        # #924-r1 -- face DEGAT d'EarlyWarningOverride (1145)
        "EarlyWarningOverride": _porte(regs, "EarlyWarningOverride"),
        # #927-r2 -- MischiefMakers (EffectType 1469), 2e porteur de HealBlockingEffect
        "MischiefMakers": _porte(regs, "MischiefMakers"),
        "FuryOfTheAncients": _porte(regs, "FuryOfTheAncients"),
        # #952-r2 -- GalvanicField : le canal FLAG existe-t-il ?
        "GalvanicField": _porte(regs, "GalvanicField"),
        "canal_flag_existe": bool(regs["ABILITY_INIT_OWNER_FLAGS"]),
        # #961-r3 -- SupaCyborkBody_CritDmgReduction
        "SupaCyborkBody": _porte(regs, "SupaCyborkBody"),
        "probe_961_passe_includeInactive": "includeInactive" in (
            RACINE / "scripts" / "python" / "probe_961_necron_passives.py"
        ).read_text(encoding="utf-8"),
        # #965-r2 -- la magnitude PAR COUP de WhisperingWeb (1579)
        "WhisperingWeb": _porte(regs, "WhisperingWeb"),
        "defender_modifiers_a_hit_index": _signature_a(
            "engine/runner/damage_model.py", "defender_modifiers", "hit_index"),
        # #966-r4 -- WayOfTheShortBlade : face COMBAT
        "WayOfTheShortBlade": _porte(regs, "WayOfTheShortBlade"),
        "poseurs_gate_wotsb": _cle_posee("friend_heroes_adjacent_to_target"),
        # #999-r1 / #999-r2 -- les mythiques de MoW
        "mythiques_r1": {n: _porte(regs, n) for n in (
            "BlightedLand", "ContemptuousDisregard", "HyperCorrosiveAcid",
            "CabalOfSorcerers", "MastersOfManoeuvre", "GuardianConstruct")},
        "mythiques_r2": {n: _porte(regs, n) for n in (
            "ShieldOfFaith", "OnMyPosition", "MoreGitzOverEre",
            "ElectrochaffBackups", "WisdomOfTheAncients")},
    }


def _est_porte(p: dict) -> bool:
    """Un NOM est PORTE des qu'il est lu par au moins un registre executable."""
    return bool(p["effect_classes"] or p["init_owner_effects"] or p["init_owner_flags"]
                or p["tertiary_posed"] or p["relic_trigger"])


# --------------------------------------------------------------------------- etage 2

def verdicts(inv: dict) -> dict:
    """Pour chacun des dix : la premisse TIENT-elle ? Chaque verdict est DERIVE de l'inventaire.

    `tient=True`  -> le residu reste ouvert tel qu'ecrit ;
    `tient=False` -> premisse REFUTEE : le residu se ferme, ou se reduit a son reliquat NOMME.

    `blocage_mesure` est le mot que la mesure JUSTIFIE ; l'etage 3 le confronte a l'ecrit."""
    v = {}

    # -- #1023-r1 : << le canal DEGAT de 1365 n'est PAS porte -- aucune classe dans EFFECT_CLASSES >>
    v["1023-r1"] = {
        "tient": not _est_porte(inv["MachineVengeance"]),
        "blocage_mesure": None,                              # FERME par #1081 : canal porte
        "note": "canal DEGAT porte (%s) -- bloc methodPointers segmente, 4 slots, 2 triviaux."
                % (inv["MachineVengeance"]["effect_classes"] or "-"),
    }
    # NOTE -- `ferme_attendu` : une fiche FERMEE ne porte plus ni `FOYER:` ni `BLOCAGE:` (c'est la
    # convention du backlog, et c'est ce qui la retire de `index-foyers.md`). L'etage 3 verifie donc
    # DEUX choses selon l'etat : pour une fiche ouverte, que le mot ECRIT vaut le mot MESURE ; pour
    # une fiche fermee, qu'il n'y a PLUS de mot. Sans ce second cran, rouvrir une fiche resolue en y
    # recollant un champ perime passerait inapercu.

    # -- #922-r1 : << une relique n'entre JAMAIS dans _seed_ability_owner_effects >>
    #    La MOITIE STRUCTURELLE est tombee (#1005 y lit `ctx.tertiary_ability`) ; ce qui reste est
    #    l'INSCRIPTION des trois owner-effects nommes.
    reste = [n for n in ("IntoxicatingElixir", "AmuletOfTheVoidwyrm", "NetherRealmCasket")
             if not inv[n]["init_owner_effects"]]
    v["922-r1"] = {
        "tient": bool(reste) and not inv["spawn_lit_tertiaire"],
        "blocage_mesure": "aucun",
        "note": ("voie tertiaire LUE par spawn.py=%s ; sans filet INIT_OWNER : %s"
                 % (inv["spawn_lit_tertiaire"], reste or "aucun")),
    }

    # -- #924-r1 : << la face DEGAT de 1145 est vivante et non portee >>
    #    RE-MESURE 2026-08-18 (#1084) : la fiche est FERMEE et sa MAJ ecrit << l'attribution
    #    `etage` de #924-r2 est REFUTEE [...] il ne reste aucun etage a construire >>. L'attendu
    #    `etage` etait donc PERIME de deux facons a la fois -- l'etat (ouverte) et le mot.
    v["924-r1"] = {
        "tient": not inv["EarlyWarningOverride"]["effect_classes"],
        "blocage_mesure": None,                              # FERMEE depuis (l'etage est REFUTE)
        "note": "depend de #924-r2 (l'additif attaquant entre a un etage trop bas).",
    }

    # -- #927-r2 : << MischiefMakers n'est pas inscrit >> + BLOCAGE `porteur`
    v["927-r2"] = {
        "tient": not _est_porte(inv["MischiefMakers"]),
        "blocage_mesure": None,                              # FERME par #1081 : plus de champ
        "note": ("classe inscrite (%s) ; porteurs deathNpc3Nurglings (npc) + deathSmnNurglings "
                 "(summon d'environnement)." % (inv["MischiefMakers"]["effect_classes"] or "-")),
    }

    # -- #952-r2 : << GalvanicField n'a AUCUN filet de spawn, faute de canal >>
    #    RE-MESURE 2026-08-18 (#1084) : #10014 a RENOMME cette fiche `#952-r7` (son objet a change
    #    -- ce n'est plus le filet de spawn mais la convention de nommage d'`ai/state_bridge.py`),
    #    donc `#952-r2` a QUITTE le backlog. Une fiche retiree est une sortie legitime : l'attendre
    #    ouverte avec `porteur` faisait rougir le cliquet sur une fermeture REUSSIE.
    v["952-r2"] = {
        "tient": not _est_porte(inv["GalvanicField"]),
        "blocage_mesure": None,                              # RETIREE (renommee #952-r7)
        "note": ("canal ABILITY_INIT_OWNER_FLAGS ne : %s -- le blocage n'est plus l'absence de "
                 "canal, seulement l'absence de regime de spawn." % inv["canal_flag_existe"]),
    }

    # -- #961-r3 : << 1475 n'est PAS dans decisionView.effects, ni actif ni inactif >>
    #    RE-MESURE 2026-08-18 (#1084) : FERMEE par #1091 (ligne RETIREE du backlog) -- << delta
    #    579 -> 0, ratio 1.000000 : la cause etait le CANAL de capture du probe, pas le port >>.
    #    C'est exactement ce que l'etage 1 mesure (le drapeau `includeInactive` est passe).
    v["961-r3"] = {
        "tient": not inv["probe_961_passe_includeInactive"],
        "blocage_mesure": None,                              # RETIREE (fermee par #1091)
        "note": ("le mirror EXISTE (%s) ; ce qui manque est de rejouer dv() avec "
                 "includeInactive=true." % (inv["SupaCyborkBody"]["effect_classes"] or "-")),
    }

    # -- #965-r2 : << la magnitude PAR COUP exige hit_index dans defender_modifiers >>
    v["965-r2"] = {
        "tient": inv["defender_modifiers_a_hit_index"] is False
        and not inv["WhisperingWeb"]["effect_classes"],
        "blocage_mesure": "etage",
        "note": "defender_modifiers reste sans hit_index -- l'etage nomme n'a pas bouge.",
    }

    # -- #966-r4 : << face COMBAT NON PORTEE ; le ctx d'aura ne porte pas l'adjacence a la CIBLE >>
    #    Les DEUX moities sont tombees : les deux effets sont au registre, et le gate est ALIMENTE.
    v["966-r4"] = {
        "tient": not (len(inv["WayOfTheShortBlade"]["effect_classes"]) >= 2
                      and inv["poseurs_gate_wotsb"]),
        "blocage_mesure": None,                              # FERME par #1081 -> #1019-r1 / #1019-r2
        "note": ("effets au registre : %s ; poseurs du gate d'adjacence-cible : %s"
                 % (inv["WayOfTheShortBlade"]["effect_classes"], inv["poseurs_gate_wotsb"])),
    }

    # -- #999-r1 / #999-r2 : << AUCUNE n'est portee >>
    non_portees_r1 = [n for n, p in inv["mythiques_r1"].items() if not _est_porte(p)]
    non_portees_r2 = [n for n, p in inv["mythiques_r2"].items() if not _est_porte(p)]
    #    RE-MESURE 2026-08-18 (#1084) : FERMEE le 2026-08-15 (<< LES DEUX ARBRES DE LA POSE SONT
    #    PORTES >>), ce que l'etage 1 confirme -- 0/6 mythique non portee. L'attendre ouverte avec
    #    `aucun` faisait rougir le cliquet sur sa PROPRE mesure de succes.
    v["999-r1"] = {
        "tient": len(non_portees_r1) == len(inv["mythiques_r1"]),
        "blocage_mesure": None,                              # FERMEE (0/6 non portee)
        "note": "mythiques #999-r1 NON portees : %s / %d" % (
            non_portees_r1 or "aucune", len(inv["mythiques_r1"])),
    }
    v["999-r2"] = {
        "tient": len(non_portees_r2) == len(inv["mythiques_r2"]),
        "blocage_mesure": None,                              # FERME par #1081 (0/5 non portee)
        "note": "mythiques #999-r2 NON portees : %s / %d" % (
            non_portees_r2 or "aucune", len(inv["mythiques_r2"])),
    }
    return v


# --------------------------------------------------------------------------- etage 3

def _lire_backlog():
    """Les champs `BLOCAGE:` REELLEMENT ecrits, via le parseur AUTORITAIRE.

    Rend `(par_id, entrees)` : l'index par identifiant ET la liste COMPLETE, dont le temoin de
    parseur est DERIVE (il ne peut pas l'etre d'un sous-ensemble choisi a la main)."""
    import backlog_entries as B
    entrees = B.lire(BACKLOG)
    par_id = {}
    for e in entrees:
        par_id.setdefault(e.ident.lstrip("#"), e)
    return par_id, entrees


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--inventaire", action="store_true", help="etage 1 seul")
    a = ap.parse_args(argv)

    inv = inventaire()
    print("[1081] ETAGE 1 -- INVENTAIRE (re-derive, jamais herite)")
    for k, n in inv["registres"].items():
        print("   %-32s %4d entrees" % (k, n))
    print("   defender_modifiers porte hit_index : %s" % inv["defender_modifiers_a_hit_index"])
    print("   spawn.py lit ctx.tertiary_ability  : %s" % inv["spawn_lit_tertiaire"])
    print("   poseurs du gate WOTSB              : %d" % len(inv["poseurs_gate_wotsb"]))
    if a.inventaire:
        return EX_OK

    v = verdicts(inv)
    # Un recenseur qui rend VIDE passerait pour vert : on assertionne son propre non-vide.
    if set(v) != set(LES_DIX):
        print("[1081] ROUGE -- les verdicts ne couvrent pas les dix : %s" % sorted(set(LES_DIX) - set(v)))
        return EX_ROUGE

    print()
    print("[1081] ETAGE 2 -- VERDICT par residu (premisse TIENT / REFUTEE)")
    tiennent = [k for k in LES_DIX if v[k]["tient"]]
    refutees = [k for k in LES_DIX if not v[k]["tient"]]
    for k in LES_DIX:
        print("   #%-9s %-8s %s" % (k, "TIENT" if v[k]["tient"] else "REFUTEE", v[k]["note"][:150]))
    print("   => TIENNENT : %d (%s)" % (len(tiennent), ", ".join("#" + k for k in tiennent)))
    print("   => REFUTEES : %d (%s)" % (len(refutees), ", ".join("#" + k for k in refutees)))

    print()
    print("[1081] ETAGE 3 -- CLIQUET : le champ BLOCAGE ECRIT vs la mesure")
    try:
        par_id, entrees = _lire_backlog()
    except Exception as exc:                                 # pragma: no cover - defense
        print("[1081] NON MESURE -- parseur du backlog indisponible : %s" % exc)
        return EX_NON_MESURE

    # -- TEMOIN DE PARSEUR, DERIVE (cf. `temoins_de_parseur`). Un parseur par PRESENCE lit la
    #    citation en prose a la place du champ ; le cran exige que le champ rendu reste du
    #    VOCABULAIRE, sur TOUTES les entrees ou l'etiquette est citee sans deux-points.
    import backlog_entries as B
    temoins = temoins_de_parseur(entrees)
    if not temoins:
        print("[1081] ROUGE -- temoin parseur VIDE : plus aucune entree ne CITE l'etiquette "
              "`BLOCAGE` en prose. Le cran ne mesure alors plus rien -- le re-ancrer, pas le "
              "laisser vert a vide.")
        return EX_ROUGE
    hors_vocab = [(e.ident, e.blocage) for e in temoins
                  if e.blocage is not None and e.blocage not in B.BLOCAGES]
    if hors_vocab:
        print("[1081] ROUGE -- temoin parseur : %d entree(s) dont le champ rendu n'est PAS du "
              "vocabulaire (donc une bribe de PROSE lue a la place du champ) :" % len(hors_vocab))
        for ident, mot in hors_vocab[:10]:
            print("   #%-16s -> %r" % (ident, mot))
        print("        (le marqueur de `backlog_entries` mord-il sur `BLOCAGE` SANS deux-points ?)")
        return EX_ROUGE
    # Le temoin doit DISCRIMINER : au moins une entree ou la lecture NAIVE differe du champ rendu.
    discriminants = [e for e in temoins if _lecture_naive(e.brut) != (e.blocage or None)]
    if not discriminants:
        print("[1081] ROUGE -- temoin parseur DEGENERE : sur les %d entrees a etiquette citee, "
              "la lecture NAIVE rend partout la meme chose que le parseur. Le cran passerait "
              "aussi bien sur un parseur casse." % len(temoins))
        return EX_ROUGE
    print("   temoin parseur DERIVE : %d entree(s) citent l'etiquette en prose, %d discriminent, "
          "0 champ hors vocabulaire  OK" % (len(temoins), len(discriminants)))

    # -- LES DIX. `blocage_mesure = None` signifie << ce n'est PLUS un residu OUVERT >> : la fiche
    #    doit etre FERMEE (`~~..~~`) ou RETIREE du backlog. Les deux sont des sorties legitimes, et
    #    les CONFONDRE avec un rouge est ce qui a fait rougir ce cliquet sur deux fermetures
    #    REUSSIES (#961-r3 ferme par #1091, #952-r2 renomme #952-r7 par #10014).
    #    ⚠ On n'exige PAS qu'une fiche fermee ait PERDU son champ : la convention n'est pas tenue
    #    a l'echelle du backlog -- MESURE au 2026-08-18, **115 des 615 fiches fermees (18,7 %)**
    #    en portent encore un. L'exiger faisait rougir ce cliquet sur une pratique majoritaire.
    rouge = []
    ouverts_compares = 0
    for k in LES_DIX:
        e = par_id.get(k)
        attendu = v[k]["blocage_mesure"]
        if attendu is None:
            if e is None:
                print("   #%-9s RETIREE du backlog                       OK" % k)
            elif e.ferme:
                print("   #%-9s FERMEE (~~%s~~) ecrit=%-8s          OK" % (k, k, e.blocage or "-"))
            else:
                rouge.append((k, "OUVERTE (ecrit=%s)" % (e.blocage or "-"),
                              "fermee ou retiree -- la premisse est REFUTEE par la mesure"))
            continue
        if e is None:
            rouge.append((k, "ABSENT du backlog", attendu))
            continue
        if e.ferme:
            rouge.append((k, "FERMEE", "%s (fiche attendue OUVERTE ; la mesure rend tient=%s) -- "
                                       "fermeture prematuree, ou attestation PERIMEE : re-mesurer"
                          % (attendu, v[k]["tient"])))
            continue
        ecrit = e.blocage or None
        if ecrit != attendu:
            rouge.append((k, ecrit, attendu))
            continue
        ouverts_compares += 1
        print("   #%-9s ouverte              ecrit=%-8s OK" % (k, ecrit))
    if rouge:
        print()
        print("[1081] ROUGE -- %d fiche(s) en desaccord avec la mesure :" % len(rouge))
        for k, ecrit, mesure in rouge:
            print("   #%-9s ECRIT=%-24s MESURE=%s" % (k, ecrit, mesure))
        print("   Un champ perime ECARTE le residu au dispatch, en silence.")
        return EX_ROUGE
    # ANTI-VACUITE : si plus AUCUNE des dix n'est ouverte, l'etage ne compare plus aucun champ et
    # passerait pour vert sans rien mesurer.
    if ouverts_compares == 0:
        print("[1081] ROUGE -- les dix fiches sont toutes fermees ou retirees : cet etage ne "
              "compare plus AUCUN champ. Le foyer a ete referme -- re-ancrer le cliquet sur le "
              "gisement courant (`docs/rl/index-foyers.md`) plutot que le laisser vert a vide.")
        return EX_ROUGE
    print()
    print("[1081] PASS -- les dix fiches concordent : %d ouverte(s) a champ juste, %d fermee(s) ou"
          " retiree(s)." % (ouverts_compares, len(LES_DIX) - ouverts_compares))
    return EX_OK


if __name__ == "__main__":
    raise SystemExit(main())
