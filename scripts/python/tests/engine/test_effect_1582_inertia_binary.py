"""GARDE #364 (OFFLINE PURE) -- `1582 MyWillBeDoneOverlord_FriendlyAttackedMarker` est INERTE.

CE QU'ELLE PROTEGE. L'`EffectType` 1582 est DECLARE par l'enum du jeu, mais le natif ne peut rien
en construire : `IdunBattle.Core.Services.EffectsDatabase$$InitializeEffects` ne lui associe AUCUNE
fabrique, et aucune instruction du segment de code ne charge sa valeur. Il n'y a donc rien a porter
-- et un port serait speculatif. Cette garde fige le constat : si un futur build lui donne une
fabrique, ou si du code se met a le poser, elle rougit, et c'est le signal qu'il faut le PORTER.

CE QUE « INERTE » VEUT DIRE, EXACTEMENT. Ce n'est pas « impossible a poser » : lu dans
`IdunBattle.Core.Services.EffectsDatabase$$GetEffect`, un `EffectType` sans fabrique ne leve pas --
le `TryGetValue` sur le dictionnaire de fabriques rate, le natif formate `System.Enum$$ToString` de
la cle dans un log, et rend un `IdunBattle.Entities.Effects.NoneEffect`. La degradation native est
donc DEFINIE et silencieuse cote gameplay. « Inerte » = « meme pose, il ne ferait rien ».

POURQUOI ELLE MESURE AUSSI LA FERMETURE DE L'INVENTAIRE (le coeur du cas). Un « 1582 est absent »
ne vaut RIEN si le balayage qui l'a produit est partiel -- et c'est exactement ce qui s'etait
passe : le balayage de #358 ne voyait que 511 des 607 enregistrements, parce que ses deux motifs
d'octets partageaient la meme cle `mov r8, rsi`. Leur accord (511 == 511) etait un accord sur la
meme cecite, et il faisait rendre « NON ENREGISTRE » pour 96 effets bien vivants (`5 Fire`,
`17 Ice`, `31 StatModifier`, `1004 MightOfHeroes_ExtraHits`, `1099 Waaagh_ExtraMovement`...).
`test_registry_inventory_is_closed` est donc la garde de la garde : elle exige que TOUS les appels
d'ajout aient une cle resolue et que le total se referme sur une source INDEPENDANTE -- le nombre
de fabriques `<>9__14_N` presentes en binaire.

Et `test_living_neighbours_are_registered` est l'anti-zero-menteur : si le recensement se cassait
et rendait un dictionnaire vide, les assertions d'absence passeraient a tort. Les deux voisins
VIVANTS de 1582 (1581, deja porte et confronte live ; 1583) doivent rester enregistres.

LES TROIS VOIES DE POSE, chacune fermee par un test :
  * une FABRIQUE dans `EffectsDatabase`          -> `test_1582_has_no_factory`
  * un IMMEDIAT dans le code (32 ET 16 bits)     -> `test_1582_is_loaded_by_no_game_code`
  * un TABLEAU statique en donnees               -> `test_1582_data_presence_is_not_discriminant`

Build-agnostique : aucune VA ni aucun compte en dur -- tout part de `data/symbols/CURRENT`, de la
table VERSIONNEE de ce build, et du PE du build correspondant.
Mesure detaillee : `scripts/python/probe_364_effect_1582_registration.py`.
ASCII only.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

import probe_364_effect_1582_registration as P  # noqa: E402

ROOT = Path(__file__).resolve().parents[4]

INERT = 1582                 # MyWillBeDoneOverlord_FriendlyAttackedMarker
LIVING_NEIGHBOURS = (1581,   # MyWillBeDoneOverlord_ExtraDamage -- porte, confronte live (#358)
                     1583)   # Helspear_IgnoreArmor -- Helspear_IgnoreArmorEffect$$.ctor


@pytest.fixture(scope="module")
def binary():
    """LE MONTAGE, nomme et partage : (buffer PE, sections, table de symboles, hash du build).

    Le `GameAssembly.dll` est une entree gitignoree qui vit hors du depot : absente, on le DIT.
    Un skip muet ici serait un vert qui ment (cf. `feedback_red_test_may_accuse_the_montage`)."""
    cur = ROOT / "data" / "symbols" / "CURRENT"
    if not cur.exists():
        pytest.skip("data/symbols/CURRENT absent -- build indetermine, rien n'est mesure")
    bhash = cur.read_text(encoding="utf-8").strip()
    dll = P.dll_path(bhash)
    if not dll.exists():
        pytest.skip("GameAssembly.dll absent pour le build %s (entree hors depot) -- NON MESURE, "
                    "pas un zero" % bhash)
    tsv = ROOT / "data" / "symbols" / bhash / "ghidra" / "functions.tsv"
    if not tsv.exists():
        pytest.skip("table de symboles absente pour le build %s" % bhash)
    buf = dll.read_bytes()
    return buf, P.sections(buf), P.functions(bhash), bhash


@pytest.fixture(scope="module")
def inventory(binary):
    """Le recensement COMPLET de `InitializeEffects` : `({effectType: N}, non_resolus, total)`."""
    buf, secs, rows, _bhash = binary
    return P.registry(buf, secs, rows)


@pytest.fixture(scope="module")
def members(binary):
    """`IdunBattle.Entities.Enum.EffectType` du build courant -- foyer UNIQUE (`P.enum_members`).

    Le lire ici plutot que de le re-transcrire garantit que la garde et le probe parlent du MEME
    identifiant : ce build a deja renumerote deux membres en silence (1563/1564, #318), et une
    chasse menee sur le mauvais identifiant rendrait un « absent » parfaitement faux."""
    _buf, _secs, _rows, bhash = binary
    return P.enum_members(bhash)


def test_registry_inventory_is_closed(binary, inventory):
    """LA GARDE DE LA GARDE : chaque appel d'ajout a une cle resolue, et le total se referme.

    Sans elle, une absence ne prouve rien -- un balayage partiel rend une absence pour tout ce
    qu'il ne voit pas. C'est la faute EXACTE que #364 a trouvee dans #358 (511 vus sur 607)."""
    _buf, _secs, rows, _bhash = binary
    by_effect, unresolved, total = inventory
    assert unresolved == 0, (
        "%d appel(s) d'ajout sur %d n'ont PAS de cle resolue : l'inventaire est INCOMPLET, donc "
        "aucune absence ne peut en etre deduite. Un encodage d'enregistrement a change -- RE-LIRE "
        "`InitializeEffects` avant de toucher a quoi que ce soit." % (unresolved, total))
    assert len(by_effect) == total, (
        "%d effectType distincts pour %d appels d'ajout : un effectType serait enregistre deux "
        "fois, ce que la loi off = 8*(N+1) exclut" % (len(by_effect), total))
    idx = [n for n in by_effect.values() if n is not None]
    assert len(idx) == total, (
        "%d appels d'ajout mais %d indices `<>9__14_N` retrouves : le store du delegate n'est plus "
        "adjacent a son Add, la loi de #358 ne tient plus" % (total, len(idx)))
    assert len(set(idx)) == total, (
        "les indices `<>9__14_N` ne sont pas distincts (%d uniques pour %d) : deux effectType "
        "partageraient la meme fabrique" % (len(set(idx)), total))

    # LA contrainte qui casse sous un balayage partiel. Compter « enregistres + orphelins ==
    # membres » ne prouverait RIEN : les orphelins etant DERIVES des enregistres, l'egalite est
    # vraie par construction, y compris avec 96 sites manquants. Le compte des fabriques, lui, est
    # une source INDEPENDANTE : chaque `<>9__14_N` du binaire doit etre enregistree.
    lambdas = {name for _a, name in rows if name.startswith(P.LAMBDA_PREFIX)}
    assert total == len(lambdas), (
        "%d appel(s) d'ajout pour %d fabrique(s) `<>9__14_N` presentes dans le binaire : le "
        "balayage en RATE %d. Toute absence qu'il rapporte est sans valeur -- c'est la faute exacte "
        "que #364 a trouvee dans #358 (511 vus sur 607)."
        % (total, len(lambdas), len(lambdas) - total))


def test_registered_keys_are_all_enum_members(inventory, members):
    """Contre-controle de TYPAGE : toute cle enregistree est un membre declare de l'enum.

    Si le suivi de flot se mettait a lire le mauvais operande (une taille de struct, un
    `MethodInfo*` tronque), il rendrait des cles arbitraires -- et un `1582 absent` tire d'un
    inventaire de valeurs arbitraires ne voudrait rien dire. Ce test est ce qui rattache le
    recensement a l'enum."""
    by_effect, _unresolved, _total = inventory
    alien = sorted(set(by_effect) - set(members))
    assert not alien, (
        "%d cle(s) enregistree(s) ne sont PAS des membres de `IdunBattle.Entities.Enum.EffectType` "
        ": %s -- le suivi de flot lit un mauvais operande, l'inventaire n'est pas interpretable"
        % (len(alien), alien[:10]))


def test_living_neighbours_are_registered(inventory):
    """ANTI-ZERO-MENTEUR : si le recensement se cassait, les assertions d'absence passeraient.

    1581 est porte ET confronte live (`entities/effects/loki/my_will_be_done_overlord.py`) ; 1583
    a sa propre classe native. Les deux doivent rester enregistres."""
    by_effect, _unresolved, _total = inventory
    for eff in LIVING_NEIGHBOURS:
        assert eff in by_effect, (
            "effectType %d n'est plus enregistre dans EffectsDatabase : ce n'est pas 1582 qui a "
            "change, c'est le RECENSEMENT qui est casse -- les constats d'absence de ce fichier "
            "sont sans valeur tant que ce test est rouge" % eff)


def test_1582_has_no_factory(inventory, members):
    """VOIE 1 -- 1582 n'est associe a AUCUNE fabrique : le natif ne peut pas le construire."""
    by_effect, _unresolved, total = inventory
    assert INERT in members, (
        "l'effectType %d n'est plus declare par l'enum de ce build -- le sujet de cette garde a "
        "disparu (renumerotation silencieuse ?), relire le cas avant de la supprimer" % INERT)
    assert members[INERT] == "MyWillBeDoneOverlord_FriendlyAttackedMarker", (
        "l'effectType %d ne designe plus `MyWillBeDoneOverlord_FriendlyAttackedMarker` mais `%s` : "
        "l'enum a ete RENUMEROTE (cf. #318, 1563/1564). Toute conclusion de ce fichier porte sur "
        "l'ancien identifiant et doit etre re-derivee." % (INERT, members[INERT]))
    assert INERT not in by_effect, (
        "effectType %d (%s) est DESORMAIS enregistre dans EffectsDatabase (fabrique <>9__14_%s, sur "
        "%d enregistrements) : il n'est plus inerte. Le porter -- `probe_364 --effect %d` donne sa "
        "fabrique et ses arguments." % (INERT, members.get(INERT), by_effect.get(INERT), total,
                                        INERT))


def test_1582_is_loaded_by_no_game_code(binary):
    """VOIE 2 -- personne ne POSE 1582 : aucune fonction `IdunBattle` ne charge sa valeur.

    Une absence de fabrique laisserait encore ouverte l'hypothese « il est pose ailleurs et se
    perd ». Le balayage du segment de code la ferme, sur les DEUX encodages d'immediat (32 bits, le
    cas normal d'un enum int32 ; 16 bits, prefixe 0x66) -- n'en verifier qu'un laisserait une porte
    ouverte. Les seules occurrences sont des coincidences numeriques hors du jeu (une table de
    localisation arabe, un calendrier hebraique)."""
    buf, secs, rows, _bhash = binary
    for width in (4, 2):
        owners = P.code_immediate_owners(buf, secs, rows, INERT, width=width)
        game = {o: v for o, v in owners.items() if o.startswith("IdunBattle")}
        assert not game, (
            "l'immediat %d est charge sur %d bits par du code IdunBattle : %s -- 1582 est POSE par "
            "le jeu, il n'est plus inerte et doit etre porte"
            % (INERT, width * 8, {k: v[:2] for k, v in game.items()}))


def test_1582_data_presence_is_not_discriminant(binary):
    """VOIE 3 -- le dernier chemin credible : un tableau d'`EffectType` initialise en DONNEES.

    Un `RuntimeHelpers.InitializeArray` depuis `.rdata` poserait un effectType SANS aucun immediat
    en code, donc invisible de la voie 2. Le test ne peut pas exiger « 0 occurrence » (1582 est un
    entier banal, on en mesure des dizaines) : il exige que la presence de 1582 en donnees soit du
    MEME ordre que celle de ses voisins ENREGISTRES 1581/1583. Si les trois se ressemblent, ces
    octets sont de la metadonnee IL2CPP -- mesure : des triplets de 12 octets
    `(index, valeur, 0xFFFFFFFF)` ou 1581, 1582 et 1583 figurent au meme titre -- et la voie
    DONNEES ne distingue rien.

    Ce qui rendrait ce test ROUGE : 1582 devenant un pic isole en donnees, tres au-dessus de
    voisins vivants -- signature d'un vrai tableau statique a aller lire."""
    buf, secs, rows, _bhash = binary
    counts = {e: P.data_occurrences(buf, secs, rows, e)
              for e in (INERT,) + LIVING_NEIGHBOURS}
    living = max(counts[e] for e in LIVING_NEIGHBOURS)
    assert counts[INERT] <= 4 * max(living, 1), (
        "1582 apparait %d fois dans les sections de DONNEES contre au plus %d pour ses voisins "
        "VIVANTS %s : ce n'est plus le bruit de metadonnee mesure en #364, c'est le profil d'un "
        "tableau statique. Aller le lire avant de conclure quoi que ce soit -- comptes complets : %s"
        % (counts[INERT], living, list(LIVING_NEIGHBOURS), counts))


def test_1582_belongs_to_the_orphan_cohort(inventory, members):
    """CONTEXTE DE POPULATION : 1582 n'est pas une singularite, il rejoint une cohorte connue.

    Le binaire declare des membres d'enum sans fabrique par DESIGN -- des sentinelles (`None`,
    `STRIPPED`), des emplacements explicitement morts (`UNUSED_*`, `NotUsed`, `Unused`), des
    mocks de test, et des reliquats de mecaniques retirees. Lire l'absence de 1582 hors de ce
    contexte inviterait a la prendre pour une anomalie a corriger ; elle est un regime NORMAL du
    binaire. Le test verifie que la cohorte existe toujours et que 1582 en fait partie -- si elle
    se vidait, c'est le RECENSEMENT qu'il faudrait suspecter, pas le jeu."""
    by_effect, _unresolved, _total = inventory
    orphans = P.unregistered_members(by_effect, members)
    assert INERT in orphans, (
        "1582 n'est plus dans la cohorte des membres sans fabrique -- il a une fabrique, "
        "cf. `test_1582_has_no_factory`")
    named_dead = [o for o in orphans
                  if any(t in members[o].lower() for t in ("unused", "notused", "not_used",
                                                           "stripped", "test_", "none"))]
    assert len(named_dead) >= 5, (
        "seulement %d membre(s) explicitement mort(s) par le NOM dans une cohorte de %d orphelins "
        "(%s) : la cohorte attendue a disparu, c'est le recensement qu'il faut suspecter avant "
        "d'interpreter l'absence de 1582"
        % (len(named_dead), len(orphans), [members[o] for o in orphans[:8]]))
