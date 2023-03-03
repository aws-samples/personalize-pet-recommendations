## Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
## SPDX-License-Identifier: MIT-0
import boto3, base64, datetime, json, os

ssm = boto3.client("ssm")

event_tracker_ssm_path = os.environ.get("event_tracker_ssm_path")


def lambda_handler(event, context):
    # expected event information
    # trackingId
    # timestamp (epoch format)
    # user_id,
    # fullvisitorid,
    # sessionid,
    # animalid,
    # animal_metadata, # for testing at least, and maybe in prod also
    # eventtype (AIF, favorite, detailview)
    records = event["Records"]
    tracking_id = str(
        ssm.get_parameter(Name=event_tracker_ssm_path)["Parameter"]["Value"]
    )

    for record in records:

        data = record["kinesis"]["data"]
        decoded_data = base64.b64decode(data)

        deserialized_data = json.loads(decoded_data)

        print(f"\ndeserialized_data: {deserialized_data}")

        timestamp = datetime.datetime.now()
        userId = None
        response = []
        session_id = deserialized_data["sessionId"]
        event_type = deserialized_data["eventType"]

        # expect at least breed, age
        animal_metadata = deserialized_data["animalMetadata"]

        # convert to animal group here
        # these are properties of the legacy animals table
        animal_group_id = (
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

        if "userId" in deserialized_data:
            try:
                userId = deserialized_data["userId"]
            except:
                print(
                    "Invalid userId, could not parse: ",
                    deserialized_data["userId"],
                )

        personalize_events = boto3.client(service_name="personalize-events")

        if userId is not None:
            response = personalize_events.put_events(
                trackingId=tracking_id,
                userId=userId,
                sessionId=session_id,
                eventList=[
                    {
                        "sentAt": timestamp,
                        "eventType": event_type,
                        "itemId": animal_group_id,
                    }
                ],
            )
            print(f"Authenticated user: {response}")
        else:
            response = personalize_events.put_events(
                trackingId=tracking_id,
                sessionId=session_id,
                eventList=[
                    {
                        "sentAt": timestamp,
                        "eventType": event_type,
                        "itemId": animal_group_id,
                    }
                ],
            )
            print(f"Authenticated user: {response}")

        # print(f"Response: {response}")
