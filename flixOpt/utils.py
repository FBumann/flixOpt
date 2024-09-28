# -*- coding: utf-8 -*-
"""
Created on Thu Nov 12 13:13:31 2020
developed by Felix Panitz* and Peter Stange*
* at Chair of Building Energy Systems and Heat Supply, Technische Universität Dresden
"""

# TODO: as_vector() -> int32 Vektoren möglich machen
import logging
from typing import Union, List, Optional, Dict, Literal

import numpy as np
import math  # für nan

from flixOpt.interface import TimeSeriesRaw
from flixOpt.core import Numeric, Skalar

logger = logging.getLogger('flixOpt')


def as_vector(value: Union[int, float, np.ndarray, List], length: int) -> np.ndarray:
    '''
    Macht aus Skalar einen Vektor. Vektor bleibt Vektor.
    -> Idee dahinter: Aufruf aus abgespeichertem Vektor schneller, als für jede i-te Gleichung zu Checken ob Vektor oder Skalar)

    Parameters
    ----------

    aValue: skalar, list, np.array
    aLen  : skalar
    '''
    # dtype = 'float64' # -> muss mit übergeben werden, sonst entstehen evtl. int32 Reihen (dort ist kein +/-inf möglich)

    # Wenn Skalar oder None, return directly as array
    if value is None:
        return np.array([None] * length)
    if np.isscalar(value):
        return np.ones(length) * value

    if len(value) != length:   # Wenn Vektor nicht richtige Länge
        raise Exception(f'error in changing to {length=}; vector has already {length=}')

    if isinstance(value, np.ndarray):
        return value
    else:
        return np.array(value)


def zero_to_nan(vector: np.ndarray) -> np.ndarray:
    # changes zeros to Nans in Vector:
    nan_vector = vector.astype(float)  # Binär ist erstmal int8-Vektor, Nan gibt es da aber nicht
    nan_vector[nan_vector == 0] = math.nan
    return nan_vector


def check_bounds(value: Union[int, float, np.ndarray, TimeSeriesRaw],
                 label: str,
                 lower_bound: Numeric,
                 upper_bound: Numeric):
    if isinstance(value, TimeSeriesRaw):
        value = value.value
    if np.any(value < lower_bound):
        raise Exception(f'{label} is below its {lower_bound=}!')
    if np.any(value >= upper_bound):
        raise Exception(f'{label} is above its {upper_bound=}!')


def check_name_for_conformity(label: str) -> str:
    if label.startswith('_') or label.endswith('_') or '__' in label:
        raise ValueError(f'{label} is an invalid name! Leading and trailing underscores are forbidden, '
                         f'as well as double underscores. Use "-" or " " instead')
    return label


def check_exists(exists: Union[int, list, np.ndarray])-> Union[int, list,np.ndarray]:
    # type checking for argument "exist"
    if np.all(np.isin(exists, [0, 1])):
        return exists
    else:
        raise ValueError(f"Argument 'exists' must be int, list or np.ndarray with values 0 or 1")


class InfiniteFullSet(object):
    def __and__(self, item):  # left operand of &
        return item

    def __rand__(self, item):  # right operand of &
        return item

    def __str__(self):
        return ('<InfiniteFullSet>')


def is_number(number_alias: Union[Skalar, str]):
    """ Returns True is string is a number. """
    try:
        float(number_alias)
        return True
    except ValueError:
        return False


def get_time_series_with_end(time_series: np.ndarray[np.datetime64],
                             dt_last: Optional[np.timedelta64] = None):
    #TODO: Migrate to single usage
    ## letzten Zeitpunkt hinzufügen:
    if dt_last is None:
        dt_last = time_series[-1] - time_series[-2]
    t_end = time_series[-1] + dt_last
    return np.append(time_series, t_end)


def check_time_series(label: str,
                      time_series: np.ndarray[np.datetime64]):
    # check sowohl für globale Zeitreihe, als auch für chosenIndexe:

    # Zeitdifferenz:
    #              zweites bis Letztes            - erstes bis Vorletztes
    dt = time_series[1:] - time_series[0:-1]
    # dt_in_hours    = dt.total_seconds() / 3600
    dt_in_hours = dt / np.timedelta64(1, 'h')

    # unterschiedliche dt:
    if np.max(dt_in_hours) - np.min(dt_in_hours) != 0:
        logger.warning(f'{label}: !! Achtung !! unterschiedliche delta_t von {min(dt)} h bis  {max(dt)} h')
    # negative dt:
    if np.min(dt_in_hours) < 0:
        raise Exception(label + ': Zeitreihe besitzt Zurücksprünge - vermutlich Zeitumstellung nicht beseitigt!')


def printDictAndList(aDictOrList) -> str:
    import yaml
    return yaml.dump(aDictOrList,
                    default_flow_style=False,
                    width=1000,  # verhindern von zusätzlichen Zeilenumbrüchen
                    allow_unicode=True)


def get_max_value(*args: Union[Numeric, List[Skalar]]) -> Skalar:
    """Get the maximum value from multiple values, lists, or arrays of values."""
    return merge_to_array(*args).max()


def get_min_value(*args: Union[Numeric, List[Skalar]]) -> Skalar:
    """Get the minimum value from multiple values, lists, or arrays of values."""
    return merge_to_array(*args).min()


def merge_to_array(*args: Union[Numeric, List[Skalar]]) -> np.ndarray:
    """Merge multiple values to a single array"""
    return np.concatenate([np.array(arg).ravel() for arg in args])


def apply_formating(data_dict: Dict[str, Union[int, float]],
                    key_format: str = "<17",
                    value_format: str = ">10.2f",
                    indent: int = 0,
                    sort_by: Optional[Literal['key', 'value']] = None) -> str:
    if sort_by == 'key':
        sorted_keys = sorted(data_dict.keys(), key=str.lower)
    elif sort_by == 'value':
        sorted_keys = sorted(data_dict, key=lambda k: data_dict[k], reverse=True)
    else:
        sorted_keys = data_dict.keys()

    lines = [f'{indent*" "}{key:{key_format}}: {data_dict[key]:{value_format}}' for key in sorted_keys]
    return '\n'.join(lines)
