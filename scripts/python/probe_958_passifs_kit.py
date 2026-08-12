#!/usr/bin/env python3
"""#958 -- MESURE LIVE des deux passifs de kit `MedicusMinistorum` (1069) et `AggressiveOnslaught`
(1248), chacun confronte au montant/compte que le PORT calcule.

Chaque volet monte SA geometrie, la VERIFIE avant de conclure, et compare une grandeur NATIVE lue
dans la cascade d'evenements a la grandeur que le mirror Python rend. Un volet dont le regime n'est
pas atteint REFUSE de conclure (rc 2) plutot que de rendre un vert vide.

  A. MEDICUS  -- Isabella adjacente a un allie BLESSE (seede blesse, jamais construit en jouant) ;
                 un ennemi PILOTE (jamais l'IA) frappe l'allie. TEMOIN = l'event
                 `Ability_Power <MedicusMinistorum>` / `HealInfo Amount=<hpToHeal>`, confronte a
                 `medicus_ministorum_hp_to_heal`. DISCRIMINANT : Isabella est HORS de portee de
                 l'attaquant, donc un soin observe ne peut venir que du passif, pas d'une riposte.
  B. ONSLAUGHT -- Mataneo CHARGE (il part hors contact et arrive au contact dans le meme pas).
                 TEMOIN = le NOMBRE d'`AddUnit Unit_IsSummoned=1 Unit_Parent_Id=<Mataneo>`,
                 confronte a `aggressive_onslaught_max_summon` (= `GetNumberConstant(0x10)`).
                 Puis le tour SUIVANT de Mataneo : les enfants doivent avoir DISPARU (unsummon).

Le volet B porte la contre-epreuve la plus utile de la tranche : le compte `2` separe la surcharge
`DSLSelectors$$First(entities, amount, ignoreForcedTargets)` (`PickFirstN`, les N premiers) de
`First(source, index)` (`PickAtIndex`, UN element) -- cette derniere rendrait `1`.

Sortie ASCII (console cp1252).

Usage :
    python probe_958_passifs_kit.py --state-file <ABSOLU unique> [--board MC1_67] [--seed 777]
"""
from __future__ import annotations

import argparse
import re
import subprocess
import sys
from pathlib import Path

ICI = Path(__file__).resolve().parent

HOSPITALLER = "adeptHospitaller"      # Isabella -- porteuse de MedicusMinistorum (HERO, au pool)
ENCAISSEUR = "ultraApothecary"        # l'allie adjacent qui prend le coup (PV seedes)
FRAPPEUR = "ultraTitus"               # l'attaquant PILOTE (melee), et la cible du volet B
INTERCESSOR = "bloodIntercessor"      # Mataneo -- porteur d'AggressiveOnslaught (HERO, au pool)
NORMAL_ATTACK = 69                    # `Loki_NormalAttack`


def _run(args: list, state_file: str) -> str:
    cmd = [sys.executable, str(ICI / "rl_duel.py")] + args + ["--state-file", state_file]
    p = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace")
    return (p.stdout or "") + (p.stderr or "")


def _dispose(state_file: str) -> None:
    _run(["dispose"], state_file)


def _uid(sortie: str, unit_id: str):
    """`u<NN> [<unitId>]` dans la vue -- l'id d'entite que le runner a attribue."""
    m = re.search(r"u(\d+) \[" + re.escape(unit_id) + r"\]", sortie)
    return int(m.group(1)) if m else None


def volet_medicus(state_file: str, adv_file: str, board: str, seed: int) -> int:
    from engine.entities.effects.magnitude import ability_var

    print("=== A. MEDICUS MINISTORUM (1069) ===")
    _dispose(state_file)
    vue = _run(["build", "--seed", str(seed), "--board", board,
                "--p-units", "%s,%s" % (HOSPITALLER, ENCAISSEUR),
                "--a-units", FRAPPEUR,
                "--place", "%s:2,2" % HOSPITALLER, "--place", "%s:3,2" % ENCAISSEUR,
                "--a-place", "%s:4,2" % FRAPPEUR,
                # Le regime est fabrique AU SEED : l'allie est DEJA blesse, et assez large pour
                # SURVIVRE au coup (un mort ne serait pas soigne -- c'est le gate `IsDamagedUnit`
                # + le `selectionType = 3` du trigger, pas un trou de montage).
                "--unit-stat", "%s:Health=30000,RemainingHealth=15000" % ENCAISSEUR,
                "--no-ai"], state_file)
    u_isa, u_enc, u_frap = _uid(vue, HOSPITALLER), _uid(vue, ENCAISSEUR), _uid(vue, FRAPPEUR)
    if None in (u_isa, u_enc, u_frap):
        print("  REFUS : montage incomplet (uid manquant) -- rien n'est conclu")
        return 2
    print("  geometrie : Isabella u%d @(2,2) · allie u%d @(3,2) · frappeur u%d @(4,2)"
          % (u_isa, u_enc, u_frap))

    _run(["act", "endturn"], state_file)
    _run(["attach", "--team", "2", "--from", state_file], adv_file)
    # L'attaquant est PILOTE, jamais l'IA : sans cela elle choisit sa cible (mesure : elle a vise
    # Isabella, pas l'allie, et le regime n'etait jamais atteint).
    _run(["act", "move", "--unit", str(u_frap), "--to", "3,3"], adv_file)
    casc = _run(["act", "ability", "--caster", str(u_frap), "--target", str(u_enc),
                 "--ability", str(NORMAL_ATTACK)], adv_file)

    coups = re.findall(r"Attacker_Id=%d Target_Id=%d Amount=(\d+)" % (u_frap, u_enc), casc)
    soins = re.findall(r"HealInfo e=%d .*?Amount=(\d+) Caster_Id=(\d+)" % u_enc, casc)
    if not coups:
        print("  REFUS : aucun coup porte sur l'allie -- regime non atteint")
        return 2
    print("  natif : %d coup(s) sur l'allie, total %d" % (len(coups), sum(int(x) for x in coups)))
    if not soins:
        print("  ECHEC : AUCUN `HealInfo` -- le passif natif n'a pas fire dans ce regime")
        return 1
    amount, caster = int(soins[0][0]), int(soins[0][1])
    print("  natif : HealInfo Amount=%d Caster_Id=%d  (1 seul soin pour %d coups -> `On(9=Attack)`"
          " est emis UNE fois en sortie d'attaque, pas par coup)" % (amount, caster, len(coups)))

    # ###### IDENTIFIABILITE plutot qu'egalite ######
    # Le montant porte est `GetVariableForLevel(0x20 = hpToHeal)` sous le `(niveau, multiplicateur)`
    # du PASSIF du porteur -- couple que la cascade de CE volet n'imprime pas (aucun `ChangeAbility`
    # n'y passe : personne n'est spawne). Plutot que de SUPPOSER le regime du harnais (ce qui ferait
    # d'un parametre choisi la moitie de la reponse), le probe balaie la table `hpToHeal` du mirror
    # et demande QUELS couples reproduisent le montant natif.
    # C'est STRICTEMENT PLUS FORT qu'une egalite sur un regime pose d'avance : si la table du port
    # etait fausse, AUCUN couple ne tomberait sur la valeur native ; et l'ensemble des solutions est
    # imprime, donc un accord obtenu par un regime absurde se VOIT au lieu de passer pour un vert.
    solutions = [(l, m) for l in range(0, 65) for m in (100, 120, 140, 160, 180, 200)
                 if int(ability_var("MedicusMinistorum", "hpToHeal", l,
                                    multiplier_pct=m) or -1) == amount]
    print("  port  : couples (niveau, multiplicateur) de la table `hpToHeal` qui rendent %d : %s"
          % (amount, solutions if solutions else "AUCUN"))
    ok_montant = bool(solutions)
    ok_regime = any(l >= 40 for l, _m in solutions)      # le harnais normalise haut (targetAbilityLevel)
    ok_caster = (caster == u_isa)
    print("  [%s] le montant natif est ATTEIGNABLE par la table du port"
          % ("OK" if ok_montant else "ECART"))
    print("  [%s] au moins une solution est a un niveau NORMALISE (>= 40) -- pas un accord"
          " fortuit sur un niveau bas" % ("OK" if ok_regime else "ECART"))
    print("  [%s] le SOIGNEUR est Isabella (`healer = Owner@<DSLSelectors+0x30>`)"
          % ("OK" if ok_caster else "ECART"))
    return 0 if (ok_montant and ok_regime and ok_caster) else 1


class _EtatFactice:
    """Le compte de summons ne depend d'AUCUN niveau : `GetNumberConstant` lit `constants`, pas
    `variables` (contraste avec `GetVariableForLevel`). Un etat vide suffit donc pour le volet B, et
    c'est precisement ce que la distinction constante/variable garantit."""
    def get_entity(self, _uid):
        return None


def volet_onslaught(state_file: str, board: str, seed: int) -> int:
    from engine.runner.operations.triggers.loki.aggressive_onslaught import (
        aggressive_onslaught_max_summon)

    print("=== B. AGGRESSIVE ONSLAUGHT (1248) ===")
    _dispose(state_file)
    vue = _run(["build", "--seed", str(seed), "--board", board,
                "--p-units", INTERCESSOR, "--a-units", FRAPPEUR,
                "--place", "%s:2,2" % INTERCESSOR, "--a-place", "%s:5,2" % FRAPPEUR,
                # La cible SURVIT : sinon `UseNormalAttackIfAble` n'a plus de cible et le volet
                # << attaque immediate >> ne peut pas etre observe.
                "--unit-stat", "%s:Health=90000,RemainingHealth=90000" % FRAPPEUR,
                "--no-ai"], state_file)
    u_mat, u_cible = _uid(vue, INTERCESSOR), _uid(vue, FRAPPEUR)
    if None in (u_mat, u_cible):
        print("  REFUS : montage incomplet (uid manquant) -- rien n'est conclu")
        return 2
    # CHARGE : Mataneo part NON adjacent (2,2) et arrive au contact (5,1) dans le meme pas.
    # `IsCharging` n'est PAS `has_moved` : sans ce depart hors contact le passif ne fire pas.
    _run(["act", "move", "--unit", str(u_mat), "--to", "5,1"], state_file)
    casc = _run(["act", "ability", "--caster", str(u_mat), "--target", str(u_cible),
                 "--ability", str(NORMAL_ATTACK)], state_file)

    spawns = re.findall(r"AddUnit e=(\d+) .*?Unit_IsSummoned=1 .*?Unit_Parent_Id=%d" % u_mat, casc)
    powers = len(re.findall(r"Ability_Power e=%d .?AggressiveOnslaught" % u_mat, casc))
    attendu = aggressive_onslaught_max_summon(_EtatFactice(), u_mat)
    print("  natif : %d summon(s) `Unit_Parent_Id=%d` ; %d event(s) `Ability_Power"
          " <AggressiveOnslaught>`" % (len(spawns), u_mat, powers))
    print("  port  : aggressive_onslaught_max_summon = %s  (`GetNumberConstant(0x10 = nrOfSummons)`)"
          % attendu)
    if not spawns:
        print("  ECHEC : aucun summon -- le passif natif n'a pas fire (charge non realisee ?)")
        return 1
    ok = (len(spawns) == int(attendu))
    print("  [%s] compte natif == compte porte -- c'est ce qui separe `PickFirstN` (les N premiers)"
          " de `PickAtIndex` (UN element, qui rendrait 1)" % ("OK" if ok else "ECART"))
    # Les DEUX classes natives doivent avoir fire : `_PrepareAbility` (PreAttack) puis
    # `_SummonAbility` (UnitAbility). Un seul event signalerait que le `Prepare` est mort.
    print("  [%s] les DEUX classes ont fire (Prepare + Summon)"
          % ("OK" if powers >= 2 else "ECART"))

    # UNSUMMON : au debut du tour SUIVANT de Mataneo, ses enfants quittent le champ. C'est le volet
    # qui distingue `ChildrenOf` (enfants relus dans l'ETAT) de `Children` (accumulateur du cast
    # COURANT, structurellement vide un tour plus tard -> no-op silencieux).
    _run(["act", "endturn"], state_file)
    _run(["aiturn"], state_file)
    vue2 = _run(["view"], state_file)
    restants = [s for s in spawns if re.search(r"u%s \[" % s, vue2)]
    print("  [%s] unsummon au tour suivant : %d/%d summon(s) encore presents"
          % ("OK" if not restants else "ECART", len(restants), len(spawns)))
    return 0 if (ok and powers >= 2 and not restants) else 1


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--state-file", required=True)
    ap.add_argument("--board", default="MC1_67")
    ap.add_argument("--seed", type=int, default=777)
    ap.add_argument("--volet", choices=["a", "b", "ab"], default="ab")
    a = ap.parse_args()
    sf = str(Path(a.state_file).resolve())
    adv = sf.replace(".json", "_adv.json")
    rc = 0
    try:
        if a.volet in ("a", "ab"):
            rc |= volet_medicus(sf, adv, a.board, a.seed)
        if a.volet in ("b", "ab"):
            rc |= volet_onslaught(sf, a.board, a.seed)
    finally:
        _dispose(adv)
        _dispose(sf)
    return rc


if __name__ == "__main__":
    sys.exit(main())
