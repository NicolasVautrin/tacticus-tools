"""Probe #986 (#954-r3) -- ou le CRIT entre-t-il vis-a-vis du SPREAD, sur les DEUX vecteurs ?

#954-r3 constatait que le port place le crit a des etages DIFFERENTS selon la famille (shift 974
sur le vecteur ABILITY, 779 sur le vecteur NORMALE) et demandait de confronter un porteur a gros
`crit_damage` sur les deux.

LECTURE (decompile, build `rnca9r7q6c`) -- le point de composition est UNIQUE :
`IdunBattle.Operations.AttackDamageOperation$$ExecuteHit` ecrit
`request+0x58 = Nullable<int>(isCrit ? CalculateCriticalDamage(D0) : D0)` AVANT d'appeler
`PredictAttack`. `IdunBattle.Core.Services.DamagePrediction$$PredictAttackRaw` relit ce champ puis
BRANCHE sur `request+0x6a` (= `AttackDamageOptions[+0x2f]`) :
  - drapeau != 0 -> `GetBaseDamageFix64(D)`  => le SPREAD s'applique a D, crit COMPRIS ;
  - drapeau == 0 -> `MinMaxDamageFix64(D, D)` => bornes DEGENEREES, AUCUN spread.
`IdunBattle.Core.HitDamage$$GetDamage` explique lequel est lequel : `min == max -> return min`
(attaque normale, options degenerees, D0 = la stat d'attaque) contre `Next(min, max+1)` (ability,
plage de config, D0 tire).

CE QUE CE PROBE MESURE -- un discriminant SANS PARAMETRE : la LARGEUR.
Si le crit entre AVANT le spread, la plage critique est ELARGIE proportionnellement
(`(A+cd) x 2s` au lieu de `A x 2s`). S'il est ajoute APRES les bornes, la largeur est CONSERVEE.
Aucun besoin de connaitre l'attaque, l'armure, le percage ni les modificateurs : on compare
l'etendue des coups critiques observes a la largeur de la plage NON-crit annoncee par le plan.

MONTAGE (identique pour les deux bras -- une seule variable, la FAMILLE de l'attaque) :
    necroDestroyer, `CritChance=100` + `CritDamage=5000` par `--unit-stat`,
    cible necroWarden `--armor-target 2000 --hp-target 400000` (aucun coup ecrete),
    board MC1_67, seed 777, unites POSEES (`--place`/`--a-place`) pour etre a portee.

MESURE DU 2026-08-12 (build `rnca9r7q6c`, session 70) :

    bras NORMALE (Loki_NormalAttack, id 69)  -- 6 coups, tous `Attack_DidCrit=1`
        non-crit annonce   : [2610, 3912] / 6 coups  -> largeur PAR COUP = 217
        crit observe       : 3092 3949 3155 3087 4829 3453   -> etendue = 1742
        1742 >> 217  => la plage critique est ELARGIE  => crit AVANT le spread

    bras ABILITY (MultiThreatEliminator, id 1006) -- 6 coups, tous `Attack_DidCrit=1`
        non-crit annonce   : [6, 930] / 6 coups     -> largeur PAR COUP = 154
        crit observe       : 4804 4776 4812 4855 4798 4704   -> etendue = 151
        151 ~= 154   => la largeur est CONSERVEE   => crit FLAT sur les bornes brutes

L'etendue d'un echantillon de 6 tirages MINORE la vraie largeur : `1742 > 217` est donc une
refutation SURE du modele « largeur conservee » sur le vecteur normale, et `151 <= 154` est
compatible avec la conservation (et INCOMPATIBLE avec un elargissement d'un facteur 8).

Ce que ces deux bras REFUTENT, cote NORMALE (aucun ne demande de connaitre A, l'armure ou le
percage -- seule la largeur compte) :
  - « crit ajoute a plat APRES toute la reduction » (lecture naive d'`ApplyCritDamage`) ;
  - « crit ajoute aux bornes APRES le spread, avant le percage ».
Les deux CONSERVENT la largeur ; le vecteur normale l'a multipliee par 8.

=> Les DEUX placements du port sont FIDELES, et le « 974 contre 779 » de #954-r3 est l'ombre du
   spread, pas une divergence. VERDICT : NON-BUG.

Usage :
    python probe_986_crit_place_vs_spread.py --state-file <ABSOLU> [--bras normale,ability]

ASCII only (console cp1252).
"""
from __future__ import annotations

import argparse
import re
import subprocess
import sys
from pathlib import Path

PYDIR = Path(__file__).resolve().parent

# Le montage, en un seul endroit : les deux bras ne different QUE par l'ability castee.
SEED = 777
BOARD = "MC1_67"
P_UNITS = "necroDestroyer,necroWarden"
A_UNITS = "necroWarden,necroWarden"
UNIT_STAT = "necroDestroyer:CritChance=100;necroDestroyer:CritDamage=5000"
PLACES = ["--place", "necroDestroyer:2,2", "--place", "necroWarden:0,0",
          "--a-place", "necroWarden:2,3", "--a-place", "necroWarden:0,4"]
CASTER, TARGET = 77, 81
BRAS = {"normale": 69, "ability": 1006}
# Largeurs PAR COUP de la plage NON-crit, mesurees le 2026-08-12 (cf. docstring). Servent de
# reference ; le probe les RE-LIT du plan a chaque run et signale toute derive.
LARGEUR_NC_ATTENDUE = {"normale": 217, "ability": 154}


def _run(args: list[str]) -> str:
    p = subprocess.run([sys.executable, "rl_duel.py", *args], cwd=str(PYDIR),
                       capture_output=True, text=True, errors="replace")
    return (p.stdout or "") + (p.stderr or "")


def _largeur_non_crit(plan: str, ability_label: str, hits: int) -> "int | None":
    """Largeur PAR COUP de la plage non-crit, lue dans le PLAN D'ATTAQUE (`[min-max]` = total
    sur `hits` coups). Rend None si le plan ne porte pas cette ability."""
    best = None
    for m in re.finditer(re.escape(ability_label) + r".*?\[(\d+)-(\d+)\]", plan):
        lo, hi = int(m.group(1)), int(m.group(2))
        w = (hi - lo) // hits
        if best is None or w > best:
            best = w
    return best


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--state-file", required=True,
                    help="chemin ABSOLU, hors data/ (un par bras, suffixe automatique)")
    ap.add_argument("--bras", default="normale,ability")
    args = ap.parse_args()

    rc = 0
    for bras in [b.strip() for b in args.bras.split(",") if b.strip()]:
        if bras not in BRAS:
            print("[986] bras inconnu: %s" % bras)
            return 2
        sf = str(Path(args.state_file).with_suffix("")) + ("_%s.json" % bras)
        plan = _run(["build", "--seed", str(SEED), "--board", BOARD,
                     "--p-units", P_UNITS, "--a-units", A_UNITS,
                     "--unit-stat", UNIT_STAT, "--armor-target", "2000",
                     "--hp-target", "400000", *PLACES,
                     "--state-file", sf, "--no-ai"])
        label = "Loki_NormalAttack" if bras == "normale" else "MultiThreatEliminator"
        out = _run(["act", "ability", "--caster", str(CASTER), "--target", str(TARGET),
                    "--ability", str(BRAS[bras]), "--state-file", sf])
        hits = [int(m.group(1)) for m in re.finditer(r"Amount=(\d+)", out)]
        crits = out.count("Attack_DidCrit=1")
        _run(["dispose", "--state-file", sf])

        if not hits:
            print("[986][%s] AUCUN coup mesure -- montage a re-verifier" % bras)
            rc = 1
            continue
        w_nc = _largeur_non_crit(plan, label, max(1, len(hits)))
        etendue = max(hits) - min(hits)
        print("[986][%s] coups=%d crits=%d  valeurs=%s" % (bras, len(hits), crits, hits))
        print("[986][%s] largeur NON-crit par coup = %s (attendue %s)"
              % (bras, w_nc, LARGEUR_NC_ATTENDUE[bras]))
        print("[986][%s] etendue des coups CRITIQUES = %d" % (bras, etendue))
        if w_nc is None:
            print("[986][%s] plan illisible -- pas de verdict" % bras)
            rc = 1
            continue
        # L'etendue d'un echantillon MINORE la vraie largeur : seul l'ELARGISSEMENT est une
        # conclusion sure. La conservation se lit « compatible », pas « demontree ».
        if bras == "normale":
            ok = etendue > 2 * w_nc
            print("[986][normale] %s : etendue %d %s 2 x largeur non-crit (%d) => crit %s le spread"
                  % ("OK" if ok else "ECHEC", etendue, ">" if ok else "<=", 2 * w_nc,
                     "AVANT" if ok else "APRES"))
        else:
            ok = etendue <= 2 * w_nc
            print("[986][ability] %s : etendue %d %s 2 x largeur non-crit (%d) => largeur %s"
                  % ("OK" if ok else "ECHEC", etendue, "<=" if ok else ">", 2 * w_nc,
                     "CONSERVEE" if ok else "ELARGIE"))
        rc = rc or (0 if ok else 1)
    return rc


if __name__ == "__main__":
    sys.exit(main())
