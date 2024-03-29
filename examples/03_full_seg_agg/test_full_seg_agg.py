# -*- coding: utf-8 -*-
"""
Created on Thu Nov 10 15:23:25 2022

@author: Panitz
"""

# just for testing values - not up to date!
from nose.tools import eq_
import os, sys
sys.path.append(os.path.dirname(__file__)) # todo: not nice
print(sys.path)
#executing example:
import Model_and_solve
import numpy as np

def test_full():
    if Model_and_solve.doFullCalc:
        costs = Model_and_solve.full.results_struct.globalComp.costs.all.sum
        eq_(np.round(costs,-1), np.round(343613,-1))
def test_agg():
    if Model_and_solve.doAggregatedCalc:
        costs = Model_and_solve.agg.results_struct.globalComp.costs.all.sum
        eq_(np.round(costs,-3) , np.round(342967.0,-3)) 
def test_segmented():
    if Model_and_solve.doSegmentedCalc:
        costs = Model_and_solve.seg.results_struct.globalComp.costs.all.sum        
        eq_ (np.round(sum(costs),-1) , np.round(sum([210569.29522477, 270926.44574398]),-1))  
