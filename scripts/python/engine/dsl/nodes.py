"""Compat : `dsl.nodes.X` reste valide apres le split. Le code vit dans
base/arithmetic/predicates/selectors/accessors ; ce module re-exporte tout.
"""
from .base import *  # noqa: F401,F403
from .base import (  # noqa: F401
    Node, DslContext, Const, _pos, _within, _round_fix64, _c_mod, _same_entity,
    _units_of, _effect_field, _is_alive, _default_get_stat,
)
from .arithmetic import *  # noqa: F401,F403
from .predicates import *  # noqa: F401,F403
from .selectors import *  # noqa: F401,F403
from .accessors import *  # noqa: F401,F403
