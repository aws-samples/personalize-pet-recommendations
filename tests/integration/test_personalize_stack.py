## Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
## SPDX-License-Identifier: MIT-0
import boto3, json, uuid, os, sys

script_dir = os.path.dirname(os.path.realpath(__file__))
sys.path.append(os.path.join(script_dir, "../../animal_recommender/utils"))

from constants import *

config = get_config()


session = boto3.Session(region_name=DEPLOY_REGION)
account_id = boto3.client("sts").get_caller_identity().get("Account")
sts = boto3.client("sts", region_name=DEPLOY_REGION)


def test_recommendation_response():

    ssm = session.client(
        "ssm",
        region_name=DEPLOY_REGION,
    )

    # Get the function name from SSM
    function_name = ssm.get_parameter(
        Name="/animal-recommender/personalize/recommendation/function-name"
    )["Parameter"]["Value"]

    _lambda = session.client(
        "lambda",
        region_name=DEPLOY_REGION,
    )

    test_event = read_get_recommendation()

    response = _lambda.invoke(
        FunctionName=function_name,
        Payload=f"{json.dumps(test_event)}",
    )
    res_json = json.loads(response["Payload"].read().decode("utf-8"))
    # print(res_json)
    # Serialize the response object
    list = res_json["body"].replace("[", "").replace("]", "")
    list = list.split(",")

    # Get the first recommendation
    item = list[0]
    item = json.loads(item)

    # Split recommendation into list to validate expected animal type in response
    animal = item["id"]
    animal = animal.split("-")

    assert animal[0] in ["1", "2"]
    assert response["StatusCode"] == 200


def test_reranking_response():

    ssm = session.client(
        "ssm",
        region_name=DEPLOY_REGION,
    )

    # Get the function name from SSM
    function_name = ssm.get_parameter(
        Name="/animal-recommender/personalize/reranking/function-name"
    )["Parameter"]["Value"]

    _lambda = session.client(
        "lambda",
        region_name=DEPLOY_REGION,
    )

    test_event = read_get_reranking()

    response = _lambda.invoke(
        FunctionName=function_name,
        Payload=f"{json.dumps(test_event)}",
    )
    # Decode Response object
    res_json = json.loads(response["Payload"].read().decode("utf-8"))
    # Get body of response object
    list = res_json["body"]
    res = json.loads(list)
    rerank = res["personalizeResponse"]["personalizedRanking"]
    rerank_item = rerank[0]

    assert rerank_item["itemId"].split("-")[0] in ["1", "2"]
    assert rerank_item["score"] >= 0.0
    assert response["StatusCode"] == 200


def test_put_event_kinesis():
    ssm = session.client(
        "ssm",
        region_name=DEPLOY_REGION,
    )

    # Get the function name from SSM
    steam_name = ssm.get_parameter(Name="/animal-recommender/kinesis-stream/name")[
        "Parameter"
    ]["Value"]

    kinesis = session.client(
        "kinesis",
        region_name=DEPLOY_REGION,
    )

    event = read_put_event()
    short_uuid = str(uuid.uuid4())[:8]

    response = kinesis.put_record(
        StreamName=steam_name,
        Data=json.dumps(event),
        PartitionKey=short_uuid,
    )

    assert response["EncryptionType"] in "KMS"
    assert response["ResponseMetadata"]["HTTPStatusCode"] == 200


def read_get_recommendation():
    with open("./tests/data/get_recommendation.json", "r") as filehandle:
        recs = json.load(filehandle)

    return recs


def read_get_reranking():
    with open("./tests/data/get_reranking.json", "r") as filehandle:
        rerank = json.load(filehandle)

    return rerank


def read_put_event():
    with open("./tests/data/put_event.json", "r") as filehandle:
        event = json.load(filehandle)

    return event
