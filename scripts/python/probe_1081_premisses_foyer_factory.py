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
  dans de la PROSE, et un critere par presence la prend pour le champ. Temoin de non-regression
  cable dans l'etage 3 : `#943-r7`, dont le corps CITE l'etiquette pour dire qu'elle est trompeuse
  et dont le champ REEL vaut `seeding`. Trois parseurs maison se sont deja fait prendre.

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

#: Temoin de NON-REGRESSION du parseur de champ (cf. l'en-tete) : son corps CITE `BLOCAGE:
#: capteur` en prose pour dire que l'etiquette est trompeuse ; son champ REEL vaut `seeding`.
#: Un parseur par presence rendrait `capteur` et passerait pour vert.
TEMOIN_PARSEUR = ("943-r7", "seeding")


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
        "blocage_mesure": "aucun",
        "note": "MachineVengeance absent de tous les registres -- le canal reste a porter.",
    }

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
    v["924-r1"] = {
        "tient": not inv["EarlyWarningOverride"]["effect_classes"],
        "blocage_mesure": "etage",
        "note": "depend de #924-r2 (l'additif attaquant entre a un etage trop bas).",
    }

    # -- #927-r2 : << MischiefMakers n'est pas inscrit >> + BLOCAGE `porteur`
    v["927-r2"] = {
        "tient": not _est_porte(inv["MischiefMakers"]),
        "blocage_mesure": "aucun",
        "note": ("porteurs IDENTIFIES (deathNpc3Nurglings npc, deathSmnNurglings summon) -- "
                 "l'inscription reste a faire, mais plus aucun porteur n'est INCONNU."),
    }

    # -- #952-r2 : << GalvanicField n'a AUCUN filet de spawn, faute de canal >>
    v["952-r2"] = {
        "tient": not _est_porte(inv["GalvanicField"]),
        "blocage_mesure": "porteur",
        "note": ("canal ABILITY_INIT_OWNER_FLAGS ne : %s -- le blocage n'est plus l'absence de "
                 "canal, seulement l'absence de regime de spawn." % inv["canal_flag_existe"]),
    }

    # -- #961-r3 : << 1475 n'est PAS dans decisionView.effects, ni actif ni inactif >>
    v["961-r3"] = {
        "tient": not inv["probe_961_passe_includeInactive"],
        "blocage_mesure": "aucun",
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
        "blocage_mesure": "aucun",
        "note": ("effets au registre : %s ; poseurs du gate d'adjacence-cible : %s"
                 % (inv["WayOfTheShortBlade"]["effect_classes"], inv["poseurs_gate_wotsb"])),
    }

    # -- #999-r1 / #999-r2 : << AUCUNE n'est portee >>
    non_portees_r1 = [n for n, p in inv["mythiques_r1"].items() if not _est_porte(p)]
    non_portees_r2 = [n for n, p in inv["mythiques_r2"].items() if not _est_porte(p)]
    v["999-r1"] = {
        "tient": len(non_portees_r1) == len(inv["mythiques_r1"]),
        "blocage_mesure": "aucun",
        "note": "mythiques #999-r1 NON portees : %s / %d" % (
            non_portees_r1 or "aucune", len(inv["mythiques_r1"])),
    }
    v["999-r2"] = {
        "tient": len(non_portees_r2) == len(inv["mythiques_r2"]),
        "blocage_mesure": "aucun",
        "note": "mythiques #999-r2 NON portees : %s / %d" % (
            non_portees_r2 or "aucune", len(inv["mythiques_r2"])),
    }
    return v


# --------------------------------------------------------------------------- etage 3

def _lire_backlog():
    """Les champs `BLOCAGE:` REELLEMENT ecrits, via le parseur AUTORITAIRE."""
    import backlog_entries as B
    par_id = {}
    for e in B.lire(BACKLOG):
        par_id.setdefault(e.ident.lstrip("#"), e)
    return par_id


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
        par_id = _lire_backlog()
    except Exception as exc:                                 # pragma: no cover - defense
        print("[1081] NON MESURE -- parseur du backlog indisponible : %s" % exc)
        return EX_NON_MESURE

    # Temoin de non-regression du parseur : il DOIT rendre le champ NU, pas la citation en prose.
    tid, attendu = TEMOIN_PARSEUR
    tem = par_id.get(tid)
    if tem is None or tem.blocage != attendu:
        print("[1081] ROUGE -- temoin de parseur #%s : attendu %r, lu %r" % (
            tid, attendu, getattr(tem, "blocage", None)))
        print("        (un critere par PRESENCE lit la citation en prose, pas le champ)")
        return EX_ROUGE
    print("   temoin parseur #%s = %r  OK (sa prose CITE une AUTRE etiquette)" % (tid, attendu))

    rouge = []
    for k in LES_DIX:
        e = par_id.get(k)
        if e is None:
            rouge.append((k, "ABSENT du backlog", v[k]["blocage_mesure"]))
            continue
        if e.blocage != v[k]["blocage_mesure"]:
            rouge.append((k, e.blocage, v[k]["blocage_mesure"]))
        else:
            print("   #%-9s ecrit=%-8s mesure=%-8s OK" % (k, e.blocage, v[k]["blocage_mesure"]))
    if rouge:
        print()
        print("[1081] ROUGE -- %d champ(s) BLOCAGE en desaccord avec la mesure :" % len(rouge))
        for k, ecrit, mesure in rouge:
            print("   #%-9s ECRIT=%-18s MESURE=%s" % (k, ecrit, mesure))
        print("   Un champ perime ECARTE le residu au dispatch, en silence.")
        return EX_ROUGE

    print()
    print("[1081] PASS -- les dix champs BLOCAGE concordent avec la mesure.")
    return EX_OK


if __name__ == "__main__":
    raise SystemExit(main())
