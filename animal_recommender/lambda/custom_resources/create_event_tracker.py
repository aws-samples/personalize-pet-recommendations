## Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
## SPDX-License-Identifier: MIT-0
import json
import os
import boto3

env = os.environ["env"]
event_tracker_id_ssm_path = os.environ["event_tracker_id_ssm"]
data_set_group_arn = os.environ["data_set_group_arn"]
ssm = boto3.client("ssm")
client = boto3.client("personalize")


def lambda_handler(event, context):

    response = client.create_event_tracker(
        name=f"{env}-recommender-personalize-event-tracker-tkr",
        datasetGroupArn=data_set_group_arn,
    )
    print(response)
    tracker_id = response["trackingId"]
    tracker_arn = response["eventTrackerArn"]

    put_tracker_id = ssm.put_parameter(
        Name=event_tracker_id_ssm_path,
        Value=tracker_id,
        Type="String",
        Overwrite=True,
        DataType="text",
    )

    return {"statusCode": 200, "body": tracker_arn}
