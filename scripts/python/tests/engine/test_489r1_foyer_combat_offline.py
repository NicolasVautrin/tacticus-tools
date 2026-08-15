"""CLIQUET de la tranche ENGINE `combat.py` -- #489-r1, #889-r2, #1030-r4, #512-r3.

Quatre residus du meme foyer, tranches le 2026-08-15 par lecture du decompile du build courant
(`t6dpr4k06g`). **DEUX de leurs premisses sont FAUSSES et deux sont PERIMEES** ; ce fichier fige
les quatre lectures, pour que personne ne les rouvre a tort ni ne les << repare >> a l'envers.

ETAGE 1 -- #489-r1 (a). LA LOI DE `GetLeftOverHits` PERDAIT UN COUP.
  `ChainLeftOverHitsAttackDamage._left_over_hits` rendait `max(0, H-k-1) + extra` ; le natif compte
  les entrees `LeftOverDamage` dont le FLAG (`+0x78 wasAlreadyDead`) est VRAI, et ce compte vaut
  `max(0, H-k)`. La preuve n'est pas une table de mesures : c'est que le port pousse DEJA ces
  entrees ailleurs (`operations/left_over_damage.py::record_left_over_damages`, mirror LU des trois
  call-sites d'`ApplyDamageOperation$$AddLeftoverHit`, live-valide par #209/#221). L'etage 1
  confronte les DEUX ports du MEME fait sur un balayage exhaustif de (H, k).

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

def _entrees_flag_vrai(per_hit_health, hp_before, deja_overkilled=False):
    """Re-joue la boucle d'`operations/left_over_damage.py::record_left_over_damages` et rend
    `(nb d'entrees FLAG-VRAI, nb d'entrees TOTAL)`.

    C'est le MEME re-jeu, aux memes conditions ; la seule chose que `record_left_over_damages` ne
    porte pas est le FLAG lui-meme (residu nomme dans son en-tete), et c'est precisement ce que
    `GetLeftOverHits` compte. On le reconstruit ici a partir de ses branches :

        (A)/(B) cible DEJA morte (ou deja `Overkilled`) a l'entree du coup -> entree, flag VRAI
        (C)     le coup TUE                                                -> entree, flag FAUX
    """
    flag_vrai = 0
    total = 0
    hp = int(hp_before)
    for dmg in per_hit_health:
        if deja_overkilled or hp <= 0:
            flag_vrai += 1
            total += 1
            continue
        applique = min(hp, int(dmg))
        hp -= applique
        if hp <= 0 and applique > 0:
            total += 1              # site (C) : flag FAUX (la cible etait VIVANTE a l'entree)
    return flag_vrai, total


@pytest.mark.parametrize("extra", [0, 1])
def test_etage1_la_loi_egale_le_cardinal_des_entrees_flag_vrai(extra):
    """Balayage EXHAUSTIF de (H, k) : la loi portee doit rendre, coup pour coup, le nombre
    d'entrees flag-vrai + le `+ extraHits` gate par « au moins UNE entree »."""
    vus = 0
    for H in range(1, 8):
        for pv in range(1, H + 2):          # k = pv (chaque coup retire 1 PV)
            per_hit = [1] * H
            attendu_flag, attendu_total = _entrees_flag_vrai(per_hit, pv)
            attendu = attendu_flag + (extra if attendu_total > 0 else 0)
            obtenu = ChainLeftOverHitsAttackDamage._left_over_hits(
                {"per_hit_health": per_hit, "hp_before": pv}, extra)
            assert obtenu == attendu, (
                "H=%d pv=%d extra=%d : loi=%d, cardinal des entrees flag-vrai=%d"
                % (H, pv, extra, obtenu, attendu))
            vus += 1
    # TEMOIN NON DEGENERE : un balayage qui n'aurait exerce aucun regime passerait pour vert.
    assert vus == sum(H + 1 for H in range(1, 8)) == 35, vus


def test_etage1_l_ancienne_loi_DIVERGE_ici_meme():
    """CONTRE-EPREUVE. `max(0, H-k-1)` n'est pas << une autre ecriture >> de la loi : elle rend
    STRICTEMENT moins des que la cible meurt avant le dernier coup. Sans cette assertion, l'etage 1
    passerait aussi avec l'ancienne formule si le re-jeu temoin etait, lui aussi, faux."""
    divergences = []
    for H in range(1, 8):
        for pv in range(1, H + 2):
            per_hit = [1] * H
            k = pv if pv <= H else None
            if k is None:
                continue
            ancienne = max(0, H - k - 1)
            attendu_flag, _ = _entrees_flag_vrai(per_hit, pv)
            if ancienne != attendu_flag:
                divergences.append((H, pv, ancienne, attendu_flag))
    assert divergences, "aucun regime ne separe l'ancienne loi de la nouvelle : temoin degenere"
    # Elle SOUS-ESTIME toujours, jamais l'inverse -- c'est la signature de l'ecart mesure par #505.
    assert all(a < b for _H, _pv, a, b in divergences), divergences


def test_etage1_les_six_regimes_mesures_passent():
    """Les SIX points que les fiches #489 / #505 / #125 portent au dossier, rejoues sur la loi.

    `1129 BloodyFury` : extraHits **null** (extra = 0), H = 4 CONNU (4 attaques forcees), report lu
    DANS le live sur un 2e maillon SURVIVANT (`probe_505_bloody_fury.py`).
    `1006 MultiThreatEliminator` : extra = 1, le regime `H == k` pin le terme `+ extraHits`.
    """
    # (H, k, extra, report LIVE attendu)
    mesures = [(4, 1, 0, 3), (4, 2, 0, 2), (4, 3, 0, 1), (4, 4, 0, 0),   # #505 / 1129
               (6, 6, 1, 1),                                            # #125 --hp-target 10000
               (5, 2, 1, 4)]                                            # #125 PV 2500 / 3000
    for H, k, extra, attendu in mesures:
        atk = {"per_hit_health": [1] * H, "hp_before": k}
        assert ChainLeftOverHitsAttackDamage._left_over_hits(atk, extra) == attendu, (H, k, extra)


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

def _appelle(fonction, nom: str) -> bool:
    """La fonction cite-t-elle `nom` comme APPEL (pas seulement dans un commentaire) ?"""
    src = inspect.getsource(fonction)
    arbre = ast.parse("if 1:\n" + "\n".join("    " + l for l in src.splitlines()))
    return any(isinstance(n, ast.Call) and isinstance(n.func, ast.Name) and n.func.id == nom
               for n in ast.walk(arbre))


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


def test_etage5_finish_attack_triggers_n_a_bien_qu_UN_call_site():
    """La moitie VRAIE de la fiche, gardee telle quelle : ajouter un second emetteur DOUBLERAIT
    `On(9)` sur les 37 consommateurs recenses. Si un jour ce compte bouge, c'est que quelqu'un a
    pris #512-r3 au mot -- et ce test est l'endroit ou on s'en apercoit."""
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
    assert sites == ["normal.py"], sites
