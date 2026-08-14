"""#1015 -- la garde du RECENSEUR DE TRAITS qui a remplace le seuil de frequence.

CE QU'ELLE GARDE, ET CONTRE QUOI. `audit_kit_coverage` ecartait du compte tout trait porte par plus
de `TRAIT_COMMON_MAX = 12` unites, en les declarant « presumes couverts ». Un seuil n'est pas un
critere : il repond a « ce trait est-il FREQUENT ? » quand la question est « le port sait-il
l'EVALUER ? ». La mesure a tranche -- 3 des 22 traits ainsi ecartes ne sont lus NULLE PART.

CINQ ETAGES, et chacun garde une propriete que le seuil n'avait pas :

  1. EXHAUSTIVITE -- aucun trait porte n'est ecarte. C'est la propriete que le seuil detruisait.
  2. NON-VIDE DE CHAQUE CANAL DECLARE -- un canal qui se viderait rendrait les etages suivants vrais
     par vacuite (la faute exacte des trois rouges que #1015 volet 1 a repares).
  3. LE CANAL `lecture` APPORTE REELLEMENT -- sans lui le compte retombe a l'ancien. Sans cet etage,
     on pourrait retirer le balayage AST sans qu'aucune assertion ne tombe.
  4. PAS DE LISTE BLANCHE -- un conteneur de module INCONNU du recenseur sort quand meme, sous son
     propre nom. C'est la parade au vice repete du depot (`unit_map find --ability` lisait 2 voies
     sur 5 et a fait classer DEAD un effet vivant).
  5. LE CLIQUET DES NON COUVERTS -- la liste des 5 est FIGEE. Qu'un trait en sorte (il est porte) ou
     qu'un NOUVEAU y entre (regression), le test le DIT.

ASCII only.
"""
from __future__ import annotations

import ast
import sys
from collections import Counter
from pathlib import Path

HERE = Path(__file__).resolve()
PY = HERE.parents[1]
if str(PY) not in sys.path:
    sys.path.insert(0, str(PY))

import gameconfig as GC                                                   # noqa: E402
import trait_channels as TC                                               # noqa: E402
from engine.entities.traits.unit_trait import UnitTrait                   # noqa: E402

#: Ce qui doit faire REJOUER ce fichier. Le foyer (`trait_channels`) et son consommateur
#: (`audit_kit_coverage`) evidemment ; mais AUSSI les trois registres de trait et le mirror
#: `UnitTrait` -- une entree ajoutee a l'un d'eux change le canal d'un trait, et le cliquet des NON
#: COUVERTS doit alors etre reconsidere. `engine/**` entier serait le perimetre exact (le balayage
#: AST le lit en totalite) ; on declare les foyers qui le decident, pas les 622 fichiers qu'il lit.
DECLENCHEUR = {
    "chemins": (
        "scripts/python/trait_channels.py",
        # #1015-r1 -- l'etage 6 lit la table Ghidra VERSIONNEE par le foyer `build_pin`
        # (`functions_tsv()`), qui tire `il2cpp_provenance`. Nommes ici parce que `probe_486r15`
        # les voit dans la fermeture d'imports, et qu'un declencheur trop ETROIT est un faux vert.
        "scripts/python/build_pin.py",
        "scripts/python/il2cpp_provenance.py",
    ),
    "build": False,
    "toujours": True,
    "raison": (
        "`toujours: True`, et c'est un RESULTAT mesure, pas un aveu. Ce fichier garde un recenseur "
        "dont le perimetre est TOUT `engine/**` : `trait_channels._balayage()` lit les 622 fichiers "
        "du paquet par `rglob`, et une simple LECTURE (`UnitTrait.Healer` ajoute dans n'importe "
        "quel module) suffit a faire basculer un trait de NON COUVERT a COUVERT. Or `rglob` ne "
        "laisse AUCUNE trace dans la fermeture d'imports : `--proposer` ne voit qu'un seul chemin "
        "(`trait_channels.py`), et une declaration reduite a lui serait le FAUX VERT que ce garde "
        "existe pour attraper -- le port pourrait porter `Healer` sans que le cliquet des cinq "
        "non couverts ne se rejoue. Les trois registres de trait "
        "(`effects/factory.TRAIT_DERIVED_ABILITIES`/`TRAIT_OWNER_EFFECTS`, "
        "`triggers/dispatch/registry.TRAIT_TRIGGERS`) et le mirror `entities/traits/unit_trait.py` "
        "sont dans le meme cas, et ne sont pas listes ici pour cette raison : ils sont deja "
        "couverts par `toujours`. S'y ajoute le gameconfig, qui decide la POPULATION des 61 traits "
        "portes et n'est atteint par aucun import (il est lu depuis `data/`)."
    ),
}

#: Les traits SANS AUCUN canal, mesures au 2026-08-13 sur le build `rnca9r7q6c`. Ils portaient tous
#: une semantique de combat (gameconfig), donc AUCUN n'etait << sans objet >> -- residu #1015-r1.
#: UN PAR LIGNE, a dessein : les cinq partent en tranches SEPAREES (foyers disjoints), et un set sur
#: une seule ligne ferait de chaque retrait un conflit de merge avec les quatre autres.
#: `CloseCombatWeakness` RETIRE par #1015-r1 -- canaux MESURES : `derived`, `effet_homonyme`,
#: `registre:TRAIT_DERIVED_ABILITIES`, `registre:ABILITY_INIT_OWNER_EFFECTS`,
#: `registre:TRAIT_TRIGGERED_ABILITY_IDS`, `lecture`. Le trait derive l'ability 1130, qui pose l'effet
#: 1130 (-50 % melee / -25 % tir au contact d'un ennemi) et charge le playbook MOVE (-40 / ennemi adjacent).
#: `InstinctiveBehaviour` RETIRE par #1015-r1 (2026-08-14) -- canaux MESURES : `trigger`, `derived`,
#: `effet_homonyme`, `registre:TRAIT_TRIGGERS`, `registre:TRAIT_DERIVED_ABILITIES`,
#: `registre:ABILITY_INIT_OWNER_EFFECTS`, `lecture`. Le trait derive l'ability 1043
#: (`InstinctiveBehaviour_UpdateTargetAbility`, qui maintient le `ForcedAttackTargetsComponent` =
#: l'ennemi le plus proche a `NormalAttackRange + Movement`) et pose l'owner-effet 1235
#: (`InstinctiveBehaviour_BlockMovement`, 4e etage de `UnitExtensions$$CanMove`). Les DEUX faces
#: sont CONFRONTEES live (`probe_1015r1_instinctive_behaviour.py`, deux regimes + temoin non nul).
#: `Healer` RETIRE par #1015-r1 (2026-08-14) -- canal MESURE :
#: `registre:TRAIT_DERIVED_ACTIVE_ABILITIES` (`entities/active_abilities.py`). Le trait derive
#: l'ability ACTIVE `18 Heal` (dict `<Trait statics>+0x08` du `.cctor`, lu par
#: `Trait$$GetActiveAbility`, materialise par `UnitFactory$$AddDerivedAbilities`), que le decideur
#: offline ne voyait chez AUCUN des 18 porteurs. CONFRONTE live (temoin non nul : la MEME unite
#: sans / avec `Healer` greffe par `--unit-stat Traits`).
#: ⚠ LES DEUX RETRAITS SONT ARRIVES PAR DEUX BRANCHES PARALLELES, et la resolution d'un ENSEMBLE
#: est l'UNION des retraits -- jamais << la mienne >> ou << la sienne >>, qui perdrait un port reel.
#: `BeastSnagga` RETIRE par #1015-r1 (2026-08-14) -- canaux MESURES : `derived`, `effet_homonyme`,
#: `registre:TRAIT_DERIVED_ABILITIES`, `registre:ABILITY_INIT_OWNER_EFFECTS`, `lecture`. Le trait
#: (0x406 = 1030, seul porteur `tauNpcFarsight`) derive la `TriggeredAbilityType` 1084, dont le
#: `CreateBehaviour` pose DEUX effets sur son porteur : 1080 `BeastSnagga_ExtraDmg` (+20 % de degat
#: MELEE vs `BigTarget`/`Vehicle` -- corps decompile IDENTIQUE a celui de `BeastSlayer_ExtraDmg`) et
#: 1081 `BeastSnagga_ExtraBlock` (+10 % de chance de bloquer 20 % des PV MAX, `StatAmount(Health,
#: Maximum)` la ou son jumeau lit `FixedArmor`).
#: ⚠ TROIS branches paralleles ont retire un trait le MEME JOUR (`InstinctiveBehaviour` et `Healer`
#: par `origin/master`, `BeastSnagga` par celle-ci), et chaque rebase a resolu par UNION des
#: retraits -- jamais << le mien >> / << le sien >>, qui perdrait un port reel.
NON_COUVERTS_MESURES = {
    "TwoManTeam",
}

#: LE TROISIEME ETAT, et il manquait a ce fichier : un trait que le NATIF LUI-MEME n'evalue nulle
#: part. `NON_COUVERTS_MESURES` melangeait jusqu'ici « le port ne sait pas encore l'evaluer » (un
#: PORT A FAIRE) et « il n'y a rien a evaluer » (un VERDICT TERMINAL) -- et rien ne distinguait les
#: deux, donc le residu #1015-r1 restait ouvert sur le second sans que personne puisse le fermer.
#:
#: `TwoManTeam` (0x3fa = 1018, 4 npc + 2 summons, TOUS a `nrOfMembers == 2`) est mesure ainsi sur
#: `rnca9r7q6c`, par TROIS lectures independantes :
#:   (a) **0 symbole** dans les 154 177 fonctions de `ghidra/functions.tsv` -- c'est le cran
#:       EXECUTABLE ci-dessous, et le seul des trois qui soit offline ;
#:   (b) `0x3fa` n'est **cle d'AUCUN** des 8 conteneurs statiques de
#:       `idun.Idun.Source.Shared.Battle.StaticBattleRules.StaticBattleRules.Trait$$.cctor` (ni
#:       ability derivee, ni owner-effect, ni `HidesTrait`, ni `IsPlayerFacing`, ni
#:       `IsNotInheritedWhenCloned`) : il n'y apparait qu'en VALEUR de la cle `0x3ef`, ou il designe
#:       une `TriggeredAbilityType` 1018 -- autre enum, meme ordinal ;
#:   (c) ni `0x3fa` ni `1018` n'est argument d'un `HasTrait` : les 12 fonctions portant `0x3fa` et
#:       les 25 portant `1018` sont des flottants, de l'UI/meta, et les deux `.cctor` de (b).
#: Ce que le tooltip decrit (<< max 50 % des PV max d'un seul coup, hors Blast ; sous 50 %, plus
#: soignable au-dessus >>) EST porte -- mais keye sur `nrOfMembers`, pas sur le trait :
#: `services/trait_damage_limits.apply_group_unit_damage_limit` (cable par `_target_limits` sur la
#: voie ATTAQUE, par `normal_like` sur le degat DIRECT et par `transfer_damage`) et
#: `get_group_unit_heal_limit` (cable dans `operations/heal.py`, `operations/repair.py`,
#: `ai/action_generators.py`).
#:
#: ⚠ AUCUNE des trois mesures ne dit << ce trait est sans objet >> : il A une semantique de combat,
#: elle est simplement realisee par un AUTRE substrat. Retirer `TwoManTeam` de
#: `NON_COUVERTS_MESURES` demanderait au port de NOMMER un trait que le natif ne lit pas -- une
#: `lecture` fabriquee, c'est-a-dire le faux positif exact que `trait_channels` existe pour eviter.
SANS_ARTEFACT_NATIF = {
    "TwoManTeam",
}


def _traits_portes() -> Counter:
    """Les traits REELLEMENT portes, TOUS SEAUX -- `lineup`, `npc` et `summons`.

    Les trois seaux, parce que `units.*` n'en porte pas d'autre (mesure : les 23 cles de `units.*`
    balayees, et `gameconfig._index()` code les memes trois). Un trait porte par les seuls `npc` est
    un trait que le moteur doit evaluer en bataille au meme titre qu'un autre."""
    out: Counter = Counter()
    idx = GC._index()
    for seau in ("lineup", "npc", "summons"):
        for _uid, u in (idx[seau] or {}).items():
            for t in (u.get("traits") or []):
                out[t] += 1
    return out


# ================================================================================================
# 1. EXHAUSTIVITE -- la propriete que le seuil detruisait
# ================================================================================================

def test_la_partition_ne_perd_aucun_trait_porte():
    portes = _traits_portes()
    assert portes, "aucun trait porte : le recenseur ne visite rien, son verdict ne prouve rien"
    part = TC.partition(sorted(portes))
    assert set(part) == set(portes), (
        "la partition n'est pas EXHAUSTIVE -- ecartes : %r" % sorted(set(portes) - set(part)))
    # Et chaque entree porte un verdict TRANCHE, jamais un « on ne sait pas ».
    for t, (couvert, canaux, _n) in part.items():
        assert isinstance(couvert, bool)
        assert couvert == bool(canaux), (
            "%s : verdict %r incoherent avec ses canaux %r" % (t, couvert, canaux))


def test_tout_trait_porte_existe_dans_le_mirror():
    """Un trait du gameconfig absent du mirror serait invisible du balayage (il ne peut etre ecrit
    ni en `UnitTrait.X` ni comme nom connu), donc compte NON COUVERT pour une mauvaise raison."""
    manquants = sorted(set(_traits_portes()) - {m.name for m in UnitTrait})
    assert manquants == [], (
        "traits portes absents du mirror `UnitTrait` : %r -- le recenseur ne peut pas les voir, et "
        "les rendrait non couverts par CECITE et non par mesure." % manquants)


# ================================================================================================
# 2-3. LES CANAUX : non vides, et `lecture` apporte reellement
# ================================================================================================

def test_chaque_canal_declare_est_non_vide_et_lecture_apporte_l_essentiel():
    """L'ecart 29 -> 56 est la MESURE de ce que le predicat d'avant ne voyait pas."""
    portes = sorted(_traits_portes())
    par_canal: Counter = Counter()
    for t in portes:
        for c in TC.canaux(t):
            par_canal[c] += 1
    for canal in ("trigger", "derived", "owner_eff", "effet_homonyme", "lecture"):
        assert par_canal[canal] > 0, (
            "le canal `%s` est VIDE : les etages qui s'appuient dessus deviennent vrais par "
            "vacuite. C'est la forme exacte des trois rouges repares par le volet 1 de #1015."
            % canal)
    sans_lecture = {t for t in portes if set(TC.canaux(t)) - {"lecture"}
                    or any(c.startswith("registre:") for c in TC.canaux(t))}
    avec = {t for t in portes if TC.canaux(t)}
    assert len(avec) > len(sans_lecture), (
        "le canal `lecture` n'apporte AUCUN trait que les registres ne portaient deja (%d vs %d) : "
        "le balayage AST pourrait etre retire sans qu'aucune assertion ne tombe."
        % (len(avec), len(sans_lecture)))


def test_le_module_de_DECLARATION_ne_compte_pas_comme_une_lecture():
    """`unit_trait.py` DECLARE le mirror : ce qu'on y lit n'est pas le moteur qui evalue un trait,
    c'est le mirror qui se definit. Compter ces mentions ferait rendre « couvert » sur la seule foi
    de l'existence du membre.

    ⚠ CE TEST A D'ABORD ETE ECRIT AVEUGLE, ET LA CONTRE-EPREUVE L'A MONTRE. Il assertionnait
    `sites(t) == []` sur les cinq traits NON COUVERTS -- or aucune des mentions du fichier de
    declaration ne les concerne, donc desarmer l'exclusion `_DECLARATION` le laissait VERT. Une
    garde qui ne peut pas rougir sur la faute qu'elle nomme est un faux vert. Il mesure desormais
    le fichier LUI-MEME, et assertionne son propre non-vide : s'il cessait d'y avoir des mentions a
    exclure, l'exclusion serait devenue inutile et le test le DIRAIT au lieu de passer."""
    decl = PY / TC._DECLARATION
    v = TC._Visiteur(TC._DECLARATION, TC._noms_de_traits())
    v.visit(ast.parse(decl.read_text(encoding="utf-8")))
    concernes = {t for t, _c, _l in v.trouves}
    assert concernes, (
        "le fichier de declaration ne porte AUCUNE mention de nom de trait : l'exclusion "
        "`_DECLARATION` ne retire plus rien. Ce n'est pas un vert -- verifier si le mirror a change "
        "de forme, et retirer l'exclusion devenue inerte plutot que de la garder par superstition.")
    balayage = TC._balayage()
    for t in sorted(concernes):
        depuis_decl = [s for s in balayage.get(t, ()) if s[1] == TC._DECLARATION]
        assert depuis_decl == [], (
            "%s est compte depuis le fichier de DECLARATION (%r) : le recenseur confond « le mirror "
            "nomme ce trait » avec « le moteur l'evalue »." % (t, depuis_decl[:2]))


# ================================================================================================
# 4. PAS DE LISTE BLANCHE -- un conteneur INCONNU sort sous son nom
# ================================================================================================

def test_un_conteneur_inconnu_du_recenseur_sort_sous_son_propre_nom(tmp_path):
    """LA PARADE AU VICE REPETE DU DEPOT, exercee pour de vrai.

    On ne verifie pas que le recenseur connait les bons registres -- on verifie qu'il n'a pas
    besoin de les connaitre. Un module qui declarerait demain `MON_REGISTRE_NEUF = {"Healer": ...}`
    doit faire sortir `Healer` sous `registre:MON_REGISTRE_NEUF`, sans qu'une ligne soit ajoutee a
    `trait_channels`. On l'exerce sur le VISITEUR, qui est le foyer de la derivation."""
    src = (
        "MON_REGISTRE_NEUF = {\n"
        "    'Healer': 1,\n"
        "    'TwoManTeam': 2,\n"
        "}\n"
        "def f(u):\n"
        "    return UnitTrait.BeastSnagga in u\n"
    )
    v = TC._Visiteur("faux/module.py", TC._noms_de_traits())
    v.visit(ast.parse(src))
    par_trait = {t: c for t, c, _l in v.trouves}
    assert par_trait.get("Healer") == "registre:MON_REGISTRE_NEUF", (
        "un conteneur INCONNU n'est pas nomme : %r. Le recenseur serait redevenu une liste "
        "blanche, et un registre neuf lui serait invisible." % par_trait)
    assert par_trait.get("TwoManTeam") == "registre:MON_REGISTRE_NEUF"
    # ... et hors conteneur, la mention reste une `lecture` : les deux roles se distinguent.
    assert par_trait.get("BeastSnagga") == "lecture", (
        "une mention hors conteneur doit sortir en `lecture`, rendu %r" % par_trait.get("BeastSnagga"))


# ================================================================================================
# 5. LE CLIQUET
# ================================================================================================

def test_les_traits_non_couverts_sont_exactement_ceux_mesures():
    """FIGE dans les DEUX sens (residu #1015-r1).

    Un trait qui SORT de la liste est une bonne nouvelle -- mais elle doit etre CONSTATEE, pas subie :
    le residu se ferme, et la ligne de backlog avec. Un trait qui ENTRE est une regression : le port
    a perdu la seule evaluation qu'il avait. Les deux se lisent dans le meme message."""
    portes = _traits_portes()
    muets = {t for t in portes if not TC.canaux(t)}
    assert muets, (
        "PLUS AUCUN trait non couvert : ce n'est pas un vert automatique. Soit le residu #1015-r1 "
        "est ferme (alors retire ce test et sa ligne de backlog), soit le recenseur a cesse de "
        "pouvoir rendre `[]` -- ce qui le rendrait incapable de mesurer quoi que ce soit.")
    entres = sorted(muets - NON_COUVERTS_MESURES)
    sortis = sorted(NON_COUVERTS_MESURES - muets)
    assert not entres, (
        "REGRESSION -- trait(s) devenu(s) non couvert(s) : %r. Le port a perdu la seule evaluation "
        "qu'il en avait ; porteurs : %s"
        % (entres, {t: portes[t] for t in entres}))
    assert not sortis, (
        "trait(s) desormais COUVERT(s) : %r -- bonne nouvelle a ENTERINER. Retire-les de "
        "`NON_COUVERTS_MESURES` et mets a jour la ligne #1015-r1 du backlog, dans le meme commit. "
        "Canaux : %s" % (sortis, {t: TC.canaux(t) for t in sortis}))


# ================================================================================================
# 6. LE TROISIEME ETAT -- « le natif ne l'evalue nulle part » n'est PAS « le port ne sait pas »
# ================================================================================================

def test_les_traits_sans_artefact_natif_n_en_ont_toujours_aucun():
    """Le cran EXECUTABLE du verdict TERMINAL (#1015-r1).

    Un trait de `SANS_ARTEFACT_NATIF` ne porte AUCUNE fonction a son nom dans la table Ghidra du
    build QUI FAIT FOI (`data/symbols/<build>/ghidra/functions.tsv`, VERSIONNEE -- donc mesurable
    depuis n'importe quel worktree, sans ghidra ni session). Le jour ou le jeu ajoute un
    `TwoManTeamAbility` ou un `TwoManTeam_...Effect`, ce test ROUGIT : le verdict << rien a evaluer >>
    est repute PERIME et se re-instruit, au lieu de rester vrai par habitude.

    ⚠ CE QUE CE CRAN NE PROUVE PAS, et il faut le lire avec (b) et (c) du commentaire de
    `SANS_ARTEFACT_NATIF` : l'absence de symbole HOMONYME n'implique pas l'absence de LECTURE (un
    id de trait peut etre lu par `HasTrait` sans qu'aucune classe ne porte son nom -- c'est
    exactement le cas de `Diminutive`, qui passe par le dict trait -> ability derivee). C'est un
    cran de PEREMPTION, pas une demonstration : celle-ci vit dans le decompile, et elle est citee.

    ⚠ ET IL S'ASSERTIONNE CONTRE SA PROPRE VACUITE. Un chemin de table casse ferait rendre `0` a
    TOUT LE MONDE, donc le test passerait pour de mauvaises raisons -- le meme vice que le
    `set()` vide de #270-r1-r1-r3. Le contre-temoin est `BeastSnagga`, dont le port a MESURE les
    4 symboles (`BeastSnaggaAbility$$CreateTrigger/$$CreateBehaviour`,
    `BeastSnagga_ExtraDmgEffect$$.ctor/$$CreateDamageModifier`) : s'il rend 0, c'est la LECTURE qui
    est cassee, pas le build."""
    import build_pin                                                      # noqa: E402
    tsv = build_pin.functions_tsv().read_text(encoding="utf-8", errors="replace")
    assert SANS_ARTEFACT_NATIF, (
        "`SANS_ARTEFACT_NATIF` est VIDE : ce test ne mesure plus rien. Si le dernier trait en est "
        "sorti, retire-le AVEC son test plutot que de laisser une garde inerte.")
    assert SANS_ARTEFACT_NATIF <= NON_COUVERTS_MESURES, (
        "incoherence : %r a un artefact natif absent ET ne figure pas dans les non couverts."
        % sorted(SANS_ARTEFACT_NATIF - NON_COUVERTS_MESURES))
    # CONTRE-TEMOIN : la lecture SAIT trouver des symboles quand il y en a.
    assert tsv.count("BeastSnagga") >= 4, (
        "la table `%s` ne rend que %d occurrence(s) de `BeastSnagga`, la ou le port en a MESURE 4. "
        "La lecture est cassee (chemin, encodage, build) -- les zeros ci-dessous ne prouveraient "
        "alors RIEN." % (build_pin.functions_tsv().as_posix(), tsv.count("BeastSnagga")))
    for trait in sorted(SANS_ARTEFACT_NATIF):
        n = tsv.count(trait)
        assert n == 0, (
            "%s porte desormais %d symbole(s) natif(s) : le verdict << le natif ne l'evalue nulle "
            "part >> est PERIME. Re-instruire les trois lectures (symboles, cles du "
            "`StaticBattleRules.Trait$$.cctor`, arguments de `HasTrait`) avant de le reconduire."
            % (trait, n))
