#!/usr/bin/python3
# -*- coding: utf-8 -*-
# Copyright (c) 2019 Huawei Technologies Co., Ltd.
# A-Tune is licensed under the Mulan PSL v2.
# You can use this software according to the terms and conditions of the Mulan PSL v2.
# You may obtain a copy of Mulan PSL v2 at:
#     http://license.coscl.org.cn/MulanPSL2
# THIS SOFTWARE IS PROVIDED ON AN "AS IS" BASIS, WITHOUT WARRANTIES OF ANY KIND, EITHER EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO NON-INFRINGEMENT, MERCHANTABILITY OR FIT FOR A PARTICULAR
# PURPOSE.
# See the Mulan PSL v2 for more details.
# Create: 2019-10-29

"""
This class is used to find optimal settings and generate optimized profile.
"""

import logging
import multiprocessing
import numpy as np
import sys
from skopt.optimizer import gp_minimize, dummy_minimize
from sklearn.linear_model import Lasso
from sklearn.preprocessing import StandardScaler

from analysis.optimizer.abtest_tuning_manager import ABtestTuningManager
from analysis.optimizer.knob_sampling_manager import KnobSamplingManager
from analysis.optimizer.tpe_optimizer import TPEOptimizer
from analysis.optimizer.weighted_ensemble_feature_selector import WeightedEnsembleFeatureSelector

LOGGER = logging.getLogger(__name__)


class Optimizer(multiprocessing.Process):
    """find optimal settings and generate optimized profile"""

    def __init__(self, name, params, child_conn, engine="bayes", max_eval=50, x0=None, y0=None, n_random_starts=20):
        super(Optimizer, self).__init__(name=name)
        self.knobs = params
        self.child_conn = child_conn
        self.engine = engine
        self.max_eval = int(max_eval)
        self.split_count = 5 #should be set by YAML client
        self.ref = []
        self.x0 = x0
        self.y0 = y0
        self._n_random_starts = 20 if n_random_starts is None else n_random_starts

    def build_space(self):
        """build space"""
        objective_params_list = []
        for p_nob in self.knobs:
            if p_nob['type'] == 'discrete':
                items = self.handle_discrete_data(p_nob)
                objective_params_list.append(items)
            elif p_nob['type'] == 'continuous':
                r_range = p_nob['range']
                if r_range is None or len(r_range) != 2:
                    raise ValueError("the item of the scope value of {} must be 2"
                                     .format(p_nob['name']))
                if p_nob['dtype'] == 'int':
                    try:
                        ref_value = int(p_nob['ref'])
                        r_range[0] = int(r_range[0])
                        r_range[1] = int(r_range[1])
                    except ValueError:
                        raise ValueError("the ref value of {} is not an integer value"
                                 .format(p_nob['name']))
                elif p_nob['dtype'] == 'float':
                    try:
                        ref_value = float(p_nob['ref'])
                        r_range[0] = float(r_range[0])
                        r_range[1] = float(r_range[1])
                    except ValueError:
                        raise ValueError("the ref value of {} is not an integer value"
                                 .format(p_nob['name']))

                if ref_value < r_range[0] or ref_value > r_range[1]:
                    raise ValueError("the ref value of {} is out of range".format(p_nob['name']))
                self.ref.append(ref_value)
                objective_params_list.append((r_range[0], r_range[1]))
            else:
                raise ValueError("the type of {} is not supported".format(p_nob['name']))
        return objective_params_list

    def handle_discrete_data(self, p_nob):
        """handle discrete data"""
        if p_nob['dtype'] == 'int':
            items = p_nob['items']
            if items is None:
                items = []
            r_range = p_nob['range']
            step = 1
            if 'step' in p_nob.keys():
                step = 1 if p_nob['step'] < 1 else p_nob['step']
            if r_range is not None:
                length = len(r_range) if len(r_range) % 2 == 0 else len(r_range) - 1
                for i in range(0, length, 2):
                    items.extend(list(np.arange(r_range[i], r_range[i + 1] + 1, step=step)))
            items = list(set(items))
            try:
                ref_value = int(p_nob['ref'])
            except ValueError:
                raise ValueError("the ref value of {} is not an integer value"
                                 .format(p_nob['name']))
            if ref_value not in items:
                items.append(ref_value)
            self.ref.append(ref_value)
            return items
        if p_nob['dtype'] == 'float':
            items = p_nob['items']
            if items is None:
                items = []
            r_range = p_nob['range']
            step = 0.1
            if 'step' in p_nob.keys():
                step = 0.1 if p_nob['step'] <= 0 else p_nob['step']
            if r_range is not None:
                length = len(r_range) if len(r_range) % 2 == 0 else len(r_range) - 1
                for i in range(0, length, 2):
                    items.extend(list(np.arange(r_range[i], r_range[i + 1], step=step)))
            items = list(set(items))
            try:
                ref_value = float(p_nob['ref'])
            except ValueError:
                raise ValueError("the ref value of {} is not a float value"
                                 .format(p_nob['name']))
            if ref_value not in items:
                items.append(ref_value)
            self.ref.append(ref_value)
            return items
        if p_nob['dtype'] == 'string':
            items = p_nob['options']
            keys = []
            length = len(self.ref)
            for key, value in enumerate(items):
                keys.append(key)
                if p_nob['ref'] == value:
                    self.ref.append(key)
            if len(self.ref) == length:
                raise ValueError("the ref value of {} is out of range"
                                 .format(p_nob['name']))
            return keys
        raise ValueError("the dtype of {} is not supported".format(p_nob['name']))

    @staticmethod
    def feature_importance(options, performance, labels):
        """feature importance"""
        options = StandardScaler().fit_transform(options)
        lasso = Lasso()
        lasso.fit(options, performance)
        result = zip(lasso.coef_, labels)
        total_sum = sum(map(abs, lasso.coef_))
        if total_sum == 0:
            return ", ".join("%s: 0" % label for label in labels)
        result = sorted(result, key=lambda x: -np.abs(x[0]))
        rank = ", ".join("%s: %s%%" % (label, round(coef * 100 / total_sum, 2))
                         for coef, label in result)
        return rank

    def _get_intvalue_from_knobs(self, kv):
        """get the int value from knobs if dtype if string"""
        x_each = []
        for p_nob in self.knobs:
            if p_nob['name'] not in kv.keys():
                raise ValueError("the param {} is not in the x0 ref".format(p_nob['name']))
            if p_nob['dtype'] != 'string':
                x_each.append(int(kv[p_nob['name']]))
                continue
            options = p_nob['options']
            for key, value in enumerate(options):
                if value != kv[p_nob['name']]:
                    continue
                x_each.append(key)
        return x_each

    def transfer(self):
        """transfer ref x0 to int, y0 to float"""
        list_ref_x = []
        list_ref_y = []
        if self.x0 is None or self.y0 is None:
            return (list_ref_x, list_ref_y)

        for xValue in self.x0:
            kv = {}
            if len(xValue) != len(self.knobs):
                raise ValueError("x0 is not the same length with knobs")

            for i, val in enumerate(xValue):
                params = val.split("=")
                if len(params) != 2:
                    raise ValueError("the param format of {} is not correct".format(params))
                kv[params[0]] = params[1]

            ref_x = self._get_intvalue_from_knobs(kv)
            if len(ref_x) != len(self.knobs):
                raise ValueError("tuning parameter is not the same length with knobs")
            list_ref_x.append(ref_x)
        list_ref_y = [float(y) for y in self.y0]
        return (list_ref_x, list_ref_y)

    def run(self):
        """start the tuning process"""
        def objective(var):
            """objective method receive the benchmark result and send the next parameters"""
            iterResult = {}
            for i, knob in enumerate(self.knobs):
                if knob['dtype'] == 'string':
                    params[knob['name']] = knob['options'][var[i]]
                else:
                    params[knob['name']] = var[i]
            
            iterResult["param"] = params
            self.child_conn.send(iterResult)
            result = self.child_conn.recv()
            x_num = 0.0
            eval_list = result.split(',')
            for value in eval_list:
                num = float(value)
                x_num = x_num + num
            options.append(var)
            performance.append(x_num)
            return x_num

        params = {}
        options = []
        performance = []
        labels = []
        try:
            params_space = self.build_space()
            ref_x, ref_y = self.transfer()
            if len(ref_x) == 0:
                ref_x = self.ref
                ref_y = None
            if not isinstance(ref_x[0], (list, tuple)):
                ref_x = [ref_x]

            LOGGER.info('x0: %s', ref_x)
            LOGGER.info('y0: %s', ref_y)

            if ref_x is not None and isinstance(ref_x[0], (list, tuple)):
                self._n_random_starts = 0 if len(ref_x) >= self._n_random_starts \
                        else self._n_random_starts - len(ref_x) + 1

            LOGGER.info('n_random_starts parameter is: %d', self._n_random_starts)
            LOGGER.info("Running performance evaluation.......")
            if self.engine == 'random':
                ret = dummy_minimize(objective, params_space, n_calls=self.max_eval)
            elif self.engine == 'bayes':
                ret = gp_minimize(objective, params_space, n_calls=self.max_eval, \
                                   n_random_starts=self._n_random_starts, x0=ref_x, y0=ref_y)
            elif self.engine == 'abtest':
                abtuning_manager = ABtestTuningManager(self.knobs, self.child_conn, self.split_count)
                options, performance = abtuning_manager.do_abtest_tuning_abtest()
                params = abtuning_manager.get_best_params()
                options = abtuning_manager.get_options_index(options) # convert string option into index
            elif self.engine == 'lhs':
                knobsampling_manager = KnobSamplingManager(self.knobs, self.child_conn, self.max_eval, self.split_count)
                options = knobsampling_manager.get_knob_samples()
                performance = knobsampling_manager.do_knob_sampling_test(options)
                params = knobsampling_manager.get_best_params(options, performance)
            elif self.engine == 'tpe':
                tpe_opt = TPEOptimizer(self.knobs, self.child_conn, self.max_eval)
                best_params = tpe_opt.tpe_minimize_tuning()
                finalParam = {}
                finalParam["finished"] = True
                finalParam["param"] = best_params
                self.child_conn.send(finalParam)
                return best_params
            LOGGER.info("Minimization procedure has been completed.")
        except ValueError as value_error:
            LOGGER.error('Value Error: %s', repr(value_error))
            self.child_conn.send(value_error)
            return None
        except RuntimeError as runtime_error:
            LOGGER.error('Runtime Error: %s', repr(runtime_error))
            self.child_conn.send(runtime_error)
            return None
        except Exception as e:
            LOGGER.error('Unexpected Error: %s', repr(e))
            self.child_conn.send(Exception("Unexpected Error:", repr(e)))
            return None

        for i, knob in enumerate(self.knobs):
            if knob['dtype'] == 'string':
                params[knob['name']] = knob['options'][ret.x[i]]
            else:
                params[knob['name']] = ret.x[i]
            labels.append(knob['name'])
        
        LOGGER.info("Optimized result: %s", params)
        LOGGER.info("The optimized profile has been generated.")
        finalParam = {}
        wefs = WeightedEnsembleFeatureSelector()
        rank = wefs.get_ensemble_feature_importance(options, performance, labels)

        finalParam["param"] = params
        finalParam["rank"] = rank
        finalParam["finished"] = True
        self.child_conn.send(finalParam)
        LOGGER.info("The feature importances of current evaluation are: %s", rank)
        return params

    def stop_process(self):
        """stop process"""
        self.child_conn.close()
        self.terminate()

