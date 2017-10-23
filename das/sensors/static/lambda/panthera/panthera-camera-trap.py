"""
This is a aws LAMBDA function that responds to new images posted in an S3 bucket then pushes image to
camera-trap sensor in DAS.

An configured S3 bucket notification calls this lambda function

S3 bucket layout for Panthera:

 s3://CameraArtifacts/<camera-id>/images/<date>/<thumbnail>.jpg

 For example:
  s3://CameraArtifacts/CAM62841/Images/080317/H0345479.jpg

  We want to partition this to specify the specific cameras going to a specific DAS instance


  The setup is that Panthera has an AWS account they have granted us a user with access key
  In this first trial, we will setup this Lambda function in the DAS AWS account
  thus needing a cross account notification.

Below, not necessary to specify the --source-account, but provides an additional level
of security. see https://aws.amazon.com/blogs/compute/easy-authorization-of-aws-lambda-functions/

aws lambda add-permission \
  --function-name PostCameraTrapImage \
  --region us-west-2 \
  --statement-id Id-123 \
  --action "lambda:InvokeFunction" \
  --principal s3.amazonaws.com \
  --source-arn arn:aws:s3:::CameraArtifacts \
  --source-account <account number> \
  --profile adminuser

"""
import logging
import boto3
import requests

from . import settings

logger = logging.getLogger(__name__)
boto3.setup_default_session()
s3_client = boto3.client('s3')


def handler(event, context):
    for record in event['Records']:
        bucket = record['s3']['bucket']['name']
        key = record['s3']['object']['key']
        download_path = '/tmp/{}'.format(key)
        s3_client.download_file(bucket, key, download_path)
        post_file(download_path, key)


def get_content_type(filename):
    if filename.endswith('.jpg'):
        return 'application/jpeg'
    raise KeyError('Unsupported filetype: {0}'.format(filename))


def post_file(image_file_path, filename):
    url = '{0}/sensors/camera-trap/panthera/status'.format(settings.DAS_API_ROOT)
    params = {'bearer': settings.DAS_TOKEN}
    with open(image_file_path, 'rb') as fh:
        files = {'file': (filename, fh,
                 get_content_type(filename))}
        result = requests.post(url, params=params)

    if result.status_code != requests.codes.created:
        result.raise_for_status()
