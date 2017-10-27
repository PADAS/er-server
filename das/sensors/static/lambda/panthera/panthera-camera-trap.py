"""
This is an aws Lambda function that responds to new images posted in an S3 bucket then pushes image to
camera-trap sensor in DAS.

A configured S3 bucket notification calls this lambda function

S3 bucket layout for Panthera:

 s3://CameraArtifacts/<camera-id>/images/<date>/<thumbnail>.jpg

 For example:
  s3://CameraArtifacts/CAM62841/Images/080317/H0345479.jpg

  We want to partition this to specify the specific cameras going to a specific DAS instance


  The setup is that Panthera has an AWS account they have granted us a user with access key
  In this first trial, we will setup this Lambda function in the DAS APN AWS account
  thus needing a cross account notification.

Below, not necessary to specify the --source-account, but provides an additional level
of security. see https://aws.amazon.com/blogs/compute/easy-authorization-of-aws-lambda-functions/

aws lambda add-permission \
  --function-name PostPantheraCameraTrapImage \
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
import urllib.parse

from . import settings

logger = logging.getLogger(__name__)
boto3.setup_default_session(aws_access_key_id=settings.AWS_ACCESS_KEY_ID,
                            aws_secret_access_key=settings.AWS_SECRET_ACCESS_KEY,
                            region_name=settings.AWS_REGION)
s3_client = boto3.client('s3')


def handler(event, context):
    for record in event['Records']:
        bucket = record['s3']['bucket']['name']
        key = record['s3']['object']['key']
        image_name = image_name_from_key(key)
        download_path = '/tmp/{}'.format(image_name)
        s3_client.download_file(bucket, key, download_path)
        post_file(download_path, image_name, key)


def get_content_type(filename):
    if filename.endswith('.jpg'):
        return 'application/jpeg'
    raise KeyError('Unsupported filetype: {0}'.format(filename))


def get_target_for_camera(camera):
    for target in settings.TARGETS:
        if camera in target['CAMERAS']:
            yield target


def get_path_from_key(key):
    if key.startswith('s3:'):
        return urllib.parse.urlparse(key).path
    return key


def image_name_from_key(key):
    pieces = get_path_from_key(key)
    folders = pieces.path.split('/')
    return folders[-1]


def parse_camera_name_from_key(key):
    pieces = get_path_from_key(key)
    folders = pieces.path.split('/')
    for name in folders:
        if name.lower().startswith('cam'):
            return name
    raise IndexError('could not find CAM folder in path {0}'.format(key))


def post_file(image_file_path, image_name, key):
    camera_name = parse_camera_name_from_key(key)
    for target in get_target_for_camera(camera_name):
        url = '{0}/sensors/camera-trap/panthera/status'.format(
            target['DAS_API_ROOT'])
        params = {'bearer': target['DAS_TOKEN']}
        with open(image_file_path, 'rb') as fh:
            files = {'filecontent.file': (image_name, fh,
                                          get_content_type(image_name))}
            result = requests.post(url, params=params, files=files)

        if result.status_code != requests.codes.created:
            result.raise_for_status()
