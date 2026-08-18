"""#920-r3 -- LE MODE SE PROPAGE DANS L'ARBRE, il ne se rabat pas sur un scalaire.

## Ce que le natif fait, RE-MESURE sur le build charge

`IdunBattle.DSL.IAmountFormula` a QUATRE points d'entree -- slots `1 Calculate`, `2 CalculateMin`,
`3 CalculateMax`, `4 CalculateAverage` -- et le dispatcher natif porte le slot en PREMIER
argument. Les corps de `CalculateMin`/`CalculateMax` d'un noeud COMPLEXE sont STRICTEMENT
identiques a celui de `Calculate` : seul le slot invoque sur les enfants change. Le natif parcourt
donc l'arbre DEUX FOIS, chaque parcours restant COHERENT jusqu'aux feuilles.

RECENSEMENT RE-DERIVE (recherche LITTERALE du dispatcher a slot 2 dans le decompile du build
charge, donc insensible a la dedup IL2CPP par adresse) -- **SEPT** noeuds propagent :
`SumAmount`, `MultiplyAmount`, `MultiplyPercentageRecursively`, `IdunBattle.DSL.IfAmount`,
`ConditionalAmount`, `CacheAmount`, `PercentageOf`. `RandomAmount` et
`FirstHitInCurrentAttackDamageRange` n'y figurent PAS (ils court-circuitent), et les noeuds
SIMPLES (`MinAmount`, `MaxAmount`, `DivideAmount`) heritent du repli sur `Calculate`.

## Ce que ce cliquet garde, et pourquoi ses temoins sont NON VIDES

Un test qui dirait seulement << la propagation marche >> serait vert sur un port ou tout est
degenere. Chaque etage porte donc son CONTRE-TEMOIN :

  * etage 1 : les propagateurs DESCENDENT le mode -- temoin `RandomAmount(10, 20)`, dont les
    bornes DIFFERENT (un enfant degenere ne discriminerait rien, l'etage l'assertionne) ;
  * etage 2 : les noeuds SIMPLES ne le descendent PAS -- meme enfant, resultat DEGENERE ;
  * etage 3 : `Negative` INVERSE les bornes (`min > max`), et c'est le comportement NATIF -- le
    << reparer >> ferait diverger le port ;
  * etage 4 : `calculate_average` d'un composite ne consomme AUCUN tirage, la ou `Calculate` en
    consomme un. C'est la consequence OBSERVABLE de la propagation ;
  * etage 5 : le REGISTRE des surcharges du port est confronte a la liste LUE.

CONTRE-EPREUVE (jouee) : retirer `calculate_min`/`calculate_max` d'un propagateur fait rougir les
etages 1 et 4 ; en ajouter a `Min`/`Max`/`Half` fait rougir l'etage 2 ; retirer l'inversion de
`Negative` fait rougir l'etage 3.

ASCII only.
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from engine.dsl.base import Const, AAmountFormula                       # noqa: E402
from engine.entities import formulas as F                               # noqa: E402

#: Ce qui doit changer pour que ce FICHIER puisse changer de verdict (#486-r15).
DECLENCHEUR = {
    "chemins": (
        "scripts/python/engine/entities/formulas.py",
        "scripts/python/engine/dsl/base.py",
        "scripts/python/tests/engine/test_920r3_modes_de_formule_offline.py",
    ),
    "build": False,
    "toujours": False,
    "raison": ("Le fichier ne construit que des noeuds DSL a partir de `Const` : il ne lit ni le "
               "binaire ni `data/symbols/**`, d'ou `build: False`. Les deux chemins declares sont "
               "les seuls qui puissent faire basculer le verdict -- `formulas.py` (les surcharges "
               "de mode) et `dsl/base.py` (le dispatcher `invoke_slot` et le repli de la BASE). "
               "L'etage 5 confronte le REGISTRE des surcharges a la liste LUE : il rougirait sur "
               "un mirror ajoute ou retire dans l'un ou l'autre."),
}

#: Les SEPT propagateurs LUS. Ceux que ce port ne contient pas encore sont NOMMES, pas oublies :
#: `CacheAmount` et `MultiplyPercentageRecursively` n'ont AUCUN mirror Python (residu).
PROPAGATEURS_LUS = ("SumAmount", "MultiplyAmount", "MultiplyPercentageRecursively",
                    "IfAmount", "ConditionalAmount", "CacheAmount", "PercentageOf")
#: Appariement mirror -> symbole natif, pour les propagateurs QUI EXISTENT cote port.
MIRROIRS = {"Sum": "SumAmount", "Multiply": "MultiplyAmount", "If": "IfAmount",
            "ConditionalAmount": "ConditionalAmount", "PercentageOf": "PercentageOf"}
#: Les fabriques qui allouent un `MultiplyAmount` DEGUISE -> elles propagent, elles aussi.
FABRIQUES_MULTIPLY = ("Double", "Negative")
#: Les noeuds SIMPLES : `ASimpleAmountFormula` replie Min/Max sur `Calculate`.
SIMPLES = ("Min", "Max", "Divide", "Half")


class _Rng:
    """Compteur de tirages -- il ne simule rien, il COMPTE, et c'est tout ce qu'on lui demande."""

    def __init__(self):
        self.n = 0

    def next_internal(self, lo, hi):
        self.n += 1
        return lo


def _ctx():
    from engine.dsl.base import DslContext
    return DslContext()


def _plage():
    """Un enfant a AMPLITUDE NON NULLE -- sans lui, aucun etage ne discrimine."""
    return F.RandomAmount(Const(10), Const(20))


# --------------------------------------------------------------------------------------------
# Etage 1 -- les PROPAGATEURS descendent le mode.
# --------------------------------------------------------------------------------------------

def test_les_propagateurs_descendent_le_mode():
    ctx, enfant = _ctx(), _plage()
    assert (enfant.calculate_min(ctx), enfant.calculate_max(ctx)) == (10, 20), \
        "TEMOIN DEGENERE : l'enfant doit avoir une amplitude, sinon rien ne discrimine"
    cas = [
        ("Sum", F.Sum(enfant, Const(5)), 15, 25),
        ("Multiply", F.Multiply(enfant, Const(3)), 30, 60),
        ("If", F.If(Const(1), enfant, Const(0)), 10, 20),
        ("ConditionalAmount", F.ConditionalAmount(Const(0), Const(0), enfant), 10, 20),
        # `PercentageOf(pct, base)` : `+0x10` = pourcentage, `+0x18` = montant.
        ("PercentageOf", F.PercentageOf(Const(50), enfant), 5, 10),
        # Fabriques qui allouent un `MultiplyAmount` : elles propagent.
        ("Double", F.Double(enfant), 20, 40),
    ]
    for nom, noeud, mn, mx in cas:
        assert noeud.calculate_min(ctx) == mn, "%s.calculate_min" % nom
        assert noeud.calculate_max(ctx) == mx, "%s.calculate_max" % nom


def test_la_propagation_traverse_PLUSIEURS_jointures():
    """Le gisement n'etait pas un arrondi : le mode etait perdu **des la premiere jointure**.
    Un arbre a DEUX etages composites le montre."""
    ctx = _ctx()
    arbre = F.PercentageOf(Const(50), F.Sum(_plage(), Const(10)))
    assert (arbre.calculate_min(ctx), arbre.calculate_max(ctx)) == (10, 15)


# --------------------------------------------------------------------------------------------
# Etage 2 -- les noeuds SIMPLES ne descendent PAS le mode (contre-temoin).
# --------------------------------------------------------------------------------------------

def test_les_noeuds_simples_ne_descendent_pas_le_mode():
    """`MinAmount` / `MaxAmount` / `DivideAmount` derivent d'`ASimpleAmountFormula`, dont
    `CalculateMin` et `CalculateMax` retombent sur `Calculate` -- avec les enfants en mode NORMAL.

    ⚠ C'EST CE QUI RECONCILIE #920-r3 AVEC #91. La reduction CAPEE defenseur
    (`GuardianOrganism`) est un arbre `Min(PercentageOf(CurrentDamage, pct), cap)` : sa RACINE est
    un `MinAmount`, donc le natif LUI-MEME ne le parcourt qu'UNE fois. Le scalaire FLAT du port
    (confirme LIVE deux fois) n'est donc pas le gisement que ce residu vise."""
    ctx, enfant = _ctx(), _plage()
    construits = {"Min": lambda: F.Min(enfant, Const(2)),
                  "Max": lambda: F.Max(enfant, Const(2)),
                  "Divide": lambda: F.Divide(enfant, Const(2), 0),
                  "Half": lambda: F.Half(enfant, 0)}
    for nom in SIMPLES:
        noeud = construits[nom]()
        mn, mx = noeud.calculate_min(ctx), noeud.calculate_max(ctx)
        assert mn == mx == noeud.calculate(ctx), \
            "%s a DESCENDU le mode : min=%s max=%s calculate=%s -- or ce noeud est SIMPLE" \
            % (nom, mn, mx, noeud.calculate(ctx))


# --------------------------------------------------------------------------------------------
# Etage 3 -- `Negative` INVERSE, et c'est le natif.
# --------------------------------------------------------------------------------------------

def test_negative_inverse_les_bornes_et_ce_n_est_pas_un_bug():
    """`DSLFormulas$$Negative(a)` alloue un `MultiplyAmount(a, Const(-1))` : patron propagateur
    SANS croisement de bornes. Donc `CalculateMin = a.CalculateMin * (-1)` = la borne HAUTE de
    `-a`, et le natif rend `min > max` sur toute amplitude non nulle."""
    ctx = _ctx()
    n = F.Negative(_plage())
    assert (n.calculate_min(ctx), n.calculate_max(ctx)) == (-10, -20)
    assert n.calculate_min(ctx) > n.calculate_max(ctx), \
        "l'inversion a disparu -- elle est NATIVE, la corriger ferait diverger le port"


# --------------------------------------------------------------------------------------------
# Etage 4 -- la CONSEQUENCE OBSERVABLE : `calculate_average` d'un composite ne TIRE pas.
# --------------------------------------------------------------------------------------------

def test_calculate_average_d_un_composite_ne_consomme_aucun_tirage():
    """Sans propagation, `calculate_average` d'un composite retombait sur `Calculate`, donc sur le
    TIRAGE de `RandomAmount` -- une prevision qui consomme le PRNG. Avec elle, les deux parcours
    lisent les bornes et n'appellent jamais le RNG.

    Le TEMOIN qui rend cet etage non vide : `Calculate`, lui, DOIT tirer."""
    ctx = _ctx()
    rng_avg, rng_calc = _Rng(), _Rng()
    arbre_avg = F.Sum(F.RandomAmount(Const(10), Const(20), rng=rng_avg), Const(5))
    arbre_calc = F.Sum(F.RandomAmount(Const(10), Const(20), rng=rng_calc), Const(5))
    moyenne = arbre_avg.calculate_average(ctx)
    arbre_calc.calculate(ctx)
    assert rng_calc.n == 1, ("TEMOIN VIDE : `Calculate` doit consommer un tirage, sinon l'etage "
                             "ne separe rien (n=%d)" % rng_calc.n)
    assert rng_avg.n == 0, "`calculate_average` a consomme %d tirage(s)" % rng_avg.n
    assert moyenne == 20, moyenne          # (15 + 25) // 2


# --------------------------------------------------------------------------------------------
# Etage 5 -- LE REGISTRE : qui surcharge, cote port, doit etre EXACTEMENT ce qui propage, cote LU.
# --------------------------------------------------------------------------------------------

def test_le_registre_des_surcharges_correspond_a_la_liste_LUE():
    """Un mirror ajoute ou retire sans relire le decompile fait rougir ici.

    Deux propagateurs LUS n'ont AUCUN mirror Python (`CacheAmount`,
    `MultiplyPercentageRecursively`) : ils sont NOMMES, pas oublies -- residu ouvert."""
    surcharge = {n for n in dir(F)
                 if isinstance(getattr(F, n), type)
                 and issubclass(getattr(F, n), AAmountFormula)
                 and getattr(F, n) is not AAmountFormula      # la BASE porte le repli, pas une surcharge
                 and "calculate_min" in vars(getattr(F, n))}
    attendu = set(MIRROIRS) | set(FABRIQUES_MULTIPLY) | {"RandomAmount"}
    assert surcharge == attendu, (
        "surcharges de mode desynchronisees du decompile : en trop=%s manquantes=%s. Les SEPT "
        "propagateurs LUS sont %s ; `RandomAmount` surcharge pour COURT-CIRCUITER (il lit `+0x10`"
        " seul / `+0x18` seul et rappelle le slot 1)."
        % (sorted(surcharge - attendu), sorted(attendu - surcharge), list(PROPAGATEURS_LUS)))
    absents = [s for s in PROPAGATEURS_LUS if s not in set(MIRROIRS.values())
               and s not in ("MultiplyAmount",)]
    assert absents == ["MultiplyPercentageRecursively", "CacheAmount"], \
        "la liste des propagateurs SANS mirror a bouge : %s" % absents
