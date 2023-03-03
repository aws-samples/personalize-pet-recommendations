## Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
## SPDX-License-Identifier: MIT-0
import json
import boto3
import os


topic_arn = os.environ.get("sns_arn")
promotion_threshold = os.environ["promotion_threshold"]
rerank_enabled = os.environ.get("rerank_enabled")


def lambda_handler(event, context):
    personalize = boto3.client("personalize")

    sns = boto3.client("sns")
    solution_version_arn = event["solution_version_arn"]

    evaluate_solution_version = personalize.get_solution_metrics(
        solutionVersionArn=solution_version_arn,
    )

    print(f"Solution Metrics: {evaluate_solution_version}")

    coverage = evaluate_solution_version["metrics"]["coverage"]
    normalized_discounted_cumulative_gain_at_5 = evaluate_solution_version["metrics"][
        "normalized_discounted_cumulative_gain_at_5"
    ]

    promote = False
    rerank_promote = "False"

    if rerank_enabled == "True":

        rerank_solution_version_arn = event["rerank_solution_version_arn"]

        evaluate_rerank_solution_version = personalize.get_solution_metrics(
            solutionVersionArn=rerank_solution_version_arn,
        )

        rerank_coverage = evaluate_rerank_solution_version["metrics"]["coverage"]
        rerank_normalized_discounted_cumulative_gain_at_5 = (
            evaluate_rerank_solution_version["metrics"][
                "normalized_discounted_cumulative_gain_at_5"
            ]
        )
        if rerank_normalized_discounted_cumulative_gain_at_5 > float(
            promotion_threshold
        ):
            rerank_promote = "True"
            publish = sns.publish(
                TopicArn=topic_arn,
                Message=f"Rerank Model Promoted: {rerank_solution_version_arn}",
                Subject=f"Rerank Model Promoted",
            )
        else:
            publish = sns.publish(
                TopicArn=topic_arn,
                Message=f"Rerank Model Not Promoted: {rerank_solution_version_arn}",
                Subject=f"Rerank Model Not Promoted",
            )

    recommender_promote = "False"
    if normalized_discounted_cumulative_gain_at_5 > float(promotion_threshold):
        recommender_promote = "True"
        publish = sns.publish(
            TopicArn=topic_arn,
            Message=f"Recommender Model Promoted: {solution_version_arn}",
            Subject=f"Recommender Model Promoted",
        )
    else:
        publish = sns.publish(
            TopicArn=topic_arn,
            Message=f"Recommender Model Not Promoted: {solution_version_arn}",
            Subject=f"Recommender Model Not Promoted",
        )

    if recommender_promote == "True" or rerank_promote == "True":
        promote = True

    if rerank_enabled == "True":
        return {
            "solution_version_arn": solution_version_arn,
            "solution_version_promote": recommender_promote,
            "rerank_solution_version_arn": rerank_solution_version_arn,
            "rerank_solution_version_promote": rerank_promote,
            "promote": promote,
        }
    else:
        return {
            "solution_version_arn": solution_version_arn,
            "solution_version_promote": recommender_promote,
            "promote": promote,
        }
