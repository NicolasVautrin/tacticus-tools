// runner-signal — ATTENDRE QU'UNE BATAILLE EXISTE, PAR SIGNAL, jamais par sondage.
//
// LE BESOIN. `sandbox_campagne.py` rend la main AVANT que la bataille soit montee -- son propre
// message le dit (<< l'APPEL est passe -- ca ne dit RIEN du montage >>). L'appelant doit donc
// attendre le fait. Il le faisait en sondant `sandboxProbe` toutes les secondes, ce qui est un
// minuteur deguise : latence jusqu'a une seconde, et un plafond qu'on choisit au doigt.
//
// LE SIGNAL EXISTE DEJA, IL N'ETAIT PAS EXPOSE. La pompe principale VOIT la transition
// `IdunGameViews._runner : null -> r` -- c'est elle qui installe les hooks du runner vivant.
// Il suffisait de compter ces transitions et de reveiller ceux qui les attendent.
//
// (!)LE COMPTEUR N'EST PAS UN LUXE, IL FERME UNE COURSE. Entre le geste qui monte la bataille
// et l'appel qui l'attend, la transition peut DEJA avoir eu lieu -- et c'est le cas le plus
// frequent, puisque le montage est rapide. Un pur push la manquerait et attendrait le plafond
// entier avant de rendre un echec sur un montage REUSSI. L'appelant lit donc la generation
// AVANT de monter et la repasse : si elle a bouge, on rend la main immediatement.
// C'est le meme cran que `ecouterTransitions.attendre(pred, plafond, depuis)` de
// `ui-windows.ts`, dont ce module est la transposition au runner.
//
// ⚠ CE MODULE N'ANCRE RIEN. Il n'existe que par ce que la pompe lui pousse : aucun
// `Interceptor`, aucun cout quand personne n'attend.

import { Ctx } from "../controller.js";

/** Nombre de transitions `null -> runner` vues depuis l'inject. Monotone. */
let generation = 0;
const reveils = new Set<() => void>();

/** Appele PAR LA POMPE, sur la transition vers un runner vivant. */
export function signalerRunnerVivant(): void {
    generation += 1;
    for (const r of [...reveils]) {
        try { r(); } catch { /* un reveil ne doit jamais casser la frame */ }
    }
}

export function generationCourante(): number {
    return generation;
}

export function register(ctx: Ctx): void {
    /** La generation COURANTE, a lire AVANT le montage. */
    ctx.rpc.runnerGeneration = (): unknown => ({ ok: true, generation });

    /**
     * Rend la main quand une bataille NEUVE existe -- par signal.
     *
     * `depuis` : la generation lue avant le montage. Si elle a deja bouge, on rend
     * IMMEDIATEMENT (la course est fermee). Sinon on dort jusqu'au push.
     *
     * ⚠ `atteint: false` = LE PLAFOND, pas << pas de bataille >>. L'appelant doit distinguer
     * les deux : un plafond dit que le montage n'a rien produit DANS CE DELAI, ce qui n'est pas
     * la meme chose qu'un montage refuse.
     */
    ctx.rpc.attendreRunner = (args?: { depuis?: number; plafondMs?: number }) => {
        const depuis = typeof args?.depuis === "number" ? args.depuis : generation;
        const plafond = typeof args?.plafondMs === "number" ? args.plafondMs : 60000;
        return new Promise((resolve) => {
            let fini = false;
            let minuteur: ReturnType<typeof setTimeout> | null = null;
            const terminer = (atteint: boolean): void => {
                if (fini) return;
                fini = true;
                reveils.delete(examiner);
                if (minuteur !== null) clearTimeout(minuteur);
                resolve({ ok: true, atteint, generation, depuis,
                          note: atteint ? "transition vers un runner vivant VUE"
                              : "PLAFOND atteint -- ce n'est PAS « aucune bataille », c'est "
                                + "« rien n'est apparu dans ce delai »" });
            };
            const examiner = (): void => { if (generation > depuis) terminer(true); };
            reveils.add(examiner);
            // LE BALAYAGE PREALABLE ferme la course : la transition a pu avoir lieu entre le
            // montage et cet appel. Sans lui, le cas le plus FREQUENT serait aussi celui qu'on
            // manque, et on rendrait un echec sur un montage reussi.
            examiner();
            if (!fini) minuteur = setTimeout(() => terminer(false), plafond);
        });
    };
}
