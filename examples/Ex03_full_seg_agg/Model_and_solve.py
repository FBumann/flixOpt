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
gapFrac        = 0.0005
solver_name    = 'cbc'
# solver_name    = 'gurobi'
# solver_name    = 'glpk'
solverProps = {'gapFrac': gapFrac, 'solver': solver_name, 'displaySolverOutput' : True, 'threads':16}   

nameSuffix = '_' + solver_name # for saving-file

## Auswahl Rechentypen: ##

doFullCalc = True
# doFullCalc = False

doSegmentedCalc = True
# doSegmentedCalc = False

doAggregatedCalc = True
# doAggregatedCalc = False

## segmented Properties: ##

nrOfUsedSteps = 96*1    
segmentLen = nrOfUsedSteps + 1*96


## aggregated Properties: ##

periodLengthInHours = 6
noTypicalPeriods    = 21
noTypicalPeriods    = 4
useExtremeValues    = True
# useExtremeValues    = False
fixBinaryVarsOnly   = False
# fixBinaryVarsOnly   = True
fixStorageFlows     = True
# fixStorageFlows     = False    
percentageOfPeriodFreedom = 0
costsOfPeriodFreedom = 0

import pandas as pd
import numpy as np
import datetime
import os
import matplotlib.pyplot as plt
import time

calcFull = None
calcSegs = None
calcAgg  = None

# #########################################################################
# ######################  Data Import  ####################################

# Daten einlesen
filename = os.path.join(os.path.dirname(__file__), "Zeitreihen2020.csv")
ts_raw = pd.read_csv(filename, index_col=0)
ts_raw = ts_raw.sort_index()

#ts = ts_raw['2020-01-01 00:00:00':'2020-12-31 23:45:00']  # EDITIEREN FÜR ZEITRAUM
ts = ts_raw['2020-01-01 00:00:00':'2020-12-31 23:45:00']
# ts['Kohlepr.€/MWh'] = 4.6
ts.set_index(pd.to_datetime(ts.index), inplace = True)   # str to datetime
data = ts



time_zero = time.time()

# ENTWEDER...
# Zeitaussschnitt definieren
zeitraumInTagen = 366 # angeben!!!
nrOfZeitschritte = zeitraumInTagen*4*24
data_sub = data[0:nrOfZeitschritte]

# ODER....
# data_sub = data['2020-01-01':'2020-01-07 23:45:00']
data_sub = data['2020-01-01':'2020-01-01 23:45:00']
data_sub = data['2020-07-01':'2020-07-07 23:45:00']
#halbes Jahr:
data_sub = data['2020-01-01':'2020-06-30 23:45:00']
data_sub = data
data_sub = data['2020-01-01':'2020-01-15 23:45:00']
data_sub = data['2020-01-01':'2020-01-03 23:45:00']


# Zeit-Index:
aTimeIndex = data_sub.index
aTimeIndex = aTimeIndex.to_pydatetime() # datetime-Format

################ Bemerkungen: #################
#jetzt hast du ein Dataframe
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
aTimeSeries = datetime.datetime(2020, 1,1) +  np.arange(nrOfPeriods) * datetime.timedelta(hours=0.25)
aTimeSeries = aTimeSeries.astype('datetime64')

##########################################################################

from flixOpt.flixStructure import *
from flixOpt.flixComps    import *
from flixOpt.flixBasicsPublic import *

import pandas as pd
import logging as log
import os # für logging

root = logging.getLogger()
root.setLevel(os.environ.get("LOGLEVEL", "DEBUG"))
root.setLevel(os.environ.get("LOGLEVEL", "INFO"))

log.warning('test warning')
log.info   ('test info')
log.debug  ('test debung')


print('#######################################################################')
print('################### start of modeling #################################')


# Bus-Definition:
#                 Typ         Name              
excessCosts = 1e5
excessCosts = None
Strom      = Bus('el', 'Strom', excessCostsPerFlowHour = excessCosts);
Fernwaerme = Bus('heat', 'Fernwärme', excessCostsPerFlowHour = excessCosts);
Gas        = Bus('fuel', 'Gas', excessCostsPerFlowHour = excessCosts);
Kohle      = Bus('fuel', 'Kohle', excessCostsPerFlowHour = excessCosts);

# Effects

costs = Effect('costs', '€', 'Kosten', isStandard = True, isObjective = True)
CO2   = Effect('CO2', 'kg', 'CO2_e-Emissionen') # effectsPerFlowHour = {'costs' : 180} ))
PE    = Effect('PE', 'kWh_PE', 'Primärenergie')

# Komponentendefinition:

aGaskessel = Boiler('Kessel', eta  = 0.85,  # , costsPerRunningHour = {costs:0,CO2:1000},#, switchOnCosts = 0
                    Q_th = Flow(label   ='Q_th', bus = Fernwaerme),  # maxGradient = 5),
                    Q_fu = Flow(label   ='Q_fu', bus = Gas, nominal_val = 95, min_rel =12 / 95, iCanSwitchOff = True, switchOnCosts=1000, valuesBeforeBegin=[0]))


aKWK  = CHP('BHKW2', eta_th = 0.58, eta_el=0.22, switchOnCosts =  24000,
            P_el = Flow('P_el', bus = Strom),
            Q_th = Flow('Q_th', bus = Fernwaerme),
            Q_fu = Flow('Q_fu', bus = Kohle, nominal_val = 288, min_rel =87 / 288), on_valuesBeforeBegin = [0])



aSpeicher = Storage('Speicher',
                    inFlow  = Flow('Q_th_load', nominal_val = 137, bus = Fernwaerme),
                    outFlow = Flow('Q_th_unload', nominal_val = 158, bus = Fernwaerme),
                    capacity_inFlowHours = 684,
                    chargeState0_inFlowHours = 137,
                    charge_state_end_min = 137,
                    charge_state_end_max = 158,
                    eta_load = 1, eta_unload = 1,
                    fracLossPerHour = 0.001,
                    avoidInAndOutAtOnce = True)
 

TS_Q_th_Last = TimeSeriesRaw(Q_th_Last)
aWaermeLast = Sink  ('Wärmelast', sink   = Flow('Q_th_Last', bus = Fernwaerme, nominal_val = 1, val_rel = TS_Q_th_Last))

# TS with explicit defined weight
TS_P_el_Last = TimeSeriesRaw(P_el_Last, agg_weight = 0.7) # explicit defined weight
aStromLast = Sink('Stromlast', sink = Flow('P_el_Last', bus = Strom, nominal_val = 1, val_rel = TS_P_el_Last))

aKohleTarif = Source('Kohletarif', source = Flow('Q_Kohle', bus = Kohle, nominal_val = 1000, costsPerFlowHour= {costs: 4.6, CO2: 0.3}))

aGasTarif = Source('Gastarif', source = Flow('Q_Gas', bus = Gas, nominal_val = 1000, costsPerFlowHour= {costs: gP, CO2: 0.3}))


# 2 TS with same aggType (--> implicit defined weigth = 0.5)
p_feed_in = TimeSeriesRaw(-(p_el - 0.5), agg_type='p_el') # weight shared in group p_el
p_sell    = TimeSeriesRaw(p_el + 0.5, agg_type='p_el')
# p_feed_in = p_feed_in.value # only value
# p_sell    = p_sell.value # only value
aStromEinspeisung = Sink  ('Einspeisung', sink   = Flow('P_el', bus = Strom, nominal_val = 1000, costsPerFlowHour = p_feed_in))
aStromEinspeisung.sink.costsPerFlowHour[None].aggregation_weight = .5

aStromTarif       = Source('Stromtarif', source = Flow('P_el', bus = Strom, nominal_val = 1000, costsPerFlowHour= {costs: p_sell, CO2: 0.3}))
aStromTarif.source.costsPerFlowHour[costs].aggregation_weight = .5

# Zusammenführung:
system = System(aTimeSeries, dt_last=None)
# system.addComponents(aGaskessel,aWaermeLast,aGasTarif)#,aGaskessel2)
system.addEffects(costs)
system.addEffects(CO2, PE)
system.addComponents(aGaskessel,aWaermeLast,aStromLast,aGasTarif,aKohleTarif)
system.addComponents(aStromEinspeisung,aStromTarif)
system.addComponents(aKWK)

system.addComponents(aSpeicher)

# system.mainSystem.extractSubSystem([0,1,2])


chosenEsTimeIndexe = None
# chosenEsTimeIndexe = [1,3,5]

########################
######## Lösung ########
listOfCalcs = []


# Roh-Rechnung:
if doFullCalc:
  calcFull = Calculation('fullModel', system, 'pyomo', chosenEsTimeIndexe)
  calcFull.doModelingAsOneSegment()
  
  system.printModel()
  system.printVariables()
  system.printEquations()
    
  calcFull.solve(solverProps, nameSuffix=nameSuffix)
  listOfCalcs.append(calcFull)

# segmentierte Rechnung:
if doSegmentedCalc :

   calcSegs = Calculation('segModel', system, 'pyomo', chosenEsTimeIndexe)
   calcSegs.doSegmentedModelingAndSolving(solverProps, segmentLen=segmentLen, nrOfUsedSteps=nrOfUsedSteps, nameSuffix = nameSuffix)
   listOfCalcs.append(calcSegs)

# aggregierte Berechnung:

if doAggregatedCalc :    
    calcAgg = Calculation('aggModel', system, 'pyomo')
    calcAgg.doAggregatedModeling(periodLengthInHours, 
                                 noTypicalPeriods, 
                                 useExtremeValues, 
                                 fixStorageFlows, 
                                 fixBinaryVarsOnly, 
                                 percentageOfPeriodFreedom = percentageOfPeriodFreedom,
                                 costsOfPeriodFreedom = costsOfPeriodFreedom,
                                 addPeakMax=[TS_Q_th_Last], # add timeseries of period with maxPeak explicitly
                                 addPeakMin=[TS_P_el_Last, TS_Q_th_Last]
                                 )
    
    system.printVariables()
    system.printEquations()
    
    calcAgg.solve(solverProps, nameSuffix = nameSuffix)
    listOfCalcs.append(calcAgg)



#########################
## some plots directly ##
#########################

# Segment-Plot:
# wenn vorhanden  

if (not calcSegs is None) and (not calcFull is None):
    fig, ax = plt.subplots(figsize=(10, 5))
    plt.plot(calcSegs.timeSeriesWithEnd, calcSegs.results_struct.Speicher.charge_state, '-', label='chargeState (complete)') 
    for aModBox in calcSegs.segmentModBoxList:  
      plt.plot(aModBox.timeSeriesWithEnd, aModBox.results_struct.Speicher.charge_state, ':', label='chargeState') 

    # plt.plot(calcFull.timeSeriesWithEnd, calcFull.results_struct.Speicher.charge_state, '-.', label='chargeState (full)') 
    plt.legend()
    plt.grid()
    plt.show()

    for aModBox in calcSegs.segmentModBoxList:  
      plt.plot(aModBox.timeSeries       , aModBox.results_struct.BHKW2.Q_th.val, label='Q_th_BHKW') 
    plt.plot(calcFull.timeSeries       , calcFull.results_struct.BHKW2.Q_th.val, label='Q_th_BHKW') 
    plt.legend()
    plt.grid()
    plt.show()


    for aModBox in calcSegs.segmentModBoxList:  
      plt.plot(aModBox.timeSeries, aModBox.results_struct.globalComp.costs.operation.sum_TS, label='costs') 
    plt.plot(calcFull.timeSeries       , calcFull.results_struct.globalComp.costs.operation.sum_TS, ':', label='costs (full)') 
    plt.legend()
    plt.grid()
    plt.show()


# Ergebnisse Korrektur-Variablen (nur wenn genutzt):
print('######### sum Korr_... (wenn vorhanden) #########')
if calcAgg is not None:
  aggretation_element=list(calcAgg.system.setOfOtherElements)[0]
  for var in aggretation_element.model.variables:
    print(var.label_full + ':' + str( sum(var.getResult())))

print('')

print('############ time durations #####################')

for aResult in listOfCalcs:
  print(aResult.label + ':')
  aResult.listOfModbox[0].printNoEqsAndVars()
  # print(aResult.infos)
  # print(aResult.duration)
  print('costs: ' + str(aResult.results_struct.globalComp.costs.all.sum))

#######################
### post processing ###
#######################

####### loading #######

import flixOpt.flixPostprocessing as flixPost

listOfResults = []

if doFullCalc:
    full = flixPost.flix_results(calcFull.nameOfCalc)
    listOfResults.append(full)
    # del calcFull
    
    costs = full.results_struct.globalComp.costs.all.sum

if doAggregatedCalc:
    agg = flixPost.flix_results(calcAgg.nameOfCalc)
    listOfResults.append(agg)
    # del calcAgg
    costs = agg.results_struct.globalComp.costs.all.sum

if doSegmentedCalc:
    seg = flixPost.flix_results(calcSegs.nameOfCalc)
    listOfResults.append(seg)
    # del calcSegs
    costs = seg.results_struct.globalComp.costs.all.sum


###### plotting #######

import matplotlib.pyplot as plt
from flixOpt.flixPlotHelperFcts import *

# Übersichtsplot:

def uebersichtsPlot(aCalc):
  fig, ax = plt.subplots(figsize=(10, 5))
  plt.title(aCalc.label)
    
  plotFlow(aCalc, aCalc.results_struct.BHKW2.P_el.val,  'P_el')
  plotFlow(aCalc, aCalc.results_struct.BHKW2.Q_th.val,  'Q_th_BHKW')
  plotFlow(aCalc, aCalc.results_struct.Kessel.Q_th.val, 'Q_th_Kessel')
  
  plotOn(aCalc, aCalc.results_struct.Kessel.Q_th, 'Q_th_Kessel', -5)
  plotOn(aCalc, aCalc.results_struct.Kessel,      'Kessel'     , -10)
  plotOn(aCalc, aCalc.results_struct.BHKW2,       'BHKW '      , -15)
  
  plotFlow(aCalc, aCalc.results_struct.Waermelast.Q_th_Last.val, 'Q_th_Last')
  
  plt.plot(aCalc.timeSeries, aCalc.results_struct.globalComp.costs.operation.sum_TS, '--', label='costs (operating)') 
  
  if hasattr(aCalc.results_struct,'Speicher'):
    plt.step(aCalc.timeSeries, aCalc.results_struct.Speicher.Q_th_unload.val, where = 'post', label='Speicher_unload')
    plt.step(aCalc.timeSeries, aCalc.results_struct.Speicher.Q_th_load.val  , where = 'post', label='Speicher_load')
    plt.plot(aCalc.timeSeriesWithEnd, aCalc.results_struct.Speicher.charge_state   , label='charge_state')
  # plt.step(aCalc.timeSeries, aCalc.results_struct.Speicher., label='Speicher_load')
  plt.grid(axis='y')
  plt.legend(loc='center left', bbox_to_anchor=(1., 0.5))
  plt.show()


for aResult in listOfResults:
  uebersichtsPlot(aResult)

for aResult in listOfResults:  
  # Komponenten-Plots:
  aResult: flixPost.flix_results
  aResult.plotInAndOuts('Fernwaerme', stacked = True)

print('## penalty: ##')
for aResult in listOfResults:
  print('Kosten penalty Sim1: ',sum(aResult.results_struct.globalComp.penalty.sum_TS))


# loading yaml-datei:
with open(agg.filename_infos,'rb') as f:
    infos = yaml.safe_load(f)

# periods order of aggregated calculation:
print('periodsOrder of aggregated calc: ' + str(infos['calculation']['aggregatedProps']['periodsOrder']))