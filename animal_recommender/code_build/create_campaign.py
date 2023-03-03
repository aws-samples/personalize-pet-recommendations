## Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
## SPDX-License-Identifier: MIT-0
import json
import os
import boto3
import time

env = os.environ["env"]
exploration_weight = os.environ["exploration_weight"]
min_tps = os.environ["min_tps"]
solution_version_ssm_path = os.environ["solution_version_ssm_path"]
campaign_arn_ssm_path = os.environ["campaign_arn_ssm_path"]
exploration_item_age_cut_off = os.environ["exploration_item_age_cut_off"]
campaign_type = os.environ["campaign_type"]
ssm = boto3.client("ssm")
client = boto3.client("personalize")


def main():

    time.sleep(120.0)
    solution_version_arn = str(
        ssm.get_parameter(Name=solution_version_ssm_path)["Parameter"]["Value"]
    )

    solution_version_ready = False
    while solution_version_ready == False:
        solution_version = client.describe_solution_version(
            solutionVersionArn=solution_version_arn,
        )
        solution_version_status = solution_version["solutionVersion"]["status"]
        print(f"Solution Version Status: {solution_version_status}")
        if solution_version_status in "ACTIVE":
            solution_version_ready = True
        elif (
            solution_version_status in "CREATE FAILED"
            or solution_version_status in "CREATE STOPPED"
            or solution_version_status in "CREATE STOPPING"
        ):
            raise Exception("Solution Version Creation Failed")
        else:
            print("Solution Version not Active, sleep")
            time.sleep(60.0)

    campaign_config = {}
    if campaign_type in "reranking":
        campaign_config = {}
    elif campaign_type in "recommender":
        campaign_config = {
            "itemExplorationConfig": {
                "explorationWeight": f"{exploration_weight}",
                "explorationItemAgeCutOff": f"{exploration_item_age_cut_off}",
            }
        }
    else:
        print(f"Invalid Campaign Type: {campaign_type}")
        raise Exception(f"Invalid Campaign Type: {campaign_type}")

    response = client.create_campaign(
        name=f"{env}-{campaign_type}-personalize-campaign-cpn",
        solutionVersionArn=solution_version_arn,
        minProvisionedTPS=int(min_tps),
        campaignConfig=campaign_config,
    )
    print(response)
    campaign_arn = response["campaignArn"]

    put_campaign_arn = ssm.put_parameter(
        Name=campaign_arn_ssm_path,
        Value=campaign_arn,
        Type="String",
        Overwrite=True,
        DataType="text",
    )

    status = ""
    campaign_active = False
    while campaign_active == False:
        campaign_status = client.describe_campaign(
            campaignArn=campaign_arn,
        )
        print(response)
        status = campaign_status["campaign"]["status"]
        print(f"\nStatus: {status}")
        if status in "ACTIVE":
            print(f"Campaign is Active: {campaign_arn}")
            campaign_active = True
        else:
            print("Campaign not Active, sleep")
            time.sleep(60.0)


if __name__ == "__main__":
    main()
