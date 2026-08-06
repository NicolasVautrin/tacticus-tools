"""L'ORACLE `abilityReason` n'est PAS l'oracle de la cascade de ciblage -- il le devient (#287-r6).

POURQUOI CE MODULE EXISTE. Le RPC `abilityReason` appelle
`IdunBattle.Core.Services.AttackQuery$$GetInvalidTargetReason`. Le port, lui, mirror
`IdunBattle.Operations.ActiveAbilityOperation$$IsInvalidTarget`. Les deux finissent sur le MEME slot
d'`ITargetingQuery` -- mais `AttackQuery` place DEUX etages AVANT, lus a l'octet sur `rnca9r7q6c` :

    ability = ActiveAbilityComponent.GetOrNull(<collection de l'unite>, abilityType);
    if (ability == null || !ability.CanCurrentlyBeUsed || *(int*)(ability+0x44) == 0)
        -> GenericBrokenTargetingRule(1)                     // TargetingRule.ValidRequest
    if (IsDamagedMachine(unit) && !IsMachinePrimaryAbilityType(unit, abilityType))
        -> GenericBrokenTargetingRule(1)
    if (AttackQuery.IsAlreadyUsedThisTurn(...))              -> 0x40000000000000
    sinon -> <ITargetingQuery>.GetInvalidTargetReason(...)    // LA cascade

`IdunBattle.Operations.ActiveAbilityOperation$$IsInvalidTarget` n'a AUCUN de ces etages. Quand
l'un d'eux mord, `abilityReason` rend `1` pour TOUTE cible et ne dit plus RIEN du ciblage : le
comparer au port compare deux fonctions natives differentes.

⚠ `1` EST REUTILISE A DEUX RANGS. C'est `ValidRequest` ici (amont, ability indisponible) ET le
litteral que la branche `TargetIsTile` de `IdunBattle.Core.Services.TargetingQuery$$GetInvalidTargetReason`
rend pour une tuile non marchable. Un `targetReason == 1` isole ne permet donc PAS de conclure.

LE DISCRIMINANT, deja publie par le RPC et sans capteur neuf :
`IdunBattle.Core.Services.AttackQuery$$GetInvalidCasterReason` porte le MEME etage de
disponibilite, rend le MEME `1`, et ne depend PAS de la cible. `casterReason == ValidRequest`
signe donc le court-circuit AMONT, pour toutes les cibles a la fois.

CE QUI DECLENCHE LE COURT-CIRCUIT LE PLUS SOUVENT, et ce n'est pas un accident de montage : la
constante `initialCooldownTurns` du gameconfig. Une ability qui la porte a `>= 1` demarre avec
`ActiveAbility.Cooldown >= 1`, donc `IdunBattle.Entities.Components.ActiveAbility$$get_CanCurrentlyBeUsed`
rend `false` au TOUR 1 -- quel que soit le board, quel que soit le porteur. `ids_a_cooldown_initial()`
les recense ; la parade est de laisser retomber le cooldown (fin de tour + tour adverse) AVANT de
lire l'oracle, pas d'exclure la mesure.
"""
from __future__ import annotations

import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

import gameconfig                                                          # noqa: E402
from engine.runner.abilities.targeting_rule import TargetingRule as TR     # noqa: E402

# Le code que `AttackQuery` rend pour « ability indisponible ». Nomme, jamais ecrit `1` : le meme
# ordinal designe autre chose un etage plus bas (cf. l'avertissement en tete de module).
CODE_AMONT = int(TR.ValidRequest)

# La constante du gameconfig qui arme le court-circuit. Ecrite ici parce qu'elle n'a PAS de membre
# dans `AbilityConstantType` -- c'est une cle de `constants`, lue par son nom, pas un ordinal.
CLE_COOLDOWN_INITIAL = "initialCooldownTurns"


def _hex_de(bloc) -> int:
    """Le code d'un bloc `casterReason`/`targetReason` du RPC, ou -1 si le bloc n'a pas ete mesure.

    -1 et 0 sont DISTINCTS et doivent le rester : `0` = mesure faite, aucune regle rompue ;
    `-1` = pas de mesure (RPC muet, methode non resolue). Rabattre l'un sur l'autre ferait lire
    « cible valide » sur une panne de capteur."""
    h = (bloc or {}).get("hex")
    if not isinstance(h, str) or not h.startswith("0x"):
        return -1
    return int(h, 16)


def oracle_court_circuite(reponse) -> bool:
    """`abilityReason` a-t-il refuse EN AMONT de la cascade de ciblage ?

    VRAI <=> `casterReason == TargetingRule.ValidRequest`. Dans ce regime, `targetReason` vaut `1`
    pour TOUTE cible et ne dit rien du ciblage : le confronter au port est une comparaison entre
    deux fonctions natives differentes.

    Une reponse SANS `casterReason` mesure (RPC muet) rend `False` : on ne fabrique pas un
    court-circuit qu'on n'a pas mesure -- mais on ne fabrique pas non plus un vert, puisque le
    lecteur voit alors `targetReason` tel quel, avec sa propre absence de mesure."""
    return _hex_de((reponse or {}).get("casterReason")) == CODE_AMONT


def cause_du_court_circuit(reponse) -> str:
    """Ce que la reponse RPC permet de DIRE du terme qui a mordu -- jamais plus.

    `abilityState` vient de `components.ActiveAbility` lu par le hook. Il expose `cooldown`,
    `disabled`, `usable` et -- DEPUIS #287-r9 -- `hasAmmo`/`ammoCost`. Le terme
    `IsDamagedMachine && !IsMachinePrimaryAbilityType` n'est toujours PAS publie : il sort en
    `indeterminee`, jamais en supposition.

    ⚠ LE TERME MUNITIONS EST LE SECOND ETAGE AMONT, ET IL EST BIEN REEL -- #287-r6 l'avait laisse
    « non exerce », #287-r9 l'a exerce. `*(int*)(ability+0x44) == 0` est ce que le RPC publie
    desormais sous `hasAmmo`. MESURE sur `ultraDreadnought` / `DutyEternal` (1158) : a
    `MachineOfWarAmmo = 0`, `casterReason` reste `ValidRequest` APRES 4 tours, `cooldown` retombe
    a `0` -- aucun nombre de tours ne leve ce court-circuit-la. A `MachineOfWarAmmo = 9`, le meme
    couple bascule. Le distinguer du cooldown est ce qui evite de faire tourner des tours pour
    rien, puis de conclure « la cause n'est pas le cooldown » sans savoir laquelle c'est.

    ⚠ TRI-ETAT SUR LE CHAMP LUI-MEME : `hasAmmo` ABSENT signifie « le hook charge ne le publie pas
    encore » (le correctif de `rpc-targeting.ts` attend une fenetre de reinject), PAS « il y a des
    munitions ». Les deux se lisent differemment ci-dessous."""
    st = (reponse or {}).get("abilityState") or {}
    cd = st.get("cooldown")
    if isinstance(cd, int) and cd >= 1:
        return "cooldown=%d (ActiveAbility.CanCurrentlyBeUsed faux)" % cd
    if st.get("disabled") is True:
        return "disabled (ActiveAbility.CanCurrentlyBeUsed faux)"
    if st.get("hasAmmo") is False:
        return "munitions epuisees (ability+0x44 == 0) -- AUCUN nombre de tours ne le leve"
    if not st:
        return "abilityState non publie (ability absente des actives)"
    if "hasAmmo" not in st:
        return ("indeterminee, et le CAPTEUR MANQUE : `hasAmmo` absent du payload (hook non "
                "reinjecte) -- le terme munitions ne peut pas etre ecarte (abilityState=%r)" % (st,))
    return "indeterminee (abilityState=%r)" % (st,)


def cooldown_initial(ability_type) -> int | None:
    """`constants.initialCooldownTurns` du gameconfig pour cet `ActiveAbilityType`, ou `None`.

    `None` = la cle est ABSENTE (ou l'ability inconnue du gameconfig) -- distinct de `0`, qui est
    une valeur mesuree. Le tri-etat est celui de tout ce depot : ne jamais rendre un zero pour
    une non-mesure."""
    nom = gameconfig.ability_name(int(ability_type))
    if nom is None:
        return None
    conf = gameconfig.ability(nom) or {}
    brut = (conf.get("constants") or {}).get(CLE_COOLDOWN_INITIAL)
    if brut is None:
        return None
    try:
        return int(brut)
    except (TypeError, ValueError):
        return None


def ids_a_cooldown_initial(ids=None) -> dict:
    """Les ids dont l'oracle est COURT-CIRCUITE AU TOUR 1, avec leur nombre de tours.

    `ids = None` -> tout le registre `ABILITY_CLASSES`. Le recensement est DERIVE du gameconfig a
    chaque appel : une ability qui gagnerait la constante au prochain build entre toute seule."""
    if ids is None:
        from engine.runner.abilities.handler import ABILITY_CLASSES
        ids = sorted(ABILITY_CLASSES)
    out = {}
    for aid in ids:
        n = cooldown_initial(aid)
        if n is not None and n >= 1:
            out[int(aid)] = n
    return out


def rendre_oracle_passant(rpc, rid: int, tours: int = 1) -> str:
    """Laisse passer `tours` tours complets, pour que le cooldown initial retombe et que l'oracle
    traverse.

    `rpc(method, body, timeout_ms)` est INJECTE par l'appelant : ce module ne connait ni le host ni
    la session, et reste importable offline (c'est ce qui permet au cliquet de le mesurer sans
    runner).

    LA PARADE EST DE DEBLOQUER, PAS D'EXCLURE. Ecarter les couples court-circuites laisserait les
    21 ids a `initialCooldownTurns >= 1` JAMAIS confrontes -- un zero de methode, pas un resultat.

    ⚠ UN SEUL TOUR NE SUFFIT PAS POUR TOUT LE GISEMENT, et c'est MESURE (#287-r9) : sur
    `1158 DutyEternal` (`initialCooldownTurns = 2`, porteur `ultraDreadnought`), un tour fait passer
    `abilityState.cooldown` de `2` a `1` et `casterReason` reste `ValidRequest`. Le parametre
    `tours` existe pour ca ; l'appelant le derive de `cooldown_initial(ability)`. Trois ids du
    gisement sont dans ce regime (1143, 1144, 1158). Prefere `debloquer_oracle`, qui MESURE au lieu
    de compter.

    ⚠ LE `endturn` EST REPETE jusqu'au flip de `currentPlayer`. `rl_duel.cmd_aiturn` documente le
    quirk H19 (un seul `endturn` peut ne pas rendre la main) ; sans le flip, `aiPlayByUnit` jouerait
    MA team et CASTERAIT peut-etre l'ability qu'on veut justement voir disponible -- ce qui
    re-armerait le cooldown et ferait lire l'echec comme une propriete du ciblage.

    Rend "" si la main est revenue, sinon une PHRASE qui nomme ce qui a manque (jamais un booleen
    muet : un deblocage rate doit se lire comme « pas mesure », pas comme un refus du natif)."""
    for n in range(max(1, int(tours))):
        dec = rpc("decisionView", {"runnerId": rid}, 60000) or {}
        moi = dec.get("currentPlayer")
        if moi not in (3, 4):
            return "PAS MESURE : currentPlayer=%r (hors 3/4)" % (moi,)
        adverse = 4 if moi == 3 else 3
        for _ in range(3):
            rpc("applyAction", {"runnerId": rid, "action": {"kind": "endturn"}}, 30000)
            if (rpc("decisionView", {"runnerId": rid}, 60000) or {}).get("currentPlayer") == adverse:
                break
        else:
            return "PAS MESURE : la main n'est jamais passee a l'adversaire (quirk H19, tour %d)" % n
        r = rpc("aiPlayByUnit", {"runnerId": rid, "maxTurns": 1, "maxActivations": 9999},
                180000) or {}
        if not r.get("ok"):
            return "PAS MESURE : tour adverse KO au tour %d (%s)" % (n, r.get("error"))
        cp = (rpc("decisionView", {"runnerId": rid}, 60000) or {}).get("currentPlayer")
        if cp != moi:
            return "PAS MESURE : la main n'est pas revenue au tour %d (currentPlayer=%r)" % (n, cp)
    return ""


def cycler_sans_ia(rpc, rid: int, max_endturns: int = 8) -> str:
    """Passe UN tour complet en `endturn` SEULS -- l'adversaire ne joue pas.

    POURQUOI CETTE VARIANTE EXISTE, et pourquoi elle n'est pas un raccourci : `rendre_oracle_passant`
    fait jouer le tour adverse par `aiPlayByUnit`, ce qui DEPLACE les unites. Sur un montage
    GEOMETRIQUE -- une cible encerclee, deux camps places au hexagone pres -- ce tour d'IA detruit
    exactement la configuration que le probe vient d'etablir, et la mesure suivante porterait sur
    autre chose. Les runners de ces probes sont batis `--no-ai` : `endturn` cede la main, un second
    `endturn` la rend, personne n'a bouge.

    ⚠ Ce n'est PAS interchangeable avec `rendre_oracle_passant` : la ou l'etat de l'ADVERSAIRE
    compte (une regle dynamique qui lit ce qu'il a fait), c'est l'autre qu'il faut. Ici on ne veut
    QUE le passage de tour.

    Rend "" si la main est revenue, sinon une PHRASE."""
    dec = rpc("decisionView", {"runnerId": rid}, 60000) or {}
    moi = dec.get("currentPlayer")
    if moi not in (3, 4):
        return "PAS MESURE : currentPlayer=%r (hors 3/4)" % (moi,)
    parti = False
    for _ in range(max(2, int(max_endturns))):
        rpc("applyAction", {"runnerId": rid, "action": {"kind": "endturn"}}, 30000)
        cp = (rpc("decisionView", {"runnerId": rid}, 60000) or {}).get("currentPlayer")
        if not parti:
            parti = cp != moi
        elif cp == moi:
            return ""
    return ("PAS MESURE : la main n'est pas revenue en %d `endturn` (parti=%s)"
            % (max_endturns, parti))


def debloquer_oracle(rpc, rid: int, caster_id: int, ability_type, max_tours: int = 4,
                     jouer_adverse: bool = True) -> str:
    """Fait passer des tours JUSQU'A ce que `casterReason` tombe a `0` pour CE couple -- et le VERIFIE.

    C'est le foyer que les consommateurs doivent appeler. Il differe de `rendre_oracle_passant` sur
    le point qui a fait tomber une mesure de #287-r9 : il ne COMPTE pas des tours, il MESURE le
    resultat. Deux consequences :

      * il couvre les cooldowns initiaux de N'IMPORTE QUELLE longueur sans que l'appelant ait a
        connaitre la constante (`1158` en demande deux, `1143` aussi) ;
      * il couvre les AUTRES causes de court-circuit -- `*(int*)(ability+0x44) == 0`,
        `IsDamagedMachine && !IsMachinePrimaryAbilityType`, cooldown ACQUIS apres un cast -- que
        `abilityState` ne publie pas : elles se manifestent par un `casterReason` qui NE TOMBE PAS,
        et la phrase rendue le dit au lieu de laisser croire a un refus de ciblage.

    `jouer_adverse=False` passe les tours en `endturn` SEULS (`cycler_sans_ia`) : a reserver aux
    montages GEOMETRIQUES, ou faire jouer l'IA adverse detruirait la configuration etablie.

    Rend "" si l'oracle est devenu passant (ou l'etait deja), sinon une PHRASE qui nomme l'etat
    atteint. ⚠ NE JAMAIS rabattre cette phrase sur un « refus du natif » : c'est une NON-MESURE."""
    def _caster():
        r = rpc("abilityReason", {"runnerId": rid, "casterId": int(caster_id),
                                  "abilityType": int(ability_type)}, 60000) or {}
        return _hex_de(r.get("casterReason")), r

    code, rep = _caster()
    if code == 0:
        return ""
    for n in range(max(1, int(max_tours))):
        empeche = (rendre_oracle_passant(rpc, rid, tours=1) if jouer_adverse
                   else cycler_sans_ia(rpc, rid))
        if empeche:
            return empeche
        code, rep = _caster()
        if code == 0:
            return ""
    return ("PAS MESURE : l'oracle reste court-circuite apres %d tour(s) -- casterReason=%s, %s"
            % (max_tours, code, cause_du_court_circuit(rep)))
