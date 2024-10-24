import unittest
import os
import datetime
from typing import Literal

import numpy as np
import pandas as pd

from flixOpt import *
from flixOpt.linear_converters import Boiler, CHP


class BaseTest(unittest.TestCase):
    def setUp(self):
        setup_logging("DEBUG")
        self.solverProps = {
            'mip_gap': 0.0001,
            'time_limit_seconds': 3600,
            'solver_name': 'highs',
            'solver_output_to_console': True,
        }

    def assertAlmostEqualNumeric(self, actual, desired, err_msg, relative_error_range_in_percent=0.011): # error_range etwas höher als mip_gap, weil unterschiedl. Bezugswerte
        '''
        Asserts that actual is almost equal to desired.
        Designed for comparing float and ndarrays. Whith respect to tolerances
        '''
        relative_tol = relative_error_range_in_percent/100
        if isinstance(desired, (int, float)):
            delta = abs(relative_tol * desired)
            self.assertAlmostEqual(actual, desired, msg=err_msg, delta=delta)
        else:
            np.testing.assert_allclose(actual, desired, rtol=relative_tol, atol=1e-9)


class TestSimple(BaseTest):

    def setUp(self):
        super().setUp()

        self.Q_th_Last = np.array([30., 0., 90., 110, 110, 20, 20, 20, 20])
        self.p_el = 1 / 1000 * np.array([80., 80., 80., 80, 80, 80, 80, 80, 80])
        self.aTimeSeries = datetime.datetime(2020, 1, 1) + np.arange(len(self.Q_th_Last)) * datetime.timedelta(hours=1)
        self.aTimeSeries = self.aTimeSeries.astype('datetime64')
        self.max_emissions_per_hour = 1000

    def test_model(self):
        results = self.model()

        # Compare expected values with actual values
        self.assertAlmostEqualNumeric(results['Effects']['costs']['all']['sum'], 81.88394666666667,
                               "costs doesnt match expected value")
        self.assertAlmostEqualNumeric(results['Effects']['CO2']['all']['sum'], 255.09184,
                               "CO2 doesnt match expected value")
        self.assertAlmostEqualNumeric(results['Boiler']['Q_th']['val'],
                                      [0, 0, 0, 28.4864, 35, 0, 0, 0, 0],
                                  "Q_th doesnt match expected value")
        self.assertAlmostEqualNumeric(results['CHP_unit']['Q_th']['val'],
                                      [30., 26.66666667, 75., 75., 75., 20., 20., 20., 20.],
                                  "Q_th doesnt match expected value")

    def model(self):
        # Define the components and flow_system
        Strom = Bus('el', 'Strom')
        Fernwaerme = Bus('heat', 'Fernwärme')
        Gas = Bus('fuel', 'Gas')

        costs = Effect('costs', '€', 'Kosten', is_standard=True, is_objective=True)
        CO2 = Effect('CO2', 'kg', 'CO2_e-Emissionen', specific_share_to_other_effects_operation={costs: 0.2},
                     maximum_operation_per_hour=self.max_emissions_per_hour)

        aBoiler = Boiler('Boiler', eta=0.5,
                         Q_th=Flow('Q_th', bus=Fernwaerme, size=50, relative_minimum=5 / 50, relative_maximum=1),
                         Q_fu=Flow('Q_fu', bus=Gas))
        aKWK = CHP('CHP_unit', eta_th=0.5, eta_el=0.4, P_el=Flow('P_el', bus=Strom, size=60, relative_minimum=5 / 60),
                   Q_th=Flow('Q_th', bus=Fernwaerme), Q_fu=Flow('Q_fu', bus=Gas))
        aSpeicher = Storage('Speicher', charging=Flow('Q_th_load', bus=Fernwaerme, size=1e4),
                            discharging=Flow('Q_th_unload', bus=Fernwaerme, size=1e4),
                            capacity_in_flow_hours=InvestParameters(fix_effects=20, fixed_size=30, optional=False),
                            initial_charge_state=0,
                            relative_maximum_charge_state=1 / 100 * np.array([80., 70., 80., 80, 80, 80, 80, 80, 80, 80]),
                            eta_load=0.9, eta_unload=1, relative_loss_per_hour=0.08, prevent_simultaneous_charge_and_discharge=True)
        aWaermeLast = Sink('Wärmelast', sink=Flow('Q_th_Last', bus=Fernwaerme, size=1, fixed_relative_value=self.Q_th_Last))
        aGasTarif = Source('Gastarif',
                           source=Flow('Q_Gas', bus=Gas, size=1000, effects_per_flow_hour={costs: 0.04, CO2: 0.3}))
        aStromEinspeisung = Sink('Einspeisung', sink=Flow('P_el', bus=Strom, effects_per_flow_hour=-1 * self.p_el))

        es = FlowSystem(self.aTimeSeries, last_time_step_hours=None)
        es.add_components(aSpeicher)
        es.add_effects(costs, CO2)
        es.add_components(aBoiler, aWaermeLast, aGasTarif)
        es.add_components(aStromEinspeisung)
        es.add_components(aKWK)

        time_indices = None

        aCalc = FullCalculation('Test_Sim', es, 'pyomo', time_indices)
        aCalc.do_modeling()

        es.print_model()
        es.print_variables()
        es.print_equations()

        aCalc.solve(self.solverProps)

        aCalc_post = flix_results(aCalc.name)
        return aCalc_post.results


class TestComplex(BaseTest):

    def setUp(self):
        super().setUp()
        self.Q_th_Last = np.array([30., 0., 90., 110, 110, 20, 20, 20, 20])
        self.P_el_Last = np.array([40., 40., 40., 40 , 40, 40, 40, 40, 40])
        self.aTimeSeries = datetime.datetime(2020, 1, 1) + np.arange(len(self.Q_th_Last)) * datetime.timedelta(hours=1)
        self.aTimeSeries = self.aTimeSeries.astype('datetime64')
        self.excessCosts = None
        self.useCHPwithLinearSegments = False

    def test_basic(self):
        results = self.basic_model()

        # Compare expected values with actual values
        self.assertAlmostEqualNumeric(results['Effects']['costs']['all']['sum'], -11597.873624489237,
                               "costs doesnt match expected value")
        self.assertAlmostEqualNumeric(results['Effects']['costs']['operation']['sum_TS'],
                                      [-2.38500000e+03, -2.21681333e+03, -2.38500000e+03, -2.17599000e+03,
                                       -2.35107029e+03, -2.38500000e+03, 0.00000000e+00, -1.68897826e-10,
                                       -2.16914486e-12], "costs doesnt match expected value")

        self.assertAlmostEqualNumeric(results['Effects']['costs']['operation']['shares']['CO2_specific_share_to_other_effects_operation'],
                                      258.63729669618675, "costs doesnt match expected value")
        self.assertAlmostEqualNumeric(results['Effects']['costs']['operation']['shares']['Kessel__Q_th_effects_per_switch_on'],
                                      0.01, "costs doesnt match expected value")
        self.assertAlmostEqualNumeric(results['Effects']['costs']['operation']['shares']['Kessel_effects_per_running_hour'],
                                      -0.0, "costs doesnt match expected value")
        self.assertAlmostEqualNumeric(results['Effects']['costs']['operation']['shares']['Gastarif__Q_Gas_effects_per_flow_hour'],
                                      39.09153113079115, "costs doesnt match expected value")
        self.assertAlmostEqualNumeric(results['Effects']['costs']['operation']['shares']['Einspeisung__P_el_effects_per_flow_hour'],
                                      -14196.61245231646, "costs doesnt match expected value")
        self.assertAlmostEqualNumeric(results['Effects']['costs']['operation']['shares']['KWK_effects_per_switch_on'],
                                      0.0, "costs doesnt match expected value")

        self.assertAlmostEqualNumeric(results['Effects']['costs']['invest']['shares']['Kessel__Q_th_fix_effects'],
                                      1000, "costs doesnt match expected value")
        self.assertAlmostEqualNumeric(results['Effects']['costs']['invest']['shares']['Kessel__Q_th_specific_effects'],
                                      500, "costs doesnt match expected value")
        self.assertAlmostEqualNumeric(results['Effects']['costs']['invest']['shares']['Speicher_specific_effects'],
                                      1, "costs doesnt match expected value")
        self.assertAlmostEqualNumeric(results['Effects']['costs']['invest']['shares']['Speicher_linearSegments'],
                                      800, "costs doesnt match expected value")

        self.assertAlmostEqualNumeric(results['Effects']['CO2']['all']['shares']['CO2_operation'], 1293.1864834809337,
                               "CO2 doesnt match expected value")
        self.assertAlmostEqualNumeric(results['Effects']['CO2']['all']['shares']['CO2_invest'], 0.9999999999999994,
                                      "CO2 doesnt match expected value")
        self.assertAlmostEqualNumeric(results['Kessel']['Q_th']['val'],
                                      [0, 0, 0, 45, 0, 0, 0, 0, 0],
                                  "Kessel doesnt match expected value")

        self.assertAlmostEqualNumeric(results['KWK']['Q_th']['val'],
                                      [7.50000000e+01, 6.97111111e+01, 7.50000000e+01, 7.50000000e+01,
                                   7.39330280e+01, 7.50000000e+01, 0.00000000e+00, 3.12638804e-14,
                                   3.83693077e-14],
                                  "KWK Q_th doesnt match expected value")
        self.assertAlmostEqualNumeric(results['KWK']['P_el']['val'],
                                      [6.00000000e+01, 5.57688889e+01, 6.00000000e+01, 6.00000000e+01,
                                   5.91464224e+01, 6.00000000e+01, 0.00000000e+00, 2.50111043e-14, 3.06954462e-14],
                                  "KWK P_el doesnt match expected value")

        self.assertAlmostEqualNumeric(results['KWK']['P_el']['val'],
                                      [6.00000000e+01, 5.57688889e+01, 6.00000000e+01, 6.00000000e+01,
                                   5.91464224e+01, 6.00000000e+01, 0.00000000e+00, 2.50111043e-14, 3.06954462e-14],
                                  "KWK P_el doesnt match expected value")

        self.assertAlmostEqualNumeric(results['Speicher']['nettoFlow'],
                                      [-45., -69.71111111, 15., -10., 36.06697198, -55., 20., 20., 20.],
                                  "Speicher nettoFlow doesnt match expected value")
        self.assertAlmostEqualNumeric(results['Speicher']['charge_state'],
                                      [0., 40.5, 100., 77.,
                                             79.84, 37.38582802, 83.89496178, 57.18336484,
                                             32.60869565, 10.],
                                  "Speicher nettoFlow doesnt match expected value")

        self.assertAlmostEqualNumeric(results['Speicher']['invest']['investCosts_segmented_costs'], 800,
                                  "Speicher investCosts_segmented_costs doesnt match expected value")

    def test_segments_of_flows(self):
        results = self.segments_of_flows_model()

        # Compare expected values with actual values
        self.assertAlmostEqualNumeric(results['Effects']['costs']['all']['sum'], -10710.997365760755,
                               "costs doesnt match expected value")
        self.assertAlmostEqualNumeric(results['Effects']['CO2']['all']['sum'], 1278.7939026086956,
                               "CO2 doesnt match expected value")
        self.assertAlmostEqualNumeric(results['Kessel']['Q_th']['val'],
                                      [0, 0, 0, 45, 0, 0, 0, 0, 0],
                                  "Kessel doesnt match expected value")
        self.assertAlmostEqualNumeric(results['KWK']['Q_th']['val'],
                                      [45., 45., 64.5962087, 100.,
                                       61.3136, 45., 45., 12.86469565,
                                       0.],
                                  "KWK Q_th doesnt match expected value")
        self.assertAlmostEqualNumeric(results['KWK']['P_el']['val'],
                                      [40., 40., 47.12589407, 60., 45.93221818,
                                       40., 40., 10.91784108, -0.],
                                  "KWK P_el doesnt match expected value")

        self.assertAlmostEqualNumeric(results['Speicher']['nettoFlow'],
                                      [-15., -45., 25.4037913, -35.,
                                       48.6864, -25., -25., 7.13530435,
                                       20.],
                                  "Speicher nettoFlow doesnt match expected value")

        self.assertAlmostEqualNumeric(results['Speicher']['invest']['investCosts_segmented_costs'], 454.74666666666667,
                                  "Speicher investCosts_segmented_costs doesnt match expected value")

    def basic_model(self):
        # Define the components and flow_system
        Strom = Bus('el', 'Strom', excess_effects_per_flow_hour=self.excessCosts)
        Fernwaerme = Bus('heat', 'Fernwärme', excess_effects_per_flow_hour=self.excessCosts)
        Gas = Bus('fuel', 'Gas', excess_effects_per_flow_hour=self.excessCosts)

        costs = Effect('costs', '€', 'Kosten', is_standard=True, is_objective=True)
        CO2 = Effect('CO2', 'kg', 'CO2_e-Emissionen', specific_share_to_other_effects_operation={costs: 0.2})
        PE = Effect('PE', 'kWh_PE', 'Primärenergie', maximum_total=3.5e3)

        aGaskessel = Boiler('Kessel', eta=0.5, effects_per_running_hour={costs: 0, CO2: 1000},
                            Q_th=Flow('Q_th', bus=Fernwaerme, size=InvestParameters(fix_effects=1000, fixed_size=50, optional=False, specific_effects={costs: 10, PE: 2}), load_factor_max=1.0, load_factor_min=0.1, relative_minimum=5 / 50, relative_maximum=1, on_hours_total_min=0, on_hours_total_max=1000, consecutive_on_hours_max=10, consecutive_off_hours_max=10, effects_per_switch_on=0.01, switch_on_total_max=1000, values_before_begin=[50], flow_hours_total_max=1e6),
                            Q_fu=Flow('Q_fu', bus=Gas, size=200, relative_minimum=0, relative_maximum=1))

        aKWK = CHP('KWK', eta_th=0.5, eta_el=0.4, effects_per_switch_on=0.01, on_values_before_begin=[1],
                   P_el=Flow('P_el', bus=Strom, size=60, relative_minimum=5 / 60),
                   Q_th=Flow('Q_th', bus=Fernwaerme, size=1e3),
                   Q_fu=Flow('Q_fu', bus=Gas, size=1e3))

        costsInvestsizeSegments = [[5, 25, 25, 100], {costs: [50, 250, 250, 800], PE: [5, 25, 25, 100]}]
        invest_Speicher = InvestParameters(fix_effects=0, effects_in_segments=costsInvestsizeSegments, optional=False, specific_effects={costs: 0.01, CO2: 0.01}, minimum_size=0, maximum_size=1000)
        aSpeicher = Storage('Speicher', charging=Flow('Q_th_load', bus=Fernwaerme, size=1e4), discharging=Flow('Q_th_unload', bus=Fernwaerme, size=1e4), capacity_in_flow_hours=invest_Speicher, initial_charge_state=0, maximal_final_charge_state=10, eta_load=0.9, eta_unload=1, relative_loss_per_hour=0.08, prevent_simultaneous_charge_and_discharge=True)

        aWaermeLast = Sink('Wärmelast', sink=Flow('Q_th_Last', bus=Fernwaerme, size=1, relative_minimum=0, fixed_relative_value=self.Q_th_Last))
        aGasTarif = Source('Gastarif', source=Flow('Q_Gas', bus=Gas, size=1000, effects_per_flow_hour={costs: 0.04, CO2: 0.3}))
        aStromEinspeisung = Sink('Einspeisung', sink=Flow('P_el', bus=Strom, effects_per_flow_hour=-1 * np.array(self.P_el_Last)))

        es = FlowSystem(self.aTimeSeries, last_time_step_hours=None)
        es.add_effects(costs, CO2, PE)
        es.add_components(aGaskessel, aWaermeLast, aGasTarif, aStromEinspeisung, aKWK, aSpeicher)

        aCalc = FullCalculation('Sim1', es, 'pyomo', None)
        aCalc.do_modeling()

        es.print_model()
        es.print_variables()
        es.print_equations()

        aCalc.solve(self.solverProps)

        return flix_results(aCalc.name).results

    def segments_of_flows_model(self):
        # Define the components and flow_system
        Strom = Bus('el', 'Strom', excess_effects_per_flow_hour=self.excessCosts)
        Fernwaerme = Bus('heat', 'Fernwärme', excess_effects_per_flow_hour=self.excessCosts)
        Gas = Bus('fuel', 'Gas', excess_effects_per_flow_hour=self.excessCosts)

        costs = Effect('costs', '€', 'Kosten', is_standard=True, is_objective=True)
        CO2 = Effect('CO2', 'kg', 'CO2_e-Emissionen', specific_share_to_other_effects_operation={costs: 0.2})
        PE = Effect('PE', 'kWh_PE', 'Primärenergie', maximum_total=3.5e3)

        aGaskessel = Boiler('Kessel', eta=0.5, effects_per_running_hour={costs: 0, CO2: 1000},
                            Q_th=Flow('Q_th', bus=Fernwaerme, size=InvestParameters(fix_effects=1000, fixed_size=50, optional=False, specific_effects={costs: 10, PE: 2}), load_factor_max=1.0, load_factor_min=0.1, relative_minimum=5 / 50, relative_maximum=1, on_hours_total_min=0, on_hours_total_max=1000, consecutive_on_hours_max=10, consecutive_off_hours_max=10, effects_per_switch_on=0.01, switch_on_total_max=1000, values_before_begin=[50], flow_hours_total_max=1e6),
                            Q_fu=Flow('Q_fu', bus=Gas, size=200, relative_minimum=0, relative_maximum=1))

        P_el = Flow('P_el', bus=Strom, size=60, relative_maximum=55)
        Q_th = Flow('Q_th', bus=Fernwaerme)
        Q_fu = Flow('Q_fu', bus=Gas)
        segmented_conversion_factors = {P_el: [5, 30, 40, 60], Q_th: [6, 35, 45, 100], Q_fu: [12, 70, 90, 200]}
        aKWK = LinearConverter('KWK', inputs=[Q_fu], outputs=[P_el, Q_th], segmented_conversion_factors=segmented_conversion_factors, effects_per_switch_on=0.01, on_values_before_begin=[1])

        costsInvestsizeSegments = [[5, 25, 25, 100], {costs: [50, 250, 250, 800], PE: [5, 25, 25, 100]}]
        invest_Speicher = InvestParameters(fix_effects=0, effects_in_segments=costsInvestsizeSegments, optional=False, specific_effects={costs: 0.01, CO2: 0.01}, minimum_size=0, maximum_size=1000)
        aSpeicher = Storage('Speicher', charging=Flow('Q_th_load', bus=Fernwaerme, size=1e4), discharging=Flow('Q_th_unload', bus=Fernwaerme, size=1e4), capacity_in_flow_hours=invest_Speicher, initial_charge_state=0, maximal_final_charge_state=10, eta_load=0.9, eta_unload=1, relative_loss_per_hour=0.08, prevent_simultaneous_charge_and_discharge=True)

        aWaermeLast = Sink('Wärmelast', sink=Flow('Q_th_Last', bus=Fernwaerme, size=1, relative_minimum=0, fixed_relative_value=self.Q_th_Last))
        aGasTarif = Source('Gastarif', source=Flow('Q_Gas', bus=Gas, size=1000, effects_per_flow_hour={costs: 0.04, CO2: 0.3}))
        aStromEinspeisung = Sink('Einspeisung', sink=Flow('P_el', bus=Strom, effects_per_flow_hour=-1 * np.array(self.P_el_Last)))

        es = FlowSystem(self.aTimeSeries, last_time_step_hours=None)
        es.add_effects(costs, CO2, PE)
        es.add_components(aGaskessel, aWaermeLast, aGasTarif, aStromEinspeisung, aKWK)
        es.add_components(aSpeicher)

        aCalc = FullCalculation('Sim1', es, 'pyomo', None)
        aCalc.do_modeling()

        es.print_model()
        es.print_variables()
        es.print_equations()

        aCalc.solve(self.solverProps)

        return flix_results(aCalc.name).results


class TestModelingTypes(BaseTest):

    def setUp(self):
        super().setUp()
        self.Q_th_Last = np.array([30., 0., 90., 110, 110, 20, 20, 20, 20])
        self.p_el = 1 / 1000 * np.array([80., 80., 80., 80, 80, 80, 80, 80, 80])
        self.aTimeSeries = (datetime.datetime(2020, 1, 1) + np.arange(len(self.Q_th_Last)) * datetime.timedelta(hours=1)).astype('datetime64')
        self.max_emissions_per_hour = 1000

    def test_full(self):
        results = self.calculate("full")
        self.assertAlmostEqualNumeric(results['Effects']['costs']['all']['sum'], 343613, "costs doesnt match expected value")

    def test_aggregated(self):
        results = self.calculate("aggregated")
        self.assertAlmostEqualNumeric(results['Effects']['costs']['all']['sum'], 342967.0, "costs doesnt match expected value")

    def test_segmented(self):
        results = self.calculate("segmented")
        self.assertAlmostEqualNumeric(sum(results['Effects']['costs']['operation']['sum_TS']), 343613, "costs doesnt match expected value")

    def calculate(self, modeling_type: Literal["full", "segmented", "aggregated"]):
        doFullCalc, doSegmentedCalc, doAggregatedCalc = modeling_type == "full", modeling_type == "segmented", modeling_type == "aggregated"
        if not any([doFullCalc, doSegmentedCalc, doAggregatedCalc]): raise Exception("Unknown modeling type")

        filename = os.path.join(os.path.dirname(__file__), "ressources", "Zeitreihen2020.csv")
        ts_raw = pd.read_csv(filename, index_col=0).sort_index()
        data = ts_raw['2020-01-01 00:00:00':'2020-12-31 23:45:00']['2020-01-01':'2020-01-03 23:45:00']
        P_el_Last, Q_th_Last, p_el, gP = data['P_Netz/MW'], data['Q_Netz/MW'], data['Strompr.€/MWh'], data['Gaspr.€/MWh']
        aTimeSeries = (datetime.datetime(2020, 1, 1) + np.arange(len(P_el_Last)) * datetime.timedelta(hours=0.25)).astype('datetime64')

        Strom, Fernwaerme, Gas, Kohle = Bus('el', 'Strom'), Bus('heat', 'Fernwärme'), Bus('fuel', 'Gas'), Bus('fuel', 'Kohle')
        costs, CO2, PE = Effect('costs', '€', 'Kosten', is_standard=True, is_objective=True), Effect('CO2', 'kg', 'CO2_e-Emissionen'), Effect('PE', 'kWh_PE', 'Primärenergie')

        aGaskessel = Boiler('Kessel', eta=0.85, Q_th=Flow(label='Q_th', bus=Fernwaerme), Q_fu=Flow(label='Q_fu', bus=Gas, size=95, relative_minimum=12 / 95, can_switch_off=True, effects_per_switch_on=1000, values_before_begin=[0]))
        aKWK = CHP('BHKW2', eta_th=0.58, eta_el=0.22, effects_per_switch_on=24000, P_el=Flow('P_el', bus=Strom), Q_th=Flow('Q_th', bus=Fernwaerme), Q_fu=Flow('Q_fu', bus=Kohle, size=288, relative_minimum=87 / 288), on_values_before_begin=[0])
        aSpeicher = Storage('Speicher', charging=Flow('Q_th_load', size=137, bus=Fernwaerme), discharging=Flow('Q_th_unload', size=158, bus=Fernwaerme), capacity_in_flow_hours=684, initial_charge_state=137, minimal_final_charge_state=137, maximal_final_charge_state=158, eta_load=1, eta_unload=1, relative_loss_per_hour=0.001, prevent_simultaneous_charge_and_discharge=True)

        TS_Q_th_Last, TS_P_el_Last = TimeSeriesData(Q_th_Last), TimeSeriesData(P_el_Last, agg_weight=0.7)
        aWaermeLast, aStromLast = Sink('Wärmelast', sink=Flow('Q_th_Last', bus=Fernwaerme, size=1, fixed_relative_value=TS_Q_th_Last)), Sink('Stromlast', sink=Flow('P_el_Last', bus=Strom, size=1, fixed_relative_value=TS_P_el_Last))
        aKohleTarif, aGasTarif = Source('Kohletarif', source=Flow('Q_Kohle', bus=Kohle, size=1000, effects_per_flow_hour={costs: 4.6, CO2: 0.3})), Source('Gastarif', source=Flow('Q_Gas', bus=Gas, size=1000, effects_per_flow_hour={costs: gP, CO2: 0.3}))

        p_feed_in, p_sell = TimeSeriesData(-(p_el - 0.5), agg_group='p_el'), TimeSeriesData(p_el + 0.5, agg_group='p_el')
        aStromEinspeisung, aStromTarif = Sink('Einspeisung', sink=Flow('P_el', bus=Strom, size=1000, effects_per_flow_hour=p_feed_in)), Source('Stromtarif', source=Flow('P_el', bus=Strom, size=1000, effects_per_flow_hour={costs: p_sell, CO2: 0.3}))

        es = FlowSystem(aTimeSeries, last_time_step_hours=None)
        es.add_effects(costs, CO2, PE)
        es.add_components(aGaskessel, aWaermeLast, aStromLast, aGasTarif, aKohleTarif, aStromEinspeisung, aStromTarif, aKWK, aSpeicher)

        if doFullCalc:
            calc = FullCalculation('fullModel', es, 'pyomo')
            calc.do_modeling()
        if doSegmentedCalc:
            calc = SegmentedCalculation('segModel', es, 'pyomo')
            calc.solve(self.solverProps, segment_length=97, nr_of_used_steps=96)
        if doAggregatedCalc:
            calc = AggregatedCalculation('aggModel', es, 'pyomo')
            calc.do_modeling(6, 4, True, True, False, 0, 0, addPeakMax=[TS_Q_th_Last], addPeakMin=[TS_P_el_Last, TS_Q_th_Last])

        es.print_model()
        es.print_variables()
        es.print_equations()

        if not doSegmentedCalc:
            calc.solve(self.solverProps)

        return flix_results(calc.name).results


if __name__ == '__main__':
    unittest.main()