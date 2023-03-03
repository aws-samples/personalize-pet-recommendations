## Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
## SPDX-License-Identifier: MIT-0
from collections import defaultdict
import boto3, base64, datetime, json, os

ssm = boto3.client("ssm")


campaign_arn_ssm_path = os.environ.get("reranking_campaign_arn_ssm_path")


def group_id_from_metadata(animal_metadata):
    return (
        str(animal_metadata["animal_species_id"])
        + "-"
        + str(animal_metadata["animal_primary_breed_id"])
        + "-"
        + str(
            animal_metadata["animal_size_id"]
            + "-"
            + str(animal_metadata["animal_age_id"])
        )
    )


def lambda_handler(event, context):

    print(f"Event: {event}")

    body = event["body"]

    campaign_arn = str(
        ssm.get_parameter(Name=campaign_arn_ssm_path)["Parameter"]["Value"]
    )

    personalize_runtime = boto3.client(service_name="personalize-runtime")

    items = body["itemMetadataList"]
    id_group_pairs = []
    for item_meta in items:
        animal_metadata = item_meta["animalMetadata"]
        animal_group_id = group_id_from_metadata(animal_metadata)
        id_group_pairs.append((item_meta["itemId"], animal_group_id))

    input_list = list(set(pair[1] for pair in id_group_pairs))
    inverse_mapping = defaultdict(list)
    for pair in id_group_pairs:
        inverse_mapping[pair[1]].append(pair[0])

    user_id = body["userId"]

    response = personalize_runtime.get_personalized_ranking(
        campaignArn=campaign_arn, inputList=input_list, userId=user_id
    )

    reranking = [item_dict["itemId"] for item_dict in response["personalizedRanking"]]
    ranked_items = []
    for animal_group in reranking:
        ranked_items += inverse_mapping[animal_group]
    data = json.dumps({"ranking": ranked_items, "personalizeResponse": response})
    print(data)
    return {
        "statusCode": 200,
        "body": json.dumps({"ranking": ranked_items, "personalizeResponse": response}),
    }
