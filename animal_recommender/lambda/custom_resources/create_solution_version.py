## Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
## SPDX-License-Identifier: MIT-0
import json
import os
import boto3

solution_arn = os.environ["solution_arn"]
solution_arn_ssm_path = os.environ["solution_version_arn_ssm_path"]
ssm = boto3.client("ssm")
client = boto3.client("personalize")


def lambda_handler(event, context):

    response = client.create_solution_version(
        solutionArn=solution_arn,
        trainingMode="FULL",
    )
    print(response)
    solution_version_arn = response["solutionVersionArn"]

    put_solution_version_arn = ssm.put_parameter(
        Name=solution_arn_ssm_path,
        Value=solution_version_arn,
        Type="String",
        Overwrite=True,
        DataType="text",
    )

    return {"PhysicalResourceId": "CustomSolutionVersion"}
