# Copyright (c) Microsoft Corporation.
# Licensed under the MIT license.


import json
import os

from redis import Redis
from typing import Any

from ..cli.utils.details_reader import DetailsReader


def report_final_result(result: Any):
    local_master_details = DetailsReader.load_local_master_details()
    redis_connection = Redis(host=local_master_details['hostname'], port=local_master_details['redis']['port'],
                             charset='utf-8', decode_responses=True)
    name = os.environ['FINAL_RESULT_KEY']
    job_name = os.environ['JOB_NAME']
    redis_connection.hset(name, job_name, json.dumps(result))
