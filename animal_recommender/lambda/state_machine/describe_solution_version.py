## Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
## SPDX-License-Identifier: MIT-0
import json
import boto3
import os


topic_arn = os.environ.get("sns_arn")
rerank_enabled = os.environ.get("rerank_enabled")


def lambda_handler(event, context):
    personalize = boto3.client("personalize")

    solution_version_arn = event["solution_version_arn"]

    describe_solution_version = personalize.describe_solution_version(
        solutionVersionArn=solution_version_arn
    )

    solution_version_status = describe_solution_version["solutionVersion"]["status"]

    if rerank_enabled == "True":
        rerank_solution_version_arn = event["rerank_solution_version_arn"]
        rerank_describe_solution_version = personalize.describe_solution_version(
            solutionVersionArn=rerank_solution_version_arn
        )

        rerank_solution_version_status = rerank_describe_solution_version[
            "solutionVersion"
        ]["status"]

        if (
            solution_version_status in "ACTIVE"
            and rerank_solution_version_status in "ACTIVE"
        ):
            return {
                "solution_version_arn": solution_version_arn,
                "rerank_solution_version_arn": rerank_solution_version_arn,
            }
        else:
            print(
                f"Recommender Status: {solution_version_status}\n Rerank Status: {rerank_solution_version_status} "
            )
            raise Exception(f"Training not completed")

    else:
        if solution_version_status in "ACTIVE":
            return {
                "solution_version_arn": solution_version_arn,
                "solution_version_status": "ACTIVE",
            }
        else:
            print(f"Model Status: {solution_version_status} ")
            raise Exception(f"Training not completed")
