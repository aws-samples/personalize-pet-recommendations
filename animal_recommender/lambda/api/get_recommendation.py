## Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
## SPDX-License-Identifier: MIT-0
import boto3, base64, datetime, json, os

ssm = boto3.client("ssm")


campaign_arn_ssm_path = os.environ.get("campaign_arn_ssm_path")


def lambda_handler(event, context):

    print(f"Event: {event}")

    body = event["body"]

    campaign_arn = str(
        ssm.get_parameter(Name=campaign_arn_ssm_path)["Parameter"]["Value"]
    )

    personalizeClient = boto3.client(service_name="personalize-runtime")

    itemLimit = 10
    itemId = None
    userId = "unknown"
    response = []

    if "limit" in body:
        try:
            paramLimit = body["limit"]
            if paramLimit > 0 and paramLimit < 500:
                itemLimit = paramLimit
        except:
            print(
                "Invalid limit, could not parse or not in bounds: ",
                body["limit"],
            )

    if "userId" in body:
        try:
            userId = body["userId"]
        except:
            print(
                "Invalid userId, could not parse: ",
                body["userId"],
            )

    response = personalizeClient.get_recommendations(
        campaignArn=campaign_arn,
        userId=userId,
        numResults=itemLimit,
    )

    print(f"response {response}")

    responseItems = buildResponse(response["itemList"])
    return {"statusCode": 200, "body": json.dumps(responseItems)}


def buildResponse(recommendedItems):
    responseItems = []
    for item in recommendedItems:
        if "itemId" in item:
            responseItem = {
                "id": item["itemId"],
            }
            responseItems.append(responseItem)
        else:
            print("Found malformed item, discarding: ", item)
    return responseItems
