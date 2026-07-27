"""MESURE la permissivite du gate de ciblage : quels masques exigent des regles NON PORTEES.

CE QUE CA REPOND
----------------
Une regle de `TargetingRule` non portee ne refuse JAMAIS -- degradation PERMISSIVE assumee (le
port ne peut pas inventer un refus qu'il ne sait pas decider). La consequence n'est pas neutre :
le moteur offline accepte des casts que le natif REFUSE, et un entrainement ira exploiter cet
espace d'action elargi. C'est silencieux : ni erreur, ni crash.

Tant que les masques etaient des litteraux hexadecimaux et la table des bits une prose maintenue a
la main, la question « quelles regles ce masque exige-t-il que je n'implemente pas ? » n'avait pas
de reponse mecanique. Avec l'enum genere (`targeting_rule.py`), elle en a une, et c'est ce que ce
probe imprime : par ability, les bits poses ET non portes.

Ce probe MESURE, il ne garde pas -- il n'echoue pas sur un manque, il le chiffre. Le passage a une
GARDE (echec sur toute NOUVELLE permissivite) est le role du cliquet de non-regression du registre.

Sortie ASCII only (console Windows cp1252).
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from engine.runner.abilities import ABILITY_CLASSES  # noqa: E402
from engine.runner.abilities.targeting_rule import TargetingRule as TR  # noqa: E402

# Regles EFFECTIVEMENT consommees par la cascade portee. Chacune est tracee a son site :
# cf. `engine/runner/abilities/targeting.py`, `get_invalid_target_reason` /
# `get_invalid_caster_reason`. Toute autre regle posee dans un masque est INERTE offline.
PORTEES = (
    TR.TargetMatchesDynamicRule    # point d'extension par ability (get_dynamic_invalid_target_reason)
    | TR.TargetIsFriendly
    | TR.TargetIsEnemy
    | TR.TargetIsTargetable        # inverse par AllowUntargetableTarget
    | TR.TargetIsCaster            # self-only
    | TR.TargetIsCasterOrEnemy
    | TR.CasterHasNotMoved         # volet CASTER
)

# Bits qui ne sont PAS des regles de refus : les compter comme « non portes » serait faux.
NON_REGLES = (
    TR.ValidRequest
    | TR.CasterIsPossibleTarget    # flag DECLARATIF (get_CanTargetCaster), aucune cascade ne le lit
    | TR.AllowUntargetableTarget   # INVERSE une regle, n'en est pas une
    | TR.AllowObscuredTargetByElevation
    | TR.AllowObscuredTargetByWalls
    | TR.AllowObscuredTarget
    | TR.AllowNullCasterTile
    | TR.AllowSteppableUnit
    | TR.AllowDeadTarget
    | TR.AllowIgnoreForcedAttackTarget
    | TR.AllowUnwalkableTargetTile
    | TR.AllowTargetWithoutTile
    | TR.AddCaster
    | TR.AddCasterIfMatchesDynamicRule
    | TR.AddCasterIfAtLeastOneTarget
    | TR.AddCasterIfAtLeastOneFreeTileInRange
)


def main() -> int:
    avec, sans = [], []
    for aid, cls in sorted(ABILITY_CLASSES.items()):
        opts = getattr(cls, "TARGETING_OPTIONS", None)
        (sans if opts is None else avec).append((aid, cls, opts))

    print("registre : %d abilities, %d avec masque, %d SANS"
          % (len(ABILITY_CLASSES), len(avec), len(sans)))
    print("  (une ability sans masque n'est gatee par RIEN -- retour 0 immediat)")
    print()

    manquantes = {}
    inertes = 0
    for aid, cls, opts in avec:
        reste = TR(int(opts.rules)) & ~PORTEES & ~NON_REGLES
        if not reste:
            continue
        inertes += 1
        noms = [m.name for m in TR if int(m) and not (int(m) & (int(m) - 1)) and (reste & m)]
        print("%-5d %-34s %s" % (aid, cls.__name__, " ".join(noms)))
        for n in noms:
            manquantes[n] = manquantes.get(n, 0) + 1

    print()
    print("%d masques sur %d exigent au moins une regle INERTE offline" % (inertes, len(avec)))
    print()
    print("regles non portees, par frequence -- c'est l'ordre de rentabilite d'un portage :")
    for nom, n in sorted(manquantes.items(), key=lambda kv: (-kv[1], kv[0])):
        print("  %-34s %d ability(s)" % (nom, n))
    return 0


if __name__ == "__main__":
    sys.exit(main())
