"""CLIQUET de la tranche ENGINE `combat.py` -- #489-r1, #889-r2, #1030-r4, #512-r3.

Quatre residus du meme foyer, tranches le 2026-08-15 par lecture du decompile du build courant
(`t6dpr4k06g`). **DEUX de leurs premisses sont FAUSSES et deux sont PERIMEES** ; ce fichier fige
les quatre lectures, pour que personne ne les rouvre a tort ni ne les << repare >> a l'envers.

ETAGE 1 -- #489-r1 (a). LE BLOQUANT DECLARE N'EXISTAIT PLUS, MAIS LA LOI RESISTE (`#489-r2`).
  La fiche annonce « la loi `(H-k) - (1 si overkill) + extraHits` reproduit 6 regimes sur 6 » et
  « bloquant : le retour d'`execute_ability_attack` n'expose AUCUN flag d'overkill ». Le second
  point est PERIME (l'etage `IsOverkill` est porte depuis #462-r4e-o-r1 ; seul le CABLAGE
  manquait, et cette tranche le pose). Le premier est FAUX : cette forme rend `2` la ou #505
  mesure `3` sur `1129 BloodyFury`.
  ⚠ ET LE CORRECTIF QUE LA LECTURE SEMBLE DICTER EST REFUTE LUI AUSSI. Le gate du call-site (a)
  d'`IdunBattle.Operations.ApplyDamageOperation$$AddLeftoverHit` -- le SEUL des trois a pousser un
  flag LITTERAL `1`, donc le seul que `GetLeftOverHits` compte -- est
  `UnitExtensions.HasFlag(target, UnitFlag.Overkilled = 8)`, **PAS** `IsDead` : le compte se lit
  sur l'index d'OVERKILL. Mais `max(0, H-k)`, la forme qui en decoule quand on suppose
  `o = k`, rend `test_523_heavy_warp_flamer_live.py` TROIS fois rouge (dont un MAILLON ENTIER en
  trop : offline `[79, 83, 81]` contre live `[79, 83]`) et `test_chain_leftover_hits_live.py` DEUX
  fois, la ou `master` est vert 13/13. La loi portee reste donc celle de `master`, et les etages
  ci-dessous FIGENT a la fois ce qu'elle vaut et ce qu'on sait de sa faute.

ETAGE 2 -- #489-r1 (a), le BLOQUANT declare. La fiche dit « le retour d'`execute_ability_attack`
  n'expose AUCUN flag d'overkill ». L'ETAGE existait (`overkill_flag_posted_by_hit`, mirror
  d'`IdunBattle.Core.Services.DamagePrediction$$IsOverkill`, porte par #462-r4e-o-r1) ; seul le
  CABLAGE manquait. L'etage 2 garde que `_run_hits` rend `overkilled` / `overkill_at_hit` /
  `hits_executed` ET que `execute_ability_attack` les REMONTE.

ETAGE 3 -- #889-r2. LE CHAMP `+0x08` DES `AttackDamageBehaviourOptions` EST RESOLU.
  La fiche (MAJ #986, 2026-08-12) dit « SEMANTIQUE toujours NON lue : aucun LECTEUR de
  `options+0x40` sur le chemin `ExecuteHit` ». Le constat est exact et la conclusion ne l'est pas :
  le lecteur vit un etage AU-DESSUS, dans `IdunBattle.Operations.AttackDamageOperation$$ExecuteHits`
  (pluriel), en fin de chaque coup NON CRITIQUE --

      hitGroup.<+0x3c isCriticalDamageAllowed> =
          options[+0x40] != null && options[+0x40].Any(hitIndex => hitIndex == i + 1)

  le predicat etant le corps ENTIER de `IdunBattle.Operations.AttackDamageOperation.
  u003Cu003Ec__DisplayClass4_0$$u003CExecuteHitsu003Eb__0` : `return hitIndex == this.<+0x10> + 1;`.
  `i` est remis a 0 en tete de chaque `ExecuteHits` -> la liste porte des numeros de coup 1-BASED.
  ⚠ La sous-partie « le crit s'eteint au premier coup non-critique » etait, elle, DEJA portee et
  documentee depuis le 2026-08-01 (`b761ab26`, #366-r1-crit-multihit) -- soit ONZE JOURS avant la
  MAJ qui declare la semantique non lue.

ETAGE 4 -- #1030-r4. LA PREMISSE EST FAUSSE, ET LA REPARER AURAIT CASSE LE PORT.
  La fiche dit : « `AttackWithAbilityDamage` ne thread PAS le `pierce_effect_bonus` des effets du
  caster, la ou son jumeau `AttackWithAttackDamage` le fait ». C'est exact, et c'est FIDELE :
  `IdunBattle.Core.Services.DamagePrediction$$CalculateAbilityDamage` passe a
  `$$CalculateBaseDamageWithAllModifiers` un `attackModifiers` **memset a 0** (`local_498..
  uStack_460 = 0` juste avant l'appel), et ce dernier lit `additionalPiercing =
  attackModifiers.HasValue ? attackModifiers.Value.<+0x20> : Fix64.Zero` avant de le passer a
  `$$GetBaseDamageWithFixedPiercedArmor`. La famille ABILITY n'a donc AUCUN terme de percage venant
  des effets du caster. Le vrai manque etait CHEZ LE VOISIN : `ChainLeftOverHitsAttackDamage`, qui
  route la famille ATTACK pour ses trois porteurs (1006/1048/1129), ne le threadait pas non plus.

ETAGE 5 -- #512-r3. LA PREMISSE EST FAUSSE : `On(Attack = 9)` **EST** EMIS PAR LA VOIE ABILITY.
  La fiche dit « `On(Attack = 9)` n'est emis par AUCUNE ability cote port -- seulement par
  l'attaque NORMALE ». Ce qui est vrai est que la FONCTION `finish_attack_triggers` n'a qu'un
  call-site (`damage_ops/normal.py`) ; l'EVENEMENT, lui, part aussi de `after_hit_ability_attack`
  (`dispatch/attack.py`), appele par `damage_ops/ability.py` a chaque attaque d'ability. Confondre
  le nom de la fonction et l'evenement aurait fait ajouter un SECOND emetteur, donc DOUBLER `On(9)`
  sur les 37 consommateurs recenses (`probe_437_on9_blast_radius.py`) -- l'inverse exact du but.

100 % OFFLINE : aucun runner, aucun RPC. Les etages 1/2/3 EXECUTENT le moteur (`_run_hits` est un
`staticmethod` sans `State`) ; les etages 4/5 lisent l'ARBRE SYNTAXIQUE des foyers, parce que ce
qu'ils gardent est un CABLAGE (qui appelle quoi), pas une valeur.
ASCII only.
"""
from __future__ import annotations

import ast
import inspect
import pathlib

import pytest

#: Le foyer UNIQUE de « quel MODULE ce nom local designe-t-il A CET ENDROIT » (#485-r2). Une
#: seconde implementation de ce predicat divergerait de la premiere (lecon #332) : le helper
#: `_appelle` ci-dessous s'y branche au lieu de re-deviner la resolution de portee.
import migrate_485r1_barils_reexport as MIG

from engine.runner.abilities.behaviours.combat import (AttackWithAbilityDamage,
                                                       AttackWithAttackDamage,
                                                       ChainLeftOverHitsAttackDamage)
from engine.runner.operations.damage import AttackDamageOperation
from engine.runner.operations.damage_hits import HitDamage
from engine.runner.prng import IntBasedMersenneTwister


#: Ce qui doit changer pour que ce FICHIER puisse changer de verdict (#486-r15).
DECLENCHEUR = {
    # Les cinq etages lisent leur propre fermeture d'imports (`combat.py`, `damage_hits.py`,
    # `damage_ops/ability.py`, `left_over_damage.py`, `dispatch/attack.py`) PLUS deux fichiers
    # de CABLAGE que rien n'importe ici -- les deux phases de `1217`, dont l'etage 3 verifie
    # qu'elles posent la liste. Ceux-la sont nommes, parce qu'ils ne sont PAS derivables.
    "chemins": (
        "scripts/python/engine/runner/abilities/darkangels.py",
        "scripts/python/engine/runner/operations/triggers/loki/lions_wrath_attack.py",
    ),
    # FAUX : rien ici ne lit le gameconfig ni la table de symboles. Les seules valeurs natives
    # citees (offsets, predicat du lambda) sont FIGEES dans les assertions, pas re-derivees.
    "build": False,
    "toujours": False,
    "raison": (
        "Ce fichier garde CINQ lectures du decompile, dont deux qui refutent la fiche de leur "
        "propre residu. Sans lui, un relecteur qui prend #1030-r4 au mot ajouterait le "
        "pierce_effect_bonus a la famille ABILITY (que le natif zeroise), et un relecteur qui "
        "prend #512-r3 au mot ajouterait un second emetteur d'On(9) sur la voie ability (qui en "
        "emet deja un). Les deux fautes sont PERMISSIVES, donc invisibles en self-play."
    ),
}


# ==================================================================================================
# ETAGE 1 -- la loi de `GetLeftOverHits` == le cardinal des entrees flag-vrai
# ==================================================================================================

def _report(H, k, extra, ovk_at=None, overkilled=None):
    """La loi portee, sur une serie de `H` coups a 1 PV et une cible a `k` PV (donc coup fatal au
    rang `k` 1-based). `ovk_at` = index 0-BASED du coup qui pose `UnitFlag.Overkilled`."""
    atk = {"per_hit_health": [1] * H, "hp_before": k,
           "overkill_at_hit": ovk_at,
           "overkilled": (overkilled if overkilled is not None else ovk_at is not None)}
    return ChainLeftOverHitsAttackDamage._left_over_hits(atk, extra)


@pytest.mark.parametrize("extra", [0, 1])
def test_etage1_la_loi_LIVE_VALIDEE_est_tenue(extra):
    """Balayage EXHAUSTIF de (H, k) de la loi effectivement portee -- celle que `master` valide
    LIVE sur `1006` (`test_chain_leftover_hits_live.py`, seeds 4242 et 777) et sur `1194`
    (`test_523_heavy_warp_flamer_live.py`, R2 et R3). Ce n'est pas la loi NATIVE (cf. l'etage 1bis
    et le residu `#489-r2`), c'est la loi CONFRONTEE : la changer exige de rejouer ces deux
    fichiers, et de mesurer AVANT."""
    vus = 0
    for H in range(1, 8):
        for k in range(1, H + 2):
            attendu = 0 if k > H else max(0, H - k - 1) + extra
            assert _report(H, k, extra) == attendu, (H, k, extra)
            vus += 1
    assert vus == sum(H + 1 for H in range(1, 8)) == 35, vus


def test_etage1bis_le_flag_d_overkill_ne_change_PAS_ENCORE_la_loi():
    """CE TEST EST LA POUR TOMBER LE JOUR OU `#489-r2` SERA FERME, et il dit pourquoi il existe.

    Le compte natif se lit sur l'index d'OVERKILL (`HasFlag(target, UnitFlag.Overkilled)` est le
    gate du seul call-site a flag LITTERAL 1), pas sur celui de la MORT. L'etage est desormais
    EXPOSE (`overkill_at_hit`) mais la LOI ne le consomme pas encore : les deux formes qui s'en
    deduisent naivement sont refutees LIVE, chacune par un montage different --
      * `max(0, H-k)`      : 3 rouges sur `test_523_...` + 2 sur `test_chain_...` (2026-08-15) ;
      * `(H-k) - 1 si ovk` : refutee par #505 sur `1129 BloodyFury` (2 au lieu de 3).
    Tant que le montage qui SEPARE n'est pas joue, consommer le flag serait un FIT."""
    assert _report(6, 2, 1, ovk_at=0) == _report(6, 2, 1, ovk_at=5) == _report(6, 2, 1) == 4


def test_etage1_les_regimes_MESURES_LIVE_passent_tous():
    """Les points que `master` valide LIVE, rejoues sur la loi portee.

    `1006 MultiThreatEliminator` (#125) : extra = 1. Le regime `H == k` pin le terme
    `+ extraHits` (le 2e maillon EST frappe alors qu'AUCUN coup n'est gaspille).
    ⚠ Le regime `1129 BloodyFury` de #505 (extra = 0, H = 4) n'est PAS ici : la loi portee y rend
    1/4, et c'est precisement le residu `#489-r2`. L'y mettre rendrait ce fichier rouge sur une
    faute CONNUE au lieu de la nommer."""
    for H, k, attendu in [(6, 6, 1), (6, 2, 4), (5, 2, 3)]:
        assert _report(H, k, 1) == attendu, (H, k)


def test_etage1_les_deux_regimes_de_bord():
    """SURVIVANTE -> 0 (pas meme `+extraHits`, le natif gate sur `list.Count > 0`) ;
    DEJA MORTE a l'entree -> H + extra (chaque coup tombe sur le cadavre, site (a))."""
    assert ChainLeftOverHitsAttackDamage._left_over_hits(
        {"per_hit_health": [1, 1, 1], "hp_before": 99}, 1) == 0
    assert ChainLeftOverHitsAttackDamage._left_over_hits(
        {"per_hit_health": [1, 1, 1], "hp_before": 0}, 1) == 4


def test_etage1_le_maillon_publie_l_entree_qui_manque_a_la_loi():
    """`ChainLeftOverHitsAttackDamage.execute` doit recopier `overkilled` / `overkill_at_hit` dans
    chaque maillon de `chain` : sans eux, un probe qui veut fermer `#489-r2` ne peut pas LIRE
    l'index d'overkill du maillon, et retomberait sur `(H, k)` -- exactement l'information
    insuffisante qui a fait echouer les deux correctifs."""
    src = inspect.getsource(ChainLeftOverHitsAttackDamage.execute)
    arbre = ast.parse("if 1:\n" + "\n".join("    " + l for l in src.splitlines()))
    cles = set()
    for n in ast.walk(arbre):
        if isinstance(n, ast.Dict):
            cles |= {k.value for k in n.keys
                     if isinstance(k, ast.Constant) and isinstance(k.value, str)}
    assert {"overkilled", "overkill_at_hit"} <= cles, sorted(cles)


# ==================================================================================================
# ETAGE 2 -- le flag d'overkill EST calcule, et il est desormais REMONTE
# ==================================================================================================

def _serie(hits, **kw):
    """Une serie de `hits` coups a valeur FIXE, sans crit ni block : le squelette minimal de
    `_run_hits`. `hit_nc == hit_cr` degenere -> aucun tirage de valeur."""
    base = dict(rng=IntBasedMersenneTwister(1234), hit_nc=HitDamage(10, 10), hit_cr=HitDamage(10, 10),
                crit_chance=0, crit_enabled=False, hits=hits, block_sources=None)
    base.update(kw)
    return AttackDamageOperation._run_hits(**base)


def test_etage2_run_hits_rend_l_etat_d_overkill():
    """`_run_hits` porte `IsOverkill` depuis #462-r4e-o-r1 : les trois cles existent, et
    `overkilled` est TRI-ETAT (`None` = PV non captes, jamais un `False` devine)."""
    sans_pv = _serie(3)
    assert sans_pv["overkilled"] is None, "PV non captes -> ni True ni False"
    assert "overkill_at_hit" in sans_pv and "hits_executed" in sans_pv
    assert sans_pv["hits_executed"] == 3

    # Cible a 15 PV, coups de 10 : le coup 0 la met a 0, le coup 1 l'ECRASE -> le flag tombe.
    avec_pv = _serie(3, hp_current=15, limits_hp=15)
    assert avec_pv["overkilled"] is True
    assert avec_pv["overkill_at_hit"] is not None
    # TEMOIN : une cible qui SURVIT ne pose rien -- sinon l'assertion ci-dessus serait vacante.
    survit = _serie(1, hp_current=10000, limits_hp=10000)
    assert survit["overkilled"] is False and survit["overkill_at_hit"] is None


def test_etage2_execute_ability_attack_REMONTE_les_trois_cles():
    """La fiche #489-r1 declare ces cles ABSENTES du retour d'`execute_ability_attack`, et en fait
    son bloquant. Elles y sont : ce test lit le `return` du foyer, pas une doc."""
    src = inspect.getsource(AttackDamageOperation.execute_ability_attack)
    arbre = ast.parse("if 1:\n" + "\n".join("    " + l for l in src.splitlines()))
    cles = set()
    for n in ast.walk(arbre):
        if isinstance(n, ast.Return) and isinstance(n.value, ast.Dict):
            cles |= {k.value for k in n.value.keys
                     if isinstance(k, ast.Constant) and isinstance(k.value, str)}
    assert {"overkilled", "overkill_at_hit", "hits_executed"} <= cles, sorted(cles)


# ==================================================================================================
# ETAGE 3 -- #889-r2 : `options+0x08` = les coups (1-based) apres lesquels le crit reste autorise
# ==================================================================================================

def test_etage3_sans_liste_le_crit_s_eteint_au_premier_coup_non_critique():
    """`Any(null)` du natif = faux. C'est le regime de l'attaque NORMALE et des douze call-sites
    a struct zeroee : comportement d'avant #889-r2, strictement inchange."""
    assert _serie(3)["crit_allowed"] is False


@pytest.mark.parametrize("liste,attendu", [
    ([1, 2, 3], True),      # tous les coups re-arment -> l'attaque suivante herite d'un crit ARME
    ([3], True),            # SEUL le dernier coup (i=2 -> i+1=3) re-arme : c'est lui qui decide
    ([1], False),           # `1217` : re-arme apres le coup 1, s'eteint apres le coup 2
    ([4], False),           # hors serie (3 coups) -> jamais vrai : la liste est bien 1-BASED
])
def test_etage3_la_liste_porte_des_numeros_1_based(liste, attendu):
    """`hitIndex == i + 1` avec `i` remis a 0 en tete d'`ExecuteHits`. Les quatre cas separent
    l'indexation 1-based de la 0-based : en 0-based, `[3]` serait hors serie et `[4]` aussi."""
    assert _serie(3, crit_allowed_hits=liste)["crit_allowed"] is attendu


def test_etage3_le_canal_est_gate_par_la_famille():
    """`IdunBattle.Operations.AbilityDamageOperation$$ExecuteHits` a une boucle PLATE et n'ecrit
    JAMAIS `hitGroup+0x3c` -> ce canal n'existe que pour la famille ATTACK. Une feuille
    `native_factory="ability"` qui poserait la liste ne doit RIEN re-armer."""
    avec = _serie(3, crit_allowed_hits=[1, 2, 3], is_attack_damage_op=False)
    sans = _serie(3, is_attack_damage_op=False)
    assert avec["crit_allowed"] == sans["crit_allowed"]
    # TEMOIN : la MEME liste MORD sur la famille ATTACK -- sinon l'egalite ci-dessus serait vraie
    # par degenerescence (canal mort des deux cotes).
    assert _serie(3, crit_allowed_hits=[1, 2, 3])["crit_allowed"] is True
    assert _serie(3)["crit_allowed"] is False


def test_etage3_le_canal_CHANGE_L_OBSERVABLE_pas_seulement_un_champ():
    """SCENARIO DE GENERALISATION. Les tests ci-dessus lisent `crit_allowed`, qui est l'ETAT rendu
    a l'attaque suivante -- un champ. Celui-ci mesure ce qui compte : le CRIT d'un coup, donc le
    DEGAT. Regime crafte : crit-chance MOYENNE (le coup 0 ne crite pas toujours) et DEUX coups.

    Sans la liste, le coup 1 ne peut JAMAIS criter des que le coup 0 a rate (`crit_gate_open`
    ferme). Avec `[1]`, il le peut. On balaie des graines jusqu'a exhiber le regime, et on EXIGE
    qu'il existe -- un balayage muet passerait pour vert."""
    vus_avec, vus_sans = 0, 0
    for graine in range(1, 200):
        def _s(liste):
            return AttackDamageOperation._run_hits(
                rng=IntBasedMersenneTwister(graine), hit_nc=HitDamage(100, 100),
                hit_cr=HitDamage(200, 200), crit_chance=50, crit_enabled=True, hits=2,
                block_sources=None, crit_allowed_hits=liste)
        avec, sans = _s([1]), _s(None)
        if not avec["crits"][0]:                     # le coup 0 a RATE son crit
            vus_sans += 1 if sans["crits"][1] else 0
            vus_avec += 1 if avec["crits"][1] else 0
    assert vus_sans == 0, "sans la liste, le coup 1 ne peut pas criter apres un coup 0 rate"
    assert vus_avec > 0, "TEMOIN DEGENERE : aucune graine n'exhibe un crit au coup 1 avec [1]"


def test_etage3_les_DEUX_phases_de_1217_posent_la_liste():
    """Le CABLAGE, appariement par le NOM du parametre. Les deux call-sites natifs construisent la
    MEME `List<int>`, lui font `Add(1)` et la rangent a `AttackDamageBehaviourOptions+0x08` :
    `...TheLionsWrathAbility$$ExecuteBehaviour` (phase 1) et
    `...TheLionsWrath_PendingAttackAbility$$CreateBehaviour` (phase 2)."""
    racine = pathlib.Path(__file__).resolve().parents[2] / "engine" / "runner"
    foyers = {
        "phase 1 (active 1217)": racine / "abilities" / "darkangels.py",
        "phase 2 (triggered 1520)": (racine / "operations" / "triggers" / "loki"
                                     / "lions_wrath_attack.py"),
    }
    for nom, chemin in foyers.items():
        arbre = ast.parse(chemin.read_text(encoding="utf-8"))
        listes = [kw.value for n in ast.walk(arbre) if isinstance(n, ast.Call)
                  and isinstance(n.func, ast.Name) and n.func.id == "AttackWithAttackDamage"
                  for kw in n.keywords if kw.arg == "crit_allowed_hits"]
        assert len(listes) == 1, "%s : %d call-site(s) portant crit_allowed_hits" % (nom, len(listes))
        assert [e.value for e in listes[0].elts] == [1], nom


# ==================================================================================================
# ETAGE 4 -- #1030-r4 : la famille ABILITY zeroise ses mods attaquant, la famille ATTACK non
# ==================================================================================================

def _noeud_de(fonction):
    """(arbre du MODULE, noeud de la fonction, nom pointe du module, racine du paquet).

    ⚠ ON PARSE LE MODULE, PAS LE CORPS -- et c'est la moitie du correctif #10035.
    `inspect.getsource(fonction)` rend le corps SEUL : les imports de tete n'y sont pas, donc
    AUCUNE resolution de `X.foo()` n'y est possible, quelle que soit la finesse du reste. La
    fonction est ensuite retrouvee par son `__qualname__`, construit selon la regle du langage
    (une `ClassDef` ajoute son nom, une `FunctionDef` ajoute `<locals>` pour ses enfants).

    ⚠ UNE FONCTION INTROUVABLE LEVE, ELLE NE REND PAS `False`. Deux des trois appelants sont des
    `assert not _appelle(...)` : un helper qui rendrait `False` sur ce qu'il n'a pas su lire les
    ferait passer AU VERT sans avoir rien mesure -- le mode de defaillance exact que le CLAUDE.md
    recense (<< un recenseur ne peut pas rendre zero sur ce qu'il ne visite pas >>)."""
    chemin = pathlib.Path(inspect.getsourcefile(fonction)).resolve()
    module = inspect.getmodule(fonction)
    assert module is not None, "module introuvable pour %r" % (fonction,)
    racine = chemin.parents[len(module.__name__.split(".")) - 1]
    arbre = ast.parse(chemin.read_text(encoding="utf-8"))

    cible, trouves = fonction.__qualname__, []

    def descendre(parent, prefixe):
        for n in ast.iter_child_nodes(parent):
            if not isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                continue
            q = "%s.%s" % (prefixe, n.name) if prefixe else n.name
            if q == cible and not isinstance(n, ast.ClassDef):
                trouves.append(n)
            descendre(n, q if isinstance(n, ast.ClassDef) else q + ".<locals>")

    descendre(arbre, "")
    assert len(trouves) == 1, (
        "`%s` introuvable (ou en %d exemplaires) dans %s -- le helper ne peut RIEN conclure, et "
        "surtout pas rendre False" % (cible, len(trouves), chemin.name))
    return arbre, trouves[0], MIG.nom_module(chemin, racine), racine


def _porte_le_nom(module_absolu: str, nom: str) -> bool:
    """Le module RESOLU expose-t-il vraiment `nom` ? TRI-ETAT : un import impossible LEVE.

    C'est le second garde de non-permissivite : sans lui, tout `<un module>.foo(...)` compterait,
    y compris sur un module qui n'a jamais porte `foo`."""
    import importlib
    try:
        return hasattr(importlib.import_module(module_absolu), nom)
    except Exception as exc:                                   # noqa: BLE001 -- tri-etat
        raise AssertionError(
            "`%s` non importable (%s) : le helper ne peut pas trancher, il refuse de rendre un "
            "booleen" % (module_absolu, exc)) from exc


def _appelle(fonction, nom: str) -> bool:
    """La fonction APPELLE-t-elle `nom` ? Les DEUX formes d'appel comptent (#10035).

    Il ne reconnaissait qu'un `ast.Name` -- donc `nom(...)` (formes A et C). Or `combat.py` ecrit
    `_abase.ability_pierce_effect_bonus(...)`, un `ast.Attribute` : c'est la **FORME B** que le
    CLAUDE.md PRESCRIT (`import X` puis `X.foo()`, la seule des trois qui morde sous
    `monkeypatch.setattr`, et le site le dit explicitement en commentaire). Le garde penalisait
    donc la forme que la doctrine exige, et l'aurait fait << reparer >> a l'envers -- en forme A,
    qui aurait desarme le patcheur `probe_910_relic_bolt_pistol_live` que ce site protege.

    ⚠ ET IL NE DEVIENT PAS PERMISSIF, par DEUX crans independants : le porteur de l'attribut doit
    resoudre, DANS SA PORTEE, vers un module (`MIG.ResolveurDeModules`, foyer unique de cette
    question -- #485-r2, ecrit apres deux faux positifs nes d'une table PLATE), et ce module doit
    REELLEMENT porter le nom. Un `<n_importe_quel_objet>.<nom>(...)` ne compte pas ; c'est ce qui
    garde le sens NEGATIF de l'etage 4 (`assert not _appelle(AttackWithAbilityDamage.execute, ...)`),
    lequel serait sinon un faux rouge des qu'un homonyme apparaitrait sur un objet quelconque."""
    arbre, noeud, mod, racine = _noeud_de(fonction)
    resolveur = MIG.ResolveurDeModules(arbre, mod, racine)
    for n in ast.walk(noeud):
        if not isinstance(n, ast.Call):
            continue
        f = n.func
        if isinstance(f, ast.Name) and f.id == nom:
            return True                                        # formes A et C
        if isinstance(f, ast.Attribute) and f.attr == nom and isinstance(f.value, ast.Name):
            cible = resolveur.resoudre(f.value.id, f.value)     # forme B
            if cible and _porte_le_nom(cible, nom):
                return True
    return False


def test_etage4_le_HELPER_voit_la_forme_B_SANS_devenir_permissif():
    """LE CRAN DE L'ETAGE 4 LUI-MEME (#10035). Un `_appelle` repare en matchant n'importe quel
    attribut du bon nom ne garderait plus RIEN -- et il retournerait le sens NEGATIF de
    `test_etage4_la_famille_ABILITY_ne_thread_PAS` en faux rouge des qu'un homonyme apparait.

    Les deux temoins sont REELS et vivent dans le meme `combat.py`, donc ce test ne peut pas
    devenir vacant sans que quelqu'un le voie :

      * POSITIF -- `_abase.ability_pierce_effect_bonus(...)` : porteur = liaison de MODULE
        (`import engine.runner.abilities.base as _abase`), et le module porte bien le nom ;
      * NEGATIF -- `AttackDamageOperation.execute_ability_attack(...)` : meme FORME syntaxique
        (`ast.Attribute` sur un `ast.Name`), mais le porteur est une CLASSE. Un helper qui se
        contenterait du nom d'attribut le compterait ; celui-ci ne le compte pas.

    ⚠ Le temoin NEGATIF est choisi pour etre EXIGEANT : `execute_ability_attack` est justement un
    nom que l'etage 5 cherche ailleurs comme fonction (`_appelle(AB._AbilityAttack.
    execute_ability_attack, ...)`), donc l'homonymie n'est pas hypothetique."""
    assert _appelle(ChainLeftOverHitsAttackDamage.execute, "ability_pierce_effect_bonus"), (
        "TEMOIN POSITIF DEGENERE : la forme B n'est plus lue, ce test ne garde plus rien")
    for nom in ("execute_ability_attack", "get", "append"):
        assert not _appelle(ChainLeftOverHitsAttackDamage.execute, nom), (
            "`%s` est appele sur un objet qui n'est PAS un module : le helper est devenu "
            "permissif et ne garde plus le sens NEGATIF de l'etage 4" % nom)


def test_etage4_le_HELPER_REFUSE_de_conclure_sur_ce_qu_il_n_a_pas_lu():
    """L'autre moitie du cran : une fonction introuvable doit LEVER, jamais rendre `False`.

    Deux des appelants sont des `assert not _appelle(...)` : un `False` par defaut les ferait
    passer au vert sans qu'aucune mesure ait eu lieu -- exactement le << vert sur un recensement
    vide >> que le CLAUDE.md recense comme mode de defaillance.

    ⚠ LE PORTEUR EST UNE `lambda`, ET LE PREMIER CHOIX ETAIT MAUVAIS. Une fonction IMBRIQUEE avait
    ete prise comme temoin d'introuvable ; mesure : elle est PARFAITEMENT trouvee (le parcours
    construit `<qualname>.<locals>.<nom>` comme le langage), donc le test ne mordait pas -- il a
    rendu `DID NOT RAISE`. C'est une `lambda` qui echappe reellement au parcours (il ne visite que
    `FunctionDef` / `AsyncFunctionDef` / `ClassDef`), et le second cran, l'AMBIGUITE, est garde par
    le meme `len(trouves) == 1`."""
    temoin = lambda: None                                          # noqa: E731 -- c'est le SUJET

    with pytest.raises(AssertionError, match="introuvable"):
        _appelle(temoin, "ability_pierce_effect_bonus")


def test_etage4_la_famille_ABILITY_ne_thread_PAS_le_bonus_de_percage():
    """FIDELITE, pas oubli. `CalculateAbilityDamage` passe `attackModifiers` memset a 0 ->
    `additionalPiercing = Fix64.Zero` dans `GetBaseDamageWithFixedPiercedArmor`. Y ajouter le
    bonus ferait diverger le port du natif sur TOUS les porteurs a effet de percage."""
    assert not _appelle(AttackWithAbilityDamage.execute, "ability_pierce_effect_bonus")


def test_etage4_les_DEUX_noeuds_de_la_famille_ATTACK_le_threadent():
    """`AttackWithAttackDamage` le faisait depuis case-117 ; `ChainLeftOverHitsAttackDamage`, qui
    route la MEME famille pour 1006/1048/1129, ne le faisait pas -- c'etait le vrai #1030-r4."""
    assert _appelle(AttackWithAttackDamage.execute, "ability_pierce_effect_bonus")
    assert _appelle(ChainLeftOverHitsAttackDamage.execute, "ability_pierce_effect_bonus")


# ==================================================================================================
# ETAGE 5 -- #512-r3 : `On(Attack = 9)` part DEJA de la voie ability
# ==================================================================================================

def test_etage5_la_voie_ability_emet_deja_On9():
    """`after_hit_ability_attack` construit un `TriggerEvent(EventTriggerType.Attack, ...)`, et
    `damage_ops/ability.py` l'appelle a chaque attaque d'ability. Le residu #512-r3 lisait le NOM
    de `finish_attack_triggers` (qui n'a bien qu'un call-site) au lieu de l'EVENEMENT."""
    from engine.dsl.event_trigger_type import EventTriggerType
    from engine.runner.operations.triggers.dispatch import attack as A
    from engine.runner.operations.damage_ops import ability as AB

    src = inspect.getsource(A.after_hit_ability_attack)
    arbre = ast.parse("if 1:\n" + "\n".join("    " + l for l in src.splitlines()))
    events = [n.args[0] for n in ast.walk(arbre)
              if isinstance(n, ast.Call) and isinstance(n.func, ast.Name)
              and n.func.id == "TriggerEvent" and n.args]
    noms = [a.attr for a in events if isinstance(a, ast.Attribute)]
    assert EventTriggerType.Attack.name in noms, noms

    # ... et ce vecteur-la EST appele par la voie ability (sinon l'assertion ci-dessus serait
    # vraie sur du code mort).
    assert _appelle(AB._AbilityAttack.execute_ability_attack, "after_hit_ability_attack")


def test_etage5_finish_attack_triggers_a_DEUX_foyers_et_pas_un_de_plus():
    """#512-r4 -- CE CLIQUET A CHANGE D'INVARIANT, ET C'EST DELIBERE.

    Il gardait « UN SEUL call-site », comme moitie VRAIE de #512-r3 : lire le NOM
    `finish_attack_triggers` au lieu de l'EVENEMENT `On(9)` faisait croire que la voie ability ne
    l'emettait pas, et ajouter un second emetteur y aurait DOUBLE l'evenement. Cette prudence-la
    est REMPLIE autrement depuis #512-r4 : l'emission par FEUILLE est desormais GATEE par
    `is_outside_attack` (cf. l'etage 6), donc un foyer de NOEUD n'ajoute rien -- il DEPLACE.

    Le nouvel invariant est la topologie NATIVE : le slot 59 (`FinishAttack`) est pousse par les
    NOEUDS de l'arbre et par la voie MESSAGE, jamais par une operation de degat. Cote port, cela
    fait exactement DEUX foyers -- `damage_ops/normal.py` (la voie normale/overwatch, mirror du
    `Attack(...)` de `ALoki_NormalAttackAbility$$GetAttackDamageBehaviour`) et
    `abilities/behaviours/combat.py::_emettre_finish_attack_de_noeud` (le foyer de NOEUD, appele par
    `SortedAttackSeries` et par `HazeOfCorruption`). Un TROISIEME nom de fichier ici veut dire qu'un
    emetteur a ete recable ailleurs qu'au foyer -- c'est ce qu'on refuse."""
    racine = pathlib.Path(__file__).resolve().parents[2] / "engine"
    sites = []
    for chemin in racine.rglob("*.py"):
        arbre = ast.parse(chemin.read_text(encoding="utf-8"))
        for n in ast.walk(arbre):
            fn = n.func if isinstance(n, ast.Call) else None
            nom = (fn.id if isinstance(fn, ast.Name)
                   else fn.attr if isinstance(fn, ast.Attribute) else None)
            if nom == "finish_attack_triggers":
                sites.append(chemin.name)
    assert sorted(sites) == ["combat.py", "normal.py"], sites


def test_etage5_le_vecteur_On9_de_la_feuille_est_GATE_par_is_outside_attack():
    """#512-r4 -- LE CRAN QUI REMPLACE « un seul call-site ». Une feuille NUE
    (`IdunBattleLogic.Entities.DSLBehaviors$$AttackDamage` / `$$AbilityDamage`, `isOutsideAttack`
    = 0) ne pousse NI `StartAttack` NI `FinishAttack` : c'est le noeud parent qui ouvre et ferme.
    Le port gatait deja `On(PreAttack = 5)` (#512-r2) et PAS `On(Attack = 9)` -- d'ou une
    CARDINALITE fausse des qu'un noeud porte deux feuilles sur la MEME cible (`1088
    HellfyreMissileRack`) ou une feuille nue dans le `Attack(...)` d'une autre attaque (le FOLD de
    l'attaque normale, les N transferts d'`HazeOfCorruption`).

    On garde le GATE, pas son ecriture : les deux facades doivent thread `emit_finish_attack`
    depuis leur `is_outside_attack`, et `after_hit_ability_attack` doit en faire une CONDITION."""
    from engine.runner.operations.triggers.dispatch import attack as A
    from engine.runner.operations.damage_ops import ability as AB
    from engine.runner.operations.damage_ops import normal_like as NL

    src = inspect.getsource(A.after_hit_ability_attack)
    arbre = ast.parse("if 1:\n" + "\n".join("    " + l for l in src.splitlines()))
    gardes = [n for n in ast.walk(arbre)
              if isinstance(n, ast.If) and isinstance(n.test, ast.Name)
              and n.test.id == "emit_finish_attack"]
    assert gardes, "`On(9)` n'est plus sous le gate `emit_finish_attack` dans la facade after-hit"
    # ... et le gate doit etre ALIMENTE par `is_outside_attack` aux DEUX call-sites, sinon il est
    # arme mais toujours vrai (degradation silencieuse, exactement le regime d'avant).
    for fn in (AB._AbilityAttack.execute_ability_attack, NL._NormalLike.execute_normal_like):
        s = inspect.getsource(fn)
        a = ast.parse("if 1:\n" + "\n".join("    " + l for l in s.splitlines()))
        kw = [k for n in ast.walk(a) if isinstance(n, ast.Call)
              for k in (n.keywords or []) if k.arg == "emit_finish_attack"]
        assert kw, "%s ne thread pas `emit_finish_attack`" % fn.__qualname__
        assert any("is_outside_attack" in ast.unparse(k.value) for k in kw), \
            "%s thread `emit_finish_attack` sans le derier d'`is_outside_attack`" % fn.__qualname__
