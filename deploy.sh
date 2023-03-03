pip3 install -r requirements.txt \
    && export VERSION=$(cat _version.py | cut -d'"' -f2) \
    && python3 seed_data/create_seed_bucket.py \
    && export S3_SEED_BUCKET=$(aws ssm get-parameter --name /animal-recommender/s3-seed-bucket/name --query "Parameter.Value" --output text --region $CDK_DEPLOY_REGION) \
    && aws s3 cp seed_data/items s3://$S3_SEED_BUCKET/seed_data/items --recursive \
    && aws s3 cp seed_data/interactions s3://$S3_SEED_BUCKET/seed_data/interactions --recursive \
    && zip -r scripts.zip animal_recommender/code_build \
    && aws s3 cp scripts.zip s3://$S3_SEED_BUCKET/$VERSION/scripts.zip \
    && cdk deploy --require-approval never --region $CDK_DEPLOY_REGION
