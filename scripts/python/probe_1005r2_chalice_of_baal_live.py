"""Probe #1005-r2 -- `ChaliceOfBaal` (relique `TriggeredAbilityType` 1550) CONFRONTEE LIVE.

Le port etait COMPLET et garde OFFLINE depuis #1005, mais aucun montage n'avait jamais fait mourir
une unite au contact de `bloodSanguinary` : les trois observables de la fiche n'avaient jamais ete
RELEVES. Ce probe les releve, plus le RESET, sur cinq etages.

  E1  le SOIN vaut `ChaliceOfBaal.hp[TertiaryAbilityLevel]`, sur le PORTEUR ;
  E2  ... et sur ses ALLIES ADJACENTS non mecaniques, le meme montant, meme `Caster_Id` ;
  E3  l'effet `1569 ChaliceOfBaal_ExtraDmg` est pose sur les MEMES unites, `remainingTurns = 1`,
      signe `Effect_SourceTriggeredAbility = 1550` ;
  E4  le DRAPEAU une-fois-par-tour : une SECONDE mort adjacente dans le MEME tour ne declenche RIEN ;
  E5  le RESET `On(TurnEnd) & HasTriggeredThisTurn -> ClearAllPersistentData` : au tour suivant, une
      TROISIEME mort adjacente RE-declenche.

## POURQUOI LES EVENTS, ET PAS LE DELTA DE PV

Le delta de PV de l'ALLIE est CONTAMINE : `SanguinaryPriest`, autre passif du porteur, le soigne
dans la MEME cascade (mesure : allie 2000 -> 4098 par `SanguinaryPriest`, puis -> 5863 par
`ChaliceOfBaal`). Seul le PORTEUR recoit un delta propre. On lit donc les `HealInfo` de la cascade,
qui portent chacun leur `Amount` et leur `Caster_Id` -- et l'attribution y est explicite.

## LE MONTAGE, ET SES TROIS ECRITURES SILENCIEUSES

`ChaliceOfBaal` est une RELIQUE : `--equip-relic` fait les trois ecritures que le natif exige
(`BC.Units[].TertiaryAbility`, la config dans `BC.Abilities.PassiveAbilities`, et
`TertiaryAbilityLevel >= 1`), dont DEUX echouent en silence si on les omet, et il les fait AVANT la
normalisation -- l'ordre compte (cf. `docs/rl/case-237-relique-forcee.md`).

⚠ **`--place` / `--a-place`, jamais les spawns.** Aux spawn points du board, les deux camps sont a
8-9 tuiles l'un de l'autre : rien n'est adjacent, et la relique ne pourrait pas se declencher. Le
montage POSE les unites -- c'est la discipline << deplacer pour forcer la configuration >>, pas
<< bloque par la geometrie de spawn >>.

⚠ **Le tour adverse se passe par DEUX `endturn`, jamais par `aiturn`.** Mesure : avec `aiturn`, le
porteur meurt pendant le tour de l'IA (un summon `orksNpc3GrotTank` apparait) et E5 devient
inobservable. `endturn` bascule le camp sans laisser personne agir.

Usage : `python probe_1005r2_chalice_of_baal_live.py [--seed S] [--board B]`.
ASCII only (console cp1252).
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

import gameconfig as GC                                                    # noqa: E402
import probe_112_darkangels as PR                                          # noqa: E402
import probe_27_custom_utility_inventory as INV                            # noqa: E402
from engine.entities.effect_type import EffectType                         # noqa: E402
from engine.entities.triggered_ability_type import TriggeredAbilityType    # noqa: E402

LOGS = HERE.parent.parent / "logs"

PORTEUR = "bloodSanguinary"      # HERO Blood Angels du pool -- porteur de la relique
ALLIE = "bloodMephiston"         # allie NON MECANIQUE, pose ADJACENT au porteur
ENNEMIS = ("orksNob", "orksRuntherd", "orksBigMek")   # trois morts : E1-E3, puis E4, puis E5

#: Tuiles, en `col,row` (odd-q). `(3,4)` est le centre ; `(3,3)`, `(3,5)`, `(4,4)` et `(2,4)` en
#: sont VOISINES -- verifie par `hexgeo.distance`, jamais suppose.
POS = {PORTEUR: "3,4", ALLIE: "3,3",
       ENNEMIS[0]: "3,5", ENNEMIS[1]: "4,4", ENNEMIS[2]: "2,4"}

#: PV forces des ennemis : assez bas pour que l'attaque normale du porteur tue d'UN coup (le
#: declencheur est la MORT), assez haut pour ne pas dependre d'un roll.
HP_ENNEMI = 150
#: PV du porteur et de l'allie : BLESSES, sinon `WasWoundedBeforeHeal` est faux et le soin est nul.
HP_BLESSE = 2000

CHALICE = int(TriggeredAbilityType.ChaliceOfBaal)          # 0x60e = 1550
EXTRA_DMG = EffectType.ChaliceOfBaal_ExtraDmg.name         # 0x621 = 1569
#: `--equip-relic` pose `TertiaryAbilityLevel = 1` ; `GetVariableForLevel` y lit `hp[0]`.
NIVEAU_RELIQUE = 1


def _run(args) -> int:
    return subprocess.run([sys.executable, "rl_duel.py"] + args, cwd=str(HERE),
                          stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                          check=False).returncode


def _uid(dv, visual):
    for u in (dv.get("units") or []):
        if u.get("visualId") == visual:
            return u.get("id")
    return None


def _normal_attack_type(dv, uid):
    """L'id CONCRET de l'attaque normale (`NormalAttackType@0x28`), PAR UNITE -- LU dans la vue,
    jamais devine (cf. `project_ability_normal_attack_concrete`)."""
    for u in (dv.get("units") or []):
        if int(u.get("id", -1)) != int(uid):
            continue
        for ab in (u.get("abilities") or []):
            if ab.get("kind") == "normal":
                return int(ab["id"])
    return None


def _tags(e):
    """Les `tags` d'un event du host -- une CHAINE JSON, pas un dict. Mesure : `applyAction` rend
    une liste PLATE d'events `{kind, entity, step, group, source, tags}` ou `tags` est
    `'{"Amount":1765,"Caster_Id":77,...}'`. Lire `e["Amount"]` directement rend toujours `None`, et
    un critere bati la-dessus serait VERT SUR RIEN."""
    t = e.get("tags")
    if isinstance(t, dict):
        return t
    if isinstance(t, str) and t:
        try:
            return json.loads(t)
        except ValueError:
            return {}
    return {}


def _soins_de_la_relique(events, hp_attendu, caster):
    """Les `HealInfo` de la cascade attribuables a la relique, indexes par cible.

    DEUX discriminants, parce qu'un seul ne suffit pas : le `Caster_Id` (le porteur) NE separe PAS
    les deux soins -- `SanguinaryPriest` est un autre passif du MEME porteur et porte le meme
    `Caster_Id`. C'est le MONTANT qui tranche (mesure : 1577 pour `SanguinaryPriest`, derive d'un
    pourcentage, contre `hp[niveau] = 1765` pour la relique, une constante de gameconfig).
    `UnitStats_WasWoundedBeforeHeal` identifie la FAMILLE d'event (aucun champ ne porte son nom)."""
    out = {}
    for e in (events or []):
        d = _tags(e)
        if "UnitStats_WasWoundedBeforeHeal" not in d:
            continue
        if int(d.get("Amount", -1)) != int(hp_attendu):
            continue
        if caster is not None and int(d.get("Caster_Id", -1)) != int(caster):
            continue
        cible = e.get("entity")
        if cible is not None:
            out[int(cible)] = int(d["Amount"])
    return out


def _effets_poses(events):
    """Les `ReceiveEffect` SIGNES par la relique (`Effect_SourceTriggeredAbility == 1550`), avec
    leur duree. C'est l'attribution la plus forte disponible : elle vient du natif lui-meme, pas
    d'un nom ni d'un montant."""
    out = {}
    for e in (events or []):
        d = _tags(e)
        if int(d.get("Effect_SourceTriggeredAbility", -1)) != CHALICE:
            continue
        if "Effect_RemainingTurns" not in d:
            continue
        cible = e.get("entity")
        if cible is not None:
            out[int(cible)] = int(d["Effect_RemainingTurns"])
    return out


def hp_attendu() -> int:
    """`GetVariableForLevel(cfg, AbilityVariableType.hp = 0x1d, abilityState, 0)` au niveau
    TERTIAIRE pose par `--equip-relic`. LU au gameconfig, jamais code en dur."""
    from engine.entities.effects.magnitude import ability_var
    return int(ability_var("ChaliceOfBaal", "hp", NIVEAU_RELIQUE) or 0)


def _parser():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--seed", type=int, default=31337)
    p.add_argument("--board", default="MC1_67")
    return p


def mesurer(seed: int, board: str) -> dict:
    """Monte le runner, joue les TROIS morts, et rend les observables des cinq etages."""
    LOGS.mkdir(parents=True, exist_ok=True)
    p = LOGS / ("rs_1005r2_chalice_%d.json" % seed)
    args = ["build", "--seed", str(seed), "--board", board, "--rank", "17",
            "--p-units", ",".join([PORTEUR, ALLIE]), "--a-units", ",".join(ENNEMIS),
            "--equip-relic", "%s:ChaliceOfBaal" % PORTEUR,
            "--hp-target", str(HP_ENNEMI),
            "--unit-stat", "%s:RemainingHealth=%d;%s:RemainingHealth=%d"
            % (PORTEUR, HP_BLESSE, ALLIE, HP_BLESSE),
            "--state-file", str(p), "--no-ai"]
    for v, tuile in POS.items():
        args += (["--place", "%s:%s" % (v, tuile)] if v in (PORTEUR, ALLIE)
                 else ["--a-place", "%s:%s" % (v, tuile)])
    _run(args)
    if not p.exists():
        return {"ok": False, "raison": "build KO (host indisponible ?)"}
    rid = int(json.loads(p.read_text(encoding="utf-8"))["runnerId"])
    sid = INV._session_id()
    attendu = hp_attendu()
    out = {"ok": True, "runner": rid, "seed": seed, "board": board, "hp_attendu": attendu}
    try:
        dv = PR.rpc(sid, "decisionView", {"runnerId": rid, "allAbilities": True}, 150)
        cid, aid = _uid(dv, PORTEUR), _uid(dv, ALLIE)
        eids = [_uid(dv, v) for v in ENNEMIS]
        na = _normal_attack_type(dv, cid)
        out.update(porteur=cid, allie=aid, ennemis=eids, normal_attack=na)
        if cid is None or aid is None or na is None or any(e is None for e in eids):
            out.update(ok=False, raison="montage incomplet: %r" % out)
            return out

        # --- E1/E2/E3 : PREMIERE mort adjacente ------------------------------------------------
        r1 = PR.cast(sid, rid, cid, eids[0], na)
        out["soins_1"] = _soins_de_la_relique(r1.get("events"), attendu, cid)
        out["effets_1"] = _effets_poses(r1.get("events"))

        # --- E4 : SECONDE mort adjacente, MEME tour -> le drapeau doit bloquer ------------------
        na_allie = _normal_attack_type(dv, aid)
        r2 = PR.cast(sid, rid, aid, eids[1], na_allie or na)
        out["soins_2"] = _soins_de_la_relique(r2.get("events"), attendu, cid)
        out["effets_2"] = _effets_poses(r2.get("events"))

        # --- E5 : TOUR SUIVANT -> le reset doit avoir re-arme -----------------------------------
        # Deux `endturn`, jamais `aiturn` (cf. l'en-tete : le porteur y meurt).
        for _ in range(3):
            PR.act(sid, rid, {"kind": "endturn"})
            dv2 = PR.rpc(sid, "decisionView", {"runnerId": rid}, 150)
            if int(dv2.get("currentPlayer", -1)) == int(dv.get("currentPlayer", -2)):
                break
        r3 = PR.cast(sid, rid, cid, eids[2], na)
        out["soins_3"] = _soins_de_la_relique(r3.get("events"), attendu, cid)
        out["effets_3"] = _effets_poses(r3.get("events"))
    finally:
        _run(["dispose", "--state-file", str(p)])
    return out


def verdicts(m: dict) -> list:
    """Les cinq etages, en couples `(nom, ok, detail)` -- foyer UNIQUE des criteres (le test les
    rejoue, il ne les re-code pas)."""
    if not m.get("ok"):
        return [("montage", False, m.get("raison"))]
    cid, aid, hp = m["porteur"], m["allie"], m["hp_attendu"]
    s1, e1 = m.get("soins_1") or {}, m.get("effets_1") or {}
    s2, e2 = m.get("soins_2") or {}, m.get("effets_2") or {}
    s3, e3 = m.get("soins_3") or {}, m.get("effets_3") or {}
    return [
        ("E0 la magnitude lue au gameconfig est NON NULLE", hp > 0, hp),
        ("E1 le PORTEUR est soigne de hp[niveau]", s1.get(cid) == hp, (s1.get(cid), hp)),
        ("E2 l'ALLIE ADJACENT recoit le MEME montant", s2 is not None and s1.get(aid) == hp,
         (s1.get(aid), hp)),
        ("E3 l'effet 1569 est pose sur les DEUX, 1 tour",
         set(e1) == {cid, aid} and set(e1.values()) == {1}, e1),
        ("E4 une 2e mort adjacente le MEME tour ne declenche RIEN",
         not s2 and not e2, (s2, e2)),
        ("E5 au tour SUIVANT, le reset a re-arme", s3.get(cid) == hp and set(e3) == {cid, aid},
         (s3, e3)),
    ]


def main() -> int:
    a = _parser().parse_args()
    m = mesurer(a.seed, a.board)
    print("[1005-r2] runner=%s seed=%s board=%s hp_attendu=%s"
          % (m.get("runner"), m.get("seed"), m.get("board"), m.get("hp_attendu")))
    bad = 0
    for nom, ok, detail in verdicts(m):
        print("  %-52s %s   %s" % (nom, "OK " if ok else "FAIL", detail))
        bad += 0 if ok else 1
    print("VERDICT: %s (%d)" % ("PASS" if not bad else "FAIL", bad))
    return 0 if not bad else 1


if __name__ == "__main__":
    sys.exit(main())
