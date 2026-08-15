"""#301 -- MONTAGE NOMME : sur le vecteur MORT, quel canal `AbilityEntities` porte le declencheur ?

    `CurrentAbility`    = `AbilityEntities+0x60` -> `state.triggering_ability`   (nom historique)
    `TriggeringAbility` = `AbilityEntities+0x98` -> `state.trigger_ability_type` (#294)

--------------------------------------------------------------------------- LE FAIT NATIF

`IdunBattle.Operations.KillUnitOperation$$Execute` batit UN SEUL `AbilityEntities` (value type de
0x128 octets = les 312 octets boxes de `classes.tsv` moins l'en-tete) et le publie CINQ fois sans
plus jamais le toucher. Sequence LUE au decompile (build `rnca9r7q6c`) :

    memset(&entities, 0, 0x128)                 -> TOUS les champs a zero, dont `+0x60` et `+0x7c`
    +0x00 = +0x08 = killer ; +0x10 = killed
    +0x38 = Tiles(killed) ; +0x48 = Tiles(killer)
    +0x98..+0xb4 = les 0x1c octets de `KillUnitOptions+0x04`         <-- TriggeringAbility
    ... puis, dans cet ordre, cinq copies de la struct suivies de :
        Publish(..., 1)      On(PreUnitDeath)
        Publish(..., 2)      On(PreUnitDeath_2)
        Publish(..., 0)      On(UnitDeath)
        Publish(..., 0x36)   On(UnitDefeated  = 54)
        Publish(..., 0x35)   On(PostUnitKill  = 53)

Les deux lecteurs sont des copies plates a offset FIXE, ce qui identifie les champs sans ambiguite :

    AbilityTypeSelector.CurrentAbilitySelector$$Select      lit +0x60 / +0x68 / +0x70 / +0x78
    AbilityTypeSelector.TriggeringAbilitySelector$$Select   lit +0x98 / +0xa0 / +0xa8 / +0xb0

=> sur les cinq evenements de mort : `CurrentAbilityIs` est TOUJOURS faux, et c'est
`TriggeringAbilityIs` / `TriggeringEffectIs` / `TriggeringAbilityIsNone` qui voient le declencheur.

CHAINE DE LA VALEUR, re-derivee de bout en bout (aucun maillon suppose) :

    IdunBattle.Core.MatchState$$AddDeath(this, killer, killed, killTrigger, attackTrigger,
                                         AttackRangeType)
        -> enqueue { +0x00 killerId, +0x04 killedId, +0x08..+0x24 killTrigger (0x1c octets),
                     +0x24..+0x40 attackTrigger, +0x40 AttackRangeType }
    IdunBattle.Messages.InputMessageProcessor.u003Cu003Ec__DisplayClass49_0$$u003CVerifyDeathsu003Eb__0
        -> options = IdunBattle.Operations.KillUnitOperationOptions$$ForDefault()
           puis ECRASE options[0x04..0x20) avec le killTrigger de l'entree, et RIEN d'autre
    Core.Services.OperationProcessor$$KillUnit  -> recopie les 0x48 octets d'options tels quels
    IdunBattle.Operations.KillUnitOperation$$Execute -> +0x98..+0xb4 = options[0x04..0x20)

=> `AbilityEntities+0x98` EST le `killTrigger` porte par l'entree de file.

------------------------------------------------------------------------- CE QUE LE PORT FAISAIT

`operations/damage.py::_verify_deaths` reposait le `killTrigger` sur `state.triggering_ability`
(le canal `+0x60`) et laissait `state.trigger_ability_type` (`+0x98`) vide -- l'INVERSE du natif.
Degradation PERMISSIVE, donc invisible : un `CurrentAbilityIs` voyait une valeur la ou le natif
n'en publie aucune, et les gates `Triggering*Is` du vecteur mort lisaient le mauvais canal.

--------------------------------------------------------------------------- LE MONTAGE (`death`)

Un `State` nu (OFFLINE, deterministe, zero RNG, zero runner). Deux triggered-abilities espionnes
enregistrees sur le vecteur mort, plus une file de morts amorcee avec un `killTrigger` connu :

    K  On(1 = PreUnitDeath)   id = None    -- pur observateur : releve (`+0x60`, `+0x98`) dans
                                              `matches` ET dans `execute_behaviour`
    N  On(2 = PreUnitDeath_2) id = N_ID    -- porte un id : etablit que `+0x60` redevient NON VIDE
                                              pendant SON behaviour (ecriture de
                                              `BaseTriggeredAbility$$Execute`) alors que `+0x98`
                                              garde le killTrigger -> DEUX NON-NULS DIFFERENTS

Deroule NATIF attendu, et ce que chaque etage etablit :

  | site      | +0x60 (`triggering_ability`) | +0x98 (`trigger_ability_type`) | etablit                      |
  |-----------|------------------------------|--------------------------------|------------------------------|
  | K.matches | **None**                     | **KILL_TRIGGER**               | le memset ET le bloc +0x98   |
  | K.exec    | None                         | KILL_TRIGGER                   | idem, cote behaviour         |
  | N.matches | None                         | KILL_TRIGGER                   | idem sur un 2e event         |
  | N.exec    | **N_ID**                     | **KILL_TRIGGER**               | SEPARATION, DEUX NON-NULS    |
  | final     | AMBIENT                      | None                           | les deux restaures           |

`AMBIENT` = la valeur de `+0x60` AVANT le drain : le port n'a qu'un canal global, il le restaure.

--------------------------------------------------------------- CONTRE-EPREUVES (`--mutate`)

Chacune neutralise UNE moitie du fix et doit faire ROUGIR le montage :

  `legacy`  l'etat AVANT #301 : `+0x60 = killTrigger`, `+0x98` laisse vide -> K voit (KT, None)
  `both`    pose le killTrigger sur les DEUX canaux -> K voit (KT, KT) : `CurrentAbilityIs`
            redevient satisfiable sur la mort, ce que le memset natif interdit
  `nowipe`  pose bien `+0x98` mais ne remet PAS `+0x60` a None -> l'ambiant FUIT dans la mort
  `persist` supprime la restauration de `+0x98` -> le killTrigger fuit APRES le drain

Reproduire :

    cd scripts/python
    python probe_301_kill_unit_trigger_channels.py
    python probe_301_kill_unit_trigger_channels.py --mutate legacy
    python probe_301_kill_unit_trigger_channels.py --mutate both
    python probe_301_kill_unit_trigger_channels.py --mutate nowipe
    python probe_301_kill_unit_trigger_channels.py --mutate persist
"""
from __future__ import annotations

import argparse
from typing import Optional

# Ids ARBITRAIRES : le montage teste le CANAL, pas une ability reelle. Trois valeurs deux a deux
# distinctes suffisent (killTrigger, id de la triggered chainee, ambiant hors drain).
KILL_TRIGGER = 5151
N_ID = 5252
AMBIENT = 5353

MUTATIONS = ("legacy", "both", "nowipe", "persist")


def _snapshot(state) -> tuple:
    """(`+0x60`, `+0x98`) tels que les verrait un noeud DSL evalue ICI."""
    return (getattr(state, "triggering_ability", None),
            getattr(state, "trigger_ability_type", None))


def _patched_verify_deaths(mutate: Optional[str]):
    """Rend un remplacant de `AttackDamageOperation._verify_deaths` qui applique la mutation.

    On reecrit le DRAIN ENTIER plutot que de patcher un attribut, parce que c'est precisement le
    couple (ce qu'on pose sur `+0x60`, ce qu'on pose sur `+0x98`) qui est sous test."""
    from engine.runner.operations.damage import AttackDamageOperation

    def _drain(state):
        if state.draining_deaths:
            return []
        state.draining_deaths = True
        saved_current = state.triggering_ability
        saved_trigger = state.trigger_ability_type
        out: list = []
        try:
            while state.pending_deaths:
                # #951-r1 : l'entree porte un 5e champ (`KillUnitOptions+0x3c`). Ce probe ne
                # mesure que les DEUX canaux d'ability -- il depile large plutot que d'imposer
                # une arite, pour rester jouable sur les deux formes de file.
                _entry = state.pending_deaths.pop(0)
                dying_id, killer_id, overkill, kill_trigger = _entry[:4]
                if mutate == "legacy":                 # l'etat AVANT #301
                    state.triggering_ability = kill_trigger
                elif mutate == "both":                 # les deux canaux alimentes
                    state.triggering_ability = kill_trigger
                    state.trigger_ability_type = kill_trigger
                elif mutate == "nowipe":               # `+0x98` bon, `+0x60` non efface
                    state.trigger_ability_type = kill_trigger
                else:                                  # nominal / persist
                    state.triggering_ability = None
                    state.trigger_ability_type = kill_trigger
                out = out + (AttackDamageOperation._kill_unit_operation(
                    state, dying_id, killer_id, overkill) or [])
        finally:
            state.triggering_ability = saved_current
            if mutate != "persist":
                state.trigger_ability_type = saved_trigger
            state.draining_deaths = False
        return out
    return _drain


def run(mutate: Optional[str] = None, verbose: bool = False, real: bool = False) -> dict:
    """Monte le drain d'UNE mort et rend la TRACE ordonnee des observations.

    `real=True` : n'installe AUCUN drain de substitution -- le montage exerce le
    `AttackDamageOperation._verify_deaths` DU DEPOT. C'est le mode qui donne son ROUGE au fix :
    joue sur le code d'avant #301, il rend la trace `legacy` (`+0x60 = killTrigger`, `+0x98` vide).
    `--mutate` y est refuse (les deux modes sont exclusifs : l'un teste le code, l'autre le montage).

    Retour :
      `obs`       liste de `(site, plus0x60, plus0x98)` dans l'ordre d'evaluation
      `fires`     nb de passages par site
      `final`     (`+0x60`, `+0x98`) apres retour complet du drain
      `separated` True si un site voit deux valeurs NON NULLES DIFFERENTES
    """
    assert mutate in (None,) + MUTATIONS, "mutation inconnue : %s" % (mutate,)
    assert not (real and mutate), "--real et --mutate sont exclusifs"
    from engine.runner.state import State
    from engine.runner.components import UnitComponent, OwnerComponent
    from engine.runner.operations.triggers.base import TriggeredAbility
    from engine.dsl.event_trigger_type import EventTriggerType
    from engine.runner.operations.damage import AttackDamageOperation
    import engine.runner.operations.triggers.dispatch.core as CORE

    obs: list[tuple] = []
    fires: dict[str, int] = {}

    def _note(site: str, state) -> None:
        obs.append((site,) + _snapshot(state))
        fires[site] = fires.get(site, 0) + 1

    class _K(TriggeredAbility):
        """Observateur PUR sur `On(1 = PreUnitDeath)`. Aucun `TRIGGERED_ABILITY_ID` : il ne touche
        donc aucun canal -- il ne fait que LIRE ce que `KillUnitOperation` a publie. C'est le cas
        des 79 classes-triggers du registre qui n'ont pas d'id."""
        event_id = int(EventTriggerType.PreUnitDeath)

        def matches(self, state, ev):
            _note("K.matches", state)
            return True

        def execute_behaviour(self, state, ev):
            _note("K.exec", state)
            return {"who": "K"}

    class _N(TriggeredAbility):
        """Triggered CHAINEE sur `On(2 = PreUnitDeath_2)`, avec un id. `BaseTriggeredAbility$$Execute`
        ecrit `+0x60 = this.Id` AVANT son behaviour ; `+0x98` reste le `killTrigger` publie par
        `KillUnitOperation`. C'est le seul site du montage ou les deux canaux portent deux valeurs
        NON NULLES DIFFERENTES."""
        event_id = int(EventTriggerType.PreUnitDeath_2)
        TRIGGERED_ABILITY_ID = N_ID

        def matches(self, state, ev):
            _note("N.matches", state)
            return True

        def execute_behaviour(self, state, ev):
            _note("N.exec", state)
            return {"who": "N"}

    state = State()
    # Deux entites : le mourant (owner des espions) et son tueur. Le gate d'owner vivant de
    # `evaluate_trigger_operation` impose un porteur VIVANT -> on met les espions sur le TUEUR.
    dying = state.add_entity(1)
    dying.add_component(UnitComponent("probe301Dying", False))   # deja mort : on DRAINE, on ne tue pas
    dying.add_component(OwnerComponent(team=2))
    killer = state.add_entity(2)
    killer.add_component(UnitComponent("probe301Killer", True))
    killer.add_component(OwnerComponent(team=1))

    saved_collect = CORE.collect_triggered_abilities
    CORE.collect_triggered_abilities = lambda st: [_K(2), _N(2)]
    saved_drain = AttackDamageOperation._verify_deaths
    if not real:
        AttackDamageOperation._verify_deaths = staticmethod(_patched_verify_deaths(mutate))
    try:
        # L'AMBIANT hors drain : ce que `+0x60` vaut AVANT (une triggered englobante, p.ex.).
        state.triggering_ability = AMBIENT
        # `MatchState$$AddDeath` : (dying, killer, overkill, killTrigger).
        state.pending_deaths.append((1, 2, False, KILL_TRIGGER))
        AttackDamageOperation._verify_deaths(state)
        final = _snapshot(state)
    finally:
        CORE.collect_triggered_abilities = saved_collect
        AttackDamageOperation._verify_deaths = saved_drain

    separated = any(a is not None and b is not None and a != b for _, a, b in obs)
    res = {"obs": obs, "fires": fires, "final": final, "separated": separated,
           "mutate": mutate, "real": real}
    if verbose:
        print("site           +0x60        +0x98")
        for site, a, b in obs:
            print("%-14s %-12s %s" % (site, a, b))
        print("%-14s %-12s %s" % ("final", final[0], final[1]))
    return res


def site(res: dict, name: str) -> tuple:
    """La PREMIERE observation `(+0x60, +0x98)` faite au site `name`. Leve si le site n'a pas ete
    atteint -- un site absent est un montage qui ne s'est pas monte, jamais un « rien a signaler »."""
    for s, a, b in res["obs"]:
        if s == name:
            return (a, b)
    raise AssertionError("site '%s' non atteint ; sites observes = %s"
                         % (name, sorted({s for s, _, _ in res["obs"]})))


def verdict(res: dict) -> tuple:
    """(ok, message). Les CINQ faits que le montage doit etablir, chacun nomme."""
    obs = res["obs"]
    by_site = {}
    for site, a, b in obs:
        by_site.setdefault(site, []).append((a, b))
    for site in ("K.matches", "K.exec", "N.matches", "N.exec"):
        if site not in by_site:
            return (False, "ROUGE -- site '%s' non atteint ; sites observes = %s"
                    % (site, sorted(by_site)))
    # 1 : le bloc `+0x98..+0xb4 = KillUnitOptions+0x04` -- le killTrigger EST publie, et sur ce
    #     canal-la. Teste EN PREMIER pour que `legacy` (qui laisse `+0x98` vide) ait sa signature
    #     propre, distincte de `both` (qui alimente les deux).
    for site in ("K.matches", "K.exec", "N.matches", "N.exec"):
        got = by_site[site][0]
        if got[1] != KILL_TRIGGER:
            return (False, "ROUGE -- '%s' voit +0x98 = %s ; attendu le killTrigger %s "
                           "(bloc AbilityEntities+0x98..+0xb4 = KillUnitOptions+0x04)"
                    % (site, got[1], KILL_TRIGGER))
    # 2 : le memset -- `+0x60` VIDE sur les evenements de mort, pour un trigger SANS id.
    for site in ("K.matches", "K.exec", "N.matches"):
        got = by_site[site][0]
        if got[0] is not None:
            return (False, "ROUGE -- '%s' voit +0x60 = %s ; le memset de KillUnitOperation "
                           "l'exige VIDE (attendu None)" % (site, got[0]))
    # 3 : la SEPARATION -- deux non-nuls differents pendant le behaviour de la triggered chainee.
    got = by_site["N.exec"][0]
    if got != (N_ID, KILL_TRIGGER):
        return (False, "ROUGE -- 'N.exec' = %s ; attendu (%s, %s) : `BaseTriggeredAbility$$Execute` "
                       "ecrit +0x60 alors que +0x98 garde le killTrigger"
                % (got, N_ID, KILL_TRIGGER))
    if not res["separated"]:
        return (False, "ROUGE -- aucun site ne separe les canaux (deux non-nuls differents)")
    # 4 : restauration des DEUX canaux en sortie de drain.
    if res["final"] != (AMBIENT, None):
        return (False, "ROUGE -- final = %s ; attendu (%s, None) : les deux canaux doivent etre "
                       "restaures a leur valeur d'avant le drain" % (res["final"], AMBIENT))
    return (True, "VERT -- +0x60 vide sur la mort, +0x98 = killTrigger, separation vue a N.exec, "
                  "les deux canaux restaures")


def run_live(seed: str = "777", hp: str = "1200", k: int = 2, verbose: bool = True) -> dict:
    """LE REGIME EST-IL ATTEINT EN BATAILLE REELLE ? Espionne les deux canaux a l'entree de CHAQUE
    `KillUnitOperation` d'un montage LIVE, et rend la liste des morts observees.

    Le montage reutilise `probe_220_haze_bonded_chain` (Maladus / chaine de transferts 1077, board et
    seed de `case-haze-bonded`), parce que c'est le seul montage porte qui produise un `killTrigger`
    NON NUL : les relais y meurent DANS le behaviour de `HazeOfCorruptionDamageTransferTrigger`
    (`TRIGGERED_ABILITY_ID = 0x435`), donc leur entree de file porte 0x435.

    Sans ce controle, la garde offline resterait suspendue en l'air : elle prouverait « quand un
    killTrigger existe, il passe par `+0x98` », sans jamais etablir qu'un killTrigger EXISTE. Ce
    mode-ci l'etablit sur du live, et c'est aussi lui qui verifie que `+0x60` reste VIDE la ou le
    natif ne publie rien -- y compris pour les morts a killTrigger nul.

    Retour : `deaths` = [(dying_id, killTrigger vu en +0x98, valeur vue en +0x60)], `rc` = code de
    sortie du probe 220 (0 = ses propres accords PV/RNG tiennent)."""
    import sys
    from engine.runner.operations.damage import AttackDamageOperation
    import probe_220_haze_bonded_chain as P220

    deaths: list[tuple] = []
    orig = AttackDamageOperation._kill_unit_operation

    def _spy(state, target_id, attacker_id, overkill):
        deaths.append((int(target_id), state.trigger_ability_type, state.triggering_ability))
        return orig(state, target_id, attacker_id, overkill)

    AttackDamageOperation._kill_unit_operation = staticmethod(_spy)
    saved_argv = sys.argv
    sys.argv = ["probe_220_haze_bonded_chain.py", "--seeds", str(seed),
                "--hp", str(hp), "--k", str(k)]
    try:
        rc = P220.main()
    finally:
        AttackDamageOperation._kill_unit_operation = staticmethod(orig)
        sys.argv = saved_argv

    with_trigger = [d for d in deaths if d[1] is not None]
    leaked = [d for d in deaths if d[2] is not None]
    res = {"deaths": deaths, "with_trigger": with_trigger, "leaked": leaked, "rc": rc}
    if verbose:
        print()
        print("[301-live] morts drainees (dying, +0x98, +0x60) = %s" % (deaths,))
        print("[301-live] dont killTrigger NON NUL : %d / %d" % (len(with_trigger), len(deaths)))
        if leaked:
            print("[301-live] ROUGE -- +0x60 NON VIDE sur %d mort(s) : %s" % (len(leaked), leaked))
        elif not with_trigger:
            print("[301-live] ROUGE -- regime NON ATTEINT : aucune mort ne porte de killTrigger, "
                  "le montage ne prouve rien sur le canal +0x98")
        else:
            print("[301-live] VERT -- regime ATTEINT (%d mort(s) a killTrigger non nul) et +0x60 "
                  "VIDE sur les %d morts" % (len(with_trigger), len(deaths)))
    return res


def main() -> int:
    ap = argparse.ArgumentParser(description="#301 : canaux d'ability du vecteur MORT")
    ap.add_argument("--mutate", choices=MUTATIONS, default=None)
    ap.add_argument("--real", action="store_true",
                    help="exerce le _verify_deaths DU DEPOT (aucun drain de substitution)")
    ap.add_argument("--live", action="store_true",
                    help="mesure LIVE : le regime « killTrigger non nul » est-il atteint en bataille ?")
    ap.add_argument("--seed", default="777")
    ap.add_argument("--hp", default="1200")
    ap.add_argument("--k", type=int, default=2)
    ap.add_argument("--quiet", action="store_true")
    a = ap.parse_args()
    if a.live:
        r = run_live(seed=a.seed, hp=a.hp, k=a.k, verbose=True)
        if r["leaked"] or not r["with_trigger"]:
            return 1
        return 0 if r["rc"] == 0 else 1
    res = run(a.mutate, verbose=not a.quiet, real=a.real)
    ok, msg = verdict(res)
    print("[301] mutate=%s real=%s : %s" % (a.mutate or "-", a.real, msg))
    if a.mutate is None:
        return 0 if ok else 1
    # Une contre-epreuve DOIT rougir : un vert y est l'echec.
    if ok:
        print("[301] ANTI-CONTRE-EPREUVE : la mutation '%s' n'a RIEN casse -- "
              "le montage ne discrimine pas." % a.mutate)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
