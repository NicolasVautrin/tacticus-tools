#!/usr/bin/env python
"""Probe #884-r2 / #1003-r1 -- `OrbsOfDecay_AdditionalHitsEffect` (1463), le DERNIER descripteur
`Average` du recensement des 19 `$$CreateAdditionalHits` (#884 SS2).

LA PREMISSE `BLOCAGE: porteur` DE LA FICHE EST FAUSSE, ET C'EST MESURE
-----------------------------------------------------------------------
`unit_map.py find --ability OrbsOfDecay` rend **12** unites, par la voie RELIQUE -- dont TROIS
`lineup` (`deathBlightbringer`, `deathPutrifier`, `deathRotbone`), toutes dans
`rl_duel build --list-pool` au rank courant. C'est l'etat 2 des trois etats d'une relique (#237) :
montage ECRIT `--equip-relic`, aucune injection catalogue.

LE REGIME QUI FAIT MORDRE LA MECANIQUE -- ET IL A FALLU LE CHERCHER
-------------------------------------------------------------------
Le trigger natif est `get_OwnerIsCaster & OrbsOfDecayAbility$$GetTriggerForAttack & IsMeleeAttack`,
et le second conjoint exige
    StatNegativeModification(cible, FixedArmor) * 100 / StatAmount(cible, FixedArmor, Initial)
    STRICTEMENT > ConfigConst(0x83 = armorReductionPct) = 30.

⚠ PREMIERE TENTATIVE, REFUTEE : `--unit-modifier "<cible>:fixedArmor:-40"`. Le point d'entree natif
`BC.UnitModifiers` -> `IdunBattle.Operations.SetupGameOperation$$ApplyModifiers` recalcule la stat
de BASE (mesure : `fixedArmor=2474`), il ne pose PAS de `StatModifier` par source ->
`StatNegativeModification` reste a **0** et le gate ne mord pas. Mesure live : **0** coup 1463.
Un montage qui ne mord pas ne valide rien -- il fallait le voir, pas le supposer.

REGIME RETENU, **NATUREL** : le trait `ContagionsOfNurgle` que portent les TROIS porteurs de la
relique. `globalValues.traitVariables` (LU) :
    contagionsOfNurgleArmorOneAura      = -20     -> ratio 20, sous le seuil -> gate FERME
    contagionsOfNurgleArmorTwoOrMoreAuras = -40   -> ratio 40, au-dessus     -> gate OUVERT
DEUX porteurs adjacents a la cible suffisent donc, sans aucune stat forcee. Et le bras a UN SEUL
porteur est la CONTRE-EPREUVE du seuil, gratuite.

TROIS BRAS, chacun tombe pour une raison DIFFERENTE :
  * MORDANT : 2 porteurs adjacents + relique -> `ContagionsOfNurgle_ArmorReduction2` -> coups 1463 ;
  * SEUIL   : 1 seul porteur + relique       -> `..._ArmorReduction1` (-20 %)         -> AUCUN coup ;
  * TEMOIN  : 2 porteurs, PAS de relique                                              -> AUCUN coup.
Le bras SEUIL est ce qui distingue << le gate a mordu >> de << la relique est simplement la >>.

ORACLE
------
`UnitDamaged.Additional_Hit_Effect_Source` publie l'`EffectType` SOURCE de chaque coup additionnel :
compter les `1463` est une mesure DIRECTE du canal #179, pas un ecart de degat a interpreter.
`DamageProfileType=24` (Toxic) confronte le `damageProfile` de la config.

CE QUI N'EST PAS COUVERT, ET IL FAUT LE LIRE AVANT DE CITER CE PROBE
--------------------------------------------------------------------
Le MONTANT des deux coups 1463. Les quatre coups d'ARME tuent la cible avant eux, donc ils sortent
en OVERKILL a `Amount=0` ; le `--unit-stat Health` pose pour l'eviter n'a PAS mordu (mesure : les
montants restent a 0). Le probe confronte donc le COMPTE, le PROFIL et le SEUIL du gate cote
NATIF, et le montant seulement cote PORT (etage 4, ou le bi-canal ROLL/DISPLAY est verifie).

ASCII only. Usage :
    python probe_884r2_orbs_of_decay.py [--seed 777] [--keep]
"""
from __future__ import annotations

import argparse
import re
import subprocess
import sys
from pathlib import Path

_HERE = Path(__file__).resolve().parent
if str(_HERE) not in sys.path:
    sys.path.insert(0, str(_HERE))

SEED = "777"
BOARD = "MC1_67"
#: `deathRotbone` porte la relique : son arme est `Power` (4 coups) et MELEE -- le trigger exige
#: `IsMeleeAttack`. `deathBlightbringer` n'est la que pour son trait `ContagionsOfNurgle`.
PORTEUR = "deathRotbone"
SECOND = "deathBlightbringer"
CIBLE = "ultraTigurius"
RELIQUE = "OrbsOfDecay"
EFFET = "OrbsOfDecay_AdditionalHits"
EFFET_ID = 1463                       # `EffectType.OrbsOfDecay_AdditionalHits` = 0x5b7
PROFIL_TOXIC = 24                     # `DamageProfileType` du `damageProfile` de la config
#: PV de la cible, forces pour que les coups 1463 NE sortent PAS en overkill (cf. _build).
CIBLE_PV = 400000
#: Tuiles ADJACENTES au spawn adverse (6,8) de `MC1_67` -- le contact est FORCE, jamais espere.
#: `--a-place` sortirait la cible de `BC.PredefinedUnits`, on deplace donc MES unites.
PLACE = {PORTEUR: "5,8", SECOND: "6,7"}


def _rl(args, state_file):
    cmd = [sys.executable, str(_HERE / "rl_duel.py")] + args + ["--state-file", str(state_file)]
    p = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace")
    return p.returncode, (p.stdout or "") + (p.stderr or "")


def _build(state_file, *, avec_relique: bool, deux_porteurs: bool, seed: str):
    unites = [PORTEUR] + ([SECOND] if deux_porteurs else [])
    args = ["build", "--seed", seed, "--board", BOARD,
            "--p-units", ",".join(unites), "--a-units", CIBLE,
            # ⚠ TENTATIVE QUI N'A PAS MORDU, GARDEE ET DECLAREE. Les quatre coups d'ARME tuent la
            # cible AVANT le canal #179, donc les deux coups 1463 sortent en OVERKILL a `Amount=0`.
            # Ce `--unit-stat Health` visait a les rendre observables ; MESURE : les montants
            # restent a 0, la normalisation du BC recalculant la sante. CONSEQUENCE ASSUMEE ET
            # BORNEE : ce probe confronte le COMPTE de coups, leur PROFIL et le SEUIL du gate --
            # jamais leur MONTANT. Dire ou s'arrete la mesure vaut mieux que laisser croire
            # qu'elle porte plus loin. Le montant reste couvert par l'etage 4 (cote PORT).
            "--unit-stat", "%s:Health=%d" % (CIBLE, CIBLE_PV)]
    for u in unites:
        args += ["--place", "%s:%s" % (u, PLACE[u])]
    if avec_relique:
        args += ["--equip-relic", "%s:%s:10" % (PORTEUR, RELIQUE)]
    return _rl(args, state_file)


def _uid_du_porteur(sortie: str):
    m = re.search(r"u(\d+) \[%s\]" % re.escape(PORTEUR), sortie)
    return int(m.group(1)) if m else None


def _uid_cible(sortie: str):
    m = re.search(r"u(\d+) \[%s\]" % re.escape(CIBLE), sortie)
    return int(m.group(1)) if m else None


def _runner_id(sortie: str):
    m = re.search(r"runnerId=(\d+)", sortie)
    return int(m.group(1)) if m else None


def _coups_additionnels(sortie: str):
    """Les `UnitDamaged` dont `Additional_Hit_Effect_Source` designe 1463 -> [(amount, profil)]."""
    out = []
    for ligne in sortie.splitlines():
        if "Additional_Hit_Effect_Source=%d" % EFFET_ID not in ligne:
            continue
        a = re.search(r"Amount=(\d+)", ligne)
        p = re.search(r"DamageProfileType=(\d+)", ligne)
        out.append((int(a.group(1)) if a else None, int(p.group(1)) if p else None))
    return out


def _bras(nom, *, avec_relique, deux_porteurs, seed, logs, runners):
    sf = logs / ("probe884r2-%s.json" % nom.lower().replace(" ", "-"))
    code, out = _build(sf, avec_relique=avec_relique, deux_porteurs=deux_porteurs, seed=seed)
    rid = _runner_id(out)
    if rid is not None:
        runners.append(sf)
    if code != 0:
        return {"nom": nom, "erreur": "build rc=%d" % code, "sortie": out[-800:]}
    caster, cible = _uid_du_porteur(out), _uid_cible(out)
    pose = EFFET in out
    reduction = ("ArmorReduction2" if "ContagionsOfNurgle_ArmorReduction2" in out
                 else "ArmorReduction1" if "ContagionsOfNurgle_ArmorReduction1" in out else "aucune")
    if caster is None or cible is None:
        return {"nom": nom, "runner": rid, "pose": pose, "reduction": reduction,
                "erreur": "unites illisibles"}
    # `Loki_NormalAttack` = 69 : l'attaque NORMALE du porteur, le vecteur que le trigger exige.
    _c, act = _rl(["act", "ability", "--caster", str(caster), "--ability", "69",
                   "--target", str(cible)], sf)
    return {"nom": nom, "runner": rid, "pose": pose, "reduction": reduction,
            "coups": _coups_additionnels(act)}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--seed", default=SEED)
    ap.add_argument("--keep", action="store_true")
    args = ap.parse_args()

    logs = _HERE.parents[1] / "logs"
    logs.mkdir(parents=True, exist_ok=True)
    print("=== probe #884-r2 -- OrbsOfDecay_AdditionalHits (1463), canal #179 ===")
    print("porteur %s + relique %s niv.10 ; second porteur %s (trait ContagionsOfNurgle)"
          % (PORTEUR, RELIQUE, SECOND))
    print("cible %s, board %s, seed %s\n" % (CIBLE, BOARD, args.seed))

    runners, rc = [], 0
    try:
        bras = [
            _bras("MORDANT", avec_relique=True, deux_porteurs=True, seed=args.seed,
                  logs=logs, runners=runners),
            _bras("SEUIL", avec_relique=True, deux_porteurs=False, seed=args.seed,
                  logs=logs, runners=runners),
            _bras("TEMOIN", avec_relique=False, deux_porteurs=True, seed=args.seed,
                  logs=logs, runners=runners),
        ]
        for b in bras:
            if b.get("erreur"):
                print("[%-8s] ERREUR : %s" % (b["nom"], b["erreur"]))
                rc = 1
                continue
            print("[%-8s] runner=%-4s effet_pose=%-5s armure_cible=%-16s coups_1463=%d %s"
                  % (b["nom"], b["runner"], b["pose"], b["reduction"],
                     len(b["coups"]), b["coups"]))
        par_nom = {b["nom"]: b for b in bras if not b.get("erreur")}

        print("\n--- etage 1 : LA POSE (temoin NON degenere) ---")
        m, t = par_nom.get("MORDANT"), par_nom.get("TEMOIN")
        if m and t and m["pose"] is True and t["pose"] is False:
            print("OK  l'effet 1463 est pose SSI la relique est equipee")
        else:
            print("ECART  pose(mordant)=%s pose(temoin)=%s"
                  % (m and m["pose"], t and t["pose"]))
            rc = 1

        print("\n--- etage 2 : LE GATE D'ARMURE MORD, ET SON SEUIL EST STRICT ---")
        s = par_nom.get("SEUIL")
        if not (m and s and t):
            print("NON MESURE : un bras manque -- rien n'est conclu.")
            return 1
        if m["reduction"] != "ArmorReduction2" or s["reduction"] != "ArmorReduction1":
            print("MONTAGE INVALIDE : reductions %s / %s -- attendu ArmorReduction2 / 1"
                  % (m["reduction"], s["reduction"]))
            rc = 1
        n_m, n_s, n_t = len(m["coups"]), len(s["coups"]), len(t["coups"])
        print("2 porteurs (-40 %%) + relique : %d coup(s)" % n_m)
        print("1 porteur  (-20 %%) + relique : %d coup(s)   <- le seuil STRICT ferme ici" % n_s)
        print("2 porteurs (-40 %%) sans relique : %d coup(s)" % n_t)
        if n_m > 0 and n_s == 0 and n_t == 0:
            print("OK  la mecanique MORD, et elle ne mord QUE dans le regime attendu")
        else:
            print("ECART  attendu (>0, 0, 0)")
            rc = 1

        print("\n--- etage 3 : nrOfHits et damageProfile ---")
        attendu_hits = _config_nr_of_hits()
        profils = {p for _a, p in m["coups"]}
        print("coups natifs = %d ; ConfigConst(0x2f = nrOfHits) = %s" % (n_m, attendu_hits))
        print("DamageProfileType observe(s) = %s ; attendu %d (Toxic)" % (sorted(profils), PROFIL_TOXIC))
        if attendu_hits is not None and n_m != int(attendu_hits):
            print("ECART sur le NOMBRE de coups")
            rc = 1
        if profils and profils != {PROFIL_TOXIC}:
            print("ECART sur le PROFIL")
            rc = 1

        print("\n--- etage 4 : LE PORT rend le meme groupe ---")
        rc |= _etage_port(n_m)
    finally:
        if not args.keep:
            for sf in runners:
                _rl(["dispose"], sf)
            print("\n[dispose] %d runner(s) libere(s)" % len(runners))
    print("\nrc = %d" % rc)
    return rc


def _config_nr_of_hits():
    from engine.entities.effects.magnitude import ability_var
    return ability_var(RELIQUE, "nrOfHits", is_constant=True)


def _etage_port(coups_natifs: int) -> int:
    """Le descripteur PORTE, evalue hors runner sur les DEUX scalaires du regime mordant.

    CE QUE CET ETAGE COUVRE : le nombre de coups, le profil, et le BI-CANAL ROLL/DISPLAY (le
    descripteur publie `min`/`max` ET `amount = Average` arrondi Fix64 demi-vers-le-PAIR).
    CE QU'IL NE COUVRE PAS : le replay du pipeline de degat complet sur la capture pre-attaque --
    les montants natifs dependent du percage, de l'armure restante et des tirages, que ce probe
    ne rejoue pas. C'est dit, pas tu."""
    from engine.entities.effects.ctx_keys import (CTX_TGT_FIXED_ARMOR_INITIAL,
                                                  CTX_TGT_FIXED_ARMOR_NEGATIVE_MOD)
    from engine.entities.effects.loki.hits import OrbsOfDecayAdditionalHitsEffect
    eff = OrbsOfDecayAdditionalHitsEffect(EFFET_ID)
    base = {"owner_id": 1, "att_id": 1, "is_melee": True}
    #: -40 % : DEUX auras `ContagionsOfNurgle` (le regime MORDANT), ratio 40 > 30.
    mord = eff.additional_hit_groups({**base, CTX_TGT_FIXED_ARMOR_INITIAL: 100,
                                      CTX_TGT_FIXED_ARMOR_NEGATIVE_MOD: 40}) or []
    #: -20 % : UNE seule aura (le bras SEUIL), ratio 20 < 30.
    seuil = eff.additional_hit_groups({**base, CTX_TGT_FIXED_ARMOR_INITIAL: 100,
                                       CTX_TGT_FIXED_ARMOR_NEGATIVE_MOD: 20}) or []
    #: -30 % PILE : `AmountIsGreater` est STRICT, donc FERME. Ce cas n'est pas theorique --
    #: `ContaminatedStatModifierEffect` pose exactement `-armorReductionPct %`.
    pile = eff.additional_hit_groups({**base, CTX_TGT_FIXED_ARMOR_INITIAL: 100,
                                      CTX_TGT_FIXED_ARMOR_NEGATIVE_MOD: 30}) or []
    #: NON MESURE : les cles absentes ferment le gate (jamais un 0 rabattu).
    nul = eff.additional_hit_groups(base) or []
    rc = 0
    print("port -40 %% : %s" % (mord,))
    print("port -20 %% : %s   (attendu vide)" % (seuil,))
    print("port -30 %% : %s   (attendu vide -- seuil STRICT)" % (pile,))
    print("port NON MESURE : %s   (attendu vide -- tri-etat)" % (nul,))
    if not mord:
        print("ECART : le port ne rend AUCUN groupe dans le regime ou le natif en rend %d"
              % coups_natifs)
        return 1
    g = mord[0]
    if int(g["count"]) != int(coups_natifs):
        print("ECART sur le nombre de coups : port=%s natif=%s" % (g["count"], coups_natifs))
        rc = 1
    if g.get("profile") != "Toxic":
        print("ECART sur le profil : port=%s" % g.get("profile"))
        rc = 1
    if "amount" not in g or "min" not in g or "max" not in g:
        print("ECART : le BI-CANAL ROLL/DISPLAY n'est pas publie (%s)" % sorted(g))
        rc = 1
    else:
        from fractions import Fraction
        from engine.dsl.base import _round_fix64
        att = _round_fix64(Fraction(int(g["min"]) + int(g["max"]), 2), 0)
        if int(g["amount"]) != int(att):
            print("ECART sur le canal DISPLAY : amount=%s, Average attendu=%s" % (g["amount"], att))
            rc = 1
    if seuil or pile or nul:
        print("ECART : le gate laisse passer un regime qu'il devrait fermer")
        rc = 1
    if rc == 0:
        print("OK  port et natif s'accordent sur le compte, le profil et le seuil STRICT ;")
        print("    le bi-canal ROLL/DISPLAY est publie des le premier commit")
    return rc


if __name__ == "__main__":
    raise SystemExit(main())
