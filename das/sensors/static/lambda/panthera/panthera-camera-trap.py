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

import datetime
import logging
import os
import sys
import tempfile
import urllib.parse

import boto3
import requests

try:
    from . import settings
except (ImportError, SystemError):
    import settings


logger = logging.getLogger(__name__)
boto3.setup_default_session(
    aws_access_key_id=settings.AWS_ACCESS_KEY_ID,
    aws_secret_access_key=settings.AWS_SECRET_ACCESS_KEY,
    region_name=settings.AWS_REGION,
)
s3_client = boto3.client("s3")


def log_stdout(level=logging.DEBUG):
    fo = logging.Formatter("%(asctime)s %(levelname)s %(processName)s %(thread)d %(name)s %(message)s")
    soh = logging.StreamHandler(sys.stdout)
    soh.setLevel(level)
    soh.setFormatter(fo)
    _logger = logging.getLogger()
    _logger.addHandler(soh)
    _logger.setLevel(level)


def handler(event, context):
    for record in event["Records"]:
        bucket = record["s3"]["bucket"]["name"]
        key = record["s3"]["object"]["key"]
        image_name = image_name_from_key(key)
        download_path = "/tmp/{}".format(image_name)
        s3_client.download_file(bucket, key, download_path)
        post_file(download_path, image_name, key)


def poll_all_targets():
    for target in settings.TARGETS:
        poll_image_bucket(target)


def date_folder_name_iter(previous_days=0):
    """Return folder names based on today's date.
    By setting previous days, return folder names based on the previous days date.
    previous_days is the number of previous days to increment from"""
    now = datetime.datetime.now(tz=datetime.timezone.utc)
    today = datetime.date(now.year, now.month, now.day)

    for i in range(previous_days, -1, -1):
        yield (today - datetime.timedelta(days=i)).strftime("%m%d%y")


def poll_image_bucket(target):
    """For each Camera, there is a day based folder name that contains that
    days images taken by the camera.
    """

    bucket = target["BUCKET"]
    logger.info("Begin poll_image_bucket: %s for DAS %s", bucket, target["DAS_API_ROOT"])

    for camera in target["CAMERAS"]:
        for folder_name in date_folder_name_iter(target["PREVIOUS_DAYS"]):
            folder_key = settings.IMAGE_KEY_TEMPLATE.format(camera=camera, date_folder=folder_name)
            images = s3_client.list_objects(Bucket=bucket, Prefix=folder_key)
            for s3_object in images.get("Contents", []):
                logger.debug("Found %s in bucket %s folder %s", s3_object, bucket, folder_key)
                if not s3_object.get("Size", 0):
                    continue
                download_and_post_image(bucket, s3_object["Key"], camera)

    logger.info("End poll_image_bucket %s", bucket)


def get_content_type(filename):
    if filename.endswith(".jpg"):
        return "application/jpeg"
    raise KeyError("Unsupported filetype: {0}".format(filename))


def get_target_for_camera(camera):
    for target in settings.TARGETS:
        if camera in target["CAMERAS"]:
            yield target


def get_path_from_key(key):
    if key.startswith("s3:"):
        return urllib.parse.urlparse(key).path
    return key


def image_name_from_key(key):
    pieces = get_path_from_key(key)
    folders = pieces.split("/")
    return folders[-1]


def parse_camera_name_from_key(key):
    pieces = get_path_from_key(key)
    folders = pieces.path.split("/")
    for name in folders:
        if name.lower().startswith("cam"):
            return name
    raise IndexError("could not find CAM folder in path {0}".format(key))


def make_camera_name(camera):
    if camera.startswith("CAM"):
        return camera
    return "CAM{0}".format(camera)


SUCCESS_CODE = (requests.codes.created, requests.codes.conflict)


def download_and_post_image(bucket, key, camera):
    image_name = image_name_from_key(key)
    image_file_path = tempfile.mkstemp()
    os.close(image_file_path[0])
    image_file_path = image_file_path[1]
    try:
        s3_client.download_file(bucket, key, image_file_path)
        post_file(image_file_path, image_name, camera)
    finally:
        try:
            os.remove(image_file_path)
        except:
            logger.exception("Failed to delete temp image file %s", image_file_path)
            raise


def post_file(image_file_path, image_name, camera):
    make_camera_name(camera)
    file_name = "CAM{camera}-{image_name}".format(camera=camera, image_name=image_name)
    for target in get_target_for_camera(camera):
        url = "{0}/sensors/camera-trap/panthera/status".format(target["DAS_API_ROOT"])
        params = {"bearer": target["DAS_TOKEN"]}
        with open(image_file_path, "rb") as fh:
            content_type = get_content_type(image_name)
            files = {"filecontent.file": (file_name, fh, content_type)}
            headers = {"Authorization": "Bearer {token}".format(token=target["DAS_TOKEN"])}
            result = requests.post(url, headers=headers, files=files)

        if result.status_code == requests.codes.bad_request:
            logger.info(
                "File post to DAS failed %s for file %s from camera %s with error: %s",
                result.status_code,
                image_name,
                camera,
                result.content.decode("utf-8"),
            )
            return

        if result.status_code not in SUCCESS_CODE:
            result.raise_for_status()
        if result.status_code == requests.codes.conflict:
            logger.debug("File %s from camera %s Already sent to DAS", image_name, camera)
            return

        logger.info("File %s from camera %s sent to DAS", image_name, camera)


if __name__ == "__main__":
    log_stdout(logging.INFO)
    poll_all_targets()
