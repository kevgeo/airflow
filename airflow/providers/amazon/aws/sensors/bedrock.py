#
# Licensed to the Apache Software Foundation (ASF) under one
# or more contributor license agreements.  See the NOTICE file
# distributed with this work for additional information
# regarding copyright ownership.  The ASF licenses this file
# to you under the Apache License, Version 2.0 (the
# "License"); you may not use this file except in compliance
# with the License.  You may obtain a copy of the License at
#
#   http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing,
# software distributed under the License is distributed on an
# "AS IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY
# KIND, either express or implied.  See the License for the
# specific language governing permissions and limitations
# under the License.
from __future__ import annotations

from typing import TYPE_CHECKING, Any, Sequence

from airflow.configuration import conf
from airflow.providers.amazon.aws.sensors.base_aws import AwsBaseSensor
from airflow.providers.amazon.aws.triggers.bedrock import BedrockCustomizeModelCompletedTrigger
from airflow.providers.amazon.aws.utils.mixins import aws_template_fields

if TYPE_CHECKING:
    from airflow.utils.context import Context

from airflow.exceptions import AirflowException, AirflowSkipException
from airflow.providers.amazon.aws.hooks.bedrock import BedrockHook


class BedrockCustomizeModelCompletedSensor(AwsBaseSensor[BedrockHook]):
    """
    Poll the state of the model customization job until it reaches a terminal state; fails if the job fails.

    .. seealso::
        For more information on how to use this sensor, take a look at the guide:
        :ref:`howto/sensor:BedrockCustomizeModelCompletedSensor`


    :param job_name: The name of the Bedrock model customization job.

    :param deferrable: If True, the sensor will operate in deferrable mode. This mode requires aiobotocore
        module to be installed.
        (default: False, but can be overridden in config file by setting default_deferrable to True)
    :param max_retries: Number of times before returning the current state. (default: 75)
    :param poke_interval: Polling period in seconds to check for the status of the job. (default: 120)
    :param aws_conn_id: The Airflow connection used for AWS credentials.
        If this is ``None`` or empty then the default boto3 behaviour is used. If
        running Airflow in a distributed manner and aws_conn_id is None or
        empty, then default boto3 configuration would be used (and must be
        maintained on each worker node).
    :param region_name: AWS region_name. If not specified then the default boto3 behaviour is used.
    :param verify: Whether or not to verify SSL certificates. See:
        https://boto3.amazonaws.com/v1/documentation/api/latest/reference/core/session.html
    :param botocore_config: Configuration dictionary (key-values) for botocore client. See:
        https://botocore.amazonaws.com/v1/documentation/api/latest/reference/config.html
    """

    INTERMEDIATE_STATES = ("InProgress",)
    FAILURE_STATES = ("Failed", "Stopping", "Stopped")
    SUCCESS_STATES = ("Completed",)
    FAILURE_MESSAGE = "Bedrock model customization job sensor failed."

    aws_hook_class = BedrockHook
    template_fields: Sequence[str] = aws_template_fields("job_name")
    ui_color = "#66c3ff"

    def __init__(
        self,
        *,
        job_name: str,
        max_retries: int = 75,
        poke_interval: int = 120,
        deferrable: bool = conf.getboolean("operators", "default_deferrable", fallback=False),
        **kwargs: Any,
    ) -> None:
        super().__init__(**kwargs)
        self.job_name = job_name
        self.poke_interval = poke_interval
        self.max_retries = max_retries
        self.deferrable = deferrable

    def execute(self, context: Context) -> Any:
        if self.deferrable:
            self.defer(
                trigger=BedrockCustomizeModelCompletedTrigger(
                    job_name=self.job_name,
                    waiter_delay=int(self.poke_interval),
                    waiter_max_attempts=self.max_retries,
                    aws_conn_id=self.aws_conn_id,
                ),
                method_name="poke",
            )
        else:
            super().execute(context=context)

    def poke(self, context: Context) -> bool:
        state = self.hook.conn.get_model_customization_job(jobIdentifier=self.job_name)["status"]
        self.log.info("Job '%s' state: %s", self.job_name, state)

        if state in self.FAILURE_STATES:
            # TODO: remove this if block when min_airflow_version is set to higher than 2.7.1
            if self.soft_fail:
                raise AirflowSkipException(self.FAILURE_MESSAGE)
            raise AirflowException(self.FAILURE_MESSAGE)

        return state not in self.INTERMEDIATE_STATES
