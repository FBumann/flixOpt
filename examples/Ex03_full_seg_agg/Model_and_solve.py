# -*- coding: utf-8 -*-
"""
Created on Fri Sep  4 11:26:10 2020
developed by Felix Panitz* and Peter Stange*
* at Chair of Building Energy Systems and Heat Supply, Technische Universität Dresden
"""

# mögliche Testszenarien für testing-tool:
# abschnittsweise linear testen
# Komponenten mit offenen Flows
# Binärvariablen ohne max-Wert-Vorgabe des Flows (Binärungenauigkeitsproblem)
# Medien-zulässigkeit

# solver:
gapFrac = 0.0005
solver_name = 'cbc'
# solver_name    = 'gurobi'
# solver_name    = 'glpk'
solverProps = {'mip_gap': gapFrac, 'solver_name': solver_name, 'solver_output_to_console': True, 'threads': 16}

## Auswahl Rechentypen: ##

doFullCalc = True
# doFullCalc = False

doSegmentedCalc = True
# doSegmentedCalc = False

doAggregatedCalc = True
# doAggregatedCalc = False

## segmented Properties: ##

nr_of_used_steps = 96 * 1
segmentLen = nr_of_used_steps + 1 * 96

## aggregated Properties: ##

periodLengthInHours = 6
nr_of_typical_periods = 21
nr_of_typical_periods = 4
useExtremeValues = True
# useExtremeValues    = False
fix_binary_vars_only = False
# fix_binary_vars_only   = True
fix_storage_flows = True
# fix_storage_flows     = False    
percentage_of_period_freedom = 0
costs_of_period_freedom = 0

import datetime
import os
import time

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

calcFull = None
calcSegs = None
calcAgg = None

# #########################################################################
# ######################  Data Import  ####################################

# Daten einlesen
filename = os.path.join(os.path.dirname(__file__), "Zeitreihen2020.csv")
ts_raw = pd.read_csv(filename, index_col=0)
ts_raw = ts_raw.sort_index()

# ts = ts_raw['2020-01-01 00:00:00':'2020-12-31 23:45:00']  # EDITIEREN FÜR ZEITRAUM
ts = ts_raw['2020-01-01 00:00:00':'2020-12-31 23:45:00']
# ts['Kohlepr.€/MWh'] = 4.6
ts.set_index(pd.to_datetime(ts.index), inplace=True)  # str to datetime
data = ts

time_zero = time.time()

# ENTWEDER...
# Zeitaussschnitt definieren
zeitraumInTagen = 366  # angeben!!!
nrOfZeitschritte = zeitraumInTagen * 4 * 24
data_sub = data[0:nrOfZeitschritte]

# ODER....
# data_sub = data['2020-01-01':'2020-01-07 23:45:00']
data_sub = data['2020-01-01':'2020-01-01 23:45:00']
data_sub = data['2020-07-01':'2020-07-07 23:45:00']
# halbes Jahr:
data_sub = data['2020-01-01':'2020-06-30 23:45:00']
data_sub = data
data_sub = data['2020-01-01':'2020-01-15 23:45:00']
data_sub = data['2020-01-01':'2020-01-03 23:45:00']

# Zeit-Index:
aTimeIndex = data_sub.index
aTimeIndex = aTimeIndex.to_pydatetime()  # datetime-Format

################ Bemerkungen: #################
# jetzt hast du ein Dataframe
# So kannst du ein Vektor aufrufen:
P_el_Last = data_sub['P_Netz/MW']
Q_th_Last = data_sub['Q_Netz/MW']
p_el = data_sub['Strompr.€/MWh']

HG_EK_min = 0
HG_EK_max = 100000
HG_VK_min = -100000
HG_VK_max = 0
gP = data_sub['Gaspr.€/MWh']

#############################################################################
nrOfPeriods = len(P_el_Last)
# aTimeSeries = pd.date_range('1/1/2020',periods=nrOfPeriods,freq='15min')
aTimeSeries = datetime.datetime(2020, 1, 1) + np.arange(nrOfPeriods) * datetime.timedelta(hours=0.25)
aTimeSeries = aTimeSeries.astype('datetime64')

##########################################################################

from flixOpt import *
from flixOpt.linear_converters import Boiler, CHP

print('#######################################################################')
print('################### start of modeling #################################')

# Bus-Definition:
#                 Typ         Name              
excessCosts = 1e5
excessCosts = None
Strom = Bus('el', 'Strom', excess_effects_per_flow_hour=excessCosts);
Fernwaerme = Bus('heat', 'Fernwärme', excess_effects_per_flow_hour=excessCosts);
Gas = Bus('fuel', 'Gas', excess_effects_per_flow_hour=excessCosts);
Kohle = Bus('fuel', 'Kohle', excess_effects_per_flow_hour=excessCosts);

# Effects

costs = Effect('costs', '€', 'Kosten', is_standard=True, is_objective=True)
CO2 = Effect('CO2', 'kg', 'CO2_e-Emissionen')  # effectsPerFlowHour = {'costs' : 180} ))
PE = Effect('PE', 'kWh_PE', 'Primärenergie')

# Komponentendefinition:

aGaskessel = Boiler('Kessel', eta=0.85,  # , effects_per_running_hour = {costs:0,CO2:1000},#, effects_per_switch_on = 0
                    Q_th=Flow(label='Q_th', bus=Fernwaerme),  # maxGradient = 5),
                    Q_fu=Flow(label='Q_fu', bus=Gas, size=95, relative_minimum=12 / 95, can_switch_off=True,
                              effects_per_switch_on=1000, values_before_begin=[0]))

aKWK = CHP('BHKW2', eta_th=0.58, eta_el=0.22, effects_per_switch_on=24000,
           P_el=Flow('P_el', bus=Strom),
           Q_th=Flow('Q_th', bus=Fernwaerme),
           Q_fu=Flow('Q_fu', bus=Kohle, size=288, relative_minimum=87 / 288),
           on_values_before_begin=[0])

aSpeicher = Storage('Speicher',
                    charging=Flow('Q_th_load', size=137, bus=Fernwaerme),
                    discharging=Flow('Q_th_unload', size=158, bus=Fernwaerme),
                    capacity_in_flow_hours=684, initial_charge_state=137,
                    minimal_final_charge_state=137, maximal_final_charge_state=158,
                    eta_load=1, eta_unload=1, relative_loss_per_hour=0.001, prevent_simultaneous_charge_and_discharge=True)

TS_Q_th_Last = TimeSeriesData(Q_th_Last)
aWaermeLast = Sink('Wärmelast', sink=Flow('Q_th_Last', bus=Fernwaerme, size=1, fixed_relative_value=TS_Q_th_Last))

# TS with explicit defined weight
TS_P_el_Last = TimeSeriesData(P_el_Last, agg_weight=0.7)  # explicit defined weight
aStromLast = Sink('Stromlast', sink=Flow('P_el_Last', bus=Strom, size=1, fixed_relative_value=TS_P_el_Last))

aKohleTarif = Source('Kohletarif',
                     source=Flow('Q_Kohle', bus=Kohle, size=1000, effects_per_flow_hour={costs: 4.6, CO2: 0.3}))

aGasTarif = Source('Gastarif', source=Flow('Q_Gas', bus=Gas, size=1000, effects_per_flow_hour={costs: gP, CO2: 0.3}))

# 2 TS with same aggType (--> implicit defined weigth = 0.5)
p_feed_in = TimeSeriesData(-(p_el - 0.5), agg_group='p_el')  # weight shared in group p_el
p_sell = TimeSeriesData(p_el + 0.5, agg_group='p_el')
# p_feed_in = p_feed_in.value # only value
# p_sell    = p_sell.value # only value
aStromEinspeisung = Sink('Einspeisung', sink=Flow('P_el', bus=Strom, size=1000, effects_per_flow_hour=p_feed_in))

aStromTarif = Source('Stromtarif',
                     source=Flow('P_el', bus=Strom, size=1000, effects_per_flow_hour={costs: p_sell, CO2: 0.3}))

# Zusammenführung:
flow_system = FlowSystem(aTimeSeries, last_time_step_hours=None)
# flow_system.add_components(aGaskessel,aWaermeLast,aGasTarif)#,aGaskessel2)
flow_system.add_effects(costs)
flow_system.add_effects(CO2, PE)
flow_system.add_components(aGaskessel, aWaermeLast, aStromLast, aGasTarif, aKohleTarif)
flow_system.add_components(aStromEinspeisung, aStromTarif)
flow_system.add_components(aKWK)

flow_system.add_components(aSpeicher)

# flow_system.mainSystem.extractSubSystem([0,1,2])


time_indices = None
# time_indices = [1,3,5]

########################
######## Lösung ########
listOfCalcs = []

# Roh-Rechnung:
if doFullCalc:
    calcFull = FullCalculation('fullModel', flow_system, 'pyomo', time_indices)
    calcFull.do_modeling()

    flow_system.print_model()
    flow_system.print_variables()
    flow_system.print_equations()

    calcFull.solve(solverProps)
    listOfCalcs.append(calcFull)

# segmentierte Rechnung:
if doSegmentedCalc:
    calcSegs = SegmentedCalculation('segModel', flow_system, 'pyomo', time_indices)
    calcSegs.solve(solverProps, segment_length=segmentLen, nr_of_used_steps=nr_of_used_steps)
    listOfCalcs.append(calcSegs)

# aggregierte Berechnung:

if doAggregatedCalc:
    calcAgg = AggregatedCalculation('aggModel', flow_system, 'pyomo')
    calcAgg.do_modeling(periodLengthInHours,
                        nr_of_typical_periods,
                        useExtremeValues,
                        fix_storage_flows,
                        fix_binary_vars_only,
                        percentage_of_period_freedom = percentage_of_period_freedom,
                        costs_of_period_freedom = costs_of_period_freedom,
                        addPeakMax=[TS_Q_th_Last],  # add timeseries of period with maxPeak explicitly
                        addPeakMin=[TS_P_el_Last, TS_Q_th_Last])

    flow_system.print_variables()
    flow_system.print_equations()

    calcAgg.solve(solverProps)
    listOfCalcs.append(calcAgg)

#########################
## some plots directly ##
#########################

# Segment-Plot:
# wenn vorhanden  

if (not calcSegs is None) and (not calcFull is None):
    fig, ax = plt.subplots(figsize=(10, 5))
    plt.plot(calcSegs.time_series_with_end, calcSegs.results_struct.Speicher.charge_state, '-',
             label='chargeState (complete)')
    for system_model in calcSegs.system_models:
        plt.plot(system_model.time_series_with_end, system_model.results_struct.Speicher.charge_state, ':',
                 label='chargeState')

    # plt.plot(calcFull.time_series_with_end, calcFull.results_struct.Speicher.charge_state, '-.', label='chargeState (full)') 
    plt.legend()
    plt.grid()
    plt.show()

    for system_model in calcSegs.system_models:
        plt.plot(system_model.time_series, system_model.results_struct.BHKW2.Q_th.val, label='Q_th_BHKW')
    plt.plot(calcFull.time_series, calcFull.results_struct.BHKW2.Q_th.val, label='Q_th_BHKW')
    plt.legend()
    plt.grid()
    plt.show()

    for system_model in calcSegs.system_models:
        plt.plot(system_model.time_series, system_model.results_struct.global_comp.costs.operation.sum_TS,
                 label='costs')
    plt.plot(calcFull.time_series, calcFull.results_struct.global_comp.costs.operation.sum_TS, ':',
             label='costs (full)')
    plt.legend()
    plt.grid()
    plt.show()

# Ergebnisse Korrektur-Variablen (nur wenn genutzt):
print('######### sum Korr_... (wenn vorhanden) #########')
if calcAgg is not None:
    aggretation_element = list(calcAgg.flow_system.other_elements)[0]
    for var in aggretation_element.model.variables:
        print(var.label_full + ':' + str(sum(var.result())))

print('')

print('############ time durations #####################')

for aResult in listOfCalcs:
    print(aResult.label + ':')
    aResult.listOfModbox[0].describe()
    # print(aResult.infos)
    # print(aResult.duration)
    print('costs: ' + str(aResult.results_struct.global_comp.costs.all.sum))

#######################
### post processing ###
#######################

####### loading #######

import flixOpt.postprocessing as flixPost

listOfResults = []

if doFullCalc:
    full = flixPost.flix_results(calcFull.label)
    listOfResults.append(full)
    # del calcFull

    costs = full.results_struct.global_comp.costs.all.sum

if doAggregatedCalc:
    agg = flixPost.flix_results(calcAgg.label)
    listOfResults.append(agg)
    # del calcAgg
    costs = agg.results_struct.global_comp.costs.all.sum

if doSegmentedCalc:
    seg = flixPost.flix_results(calcSegs.label)
    listOfResults.append(seg)
    # del calcSegs
    costs = seg.results_struct.global_comp.costs.all.sum

###### plotting #######

from flixOpt.plotting import *


# Übersichtsplot:

def uebersichtsPlot(aCalc):
    fig, ax = plt.subplots(figsize=(10, 5))
    plt.title(aCalc.name)

    plotFlow(aCalc, aCalc.results_struct.BHKW2.P_el.val, 'P_el')
    plotFlow(aCalc, aCalc.results_struct.BHKW2.Q_th.val, 'Q_th_BHKW')
    plotFlow(aCalc, aCalc.results_struct.Kessel.Q_th.val, 'Q_th_Kessel')

    plotOn(aCalc, aCalc.results_struct.Kessel.Q_th, 'Q_th_Kessel', -5)
    plotOn(aCalc, aCalc.results_struct.Kessel, 'Kessel', -10)
    plotOn(aCalc, aCalc.results_struct.BHKW2, 'BHKW ', -15)

    plotFlow(aCalc, aCalc.results_struct.Waermelast.Q_th_Last.val, 'Q_th_Last')

    plt.plot(aCalc.time_series, aCalc.results_struct.global_comp.costs.operation.sum_TS, '--',
             label='costs (operating)')

    if hasattr(aCalc.results_struct, 'Speicher'):
        plt.step(aCalc.time_series, aCalc.results_struct.Speicher.Q_th_unload.val, where='post',
                 label='Speicher_unload')
        plt.step(aCalc.time_series, aCalc.results_struct.Speicher.Q_th_load.val, where='post', label='Speicher_load')
        plt.plot(aCalc.time_series_with_end, aCalc.results_struct.Speicher.charge_state, label='charge_state')
    # plt.step(aCalc.time_series, aCalc.results_struct.Speicher., label='Speicher_load')
    plt.grid(axis='y')
    plt.legend(loc='center left', bbox_to_anchor=(1., 0.5))
    plt.show()


for aResult in listOfResults:
    uebersichtsPlot(aResult)

for aResult in listOfResults:
    # Komponenten-Plots:
    aResult: flixPost.flix_results
    aResult.plotInAndOuts('Fernwaerme', stacked=True)

print('## penalty: ##')
for aResult in listOfResults:
    print('Kosten penalty Sim1: ', sum(aResult.results_struct.global_comp.penalty.sum_TS))

# loading yaml-datei:
with open(agg.filename_infos, 'rb') as f:
    infos = yaml.safe_load(f)

# periods order of aggregated calculation:
print('periods_order of aggregated calc: ' + str(infos['calculation']['aggregatedProps']['periods_order']))
