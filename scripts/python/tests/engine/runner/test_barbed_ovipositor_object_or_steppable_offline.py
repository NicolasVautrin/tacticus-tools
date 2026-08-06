"""#462-r4b-r1-r1-r1-r1-b-r1-r1-r3 -- GARDE des DEUX conjoints de TRAIT de
`IdunBattleLogic.Entities.Abilities.Triggered.Loki.BarbedOvipositorAbility$$CreateTrigger`.

CE QUE CE FICHIER VERROUILLE, ET CE QU'IL NE VERROUILLE PAS. Le conjoint
`NOT IsObjectOrSteppable(sel@+0x60)` et son voisin `NOT HasTrait(sel@+0x60, 5 = Mechanical)`
etaient RECOPIES A LA MAIN. **Leurs LITTERAUX etaient JUSTES** (`Steppable` 27, `Object` 13,
`Mechanical` 5) -- contrairement a `MasterOfTheTutelaries` (#462-...-r1), qui nommait `Decoy`
(1053). Ce fichier ne garde donc PAS un choix de traits : il garde le **SUBSTRAT** sur lequel ces
traits sont cherches.

  * la recopie lisait `StatsComponent.ctx.traits` BRUT, avec le repli `set()` ;
  * les noeuds du foyer lisent `_traits` = `entity_trait_names` (le repli gameconfig #226).

Cote natif il n'y a qu'UNE lecture : `IdunBattle.Entities.Components.BaseUnitComponent$$HasTrait`
interroge les collections de l'entite, et la mort n'en vide AUCUNE. Un cadavre garde ses traits ;
le `set()` du port etait un ARTEFACT.

CE QUE LA MIGRATION CHANGE (mesure `probe_..._r3 --step substrat`, re-derivee a chaque run) :
  * regime NOMINAL (victime VIVANTE au chargement, donc porteuse d'un `StatsComponent`) : les deux
    substrats coincident sur `{Steppable, Object, Mechanical}` -> **AUCUN verdict ne bouge**. C'est
    le regime de TOUS les bras de `test_barbed_ovipositor_live.py`.
  * regime CADAVRE (victime deja morte au chargement : `combatSnapshot.units` ne la porte pas,
    donc pas de `StatsComponent`) : substrat BRUT = `[]` -> les deux gates AVEUGLES. **TROIS bras
    basculent**, et le port posait un Ripper que le natif refuse.

ATTEIGNABILITE. Un `On(UnitDeath)` ne vise un cadavre-au-chargement que s'il a ete RESSUSCITE :
`IdunBattle.Operations.ResurrectUnitOperation$$Execute` (port `operations/resurrect.py`) cible
explicitement une unite DEFEATED, et ni lui ni `operations/revive.py` ne pose de `StatsComponent`.
Le regime est CONFRONTE sur un etat LIVE par
`test_barbed_ovipositor_live.py::test_barbed_ovipositor_corpse_substrate_live`.

POURQUOI UN TEST ET PAS SEULEMENT LE PROBE. La mesure vit dans
`probe_462_r4b_r1_r1_r1_r1_b_r1_r1_r3_barbed_object_or_steppable.py --step guard`, mais **un probe
MESURE, il ne GARDE pas** : aucune passe de tests ne le joue. Ce fichier rejoue le meme montage
sous pytest -- le probe reste la source du montage (aucun fork : ces tests l'IMPORTENT).

OFFLINE, ET C'EST UN CHOIX : `matches` est un predicat PUR, il se teste sans runner ni tirage.

ASCII only (cp1252).
"""
from __future__ import annotations

import pytest

import probe_462_r4b_r1_r1_r1_r1_b_r1_r1_r3_barbed_object_or_steppable as P

# (visualId REEL, regime `StatsComponent`, verdict attendu de `matches`).
# Le visualId doit etre REEL : dans le regime CADAVRE le substrat est le kit gameconfig de cet
# id, pas une liste de traits inventee. Le verdict attendu est le MEME dans les deux regimes --
# c'est exactement ce que le fix etablit.
BRAS = [
    pytest.param("astraBullgryn", True, True, id="controle-NOMINAL"),
    pytest.param("astraBullgryn", False, True, id="controle-CADAVRE"),
    pytest.param("necroWarden", True, False, id="Mechanical-5-NOMINAL"),
    pytest.param("necroWarden", False, False, id="Mechanical-5-CADAVRE-BASCULE"),
    pytest.param("genesSmnDecoy", True, False, id="Steppable-27-NOMINAL"),
    pytest.param("genesSmnDecoy", False, False, id="Steppable-27-CADAVRE-BASCULE"),
    pytest.param("LootObj_Crate_Imp", True, False, id="Object-13-NOMINAL"),
    pytest.param("LootObj_Crate_Imp", False, False, id="Object-13-CADAVRE-BASCULE"),
]


@pytest.mark.parametrize("vis,stats,attendu", BRAS)
def test_les_deux_conjoints_de_trait_gatent_la_victime(vis, stats, attendu):
    """`NOT IsObjectOrSteppable(target)` et `NOT HasTrait(target, 5)` sur `sel@+0x60` -- le sujet
    est la VICTIME (le 2e argument d'`AreEnemies`), jamais le porteur (`sel@+0x30`).

    Le verdict ne doit dependre QUE des traits de la victime, pas de la facon dont son entite a
    ete chargee."""
    got, _ = P.verdict(vis, stats)
    assert got is attendu, (
        "victime %r (StatsComponent=%s) -> matches=%s, attendu %s. Les conjoints de trait de "
        "`BarbedOvipositorAbility$$CreateTrigger` doivent passer par `entities/triggers.py` "
        "(`is_object_or_steppable` + `HasTrait`), donc par le substrat `entity_trait_names`."
        % (vis, stats, got, attendu))


def test_le_verdict_ne_depend_PAS_du_regime_de_chargement():
    """L'INVARIANT que le fix installe : pour un meme visualId, `matches` rend le MEME verdict que
    la victime ait ete chargee vivante ou deja morte.

    C'est la formulation POSITIVE du defaut : avant le fix, un cadavre rendait un verdict
    DIFFERENT d'une unite vivante de meme kit, sans qu'aucun trait n'ait change."""
    ecarts = []
    for vis in sorted({p.values[0] for p in BRAS}):
        a, _ = P.verdict(vis, True)
        b, _ = P.verdict(vis, False)
        if a is not b:
            ecarts.append((vis, a, b))
    assert not ecarts, (
        "le verdict depend encore du regime de chargement pour %r (NOMINAL, CADAVRE) -- un "
        "conjoint lit toujours un substrat qui s'effondre quand `StatsComponent` manque."
        % (ecarts,))


@pytest.mark.parametrize("vis,stats,attendu", BRAS)
def test_contre_epreuve_neutralisee_les_conjoints_mordent(vis, stats, attendu):
    """CONTRE-EPREUVE 1 -- les conjoints EXISTENT et ils sont CONSULTES.

    Le meme etat est rejoue avec les deux noeuds rendus INERTES (toujours faux, donc les deux
    `NOT` toujours vrais) : cela reconstitue << aucun conjoint de trait >>. On exige que le verdict
    BASCULE sur les bras gates et COINCIDE sur les autres.

    ⚠ LA MUTATION EST VERIFIEE AVANT SON RESULTAT. `calls == 0` = les noeuds substitues n'ont
    jamais ete consultes : la contre-epreuve n'aurait alors rien prouve, et son << verdict
    identique >> se lirait a tort comme << les conjoints ne changent rien >>."""
    neu, calls = P.verdict(vis, stats, "neutralise")
    assert calls, (
        "MUTATION INERTE : les noeuds substitues ont ete consultes %r fois pour (%r, stats=%s). "
        "La contre-epreuve ne mesure RIEN -- soit un conjoint anterieur court-circuite avant eux "
        "(`OwnerIsActor`, `AreEnemies`, `UnitComponent`), soit la substitution ne prend pas."
        % (calls, vis, stats))
    got, _ = P.verdict(vis, stats)
    if not attendu:
        assert neu != got, (
            "(%r, stats=%s) : neutraliser les conjoints ne change RIEN (%s -> %s) alors que ce "
            "bras est precisement celui qu'ils gatent -- le `False` vient donc d'AILLEURS, et ce "
            "fichier ne garde pas ce qu'il pretend garder." % (vis, stats, got, neu))
    else:
        assert neu == got, (
            "(%r, stats=%s) : neutraliser les conjoints change le verdict (%s -> %s) alors que ce "
            "bras ne doit PAS etre gate -- ils mordent trop large." % (vis, stats, got, neu))


@pytest.mark.parametrize("vis,stats,attendu", BRAS)
def test_contre_epreuve_la_lecture_brute_rejouee_donne_l_etat_d_avant(vis, stats, attendu):
    """CONTRE-EPREUVE 2 -- c'est ELLE qui prouve que le fix n'est pas un no-op deguise.

    Les deux noeuds sont remplaces par la lecture BRUTE `set(StatsComponent.ctx.traits)` (repli
    `set()`) : cela reconstitue EXACTEMENT le port d'avant ce fix. On exige (a) que la substitution
    ait mordu, (b) qu'elle rende le verdict d'AVANT -- **DERIVE** par `P.attendu_recopie`, jamais
    recopie a la main -- et (c) qu'il DIFFERE du verdict courant sur les seuls bras CADAVRE gates.

    Sans ce test, un fix qui n'aurait migre QU'UN des deux conjoints resterait invisible : les
    quatre bras NOMINAUX coincident dans les deux mondes."""
    rec, calls = P.verdict(vis, stats, "recopie")
    avant = P.attendu_recopie(vis, stats)
    assert calls, (
        "MUTATION INERTE : la lecture brute substituee a ete consultee %r fois pour (%r, "
        "stats=%s)." % (calls, vis, stats))
    assert rec is avant, (
        "(%r, stats=%s) : rejouer la lecture BRUTE rend %s, or le port d'AVANT le fix rendait %s. "
        "La contre-epreuve ne reconstitue pas l'etat d'avant -- elle ne mesure donc pas le "
        "CHANGEMENT." % (vis, stats, rec, avant))
    got, _ = P.verdict(vis, stats)
    if attendu != avant:
        assert rec != got, (
            "(%r, stats=%s) : le fix devait CHANGER ce bras (%s -> %s) et il ne change rien."
            % (vis, stats, avant, attendu))
    else:
        assert rec == got, (
            "(%r, stats=%s) : le fix a change un bras qu'il ne devait PAS changer (%s -> %s)."
            % (vis, stats, avant, attendu))


def test_le_fix_change_exactement_les_trois_bras_CADAVRE():
    """La migration n'est ni un no-op ni un elargissement sauvage : elle deplace EXACTEMENT les
    trois verdicts CADAVRE dont le kit porte un trait gate, et AUCUN verdict NOMINAL.

    Le second point est le plus important a figer : c'est lui qui autorise a dire que la migration
    est value-preserving la ou toute la suite live se joue."""
    changeants = [(p.values[0], p.values[1]) for p in BRAS
                  if p.values[2] != P.attendu_recopie(p.values[0], p.values[1])]
    assert changeants == [("necroWarden", False), ("genesSmnDecoy", False),
                          ("LootObj_Crate_Imp", False)], (
        "les bras que le fix fait changer ne sont plus les trois bras CADAVRE mais %r"
        % (changeants,))


def test_le_port_passe_par_le_foyer_partage():
    """Les conjoints doivent venir du FOYER, pas d'une n-ieme recopie manuelle.

    C'est ce qui a produit le defaut d'origine : `IsObjectOrSteppable` a HUIT call-sites natifs, le
    port en portait plusieurs, recopies a la main -- et ils DIVERGEAIENT. Cette assertion fige
    l'identite de l'objet : si quelqu'un remplace le noeud par une recopie locale, le test rougit
    meme si le comportement coincide, parce que c'est la DIVERGENCE FUTURE qu'on previent."""
    from engine.runner.operations.triggers.loki import barbed_ovipositor as B
    from engine.entities.selectors.accessors import Target
    from engine.entities.traits.unit_trait import UnitTrait
    from engine.entities.triggers import is_object_or_steppable

    attendu = is_object_or_steppable(Target())
    assert type(B._IS_OBJECT_OR_STEPPABLE) is type(attendu), (
        "`barbed_ovipositor._IS_OBJECT_OR_STEPPABLE` n'est plus un noeud produit par "
        "`entities/triggers.py::is_object_or_steppable` (type %r au lieu de %r)."
        % (type(B._IS_OBJECT_OR_STEPPABLE).__name__, type(attendu).__name__))
    # Ordre du decompile : Steppable a gauche, Object a droite.
    assert (B._IS_OBJECT_OR_STEPPABLE.a.trait, B._IS_OBJECT_OR_STEPPABLE.b.trait) == (
        int(UnitTrait.Steppable), int(UnitTrait.Object)), (
        "les operandes du OU ne sont plus `(27 Steppable, 13 Object)` : %r"
        % ((B._IS_OBJECT_OR_STEPPABLE.a.trait, B._IS_OBJECT_OR_STEPPABLE.b.trait),))
    assert int(UnitTrait.Decoy) not in (B._IS_OBJECT_OR_STEPPABLE.a.trait,
                                        B._IS_OBJECT_OR_STEPPABLE.b.trait), \
        "`Decoy` (1053) est apparu dans le foyer -- le natif ne nomme que 27 et 13."
    assert B._HAS_TRAIT_MECHANICAL.trait == int(UnitTrait.Mechanical), (
        "le conjoint voisin ne teste plus `HasTrait(target, 5 = Mechanical)` : %r"
        % (B._HAS_TRAIT_MECHANICAL.trait,))


def test_le_module_APPELLE_le_foyer_et_pas_un_equivalent_local():
    """Volet PROVENANCE de la garde ci-dessus -- et il existe parce que l'autre ne suffit PAS.

    Contre-epreuve mesuree : un mutant qui remplace `is_object_or_steppable(Target())` par
    `TriggerOr(HasTrait(Target(), 27), HasTrait(Target(), 13))` -- une recopie LOCALE strictement
    equivalente -- passe les 29 tests, y compris l'assertion de structure (meme type, memes
    litteraux). C'est normal : elle est comportementalement indistinguable AUJOURD'HUI. Le risque
    qu'elle porte est la DIVERGENCE FUTURE (c'est exactement ainsi que `master_of_the_tutelaries`
    en est venu a gater `Decoy`), et un critere de VALEUR ne peut pas la voir.

    On lit donc le SOURCE (AST, pas un grep : un appel dans un commentaire ne compte pas) et on
    exige un appel effectif a `is_object_or_steppable`."""
    import ast
    import inspect
    from engine.runner.operations.triggers.loki import barbed_ovipositor as B

    arbre = ast.parse(inspect.getsource(B))
    appels = {n.func.id for n in ast.walk(arbre)
              if isinstance(n, ast.Call) and isinstance(n.func, ast.Name)}
    assert "is_object_or_steppable" in appels, (
        "`barbed_ovipositor` n'APPELLE plus `entities/triggers.py::is_object_or_steppable` : le "
        "conjoint est recompose localement. Meme a l'identique, c'est la recopie que ce residu "
        "ferme -- appels de haut niveau trouves : %r" % (sorted(appels),))


def test_le_module_ne_porte_plus_de_recopie_de_traits():
    """Le symptome exact du defaut etait un couple de NOMS de traits fige dans le module, lu sur un
    substrat local. Sa disparition est ce qui garantit qu'aucune recopie ne repousse ici."""
    from engine.runner.operations.triggers.loki import barbed_ovipositor as B
    for attr in ("_OBJECT_OR_STEPPABLE", "_MECHANICAL"):
        assert not hasattr(B, attr), (
            "`%s` est revenu dans `barbed_ovipositor` : c'est la recopie manuelle que ce residu "
            "ferme. Les conjoints doivent passer par `entities/triggers.py`." % attr)


def test_le_substrat_diverge_bien_sur_un_cadavre():
    """LA MESURE qui justifie tout ce fichier, figee comme garde : sur une entite SANS
    `StatsComponent`, la lecture BRUTE s'effondre a `set()` alors que le foyer rend le kit.

    Si un jour `snapshot.load_state` posait un `StatsComponent` a tout le monde, ce test rougirait
    -- et ce serait la bonne nouvelle a instruire, pas un bruit a faire taire : la migration
    deviendrait alors vraiment cosmetique, et ce fichier devrait le dire."""
    import gameconfig as GC
    for vis in ("necroWarden", "genesSmnDecoy", "LootObj_Crate_Imp"):
        kit = set((GC.unit(vis) or {}).get("traits") or ())
        st = P._mk_state(vis, False)                     # regime CADAVRE
        brut = P._raw_traits(st, 2)
        foyer = P._dsl_traits(st, 1, 2)
        assert brut == set(), (
            "la lecture BRUTE rend %r sur un cadavre %r -- la mesure de ce residu est perimee."
            % (sorted(brut), vis))
        assert foyer >= kit, (
            "le substrat FOYER (%r) ne couvre pas le kit gameconfig (%r) de %r -- le repli #226 "
            "ne joue plus." % (sorted(foyer), sorted(kit), vis))
