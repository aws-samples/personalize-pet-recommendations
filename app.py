#!/usr/bin/env python3
import os

import aws_cdk as cdk

from animal_recommender.animal_recommender_stack import AnimalRecommenderStack
from animal_recommender.utils.constants import *

stack_name = f"{ENV_PREFIX}-animal-recommender"

app = cdk.App()
AnimalRecommenderStack(
    app,
    stack_name,
    SEED_BUCKET,
    env=cdk.Environment(account=ACCOUNT_ID, region=DEPLOY_REGION),
)


app.synth()
