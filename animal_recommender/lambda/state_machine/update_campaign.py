## Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
## SPDX-License-Identifier: MIT-0
import json
import boto3
import os


topic_arn = os.environ.get("sns_arn")

exploration_weight = os.environ["exploration_weight"]
min_tps = os.environ["min_tps"]
campaign_arn_ssm_path = os.environ["campaign_arn_ssm_path"]
exploration_item_age_cut_off = os.environ["exploration_item_age_cut_off"]

rerank_enabled = os.environ.get("rerank_enabled")
rerank_campaign_arn_ssm_path = os.environ["rerank_campaign_arn_ssm_path"]
rerank_min_tps = os.environ["rerank_min_tps"]


def lambda_handler(event, context):
    personalize = boto3.client("personalize")
    ssm = boto3.client("ssm")

    solution_version_arn = event["solution_version_arn"]
    solution_version_promote = event["solution_version_promote"]

    campaign_arn = str(
        ssm.get_parameter(Name=campaign_arn_ssm_path)["Parameter"]["Value"]
    )

    # If rerank is enabled, check which models can be promoted
    if rerank_enabled == "True":

        # Update recommendations campaign
        if solution_version_promote == "True":
            update_campaign = personalize.update_campaign(
                campaignArn=campaign_arn,
                solutionVersionArn=solution_version_arn,
                minProvisionedTPS=int(min_tps),
                campaignConfig={
                    "itemExplorationConfig": {
                        "explorationWeight": f"{exploration_weight}",
                        "explorationItemAgeCutOff": f"{exploration_item_age_cut_off}",
                    }
                },
            )

        rerank_promote = event["rerank_solution_version_promote"]
        rerank_solution_version_arn = event["rerank_solution_version_arn"]
        reank_campaign_arn = str(
            ssm.get_parameter(Name=rerank_campaign_arn_ssm_path)["Parameter"]["Value"]
        )
        if rerank_promote == "True":
            # Update rerank campaign
            rerank_update_campaign = personalize.update_campaign(
                campaignArn=reank_campaign_arn,
                solutionVersionArn=rerank_solution_version_arn,
                minProvisionedTPS=int(rerank_min_tps),
                campaignConfig={},
            )
            return {
                "campaign_arn": campaign_arn,
                "campaign_promote": solution_version_promote,
                "rerank_campaign_arn": reank_campaign_arn,
                "rerank_promote": rerank_promote,
            }
        else:
            return {
                "campaign_arn": campaign_arn,
                "campaign_promote": solution_version_promote,
                "rerank_campaign_arn": reank_campaign_arn,
                "rerank_promote": rerank_promote,
            }
    # If reranking is not enabled, there is only one model to promote so we do not need to check solution_version_promote since model has already passed evaluation
    else:
        # Update recommendations campaign
        update_campaign = personalize.update_campaign(
            campaignArn=campaign_arn,
            solutionVersionArn=solution_version_arn,
            minProvisionedTPS=int(min_tps),
            campaignConfig={
                "itemExplorationConfig": {
                    "explorationWeight": f"{exploration_weight}",
                    "explorationItemAgeCutOff": f"{exploration_item_age_cut_off}",
                }
            },
        )
        return {
            "campaign_arn": campaign_arn,
            "campaign_promote": solution_version_promote,
        }
