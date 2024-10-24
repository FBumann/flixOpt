# -*- coding: utf-8 -*-
"""
Created on Tue Nov 17 14:09:02 2020
developed by Felix Panitz* and Peter Stange*
* at Chair of Building Energy Systems and Heat Supply, Technische Universität Dresden
"""

import logging
import re
import timeit
from typing import List, Dict, Optional, Union, Literal

import numpy as np
from pyomo.contrib import appsi

from flixOpt import utils
from flixOpt.core import Skalar, Numeric

pyomoEnv = None  # das ist module, das nur bei Bedarf belegt wird

logger = logging.getLogger('flixOpt')


class Variable:
    """
    Regular single Variable
    """
    def __init__(self,
                 label: str,
                 label_short: str,
                 length: int,
                 math_model: 'MathModel',
                 is_binary: bool = False,
                 value: Optional[Skalar] = None,
                 lower_bound: Optional[Skalar] = None,
                 upper_bound: Optional[Skalar] = None):
        """
        label: full label of the variable
        label_short: short label of the variable
        """
        self.label = label
        self.label_short = label_short
        self.length = length
        self.math_model = math_model
        self.is_binary = is_binary
        self.value = value
        self.lower_bound = lower_bound
        self.upper_bound = upper_bound

        self.indices = range(self.length)
        self.fixed = False

        self._result = None  # Ergebnis-Speicher

        if value is not None:   # Check if value is within bounds, element-wise
            min_ok = (self.lower_bound is None) or np.all(self.value >= self.lower_bound)
            max_ok = (self.upper_bound is None) or np.all(self.value <= self.upper_bound)

            if not (min_ok and max_ok):
                raise Exception(f'Variable.fixed_value {self.label} not inside set bounds:'
                                f'\n{self.value=};\n{self.lower_bound=};\n{self.upper_bound=}')

            # Set value and mark as fixed
            self.fixed = True
            self.value = utils.as_vector(value, length)

        logger.debug('Variable created: ' + self.label)

    def description(self, max_length_ts=60) -> str:
        bin_type = 'bin' if self.is_binary else '   '

        header = f'Var {bin_type} x {self.length:<6} "{self.label}"'
        if self.fixed:
            description = f'{header:<40}: fixed={str(self.value)[:max_length_ts]:<10}'
        else:
            description = (f'{header:<40}: min={str(self.lower_bound)[:max_length_ts]:<10}, '
                           f'max={str(self.upper_bound)[:max_length_ts]:<10}')
        return description

    def to_math_model(self, math_model: 'MathModel'):
        self.math_model = math_model

        # TODO: self.var ist hier einziges Attribut, das math_model-spezifisch ist: --> umbetten in math_model!
        if math_model.modeling_language == 'pyomo':
            if self.is_binary:
                self._pyomo_comp = pyomoEnv.Var(self.indices, domain=pyomoEnv.Binary)
            else:
                self._pyomo_comp = pyomoEnv.Var(self.indices, within=pyomoEnv.Reals)

            # Register in pyomo-model:
            math_model._pyomo_register(self._pyomo_comp, f'var__{self.label}')

            lower_bound_vector = utils.as_vector(self.lower_bound, self.length)
            upper_bound_vector = utils.as_vector(self.upper_bound, self.length)
            value_vector = utils.as_vector(self.value, self.length)
            for i in self.indices:
                # Wenn Vorgabe-Wert vorhanden:
                if self.fixed and (value_vector[i] != None):
                    # Fixieren:
                    self._pyomo_comp[i].value = value_vector[i]
                    self._pyomo_comp[i].fix()
                else:
                    # Boundaries:
                    self._pyomo_comp[i].setlb(lower_bound_vector[i])  # min
                    self._pyomo_comp[i].setub(upper_bound_vector[i])  # max

        elif math_model.modeling_language == 'cvxpy':
            raise NotImplementedError('CVXPY not yet implemented')
        else:
            raise NotImplementedError(f'Modeling Language {math_model.modeling_language} not yet implemented')

    def reset_result(self):
        self._result = None

    @property
    def result(self) -> Numeric:
        # wenn noch nicht abgefragt: (so wird verhindert, dass für jede Abfrage jedesMal neuer Speicher bereitgestellt wird.)
        if self._result is None:
            if self.math_model.modeling_language == 'pyomo':
                # get Data:
                values = self._pyomo_comp.get_values().values()  # .values() of dict, because {0:0.1, 1:0.3,...}
                # choose dataType:
                if self.is_binary:
                    dType = np.int8  # geht das vielleicht noch kleiner ???
                else:
                    dType = float
                # transform to np-array (fromiter() is 5-7x faster than np.array(list(...)) )
                self._result = np.fromiter(values, dtype=dType)
                # Falls skalar:
                if len(self._result) == 1:
                    self._result = self._result[0]

            elif self.math_model.modeling_language == 'cvxpy':
                raise NotImplementedError('CVXPY not yet implemented')
            else:
                raise NotImplementedError(f'Modeling Language {self.math_model.modeling_language} not yet implemented')

        return self._result


class VariableTS(Variable):
    """
    # Timeseries-Variable, optional mit Before-Werten
    """
    def __init__(self,
                 label: str,
                 label_short: str,
                 length: int,
                 math_model: 'MathModel',
                 is_binary: bool = False,
                 value: Optional[Numeric] = None,
                 lower_bound: Optional[Numeric] = None,
                 upper_bound: Optional[Numeric] = None,
                 before_value: Optional[Numeric] = None,
                 before_value_is_start_value: bool = False):
        assert length > 1, 'length is one, that seems not right for VariableTS'
        super().__init__(label, label_short, length, math_model, is_binary=is_binary, value=value, lower_bound=lower_bound, upper_bound=upper_bound)
        self._before_value = before_value
        self.before_value_is_start_value = before_value_is_start_value

    @property
    def before_value(self) -> Optional[Numeric]:
        # Return value if found in before_values, else return stored value
        return self.math_model.before_values.get(self.label) or self._before_value

    @before_value.setter
    def before_value(self, value: Numeric):
        self._before_value = value


# class cInequation(Equation):
#   def __init__(self, label, owner, math_model):
#     super().__init__(label, owner, math_model, eqType='ineq')

class Equation:
    """
    Representing a single equation or, with the Variable being a VariableTS, a set of equations
    """
    def __init__(self,
                 label: str,
                 label_short: str,
                 math_model: 'MathModel',  #TODO Remove
                 eqType: Literal['eq', 'ineq', 'objective'] = 'eq'):
        """
        label: full label of the variable
        label_short: short label of the variable
        """
        self.label = label
        self.label_short = label_short
        self.listOfSummands = []
        self.constant = 0  # rechte Seite

        self.nr_of_single_equations = 1  # Anzahl der Gleichungen
        self.constant_vector = np.array([0])
        self.parts_of_constant = []  # liste mit shares von constant
        self.eqType = eqType
        self._pyomo_comp = None  # z.B. für pyomo : pyomoComponente

        logger.debug(f'Equation created: {self.label}')

    def add_summand(self,
                    variable: Variable,
                    factor: Numeric,
                    indices_of_variable: Optional[Union[int, np.ndarray, range, List[int]]] = None,
                    as_sum: bool = False) -> None:
        """
        Adds a summand to the equation.

        This method creates a summand from the given variable and factor, optionally summing over all indices of the variable.
        The summand is then added to the list of summands for the equation.

        Parameters:
        -----------
        variable : Variable
            The variable to be used in the summand.
        factor : Numeric
            The factor by which the variable is multiplied.
        indices_of_variable : Optional[Numeric], optional
            Specific indices of the variable to be used. If not provided, all indices are used.
        as_sum : bool, optional
            If True, the summand is treated as a sum over all indices of the variable.

        Raises:
        -------
        TypeError
            If the provided variable is not an instance of the Variable class.
        Exception
            If the variable is None and as_sum is True.
        """
        # TODO: Functionality to create A Sum of Summand over a specified range of indices? For Limiting stuff per one year...?
        if not isinstance(variable, Variable):
            raise TypeError(f'Error in Equation "{self.label}": no variable given (variable = "{variable}")')
        if np.isscalar(indices_of_variable):   # Wenn nur ein Wert, dann Liste mit einem Eintrag drausmachen:
            indices_of_variable = [indices_of_variable]

        if not as_sum:
            summand = Summand(variable, factor, indices=indices_of_variable)
        else:
            if variable is None:
                raise Exception(
                    f'Error in Equation "{self.label}": Variable can not be None if the variable is summed up!')
            summand = SumOfSummand(variable, factor, indices=indices_of_variable)

        self._update_nr_of_single_equations(summand.length, summand.variable.label)   # Check Variablen-Länge:
        self.listOfSummands.append(summand)   # zu Liste hinzufügen:

    def add_constant(self, value: Numeric) -> None:
        """
          constant value of the right side,
          if method is executed several times, than values are summed up.

          Parameters
          ----------
          value : float or array
              constant-value of equation [A*x = constant] or [A*x <= constant]

          Returns
          -------
          None.

          """
        self.constant = np.add(self.constant, value)  # Adding to current constant
        self.parts_of_constant.append(value)   # Adding to parts of constants

        length = 1 if np.isscalar(self.constant) else len(self.constant)
        self._update_nr_of_single_equations(length, 'constant')   # Update
        self.constant_vector = utils.as_vector(self.constant, self.nr_of_single_equations)  # Update

    def to_math_model(self, math_model: 'MathModel') -> None:
        logger.debug(f'eq {self.label} .to_math_model()')

        # constant_vector hier erneut erstellen, da Anz. Glg. vorher noch nicht bekannt:
        self.constant_vector = utils.as_vector(self.constant, self.nr_of_single_equations)

        if math_model.modeling_language == 'pyomo':
            # 1. Constraints:
            if self.eqType in ['eq', 'ineq']:

                # lineare Summierung für i-te Gleichung:
                def linear_sum_pyomo_rule(model, i):
                    lhs = 0
                    aSummand: Summand
                    for aSummand in self.listOfSummands:
                        lhs += aSummand.math_expression(i)  # i-te Gleichung (wenn Skalar, dann wird i ignoriert)
                    rhs = self.constant_vector[i]
                    # Unterscheidung return-value je nach typ:
                    if self.eqType == 'eq':
                        return lhs == rhs
                    elif self.eqType == 'ineq':
                        return lhs <= rhs

                # TODO: self._pyomo_comp ist hier einziges Attribut, das math_model-spezifisch ist: --> umbetten in math_model!
                self._pyomo_comp = pyomoEnv.Constraint(range(self.nr_of_single_equations),
                                              rule=linear_sum_pyomo_rule)  # Nebenbedingung erstellen
                # Register im Pyomo:
                math_model._pyomo_register(
                    self._pyomo_comp,
                    f'eq_{self.label}'   # in pyomo-Modell mit eindeutigem Namen registrieren
                )

            # 2. Zielfunktion:
            elif self.eqType == 'objective':
                # Anmerkung: nrOfEquation - Check könnte auch weiter vorne schon passieren!
                if self.nr_of_single_equations > 1:
                    raise Exception('Equation muss für objective ein Skalar ergeben!!!')

                # Summierung der Skalare:
                def linearSumRule_Skalar(model):
                    skalar = 0
                    for aSummand in self.listOfSummands:
                        skalar += aSummand.math_expression(math_model.modeling_language)  # kein i übergeben, da skalar
                    return skalar

                self._pyomo_comp = pyomoEnv.Objective(rule=linearSumRule_Skalar, sense=pyomoEnv.minimize)
                # Register im Pyomo:
                math_model.model.objective = self._pyomo_comp

                # 3. Undefined:
            else:
                raise Exception('equation.eqType= ' + str(self.eqType) + ' nicht definiert')
        elif math_model.modeling_language == 'cvxpy':
            raise NotImplementedError('CVXPY not yet implemented')
        else:
            raise NotImplementedError(f'Modeling Language {math_model.modeling_language} not yet implemented')

            # print i-th equation:

    def description(self, equation_nr: int = 0) -> str:
        equation_nr = min(equation_nr, self.nr_of_single_equations - 1)

        # Name and index
        if self.eqType == 'objective':
            name = 'OBJ'
            index_str = ''
        else:
            name = f'EQ {self.label}'
            index_str = f'[{equation_nr+1}/{self.nr_of_single_equations}]'

        # Summands:
        summand_strings = []
        for idx, summand in enumerate(self.listOfSummands):
            i = 0 if summand.length == 1 else equation_nr
            index = summand.indices[i]
            factor = summand.factor_vec[i]
            factor_str = str(factor) if isinstance(factor, int) else f"{factor:.6}"
            single_summand_str = f"{factor_str} * {summand.variable.label}[{index}]"

            if isinstance(summand, SumOfSummand):
                summand_strings.append(
                    f"∑({('..+' if i > 0 else '')}{single_summand_str}{('+..' if i < summand.length else '')})")
            else:
                summand_strings.append(single_summand_str)

        all_summands_string = ' + '.join(summand_strings)

        # Equation type:
        signs = {'eq': '= ', 'ineq': '=>', 'objective': '= '}
        sign = signs.get(self.eqType, '? ')

        constant = self.constant_vector[equation_nr]

        header_width = 30
        header = f"{name:<{header_width-len(index_str)-1}} {index_str}"
        return f'{header:<{header_width}}: {constant:>8} {sign} {all_summands_string}'

    def _update_nr_of_single_equations(self, length_of_summand: int, label_of_summand: str) -> None:
        """Checks if the new Summand is compatible with the existing Summands"""
        if self.nr_of_single_equations == 1:
            self.nr_of_single_equations = length_of_summand  # first Summand defines length of equation
            self.constant_vector = utils.as_vector(self.constant, self.nr_of_single_equations)  # Update
        elif (length_of_summand != 1) & (length_of_summand != self.nr_of_single_equations):
            raise Exception(f'Variable {label_of_summand} hat eine nicht passende Länge für Gleichung {self.label}')


# Beachte: Muss auch funktionieren für den Fall, dass variable.var fixe Werte sind.
class Summand:
    """
    Part of an equation. Either with a single Variable or a VariableTS
    """
    def __init__(self,
                 variable: Variable,
                 factor: Numeric,
                 indices: Optional[Union[int, np.ndarray, range, List[int]]] = None):  # indices_of_variable default : alle
        self.variable = variable
        self.factor = factor
        self.indices = indices if indices is not None else variable.indices    # wenn nicht definiert, dann alle Indexe

        self.length = self._check_length()   # Länge ermitteln:

        self.factor_vec = utils.as_vector(factor, self.length)   # Faktor als Vektor:

    def math_expression(self, at_index: int = 0):
        # Ausdruck für i-te Gleichung (falls Skalar, dann immer gleicher Ausdruck ausgegeben)
        if self.length == 1:
            return self.variable._pyomo_comp[self.indices[0]] * self.factor_vec[0]  # ignore argument at_index, because Skalar is used for every single equation
        if len(self.indices) == 1:
            return self.variable._pyomo_comp[self.indices[0]] * self.factor_vec[at_index]
        return self.variable._pyomo_comp[self.indices[at_index]] * self.factor_vec[at_index]

    def _check_length(self):
        """
        Determines and returns the length of the summand by comparing the lengths of the factor and the variable indices.
        Sets the attribute .length to this value.

        Returns:
        --------
        int
            The length of the summand, which is the length of the indices if they match the length of the factor,
            or the length of the longer one if one of them is a scalar.

        Raises:
        -------
        Exception
            If the lengths of the factor and the variable indices do not match and neither is a scalar.
        """
        length_of_factor = 1 if np.isscalar(self.factor) else len(self.factor)
        length_of_indices = len(self.indices)
        if length_of_indices == length_of_factor:
            return length_of_indices
        elif length_of_factor == 1:
            return length_of_indices
        elif length_of_indices == 1:
            return length_of_factor
        else:
            raise Exception(f'Variable {self.variable.label} (length={length_of_indices}) und '
                            f'Faktor (length={length_of_factor}) müssen gleiche Länge haben oder Skalar sein')


class SumOfSummand(Summand):
    """
    Part of an Equation. Summing up all parts of a regular Summand of a regular Summand
    'sum(factor[i]*variable[i] for i in all_indexes)'
    """
    def __init__(self,
                 variable: Variable,
                 factor: Numeric,
                 indices: Optional[Union[int, np.ndarray, range, List[int]]] = None):  # indices_of_variable default : alle
        super().__init__(variable, factor, indices)

        self._math_expression = None
        self.length = 1

    def math_expression(self, at_index=0):
        # at index doesn't do anything. Can be removed, but induces changes elsewhere (Inherritance)
        if self._math_expression is not None:
            return self._math_expression
        else:
            self._math_expression = sum(self.variable._pyomo_comp[self.indices[j]] * self.factor_vec[j] for j in self.indices)
            return self._math_expression


class MathModel:
    '''
    Class for equations of the form a_1*x_1 + a_2*x_2 = y
    x_1 and a_1 can be vectors or scalars.

    Model for adding vector variables and scalars:
    Allowed summands:
    - var_vec * factor_vec
    - var_vec * factor
    - factor
    - var * factor
    - var * factor_vec  # Does this make sense? Is this even implemented?
    '''

    def __init__(self,
                 label: str,
                 modeling_language: Literal['pyomo', 'cvxpy'] = 'pyomo'):
        self._infos = {}
        self.label = label
        self.modeling_language = modeling_language

        self.countComp = 0  # ElementeZähler für Pyomo
        self.epsilon = 1e-5  #

        self.solver_name: Optional[str] = None
        self.model = None  # Übergabe später, zumindest für Pyomo notwendig
        self._variables = []
        self._eqs = []
        self._ineqs = []
        self.objective = None  # objective-Function
        self.objective_result = None  # Ergebnis
        self.duration = {}  # Laufzeiten
        self.solver_log = None  # logging und parsen des solver-outputs
        self.before_values: Dict[str, Numeric] = {}  # before_values, which overwrite inital before values defined in the Elements.

        if self.modeling_language == 'pyomo':
            global pyomoEnv  # als globale Variable
            import pyomo.environ as pyomoEnv
            logger.debug('Loaded pyomo modules')
            # für den Fall pyomo wird EIN Modell erzeugt, das auch für rollierende Durchlaufe immer wieder genutzt wird.
            self.model = pyomoEnv.ConcreteModel(name="(Minimalbeispiel)")
        elif self.modeling_language == 'cvxpy':
            raise NotImplementedError('Modeling Language cvxpy is not yet implemented')
        else:
            raise Exception('not defined for modeling_language' + str(self.modeling_language))

    def add(self, *args: Union[Variable, Equation]) -> None:
        if not isinstance(args, list):
            args = list(args)
        for arg in args:
            if isinstance(arg, Variable):
                self._variables.append(arg)
            elif isinstance(arg, Equation):
                if arg.eqType == 'eq':
                    self._eqs.append(arg)
                elif arg.eqType == 'ineq':
                    self._ineqs.append(arg)
                else:
                    raise Exception(f'{arg} cant be added this way!')
            else:
                raise Exception(f'{arg} cant be added this way!')

    def describe(self) -> str:
        return (f'no of Eqs   (single): {self.nr_of_equations} ({self.nr_of_single_equations})\n'
                f'no of InEqs (single): {self.nr_of_inequations} ({self.nr_of_single_inequations})\n'
                f'no of Vars  (single): {self.nr_of_variables} ({self.nr_of_single_variables})')

    def to_math_model(self) -> None:
        t_start = timeit.default_timer()
        for variable in self.variables:   # Variablen erstellen
            variable.to_math_model(self)
        for eq in self.eqs:   # Gleichungen erstellen
            eq.to_math_model(self)
        for ineq in self.ineqs:   # Ungleichungen erstellen:
            ineq.to_math_model(self)

        self.duration['to_math_model'] = round(timeit.default_timer() - t_start, 2)

    def solve(self,
              mip_gap: float,
              time_limit_seconds: int,
              solver_name: Literal['highs', 'gurobi', 'cplex', 'glpk', 'cbc'],
              solver_output_to_console: bool,
              logfile_name: str,
              **solver_opt) -> None:
        self.solver_name = solver_name
        t_start = timeit.default_timer()
        for variable in self.variables:
            variable.reset_result()  # altes Ergebnis löschen (falls vorhanden)
        if self.modeling_language == 'pyomo':
            if solver_name == 'highs':
              solver = appsi.solvers.Highs()
            else:
              solver = pyomoEnv.SolverFactory(solver_name)
            if solver_name == 'cbc':
                solver_opt["ratio"] = mip_gap
                solver_opt["sec"] = time_limit_seconds
            elif solver_name == 'gurobi':
                solver_opt["mipgap"] = mip_gap
                solver_opt["TimeLimit"] = time_limit_seconds
            elif solver_name == 'cplex':
                solver_opt["mipgap"] = mip_gap
                solver_opt["timelimit"] = time_limit_seconds
                # todo: threads = ? funktioniert das für cplex?
            elif solver_name == 'glpk':
                # solver_opt = {} # überschreiben, keine kwargs zulässig
                # solver_opt["mipgap"] = mip_gap
                solver_opt['mipgap'] = mip_gap
            elif solver_name == 'highs':
                  solver_opt["mip_rel_gap"] = mip_gap
                  solver_opt["time_limit"] = time_limit_seconds
                  solver_opt["log_file"]= "results/highs.log"
                  solver_opt["parallel"] = "on"
                  solver_opt["presolve"] = "on"
                  solver_opt["threads"] = 4
                  solver_opt["output_flag"] = True
                  solver_opt["log_to_console"] = True
            # logfile_name = "flixSolverLog.log"
            if solver_name == 'highs':
                solver.highs_options=solver_opt
                self.solver_results = solver.solve(self.model)
            else:
                self.solver_results = solver.solve(self.model, options = solver_opt, tee = solver_output_to_console, keepfiles=True, logfile=logfile_name)

            # Log wieder laden:
            if solver_name == 'highs':
                pass
            else:
                self.solver_log = SolverLog(solver_name, logfile_name)
                self.solver_log.parse_infos()
            # Ergebnis Zielfunktion ablegen
            self.objective_result = self.model.objective.expr()

        else:
            raise Exception('not defined for modtype ' + self.modeling_language)

        self.duration['solve'] = round(timeit.default_timer() - t_start, 2)

    @property
    def infos(self) -> Dict:
        infos = {}
        infos['Solver'] = self.solver_name

        info_flixModel = {}
        infos['flixModel'] = info_flixModel

        info_flixModel['no eqs'] = self.nr_of_equations
        info_flixModel['no eqs single'] = self.nr_of_single_equations
        info_flixModel['no inEqs'] = self.nr_of_inequations
        info_flixModel['no inEqs single'] = self.nr_of_single_inequations
        info_flixModel['no vars'] = self.nr_of_variables
        info_flixModel['no vars single'] = self.nr_of_single_variables
        info_flixModel['no vars TS'] = len(self.ts_variables)

        if self.solver_log is not None:
            infos['solver_log'] = self.solver_log.infos
        return infos

    @property
    def variables(self) -> List[Variable]:
        return self._variables

    @property
    def eqs(self) -> List[Equation]:
        return self._eqs

    @property
    def ineqs(self) -> List[Equation]:
        return self._ineqs

    @property
    def ts_variables(self) -> List[VariableTS]:
        return [variable for variable in self.variables if isinstance(variable, VariableTS)]

    @property
    def nr_of_variables(self) -> int:
        return len(self.variables)

    @property
    def nr_of_equations(self) -> int:
        return len(self.eqs)

    @property
    def nr_of_inequations(self) -> int:
        return len(self.ineqs)

    @property
    def nr_of_single_variables(self) -> int:
        return sum([var.length for var in self.variables])

    @property
    def nr_of_single_equations(self) -> int:
        return sum([eq.nr_of_single_equations for eq in self.eqs])

    @property
    def nr_of_single_inequations(self) -> int:
        return sum([eq.nr_of_single_equations for eq in self.ineqs])

    ################################## pyomo
    def _pyomo_register(self, pyomo_comp, label='', old_pyomo_comp_to_overwrite=None) -> None:
        # neu erstellen
        if old_pyomo_comp_to_overwrite is None:
            self.countComp += 1
            # Komponenten einfach hochzählen, damit eindeutige Namen, d.h. a1_timesteps, a2, a3 ,...
            # Beispiel:
            # model.add_component('a1',py_comp) äquivalent zu model.a1 = py_comp
            self.model.add_component(f'a{self.countComp}__{label}', pyomo_comp)  # a1,a2,a3, ...
        # altes überschreiben:
        else:
            self._pyomo_overwrite_comp(pyomo_comp, old_pyomo_comp_to_overwrite)

    def _pyomo_delete(self, old_pyomo_comp) -> None:
        # Komponente löschen:
        name_of_pyomo_comp = self._pyomo_get_internal_name(old_pyomo_comp)
        additional_comps_to_delete = name_of_pyomo_comp + '_index'  # sowas wird bei manchen Komponenten als Komponente automatisch mit erzeugt.
        if additional_comps_to_delete in self.model.component_map().keys():   # sonstige zugehörige Variablen löschen:
            self.model.del_component(additional_comps_to_delete)
        self.model.del_component(name_of_pyomo_comp)

    def _pyomo_get_internal_name(self, pyomo_comp) -> str:
        # name of component
        for key, value in self.model.component_map().iteritems():
            if pyomo_comp == value:
                return key

    def _pyomo_get_comp(self, name_of_pyomo_comp: str):
        return self.model.component_map()[name_of_pyomo_comp]

    def _pyomo_overwrite_comp(self, pyomo_comp, old_py_comp) -> None:
        # gleichnamige Pyomo-Komponente überschreiben (wenn schon vorhanden, sonst neu)
        name_of_pyomo_comp = self._pyomo_get_internal_name(old_py_comp)
        self._pyomo_delete(old_py_comp)   # alles alte löschen:
        self.model.add_component(name_of_pyomo_comp, pyomo_comp)   # überschreiben:

    ######## Other Modeling Languages

    def results(self):
        return {variable.label: variable.result for variable in self.variables}


class SolverLog:
    def __init__(self, solver_name: str, filename: str):
        with open(filename, 'r') as file:
            self.log = file.read()

        self.solver_name = solver_name

        self.presolved_rows = None
        self.presolved_cols = None
        self.presolved_nonzeros = None

        self.presolved_continuous = None
        self.presolved_integer = None
        self.presolved_binary = None

    @property
    def infos(self):
        infos = {}
        aPreInfo = {}
        infos['presolved'] = aPreInfo
        aPreInfo['cols'] = self.presolved_cols
        aPreInfo['continuous'] = self.presolved_continuous
        aPreInfo['integer'] = self.presolved_integer
        aPreInfo['binary'] = self.presolved_binary
        aPreInfo['rows'] = self.presolved_rows
        aPreInfo['nonzeros'] = self.presolved_nonzeros

        return infos

    # Suche infos aus log:
    def parse_infos(self):
        if self.solver_name == 'gurobi':

            # string-Schnipsel 1:
            '''
            Optimize a model with 285 rows, 292 columns and 878 nonzeros
            Model fingerprint: 0x1756ffd1
            Variable types: 202 continuous, 90 integer (90 binary)        
            '''
            # string-Schnipsel 2:
            '''
            Presolve removed 154 rows and 172 columns
            Presolve time: 0.00s
            Presolved: 131 rows, 120 columns, 339 nonzeros
            Variable types: 53 continuous, 67 integer (67 binary)
            '''
            # string: Presolved: 131 rows, 120 columns, 339 nonzeros\n
            match = re.search('Presolved: (\d+) rows, (\d+) columns, (\d+) nonzeros' +
                              '\\n\\n' +
                              'Variable types: (\d+) continuous, (\d+) integer \((\d+) binary\)', self.log)
            if not match is None:
                # string: Presolved: 131 rows, 120 columns, 339 nonzeros\n
                self.presolved_rows = int(match.group(1))
                self.presolved_cols = int(match.group(2))
                self.presolved_nonzeros = int(match.group(3))
                # string: Variable types: 53 continuous, 67 integer (67 binary)
                self.presolved_continuous = int(match.group(4))
                self.presolved_integer = int(match.group(5))
                self.presolved_binary = int(match.group(6))

        elif self.solver_name == 'cbc':

            # string: Presolve 1623 (-1079) rows, 1430 (-1078) columns and 4296 (-3306) elements
            match = re.search('Presolve (\d+) \((-?\d+)\) rows, (\d+) \((-?\d+)\) columns and (\d+)', self.log)
            if not match is None:
                self.presolved_rows = int(match.group(1))
                self.presolved_cols = int(match.group(3))
                self.presolved_nonzeros = int(match.group(5))

            # string: Presolved problem has 862 integers (862 of which binary)
            match = re.search('Presolved problem has (\d+) integers \((\d+) of which binary\)', self.log)
            if not match is None:
                self.presolved_integer = int(match.group(1))
                self.presolved_binary = int(match.group(2))
                self.presolved_continuous = self.presolved_cols - self.presolved_integer

        elif self.solver_name == 'glpk':
            logger.warning(f'{"":#^80}\n')
            logger.warning(f'{" No solver-log parsing implemented for glpk yet! ":#^80}\n')
        else:
            raise Exception('SolverLog.parse_infos() is not defined for solver ' + self.solver_name)
