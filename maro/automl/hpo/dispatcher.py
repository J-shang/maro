# Copyright (c) Microsoft Corporation.
# Licensed under the MIT license.


import copy
import json

from redis import Redis
from time import sleep

from nni.tuner import Tuner

_parameter_id = 0

def _get_parameter_id():
    # Each parameter id corresponds to a parameter and a job yaml file.
    global _parameter_id
    _parameter_id += 1
    return _parameter_id - 1

def _back_parameter_id(back_num: int):
    # Fallback, if the tuner cannot generate the required parameters.
    global _parameter_id
    _parameter_id -= back_num


class Dispatcher():
    def __init__(self, tuner: Tuner, redis_connection: Redis, tuner_job_name: str, cluster_name: str, job_temp: dict):
        self.tuner = tuner
        self.redis_connection = redis_connection
        self.tuner_job_name = tuner_job_name
        self.cluster_name = cluster_name
        self.job_temp = job_temp

        self.remaining_budget = 1

        self.stopping = False
        self.parameter_dict = {}

        self.redis_key_final_metric = '{}:job_final_metric'.format(self.cluster_name)

    def run(self):
        while not self.stopping:
            self._check_metric_value()

            if self.remaining_budget > 0:
                parameter_ids = [_get_parameter_id() for i in range(self.remaining_budget)]
                parameters = self.tuner.generate_multiple_parameters(parameter_ids)
                self.remaining_budget -= len(parameters)
                _back_parameter_id(self.remaining_budget)

                for i, _ in enumerate(parameters):
                    self.parameter_dict[parameter_ids[i]] = parameters[i]
                    job_detail = copy.deepcopy(self.job_temp)

                    job_detail['name'] = 'cluster-{}-job-{}'.format(self.cluster_name, parameter_ids[i])
                    param = json.dumps(parameters[i])
                    for key, value in job_detail['components'].items():
                        value['command'] = value['command'].format(param)
                    self._tuner_push_pending_job(job_detail)
            sleep(5)

    def _check_metric_value(self):
        metric_value_dict = self.redis_connection.hgetall(self.redis_key_final_metric)
        parameter_ids = list(self.parameter_dict.keys())
        for key in parameter_ids:
            job_key = 'cluster-{}-job-{}'.format(self.cluster_name, key).encode()
            if job_key in metric_value_dict:
                # assume the metric is float
                self.tuner.receive_trial_result(key, self.parameter_dict[key], float(metric_value_dict[job_key]))
                self.parameter_dict.pop(key)
                self.remaining_budget += 1

    def _tuner_push_pending_job(self, job_details: dict):
        job_name = job_details['name']
        # Push job details to redis
        self.redis_connection.hset(
            '{}:job_details'.format(self.cluster_name),
            job_name,
            json.dumps(job_details)
        )

        # Push job name to pending_job_tickets
        self.redis_connection.lpush(
            '{}:pending_job_tickets'.format(self.cluster_name),
            job_name
        )

        tuner_detail = json.loads(self.redis_connection.hget(
            '{}:job_details'.format(self.cluster_name),
            self.tuner_job_name
        ))

        tuner_detail['job_names'].append(job_details['name'])
        self.redis_connection.hset(
            '{}:job_details'.format(self.cluster_name),
            self.tuner_job_name,
            json.dumps(tuner_detail)
        )
