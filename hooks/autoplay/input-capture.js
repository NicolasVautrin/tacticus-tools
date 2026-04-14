// hook: Input capture — tap-to-select units/tiles on the board
// requires: _utils/il2cpp-helpers, _utils/il2cpp-serializer, _utils/matchstate-reader

// --- Hook HandleMouseButtonUpThisFrame ---
// ARM64 ABI: Vector3 (HFA, 3 floats) goes in float regs, not integer regs.
// So: args[0]=this, args[1]=entityHit, args[2]=tileHit, args[3]=MethodInfo*
hook("Assembly-CSharp.dll", "IdunBattle.View.FSM", "UnitSelectionFsm", "HandleMouseButtonUpThisFrame", {
    onEnter: function(args) {
        try {
            var entityHit = args[1];
            var tileHit = args[2];

            var tap = {};
            if (!entityHit.isNull()) tap.entity = serialize(entityHit, 4);
            if (!tileHit.isNull()) tap.tile = serialize(tileHit, 4);

            send({t: "tap", tap: tap});
        } catch(e) {
            send({t: "tap", error: e.message});
        }
    }
});

console.log("[*] Input capture loaded");