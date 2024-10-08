# -*- coding: utf-8 -*-
"""
Created on Thu Jun 16 11:19:17 2022
developed by Felix Panitz* and Peter Stange*
* at Chair of Building Energy Systems and Heat Supply, 
  Technische Universität Dresden
"""

import numpy as np
import datetime

from flixOpt import *
from flixOpt.linear_converters import Boiler, CHP

### some Solver-Inputs: ###
displaySolverOutput = False # ausführlicher Solver-Output.
displaySolverOutput = True  # ausführlicher Solver-Output.
gapFrac = 0.0001 # solver-gap
timelimit = 3600 # seconds until solver abort
# choose the solver, you have installed:
# solver_name = 'glpk' # warning, glpk quickly has numerical problems with binaries (big and epsilon)
# solver_name = 'gurobi'
solver_name = 'highs'
solverProps = {'mip_gap': gapFrac,
               'time_limit_seconds': timelimit,
               'solver_name': solver_name,
               'solver_output_to_console' : displaySolverOutput,
               }

#####################
## some timeseries ##
Q_th_Last = np.array([30., 0., 90., 110, 110 , 20, 20, 20, 20]) # kW; thermal load profile in
p_el = 1/1000*np.array([80., 80., 80., 80 , 80, 80, 80, 80, 80]) # €/kWh; feed_in tariff;
aTimeSeries = datetime.datetime(2020, 1,1) +  np.arange(len(Q_th_Last)) * datetime.timedelta(hours=1) # creating timeseries
aTimeSeries = aTimeSeries.astype('datetime64') # needed format for timeseries in flixOpt
max_emissions_per_hour = 1000 # kg per timestep

print('#######################################################################')
print('################### start of modeling #################################')

# #####################
# ## Bus-Definition: ##
# define buses for the 3 used media:
Strom = Bus('el', 'Strom') # balancing node/bus of electricity
Fernwaerme = Bus('heat', 'Fernwärme') # balancing node/bus of heat
Gas = Bus('fuel', 'Gas') # balancing node/bus of gas

# ########################
# ## Effect-Definition: ##
costs = Effect('costs', '€', 'Kosten',  # name, unit, description
               is_standard= True,  # standard effect --> shorter input possible (without effect as a key)
               is_objective= True) # defining costs as objective of optimiziation

CO2   = Effect('CO2', 'kg', 'CO2_e-Emissionen',  # name, unit, description
               specific_share_to_other_effects_operation= {costs: 0.2}, maximum_operation_per_hour= max_emissions_per_hour) # 0.2 €/kg; defining links between effects, here CO2-price

# ###########################
# ## Component-Definition: ##

# # 1. heat supply units: #

# 1.a) defining a boiler
aBoiler = Boiler('Boiler', eta = 0.5,  # name, efficiency factor
                 # defining the output-flow = thermal -flow
                 Q_th = Flow(label ='Q_th',  # name of flow
                             bus = Fernwaerme,  # define, where flow is linked to (here: Fernwaerme-Bus)
                             size=50,  # kW; nominal_size of boiler
                             relative_minimum = 5/50,  # 10 % minimum load, i.e. 5 kW
                             relative_maximum = 1,  # 100 % maximum load, i.e. 50 kW
                             ),
                 # defining the input-flow = fuel-flow
                 Q_fu = Flow(label ='Q_fu',  # name of flow
                             bus = Gas)  # define, where flow is linked to (here: Gas-Bus)
                 )

# 2.b) defining a CHP unit:
aKWK  = CHP('CHP_unit', eta_th = 0.5, eta_el = 0.4,  # name, thermal efficiency, electric efficiency
            # defining flows:
            P_el = Flow('P_el', bus = Strom,
                        size=60,  # 60 kW_el
                        relative_minimum = 5/60, ),  # 5 kW_el, min- and max-load (100%) are here defined through this electric flow
            Q_th = Flow('Q_th', bus = Fernwaerme),
            Q_fu = Flow('Q_fu', bus = Gas))

# # 2. storage #

aSpeicher = Storage('Speicher',
                    charging= Flow('Q_th_load', bus = Fernwaerme, size=1e4),  # load-flow, maximum load-power: 1e4 kW
                    discharging= Flow('Q_th_unload', bus = Fernwaerme, size=1e4),  # unload-flow, maximum load-power: 1e4 kW
                    capacity_in_flow_hours=InvestParameters(fix_effects=20, fixed_size=30, optional=False),  # 30 kWh; storage capacity
                    initial_charge_state=0,  # empty storage at first time step
                    relative_maximum_charge_state=1 / 100 * np.array([80., 70., 80., 80 , 80, 80, 80, 80, 80, 80]),
                    eta_load=0.9, eta_unload=1,  #loading efficiency factor, unloading efficiency factor
                    relative_loss_per_hour=0.08,  # 8 %/h; 8 percent of storage loading level is lossed every hour
                    prevent_simultaneous_charge_and_discharge=True,  # no parallel loading and unloading at one time
                    )
 
# # 3. sinks and sources #

# sink of heat load:
aWaermeLast = Sink('Wärmelast',
                   # defining input-flow:
                   sink   = Flow('Q_th_Last',  # name
                                 bus = Fernwaerme,  # linked to bus "Fernwaerme"
                                 size=1,  # sizeue
                                 fixed_relative_value = Q_th_Last)) # fixed profile
                                   # relative fixed values (timeseries) of the flow
                                   # value = fixed_relative_value * size
    
# source of gas:
aGasTarif = Source('Gastarif',
                   # defining output-flow:
                   source = Flow('Q_Gas',  # name
                                 bus = Gas,  # linked to bus "Gas"
                                 size=1000,  # nominal size, i.e. 1000 kW maximum
                                 # defining effect-shares.
                                 #    Here not only "costs", but also CO2-emissions:
                                 effects_per_flow_hour= {costs: 0.04, CO2: 0.3})) # 0.04 €/kWh, 0.3 kg_CO2/kWh

# sink of electricity feed-in:
aStromEinspeisung = Sink('Einspeisung',
                         # defining input-flow:
                         sink=Flow('P_el',  # name
                                   bus = Strom,  # linked to bus "Strom"
                                   effects_per_flow_hour=-1 * p_el)) # gains (negative costs) per kWh


# ######################################################
# ## Build energysystem - Registering of all elements ##

flow_system = FlowSystem(aTimeSeries, last_time_step_hours=None) # creating flow_system, (duration of last timestep is like the one before)
flow_system.add_components(aSpeicher) # adding components
flow_system.add_effects(costs, CO2) # adding defined effects
flow_system.add_components(aBoiler, aWaermeLast, aGasTarif) # adding components
flow_system.add_components(aStromEinspeisung) # adding components
flow_system.add_components(aKWK) # adding components


# choose used timeindexe:
time_indices = None # all timeindexe are used
# time_indices = [1,3,5] # only a subset shall be used

# ## modeling the flow_system ##

# 1. create a Calculation 
aCalc = FullCalculation('Sim1',  # name of calculation
                    flow_system,  # energysystem to calculate
                     'pyomo',  # optimization modeling language (only "pyomo" implemented, yet)
                    time_indices) # used time steps

# 2. modeling:
aCalc.do_modeling() # mathematic modeling of flow_system

# 3. (optional) print Model-Characteristics:
flow_system.print_model() # string-output:network structure of model
flow_system.print_variables() # string output: variables of model
flow_system.print_equations() # string-output: equations of model


# #################
# ## calculation ##

aCalc.solve(solverProps)
# .. results are saved under /results/
# these files are written:
# -> json-file with model- and solve-Informations!
# -> log-file
# -> data-file


# ####################
# # PostProcessing: ##
# ####################


# ##### loading results from output-files ######
import flixOpt.postprocessing as flixPost

label = aCalc.name
print(label)
# loading results, creating postprocessing Object:
aCalc_post = flixPost.flix_results(label) 

# ## plotting ##
# plotting all in- and out-flows of bus "Fernwaerme":
fig1 = aCalc_post.plotInAndOuts('Fernwaerme',stacked=True)
fig1.savefig('results/test1')
fig2 = aCalc_post.plotInAndOuts('Fernwaerme',stacked=True, plotAsPlotly = True)
fig2.show()
fig2.write_html('results/test2.html')
fig3 = aCalc_post.plotInAndOuts('Strom',stacked=True, plotAsPlotly = True)
fig3.show()
fig4 = aCalc_post.plotShares('Fernwaerme',plotAsPlotly=True)
fig4.show()


##############################
# ## access to timeseries: ##

# 1. direct access:
# (not recommended, better use postProcessing instead, see next)
print('# direct access:')
print('way 1:')
print(aCalc.results['Boiler']['Q_th']['val']) # access through dict
print('way 2:')
print(aBoiler.Q_th.model.variables["val"].result) # access directly through component/flow-variables
#    (warning: there are only temporarily the results of the last executed solve-command of the flow_system)

# 2. post-processing access:
print('# access to timeseries:#')
print('way 1:')
print(aCalc_post.results['Boiler']['Q_th']['val']) # access through dict
print('way 2:')
# find flow:
aFlow_post = aCalc_post.getFlowsOf('Fernwaerme','Boiler')[0][0] # getting flow
print(aFlow_post.results['val']) # access through cFlow_post object

# ###############################################
# ## saving csv of special flows of bus "Fernwaerme" ##
aCalc_post.to_csv('Fernwaerme', 'results/FW.csv')
    
