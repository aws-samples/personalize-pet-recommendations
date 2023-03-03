## Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
## SPDX-License-Identifier: MIT-0
import json
import boto3
import os


solution_arn = os.environ.get("solution_arn")
topic_arn = os.environ.get("sns_arn")
rerank_solution_arn = os.environ.get("rerank_solution_arn")
rerank_enabled = os.environ.get("rerank_enabled")


def lambda_handler(event, context):
    personalize = boto3.client("personalize")

    sns = boto3.client("sns")

    create_solution_version = personalize.create_solution_version(
        solutionArn=solution_arn,
        trainingMode="FULL",
    )
    solution_version_arn = create_solution_version["solutionVersionArn"]

    print(f"rerank_enabled: {rerank_enabled}")

    if rerank_enabled == "True":
        create_rerank_solution_version = personalize.create_solution_version(
            solutionArn=rerank_solution_arn,
            trainingMode="FULL",
        )
        rerank_solution_version_arn = create_rerank_solution_version[
            "solutionVersionArn"
        ]
        publish = sns.publish(
            TopicArn=topic_arn,
            Message=f"Recommender and Rerank Model Training Started",
            Subject=f"Recommender and Rerank Model Training Started",
        )
        return {
            "solution_version_arn": solution_version_arn,
            "rerank_solution_version_arn": rerank_solution_version_arn,
        }
    else:
        publish = sns.publish(
            TopicArn=topic_arn,
            Message=f"Recommender Model Training Started",
            Subject=f"Recommender Model Training Started",
        )
        return {
            "solution_version_arn": solution_version_arn,
        }
