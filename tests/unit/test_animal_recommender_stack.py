## Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
## SPDX-License-Identifier: MIT-0
import aws_cdk as core
import aws_cdk.assertions as assertions

from animal_recommender.animal_recommender_stack import AnimalRecommenderStack
from animal_recommender.utils.constants import *


def test_lambdas_created():
    # Given
    app = core.App()

    # When
    stack = AnimalRecommenderStack(
        app,
        "animal-recommender",
        seed_bucket_name="example-seed-bucket",
        env=core.Environment(account=ACCOUNT_ID, region="us-east-1"),
    )
    template = assertions.Template.from_stack(stack)

    # Then
    template = app.synth().get_stack_by_name("animal-recommender").template

    lambdas = [
        resource
        for resource in template["Resources"].values()
        if resource["Type"] == "AWS::Lambda::Function"
    ]

    assert len(lambdas) == 12
