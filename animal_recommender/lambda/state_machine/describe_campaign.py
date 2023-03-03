## Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
## SPDX-License-Identifier: MIT-0
import json
import boto3
import os


topic_arn = os.environ.get("sns_arn")
campaign_arn_ssm_path = os.environ["campaign_arn_ssm"]

rerank_enabled = os.environ.get("rerank_enabled")
rerank_campaign_arn_ssm_path = os.environ["rerank_campaign_arn_ssm_path"]


def lambda_handler(event, context):
    personalize = boto3.client("personalize")
    ssm = boto3.client("ssm")
    sns = boto3.client("sns")

    campaign_arn = str(
        ssm.get_parameter(Name=campaign_arn_ssm_path)["Parameter"]["Value"]
    )

    describe_campaign = personalize.describe_campaign(
        campaignArn=campaign_arn,
    )

    campaign_status = describe_campaign["campaign"]["latestCampaignUpdate"]["status"]

    if rerank_enabled == "True":
        rerank_campaign_arn = str(
            ssm.get_parameter(Name=campaign_arn_ssm_path)["Parameter"]["Value"]
        )
        rerank_describe_campaign = personalize.describe_campaign(
            campaignArn=rerank_campaign_arn,
        )
        rerank_status = rerank_describe_campaign["campaign"]["latestCampaignUpdate"][
            "status"
        ]
        if campaign_status in "ACTIVE" and rerank_status in "ACTIVE":
            publish = sns.publish(
                TopicArn=topic_arn,
                Message=f"Recommender and Rerank Campaign Update Completed: {campaign_arn}",
                Subject=f"Recommender and Rerank Campaign Update Completed",
            )
            return {
                "campaign_arn": campaign_arn,
                "status": campaign_status,
                "rerank_campaign_arn": rerank_campaign_arn,
                "rerank_status": rerank_status,
            }
        elif (
            campaign_status in "CREATE PENDING"
            or campaign_status in "CREATE IN_PROGRESS"
            or rerank_status in "CREATE PENDING"
            or rerank_status in "CREATE IN_PROGRESS"
        ):
            print(
                f"Update in Progress:\n Recommender Status: {campaign_status}\n Rerank Status: {rerank_status}"
            )
            raise Exception("Update in Progress")
        else:
            print(
                f"Update Failed:\n Recommender Status: {campaign_status}\n Rerank Status: {rerank_status}"
            )
            raise Exception("Update Failed")
    else:
        if campaign_status in "ACTIVE":
            publish = sns.publish(
                TopicArn=topic_arn,
                Message=f"Recommender Campaign Update Completed: {campaign_arn}",
                Subject=f"Recommender Campaign Update Completed",
            )
            return {"campaign_arn": campaign_arn, "status": campaign_status}
        elif (
            campaign_status in "CREATE PENDING"
            or campaign_status in "CREATE IN_PROGRESS"
        ):
            print(f"Update in Progress: {campaign_status}")
            raise Exception("Update in Progress")
        else:
            print(f"STATUS: {campaign_status}")
            raise Exception("Update Failed")
