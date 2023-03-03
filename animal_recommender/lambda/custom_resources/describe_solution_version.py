## Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
## SPDX-License-Identifier: MIT-0
import json
import boto3
import os


topic_arn = os.environ.get("sns_arn")
solution_version_arn_ssm_path = os.environ["solution_version_arn_ssm_path"]


def lambda_handler(event, context):
    request_type = event["RequestType"].lower()
    personalize = boto3.client("personalize")
    ssm = boto3.client("ssm")

    solution_version_arn = str(
        ssm.get_parameter(Name=solution_version_arn_ssm_path)["Parameter"]["Value"]
    )

    describe_solution_version = personalize.describe_solution_version(
        solutionVersionArn=solution_version_arn
    )

    solution_version_status = describe_solution_version["solutionVersion"]["status"]

    if request_type == "create":
        if solution_version_status in "ACTIVE":
            is_ready = True
        else:
            print(f"Solution Version Status: {solution_version_status}")
            is_ready = False
    if request_type == "update":
        print(f"No Updates to perform")
        # Implement update wait logic here using the data in event['OldResourceProperties']
        is_ready = True
    if request_type == "delete":
        is_ready = True

    return {"IsComplete": is_ready}
