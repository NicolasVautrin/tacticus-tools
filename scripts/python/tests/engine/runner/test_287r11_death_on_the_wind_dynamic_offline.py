"""#287-r11 -- la regle dynamique de `1213 DeathOnTheWind`, et la PREMISSE PERIMEE qui la bloquait.

Le residu declarait `BLOCAGE: seeding` : « `UnitComponent.times_attacked_this_turn` n'est PAS seede
par `load_state` (le RPC ne l'expose pas) », et en tirait qu'un port refuserait des cibles que le
natif ACCEPTE. RE-MESURE (2026-08-15) : le canal EXISTE
(`frida/hooks/features/ai-step/rpc-snapshot.ts` publie `actorStats.attacksReceivedThisTurn`, soit
`ActorStatisticsComponent+0x38`) et `snapshot.py` le seede depuis #287-r5-r2. Le << point d'ancrage
a hooker >> que la fiche reclamait etait DEJA POSE ; il ne restait que le mirror.

Ce que ce fichier garde :

  1. **LE MIRROR EST AU BON NIVEAU** -- une SURCHARGE de la classe, ce que le natif fait
     (`DeathOnTheWindAbility$$GetDynamicInvalidTargetReason` est un corps propre, pas le
     `return 0` de la base). Sans elle, `get_invalid_target_reason` rend `0` : gate PERMISSIF.
  2. **LE COMPTEUR LU EST `+0x38`, PAS `+0x34`.** `times_attacked_this_turn` est per-TOUR ;
     `total_times_attacked` est le cumul de BATAILLE. Les confondre rendrait la regle vraie des le
     2e tour pour toute unite deja touchee une fois -- une erreur INVISIBLE au premier tour.
  3. **LE SEEDING EST LE FAIT MESURE QUI DEBLOQUE**, et il est garde ici : la cle
     `attacksReceivedThisTurn` d'`actorStats` doit atterrir dans `times_attacked_this_turn`.
  4. **LA CIBLE EST RESOLUE PAR `GetUnit`**, pas prise telle quelle : le masque de 1213 est
     TILE-targeting, donc la cible est une entite-TUILE et le natif la resout en son OCCUPANT.

ASCII only.
"""
from __future__ import annotations

DECLENCHEUR = {
    "chemins": ("scripts/python/*.py", "scripts/python/**/*.py"),
    "build": False,
    "toujours": True,
    "raison": "Regle dynamique de 1213 DeathOnTheWind (#287-r11) : la surcharge au bon niveau, le "
              "compteur `+0x38` et non `+0x34`, le seeding `actorStats.attacksReceivedThisTurn` "
              "qui a rendu la premisse du residu PERIMEE, et la resolution de cible par GetUnit.",
}

import sys
from pathlib import Path

PYDIR = Path(__file__).resolve().parents[3]
if str(PYDIR) not in sys.path:
    sys.path.insert(0, str(PYDIR))

import engine.runner.abilities.targeting as T                                    # noqa: E402
from engine.entities.active_ability_type import ActiveAbilityType                # noqa: E402
from engine.runner.abilities.handler import ABILITY_CLASSES                      # noqa: E402
from engine.runner.abilities.targeting_rule import TargetingRule as TR           # noqa: E402
from engine.runner.components import OwnerComponent, PositionComponent, UnitComponent  # noqa: E402

ABILITY = int(ActiveAbilityType.DeathOnTheWind)          # 1213


class _Entity:
    def __init__(self, comps):
        self._c = {type(c): c for c in comps}

    def get_component(self, cls):
        return self._c.get(cls)


class _State:
    def __init__(self, entities):
        self.entities = entities
        self.board = None
        self.effects = None

    def get_entity(self, uid):
        return self.entities.get(uid)


def _etat(recues: int):
    """Deux unites de camps opposes ; la CIBLE (id 2) a recu `recues` attaques ce tour."""
    uc = UnitComponent("astarLysander", True)
    uc.times_attacked_this_turn = int(recues)
    return _State({1: _Entity([OwnerComponent(1, 3), UnitComponent("darkaStormSpeeder", True),
                               PositionComponent(0, 0)]),
                   2: _Entity([OwnerComponent(2, 4), uc, PositionComponent(2, 0)])})


# ========================================================== 1. LE MIRROR EXISTE ET IL EST AU NIVEAU

def test_la_surcharge_est_DECLAREE_par_la_classe_pas_heritee():
    """Le natif a un CORPS PROPRE. Cote port, `get_invalid_target_reason` consulte le delegue via
    l'instance ; une methode seulement HERITEE d'`ActiveAbility` rendrait le `return 0` de la base,
    soit exactement le gate permissif que ce port ferme. Le discriminant est `__dict__`, pas
    `getattr` -- qui remonterait la MRO et verrait toujours quelque chose."""
    assert ABILITY in ABILITY_CLASSES
    klass = ABILITY_CLASSES[ABILITY]
    assert "get_dynamic_invalid_target_reason" in klass.__dict__, \
        "surcharge ABSENTE => le port rend 0 => gate PERMISSIF, invisible en self-play"
    assert bool(int(klass.TARGETING_OPTIONS.rules) & int(TR.TargetMatchesDynamicRule)), \
        "sans le bit, la cascade n'appelle JAMAIS la regle -- le port serait ecrit pour rien"


def test_le_verdict_BASCULE_avec_le_compteur_d_attaques_RECUES():
    """`return GetNumAttacksReceivedThisTurn(unit) != 0 ? 0 : 2;` -- les deux bras, et rien d'autre."""
    klass = ABILITY_CLASSES[ABILITY]
    assert klass().get_dynamic_invalid_target_reason(_etat(0), 1, 2) == int(
        TR.TargetMatchesDynamicRule), "cible JAMAIS attaquee ce tour -> REFUS"
    assert klass().get_dynamic_invalid_target_reason(_etat(1), 1, 2) == 0
    assert klass().get_dynamic_invalid_target_reason(_etat(7), 1, 2) == 0, \
        "le natif teste `!= 0`, pas `== 1` : tout compte non nul accepte"


def test_cible_non_resolue_rend_ZERO_sans_inventer_de_refus():
    """`if (unit == null) return 0;` -- le natif le dit explicitement."""
    klass = ABILITY_CLASSES[ABILITY]
    assert klass().get_dynamic_invalid_target_reason(_etat(0), 1, None) == 0
    assert klass().get_dynamic_invalid_target_reason(_etat(0), 1, 999) == 0


def test_la_cascade_COMPLETE_relaie_bien_la_regle():
    """Le verdict doit remonter par `get_invalid_target_reason`, pas seulement par un appel direct :
    c'est la cascade qui teste le bit et invoque le delegue.

    ⚠ ON N'INTERROGE PAS AVEC LE MASQUE COMPLET DE 1213 : il porte aussi `TargetIsTile` et
    `TargetTileHasEnemyUnit`, deux regles evaluees AVANT la dynamique et qui exigent un board. Le
    test rendrait alors leur verdict a elles, jamais celui de la regle qu'il pretend mesurer -- un
    vert (ou un rouge) pour la mauvaise raison. On isole donc le SEUL bit qui nous concerne, en
    gardant l'instance REELLE comme porteuse du delegue."""
    from dataclasses import replace as _replace
    klass = ABILITY_CLASSES[ABILITY]
    # La classe est `__slots__` : on sous-classe plutot que d'ecrire un attribut d'instance. Le
    # delegue reste celui de 1213 -- c'est ce qu'on mesure.
    isole = type("_Isole", (klass,), {
        "TARGETING_OPTIONS": _replace(klass.TARGETING_OPTIONS,
                                      rules=int(TR.TargetMatchesDynamicRule))})
    inst_isole = isole()
    # `apply_self_cast_switch=False` : on vise la surcharge 7 arguments, celle de l'ENUMERATION.
    assert T.get_invalid_target_reason(_etat(1), 1, 2, inst_isole,
                                       apply_self_cast_switch=False) == 0
    assert T.get_invalid_target_reason(_etat(0), 1, 2, inst_isole,
                                       apply_self_cast_switch=False) == int(
        TR.TargetMatchesDynamicRule)


# ============================================= 2. LE COMPTEUR EST `+0x38`, PAS `+0x34` (piege 2)

def test_le_compteur_lu_est_PER_TOUR_et_non_le_cumul_de_BATAILLE():
    """`+0x38` (`times_attacked_this_turn`, remis a zero au turn-start) contre `+0x34`
    (`total_times_attacked`, cumul de BATAILLE). Un port qui lirait le second accepterait, des le
    2e tour, toute cible deja touchee une fois -- et resterait vert au premier tour."""
    klass = ABILITY_CLASSES[ABILITY]
    st = _etat(0)
    st.get_entity(2).get_component(UnitComponent).total_times_attacked = 9
    assert klass().get_dynamic_invalid_target_reason(st, 1, 2) == int(TR.TargetMatchesDynamicRule), \
        "cumul de BATAILLE non nul mais compteur du TOUR a zero -> le natif REFUSE"


# =========================================== 3. LE SEEDING, LE FAIT QUI A PERIME LA PREMISSE (3)

def test_le_canal_actorStats_alimente_bien_le_compteur():
    """La cle `attacksReceivedThisTurn` d'`actorStats` doit atterrir dans
    `UnitComponent.times_attacked_this_turn`. C'est CE fait qui rend le port possible : sans lui, le
    compteur resterait a son 0 de construction et la regle refuserait tout."""
    from engine.runner import snapshot as S
    src = Path(S.__file__).read_text(encoding="utf-8")
    assert '("attacksReceivedThisTurn", "times_attacked_this_turn")' in src, \
        "le seeder a disparu -- la premisse du residu redeviendrait VRAIE, et ce port FAUX"


def test_le_capteur_publie_bien_le_champ_cote_hooks():
    """Le pendant amont : le hook doit publier la cle. Un port qui lit un compteur que personne
    n'alimente est un refus FABRIQUE."""
    hook = PYDIR.parents[1] / "frida" / "hooks" / "features" / "ai-step" / "rpc-snapshot.ts"
    if not hook.exists():                       # arbre partiel : on DIT qu'on ne mesure pas
        import pytest
        pytest.skip("hook absent de cet arbre -- mesure NON FAITE, pas un vert")
    assert "attacksReceivedThisTurn" in hook.read_text(encoding="utf-8", errors="replace")


# ============================================================ 4. LA DETTE #287-r5 EST A ZERO

def test_la_dette_des_regles_dynamiques_est_RE_DERIVEE_a_zero():
    """`probe_287r5_etages_bloquants` compte les ids a surcharge NATIVE LISIBLE et sans regle portee.
    `1213` en etait le DERNIER. Le compte est re-derive du binaire, jamais cite."""
    import probe_287r5_etages_bloquants as P
    res = P.recenser()
    assert res["dette"] == [], \
        "dette non vide : %s" % ",".join(n for _a, n, _s in res["dette"])
    assert ActiveAbilityType.DeathOnTheWind not in P.ETAGE_BLOQUANT, \
        "une entree d'etage pour une regle PORTEE n'est plus jamais imprimee -- declaration muette"
