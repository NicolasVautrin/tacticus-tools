"""#1037 -- EPREUVE ADVERSARIALE du port `WyrdmakersHelm` : 12 mutants, tous doivent etre VUS.

Un test vert ne prouve rien tant qu'on n'a pas montre qu'il ROUGIT quand le port ment. Ce probe
applique une mutation a la fois DANS UNE COPIE de l'arbre (jamais dans l'arbre de travail), rejoue
`tests/engine/runner/test_1037_wyrdmakers_helm_offline.py`, et exige `rc != 0`.

Chaque mutant vise UN etage precis. S'il passe INAPERCU, c'est que ce cran-la n'est garde par
personne -- pas que le port est bon.

    python probe_1037_wyrdmakers_helm_mutants.py

ASCII only (console cp1252).
"""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile

_HERE = os.path.dirname(os.path.abspath(__file__))
_TEST = "tests/engine/runner/test_1037_wyrdmakers_helm_offline.py"

_HELM = "engine/runner/operations/triggers/loki/wyrdmakers_helm.py"
_REG = "engine/runner/operations/triggers/dispatch/registry.py"
_HEAL = "engine/runner/operations/heal.py"
_TURN = "engine/runner/operations/turnflow.py"
_CTX = "engine/runner/abilities/behaviours/context.py"

#: (nom, fichier, ancien, nouveau) -- l'ancien doit etre PRESENT, sinon le mutant est INAPPLICABLE
#: (et un mutant inapplicable qui se lirait « non vu » serait un faux negatif : on le signale).
MUTANTS = [
    ("registre retire",
     _REG, '    "WyrdmakersHelm": [WyrdmakersHelmAbility],', '    # mutant : entree retiree'),
    ("event 0x2b au lieu de 0x2c",
     _HELM, "event_id = EventTriggerType.UnitHealedWithRemoveEffects",
     "event_id = EventTriggerType.UnitHealed"),
    ("gate IsTurnOf supprime",
     _HELM, "        IsTurnOf(Owner()))", "        OwnerIsTarget())"),
    ("gate AreFriends supprime",
     _HELM, "        AreFriends(Owner(), Target(), selection_type=FRIENDS_COMPARISON))",
     "        IsAdjacent(Owner(), Target(), selection_type=int(ADJACENCY_SELECTION)))"),
    ("gate IsAdjacent supprime",
     _HELM, "        IsAdjacent(Owner(), Target(), selection_type=int(ADJACENCY_SELECTION)),",
     "        AreFriends(Owner(), Target(), selection_type=FRIENDS_COMPARISON),"),
    ("egalite devenue >= 1 (Const(0))",
     _HELM, "FIRST_HEAL_OF_TURN = 1", "FIRST_HEAL_OF_TURN = 0"),
    ("stat-mod sur DEFENSE au lieu d'ATTACK",
     _HELM, "WYRDMAKERS_HELM_STAT = StatType.ATTACK", "WYRDMAKERS_HELM_STAT = StatType.DEFENSE"),
    ("gate final sur la CIBLE au lieu du PORTEUR",
     _HELM, "        If(Not(IsDead(Owner())),", "        If(Not(IsDead(Target())),"),
    ("RemoveEffect du stat-mod supprime",
     _HELM, "        RemoveEffect(int(WYRDMAKERS_HELM_STAT_MOD), Owner()),",
     "        SetCache(cache),"),
    ("increment du compteur supprime",
     _HEAL, "            uc.times_healed_this_turn = int(getattr(uc, \"times_healed_this_turn\", 0) or 0) + 1",
     "            pass"),
    ("reset de turn-start supprime",
     _TURN, "                uc.times_healed_this_turn = 0", "                pass"),
    ("gate removeEffects du vecteur supprime",
     _HEAL, "        if remove_effects:", "        if True:"),
    ("compteur retire de _LIVE_KEYS (fige au seed)",
     _CTX, '                        "defeatedUnits", "timesHealedThisTurn"})',
     '                        "defeatedUnits"})'),
]


def main() -> int:
    base = os.path.abspath(os.path.join(_HERE, "..", ".."))
    vus, rates, inapplicables = [], [], []
    for nom, rel, avant, apres in MUTANTS:
        tmp = tempfile.mkdtemp(prefix="mut1037_")
        try:
            arbre = os.path.join(tmp, "scripts", "python")
            shutil.copytree(os.path.join(base, "scripts", "python"), arbre,
                            ignore=shutil.ignore_patterns("__pycache__", ".pytest_cache", "logs"))
            # `data/` COMPLET : les caches lazy du gameconfig doivent voir les memes ENTREES que
            # l'arbre mesure, sinon la divergence mesuree est celle du montage (lecon #270-r1-r1).
            if os.path.isdir(os.path.join(base, "data")):
                shutil.copytree(os.path.join(base, "data"), os.path.join(tmp, "data"),
                                ignore=shutil.ignore_patterns("__pycache__"))
            cible = os.path.join(arbre, rel.replace("/", os.sep))
            with open(cible, encoding="utf-8") as fh:
                src = fh.read()
            if avant not in src:
                inapplicables.append(nom)
                print("INAPPLICABLE  %s  (motif absent de %s)" % (nom, rel))
                continue
            with open(cible, "w", encoding="utf-8", newline="") as fh:
                fh.write(src.replace(avant, apres, 1))
            env = dict(os.environ)
            env["PYTHONPATH"] = arbre
            r = subprocess.run([sys.executable, "-m", "pytest", _TEST, "-q", "--no-header", "-x"],
                               cwd=arbre, capture_output=True, text=True, env=env, timeout=600)
            if r.returncode != 0:
                vus.append(nom)
                print("VU            %s  (rc=%d)" % (nom, r.returncode))
            else:
                rates.append(nom)
                print("NON VU        %s  <-- ce cran n'est garde par PERSONNE" % nom)
        finally:
            shutil.rmtree(tmp, ignore_errors=True)
    print("")
    print("BILAN : %d vus / %d rates / %d inapplicables (sur %d)"
          % (len(vus), len(rates), len(inapplicables), len(MUTANTS)))
    for n in rates:
        print("   RATE : " + n)
    for n in inapplicables:
        print("   INAPPLICABLE : " + n)
    return 0 if (not rates and not inapplicables) else 1


if __name__ == "__main__":
    raise SystemExit(main())
