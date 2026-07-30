"""Gate d'entree du generateur d'abilities de l'IA : `HasFlag(unit, ActiveAbilityUsed = 2)`.
GARDE de non-regression, LIVE.

NATIF (mirror relu sur `rnca9r7q6c`) -- PREMIERE instruction de l'etat 0 de
`IdunBattle.AI.ActionGenerators.ActiveAbilityActionGenerator.u003CGenerateActionsu003Ed__7$$MoveNext` :

    if (IdunBattle.Entities.UnitExtensions$$HasFlag(<unit @+0x20>, 2)) return 0;

Le generateur rend ZERO action, AVANT meme `GetUnitAbilitiesInOrder` -- donc l'attaque NORMALE tombe
avec les actives (meme liste, cf. #64). `ABaseAiActorTactic$$GetDefaultActiveAbilityActionGenerators`
instancie SIX generateurs de cette classe (5 tiers NonComparable + 1 Comparable) ; le
`MovementActionGenerator` est d'une AUTRE classe -> une unite qui a consomme son action peut encore
SE DEPLACER, et rien d'autre.

POURQUOI CETTE GARDE EXISTE. C'est l'un des deux residus `move` de la fiche #17, etiquete « over-fire
RNG » -- etiquette FAUSSE pour celui-la. Re-derivation du 2026-07-30 (`stages17_gen`, build
`rnca9r7q6c`) : a `1357 s6`, `u85 tyranParasite` porte `unitFlags = [2]` apres avoir caste 1121
ItItches au pas 5 ; le natif ne peut plus que BOUGER vers (3,2), le port emettait `69 -> u93`. Rien
d'aleatoire : un gate DETERMINISTE manquant. Effet mesure du correctif sur le batch GEN
(12345/2468/54321/1357, 20 pas) : move 61/65 -> **62/65**, `generator-overfire` 2 -> 1, axe ability
inchange (50/53). Le residu restant est, lui, reellement RNG
(`SpawnPoxwalkersPlaybook$$GetUseProbability = TurnsStarted x 1/5`, 2468 s4).

CE QUI REND L'ETAT OBSERVABLE. `ActiveAbilityOperation$$AddFlagsAfterAbilityExecution` lit DEUX
virtuals independants : `SetsActiveAbilityUsedFlag` (-> flag 2) et `SetsEndTurnFlags` (-> fin de
tour). `1121 ItItches` override le SECOND seulement : le caster garde son activation ET porte deja
son flag. C'est le montage.

LES DEUX MOITIES SONT NECESSAIRES. « Le port ne propose plus d'ability » ne prouve rien tout seul
(plus de cible ? plus de tuile ?). La garde exige donc AUSSI que le port dont on NEUTRALISE le seul
canal `active_ability_used_by_id` en propose une -- c'est le port d'avant le correctif, et c'est ce
qui fait mordre le test.

Montage : fixture `active_ability_used_case` (cf. `tests/engine/conftest.py` ->
`probe_17_active_ability_used_gate`). ASCII only.

NON COUVERT, et nomme expres : cette garde porte sur « plus aucune ability », PAS sur l'accord
move-vs-finish qui suit. Mesure des deux montages -- sur `MC1_63` le natif rend `MoveUnitMessage`
(la forme exacte de 1357 s6, et le port gate rend un `move` lui aussi), mais sur `MC1_67` il rend
`FinishUnitTurnMessage` (son meilleur deplacement est la tuile COURANTE -> action nulle) la ou le
port gate rend quand meme un `move` a utilite NEGATIVE. Ce second ecart est DISTINCT (le
`MovementActionGenerator` du port rend TOUJOURS une action, cf. sa docstring) et n'est pas traite
ici."""
from __future__ import annotations


def _assert_montage(c, label):
    """Sans ces quatre faits, l'assertion principale serait vide de sens."""
    assert c["cast_ok"], f"[{label}] le cast d'ItItches (1121) a echoue -- aucun flag pose"
    assert c["flag_set_before"] is False, \
        (f"[{label}] le caster portait DEJA `ActiveAbilityUsed` avant le cast "
         f"(flags={c['flags_before']}) : le regime temoin n'en est pas un")
    assert c["flag_set_after"] is True, \
        (f"[{label}] `ActiveAbilityUsed` (id {c['flag_id']}) n'est PAS pose apres le cast "
         f"(flags={c['flags_after']}) -- ItItches ne pose plus le flag, le montage est a refaire")
    assert c["has_action_left_after"] is True, \
        (f"[{label}] le tour du caster est TERMINE apres le cast (hasActionLeft="
         f"{c['has_action_left_after']}) : on ne mesure plus le gate d'ability mais la fin de tour "
         f"-- 1121 doit rester dans `NO_END_TURN_ABILITY_TYPES`")
    # `targets` = cibles atteignables CE TOUR, deplacement inclus (`fromHere` = sans bouger). C'est
    # `targets` qui compte ici : `AttackQuery$$GetValidTargets` ne gate PAS sur le flag, donc un port
    # non gate sur-tire aussi bien depuis une tuile de deplacement (c'est exactement 1357 s6).
    assert (c["attack_targets_after"] or 0) > 0, \
        (f"[{label}] apres le cast, l'attaque normale n'a plus AUCUNE cible legale ce tour "
         f"(targets={c['attack_targets_after']}, fromHere={c['attack_fromhere_after']}) : un port "
         f"non gate ne pourrait pas sur-tirer, la contre-epreuve serait vide")
    assert c["scene_sees_after"] is True, \
        (f"[{label}] la Scene du port ne voit pas le flag (scene_sees_after="
         f"{c['scene_sees_after']}) : le canal `active_ability_used_by_id` ne remonte pas")


def _assert_tile_target_route_is_covered(c, label):
    """#302 -- la route Comparable SANS prediction (domaine de cible TUILE, ouverte par #302 et
    dont `1169 PlagueburstMortar` est le 1er membre) est-elle COUVERTE par le gate ?

    MESURE, pas supposition : le probe compte les appels a `nonattack_candidates` pendant
    `engine_decide`. Elle vit a l'INTERIEUR de `ComparableAbilityGenerator.generate`, donc EN AVAL
    du gate. Le discriminant est la PAIRE mesuree sur le MEME etat (apres le cast) :
    **0 appel quand le gate coupe, >= 1 quand on le neutralise**.

    ⚠ Le compte AVANT le cast n'entre PAS dans le verdict, et une premiere version de cette garde
    s'y appuyait a tort : le tactic s'arrete au PREMIER generateur non-nul, donc si une
    NonComparable sort avant (mesure `MC1_63`/12163 : le port propose `1121`), le generateur
    Comparable n'est jamais atteint et la route n'est pas empruntee -- sans que le gate y soit pour
    quoi que ce soit. Faire dependre le verdict de ce compte, c'est mesurer quel generateur gagne,
    pas la portee du gate.

    Cote natif c'est la meme reponse, et elle est STRUCTURELLE :
    `IdunBattle.AI.Tactics.ABaseAiActorTactic$$GetDefaultActiveAbilityActionGenerators` instancie
    SIX generateurs, TOUS par `ActiveAbilityActionGenerator$$.ctor` (5 tiers NonComparable pris dans
    `dict[1000/100/0/-100/-1000]` + le set `special`) -- il n'existe AUCUNE autre classe de
    generateur d'abilities, donc aucune route qui echapperait au gate. Et le gate precede
    `GetUnitAbilitiesInOrder`, donc il ignore le domaine de cible (entite comme tuile)."""
    after = c.get("nonattack_route_after") or {}
    ungated = c.get("nonattack_route_ungated") or {}
    assert ungated.get("nonattack_calls", 0) >= 1, \
        (f"[{label}] gate NEUTRALISE et la route non-attaque / TUILE (#302) n'est pas empruntee "
         f"({ungated}) : le compteur ne mesure rien sur cet etat, l'assertion suivante serait vide")
    assert after.get("nonattack_calls", None) == 0, \
        (f"[{label}] le gate coupe l'attaque mais la route non-attaque / TUILE (#302) est ENCORE "
         f"empruntee ({after}) -- une ability a cible TUILE pourrait donc etre proposee a une unite "
         f"qui a deja consomme son action. Le natif n'a qu'UNE classe de generateur d'abilities "
         f"(`ABaseAiActorTactic$$GetDefaultActiveAbilityActionGenerators`), gatee en tete. "
         f"Contre-epreuve du meme etat, gate neutralise : {ungated}.")


def _assert_native_offers_no_ability(c, label):
    assert "ActiveAbilityMessage" in (c["native_before"] or []), \
        (f"[{label}] REGIME TEMOIN casse : le natif ne proposait aucune ability AVANT le cast "
         f"({c['native_before']}) -- l'etat n'oppose pas les deux regimes")
    assert "ActiveAbilityMessage" not in (c["native_after"] or []), \
        (f"[{label}] le NATIF propose encore une ability alors que `ActiveAbilityUsed` est pose "
         f"({c['native_after']}) : le gate lu au decompile ne serait pas celui-la -- re-ouvrir le RE")


def test_port_offers_no_ability_once_the_flag_is_set(active_ability_used_case):
    """Le port GATE ne propose plus d'ability quand le flag est pose -- comme le natif."""
    c = active_ability_used_case()
    _assert_montage(c, "MC1_67")
    _assert_native_offers_no_ability(c, "MC1_67")
    _assert_tile_target_route_is_covered(c, "MC1_67")
    assert c["port_before"].get("kind") == "ability", \
        (f"[MC1_67] REGIME TEMOIN casse : le port ne proposait aucune ability AVANT le cast "
         f"({c['port_before']})")
    assert c["port_after"].get("kind") != "ability", \
        (f"[MC1_67] le port propose {c['port_after']} alors que le caster u{c['caster']} porte "
         f"`ActiveAbilityUsed` : le generateur d'abilities doit etre MUET "
         f"(`ActiveAbilityActionGenerator.u003CGenerateActionsu003Ed__7$$MoveNext` rend 0). "
         f"Natif = {c['native_after']}.")


def test_removing_the_gate_reintroduces_the_over_fire(active_ability_used_case):
    """CONTRE-EPREUVE : le MEME port dont on vide le canal `active_ability_used_by_id` re-emet une
    ability. Sans elle, le test precedent passerait meme si le port etait muet pour une tout autre
    raison."""
    c = active_ability_used_case()
    _assert_montage(c, "MC1_67")
    assert c["port_ungated"].get("kind") == "ability", \
        (f"[MC1_67] gate NEUTRALISE, le port propose {c['port_ungated']} : il n'y a donc plus rien "
         f"a gater sur ce montage et la garde ne protege rien. Verifier que l'attaque normale reste "
         f"legale (targets={c['attack_targets_after']}).")
    assert c["port_ungated"].get("ability") is not None, \
        f"[MC1_67] contre-epreuve sans id d'ability : {c['port_ungated']}"


def test_gate_generalises_to_a_second_board(active_ability_used_case):
    """GENERALISATION : meme montage sur un AUTRE couple (board, seed). Le gate est une propriete du
    generateur natif, pas du terrain."""
    c = active_ability_used_case(seed=12163, board="MC1_63")
    _assert_montage(c, "MC1_63")
    _assert_native_offers_no_ability(c, "MC1_63")
    _assert_tile_target_route_is_covered(c, "MC1_63")
    assert c["port_after"].get("kind") != "ability", \
        f"[MC1_63] le port propose {c['port_after']} malgre `ActiveAbilityUsed`"
    assert c["port_ungated"].get("kind") == "ability", \
        f"[MC1_63] contre-epreuve non exercee : gate neutralise -> {c['port_ungated']}"
    assert c["board"] != "MC1_67", \
        f"[MC1_63] montage rejoue sur le MEME board que la reference ({c['board']})"
