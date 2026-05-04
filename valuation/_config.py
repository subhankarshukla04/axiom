import json
import os
from typing import Dict, Optional, Tuple

_CONFIG_DIR = os.path.join(os.path.dirname(__file__), 'config')


def _load(filename: str) -> dict:
    with open(os.path.join(_CONFIG_DIR, filename)) as f:
        return json.load(f)


_tags_raw   = _load('subsector_tags.json')
_mults_raw  = _load('subsector_multiples.json')
_tgrowth_raw = _load('terminal_growth.json')
_capex_raw  = _load('capex_norms.json')
_bank_raw   = _load('bank_multiples.json')
_reit_raw   = _load('reit_multiples.json')
_blend_raw  = _load('blend_weights.json')

TICKER_TAG_MAP: Dict[str, str] = _tags_raw

SUBSECTOR_MULT: Dict[str, Tuple] = {
    tag: (v[0], v[1], v[2])
    for tag, v in _mults_raw['multiples'].items()
}

CYCLICAL_TAGS = frozenset(_mults_raw['cyclical_tags'])
SECULAR_DECLINE_TAGS = frozenset(_mults_raw['secular_decline_tags'])

TERMINAL_GROWTH_BY_TAG: Dict[str, float] = _tgrowth_raw['rates']
TERMINAL_GROWTH_DEFAULT: float = _tgrowth_raw['default']

SECTOR_CAPEX_NORM: Dict[str, float] = _capex_raw['norms']
CAPEX_NORM_DEFAULT: float = _capex_raw['default']

SECTOR_PB: Dict[str, float] = _bank_raw['sector_pb']
TICKER_PB: Dict[str, float] = _bank_raw['ticker_pb']

SECTOR_PFFO: Dict[str, float] = _reit_raw['sector_pffo']
TICKER_PFFO: Dict[str, float] = _reit_raw['ticker_pffo']

BLEND_WEIGHTS: Dict[str, Dict[str, float]] = _blend_raw
